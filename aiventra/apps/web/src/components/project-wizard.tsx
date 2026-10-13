"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Workflow } from "@/lib/types";
import { Badge, Button, Loading, Panel, useApp } from "./common";
import type { CatalogModel, Catalog } from "./model-catalog";
import { ModelPicker } from "./model-picker";
import { ExecutionEvidence } from "./ai-readiness";
import { RequirementsReview } from "./requirements-review";

type Form = {
  client_id: string;
  title: string;
  text: string;
  step: number;
  source_project_id: string | null;
  repository_id: string | null;
  technology: string;
  constraints: string;
  deadline: string | null;
  budget_micro: number;
  preferred_lead: "GPT-6.1 Sol";
  lead_model_id: string | null;
  worker_mode: "automatic" | "manual" | "hybrid";
  worker_model_ids: string[];
  overrides: Record<string, string>;
  planning_mode: "ai" | "manual";
  review_before_planning?: boolean;
};
type Eligibility = { allowed: boolean; state: string; reason: string };
type Options = {
  models: CatalogModel[];
  providers: Catalog["providers"];
  roles: string[];
  departments: { id: string; name: string }[];
};
type Draft = {
  id: string;
  title: string;
  version: number;
  status: string;
  lead_status: Eligibility;
  workflow: Workflow | null;
  approved_project_id: string | null;
  required_approvals: string[];
  data: {
    form: Form;
    attachments: {
      id: string;
      name: string;
      parsed: boolean;
      redacted: boolean;
      bytes: number;
      source_sha256?: string;
      warnings?: string[];
      format?: string;
      page_count?: number;
      document_version?: number;
    }[];
    requirement_id?: string;
    manual_proposal_id?: string;
    refinement?: { approval_id: string | null };
  };
};

