/* ── PDF Editor ── */
const $ = id => document.getElementById(id);

let sessionId   = null;
let pages       = [];
let currentTool = 'select';
let selectedEl  = null;
let imgCounter  = 0;
const imageFiles = {};   // img_key -> File
const history   = [];    // stack of created overlay elements, for Undo

const HINTS = {
  select:   '<strong>Select</strong> — click any item to move it; drag its corner to resize. Press Delete to remove.',
  edittext: '<strong>Edit text</strong> — click highlighted existing text to change it.',
  text:     '<strong>Add text</strong> — click anywhere on the page to add a new text box.',
  whiteout: '<strong>Whiteout</strong> — drag a rectangle to cover content with white.',
  highlight:'<strong>Highlight</strong> — drag across text to add a translucent highlight.',
  draw:     '<strong>Draw</strong> — press and drag to draw freehand. Use the colour picker for the pen colour.',
  image:    '<strong>Sign / Image</strong> — click on the page, then pick a signature or image to place.',
};

function pushHistory(el) {
  history.push(el);
  $('undoBtn').disabled = history.length === 0;
}

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

  // Toolbar buttons
  document.querySelectorAll('.ed-tool').forEach(btn => {
    btn.addEventListener('click', () => setTool(btn.dataset.tool));
  });

  $('deleteSelBtn').addEventListener('click', deleteSelected);
  $('undoBtn').addEventListener('click', undoLast);
  $('imageInput').addEventListener('change', onImagePicked);

  $('styBold').addEventListener('click',   () => toggleStyle('bold'));
  $('styItalic').addEventListener('click', () => toggleStyle('italic'));
  $('styUnder').addEventListener('click',  () => toggleStyle('under'));
  $('styStrike').addEventListener('click', () => toggleStyle('strike'));

  document.addEventListener('keydown', e => {
    if ((e.key === 'Delete' || e.key === 'Backspace') && selectedEl &&
        !isEditing(document.activeElement)) {
      e.preventDefault();
      deleteSelected();
    }
  });
});

function isEditing(el) {
  return el && (el.isContentEditable || el.tagName === 'INPUT' || el.tagName === 'TEXTAREA');
}

function setTool(tool) {
  currentTool = tool;
  document.querySelectorAll('.ed-tool').forEach(b =>
    b.classList.toggle('active', b.dataset.tool === tool));
  $('editorHint').innerHTML = HINTS[tool] || '';
  document.querySelectorAll('.edit-layer').forEach(l =>
    l.classList.toggle('show-spans', tool === 'edittext'));
  selectEl(null);
}

/* ── Load ── */
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
    layer.className = 'edit-layer';
    layer.dataset.page = pidx;
    pageDiv.appendChild(layer);

    // existing-text hotspots
    pg.spans.forEach(span => {
      const hot = document.createElement('div');
      hot.className = 'span-hotspot';
      hot.style.left   = (span.x * 100) + '%';
      hot.style.top    = (span.y * 100) + '%';
      hot.style.width  = (span.w * 100) + '%';
      hot.style.height = (span.h * 100) + '%';
      hot.addEventListener('click', e => {
        if (currentTool !== 'edittext') return;
        e.stopPropagation();
        startEditExisting(layer, span);
      });
      layer.appendChild(hot);
    });

    layer.addEventListener('mousedown', e => onLayerMouseDown(e, layer, pidx));
    canvas.appendChild(pageDiv);
  });
}

/* ── Coordinate helpers (everything stored normalized 0..1) ── */
function layerMetrics(layer) {
  const r = layer.getBoundingClientRect();
  return r;
}

/* ── Edit existing text ── */
function startEditExisting(layer, span) {
  const style = { bold: span.bold, italic: span.italic, serif: span.serif,
                  mono: span.mono, font: span.font };
  const el = makeTextEl(layer, span.x, span.y, span.text, span.size, span.color, 'edit', style);
  el.dataset.w = span.w;
  el.dataset.h = span.h;
  el.style.width = (span.w * 100) + '%';
  el.classList.add('is-edit');
  focusText(el);
}

