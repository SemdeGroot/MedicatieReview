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
      --bg-primary: #0f0f17;        /* Zeer donkere basis */
      --bg-secondary: #1a1a26;      /* Iets lichter voor panelen */
      --bg-tertiary: #252532;       /* Cards en elementen */
      --bg-accent: #2d2d3f;         /* Hover states */
      
      /* Blauwe accenten - donkerdere tinten */
      --blue-primary: #1d4ed8;      /* Donkerder blauw */
      --blue-secondary: #1e3a8a;    /* Nog donkerder blauw */
      --blue-tertiary: #0f172a;     /* Zeer donker blauw voor textarea */
      --blue-soft: #1e293b;         /* Zachte donkere blauwe tint */
      --blue-glow: rgba(29, 78, 216, 0.15);
      
      /* Tekst kleuren */
      --text-primary: #f8fafc;      /* Hoofdtekst */
      --text-secondary: #cbd5e1;    /* Secondary tekst */
      --text-muted: #94a3b8;        /* Gedempt */
      --text-accent: #e0e7ff;       /* Accent tekst */
      
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

    * { 
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, var(--bg-primary) 0%, var(--bg-secondary) 100%);
      color: var(--text-primary);
      line-height: 1.6;
      min-height: 100vh;
      overflow-x: hidden;
    }
    
    /* Subtiele geanimeerde achtergrond */
    body::before {
      content: '';
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: 
        radial-gradient(circle at 20% 20%, rgba(29, 78, 216, 0.12) 0%, transparent 50%),
        radial-gradient(circle at 80% 80%, rgba(29, 78, 216, 0.08) 0%, transparent 50%);
      z-index: -1;
      animation: float 20s ease-in-out infinite;
    }
    
    @keyframes float {
      0%, 100% { transform: translateY(0px) rotate(0deg); }
      50% { transform: translateY(-10px) rotate(1deg); }
    }

    /* Header styling - terug naar donker */
    header {
      background: rgba(26, 26, 38, 0.95);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border-primary);
      padding: 1rem 2rem;
      position: sticky;
      top: 0;
      z-index: 100;
      box-shadow: var(--shadow-md);
    }
    
    .header-content {
      max-width: 1200px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      gap: 1rem;
    }
    
    /* Logo styling - witte achtergrond voor het logo zelf */
    header img {
      height: 50px;
      width: auto;
      border-radius: var(--radius-md);
      
      /* Witte achtergrond voor het logo */
      background: rgba(255, 255, 255, 0.98);
      padding: 8px 12px;
      
      /* Subtiele filters voor betere integratie */
      filter: 
        contrast(1.05)
        saturate(0.95);
      
      /* Elegante shadow */
      box-shadow: 
        var(--shadow-sm),
        0 0 10px rgba(0, 0, 0, 0.1);
      
      /* Subtiele border */
      border: 1px solid rgba(255, 255, 255, 0.2);
      
      transition: all 0.3s ease;
    }
    
    header img:hover {
    transform: none !important;
    background: rgba(255, 255, 255, 0.98) !important;
    box-shadow: var(--shadow-sm), 0 0 10px rgba(0, 0, 0, 0.1) !important;
    border-color: rgba(255, 255, 255, 0.2) !important;
    }
    
    header h1 {
      font-size: 1.5rem;
      font-weight: 600;
      background: linear-gradient(135deg, var(--text-primary) 0%, var(--blue-primary) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      letter-spacing: -0.025em;
    }

    /* Main content */
    main {
      max-width: 1200px;
      margin: 2rem auto;
      padding: 0 2rem;
    }

    /* Card styling */
    .card {
      background: var(--bg-tertiary);
      border: 1px solid var(--border-primary);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow-lg);
      overflow: hidden;
      position: relative;
      transition: all 0.3s ease;
    }
    
    .card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--blue-primary), var(--blue-secondary));
    }
    
    .card:hover {
    transform: none !important;
    box-shadow: var(--shadow-lg) !important; /* zelfde als de basis .card */
    }

    .card .head {
      background: linear-gradient(135deg, var(--bg-accent) 0%, var(--bg-tertiary) 100%);
      padding: 1.5rem 2rem;
      border-bottom: 1px solid var(--border-primary);
    }
    
    .card .head h2 {
      font-size: 1.25rem;
      font-weight: 600;
      color: var(--text-primary);
    }
    
    .card .head h2 code {
      background: var(--blue-tertiary);
      color: var(--blue-primary);
      padding: 0.25rem 0.5rem;
      border-radius: var(--radius-sm);
      font-size: 0.875rem;
      font-weight: 500;
    }

    .content {
      padding: 2rem;
    }

    .row {
      display: grid;
      grid-template-columns: 1fr;
      gap: 2rem;
      align-items: start;
    }
    
    @media (min-width: 900px) {
      .row {
        grid-template-columns: 2fr 1fr;
      }
    }

    /* Form elements */
    label {
      display: block;
      font-weight: 500;
      color: var(--text-accent);
      margin-bottom: 0.75rem;
      font-size: 0.95rem;
    }

    textarea {
      width: 100%;
      min-height: 300px;
      resize: vertical;
      background: var(--blue-tertiary);
      color: var(--text-primary);
      border: 2px solid transparent;
      border-radius: var(--radius-lg);
      padding: 1.25rem;
      font-family: 'JetBrains Mono', 'Fira Code', monospace;
      font-size: 0.875rem;
      line-height: 1.6;
      transition: all 0.3s ease;
      outline: none;
      box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.3);
    }
    
    textarea::placeholder {
      color: var(--text-muted);
      font-style: italic;
    }
    
    textarea:focus {
      border-color: var(--blue-primary);
      box-shadow: 
        inset 0 2px 4px rgba(0, 0, 0, 0.3),
        0 0 0 3px rgba(29, 78, 216, 0.18);
      transform: translateY(-1px);
    }

    /* Buttons */
    .btns {
      display: flex;
      gap: 1rem;
      flex-wrap: wrap;
      margin-bottom: 1.5rem;
    }
    
    button {
      appearance: none;
      border: none;
      border-radius: var(--radius-md);
      padding: 0.875rem 1.5rem;
      font-weight: 600;
      font-size: 0.95rem;
      cursor: pointer;
      transition: all 0.2s ease;
      position: relative;
      overflow: hidden;
    }
    
    button::before {
      content: '';
      position: absolute;
      top: 0;
      left: -100%;
      width: 100%;
      height: 100%;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
      transition: left 0.5s ease;
    }
    
    button:hover::before {
      left: 100%;
    }
    
    .btn-primary {
      background: linear-gradient(135deg, var(--blue-primary) 0%, var(--blue-secondary) 100%);
      color: white;
      box-shadow: var(--shadow-md);
    }
    
    .btn-primary:hover {
      transform: translateY(-2px);
      box-shadow: var(--shadow-lg), 0 0 20px rgba(29, 78, 216, 0.25);
    }
    
    .btn-primary:active {
      transform: translateY(0);
    }
    
    .btn-secondary {
      background: var(--bg-accent);
      color: var(--text-primary);
      border: 1px solid var(--border-primary);
    }
    
    .btn-secondary:hover {
      background: var(--bg-tertiary);
      border-color: var(--blue-primary);
      transform: translateY(-1px);
    }
    
    button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
      transform: none !important;
    }
    
    button:disabled::before {
      display: none;
    }

    /* Status messages */
    .status {
      padding: 1rem 1.25rem;
      border-radius: var(--radius-lg);
      font-size: 0.9rem;
      font-weight: 500;
      border: 1px solid;
      display: none;
      position: relative;
      overflow: hidden;
    }
    
    .status::before {
      content: '';
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 4px;
    }
    
    .status.ok {
      display: block;
      background: var(--success-bg);
      border-color: var(--success);
      color: var(--success);
    }
    
    .status.ok::before {
      background: var(--success);
    }
    
    .status.err {
      display: block;
      background: var(--error-bg);
      border-color: var(--error);
      color: var(--error);
    }
    
    .status.err::before {
      background: var(--error);
    }
    
    .status.info {
      display: block;
      background: var(--info-bg);
      border-color: var(--info);
      color: var(--info);
    }
    
    .status.info::before {
      background: var(--info);
    }

    /* Download section */
    .download {
      margin-top: 1.5rem;
      padding: 1.25rem;
      background: linear-gradient(135deg, var(--success-bg) 0%, rgba(16, 185, 129, 0.05) 100%);
      border: 2px dashed var(--success);
      border-radius: var(--radius-lg);
      display: none;
      align-items: center;
      gap: 0.75rem;
      animation: slideIn 0.3s ease;
    }
    
    @keyframes slideIn {
      from {
        opacity: 0;
        transform: translateY(10px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
    
    .download a {
      color: var(--success);
      font-weight: 600;
      text-decoration: none;
      padding: 0.5rem 1rem;
      background: rgba(16, 185, 129, 0.1);
      border-radius: var(--radius-md);
      transition: all 0.2s ease;
      border: 1px solid transparent;
    }
    
    .download a:hover {
      background: rgba(16, 185, 129, 0.2);
      border-color: var(--success);
      transform: translateY(-1px);
    }

    /* Loading animation */
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    
    .loading {
      animation: pulse 1.5s ease-in-out infinite;
    }

    /* Responsive design */
    @media (max-width: 768px) {
      main {
        padding: 0 1rem;
        margin: 1rem auto;
      }
      
      header {
        padding: 1rem;
      }
      
      .content {
        padding: 1.5rem;
      }
      
      .btns {
        flex-direction: column;
      }
      
      button {
        width: 100%;
      }
      
      textarea {
        min-height: 250px;
        padding: 1rem;
      }
    }

    /* Accessibility improvements */
    @media (prefers-reduced-motion: reduce) {
      * {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
      }
      
      body::before {
        animation: none;
      }
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
              <button class="btn-primary" id="runBtn">
                Verwerken
              </button>
              <button class="btn-secondary" id="clearBtn">
                Leegmaken
              </button>
            </div>
            <div id="status" class="status info">Klaar om te verwerken.</div>
            <div id="download" class="download">
              <span>Gereed!</span>
              <a id="downloadLink" href="#" download>Download Word Document (.docx)</a>
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

    function setStatus(msg, type='info'){
      statusBox.textContent = msg;
      statusBox.className = 'status ' + type;
      statusBox.style.display = 'block';
      
      // Add loading animation for processing
      if (type === 'info' && msg.includes('Verwerken')) {
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

    clearBtn.addEventListener('click', ()=>{
      medimo.value = '';
      setStatus('Leeg gemaakt. Plak nieuwe input om te verwerken.', 'info');
      resetDownload();
      medimo.focus();
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
        const resp = await fetch('/api/run', {
          method:'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ medimo_text: text })
        });

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
      } finally {
        runBtn.disabled = false;
        runBtn.textContent = 'Verwerken';
      }
    });

    // Auto-focus textarea on load
    medimo.focus();
    
    // Add keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      if (e.ctrlKey || e.metaKey) {
        if (e.key === 'Enter') {
          e.preventDefault();
          runBtn.click();
        } else if (e.key === 'k') {
          e.preventDefault();
          clearBtn.click();
        }
      }
    });
  </script>
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
    - Stuurt nieuwste .docx terug
    - Herstelt altijd het originele bestand (of verwijdert als er geen origineel was)
    """
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

        return send_file(
            latest,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=os.path.basename(latest)
        )

    except Exception as e:
        traceback.print_exc()
        return jsonify({"detail": f"Fout tijdens verwerken: {e}"}), 500

    finally:
        # 5) Herstel altijd het originele bestand
        try:
            with WRITE_LOCK:
                if backup_path and os.path.exists(backup_path):
                    os.replace(backup_path, ORIGINAL_MEDIMO)  # restore origineel
                    backup_path = None
                else:
                    # Er was geen origineel: verwijder tijdelijke vervanger
                    if os.path.exists(ORIGINAL_MEDIMO):
                        os.remove(ORIGINAL_MEDIMO)
        except Exception:
            traceback.print_exc()
        # Opruimen als temp_new niet gebruikt/overgezet is
        if temp_new and os.path.exists(temp_new):
            try:
                os.remove(temp_new)
            except Exception:
                traceback.print_exc()


# -------------------------------------------------
# Entrypoint
# -------------------------------------------------
if __name__ == "__main__":
    # Start lokale server en open http://127.0.0.1:5000
    app.run(host="127.0.0.1", port=5000, debug=True)