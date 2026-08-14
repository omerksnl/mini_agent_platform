import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api, type HttpTool, type Skill, type SkillInput } from "../api";
import { useAuth } from "../AuthContext";

type SkillForm = Omit<SkillInput, "output_schema"> & { outputSchemaText: string };
type PanelMode = "idle" | "create" | "edit";

const emptyForm: SkillForm = {
  name: "",
  description: "",
  instructions: "",
  outputSchemaText: "",
  required_system_tools: [],
  required_tool_ids: [],
  is_active: true,
};

export function SkillsPage() {
  const { me, logout } = useAuth();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [tools, setTools] = useState<HttpTool[]>([]);
  const [form, setForm] = useState<SkillForm>(emptyForm);
  const [mode, setMode] = useState<PanelMode>("idle");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Skill | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [skillList, toolList] = await Promise.all([api.listSkills(), api.listTools()]);
      setSkills(skillList);
      setTools(toolList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load skills");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadData(); }, []);

  function closePanel() {
    setMode("idle"); setEditingId(null); setForm(emptyForm); setError("");
  }

  function startCreate() {
    setMode("create"); setEditingId(null); setForm(emptyForm); setError("");
  }

  function startEdit(skill: Skill) {
    setMode("edit");
    setEditingId(skill.id);
    setForm({
      name: skill.name,
      description: skill.description,
      instructions: skill.instructions,
      outputSchemaText: skill.output_schema ? JSON.stringify(skill.output_schema, null, 2) : "",
      required_system_tools: skill.required_system_tools,
      required_tool_ids: skill.required_tool_ids,
      is_active: skill.is_active,
    });
    setError("");
  }

  function toggleSystemTool(name: string, checked: boolean) {
    setForm({ ...form, required_system_tools: checked
      ? [...form.required_system_tools, name]
      : form.required_system_tools.filter((item) => item !== name) });
  }

  function toggleHttpTool(id: string, checked: boolean) {
    setForm({ ...form, required_tool_ids: checked
      ? [...form.required_tool_ids, id]
      : form.required_tool_ids.filter((item) => item !== id) });
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError("");
    try {
      let outputSchema: Record<string, unknown> | null = null;
      if (form.outputSchemaText.trim()) {
        const parsed: unknown = JSON.parse(form.outputSchemaText);
        if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
          throw new Error("Output schema must be a JSON object");
        }
        outputSchema = parsed as Record<string, unknown>;
      }
      const payload: SkillInput = {
        name: form.name,
        description: form.description,
        instructions: form.instructions,
        output_schema: outputSchema,
        required_system_tools: form.required_system_tools,
        required_tool_ids: form.required_tool_ids,
        is_active: form.is_active,
      };
      if (mode === "edit" && editingId) await api.updateSkill(editingId, payload);
      else await api.createSkill(payload);
      closePanel(); await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Skill could not be saved");
    } finally { setSaving(false); }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    try {
      await api.deleteSkill(pendingDelete.id);
      if (editingId === pendingDelete.id) closePanel();
      setPendingDelete(null); await loadData();
    } catch (err) {
      setPendingDelete(null); setError(err instanceof Error ? err.message : "Skill could not be deleted");
    }
  }

  return (
    <div className="app-shell">
      <header className="box topbar">
        <div><p className="brand">Mini Agent</p><p className="workspace">{me?.tenant_name} · {me?.user.full_name}</p></div>
        <div className="topbar-actions">
          <Link className="btn" to="/">Agents</Link><Link className="btn" to="/chat">Chat</Link>
          <Link className="btn" to="/tools">Tools</Link><button className="btn" onClick={logout}>Sign out</button>
        </div>
      </header>
      <main className="layout">
        <section className="box panel">
          <div className="panel-head"><h1>Skills</h1><button className="btn btn-primary" onClick={startCreate}>New skill</button></div>
          <p className="field-hint">Reusable instructions that can be assigned to agents.</p>
          {loading ? <p>Loading...</p> : null}
          {!loading && skills.length === 0 ? <p>No skills yet.</p> : null}
          <ul className="agent-list">{skills.map((skill) => (
            <li key={skill.id} className={editingId === skill.id ? "active" : ""}>
              <button className="agent-item" onClick={() => startEdit(skill)}><strong>{skill.name}</strong><span className="agent-meta">{skill.is_active ? "Active" : "Inactive"} · {skill.description}</span></button>
              <button className="btn btn-danger" onClick={() => setPendingDelete(skill)}>Delete</button>
            </li>
          ))}</ul>
        </section>
        <section className="box panel">
          {mode === "idle" ? <div className="idle-panel"><p className="idle-title">Reusable expertise</p><p>Create or select a skill.</p></div> : <>
            <div className="panel-accent"><div className="panel-head"><div><h1>{mode === "edit" ? "Edit skill" : "Create skill"}</h1><p>Instructions, output format, and required tools.</p></div><button className="icon-close" onClick={closePanel} aria-label="Close">×</button></div></div>
            {error ? <p className="error">{error}</p> : null}
            <form className="stack" onSubmit={onSubmit}>
              <label>Name<input value={form.name} pattern="[a-z][a-z0-9_]*" onChange={(e) => setForm({ ...form, name: e.target.value })} required /></label>
              <label>Description<textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} required /></label>
              <label>Instructions<textarea rows={12} value={form.instructions} onChange={(e) => setForm({ ...form, instructions: e.target.value })} required /></label>
              <label>Output schema (optional JSON object)<textarea rows={8} placeholder={'{"field": "description"}'} value={form.outputSchemaText} onChange={(e) => setForm({ ...form, outputSchemaText: e.target.value })} /></label>
              <fieldset className="tool-picker"><legend>Required tools</legend><span className="field-hint">Agents must also be granted these tools explicitly.</span>
                {["calculator", "current_datetime", "pdf_to_text", "text_to_pdf"].map((name) => <label className="tool-option" key={name}><input type="checkbox" checked={form.required_system_tools.includes(name)} onChange={(e) => toggleSystemTool(name, e.target.checked)} /><span><strong>{name}</strong><small>System tool</small></span></label>)}
                {tools.map((tool) => <label className="tool-option" key={tool.id}><input type="checkbox" checked={form.required_tool_ids.includes(tool.id)} onChange={(e) => toggleHttpTool(tool.id, e.target.checked)} /><span><strong>{tool.name}</strong><small>HTTP tool</small></span></label>)}
              </fieldset>
              <label className="inline-check"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />Active</label>
              <button className="btn btn-primary btn-large btn-block" disabled={saving}>{saving ? "Saving..." : "Save skill"}</button>
            </form>
          </>}
        </section>
      </main>
      {pendingDelete ? <div className="modal-backdrop" onClick={() => setPendingDelete(null)}><div className="box modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}><h2>Delete skill</h2><p>Remove <strong>{pendingDelete.name}</strong> from all agents?</p><div className="modal-actions"><button className="btn" onClick={() => setPendingDelete(null)}>Cancel</button><button className="btn btn-primary" onClick={() => void confirmDelete()}>Delete</button></div></div></div> : null}
    </div>
  );
}