/* ── Add new text ── */
function addTextAt(layer, nx, ny) {
  const size = parseInt($('fontSize').value) || 14;
  const color = $('fontColor').value;
  const el = makeTextEl(layer, nx, ny, 'Type here', size, color, 'text', {});
  focusText(el);
}

function makeTextEl(layer, nx, ny, text, size, color, type, style) {
  style = style || {};
  const r = layerMetrics(layer);
  const el = document.createElement('div');
  el.className = 'ov ov-text';
  el.contentEditable = 'true';
  el.textContent = text;
  el.dataset.type = type;
  el.dataset.x = nx;
  el.dataset.y = ny;
  el.dataset.size = size;
  el.dataset.color = color;
  el.dataset.bold   = style.bold   ? '1' : '';
  el.dataset.italic = style.italic ? '1' : '';
  el.dataset.serif  = style.serif  ? '1' : '';
  el.dataset.mono   = style.mono   ? '1' : '';
  el.dataset.under  = '';
  el.dataset.strike = '';
  el.dataset.font   = style.font || '';
  el.style.left = (nx * 100) + '%';
  el.style.top  = (ny * 100) + '%';
  // font size scales with the rendered page width
  el.style.fontSize = (size * r.width / pages[layer.dataset.page].width_pt) + 'px';
  el.style.color = color;
  applyTextStyle(el);
  attachOv(el, layer);
  layer.appendChild(el);
  pushHistory(el);
  return el;
}

function focusText(el) {
  setTimeout(() => {
    el.focus();
    const range = document.createRange();
    range.selectNodeContents(el);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }, 10);
}

/* reflect the element's style flags visually (WYSIWYG) */
function applyTextStyle(el) {
  const d = el.dataset;
  el.style.fontWeight = d.bold ? '700' : '400';
  el.style.fontStyle  = d.italic ? 'italic' : 'normal';
  const named = (d.font || '').replace(/^[A-Z]{6}\+/, '').split(/[-,]/)[0].trim();
  if (named) {
    el.style.fontFamily = `"${named}", ` +
      (d.mono ? 'monospace' : d.serif ? 'serif' : 'sans-serif');
  } else {
    el.style.fontFamily = d.mono ? 'monospace'
      : d.serif ? 'Georgia, "Times New Roman", serif'
                : 'Helvetica, Arial, sans-serif';
  }
  const deco = [];
  if (d.under)  deco.push('underline');
  if (d.strike) deco.push('line-through');
  el.style.textDecoration = deco.join(' ') || 'none';
}

/* toolbar B / I / U / S toggles act on the selected text box */
function toggleStyle(prop) {
  const el = selectedEl;
  if (!el || !el.classList.contains('ov-text')) return;
  el.dataset[prop] = el.dataset[prop] ? '' : '1';
  applyTextStyle(el);
  syncStyleButtons(el);
}

function syncStyleButtons(el) {
  const isText = el && el.classList.contains('ov-text');
  const map = { styBold: 'bold', styItalic: 'italic', styUnder: 'under', styStrike: 'strike' };
  for (const id in map) {
    const btn = $(id);
    btn.disabled = !isText;
    btn.classList.toggle('on', isText && !!el.dataset[map[id]]);
  }
}

/* ── Rectangle tools (whiteout + highlight) and freehand draw ── */
let dragRect = null, dragStart = null, dragLayer = null;

