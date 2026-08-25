export type ModelOption = {
  id: string;
  label: string;
  provider: string;
};

export const MODEL_OPTIONS: ModelOption[] = [
  {
    id: "anthropic/claude-haiku-4.5",
    label: "Claude Haiku 4.5",
    provider: "Anthropic",
  },
  {
    id: "openai/gpt-4o-mini",
    label: "GPT-4o mini",
    provider: "OpenRouter",
  },
  {
    id: "gpt-4o-mini",
    label: "GPT-4o mini",
    provider: "OpenAI",
  },
  {
    id: "gpt-4.1-mini",
    label: "GPT-4.1 mini",
    provider: "OpenAI",
  },
  {
    id: "gpt-4.1",
    label: "GPT-4.1",
    provider: "OpenAI",
  },
];

export const DEFAULT_MODEL = MODEL_OPTIONS[0].id;
