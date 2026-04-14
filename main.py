# ============================================================
# SHUTTERBOT MAIN
# ============================================================

import os
import sys
import time
import threading
import urllib.request
import webview
import json

if getattr(sys, 'frozen', False):
    BASE_DIR     = os.path.dirname(sys.executable)
    TEMPLATE_DIR = os.path.join(sys._MEIPASS, "templates")
else:
    BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
    TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
FLASK_URL   = "http://127.0.0.1:5050"
FLASK_PORT  = 5050

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return None

def save_config(data):
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)

def ensure_global_storage(window):
    config = load_config()
    if config and "global_storage_path" in config:
        return config["global_storage_path"]
    result = window.create_file_dialog(webview.FileDialog.FOLDER)
    if not result:
        window.destroy()
        os._exit(0)
    selected_path = result[0]
    save_config({"global_storage_path": selected_path})
    return selected_path

LOADING_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:#080c12;color:white;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    display:flex;align-items:center;justify-content:center;
    height:100vh;flex-direction:column;gap:20px}
  .logo{display:flex;align-items:center;gap:14px}
  .logo-icon{font-size:36px;line-height:1}
  .logo-text h1{font-size:24px;font-weight:700;letter-spacing:-.4px;
    background:linear-gradient(135deg,#e2e8f0,#93c5fd);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
  .logo-text p{font-size:11px;color:#4a6080;margin-top:2px}
  .bw{width:280px;height:5px;background:#0f1520;border-radius:3px;overflow:hidden}
  .b{height:100%;background:linear-gradient(90deg,#080c12 0%,#3b82f6 50%,#080c12 100%);
    background-size:200% 100%;animation:p 1.4s infinite ease-in-out;border-radius:3px}
  @keyframes p{0%{background-position:100% 0}100%{background-position:-100% 0}}
  .ver{font-size:10px;color:#1e2d42;margin-top:-8px}
</style></head>
<body>
  <div class="logo">
    <div class="logo-icon">🤖</div>
    <div class="logo-text">
      <h1>GenMeta</h1>
      <p>Stock photo metadata generator</p>
    </div>
  </div>
  <div class="bw"><div class="b"></div></div>
  <div class="ver">v20.1 · Starting up…</div>
</body></html>"""


# ============================================================
# JS API — runs on background thread, must NOT call GUI directly
# ============================================================
class JsApi:
    def browse_folder(self):
        """
        Open native folder picker.
        create_file_dialog() MUST run on the main GUI thread.
        We schedule it via window.evaluate_js trick — actually the
        correct pywebview way is to call it directly; pywebview
        internally marshals it to the GUI thread when called from JS API.
        """
        wins = webview.windows
        if not wins:
            return ""
        try:
            result = wins[0].create_file_dialog(webview.FileDialog.FOLDER)
            if result:
                return result[0]
        except Exception as e:
            print(f"[JsApi] browse_folder error: {e}")
        return ""


def start_flask():
    from app import app
    app.run(port=FLASK_PORT, debug=False, use_reloader=False)

def wait_for_flask(window):
    for _ in range(120):
        try:
            urllib.request.urlopen(FLASK_URL, timeout=1)
            # Ensure Universal subfolders exist silently
            try:
                import urllib.request as _ur
                _ur.urlopen(
                    urllib.request.Request(
                        FLASK_URL + "/ensure_folders",
                        data=b"{}",
                        headers={"Content-Type": "application/json"},
                        method="POST"
                    ), timeout=2
                )
            except Exception:
                pass
            window.load_url(FLASK_URL)
            time.sleep(1.5)
            _install_native_drop(window)
            return
        except Exception:
            time.sleep(0.5)
    window.load_url(FLASK_URL)

def _install_native_drop(window):
    try:
        import native_drop
        native_drop.install(window, app_title="GenMeta")
    except Exception as e:
        print(f"[main] native_drop setup failed: {e}")

if __name__ == "__main__":
    window = webview.create_window(
        "GenMeta", html=LOADING_HTML,
        width=1100, height=780, resizable=True, min_size=(900, 650),
        js_api=JsApi(),
    )

    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    def on_start():
        ensure_global_storage(window)
        threading.Thread(target=wait_for_flask, args=(window,), daemon=True).start()

    webview.start(on_start, gui="edgechromium",
                  # Allow file:// paths to be read by WebView2 — needed for drag-drop file.path
                  http_server=True,
                  )
    os._exit(0)