export function ProjectWizard({ initialId = "" }: { initialId?: string }) {
  const { state, navigate, refresh } = useApp();
  const [options, setOptions] = useState<Options | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [row, setRow] = useState<Draft | null>(null);
  const current = useRef<Form | null>(null);
  const saved = useRef<Draft | null>(null);
  const chain = useRef<Promise<unknown>>(Promise.resolve());
  const queued = useRef(0);
  const retrySave = useRef<{
    path: string;
    body: unknown;
    method: string;
  } | null>(null);
  const mounted = useRef(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [dirty, setDirty] = useState(false);
  const [editingModels, setEditingModels] = useState(false);
  const [replaceAttachment, setReplaceAttachment] = useState("");
  const [architecture, setArchitecture] = useState("");
  const [milestones, setMilestones] = useState("");
  const [criteria, setCriteria] = useState("");
  const [modelSearch, setModelSearch] = useState("");
  const [modelProvider, setModelProvider] = useState("");
  const [modelAvailability, setModelAvailability] = useState("all");
  const [refreshStatus, setRefreshStatus] = useState("");
  const [extraRoles, setExtraRoles] = useState<string[]>([]);
  const [extraDepartments, setExtraDepartments] = useState<string[]>([]);
  const accept = useCallback((result: Draft) => {
    saved.current = result;
    setRow(result);
  }, []);
  const acceptAttachment = (result: Draft, base: Draft) => {
    accept(result);
    if (current.current) {
      // Preserve edits made while the bounded upload/removal request was in flight.
      const next = {
        ...current.current,
        text:
          current.current.text === base.data.form.text
            ? result.data.form.text
            : current.current.text,
      };
      current.current = next;
      setForm(next);
      setDirty(JSON.stringify(next) !== JSON.stringify(result.data.form));
    }
  };
  useEffect(() => {
    let disposed = false;
    Promise.all([
      api<Options>("/project-creation-options"),
      initialId
        ? api<Draft>(`/project-drafts/${initialId}`)
        : Promise.resolve(null),
    ])
      .then(([configuration, draft]) => {
        if (disposed) return;
        setOptions(configuration);
        const initial: Form = draft?.data.form || {
          client_id: state.clients[0]?.id || "",
          title: "",
          text: sessionStorage.getItem("aiventra-project-brief") || "",
          step: 1,
          source_project_id: null,
          repository_id: null,
          technology: "",
          constraints: "",
          deadline: null,
          budget_micro: 5000000,
          preferred_lead: "GPT-6.1 Sol",
          lead_model_id: null,
          worker_mode: "automatic",
          worker_model_ids: [],
          overrides: {},
          planning_mode: "ai",
          review_before_planning: true,
        };
        sessionStorage.removeItem("aiventra-project-brief");
        current.current = initial;
        setForm(initial);
        if (draft) accept(draft);
      })
      .catch((exc: Error) => {
        if (!disposed) setError(exc.message);
      });
    return () => {
      disposed = true;
    };
    // The draft is loaded once; polling the surrounding workspace must not replace unsaved edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialId, accept]);
  const update = (changes: Partial<Form>) => {
    if (!current.current) return;
    current.current = { ...current.current, ...changes };
    setForm(current.current);
    setDirty(true);
  };
  const save = useCallback(async () => {
    const value = current.current;
    if (!value) throw new Error("Draft is loading");
    const existing = saved.current;
    if (
      existing &&
      JSON.stringify(existing.data.form) === JSON.stringify(value)
    )
      return existing;
    const request =
      retrySave.current ||
      (existing
        ? {
            path: `/project-drafts/${existing.id}`,
            body: {
              request_id: crypto.randomUUID(),
              version: existing.version,
              form: value,
            },
            method: "PATCH",
          }
        : {
            path: "/project-drafts",
            body: {
              request_id: crypto.randomUUID(),
              form: value,
            },
            method: "POST",
          });
    retrySave.current = request;
    const result = await api<Draft>(request.path, request.body, request.method);
    retrySave.current = null;
    accept(result);
    if (JSON.stringify(current.current) === JSON.stringify(result.data.form))
      setDirty(false);
    if (mounted.current)
      window.history.replaceState(
        {},
        "",
        `/?view=new-project&draft=${result.id}`,
      );
    return result;
  }, [accept]);
  const execute = useCallback((operation: () => Promise<unknown>) => {
    queued.current += 1;
    setSaving(true);
    const pending = chain.current.catch(() => undefined).then(operation);
    chain.current = pending;
    pending
      .catch((exc: Error) => setError(exc.message))
      .finally(() => {
        queued.current -= 1;
        if (!queued.current) setSaving(false);
      });
  }, []);
  useEffect(() => {
    if (!dirty || error || row?.status === "submitted") return;
    const timer = setTimeout(() => execute(save), 700);
    return () => clearTimeout(timer);
  }, [dirty, form, error, row?.status, execute, save]);
  useEffect(() => {
    mounted.current = true;
    const warn = (event: BeforeUnloadEvent) => {
      if (
        saved.current?.status !== "submitted" &&
        current.current &&
        JSON.stringify(current.current) !==
          JSON.stringify(saved.current?.data.form)
      )
        event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      mounted.current = false;
      window.removeEventListener("beforeunload", warn);
      if (
        current.current &&
        saved.current?.status !== "submitted" &&
        JSON.stringify(current.current) !==
          JSON.stringify(saved.current?.data.form)
      ) {
        chain.current = chain.current
          .catch(() => undefined)
          .then(save)
          .catch(() => undefined);
      }
    };
  }, [save]);
  useEffect(() => {
    if (row?.status !== "submitted") return;
    const timer = setInterval(
      () =>
        api<Draft>(`/project-drafts/${row.id}`)
          .then(accept)
          .catch((exc: Error) => setError(exc.message)),
      3000,
    );
    return () => clearInterval(timer);
  }, [row?.id, row?.status, accept]);
  const reload = async () => {
    if (!saved.current) {
      setError("");
      return;
    }
    const result = await api<Draft>(`/project-drafts/${saved.current.id}`);
    accept(result);
    current.current = result.data.form;
    setForm(result.data.form);
    setDirty(false);
    retrySave.current = null;
    setError("");
  };
  if (!form || !options)
    return error ? (
      <div className="alert error" role="alert">
        {error}
      </div>
    ) : (
      <Loading />
    );
  const submitted = row?.status === "submitted";
  const lead = options.models.find((model) => model.id === form.lead_model_id);
  const visibleModels = options.models.filter(
    (model) =>
      (!modelProvider || model.provider_id === modelProvider) &&
      (modelAvailability === "all" ||
        model.eligibility.allowed === (modelAvailability === "ready")) &&
      `${model.identifier} ${model.provider}`
        .toLowerCase()
        .includes(modelSearch.toLowerCase()),
  );
  const override = (scope: string, model: string) => {
    const overrides = { ...form.overrides };
    if (model) overrides[scope] = model;
    else delete overrides[scope];
    update({ overrides });
  };
  const modelControls = (
    <>
      <div className="form-grid">
        <label>
          Search AI models
          <input
            type="search"
            value={modelSearch}
            onChange={(e) => setModelSearch(e.target.value)}
          />
        </label>
        <label>
          AI provider
          <select
            aria-label="AI provider"
            value={modelProvider}
            onChange={(e) => setModelProvider(e.target.value)}
          >
            <option value="">All workspace providers</option>
            {options.providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.configured ? "" : " · not configured"}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Model availability
        <select
          aria-label="Model availability"
          value={modelAvailability}
          onChange={(e) => setModelAvailability(e.target.value)}
        >
          <option value="all">All registered / discovered</option>
          <option value="ready">Ready to use</option>
          <option value="blocked">Unavailable</option>
        </select>
      </label>
      <Button
        secondary
        disabled={saving}
        onClick={() =>
          execute(async () => {
            setRefreshStatus("Refreshing connected provider catalogs…");
            const failures: string[] = [];
            for (const provider of options.providers.filter(
              (p) => p.configured && p.enabled,
            )) {
              try {
                const result = await api<{ error_code: string }>(
                  `/providers/${provider.id}/discover`,
                  {},
                );
                if (result.error_code)
                  failures.push(`${provider.name}: ${result.error_code}`);
              } catch {
                failures.push(
                  `${provider.name}: discovery unavailable; retry in Settings`,
                );
              }
            }
            const updated = await api<Options>("/project-creation-options");
            setOptions(updated);
            setRefreshStatus(
              `${updated.models.length} registered models. ${failures.join(" · ") || "Catalog refresh finished."}`,
            );
          })
        }
      >
        Refresh model choices
      </Button>
      {refreshStatus && <p role="status">{refreshStatus}</p>}
      {!!options.models.length &&
        !options.models.some((model) => model.eligibility.allowed) && (
          <p>
            Models are available in your catalog, but none can currently run
            under ZERO_COST_ONLY.
          </p>
        )}
      {!options.models.length && (
        <p>
          {options.providers.some((p) => p.configured)
            ? "A provider is configured, but no models have been discovered. Refresh model choices or open Settings."
            : "No providers are connected yet. Open Settings to connect OpenAI, Grok or DeepSeek."}
          <Button secondary onClick={() => navigate("models")}>
            Connect AI Provider
          </Button>
        </p>
      )}
      <div className="control-note">
        <p>Preferred Lead AI: GPT-6.1 Sol — Not currently available.</p>
        {form.lead_model_id && (
          <Button secondary onClick={() => update({ lead_model_id: null })}>
            Keep preferred Lead AI without an alternate
          </Button>
        )}
      </div>
      {form.lead_model_id && !lead && (
        <p role="status">
          Saved unavailable registry reference: {form.lead_model_id}. It is
          preserved, but cannot authorize execution.
        </p>
      )}
      <ModelPicker
        label="Lead AI"
        models={visibleModels}
        value={form.lead_model_id || ""}
        onChange={(id) => update({ lead_model_id: id })}
      />
      <div className="control-note">
        <p>
          {lead
            ? `${lead.identifier}: ${lead.eligibility.reason}`
            : "GPT-6.1 Sol is saved as your preferred Lead AI. It cannot currently run under zero-cost mode. Select a registered alternate explicitly, save the draft, wait, or write a manual plan."}
        </p>
      </div>
      <label>
        Specialist allocation
        <select
          aria-label="Specialist allocation"
          value={form.worker_mode}
          onChange={(event) =>
            update({
              worker_mode: event.target.value as Form["worker_mode"],
              overrides:
                event.target.value === "automatic" ? {} : form.overrides,
            })
          }
        >
          <option value="automatic">Automatic · eligible models only</option>
          <option value="hybrid">Hybrid · automatic with my overrides</option>
          <option value="manual">
            Manual · assign every participating role
          </option>
        </select>
      </label>
      <fieldset>
        <legend>Optional worker pool</legend>
        <p className="muted">
          Registered models can be saved as preferences, including blocked
          models. Automatic execution uses only eligible models; every call
          still checks capabilities, budget and independent review.
        </p>
        <div className="model-picker-list">
          {visibleModels.length ? (
            visibleModels.map((model) => (
              <label className="checkbox-label" key={model.id}>
                <input
                  type="checkbox"
                  checked={form.worker_model_ids.includes(model.id)}
                  onChange={(event) =>
                    update({
                      worker_model_ids: event.target.checked
                        ? [...form.worker_model_ids, model.id]
                        : form.worker_model_ids.filter((id) => id !== model.id),
                      overrides: {},
                    })
                  }
                />
                <span>
                  {model.identifier} · {model.provider} ·{" "}
                  {model.eligibility.allowed
                    ? "Ready to use"
                    : "Blocked preference"}{" "}
                  · {model.capabilities.join(", ") || "Capabilities unknown"}
                  <small>{model.eligibility.reason}</small>
                </span>
              </label>
            ))
          ) : (
            <p>
              No models match. Registered blocked preferences remain available
              when filters are cleared; work waits for eligible models.
            </p>
          )}
        </div>
      </fieldset>
      {form.worker_mode !== "automatic" && (
        <details open>
          <summary>Role and department assignments</summary>
          <div className="wizard-grid">
            {[
              ...options.roles
                .filter(
                  (role) =>
                    [
                      "Business Analyst",
                      "CTO",
                      "Project Manager",
                      ...extraRoles,
                    ].includes(role) || !!form.overrides[`role:${role}`],
                )
                .map((role) => ({
                  key: `role:${role}`,
                  label: role,
                })),
              ...options.departments
                .filter(
                  (department) =>
                    extraDepartments.includes(department.id) ||
                    !!form.overrides[`department:${department.id}`],
                )
                .map((department) => ({
                  key: `department:${department.id}`,
                  label: `${department.name} department`,
                })),
            ].map((scope) => (
              <div key={scope.key}>
                <p>
                  {scope.label}:{" "}
                  {options.models.find(
                    (model) => model.id === form.overrides[scope.key],
                  )?.identifier ||
                    (form.overrides[scope.key]
                      ? "Saved unavailable reference"
                      : form.worker_mode === "manual"
                        ? "Unassigned · this role will wait"
                        : "Automatic")}
                </p>
                <ModelPicker
                  label={`${scope.label} model`}
                  value={form.overrides[scope.key] || ""}
                  onChange={(id) => override(scope.key, id)}
                  models={visibleModels.filter(
                    (model) =>
                      !form.worker_model_ids.length ||
                      form.worker_model_ids.includes(model.id),
                  )}
                />
                {form.overrides[scope.key] && (
                  <Button secondary onClick={() => override(scope.key, "")}>
                    Clear {scope.label} assignment
                  </Button>
                )}
              </div>
            ))}
          </div>
          <label>
            Add a participating role
            <select
              aria-label="Add a participating role"
              value=""
              onChange={(e) => setExtraRoles([...extraRoles, e.target.value])}
            >
              <option value="">Choose a role when required</option>
              {options.roles
                .filter(
                  (role) =>
                    ![
                      "Business Analyst",
                      "CTO",
                      "Project Manager",
                      ...extraRoles,
                    ].includes(role),
                )
                .map((role) => (
                  <option key={role}>{role}</option>
                ))}
            </select>
          </label>
          <label>
            Add a participating department
            <select
              aria-label="Add a participating department"
              value=""
              onChange={(event) =>
                setExtraDepartments([...extraDepartments, event.target.value])
              }
            >
              <option value="">Choose a department when required</option>
              {options.departments
                .filter(
                  (department) =>
                    !extraDepartments.includes(department.id) &&
                    !form.overrides[`department:${department.id}`],
                )
                .map((department) => (
                  <option key={department.id} value={department.id}>
                    {department.name}
                  </option>
                ))}
            </select>
          </label>
        </details>
      )}
    </>
  );
  return (
    <div className="project-wizard">
      <div className="wizard-toolbar">
        <span role="status">
          {saving
            ? "Saving…"
            : error
              ? "Changes need attention"
              : dirty
                ? "Unsaved changes"
                : row
                  ? `Saved · version ${row.version}`
                  : "New draft"}
        </span>
        <Button
          secondary
          disabled={saving || submitted || !form.client_id}
          onClick={() => execute(save)}
        >
          Save draft
        </Button>
      </div>
      {error && (
        <div className="alert error" role="alert">
          {error}
          <Button secondary disabled={saving} onClick={() => execute(reload)}>
            Reload saved draft
          </Button>
          {retrySave.current && (
            <Button
              secondary
              disabled={saving}
              onClick={() => {
                setError("");
                execute(save);
              }}
            >
              Retry interrupted save
            </Button>
          )}
          <p>Reload replaces local edits. Copy any unsaved text first.</p>
        </div>
      )}
      {!submitted ? (
        <>
          <nav className="wizard-steps" aria-label="Project creation steps">
            {["Describe", "Choose AI", "Review"].map((label, index) => (
              <button
                key={label}
                disabled={saving}
                aria-current={form.step === index + 1 ? "step" : undefined}
                className={form.step === index + 1 ? "selected" : ""}
                onClick={() => update({ step: index + 1 })}
              >
                <span>{index + 1}</span>
                {label}
              </button>
            ))}
          </nav>
          {form.step === 1 && (
            <Panel
              title="Tell us what you need"
              subtitle="Start with the outcome. You can refine the plan before approving it."
            >
              <div className="wizard-grid">
                <label>
                  Project name
                  <input
                    aria-label="Project name"
                    value={form.title}
                    maxLength={200}
                    onChange={(event) => update({ title: event.target.value })}
                  />
                </label>
                <label>
                  Client
                  <select
                    aria-label="Project client"
                    value={form.client_id}
                    onChange={(event) =>
                      update({
                        client_id: event.target.value,
                        source_project_id: null,
                        repository_id: null,
                      })
                    }
                  >
                    {state.clients.map((client) => (
                      <option key={client.id} value={client.id}>
                        {client.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {!state.clients.length && (
                <Button secondary onClick={() => navigate("crm")}>
                  Create a client
                </Button>
              )}
              <label>
                Requirements
                <textarea
                  aria-label="Project requirements"
                  rows={7}
                  maxLength={30000}
                  value={form.text}
                  onChange={(event) => update({ text: event.target.value })}
                  placeholder="Who is it for? What should it do? What would a successful result look like?"
                />
              </label>
              <label>
                Attach requirements
                <input
                  aria-label="Upload project requirements"
                  type="file"
                  accept=".txt,.md,.csv,.json,.docx,.pdf"
                  disabled={saving || !!error}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (!file) return;
                    execute(async () => {
                      const draft = await save();
                      const body = new FormData();
                      body.set("file", file);
                      body.set("version", String(draft.version));
                      body.set("request_id", crypto.randomUUID());
                      if (replaceAttachment)
                        body.set("replace_id", replaceAttachment);
                      const uploaded = await api<Draft>(
                        `/project-drafts/${draft.id}/attachments`,
                        body,
                      );
                      acceptAttachment(uploaded, draft);
                      setReplaceAttachment("");
                    });
                  }}
                />
              </label>
              <p className="muted">
                UTF-8 TXT, Markdown, CSV or valid JSON · 16 KB each. DOCX · 1 MB
                file / 64 KB extracted text. PDF · 1 MB / 50 pages, text only.
                Six files / 2 MB total. Scanned images need OCR and are
                unsupported.
              </p>
              {!!row?.data.attachments.length && (
                <label>
                  Upload action
                  <select
                    aria-label="Replace requirement attachment"
                    value={replaceAttachment}
                    disabled={saving || !!error}
                    onChange={(e) => setReplaceAttachment(e.target.value)}
                  >
                    <option value="">Add a new document</option>
                    {row.data.attachments.map((file) => (
                      <option key={file.id} value={file.id}>
                        Replace {file.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {row?.data.attachments.map((file) => (
                <div key={file.id}>
                  <p>
                    {file.name} · parsed and saved · {file.bytes} bytes
                    {file.page_count ? ` · ${file.page_count} pages` : ""}
                    {file.document_version
                      ? ` · version ${file.document_version}`
                      : ""}
                    {file.redacted ? " · sensitive content redacted" : ""}
                  </p>
                  {file.warnings?.map((warning) => (
                    <p className="muted" key={warning}>
                      {warning}
                    </p>
                  ))}
                  <details>
                    <summary>Document provenance</summary>
                    <p className="mono">
                      Source SHA-256:{" "}
                      {file.source_sha256 || "Historical text attachment"}
                    </p>
                    <p>
                      Private draft; supplied to assigned project agents after
                      submission. Content is untrusted data.
                    </p>
                  </details>
                  {file.format === "pdf" && (
                    <Button
                      secondary
                      disabled={saving || !!error}
                      onClick={() =>
                        execute(async () => {
                          const draft = await save();
                          const result = await api<Draft>(
                            `/project-drafts/${draft.id}/attachments/${file.id}/reprocess`,
                            {
                              version: draft.version,
                              request_id: crypto.randomUUID(),
                            },
                          );
                          acceptAttachment(result, draft);
                        })
                      }
                    >
                      Reprocess {file.name}
                    </Button>
                  )}
                  <Button
                    secondary
                    disabled={saving || !!error}
                    onClick={() =>
                      execute(async () => {
                        const draft = await save();
                        const result = await api<Draft>(
                          `/project-drafts/${draft.id}/attachments/${file.id}/remove`,
                          {
                            version: draft.version,
                            request_id: crypto.randomUUID(),
                          },
                        );
                        acceptAttachment(result, draft);
                        setReplaceAttachment("");
                      })
                    }
                  >
                    Remove {file.name}
                  </Button>
                </div>
              ))}
              <details>
                <summary>Reference project, repository and constraints</summary>
                <div className="wizard-grid">
                  <label>
                    Reference project
                    <select
                      aria-label="Reference project"
                      value={form.source_project_id || ""}
                      onChange={(event) =>
                        update({
                          source_project_id: event.target.value || null,
                          repository_id: null,
                        })
                      }
                    >
                      <option value="">New project</option>
                      {state.projects
                        .filter(
                          (project) => project.client_id === form.client_id,
                        )
                        .map((project) => (
                          <option key={project.id} value={project.id}>
                            {project.name}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Authorized repository
                    <select
                      aria-label="Authorized repository"
                      value={form.repository_id || ""}
                      onChange={(event) =>
                        update({ repository_id: event.target.value || null })
                      }
                    >
                      <option value="">No repository reference</option>
                      {state.repositories
                        .filter(
                          (repo) => repo.project_id === form.source_project_id,
                        )
                        .map((repo) => (
                          <option key={repo.id} value={repo.id}>
                            {repo.name} · {repo.baseline_commit.slice(0, 8)}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Preferred technology
                    <input
                      value={form.technology}
                      maxLength={1000}
                      onChange={(event) =>
                        update({ technology: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    Deadline
                    <input
                      type="date"
                      value={form.deadline || ""}
                      onChange={(event) =>
                        update({ deadline: event.target.value || null })
                      }
                    />
                  </label>
                  <label>
                    Budget limit (USD)
                    <input
                      type="number"
                      min="0"
                      max="1000000"
                      step="0.01"
                      value={form.budget_micro / 1000000}
                      onChange={(event) =>
                        update({
                          budget_micro: Math.round(
                            Number(event.target.value) * 1000000,
                          ),
                        })
                      }
                    />
                  </label>
                </div>
                <label>
                  Constraints
                  <textarea
                    value={form.constraints}
                    maxLength={4000}
                    onChange={(event) =>
                      update({ constraints: event.target.value })
                    }
                  />
                </label>
                <p className="muted">
                  A repository reference authorizes no checkout or code
                  execution. Engineering approvals remain separate.
                </p>
              </details>
            </Panel>
          )}
          {form.step === 2 && (
            <Panel
              title="Choose your Lead AI"
              subtitle="Your Lead coordinates the plan; specialists use the existing routing and safety controls."
            >
              {modelControls}
            </Panel>
          )}
          {form.step === 3 && (
            <Panel
              title="Review your project"
              subtitle="Submitting requests analysis. It does not authorize engineering, publication or delivery."
            >
              <h3>{form.title || "Untitled project"}</h3>
              <p className="wizard-brief">{form.text}</p>
              <p>
                Lead: {lead?.identifier || "GPT-6.1 Sol · unavailable favorite"}{" "}
                · Specialists: {form.worker_mode}
              </p>
              <p>
                {row?.data.attachments.length || 0} saved documents · Budget
                limit ${(form.budget_micro / 1000000).toFixed(2)}
              </p>
              <label>
                Planning path
                <select
                  aria-label="Planning path"
                  value={form.planning_mode}
                  onChange={(event) =>
                    update({
                      planning_mode: event.target
                        .value as Form["planning_mode"],
                    })
                  }
                >
                  <option value="ai">
                    AI analysis · wait if no eligible Lead
                  </option>
                  <option value="manual">
                    Owner-authored plan · no AI inference
                  </option>
                </select>
              </label>
              <p className="muted">
                Exact proposal, workforce, code changes, PR publication,
                delivery release and closure each retain their existing approval
                gates.
              </p>
              <Button
                disabled={
                  saving ||
                  !!error ||
                  form.title.trim().length < 3 ||
                  form.text.trim().length < 20 ||
                  !form.client_id
                }
                onClick={() =>
                  execute(async () => {
                    const draft = await save();
                    accept(
                      await api<Draft>(`/project-drafts/${draft.id}/submit`, {
                        request_id: crypto.randomUUID(),
                        version: draft.version,
                      }),
                    );
                    await refresh();
                  })
                }
              >
                Submit requirements
              </Button>
            </Panel>
          )}
          <div className="wizard-toolbar">
            <Button
              secondary
              disabled={saving || form.step === 1}
              onClick={() => update({ step: form.step - 1 })}
            >
              Back
            </Button>
            {form.step < 3 && (
              <Button
                disabled={saving}
                onClick={() => update({ step: form.step + 1 })}
              >
                Continue
              </Button>
            )}
          </div>
        </>
      ) : (
        <>
          {row.data.refinement && (
            <RequirementsReview
              draftId={row.id}
              onChanged={async () => {
                accept(await api<Draft>(`/project-drafts/${row.id}`));
                await refresh();
              }}
            />
          )}
          <ExecutionEvidence key={row.id} draftId={row.id} />
          <Panel
            title={
              row.approved_project_id
                ? "Your project is approved"
                : row.data.manual_proposal_id
                  ? "Your plan is ready for review"
                  : "Your requirements are saved"
            }
            subtitle="Follow the actual workflow below."
          >
            <Badge>
              {row.approved_project_id
                ? "approved"
                : row.data.manual_proposal_id
                  ? "awaiting owner approval"
                  : row.workflow?.status || row.status}
            </Badge>
            <p>
              {row.approved_project_id
                ? "The exact proposal is approved. Workforce, engineering and delivery keep their separate approval gates."
                : row.data.manual_proposal_id
                  ? "Your owner-authored proposal is saved. AI analysis has stopped; review and approve the exact scope before work begins."
                  : row.workflow?.last_error ||
                    (row.workflow?.status === "paused"
                      ? row.data.refinement && !row.data.refinement.approval_id
                        ? "Review and approve your requirements before architecture planning."
                        : "Waiting for your owner-authored plan."
                      : "Analysis progresses only when an eligible Lead AI and specialist models are available.")}
            </p>
            {!row.data.manual_proposal_id && !row.approved_project_id && (
              <p>{row.lead_status.reason}</p>
            )}
            {row.approved_project_id ? (
              <Button
                onClick={() => navigate(`projects:${row.approved_project_id}`)}
              >
                Open project workspace
              </Button>
            ) : (
              <Button
                secondary
                onClick={() => navigate(`proposals:${row.data.requirement_id}`)}
              >
                Review requirements and approvals
              </Button>
            )}
            {row.workflow?.status === "waiting_for_free_provider" && (
              <>
                <Button
                  secondary
                  onClick={() => setEditingModels(!editingModels)}
                >
                  Choose an alternate Lead AI
                </Button>
                <Button
                  secondary
                  disabled={saving}
                  onClick={() =>
                    execute(async () => {
                      await api(
                        `/workflows/${row.workflow!.id}/resume-free`,
                        {},
                      );
                      accept(await api<Draft>(`/project-drafts/${row.id}`));
                    })
                  }
                >
                  Verify and resume
                </Button>
              </>
            )}
          </Panel>
          {editingModels && (
            <Panel
              title="Explicit model selection"
              subtitle="Available only before inference. Requirements and approval scope remain fixed."
            >
              {modelControls}
              <Button
                disabled={saving}
                onClick={() =>
                  execute(async () => {
                    accept(
                      await api<Draft>(`/project-drafts/${row.id}/models`, {
                        request_id: crypto.randomUUID(),
                        version: saved.current!.version,
                        form: current.current,
                      }),
                    );
                    setDirty(false);
                    setEditingModels(false);
                  })
                }
              >
                Save model selection
              </Button>
            </Panel>
          )}
          {!row.data.manual_proposal_id &&
            !row.approved_project_id &&
            (!row.data.refinement || row.data.refinement.approval_id) &&
            ["paused", "waiting_for_free_provider"].includes(
              row.workflow?.status || "",
            ) && (
              <Panel
                title="Write a manual plan"
                subtitle="Owner-authored content. No AI analysis, review or execution is implied."
              >
                <label>
                  Architecture
                  <textarea
                    aria-label="Manual architecture"
                    rows={4}
                    value={architecture}
                    onChange={(event) => setArchitecture(event.target.value)}
                  />
                </label>
                <label>
                  Milestones · one per line
                  <textarea
                    aria-label="Manual milestones"
                    value={milestones}
                    onChange={(event) => setMilestones(event.target.value)}
                  />
                </label>
                <label>
                  Acceptance criteria · one per line
                  <textarea
                    aria-label="Manual acceptance criteria"
                    value={criteria}
                    onChange={(event) => setCriteria(event.target.value)}
                  />
                </label>
                <Button
                  disabled={
                    saving ||
                    architecture.trim().length < 20 ||
                    !milestones.trim() ||
                    !criteria.trim()
                  }
                  onClick={() =>
                    execute(async () => {
                      accept(
                        await api<Draft>(
                          `/project-drafts/${row.id}/manual-plan`,
                          {
                            request_id: crypto.randomUUID(),
                            version: saved.current!.version,
                            architecture,
                            milestones: milestones
                              .split("\n")
                              .filter((line) => line.trim()),
                            criteria: criteria
                              .split("\n")
                              .filter((line) => line.trim()),
                          },
                        ),
                      );
                      await refresh();
                    })
                  }
                >
                  Save owner-authored proposal
                </Button>
              </Panel>
            )}
        </>
      )}
    </div>
  );
}
