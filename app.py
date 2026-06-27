import os
import io
import re
import json
import uuid
import hashlib
import time
import shutil
import tempfile
import zipfile
import base64
from flask import Flask, render_template, request, send_file, jsonify, redirect, url_for
import fitz  # PyMuPDF

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024  # 300 MB

TEMP_DIR = os.path.join(tempfile.gettempdir(), 'pdf_tools_sessions')
os.makedirs(TEMP_DIR, exist_ok=True)

# ─── Tool Registry ────────────────────────────────────────────────────────────

TOOLS = [
    {
        'id': 'merge', 'name': 'Merge PDF', 'icon': 'merge',
        'color': '#e74c3c', 'bg': '#fdf2f2',
        'desc': 'Combine multiple PDF files into one document',
        'accept': '.pdf', 'multiple': True, 'category': 'organize',
    },
    {
        'id': 'split', 'name': 'Split PDF', 'icon': 'split',
        'color': '#e67e22', 'bg': '#fef9f2',
        'desc': 'Extract pages or split into separate PDF files',
        'accept': '.pdf', 'multiple': True, 'category': 'organize',
    },
    {
        'id': 'reorder', 'name': 'Reorder Pages', 'icon': 'reorder',
        'color': '#27ae60', 'bg': '#f2fdf5',
        'desc': 'Drag and drop to rearrange pages in your PDF',
        'accept': '.pdf', 'multiple': False, 'category': 'organize',
    },
    {
        'id': 'rotate', 'name': 'Rotate PDF', 'icon': 'rotate',
        'color': '#8e44ad', 'bg': '#faf2fd',
        'desc': 'Rotate all or specific pages in your PDFs',
        'accept': '.pdf', 'multiple': True, 'category': 'organize',
    },
    {
        'id': 'compress', 'name': 'Compress PDF', 'icon': 'compress',
        'color': '#f39c12', 'bg': '#fefcf2',
        'desc': 'Reduce PDF file size while keeping quality',
        'accept': '.pdf', 'multiple': True, 'category': 'optimize',
    },
    {
        'id': 'optimize', 'name': 'Optimize PDF', 'icon': 'optimize',
        'color': '#16a085', 'bg': '#f2fdfb',
        'desc': 'Clean and optimize PDF structure for faster loading',
        'accept': '.pdf', 'multiple': True, 'category': 'optimize',
    },
    {
        'id': 'jpg-to-pdf', 'name': 'JPG to PDF', 'icon': 'img2pdf',
        'color': '#2980b9', 'bg': '#f2f8fd',
        'desc': 'Convert JPG, PNG, BMP and other images to PDF',
        'accept': '.jpg,.jpeg,.png,.bmp,.tiff,.tif,.gif,.webp', 'multiple': True,
        'category': 'convert',
    },
    {
        'id': 'remove-bg', 'name': 'Remove Background', 'icon': 'removebg',
        'color': '#9b59b6', 'bg': '#f9f2fc',
        'desc': 'Erase the background from photos of people or products — outputs transparent PNG',
        'accept': '.jpg,.jpeg,.png,.bmp,.webp', 'multiple': True,
        'category': 'convert',
    },
    {
        'id': 'clean-scan', 'name': 'Clean Scan', 'icon': 'cleanscan',
        'color': '#0d9488', 'bg': '#f0fdfa',
        'desc': 'Whiten the paper and sharpen text on scanned documents and receipts',
        'accept': '.jpg,.jpeg,.png,.bmp,.webp,.tiff,.tif', 'multiple': True,
        'category': 'convert',
    },
    {
        'id': 'doc-transparent', 'name': 'Document to Transparent', 'icon': 'doctransparent',
        'color': '#6366f1', 'bg': '#f1f2fe',
        'desc': 'Keep only the ink and make the paper transparent — great for stamps & signatures',
        'accept': '.jpg,.jpeg,.png,.bmp,.webp,.tiff,.tif', 'multiple': True,
        'category': 'convert',
    },
    {
        'id': 'pdf-to-jpg', 'name': 'PDF to JPG', 'icon': 'pdf2img',
        'color': '#c0392b', 'bg': '#fdf2f2',
        'desc': 'Convert each PDF page into a high-quality image',
        'accept': '.pdf', 'multiple': True, 'category': 'convert',
    },
    {
        'id': 'word-to-pdf', 'name': 'Word to PDF', 'icon': 'word2pdf',
        'color': '#2c3e50', 'bg': '#f5f6f7',
        'desc': 'Convert Word documents (.docx) to PDF format',
        'accept': '.docx,.doc', 'multiple': True, 'category': 'convert',
    },
    {
        'id': 'excel-to-pdf', 'name': 'Excel to PDF', 'icon': 'excel2pdf',
        'color': '#1a8a4a', 'bg': '#f2fdf5',
        'desc': 'Convert Excel spreadsheets (.xlsx) to PDF format',
        'accept': '.xlsx,.xls', 'multiple': True, 'category': 'convert',
    },
    {
        'id': 'pdf-to-word', 'name': 'PDF to Word', 'icon': 'pdf2word',
        'color': '#d35400', 'bg': '#fdf5f2',
        'desc': 'Extract PDF text and content into a Word document',
        'accept': '.pdf', 'multiple': True, 'category': 'convert',
    },
    {
        'id': 'edit', 'name': 'Edit PDF', 'icon': 'edit',
        'color': '#e84393', 'bg': '#fdf2f8',
        'desc': 'Edit existing text, add text, whiteout & place signatures',
        'accept': '.pdf', 'multiple': False, 'category': 'organize',
        'custom_url': '/editor',
    },
    {
        'id': 'redact', 'name': 'Redact PDF', 'icon': 'redact',
        'color': '#1f2937', 'bg': '#f3f4f6',
        'desc': 'Permanently remove sensitive text — true redaction, not just black boxes',
        'accept': '.pdf', 'multiple': False, 'category': 'organize',
        'custom_url': '/redact',
    },
]

