from langchain_openai import OpenAIEmbeddings,ChatOpenAI

from vectordb.vector_db_manager import VectorDBManager
from pinecone import Pinecone, IndexModel, ServerlessSpec


from googledoc.googledoc import GoogleDocsEditor


from pdf_pipeline.parse import EmbedTreeNode, GdocTreeNode, pdf_to_syntree, stree_to_etree
from io import BytesIO

from dotenv import load_dotenv
import os
import time
load_dotenv()

def test_render_to_gdoc():
    # 1. Setup Data and Paths
    SUPERDOC_ID = '1zjQClSEUE587kPrupY5fplFtUcB3OGEj5mKhplmiFxM' # Your specified ID
    COURSE_ID = 'prof-1302'
    with open("files/Chloroplasts 1.pdf", "rb") as f:
        pdf_bytes = f.read()
    strm = BytesIO(pdf_bytes)
    
    # 2. Convert PDF to Semantic Tree
    synt_tree = pdf_to_syntree(stream=strm)
    emb_model = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY")) 
    
    # 3. Initialize the Vector DB to get existing headings and docs editor
    pinecone_api_key = os.environ.get("PINECONE_API_KEY")
    docs_editor = GoogleDocsEditor()
    db = VectorDBManager(pc=Pinecone(pinecone_api_key))
    db.initVectorStore(index_name="sdtest1", embedding=emb_model)
    
    # 4. Build and Process the EmbedTreeNode Tree
    root = stree_to_etree(stree=synt_tree,emb_model=emb_model)
    print(root) 
    #print(root)
    # 5. Inject Custom Headings from Pinecone
    # Note: Using the course_id and reference doc ID from your example
    headings = db.get_all_headings_for_doc(
        course_id=COURSE_ID, 
        superdoc_id=SUPERDOC_ID
    )
    #print(headings)
    #print(f"\n=== BEFORE insert_custom_headings ===")
    #print(f"Root has {len(root.children)} children")
    #for i, child in enumerate(root.children[:3]):  # First 3 children
    #    print(f"  Child {i}: type={child.type}, block_len={child.block_len}")

    (new_cust_nodes, all_cust_nodes) = root.insert_custom_headings(headings=headings)
   
    print(f"Printing generated nodes({len(new_cust_nodes)}):{new_cust_nodes}")
    db.append_documents(e_branches=new_cust_nodes,course_id=COURSE_ID,superdoc_id=SUPERDOC_ID)
    print("Custom headings display:\n")
    root.display_custom_headings()
    print(root)
    print(f"\n=== AFTER insert_custom_headings ===")
    print(f"Generated {len(new_cust_nodes)} new headings")
    print(f"Total {len(all_cust_nodes)} custom nodes")

    # Debug each custom node
    for i, node in enumerate(all_cust_nodes):
        print(f"\n=== Custom node {i}: {node.content} ===")
        print(f"  Type: {node.type}")
        print(f"  Is custom: {node.is_custom_node}")
        print(f"  Parent: {node.parent.type if node.parent else None}")
        print(f"  Children count: {len(node.children)}")

        # Check what the ORIGINAL node under this was
        if len(node.children) > 0:
            for j, child in enumerate(node.children[:2]):
                print(f"    Child {j}: type={child.type}, content={child.content[:50] if child.content else 'None'}")
        else:
            print(f"    ⚠️ NO CHILDREN - This is the problem!")

    print("Transforming to Gdoc Hierarchical Tree...")
    #gdoc_root = GdocTreeNode._init_tree(etree=root)
    
    # 7. Initialize Google Docs Editor and Render
    start_render = time.perf_counter()
    print(f"Connecting to Google Doc: {SUPERDOC_ID}")
    docs_editor.render_etree_custom_nodes(superdoc_id=SUPERDOC_ID,all_cust_nodes=all_cust_nodes)
    
    
    end_render = time.perf_counter()
    print(f"Time:{(end_render - start_render):.2f}s")    



if __name__ == "__main__": 
    test_render_to_gdoc()
