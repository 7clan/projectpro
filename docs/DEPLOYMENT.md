# Deployment readiness

Local/private pilot only: `docker compose up --build -d`. The service binds to 127.0.0.1 on the host, runs as a non-root user, uses a persistent SQLite volume and includes French/English Tesseract OCR. To install neural voice models into its named volume, run:

```sh
docker compose exec declic python -m piper.download_voices --data-dir /app/voices fr_FR-siwis-medium en_US-lessac-medium
```

Check model licenses before redistributing weights. Provide credentials in an untracked .env alongside compose.yml; never put keys in HTML. `docker compose down` preserves named volumes; `down -v` deletes them. Use a consistent SQLite backup and test restoration before upgrades.

Before an internet-facing deployment: choose a hosting target and domain; configure TLS, HTTPS-only cookies or hardened bearer-token handling, per-user/IP rate limits and abuse prevention, encrypted storage/backups, account lifecycle and retention policies, consent and administrative controls, monitoring, vulnerability scanning, and recovery procedures. The current prototype is single-instance and not an institutional LMS. No public deployment is claimed. The private localhost HTTPS workflow has verified a trusted local certificate, HTTP-to-HTTPS redirect, security headers and the liveness probe.

Local Ollama: run Ollama on the same host as the Python server, install a supported instruct model, then set DECLIC_OLLAMA_MODEL to that exact installed name. DECLIC_LOCAL_ONLY=1 avoids external LLM and cloud speech calls. Local-only mode disables browser recognition; optional Vosk speech models and dependencies must be installed to enable local microphone input. The default Docker image does not include Vosk. Loopback Ollama is intended for native host startup, not this isolated Docker container. Local generation is limited by hardware, memory, speed and model quality; there is no promise of unlimited capacity or correct outputs.


## Optional HTTPS configuration (not publicly deployed)

The repository includes `compose.https.yml` and `deploy/Caddyfile`. After a security review, provision a Linux host and domain; set `DECLIC_DOMAIN` in your server's untracked environment, direct DNS to that host and allow ports 80/443. Only then consider `docker compose -f compose.yml -f compose.https.yml up -d --build`. Caddy obtains/renews TLS certificates for a qualifying public domain. Do not run the public configuration with real student records until institutional access, data retention, encryption, abuse prevention and recovery have been reviewed. See https://caddyserver.com/docs/automatic-https. The pilot middleware adds CSP, frame denial, MIME protection and optional in-memory limits, but the limits are not distributed or a robust defense against forged-token abuse.

Use `python scripts/healthcheck.py https://YOUR-DOMAIN/api/health` as a one-shot liveness/latency probe. A monitoring system must schedule the probe and alert an operator; none has been connected. Docker's existing healthcheck covers container liveness. Configure monitoring and backups on the actual host.

For operator approval of teachers, verify the person's identity outside the app and add their immutable account ID to `DECLIC_APPROVED_TEACHER_IDS` (comma separated); set `DECLIC_REQUIRE_APPROVED_TEACHER=1` to require that approval for publishing assignments. Do not use an unverified email claim as proof of identity. This is manual approval, not institutional SSO.

## Physical-device acceptance still required

Use actual Android Chrome, iOS Safari, and Windows Chrome/Edge. Confirm authentication, document upload, mixed scan, quiz, classroom membership/assignment, audio playback, and source navigation at each viewport. Enable microphone access explicitly. With headphones, test interruption of narration by speech; then test loudspeaker echo, noisy room, permission denial and revoked permission. Verify no microphone tracks remain active after leaving Studio or hiding the tab. Test TalkBack, VoiceOver and NVDA on labels, keyboard focus, announcement and diagram descriptions. Record device/OS/browser versions, expected result, actual result and screenshots. Emulation or synthetic recognition is not a substitute for these checks.
