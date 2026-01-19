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
load_dotenv(os.path.join(os.environ.get('LAMBDA_TASK_ROOT', ''), '.env'))


MIN_BLOCK_LEN = 10
SIMILARITY_THRESHOLD=0.97

class EmbedTreeNode(): 
    def __init__(self,node:SyntaxTreeNode,emb_model:OpenAIEmbeddings,parent,is_custom:bool=False):
        
        self.node:SyntaxTreeNode = node
        self.type:str = self.node.type 
        self.emb_model:OpenAIEmbeddings = emb_model
        self.emb = np.zeros(1536)
        self.mean_emb = self.emb
        self.parent = parent
        self.children:list[EmbedTreeNode] = []
        
        self.content = getattr(self.node,'content',"") or ""
        self.block_len = len(self.content.split(" "))  #0 if (self.node.type=="root") else len(self.node.content)
        self.is_custom_node = is_custom
        self.has_custom_node = is_custom
        #self.claimed = False



    '''@classmethod
    def _init_tree(cls,node:SyntaxTreeNode,emb_model:OpenAIEmbeddings,parent)->'EmbedTreeNode':
        #create current node's wrapper object
        curr = cls(node=node,emb_model=emb_model,parent=parent)
        #wrap all its children
        for child in node.children: 
            e_child = cls._init_tree(child,emb_model,curr)
            curr.children.append(e_child)
        #return wrapper object
        return curr
    '''

    @classmethod
    def _init_tree(cls, root_node: SyntaxTreeNode, emb_model: OpenAIEmbeddings) -> 'EmbedTreeNode':
        # 1. Create the actual Root wrapper
        root_wrapper = cls(node=root_node, emb_model=emb_model, parent=None)

        # 2. Stack to track heading hierarchy
        stack: list[tuple[int, 'EmbedTreeNode']] = [(0, root_wrapper)]

        for child in root_node.children:
            current_level = 999 
            if child.type == "heading":
                current_level = int(child.tag[1]) 

            # 3. Pop stack to find the correct parent
            while stack and stack[-1][0] >= current_level:
                stack.pop()

            current_parent = stack[-1][1]

            # 4. Wrap the child
            e_child = cls(node=child, emb_model=emb_model, parent=current_parent)

            # --- NEW LOGIC: Extract Heading Text ---
            if child.type == "heading":
                raw_text = cls._extract_text_recursive(child).strip()
                # Clean out common markdown characters that might be caught in the extraction
                clean_text = raw_text.replace("**", "").replace("__", "").replace("#", "")
                e_child.content = clean_text

            current_parent.children.append(e_child)

            # 5. Maintain the hierarchy
            if child.type == "heading":
                stack.append((current_level, e_child))

            # Handle internal children (bold text in paragraphs, list items, etc.)
            if child.children and child.type != "heading":
                cls._build_internal_children(child, e_child, emb_model)

        return root_wrapper

    @classmethod
    def _extract_text_recursive(cls, node: SyntaxTreeNode) -> str:
        """Gathers text only from leaf nodes to avoid duplication."""
        # If it's a leaf node with content, that's our raw text
        if not node.children:
            return node.content if node.content else ""

        # If it has children, ignore its own 'content' (which usually contains markup)
        # and only collect from the children.
        return "".join(cls._extract_text_recursive(child) for child in node.children)

    @classmethod
    def _build_internal_children(cls, node, wrapper, emb_model):
        for child in node.children:
            e_child = cls(node=child, emb_model=emb_model, parent=wrapper)
            wrapper.children.append(e_child)
            cls._build_internal_children(child, e_child, emb_model)    
    
    @classmethod 
    def _calc_block_len(cls,node): 
        etree:cls = node 
        for child in etree.children: 
            cls._calc_block_len(child)
        all_block_lens = [child.block_len for child in etree.children]
        etree.block_len +=sum(all_block_lens)


    @classmethod
    def _calc_mean_embedding(cls, node): 
        for child in node.children: 
           cls._calc_mean_embedding(child)

        # Collect only non-None, non-zero embeddings from children
        children_embs = [c.mean_emb for c in node.children if c.mean_emb is not None and np.any(c.mean_emb)]

        current_emb = node.emb if (node.emb is not None and np.any(node.emb)) else None

        if children_embs or current_emb is not None:
            all_vecs = children_embs + ([current_emb] if current_emb is not None else [])
            node.mean_emb = np.mean(all_vecs, axis=0)


    @classmethod     
    def _embed_tree_(cls,node): 
        etree:cls = node
        all_content = etree.apply(lambda enode: enode.node.content)
        print(f"List of all content being embedded")
        tree_vectors = etree.emb_model.embed_documents(list(all_content))
        all_enodes = etree.apply(lambda enode: enode)
        for enode,vector in zip(all_enodes,tree_vectors): 
            enode.emb = vector
            enode.mean_emb = enode.emb
   
    @classmethod
    def _insert_custom_before(cls,node,custom_node): 
        if not node.parent or node.type=="root":
            return
        curr = node.parent
        print("Checking if circular loop is found")
        while curr:
            if curr is custom_node:
                print("!!! ABORT: Circular reference detected. Trying to insert a node as its own ancestor.")
                return
            curr = curr.parent
        parent = node.parent 
        # 1. Find where 'node' was in the parent's list
        idx = parent.children.index(node)
        # 2. Setup the custom_node
        custom_node.parent = parent 
        custom_node.children = [node]
        # 3. Update the node to point to its new custom parent
        node.parent = custom_node 
        # 4. Swap node for custom_node in the parent's list at the same index
        parent.children[idx] = custom_node

        custom_node.mean_emb = node.mean_emb


    @classmethod
    def get_full_text(cls, node) -> str:
        """
        Recursively gathers all content from this node and all its children.
        """
        etree:cls = node
        # Start with the current node's content
        texts = []

        current_content = node.content.strip() if node.content else ""
        if current_content:
            texts.append(current_content)

        # Recursively gather content from children
        for child in node.children:
            child_text = cls.get_full_text(child)
            if child_text:
                texts.append(child_text)

        return "\n".join(texts)
     
     
    

    '''
    Heading:
        "id": match.id,
        "heading": match.metadata.get("heading"),
        "position": match.metadata.get("position"),
        "embedding": match.values

    headings:list[Heading]
    '''     


    def insert_custom_headings(self,headings):

        #Makes heading:node pairs for nodes most similar to headings
        heading_vecs = [heading['embedding'] for heading in headings if len(heading['embedding'])==1536]
        heading_vecs = np.array(heading_vecs)
        
        def check_node_against_headings(node)->tuple[Any,Any]:
            if heading_vecs.size==0: 
                return
            if node.type=="root":
                return
            if node.block_len<MIN_BLOCK_LEN:
                return
            most_similar_idx,similarity = find_closest_cosine_sim(node.mean_emb,heading_vecs)
            if similarity<SIMILARITY_THRESHOLD:
                return
            return (headings[most_similar_idx],node)

        print(f"Fetched Headings len:{len(headings)}")
        heading_node_pairs:list[tuple[Any,node]] = self.apply(check_node_against_headings) 
        heading_node_pairs = [pair for pair in heading_node_pairs if (pair)] 
        node_only_list = [node for (_,node) in heading_node_pairs]
        #print(f"Heading node pairs:{heading_node_pairs}")
        def parents_exist_in_list(node)->bool:
            curr = node.parent
            while curr: 
                if curr in node_only_list:
                    return True
                curr = curr.parent
            return False

        pruned_node_list = []
        for i,node in enumerate(node_only_list): 
            if parents_exist_in_list(node):
                continue
            pruned_node_list.append(heading_node_pairs[i])

        #kinda goofy, but loosing reference will hopefully make python garbage
        #collector pick it up
        heading_node_pairs:list[tuple[Any,node]] = pruned_node_list
        all_final_custom_nodes = []
        mdit = MarkdownIt()
        #Inserting custom heading into tree
        custom_nodes:EmbedTreeNode = []
        for heading,node in heading_node_pairs: 
            '''
            md = mdit.parse(f"#{heading['heading']}")             
            cus_node = EmbedTreeNode(SyntaxTreeNode(md),self.emb_model,parent=None,is_custom=True)
            '''
            md = mdit.parse(f"#{heading['heading']}")
            syntax_tree = SyntaxTreeNode(md)
    
            # Extract the heading node, not the root
            if syntax_tree.children and len(syntax_tree.children) > 0:
                heading_node = syntax_tree.children[0]
            else:
                heading_node = syntax_tree
    
            cus_node = EmbedTreeNode(heading_node, self.emb_model, parent=None, is_custom=True)
            if node.is_custom_node or (node.parent and node.parent.is_custom_node):
                continue
            cus_node.content = heading['heading']
            cus_node.is_custom_node = True 
            cus_node.has_custom_node = True
            node.claimed = True
            EmbedTreeNode._insert_custom_before(node, cus_node)
            custom_nodes.append(cus_node)
            all_final_custom_nodes.append(cus_node)
        
        #Propogate has_custom_node flag upwards 
        for node in custom_nodes: 
            curr = node 
            while curr: 
                curr.custom_node_present = True 
                curr = curr.parent

        #Find straggler branches 
        def find_straggle_branches(node) -> Generator[Any, None, None]:
            if node.block_len < MIN_BLOCK_LEN:
                return 

            # CRITICAL: If this node is a custom heading, STOP recursing. 
            # Do not look for stragglers inside a branch we already defined.
            if getattr(node, 'is_custom_node', False):
                return

            # If it's the root or has a custom node somewhere in its subtree, 
            # we look at its children.
            if node.node.type == "root" or getattr(node, 'has_custom_node', False): 
                for child in node.children:
                    yield from find_straggle_branches(child)
            else:
                # If it's not custom and not claimed, this is a straggler
                if not getattr(node, 'claimed', False):
                    yield node
                
            
            
        #Add or redefine straggler branches to be a custom node(set is_custom_node=True) 
        straggler_branches = [node for node in find_straggle_branches(self) if(node)]#self.apply(lambda node: if (not node.is_custom_node and node.block_len>=MIN_BLOCK_LEN) node)    
        new_heading_needed:list[EmbedTreeNode] = []
        for branch in straggler_branches: 
            #handles redefines
            if branch.type == "heading": 
                branch.is_custom_node = True
                branch.has_custom_node = True 
                all_final_custom_nodes.append(branch)
                continue
            new_heading_needed.append(branch)

        #limit length of string being sent later    
        needed_headings = [EmbedTreeNode.get_full_text(node).split(".")[0] for node in new_heading_needed]  
        generated_headings = generate_headings_from_sentences(needed_headings)    
        generated_nodes = []  
        for i, node in enumerate(new_heading_needed):
            print("Heading generated") 
            md = mdit.parse(f"#{generated_headings[i]}")
            syntax_tree = SyntaxTreeNode(md)

            # The parsed tree structure is: root -> heading
            # So we need to get the first child (the actual heading node)
            if syntax_tree.children and len(syntax_tree.children) > 0:
                heading_node = syntax_tree.children[0]  # Get the actual heading, not root
            else:
                # Fallback: create a simple heading node manually
                heading_node = syntax_tree

            cus_node = EmbedTreeNode(heading_node, self.emb_model, parent=None, is_custom=True)
            cus_node.content = generated_headings[i]
            cus_node.is_custom_node = True 
            cus_node.has_custom_node = True
            node.claimed = True
            EmbedTreeNode._insert_custom_before(node, cus_node)
            generated_nodes.append(cus_node)
            #all_final_custom_nodes.append(cus_node)
        all_final_custom_nodes.extend(generated_nodes)
        return (generated_nodes,all_final_custom_nodes)



    def display_custom_headings(self, level: int = 0) -> None:
        """
        Recursively finds and prints all nodes marked as custom headings.
        """
        # If the current node is a custom node, print it with indentation
        if getattr(self, 'is_custom_node', False):
            indent = "  " * level
            # Extract content; if it's a SyntaxTreeNode, we look at its content attribute
            content = self.content.strip() if self.content else "Untitled Custom Heading"
            print(f"{indent} [CUSTOM HEADING] -> {content}")

            # We increment the level for children only if we found a heading, 
            # to keep the visual hierarchy of the headings themselves.
            new_level = level + 1
        else:
            # If this isn't a custom node, children still might be, 
            # so we keep the current level.
            new_level = level

        for child in self.children:
            child.display_custom_headings(new_level)        
            

    def apply(self,func: Callable[["EmbedTreeNode"],Any])->Generator[Any,None,None]:
        if self.node.type!="root":
            yield func(self)#yeild the result of the func on current node
        for child in self.children: 
            yield from child.apply(func)#recursively yield from da children

     

    def __str__(self) -> str:
        return self._format_tree(level=0)

    def _format_tree(self, level: int) -> str:
        indent = "  " * level

        # --- 1. ROOT SPECIFIC LOGIC ---
        if self.node.type == "root":
            # Root is a container, we usually just want to see it and its children
            children_str = "".join([child._format_tree(level + 1) for child in self.children])
            return f"\n{indent}<ROOT> (Total Children: {len(self.children)}){children_str}"

        # --- 2. STANDARD NODE LOGIC ---
        # Identity & Flags
        is_custom = getattr(self, 'is_custom_node', False)
        has_custom = getattr(self, 'has_custom_node', False)

        # Color-like markers for terminal readability
        type_label = f" {self.node.type.upper()} "
        flags = f"{'[CUS]' if is_custom else ''}{'[+PATH]' if has_custom else ''}"
        node_id = f"ID:{id(self) % 10000}" # Helps track if the same object exists in two places

        # Build Header Line
        header = f"{indent} {flags} {type_label} ({node_id}) tag='{self.node.tag}' [Len: {self.block_len}] [Mean Emb:{self.mean_emb[:3]}]"

        # --- 3. CONTENT TRANSPARENCY ---
        # We check self.content (custom heading text) or node.content (original markdown text)
        display_text = ""
        if is_custom and self.content:
            display_text = f"CUSTOM_HEADER: {self.content}"
        elif self.node.content.strip():
            clean_content = self.node.content.strip().replace('\n', ' ')
            # Then put it in the f-string
            display_text = f"RAW_CONTENT: {clean_content}"


        content_snippet = ""
        if display_text:
            content_snippet = f"\n{indent}    | {display_text[:60]}..."

        # --- 4. RECURSION ---
        children_str = "".join([child._format_tree(level + 1) for child in self.children])

        return f"\n{header}{content_snippet}{children_str}"

    




