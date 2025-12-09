# check_standaardvragen.py

import json
import os
from typing import List, Dict, Set, Any, Optional

import boto3

# ==============================================================================
# 1. CONFIGURATIE & GLOBAL DATA (S3 + CACHE)
# ==============================================================================

S3_BUCKET = os.environ.get("AWS_STORAGE_BUCKET_NAME")
S3_KEY = "config/vragen.json"

s3 = boto3.client("s3")

# Cache variabelen (blijven bestaan in warme Lambda container)
VRAGEN_CACHE: List[Dict[str, Any]] = []
VRAGEN_ETAG: Optional[str] = None


def _refresh_vragen_from_s3_if_needed() -> None:
    """
    Checkt de ETag van vragen.json in S3.
    - Als ETag nieuw is (of cache leeg) -> opnieuw laden.
    - Als ETag gelijk is -> cache laten staan.
    """
    global VRAGEN_CACHE, VRAGEN_ETAG

    if not S3_BUCKET:
        print("❌ S3_BUCKET (AWS_STORAGE_BUCKET_NAME) niet gezet in env")
        return

    try:
        # 1. Huidige ETag opvragen
        head = s3.head_object(Bucket=S3_BUCKET, Key=S3_KEY)
        current_etag = head["ETag"].strip('"')

        # 2. Als niets veranderd is en we hebben al data, dan klaar
        if VRAGEN_CACHE and VRAGEN_ETAG == current_etag:
            return

        # 3. Veranderd of nog nooit geladen -> object ophalen
        obj = s3.get_object(Bucket=S3_BUCKET, Key=S3_KEY)
        body = obj["Body"].read().decode("utf-8")
        data = json.loads(body)

        VRAGEN_CACHE = data.get("criteria", [])
        VRAGEN_ETAG = current_etag
        print(f"✅ Loaded {len(VRAGEN_CACHE)} standaardvragen uit S3 (ETag={VRAGEN_ETAG})")

    except Exception as e:
        # In productie wellicht loggen naar CloudWatch / Sentry
        print(f"❌ Error loading vragen.json from S3: {e}")
        # Oude cache (indien aanwezig) laten staan

# ==============================================================================
# 2. HULPFUNCTIES VOOR ATC-MAPPINGS
# ==============================================================================

def _add(dct: Dict[str, Set[str]], key: Optional[str], name: str) -> None:
    """Voegt een middelnaam toe aan de juiste ATC-map."""
    if not key:
        return
    k = str(key).strip().upper()
    if not k:
        return
    dct.setdefault(k, set()).add(name)


def _build_atc_indices(medicatielijst: List[Dict[str, Any]]) -> Dict[str, Dict[str, Set[str]]]:
    """
    Bouwt verschillende indices:
    - atc7: volledige ATC-code
    - atc5, atc4, atc3: groepsniveaus

    Returnt een dict met:
    {
        "atc7": {...},
        "atc5": {...},
        "atc4": {...},
        "atc3": {...},
    }
    """
    meds_by_atc7: Dict[str, Set[str]] = {}
    meds_by_atc5: Dict[str, Set[str]] = {}
    meds_by_atc4: Dict[str, Set[str]] = {}
    meds_by_atc3: Dict[str, Set[str]] = {}

    for gm in medicatielijst:
        # Naam van het middel
        name = (gm.get("clean") or gm.get("name") or "").strip() or "Onbekend middel"

        # ATC-codes verzamelen (gebruik wat er is)
        atc_full = gm.get("ATC") or gm.get("ATC7") or gm.get("atc") or gm.get("atc7")
        atc5 = gm.get("ATC5") or gm.get("atc5")
        atc4 = gm.get("ATC4") or gm.get("atc4")
        atc3 = gm.get("ATC3") or gm.get("atc3")

        _add(meds_by_atc7, atc_full, name)
        _add(meds_by_atc5, atc5, name)
        _add(meds_by_atc4, atc4, name)
        _add(meds_by_atc3, atc3, name)

    return {
        "atc7": meds_by_atc7,
        "atc5": meds_by_atc5,
        "atc4": meds_by_atc4,
        "atc3": meds_by_atc3,
    }


def _meds_for_substance_token(token: str, idx: Dict[str, Dict[str, Set[str]]]) -> Set[str]:
    """Exacte ATC7 match."""
    return idx["atc7"].get(str(token).strip().upper(), set())


def _meds_for_group_token(token: str, idx: Dict[str, Dict[str, Set[str]]]) -> Set[str]:
    """
    Groepsmatches: probeer ATC5 -> ATC4 -> ATC3.
    Alleen exact op die code (we gaan ervan uit dat de juiste keys al opgebouwd zijn).
    """
    t = str(token).strip().upper()
    if t in idx["atc5"]:
        return idx["atc5"][t]
    if t in idx["atc4"]:
        return idx["atc4"][t]
    if t in idx["atc3"]:
        return idx["atc3"][t]
    return set()


def _meds_for_any_token(token: str, idx: Dict[str, Dict[str, Set[str]]]) -> Set[str]:
    """
    Combineert substance- en group-match.
    """
    return _meds_for_substance_token(token, idx) | _meds_for_group_token(token, idx)


# ==============================================================================
# 3. HOOFDFUNCTIE: CHECK_STANDAARDVRAGEN
# ==============================================================================

