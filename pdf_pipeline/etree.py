from markdown_it import MarkdownIt  
from markdown_it.tree import SyntaxTreeNode

from io import BytesIO
import pymupdf.layout
import pymupdf4llm
import pymupdf

import numpy as np
from langchain_openai import OpenAIEmbeddings,ChatOpenAI

from pydantic import BaseModel
from typing import List, Callable, Any, Generator, Iterator, Self ,TypeVar
from itertools import tee



from dotenv import load_dotenv
import os
import time
import traceback


MIN_BLOCK_LEN = 10
SIMILARITY_THRESHOLD=0.97

class EmbedTreeNode(): 
    def __init__(self,node:SyntaxTreeNode,emb_model:OpenAIEmbeddings,parent,is_custom:bool=False):
        
        self.node:SyntaxTreeNode = node
        self.type:str = self.node.type 
        self.emb_model:OpenAIEmbeddings = emb_model
        self.emb = None
        self.parent = parent
        self.children:list[EmbedTreeNode] = []
        
        self.has_embedding = False
        self.is_pruned = False
        self.needs_gen_heading = False

        self.content = getattr(self.node,'content',"") or ""
        self.block_len = len(self.content.split(" "))  #0 if (self.node.type=="root") else len(self.node.content)
        self.is_custom_node = is_custom
        self.has_custom_node = is_custom
        #self.claimed = False

    def __hash__(self): 
        return id(self)
    
    def __eq__(self,other): 
        return self is other

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
    def _embed_tree_(cls,node): 
        heading_nodes = [n for n in node.apply(lambda x: x) if n.type == 'heading']
        
        if not heading_nodes:
            return
        heading_nodes_content = [h_node.content for h_node in heading_nodes]
        heading_node_vectors = node.emb_model.embed_documents(heading_nodes_content)

        for h_node,h_vector in zip(heading_nodes,heading_node_vectors):
            h_node.has_embedding = True 
            h_node.emb = h_vector
            

            
   
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


    @classmethod 
    def _insert_batch_before(cls,batch_node):
        first_child = batch_node.children[0]
        parent = child.parent
        if not parent or first_child.type=='root': 
            return

        #If we want to retain our place the hierarchy, we need to keep track of the idx of the batch
        # and reinsert our custom batch node at that idx.
        idx = parent.children.index

        for batch_child in batch_node.children:
            batch_child.parent = batch_node 
            parent.children.remove(batch_child)

        batch_node.parent = parent
        parent.children.insert(idx,batch_node)

    @classmethod 
    def remove_branch(cls,node): 
        if not node.parent or node.type=="root": 
            return  
        parent = node.parent
        #remove the child
        parent.children.remove(node)
        node.parent = None




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

        insert_custom_heading helper functions

    '''   

    class DB_Heading(BaseModel): 
        id: str 
        heading: Optional[str]
        position: Optional[int]
        embedding: List[float]
         


    def match_headings(self,db_headings:list[DB_Heading],pdf_heading_nodes) -> dict[Self,str]:
        
        heading_vecs = np.array([h.embedding for h in db_headings if len(h.embedding) == 1536])
        
        def check_node_against_headings(node)->tuple[str,Self]:
            if heading_vecs.size==0: 
                return
            if node.type=="root":
                return
            if node.block_len<MIN_BLOCK_LEN:
                return
            if not node.has_embedding: 
                return
            most_similar_idx,similarity = find_closest_cosine_sim(node.mean_emb,heading_vecs)
            if similarity<SIMILARITY_THRESHOLD:
                return
            return (db_headings[most_similar_idx].heading,node)

        print(f"Fetched Headings len:{len(db_headings)}")
        #heading_node_pairs:list[tuple[str,Self]] = list(self.apply(check_node_against_headings)) 
        node_heading_pairs = {
            node: heading 
            for result in self.apply(check_node_against_headings)
            if result is not None 
            for heading, node in [result] # unpacking trick for a singular tuple within the comprehension
        }
        return node_heading_pairs




    def remove_different_heading_child_branches(self,parent_heading:str,node_heading_pairs:dict[Self,str]):
        if not parent_heading:
            parent_heading = node_heading_pairs.get(self)
            if not parent_heading:
                # If this is the root, just recurse into children without a lock yet
                if self.type == "root":
                    for child in list(self.children):
                        child.remove_different_heading_child_branches(None, node_heading_pairs)
                    return
                else:
                    raise Exception('Can remove different heading child branches from headingless node')
        
        for child in list(self.children): #iterate over a copy of self.children, don't have to deal w/index shifts 
            matched_heading = node_heading_pairs.get(child)
            if matched_heading: 
                if not (parent_heading == matched_heading): 
                    child.is_pruned = True
                    type(self).remove_branch(child)
                    continue
                else: 
                    child.is_custom_node = False
            child.remove_different_heading_child_branches(parent_heading=parent_heading,node_heading_pairs=node_heading_pairs)




    def find_straggle_branches(node) -> Generator[list[EmbedTreeNode], None, None]:
            if node.block_len < MIN_BLOCK_LEN:
                return 

            if getattr(node, 'is_custom_node', False):
                return

            # If this path has custom nodes, we must check children
            if node.node.type == "root" or getattr(node, 'has_custom_node', False):
                current_group = []

                for child in node.children:
                    # If child is a 'clean' branch (no custom nodes), collect it
                    if not getattr(child, 'has_custom_node', False) and not getattr(child, 'is_custom_node', False):
                        if child.block_len >= MIN_BLOCK_LEN:
                            current_group.append(child)
                    else:
                        # We hit a 'custom' branch, so flush the current group first
                        if current_group:
                            yield current_group
                            current_group = []
                        # Then recurse into the branch that HAS custom nodes
                        yield from find_straggle_branches(child)

                # Flush any remaining group at the end of siblings
                if current_group:
                    yield current_group
            else:
                # This whole branch is an orphan
                yield [node]  





    def insert_custom_headings(self,headings:list[DB_Heading]):


        #Very important, maintain references to pdf_heading_nodes, branches will get pruned
        pdf_heading_nodes = [node for node in self.apply(lambda enode: enode.has_embedding) if node]
        #Get straggler branches that come in as a list[list[EmbedTreeNode]], these lists of nodes represent branches that don't have a prent heading 
        straggler_batches = [batch for batch in find_straggle_branches(self) if(batch)]
        #Get the filtered content of each batch(after assembling all the batch text get the first 30, the middle 30 and the last 30 characters)
        straggler_batch_content = []
        for batch in straggler_batches: 
            batch_content = ''
            for batch_node in batch: 
                batch_content+=batch_node.get_full_text()
            straggler_batch_content.append(batch_content)
        
        #filtered batch content
        straggler_batch_sampled_content = [get_sampled_text(content) for content in straggler_batch_content]
        

        #Make custom batch nodes
        batch_nodes = []
        for batch, heading in zip(straggler_batches,straggler_batch_sampled_content): 
            print("New Batch Node Made") 
            md = mdit.parse(f"#{heading}")
            syntax_tree = SyntaxTreeNode(md)

            # The parsed tree structure is: root -> heading
            # So we need to get the first child (the actual heading node)
            if syntax_tree.children and len(syntax_tree.children) > 0:
                heading_node = syntax_tree.children[0]  # Get the actual heading, not root
            else:
                # Fallback: create a simple heading node manually
                heading_node = syntax_tree

            cus_node = EmbedTreeNode(heading_node, self.emb_model, parent=None, is_custom=True)
            cus_node.content = heading
            cus_node.is_custom_node = True 
            cus_node.has_custom_node = True
            cus_node.children = batch

            type(self)._insert_batch_before(cus_node)

            batch_nodes.append(cus_node)

        straggler_batch_vectors = self.emb_model.embed_documents(straggler_batch_sampled_content)
        
        #Embedding the sampled content from batches
        for h_node,h_vector in zip(batch_nodes,straggler_batch_vectors):
            h_node.has_embedding = True 
            h_node.emb = h_vector    

        node_heading_pairs = self.match_headings(db_headings=headings)
        self.remove_different_heading_child_branches(parent_heading=None,node_heading_pairs=node_heading_pairs)
        

        










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

#Base Functions


def get_sampled_text(nodes: list[EmbedTreeNode]) -> str:
    # 1. Join all text from the group of nodes
    full_text = "\n".join([EmbedTreeNode.get_full_text(n) for n in nodes])
    
    if len(full_text) <= 100:
        return full_text
        
    # 2. Extract the 3-point sample
    start = full_text[:30]
    mid_idx = len(full_text) // 2
    middle = full_text[mid_idx - 15 : mid_idx + 15]
    end = full_text[-30:]
    
    return f"{start}...{middle}...{end}"





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