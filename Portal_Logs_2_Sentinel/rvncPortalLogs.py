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

#Third Party Libraries
import requests
from dotenv import load_dotenv


#load_dotenv()
#key= os.getenv("SECRET_KEY")
#print(key)




def __Main__():
    print("do something")
### Run script. 
__Main__()
