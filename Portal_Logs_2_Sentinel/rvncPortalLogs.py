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
    # INSERT response checking function here
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
