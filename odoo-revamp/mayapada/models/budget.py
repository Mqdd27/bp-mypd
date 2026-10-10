from odoo import models, fields, api, tools, exceptions
#import datetime

from datetime import datetime, timedelta

from collections import OrderedDict
from odoo.exceptions import UserError, ValidationError, Warning
import requests
import json
try:
    import ujson as JSON
except:
    import json as JSON

from xlrd import open_workbook
import re
import io
import csv
import hashlib
import base64
from . import sync


class Budget(models.Model):
    _inherit = 'crossovered.budget'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    #status = fields.Selection([('cancelled', "Cancelled"), ('draft', "Draft"), ('confirmed', "Confirmed"), ('financial', "Approved by Financial Director"), ('managing', "Approved by Managing Director"), ('coo', "Approved by COO"), ('president', "Approved by President"), ('done', "Done")], string="Status", readonly=True, default='draft')
    total_budget = fields.Float(string="Total Budget")
    remaining_budget = fields.Float(string="Remaining Budget",readonly=True, compute='_remain',store=True)
    remaining_amount = fields.Float(string="Remaining Amount",readonly=True, compute='_remain',store=True)
    allocated_amount = fields.Float(string="Unallocated Amount",readonly=True, compute='_remain',store=True)
    #type_budget = fields.Many2one('budget.type', string="Budget Type")

    history_ids = fields.One2many('budget.history','budget_id', string="Budget Approval", readonly=True)
    parent = fields.Boolean(string="Is Parent",readonly=True, default=True, compute='_parent', store=True)
    parent_id = fields.Many2one('crossovered.budget',string="Parent", domain=[('state', '!=', 'done')])
    child_ids = fields.One2many('crossovered.budget','parent_id', string="Childs", readonly=True)
    user_ids = fields.Many2many('res.users', relation='crossovered_budget_res_users_rel', string="Member")
    type_id = fields.Many2one('budget.type',string="Budget Type",required=False)
    #status = fields.Selection([('cancelled', "Cancelled"), ('draft', "Draft"), ('confirmed', "Confirmed"),  ('waiting', "Waiting for Approval"), ('approved', "Approved"), ('done', "Done")], string="Status", readonly=True, default='draft')
    remarks = fields.Char(string="Cancel Remarks")
    year = fields.Selection([
        ('FY17', "FY17"),
        ('FY18', "FY18"),
        ('FY19', "FY19"),
        ('FY20', "FY20"),
        ('FY21', "FY21"),
        ('FY22', "FY22"),
        ('FY23', "FY23"),
        ('FY24', "FY24"),
        ('FY25', "FY25"),
        ('FY26', "FY26"),
        ('FY27', "FY27"),
        ('FY28', "FY28"),
        ('FY29', "FY29"),
        ('FY30', "FY30"),
        ('FY31', "FY31"),
        ('FY32', "FY32"),
        ('FY33', "FY33"),
        ('FY34', "FY34"),
        ('FY35', "FY35"),
        ('FY36', "FY36"),
        ('FY37', "FY37"),
        ('FY38', "FY38"),
        ('FY39', "FY39"),
        ('FY40', "FY40"),
    ], string="Fiscal Year", readonly=False, required=False, domain=[('state', '=', 'draft')])
    used_percent = fields.Float(string="Amount Already Spent", readonly=True, compute='_remain', store=True)
    allocated_percent = fields.Float(string="Allocated Percent", readonly=True, compute='_remain', store=True)
    
    state = fields.Selection([
        ('draft', 'Draft'), 
        ('cancel', 'Cancelled'),
        ('confirm', 'Waiting for Approval'),
        ('validate', 'Approved'), 
        ('done', 'Done')], 'Status', 
        default='draft', index=True, required=True, readonly=True, copy=False, tracking=True)

    approve_user_ids = fields.Many2many('res.users', relation='crossovered_budget_res_users2_rel', string="Approval Users", compute='_approval',store=True)
    approve_id = fields.Many2one('budget.approval', string="Approval Level Rule", readonly=True, compute='_approval', store=True)
    approve_rule_id = fields.Many2one('budget.approval.rule', string="Approval Status", readonly=True)
    # approve_status = fields.Char(string="Approval Status", readonly=True, related='approve_rule_id.position_id.name', store=True)
    approve_status = fields.Char(string="Approval Status",readonly=True)
    approve_next = fields.Char(string="Next Approval", readonly=True, compute='_approval')
    approve_next_store = fields.Char(string="Stored Next Approval", readonly=False, store=True, index=True)
    end_approval = fields.Char(string="End Approval", compute="_get_end_approval")
    no_approval = fields.Boolean(string="No Approval", states={'posted':[('readonly', True)], 'reconciled':[('readonly', True)]})
    approved_bool = fields.Boolean(string="Approved")

    current_user_position = fields.Char(string="Current Position",compute='_get_current_position')
    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

    creating_user_id = fields.Many2one('res.users', string="Create User", readonly=True)
    

    # @api.multi
    def function_consol(self, function=False):
        for record in self:
            consol_active = record.company_id.sync_consol_crossovered_budget
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            name_function = function
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/call_function/unit/crossovered.budget"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/call_function/main/crossovered.budget"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                # self.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                login_user = self.env.user.login
                password_user = self.env.user.password_consol
                self.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                
                headers = {}
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = {}
                body['csrf_token'] = self.env.user.token_consol
                # body['ids'] = self.env.user[consol_id_from]
                body['ids'] = record.id
                # body['arguments'] = (new_passwd)
                body['function'] = name_function
                cookies = {'session_id': self.env.user.cookies}
                print(body)
                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                json_resp = response_json.json()
                # self.env.user.sync_consol_response = json_resp



    @api.model
    def create(self, vals):
        result = super(Budget, self).create(vals)
        if vals.get('company_id'):
            company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
            result.sync_type = company_id.sync_type

        if result.trigger_create == False:
            result.send_api_consol_company()
            for tes_loop in result.crossovered_budget_line:
                tes_loop.send_api_consol_company()
        return result




    # @api.multi
    def send_api_consol_company(self):
        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "create budget")
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_crossovered_budget
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/crossovered.budget"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/crossovered.budget"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                
                headers = {}
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = {}
                body['csrf_token'] = record.env.user.token_consol
                values = {}
                lst = []
                values['sync_type'] = record.company_id.sync_type
                values[consol_id_from] = str(record.id)
                values['name'] = str(record.name)

                if record.company_id.id == False:
                    values['company_id'] = record.company_id.id
                else:
                    values['company_id'] = str(record.company_id.id)

                if record.creating_user_id.id == False:
                    values['creating_user_id'] = record.creating_user_id.id
                else:
                    values['creating_user_id'] = str(record.creating_user_id.id)

                values['year'] = str(record.year)
                values['date_from'] = record.date_from
                values['date_to'] = record.date_to
                values['remarks'] = record.remarks
                values['total_budget'] = record.total_budget

                if record.type_id.id == False:
                    values['type_id'] = record.type_id.id
                else:
                    values['type_id'] = str(record.type_id.id)
                values['trigger_create'] = True


                lst.append(values)
                body['values'] = json.dumps(lst)
                # body['values'] = json.dumps(values)
                
                cookies = {'session_id': record.env.user.cookies}
                print('\n' + "body : " + str(body))
                print('\n' + "headers : " + str(headers))
                print('\n' + "url : " + str(url))

                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                print (response_json.status_code)
                if response_json.status_code != 200:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                try:
                    json_resp = response_json.json()
                except:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    json_resp = response_json.json()
                    
                api_status = 'failed'
                print('\n' + "json_resp : " + str(json_resp))

                data_sent = False
                response_id = False

                if 'status' in json_resp:
                    if json_resp['status'] == 'success':
                        api_status = 'success'
                        data_sent = True
                        if json_resp['data']['id']:
                            response_id = json_resp['data']['id']
                        # for d in json_resp['data']:
                        #     if 'id' in d:
                        #         response_id = d['id']
                    if json_resp['status'] == 'error':
                        # raise exceptions.ValidationError(_('Data Gagal Dibuat'))
                        raise exceptions.ValidationError(_(json_resp['message']))


                data_update = {
                    consol_id_to : response_id,
                    # 'sync_consol_response': json_resp,
                    # 'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    # 'sync_consol_sent' : data_sent
                }
                super(Budget, self).write(data_update)





    # @api.multi
    def send_api_consol_write_company(self):
        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "write budget")
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_crossovered_budget
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/crossovered.budget"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/crossovered.budget"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                headers = {}
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = {}
                body['csrf_token'] = record.env.user.token_consol
                values = {}
                lst = []
                values['sync_type'] = record.company_id.sync_type
                values[consol_id_from] = str(record.id)
                values['name'] = str(record.name)

                if record.company_id.id == False:
                    values['company_id'] = record.company_id.id
                else:
                    values['company_id'] = str(record.company_id.id)

                if record.creating_user_id.id == False:
                    values['creating_user_id'] = record.creating_user_id.id
                else:
                    values['creating_user_id'] = str(record.creating_user_id.id)

                values['year'] = str(record.year)
                values['date_from'] = record.date_from
                values['date_to'] = record.date_to
                values['remarks'] = record.remarks
                values['total_budget'] = record.total_budget

                if record.type_id.id == False:
                    values['type_id'] = record.type_id.id
                else:
                    values['type_id'] = str(record.type_id.id)
                values['trigger_write'] = False

                
                lst.append(values)
                body['values'] = json.dumps(lst)
                # body['values'] = json.dumps(values)
                
                cookies = {'session_id': record.env.user.cookies}

                print('\n' + "body : " + str(body))
                print('\n' + "headers : " + str(headers))
                print('\n' + "url : " + str(url))

                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                print (response_json.status_code)
                if response_json.status_code != 200:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                try:
                    json_resp = response_json.json()
                    
                except:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    json_resp = response_json.json()
                    
                api_status = 'failed'
                print('\n' + "json_resp : " + str(json_resp))

                data_sent = False
                response_id = False

                if 'status' in json_resp:
                    if json_resp['status'] == 'success':
                        api_status = 'success'
                        data_sent = True
                        if json_resp['data']['id']:
                            response_id = json_resp['data']['id']
                        # for d in json_resp['data']:
                        #     if 'id' in d:
                        #         response_id = d['id']
                    if json_resp['status'] == 'error':
                        # raise exceptions.ValidationError(_('Data Gagal Diedit'))
                        raise exceptions.ValidationError(_(json_resp['message']))


                data_update = {
                    consol_id_to : response_id,
                    # 'sync_consol_response': json_resp,
                    # 'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    # 'sync_consol_sent' : data_sent
                }
                super(Budget, self).write(data_update)




    @api.onchange('sync_type', 'name','creating_user_id','year','date_from','date_to','remarks','total_budget')
    def onchange_trigger_write(self):
        self.trigger_write = True




    # @api.one
    def _get_end_approval(self):
        record = self.sudo()
        end_approval = ''
        for at in record.type_id.approval_ids:
            if at.min_amount <= record.total_budget and at.max_amount >= record.total_budget:
                for apv in at.rule_ids:
                    end_approval = apv.position_id.name
        record.end_approval = end_approval




    # @api.one
    def _get_current_position(self):
        for rec in self:
            rec.current_user_position = self.env.user.position_id.name




    # @api.one
    def _approval(self):
        for record in self:
            planned = record.total_budget or 0.0
            approval = record.env['budget.approval'].sudo()

            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "_approval 1 " + str(approval))
            record.approve_id = approval.search([('id', 'in', record.type_id.approval_ids.ids),('max_amount', '>=', planned), ('min_amount', '<=', planned)],limit=1).id or None 
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "_approval 2 " + str(self.approve_id))
            if record.approve_id:
                # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "_approval 3 " + str(self.approve_id.rule_ids))
                rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
                # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "_approval 4 " + str(rule_ids))
                if not record.approve_rule_id:
                    record.approve_next = rule_ids[0].position_id.name
                else:
                    rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                    if rule_id:
                        if len(rule_id) > 1:
                            raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                        record.approve_next = rule_id.position_id.name
                        # 2021.04.12 >> tambahan firgi auto-update next_store
                        record.approve_next_store = "Completed"
                    else:
                        record.approve_next = "Completed"
                        record.approved_bool = True
                        # 2021.04.12 >> tambahan firgi auto-update next_store
                        record.approve_next_store = "Completed"
            else:
                record.approve_next = ''


    # @api.one
    @api.depends('child_ids')
    def _parent(self):
        for record in self:
            if record.child_ids:
                record.parent = True
            else:
                record.parent = False




    # 2021.10.02 - improve sum total by query
    # @api.one
    def _remain(self):
        for record in self:
            if record.crossovered_budget_line:
                planned = 0
                practical = 0
                total = 0

                # for line in self.crossovered_budget_line:
                #     planned += line.planned_amount
                #     practical += line.pr_amount + line.po_amount + line.practical_amount + line.paid_amount

                query = """
                    select 
                        coalesce(sum(coalesce(planned_amount,0)),0) planned_amount,
                        coalesce(sum(coalesce(grn_amount,0)),0) grn_amount,
                        coalesce(sum(coalesce(practical_amount,0)),0) practical_amount,
                        coalesce(sum(coalesce(paid_amount,0)),0) paid_amount,
                        coalesce(sum(coalesce(other_amount,0)),0) other_amount
                    from crossovered_budget_lines 
                    where crossovered_budget_id = {budget_id} 
                """.format(budget_id = record.id)
                record.sudo().env.cr.execute(query)
                results = record.sudo().env.cr.dictfetchall()
                if results:
                    planned += results[0]['planned_amount']
                    practical +=  results[0]['grn_amount'] + results[0]['practical_amount'] + results[0]['paid_amount'] + results[0]['other_amount']
                
                for child in record.child_ids:
                    total += child.total_budget
                
                #if self.total_budget == 0:
                #   self.write({'total_budget': planned})
                if planned < 0:
                    planned = -planned
                if practical < 0:
                    practical = -practical

                record.remaining_budget = record.total_budget - planned
                record.remaining_amount = record.total_budget - practical
                record.allocated_amount = record.total_budget - total

                if practical and record.total_budget:
                    record.used_percent = practical / record.total_budget * 100

                if planned and record.total_budget:
                    record.allocated_percent = planned / record.total_budget * 100




    # @api.multi
    def ask_approve(self):
        for record in self:
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "ASK APPROVE non consol")
            record.function_consol(function="ask_approve_consol")
            record.trigger_write == False
            planned = record.total_budget
            if record.type_id == False:
                raise exceptions.ValidationError("Fill Budget Type Before Ask Approve!!")

            # if len(record) > 1: return [record.ask_approve() for record in self][0]
            record.approve_status = 'Waiting for Approval'
            record.state = 'confirm'

            record = record.sudo()
            # record.subscribe_approval()

            now = (tools.datetime.now() + tools.timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
            approval_link = "https://erp.ad.mayapadahospital.com/web#min=1&limit=80&view_type=list&model=account.payment&menu_id=565&action=689"

            record.message_post(body='Please Approve This Budget, ' + 'Asked by ' +record.env.user.name + " at " + now + '\n' +"Please Click This Link To Approve " + approval_link,message_type='notification',content_subtype='plaintext',subtype_xmlid='mail.mt_comment',approval_link_payment=True)
            approval = record.env['budget.approval'].sudo()

            record.approve_id = approval.search([('id', 'in', record.type_id.approval_ids.ids),('max_amount', '>=', planned), ('min_amount', '<=', planned)],limit=1)
            if record.approve_id:
                rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
                if not record.approve_rule_id:
                    record.approve_next_store = rule_ids[0].position_id.name
                else:
                    rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                    if rule_id:
                        if len(rule_id) > 1:
                            raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                        record.approve_next_store = rule_id.position_id.name
                    else:
                        record.approve_next_store = "Completed"
                        record.approved_bool = True




    # @api.multi
    def ask_approve_consol(self):
        for record in self:
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "ASK APPROVE consol")
            query = """
                UPDATE crossovered_budget set trigger_write = 'f'
                WHERE id = %s""" % (record.id)

            record.env.cr.execute(query)
            record.env.cr.commit()

            # self.trigger_write == False
            planned = record.total_budget
            if record.type_id == False:
                raise exceptions.ValidationError("Fill Budget Type Before Ask Approve!!")

            # if len(self) > 1: return [record.ask_approve() for record in self][0]
            record.approve_status = 'Waiting for Approval'
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "LEWAT APPROVE consol 1")
            record.state = 'confirm'
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "LEWAT APPROVE consol 2")


            record = record.sudo()
            # record.subscribe_approval()
            now = (tools.datetime.now() + tools.timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
            approval_link = "https://erp.ad.mayapadahospital.com/web#min=1&limit=80&view_type=list&model=account.payment&menu_id=565&action=689"
            record.message_post(body='Please Approve This Budget, ' + 'Asked by ' +record.env.user.name + " at " + now + '\n' +"Please Click This Link To Approve " + approval_link,message_type='notification',content_subtype='plaintext',subtype_xmlid='mail.mt_comment',approval_link_payment=True)

            approval = record.env['budget.approval'].sudo()
            record.approve_id = approval.search([('id', 'in', record.type_id.approval_ids.ids),('max_amount', '>=', planned), ('min_amount', '<=', planned)],limit=1)
            
            if record.approve_id:
                rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
                if not record.approve_rule_id:
                    record.approve_next_store = rule_ids[0].position_id.name
                else:
                    rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                    if rule_id:
                        if len(rule_id) > 1:
                            raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                        record.approve_next_store = rule_id.position_id.name
                    else:
                        record.approve_next_store = "Completed"
                        record.approved_bool = True



    # @api.multi
    def act_new(self):
        for record in self:
            date_from = (tools.datetime.strptime(record.date_from, '%Y-%m-%d') + tools.timedelta(days=365)).strftime('%Y-%m-%d')
            date_to = (tools.datetime.strptime(record.date_to, '%Y-%m-%d') + tools.timedelta(days=365)).strftime('%Y-%m-%d')
            year = OrderedDict(record.env['crossovered.budget']._fields['year'].selection)._OrderedDict__map[record.year][1][2]
            new = {
                'name': record.name,
                'creating_user_id': record.creating_user_id.id,
                'date_from': date_from,
                'date_to': date_to,
                'type_id': record.type_id.id,
                'total_budget': record.remaining_amount,
                'year': year
            }
            budget_id = record.sudo().env['crossovered.budget'].create(new)
            budget_id.user_ids = record.user_ids
            for line in record.crossovered_budget_line:
                analytic_name = line.analytic_account_id.name
                if analytic_name:
                    if '/ ' in analytic_name:
                        analytic_name = analytic_name.split('/ ')[0]
                partner_id = line.analytic_account_id.partner_id.id if line.analytic_account_id.partner_id else False
                new_analytic_account_id = {
                    'name': analytic_name,
                    'code': line.analytic_account_id.code,
                    'year': year,
                    'parent_id': line.analytic_account_id.parent_id.id,
                    'partner_id': partner_id
                }
                analytic_account_id = record.sudo().env['account.analytic.account'].create(new_analytic_account_id)
                planned_amount = abs(line.planned_amount) - abs(line.practical_amount)
                new_line = {
                    'crossovered_budget_id': budget_id.id,
                    'date_from': budget_id.date_from,
                    'date_to': budget_id.date_to,
                    'planned_amount': -planned_amount,
                    'general_budget_id': line.general_budget_id.id,
                    'general_budget_id': line.general_budget_id.id,
                    'analytic_account_id': analytic_account_id.id
                }
                budget_line_id = record.sudo().env['crossovered.budget.lines'].create(new_line)
                for user_id in budget_id.user_ids:
                    if user_id.position_id.id not in [1, 12, 56]:
                        user_id.analytic_id += analytic_account_id
                        if analytic_account_id.parent_id:
                            user_id.analytic_id += analytic_account_id.parent_id

            budget_id.message_post(body='Created by ' + record.env.user.name,message_type='notification',content_subtype='plaintext',subtype_xmlid='mail.mt_comment',)
            action = {}
            action['type'] = 'ir.actions.act_window'
            action['res_id'] = budget_id.id
            action['res_model'] = 'crossovered.budget'
            action['view_mode'] = 'form'
            action['target'] = 'current'
            action['context'] = record.env.context
            return action



    # @api.model
    # def rule(self, domain):
    #     if not domain:
    #         domain = []
    #     if self.env.user.department_id.id == 2176:
    #         return domain
    #     if self.env.user.id == 1:
    #         return domain
    #     if self.env.context.get('for_approval'):
    #         domain += [('approve_next_position_id', '=',self.env.user.position_id.id)]
    #         return domain
    #     domain += ['|', ('user_ids', '=', self.env.user.id), ('creating_user_id', '=', self.env.user.id)]
    #     return domain



    # @api.model
    # def search(self, args, offset=0, limit=None, order=None, count=False):
    #     args = self.rule(args)
    #     return super(Budget, self).search(args,offset=offset,limit=limit,order=order,count=count)


    # @api.model
    # def name_search(self, name, args=None, operator='ilike', limit=100):
    #     args = self.rule(args)
    #     return super(Budget, self).name_search(name,args=args,operator=operator,limit=limit)


    # @api.multi
    @api.constrains('date_to', 'date_from')
    def date_constrains(self):
        for rec in self:
            if rec.date_to < rec.date_from:
                raise exceptions.ValidationError(_('Sorry, End Date Must be greater Than Start Date'))



    # @api.one
    # def _approval(self):
    #     record = self.sudo()
    #     planned = self.total_budget  #sum(line.planned_amount for line in record.crossovered_budget_line)
    #     approval = self.env['budget.approval'].sudo()
    #     self.approve_id = approval.search([('id', 'in', record.type_id.approval_ids.ids),('max_amount', '>=', planned), ('min_amount', '<=', planned)],limit=1)
    #     if self.approve_id:
    #         rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
    #         if not self.approve_rule_id:
    #             self.approve_next = rule_ids[0].position_id.name
    #             self.approve_user_ids = rule_ids[0].position_id.user_ids
    #         else:
    #             rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
    #             if rule_id:
    #                 self.approve_next = rule_id.position_id.name
    #                 self.approve_user_ids = rule_id.position_id.user_ids
    #             else:
    #                 self.approve_next = "Done"


    # @api.multi
    def action_budget_cancel(self):
        for record in self:
            record.function_consol(function="action_budget_cancel_consol")
            if not record.remarks:
                raise exceptions.ValidationError(("Fill remarks before cancel"))
            record.write({'state': 'cancel'})


    # @api.multi
    def action_budget_cancel_consol(self):
        for record in self:
            if not record.remarks:
                raise exceptions.ValidationError(("Fill remarks before cancel"))
            record.write({'state': 'cancel'})



    # @api.multi
    def action_budget_confirm(self):
        for record in self:
            record.function_consol(function="action_budget_confirm_consol")
            record.write({'state': 'confirm'})
    


    # @api.multi
    def action_budget_confirm_consol(self):
        for record in self:
            record.write({'state': 'confirm'})

    # @api.multi
    def action_budget_draft(self):
        for record in self:
            record.function_consol(function="action_budget_draft_consol")
            record.write({'state': 'draft'})



    # @api.multi
    def action_budget_draft_consol(self):
        for record in self:
            record.write({'state': 'draft'})


    # @api.multi
    def action_budget_validate(self):
        for record in self:
            record.function_consol(function="action_budget_validate_consol")
            record.write({'state': 'validate'})

    # @api.multi
    def action_budget_validate_consol(self):
        for record in self:
            record.write({'state': 'validate'})

    # @api.multi
    def action_budget_done(self):
        for record in self:
            record.function_consol(function="action_budget_done_consol")
            record.write({'state': 'done'})

    # @api.multi
    def action_budget_validate(self):
        for record in self:
            record.write({'state': 'validate'})

    # @api.multi
    def action_budget_done_consol(self):
        for record in self:
            record.write({'state': 'done'})


    # @api.multi
    def budget_compute_balance(self):
        for record in self:
            if record.crossovered_budget_line:
                for line in record.crossovered_budget_line:
                    line.budget_line_compute_balance()
            record.constrain_total_budget()
            record.constrain_line_amount()
            record._remain()




    # @api.constrains('total_budget', 'crossovered_budget_line')
    def constrain_total_budget(self):
        for record in self:
            # total_planned = sum(line.planned_amount for line in self.crossovered_budget_line)
            # 2021.10.02 - Firgi improve SUM by query
            query = """
                select sum(planned_amount) total_planned
                from crossovered_budget_lines 
                where crossovered_budget_id = {budget_id} 
            """.format(budget_id = record.id)
            record.sudo().env.cr.execute(query)
            results = record.sudo().env.cr.dictfetchall()

            total_planned = 0
            if results:
                total_planned += results[0]['total_planned'] or 0

            if record.total_budget == 0 and total_planned > 0:
                record.total_budget = total_planned

            if record.parent_id and record.parent_id.total_budget < record.total_budget:
                raise exceptions.ValidationError("Total Budget of the Parent must be greater than Child's Total Budget")

            if total_planned > record.total_budget:
                raise exceptions.ValidationError("Total Budget must be greater than the Total Planned Amount")





    # @api.constrains('crossovered_budget_line', 'parent_id')
    def constrain_line_amount(self):
        for record in self:
            if record.parent_id:
                # total_planned = sum(line.planned_amount for line in self.crossovered_budget_line)
                # 2021.10.02 - Firgi improve SUM by query
                query = """
                    select sum(planned_amount) total_planned
                    from crossovered_budget_lines 
                    where crossovered_budget_id = {budget_id} 
                """.format(budget_id = record.id)
                record.sudo().env.cr.execute(query)
                results = record.sudo().env.cr.dictfetchall()
                total_planned = 0
                if results:
                    total_planned += results[0]['total_planned'] or 0
                
                for child in record.parent_id.child_ids:
                    if child.id != record.id:
                        # total_planned += sum(line.planned_amount for line in child.crossovered_budget_line)
                        query = """
                            select sum(planned_amount) total_planned
                            from crossovered_budget_line 
                            where budget_id = {budget_id} 
                        """.format(budget_id = child.id)
                        record.sudo().env.cr.execute(query)
                        results = record.sudo().env.cr.dictfetchall()
                        if results:
                            total_planned += results[0]['total_planned'] or 0

                if total_planned > record.parent_id.total_budget:
                    raise exceptions.ValidationError("Child's Total Planned Amount is greater than Parent's Budget Amount")




    # @api.multi
    def approve_history(self, description):
        for record in self:
            record.sudo().history_ids.create({
                'name': description,
                'budget_id': record.id,
                'user_id': record.env.user.id
            })




    # @api.multi
    def approve(self):
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "APPROVE non consol")
        self.function_consol(function="approve_consol")
        if len(self) > 1:
            for record in self.sudo():
                record.approve()
        record = self.sudo()
        if not record.approve_id:
            raise exceptions.ValidationError("There are no rule defined for this Budget")
        rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
        if not rule_ids:
            raise exceptions.ValidationError("There are no rule defined for this Budget")
        if not self.approve_rule_id:
            if self.env.user.position_id.id in rule_ids[
                    0].position_id.get_parent_ids():
                self.approve_rule_id = rule_ids[0]
                self.approve_history("Approved by " + self.approve_status)
                if not rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1):
                    self.state = 'validate'
                    #self.status = 'approved'
            else:
                raise exceptions.ValidationError("You doesn't have authority to approve this Budget")
        else:
            rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
            if rule_id:
                if self.env.user.position_id.id in rule_id.position_id.get_parent_ids():
                    self.approve_rule_id = rule_id
                    self.approve_history("Approved by " + self.approve_status)
                    if not rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1):
                        self.state = 'validate'
                        #self.status = 'approved'
                else:
                    raise exceptions.ValidationError("You doesn't have authority to approve this Budget")
            else:
                raise exceptions.ValidationError("There are no Approval anymore for this Budget")




    # @api.multi
    def approve_consol(self):
        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "APPROVE consol")
        if len(self) > 1:
            for record in self.sudo():
                record.approve()

        record = self.sudo()
        if not record.approve_id:
            raise exceptions.ValidationError("There are no rule defined for this Budget")
        rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
        if not rule_ids:
            raise exceptions.ValidationError("There are no rule defined for this Budget")
        if not self.approve_rule_id:
            if self.env.user.position_id.id in rule_ids[
                    0].position_id.get_parent_ids():
                self.approve_rule_id = rule_ids[0]
                self.approve_history("Approved by " + self.approve_status)
                if not rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1):
                    self.state = 'validate'
                    #self.status = 'approved'
            else:
                raise exceptions.ValidationError("You doesn't have authority to approve this Budget")
        else:
            rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
            if rule_id:
                if self.env.user.position_id.id in rule_id.position_id.get_parent_ids():
                    self.approve_rule_id = rule_id
                    self.approve_history("Approved by " + self.approve_status)
                    if not rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1):
                        self.state = 'validate'
                        #self.status = 'approved'
                else:
                    raise exceptions.ValidationError("You doesn't have authority to approve this Budget")
            else:
                raise exceptions.ValidationError("There are no Approval anymore for this Budget")




    # @api.multi
    def write(self, vals):
        if vals.get('state') == 'cancel':
            vals['approve_rule_id'] = False
        result = super(Budget, self).write(vals)
        if self.env.context.get('writed'):
            return result

        self = self.with_context(writed=True)
        data = self.read()
        data = (data and data[0]) or {}

        if vals.get('state'):
            value = dict(self._fields['state'].selection).get(vals['state'])
            self.approve_history('Status' + " set to " + str(value))

        if self.company_id:
            self.sync_type = self.company_id.sync_type

        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "write budget diatas trigger_write")
        if self.trigger_write == True:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "write budget didalam trigger_write")
            self.send_api_consol_write_company()
        
        # for record in self:
        #     for line in record.crossovered_budget_line.mapped('analytic_account_id'):
        #         line.budget_true = True 
        

            # for line in record.user_ids:
            #     user.write({'analytic_ids': record.})
        
        return result


    # @api.multi
    def unlink(self):
        for record in self:
            if record.state != 'cancel':
                raise exceptions.ValidationError("The record must be cancelled!")
        return super(Budget, self).unlink()





