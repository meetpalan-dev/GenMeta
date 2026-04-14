import os
import re
import subprocess
import threading
import json
import shutil
import csv
import hashlib
import time
import sys
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response

# Heavy imports (PIL, transformers) are deferred into load_blip()
# so Flask starts immediately and the window opens fast.

os.environ["HF_HUB_OFFLINE"]               = "1"
os.environ["TRANSFORMERS_OFFLINE"]         = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"]       = "error"

if getattr(sys, 'frozen', False):
    _TEMPLATE_DIR = os.path.join(sys._MEIPASS, "templates")
else:
    _TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

app = Flask(__name__, template_folder=_TEMPLATE_DIR)

# ============================================================
# CONSTANTS
# ============================================================
MIN_PIXELS    = 4_000_000
MAX_FILE_MB   = 50
MIN_KEYWORDS  = 20
ACCEPTED_EXTS = (".jpg", ".jpeg", ".tiff", ".tif")
VIDEO_EXTS    = (".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv",
                 ".m4v", ".mts", ".m2ts", ".3gp")

STOPWORDS = {
    "a","an","the","and","or","but","so","yet",
    "of","in","on","at","by","for","to","from","with","without",
    "this","that","these","those","it","its","their","his","her",
    "is","are","was","were","be","been","being",
    "has","have","had","do","does","did",
    "photo","photograph","photography","image","picture",
    "shot","capture","captured","nature",
    "high","quality","best","beautiful","nice",
    "scene","view","perspective","angle",
    "background","foreground","", " "
}

CATEGORY_RULES = {
    "flower":    ["Nature",               "Parks/Outdoor"],
    "plant":     ["Nature",               "Objects"],
    "tree":      ["Nature",               "Parks/Outdoor"],
    "forest":    ["Nature",               "Parks/Outdoor"],
    "animal":    ["Animals/Wildlife",     "Nature"],
    "bird":      ["Animals/Wildlife",     "Nature"],
    "dog":       ["Animals/Wildlife",     "Nature"],
    "cat":       ["Animals/Wildlife",     "Nature"],
    "person":    ["People",               ""],
    "face":      ["People",               ""],
    "woman":     ["People",               ""],
    "man":       ["People",               ""],
    "child":     ["People",               ""],
    "temple":    ["Buildings/Landmarks",  "Religion"],
    "church":    ["Buildings/Landmarks",  "Religion"],
    "mosque":    ["Buildings/Landmarks",  "Religion"],
    "building":  ["Buildings/Landmarks",  ""],
    "city":      ["Buildings/Landmarks",  "Transportation"],
    "street":    ["Buildings/Landmarks",  "Transportation"],
    "texture":   ["Backgrounds/Textures", "Abstract"],
    "pattern":   ["Backgrounds/Textures", "Abstract"],
    "food":      ["Food and drink",       "Objects"],
    "fruit":     ["Food and drink",       "Nature"],
    "water":     ["Nature",               "Parks/Outdoor"],
    "ocean":     ["Nature",               "Parks/Outdoor"],
    "mountain":  ["Nature",               "Parks/Outdoor"],
    "sky":       ["Nature",               "Parks/Outdoor"],
    "sunset":    ["Nature",               "Parks/Outdoor"],
    "firework":  ["Holidays",             "Parks/Outdoor"],
    "road":      ["Transportation",       ""],
    "car":       ["Transportation",       ""],
}

# ============================================================
# GLOBAL STATE
# ============================================================
processor       = None
model           = None
model_ready     = False
model_status    = "loading"
is_running      = False
stop_requested  = False
log_messages    = []
last_output_dir = ""
move_log        = []
undo_available  = False

progress = {
    "current":0,"total":0,
    "valid":0,"dupes":0,"small":0,
    "oversized":0,"skipped":0,"videos":0,"errors":0,
    "locked":0,
    "stage": "idle",   # "filtering" | "processing" | "done"
    "filter_current":0, "filter_total":0,   # for pass-1 bar
}

locked_sources = []   # (src_path, dst_path) — retried after pipeline ends

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
UNDO_LOG    = os.path.join(BASE_DIR, "undo_log.json")
HISTORY_LOG = os.path.join(BASE_DIR, "run_history.json")


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {"global_storage_path": BASE_DIR, "use_local_output": True}


def log(msg):
    print(msg)
    log_messages.append(msg)


