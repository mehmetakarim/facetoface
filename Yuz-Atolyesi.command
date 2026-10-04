#!/bin/bash
set -e
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_PATH="$PROJECT_DIR/desktop/src-tauri/target/debug/bundle/macos/Yüz Atölyesi.app"
if [[ -d "$APP_PATH" ]]; then
  open "$APP_PATH"
else
  echo "Yüz Atölyesi henüz derlenmemiş."
  echo "Projenin desktop klasöründe şu komutu çalıştırın:"
  echo "DEVELOPER_DIR=/Library/Developer/CommandLineTools npm run tauri -- build --debug --bundles app"
  read -r -p "Kapatmak için Enter tuşuna basın. "
fi
