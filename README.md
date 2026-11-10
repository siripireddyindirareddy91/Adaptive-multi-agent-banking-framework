# NEXORA Banking Intelligence

**Adaptive Intelligence. Secure Banking. Trusted Decisions.**

Live demo: https://nexora-banking-intelligence.vercel.app

A functional synthetic-data banking operations demonstration: React/TypeScript, Vite, FastAPI, SQLAlchemy, PostgreSQL/SQLite, twelve LangGraph specialists, ML baselines, evidence uploads, investigations, and authorized human review.

## Local setup

Requires Node 22+ and Python 3.12. Run these from the repository root:

```powershell
npm ci
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-ml.txt
python -m uvicorn backend.main:app --reload
```

In another terminal run `npm run dev`, then open http://localhost:5173. API docs: http://localhost:8000/docs. Alternatively, run `npm run build` and open http://localhost:8000 for single-origin serving.

For persistent PostgreSQL and the compiled application together:

```sh
docker compose up --build
```

Open http://localhost:8000. PostgreSQL persists in the named volume. Docker configuration is provided but has not been validated on this host.

## Demonstration accounts

All accounts use `NexoraDemo!2026` by default. Set `DEMO_PASSWORD` before initializing a fresh database to override it.

| Role | Email |
| --- | --- |
| Super Administrator | admin@nexora.demo |
| Operations Manager | reviewer1@nexora.demo |
| KYC Analyst | reviewer2@nexora.demo |
| Fraud Analyst | reviewer3@nexora.demo |
| AML Investigator | reviewer4@nexora.demo |
| Compliance Officer | reviewer5@nexora.demo |
| Risk Manager | reviewer6@nexora.demo |
| Approval Officer | reviewer7@nexora.demo |
| Auditor | reviewer8@nexora.demo |
| Read-Only Analyst | reviewer9@nexora.demo |

Passwords use Argon2. JWT access tokens last 45 minutes; refresh tokens rotate and are hashed in storage. The UI keeps its access token in session storage. These public demo accounts must never be used with real customer information.

## Working features

- Fourteen navigable modules covering command center, onboarding, identity, fraud, transactions, AML, compliance, risk, agents, approvals, cases, analytics, audit and configuration.
- Database-derived dashboards, date-range trends, searchable/paginated tables, status filters, CSV exports and browser print/save-to-PDF.
- Four-step onboarding, required consent, age/email validation, duplicate detection, masked identity reference, drafts and resume.
- Authenticated PDF/PNG/JPEG uploads, 5 MB limits, signature checks, SHA-256 duplicate detection and evidence previews. Authenticity is explicitly unverified.
- Typed LangGraph execution with twelve specialist nodes, conditional investigations, retry policies, structured findings and SQL snapshots after each node.
- Synthetic fuzzy watchlist screening, rule-based risk, separate confidence/uncertainty, optional evidence-only LLM summaries.
- Human approval requires an authorized reviewer, a reason, mandatory consent and uploaded evidence. No self-approval. Elevated risk requires two distinct reviewers.
- Investigation creation, assignees, notes, priority/status updates, alert resolution and append-only application audit events.
- Editable/versioned illustrative policy controls evaluated during workflows, configurable thresholds and visible integration status.
- Ten executable synthetic scenarios. Seed: 500 customers, 300 applications, 1,000 transactions, 100 alerts, 50 cases, 30 rules, 25 pending approvals, and 100 initial audit events. Agent execution metrics come from actual workflow runs.

## Architecture

```text
React + Vite + TypeScript + Router + TanStack Query + Recharts + Lucide
                         |
                   FastAPI /api/v1
                         |
          SQLAlchemy -> PostgreSQL / local demo SQLite
                         |
                LangGraph typed StateGraph
Orchestrator -> Profiling -> Documents -> KYC -> AML -> Fraud
-> Transactions -> Risk -> Compliance -> [Investigation]
-> Explainability -> Human Approval Router -> authorized API decision
```

