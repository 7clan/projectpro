# DÉCLIC — Technical architecture and limitations

## Scope

One reliable vertical experience: a civil-engineering student working on support reactions for simply supported beams with an interior downward point load **P** at distance **a**, and an optional uniformly distributed load **q** along the whole span **L**. The left support is a pin and right support a roller, both vertical reactions; no horizontal force, beam self-weight, overhangs, applied couples, nonlinear behavior, or deflections.

## The statics engine (deterministic)

Using kN, kN/m, and m:

- `RA + RB = P + qL`
- `RB·L = P·a + (qL)(L/2)`
- `RA = P(L−a)/L + qL/2`
- `RB = Pa/L + qL/2`
- `V(x) = RA − qx − P·H(x−a)`
- `M(x) = RA·x − qx²/2 − P·max(0,x−a)`

The **step discontinuity in shear at the point load** is intentional. The maximum bending moment is evaluated at supports, the point-load location, and internal stationary points where shear is zero. Each new case checks ΣFy, ΣMA, M(0), and M(L), and numerical results are regression-tested with known hand-solutions.

**Example:** L=8 m, P=12 kN, a=2 m, q=2 kN/m → RA=17 kN, RB=11 kN. An answer of RA=9/RB=3 misses the distributed-load resultant; a reversed pair misses lever-arm orientation.

## Data model

- `users(id, name, email, password_hash, exam_date, created_at)`
- `sessions(token_hash, user_id, expires)`
- `challenges(id, user_id, kind, length, load, position, udl, created_at)`
- `attempts(id, user_id, challenge_id, stage, concept, correct, misconception, input, created_at)`
- `documents(id, user_id, title, subject, data, page_count, created_at)`
- `document_pages(document_id, page, content)`
- `reading_events(user_id, document_id, page, activity, seconds, created_at)`

Stages are immutable per challenge (`UNIQUE(user_id,challenge_id,stage)`). A student cannot improve a wrong score simply by repeating the same submission: a new exercise is necessary. This design intentionally captures first attempts, but can be extended with explicit retries and interleaved spaced practice.

## Mastery heuristic

For each concept, the last 8 attempts are combined into a small Bayesian-style smoothed score: `(1 + weighted_correct) / (2 + weighted_attempts) × 100`. Independent transfer attempts receive 3× the weight of guided attempts. No attempts means **not evaluated**, never 0%. Priorities select weak/unassessed foundational concepts using these scores and concept importance. A warning is generated only when a specific misconception appears at least twice. The exam date raises urgency without fabricating a failure probability.

A single weighted scalar cannot replace validated concept assessment. We should compare this heuristic with expert marking, calibrate item difficulty, measure discrimination, and include teacher oversight before using it beyond a demo.

## Document tracking

Uploaded PDF bytes are parsed with PyMuPDF and stored locally; text extraction is capped at 20,000 characters per page. The reader renders authenticated pages server-side. `view` is recorded when navigating to a page; every 5 seconds in a focused browser the client checks for activity within the prior 30 seconds, and flushes active seconds in batches. This is **approximate interaction time**, not proof of reading, concentration or comprehension. The current browser may lose a few seconds when the page closes abruptly, by design avoiding unauthenticated background beacons.

## Retrieval and optional coach

Selected page texts are retrieved via a basic term-frequency matcher; sources are returned with document title and page number. No embeddings or vector database are used at this stage; do not label this as semantic search or full production RAG. If a Gemini or OpenRouter key exists, a constrained Socratic prompt receives the question, beam parameters, and up to three retrieved excerpts. Otherwise deterministic guiding questions are returned. Numeric correctness remains the responsibility of `engine.py`; free-form AI is a learning aid, not the grader.

**Prompt injection risk:** PDF excerpts are untrusted and explicitly described as non-instructional; this reduces but does not eliminate prompt injection. External providers could receive course excerpts. Obtain consent before enabling live AI with real educational materials.

## Security posture

Prototype mitigations: 12 MB PDF cap, page count cap, file signature check, per-object ownership checks, PBKDF2 password hashing with salts, random opaque tokens and hashed token storage, token expiry, no user-provided HTML templates, output escaping, bounded inputs and strict model validation. Remaining gaps: HTTPS, CSRF defenses if moving to cookie auth, service-side rate limiting, retention/deletion controls, encrypted backups, file scanning/isolation, production observability, robust session revocation management, DPAs/consent and possible GDPR compliance, load testing and institutional access controls.

## Roadmap after the competition

1. **Evidence quality:** teacher-authored concept graph and verified item bank; transfer scoring against teacher rubrics.
2. **Privacy:** opt-in LLM retrieval, user deletion/export, retention policy, encryption at rest, HTTPS, rate limiting.
3. **Data / analytics:** event-sourced activity with explicit session boundaries; useful engagement signals separated from grades.
4. **Discovery:** resource catalog with verified metadata, curriculum mapping and source licensing; never fabricate recommendations.
5. **Generalize:** subject plugins and multiple simulation engines, then institution/teacher views under explicit authorization.
6. **Evaluation:** run blinded pre/post + delayed transfer assessments with consent before claiming any causal learning gains.
