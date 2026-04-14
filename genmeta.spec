# -*- mode: python ; coding: utf-8 -*-
# GenMeta — PyInstaller build spec
# Run: pyinstaller genmeta.spec --clean --noconfirm

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect transformers data files (tokenizer configs, etc.)
transformers_datas = collect_data_files("transformers")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("templates",       "templates"),        # Flask HTML templates
        ("native_drop.py",  "."),                # drag-drop helper
        *transformers_datas,                     # transformers configs
    ],
    hiddenimports=[
        # Flask / Jinja2
        "flask", "jinja2", "jinja2.ext", "werkzeug",
        # WebView
        "webview", "webview.platforms.edgechromium",
        # PIL
        "PIL", "PIL.Image", "PIL.ImageFile",
        # Transformers / Torch
        "transformers",
        "transformers.models.blip",
        "transformers.models.blip.modeling_blip",
        "transformers.models.blip.processing_blip",
        "torch", "torchvision",
        # Misc
        "requests", "packaging", "filelock", "huggingface_hub",
        "regex", "tqdm", "safetensors",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "scipy", "pandas",
        "notebook", "IPython", "pytest",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GenMeta",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,   # no CMD window
    # icon="icon.ico",   # uncomment and add icon.ico to use a custom icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="GenMeta",
)
