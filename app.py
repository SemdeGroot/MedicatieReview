import os
import io
import time
import uuid
import json
import shutil
import traceback
from typing import Dict, Optional

from flask import Flask, request, send_file, jsonify, render_template

# -------------------------------------------------
# Config
# -------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR     = os.path.join(PROJECT_ROOT, "Data")
RUNS_ROOT    = os.path.join(DATA_DIR, "Temp")      # per-run submappen: Data/Temp/<run_id>/
SECRET_KEY   = os.environ.get("FLASK_SECRET", "change-me-in-production")

# Import main (die paden accepteert)
import importlib
main_mod = importlib.import_module("main")

# Flask
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = SECRET_KEY


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def _ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(RUNS_ROOT, exist_ok=True)

def _run_paths(run_id: str) -> Dict[str, str]:
    base = os.path.join(RUNS_ROOT, run_id)
    return {
        "run_dir": base,
        "input_path": os.path.join(base, "input.txt"),
        "progress_path": os.path.join(base, "progress.json"),
        "cancel_path": os.path.join(base, "cancel.flag"),
    }

def _safe_rmtree(path: str):
    if not os.path.isdir(path):
        return
    for _ in range(5):
        try:
            shutil.rmtree(path)
            return
        except Exception:
            time.sleep(0.1)
    shutil.rmtree(path, ignore_errors=True)

def _require_run_id() -> Optional[str]:
    rid = request.args.get("run_id")
    if not rid:
        # ook body accepteren
        try:
            j = request.get_json(silent=True) or {}
            rid = j.get("run_id")
        except Exception:
            rid = None
    return rid

# -------------------------------------------------
# Routes
# -------------------------------------------------

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/api/run")
def api_run():
    """
    - Vereist run_id (meegegeven door de client) en medimo_text
    - Maakt per-run map
    - Schrijft input.txt
    - Draait main.main(...) met per-run paden
    - Stuurt .docx uit geheugen terug
    - Verwijdert run-map (geen dataretentie)
    """
    try:
        j = request.get_json(force=True, silent=False) or {}
        run_id = j.get("run_id")
        medimo_text = (j.get("medimo_text") or "").strip()
        if not run_id:
            return jsonify({"detail": "run_id ontbreekt"}), 400
        if not medimo_text:
            return jsonify({"detail": "Geen medimo_text aangeleverd."}), 400

        _ensure_dirs()
        p = _run_paths(run_id)
        os.makedirs(p["run_dir"], exist_ok=True)

        # input schrijven
        with open(p["input_path"], "w", encoding="utf-8") as f:
            f.write(medimo_text)

        # run (synchronisch)
        main_mod.main(
            input_path=p["input_path"],
            output_dir=p["run_dir"],          # Word komt in deze map (met afdelingsnaam in bestandsnaam)
            progress_path=p["progress_path"], # parse_medimo schrijft hierin
            cancel_flag_path=p["cancel_path"]
        )

        # zoek .docx in run-dir
        docxs = [os.path.join(p["run_dir"], q) for q in os.listdir(p["run_dir"]) if q.lower().endswith(".docx")]
        if not docxs:
            _safe_rmtree(p["run_dir"])
            return jsonify({"detail": "Geen .docx-output gevonden."}), 500

        result_path = max(docxs, key=os.path.getmtime)
        filename = os.path.basename(result_path)

        # uit geheugen sturen
        with open(result_path, "rb") as f:
            data = f.read()

        # cleanup na succesvolle run
        _safe_rmtree(p["run_dir"])

        bio = io.BytesIO(data); bio.seek(0)
        resp = send_file(
            bio,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=filename,
            max_age=0
        )
        resp.headers["Cache-Control"] = "no-store, max-age=0"
        return resp

    except Exception as e:
        traceback.print_exc()
        # opruimen bij error
        rid = _require_run_id()
        if rid:
            _safe_rmtree(_run_paths(rid)["run_dir"])
        return jsonify({"detail": f"Fout tijdens verwerken: {e}"}), 500


@app.get("/api/progress")
def api_progress():
    """
    Leest expliciet Data/Temp/<run_id>/progress.json (run_id verplicht).
    Geen fallback meer → multi-user safe.
    """
    run_id = _require_run_id()
    if not run_id:
        return jsonify({"detail": "run_id ontbreekt"}), 400
    p = _run_paths(run_id)
    progress_path = p["progress_path"]
    if os.path.exists(progress_path):
        resp = send_file(progress_path, mimetype="application/json")
        resp.headers["Cache-Control"] = "no-store, max-age=0"
        return resp
    return jsonify({"detail": "Nog geen progress of al afgerond."}), 404


@app.post("/api/cancel")
def api_cancel():
    """
    Zet cancel voor de opgegeven run_id.
    Als er geen progress.json (meer) is, ruimen we de map meteen op (idempotent schoonmaken).
    """
    run_id = _require_run_id()
    if not run_id:
        return jsonify({"ok": True, "running": False})
    p = _run_paths(run_id)
    try:
        os.makedirs(p["run_dir"], exist_ok=True)
        # Als er geen progress is, is er waarschijnlijk niets actief → schoonmaken en klaar
        if not os.path.exists(p["progress_path"]):
            _safe_rmtree(p["run_dir"])
            return jsonify({"ok": True, "running": False, "cleaned": True})
        # Anders: cancel-flag zetten en de parser laat de map later verdwijnen
        with open(p["cancel_path"], "w", encoding="utf-8") as f:
            f.write("cancel")
        return jsonify({"ok": True, "running": True})
    except Exception as e:
        return jsonify({"ok": False, "detail": str(e)}), 500


@app.post("/api/clear")
def api_clear():
    """
    Forceer directe opruiming van Data/Temp/<run_id>/.
    Handig voor jouw 'Leegmaken' knop – idempotent.
    """
    run_id = _require_run_id()
    if not run_id:
        return jsonify({"ok": True, "cleared": False})
    try:
        _safe_rmtree(_run_paths(run_id)["run_dir"])
        return jsonify({"ok": True, "cleared": True})
    except Exception as e:
        return jsonify({"ok": False, "detail": str(e)}), 500


# -------------------------------------------------
# Entrypoint
# -------------------------------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)