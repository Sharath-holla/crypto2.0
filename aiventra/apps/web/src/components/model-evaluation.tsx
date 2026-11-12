"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Button, useApp } from "./common";

export function ModelEvaluation({ runId }: { runId: string }) {
  const { state, run, busy } = useApp();
  const [score, setScore] = useState("70");
  const [note, setNote] = useState("");
  const record = state.runs.find((r) => r.id === runId);
  const evaluation = state.model_evaluations.find((e) => e.run_id === runId);
  const taskClass =
    state.agent_work.find((w) => w.workflow_id === record?.workflow_id)?.kind ||
    state.workflows.find((w) => w.id === record?.workflow_id)?.kind;
  if (evaluation)
    return (
      <p className="muted">
        Owner evaluation: {evaluation.score}/100 · {evaluation.task_class} ·{" "}
        {evaluation.note}
      </p>
    );
  if (
    record?.status !== "succeeded" ||
    record.cost_basis === "mock_no_charge" ||
    !taskClass
  )
    return null;
  return (
    <details>
      <summary>Evaluate this recorded result</summary>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          run(
            () =>
              api(`/model-runs/${runId}/evaluate`, {
                score: Number(score),
                note,
                task_class: taskClass,
              }),
            "Owner evaluation recorded with run provenance.",
          );
        }}
      >
        <label>
          Owner quality score
          <input
            type="number"
            min="0"
            max="100"
            required
            value={score}
            onChange={(e) => setScore(e.target.value)}
          />
        </label>
        <label>
          Evaluation evidence
          <textarea
            maxLength={2000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <p className="muted">
          This is a human evaluation for {taskClass}. Its average can restrict
          future routing. It does not certify tests, deployment or an automatic
          benchmark.
        </p>
        <Button type="submit" disabled={busy}>
          Record quality evaluation
        </Button>
      </form>
    </details>
  );
}
