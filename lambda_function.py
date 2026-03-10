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



# --- Middleware ---
@app.middleware("http")
async def log_requests(request, call_next):
    print(f"Incoming request: {request.method} {request.url.path}")
    response = await call_next(request)
    return response


# --- Endpoints ---

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/merge_pdf")
def handle_merge_pdf(req: MergePDFRequest):
    from superdoc.superdoc import superdoc

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
    from superdoc.superdoc import superdoc

    try:
        sd = superdoc(DOCUMENT_ID=req.documentId, COURSE_ID=req.courseId, index_name=req.index_name)
        sd.create_heading(new_heading=req.heading)
        return {"status": "heading created", "documentId": req.documentId}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/headings/delete")
def delete_heading(req: HeadingOperation):
    from superdoc.superdoc import superdoc

    try:
        sd = superdoc(DOCUMENT_ID=req.documentId, COURSE_ID=req.courseId, index_name=req.index_name)
        sd.delete_heading(old_heading=req.heading)
        return {"status": "heading deleted", "documentId": req.documentId}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/headings/update")
def update_heading(req: UpdateHeadingRequest):
    from superdoc.superdoc import superdoc

    try:
        sd = superdoc(DOCUMENT_ID=req.documentId, COURSE_ID=req.courseId, index_name=req.index_name)
        sd.update_heading(old_heading=req.oldHeading, new_heading=req.newHeading)
        return {"status": "heading updated", "documentId": req.documentId}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{course_id}")
def get_course_documents(course_id: str):
    from superdoc.superdoc import superdoc

    try:
        # We initialize with None to use the class helper methods
        sd = superdoc(DOCUMENT_ID="DUMMY", COURSE_ID=course_id)
        ids = sd.get_docids(course_id=course_id)
        return {"courseId": course_id, "documentIds": ids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/create")
def create_new_document(req: CreateDocRequest):
    from superdoc.superdoc import superdoc

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
handler = Mangum(app, lifespan="off", api_gateway_base_path="/dev")

if __name__ == "__main__":
    import json
    from io import BytesIO
    # We already have 'superdoc' imported at the top of the file
  
    # 1. Configuration for DIRECT test (Bypassing API)
    MY_DOC_ID = '13OiEdtje4wMZGT1LEfVmj3RmAeR1BchUF6eZBaICH8w'
    MY_COURSE_ID = "RHET1302"
    LOCAL_PDF_PATH = "/Users/tharunsevvel/Downloads/Chloroplasts.pdf"


    print(f"\n--- TRIGGERING DIRECT METHOD CALL ---")
    sd = superdoc(DOCUMENT_ID=MY_DOC_ID, COURSE_ID=MY_COURSE_ID)


    if os.path.exists(LOCAL_PDF_PATH):
        with open(LOCAL_PDF_PATH, "rb") as f:
            pdf_bytes = f.read()
        strm = BytesIO(pdf_bytes)


        print("Starting Hierarchical Merge...")
        # We wrap this in a try/except to catch that Pinecone/List error
        try:
            sd.merge_pdf_hierarchical(stream=strm)
            print("Done! Check your Google Doc.")
        except Exception as e:
            print(f"Merge failed: {e}")
            print("Check if reconcile_structure is returning None instead of a list.")

