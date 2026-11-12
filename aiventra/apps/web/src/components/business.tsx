"use client";
import { useState } from "react";
import { BookOpen, Plus, Users } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Empty, Panel, Pretty, useApp } from "./common";
export function Business({ view }: { view: string }) {
  const { state, run, busy } = useApp();
  const kinds =
    view === "crm"
      ? ["opportunity", "email_draft", "calendar_draft", "campaign"]
      : ["knowledge", "support", "incident"];
  const [kind, setKind] = useState(kinds[0]);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [project, setProject] = useState("");
  const [clientName, setClientName] = useState("");
  const [tab, setTab] = useState(kinds[0]);
  const records = state.records.filter((r) => r.kind === tab);
  return (
    <>
      {view === "crm" && (
        <Panel
          title="Client directory"
          subtitle="Client-scoped consulting and project records"
        >
          <div className="client-grid">
            {state.clients.map((c) => (
              <div className="client-card" key={c.id}>
                <span className="agent-avatar">
                  <Users size={22} />
                </span>
                <h3>{c.name}</h3>
                <small>
                  {
                    state.requirements.filter((r) => r.client_id === c.id)
                      .length
                  }{" "}
                  requirements ·{" "}
                  {state.projects.filter((p) => p.client_id === c.id).length}{" "}
                  projects
                </small>
              </div>
            ))}
          </div>
          <form
            className="inline-form"
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                await api("/clients", { name: clientName });
                setClientName("");
              });
            }}
          >
            <label>
              New client name
              <input
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
                required
              />
            </label>
            <Button type="submit" disabled={busy}>
              <Plus size={15} />
              Add client
            </Button>
          </form>
        </Panel>
      )}
      <div className="tabs">
        {kinds.map((k) => (
          <button
            key={k}
            className={tab === k ? "active" : ""}
            onClick={() => setTab(k)}
          >
            {k.replaceAll("_", " ")}
          </button>
        ))}
      </div>
      {["email_draft", "calendar_draft", "campaign"].includes(tab) && (
        <div className="alert warning">
          Draft storage is implemented. OAuth account connections, recipient
          validation and approved external sending/publishing are pending. No
          external action is executed.
        </div>
      )}
      <div className="two-columns">
        <Panel
          title={`Stored ${tab.replaceAll("_", " ")} records`}
          subtitle="Persistent business records with versioned owner updates"
        >
          {records.length ? (
            records.map((r) => (
              <details key={r.id}>
                <summary>
                  {r.title} <Badge>{r.status}</Badge>
                </summary>
                <Pretty value={r.data} />
                <label>
                  Status
                  <select
                    value={r.status}
                    onChange={(e) =>
                      run(() =>
                        api(
                          `/records/${r.id}`,
                          { version: r.version, status: e.target.value },
                          "PATCH",
                        ),
                      )
                    }
                  >
                    {[
                      "open",
                      "qualified",
                      "won",
                      "lost",
                      "resolved",
                      "reviewed",
                    ].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </label>
              </details>
            ))
          ) : (
            <Empty
              title="No records in this workspace"
              text="Create a stored record to start tracking your company's work."
            />
          )}
        </Panel>
        <Panel
          title="Create a business record"
          subtitle="Project-scoped facts and drafts"
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                await api("/records", {
                  kind,
                  title,
                  project_id: project || null,
                  data: { body },
                });
                setTitle("");
                setBody("");
                setTab(kind);
              });
            }}
          >
            <label>
              Record type
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                {kinds.map((k) => (
                  <option key={k} value={k}>
                    {k.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Project scope
              <select
                value={project}
                onChange={(e) => setProject(e.target.value)}
              >
                <option value="">Organization record</option>
                {state.projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Title
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
            </label>
            <label>
              Details
              <textarea
                rows={7}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                required
              />
            </label>
            <Button type="submit" disabled={busy}>
              <BookOpen size={15} />
              Save record
            </Button>
          </form>
        </Panel>
      </div>
    </>
  );
}
