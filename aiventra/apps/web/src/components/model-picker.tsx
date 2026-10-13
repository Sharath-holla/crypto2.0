"use client";
import { useId } from "react";
import type { CatalogModel } from "./model-catalog";

export function ModelPicker({
  label,
  models,
  value,
  onChange,
}: {
  label: string;
  models: CatalogModel[];
  value: string;
  onChange: (id: string) => void;
}) {
  const name = useId();
  const providers = [...new Set(models.map((m) => m.provider_id))];
  return (
    <fieldset className="model-picker" aria-label={label}>
      <legend>{label}</legend>
      <div
        className="model-picker-list"
        tabIndex={0}
        aria-label={`${label} results`}
      >
        {providers.map((id) => (
          <div key={id}>
            <h4>{models.find((m) => m.provider_id === id)!.provider}</h4>
            {models
              .filter((m) => m.provider_id === id)
              .map((model) => (
                <label key={model.id} className="model-picker-row">
                  <input
                    type="radio"
                    name={name}
                    aria-label={`${label}: ${model.identifier}`}
                    value={model.id}
                    checked={value === model.id}
                    onChange={() => onChange(model.id)}
                  />
                  <span>
                    <strong>
                      {model.identifier === "qwen3:0.6b"
                        ? "Qwen3 0.6B"
                        : model.identifier}
                    </strong>
                    <small>
                      {model.provider} · {model.kind === "ollama" && "Local · "}
                      {model.eligibility.allowed
                        ? "Ready to use"
                        : "Unavailable"}
                    </small>
                    {model.identifier === "qwen3:0.6b" && (
                      <small>
                        {model.identifier} · Small-model capability must be
                        measured; no production QA qualification is implied.
                      </small>
                    )}
                    <small>
                      {model.capabilities.join(", ") ||
                        "Capabilities unverified"}{" "}
                      · {model.eligibility.reason}
                    </small>
                  </span>
                </label>
              ))}
          </div>
        ))}
        {!models.length && <p>No models match these filters.</p>}
      </div>
    </fieldset>
  );
}
