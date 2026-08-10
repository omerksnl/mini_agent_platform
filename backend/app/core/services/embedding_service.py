from openai import OpenAI

from app.config import get_settings


class EmbeddingService:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openrouter_api_key:
            raise RuntimeError("OpenRouter API key is not configured")
        self.settings = settings
        self.client = OpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)

    def embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(
            model=self.settings.embedding_model,
            input=texts,
            dimensions=self.settings.embedding_dimensions,
            extra_body={"input_type": input_type},
        )
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
