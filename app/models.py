# app/models.py
from pydantic import BaseModel, Field
from typing import Literal, Optional

class ReviewRequest(BaseModel):
    text: str = Field(..., description="De ruwe tekstkopie uit het AIS (bijv. Medimo)")
    
    source: Literal["medimo"] = Field(
        default="medimo", 
        description="Het bronsysteem. Voorlopig alleen 'medimo' ondersteund."
    )
    
    scope: Literal["afdeling", "patient"] = Field(
        default="afdeling", 
        description="Review je 1 patiënt of een hele lijst? (Invloed op parsing logica)"
    )

    # Optioneel: als je later specifieke instellingen wilt doorgeven (bijv. leeftijd negeren)
    ignore_age: bool = False