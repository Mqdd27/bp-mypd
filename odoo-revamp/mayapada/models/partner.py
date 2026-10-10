import logging
from odoo.exceptions import AccessError, UserError
from odoo.osv import expression
from odoo import models, fields, api, tools, exceptions, _
import requests
import json
try:
    from multiprocess import Process, Manager
except:
    from threading import Thread as Process

# import sys
# reload(sys)
# sys.setdefaultencoding('utf-8')
from . import sync


class ResPartner(models.Model):
    _inherit = 'res.partner'

    sync_id = sync.id
    sync_date = sync.date
    sync_id_api = sync.id_api
    sync_type = sync.type
    sync_is_arcus = sync.is_arcus
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    sync_consol_sent = sync.consol_sent
    sync_consol_response_status = sync.consol_response_status
    sync_consol_response = sync.consol_response
    user_id_cek = fields.Char(string="User ID")

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=False,default=_get_company)
    company_name = fields.Char(string="Company Name")

    parent_doctor_id = fields.Many2one('res.partner', string="Parent Doctor")
    doctor = fields.Boolean(string="Is a Doctor", index=True, default=False)
    patient = fields.Boolean(string="Is a Patient", index=True, default=False)
    passport = fields.Char(string="Passport No.")
    ktp = fields.Char(string="National ID")
    spec = fields.Char(string="Specialisation", index=True)
    type_doctor = fields.Selection([('internal', 'Internal'),('external', 'External')],string='Doctor Type')
    type_employment = fields.Char(string="Employment Type")
    insurance = fields.Boolean(string="Is a Insurance",default=False,index=True)
    tariff_id = fields.Many2one('hospital.tariff', string="Tariff")
    registration_code = fields.Char(string="MR. Number")
    reference = fields.Char(string="Reference")
    gender = fields.Selection([('male', "Male"), ('female', "Female"),('unknown', "Unknown")],string="Gender")
    age = fields.Integer(string="Age", default=1, compute='_age', store=True)
    age_type = fields.Selection([('years', 'Years'), ('months', 'Months'),('days', 'Days')],string='Age Type')
    patient_country = fields.Char(string="Patient Country")
    patient_state = fields.Char(string="Patient State")
    patient_city = fields.Char(string="Patient City")
    patient_area = fields.Char(string="Patient Area")
    patient_nationality = fields.Char(string="Patient Nationality")
    patient_district = fields.Char(string="Patient District")
    patient_subdistrict = fields.Char(string="Patient Sub-district")


    department = fields.Char(string="Department")
    title_name = fields.Char(string="Title Name")
    vendor_code = fields.Char(string="Customer Code", store=True)
    vendor_wipro = fields.Boolean(string="Is a Vendor HIS", index=True)
    customer_wipro = fields.Boolean(string="Is a Customer HIS", index=True)
    # customer_type_wipro = fields.Selection([('1','GOVERNMENT'),('2','INSURANCE'),('3','CORPORATE'),('4','EMPLOYEE'),('5','PT'),('6','ASURANSI'),('7','REFFERAL'),('8','BANK'),('9','PRIVATE CREDIT'),('10','GOVERMENT'), ('11','MAYAPADA'), ('13','E-COMMERCE')], string="Payer Type", store=True)
    customer_type_wipro = fields.Char(string="Customer Type (HIS)")
    customer_type_api = fields.Char(string="Customer Type API")
    customer_category = fields.Char(string="Customer Category", store=True)
    street3 = fields.Char(string="Street3")
    customer_pic = fields.Char(string="Customer PIC")
    customer_pic_div = fields.Char(string="Customer PIC Division")
    # ada kebutuhan dari Finance/Accounting untuk Credit Limit per Penjamin
    credit_days = fields.Integer(string="AR/AP Credit Days")
    credit_limit = fields.Monetary(string="AR/AP Credit Limit")
    payer_aging = fields.Monetary(string="AR Aging")
    payer_tax_invoice = fields.Boolean(string="AR Enable Invoice Taxes")
    payer_autoblock = fields.Boolean(string="HIS Auto-Block", index=False, default=False)
    payer_block = fields.Boolean(string="HIS Block Aging", default=False)
    payer_new = fields.Selection([('new','New'), ('old','Old')], string="HIS Payer New")
    
    # ada kebutuhan dari FA u/ membuat tagihan CL per Penjamin satu virtual account
    virtual_enable = fields.Boolean(string="Enable VA Payer", default=False)
    virtual_beneficary = fields.Char(string="VA Beneficary")
    virtual_number = fields.Char(string="VA Number")
    virtual_bank = fields.Many2one('res.bank', string="VA Bank")

    cl_enable = fields.Boolean(string="CL Enbale")
    cl_beneficiary = fields.Char(string="CL Beneficiary", index=True)
    cl_account = fields.Char(string="CL Account Number", index=True)
    cl_bank_name = fields.Char(string="CL Bank Name", index=True)
    cl_pic = fields.Char(string="CL PIC", index=True)
    cl_pic_email = fields.Char(string="CL PIC Email", index=True)
    cl_ttd = fields.Char(string="CL TTD", index=True)

    discount_enable = fields.Boolean(string="Discount Enable")
    discount_rate = fields.Float(string="Discount Rate (%)")
    discount_reason = fields.Char(string="Discount Reason")

    wipro_block = fields.Boolean(string="HIS Blocked")
    contact_person = fields.Char(string="Contact Person")
    date_of_birth = fields.Date(string="Date of Birth")
    # payer_ids = fields.Many2many('res.payer', string="Payers")
    bpjs_number = fields.Char(string="BPJS Number")
    npwp = fields.Char(string="NPWP")
    sip_number = fields.Char(string="SIP Number")
    practice_doctor_location = fields.Char(string="Lokasi Praktek Dokter")
    start_date_doc = fields.Date(string="Start Date Doctor")
    end_date_doc = fields.Date(string="End Date Doctor")
    background = fields.Char(string="Background")
    employee_number = fields.Char(string="Employee Number")
    doctor_code = fields.Char(string="Doctor Code")
    specialise_id = fields.Float()
    specialise_api_id = fields.Char(string="Specialise API",required=False,index=True)
    ssn = fields.Char(string="SSN")
    akl = fields.Char(string="AKL")
    loa = fields.Char(string="LOA")   

    bank_information_ids = fields.One2many('bank.information','bank_id',string="Bank Information",required=False)
    discount_after_bills_ids = fields.One2many('discount.after.bills','partner_id', ondelete='cascade', copy=False, required=False)
    account_ar_id = fields.Many2one('account.account',string="Account AR Stored", tracking=True, index=True)
    account_ap_id = fields.Many2one('account.account',string="Account AP Stored", tracking=True, index=True)
    # property_account_payable_id = fields.Many2one('account.account', company_dependent=True,
    #     string="Account Payable", oldname="property_account_payable",
    #     domain="[('internal_type', '=', 'payable'), ('deprecated', '=', False)]",
    #     help="This account will be used instead of the default one as the payable account for the current partner",
    #     required=True, tracking=True)
    # property_account_receivable_id = fields.Many2one('account.account', company_dependent=True,
    #     string="Account Receivable", oldname="property_account_receivable",
    #     domain="[('internal_type', '=', 'receivable'), ('deprecated', '=', False)]",
    #     help="This account will be used instead of the default one as the receivable account for the current partner",
    #     required=True, tracking=True)

    account_ar_updated = fields.Boolean(string="AR Updated", default=False)
    check_double = fields.Char(string="Checking Double Sync",index=True,store=True)

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")

    api_post_timestamp = fields.Datetime(string="Timestamp", readonly=True)
    api_post_status = fields.Selection([('done', 'Done'), ('failed', 'Failed')], string='Status API Post', readonly=True)
    api_post_payload = fields.Char(string="Payload", readonly=True)
    api_post_response = fields.Char(string="Response", readonly=True)
    api_post_timestamp_cancel = fields.Datetime(string="Timestamp", readonly=True)
    api_post_status_cancel = fields.Selection([('done', 'Done'),('failed', 'Failed')], string='Status API Cancel', readonly=True)
    api_post_payload_cancel = fields.Char(string="Payload", readonly=True)
    api_post_response_cancel = fields.Char(string="Response", readonly=True)
    address_ids = fields.One2many('res.partner.address', 'partner_id', string="List Address")
    
    is_user = fields.Boolean(string="Is User", default=False)
    supplier = fields.Boolean(string='Is a Vendor')
    customer = fields.Boolean(string='Is a Customer', default=True)
    # invoice_ids = fields.One2many('account.invoice','partner_id', string="Invoices", readonly=True)
    # payment_ids = fields.One2many('account.payment','partner_id', string="Payments", readonly=True)
    # letter_ids = fields.One2many('account.coveringletter','payer', string="Payer Invoice", readonly=True)
    # billing_ids = fields.One2many('sale.order.bill','partner_id', string="Patient Bills", readonly=True)

    patient_type_id = fields.Many2one('hospital.patient.type', string="Patient Type")
    message_last_post = fields.Datetime(string="Last Message Date")
    opt_out = fields.Boolean(string="Opt-Out")
    fax = fields.Char(string="Age")
    barcode = fields.Char(string='Barcode', oldname='ean13', store=True)
    notify_email = fields.Selection([('none', 'Never'), ('always', 'All Messages')], string="Email Messages and Notifications")
    is_tpa = fields.Boolean(string="Is TPA", default=False)
    tpa_ids = fields.Many2many(
        'res.partner',
        'res_partner_tpa_rel',  # Explicit name for the relationship table
        'partner_id',  # Column referring to the source model (res.partner)
        'tpa_id',  # Column referring to the target model (res.partner)
        string='TPA Partners'
    )

    supplier_id = fields.Many2one('payable.supplier', string="AP Supplier Group")
    
    credit = fields.Monetary(
        string='Total Receivable', help="Total amount this customer owes you.",
        groups='account.group_account_invoice,account.group_account_readonly',store=True)

    debit = fields.Monetary(
        string='Total Payable',
        help="Total amount you have to pay to this vendor.",
        groups='account.group_account_invoice,account.group_account_readonly',store=True)

    @api.model
    def _signup_retrieve_partner(self, token, check_validity=False, raise_exception=False):
        """ find the partner corresponding to a token, and possibly check its validity
            :param token: the token to resolve
            :param check_validity: if True, also check validity
            :param raise_exception: if True, raise exception instead of returning False
            :return: partner (browse record) or False (if raise_exception is False)
        """

        # partner = self.sudo().env['res.partner'].search([('token', '=', token)], limit=1)
        query = self.env.cr.execute("""SELECT * FROM res_partner WHERE signup_token='{token}'""".format(token=token))
        result = self.env.cr.dictfetchone()

        if result:
            partner = self.sudo().env['res.partner'].browse(result['id'])
        else:
            partner = None

        if not partner:
            if raise_exception:
                raise exceptions.UserError(_("Signup token '%s' is not valid", token))
            return False
        if check_validity and not partner.signup_valid:
            if raise_exception:
                raise exceptions.UserError(_("Signup token '%s' is no longer valid", token))
            return False
        return partner


    @api.model
    def get_mention_suggestions(self, search, limit=8, channel_id=None):
        """ Return 'limit'-first partners' such that the name or email matches a 'search' string.
            Prioritize partners that are also (internal) users, and then extend the research to all partners.
            If channel_id is given, only members of this channel are returned.
            The return format is a list of partner data (as per returned by `mail_partner_format()`).
        """



        company_ids = self.env.user.company_ids.ids
        search_dom = expression.OR([[('name', 'ilike', search), ('is_user', '=', True), ('company_id', 'in', self.env.user.company_ids.ids)]])
        search_dom = expression.AND([[('name', 'ilike', search), ('is_user', '=', True), ('company_id', 'in', self.env.user.company_ids.ids)], search_dom])

        if channel_id:
            search_dom = expression.AND([[('name', 'ilike', search), ('is_user', '=', True), ('company_id', 'in', self.env.user.company_ids.ids)], search_dom])
        domain_is_user = expression.AND([[('name', 'ilike', search), ('is_user', '=', True), ('company_id', 'in', self.env.user.company_ids.ids)], search_dom])

        open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + str("masuk sini 1 " + str(search_dom)))
        if channel_id:
            search_dom = expression.AND([[('name', 'ilike', search), ('is_user', '=', True), ('company_id', 'in', self.env.user.company_ids.ids)], search_dom])
            open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + str("masuk sini 2"))
        domain_is_user = expression.AND([[('name', 'ilike', search), ('is_user', '=', True), ('company_id', 'in', self.env.user.company_ids.ids)], search_dom])
        open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + str("masuk sini 3 " + str(domain_is_user)))

        priority_conditions = [
            expression.AND([domain_is_user, [('name', 'ilike', search), ('is_user', '=', True), ('company_id', 'in', self.env.user.company_ids.ids)]]),  # Search partners that are internal users
            domain_is_user,  # Search partners that are users
            search_dom,  # Search partners that are not users
        ]
        partners = self.env['res.partner']

        open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + str("masuk sini 4 " + str(priority_conditions)))
        for domain in priority_conditions:
            #open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + str("masuk sini 5"))
            remaining_limit = limit - len(partners)
            if remaining_limit <= 0:
                break
            partners |= self.search(expression.AND([[('name', 'ilike', search), ('is_user', '=', True), ('company_id', 'in', self.env.user.company_ids.ids)], domain]), limit=remaining_limit)
        partners_format = partners.mail_partner_format()

        if channel_id:
            open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + str("masuk sini 8"))
            member_by_partner = {member.partner_id: member for member in self.env['mail.channel.member'].search([('name', 'ilike', search), ('is_user', '=', True), ('company_id', 'in', self.env.user.company_ids.ids)])}
            for partner in partners:
                partners_format.get(partner)['persona'] = {
                    'channelMembers': [('insert', member_by_partner.get(partner)._mail_channel_member_format(fields={'id': True, 'channel': {'id'}, 'persona': {'partner': {'id'}}}).get(member_by_partner.get(partner)))],
                }

        open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + str("masuk sini 9 : " + str(partners_format)))
        return list(partners_format.values())



    @api.model
    def signup_retrieve_info(self, token):
        """ retrieve the user info about the token
            :return: a dictionary with the user information:
                - 'db': the name of the database
                - 'token': the token, if token is valid
                - 'name': the name of the partner, if token is valid
                - 'login': the user login, if the user already exists
                - 'email': the partner email, if the user does not exist
        """
        partner = self._signup_retrieve_partner(token, raise_exception=True)
        res = {'db': self.env.cr.dbname}
        if partner.signup_valid:
            res['token'] = token
            res['name'] = partner.name
        if partner.user_ids:
            res['login'] = partner.user_ids[0].login
        else:
            res['email'] = res['login'] = partner.email or ''
        return res


    @api.depends_context('company')
    def _credit_debit_get(self):
        print ("tes")
        return



    @api.onchange('name')
    def set_upper(self):
        val = str(self.name)
        self.name = val.upper()



    @api.depends('registration_code','doctor_code','patient','doctor')
    def _partner_code(self):
        if self.doctor is True:
            self.vendor_code = self.doctor_code
        elif self.patient is True:
            self.vendor_code = self.registration_code
        elif self.customer is True or self.supplier is True:
            if not self.vendor_code:
                self.vendor_code = '[NONE]'


    # @api.model
    # def search(self, args, offset=0, limit=None, order=None, count=False):
    #     args = self.rule(args) #INI MANGGIL RULE
    #     return super(StockPicking, self).search(args, offset=offset, limit=limit, order=order, count=count)



    # @api.multi
    # def send_api_consol(self):
    #     now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    #     for record in self:
    #         consol_active = record.env.company.sync_consol_res_partner
    #         consol_url = record.env.company.sync_consol_url
    #         consol_type = record.env.company.sync_consol_type
    #         consol_id_to = ""
    #         consol_id_from = ""
    #         if consol_active:
    #             if consol_type == 'unit':
    #                 url = consol_url + "/internal_api/unit/create/res.partner"
    #                 consol_id_to = 'sync_consol_id_main'
    #                 consol_id_from = 'sync_consol_id_unit'
    #             if consol_type == 'main':
    #                 url = consol_url + "/internal_api/main/create/res.partner"
    #                 consol_id_to = 'sync_consol_id_unit'
    #                 consol_id_from = 'sync_consol_id_main'

    #             if not record.env.user.token_consol:
    #                 record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)

    #             headers = {}
    #             headers['Content-Type'] = 'application/x-www-form-urlencoded'
    #             body = {}
    #             body['csrf_token'] = record.env.user.token_consol
    #             values = {}
    #             values['sync_type'] = int(record.env.company.sync_type)
    #             values[consol_id_from] = record.id
    #             values['name'] = record.name
    #             values['display_name'] = record.name
    #             values['phone'] = record.phone
    #             values['mobile'] = record.mobile
    #             values['fax'] = record.fax
    #             values['email'] = record.email
    #             values['street'] = record.street
    #             values['street2'] = record.street2
    #             values['city'] = record.city
    #             values['zip'] = record.zip
    #             values['supplier'] = True
    #             values['vendor_code'] = record.vendor_code
    #             values['company_id'] = record.company_id.sync_consol_id_main
    #             values['company_type'] = record.company_type
    #             body['values'] = json.dumps(values)

    #             cookies = {'session_id': record.env.user.cookies}

    #             print('\n' + "body : " + str(body))
    #             print('\n' + "headers : " + str(headers))
    #             print('\n' + "url : " + str(url))

    #             response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
    #             print (response_json.status_code)
    #             if response_json.status_code != 200:
    #                 record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
    #                 cookies = {'session_id': record.env.user.cookies}
    #                 body['csrf_token'] = False
    #                 body['csrf_token'] = record.env.user.token_consol
    #                 response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

    #             try:
    #                 json_resp = response_json.json()
    #             except:
    #                 record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
    #                 cookies = {'session_id': record.env.user.cookies}
    #                 body['csrf_token'] = False
    #                 body['csrf_token'] = record.env.user.token_consol
    #                 response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
    #                 json_resp = response_json.json()

    #             api_status = 'failed'

    #             print('\n' + "json_resp : " + str(json_resp))

    #             data_sent = False
    #             response_id = False

    #             if 'status' in json_resp:
    #                 if json_resp['status'] == 'success':
    #                     api_status = 'success'
    #                     data_sent = True
    #                     for d in json_resp['data']:
    #                         if 'id' in d:
    #                             response_id = d['id']


    #             data_update = {
    #                 consol_id_to : response_id,
    #                 'sync_consol_response': json_resp,
    #                 'sync_consol_response_status': api_status,
    #                 'sync_consol_date': now,
    #                 'sync_consol_sent' : data_sent
    #                 }
    #             super(ResPartner, self).write(data_update)


    # @api.multi
    def send_api_consol_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_res_partner
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/res.partner"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/res.partner"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                ############Chaelvin##############
                headers = {}
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = {}
                body['csrf_token'] = record.env.user.token_consol
                values = {}
                lst = []
                values['sync_type'] = str(record.company_id.sync_type)
                values[consol_id_from] = str(record.id)
                values['name'] = record.name
                values['display_name'] = record.name
                values['phone'] = record.phone
                values['mobile'] = record.mobile
                values['fax'] = record.fax
                values['email'] = record.email
                values['ref'] = record.ref
                values['street'] = record.street
                values['street2'] = record.street2
                values['city'] = record.city
                values['zip'] = record.zip
                values['trigger_create'] = True
                
                values['website'] = record.website
                values['supplier'] = record.supplier
                values['customer'] = record.customer
                values['customer_wipro'] = record.customer_wipro
                values['vendor_wipro'] = record.vendor_wipro
                values['doctor'] = record.doctor
                values['patient'] = record.patient
                values['wipro_block'] = record.wipro_block

                values['vendor_code'] = record.vendor_code
                values['company_type'] = record.company_type

                if record.company_id.id == False:
                    values['company_id'] = record.company_id.id
                else:
                    values['company_id'] = str(record.company_id.id)

                if record.user_id.id == False:
                    values['user_id'] = record.user_id.id
                else:
                    values['user_id'] = str(record.user_id.id)

                if record.property_account_receivable_id.id == False:
                    values['property_account_receivable_id'] = record.property_account_receivable_id.id
                else:
                    values['property_account_receivable_id'] = str(record.property_account_receivable_id.id)

                if record.property_account_payable_id.id == False:
                    values['property_account_payable_id'] = record.property_account_payable_id.id
                else:
                    values['property_account_payable_id'] = str(record.property_account_payable_id.id)
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

                lst.append(values)
                body['values'] = json.dumps(lst)
                # body['values'] = json.dumps(values)
                
                cookies = {'session_id': record.env.user.cookies}

                print('\n' + "body : " + str(body))
                print('\n' + "headers : " + str(headers))
                print('\n' + "url : " + str(url))

                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "body create res.partner : " + str(body))
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
                super(ResPartner, self).write(data_update)

    # @api.multi
    def send_api_consol_write_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_res_partner
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/res.partner"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/res.partner"
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
                values['name'] = record.name
                values['display_name'] = record.name
                values['phone'] = record.phone
                values['mobile'] = record.mobile
                values['fax'] = record.fax
                values['email'] = record.email
                values['ref'] = record.ref
                values['street'] = record.street
                values['street2'] = record.street2
                values['city'] = record.city
                values['zip'] = record.zip
                values['trigger_write'] = False
                
                values['website'] = record.website
                values['supplier'] = record.supplier
                values['customer'] = record.customer
                values['customer_wipro'] = record.customer_wipro
                values['vendor_wipro'] = record.vendor_wipro
                values['doctor'] = record.doctor
                values['patient'] = record.patient
                values['wipro_block'] = record.wipro_block

                values['vendor_code'] = record.vendor_code
                values['company_type'] = record.company_type

                if record.company_id.id == False:
                    values['company_id'] = record.company_id.id
                else:
                    values['company_id'] = str(record.company_id.id)

                if record.user_id.id == False:
                    values['user_id'] = record.user_id.id
                else:
                    values['user_id'] = str(record.user_id.id)
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

                lst.append(values)
                body['values'] = json.dumps(lst)
                # body['values'] = json.dumps(values)
                
                cookies = {'session_id': record.env.user.cookies}

                print('\n' + "body : " + str(body))
                print('\n' + "headers : " + str(headers))
                print('\n' + "url : " + str(url))
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "body write res.partner : " + str(body))

                # raise exceptions.ValidationError(_(str(body)))
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
                super(ResPartner, self).write(data_update)


    # @api.multi
    @api.depends('name', 'vendor_code')
    def name_get(self):
        result = []

        for partner in self:
            if partner.customer or partner.supplier:
                if partner.vendor_code and not partner.patient:
                    name = str(partner.vendor_code) + ' ' + str(partner.name)
                else:
                    name = str(partner.name)
            else:
                name = str(partner.name)
            result.append((partner.id, name))
        return result


    # @api.multi
    @api.constrains('bank_information_ids')
    def bank_information(self):
        for rec in self:
            if rec.supplier:
                if not rec.bank_information_ids:
                    raise exceptions.ValidationError(_('Bank Information must be filled'))


    @api.model
    def ar_account_setup(self, sync_type='1'):
        partner = self.env['res.partner'].search([('customer_wipro', '=', True)]).mapped('account_ar_id')
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010203' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_wipro) like 'GOVERNMENT' and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010203' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_wipro) like '%BPJS%' and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010202' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_wipro) like 'INSURANCE' and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010201' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_wipro) like 'CORPORATE' and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010205' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_wipro) like 'EMPLOYEE' and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010204' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_wipro) like 'REFERRAL' and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010206' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_wipro) like 'PERSONAL' and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010207' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_wipro) like 'E-COMMERCE'and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010206' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_wipro) like 'PRIVATE CREDIT' and account_ar_updated is not True")
        
        # import pdb; pdb.set_trace()
        # different = self.env['res.partner'].search([('customer_wipro', '=', True), ('property_account_receivable_id', 'not in', partner.ids)])
        # different = self.env['res.partner'].search([('id', '=', 205234)])
        # if different:
        #     for d in different:D
        #         # d.write({'property_account_receivable_id': d.account_ar_id})
        #         d.property_account_receivable_id = d.account_ar_id.id
        #         # import pdb; pdb.set_trace()

    @api.model
    def ar_account_setup_api(self, sync_type='4'):
        self.env.cr.execute("UPDATE res_partner rp set account_ar_updated = False where account_ar_id is null and customer_wipro = true""")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010201' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_api) ilike 'CORPORATE' and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010205' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_api) ilike 'EMPLOYEE' and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010207' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_api) ilike 'E-COMMERCE'and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010203' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_api) ilike 'GOVERNMENT' and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010202' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_api) ilike 'INSURANCE' and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010205' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_api) ilike 'MAYAPADA' and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010206' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_api) ilike 'PRIVATE CREDIT' and account_ar_updated is not True")
        self.env.cr.execute("UPDATE res_partner rp set account_ar_id = (select id from account_account where code like '1104010204' and company_id = rp.company_id), account_ar_updated = True where UPPER(customer_type_api) ilike 'REFERRAL' and account_ar_updated is not True")
        # try:
        #     self.env.cr.execute("""DELETE from res_partner where id in (select max(a.id) from res_partner a where a.sync_id_api is not null group by a.sync_id_api having count(*) > 1)""")
        # except:
        #     pass

    # @api.model
    # def name_search(self, name='', args=None, operator='ilike', limit=100):
    #     try:
    #         return super(ResPartner, self).name_search(name=name, args=args, operator=operator, limit=limit)
    #     except:
    #         import traceback
    #         raise exceptions.ValidationError(traceback.format_exc())

    @api.model
    def _update_doctor_external(self, vals):
                
        # declare:: modify by Dudi #20220413
        sync_type = vals['sync_type']
        doctor_code = vals['doctor_code']
        sync_id_api = vals['sync_id_api']
        
        if doctor_code:
            # update res.partner
            query1 = """
                UPDATE res_partner SET sync_id_api = '{sync_id_api}', sync_date = CURRENT_TIMESTAMP
                    WHERE sync_type='{sync_type}' AND doctor_code='{doctor_code}' AND active = True
            """.format(sync_type=sync_type, doctor_code=doctor_code, sync_id_api=sync_id_api)
            self.env.cr.execute(query1)
            
            # update account.analytic.account
            query2 = """
                UPDATE account_analytic_account SET sync_id_api = '{sync_id_api}', sync_date = CURRENT_TIMESTAMP 
                WHERE sync_type='{sync_type}' AND code='{doctor_code}' AND active = True
            """.format(sync_type=sync_type, doctor_code=doctor_code, sync_id_api=sync_id_api)
            self.env.cr.execute(query2)
            
            if sync_id_api is None:
                result = super(ResPartner, self).create(vals)
            else:
                result = self.env['res.partner'].search([('sync_type', '=', sync_type), ('sync_id_api', '=', sync_id_api)])
        
        return result
    
    @api.model
    def create(self, vals):
        from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
        from datetime import datetime
        import os

        # # define now datetime
        # now = datetime.now()
        # now_formatted = now.strftime("%Y-%m-%d %H:%M:%S")

        # # define python timezone
        # import pytz
        # local = pytz.timezone('Asia/Jakarta')
        # log_date = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y%m%d")
        # log_year = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y")
        # log_month = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        # log_day = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        # #log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local),"%H%M%S.%f")
        # log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        # log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'res.partner' + '/'
        # log_name = log_date + '_' + 'create' + '_' + 'res.partner'
        # log_file = log_dir + log_name + '.log'

        # log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # # create dir if not exists
        # if not os.path.exists(log_dir):
        #     os.makedirs(log_dir)
        # os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        # message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        # message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        # open(log_file, 'a').write(message_log)
        # open('/opt/odoo16/logs/log_res_partner_test.log', 'a+').write('\n\n' + str(vals))
        result = super(ResPartner, self).create(vals)

        # 2025.08.11 - Bypass new vendor creation in Odoo Unit & Consol
        # open('/opt/odoo16/logs/log_res_partner_vals.log', 'a+').write(str(vals))
        if (result.supplier and not result.company_id.enable_create_vendor) and not result.sync_id_api:
            raise UserError("Not allowed to create new master vendor from Odoo, Please contact Procurement to manage master data Vendor from HIS. Vendor changes in HIS will automatically synchronize to Odoo Unit & ERP on H+1.")


        if self.env.context.get('is_user'):
            open('/opt/odoo16/logs/log_res_partner.log','a+').write('\n is_user=True')
            return result
        
        for r in result:
            if self.env.company.sync_api_active:
                r.ar_account_setup_api(sync_type=r.sync_type)
                if r.doctor == True and r.type_doctor == 'internal':
                    r.env['account.analytic.account']._sync_doctor_internal_api(id_partner=r.id, sync_id_partner=r.sync_id_api, id_specialise=r.spec, sync_type=r.sync_type)
                if r.doctor == True and r.type_doctor == 'external':
                    r.env['account.analytic.account']._sync_doctor_external_api(id_partner=r.id, sync_id_partner=r.sync_id_api, id_specialise=r.spec, code=r.doctor_code, sync_type=r.sync_type)
                if r.customer_wipro == True:
                    r.insurance = True
            #else:
            #    self.ar_account_setup()

        if vals.get('company_id'):
            company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
            result.sync_type = company_id.sync_type

        if vals.get('patient'):
            if not result.vendor_code:
                result.vendor_code = result.registration_code

        if (result.trigger_create == False and result.company_id.name != 'Mayapada Hospital Bogor') or (result.trigger_create == False and result.company_id.name == 'Mayapada Hospital Bogor' and result.supplier ==True):
            # jika res_partner tidak related dengan res.users
            if self.is_user is not True:
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger create res partner")
                result.send_api_consol_company()
                for tes_loop in result.bank_information_ids:
                    tes_loop.send_api_consol_company()
        # log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        # message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        # message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " +str(result.id)

        # open(log_file, 'a').write(message_log)
        return result

    # except:
    #    import traceback
    #    raise UserError(traceback.format_exc())



    # @api.multi
    def write(self, vals):
        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "Write res partner")
        # open('/opt/odoo16/logs/log_change_user.log', '+a').write('\n ubah res.partner disini 2')
        from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
        from datetime import datetime
        import os

        # # define now datetime
        # now = datetime.now()
        # now_formatted = now.strftime("%Y-%m-%d %H:%M:%S")

        # # define python timezone
        import pytz
        # local = pytz.timezone('Asia/Jakarta')
        # log_date = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y%m%d")
        # log_year = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y")
        # log_month = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        # log_day = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        # #log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local),"%H%M%S.%f")
        # log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        # log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'res.partner' + '/'
        # log_name = log_date + '_' + 'write' + '_' + 'res.partner'
        # log_file = log_dir + log_name + '.log'

        # log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # # create dir if not exists
        # if not os.path.exists(log_dir):
        #     os.makedirs(log_dir)
        # os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        # message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        # message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        # open(log_file, 'a').write(message_log)
        if vals.get('account_ar_id') or vals.get('account_ap_id') or vals.get('property_account_payable_id') or vals.get('property_account_receivable_id'):
            group_access = ['Finance & Accounting - Configuration','Finance & Accounting - Corporate','Finance & Accounting - Ka.Dept Accounting & Finance']
            group_allows = self.sudo().env['res.groups'].search([('name','in', group_access)]).ids
            group_valid = False
            for group_id in self.env.user.groups_id:
                if group_id.id in group_allows:
                    group_valid = True
                    break;
           
            open('/opt/odoo16/logs/log_res_partner.log', 'a+').write('\n ' + str(group_access))
            open('/opt/odoo16/logs/log_res_partner.log', 'a+').write('\n ' + str(group_allows))
            open('/opt/odoo16/logs/log_res_partner.log', 'a+').write('\n ' + str(group_valid))

            if vals.get('account_ar_id') and self.account_ar_id and not group_valid:
                raise exceptions.ValidationError( "Only user with this access are allowed to change AR Account: \n %s" % (" \n".join(group_access)))
            if vals.get('property_account_receivable_id') and self.property_account_receivable_id and not group_valid:
                raise exceptions.ValidationError( "Only user with this access are allowed to change AR Account: \n %s" % (" \n".join(group_access)))

            if vals.get('account_ap_id') and self.account_ap_id and not group_valid:
                raise exceptions.ValidationError( "Only user with this access are allowed to change AP Account: \n %s" % (" \n".join(group_access)))
            if vals.get('property_account_payable_id') and self.property_account_payable_id and not group_valid:
                raise exceptions.ValidationError( "Only user with this access are allowed to change AP Account: \n %s" % (" \n".join(group_access)))
        
        result = super(ResPartner, self).write(vals)

        if self.env.context.get('is_user'):
            open('/opt/odoo16/logs/log_res_partner.log','a+').write('\n is_user=True')
            return result

        if self.env.context.get('writed'):
            return result

        self = self.with_context(writed=True)
        for record in self:

            if record.customer_wipro == True:
                record.insurance = True
                if vals.get('customer_type_wipro'):
                    record.ar_account_setup()
            
            if record.doctor == True and record.type_doctor == 'internal':
                doctor = record.env['account.analytic.account'].search([('partner_id', '=', record.id), ('sync_type', '=', record.sync_type)])
                for d in doctor:
                    d.name = record.name
                    d.sync_wipro_type = 'doctor_internal'

            if record.doctor == True and record.type_doctor == 'external':
                doctor = record.env['account.analytic.account'].search([('partner_id', '=', record.id), ('sync_type', '=', record.sync_type)])
                for d in doctor:
                    d.name = record.name
                    d.sync_wipro_type = 'doctor_external'

        if self.company_id:
            self.sync_type = self.company_id.sync_type
        
        if (self.trigger_write == True and self.company_id.name != 'Mayapada Hospital Bogor') or (self.trigger_write == True and self.company_id.name == 'Mayapada Hospital Bogor' and self.supplier ==True):
            if self.is_user is not True:
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger write res partner")
                query = """
                UPDATE res_partner set trigger_write = false
                WHERE id = {self_id}""".format(self_id = self.id)
                self.env.cr.execute(query)
                self.send_api_consol_write_company()   
        # log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        # message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        # message_log += "\n\nuser: " + self.env.user.login + "\n\n Write before return" + "\n ID: " +str(self.id)

        # open(log_file, 'a').write(message_log)         
        return result


    @api.onchange('sync_type', 'name','phone','mobile','fax','email','ref','street','street2','city','zip','website','supplier','customer','customer_wipro','vendor_wipro','doctor','patient','wipro_block','vendor_code','company_type','company_id','user_id')
    def onchange_trigger_write(self):
        self.trigger_write = True


    # @api.multi
    def read(self, fields=None, load='_classic_read'):
        for index, field in enumerate(list(fields or [])):
            if field == 'total_invoiced':
                del fields[index]
        return super(ResPartner, self).read(fields=fields, load=load)


    # @api.one
    @api.depends('date_of_birth')
    def _age(self):
        for record in self:
            if record.date_of_birth:
                record.age = tools.relativedelta(tools.datetime.now(), tools.datetime.strptime(record.date_of_birth, '%Y-%m-%d')).years




    @api.model
    def rule(self, domain):
        if not domain:
            domain = []
        if self.env.user.id == 1:
            return domain
        # domain += ['|', ('company_id', '=', False),('company_id', 'child_of', [self.env.company.id])]
        domain += ['|', ('company_id', '=', False),('company_id', 'in', self.env.user.company_ids.ids)]
        return domain

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        args = self.rule(args)
        return super(ResPartner, self).search(args,offset=offset,limit=limit,order=order,count=count)

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = self.rule(args)
        recs = self.search([('vendor_code', operator, name),('company_id', 'child_of', [self.env.company.id])] + args,limit=limit)
        if not recs.ids:
            return super(ResPartner, self).name_search(name,args=args,operator=operator,limit=limit)
        return recs.name_get()


    @api.model
    def api_generate_payload(self, action = 'block'):
        payload = {}
        for record in self:
            if record.insurance == True and record.sync_id_api:
                payload["payer_id"] = record.id # payer_id odoo
                payload["payer_id_api"] = record.sync_id_api # payer_id_api dhealth
                payload["payer_limit"] = record.credit_limit or 0 
                payload["payer_aging"] = record.payer_aging or 0 
                payload["payer_block"] = action
        return payload


    # @api.multi
    def _credit_debit_get(self):
        print("Do something")
        # tables, where_clause, where_params = self.env['account.move.line'].with_context(company_id=self.env.company.id)._query_get()
        # where_params = [tuple(self.ids)] + where_params
        # if where_clause:
        #     where_clause = 'AND ' + where_clause
        # self._cr.execute("""SELECT account_move_line.partner_id, act.type, SUM(account_move_line.balance)
        #               FROM account_move_line
        #               INNER JOIN account_move mv ON (mv.id=account_move_line.move_id)
        #               LEFT JOIN account_account a ON (account_move_line.account_id=a.id)
        #               LEFT JOIN account_account_type act ON (a.user_type_id=act.id)
        #               WHERE act.type IN ('receivable','payable','other')
        #               AND account_move_line.partner_id IN %s
        #               -- AND account_move_line.reconciled IS FALSE
        #               AND mv.state = 'posted'
        #               AND (LEFT(a.code,6) = '110401' OR LEFT(a.code,4) in('2102','2103'))
        #               """ + where_clause + """
        #               GROUP BY account_move_line.partner_id, act.type
        #               """, where_params)
        # for pid, type, val in self._cr.fetchall():
        #     partner = self.browse(pid)
        #     if type == 'receivable':
        #         partner.credit = val
        #         partner.payer_aging = val

        #         # auto send block/unblock to HIS
        #         if partner.payer_autoblock:
        #             if partner.payer_aging >= partner.credit_limit and partner.payer_block == False:
        #                 partner.send_api_payer_block()
        #             elif partner.payer_aging < partner.credit_limit and partner.payer_block == True:
        #                 partner.send_api_payer_unblock()

        #     # elif type == 'payable':
        #     else:
        #         partner.debit = -val


    # auto block/unblock payer 
    # @api.multi 
    def compute_payer_aging(self):
        print("Do something")
        for partner in self:
            tables, where_clause, where_params = self.env['account.move.line'].with_context(company_id=self.env.company.id)._query_get()
            where_params = [tuple(self.ids)] + where_params
            if where_clause:
                where_clause = 'AND ' + where_clause
            self._cr.execute("""SELECT account_move_line.partner_id, act.type, SUM(account_move_line.balance)
                          FROM account_move_line
                          INNER JOIN account_move mv ON (mv.id=account_move_line.move_id)
                          LEFT JOIN account_account a ON (account_move_line.account_id=a.id)
                          LEFT JOIN account_account_type act ON (a.user_type_id=act.id)
                          WHERE act.type IN ('receivable','payable','other')
                          AND account_move_line.partner_id IN %s
                          -- AND account_move_line.reconciled IS FALSE
                          AND mv.state = 'posted'
                          AND (LEFT(a.code,6) = '110401' OR LEFT(a.code,4) in('2102','2103'))                     
                          """ + where_clause + """
                          GROUP BY account_move_line.partner_id, act.type
                          """, where_params)

            for pid, type, val in self._cr.fetchall():
                if type == 'receivable':
                    partner.credit = val
                    partner.payer_aging = val

                    # auto send block/unblock to HIS
                    if partner.payer_autoblock:
                        if partner.payer_aging >= partner.credit_limit and partner.payer_block == False:
                            partner.send_api_payer_block()
                        elif partner.payer_aging < partner.credit_limit and partner.payer_block == True:
                            partner.send_api_payer_unblock()

                #elif type == 'payable':
                else:
                    partner.debit = -val


    # set send_api_payload to his for block payer by aging
    # @api.multi 
    def send_api_payer_block(self):
        for record in self:
            # api block HIS payer by aging 
            # kondisi payer_aging sudah melebihi credit_limit 
            # kondisi payer sudah "block" tapi gagal submit ke dhealth, maka bisa resend 
            if self.env.company.sync_api_active == True and ((record.payer_block == True and record.api_post_status != 'done') or record.payer_block==False):
                api_payload = self.api_generate_payload('block')
                api_endpoint = self.env.company.his_api_url + '/on/payer_block/create'
                api_headers = {'Content-Type': 'application/json', 'X-Behaviour':'blocking', 'Authorization': 'Key ' + self.env.company.his_api_key }

                open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n\n' + str(api_endpoint))
                open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n' + str(api_headers) + '\n' + str(api_payload))
                response_json = requests.post(url=api_endpoint, headers=api_headers, json=api_payload, verify=False)
                json_resp = response_json.json()
                api_post_status = 'failed'
                if 'status' in json_resp:
                    api_post_status = ('done' if json_resp['status'] == 'success' else 'failed')
                now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                data = {'api_post_payload': api_payload, 'api_post_response': json_resp, 'api_post_timestamp': now, 'api_post_status': api_post_status}
                write_result = super(ResPartner, self).write(data)
            
            # block res.partner 
            record.payer_block = True 


    # set send_api_payload to his for unblock payer by aging
    # @api.multi 
    def send_api_payer_unblock(self):
        for record in self:
            # api block HIS payer by aging 
            # kondisi payer_aging sudah kurang dari credit_limit 
            # kondisi payer sudah "block" tapi gagal submit ke dhealth, maka bisa resend 
            if self.env.company.sync_api_active == True and ((record.payer_block == False and record.api_post_status != 'done') or record.payer_block==True):
                api_payload = self.api_generate_payload('unblock')
                api_endpoint = self.env.company.his_api_url + '/on/payer_block/create'
                api_headers = {'Content-Type': 'application/json', 'X-Behaviour':'blocking', 'Authorization': 'Key ' + self.env.company.his_api_key }

                open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n\n' + str(api_endpoint))
                open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n' + str(api_headers) + '\n' + str(api_payload))
                response_json = requests.post(url=api_endpoint, headers=api_headers, json=api_payload, verify=False)
                json_resp = response_json.json()
                api_post_status = 'failed'
                if 'status' in json_resp:
                    api_post_status = ('done' if json_resp['status'] == 'success' else 'failed')
                now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                data = {'api_post_payload_cancel': api_payload, 'api_post_response_cancel': json_resp, 'api_post_timestamp_cancel': now, 'api_post_status_cancel': api_post_status}
                write_result = super(ResPartner, self).write(data)
            
            # unblock res.partner 
            record.payer_block = False 