class GdocTreeNode():
    def __init__(self,enode:EmbedTreeNode):
        '''
        self.enode = enode
        self.node:SyntaxTreeNode = self.enode.node
        self.type:str = self.node.type
        self.content:str = None if self.type=="root" else enode.content
        self.children:list[GdocTreeNode] = []
        self.text_requests = []
        self.format_requests = []
        #self.level = -1
        self.is_custom_node = enode.is_custom_node
        '''
        self.enode = enode
        self.node = enode.node
        self.type = enode.type
        # Ensure we grab the 'content' string set during insert_custom_headings
        self.content = enode.content 
        self.children = []
        self.is_custom_node = enode.is_custom_node
    @classmethod
    def _init_tree(cls,etree:EmbedTreeNode): 
        #create current node's wrapper object
        curr = cls(enode=etree)
        #wrap all its children
        for child in etree.children: 
            gdoc_child = cls._init_tree(child)
            curr.children.append(gdoc_child)
        #return wrapper object
        return curr
   
    def generate_custom_branch_requests(self, startIndex: int, level: int = 0): 
        if not self.is_custom_node: 
            return None, None, None
        all_text_requests = []
        all_format_requests = []
        print(f"Custom branch content:{self.content}")
        total_offset = text_utf16_len(text=self.content+":\n\n")

        # 1. Process all children safely (even if 0 or many)
        for child in self.children:
            # Note: level+1 keeps the indentation hierarchy correct
            child_text, child_format, child_len = child.generate_formatted_requests(startIndex + total_offset, level + 1)
            all_text_requests.extend(child_text)
            all_format_requests.extend(child_format)
            total_offset += child_len

        # 2. Define the Named Range covering the total span of all children
        if self.content:
            self.format_requests = [
                {
                    'deleteNamedRange': {
                        'name': self.content
                    }
                },
                {
                    'createNamedRange': {
                        'name': self.content,
                        'range': {
                            'startIndex': startIndex,
                            # If there is no text, it covers 0 distance
                            'endIndex': startIndex + total_offset
                        }
                    }
                } 
            ]
            all_format_requests.extend(self.format_requests)

        return all_text_requests, all_format_requests, total_offset
    
    def _dispatch_node_type(self, index: int, level: int, context: dict = None) -> tuple[list[dict], list[dict], int]:
        node_type = self.node.type
        context = context or {}

        if node_type == "paragraph":
            # Paragraph is now the leaf renderer
            return self._format_paragraph_as_leaf(index, level, context)

        elif not self.is_custom_node and node_type == "heading":
            return self._format_heading(index, level)

        elif node_type in ["bullet_list", "ordered_list"]:
            # Lists don't insert text themselves, they just pass context to children
            return [], [], 0 

        elif node_type == "list_item":
            # Determine list type from parent or node attribute
            list_type = context.get("list_type", "BULLET") 
            return [], [], 0 # Handled by the paragraph child via context

        return [], [], 0

    def generate_formatted_requests(self, start_index: int, level: int = 0, context: dict = None) -> tuple[list[dict], list[dict], int]:
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
        if self.node.type not in ["paragraph", "text"]:
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
         # Use self.enode.content (where custom headings store text) or self.content
        content = getattr(self.enode, 'content', self.content) or "Untitled"
        text = content.strip() + "\n"
        text_len = len(text.encode("utf-16-le")) // 2

        # HEADING_1, HEADING_2, etc.
        heading_type = f"HEADING_{min(level + 1, 6)}"

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
        Processes the paragraph by gathering internal text nodes and applying tabs.
        """
        # 1. Gather text from children, ignoring INLINE containers but keeping TEXT content
        raw_content = self._extract_clean_text(self)

        # Check if this paragraph contains the markdown table pattern
        if "|" in raw_content and "---" in raw_content:
            return [],[],0#self._build_native_table_requests(raw_content, index, level)
        # 2. Apply level-based indentation with tabs and add newline
        tab_prefix = "\t" * level
        final_text = f"{tab_prefix}{raw_content}\n"

        # Calculate length (Google Docs uses UTF-16)
        text_len = len(final_text.encode("utf-16-le")) // 2
        
        # 3. Text Insertion Request
        text_requests = [{
            'insertText': {
                'location': {'index': index},
                'text': final_text
            }
        }]

        # 4. Block Formatting (Bullets vs Standard)
        format_requests = []
        if context.get("list_mode"):
            format_requests.append({
                'createParagraphBullets': {
                    'range': {'startIndex': index, 'endIndex': index + text_len},
                    'bulletPreset': 'BULLET_DISC_CIRCLE_SQUARE' if context["list_mode"] == "BULLET" else 'NUMBERED_DECIMAL_ALPHA_ROMAN'
                }
            })
        else:
            # Standard paragraph styling (spacing, etc.)
            format_requests.append({
                'updateParagraphStyle': {
                    'range': {'startIndex': index, 'endIndex': index + text_len},
                    'paragraphStyle': {
                        'lineSpacing': 115.0,
                        'spaceAbove': {'magnitude': 10, 'unit': 'PT'}
                    },
                    'fields': 'lineSpacing,spaceAbove'
                }
            })

        return text_requests, format_requests, text_len

    def _extract_clean_text(self, node) -> str:
        """
        Recursively finds TEXT nodes. 
        Ignores the 'content' attribute of INLINE nodes to prevent duplicates.
        """
        pieces = []

        # Only pull content if it is explicitly a TEXT node or a leaf with content
        if node.node.type == "text" and node.content:
            pieces.append(node.content.strip())

        # Recurse into children (STONG, EM, etc. will eventually lead to TEXT nodes)
        for child in node.children:
            # Note: We do NOT check child.content here if it's an INLINE type
            pieces.append(self._extract_clean_text(child))

        return " ".join(filter(None, pieces))

    def _build_native_table_requests(self, raw_content: str, start_index: int, level: int):
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
        """Entry point for string representation."""
        return self._format_tree(level=0)

    def _format_tree(self, level: int) -> str:
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
    return len((text).encode("utf-16-le"))//2

#Base Functions
def generate_headings_from_sentences(sentences: list[str]) -> list[str]:
    """
    Generate clean, short headings for a list of sentences using batching.
    Returns a list of headings in the same order as input.
    """
    # 1. Validation and Setup
    if not sentences:
        return []

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.1,
        max_tokens=20
    )

    # 2. Prepare Prompts
    prompts = []
    for sentence in sentences:
        # Fallback check for individual invalid items
        if not sentence or not isinstance(sentence, str):
            prompts.append("Generate a fallback heading: 'Basic'")
        else:
            prompts.append(
                "Create a concise heading (4–7 words maximum) based ONLY on the following "
                "sentence. The heading must:\n"
                "- be title case\n"
                "- remove unnecessary words\n"
                "- not include punctuation\n"
                "- sound like a real document section heading\n\n"
                f"Sentence: \"{sentence}\"\n\n"
                "Heading:"
            )

    # 3. Batch Invoke
    try:
        # .batch() runs requests in parallel (default 5-10 at a time)
        responses = llm.batch(prompts,return_exceptions=True)
        
        # 4. Parse results
        headings = []
        for res in responses:
            if isinstance(res, Exception):
                print(f"[ERROR] Individual prompt failed: {res}")
                headings.append("Basic")
            else:
                text = res.content.strip() if res.content else "Basic"
                headings.append(text)
        return headings

    except Exception as e:
        sample = f"'{sentences[0][:40]}...'" if sentences else "None"
        print(f"\n[WARN] Batch LLM heading generation failed!")
        print(f" ├─ Error Type: {type(e).__name__}")
        print(f" ├─ Batch Size: {len(sentences)} items")
        print(f" ├─ First Item Preview: {sample}")
        print(f" └─ Error Detail: {e}")
        traceback.print_exc()
        return ["Basic"] * len(sentences)




def find_closest_cosine_sim(query_vec,list_vecs)->tuple[int,float]:
    # Force list_vecs to be 2D (rows, features)
    if list_vecs.ndim == 1:
        list_vecs = list_vecs[np.newaxis, :]
    query_norm = query_vec / np.linalg.norm(query_vec)
    list_norms = list_vecs / np.linalg.norm(list_vecs,axis=1)[:,np.newaxis]
    similarities = np.dot(list_norms,query_norm)
    closest_idx = np.argmax(similarities)
    return closest_idx,similarities[closest_idx]

def pdf_to_syntree(stream:BytesIO) -> SyntaxTreeNode:
    doc = pymupdf.open(stream=stream)
    markdown = pymupdf4llm.to_markdown(doc)
    mdit = MarkdownIt()
    md = mdit.parse(markdown)
    return SyntaxTreeNode(md)

def stree_to_etree(stree:SyntaxTreeNode,emb_model:OpenAIEmbeddings):
    print("Building Semantic Tree...")
    root = EmbedTreeNode._init_tree(root_node=stree, emb_model=emb_model)
    EmbedTreeNode._embed_tree_(root)
    EmbedTreeNode._calc_mean_embedding(root)
    EmbedTreeNode._calc_block_len(root)
    return root

def main():

    with open("files/Chloroplast 2.pdf","rb") as f:
        pdf_bytes = f.read()
    strm = BytesIO(pdf_bytes)
    synt_tree = pdf_to_syntree(stream=strm)

    emb_model = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY")) 
    heading_gen_model = llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.1,
                max_tokens=20  # keep it short
            )
    pinecone_api_key = os.environ.get("PINECONE_API_KEY")
    db = VectorDBManager(pc=Pinecone(pinecone_api_key))
    db.initVectorStore(index_name="sdtest1", embedding=OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY")))          
    #print(pdf_to_stree(stream=strm).pretty())
    start = time.perf_counter()
    root = EmbedTreeNode._init_tree(root_node=synt_tree,emb_model=emb_model)
    EmbedTreeNode._embed_tree_(root)
    EmbedTreeNode._calc_mean_embedding(root)
    EmbedTreeNode._calc_block_len(root)
    headings = db.get_all_headings_for_doc(course_id="prof-1302",superdoc_id="1VLXyc4FDmf0kENOa__O-70ANrKUsxcAUV9wKDSh-X9A")
    new_headings = root.insert_custom_headings(headings=headings)
    root.display_custom_headings()
    end = time.perf_counter() 
    print(f"Time:{(end-start):.2f}")
    print(root)                
                

if __name__ == "__main__":
    main()





