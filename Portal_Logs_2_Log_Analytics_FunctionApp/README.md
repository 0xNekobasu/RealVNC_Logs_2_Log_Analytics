# RealVNC Portal Logs → Azure Log Analytics (Azure Function App)

A serverless, one-click-deployable version of the RealVNC portal audit-log forwarder.
It runs on a timer in an **Azure Functions Flex Consumption** plan (Python 3.12),
authenticates to Azure with a **managed identity**, reads the RealVNC API keys from
**Key Vault**, and ingests audit events into a Log Analytics custom table through a
**Direct Data Collection Rule**.

> Prefer to run it on-prem (cron / Jenkins) instead? Use the legacy script in
> [`../Portal_Logs_2_Log_Analytics/`](../Portal_Logs_2_Log_Analytics/).

## Deploy

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2F0xNekobasu%2FRealVNC_Logs_2_Log_Analytics%2Fmain%2FPortal_Logs_2_Log_Analytics_FunctionApp%2Finfra%2Fazuredeploy.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2F0xNekobasu%2FRealVNC_Logs_2_Log_Analytics%2Fmain%2FPortal_Logs_2_Log_Analytics_FunctionApp%2Finfra%2FcreateUiDefinition.json)

### Prerequisites
- An **existing Log Analytics workspace** (this template does **not** create one). Deploy
  into the **same resource group** as that workspace.
- A region that supports the [Flex Consumption plan](https://learn.microsoft.com/azure/azure-functions/flex-consumption-how-to#view-currently-supported-regions).
- RealVNC portal API credentials (`accessKey` + `accessKeyId`).
- A published GitHub Release containing `released-package.zip` (see [Releasing](#releasing)).
  The button defaults to `releases/latest/download/released-package.zip`.

### What gets deployed
All into one resource group (everything **except** the Log Analytics workspace):

| Resource | Purpose |
| --- | --- |
| `Microsoft.OperationalInsights/workspaces/tables` | `RealVNC_PortalLogs_CL` custom table in the existing workspace |
| `Microsoft.Insights/dataCollectionRules` (`kind: Direct`) | Schema + `timestamp → TimeGenerated` transform; exposes its own logs-ingestion endpoint (no DCE needed) |
| `Microsoft.KeyVault/vaults` (+ 2 secrets) | Stores the RealVNC API key & key id |
| `Microsoft.Storage/storageAccounts` (+ container) | Host/deployment storage (identity-based, no shared keys) |
| `Microsoft.Insights/components` | Application Insights (workspace-based) |
| `Microsoft.Web/serverfarms` (`FC1`) | Flex Consumption plan |
| `Microsoft.Web/sites` | The Python 3.12 function app with a system-assigned identity |
| 3 × `roleAssignments` | Storage Blob Data Owner, Key Vault Secrets User, Monitoring Metrics Publisher (on the DCR) |
| `Microsoft.Web/sites/extensions/onedeploy` | Pulls `released-package.zip` and activates the code |

Resource names are `<appNamePrefix>-<kind>-<6-char-hash>` so repeated deployments don't collide.

### Parameters
| Parameter | Default | Notes |
| --- | --- | --- |
| `appNamePrefix` | — | Your common name; 2–11 letters/numbers, prefixed to every resource |
| `logAnalyticsWorkspaceName` | — | Name of the **existing** workspace in this RG |
| `rvncApiKey` / `rvncApiKeyId` | — | RealVNC credentials (securestring → Key Vault) |
| `scheduleNcrontab` | `0 */10 * * * *` | Timer cadence; editable later as an app setting |
| `lookbackMs` | `900000` | Audit lookback per run (ms); keep ≥ the schedule interval |
| `pythonVersion` | `3.12` | `3.11` or `3.12` |
| `packageUri` | latest GitHub release | URL of `released-package.zip` |
| `maximumInstanceCount` / `instanceMemoryMB` | `40` / `2048` | Flex Consumption scale settings |

### CLI deploy (alternative to the button)
```bash
az deployment group create \
  --resource-group <rg-with-your-workspace> \
  --template-file Portal_Logs_2_Log_Analytics_FunctionApp/infra/azuredeploy.json \
  --parameters appNamePrefix=realvnc \
               logAnalyticsWorkspaceName=<workspace> \
               rvncApiKey=<accessKey> \
               rvncApiKeyId=<accessKeyId>
```

## Changing the schedule
Edit the **`SCHEDULE_NCRONTAB`** application setting on the function app — no redeploy needed.
Examples: `0 */10 * * * *` (every 10 min, default), `0 */1 * * * *` (every minute),
`0 0 * * * *` (hourly).

## How duplicates are avoided (watermark/checkpoint)
Log Analytics has no primary key or upsert, so naively re-pulling overlapping time
windows would create duplicate rows. Instead the function keeps a **checkpoint** blob
(`checkpoints/realvnc-watermark.json` in the function's storage account) recording the
last ingested event time **and** the unique RealVNC event `id`s seen at that exact
millisecond. Each run pulls from `lastTimestamp` (inclusive, so same-millisecond events
are never missed) and skips any `id` already ingested. The watermark only advances after
a **successful** upload, so a failed run safely re-pulls next time.

- **`LOOKBACK_MS`** is now only the **first-run bootstrap** window (how far back to reach
  when there's no checkpoint yet). Default `900000` (15 min).
- If the checkpoint store is ever unavailable, the function falls back to the `LOOKBACK_MS`
  window and logs a warning (at-least-once). As cheap defence-in-depth you can still
  de-duplicate by `id` at query time:
  `RealVNC_PortalLogs_CL | summarize arg_max(TimeGenerated, *) by id`.
- To re-pull from scratch (e.g. after a gap), delete the checkpoint blob; the next run
  bootstraps from `LOOKBACK_MS`.

## App settings
| Setting | Source |
| --- | --- |
| `RVNC_API_KEY`, `RVNC_API_KEY_ID` | Key Vault references (`@Microsoft.KeyVault(...)`) |
| `DCR_IMMUTABLE_ID`, `DCE_ENDPOINT` | Set from the Direct DCR (immutable id + logs-ingestion endpoint) |
| `SCHEDULE_NCRONTAB` | Timer cadence; `LOOKBACK_MS` is the first-run bootstrap window |
| `AzureWebJobsStorage__accountName` / `__credential` | Identity-based host storage (also used for the checkpoint blob) |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Monitoring |

## Local development
```bash
cd Portal_Logs_2_Log_Analytics_FunctionApp
python -m venv .venv && . .venv/Scripts/activate   # Windows; use bin/activate on *nix
pip install -r requirements.txt
cp local.settings.json.example local.settings.json   # fill in your values
func start
```
`DefaultAzureCredential` uses your Azure CLI / VS Code sign-in locally and the managed
identity in Azure. To ingest locally you need **Monitoring Metrics Publisher** on the DCR.

## Releasing
Code is delivered to deployments via a GitHub Release asset named `released-package.zip`:
```bash
git tag v1.0.0
git push origin v1.0.0
```
[`.github/workflows/release.yml`](../.github/workflows/release.yml) builds the package and
attaches it to the release. The Deploy-to-Azure button / `packageUri` then pull
`releases/latest/download/released-package.zip`.
