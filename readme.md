- Make Data collection Endpoint
- Make custom table in GUI using (direct ingest)
- Create a new Data Collection RUle as part of this. Select your made DCE
- Upload example log file for the format. (create dummy data for public upload)
- Mod the transformation to use the timestamp for the actual timeGenerated with the following: 
```
source
| extend timestamp_sec = todouble(timestamp) / 1000.0
| extend TimeGenerated = todatetime('1970-01-01 00:00:00') + totimespan(timestamp_sec * 1s)
// | extend t = unixtime_seconds_todatetime(timestamp_sec)
| project 
    TimeGenerated,
    id,
    description,
    teamId,
    serverId,
    serverName,
    viewerId,
    userId,
    email,
    timestamp,
    eventType,
    eventCategory,
    eventBody
```
- Create App Registration 
- Generate a secret for the script.
- Assign the service principle from the app registration the role "monitoring metrics publisher" to the Data collection rule