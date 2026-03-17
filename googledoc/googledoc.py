import os.path
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone, IndexModel, ServerlessSpec
from itertools import chain
from diskcache import Index

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from langchain_core.documents import Document

from pdf_pipeline.etree import EmbedTreeNode
from pdf_pipeline.gdoctree import GdocTreeNode
from io import BytesIO

from collections import defaultdict

from dynamodb.dynamodb import append_to_course_docs, fetch_all_course_docs
# If modifying these SCOPES, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/documents","https://www.googleapis.com/auth/drive.file"] # Use full scope like 'https://www.googleapis.com/auth/documents' for write operations

class GoogleDocsAPI:
    def __init__(self, credentials_file='credentials.json', token_file='token.json'):
        self.credentials_file = credentials_file
        self.token_file = token_file
        (self.doc_service,self.drive_service) = self.authenticate()
        #self.doc = None
    
    def authenticate(self):
        """Authenticate and build the Google Docs service"""
        """Authenticate and build the Google Docs and Drive services in a read-only environment"""
    
        creds = None
        
        if os.path.exists(self.token_file):
            # 1. Read the file into memory first
            with open(self.token_file, 'r') as f:
                token_data = json.load(f)
            
            # 2. Use 'from_authorized_user_info' to prevent the library 
            # from trying to manage (and write to) the file on disk.
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        
        # 3. Handle token refresh
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                print("Refreshing expired Google token in memory...")
                try:
                    # This refreshes the 'creds' object but DOES NOT save to disk
                    creds.refresh(Request())
                except Exception as e:
                    print(f"Failed to refresh token: {e}")
                    raise Exception("Google Refresh Token is invalid or revoked.")
            else:
                # In Lambda, we cannot run flow.run_local_server(). 
                # If we reach this block, it means token.json is missing or totally invalid.
                raise FileNotFoundError("Valid token.json not found. Please generate it locally first.")
    
        print(f"Credentials valid: {creds.valid}")
        
        # Build services
        docs_service = build('docs', 'v1', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)
        
        return (docs_service, drive_service)
        
