#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng curl unzip zstd
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-voice.txt -r requirements-speech.txt
mkdir -p voices speech-models
.venv/bin/python -m piper.download_voices --data-dir voices fr_FR-siwis-medium en_US-lessac-medium
for model in vosk-model-small-fr-0.22 vosk-model-small-en-us-0.15; do
  if [[ ! -d "speech-models/$model/am" ]]; then
    tmp="$(mktemp)"
    curl -fsSL --retry 2 "https://alphacephei.com/vosk/models/$model.zip" -o "$tmp"
    unzip -oq "$tmp" -d speech-models
    rm -f "$tmp"
  fi
done
echo "DÉCLIC dependencies, OCR, Piper and Vosk ready. Ollama is optional: bash .devcontainer/enable-ollama.sh"