class BudgetLine(models.Model):
    _inherit = "crossovered.budget.lines"

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    theoritical_amount = fields.Float(string="Theoretical Amount",readonly=True,compute='_theoritical', store=True)
    percentage = fields.Float(string="Achievement",readonly=True,compute='_theoritical', store=True)
    percent = fields.Float(string="Percentage",readonly=True,compute='_theoritical', store=True)
    actual_percent = fields.Float(string="Actual Percentage",readonly=True,compute='_percentage', store=True)
    analytic_account_id = fields.Many2one('account.analytic.account','Analytic Account', required=True, domain=[('parent_id', '!=', False),('type_analytic', '=','expense')])
    pr_amount = fields.Float(string="PR Amount", compute='_compute_pr_amount', store=True)
    po_amount = fields.Float(string="PO Amount", compute='_compute_po_amount', store=True)
    practical_amount = fields.Float(string="Invoice Amount",compute='_compute_practical', store=True)
    paid_amount = fields.Float(string="Paid Amount",compute='_compute_paid_amount', store=True)
    remain_amount = fields.Float(string="Remain Amount",compute='_compute_remain_amount', store=True)
    other_amount = fields.Float(string='Other Amount',compute='_compute_other', store=True)
    grn_amount = fields.Float(string='GRN Amount',compute='_compute_grn_amount', store=True)
    actual_amount = fields.Float(string='Actual Amount',compute='_compute_actual_amount', store=True)
    exceed_amount = fields.Float(string='Exceed Budget', store=True)
    planned_amount = fields.Float('Planned Budget', required=True, digits=0)

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)
    
    pr_line_ids = fields.Many2many('purchase.requisition.line', 'purchase_requisition_line_crossovered_budget_lines_rel', 'purchase_requisition_line_id', 'crossovered_budget_lines_id', string="PR Lines")
    po_line_ids = fields.Many2many('purchase.order.line', 'purchase_order_line_crossovered_budget_lines_rel', 'purchase_order_line_id', 'crossovered_budget_lines_id', string="PO Lines")
    stock_move_ids = fields.Many2many('stock.move', 'stock_move_crossovered_budget_lines_rel', 'stock_move_id', 'crossovered_budget_lines_id', string="GRN")
    invoice_line_ids = fields.Many2many('account.invoice.line', 'account_invoice_line_crossovered_budget_lines_rel', 'account_invoice_line_id', 'crossovered_budget_lines_id', string="Invoice not Paid")
    invoice_line_paid_ids = fields.Many2many('account.invoice.line', 'account_invoice_line_paid_crossovered_budget_lines_rel', 'account_invoice_line_id', 'crossovered_budget_lines_id', string="Invoice Paid")
    other_ids = fields.Many2many('account.move.line', 'account_move_line_crossovered_budget_lines_rel', 'account_move_line_id', 'crossovered_budget_lines_id', string="Other")
    
    ###########Supaya analytic account bisa di buka
    budget_id = fields.Many2one('account.analytic.account', 'Analytic Account')
    practical_amount = fields.Float(string='Practical Amount', digits=0)
    theoretical_amount = fields.Float(string='Theoretical Amount', digits=0)
    

    @api.model
    def create(self, vals):
        result = super(BudgetLine, self).create(vals)

        if vals.get('company_id'):
            company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
            result.sync_type = company_id.sync_type
            
        if result.trigger_create == False:
            result.send_api_consol_company()
        return result



    # @api.multi
    def send_api_consol_company(self):
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "create budget line")
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_crossovered_budget
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/crossovered.budget.lines"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/crossovered.budget.lines"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                headers = {}
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = {}
                body['csrf_token'] = record.env.user.token_consol
                values = {}
                lst = []
                values['sync_type'] = record.company_id.sync_type
                values[consol_id_from] = record.id
                if record.analytic_account_id.id == False:
                    values['analytic_account_id'] = record.analytic_account_id.id
                else:
                    values['analytic_account_id'] = str(record.analytic_account_id.id)

                if record.general_budget_id.id == False:
                    values['general_budget_id'] = record.general_budget_id.id
                else:
                    values['general_budget_id'] = str(record.general_budget_id.id)
                
                values['date_from'] = record.date_from
                values['date_to'] = record.date_to
                values['paid_date'] = record.paid_date
                values['planned_amount'] = record.planned_amount

                if record.company_id.id == False:
                    values['company_id'] = record.company_id.id
                else:
                    values['company_id'] = str(record.company_id.id)

                if record.crossovered_budget_id.id == False:
                    values['crossovered_budget_id'] = record.crossovered_budget_id.id
                else:
                    values['crossovered_budget_id'] = str(record.crossovered_budget_id.id)
                
                
                values['trigger_create'] = True

                
                
                
                lst.append(values)
                body['values'] = json.dumps(lst)
                # body['values'] = json.dumps(values)
                
                cookies = {'session_id': record.env.user.cookies}
                print('\n' + "body : " + str(body))
                print('\n' + "headers : " + str(headers))
                print('\n' + "url : " + str(url))

                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                print (response_json.status_code)
                if response_json.status_code != 200:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                try:
                    json_resp = response_json.json()
                except:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    json_resp = response_json.json()
                    
                api_status = 'failed'
                print('\n' + "json_resp : " + str(json_resp))

                data_sent = False
                response_id = False

                if 'status' in json_resp:
                    if json_resp['status'] == 'success':
                        api_status = 'success'
                        data_sent = True
                        if json_resp['data']['id']:
                            response_id = json_resp['data']['id']
                        # for d in json_resp['data']:
                        #     if 'id' in d:
                        #         response_id = d['id']
                    if json_resp['status'] == 'error':
                        # raise exceptions.ValidationError(_('Data Gagal Dibuat'))
                        raise exceptions.ValidationError(_(json_resp['message']))


                data_update = {
                    consol_id_to : response_id,
                    # 'sync_consol_response': json_resp,
                    # 'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    # 'sync_consol_sent' : data_sent
                }
                super(BudgetLine, self).write(data_update)



    # @api.multi
    def write(self, vals):
        result = super(BudgetLine, self).write(vals)
        if self.env.context.get('writed'):
            return result
        
        self = self.with_context(writed=True)

        if self.company_id:
            self.sync_type = self.company_id.sync_type
        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "write budget line diatas trigger_write")
        if self.trigger_write == True:
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "write budget line didalem trigger_write")
            self.send_api_consol_write_company()
        
        return result




    # @api.multi
    def send_api_consol_write_company(self):
        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "write budget line")
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_crossovered_budget
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/crossovered.budget.lines"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/crossovered.budget.lines"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                headers = {}
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = {}
                body['csrf_token'] = record.env.user.token_consol
                values = {}
                lst = []
                values['sync_type'] = str(record.company_id.sync_type)
                values[consol_id_from] = str(record.id)
                
                if record.analytic_account_id.id == False:
                    values['analytic_account_id'] = record.analytic_account_id.id
                else:
                    values['analytic_account_id'] = str(record.analytic_account_id.id)

                if record.general_budget_id.id == False:
                    values['general_budget_id'] = record.general_budget_id.id
                else:
                    values['general_budget_id'] = str(record.general_budget_id.id)
                
                values['date_from'] = record.date_from
                values['date_to'] = record.date_to
                values['paid_date'] = record.paid_date
                values['planned_amount'] = record.planned_amount

                if record.company_id.id == False:
                    values['company_id'] = record.company_id.id
                else:
                    values['company_id'] = str(record.company_id.id)

                if record.crossovered_budget_id.id == False:
                    values['crossovered_budget_id'] = record.crossovered_budget_id.id
                else:
                    values['crossovered_budget_id'] = str(record.crossovered_budget_id.id)

                values['trigger_write'] = False
                

                
                

                
                lst.append(values)
                body['values'] = json.dumps(lst)
                # body['values'] = json.dumps(values)
                
                cookies = {'session_id': record.env.user.cookies}

                print('\n' + "body : " + str(body))
                print('\n' + "headers : " + str(headers))
                print('\n' + "url : " + str(url))

                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                print (response_json.status_code)
                if response_json.status_code != 200:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                try:
                    json_resp = response_json.json()
                    
                except:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    json_resp = response_json.json()
                    
                api_status = 'failed'
                print('\n' + "json_resp : " + str(json_resp))

                data_sent = False
                response_id = False

                if 'status' in json_resp:
                    if json_resp['status'] == 'success':
                        api_status = 'success'
                        data_sent = True
                        if json_resp['data']['id']:
                            response_id = json_resp['data']['id']
                        # for d in json_resp['data']:
                        #     if 'id' in d:
                        #         response_id = d['id']
                    if json_resp['status'] == 'error':
                        # raise exceptions.ValidationError(_('Data Gagal Diedit'))
                        raise exceptions.ValidationError(_(json_resp['message']))


                data_update = {
                    consol_id_to : response_id,
                    # 'sync_consol_response': json_resp,
                    # 'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    # 'sync_consol_sent' : data_sent
                }
                super(BudgetLine, self).write(data_update)




    @api.onchange('sync_type', 'analytic_account_id','general_budget_id','date_from','date_to','paid_date','planned_amount','crossovered_budget_id')
    def onchange_trigger_write(self):
        self.trigger_write = True




    # @api.multi 
    def budget_line_compute_balance(self):
        for record in self:
            if record.id:
                record._compute_pr_amount()
                record._compute_po_amount()
                record._compute_grn_amount()
                record._compute_practical()
                record._compute_paid_amount()
                record._compute_other()
                record._compute_actual_amount()
                record._compute_remain_amount()
                record._theoritical()
                record._percentage()


    # @api.one
    def _compute_remain_amount(self):
        for record in self:
            if record.analytic_account_id:
                record.remain_amount = 0
                total = 0
                total += record.planned_amount - record.practical_amount - record.paid_amount - record.other_amount - record.grn_amount + record.exceed_amount
                record.remain_amount += total


    # @api.one
    def _compute_actual_amount(self):
        for record in self:
            record.actual_amount = 0
            if record.analytic_account_id:                
                total = 0
                # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "practical amount : " + str(record.practical_amount))
                # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "paid amount : " + str(record.paid_amount))
                # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "other amount : " + str(record.other_amount))
                # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "grn amount : " + str(record.grn_amount))
                total +=  record.practical_amount + record.paid_amount + record.other_amount + record.grn_amount
                record.actual_amount += total





    # 2021.10.02 - improve by query 
    # @api.one
    def _compute_grn_amount(self):
        for record in self:
            if record.id:
                amount = 0
                
                query = """
                    select sum(((coalesce(sm.product_qty, 0) - coalesce(aio.quantity, 0) - coalesce(aip.quantity, 0)) * pol.price_unit) - - coalesce(pol.discount_total, 0) + coalesce(pol.price_tax, 0)) price_subtotal
                    from stock_move sm
                    left join purchase_order_line pol on pol.id = sm.purchase_line_id

                    left join lateral (
                    select ail.quantity, ail.purchase_line_id
                    from account_invoice_line ail
                    left join account_invoice ai on ai.id = ail.invoice_id
                    left join purchase_order_line pol on pol.id = ail.purchase_line_id  
                    left join stock_move sm on sm.purchase_line_id = pol.id

                    where ai.state = 'open'
                                        and sm.date >= '{date_from}'
                                        and sm.date <= '{date_to}'
                                        and ail.account_analytic_id = {analytic_account_id}
                    ) aio on aio.purchase_line_id = pol.id

                    left join lateral (
                    select ail.quantity, ail.purchase_line_id
                    from account_invoice_line ail
                    left join account_invoice ai on ai.id = ail.invoice_id
                    left join purchase_order_line pol on pol.id = ail.purchase_line_id  
                    left join stock_move sm on sm.purchase_line_id = pol.id

                    where ai.state = 'paid'
                                        and sm.date >= '{date_from}'
                                        and sm.date <= '{date_to}'
                                        and ail.account_analytic_id = {analytic_account_id}
                    ) aip on aip.purchase_line_id = pol.id

                    where sm.state='done'
                    and sm.date >= '{date_from}'
                    and sm.date <= '{date_to}'
                    and sm.account_analytic_id = {analytic_account_id}
                    group by sm.product_qty, aio.quantity, aip.quantity
                """.format(
                    analytic_account_id = record.analytic_account_id.id,
                    date_from = record.date_from,
                    date_to = record.date_to)
                record.sudo().env.cr.execute(query)
                results = record.sudo().env.cr.dictfetchall()
                if results:
                    for rec in results:
                        amount += rec['price_subtotal'] or 0


                record.grn_amount = amount
                #     open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "amount result 1 : " + str(amount))
                
                    
                # query2 = """
                #    select sum(((ail.quantity) * pol.price_unit) - coalesce(pol.discount_total, 0) + coalesce(pol.price_tax, 0)) price_subtotal
                #     from stock_move sm 
                #     left join purchase_order_line pol on pol.id = sm.purchase_line_id 
                #   left join account_invoice_line ail on ail.purchase_line_id = pol.id
                #   left join account_invoice ai on ai.id = ail.invoice_id
                #     where sm.state = 'done'
                #         and sm.date >= '{date_from}'
                #         and sm.date <= '{date_to}'
                #         and sm.account_analytic_id = {analytic_account_id}
                #         and ai.state ='draft'
                # """.format(
                #     analytic_account_id = self.analytic_account_id.id,
                #     date_from = self.date_from,
                #     date_to = self.date_to)
                # self.sudo().env.cr.execute(query2)
                # results2 = self.sudo().env.cr.dictfetchall()
                # if results2:
                #     amount += results2[0]['price_subtotal'] or 0
                #     open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "amount result 2 : " + str(amount))

                # amount = self.analytic_account_id.total_credit - self.analytic_account_id.total_debit
                # self.grn_amount = -amount
                

                query_delete = """
                    delete from stock_move_crossovered_budget_lines_rel 
                    where crossovered_budget_lines_id = '{crossovered_budget_lines_id}'
                """.format(crossovered_budget_lines_id=record.id)
                record.env.cr.execute(query_delete)

                query3 = """
                    select sm.id id
                    from stock_move sm 
                    inner join purchase_order_line pol on pol.id = sm.purchase_line_id 
                    where sm.state = 'done'
                        and sm.date >= '{date_from}'
                        and sm.date <= '{date_to}'
                        and sm.account_analytic_id = {analytic_account_id}
                        and pol.qty_received > 0
                """.format(
                    analytic_account_id = record.analytic_account_id.id,
                    date_from = record.date_from,
                    date_to = record.date_to)
                record.sudo().env.cr.execute(query3)
                results3 = record.sudo().env.cr.dictfetchall()

                if results3:    
                    for line in results3:
                        if line['id']:
                            query_insert = """
                                insert into stock_move_crossovered_budget_lines_rel (
                                    crossovered_budget_lines_id,stock_move_id) 
                                values('{crossovered_budget_lines_id}','{stock_move_id}');
                            """.format(crossovered_budget_lines_id=record.id, stock_move_id=line['id'])
                            record.env.cr.execute(query_insert)
        


    # 2021.10.02 - improve by query 
    # @api.one
    def _compute_other(self):
        for record in self:
            if record.id:
                amount = 0
                # amount = self.env['account.move.line'].search([
                #     ('move_id.state', '=', 'posted'),
                #     ('analytic_account_id', '=', self.analytic_account_id.id),
                #     ('date', '>=', self.date_from), ('date', '<=', self.date_to)
                # ]).balance
                
                query = """
                    select sum(balance) balance
                    from account_move_line mvl 
                    inner join account_move mv on mv.id = mvl.move_id 
                    where mv.state = 'posted'
                        and mvl.date >= '{date_from}'
                        and mvl.date <= '{date_to}'
                        and mvl.analytic_account_id = {analytic_account_id}
                        and mvl.stock_picking_id is null
                        and mvl.payment_id is null
                        and mvl.invoice_id is null
                        and mvl.purchase_id is null
                        and mvl.covering_id is null
                        and mvl.creditnote_id is null
                        and mvl.advance_id is null
                        and mvl.stock_move_id is null
                        and mvl.realization_id is null
                        and mvl.salary_id is null
                        and mvl.salary_deduction_id is null
                        and mvl.doctor_fee_id is null
                        and mvl.external_fee_id is null
                        and mvl.sales_id is null
                """.format(
                    analytic_account_id = record.analytic_account_id.id,
                    date_from = record.date_from,
                    date_to = record.date_to)
                record.sudo().env.cr.execute(query)
                results = record.sudo().env.cr.dictfetchall()
                if results:
                    amount += results[0]['balance'] or 0


                # amount = self.analytic_account_id.total_credit - self.analytic_account_id.total_debit
                record.other_amount = amount
                
                # query_delete = """ 
                #     delete from account_move_line_paid_crossovered_budget_lines_rel 
                #     where crossovered_budget_lines_id = '{crossovered_budget_lines_id}'
                # """.format(crossovered_budget_lines_id=record.id)
                # record.env.cr.execute(query_delete)

                query2 = """
                    select mvl.id id
                    from account_move_line mvl 
                    inner join account_move mv on mv.id = mvl.move_id 
                    where mv.state = 'posted'
                        and mvl.date >= '{date_from}'
                        and mvl.date <= '{date_to}'
                        and mvl.analytic_account_id = {analytic_account_id}
                        and mvl.stock_picking_id is null
                        and mvl.payment_id is null
                        and mvl.invoice_id is null
                        and mvl.purchase_id is null
                        and mvl.covering_id is null
                        and mvl.creditnote_id is null
                        and mvl.advance_id is null
                        and mvl.stock_move_id is null
                        and mvl.realization_id is null
                        and mvl.salary_id is null
                        and mvl.salary_deduction_id is null
                        and mvl.doctor_fee_id is null
                        and mvl.external_fee_id is null
                        and mvl.sales_id is null
                """.format(
                    analytic_account_id = record.analytic_account_id.id,
                    date_from = record.date_from,
                    date_to = record.date_to)
                record.sudo().env.cr.execute(query2)
                results2 = record.sudo().env.cr.dictfetchall()

                if results2:    
                    for line in results2:
                        if line['id']:
                            query_insert = """
                                insert into account_move_line_paid_crossovered_budget_lines_rel (
                                    crossovered_budget_lines_id,account_move_line_id) 
                                values('{crossovered_budget_lines_id}','{account_move_line_id}');
                            """.format(crossovered_budget_lines_id=record.id, account_move_line_id=line['id'])
                            record.env.cr.execute(query_insert)





    # 2021.10.02 - improve by query 
    # @api.one
    def _compute_practical(self):
        for record in self:
            if record.analytic_account_id.id:
                jumlah = 0
                # ai = self.env['account.invoice'].search([('state','=','open')])
                # for ai_item in ai:

                # for item in self.env['account.invoice.line'].search([
                #     ('invoice_id.state', '=', 'open'),
                #     ('account_analytic_id', '=', self.analytic_account_id.id),
                #     ('date_invoice', '>=', self.date_from),
                #     ('date_invoice', '<=', self.date_to)
                # ]):
                #     jumlah += item.price_subtotal
                
                query = """
                    select sum(ail.price_subtotal) price_subtotal
                    from account_invoice_line ail
                    left join account_invoice ai on ai.id = ail.invoice_id
                    left join purchase_order_line pol on pol.id = ail.purchase_line_id  
                    left join stock_move sm on sm.purchase_line_id = pol.id

                    where ai.state = 'open'
                    and sm.date >= '{date_from}'
                    and sm.date <= '{date_to}'
                    and ail.account_analytic_id = {analytic_account_id} 
                """.format(
                    analytic_account_id = record.analytic_account_id.id,
                    date_from = record.date_from,
                    date_to = record.date_to)
                record.sudo().env.cr.execute(query)
                results = record.sudo().env.cr.dictfetchall()
                if results:
                    jumlah += results[0]['price_subtotal'] or 0

                record.practical_amount = jumlah
                
                
                query_delete = """ 
                    delete from account_invoice_line_crossovered_budget_lines_rel 
                    where crossovered_budget_lines_id = '{crossovered_budget_lines_id}'
                    """.format(crossovered_budget_lines_id=record.id)
                open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "query delete " + str(query_delete))
                record.env.cr.execute(query_delete)

                query2 = """
                    select ail.id id
                from account_invoice_line ail
                left join account_invoice ai on ai.id = ail.invoice_id
                left join purchase_order_line pol on pol.id = ail.purchase_line_id  
                left join stock_move sm on sm.purchase_line_id = pol.id

                where ai.state = 'open'
                and sm.date >= '{date_from}'
                and sm.date <= '{date_to}'
                and ail.account_analytic_id = {analytic_account_id} 
                """.format(
                    analytic_account_id = record.analytic_account_id.id,
                    date_from = record.date_from,
                    date_to = record.date_to)
                record.sudo().env.cr.execute(query2)
                results2 = record.sudo().env.cr.dictfetchall()

                if results2:
                    
                    for line in results2:
                        if line['id']:
                            query_insert = """
                                insert into account_invoice_line_crossovered_budget_lines_rel (
                                    crossovered_budget_lines_id,account_invoice_line_id
                                ) values('{crossovered_budget_lines_id}','{account_invoice_line_id}');
                            """.format(crossovered_budget_lines_id=record.id, account_invoice_line_id=line['id'])
                            record.env.cr.execute(query_insert)




    # 2021.10.02 - improve by query 
    # @api.one
    def _compute_paid_amount(self):
        for record in self:
            if record.analytic_account_id:
                jumlah = 0

                # ai = self.env['account.invoice'].search([('state','=','paid')])
                # for ai_item in ai:
                # for item in self.env['account.invoice.line'].search([
                #     ('invoice_id.state', '=', 'paid'),
                #     ('account_analytic_id', '=', self.analytic_account_id.id),
                #     ('date_invoice', '>=', self.date_from),
                #     ('date_invoice', '<=', self.date_to)
                # ]):
                #     jumlah += item.price_subtotal

                # query = """
                #     select sum(price_subtotal) price_subtotal
                #     from account_invoice_line mvl 
                #     inner join account_invoice mv on mv.id = mvl.invoice_id 
                #     where (mv.state = 'paid')
                #         and mvl.date_invoice >= '{date_from}'
                #         and mvl.date_invoice <= '{date_to}'
                #         and mvl.account_analytic_id = {analytic_account_id} 
                # """

                query = """
                    select sum(ail.price_subtotal) price_subtotal
                    from account_invoice_line ail
                    left join account_invoice ai on ai.id = ail.invoice_id
                    left join purchase_order_line pol on pol.id = ail.purchase_line_id  
                    left join stock_move sm on sm.purchase_line_id = pol.id
                    where ai.state = 'paid'
                        and sm.date >= '{date_from}'
                        and sm.date <= '{date_to}'
                        and ail.account_analytic_id = {analytic_account_id} 
                """.format(
                    analytic_account_id = record.analytic_account_id.id,
                    date_from = record.date_from,
                    date_to = record.date_to
                )

                record.sudo().env.cr.execute(query)
                results = record.sudo().env.cr.dictfetchall()

                if results:
                    jumlah += results[0]['price_subtotal'] or 0
                record.paid_amount = jumlah
                

                query_delete = """
                    delete from account_invoice_line_paid_crossovered_budget_lines_rel 
                    where crossovered_budget_lines_id = '{crossovered_budget_lines_id}'
                """.format(crossovered_budget_lines_id=record.id)

                record.env.cr.execute(query_delete)
                query2 = """
                    select ail.id id
                    from account_invoice_line ail
                    left join account_invoice ai on ai.id = ail.invoice_id
                    left join purchase_order_line pol on pol.id = ail.purchase_line_id  
                    left join stock_move sm on sm.purchase_line_id = pol.id
                    where ai.state = 'paid'
                        and sm.date >= '{date_from}'
                        and sm.date <= '{date_to}'
                        and ail.account_analytic_id = {analytic_account_id} 
                """.format(
                    analytic_account_id = record.analytic_account_id.id,
                    date_from = record.date_from,
                    date_to = record.date_to)
                record.sudo().env.cr.execute(query2)
                results2 = record.sudo().env.cr.dictfetchall()

                if results2:    
                    for line in results2:
                        if line['id']:
                            query_insert = """
                                insert into account_invoice_line_paid_crossovered_budget_lines_rel (
                                    crossovered_budget_lines_id,account_invoice_line_id) 
                                values('{crossovered_budget_lines_id}','{account_invoice_line_id}');
                            """.format(
                                crossovered_budget_lines_id=record.id, 
                                account_invoice_line_id=line['id'])
                            record.sudo().env.cr.execute(query_insert)




    # 2021.10.02 - improve pr amount 
    # @api.one
    def _compute_pr_amount(self):
        for record in self:
            if record.analytic_account_id.id:
                record.pr_amount = 0
                jumlah = 0

                # pr = self.env['purchase.requisition.line'].search([
                #     ('requisition_id.state', '=', 'in_progress'),
                #     ('account_analytic_id', '=', self.analytic_account_id.id),
                #     ('request_date', '>=', self.date_from),
                #     ('request_date', '<=', self.date_to)
                # ])
                # for item in pr:
                #     jumlah += item.price_subtotal

                query = """
                    select sum(price_subtotal) price_subtotal
                    from purchase_requisition_line mvl 
                    inner join purchase_requisition mv on mv.id = mvl.requisition_id 
                    where mv.state = 'in_progress'
                        and mvl.request_date >= '{date_from}'
                        and mvl.request_date <= '{date_to}'
                        and mvl.account_analytic_id = {analytic_account_id} 
                        AND NOT EXISTS (
                        SELECT 1 
                        FROM purchase_order po
                        left join purchase_order_line pol on pol.order_id = po.id
                        WHERE po.requisition_id = mv.id and 
                        (po.state in('purchase', 'done') 
                           or (po.state not in ('cancel', 'sent', 'purchase', 'done')
                            and po.approve_next_store != 'Completed'
                           ))
                           and pol.qty_received < 1)
                """.format(
                    analytic_account_id = record.analytic_account_id.id,
                    date_from = record.date_from,
                    date_to = record.date_to)

                record.sudo().env.cr.execute(query)
                results = record.sudo().env.cr.dictfetchall()

                if results:
                    # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + " result PR  : " + str(results[0]['price_subtotal']))
                    jumlah += results[0]['price_subtotal'] or 0
                record.pr_amount = jumlah
                

                query_delete = """ 
                    delete from purchase_requisition_line_crossovered_budget_lines_rel 
                    where crossovered_budget_lines_id = '{crossovered_budget_lines_id}'
                """.format(crossovered_budget_lines_id=record.id)
                record.sudo().env.cr.execute(query_delete)

                query2 = """
                    select mvl.id id
                    from purchase_requisition_line mvl 
                    inner join purchase_requisition mv on mv.id = mvl.requisition_id 
                    where mv.state = 'in_progress'
                        and mvl.request_date >= '{date_from}'
                        and mvl.request_date <= '{date_to}'
                        and mvl.account_analytic_id = {analytic_account_id} 
                        AND NOT EXISTS (
                        SELECT 1 
                        FROM purchase_order po
                        left join purchase_order_line pol on pol.order_id = po.id
                        WHERE po.requisition_id = mv.id and 
                        (po.state in('purchase', 'done') 
                           or (po.state not in ('cancel', 'sent', 'purchase', 'done')
                            and po.approve_next_store != 'Completed'
                           ))
                           and pol.qty_received < 1)
                """.format(
                    analytic_account_id = record.analytic_account_id.id,
                    date_from = record.date_from,
                    date_to = record.date_to)
                record.sudo().env.cr.execute(query2)
                results2 = record.sudo().env.cr.dictfetchall()


                if results2:    
                    for line in results2:
                        if line['id']:
                            query_insert = """
                                    insert into purchase_requisition_line_crossovered_budget_lines_rel (
                                        crossovered_budget_lines_id,purchase_requisition_line_id) 
                                    values('{crossovered_budget_lines_id}','{purchase_requisition_line_id}');
                                    """.format(crossovered_budget_lines_id=record.id, purchase_requisition_line_id=line['id'])
                            record.sudo().env.cr.execute(query_insert)


    # 2021.10.02 - improve by query 
    # @api.one
    def _compute_po_amount(self):
        for record in self:
            if record.analytic_account_id:
                record.po_amount = 0
                jumlah = 0
                # pol = self.env['purchase.order.line'].search([
                #     ('account_analytic_id', '=', self.analytic_account_id.id),
                #     ('qty_invoiced', '<', '1'),
                #     ('order_id.state', 'in', ['purchase', 'done']),
                #     ('date_order', '>=', self.date_from),
                #     ('date_order', '<=', self.date_to)
                # ])
                # for record in pol:
                #     jumlah += record.price_total

                # on_going = self.env['purchase.order.line'].search([
                #     ('account_analytic_id', '=', self.analytic_account_id.id),
                #     ('qty_invoiced', '<', '1'),
                #     ('order_id.approve_status', '=', 'Waiting for Approval'),
                #     ('order_id.state', 'not in',['cancel', 'sent', 'purchase', 'done']),
                #     ('date_order', '>=', self.date_from),
                #     ('date_order', '<=', self.date_to)
                # ])
                # for og in on_going:
                #     jumlah += og.price_total

                # ambil semua RFQ yg status nya sudah jadi PO/Completed dan blm di GRN
                # atau yang masih RFQ tapi sudah masuk proses approval 

                query = """
                    select sum(price_total) price_total
                    from purchase_order_line mvl 
                    inner join purchase_order mv on mv.id = mvl.order_id 
                    where (mv.state in('purchase', 'done') 
                           or (mv.state not in ('cancel', 'sent', 'purchase', 'done')
                            and mv.approve_next_store != 'Completed'
                           ))
                        and mvl.qty_received < 1
                        and mv.date_order >= '{date_from}'
                        and mv.date_order <= '{date_to}'
                        and mvl.account_analytic_id = {analytic_account_id} 
                """.format(
                    analytic_account_id = record.analytic_account_id.id,
                    date_from = record.date_from,
                    date_to = record.date_to)
                record.sudo().env.cr.execute(query)
                results = record.sudo().env.cr.dictfetchall()

                if results:
                    jumlah += results[0]['price_total'] or 0
                    # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + " result PO  : " + str(results[0]['price_total']))

               
                record.po_amount = jumlah
                query_delete = """ 
                    delete from purchase_order_line_crossovered_budget_lines_rel 
                    where crossovered_budget_lines_id = '{crossovered_budget_lines_id}'
                """.format(crossovered_budget_lines_id=record.id)
                record.env.cr.execute(query_delete)

                query2 = """
                    select mvl.id id
                    from purchase_order_line mvl 
                    inner join purchase_order mv on mv.id = mvl.order_id 
                    where (mv.state in('purchase', 'done') 
                           or (mv.state not in ('cancel', 'sent', 'purchase', 'done')
                            and mv.approve_next_store != 'Completed'
                           ))
                        and mvl.qty_received < 1
                        and mv.date_order >= '{date_from}'
                        and mv.date_order <= '{date_to}'
                        and mvl.account_analytic_id = {analytic_account_id} 
                """.format(
                    analytic_account_id = record.analytic_account_id.id,
                    date_from = record.date_from,
                    date_to = record.date_to)

                record.sudo().env.cr.execute(query2)
                results2 = record.sudo().env.cr.dictfetchall()
                if results2:
                    for line in results2:
                        if line['id']:
                            query_insert = """
                                insert into purchase_order_line_crossovered_budget_lines_rel (
                                    crossovered_budget_lines_id,purchase_order_line_id) 
                                values('{crossovered_budget_lines_id}','{purchase_order_line_id}');
                            """.format(crossovered_budget_lines_id=record.id, purchase_order_line_id=line['id'])
                            record.env.cr.execute(query_insert)




    # @api.one
    def _theoritical(self):
        for record in self:
            # now = tools.datetime.now()
            # start = tools.datetime.strptime(record.date_from, "%Y-%m-%d")
            # end = tools.datetime.strptime(record.date_to, "%Y-%m-%d")

            now = tools.date.today()
            start = record.date_from
            end = record.date_to
            
            days = (end - start).days + 1
            today = (now - start).days + 1
            amount = 0

            if record.planned_amount and days:
                amount = record.planned_amount / days

            if today > 0 and today <= days and record.planned_amount != 0:
                record.theoritical_amount = today * amount
                record.percentage = (today * amount) / record.planned_amount * 100
                record.percentage = 100 - record.percentage

            if today > days and record.planned_amount != 0:
                today = days
                record.theoritical_amount = today * amount
                record.percentage = (today * amount) / record.planned_amount * 100
                record.percentage = 100 - record.percentage

            if record.planned_amount != 0 and record.practical_amount != 0:
                record.percent = record.practical_amount / record.planned_amount * 100



    # @api.one
    def _percentage(self):
        for record in self:
            if record.planned_amount and record.actual_amount:
                record.actual_percent = (record.actual_amount / record.planned_amount) * 100
            else:
                record.actual_percent = 0.0






