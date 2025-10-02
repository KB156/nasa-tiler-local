#!/usr/bin/env python3
import subprocess
import threading
import time
import traceback
from pathlib import Path
from flask import Flask, render_template_string, send_from_directory, request, jsonify
import json

# These paths are INSIDE the container
DATA_DIR = Path("/data")
PROCESSED_DIR = DATA_DIR / "processed"
TILES_DIR = DATA_DIR / "tiles"
ANNOTATIONS_DIR = DATA_DIR / "annotations" 

app = Flask(__name__, static_folder="static")
datasets = {}

# --- HTML Templates ---
HTML_INDEX = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>NASA Tiler — JP2 datasets</title>
  <style>
    :root {
      /* Dark Theme Palette */
      --background: hsl(222.2 84% 4.9%);
      --foreground: hsl(210 40% 98%);
      --card: hsl(222.2 84% 4.9%);
      --card-foreground: hsl(210 40% 98%);
      --muted: hsl(217.2 32.6% 17.5%);
      --muted-foreground: hsl(215 20.2% 65.1%);
      --primary: hsl(217.2 91.2% 59.8%);
      --primary-foreground: hsl(210 40% 98%);
      --border: hsl(217.2 32.6% 17.5%);
      --radius: 0.5rem;
      --status-ready: #4ade80;
      --status-processing: #facc15;
      --status-error: #f87171;
    }
    body { 
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
      margin: 0; padding: 2rem; background-color: var(--background); color: var(--foreground);
    }
    .container {
      max-width: 1100px; margin: 2rem auto; padding: 2rem;
      border-radius: var(--radius); border: 1px solid var(--border);
      background: var(--card);
    }
    h1 { 
      font-weight: 600; text-align: center; font-size: 2rem;
      margin-bottom: 0.5rem; letter-spacing: -0.025em;
    }
    h1 span { vertical-align: middle; margin-right: 10px; }
    p.subtitle { 
      color: var(--muted-foreground); text-align: center; margin-top: 0; margin-bottom: 2.5rem;
      font-size: 1rem;
    }
    code { 
      background: var(--muted); padding: 3px 6px; border-radius: 0.3rem; 
      font-family: monospace; color: var(--foreground);
    }
    table { width: 100%; border-collapse: collapse; }
    th {
      padding: 0.75rem 1rem; text-align: left; color: var(--muted-foreground);
      font-weight: 500; text-transform: uppercase; font-size: 0.75rem;
      border-bottom: 1px solid var(--border);
    }
    td { padding: 1rem; border-bottom: 1px solid var(--border); }
    tr:last-child td { border-bottom: none; }
    .status b { font-weight: 600; }
    .ready b { color: var(--status-ready); }
    .processing b { color: var(--status-processing); }
    .error b { color: var(--status-error); }
    .btn {
        display: inline-flex; align-items: center; justify-content: center;
        border-radius: var(--radius); text-decoration: none;
        padding: 0.5rem 1rem; font-weight: 500; transition: all 0.2s;
        border: 1px solid transparent;
    }
    .btn-primary { color: var(--primary-foreground); background-color: var(--primary); }
    .btn-primary:hover { opacity: 0.9; }
    pre {
      max-height: 120px; overflow: auto; background: var(--muted);
      padding: 0.75rem; border-radius: var(--radius); color: var(--muted-foreground); 
      font-size: 0.8rem; white-space: pre-wrap;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1><span>🛰️</span> NASA Tiler</h1>
    <p class="subtitle">Drop <code>.jp2</code> files into the mounted <code>nasa-tiler-data</code> folder. The dashboard updates automatically.</p>
    <table>
      <thead><tr><th>Dataset</th><th>Status</th><th>Logs</th><th>Actions</th></tr></thead>
      <tbody id="dataset-table-body"></tbody>
    </table>
  </div>
  <script>
    async function updateTable() {
      try {
        const response = await fetch('/status_table');
        const html = await response.text();
        const tbody = document.getElementById('dataset-table-body');
        if (html.trim() === '') {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color: var(--muted-foreground);">No datasets found. Waiting for .jp2 files...</td></tr>';
        } else { tbody.innerHTML = html; }
      } catch (error) { console.error('Failed to fetch status:', error); }
    }
    updateTable(); setInterval(updateTable, 3000);
  </script>
</body>
</html>
"""

TABLE_ROW_HTML = """
{% for name,meta in datasets.items() %}
<tr>
  <td>{{name}}</td>
  <td class="{{meta.status}}"><b>{{meta.status | upper}}</b></td>
  <td><pre>{{ meta.logs | join('\\n') }}</pre></td>
  <td>
    {% if meta.status == 'ready' %}
      <a href="/viewer/{{name}}" class="btn btn-primary">Open Viewer</a>
    {% else %} - {% endif %}
  </td>
</tr>
{% endfor %}
"""

VIEWER_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Viewer - {{name}}</title>
  <style>
    :root {
      /* Dark Theme Palette */
      --background: hsl(224, 71%, 4%);
      --foreground: hsl(210 40% 98%);
      --card: hsl(224, 71%, 4%);
      --card-foreground: hsl(210 40% 98%);
      --muted: hsl(217.2 32.6% 17.5%);
      --muted-foreground: hsl(215 20.2% 65.1%);
      --primary: hsl(217.2 91.2% 59.8%);
      --primary-foreground: hsl(210 40% 98%);
      --border: hsl(217.2 32.6% 17.5%);
      --radius: 0.5rem;
    }
    html, body {
      height: 100vh; width: 100vw; margin: 0; padding: 0;
      background-color: var(--background);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: var(--foreground);
      overflow: hidden;
    }
    * { box-sizing: border-box; }
    .viewer-grid-container {
      display: grid; grid-template-columns: 200px 1fr 240px;
      grid-template-rows: 1fr auto; grid-template-areas: "sidebar-left main sidebar-right" "timeline timeline timeline";
      height: 100vh; padding: 1rem; gap: 1rem;
    }
    .sidebar-left { grid-area: sidebar-left; display: flex; flex-direction: column; gap: 0.5rem; }
    .main-viewer-area { grid-area: main; position: relative; border: 1px solid var(--border); border-radius: var(--radius); background: var(--background); }
    .sidebar-right { grid-area: sidebar-right; display: flex; flex-direction: column; gap: 1rem; }
    .timeline-explorer { grid-area: timeline; }
    .panel {
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 1rem;
    }
    .panel h3 { margin-top: 0; margin-bottom: 1rem; font-size: 0.9rem; font-weight: 600; color: var(--card-foreground); }
    .btn {
        display: inline-flex; align-items: center; justify-content: center; width: 100%;
        border-radius: var(--radius); text-decoration: none; padding: 0.5rem 1rem;
        font-weight: 500; transition: all 0.2s; border: 1px solid var(--border);
        background: transparent; color: var(--foreground); cursor: pointer;
    }
    .btn:hover { background-color: var(--muted); }
    .btn.btn-primary { color: var(--primary-foreground); background-color: var(--primary); border-color: var(--primary); }
    .btn.btn-primary:hover { opacity: 0.9; }
    .annotation-group input[type="text"] {
        width: 100%; border: 1px solid var(--border); background: var(--background);
        padding: 0.5rem; border-radius: var(--radius); margin-bottom: 0.75rem; color: var(--foreground);
    }
    .annotation-status { font-size: 0.8rem; color: var(--muted-foreground); min-height: 20px; }
    #viewer { width: 100%; height: 100%; border-radius: var(--radius); }
    
    #viewer .openseadragon-canvas {
        /* UPDATED: SVG cursor stroke changed to white for dark mode */
        cursor: url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIiIGhlaWdodD0iMzIiIHZpZXdCb3g9IjAgMCAzMiAzMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48Y2lyY2xlIGN4PSIxNiIgY3k9IjE2IiByPSI2IiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjEuNSIvPjxwYXRoIGQ9Ik0xNiA0VjEwTTE2IDIyVjI4TTQgMTZIMTBMMjIgMTZIMjgiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMS41Ii8+PC9zdmc+') 16 16, crosshair;
    }
    
    .viewer-controls { position: absolute; top: 1rem; left: 1rem; z-index: 100; display: flex; flex-direction: column; gap: 0.5rem; }
    .control-btn { width: 36px; height: 36px; font-size: 1rem; padding: 0; background: var(--card); }
    .annotation-marker {
        width: 24px; height: 24px; border-radius: 50%;
        background-color: hsla(217, 91%, 59%, 0.5);
        border: 2px solid white; box-shadow: 0 0 5px black;
        cursor: pointer;
    }
    .annotation-marker:hover .annotation-tooltip { display: block; }
    .annotation-tooltip {
        display: none; position: absolute; bottom: 120%; left: 50%;
        transform: translateX(-50%); background: #222; color: white;
        padding: 5px 10px; border-radius: 4px; font-size: 0.9rem;
        white-space: nowrap;
    }
  </style>
  <script src="/static/openseadragon.min.js"></script>
</head>
<body>
  <div class="viewer-grid-container">
    <div class="sidebar-left"> <button class="btn">Layers</button> <button class="btn">Search</button> <button class="btn">Filters</button> <button class="btn">Compare</button> </div>
    <div class="main-viewer-area"> <div id="viewer"></div> <div class="viewer-controls"> <button id="zoom-in" class="btn control-btn">+</button> <button id="zoom-out" class="btn control-btn">-</button> </div> </div>
    <div class="sidebar-right">
        <div class="panel"><h3>Dataset</h3> </div>
        <div class="panel annotation-group">
            <h3>Annotations</h3>
            <p id="annotation-status" class="annotation-status">Click on the image to place a marker.</p>
            <input type="text" id="annotation-text" placeholder="Add annotation...">
            <button id="add-annotation-btn" class="btn btn-primary">+ Add</button>
        </div>
    </div>
    <div class="timeline-explorer panel"> </div>
  </div>

  <script>
    const datasetName = "{{name}}";
    let newAnnotationPoint = null;

    const viewer = OpenSeadragon({
      id: "viewer",
      prefixUrl: "https://openseadragon.github.io/openseadragon/images/",
      tileSources: `/tiles/${datasetName}/output.dzi`,
      showZoomControl: false, showHomeControl: false, showFullScreenControl: false, showNavigator: false,
    });

    function drawAnnotation(annotation) {
        const marker = document.createElement('div');
        marker.className = 'annotation-marker';
        const tooltip = document.createElement('div');
        tooltip.className = 'annotation-tooltip';
        tooltip.textContent = annotation.text;
        marker.appendChild(tooltip);
        viewer.addOverlay({
            element: marker,
            location: new OpenSeadragon.Point(annotation.x, annotation.y)
        });
    }

    async function loadAnnotations() {
        const response = await fetch(`/annotations/${datasetName}`);
        const annotations = await response.json();
        annotations.forEach(drawAnnotation);
    }

    viewer.addHandler('open', loadAnnotations);

    viewer.addHandler('canvas-click', function(event) {
        newAnnotationPoint = viewer.viewport.pointFromPixel(event.position);
        document.getElementById('annotation-status').textContent = 'Marker placed. Add text and save.';
    });

    document.getElementById('add-annotation-btn').addEventListener('click', async function() {
        const textInput = document.getElementById('annotation-text');
        const text = textInput.value.trim();
        if (!newAnnotationPoint) {
            alert('Please click on the image to place a marker first.');
            return;
        }
        if (!text) {
            alert('Please enter some text for the annotation.');
            return;
        }
        const newAnnotation = { x: newAnnotationPoint.x, y: newAnnotationPoint.y, text: text };
        const response = await fetch(`/annotations/${datasetName}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newAnnotation)
        });
        if (response.ok) {
            drawAnnotation(newAnnotation);
            textInput.value = '';
            newAnnotationPoint = null;
            document.getElementById('annotation-status').textContent = 'Annotation saved! Click image for new marker.';
        } else {
            alert('Failed to save annotation.');
        }
    });

    document.getElementById('zoom-in').addEventListener('click', () => viewer.viewport.zoomBy(1.4));
    document.getElementById('zoom-out').addEventListener('click', () => viewer.viewport.zoomBy(1 / 1.4));
  </script>
</body>
</html>
"""

# --- Main Application Logic ---
def log_for(name, line):
    entry = f"[{time.strftime('%H:%M:%S')}] {line.strip()}"
    datasets.setdefault(name, {'status':'pending','logs':[]})
    datasets[name]['logs'].append(entry)
    if len(datasets[name]['logs']) > 100:
        datasets[name]['logs'] = datasets[name]['logs'][-100:]
    print(f"{name}: {line.strip()}")

def process_single(img_path: Path):
    name = img_path.stem
    datasets.setdefault(name, {'status':'pending','logs':[],'dzi':None})
    if (TILES_DIR / name / "output.dzi").exists():
        if datasets[name]['status'] != 'ready':
            log_for(name, "✅ Dataset already processed and is ready.")
            datasets[name]['status'] = 'ready'
        return
    
    total_start_time = time.monotonic()
    try:
        datasets[name]['status'] = 'processing'
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        TILES_DIR.mkdir(parents=True, exist_ok=True)
        ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True) 
        tif_out = PROCESSED_DIR / f"{name}.tif"
        log_for(name, f"➡️ Step 1/3: Converting {img_path.name} to TIFF...")
        start_time_1 = time.monotonic()
        vips_out_path = f"{tif_out}[compression=lzw]"
        p1 = subprocess.run(["vips", "copy", str(img_path), vips_out_path], capture_output=True, text=True, timeout=3600)
        if p1.returncode != 0: raise RuntimeError(f"VIPS failed to convert JP2: {p1.stderr}")
        log_for(name, f"✔️ Step 1/3 finished in {time.monotonic() - start_time_1:.2f} seconds.")
        out_prefix = TILES_DIR / name / "output"
        log_for(name, f"➡️ Step 2/3: Creating image tile pyramid...")
        start_time_2 = time.monotonic()
        p2 = subprocess.run([
            "vips", "dzsave", str(tif_out), str(out_prefix),
            "--tile-size=512", "--overlap=1","--depth=onepixel", "--suffix=.jpg[Q=90]"
        ], capture_output=True, text=True, timeout=3600)
        if p2.returncode != 0: raise RuntimeError(f"VIPS failed to create tiles: {p2.stderr}")
        log_for(name, f"✔️ Step 2/3 finished in {time.monotonic() - start_time_2:.2f} seconds.")
        dzi_file = out_prefix.with_suffix(".dzi")
        log_for(name, f"➡️ Step 3/3: Generating manifest...")
        start_time_3 = time.monotonic()
        p3 = subprocess.run(["python3", "/app/make_manifest.py", str(dzi_file)], capture_output=True, text=True)
        if p3.returncode != 0: raise RuntimeError(f"make_manifest.py failed: {p3.stderr}")
        log_for(name, f"✔️ Step 3/3 finished in {time.monotonic() - start_time_3:.2f} seconds.")
        datasets[name]['status'] = 'ready'
        log_for(name, f"✅ Total processing finished in {time.monotonic() - total_start_time:.2f} seconds.")
    except Exception as e:
        datasets[name]['status'] = 'error'
        err = ''.join(traceback.format_exception_only(type(e), e)).strip()
        log_for(name, f"❌ ERROR: {err}")
        datasets[name]['logs'].append(''.join(traceback.format_exc()))

