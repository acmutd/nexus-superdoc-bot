from markdown_it import MarkdownIt  
from markdown_it.tree import SyntaxTreeNode

from io import BytesIO
import pymupdf.layout
import pymupdf4llm
import pymupdf
from markdown_it import MarkdownIt  



import numpy as np
from langchain_openai import OpenAIEmbeddings,ChatOpenAI

from pydantic import BaseModel
from typing import List, Callable, Any, Generator, Iterator, Self ,TypeVar, Optional
from itertools import tee



from dotenv import load_dotenv
import os
import time
import traceback


MIN_BLOCK_LEN = 2
SIMILARITY_THRESHOLD=0.97

class EmbedTreeNode(): 
    def __init__(self,node:SyntaxTreeNode,emb_model:OpenAIEmbeddings,parent,is_custom:bool=False):
        
        self.node:SyntaxTreeNode = node
        self.type:str = self.node.type 
        self.emb_model:OpenAIEmbeddings = emb_model
        self.emb = None
        self.mean_emb = self.emb
        self.parent = parent
        self.children:list[EmbedTreeNode] = []
        
        self.has_embedding = False
        self.is_pruned = False

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
        parent = first_child.parent
        if not parent or first_child.type=='root': 
            return

        #If we want to retain our place the hierarchy, we need to keep track of the idx of the batch
        # and reinsert our custom batch node at that idx.
        idx = parent.children.index(first_child)

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


    @staticmethod
    def rows_to_headings(rows: list[dict]) -> list["EmbedTreeNode.DB_Heading"]:
        """Converts raw database dictionaries into DB_Heading Pydantic objects."""
        headings = []
        for row in rows:
            try:
                # This maps dict keys to Pydantic attributes automatically
                headings.append(EmbedTreeNode.DB_Heading(**row))
            except Exception as e:
                print(f"[WARN] Skipping malformed DB row: {row}. Error: {e}")
        return headings


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

        reconciliation helper functions

    '''   

    class DB_Heading(BaseModel): 
        id: str 
        heading: Optional[str]
        position: Optional[int]
        embedding: List[float]
         


    def match_headings(self,db_headings:list[DB_Heading]) -> dict[Self,str]:
        
        heading_vecs = np.array([h.embedding for h in db_headings if len(h.embedding) == 1536])
        
        def check_node_against_headings(node)->tuple[str,Self]:
            if heading_vecs.size==0: 
                return
            if node.type=="root":
                return
            if node.block_len<MIN_BLOCK_LEN:
                return
            if not node.has_embedding or node.emb is None: 
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
        current_match = node_heading_pairs.get(self)
    
        if current_match:
            active_heading = current_match
            self.is_custom_node = False # It's a verified match, no longer 'custom'
        else:
            # If no match, inherit the heading from above
            active_heading = parent_heading
        
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

    def mark_structural_mismatch(self, target_heading: str, node_heading_pairs: dict):
        """
        Marks nodes that don't match the database heading label.
        """
        for child in self.children:
            matched_heading = node_heading_pairs.get(child)

            # If the child has a label and it doesn't match the parent's label, mark it
            if matched_heading and target_heading and (matched_heading != target_heading):
                child.is_pruned = True
                # We don't recurse into pruned branches
            else:
                # Continue checking deeper
                child.mark_structural_mismatch(target_heading, node_heading_pairs)

    def mark_semantic_mismatch(self, anchor_vector: np.ndarray, threshold: float = 0.8):
        """
        Marks nodes that stray too far from the anchor vector's meaning.
        """
        if anchor_vector is None:
            return

        for child in self.children:
            is_relevant = True
            if child.mean_emb is not None:
                norm_anchor = np.linalg.norm(anchor_vector)
                norm_child = np.linalg.norm(child.mean_emb)

                if norm_anchor > 0 and norm_child > 0:
                    similarity = np.dot(anchor_vector, child.mean_emb) / (norm_anchor * norm_child)
                    if similarity < threshold:
                        is_relevant = False

            if not is_relevant:
                child.is_pruned = True
            else:
                child.mark_semantic_mismatch(anchor_vector, threshold)


    def execute_pruning(self):
        """
        Physically removes nodes marked as is_pruned and yields them.
        """
        for child in list(self.children):
            if child.is_pruned:
                # 1. Remove from the parent's list
                self.children.remove(child)
                # 2. Break the link to parent
                child.parent = None
                # 3. Yield the whole pruned branch back to the caller
                yield child
            else:
                # 4. Recurse and yield results from deeper levels
                yield from child.execute_pruning()


    @staticmethod
    def find_straggler_branches(node) -> Generator[list['EmbedTreeNode'], None, None]:
        # 1. Immediate exit for tiny nodes
        if node.block_len < MIN_BLOCK_LEN:
            return 
    
        # 2. Boundary Check: If this node is already "Settled", don't batch it.
        # We also treat HEADING types as boundaries to prevent nesting them.
        is_boundary = (
            getattr(node, 'is_custom_node', False) or 
            getattr(node, 'has_embedding', False) or 
            node.type == 'heading'
        )
    
        if is_boundary and node.node.type != "root":
            # This node is an "Anchor." We don't include it in a straggler batch,
            # but we MUST check its children for orphans hidden underneath it.
            for child in node.children:
                yield from EmbedTreeNode.find_straggler_branches(child)
            return
    
        # 3. Path Traversal: If we are at root or a branch that contains Anchors
        if node.node.type == "root" or getattr(node, 'has_custom_node', False):
            current_group = []
    
            for child in node.children:
                # A child is "collectible" only if it's NOT a boundary 
                # and doesn't contain boundaries deeper down.
                child_is_boundary = (
                    getattr(child, 'is_custom_node', False) or 
                    getattr(child, 'has_embedding', False) or 
                    child.type == 'heading' or
                    getattr(child, 'has_custom_node', False)
                )
    
                if not child_is_boundary:
                    if child.block_len >= MIN_BLOCK_LEN:
                        current_group.append(child)
                else:
                    # We hit a boundary! Flush what we have so far.
                    if current_group:
                        yield current_group
                        current_group = []
                    
                    # Now recurse into that boundary node to find stragglers inside/after
                    yield from EmbedTreeNode.find_straggler_branches(child)
    
            # Final flush for the end of the sibling list
            if current_group:
                yield current_group
        else:
            # 4. Pure Orphan: This node and its entire subtree are "Clean"
            yield [node]





    def reconcile_structure(self,headings:list[DB_Heading]):
        mdit = MarkdownIt()
        headings = type(self).rows_to_headings(headings)
        #Very important, maintain references to pdf_heading_nodes, branches will get pruned
        #pdf_heading_nodes = [node for node in self.apply(lambda enode: enode) if node.has_embedding]
        #Get straggler branches that come in as a list[list[EmbedTreeNode]], these lists of nodes represent branches that don't have a prent heading 
        straggler_batches = [batch for batch in self.find_straggler_branches(self) if(batch)]
        #Get the filtered content of each batch(after assembling all the batch text get the first 30, the middle 30 and the last 30 characters)
        straggler_batch_sampled_content = [get_sampled_text(batch) for batch in straggler_batches]
        generated_headings = generate_headings_from_sentences(straggler_batch_sampled_content)

        #Make custom batch nodes
        batch_nodes = []
        for batch, heading in zip(straggler_batches,generated_headings): 
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


            for node in batch: 
                node.parent = cus_node

            type(self)._insert_batch_before(cus_node)

            batch_nodes.append(cus_node)


        straggler_batch_vectors = self.emb_model.embed_documents(generated_headings)
        
        #Embedding the sampled content from batches
        for h_node,h_vector in zip(batch_nodes,straggler_batch_vectors):
            h_node.has_embedding = True 
            h_node.emb = np.array(h_vector)    

        type(self)._calc_mean_embedding(self)
        node_heading_pairs = self.match_headings(db_headings=headings)
        #self.remove_different_heading_child_branches(parent_heading=None,node_heading_pairs=node_heading_pairs)
        
        for child in self.children: 
            target_heading = node_heading_pairs.get(child)

            if target_heading: 
                child.mark_structural_mismatch(target_heading=target_heading,node_heading_pairs=node_heading_pairs)
            if child.is_custom_node and child.emb is not None: 
                child.mark_semantic_mismatch(anchor_vector=child.emb)

            child.is_custom_node = True
        print(self)

        pruned_nodes = list(self.execute_pruning())
        
        print(f"\n\n{"INSANITY"}\n\n")

        print(self)



        main_tree_branches = [node for node in self.apply(lambda n: n) if getattr(node, 'is_custom_node', False)]
        
        all_cust_nodes = main_tree_branches + pruned_nodes
        
        print(f"\n\nAll Pruned Nodes:{pruned_nodes}\n\n")

        print(f"\n\nAll Custom Nodes:{all_cust_nodes}\n\n")

        all_matched_nodes = set(node_heading_pairs.keys())

        print(f"\n\nAll Matched Nodes:{all_matched_nodes}\n\n")

        new_cust_nodes = [n for n in all_cust_nodes if n not in all_matched_nodes]
        
        return new_cust_nodes,all_cust_nodes









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
            children_str = "".join([child._format_tree(level + 1) for child in self.children])
            return f"\n{indent}<ROOT> (Total Children: {len(self.children)}){children_str}"

        # --- 2. IDENTITY & FLAGS ---
        is_custom = getattr(self, 'is_custom_node', False)
        has_custom = getattr(self, 'has_custom_node', False)
        is_pruned = getattr(self, 'is_pruned', False)
        has_emb = getattr(self, 'has_embedding', False)
        
        flags = []
        if is_custom: flags.append("CUS")
        if has_custom: flags.append("+PATH")
        if is_pruned: flags.append("PRUNED")
        if has_emb: flags.append("ANCHOR")
        
        flag_str = "".join([f"[{f}]" for f in flags])
        type_label = f"<{self.node.type.upper()}>"
        node_id = f"ID:{id(self) % 10000}"

        # --- 3. EMBEDDING PREVIEW (First 5 elements) ---
        emb_preview = "None"
        if self.mean_emb is not None:
            # Handle both list and numpy array types safely
            vals = self.mean_emb[:5]
            emb_preview = "[" + ", ".join([f"{v:.3f}" for v in vals]) + "...]"

        # --- 4. ANCHOR CONTENT HIGHLIGHTING ---
        # If this is an anchor, we want to see exactly what text the embedding represents
        anchor_text_display = ""
        if has_emb:
            anchor_text_display = f"\n{indent}    >> ANCHOR TEXT: {self.content.strip()[:100]}"

        # --- 5. BUILD HEADER ---
        header = f"{indent} {flag_str:25} {type_label:12} ({node_id}) [Len: {self.block_len}]"
        emb_line = f"{indent}    └─ MeanEmb: {emb_preview}"

        # --- 6. GENERAL CONTENT SNIPPET ---
        display_text = ""
        if is_custom and self.content:
            display_text = f"CUSTOM_HEADER: {self.content}"
        elif self.node.content and self.node.content.strip():
            # Clean newlines for single-line preview
            clean_content = self.node.content.strip().replace('\n', ' ')
            display_text = f"RAW: {clean_content}"

        content_snippet = ""
        if display_text:
            content_snippet = f"\n{indent}    │ {display_text[:85]}..."

        # --- 7. RECURSION ---
        children_str = "".join([child._format_tree(level + 1) for child in self.children])

        # Assemble the block
        return f"\n{header}{anchor_text_display}{content_snippet}\n{emb_line}{children_str}"
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