class BudgetHistory(models.Model):
    _name = 'budget.history'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    name = fields.Char(string="Description", required=True)
    budget_id = fields.Many2one('crossovered.budget', string="Budget")
    user_id = fields.Many2one('res.users', string="Responsible")

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)






class BudgetType(models.Model):
    _name = 'budget.type'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=True, index=True, default=_get_company)
    name = fields.Char(string="Type", required=True)
    approval_ids = fields.Many2many('budget.approval', string="Approval Rules")


    @api.model
    def create(self, vals):
        result = super(BudgetType, self).create(vals)
        if vals.get('company_id'):
            company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
            result.sync_type = company_id.sync_type
        if result.trigger_create == False:
            result.send_api_consol_company()
            result.send_api_consol_many2many()
        return result



    # @api.multi
    def send_api_consol_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            list_company += str(record.company_id.name) + ', '+ '\n'
            consol_active = record.company_id.sync_consol_budget_type
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/budget.type"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/budget.type"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)

                headers = {}
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = {}
                body['csrf_token'] = record.env.user.token_consol
                values = {}
                values_array = []
                values['sync_type'] = str(record.company_id.sync_type)
                values[consol_id_from] = record.id
                values['name'] = record.name
                values['trigger_create'] = True
                

                if record.company_id.id == False:
                    values['company_id'] = record.company_id.id
                else:
                    values['company_id'] = str(record.company_id.id)
                values_array.append(values)
                body['values'] = json.dumps(values_array)
                
                cookies = {'session_id': record.env.user.cookies}

                print('\n' + "body : " + str(body))
                print('\n' + "headers : " + str(headers))
                print('\n' + "url : " + str(url))

                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                print (response_json.status_code)
                if response_json.status_code != 200:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                try:
                    json_resp = response_json.json()
                except:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    json_resp = response_json.json()

                api_status = 'failed'

                print('\n' + "json_resp : " + str(json_resp))

                data_sent = False
                response_id = False

                if 'status' in json_resp:
                    if json_resp['status'] == 'success':
                        api_status = 'success'
                        data_sent = True
                        if json_resp['data']['id']:
                            response_id = json_resp['data']['id']
                    #     for d in json_resp['data']:
                    #         if 'id' in d:
                    #             response_id = d['id']
                    # if json_resp['status'] == 'error':
                        # raise exceptions.ValidationError(_('Data Gagal Dibuat'))
                        raise exceptions.ValidationError(_(json_resp['message']))


                data_update = {
                    consol_id_to : response_id,
                    # 'sync_consol_response': json_resp,
                    # 'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    # 'sync_consol_sent' : data_sent,
                    'sync_consol_log': list_company
                    }

                super(BudgetType, self).write(data_update)

    # @api.multi
    def write(self, vals):
        result = super(BudgetType, self).write(vals)
        if self.env.context.get('ganti_nama'): return result
        self = self.with_context(ganti_nama=True)
        if self.company_id:
            self.sync_type = self.company_id.sync_type
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "write budget type trigger_write")
        if self.trigger_write == True:
            self.send_api_consol_write_company()
        self.send_api_consol_many2many()
        return result

    # @api.multi
    def send_api_consol_write_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            list_company += str(record.company_id.name) + ', '+ '\n'
            consol_active = record.company_id.sync_consol_budget_type
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/budget.type"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/budget.type"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)

                headers = {}
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = {}
                body['csrf_token'] = record.env.user.token_consol
                values = {}
                values_array = []
                values['sync_type'] = str(record.company_id.sync_type)
                values[consol_id_from] = record.id
                values['name'] = record.name
                values['trigger_write'] = False
                if record.company_id.id == False:
                    values['company_id'] = record.company_id.id
                else:
                    values['company_id'] = str(record.company_id.id)
                values_array.append(values)
                body['values'] = json.dumps(values_array)

                cookies = {'session_id': record.env.user.cookies}

                print('\n' + "body : " + str(body))
                print('\n' + "headers : " + str(headers))
                print('\n' + "url : " + str(url))

                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                print (response_json.status_code)
                if response_json.status_code != 200:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                try:
                    json_resp = response_json.json()
                except:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    json_resp = response_json.json()
                    
                api_status = 'failed'
                print('\n' + "json_resp : " + str(json_resp))
                data_sent = False
                response_id = False

                if 'status' in json_resp:
                    if json_resp['status'] == 'success':
                        api_status = 'success'
                        data_sent = True
                        if json_resp['data']['id']:
                            response_id = json_resp['data']['id']
                        # for d in json_resp['data']:
                        #     if 'id' in d:
                        #         response_id = d['id']
                    if json_resp['status'] == 'error':
                        # raise exceptions.ValidationError(_('Data Gagal Diedit'))
                        raise exceptions.ValidationError(_(json_resp['message']))


                data_update = {
                    consol_id_to : response_id,
                    # 'sync_consol_response': json_resp,
                    # 'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    # 'sync_consol_sent' : data_sent,
                    'sync_consol_log': list_company
                    }

                super(BudgetType, self).write(data_update)

    # @api.multi
    def send_api_consol_many2many(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_budget_type
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api_many2many/budget_type/unit/write/type"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api_many2many/budget_type/main/write/type"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)

                headers = {}
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = {}
                body['csrf_token'] = record.env.user.token_consol
                values = {}
                values_array = []
                # values['sync_type'] = str(record.company_id.sync_type)
                # values['gid'] = str(loop.id)
                # values['uid'] = str(record.id)

                # values_array.append(values)
                if record.approval_ids:
                    for loop in record.approval_ids:
                        values = {}
                        values['sync_type'] = str(record.company_id.sync_type)
                        values['budget_approval_id'] = str(loop.id)
                        values['budget_type_id'] = str(record.id)
                        values_array.append(values)
                        body['values'] = values_array
                else:
                    values = {}
                    values['sync_type'] = False
                    values['budget_approval_id'] = False
                    values['budget_type_id'] = self.id
                    values_array.append(values)
                    body['values'] = values_array

                body['values'] = json.dumps(values_array)

                cookies = {'session_id': record.env.user.cookies}

                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                
                if response_json.status_code != 200:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                try:
                    json_resp = response_json.json()
                except:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    json_resp = response_json.json()
                    
                api_status = 'failed'

                print('\n' + "json_resp : " + str(json_resp))

                data_sent = False
                response_id = False

                if 'status' in json_resp:
                    if json_resp['status'] == 'success':
                        api_status = 'success'
                        data_sent = True
                        # for d in json_resp['data']:
                        #     if 'id' in d:
                        #         response_id = d['id']
                    if json_resp['status'] == 'error':
                        # raise exceptions.ValidationError(_('Data Gagal Diedit'))
                        raise exceptions.ValidationError(_(json_resp['message']))


                data_update = {
                    # consol_id_to : response_id,
                    # 'sync_consol_response': json_resp,
                    # 'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    # 'sync_consol_sent' : data_sent
                    }

                super(BudgetType, self).write(data_update)

    @api.onchange('sync_type', 'name','company_id')
    def onchange_trigger_write(self):
        self.trigger_write = True



