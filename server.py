#!/usr/bin/env python3
import subprocess
import threading
import time
import traceback
from pathlib import Path
from flask import Flask, render_template_string, send_from_directory

# These paths are INSIDE the container
DATA_DIR = Path("/data")
PROCESSED_DIR = DATA_DIR / "processed"
TILES_DIR = DATA_DIR / "tiles"

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
      --bg-color: #e0e5ec; /* Light background, similar to the image */
      --container-bg: #e0e5ec;
      --text-color: #333;
      --header-color: #5d5d81; /* A muted purplish tone */
      --shadow-light: #ffffff; /* Lighter shadow for embossed effect */
      --shadow-dark: #a3b1c6;  /* Darker shadow for embossed effect */
      --primary-color: #6a6ee0; /* Main button/link color */
      --secondary-color: #b3baff; /* Lighter shade of primary */
      --status-ready: #4CAF50;
      --status-processing: #FFC107;
      --status-error: #F44336;
    }
    body { 
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
      margin: 0; padding: 2rem; background-color: var(--bg-color); color: var(--text-color);
    }
    .container {
      max-width: 1100px; margin: 2rem auto; padding: 2.5rem;
      border-radius: 20px;
      background: var(--container-bg);
      box-shadow: 9px 9px 18px var(--shadow-dark), -9px -9px 18px var(--shadow-light);
    }
    h1 { 
      color: var(--header-color); font-weight: 700; text-align: center; font-size: 2.5rem;
      margin-bottom: 0.5rem;
    }
    h1 span { font-size: 2rem; vertical-align: middle; margin-right: 10px; }
    p.subtitle { 
      color: #666; text-align: center; margin-top: 0; margin-bottom: 2rem;
      font-size: 1.1rem;
    }
    code { 
      background: rgba(0,0,0,0.05); padding: 3px 7px; border-radius: 6px; 
      font-family: monospace; color: var(--text-color);
      box-shadow: inset 2px 2px 4px var(--shadow-dark), inset -2px -2px 4px var(--shadow-light);
    }
    table {
      width: 100%; border-collapse: separate; border-spacing: 0 1rem;
      margin-top: 2rem;
    }
    th {
      padding: 1rem 1.5rem; text-align: left; color: var(--header-color);
      font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
      border-bottom: 1px solid rgba(0,0,0,0.1); /* Subtle separator */
    }
    td {
      background-color: var(--container-bg);
      padding: 1.5rem;
      border-radius: 12px;
      box-shadow: 6px 6px 12px var(--shadow-dark), -6px -6px 12px var(--shadow-light);
      transition: all 0.2s ease-in-out;
    }
    td:hover {
        box-shadow: inset 3px 3px 6px var(--shadow-dark), inset -3px -3px 6px var(--shadow-light);
    }
    .status b { font-weight: 600; }
    .ready b { color: var(--status-ready); }
    .processing b { color: var(--status-processing); }
    .error b { color: var(--status-error); }
    .action-btn {
      display: inline-block;
      color: white; background-color: var(--primary-color);
      text-decoration: none; padding: 0.8rem 1.5rem; border-radius: 12px;
      text-align: center; transition: all 0.2s ease-in-out;
      box-shadow: 6px 6px 12px var(--shadow-dark), -6px -6px 12px var(--shadow-light);
      font-weight: 600;
      border: none;
    }
    .action-btn:hover {
      background-color: var(--secondary-color);
      box-shadow: inset 3px 3px 6px var(--shadow-dark), inset -3px -3px 6px var(--shadow-light);
      color: var(--text-color);
    }
    pre {
      max-height: 120px; overflow: auto; background: rgba(0,0,0,0.03);
      padding: 0.8rem; border-radius: 8px; color: #555; font-size: 0.8rem;
      white-space: pre-wrap;
      box-shadow: inset 2px 2px 4px var(--shadow-dark), inset -2px -2px 4px var(--shadow-light);
    }
  </style>
