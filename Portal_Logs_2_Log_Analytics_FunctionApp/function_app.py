"""
function_app.py

Azure Functions (Python v2 model) version of the RealVNC Portal -> Azure Log
Analytics audit log forwarder.

On a timer (default every 10 minutes) it:
  1. Authenticates to the RealVNC Portal API and obtains a short-lived bearer token.
  2. Works out which events it still needs by reading a checkpoint (watermark) from
     blob storage, then pulls the portal audit logs from that point (handling
     pagination).
  3. Drops any events already ingested, ingests the rest into a Log Analytics custom
     table via the Logs Ingestion API (authenticating with a managed identity), then
     advances the checkpoint.

Configuration is supplied through application settings (environment variables):

    RVNC_API_KEY          RealVNC portal access key      (Key Vault reference)
    RVNC_API_KEY_ID       RealVNC portal access key id   (Key Vault reference)
    DCR_IMMUTABLE_ID      Immutable id of the Direct DCR
    DCE_ENDPOINT          Logs ingestion endpoint (the Direct DCR's endpoint)
    SCHEDULE_NCRONTAB     NCRONTAB schedule, e.g. "0 */10 * * * *" (every 10 min)
    LOOKBACK_MS           First-run bootstrap window in ms (default 900000 / 15 min)
    AzureWebJobsStorage__accountName  Storage account used for the checkpoint blob

Duplicate handling
------------------
Log Analytics has no primary key / upsert, so re-pulling overlapping windows would
create duplicate rows. To avoid that, the function keeps a checkpoint of the last
ingested event time plus the unique RealVNC event ``id``s seen at that exact
millisecond. Each run pulls from ``lastTimestamp`` (inclusive, so same-millisecond
events are never missed) and skips any ``id`` already ingested. If the checkpoint
store is unavailable, it falls back to the ``LOOKBACK_MS`` window and logs a warning
(at-least-once delivery; de-duplicate by ``id`` at query time if needed).
"""
# Standard Libraries
import os
import logging
import json
import time

# Third Party Libraries
import requests
import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.monitor.ingestion import LogsIngestionClient

# RealVNC custom table / stream name. The Direct DCR declares the matching
# stream "Custom-RealVNC_PortalLogs_CL".
TABLE_NAME = "RealVNC_PortalLogs_CL"
STREAM_NAME = "Custom-" + TABLE_NAME

# Default first-run bootstrap window (15 minutes) if LOOKBACK_MS is not set.
DEFAULT_LOOKBACK_MS = 900000

# Checkpoint (watermark) location in the function's storage account.
CHECKPOINT_CONTAINER = os.getenv("CHECKPOINT_CONTAINER", "checkpoints")
CHECKPOINT_BLOB = os.getenv("CHECKPOINT_BLOB", "realvnc-watermark.json")

# Reused across invocations on a warm instance.
_credential = DefaultAzureCredential()
_checkpoint_client = None

app = func.FunctionApp()


def check_response(api_response):
    """
    Checks if an API call returned a successful (200/201) status code.

    Args:
        api_response (requests.Response): The HTTP response to validate.

    Returns:
        bool: True if the request succeeded, otherwise False.
    """
    if api_response.status_code in (200, 201):
        logging.info("API Response - Successful (%s)", api_response.status_code)
        return True
    logging.error(
        "API Response - ERROR - Request Failed (%s)", api_response.status_code
    )
    return False


def get_rvnc_bearertoken():
    """
    Calls the RealVNC portal authentication API to obtain a bearer token.

    Returns:
        str | None: The bearer token used to authenticate with the RealVNC
        portal API, or None if the request failed.
    """
    str_auth_url = "https://connect-api.services.vnc.com/1.0/sessions"
    obj_body_json = {
        "accessKey": os.getenv("RVNC_API_KEY"),
        "accessKeyId": os.getenv("RVNC_API_KEY_ID"),
        "expiry": "PT30M",
    }
    obj_headers_json = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    response = requests.post(
        str_auth_url, json=obj_body_json, headers=obj_headers_json, timeout=30
    )
    if not check_response(response):
        logging.error("ERROR: Issue with RealVNC authentication API call")
        return None
    obj_parsed_response = json.loads(response.text)
    logging.info("RealVNC bearer token successfully obtained")
    return obj_parsed_response["token"]