class BudgetApproval(models.Model):
    _name = 'budget.approval'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    name = fields.Char(string="Rule Name")
    rule_name = fields.Char(string="Name", compute='_rule_name', store=True)
    min_amount = fields.Float(string="Minimum Amount", required=True)
    max_amount = fields.Float(string="Maximum Amount", required=True)
    rule_ids = fields.One2many('budget.approval.rule','approval_id',string="Rules")

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)




    @api.model
    def create(self, vals):
        result = super(BudgetApproval, self).create(vals)
        result.send_api_consol()
        for tes_loop in result.rule_ids:
            tes_loop.send_api_consol()
        return result

    # @api.multi
    def send_api_consol(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            company = self.env['res.company'].search([('sync_consol_budget_approval','=',True)])
            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_budget_approval
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/create/budget.approval"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/create/budget.approval"
                        consol_id_to = 'sync_consol_id_unit'
                        consol_id_from = 'sync_consol_id_main'

                    if not record.env.user.token_consol:
                        login_user = record.env.user.login
                        password_user = record.env.user.password_consol
                        record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)

                    headers = {}
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
                    body = {}
                    body['csrf_token'] = record.env.user.token_consol
                    values = {}
                    values_array = []
                    values['sync_type'] = str(company_id.sync_type)
                    values[consol_id_from] = record.id
                    values['name'] = record.name
                    values['min_amount'] = record.min_amount
                    values['max_amount'] = record.max_amount
                    values_array.append(values)
                    body['values'] = json.dumps(values_array)
                    
                    cookies = {'session_id': record.env.user.cookies}

                    print('\n' + "body : " + str(body))
                    print('\n' + "headers : " + str(headers))
                    print('\n' + "url : " + str(url))

                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    print (response_json.status_code)
                    if response_json.status_code != 200:
                        login_user = record.env.user.login
                        password_user = record.env.user.password_consol
                        record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        cookies = {'session_id': record.env.user.cookies}
                        body['csrf_token'] = False
                        body['csrf_token'] = record.env.user.token_consol
                        response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                    try:
                        json_resp = response_json.json()
                    except:
                        login_user = record.env.user.login
                        password_user = record.env.user.password_consol
                        record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        cookies = {'session_id': record.env.user.cookies}
                        body['csrf_token'] = False
                        body['csrf_token'] = record.env.user.token_consol
                        response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                        json_resp = response_json.json()

                    api_status = 'failed'

                    print('\n' + "json_resp : " + str(json_resp))

                    data_sent = False
                    response_id = False

                    if 'status' in json_resp:
                        if json_resp['status'] == 'success':
                            api_status = 'success'
                            data_sent = True
                            if json_resp['data']['id']:
                                response_id = json_resp['data']['id']
                            # for d in json_resp['data']:
                            #     if 'id' in d:
                            #         response_id = d['id']
                        if json_resp['status'] == 'error':
                            # raise exceptions.ValidationError(_('Data Gagal Dibuat'))
                            raise exceptions.ValidationError(_(json_resp['message']))


                    data_update = {
                        consol_id_to : response_id,
                        # 'sync_consol_response': json_resp,
                        # 'sync_consol_response_status': api_status,
                        'sync_consol_date': now,
                        # 'sync_consol_sent' : data_sent,
                        'sync_consol_log': list_company
                        }

                    super(BudgetApproval, self).write(data_update)

    # @api.multi
    def write(self, vals):
        result = super(BudgetApproval, self).write(vals)
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "write budget approval diatas trigger_write")
        self.send_api_consol_write()
        return result

    # @api.multi
    def send_api_consol_write(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            company = self.env['res.company'].search([('sync_consol_budget_approval','=',True)])
            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_budget_approval
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/write/budget.approval"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/write/budget.approval"
                        consol_id_to = 'sync_consol_id_unit'
                        consol_id_from = 'sync_consol_id_main'

                    if not record.env.user.token_consol:
                        login_user = record.env.user.login
                        password_user = record.env.user.password_consol
                        record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)

                    headers = {}
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
                    body = {}
                    body['csrf_token'] = record.env.user.token_consol
                    values = {}
                    values_array = []
                    values['sync_type'] = str(company_id.sync_type)
                    values[consol_id_from] = record.id
                    values['name'] = record.name
                    values['min_amount'] = record.min_amount
                    values['max_amount'] = record.max_amount
                    values_array.append(values)
                    body['values'] = json.dumps(values_array)

                    cookies = {'session_id': record.env.user.cookies}

                    print('\n' + "body : " + str(body))
                    print('\n' + "headers : " + str(headers))
                    print('\n' + "url : " + str(url))

                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    print (response_json.status_code)
                    if response_json.status_code != 200:
                        login_user = record.env.user.login
                        password_user = record.env.user.password_consol
                        record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        cookies = {'session_id': record.env.user.cookies}
                        body['csrf_token'] = False
                        body['csrf_token'] = record.env.user.token_consol
                        response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                    try:
                        json_resp = response_json.json()
                    except:
                        login_user = record.env.user.login
                        password_user = record.env.user.password_consol
                        record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        cookies = {'session_id': record.env.user.cookies}
                        body['csrf_token'] = False
                        body['csrf_token'] = record.env.user.token_consol
                        response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                        json_resp = response_json.json()

                    api_status = 'failed'

                    print('\n' + "json_resp : " + str(json_resp))

                    data_sent = False
                    response_id = False

                    if 'status' in json_resp:
                        if json_resp['status'] == 'success':
                            api_status = 'success'
                            data_sent = True
                            if json_resp['data']['id']:
                                response_id = json_resp['data']['id']
                            # for d in json_resp['data']:
                            #     if 'id' in d:
                            #         response_id = d['id']
                        if json_resp['status'] == 'error':
                            # raise exceptions.ValidationError(_('Data Gagal Diedit'))
                            raise exceptions.ValidationError(_(json_resp['message']))


                    data_update = {
                        consol_id_to : response_id,
                        # 'sync_consol_response': json_resp,
                        # 'sync_consol_response_status': api_status,
                        'sync_consol_date': now,
                        # 'sync_consol_sent' : data_sent,
                        'sync_consol_log': list_company
                        }

                    super(BudgetApproval, self).write(data_update)

    # @api.one
    @api.depends('name', 'min_amount', 'max_amount')
    def _rule_name(self):
        name = False
        if not self.name:
            name = ""
        else:
            name = self.name + " "
        self.rule_name = name + "%s - %s" % (self.min_amount, self.max_amount)

    # @api.multi
    def name_get(self):
        return [(record.id, record.rule_name) for record in self]



