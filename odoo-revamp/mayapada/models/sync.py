try:
    import ujson as JSON
except:
    import json as JSON

import subprocess
import multiprocessing
import requests

# from urllib import quote as encodeURI
from urllib import parse as encodeURI
from re import sub
from sys import _getframe
from odoo import fields


# Integration for External Apps
id = fields.Float(string="Sync ID", store=True, index=True)
id_big = fields.Float(string="Sync ID (Big Integers)", store=True, index=True)
id_api = fields.Char(string="Sync ID API", store=True, index=True)
date = fields.Datetime(string="Sync Date", index=True)
type = fields.Selection([
    ('1', 'Wipro MHJS'), 
    ('2', 'Wipro MHTG'), 
    ('3', 'Dhealth MHSB'), 
    ('4', 'New HIS MHJS'), 
    ('5', 'New HIS MHTG'), 
    ('6', 'Dhealth MHKN'), 
    ('7', 'Dhealth MHBG'), 
    ('8', 'Dhealth MHBD'), 
    ('9', 'HIS MHNS'), 
    ('10', 'MEC JS'),
    ('11', 'New HIS MHJT'),
    ('12', 'New HIS MABIH'),
    ('13', 'MMCK'),
    ('31', 'MHSB-BSL2'),
    ('32', 'MHSB-BSL2 Elimination'),
    ('33', 'MHSB-PT'), 
    ('34', 'MHTG-Corporate'),
    ('35', 'MHJS-Corporate'),
    ('999', 'Parent MHG')
], string="Sync Type", store=True, index=True)

# Integration to Internal Odoo
consol_id_unit = fields.Float(string="Console ID Unit", store=True, index=True, readonly=True)
consol_id_main = fields.Float(string="Console ID Main", store=True, index=True, readonly=True)
consol_type = fields.Selection([
    ('main', 'Odoo for Main Consolidation'), 
    ('unit', 'Odoo for Unit')], string="Consolodation Type", default='main', store=True, index=True)
consol_date = fields.Datetime(string="Console Date", index=True, readonly=True)
consol_sent = fields.Boolean(string="Data Sent To Consol", readonly=True)
consol_response_status = fields.Char(string="Console Response Status", index=True, readonly=True)
consol_response = fields.Text(string="Console Response", readonly=True)

# Integration Odoo X Arcus
is_arcus = fields.Boolean(string="Sync Is Arcus", default=False)

servers = {
    '1':'http://10.2.1.124:1510/api/query', 
    '2':'http://10.2.1.124:1511/api/query', 
    '3':'https://mayapada-cloud.andalsoftware.com/andalgatewaytest/api/'
}
cpu_count = multiprocessing.cpu_count()
customer_type = {}


def get_data(url, query, args=False, as_list=False):
    args = args or []
    #result = False
    #try:
    #    result = subprocess.check_output(['curl', '-g', url + '?api_key=m4y4p4d4juk34p1&query=' + encodeURI.quote(query) + '&args=' + json(args) + '&list=' + json(as_list)])
    #except Exception as error:
    #    print error
    try:
        if query == 'select CustomerTypeID, CustomerTypename from V_DBCustomerType' and customer_type.get(url):
            result = customer_type[url]
        else:
            result = requests.post(url, data={'api_key': 'm4y4p4d4juk34p1', 'query': query, 'args': json(args), 'list': json(as_list)}).text
            if query == 'select CustomerTypeID, CustomerTypename from V_DBCustomerType':
                customer_type[url] = result
        # result = subprocess.check_output(['wget', '-t', '1', '-T', '0', '-qO-', url + '?api_key=m4y4p4d4juk34p1&query=' + encodeURI.quote(query) + '&args=' + json(args) + '&list=' + json(as_list)])
        # result = subprocess.check_output(['wget', '-T', '0', '-qO-', url + '?api_key=m4y4p4d4juk34p1&query=' + encodeURI.quote(query) + '&args=' + json(args) + '&list=' + json(as_list)])
        # result = subprocess.check_output(['wget', '-T', '0', '-qO-', url + '?api_key=m4y4p4d4juk34p1&query=' + encodeURI.quote(query) + '&args=' + json(args) + '&list=' + json(as_list)])
    except Exception as error:
        if query == 'select CustomerTypeID, CustomerTypename from V_DBCustomerType':
            result = '{"status":"success","data":[{"CustomerTypeID":1,"CustomerTypename":"GOVERNMENT"},{"CustomerTypeID":2,"CustomerTypename":"INSURANCE"},{"CustomerTypeID":3,"CustomerTypename":"CORPORATE"},{"CustomerTypeID":4,"CustomerTypename":"EMPLOYEE"},{"CustomerTypeID":5,"CustomerTypename":"PT"},{"CustomerTypeID":6,"CustomerTypename":"ASURANSI"},{"CustomerTypeID":7,"CustomerTypename":"REFFERAL"},{"CustomerTypeID":8,"CustomerTypename":"BANK"},{"CustomerTypeID":9,"CustomerTypename":"PRIVATE CREDIT"},{"CustomerTypeID":10,"CustomerTypename":"GOVERMENT"}, {"CustomerTypeID":13,"CustomerTypename":"E-COMMERCE"}, {"CustomerTypeID":11,"CustomerTypename":"MAYAPADA"}]}'
        else:
            raise error

    if 'select CustomerType' not in query:
        open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + query + '\n' + str(result))
    if result:
        result = JSON.loads(result)
        if result['status'] == 'success':
            return result['data']
    return []