def check_standaardvragen(
    medicatielijst: List[Dict[str, Any]],
    leeftijd: int = 75
) -> List[Dict[str, Any]]:
    """
    Controleert standaardvragen op basis van ATC-codes.

    Nieuwe JSON-structuur:

    {
      "criteria": [
        {
          "definition": {
            "id": "...",
            "title": "...",
            "category_atc_code": "A",
            "subcategory_atc_code": "A02",
            "description": "Vraagtekst..."
          },
          "activation": {
            "primary_triggers": ["A02BC", ...]
          },
          "logic_rules": [
            {
              "type": "ATC",
              "boolean_operator": "AND" | "AND_NOT",
              "trigger_codes": ["M01A", ...]
            },
            ...
          ],
          "filters": {
            "age_min": 70,
            "egfr_max": null
          }
        },
        ...
      ]
    }

    Logica:
    - Trigger als:
      - Minstens één primary_trigger aanwezig is (OR binnen die lijst), én
      - Alle AND-regels waar zijn (per AND: OR binnen trigger_codes), én
      - Alle AND_NOT-regels waar zijn (geen van de codes aanwezig, OR binnen trigger_codes)
      - Filters (bv. leeftijd) zijn voldaan.

    Output (zelfde keys als oude versie):
    [
      {
        "id": ...,
        "categorie": ...,
        "subcategorie": ...,
        "vraag": ...,
        "toelichting": ...,
        "betrokken_middelen": "middel1, middel2, ..."
      },
      ...
    ]
    """

    # ETag check + eventueel S3 opnieuw lezen
    _refresh_vragen_from_s3_if_needed()
    if not VRAGEN_CACHE:
        return []

    # ATC-indexen opbouwen voor snelle lookup
    idx = _build_atc_indices(medicatielijst)

    triggered_vragen: List[Dict[str, Any]] = []

    for crit in VRAGEN_CACHE:
        definition = crit.get("definition", {}) or {}
        activation = crit.get("activation", {}) or {}
        logic_rules = crit.get("logic_rules", []) or []
        filters = crit.get("filters", {}) or {}

        # ------------------------------
        # 1. Leeftijdsfilter
        # ------------------------------
        age_min = filters.get("age_min")
        if isinstance(age_min, (int, float)) and leeftijd < int(age_min):
            continue

        # (egfr_max kun je hier later eventueel toevoegen als extra arg in de functie)

        # ------------------------------
        # 2. Primary triggers (OR binnen lijst)
        # ------------------------------
        primary_triggers = activation.get("primary_triggers", []) or []
        if not primary_triggers:
            # Geen primary triggers = geen vraag (volgens jouw definitie)
            continue

        primary_meds: Set[str] = set()
        for code in primary_triggers:
            primary_meds |= _meds_for_any_token(code, idx)

        # Als geen enkele primary trigger matcht, dan deze vraag niet tonen
        if not primary_meds:
            continue

        # We gebruiken matched_meds om alle middelen te verzamelen die relevant zijn
        matched_meds: Set[str] = set(primary_meds)

        # ------------------------------
        # 3. Logica regels (AND / AND_NOT)
        # ------------------------------
        all_rules_ok = True

        for rule in logic_rules:
            if (rule.get("type") or "").upper() != "ATC":
                # Voor nu negeren we andere types; je kunt hier later op uitbreiden
                continue

            operator = (rule.get("boolean_operator") or "AND").upper()
            codes = rule.get("trigger_codes", []) or []

            # Verzamel alle middelen die door deze regel geraakt worden
            rule_meds: Set[str] = set()
            for code in codes:
                rule_meds |= _meds_for_any_token(code, idx)

            if operator == "AND":
                # AND-regel:
                # - Als er GEEN codes zijn -> altijd True (placeholder)
                # - Als er wel codes zijn -> minstens één hit nodig (OR binnen lijst)
                if codes and not rule_meds:
                    all_rules_ok = False
                    break
                # Toevoegen aan matched_meds (dit zijn juist middelen die de vraag ondersteunen)
                matched_meds |= rule_meds

            elif operator == "AND_NOT":
                # AND_NOT-regel:
                # - Als er GEEN codes zijn -> altijd True
                # - Als er wel codes zijn -> GEEN enkele mag aanwezig zijn
                if rule_meds:
                    # Er is toch een middel dat in deze AND_NOT-lijst valt -> vraag NIET tonen
                    all_rules_ok = False
                    break

            else:
                # Onbekende operator -> voor nu overslaan of als False behandelen.
                # Ik kies overslaan (veiligste als je later nieuwe operators toevoegt).
                continue

        if not all_rules_ok:
            continue

        if not matched_meds:
            # In theorie kan dit niet gebeuren (primary_meds stond er al in),
            # maar een extra guard kan geen kwaad.
            continue

        # ------------------------------
        # 4. Resultaat samenstellen
        # ------------------------------
        meds_list = sorted(matched_meds, key=str.lower)
        trigger_txt = ", ".join(meds_list)

        triggered_vragen.append({
            "id": definition.get("id", ""),
            # categorie/subcategorie uit je nieuwe JSON
            "categorie": definition.get("category_atc_code", ""),
            "subcategorie": definition.get("subcategory_atc_code", ""),
            # vraag = description (zoals je aangaf)
            "vraag": definition.get("description", ""),
            # toelichting: ik gebruik hier de title (kun je aanpassen naar wens)
            "toelichting": definition.get("title", ""),
            "betrokken_middelen": trigger_txt,
        })

    return triggered_vragen