class BudgetApprovalRule(models.Model):
    _name = 'budget.approval.rule'
    _order = 'sequence'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    approval_id = fields.Many2one('budget.approval', string="Approval Rule")
    position_id = fields.Many2one('res.position', string="Position")
    sequence = fields.Integer(string="Sequence", default=1)

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)



    @api.model
    def create(self, vals):
        result = super(BudgetApprovalRule, self).create(vals)
        result.send_api_consol()
        return result

    # @api.multi
    def send_api_consol(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            company = self.env['res.company'].search([('sync_consol_budget_approval','=',True)])
            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_purchase_approval
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/create/budget.approval.rule"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/create/budget.approval.rule"
                        consol_id_to = 'sync_consol_id_unit'
                        consol_id_from = 'sync_consol_id_main'

                    if not record.env.user.token_consol:
                        login_user = record.env.user.login
                        password_user = record.env.user.password_consol
                        record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)

                    headers = {}
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
                    body = {}
                    body['csrf_token'] = record.env.user.token_consol
                    values = {}
                    values_array = []
                    values['sync_type'] = str(company_id.sync_type)
                    values[consol_id_from] = record.id
                    values['sequence'] = record.sequence
                    if record.approval_id.id == False:
                        values['approval_id'] = record.approval_id.id
                    else:
                        values['approval_id'] = str(record.approval_id.id)
                    if record.position_id.id == False:
                        values['position_id'] = record.position_id.id
                    else:
                        values['position_id'] = str(record.position_id.id)
                    values_array.append(values)
                    body['values'] = json.dumps(values_array)
                    
                    cookies = {'session_id': record.env.user.cookies}

                    print('\n' + "body : " + str(body))
                    print('\n' + "headers : " + str(headers))
                    print('\n' + "url : " + str(url))

                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    print (response_json.status_code)
                    if response_json.status_code != 200:
                        login_user = record.env.user.login
                        password_user = record.env.user.password_consol
                        record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        cookies = {'session_id': record.env.user.cookies}
                        body['csrf_token'] = False
                        body['csrf_token'] = record.env.user.token_consol
                        response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                    try:
                        json_resp = response_json.json()
                    except:
                        login_user = record.env.user.login
                        password_user = record.env.user.password_consol
                        record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        cookies = {'session_id': record.env.user.cookies}
                        body['csrf_token'] = False
                        body['csrf_token'] = record.env.user.token_consol
                        response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                        json_resp = response_json.json()

                    api_status = 'failed'
                    print('\n' + "json_resp : " + str(json_resp))
                    data_sent = False
                    response_id = False

                    if 'status' in json_resp:
                        if json_resp['status'] == 'success':
                            api_status = 'success'
                            data_sent = True
                            if json_resp['data']['id']:
                                response_id = json_resp['data']['id']
                            # for d in json_resp['data']:
                            #     if 'id' in d:
                            #         response_id = d['id']
                        if json_resp['status'] == 'error':
                            # raise exceptions.ValidationError(_('Data Gagal Dibuat'))
                            raise exceptions.ValidationError(_(json_resp['message']))


                    data_update = {
                        consol_id_to : response_id,
                        # 'sync_consol_response': json_resp,
                        # 'sync_consol_response_status': api_status,
                        'sync_consol_date': now,
                        # 'sync_consol_sent' : data_sent,
                        'sync_consol_log': list_company
                        }

                    super(BudgetApprovalRule, self).write(data_update)

    # @api.multi
    def write(self, vals):
        result = super(BudgetApprovalRule, self).write(vals)
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "write budget approval rule diatas trigger_write")
        self.send_api_consol_write()
        return result

    # @api.multi
    def send_api_consol_write(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            company = self.env['res.company'].search([('sync_consol_budget_approval','=',True)])
            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_purchase_approval
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/write/budget.approval.rule"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/write/budget.approval.rule"
                        consol_id_to = 'sync_consol_id_unit'
                        consol_id_from = 'sync_consol_id_main'

                    if not record.env.user.token_consol:
                        login_user = record.env.user.login
                        password_user = record.env.user.password_consol
                        record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)

                    headers = {}
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
                    body = {}
                    body['csrf_token'] = record.env.user.token_consol
                    values = {}
                    values_array = []
                    values['sync_type'] = str(company_id.sync_type)
                    values[consol_id_from] = record.id
                    values['sequence'] = record.sequence
                    if record.approval_id.id == False:
                        values['approval_id'] = record.approval_id.id
                    else:
                        values['approval_id'] = str(record.approval_id.id)
                    if record.position_id.id == False:
                        values['position_id'] = record.position_id.id
                    else:
                        values['position_id'] = str(record.position_id.id)
                    values_array.append(values)
                    body['values'] = json.dumps(values_array)

                    cookies = {'session_id': record.env.user.cookies}

                    print('\n' + "body : " + str(body))
                    print('\n' + "headers : " + str(headers))
                    print('\n' + "url : " + str(url))

                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    print (response_json.status_code)
                    if response_json.status_code != 200:
                        login_user = record.env.user.login
                        password_user = record.env.user.password_consol
                        record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        cookies = {'session_id': record.env.user.cookies}
                        body['csrf_token'] = False
                        body['csrf_token'] = record.env.user.token_consol
                        response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                    try:
                        json_resp = response_json.json()
                    except:
                        login_user = record.env.user.login
                        password_user = record.env.user.password_consol
                        record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                        cookies = {'session_id': record.env.user.cookies}
                        body['csrf_token'] = False
                        body['csrf_token'] = record.env.user.token_consol
                        response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                        json_resp = response_json.json()

                    api_status = 'failed'
                    print('\n' + "json_resp : " + str(json_resp))
                    data_sent = False
                    response_id = False

                    if 'status' in json_resp:
                        if json_resp['status'] == 'success':
                            api_status = 'success'
                            data_sent = True
                            if json_resp['data']['id']:
                                response_id = json_resp['data']['id']
                            # for d in json_resp['data']:
                            #     if 'id' in d:
                            #         response_id = d['id']
                        if json_resp['status'] == 'error':
                            # raise exceptions.ValidationError(_('Data Gagal Diedit'))
                            raise exceptions.ValidationError(_(json_resp['message']))


                    data_update = {
                        consol_id_to : response_id,
                        # 'sync_consol_response': json_resp,
                        # 'sync_consol_response_status': api_status,
                        'sync_consol_date': now,
                        # 'sync_consol_sent' : data_sent,
                        'sync_consol_log': list_company
                        }

                    super(BudgetApprovalRule, self).write(data_update)