#     @api.model
#     def _sync_vendor_wipro(self, sync_type='1'):
#         sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '!=',False), ('vendor_wipro', '=',True), ('active', '=',True)])}
#         sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name), ('sync_type', '=', sync_type)], limit=1)
#         query = """ 
#          SELECT  
#             a.SupplierID 'sync_id',
#             a.SupplierCode 'vendor_code',
#             a.SupplierName 'name',
#             a.SupplierName 'display_name',
#             a.PhoneNo 'phone',
#             a.FaxNo 'fax',
#             a.MobileNo 'mobile',
#             a.Email 'email',
#             a.ContactPerson 'contact_person',
#             a.Address1 'street',
#             a.Address2 'street2',
#             a.Address3 'street3',
#             a.WebSite 'website',
#             a.City 'city',
#             a.ZipCode 'zip',
#             a.CreditLimitDays 'credit_days',
#             a.TermID 'term_id',
#             a.TermsSequence 'term_sequence',
#             cast(a.Blocked as bit) 'wipro_block',
#             cast('True' as bit) 'supplier',
#             cast('True' as bit) 'vendor_wipro',
#             cast('False' as bit) 'customer',
#             cast('False' as bit) 'customer_wipro',
#             cast('False' as bit) 'insurance',
#             cast('False' as bit) 'patient',
#             cast('False' as bit) 'doctor',
#             cast('True' as bit) 'active'
#         FROM (
#             SELECT DISTINCT  VEN.*, (CASE
#                 WHEN CompUpdated > SuppUpdated 
#                 THEN CompUpdated ELSE SuppUpdated
#             END) LastUpdated
#             FROM dbo.VRP_OdooSupplier VEN
#             INNER JOIN dbo.VRP_OdooPurchaseReceipt PRC ON PRC.partner_id=VEN.SupplierID
#             WHERE CONVERT(VARCHAR(10), PRC.date_order, 121) >= '{0}'
#             OR CONVERT(VARCHAR(10), CompUpdated, 121) >= '{0}'
#             OR CONVERT(VARCHAR(10), SuppUpdated, 121) >= '{0}'
#         ) a """.format(tools.datetime.strptime(sync_date.date,'%Y-%m-%d %H:%M:%S').date())
#         if sync_date:
#             print (query)
#             sync_date.date = tools.datetime.now().strftime('%Y-%m-%d')
#         else:
#             self.env['sync.date'].sudo().create({
#                 'name':sync.getframe().f_code.co_name,
#                 'sync_type':sync_type
#             })

