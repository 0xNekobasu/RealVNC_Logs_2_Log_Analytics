#!/usr/bin/env python3
"""
rvncPortalLogs.py

Calls RealVNC Portal API to pull logs and then pushes them to Microsoft log analytics

Usage (typically in crontab or other automation system e.g Jenkins):
    python3 rvncPortalLogs.py

Notes:
  - insert note here
"""
# Standard Libraries
import os
import logging
import json
import time
import urllib.parse

#Third Party Libraries
import requests
from dotenv import load_dotenv
from azure.identity import ClientSecretCredential
from azure.monitor.ingestion import LogsIngestionClient

def get_rvnc_bearertoken():
    """
    Calls the Real VNC portal Authentication API to obtain the bearer token.

    Args:
        None

    Returns:
        The bearer token used to authenticate with the RealVNC portal API   
    
    Raises:
        None
    """
    # Set variables and make the request to the RealVNC API Endpoint for obtaining a bearer token.
    strAuthUrl="https://connect-api.services.vnc.com/1.0/sessions"
    objBodyJson ={
        "accessKey":os.getenv("RVNC_API_KEY"),
        "accessKeyId":os.getenv("RVNC_API_KEY_ID"),
        "expiry":"PT30M" 
    }
    objHeadersJson = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    response = requests.post(strAuthUrl,json=objBodyJson,headers=objHeadersJson)
    # Check if the response is good or not 
    if check_response(response) == False:
        logging.error("ERROR: Issue with API CALL")
        logging.error(response)
        return response
    objParsedResponse = json.loads(response.text)
    return (objParsedResponse['token'])

def init_Logging():
    """
    Initialises the logging for the script.

    Args:
        None
    
    Returns:
        None
    
    Raises:
        Nothing (hopefully)
    """
    logger = logging.getLogger(__name__)
    logging.basicConfig(filename='rvncPortalLogs.log',format='%(asctime)s|%(levelname)s|%(message)s',encoding='utf-8',level=logging.DEBUG)
    #logging.debug("Logging Initialised")

def check_response(apiResponse):
    """
    Checks if an API Call returns a valid value or not. If not, throw error

    Args:
        API Response (apiResponse)

    Returns:
        Bool - True/False depending on result of check   
    
    Raises:
        ###    
    """
    if "201" in str(apiResponse) or "200" in str(apiResponse):
        logging.info("API Response returned correct")
        return True 
    else:
        logging.error("API Response error - request failed")
        return False

def set_log_time_window():
    """
        Generates the 15 minute time window which is for pulling a specific amount of audit logs.

    Args:
        None

    Returns:
        The unix time which dictates when the audit logs should be pulled from the RealVNC portal from.
    
    Raises:
        None
    """
    intUnixTime = int(time.time()*1000)
    intAuditStart = intUnixTime - 900000
    return intAuditStart

def get_portal_logs(bearerToken):
    """
    Calls the Real VNC portal audit api to pull the logs down, handles pagination also

    Args:
        Bearer token

    Returns:
        ### arrEvents - a python array containing each log line to ingest in the form of a python object. These lines will need to be json dumped before ingestion.
    
    Raises:
        None
    """
    # Setup the http request to call the audit logs
    strAuditUrl = "https://connect-api.services.vnc.com"
    objParametersJson={
        "order":"DESC"
        #"from":set_log_time_window()
    }
    objHeadersJson={
        "Accept":"application/json",
        "Authorization":f"Bearer {bearerToken}" # Generates the bearer token at this point.
    }
    response = requests.get(url=strAuditUrl+"/1.0/audit",headers=objHeadersJson,params=objParametersJson)
    if check_response(response) == False:
        logging.error("ERROR: Issue with API call for obtaining Audit logs")
        logging.error(response)
        return response
    objRVNCLogsJson = json.loads(response.text)
    #Pagination checks, will go and grab all the logs for the time period until we have no more left. 
    while (response.links):
        logging.info("Pagination detected, obtaining additional logs")
        response = requests.get(url=strAuditUrl+str(response.links['next'].get('url')),headers=objHeadersJson)
        objPgResponse = json.loads(response.text)
        objRVNCLogsJson = {
            'events':objRVNCLogsJson['events']+ objPgResponse['events'] #Merges any paginated log lines together
        }
    arrEvents = objRVNCLogsJson.get("events",[])
    return arrEvents # This is an array of pythonObjects

def upload_to_log_analytics(arrEvents):
    """
    uploads the logs to Microsoft Log Analytics.

    Args:
        arrEvents - python array of the event logs to upload in object format. 

    Returns:
        Complete Action. Script end.
    
    Raises:
        None
    """
    dcrImmutableID = os.getenv("DCR_IMMUTABLE_ID")
    table = "RealVNC_PortalLogs_CL"
    dceURI = os.getenv("DCE_ENDPOINT")
    streamName = "Custom-" + table

    # Get authed with Azure
    credential = ClientSecretCredential(os.getenv("AZURE_TENANT_ID"),os.getenv("AZURE_CLIENT_ID"),os.getenv("AZURE_CLIENT_SECRET"))
    
    # ADD A "CHECK IF THIS WORKED FUNCTION HERE"

    # setup ingestion client
    ingestionClient = LogsIngestionClient(endpoint=dceURI,credential=credential,logging_enable=True)
    # ADD A "CHECK IF THIS WORKED FUNCTION HERE"
    # shove logs to log Analytics
    ingestionClient.upload(rule_id=dcrImmutableID,stream_name=streamName,logs=arrEvents)


    #for logline in range(len(arrEvents)): # for each log line, convert to JSON and push to Log Analytics
    
        #arrLogLine= arrLogLine.append(json.dumps(arrEvents[logline]))
        #ingestionClient.upload(rule_id=dcrImmutableID,stream_name=streamName,logs=arrEvents)

def get_ms_bearer_token():
    """
    Gets the bearer credentials for authenticating with azure monitor ingestion Service principle

    Args:
        none 

    Returns:
        bearer token
    
    Raises:
        TBC
    """
    msURL = "https://login.microsoftonline.com/"+os.getenv("AZURE_TENANT_ID")+"/oauth2/v2.0/token"
    scope = urllib.parse.quote("https://monitor.azure.com//.default",safe='')
    objBody=(
        f"client_id={os.getenv("AZURE_CLIENT_ID")}"
        f"&scope={scope}"
        f"&client_secret={os.getenv("AZURE_CLIENT_SECRET")}"
        f"&grant_type=client_credentials"
    )
    objHeadersJson={
        "Content-Type":"application/x-www-form-urlencoded",
    }
    response = requests.post(url=msURL,headers=objHeadersJson,data=objBody)
    check_response(response)
    bearer=response.json()["access_token"]
    return bearer



####################################################
def __Main__():
    """
    Runs the python script
    """
    # Pre-requisite setup
    init_Logging()
    logging.debug("Logging setup complete")
    load_dotenv()
    logging.debug("dotEnvInitialised, Envrionment variables now available")
    # end pre-requisiste setup
    arrEvents = get_portal_logs(get_rvnc_bearertoken())
    upload_to_log_analytics(arrEvents)
    #get_ms_bearer_token()
####################################################
#  Run script. 
__Main__()
