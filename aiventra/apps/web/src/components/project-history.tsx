"use client";
import { useEffect, useState } from "react";
import { api, date } from "@/lib/api";
import { Button, Panel, Pretty } from "./common";

type Event = {
  id: string;
  created_at: number;
  action: string;
  subject: string;
  detail: unknown;
};
type Page = { items: Event[]; next_cursor: string | null };

export function ProjectHistory({
  projectId,
  taskId,
}: {
  projectId: string;
  taskId?: string;
}) {
  const endpoint = taskId
    ? `/tasks/${taskId}/history`
    : `/projects/${projectId}/history`;
  const [history, setHistory] = useState<Page | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    setHistory(null);
    setError("");
    api<Page>(endpoint)
      .then((value) => {
        if (alive) setHistory(value);
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [endpoint]);
  const load = async (older: boolean) => {
    setBusy(true);
    setError("");
    try {
      const value = await api<Page>(
        `${endpoint}${older && history?.next_cursor ? `?before=${encodeURIComponent(history.next_cursor)}` : ""}`,
      );
      setHistory((current) => ({
        ...value,
        items: older
          ? [
              ...new Map(
                [...(current?.items || []), ...value.items].map((row) => [
                  row.id,
                  row,
                ]),
              ).values(),
            ]
          : value.items,
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "History failed to load");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel
      title={taskId ? "Task activity" : "Project activity"}
      subtitle="Recent saved events, newest first"
    >
      {error && <p role="alert">{error}</p>}
      <Button disabled={busy} onClick={() => load(false)}>
        Refresh recent activity
      </Button>
      {!history ? (
        <p>Loading saved activity…</p>
      ) : !history.items.length ? (
        <p>No saved activity.</p>
      ) : (
        <ol aria-label={taskId ? "Task history" : "Project history"}>
          {history.items.map((row) => (
            <li key={row.id} data-event-id={row.id}>
              <p>
                {date(row.created_at)} · {row.action}
              </p>
              <details>
                <summary>Saved details</summary>
                <Pretty value={{ subject: row.subject, detail: row.detail }} />
              </details>
            </li>
          ))}
        </ol>
      )}
      {history?.next_cursor && (
        <Button disabled={busy} onClick={() => load(true)}>
          Load older {taskId ? "task" : "project"} activity
        </Button>
      )}
    </Panel>
  );
}