#         data = sync.get_data(sync.servers.get(sync_type), query)
#         if not data:
#             print ("No new data available")
#             return
#         fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and self._fields[key].required == True)
#         columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type','company_id') if data else ()
#         fields_without_id += columns
#         fields = fields_without_id + ('id', )
#         if columns:
#             columns += ('id', )
#         default_values = {}
#         for field in fields:
#             if field in columns:
#                 continue
#             default = self._fields[field].default
#             if callable(default):
#                 default = default(self)
#             if isinstance(default, models.Model):
#                 default = default.id
#             default_values[field] = default
#         values = ''
#         now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
#         for object in data:
#             for value in default_values:
#                 object[value] = default_values[value]
#             if int(object['sync_id']) in sync_ids:
#                 object['id'] = sync_ids[object['sync_id']]
#             else:
#                 object['id'] = 'DEFAULT'
#             #object['vendor_wipro'] = True
#             object['sync_date'] = now
#             object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].search([('sync_type', '=', sync_type)],limit=1).id
#             if values:
#                 values += ', '
#             value = False
#             for field in fields:
#                 if value:
#                     value += ', '
#                 else:
#                     value = '('
#                 if field == 'id' and object['id'] == 'DEFAULT':
#                     value += object['id']
#                     continue
#                 if type(object[field]) in [str, unicode]:
#                     string = object[field]
#                     value += "'" + string.replace("'", "''") + "'"
#                     continue
#                 value += sync.json(object[field])
#             value += ')'
#             values += value
#         excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
#         columns = sync.remove_unicode(str(fields)).replace("'", "")
#         columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
#         query = "INSERT into res_partner %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
#         set_vendor = "UPDATE res_partner SET supplier = True where vendor_wipro = True and supplier is not true"
#         print (query.encode('utf8'))
#         self.env.cr.execute(query)
#         self.env.cr.execute(set_vendor)
#         self.env.cr.execute("UPDATE res_partner set commercial_partner_id = id where commercial_partner_id is null")