# def get_data_andal(url, sub, is_value=False, value=0):
#     key = "Bearer " + req_auth_key()
#     headers = {'Authorization': key}
#     fix_url = ''
#     if is_value:
#         fix_url = url + sub + value
#     else:
#         fix_url = url + sub

#     resp = requests.get(fix_url, headers=headers)

#     if resp.status_code == 200:
#         result = JSON.loads(resp.content)
#         # open('/etc/odoo/log_custom/report.log', 'w+').write(resp.content)
#         return result
#         # open('/etc/odoo/log_custom/report.log', 'w+').write('GAGAL : ' + key)
#     return []


# def get_data_andal_temp():
#     fix_url = 'http://103.44.27.111/emp-odoo.json'
#     headers = {'content-type': 'application/json', 'Accept-Charset': 'UTF-8'}
#     resp = requests.get(fix_url, headers=headers)

#     if resp.status_code == 200:
#         # result = JSON.loads(resp.content)
#         result = resp.json()
#         # open('/etc/odoo/log_custom/report.log', 'w+').write(resp.content)
#         return result
#         # open('/etc/odoo/log_custom/report.log', 'w+').write('GAGAL : ' + key)
#     return []


def get_data_master_referral_agen(self, StartDate, EndDate):
    # url = 'http://172.16.0.103:82/publics/doctor/doctor_external'
    url = self.env.company.api_backend_endpoint + '/doctor/doctor_external'
    token = 'Basic ' + self.env.company.api_backend_key
    headers = {'Authorization': token, 'content-type': 'application/json', 'Accept-Charset': 'UTF-8'}
    params = {'StartDate': StartDate, 'EndDate': EndDate}

    resp = requests.post(url, headers=headers, params=params)

    if resp.status_code == 200:
        result = resp.content
        # open('/opt/odoo16/logs/referral.log', 'w+').write(result)

        return result
        # open('/opt/odoo16/logs/referral.log', 'w+').write('GAGAL : ' + key)
    return []


def get_data_master_transaksi_agen(self, StartDate, EndDate):
    # url = 'http://172.16.0.103:82/publics/appointment/transaction_referral'
    url = self.env.company.api_backend_endpoint + '/appointment/transaction_referral'
    token = 'Basic ' + self.env.company.api_backend_key
    headers = {'Authorization': token, 'content-type': 'application/json', 'Accept-Charset': 'UTF-8'}
    params = {'StartDate': StartDate, 'EndDate': EndDate}

    resp = requests.post(url, headers=headers, params=params)
    
    if resp.status_code == 200:
        result = resp.content
        # open('/opt/odoo16/logs/referral.log', 'w+').write(resp.content)
        
        return result
        # open('/opt/odoo16/logs/referral.log', 'w+').write('GAGAL : ' + key)
    return []


def remove_unicode(string):
    return sub("u'([^']*)'", r'\1', string)


def json(data):
    return JSON.dumps(data)


def search(iterable, default=False):
    return next(iter(iterable), default)


def split_list(a, n):
    k, m = divmod(len(a), n)
    return (a[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in xrange(n))


getframe = _getframe