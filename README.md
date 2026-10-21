# Azure Savings Plan Advisor

**Windows setup:** [Download prerequisite installers](#windows-installers)
and follow the [local development steps](#local-development).

A Copilot Studio-ready planning API backed by a Python Azure Function. It keeps
the conversation separate from financial calculations and connected
recommendations:

```text
User -> Copilot Studio -> Entra-authenticated REST API -> Azure Function
                                                    -> Cost Management API
```

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
