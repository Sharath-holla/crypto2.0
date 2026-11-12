"use client";
import { useEffect, useState } from "react";
import { api, date } from "@/lib/api";
import { Badge, Button, Empty, Panel, Pretty, useApp } from "./common";

type Entry = {
  id: string;
  title: string;
  kind: string;
  version: number;
  source_key: string;
  visibility: string;
  index_status: string;
  project_id: string | null;
  agent_id: string | null;
  updated_at: number;
};
type Version = {
  version: number;
  content: string;
  content_hash: string;
  provenance: { grants?: string[] };
};
type Result = {
  id: string;
  title: string;
  excerpt: string;
  version: number;
  source_key: string;
  retrieval: string;
  score: number;
};
type MemoryData = {
  mode: string;
  reason: string;
  storage: string;
  entries: Entry[];
  results: Result[];
};

export function MemoryBrowser() {
  const { state, run, busy } = useApp();
  const [project, setProject] = useState("");
  const [agent, setAgent] = useState("");
  const [query, setQuery] = useState("");
  const [data, setData] = useState<MemoryData | null>(null);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [kind, setKind] = useState("knowledge");
  const [visibility, setVisibility] = useState("organization");
  const [memoryAgent, setMemoryAgent] = useState("");
  const [grants, setGrants] = useState<string[]>([]);
  const [editing, setEditing] = useState<Entry | null>(null);
  const [history, setHistory] = useState<Version[]>([]);
  const load = async () => {
    const params = new URLSearchParams({ query });
    if (project) params.set("project_id", project);
    if (agent) params.set("agent_id", agent);
    setData(await api<MemoryData>(`/semantic-memory?${params}`));
    setError("");
  };
  useEffect(() => {
    let active = true;
    const params = new URLSearchParams();
    if (project) params.set("project_id", project);
    if (agent) params.set("agent_id", agent);
    api<MemoryData>(`/semantic-memory?${params}`)
      .then((d) => {
        if (active) {
          setData(d);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [project, agent]);
  return (
    <>
      <Panel
        title="Company memory"
        subtitle="Versioned evidence · scoped retrieval · local embeddings"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run(load);
          }}
        >
          <div className="form-grid">
            <label>
              Memory project scope
              <select
                aria-label="Memory project scope"
                value={project}
                onChange={(e) => {
                  setProject(e.target.value);
                  setEditing(null);
                  setHistory([]);
                }}
              >
                <option value="">Organization / owner view</option>
                {state.projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Inspect agent access
              <select
                aria-label="Inspect agent access"
                value={agent}
                onChange={(e) => setAgent(e.target.value)}
              >
                <option value="">Owner access</option>
                {state.agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Search memory
              <input
                aria-label="Search memory"
                maxLength={500}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Find decisions, requirements or resolved errors"
              />
            </label>
          </div>
          <Button type="submit" disabled={busy}>
            Search memory
          </Button>{" "}
          <Button
            secondary
            disabled={busy}
            onClick={() =>
              run(async () => {
                await api("/semantic-memory/index", {});
                await load();
              }, "Bounded memory indexing checked")
            }
          >
            Index saved sources
          </Button>
        </form>
        {error && <p role="alert">{error}</p>}
        {data && (
          <>
            <p className="muted">
              <Badge>{data.mode}</Badge> · {data.storage} · {data.reason}
            </p>
            {data.results.map((r) => (
              <div className="run-evidence" key={r.id}>
                <strong>{r.title}</strong>
                <p className="muted">
                  v{r.version} · {r.retrieval} · {r.source_key}
                </p>
                <p className="memory-excerpt">{r.excerpt}</p>
              </div>
            ))}
            {!data.entries.length && (
              <Empty
                title="No memory in this scope"
                text="Save a decision or index existing project evidence."
              />
            )}
            {data.entries.map((entry) => (
              <details key={entry.id}>
                <summary>
                  {entry.title} <Badge>{entry.kind}</Badge> · v{entry.version} ·{" "}
                  {entry.index_status}
                </summary>
                <p>
                  {entry.visibility} · {date(entry.updated_at)} ·{" "}
                  {entry.source_key}
                </p>
                <Button
                  secondary
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      const versions = await api<Version[]>(
                        `/semantic-memory/${entry.id}/versions`,
                      );
                      setHistory(versions);
                      setEditing(entry);
                      if (entry.source_key.startsWith("manual:")) {
                        setProject(entry.project_id || "");
                        setTitle(entry.title);
                        setContent(versions[0]?.content || "");
                        setKind(entry.kind);
                        setVisibility(entry.visibility);
                        setMemoryAgent(entry.agent_id || "");
                        setGrants(versions[0]?.provenance.grants || []);
                      }
                    }, "Version history loaded")
                  }
                >
                  Inspect versions
                </Button>{" "}
                <Button
                  secondary
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await api(`/semantic-memory/${entry.id}/delete`, {
                        version: entry.version,
                      });
                      setEditing(null);
                      setHistory([]);
                      await load();
                    }, "Memory content purged; source tombstone retained")
                  }
                >
                  Purge memory content
                </Button>
              </details>
            ))}
          </>
        )}
      </Panel>
      {history.length > 0 && (
        <Panel
          title={`Version history · ${editing?.title}`}
          subtitle="Source-backed records are revised through their original workflow"
        >
          {history.map((v) => (
            <details key={v.version}>
              <summary>
                Version {v.version} · {v.content_hash.slice(0, 12)}
              </summary>
              <p className="memory-excerpt">{v.content}</p>
              <Pretty value={v.provenance} />
            </details>
          ))}
        </Panel>
      )}
      <Panel
        title={
          editing?.source_key.startsWith("manual:")
            ? "Revise saved memory"
            : "Save memory or architecture decision"
        }
        subtitle="Owner-authored evidence; every revision preserves its source and permissions"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run(async () => {
              const body = {
                title,
                content,
                kind,
                project_id: project || null,
                agent_id: memoryAgent || null,
                visibility,
                grant_ids: grants,
              };
              if (editing?.source_key.startsWith("manual:"))
                await api(
                  `/semantic-memory/${editing.id}`,
                  { ...body, version: editing.version },
                  "PATCH",
                );
              else await api("/semantic-memory", body);
              setEditing(null);
              setHistory([]);
              setTitle("");
              setContent("");
              await load();
            }, "Memory saved");
          }}
        >
          <div className="form-grid">
            <label>
              Memory title
              <input
                aria-label="Memory title"
                required
                maxLength={200}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <label>
              Memory type
              <select
                aria-label="Memory type"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
              >
                {[
                  "knowledge",
                  "architecture_decision",
                  "resolution",
                  "working_memory",
                ].map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </select>
            </label>
            <label>
              Memory visibility
              <select
                aria-label="Memory visibility"
                value={visibility}
                onChange={(e) => setVisibility(e.target.value)}
              >
                {["organization", "project", "agent", "selected", "owner"].map(
                  (k) => (
                    <option key={k}>{k}</option>
                  ),
                )}
              </select>
            </label>
            {visibility === "agent" && (
              <label>
                Private memory agent
                <select
                  aria-label="Private memory agent"
                  required
                  value={memoryAgent}
                  onChange={(e) => setMemoryAgent(e.target.value)}
                >
                  <option value="">Select agent</option>
                  {state.agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          {visibility === "selected" && (
            <fieldset>
              <legend>Permitted agents</legend>
              <div className="participant-grid">
                {state.agents.map((a) => (
                  <label key={a.id}>
                    <input
                      type="checkbox"
                      aria-label={`Memory access for ${a.name}`}
                      checked={grants.includes(a.id)}
                      onChange={(e) =>
                        setGrants(
                          e.target.checked
                            ? [...grants, a.id]
                            : grants.filter((id) => id !== a.id),
                        )
                      }
                    />
                    {a.name}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          <label>
            Memory content
            <textarea
              aria-label="Memory content"
              required
              maxLength={64000}
              value={content}
              onChange={(e) => setContent(e.target.value)}
            />
          </label>
          <Button
            type="submit"
            disabled={busy || (visibility === "project" && !project)}
          >
            Save memory
          </Button>{" "}
          {editing && (
            <Button
              secondary
              onClick={() => {
                setEditing(null);
                setHistory([]);
                setTitle("");
                setContent("");
              }}
            >
              New entry
            </Button>
          )}
        </form>
      </Panel>
    </>
  );
}
