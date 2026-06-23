# RealVNC Portal Logs → Azure Log Analytics

Pulls RealVNC **portal audit logs** and forwards them into a Microsoft **Log Analytics**
custom table (`RealVNC_PortalLogs_CL`). Two ways to run it — pick one:

## ☁️ Azure Function App (recommended)
A serverless, **one-click deployable** version. An ARM template stands up everything
(custom table, Direct DCR, Key Vault, storage, Application Insights, a Flex Consumption
Python 3.12 function app, and managed-identity role assignments) — everything except your
existing Log Analytics workspace. Runs on a timer (default every 10 minutes), uses a
**managed identity** for Azure auth, and stores the RealVNC secrets in **Key Vault**.

➡️ See [`Portal_Logs_2_Log_Analytics_FunctionApp/`](Portal_Logs_2_Log_Analytics_FunctionApp/)
for the Deploy-to-Azure button and full instructions.

## 🖥️ Legacy on-prem script
The original standalone Python script, suitable for running on-prem via cron, Jenkins, or
any scheduler. Uses a service principal (client secret) and a `.env` file, and expects a
manually-created DCE/DCR/custom table.

➡️ See [`Portal_Logs_2_Log_Analytics/`](Portal_Logs_2_Log_Analytics/).

---

Both write the same schema, so you can switch between them without changing your queries.
