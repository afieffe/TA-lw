
# encoding = utf-8

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from laceworksdk import LaceworkClient
from laceworksdk.exceptions import ApiError, RateLimitError
from json import dumps
import concurrent.futures
import copy
from json_normalize import json_normalize

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

META_G=['START_TIME','REC_ID','STATUS','ASSESSED_RESOURCE_COUNT','SEVERITY','CATEGORY',"TITLE","LW_ORG"]
META_GCP=['PROJECT_ID','PROJECT_NAME','ORGANIZATION_ID','ORGANIZATION_NAME']
META_AZURE=['SUBSCRIPTION_ID','SUBSCRIPTION_NAME','TENANT_ID','TENANT_NAME']
META_AWS = ['ACCOUNT_ID','ACCOUNT_ALIAS']

META = { 'aws' : META_AWS  , 'azure' :  META_AZURE , 'gcp' : META_GCP  }
ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

LQL_ITEMS = { 'aws': 'lw_client.cloud_accounts.get_by_type(\"AwsCfg\")[\"data\"]' , 'gcp' :'self.get_gcp_project(lw_client)' , 'azure' : 'lw_client.configs.azure_subscriptions.get()[\"data\"]' }

#CLOUD_PROVIDERS=['aws','azure','gcp']
CLOUD_PROVIDERS=['aws','gcp' ]


REPORT_MAPPING= { 'aws' : { 'item1' : 'awsAccountId'} , 'azure' : { 'item1' : 'tenant' , 'item2' : 'subscriptions'}, 'gcp' : { 'item1' : 'ORGANIZATION_ID' , 'item2' : 'PROJECT_ID'} }

class lw_assesment:
    def __init__(self,report_name,lw_client,helper):
        self.lw_client = lw_client
        self.current = datetime.now(timezone.utc)
        self.start_time = (self.current - timedelta(hours=0, days=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.end_time = self.current.strftime('%Y-%m-%dT%H:%M:%SZ')
        self.lw_accounts = self.get_subaccount_list()
        #self.lw_accounts = ['randstad-au']
        self.max_threads=8
        self.cloud_providers=CLOUD_PROVIDERS
        self.helper=helper
        self.report_name=report_name

        self.reports_name= report_name
        self.providers_items=self.get_all_providers_items()
        #self.compliance=self.get_all_compliance()

    def get_subaccount_list(self):
        profile=self.lw_client.user_profile.get()
        sub_accounts=[]
        if profile:
            data=profile.get('data', None)
            for sub_account in  data[0]['accounts']:
                if sub_account['accountName'] not in sub_accounts:
                    sub_accounts.append(sub_account['accountName'])

        return sub_accounts

    def _build_gcp_project_query(self):
        query_text = '{ source { LW_CFG_GCP_CLOUDRESOURCEMANAGER_PROJECT }'
        query_text += ' return distinct { ORGANIZATION_ID  ,  PROJECT_ID  } }'

        return query_text

    def get_gcp_project(self,lw_client):
        results = lw_client.queries.execute(
        query_text=self._build_gcp_project_query(),
        arguments={
            'StartTimeRange':  self.start_time,
            'EndTimeRange': self.end_time,
        },)['data']

        return results

    def get_provider_items(self,sub_account,provider):
        arguments={}
        arguments["StartTimeRange"]=self.start_time
        arguments["EndTimeRange"]=self.end_time

        lw_client=copy.deepcopy(self.lw_client)
        lw_client.set_subaccount(sub_account)

        items=[]
        results=eval(LQL_ITEMS[provider])

        if  provider == 'azure':
            for item in results:
                for subitem in item[REPORT_MAPPING[provider]['item2']]:
                    if len(subitem) > 0 :
                        new_item={}
                        new_item[REPORT_MAPPING[provider]['item1']] = item[REPORT_MAPPING[provider]['item1']].split()[0]
                        new_item[REPORT_MAPPING[provider]['item2']] = subitem.split()[0]
                        new_item['CLOUD_PROVIDER']=provider
                        new_item['LW_ORG']=sub_account
                        items.append(new_item)
        elif provider == 'gcp':
            for item in results:
                new_item={}
                new_item[REPORT_MAPPING[provider]['item1']] = item[REPORT_MAPPING[provider]['item1']]
                new_item[REPORT_MAPPING[provider]['item2']] = item[REPORT_MAPPING[provider]['item2']]
                new_item['CLOUD_PROVIDER']=provider
                new_item['LW_ORG']=sub_account
                items.append(new_item)
        elif provider == 'aws':
            for item in results:
                new_item={}
                new_item[REPORT_MAPPING[provider]['item1']] = item['data'][REPORT_MAPPING[provider]['item1']]
                new_item['CLOUD_PROVIDER']=provider
                new_item['LW_ORG']=sub_account
                items.append(new_item)

        lw_client=None
        return items

    def get_all_providers_items(self):
        futures=[]
        items=[]

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_threads ) as executor:
            for provider in self.cloud_providers:
                for sub_account in self.lw_accounts:
                    self.helper.log_info(f'Getting items for {provider}, lw org:{sub_account}')
                    futures.append(executor.submit(self.get_provider_items,sub_account,provider))
            for future in concurrent.futures.as_completed(futures):
                    for res in future.result():
                       items.append(res)
        return items

    def get_report(self,sub_account,item1,item2,report_name,cloud_provider):
        recos=[]
        lw_client=copy.deepcopy(self.lw_client)
        lw_client.set_subaccount(sub_account)
        self.helper.log_info(f'Getting report {report_name}, lw org:{sub_account}, {item1}/{item2} ')
        try:
            recos=lw_client.reports.get(primary_query_id=item1,secondary_query_id=item2, type="COMPLIANCE", report_name=report_name, format="json",latest=True,templateName='DEFAULT')['data'][0]['recommendations']
            for i, d in enumerate(recos):
                    recos[i]['LW_ORG']=sub_account
                    recos[i]['collection_time']=self.end_time
        except Exception as e :
            self.helper.log_error(f'Error Getting report {report_name}, lw org:{sub_account}, {item1}/{item2} Exception: {e}')
        return (recos,cloud_provider)

    def get_all_compliance(self):
        futures=[]
        compliance={ }
        results={}
        scoring={}
        self.helper.log_info(f'Items {self.providers_items}')
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_threads) as pool:
            for item in self.providers_items:
                item1=item[REPORT_MAPPING[item['CLOUD_PROVIDER']]['item1']] if 'item1' in REPORT_MAPPING[item['CLOUD_PROVIDER']].keys() else None
                item2=item[REPORT_MAPPING[item['CLOUD_PROVIDER']]['item2']] if 'item2' in REPORT_MAPPING[item['CLOUD_PROVIDER']].keys() else None
                #for report_type in self.reports_type[item['CLOUD_PROVIDER']]:
                futures.append(pool.submit(self.get_report,item['LW_ORG'],item1,item2,self.report_name,item['CLOUD_PROVIDER']))
            for future in concurrent.futures.as_completed(futures):
                    recos,cloud_provider =future.result()
                    for rec in recos:
                        if cloud_provider not in compliance.keys() : compliance[cloud_provider]=[]
                        compliance[cloud_provider].append(rec)

        return compliance








