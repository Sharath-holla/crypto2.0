"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  Database,
  GitBranch,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Empty, Panel, Pretty, useApp } from "./common";

type Facts = Record<string, unknown>;
type Model = {
  position: number;
  spec_id: string;
  architecture: string;
  target_type: string;
  horizon_minutes: number;
  seed: number;
  status: string;
  best_iteration: number | null;
  metrics: Facts | null;
  artifact_integrity: string;
};
type Fold = {
  fold_id: string;
  display_fold: number;
  status: string;
  specs_expected: number;
  reports_reported_complete: number;
  models_verified_complete: number | null;
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
};
type Snapshot = {
  identity: Facts;
  dataset: Facts;
  lineage: Facts;
  folds: Fold[];
  models: Model[];
  preparation: Facts;
  training: Facts;
  resources: Facts;
  holdout: Facts;
  observed_at: number;
};
type Scope = {
  scope_hash: string;
  command: string[];
  execution_blockers: string[];
  request: Facts;
  identity: Facts;
  fold_id: string;
  spec: Facts;
};
type Job = {
  id: string;
  title: string;
  status: string;
  version: number;
  data: { scope: Scope; runtime_receipt?: Facts };
};
type JobView = { record: Job; runtime: Facts | null };
type Artifact = {
  name: string;
  relative_path: string;
  directory: boolean;
  bytes: number | null;
};
const tabs = [
  "Overview",
  "Scientific Identity",
  "Lineage",
  "Data",
  "Folds",
  "Preparation",
  "Training",
  "Models",
  "Metrics",
  "Jobs",
  "Artifacts",
  "Logs",
  "Recovery",
  "Approvals",
  "Resources",
  "Settings",
];
const jobTypes = [
  "CRYPTO_RUNTIME_HEALTH",
  "CRYPTO_RECOVERY_INSPECT",
  "CRYPTO_REPORT_GENERATE",
  "CRYPTO_CACHE_PREPARE",
  "CRYPTO_CACHE_VALIDATE",
  "CRYPTO_FOLD_TRAIN",
  "CRYPTO_SPEC_TRAIN",
  "CRYPTO_LINEAGE_VALIDATE",
  "CRYPTO_MODEL_VALIDATE",
];
const display = (value: unknown) =>
  value == null
    ? "Not available"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
const bytes = (value: unknown) =>
  typeof value === "number"
    ? `${(value / 1024 ** 3).toFixed(2)} GiB`
    : "Not available";
const timestamp = (value: unknown) =>
  typeof value === "number"
    ? new Date(value * 1000).toLocaleString()
    : "Not available";

