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