def validate_input(helper, definition):
    """Implement your own validation logic to validate the input stanza configurations"""
    # This example accesses the modular input variable
    # collect_events = definition.parameters.get('collect_events', None)
    pass



def collect_events(helper, ew):
    global_account = helper.get_global_setting("account")
    global_sub_account = helper.get_global_setting("sub_account")
    global_account_key = helper.get_global_setting("account_key")
    global_key_secret = helper.get_global_setting("key_secret")
    input_org_level = helper.get_arg('org_level')
    report_name = helper.get_arg('report_name')
    helper.log_critical(f"org level {input_org_level}")
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

    assesment = lw_assesment(report_name,lw_client,helper)
    compliance=assesment.get_all_compliance()

    for cloud_provider in compliance.keys():
        for rec in compliance[cloud_provider]:
            helper.log_debug(f'compliance: {dumps(rec)}')
            if len(rec['VIOLATIONS'])>0:
                normal_rec = json_normalize(rec,drop_nodes=("SUPPRESSIONS",))
                for rec_event in list(normal_rec):
                    event = helper.new_event(source=helper.get_input_type(), index=helper.get_output_index(), sourcetype=helper.get_sourcetype(), data=dumps(rec_event), host=global_account)
                    ew.write_event(event)
            if len(rec['SUPPRESSIONS'])>0:
                normal_rec = json_normalize(rec,drop_nodes=("VIOLATIONS",))
                for rec_event in list(normal_rec):
                    event = helper.new_event(source=helper.get_input_type(), index=helper.get_output_index(), sourcetype=helper.get_sourcetype(), data=dumps(rec_event), host=global_account)
                    ew.write_event(event)
            if len(rec['SUPPRESSIONS'])==0 and len(rec['VIOLATIONS'])==0 :
                event = helper.new_event(source=helper.get_input_type(), index=helper.get_output_index(), sourcetype=helper.get_sourcetype(), data=dumps(rec), host=global_account)
                ew.write_event(event)



    """Implement your data collection logic here

    # The following examples get the arguments of this input.
    # Note, for single instance mod input, args will be returned as a dict.
    # For multi instance mod input, args will be returned as a single value.
    opt_collect_events = helper.get_arg('collect_events')
    # In single instance mode, to get arguments of a particular input, use
    opt_collect_events = helper.get_arg('collect_events', stanza_name)

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
