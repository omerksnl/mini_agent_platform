import { useState, type FormEvent } from "react";

import { api } from "../api";

type Props = { targetType: "message" | "workflow_run"; targetId: string };

export function HumanFeedback({ targetType, targetId }: Props) {
  const [open, setOpen] = useState(false);
  const [score, setScore] = useState(0);
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!score) return;
    setSaving(true); setError("");
    try {
      await api.submitHumanFeedback({ target_type: targetType, target_id: targetId, score, comment });
      setSubmitted(true); setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Feedback could not be submitted");
    } finally { setSaving(false); }
  }

  if (submitted && !open) {
    return <div className="human-feedback compact"><span>Feedback sent · {score}/5</span><button type="button" onClick={() => setOpen(true)}>Edit</button></div>;
  }
  if (!open) {
    return <button type="button" className="feedback-open" onClick={() => setOpen(true)}>Rate this response</button>;
  }
  return <form className="human-feedback" onSubmit={submit}>
    <div className="feedback-head"><strong>Human feedback</strong><button type="button" onClick={() => setOpen(false)}>×</button></div>
    <div className="feedback-scores" aria-label="Score from 1 to 5">
      {[1, 2, 3, 4, 5].map((value) => <button type="button" className={score === value ? "active" : ""} onClick={() => setScore(value)} key={value} aria-label={`${value} out of 5`}>{value}</button>)}
    </div>
    <textarea rows={2} maxLength={1000} value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Optional note: what worked or what should improve?" />
    {error ? <small className="feedback-error">{error}</small> : null}
    <button className="btn btn-primary btn-compact" disabled={!score || saving}>{saving ? "Sending..." : submitted ? "Update feedback" : "Send feedback"}</button>
  </form>;
}
