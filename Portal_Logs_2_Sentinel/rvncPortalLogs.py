#!/usr/bin/env python3
"""
rvncPortalLogs.py

Calls RealVNC Portal API to pull logs and then pushes them to Microsoft Sentinel SIEM

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

#Third Party Libraries
import requests
from dotenv import load_dotenv

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
        ### A VERSION OF THE LOGS WHICH IS THEN PUSHED INTO SENTINEL   
    
    Raises:
        None
    """
    # Setup the http request to call the audit logs
    strAuditUrl = "https://connect-api.services.vnc.com/1.0/audit"
    objParametersJson={
        "order":"DESC",
        "from":set_log_time_window()
    }
    objHeadersJson={
        "Accept":"application/json",
        "Authorization":f"Bearer {get_rvnc_bearertoken()}" # Generates the bearer token at this point.
    }
    response = requests.get(strAuditUrl,headers=objHeadersJson,params=objParametersJson)
    if check_response(response) == False:
        logging.error("ERROR: Issue with API call for obtaining Audit logs")
        logging.error(response)
        return response
    


####################################################
def __Main__():
    """
    Runs the python script
    """
    # Pre-requisite setup
    init_Logging()
    logging.debug("Logging setup")
    load_dotenv()
    logging.debug("dotEnvInitialised")
    # end pre-requisiste setup
    get_rvnc_bearertoken()


####################################################
#  Run script. 
__Main__()