'''
class GoogleDocsAPI:
    def __init__(self, credentials_file='service-account-key.json'):
        # In Docker, make sure this path matches where you COPY the file
        self.credentials_file = credentials_file
        self.doc_service, self.drive_service = self.authenticate()
        self.doc = None

    def authenticate(self):
        SCOPES = ['https://www.googleapis.com/auth/documents', 
                  'https://www.googleapis.com/auth/drive']
        
        # Load the service account credentials directly
        creds = service_account.Credentials.from_service_account_file(
            self.credentials_file, scopes=SCOPES)
        
        return (
            build('docs', 'v1', credentials=creds),
            build('drive', 'v3', credentials=creds)
        )
'''
    
    
class GoogleDocsEditor(GoogleDocsAPI):
    def __init__(self):
        super().__init__()
        
    def get_text_in_range_from_doc_obj(self,heading:str):
        """Helper to extract text from a doc object already in memory."""
        named_range = self.find_named_range(heading)
        start_index = named_range['namedRanges'][0]['ranges'][0]['startIndex']
        end_index = named_range['namedRanges'][0]['ranges'][0]['endIndex']
        extracted = []
        content = self.doc.get('body').get('content', [])

        for element in content:
            el_start = element.get('startIndex')
            el_end = element.get('endIndex')

            if el_start is not None and el_end is not None:
                if el_start < end_index and el_end > start_index:
                    if 'paragraph' in element:
                        for part in element['paragraph']['elements']:
                            if 'textRun' in part:
                                text = part['textRun']['content']
                                p_start = part.get('startIndex')

                                rel_start = max(0, start_index - p_start)
                                rel_end = min(len(text), end_index - p_start)

                                if rel_start < rel_end:
                                    extracted.append(text[rel_start:rel_end])
        return "".join(extracted)


    def create_google_doc(self, name:str, courseid:str):
        try:
            # Create the document using the Docs API
            #print(f"Service Account Email: {self.doc_service._http.credentials.service_account_email}")
            response = self.doc_service.documents().create(body={'title': name}).execute()
            document_id = response.get('documentId')
            append_to_course_docs(courseId=courseid,new_doc_ids=[document_id])#self.idstore.push_new_docId(courseid=courseid,docname=name,docid=document_id)
            print(f'Created Document ID: {document_id}')

            # Set the document to be editable by anyone with the link
            permission_result = self.drive_service.permissions().create(
                fileId=document_id,
                body={
                    'role': 'writer',
                    'type': 'anyone'
                }
            ).execute()
            print(permission_result)
            print("Document sharing permissions updated.")
            print(document_id)

            return response

        except Exception as err:
            print(f'Error creating document: {err}')
            return None
    
    def get_docids(self,courseid:str): 
        return fetch_all_course_docs(courseId=courseid)
      
    def get_document_structure(self, document_id):
        """Fetch the current document state"""
        try:
            ##print("CALLED DOCUMENT STRUCTURE")
            self.document_id = document_id
            self.doc = self.doc_service.documents().get(documentId=document_id).execute()
            return self.doc
           # print(f"CALLED DOCUMETN STRUCTURE:{self.doc}")
        except Exception as e:
            print(f"Error fetching document: {e}")
            return None
    
    def text_utf16_len(self,text:str): 
        return len((text).encode("utf-16-le"))//2
        
    def descending_sort_inserttext(self,requests):
        return sorted(requests, 
                 key=lambda x: x.get("insertText", {})
                               .get("location", {})
                               .get("index", 0), 
                 reverse=True) 
            
    def batch_update(self,requests):
        if not requests or len(requests) == 0: 
            return
        try: 
            # Execute the batch update
            result = self.doc_service.documents().batchUpdate(
                #replace with actual document_id 
                documentId=self.document_id,
                body={'requests': requests}
            ).execute()
            
            #print(f"Successfully inserted text at index {insertion_index}")
            return True
            
        except Exception as e:
            print(f"Error inserting text: {e}")
            return False
    
    
  
    def find_named_range(self,heading:str)->dict|None:
        document = self.doc
        named_ranges = document.get("namedRanges",{})
        for range_name in named_ranges.keys():
            #print(f'-{range_name}')
            if range_name==heading: 
                return named_ranges[heading] 
        return None
    def create_heading(self,new_heading:str): 
        (_,startIndex,_) = self.find_insertion_point()
        named_range = self.find_named_range(heading=new_heading)
        if named_range: 
            raise Exception(f"Heading: {new_heading} already exists")
        
        newHeadingLen = len((new_heading+":\n\n").encode("utf-16-le"))//2
        endIndex = startIndex+newHeadingLen
        requests = [
        {
            'insertText': {
                'location': {
                    'index': startIndex
                },
                    'text': new_heading+":\n\n"
            }
        },
        # Create a new named range for the updated heading
        {
            'createNamedRange': {
                'name': new_heading,
                'range': {
                    'startIndex': startIndex,
                    'endIndex': endIndex
                }
            }
        },
        {
            'updateParagraphStyle': {
                'paragraphStyle': {'namedStyleType': 'HEADING_2'},
                'range': {
                    'startIndex': startIndex,
                    'endIndex': endIndex
                },
                'fields': 'namedStyleType'
            }
        },
        {
            'updateTextStyle': {
                'textStyle': {'bold': True},
                'range': {
                    'startIndex': startIndex,
                    'endIndex': endIndex
                },
                'fields': 'bold'
            }
        }
    ]
        self.batch_update(requests=requests)
        return (startIndex,endIndex)
    
    
    def create_headings(self,headings:list[str]): 
        ranges = []
        processed = {}
        for heading in headings:
            nm_range = self.find_named_range(heading)
            startIndex = -1
            endIndex = -1
            if heading in processed: 
                startIndex = processed[heading][0]
                endIndex = processed[heading][1]
            elif not nm_range:
                rn = self.create_heading(heading)
                processed[heading] = rn
                startIndex = rn[0]
                endIndex = rn[1]
                continue 
            else: 
                startIndex = nm_range['namedRanges'][0]['ranges'][0]['startIndex']
                endIndex = nm_range['namedRanges'][0]['ranges'][0]['endIndex']

            ranges.append((startIndex,endIndex))
        return ranges

                
        
    def delete_heading(self,old_heading:str): 
        named_range = self.find_named_range(heading=old_heading)
        if not named_range: 
            raise Exception(f"Heading: {old_heading} does not exist")
        print(named_range)
        startIndex = named_range['namedRanges'][0]['ranges'][0]['startIndex']
        endIndex = named_range['namedRanges'][0]['ranges'][0]['endIndex']
        oldHeadingLen = len((old_heading).encode("utf-16-le"))//2
        requests = [
        # Delete the old heading text from the document
        {
            'deleteContentRange': {
                'range': {
                    'startIndex': startIndex,
                    'endIndex': startIndex + oldHeadingLen
                }
            }
        },
        # Remove the old named range
        {
            'deleteNamedRange': {
                'name': old_heading
            }
        },
    ]
        self.batch_update(requests=requests)
    def update_heading(self,old_heading:str,new_heading:str): 
        named_range = self.find_named_range(heading=old_heading)
        if not named_range: 
            raise Exception(f"Heading: {old_heading} does not exist")
        print(named_range)
        startIndex = named_range['namedRanges'][0]['ranges'][0]['startIndex']
        endIndex = named_range['namedRanges'][0]['ranges'][0]['endIndex']
        oldHeadingLen = len((old_heading).encode("utf-16-le"))//2
        newHeadingLen = len((new_heading).encode("utf-16-le"))//2
        requests = [
        # Delete the old heading text from the document
        {
            'deleteContentRange': {
                'range': {
                    'startIndex': startIndex,
                    'endIndex': startIndex + oldHeadingLen
                }
            }
        },
        # Insert the new heading text at the same position
        {
            'insertText': {
                'location': {
                    'index': startIndex
                },
                'text': new_heading
            }
        },
        # Remove the old named range
        {
            'deleteNamedRange': {
                'name': old_heading
            }
        },
        # Create a new named range for the updated heading
        {
            'createNamedRange': {
                'name': new_heading,
                'range': {
                    'startIndex': startIndex,
                    'endIndex': endIndex-1+(newHeadingLen-oldHeadingLen)
                }
            }
        },
    ]
        self.batch_update(requests=requests)
        #print(f"Named Range: {named_range}")
        
            
    def find_insertion_point(self, target_heading=None):
        """Locate the insertion point in the document"""
        document = self.doc
        body = document.get('body', {})
        content = body.get('content', [])
        named_ranges = document.get("namedRanges",{})
        for range_name in named_ranges.keys():
            print(f"- {range_name}")
        #print(f"Body:{body}")
        # If no target heading specified, append to the very end
        if not (target_heading):
            print(f"Printing to {content[-1].get('endIndex') - 1}")
            return (content[-1].get('endIndex'),content[-1].get('endIndex') - 1, -2)  # Adjust for 0-based indexing
        #If the heading is non-null, and is new(doesn't exist in document)
        try: 
            named_ranges[target_heading]
        except KeyError as e: 
            return (content[-1].get('endIndex'),content[-1].get('endIndex') - 1, -1)

        # Search for the specific heading
        named_range_data = named_ranges[target_heading]
        for range_group in named_range_data["namedRanges"]:
            for range_info in range_group["ranges"]:
                return (range_info["startIndex"],range_info["endIndex"],0)
            
        # If heading not found, append to end
        print(f"Heading '{target_heading}' not found. Appending to end.")
        print(f"Printing to {content[-1].get('endIndex') - 1}")
        return (content[-1].get('endIndex'),content[-1].get('endIndex') - 1,-1)

    #Before modifying the google doc, we run a quick check on all of the 
    def mutate_named_ranges(self,document_id:str):
        #self.get_document_structure(document_id=document_id)
        document = self.doc
        named_ranges = document.get("namedRanges",{})
        sorted_items = sorted(named_ranges.items(),key=lambda item: item[1].get("namedRanges", [{}])[0]
                               .get("ranges", [{}])[0]
                               .get("endIndex", 0)) 
        print(sorted_items)
        requests= []
        for i in range(1,len(sorted_items)):
            prev_ranges = sorted_items[i-1][1]\
                        .get("namedRanges",[{}])[0]\
                        .get("ranges",[{}])[0]
            curr_ranges = sorted_items[i][1]\
                        .get("namedRanges",[{}])[0]\
                        .get("ranges",[{}])[0]
            prevEndIdx = prev_ranges.get("endIndex",0)
            currStartIdx = curr_ranges.get("startIndex",0)
            #heading = sorted_items[i][0]
            diff = currStartIdx - prevEndIdx
            print(diff)
            if((diff)>self.text_utf16_len('\n')): 
                print("hit")
                requests.append(
                    {
                        'deleteNamedRange': {
                            'name': sorted_items[i-1][0]#prev_heading
                        }
                    }
                    )
                requests.append(# Create a new named range for the updated heading
                    {
                        'createNamedRange': {
                            'name': sorted_items[i-1][0],
                            'range': {
                                'startIndex': prev_ranges.get("startIndex",0),
                                'endIndex': prevEndIdx-1+(diff)
                            }
                        }
                    }
                )
        #print(requests,self.text_utf16_len('\n'))
        self.batch_update(requests=requests) 
        self.get_document_structure(document_id=document_id) 
        #named_ranges = document.get("namedRanges",{})
    
    def render_etree_custom_nodes(self,superdoc_id:str,all_cust_nodes:list[EmbedTreeNode]): 
        print(f"Connecting to Google Doc: {superdoc_id}")
        self.get_document_structure(document_id=superdoc_id) # Set the active document

        headings = [node.content for node in all_cust_nodes]
        headings.reverse()
        print(f"RECIEVED HEADINGS:{headings}") 
        self.create_headings(headings)
        self.get_document_structure(document_id=superdoc_id)
        ranges = [self.find_named_range(heading) for heading in headings] 
        ranges.reverse()
        print(f"Ranges: {ranges}")
        # Before converting to Gdoc
        for i, node in enumerate(all_cust_nodes):
            print(f"ETREE Node {i} type: {node.type}, children count: {len(node.children)}")

        gdoc_branches = [GdocTreeNode._init_tree(etree=node) for node in all_cust_nodes]

        # After converting
        for i, branch in enumerate(gdoc_branches):
            print(f"GDOC Branch {i} type: {branch.type}, children count: {len(branch.children)}")

        # Debug: Check if branches have children
        for i, branch in enumerate(gdoc_branches):
            print(f"Branch {i} ({all_cust_nodes[i].content}): {len(branch.children)} children")
    



        text_requests = []
        format_requests = []
        range_dict = {}
        req_per_heading = defaultdict(list)
        for branch, range in zip(gdoc_branches, ranges): 
            #print(f"Heading range{range}")
            heading = branch.content
            #print(branch)
            
            if heading in range_dict: 
                # Use previously calculated indices if we've already touched this heading
                startIndex = range_dict[heading]['startIndex']
                endIndex = range_dict[heading]['endIndex'] -1
                code = 0
            else:
                # Look up the heading's location in the freshly updated doc
                startIndex = range['namedRanges'][0]['ranges'][0]['startIndex']
                endIndex = range['namedRanges'][0]['ranges'][0]['endIndex']


            #startIndex = range['namedRanges'][0]['ranges'][0]['startIndex']
            #endIndex = range['namedRanges'][0]['ranges'][0]['endIndex']
            print(f"\nGDOC BRANCH: {branch}\n\n")
            (branch_text_requests, branch_format_requests, text_len) = branch.generate_formatted_requests(start_index=endIndex)#branch.generate_custom_branch_requests(startIndex=startIndex,endIndex=endIndex)
            req_per_heading[heading].append(branch_text_requests)
            req_per_heading[heading].append(branch_format_requests)
            text_requests.append(branch_text_requests)
            format_requests.append(branch_format_requests)

            range_dict[heading] ={
                    'startIndex' : startIndex, 
                    'endIndex' : endIndex + text_len
                }


        #Need to make a final set named range fixer here:

        #sorting custom_node delimited branches in reverse order so that the branches get appened right
        #print(text_requests)
        text_requests = [req for req in text_requests if len(req)!=0]

        sorted_heading_ranges = sorted(range_dict.items(), 
                    key= lambda x: x[1]['startIndex'],
                                reverse=True)
        print(f"Sorted heading ranges: {sorted_heading_ranges}")
        text_and_format_requests = []
        for (heading,heading_range) in sorted_heading_ranges:
            startIndex = range_dict[heading]['startIndex']
            endIndex = range_dict[heading]['endIndex']

            for requests in req_per_heading[heading]:
                text_and_format_requests.extend(requests)
            text_and_format_requests.extend([
                {'deleteNamedRange': {'name': heading}},                  
                {
                    'createNamedRange': {
                        'name': heading,
                        'range': {
                            'startIndex': startIndex,
                            'endIndex': endIndex
                        }
                    }   
                }
            ])
       
     
        batch_all_requests = text_and_format_requests
        print(f"Len of all requests:{len(batch_all_requests)}")
      
        self.batch_update(batch_all_requests)
        print(f"FINISHED BATCH UPDATE")

       