TOOL_MAP = {t['id']: t for t in TOOLS}

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html', tools=TOOLS)


@app.route('/tool/<tool_id>')
def tool(tool_id):
    t = TOOL_MAP.get(tool_id)
    if not t:
        return redirect(url_for('index'))
    if t.get('custom_url'):
        return redirect(t['custom_url'])
    return render_template('tool.html', tool=t)


@app.route('/editor')
def editor():
    return render_template('editor.html')


@app.route('/redact')
def redact_page():
    return render_template('redact.html')


@app.route('/api/redact/apply', methods=['POST'])
def redact_apply():
    """Permanently remove content under each box and every match of the search
    terms, then fill black. Uses PyMuPDF redaction so the underlying text and
    images are truly destroyed — not merely covered."""
    session_id = request.form.get('session_id', '').strip()
    payload    = request.form.get('payload', '')
    terms_raw  = request.form.get('terms', '')

    if session_id:
        _validate_session_id(session_id)
        pdf_path = os.path.join(TEMP_DIR, session_id, 'input.pdf')
        if not os.path.exists(pdf_path):
            return jsonify({'error': 'Session expired — please re-upload the file'}), 400
        doc = fitz.open(pdf_path)
    else:
        f = request.files.get('files')
        if not f:
            return jsonify({'error': 'No file uploaded'}), 400
        _validate_ext(f.filename, {'pdf'})
        doc = fitz.open(stream=f.read(), filetype='pdf')

    try:
        boxes = json.loads(payload) if payload else []
    except json.JSONDecodeError:
        boxes = []

    count = 0
    touched = set()

    # ── User-drawn boxes ──
    for op in boxes:
        pidx = op.get('page', 0)
        if not (0 <= pidx < doc.page_count):
            continue
        page = doc[pidx]
        pw, ph = page.rect.width, page.rect.height
        rect = fitz.Rect(op['x'] * pw, op['y'] * ph,
                         (op['x'] + op['w']) * pw, (op['y'] + op['h']) * ph)
        if rect.is_empty or rect.width < 1 or rect.height < 1:
            continue
        page.add_redact_annot(rect, fill=(0, 0, 0))
        touched.add(pidx)
        count += 1

    # ── Find & redact every occurrence of each search term ──
    terms = [t.strip() for t in re.split(r'[\n,]', terms_raw) if t.strip()]
    if terms:
        for pidx, page in enumerate(doc):
            for term in terms:
                for rect in page.search_for(term):
                    page.add_redact_annot(rect, fill=(0, 0, 0))
                    touched.add(pidx)
                    count += 1

    if count == 0:
        doc.close()
        return jsonify({'error': 'Nothing to redact — draw a box or enter a '
                                 'search term first.'}), 400

    # ── Apply: this is the step that permanently removes the content ──
    for pidx in touched:
        page = doc[pidx]
        try:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
        except (AttributeError, TypeError):
            page.apply_redactions()

    output = io.BytesIO()
    doc.save(output, garbage=4, deflate=True)
    doc.close()

    if session_id:
        shutil.rmtree(os.path.join(TEMP_DIR, session_id), ignore_errors=True)

    output.seek(0)
    resp = send_file(output, mimetype='application/pdf',
                     as_attachment=True, download_name='redacted.pdf')
    resp.headers['X-Redaction-Count'] = str(count)
    return resp


EDIT_RENDER_SCALE = 2.0  # 144 DPI render for a crisp editing canvas


@app.route('/api/edit/load', methods=['POST'])
def edit_load():
    """Upload a PDF: render each page to a PNG and extract editable text spans.
    Coordinates are returned normalized (0..1) so the front-end is resolution
    independent."""
    f = request.files.get('files')
    if not f:
        return jsonify({'error': 'No file uploaded'}), 400

    _validate_ext(f.filename, {'pdf'})
    _cleanup_old_sessions()

    session_id = str(uuid.uuid4())
    session_dir = os.path.join(TEMP_DIR, session_id)
    os.makedirs(session_dir)
    pdf_path = os.path.join(session_dir, 'input.pdf')
    f.save(pdf_path)

    doc = fitz.open(pdf_path)
    mat = fitz.Matrix(EDIT_RENDER_SCALE, EDIT_RENDER_SCALE)
    pages = []

    for page in doc:
        pw, ph = page.rect.width, page.rect.height
        pix = page.get_pixmap(matrix=mat)
        img_b64 = base64.b64encode(pix.tobytes('png')).decode()

        spans = []
        data = page.get_text('dict')
        for block in data.get('blocks', []):
            if block.get('type') != 0:
                continue
            for line in block.get('lines', []):
                for span in line.get('spans', []):
                    text = span.get('text', '')
                    if not text.strip():
                        continue
                    x0, y0, x1, y1 = span['bbox']
                    c = span.get('color', 0)
                    flags = span.get('flags', 0)
                    spans.append({
                        'text': text,
                        'x': x0 / pw, 'y': y0 / ph,
                        'w': (x1 - x0) / pw, 'h': (y1 - y0) / ph,
                        'size': span.get('size', 11),
                        'color': '#%02x%02x%02x' % ((c >> 16) & 255, (c >> 8) & 255, c & 255),
                        'font': span.get('font', ''),
                        # Style flags (PyMuPDF span flag bits)
                        'italic': bool(flags & 2),
                        'serif':  bool(flags & 4),
                        'mono':   bool(flags & 8),
                        'bold':   bool(flags & 16),
                    })

        pages.append({
            'image': img_b64,
            'width_pt': pw,
            'height_pt': ph,
            'spans': spans,
        })

    doc.close()
    return jsonify({'session_id': session_id, 'pages': pages})


