# app/main.py
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.models import ReviewRequest
from core.services import run_review_service

app = FastAPI(title="Medicatiereview API", version="2.0.0")

# CORS instellen (belangrijk voor je frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Zet dit in productie op je specifieke domein
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "ok", "service": "Medimo Review API"}

@app.post("/api/review")
async def review_endpoint(request: ReviewRequest):
    """
    Start een review proces.
    Input: JSON met {text, source, scope}
    Output: NDJSON stream (status -> progress -> result)
    """
    
    def iter_json():
        # We roepen de service aan
        iterator = run_review_service(request.text, request.source, request.scope)
        
        for item in iterator:
            # Check op errors in de stream
            if item.get("type") == "error":
                # In een stream kunnen we geen HTTP 400 meer gooien als we al begonnen zijn,
                # dus sturen we een error object in de JSON.
                yield json.dumps(item) + "\n"
                break
            
            # Schrijf JSON regel + newline
            yield json.dumps(item) + "\n"

    return StreamingResponse(iter_json(), media_type="application/x-ndjson")

# Handler voor AWS Lambda
handler = Mangum(app)

# run met : uvicorn app.main:app --reload --port 8001