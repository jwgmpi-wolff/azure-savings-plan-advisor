# Security and privacy

## Identity and authorization

- Production API requests are protected by App Service Authentication using
  Microsoft Entra ID. `infra/main.bicep` configures an explicit API audience;
  `/api/health` is the only excluded route and returns no customer data.
- Connected recommendations use an on-behalf-of token exchange. Azure
  Cost Management therefore evaluates the signed-in user's delegated access,
  not a broad Function App managed identity.
- The Function App's user-assigned managed identity is used for Function
  storage, deployment storage, Application Insights, and Key Vault secret
  resolution only.
- The template does not grant Cost Management roles. Grant users only the
  minimum read access needed at the customer-approved scope.
- Local connected development uses `DefaultAzureCredential` only when
  `AZURE_AUTH_MODE=developer` is explicitly selected in local settings.

## Data handling

- Never commit client secrets, Function keys, access tokens, customer billing
  identifiers, or exported customer usage data.
- Store the API app registration secret in Azure Key Vault and deploy its
  versionless secret URI as an App Service Key Vault reference.
- Request bodies, authorization headers, CSV rows, and Cost Management
  payloads are not written to logs. Events contain only an operation marker and
  an exception class when needed for troubleshooting.
- Connected responses contain only a documented allowlist of recommendation
  fields. Customer-specific Azure resource identifiers are not returned;
  recommendation references are one-way shortened hashes.
- The health endpoint reports only service status.
- What-if requests are validated before calculation. CSV is size limited and
  rejects invalid, nonnumeric, negative, unordered, duplicate, or
  non-consecutive hourly data rather than repairing it.

## Operational controls

- The Bicep template uses HTTPS-only access, TLS 1.2 minimum, disabled FTP,
  restricted CORS origins, non-public storage containers, storage data-plane
  identities, and Key Vault Secrets User at the specific OBO client-secret
  scope.
- Do not use wildcard CORS or Function keys as a production authentication
  substitute.
- Monitor Function failures and Azure dependency failures through
  workspace-based Application Insights. Keep telemetry free of raw requests
  and financial records.
- Review Key Vault reference resolution and managed-identity role propagation
  before enabling customer traffic.
- Validate deployment tenant, subscription, region, resource group, and
  principal before infrastructure changes. Review and approve role assignments.
- The API is decision support only and never performs Savings Plan purchases,
  modifications, exchanges, cancellations, or renewals.

## Windows desktop app

- The Windows app uses the Azure CLI's interactive user sign-in for direct,
  read-only Azure Advisor and Cost Management access. It does not use a managed
  identity, client secret, or service-principal fallback. Tokens stay in memory
  and are not included in app exports, logs, or configuration.
- Tenant and subscription membership are validated before collection. Requests
  use an explicitly tenant-bound user credential, not a global subscription
  selection. Switching context invalidates results and exports. The Azure CLI's
  shared credential cache is managed by Azure CLI; disconnecting the app does
  not sign out other CLI users or sessions.
  Switching Azure accounts is an explicit action that clears the app's selected
  tenant/subscriptions and starts normal Azure CLI account-wide authorization
  without a `--tenant` override. No alias is passed as a specific directory.
  Scoped sign-in still honors the selected tenant and never silently
  falls back to another directory or account. A cached token in one tenant is
  not treated as proof of membership in a different tenant. Tenant-mismatch
  failures surface only recognized `AADSTS` codes and fixed guidance, not raw
  authentication descriptions containing personal or directory identifiers.
  `AADSTS90002` is reported as tenant not found rather than cancellation,
  account membership rejection or Conditional Access denial.
- Multi-subscription collection validates every selection against the selected
  tenant before collecting. Each subscription retains independent Single-scope
  recommendations and source coverage; failed collections remain explicitly
  partial and do not erase other subscriptions' results.