@app.route('/api/edit/save', methods=['POST'])
def edit_save():
    """Apply edit operations and return the final flattened PDF.

    operations: list of dicts, each with 'page' index and 'type':
      - 'edit'     : replace an existing text span (redact + reinsert)
      - 'text'     : add new text
      - 'whiteout' : cover a rectangle with white
      - 'image'    : place an uploaded image
    All rect coords are normalized (0..1) relative to the page.
    """
    payload = request.form.get('payload')
    session_id = request.form.get('session_id', '').strip()
    if not payload:
        return jsonify({'error': 'Missing edit data'}), 400

    try:
        ops = json.loads(payload)
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid edit data'}), 400

    if session_id:
        _validate_session_id(session_id)
        pdf_path = os.path.join(TEMP_DIR, session_id, 'input.pdf')
        if not os.path.exists(pdf_path):
            return jsonify({'error': 'Session expired — please re-upload the file'}), 400
        doc = fitz.open(pdf_path)
    else:
        f = request.files.get('files')
        if not f:
            return jsonify({'error': 'No file uploaded'}), 400
        _validate_ext(f.filename, {'pdf'})
        doc = fitz.open(stream=f.read(), filetype='pdf')

    # Uploaded images for 'image' ops, keyed by the id used in the payload.
    images = {}
    for key in request.files:
        if key.startswith('img_'):
            images[key] = request.files[key].read()

    def _rgb(hex_str):
        h = (hex_str or '#000000').lstrip('#')
        if len(h) != 6:
            return (0, 0, 0)
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


    # ── Pass 1: redactions (must be applied before drawing new content) ──
    pages_needing_redaction = set()
    for op in ops:
        if op.get('type') in ('edit', 'whiteout'):
            pidx = op.get('page', 0)
            if 0 <= pidx < doc.page_count:
                page = doc[pidx]
                pw, ph = page.rect.width, page.rect.height
                rect = fitz.Rect(op['x'] * pw, op['y'] * ph,
                                 (op['x'] + op['w']) * pw, (op['y'] + op['h']) * ph)
                page.add_redact_annot(rect, fill=(1, 1, 1))
                pages_needing_redaction.add(pidx)

    for pidx in pages_needing_redaction:
        doc[pidx].apply_redactions()

    # ── Pass 2: add new text and images ──
    for op in ops:
        t = op.get('type')
        pidx = op.get('page', 0)
        if not (0 <= pidx < doc.page_count):
            continue
        page = doc[pidx]
        pw, ph = page.rect.width, page.rect.height

        if t in ('edit', 'text'):
            text = op.get('text', '')
            if not text:
                continue
            size = float(op.get('size', 11))
            color = _rgb(op.get('color', '#000000'))
            fontname, fontfile = _resolve_font(op)
            x0 = op['x'] * pw
            y0 = op['y'] * ph
            y1 = (op['y'] + op['h']) * ph if op.get('h') else y0 + size * 1.2
            # Insert with room to the right edge so longer replacements fit.
            rect = fitz.Rect(x0, y0, pw - 4, max(y1, y0 + size * 1.3))
            kw = dict(fontsize=size, fontname=fontname, color=color)
            if fontfile:
                kw['fontfile'] = fontfile
            rc = page.insert_textbox(rect, text, align=0, **kw)
            if rc < 0:
                page.insert_text((x0, y1 - size * 0.2), text, **kw)

            # underline / strikethrough (drawn lines, since PDFs store them so)
            if op.get('underline') or op.get('strike'):
                try:
                    if fontfile:
                        tw = fitz.Font(fontfile=fontfile).text_length(text, size)
                    else:
                        tw = fitz.get_text_length(text, fontname=fontname, fontsize=size)
                except Exception:
                    tw = size * 0.5 * len(text)
                lw = max(0.5, size * 0.06)
                if op.get('underline'):
                    uy = y0 + size * 1.02
                    page.draw_line((x0, uy), (x0 + tw, uy), color=color, width=lw)
                if op.get('strike'):
                    sy = y0 + size * 0.62
                    page.draw_line((x0, sy), (x0 + tw, sy), color=color, width=lw)

        elif t == 'highlight':
            rect = fitz.Rect(op['x'] * pw, op['y'] * ph,
                             (op['x'] + op['w']) * pw, (op['y'] + op['h']) * ph)
            try:
                page.draw_rect(rect, color=None, fill=_rgb(op.get('color', '#ffeb3b')),
                               fill_opacity=0.35, stroke_opacity=0)
            except TypeError:
                # Older PyMuPDF without opacity kwargs — use a highlight annot.
                page.add_highlight_annot(rect)

        elif t == 'draw':
            pts = op.get('points', [])
            if len(pts) >= 2:
                points = [fitz.Point(px * pw, py * ph) for px, py in pts]
                try:
                    page.draw_polyline(points, color=_rgb(op.get('color', '#000000')),
                                       width=float(op.get('width', 2)))
                except Exception:
                    pass

        elif t == 'image':
            img_key = op.get('img')
            if img_key not in images:
                continue
            rect = fitz.Rect(op['x'] * pw, op['y'] * ph,
                             (op['x'] + op['w']) * pw, (op['y'] + op['h']) * ph)
            try:
                page.insert_image(rect, stream=images[img_key], keep_proportion=True)
            except Exception:
                pass

    output = io.BytesIO()
    doc.save(output, garbage=3, deflate=True)
    doc.close()

    if session_id:
        shutil.rmtree(os.path.join(TEMP_DIR, session_id), ignore_errors=True)

    output.seek(0)
    return send_file(output, mimetype='application/pdf',
                     as_attachment=True, download_name='edited.pdf')


