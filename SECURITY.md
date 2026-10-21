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
- Multi-subscription collection validates every selection against the selected
  tenant before collecting. Each subscription retains independent Single-scope
  recommendations and source coverage; failed collections remain explicitly
  partial and do not erase other subscriptions' results.
- Desktop CLI login, discovery and token retrieval use captured output,
  disconnected standard input, timeouts and hidden Windows process startup.
  Browser authentication and MFA are not suppressed. Token failures return
  fixed guidance rather than CLI output; token expiry uses the CLI's UTC epoch.
- ARM pagination stays on the same HTTPS host and collection path. Redirects,
  loops, and cross-scope continuation links are rejected before forwarding tokens.
- The app does not send telemetry or upload CSV files. Offline CSV modes remain
  separate from live recommendations, with no silent fallback on Azure failures.
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
