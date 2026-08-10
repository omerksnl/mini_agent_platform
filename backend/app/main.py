from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import agents, attachments, auth, collections, conversations, skills, tools
from app.config import get_settings
from app.core.cache import redis_is_ready
from app.db.session import get_db
from sqlalchemy.orm import Session

settings = get_settings()

app = FastAPI(title="Mini Agent Platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")
app.include_router(tools.router, prefix="/api")
app.include_router(skills.router, prefix="/api")
app.include_router(attachments.router, prefix="/api")
app.include_router(collections.router, prefix="/api")


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    redis_ready = redis_is_ready()
    return {
        "status": "ok",
        "database": "ok",
        "redis": "disabled" if redis_ready is None else "ok" if redis_ready else "unavailable",
    }