@app.route('/api/process/<tool_id>', methods=['POST'])
def process(tool_id):
    try:
        handlers = {
            'merge':        do_merge,
            'split':        do_split,
            'compress':     do_compress,
            'optimize':     do_optimize,
            'rotate':       do_rotate,
            'jpg-to-pdf':   do_jpg_to_pdf,
            'remove-bg':    do_remove_bg,
            'clean-scan':   do_clean_scan,
            'doc-transparent': do_doc_transparent,
            'pdf-to-jpg':   do_pdf_to_jpg,
            'word-to-pdf':  do_word_to_pdf,
            'excel-to-pdf': do_excel_to_pdf,
            'pdf-to-word':  do_pdf_to_word,
            'reorder':      do_reorder,
        }
        handler = handlers.get(tool_id)
        if not handler:
            return jsonify({'error': 'Unknown tool'}), 400
        return handler()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/preview-upload', methods=['POST'])
def preview_upload():
    """Upload PDF and return page thumbnails for the reorder tool."""
    f = request.files.get('files')
    if not f:
        return jsonify({'error': 'No file uploaded'}), 400

    _validate_ext(f.filename, {'pdf'})
    _cleanup_old_sessions()

    session_id = str(uuid.uuid4())
    session_dir = os.path.join(TEMP_DIR, session_id)
    os.makedirs(session_dir)

    pdf_path = os.path.join(session_dir, 'input.pdf')
    f.save(pdf_path)

    doc = fitz.open(pdf_path)
    total = doc.page_count
    thumbnails = []
    mat = fitz.Matrix(0.4, 0.4)

    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        thumbnails.append(base64.b64encode(pix.tobytes('png')).decode())

    doc.close()

    return jsonify({
        'session_id': session_id,
        'page_count': total,
        'thumbnails': thumbnails,
    })


# ─── Batch helpers ───────────────────────────────────────────────────────────

def _get_files(allowed_exts):
    """Return validated list of uploaded files (raises ValueError on bad ext)."""
    files = [f for f in request.files.getlist('files') if f and f.filename]
    if not files:
        raise ValueError('No file uploaded')
    for f in files:
        _validate_ext(f.filename, allowed_exts)
    return files


def _stem(filename):
    return os.path.splitext(os.path.basename(filename or 'file'))[0]


def _send_results(results, zip_name='results.zip'):
    """results = list of (filename, bytes, mimetype).
    One file → send directly; many → bundle into a ZIP."""
    if len(results) == 1:
        name, data, mt = results[0]
        return send_file(io.BytesIO(data), mimetype=mt,
                         as_attachment=True, download_name=name)
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        used = set()
        for name, data, _ in results:
            # avoid duplicate names inside the zip
            base, ext = os.path.splitext(name)
            n, candidate = 1, name
            while candidate in used:
                n += 1
                candidate = f'{base}_{n}{ext}'
            used.add(candidate)
            zf.writestr(candidate, data)
    zip_buf.seek(0)
    return send_file(zip_buf, mimetype='application/zip',
                     as_attachment=True, download_name=zip_name)


# ─── Tool Handlers ───────────────────────────────────────────────────────────

def do_merge():
    files = _get_files({'pdf'})
    if len(files) < 2:
        return jsonify({'error': 'Please upload at least 2 PDF files'}), 400

    merged = fitz.open()
    for f in files:
        doc = fitz.open(stream=f.read(), filetype='pdf')
        merged.insert_pdf(doc)
        doc.close()

    output = io.BytesIO()
    merged.save(output, garbage=4, deflate=True)
    merged.close()
    output.seek(0)
    return send_file(output, mimetype='application/pdf',
                     as_attachment=True, download_name='merged.pdf')


def do_split():
    files = _get_files({'pdf'})
    page_range = request.form.get('pages', '').strip()

    results = []
    for f in files:
        stem = _stem(f.filename)
        doc = fitz.open(stream=f.read(), filetype='pdf')
        total = doc.page_count

        if page_range:
            pages = _parse_page_range(page_range, total)
            if not pages:
                doc.close()
                return jsonify({'error': f'No valid pages in range "{page_range}" '
                                         f'for "{f.filename}" ({total} pages).'}), 400
            new_doc = fitz.open()
            for p in pages:
                new_doc.insert_pdf(doc, from_page=p - 1, to_page=p - 1)
            buf = io.BytesIO()
            new_doc.save(buf, garbage=3, deflate=True)
            new_doc.close()
            results.append((f'{stem}_split.pdf', buf.getvalue(), 'application/pdf'))
        else:
            # every page as its own PDF
            for i in range(total):
                pg = fitz.open()
                pg.insert_pdf(doc, from_page=i, to_page=i)
                pb = io.BytesIO()
                pg.save(pb)
                pg.close()
                results.append((f'{stem}_page_{i + 1:03d}.pdf', pb.getvalue(),
                                'application/pdf'))
        doc.close()

    return _send_results(results, zip_name='split_pages.zip')


