# test_dev/test_standaardvragen.py
import sys
import os
from pprint import pprint

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

# 👇 PAS DIT AAN NAAR JOUW ECHTE MODULEPAD
import core.analyses.standaardvragen.check_standaardvragen as csv_mod

# -------------------------------------------------------
# 1. Dummy criteria (jouw JSON, maar dan als Python dict)
# -------------------------------------------------------

DUMMY_CRITERIA = [
    {
        "definition": {
            "id": "1765273378663",
            "title": "Maagzuurremmer NSAID",
            "category_atc_code": "A",
            "subcategory_atc_code": "A02",
            "description": (
                "Is de maagzuurremmer nog geindiceerd? "
                "de patient gebruikt geen NSAID >70 jaar."
            ),
        },
        "activation": {
            "primary_triggers": ["A02BC"],  # maagzuurremmer
        },
        "logic_rules": [
            {
                "type": "ATC",
                "boolean_operator": "AND",
                "trigger_codes": [],  # placeholder
            },
            {
                "type": "ATC",
                "boolean_operator": "AND_NOT",
                "trigger_codes": ["M01A"],  # NSAID
            },
        ],
        "filters": {
            "age_min": 70,
            "egfr_max": None,
        },
    },
    {
        "definition": {
            "id": "1765273581965",
            "title": "Maagzuurremmer TAR",
            "category_atc_code": "A",
            "subcategory_atc_code": "A02",
            "description": (
                "Is de maagzuurremmer nog geindiceerd? "
                "de patient gebruikt geen TAR >80 jaar"
            ),
        },
        "activation": {
            "primary_triggers": ["A02BC"],  # maagzuurremmer
        },
        "logic_rules": [
            {
                "type": "ATC",
                "boolean_operator": "AND",
                "trigger_codes": [],  # placeholder
            },
            {
                "type": "ATC",
                "boolean_operator": "AND_NOT",
                "trigger_codes": ["B01AC"],  # TAR
            },
        ],
        "filters": {
            "age_min": 80,
            "egfr_max": None,
        },
    },
]

# -------------------------------------------------------
# 2. Test-setup: S3 uitzetten en cache vullen
# -------------------------------------------------------

def setup_dummy_config():
    """
    Zet de module in 'offline test mode':
    - Geen S3-bucket gebruiken.
    - VRAGEN_CACHE vullen met DUMMY_CRITERIA.
    - _refresh_vragen_from_s3_if_needed overschrijven naar een no-op.
    """
    # Zorg dat eventuele S3 env var niet in de weg zit
    os.environ.pop("AWS_STORAGE_BUCKET_NAME", None)

    # Cache direct vullen met onze dummy criteria
    csv_mod.VRAGEN_CACHE = DUMMY_CRITERIA
    csv_mod.VRAGEN_ETAG = "dummy-etag"

    # Refresh-functie vervangen zodat hij niet naar S3 gaat
    def _fake_refresh():
        # doet niets, gebruikt alleen de bestaande VRAGEN_CACHE
        return None

    csv_mod._refresh_vragen_from_s3_if_needed = _fake_refresh


# -------------------------------------------------------
# 3. Dummy medicatielijsten om logica te testen
# -------------------------------------------------------

def case_1_maagzuurremmer_geen_nsaid():
    """
    Verwacht:
    - Eerste vraag (NSAID) triggert (age >= 70, wel maagzuurremmer, geen M01A)
    - Tweede vraag triggert alleen als leeftijd >= 80
    """
    medicatielijst = [
        {
            "clean": "omeprazol",
            "ATC": "A02BC",  # maagzuurremmer
            "ATC3": "A02",
        },
    ]
    print("\n=== CASE 1: maagzuurremmer, GEEN NSAID/TAR, leeftijd 82 ===")
    res = csv_mod.check_standaardvragen(medicatielijst, leeftijd=82)
    pprint(res)


def case_2_maagzuurremmer_met_nsaid():
    """
    Verwacht:
    - Eerste vraag mag NIET triggeren (want M01A aanwezig)
    - Tweede vraag kan nog wel triggeren (TAR niet aanwezig)
    """
    medicatielijst = [
        {
            "clean": "omeprazol",
            "ATC": "A02BC",
            "ATC3": "A02",
        },
        {
            "clean": "diclofenac",
            "ATC": "M01AB",  # valt onder M01A (NSAID)
            "ATC3": "M01",
        },
    ]
    print("\n=== CASE 2: maagzuurremmer + NSAID, leeftijd 82 ===")
    res = csv_mod.check_standaardvragen(medicatielijst, leeftijd=82)
    pprint(res)


def case_3_maagzuurremmer_geen_tar():
    """
    Specifiek kijken naar TAR-regel (B01AC).
    Verwacht:
    - Tweede vraag triggert als leeftijd >= 80 en geen B01AC.
    """
    medicatielijst = [
        {
            "clean": "omeprazol",
            "ATC": "A02BC",
            "ATC3": "A02",
        },
    ]
    print("\n=== CASE 3: maagzuurremmer, GEEN TAR, leeftijd 85 ===")
    res = csv_mod.check_standaardvragen(medicatielijst, leeftijd=85)
    pprint(res)


def case_4_maagzuurremmer_met_tar():
    """
    - Tweede vraag mag NIET triggeren (want B01AC aanwezig).
    """
    medicatielijst = [
        {
            "clean": "omeprazol",
            "ATC": "A02BC",
            "ATC3": "A02",
        },
        {
            "clean": "apixaban",
            "ATC": "B01AC",  # TAR
            "ATC3": "B01",
        },
    ]
    print("\n=== CASE 4: maagzuurremmer + TAR, leeftijd 85 ===")
    res = csv_mod.check_standaardvragen(medicatielijst, leeftijd=85)
    pprint(res)


# -------------------------------------------------------
# 4. Main
# -------------------------------------------------------

if __name__ == "__main__":
    setup_dummy_config()

    case_1_maagzuurremmer_geen_nsaid()
    case_2_maagzuurremmer_met_nsaid()
    case_3_maagzuurremmer_geen_tar()
    case_4_maagzuurremmer_met_tar()
