from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_community.utils.math import (
    cosine_similarity,
)
from pinecone import Pinecone, IndexModel, ServerlessSpec
import os
import hashlib
import numpy as np
import time
from pydantic import BaseModel 
from numpy import ndarray
from typing import Optional
from uuid import uuid4
from langchain_core.documents import Document
import re
from langchain_openai import ChatOpenAI
from lexical.lexical_algs import extract_text_similarity_jaccard
from googledoc.googledoc import GoogleDocsEditor

from pdf_pipeline.parse import EmbedTreeNode, pdf_to_syntree
from io import BytesIO
'''
Need this to, create tables automatically
Initalize and Access the tables
And also do cosine similarity search efficently
In order to do the superdoc comparison alg properly

'''

class VectorDBManager(BaseModel):
    pc:Pinecone
    vs:Optional[PineconeVectorStore] = None
    index_name:Optional[str] = None
    model_config = {"arbitrary_types_allowed" : True}
    def initVectorStore(self,index_name:str,embedding:OpenAIEmbeddings):
        if not self.pc.has_index(index_name): 
            raise ValueError(f"Index:{index_name}, does not exist")
        index = self.pc.Index(index_name)
        self.vs = PineconeVectorStore(index=index,embedding=embedding)
        self.index_name = index_name        
    def createIndex(self,index_name:str):
        if self.pc.has_index(index_name): 
            raise ValueError(f"Index:{index_name}, already exists")
        self.pc.create_index(
            name=index_name,
            dimension=1536,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )    
        return self.pc.Index(index_name)
    
    def generate_timestamp_id(self,course_id):
        """Generate ID using both content and timestamp"""
        timestamp = int(time.time() * 1000)
        return f"{course_id}_{timestamp}"  
    
    def create_vectordb_heading(self, heading_text: str, course_id: str, superdoc_id: str) -> None:
        """
        Creates a new heading entry in vector DB with dynamically generated OpenAI embedding.
    
        Args:
            heading_text: The heading text (will be used to generate embedding)
            course_id: Course namespace for vector DB operations
            superdoc_id: Source filter for vector DB queries
    
        Raises:
            Exception: If embedding generation or creation fails
        """
        try:
            # Generate OpenAI embedding for the heading text
            embeddings = OpenAIEmbeddings()
            embedding = embeddings.embed_query(heading_text)
    
            print(f"Generated embedding for heading: '{heading_text}' (dimension: {len(embedding)})")
    
            index = self.pc.Index(self.index_name)
    
            # Create new entry with the dynamically generated embedding
            new_vector = {
                "id": self.generate_timestamp_id(course_id),
                "values": embedding,
                "metadata": {
                    "position": [heading_text],
                    "source": superdoc_id,
                    "heading": heading_text
                }
            }
    
            index.upsert(vectors=[new_vector], namespace=course_id)
            print(f"Successfully created new entry with heading: '{heading_text}'")
    
        except ImportError:
            raise Exception("OpenAIEmbeddings not available. Please install langchain-openai")
        except Exception as e:
            raise Exception(f"Failed to create vector DB heading '{heading_text}': {str(e)}")
    
    def remove_vectordb_heading(self, heading: str, course_id: str, superdoc_id: str) -> int:
        """
        Removes all entries with a specific heading from vector DB.

        Args:
            heading: The heading name to be removed
            course_id: Course namespace for vector DB operations
            superdoc_id: Source filter for vector DB queries

        Returns:
            int: Number of entries deleted

        Raises:
            Exception: If deletion fails
        """
        try:
            index = self.pc.Index(self.index_name)

            # Query for entries with the specified heading
            response = index.query(
                top_k=100,
                filter={"source": superdoc_id, "heading": heading},
                vector=[0] * 1536,  # Default OpenAI embedding dimension
                namespace=course_id,
                include_metadata=True
            )

            matches = response.get("matches", [])
            if matches:
                index.delete(ids=[match.id for match in matches], namespace=course_id)
                print(f"Deleted {len(matches)} entries with heading: '{heading}'")
                return len(matches)
            else:
                print(f"No existing entries found with heading: '{heading}'")
                return 0

        except Exception as e:
            raise Exception(f"Failed to remove vector DB heading '{heading}': {str(e)}")
        
        
    def replace_vectordb_heading_with_text(self, old_heading: str, new_heading_text: str, course_id: str, superdoc_id: str) -> None:
        """
        Replaces a heading in vector DB by deleting the old entry and creating a new one
        with the new heading text and its dynamically generated OpenAI embedding.

        Args:
            old_heading: The heading name to be removed
            new_heading_text: The new heading text (will be used to generate embedding)
            course_id: Course namespace for vector DB operations
            superdoc_id: Source filter for vector DB queries

        Raises:
            Exception: If embedding generation fails
        """
        try:
            # Generate OpenAI embedding for the new heading text

            embeddings = OpenAIEmbeddings()
            new_embedding = embeddings.embed_query(new_heading_text)

            print(f"Generated embedding for new heading: '{new_heading_text}' (dimension: {len(new_embedding)})")

            index = self.pc.Index(self.index_name)

            # Delete old entries
            response = index.query(
                top_k=100,
                filter={"superdoc": superdoc_id, "heading": old_heading}, #{"source": superdoc_id, "heading": old_heading}
                vector=[0] * len(new_embedding),
                namespace=course_id,
                include_metadata=True
            )

            matches = response.get("matches", [])
            if matches:
                index.delete(ids=[match.id for match in matches], namespace=course_id)
                print(f"Deleted {len(matches)} entries with old heading: '{old_heading}'")
            else:
                print(f"No existing entries found with heading: '{old_heading}'")

            # Create new entry with the dynamically generated embedding
            new_vector = {
                "id": self.generate_timestamp_id(course_id),
                "values": new_embedding,
                "metadata": {
                    "position": [new_heading_text],
                    "source": superdoc_id,
                    "heading": new_heading_text
                }
            }

            index.upsert(vectors=[new_vector], namespace=course_id)
            print(f"Successfully created new entry with heading: '{new_heading_text}'")

        except ImportError:
            raise Exception("OpenAIEmbeddings not available. Please install langchain-openai")
        except Exception as e:
            raise Exception(f"Failed to replace vector DB heading: {str(e)}")
    def _generate_heading_from_sentence(self, sentence: str) -> str:
        """
        Generate a clean, short heading using an OpenAI LLM.
        Falls back to 'Basic' if input is missing or model fails.
        """
        if not sentence or not isinstance(sentence, str):
            return "Basic"      
        try:
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.1,
                max_tokens=20  # keep it short
            )       
            prompt = (
                "Create a concise heading (4–7 words maximum) based ONLY on the following "
                "sentence. The heading must:\n"
                "- be title case\n"
                "- remove unnecessary words\n"
                "- not include punctuation\n"
                "- sound like a real document section heading\n\n"
                f"Sentence: \"{sentence}\"\n\n"
                "Heading:"
            )       
            response = llm.invoke(prompt)
            heading = response.content.strip()      
            # safety check
            if not heading:
                return "Basic"      
            return heading      
        except Exception as e:
            print(f"[WARN] LLM heading generation failed: {e}")
            return "Basic"


    def get_all_headings_for_doc(self, course_id: str, superdoc_id: str) -> list[dict]:
        """
        Retrieves all heading entries associated with a specific superdoc_id 
        within a course namespace.
        """
        try:
            index = self.pc.Index(self.index_name)
    
            # We query using a dummy vector and a metadata filter.
            # Since we want ALL headings, we set top_k to a high number (e.g., 1000).
            response = index.query(
                namespace=course_id,
                vector=[0.0] * 1536,  # Dummy vector for filter-based search
                filter={
                    "superdoc": superdoc_id
                },
                top_k=1000, 
                include_metadata=True,
                include_values=True # Set to True if you need the embeddings for similarity math
            )
    
            # Extract just the metadata/values into a clean list
            headings = []
            for match in response.get("matches", []):
                headings.append({
                    "id": match.id,
                    "heading": match.metadata.get("heading"),
                    "position": match.metadata.get("position"),
                    "embedding": match.values
                })
                
            return headings
    
        except Exception as e:
            print(f"Error fetching headings: {e}")
            return []

    def modify_embed_tree(self, etree:EmbedTreeNode, course_id:str, superdoc_id:str):
        headings = get_all_headings_for_doc(course_id=course_id,superdoc_id=superdoc_id)


    def modify_doc_heading(self, documents: list[Document], course_id: str, superdoc_id: str) -> list[Document]:
        """
            Standardizes document headings across similar content using semantic similarity.
            Reuses existing headings when content is highly similar (≥0.95 cosine similarity),
            otherwise uses current headings. Updates vector database with new headings.
        """
        gdoc_editor = GoogleDocsEditor() 
        gdoc_editor.get_document_structure(document_id=superdoc_id)
        modified_docs = []
        index = self.pc.Index(self.index_name)
        threshold = 0.95
        prev_headings = []
        for doc in documents:
        # Search for similar headings
            #instead of self.vs try index
            #print(f"Trying index search on: {doc.metadata["chunk_embedding"]}")
            response = index.query(
                top_k=1, filter={"source": superdoc_id},
                vector=doc.metadata["chunk_embedding"],
                lambda_mult=1, 
                namespace=course_id,
                include_metadata=True,
                include_values=True
            )
            #print(f"Result:{response.get("matches",[{}])[0].get("metadata",{})}")
            # Get current heading
            results = response.get("matches")
            current_heading = None
            if doc.metadata.get("position",None):
                current_heading = doc.metadata.get("position", ["basic"])[-1]
            if not current_heading:
                relevant = doc.metadata.get("relevant_sentence") or doc.metadata.get("page_content") or ""
                current_heading = self._generate_heading_from_sentence(sentence=relevant)
            #fetched_heading = ""
            if len(results) == 0:
                # No existing headings found - use current one
                new_heading = current_heading
            else:
                # Calculate actual cosine similarity
                similarity = cosine_similarity(
                    [doc.metadata["chunk_embedding"]],
                    [results[0].values]  # Need stored embedding results[0].metadata.get("embedding", [])]
                )[0][0]
                fetched_heading = results[0].metadata.get("position")[-1]
                
                if similarity >= threshold:
                    # Good match - use the found heading
                    gdoc_content = gdoc_editor.get_text_in_range_from_doc_obj(fetched_heading)
                    gdoc_content = gdoc_content.split("\n")
                    not_redundant = True
                    for paragraph in gdoc_content: 
                        val = extract_text_similarity_jaccard(paragraph,doc.page_content)
                        not_redundant = not_redundant and (val<0.3)
                    if not_redundant:
                        new_heading = fetched_heading
                    else:
                        print(f"REDUNDANT DOC FOUND")
                        continue    
                else:
                    # Poor match - use current heading
                    new_heading = current_heading
        
            # Update document
            print(f"New Heading:{new_heading}")
            doc.metadata["position"] = [new_heading]
            modified_docs.append(doc)
            # Store in vector DB (if new or modified)
            if (len(results) == 0 or similarity < threshold) and not (new_heading in prev_headings):
                index.upsert(vectors=[{
                    "id": self.generate_timestamp_id(course_id),
                    "values": doc.metadata["chunk_embedding"],
                    "metadata": {"position": [new_heading], "source": superdoc_id, "heading": new_heading}
                }], namespace=course_id)
            #index = self.pc.Index(self.index_name)
            prev_headings.append(new_heading)
        return modified_docs  # Return ALL modified docs
                 
    


    def remove_heading_entry(self,heading:str,course_id:str,superdoc_id:str): 
        try:
            # Generate OpenAI embedding for the new heading text

            embeddings = OpenAIEmbeddings()
            index = self.pc.Index(self.index_name)

            # Delete old entries
            response = index.query(
                top_k=100,
                filter={"source": superdoc_id, "heading": heading},
                vector=[0] * 1536,
                namespace=course_id,
                include_metadata=True
            )

            matches = response.get("matches", [])
            if matches:
                index.delete(ids=[match.id for match in matches], namespace=course_id)
                print(f"Deleted {len(matches)} entries with old heading: '{heading}'")
            else:
                print(f"No existing entries found with heading: '{heading}'")
        except Exception as e:
            raise Exception(f"Failed to delete vector DB heading: {str(e)}")                            
            
    #adding document to vector store-append misleading cuz it just adds it to the database
    def append_documents(self,documents:list[Document],course_id:str,superdoc_id:str):
        
        
        index = self.pc.Index(self.index_name)
        filtered_docs = ""
        index.upsert(
            vectors=[{
                "id":self.generate_timestamp_id(doc.course_id), 
                "values": doc.metadata["chunk_embedding"],
                "metadata": {"position":doc.metadata["position"],"superdoc":superdoc_id,"heading":doc.page_content}
                    
            } for doc in documents],
            namespace=course_id)

    def append_documents(self,e_branches:list[EmbedTreeNode],course_id:str,superdoc_id:str):
        
        if len(e_branches)==0:
            return
        index = self.pc.Index(self.index_name)
        filtered_docs = ""
        print(f"Append Documents branch check")
        #for branch in e_branches:
        #    print(branch)
        
        index.upsert(
            vectors=[{
                "id":self.generate_timestamp_id(course_id), 
                "values": branch.mean_emb,
                "metadata": {"superdoc":superdoc_id,"heading":branch.content}
                    
            } for branch in e_branches],
            namespace=course_id)

        
def tree_test(): 
    
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
    '''
    pinecone_api_key = os.environ.get("PINECONE_API_KEY")
    print(f"Start of VectorDBManager init")
    db = VectorDBManager(pc=Pinecone(pinecone_api_key))
    db.initVectorStore(index_name="sdtest1", embedding=OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY")))
    print(f"Start of pdf conversion")
    converter = DocumentConverter()
    doc = converter.convert("./files/ResearchPaperTurnIn.pdf").document 
    print(f"Start of chunking")
    chunker = DocSemChunker() 
    chunk_iter = list(chunker.chunk(dl_doc=doc,doc_name="rpaper"))
    print(f"Start of modifying headings")
    db.modify_doc_heading(documents=chunk_iter,superdoc_id="rpaper",course_id="RHET1302")
    #db.append_documents(documents=chunk_iter,superdoc_str="rpaper",course_id="RHET1302")
    #DOCUMENT CHUNKING AND UPLOADING
    '''
    tree_test()

