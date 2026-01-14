import os.path
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone, IndexModel, ServerlessSpec
from itertools import chain
from diskcache import Index

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from langchain_core.documents import Document
from chunking.doc_chunking import DocSemChunker
from docling.document_converter import DocumentConverter

from pdf_pipeline.parse import EmbedTreeNode

# If modifying these SCOPES, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/documents","https://www.googleapis.com/auth/drive.file"] # Use full scope like 'https://www.googleapis.com/auth/documents' for write operations
class GdocTreeNode():
    def __init__(self,enode:EmbedTreeNode):
        self.enode = enode
        self.node:SyntaxTreeNode = self.enode.node
        type:str = self.node.type
        content:str = None if type=="root" else self.node.content
        self.children:list[GdocTreeNode] = []
        self.requests = []

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

    def _dispatch_node_type(self, index: int) -> tuple[list[dict], int]:
        """Routes the node to the correct formatting method based on SyntaxTreeNode type."""
        node_type = self.node.type
        
        if node_type == "root":
            return [], 0 # Root usually holds no text
        elif node_type == "heading":
            return self._format_heading(index)
        elif node_type == "paragraph":
            return self._format_paragraph(index)
        elif node_type == "list":
            return self._format_list_item(index)
        elif node_type == "code_block":
            return self._format_code_block(index)
        else:
            # Default fallback for basic text
            return self._format_plain_text(index)

    def _format_heading(self, index: int) -> tuple[list[dict], int]:
        text = self.node.content.strip() + "\n"
        text_len = len(text.encode("utf-16-le")) // 2
        
        requests = [
            {'insertText': {'location': {'index': index}, 'text': text}},
            {'updateTextStyle': {
                'range': {'startIndex': index, 'endIndex': index + text_len},
                'textStyle': {'bold': True, 'fontSize': {'magnitude': 16, 'unit': 'PT'}},
                'fields': 'bold,fontSize'
            }}
        ]
        return requests, text_len

    def _format_paragraph(self, index: int) -> tuple[list[dict], int]:
        text = self.node.content.strip() + "\n\n"
        text_len = len(text.encode("utf-16-le")) // 2
        
        requests = [
            {'insertText': {'location': {'index': index}, 'text': text}},
            {'updateParagraphStyle': {
                'range': {'startIndex': index, 'endIndex': index + text_len},
                'paragraphStyle': {'lineSpacing': 115.0, 'spaceAbove': {'magnitude': 10, 'unit': 'PT'}},
                'fields': 'lineSpacing,spaceAbove'
            }}
        ]
        return requests, text_len

    def _format_list_item(self, index: int) -> tuple[list[dict], int]:
        text = self.node.content.strip() + "\n"
        text_len = len(text.encode("utf-16-le")) // 2
        
        requests = [
            {'insertText': {'location': {'index': index}, 'text': text}},
            {'createParagraphBullets': {
                'range': {'startIndex': index, 'endIndex': index + text_len},
                'bulletPreset': 'BULLET_DISC_CIRCLE_SQUARE'
            }}
        ]
        return requests, text_len

    def _format_code_block(self, index: int) -> tuple[list[dict], int]:
        text = self.node.content.strip() + "\n"
        text_len = len(text.encode("utf-16-le")) // 2
        
        requests = [
            {'insertText': {'location': {'index': index}, 'text': text}},
            {'updateTextStyle': {
                'range': {'startIndex': index, 'endIndex': index + text_len},
                'textStyle': {
                    'weightedFontFamily': {'fontFamily': 'Courier New'},
                    'backgroundColor': {'color': {'rgbColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}}}
                },
                'fields': 'weightedFontFamily,backgroundColor'
            }}
        ]
        return requests, text_len

    def _format_plain_text(self, index: int) -> tuple[list[dict], int]:
        text = self.node.content
        if not text: return [], 0
        text_len = len(text.encode("utf-16-le")) // 2
        return [{'insertText': {'location': {'index': index}, 'text': text}}], text_len 
        



class GoogleDocsAPI:
    def __init__(self, credentials_file='credentials.json', token_file='token.json'):
        self.credentials_file = credentials_file
        self.token_file = token_file
        (self.doc_service,self.drive_service) = self.authenticate()
    
    def authenticate(self):
        creds = None
        # The token.json stores the user's access and refresh tokens
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES)
                # This will open a browser window for you to sign in
                creds = flow.run_local_server(port=0)
                
            # Save the credentials for the next run
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        return (build('docs', 'v1', credentials=creds),build('drive', 'v3', credentials=creds))
    '''
    def authenticate(self):
        """Authenticate and build the Google Docs service"""
        
        # If you have OAuth 2.0 credentials
        creds = None
        # The file token.json stores the user's access and refresh tokens.
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file)
        
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # You'll need to set up OAuth 2.0 credentials
                # See: https://developers.google.com/docs/api/quickstart/python
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, 
                    ['https://www.googleapis.com/auth/documents']
                )
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        return build('docs', 'v1', credentials=creds)
        try:
            #print(f"OS:{os.getenv("GOOGLE_SERVICE_ACCT")}")
            creds = service_account.Credentials.from_service_account_file(
                os.getenv("GOOGLE_SERVICE_ACCT"), 
                scopes=SCOPES
            )
            return (build('docs', 'v1', credentials=creds),build('drive', 'v3', credentials=creds))
        except Exception as e:
            print(f"Error authenticating with service account: {e}")
            raise
        '''
    
class IDSError(Exception): 
        def __init__(self,msg:str):
            self.msg = msg
class DocumentIDStore(): 
    
    def __init__(self):
        self.cache = Index("idstore")
    
    def push_new_docId(self,courseid:str,docname:str,docid:str):
        temp_dict = {}
        if courseid in self.cache: 
            temp_dict = self.cache[courseid]
        if docname in temp_dict: 
            raise IDSError("document name taken")
        temp_dict[docname] = docid
        self.cache[courseid] = temp_dict
        
    def get_docids(self,courseid:str): 
        if courseid in self.cache:
            return self.cache[courseid]
        return None 
    
    
class GoogleDocsEditor(GoogleDocsAPI):
    def __init__(self):
        super().__init__()
        self.idstore = DocumentIDStore()
        
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
            self.idstore.push_new_docId(courseid=courseid,docname=name,docid=document_id)
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
    
    def get_idstore_docids(self,courseid:str): 
        return self.idstore.get_docids(courseid=courseid)
      
    def get_document_structure(self, document_id):
        """Fetch the current document state"""
        try:
            self.document_id = document_id
            self.doc = self.doc_service.documents().get(documentId=document_id).execute()
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
        
        newHeadingLen = len((new_heading).encode("utf-16-le"))//2
        endIndex = startIndex+newHeadingLen
        requests = [
        {
            'insertText': {
                'location': {
                    'index': startIndex
                },
                'text': new_heading
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
        }
    ]
        self.batch_update(requests=requests)
        
        
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
    
        
                


        
def insert_text_ex(): 
     # Initialize the editorpinecone_api_key = os.environ.get("PINECONE_API_KEY")
    pinecone_api_key = os.environ.get("PINECONE_API_KEY")
    print(f"Start of VectorDBManager init")
    db = VectorDBManager(pc=Pinecone(pinecone_api_key))
    db.initVectorStore(index_name="sdtest1", embedding=OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY")))
    print(f"Start of pdf conversion")
    docs_editor = GoogleDocsEditor()
    drive_activity = GoogleDriveActivity()
    
    converter = DocumentConverter()
    doc = converter.convert("./files/ResearchPaperTurnIn.pdf").document 
    chunker = DocSemChunker() 
    print("Starting chuking")
    chunk_iter = list(chunker.chunk(dl_doc=doc,doc_name="rpaper"))
    # Your Google Docs document ID (om the URL)
    chunk_iter = db.modify_doc_heading(documents=chunk_iter,superdoc_id="rpaper",course_id="RHET1302")
    DOCUMENT_ID = '1zjQClSEUE587kPrupY5fplFtUcB3OGEj5mKhplmiFxM'
    
    # Example 1: Append to the very end
    docs_editor.get_document_structure(document_id=DOCUMENT_ID)
   # print(f"Doc structure:{docs_editor.doc}")
    #print(docs_editor.find_insertion_point("stuff"))
    #print("Appending to end of document...")
    docs_editor.insert_text(document_id=DOCUMENT_ID, chunk_docs=chunk_iter)
       
    
    
    
def main():
    # Initialize the editorpinecone_api_key = os.environ.get("PINECONE_API_KEY")
    #drive_activity = GoogleDriveActivity()
    #insert_text_ex()
    DOCUMENT_ID = '1PD0Pd_O7BUplXV1RJ3xGsBp9e_UwXWqkhuTCMgAxKcY'
    docs_editor = GoogleDocsEditor()
    #docs_editor.update_heading(old_heading="Introduction",new_heading="Goofy Goober")
    #print(docs_editor.find_named_range(heading="Introduction"))
    docs_editor.get_document_structure(document_id=DOCUMENT_ID)
    #docs_editor.create_google_doc(name="cholorplasts",courseid="RHET1302")
    print(f"Doc Content{docs_editor.get_text_in_range_from_doc_obj(heading="Thylakoid Membranes Maximize Light Absorption")}")
    # print(f"Doc structure:{docs_editor.doc}")
    #print(docs_editor.find_insertion_point("stuff"))
    #print("Appending to end of document...")
    #docs_editor.insert_text(document_id=DOCUMENT_ID, chunk_docs=chunk_iter)
    #AUTHOR_DISPLAY_NAME = "Indrajith Thyagaraja"
    #comments = drive_activity.list_comments_by_author(file_id=DOCUMENT_ID,author_display_name=AUTHOR_DISPLAY_NAME)
    #print(f"Comments: {comments}")
    
if __name__ == "__main__":
    main()