#     @api.model
#     def _sync_customer_wipro(self, sync_type='1'):
#         sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '!=',False), ('customer_wipro', '=',True), ('active', '=',True)])}
#         sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name), ('sync_type', '=', sync_type)], limit=1)
#         query = """
#             SELECT 
#                 a.CustomerID 'sync_id', 
#                 a.CustomerCode 'vendor_code',
#                 a.CustomerName 'name', 
#                 a.CustomerName 'display_name', 
#                 a.CustomerTypeName 'customer_type_wipro',
#                 a.ContactPerson 'contact_person', 
#                 a.PhoneNo 'phone',
#                 a.MobileNo 'mobile', 
#                 a.FaxNo 'fax', 
#                 a.Email 'email',
#                 a.WebSite 'website', 
#                 a.Address1 'street', 
#                 a.Address2 'street2', 
#                 a.Address3 'street3', 
#                 a.City 'city', 
#                 a.ZipCode 'zip', 
#                 a.CreditDays 'credit_days', 
#                 a.OpDiscountID,
#                 a.IPDiscountID, 
#                 a.TaxID, 
#                 a.payer_new,
#                 cast(a.Blocked as bit) 'wipro_block',
#                 cast('False' as bit) 'supplier',
#                 cast('False' as bit) 'vendor_wipro',
#                 cast('True' as bit) 'customer',
#                 cast('True' as bit) 'customer_wipro',
#                 cast('True' as bit) 'insurance',
#                 cast('False' as bit) 'patient',
#                 cast('False' as bit) 'doctor',
#                 cast('True' as bit) 'active'
#             from (
#                 select *, (case 
#                     when CompUpdated > SuppUpdated 
#                     then CompUpdated else SuppUpdated
#                     end) LastUpdated
#                 from dbo.VRP_OdooCustomer 
#             ) a 
#          """
#         if sync_date:
#             query += """ WHERE a.CustomerID IN(
#                     SELECT DISTINCT t.PayerID
#                     FROM dbo.A_A_RawDataH30 t 
#                     WHERE CONVERT(varchar(10), t.tglproses, 121) >= '{0}' 
#                 ) OR CONVERT(varchar(10), a.LastUpdated, 121) >= '{0}'""".format(
#                 tools.datetime.strptime(sync_date.date,'%Y-%m-%d %H:%M:%S').date())
#             print (query)
#             sync_date.date = tools.datetime.now().strftime('%Y-%m-%d')
#         else:
#             self.env['sync.date'].sudo().create({
#                 'name':sync.getframe().f_code.co_name,
#                 'sync_type':sync_type
#             })
#         data = sync.get_data(sync.servers.get(sync_type), query)
#         if not data:
#             print ("No new data available")
#             return
#         fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and self._fields[key].required == True)
#         columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type','company_id') if data else ()
#         fields_without_id += columns
#         fields = fields_without_id + ('id', )
#         if columns:
#             columns += ('id', )
#         default_values = {}
#         for field in fields:
#             if field in columns:
#                 continue
#             default = self._fields[field].default
#             if callable(default):
#                 default = default(self)
#             if isinstance(default, models.Model):
#                 default = default.id
#             default_values[field] = default
#         values = ''
#         now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
#         for object in data:
#             for value in default_values:
#                 object[value] = default_values[value]
#             if int(object['sync_id']) in sync_ids:
#                 object['id'] = sync_ids[object['sync_id']]
#             else:
#                 object['id'] = 'DEFAULT'
#             #object['customer_wipro'] = True
#             object['sync_date'] = now
#             object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].search([('sync_type', '=', sync_type)],limit=1).id
#             if values:
#                 values += ', '
#             value = False
#             for field in fields:
#                 if value:
#                     value += ', '
#                 else:
#                     value = '('
#                 if field == 'id' and object['id'] == 'DEFAULT':
#                     value += object['id']
#                     continue
#                 if type(object[field]) in [str, unicode]:
#                     string = object[field]
#                     value += "'" + string.replace("'", "''") + "'"
#                     continue
#                 value += sync.json(object[field])
#             value += ')'
#             values += value
#         excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
#         columns = sync.remove_unicode(str(fields)).replace("'", "")
#         columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
#         query = "INSERT into res_partner %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
#         set_customer = "update res_partner set customer = True and insurance = True where customer_wipro = True"
#         print (query.encode('utf8'))
#         self.env.cr.execute(query)
#         self.env.cr.execute(set_customer)


