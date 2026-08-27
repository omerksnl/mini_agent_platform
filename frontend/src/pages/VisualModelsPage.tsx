import { useEffect, useState, type FormEvent } from "react";

import { api, type VisualDatasetSummary, type VisualModel, type VisualModelInput } from "../api";
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
  const [dataset, setDataset] = useState<VisualDatasetSummary | null>(null);
  const [datasetFiles, setDatasetFiles] = useState<File[]>([]);
  const [datasetClass, setDatasetClass] = useState("");
  const [uploadingDataset, setUploadingDataset] = useState(false);
  const [datasetNotice, setDatasetNotice] = useState("");
  const [datasetInputKey, setDatasetInputKey] = useState(0);
  const [clearDatasetOpen, setClearDatasetOpen] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setModels(await api.listVisualModels());
  }

  useEffect(() => { void load().catch((err) => setError(err.message)); }, []);

  function reset() {
    setEditingId(null);
    setForm(empty);
    setClassNames("class_a, class_b");
    setDataset(null);
    setDatasetFiles([]);
    setDatasetClass("");
    setDatasetNotice("");
    setDatasetInputKey((value) => value + 1);
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
    setDatasetClass(model.class_names[0] ?? "");
    setDataset(null);
    setDatasetFiles([]);
    setDatasetInputKey((value) => value + 1);
    setDatasetNotice("");
    void api.getVisualDataset(model.id).then(setDataset).catch((err) => setError(err.message));
    setError("");
  }

  async function uploadDataset() {
    if (!editingId || !datasetFiles.length) return;
    setUploadingDataset(true);
    setError("");
    setDatasetNotice("");
    try {
      const result = await api.uploadVisualDataset(editingId, datasetFiles, datasetClass);
      setDataset(result.summary);
      setDatasetFiles([]);
      setDatasetInputKey((value) => value + 1);
      setDatasetNotice(`${result.added_images} image${result.added_images === 1 ? "" : "s"} added${result.skipped_duplicates ? `; ${result.skipped_duplicates} duplicate${result.skipped_duplicates === 1 ? "" : "s"} skipped` : ""}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dataset could not be uploaded");
    } finally {
      setUploadingDataset(false);
    }
  }

  function formatBytes(value: number) {
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }

  const editingModel = models.find((model) => model.id === editingId);

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
        <div className="visual-feature-note"><strong>Dataset-ready configuration</strong><span>Upload class folders as ZIP or assign multiple images to one class. Training arrives next.</span></div>
        {!models.length ? <div className="guardrail-empty"><strong>No visual models yet</strong><span>Create your first image-classification configuration.</span></div> : null}
        {models.map((model) => <div className={`visual-model-row ${editingId === model.id ? "selected" : ""}`} key={model.id}>
          <button type="button" className="visual-model-main" onClick={() => edit(model)}><span className="vision-model-icon" aria-hidden="true">◉</span><span><strong>{model.name}</strong><small>{architectureLabels[model.architecture]} · {model.class_names.length} classes · {model.image_width}×{model.image_height}</small></span><b>{model.status}</b></button>
          <button type="button" className="visual-delete-button" aria-label={`Delete ${model.name}`} onClick={() => setDeleteTarget(model)}>×</button>
        </div>)}
      </section>

      <section className="box panel visual-model-editor">
        <div className="panel-accent"><div className="panel-head"><div><h1>{editingId ? "Edit visual model" : "New visual model"}</h1><p>Configure the model, then add its labeled image dataset.</p></div><span className="vision-status-badge">{editingModel?.status ?? "new"}</span></div></div>
        {error ? <div className="error-banner">{error}</div> : null}
        <form className="stack visual-model-form" onSubmit={save}>
          <div className="visual-form-grid"><label>Name<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Dog or cat classifier" required /></label><label>Task<select value={form.task_type} disabled><option value="image_classification">Image classification</option></select></label></div>
          <label>Description<textarea rows={3} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="What should this model recognize?" /></label>
          <label>Classes<textarea rows={3} value={classNames} onChange={(event) => setClassNames(event.target.value)} placeholder="cat, dog, bird" required/><small>Comma-separated; at least two unique classes.</small></label>
          <details className="agent-config-section visual-config-section">
            <summary><span>Architecture & image input</span><small>{architectureLabels[form.architecture]} · {form.image_width}×{form.image_height} · {form.channels === 3 ? "RGB" : "Grayscale"}</small></summary>
            <div className="agent-config-content visual-config-content">
              <fieldset className="vision-architecture-picker"><legend>Architecture</legend>{(["simple_cnn", "mobilenet_v2", "resnet50"] as const).map((architecture) => <label className={form.architecture === architecture ? "selected" : ""} key={architecture}><input type="radio" name="architecture" value={architecture} checked={form.architecture === architecture} onChange={() => setForm({ ...form, architecture, use_pretrained_weights: architecture !== "simple_cnn" })}/><strong>{architectureLabels[architecture]}</strong><small>{architecture === "simple_cnn" ? "A lightweight model trained from scratch" : architecture === "mobilenet_v2" ? "Efficient transfer learning for edge use" : "Deeper transfer learning for higher capacity"}</small></label>)}</fieldset>
              <div className="visual-input-grid"><label>Image width<input type="number" min={32} max={2048} value={form.image_width} onChange={(event) => setForm({ ...form, image_width: Number(event.target.value) })} required /></label><label>Image height<input type="number" min={32} max={2048} value={form.image_height} onChange={(event) => setForm({ ...form, image_height: Number(event.target.value) })} required /></label><label>Channels<select value={form.channels} onChange={(event) => setForm({ ...form, channels: Number(event.target.value) as 1 | 3 })}><option value={3}>RGB (3)</option><option value={1}>Grayscale (1)</option></select></label></div>
              <label className="checkbox-row"><input type="checkbox" checked={form.use_pretrained_weights} disabled={form.architecture === "simple_cnn"} onChange={(event) => setForm({ ...form, use_pretrained_weights: event.target.checked })}/> Use pretrained ImageNet weights</label>
            </div>
          </details>
          <div className="form-actions"><button className="btn" type="button" onClick={reset}>Cancel</button><button className="btn btn-primary btn-large" type="submit" disabled={saving}>{saving ? "Saving..." : editingId ? "Save changes" : "Create visual model"}</button></div>
        </form>

        {editingId && dataset ? <details className="agent-config-section visual-config-section visual-dataset-details">
          <summary><span>Image dataset</span><small>{dataset.total_images} images · {dataset.classes.filter((item) => item.image_count > 0).length}/{dataset.classes.length} classes · {dataset.ready_for_training ? "Ready" : "Needs images"}</small></summary>
          <div className="agent-config-content"><section className="visual-dataset-section">
            <div className="panel-head"><div><h2>Image dataset</h2><p className="muted">Stored locally and isolated to this tenant and model.</p></div><span className={`dataset-ready-badge ${dataset.ready_for_training ? "ready" : ""}`}>{dataset.ready_for_training ? "Ready" : "Needs images"}</span></div>
            <div className="dataset-totals"><div><strong>{dataset.total_images}</strong><span>Total images</span></div><div><strong>{formatBytes(dataset.total_bytes)}</strong><span>Stored size</span></div><div><strong>{dataset.classes.filter((item) => item.image_count > 0).length}/{dataset.classes.length}</strong><span>Classes populated</span></div></div>
            <div className="dataset-class-grid">{dataset.classes.map((item) => <div className={item.image_count ? "populated" : ""} key={item.class_name}><strong>{item.class_name}</strong><span>{item.image_count} images</span><small>{formatBytes(item.total_bytes)}</small></div>)}</div>
            <div className="dataset-upload-box">
              <div className="visual-form-grid"><label>Class for image files<select value={datasetClass} onChange={(event) => setDatasetClass(event.target.value)}>{dataset.classes.map((item) => <option key={item.class_name} value={item.class_name}>{item.class_name}</option>)}</select></label><label>Images or class-folder ZIP<input key={datasetInputKey} type="file" multiple accept=".jpg,.jpeg,.png,.webp,.zip,image/jpeg,image/png,image/webp,application/zip" onChange={(event) => setDatasetFiles(Array.from(event.target.files ?? []))}/></label></div>
              <p className="muted dataset-upload-help">For ZIP uploads, use folders matching the configured classes, for example <code>cat/</code> and <code>dog/</code>. The class selector is ignored for ZIP files.</p>
              {datasetFiles.length ? <div className="dataset-selection"><span>{datasetFiles.length} file{datasetFiles.length === 1 ? "" : "s"} selected</span><button type="button" onClick={() => { setDatasetFiles([]); setDatasetInputKey((value) => value + 1); }}>Clear selection</button></div> : null}
              {datasetNotice ? <div className="success-note">{datasetNotice}</div> : null}
              <div className="form-actions"><button className="btn" type="button" disabled={!dataset.total_images} onClick={() => setClearDatasetOpen(true)}>Clear dataset</button><button className="btn btn-primary" type="button" disabled={!datasetFiles.length || uploadingDataset} onClick={() => void uploadDataset()}>{uploadingDataset ? "Uploading..." : "Upload dataset"}</button></div>
            </div>
          </section></div>
        </details> : null}
      </section>
    </main>

    {deleteTarget ? <div className="modal-backdrop"><div className="box modal"><h2>Delete visual model?</h2><p><strong>{deleteTarget.name}</strong> and every image in its dataset will be permanently removed.</p><div className="modal-actions"><button className="btn" type="button" onClick={() => setDeleteTarget(null)}>Cancel</button><button className="btn btn-primary" type="button" onClick={async () => { await api.deleteVisualModel(deleteTarget.id); if (editingId === deleteTarget.id) reset(); setDeleteTarget(null); await load(); }}>Delete</button></div></div></div> : null}
    {clearDatasetOpen && editingId ? <div className="modal-backdrop"><div className="box modal"><h2>Clear image dataset?</h2><p>Every uploaded image for this visual model will be permanently removed. The model configuration will remain.</p><div className="modal-actions"><button className="btn" type="button" onClick={() => setClearDatasetOpen(false)}>Cancel</button><button className="btn btn-primary" type="button" onClick={async () => { await api.clearVisualDataset(editingId); setDataset(await api.getVisualDataset(editingId)); setClearDatasetOpen(false); setDatasetNotice("Dataset cleared."); await load(); }}>Clear dataset</button></div></div></div> : null}
  </div>;
}
