# Azure Savings Plan Advisor

**Version 0.9.0: direct local AI, no sign-in required.** The Windows app starts
in **modeler** mode, calculates break-even reference figures, and connects to
**Ollama on this PC** for an actual AI-generated explanation inside the app.
The default model is **`llama3.1:8b`**. No GitHub/Azure login, API key, cloud
usage quota, CSV or clipboard handoff is needed for this workflow.
This is **local AI, not Microsoft or GitHub Copilot**. Ollama and a suitable
local model must be installed separately; see [local AI setup](#direct-local-ai-analysis).

**New PC without Ollama:** The app can calculate and export the financial
reference figures, but **cannot generate an AI explanation** until Ollama and
a local chat model are installed and running. The Windows installer is not a
self-contained AI installation and has **no cloud AI fallback**. Windows
Copilot being installed or licensed does not configure an inference endpoint
for this app.

**Get the current version:** [Build the 0.9.0 Windows installer](#build-the-windows-installer-from-source)
or [run from source](#direct-local-ai-analysis). The build creates
`dist\installer\AzureSavingsPlanAdvisor-0.9.0-Setup-x64.exe` and its checksum.
The 0.9.0 installer has not been published at the historical download links below.

**Legacy Windows download (0.7.2; no local AI):** [Get the older Windows x64 app installer](downloads/windows/AzureSavingsPlanAdvisor-0.7.2-Setup-x64.exe).
Open the file and select **Download raw file** on GitHub, or run it from your
local clone. [Verify its SHA-256 checksum](downloads/windows/SHA256SUMS.txt).
For API development, see [prerequisite installers](#windows-installers)
and [local development](#local-development).

The desktop separates tested financial arithmetic from the AI explanation:

```text
Windows app -> deterministic planning model -> break-even figures and charts
            -> local Ollama chat model     -> in-app AI explanation
```

Azure sign-in is needed **only** for optional **connected** mode, which reads
authoritative Azure recommendations. Local AI does not retrieve or validate live
Azure prices, eligibility or recommendations.

A separate Copilot Studio-ready planning API backed by a Python Azure Function
is also included. Its deployment path is independent of the desktop's local AI:

```text
User -> Copilot Studio -> Entra-authenticated REST API -> Azure Function
                                                    -> Cost Management API
```

<!-- project-downloads:start -->
## APK and installer downloads

Every available project package is indexed below, including older versions. Prefer the newest stable version for your platform and architecture. Debug APKs and prereleases are labeled; archives are not necessarily standalone installers.

Downloads hosted in this private repository require signing in to GitHub with repository access. They are not anonymous public downloads.

### Release downloads: all published versions

| Version / source | Package | Download |
| --- | --- | --- |
| v0.7.2 | Windows installer | [AzureSavingsPlanAdvisor-0.7.2-Setup-x64.exe](https://github.com/jerrywolff_microsoft/azure-savings-plan-advisor/releases/download/v0.7.2/AzureSavingsPlanAdvisor-0.7.2-Setup-x64.exe) |
| v0.7.1 | Windows installer | [AzureSavingsPlanAdvisor-0.7.1-Setup-x64.exe](https://github.com/jerrywolff_microsoft/azure-savings-plan-advisor/releases/download/v0.7.1/AzureSavingsPlanAdvisor-0.7.1-Setup-x64.exe) |
| v0.7.0 | Windows installer | [AzureSavingsPlanAdvisor-0.7.0-Setup-x64.exe](https://github.com/jerrywolff_microsoft/azure-savings-plan-advisor/releases/download/v0.7.0/AzureSavingsPlanAdvisor-0.7.0-Setup-x64.exe) |
| v0.6.0 | Windows installer | [AzureSavingsPlanAdvisor-0.6.0-Setup-x64.exe](https://github.com/jerrywolff_microsoft/azure-savings-plan-advisor/releases/download/v0.6.0/AzureSavingsPlanAdvisor-0.6.0-Setup-x64.exe) |
| v0.5.0 | Windows installer | [AzureSavingsPlanAdvisor-0.5.0-Setup-x64.exe](https://github.com/jerrywolff_microsoft/azure-savings-plan-advisor/releases/download/v0.5.0/AzureSavingsPlanAdvisor-0.5.0-Setup-x64.exe) |

### Repository-hosted packages: all available versions

| Version / source | Package | Download |
| --- | --- | --- |
| repository | Windows installer | [downloads/windows/AzureSavingsPlanAdvisor-0.6.0-Setup-x64.exe](https://github.com/jerrywolff_microsoft/azure-savings-plan-advisor/raw/refs/heads/main/downloads/windows/AzureSavingsPlanAdvisor-0.6.0-Setup-x64.exe) |
| repository | Windows installer | [downloads/windows/AzureSavingsPlanAdvisor-0.7.0-Setup-x64.exe](https://github.com/jerrywolff_microsoft/azure-savings-plan-advisor/raw/refs/heads/main/downloads/windows/AzureSavingsPlanAdvisor-0.7.0-Setup-x64.exe) |
| repository | Windows installer | [downloads/windows/AzureSavingsPlanAdvisor-0.7.1-Setup-x64.exe](https://github.com/jerrywolff_microsoft/azure-savings-plan-advisor/raw/refs/heads/main/downloads/windows/AzureSavingsPlanAdvisor-0.7.1-Setup-x64.exe) |
| repository | Windows installer | [downloads/windows/AzureSavingsPlanAdvisor-0.7.2-Setup-x64.exe](https://github.com/jerrywolff_microsoft/azure-savings-plan-advisor/raw/refs/heads/main/downloads/windows/AzureSavingsPlanAdvisor-0.7.2-Setup-x64.exe) |

Git LFS links download the package itself, not a pointer file. Executables without a setup wrapper may require accompanying project files.

### Setup scripts and source


- [Download the complete source ZIP](https://github.com/jerrywolff_microsoft/azure-savings-plan-advisor/archive/refs/heads/main.zip). Extract the complete checkout before running setup scripts unless the project instructions explicitly support standalone installation.
- [Browse all releases and their assets](https://github.com/jerrywolff_microsoft/azure-savings-plan-advisor/releases).

Android may require approval to install apps from the download source. Follow the project-specific installation, signing, checksum, and prerequisite instructions elsewhere in this README.
<!-- project-downloads:end -->

## Install the Windows app

1. Use the **0.9.0** installer produced by
   [building from source](#build-the-windows-installer-from-source):
   `dist\installer\AzureSavingsPlanAdvisor-0.9.0-Setup-x64.exe`.
   The checked-in and published **0.7.2** installers are historical and do not
   include the local AI connection.
2. Run the installer on Windows 10/11 x64. It installs for your current user,
   creates a Start menu shortcut, and optionally creates a desktop shortcut.
   Python is bundled. Node.js and Functions Core Tools are **not required**.
3. Install/start [Ollama for Windows](https://ollama.com/download/windows) and
   make sure `ollama list` includes `llama3.1:8b`, or another approved installed
   local chat model. See [local AI setup](#direct-local-ai-analysis) for commands.
   The installer does **not** bundle Ollama or model weights.
4. Open **Azure Savings Plan Advisor** from Start. Keep **modeler** selected,
   enter your financial assumptions and the installed local model name, then
   select **Run report**. Do not sign in to Azure or GitHub for local AI.
5. Review the calculated figures and charts, then **AI analysis** for the
   returned explanation. Model loading/inference can take time; the window
   remains usable while the request runs. **Ask AI** retries the current model.
   Verify AI statements against the calculated references before acting.
6. Use **Executive PDF**, **Executive PowerPoint**, **Export CSV** or **JSON**
   to save your current results, including the AI response and its provenance
   when available.

### Optional: connect to Azure for live recommendations

Local modeling and AI do not require these steps.

1. Install [Azure CLI for Windows](https://aka.ms/installazurecliwindows),
   then restart the app so it can find `az`.
2. Select **connected** mode.
   Select **Switch Azure account** to choose an identity in your browser without
   reusing a previously selected tenant. This explicitly clears the app's tenant,
   subscriptions and results, but does not clear the shared CLI account cache.
   The initial authorization omits `--tenant`, using the Azure CLI's normal
   account-wide discovery; the app does not choose an account for you. Passing
   an alias such as `organizations` explicitly would instead force CLI
   tenant-specific subscription discovery. After sign-in, select an accessible
   directory and subscriptions.
   To sign in to a specific directory, enter/select its approved tenant GUID and
   select **Sign in to selected tenant**. That action intentionally preserves
   the tenant constraint, including when you need an approved guest directory.
   The sign-in status shows elapsed time while waiting for the browser, with
   a five-minute limit and **Cancel sign-in**. Cancelling or closing the app
   stops its pending login process; it does not sign out or clear shared CLI
   credentials. Close any unused browser sign-in page yourself.
   If no browser appears, cancel, run `az login` in PowerShell, and select
   **Refresh context**. Browser sign-in and tenant/subscription discovery are
   shown as separate steps so a network wait is not mistaken for a frozen app.
3. Select one or more accessible subscriptions using Ctrl/Shift, or **Select all shown**.
   Filter by name or ID; selections remain selected when hidden by the filter.
   **Clear selections** clears all selected subscriptions, including hidden ones.
   Choose P1Y/P3Y and the lookback, then select **Run report**.
   **No CSV or assumed discount is required.**
4. Review the **Executive dashboard** for summary cards, savings-percentage
   bars, hourly commitment charts and the combined recommendation table;
   **Evidence & details** includes the
   assumptions, warnings and underlying Azure values.
5. Use **Executive PDF**, **Executive PowerPoint**, **Export CSV** or **JSON**
   to save your current results.

### Account does not exist in the requested tenant

This is an account/directory mismatch, not evidence that a password or usage
allowance is wrong. Cancel the waiting sign-in and use **Switch Azure account**
to remove the previous tenant restriction, then select the intended identity.
Alternatively, enter a directory that the intended account can access and use
**Sign in to selected tenant**. A valid cached CLI session in one directory
does not prove access to a different directory.

The app surfaces recognized `AADSTS` error codes and safe guidance, not raw CLI
output containing account names, directory IDs or credentials. If the intended
directory requires guest membership, its administrator must approve that access.
The app never creates guest accounts, changes role assignments, silently chooses
another account, or retries a different tenant after a scoped sign-in failure.

`AADSTS90002` specifically means **tenant not found**, not that the password is
incorrect or the user cancelled. Use **Switch Azure account** to remove the
tenant override, or verify the tenant GUID and active Azure cloud for scoped
sign-in. A deleted directory or a tenant in a different Azure cloud is not
repaired by switching passwords, adding guest membership or changing
Conditional Access policy. The app does not change the active cloud for you.

### Executive dashboard and exports

The desktop uses a light blue background, white report panels and teal controls.
The screen, PDF, PowerPoint (`.pptx`) and CSV use the same normalized report:

- Summary cards show recommendation/option count, Advisor action count,
  collection coverage and currencies. Values are never summed across currencies
  or mutually exclusive alternatives.
- Savings-percentage charts show up to five primary recommendations or modeled
  options. The count of displayed/available percentages is explicit; all records,
  including Azure's alternatives and Advisor actions, remain in the table/exports.
- Hourly commitment charts show up to five primary recommendations or modeled
  options per currency, with subscription/term labels and independent scales.
  Missing amounts and alternatives are excluded from charts; nothing is added
  across subscriptions, currencies or alternatives. PDF and PowerPoint include
  the same charts.
- The scrollable results table includes subscription name/ID, recommendation,
  term, currency, hourly commitment, savings amount/percentage, coverage and
  utilization. Per-subscription collection warnings appear only in the separate
  **Log** tab, using subscription names rather than raw diagnostic keys. Results
  show one incomplete-data notice with a pointer to Log, not a warning list.
  Routine successful/empty API statuses, API versions and verbose service messages
  remain suppressed.
  A failed subscription does not discard successful results from the others.
- The read-only **Log** tab contains the current report's collection warnings
  and permission guidance, with collection time and scope. It is separate from
  the executive dashboard and evidence/details. It does not steal focus when
  collection completes. Changing context or report inputs clears stale entries;
  running a new report replaces them. Log entries use the same secret redaction
  as the rest of the UI and are not included in report exports.
- Click any results row (or focus a row and press Enter) to open a scrollable
  details popup with benefit/plan SKU, benefit cost, savings, discount assumptions,
  financial details, collection time, evidence reference and a brief completeness notice.
  Escape or Close dismisses it. Changing report context closes stale details.
  Connected reports also collect current VM, VM scale set and App Service plan
  inventory using the same delegated user and selected subscriptions. Inventory
  rows show compute type, configured SKU and reported license type; plan popups
  show same-subscription inventory as context, **not attributed benefit coverage**.
  Advisor rows show compute details only on an exact resource-ID match.
  Unsupported compute services, offline inputs and missing fields remain
  **Not supplied**. Inventory is not historical usage or proof of eligibility.
  A returned benefit/plan SKU is not a VM SKU, and overall savings percentage
  is not a per-SKU discount. Offline discounts remain explicitly assumed.
- PDF and PowerPoint include the executive summary, chart when percentages are
  available, scope, collection time, a brief completeness notice, evidence
  references, details and limitations. Long reports paginate instead of dropping
  records. CSV includes the same metadata on each data row and separate rows for
  recommendations, alternatives, Advisor actions or modeled options.
- Empty and partial reports can be exported with their coverage limitations.
  Missing financial values stay **Not supplied** (blank numeric CSV cells);
  they are never replaced with zero.
- JSON exports omit raw per-source `coverage` diagnostics and detailed
  `collectionWarnings`, including legacy warning lists. They include a single
  `collectionSummary` only when collection is incomplete. CSV retains the
  `sourceCoverage` column for schema compatibility, containing the same brief
  completeness notice (blank for healthy connected collection).
  Per-subscription warning entries remain in Log; financial evidence and
  partial-completeness indicators are preserved in all reports.
- The app does not collect service/resource-group cost breakdowns. It therefore
  does not fabricate the cost-by-service/resource-group charts shown in other
  report products. Its charts represent the Savings Plan data actually returned.
- Changing tenant, subscription, mode or assumptions clears the dashboard and
  disables every export until a new report is run. Exports use the already
  collected report; they do not silently query Azure again.
- Known credential patterns are redacted consistently from screen data and
  exports, and CSV text cells are protected against spreadsheet formula execution.
  Tenant/subscription provenance and legitimate workload descriptions remain;
  review these customer-sensitive fields before sharing externally.
- Export writes are atomic: a failed export does not replace a previous report.
  Exports are generated locally; PowerPoint and a PDF printer are not required.

### Azure context, permissions, and recommendation sources

- **Refresh context** uses an existing Azure CLI user sign-in to discover tenants
  and enabled subscriptions. A blank tenant uses the current CLI user's context.
  Only subscriptions belonging to the selected tenant are offered. Membership
  is rechecked before every collection; a service-principal CLI login is rejected.
- Azure CLI commands for sign-in, context discovery and token retrieval run
  without terminal windows. Browser sign-in and MFA remain visible. Use a current
  Azure CLI version (2.54 or later for UTC token expiry support).
- Switching tenant/subscription clears previous results and disables stale exports.
  The app does not call `az account set`; requests use a tenant-specific delegated
  credential and explicitly selected subscriptions. Sign-in may update the
  shared Azure CLI account cache. **Disconnect app** clears app state only; use
  `az logout` separately if you intend to clear CLI credentials.
- The desktop app calls Azure directly; no Function deployment or API client
  secret is required. The separate Copilot/Function deployment remains supported.
  Only public Azure (`management.azure.com`) is supported by this desktop version.
- Grant only the read access needed at the selected subscription. Azure Advisor
  reading requires `Microsoft.Advisor/recommendations/read` (included in Reader);
  Cost Management recommendations require the appropriate Cost Management read
  access, for example Cost Management Reader, subject to billing agreement and
  cost visibility settings. Role assignment does not guarantee billing eligibility.
- Compute inventory additionally requires `Microsoft.Compute/virtualMachines/read`,
  `Microsoft.Compute/virtualMachineScaleSets/read` and
  `Microsoft.Web/serverfarms/read` (included in Reader). Each list has independent
  coverage and uses paginated ARM APIs: Compute `2024-07-01` and App Service
  `2024-11-01`. A denied, unsupported or unavailable inventory source makes
  coverage partial without discarding recommendations or other inventory.
  Resource names, subscription provenance and reported license settings appear
  in reports and exports; review them before sharing. No license entitlement,
  actual benefit assignment or resource-level rate/discount is inferred.
- [Azure Advisor](https://learn.microsoft.com/en-us/rest/api/advisor/recommendations/list)
  provides **cached Cost recommendations** for existing workloads. Not every Cost
  action is a Savings Plan, and the app does not add Advisor savings to benefit
  savings or assume each action applies to the requested term.
- The [Benefit Recommendations API](https://learn.microsoft.com/en-us/rest/api/cost-management/benefit-recommendations/list)
  supplies Microsoft's recommended hourly commitment, savings, coverage and
  utilization, with any returned alternative commitments. The desktop uses
  **Single/subscription scope**, independently for each selected subscription;
  selecting several subscriptions does not create a shared-scope commitment.
  Shared billing scope remains an API capability.
  [Microsoft documents](https://learn.microsoft.com/en-us/azure/cost-management-billing/savings-plan/choose-commitment-amount)
  that Advisor Savings Plan recommendations use a 30-day lookback; the Benefit
  Recommendations API supports the app's 7/30/60-day selection.
- Reports include collection time, selected context, request filters, hashed
  evidence references and a brief completeness notice, not per-subscription
  warning lists or raw API-version/source-status diagnostics. Detailed warnings
  are available separately in Log. Internally, an empty response remains distinct from
  denied, unsupported or unavailable. Partial collection remains visibly partial;
  no invented recommendation or CSV model replaces missing data.
- Collection is read-only: the app does not refresh/generate Advisor recommendations,
  deploy resources, assign roles, or purchase/change a Savings Plan. Azure's cached
  recommendations can lag current workload changes; review them in Azure before purchase.

### Optional CSV modeling

Choose **what-if** or **comparison** to model a separate scenario from your own
hourly CSV and explicit discount/usage assumptions. CSV is required **only for
these offline modes**, never for connected analysis. The installation's `samples`
folder contains a synthetic CSV for trying offline modeling. These estimates
remain clearly distinct from live Azure recommendations, and CSV data is not uploaded.

### Compute-hours modeler and break-even guidance

Select **modeler**, enter the following, and select **Run report**. Neither a CSV
nor Azure sign-in is required:

- **Elapsed period hours**, such as 720 for a 30-day period.
- **Compute running hours** within that period, for one constant-rate workload.
  Fractional hours are supported; runtime cannot exceed elapsed hours. This is
  not a model of aggregate instance-hours for parallel workloads.
- Your **eligible PAYG rate per running hour**, **assumed Savings Plan discount**,
  **hourly monetary commitment**, **currency**, and **P1Y/P3Y term**.
  No price, discount, or commitment is guessed or fetched automatically.
- The **installed local Ollama model** name, default `llama3.1:8b`, for the
  separate AI explanation. GitHub usernames and API keys are not requested.

The dashboard shows projected period savings or loss, break-even running hours,
whether break-even is attainable, and a table of the selected model plus
independent runtime-sensitivity scenarios. Charts show savings/loss at different
running hours, savings percentage, and hourly commitment. Red bars indicate
negative values; lengths show magnitudes. Scenarios are not additive.
PDF, PowerPoint, CSV and JSON retain the figures, inputs, guidance and limitations.

For period hours `P`, runtime `H`, PAYG rate `R`, assumed discount fraction `d`,
and hourly commitment `C`, the model uses:

```text
Avoided PAYG per running hour = min(R, C / (1 - d))
PAYG cost                    = H * R
Commitment cost              = P * C
Uncovered PAYG               = H * (R - avoided PAYG per running hour)
Modeled cost                 = commitment cost + uncovered PAYG
Net savings                  = PAYG cost - modeled cost
Break-even running hours     = (P * C) / avoided PAYG per running hour
```

Commitment is paid **every elapsed hour, including idle hours**; unused amounts
do not roll over. Break-even is a runtime/utilization threshold over the entire
period, **not a promise of payback after that many elapsed hours**. A threshold
above the period is unattainable for this workload. Zero commitment means PAYG
with no discount coverage and no meaningful break-even threshold. Zero discount
cannot produce positive savings. Full-term cost/savings projections repeat the
period's duty cycle for 365 days/year; modeling a shorter period does not shorten
the financial obligation.

**Example (synthetic assumptions, not Azure pricing):** 100 elapsed hours,
90 running hours, 10 USD/running hour, 20% discount and 8 USD/hour commitment
produce 900 USD PAYG versus 800 USD modeled cost, 100 USD period savings,
80 USD unused commitment, and 80 break-even running hours. At only 50 running
hours the same commitment produces a 300 USD loss.

To verify the connection, enter those synthetic inputs with currency **USD**
and term **P1Y**, then **Run report**. The calculated reference must show
**80 hours / 80% break-even** and **100 USD savings**. An actual model response
should appear in **AI analysis**, labeled **Ollama (local)** with its model name
and timestamps. A local calculation alone, a pending status or an error is not
proof that AI inference succeeded. This synthetic scenario was also exercised
through the desktop against the running local model during 0.9.0 validation.

### Direct local AI analysis

**Modeler** is the initial mode. **Run report** automatically calls the selected
installed **Ollama** model and displays its returned break-even explanation in
**AI analysis**. This is local AI, not Microsoft/GitHub Copilot.
There is no clipboard handoff. **Ask AI** retries the request for the current
model. Local calculations remain the tested financial reference; the separately
labeled AI response explains the break-even hours/percentage, savings or loss,
idle-hour commitment risk, uncovered PAYG and limitations.

Install [Ollama for Windows](https://ollama.com/download/windows) using your
organization's approved process. Start Ollama and install a suitable local chat
model if one is not already present. The default is `llama3.1:8b`; hardware must
have sufficient memory for it. No model or runtime is downloaded automatically
by the app. Internet access may be needed for initial installation/downloads,
but local analysis requires no cloud credentials, subscription or quota.

#### What happens on a new Windows laptop or desktop?

| Target PC | Available behavior |
| --- | --- |
| No Ollama installed or running | Reference calculations, charts and exports work. The AI request reports that Ollama is unavailable; no AI explanation is generated. |
| Ollama running, but selected model missing | Reference calculations remain available. Install an approved local chat model and select its exact name before retrying AI. |
| Ollama and a supported local model ready | Both calculations and actual in-app AI explanations are available, subject to sufficient hardware resources. |

Installing the advisor alone does not install Ollama, download weights or
provision a cloud service. For PCs where local inference is not permitted or
practical, a cloud-backed version would need a separately implemented,
organization-approved AI endpoint and authentication flow. **That cloud
connection is not implemented in 0.9.0.** Do not distribute this installer as
providing out-of-the-box AI on every Windows PC.

Prerequisites and source execution (Python 3.11+; Python is bundled in installers):

```powershell
ollama list
# Only if approved and not already installed (downloads model weights):
ollama pull llama3.1:8b
# Start the Ollama Windows application, or run ollama serve if it is not running.
python -m pip install -r requirements-windows.txt
python .\desktop_app.py
```

In the modeler, enter the exact installed local chat model name from
`ollama list`, then your financial assumptions and **Run report**. The first
request may take longer while the weights load. The app checks local model
metadata before sending the financial prompt; cloud/remote models, including
`:cloud` models, are rejected. There is no automatic cloud fallback.

The app posts only allowlisted numeric financial inputs, currency/term and
calculated results to the fixed loopback endpoint `http://127.0.0.1:11434`.
It does **not** send Azure tenant/subscription identifiers, inventory, raw CSVs,
previous explanations or arbitrary report text. HTTP proxies, netrc credentials
and redirects are disabled for this connection. The request has no tools,
MCP servers, file access or project instructions. The local service must be
trusted; follow organization policy for local models, service logs and saved
exports. Do not expose Ollama to untrusted networks.

Unavailable services/models, unsupported models, invalid responses, redirects,
timeouts and incomplete/truncated responses are explicit failures, not
deterministic text disguised as AI output. Check that Ollama is running and
that the model fits the PC's memory, then **Ask AI** to retry. The inference
read timeout is 150 seconds; connecting and local-model verification have
separate shorter timeouts. Reference calculations and exports remain available.
Responses include service, selected model, generation time and calculation
timestamp in JSON and PDF/PowerPoint/CSV report notices. The existing JSON
`copilotAnalysis` property is retained for compatibility, but its `source` and
`model` identify local Ollama rather than Copilot. AI text uses the shared
credential redactor. AI explanations can still contain mistakes: verify them
against the reference figures. Neither local AI nor this model verifies Azure
eligibility or live rates.

Editing inputs clears the explanation and disables stale exports until rerun.
Responses for an older input state are discarded, not attached to the new report.
Connected Azure reports and CSV modes retain their existing behavior; they do
not call AI. To stop local AI inference, close the app and manage Ollama using
its own controls. Closing does not stop a shared Ollama service. Changing inputs
or closing the app does not delete saved exports or local service logs.
Connecting a specific approved Microsoft Copilot agent still requires its
published client endpoint and approved authentication configuration; no such
connection is claimed or silently substituted.

#### Local AI troubleshooting

| Symptom | Action |
| --- | --- |
| Cannot connect to local Ollama | Start the Ollama Windows application, or run `ollama serve` in a separate PowerShell window if it is not already running. Retry **Ask AI**. |
| Selected model is not installed | Run `ollama list` and enter an exact installed chat-model name. If permitted, `ollama pull llama3.1:8b` downloads the default model. |
| Cloud/remote model is rejected | Choose an installed local model. Cloud inference and automatic cloud fallback are intentionally disabled. |
| Request times out or is incomplete | Check available memory and Ollama status; try another approved installed local chat model and rerun. The inference read timeout is 150 seconds. |
| Azure or GitHub login is shown as required for AI | Verify that you launched the updated 0.9.0 app in **modeler** mode, not an older installed copy. Connected Azure analysis has a separate sign-in flow. |
| No AI response for connected/CSV reports | Expected: only **modeler** reports request a local AI explanation. |

Validate actual eligibility, rate, discount and Azure recommendations before
making a purchase decision. Taxes, licensing, ineligible charges and consumption
of unused commitment by other workloads are outside this single-workload model.

The installer is currently **unsigned**; Windows SmartScreen may show a warning
or organizational policy may block it. Verify the release's `SHA256SUMS.txt`
and publisher/source before running; do not bypass your organization's policy.
Check a downloaded file with `Get-FileHash -Algorithm SHA256`.
Uninstall through Windows **Settings > Apps > Installed apps**. Exported results
and your input CSV files are not removed.

### Build the Windows installer from source

Use Windows x64 with Python 3.11 and [Inno Setup 6](https://jrsoftware.org/isdl.php).
From the project directory:

```powershell
py -3.11 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
.\.venv\Scripts\python.exe -m pip install -r requirements-windows.txt
if ($LASTEXITCODE -ne 0) { throw 'Windows build dependency installation failed.' }
.\scripts\Build-WindowsInstaller.ps1 -Python .\.venv\Scripts\python.exe -Version 0.9.0
.\scripts\Test-WindowsInstaller.ps1 -Installer .\dist\installer\AzureSavingsPlanAdvisor-0.9.0-Setup-x64.exe
```

The installer and checksum are written under `dist\installer`. The Windows
installer workflow also builds, tests installation/application launch/uninstall,
and publishes these files when a version tag is pushed, when hosted runners
are permitted. This repository's enterprise policy currently disables hosted
runners; an enterprise administrator must enable them or provide an approved
runner. Version 0.9.0 starts in modeler mode and uses local Ollama instead of the
GitHub Copilot SDK; the app no longer requests a GitHub username for AI.
Ollama and model weights must be installed separately on each target PC.
Live Azure collection still requires validation with the intended tenant, selected
subscriptions and RBAC.
The install/uninstall smoke test requires a separate Windows test user if the
app is already installed; it deliberately refuses to modify an existing install.
Select the installer explicitly when several versions exist in the output folder.

The build script finds Inno Setup on PATH or in its standard machine/per-user
installation directory. Signing requires a separately provisioned code-signing
certificate; none is stored in this repo.

## Decision-support boundary

- **Connected mode** returns normalized Savings Plan benefit recommendations
  from Azure Cost Management. The API does not recreate or supplement Azure's
  recommendation algorithm.
- **What-if mode** calculates deterministic planning estimates from hourly
  eligible PAYG cost history and the explicit assumptions supplied in the
  request.
- **Comparison mode** compares pay-as-you-go, P1Y, and P3Y using explicit
  discount assumptions for each term.
- The conservative, balanced, and maximum-savings scenarios use lower,
  middle, and higher historical hourly cost percentiles to model different
  commitment levels. They are transparent planning scenarios, not Microsoft's
  proprietary recommendations.
- An hourly commitment is modeled as the hourly amount paid for the plan.
  PAYG coverage capacity is estimated as commitment divided by
  `(1 - modeled discount)`. The model assumes that unused commitment is still
  paid and uncovered usage remains at PAYG cost.
- What-if responses distinguish the supplied observed baseline from the
  usage-change-adjusted scenario baseline. Modeled savings are compared with
  the scenario baseline, not presented as historical realized savings.
- Confidence and risk are transparent heuristics based on sample size,
  variability, and modeled utilization. They are not Azure-provided scores.
- What-if estimates are not guaranteed savings or purchase recommendations.
  Review all inputs and Azure recommendations before making a purchase.
- This application never purchases, modifies, exchanges, cancels, or renews a
  Savings Plan.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Minimal health response; no customer data |
| `POST` | `/api/analyze-savings-plan` | JSON connected, what-if, or comparison request |
| `POST` | `/api/analyze-savings-plan-csv` | Multipart CSV upload for offline what-if analysis |

### What-if example

```json
{
  "mode": "what-if",
  "term": "P1Y",
  "currencyCode": "USD",
  "expectedChangePercent": -10,
  "discountPercent": 18,
  "scenario": "balanced",
  "baselineHourlyCosts": [12.4, 11.8, 13.1, 14.0]
}
```

The four values above are illustrative inputs only. Replace them with
customer-approved data and assumptions. `discountPercent` is required; the
service will not look up or invent a what-if discount. For a custom plan amount,
set `"scenario": "custom"` and supply `hourlyCommitment`.

### Comparison example

```json
{
  "mode": "comparison",
  "currencyCode": "USD",
  "expectedChangePercent": 0,
  "discountPercentP1Y": 15,
  "discountPercentP3Y": 25,
  "baselineHourlyCosts": [12.4, 11.8, 13.1, 14.0]
}
```

The two discounts are explicit assumptions, not Azure prices. The response
contains three options: no commitment, P1Y, and P3Y. A longer term is not
automatically assigned a larger discount.

### Connected example

```json
{
  "mode": "connected",
  "scope": "/subscriptions/00000000-0000-0000-0000-000000000000",
  "term": "P1Y",
  "lookbackPeriod": "Last30Days",
  "recommendationScope": "Shared"
}
```

The example scope is a placeholder. Connected requests support `P1Y`/`P3Y`,
`Last7Days`/`Last30Days`/`Last60Days`, and `Single`/`Shared`. The response
includes only selected recommendation fields, source, collection time, and
request filters; it does not forward the full ARM response to Copilot.

### CSV upload

CSV must contain `timestamp` and `eligible_payg_cost` columns. Header matching
is case-insensitive and spaces are treated as underscores. The timestamp must
include a timezone and represent a consecutive hourly series in increasing
order. Invalid rows, missing hours, duplicate timestamps, negative/non-numeric
costs, empty data, and uploads larger than 2 MB are rejected; values are never
silently repaired.

`samples/hourly-costs.csv` contains synthetic data. For the multipart endpoint,
send the file in the `csvFile` field plus `term`, `currencyCode`,
`discountPercent`, `expectedChangePercent`, and `scenario` fields.
The JSON endpoint also accepts the CSV text in a `csvData` property.

## Windows installers

Install these tools before following the local development steps:

| Tool | Windows download / installation |
| --- | --- |
| Python 3.11 (64-bit) | [Download the Python 3.11.9 Windows installer](https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe) or see the [Python 3.11 release page](https://www.python.org/downloads/release/python-3119/). Enable **Add python.exe to PATH** in the installer. |
| Node.js (LTS) | Download the Windows `.msi` installer from [Node.js downloads](https://nodejs.org/en/download/). Node.js and npm are needed to install Core Tools and Azurite below. |
| Azure CLI | Download the [64-bit Azure CLI MSI](https://aka.ms/installazurecliwindows); see [Microsoft's Windows installation guide](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows) for details. |

After installing Node.js, open PowerShell and install the local Azure Functions
tools and storage emulator:

```powershell
npm install --global azure-functions-core-tools@4
npm install --global azurite
```

See Microsoft's [Azure Functions Core Tools guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local)
and [Azurite installation guide](https://learn.microsoft.com/en-us/azure/storage/common/storage-install-azurite)
for alternatives and troubleshooting. Azure CLI includes the Bicep CLI;
install it with `az bicep install` if it is not already available.

## Local development

Prerequisites: Python 3.11, Node.js/npm, Azure Functions Core Tools v4, and
Azurite for local host storage. Azure CLI is additionally needed for connected
mode and Azure deployment.

From PowerShell in this folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item local.settings.example.json local.settings.json
.\.venv\Scripts\python.exe -m pytest -q
$sourceFiles = @('.\function_app.py') + (Get-ChildItem .\api -Filter *.py | Select-Object -ExpandProperty FullName)
& .\.venv\Scripts\python.exe -m py_compile $sourceFiles
if ($LASTEXITCODE -ne 0) { throw 'Python compilation failed.' }
func start
```

Run `azurite --silent --location .\azurite-data` in another terminal before
starting the Functions host.

Try the deterministic offline example in another PowerShell window:

```powershell
$body = Get-Content .\samples\what-if-request.json -Raw
Invoke-RestMethod -Method Post -Uri http://localhost:7071/api/analyze-savings-plan `
  -ContentType 'application/json' -Body $body
```

To try connected mode locally:

```powershell
az login
az account show --output table
```

Set `AZURE_AUTH_MODE=developer` in local settings, then use an identity with
read permission at the requested Cost Management scope. Do not put real billing
data or credentials into checked-in samples.

## Azure deployment

Deployment is intentionally explicit and is not run by this repository's CI.
Before deploying, confirm the signed-in tenant/subscription and obtain the
customer's approval for the target resource group, region, and permissions.

### Prerequisites

1. An Entra app registration for the API, configured to expose an API scope
   (for example `user_impersonation`) and allow the Copilot Studio custom
   connector client.
2. The API app registration has the delegated Azure Resource Manager
   `user_impersonation` permission, with the required consent granted.
3. A Key Vault in the deployment resource group containing the API app
   registration's client secret, with the Azure RBAC permission model enabled.
   Grant operators no broader access than required to deploy and rotate it.
4. Users have the necessary Cost Management read permissions at the billing
   scope they request. The template deliberately does not grant billing-scope
   roles.
5. Azure CLI with Bicep support and Azure Functions Core Tools v4.
6. The deployment principal can create the listed resources and assign the
   scoped built-in storage, Key Vault, and telemetry roles.

The Function App uses a Linux Flex Consumption plan, App Service
Authentication (Easy Auth) to enforce the API audience, and an on-behalf-of
exchange to call Azure Resource Manager as the authenticated user. Its
user-assigned managed identity is used for Function storage, deployment
packages, Application Insights, and Key Vault secret resolution; it is not
substituted for the user's billing permissions. The template does not create
private networking; if the customer's network policy requires it, configure a
supported private ingress path that Copilot Studio can reach before deployment.

### Provision infrastructure

Run from the project directory in PowerShell. Replace every placeholder with
values approved for this deployment; never reuse another customer's tenant,
subscription, or billing scope.

```powershell
$expectedTenantId = '<approved-tenant-guid>'
$expectedSubscriptionId = '<approved-subscription-guid>'
az login --tenant $expectedTenantId
if ($LASTEXITCODE -ne 0) { throw 'Azure sign-in failed.' }
az account set --subscription $expectedSubscriptionId
if ($LASTEXITCODE -ne 0) { throw 'Unable to select the approved subscription.' }
$tenantId = az account show --query tenantId --output tsv
$subscriptionId = az account show --query id --output tsv
if ($LASTEXITCODE -ne 0) { throw 'Unable to read Azure context.' }
if ($tenantId -ne $expectedTenantId) { throw 'Unexpected Azure tenant.' }
if ($subscriptionId -ne $expectedSubscriptionId) { throw 'Unexpected Azure subscription.' }

$resourceGroupName = '<approved-resource-group>'
$location = '<approved-region>'
$functionAppName = '<globally-unique-function-app-name>'
$storageAccountName = '<globally-unique-lowercase-storage-name>'
$appInsightsName = '<application-insights-name>'
$appServicePlanName = '<function-plan-name>'
$keyVaultName = '<existing-key-vault-in-the-same-resource-group>'
$clientSecretName = '<existing-api-client-secret-name>'
$apiClientId = '<api-app-registration-client-id>'
$apiAudience = "api://$apiClientId"
$corsOrigins = '["<approved-copilot-studio-origin>"]'

az group show --name $resourceGroupName --output none
if ($LASTEXITCODE -ne 0) { throw 'The approved resource group must already exist.' }
az keyvault show --name $keyVaultName --resource-group $resourceGroupName --output none
if ($LASTEXITCODE -ne 0) { throw 'The existing Key Vault must be in the deployment resource group.' }
az deployment group create --resource-group $resourceGroupName `
  --template-file .\infra\main.bicep `
  --parameters "location=$location" `
    "functionAppName=$functionAppName" `
    "storageAccountName=$storageAccountName" `
    "appInsightsName=$appInsightsName" `
    "appServicePlanName=$appServicePlanName" `
    "keyVaultName=$keyVaultName" `
    "clientSecretName=$clientSecretName" `
    "tenantId=$expectedTenantId" `
    "apiClientId=$apiClientId" `
    "apiAudience=$apiAudience" `
    "corsAllowedOrigins=$corsOrigins"
if ($LASTEXITCODE -ne 0) { throw 'Infrastructure deployment failed.' }
```

The template creates a Python 3.11 Linux Flex Consumption Function App, storage,
workspace-based Application Insights, HTTPS-only settings, explicit CORS
origins, Entra authentication, and scoped storage/secret roles for its
user-assigned managed identity. The Key Vault must use Azure RBAC and be in the
same resource group. Allow time for role-assignment propagation before
validating Key Vault references. It does not create an app registration or
grant Cost Management access.

### Deploy the Function package

```powershell
func azure functionapp publish '<function-app-name>'
if ($LASTEXITCODE -ne 0) { throw 'Function deployment failed.' }
```

Confirm `GET https://<function-app-name>.azurewebsites.net/api/health` returns
the minimal health response. Then configure the Copilot Studio REST tool with
`agent/openapi-v2.json`, replace its host and Entra OAuth placeholders, and
test connected and what-if modes using approved, non-production test data
first. Never paste tokens or client secrets into the OpenAPI file or chat.

## Copilot Studio

- Import `agent/openapi-v2.json` as a REST API tool.
- Configure OAuth with the approved Entra app registration; do not use Function
  keys for production.
- Add the instructions in `agent/instructions.md` to the agent.
- Review the sample conversations in `agent/sample-conversations.md`.
- Keep the LLM in an explanatory role: all financial figures and comparisons
  must come from the API response.

## CI and tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
$sourceFiles = @('.\function_app.py') + (Get-ChildItem .\api -Filter *.py | Select-Object -ExpandProperty FullName)
& .\.venv\Scripts\python.exe -m py_compile $sourceFiles
if ($LASTEXITCODE -ne 0) { throw 'Python compilation failed.' }
```

GitHub Actions runs tests and compilation for pushes and pull requests to
`main`. Infrastructure deployment is a separate, explicitly approved
operation.

## Limitations

- What-if outputs are estimates based on one supplied hourly series and explicit
  assumptions. Validate the model and input data against your approved FinOps
  methodology before customer use.
- A single assumed discount is not an Azure quote. Comparison mode requires a
  separate user-approved assumption for P1Y and P3Y.
- CSV input must already be normalized to consecutive hourly eligible PAYG
  amounts; this service does not query, infer, aggregate, or interpolate usage.
- Connected recommendations depend on Azure API availability, the signed-in
  user's delegated permissions, and supported billing scopes.
- Local AI requires a running Ollama service and an installed local chat model
  that fits the PC's hardware. Its explanations can contain mistakes and do not
  replace the calculated references or authoritative Azure recommendations.

## Copyright

Copyright (c) 2026 Jerry Wolff. See [COPYRIGHT](COPYRIGHT) for the scope of this
notice. Existing licenses and third-party attribution remain unchanged; this
notice does not grant additional permissions.
