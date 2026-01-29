# app/models.py
from pydantic import BaseModel, Field
from typing import Literal, Optional

class ReviewRequest(BaseModel):
    text: str = Field(..., description="De ruwe tekstkopie uit het AIS (bijv. Medimo)")

    source: Literal["medimo", "pharmacom"] = Field(
        default="medimo",
        description="Het bronsysteem."
    )

    scope: Literal["afdeling", "patient"] = Field(
        default="afdeling",
        description="Review je 1 patiënt of een hele lijst?"
    )

    # Alleen voor scope="patient" handig (single export mist vaak demografie)
    geboortedatum: Optional[str] = Field(
        default=None,
        description="Override geboortedatum in ISO-formaat YYYY-MM-DD (alleen bij single patient)"
    )

    ignore_age: bool = False