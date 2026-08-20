import { useEffect, useRef, useState } from "react";

import { api, type Agent, type AgentPromptVersion } from "../api";

type Props = {
  agentId: string;
  currentPrompt: string;
  onRestored: (agent: Agent) => void;
  onDraftCreated: (prompt: string) => void;
};

export function PromptVersionHistory({ agentId, currentPrompt, onRestored, onDraftCreated }: Props) {
  const [versions, setVersions] = useState<AgentPromptVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [evaluating, setEvaluating] = useState(false);
  const [improving, setImproving] = useState(false);
  const [lastCost, setLastCost] = useState(0);
  const [rationale, setRationale] = useState<string[]>([]);
  const evaluationAttemptRef = useRef<string | null>(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const loaded = await api.listAgentPromptVersions(agentId);
      setVersions(loaded);
      if (loaded.some((version) => !version.evaluation) && evaluationAttemptRef.current !== agentId) {
        evaluationAttemptRef.current = agentId;
        setEvaluating(true);
        const evaluated = await api.evaluateAgentPromptVersions(agentId);
        setVersions(evaluated.versions);
        setLastCost(evaluated.api_cost_usd);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Prompt history could not be loaded");
    } finally {
      setEvaluating(false);
      setLoading(false);
    }
  }

  async function createDraft() {
    setImproving(true);
    setError("");
    try {
      const result = await api.improveAgentPrompt(agentId, currentPrompt);
      onDraftCreated(result.improved_prompt);
      setRationale(result.rationale);
      setLastCost(result.api_cost_usd);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Prompt draft could not be created");
    } finally {
      setImproving(false);
    }
  }

  useEffect(() => {
    void load();
  }, [agentId]);

  async function restore(version: AgentPromptVersion) {
    setRestoringId(version.id);
    setError("");
    try {
      const agent = await api.restoreAgentPromptVersion(agentId, version.id);
      onRestored(agent);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Prompt version could not be restored");
    } finally {
      setRestoringId(null);
    }
  }

  return <details className="prompt-history">
    <summary><strong>Prompt history & evaluation</strong><span>Last {versions.length} of 3 versions</span></summary>
    <p className="field-hint">Only prompt changes create versions. Restoring a version makes it the current prompt.</p>
    <div className="prompt-ai-actions"><button type="button" className="btn btn-primary" disabled={loading || evaluating || improving} onClick={() => void createDraft()}>{improving ? "Creating draft..." : "Create with AI"}</button><span className="field-hint">Creates a draft only. Save the agent to accept it.</span></div>
    {loading ? <p>{evaluating ? "Evaluating prompt versions..." : "Loading prompt history..."}</p> : null}
    {error ? <p className="error">{error}</p> : null}
    {rationale.length ? <div className="prompt-ai-rationale"><strong>Draft improvements</strong><ul>{rationale.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
    {lastCost > 0 ? <p className="field-hint">Last AI operation cost: ${lastCost.toFixed(6)}</p> : null}
    {!loading ? <div className="prompt-version-list">{versions.map((version) => <details className={`prompt-version${version.is_current ? " current" : ""}`} key={version.id}>
      <summary>
        <span><strong>v{version.version_number}{version.is_current ? " · Current" : ""}</strong><small>{new Date(version.created_at).toLocaleString()}</small></span>
        {version.evaluation ? <span className="prompt-version-inline-score">{version.evaluation.score ?? Math.round((version.evaluation.overall ?? 0) / 10)} / 10</span> : <span className="prompt-version-inline-score pending">Not scored</span>}
      </summary>
      <pre className="prompt-version-content">{version.system_prompt || "Empty prompt"}</pre>
      {!version.is_current ? <button type="button" className="btn" disabled={restoringId !== null} onClick={() => void restore(version)}>{restoringId === version.id ? "Restoring..." : "Restore v" + version.version_number}</button> : null}
    </details>)}</div> : null}
  </details>;
}
