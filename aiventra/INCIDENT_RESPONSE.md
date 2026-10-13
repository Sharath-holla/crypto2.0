# Incident response procedure and implementation limits

If a credential is disclosed, revoke it at the provider and replace it privately. Do not copy it into repository files, prompts, logs or issue reports. Revoke stored provider credentials through the authenticated owner control; environment fallback must be removed separately. Preserve relevant append-only audit evidence without publishing client data.

For suspected unauthorized execution, pause the company and affected workflows, revoke sessions/credentials as appropriate, and isolate the dedicated runner host. Preserve uncertain provider/runner outcomes for reconciliation. Never assume cancellation proves no charge or that an interrupted job did not execute. Review exact approvals, lease tokens, diffs and recorded usage before owner-authorized recovery.

Existing controls provide pause, cancellation, session revocation, write-only vault storage, append-only audit and notifications. Independent incident triage, external log anchoring, managed key rotation, alerts/on-call automation and forensic tooling are not implemented. This document is an operational procedure, not a claim of automated incident-response readiness.
