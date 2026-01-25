# Ingest RealVNCAuditLogs to Sentinel SIEM
import time
import logging
import datetime
import ast
import json
import requests as req
import os
from azure.monitor.ingestion import LogsIngestionClient
from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential

#REALVNCENVIRONMENT VARS
enRVNCAccessKey=os.getenv('REALVNC_ACCESS_KEY')
enRVNCAccessKeyID=os.getenv('REALVNC_ACCESS_KEY_ID')

#AZURE ENVRIONMENT VARS

#global Vars

#Get bearer token to authenticate with realVNC API's
###################################################################################
## Functions which can be called with no requirement to pass information through ##
###################################################################################
def get_bearer_token():
    reqUrl="https://connect-api.services.vnc.com/1.0/sessions"
    authJson = {
        "accessKey":enRVNCAccessKey,
        "accessKeyId":enRVNCAccessKeyID,
        "expiry":"PT30M"
    }
    authHeaders={
        'Content-Type':'application/json',
        'Accept': 'application/json'
    }
    response = req.post(reqUrl,json=authJson,headers=authHeaders)
    if responseCheck(response) == False:
        #logging.info('Error: '+response)
        return response
    decodedResponse = json.loads(response.text)
    #print (decodedResponse['token'])
    #logging.info(decodedResponse)
    return (decodedResponse['token'])

def responseCheck(response):
    if "201" in str(response) or "200" in str(response):
        #print("theresponse is true")
        return True
    #write stuff to log file here or do something else
    else:
        #print("the response is false")
        return False
    #write stuff to log file here or do something else

def getUnixLogTime():
    unixMSTime = int(time.time()*1000)
    auditTimestamp = unixMSTime - 900000
    #auditTimestamp = unixMSTime -1000000
    return auditTimestamp


#returns audit logs in the form of a raw JSON obtained from the realVNCAPI
def getAuditLogs():
    url="https://connect-api.services.vnc.com"
    
    #auditLogTime = getUnixLogTime
    reqParams={
        'order':'DESC',
        'from':getUnixLogTime()
        #'to':''
    }
    reqHeaders={
        'Accept':'application/json',
        'Authorization':f'Bearer {get_bearer_token()}'
    }
    response=req.get(url=url+"/1.0/audit",headers=reqHeaders,params=reqParams)
    if responseCheck(response) == False:
        #logging.info('Error: '+response)
        return response
    #print (json.loads(response.text))
    #print (type(response.text))
    #print (json.loads(response.text))
    ## get the data from paginated urls and then add them to a big array which contains all the json data.
    #print (response.links['next'].get('url'))
    #while response.links['next'].get('rel') != 'None': #need to change this to be "while this exists in the headers instead of a value cause otherwise it breaks on the last loop."
    finLog = (json.loads(response.text))
    while (response.links):
        #print ("oi we got a pagination!")
        #the request URL
        #newurl= url+ str((response.links['next'].get('url')))
        response = req.get(url=url+ str((response.links['next'].get('url'))),headers=reqHeaders)
        #print (response.links['next'].get('url'))
        pgResponse = (json.loads(response.text))
        #print ("respoonse:",pgResponse)
        #print (type(pgResponse))
        finLog = {
            'events':finLog['events'] + pgResponse['events']
        }
    #print (finLog)
    #print (type(finLog))
    #print (type(finLog['events']))
    #print (finLog)
    #print(finLogArr)
    #print(type(finLogArr))
    #print (response)
    #print (response.links)
    #for event in finLog['events']:
    #    print (event.get('description'))
    #    #rint (finLog['events'].get('description')[i])
    for event in finLog.get('events',[]):
        
        desc = event.get('description')
        #print ("old ",desc)
        if isinstance(desc,str) and "'" in desc:
            event['description'] = desc.replace("'s","")
        #print ("new ",event['description'])


    #print (finLog)    
    
        
        
        #if "'" in desc:
        #    print(f"contains single quote: {desc}")
        #else:
        #    print (f"No single quote: {desc}")

    return (finLog)
    #print (decodedresponse)

#Create an Array of all the audit logs which will be used to ingest logs line by line by the function "pushToSentinel"
#Returns an Array of the audit logs 
def constructLogArr(auditLogsJson):
    #Dont ask why it does this
    auditLogsArr = []
    for events in auditLogsJson['events']:
        auditLogsArr.append(json.dumps(events))
    #Now conver that into a json list again (i dont understand JSON and python well enough to just pull them all out of "events")
    json_list = []
    for row in auditLogsArr:
        #print (row)
        #print (type(row))
        #match = re.search(r'"description"\s*:\s*"([^"]*?)"\s*,',row)
        #extractedDesc = match.group(1)
        #if ("'" in extractedDesc):
            #print(extractedDesc, "contains a single quote")

        
        #print ("extracted Description",extractedDesc)


        json_list.append(json.loads(row))
        
        
    #print("JSON_LIST:", json_list)
    #print(type(json_list))
    #print (json_list)
    return json_list


def pushToSentinel(auditLogsArr):
    #print (len(auditLogsArr))
    #print(type(auditLogsArr))
    dcrImmutableID = "dcr-0930e8d0344e47038d59196dda3b7e97"
    logtable = "realVNC_AuditLog_CL"
    dceURI = "https://123-realvnc-auditlogs-3pz2.uksouth-1.ingest.monitor.azure.com"
    stream_name = "Custom-" + logtable
    #There are environment variables which will automatically get yoinked to use this function
    credential = DefaultAzureCredential()
    #The credential here should be a bearer/auth token which can be nabbed by a service principle, unsure why we cant just launch that into the value...maybe we can?
    client = LogsIngestionClient(endpoint=dceURI,credential=credential)
    for i in range(len(auditLogsArr)):
        #print ("raw values from Function")
        #print (auditLogsArr[i])
        #print (type(auditLogsArr[i]))
        
        conversionLine = ast.literal_eval(str(auditLogsArr[i]))
        convertedJsonLine = json.dumps(conversionLine,ensure_ascii=False)
        #print ("converted JSon (new method)")
        #print(convertedJsonLine)
        #print (type(convertedJsonLine))
        #logstring = str(auditLogsArr[i])
        #logLine= "["+logstring+"]"
        logLine= "["+convertedJsonLine+"]"
        #do silly stuff to the logline
        #newstr = logLine.replace("'",'"')
        logLine = logLine.replace("timestamp","unixTimestamp")
        #print (logLine)
        #print (logLine)
        #print (newstr)
        #print(newstr)
        




        #print (newstr)
        #print ("this is the JsonJSON")
        #jsonJson= json.loads(convertedJsonLine)
        #print(jsonJson)
        #print ("this is the JSON String (final output)")
        json_str= json.loads(logLine)
        print (json_str)
        #print (jsonstr)
        #print (str)
        #print(type(logstring))a
        #upLog = json.loads(logstring)
        #print("trying to upload Log line: ",logstring,type(jsonstr))
        #print(jsonstr)
        client.upload(rule_id=dcrImmutableID,stream_name=stream_name,logs=json_str)



################################################################################
def __main__():
    constructedArr=(constructLogArr(getAuditLogs()))
    #print (constructedArr)
    #print (type(constructedArr))
    pushToSentinel(constructedArr)

    #print (myArr)
    #print (type(myArr))
    #print (len(myArr))
    #for i in range(len(myArr)):
    #    print("logLine: ",myArr[i])


    #get_bearer_token()


#############
__main__()