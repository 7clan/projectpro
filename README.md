# DÉCLIC · From information to understanding

**AI Educathon 2026 · CNAM Liban · RDM2 (Civil Engineering)**

DÉCLIC is a French-first (English toggle), responsive adaptive-learning proof of concept. Rather than handing out a corrected answer, it connects an engineering exercise to a learner's evolving knowledge profile. It demonstrates one complete **predict → experiment → explain → independent transfer** cycle.

![Dashboard preview](docs/dashboard.png)

## Run locally

Requirements: **Python 3.10+** and a modern browser. No Node installation, database server, paid AI service, or Docker is required.

```bash
# macOS / Linux
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

```powershell
# Windows PowerShell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000** and choose **Explorer la démo immédiatement**. Alternatively register a local account.

For the PDF reader, upload **`data/demo_rdm2.pdf`** from this repository. No external network or model key is necessary for the principal learning flow. Google Fonts are an optional enhancement; the interface falls back to system fonts offline.

### Enable live AI and neural speech locally

GitHub Actions secrets do **not** transfer to your laptop. Set your own keys in the same terminal used to start the server. On Windows PowerShell:

```powershell
$env:GEMINI_API_KEY = "YOUR_GEMEINI_KEY"
$env:OPENROUTER_API_KEY = "YOUR_OPENROUTER_KEY"
$env:BAZAARLINK_API_KEY = "YOUR_SOME_KEY"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

To install offline French and English neural voices before starting:

```powershell
pip install -r requirements-voice.txt
New-Item -ItemType Directory -Force voices
python -m piper.download_voices --data-dir voices fr_FR-siwis-medium en_US-lessac-medium
```

On macOS/Linux use `export NAME="value"` instead of the PowerShell assignments. The `.env.example` file is a template; the application does not automatically load it. In Studio Live, enable external AI consent, keep generated animations and audio selected, then choose cloud speech or local Piper. Cloud voice tries Gemini, then the free HeyGen speech model via OpenRouter, then local Piper. The UI shows the actual backend. Free services may rate-limit requests.

BazaarLink prefers original animations, OpenRouter handles short tutoring requests, and Gemini is a fallback for text. Set `DECLIC_GEMINI_TEXT_FALLBACK=0` to reserve Gemini for voice when other providers are configured. Never commit credentials. The deterministic mechanics grading works without API keys.

See [neural voice setup](docs/NEURAL_VOICE.md).

## 4-minute live demonstration

1. **Dashboard** — the initial mastery estimate is intentionally blank; no fabricated scores.
2. **Laboratoire RDM** — set `L=8 m`, `P=12 kN`, `a=2 m`, `q=2 kN/m`, then click **Utiliser cette configuration**.
3. **Predict** — choose `RA = RB` (intentionally incorrect) and observe formative feedback.
4. **Solve** — enter `RA=9`, `RB=3` (deliberately forget the distributed load). The verified answer is `RA=17`, `RB=11`. DÉCLIC identifies the omitted load and shows shear and bending-moment plots.
5. **Explain** — explain force balance, lever arms, and the equilibrium of moments in your own words. The checklist flags missing reasoning cues; it is *not* a semantic proof of correctness.
6. **Transfer** — launch an independent case with different values, then return to the dashboard. The learner profile and next priority change.
7. **PDF tracker** — upload `data/demo_rdm2.pdf`, browse pages and see per-page activity analytics. **Active reading time ≠ understanding.**
8. **Coach & Discover** — use the always-on rule-based coach, optionally enable Gemini/OpenRouter, and see curated MIT, OpenStax and PhET resources.

A timed presenter script is in [`docs/DEMO_SCRIPT_FR.md`](docs/DEMO_SCRIPT_FR.md).

## Implemented

| Feature | Implementation | Important distinction |
|---|---|---|
| F01 authentication | Local registration/login, hashed passwords, bearer sessions, one-click isolated demo | Single-instance prototype; not a university SSO |
| F02–F03 course PDFs | PDF upload, extraction, rendered in-app pages, source excerpts | Native extraction plus bounded local Tesseract OCR; deferred pages can be retried |
| F04 learning profile | Per-concept heuristics weighted toward independent transfer | Not a validated psychometric score |
| F05 interactive beam | Load parameters, SVG beam, shear and moment diagrams | One simply supported beam model |
| F06 recurring mistakes | Deterministic classifications; moment arms, omitted UDL, force balance | Heuristic, limited to this model |
| F07 guided learning | Rule-based Socratic tutor, optional external LLM | LLM answers are labeled and may err |
| F08 independent assessment | New parametric case; first attempt immutable | Not a proctored test |
| F09–F11 adaptive priorities | Based on mastery, importance, exam proximity | Explainable rules, not predictive ML |
| F12 resource discovery | Curated reputable links ranked by target concept | No live social/web crawler |
| F13 writing feedback | Transparent textual checklist on student's explanation | Does not establish actual correctness |
| F14 learning signals | Alert after repeated misconception | No predictive academic risk label |
| F16–F20 PDF analytics | Pages viewed, foreground activity, active time | Timer is approximate, not attention tracking |

New course tools include opt-in teacher classrooms, source-exact recall quizzes, and local scanned-page OCR. Not implemented: institutional SSO, validated conceptual quiz generation across arbitrary subjects, verified social-media recommendations, public production deployment, or measured improvements in educational outcomes. The term **“AI” describes the optional LLM coach and product direction**, not the deterministic parts.

## Verify the code

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

The test suite checks analytic equilibrium against independent formula values, error classification, user isolation, auth, PDF rendering/text extraction, activity tracking, coaching fallback, and a complete learning cycle. Run `python -m pytest -q` rather than bare `pytest` on environments where the current directory is not added to Python's import path.

## Architecture

```text
Browser (HTML / CSS / vanilla JS, FR/EN)
  ├── Dashboard / learner profile
  ├── SVG RDM2 simulator + charts
  ├── PDF reader with active-time events
  └── Socratic coach + curated resources
                    │ REST + Bearer auth
