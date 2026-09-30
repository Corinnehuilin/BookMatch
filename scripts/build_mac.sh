#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller-cache"
.venv/bin/python -m PyInstaller --noconfirm --clean --windowed --name BookMatch \
  --osx-bundle-identifier org.bookmatch.desktop \
  --icon assets/bookmatch-icon.png \
  --add-data 'data/catalog.json:data' \
  --add-data 'data/cover_ids.json:data' \
  --add-data 'assets/bookmatch-icon.png:assets' \
  --add-data 'THIRD_PARTY_NOTICES.md:.' \
  --add-data 'third_party:third_party' \
  --add-data 'data/SOURCE.md:data' \
  --copy-metadata PySide6 \
  --copy-metadata PySide6_Essentials \
  --copy-metadata PySide6_Addons \
  --copy-metadata shiboken6 \
  --collect-all fastembed \
  --collect-all onnxruntime \
  run_bookmatch.py
.venv/bin/python -m scripts.stamp_mac_bundle
codesign --force --deep --sign - dist/BookMatch.app
ditto -c -k --sequesterRsrc --keepParent dist/BookMatch.app dist/BookMatch-mac-arm64.zip
