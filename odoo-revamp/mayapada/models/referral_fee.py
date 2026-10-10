import datetime
import calendar
from odoo import models, fields, api, tools, exceptions
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero, float_compare
from odoo.addons import decimal_precision as dp
import requests
import logging
import pytz
from xml.etree import ElementTree
# import urllib2
import urllib.request as urllib2
import xmltodict
from dateutil.relativedelta import relativedelta
from multiprocess import Process, Manager
import json
import base64
# load odoo library
from odoo.http import request
from . import sync



class ReferralAgen(models.Model):
    _name = 'referral.agen'

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    external_group_id = fields.Char(string="Referral Group Id")
    external_group_code = fields.Char(string="Referral Group Code")
    code = fields.Char(string="Referral Code", required=True)
    name = fields.Char(string="Referral Name", required=True)
    specialise_id = fields.Integer(string="Specialise Group ID")
    specialise_name = fields.Char(string="Specialise Group")
    doctor_id = fields.Many2one('account.analytic.account', string="Doctor Analytic", domain=[('sync_wipro_type','=','doctor_external')], required=False)
    spec_id = fields.Many2one('account.analytic.account', domain=[('sync_wipro_type','=','specialization')], string="Specialisation")
    spec_name = fields.Char(string="Specialisation Name")
    mobile = fields.Char(string="Mobile No.")
    email = fields.Char(string="Email")
    address = fields.Char(string="Address")
    date_of_birth = fields.Date(string="DOB")
    category_id = fields.Selection([('1', 'Referral Doctor (External)'), ('2', 'Rumah Sakit'), ('3', 'Klinik'), ('4', 'Puskesmas'), ('5', 'Agen Asuransi'), ('6', 'Corporate'), ('7', 'Agen Travel'), ('8', 'Agen Community'), ('9', 'Referral Doctor (Internal)'), ('10', 'Key Opinion Leader (KOL)')], string="Referral Category", required=False)
    gender = fields.Selection([('1', 'Male'), ('2', 'Female')], string="Gender", required=False)
    phone = fields.Char(string="Phone")
    no_ktp = fields.Char(string="No. KTP", required=True)
    no_rekening = fields.Char(string="No. Rekening")
    bank_name = fields.Char(string="Bank Name")
    bank_account_name = fields.Char(string="Bank Account Name")
    blocked = fields.Boolean(string="Blocked", default=False)
    institution_id = fields.Many2one('res.partner', string="Institution Name")
    agency_name = fields.Char(string="Agency Name")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralAgen,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Agen" delete="false">
                    <!--<header>
                        <button string="Sync" name="sync_referral_agen" type="object" class="oe_highlight"/>
                    </header>-->
                    <sheet>
                        <group>
                            <group>
                                <field name="sync_type" invisible="1" />
                                <field name="company_id" />
                                <field name="external_group_id" invisible="1" />
                                <field name="external_group_code" />
                                <field name="code" />
                                <field name="name" />
                                <field name="specialise_id" invisible="1" />
                                <field name="specialise_name" />
                                <field name="doctor_id" domain="[('sync_type','=',sync_type)]" />
                                <field name="spec_id" domain="[('sync_type','=',sync_type)]" />
                                <field name="mobile" />
                                <field name="email" />
                                <field name="address" />
                            </group>
                            <group>
                                <field name="date_of_birth" />
                                <field name="category_id" />
                                <field name="institution_id" />
                                <field name="agency_name" />
                                <field name="gender" />
                                <field name="phone" />
                                <field name="no_ktp" />
                                <field name="no_rekening" />
                                <field name="bank_name" />
                                <field name="bank_account_name" />
                                <field name="blocked" />
                            </group>
                        </group>    
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" />
                                        <field name="sync_id" readonly="1" />
                                        <field name="sync_id_api" readonly="1" />
                                        <field name="sync_date" readonly="1" />
                                    </group>
                                    <group>
                                        <field name="sync_consol_id_main" readonly="1" />
                                        <field name="sync_consol_id_unit" readonly="1" />
                                        <field name="sync_consol_date" readonly="1" />
                                    </group>
                                </group>
                            </page>
                        </notebook>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Referral Agen" delete="false">
                    <field name="code"/>
                    <field name="name"/>
                    <field name="doctor_id"/>
                    <field name="gender"/>
                    <field name="category_id"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Referral Agen Search">
                    <filter string="Referral Doctor (External)" domain="[('category_id','=', '1')]" />
                    <filter string="Rumah Sakit" domain="[('category_id','=', '2')]" />
                    <filter string="Klinik" domain="[('category_id','=', '3')]" />
                    <filter string="Puskesmas" domain="[('category_id','=', '4')]" />
                    <filter string="Agen Asuransi" domain="[('category_id','=', '5')]" />
                    <filter string="Corporate" domain="[('category_id','=', '6')]" />
                    <filter string="Agen Travel" domain="[('category_id','=', '7')]" />
                    <filter string="Agen Community" domain="[('category_id','=', '8')]" />
                    <filter string="Referral Doctor (Internal)" domain="[('category_id','=', '9')]" />
                    <filter string="Key Opinion Leader (KOL)" domain="[('category_id','=', '10')]" />
                    <separator/>
                    <field name="code"/>
                    <field name="name"/>
                    <field name="doctor_id"/>
                    <field name="spec_id"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    @api.onchange('company_id')
    def _sync_type(self):
        _sync_type = self.env['res.company'].search([('id', '=', self.company_id.id)], limit=1)
        self.sync_type = _sync_type.sync_type

    # @api.multi
    def sync_referral_agen(self, StartDate, EndDate):
        data_ref_agen = sync.get_data_master_referral_agen(self, StartDate, EndDate)
        sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_id', '>',0)])}
        record_partner = self.env['res.partner'].sudo()
        sync_partner_institution = self.env['res.partner'].sudo()
        record_account_analytic = self.env['account.analytic.account'].sudo()
        json_data = json.loads(data_ref_agen)
        
        if json_data['data']:
            for dt in json_data['data']:
                row = {}
                row['sync_type'] = dt['HospitalUnitId'] or 0
                row['company_id'] = self.env['res.company'].sudo().search([('sync_type', '=', dt['HospitalUnitId'])], limit=1).id or None
                row['external_group_id'] = dt['DoctorExternalId'] or 0
                row['external_group_code'] = dt['DoctorExternalCode']
                row['sync_id'] = float(dt['DoctorExternalUnitId']) or 0
                row['sync_id_api'] = float(dt['DoctorExternalUnitId']) or 0
                row['code'] = dt['DoctorExternalUnitCode'] or "-"
                row['name'] = (dt['DoctorExternalName'] or "-").upper()
                row['specialise_id'] = dt['SpecializationGroupId']
                row['specialise_name'] = (dt['SpecializationGroupName'] or "-").upper()

                sync_partner = self.env['res.partner'].search([('sync_type', '=', row['sync_type']), ('sync_id','=', row['sync_id_api'])], limit=1)
                sync_account_analytic = self.env['account.analytic.account'].sudo().search([('sync_type', '=', row['sync_type']), ('sync_id', '=', row['sync_id_api']), ('sync_wipro_type', '=', 'doctor_external')], limit=1)

                # Check res.partner
                if sync_partner['sync_id'] == row['sync_id_api']:
                    sync_partner['sync_id'] = row['sync_id_api']
                    sync_partner['sync_type'] = row['sync_type']
                    sync_partner['company_id'] = row['company_id']
                    sync_partner['doctor_code'] = row['code']
                    sync_partner['doctor'] = True
                    sync_partner['active'] = True
                    sync_partner['name'] = (row['name'] or "-").upper()
                else:
                    vals = {
                        'sync_id': row['sync_id_api'],
                        'sync_type': row['sync_type'],
                        'company_id': row['company_id'],
                        'doctor_code': row['code'],
                        'doctor': True,
                        'active': True,
                        'name': (row['name'] or "-").upper()
                    }
                    record_partner.sudo().create(vals)
                
                # Check res.partner.institution
                if sync_partner_institution['sync_id'] == dt['InstitutionId']:
                    sync_partner_institution['sync_id'] = dt['InstitutionId']
                    sync_partner_institution['sync_type'] = row['sync_type']
                    sync_partner_institution['company_id'] = row['company_id']
                    sync_partner_institution['name'] = (dt['InstitutionName'] or "-").upper()
                    row['institution_id'] = self.env['res.partner'].sudo().search([('sync_id', '=', dt['InstitutionId']), ('sync_type', '=', row['sync_type'])], limit=1).id or None
                
                elif dt['InstitutionId']:
                    vals = {
                        'sync_id': dt['InstitutionId'],
                        'sync_type': row['sync_type'],
                        'company_id': row['company_id'],
                        'name': (dt['InstitutionName'] or "-").upper()
                    }
                    record_partner.sudo().create(vals)
                    row['institution_id'] = self.env['res.partner'].sudo().search([('sync_id', '=', dt['InstitutionId']), ('sync_type', '=', row['sync_type'])], limit=1).id or None

                # Check account.analytic.account
                if sync_account_analytic['sync_id'] == row['sync_id_api']:
                    sync_account_analytic['sync_id'] = row['sync_id_api']
                    sync_account_analytic['sync_type'] = row['sync_type']
                    sync_account_analytic['partner_id'] = self.env['res.partner'].search([('sync_type', '=', row['sync_type']), ('sync_id','=', row['sync_id_api'])], limit=1).id or None
                    sync_account_analytic['code'] = row['code']
                    sync_account_analytic['name'] = (row['name'] or "-").upper()
                    sync_account_analytic['sync_wipro_type'] = 'doctor_external'
                else:
                    vals = {
                        'sync_id': row['sync_id_api'],
                        'sync_type': row['sync_type'],
                        'partner_id': self.env['res.partner'].search([('sync_type', '=', row['sync_type']), ('sync_id','=', row['sync_id_api'])], limit=1).id or None,
                        'code': row['code'],
                        'name': (row['name'] or "-").upper(),
                        'sync_wipro_type': 'doctor_external'
                    }
                    record_account_analytic.sudo().create(vals)

                row['doctor_id'] = self.env['account.analytic.account'].sudo().search([('sync_id', '=', dt['DoctorExternalUnitId']), ('sync_wipro_type', '=', 'doctor_external'), ('sync_type', '=', row['sync_type'])],limit=1).id or None
                row['spec_id'] = self.env['account.analytic.account'].sudo().search([('sync_id', '=', dt['SpecializationUnitId']), ('sync_wipro_type', '=', 'specialization'), ('sync_type', '=', row['sync_type'])],limit=1).id or None
                row['spec_name'] = (dt['SpecializationUnitName'] or "-").upper()
                row['mobile'] = dt['MobilePhone']
                row['email'] = dt['Email']
                row['address'] = dt['Address']
                row['date_of_birth'] = dt['DateOfBirth']
                row['category_id'] = dt['ReferralCategoryId'] or "-"
                row['gender'] = dt['GenderId']
                row['phone'] = dt['PhoneNumber']
                row['no_ktp'] = str(dt['NoKtp'] or "-")
                row['no_rekening'] = dt['NoRekening']
                row['bank_name'] = (dt['BankName'] or "-").upper()
                row['bank_account_name'] = (dt['BankAccountName'] or "-").upper()
                
                if int(row['sync_id']) in sync_ids:
                    self.sudo().browse(sync_ids[row['sync_id']]).write(row)
                else:
                    self.sudo().create(row)

    @api.model
    def _update_referral_agen(self, sync_type, sync_id_partner, code, sync_id_spec):
        # update doctor_id
        self.env.cr.execute("""
            UPDATE referral_agen SET 
                doctor_id = (
                    select id from account_analytic_account 
                    where sync_type = '{sync_type}' 
                    and sync_id_api='{sync_id_partner}'
                    and sync_wipro_type = 'doctor_external'),
                write_date = CURRENT_TIMESTAMP 
            WHERE code = '{code}' AND sync_type='{sync_type}'
        """.format(
            sync_type=sync_type,
            sync_id_partner=sync_id_partner,
            code=code))
        
        # update spec_id
        if sync_type in ['3','6']: # MHKN & MHSB
            self.env.cr.execute("""
                UPDATE referral_agen SET 
                    spec_id = (
                        select id from account_analytic_account 
                        where sync_type = '{sync_type}' 
                        and sync_id_api='{sync_id_spec}'
                        and sync_wipro_type = 'specialization'),
                    write_date = CURRENT_TIMESTAMP 
                WHERE code = '{code}' AND sync_type='{sync_type}'
            """.format(
                sync_type=sync_type,
                sync_id_spec=sync_id_spec,
                code=code))


class ReferralRate(models.Model):
    _name = 'referral.rate'
    _rec_name = 'external_id'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    referral_type = fields.Selection([('1','AGEN'),('2','CATEGORY')], string="Rate Type")
    external_id = fields.Many2one('referral.agen', string="Referral Agen")
    referral_category = fields.Selection([('1', 'Referral Doctor (External)'), ('2', 'Rumah Sakit'), ('3', 'Klinik'), ('4', 'Puskesmas'), ('5', 'Agen Asuransi'), ('6', 'Corporate'), ('7', 'Agen Travel'), ('8', 'Agen Community'), ('9', 'Referral Doctor (Internal)'), ('10', 'Key Opinion Leader (KOL)')], string="Referral Category", required=False)
    start_date_validity = fields.Date(string="Start Date Validity")
    end_date_validity = fields.Date(string="End Date Validity")
    rate_item_ids = fields.One2many('referral.rate.item','rate_id', string="Rate Items", copy=True)
    rate_service_ids = fields.One2many('referral.rate.service', 'rate_id', string="Rate Service", copy=True)
    rate_payer_ids = fields.One2many('referral.rate.payer', 'rate_id', string="Rate Payer", copy=True)
    rate_tariff_ids = fields.One2many('referral.rate.tariff', 'rate_id', string="Rate Tariff", copy=True)
    rate_bill_ids = fields.One2many('referral.rate.bill', 'rate_id', string="Rate Billing", copy=True)
    rate_visit_ids = fields.One2many('referral.rate.visit', 'rate_id', string="Rate Visit", copy=True)
    rate_payer_discount_ids = fields.One2many('referral.rate.payer.discount', 'rate_id', string="Rate Payer Discount", copy=True)

    @api.onchange('company_id')
    def _sync_type(self):
        _sync_type = self.env['res.company'].search([('id', '=', self.company_id.id)], limit=1)
        self.sync_type = _sync_type.sync_type
    
    @api.onchange('referral_type')
    def _ref_type(self):
        if self.referral_type == '2':
            self.external_id = None

    @api.onchange('external_id')
    def _ref_agen(self):
        self.referral_category = self.external_id.category_id

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralRate,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Referral Rate">
                    <field name="referral_type"/>
                    <field name="external_id"/>
                    <field name="referral_category"/>
                    <field name="start_date_validity"/>
                    <field name="end_date_validity"/>
                    <field name="company_id"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Referral Rate Search">
                    <filter string="Rate Agen" domain="[('referral_type','=', '1')]" />
                    <filter string="Rate Category" domain="[('referral_type','=', '2')]" />
                    <separator/>
                    <field name="external_id"/>
                    <field name="referral_category"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class ReferralRateItem(models.Model):
    _name = 'referral.rate.item'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    rate_id = fields.Many2one('referral.rate', string="Rate", ondelete='cascade')
    service_id = fields.Many2one('product.category', string="Category")
    product_id = fields.Many2one('product.product', string="Product")
    patient_type = fields.Selection([('1','OP'),('2','IP'),('3','Emergency'),('4','Daycare'),('5','MCU'),('6','Pharmacy')], string="Patient Type")
    rate_percent = fields.Float(string="Rate Percent")
    rate_value = fields.Float(string="Rate Value")
    takeout = fields.Boolean(string="Takeout")
    is_odc = fields.Boolean(string="Is_odc")
    remark = fields.Char(string="Remark")

    @api.onchange('service_id')
    def _domain_service(self):
        res = {}
        res['domain'] = {'service_id': [('sync_type', '=', self.rate_id.sync_type)]}
        return res

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralRateItem,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Rate Item">
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" readonly="1" />
                                <field name="rate_id" />
                                <field name="service_id" />
                                <field name="product_id"/>
                                <field name="patient_type" />
                            </group>
                            <group>
                                <field name="rate_percent" />
                                <field name="rate_value" />
                                <field name="takeout" />
                                <field name="is_odc" />
                                <field name="remark" />
                            </group>
                        </group>
                        <group>
                            <notebook>
                                <page string="Technical">
                                    <group>
                                        <group>
                                            <field name="sync_type" readonly="1" />
                                            <field name="sync_id" readonly="1" />
                                            <field name="sync_id_api" readonly="1" />
                                            <field name="sync_date" readonly="1" />
                                        </group>
                                        <group>
                                            <field name="sync_consol_id_main" readonly="1" />
                                            <field name="sync_consol_id_unit" readonly="1" />
                                            <field name="sync_consol_date" readonly="1" />
                                        </group>
                                    </group>
                                </page>
                            </notebook>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Referral Rate Item">
                    <field name="service_id"/>
                    <field name="product_id"/>
                    <field name="patient_type" />
                    <field name="rate_percent"/>
                    <field name="remark"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(self._name, doc, view_id)
        return res