FastAPI            │
  ├── engine.py     → deterministic statics + explanation checklist
  ├── learning.py   → explainable mastery and priorities
  ├── ai.py         → lexical document retrieval + optional Gemini/OpenRouter
  ├── storage.py    → SQLite, salted PBKDF2 passwords, expiring sessions
  └── main.py       → validation, access control, file processing, API
                    │
               SQLite (local)
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for data flow, formulas, model limitations, threat model and deployment recommendations.

## Trust, privacy and ethics

- Every user owns their PDFs, reading events and attempts. Every document/challenge endpoint checks ownership.
- PDFs are stored locally in SQLite, with a 12 MB / 120 page limit. Session tokens expire after 3 days; passwords use salted PBKDF2-HMAC-SHA256.
- Raw uploaded content may be sent **as selected excerpts to Gemini/OpenRouter/BazaarLink only if a key is configured and the student explicitly consents when invoking the coach**. Refusing consent preserves the local guidance mode.
- In this one-day proof of concept, accounts are local, data is **not encrypted at rest**, and self-service account and document deletion are available, but there is no production-grade administrative consent workflow. Do **not** use this build with sensitive real student data or expose it publicly unchanged.
- The learning score is a transparent heuristic, not a grade or academic risk prediction. The explanation checklist uses keywords and can be fooled.
- Citation display indicates *retrieval provenance*, never automatic factual verification. Deterministic engineering results have priority.
- The included beam simulator is for instruction, **not structural design or safety decisions**.

## Foundational references

