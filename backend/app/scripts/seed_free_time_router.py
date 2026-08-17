import argparse

from sqlalchemy import select

from app.core.services.agent_service import AgentService
from app.db.session import SessionLocal
from app.models import Agent, Collection, HttpTool, User
from app.schemas.agent import AgentCreate, AgentUpdate


COLLECTIONS = {
    "movie_series_library": "Personal movie and series catalog, ratings, summaries, genres, runtimes, and mood tags.",
    "recipe_library": "Reusable recipes with ingredients, preparation time, difficulty, portions, and dietary tags.",
    "activity_library": "Outdoor activities, indoor sports, home workouts, group activities, cost, time, and equipment.",
    "book_library": "Book catalog with authors, genres, page counts, summaries, themes, and personal ratings.",
}

AGENTS = {
    "movie_series_agent": """You are a Movie and Series Night specialist.
Help the user choose something to watch based on mood, available time, preferred genres, format, and group size.
Search movie_series_library before recommending catalog titles. Do not invent catalog entries or personal ratings.
Give at most three focused recommendations with a short reason for each. Respect runtime and episode-length limits.
If one essential preference is missing, ask one short clarification question.""",
    "cooking_agent": """You are a practical Cooking specialist.
Recommend meals from the user's ingredients, available time, serving count, dietary needs, and cooking equipment.
Search recipe_library for reusable recipes. Clearly separate required ingredients from optional substitutions.
Give concise numbered steps and never claim an ingredient is available unless the user said so.
If allergy or dietary information is important and missing, ask one short clarification question.""",
    "activity_agent": """You are an Activity and Sports specialist covering outdoor activities, indoor sports, and home exercise.
Use the user's location, weather, time, budget, group size, fitness level, and equipment to make a practical suggestion.
Search activity_library for suitable options and use weather when current conditions affect safety or suitability.
Offer at most three options with duration, equipment, and indoor/outdoor status. Do not provide medical claims.
Ask one short clarification question only when a safe recommendation cannot be made.""",
    "book_agent": """You are a Book Recommendation specialist.
Recommend books based on mood, genre, themes, reading length, difficulty, and fiction/nonfiction preference.
Search book_library before recommending catalog titles and preserve stored author, summary, and rating information.
Give at most three recommendations with a concise reason and avoid spoilers.
Use book_finder only when the user explicitly wants information beyond the personal collection.""",
}

ROUTER_PROMPT = """You are the Free Time Router.
Route watching requests to movie_series_agent, food and recipe requests to cooking_agent, physical activity or sports requests to activity_agent, and reading requests to book_agent.
Never answer a specialist request yourself and never call more than one target agent.

If the user explicitly asks to watch something, cook or eat something, do an activity or sport, or read a book, route immediately to the matching specialist.

If the user asks an open-ended question such as "What should I do?", "I am bored", or "Give me energy", do not choose a category randomly. Return a concise, motivating choice menu with exactly four concrete headings:
1. Watch — a mood-matched movie or series direction
2. Cook — a simple food or cooking direction
3. Move or Explore — an activity, sport, trip, game, photography, or rest direction
4. Read — a book direction

Adapt those four headings to context already supplied by the user, including energy, tiredness, mood, available time, indoor/outdoor preference, company, and budget. For low energy, make the options gentle and easy to start. For high energy, make them active or challenging. The menu should create momentum, not sound like a form.

After the user chooses or clearly favors one option, route the new request to that one specialist. If essential context is still missing, ask at most one natural follow-up question inside the four-option menu."""


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the Free Time Router demo for one user tenant.")
    parser.add_argument("--email", required=True, help="Existing platform user email")
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
        if not user:
            raise SystemExit(f"User not found: {args.email}")
        tenant_id = user.tenant_id

        collections: dict[str, Collection] = {}
        for name, description in COLLECTIONS.items():
            collection = db.scalar(select(Collection).where(
                Collection.tenant_id == tenant_id, Collection.name == name
            ))
            if not collection:
                collection = Collection(tenant_id=tenant_id, name=name, description=description)
                db.add(collection)
                db.flush()
            else:
                collection.description = description
            collections[name] = collection
        db.commit()

        http_tools = {
            tool.name: tool for tool in db.scalars(
                select(HttpTool).where(HttpTool.tenant_id == tenant_id)
            ).all()
        }
        agent_service = AgentService(db)
        specialists: list[Agent] = []
        agent_settings = {
            "movie_series_agent": ("movie_series_library", []),
            "cooking_agent": ("recipe_library", []),
            "activity_agent": ("activity_library", ["weather"]),
            "book_agent": ("book_library", ["book_finder"]),
        }
        for name, prompt in AGENTS.items():
            collection_name, desired_tools = agent_settings[name]
            tool_ids = [http_tools[item].id for item in desired_tools if item in http_tools]
            existing = db.scalar(select(Agent).where(
                Agent.tenant_id == tenant_id, Agent.name == name
            ))
            payload = dict(
                system_prompt=prompt,
                model="anthropic/claude-haiku-4.5",
                temperature=0.2,
                system_tools=["current_datetime"] if name == "activity_agent" else [],
                tool_ids=tool_ids,
                skill_ids=[],
                collection_ids=[collections[collection_name].id],
                managed_agent_ids=[],
                router_target_ids=[],
            )
            if existing:
                specialist = agent_service.update_agent(
                    existing.id, tenant_id, AgentUpdate(agent_type="normal", **payload)
                )
            else:
                specialist = agent_service.create_agent(
                    tenant_id, AgentCreate(name=name, agent_type="normal", **payload)
                )
            specialists.append(specialist)

        existing_router = db.scalar(select(Agent).where(
            Agent.tenant_id == tenant_id, Agent.name == "free_time_router"
        ))
        router_payload = dict(
            system_prompt=ROUTER_PROMPT,
            model="anthropic/claude-haiku-4.5",
            temperature=0.1,
            system_tools=[], tool_ids=[], skill_ids=[], collection_ids=[], managed_agent_ids=[],
            router_target_ids=[agent.id for agent in specialists],
        )
        if existing_router:
            agent_service.update_agent(
                existing_router.id, tenant_id, AgentUpdate(agent_type="router", **router_payload)
            )
        else:
            agent_service.create_agent(
                tenant_id,
                AgentCreate(name="free_time_router", agent_type="router", **router_payload),
            )

        print(f"Free Time Router created for {user.email}")
        print("Collections: " + ", ".join(COLLECTIONS))
        print("Agents: " + ", ".join([*AGENTS, "free_time_router"]))


if __name__ == "__main__":
    main()
