# Deployment readiness

Local/private pilot only: `docker compose up --build -d`. The service binds to 127.0.0.1 on the host, runs as a non-root user, uses a persistent SQLite volume and includes French/English Tesseract OCR. To install neural voice models into its named volume, run:

```sh
docker compose exec declic python -m piper.download_voices --data-dir /app/voices fr_FR-siwis-medium en_US-lessac-medium
```

Check model licenses before redistributing weights. Provide credentials in an untracked .env alongside compose.yml; never put keys in HTML. `docker compose down` preserves named volumes; `down -v` deletes them. Use a consistent SQLite backup and test restoration before upgrades.

Before an internet-facing deployment: choose a hosting target and domain; configure TLS, HTTPS-only cookies or hardened bearer-token handling, per-user/IP rate limits and abuse prevention, encrypted storage/backups, account lifecycle and retention policies, consent and administrative controls, monitoring, vulnerability scanning, and recovery procedures. The current prototype is single-instance and not an institutional LMS. No public deployment is claimed.

Local Ollama: run Ollama on the same host as the Python server, install a supported instruct model, then set DECLIC_OLLAMA_MODEL to that exact installed name. DECLIC_LOCAL_ONLY=1 avoids external LLM and cloud speech calls. Browser speech recognition may still depend on the browser vendor's service; disable it for a fully offline session. Loopback Ollama is intended for native host startup, not this isolated Docker container. Local generation is limited by hardware, memory, speed and model quality; there is no promise of unlimited capacity or correct outputs.
