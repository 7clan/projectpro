# Studio Live neural narration

Install in the same virtual environment as DÉCLIC:

```sh
pip install -r requirements-voice.txt
mkdir voices
python -m piper.download_voices --data-dir voices fr_FR-siwis-medium en_US-lessac-medium
```

Restart uvicorn. The local server uses neural Piper speech first. The browser falls back to its installed speech voices if the optional neural model is unavailable. Set `DECLIC_ALLOW_ESPEAK=1` only to explicitly enable the old robotic fallback. Downloaded models are not committed. The voice model directory can be changed with `DECLIC_PIPER_DIR`. Audio cue timestamps use rendered frame counts. Local Piper sends no text to a speech API. With explicit external AI consent, choose the cloud voice in Studio Live to send only narration phrases to Gemini or the free HeyGen endpoint through OpenRouter. The verified model is gemini-3.8-flash-lite-tts; override with GEMINI_TTS_MODEL. Cloud synthesis is bounded to three phrases. The preference order is Gemini → OpenRouter HeyGen Voice Turbo (free) → Piper → browser voice; paid OpenRouter speech models are never selected automatically. A rate-limit response activates a provider cooldown. The UI reports the actual backend. The interface displays the actual engine. The audio timestamps mark rendered phrase starts, not word-level phoneme alignment.

With BazaarLink configured via BAZAARLINK_API_KEY (or the repository secret SOME mapped to that environment variable), original visual generation prefers BazaarLink and short text coaching prefers OpenRouter. Reviews prefer an independent BazaarLink model when available. BazaarLink requests send X-Free-Fallback: false; account-wide rate limits activate a shared cooldown. Independent review uses OpenRouter when it is configured, preserving Gemini capacity. Set `DECLIC_GEMINI_TEXT_FALLBACK=0` to reserve Gemini strictly for speech (when OpenRouter is configured); the default permits Gemini text fallback when OpenRouter fails. Both services have their own rate limits. The repository owner identified `SOME` as a BazaarLink key. It is sent only to the official BazaarLink API. All keys remain server-side.

Piper is GPL-3.0: https://github.com/OHF-Voice/piper1-gpl. Check each downloaded model's license and attribution before redistribution: https://huggingface.co/rhasspy/piper-voices/tree/main/fr/fr_FR/siwis/medium and https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/lessac/medium.
