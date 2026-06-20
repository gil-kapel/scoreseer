// Display metadata for each estimator. Backend compare() returns the friendly name
// ("Poisson" | "Elo" | "Naive" | "LLM"); match-detail returns the raw model_id.

const ICONS: Record<string, string> = {
  Poisson: "📊",
  Elo: "📈",
  "Dixon-Coles": "📐",
  Market: "💱",
  Naive: "🪙",
  LLM: "🤖",
};

export function estimatorIcon(name: string): string {
  return ICONS[name] ?? "🤖";
}

export function estimatorFromModelId(modelId: string): { icon: string; name: string } {
  if (modelId === "poisson-v1") return { icon: "📊", name: "Poisson" };
  if (modelId === "elo-v1") return { icon: "📈", name: "Elo" };
  if (modelId === "dc-v1") return { icon: "📐", name: "Dixon-Coles" };
  if (modelId === "market-v1") return { icon: "💱", name: "Market" };
  if (modelId === "naive-v1") return { icon: "🪙", name: "Naive" };
  return { icon: "🤖", name: "LLM" };
}
