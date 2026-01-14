import json
import base64
import logging
import traceback
import sys
import os
from io import BytesIO
import urllib.request  # Used to fetch the PDF from the URL

# Import your custom modules
from superdoc.superdoc import superdoc
from googledoc.googledoc import DocumentIDStore, GoogleDocsEditor

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

INDEX_NAME = 'sdtest1'

def handler(event, context):
    """
    Main entry point for AWS Lambda.
    Routes requests based on the 'path' or 'resource' key in the event.
    """
    try:
        # 1. Determine the path and method
        # Handling both REST API and HTTP API Gateway formats
        path = event.get('path', event.get('rawPath', '/'))
        method = event.get('httpMethod', event.get('requestContext', {}).get('http', {}).get('method', 'GET'))
        
        logger.info(f"Method: {method}, Path: {path}")

        # 2. Routing Logic
        if path == '/health' and method == 'GET':
            return respond(200, {"status": "healthy"})

        elif path == '/merge_pdf' and method == 'POST':
            return handle_merge_pdf(event)

        elif path == '/delete_heading' and method == 'DELETE':
            return handle_heading_operation(event, "delete")

        elif path == '/create_heading' and method == 'POST':
            return handle_heading_operation(event, "create")

        elif path == '/update_heading' in ['PUT', 'PATCH']:
            return handle_heading_operation(event, "update")

        elif path == '/get_docids':
            return handle_get_docids(event)

        elif path == '/create_document' and method == 'POST':
            return handle_create_document(event)

        else:
            return respond(404, {"error": f"Route {path} not found"})

    except Exception as e:
        logger.error(traceback.format_exc())
        return respond(500, {"error": str(e), "trace": traceback.format_exc()})

# --- Helper Functions for Endpoints ---

def handle_merge_pdf(event):
    print(event)
    body = parse_body(event)
    
    # 1. Acquire the URL from the JSON body
    pdf_url = body.get('pdfUrl') or event.get('pdfUrl')
    courseId = body.get('courseId') or event.get('courseId') 
    documentId = body.get('documentId') or event.get('documentId')
    index_name = body.get('index_name') or event.get('index_name') or INDEX_NAME # Fallback to default

    if not pdf_url or not courseId:
        print(f"pdfUrl:{pdf_url}")
        print(f"courseId:{courseId}")
        return respond(400, {"error": "pdf_url and course-Id are required"})

    try:
        logger.info(f"Fetching PDF from URL: {pdf_url}")
        
        # 2. Process the PDF and turn it into a BytesIO stream
        # We use a context manager to ensure the connection closes
        with urllib.request.urlopen(pdf_url) as response:
            if response.status != 200:
                return respond(400, {"error": f"Failed to download PDF from Discord. Status: {response.status}"})
            
            # Read the bytes into a BytesIO stream
            pdf_stream = BytesIO(response.read())
        
        logger.info("PDF successfully converted to BytesIO stream")

        # 3. Pass the stream to your superdoc logic
        sd = superdoc(DOCUMENT_ID=documentId, COURSE_ID=courseId, index_name=index_name)
        sd.merge_pdf_hierarchical(stream=pdf_stream)

        return respond(200, {
            "status": "success", 
            "message": "PDF fetched and merged successfully",
            "documentId": sd.DOCUMENTID
        })

    except Exception as e:
        logger.error(f"Error processing PDF URL: {str(e)}")
        return respond(500, {"error": f"Internal error processing PDF: {str(e)}"})

def handle_heading_operation(event, action):
    body = parse_body(event)    
    courseId = body.get('courseId') or event.get('courseId') 
    documentId = body.get('documentId') or event.get('documentId')
    if not courseId:
        return respond(400, {"error": "course-Id is required"})

    sd = superdoc(DOCUMENT_ID=documentId, COURSE_ID=courseId, index_name=INDEX_NAME)

    if action == "delete":
        sd.delete_heading(old_heading=body.get('old_heading') or event.get('old_heading'))
    elif action == "create":
        sd.create_heading(new_heading=body.get('new_heading') or event.get('new_heading'))
    elif action == "update":
        sd.update_heading(old_heading=body.get('old_heading') or event.get('old_heading'), new_heading=body.get('new_heading') or event.get('new_heading'))

    return respond(200, {"status": "success", "documentId": sd.DOCUMENTID})

def handle_get_docids(event):
    data = parse_body(event)
    courseId = body.get('courseId') or event.get('courseId') 
    if not courseId:
        return respond(400, {"error": "course-Id is required"})

    idstore = DocumentIDStore()
    ids = idstore.get_docids(courseid=courseId)
    return respond(200, {"status": "success", "ids": ids})

def handle_create_document(event):
    data = parse_body(event)
    courseId = body.get('courseId') or event.get('courseId') 
    document_name = data.get('document_name')

    if not courseId or not document_name:
        return respond(400, {"error": "course-Id and document_name are required"})

    docs_editor = GoogleDocsEditor()
    response = docs_editor.create_google_doc(name=document_name, courseid=courseId)
    
    if not response:
        return respond(500, {"error": "Failed to create document"})

    return respond(200, {
        "status": "success", 
        "documentId": response.get('documentId')
    })

# --- Utility Functions ---

def parse_body(event):
    """Helper to parse JSON body from Lambda event"""
    body = event.get('body', '{}')
    if event.get('isBase64Encoded', False):
        body = base64.b64decode(body).decode('utf-8')
    
    try:
        return json.loads(body) if isinstance(body, str) else body
    except:
        return {}

def respond(status_code, body):
    """Helper to format API Gateway responses"""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*" # Required for CORS
        },
        "body": json.dumps(body)
    }