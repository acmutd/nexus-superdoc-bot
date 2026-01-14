import os
import json
import base64
import logging
import traceback
from io import BytesIO
from superdoc.superdoc import superdoc
from googledoc.googledoc import DocumentIDStore, GoogleDocsEditor

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

INDEX_NAME = os.environ.get('INDEX_NAME', 'sdtest1')

def handler(event, context):
    """
    Main AWS Lambda Handler
    """
    try:
        # 1. Determine the route/action
        # If using Function URL or API Gateway, we check the path
        path = event.get('rawPath', event.get('path', ''))
        method = event.get('requestContext', {}).get('http', {}).get('method', event.get('httpMethod', ''))
        
        logger.info(f"Method: {method}, Path: {path}")

        # 2. Route Handling
        if "/merge_pdf" in path:
            return handle_merge_pdf(event)
        
        elif "/create_document" in path:
            return handle_create_document(event)
            
        elif "/get_docids" in path:
            return handle_get_docids(event)

        elif "/update_heading" in path:
            return handle_update_heading(event)

        # Default Health Check
        return response(200, {"status": "healthy", "service": "superdoc-lambda"})

    except Exception as e:
        logger.error(f"Top level error: {str(e)}")
        return response(500, {
            "error": str(e),
            "trace": traceback.format_exc()
        })

def handle_merge_pdf(event):
    """
    Handles multipart/form-data PDF uploads.
    Note: Requires API Gateway/Function URL to be configured for binary media types.
    """
    # In Lambda, binary bodies are usually base64 encoded
    is_base64 = event.get('isBase64Encoded', False)
    body = event.get('body', '')
    
    if is_base64:
        body_bytes = base64.b64decode(body)
    else:
        body_bytes = body.encode('utf-8')

    # Note: Parsing multipart/form-data in Lambda is complex without Flask.
    # For a robust Lambda, it's often easier to send JSON with a base64 string
    # or use a library like 'requests-toolbelt' to parse body_bytes.
    # Here we assume a JSON trigger for simplicity or a direct binary stream.
    
    try:
        # Assuming JSON trigger for Lambda: { "pdf_base64": "...", "course_id": "...", "document_id": "..." }
        data = json.loads(body_bytes)
        pdf_content = base64.b64decode(data['pdf_base64'])
        course_id = data['course_id']
        document_id = data.get('document_id')
    except:
        # Fallback: If it's a raw PDF upload directly as the body
        return response(400, {"error": "Lambda requires JSON with base64 encoded 'pdf_base64' for this handler implementation."})

    pdf_stream = BytesIO(pdf_content)
    
    sd = superdoc(DOCUMENT_ID=document_id, COURSE_ID=course_id, index_name=INDEX_NAME)
    sd.merge_pdf_hierarchical(stream=pdf_stream)
    
    return response(200, {
        "status": "success",
        "document_id": sd.DOCUMENT_ID
    })

def handle_create_document(event):
    data = json.loads(event.get('body', '{}'))
    course_id = data.get('course_id')
    doc_name = data.get('document_name')
    
    docs_editor = GoogleDocsEditor()
    res = docs_editor.create_google_doc(name=doc_name, courseid=course_id)
    
    return response(200, {"document_id": res.get('documentId')})

def handle_get_docids(event):
    data = json.loads(event.get('body', '{}'))
    course_id = data.get('course_id')
    idstore = DocumentIDStore()
    ids = idstore.get_docids(courseid=course_id)
    return response(200, {"ids": ids})

def handle_update_heading(event):
    data = json.loads(event.get('body', '{}'))
    sd = superdoc(
        DOCUMENT_ID=data.get('document_id'), 
        COURSE_ID=data.get('course_id'), 
        index_name=INDEX_NAME
    )
    sd.update_heading(old_heading=data['old_heading'], new_heading=data['new_heading'])
    return response(200, {"status": "updated"})

def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body)
    }