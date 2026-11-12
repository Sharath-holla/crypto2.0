# Security and authorization model

The initial threat model is a trusted human owner operating a private local service, with untrusted client/repository/model content. The current installation is not certified for hostile public multi-tenant use.

Local users authenticate with Argon2 and JWTs bound to persisted expiring/revocable sessions. Server logout revokes the current session before the browser proxy clears its HttpOnly SameSite cookie. Login counters are atomic database records; the trusted-proxy source integration and operational retention remain pending. The proxy validates write origins. Provider credentials stay in the server environment. Production requires configured OIDC issuer/audience/JWKS and pre-provisioned subject-to-user membership. Browser OIDC authorization-code login and upstream logout/session management remain pending.

The server resolves tenant membership from the authenticated user. Agent output cannot create credentials, grant permissions, approve costs or approve deployments. Tools check organization pause, employee enablement, project state and allowed operation. CEO instances cannot receive code-authoring or test-execution permissions. Monitoring reports directly to the owner and its auditing is not an agent tool.

Proposal approval binds exact content hash, revision, selected alternative, owner and expiry. Material requirement changes supersede proposals and pause related projects. Repository changes need a distinct approved task payload. Cloud, production deployment, outreach, trading and transfer actions have no executable live connector and are rejected.

Generated code runs only through a separate Docker worker with fixed test commands, pre-pulled allowlisted images, no network, read-only mount/root filesystem, non-root UID, dropped capabilities, no-new-privileges, memory/CPU/PID/output/time limits and no provider credentials. Docker alone does not establish hostile-code containment. Hardened dedicated VM/microVM runners, sandbox attestation and per-project credentials are required for production.

Local repository registration is restricted under REPOSITORY_ROOT. Secret files, symlinks/junctions and executable Git filters are rejected. Modification happens in isolated worktrees after approval. Existing uncommitted work is never reset. Review actual Git configuration and repository trust before enabling execution.

Untrusted data is explicitly delimited in prompts and never authorizes tool privileges. Structured model outputs are validated. Redaction covers configured secrets, labeled key material, common token formats and PEM private keys. Redaction cannot discover every possible secret or unlabeled wallet seed; use a vault, approved inputs and a DLP layer. Do not submit private keys or seed phrases at all.

Published evidence fetches only explicitly allowlisted HTTPS hosts, without redirects, ambient proxies or arbitrary userinfo. An egress firewall and DNS/IP pinning are required to defend against DNS rebinding in hostile deployments. Retrieved content cannot be treated as verified numerical pricing simply because it was downloaded.

Audit database triggers forbid historical mutation through ordinary SQL. Hash verification checks chain consistency. External anchoring, independent retention, operational security review and adversarial tests remain required. Backup private `.env`, database and artifact data with encryption and restricted access; never publish them.