def get_bootstrap_window():
    """
    Returns the unix time (ms) to start from on the very first run (no checkpoint).

    The bootstrap window is controlled by the LOOKBACK_MS environment variable
    (default 900000 ms / 15 minutes).

    Returns:
        int: The unix time in milliseconds marking the start of the window.
    """
    try:
        lookback_ms = int(os.getenv("LOOKBACK_MS", DEFAULT_LOOKBACK_MS))
    except ValueError:
        logging.warning("Invalid LOOKBACK_MS value; falling back to default")
        lookback_ms = DEFAULT_LOOKBACK_MS
    return int(time.time() * 1000) - lookback_ms


def _get_checkpoint_blob_client():
    """
    Returns a BlobClient for the checkpoint blob, or None if storage isn't
    configured/available (in which case the caller falls back to the lookback
    window).

    The client is built once per worker instance and cached. The container is
    normally created by the ARM template; we only attempt to create it on the
    first build as a fallback (e.g. local development), swallowing the
    "already exists" conflict.
    """
    global _checkpoint_client
    if _checkpoint_client is not None:
        return _checkpoint_client

    account = os.getenv("AzureWebJobsStorage__accountName") or os.getenv(
        "CHECKPOINT_STORAGE_ACCOUNT"
    )
    if not account:
        logging.warning(
            "No storage account configured for checkpoints; using lookback window"
        )
        return None
    try:
        from azure.storage.blob import BlobServiceClient
        from azure.core.exceptions import ResourceExistsError

        endpoint = f"https://{account}.blob.core.windows.net"
        service = BlobServiceClient(account_url=endpoint, credential=_credential)
        container = service.get_container_client(CHECKPOINT_CONTAINER)
        try:
            container.create_container()
        except ResourceExistsError:
            pass  # already created (normally by the ARM template)
        _checkpoint_client = container.get_blob_client(CHECKPOINT_BLOB)
        return _checkpoint_client
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        logging.warning(
            "Checkpoint storage unavailable (%s); using lookback window", exc
        )
        return None


def read_checkpoint():
    """
    Reads the checkpoint blob.

    Returns:
        dict | None: {"lastTimestamp": int, "seenIds": set[str]} or None if there
        is no checkpoint yet (first run) or storage is unavailable.
    """
    client = _get_checkpoint_blob_client()
    if client is None:
        return None
    try:
        raw = client.download_blob().readall()
    except Exception:  # noqa: BLE001 - typically ResourceNotFound on first run
        logging.info("No existing checkpoint found; bootstrapping")
        return None
    cp = json.loads(raw)
    return {
        "lastTimestamp": int(cp["lastTimestamp"]),
        "seenIds": set(cp.get("seenIds", [])),
    }


def write_checkpoint(last_timestamp, seen_ids):
    """
    Persists the watermark (last ingested event time + boundary event ids).
    """
    client = _get_checkpoint_blob_client()
    if client is None:
        logging.warning("No checkpoint storage; watermark not persisted")
        return
    payload = json.dumps(
        {"lastTimestamp": int(last_timestamp), "seenIds": sorted(seen_ids)}
    )
    client.upload_blob(payload, overwrite=True)
    logging.info(
        "Checkpoint updated: lastTimestamp=%s, boundaryIds=%d",
        last_timestamp,
        len(seen_ids),
    )


