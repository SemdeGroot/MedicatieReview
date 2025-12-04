from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json

# Importeer de generator functie
from core.parsers.parse_medimo_afdeling import process_medimo_text_stream

app = FastAPI()

class MedimoInput(BaseModel):
    text: str

@app.post("/api/analyze/stream")
def analyze_stream(payload: MedimoInput):
    """
    Geeft een stream terug van JSON objecten.
    Client leest regel voor regel.
    """
    
    def event_generator():
        # Roep de generator aan in de parser
        iterator = process_medimo_text_stream(payload.text)
        
        for item in iterator:
            # Schrijf elke update als een JSON-regel + newline
            yield json.dumps(item) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")