#     @api.model
#     def _sync_doctor_internal_wipro(self, sync_type='1'):
#         sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '!=',0), ('sync_id', '!=',False), ('doctor', '=', True), ('type_doctor', '=', 'internal'), ('active', '=', True)])}
#         sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name),('sync_type', '=', sync_type)],limit=1)
#         query = """
#             SELECT 
#                 a.DoctorID 'sync_id', 
#                 a.DoctorCode 'doctor_code', 
#                 a.DoctorCode 'vendor_code', 
#                 a.DoctorName 'name', 
#                 a.DoctorName 'display_name', 
#                 isnull(a.Specialisation,'') as spec,
#                 a.DepartmentName 'department', 
#                 a.EmploymentType 'type_employment', 
#                 a.Designation 'designation', 
#                 a.HrProfile 'hrprofile', 
#                 lower(a.Gender) 'gender', 
#                 a.Phone 'phone', 
#                 a.Mobile 'mobile',
#                 a.Email 'email', 
#                 a.[Address] 'street',
#                 a.SpecialiseID 'specialise_id',
#                 (case when a.Blocked = 1 then 'TRUE' else 'FALSE' end ) as EmpBlocked, 
#                 LOWER(a.DoctorType) 'type_doctor', 
#                 cast(a.Blocked as bit) 'wipro_block',
#                 cast('False' as bit) 'supplier',
#                 cast('False' as bit) 'vendor_wipro',
#                 cast('True' as bit) 'customer',
#                 cast('False' as bit) 'customer_wipro',
#                 cast('False' as bit) 'insurance',
#                 cast('False' as bit) 'patient',
#                 cast('True' as bit) 'doctor',
#                 cast('True' as bit) 'active'
#             FROM dbo.VRP_OdooAllDoctors a
#             WHERE LOWER(a.DoctorType) = 'internal'
#             ORDER BY a.DoctorType, a.DoctorID ASC """
#         if sync_date:
#             # query = query.replace("order by", "where a.MODDATE >= '{0}' order by".format(sync_date.date))
#             print (query)
#             sync_date.date = tools.datetime.now().strftime('%Y-%m-%d')
#         else:
#             self.env['sync.date'].sudo().create({
#                 'name':sync.getframe().f_code.co_name,
#                 'sync_type':sync_type
#             })
#         data = sync.get_data(sync.servers.get(sync_type), query)
#         if not data:
#             print ("No new data available")
#             return
#         fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and self._fields[key].required == True)
#         columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
#         fields_without_id += columns
#         fields = fields_without_id + ('id', )
#         if columns:
#             columns += ('id', )
#         default_values = {}
#         for field in fields:
#             if field in columns:
#                 continue
#             default = self._fields[field].default
#             if callable(default):
#                 default = default(self)
#             if isinstance(default, models.Model):
#                 default = default.id
#             default_values[field] = default
#         values = ''
#         now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
#         for object in data:
#             for value in default_values:
#                 object[value] = default_values[value]
#             if int(object['sync_id']) in sync_ids:
#                 object['id'] = sync_ids[object['sync_id']]
#             else:
#                 object['id'] = 'DEFAULT'
#             object['sync_date'] = now
#             object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].search([('sync_type', '=', sync_type)],limit=1).id
#             if values:
#                 values += ', '
#             value = False
#             for field in fields:
#                 if value:
#                     value += ', '
#                 else:
#                     value = '('
#                 if field == 'id' and object['id'] == 'DEFAULT':
#                     value += object['id']
#                     continue
#                 if type(object[field]) in [str, unicode]:
#                     string = object[field]
#                     value += "'" + string.replace("'", "''") + "'"
#                     continue
#                 value += sync.json(object[field])
#             value += ')'
#             values += value
#         excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
#         columns = sync.remove_unicode(str(fields)).replace("'", "")
#         columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
#         query = "INSERT into res_partner %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
#         print (query.encode('utf8'))
#         self.env.cr.execute(query)