def get_portal_logs(bearer_token, from_ms):
    """
    Calls the RealVNC portal audit API to pull logs from ``from_ms`` onwards,
    handling pagination.

    Args:
        bearer_token (str): The RealVNC portal bearer token.
        from_ms (int): Unix time (ms) to pull events from (inclusive).

    Returns:
        list: An array of event objects. Empty if none were found.
    """
    str_audit_url = "https://connect-api.services.vnc.com"
    obj_parameters_json = {
        "order": "DESC",
        "from": from_ms,
    }
    obj_headers_json = {
        "Accept": "application/json",
        "Authorization": f"Bearer {bearer_token}",
    }
    response = requests.get(
        url=str_audit_url + "/1.0/audit",
        headers=obj_headers_json,
        params=obj_parameters_json,
        timeout=30,
    )
    if not check_response(response):
        logging.error("ERROR: Issue with API call for obtaining audit logs")
        return []
    obj_rvnc_logs_json = json.loads(response.text)
    # Pagination - keep grabbing logs for the time period until none remain.
    while response.links:
        logging.info("Pagination detected, obtaining additional logs")
        response = requests.get(
            url=str_audit_url + str(response.links["next"].get("url")),
            headers=obj_headers_json,
            timeout=30,
        )
        if not check_response(response):
            logging.error("ERROR: Issue with API call during pagination")
            break
        obj_pg_response = json.loads(response.text)
        obj_rvnc_logs_json = {
            "events": obj_rvnc_logs_json["events"] + obj_pg_response["events"]
        }
    return obj_rvnc_logs_json.get("events", [])


def upload_to_log_analytics(arr_events):
    """
    Uploads the events to Microsoft Log Analytics via the Logs Ingestion API.

    Authenticates to Azure using a managed identity (DefaultAzureCredential),
    which resolves to the Function App's system-assigned identity in Azure and
    to local developer credentials (Azure CLI / VS Code) when running locally.

    Args:
        arr_events (list): The event logs to upload.

    Raises:
        RuntimeError: If required ingestion configuration is missing.
    """
    dcr_immutable_id = os.getenv("DCR_IMMUTABLE_ID")
    dce_uri = os.getenv("DCE_ENDPOINT")
    if not dcr_immutable_id or not dce_uri:
        raise RuntimeError(
            "DCR_IMMUTABLE_ID and DCE_ENDPOINT must both be set to ingest logs"
        )

    ingestion_client = LogsIngestionClient(endpoint=dce_uri, credential=_credential)
    ingestion_client.upload(
        rule_id=dcr_immutable_id, stream_name=STREAM_NAME, logs=arr_events
    )
    logging.info("Uploaded %d event(s) to %s", len(arr_events), TABLE_NAME)


def _event_ts(event):
    """Safely extracts an event's timestamp (epoch ms) as an int."""
    return int(event.get("timestamp", 0))


@app.timer_trigger(
    schedule="%SCHEDULE_NCRONTAB%",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def rvnc_portal_logs(timer: func.TimerRequest) -> None:
    """
    Timer-triggered entry point. Pulls RealVNC portal audit logs since the last
    checkpoint and forwards the new events to Log Analytics.
    """
    logging.info("----------------- RealVNC log run start -----------------")
    if timer.past_due:
        logging.warning("Timer is past due")

    bearer_token = get_rvnc_bearertoken()
    if not bearer_token:
        logging.error("Could not obtain bearer token; aborting run")
        return

    # Decide the window from the checkpoint, falling back to a bootstrap lookback.
    checkpoint = read_checkpoint()
    if checkpoint:
        from_ms = checkpoint["lastTimestamp"]
        seen_ids = checkpoint["seenIds"]
    else:
        from_ms = get_bootstrap_window()
        seen_ids = set()

    events = get_portal_logs(bearer_token, from_ms)
    # Drop any event already ingested at the checkpoint boundary (same id).
    new_events = [e for e in events if e.get("id") not in seen_ids]
    if not new_events:
        logging.info("No new events since last checkpoint")
        logging.info("----------------- RealVNC log run end -----------------")
        return

    upload_to_log_analytics(new_events)

    # Advance the watermark to the newest event time, remembering the ids that
    # occurred at that exact millisecond so the next run can skip them.
    new_max = max(_event_ts(e) for e in new_events)
    boundary_ids = {e.get("id") for e in new_events if _event_ts(e) == new_max}
    if checkpoint and new_max == checkpoint["lastTimestamp"]:
        # Only more same-millisecond events arrived; accumulate their ids.
        boundary_ids |= seen_ids
    write_checkpoint(new_max, boundary_ids)

    logging.info("----------------- RealVNC log run end -----------------")
