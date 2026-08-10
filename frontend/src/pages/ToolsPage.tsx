import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import {
  api,
  type HttpTool,
  type HttpToolInput,
  type ToolParameter,
} from "../api";
import { useAuth } from "../AuthContext";

const emptyForm: HttpToolInput = {
  name: "",
  description: "",
  url: "https://",
  method: "GET",
  parameters: [],
};

type PanelMode = "idle" | "create" | "edit";

export function ToolsPage() {
  const { me, logout } = useAuth();
  const [tools, setTools] = useState<HttpTool[]>([]);
  const [form, setForm] = useState<HttpToolInput>(emptyForm);
  const [mode, setMode] = useState<PanelMode>("idle");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<HttpTool | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function loadTools() {
    setLoading(true);
    try {
      setTools(await api.listTools());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tools");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadTools();
  }, []);

  function closePanel() {
    setMode("idle");
    setEditingId(null);
    setForm(emptyForm);
    setError("");
  }

  function startCreate() {
    setMode("create");
    setEditingId(null);
    setForm(emptyForm);
    setError("");
  }

  function startEdit(tool: HttpTool) {
    setMode("edit");
    setEditingId(tool.id);
    setForm({
      name: tool.name,
      description: tool.description,
      url: tool.url,
      method: tool.method,
      parameters: tool.parameters,
    });
    setError("");
  }

  function addParameter() {
    const parameter: ToolParameter = {
      name: "",
      type: "string",
      description: "",
      required: true,
    };
    setForm({ ...form, parameters: [...form.parameters, parameter] });
  }

  function updateParameter(index: number, patch: Partial<ToolParameter>) {
    setForm({
      ...form,
      parameters: form.parameters.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...patch } : item
      ),
    });
  }

  function removeParameter(index: number) {
    setForm({ ...form, parameters: form.parameters.filter((_, itemIndex) => itemIndex !== index) });
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      if (mode === "edit" && editingId) {
        await api.updateTool(editingId, form);
      } else {
        await api.createTool(form);
      }
      closePanel();
      await loadTools();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tool could not be saved");
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    try {
      await api.deleteTool(pendingDelete.id);
      if (editingId === pendingDelete.id) closePanel();
      setPendingDelete(null);
      await loadTools();
    } catch (err) {
      setPendingDelete(null);
      setError(err instanceof Error ? err.message : "Tool could not be deleted");
    }
  }

  return (
    <div className="app-shell">
      <header className="box topbar">
        <div>
          <p className="brand">Mini Agent</p>
          <p className="workspace">{me?.tenant_name} · {me?.user.full_name}</p>
        </div>
        <div className="topbar-actions">
          <Link className="btn" to="/">Agents</Link>
          <Link className="btn" to="/chat">Chat</Link>
          <Link className="btn" to="/skills">Skills</Link>
          <button type="button" className="btn" onClick={logout}>Sign out</button>
        </div>
      </header>

      <main className="layout">
        <section className="box panel">
          <div className="panel-head">
            <h1>HTTP tools</h1>
            <button type="button" className="btn btn-primary" onClick={startCreate}>New tool</button>
          </div>
          <p className="field-hint">Calculator and current_datetime are built-in system tools.</p>
          {loading ? <p>Loading...</p> : null}
          {!loading && tools.length === 0 ? <p>No HTTP tools yet.</p> : null}
          <ul className="agent-list">
            {tools.map((tool) => (
              <li key={tool.id} className={editingId === tool.id ? "active" : ""}>
                <button type="button" className="agent-item" onClick={() => startEdit(tool)}>
                  <strong>{tool.name}</strong>
                  <span className="agent-meta">{tool.method} · {tool.url}</span>
                </button>
                <button type="button" className="btn btn-danger" onClick={() => setPendingDelete(tool)}>Delete</button>
              </li>
            ))}
          </ul>
        </section>

        <section className="box panel">
          {mode === "idle" ? (
            <div className="idle-panel">
              <p className="idle-title">Connect a public API</p>
              <p>Create or select an HTTP tool.</p>
            </div>
          ) : (
            <>
              <div className="panel-accent">
                <div className="panel-head">
                  <div>
                    <h1>{mode === "edit" ? "Edit HTTP tool" : "Create HTTP tool"}</h1>
                    <p>Only public HTTP and HTTPS endpoints are allowed.</p>
                  </div>
                  <button type="button" className="icon-close" onClick={closePanel} aria-label="Close">×</button>
                </div>
              </div>
              {error ? <p className="error">{error}</p> : null}
              <form className="stack" onSubmit={onSubmit}>
                <label>Name <input value={form.name} pattern="[a-z][a-z0-9_]*" onChange={(event) => setForm({ ...form, name: event.target.value })} required /></label>
                <label>Description <textarea rows={3} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} required /></label>
                <label>URL <input type="url" value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} required /></label>
                <label>Method
                  <select value={form.method} onChange={(event) => setForm({ ...form, method: event.target.value as "GET" | "POST" })}>
                    <option value="GET">GET</option><option value="POST">POST</option>
                  </select>
                </label>
                <div className="parameter-section">
                  <div className="panel-head"><h2>Parameters</h2><button type="button" className="btn" onClick={addParameter}>Add parameter</button></div>
                  {form.parameters.map((parameter, index) => (
                    <div className="parameter-row" key={index}>
                      <input aria-label="Parameter name" placeholder="name" value={parameter.name} onChange={(event) => updateParameter(index, { name: event.target.value })} required />
                      <select aria-label="Parameter type" value={parameter.type} onChange={(event) => updateParameter(index, { type: event.target.value as ToolParameter["type"] })}>
                        <option value="string">string</option><option value="integer">integer</option><option value="number">number</option><option value="boolean">boolean</option>
                      </select>
                      <input aria-label="Parameter description" placeholder="Description" value={parameter.description} onChange={(event) => updateParameter(index, { description: event.target.value })} />
                      <label className="inline-check"><input type="checkbox" checked={parameter.required} onChange={(event) => updateParameter(index, { required: event.target.checked })} />Required</label>
                      <button type="button" className="btn btn-danger" onClick={() => removeParameter(index)}>Remove</button>
                    </div>
                  ))}
                </div>
                <button className="btn btn-primary btn-large btn-block" disabled={saving}>{saving ? "Saving..." : "Save tool"}</button>
              </form>
            </>
          )}
        </section>
      </main>

      {pendingDelete ? (
        <div className="modal-backdrop" onClick={() => setPendingDelete(null)}>
          <div className="box modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <h2>Delete tool</h2><p>Remove <strong>{pendingDelete.name}</strong> from all agents?</p>
            <div className="modal-actions"><button className="btn" onClick={() => setPendingDelete(null)}>Cancel</button><button className="btn btn-primary" onClick={() => void confirmDelete()}>Delete</button></div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
