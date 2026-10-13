"use client";
import { useState } from "react";
import { api, date } from "@/lib/api";
import { Badge, Button } from "./common";

type LocalStatus = {
  reachable: boolean;
  version: string | null;
  checked_at: number;
  available_memory_mb: number | null;
  minimum_available_memory_mb: number;
  resource_warning: string;
  context_limit: number;
  keep_alive_seconds: number;
  thinking: boolean;
  error: string;
  installed_models: { name: string; digest?: string; size?: number }[];
  loaded_models: { name: string; size?: number; size_vram?: number }[];
};

export function LocalAiStatus({ providerId }: { providerId: string }) {
  const [value, setValue] = useState<LocalStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  async function check() {
    setLoading(true);
    setError("");
    try {
      setValue(await api<LocalStatus>(`/providers/${providerId}/local-status`));
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setLoading(false);
    }
  }
  return (
    <section aria-label="Local AI Models" className="control-note">
      <div>
        <h4>Local AI Models</h4>
        <p>
          Inspect the registered loopback server. This check sends no inference
          and installs nothing.
        </p>
        {error && <p role="alert">Local status check failed: {error}</p>}
        {value && (
          <>
            <Badge>
              {value.reachable
                ? "Local server reachable"
                : "Local server unavailable"}
            </Badge>
            <p>
              Ollama API version: {value.version || "unverified"}. Checked{" "}
              {date(value.checked_at)}.
            </p>
            {value.error && <p role="alert">{value.error}</p>}
            <p>
              Available host RAM: {value.available_memory_mb ?? "unknown"} MiB.
              Inference memory floor:{" "}
              {value.minimum_available_memory_mb || "not configured"} MiB.
            </p>
            <p>
              Configured context limit: {value.context_limit}. Keep alive:{" "}
              {value.keep_alive_seconds}s. Thinking:{" "}
              {value.thinking ? "enabled" : "disabled"}.
            </p>
            {value.resource_warning && (
              <p role="alert">{value.resource_warning}</p>
            )}
            {!value.installed_models.length && (
              <p>No installed local models were observed.</p>
            )}
            {value.installed_models.map((model) => (
              <div key={model.name}>
                <strong>{model.name} · Ollama · Local</strong>
                <p>
                  {model.size
                    ? `${(model.size / 1_000_000).toFixed(1)} MB`
                    : "Size unverified"}
                </p>
                <details>
                  <summary>Installed model digest</summary>
                  <code>{model.digest || "unverified"}</code>
                </details>
              </div>
            ))}
            <p>{value.loaded_models.length} models currently loaded.</p>
            {value.loaded_models.map((model) => (
              <p key={model.name}>
                {model.name}:{" "}
                {typeof model.size_vram === "number"
                  ? `${(model.size_vram / 1_048_576).toFixed(0)} MiB reported VRAM allocation`
                  : "GPU allocation unverified"}
                . Allocation does not establish GPU utilization.
              </p>
            ))}
          </>
        )}
        <Button secondary disabled={loading} onClick={() => void check()}>
          {loading ? "Checking local server…" : "Check local server"}
        </Button>
      </div>
    </section>
  );
}
