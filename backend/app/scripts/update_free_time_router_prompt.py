import argparse

from sqlalchemy import select

from app.core.services.agent_service import AgentService
from app.db.session import SessionLocal
from app.models import Agent, User
from app.schemas.agent import AgentUpdate
from app.scripts.seed_free_time_router import ROUTER_PROMPT


def main() -> None:
    parser = argparse.ArgumentParser(description="Update only the Free Time Router prompt.")
    parser.add_argument("--email", required=True, help="Existing platform user email")
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
        if not user:
            raise SystemExit(f"User not found: {args.email}")
        router = db.scalar(select(Agent).where(
            Agent.tenant_id == user.tenant_id,
            Agent.name == "free_time_router",
            Agent.agent_type == "router",
        ))
        if not router:
            raise SystemExit("free_time_router was not found")
        AgentService(db).update_agent(
            router.id,
            user.tenant_id,
            AgentUpdate(system_prompt=ROUTER_PROMPT),
        )
        print(f"Free Time Router prompt updated for {user.email}")


if __name__ == "__main__":
    main()