# ============================================================
# SAFE TRANSFER  — copy first, then retry deletion up to 5×
#
# Root cause of the "same files processed every run" bug:
# Windows Explorer Preview pane holds a read lock on files it
# previews. shutil.move() and os.remove() both fail with
# WinError 32 when that lock is held. Previously we swallowed
# the error silently, so the source was never deleted and every
# run re-processed the same files.
#
# Fix: after copy, retry os.remove() up to 5 times with a 0.4 s
# pause. This handles brief preview-pane locks. If still locked
# after retries, log a warning and increment progress["locked"]
# so the user sees the count in the UI.
# ============================================================
def safe_transfer(src, dst_dir):
    filename = os.path.basename(src)
    dst      = os.path.join(dst_dir, filename)
    shutil.copy2(src, dst)

    for attempt in range(5):
        try:
            os.remove(src)
            move_log.append({"src": src, "dst": dst})
            return True
        except OSError as e:
            if attempt < 4:
                time.sleep(0.4)
            else:
                print(f"DELETE FAILED: {src} | {e}")

    locked_sources.append({"src": src, "dst": dst})
    progress["locked"] += 1
    return False


# ============================================================
# LAZY FOLDER CREATION
# ============================================================
_created_dirs = set()

def ensure_dir(path):
    if path not in _created_dirs:
        os.makedirs(path, exist_ok=True)
        _created_dirs.add(path)


# ============================================================
# AI MODEL LOADER
# ============================================================
Image = None   # set by load_blip() after PIL is imported

def load_blip():
    global processor, model, model_ready, model_status, Image
    try:
        # Import heavy libs HERE so Flask/app.py module loads in <1 s
        from PIL import Image as _PIL_Image
        from transformers import BlipProcessor, BlipForConditionalGeneration
        Image = _PIL_Image   # make available to pipeline functions

        model_id = "Salesforce/blip-image-captioning-base"

        try:
            processor = BlipProcessor.from_pretrained(
                model_id, local_files_only=True, use_fast=False
            )
            model = BlipForConditionalGeneration.from_pretrained(
                model_id, local_files_only=True
            )
        except Exception:
            log("Model not in cache — downloading (~1 GB, one-time only)...")
            os.environ.pop("HF_HUB_OFFLINE",      None)
            os.environ.pop("TRANSFORMERS_OFFLINE", None)
            processor = BlipProcessor.from_pretrained(model_id, use_fast=False)
            model     = BlipForConditionalGeneration.from_pretrained(model_id)
            os.environ["HF_HUB_OFFLINE"]      = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            log("Download complete. Model cached for future runs.")

        model_ready  = True
        model_status = "ready"
        log("MODEL_READY")
    except Exception as e:
        model_status = "error"
        log(f"FATAL ERROR loading model: {str(e)}")


threading.Thread(target=load_blip, daemon=True).start()


# ============================================================
# DUPLICATE SORT
# ============================================================
_COPY_RE = re.compile(r'[\s_-]*(copy\d*|\(\d+\)|\s\d+)$', re.IGNORECASE)

def is_copy(f):
    return bool(_COPY_RE.search(os.path.splitext(f)[0]))

def sort_originals_first(lst):
    return sorted(lst, key=lambda f: (is_copy(f), len(f), f.lower()))


# ============================================================
# PIPELINE HELPERS
# ============================================================
def clean_text(t):
    return re.sub(r"[^a-zA-Z0-9 ]+", "", t.lower()).strip()

def image_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def generate_caption(image):
    """
    Generate caption with conditional prompting.
    Greedy decoding (num_beams=1) keeps speed identical to the original
    while still benefiting from the 'a photo of' prompt for richer output.
    num_beams=5 was ~5x slower — not worth the marginal quality gain.
    """
    inputs = processor(image, text="a photo of", return_tensors="pt")
    out    = model.generate(**inputs, max_length=40)   # greedy, same as original
    caption = processor.decode(out[0], skip_special_tokens=True)
    # Strip echoed prompt prefix if present
    for prefix in ("a photo of ", "a photo of"):
        if caption.lower().startswith(prefix):
            caption = caption[len(prefix):]
    return caption.strip()


MIN_DESC_WORDS = 7   # minimum, 10 preferred