</head>
<body>
  <div class="container">
    <h1><span>🛰️</span> NASA Tiler</h1>
    <p class="subtitle">Drop <code>.jp2</code> files into the mounted <code>nasa-tiler-data</code> folder. The dashboard updates automatically.</p>
    <table>
      <thead>
        <tr>
          <th>Dataset</th>
          <th>Status</th>
          <th>Logs</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody id="dataset-table-body">
        </tbody>
    </table>
  </div>

  <script>
    async function updateTable() {
      try {
        const response = await fetch('/status_table');
        const html = await response.text();
        const tbody = document.getElementById('dataset-table-body');
        if (html.trim() === '') {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; box-shadow:none; background:transparent;">No datasets found. Waiting for .jp2 files...</td></tr>';
        } else {
            tbody.innerHTML = html;
        }
      } catch (error) {
        console.error('Failed to fetch status:', error);
      }
    }
    updateTable();
    setInterval(updateTable, 3000);
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
      <a href="/viewer/{{name}}" class="action-btn">Open Viewer</a>
    {% else %}
      -
    {% endif %}
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
  <style> html,body,#viewer{ height:100vh; margin:0; padding:0; background-color: #000; } </style>
  <script src="/static/openseadragon.min.js"></script>
</head>
<body>
  <div id="viewer"></div>
  <script>
    var viewer = OpenSeadragon({
      id: "viewer",
      prefixUrl: "https://openseadragon.github.io/openseadragon/images/",
      tileSources: "/tiles/{{name}}/output.dzi",
      showNavigator: true,
      navigatorPosition: "BOTTOM_RIGHT"
    });
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
        tif_out = PROCESSED_DIR / f"{name}.tif"

        log_for(name, f"➡️ Step 1/3: Converting {img_path.name} to TIFF (This can be very slow)...")
        start_time_1 = time.monotonic()
        vips_out_path = f"{tif_out}[compression=lzw]"
        p1 = subprocess.run(["vips", "copy", str(img_path), vips_out_path], capture_output=True, text=True, timeout=3600)
        if p1.returncode != 0: raise RuntimeError(f"VIPS failed to convert JP2: {p1.stderr}")
        duration_1 = time.monotonic() - start_time_1
        log_for(name, f"✔️ Step 1/3 finished in {duration_1:.2f} seconds.")

        out_prefix = TILES_DIR / name / "output"
        log_for(name, f"➡️ Step 2/3: Creating image tile pyramid...")
        start_time_2 = time.monotonic()
        p2 = subprocess.run([
            "vips", "dzsave", str(tif_out), str(out_prefix),
            "--tile-size=512", "--overlap=1","--depth=onepixel", "--suffix=.jpg[Q=90]"
        ], capture_output=True, text=True, timeout=3600)
        if p2.returncode != 0: raise RuntimeError(f"VIPS failed to create tiles: {p2.stderr}")
        duration_2 = time.monotonic() - start_time_2
        log_for(name, f"✔️ Step 2/3 finished in {duration_2:.2f} seconds.")

        dzi_file = out_prefix.with_suffix(".dzi")
        log_for(name, f"➡️ Step 3/3: Generating manifest...")
        start_time_3 = time.monotonic()
        p3 = subprocess.run(["python3", "/app/make_manifest.py", str(dzi_file)], capture_output=True, text=True)
        if p3.returncode != 0: raise RuntimeError(f"make_manifest.py failed: {p3.stderr}")
        duration_3 = time.monotonic() - start_time_3
        log_for(name, f"✔️ Step 3/3 finished in {duration_3:.2f} seconds.")

        datasets[name]['status'] = 'ready'
        total_duration = time.monotonic() - total_start_time
        log_for(name, f"✅ Total processing finished in {total_duration:.2f} seconds. Dataset is ready.")

    except Exception as e:
        datasets[name]['status'] = 'error'
        err = ''.join(traceback.format_exception_only(type(e), e)).strip()
        log_for(name, f"❌ ERROR: {err}")
        traceback_str = ''.join(traceback.format_exc())
        datasets[name]['logs'].append(traceback_str)

def discover_and_process():
    log_global("Starting discovery thread...")
    while True:
        try:
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

if __name__ == "__main__":
    t = threading.Thread(target=discover_and_process, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=8080)