# 2021.10.08 - account.budget.pos 
class BudgetaryPosition(models.Model):
    _inherit = 'account.budget.post'
    _sql_constraints = [('name_unique', 'UNIQUE(name, company_id)', "The title and company name must be unique!"),]

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    
    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)



    @api.model
    def create(self, vals):
        result = super(BudgetaryPosition, self).create(vals)

        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + 'MASUK SINI CREATE POSITION BUDGET')
        if vals.get('company_id'):
            company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
            result.sync_type = company_id.sync_type
        if result.trigger_create == False:
            result.send_api_consol_company()
            result.send_api_consol_many2many()
        return result

    # @api.multi
    def send_api_consol_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            list_company += str(record.company_id.name) + ', '+ '\n'
            consol_active = record.company_id.sync_consol_budget_position
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/account.budget.post"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/account.budget.post"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)

                headers = {}
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = {}
                body['csrf_token'] = record.env.user.token_consol
                values = {}
                values_array = []
                values['sync_type'] = str(record.company_id.sync_type)
                values[consol_id_from] = record.id
                values['name'] = record.name
                values['trigger_create'] = True
                

                if record.company_id.id == False:
                    values['company_id'] = record.company_id.id
                else:
                    values['company_id'] = str(record.company_id.id)
                values_array.append(values)
                body['values'] = json.dumps(values_array)
                
                cookies = {'session_id': record.env.user.cookies}

                print('\n' + "body : " + str(body))
                print('\n' + "headers : " + str(headers))
                print('\n' + "url : " + str(url))

                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                print (response_json.status_code)
                if response_json.status_code != 200:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                try:
                    json_resp = response_json.json()
                except:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    json_resp = response_json.json()

                api_status = 'failed'

                print('\n' + "json_resp : " + str(json_resp))

                data_sent = False
                response_id = False

                if 'status' in json_resp:
                    if json_resp['status'] == 'success':
                        api_status = 'success'
                        data_sent = True
                        if json_resp['data']['id']:
                            response_id = json_resp['data']['id']
                        # for d in json_resp['data']:
                        #     if 'id' in d:
                        #         response_id = d['id']
                    if json_resp['status'] == 'error':
                        # raise exceptions.ValidationError(_('Data Gagal Dibuat'))
                        raise exceptions.ValidationError(_(json_resp['message']))


                data_update = {
                    consol_id_to : response_id,
                    # 'sync_consol_response': json_resp,
                    # 'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    # 'sync_consol_sent' : data_sent,
                    'sync_consol_log': list_company
                    }

                super(BudgetaryPosition, self).write(data_update)

    # @api.multi
    def write(self, vals):
        result = super(BudgetaryPosition, self).write(vals)
        if self.env.context.get('ganti_nama'): return result
        self = self.with_context(ganti_nama=True)
        if self.company_id:
            self.sync_type = self.company_id.sync_type
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "write budget position diatas trigger_write")
        if self.trigger_write == True:
            self.send_api_consol_write_company()
        self.send_api_consol_many2many()
        return result

    # @api.multi
    def send_api_consol_write_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            list_company += str(record.company_id.name) + ', '+ '\n'
            consol_active = record.company_id.sync_consol_budget_position
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/account.budget.post"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/account.budget.post"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)

                headers = {}
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = {}
                body['csrf_token'] = record.env.user.token_consol
                values = {}
                values_array = []
                values['sync_type'] = str(record.company_id.sync_type)
                values[consol_id_from] = record.id
                values['name'] = record.name
                values['trigger_write'] = False
                if record.company_id.id == False:
                    values['company_id'] = record.company_id.id
                else:
                    values['company_id'] = str(record.company_id.id)
                values_array.append(values)
                body['values'] = json.dumps(values_array)

                cookies = {'session_id': record.env.user.cookies}

                print('\n' + "body : " + str(body))
                print('\n' + "headers : " + str(headers))
                print('\n' + "url : " + str(url))

                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                print (response_json.status_code)
                if response_json.status_code != 200:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                try:
                    json_resp = response_json.json()
                except:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    json_resp = response_json.json()
                    
                api_status = 'failed'
                print('\n' + "json_resp : " + str(json_resp))
                data_sent = False
                response_id = False

                if 'status' in json_resp:
                    if json_resp['status'] == 'success':
                        api_status = 'success'
                        data_sent = True
                        if json_resp['data']['id']:
                            response_id = json_resp['data']['id']
                        # for d in json_resp['data']:
                        #     if 'id' in d:
                        #         response_id = d['id']
                    if json_resp['status'] == 'error':
                        # raise exceptions.ValidationError(_('Data Gagal Diedit'))
                        raise exceptions.ValidationError(_(json_resp['message']))


                data_update = {
                    consol_id_to : response_id,
                    # 'sync_consol_response': json_resp,
                    # 'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    # 'sync_consol_sent' : data_sent,
                    'sync_consol_log': list_company
                    }

                super(BudgetaryPosition, self).write(data_update)

    # @api.multi
    def send_api_consol_many2many(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_budget_position
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api_many2many/budget_position/unit/write/type"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api_many2many/budget_position/main/write/type"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)

                headers = {}
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = {}
                body['csrf_token'] = record.env.user.token_consol
                values = {}
                values_array = []
                # values['sync_type'] = str(record.company_id.sync_type)
                # values['gid'] = str(loop.id)
                # values['uid'] = str(record.id)

                # values_array.append(values)
                if record.account_ids:
                    for loop in record.account_ids:
                        values = {}
                        values['sync_type'] = str(record.company_id.sync_type)
                        values['account_id'] = str(loop.id)
                        values['budget_id'] = str(record.id)
                        values_array.append(values)
                        body['values'] = values_array
                else:
                    values = {}
                    values['sync_type'] = False
                    values['account_id'] = False
                    values['budget_id'] = self.id
                    values_array.append(values)
                    body['values'] = values_array

                body['values'] = json.dumps(values_array)

                cookies = {'session_id': record.env.user.cookies}

                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                
                if response_json.status_code != 200:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                try:
                    json_resp = response_json.json()
                except:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    cookies = {'session_id': record.env.user.cookies}
                    body['csrf_token'] = False
                    body['csrf_token'] = record.env.user.token_consol
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    json_resp = response_json.json()
                    
                api_status = 'failed'

                print('\n' + "json_resp : " + str(json_resp))

                data_sent = False
                response_id = False

                if 'status' in json_resp:
                    if json_resp['status'] == 'success':
                        api_status = 'success'
                        data_sent = True
                        # for d in json_resp['data']:
                        #     if 'id' in d:
                        #         response_id = d['id']
                    if json_resp['status'] == 'error':
                        # raise exceptions.ValidationError(_('Data Gagal Diedit'))
                        raise exceptions.ValidationError(_(json_resp['message']))


                data_update = {
                    # consol_id_to : response_id,
                    # 'sync_consol_response': json_resp,
                    # 'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    # 'sync_consol_sent' : data_sent
                    }

                super(BudgetaryPosition, self).write(data_update)

    @api.onchange('sync_type', 'name','company_id')
    def onchange_trigger_write(self):
        self.trigger_write = True




