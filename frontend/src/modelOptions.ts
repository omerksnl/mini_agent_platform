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
];

export const DEFAULT_MODEL = MODEL_OPTIONS[0].id;
