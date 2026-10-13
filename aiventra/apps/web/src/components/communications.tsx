"use client";
import { useState } from "react";
import { ArrowRight, MessageSquare, Send, Users } from "lucide-react";
import { api, date } from "@/lib/api";
import { Badge, Button, Empty, Panel, Pretty, useApp } from "./common";
import { AgentWorkControls } from "./agent-work-controls";
import { NativeExecution } from "./native-execution";
export function Communications({ chat }: { chat: boolean }) {
  const { state, run, busy } = useApp();
  const [text, setText] = useState("");
  const [reply, setReply] = useState("");
  const [mode, setMode] = useState("mock");
  const [channel, setChannel] = useState("");
  const [messageLimit, setMessageLimit] = useState(30);
  const [meetingLimit, setMeetingLimit] = useState(10);
  if (chat)
    return (
      <div className="chat-layout">
        <Panel
          title="CEO · executive command interface"
          subtitle="Authenticated commands map to recorded backend actions"
        >
          <div className="chat-welcome">
            <span className="agent-avatar">CEO</span>
            <h2>What should we focus on?</h2>
            <p>
              Ask for project or test records, direct company controls, or
              submit a client brief for consultation.
            </p>
            <div className="suggestions">
              {[
                "Show every active project",
                "Give me the complete test report",
                "Show spending",
                "Pause all production deployments",
              ].map((command) => (
                <button key={command} onClick={() => setText(command)}>
                  {command}
                  <ArrowRight size={14} />
                </button>
              ))}
            </div>
          </div>
          <div className="chat-history">
            {state.messages
              .filter((m) => m.type === "OWNER_COMMAND")
              .slice()
              .reverse()
              .map((m) => (
                <div key={m.id}>
                  <div className="chat-bubble owner">
                    {String(m.content.input)}
                  </div>
                  <div className="chat-bubble ceo">
                    <strong>CEO command interface</strong>
                    <p>{String(m.content.reply)}</p>
                    <small>
                      Recorded action:{" "}
                      {String(m.content.executed_action || "None")}
                    </small>
                  </div>
                </div>
              ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                const result = await api<{
                  reply: string;
                  action: string | null;
                }>("/chat", { text, mode });
                setReply(result.reply);
                setText("");
              }, "Command response recorded with audit evidence.");
            }}
          >
            <div className="chat-composer">
              <textarea
                aria-label="Message the CEO"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Give a direction, or use consult: followed by a requirement…"
                rows={3}
                required
              />
              <div>
                <select
                  aria-label="Consultation provider mode"
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                >
                  <option value="mock">Local fixture</option>
                  <option value="live">Live providers</option>
                </select>
                <Button type="submit" disabled={busy || !text.trim()}>
                  <Send size={15} />
                  Send direction
                </Button>
              </div>
            </div>
          </form>
        </Panel>
        <Panel title="Human direction, explicit execution">
          <div className="control-note">
            <MessageSquare />
            <p>
              This command interface executes a bounded set of authenticated
              operations. It does not claim an action for unsupported
              instructions. Live specialist consultation starts with{" "}
              <code>consult:</code>.
            </p>
          </div>
          <h3>Approval boundaries</h3>
          <p>
            Proposal approval, repository modification, budgets and deployments
            remain controlled by server-side policy.
          </p>
          {reply && (
            <details>
              <summary>Last recorded response</summary>
              <Pretty value={reply} />
            </details>
          )}
        </Panel>
      </div>
    );
  const messages = state.messages.filter((m) => !channel || m.type === channel);
  const types = [...new Set(state.messages.map((m) => m.type))];
  return (
    <>
      <AgentWorkControls />
      <NativeExecution />
      <Panel
        title="Internal consulting meetings"
        subtitle="Independent contributions, one synthesis round, recorded decision"
      >
        {state.meetings.length ? (
          state.meetings.slice(0, meetingLimit).map((m) => (
            <details key={m.id}>
              <summary>
                <Users size={17} />
                {m.agenda}
                <Badge mode={m.mode}>{m.mode}</Badge>
              </summary>
              <p>
                {m.rounds} bounded round · {m.contributions.length} persisted
                specialist contributions
              </p>
              <Pretty value={m.contributions} />
              <h3>Decision</h3>
              <Pretty value={m.decision} />
            </details>
          ))
        ) : (
          <Empty
            title="No meeting records yet"
            text="A consulting workflow saves actual specialist outputs before recording a recommendation."
          />
        )}
        {state.meetings.length > meetingLimit && (
          <Button secondary onClick={() => setMeetingLimit(meetingLimit + 10)}>
            Show more meeting records
          </Button>
        )}
      </Panel>
      <Panel
        title="Company communication feed"
        subtitle="Durable messages with correlation and acknowledgement"
      >
        <div className="toolbar">
          <select
            aria-label="Message type"
            value={channel}
            onChange={(e) => {
              setChannel(e.target.value);
              setMessageLimit(30);
            }}
          >
            <option value="">All message types</option>
            {types.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </div>
        <p className="muted">
          Showing {Math.min(messageLimit, messages.length)} of {messages.length}{" "}
          messages in this snapshot.
        </p>
        {messages.slice(0, messageLimit).map((m) => (
          <details key={m.id}>
            <summary>
              <Badge>{m.type}</Badge>
              <Badge>{m.status}</Badge>
              {state.agents.find((a) => a.id === m.sender)?.name ||
                m.sender.slice(0, 20)}{" "}
              →{" "}
              {state.agents.find((a) => a.id === m.recipient)?.name ||
                m.recipient}
              <small>{date(m.created_at)}</small>
            </summary>
            <Pretty value={m.content} />
            <p className="mono muted">Correlation: {m.correlation_id}</p>
            {m.status === "delivered" && (
              <Button
                secondary
                disabled={busy}
                onClick={() => run(() => api(`/messages/${m.id}/ack`, {}))}
              >
                Acknowledge message
              </Button>
            )}
          </details>
        ))}
        {messages.length > messageLimit && (
          <Button secondary onClick={() => setMessageLimit(messageLimit + 30)}>
            Show more messages
          </Button>
        )}
      </Panel>
    </>
  );
}
