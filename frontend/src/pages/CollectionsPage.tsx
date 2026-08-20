import { useEffect, useState, type FormEvent } from "react";
import { api, type Collection, type CollectionDocument } from "../api";
import { AppHeader } from "../components/AppHeader";

export function CollectionsPage() {
  const [items, setItems] = useState<Collection[]>([]);
  const [selected, setSelected] = useState<Collection | null>(null);
  const [name, setName] = useState(""); const [description, setDescription] = useState("");
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<
    { kind: "collection"; item: Collection } | { kind: "document"; item: CollectionDocument } | null
  >(null);
  async function load(selectId?: string) {
    const list = await api.listCollections(); setItems(list);
    if (selectId || selected) setSelected(list.find((x) => x.id === (selectId ?? selected?.id)) ?? null);
  }
  useEffect(() => { void load().catch((e) => setError(e.message)); }, []);
  async function create(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try { const item = await api.createCollection({ name, description }); setName(""); setDescription(""); await load(item.id); }
    catch (e) { setError(e instanceof Error ? e.message : "Collection could not be created"); }
    finally { setBusy(false); }
  }
  async function upload(file: File) {
    if (!selected) return; setBusy(true); setError("");
    try { await api.uploadCollectionDocument(selected.id, file); await load(selected.id); }
    catch (e) { setError(e instanceof Error ? e.message : "Document could not be indexed"); }
    finally { setBusy(false); }
  }
  async function confirmDelete() {
    if (!pendingDelete) return;
    setBusy(true); setError("");
    try {
      if (pendingDelete.kind === "collection") {
        await api.deleteCollection(pendingDelete.item.id);
        if (selected?.id === pendingDelete.item.id) setSelected(null);
        setPendingDelete(null); await load();
      } else if (selected) {
        await api.deleteCollectionDocument(selected.id, pendingDelete.item.id);
        setPendingDelete(null); await load(selected.id);
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Delete failed"); }
    finally { setBusy(false); }
  }
  return <div className="app-shell">
    <AppHeader />
    <main className="layout"><section className="box panel"><div className="panel-head"><h1>Collections</h1></div><form className="stack compact-form" onSubmit={create}><label>Name<input value={name} onChange={(e) => setName(e.target.value)} required /></label><label>Description<textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></label><button className="btn btn-primary" disabled={busy}>New collection</button></form>
      <ul className="agent-list">{items.map((item) => <li key={item.id} className={selected?.id === item.id ? "active" : ""}><button className="agent-item" onClick={() => setSelected(item)}><strong>{item.name}</strong><span className="agent-meta">{item.documents.length} documents · {item.description}</span></button><button className="btn btn-danger" onClick={() => setPendingDelete({ kind: "collection", item })}>Delete</button></li>)}</ul></section>
      <section className="box panel">{selected ? <><div className="panel-accent"><h1>{selected.name}</h1><p>Upload reusable knowledge. It is chunked and embedded once.</p></div>{error ? <p className="error">{error}</p> : null}<label className="collection-upload btn btn-primary">{busy ? "Indexing..." : "Upload document"}<input type="file" accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown" disabled={busy} onChange={(e) => { const f=e.target.files?.[0]; if(f) void upload(f); e.currentTarget.value=""; }} /></label><p className="field-hint">PDF, TXT or Markdown · maximum 10 MB</p><ul className="document-list">{selected.documents.map((doc) => <li key={doc.id}><div><strong>{doc.original_name}</strong><small>{doc.chunk_count} chunks · {(doc.size_bytes/1024).toFixed(1)} KB</small></div><button className="btn btn-danger" onClick={() => setPendingDelete({ kind: "document", item: doc })}>Delete</button></li>)}</ul>{selected.documents.length===0?<div className="idle-panel"><p className="idle-title">No documents yet</p><p>Upload HR instructions or other reusable knowledge.</p></div>:null}</> : <div className="idle-panel"><p className="idle-title">Reusable knowledge</p><p>Create or select a collection.</p></div>}</section></main>
    {pendingDelete ? <div className="modal-backdrop" onClick={() => !busy && setPendingDelete(null)}><div className="box modal" role="dialog" aria-modal="true" aria-labelledby="collection-delete-title" onClick={(e) => e.stopPropagation()}><h2 id="collection-delete-title">Delete {pendingDelete.kind}</h2><p>{pendingDelete.kind === "collection" ? <>Remove <strong>{pendingDelete.item.name}</strong> and all indexed documents?</> : <>Remove <strong>{pendingDelete.item.original_name}</strong> from this collection?</>}</p><div className="modal-actions"><button className="btn" disabled={busy} onClick={() => setPendingDelete(null)}>Cancel</button><button className="btn btn-primary" disabled={busy} onClick={() => void confirmDelete()}>{busy ? "Deleting..." : "Delete"}</button></div></div></div> : null}
  </div>;
}
