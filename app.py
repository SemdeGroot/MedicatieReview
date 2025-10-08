import os
import io
import time
import uuid
import json
import shutil
import traceback
from typing import Dict, Optional

from flask import Flask, request, send_file, jsonify, render_template_string

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
app = Flask(__name__, static_folder="Data", static_url_path="/static")
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
# Frontend (moderne dark UI)
# -------------------------------------------------
HTML_PAGE = r"""<!doctype html>
<html lang="nl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Medicatiebeoordeling Voorbereider</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root{
      --bg-primary: #0f0f17;
      --bg-secondary: #1a1a26;
      --bg-tertiary: #252532;
      --bg-accent: #2d2d3f;
      --blue-primary: #1d4ed8;
      --blue-secondary: #1e3a8a;
      --blue-tertiary: #0f172a;
      --blue-soft: #1e293b;
      --blue-glow: rgba(29, 78, 216, 0.15);
      --text-primary: #f8fafc;
      --text-secondary: #cbd5e1;
      --text-muted: #94a3b8;
      --text-accent: #e0e7ff;
      --success: #10b981;
      --success-bg: rgba(16, 185, 129, 0.1);
      --error: #ef4444;
      --error-bg: rgba(239, 68, 68, 0.1);
      --info: #1d4ed8;
      --info-bg: rgba(29, 78, 216, 0.1);
      --border-primary: #374151;
      --border-accent: #4f46e5;
      --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.3);
      --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.4);
      --shadow-lg: 0 10px 40px rgba(0, 0, 0, 0.6);
      --shadow-glow: 0 0 30px rgba(29, 78, 216, 0.15);
      --radius-sm: 8px;
      --radius-md: 12px;
      --radius-lg: 16px;
      --radius-xl: 20px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, var(--bg-primary) 0%, var(--bg-secondary) 100%);
      color: var(--text-primary);
      line-height: 1.6;
      min-height: 100vh;
      overflow-x: hidden;
    }
    body::before {
      content: '';
      position: fixed; inset: 0;
      background:
        radial-gradient(circle at 20% 20%, rgba(29, 78, 216, 0.12) 0%, transparent 50%),
        radial-gradient(circle at 80% 80%, rgba(29, 78, 216, 0.08) 0%, transparent 50%);
      z-index: -1;
      animation: float 20s ease-in-out infinite;
    }
    @keyframes float { 0%,100%{transform:translateY(0) rotate(0)} 50%{transform:translateY(-10px) rotate(1deg)} }
    header {
      background: rgba(26, 26, 38, 0.95);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border-primary);
      padding: 1rem 2rem;
      position: sticky; top: 0; z-index: 100;
      box-shadow: var(--shadow-md);
    }
    .header-content { max-width: 1200px; margin: 0 auto; display: flex; align-items: center; gap: 1rem; }
    header img {
      height: 60px; width: auto; border-radius: var(--radius-md);
      background: rgba(255,255,255,0.98); padding: 8px 12px;
      filter: contrast(1.05) saturate(0.95);
      box-shadow: var(--shadow-sm), 0 0 10px rgba(0,0,0,0.1);
      border: 1px solid rgba(255,255,255,0.2);
      transition: all 0.3s ease;
    }
    header h1 {
      font-size: 1.5rem; font-weight: 600;
      background: linear-gradient(135deg, var(--text-primary) 0%, var(--blue-primary) 100%);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
      letter-spacing: -0.025em;
    }
    main { max-width: 1200px; margin: 2rem auto; padding: 0 2rem; }
    .card { background: var(--bg-tertiary); border: 1px solid var(--border-primary);
      border-radius: var(--radius-xl); box-shadow: var(--shadow-lg); overflow: hidden; position: relative; }
    .card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px;
      background: linear-gradient(90deg, var(--blue-primary), var(--blue-secondary)); }
    .card .head { background: linear-gradient(135deg, var(--bg-accent) 0%, var(--bg-tertiary) 100%);
      padding: 1.5rem 2rem; border-bottom: 1px solid var(--border-primary); }
    .card .head h2 { font-size: 1.25rem; font-weight: 600; color: var(--text-primary); }
    .content { padding: 2rem; }
    .row { display: grid; grid-template-columns: 1fr; gap: 2rem; align-items: start; }
    @media (min-width: 900px) { .row { grid-template-columns: 2fr 1fr; } }
    label { display: block; font-weight: 500; color: var(--text-accent);
      margin-bottom: 0.75rem; font-size: 0.95rem; }
    textarea {
      width: 100%; min-height: 300px; resize: vertical; background: var(--blue-tertiary);
      color: var(--text-primary); border: 2px solid transparent; border-radius: var(--radius-lg);
      padding: 1.25rem; font-family: 'JetBrains Mono','Fira Code',monospace; font-size: 0.875rem;
      line-height: 1.6; outline: none; box-shadow: inset 0 2px 4px rgba(0,0,0,0.3);
    }
    textarea::placeholder { color: var(--text-muted); font-style: italic; }
    textarea:focus {
      border-color: var(--blue-primary);
      box-shadow: inset 0 2px 4px rgba(0,0,0,0.3), 0 0 0 3px rgba(29,78,216,0.18);
      transform: translateY(-1px);
    }
    .btns { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
    button {
      appearance: none; border: none; border-radius: var(--radius-md);
      padding: 0.875rem 1.5rem; font-weight: 600; font-size: 0.95rem; cursor: pointer;
      transition: all 0.2s ease; position: relative; overflow: hidden;
    }
    button::before {
      content: ''; position: absolute; top:0; left:-100%; width:100%; height:100%;
      background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
      transition: left 0.5s ease;
    }
    button:hover::before { left: 100%; }
    .btn-primary {
      background: linear-gradient(135deg, var(--blue-primary) 0%, var(--blue-secondary) 100%); color: white;
      box-shadow: var(--shadow-sm);
    }
    .btn-secondary { background: var(--bg-accent); color: var(--text-primary); border: 1px solid var(--border-primary); }
    .status {
      padding: 1rem 1.25rem; border-radius: var(--radius-lg);
      font-size: 0.9rem; font-weight: 500; border: 1px solid; display: none; position: relative; overflow:hidden;
    }
    .status::before { content:''; position:absolute; left:0; top:0; bottom:0; width:4px; }
    .status.ok { display:block; background: var(--success-bg); border-color: var(--success); color: var(--success); }
    .status.ok::before { background: var(--success); }
    .status.err { display:block; background: var(--error-bg); border-color: var(--error); color: var(--error); }
    .status.err::before { background: var(--error); }
    .status.info { display:block; background: var(--info-bg); border-color: var(--info); color: var(--info); }
    .status.info::before { background: var(--info); }
    .loading { animation: pulse 1.5s ease-in-out infinite; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }
    .download {
      margin-top: 1.5rem; padding: 1.25rem;
      background: linear-gradient(135deg, var(--success-bg) 0%, rgba(16,185,129,0.05) 100%);
      border: 2px solid var(--success); border-radius: var(--radius-lg);
      display: none; align-items: center; gap: 0.75rem;
    }
    .download a {
      color: var(--success); font-weight: 600; text-decoration: none;
      padding: 0.5rem 1rem; background: rgba(16,185,129,0.1); border-radius: var(--radius-md);
      transition: all 0.2s ease; border: 1px solid transparent;
    }
  </style>
</head>
<body>
  <header>
    <div class="header-content">
      <img src="/static/logo_apotheek_rgb.jpg" alt="Apotheek Jansen logo" />
      <h1>Medicatiebeoordeling Voorbereider</h1>
    </div>
  </header>

  <main>
    <section class="card">
      <div class="head">
        <h2>Automatiseer de voorbereiding van medicatiebeoordelingen</h2>
      </div>
      <div class="content">
        <div class="row">
          <div>
            <label for="medimo">Plak hier het VOLLEDIGE medicatieoverzicht uit Medimo van de afdeling</label>
            <textarea 
              id="medimo" 
              placeholder="Bijvoorbeeld...:

Overzicht medicatie Afdeling X
Een overzicht van alle actieve medicatie in afdeling Afdeling X. Per patient wordt weergegeven of en zo ja welke geneesmiddelen deze mensen gebruiken.

10 records in selectie.
________________________________________
Dhr. A Einstein (14-03-1879)
C   Clozapine tablet 6,25mg	1-0-0 stuks, dagelijks, Continu
Z   Paracetamol tablet 500mg	0-0-0 stuks, dagelijks, Zo nodig
Etc..."></textarea>
          </div>
          <div>
            <div class="btns">
              <button class="btn-primary" id="runBtn">Verwerken</button>
              <button class="btn-secondary" id="clearBtn">Leegmaken</button>
            </div>

            <div id="status" class="status info">Klaar om te verwerken.</div>

            <div id="download" class="download">
              <span>Gereed!</span>
              <a id="downloadLink" href="#" download>Download Word Document (.docx)</a>
            </div>

            <!-- Live voortgang -->
            <div id="progressWrap" style="display:none; margin-top:1rem;">
              <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                <strong id="progressTitle"></strong>
                <span id="progressPct">0%</span>
              </div>
              <div style="width:100%; height:10px; background:#2a2a3a; border-radius:8px; overflow:hidden;">
                <div id="progressFill" style="height:100%; width:0%; background:#1d4ed8;"></div>
              </div>
              <div id="progressMeta" style="margin-top:6px; font-size:0.9em; color:#94a3b8;"></div>
            </div>

          </div>
        </div>
      </div>
    </section>
  </main>

  <script>
  const runBtn = document.getElementById('runBtn');
  const clearBtn = document.getElementById('clearBtn');
  const medimo = document.getElementById('medimo');
  const statusBox = document.getElementById('status');
  const dlWrap = document.getElementById('download');
  const dlLink = document.getElementById('downloadLink');

  const progressWrap = document.getElementById('progressWrap');
  const progressTitle = document.getElementById('progressTitle');
  const progressPct = document.getElementById('progressPct');
  const progressFill = document.getElementById('progressFill');
  const progressMeta = document.getElementById('progressMeta');

  let progressTimer = null;
  let runAbortCtrl = null;
  let titleGraceUntil = 0;
  let currentRunId = null;

  function setStatus(msg, type='info'){
    statusBox.textContent = msg;
    statusBox.className = 'status ' + type;
    statusBox.style.display = 'block';
    if (type === 'info' && msg.toLowerCase().startsWith('verwerken')) {
      statusBox.classList.add('loading');
    } else {
      statusBox.classList.remove('loading');
    }
  }

  function resetDownload(){
    dlWrap.style.display = 'none';
    dlLink.removeAttribute('href');
    dlLink.removeAttribute('download');
  }

  function startProgressPolling() {
    if (!currentRunId) return;
    stopProgressPolling();
    progressWrap.style.display = 'block';
    progressTitle.textContent = '';
    progressPct.textContent = '0%';
    progressFill.style.width = '0%';
    progressMeta.textContent = 'Bezig...';
    titleGraceUntil = Date.now() + 1500;
    pollProgressOnce();
    progressTimer = setInterval(pollProgressOnce, 500);
  }

  function stopProgressPolling() {
    if (progressTimer) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
  }

  async function pollProgressOnce() {
    if (!currentRunId) return;
    try {
      const r = await fetch(`/api/progress?run_id=${encodeURIComponent(currentRunId)}`, { cache: 'no-store' });
      if (!r.ok) {
        // 404 betekent: nog niet gestart óf al afgerond & progress verwijderd → stil blijven
        return;
      }
      const d = await r.json();

      const pct = d.pct_geanalyseerd ?? d.pct ?? 0;

      if (d.afdeling && d.afdeling !== 'Onbekend') {
        progressTitle.textContent = `Voortgang — Afdeling ${d.afdeling}`;
      } else if (!progressTitle.textContent && Date.now() > titleGraceUntil) {
        progressTitle.textContent = 'Voortgang analyse';
      }

      progressPct.textContent = `${pct}%`;
      progressFill.style.width = `${pct}%`;
      const nA = (d.n_medicijnen_geanalyseerd ?? 0);
      const nT = (d.n_medicijnen_input ?? 0);
      progressMeta.textContent = nT ? `${nA}/${nT} Geneesmiddelen` : (d.status || 'Bezig...');

      if (d.status === 'done' || d.status === 'aborted' || d.status === 'error' || pct >= 100) {
        stopProgressPolling();
      }
    } catch (e) {
      // tijdelijke race conditions: zwijgen
    }
  }

  clearBtn.addEventListener('click', async ()=>{
    medimo.value = '';
    resetDownload();
    progressWrap.style.display = 'none';
    stopProgressPolling();
    setStatus('Leeg gemaakt. Plak nieuwe input om te verwerken.', 'info');
    medimo.focus();

    // Stop eventueel lopend request
    try { if (runAbortCtrl) runAbortCtrl.abort(); } catch (_) {}

    // Annuleren + opruimen van huidige run
    try {
      if (currentRunId) {
        await fetch('/api/cancel', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ run_id: currentRunId })
        });
        await fetch('/api/clear', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ run_id: currentRunId })
        });
      }
    } catch (_) {}

    currentRunId = null;
    runBtn.disabled = false;
    runBtn.textContent = 'Verwerken';
  });

  runBtn.addEventListener('click', async ()=>{
    resetDownload();
    const text = medimo.value.trim();
    if(!text){
      setStatus('Voer eerst tekst in.', 'err');
      medimo.focus();
      return;
    }

    // Nieuwe run_id per klik
    currentRunId = (crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());

    runBtn.disabled = true;
    runBtn.textContent = 'Verwerken...';
    setStatus('Verwerken van medicatie gegevens...', 'info');

    try{
      startProgressPolling();
      runAbortCtrl = new AbortController();

      const resp = await fetch('/api/run', {
        method:'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ run_id: currentRunId, medimo_text: text }),
        signal: runAbortCtrl.signal
      });

      stopProgressPolling();

      if(!resp.ok){
        const data = await resp.json().catch(()=> ({}));
        const det = data?.detail || resp.statusText;
        throw new Error(det);
      }

      const blob = await resp.blob();
      const cd = resp.headers.get('Content-Disposition') || '';
      const m = /filename="?(.*?)"?$/.exec(cd);
      const filename = m ? m[1] : 'MedicatieReview.docx';

      const url = URL.createObjectURL(blob);
      dlLink.href = url;
      dlLink.download = filename;
      dlWrap.style.display = 'flex';
      setStatus('Succesvol verwerkt! Download is beschikbaar.', 'ok');
    } catch(err){
      console.error(err);
      setStatus('Fout: ' + err.message, 'err');
      stopProgressPolling();
    } finally {
      runBtn.disabled = false;
      runBtn.textContent = 'Verwerken';
    }
  });

  // Auto-focus textarea on load
  medimo.focus();

  // Shortcuts
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey) {
      if (e.key === 'Enter') {
        e.preventDefault();
        runBtn.click();
      } else if (e.key.toLowerCase() === 'k') {
        e.preventDefault();
        clearBtn.click();
      }
    }
  });
</script>
  <footer style="margin-top:2rem; padding:1rem; text-align:center; font-size:0.9rem; color:var(--text-muted); border-top:1px solid var(--border-primary);">
  <p>© 2025 Sem de Groot – Voor vragen of verbeteringen: +31 637395978 of <a href="mailto:semdegroot2003@gmail.com" style="color:var(--text-accent);">semdegroot2003@gmail.com</a></p>
  </footer>
</body>
</html>
"""

# -------------------------------------------------
# Routes
# -------------------------------------------------

@app.get("/")
def index():
    return render_template_string(HTML_PAGE)

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