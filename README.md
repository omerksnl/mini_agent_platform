# Mini Agent Platform

## First-time setup

Requirements for local development: Python 3.12, Node.js, and Docker Desktop.
For the fully containerized setup, only Docker Desktop is required.

From the project directory:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Replace `SECRET_KEY` in `backend/.env` with a long random value. You can generate one with:

```powershell
py -3.12 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Add the company-provided OpenRouter key to `backend/.env` without committing it:

```env
OPENROUTER_API_KEY=*******
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_APP_TITLE=Mini Agent Platform
LLM_MAX_TOKENS=500
SHORT_TERM_MEMORY_MESSAGES=20
AGENT_TOOL_CALL_LIMIT=5
AGENT_MODEL_CALL_LIMIT=6
AGENT_RECURSION_LIMIT=15
HTTP_TOOL_TIMEOUT_SECONDS=10
HTTP_TOOL_MAX_RESPONSE_BYTES=1000000
```

The default model for newly created agents is `anthropic/claude-haiku-4.5`.

Then install the frontend dependencies:

```powershell
cd ..\frontend
npm install
```

## Running

### Local development

Run from the project directory. This starts PostgreSQL and Redis in Docker,
applies migrations, and runs the API and Vite UI locally:

```powershell
.\start.ps1
```

Open `http://localhost:5173`. API documentation is available at
`http://127.0.0.1:8000/docs`.

### Fully containerized

Keep the real backend settings in `backend/.env`; that file is excluded from
Git and from Docker build contexts. Then run:

```powershell
docker compose up --build
```

Open `http://localhost:5173`. The frontend proxies `/api` to the backend, and
the API is also exposed at `http://127.0.0.1:8000` for Swagger and diagnostics.

To run in the background:

```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f backend
```

Stop containers without deleting data:

```powershell
docker compose down
```

PostgreSQL and Redis use named volumes, so ordinary restarts and
`docker compose down` preserve data. Do not add `--volumes` unless you
intentionally want to delete the database and cache.

## Phase 2

Phase 2 includes LangChain/LangGraph `create_agent`, OpenRouter chat, persisted
conversations, the most recent 20 messages as short-term memory, tool-call limits,
built-in tools, and tenant-owned HTTP tools.

Built-in tools:

- `calculator`
- `current_datetime`
- `pdf_to_text` (extracts selectable text only from a PDF attached to the current chat message)
- `text_to_pdf` (renders Markdown with a registered safe template and returns an authenticated download)

`text_to_pdf` currently exposes two developer-managed templates: `blank_markdown` for a clean
single-column document and `two_column`, adapted from the LPPL-licensed Overleaf two-column CV
layout. Agents may select only these registered identifiers; they cannot submit arbitrary HTML or
LaTeX. Generated PDFs are tenant-scoped, size-limited, and stored separately from uploaded PDFs.

## CV extraction in chat

Migration `008_cv_skill` installs a tenant skill named `cv_extraction`. On the Agents page,
enable `pdf_to_text` and assign `cv_extraction` to the CV extraction agent. In Chat, attach a
PDF CV and ask the agent to extract a candidate profile. The result is returned in the same
conversation as evidence-based JSON; this stage does not score or rank the candidate.

Uploads are limited to PDF files, 10 MB and 50 pages by default. Text PDFs are supported.
Scanned/image-only PDFs return a clear OCR-required error and will be supported by the later OCR step.

HTTP tools are created at `/tools` in the React UI. Each tool has a lowercase
name, description, public HTTP/HTTPS URL, `GET` or `POST` method, and a validated
parameter schema. Agents can be configured with any combination of built-in and
tenant-owned tools from the agent editor.

HTTP tool safeguards include model-argument validation, blocked local/private
network addresses, disabled redirects, request timeouts, response-size limits,
and sanitized tool errors. Redis remains optional and is not required to run the
Phase 2 demo. Phase 3 provides Redis and `REDIS_URL`; PostgreSQL remains the
source of truth and cache failures do not delete persistent data.

## Phase 3: Docker and operations

