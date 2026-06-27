/* ── State ── */
let selectedFiles = [];
let sessionId     = null;
let pageOrder     = [];

/* ── DOM helpers ── */
const $   = id => document.getElementById(id);
const show = id => { const el = $(id); if (el) el.hidden = false; };
const hide = id => { const el = $(id); if (el) el.hidden = true; };

/* ── Init ── */
document.addEventListener('DOMContentLoaded', () => {
  if (typeof TOOL_ID === 'undefined') return; // home page

  const zone  = $('uploadZone');
  const input = $('fileInput');

  zone.addEventListener('click', e => {
    if (e.target.closest('.link-btn') || e.target.closest('.btn-add-more')) return;
    input.click();
  });

  input.addEventListener('change', () => {
    handleFiles(Array.from(input.files));
    input.value = '';
  });

  zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', ()  => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    handleFiles(Array.from(e.dataTransfer.files));
  });

  // Level / quality card selection
  document.querySelectorAll('.compress-levels').forEach(group => {
    group.querySelectorAll('.level-card').forEach(card => {
      card.addEventListener('click', () => {
        group.querySelectorAll('.level-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
      });
    });
  });

  // Enter key in split page-range input triggers submit
  const pr = $('pageRange');
  if (pr) {
    pr.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); processFiles(); }
    });
  }

  // Enter key in rotate page-range input
  const rpr = $('rotatePageRange');
  if (rpr) {
    rpr.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); processFiles(); }
    });
  }
});

/* ── File handling ── */
function handleFiles(incoming) {
  if (MULTIPLE) {
    selectedFiles.push(...incoming);
  } else {
    selectedFiles = [incoming[0]];
  }
  renderFileList();

  if (TOOL_ID === 'reorder') {
    uploadForPreview(selectedFiles[0]);
    return;
  }

  show('optionsBox');
  show('actionBar');
  updateMergeButton();
}

function renderFileList() {
  const list = $('fileList');
  if (!list) return;
  if (selectedFiles.length === 0) { list.hidden = true; return; }

  list.hidden = false;

  const rows = selectedFiles.map((f, i) => `
    <div class="file-item">
      <span class="file-icon">${fileIcon(f.name)}</span>
      <span class="file-name">${esc(f.name)}</span>
      <span class="file-size">${formatSize(f.size)}</span>
      <button class="file-remove" onclick="removeFile(${i})" title="Remove">✕</button>
    </div>
  `).join('');

  // "Add more files" button for multi-upload tools
  const addMore = MULTIPLE ? `
    <div class="add-more-row">
      <button class="btn-add-more" onclick="document.getElementById('fileInput').click()">
        + Add more files
      </button>
    </div>
  ` : '';

  // Merge hint when fewer than 2 files
  const mergeHint = (TOOL_ID === 'merge' && selectedFiles.length < 2) ? `
    <div class="merge-hint">Add at least one more PDF to merge.</div>
  ` : '';

  list.innerHTML = rows + mergeHint + addMore;
}

function removeFile(i) {
  selectedFiles.splice(i, 1);
  renderFileList();
  updateMergeButton();
  if (selectedFiles.length === 0) {
    hide('optionsBox');
    hide('actionBar');
    hide('reorderSection');
  }
}

function updateMergeButton() {
  if (TOOL_ID !== 'merge') return;
  const btn = $('processBtn');
  if (!btn) return;
  btn.disabled = selectedFiles.length < 2;
}

/* ── Process ── */
function processFiles() {
  if (selectedFiles.length === 0) return;
  if (TOOL_ID === 'merge' && selectedFiles.length < 2) return;

  const fd = new FormData();
  selectedFiles.forEach(f => fd.append('files', f));

  if (TOOL_ID === 'split') {
    const mode = document.querySelector('input[name="splitMode"]:checked');
    if (mode && mode.value === 'range') {
      const range = $('pageRange') ? $('pageRange').value.trim() : '';
      if (range) fd.append('pages', range);
    }
  } else if (TOOL_ID === 'compress') {
    const lvl = document.querySelector('input[name="compressLevel"]:checked');
    if (lvl) fd.append('level', lvl.value);
  } else if (TOOL_ID === 'pdf-to-jpg') {
    const dpi = document.querySelector('input[name="dpi"]:checked');
    if (dpi) fd.append('dpi', dpi.value);
  } else if (TOOL_ID === 'rotate') {
    const deg = document.querySelector('input[name="degrees"]:checked');
    if (deg) fd.append('degrees', deg.value);
    const rpr = $('rotatePageRange');
    if (rpr && rpr.value.trim()) fd.append('pages', rpr.value.trim());
  }

  startProcessing();
  fetch(`/api/process/${TOOL_ID}`, { method: 'POST', body: fd })
    .then(handleResponse)
    .catch(err => showError(err.message));
}

function processReorder() {
  if (!sessionId && selectedFiles.length === 0) return;

  const fd = new FormData();
  if (sessionId) {
    fd.append('session_id', sessionId);
  } else {
    fd.append('files', selectedFiles[0]);
  }
  fd.append('order', pageOrder.join(','));

  startProcessing();
  fetch('/api/process/reorder', { method: 'POST', body: fd })
    .then(handleResponse)
    .catch(err => showError(err.message));
}

