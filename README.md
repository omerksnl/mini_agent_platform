# Mini Agent Platform

<p align="center">
  <strong>Build, connect, observe, and run AI agents and visual models from one workspace.</strong>
</p>

<p align="center">
  <a href="#quick-start"><img alt="Quick start" src="https://img.shields.io/badge/Quick_Start-Docker-e25555?style=for-the-badge&logo=docker&logoColor=white"></a>
  <a href="#platform-capabilities"><img alt="Features" src="https://img.shields.io/badge/Explore-Features-e25555?style=for-the-badge"></a>
  <a href="#visual-models-and-gpu-training"><img alt="GPU training" src="https://img.shields.io/badge/Visual_Models-GPU-76b900?style=for-the-badge&logo=nvidia&logoColor=white"></a>
  <a href="http://localhost:5173"><img alt="Open application" src="https://img.shields.io/badge/Open-App-222222?style=for-the-badge"></a>
  <a href="http://127.0.0.1:8000/docs"><img alt="API documentation" src="https://img.shields.io/badge/Open-API_Docs-009688?style=for-the-badge&logo=fastapi&logoColor=white"></a>
</p>

Mini Agent Platform is a multi-tenant AI workspace for configuring agents, reusable knowledge, tools, safety controls, multi-agent systems, visual workflows, A2A connections, and trainable image-classification models. It combines React with FastAPI, PostgreSQL, Redis, LangGraph, optional Langfuse tracing, and Docker deployment.

> [!IMPORTANT]
> Keep real API keys in `backend/.env`. Never commit that file or paste secrets into issues, screenshots, or documentation.

## Navigation

