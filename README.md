<<<<<<< HEAD
# 🤖 GenMeta

**AI-powered stock photo metadata generator for Shutterstock & Adobe Stock**

GenMeta automatically processes folders of images — filtering duplicates, sizing out small or oversized files, generating AI captions and keywords using BLIP, and exporting ready-to-upload CSV files for Shutterstock and Adobe Stock.

---

## ✨ Features

- 🧠 **AI captioning** via [BLIP](https://huggingface.co/Salesforce/blip-image-captioning-base) — generates descriptions and 20–50 keywords per image
- 🔍 **Two-pass pipeline** — fast filter first (dedup + size), then AI only on valid images
- 📁 **Smart folder output** — dynamic per-run naming (`alpha_val_14042025`, `alpha_dub_14042025` …)
- 📊 **CSV export** — Shutterstock and Adobe Stock formats, independently togglable
- ↩ **Full undo** — reverses every file move and deletes created folders/CSVs
- 🌗 **Dark/light mode** — clean minimal UI built with Flask + pywebview
- 📋 **Run history** — click any past run to jump straight to its output folders

---

## 📸 Screenshots

><img width="1920" height="1080" alt="{6DB1AA97-C0E7-4678-AA3F-D92F6528F76A}" src="https://github.com/user-attachments/assets/e55c55c6-522f-4fc4-9c65-8d7f02cdf637" />


---

## 🚀 Quick Start (from source)

### Requirements
- Python 3.9–3.11
- Windows 10 or later
- Internet connection for first run (downloads BLIP model ~900 MB, cached after that)

### Install & run

```bash
git clone https://github.com/meetpalan-dev/genmeta.git
cd genmeta
pip install -r requirements.txt
python main.py
```

The app window opens immediately. The AI model loads in the background — a progress bar shows when it's ready.

---

## 📦 Install as a desktop app (Windows)

Download the latest installer from [Releases](https://github.com/meetpalan-dev/genmeta/releases):

```
GenMeta_Setup_v20.1.exe
```

**Two install modes:**

| Mode | Install path | Output path | Best for |
|------|-------------|-------------|----------|
| **Recommended** | `C:\Program\GenMeta` | Same as install dir | Most users |
| **Custom** | You choose | You choose | Power users |

After install, double-click **GenMeta** on your Desktop or Start Menu.  
On first launch the BLIP model downloads (~900 MB). Every subsequent launch is instant.

> ⚠️ **Requires** [Microsoft WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) — already installed on most Windows 10/11 machines.

---

## 📁 Output folder structure

### Universal mode (default)
Each scan creates uniquely named folders inside the configured output root:

```
C:\Program\GenMeta\
├── alpha_val_14042025\        ← valid images + moved here
├── alpha_dub_14042025\        ← duplicates
├── alpha_vid_14042025\        ← videos
├── alpha_small_14042025\      ← too small (< 4 MP)
├── alpha_max_14042025\        ← oversized (> 50 MB)
├── alpha_otr_14042025\        ← other formats (.webp, .png …)
└── Universal CSV\
    ├── shutter_alpha_14042025.csv
    └── adobe_alpha_14042025.csv
```

### Local mode (subfolders next to source)
Enable **"Save next to source folder"** in Settings:

```
C:\Photos\alpha\
├── valid\
├── duplicates\
├── videos\
└── shutter_alpha_14042025.csv
```

---

## ⚙️ Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Universal output folder | App install dir | Root for all universal-mode output |
| Save next to source | OFF | Creates subfolders inside source folder |
| Universal duplicate folder | OFF | Collect duplicates from all scans in one place |
| Custom CSV destination | OFF | Override where CSV files are saved |
| Check duplicates across all types | ON | Videos + wrong-format files also deduplicated |
| Export Shutterstock CSV | ON | Generate `shutter_*.csv` |
| Export Adobe Stock CSV | ON | Generate `adobe_*.csv` |

---

## 🔧 Building from source (create installer)

### 1. Install build tools

```bash
pip install pyinstaller
```

### 2. Build the executable

```bash
# Windows — just double-click build.bat, or run:
pyinstaller genmeta.spec --clean --noconfirm
```

Output: `dist\GenMeta\`

### 3. Create the installer

1. Download [Inno Setup 6](https://jrsoftware.org/isinfo.php) (free)
2. Open `installer.iss` in Inno Setup
3. Press **Ctrl+F9**
4. Find your installer at `installer_output\GenMeta_Setup_v20.1.exe`

---

## 📋 Accepted file formats

GenMeta follows [Shutterstock submission guidelines](https://www.shutterstock.com/contributorsupport/articles/en_US/kbat02/What-are-the-technical-requirements-for-images):

| Format | Accepted | Notes |
|--------|----------|-------|
| JPEG / JPG | ✅ | Recommended |
| TIFF / TIF | ✅ | Max 4 GB via FTPS |
| PNG / WEBP / PSD | ❌ | Counted, not moved (unless toggle ON) |
| Videos | ❌ | Moved to `*_vid_*` folder |
| Min size | 4 MP | Width × Height ≥ 4,000,000 pixels |
| Max size | 50 MB | Per Shutterstock web upload limit |

---

## 🤖 AI model

GenMeta uses **BLIP (Bootstrapping Language-Image Pre-training)** by Salesforce:

- Model: [`Salesforce/blip-image-captioning-base`](https://huggingface.co/Salesforce/blip-image-captioning-base)
- Downloaded once on first run (~900 MB), cached in `~/.cache/huggingface/`
- Runs on CPU — no GPU required
- GPU (NVIDIA) supported automatically if PyTorch detects CUDA

---

## 📝 CSV format

### Shutterstock
| Filename | Description | Keywords | Categories | Editorial | Mature content | Illustration |
|----------|-------------|----------|------------|-----------|----------------|--------------|

### Adobe Stock
| Filename | Title | Keywords | Category | Releases |
|----------|-------|----------|----------|---------|

---

## 🗂 Project structure

```
genmeta/
├── main.py              # Entry point — webview window + Flask startup
├── app.py               # Flask routes + full processing pipeline
├── native_drop.py       # Win32 drag-drop handler stub
├── config.json          # Auto-created on first run
├── requirements.txt     # Python dependencies
├── genmeta.spec         # PyInstaller build spec
├── installer.iss        # Inno Setup installer script
├── build.bat            # One-click build script (Windows)
├── version.json         # Remote version file (upload to repo root)
└── templates/
    └── index.html       # App UI (Flask template)
```

---

## 🛣 Roadmap

- [ ] Getty Images / Pond5 CSV export
- [ ] File rename on export (clean stock-friendly names)
- [ ] Preview panel — click image to edit caption/keywords before export
- [ ] Batch retry — re-run AI only on errored files
- [ ] Custom keyword rules via settings UI

---

## 👨‍💻 Author

**Palan Dev** — [github.com/meetpalan-dev](https://github.com/meetpalan-dev)

---

## 📄 License

MIT License — see [LICENSE](LICENSE)
=======
# GenMeta
AI-powered desktop tool to generate stock photo metadata, captions, and CSV exports for Shutterstock and Adobe.
>>>>>>> 25b089fc822521beba17ae5dcd469a81efdb92cd
