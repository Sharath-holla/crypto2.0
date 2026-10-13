"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUp,
  Check,
  Copy,
  FileText,
  LoaderCircle,
  MessageSquare,
  PanelRightClose,
  PanelRightOpen,
  Paperclip,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, date, money } from "@/lib/api";
import type {
  Artifact,
  Conversation,
  ConversationSnapshot,
  ConversationTurn,
} from "@/lib/types";
import { Badge, Button, Empty, Pretty, useApp } from "./common";

const activeStatuses = [
  "queued",
  "running",
  "waiting_for_provider",
  "waiting_for_free_provider",
];
const starters = [
  {
    title: "Plan a new application",
    detail: "Turn a brief into an approved direction",
    text: "Help me plan a new application. Compare viable architectures, identify unknowns, and prepare a proposal before implementation.",
    intent: "consult",
  },
  {
    title: "Compare cloud options",
    detail: "Consider cost, reliability and migration",
    text: "Compare my current cloud infrastructure with alternatives. Ask for the workload, region, egress and budget details before recommending a migration.",
    intent: "consult",
  },
  {
    title: "Review project architecture",
    detail: "Work from the context you provide",
    text: "Review the selected project's architecture and documents. Identify risks and missing evidence before suggesting improvements.",
    intent: "chat",
  },
  {
    title: "Optimize project costs",
    detail: "Inspect assumptions before making changes",
    text: "Analyze the selected project's cost assumptions and budget. What evidence do we need to identify viable savings?",
    intent: "chat",
  },
] as const;

function ResponseBody({ text }: { text: string }) {
  return (
    <div className="markdown">
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          img: ({ alt }) => <span>[Image: {alt || "external image"}]</span>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="markdown-table">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {text}
      </Markdown>
    </div>
  );
}