Completed nodes save their state/evidence in workflow rows. The graph ends at an application-level waiting state; authorized decisions update that persisted workflow. This is **not** native LangGraph `interrupt()`/checkpointer recovery. Failed traces preserve completed evidence, but automatic continuation from a failed node is not implemented. Execution is synchronous within Vercel's 60-second limit; no Celery/Redis workers are configured.

Normalized tables cover users, customers, applications, documents, transactions, alerts, cases, rules, workflows, approvals, audit, settings and refresh tokens. Structured agent findings live in workflow JSON. This is a smaller schema than the brief's proposed 30-table schema. An initial Alembic migration is included.

## ML and optional LLM

```sh
python scripts/train_models.py
```

Trains scikit-learn Random Forest and Isolation Forest baselines on reproducible synthetic data, exports versioned trees to `backend/baseline_models.json`, and records holdout precision, recall, F1, confusion matrix and ROC-AUC. Portable inference runs those exported trees without the heavy training libraries in Vercel. `/api/v1/models` exposes evaluation metadata. Synthetic metrics are not real banking accuracy; global feature importance is not SHAP or a local causal explanation.

Default summaries are deterministic. Optional OpenAI-compatible/Ollama endpoints use `LLM_BASE_URL` (including `/v1`), `LLM_MODEL`, and `LLM_API_KEY`. The adapter validates structured outputs, bounds timeouts, retries once, excludes personal identifiers/document bytes, grants no tools, and falls back safely. LLM output cannot authorize banking decisions.

## Verification and APIs

```sh
npm run build
python -m pytest tests -q
python -m alembic upgrade head
```

Tests exercise authentication, read-only restrictions, seed metrics, scenario routing, no self-approval, missing evidence, dual independent approvals, duplicate applications, masking, invalid uploads, case notes, CSV export and refresh-token replay. OpenAPI is generated at `/docs` and `/openapi.json`.

Endpoints include `/api/v1/auth/login`, `/auth/refresh`, `/auth/me`, `/health`, `/dashboard/summary`, `/records/{resource}`, `/onboarding`, `/documents/{customer_id}`, `/workflows/run`, `/scenarios/launch`, `/approvals/{id}/decision`, `/cases`, `/rules`, `/settings`, `/export/{resource}`, `/models` and `/events`. Records and mutations require bearer authentication. SSE offers bounded snapshots and reconnect instructions; dashboard polling runs every 15 seconds.

## Vercel

```sh
vercel deploy --prod
```

Vite assets and `api/index.py` deploy together. **Set `DATABASE_URL` to an authorized PostgreSQL database for durable hosted persistence.** Without it, `/tmp/nexora.db` is temporary and can reset or differ between instances. The UI labels this limitation. Stable seeded IDs allow demo authentication across cold starts, but temporary SQLite is not shared production storage. See `.env.example`. Set a strong `JWT_SECRET`; it is required when `DEMO_MODE=false`.

Git push and direct CLI deployment are independent. Automatic deploy-on-push requires granting the Vercel GitHub integration repository access; the initial automatic linking attempt lacked that permission.

## Scope and limits

This is a functional portfolio/academic demonstration, **not production banking software or a complete implementation of every master-brief requirement**. No live government, sanctions, biometric, payment or regulatory-reporting integrations exist. No real accounts are opened, no payments move, and no AI independently approves or rejects customers.

Not implemented: OCR/authenticity verification, SHAP, native LangGraph checkpoints/interrupt recovery, Redis/Celery, device intelligence, cryptographically tamper-evident audit storage, field-level encryption, active retention deletion, permission-table administration, streaming agent transitions, external document storage, production drift monitoring and calibration. File signatures are checked; antivirus scanning is not configured. Regulatory controls are illustrative India/demo-1.0 policies, not verified current legal requirements. PDF reporting uses the browser print dialog.

A real deployment needs managed PostgreSQL, object storage/KMS, production identity/session hardening, shared rate limiting, observability and independent security/compliance validation. Do not enter real personal or banking data into this public demo.
