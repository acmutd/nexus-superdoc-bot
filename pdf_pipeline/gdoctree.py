from markdown_it import MarkdownIt  
from markdown_it.tree import SyntaxTreeNode

from io import BytesIO
import pymupdf.layout
import pymupdf4llm
import pymupdf

import numpy as np
from langchain_openai import OpenAIEmbeddings,ChatOpenAI

from typing import Callable, Any, Generator, Iterator, TypeVar
from itertools import tee

from dotenv import load_dotenv
import os
import time
import traceback

from pdf_pipeline.etree import EmbedTreeNode


class GdocTreeNode():
    """
    Acts as a bridge between the semantic tree and the Google Docs API.
    Its primary job is to calculate indices and generate 'BatchUpdate' requests.
    """
    def __init__(self,enode:EmbedTreeNode):
        """
        Initializes the node by mirroring the structure of its semantic counterpart.
        It keeps track of content, node type, and whether it was a 'custom' injected heading.
        """
        self.enode = enode
        self.node = enode.node
        self.type = enode.type
        # Ensure we grab the 'content' string set during insert_custom_headings
        self.content = enode.content 
        self.children = []
        self.is_custom_node = enode.is_custom_node
    @classmethod
    def _init_tree(cls,etree:EmbedTreeNode):
        """
        A recursive factory method. It walks the entire EmbedTree and 
        wraps every node in a GdocTreeNode layer, preserving the hierarchy.
        """ 
        #create current node's wrapper object
        curr = cls(enode=etree)
        #wrap all its children
        for child in etree.children: 
            gdoc_child = cls._init_tree(child)
            curr.children.append(gdoc_child)
        #return wrapper object
        return curr
   
    def _dispatch_node_type(self, index: int, level: int, context: dict = None) -> tuple[list[dict], list[dict], int]:
        """
        The 'Traffic Controller.' It looks at the Markdown node type (heading, paragraph, list)
        and decides which specific formatting method should handle the text generation.
        """
        node_type = self.node.type
        context = context or {}

        if self.is_custom_node:
            header_text = f"{self.content}:\n\n"
            u16_len = text_utf16_len(header_text)

            start_index = index - u16_len

            # Make the custom header bold
            '''
            format_request = {
                'updateTextStyle': {
                    'textStyle': {'bold': True},
                    'range': {
                        'startIndex': start_index,
                        'endIndex': start_index + u16_len
                    },
                    'fields': 'bold'
                }
            }
            '''
            return [], [], 0    

        if node_type == "heading":
            return self._format_heading(index, level)

        if node_type == "paragraph":
            # Paragraph is now the leaf renderer
            return self._format_paragraph_as_leaf(index, level, context)
        
        if node_type in ["bullet_list", "ordered_list"]:
            # Lists don't insert text themselves, they just pass context to children
            return [], [], 0 

        if node_type == "list_item":
            # Determine list type from parent or node attribute
            list_type = context.get("list_type", "BULLET") 
            return [], [], 0 # Handled by the paragraph child via context

        return [], [], 0

    def generate_formatted_requests(self, start_index: int, level: int = 0, context: dict = None) -> tuple[list[dict], list[dict], int]:
        """
        The recursive engine of the class. It calculates the 'current_offset' (how many 
        characters have been inserted) so that the next node knows exactly where to 
        start its insertion in the Google Doc.
        """
        all_text_requests = []
        all_format_requests = []
        current_offset = 0

        # Initialize/Update context
        current_context = (context or {}).copy()
        if self.node.type == "bullet_list":
            current_context["list_mode"] = "BULLET"
        elif self.node.type == "ordered_list":
            current_context["list_mode"] = "ORDERED"

        # Dispatch logic
        node_text_reqs, node_format_reqs, node_len = self._dispatch_node_type(start_index, level, current_context)

        all_text_requests.extend(node_text_reqs)
        all_format_requests.extend(node_format_reqs)
        current_offset += node_len

        # If this is a Paragraph, it has already processed its internal TEXT children.
        # We only recurse for non-leaf containers (Lists, Sections, etc.)
        if self.is_custom_node or self.node.type not in ["paragraph", "text"]:
            for child in self.children:
                c_text, c_format, c_len = child.generate_formatted_requests(
                    start_index + current_offset, 
                    level + 1, 
                    current_context
                )
                all_text_requests.extend(c_text)
                all_format_requests.extend(c_format)
                current_offset += c_len

        return all_text_requests, all_format_requests, current_offset

    def _format_heading(self, index: int,level:int) -> tuple[list[dict], int]:
        """
        Generates requests to insert heading text and applies 'HEADING_X' 
        paragraph styles based on the tree depth.
        """
        
         # Use self.enode.content (where custom headings store text) or self.content
        content = getattr(self.enode, 'content', self.content) or "Untitled"
        text = content.strip() + "\n"
        text_len = len(text.encode("utf-16-le")) // 2

        # HEADING_1, HEADING_2, etc.
        heading_type = f"HEADING_{min(level + 2, 6)}"

        text_requests = [{'insertText': {'location': {'index': index}, 'text': text}}]
        format_requests = [{
            'updateParagraphStyle': {
                'range': {'startIndex': index, 'endIndex': index + text_len},
                'paragraphStyle': {'namedStyleType': heading_type},
                'fields': 'namedStyleType'
            }
        }]
        return text_requests, format_requests, text_len

    def _format_paragraph_as_leaf(self, index: int, level: int, context: dict) -> tuple[list[dict], list[dict], int]:
        """
        Handles the insertion of body text. This is where complex layout logic 
        happens, including indentation math (measured in Points) and 
        attaching bullet/numbering presets to paragraphs.
        """
        
        #Clean the content - strip to prevent double-spacing
        raw_content = self._extract_clean_text(self).strip()
        if not raw_content:
            return [], [], 0
    
        is_list = context.get("list_mode") is not None
        
        
        final_text = f"{raw_content}\n" if is_list else f"{raw_content}\n\n"
        # Calculate length using UTF-16 (Google Docs requirement)
        text_len = len(final_text.encode("utf-16-le")) // 2
        
        text_requests = [{
            'insertText': {
                'location': {'index': index},
                'text': final_text
            }
        }]
    
        format_requests = []
        
        
        # Define Indentation Math (Standard: 18pt or 36pt per level)
        # bullet_offset: Where the bullet or the first character sits
        # text_offset: Where the actual block of text aligns
        bullet_offset = level * 36
        text_offset = (level + 1) * 36
    
        if is_list:
            # Create the Bullet
            format_requests.append({
                'createParagraphBullets': {
                    'range': {'startIndex': index, 'endIndex': index + text_len},
                    'bulletPreset': 'BULLET_DISC_CIRCLE_SQUARE' if context["list_mode"] == "BULLET" else 'NUMBERED_DECIMAL_ALPHA_ROMAN'
                }
            })
        else:
            # For standard text, we want the first line and the rest of the block 
            # to start at the same indented position (unlike a bullet)
            bullet_offset = text_offset 
    
        # Apply the Paragraph Style (The "Alignment Fix")
        format_requests.append({
            'updateParagraphStyle': {
                'paragraphStyle': {
                    'indentFirstLine': {'magnitude': bullet_offset, 'unit': 'PT'},
                    'indentStart': {'magnitude': text_offset, 'unit': 'PT'},
                    'namedStyleType': 'NORMAL_TEXT'
                },
                'range': {'startIndex': index, 'endIndex': index + text_len},
                'fields': 'indentFirstLine,indentStart,namedStyleType'
            }
        })
    
        return text_requests, format_requests, text_len

    def _extract_clean_text(self, node) -> str:
        """
        A recursive cleaner. It digs through inline Markdown nodes (like Bold or Italics)
        to extract raw text pieces and joins them into a single coherent string.
        """
        pieces = []

        # Only pull content if it is explicitly a TEXT node or a leaf with content
        if node.type == "text" and node.content: #node.node.type == "text" and node.content
            pieces.append(node.content.strip())

        # Recurse into children (STONG, EM, etc. will eventually lead to TEXT nodes)
        for child in node.children:
            # Note: We do NOT check child.content here if it's an INLINE type
            pieces.append(self._extract_clean_text(child))

        return " ".join(filter(None, pieces))



    def _build_native_table_requests(self, raw_content: str, start_index: int, level: int):
        """
        DEPRECATED
        The 'Geometry Teacher.' Converts a raw Markdown table string into 
        a native Google Docs Table. It calculates the complex 'boundary indices' 
        required to place text inside specific table cells.
        """
        
        # 1. Clean and split the markdown into rows/cols
        # We filter out the '---' separator row used in markdown
        lines = [line.strip() for line in raw_content.split('\n') if line.strip()]
        table_data = []
        for line in lines:
            if "---" in line: continue  # Skip the markdown divider
            # Split by pipe and remove empty strings from ends
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if cells:
                table_data.append(cells)

        if not table_data:
            return [], [], 0

        num_rows = len(table_data)
        num_cols = len(table_data[0])

        # 2. Request: Insert the empty Table
        # Note: Level indentation for tables is usually handled by table properties, 
        # but for simplicity, we insert at the provided index.
        all_text_requests = [{
            'insertTable': {
                'rows': num_rows,
                'columns': num_cols,
                'location': {'index': start_index}
            }
        }]

        all_format_requests = []

        # 3. Calculate Cell Indices and Insert Text
        # Indexing Math: 
        # Index start_index is the table start. 
        # start_index + 1 is the first cell.
        # Every cell is followed by a "boundary" index. 
        # To get to the next cell, we add 2.

        current_cell_index = start_index + 1

        for row in table_data:
            for cell_text in row:
                if cell_text:
                    all_text_requests.append({
                        'insertText': {
                            'location': {'index': current_cell_index},
                            'text': cell_text
                        }
                    })
                    # Optional: Bold the first row (Header)
                    if table_data.index(row) == 0:
                        all_format_requests.append({
                            'updateTextStyle': {
                                'range': {
                                    'startIndex': current_cell_index, 
                                    'endIndex': current_cell_index + len(cell_text.encode('utf-16-le')) // 2
                                },
                                'textStyle': {'bold': True},
                                'fields': 'bold'
                            }
                        })

                # Move to the next cell's starting index
                # IMPORTANT: We must account for the text we just inserted
                text_len = len(cell_text.encode('utf-16-le')) // 2
                current_cell_index += text_len + 2 

        # 4. Calculate total offset for the document
        # A table's length in the index system is (cells * 2) + 2 + total_text_len
        total_text_len = sum(len(c.encode('utf-16-le')) // 2 for row in table_data for c in row)
        total_offset = (num_rows * num_cols * 2) + 2 + total_text_len

        return all_text_requests, all_format_requests, total_offset
        

    def __str__(self) -> str:
        """Standard entry point for tree visualization."""
        return self._format_tree(level=0)

    def _format_tree(self, level: int) -> str:
        """
        Generates a readable, indented string of the Gdoc tree, showing 
        node types, nesting depth [D:X], and text snippets for debugging.
        """
        indent = "  " * level
        
        # 1. Handle the Root specially
        if self.type == "root":
            # Added [D:0] for the root
            header = f"<GDOC_ROOT> [D:{level}] (Children: {len(self.children)})"
        else:
            # 2. Prepare metadata flags
            custom_flag = "[CUSTOM]" if getattr(self, 'is_custom_node', False) else ""
            
            # 3. Build the header line with Depth indicator
            # This will show like: [CUSTOM] PARAGRAPH [D:5] (tag='p')
            header = f"{indent}{custom_flag} {self.type.upper()} [D:{level}] (tag='{self.node.tag}')"

        # 4. Extract a content snippet for visibility
        display_text = ""
        if hasattr(self, 'content') and self.content:
            display_text = self.content.strip().replace("\n", " ")
        elif self.node and self.node.content:
            display_text = self.node.content.strip().replace("\n", " ")

        content_snippet = ""
        if display_text:
            snippet = (display_text[:50] + "..") if len(display_text) > 50 else display_text
            content_snippet = f"\n{indent}  | Content: \"{snippet}\""

        # 5. Recurse through children
        children_str = "".join([child._format_tree(level + 1) for child in self.children])

        return f"\n{header}{content_snippet}{children_str}"

   

def text_utf16_len(text:str):
    """
    Helper to calculate string length in UTF-16 code units. 
    Crucial because Google Docs API indices are not 0-indexed bytes or UTF-8 chars.
    """ 
    return len((text).encode("utf-16-le"))//2
