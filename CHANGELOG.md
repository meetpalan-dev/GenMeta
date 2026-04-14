# Changelog

All notable changes to GenMeta are documented here.

---

## [20.1] — 2025-04-14

### Added
- Dynamic per-run Universal output folder naming (`alpha_val_ddmmyyyy`, `alpha_dub_ddmmyyyy` etc.)
- Independent Universal CSV destination — toggle + custom path separate from Duplicate folder
- Output folder preview panel in UI — shows exact destination paths before you run
- `/preview_folders` API endpoint for live preview
- `/ensure_folders` API endpoint — auto-creates output directories on startup
- Two installer modes: **Recommended** (`C:\Program\GenMeta`) and **Custom** (user picks paths)
- Installer writes default `config.json` so app starts correctly out of the box
- WebView2 runtime check during installation
- Version check button in Settings footer (`v20.1` — click to check for updates)
- `version.json` for future remote update notifications
- Light mode contrast improvements (darker borders, stronger button hierarchy)

### Changed
- Default `global_storage_path` is now the app install directory (not a hardcoded path)
- Universal mode CSV now goes to `Universal CSV/` subfolder of output root by default
- `ensure_folders` no longer pre-creates per-run dynamic folders (created lazily on first use)
- `save_settings` auto-creates custom `univ_dup_path` and `univ_csv_path` if enabled

### Fixed
- `global_root` now falls back to `BASE_DIR` if config path is empty (prevents crash on fresh install)

---

## [2.01] — 2025-04-12

### Added
- "Check duplicates across all file types" toggle (default ON)
- Version note in Settings panel

### Changed
- Duplicate scan now runs first for ALL file types, not just valid images

---

## [2.0] — 2025-04-11

### Added
- Two-pass pipeline: fast filter (MD5 + size) first, AI captioning only on valid candidates
- Universal duplicate folder (independent, cross-scan)
- Run history panel with clickable folder/CSV links
- PIL image handle fix — files properly closed before move (root cause of WinError 32)
- Verbose `DELETE FAILED` logging in `safe_transfer`
- Renamed app from ShutterBot → GenMeta

### Changed
- `valid_candidates` stores filenames only — no PIL objects passed between passes
- Lazy folder creation — output directories only created when first file needs them

---

## [1.x] — 2025-04-09 to 2025-04-11

### Features built during initial development
- BLIP AI captioning with conditional prompting
- Flask + pywebview desktop app
- Progress bar with two-phase display (filtering / AI)
- Stop button, undo system with double-confirm
- Per-run toggle pills (duplicates, videos, too-small, oversized, other formats)
- Settings panel with dark/light mode, persistent config
- Safe file transfer with retry (handles Windows Explorer preview lock)
- Cleanup pass after pipeline for still-locked files
- One-click launcher (`launch.vbs`)
- PyInstaller + Inno Setup packaging