function onLayerMouseDown(e, layer, pidx) {
  if (e.target.classList.contains('ov') || e.target.classList.contains('span-hotspot') ||
      e.target.classList.contains('ov-handle')) return;

  const r = layerMetrics(layer);
  const nx = (e.clientX - r.left) / r.width;
  const ny = (e.clientY - r.top) / r.height;

  if (currentTool === 'text') {
    addTextAt(layer, nx, ny);
  } else if (currentTool === 'image') {
    pendingImage = { layer, nx, ny };
    $('imageInput').click();
  } else if (currentTool === 'whiteout' || currentTool === 'highlight') {
    const isHi = currentTool === 'highlight';
    dragLayer = layer;
    dragStart = { nx, ny };
    dragRect = document.createElement('div');
    dragRect.className = 'ov ' + (isHi ? 'ov-highlight' : 'ov-white');
    dragRect.dataset.type = isHi ? 'highlight' : 'whiteout';
    if (isHi) dragRect.dataset.color = '#ffeb3b';
    dragRect.style.left = (nx * 100) + '%';
    dragRect.style.top  = (ny * 100) + '%';
    layer.appendChild(dragRect);
    document.addEventListener('mousemove', onRectMove);
    document.addEventListener('mouseup', onRectUp);
  } else if (currentTool === 'draw') {
    startDraw(e, layer);
  } else {
    selectEl(null);
  }
}

function onRectMove(e) {
  if (!dragRect) return;
  const r = layerMetrics(dragLayer);
  let nx = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  let ny = Math.max(0, Math.min(1, (e.clientY - r.top) / r.height));
  const x = Math.min(nx, dragStart.nx), y = Math.min(ny, dragStart.ny);
  const w = Math.abs(nx - dragStart.nx), h = Math.abs(ny - dragStart.ny);
  dragRect.style.left = (x * 100) + '%';
  dragRect.style.top  = (y * 100) + '%';
  dragRect.style.width  = (w * 100) + '%';
  dragRect.style.height = (h * 100) + '%';
  dragRect.dataset.x = x; dragRect.dataset.y = y;
  dragRect.dataset.w = w; dragRect.dataset.h = h;
}

function onRectUp() {
  document.removeEventListener('mousemove', onRectMove);
  document.removeEventListener('mouseup', onRectUp);
  if (dragRect && (parseFloat(dragRect.dataset.w || 0) < 0.005)) {
    dragRect.remove();
  } else if (dragRect) {
    attachOv(dragRect, dragLayer);
    pushHistory(dragRect);
  }
  dragRect = null; dragStart = null; dragLayer = null;
}

/* ── Freehand draw (SVG polyline overlay) ── */
const SVGNS = 'http://www.w3.org/2000/svg';
let drawState = null;

function startDraw(e, layer) {
  const r = layerMetrics(layer);
  const color = $('fontColor').value;
  const width = Math.max(1, Math.round((parseInt($('fontSize').value) || 14) / 7));

  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('class', 'ov ov-draw');
  svg.setAttribute('viewBox', '0 0 1000 1000');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.style.left = '0'; svg.style.top = '0';
  svg.style.width = '100%'; svg.style.height = '100%';
  svg.dataset.type = 'draw';
  svg.dataset.color = color;
  svg.dataset.width = width;

  const poly = document.createElementNS(SVGNS, 'polyline');
  poly.setAttribute('fill', 'none');
  poly.setAttribute('stroke', color);
  poly.setAttribute('stroke-width', width * (1000 / r.width));
  poly.setAttribute('stroke-linecap', 'round');
  poly.setAttribute('stroke-linejoin', 'round');
  svg.appendChild(poly);
  layer.appendChild(svg);

  drawState = { svg, poly, layer, r, pts: [] };
  addDrawPoint(e);
  document.addEventListener('mousemove', onDrawMove);
  document.addEventListener('mouseup', onDrawUp);
}

function addDrawPoint(e) {
  const r = drawState.r;
  const nx = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  const ny = Math.max(0, Math.min(1, (e.clientY - r.top) / r.height));
  drawState.pts.push([nx, ny]);
  const vbPts = drawState.pts.map(p => `${p[0] * 1000},${p[1] * 1000}`).join(' ');
  drawState.poly.setAttribute('points', vbPts);
}

function onDrawMove(e) { if (drawState) addDrawPoint(e); }

function onDrawUp() {
  document.removeEventListener('mousemove', onDrawMove);
  document.removeEventListener('mouseup', onDrawUp);
  if (drawState) {
    if (drawState.pts.length < 2) {
      drawState.svg.remove();
    } else {
      drawState.svg.dataset.points = JSON.stringify(drawState.pts);
      pushHistory(drawState.svg);
    }
  }
  drawState = null;
}