def discover_and_process():
    log_global("Starting discovery thread...")
    while True:
        try:
            ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True) 
            for p in DATA_DIR.glob('*.[jJ][pP]2'):
                if p.is_file():
                    name = p.stem
                    if name not in datasets:
                        log_global(f"Discovered new file: {p.name}")
                        threading.Thread(target=process_single, args=(p,), daemon=True).start()
            time.sleep(5)
        except Exception as e:
            log_global(f"Discovery loop error: {e}")
            time.sleep(15)

def log_global(line):
    print(f"[global {time.strftime('%H:%M:%S')}] {line}")

# --- Web Routes ---
@app.route("/")
def index():
    return render_template_string(HTML_INDEX)

@app.route("/status_table")
def status_table():
    sorted_datasets = dict(sorted(datasets.items()))
    return render_template_string(TABLE_ROW_HTML, datasets=sorted_datasets)

@app.route("/viewer/<name>")
def viewer(name):
    return render_template_string(VIEWER_HTML, name=name)

@app.route("/tiles/<path:filename>")
def tiles(filename):
    return send_from_directory(str(TILES_DIR), filename)

# --- Annotation API Endpoints ---
@app.route("/annotations/<name>", methods=['GET'])
def get_annotations(name):
    annotation_file = ANNOTATIONS_DIR / f"{name}.json"
    if not annotation_file.exists():
        return jsonify([])
    
    with open(annotation_file, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = []
    
    response = jsonify(data)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/annotations/<name>", methods=['POST'])
def add_annotation(name):
    new_annotation = request.get_json()
    if not new_annotation or 'x' not in new_annotation or 'y' not in new_annotation or 'text' not in new_annotation:
        return jsonify({"error": "Invalid annotation data"}), 400
    
    annotation_file = ANNOTATIONS_DIR / f"{name}.json"
    annotations = []
    if annotation_file.exists():
        with open(annotation_file, 'r') as f:
            try:
                annotations = json.load(f)
            except json.JSONDecodeError:
                pass 
    
    annotations.append(new_annotation)
    
    with open(annotation_file, 'w') as f:
        json.dump(annotations, f, indent=2)
        
    return jsonify({"success": True, "annotation": new_annotation}), 201

if __name__ == "__main__":
    t = threading.Thread(target=discover_and_process, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=8080)