function startProcessing() {
  hide('actionBar');
  hide('reorderSection');
  hide('errorBox');
  hide('resultBox');
  show('progressWrap');
}

async function handleResponse(res) {
  hide('progressWrap');

  if (!res.ok) {
    const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
    showError(data.error || 'Unknown error');
    return;
  }

  // Read size-reduction info from compress
  const origSize   = res.headers.get('X-Original-Size');
  const resultSize = res.headers.get('X-Result-Size');

  const blob = await res.blob();
  const url  = URL.createObjectURL(blob);
  const cd   = res.headers.get('Content-Disposition') || '';
  const nameMatch = cd.match(/filename="?([^"]+)"?/);
  const filename  = nameMatch ? nameMatch[1] : 'result';

  const link = $('downloadLink');
  link.href     = url;
  link.download = filename;

  // Show an inline preview for single-image results (e.g. background remover)
  const previewWrap = $('resultPreview');
  const previewImg  = $('resultPreviewImg');
  if (previewWrap && previewImg) {
    if (blob.type && blob.type.startsWith('image/')) {
      previewImg.src = url;
      previewWrap.hidden = false;
    } else {
      previewWrap.hidden = true;
      previewImg.removeAttribute('src');
    }
  }

  if (origSize && resultSize) {
    const orig = parseInt(origSize);
    const rslt = parseInt(resultSize);
    const saved = orig - rslt;
    const pct   = ((saved / orig) * 100).toFixed(1);
    if (saved > 0) {
      $('resultMsg').innerHTML =
        `${formatSize(orig)} → <strong>${formatSize(rslt)}</strong> &mdash; saved ${pct}%`;
    } else {
      $('resultMsg').textContent = `${filename} is ready. (File was already well-compressed.)`;
    }
  } else {
    $('resultMsg').textContent = `${filename} is ready to save.`;
  }

  show('resultBox');
}

function showError(msg) {
  hide('progressWrap');
  show('actionBar');
  $('errorMsg').textContent = msg;
  show('errorBox');
}

function resetTool() {
  selectedFiles = [];
  sessionId     = null;
  pageOrder     = [];

  hide('fileList');
  hide('optionsBox');
  hide('actionBar');
  hide('progressWrap');
  hide('resultBox');
  hide('errorBox');
  hide('reorderSection');

  const grid = $('thumbnailGrid');
  if (grid) grid.innerHTML = '';

  const previewWrap = $('resultPreview');
  if (previewWrap) previewWrap.hidden = true;

  renderFileList();
}

/* ── Reorder preview ── */
function uploadForPreview(file) {
  hide('actionBar');
  show('progressWrap');
  $('progressLabel').textContent = 'Loading page thumbnails…';

  const fd = new FormData();
  fd.append('files', file);

  fetch('/api/preview-upload', { method: 'POST', body: fd })
    .then(r => r.json())
    .then(data => {
      hide('progressWrap');
      if (data.error) { showError(data.error); return; }

      sessionId = data.session_id;
      pageOrder = Array.from({ length: data.page_count }, (_, i) => i + 1);
      renderThumbnails(data.thumbnails);
      show('reorderSection');
      show('actionBar');
    })
    .catch(err => {
      hide('progressWrap');
      showError(err.message);
    });
}

function renderThumbnails(thumbs) {
  const grid = $('thumbnailGrid');
  grid.innerHTML = thumbs.map((t, i) => `
    <div class="thumb-card" data-page="${i + 1}">
      <img class="thumb-img" src="data:image/png;base64,${t}" alt="Page ${i + 1}" loading="lazy">
      <div class="thumb-label">Page ${i + 1}</div>
    </div>
  `).join('');

  if (typeof Sortable !== 'undefined') {
    Sortable.create(grid, {
      animation: 180,
      ghostClass: 'sortable-ghost',
      chosenClass: 'sortable-chosen',
      onEnd: updatePageOrder,
    });
  }
}

function updatePageOrder() {
  pageOrder = Array.from(document.querySelectorAll('.thumb-card'))
    .map(c => parseInt(c.dataset.page));
}

/* ── Split mode toggle ── */
function toggleSplitMode(val) {
  const ri = $('rangeInput');
  if (ri) ri.style.display = val === 'range' ? 'block' : 'none';
}

/* ── Helpers ── */
function formatSize(bytes) {
  if (bytes < 1024)        return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

function fileIcon(name) {
  const ext = name.split('.').pop().toLowerCase();
  const map = {
    pdf:'📄', docx:'📝', doc:'📝', xlsx:'📊', xls:'📊',
    jpg:'🖼️', jpeg:'🖼️', png:'🖼️', gif:'🖼️', bmp:'🖼️',
    tiff:'🖼️', tif:'🖼️', webp:'🖼️', zip:'📦',
  };
  return map[ext] || '📁';
}

function esc(str) {
  return str
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
