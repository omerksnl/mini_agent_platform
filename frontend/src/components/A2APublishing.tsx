import { useEffect, useState } from "react";

import { api, type A2APublishResponse, type Agent } from "../api";


type Props = {
  agent: Agent;
  onChanged: () => void | Promise<void>;
};


export function A2APublishing({ agent, onChanged }: Props) {
  const [description, setDescription] = useState(agent.a2a_description);
  const [credentials, setCredentials] = useState<A2APublishResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");

  useEffect(() => {
    setDescription(agent.a2a_description);
    setCredentials(null);
    setError("");
  }, [agent.id, agent.a2a_description]);

  const endpoint = credentials?.endpoint_url ?? `${window.location.origin}/a2a/agents/${agent.id}`;
  const cardUrl = credentials?.agent_card_url ?? `${endpoint}/.well-known/agent-card.json`;

  async function publish() {
    setBusy(true);
    setError("");
    try {
      const result = await api.publishAgentA2A(agent.id, description);
      setCredentials(result);
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "A2A publishing failed");
    } finally {
      setBusy(false);
    }
  }

  async function unpublish() {
    setBusy(true);
    setError("");
    try {
      await api.unpublishAgentA2A(agent.id);
      setCredentials(null);
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "A2A unpublishing failed");
    } finally {
      setBusy(false);
    }
  }

  async function copy(value: string, label: string) {
    await navigator.clipboard.writeText(value);
    setCopied(label);
    window.setTimeout(() => setCopied(""), 1400);
  }

  return <fieldset className="a2a-publishing">
    <legend><span>A2A publishing</span><span className={`a2a-status ${agent.a2a_enabled ? "published" : "private"}`}>{agent.a2a_enabled ? "Published" : "Private"}</span></legend>
    <p className="field-hint">Expose this agent to other A2A-compatible agents without revealing its system prompt or tenant data.</p>
    <label>
      Public capability description
      <textarea rows={3} maxLength={2000} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Describe what another agent may delegate to this agent." />
    </label>
    {agent.a2a_enabled ? <div className="a2a-endpoints">
      <div><span>Agent Card</span><code>{cardUrl}</code><button type="button" className="btn" onClick={() => void copy(cardUrl, "card")}>{copied === "card" ? "Copied" : "Copy"}</button></div>
      <div><span>Task endpoint</span><code>{endpoint}</code><button type="button" className="btn" onClick={() => void copy(endpoint, "endpoint")}>{copied === "endpoint" ? "Copied" : "Copy"}</button></div>
    </div> : null}
    {credentials ? <div className="a2a-secret">
      <strong>Copy this API key now</strong>
      <p>For security, it will not be shown again.</p>
      <div><code>{credentials.api_key}</code><button type="button" className="btn btn-primary" onClick={() => void copy(credentials.api_key, "key")}>{copied === "key" ? "Copied" : "Copy key"}</button></div>
    </div> : null}
    {error ? <p className="error">{error}</p> : null}
    <div className="a2a-actions">
      {agent.a2a_enabled ? <>
        <button type="button" className="btn" disabled={busy} onClick={() => void publish()}>{busy ? "Working..." : "Rotate API key"}</button>
        <button type="button" className="btn btn-danger" disabled={busy} onClick={() => void unpublish()}>Unpublish</button>
      </> : <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void publish()}>{busy ? "Publishing..." : "Publish as A2A agent"}</button>}
    </div>
  </fieldset>;
}
