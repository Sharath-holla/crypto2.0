"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Repository } from "@/lib/types";
import { Button, Panel, Pretty, useApp } from "./common";
import { RepositoryCheckout } from "./repository-checkout";

export function RepositoryImport({ projectId }: { projectId: string }) {
  const { run, busy, state } = useApp();
  const [configuration, setConfiguration] = useState<{
    credential_configured: boolean;
    repositories: string[];
  } | null>(null);
  const [repository, setRepository] = useState("");
  const [branch, setBranch] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<Repository | null>(null);
  useEffect(() => {
    api<{ credential_configured: boolean; repositories: string[] }>(
      "/operations/github",
    )
      .then(setConfiguration)
      .catch((e: Error) => setError(e.message));
  }, []);
  const imports = state.repositories.filter(
    (row) => row.project_id === projectId && row.report.remote_metadata_only,
  );
  return (
    <Panel
      title="Read-only GitHub analysis"
      subtitle="Inspect an authorized repository and branch without checking out or executing its code."
    >
      {error && <p role="alert">{error}</p>}
      {!configuration?.credential_configured && (
        <p>
          A scoped GitHub connector credential is required. Configure it on the
          server; never put credentials in this form.
        </p>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          run(async () => {
            const value = await api<Repository>(
              `/projects/${projectId}/github-import`,
              {
                request_id: crypto.randomUUID(),
                repository,
                branch: branch || null,
              },
            );
            setResult(value);
          }, "Read-only repository findings saved. Coding still requires a managed checkout and separate approval.");
        }}
      >
        <label>
          Authorized GitHub repository
          <input
            aria-label="GitHub import repository"
            list="authorized-import-repos"
            value={repository}
            onChange={(e) => setRepository(e.target.value)}
            placeholder="https://github.com/owner/repository"
            required
          />
        </label>
        <datalist id="authorized-import-repos">
          {configuration?.repositories.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <label>
          Branch (empty uses the actual default)
          <input
            aria-label="GitHub import branch"
            list="import-branches"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
          />
        </label>
        <datalist id="import-branches">
          {Array.isArray(result?.report.branches) &&
            result.report.branches
              .filter((v): v is string => typeof v === "string")
              .map((name) => <option key={name} value={name} />)}
        </datalist>
        <Button
          type="submit"
          disabled={
            busy ||
            !configuration?.credential_configured ||
            !configuration.repositories.length
          }
        >
          Analyze authorized GitHub repository
        </Button>
      </form>
      {imports.map((row) => (
        <details key={row.id}>
          <summary>{row.name} · read-only findings</summary>
          <p>Commit: {row.baseline_commit}</p>
          <Pretty value={row.report} />
          <RepositoryCheckout repositoryId={row.id} />
        </details>
      ))}
      {result && !imports.some((row) => row.id === result.id) && (
        <Pretty value={result.report} />
      )}
    </Panel>
  );
}