/* ── Image / signature ── */
let pendingImage = null;

function onImagePicked() {
  const file = $('imageInput').files[0];
  $('imageInput').value = '';
  if (!file || !pendingImage) return;

  const { layer, nx, ny } = pendingImage;
  pendingImage = null;
  const key = 'img_' + (imgCounter++);
  imageFiles[key] = file;

  const r = layerMetrics(layer);
  const url = URL.createObjectURL(file);
  const tmp = new Image();
  tmp.onload = () => {
    const defW = 0.25;  // 25% of page width
    const defH = defW * (tmp.height / tmp.width) * (r.width / r.height);
    const el = document.createElement('div');
    el.className = 'ov ov-image';
    el.dataset.type = 'image';
    el.dataset.img = key;
    el.dataset.x = nx; el.dataset.y = ny;
    el.dataset.w = defW; el.dataset.h = defH;
    el.style.left = (nx * 100) + '%';
    el.style.top  = (ny * 100) + '%';
    el.style.width  = (defW * 100) + '%';
    el.style.height = (defH * 100) + '%';
    el.style.backgroundImage = `url(${url})`;
    addHandle(el);
    attachOv(el, layer);
    layer.appendChild(el);
    pushHistory(el);
    selectEl(el);
  };
  tmp.src = url;
}

/* ── Overlay element: drag to move, corner to resize, click to select ── */
function attachOv(el, layer) {
  el.addEventListener('mousedown', e => {
    if (currentTool !== 'select') return;
    if (e.target.classList.contains('ov-handle')) return;
    if (el.isContentEditable && isEditing(document.activeElement) === el) return;
    e.stopPropagation();
    selectEl(el);
    startDrag(e, el, layer);
  });
  el.addEventListener('click', e => {
    if (currentTool === 'select') { e.stopPropagation(); selectEl(el); }
  });
}

function addHandle(el) {
  const h = document.createElement('div');
  h.className = 'ov-handle';
  h.addEventListener('mousedown', e => {
    e.stopPropagation(); e.preventDefault();
    startResize(e, el);
  });
  el.appendChild(h);
}

let drag = null;
function startDrag(e, el, layer) {
  const r = layerMetrics(layer);
  drag = {
    el, layer, r,
    sx: e.clientX, sy: e.clientY,
    ox: parseFloat(el.dataset.x), oy: parseFloat(el.dataset.y),
  };
  document.addEventListener('mousemove', onDragMove);
  document.addEventListener('mouseup', onDragUp);
}
function onDragMove(e) {
  if (!drag) return;
  let nx = drag.ox + (e.clientX - drag.sx) / drag.r.width;
  let ny = drag.oy + (e.clientY - drag.sy) / drag.r.height;
  nx = Math.max(0, Math.min(0.99, nx));
  ny = Math.max(0, Math.min(0.99, ny));
  drag.el.dataset.x = nx; drag.el.dataset.y = ny;
  drag.el.style.left = (nx * 100) + '%';
  drag.el.style.top  = (ny * 100) + '%';
}
function onDragUp() {
  document.removeEventListener('mousemove', onDragMove);
  document.removeEventListener('mouseup', onDragUp);
  drag = null;
}

let resize = null;
function startResize(e, el) {
  const layer = el.parentElement;
  const r = layerMetrics(layer);
  resize = {
    el, r, sx: e.clientX, sy: e.clientY,
    ow: parseFloat(el.dataset.w), oh: parseFloat(el.dataset.h),
  };
  document.addEventListener('mousemove', onResizeMove);
  document.addEventListener('mouseup', onResizeUp);
}
function onResizeMove(e) {
  if (!resize) return;
  let nw = resize.ow + (e.clientX - resize.sx) / resize.r.width;
  let nh = resize.oh + (e.clientY - resize.sy) / resize.r.height;
  nw = Math.max(0.03, Math.min(1, nw));
  nh = Math.max(0.02, Math.min(1, nh));
  resize.el.dataset.w = nw; resize.el.dataset.h = nh;
  resize.el.style.width  = (nw * 100) + '%';
  resize.el.style.height = (nh * 100) + '%';
}
function onResizeUp() {
  document.removeEventListener('mousemove', onResizeMove);
  document.removeEventListener('mouseup', onResizeUp);
  resize = null;
}

