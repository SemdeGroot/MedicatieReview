# app.py
import os
import io
import glob
import time
import tempfile
import shutil
import traceback
import threading
from typing import Optional
from flask import Flask, request, send_file, jsonify, render_template_string

# -------------------------------------------------
# Config
# -------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "Output")
DATA_DIR = os.path.join(PROJECT_ROOT, "Data")
ORIGINAL_MEDIMO = os.path.join(DATA_DIR, "medimo_input.txt")
TEMP_DIR = os.path.join(DATA_DIR, "Temp")
CANCEL_FLAG = os.path.join(TEMP_DIR, "cancel.flag")

# Importeer jouw bestaande main.py (moet in dezelfde root liggen)
import importlib
main_mod = importlib.import_module("main")  # jouw main.py met main()

# Eén globale lock om race-conditions te voorkomen als meerdere users tegelijk posten
WRITE_LOCK = threading.Lock()

# Flask - serveer /static/* uit ./Data zodat het logo zichtbaar is
app = Flask(__name__, static_folder="Data", static_url_path="/static")


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def _latest_docx_after(path: str, t0: float) -> Optional[str]:
    """Geef het nieuwste .docx-pad terug dat is aangepast ná tijdstip t0."""
    if not os.path.isdir(path):
        return None
    candidates = []
    for p in glob.glob(os.path.join(path, "*.docx")):
        try:
            if os.path.getmtime(p) >= t0:
                candidates.append(p)
        except FileNotFoundError:
            pass
    if not candidates:
        return None
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0]


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
      /* Moderne donkere kleurenpalet */
      --bg-primary: #0f0f17;
      --bg-secondary: #1a1a26;
      --bg-tertiary: #252532;
      --bg-accent: #2d2d3f;

      /* Blauwe accenten */
      --blue-primary: #1d4ed8;
      --blue-secondary: #1e3a8a;
      --blue-tertiary: #0f172a;
      --blue-soft: #1e293b;
      --blue-glow: rgba(29, 78, 216, 0.15);

      /* Tekst kleuren */
      --text-primary: #f8fafc;
      --text-secondary: #cbd5e1;
      --text-muted: #94a3b8;
      --text-accent: #e0e7ff;

      /* Status kleuren */
      --success: #10b981;
      --success-bg: rgba(16, 185, 129, 0.1);
      --error: #ef4444;
      --error-bg: rgba(239, 68, 68, 0.1);
      --info: #1d4ed8;
      --info-bg: rgba(29, 78, 216, 0.1);

      /* Borders en shadows */
      --border-primary: #374151;
      --border-accent: #4f46e5;
      --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.3);
      --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.4);
      --shadow-lg: 0 10px 40px rgba(0, 0, 0, 0.6);
      --shadow-glow: 0 0 30px rgba(29, 78, 216, 0.15);

      /* Geometrie */
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
    .header-content {
      max-width: 1200px; margin: 0 auto; display: flex; align-items: center; gap: 1rem;
    }
    header img {
      height: 50px; width: auto; border-radius: var(--radius-md);
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

    .card {
      background: var(--bg-tertiary); border: 1px solid var(--border-primary);
      border-radius: var(--radius-xl); box-shadow: var(--shadow-lg); overflow: hidden; position: relative;
    }
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

            <!-- Live voortgang (staat los van download-div) -->
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
      stopProgressPolling();
      progressWrap.style.display = 'block';
      progressTitle.textContent = '';            // <-- leeg, geen flash
      progressPct.textContent = '0%';
      progressFill.style.width = '0%';
      progressMeta.textContent = 'Bezig...';

      // titel-grace: wacht even op afdeling voor we fallback tonen
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
      try {
        const r = await fetch('/api/progress', { cache: 'no-store' });
        if (!r.ok) return;
        const d = await r.json();

        const pct = d.pct_geanalyseerd ?? 0;

        // Titel-logica: voorkom flash van "Voortgang analyse"
        if (d.afdeling && d.afdeling !== 'Onbekend') {
          progressTitle.textContent = `Voortgang — Afdeling ${d.afdeling}`;
        } else if (!progressTitle.textContent && Date.now() > titleGraceUntil) {
          // Pas na de grace-periode een fallback tonen
          progressTitle.textContent = 'Voortgang analyse';
        }

        progressPct.textContent = `${pct}%`;
        progressFill.style.width = `${pct}%`;
        progressMeta.textContent = `${d.n_medicijnen_geanalyseerd}/${d.n_medicijnen_input} Geneesmiddelen `;

        if (d.status === 'done' || pct >= 100) {
          stopProgressPolling();
        }
      } catch (e) {
        // Zwijg bij tijdelijke read/JSON race
      }
    }

    clearBtn.addEventListener('click', async ()=>{
      // UI direct resetten
      medimo.value = '';
      resetDownload();
      progressWrap.style.display = 'none';
      stopProgressPolling();
      setStatus('Leeg gemaakt. Plak nieuwe input om te verwerken.', 'info');
      medimo.focus();

      // Abort het lopende fetch-request naar /api/run (client-side)
      try {
        if (runAbortCtrl) {
          runAbortCtrl.abort();
        }
      } catch (_) {}

      // Vraag de server om parsing te stoppen
      try {
        await fetch('/api/cancel', { method: 'POST' });
      } catch (_) {}

      // Knoppen herstellen
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

      runBtn.disabled = true;
      runBtn.textContent = 'Verwerken...';
      setStatus('Verwerken van medicatie gegevens...', 'info');

      try{
        // Start meteen met live polling
        startProgressPolling();

        // maak een AbortController voor deze run
        runAbortCtrl = new AbortController();

        // Start de run (promise), laat intussen polling doorlopen
        const runPromise = fetch('/api/run', {
          method:'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ medimo_text: text }),
          signal: runAbortCtrl.signal   // belangrijk
        });

        const resp = await runPromise;  // wachten op klaar

        // extra: stop polling (zou al gestopt zijn als status 'done' is gezet)
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
    # Frontend uit string; logo via /static/logo_apotheek_rgb.jpg
    return render_template_string(HTML_PAGE)


@app.post("/api/run")
def run_pipeline():
    """
    - Maakt tijdelijke kopie met user-input
    - Vervangt Data/medimo_input.txt atomisch (met lock)
    - Draait main.main()
    - Stuurt .docx terug vanuit geheugen (en verwijdert het bestand meteen)
    - Herstelt altijd het originele bestand (of verwijdert als er geen origineel was)
    """
    from werkzeug.exceptions import ClientDisconnected

    backup_path = None
    temp_new = None
    t0 = time.time()

    try:
        j = request.get_json(force=True, silent=False) or {}
        medimo_text = j.get("medimo_text", "")
        if not medimo_text.strip():
            return jsonify({"detail": "Geen medimo_text aangeleverd."}), 400

        # 1) Tijdelijke file met inhoud
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as tmp:
            tmp.write(medimo_text)
            temp_new = tmp.name

        # 2) Met lock: backup + atomisch vervangen
        with WRITE_LOCK:
            os.makedirs(DATA_DIR, exist_ok=True)
            if os.path.exists(ORIGINAL_MEDIMO):
                with tempfile.NamedTemporaryFile(delete=False) as bak:
                    backup_path = bak.name
                shutil.copy2(ORIGINAL_MEDIMO, backup_path)
            os.replace(temp_new, ORIGINAL_MEDIMO)
            temp_new = None  # eigendom overgedragen

        # 3) Draai jouw pipeline
        main_mod.main()

        # 4) Vind nieuwste docx sinds starttijd
        time.sleep(0.2)  # kleine FS-pauze
        latest = _latest_docx_after(OUTPUT_DIR, t0)
        if not latest:
            files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "*.docx")), key=os.path.getmtime, reverse=True)
            latest = files[0] if files else None

        if not latest:
            return jsonify({"detail": "Geen .docx-output gevonden in Output/."}), 500

        # 5) Lees bestand volledig in geheugen en verwijder op schijf
        try:
            with open(latest, "rb") as f:
                doc_bytes = f.read()
        except FileNotFoundError:
            # Bestaat al niet meer (race)? Fout teruggeven.
            return jsonify({"detail": "Output-bestand kon niet worden gelezen."}), 500

        # Verwijder met mini-retry om Windows locks te omzeilen
        for _ in range(10):
            try:
                os.remove(latest)
                break
            except PermissionError:
                time.sleep(0.1)
            except FileNotFoundError:
                break

        # 6) Stuur uit geheugen
        bio = io.BytesIO(doc_bytes)
        bio.seek(0)
        resp = send_file(
            bio,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=os.path.basename(latest),
            max_age=0
        )
        resp.headers["Cache-Control"] = "no-store, max-age=0"
        return resp

    except ClientDisconnected:
        # Client heeft afgebroken (AbortController) → geen errorlog, alleen opruimen
        return ("", 204)

    except Exception as e:
        traceback.print_exc()
        # Geef nette fout i.p.v. “Failed to fetch”
        return jsonify({"detail": f"Fout tijdens verwerken: {e}"}), 500

    finally:
        # 7) Herstel altijd het originele bestand
        try:
            with WRITE_LOCK:
                if backup_path and os.path.exists(backup_path):
                    os.replace(backup_path, ORIGINAL_MEDIMO)
                    backup_path = None
                else:
                    if os.path.exists(ORIGINAL_MEDIMO) and not os.path.samefile(ORIGINAL_MEDIMO, ORIGINAL_MEDIMO):
                        # normaal gesproken redundant; defensief gelaten
                        os.remove(ORIGINAL_MEDIMO)
        except Exception:
            traceback.print_exc()

        # Opruimen als temp_new niet gebruikt/overgedragen is
        if temp_new and os.path.exists(temp_new):
            try:
                os.remove(temp_new)
            except Exception:
                traceback.print_exc()