class BudgetExceed(models.Model):
    _name = 'budget.exceed'



    @api.model
    def _get_company(self):
        return self.env.company.id
    
    @api.model
    def _get_user(self):
        return self.env.user.id

    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=True, index=True, default=_get_company)
    user_id = fields.Many2one('res.users', string='Responsible', store=True, index=True, default=_get_user)
    name = fields.Char(string="Name", required=True)
    state = fields.Selection([
        ('draft', 'Draft'), 
        ('cancel', 'Cancelled'),
        ('confirm', 'Waiting for Approval'),
        ('validate', 'Approved'), 
        ('done', 'Done')], 'Status', 
        default='draft', index=True, required=True, readonly=True, copy=False)
    exceed_type = fields.Selection([
        ('grn', 'GRN'), 
        ('pv', 'PV')], 'Type', 
        default='grn', index=True, required=True,)
    line_ids = fields.One2many('budget.exceed.line','exceed_id', string="Exceed Line")
    pv_line_ids = fields.One2many('budget.exceed.pv.line','exceed_pv_id', string="Exceed PV Line")


    type_id = fields.Many2one('budget.type',string="Budget Type",required=False)
    remarks = fields.Char(string="Cancel Remarks")

    approve_user_ids = fields.Many2many('res.users', string="Approval Users", compute='_approval',store=True)
    approve_id = fields.Many2one('budget.approval', string="Approval Level Rule", readonly=True, compute='_approval', store=True)
    approve_rule_id = fields.Many2one('budget.approval.rule', string="Approval Status", readonly=True)
    # approve_status = fields.Char(string="Approval Status", readonly=True, related='approve_rule_id.position_id.name', store=True)
    approve_status = fields.Char(string="Approval Status",readonly=True)
    approve_next = fields.Char(string="Next Approval", readonly=True, compute='_approval')
    approve_next_store = fields.Char(string="Stored Next Approval", readonly=False, store=True, index=True)
    end_approval = fields.Char(string="End Approval", compute="_get_end_approval")
    no_approval = fields.Boolean(string="No Approval", states={'posted':[('readonly', True)], 'reconciled':[('readonly', True)]})
    approved_bool = fields.Boolean(string="Approved")

    current_user_position = fields.Char(string="Current Position",compute='_get_current_position')


    # @api.one
    def _get_end_approval(self):
        record = self.sudo()
        end_approval = ''
        for at in record.type_id.approval_ids:
            for apv in at.rule_ids:
                end_approval = apv.position_id.name
        record.end_approval = end_approval

    # @api.multi
    def button_draft(self):
        self.state = 'draft'
        self.approve_rule_id = False
        self.approve_next_store = False

    # @api.one
    def _get_current_position(self):
        for rec in self:
            rec.current_user_position = self.env.user.position_id.name


    # @api.one
    def _approval(self):
        record = self.sudo()
        approval = self.env['budget.approval'].sudo()
        self.approve_id = approval.search([('id', 'in', record.type_id.approval_ids.ids)],limit=1)
        if self.approve_id:
            rule_ids = self.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
            if not self.approve_rule_id:
                self.approve_next = rule_ids[0].position_id.name
            else:
                rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                if rule_id:
                    if len(rule_id) > 1:
                        raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                    self.approve_next = rule_id.position_id.name
                    # 2021.04.12 >> tambahan firgi auto-update next_store
                    self.approve_next_store = "Completed"
                else:
                    self.approve_next = "Completed"
                    self.approved_bool = True
                    # 2021.04.12 >> tambahan firgi auto-update next_store
                    self.approve_next_store = "Completed"
        else:
            self.approve_next = ''




    # @api.multi
    def ask_approve(self):
        if self.type_id == False:
            raise exceptions.ValidationError("Fill Budget Type Before Ask Approve!!")
        if len(self) > 1: return [record.ask_approve() for record in self][0]
        self.approve_status = 'Waiting for Approval'
        self.state = 'confirm'

        record = self.sudo()
        now = (tools.datetime.now() + tools.timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
        approval_link = "https://erp.ad.mayapadahospital.com/web#min=1&limit=80&view_type=list&model=account.payment&menu_id=565&action=689"
        approval = self.env['budget.approval'].sudo()
        self.approve_id = approval.search([('id', 'in', record.type_id.approval_ids.ids)],limit=1)
        if self.approve_id:
            rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
            if not self.approve_rule_id:
                self.approve_next_store = rule_ids[0].position_id.name
            else:
                rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                if rule_id:
                    if len(rule_id) > 1:
                        raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                    self.approve_next_store = rule_id.position_id.name
                else:
                    self.approve_next_store = "Completed"
                    self.approved_bool = True

    # @api.multi
    def approve(self):
        if len(self) > 1:
            for record in self.sudo():
                record.approve()
        record = self.sudo()
        if not record.approve_id:
            raise exceptions.ValidationError("There are no rule defined for this Budget")
        rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
        if not rule_ids:
            raise exceptions.ValidationError("There are no rule defined for this Budget")
        if not self.approve_rule_id:
            if self.env.user.position_id.id in rule_ids[
                    0].position_id.get_parent_ids():
                self.approve_rule_id = rule_ids[0]
                if not rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1):
                    self.state = 'validate'
                    #self.status = 'approved'
            else:
                raise exceptions.ValidationError("You doesn't have authority to approve this Budget")
        else:
            rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
            if rule_id:
                if self.env.user.position_id.id in rule_id.position_id.get_parent_ids():
                    self.approve_rule_id = rule_id
                    if not rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1):
                        self.state = 'validate'
                        #self.status = 'approved'
                        self.approve_next_store = rule_id.position_id.name
                else:
                    raise exceptions.ValidationError("You doesn't have authority to approve this Budget")
            else:
                raise exceptions.ValidationError("There are no Approval anymore for this Budget")

        if self.approve_id:
            rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
            if not self.approve_rule_id:
                self.approve_next_store = rule_ids[0].position_id.name
            else:
                rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                if rule_id:
                    if len(rule_id) > 1:
                        raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                    self.approve_next_store = rule_id.position_id.name
                else:
                    
                    self.approve_next_store = "Completed"

    # @api.multi
    def validate_exceed(self):
        for record in self:
            if record.line_ids:
                for line in record.line_ids:
                    line.compute_exceed()
            if record.pv_line_ids:
                for line_pv in record.pv_line_ids:
                    line_pv.compute_exceed()
            record.state = 'done'

    # @api.multi
    def cancel_exceed(self):
        for record in self:
            if record.line_ids:
                for line in record.line_ids:
                    line.compute_cancel_exceed()
            if record.pv_line_ids:
                for line_pv in record.pv_line_ids:
                    line_pv.compute_cancel_exceed()
            record.state = 'cancel'

    # @api.constrains('state')
    def _action_cancel(self):
        if self.state == 'cancel' and not self.remarks:
            raise exceptions.ValidationError(_("Fill remarks before cancel"))



class BudgetExceedLine(models.Model):
    _name = 'budget.exceed.line'

    @api.model
    def _get_company(self):
        return self.env.company.id

    exceed_id = fields.Many2one('budget.exceed', string='Exceed', store=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=True, index=True, default=_get_company)
    purchase_id = fields.Many2one('purchase.order', string='Purchase Order', store=True, index=True)
    purchase_line_id = fields.Many2one('purchase.order.line', string='PO Item', store=True, index=True)
    budget_line_id = fields.Many2one('crossovered.budget.lines', string='Budget Line ID', store=True, index=True)
    move_id = fields.Many2one('stock.move', string='Move ID', store=True, index=True)
    picking_id = fields.Many2one('stock.picking', string='Picking ID', store=True, index=True)
    price_subtotal = fields.Float(string="Price Subtotal")
    price = fields.Float(string="Price")
    quantity = fields.Float(string="Quantity")
    discount = fields.Float(string="Price Subtotal")
    tax = fields.Float(string="Price")
    analytic_account_id = fields.Many2one('account.analytic.account','Analytic Account', required=True, domain=[('parent_id', '!=', False),('type_analytic', '=','expense')])
    remaining_budget = fields.Float(string="Remaining Budget")
    exceed_budget = fields.Float(string="Exceed Budget")


    # @api.multi 
    def compute_exceed(self):
        for record in self:
            if record.exceed_budget == 0:
                raise exceptions.ValidationError("Budget untuk Analytic {code} masih ada".format(code=record.analytic_account_id.name))
            else:
                record.budget_line_id.exceed_amount += record.exceed_budget

    # @api.multi 
    def compute_cancel_exceed(self):
        for record in self:
            record.budget_line_id.exceed_amount -= record.exceed_budget
            
    @api.onchange('picking_id')
    def onchange_picking_id(self):
        if self.picking_id:
            move_id = self.env['stock.move'].sudo().search([
                    ('picking_id', '=', self.picking_id.id),
                    ('account_analytic_id', '=',self.purchase_line_id.account_analytic_id.id)], limit=1)
            if move_id:
                self.move_id = move_id.id
        

    @api.onchange('move_id')
    def onchange_move_id(self):
        if self.move_id:
            self.analytic_account_id = self.move_id.account_analytic_id.id
            self.quantity = self.move_id.product_qty
            self.price = self.move_id.purchase_line_id.price_total / self.move_id.purchase_line_id.product_qty

    @api.onchange('price', 'quantity')
    def onchange_price(self):
        self.price_subtotal = self.quantity * self.price

    @api.onchange('analytic_account_id')
    def onchange_analytic_account_id(self):
        if self.analytic_account_id:
            budget_used = self.env['crossovered.budget.lines'].sudo().search([
                    ('analytic_account_id', '=', self.analytic_account_id.id),
                    ('crossovered_budget_id.state','in', ['validate','done']),
                    ('date_from', '<=',self.move_id.date),
                    ('date_to', '>=',self.move_id.date)], limit=1)
            if budget_used:
                self.budget_line_id = budget_used.id

    @api.onchange('budget_line_id')
    def onchange_budget_line_id(self):
        self.remaining_budget = self.budget_line_id.remain_amount

    @api.onchange('remaining_budget','price_subtotal')
    def onchange_remaining_budget(self):
        if self.price_subtotal > self.remaining_budget:
            self.exceed_budget = self.price_subtotal - self.remaining_budget
        else:
            self.exceed_budget = 0