def do_compress():
    files = _get_files({'pdf'})
    level = request.form.get('level', 'medium')

    total_orig = 0
    total_out  = 0
    results = []

    for f in files:
        data = f.read()
        total_orig += len(data)
        doc = fitz.open(stream=data, filetype='pdf')
        output = io.BytesIO()
        try:
            if level == 'high':
                _recompress_images(doc, quality=40)
                doc.save(output, garbage=4, deflate=True, clean=True,
                         deflate_images=True, deflate_fonts=True)
            elif level == 'medium':
                _recompress_images(doc, quality=65)
                doc.save(output, garbage=3, deflate=True, deflate_images=True)
            else:
                doc.save(output, garbage=2, deflate=True)
        except TypeError:
            _recompress_images(doc, quality=65 if level != 'low' else 80)
            doc.save(output, garbage=3, deflate=True)
        doc.close()
        out_bytes = output.getvalue()
        total_out += len(out_bytes)
        results.append((f'{_stem(f.filename)}_compressed.pdf', out_bytes,
                        'application/pdf'))

    resp = _send_results(results, zip_name='compressed.zip')
    resp.headers['X-Original-Size'] = str(total_orig)
    resp.headers['X-Result-Size']   = str(total_out)
    return resp


def do_optimize():
    files = _get_files({'pdf'})
    results = []
    for f in files:
        doc = fitz.open(stream=f.read(), filetype='pdf')
        output = io.BytesIO()
        try:
            doc.save(output, garbage=4, deflate=True, clean=True,
                     deflate_images=True, deflate_fonts=True)
        except TypeError:
            doc.save(output, garbage=4, deflate=True, clean=True)
        doc.close()
        results.append((f'{_stem(f.filename)}_optimized.pdf', output.getvalue(),
                        'application/pdf'))
    return _send_results(results, zip_name='optimized.zip')


def do_rotate():
    files = _get_files({'pdf'})

    try:
        degrees = int(request.form.get('degrees', 90))
    except ValueError:
        return jsonify({'error': 'Invalid rotation angle'}), 400
    if degrees not in (90, 180, 270):
        return jsonify({'error': 'Rotation must be 90, 180, or 270 degrees'}), 400

    page_range = request.form.get('pages', '').strip()
    results = []

    for f in files:
        doc = fitz.open(stream=f.read(), filetype='pdf')
        total = doc.page_count
        if page_range:
            pages_to_rotate = set(_parse_page_range(page_range, total))
        else:
            pages_to_rotate = set(range(1, total + 1))

        for i, page in enumerate(doc):
            if (i + 1) in pages_to_rotate:
                page.set_rotation((page.rotation + degrees) % 360)

        output = io.BytesIO()
        doc.save(output, garbage=3, deflate=True)
        doc.close()
        results.append((f'{_stem(f.filename)}_rotated.pdf', output.getvalue(),
                        'application/pdf'))

    return _send_results(results, zip_name='rotated.zip')


def do_reorder():
    session_id = request.form.get('session_id', '').strip()
    order_str  = request.form.get('order', '')

    if session_id:
        _validate_session_id(session_id)  # raises ValueError on bad input
        pdf_path = os.path.join(TEMP_DIR, session_id, 'input.pdf')
        if not os.path.exists(pdf_path):
            return jsonify({'error': 'Session expired — please re-upload the file'}), 400
        doc = fitz.open(pdf_path)
    else:
        f = request.files.get('files')
        if not f:
            return jsonify({'error': 'No file uploaded'}), 400
        _validate_ext(f.filename, {'pdf'})
        doc = fitz.open(stream=f.read(), filetype='pdf')

    if order_str:
        try:
            new_order = [int(x) - 1 for x in order_str.split(',')]
        except ValueError:
            doc.close()
            return jsonify({'error': 'Invalid page order'}), 400
        doc.select(new_order)

    output = io.BytesIO()
    doc.save(output, garbage=3, deflate=True)
    doc.close()

    if session_id:
        shutil.rmtree(os.path.join(TEMP_DIR, session_id), ignore_errors=True)

    output.seek(0)
    return send_file(output, mimetype='application/pdf',
                     as_attachment=True, download_name='reordered.pdf')


def do_jpg_to_pdf():
    files = _get_files({'jpg', 'jpeg', 'png', 'bmp', 'tiff', 'tif', 'gif', 'webp'})

    doc = fitz.open()
    for f in files:
        data = f.read()
        ext = os.path.splitext(f.filename)[1].lower().lstrip('.')
        fitz_type = 'jpeg' if ext in ('jpg', 'jpeg') else ext
        try:
            img_doc = fitz.open(stream=data, filetype=fitz_type)
            pdf_bytes = img_doc.convert_to_pdf()
            img_doc.close()
        except Exception:
            from PIL import Image as PILImage
            pil_img = PILImage.open(io.BytesIO(data)).convert('RGB')
            buf = io.BytesIO()
            pil_img.save(buf, format='JPEG', quality=95)
            img_doc = fitz.open(stream=buf.getvalue(), filetype='jpeg')
            pdf_bytes = img_doc.convert_to_pdf()
            img_doc.close()

        img_pdf = fitz.open('pdf', pdf_bytes)
        doc.insert_pdf(img_pdf)
        img_pdf.close()

    output = io.BytesIO()
    doc.save(output, garbage=3, deflate=True)
    doc.close()
    output.seek(0)
    return send_file(output, mimetype='application/pdf',
                     as_attachment=True, download_name='images.pdf')