class ReferralRateService(models.Model):
    _name = 'referral.rate.service'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    rate_id = fields.Many2one('referral.rate', string="Rate", ondelete='cascade')
    service_id = fields.Many2one('product.category', string="Category")
    takeout = fields.Boolean(string="Takeout")
    remark = fields.Char(string="Remark")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralRateService,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Rate Service">
                    <sheet>
                        <group>
                            <field name="company_id" />
                            <field name="rate_id" />
                            <field name="service_id" />
                            <field name="takeout" />
                            <field name="remark" />
                        </group>
                        <group>
                            <notebook>
                                <page string="Technical">
                                    <group>
                                        <group>
                                            <field name="sync_type" readonly="1" />
                                            <field name="sync_id" readonly="1" />
                                            <field name="sync_id_api" readonly="1" />
                                            <field name="sync_date" readonly="1" />
                                        </group>
                                        <group>
                                            <field name="sync_consol_id_main" readonly="1" />
                                            <field name="sync_consol_id_unit" readonly="1" />
                                            <field name="sync_consol_date" readonly="1" />
                                        </group>
                                    </group>
                                </page>
                            </notebook>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Referral Rate Tariff">
                    <field name="rate_id"/>
                    <field name="service_id" />
                    <field name="takeout"/>
                    <field name="remark"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(self._name, doc, view_id)
        return res


class ReferralRatePayer(models.Model):
    _name = 'referral.rate.payer'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    rate_id = fields.Many2one('referral.rate', string="Rate", ondelete='cascade')
    payer_id = fields.Many2one('res.partner', string="Payer", domain="[('customer_wipro','=',True)]", index=True, required=True)
    takeout = fields.Boolean(string="Takeout")
    remark = fields.Char(string="Remark")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralRatePayer,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Rate Payer">
                    <sheet>
                        <group>
                            <group>
                                <field name="rate_id" />
                                <field name="payer_id" />
                            </group>
                            <group>
                                <field name="takeout" />
                                <field name="remark" />
                            </group>
                        </group>
                        <group>
                            <notebook>
                                <page string="Technical">
                                    <group>
                                        <group>
                                            <field name="sync_type" readonly="1" />
                                            <field name="sync_id" readonly="1" />
                                            <field name="sync_id_api" readonly="1" />
                                            <field name="sync_date" readonly="1" />
                                        </group>
                                        <group>
                                            <field name="sync_consol_id_main" readonly="1" />
                                            <field name="sync_consol_id_unit" readonly="1" />
                                            <field name="sync_consol_date" readonly="1" />
                                        </group>
                                    </group>
                                </page>
                            </notebook>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Referral Rate Payer">
                    <field name="company_id"/>
                    <field name="rate_id"/>
                    <field name="payer_id" />
                    <field name="remark"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(self._name, doc, view_id)
        return res


class ReferralRateTariff(models.Model):
    _name = 'referral.rate.tariff'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    rate_id = fields.Many2one('referral.rate', string="Rate", ondelete='cascade')
    tariff_id = fields.Many2one('hospital.tariff', string="Tariff Name", required=True)
    takeout = fields.Boolean(string="Takeout")
    remark = fields.Char(string="Remark")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralRateTariff,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Rate Tariff">
                    <sheet>
                        <group>
                            <field name="company_id" />
                            <field name="rate_id" />
                            <field name="tariff_id" />
                            <field name="takeout" />
                            <field name="remark" />
                        </group>
                        <group>
                            <notebook>
                                <page string="Technical">
                                    <group>
                                        <group>
                                            <field name="sync_type" readonly="1" />
                                            <field name="sync_id" readonly="1" />
                                            <field name="sync_id_api" readonly="1" />
                                            <field name="sync_date" readonly="1" />
                                        </group>
                                        <group>
                                            <field name="sync_consol_id_main" readonly="1" />
                                            <field name="sync_consol_id_unit" readonly="1" />
                                            <field name="sync_consol_date" readonly="1" />
                                        </group>
                                    </group>
                                </page>
                            </notebook>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Referral Rate Tariff">
                    <field name="rate_id"/>
                    <field name="tariff_id" />
                    <field name="takeout"/>
                    <field name="remark"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(self._name, doc, view_id)
        return res


class ReferralRateBill(models.Model):
    _name = 'referral.rate.bill'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    rate_id = fields.Many2one('referral.rate', string="Rate", ondelete='cascade')
    patient_type = fields.Selection([('1','OP'),('2','IP'),('3','Emergency')], string="Patient Type")
    min_amount = fields.Float(string="Min Amount", required=True)
    max_amount = fields.Float(string="Max Amount", required=True)
    inc_fee_doctor = fields.Boolean(string="Inc FeeDoctor", default=False)
    rate_percent = fields.Float(string="Rate Percent")
    rate_value = fields.Float(string="Rate Amount")
    remark = fields.Char(string="Remark")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralRateBill,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Rate Item">
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" />
                                <field name="rate_id" />
                                <field name="patient_type" />
                                <field name="min_amount" />
                                <field name="max_amount" />
                            </group>
                            <group>
                                <field name="inc_fee_doctor" />
                                <field name="rate_percent" />
                                <field name="rate_value" />
                                <field name="remark" />
                            </group>
                        </group>
                        <group>
                            <notebook>
                                <page string="Technical">
                                    <group>
                                        <group>
                                            <field name="sync_type" readonly="1" />
                                            <field name="sync_id" readonly="1" />
                                            <field name="sync_id_api" readonly="1" />
                                            <field name="sync_date" readonly="1" />
                                        </group>
                                        <group>
                                            <field name="sync_consol_id_main" readonly="1" />
                                            <field name="sync_consol_id_unit" readonly="1" />
                                            <field name="sync_consol_date" readonly="1" />
                                        </group>
                                    </group>
                                </page>
                            </notebook>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Referral Rate Item">
                    <field name="rate_id"/>
                    <field name="patient_type" />
                    <field name="min_amount"/>
                    <field name="max_amount" />
                    <field name="rate_percent"/>
                    <field name="rate_value" />
                    <field name="remark"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(self._name, doc, view_id)
        return res


class ReferralRateVisit(models.Model):
    _name = 'referral.rate.visit'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    rate_id = fields.Many2one('referral.rate', string="Rate", ondelete='cascade')
    patient_type = fields.Selection([('1','OP'),('2','IP'),('3','Emergency'),('4','Daycare'),('5','MCU'),('6','Pharmacy')], string="Patient Type")
    min_visit = fields.Integer(string="Min", required=True)
    max_visit = fields.Integer(string="Max", required=True)
    rate_percent = fields.Float(string="Rate Percent")
    rate_value = fields.Float(string="Rate Amount")
    remark = fields.Char(string="Remark")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralRateVisit,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Rate Item">
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" />
                                <field name="rate_id" />
                                <field name="patient_type" />
                                <field name="min_visit" />
                                <field name="max_visit" />
                            </group>
                            <group>
                                <field name="rate_percent" />
                                <field name="rate_value" />
                                <field name="remark" />
                            </group>
                        </group>
                        <group>
                            <notebook>
                                <page string="Technical">
                                    <group>
                                        <group>
                                            <field name="sync_type" readonly="1" />
                                            <field name="sync_id" readonly="1" />
                                            <field name="sync_id_api" readonly="1" />
                                            <field name="sync_date" readonly="1" />
                                        </group>
                                        <group>
                                            <field name="sync_consol_id_main" readonly="1" />
                                            <field name="sync_consol_id_unit" readonly="1" />
                                            <field name="sync_consol_date" readonly="1" />
                                        </group>
                                    </group>
                                </page>
                            </notebook>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Referral Rate Item">
                    <field name="rate_id"/>
                    <field name="patient_type" />
                    <field name="min_visit"/>
                    <field name="max_visit" />
                    <field name="rate_percent"/>
                    <field name="rate_value" />
                    <field name="remark"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(self._name, doc, view_id)
        return res


class ReferralRatePayerDiscount(models.Model):
    _name = 'referral.rate.payer.discount'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    rate_id = fields.Many2one('referral.rate', string="Rate", ondelete='cascade')
    payer_id = fields.Many2one('res.partner', string="Payer", domain="[('customer_wipro','=',True)]", index=True, required=True)
    rate_percent = fields.Float(string="Rate Discount")
    takeout = fields.Boolean(string="Takeout")
    remark = fields.Char(string="Remark")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralRatePayerDiscount,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Rate Payer Discount">
                    <sheet>
                        <group>
                            <group>
                                <field name="rate_id" />
                                <field name="payer_id" />
                                <field name="remark" />
                            </group>
                            <group>
                                <field name="rate_percent" />
                                <field name="takeout" />
                            </group>
                        </group>
                        <group>
                            <notebook>
                                <page string="Technical">
                                    <group>
                                        <group>
                                            <field name="sync_type" readonly="1" />
                                            <field name="sync_id" readonly="1" />
                                            <field name="sync_id_api" readonly="1" />
                                            <field name="sync_date" readonly="1" />
                                        </group>
                                        <group>
                                            <field name="sync_consol_id_main" readonly="1" />
                                            <field name="sync_consol_id_unit" readonly="1" />
                                            <field name="sync_consol_date" readonly="1" />
                                        </group>
                                    </group>
                                </page>
                            </notebook>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Referral Rate Payer">
                    <field name="company_id"/>
                    <field name="rate_id"/>
                    <field name="payer_id" />
                    <field name="remark"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(self._name, doc, view_id)
        return res
    

class ReferralTransaction(models.Model):
    _name = 'referral.transaction'
    _rec_name = 'transaction_no'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    transaction_no = fields.Char(string="Transaction No.", required=True)
    transaction_date = fields.Date(string="Transaction Date", required=True)
    patient_name = fields.Char(string="Patient Name", required=True)
    date_of_birth = fields.Date(string="Date of Birth", required=True)
    gender = fields.Selection([('1', 'Male'), ('2', 'Female')], string="Gender", required=False)
    appointment_date = fields.Date(string="Appointment Date", required=True)
    mobile_phone = fields.Char(string="Mobile No.")
    email = fields.Char(string="Email")
    external_id = fields.Integer(string="External Referral ID", required=True)
    odoo_external_id = fields.Many2one('referral.agen', string="External Referral", required=True)
    external_name = fields.Char(string="External Referral Name", required=False)
    admission_id = fields.Integer(string="Admission Id", required=False)
    odoo_admission_id = fields.Many2one('sale.order', string="Admission")
    admission_no = fields.Char(string="Admission No.", required=True)
    bill_id = fields.Integer(string="Bill Id", required=False)
    odoo_bill_id = fields.Many2one('sale.order.bill', string="Billing", required=False)
    bill_no = fields.Char(string="Bill No.", required=False)
    bill_date = fields.Date(string="Bill Date", required=False)
    blocked = fields.Boolean(string="Blocked", default=False)
    is_merge_bill = fields.Boolean(string="Merge Billing", default=False)


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralTransaction,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Transaction Agen" delete="false">
                    <!--<header>
                        <button string="Sync" name="sync_transaksi_agen" type="object" class="oe_highlight"/>
                    </header>-->
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" />
                                <field name="transaction_no" />
                                <field name="transaction_date" />
                                <field name="patient_name" />
                                <field name="date_of_birth" />
                                <field name="gender" />
                                <field name="appointment_date" />
                                <field name="mobile_phone" />
                                <field name="email" />
                            </group>
                            <group>
                                <field name="sync_type"  invisible="1" />
                                <field name="external_id"  invisible="1" />
                                <field name="odoo_external_id" />
                                <field name="external_name" />
                                <field name="admission_id" invisible="1" />
                                <field name="odoo_admission_id" domain="[('sync_type','=',sync_type)]" />
                                <field name="admission_no" />
                                <field name="bill_id" invisible="1" />
                                <field name="odoo_bill_id" domain="[('sync_type','=',sync_type)]" />
                                <field name="bill_no" />
                                <field name="bill_date" />
                            </group>
                        </group>
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" />
                                        <field name="sync_id" readonly="1" />
                                        <field name="sync_id_api" readonly="1" />
                                        <field name="sync_date" readonly="1" />
                                    </group>
                                    <group>
                                        <field name="sync_consol_id_main" readonly="1" />
                                        <field name="sync_consol_id_unit" readonly="1" />
                                        <field name="sync_consol_date" readonly="1" />
                                        <field name="is_merge_bill" readonly="1" />
                                        <field name="blocked" readonly="1" />
                                    </group>
                                </group>
                            </page>
                        </notebook>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Referral Transaction" delete="false">
                    <field name="transaction_no"/>
                    <field name="transaction_date"/>
                    <field name="patient_name"/>
                    <field name="appointment_date"/>
                    <field name="external_name"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Referral Transaction Search">
                    <field name="transaction_no"/>
                    <field name="admission_no"/>
                    <field name="bill_no"/>
                    <field name="patient_name"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    @api.onchange('company_id')
    def _sync_type(self):
        _sync_type = self.env['res.company'].search([('id', '=', self.company_id.id)], limit=1)
        self.sync_type = _sync_type.sync_type

    # @api.multi
    def sync_transaksi_agen(self, StartDate, EndDate):
        data_tranc_agen = sync.get_data_master_transaksi_agen(self, StartDate, EndDate)     
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_id', '>',0)])}
        json_data = json.loads(data_tranc_agen)
        
        if json_data['data']:
            for dt in json_data['data']:
                row = {}
                row['sync_type'] = dt['HospitalUnitId'] or 0
                row['sync_id'] = float(dt['Id']) or 0
                row['company_id'] = self.env['res.company'].sudo().search([('sync_type', '=', dt['HospitalUnitId'])], limit=1).id or None
                row['transaction_no'] = dt['TransactionNo'] or "-"
                row['transaction_date'] = dt['TransactionDate']
                row['patient_name'] = (dt['PatientName'] or "-").upper()
                row['date_of_birth'] = dt['DateOfBirth']
                row['gender'] = dt['GenderId']
                row['appointment_date'] = dt['AppointmentDate']
                row['mobile_phone'] = dt['MobilePhone']
                row['email'] = dt['Email'].encode('utf-8')
                row['external_id'] = dt['DoctorExternalId'] or 0
                row['odoo_external_id'] = self.env['referral.agen'].sudo().search([('sync_id', '=', dt['DoctorExternalId']), ('sync_type', '=', row['sync_type'])],limit=1).id or None
                row['external_name'] = (dt['DoctorExternalName'] or "-").upper()
                row['odoo_admission_id'] = self.env['sale.order'].sudo().search([('sync_id', '=', dt['AdmissionId']), ('sync_type', '=', row['sync_type'])],limit=1).id or None
                row['admission_id'] = dt['AdmissionId'] or None
                row['admission_no'] = dt['AdmissionNo'] or "-"
                row['bill_id'] = dt['BillID'] or None
                row['odoo_bill_id'] = self.env['sale.order.bill'].sudo().search([('admission_id', '=', row['odoo_admission_id']), ('sync_type', '=', row['sync_type'])],limit=1).id or None
                row['bill_no'] = self.env['sale.order.bill'].sudo().search([('admission_id', '=', row['odoo_admission_id']), ('sync_type', '=', row['sync_type'])],limit=1).billno or None
                row['bill_date'] = self.env['sale.order.bill'].sudo().search([('admission_id', '=', row['odoo_admission_id']), ('sync_type', '=', row['sync_type'])],limit=1).confirmation_date or None
                row['sync_date'] = tools.datetime.now().strftime('%Y-%m-%d')
                # row['blocked'] = dt['Blocked']
                
                if int(row['sync_id']) in sync_ids:
                    self.sudo().browse(sync_ids[row['sync_id']]).write(row)
                else:
                    self.sudo().create(row)

    @api.model
    def create_ir_attachment(self, val, action):
        
        if action == 'insert':
            request.env['ir.attachment'].sudo().create({
                'sync_type': val['sync_type'],
                'name': val['filename'],
                'datas': val['image'],
                'datas_fname': val['filename'],
                'res_model': 'referral.transaction',
                'res_id': request.env['referral.transaction'].sudo().search([('transaction_no', '=', val['transaction_no'])], limit=1).id or None
            })
        elif action == 'update':
            reff_id = self.env['referral.transaction'].sudo().search([('transaction_no','=',val['transaction_no']), ('sync_type','=',val['sync_type'])], limit=1).id or None
            self.env['ir.attachment'].sudo().search([('res_model','=','referral.transaction'), ('res_id','=',reff_id), ('name','=',val['filename'])], limit=1).unlink()
            
            request.env['ir.attachment'].sudo().create({
                'sync_type': val['sync_type'],
                'name': val['filename'],
                'datas': val['image'],
                'datas_fname': val['filename'],
                'res_model': 'referral.transaction',
                'res_id': request.env['referral.transaction'].sudo().search([('transaction_no', '=', val['transaction_no'])], limit=1).id or None
            })
    
        return


