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
        '''        
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
        '''    
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