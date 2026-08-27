import { useEffect, useState, type FormEvent } from "react";
import { api, type Guardrail, type GuardrailInput } from "../api";
import { AppHeader } from "../components/AppHeader";
import { SingleAgentWorkspaceHeader } from "../components/SingleAgentWorkspaceHeader";

const empty: GuardrailInput = {
  name: "", guardrail_type: "pii_redaction", stages: ["output"], action: "redact",
  config: { types: ["email", "phone", "ip_address"] }, is_active: true,
};

export function GuardrailsPage() {
  const [items, setItems] = useState<Guardrail[]>([]);
  const [form, setForm] = useState<GuardrailInput>(empty);
  const [editing, setEditing] = useState<string | null>(null);
  const [values, setValues] = useState("email, phone, ip_address");
  const [error, setError] = useState("");

  const load = async () => setItems(await api.listGuardrails());
  useEffect(() => { void load().catch((e) => setError(e.message)); }, []);

  function setType(type: GuardrailInput["guardrail_type"]) {
    if (type === "pii_redaction") { setForm({ ...form, guardrail_type: type, action: "redact", stages: ["output"] }); setValues("email, phone, ip_address"); }
    else if (type === "blocked_terms") { setForm({ ...form, guardrail_type: type, action: "block", stages: ["input", "output"] }); setValues(""); }
    else { setForm({ ...form, guardrail_type: type, action: "block", stages: ["output"] }); setValues(""); }
  }

  async function save(event: FormEvent) {
    event.preventDefault(); setError("");
    const list = values.split(",").map((v) => v.trim()).filter(Boolean);
    const key = form.guardrail_type === "pii_redaction" ? "types" : form.guardrail_type === "blocked_terms" ? "terms" : "fields";
    const payload = { ...form, config: { [key]: list } };
    try { editing ? await api.updateGuardrail(editing, payload) : await api.createGuardrail(payload); setEditing(null); setForm(empty); setValues("email, phone, ip_address"); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Save failed"); }
  }

  function edit(item: Guardrail) {
    setEditing(item.id); setForm({ name: item.name, guardrail_type: item.guardrail_type, stages: item.stages, action: item.action, config: item.config, is_active: item.is_active });
    const key = item.guardrail_type === "pii_redaction" ? "types" : item.guardrail_type === "blocked_terms" ? "terms" : "fields";
    setValues(((item.config[key] as string[] | undefined) ?? []).join(", "));
  }

  return <div className="app-shell"><AppHeader /><SingleAgentWorkspaceHeader /><main className="layout guardrail-layout">
    <section className="box panel"><div className="panel-head"><div><h1>Guardrails</h1><p className="muted">Reusable deterministic safety policies.</p></div><button className="btn btn-primary" type="button" onClick={() => { setEditing(null); setForm(empty); setValues("email, phone, ip_address"); setError(""); }}>New guardrail</button></div>
      {!items.length ? <div className="guardrail-empty"><strong>No guardrails yet</strong><span>Create a local policy for input, tools, or model output.</span></div> : null}
      {items.map((item) => <div className={`list-row ${editing === item.id ? "selected" : ""}`} key={item.id}>
        <button type="button" className="list-row-main" onClick={() => edit(item)}><strong>{item.name}</strong><small>{item.guardrail_type.replaceAll("_", " ")} · {item.stages.join(", ")}</small></button>
        <button className="btn btn-danger-outline" type="button" onClick={async () => { await api.deleteGuardrail(item.id); if (editing === item.id) setEditing(null); await load(); }}>Delete</button>
      </div>)}
    </section>
    <section className="box panel guardrail-editor"><div className="panel-accent"><div className="panel-head"><div><h1>{editing ? "Edit guardrail" : "New guardrail"}</h1><p>Runs locally without an additional model call.</p></div></div></div>
      {error ? <div className="error-banner">{error}</div> : null}
      <form onSubmit={save} className="stack"><div className="guardrail-form-grid"><label>Name<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></label>
        <label>Type<select value={form.guardrail_type} onChange={(e) => setType(e.target.value as GuardrailInput["guardrail_type"])}><option value="pii_redaction">PII redaction</option><option value="blocked_terms">Blocked terms</option><option value="required_output_fields">Required output fields</option></select></label>
        </div><fieldset className="tool-picker guardrail-stages"><legend>Stages</legend>{(["input", "tool_input", "tool_output", "output"] as const).map((stage) => <label className="tool-option" key={stage}><input type="checkbox" checked={form.stages.includes(stage)} disabled={form.guardrail_type === "required_output_fields" && stage === "output"} onChange={(e) => setForm({ ...form, stages: e.target.checked ? [...form.stages, stage] : form.stages.filter((v) => v !== stage) })}/><span><strong>{stage.replace("_", " ")}</strong><small>{stage === "input" ? "Before the agent runs" : stage === "output" ? "Before the answer is returned" : `Validate ${stage.replace("_", " ")}`}</small></span></label>)}</fieldset>
        <label>{form.guardrail_type === "pii_redaction" ? "PII types" : form.guardrail_type === "blocked_terms" ? "Terms and aliases" : "Required JSON fields"}<textarea rows={4} value={values} onChange={(e) => setValues(e.target.value)} placeholder="Comma-separated values" /></label>
        {form.guardrail_type !== "pii_redaction" ? <label>Action<select value={form.action} onChange={(e) => setForm({ ...form, action: e.target.value as GuardrailInput["action"] })}><option value="block">Block</option><option value="warn">Warn</option>{form.guardrail_type === "blocked_terms" ? <option value="redact">Redact</option> : null}</select></label> : null}
        <label className="checkbox-row"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })}/> Active</label>
        <div className="form-actions"><button className="btn btn-primary btn-large" type="submit">{editing ? "Save changes" : "Create guardrail"}</button></div>
      </form>
    </section>
  </main></div>;
}
