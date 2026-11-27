# Studio Live neural narration

Install in the same virtual environment as DÉCLIC:

```sh
pip install -r requirements-voice.txt
mkdir voices
python -m piper.download_voices --data-dir voices fr_FR-siwis-medium en_US-lessac-medium
```

Restart uvicorn. The local server uses neural Piper speech first. The browser falls back to its installed speech voices if the optional neural model is unavailable. Set `DECLIC_ALLOW_ESPEAK=1` only to explicitly enable the old robotic fallback. Downloaded models are not committed. The voice model directory can be changed with `DECLIC_PIPER_DIR`. Audio cue timestamps use rendered frame counts. Local Piper sends no text to a speech API. With explicit external AI consent, choose Gemini cloud in Studio Live to send only the narration phrases to Google's speech model. The verified model is gemini-3.8-flash-lite-tts; override with GEMINI_TTS_MODEL. Cloud synthesis is bounded to four phrases and may fall back to Piper if unavailable, rate limited or timed out. The interface displays the actual engine. The audio timestamps mark rendered phrase starts, not word-level phoneme alignment.

Piper is GPL-3.0: https://github.com/OHF-Voice/piper1-gpl. Check each downloaded model's license and attribution before redistribution: https://huggingface.co/rhasspy/piper-voices/tree/main/fr/fr_FR/siwis/medium and https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/lessac/medium.