def test_render_to_gdoc():
    # 1. Setup Data and Paths
    superdoc_id = '1zjQClSEUE587kPrupY5fplFtUcB3OGEj5mKhplmiFxM' # Your specified ID
    with open("files/Chloroplast 2.pdf", "rb") as f:
        pdf_bytes = f.read()
    strm = BytesIO(pdf_bytes)
    
    # 2. Convert PDF to Semantic Tree
    synt_tree = pdf_to_syntree(stream=strm)
    emb_model = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY")) 
    
    # 3. Initialize the Vector DB to get existing headings
    pinecone_api_key = os.environ.get("PINECONE_API_KEY")
    db = VectorDBManager(pc=Pinecone(pinecone_api_key))
    db.initVectorStore(index_name="sdtest1", embedding=emb_model)
    
    # 4. Build and Process the EmbedTreeNode Tree
    print("Building Semantic Tree...")
    root = EmbedTreeNode._init_tree(root_node=synt_tree, emb_model=emb_model)
    EmbedTreeNode._embed_tree_(root)
    EmbedTreeNode._calc_mean_embedding(root)
    EmbedTreeNode._calc_block_len(root)
    
    # 5. Inject Custom Headings from Pinecone
    # Note: Using the course_id and reference doc ID from your example
    headings = db.get_all_headings_for_doc(
        course_id="prof-1302", 
        superdoc_id="1VLXyc4FDmf0kENOa__O-70ANrKUsxcAUV9wKDSh-X9A"
    )
    root.insert_custom_headings(headings=headings)
    
    # 6. Transform to Google Doc Tree
    print("Transforming to Gdoc Hierarchical Tree...")
    gdoc_root = GdocTreeNode._init_tree(etree=root)
    
    # 7. Initialize Google Docs Editor and Render
    print(f"Connecting to Google Doc: {superdoc_id}")
    self = GoogleDocsEditor()
    self.document_id = superdoc_id # Set the active document
    
    start_render = time.perf_counter()
    
    # This calls the recursive logic to generate requests and upsert
    self.upsert_gdoc_tree(gdoc_root)
    
    end_render = time.perf_counter()
    print(f"Success! Tree rendered to Google Docs in {(end_render - start_render):.2f}s")    
    
    
def main():
    # Initialize the editorpinecone_api_key = os.environ.get("PINECONE_API_KEY")
    #drive_activity = GoogleDriveActivity()
    #insert_text_ex()
    #DOCUMENT_ID = '1PD0Pd_O7BUplXV1RJ3xGsBp9e_UwXWqkhuTCMgAxKcY'
    #self = GoogleDocsEditor()
    #self.update_heading(old_heading="Introduction",new_heading="Goofy Goober")
    #print(self.find_named_range(heading="Introduction"))
    #self.get_document_structure(document_id=DOCUMENT_ID)
    #self.create_google_doc(name="trees",courseid="prof-1302")
    #print(f"Doc Content{self.get_text_in_range_from_doc_obj(heading="Thylakoid Membranes Maximize Light Absorption")}")
   # test_render_to_gdoc()
    pass
if __name__ == "__main__":
    main()
