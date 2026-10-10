from odoo import models, fields, api, tools, exceptions, _
from odoo.exceptions import UserError, ValidationError, Warning
import requests
import json
try:
    import ujson as JSON
except:
    import json as JSON

from . import sync




class HrDepartment(models.Model):
    _inherit = 'hr.department'

    sync_id = sync.id
    sync_date = sync.date
    sync_type = sync.type
    sync_id_api = sync.id_api
    sync_is_arcus = sync.is_arcus
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    sync_consol_sent = sync.consol_sent
    sync_consol_response_status = sync.consol_response_status
    sync_consol_response = sync.consol_response
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")

    hospdeptid = fields.Integer(string="HospDept ID", store=True)
    is_store = fields.Boolean(string="Is Location", readonly=True)
    is_mainstore = fields.Boolean(string="Is MainStore", default=False)
    is_substore = fields.Boolean(string="Is SubStore", default=False)
    is_cartstore = fields.Boolean(string="Is CartStore", default=False)
    is_user = fields.Boolean(string="HR Department", default=False)
    is_his = fields.Boolean(string="HIS Facility", default=False)
    location_type = fields.Char(string="Location Type")
    wipro_block = fields.Boolean(string="Wipro Blocked", default=False)
    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    message_last_post = fields.Datetime(string="Message Last Post", index=True, readonly=True)
    
    cost_center_ids = fields.One2many('cost.center.master','department_id',string="Cost Center")
    member_ids = fields.One2many('res.users', 'department_id', string='Members', readonly=True)
    jobs_ids = fields.One2many('res.position', 'department_id', string='Positions')
    head_id = fields.Many2one('res.users', string='Manager', tracking=True)
    type = fields.Char(string="Type")

    @api.onchange('name')
    def set_upper(self):
        val = str(self.name)
        self.name = val.upper()
    
    
    # @api.multi
    def name_get(self):
        res = []
        for record in self:
            if record.is_his:
                if record.company_id and record.company_id.company_code:
                    res.append((record.id, record.company_id.company_code + ' / HIS / ' + record.name))
                else:
                    res.append({record.id, 'HIS / ' + record.name})
            elif record.parent_id:
                if record.parent_id.display_name:
                    res.append((record.id, record.parent_id.display_name + ' / ' + record.name))
                elif record.company_id and record.company_id.company_code:
                    res.append((record.id, record.company_id.company_code + ' / ' + record.parent_id.name + ' / ' + record.name))
                else:
                    res.append((record.id, record.parent_id.name + ' / ' + record.name))                 
            else:
                if record.company_id and record.company_id.company_code:
                    res.append((record.id, record.company_id.company_code + ' / ' + record.name))
                else:
                    res.append((record.id, record.name))
        return res



    # @api.multi
    def send_api_consol_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_hr_department
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/hr.department"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/hr.department"
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
                values['is_user'] = record.is_user
                values['trigger_create'] = True
                if record.parent_id.id == False:
                    values['parent_id'] = record.parent_id.id
                else:
                    values['parent_id'] = str(record.parent_id.id)
                # karena tidak ada sync_consol di object hr.employee
                # if record.manager_id.id == False:
                #     values['manager_id'] = record.manager_id.id
                # else:
                #     values['manager_id'] = str(record.manager_id.id)
                values['is_store'] = record.is_store
                values['is_mainstore'] = record.is_mainstore
                values['is_substore'] = record.is_substore
                values['is_cartstore'] = record.is_cartstore
                values['location_type'] = str(record.location_type)
                values['wipro_block'] = record.wipro_block
                if record.company_id.id == False:
                    values['company_id'] = record.company_id.id
                else:
                    values['company_id'] = str(record.company_id.id)
                if consol_type == 'unit':
                    sync_consol_id_main = str(self.env.user.login)
                    company_name = record.company_id.name
                    values['company_name'] = company_name
                    values['user_id_cek'] = sync_consol_id_main
                if consol_type == 'main':
                    sync_consol_id_main = str(self.env.user.login)
                    company_name = record.company_id.name
                    values['company_name'] = company_name
                    values['user_id_cek'] = sync_consol_id_main

                values_array.append(values)
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
                    'sync_consol_response': json_resp,
                    'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    'sync_consol_sent' : data_sent
                    }

                super(HrDepartment, self).write(data_update)


    # @api.multi
    def send_api_consol_write_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_hr_department
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/hr.department"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/hr.department"
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
                values['is_user'] = record.is_user
                values['trigger_write'] = False
                if record.parent_id.id == False:
                    values['parent_id'] = record.parent_id.id
                else:
                    values['parent_id'] = str(record.parent_id.id)
                # karena tidak ada sync_consol di object hr.employee
                # if record.manager_id.id == False:
                #     values['manager_id'] = record.manager_id.id
                # else:
                #     values['manager_id'] = str(record.manager_id.id)
                values['is_store'] = record.is_store
                values['is_mainstore'] = record.is_mainstore
                values['is_substore'] = record.is_substore
                values['is_cartstore'] = record.is_cartstore
                values['location_type'] = str(record.location_type)
                values['wipro_block'] = record.wipro_block
                if consol_type == 'unit':
                    sync_consol_id_main = str(self.env.user.login)
                    company_name = record.company_id.name
                    values['company_name'] = company_name
                    values['user_id_cek'] = sync_consol_id_main
                if consol_type == 'main':
                    sync_consol_id_main = str(self.env.user.login)
                    company_name = record.company_id.name
                    values['company_name'] = company_name
                    values['user_id_cek'] = sync_consol_id_main
                values_array.append(values)
                body['values'] = json.dumps(values_array)

                cookies = {'session_id': record.env.user.cookies}

                # raise exceptions.ValidationError(str(body))
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
                    'sync_consol_response': json_resp,
                    'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    'sync_consol_sent' : data_sent
                    }

                super(HrDepartment, self).write(data_update)

    # @api.model
    # def get_view(self,view_id=None, view_type='form', **options):
    #     res = super(HrDepartment,self).get_view(view_id=view_id,view_type=view_type, **options)
    #     if view_type == 'tree':
    #         res['arch'] = """
    #             <tree string="HR Department" decoration-info="is_user==1" delete="false">
    #                 <field name="display_name"/>
    #                 <field name="head_id"/>
    #                 <field name="is_user"/>
    #                 <field name="is_store"/>
    #                 <field name="company_id" groups="base.group_multi_company"/>
    #                 <field name="sync_type"/>
    #             </tree>
    #         """
    #     elif view_type == 'search':
    #         res['arch'] = """
    #             <search string="Search Department..">
    #                 <filter string="Facility/Store" domain="[('is_store','=', 1)]" help="Facility/Store"/>
    #                 <filter string="HR Department" domain="[('is_user','=', 1)]" help="HR Department"/>
    #                 <filter string="From Arcus" domain="[('sync_is_arcus','=', 1)]" help="From Arcus"/>
    #                 <separator/>
    #                 <field name="name"/>
    #                 <field name="head_id"/>
    #                 <field name="company_id"/>
    #             </search>"""
    #     from lxml import etree
    #     doc = etree.XML(res['arch'])
    #     View = self.env['ir.ui.view'].sudo()
    #     res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
    #     return res



    @api.model
    def create(self, vals):
        from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
        from datetime import datetime
        import os

        # define now datetime
        now = datetime.now()
        now_formatted = now.strftime("%Y-%m-%d %H:%M:%S")

        # define python timezone
        import pytz
        local = pytz.timezone('Asia/Jakarta')
        log_date = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y%m%d")
        log_year = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y")
        log_month = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        #log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local),"%H%M%S.%f")
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'hr.department' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'hr.department'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        result = super(HrDepartment, self).create(vals)
        for record in result:
            if vals.get('sync_type'):
                record.env['stock.location'].sudo()._sync_department_api(sync_type=vals['sync_type'])
            
            if vals.get('sync_id') or vals.get('sync_id_api'):
                result.is_his = True 
            
            if vals.get('company_id'):
                company_id = record.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
                result.sync_type = company_id.sync_type
        if result.trigger_create == False and not result.sync_id and not result.sync_id_api:
            result.send_api_consol_company()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " +str(result.id)

        open(log_file, 'a').write(message_log)
        return result


    # @api.multi
    def write(self, vals):
        from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
        from datetime import datetime
        import os

        # define now datetime
        now = datetime.now()
        now_formatted = now.strftime("%Y-%m-%d %H:%M:%S")

        # define python timezone
        import pytz
        local = pytz.timezone('Asia/Jakarta')
        log_date = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y%m%d")
        log_year = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y")
        log_month = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        #log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local),"%H%M%S.%f")
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'hr.department' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'hr.department'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        result = super(HrDepartment, self).write(vals)
        if self.env.context.get('ganti_nama'): return result
        self = self.with_context(ganti_nama=True)

        if self.is_store == True:
            stock = self.env['stock.location'].search([('sync_id_api', '=', self.sync_id_api), ('sync_type', '=', self.sync_type)], limit=1)
            if stock:
                stock.name = self.name
            else:
                self.env['stock.location'].sudo()._sync_department_api(sync_type=self.sync_type)

        if self.company_id:
            self.sync_type = self.company_id.sync_type
        if self.sync_id_api or self.sync_id:
            self.is_his = True 

        if self.trigger_write == True and not self.sync_id and not self.sync_id_api:
            self.send_api_consol_write_company()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Write before return" + "\n ID: " +str(self.id)

        open(log_file, 'a').write(message_log)
        return result


    @api.onchange('sync_type', 'name','is_user','parent_id','is_store','is_mainstore','is_substore','is_cartstore','location_type','wipro_block')
    def onchange_trigger_write(self):
        self.trigger_write = True


    @api.model
    def _sync_department_wipro(self, sync_type='1'):
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>',0)])}
        sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name),('sync_type', '=', sync_type)],limit=1)
        query = """
            SELECT a.Name 'name', 
                a.HospDeptId 'sync_id', 
                a.HospDeptId 'hospdeptid', 
                cast(a.IsStore as bit) 'is_store' 
            FROM dbo.v_DBDepartments a 
            WHERE a.Name is not null 
        """
        if sync_date:
            query += " and convert(varchar(10), a.MODDATE, 121) >= '{0}'".format(tools.datetime.strptime(sync_date.date,'%Y-%m-%d %H:%M:%S').date())
            print(query)
            sync_date.date = tools.datetime.now()
        else:
            self.env['sync.date'].sudo().create({
                'name':sync.getframe().f_code.co_name,
                'sync_type':sync_type
            })
        data = sync.get_data(sync.servers.get(sync_type), query)

        if not data:
            print("No new data available")
            return
            
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:S')
        for object in data:
            open('/opt/odoo16/logs/test_data.log', 'a+').write('\n' + str(data))
            object['sync_date'] = now
            object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)],limit=1).id
            if int(object['sync_id']) in sync_ids:
                self.sudo().browse(sync_ids[object['sync_id']]).write(object)
            else:
                self.sudo().create(object)