_BG_SESSION = None


def _get_bg_session():
    """Lazily create and cache the rembg session (loads the model once)."""
    global _BG_SESSION
    if _BG_SESSION is None:
        from rembg import new_session
        _BG_SESSION = new_session('u2net')
    return _BG_SESSION


def do_remove_bg():
    files = _get_files({'jpg', 'jpeg', 'png', 'bmp', 'webp'})

    try:
        from rembg import remove
    except ImportError:
        return jsonify({
            'error': 'rembg is not installed.\n'
                     'Run:  pip install rembg onnxruntime'
        }), 500

    session = _get_bg_session()
    results = []
    for f in files:
        out_png = remove(f.read(), session=session)
        results.append((f'{_stem(f.filename)}_no_bg.png', out_png, 'image/png'))

    return _send_results(results, zip_name='no_background.zip')


_SCAN_EXTS = {'jpg', 'jpeg', 'png', 'bmp', 'webp', 'tiff', 'tif'}


def _normalize_background(gray_img):
    """Flatten uneven lighting: divide the image by a blurred estimate of the
    paper background so the paper becomes uniformly white. Returns a float
    numpy array in 0–255."""
    import numpy as np
    from PIL import ImageFilter
    arr = np.asarray(gray_img).astype(np.float32)
    # Large blur approximates the background (paper) brightness everywhere.
    radius = max(11, int(min(gray_img.size) * 0.04))
    bg = np.asarray(gray_img.filter(ImageFilter.GaussianBlur(radius=radius))
                    ).astype(np.float32)
    bg = np.clip(bg, 1.0, 255.0)
    norm = np.clip(arr / bg * 255.0, 0, 255)
    return norm


def do_clean_scan():
    files = _get_files(_SCAN_EXTS)
    import numpy as np
    from PIL import Image

    results = []
    for f in files:
        gray = Image.open(io.BytesIO(f.read())).convert('L')
        norm = _normalize_background(gray)
        # Contrast stretch: push the paper to pure white and darken the ink.
        lo, hi = 50.0, 210.0
        out = np.clip((norm - lo) * (255.0 / (hi - lo)), 0, 255).astype('uint8')
        out_img = Image.fromarray(out, mode='L')
        buf = io.BytesIO()
        out_img.save(buf, format='PNG', optimize=True)
        results.append((f'{_stem(f.filename)}_cleaned.png', buf.getvalue(),
                        'image/png'))

    return _send_results(results, zip_name='cleaned_scans.zip')


def do_doc_transparent():
    files = _get_files(_SCAN_EXTS)
    import numpy as np
    from PIL import Image

    keep_color = request.form.get('keep_color', 'false') == 'true'

    results = []
    for f in files:
        raw = f.read()
        color = Image.open(io.BytesIO(raw)).convert('RGB')
        gray = color.convert('L')
        norm = _normalize_background(gray)

        # Darkness → opacity. White paper (norm≈255) becomes transparent;
        # dark ink (norm≈0) becomes opaque.
        darkness = 255.0 - norm
        lo, hi = 25.0, 160.0
        alpha = np.clip((darkness - lo) * (255.0 / (hi - lo)), 0, 255).astype('uint8')

        h, w = alpha.shape
        if keep_color:
            rgb = np.asarray(color).astype('uint8')
        else:
            rgb = np.zeros((h, w, 3), dtype='uint8')  # black ink

        rgba = np.dstack([rgb, alpha])
        out_img = Image.fromarray(rgba, mode='RGBA')
        buf = io.BytesIO()
        out_img.save(buf, format='PNG', optimize=True)
        results.append((f'{_stem(f.filename)}_transparent.png', buf.getvalue(),
                        'image/png'))

    return _send_results(results, zip_name='transparent_docs.zip')


def do_pdf_to_jpg():
    files = _get_files({'pdf'})

    try:
        dpi = min(int(request.form.get('dpi', 150)), 300)
    except ValueError:
        dpi = 150
    scale = dpi / 72
    mat = fitz.Matrix(scale, scale)

    results = []
    for f in files:
        stem = _stem(f.filename)
        doc = fitz.open(stream=f.read(), filetype='pdf')
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=mat)
            results.append((f'{stem}_page_{i + 1:03d}.jpg',
                            pix.tobytes('jpeg'), 'image/jpeg'))
        doc.close()

    return _send_results(results, zip_name='pdf_images.zip')