- Desktop CLI login, discovery and token retrieval use captured output,
  disconnected standard input, timeouts and hidden Windows process startup.
  Browser authentication and MFA are not suppressed. Token failures return
  fixed guidance rather than CLI output; token expiry uses the CLI's UTC epoch.
  Windows MSI installations invoke the Azure CLI's Python runtime directly
  rather than leaving a shell-owned login child behind. Interactive login
  waits are cancellable, with a five-minute deadline; cancellation, timeout and
  closing the app kill and reap only the owned CLI process. Closing a pending
  login waits for cleanup before destroying the window. Sign-in remains in a
  background worker; the UI displays elapsed time and browser/collection phases.
  Cancellation does not undo authentication that already reached the shared CLI
  cache, nor close a user-owned browser. The app does not silently clear credentials.
- ARM pagination stays on the same HTTPS host and collection path. Redirects,
  loops, and cross-scope continuation links are rejected before forwarding tokens.
- The app does not send telemetry or upload CSV files. Offline CSV modes remain
  separate from live recommendations, with no silent fallback on Azure failures.
- The compute-hours modeler runs locally with explicit user-entered financial
  assumptions; it does not retrieve pricing or claim live Azure validation.
  Modeler is now the initial desktop mode. Running a modeler report calls a
  local Ollama chat model, not GitHub or Microsoft Copilot, and displays the
  actual AI explanation separately from calculated reference figures.
  The UI discloses the local connection. Only allowlisted model inputs and
  calculated financial figures go to `http://127.0.0.1:11434`; Azure identifiers,
  CSVs, inventory and arbitrary report text are excluded. There are no tools,
  MCP servers, file access, cloud credentials or inherited project instructions.
  Cloud-tagged models and metadata identifying a remote model are rejected;
  local model metadata and chat capability are required before figures are sent.
  HTTP proxies, netrc credential discovery and redirects are disabled.
  No model is downloaded and no service is started automatically by the app.
  Trust and secure the local service; follow organization policy for local
  weights, service logs and exports. Keep Ollama restricted to trusted local use.
  Inference uses a 150-second read timeout and a short connection timeout;
  local-model verification has a separate shorter timeout.
  Errors do not expose raw HTTP diagnostics or substitute deterministic guidance
  for AI output. Empty, incomplete, truncated, tool-call and unexpected-model
  replies are rejected. Stale responses are discarded when inputs change.
  AI responses and exports use the shared credential redactor and record the
  provider, model and timestamps. AI text can be incorrect and must be checked
  against the calculated references.
  Input changes clear in-app analysis, not saved exports or local service logs.
  Closing the app does not terminate a shared Ollama service. No approved
  Microsoft agent connection is claimed without its actual configuration.
- Input files are read locally; results are written only to the JSON export
  location selected by the user. Protect these files as financial data.
- Connected exports intentionally include selected tenant/subscription context
  for provenance and allowlisted Advisor descriptions, which may contain workload
  details. Review/redact these before sharing. Raw Azure responses are not exported.
- The dashboard, JSON and report exports apply a shared credential-pattern
  redaction policy. PDF, PowerPoint and CSV share normalized recommendation
  records, including source coverage, missing-value semantics and limitations.
  This is not a guarantee of anonymization; customer workload descriptions and
  selected scope identifiers are intentionally retained as evidence.
- CSV text cells beginning with spreadsheet formula markers are escaped.
  Every export is disabled when context/assumptions change. PDF/PPTX/CSV writes
  use a temporary file and atomic replacement to preserve a previous report on
  generation failure; no external export service is used.
- The per-user installer bundles Python and dependencies and does not require
  administrator rights. Releases include a SHA-256 checksum.
- Installers are currently unsigned. Code signing and organizational deployment
  approval are separate requirements; do not bypass endpoint security policies.
- Uninstall removes application files, not user-selected input or export files.

Report security concerns privately to the repository owner or through the
repository's private vulnerability reporting process. Do not disclose
vulnerabilities in public issues.
