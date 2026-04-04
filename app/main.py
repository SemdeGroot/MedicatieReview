from dotenv import load_dotenv
load_dotenv()

import json
import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.models import ReviewRequest
from core.services import run_review_service, run_review_service_pdf

API_KEY = os.getenv("MEDICATIEREVIEW_API_KEY")

app = FastAPI(title="Medicatiereview API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _check_api_key(x_api_key: str):
    if API_KEY:
        if not x_api_key or x_api_key != API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/")
def read_root():
    return {"status": "ok", "service": "Medimo Review API"}


@app.post("/api/review")
async def review_endpoint(
    request: ReviewRequest,
    x_api_key: str = Header(default=None, alias="X-API-Key"),
):
    """
    Start een review proces (tekst-input).
    Input: JSON met {text, source, scope}
    Output: NDJSON stream
    """
    _check_api_key(x_api_key)

    def iter_json():
        iterator = run_review_service(request.text, request.source, request.scope, geboortedatum=request.geboortedatum)
        for item in iterator:
            if item.get("type") == "error":
                yield json.dumps(item) + "\n"
                break
            yield json.dumps(item) + "\n"

    return StreamingResponse(iter_json(), media_type="application/x-ndjson")


@app.post("/api/review/upload")
async def review_upload_endpoint(
    file: UploadFile = File(...),
    source: str = Form("pharmacom"),
    scope: str = Form("patient"),
    geboortedatum: Optional[str] = Form(None),
    x_api_key: str = Header(default=None, alias="X-API-Key"),
):
    """
    Start een review proces via PDF-upload (Pharmacom).
    Input: multipart/form-data met file + source + scope
    Output: NDJSON stream
    """
    _check_api_key(x_api_key)

    if source != "pharmacom":
        raise HTTPException(status_code=400, detail="Upload wordt alleen ondersteund voor Pharmacom.")
    if scope != "patient":
        raise HTTPException(status_code=400, detail="Pharmacom ondersteunt alleen scope='patient'.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Leeg bestand ontvangen.")

    def iter_json():
        iterator = run_review_service_pdf(file_bytes, source, scope, geboortedatum=geboortedatum)
        for item in iterator:
            if item.get("type") == "error":
                yield json.dumps(item) + "\n"
                break
            yield json.dumps(item) + "\n"

    return StreamingResponse(iter_json(), media_type="application/x-ndjson")


# Handler voor AWS Lambda
handler = Mangum(app)

# run met : uvicorn app.main:app --reload --port 8001