| Workspace | Purpose | Local link |
|---|---|---|
| Home | Platform overview and recent resources | [Open Home](http://localhost:5173/) |
| Single-agent | Agents, tools, skills, collections, and guardrails | [Open Agents](http://localhost:5173/agents) |
| Multi-agent | Routers and supervisors | [Open Multi-agent](http://localhost:5173/multi-agent) |
| Workflows | Visual workflow editor and execution monitoring | [Open Workflows](http://localhost:5173/workflows) |
| Chat | Persistent conversations with local and remote agents | [Open Chat](http://localhost:5173/chat) |
| Visual models | Configure, train, and run image classifiers | [Open Visual Models](http://localhost:5173/visual-models) |
| AI providers | Platform and personal OpenRouter/OpenAI credentials | [Open Providers](http://localhost:5173/providers) |
| API | Interactive FastAPI documentation | [Open Swagger](http://127.0.0.1:8000/docs) |

These links work after the local stack is running.

## Platform capabilities

### Agent workspace

- Create agents with selectable provider profiles, models, temperature, and system prompts.
- Keep recent prompt versions, inspect their scores, restore a version, or generate an improved AI draft.
- Assign system tools, custom HTTP tools, reusable skills, searchable collections, deterministic guardrails, and remote A2A agents.
- Persist tenant-scoped conversations and provide configurable short-term memory.
- Display used tools, skills, delegated agents, and API cost alongside responses.

### Knowledge and tools

- Upload documents, chunk their content, create embeddings, and retrieve relevant passages through `collection_search`.
- Create reusable skills with optional output schemas and required-tool declarations.
- Create validated `GET` and `POST` HTTP tools with typed parameters.
- Use safe calculation, current date/time, PDF text extraction, and registered-template PDF generation.
- Protect HTTP execution with argument validation, blocked private addresses, redirect restrictions, response limits, and timeouts.

### Multi-agent systems

- **Router:** selects exactly one appropriate specialist for each request.
- **Supervisor:** dynamically coordinates managed agents and passes their results between stages.
- **A2A:** publishes an agent through an Agent Card and authenticated task endpoint, or connects another account's public agent as a remote capability.
- Track delegated-agent usage and costs without exposing system prompts or tenant data in Agent Cards.

### Visual workflows

- Drag local agents, remote agents, nested workflows, human waits, and report nodes onto a canvas.
- Connect nodes with outcome-aware edges and preserve node positions.
- Execute independent branches in parallel while retaining deterministic dependency handling.
- Pause for human input, resume the same run, transfer artifacts, and inspect rendered Markdown output.
- Monitor step and edge state, progress, per-step cost, total cost, and generated reports on the canvas.

### Safety and observability

- Apply deterministic guardrails at user input, tool input, tool output, and agent output stages without another LLM call.
- Redact configured PII, block disallowed content, and record guardrail decisions.
- Store token and API-cost data locally from provider usage responses.
- Optionally send agent, tool, workflow, artifact, cost, and guardrail events to Langfuse.
- Keep application records tenant-isolated in PostgreSQL.

## Architecture

```text
React + Nginx
      |
      v
FastAPI API
  |-- LangChain / LangGraph agent runtime
  |-- Workflow, router, supervisor, and A2A services
  |-- RAG, tools, skills, guardrails, PDF, and visual training services
  |
  +--> PostgreSQL + pgvector   persistent source of truth and embeddings
  +--> Redis                   cache and deferred execution support
  +--> OpenRouter / OpenAI     language-model providers
  +--> Langfuse (optional)     traces, sessions, scores, and annotations
  +--> TensorFlow              CPU or NVIDIA GPU visual-model training
```

| Compose service | Responsibility |
|---|---|
| `postgres` | PostgreSQL 16 + pgvector with persistent storage |
| `redis` | Redis 7 cache and coordination layer |
| `backend` | FastAPI; applies Alembic migrations before startup |
| `frontend` | Production React build served by Nginx |

## Quick start

### Requirements

- Docker Desktop
- Git
- An OpenRouter or OpenAI API key, unless a platform key is already configured
- Optional: NVIDIA GPU with a working Docker/WSL2 GPU runtime

### 1. Configure the backend

```powershell
cd C:\Users\EXCALIBUR\Documents\Codex\Intern_Project
Copy-Item backend\.env.example backend\.env
```

Generate a JWT signing secret:

```powershell
py -3.12 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set the generated `SECRET_KEY` and one provider in `backend/.env`:

```env
SECRET_KEY=replace-with-the-generated-secret
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=replace-with-your-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

For direct OpenAI instead:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=replace-with-your-key
OPENAI_BASE_URL=https://api.openai.com/v1
```

Users may also save encrypted personal provider profiles from **AI providers** and assign different profiles to different agents.

### 2. Start the platform

CPU-compatible stack:

```powershell
docker compose up -d --build
```

NVIDIA GPU-enabled visual training:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

The first GPU build downloads TensorFlow CUDA libraries and is substantially larger than the CPU image. Later builds reuse Docker cache.

### 3. Open and verify

- Application: [http://localhost:5173](http://localhost:5173)
- API documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

```powershell
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
docker compose exec backend python -m alembic current
docker compose exec postgres pg_isready -U agent -d agent_platform
docker compose exec redis redis-cli ping
```

Stop without deleting persistent data:

```powershell
docker compose down
```

PostgreSQL, Redis, attachments, datasets, and generated artifacts use persistent storage. Do not add `--volumes` unless you intentionally want to remove stored data.

## Local development

Requirements: Python 3.12, Node.js, and Docker Desktop.

```powershell
cd C:\Users\EXCALIBUR\Documents\Codex\Intern_Project\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

cd ..\frontend
npm install

cd ..
.\start.ps1
```

`start.ps1` starts PostgreSQL and Redis in Docker, applies outstanding migrations, and runs FastAPI and Vite locally. It does not erase migrations or database data.

## Visual models and GPU training

Visual Models provides a configurable image-classification workflow:

1. Create a model and define at least two classes.
2. Select an architecture and image size.
3. Upload images or a class-folder ZIP dataset.
4. Configure epochs, batch size, validation split, learning rate, and compute device.
5. Train asynchronously and monitor accuracy, validation accuracy, loss, and validation loss.
6. Test the saved model with an uploaded image or live browser-camera capture.

| Device option | Behavior |
|---|---|
| `Auto` | Uses a detected GPU; otherwise falls back to CPU |
| `CPU` | Forces CPU execution |
| `GPU` | Requires an available GPU and reports an error if none is detected |

GPU training enables TensorFlow memory growth to avoid reserving all VRAM. Each run records the requested device, actual device, and detected device name.

Verify GPU access inside Docker:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec backend `
  python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

## Langfuse tracing

Langfuse is optional. Add project credentials to `backend/.env`:

```env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=development
```

Then rebuild the backend:

```powershell
docker compose up -d --build backend
```

If Langfuse is unavailable, execution continues using local PostgreSQL cost records. Traces may contain prompts, CV data, interview responses, tool input, and model output; use an approved retention policy with real personal data.

## Environment reference

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection |
| `SECRET_KEY` | JWT signing secret |
| `LLM_PROVIDER` | Platform default: `openrouter` or `openai` |
| `OPENROUTER_API_KEY` | Platform OpenRouter credential |
| `OPENAI_API_KEY` | Platform OpenAI credential |
| `REDIS_URL` | Redis connection |
| `CORS_ORIGINS` | Allowed browser origins |
| `SHORT_TERM_MEMORY_MESSAGES` | Recent messages included in agent context |
| `AGENT_TOOL_CALL_LIMIT` | Tool-call safety limit per execution |
| `AGENT_MODEL_CALL_LIMIT` | Model-call safety limit per execution |
| `LANGFUSE_PUBLIC_KEY` | Optional Langfuse public key |
| `LANGFUSE_SECRET_KEY` | Optional Langfuse secret key |
| `ATTACHMENT_MAX_BYTES` | Maximum attachment size |
| `PDF_MAX_PAGES` | Maximum accepted PDF pages |

See [`backend/.env.example`](backend/.env.example) and [`.env.example`](.env.example) for complete configuration.

## Testing

```powershell
# Backend
cd backend
.\.venv\Scripts\python.exe -m pytest

# Frontend production build
cd ..\frontend
npm run build

# Focused visual-training tests
cd ..\backend
.\.venv\Scripts\python.exe -m pytest tests\test_visual_training.py -q
```

Tests use isolated data and do not modify the PostgreSQL development database.

## Troubleshooting

### Docker Linux engine pipe not found

Start Docker Desktop and wait until its engine reports **Running**, then retry.

### GPU is not listed

Confirm that `nvidia-smi` works, Docker Desktop uses WSL2, and the stack was started with `docker-compose.gpu.yml`. Then run the GPU verification command above.

### Login or chat reports connection refused

```powershell
docker compose ps
docker compose logs --tail 100 backend
Invoke-RestMethod http://127.0.0.1:8000/health
```

### Resetting data

Normal restarts preserve data. `docker compose down --volumes` deletes persistent volumes and should only be used deliberately.

---

<p align="center">
  <a href="http://localhost:5173"><strong>Open Mini Agent Platform</strong></a>
  ·
  <a href="http://127.0.0.1:8000/docs"><strong>Browse the API</strong></a>
  ·
  <a href="#quick-start"><strong>Back to Quick Start</strong></a>
</p>