class BudgetExceedPVLine(models.Model):
    _name = 'budget.exceed.pv.line'

    @api.model
    def _get_company(self):
        return self.env.company.id

    exceed_pv_id = fields.Many2one('budget.exceed', string='Exceed', store=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=True, index=True, default=_get_company)
    move_id = fields.Many2one('account.move', string='Journal Entries', store=True, index=True)
    move_line_id = fields.Many2one('account.move.line', string='Journal Items', store=True, index=True)
    budget_line_id = fields.Many2one('crossovered.budget.lines', string='Budget Line ID', store=True, index=True)
    account_id = fields.Many2one('account.account', string='Account', store=True, index=True)
    balance = fields.Float(string="Balance")
    price = fields.Float(string="Price")
    quantity = fields.Float(string="Quantity")
    analytic_account_id = fields.Many2one('account.analytic.account','Analytic Account', required=False, domain=[('parent_id', '!=', False),('type_analytic', '=','expense')])
    remaining_budget = fields.Float(string="Remaining Budget")
    exceed_budget = fields.Float(string="Exceed Budget")


    # @api.multi 
    def compute_exceed(self):
        for record in self:
            if record.exceed_budget == 0:
                raise exceptions.ValidationError("Budget PV untuk Analytic {code} masih ada".format(code=record.analytic_account_id.name))
            else:
                record.budget_line_id.exceed_amount += record.exceed_budget

    # @api.multi 
    def compute_cancel_exceed(self):
        for record in self:
            record.budget_line_id.exceed_amount -= record.exceed_budget

    @api.onchange('move_line_id')
    def onchange_move_line_id(self):
        if self.move_line_id:
            
            self.analytic_account_id = self.move_line_id.analytic_account_id.id
            self.balance = self.move_line_id.balance
            self.account_id = self.move_line_id.account_id.id

    @api.onchange('analytic_account_id')
    def onchange_analytic_account_id(self):
        if self.analytic_account_id:
        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "date4 : " + str(self.move_line_id.date))
        
            budget_used = self.env['crossovered.budget.lines'].sudo().search([
                    ('analytic_account_id', '=', self.analytic_account_id.id),
                    ('crossovered_budget_id.state','in', ['validate','done']),
                    ('date_from', '<=',self.move_line_id.date),
                    ('date_to', '>=',self.move_line_id.date)], limit=1)
            if budget_used:
                open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk onchange analytic 5")
                self.budget_line_id = budget_used.id

    @api.onchange('budget_line_id')
    def onchange_budget_line_id(self):
        if self.budget_line_id:
            self.remaining_budget = self.budget_line_id.remain_amount

    @api.onchange('remaining_budget','balance')
    def onchange_remaining_budget(self):
        if self.balance > self.remaining_budget:
            self.exceed_budget = self.balance - self.remaining_budget
        else:
            self.exceed_budget = 0




#Budget Import
class BudgetImportWizard(models.TransientModel):
    _name = "budget.import.wizard"

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    upload_file = fields.Binary(string="Upload File")
    filename = fields.Char(string="filename")
    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        string='Attachments',
    )
    uploaded = fields.Boolean()


    def minimalist_xldate_as_datetime(self, xldate, datemode):
        return (
            datetime(1899, 12, 30)
            + timedelta(days=xldate + 1462 * datemode)
            )


    def upload(self):
        if not self.attachment_ids:
             raise UserError(
                "Attachment Kosong, Harap Diisi Terlebih Dahulu")
        if not self.company_id:
             raise UserError(
                "Company Kosong, Harap Diisi Terlebih Dahulu")
        salah = ""
        baris_salah = ""
        if self.uploaded:
            raise UserError(
                "Data has been processed. \
                Please close and click the same menu to upload again.")
        for attachment in self.attachment_ids:
            wb = open_workbook(
                file_contents=base64.decodebytes(attachment.datas))
            if not wb:
                raise UserError("Please Attach xlsx")
            values = []
            for s in wb.sheets():
                for row in range(s.nrows):
                    col_value = []
                    for col in range(s.ncols):
                        value = (s.cell(row, col).value)
                        col_value.append(value)
                    values.append(col_value)

            line = 1
            baris = 1
            for val in values:
                if line == 1:
                    line += 1
                    continue
                baris += 1

                if not val[0] or not val[1]or not val[2] or not val[3] or not val[4]:
                    raise UserError("Terdapat Data yang kosong pada baris " + str(baris))
                # # company = val[0]
                # # company_id = self.env['res.company'].search([('name','=', company)], limit=1)
                # analytic_code = val[1]
                # analytic_code_id = self.env['account.analytic.account'].search([('code', '=', val[1]), ('company_id','=',self.company_id.id)],limit=1)
                # account_debit = val[2]
                # account_debit_id = self.env['account.account'].search([('code', '=', val[2]), ('company_id','=',self.company_id.id)],limit=1)
                # account_credit = val[3]
                # account_credit_id = self.env['account.account'].search([('code', '=', val[3]), ('company_id','=',self.company_id.id)],limit=1)
                # # tanggal = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + int(val[4]) - 2)
                # tanggal = self.minimalist_xldate_as_datetime(val[4], 0)
                # amount = val[5]
                budget_name = val[0]
                periode_start = self.minimalist_xldate_as_datetime(val[2], 0)
                periode_end = self.minimalist_xldate_as_datetime(val[3], 0) 
                analytic_code = val[1]
                analytic_code_id = self.env['account.analytic.account'].search([('code', '=', val[1]), ('company_id','=',self.company_id.id)],limit=1)
                
                if not analytic_code_id:
                    baris_salah += 'Baris ' + str(baris) + ' - ' + 'Code Analytic Tidak ditemukan' + ",  \n"
                    salah += str(val[1]) + ", "
                # elif not account_debit_id:
                #     baris_salah += 'Baris ' + str(baris) + ' - ' + 'Account Debit Tidak ditemukan' + ",  \n"
                #     salah += str(val[1]) + ", "
                # elif not account_credit_id:
                #     baris_salah += 'Baris ' + str(baris) + ' - ' + 'Account Credit Tidak ditemukan' + ", \n "
                #     salah += str(val[1]) + ", "
                # # baris_salah += str(baris) + ' - ' + + ", "
                # # salah += str(val[1]) + ", "
                # else:
                if val[0] and val[1] and val[2] and val[3] and val[4]:
                    # search_budget = self.env['crossovered.budget'].search([('company_id', '=', self.company_id.id), ('name','=', budget_name), ('date_from','=', periode_start), ('date_to','=', periode_end)],limit=1)
                    # if search_budget:
                    #     # search_account_salary.write({'amount': amount})
                    #     raise UserError("Sudah Ada Budget")

                            
                    # if not search_budget:
                    #     # journal_id = self.env['account.journal'].search([('name','=', 'Salary'), ('company_id','=', self.company_id.id)], limit=1)
                    budget_id = self.env['crossovered.budget'].create({
                                                        'company_id': self.company_id.id,
                                                        'name':budget_name,
                                                        'date_from': periode_start,
                                                        'date_to' : periode_end,
                                                        # 'journal_id': journal_id.id,
                                                        # 'expense_account_id': account_debit_id.id,
                                                        # 'payable_account_id': account_credit_id.id,
                                                        # 'date':tanggal,
                                                        # 'amount': amount,
                                                    })
                    if analytic_code_id and val[4] and val[5]:
                        
                        int_year = int(val[4])
                        amount = float(val[5])
                        start_date = str(int_year) + '-01-01'
                        end_date = str(int_year) + '-01-31'
                        budget_line_id  = self.env['crossovered.budget.lines'].create({
                                                        'company_id': self.company_id.id,
                                                        'analytic_account_id':analytic_code_id.id,
                                                        'date_from': start_date,
                                                        'date_to' : end_date,
                                                        'general_budget_id' : 1838,
                                                        'planned_amount' : amount,
                                                        'crossovered_budget_id' : budget_id.id,
                                                    })
                    if analytic_code_id and val[4] and val[6]:
                        
                        int_year = int(val[4])
                        if (int_year % 4) == 0:
                            amount = float(val[6])
                            start_date = str(int_year) + '-02-01'
                            end_date = str(int_year) + '-02-29'
                            budget_line_id  = self.env['crossovered.budget.lines'].create({
                                                            'company_id': self.company_id.id,
                                                            'analytic_account_id':analytic_code_id.id,
                                                            'date_from': start_date,
                                                            'date_to' : end_date,
                                                            'general_budget_id' : 1838,
                                                            'planned_amount' : amount,
                                                            'crossovered_budget_id' : budget_id.id,
                                                        })
                        else:
                            amount = float(val[6])
                            start_date = str(int_year) + '-02-01'
                            end_date = str(int_year) + '-02-28'
                            budget_line_id  = self.env['crossovered.budget.lines'].create({
                                                            'company_id': self.company_id.id,
                                                            'analytic_account_id':analytic_code_id.id,
                                                            'date_from': start_date,
                                                            'date_to' : end_date,
                                                            'general_budget_id' : 1838,
                                                            'planned_amount' : amount,
                                                            'crossovered_budget_id' : budget_id.id,
                                                        })
                    if analytic_code_id and val[4] and val[7]:
                        
                        int_year = int(val[4])
                        amount = float(val[7])
                        start_date = str(int_year) + '-03-01'
                        end_date = str(int_year) + '-03-31'
                        budget_line_id  = self.env['crossovered.budget.lines'].create({
                                                        'company_id': self.company_id.id,
                                                        'analytic_account_id':analytic_code_id.id,
                                                        'date_from': start_date,
                                                        'date_to' : end_date,
                                                        'general_budget_id' : 1838,
                                                        'planned_amount' : amount,
                                                        'crossovered_budget_id' : budget_id.id,
                                                    })
                    if analytic_code_id and val[4] and val[8]:
                        
                        int_year = int(val[4])
                        amount = float(val[8])
                        start_date = str(int_year) + '-04-01'
                        end_date = str(int_year) + '-04-30'
                        budget_line_id  = self.env['crossovered.budget.lines'].create({
                                                        'company_id': self.company_id.id,
                                                        'analytic_account_id':analytic_code_id.id,
                                                        'date_from': start_date,
                                                        'date_to' : end_date,
                                                        'general_budget_id' : 1838,
                                                        'planned_amount' : amount,
                                                        'crossovered_budget_id' : budget_id.id,
                                                    })
                    if analytic_code_id and val[4] and val[9]:
                        
                        int_year = int(val[4])
                        amount = float(val[9])
                        start_date = str(int_year) + '-05-01'
                        end_date = str(int_year) + '-05-31'
                        budget_line_id  = self.env['crossovered.budget.lines'].create({
                                                        'company_id': self.company_id.id,
                                                        'analytic_account_id':analytic_code_id.id,
                                                        'date_from': start_date,
                                                        'date_to' : end_date,
                                                        'general_budget_id' : 1838,
                                                        'planned_amount' : amount,
                                                        'crossovered_budget_id' : budget_id.id,
                                                    })
                    if analytic_code_id and val[4] and val[10]:
                        
                        int_year = int(val[4])
                        amount = float(val[10])
                        start_date = str(int_year) + '-06-01'
                        end_date = str(int_year) + '-06-30'
                        budget_line_id  = self.env['crossovered.budget.lines'].create({
                                                        'company_id': self.company_id.id,
                                                        'analytic_account_id':analytic_code_id.id,
                                                        'date_from': start_date,
                                                        'date_to' : end_date,
                                                        'general_budget_id' : 1838,
                                                        'planned_amount' : amount,
                                                        'crossovered_budget_id' : budget_id.id,
                                                    })
                    if analytic_code_id and val[4] and val[11]:
                        
                        int_year = int(val[4])
                        amount = float(val[11])
                        start_date = str(int_year) + '-07-01'
                        end_date = str(int_year) + '-07-31'
                        budget_line_id  = self.env['crossovered.budget.lines'].create({
                                                        'company_id': self.company_id.id,
                                                        'analytic_account_id':analytic_code_id.id,
                                                        'date_from': start_date,
                                                        'date_to' : end_date,
                                                        'general_budget_id' : 1838,
                                                        'planned_amount' : amount,
                                                        'crossovered_budget_id' : budget_id.id,
                                                    })
                    if analytic_code_id and val[4] and val[12]:
                        
                        int_year = int(val[4])
                        amount = float(val[12])
                        start_date = str(int_year) + '-08-01'
                        end_date = str(int_year) + '-08-31'
                        budget_line_id  = self.env['crossovered.budget.lines'].create({
                                                        'company_id': self.company_id.id,
                                                        'analytic_account_id':analytic_code_id.id,
                                                        'date_from': start_date,
                                                        'date_to' : end_date,
                                                        'general_budget_id' : 1838,
                                                        'planned_amount' : amount,
                                                        'crossovered_budget_id' : budget_id.id,
                                                    })
                    if analytic_code_id and val[4] and val[13]:
                        
                        int_year = int(val[4])
                        amount = float(val[13])
                        start_date = str(int_year) + '-09-01'
                        end_date = str(int_year) + '-09-30'
                        budget_line_id  = self.env['crossovered.budget.lines'].create({
                                                        'company_id': self.company_id.id,
                                                        'analytic_account_id':analytic_code_id.id,
                                                        'date_from': start_date,
                                                        'date_to' : end_date,
                                                        'general_budget_id' : 1838,
                                                        'planned_amount' : amount,
                                                        'crossovered_budget_id' : budget_id.id,
                                                    })
                    if analytic_code_id and val[4] and val[14]:
                        
                        int_year = int(val[4])
                        amount = float(val[14])
                        start_date = str(int_year) + '-10-01'
                        end_date = str(int_year) + '-10-31'
                        budget_line_id  = self.env['crossovered.budget.lines'].create({
                                                        'company_id': self.company_id.id,
                                                        'analytic_account_id':analytic_code_id.id,
                                                        'date_from': start_date,
                                                        'date_to' : end_date,
                                                        'general_budget_id' : 1838,
                                                        'planned_amount' : amount,
                                                        'crossovered_budget_id' : budget_id.id,
                                                    })
                    if analytic_code_id and val[4] and val[15]:
                        
                        int_year = int(val[4])
                        amount = float(val[15])
                        start_date = str(int_year) + '-11-01'
                        end_date = str(int_year) + '-11-30'
                        budget_line_id  = self.env['crossovered.budget.lines'].create({
                                                        'company_id': self.company_id.id,
                                                        'analytic_account_id':analytic_code_id.id,
                                                        'date_from': start_date,
                                                        'date_to' : end_date,
                                                        'general_budget_id' : 1838,
                                                        'planned_amount' : amount,
                                                        'crossovered_budget_id' : budget_id.id,
                                                    })
                    if analytic_code_id and val[4] and val[16]:
                        
                        int_year = int(val[4])
                        amount = float(val[16])
                        start_date = str(int_year) + '-12-01'
                        end_date = str(int_year) + '-12-31'
                        budget_line_id  = self.env['crossovered.budget.lines'].create({
                                                        'company_id': self.company_id.id,
                                                        'analytic_account_id':analytic_code_id.id,
                                                        'date_from': start_date,
                                                        'date_to' : end_date,
                                                        'general_budget_id' : 1838,
                                                        'planned_amount' : amount,
                                                        'crossovered_budget_id' : budget_id.id,
                                                    })



                        
                
        self.write({'uploaded': True})
        # self._cr.commit()

        if salah == "":
            self._cr.commit()
            raise UserError("Successfully")
        if salah != "":
            raise UserError("Nomor Baris Salah : \n"  + baris_salah)
        # Success Partial \n