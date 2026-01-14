from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.hierarchical_chunker import HierarchicalChunker, DocChunk,DocMeta, ChunkingSerializerProvider
from docling_core.types.doc.document import (
    DocItem,
    DoclingDocument,
    DocumentOrigin,
    InlineGroup,
    LevelNumber,
    ListGroup,
    SectionHeaderItem,
    TableItem,
    TitleItem,
    TextItem
)
from docling_core.transforms.serializer.common import create_ser_result
from docling_core.transforms.chunker import BaseChunk, BaseChunker, BaseMeta
from chunking.semchunking import SemanticChunker
from langchain_openai import OpenAIEmbeddings
from typing import Any
from langchain_core.embeddings import Embeddings
from langchain_community.utils.math import cosine_similarity
import numpy as np
import os 

class EmbedChunk(DocChunk):
    embedding:Any

class DocSemChunker():
    def __init__(self):
        self.serializer_provider = ChunkingSerializerProvider()
        self.chunker = SemanticChunker(
            OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY")),
            breakpoint_threshold_type="percentile"
        )
    def chunk(self,dl_doc:DoclingDocument,doc_name:str):
        heading_by_level: dict[int, str] = {}  # Changed LevelNumber to int for simplicity
        visited: set[str] = set()
        
        my_doc_ser = self.serializer_provider.get_serializer(doc=dl_doc)
        excluded_refs = my_doc_ser.get_excluded_refs()
        combined_text = ""
        prev_heading = ""
        prev_level = 0
        seen_heading = False
        #Going through each item/level picked up by docling
        for item, level in dl_doc.iterate_items(with_groups=True):
           # print(f"Item:{item}, level:{level}")
            if item.self_ref in excluded_refs: 
                continue 
            #If the current element is a "heading", then we chunk the combined text and yeild the chunked docs
            if isinstance(item, (TitleItem,SectionHeaderItem)): 
                
                level = item.level if isinstance(item, SectionHeaderItem) else 0 
                
                #flushes current blurb if we're not under the same heading anymore->could deal with some refactoring to take in subheadings and such
                if(item.text!=prev_heading): 
                    if(combined_text!=""): 
                        seen_heading = True
                        for document in self.chunker.create_documents([combined_text]): 
                            
                            '''
                            c = EmbedChunk(
                                text=document.page_content,
                                meta=DocMeta(
                                doc_items=[item],
                                headings=[heading_by_level[k] for k in sorted(heading_by_level)]
                                or None,
                                origin=dl_doc.origin,
                                ),
                                embedding = document.metadata["chunk_embedding"] 
                            )
                        '''
                            document.metadata["source"] = doc_name
                            document.metadata["position"] = [heading_by_level[k] for k in sorted(heading_by_level)] or None
                            document.metadata["origin"] = str(dl_doc.origin) 
                            
                            yield document
                    #combined_text is emptied because we are now under empty/new_heading
                    combined_text = ""
                    
                
                heading_by_level[level] = item.text
                prev_heading = item.text 
                prev_level = level
                
                 # remove headings of higher level as they just went out of scope
                keys_to_del = [k for k in heading_by_level if k > level]
                for k in keys_to_del:
                    heading_by_level.pop(k, None)
                
            elif(
                isinstance(item,(ListGroup, InlineGroup, DocItem))
                and item.self_ref not in visited
            ): 
                if(level<prev_level):
                    for document in self.chunker.create_documents([combined_text]): 
                        document.metadata["source"] = doc_name
                        document.metadata["position"] = [heading_by_level[k] for k in sorted(heading_by_level)] or None
                        document.metadata["origin"] = str(dl_doc.origin) 
                        yield document
                    combined_text=""
                ser_res = my_doc_ser.serialize(item=item, visited=visited)
                combined_text+=ser_res.text
            else:   
                print(f"Ingoring:{item}")
                continue
        if(not seen_heading): 
            for document in self.chunker.create_documents([combined_text]): 
                document.metadata["source"] = doc_name
                document.metadata["position"] = [heading_by_level[k] for k in sorted(heading_by_level)] or None
                document.metadata["origin"] = str(dl_doc.origin) 
                yield document

    def create_chunk_clusters(self,dl_doc:DoclingDocument,doc_name:str,threshold:float):
        """



        Improved version of your original approach with better similarity checking.


        """
        chunk_gen = self.chunk(dl_doc=dl_doc,doc_name=doc_name)
        
        clusters = []


        used = set()

        # Sort by embedding magnitude to start with "prototypical" documents
        sorted_chunks = sorted(list(chunk_gen), 
            key=lambda x: np.linalg.norm(x.metadata['chunk_embedding']), 
            reverse=True)

        for i, chunk in enumerate(sorted_chunks):

            if id(chunk) in used:
                continue

            # Start new cluster

            cluster = [chunk]

            used.add(id(chunk))

            center_embedding = chunk.metadata['chunk_embedding']

            # Find similar chunks (check against cluster center)
            for other_chunk in sorted_chunks[i+1:]:
                
                if id(other_chunk) in used:
                    continue

                similarity = cosine_similarity(

                    [center_embedding], 
                    [other_chunk.metadata['chunk_embedding']]
                )[0][0]

                if similarity >= threshold:
                    cluster.append(other_chunk)
                    used.add(id(other_chunk))
                    # Update cluster center as we add members
                    cluster_embeddings = [c.metadata['chunk_embedding'] for c in cluster]
                    center_embedding = np.array(cluster_embeddings).mean(axis=0)

            # Final mean embedding for the cluster

            cluster_embeddings = [c.metadata['chunk_embedding'] for c in cluster]

            mean_embedding = np.array(cluster_embeddings).mean(axis=0)

            clusters.append({
                'mean_embedding': mean_embedding,
                'chunks': cluster,
                'size': len(cluster)
            })
        return clusters
if __name__ == "__main__": 
    converter = DocumentConverter()
    doc = converter.convert("./files/ResearchPaperTurnIn.pdf").document 
    chunker = DocSemChunker() 
    cluster_iter = chunker.create_chunk_clusters(dl_doc=doc,doc_name="rpaper",threshold=1.85)

    embedder = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY"))

    for cluster in cluster_iter: 
       
        print(f"cluster len:{cluster['size']}")
    
    
