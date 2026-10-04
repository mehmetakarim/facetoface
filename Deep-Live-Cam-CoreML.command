#!/bin/bash
# Çift tıklayınca Terminal'de CoreML ile uygulamayı başlatır.
# İlk kullanımda: chmod +x "Deep-Live-Cam-CoreML.command"

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [[ ! -f "venv/bin/activate" ]]; then
  echo "venv bulunamadı. Önce: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  read -r _
  exit 1
fi

# Homebrew (ffmpeg vb.) — Apple Silicon varsayılan yolu
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

source venv/bin/activate
exec python run.py --execution-provider coreml