def do_word_to_pdf():
    files = _get_files({'docx', 'doc'})

    try:
        import win32com.client
        import pythoncom
    except ImportError:
        return jsonify({
            'error': 'pywin32 is not installed.\n'
                     'Run:  pip install pywin32\n'
                     '(Also requires Microsoft Word to be installed)'
        }), 500

    results = []
    tmp_dir = tempfile.mkdtemp()
    word = None
    pythoncom.CoInitialize()
    try:
        try:
            word = win32com.client.Dispatch('Word.Application')
            word.Visible = False
            word.DisplayAlerts = 0  # wdAlertsNone

            for idx, f in enumerate(files):
                suffix  = os.path.splitext(f.filename)[1] or '.docx'
                tmp_in  = os.path.join(tmp_dir, f'input_{idx}{suffix}')
                tmp_out = os.path.join(tmp_dir, f'output_{idx}.pdf')
                f.save(tmp_in)

                doc = word.Documents.Open(os.path.abspath(tmp_in), ReadOnly=True)
                doc.ExportAsFixedFormat(os.path.abspath(tmp_out), 17)  # 17 = wdExportFormatPDF
                doc.Close(False)

                if not os.path.exists(tmp_out):
                    return jsonify({
                        'error': f'Conversion failed for "{f.filename}" — no output created.\n'
                                 'The file may be corrupted or password-protected.'
                    }), 500

                with open(tmp_out, 'rb') as pf:
                    results.append((f'{_stem(f.filename)}.pdf', pf.read(),
                                    'application/pdf'))
        except Exception as e:
            raise RuntimeError(
                f'Word conversion failed: {e}\n'
                'Make sure Microsoft Word is installed and the file is not '
                'corrupted or password-protected.'
            )
        finally:
            if word is not None:
                try:
                    word.Quit()
                except Exception:
                    pass
    finally:
        pythoncom.CoUninitialize()
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return _send_results(results, zip_name='word_pdfs.zip')


def do_excel_to_pdf():
    files = _get_files({'xlsx', 'xls'})

    try:
        import win32com.client
        import pythoncom
    except ImportError:
        return jsonify({
            'error': 'pywin32 is not installed.\n'
                     'Run:  pip install pywin32\n'
                     '(Also requires Microsoft Excel to be installed)'
        }), 500

    results = []
    tmp_dir = tempfile.mkdtemp()
    excel = None
    pythoncom.CoInitialize()
    try:
        try:
            excel = win32com.client.Dispatch('Excel.Application')
            excel.Visible = False
            excel.DisplayAlerts = False

            for idx, f in enumerate(files):
                suffix  = os.path.splitext(f.filename)[1] or '.xlsx'
                tmp_in  = os.path.join(tmp_dir, f'input_{idx}{suffix}')
                tmp_out = os.path.join(tmp_dir, f'output_{idx}.pdf')
                f.save(tmp_in)

                wb = excel.Workbooks.Open(os.path.abspath(tmp_in))
                wb.ExportAsFixedFormat(0, os.path.abspath(tmp_out))
                wb.Close(False)

                with open(tmp_out, 'rb') as pf:
                    results.append((f'{_stem(f.filename)}.pdf', pf.read(),
                                    'application/pdf'))
        except Exception as e:
            raise RuntimeError(
                f'Excel conversion failed: {e}\n'
                'Make sure Microsoft Excel is installed.'
            )
        finally:
            if excel is not None:
                try:
                    excel.Quit()
                except Exception:
                    pass
    finally:
        pythoncom.CoUninitialize()
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return _send_results(results, zip_name='excel_pdfs.zip')


def _pdf_to_docx_textonly(pdf_bytes):
    """Fallback: plain text-block extraction (loses layout/tables/images)."""
    from docx import Document
    from docx.shared import Pt

    pdf_doc  = fitz.open(stream=pdf_bytes, filetype='pdf')
    word_doc = Document()
    word_doc.styles['Normal'].font.size = Pt(11)

    for page_num, page in enumerate(pdf_doc):
        if page_num > 0:
            word_doc.add_page_break()
        blocks = sorted(page.get_text('blocks'), key=lambda b: (b[1], b[0]))
        for block in blocks:
            text = block[4].strip()
            if text:
                word_doc.add_paragraph(text)
    pdf_doc.close()

    buf = io.BytesIO()
    word_doc.save(buf)
    return buf.getvalue()


def do_pdf_to_word():
    files = _get_files({'pdf'})

    docx_mime = ('application/vnd.openxmlformats-officedocument'
                 '.wordprocessingml.document')

    try:
        from pdf2docx import Converter
        have_pdf2docx = True
    except ImportError:
        have_pdf2docx = False

    results = []
    tmp_dir = tempfile.mkdtemp()
    try:
        for idx, f in enumerate(files):
            pdf_bytes = f.read()
            out_bytes = None

            if have_pdf2docx:
                tmp_in  = os.path.join(tmp_dir, f'in_{idx}.pdf')
                tmp_out = os.path.join(tmp_dir, f'out_{idx}.docx')
                with open(tmp_in, 'wb') as pf:
                    pf.write(pdf_bytes)
                try:
                    # Layout-aware conversion: keeps paragraphs, tables, fonts,
                    # columns and images close to the original PDF.
                    cv = Converter(tmp_in)
                    cv.convert(tmp_out)
                    cv.close()
                    if os.path.exists(tmp_out):
                        with open(tmp_out, 'rb') as of:
                            out_bytes = of.read()
                except Exception:
                    out_bytes = None  # fall back below

            if out_bytes is None:
                # Either pdf2docx unavailable or it failed on this PDF.
                out_bytes = _pdf_to_docx_textonly(pdf_bytes)

            results.append((f'{_stem(f.filename)}.docx', out_bytes, docx_mime))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return _send_results(results, zip_name='word_docs.zip')


# ─── Helpers ─────────────────────────────────────────────────────────────────

