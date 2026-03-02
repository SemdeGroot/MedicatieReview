import json
import os
from typing import List, Dict, Set, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, "data", "stop-v2.json")

_CRITERIA_CACHE: List[Dict] = []


def _load_data() -> None:
    global _CRITERIA_CACHE
    if _CRITERIA_CACHE or not os.path.exists(JSON_PATH):
        return
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            _CRITERIA_CACHE = json.load(f).get("criteria", [])
    except Exception as e:
        print(f"Error loading stop-v2.json: {e}")
        _CRITERIA_CACHE = []


_load_data()


def _build_atc_index(medicatielijst: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    """
    Returns a dict mapping every ATC prefix/code (upper) to the set of
    medication names that carry it. Covers ATC3 through ATC7/full.
    """
    index: Dict[str, Set[str]] = {}

    def _add(code: Optional[str], name: str) -> None:
        if not code:
            return
        key = code.strip().upper()
        index.setdefault(key, set()).add(name)

    for med in medicatielijst:
        name = (med.get("clean") or "").strip() or "Onbekend middel"
        full = med.get("ATC") or med.get("ATC7")
        _add(full, name)
        _add(med.get("ATC5"), name)
        _add(med.get("ATC4"), name)
        _add(med.get("ATC3"), name)

    return index


def _meds_for_atc_token(token: str, index: Dict[str, Set[str]]) -> Set[str]:
    """
    Match a criterion ATC token against the patient index.
    The patient's stored code must start with the criterion token,
    meaning the criterion is at the same level or higher (broader) than
    the patient's code. Never the reverse: criterion "N05AE" must not
    match a patient code "N05A".
    """
    t = token.strip().upper()
    result: Set[str] = set()
    for stored_code, names in index.items():
        if stored_code.startswith(t):
            result |= names
    return result

def check_stopp_criteria(
    medicatielijst: List[Dict[str, Any]],
    leeftijd: int = 75,
) -> List[Dict[str, Any]]:
    """
    Checks STOP-NL V2 criteria against a patient medication list.

    Args:
        medicatielijst: Parsed medication list; each entry must have at least
                        one of: ATC, ATC7, ATC5, ATC4, ATC3, and 'clean'.
        leeftijd:       Patient age (unused by v2 criteria, kept for API
                        compatibility with services.py).

    Returns:
        List of triggered criteria dicts with keys:
        id, category, description, argument, triggering_medicines.
    """
    if not _CRITERIA_CACHE:
        _load_data()
    if not _CRITERIA_CACHE:
        return []

    atc_index = _build_atc_index(medicatielijst)
    triggered: List[Dict[str, Any]] = []

    for criterion in _CRITERIA_CACHE:
        atc_codes: List[str] = criterion.get("ATC_codes", [])

        # Criteria A1-A4 and others with no ATC codes cannot be matched
        # automatically against a medication list; skip them.
        if not atc_codes:
            continue

        matched_meds: Set[str] = set()
        for token in atc_codes:
            matched_meds |= _meds_for_atc_token(token, atc_index)

        if matched_meds:
            triggered.append({
                "id": criterion.get("id", ""),
                "category": criterion.get("category", ""),
                "description": criterion.get("description", ""),
                "argument": criterion.get("argument", ""),
                "triggering_medicines": ", ".join(sorted(matched_meds, key=str.lower)),
            })

    return triggered