- [OpenStax, *University Physics* 12.1 — Conditions for Static Equilibrium](https://openstax.org/books/university-physics-volume-1/pages/12-1-conditions-for-static-equilibrium) — equilibrium of forces and torques.
- [MIT OpenCourseWare, *Solid Mechanics 1.050*](https://ocw.mit.edu/courses/1-050-solid-mechanics-fall-2004/) — introductory statics and structural mechanics, including determinate beams.
- [PhET, *Balancing Act*](https://phet.colorado.edu/en/simulations/balancing-act) — interactive torque and lever-arm intuition.

DÉCLIC is an independently developed competition prototype, not endorsed by the institutions above.

## Extended course tools and local deployment

- **Quiz:** select one document or all indexed courses. The quiz blanks out an exact source word, grades recall, and links each correction to its page. It does not measure conceptual mastery.
- **Classes:** create a classroom, share the one-time displayed join code, and view opted-in learner attempt/transfer counts from after enrolment. Students can revoke membership. No raw answers, PDFs, chats or email addresses are shared. Classroom ownership is self-service, not institutionally verified teacher identity.
- **OCR:** install Tesseract with French and English language data (and add its executable to PATH). Upload automatically attempts up to 12 scan pages within a bounded time. Use OCR / Retry scan for an unindexed page; review OCR text before relying on it.
- **Voice interruption:** click Interrupt or Micro to interrupt playback and cancel pending browser work. Optional speech auto-send submits recognized final text; recognition availability depends on the browser. This is turn-based conversation, not full-duplex streaming.
- **Local AI:** optional Ollama on localhost. Set DECLIC_OLLAMA_MODEL to an installed model and DECLIC_LOCAL_ONLY=1 to avoid external LLM and speech calls. Model performance depends on hardware; local AI mode disables browser recognition and requires the optional Vosk models for microphone use.
- **Docker:** see [private pilot deployment instructions](docs/DEPLOYMENT.md). No public hosting is claimed.

## Windows: use your installed Ollama

Open Ollama from the Start menu. In PowerShell, run `ollama list` to inspect installed models. If no suitable model is installed, `ollama pull qwen2.5:3b-instruct` downloads a relatively small multilingual model (about 1.9 GB). From the repository folder, run `powershell -ExecutionPolicy RemoteSigned -File .\start-local.ps1` and select an installed local model. If a downloaded script is blocked, inspect its contents and use `Unblock-File .\start-local.ps1` only if you trust it. The launcher creates a virtual environment if needed and installs dependencies. Alternatively set `DECLIC_OLLAMA_MODEL` and `DECLIC_LOCAL_ONLY=1` in your current terminal before starting Uvicorn. Local-only mode permits original animations without external sharing consent. Keep external consent unchecked. For additional privacy set `OLLAMA_NO_CLOUD=1` in the Windows user environment and restart Ollama, as described in [Ollama's local FAQ](https://docs.ollama.com/faq). `ollama ps` shows whether a model is using CPU or GPU. Install Piper separately for offline neural speech. Use `-Hybrid` on the launcher only if you want cloud fallbacks with explicit external consent; keys must be configured on your laptop.

The GitHub Actions [Ollama acceptance workflow](.github/workflows/ollama-acceptance.yml) installs its own local model and captures actual generated lessons with Piper audio. It cannot use your laptop's Ollama server.


### Extended learning and voice features

The Quiz screen offers exact-source recall plus deterministic RDM2 conceptual MCQs with selectable difficulty and adaptation based on prior statics attempts. Classes support publishing and completing statics assignments, score reports and weekly practice trends. Teacher identity remains unverified unless explicitly approved by an operator after an external check. Assignment due dates are informational.

Experimental voice interruption uses local microphone amplitude detection with echo cancellation, then invokes the selected speech recognizer. In local mode it uses Vosk and never falls back to browser speech recognition. Use a headset, opt in and continue speaking after interruption. This is not full-duplex streaming, and the recognizer may use the browser vendor's service. Permission must be tested on real hardware.

Small local Ollama models generate schema-constrained semantic plans (triangle, force and flow diagrams) rather than unrestricted SVG instructions. The application validates supported relationships and checks the diagram against recognized question types and explicit numeric parameters; no unrestricted academic guarantee is implied. For local-only operation install Piper separately and keep the external service consent off.

For public hosting preparation and physical-device testing, see [deployment instructions](docs/DEPLOYMENT.md).


## AI mode selector and streaming speech

Studio, Coach and Quiz share a mode selector: Cloud (Gemini/OpenRouter/BazaarLink), Hybrid (cloud with Ollama fallback), or Local (Ollama). A server started with DECLIC_LOCAL_ONLY=1 locks all requests to local processing; use start-local.ps1 -Hybrid with locally configured keys to enable all choices. Cloud requests still require explicit consent; selecting local clears previous cloud consent. The Studio AI providers panel checks the loopback Ollama daemon and installed model without testing cloud quotas. See https://docs.ollama.com/api/tags.

To enable French and English local speech recognition on Windows, from the repository folder after the Python environment exists:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-speech.txt
New-Item -ItemType Directory -Force speech-models
Invoke-WebRequest https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip -OutFile speech-models/fr.zip
Expand-Archive speech-models/fr.zip -DestinationPath speech-models -Force
Invoke-WebRequest https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -OutFile speech-models/en.zip
Expand-Archive speech-models/en.zip -DestinationPath speech-models -Force
```

Restart DÉCLIC and choose Vosk recognition in Studio. Vosk accepts streaming 16 kHz PCM via the authenticated same-origin WebSocket and returns partial and final transcripts. Audio is not stored. Local speech is processed on the **DÉCLIC server**, so it is on your own laptop only when you run the server there. Browser recognition remains optional in cloud/hybrid mode. Use headphones; automatic acoustic interruption is experimental, and true simultaneous model output streaming remains unimplemented. See [Vosk models and licenses](https://alphacephei.com/vosk/models). The real browser acceptance test used French synthetic microphone audio, not a physical device.

The new AI Course MCQ option samples up to four indexed pages and returns up to six questions per request. It requires an exact supporting excerpt and a correct option appearing in that excerpt. Independent model review, when available, can reject the batch; otherwise it is labelled unreviewed. These checks do not prove conceptual correctness or full-course coverage. Source recall and deterministic RDM2 questions remain separate choices.


## Use Ollama Cloud from your existing Windows desktop app

Sign in to Ollama and select a working cloud model in its desktop chat. Start DÉCLIC with the exact cloud name displayed there, e.g.:

```powershell
powershell -ExecutionPolicy RemoteSigned -File .\start-local.ps1 -Hybrid -Model qwen2.5-coder:3b -CloudModel nemotron-3-super:cloud
```

No new model weights or separate Ollama API key are required. The launcher reads private .env settings automatically. In Studio, Coach or Quiz select Ollama · Cloud, then grant external processing consent. Cloud requests are sent through the fixed localhost Ollama API, and Ollama authenticates and executes them remotely. Cloud models do not support structured outputs, so DÉCLIC requests plain JSON and validates it before using it. Local mode remains isolated from cloud requests. Hybrid can fall back to the configured cloud model; cloud usage is subject to the Ollama account's current plan, quotas and charges. The provider panel checks daemon reachability, not cloud authentication or remaining quota. To change cloud model, restart with a different -CloudModel value or configure DECLIC_OLLAMA_CLOUD_MODEL in .env. Never assume this mode is offline. See https://docs.ollama.com/cloud/models and https://docs.ollama.com/capabilities/structured-outputs.


### Optional extra neural voices (Windows)

The original Piper and cloud engines are unchanged. Download only the voices you want using your existing Python environment:

```powershell
.\.venv\Scripts\python.exe -m piper.download_voices --data-dir voices en_US-amy-medium en_US-ryan-medium en_GB-alba-medium fr_FR-tom-medium
```

Reopen Live Studio, choose **Piper · local**, and select an installed **Voice profile** for the lesson language. Default retains the existing Lessac (English) or Siwis (French). Additional local profiles never send narration to a cloud service and do not load Ollama. Voice downloads are optional; no model files are committed. Each voice has its own model-card license: https://huggingface.co/rhasspy/piper-voices. The branch recording uses actual synthesized audio played by Chromium, with a controlled guided lesson for a fair comparison; the recording does not establish that the explanation itself was generated by a live LLM.


### Optional Kokoro English narration

Kokoro provides Michael and an optional smooth Michael profile (slightly slower delivery and quiet-gap attenuation). It is independent of Ollama and cloud APIs. Existing Piper and cloud voices remain unchanged. Install only if you want to try these voices:

```powershell
.\.venv\Scripts\python.exe -m pip install kokoro-onnx==0.6.0
New-Item -ItemType Directory -Force voices\kokoro | Out-Null
curl.exe -fL --retry 2 https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx -o voices/kokoro/kokoro-v1.0.onnx
curl.exe -fL --retry 2 https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin -o voices/kokoro/voices-v1.0.bin
```

Restart DÉCLIC, use an English lesson, select the local speech engine and choose a Kokoro voice profile. The models are loaded lazily and the ONNX session uses two CPU inference threads. The model download is optional and stored in the ignored voices folder. Cue groups can share a phrase-start timestamp to keep longer, more natural phrases. The upstream model is Apache-2.0 and the ONNX library is MIT: https://github.com/thewh1teagle/kokoro-onnx.


### Optional Pocket TTS comparison

Pocket George and Pocket Alba use Kyutai's standalone runtime. Download the official v4.0.1 Windows x86_64 archive from https://github.com/kyutai-labs/pocket-tts/releases/tag/v4.0.1 and extract the executable to `voices/pocket/pocket-tts.exe`. Initialize the model and each voice with the official CLI before use. This first initialization requires Internet access to fetch the public pretrained model and voice assets; subsequent inference is performed on the CPU. The application does not send narration to a TTS API. No arbitrary reference voice or user-provided executable path is accepted. Use the supplied voice identifiers, not personal voice recordings. Model and voice attribution: https://huggingface.co/kyutai/pocket-tts-without-voice-cloning and https://huggingface.co/kyutai/tts-voices. Quality and startup latency must be evaluated before enabling by default.


### Install the approved automatic fallback voices

After pulling the updated main branch, run this once in the existing Windows PowerShell virtual environment:

```powershell
.\.venv\Scripts\python.exe scripts\install_voice_fallbacks.py
```

The installer downloads and verifies the pinned Pocket TTS runtime, initializes the English George model, installs French Piper Tom, and synthesizes actual WAV files for both. It requires Internet for first-time asset installation; a successful installation prints both PASS lines. The existing launcher does not automatically download large voice assets. Cloud narration prefers HeyGen, then Gemini; automatic local narration prefers George for English and Tom for French. Smooth Michael is an optional English backup if its assets and dependencies are separately installed (see Kokoro instructions above). Existing Piper voices remain emergency backups. Browser status reports the backend that actually rendered the scene. If a chosen voice fails, explicit selection is not silently replaced.
