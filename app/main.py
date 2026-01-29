from dotenv import load_dotenv
load_dotenv()

import json
import os
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.models import ReviewRequest
from core.services import run_review_service

API_KEY = os.getenv("MEDICATIEREVIEW_API_KEY")

app = FastAPI(title="Medicatiereview API", version="2.0.0")

# CORS instellen (belangrijk voor je frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In prod liever beperken
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "ok", "service": "Medimo Review API"}

@app.post("/api/review")
async def review_endpoint(
    request: ReviewRequest,
    x_api_key: str = Header(default=None, alias="X-API-Key"),
):
    """
    Start een review proces.
    Input: JSON met {text, source, scope}
    Output: NDJSON stream (status -> progress -> result)
    """

    # Als er een API_KEY is gezet in de env, enforce hem
    if API_KEY:
        if not x_api_key or x_api_key != API_KEY:
            # Liever geen details loggen over wat verwacht werd
            raise HTTPException(status_code=401, detail="Unauthorized")

    def iter_json():
        iterator = run_review_service(request.text, request.source, request.scope, geboortedatum=request.geboortedatum)

        for item in iterator:
            if item.get("type") == "error":
                yield json.dumps(item) + "\n"
                break
            yield json.dumps(item) + "\n"

    return StreamingResponse(iter_json(), media_type="application/x-ndjson")

# Handler voor AWS Lambda
handler = Mangum(app)

# run met : uvicorn app.main:app --reload --port 8001