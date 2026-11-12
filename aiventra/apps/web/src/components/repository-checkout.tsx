"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button, Pretty, useApp } from "./common";

type Checkout = {
  id: string;
  version: number;
  status: string;
  data: {
    error?: string;
    manifest: { branch: string; commit: string };
    receipt?: {
      source_digest: string;
      file_count: number;
      bytes: number;
      error?: string;
      notice?: string;
    };
  };
};
type Execution = {
  id: string;
  status: string;
  data: { result?: unknown; error?: string };
};
export function RepositoryCheckout({ repositoryId }: { repositoryId: string }) {
  const { run, busy } = useApp();
  const [rows, setRows] = useState<Checkout[]>([]);
  const [error, setError] = useState("");
  const [suite, setSuite] = useState("python-unittest");
  const [approval, setApproval] = useState<{
    id: string;
    checkout: string;
    suite: string;
  } | null>(null);
  const [execution, setExecution] = useState<Execution | null>(null);
  const [savedExecutions, setSavedExecutions] = useState<
    { id: string; status: string }[]
  >([]);
  const reload = useCallback(
    async () =>
      setRows(await api<Checkout[]>(`/repositories/${repositoryId}/checkouts`)),
    [repositoryId],
  );
  useEffect(() => {
    let active = true;
    api<Checkout[]>(`/repositories/${repositoryId}/checkouts`)
      .then((value) => {
        if (active) setRows(value);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [repositoryId]);
  return (
    <section aria-label="Restricted repository checkout">
      <h3>Temporary restricted checkout</h3>
      <p>
        Fetch the imported commit into the dedicated runner. No GitHub changes.
        Test execution requires a separate approval and a configured Docker
        runner.
      </p>
      {error && <p role="alert">{error}</p>}
      <Button
        disabled={busy}
        onClick={() =>
          run(async () => {
            try {
              await api(`/repositories/${repositoryId}/checkout`, {
                request_id: crypto.randomUUID(),
              });
            } finally {
              await reload();
            }
          }, "Checkout request saved. Inspect its actual result below.")
        }
      >
        Request isolated checkout
      </Button>
      {rows.map((row) => (
        <div key={row.id}>
          <p>
            {row.status} · {row.data.manifest.branch} ·{" "}
            <span className="mono">{row.data.manifest.commit}</span>
          </p>
          <Button
            secondary
            disabled={busy}
            onClick={() =>
              run(async () => {
                setSavedExecutions(
                  await api<{ id: string; status: string }[]>(
                    `/repository-checkouts/${row.id}/executions`,
                  ),
                );
              }, "Saved execution history loaded.")
            }
          >
            Load saved executions
          </Button>
          {row.data.receipt?.file_count !== undefined && (
            <p>
              {row.data.receipt.file_count} files · {row.data.receipt.bytes}{" "}
              bytes
            </p>
          )}
          {row.data.receipt?.notice && <p>{row.data.receipt.notice}</p>}
          {(row.data.error || row.data.receipt?.error) && (
            <p role="alert">{row.data.error || row.data.receipt?.error}</p>
          )}
          <Button
            secondary
            disabled={busy}
            onClick={() =>
              run(async () => {
                await api(`/repository-checkouts/${row.id}/reconcile`, {});
                await reload();
              }, "Checkout receipt refreshed.")
            }
          >
            Refresh checkout receipt
          </Button>
          <Button
            secondary
            disabled={
              busy || row.status === "fetching" || row.status === "cleaned"
            }
            onClick={() =>
              run(async () => {
                await api(`/repository-checkouts/${row.id}/cleanup`, {});
                setApproval(null);
                await reload();
              }, "Temporary source removed.")
            }
          >
            Clean up checkout
          </Button>
          {row.status === "ready" && (
            <>
              <label>
                Restricted verification suite
                <select
                  aria-label="Checkout test suite"
                  value={suite}
                  onChange={(event) => {
                    setSuite(event.target.value);
                    setApproval(null);
                  }}
                >
                  <option value="python-unittest">
                    Python unittest + compile
                  </option>
                  <option value="node-test">Node test + syntax</option>
                </select>
              </label>
              <Button
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const value = await api<{ id: string }>(
                      `/repository-checkouts/${row.id}/approve-execution`,
                      {
                        request_id: crypto.randomUUID(),
                        version: row.version,
                        source_digest: row.data.receipt?.source_digest,
                        suite,
                      },
                    );
                    setApproval({ id: value.id, checkout: row.id, suite });
                  }, "Exact source and suite approved for ten minutes; execution has not started.")
                }
              >
                Approve this source for tests
              </Button>
              <Button
                disabled={
                  busy ||
                  approval?.checkout !== row.id ||
                  approval.suite !== suite
                }
                onClick={() =>
                  run(async () => {
                    if (!approval) return;
                    setExecution(
                      await api<Execution>(
                        `/repository-checkouts/${row.id}/execute`,
                        {
                          request_id: crypto.randomUUID(),
                          approval_id: approval.id,
                        },
                      ),
                    );
                    setApproval(null);
                  }, "Saved runner execution result received.")
                }
              >
                Run approved tests
              </Button>
            </>
          )}
        </div>
      ))}
      {!!savedExecutions.length && (
        <div aria-label="Saved checkout executions">
          {savedExecutions.map((job) => (
            <Button
              key={job.id}
              secondary
              disabled={busy}
              onClick={() =>
                run(async () => {
                  setExecution(
                    await api<Execution>(
                      `/repository-checkout-executions/${job.id}`,
                    ),
                  );
                }, "Saved execution details loaded.")
              }
            >
              {job.status} · {job.id}
            </Button>
          ))}
        </div>
      )}
      {execution && (
        <div>
          <p>Execution: {execution.status}</p>
          <Pretty value={execution.data} />
          <Button
            secondary
            disabled={busy}
            onClick={() =>
              run(async () => {
                setExecution(
                  await api<Execution>(
                    `/repository-checkout-executions/${execution.id}/reconcile`,
                    {},
                  ),
                );
              }, "Saved execution reconciled.")
            }
          >
            Refresh saved execution
          </Button>
        </div>
      )}
    </section>
  );
}
