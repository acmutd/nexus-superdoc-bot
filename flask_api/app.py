from flask import Flask, request, jsonify
from superdoc.superdoc import superdoc
from googledoc.googledoc import DocumentIDStore
from io import BytesIO

import os
import sys
import tempfile
import traceback
import logging

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging to output to stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True  # Override any existing configuration
)

# Configure Flask's logger
app = Flask(__name__)
app.logger.setLevel(logging.INFO)
app.logger.handlers = []  # Clear existing handlers
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
app.logger.addHandler(handler)

INDEX_NAME = 'sdtest1'

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

@app.route('/merge_pdf', methods=['POST'])
def merge_pdf():
    """
    Merge PDF into the document.
    Expects multipart/form-data with:
    - pdf_file (required): PDF file to merge
    - course_id (required): Course ID (as form field)
    - document_id (optional): Google Docs document ID. If not provided, a new document will be created.
    - index_name (optional): Pinecone index name (defaults to 'sdtest1')
    """
    try:
        # 1. Handle Multipart (Local/Standard)
        if 'pdf_file' in request.files:
            pdf_file = request.files['pdf_file']
            pdf_bytes = pdf_file.read()
        
        # 2. Handle Base64 (Common in Lambda/API Gateway triggers)
        else:
            data = request.get_json()
            if data and 'pdf_base64' in data:
                pdf_bytes = base64.b64decode(data['pdf_base64'])
            else:
                return jsonify({"error": "No PDF data found"}), 400

        # ... rest of your logic using BytesIO(pdf_bytes) ...
        document_id = request.form.get('document_id', None)
        course_id = request.form.get('course_id', None)
        index_name = INDEX_NAME 
        pdf_stream = BytesIO(pdf_bytes)
        sd = superdoc(DOCUMENT_ID=document_id, COURSE_ID=course_id, index_name=INDEX_NAME)
        sd.merge_pdf_hierarchical(stream=pdf_stream)

        return jsonify({"status": "success", "document_id": sd.DOCUMENT_ID}), 200
    except Exception as e:
        app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/delete_heading', methods=['DELETE'])
def delete_heading():
    """
    Delete a heading from the document.
    Expects JSON body with:
    - course_id (required): Course ID
    - old_heading (required): Name of the heading to delete
    - document_id (optional): Google Docs document ID. If not provided, a new document will be created.
    - index_name (optional): Pinecone index name (defaults to 'sdtest1')
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        if 'course_id' not in data:
            return jsonify({"error": "course_id is required"}), 400
        
        if 'old_heading' not in data:
            return jsonify({"error": "old_heading is required"}), 400
        
        course_id = data['course_id']
        old_heading = data['old_heading']
        document_id = data.get('document_id', None)
        index_name = INDEX_NAME
        
        # Initialize superdoc instance
        sd = superdoc(DOCUMENT_ID=document_id, COURSE_ID=course_id, index_name=index_name)
        
        # Call delete_heading method
        sd.delete_heading(old_heading=old_heading)
        
        return jsonify({
            "status": "success",
            "message": f"Heading '{old_heading}' deleted successfully",
            "document_id": sd.DOCUMENT_ID
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/create_heading', methods=['POST'])
def create_heading():
    """
    Create a new heading in the document.
    Expects JSON body with:
    - course_id (required): Course ID
    - new_heading (required): Name of the new heading to create
    - document_id (optional): Google Docs document ID. If not provided, a new document will be created.
    - index_name (optional): Pinecone index name (defaults to 'sdtest1')
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        if 'course_id' not in data:
            return jsonify({"error": "course_id is required"}), 400
        
        if 'new_heading' not in data:
            return jsonify({"error": "new_heading is required"}), 400
        
        course_id = data['course_id']
        new_heading = data['new_heading']
        document_id = data.get('document_id', None)
        index_name = INDEX_NAME
        
        # Initialize superdoc instance
        sd = superdoc(DOCUMENT_ID=document_id, COURSE_ID=course_id, index_name=index_name)
        
        # Call create_heading method
        sd.create_heading(new_heading=new_heading)
        
        return jsonify({
            "status": "success",
            "message": f"Heading '{new_heading}' created successfully",
            "document_id": sd.DOCUMENT_ID
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/update_heading', methods=['PUT', 'PATCH'])
def update_heading():
    """
    Update a heading in the document.
    Expects JSON body with:
    - course_id (required): Course ID
    - old_heading (required): Current name of the heading
    - new_heading (required): New name for the heading
    - document_id (optional): Google Docs document ID. If not provided, a new document will be created.
    - index_name (optional): Pinecone index name (defaults to 'sdtest1')
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        if 'course_id' not in data:
            return jsonify({"error": "course_id is required"}), 400
        
        if 'old_heading' not in data:
            return jsonify({"error": "old_heading is required"}), 400
        
        if 'new_heading' not in data:
            return jsonify({"error": "new_heading is required"}), 400
        
        course_id = data['course_id']
        old_heading = data['old_heading']
        new_heading = data['new_heading']
        document_id = data.get('document_id', None)
        index_name = INDEX_NAME
        
        # Initialize superdoc instance
        sd = superdoc(DOCUMENT_ID=document_id, COURSE_ID=course_id, index_name=index_name)
        
        # Call update_heading method
        sd.update_heading(old_heading=old_heading, new_heading=new_heading)
        
        return jsonify({
            "status": "success",
            "message": f"Heading '{old_heading}' updated to '{new_heading}' successfully",
            "document_id": sd.DOCUMENT_ID
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_docids', methods=['PUT','POST', 'PATCH'])
def get_docids():
    """
    Get document IDs for a course.
    Expects JSON body with:
    - course_id (required): Course ID
    - index_name (optional): Pinecone index name (defaults to 'sdtest1')
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        if 'course_id' not in data:
            return jsonify({"error": "course_id is required"}), 400
        
        course_id = data['course_id']
        index_name = INDEX_NAME
        idstore = DocumentIDStore()
        # Initialize idstore instance
        ids = idstore.get_docids(courseid=course_id)
        
        
        return jsonify({
            "status": "success",
            "message": f"Retrieved {len(ids) if ids else 0} from {course_id}",
            "ids": ids
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/create_document', methods=['POST'])
def create_document():
    """
    Create a new document.
    Expects JSON body with:
    - course_id (required): Course ID
    - document_name (required): Name of the document to create
    - index_name (optional): Pinecone index name (defaults to 'sdtest1')
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        if 'course_id' not in data:
            return jsonify({"error": "course_id is required"}), 400
        
        if 'document_name' not in data:
            return jsonify({"error": "document_name is required"}), 400
        
        course_id = data['course_id']
        document_name = data['document_name']
        index_name = INDEX_NAME
        
        # Create document using GoogleDocsEditor
        from googledoc.googledoc import GoogleDocsEditor
        docs_editor = GoogleDocsEditor()
        response = docs_editor.create_google_doc(name=document_name, courseid=course_id)
        
        if response is None:
            return jsonify({"error": "Failed to create document"}), 500
        
        document_id = response.get('documentId')
        
        return jsonify({
            "status": "success",
            "message": f"Document '{document_name}' created successfully",
            "document_id": document_id
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting Flask server on http://0.0.0.0:5000", flush=True)
    app.logger.info("Flask server starting...")
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)