_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


def _validate_session_id(sid):
    """Raise ValueError if sid is not a valid v4 UUID (prevents path traversal)."""
    if not sid or not _UUID_RE.match(sid):
        raise ValueError('Invalid session ID')


_FONT_INDEX = None


def _font_index():
    """Scan installed fonts once, mapping family name → style variants → file.
    Lets the editor reproduce the exact installed font (Calibri, Arial, etc.)."""
    global _FONT_INDEX
    if _FONT_INDEX is not None:
        return _FONT_INDEX

    from fontTools.ttLib import TTFont
    dirs = [
        os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''),
                     'Microsoft', 'Windows', 'Fonts'),
    ]
    index = {}
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            ext = fn.lower().rsplit('.', 1)[-1]
            if ext not in ('ttf', 'otf'):
                continue
            path = os.path.join(d, fn)
            try:
                tt = TTFont(path, fontNumber=0, lazy=True)
                family = (tt['name'].getDebugName(1) or '').strip()
                sub = (tt['name'].getDebugName(2) or '').lower()
                bold = 'bold' in sub
                italic = 'italic' in sub or 'oblique' in sub
                try:
                    mac = tt['head'].macStyle
                    bold = bold or bool(mac & 1)
                    italic = italic or bool(mac & 2)
                except Exception:
                    pass
                tt.close()
                if not family:
                    continue
                key = re.sub(r'[^a-z]', '', family.lower())
                index.setdefault(key, []).append(
                    {'bold': bold, 'italic': italic, 'path': path})
            except Exception:
                pass
    _FONT_INDEX = index
    return index


def _base14_font(op):
    """Fallback: nearest standard font for the detected style category."""
    b = 1 if op.get('bold') else 0
    i = 1 if op.get('italic') else 0
    if op.get('mono'):
        return {(0, 0): 'cour', (1, 0): 'cobo', (0, 1): 'coit', (1, 1): 'cobi'}[(b, i)]
    if op.get('serif'):
        return {(0, 0): 'tiro', (1, 0): 'tibo', (0, 1): 'tiit', (1, 1): 'tibi'}[(b, i)]
    return {(0, 0): 'helv', (1, 0): 'hebo', (0, 1): 'heit', (1, 1): 'hebi'}[(b, i)]


def _resolve_font(op):
    """Return (fontname_tag, fontfile_path). If the original font is installed,
    embed it for an exact match; otherwise fall back to a standard font."""
    raw = op.get('font') or ''
    if '+' in raw:               # strip subset prefix e.g. "ABCDEF+Calibri"
        raw = raw.split('+', 1)[1]
    clean = re.sub(r'[^a-z]', '', raw.lower())
    bold = bool(op.get('bold'))
    italic = bool(op.get('italic'))

    if clean:
        idx = _font_index()
        # longest family name that is contained in the PDF font name wins
        cands = [fam for fam in idx if fam and fam in clean]
        if cands:
            fam = max(cands, key=len)
            best = max(idx[fam],
                       key=lambda v: (v['bold'] == bold) + (v['italic'] == italic))
            tag = 'F' + hashlib.md5(best['path'].encode()).hexdigest()[:10]
            return tag, best['path']

    return _base14_font(op), None


def _validate_ext(filename, allowed_exts):
    """Raise ValueError if file extension is not in the allowed set."""
    ext = os.path.splitext(filename or '')[1].lower().lstrip('.')
    if ext not in allowed_exts:
        raise ValueError(
            f'File type ".{ext}" is not allowed for this tool. '
            f'Expected: {", ".join(sorted(allowed_exts))}'
        )


def _parse_page_range(range_str, total):
    pages = set()
    for part in range_str.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            try:
                s, e = part.split('-', 1)
                for p in range(int(s.strip()), int(e.strip()) + 1):
                    if 1 <= p <= total:
                        pages.add(p)
            except ValueError:
                pass
        else:
            try:
                p = int(part)
                if 1 <= p <= total:
                    pages.add(p)
            except ValueError:
                pass
    return sorted(pages)


def _recompress_images(doc, quality=60):
    from PIL import Image as PILImage
    seen = set()
    for page in doc:
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            if xref in seen:
                continue
            seen.add(xref)
            try:
                base_img  = doc.extract_image(xref)
                img_bytes = base_img['image']
                pil_img   = PILImage.open(io.BytesIO(img_bytes))
                if pil_img.mode in ('RGBA', 'LA', 'P', 'CMYK'):
                    pil_img = pil_img.convert('RGB')
                out = io.BytesIO()
                pil_img.save(out, format='JPEG', quality=quality, optimize=True)
                doc.update_stream(xref, out.getvalue())
            except Exception:
                pass


def _cleanup_old_sessions(max_age_secs=7200):
    """Delete temp session folders older than max_age_secs (default 2 h)."""
    now = time.time()
    try:
        for entry in os.scandir(TEMP_DIR):
            if entry.is_dir():
                try:
                    if now - entry.stat().st_mtime > max_age_secs:
                        shutil.rmtree(entry.path, ignore_errors=True)
                except Exception:
                    pass
    except Exception:
        pass


# ─── Startup ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    _cleanup_old_sessions()
    print('\n' + '=' * 50)
    print('  PDF Tools — Local PDF Toolkit')
    print('  Open your browser at: http://localhost:5000')
    print('=' * 50 + '\n')
    app.run(debug=False, port=5000, host='0.0.0.0')
