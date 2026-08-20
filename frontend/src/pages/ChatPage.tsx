import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent, type MouseEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api, type Agent, type Attachment, type Conversation, type Message } from "../api";
import { HumanFeedback } from "../components/HumanFeedback";
import { AppHeader } from "../components/AppHeader";

export function ChatPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("New conversation");
  const [agentId, setAgentId] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [processingPdf, setProcessingPdf] = useState(false);
  const [error, setError] = useState("");
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const messageThreadRef = useRef<HTMLDivElement | null>(null);
  const draft = selected ? drafts[selected.id] ?? "" : "";

  function setCurrentDraft(value: string) {
    if (!selected) return;
    setDrafts((current) => ({ ...current, [selected.id]: value }));
  }

  async function handleMarkdownLink(event: MouseEvent<HTMLAnchorElement>, href?: string) {
    if (!href?.match(/^\/api\/generated-files\/[0-9a-f-]+\/download$/i)) return;
    event.preventDefault();
    const filename = event.currentTarget.textContent?.trim() || "document.pdf";
    try {
      await api.downloadGeneratedFile(href, filename);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Generated PDF could not be downloaded");
    }
  }

  function scrollThreadToBottom() {
    const thread = messageThreadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [agentList, conversationList] = await Promise.all([
          api.listAgents(),
          api.listConversations(),
        ]);
        setAgents(agentList);
        setAgentId(agentList[0]?.id ?? "");
        setConversations(conversationList);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load chat");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  useLayoutEffect(() => {
    scrollThreadToBottom();
    const frame = window.requestAnimationFrame(scrollThreadToBottom);
    return () => window.cancelAnimationFrame(frame);
  }, [messages, sending, loadingMessages, selected?.id]);

  useLayoutEffect(() => {
    const thread = messageThreadRef.current;
    if (!thread || !selected) return;

    const keepAtBottom = () => {
      thread.scrollTop = thread.scrollHeight;
    };
    const mutationObserver = new MutationObserver(keepAtBottom);
    const resizeObserver = new ResizeObserver(keepAtBottom);
    mutationObserver.observe(thread, { childList: true, subtree: true, characterData: true });
    resizeObserver.observe(thread);
    for (const child of Array.from(thread.children)) resizeObserver.observe(child);
    keepAtBottom();

    return () => {
      mutationObserver.disconnect();
      resizeObserver.disconnect();
    };
  }, [selected?.id]);

  async function selectConversation(conversation: Conversation) {
    setSelected(conversation);
    setPendingFile(null);
    setCreating(false);
    setLoadingMessages(true);
    setError("");
    try {
      setMessages(await api.listMessages(conversation.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load messages");
    } finally {
      setLoadingMessages(false);
    }
  }

  function startCreate() {
    setSelected(null);
    setMessages([]);
    setPendingFile(null);
    setCreating(true);
    setTitle("New conversation");
    setAgentId(agents[0]?.id ?? "");
    setError("");
  }

  async function createConversation(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const conversation = await api.createConversation({ agent_id: agentId, title });
      setConversations((current) => [conversation, ...current]);
      await selectConversation(conversation);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create conversation");
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!selected || (!content && !pendingFile) || sending) return;

    const temporaryId = `temporary-${Date.now()}`;
    setCurrentDraft("");
    const fileToUpload = pendingFile;
    setProcessingPdf(Boolean(fileToUpload));
    setPendingFile(null);
    setSending(true);
    setError("");
    setMessages((current) => [
      ...current,
      {
        id: temporaryId,
        conversation_id: selected.id,
        role: "user",
        content,
        used_tools: [],
        used_skills: [],
        used_agents: [],
        api_cost_usd: 0,
        attachments: fileToUpload ? [{
          id: `temporary-attachment-${Date.now()}`,
          original_name: fileToUpload.name,
          content_type: fileToUpload.type || "application/pdf",
          size_bytes: fileToUpload.size,
          created_at: new Date().toISOString(),
        }] : [],
        created_at: new Date().toISOString(),
      },
    ]);
    window.requestAnimationFrame(scrollThreadToBottom);

    try {
      let uploaded: Attachment | null = null;
      if (fileToUpload) uploaded = await api.uploadAttachment(fileToUpload);
      await api.sendMessageWithAttachments(selected.id, content, uploaded ? [uploaded.id] : []);
      setMessages(await api.listMessages(selected.id));
      setConversations((current) => [
        selected,
        ...current.filter((item) => item.id !== selected.id),
      ]);
    } catch (err) {
      setMessages((current) => current.filter((message) => message.id !== temporaryId));
      setCurrentDraft(content);
      setPendingFile(fileToUpload);
      setError(err instanceof Error ? err.message : "Message failed");
    } finally {
      setSending(false);
      setProcessingPdf(false);
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    try {
      await api.deleteConversation(pendingDelete.id);
      setConversations((current) => current.filter((item) => item.id !== pendingDelete.id));
      setDrafts((current) => {
        const next = { ...current };
        delete next[pendingDelete.id];
        return next;
      });
      if (selected?.id === pendingDelete.id) {
        setSelected(null);
        setMessages([]);
      }
      setPendingDelete(null);
    } catch (err) {
      setPendingDelete(null);
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  function agentName(id: string) {
    return agents.find((agent) => agent.id === id)?.name ?? "Unknown agent";
  }

  async function copyMessage(message: Message) {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopiedMessageId(message.id);
      window.setTimeout(() => {
        setCopiedMessageId((current) => current === message.id ? null : current);
      }, 1500);
    } catch {
      setError("Message could not be copied");
    }
  }

  return (
    <div className="app-shell chat-shell">
      <AppHeader />

      <main className="layout chat-layout">
        <section className="box panel conversation-panel">
          <div className="panel-head">
            <h1>Conversations</h1>
            <button type="button" className="btn btn-primary" onClick={startCreate}>New chat</button>
          </div>
          {loading ? <p>Loading...</p> : null}
          {!loading && conversations.length === 0 ? <p>No conversations yet.</p> : null}
          <ul className="conversation-list">
            {conversations.map((conversation) => (
              <li key={conversation.id} className={selected?.id === conversation.id ? "active" : ""}>
                <button
                  type="button"
                  className="conversation-item"
                  onClick={() => void selectConversation(conversation)}
                >
                  <strong>{conversation.title}</strong>
                  <span>{agentName(conversation.agent_id)}</span>
                </button>
                <button type="button" className="btn btn-danger" onClick={() => setPendingDelete(conversation)}>
                  Delete
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="box panel chat-panel">
          {error ? <p className="error">{error}</p> : null}
          {creating ? (
            <>
              <div className="panel-accent">
                <div className="panel-head">
                  <div>
                    <h1>New conversation</h1>
                    <p>Choose an agent and give the conversation a title.</p>
                  </div>
                  <button type="button" className="icon-close" onClick={() => setCreating(false)}>×</button>
                </div>
              </div>
              <form className="stack" onSubmit={createConversation}>
                <label>
                  Agent
                  <select value={agentId} onChange={(event) => setAgentId(event.target.value)} required>
                    {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
                  </select>
                </label>
                <label>
                  Title
                  <input value={title} onChange={(event) => setTitle(event.target.value)} required />
                </label>
                {agents.length === 0 ? <p>Create an agent before starting a chat.</p> : null}
                <button className="btn btn-primary btn-large btn-block" disabled={!agentId}>
                  Create conversation
                </button>
              </form>
            </>
          ) : selected ? (
            <div className="chat-workspace">
              <div className="panel-accent chat-heading">
                <h1>{selected.title}</h1>
                <p>{agentName(selected.agent_id)} · remembers the last 20 messages</p>
              </div>
              <div ref={messageThreadRef} className="message-thread" aria-live="polite">
                {loadingMessages ? <p>Loading messages...</p> : null}
                {!loadingMessages && messages.length === 0 ? (
                  <div className="empty-chat">
                    <p className="idle-title">Start the conversation</p>
                    <p>Send a message to your agent.</p>
                  </div>
                ) : null}
                {messages.map((message) => (
                  <div key={message.id} className={`message-row ${message.role}`}>
                    <div className="message-bubble">
                      <div className="message-bubble-head">
                        <span className="message-role">
                          {message.role === "user" ? "You" : agentName(selected.agent_id)}
                        </span>
                      </div>
                      {message.role === "assistant" ? (
                        <div className="markdown-content">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              a: ({ href, children }) => (
                                <a href={href} onClick={(event) => void handleMarkdownLink(event, href)}>{children}</a>
                              ),
                            }}
                          >{message.content}</ReactMarkdown>
                        </div>
                      ) : (
                        <p>{message.content}</p>
                      )}
                      {message.attachments.length > 0 ? (
                        <div className="message-attachments">
                          {message.attachments.map((attachment) => (
                            <span key={attachment.id} className="attachment-chip">
                              PDF · {attachment.original_name}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {message.used_tools.length > 0 || message.used_skills.length > 0 || message.used_agents.length > 0 ? (
                        <div className="message-metadata">
                          {message.used_tools.length > 0 ? <p>Used tools: {message.used_tools.join(", ")}</p> : null}
                          {message.used_skills.length > 0 ? <p>Used skills: {message.used_skills.join(", ")}</p> : null}
                          {message.used_agents.length > 0 ? <p>Used agents: {message.used_agents.join(", ")}</p> : null}
                        </div>
                      ) : null}
                      {message.role === "assistant" && message.api_cost_usd > 0 ? (
                        <p className="message-cost">API cost: ${message.api_cost_usd.toFixed(6)}</p>
                      ) : null}
                      {message.role === "assistant" ? <HumanFeedback targetType="message" targetId={message.id} /> : null}
                      <div className="message-actions">
                        <button
                          type="button"
                          className="message-copy"
                          onClick={() => void copyMessage(message)}
                          aria-label="Copy message"
                          title="Copy message"
                        >
                          {copiedMessageId === message.id ? "Copied" : "Copy"}
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
                {sending ? (
                  <div className="message-row assistant">
                    <div className="message-bubble message-waiting">
                      <p>{processingPdf ? "Processing PDF..." : "Thinking..."}</p>
                    </div>
                  </div>
                ) : null}
              </div>
              {error ? <p className="error composer-error">{error}</p> : null}
              <form className="chat-composer" onSubmit={sendMessage}>
                <div className="composer-inputs">
                  <div className="composer-main">
                    <label
                      className="attachment-plus"
                      data-tooltip="Attach a PDF file"
                      aria-label="Attach a PDF file"
                    >
                      +
                      <input
                        type="file"
                        accept="application/pdf,.pdf"
                        disabled={sending}
                        onChange={(event) => setPendingFile(event.target.files?.[0] ?? null)}
                      />
                    </label>
                    <textarea
                      rows={3}
                      placeholder="Write a message..."
                      value={draft}
                      onChange={(event) => setCurrentDraft(event.target.value)}
                      onKeyDown={handleComposerKeyDown}
                      disabled={sending}
                    />
                  </div>
                  <div className="attachment-controls">
                    {pendingFile ? (
                      <span className="pending-attachment">
                        {pendingFile.name}
                        <button type="button" onClick={() => setPendingFile(null)} aria-label="Remove attachment">×</button>
                      </span>
                    ) : null}
                  </div>
                </div>
                <button className="btn btn-primary btn-large" disabled={sending || (!draft.trim() && !pendingFile)}>
                  {sending ? "Sending..." : "Send"}
                </button>
              </form>
            </div>
          ) : (
            <div className="idle-panel">
              <p className="idle-title">Your conversations</p>
              <p>Create a new chat or select an existing conversation.</p>
            </div>
          )}
        </section>
      </main>

      {pendingDelete ? (
        <div className="modal-backdrop" onClick={() => setPendingDelete(null)}>
          <div className="box modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <h2>Delete conversation</h2>
            <p>Remove <strong>{pendingDelete.title}</strong> and all of its messages?</p>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => setPendingDelete(null)}>Cancel</button>
              <button type="button" className="btn btn-primary" onClick={() => void confirmDelete()}>Delete</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