@app.get("/api/progress")
def api_progress():
    """
    Geeft live voortgang terug als JSON.
    - Optioneel: /api/progress?afdeling=Argusvlinder
    - Zonder param: pak het meest recente afdelings_progress_*.json bestand.
    """
    afd = request.args.get("afdeling")
    if afd:
        path = os.path.join(TEMP_DIR, f"afdelings_progress_{afd}.json")
        if not os.path.exists(path):
            return jsonify({"detail": f"Geen progress voor afdeling '{afd}'."}), 404
    else:
        files = glob.glob(os.path.join(TEMP_DIR, "afdelings_progress_*.json"))
        if not files:
            return jsonify({"detail": "Nog geen progress-bestand gevonden."}), 404
        path = max(files, key=os.path.getmtime)

    resp = send_file(path, mimetype="application/json")
    # Zorg dat de browser nooit cached tijdens polling
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp

@app.post("/api/cancel")
def api_cancel():
    """Zet een cancel-flag zodat de parser kan stoppen."""
    try:
        os.makedirs(TEMP_DIR, exist_ok=True)
        with open(CANCEL_FLAG, "w", encoding="utf-8") as f:
            f.write("cancel")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "detail": str(e)}), 500

# -------------------------------------------------
# Entrypoint
# -------------------------------------------------
if __name__ == "__main__":
    # Start lokale server en open http://127.0.0.1:5000
    app.run(host="127.0.0.1", port=5000, debug=True)