def build_description(caption):
    """Build a description with minimum word count padding."""
    text  = clean_text(caption)
    words = text.split()

    # Pad short captions with context to reach minimum word count
    padding_phrases = [
        "in natural outdoor environment",
        "with realistic visual detail",
        "captured in natural light",
        "showcasing natural composition",
        "with scenic outdoor background",
    ]
    idx = 0
    while len(words) < MIN_DESC_WORDS and idx < len(padding_phrases):
        extra = padding_phrases[idx].split()
        words += [w for w in extra if w not in words]
        idx += 1

    return " ".join(words).capitalize()


def extract_keywords(caption):
    """Extract and enrich keywords; always return exactly 50."""
    words    = clean_text(caption).split()
    keywords = [w for w in words if w not in STOPWORDS and len(w) > 2]

    # Primary enrichment — nature/stock essentials
    enrich_primary = [
        "natural","outdoor","environment","detail",
        "texture","composition","scenic","realistic",
        "visual","surface",
    ]
    for e in enrich_primary:
        if e not in keywords:
            keywords.append(e)

    # Filler to reach MIN_KEYWORDS
    filler = [
        "aesthetic","travel","design","material",
        "context","pattern","background","landscape",
        "photography","color","light","shadow",
        "depth","contrast","focus","clarity",
    ]
    for f in filler:
        if len(keywords) >= MIN_KEYWORDS:
            break
        if f not in keywords:
            keywords.append(f)

    # Deduplicate preserving order, cap at 50
    seen, unique = set(), []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            unique.append(k)
    return unique[:50]

def choose_categories(text):
    text = text.lower()
    for key, cats in CATEGORY_RULES.items():
        if key in text:
            return cats[0], cats[1] if len(cats) > 1 else ""
    return "Nature", "Parks/Outdoor"