#     @api.model
#     def _sync_doctor_external_wipro(self, sync_type='1'):
#         sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '!=',0), ('sync_id', '!=',False), ('doctor', '=', True), ('type_doctor', '=', 'external'), ('active', '=', True)])}
#         sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name),('sync_type', '=', sync_type)],limit=1)
#         query = """
#             SELECT 
#                 a.DoctorID 'sync_id', 
#                 a.DoctorCode 'doctor_code', 
#                 a.DoctorCode 'vendor_code', 
#                 a.DoctorName 'name', 
#                 a.DoctorName 'display_name', 
#                 isnull(a.Specialisation,'') as spec,
#                 a.DepartmentName 'department', 
#                 a.EmploymentType 'type_employment', 
#                 a.Designation 'designation', 
#                 a.HrProfile 'hrprofile', 
#                 LOWER(a.Gender) 'gender', 
#                 a.Phone 'phone', 
#                 a.Mobile 'mobile',
#                 a.Email 'email', 
#                 a.[Address] 'street',
#                 a.SpecialiseID 'specialise_id',
#                 (case when a.Blocked = 1 then 'TRUE' else 'FALSE' end ) as EmpBlocked, 
#                 LOWER(a.DoctorType) 'type_doctor', 
#                 cast(a.Blocked as bit) 'wipro_block',
#                 cast('False' as bit) 'supplier',
#                 cast('False' as bit) 'vendor_wipro',
#                 cast('True' as bit) 'customer',
#                 cast('False' as bit) 'customer_wipro',
#                 cast('False' as bit) 'insurance',
#                 cast('False' as bit) 'patient',
#                 cast('True' as bit) 'doctor',
#                 cast('True' as bit) 'active'
#             FROM dbo.VRP_OdooAllDoctors a
#             WHERE LOWER(a.DoctorType) = 'external'
#             ORDER BY a.DoctorType, a.DoctorID ASC """
#         if sync_date:
#             # query = query.replace("order by", "where a.MODDATE >= '{0}' order by".format(sync_date.date))
#             print (query)
#             sync_date.date = tools.datetime.now().strftime('%Y-%m-%d')
#         else:
#             self.env['sync.date'].sudo().create({
#                 'name':sync.getframe().f_code.co_name,
#                 'sync_type':sync_type
#             })
#         data = sync.get_data(sync.servers.get(sync_type), query)
#         if not data:
#             print ("No new data available")
#             return
#         fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and self._fields[key].required == True)
#         columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
#         fields_without_id += columns
#         fields = fields_without_id + ('id', )
#         if columns:
#             columns += ('id', )
#         default_values = {}
#         for field in fields:
#             if field in columns:
#                 continue
#             default = self._fields[field].default
#             if callable(default):
#                 default = default(self)
#             if isinstance(default, models.Model):
#                 default = default.id
#             default_values[field] = default
#         values = ''
#         now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
#         for object in data:
#             for value in default_values:
#                 object[value] = default_values[value]
#             if int(object['sync_id']) in sync_ids:
#                 object['id'] = sync_ids[object['sync_id']]
#             else:
#                 object['id'] = 'DEFAULT'
#             object['sync_date'] = now
#             object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].search([('sync_type', '=', sync_type)],limit=1).id
#             if values:
#                 values += ', '
#             value = False
#             for field in fields:
#                 if value:
#                     value += ', '
#                 else:
#                     value = '('
#                 if field == 'id' and object['id'] == 'DEFAULT':
#                     value += object['id']
#                     continue
#                 if type(object[field]) in [str, unicode]:
#                     string = object[field]
#                     value += "'" + string.replace("'", "''") + "'"
#                     continue
#                 value += sync.json(object[field])
#             value += ')'
#             values += value
#         excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
#         columns = sync.remove_unicode(str(fields)).replace("'", "")
#         columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
#         query = "INSERT into res_partner %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
#         print (query.encode('utf8'))
#         self.env.cr.execute(query)


#     @api.model
#     def _sync_patient_wipro(self, sync_type='1'):
#         self.env.cr.execute("SELECT cast(sync_id as integer) sync_id, id from res_partner where sync_type = '%s' and sync_id > 0 and patient = True and active = True" % (sync_type))
#         sync_ids = dict(self.env.cr.fetchall())
#         sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name), ('sync_type', '=', sync_type)], limit=1)
#         print (sync_date.date)
#         query = """
#             SELECT 
#                 a.sync_id
#                 ,a.registration_code
#                 ,a.registration_code vendor_code
#                 ,a.name
#                 ,a.display_name
#                 ,a.gender
#                 ,a.title_name
#                 ,a.patient_city
#                 ,a.patient_district 
#                 ,a.patient_subdistrict
#                 ,a.date_of_birth
#                 ,a.street
#                 ,a.street2
#                 ,a.street3
#                 ,a.zip
#                 ,a.phone
#                 ,a.mobile
#                 ,a.email
#                 ,a.contact_person
#                 ,a.passport
#                 ,a.ktp
#                 ,a.ModDate, a.wipro_block,
#                 cast('False' as bit) 'supplier',
#                 cast('False' as bit) 'vendor_wipro',
#                 cast('True' as bit) 'customer',
#                 cast('False' as bit) 'customer_wipro',
#                 cast('False' as bit) 'insurance',
#                 cast('True' as bit) 'patient',
#                 cast('False' as bit) 'doctor',
#                 cast('True' as bit) 'active'
#             FROM dbo.VRP_OdooPatients a
#             """
#         if sync_date:
            