class ResPosition(models.Model):
    _name = 'res.position'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    sync_consol_sent = sync.consol_sent
    sync_consol_response_status = sync.consol_response_status
    sync_consol_response = sync.consol_response
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")

    name = fields.Char(string="Position", required=True)
    department_id = fields.Many2one('hr.department', string="Division/Department",domain="[('is_user', '=', 1)]")
    parent_id = fields.Many2one('res.position', string="Head",domain="[('id', '!=', active_id)]")
    child_ids = fields.One2many('res.position','parent_id', string="Subordinates",readonly=True)
    user_ids = fields.One2many('res.users','position_id', string="Users",readonly=True)
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)
    


    @api.onchange('name')
    def set_upper(self):
        val = str(self.name)
        self.name = val.upper()
    



    @api.model
    def create(self, vals):
        from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
        from datetime import datetime
        import os

        # define now datetime
        now = datetime.now()
        now_formatted = now.strftime("%Y-%m-%d %H:%M:%S")

        # define python timezone
        import pytz
        local = pytz.timezone('Asia/Jakarta')
        log_date = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y%m%d")
        log_year = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y")
        log_month = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        #log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local),"%H%M%S.%f")
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'res.position' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'res.position'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        result = super(ResPosition, self).create(vals)
            
        result.send_api_consol()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " +str(result.id)

        open(log_file, 'a').write(message_log)
        return result




    # @api.multi
    def send_api_consol(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            company = self.env['res.company'].search([('sync_consol_res_position','=',True)])

            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_res_position
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""

                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/create/res.position"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/create/res.position"
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
                    values['sync_type'] = str(company_id.sync_type)
                    values[consol_id_from] = str(record.id)
                    values['name'] = str(record.name)
                    if record.parent_id.id == False:
                        values['parent_id'] = record.parent_id.id
                    else:
                        values['parent_id'] = str(record.parent_id.id)
                    if consol_type == 'unit':
                        sync_consol_id_main = str(self.env.user.login)
                        company_name = company_id.name
                        values['company_name'] = company_name
                        values['user_id_cek'] = sync_consol_id_main
                    if consol_type == 'main':
                        sync_consol_id_main = str(self.env.user.login)
                        company_name = company_id.name
                        values['company_name'] = company_name
                        values['user_id_cek'] = sync_consol_id_main
                    lst.append(values)
                    body['values'] = json.dumps(lst)
                    # body['values'] = json.dumps(values)
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
                        'sync_consol_response': json_resp,
                        'sync_consol_response_status': api_status,
                        'sync_consol_date': now,
                        'sync_consol_sent' : data_sent,
                        'sync_consol_log': list_company
                    }
                    super(ResPosition, self).write(data_update)





    # @api.multi
    def write(self, vals):
        from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
        from datetime import datetime
        import os

        # define now datetime
        now = datetime.now()
        now_formatted = now.strftime("%Y-%m-%d %H:%M:%S")

        # define python timezone
        import pytz
        local = pytz.timezone('Asia/Jakarta')
        log_date = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y%m%d")
        log_year = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y")
        log_month = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        #log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local),"%H%M%S.%f")
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'res.position' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'res.position'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        result = super(ResPosition, self).write(vals)
            
        self.send_api_consol_write()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Write before return" + "\n ID: " +str(self.id)

        open(log_file, 'a').write(message_log)
        return result




    # @api.multi
    def send_api_consol_write(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            company = self.env['res.company'].search([('sync_consol_res_position','=',True)])
            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_res_position
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/write/res.position"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/write/res.position"
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
                    values['sync_type'] = str(company_id.sync_type)
                    values[consol_id_from] = str(record.id)
                    values['name'] = record.name
                    if record.parent_id.id == False:
                        values['parent_id'] = record.parent_id.id
                    else:
                        values['parent_id'] = str(record.parent_id.id)
                    if consol_type == 'unit':
                        sync_consol_id_main = str(self.env.user.login)
                        company_name = company_id.name
                        values['company_name'] = company_name
                        values['user_id_cek'] = sync_consol_id_main
                    if consol_type == 'main':
                        sync_consol_id_main = str(self.env.user.login)
                        company_name = company_id.name
                        values['company_name'] = company_name
                        values['user_id_cek'] = sync_consol_id_main
                    lst.append(values)
                    body['values'] = json.dumps(lst)
                    # body['values'] = json.dumps(values)
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
                        'sync_consol_response': json_resp,
                        'sync_consol_response_status': api_status,
                        'sync_consol_date': now,
                        'sync_consol_sent' : data_sent,
                        'sync_consol_log': list_company
                    }
                    super(ResPosition, self).write(data_update)




    # @api.multi
    def get_parent_ids(self, ids=False):
        if not ids:
            ids = []
        ids += [self.id]
        if self.parent_id:
            ids += [self.parent_id.id]
            if self.parent_id.parent_id:
                ids = self.parent_id.parent_id.get_parent_ids(ids)
        return ids




    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ResPosition,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Positions" delete="false">
                    <field name="name"/>
                    <field name="parent_id"/>
                    <field name="department_id"/>
                    <field name="sync_type"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res



