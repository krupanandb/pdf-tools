/* ── PDF Redaction ── */
const $ = id => document.getElementById(id);

let sessionId = null;
let pages = [];
const marks = [];   // stack of mark elements (for Undo + count)

document.addEventListener('DOMContentLoaded', () => {
  const zone = $('uploadZone'), input = $('fileInput');

  zone.addEventListener('click', e => {
    if (e.target.closest('.link-btn')) return;
    input.click();
  });
  input.addEventListener('change', () => {
    if (input.files[0]) loadPdf(input.files[0]);
  });
  zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault(); zone.classList.remove('drag-over');
    if (e.dataTransfer.files[0]) loadPdf(e.dataTransfer.files[0]);
  });

  $('findBtn').addEventListener('click', markMatches);
  $('searchTerms').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); markMatches(); }
  });
  $('undoBtn').addEventListener('click', undoMark);
});

/* ── Load (reuses the editor's load endpoint) ── */
function loadPdf(file) {
  $('uploadZone').hidden = true;
  $('loadingWrap').hidden = false;
  const fd = new FormData();
  fd.append('files', file);
  fetch('/api/edit/load', { method: 'POST', body: fd })
    .then(r => r.json())
    .then(data => {
      $('loadingWrap').hidden = true;
      if (data.error) return showError(data.error);
      sessionId = data.session_id;
      pages = data.pages;
      renderPages();
      $('editorMain').hidden = false;
    })
    .catch(err => { $('loadingWrap').hidden = true; showError(err.message); });
}

function renderPages() {
  const canvas = $('pagesCanvas');
  canvas.innerHTML = '';
  pages.forEach((pg, pidx) => {
    const pageDiv = document.createElement('div');
    pageDiv.className = 'editor-page';

    const img = document.createElement('img');
    img.className = 'page-img';
    img.src = 'data:image/png;base64,' + pg.image;
    img.draggable = false;
    pageDiv.appendChild(img);

    const layer = document.createElement('div');
    layer.className = 'edit-layer redact-layer';
    layer.dataset.page = pidx;
    layer.addEventListener('mousedown', e => onLayerMouseDown(e, layer));
    pageDiv.appendChild(layer);

    canvas.appendChild(pageDiv);
  });
}

/* ── Draw redaction boxes ── */
let dragRect = null, dragStart = null, dragLayer = null;

function onLayerMouseDown(e, layer) {
  if (e.target.classList.contains('rd-box')) return;  // ignore clicks on existing marks
  const r = layer.getBoundingClientRect();
  const nx = (e.clientX - r.left) / r.width;
  const ny = (e.clientY - r.top) / r.height;

  dragLayer = layer;
  dragStart = { nx, ny };
  dragRect = makeBox(layer, nx, ny, 0, 0, 'drawn');
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

function onMove(e) {
  if (!dragRect) return;
  const r = dragLayer.getBoundingClientRect();
  let nx = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  let ny = Math.max(0, Math.min(1, (e.clientY - r.top) / r.height));
  const x = Math.min(nx, dragStart.nx), y = Math.min(ny, dragStart.ny);
  const w = Math.abs(nx - dragStart.nx), h = Math.abs(ny - dragStart.ny);
  setBox(dragRect, x, y, w, h);
}

function onUp() {
  document.removeEventListener('mousemove', onMove);
  document.removeEventListener('mouseup', onUp);
  if (dragRect && parseFloat(dragRect.dataset.w || 0) < 0.004) {
    dragRect.remove();
  } else if (dragRect) {
    marks.push(dragRect);
    updateCount();
  }
  dragRect = null; dragStart = null; dragLayer = null;
}

function makeBox(layer, x, y, w, h, kind) {
  const el = document.createElement('div');
  el.className = 'rd-box' + (kind === 'found' ? ' rd-found' : '');
  el.dataset.page = layer.dataset.page;
  setBox(el, x, y, w, h);
  el.addEventListener('click', e => {
    e.stopPropagation();
    removeMark(el);
  });
  el.title = 'Click to remove this mark';
  layer.appendChild(el);
  return el;
}

function setBox(el, x, y, w, h) {
  el.dataset.x = x; el.dataset.y = y; el.dataset.w = w; el.dataset.h = h;
  el.style.left = (x * 100) + '%';
  el.style.top  = (y * 100) + '%';
  el.style.width  = (w * 100) + '%';
  el.style.height = (h * 100) + '%';
}

/* ── Find & mark matches (client-side preview from spans) ── */
function markMatches() {
  const raw = $('searchTerms').value.trim();
  if (!raw) return;
  const terms = raw.split(',').map(t => t.trim().toLowerCase()).filter(Boolean);
  let added = 0;

  document.querySelectorAll('.redact-layer').forEach(layer => {
    const pidx = parseInt(layer.dataset.page);
    pages[pidx].spans.forEach(span => {
      const text = (span.text || '').toLowerCase();
      if (terms.some(t => text.includes(t))) {
        const el = makeBox(layer, span.x, span.y, span.w, span.h, 'found');
        marks.push(el);
        added++;
      }
    });
  });

  updateCount();
  if (added === 0) {
    $('editorHint').innerHTML =
      'No on-screen matches found — but the words will still be searched precisely on the server when you Apply.';
  } else {
    $('editorHint').innerHTML =
      `<strong>${added}</strong> match(es) marked. Review them, then click <strong>Apply</strong>.`;
  }
}

/* ── Marks management ── */
function removeMark(el) {
  const i = marks.indexOf(el);
  if (i !== -1) marks.splice(i, 1);
  el.remove();
  updateCount();
}
function undoMark() {
  const el = marks.pop();
  if (el) el.remove();
  updateCount();
}
function updateCount() {
  $('redactCount').textContent = marks.length + ' marked';
  $('undoBtn').disabled = marks.length === 0;
}

/* ── Apply ── */
function applyRedactions() {
  const boxes = marks.map(el => ({
    page: parseInt(el.dataset.page),
    x: parseFloat(el.dataset.x), y: parseFloat(el.dataset.y),
    w: parseFloat(el.dataset.w), h: parseFloat(el.dataset.h),
  }));
  const terms = $('searchTerms').value.trim();

  if (boxes.length === 0 && !terms) {
    showError('Nothing to redact yet — draw a box or enter a search term.');
    return;
  }

  if (!confirm('Apply redactions? This permanently removes the marked content '
             + 'and cannot be undone on the downloaded file.')) return;

  const fd = new FormData();
  fd.append('session_id', sessionId);
  fd.append('payload', JSON.stringify(boxes));
  fd.append('terms', terms);

  $('editorMain').hidden = true;
  $('loadingWrap').hidden = false;
  $('loadingLabel').textContent = 'Applying redactions…';

  fetch('/api/redact/apply', { method: 'POST', body: fd })
    .then(async res => {
      $('loadingWrap').hidden = true;
      if (!res.ok) {
        const d = await res.json().catch(() => ({ error: 'HTTP ' + res.status }));
        return showError(d.error || 'Unknown error');
      }
      const n = res.headers.get('X-Redaction-Count');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = $('downloadLink');
      link.href = url; link.download = 'redacted.pdf';
      if (n) $('resultMsg').textContent =
        `${n} area(s) permanently redacted. Your file is ready.`;
      $('resultBox').hidden = false;
    })
    .catch(err => { $('loadingWrap').hidden = true; showError(err.message); });
}

function showError(msg) {
  $('errorMsg').textContent = msg;
  $('errorBox').hidden = false;
}