/* ── Selection ── */
function selectEl(el) {
  if (selectedEl) selectedEl.classList.remove('selected');
  selectedEl = el;
  if (el) el.classList.add('selected');
  $('deleteSelBtn').disabled = !el;
  syncStyleButtons(el);
}
function deleteSelected() {
  if (!selectedEl) return;
  removeOverlay(selectedEl);
  selectEl(null);
}

function removeOverlay(el) {
  const key = el.dataset.img;
  if (key) delete imageFiles[key];
  const i = history.indexOf(el);
  if (i !== -1) history.splice(i, 1);
  el.remove();
  $('undoBtn').disabled = history.length === 0;
}

function undoLast() {
  const el = history.pop();
  if (el) {
    if (el === selectedEl) selectEl(null);
    const key = el.dataset.img;
    if (key) delete imageFiles[key];
    el.remove();
  }
  $('undoBtn').disabled = history.length === 0;
}

/* ── Save ── */
function saveEdits() {
  const ops = [];
  document.querySelectorAll('.edit-layer').forEach(layer => {
    const pidx = parseInt(layer.dataset.page);
    layer.querySelectorAll('.ov').forEach(el => {
      const type = el.dataset.type;
      const base = {
        page: pidx,
        x: parseFloat(el.dataset.x),
        y: parseFloat(el.dataset.y),
        w: parseFloat(el.dataset.w) || 0,
        h: parseFloat(el.dataset.h) || 0,
      };
      if (type === 'edit' || type === 'text') {
        const text = el.textContent.trim();
        if (!text) return;
        ops.push({ ...base, type, text,
                   size: parseFloat(el.dataset.size) || 14,
                   color: el.dataset.color || '#000000',
                   font:   el.dataset.font || '',
                   bold:   !!el.dataset.bold,
                   italic: !!el.dataset.italic,
                   serif:  !!el.dataset.serif,
                   mono:   !!el.dataset.mono,
                   underline: !!el.dataset.under,
                   strike: !!el.dataset.strike });
      } else if (type === 'whiteout') {
        if (base.w > 0.003) ops.push({ ...base, type });
      } else if (type === 'highlight') {
        if (base.w > 0.003) ops.push({ ...base, type, color: el.dataset.color || '#ffeb3b' });
      } else if (type === 'draw') {
        let pts = [];
        try { pts = JSON.parse(el.dataset.points || '[]'); } catch (_) {}
        if (pts.length >= 2) {
          ops.push({ page: pidx, type, points: pts,
                     color: el.dataset.color || '#000000',
                     width: parseFloat(el.dataset.width) || 2 });
        }
      } else if (type === 'image') {
        ops.push({ ...base, type, img: el.dataset.img });
      }
    });
  });

  if (ops.length === 0) {
    showError('No edits to save yet. Add or change something first.');
    return;
  }

  const fd = new FormData();
  fd.append('session_id', sessionId);
  fd.append('payload', JSON.stringify(ops));
  for (const key in imageFiles) fd.append(key, imageFiles[key]);

  $('editorMain').hidden = true;
  $('loadingWrap').hidden = false;
  $('loadingLabel').textContent = 'Saving your edited PDF…';

  fetch('/api/edit/save', { method: 'POST', body: fd })
    .then(async res => {
      $('loadingWrap').hidden = true;
      if (!res.ok) {
        const d = await res.json().catch(() => ({ error: 'HTTP ' + res.status }));
        return showError(d.error || 'Unknown error');
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = $('downloadLink');
      link.href = url;
      link.download = 'edited.pdf';
      $('resultBox').hidden = false;
    })
    .catch(err => { $('loadingWrap').hidden = true; showError(err.message); });
}

function showError(msg) {
  $('errorMsg').textContent = msg;
  $('errorBox').hidden = false;
}
