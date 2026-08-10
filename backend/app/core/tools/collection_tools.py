from uuid import UUID

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.services.collection_service import CollectionService
from app.models import Agent

class CollectionSearchInput(BaseModel):
    query: str = Field(min_length=2, description="A focused semantic search query")

def build_collection_search_tool(db: Session, agent: Agent) -> StructuredTool:
    collection_ids: list[UUID] = [item.id for item in agent.collections]

    def search(query: str) -> str:
        results = CollectionService(db).search(agent.tenant_id, collection_ids, query)
        if not results:
            return "No relevant information was found in the assigned collections."
        blocks = []
        for chunk, score in results:
            source = chunk.document.original_name
            location = f", page {chunk.page_number}" if chunk.page_number else ""
            blocks.append(f"[Source: {source}{location}; relevance={score:.3f}]\n{chunk.content}")
        return "\n\n---\n\n".join(blocks)

    return StructuredTool.from_function(
        func=search,
        name="collection_search",
        description="Search the agent's assigned knowledge collections. One focused call normally returns all relevant chunks, so do not repeat the same search. Cite source filenames and page numbers from the result.",
        args_schema=CollectionSearchInput,
    )
