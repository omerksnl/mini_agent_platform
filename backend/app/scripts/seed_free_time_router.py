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
Make a reasonable assumption instead of asking the user to narrow the choice. If the user dislikes a suggestion, recommend a substantially different title without another questionnaire.""",
    "cooking_agent": """You are a practical Cooking specialist.
Recommend meals from the user's ingredients, available time, serving count, dietary needs, and cooking equipment.
Search recipe_library for reusable recipes. Clearly separate required ingredients from optional substitutions.
Give concise numbered steps and never claim an ingredient is available unless the user said so.
Make a reasonable assumption and suggest something immediately. Ask one short question only when allergy or dietary safety genuinely requires it. If rejected, offer a substantially different meal.""",
    "activity_agent": """You are an Activity and Sports specialist covering outdoor activities, indoor sports, home exercise, and games.
Use the user's location, weather, time, budget, group size, fitness level, and equipment to make a practical suggestion.
Search activity_library for suitable options and use weather when current conditions affect safety or suitability.
Use the collection records as the source of truth. Never replace them with generic category ideas or unlisted game titles.
This is an inspiration agent, not a strict filter. Missing preferences and imperfect matches must never block a recommendation.
When the user names a category, search that broad category and choose one collection result without asking questions. For example, any PC/computer game request must search "PC gaming plans League of Legends Valorant indie games" and select one returned plan.
When the request is open-ended, search broadly and pick any one appealing collection plan. Treat time, equipment, energy, and group information as soft preferences unless safety is involved.
Never say that no matching activity exists. If there is no exact match, silently choose the closest or a random alternative and clearly mention any equipment it needs.
Offer at most three separate, immediately usable plans. Never group two different activities or games into one recommendation.
For every recommendation include these collection-backed fields:
- Exact activity or plan name
- Category and indoor/outdoor setting
- Intensity or energy level
- Duration
- Required equipment
- Suitable conditions
- Solo/group suitability
- Estimated cost
- Why it fits the user's current request
- A concrete 2-4 step start-now plan
Omit a field only when the collection record genuinely does not contain it. Keep the output detailed but easy to scan. Do not provide medical claims.
Do not ask preference questionnaires or end by asking the user to choose. Make a reasonable assumption and recommend something now. Ask one short question only when missing information would make the activity unsafe.
If the user dislikes a suggestion, give a clearly different activity or game without asking them to narrow it down.""",
    "book_agent": """You are a Book Recommendation specialist.
Recommend books based on mood, genre, themes, reading length, difficulty, and fiction/nonfiction preference.
Search book_library before recommending catalog titles and preserve stored author, summary, and rating information.
Give at most three recommendations with a concise reason and avoid spoilers.
Use book_finder only when the user explicitly wants information beyond the personal collection.
Make a reasonable assumption instead of asking the user to narrow the choice. If rejected, offer a substantially different book.""",
}

ROUTER_PROMPT = """You are the Free Time Router.
Route watching requests to movie_series_agent, food and recipe requests to cooking_agent, and reading requests to book_agent.
Route every activity and game request to activity_agent. This explicitly includes physical activities, sports, PC games, console games, indie games, online games, party games, card games, okey, and tabletop games.
Never answer a specialist request yourself and never call more than one target agent.
Never claim that a game specialist is unavailable: activity_agent is the game specialist.

If the user explicitly asks to watch something, cook or eat something, do an activity, play a game or sport, or read a book, route immediately to the matching specialist.
For open requests such as "What should I do?", "I am bored", "Give me energy", or "Recommend something", immediately choose exactly one specialist from movie_series_agent, cooking_agent, activity_agent, or book_agent. Treat all four as equally valid sources of free-time inspiration. Do not default to activity_agent.
For a new open-ended request, inspect the recent conversation and avoid the specialist used for the immediately previous recommendation. Rotate categories across repeated general requests; if no prior recommendation exists, choose one randomly. A general "another suggestion" means a different specialist unless the user explicitly asks to stay in the same category.
Do not return a category menu and do not ask the user to narrow it down.
Use context already supplied by the user, including energy, tiredness, mood, available time, indoor/outdoor preference, company, and budget. Low energy should favor gentle options; high energy should favor active options.
You may ask at most one short clarification question only when the first message is impossible to route safely. On the user's next message, route immediately even if some preferences remain unknown.
If the user says they dislike, reject, or want another suggestion, use the conversation context and route immediately. The specialist must provide something substantially different from the previous recommendation. Never respond with "help me narrow it down", a questionnaire, or another choice menu."""


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
            temperature=0.6,
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
