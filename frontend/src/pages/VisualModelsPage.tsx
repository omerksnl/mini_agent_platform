import { useEffect, useRef, useState, type FormEvent } from "react";

import { api, type VisualDatasetSummary, type VisualModel, type VisualModelInput, type VisualPrediction, type VisualTrainingInput, type VisualTrainingRun } from "../api";
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

const defaultTraining: VisualTrainingInput = { epochs: 5, batch_size: 16, validation_split: 0.2, learning_rate: 0.001 };

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
  const [trainingConfig, setTrainingConfig] = useState<VisualTrainingInput>(defaultTraining);
  const [trainingRun, setTrainingRun] = useState<VisualTrainingRun | null>(null);
  const [startingTraining, setStartingTraining] = useState(false);
  const [predictionFile, setPredictionFile] = useState<File | null>(null);
  const [predictionPreview, setPredictionPreview] = useState("");
  const [prediction, setPrediction] = useState<VisualPrediction | null>(null);
  const [predicting, setPredicting] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const predictionInputRef = useRef<HTMLInputElement>(null);
  const cameraVideoRef = useRef<HTMLVideoElement>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const [error, setError] = useState("");

  async function load() {
    setModels(await api.listVisualModels());
  }

  useEffect(() => { void load().catch((err) => setError(err.message)); }, []);

  useEffect(() => {
    if (!trainingRun || !["queued", "running"].includes(trainingRun.status)) return;
    const timer = window.setInterval(() => {
      void api.getVisualTrainingRun(trainingRun.id).then((next) => {
        setTrainingRun(next);
        if (["completed", "failed"].includes(next.status)) void load();
      }).catch((err) => setError(err.message));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [trainingRun?.id, trainingRun?.status]);

  useEffect(() => () => {
    cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
    if (predictionPreview) URL.revokeObjectURL(predictionPreview);
  }, [predictionPreview]);

  useEffect(() => {
    const video = cameraVideoRef.current;
    const stream = cameraStreamRef.current;
    if (!cameraOpen || !video || !stream) return;
    video.srcObject = stream;
    void video.play().catch(() => setCameraError("The camera opened, but live playback could not start."));
    return () => {
      if (video.srcObject === stream) video.srcObject = null;
    };
  }, [cameraOpen]);

  function clearPredictionImage() {
    setPredictionFile(null);
    setPrediction(null);
    if (predictionPreview) URL.revokeObjectURL(predictionPreview);
    setPredictionPreview("");
    if (predictionInputRef.current) predictionInputRef.current.value = "";
  }

  function selectPredictionImage(file: File | null) {
    clearPredictionImage();
    if (!file) return;
    setPredictionFile(file);
    setPredictionPreview(URL.createObjectURL(file));
  }

  function stopCamera() {
    cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
    cameraStreamRef.current = null;
    setCameraOpen(false);
  }

  async function openCamera() {
    setCameraError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      cameraStreamRef.current = stream;
      setCameraOpen(true);
    } catch {
      setCameraError("Camera permission was not granted or no camera is available.");
    }
  }

  function captureCameraImage() {
    const video = cameraVideoRef.current;
    if (!video?.videoWidth || !video.videoHeight) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) return;
      selectPredictionImage(new File([blob], `camera-${Date.now()}.jpg`, { type: "image/jpeg" }));
      stopCamera();
    }, "image/jpeg", 0.92);
  }

  async function runPrediction() {
    if (!editingId || !predictionFile) return;
    setPredicting(true);
    setPrediction(null);
    setError("");
    try {
      setPrediction(await api.predictVisualModel(editingId, predictionFile));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Prediction could not be completed");
    } finally {
      setPredicting(false);
    }
  }

  function reset() {
    setEditingId(null);
    setForm(empty);
    setClassNames("class_a, class_b");
    setDataset(null);
    setDatasetFiles([]);
    setDatasetClass("");
    setDatasetNotice("");
    setTrainingRun(null);
    setTrainingConfig(defaultTraining);
    setDatasetInputKey((value) => value + 1);
    clearPredictionImage();
    stopCamera();
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
    clearPredictionImage();
    stopCamera();
    void api.getVisualDataset(model.id).then(setDataset).catch((err) => setError(err.message));
    void api.getLatestVisualTraining(model.id).then(setTrainingRun).catch((err) => setError(err.message));
    setError("");
  }

  async function startTraining() {
    if (!editingId) return;
    setStartingTraining(true);
    setError("");
    try {
      setTrainingRun(await api.startVisualTraining(editingId, trainingConfig));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Training could not be started");
    } finally {
      setStartingTraining(false);
    }
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
        {!models.length ? <div className="guardrail-empty"><strong>No visual models yet</strong><span>Create your first image-classification configuration.</span></div> : null}
        {models.map((model) => <div className={`visual-model-row ${editingId === model.id ? "selected" : ""}`} key={model.id}>
          <button type="button" className="visual-model-main" onClick={() => edit(model)}><span className="vision-model-icon" aria-hidden="true">◉</span><span><strong>{model.name}</strong><small>{architectureLabels[model.architecture]} · {model.class_names.length} classes · {model.image_width}×{model.image_height}</small></span><b>{model.status}</b></button>
          <button type="button" className="visual-delete-button" aria-label={`Delete ${model.name}`} onClick={() => setDeleteTarget(model)}>×</button>
        </div>)}
      </section>

      <section className="box panel visual-model-editor">
        <form className="stack visual-model-form" onSubmit={save}>
          <header className="visual-editor-header">
            <div><div className="visual-editor-title"><h1>{editingId ? (editingModel?.name || "Edit visual model") : "New visual model"}</h1><span className={`vision-status-badge ${editingModel?.status ?? "new"}`}>{editingModel?.status?.replaceAll("_", " ") ?? "new"}</span></div><p>{editingId ? "Update the model configuration." : "Configure a reusable image classifier."}</p></div>
            <div className="visual-editor-actions"><button className="btn" type="button" onClick={reset}>{editingId ? "Close" : "Clear"}</button></div>
          </header>
          {error ? <div className="error-banner">{error}</div> : null}

          <section className="visual-form-section">
            <div className="visual-section-heading"><div><h2>Basic information</h2><p>Name the model and define the classes it recognizes.</p></div></div>
            <div className="visual-form-grid"><label>Model name<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Dog or cat classifier" required /></label><label>Task type<select value={form.task_type} disabled><option value="image_classification">Image classification</option></select></label></div>
            <label>Description<textarea rows={3} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="Describe the recognition goal and intended use." /></label>
            <label>Classes<textarea rows={2} value={classNames} onChange={(event) => setClassNames(event.target.value)} placeholder="cat, dog, bird" required/><small>Comma-separated; at least two unique classes.</small></label>
          </section>

          <section className="visual-form-section visual-model-setup-card">
            <div className="visual-section-heading"><div><h2>Model setup</h2><p>Choose the architecture and expected image format.</p></div><small>{architectureLabels[form.architecture]} · {form.image_width}×{form.image_height} · {form.channels === 3 ? "RGB" : "Grayscale"}</small></div>
            <fieldset className="vision-architecture-picker"><legend className="sr-only">Architecture</legend>{(["simple_cnn", "mobilenet_v2", "resnet50"] as const).map((architecture) => <label className={form.architecture === architecture ? "selected" : ""} key={architecture}><input type="radio" name="architecture" value={architecture} checked={form.architecture === architecture} onChange={() => setForm({ ...form, architecture, use_pretrained_weights: architecture !== "simple_cnn" })}/><span className="architecture-choice-mark"/><strong>{architectureLabels[architecture]}</strong><small>{architecture === "simple_cnn" ? "Lightweight · from scratch" : architecture === "mobilenet_v2" ? "Efficient · recommended" : "Higher capacity · deeper"}</small></label>)}</fieldset>
            <div className="visual-input-grid"><label>Image width<input className="clean-number-input" type="number" min={32} max={2048} value={form.image_width} onChange={(event) => setForm({ ...form, image_width: Number(event.target.value) })} required /></label><label>Image height<input className="clean-number-input" type="number" min={32} max={2048} value={form.image_height} onChange={(event) => setForm({ ...form, image_height: Number(event.target.value) })} required /></label><label>Color mode<select value={form.channels} onChange={(event) => setForm({ ...form, channels: Number(event.target.value) as 1 | 3 })}><option value={3}>RGB · 3 channels</option><option value={1}>Grayscale · 1 channel</option></select></label></div>
            <label className="visual-pretrained-toggle"><input type="checkbox" checked={form.use_pretrained_weights} disabled={form.architecture === "simple_cnn"} onChange={(event) => setForm({ ...form, use_pretrained_weights: event.target.checked })}/><span><strong>Use pretrained ImageNet weights</strong><small>Start from learned visual features for faster, stronger transfer learning.</small></span></label>
          </section>

          <div className="visual-save-bar"><span>{editingId ? "Your dataset remains unchanged when this configuration is saved." : "Save to add images and start training."}</span><button className="btn btn-primary" type="submit" disabled={saving}>{saving ? "Saving..." : editingId ? "Save changes" : "Create model"}</button></div>
        </form>

        {editingId && dataset ? <details className="agent-config-section visual-config-section visual-dataset-details">
          <summary><span>Image dataset</span><small>{dataset.total_images} images · {dataset.classes.filter((item) => item.image_count > 0).length}/{dataset.classes.length} classes · {dataset.ready_for_training ? "Ready" : "Needs images"}</small></summary>
          <div className="agent-config-content"><section className="visual-dataset-section">
            <div className="panel-head"><div><h2>Image dataset</h2><p className="muted">Stored locally and isolated to this tenant and model.</p></div><span className={`dataset-ready-badge ${dataset.ready_for_training ? "ready" : ""}`}>{dataset.ready_for_training ? "Ready" : "Needs images"}</span></div>
            <div className="dataset-totals"><div><strong>{dataset.total_images}</strong><span>Total images</span></div><div><strong>{formatBytes(dataset.total_bytes)}</strong><span>Stored size</span></div><div><strong>{dataset.classes.filter((item) => item.image_count > 0).length}/{dataset.classes.length}</strong><span>Classes populated</span></div></div>
            <div className="dataset-class-grid">{dataset.classes.map((item) => <div className={item.image_count ? "populated" : ""} key={item.class_name}><strong>{item.class_name}</strong><span>{item.image_count} images</span><small>{formatBytes(item.total_bytes)}</small></div>)}</div>
            <div className="dataset-upload-box">
              <div className="visual-form-grid"><label>Class for image files<select value={datasetClass} onChange={(event) => setDatasetClass(event.target.value)}>{dataset.classes.map((item) => <option key={item.class_name} value={item.class_name}>{item.class_name}</option>)}</select></label><label>Images or class-folder ZIP<span className="file-picker-control"><span>{datasetFiles.length ? `${datasetFiles.length} file${datasetFiles.length === 1 ? "" : "s"} selected` : "No file selected"}</span><b>Choose files</b><input key={datasetInputKey} type="file" multiple accept=".jpg,.jpeg,.png,.webp,.zip,image/jpeg,image/png,image/webp,application/zip" onChange={(event) => setDatasetFiles(Array.from(event.target.files ?? []))}/></span></label></div>
              <p className="muted dataset-upload-help">For ZIP uploads, use folders matching the configured classes, for example <code>cat/</code> and <code>dog/</code>. The class selector is ignored for ZIP files.</p>
              {datasetFiles.length ? <div className="dataset-selection"><span>{datasetFiles.length} file{datasetFiles.length === 1 ? "" : "s"} selected</span><button type="button" onClick={() => { setDatasetFiles([]); setDatasetInputKey((value) => value + 1); }}>Clear selection</button></div> : null}
              {datasetNotice ? <div className="success-note">{datasetNotice}</div> : null}
              <div className="form-actions"><button className="btn" type="button" disabled={!dataset.total_images} onClick={() => setClearDatasetOpen(true)}>Clear dataset</button><button className="btn btn-primary" type="button" disabled={!datasetFiles.length || uploadingDataset} onClick={() => void uploadDataset()}>{uploadingDataset ? "Uploading..." : "Upload dataset"}</button></div>
            </div>
          </section></div>
        </details> : null}

        {editingId && dataset ? <details className="agent-config-section visual-config-section visual-training-details">
          <summary><span>Training</span><small>{trainingRun ? `${trainingRun.status} · ${trainingRun.progress}%` : dataset.ready_for_training ? "Ready to start" : "Dataset not ready"}</small></summary>
          <div className="agent-config-content"><section className="visual-training-section">
            <div className="panel-head"><div><h2>Train model</h2><p className="muted">Runs locally in the background and does not use an LLM or API balance.</p></div><span className={`training-status-badge ${trainingRun?.status ?? "idle"}`}>{trainingRun?.status ?? "Not started"}</span></div>
            <div className="visual-training-grid">
              <label>Epochs<input className="clean-number-input" type="number" min={1} max={100} value={trainingConfig.epochs} disabled={trainingRun?.status === "queued" || trainingRun?.status === "running"} onChange={(event) => setTrainingConfig({ ...trainingConfig, epochs: Number(event.target.value) })}/></label>
              <label>Batch size<input className="clean-number-input" type="number" min={1} max={256} value={trainingConfig.batch_size} disabled={trainingRun?.status === "queued" || trainingRun?.status === "running"} onChange={(event) => setTrainingConfig({ ...trainingConfig, batch_size: Number(event.target.value) })}/></label>
              <label>Validation split<input className="clean-number-input" type="number" min={0.1} max={0.5} step={0.05} value={trainingConfig.validation_split} disabled={trainingRun?.status === "queued" || trainingRun?.status === "running"} onChange={(event) => setTrainingConfig({ ...trainingConfig, validation_split: Number(event.target.value) })}/></label>
              <label>Learning rate<input className="clean-number-input" type="number" min={0.000001} max={0.1} step={0.0001} value={trainingConfig.learning_rate} disabled={trainingRun?.status === "queued" || trainingRun?.status === "running"} onChange={(event) => setTrainingConfig({ ...trainingConfig, learning_rate: Number(event.target.value) })}/></label>
            </div>
            {trainingRun ? <div className="training-progress-card">
              <div className="training-progress-label"><strong>{trainingRun.status === "completed" ? "Training completed" : trainingRun.status === "failed" ? "Training failed" : `Epoch ${trainingRun.current_epoch} of ${trainingRun.epochs}`}</strong><span>{trainingRun.progress}%</span></div>
              <div className="training-progress-track"><span style={{ width: `${trainingRun.progress}%` }}/></div>
              {Object.keys(trainingRun.metrics).length ? <div className="training-metrics">{Object.entries(trainingRun.metrics).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{Number(value).toFixed(4)}</strong></div>)}</div> : null}
              {trainingRun.artifact_path ? <p className="success-note">Saved model artifact: <code>{trainingRun.artifact_path}</code></p> : null}
              {trainingRun.error ? <div className="error-banner">{trainingRun.error}</div> : null}
            </div> : null}
            <div className="form-actions"><button className="btn btn-primary" type="button" disabled={!dataset.ready_for_training || startingTraining || trainingRun?.status === "queued" || trainingRun?.status === "running"} onClick={() => void startTraining()}>{startingTraining ? "Starting..." : trainingRun?.status === "completed" || trainingRun?.status === "failed" ? "Train again" : "Start training"}</button></div>
          </section></div>
        </details> : null}

        {editingId && trainingRun?.status === "completed" ? <details className="agent-config-section visual-config-section visual-prediction-details" open>
          <summary><span>Run model</span><small>{prediction ? `${prediction.predicted_class} · ${(prediction.confidence * 100).toFixed(1)}%` : "Image or camera"}</small></summary>
          <div className="agent-config-content"><section className="visual-prediction-section">
            <div className="panel-head"><div><h2>Test recognition</h2><p className="muted">Use an uploaded image or capture one from this device. Prediction runs locally and does not use API balance.</p></div></div>
            <div className="prediction-source-actions">
              <label className="btn prediction-upload-button">Choose image<input ref={predictionInputRef} type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => selectPredictionImage(event.target.files?.[0] ?? null)}/></label>
              <button className="btn" type="button" onClick={() => void (cameraOpen ? Promise.resolve(stopCamera()) : openCamera())}>{cameraOpen ? "Close camera" : "Use camera"}</button>
            </div>
            {cameraError ? <div className="error-banner">{cameraError}</div> : null}
            {cameraOpen ? <div className="camera-capture-card"><video ref={cameraVideoRef} autoPlay playsInline muted/><button className="btn btn-primary" type="button" onClick={captureCameraImage}>Capture image</button></div> : null}
            {predictionPreview ? <div className="prediction-preview-card"><img src={predictionPreview} alt="Selected prediction input"/><div><strong>{predictionFile?.name}</strong><span>Ready for recognition</span><button type="button" onClick={clearPredictionImage}>Remove image</button></div></div> : null}
            {prediction ? <div className="prediction-result-card"><div className="prediction-result-head"><span>Prediction</span><strong>{prediction.predicted_class}</strong><b>{(prediction.confidence * 100).toFixed(1)}% confidence</b></div><div className="prediction-score-list">{prediction.scores.map((score) => <div key={score.class_name}><span>{score.class_name}</span><div><i style={{ width: `${score.probability * 100}%` }}/></div><strong>{(score.probability * 100).toFixed(1)}%</strong></div>)}</div></div> : null}
            <div className="form-actions"><button className="btn btn-primary" type="button" disabled={!predictionFile || predicting} onClick={() => void runPrediction()}>{predicting ? "Recognizing..." : "Run recognition"}</button></div>
          </section></div>
        </details> : null}
      </section>
    </main>

    {deleteTarget ? <div className="modal-backdrop"><div className="box modal"><h2>Delete visual model?</h2><p><strong>{deleteTarget.name}</strong> and every image in its dataset will be permanently removed.</p><div className="modal-actions"><button className="btn" type="button" onClick={() => setDeleteTarget(null)}>Cancel</button><button className="btn btn-primary" type="button" onClick={async () => { await api.deleteVisualModel(deleteTarget.id); if (editingId === deleteTarget.id) reset(); setDeleteTarget(null); await load(); }}>Delete</button></div></div></div> : null}
    {clearDatasetOpen && editingId ? <div className="modal-backdrop"><div className="box modal"><h2>Clear image dataset?</h2><p>Every uploaded image for this visual model will be permanently removed. The model configuration will remain.</p><div className="modal-actions"><button className="btn" type="button" onClick={() => setClearDatasetOpen(false)}>Cancel</button><button className="btn btn-primary" type="button" onClick={async () => { await api.clearVisualDataset(editingId); setDataset(await api.getVisualDataset(editingId)); setClearDatasetOpen(false); setDatasetNotice("Dataset cleared."); await load(); }}>Clear dataset</button></div></div></div> : null}
  </div>;
}