class ReferralFee(models.Model):
    # _inherit = ['mail.thread', 'ir.needaction_mixin']
    _name = 'referral.fee'
    _rec_name = 'external_id'

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.company.id

    def _year(orm):
        result = []
        year = tools.datetime.now().year - 4
        now = tools.datetime.now().year
        for loop in range(now - year):
            value = str(year + loop + 1)
            result += [(value, value)]
        return result

    def _month(orm):
        result = []
        for loop in range(12):
            month = loop + 1
            result += [(str(month), calendar.month_name[month])]
        return result

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    external_id = fields.Many2one('referral.agen', string="Referral Doctor/Agen", required=True)
    category_id = fields.Selection(related="external_id.category_id", string="Referral Category", store=False)
    year = fields.Selection(_year, string="Year", required=True)
    month = fields.Selection(_month, string="Month", required=True)
    bruto = fields.Float(string="Bruto", required=True)
    fee = fields.Float(string="Fee", required=True)
    others = fields.Float(string="Others")
    total_fee = fields.Float(string="Total Fee", required=True)
    pph = fields.Float(string="PPH")
    total_pph21 = fields.Float(string="Total Pph21")
    deduction = fields.Float(string="Deduction")
    net_fee = fields.Float(string="Net Fee", required=True)
    state = fields.Selection([('draft','Draft'),('confirm','Confirmed'),('posted','Posted')], default='draft', string="State",  index=True, required=True, readonly=True, copy=False, tracking=True, store=True)
    journal_id = fields.Many2one('account.move', string="Journal Entries", readonly=True, tracking=True)
    
    fee_line_ids = fields.One2many('referral.fee.line','fee_id', string="Fee Line", copy=True)
    fee_other_ids = fields.One2many('referral.fee.other','fee_id', string="Fee Other", copy=True)
    fee_deduction_ids = fields.One2many('referral.fee.deduction','fee_id', string="Deduction", copy=True)
    
    api_confirm_status = fields.Selection([('pending','Pending'),('done','Done'),('failed','Failed')], default='pending', string="API Confirm Status")
    api_confirm_payload = fields.Char(string="API Confirm Payload")
    api_confirm_response = fields.Char(string="API Confirm Response")
    api_confirm_datetime = fields.Datetime(string="API Confirm Datetime")
    
    api_cancel_status = fields.Selection([('pending','Pending'),('done','Done'),('failed','Failed')], default='pending', string="API Cancel Status")
    api_cancel_payload = fields.Char(string="API Cancel Payload")
    api_cancel_response = fields.Char(string="API Cancel Response")
    api_cancel_datetime = fields.Datetime(string="API Cancel Datetime")

    @api.onchange('company_id')
    def _sync_type(self):
        _sync_type = self.env['res.company'].search([('id', '=', self.company_id.id)], limit=1)
        self.sync_type = _sync_type.sync_type

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralFee,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Referral Fee Worklist" delete="false">
                    <field name="year"/>
                    <field name="month"/>
                    <field name="external_id"/>
                    <field name="category_id"/>
                    <field name="bruto"/>
                    <field name="fee"/>
                    <field name="others"/>
                    <field name="net_fee"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <tree string="Referral Fee Worklist Search">
                    <filter string="Draft" domain="[('state','=', 'draft')]" />
                    <filter string="Confirmed" domain="[('state','=', 'confirm')]" />
                    <filter string="Posted" domain="[('state','=', 'posted')]" />
                    <separator/>
                    <field name="external_id"/>
                    <field name="year"/>
                    <field name="month"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # @api.multi
    def confirm(self):
        if self.fee_line_ids:
            for r in self.fee_line_ids:
                r.state = 'confirmed'
                if r.confirm_fee_date == False:
                    r.confirm_fee_date = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.action_confirm_api()

            for r1 in self.fee_other_ids:
                r1.state = 'confirmed'

            for r2 in self.fee_deduction_ids:
                r2.state = 'confirmed' 
        self.state = 'confirm'        

    # @api.multi
    # def post(self):
    #     if self:
    #         move = self.env['account.move'].search([('id','=', self.journal_id.id)])
            
    #         if move:
    #             move.post()
    #             self.state = 'posted'
                
    #             # update state referral.fee.line
    #             for r in self.fee_line_ids:
    #                 r.state = 'posted'
    #             for r1 in self.fee_other_ids:
    #                 r1.state = 'posted'
    #             for r2 in self.fee_deduction_ids:
    #                 r2.state = 'posted'
                
    # @api.multi
    def unpost(self):
        if self:
            move = self.env['account.move'].search([('id','=', self.journal_id.id)])
            
            if move:
                for line in move.line_ids:
                    line.write({'referral_id': None, 'reconciled':False, 'full_reconcile_id':False})
                
                move.button_cancel()
                move.unlink()
                self.state = 'confirm'
            
                for r in self.fee_line_ids:
                    r.state = 'confirmed'
                for r1 in self.fee_other_ids:
                    r1.state = 'confirmed'
                for r2 in self.fee_deduction_ids:
                    r2.state = 'confirmed' 
            
    # @api.multi
    def action_confirm_api(self):
        if self.company_id.api_backend_active == True and ((self.state == 'confirm' and self.api_confirm_status != 'done') or self.state == 'draft'):
            api_payload = self.generate_payload('confirm')
            api_endpoint = self.company_id.api_backend_endpoint + '/appointment/update_bill'
            # open('/opt/odoo16/logs/referral.log','a+').write('\n' + str(api_endpoint))
            api_headers = {'Content-Type': 'application/json', 'X-Behaviour':'blocking', 'Authorization': 'Basic ' + self.company_id.api_backend_key }               
            
            response_json = requests.post(url=api_endpoint, headers=api_headers, json=api_payload, verify=False)
            json_resp = response_json.json()
            # open('/opt/odoo16/logs/referral.log','a+').write('\n' + str(response_json))

            api_confirm_status = 'failed'
            if 'error' in json_resp:
                api_confirm_status = ('done' if json_resp['error'] == False else 'failed')
            now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            data = {'api_confirm_payload': api_payload, 'api_confirm_response': json_resp, 'api_confirm_datetime': now, 'api_confirm_status': api_confirm_status}
            write_result = super(ReferralFee, self).write(data)
    
    # @api.multi
    def cancel(self):
        self.state = 'draft'
        if self.fee_line_ids:
            
            for r in self.fee_line_ids:
                r.state = 'draft'
            self.action_cancel_api()

            for r1 in self.fee_other_ids:
                r1.state = 'draft'

            for r2 in self.fee_deduction_ids:
                r2.state = 'draft'    

    # @api.multi
    def action_cancel_api(self):
        if self.company_id.api_backend_active == True and self.state == 'draft':
            api_payload = self.generate_payload('cancel')
            api_endpoint = self.company_id.api_backend_endpoint + '/appointment/update_bill'
            api_headers = {'Content-Type': 'application/json', 'X-Behaviour':'blocking', 'Authorization': 'Basic ' + self.company_id.api_backend_key, }               
            
            response_json = requests.post(url=api_endpoint, headers=api_headers, json=api_payload, verify=False)
            json_resp = response_json.json()
            api_cancel_status = 'failed'
            if 'error' in json_resp:
                api_cancel_status = ('done' if json_resp['error'] == False else 'failed')
            now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            data = {'api_cancel_payload': api_payload, 'api_cancel_response': json_resp, 'api_cancel_datetime': now, 'api_cancel_status': api_cancel_status}
            write_result = super(ReferralFee, self).write(data)
    
    @api.model
    def generate_payload(self, action = 'confirm'):
        query = self.env.cr.execute("""
                select distinct
                    max(a.referral_number) referral_number,
                    a.admission_no, b.sync_id, a.admission_id, a.bill_no, 
                    a.odoo_admission_id, a.odoo_bill_id, a.bill_date,
                    a.confirm_fee_date confirmdocfeedate,
                    sum(a.fee_amount) total_fee,
                    max(a.nett_amount) total_bill
                from referral_fee_line a 
                inner join referral_transaction b 
                on TRIM(a.admission_no)=TRIM(b.admission_no) and a.sync_type=b.sync_type
                where a.fee_id = {fee_id} 
                group by a.admission_no, b.sync_id, a.admission_id, a.bill_no, a.confirm_fee_date,
                a.odoo_admission_id, a.odoo_bill_id, a.bill_date""".format(fee_id=self.id))
        admission_line_ids = self.env.cr.dictfetchall()
        
        payload = {}
        payload['Values'] = []
        # Grouping Admission
        for record in admission_line_ids:
            obj = {}
            obj["Id"] = record['sync_id']
            if str(action) == 'confirm':
                obj["Status"] = 7
                obj["ConfirmDocFeeDate"] = record['confirmdocfeedate']             
            elif str(action) == 'cancel':
                obj["Status"] = 12
                obj["ConfirmDocFeeDate"] = record['confirmdocfeedate']
            obj["TransactionNo"] = record['referral_number'] or ""
            obj["AdmissionId"] = record['admission_id']
            obj["BillDate"] = record['bill_date']
            obj["DoctorExternalId"] = self.external_id.sync_id
            obj["TotalNetDoctorFee"] = float((record['total_fee'] or 0.0) if action == 'confirm' else 0.0)
            obj["TotalNetBillOdoo"] = float(record['total_bill'])
            obj["BillNo"] = record['bill_no'] or "-"
            obj["Remarks"] = "Sync From Odoo"
            payload['Values'] += [obj] 

        # open('/opt/odoo16/logs/referral.log','a+').write('\n' + str(payload))
        return payload
    
    # @api.multi
    def compute(self):
        if self.state == 'draft':
            total_visit_ip = total_visit_op = total_visit_aae = 0
            total_bruto = total_fee = total_other = total_deduction = total_pph21 = 0

            # hitung total others
            for line_ot in self.fee_other_ids:
                total_other += line_ot['amount']
                total_bruto += line_ot['amount']
        
            # hitung total deduction 
            for line_ded in self.fee_deduction_ids:
                total_deduction += line_ded['amount']

            # hitung total_visit 
            for line_fee in self.fee_line_ids:
                if line_fee.fee_type == 'VISIT' and str(line_fee.patient_type) == '1':
                    total_visit_op += 1
                elif line_fee.fee_type == 'VISIT' and str(line_fee.patient_type) == '2':
                    total_visit_ip += 1
                elif line_fee.fee_type == 'VISIT' and str(line_fee.patient_type) == '3':
                    total_visit_aae += 1
            
            # ambil rate visit 
            rate = self.env['referral.rate'].search([('company_id', '=',self.company_id.id),('external_id', '=', self.external_id.id)], limit=1) 
            if not rate:
                rate = self.env['referral.rate'].search([('company_id', '=',self.company_id.id),('referral_category', '=', self.external_id.category_id), ('referral_type', '=', '2')], limit=1) 
            # cari rate visit opd 
            rate_visit_op = self.env['referral.rate.visit'].search([('rate_id','=', rate.id),('patient_type','=','1'),('min_visit','<=', total_visit_op), ('max_visit','>=', total_visit_op)], limit=1)
            # cari rate visit ipd 
            rate_visit_ip = self.env['referral.rate.visit'].search([('rate_id','=', rate.id),('patient_type','=','2'),('min_visit','<=', total_visit_ip), ('max_visit','>=', total_visit_ip)], limit=1)
            # cari rate visit aae
            rate_visit_aae = self.env['referral.rate.visit'].search([('rate_id','=', rate.id),('patient_type','=','3'),('min_visit','<=', total_visit_aae), ('max_visit','>=', total_visit_aae)], limit=1) 

            # update fee per visit pasien 
            for line_fee in self.fee_line_ids:

                # update visit OP
                if line_fee.fee_type == 'VISIT' and str(line_fee.patient_type) == '1':
                    if rate_visit_op:
                        line_fee.fee_rate = rate_visit_op.rate_percent
                        line_fee.fee_amount = rate_visit_op.rate_value
            
                # update visit IP
                elif line_fee.fee_type == 'VISIT' and str(line_fee.patient_type) == '2':
                    if rate_visit_ip:
                        line_fee.fee_rate = rate_visit_ip.rate_percent
                        line_fee.fee_amount = rate_visit_ip.rate_value

                # update visit AAE
                elif line_fee.fee_type == 'VISIT' and str(line_fee.patient_type) == '3':
                    if rate_visit_aae:
                        line_fee.fee_rate = rate_visit_aae.rate_percent
                        line_fee.fee_amount = rate_visit_aae.rate_value

            # hitung total fee  
            for line in self.fee_line_ids:
                total_fee += line.fee_amount   
                total_bruto += line.fee_amount 

            # update total per referral_agen 
            self.bruto = total_bruto
            self.fee = total_fee
            self.others = total_other
            self.deduction = total_deduction
            self.total_pph21 = 0 #sementara pph21 set NOL dulu  
            self.total_fee = total_fee + total_other
            self.net_fee = self.fee + self.others - self.total_pph21 - self.deduction


    # @api.multi
    def print_pdf(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/referral_fee/print_referral_fee?format=pdf&id=' + str(self.id)
        action['target'] = 'new'
        return action
    
    # @api.multi
    def print_xls(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/referral_fee/print_referral_fee?format=xls&id=' + str(self.id)
        action['target'] = 'new'
        return action
        

class ReferralFeeLine(models.Model):
    _name = 'referral.fee.line'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    fee_id = fields.Many2one('referral.fee', string="Fee ID", ondelete='cascade')
    fee_type = fields.Selection([('BILL','BILL'),('VISIT','VISIT'),('ITEM','ITEM')], string="Fee Type", required=True)
    odoo_bill_id = fields.Many2one('sale.order.bill', string="Billiing")
    bill_id = fields.Integer(string="Bill ID")
    bill_no = fields.Char(string="Bill No")
    bill_date = fields.Datetime(string="Bill Date")
    odoo_admission_id = fields.Many2one('sale.order', string="Admission")
    admission_no = fields.Char(string="Admission No.")
    admission_id = fields.Integer(string="Admission ID")
    admit_date = fields.Datetime(string="Admit Date")
    referral_number = fields.Char(string="Referral No.", required=True)
    is_merge_bill = fields.Boolean(string="Merge Billing", default=False)
    service_id = fields.Many2one('product.category', string="Service Category", required=False)
    product_id = fields.Many2one('product.product', string="Service Item", required=False)
    patient_type = fields.Selection([('1','OP'),('2','IP'),('3','Emergency'),('4','Daycare'),('5','MCU')], string="Patient Type", required=True)
    payer_id = fields.Many2one('res.partner', domain="[('customer_wipro','=',True)]", string="Payer", required=True)
    patient_id = fields.Many2one('res.partner', string="Patient")
    total_bill = fields.Float(string="Bill Amount")
    odoo_total_bill = fields.Float(string="Total Billing", related="odoo_bill_id.total_amount", store=False)
    total_feedoctor = fields.Float(string="Fee Doctor")
    nett_amount = fields.Float(string="Nett Amount")
    inc_fee_doctor = fields.Boolean(string="Inc FeeDoctor", default=False)
    fee_rate = fields.Float(string="Fee Rate")
    fee_amount = fields.Float(string="Fee Amount")
    state = fields.Selection([('draft','Draft'),('confirmed','Confirmed'),('posted','Posted')], default='draft', string="State")
    confirm_fee_date = fields.Datetime(string="Confirm Fee Date")

    @api.onchange('service_id')
    def _domain_service(self):
        res = {}
        res['domain'] = {'service_id': [('sync_type', '=', self.fee_id.sync_type)]}
        return res

    @api.onchange('odoo_admission_id')
    def _admission_no(self):
        self.admission_no = self.odoo_admission_id.name
        self.admit_date = self.odoo_admission_id.date_order
        self.nett_amount = self.odoo_admission_id.amount_total
    
    @api.onchange('odoo_bill_id')
    def _bill_no(self):
        self.bill_no = self.odoo_bill_id.billno
        self.bill_date = self.odoo_bill_id.confirmation_date
        self.total_bill = self.odoo_bill_id.total_amount
        
    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralFeeLine,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Rate Item">
                    <sheet>
                        <group>
                            <group string="General">
                                <field name="company_id" />
                                <field name="referral_number" />
                                <field name="is_merge_bill" />
                                <field name="patient_type" />
                                <field name="payer_id" />
                                <field name="service_id" />
                                <field name="product_id" />
                                <field name="state" />
                            </group>
                            <group string="Billing">
                                <field name="odoo_bill_id" />
                                <field name="bill_id" invisible="1" />
                                <field name="bill_no" />
                                <field name="bill_date" />
                                <field name="total_bill" />
                            </group>
                            <group string="Admission">
                                <field name="odoo_admission_id" />
                                <field name="admission_no" />
                                <field name="admission_id" invisible="1" />
                                <field name="patient_id" />
                                <field name="admit_date" />
                                <field name="nett_amount" />
                            </group>
                            <group string="Fee">
                                <field name="fee_id" />
                                <field name="fee_type" />
                                <field name="total_feedoctor" />
                                <field name="fee_rate" />
                                <field name="fee_amount" />
                                <field name="inc_fee_doctor" />
                            </group>
                        </group>
                    </sheet>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res



class ReferralFeeOther(models.Model):
    _name = 'referral.fee.other'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    fee_id = fields.Many2one('referral.fee', string="Fee ID", ondelete='cascade')
    item = fields.Char(string="Item")
    remark = fields.Char(string="Description")
    amount = fields.Float(string="Amount")
    state = fields.Selection([('draft','Draft'),('confirmed','Confirmed'),('posted','Posted')], default='draft', string="State")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralFeeOther,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Fee Other">
                    <sheet>
                        <group>
                            <field name="company_id" />
                            <field name="fee_id" />
                            <field name="item" />
                            <field name="remark" />
                            <field name="amount" />
                            <field name="state" />
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Referral Fee Other">
                    <field name="fee_id"/>
                    <field name="item"/>
                    <field name="remark" />
                    <field name="amount"/>
                    <field name="state"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

class ReferralFeeDeduction(models.Model):
    _name = 'referral.fee.deduction'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    fee_id = fields.Many2one('referral.fee', string="Fee ID", ondelete='cascade')
    item = fields.Char(string="Item")
    remark = fields.Char(string="Description")
    amount = fields.Float(string="Amount")
    state = fields.Selection([('draft','Draft'),('confirmed','Confirmed'),('posted','Posted')], default='draft', string="State")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralFeeDeduction,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Fee Deduction">
                    <sheet>
                        <group>
                            <field name="company_id" />
                            <field name="fee_id" />
                            <field name="item" />
                            <field name="remark" />
                            <field name="amount" />
                            <field name="state" />
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Referral Fee Deduction">
                    <field name="fee_id"/>
                    <field name="item"/>
                    <field name="remark" />
                    <field name="amount"/>
                    <field name="state"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res



class ReferralRemappingWizard(models.TransientModel):
    _name = 'referral.remapping.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    def _year(orm):
        result = []
        year = tools.datetime.now().year - 4
        now = tools.datetime.now().year
        for loop in range(now - year):
            value = str(year + loop + 1)
            result += [(value, value)]
        return result

    def _month(orm):
        result = []
        for loop in range(12):
            month = loop + 1
            result += [(str(month), calendar.month_name[month])]
        return result

    company_id = fields.Many2one('res.company', required=True, default=_get_company)
    year = fields.Selection(_year, string="Year")
    month = fields.Selection(_month, string="Month")
    remarks = fields.Html(string="Remarks", default="""Remapping transaksi billing analysis dengan data 
                                                    referral.transaksi berdasarkan tanggal billing""", readonly=True)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralRemappingWizard,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Doctor ReMapping">
                    <group>
                        <group>
                            <field name="company_id" string="Company ID" />
                            <field name="remarks" string="" />
                        </group>
                        <group>
                            <field name="year" string="Year" />
                            <field name="month" string="Month" /> 
                        </group>
                    </group>
                    <footer>
                        <button name="remapping" string="REMAPPING" type="object" class="oe_highlight"/>
                    </footer>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # @api.multi
    def remapping(self):
        month_period = str(self.month)
        year_period = str(self.year)
        company_id = str(self.company_id.id)

        query = """
            UPDATE sale_order_line AS a set 
                referral_id = c.id,
                referral_number = c.transaction_no,
                referral_doc_id = d.doctor_id
            FROM sale_order AS b
            INNER JOIN referral_transaction AS c ON trim(c.admission_no)=trim(b.name) and c.sync_type=b.sync_type
            INNER JOIN referral_agen AS d ON d.id=c.odoo_external_id 
            WHERE EXTRACT(YEAR FROM a.tglproses) = '{year}'
                and EXTRACT(MONTH FROM a.tglproses) = '{month}'
                and a.company_id = {company_id}
                and a.order_id = b.id 
                and c.blocked = '0'
                and (c.id, c.transaction_no, d.doctor_id) is null
        """.format(company_id=company_id, month=month_period, year=year_period)
        
        self.sudo().env.cr.execute(query)

        print("Re-Mapping Success!!!")


class ReferralComputeWizard(models.TransientModel):
    _name = 'referral.compute.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    def _year(orm):
        result = []
        year = tools.datetime.now().year - 4
        now = tools.datetime.now().year
        for loop in range(now - year):
            value = str(year + loop + 1)
            result += [(value, value)]
        return result

    def _month(orm):
        result = []
        for loop in range(12):
            month = loop + 1
            result += [(str(month), calendar.month_name[month])]
        return result
    
    company_id = fields.Many2one('res.company', required=True, default=_get_company)
    year = fields.Selection(_year, string="Year", required=True)
    month = fields.Selection(_month, string="Month", required=True)
    type = fields.Selection([('item', 'Fee Per Item'), ('bill', 'Fee Per Billing'), ('igd', 'Fee Per Billing IGD'), ('visit', 'Fee Per Visit'), ('kol', 'Fee Per KOL')], string="Type", required=True)
    remarks = fields.Html(string="Remarks", default="""Compute seluruh fee referral agen dalam satu periode tertentu.""", readonly=True)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralComputeWizard,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Compute Line">
                    <group>
                        <group>
                            <field name="company_id" string="Company ID" />
                            <field name="type" />
                            <field name="remarks" string="" />
                        </group>
                        <group>
                            <field name="year" string="Year" />
                            <field name="month" string="Month" /> 
                        </group>
                    </group>
                    <footer>
                        <button name="compute" string="COMPUTE LINE" type="object" class="oe_highlight"/>
                    </footer>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # @api.multi
    def compute(self):
        sudo = self.sudo()
        sync_type = self.company_id.sync_type
        month_period = str(self.month)
        year_period = str(self.year)
        company_id = str(self.company_id.id)

        # Get Rate Per Agen/Category
        query0 = """
            SELECT DISTINCT COALESCE(b.id, c.id) AS filter_rate_id
			FROM referral_agen a 
            LEFT JOIN referral_rate b on b.external_id = a.id and b.referral_type = '1' and a.sync_type=b.sync_type
            LEFT JOIN referral_rate c on c.referral_category = a.category_id and c.referral_type = '2' and a.sync_type=c.sync_type
            WHERE a.company_id = {company_id} and coalesce(b.id, c.id) is not null  
            """.format(company_id=company_id)
        query0 = sudo.env.cr.execute(query0)
        line_rates = sudo.env.cr.dictfetchall()

        if line_rates:
            for rates in line_rates:
                # Get doctor_id
                query01 = """
                    SELECT COALESCE(a.doctor_id, 0) doctor_id 
                    FROM referral_agen a 
                    LEFT JOIN referral_rate b on b.external_id = a.id and b.referral_type = '1' and a.sync_type=b.sync_type
                    LEFT JOIN referral_rate c on c.referral_category = a.category_id and c.referral_type = '2' and a.sync_type=c.sync_type
                    WHERE a.company_id = {company_id} and coalesce(b.id, c.id) is not null 
                    and COALESCE(b.id, c.id)={rate_id} 
                    """.format(company_id=company_id, rate_id=rates['filter_rate_id'])
                    
                query01 = sudo.env.cr.execute(query01)
                doctor_ids = sudo.env.cr.dictfetchall()
                
                param_doctor = []
                if len(doctor_ids) < 2:
                    param_doctor.append(0)

                for line in doctor_ids:
                    param_doctor.append(line['doctor_id'])
                
                #create if referral_fee not exists & get_id
                query1 = """
                    insert into referral_fee (
                    sync_type, company_id, year, month, external_id, 
                    bruto, fee, net_fee, total_fee, state)
                        select a.sync_type, a.company_id, '{year}', '{month}', a.id, 0, 0, 0, 0,'draft'
                        from referral_agen a 
                        where not exists(
                    select 1 
                    from referral_fee t where t.external_id = a.id
                    and t.sync_type = a.sync_type
                    and t.year = '{year}' 
                    and t.month = '{month}')""".format(year=year_period, month=month_period)
                                
                self.env.cr.execute(query1)
                
                if self.type == "kol":
                    # (2.1) PERHITUNGAN KOL
                    query_x1 = """
                        insert into referral_fee_line (
                            sync_type, company_id, fee_id, fee_type, referral_number,
                            odoo_bill_id, bill_no, bill_date, patient_type, odoo_admission_id, 
                            admission_no, admission_id, admit_date, payer_id, patient_id, 
                            service_id, product_id, total_bill, total_feedoctor, nett_amount, 
                            inc_fee_doctor, fee_rate, fee_amount, state )
                                                
                        select {sync_type} as sync_type, 
                            {company_id} as company_id, 
                            null as fee_id, ba.fee_type, ba.referral_number, ba.odoo_billing_id, 
                            ba.bill_no, ba.bill_date, ba.patient_type, ba.odoo_admission_id, 
                            ba.admission_no, ba.admission_id, ba.admit_date, ba.payer_id, 
                            ba.patient_id, ba.service_id, ba.product_id, ba.total_bill, 
                            ba.total_feedoctor, ba.nett_amount, ba.inc_fee_doctor, ba.rate_percent fee_rate, 
                            (case when coalesce(ba.rate_value, 0) > 0 then coalesce(ba.rate_value, 0)
                                else (coalesce(ba.rate_percent, 0) / 100 * ba.nett_amount) end) fee_amount, 
                            'draft' state
                        from (
                            select distinct 
                                'ITEM' fee_type,
                                COALESCE(a.referral_number,'-') referral_number,
                                MAX(a.billing_id) odoo_billing_id, 
                                MAX(a.billno) bill_no, 
                                MAX(b.confirmation_date) bill_date, 
                                MAX(a.patient_type) patient_type,
                                MAX(a.order_id) odoo_admission_id, 
                                MAX(b.name) admission_no,
                                MAX(b.sync_id) admission_id,
                                MAX(b.date_order) admit_date,
                                MAX(a.payer) payer_id,
                                MAX(a.partner_id) patient_id,
                                a.service_categ_id service_id,
                                a.product_id product_id,
                                SUM(a.price_subtotal) total_bill,
                                0 total_feedoctor,
                                --MAX(a.personal_amount) nett_amount,
                                --(MAX(a.payer_amount) + MAX(a.personal_amount)) nett_amount,
                                (CASE WHEN '{sync_type}' in ('3','6') THEN (
                                    select SUM(payer_amount) + SUM(personal_amount) nett_amount from sale_order_line 
                                    where is_package = TRUE and package_name=MAX(a.package_name) and order_id=MAX(a.order_id)) 
                                ELSE (MAX(a.payer_amount) + MAX(a.personal_amount)) END) nett_amount,
                                false inc_fee_doctor,
                                MAX(rri.rate_percent) rate_percent,
                                MAX(rri.rate_value) rate_value
                            from sale_order_line a 
                            inner join sale_order b on b.id=a.order_id
                            inner join res_partner py on py.id=a.payer 
                            inner join referral_rate_item rri 
                            inner join referral_rate rr2 on rri.rate_id=rr2.id
                                on rri.rate_id = {rate_id} 
                                and rri.product_id = a.product_id
                                and rri.takeout is not true 
                                and rri.patient_type = a.patient_type 
                            where a.company_id = {company_id}
                                and EXTRACT(YEAR FROM a.tglproses) = {year}
                                and EXTRACT(MONTH FROM a.tglproses) = {month}
                                {doctor_ids}
                                
                            -- filter transaksi yg udh billing aja
                            and a.type_line in ('BILL','BILLING','DISCOUNT')
                            
                            -- khusus KOL saja
                            and rr2.referral_category='10'
                                group by a.referral_number, a.service_categ_id, a.product_id
                            ) AS ba
                                                        
                            where not exists (
                                select t.id 
                                from referral_fee_line t 
                                inner join referral_fee rf on rf.id=t.fee_id 
                                where t.admission_no = ba.admission_no 
                                and rf.company_id = {company_id}
                            limit 1 )
                    """.format(company_id=company_id, year=year_period, 
                    month=month_period, sync_type=sync_type, rate_id=rates['filter_rate_id'], 
                    doctor_ids=("and a.referral_doc_id in " + str(tuple(param_doctor)) if param_doctor else "" ))
                    
                    self.env.cr.execute(query_x1)
                    open('/opt/odoo16/logs/referral.log','a+').write('\n' + str(query_x1))

                elif self.type == "item":
                    # (2.2) Hitung referral fee per tindakan (Penunjang)
                    query2 = """
                        insert into referral_fee_line (
                        sync_type, company_id, fee_id, fee_type, referral_number,
                        odoo_bill_id, bill_no, bill_date, patient_type,
                        odoo_admission_id, admission_no, admission_id, admit_date,
                        payer_id, patient_id, service_id, product_id, total_bill, 
                        total_feedoctor, nett_amount, inc_fee_doctor, fee_rate, fee_amount, state )
                    select 
                        {sync_type} as sync_type, 
                        {company_id} as company_id, 
                        null as fee_id, ba.fee_type, ba.referral_number,
                        ba.odoo_billing_id, ba.bill_no, ba.bill_date, ba.patient_type,
                        ba.odoo_admission_id, ba.admission_no, ba.admission_id, ba.admit_date,
                        ba.payer_id, ba.patient_id, ba.service_id, ba.product_id, 
                        ba.total_bill, ba.total_feedoctor, ba.nett_amount,
                        ba.inc_fee_doctor, ba.fee_rate, ba.fee_amount, 'draft' state
                    from (
                        
                        -- cari semua billing analysis yang sudah included/excluded mapping 
                        select 
                            'ITEM' fee_type,
                            a.referral_number,
                            a.billing_id odoo_billing_id, a.billno bill_no, 
                            b.confirmation_date bill_date, a.patient_type,
                            a.order_id odoo_admission_id, b.name admission_no,
                            b.sync_id admission_id,
                            b.date_order admit_date,
                            a.payer payer_id,
                            a.partner_id patient_id,
                            a.service_categ_id service_id,
                            a.product_id,
                            a.price_subtotal total_bill,
                            0 total_feedoctor,
                            a.price_subtotal nett_amount,
                            false inc_fee_doctor,
                            coalesce(rri.rate_value, rri.rate_percent) fee_rate,
                            (case when coalesce(rri.rate_value,0) > 0 then coalesce(rri.rate_value,0)
                                else (coalesce(rri.rate_percent,0) / 100 * a.price_subtotal) end) fee_amount
                        from sale_order_line a 
                        inner join sale_order b on b.id=a.order_id
                        inner join res_partner py on py.id=a.payer 
                        inner join referral_rate_item rri 
                            on rri.rate_id = {rate_id} 
                            and rri.product_id = a.product_id
                            and rri.takeout is not true 
                            and coalesce(rri.patient_type, a.patient_type) = a.patient_type 
                        where py.name not like '%BPJS%'
                            and a.company_id = {company_id}
                            and EXTRACT(YEAR FROM a.tglproses) = {year}
                            and EXTRACT(MONTH FROM a.tglproses) = {month}
                            {doctor_ids}
                                
                            -- filter transaksi yg udh billing aja
                            and a.type_line in ('BILL','BILLING','DISCOUNT')
                            -- exclude IPD and include day_care
                            and (a.patient_type <> '2' or (a.patient_type = '2' and COALESCE(a.is_daycare, False) = True))

                            -- filter takeout service global 
                            and COALESCE(a.service_categ_id, 0) not in( 
                                select service_id 
                                from referral_rate_item t 
                                where t.rate_id = {rate_id} 
                                    and t.service_id is not null 
                                    and t.product_id is null 
                                    and t.takeout=true )
                                
                            -- filter takeout service dg patient_type yg sesuai 
                            and COALESCE(a.service_categ_id, 0) not in( 
                                select service_id 
                                from referral_rate_item t 
                                where t.rate_id = {rate_id} 
                                    and t.service_id is not null 
                                    and t.product_id is null 
                                    and t.patient_type = a.patient_type
                                    and t.takeout=true )
                                
                            -- filter takeout service item global
                            and (
                            COALESCE(a.product_id, 0) not in ( 
                                select product_id 
                                from referral_rate_item t 
                                where t.rate_id = {rate_id} 
                                    and t.product_id is not null 
                                    and t.patient_type is null 
                                    and t.takeout=true )
                                    
                            -- filter takeout ODC/NON ODC
                            and COALESCE(a.product_id, 0) not in ( 
                                select distinct t.product_id from referral_rate_item t 
                                    where t.rate_id = {rate_id}
                                    and t.product_id is not null 
                                    and t.patient_type is null 
                                    and COALESCE(t.is_odc, False) <> COALESCE(a.is_daycare, False)
                                    and t.remark SIMILAR TO '%(Endoscopy|Colonoscopy)%' )
                                )
                                
                            -- filter takeout service item dg patient_type yg sesuai 
                            and COALESCE(a.product_id, 0) not in( 
                                select product_id 
                                from referral_rate_item t 
                                where t.rate_id = {rate_id} 
                                    and t.product_id is not null 
                                    and t.patient_type = a.patient_type 
                                    and t.takeout=true )
                                
                            --filter takeout payer 
                            and COALESCE(a.payer, 0) not in ( 
                                select payer_id 
                                from referral_rate_payer t 
                                where t.rate_id = {rate_id} 
                                    and t.takeout=true )
                                
                            --filter included payer, atau semua jika tidak ada mapping 
                            and (
                                COALESCE(a.payer, 0) in (
                                    select payer_id 
                                    from referral_rate_payer t 
                                    where t.rate_id = {rate_id} 
                                        and t.takeout is not true) 
                                or not exists(
                                    select payer_id 
                                    from referral_rate_payer t 
                                    where t.rate_id = {rate_id} 
                                        and t.takeout is not true limit 1)
                            )
                            
                            --filter takeout tariff 
                            and COALESCE(b.tariff_id, 0) not in ( 
                                select tariff_id 
                                from referral_rate_tariff t 
                                where t.rate_id = {rate_id} 
                                    and t.takeout=true )

                            --filter included tariff jika ada, atau semua tariff jika tidak ada mapping 
                            and (
                                COALESCE(b.tariff_id, 0) in (
                                    select tariff_id 
                                    from referral_rate_tariff t 
                                    where t.rate_id = {rate_id} 
                                        and t.takeout is not true) 
                                or not exists(
                                    select tariff_id 
                                    from referral_rate_tariff t 
                                    where t.rate_id = {rate_id} 
                                    and t.takeout is not true limit 1)
                            )
                        ) AS ba 

                    -- filter admission yang belum ada sebelumnya di referral.fee 
                    where not exists (
                        select t.id 
                        from referral_fee_line t 
                        inner join referral_fee rf on rf.id=t.fee_id 
                        where t.admission_no = ba.admission_no 
                            and rf.company_id = {company_id}
                        limit 1 )
                    """.format(company_id=company_id, year=year_period, 
                    month=month_period, sync_type=sync_type, rate_id=rates['filter_rate_id'], 
                    doctor_ids=("and a.referral_doc_id in " + str(tuple(param_doctor)) if param_doctor else "" ))
                    
                    self.env.cr.execute(query2)
                    open('/opt/odoo16/logs/referral.log','a+').write('\n' + str(query2))
                
                elif self.type == "bill":
                    # (2.3) Hitung referral fee per billing (IPD)
                    query3 = """
                        insert into referral_fee_line (
                        sync_type, company_id, fee_id, fee_type, referral_number,
                        odoo_bill_id, bill_no, bill_date, patient_type,
                        odoo_admission_id, admission_no, admission_id, admit_date,
                        payer_id, patient_id, total_bill, total_feedoctor, nett_amount,
                        inc_fee_doctor, fee_rate, fee_amount, state )
                    select 
                        {sync_type} as sync_type, 
                        {company_id} as company_id, 
                        null as fee_id, 
                        ba.fee_type, ba.referral_number, ba.odoo_billing_id, 
                        ba.bill_no, ba.bill_date, ba.patient_type,
                        ba.odoo_admission_id, ba.admission_no, ba.admission_id, ba.admit_date,
                        ba.payer_id, ba.patient_id, ba.total_bill, ba.total_feedoctor, 
                        --ba.nett_amount,
                        (case when coalesce(rrb.inc_fee_doctor, rrb2.inc_fee_doctor, false) = False then
                            (coalesce(ba.total_bill, 0) - coalesce(ba.total_discount, 0)) - coalesce(ba.total_feedoctor, 0)
                        else
                            coalesce(total_bill, 0) - coalesce(ba.total_discount, 0) end) nett_amount,
                        coalesce(rrb.inc_fee_doctor, rrb2.inc_fee_doctor, false) inc_fee_doctor,
                        coalesce(rrb.rate_percent, rrb2.rate_percent, 0) fee_rate,
                        (case 
                            --ambil dari rate_value 
                            when coalesce(rrb.rate_value, rrb2.rate_value, 0) > 0 
                                then coalesce(rrb.rate_value, rrb2.rate_value, 0)
                            --ambil dari rate_percent * total_bill
                            when coalesce(rrb.inc_fee_doctor, rrb2.inc_fee_doctor, false) = true 
                                then ( coalesce(rrb.rate_percent, rrb2.rate_percent, 0) * (ba.total_bill-ba.total_discount) / 100 )
                            --ambil dari rate_percent * nett_amount (exclude doctor_fee)
                            when coalesce(rrb.inc_fee_doctor, rrb2.inc_fee_doctor, false) = false 
                                then ( coalesce(rrb.rate_percent, rrb2.rate_percent, 0) * ba.nett_amount / 100 )
                            else 0 
                        end) fee_amount, 
                        'draft' state 
                    from (
                        select 
                            ba.fee_type, ba.referral_number, ba.odoo_billing_id, ba.bill_no,
                            ba.bill_date, ba.patient_type, ba.odoo_admission_id,
                            ba.admission_no, ba.admission_id, ba.admit_date, ba.payer_id,
                            ba.patient_id, ba.total_bill,
                            df3.total_billing * COALESCE(ba.rate_percent, 0) / 100 total_discount,
                            COALESCE(ba.rate_percent, 0) rate_percent,
                            (case when {sync_type} = '2' then df2.total_feedoctor_other else df.total_feedoctor end) total_feedoctor,
                            (case when (coalesce(ba.total_bill,0) - coalesce(
                                (case when {sync_type} = '2' then df2.total_feedoctor_other else df.total_feedoctor end),0)) < 0 then 0
                            else (coalesce(ba.total_bill,0) - coalesce(
                                (case when {sync_type} = '2' then df2.total_feedoctor_other else df.total_feedoctor end),0)) end) nett_amount
                        from (
                            -- cari semua billing analysis yang sudah included/excluded mapping 
                            -- group by billno 
                            select 
                                'BILL' fee_type,
                                a.order_id,
                                pd.rate_percent,
                                max(a.referral_number) referral_number,
                                max(a.billing_id) odoo_billing_id, a.billno bill_no, 
                                max(b.confirmation_date) bill_date, a.patient_type,
                                max(a.order_id) odoo_admission_id, max(b.name) admission_no,
                                max(b.sync_id) admission_id,
                                max(b.date_order) admit_date,
                                max(a.payer) payer_id,
                                max(a.partner_id) patient_id,
                                sum(a.price_subtotal) total_bill
                            from sale_order_line a 
                            inner join sale_order b on b.id=a.order_id
                            inner join sale_order_bill bl on a.billing_id=bl.id
                            inner join res_partner py on py.id=a.payer 
                            left join lateral (select pd.rate_percent from referral_rate_payer_discount pd where pd.payer_id=b.payer_id 
                                and pd.takeout = False and pd.rate_id=1 LIMIT 1) as pd ON 1=1 --get discount percent
                            left join referral_transaction rt on a.referral_id=rt.id
                            where py.name not like '%BPJS%'
                                and a.company_id = {company_id}
                                and EXTRACT(YEAR FROM a.tglproses) = {year}
                            and EXTRACT(MONTH FROM a.tglproses) = {month}
                                {doctor_ids}
                                
                                -- filter transaksi yg udh billing aja
                                and a.type_line in ('BILL','BILLING','DISCOUNT')
                                -- just include IPD and exclude day_care
                                and a.patient_type = '2'
                                and COALESCE(a.is_daycare, False) = False
                                and COALESCE(rt.is_merge_bill, False) = False
                                -- exclude cancel
                                and bl.state not in ('cancel')
                                
                                -- filter takeout service global 
                                and COALESCE(a.service_categ_id, 0) not in( 
                                    select service_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.service_id is not null 
                                        and t.product_id is null 
                                        and t.takeout=true )
                                
                                -- filter takeout service dg patient_type yg sesuai 
                                and COALESCE(a.service_categ_id, 0) not in( 
                                    select service_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.service_id is not null 
                                        and t.product_id is null 
                                        and t.patient_type = a.patient_type
                                        and t.takeout=true )
                                
                                -- filter takeout service item global
                                and COALESCE(a.product_id, 0) not in( 
                                    select product_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.product_id is not null 
                                        and t.patient_type is null 
                                        and t.takeout=true )
                                
                                -- filter takeout bill service
                                and COALESCE(a.product_id, 0) not in (select a.id from product_product a 
                                    left join product_template b ON a.product_tmpl_id=b.id 
                                    where b.categ_id in ( 
                                        select service_id from referral_rate_service t 
                                        where t.rate_id = {rate_id} and t.takeout=true))

                                --filter included bill service jika ada, atau semua bill service jika tidak ada mapping
                                and (
                                    COALESCE(a.product_id, 0) in (select a.id from product_product a 
                                        left join product_template b ON a.product_tmpl_id=b.id 
                                        where b.categ_id in (select service_id 
                                    from referral_rate_service t 
                                        where t.rate_id = {rate_id}  
                                        and t.takeout is not true) 
                                    or not exists(
                                        select service_id 
                                        from referral_rate_service t 
                                        where t.rate_id = {rate_id}  
                                        and t.takeout is not true limit 1)))

                                -- filter takeout service item dg patient_type yg sesuai 
                                and COALESCE(a.product_id, 0) not in( 
                                    select product_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.product_id is not null 
                                        and t.patient_type = a.patient_type 
                                        and t.takeout=true )
                                
                                --filter takeout payer 
                                and COALESCE(a.payer, 0) not in ( 
                                    select payer_id 
                                    from referral_rate_payer t 
                                    where t.rate_id = {rate_id} 
                                        and t.takeout=true )
                                
                                --filter included payer, atau semua jika tidak ada mapping 
                                and (
                                    COALESCE(a.payer, 0) in (
                                        select payer_id 
                                        from referral_rate_payer t 
                                        where t.rate_id = {rate_id} 
                                            and t.takeout is not true) 
                                    or not exists(
                                        select payer_id 
                                        from referral_rate_payer t 
                                        where t.rate_id = {rate_id} 
                                            and t.takeout is not true limit 1)
                                )
                            
                                --filter takeout tariff 
                                and COALESCE(b.tariff_id, 0) not in ( 
                                    select tariff_id 
                                    from referral_rate_tariff t 
                                    where t.rate_id = {rate_id} 
                                        and t.takeout=true )

                                --filter included tariff jika ada, atau semua tariff jika tidak ada mapping 
                                and (
                                    COALESCE(b.tariff_id, 0) in (
                                        select tariff_id 
                                        from referral_rate_tariff t 
                                        where t.rate_id = {rate_id} 
                                            and t.takeout is not true) 
                                    or not exists(
                                        select tariff_id 
                                        from referral_rate_tariff t 
                                        where t.rate_id = {rate_id} 
                                        and t.takeout is not true limit 1)
                                )
                            group by a.billno, a.patient_type, a.order_id, pd.rate_percent
                        ) AS ba   
                        
                        -- cari total doctor_fee  by admission_no yg sudah di confirm  
                        LEFT JOIN LATERAL (
                            select df.bill_no, 
                                sum(df.rate) total_feedoctor 
                            from doctor_fee_line df 
                            where df.admission_no = ba.admission_no
                                and df.bill_no = ba.bill_no
                                and df.company_id = {company_id} 
                                and df.state = 'confirmed'

                                -- filter takeout service global 
                                and COALESCE(df.odoo_service_id, 0) not in( 
                                    select service_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.service_id is not null 
                                        and t.product_id is null 
                                        and t.takeout=true )
                                
                                -- filter takeout service dg patient_type yg sesuai 
                                and COALESCE(df.odoo_service_id, 0) not in( 
                                    select service_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.service_id is not null 
                                        and t.product_id is null 
                                        and t.patient_type = df.patient_type
                                        and t.takeout=true )
                                
                                -- filter takeout service item global
                                and COALESCE(df.odoo_service_item_id, 0) not in( 
                                    select product_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.product_id is not null 
                                        and t.patient_type is null 
                                        and t.takeout=true )
                                
                                -- filter takeout service item dg patient_type yg sesuai 
                                and COALESCE(df.odoo_service_item_id, 0) not in( 
                                    select product_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.product_id is not null 
                                        and t.patient_type = df.patient_type 
                                        and t.takeout=true )
                            group by df.bill_no 

                        ) AS df ON 1=1 
                        -- end: doctor_fee per billing 

                        -- cari total doctor_fee_other_detail  by admission_no yg sudah di confirm  
                        LEFT JOIN LATERAL (
                            select df2.bill_no, 
                                sum(df2.rate) total_feedoctor_other 
                            from doctor_fee_others_detail df2 
                            where df2.admission_no = ba.admission_no
                                and df2.bill_no = ba.bill_no
                                and df2.company_id = {company_id} 
                                and df2.state = 'confirmed'

                            -- filter takeout service global 
                                and COALESCE(df2.odoo_service_id, 0) not in( 
                                    select service_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.service_id is not null 
                                        and t.product_id is null 
                                        and t.takeout=true )
                                
                            -- filter takeout service dg patient_type yg sesuai 
                            and COALESCE(df2.odoo_service_id, 0) not in( 
                                select service_id 
                                from referral_rate_item t 
                                where t.rate_id = {rate_id} 
                                    and t.service_id is not null 
                                    and t.product_id is null 
                                    and t.patient_type = df2.patient_type
                                    and t.takeout=true )
                            
                            -- filter takeout service item global
                            and COALESCE(df2.odoo_service_item_id, 0) not in( 
                                select product_id 
                                from referral_rate_item t 
                                where t.rate_id = {rate_id} 
                                    and t.product_id is not null 
                                    and t.patient_type is null 
                                    and t.takeout=true )
                            
                            -- filter takeout service item dg patient_type yg sesuai 
                            and COALESCE(df2.odoo_service_item_id, 0) not in( 
                                select product_id 
                                from referral_rate_item t 
                                where t.rate_id = {rate_id} 
                                    and t.product_id is not null 
                                    and t.patient_type = df2.patient_type 
                                    and t.takeout=true )

                            group by df2.bill_no 

                        ) AS df2 ON 1=1 

                        --Get Discount Percent By Payer
                        LEFT JOIN LATERAL 
                            (select sum(df3.price_subtotal) total_billing 
                            from sale_order_line df3 where df3.order_id=ba.order_id
                            
                        ) AS df3 ON 1=1
                        
                    ) AS ba 

                    -- cari rate bill dengan patient type yg sesuai 
                    inner join referral_rate_bill rrb 
                        on rrb.rate_id = {rate_id}
                        and rrb.patient_type = ba.patient_type
                        and rrb.min_amount <= (case when rrb.inc_fee_doctor=true then ba.total_bill else ba.nett_amount end)
                        and rrb.max_amount >= (case when rrb.inc_fee_doctor=true then ba.total_bill else ba.nett_amount end)

                    -- cari rate bill global 
                    left join referral_rate_bill rrb2 
                        on rrb2.rate_id = {rate_id}
                        and rrb2.patient_type is null 
                        and rrb2.min_amount <= (case when rrb2.inc_fee_doctor=true then ba.total_bill else ba.nett_amount end)
                        and rrb2.max_amount >= (case when rrb2.inc_fee_doctor=true then ba.total_bill else ba.nett_amount end)
                        
                    -- filter admission yang belum ada sebelumnya di referral.fee 
                    where not exists (
                        select t.id 
                        from referral_fee_line t 
                        inner join referral_fee rf on rf.id=t.fee_id 
                        where t.admission_no = ba.admission_no 
                            and rf.company_id = {company_id}
                        limit 1 )
                        """.format(company_id=company_id, year=year_period, month=month_period,
                        sync_type=sync_type, rate_id=rates['filter_rate_id'], 
                        doctor_ids=("and a.referral_doc_id in " + str(tuple(param_doctor)) if param_doctor else "" ))
                    
                    self.env.cr.execute(query3)
                    open('/opt/odoo16/logs/referral.log','a+').write('\n' + str(query3))

                elif self.type == "igd":
                    # (2.3.3) Hitung referral fee per billing / is_merge_billing = True
                    query_x3 = """
                    insert into referral_fee_line (
                        sync_type, company_id, fee_id, fee_type, referral_number,
                        odoo_bill_id, bill_no, bill_date, patient_type, is_merge_bill,
                        odoo_admission_id, admission_no, admission_id, admit_date,
                        payer_id, patient_id, total_bill, total_feedoctor, nett_amount,
                        inc_fee_doctor, fee_rate, fee_amount, state )
                    select 
                        {sync_type} as sync_type, 
                        {company_id} as company_id, 
                        null as fee_id, 
                        ba.fee_type, ba.referral_number, ba.odoo_billing_id, 
                        ba.bill_no, ba.bill_date, ba.patient_type, ba.is_merge_bill,
                        ba.odoo_admission_id, ba.admission_no, ba.admission_id, ba.admit_date,
                        ba.payer_id, ba.patient_id, ba.total_bill, ba.total_feedoctor, 
                        --ba.nett_amount,
                        (case when coalesce(rrb.inc_fee_doctor, rrb2.inc_fee_doctor, false) = False then
                            (coalesce(ba.total_bill, 0) - coalesce(ba.total_discount, 0)) - coalesce(ba.total_feedoctor, 0)
                        else
                            coalesce(total_bill, 0) - coalesce(ba.total_discount, 0) end) nett_amount,
                        coalesce(rrb.inc_fee_doctor, rrb2.inc_fee_doctor, false) inc_fee_doctor,
                        coalesce(rrb.rate_percent, rrb2.rate_percent, 0) fee_rate,
                        (case 
                            --ambil dari rate_value 
                            when coalesce(rrb.rate_value, rrb2.rate_value, 0) > 0 
                                then coalesce(rrb.rate_value, rrb2.rate_value, 0)
                            --ambil dari rate_percent * total_bill
                            when coalesce(rrb.inc_fee_doctor, rrb2.inc_fee_doctor, false) = true 
                                then ( coalesce(rrb.rate_percent, rrb2.rate_percent, 0) * (ba.total_bill-ba.total_discount) / 100 )
                            --ambil dari rate_percent * nett_amount (exclude doctor_fee)
                            when coalesce(rrb.inc_fee_doctor, rrb2.inc_fee_doctor, false) = false 
                                then ( coalesce(rrb.rate_percent, rrb2.rate_percent, 0) * ba.nett_amount / 100 )
                            else 0 
                        end) fee_amount, 
                        'draft' state 
                    from (
                        select 
                            ba.fee_type, ba.referral_number, ba.odoo_billing_id, ba.bill_no,
                            ba.bill_date, ba.patient_type, ba.odoo_admission_id, ba.is_merge_bill,
                            ba.admission_no, ba.admission_id, ba.admit_date, ba.payer_id,
                            ba.patient_id, ba.total_bill,
                            df3.total_billing * COALESCE(ba.rate_percent, 0) / 100 total_discount,
                            COALESCE(ba.rate_percent, 0) rate_percent,
                            (case when {sync_type} = '2' then df2.total_feedoctor_other else df.total_feedoctor end) total_feedoctor,
                            (case when (coalesce(ba.total_bill,0) - coalesce(
                                (case when {sync_type} = '2' then df2.total_feedoctor_other else df.total_feedoctor end),0)) < 0 then 0
                            else (coalesce(ba.total_bill,0) - coalesce(
                                (case when {sync_type} = '2' then df2.total_feedoctor_other else df.total_feedoctor end),0)) end) nett_amount
                        from (
                            -- cari semua billing analysis yang sudah included/excluded mapping 
                            -- group by billno 
                            select 
                                'BILL' fee_type,
                                a.order_id,
                                pd.rate_percent,
                                rt.is_merge_bill,
                                max(a.referral_number) referral_number,
                                max(a.billing_id) odoo_billing_id, a.billno bill_no, 
                                max(b.confirmation_date) bill_date, a.patient_type,
                                max(a.order_id) odoo_admission_id, max(b.name) admission_no,
                                max(b.sync_id) admission_id,
                                max(b.date_order) admit_date,
                                max(a.payer) payer_id,
                                max(a.partner_id) patient_id,
                                (sum(a.price_subtotal) + mrg.total_bill) total_bill
                            from sale_order_line a 
                            inner join sale_order b on b.id=a.order_id
                            inner join sale_order_bill bl on a.billing_id=bl.id
                            inner join res_partner py on py.id=a.payer 
                            left join lateral (select pd.rate_percent from referral_rate_payer_discount pd where pd.payer_id=b.payer_id 
                                and pd.takeout = False and pd.rate_id=1 LIMIT 1) as pd ON 1=1 --get discount percent
                            left join referral_transaction rt on a.referral_id=rt.id
                            -- merge igd
                            left join (select 
                                    'BILL' fee_type,
                                    a.order_id,
                                    pd.rate_percent,
                                    max(a.referral_number) referral_number,
                                    max(a.billing_id) odoo_billing_id, a.billno bill_no, 
                                    max(b.confirmation_date) bill_date, a.patient_type,
                                    max(a.order_id) odoo_admission_id, max(b.name) admission_no,
                                    max(b.sync_id) admission_id,
                                    max(b.date_order) admit_date,
                                    max(a.payer) payer_id,
                                    max(a.partner_id) patient_id,
                                    sum(a.price_subtotal) total_bill
                                from sale_order_line a 
                                inner join sale_order b on b.id=a.order_id
                                inner join sale_order_bill bl on a.billing_id=bl.id
                                inner join res_partner py on py.id=a.payer 
                                left join lateral (select pd.rate_percent from referral_rate_payer_discount pd where pd.payer_id=b.payer_id 
                                    and pd.takeout = False and pd.rate_id=1 LIMIT 1) as pd ON 1=1 --get discount percent
                                left join referral_transaction rt on a.referral_id=rt.id
                                where py.name not like '%BPJS%'
                                    and a.company_id = {company_id}
                                    and EXTRACT(YEAR FROM a.tglproses) = {year}
                                    --and EXTRACT(MONTH FROM a.tglproses) = {month} di comment karena bisa beda tgl igd & ipd
                                    {doctor_ids}
                                    
                                    -- filter transaksi yg udh billing aja
                                    and a.type_line in ('BILL','BILLING','DISCOUNT')
                                    -- just include IPD and exclude day_care
                                    and a.patient_type = '3'
                                    and COALESCE(a.is_daycare, False) = False
                                    and COALESCE(rt.is_merge_bill, False) = True
                                    -- exclude cancel
                                    and bl.state not in ('cancel')
                                    
                                    -- filter takeout service global 
                                    and COALESCE(a.service_categ_id, 0) not in( 
                                        select service_id 
                                        from referral_rate_item t 
                                        where t.rate_id = {rate_id} 
                                            and t.service_id is not null 
                                            and t.product_id is null 
                                            and t.takeout=true )
                                    
                                    -- filter takeout service dg patient_type yg sesuai 
                                    and COALESCE(a.service_categ_id, 0) not in( 
                                        select service_id 
                                        from referral_rate_item t 
                                        where t.rate_id = {rate_id} 
                                            and t.service_id is not null 
                                            and t.product_id is null 
                                            and t.patient_type = a.patient_type
                                            and t.takeout=true )
                                    
                                    -- filter takeout service item global
                                    and COALESCE(a.product_id, 0) not in( 
                                        select product_id 
                                        from referral_rate_item t 
                                        where t.rate_id = {rate_id} 
                                            and t.product_id is not null 
                                            and t.patient_type is null 
                                            and t.takeout=true )
                                    
                                    -- filter takeout bill service
                                    and COALESCE(a.product_id, 0) not in (select a.id from product_product a 
                                        left join product_template b ON a.product_tmpl_id=b.id 
                                        where b.categ_id in ( 
                                            select service_id from referral_rate_service t 
                                            where t.rate_id = {rate_id} and t.takeout=true))

                                    --filter included bill service jika ada, atau semua bill service jika tidak ada mapping
                                    and (
                                        COALESCE(a.product_id, 0) in (select a.id from product_product a 
                                            left join product_template b ON a.product_tmpl_id=b.id 
                                            where b.categ_id in (select service_id 
                                        from referral_rate_service t 
                                            where t.rate_id = {rate_id}  
                                            and t.takeout is not true) 
                                        or not exists(
                                            select service_id 
                                            from referral_rate_service t 
                                            where t.rate_id = {rate_id}  
                                            and t.takeout is not true limit 1)))

                                    -- filter takeout service item dg patient_type yg sesuai 
                                    and COALESCE(a.product_id, 0) not in( 
                                        select product_id 
                                        from referral_rate_item t 
                                        where t.rate_id = {rate_id} 
                                            and t.product_id is not null 
                                            and t.patient_type = a.patient_type 
                                            and t.takeout=true )
                                    
                                    --filter takeout payer 
                                    and COALESCE(a.payer, 0) not in ( 
                                        select payer_id 
                                        from referral_rate_payer t 
                                        where t.rate_id = {rate_id} 
                                            and t.takeout=true )
                                    
                                    --filter included payer, atau semua jika tidak ada mapping 
                                    and (
                                        COALESCE(a.payer, 0) in (
                                            select payer_id 
                                            from referral_rate_payer t 
                                            where t.rate_id = {rate_id} 
                                                and t.takeout is not true) 
                                        or not exists(
                                            select payer_id 
                                            from referral_rate_payer t 
                                            where t.rate_id = {rate_id} 
                                                and t.takeout is not true limit 1)
                                    )
                                
                                    --filter takeout tariff 
                                    and COALESCE(b.tariff_id, 0) not in ( 
                                        select tariff_id 
                                        from referral_rate_tariff t 
                                        where t.rate_id = {rate_id} 
                                            and t.takeout=true )

                                    --filter included tariff jika ada, atau semua tariff jika tidak ada mapping 
                                    and (
                                        COALESCE(b.tariff_id, 0) in (
                                            select tariff_id 
                                            from referral_rate_tariff t 
                                            where t.rate_id = {rate_id} 
                                                and t.takeout is not true) 
                                        or not exists(
                                            select tariff_id 
                                            from referral_rate_tariff t 
                                            where t.rate_id = {rate_id} 
                                            and t.takeout is not true limit 1)
                                    )
                                group by a.billno, a.patient_type, a.order_id, pd.rate_percent) mrg on TRIM(a.referral_number)=TRIM(mrg.referral_number)
                            -- exit merge igd
                            
                            where py.name not like '%BPJS%'
                                and a.company_id = {company_id}
                                and EXTRACT(YEAR FROM a.tglproses) = {year}
                            and EXTRACT(MONTH FROM a.tglproses) = {month}
                                {doctor_ids}
                                
                                -- filter transaksi yg udh billing aja
                                and a.type_line in ('BILL','BILLING','DISCOUNT')
                                -- just include IPD and exclude day_care
                                and a.patient_type = '2'
                                and COALESCE(a.is_daycare, False) = False
                                and COALESCE(rt.is_merge_bill, False) = True
                                -- exclude cancel
                                and bl.state not in ('cancel')
                                
                                -- filter takeout service global 
                                and COALESCE(a.service_categ_id, 0) not in( 
                                    select service_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.service_id is not null 
                                        and t.product_id is null 
                                        and t.takeout=true )
                                
                                -- filter takeout service dg patient_type yg sesuai 
                                and COALESCE(a.service_categ_id, 0) not in( 
                                    select service_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.service_id is not null 
                                        and t.product_id is null 
                                        and t.patient_type = a.patient_type
                                        and t.takeout=true )
                                
                                -- filter takeout service item global
                                and COALESCE(a.product_id, 0) not in( 
                                    select product_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.product_id is not null 
                                        and t.patient_type is null 
                                        and t.takeout=true )
                                
                                -- filter takeout bill service
                                and COALESCE(a.product_id, 0) not in (select a.id from product_product a 
                                    left join product_template b ON a.product_tmpl_id=b.id 
                                    where b.categ_id in ( 
                                        select service_id from referral_rate_service t 
                                        where t.rate_id = {rate_id} and t.takeout=true))

                                --filter included bill service jika ada, atau semua bill service jika tidak ada mapping
                                and (
                                    COALESCE(a.product_id, 0) in (select a.id from product_product a 
                                        left join product_template b ON a.product_tmpl_id=b.id 
                                        where b.categ_id in (select service_id 
                                    from referral_rate_service t 
                                        where t.rate_id = {rate_id}  
                                        and t.takeout is not true) 
                                    or not exists(
                                        select service_id 
                                        from referral_rate_service t 
                                        where t.rate_id = {rate_id}  
                                        and t.takeout is not true limit 1)))

                                -- filter takeout service item dg patient_type yg sesuai 
                                and COALESCE(a.product_id, 0) not in( 
                                    select product_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.product_id is not null 
                                        and t.patient_type = a.patient_type 
                                        and t.takeout=true )
                                
                                --filter takeout payer 
                                and COALESCE(a.payer, 0) not in ( 
                                    select payer_id 
                                    from referral_rate_payer t 
                                    where t.rate_id = {rate_id} 
                                        and t.takeout=true )
                                
                                --filter included payer, atau semua jika tidak ada mapping 
                                and (
                                    COALESCE(a.payer, 0) in (
                                        select payer_id 
                                        from referral_rate_payer t 
                                        where t.rate_id = {rate_id} 
                                            and t.takeout is not true) 
                                    or not exists(
                                        select payer_id 
                                        from referral_rate_payer t 
                                        where t.rate_id = {rate_id} 
                                            and t.takeout is not true limit 1)
                                )
                            
                                --filter takeout tariff 
                                and COALESCE(b.tariff_id, 0) not in ( 
                                    select tariff_id 
                                    from referral_rate_tariff t 
                                    where t.rate_id = {rate_id} 
                                        and t.takeout=true )

                                --filter included tariff jika ada, atau semua tariff jika tidak ada mapping 
                                and (
                                    COALESCE(b.tariff_id, 0) in (
                                        select tariff_id 
                                        from referral_rate_tariff t 
                                        where t.rate_id = {rate_id} 
                                            and t.takeout is not true) 
                                    or not exists(
                                        select tariff_id 
                                        from referral_rate_tariff t 
                                        where t.rate_id = {rate_id} 
                                        and t.takeout is not true limit 1)
                                )
                            group by a.billno, a.patient_type, a.order_id, pd.rate_percent, mrg.total_bill, rt.is_merge_bill
                        ) AS ba   
                        
                        -- cari total doctor_fee  by admission_no yg sudah di confirm  
                        LEFT JOIN LATERAL (
                            select df.bill_no, 
                                sum(df.rate) total_feedoctor 
                            from doctor_fee_line df 
                            where df.admission_no = ba.admission_no
                                and df.bill_no = ba.bill_no
                                and df.company_id = {company_id} 
                                and df.state = 'confirmed'

                                -- filter takeout service global 
                                and COALESCE(df.odoo_service_id, 0) not in( 
                                    select service_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.service_id is not null 
                                        and t.product_id is null 
                                        and t.takeout=true )
                                
                                -- filter takeout service dg patient_type yg sesuai 
                                and COALESCE(df.odoo_service_id, 0) not in( 
                                    select service_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.service_id is not null 
                                        and t.product_id is null 
                                        and t.patient_type = df.patient_type
                                        and t.takeout=true )
                                
                                -- filter takeout service item global
                                and COALESCE(df.odoo_service_item_id, 0) not in( 
                                    select product_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.product_id is not null 
                                        and t.patient_type is null 
                                        and t.takeout=true )
                                
                                -- filter takeout service item dg patient_type yg sesuai 
                                and COALESCE(df.odoo_service_item_id, 0) not in( 
                                    select product_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.product_id is not null 
                                        and t.patient_type = df.patient_type 
                                        and t.takeout=true )
                            group by df.bill_no 

                        ) AS df ON 1=1 
                        -- end: doctor_fee per billing 

                        -- cari total doctor_fee_other_detail  by admission_no yg sudah di confirm  
                        LEFT JOIN LATERAL (
                            select df2.bill_no, 
                                sum(df2.rate) total_feedoctor_other 
                            from doctor_fee_others_detail df2 
                            where df2.admission_no = ba.admission_no
                                and df2.bill_no = ba.bill_no
                                and df2.company_id = {company_id} 
                                and df2.state = 'confirmed'

                            -- filter takeout service global 
                                and COALESCE(df2.odoo_service_id, 0) not in( 
                                    select service_id 
                                    from referral_rate_item t 
                                    where t.rate_id = {rate_id} 
                                        and t.service_id is not null 
                                        and t.product_id is null 
                                        and t.takeout=true )
                                
                            -- filter takeout service dg patient_type yg sesuai 
                            and COALESCE(df2.odoo_service_id, 0) not in( 
                                select service_id 
                                from referral_rate_item t 
                                where t.rate_id = {rate_id} 
                                    and t.service_id is not null 
                                    and t.product_id is null 
                                    and t.patient_type = df2.patient_type
                                    and t.takeout=true )
                            
                            -- filter takeout service item global
                            and COALESCE(df2.odoo_service_item_id, 0) not in( 
                                select product_id 
                                from referral_rate_item t 
                                where t.rate_id = {rate_id} 
                                    and t.product_id is not null 
                                    and t.patient_type is null 
                                    and t.takeout=true )
                            
                            -- filter takeout service item dg patient_type yg sesuai 
                            and COALESCE(df2.odoo_service_item_id, 0) not in( 
                                select product_id 
                                from referral_rate_item t 
                                where t.rate_id = {rate_id} 
                                    and t.product_id is not null 
                                    and t.patient_type = df2.patient_type 
                                    and t.takeout=true )

                            group by df2.bill_no 

                        ) AS df2 ON 1=1 

                        --Get Discount Percent By Payer
                        LEFT JOIN LATERAL 
                            (select sum(df3.price_subtotal) total_billing 
                            from sale_order_line df3 where df3.order_id=ba.order_id
                            
                        ) AS df3 ON 1=1
                        
                    ) AS ba 

                    -- cari rate bill dengan patient type yg sesuai 
                    inner join referral_rate_bill rrb 
                        on rrb.rate_id = {rate_id}
                        and rrb.patient_type = ba.patient_type
                        and rrb.min_amount <= (case when rrb.inc_fee_doctor=true then ba.total_bill else ba.nett_amount end)
                        and rrb.max_amount >= (case when rrb.inc_fee_doctor=true then ba.total_bill else ba.nett_amount end)

                    -- cari rate bill global 
                    left join referral_rate_bill rrb2 
                        on rrb2.rate_id = {rate_id}
                        and rrb2.patient_type is null 
                        and rrb2.min_amount <= (case when rrb2.inc_fee_doctor=true then ba.total_bill else ba.nett_amount end)
                        and rrb2.max_amount >= (case when rrb2.inc_fee_doctor=true then ba.total_bill else ba.nett_amount end)
                        
                    -- filter admission yang belum ada sebelumnya di referral.fee 
                    where not exists (
                        select t.id 
                        from referral_fee_line t 
                        inner join referral_fee rf on rf.id=t.fee_id 
                        where t.admission_no = ba.admission_no 
                            and rf.company_id = {company_id}
                        limit 1 )
                        """.format(company_id=company_id, year=year_period, month=month_period,
                        sync_type=sync_type, rate_id=rates['filter_rate_id'], 
                        doctor_ids=("and a.referral_doc_id in " + str(tuple(param_doctor)) if param_doctor else "" ))
                    
                    self.env.cr.execute(query_x3)
                    open('/opt/odoo16/logs/referral.log','a+').write('\n' + str(query_x3))
                
                elif self.type == "visit":
                    # (2.4) Hitung referral fee per visit private(OPD)
                    query4 = """
                        insert into referral_fee_line (
                        sync_type, company_id, fee_id, fee_type, referral_number,
                        odoo_bill_id, bill_no, bill_date, patient_type,
                        odoo_admission_id, admission_no, admission_id, admit_date,
                        payer_id, patient_id, total_bill, total_feedoctor, nett_amount,
                        inc_fee_doctor, fee_rate, fee_amount, state )
                    select 
                        {sync_type} as sync_type, 
                        {company_id} as company_id, 
                        null as fee_id, ba.fee_type, ba.referral_number,
                        ba.odoo_billing_id, ba.bill_no, ba.bill_date, ba.patient_type,
                        ba.odoo_admission_id, ba.admission_no, ba.admission_id, ba.admit_date,
                        ba.payer_id, ba.patient_id, ba.total_bill, ba.total_feedoctor, ba.nett_amount,
                        ba.inc_fee_doctor, ba.fee_rate, ba.fee_amount, 'draft' state
                    from (
                        
                        -- cari semua billing analysis yang sudah included/excluded mapping 
                        -- group by billno 
                        select 
                            'VISIT' fee_type,
                            max(a.referral_number) referral_number,
                            max(a.billing_id) odoo_billing_id, max(a.billno) bill_no, 
                            max(b.confirmation_date) bill_date, max(a.patient_type) patient_type,
                            a.order_id odoo_admission_id, max(b.name) admission_no,
                            max(b.sync_id) admission_id,
                            max(b.date_order) admit_date,
                            max(a.payer) payer_id,
                            max(a.partner_id) patient_id,
                            0 total_bill,
                            0 total_feedoctor,
                            0 nett_amount,
                            false inc_fee_doctor,
                            0 fee_rate,
                            0 fee_amount
                        from sale_order_line a 
                        inner join sale_order b on b.id=a.order_id
                        inner join res_partner py on py.id=a.payer 
                        where py.name not like '%BPJS%'
                            and py.customer_type_wipro like '%PRIVATE%'
                            and a.company_id = {company_id}
                            and EXTRACT(YEAR FROM a.tglproses) = {year}
                            and EXTRACT(MONTH FROM a.tglproses) = {month}
                            {doctor_ids}
                                
                            -- filter transaksi yg udh billing aja
                            and a.type_line in ('BILL','BILLING','DISCOUNT')
                                
                            --filter visit patient_type 
                            and a.patient_type in(
                                select a.patient_type
                                from referral_rate_visit t 
                                where t.rate_id = {rate_id} 
                                    and t.patient_type = a.patient_type
                            )
                                
                            -- yg mendapat visit fee jika ada service "consultation"
                            and COALESCE(a.service_categ_id, 0) in ( 
                                select pc.id from product_category pc
                                where pc.name like '%Consultation%' 
                                and pc.sync_type='{sync_type}')
                            --filter takeout payer 
                            and COALESCE(a.payer, 0) not in ( 
                                select payer_id 
                                from referral_rate_payer t 
                                where t.rate_id = {rate_id} 
                                    and t.takeout=true )
                                
                            --filter included payer, atau semua jika tidak ada mapping 
                            and (
                                COALESCE(a.payer, 0) in (
                                    select payer_id 
                                    from referral_rate_payer t 
                                    where t.rate_id = {rate_id} 
                                        and t.takeout is not true) 
                                or not exists(
                                    select payer_id 
                                    from referral_rate_payer t 
                                    where t.rate_id = {rate_id} 
                                        and t.takeout is not true limit 1)
                            )
                            
                            --filter takeout tariff 
                            and COALESCE(b.tariff_id, 0) not in ( 
                                select tariff_id 
                                from referral_rate_tariff t 
                                where t.rate_id = {rate_id} 
                                    and t.takeout=true )

                            --filter included tariff jika ada, atau semua tariff jika tidak ada mapping 
                            and (
                                COALESCE(b.tariff_id, 0) in (
                                    select tariff_id 
                                    from referral_rate_tariff t 
                                    where t.rate_id = {rate_id} 
                                        and t.takeout is not true) 
                                or not exists(
                                    select tariff_id 
                                    from referral_rate_tariff t 
                                    where t.rate_id = {rate_id} 
                                    and t.takeout is not true limit 1)
                            )
                        group by a.order_id 
                    ) AS ba 

                    -- filter admission yang belum ada sebelumnya di referral.fee 
                    where not exists (
                        select t.id 
                        from referral_fee_line t 
                        inner join referral_fee rf on rf.id=t.fee_id 
                        where t.admission_no = ba.admission_no 
                            and rf.company_id = {company_id}
                        limit 1 )
                    """.format(company_id=company_id, year=year_period, month=month_period,
                    sync_type=sync_type, rate_id=rates['filter_rate_id'], 
                    doctor_ids=("and a.referral_doc_id in " + str(tuple(param_doctor)) if param_doctor else "" ))
                    
                    self.env.cr.execute(query4)
                    open('/opt/odoo16/logs/referral.log','a+').write('\n' + str(query4))
                    
            print("Compute Success!!!")
        else:
            print("Record Rate Not Found!!!")   

        # update fee_id in referral_fee_line
        query_x4 = """
            UPDATE referral_fee_line AS fl set fee_id=fe.id 
                from referral_transaction tr
                left join referral_agen ag on tr.odoo_external_id=ag.id
                left join account_analytic_account ac on ag.doctor_id=ac.id
                left join referral_fee fe on ag.id=fe.external_id
            where TRIM(fl.referral_number)=TRIM(tr.transaction_no) 
                and fl.fee_id is null and fe.year='{year}' and fe.month='{month}' 
                and fl.company_id={company_id}
            """.format(company_id=company_id, year=year_period, month=month_period)
                        
        self.env.cr.execute(query_x4)



class ReferralFeeComputeWizard(models.TransientModel):
    _name = 'referral.fee.compute.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    def _year(orm):
        result = []
        year = tools.datetime.now().year - 4
        now = tools.datetime.now().year
        for loop in range(now - year):
            value = str(year + loop + 1)
            result += [(value, value)]
        return result

    def _month(orm):
        result = []
        for loop in range(12):
            month = loop + 1
            result += [(str(month), calendar.month_name[month])]
        return result
    
    company_id = fields.Many2one('res.company', required=True, default=_get_company)
    year = fields.Selection(_year, string="Year", required=True)
    month = fields.Selection(_month, string="Month", required=True)
    remarks = fields.Html(string="Remarks", default="""Compute referral fee setelah menjalankan compute line""", readonly=True)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralFeeComputeWizard,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Compute Fee">
                    <group>
                        <field name="company_id" string="Company ID" />
                        <field name="year" string="Year" />
                        <field name="month" string="Month" />
                        <field name="remarks" string="" /> 
                    </group>
                    <footer>
                        <button name="compute_fee" string="COMPUTE FEE" type="object" class="oe_highlight"/>
                    </footer>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # @api.multi
    def compute_fee(self):
        # Auto Compute
        data_ref = self.env['referral.fee'].search([('year','=', self.year),('month','=',self.month),('company_id','=',self.company_id.id)])
        for referral_fee in data_ref:
            self = referral_fee
            
            if self.state == 'draft':
                total_visit_ip = total_visit_op = total_visit_aae = 0
                total_bruto = total_fee = total_other = total_deduction = total_pph21 = 0

                # hitung total others
                for line_ot in self.fee_other_ids:
                    total_other += line_ot['amount']
                    total_bruto += line_ot['amount']
            
                # hitung total deduction 
                for line_ded in self.fee_deduction_ids:
                    total_deduction += line_ded['amount']

                # hitung total_visit 
                for line_fee in self.fee_line_ids:
                    if line_fee.fee_type == 'VISIT' and str(line_fee.patient_type) == '1':
                        total_visit_op += 1
                    elif line_fee.fee_type == 'VISIT' and str(line_fee.patient_type) == '2':
                        total_visit_ip += 1
                    elif line_fee.fee_type == 'VISIT' and str(line_fee.patient_type) == '3':
                        total_visit_aae += 1
                
                # ambil rate visit 
                rate = self.env['referral.rate'].search([('company_id', '=',self.company_id.id),('external_id', '=', self.external_id.id)], limit=1) 
                if not rate:
                    rate = self.env['referral.rate'].search([('company_id', '=',self.company_id.id),('referral_category', '=', self.external_id.category_id), ('referral_type', '=', '2')], limit=1) 
                # cari rate visit opd 
                rate_visit_op = self.env['referral.rate.visit'].search([('rate_id','=', rate.id),('patient_type','=','1'),('min_visit','<=', total_visit_op), ('max_visit','>=', total_visit_op)], limit=1)
                # cari rate visit ipd 
                rate_visit_ip = self.env['referral.rate.visit'].search([('rate_id','=', rate.id),('patient_type','=','2'),('min_visit','<=', total_visit_ip), ('max_visit','>=', total_visit_ip)], limit=1)
                # cari rate visit aae
                rate_visit_aae = self.env['referral.rate.visit'].search([('rate_id','=', rate.id),('patient_type','=','3'),('min_visit','<=', total_visit_aae), ('max_visit','>=', total_visit_aae)], limit=1) 

                # update fee per visit pasien 
                for line_fee in self.fee_line_ids:

                    # update visit OP
                    if line_fee.fee_type == 'VISIT' and str(line_fee.patient_type) == '1':
                        if rate_visit_op:
                            line_fee.fee_rate = rate_visit_op.rate_percent
                            line_fee.fee_amount = rate_visit_op.rate_value
                
                    # update visit IP
                    elif line_fee.fee_type == 'VISIT' and str(line_fee.patient_type) == '2':
                        if rate_visit_ip:
                            line_fee.fee_rate = rate_visit_ip.rate_percent
                            line_fee.fee_amount = rate_visit_ip.rate_value

                    # update visit AAE
                    elif line_fee.fee_type == 'VISIT' and str(line_fee.patient_type) == '3':
                        if rate_visit_aae:
                            line_fee.fee_rate = rate_visit_aae.rate_percent
                            line_fee.fee_amount = rate_visit_aae.rate_value

                # hitung total fee  
                for line in self.fee_line_ids:
                    total_fee += line.fee_amount   
                    total_bruto += line.fee_amount 

                # update total per referral_agen 
                self.bruto = total_bruto
                self.fee = total_fee
                self.others = total_other
                self.deduction = total_deduction
                self.total_pph21 = 0 #sementara pph21 set NOL dulu  
                self.total_fee = total_fee + total_other
                self.net_fee = self.fee + self.others - self.total_pph21 - self.deduction



class ReferralFeeReportWizard(models.TransientModel):
    _name = 'referral.fee.report.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    def _year(orm):
        result = []
        year = tools.datetime.now().year - 4
        now = tools.datetime.now().year
        for loop in range(now - year):
            value = str(year + loop + 1)
            result += [(value, value)]
        return result

    def _month(orm):
        result = []
        for loop in range(12):
            month = loop + 1
            result += [(str(month), calendar.month_name[month])]
        return result
    
    company_id = fields.Many2one('res.company', required=True, default=_get_company)
    year = fields.Selection(_year, string="Year", required=True)
    month = fields.Selection(_month, string="Month", required=True)
    external_id = fields.Many2one('referral.agen', domain="[('company_id','=',company_id)]", string="Referral Agen")
    # terms_period = fields.Selection([('15','15 Days'),('31','30 Month')], string="Terms", required=True)
    # category_id = fields.Selection([('1', 'Dokter'), ('2', 'Rumah Sakit'), ('3', 'Klinik'), ('4', 'Puskesmas'), ('5', 'Agen Asuransi'), ('6', 'Corporate'), ('7', 'Agen Travel')], string="Referral Category", required=False)
    type_report = fields.Selection([('fee_doctor', 'Fee Per-Doctor'), ('fee_transaction', 'Fee Per-Transaksi'), ('fee_agen', 'Fee Per-Agen')], string='Type Report', required=True)
    format_print_id = fields.Selection([('pdf','PDF'),('xls','EXCEL')], string="Format", required=True)
    category_ids = fields.Many2many('referral.category', string="Referral Category")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralFeeReportWizard,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Fee Report">
                    <group>
                        <group>
                            <field name="company_id" string="Company ID" />
                            <field name="year" string="Year" />
                            <field name="month" string="Month" />
                            <field name="type_report" string="Type Report" />
                            <!--field name="terms_period" string="Terms" /-->
                        </group>
                        <group>
                            <field string="Referral Category" name="category_ids"  widget="many2many_tags" options="{'no_open': False}" />
                            <field name="external_id" string="Referral Agen" />
                            <field name="format_print_id" string="Format" />
                        </group>
                    </group>
                    
                    <footer>
                        <button name="export" string="EXPORT" type="object" class="oe_highlight"/>
                    </footer>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    
    # @api.multi
    def export(self):
        if self.type_report == "fee_doctor":
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/referral_fee/export_referral_fee?id=' + str(self.id)
            action['target'] = 'new'
            return action
        
        if self.type_report == "fee_transaction":
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/referral_fee/export_referral_fee_transaction?id=' + str(self.id)
            action['target'] = 'new'
            return action
        
        if self.type_report == "fee_agen":
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/referral_fee/export_referral_fee_agen?id=' + str(self.id)
            action['target'] = 'new'
            return action



class ReferralFeeConfirmWizard(models.TransientModel):
    _name = 'referral.fee.confirm.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id

    def _year(orm):
        result = []
        year = tools.datetime.now().year - 4
        now = tools.datetime.now().year
        for loop in range(now - year):
            value = str(year + loop + 1)
            result += [(value, value)]
        return result

    def _month(orm):
        result = []
        for loop in range(12):
            month = loop + 1
            result += [(str(month), calendar.month_name[month])]
        return result
    
    company_id = fields.Many2one('res.company', required=True, default=_get_company)
    year = fields.Selection(_year, string="Year", required=True)
    month = fields.Selection(_month, string="Month", required=True)
    referral_fee_ids = fields.Many2many('referral.fee', string="Referral Fee (Odoo)", store=True)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralFeeConfirmWizard,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Fee Confirm">
                    <group>
                        <group>
                            <field name="year" string="Year" />
                            <field name="month" string="Month" />
                        </group>
                        <group>
                            <field name="company_id" string="Company" />
                        </group>
                    </group>
                    <group> 
                        <field name="referral_fee_ids" domain="[('company_id', '=', company_id),('state', '=', 'draft'),('year', '=', year),('month', '=', month)]">
                            <tree>
                                <!--field name="year" string="Year"/>
                                <field name="month" string="Month"/>
                                <field name="external_id"/>
                                <field name="state"/>
                                <field name="net_fee" string="THP" sum="Total" widget="monetary"/-->
                            </tree>
                        </field>
                    </group>
                    <footer>
                        <button name="confirm" string="CONFRIM" type="object" class="oe_highlight"/>
                    </footer>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # @api.multi
    def confirm(self):
        record = self.sudo()
        if record:
            for line in record.referral_fee_ids:
                line.state = 'confirm'
                line.action_confirm_api()
                for l in line.fee_line_ids:
                    l.state = 'confirmed'


class ReferralFeePostingWizard(models.TransientModel):
    _name = 'referral.fee.posting.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id

    def _year(orm):
        result = []
        year = tools.datetime.now().year - 4
        now = tools.datetime.now().year
        for loop in range(now - year):
            value = str(year + loop + 1)
            result += [(value, value)]
        return result

    def _month(orm):
        result = []
        for loop in range(12):
            month = loop + 1
            result += [(str(month), calendar.month_name[month])]
        return result

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    year = fields.Selection(_year, string="Year Period", required=True)
    month = fields.Selection(_month, string="Month Period", required=True)
    referral_fee_ids = fields.Many2many('referral.fee', relation='referral_fee_posting_rel', string="Referral Fee (Odoo)", store=True)
    
    expense_date = fields.Date(string="Expense Date", store=True, required=True, index=True)
    expense_journal_id = fields.Many2one('account.journal', string="Expense Journal")
    expense_account_id = fields.Many2one('account.account', string="Expense Account")
    credit_account_id = fields.Many2one('account.account', string="Credit Account")
    auto_posting = fields.Boolean(string='Posting Entries', default=True, readonly=True)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReferralFeePostingWizard,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Referral Fee Posting">
                    <group>
                        <group>
                            <field name="company_id" />
                            <field name="year" />
                            <field name="month" />
                        </group>
                        <group>
                            <field name="expense_journal_id" domain="[('company_id', '=', company_id)]" />
                            <field name="expense_date" />
                            <field name="expense_account_id" domain="[('company_id', '=', company_id),('code', 'like', '6302%')]" />
                            <field name="credit_account_id" domain="[('company_id', '=', company_id),('code', 'like', '210%')]" />
                            <field name="auto_posting"/>
                        </group>
                    </group>
                    <!--group> 
                        <field name="referral_fee_ids" domain="[('company_id', '=', company_id),('state', '=', 'confirm'),('year', '=', year),('month', '=', month)]">
                            <tree>
                                <field name="year" string="Year"/>
                                <field name="month" string="Month"/>
                                <field name="external_id"/>
                                <field name="state"/>
                                <field name="net_fee" string="THP" sum="Total" widget="monetary"/>
                            </tree>
                        </field>
                    </group-->
                    <footer>
                        <button name="posting" string="Generate Journal" type="object" class="oe_highlight"/>
                    </footer>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # @api.multi
    def posting(self):
        date = self.expense_date
        account_credit_id = self.credit_account_id.id 
        account_debit_id = self.expense_account_id.id
        journal_id = self.expense_journal_id.id
        auto_posting = self.auto_posting
        company_id = self.company_id.id 

        # doctor_ids = tuple(line.external_id.doctor_id.id for line in self.referral_fee_ids)
        for record in self.referral_fee_ids:
            doctor_id = record.external_id.doctor_id.id 
            label = 'RF ' + str(self.year) + '-' + ('00'+str(self.month))[2:] + ' / ' + record.external_id.doctor_id.name
            query = """
                SELECT 
                    sol.tglproses,
                    sol.direction, sol.amount, 
                    sol.account_label service_label, 
                    sol.account_credit_id, 
                    sol.account_debit_id, 
                    (CASE 
                        WHEN sol.direction < 1 
                        THEN COALESCE(sol.analytic_id, 0) 
                        ELSE 0 END) analytic_credit_id,
                    (CASE 
                        WHEN sol.direction = 1 
                        THEN COALESCE(sol.analytic_id, 0) 
                        ELSE 0 END) analytic_debit_id
                FROM view_account_referral_cost sol
                WHERE sol.company_id = {company_id}
                AND EXTRACT(YEAR FROM sol.tglproses) = {year}
                AND EXTRACT(MONTH FROM sol.tglproses) = {month}
                AND sol.trans_type IN('DF-LINE','REF-THP')
                AND sol.doctor_id = {doctor_id} AND sol.amount != 0
            """ .format(
                company_id=company_id,
                doctor_id=doctor_id,
                year=self.year, 
                month=self.month)

            self.env.cr.execute(query)
            lines = self.env.cr.dictfetchall()

            if not lines:
                print ("There are no lines to make journal")
                return
            move_lines = []

            for line in lines:
                debit_id = account_credit_id if line['direction'] < 1 else account_debit_id
                credit_id = account_debit_id if line['direction'] < 1 else account_credit_id

                if int(line['analytic_credit_id']) > 0:
                    move_lines.append([0, 0, {'name':str(line['service_label']), 'analytic_account_id':int(line['analytic_credit_id']), 'account_id':credit_id, 'debit':0.0, 'credit':line['amount'] or 0.0, 'referral_id':record.id}])
                else:
                    move_lines.append([0, 0, {'name':str(line['service_label']), 'account_id':credit_id, 'debit':0.0, 'credit':line['amount'] or 0.0, 'referral_id':record.id}])
                
                if int(line['analytic_debit_id']) > 0:
                    move_lines.append([0, 0, {'name':str(line['service_label']), 'analytic_account_id':int(line['analytic_debit_id']), 'account_id':debit_id, 'credit':0.0, 'debit':line['amount'] or 0.0, 'referral_id':record.id}])
                else:
                    move_lines.append([0, 0, {'name':str(line['service_label']), 'account_id':debit_id, 'credit':0.0, 'debit':line['amount'] or 0.0, 'referral_id':record.id}])
                    
            move = self.env['account.move'].create({'journal_id':journal_id,'ref':label,'line_ids':move_lines,'date':date, 'referral_id':record.id})
            
            if move:
                record.journal_id = move.id 
                
            if auto_posting:
                move.action_post()
                record.state = 'posted'
                
                # update state referral.fee.line
                for r in record.fee_line_ids:
                    r.state = 'posted'
                for r1 in record.fee_other_ids:
                    r1.state = 'posted'
                for r2 in record.fee_deduction_ids:
                    r2.state = 'posted' 


class ReferralCategory(models.Model):
    _name = 'referral.category'

    sync_type = sync.type
    sync_date = sync.date 
    sync_id = sync.id
    sync_id_api = sync.id_api 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    # @api.model
    # def _get_company(self):
    #     return self.env.company.id

    # company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    name = fields.Char(string="Category", required=True)