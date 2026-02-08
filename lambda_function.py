import os
import urllib.request
from io import BytesIO
from fastapi import FastAPI, HTTPException, Body
from mangum import Mangum
from pydantic import BaseModel

from superdoc.superdoc import superdoc

app = FastAPI()
import os
import urllib.request
from io import BytesIO
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Body
from mangum import Mangum
from pydantic import BaseModel

from superdoc.superdoc import superdoc

app = FastAPI(title="SuperDoc API")

# --- Request Models ---

class MergePDFRequest(BaseModel):
    pdfUrl: str
    courseId: str
    documentId: Optional[str] = None
    index_name: str = "sdtest1"

class HeadingOperation(BaseModel):
    courseId: str
    documentId: str
    heading: str  # Used for create/delete
    index_name: str = "sdtest1"

class UpdateHeadingRequest(BaseModel):
    courseId: str
    documentId: str
    oldHeading: str
    newHeading: str
    index_name: str = "sdtest1"

class CreateDocRequest(BaseModel):
    courseId: str
    documentName: str

# --- Endpoints ---

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/merge_pdf")
def handle_merge_pdf(req: MergePDFRequest):
    try:
        with urllib.request.urlopen(req.pdfUrl) as response:
            if response.status != 200:
                raise HTTPException(status_code=400, detail="Failed to download PDF")
            pdf_stream = BytesIO(response.read())
        
        # Initializes superdoc (creates one if documentId is None)
        sd = superdoc(DOCUMENT_ID=req.documentId, COURSE_ID=req.courseId, index_name=req.index_name)
        sd.merge_pdf_hierarchical(stream=pdf_stream)
        
        return {"status": "success", "documentId": sd.DOCUMENT_ID}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/headings/create")
def create_heading(req: HeadingOperation):
    try:
        sd = superdoc(DOCUMENT_ID=req.documentId, COURSE_ID=req.courseId, index_name=req.index_name)
        sd.create_heading(new_heading=req.heading)
        return {"status": "heading created", "documentId": req.documentId}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/headings/delete")
def delete_heading(req: HeadingOperation):
    try:
        sd = superdoc(DOCUMENT_ID=req.documentId, COURSE_ID=req.courseId, index_name=req.index_name)
        sd.delete_heading(old_heading=req.heading)
        return {"status": "heading deleted", "documentId": req.documentId}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/headings/update")
def update_heading(req: UpdateHeadingRequest):
    try:
        sd = superdoc(DOCUMENT_ID=req.documentId, COURSE_ID=req.courseId, index_name=req.index_name)
        sd.update_heading(old_heading=req.oldHeading, new_heading=req.newHeading)
        return {"status": "heading updated", "documentId": req.documentId}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{course_id}")
def get_course_documents(course_id: str):
    try:
        # We initialize with None to use the class helper methods
        sd = superdoc(DOCUMENT_ID="DUMMY", COURSE_ID=course_id)
        ids = sd.get_docids(course_id=course_id)
        return {"courseId": course_id, "documentIds": ids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/create")
def create_new_document(req: CreateDocRequest):
    try:
        # Note: Using the standalone create_document method in the class
        sd = superdoc(DOCUMENT_ID="DUMMY", COURSE_ID=req.courseId)
        doc_map = sd.get_docids(course_id=course_id)
        if doc_map.get(course_id,None):
            raise HTTPException(status_code=400, detail=f"A superdoc with the name {req.documentName} already exists!")
        response = sd.create_document(name=req.documentName, course_id=req.courseId)

        return {"status": "created", "document": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Lambda Handler
handler = Mangum(app)