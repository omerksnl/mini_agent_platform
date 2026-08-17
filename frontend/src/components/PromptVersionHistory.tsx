import { useEffect, useState } from "react";

import { api, type Agent, type AgentPromptVersion } from "../api";

type Props = {
  agentId: string;
  onRestored: (agent: Agent) => void;
};

export function PromptVersionHistory({ agentId, onRestored }: Props) {
  const [versions, setVersions] = useState<AgentPromptVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      setVersions(await api.listAgentPromptVersions(agentId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Prompt history could not be loaded");
    } finally {
      setLoading(false);
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
    <summary><strong>Prompt history</strong><span>Last {versions.length} of 3 versions</span></summary>
    <p className="field-hint">Only prompt changes create versions. Restoring a version makes it the current prompt.</p>
    {loading ? <p>Loading prompt history...</p> : null}
    {error ? <p className="error">{error}</p> : null}
    {!loading ? <div className="prompt-version-list">{versions.map((version) => <details className={`prompt-version${version.is_current ? " current" : ""}`} key={version.id}>
      <summary>
        <span><strong>v{version.version_number}{version.is_current ? " · Current" : ""}</strong><small>{new Date(version.created_at).toLocaleString()}</small></span>
        <span className="prompt-version-preview">{version.system_prompt || "Empty prompt"}</span>
      </summary>
      <pre className="prompt-version-content">{version.system_prompt || "Empty prompt"}</pre>
      {!version.is_current ? <button type="button" className="btn" disabled={restoringId !== null} onClick={() => void restore(version)}>{restoringId === version.id ? "Restoring..." : "Restore v" + version.version_number}</button> : null}
    </details>)}</div> : null}
  </details>;
}
