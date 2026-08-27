import { useEffect, useState, type FormEvent } from "react";

import { api, type VisualModel, type VisualModelInput } from "../api";
import { AppHeader } from "../components/AppHeader";

const empty: VisualModelInput = {
  name: "",
  description: "",
  task_type: "image_classification",
  architecture: "mobilenet_v2",
  class_names: ["class_a", "class_b"],
  image_width: 224,
  image_height: 224,
  channels: 3,
  use_pretrained_weights: true,
};

const architectureLabels: Record<VisualModelInput["architecture"], string> = {
  simple_cnn: "Simple CNN",
  mobilenet_v2: "MobileNetV2",
  resnet50: "ResNet50",
};

export function VisualModelsPage() {
  const [models, setModels] = useState<VisualModel[]>([]);
  const [form, setForm] = useState<VisualModelInput>(empty);
  const [classNames, setClassNames] = useState("class_a, class_b");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<VisualModel | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setModels(await api.listVisualModels());
  }

  useEffect(() => { void load().catch((err) => setError(err.message)); }, []);

  function reset() {
    setEditingId(null);
    setForm(empty);
    setClassNames("class_a, class_b");
    setError("");
  }

  function edit(model: VisualModel) {
    setEditingId(model.id);
    setForm({
      name: model.name,
      description: model.description,
      task_type: model.task_type,
      architecture: model.architecture,
      class_names: model.class_names,
      image_width: model.image_width,
      image_height: model.image_height,
      channels: model.channels,
      use_pretrained_weights: model.use_pretrained_weights,
    });
    setClassNames(model.class_names.join(", "));
    setError("");
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const classes = classNames.split(",").map((item) => item.trim()).filter(Boolean);
    const payload = { ...form, class_names: classes };
    try {
      if (editingId) await api.updateVisualModel(editingId, payload);
      else await api.createVisualModel(payload);
      reset();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Visual model could not be saved");
    } finally {
      setSaving(false);
    }
  }

  return <div className="app-shell visual-models-shell">
    <AppHeader />
    <main className="layout visual-model-layout">
      <section className="box panel visual-model-list">
        <div className="panel-head"><div><h1>Visual models</h1><p className="muted">Configure reusable image-recognition models.</p></div><button className="btn btn-primary" type="button" onClick={reset}>New model</button></div>
        <div className="visual-feature-note"><strong>Configuration only</strong><span>Dataset upload and training will arrive in the next feature.</span></div>
        {!models.length ? <div className="guardrail-empty"><strong>No visual models yet</strong><span>Create your first image-classification configuration.</span></div> : null}
        {models.map((model) => <div className={`visual-model-row ${editingId === model.id ? "selected" : ""}`} key={model.id}>
          <button type="button" className="visual-model-main" onClick={() => edit(model)}><span className="vision-model-icon" aria-hidden="true">◉</span><span><strong>{model.name}</strong><small>{architectureLabels[model.architecture]} · {model.class_names.length} classes · {model.image_width}×{model.image_height}</small></span><b>{model.status}</b></button>
          <button type="button" className="visual-delete-button" aria-label={`Delete ${model.name}`} onClick={() => setDeleteTarget(model)}>×</button>
        </div>)}
      </section>

      <section className="box panel visual-model-editor">
        <div className="panel-accent"><div className="panel-head"><div><h1>{editingId ? "Edit visual model" : "New visual model"}</h1><p>Define the architecture and expected image input.</p></div><span className="vision-status-badge">Draft</span></div></div>
        {error ? <div className="error-banner">{error}</div> : null}
        <form className="stack visual-model-form" onSubmit={save}>
          <div className="visual-form-grid"><label>Name<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Waste classifier" required /></label><label>Task<select value={form.task_type} disabled><option value="image_classification">Image classification</option></select></label></div>
          <label>Description<textarea rows={3} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="What should this model recognize?" /></label>
          <fieldset className="vision-architecture-picker"><legend>Architecture</legend>{(["simple_cnn", "mobilenet_v2", "resnet50"] as const).map((architecture) => <label className={form.architecture === architecture ? "selected" : ""} key={architecture}><input type="radio" name="architecture" value={architecture} checked={form.architecture === architecture} onChange={() => setForm({ ...form, architecture, use_pretrained_weights: architecture !== "simple_cnn" })}/><strong>{architectureLabels[architecture]}</strong><small>{architecture === "simple_cnn" ? "A lightweight model trained from scratch" : architecture === "mobilenet_v2" ? "Efficient transfer learning for edge use" : "Deeper transfer learning for higher capacity"}</small></label>)}</fieldset>
          <label>Classes<textarea rows={3} value={classNames} onChange={(event) => setClassNames(event.target.value)} placeholder="cat, dog, bird" required/><small>Comma-separated; at least two unique classes.</small></label>
          <div className="visual-input-grid"><label>Image width<input type="number" min={32} max={2048} value={form.image_width} onChange={(event) => setForm({ ...form, image_width: Number(event.target.value) })} required /></label><label>Image height<input type="number" min={32} max={2048} value={form.image_height} onChange={(event) => setForm({ ...form, image_height: Number(event.target.value) })} required /></label><label>Channels<select value={form.channels} onChange={(event) => setForm({ ...form, channels: Number(event.target.value) as 1 | 3 })}><option value={3}>RGB (3)</option><option value={1}>Grayscale (1)</option></select></label></div>
          <label className="checkbox-row"><input type="checkbox" checked={form.use_pretrained_weights} disabled={form.architecture === "simple_cnn"} onChange={(event) => setForm({ ...form, use_pretrained_weights: event.target.checked })}/> Use pretrained ImageNet weights</label>
          <div className="form-actions"><button className="btn" type="button" onClick={reset}>Cancel</button><button className="btn btn-primary btn-large" type="submit" disabled={saving}>{saving ? "Saving..." : editingId ? "Save changes" : "Create visual model"}</button></div>
        </form>
      </section>
    </main>

    {deleteTarget ? <div className="modal-backdrop"><div className="box modal"><h2>Delete visual model?</h2><p><strong>{deleteTarget.name}</strong> will be permanently removed. No dataset or training runs exist in this version.</p><div className="modal-actions"><button className="btn" type="button" onClick={() => setDeleteTarget(null)}>Cancel</button><button className="btn btn-primary" type="button" onClick={async () => { await api.deleteVisualModel(deleteTarget.id); if (editingId === deleteTarget.id) reset(); setDeleteTarget(null); await load(); }}>Delete</button></div></div></div> : null}
  </div>;
}
