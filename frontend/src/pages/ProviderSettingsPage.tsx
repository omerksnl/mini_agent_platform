import { useEffect, useState, type FormEvent } from "react";

import { api, type ProviderCredential, type ProviderSettings } from "../api";
import { AppHeader } from "../components/AppHeader";

export function ProviderSettingsPage() {
  const [settings, setSettings] = useState<ProviderSettings | null>(null);
  const [provider, setProvider] = useState<"openrouter" | "openai">("openrouter");
  const [name, setName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [credentials, setCredentials] = useState<ProviderCredential[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function load() {
    const [value, saved] = await Promise.all([api.getProviderSettings(), api.listProviderCredentials()]);
    setSettings(value);
    setCredentials(saved);
    setProvider(value.provider);
  }

  useEffect(() => { void load().catch((err) => setError(err.message)); }, []);

  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError(""); setMessage("");
    try {
      const value = await api.updateProviderSettings(name, provider, apiKey);
      setSettings(value); setName(""); setApiKey(""); setMessage("Personal API key saved securely."); await load();
    } catch (err) { setError(err instanceof Error ? err.message : "Could not save API key"); }
    finally { setSaving(false); }
  }

  async function test() {
    setError(""); setMessage("");
    try { const result = await api.testProviderSettings(); setMessage(`${result.provider === "openai" ? "OpenAI" : "OpenRouter"} connection is working.`); }
    catch (err) { setError(err instanceof Error ? err.message : "Connection test failed"); }
  }

  async function clear() {
    await api.clearProviderSettings(); setApiKey(""); setMessage("Using the platform default provider again."); await load();
  }

  async function activate(id: string) { await api.activateProviderCredential(id); setMessage("Active API key changed."); await load(); }
  async function remove(id: string) { await api.deleteProviderCredential(id); setMessage("Saved API key removed."); await load(); }

  return <main className="page-shell"><AppHeader />
    <section className="box provider-settings-card">
      <div><h1>AI provider</h1><p>Use the platform default or bring your own OpenRouter/OpenAI API key.</p></div>
      {error ? <p className="error">{error}</p> : null}{message ? <p className="success-note">{message}</p> : null}
      <div className="provider-status"><span className="status-pill">{settings?.source === "personal" ? "Personal key" : "Platform default"}</span><strong>{settings?.provider === "openai" ? "OpenAI" : "OpenRouter"}</strong><small>{settings?.masked_key ?? "No personal key stored"}</small></div>
      <form onSubmit={save} className="provider-form">
        <label>Name<input required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} placeholder="Personal OpenAI" /></label>
        <label>Provider<select value={provider} onChange={(event) => setProvider(event.target.value as "openrouter" | "openai")}><option value="openrouter">OpenRouter</option><option value="openai">OpenAI (direct)</option></select></label>
        <label>API key<input type="password" autoComplete="off" required minLength={16} value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={provider === "openai" ? "sk-..." : "sk-or-v1-..."} /></label>
        <p className="field-help">The key is encrypted before it is stored and is never returned by the API.</p>
        <div className="form-actions"><button className="btn btn-primary" disabled={saving}>{saving ? "Saving..." : "Save personal key"}</button><button className="btn" type="button" onClick={() => void test()}>Test connection</button>{settings?.has_personal_key ? <button className="btn" type="button" onClick={() => void clear()}>Use platform default</button> : null}</div>
      </form>
      <div className="saved-provider-section"><h2>Saved API keys</h2>{credentials.length ? <ul className="saved-provider-list">{credentials.map((item) => <li key={item.id} className={item.is_active ? "active" : ""}><div><strong>{item.name}</strong><span>{item.provider === "openai" ? "OpenAI" : "OpenRouter"}</span><small>{item.masked_key}</small></div><div>{item.is_active ? <span className="status-pill">Active</span> : <button className="btn" type="button" onClick={() => void activate(item.id)}>Use</button>}<button className="btn" type="button" onClick={() => void remove(item.id)}>Delete</button></div></li>)}</ul> : <p className="field-help">No saved personal API keys yet.</p>}</div>
      <p className="field-help">Assign a saved profile from an agent, router, or supervisor edit screen. Direct OpenAI profiles require an OpenAI model; OpenRouter profiles can run models from multiple providers.</p>
    </section>
  </main>;
}