#             query += """ 
#                 WHERE a.sync_id in ( 
#                     SELECT distinct t.PatientID 
#                     FROM dbo.A_A_RawDataH30 t 
#                     WHERE convert(varchar(10), t.tglproses, 121) >= '{0}' 
#                 ) or a.sync_id in (
#                     SELECT distinct t.PatientID
#                     FROM dbo.v_DBBills t
#                     WHERE t.BillDate >= dateadd(day, -10, '{1}')
#                 ) or convert(varchar(10), a.ModDate, 121) >= '{2}' 
#                 """.format(sync_date.date, sync_date.date, sync_date.date)
#                 # tools.datetime.strptime(sync_date.date,'%Y-%m-%d  %H:%M:%S').date(),
#                 # tools.datetime.strptime(sync_date.date,'%Y-%m-%d  %H:%M:%S').date())
#             print (query)
#             sync_date.date = tools.datetime.now().strftime('%Y-%m-%d')
            
#         else:
#             self.env['sync.date'].sudo().create({
#                 'name':sync.getframe().f_code.co_name,
#                 'sync_type':sync_type
#             })
#         data = sync.get_data(sync.servers.get(sync_type), query)
#         if not data:
#             print ("No new data available")
#             return
#         fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and self._fields[key].required == True and self._fields[key].store == True)
#         columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
#         fields_without_id += columns
#         columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
#         fields = fields_without_id + ('id', )
#         if columns:
#             columns += ('id', )
#         default_values = {}
#         for field in fields:
#             if field in columns:
#                 continue
#             default = self._fields[field].default
#             if callable(default):
#                 default = default(self)
#             if isinstance(default, models.Model):
#                 default = default.id
#             default_values[field] = default
#         values = ''
#         now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
#         dbname = self.env.cr.dbname
#         login = self.sudo().env.user.login
#         import odoorpc
#         request = odoorpc.ODOO('localhost', port=8085, timeout=100000000000)
#         request.login(dbname, login, 'mayapada@hospital2018')
#         env = request.env

#         def process_query(object, result):
#             for value in default_values:
#                 object[value] = default_values[value]
#             if int(object['sync_id']) in sync_ids:
#                 object['id'] = sync_ids[object['sync_id']]
#             else:
#                 object['id'] = 'DEFAULT'
#             object['sync_date'] = now
#             object['sync_type'], object['company_id'] = sync_type, env['res.company'].search([('sync_type', '=', sync_type)], limit=1)[0]
#             #if values:
#             #    values += ', '
#             value = False
#             for field in fields:
#                 if value:
#                     value += ', '
#                 else:
#                     value = '('
#                 if field == 'id' and object['id'] == 'DEFAULT':
#                     value += object['id']
#                     continue
#                 if type(object[field]) in [str, unicode]:
#                     string = object[field]
#                     value += "'" + string.replace("'", "''") + "'"
#                     continue
#                 value += sync.json(object[field])
#             value += ')'
#             result += [value]
#             #values += value

#         processes = []
#         result = list()
#         try:
#             result = Manager().list()
#         except:
#             pass
#         for chunk in sync.split_list(data, sync.cpu_count):
#             process = Process(
#                 target=lambda chunk, result:
#                 [process_query(object, result) for object in chunk],
#                 args=(chunk, result))
#             process.start()
#             processes += [process]
#         for process in processes:
#             process.join()
#         values = ', '.join(result)
#         excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
#         columns = sync.remove_unicode(str(fields)).replace("'", "")
#         columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
#         query = "INSERT into res_partner %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
#         print (query.encode('utf8'))
#         self.env.cr.execute(query)



#     @api.model
#     def _sync_patient_manual(self, sync_type='1'):
#         self.env.cr.execute("SELECT cast(sync_id as integer) sync_id, id from res_partner where sync_type = '%s' and sync_id > 0 and patient = True and active = True" % (sync_type))
#         sync_ids = dict(self.env.cr.fetchall())
#         sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name), ('sync_type', '=', sync_type)], limit=1)
#         print (sync_date.date)
#         query = """
#             SELECT 
#                 a.sync_id
#                 ,a.registration_code
#                 ,a.registration_code vendor_code
#                 ,a.name
#                 ,a.display_name
#                 ,a.gender
#                 ,a.title_name
#                 ,a.patient_city
#                 ,a.patient_district 
#                 ,a.patient_subdistrict
#                 ,a.date_of_birth
#                 ,a.street
#                 ,a.street2
#                 ,a.street3
#                 ,a.zip
#                 ,a.phone
#                 ,a.mobile
#                 ,a.email
#                 ,a.contact_person
#                 ,a.passport
#                 ,a.ktp
#                 ,a.ModDate, a.wipro_block,
#                 cast('False' as bit) 'supplier',
#                 cast('False' as bit) 'vendor_wipro',
#                 cast('True' as bit) 'customer',
#                 cast('False' as bit) 'customer_wipro',
#                 cast('False' as bit) 'insurance',
#                 cast('True' as bit) 'patient',
#                 cast('False' as bit) 'doctor',
#                 cast('True' as bit) 'active'
#             FROM dbo.VRP_OdooPatients a
#             where convert(varchar(10), a.moddate, 121) >= '2021-01-01'
#             """
        
#         data = sync.get_data(sync.servers.get(sync_type), query)
#         if not data:
#             print ("No new data available")
#             return
#         fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and self._fields[key].required == True and self._fields[key].store == True)
#         columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
#         fields_without_id += columns
#         columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
#         fields = fields_without_id + ('id', )
#         if columns:
#             columns += ('id', )
#         default_values = {}
#         for field in fields:
#             if field in columns:
#                 continue
#             default = self._fields[field].default
#             if callable(default):
#                 default = default(self)
#             if isinstance(default, models.Model):
#                 default = default.id
#             default_values[field] = default
#         values = ''
#         now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
#         dbname = self.env.cr.dbname
#         login = self.sudo().env.user.login
#         import odoorpc
#         request = odoorpc.ODOO('localhost', port=8085, timeout=100000000000)
#         request.login(dbname, login, 'mayapada@hospital2018')
#         env = request.env

#         def process_query(object, result):
#             for value in default_values:
#                 object[value] = default_values[value]
#             if int(object['sync_id']) in sync_ids:
#                 object['id'] = sync_ids[object['sync_id']]
#             else:
#                 object['id'] = 'DEFAULT'
#             object['sync_date'] = now
#             object['sync_type'], object['company_id'] = sync_type, env['res.company'].search([('sync_type', '=', sync_type)], limit=1)[0]
#             #if values:
#             #    values += ', '
#             value = False
#             for field in fields:
#                 if value:
#                     value += ', '
#                 else:
#                     value = '('
#                 if field == 'id' and object['id'] == 'DEFAULT':
#                     value += object['id']
#                     continue
#                 if type(object[field]) in [str, unicode]:
#                     string = object[field]
#                     value += "'" + string.replace("'", "''") + "'"
#                     continue
#                 value += sync.json(object[field])
#             value += ')'
#             result += [value]
#             #values += value

#         processes = []
#         result = list()
#         try:
#             result = Manager().list()
#         except:
#             pass
#         for chunk in sync.split_list(data, sync.cpu_count):
#             process = Process(
#                 target=lambda chunk, result:
#                 [process_query(object, result) for object in chunk],
#                 args=(chunk, result))
#             process.start()
#             processes += [process]
#         for process in processes:
#             process.join()
#         values = ', '.join(result)
#         excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
#         columns = sync.remove_unicode(str(fields)).replace("'", "")
#         columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
#         query = "INSERT into res_partner %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
#         print (query.encode('utf8'))
#         self.env.cr.execute(query)



class ResBank(models.Model):
    _inherit = 'res.bank'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")

    bank_charges = fields.Float(string="LLG", required=False)
    bank_charges2 = fields.Float(string="RTGS", required=False)

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'res.bank' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'res.bank'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        result = super(ResBank, self).create(vals)
        if result.trigger_create == False:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger create res bank")
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
            company = self.env['res.company'].search([('sync_consol_res_bank','=',True)])
            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_res_bank
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/create/res.bank"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/create/res.bank"
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
                    values['bank_charges'] = record.bank_charges
                    values['bic'] = record.bic
                    values['bank_charges2'] = record.bank_charges2
                    values['street'] = record.street
                    values['street2'] = record.street2
                    values['city'] = record.city
                    values['zip'] = record.zip
                    values['phone'] = record.phone
                    # values['fax'] = record.fax
                    values['email'] = record.email
                    values['active'] = record.active
                    values['trigger_create'] = True
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
                        # 'sync_consol_response': json_resp,
                        # 'sync_consol_response_status': api_status,
                        'sync_consol_date': now,
                        # 'sync_consol_sent' : data_sent,
                        'sync_consol_log': list_company
                    }
                    super(ResBank, self).write(data_update)

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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'res.bank' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'res.bank'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        result = super(ResBank, self).write(vals)
        if self.env.context.get('ganti_nama'): return result
        self = self.with_context(ganti_nama=True)
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "write res bank")
        # company = self.env['res.company'].search([('sync_consol_res_bank','=',True)])
        if self.trigger_write == True:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger write res bank")
            query = """
            UPDATE res_bank set trigger_write = false
            WHERE id = {self_id}""".format(self_id = self.id)
            self.env.cr.execute(query)
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
            company = self.env['res.company'].search([('sync_consol_res_bank','=',True)])
            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_res_bank
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/write/res.bank"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/write/res.bank"
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
                    values['bank_charges'] = record.bank_charges
                    values['bic'] = record.bic
                    values['bank_charges2'] = record.bank_charges2
                    values['street'] = record.street
                    values['street2'] = record.street2
                    values['city'] = record.city
                    values['zip'] = record.zip
                    values['phone'] = record.phone
                    # values['fax'] = record.fax
                    values['email'] = record.email
                    values['active'] = record.active
                    values['trigger_write'] = False
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
                        # 'sync_consol_response': json_resp,
                        # 'sync_consol_response_status': api_status,
                        'sync_consol_date': now,
                        # 'sync_consol_sent' : data_sent,
                        'sync_consol_log': list_company
                    }
                    super(ResBank, self).write(data_update)


    @api.onchange('sync_type', 'name','bank_charges','bic','bank_charges2','street','street2','city','zip','phone','fax','email','active')
    def onchange_trigger_write(self):
        self.trigger_write = True


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ResBank,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Bank" delete="0">
                    <sheet>
                        <group col="4">
                            <field name="name" on_change="1" modifiers="{&quot;required&quot;: true}"/>
                            <field name="bic" on_change="1"/>
                            <field name="bank_charges" on_change="1"/>
                            <field name="bank_charges2" on_change="1"/>
                        </group>
                        <group>
                            <group string="Address">
                                <label for="street" string="Address"/>
                                    <div class="o_address_format">
                                        <field name="street" placeholder="Street..." class="o_address_street" on_change="1"/>
                                        <field name="street2" placeholder="Street 2..." class="o_address_street" on_change="1"/>
                                        <field name="city" placeholder="City" class="o_address_city" on_change="1"/>
                                        <field name="state" class="o_address_state" placeholder="State" options="{&quot;no_open&quot;: True}" can_create="true" can_write="true"/>
                                        <field name="zip" placeholder="ZIP" class="o_address_zip" on_change="1"/>
                                        <field name="country" placeholder="Country" class="o_address_country" options="{&quot;no_open&quot;: True, &quot;no_create&quot;: True}" can_create="true" can_write="true"/>
                                    </div>
                            </group>
                            <group string="Communication">
                                <field name="phone" on_change="1"/>
                                <!--field name="fax" on_change="1"/-->
                                <field name="email" widget="email" on_change="1"/>
                                <field name="active" on_change="1"/>
                            </group>
                        </group>

                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="trigger_create" invisible="1" modifiers="{&quot;invisible&quot;: true}"/>
                                        <field name="trigger_write" invisible="1" modifiers="{&quot;invisible&quot;: true}"/>
                                        <field name="sync_type" readonly="1" on_change="1" modifiers="{&quot;readonly&quot;: true}"/>
                                        <field name="sync_consol_id_main" readonly="1" modifiers="{&quot;readonly&quot;: true}"/>
                                    </group>
                                    <group>
                                        <field name="sync_consol_id_unit" readonly="1" modifiers="{&quot;readonly&quot;: true}"/>
                                        <field name="sync_consol_date" readonly="1" modifiers="{&quot;readonly&quot;: true}"/>
                                    </group>
                                </group>
                            </page>
                        </notebook>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Banks" delete="0">
                    <field name="name" on_change="1" modifiers="{&quot;required&quot;: true}"/>
                    <field name="bic" on_change="1"/>
                    <field name="country" can_create="true" can_write="true"/>
                    <field name="sync_type" on_change="1"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res
        





        
