"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { BusinessRecord, Task } from "@/lib/types";
import { Badge, Button, Panel, Pretty, useApp } from "./common";

type Configuration = {
  credential_configured: boolean;
  repositories: string[];
  draft_only: boolean;
  repair_request_limit: number;
};

export function PublicationControls({
  projectId,
  tasks,
}: {
  projectId: string;
  tasks: Task[];
}) {
  const { state, run, busy } = useApp();
  const [config, setConfig] = useState<Configuration | null>(null);
  const [error, setError] = useState("");
  const [taskId, setTaskId] = useState("");
  const [repository, setRepository] = useState("");
  const [base, setBase] = useState("main");
  const [objective, setObjective] = useState("");
  const pending = useRef<{ hash: string; id: string } | null>(null);
  useEffect(() => {
    let active = true;
    api<Configuration>("/operations/github")
      .then((value) => {
        if (active) setConfig(value);
      })
      .catch((cause: unknown) => {
        if (active) setError(String(cause));
      });
    return () => {
      active = false;
    };
  }, []);
  const records = state.records.filter(
    (record) =>
      record.kind === "github_publication" && record.project_id === projectId,
  );
  const eligible = tasks.filter(
    (task) =>
      task.kind === "coding" &&
      task.status === "completed" &&
      task.payload.mode === "live",
  );
  const selectedRepository = repository || config?.repositories[0] || "";
  return (
    <Panel
      title="GitHub draft publication"
      subtitle="Exact candidate approval · scoped connector · independent evidence · no force push"
    >
      {error && <p className="alert warning">{error}</p>}
      {!config ? (
        <p className="muted">Loading connector configuration…</p>
      ) : (
        <>
          <p>
            <Badge>
              {config.credential_configured
                ? "Credential configured"
                : "Credential missing"}
            </Badge>{" "}
            {config.repositories.length} authorized repositories · drafts only ·
            up to {config.repair_request_limit} owner-approved repair scopes
          </p>
          <p className="muted">
            The server needs a repository-scoped GitHub credential outside model
            and runner environments. A source-code push does not configure this
            connector.
          </p>
          <form
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              run(
                () =>
                  api(`/tasks/${taskId}/publication-preview`, {
                    repository: selectedRepository,
                    base_ref: base,
                  }),
                "Exact publication preview saved. Review the diff and evidence before approving.",
              );
            }}
          >
            <label>
              Verified coding candidate
              <select
                aria-label="Publication task"
                value={taskId}
                onChange={(event) => setTaskId(event.target.value)}
                required
              >
                <option value="">Choose a completed live coding task</option>
                {eligible.map((task) => (
                  <option key={task.id} value={task.id}>
                    {task.objective}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Authorized GitHub repository
              <select
                aria-label="Publication repository"
                value={selectedRepository}
                onChange={(event) => setRepository(event.target.value)}
                required
              >
                {!config.repositories.length && (
                  <option value="">No repository authorized</option>
                )}
                {config.repositories.map((name) => (
                  <option key={name}>{name}</option>
                ))}
              </select>
            </label>
            <label>
              Remote base branch
              <input
                aria-label="Publication base branch"
                value={base}
                onChange={(event) => setBase(event.target.value)}
                required
              />
            </label>
            <div className="full">
              <Button
                type="submit"
                disabled={
                  busy ||
                  !taskId ||
                  !selectedRepository ||
                  !config.credential_configured
                }
              >
                Prepare exact publication preview
              </Button>
            </div>
          </form>
        </>
      )}
      {records.map((record: BusinessRecord) => {
        const data = record.data;
        return (
          <details key={record.id}>
            <summary>
              {record.title} <Badge>{record.status}</Badge>
            </summary>
            <Pretty value={data.manifest} />
            {record.status === "prepared" && (
              <Button
                disabled={busy}
                onClick={() =>
                  run(
                    () =>
                      api(`/publications/${record.id}/approve`, {
                        version: record.version,
                        content_hash: data.manifest_hash,
                      }),
                    "Exact publication manifest approved. Publishing is a separate action.",
                  )
                }
              >
                Approve exact publication
              </Button>
            )}
            {(["approved", "needs_reconciliation"].includes(record.status) ||
              (record.status === "publishing" &&
                typeof data.lease_until === "number" &&
                data.lease_until <= Date.now() / 1000)) && (
              <Button
                disabled={busy}
                onClick={() =>
                  run(
                    () => api(`/publications/${record.id}/publish`, {}),
                    "GitHub returned and verified the approved draft pull request.",
                  )
                }
              >
                {record.status === "needs_reconciliation"
                  ? "Reconcile and retry exact publication"
                  : "Publish approved draft"}
              </Button>
            )}
            {typeof data.error === "string" && data.error && (
              <p className="alert warning">{data.error}</p>
            )}
            {record.status === "published" && (
              <>
                {typeof data.url === "string" && (
                  <p>
                    <a href={data.url} target="_blank" rel="noreferrer">
                      Open verified draft pull request
                    </a>
                  </p>
                )}
                <Button
                  secondary
                  disabled={busy}
                  onClick={() =>
                    run(
                      () => api(`/publications/${record.id}/feedback`, {}),
                      "CI and review feedback saved for the approved remote commit.",
                    )
                  }
                >
                  Retrieve CI and review feedback
                </Button>
                <Pretty value={data.feedback} />
                {typeof data.feedback_hash === "string" && (
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      const hash = JSON.stringify({
                        record: record.id,
                        feedback: data.feedback_hash,
                        objective,
                      });
                      if (pending.current?.hash !== hash)
                        pending.current = { hash, id: crypto.randomUUID() };
                      run(async () => {
                        await api(`/publications/${record.id}/repairs`, {
                          request_id: pending.current!.id,
                          feedback_hash: data.feedback_hash,
                          objective,
                        });
                        pending.current = null;
                        setObjective("");
                      }, "Repair scope created. Approve its exact repository scope before execution.");
                    }}
                  >
                    <label>
                      Review repair objective
                      <textarea
                        minLength={10}
                        maxLength={2000}
                        value={objective}
                        onChange={(event) => setObjective(event.target.value)}
                        required
                      />
                    </label>
                    <Button type="submit" secondary disabled={busy}>
                      Prepare bounded repair scope
                    </Button>
                  </form>
                )}
              </>
            )}
          </details>
        );
      })}
      {!records.length && (
        <p className="muted">
          No generated draft has been published for this project.
        </p>
      )}
    </Panel>
  );
}