function FactsView({ value }: { value: Facts }) {
  return (
    <dl className="crypto-facts">
      {Object.entries(value).map(([key, item]) => (
        <div key={key}>
          <dt>{key.replaceAll("_", " ")}</dt>
          <dd>{display(item)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function CryptoProjectLink() {
  const { navigate } = useApp();
  return (
    <Panel
      title="Managed scientific project"
      subtitle="An existing engine, separate from generated-code projects."
    >
      <div className="crypto-project-link">
        <div>
          <strong>Crypto 2.0</strong>
          <p>Phase 7A · Core20 research · protected scientific assets</p>
        </div>
        <Button secondary onClick={() => navigate("crypto")}>
          Open Crypto 2.0
        </Button>
      </div>
    </Panel>
  );
}

export function CryptoProject() {
  const { run, busy } = useApp();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [registered, setRegistered] = useState(false);
  const [jobs, setJobs] = useState<JobView[]>([]);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("Overview");
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState("position");
  const [jobType, setJobType] = useState("CRYPTO_RUNTIME_HEALTH");
  const [spec, setSpec] = useState("architecture-G0-A6-60m-raw");
  const [seconds, setSeconds] = useState(60);
  const [ceiling, setCeiling] = useState("0");
  const [currency, setCurrency] = useState("INR");
  const [cpuThreads, setCpuThreads] = useState(1);
  const [ramFloor, setRamFloor] = useState(1);
  const [diskFloor, setDiskFloor] = useState(1);
  const [consent, setConsent] = useState<string[]>([]);
  const [category, setCategory] = useState("reports");
  const [directory, setDirectory] = useState(".");
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [document, setDocument] = useState("");
  const [selectedJob, setSelectedJob] = useState<JobView | Facts | null>(null);

  const reload = useCallback(async () => {
    try {
      const [project, list] = await Promise.all([
        api<{ registration: unknown; snapshot: Snapshot }>("/crypto/project"),
        api<JobView[]>("/crypto/jobs"),
      ]);
      setSnapshot(project.snapshot);
      setRegistered(Boolean(project.registration));
      setJobs(list);
      setError("");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Crypto evidence unavailable",
      );
    }
  }, []);
  useEffect(() => {
    void reload();
    const timer = setInterval(() => void reload(), 15000);
    return () => clearInterval(timer);
  }, [reload]);
  const models = useMemo(
    () =>
      (snapshot?.models || [])
        .filter((model) =>
          `${model.spec_id} ${model.status}`
            .toLowerCase()
            .includes(filter.toLowerCase()),
        )
        .sort((a, b) =>
          sort === "horizon"
            ? a.horizon_minutes - b.horizon_minutes
            : a.position - b.position,
        ),
    [snapshot, filter, sort],
  );

  const inspect = async (
    nextCategory = category,
    nextDirectory = directory,
  ) => {
    const result = await api<{ entries: Artifact[] }>(
      `/crypto/artifacts?category=${encodeURIComponent(nextCategory)}&path=${encodeURIComponent(nextDirectory)}`,
    );
    setArtifacts(result.entries);
    setCategory(nextCategory);
    setDirectory(nextDirectory);
    setDocument("");
  };
  const preview = async (parent?: Job) => {
    await api("/crypto/jobs/preview", {
      request_id: crypto.randomUUID(),
      job_type: parent?.data.scope.request.job_type || jobType,
      spec_id: parent?.data.scope.request.spec_id || spec,
      maximum_runtime_seconds: seconds,
      deadline_utc: Math.floor(Date.now() / 1000) + seconds + 60,
      cost_ceiling: ceiling,
      cost_currency: currency,
      cpu_threads: cpuThreads,
      minimum_free_ram_gib: ramFloor,
      minimum_free_disk_gib: diskFloor,
      parent_job_id: parent?.id || null,
    });
    setTab("Approvals");
    await reload();
  };
  const pending = jobs.filter(
    ({ record }) => record.status === "PENDING_APPROVAL",
  );

  return (
    <div className="crypto-workspace" data-testid="crypto-workspace">
      <section className="crypto-masthead">
        <div>
          <p className="eyebrow">MANAGED SCIENTIFIC ENGINE</p>
          <h2>Crypto 2.0</h2>
          <p>
            Research evidence. Explicit authority. No automatic scientific
            execution.
          </p>
        </div>
        <div className="crypto-lock">
          <LockKeyhole size={18} />
          <div>
            <strong>August · LOCKED_UNUSED</strong>
            <small>
              used=false · evaluation_authorized=false · July unused
            </small>
          </div>
        </div>
      </section>
      <div className="crypto-toolbar">
        <Badge>{display(snapshot?.identity.mode || "Awaiting evidence")}</Badge>
        <span>Observed {timestamp(snapshot?.observed_at)}</span>
        <Button secondary onClick={() => void reload()}>
          <RefreshCw size={14} /> Refresh evidence
        </Button>
      </div>
      {error && (
        <div className="alert" role="alert">
          {error}. No demo metrics substituted.
        </div>
      )}
      <nav className="crypto-tabs" aria-label="Crypto navigation">
        {tabs.map((name) => (
          <button
            key={name}
            className={tab === name ? "selected" : ""}
            aria-current={tab === name ? "page" : undefined}
            onClick={() => setTab(name)}
          >
            {name}
          </button>
        ))}
      </nav>
      {!snapshot ? (
        <Empty
          title="Awaiting Crypto evidence"
          text="Start the private adapter and check configuration. The platform will not invent progress or results."
        />
      ) : (
        <>
          {tab === "Overview" && (
            <>
              <div className="stats-grid">
                {[
                  ["Phase / profile", "7A · CORE20_PRIMARY", Activity],
                  ["Fold 1 models verified", "Not evaluated / 48", GitBranch],
                  ["Gold evidence", display(snapshot.dataset.status), Database],
                  [
                    "Lineage closure",
                    display(snapshot.lineage.full_lineage_closure),
                    ShieldCheck,
                  ],
                ].map(([label, value, Icon]) => {
                  const Symbol = Icon as typeof Activity;
                  return (
                    <div className="stat-card" key={String(label)}>
                      <div className="stat-label">
                        {String(label)}
                        <Symbol size={16} />
                      </div>
                      <div className="stat-value crypto-status-value">
                        {String(value)}
                      </div>
                    </div>
                  );
                })}
              </div>
              <Panel
                title="The scientific boundary"
                subtitle="Aiventra is the control plane. Crypto remains authoritative."
              >
                <FactsView
                  value={{
                    run_identity: snapshot.identity.run_identity,
                    configuration_hash: snapshot.identity.configuration_hash,
                    research_cutoff_exclusive:
                      snapshot.identity.research_cutoff,
                    prospective_holdout: "LOCKED_UNUSED",
                    canonical_folds: 16,
                    canonical_primary_specs: 48,
                    production_features: 109,
                    prepared_cache: snapshot.preparation.status,
                    current_training_evidence: snapshot.training.status,
                    production_winner: "Not evaluated",
                  }}
                />
                {!registered && (
                  <Button
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        await api("/crypto/register", {});
                        await reload();
                      }, "Existing protected Crypto project registered")
                    }
                  >
                    Register existing Crypto project
                  </Button>
                )}
              </Panel>
              <Panel
                title="Evidence, not assumptions"
                subtitle="Historical restored counts are not validation of this machine."
              >
                <p>
                  Missing evidence is shown as unavailable. Reported metrics
                  remain distinct from validated model/checkpoint completion. No
                  fold is declared complete from filenames or a worker exit.
                </p>
              </Panel>
            </>
          )}
          {tab === "Scientific Identity" && (
            <Panel title="Canonical scientific identity">
              <Pretty value={snapshot.identity} />
            </Panel>
          )}
          {tab === "Lineage" && (
            <Panel
              title="Scientific lineage"
              subtitle="Registry, universe, descriptors and Silver closure remain protected."
            >
              <FactsView value={snapshot.lineage} />
            </Panel>
          )}
          {tab === "Data" && (
            <Panel
              title="Protected research data"
              subtitle="Read-only manifest metadata; market rows are not loaded by this view."
            >
              <FactsView value={snapshot.dataset} />
            </Panel>
          )}
          {tab === "Folds" && (
            <Panel
              title="16 canonical walk-forward folds"
              subtitle="No automatic fold advancement or fabricated completion."
            >
              <div className="crypto-fold-grid">
                {snapshot.folds.map((fold) => (
                  <article className="crypto-fold-card" key={fold.fold_id}>
                    <strong>Fold {fold.display_fold}</strong>
                    <Badge>{fold.status}</Badge>
                    <small>{fold.fold_id}</small>
                    <p>
                      TRAIN {fold.train_start.slice(0, 10)} →{" "}
                      {fold.train_end.slice(0, 10)}
                    </p>
                    <p>
                      TEST {fold.test_start.slice(0, 10)} →{" "}
                      {fold.test_end.slice(0, 10)}
                    </p>
                    <span>
                      {fold.reports_reported_complete} reported ·{" "}
                      {display(fold.models_verified_complete)} verified / 48
                    </span>
                  </article>
                ))}
              </div>
            </Panel>
          )}
          {tab === "Preparation" && (
            <Panel
              title="Preparation evidence"
              subtitle="Stage + elapsed only; no invented progress percentage."
            >
              <Pretty value={snapshot.preparation} />
            </Panel>
          )}
          {tab === "Training" && (
            <Panel
              title="Fold 1 training monitor"
              subtitle="48 canonical primary specs. Actual device/iteration stay unavailable without evidence."
            >
              <Pretty value={snapshot.training} />
            </Panel>
          )}
          {["Models", "Metrics"].includes(tab) && (
            <Panel
              title="Regression models and results"
              subtitle="Reported metrics are not model qualification or a production-winner decision."
            >
              <div className="crypto-toolbar">
                <label>
                  Filter models
                  <input
                    aria-label="Filter Crypto models"
                    value={filter}
                    onChange={(event) => setFilter(event.target.value)}
                  />
                </label>
                <label>
                  Sort
                  <select
                    aria-label="Sort Crypto models"
                    value={sort}
                    onChange={(event) => setSort(event.target.value)}
                  >
                    <option value="position">Canonical position</option>
                    <option value="horizon">Horizon</option>
                  </select>
                </label>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Spec</th>
                      <th>Architecture</th>
                      <th>Horizon</th>
                      <th>Target</th>
                      <th>Seed</th>
                      <th>Evidence</th>
                      <th>Best iteration</th>
                      <th>MAE / RMSE / R² / DA / IC</th>
                    </tr>
                  </thead>
                  <tbody>
                    {models.map((model) => (
                      <tr key={model.spec_id}>
                        <td>
                          {model.position}. {model.spec_id}
                        </td>
                        <td>{model.architecture}</td>
                        <td>{model.horizon_minutes}m</td>
                        <td>{model.target_type}</td>
                        <td>{model.seed}</td>
                        <td>{model.status}</td>
                        <td>{display(model.best_iteration)}</td>
                        <td>
                          {model.metrics ? (
                            <details>
                              <summary>Reported regression metrics</summary>
                              <Pretty value={model.metrics} />
                            </details>
                          ) : (
                            "Not evaluated"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
          {["Jobs", "Approvals"].includes(tab) && (
            <>
              <Panel
                title="Request an exact scientific operation"
                subtitle="Preview first. Approval never bypasses the canonical engine or target-host safety gates."
              >
                <form
                  className="crypto-job-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void run(() => preview());
                  }}
                >
                  <label>
                    Operation
                    <select
                      aria-label="Crypto job type"
                      value={jobType}
                      onChange={(event) => setJobType(event.target.value)}
                    >
                      {jobTypes.map((type) => (
                        <option key={type}>{type}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Canonical specification
                    <select
                      aria-label="Crypto canonical spec"
                      value={spec}
                      onChange={(event) => setSpec(event.target.value)}
                    >
                      {snapshot.models.map((model) => (
                        <option key={model.spec_id}>{model.spec_id}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Maximum runtime (seconds)
                    <input
                      aria-label="Crypto maximum runtime"
                      type="number"
                      min={5}
                      max={86400}
                      value={seconds}
                      onChange={(event) =>
                        setSeconds(Number(event.target.value))
                      }
                    />
                  </label>
                  <label>
                    Explicit cost ceiling
                    <input
                      aria-label="Crypto cost ceiling"
                      value={ceiling}
                      onChange={(event) => setCeiling(event.target.value)}
                    />
                  </label>
                  <label>
                    CPU threads
                    <input
                      aria-label="Crypto CPU threads"
                      type="number"
                      min={1}
                      max={128}
                      value={cpuThreads}
                      onChange={(event) =>
                        setCpuThreads(Number(event.target.value))
                      }
                    />
                  </label>
                  <label>
                    Minimum free RAM (GiB)
                    <input
                      aria-label="Crypto minimum free RAM"
                      type="number"
                      min={0.01}
                      step={0.01}
                      value={ramFloor}
                      onChange={(event) =>
                        setRamFloor(Number(event.target.value))
                      }
                    />
                  </label>
                  <label>
                    Minimum free disk (GiB)
                    <input
                      aria-label="Crypto minimum free disk"
                      type="number"
                      min={0.01}
                      step={0.01}
                      value={diskFloor}
                      onChange={(event) =>
                        setDiskFloor(Number(event.target.value))
                      }
                    />
                  </label>
                  <label>
                    Currency
                    <input
                      aria-label="Crypto cost currency"
                      value={currency}
                      onChange={(event) =>
                        setCurrency(event.target.value.toUpperCase())
                      }
                    />
                  </label>
                  <Button type="submit" disabled={busy || !registered}>
                    Preview operation (does not execute)
                  </Button>
                </form>
                <p>
                  Heavy operations remain blocked on Windows and without
                  reviewed Linux/Gold/equivalence evidence. No holdout or
                  arbitrary-shell operation exists.
                </p>
              </Panel>
              <Panel
                title={
                  tab === "Approvals"
                    ? "Exact owner approvals"
                    : "Persisted jobs"
                }
                subtitle={`${pending.length} pending approval · no automatic replay`}
              >
                {jobs.length === 0 ? (
                  <Empty
                    title="No jobs requested"
                    text="Starting the platform does not queue preparation, training or evaluation."
                  />
                ) : (
                  jobs.map(({ record, runtime }) => (
                    <article className="crypto-job-card" key={record.id}>
                      <div className="crypto-toolbar">
                        <strong>{record.title}</strong>
                        <Badge>
                          {display(runtime?.state || record.status)}
                        </Badge>
                      </div>
                      <small>{record.id}</small>
                      <details>
                        <summary>
                          Exact scope, command, resources and scientific
                          identity
                        </summary>
                        <Pretty value={record.data.scope} />
                      </details>
                      {record.data.scope.execution_blockers.length > 0 && (
                        <p role="status">
                          BLOCKED:{" "}
                          {record.data.scope.execution_blockers.join("; ")}
                        </p>
                      )}
                      {record.status === "PENDING_APPROVAL" && (
                        <>
                          <label className="crypto-consent">
                            <input
                              type="checkbox"
                              checked={consent.includes(record.id)}
                              onChange={(event) =>
                                setConsent((current) =>
                                  event.target.checked
                                    ? [...current, record.id]
                                    : current.filter((id) => id !== record.id),
                                )
                              }
                            />
                            I reviewed this exact command, scope, deadline and
                            resource/cost contract.
                          </label>
                          <Button
                            disabled={
                              busy ||
                              !consent.includes(record.id) ||
                              record.data.scope.execution_blockers.length > 0
                            }
                            onClick={() =>
                              void run(async () => {
                                await api(`/crypto/jobs/${record.id}/approve`, {
                                  version: record.version,
                                  scope_hash: record.data.scope.scope_hash,
                                });
                                await reload();
                              }, "Exact operation approved; independent worker requested")
                            }
                          >
                            Approve exact operation
                          </Button>
                        </>
                      )}
                      {record.status !== "PENDING_APPROVAL" && (
                        <div className="crypto-toolbar">
                          <Button
                            secondary
                            disabled={busy}
                            onClick={() => setSelectedJob({ record, runtime })}
                          >
                            Inspect job evidence
                          </Button>
                          <Button
                            secondary
                            disabled={busy}
                            onClick={() =>
                              void run(async () => {
                                setSelectedJob(
                                  await api(`/crypto/jobs/${record.id}/logs`),
                                );
                              })
                            }
                          >
                            Read job log tail
                          </Button>
                          <Button
                            secondary
                            disabled={busy}
                            onClick={() =>
                              void run(async () => {
                                await api(
                                  `/crypto/jobs/${record.id}/reconcile`,
                                  {},
                                );
                                await reload();
                              })
                            }
                          >
                            Reconcile evidence (no replay)
                          </Button>
                          {![
                            "COMPLETED",
                            "PREPARATION_COMPLETE",
                            "STOPPED",
                            "FAILED",
                            "BLOCKED",
                            "INTERRUPTED",
                          ].includes(
                            String(runtime?.state || record.status),
                          ) && (
                            <Button
                              secondary
                              disabled={busy}
                              onClick={() => {
                                if (
                                  window.confirm(
                                    "Approve stopping this exact Crypto job? Its evidence will be preserved.",
                                  )
                                )
                                  void run(async () => {
                                    await api(
                                      `/crypto/jobs/${record.id}/stop`,
                                      {
                                        version: record.version,
                                        scope_hash:
                                          record.data.scope.scope_hash,
                                      },
                                    );
                                    await reload();
                                  });
                              }}
                            >
                              Approve stop
                            </Button>
                          )}
                          {[
                            "INTERRUPTED",
                            "STOPPED",
                            "FAILED",
                            "BLOCKED",
                          ].includes(record.status) && (
                            <Button
                              secondary
                              disabled={busy}
                              onClick={() => void run(() => preview(record))}
                            >
                              Request fresh resume approval
                            </Button>
                          )}
                        </div>
                      )}
                    </article>
                  ))
                )}
                {selectedJob && <Pretty value={selectedJob} />}
              </Panel>
            </>
          )}
          {["Artifacts", "Logs"].includes(tab) && (
            <Panel
              title="Read-only artifact browser"
              subtitle="No delete, Gold/Silver access, secret files or path traversal."
            >
              <form
                className="crypto-toolbar"
                onSubmit={(event) => {
                  event.preventDefault();
                  void run(() => inspect());
                }}
              >
                <label>
                  Category
                  <select
                    aria-label="Crypto artifact category"
                    value={category}
                    onChange={(event) => setCategory(event.target.value)}
                  >
                    {[
                      "cache",
                      "models",
                      "reports",
                      "logs",
                      "checkpoints",
                      "verification",
                      "historical",
                    ].map((name) => (
                      <option key={name}>{name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Relative directory
                  <input
                    aria-label="Crypto artifact directory"
                    value={directory}
                    onChange={(event) => setDirectory(event.target.value)}
                  />
                </label>
                <Button type="submit" disabled={busy}>
                  Inspect directory
                </Button>
              </form>
              {artifacts.length === 0 && (
                <p>Awaiting evidence. No artifacts invented.</p>
              )}
              <div className="crypto-artifacts">
                {artifacts.map((item) => (
                  <button
                    key={item.relative_path}
                    onClick={() =>
                      void run(async () => {
                        if (item.directory)
                          await inspect(category, item.relative_path);
                        else {
                          const result = await api<{ content: string }>(
                            `/crypto/document?category=${encodeURIComponent(category)}&path=${encodeURIComponent(item.relative_path)}&tail=${tab === "Logs"}`,
                          );
                          setDocument(result.content);
                        }
                      })
                    }
                  >
                    {item.directory ? "Directory" : "Protected file"} ·{" "}
                    {item.name} · {item.bytes ?? "—"} bytes
                  </button>
                ))}
              </div>
              {document && <Pretty value={document} />}
            </Panel>
          )}
          {tab === "Recovery" && (
            <Panel
              title="Interruptions and recovery"
              subtitle="Inspect → validate identity → obtain fresh approval. Never automatically replay science."
            >
              <p>
                A vanished worker or stale heartbeat is interrupted, not
                completed. Model-only evidence requires owner review;
                corrupt/partial cache and model/report artifacts remain
                protected.
              </p>
              {jobs
                .filter(({ record, runtime }) =>
                  ["INTERRUPTED", "FAILED", "BLOCKED", "STOPPED"].includes(
                    String(runtime?.state || record.status),
                  ),
                )
                .map((job) => (
                  <Pretty key={job.record.id} value={job} />
                ))}
              <Button
                secondary
                disabled={busy || !registered}
                onClick={() => {
                  setJobType("CRYPTO_RECOVERY_INSPECT");
                  setTab("Jobs");
                }}
              >
                Request read-only recovery inspection
              </Button>
            </Panel>
          )}
          {tab === "Resources" && (
            <Panel
              title="Observed host resources"
              subtitle="Live host observations, not a real-training sufficiency or GPU qualification claim."
            >
              <FactsView
                value={{
                  cpu_count: snapshot.resources.cpu_count,
                  cpu_percent: snapshot.resources.cpu_percent,
                  ram_total: bytes(snapshot.resources.ram_total_bytes),
                  ram_available: bytes(snapshot.resources.ram_available_bytes),
                  adapter_rss: bytes(snapshot.resources.process_rss_bytes),
                  disk_total: bytes(snapshot.resources.disk_total_bytes),
                  disk_free: bytes(snapshot.resources.disk_free_bytes),
                  adapter_pid: snapshot.resources.adapter_pid,
                  worker_pid: snapshot.resources.worker_pid,
                  gpu: snapshot.resources.gpu,
                  gpu_required: snapshot.resources.gpu_required,
                }}
              />
            </Panel>
          )}
          {tab === "Settings" && (
            <Panel
              title="Execution boundaries"
              subtitle="Server-configured paths and closed operations; no browser environment overrides."
            >
              <FactsView
                value={{
                  mode: snapshot.identity.mode,
                  scientific_execution_authorized: false,
                  august: "LOCKED_UNUSED",
                  holdout_operation: "Not exposed",
                  arbitrary_shell: "Not exposed",
                  automatic_next_fold: false,
                  cloud_provisioning: "Not exposed",
                  live_trading: "Not exposed",
                }}
              />
            </Panel>
          )}
        </>
      )}
    </div>
  );
}