class BankInformation(models.Model):
    _name = 'bank.information'

    @api.model
    def _get_default_company(self):
        return self.env.company.id 

    company_id = fields.Many2one('res.company', string="Company", default=_get_default_company)
    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")

    name = fields.Char(string="Name", compute='_compute_name')
    account_no = fields.Char(string="Account Number", required=True)
    beneficiary_name = fields.Char(string="Beneficiary Name", required=True)
    bank_name = fields.Many2one('res.bank', string="Bank Name", required=True)
    bank_branch = fields.Char(string="Bank Branch", required=False)
    bank_charges = fields.Float(string="LLG",required=False,related='bank_name.bank_charges',store=True)
    bank_charges2 = fields.Float(string="RTGS",required=False,related='bank_name.bank_charges2',store=True)
    bank_id = fields.Many2one('res.partner',string="Partner Information",ondelete='cascade')

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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'bank.information' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'bank.information'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        result = super(BankInformation, self).create(vals)
        if vals.get('company_id'):
            company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
            result.sync_type = company_id.sync_type
        if result.trigger_create == False:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger create bank information")
            result.send_api_consol_company()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " +str(result.id)

        open(log_file, 'a').write(message_log)
        return result

    # @api.multi
    def send_api_consol_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_bank_information
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/bank.information"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/bank.information"
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
                values['name'] = str(record.name)
                values['account_no'] = str(record.account_no)
                values['beneficiary_name'] = str(record.beneficiary_name)
                values['bank_branch'] = str(record.bank_branch)
                values['bank_charges'] = record.bank_charges
                values['bank_charges2'] = record.bank_charges2
                values['trigger_create'] = True

                if record.env.company.sync_consol_type =='main':
                    if record.bank_name.id == False:
                        values['bank_name'] = record.bank_name.id
                    else:
                        values['bank_name'] = str(record.bank_name.id)
                if record.env.company.sync_consol_type =='unit':
                    if record.bank_name.id == False:
                        values['bank_name'] = record.bank_name.sync_consol_id_main
                    else:
                        values['bank_name'] = str(int(record.bank_name.sync_consol_id_main))
                if record.bank_id.id == False:
                    values['bank_id'] = record.bank_id.id
                else:
                    values['bank_id'] = str(record.bank_id.id)

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
                


                lst.append(values)
                body['values'] = json.dumps(lst)
                # body['values'] = json.dumps(values)
                
                cookies = {'session_id': record.env.user.cookies}

                print('\n' + "body : " + str(body))
                print('\n' + "headers : " + str(headers))
                print('\n' + "url : " + str(url))
                # raise exceptions.ValidationError(_(str(body)))
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
                        # raise exceptions.ValidationError(_('Data Gagal Dibuat'))
                        raise exceptions.ValidationError(_(json_resp['message']))


                data_update = {
                    consol_id_to : response_id,
                    # 'sync_consol_response': json_resp,
                    # 'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    # 'sync_consol_sent' : data_sent
                }
                super(BankInformation, self).write(data_update)



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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'bank.information' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'bank.information'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        result = super(BankInformation, self).write(vals)
        if self.env.context.get('ganti_nama'): return result
        self = self.with_context(ganti_nama=True)
        # if self.company_id:
        #     self.sync_type = self.company_id.sync_type
        if self.trigger_write == True:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger write bank information")
            query = """
            UPDATE bank_information set trigger_write = false
            WHERE id = {self_id}""".format(self_id = self.id)
            self.env.cr.execute(query)
            self.send_api_consol_write_company()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Write before return" + "\n ID: " +str(self.id)

        open(log_file, 'a').write(message_log)
        return result



    # @api.multi
    def send_api_consol_write_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_bank_information
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/bank.information"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/bank.information"
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
                values['name'] = str(record.name)
                values['account_no'] = str(record.account_no)
                values['beneficiary_name'] = str(record.beneficiary_name)
                values['bank_branch'] = str(record.bank_branch)
                values['bank_charges'] = record.bank_charges
                values['bank_charges2'] = record.bank_charges2
                values['trigger_write'] = False
                if record.env.company.sync_consol_type =='main':
                    if record.bank_name.id == False:
                        values['bank_name'] = record.bank_name.id
                    else:
                        values['bank_name'] = str(record.bank_name.id)
                if record.env.company.sync_consol_type =='unit':
                    if record.bank_name.id == False:
                        values['bank_name'] = record.bank_name.sync_consol_id_main
                    else:
                        values['bank_name'] = str(int(record.bank_name.sync_consol_id_main))
                if record.bank_id.id == False:
                    values['bank_id'] = record.bank_id.id
                else:
                    values['bank_id'] = str(record.bank_id.id)
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

                # if record.company_id.id == False:
                #     values['company_id'] = record.company_id.id
                # else:
                #     values['company_id'] = str(record.company_id.id)

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
                super(BankInformation, self).write(data_update)


    @api.onchange('sync_type', 'name','account_no','beneficiary_name','bank_branch','bank_charges','bank_charges2','bank_name','bank_id')
    def onchange_trigger_write(self):
        self.trigger_write = True


    # @api.multi
    def _compute_name(self):
        for r in self:
            r.name = r.bank_name.name + "/" + r.account_no + "/" + r.beneficiary_name + "/"

    
    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(BankInformation,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Bank Information" delete="false">
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id"/>
                                <field name="bank_id" />
                                <field name="name" />
                                <field name="bank_branch" />
                            </group>
                            <group>
                                <field name="account_no"/>
                                <field name="beneficiary_name" />
                                <field name="bank_name" />
                                <field name="bank_charges" />
                                <field name="bank_charges2" />
                            </group>
                        </group>
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type"/>
                                        <field name="trigger_create"/>
                                        <field name="trigger_write"/>
                                    </group>
                                    <group>
                                        <field name="sync_consol_id_unit"/>
                                        <field name="sync_consol_id_main"/>
                                    </group>
                                </group>
                            </page>
                        </notebook>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Bank Information">
                    <field name="account_no"/>
                    <field name="beneficiary_name"/>
                    <field name="name"/>
                    <field name="bank_branch"/>
                    <field name="bank_charges"/>
                    <field name="bank_charges2"/>
                    <field name="company_id"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Bank Information..">
                    <field name="account_no"/>
                    <field name="beneficiary_name"/>
                    <field name="name"/>
                    <field name="bank_branch"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res





class DiscountAfterBills(models.Model):
    _name = 'discount.after.bills'

    @api.model
    def _get_default_company(self):
        return self.env.company.id 

    company_id = fields.Many2one('res.company', string="Company", default=_get_default_company)
    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    service_id = fields.Many2one('product.category', string="Category")
    # service_name = fields.Char(related='service_id.name', string="Category Name", store=True)
    product_id = fields.Many2one('product.product', string="Product")
    # product_name = fields.Char(related='product_id.product_tmpl_id.name', string="Product Name", store=True)
    # takeout = fields.Boolean(string="Takeout")
    # rate_percent = fields.Float(string="Rate Percent")
    remark = fields.Char(string="Remark")
    partner_id = fields.Many2one('res.partner',string="Bank Information",ondelete='cascade')



class ResPartnerAddress(models.Model):
    _name = 'res.partner.address'

    partner_id = fields.Many2one('res.partner', string="Partner")
    name = fields.Char(string="Title")
    pic = fields.Char(string="PIC")
    pic_division = fields.Char(string="PIC Division")
    address = fields.Char(string="Address")
    address2 = fields.Char(string="Address 2nd")
    phone = fields.Char(string="Phone")
    fax = fields.Char(string="Fax")
    email = fields.Char(string="Email")
    city = fields.Char(string="City")



