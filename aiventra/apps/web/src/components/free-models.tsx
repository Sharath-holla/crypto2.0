"use client";

import { api } from "@/lib/api";
import { Badge, Button, Panel, useApp } from "./common";

export function FreeModels() {
  const { state, run, busy } = useApp();
  const waiting = state.workflows.filter(
    (workflow) => workflow.status === "waiting_for_free_provider",
  );
  return (
    <Panel
      title="Zero-cost inference policy"
      subtitle="Remote models remain blocked until provider-enforced zero billing can be verified. Catalog access and credentials do not prove free inference."
    >
      <Badge>{state.runtime.ai_spending_mode}</Badge>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Eligibility</th>
              <th>Evidence</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {state.runtime.inference_eligibility.map((entry) => (
              <tr key={entry.model_id}>
                <td>
                  {
                    state.models.find((model) => model.id === entry.model_id)
                      ?.identifier
                  }
                </td>
                <td>
                  <Badge>{entry.state}</Badge>
                </td>
                <td>{entry.reason}</td>
                <td>
                  {entry.local_candidate && (
                    <Button
                      secondary
                      disabled={busy}
                      onClick={() =>
                        run(
                          () =>
                            api(`/models/${entry.model_id}/verify-local`, {}),
                          "Local metadata checked. No inference or model download requested.",
                        )
                      }
                    >
                      Verify installed model
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {waiting.length > 0 && <h3>Saved work waiting for a free model</h3>}
      {waiting.map((workflow) => (
        <div
          key={workflow.id}
          className="notification-row"
          data-workflow-id={workflow.id}
        >
          <div>
            <strong>
              {workflow.kind} · step {workflow.step}
            </strong>
            <p>{workflow.last_error}</p>
          </div>
          <Button
            secondary
            disabled={busy}
            onClick={() =>
              run(
                () => api(`/workflows/${workflow.id}/resume-free`, {}),
                "Owner authorized resumption. The worker will recheck eligibility.",
              )
            }
          >
            Resume saved work
          </Button>
        </div>
      ))}
    </Panel>
  );
}
