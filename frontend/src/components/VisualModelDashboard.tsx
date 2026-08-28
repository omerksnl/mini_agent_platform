import ReactECharts from "echarts-for-react";
import { useEffect, useMemo, useState } from "react";

import { api, type VisualModel, type VisualModelEvaluation, type VisualTrainingRun } from "../api";

type Props = { models: VisualModel[] };

const red = "#e15357";
const green = "#45a77b";
const blue = "#6681a3";

function percent(value?: number) {
  return value == null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function hasEvaluation(value: VisualTrainingRun["evaluation"]): value is VisualModelEvaluation {
  return Boolean(value && "summary" in value && "classes" in value);
}

const chartBase = {
  animationDuration: 700,
  animationEasing: "cubicOut" as const,
  textStyle: { fontFamily: "inherit", color: "#53575f" },
  tooltip: { trigger: "axis" as const, backgroundColor: "#fff", borderColor: "#ddd", textStyle: { color: "#30343b" } },
  legend: { top: 4, itemGap: 24, itemWidth: 22, itemHeight: 10 },
  grid: { left: 18, right: 22, top: 54, bottom: 20, containLabel: true },
};

const categoryAxis = (data: string[]) => ({
  type: "category" as const,
  data,
  boundaryGap: data.length === 1,
  axisLabel: { margin: 14, hideOverlap: true },
  axisTick: { alignWithLabel: true },
});

export function VisualModelDashboard({ models }: Props) {
  const [modelId, setModelId] = useState(models[0]?.id ?? "");
  const [versions, setVersions] = useState<VisualTrainingRun[]>([]);
  const [runId, setRunId] = useState("");
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!models.some((model) => model.id === modelId)) setModelId(models[0]?.id ?? "");
  }, [models, modelId]);

  useEffect(() => {
    if (!modelId) { setVersions([]); setRunId(""); return; }
    void api.listVisualModelVersions(modelId).then((items) => {
      setVersions(items);
      const preferred = items.find((item) => item.is_active) ?? items[0];
      setRunId(preferred?.id ?? "");
    }).catch((err) => setError(err.message));
  }, [modelId]);

  const selected = versions.find((version) => version.id === runId);
  const evaluation = selected && hasEvaluation(selected.evaluation) ? selected.evaluation : null;
  const epochs = useMemo(() => {
    const length = Math.max(...Object.values(selected?.training_history ?? {}).map((values) => values.length), 0);
    return Array.from({ length }, (_, index) => `Epoch ${index + 1}`);
  }, [selected]);

  async function evaluate() {
    if (!selected || !modelId) return;
    setEvaluating(true); setError("");
    try {
      const updated = await api.evaluateVisualModelVersion(modelId, selected.id);
      setVersions((items) => items.map((item) => item.id === updated.id ? updated : item));
    } catch (err) { setError(err instanceof Error ? err.message : "Evaluation failed"); }
    finally { setEvaluating(false); }
  }

  if (!models.length) return <section className="box visual-dashboard-empty"><h2>No visual models yet</h2><p>Create and train a model to unlock its evaluation dashboard.</p></section>;

  const history = selected?.training_history ?? {};
  const retainedEpochCount = epochs.length;
  const expectedEpochCount = selected?.epochs ?? 0;
  const incompleteHistory = retainedEpochCount > 0 && retainedEpochCount < expectedEpochCount;
  return <section className="visual-dashboard">
    <header className="box visual-dashboard-header">
      <div><h1>Evaluation dashboard</h1><p>Inspect training behavior and validation quality for every retained version.</p></div>
      <div className="visual-dashboard-selectors">
        <label>Model<select value={modelId} onChange={(event) => setModelId(event.target.value)}>{models.map((model) => <option value={model.id} key={model.id}>{model.name}</option>)}</select></label>
        <label>Version<select value={runId} onChange={(event) => setRunId(event.target.value)}>{versions.map((version) => <option value={version.id} key={version.id}>Version {version.version_number}{version.is_active ? " · Active" : ""}</option>)}</select></label>
      </div>
    </header>
    {error ? <div className="error-banner">{error}</div> : null}
    {!selected ? <div className="box visual-dashboard-empty"><h2>No trained versions</h2><p>Train this model once to create its first dashboard.</p></div> : !evaluation ? <div className="box visual-dashboard-empty"><h2>This older version has not been evaluated</h2><p>Run one local validation pass. This uses no LLM and no API balance.</p><button className="btn btn-primary" type="button" onClick={() => void evaluate()} disabled={evaluating}>{evaluating ? "Evaluating..." : "Evaluate version"}</button></div> : <>
      <div className="visual-kpi-grid">
        {[ ["Accuracy", evaluation.summary.accuracy], ["Balanced accuracy", evaluation.summary.balanced_accuracy], ["Macro precision", evaluation.summary.macro_precision], ["Macro recall", evaluation.summary.macro_recall], ["Macro F1", evaluation.summary.macro_f1] ].map(([label, value]) => <article className="box visual-kpi" key={String(label)}><span>{label}</span><strong>{percent(Number(value))}</strong><small>{evaluation.sample_count} validation images</small></article>)}
      </div>
      {incompleteHistory ? <div className="visual-history-notice">This version was created before full epoch tracking was enabled. {retainedEpochCount} of {expectedEpochCount} epochs can be shown; retraining will record every epoch.</div> : null}
      <div className="visual-chart-grid">
        <article className="box visual-chart-card"><h2>Accuracy by epoch</h2>{epochs.length ? <ReactECharts option={{ ...chartBase, xAxis: categoryAxis(epochs), yAxis: { type: "value", min: 0, max: 1 }, series: [{ name: "Training", type: "line", smooth: epochs.length > 2, data: history.accuracy ?? [], color: red, symbolSize: 8, areaStyle: { opacity: .08 } }, { name: "Validation", type: "line", smooth: epochs.length > 2, data: history.val_accuracy ?? [], color: green, symbolSize: 8 }] }} /> : <p className="chart-unavailable">Training curves were not retained for this older version.</p>}</article>
        <article className="box visual-chart-card"><h2>Loss by epoch</h2>{epochs.length ? <ReactECharts option={{ ...chartBase, xAxis: categoryAxis(epochs), yAxis: { type: "value" }, series: [{ name: "Training", type: "line", smooth: epochs.length > 2, data: history.loss ?? [], color: red, symbolSize: 8 }, { name: "Validation", type: "line", smooth: epochs.length > 2, data: history.val_loss ?? [], color: blue, symbolSize: 8 }] }} /> : <p className="chart-unavailable">Training curves were not retained for this older version.</p>}</article>
        <article className="box visual-chart-card"><h2>Confusion matrix</h2><ReactECharts option={{ animationDuration: 700, tooltip: { position: "top" }, grid: { left: 80, right: 30, top: 20, bottom: 65 }, xAxis: { type: "category", name: "Predicted", data: evaluation.classes.map((item) => item.class_name), splitArea: { show: true } }, yAxis: { type: "category", name: "Actual", data: evaluation.classes.map((item) => item.class_name), splitArea: { show: true } }, visualMap: { min: 0, max: Math.max(...evaluation.confusion_matrix.flat(), 1), calculable: false, orient: "horizontal", left: "center", bottom: 0, inRange: { color: ["#fff4f4", "#efa3a5", red] } }, series: [{ type: "heatmap", label: { show: true }, data: evaluation.confusion_matrix.flatMap((row, y) => row.map((value, x) => [x, y, value])) }] }} /></article>
        <article className="box visual-chart-card"><h2>Per-class performance</h2><ReactECharts option={{ ...chartBase, legend: {}, xAxis: { type: "category", data: evaluation.classes.map((item) => item.class_name) }, yAxis: { type: "value", min: 0, max: 1 }, series: [{ name: "Precision", type: "bar", data: evaluation.classes.map((item) => item.precision), color: red }, { name: "Recall", type: "bar", data: evaluation.classes.map((item) => item.recall), color: blue }, { name: "F1", type: "bar", data: evaluation.classes.map((item) => item.f1), color: green }] }} /></article>
        <article className="box visual-chart-card"><h2>Confidence distribution</h2><ReactECharts option={{ ...chartBase, xAxis: { type: "category", data: evaluation.confidence_histogram.labels }, yAxis: { type: "value", minInterval: 1 }, series: [{ type: "bar", data: evaluation.confidence_histogram.counts, color: green, barMaxWidth: 42 }] }} /></article>
        <article className="box visual-chart-card"><h2>Recent version comparison</h2><ReactECharts option={{ ...chartBase, xAxis: categoryAxis(versions.map((item) => `V${item.version_number}`).reverse()), yAxis: { type: "value", min: 0, max: 1 }, series: [{ name: "Validation accuracy", type: "bar", data: versions.map((item) => item.metrics.val_accuracy ?? null).reverse(), color: red, barMaxWidth: 74 }, { name: "Macro F1", type: "line", data: versions.map((item) => hasEvaluation(item.evaluation) ? item.evaluation.summary.macro_f1 : null).reverse(), color: green, symbolSize: 9 }] }} /></article>
      </div>
    </>}
  </section>;
}