export function CEOChat({
  conversationId,
  onCreated,
}: {
  conversationId: string;
  onCreated: (id: string) => void;
}) {
  const { state, refresh, navigate } = useApp();
  const [snapshot, setSnapshot] = useState<ConversationSnapshot | null>(null);
  const [olderBusy, setOlderBusy] = useState(false);
  const mergeRecent = useCallback((next: ConversationSnapshot) => {
    setSnapshot((current) => {
      if (
        !current ||
        current.conversation.id !== next.conversation.id ||
        !current.turns.length
      )
        return next;
      const known = new Set(current.turns.map((row) => row.id));
      if (
        next.total_turns > current.total_turns &&
        next.turns.length &&
        next.turns.every((row) => !known.has(row.id))
      )
        return next;
      const turns = [
        ...new Map(
          [...current.turns, ...next.turns].map((row) => [row.id, row]),
        ).values(),
      ].sort((a, b) => a.position - b.position);
      return {
        ...next,
        turns,
        attachments: [
          ...new Map(
            [...current.attachments, ...next.attachments].map((row) => [
              row.id,
              row,
            ]),
          ).values(),
        ],
        next_cursor:
          current.turns[0].position < (next.turns[0]?.position || 0)
            ? current.next_cursor
            : next.next_cursor,
      };
    });
  }, []);
  const [loading, setLoading] = useState(Boolean(conversationId));
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"live" | "mock">("live");
  const [intent, setIntent] = useState<"chat" | "consult">("chat");
  const [clientId, setClientId] = useState(state.clients[0]?.id || "");
  const [projectId, setProjectId] = useState("");
  const [budget, setBudget] = useState("1");
  const [attached, setAttached] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [streamState, setStreamState] = useState("Connecting");
  const [contextOpen, setContextOpen] = useState(false);
  const [document, setDocument] = useState<Artifact | null>(null);
  const [copied, setCopied] = useState("");
  const createId = useRef(crypto.randomUUID());
  useEffect(() => {
    setContextOpen(window.matchMedia("(min-width: 1100px)").matches);
  }, []);
  const requestKey = useRef({ fingerprint: "", id: "" });
  const composer = useRef<HTMLTextAreaElement>(null);
  const timeline = useRef<HTMLDivElement>(null);
  const documentDialog = useRef<HTMLElement>(null);
  const nearBottom = useRef(true);
  const conversation = snapshot?.conversation;
  useEffect(() => {
    if (!document) return;
    const previous = window.document.activeElement as HTMLElement | null;
    const panel = documentDialog.current;
    const close = panel?.querySelector<HTMLButtonElement>("button");
    close?.focus();
    const trap = (event: KeyboardEvent) => {
      if (event.key === "Tab") {
        event.preventDefault();
        close?.focus();
      }
    };
    panel?.addEventListener("keydown", trap);
    return () => {
      panel?.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, [document]);
  const activeId = conversation?.id || conversationId;
  const reload = useCallback(async () => {
    if (activeId)
      mergeRecent(
        await api<ConversationSnapshot>(`/conversations/${activeId}`),
      );
  }, [activeId, mergeRecent]);
  useEffect(() => {
    setSnapshot(null);
    setLoading(Boolean(conversationId));
    setOlderBusy(false);
    setError("");
    if (!conversationId) return;
    let mounted = true;
    api<ConversationSnapshot>(`/conversations/${conversationId}`)
      .then((value) => {
        if (mounted) setSnapshot(value);
      })
      .catch((exc) => {
        if (mounted) setError(exc.message);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [conversationId]);
  useEffect(() => {
    if (!activeId) return;
    const source = new EventSource(`/api/conversations/${activeId}/events`);
    source.addEventListener("snapshot", (event) => {
      mergeRecent(JSON.parse((event as MessageEvent).data));
      setStreamState("Connected");
    });
    source.onerror = () => setStreamState("Reconnecting");
    // Durable snapshots are also recovered if an intermediary interrupts SSE.
    const timer = setInterval(
      () => reload().catch(() => setStreamState("Disconnected")),
      5000,
    );
    return () => {
      source.close();
      clearInterval(timer);
    };
  }, [activeId, reload, mergeRecent]);
  useEffect(() => {
    if (nearBottom.current && timeline.current)
      timeline.current.scrollTop = timeline.current.scrollHeight;
  }, [snapshot]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDocument(null);
        setContextOpen(false);
      }
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);
  const ensureConversation = async () => {
    if (conversation) return conversation;
    const created = await api<Conversation>("/conversations", {
      id: createId.current,
      client_id: clientId,
      project_id: projectId || null,
      mode,
      budget_micro: Math.round(Number(budget) * 1000000),
    });
    const value = await api<ConversationSnapshot>(
      `/conversations/${created.id}`,
    );
    setSnapshot(value);
    return created;
  };
  const submit = async (content = text) => {
    if (busy || !content.trim()) return;
    setBusy(true);
    setError("");
    try {
      const current = await ensureConversation();
      const fingerprint = JSON.stringify([content, intent, attached]);
      if (requestKey.current.fingerprint !== fingerprint)
        requestKey.current = { fingerprint, id: crypto.randomUUID() };
      await api(`/conversations/${current.id}/turns`, {
        request_id: requestKey.current.id,
        version: current.version,
        text: content,
        intent,
        attachment_ids: attached,
      });
      setText("");
      setAttached([]);
      requestKey.current = { fingerprint: "", id: "" };
      nearBottom.current = true;
      mergeRecent(
        await api<ConversationSnapshot>(`/conversations/${current.id}`),
      );
      if (!conversationId) onCreated(current.id);
      await refresh();
    } catch (exc) {
      setError(
        exc instanceof Error ? exc.message : "Message could not be queued",
      );
      await reload().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };
  const attach = async (file: File) => {
    if (attached.length >= 4) {
      setError("Attach up to four documents per message.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const current = await ensureConversation();
      const data = new FormData();
      data.append("file", file);
      const artifact = await api<Artifact>(
        `/conversations/${current.id}/attachments`,
        data,
      );
      setAttached((ids) => [...ids, artifact.id]);
      mergeRecent(
        await api<ConversationSnapshot>(`/conversations/${current.id}`),
      );
      await refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };
  const mutate = async (path: string) => {
    setBusy(true);
    setError("");
    try {
      await api(path, {});
      await reload();
      await refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };
  const pending = snapshot?.turns.find(
    (turn) => turn.workflow && activeStatuses.includes(turn.workflow.status),
  );
  const selectedProject = state.projects.find(
    (project) => project.id === (conversation?.project_id || projectId),
  );
  const actualBudget = state.budgets.find(
    (item) => item.scope === `conversation:${activeId}`,
  );
  const showDocument = async (id: string) => {
    try {
      setDocument(await api<Artifact>(`/artifacts/${id}`));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Document unavailable");
    }
  };
  const copy = async (turn: ConversationTurn) => {
    try {
      await navigator.clipboard.writeText(turn.response);
      setCopied(turn.id);
      setTimeout(() => setCopied(""), 2000);
    } catch {
      setError("Clipboard access is unavailable in this browser.");
    }
  };
  if (loading)
    return (
      <div className="conversation-loading" role="status">
        <LoaderCircle className="spin" />
        Loading your conversation…
      </div>
    );
  const providerMode = conversation?.mode || mode;
  return (
    <div
      className={`conversation-workspace ${contextOpen ? "with-context" : ""}`}
    >
      <section className="conversation-main" aria-label="CEO conversation">
        <div className="conversation-toolbar">
          <div>
            <Sparkles size={16} />
            <strong>{conversation?.title || "CEO workspace"}</strong>
            <Badge mode={providerMode}>
              {providerMode === "mock" ? "Local fixture" : "Live AI"}
            </Badge>
          </div>
          <button
            className="icon-button"
            aria-label={
              contextOpen
                ? "Hide conversation context"
                : "Show conversation context"
            }
            aria-expanded={contextOpen}
            onClick={() => setContextOpen(!contextOpen)}
          >
            {contextOpen ? (
              <PanelRightClose size={18} />
            ) : (
              <PanelRightOpen size={18} />
            )}
          </button>
        </div>
        <div
          className="conversation-scroll"
          ref={timeline}
          onScroll={() => {
            const element = timeline.current;
            if (element)
              nearBottom.current =
                element.scrollHeight -
                  element.scrollTop -
                  element.clientHeight <
                100;
          }}
        >
          {!snapshot?.turns.length && (
            <div className="conversation-welcome">
              <span className="welcome-symbol">
                <Sparkles size={27} />
              </span>
              <span className="eyebrow">AIVENTRA · OWNER WORKSPACE</span>
              <h1>
                Your autonomous
                <br />
                AI company.
              </h1>
              <p>
                One place to think, plan and build.
                <br />
                Every decision stays connected to its work.
              </p>
              <div className="starter-grid">
                {starters.map((starter) => (
                  <button
                    key={starter.title}
                    onClick={() => {
                      setIntent(starter.intent);
                      setText(starter.text);
                      composer.current?.focus();
                    }}
                  >
                    <span>
                      <strong>{starter.title}</strong>
                      <small>{starter.detail}</small>
                    </span>
                    <ArrowRight size={16} />
                  </button>
                ))}
              </div>
            </div>
          )}
          {!!snapshot?.turns.length && (
            <div className="conversation-timeline">
              {snapshot.next_cursor && (
                <Button
                  disabled={olderBusy}
                  onClick={async () => {
                    setOlderBusy(true);
                    try {
                      const older = await api<ConversationSnapshot>(
                        `/conversations/${snapshot.conversation.id}/history?before=${snapshot.next_cursor}`,
                      );
                      setSnapshot((current) =>
                        !current ||
                        current.conversation.id !== older.conversation.id
                          ? current
                          : {
                              ...current,
                              attachments: [
                                ...new Map(
                                  [
                                    ...current.attachments,
                                    ...older.attachments,
                                  ].map((row) => [row.id, row]),
                                ).values(),
                              ],
                              turns: [
                                ...new Map(
                                  [...older.turns, ...current.turns].map(
                                    (row) => [row.id, row],
                                  ),
                                ).values(),
                              ].sort((a, b) => a.position - b.position),
                              next_cursor: older.next_cursor,
                            },
                      );
                    } catch (e) {
                      setError(
                        e instanceof Error
                          ? e.message
                          : "History failed to load",
                      );
                    } finally {
                      setOlderBusy(false);
                    }
                  }}
                >
                  Load older chat history
                </Button>
              )}
              {snapshot.total_turns > snapshot.turns.length && (
                <p className="muted">
                  Showing the latest {snapshot.turns.length} of{" "}
                  {snapshot.total_turns} turns.
                </p>
              )}
              {snapshot.turns.map((turn) => (
                <article className="conversation-turn" key={turn.id}>
                  <div className="human-message">
                    <small>You · {date(turn.created_at)}</small>
                    <div>{turn.content}</div>
                    {turn.attachment_ids.map((id) => (
                      <button
                        className="attachment-chip"
                        key={id}
                        onClick={() => showDocument(id)}
                      >
                        <FileText size={14} />
                        {snapshot.attachments.find((file) => file.id === id)
                          ?.name || "Attached document"}
                      </button>
                    ))}
                  </div>
                  <div className="assistant-message">
                    <div className="assistant-identity">
                      <span className="ceo-symbol">
                        <Sparkles size={16} />
                      </span>
                      <strong>
                        {turn.intent === "consult"
                          ? "Consultation coordinator"
                          : "CEO"}
                      </strong>
                      <Badge mode={providerMode}>
                        {providerMode === "mock" ? "Fixture" : "Live"}
                      </Badge>
                    </div>
                    {!turn.response &&
                      turn.workflow?.status === "running" &&
                      turn.run_traces
                        ?.filter(
                          (trace) =>
                            trace.state === "streaming" && trace.preview,
                        )
                        .map((trace) => (
                          <div key={trace.id} className="native-preview">
                            <small>
                              Provisional native output · awaiting validation
                              and usage
                            </small>
                            <pre>{trace.preview}</pre>
                          </div>
                        ))}
                    {turn.response ? (
                      <ResponseBody text={turn.response} />
                    ) : (
                      <div className="response-status" role="status">
                        {turn.workflow?.status === "running" && (
                          <LoaderCircle className="spin" size={16} />
                        )}
                        <strong>
                          {[
                            "waiting_for_provider",
                            "waiting_for_free_provider",
                          ].includes(turn.workflow?.status || "")
                            ? "Waiting for an eligible free AI model"
                            : turn.workflow?.status === "cancelled"
                              ? "Response stopped"
                              : turn.workflow?.status === "needs_attention"
                                ? "Response needs attention"
                                : turn.workflow?.status === "running"
                                  ? "CEO is processing your question"
                                  : "Queued for the worker"}
                        </strong>
                        <p>
                          {[
                            "waiting_for_provider",
                            "waiting_for_free_provider",
                          ].includes(turn.workflow?.status || "")
                            ? "Your request is saved. Verify a local model, then authorize resumption in Models & providers. Remote inference is blocked by ZERO_COST_ONLY."
                            : turn.workflow?.last_error ||
                              (turn.workflow?.status === "cancelled"
                                ? "No response was published. In-flight provider usage may still be charged."
                                : "Status comes from the persistent workflow.")}
                        </p>
                        {[
                          "waiting_for_provider",
                          "waiting_for_free_provider",
                        ].includes(turn.workflow?.status || "") && (
                          <button
                            className="text-button"
                            onClick={() => navigate("models")}
                          >
                            Configure AI models <ArrowRight size={14} />
                          </button>
                        )}
                      </div>
                    )}
                    {turn.consultation && (
                      <div className="consultation-result">
                        <div>
                          <ShieldCheck size={18} />
                          <strong>Specialist consultation</strong>
                          <Badge mode={turn.consultation.requirement.status}>
                            {turn.consultation.requirement.status.replaceAll(
                              "_",
                              " ",
                            )}
                          </Badge>
                        </div>
                        <p>
                          {turn.consultation.workflow?.step || 0} of 7 saved
                          checkpoints · Implementation requires an approved
                          proposal.
                        </p>
                        <Button
                          secondary
                          onClick={() =>
                            navigate(
                              `proposals:${turn.consultation!.requirement.id}`,
                            )
                          }
                        >
                          Review consultation & proposal{" "}
                          <ArrowRight size={14} />
                        </Button>
                      </div>
                    )}
                    <div className="message-actions">
                      {turn.response && (
                        <button
                          aria-label="Copy response"
                          onClick={() => copy(turn)}
                        >
                          {copied === turn.id ? (
                            <Check size={14} />
                          ) : (
                            <Copy size={14} />
                          )}{" "}
                          {copied === turn.id ? "Copied" : "Copy"}
                        </button>
                      )}
                      {turn.workflow?.status === "completed" &&
                        turn.intent === "chat" && (
                          <button
                            disabled={busy || Boolean(pending)}
                            onClick={() => submit(turn.content)}
                          >
                            Ask again
                          </button>
                        )}
                      {turn.workflow?.status === "needs_attention" &&
                        turn.workflow.attempts < turn.workflow.max_attempts &&
                        !turn.runs.some((run) =>
                          ["uncertain", "started"].includes(run.status),
                        ) && (
                          <button
                            disabled={busy}
                            onClick={() =>
                              mutate(`/workflows/${turn.workflow!.id}/retry`)
                            }
                          >
                            Retry response
                          </button>
                        )}
                    </div>
                    <details className="execution-details">
                      <summary>
                        Inspect underlying work · {turn.runs.length} model runs
                      </summary>
                      {turn.workflow && (
                        <p>
                          Workflow: {turn.workflow.status} · Attempts:{" "}
                          {turn.workflow.attempts}/{turn.workflow.max_attempts}
                        </p>
                      )}
                      {turn.runs.map((run) => (
                        <div className="run-evidence" key={run.id}>
                          <strong>
                            {state.agents.find(
                              (agent) => agent.id === run.agent_id,
                            )?.name || "Agent"}{" "}
                            ·{" "}
                            {state.models.find(
                              (model) => model.id === run.model_id,
                            )?.identifier || run.model_id}
                          </strong>
                          <Badge mode={run.status}>{run.status}</Badge>
                          <small>
                            {run.input_tokens} input / {run.output_tokens}{" "}
                            output tokens · {money(run.cost_micro)} ·{" "}
                            {run.cost_basis}
                          </small>
                          <p>{run.routing_reason}</p>
                          {run.error && (
                            <p className="error-text">{run.error}</p>
                          )}
                          {turn.run_traces
                            ?.filter((trace) => trace.run_id === run.id)
                            .map((trace) => (
                              <p key={trace.id}>
                                Native stream: {trace.state} ·{" "}
                                {trace.event_count} events · {trace.tool_count}{" "}
                                calls · usage{" "}
                                {trace.usage_known ? "recorded" : "unresolved"}
                              </p>
                            ))}
                        </div>
                      ))}
                    </details>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
        <div className="composer-region">
          {error && (
            <div className="alert error" role="alert">
              <span>{error}</span>
              <button
                aria-label="Dismiss conversation error"
                onClick={() => setError("")}
              >
                <X size={15} />
              </button>
            </div>
          )}
          <form
            className="premium-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            {attached.length > 0 && (
              <div className="composer-attachments">
                {attached.map((id) => (
                  <span className="attachment-chip" key={id}>
                    <FileText size={14} />
                    {snapshot?.attachments.find((file) => file.id === id)?.name}
                    <button
                      aria-label="Remove attachment"
                      type="button"
                      onClick={() =>
                        setAttached((ids) =>
                          ids.filter((value) => value !== id),
                        )
                      }
                    >
                      <X size={13} />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <textarea
              aria-label="Message your AI company"
              ref={composer}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Describe a project, attach requirements, or ask your AI company to solve a problem…"
              rows={3}
              maxLength={20000}
              required
              disabled={busy}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                  event.preventDefault();
                  void submit();
                }
              }}
            />
            <div className="composer-controls">
              <label
                className={`attach-control ${busy ? "disabled" : ""}`}
                title="UTF-8 documents up to 16 KB"
              >
                <Paperclip size={18} />
                <span>Attach</span>
                <input
                  aria-label="Attach project document"
                  type="file"
                  accept=".txt,.md,.csv,.json"
                  disabled={busy || Boolean(pending)}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void attach(file);
                    event.target.value = "";
                  }}
                />
              </label>
              <select
                aria-label="Message intent"
                value={intent}
                onChange={(event) =>
                  setIntent(event.target.value as "chat" | "consult")
                }
              >
                <option value="chat">Ask CEO</option>
                <option value="consult">Start consultation</option>
              </select>
              <select
                aria-label="Conversation provider mode"
                value={providerMode}
                disabled={Boolean(conversation)}
                onChange={(event) =>
                  setMode(event.target.value as "live" | "mock")
                }
              >
                <option value="live">Live AI</option>
                {state.runtime.mock_enabled && (
                  <option value="mock">Local fixture</option>
                )}
              </select>
              {pending ? (
                <button
                  className="send-button stop-button"
                  aria-label="Stop response"
                  type="button"
                  disabled={busy}
                  title="In-flight usage may still be charged"
                  onClick={() =>
                    mutate(
                      `/conversations/${activeId}/turns/${pending.id}/cancel`,
                    )
                  }
                >
                  <Square size={15} fill="currentColor" />
                </button>
              ) : (
                <button
                  className="send-button"
                  aria-label="Send message"
                  type="submit"
                  disabled={busy || !text.trim() || !clientId}
                >
                  {busy ? (
                    <LoaderCircle className="spin" size={18} />
                  ) : (
                    <ArrowUp size={20} />
                  )}
                </button>
              )}
            </div>
          </form>
          <div className="composer-footnote">
            <span>
              {providerMode === "mock"
                ? "Explicit test fixture. No live inference."
                : "Advisory answers do not authorize implementation."}
            </span>
            <span>
              {activeId ? `Events: ${streamState}` : "Ctrl + Enter to send"}
            </span>
          </div>
        </div>
      </section>
      {contextOpen && (
        <aside className="chat-context" aria-label="Conversation context">
          <div className="context-heading">
            <span className="eyebrow">WORKSPACE CONTEXT</span>
            <button
              className="icon-button"
              aria-label="Close conversation context"
              onClick={() => setContextOpen(false)}
            >
              <X size={15} />
            </button>
          </div>
          <h2>Keep the work in view.</h2>
          <p>Choose the client and project behind this conversation.</p>
          <label>
            Client
            <select
              aria-label="Conversation client"
              value={conversation?.client_id || clientId}
              disabled={Boolean(conversation)}
              onChange={(event) => {
                setClientId(event.target.value);
                setProjectId("");
              }}
            >
              {state.clients.map((client) => (
                <option key={client.id} value={client.id}>
                  {client.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Project context
            <select
              aria-label="Conversation project"
              value={conversation?.project_id || projectId}
              disabled={Boolean(conversation)}
              onChange={(event) => setProjectId(event.target.value)}
            >
              <option value="">General company conversation</option>
              {state.projects
                .filter(
                  (project) =>
                    project.client_id === clientId ||
                    project.client_id === conversation?.client_id,
                )
                .map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Conversation budget (USD)
            <input
              aria-label="Conversation budget"
              type="number"
              min="0"
              max="1000"
              step="0.01"
              value={
                conversation
                  ? String(conversation.budget_micro / 1000000)
                  : budget
              }
              disabled={Boolean(conversation)}
              onChange={(event) => setBudget(event.target.value)}
            />
          </label>
          <div className="context-budget">
            <span>Recorded estimate</span>
            <strong>{money(actualBudget?.spent_micro || 0)}</strong>
            <small>
              {money(actualBudget?.reserved_micro || 0)} held · Hard cap{" "}
              {money(
                conversation?.budget_micro ??
                  Math.round(Number(budget) * 1000000),
              )}
            </small>
          </div>
          {selectedProject && (
            <div className="context-section">
              <span className="eyebrow">PROJECT</span>
              <h3>{selectedProject.name}</h3>
              <Badge mode={selectedProject.status}>
                {selectedProject.status}
              </Badge>
              <p>
                {
                  state.tasks.filter(
                    (task) =>
                      task.project_id === selectedProject.id &&
                      task.status === "completed",
                  ).length
                }{" "}
                of{" "}
                {
                  state.tasks.filter(
                    (task) => task.project_id === selectedProject.id,
                  ).length
                }{" "}
                tasks complete
              </p>
              <button
                className="text-button"
                onClick={() => navigate(`projects:${selectedProject.id}`)}
              >
                Open project <ArrowRight size={14} />
              </button>
            </div>
          )}
          <div className="context-section">
            <span className="eyebrow">EXECUTION</span>
            <div className="context-fact">
              <span>Worker</span>
              <Badge mode={state.runtime.worker.status}>
                {state.runtime.worker.status}
              </Badge>
            </div>
            <div className="context-fact">
              <span>CEO routing</span>
              <strong>
                {state.agents.find((agent) => agent.name === "CEO")
                  ?.routing_policy || "Not configured"}
              </strong>
            </div>
            {providerMode === "live" &&
              !state.runtime.providers.some(
                (provider) =>
                  provider.mode === "live" &&
                  provider.status === "configured_unverified",
              ) && (
                <p className="provider-note">
                  No live provider is configured. Requests wait safely without a
                  fabricated answer.
                </p>
              )}
            <button className="text-button" onClick={() => navigate("models")}>
              Models & providers <ArrowRight size={14} />
            </button>
          </div>
          <div className="context-section">
            <span className="eyebrow">DOCUMENTS</span>
            {snapshot?.attachments.length ? (
              snapshot.attachments.map((file) => (
                <div className="context-document" key={file.id}>
                  <button onClick={() => showDocument(file.id)}>
                    <FileText size={15} />
                    <span>{file.name}</span>
                  </button>
                  <button
                    aria-label={`Include ${file.name}`}
                    title="Include with next message"
                    disabled={
                      attached.includes(file.id) ||
                      attached.length >= 4 ||
                      Boolean(pending)
                    }
                    onClick={() => setAttached((ids) => [...ids, file.id])}
                  >
                    <Plus size={13} />
                  </button>
                </div>
              ))
            ) : (
              <p>
                Attach requirements or project notes. UTF-8 text, Markdown, CSV
                or JSON · 16 KB per file.
              </p>
            )}
          </div>
          <div className="context-boundary">
            <ShieldCheck size={16} />
            <p>Human approval stays between proposals and implementation.</p>
          </div>
        </aside>
      )}
      {document && (
        <div className="modal-overlay">
          <section
            className="modal"
            ref={documentDialog}
            role="dialog"
            aria-modal="true"
            aria-label="Attached document"
          >
            <button
              className="modal-close"
              aria-label="Close document"
              onClick={() => setDocument(null)}
            >
              ×
            </button>
            <h2>{document.name}</h2>
            <small className="mono">SHA-256: {document.sha256}</small>
            <Pretty value={document.content} />
          </section>
        </div>
      )}
    </div>
  );
}

export function ConversationHistory() {
  const { navigate } = useApp();
  const [items, setItems] = useState<Conversation[]>([]);
  const [search, setSearch] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const load = useCallback(
    async (before = "") => {
      const requestGeneration = ++generation.current;
      setLoading(true);
      setError("");
      try {
        const query = new URLSearchParams({ search });
        if (before) query.set("before", before);
        const result = await api<{
          items: Conversation[];
          next_cursor: string | null;
        }>(`/conversations?${query}`);
        if (generation.current !== requestGeneration) return;
        setItems((current) =>
          before
            ? [
                ...new Map(
                  [...current, ...result.items].map((row) => [row.id, row]),
                ).values(),
              ]
            : result.items,
        );
        setCursor(result.next_cursor);
      } catch (exc) {
        if (generation.current === requestGeneration)
          setError(exc instanceof Error ? exc.message : "History unavailable");
      } finally {
        if (generation.current === requestGeneration) setLoading(false);
      }
    },
    [search],
  );
  useEffect(() => {
    generation.current++;
    const timer = setTimeout(() => void load(), 200);
    return () => {
      generation.current++;
      clearTimeout(timer);
    };
  }, [load]);
  return (
    <section className="history-workspace">
      <div className="history-toolbar">
        <div className="filter-input">
          <Search size={16} />
          <input
            aria-label="Search conversations"
            placeholder="Search conversation titles…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <Button onClick={() => navigate("chat")}>
          <Plus size={16} />
          New conversation
        </Button>
      </div>
      {error && (
        <div role="alert" className="alert error">
          {error}
          <button onClick={() => void load()}>Retry</button>
        </div>
      )}
      {loading && !items.length ? (
        <Empty
          title="Loading conversations"
          text="Reading your saved company records."
        />
      ) : !items.length ? (
        <Empty
          title="No matching conversations"
          text="Start a new conversation and its context will be saved here."
        />
      ) : (
        <div className="history-list">
          {items.map((item) => (
            <button key={item.id} onClick={() => navigate(`chat:${item.id}`)}>
              <span className="history-icon">
                <MessageSquare size={20} />
              </span>
              <span>
                <strong>{item.title}</strong>
                <small>
                  {date(item.updated_at)} ·{" "}
                  {item.mode === "mock" ? "Local fixture" : "Live AI"} ·{" "}
                  {money(item.budget_micro)} cap
                </small>
              </span>
              <ArrowRight size={17} />
            </button>
          ))}
        </div>
      )}
      {cursor && (
        <Button secondary disabled={loading} onClick={() => void load(cursor)}>
          Load older conversations
        </Button>
      )}
    </section>
  );
}