# ============================================================
# PIPELINE  — two-pass: filter first, AI second
# ============================================================
def process_images_task(source_dir, settings):
    global is_running, stop_requested, progress
    global last_output_dir, _created_dirs, move_log, undo_available

    move_dupes         = settings.get("move_dupes",         True)
    move_videos        = settings.get("move_videos",        True)
    move_small         = settings.get("move_small",         False)
    move_oversized     = settings.get("move_oversized",     False)
    move_other         = settings.get("move_other",         False)
    use_local_output   = settings.get("use_local_output",   True)

    _created_dirs  = set()
    move_log       = []
    undo_available = False
    locked_sources.clear()

    try:
        config      = load_config()
        global_root = config.get("global_storage_path", BASE_DIR).strip() or BASE_DIR

        # Universal dup folder from config (not per-run settings)
        univ_dup_enabled = config.get("univ_dup_enabled", False)
        univ_dup_path    = config.get("univ_dup_path", "").strip()
        dedup_all_files  = config.get("dedup_all_files", True)  # if False: only dedup valid images

        project_name      = os.path.basename(os.path.normpath(source_dir))
        date_tag          = datetime.now().strftime("%d%m%Y")
        final_folder_name = f"{project_name}_{date_tag}"

        # ── Per-run dynamic folder suffixes ─────────────────────
        # Universal mode uses  alpha_val_ddmmyyyy,  alpha_dub_ddmmyyyy … etc.
        # Local mode uses simple fixed names inside the source folder.
        p   = project_name   # short alias
        dt  = date_tag

        if use_local_output:
            output_root   = source_dir
            valid_dir     = os.path.join(source_dir, "valid")
            dup_dir       = os.path.join(source_dir, "duplicates")
            video_dir     = os.path.join(source_dir, "videos")
            small_dir     = os.path.join(source_dir, "too_small")
            oversized_dir = os.path.join(source_dir, "oversized")
            other_dir     = os.path.join(source_dir, "other_formats")
            csv_dir       = source_dir
        else:
            # Default base is the app install dir; user can override via settings
            os.makedirs(global_root, exist_ok=True)
            output_root   = global_root

            # Dynamic per-run named subfolders
            valid_dir     = os.path.join(global_root, f"{p}_val_{dt}")
            dup_dir       = os.path.join(global_root, f"{p}_dub_{dt}")
            video_dir     = os.path.join(global_root, f"{p}_vid_{dt}")
            small_dir     = os.path.join(global_root, f"{p}_small_{dt}")
            oversized_dir = os.path.join(global_root, f"{p}_max_{dt}")
            other_dir     = os.path.join(global_root, f"{p}_otr_{dt}")

            # CSV destination — independently controlled
            univ_csv_enabled = config.get("univ_csv_enabled", False)
            univ_csv_path    = config.get("univ_csv_path", "").strip()
            if univ_csv_enabled and univ_csv_path:
                os.makedirs(univ_csv_path, exist_ok=True)
                csv_dir = univ_csv_path
            else:
                # Default: CSV goes into a "Universal CSV" subfolder of the output root
                csv_dir = os.path.join(global_root, "Universal CSV")
                os.makedirs(csv_dir, exist_ok=True)

        # Decide which duplicate destination to use
        if univ_dup_enabled and univ_dup_path:
            os.makedirs(univ_dup_path, exist_ok=True)   # create if needed
            actual_dup_dir = univ_dup_path
        else:
            actual_dup_dir = dup_dir

        ensure_dir(valid_dir)
        last_output_dir = output_root

        all_files = [f for f in os.listdir(source_dir)
                     if os.path.isfile(os.path.join(source_dir, f))]

        video_files   = [f for f in all_files if f.lower().endswith(VIDEO_EXTS)]
        image_files   = [f for f in all_files if f.lower().endswith(ACCEPTED_EXTS)]
        skipped_files = [f for f in all_files
                         if not f.lower().endswith(VIDEO_EXTS)
                         and not f.lower().endswith(ACCEPTED_EXTS)]

        image_files = sort_originals_first(image_files)

        progress.update({
            "current":0,
            "total": len(image_files) + len(video_files) + len(skipped_files),
            "valid":0, "dupes":0, "small":0,
            "oversized":0, "skipped": len(skipped_files),
            "videos":0, "errors":0, "locked":0,
            "stage": "filtering",
            "filter_current": 0,
            "filter_total":   len(image_files),
        })

        log(f"Found {len(image_files)} images, {len(video_files)} videos, "
            f"{len(skipped_files)} other format files.")

        # ──────────────────────────────────────────────────────
        # PASS 1 — Fast filter (no AI): size, pixel, MD5 dedup
        # Buckets files into lists for pass 2 / immediate action
        # ──────────────────────────────────────────────────────
        log("Pass 1: Filtering…")

        valid_candidates = []   # filenames only — re-opened properly in pass 2
        local_hashes     = {}

        # ── Other formats — dedup first (if enabled), then move ─
        for filename in skipped_files:
            if stop_requested: break
            src = os.path.join(source_dir, filename)
            try:
                if dedup_all_files:
                    file_hash = image_md5(src)
                    if file_hash in local_hashes:
                        if move_dupes:
                            ensure_dir(actual_dup_dir)
                            safe_transfer(src, actual_dup_dir)
                        progress["dupes"]   += 1
                        progress["current"] += 1
                        continue
                    local_hashes[file_hash] = filename

                if move_other:
                    ensure_dir(other_dir)
                    safe_transfer(src, other_dir)
                progress["current"] += 1
            except Exception as e:
                log(f"Error on other {filename}: {str(e)}")
                progress["errors"]  += 1
                progress["current"] += 1

        # ── Videos — dedup first (if enabled), then move ─────
        for filename in video_files:
            if stop_requested: break
            src = os.path.join(source_dir, filename)
            try:
                if dedup_all_files:
                    file_hash = image_md5(src)
                    if file_hash in local_hashes:
                        if move_dupes:
                            ensure_dir(actual_dup_dir)
                            safe_transfer(src, actual_dup_dir)
                        progress["dupes"]   += 1
                        progress["current"] += 1
                        continue
                    local_hashes[file_hash] = filename

                if move_videos:
                    ensure_dir(video_dir)
                    safe_transfer(src, video_dir)
                progress["videos"]  += 1
                progress["current"] += 1
            except Exception as e:
                log(f"Error on video {filename}: {str(e)}")
                progress["errors"]  += 1
                progress["current"] += 1

        # ── Images — dedup FIRST, then size/pixel filters ────
        for filename in image_files:
            if stop_requested:
                log("STOPPED: User cancelled.")
                break

            src = os.path.join(source_dir, filename)
            progress["filter_current"] += 1

            try:
                # ① MD5 dedup — always runs for images regardless of setting
                #   (dedup_all_files only gates non-image file types above)
                file_hash = image_md5(src)
                if file_hash in local_hashes:
                    if move_dupes:
                        ensure_dir(actual_dup_dir)
                        safe_transfer(src, actual_dup_dir)
                    progress["dupes"]   += 1
                    progress["current"] += 1
                    continue
                local_hashes[file_hash] = filename

                # ② File size check (max 50 MB)
                file_mb = os.path.getsize(src) / (1024 * 1024)
                if file_mb > MAX_FILE_MB:
                    if move_oversized:
                        ensure_dir(oversized_dir)
                        safe_transfer(src, oversized_dir)
                    progress["oversized"] += 1
                    progress["current"]   += 1
                    continue

                # ③ Pixel count check (min 4 MP)
                with Image.open(src) as img:
                    w, h = img.size

                if (w * h) < MIN_PIXELS:
                    if move_small:
                        ensure_dir(small_dir)
                        safe_transfer(src, small_dir)
                    progress["small"]   += 1
                    progress["current"] += 1
                    continue

                # ④ Passed all filters → queue for AI
                valid_candidates.append(filename)

            except Exception as e:
                log(f"Error filtering {filename}: {str(e)}")
                progress["errors"]  += 1
                progress["current"] += 1

        log(f"Pass 1 done. {len(valid_candidates)} images passed filters, "
            f"{progress['dupes']} dupes, {progress['small']} small, "
            f"{progress['oversized']} oversized.")

        # ──────────────────────────────────────────────────────
        # PASS 2 — AI captioning on valid candidates only
        # ──────────────────────────────────────────────────────
        progress["stage"] = "processing"

        adobe_rows   = [["Filename","Title","Keywords","Category","Releases"]]
        shutter_rows = [["Filename","Description","Keywords","Categories",
                         "Editorial","Mature content","Illustration"]]

        for filename in valid_candidates:
            if stop_requested:
                log("STOPPED: User cancelled.")
                break

            src = os.path.join(source_dir, filename)
            try:
                # Re-open with 'with' so PIL releases the lock before we try to move
                with Image.open(src) as img:
                    caption = generate_caption(img.convert("RGB"))

                description = build_description(caption)
                keywords    = extract_keywords(caption)
                kw_str      = ", ".join(keywords)
                cat1, cat2  = choose_categories(caption)
                categories  = f"{cat1},{cat2}" if cat2 else cat1

                # File is now fully closed — safe_transfer can delete it
                safe_transfer(src, valid_dir)
                progress["valid"]   += 1
                progress["current"] += 1

                adobe_rows.append([filename, description, kw_str, 11, ""])
                shutter_rows.append([filename, description, kw_str,
                                     categories, "", "", ""])

            except Exception as e:
                log(f"Error processing {filename}: {str(e)}")
                progress["errors"]  += 1
                progress["current"] += 1

        # ── Save CSVs (respecting export toggles) ─────────────
        export_adobe   = config.get("export_adobe",   True)
        export_shutter = config.get("export_shutter", True)

        adobe_csv_path   = os.path.join(csv_dir, f"adobe_{final_folder_name}.csv")
        shutter_csv_path = os.path.join(csv_dir, f"shutter_{final_folder_name}.csv")

        if export_adobe:
            with open(adobe_csv_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(adobe_rows)
        else:
            adobe_csv_path = None   # not created — don't show in history

        if export_shutter:
            with open(shutter_csv_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(shutter_rows)
        else:
            shutter_csv_path = None

        # ── Post-run cleanup pass for locked files ────────────
        if locked_sources:
            log(f"Retrying deletion of {len(locked_sources)} locked file(s)...")
            still_locked = []
            for entry in locked_sources:
                src     = entry["src"]
                deleted = False
                for attempt in range(8):
                    try:
                        os.remove(src)
                        move_log.append(entry)
                        progress["locked"] -= 1
                        deleted = True
                        break
                    except OSError:
                        time.sleep(1.0)
                if not deleted:
                    still_locked.append(os.path.basename(src))

            if still_locked:
                log(f"WARNING: {len(still_locked)} file(s) still locked: "
                    f"{', '.join(still_locked[:5])}{'…' if len(still_locked)>5 else ''}")
            else:
                log("All locked files cleaned up.")

        # ── Save undo log (files + folders/CSVs to delete on undo) ──
        undo_data = {
            "moves":         move_log,
            "created_dirs":  [valid_dir],
            "created_files": [p for p in [adobe_csv_path, shutter_csv_path] if p],
        }
        with open(UNDO_LOG, "w", encoding="utf-8") as f:
            json.dump(undo_data, f, indent=2)
        undo_available = len(move_log) > 0

        # ── Save run history ───────────────────────────────────
        history_entry = {
            "timestamp":   datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source":      source_dir,
            "output":      output_root,
            "valid_dir":   valid_dir,
            "dup_dir":     actual_dup_dir if move_dupes else None,
            "csv_adobe":   os.path.join(csv_dir, f"adobe_{final_folder_name}.csv"),
            "csv_shutter": os.path.join(csv_dir, f"shutter_{final_folder_name}.csv"),
            "stats": {
                "valid":     progress["valid"],
                "dupes":     progress["dupes"],
                "small":     progress["small"],
                "oversized": progress["oversized"],
                "videos":    progress["videos"],
                "skipped":   progress["skipped"],
                "errors":    progress["errors"],
            }
        }
        history = []
        if os.path.exists(HISTORY_LOG):
            try:
                with open(HISTORY_LOG, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []
        history.insert(0, history_entry)    # newest first
        history = history[:50]             # keep last 50 runs
        with open(HISTORY_LOG, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

        progress["stage"] = "done"

        locked_warn = (f" | ⚠ {progress['locked']} still locked"
                       if progress["locked"] > 0 else "")

        log(
            f"PROCESS_END: valid={progress['valid']} | dupes={progress['dupes']} | "
            f"small={progress['small']} | oversized={progress['oversized']} | "
            f"videos={progress['videos']} | skipped={progress['skipped']} | "
            f"errors={progress['errors']}{locked_warn} | saved to {output_root}"
        )

    except Exception as e:
        log(f"FATAL PIPELINE ERROR: {str(e)}")
    finally:
        is_running     = False
        stop_requested = False


# ============================================================
# FLASK ROUTES
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/model_progress")
def model_progress():
    return jsonify({"ready": model_ready, "status": model_status})

@app.route("/run", methods=["POST"])
def run():
    global is_running, stop_requested, log_messages

    if is_running:
        return jsonify({"error": "Already running"}), 400
    if not model_ready:
        return jsonify({"error": "Model not ready yet — please wait"}), 400

    data   = request.get_json(silent=True) or {}
    folder = data.get("folder", "").strip()

    if not folder or not os.path.isdir(folder):
        return jsonify({"error": f"Folder not found: '{folder}'"}), 400

    settings = {
        "move_dupes":       bool(data.get("move_dupes",       True)),
        "move_videos":      bool(data.get("move_videos",      True)),
        "move_small":       bool(data.get("move_small",       False)),
        "move_oversized":   bool(data.get("move_oversized",   False)),
        "move_other":       bool(data.get("move_other",       False)),
        "use_local_output": bool(data.get("use_local_output", True)),
    }

    log_messages   = []
    is_running     = True
    stop_requested = False

    threading.Thread(
        target=process_images_task, args=(folder, settings), daemon=True
    ).start()
    return jsonify({"status": "started"})

@app.route("/stop", methods=["POST"])
def stop():
    global stop_requested
    if is_running:
        stop_requested = True
        return jsonify({"status": "stop requested"})
    return jsonify({"status": "not running"})

@app.route("/progress")
def get_progress():
    return jsonify({
        **progress,
        "running":        is_running,
        "model_status":   model_status,
        "undo_available": undo_available,
    })

@app.route("/open_folder", methods=["POST"])
def open_folder():
    path = last_output_dir or load_config().get("global_storage_path", BASE_DIR)
    if path and os.path.isdir(path):
        subprocess.Popen(["explorer", os.path.normpath(path)])
        return jsonify({"status": "opened"})
    return jsonify({"error": "Folder not found"}), 400

@app.route("/undo", methods=["POST"])
def undo():
    global undo_available
    if is_running:
        return jsonify({"error": "Cannot undo while running"}), 400
    if not os.path.exists(UNDO_LOG):
        return jsonify({"error": "No undo log found"}), 400

    with open(UNDO_LOG, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Support both old format (list) and new format (dict)
    if isinstance(raw, list):
        entries       = raw
        created_dirs  = []
        created_files = []
    else:
        entries       = raw.get("moves", [])
        created_dirs  = raw.get("created_dirs",  [])
        created_files = raw.get("created_files", [])

    if not entries and not created_files:
        return jsonify({"error": "Nothing to undo"}), 400

    restored, failed = 0, []
    dirs_to_check = set()

    # 1. Move all files back to source
    for entry in reversed(entries):
        src_orig    = entry["src"]
        dst_current = entry["dst"]
        if not os.path.exists(dst_current):
            failed.append(f"Missing: {os.path.basename(dst_current)}")
            continue
        try:
            os.makedirs(os.path.dirname(src_orig), exist_ok=True)
            shutil.move(dst_current, src_orig)
            dirs_to_check.add(os.path.dirname(dst_current))
            restored += 1
        except Exception as e:
            failed.append(f"{os.path.basename(dst_current)}: {str(e)}")

    # 2. Delete CSV files created by this run
    deleted_files = 0
    for fpath in created_files:
        try:
            if os.path.isfile(fpath):
                os.remove(fpath)
                deleted_files += 1
                dirs_to_check.add(os.path.dirname(fpath))
        except Exception:
            pass

    # 3. Remove empty folders (valid_dir + any output dirs), walk up tree
    removed_dirs = []
    all_dirs = sorted(
        dirs_to_check | set(created_dirs),
        key=lambda p: -len(p)   # deepest first
    )
    for d in all_dirs:
        current = d
        while current and os.path.isdir(current):
            try:
                if not os.listdir(current):
                    os.rmdir(current)
                    removed_dirs.append(current)
                    current = os.path.dirname(current)
                else:
                    break
            except Exception:
                break

    os.remove(UNDO_LOG)
    undo_available = False
    result = {
        "restored":     restored,
        "failed":       len(failed),
        "dirs_removed": len(removed_dirs),
        "files_deleted": deleted_files,
    }
    if failed:
        result["errors"] = failed[:10]
    return jsonify(result)

@app.route("/get_settings")
def get_settings():
    config = load_config()
    return jsonify({
        "global_storage_path": config.get("global_storage_path", BASE_DIR),
        "use_local_output":    config.get("use_local_output",    True),
        "univ_dup_enabled":    config.get("univ_dup_enabled",    False),
        "univ_dup_path":       config.get("univ_dup_path",       ""),
        "univ_csv_enabled":    config.get("univ_csv_enabled",    False),
        "univ_csv_path":       config.get("univ_csv_path",       ""),
        "dedup_all_files":     config.get("dedup_all_files",     True),
        "export_adobe":        config.get("export_adobe",        True),
        "export_shutter":      config.get("export_shutter",      True),
    })

@app.route("/save_settings", methods=["POST"])
def save_settings():
    data   = request.get_json(silent=True) or {}
    config = load_config()
    for key in ["global_storage_path", "univ_dup_path", "univ_csv_path"]:
        if key in data:
            config[key] = data[key]
    for key in ["use_local_output", "univ_dup_enabled", "univ_csv_enabled",
                "dedup_all_files", "export_adobe", "export_shutter"]:
        if key in data:
            config[key] = bool(data[key])
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

    # Auto-create Universal CSV subfolder inside global_storage_path
    # (only when not using a custom univ_csv_path)
    if not config.get("use_local_output", True):
        gp = config.get("global_storage_path", "").strip()
        if gp:
            os.makedirs(gp, exist_ok=True)
            if not config.get("univ_csv_enabled") or not config.get("univ_csv_path", "").strip():
                os.makedirs(os.path.join(gp, "Universal CSV"), exist_ok=True)
    # Auto-create custom univ_dup_path if enabled
    if config.get("univ_dup_enabled") and config.get("univ_dup_path", "").strip():
        os.makedirs(config["univ_dup_path"], exist_ok=True)
    # Auto-create custom univ_csv_path if enabled
    if config.get("univ_csv_enabled") and config.get("univ_csv_path", "").strip():
        os.makedirs(config["univ_csv_path"], exist_ok=True)

    return jsonify({"status": "saved"})

@app.route("/history")
def get_history():
    if not os.path.exists(HISTORY_LOG):
        return jsonify([])
    try:
        with open(HISTORY_LOG, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify([])

@app.route("/open_path", methods=["POST"])
def open_path():
    data = request.get_json(silent=True) or {}
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"error": "No path"}), 400
    # Handle URLs
    if path.startswith("http://") or path.startswith("https://"):
        import webbrowser
        webbrowser.open(path)
        return jsonify({"status": "opened"})
    if os.path.exists(path):
        if os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            subprocess.Popen(["explorer", os.path.normpath(path)])
        return jsonify({"status": "opened"})
    return jsonify({"error": "Path not found"}), 400

@app.route("/preview_folders", methods=["POST"])
def preview_folders():
    """
    Given a source folder path, return the exact output folder names that
    will be created on the next run. Used by the UI to show a preview.
    """
    data       = request.get_json(silent=True) or {}
    source_dir = data.get("folder", "").strip()
    if not source_dir:
        return jsonify({"error": "No folder"}), 400
    try:
        config       = load_config()
        use_local    = config.get("use_local_output", True)
        global_root  = config.get("global_storage_path", BASE_DIR).strip() or BASE_DIR
        project_name = os.path.basename(os.path.normpath(source_dir))
        date_tag     = datetime.now().strftime("%d%m%Y")
        p, dt        = project_name, date_tag

        if use_local:
            base = source_dir
            return jsonify({
                "mode":       "local",
                "base":       base,
                "valid":      os.path.join(base, "valid"),
                "duplicates": os.path.join(base, "duplicates"),
                "videos":     os.path.join(base, "videos"),
                "small":      os.path.join(base, "too_small"),
                "oversized":  os.path.join(base, "oversized"),
                "other":      os.path.join(base, "other_formats"),
                "csv":        base,
            })
        else:
            univ_csv_enabled = config.get("univ_csv_enabled", False)
            univ_csv_path    = config.get("univ_csv_path", "").strip()
            csv_dest = univ_csv_path if (univ_csv_enabled and univ_csv_path) \
                       else os.path.join(global_root, "Universal CSV")
            univ_dup_enabled = config.get("univ_dup_enabled", False)
            univ_dup_path    = config.get("univ_dup_path", "").strip()
            dup_dest = univ_dup_path if (univ_dup_enabled and univ_dup_path) \
                       else os.path.join(global_root, f"{p}_dub_{dt}")
            return jsonify({
                "mode":       "universal",
                "base":       global_root,
                "valid":      os.path.join(global_root, f"{p}_val_{dt}"),
                "duplicates": dup_dest,
                "videos":     os.path.join(global_root, f"{p}_vid_{dt}"),
                "small":      os.path.join(global_root, f"{p}_small_{dt}"),
                "oversized":  os.path.join(global_root, f"{p}_max_{dt}"),
                "other":      os.path.join(global_root, f"{p}_otr_{dt}"),
                "csv":        csv_dest,
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/version_check")
def version_check():
    """
    Optional future update check. Returns local version + optionally checks
    a remote version.json. Safe to call offline — falls back gracefully.
    """
    LOCAL_VERSION = "20.1"
    info = {"local": LOCAL_VERSION, "remote": None, "update_available": False}
    try:
        import urllib.request
        url = "https://raw.githubusercontent.com/meetpalan-dev/genmeta/main/version.json"
        with urllib.request.urlopen(url, timeout=3) as r:
            remote = json.loads(r.read().decode())
            info["remote"]           = remote.get("version")
            info["update_available"] = remote.get("version", LOCAL_VERSION) != LOCAL_VERSION
            info["changelog"]        = remote.get("changelog", "")
            info["download_url"]     = remote.get("download_url", "")
    except Exception:
        pass   # offline or repo not set up yet — totally fine
    return jsonify(info)


@app.route("/ensure_folders", methods=["POST"])
def ensure_folders():
    """
    Ensure the Universal output root and Universal CSV subfolder exist.
    Per-run dynamic folders (alpha_val_, alpha_dub_ …) are created lazily
    during processing — no pre-creation needed for those.
    Called on app load and after settings save.
    """
    try:
        config      = load_config()
        global_root = config.get("global_storage_path", BASE_DIR).strip() or BASE_DIR

        created = []

        # Always ensure the root exists
        if not os.path.exists(global_root):
            os.makedirs(global_root, exist_ok=True)
            created.append(global_root)

        # Default Universal CSV subfolder (only when no custom path is set)
        if not config.get("univ_csv_enabled") or not config.get("univ_csv_path", "").strip():
            csv_sub = os.path.join(global_root, "Universal CSV")
            if not os.path.exists(csv_sub):
                os.makedirs(csv_sub, exist_ok=True)
                created.append(csv_sub)

        # Custom paths if enabled
        for key in ["univ_dup_path", "univ_csv_path"]:
            enabled_key = "univ_dup_enabled" if key == "univ_dup_path" else "univ_csv_enabled"
            p = config.get(key, "").strip()
            if config.get(enabled_key) and p and not os.path.exists(p):
                os.makedirs(p, exist_ok=True)
                created.append(p)

        return jsonify({"status": "ok", "created": created})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/status")
def status():
    def stream():
        sent = 0
        while True:
            while sent < len(log_messages):
                yield f"data: {log_messages[sent]}\n\n"
                sent += 1
            if not is_running and sent >= len(log_messages):
                break
            time.sleep(0.3)
    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
