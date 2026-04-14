"""
native_drop.py — stub (drag-drop handled entirely in JS via file.path)
WebView2 exposes full file paths on dropped files, so no Win32 hooks needed.
"""

def install(webview_window, app_title="GenMeta"):
    print("[native_drop] JS-only mode — no Win32 hooks.")
