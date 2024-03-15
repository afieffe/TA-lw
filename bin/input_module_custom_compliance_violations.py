
# encoding = utf-8

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from laceworksdk import LaceworkClient
from laceworksdk.exceptions import ApiError, RateLimitError
from json import dumps

'''
    IMPORTANT
    Edit only the validate_input and collect_events functions.
    Do not edit any other part in this file.
    This file is generated only once when creating the modular input.
'''
'''
# For advanced users, if you want to create single instance mod input, uncomment this method.
def use_single_instance_mode():
    return True
'''

def validate_input(helper, definition):
    """Implement your own validation logic to validate the input stanza configurations"""
    # This example accesses the modular input variable
    # collect_events = definition.parameters.get('collect_events', None)
    pass

def get_subaccount_list(lw_client):
    profile=lw_client.user_profile.get()
    sub_accounts=[]
    if profile:
        data=profile.get('data', None)
        for sub_account in  data[0]['accounts']:
            if sub_account['accountName'] not in sub_accounts:
                sub_accounts.append(sub_account['accountName'])
    
    return sub_accounts

def get_compliance_query():
 

    query = {
        "timeFilter": {
            "startTime": start_time,
            "endTime": end_time
        },
        "csp": "AWS",
        "dataset": "AwsCompliance"
    }

    return query
    
def get_events(lw_client,helper,ew,global_account,sub_account):
    queries=[]
    policies=lw_client.policies.get()
    current_time = datetime.now(timezone.utc)
    start_time = current_time - timedelta(hours=0, days=1)
    start_time = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_time = current_time 
    end_time = end_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    for pol in policies['data']:
    
        if 'queryId' in pol.keys() and not 'CloudTrailRawEvents' in pol['queryText']  and not pol['queryId'] in queries and not pol['policyId'].startswith('lacework-global-') :
            
            queries.append(pol)
    
    for query in queries:
    
        results=lw_client.queries.execute_by_id(query['queryId'],    arguments={
        'StartTimeRange': start_time,
        'EndTimeRange': end_time })
    
        for event in results['data']:
                event['policy']=query['queryId']
                event['severity']=query['severity']
                event = helper.new_event(source=helper.get_input_type(), index=helper.get_output_index(), sourcetype=helper.get_sourcetype(), data=dumps(event), host=global_account.lower()+'-'+sub_account.lower())
                ew.write_event(event)

def collect_events(helper, ew):
    global_account = helper.get_global_setting("account")
    global_sub_account = helper.get_global_setting("sub_account")
    global_account_key = helper.get_global_setting("account_key")
    global_key_secret = helper.get_global_setting("key_secret")
    input_org_level = helper.get_arg('org_level')

    #helper.log("log message")
    # write to the log using specified log level

    try:
        lw_client = LaceworkClient(
            account = global_account,
            subaccount= global_sub_account,
            api_key = global_account_key,
            api_secret = global_key_secret
        )
    except Exception:
        helper.log_critical(f"Cannot connect to {global_account}")
        raise
    helper.log_info('Getting sub-accounts')
    sub_accounts=get_subaccount_list(lw_client)

    if input_org_level:
        
        for sub_account in sub_accounts:
            helper.log_debug(f"Iterating subaccount {sub_account}")
            lw_client.set_subaccount(sub_account)
            get_events(lw_client,helper,ew,global_account,sub_account)
    else:
        if len(global_sub_account) == 0 :
            global_sub_account=global_account.split('.')[0]
        