The Compose stack contains four services:

- `postgres`: PostgreSQL 16 with a persistent volume and readiness check
- `redis`: Redis 7 with a persistent volume and readiness check
- `backend`: FastAPI; runs `alembic upgrade head` before every start
- `frontend`: production React build served by Nginx

Startup order is enforced by health checks: PostgreSQL and Redis become ready,
the backend applies outstanding migrations and becomes healthy, then the
frontend starts. Re-running migrations is safe: Alembic only applies revisions
that are not already recorded in the database.

Compose ports can be customized by copying the root example file:

```powershell
Copy-Item .env.example .env
```

The root `.env` controls container ports and PostgreSQL container credentials.
`backend/.env` contains application settings and the OpenRouter key.

Important environment variables:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection |
| `SECRET_KEY` | JWT signing secret |
| `OPENROUTER_API_KEY` | OpenRouter credential; never commit it |
| `OPENROUTER_BASE_URL` | OpenRouter API base URL |
| `REDIS_URL` | Optional Redis cache connection |
| `CORS_ORIGINS` | Allowed browser origins |
| `LANGFUSE_PUBLIC_KEY` | Optional Langfuse project public key |
| `LANGFUSE_SECRET_KEY` | Optional Langfuse project secret key |
| `LANGFUSE_BASE_URL` | Langfuse Cloud region or self-hosted URL |
| `LANGFUSE_TRACING_ENVIRONMENT` | Trace environment such as `development` |

## Langfuse observability

Langfuse tracing is optional and supplements the platform's own PostgreSQL API-cost
records. Create a Langfuse project, copy its public and secret keys into
`backend/.env`, and rebuild the backend:

```env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=development
```

```powershell
docker compose up -d --build backend
```

LangChain model, agent, and tool events are then sent to Langfuse. Workflow
steps include workflow, run, tenant, agent, and artifact-key metadata; traces
from the same workflow run share one Langfuse session ID. If the keys are empty
or Langfuse is temporarily unavailable, workflows and the existing cost tracker
continue to operate normally.

Tracing can include prompts, model responses, tool inputs, and tool outputs.
Because recruitment workflows may contain CV and interview information, use an
approved Langfuse deployment and retention policy before enabling tracing with
real candidate data. Leave both keys empty to keep tracing disabled.

Useful checks:

```powershell
docker compose config
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
docker compose exec backend python -m alembic current
docker compose exec postgres pg_isready -U agent -d agent_platform
docker compose exec redis redis-cli ping
```

If Docker reports that the Linux engine pipe cannot be found, start Docker
Desktop and wait until the engine shows as running before retrying.

Conversation API:

```text
POST   /api/conversations
GET    /api/conversations
GET    /api/conversations/{conversation_id}
PATCH  /api/conversations/{conversation_id}
DELETE /api/conversations/{conversation_id}
GET    /api/conversations/{conversation_id}/messages
POST   /api/conversations/{conversation_id}/messages
```

HTTP tool API:

```text
POST   /api/tools
GET    /api/tools
GET    /api/tools/{tool_id}
PATCH  /api/tools/{tool_id}
DELETE /api/tools/{tool_id}
```

The React UI provides agent management at `/`, chat at `/chat`, and HTTP tool
management at `/tools`. Tool calls used for an assistant response are persisted
and displayed below that message.

## Skills

Tenant-owned skills are reusable instruction packages assigned to agents from
the agent editor. A skill contains instructions, an optional JSON output schema,
an active state, and required system or HTTP tools. Assigning a skill never
grants tool access automatically; required tools must also be selected on the
agent.

```text
POST   /api/skills
GET    /api/skills
GET    /api/skills/{skill_id}
PATCH  /api/skills/{skill_id}
DELETE /api/skills/{skill_id}
```

The UI provides skill management at `/skills`. Active skills are appended to
the effective system prompt in agent assignment order. Inactive skills remain
stored but are not included in model prompts.

## Tests

Install the development dependencies once:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Run the complete backend test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The tests use a temporary in-memory database and do not modify the PostgreSQL development data.
