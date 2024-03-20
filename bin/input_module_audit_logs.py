# encoding = utf-8

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from laceworksdk import LaceworkClient
from json import dumps
from operator import itemgetter




def validate_input(helper, definition):
    """Implement your own validation logic to validate the input stanza configurations"""
    # This example accesses the modular input variable
    # org_level = definition.parameters.get('org_level', None)
    # alerts_categories = definition.parameters.get('alerts_categories', None)
    # alert_details = definition.parameters.get('alert_details', None)
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

def get_audit(lw_client,helper,ew,sub_account):
    current_time = datetime.now(timezone.utc)
    start_time = current_time - timedelta(hours=0, days=7)
    start_time = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_time = current_time
    end_time = end_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    lw_client.set_subaccount(sub_account)
    checkpoint_key=helper.get_input_stanza_names()+'-'+helper.get_global_setting("account")+'-'+sub_account
    checkpoint=helper.get_check_point(checkpoint_key)
    if (not checkpoint is None):
        start_time = checkpoint
        checkpoint = datetime.strptime(checkpoint,'%Y-%m-%dT%H:%M:%SZ')


    alerts=[]
    helper.log_debug(f'Stanza Name:{helper.get_input_stanza_names()}')
    query = {
        "timeFilter": {
            "startTime": start_time,
            "endTime": end_time
        },

        }
    a=lw_client.audit_logs.search(json=query)
    helper.log_info(a)
    for audit in a['data']:

        helper.log_debug(checkpoint)
        auditstmp = datetime.strptime(audit['createdTime'],'%Y-%m-%dT%H:%M:%SZ')
        helper.log_debug(auditstmp)

        if (checkpoint is None or auditstmp > checkpoint):
            checkpoint = auditstmp
            helper.log_debug(f'New checkpoint {checkpoint_key} : {checkpoint}')


    if (not checkpoint is None) :
        if (len(a['data'])> 0) :
            checkpoint = checkpoint + timedelta(seconds=1)
        helper.log_debug(f'Saving checkpoint {checkpoint_key} : {checkpoint}')
        helper.save_check_point(checkpoint_key, checkpoint.strftime('%Y-%m-%dT%H:%M:%SZ'))
    return a['data']



def collect_events(helper, ew):
    global_account = helper.get_global_setting("account")
    global_sub_account = helper.get_global_setting("sub_account")
    global_account_key = helper.get_global_setting("account_key")
    global_key_secret = helper.get_global_setting("key_secret")
    input_org_level = helper.get_arg('org_level')
    input_type = helper.get_input_type()


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
        alerts=[]
        for sub_account in sub_accounts:
            helper.log_debug(f"Iterating subaccount {sub_account}")
            lw_client.set_subaccount(sub_account)
            alerts=alerts + get_audit(lw_client,helper,ew,global_sub_account.lower())

    else:
        alerts = []
        if len(global_sub_account) == 0 :
            global_sub_account=global_account.split('.')[0]
        helper.log_debug(f"Iterating using current subaccount")
        alerts=get_audit(lw_client,helper,ew,global_sub_account.lower())

    for alert in alerts:
        event = helper.new_event(source=input_type, index=helper.get_output_index(), sourcetype=helper.get_sourcetype(), data=dumps(alert),  host=global_account)
        ew.write_event(event)

    """Implement your data collection logic here

    # The following examples get the arguments of this input.
    # Note, for single instance mod input, args will be returned as a dict.
    # For multi instance mod input, args will be returned as a single value.
    opt_org_level = helper.get_arg('org_level')
    opt_alerts_categories = helper.get_arg('alerts_categories')
    opt_alert_details = helper.get_arg('alert_details')
    # In single instance mode, to get arguments of a particular input, use
    opt_org_level = helper.get_arg('org_level', stanza_name)

    opt_alert_details = helper.get_arg('alert_details', stanza_name)

    # get input type
    helper.get_input_type()

    # The following examples get input stanzas.
    # get all detailed input stanzas
    helper.get_input_stanza()
    # get specific input stanza with stanza name
    helper.get_input_stanza(stanza_name)
    # get all stanza names
    helper.get_input_stanza_names()

    # The following examples get options from setup page configuration.
    # get the loglevel from the setup page
    loglevel = helper.get_log_level()
    # get proxy setting configuration
    proxy_settings = helper.get_proxy()
    # get account credentials as dictionary
    account = helper.get_user_credential_by_username("username")
    account = helper.get_user_credential_by_id("account id")
    # get global variable configuration
    global_account = helper.get_global_setting("account")
    global_sub_account = helper.get_global_setting("sub_account")
    global_account_key = helper.get_global_setting("account_key")
    global_key_secret = helper.get_global_setting("key_secret")

    # The following examples show usage of logging related helper functions.
    # write to the log for this modular input using configured global log level or INFO as default
    helper.log("log message")
    # write to the log using specified log level
    helper.log_debug("log message")
    helper.log_info("log message")
    helper.log_warning("log message")
    helper.log_error("log message")
    helper.log_critical("log message")
    # set the log level for this modular input
    # (log_level can be "debug", "info", "warning", "error" or "critical", case insensitive)
    helper.set_log_level(log_level)

    # The following examples send rest requests to some endpoint.
    response = helper.send_http_request(url, method, parameters=None, payload=None,
                                        headers=None, cookies=None, verify=True, cert=None,
                                        timeout=None, use_proxy=True)
    # get the response headers
    r_headers = response.headers
    # get the response body as text
    r_text = response.text
    # get response body as json. If the body text is not a json string, raise a ValueError
    r_json = response.json()
    # get response cookies
    r_cookies = response.cookies
    # get redirect history
    historical_responses = response.history
    # get response status code
    r_status = response.status_code
    # check the response status, if the status is not sucessful, raise requests.HTTPError
    response.raise_for_status()

    # The following examples show usage of check pointing related helper functions.
    # save checkpoint
    helper.save_check_point(key, state)
    # delete checkpoint
    helper.delete_check_point(key)
    # get checkpoint
    state = helper.get_check_point(key)

    # To create a splunk event
    helper.new_event(data, time=None, host=None, index=None, source=None, sourcetype=None, done=True, unbroken=True)
    """

    '''
    # The following example writes a random number as an event. (Multi Instance Mode)
    # Use this code template by default.
    import random
    data = str(random.randint(0,100))
    event = helper.new_event(source=helper.get_input_type(), index=helper.get_output_index(), sourcetype=helper.get_sourcetype(), data=data)
    ew.write_event(event)
    '''

    '''
    # The following example writes a random number as an event for each input config. (Single Instance Mode)
    # For advanced users, if you want to create single instance mod input, please use this code template.
    # Also, you need to uncomment use_single_instance_mode() above.
    import random
    input_type = helper.get_input_type()
    for stanza_name in helper.get_input_stanza_names():
        data = str(random.randint(0,100))
        event = helper.new_event(source=input_type, index=helper.get_output_index(stanza_name), sourcetype=helper.get_sourcetype(stanza_name), data=data)
        ew.write_event(event)
    '''
