from datetime import datetime, timedelta
import calendar
from odoo import http, models, fields, api, tools, exceptions
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero, float_compare
from odoo.addons import decimal_precision as dp
# from odoo.addons.web.controllers.main import serialize_exception, content_disposition
# from data import convert, json, encode
from json import dumps, loads

import requests
import logging
import pytz

from xml.etree import ElementTree
# import urllib2
import urllib.request as urllib2
import xmltodict

from dateutil.relativedelta import relativedelta
from multiprocess import Process, Manager
# import json

import base64
# load odoo library
from odoo.http import request
from pyjasperclient import JasperClient

from . import sync


class RatePosition(models.Model):
    _name = 'marketing.position'
    _rec_name = 'name'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    code  = fields.Char(string="Code")
    name = fields.Char(string="Position")
    level = fields.Selection([('staff','Staff'),('management','Management')], string="Level")
    active = fields.Boolean(string="Active", default=True)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(RatePosition,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Job Position">
                    <sheet>
                        <div class="oe_title">
                            <label string="Job Title"/>
                                <h1>
                                    <field name="name" />
                                </h1>
                            </div>
                            <group>
                                <group>
                                    <field name="code"/>
                                    <field name="level"/>
                                </group>
                                <group>
                                    <field name="company_id"/>
                                    <field name="active"/>
                                </group>
                            </group>
                    </sheet>
                    <!--div class="oe_chatter">
                        <field name="message_follower_ids" widget="mail_followers"/>
                        <field name="message_ids" widget="mail_thread"/>
                    </div-->
                </form>
            """

        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Job Position">
                    <field name="company_id"/>
                    <field name="code"/>
                    <field name="name"/>
                </tree>
            """

        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Position">
                    <filter name="active" string="Active" domain="[('active','=', True)]"/>
                    <filter name="inactive" string="Inactive" domain="[('active','=', False)]"/>
                    <separator/>
                    <field name="company_id"/>
                    <field name="code"/>
                    <field name="name"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class RateSales(models.Model):
    _name = 'marketing.sales'
    # _rec_name = 'sales_code'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    sales_code  = fields.Char(string="Sales Code")
    sales_direct = fields.Boolean(string="Is Direct Sales")
    position_id = fields.Many2one('marketing.position', string="Job Position")
    active = fields.Boolean(string="Active", default=True)

    # @api.multi
    @api.depends('position_id', 'sales_code','sales_direct')
    def name_get(self):
        result = []
        for record in self:
            name = str(record.sales_code) + ' - ' + str(record.position_id.name) + (' (Direct Sales)' if record.sales_direct is True else '')
            result.append((record.id, name))
        return result

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(RateSales,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Marketing Type">
                    <sheet>
                        <group>
                            <group>
                                <field name="sales_code"/>
                                <field name="position_id"/>
                                <field name="sales_direct"/>
                            </group>
                            <group>
                                <field name="company_id"/>
                                <field name="active"/>
                            </group>
                        </group>
                    </sheet>
                    <!--div class="oe_chatter">
                        <field name="message_follower_ids" widget="mail_followers"/>
                        <field name="message_ids" widget="mail_thread"/>
                    </div-->
                </form>
            """

        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Sales Type">
                    <field name="company_id"/>
                    <field name="sales_code"/>
                    <field name="sales_direct"/>
                    <field name="position_id"/>
                </tree>
            """

        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Sales Type">
                    <filter name="active" string="Active" domain="[('active','=', True)]"/>
                    <filter name="inactive" string="Inactive" domain="[('active','=', False)]"/>
                    <separator/>
                    <field name="company_id"/>
                    <field name="sales_code"/>
                    <field name="sales_direct"/>
                    <field name="position_id"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class MarketingEmployee(models.Model):
    _name = 'marketing.employee'
    _rec_name = 'name'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    code  = fields.Char(string="Employee No.")
    name = fields.Char(string="Employee Name")
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')], string="Gender")
    position_id = fields.Many2one('marketing.position', string="Job Position")
    sales_id = fields.Many2one('marketing.sales', string="Marketing Type")
    # sales_direct = fields.Boolean(related="sales_id.sales_direct")
    is_npwp = fields.Boolean(string="Is NPWP")
    npwp = fields.Char(string="NPWP")
    pph = fields.Selection([('0','Without PPH'),('21','PPH 21') ,('23','PPH 23')], string="PPH")
    address = fields.Char(string="Address")
    phone = fields.Char(string="Phone")
    bank_name = fields.Char(string="Bank Name")
    bank_branch = fields.Char(string="Bank Branch")
    bank_account = fields.Char(string="Bank Account No.")
    bank_client = fields.Char(string="Bank Account Name")
    active = fields.Boolean(string="Active", default=True)
    line_ids = fields.One2many('marketing.employee.company', 'employee_id', string="Mapping Companies")

    # @api.multi
    @api.depends('name')
    def name_get(self):
        result = []
        for record in self:
            if record.code:
                name = '[' + str(record.code) + '] ' + str(record.name)
            else:
                name = str(record.name)
            result.append((record.id, name))
        return result

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(MarketingEmployee,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Marketing Employee">
                    <field name="company_id"/>
                    <field name="code"/>
                    <field name="name"/>
                    <field name="gender"/>
                    <field name="sales_id"/>
                    <field name="npwp"/>
                </tree>
            """

        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Marketing Employee">
                    <filter name="active" string="Active" domain="[('active','=', True)]"/>
                    <filter name="inactive" string="Inactive" domain="[('active','=', False)]"/>
                    <separator/>
                    <field name="company_id"/>
                    <field name="code"/>
                    <field name="name"/>
                    <field name="gender"/>
                    <field name="sales_id"/>
                    <field name="npwp"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res
    

class MarketingEmployeeCompany(models.Model):
    _name = 'marketing.employee.company'
    # _rec_name = 'name'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    employee_id = fields.Many2one('marketing.employee', string="Employee No.")
    payor_id = fields.Many2one('res.partner', string="Payor Name")
    payor_type = fields.Char(related="payor_id.customer_type_wipro", string="Payor Type")
    payor_code = fields.Char(related="payor_id.vendor_code", string="Payor Code")
    active = fields.Boolean(string="Active", default=True)


class MarketingRate(models.Model):
    _name = 'marketing.rate'
    _rec_name = 'company_id'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    rate = fields.Float(string="Incentive Rate", digits=(16,6))
    new_rate_ids = fields.One2many('marketing.rate.line', 'rate_id', string="Rate New Customer")
    dividen_ids = fields.One2many('marketing.dividen', 'rate_id', string="Rate Dividen")
    exception_ids = fields.One2many('marketing.exception', 'rate_id', string="Exception Payer")
    exception_type_ids = fields.One2many('marketing.exception.type', 'rate_id', string="Exception Type")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(MarketingRate,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Incentive Rate for Old Customer">
                    <field name="company_id"/>
                    <field name="rate"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Rate">
                    <field name="company_id"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res



class MarketingRatePersonal(models.Model):
    _name = 'marketing.rate.personal'
    _rec_name = 'name'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    # payor_id = fields.Many2one('res.partner', string="Payor Name")
    # payor_type = fields.Char(related="payor_id.customer_type_wipro")
    # payor_code = fields.Char(related="payor_id.vendor_code")

    code = fields.Char(string="Personal No.")
    name = fields.Char(string="Personel Name")
    payer_name = fields.Char(string="Payer Name")
    fee_percent = fields.Float(string="Fee Percentage", digits=(16,6))
    is_npwp = fields.Boolean(string="Is NPWP")
    npwp = fields.Char(string="NPWP")
    pph = fields.Selection([('0','Without PPH'),('21','PPH 21') ,('23','PPH 23')], string="PPH")
    remark = fields.Char(string="Remark")
    active = fields.Boolean(string="Active", default=True)
    payor_ids = fields.Many2many('res.partner', 'marketing_rate_personal_company', 'personal_id', string="Payor Name")

    # @api.multi
    @api.depends('name')
    def name_get(self):
        result = []
        for record in self:
            if record.code:
                name = '[' + str(record.code) + '] ' + str(record.name)
            else:
                name = str(record.name)
            result.append((record.id, name))
        return result


    @api.model
    def create(self, vals):
        result = super(MarketingRatePersonal, self).create(vals)
        result.code = self.env['ir.sequence'].sudo().next_by_code('marketing.personal.sequence')
        return result


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(MarketingRatePersonal,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Rate of Personel Fee">
                    <field name="company_id"/>
                    <field name="code"/>
                    <field name="name"/>
                    <field name="remark"/>
                </tree>
            """

        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Rate of Fee PIC">
                    <filter name="active" string="Active" domain="[('active','=', True)]"/>
                    <filter name="inactive" string="Inactive" domain="[('active','=', False)]"/>
                    <separator/>
                    <field name="company_id"/>
                    <field name="name"/>
                    <field name="code"/>
                    <field name="remark"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res




class MarketingRatePIC(models.Model):
    _name = 'marketing.rate.pic'
    _rec_name = 'name'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    code = fields.Char(string="PIC No.")
    name = fields.Char(string="PIC Name")
    payer_name = fields.Char(string="Payer Name")

    fee_percent = fields.Float(string="Fee Percentage", digits=(16,6))
    fee_amount = fields.Float(string="Fee Amount", digits=(16,6))

    is_npwp = fields.Boolean(string="Is NPWP")
    npwp = fields.Char(string="NPWP")
    pph = fields.Selection([('0','Without PPH'),('21','PPH 21') ,('23','PPH 23')], string="PPH")

    bank_name = fields.Char(string="Bank Name")
    bank_branch = fields.Char(string="Bank Branch")
    bank_account = fields.Char(string="Bank Account No.")
    bank_client = fields.Char(string="Bank Account Name")
    payor_ids = fields.Many2many('res.partner', 'marketing_rate_pic_company', 'pic_id', string="Payor")

    payment_type = fields.Selection([('TRANSFER','BANK TRANSFER'), ('CASH','CASH')], string="Payment Method")
    patient_type = fields.Selection([
        ('0', 'ALL'),
        ('1', 'OPD (Without Pharmacy Item)'),
        ('2', 'IPD'),
        ('3', 'EMERGENCY'),
        ('4', 'DAYCARE'),
        ('5', 'OPD (With Pharmacy Item)'),
        ('6', 'PHARMACY')], string="Patient Type")
    remark = fields.Char(string="Remark")
    active = fields.Boolean(string="Active", default=True)


    # @api.multi
    @api.depends('name')
    def name_get(self):
        result = []
        for record in self:
            if record.code:
                name = '[' + str(record.code) + '] ' + str(record.name)
            else:
                name = str(record.name)
            result.append((record.id, name))
        return result


    @api.model
    def create(self, vals):
        result = super(MarketingRatePIC, self).create(vals)
        result.code = self.env['ir.sequence'].sudo().next_by_code('marketing.pic.sequence')
        return result


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(MarketingRatePIC,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Rate of Fee PIC">
                    <field name="company_id"/>
                    <field name="code"/>
                    <field name="name"/>
                    <field name="payment_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Rate of Fee PIC">
                    <filter name="active" string="Active" domain="[('active','=', True)]"/>
                    <filter name="inactive" string="Inactive" domain="[('active','=', False)]"/>
                    <separator/>
                    <field name="company_id"/>
                    <field name="code"/>
                    <field name="name"/>
                    <field name="payment_type"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class MarketingRateLine(models.Model):
    _name = 'marketing.rate.line'
    # _rec_name = 'company_id'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    rate_id = fields.Many2one('marketing.rate', string="Rate ID")
    sequence = fields.Integer(string="Sequence")
    range_min = fields.Float(string="Range Min", digits=(16,6))
    range_max = fields.Float(string="Range Max", digits=(16,6))
    rate = fields.Float(string="Incentive Rate", digits=(16,6))


class MarketingDividen(models.Model):
    _name = 'marketing.dividen'
    # _rec_name = 'company_id'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    rate_id = fields.Many2one('marketing.rate', string="Rate")
    sales_id = fields.Many2one('marketing.sales', string="Sales Position")
    sales_code = fields.Char(related="sales_id.sales_code")
    is_direct = fields.Boolean(string="Direct Sales", default=False)
    sales_position = fields.Char(related="sales_id.position_id.code")
    rate_old = fields.Float(string="Rate for Old", digits=(16,6))
    rate_new = fields.Float(string="Rate for New", digits=(16,6))


class MarketingException(models.Model):
    _name = 'marketing.exception'
    # _rec_name = 'company_id'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    rate_id = fields.Many2one('marketing.rate', string="Rate ID")
    payor_id = fields.Many2one('res.partner', string="Payor Name")
    payor_type = fields.Char(related="payor_id.customer_type_wipro")
    payor_code = fields.Char(related="payor_id.vendor_code")
    active = fields.Boolean(string="Active", default=True)



class MarketingExceptionType(models.Model):
    _name = 'marketing.exception.type'
    # _rec_name = 'company_id'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    rate_id = fields.Many2one('marketing.rate', string="Rate ID")
    name = fields.Char(string="Payor Type")


class MarketingFeeDoctor(models.Model):
    _name = 'marketing.doctor.fee.import'
    _rec_name = 'name'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    period_year = fields.Integer(string="Tahun")
    period_month = fields.Selection([
        ('1','January'),
        ('2','February'),
        ('3','March'),
        ('4','April'),
        ('5','May'),
        ('6','June'),
        ('7','July'),
        ('8','Augustus'),
        ('9','September'),
        ('10','October'),
        ('11','November'),
        ('12','December')], string="Bulan")
    name = fields.Char(string="No Bayar")
    serial_no = fields.Char(string="Serial No")
    bill_date = fields.Date(string="Bill Date")
    bill_no = fields.Char(string="Bill No")
    patient_name = fields.Char(string="Patient Name")
    doctor_name = fields.Char(string="Doctor Name")
    emp_no = fields.Char(string="Emp No")
    service_name = fields.Char(string="Service Name")
    service_item = fields.Char(string="Service Item")
    bill_amount = fields.Float(string="Amount")
    fee_amount = fields.Float(string="Doctor Amount")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(MarketingFeeDoctor,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Fee Doctor Import">
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id"/>
                                <field name="period_year"/>
                                <field name="period_month"/>
                                <field name="name"/>
                                <field name="serial_no"/>
                                <field name="bill_date"/>
                                <field name="bill_no"/>
                            </group>
                            <group>
                                <field name="patient_name"/>
                                <field name="doctor_name"/>
                                <field name="emp_no"/>
                                <field name="service_name"/>
                                <field name="service_item"/>
                                <field name="bill_amount"/>
                                <field name="fee_amount"/>
                            </group>
                        </group>
                    </sheet>
                    <!--div class="oe_chatter">
                        <field name="message_follower_ids" widget="mail_followers"/>
                        <field name="message_ids" widget="mail_thread"/>
                    </div-->
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Fee Doctor Import">
                    <field name="company_id" invisible="1"/>
                    <field name="period_year"/>
                    <field name="period_month"/>           
                    <field name="name"/>
                    <field name="bill_no"/>
                    <field name="patient_name"/>
                    <field name="doctor_name"/>
                    <field name="service_name"/>
                    <field name="service_item"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Fee Doctor">
                    <filter name="active" string="Active" domain="[('active','=', True)]"/>
                    <filter name="inactive" string="Inactive" domain="[('active','=', False)]"/>
                    <separator/>
                    <field name="company_id"/>
                    <field name="name"/>
                    <field name="bill_no"/>
                    <field name="patient_name"/>
                    <field name="doctor_name"/>
                    <field name="service_name"/>
                    <field name="service_item"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

class MarketingFeeWizard(models.TransientModel):
    _name = 'marketing.fee.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    date_cutoff = fields.Date(string="Cutoff Receipt", default=lambda self: datetime.today().strftime("%Y-%m-%d"))
    date_start = fields.Date(string="Bill Start", default=lambda self: datetime.today().strftime("%Y-%m-%d"))
    date_end = fields.Date(string="Bill End", default=lambda self: datetime.today().strftime("%Y-%m-%d"))
    reference = fields.Char(string="Reference")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(MarketingFeeWizard,self).get_view(view_id=view_id,view_type=view_type, **options)  
        res['arch'] = """
            <form string="Compute Fee">
                <group>
                    <group>
                        <field name="company_id" />
                        <field name="date_cutoff"  />
                        <field name="reference" />
                    </group>
                    <group>
                        <field name="date_start" />
                        <field name="date_end" />
                    </group>
                </group>
                <footer>                        
                    <button name="compute_billing" string="Calculate Billing" type="object" class="oe_highlight"/>
                    <button name="compute_calculate" string="Calculate Billing" type="object" class="oe_highlight"/>
                    <button name="compute_personal" string="Compute Personal Fee" type="object" class="oe_highlight"/>
                    <button name="compute_marketing" string="Compute Marketing Fee" type="object" class="oe_highlight"/>
                    <button name="compute_pic" string="Compute PIC Fee" type="object" class="oe_highlight"/>
                </footer>
            </form>
        """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


    # @api.multi
    def compute_billing(self):
        company_id = self.company_id.id 
        sync_type = self.company_id.sync_type 
        reference = self.reference

        date_cutoff = datetime.strptime(str(self.date_cutoff), '%Y-%m-%d')
        date_start = datetime.strptime(str(self.date_start), '%Y-%m-%d')
        date_end = datetime.strptime(str(self.date_end), '%Y-%m-%d')

        month_start = datetime.strptime(str(self.date_start), '%Y-%m-%d').month
        month_end = datetime.strptime(str(self.date_end), '%Y-%m-%d').month

        year_start = datetime.strptime(str(self.date_start), '%Y-%m-%d').year
        year_end = datetime.strptime(str(self.date_end), '%Y-%m-%d').year

        if month_start != month_end:
            raise UserError(_("Tanggal awal & akhir masih harus dalam satu periode bulan."))
        if year_start != year_end:
            raise UserError(_("Tanggal awal & akhir masih harus dalam satu periode bulan."))

        # hapus temp billing yg masih draft
        query = """
            delete from marketing_billing
            where company_id = {company_id}
                and date_start >= '{date_start}'
                and date_end <= '{date_end}'
                and status = 'draft'
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_cutoff = date_cutoff,
            date_start = date_start,
            date_end = date_end)
        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        # cek apakah ada temp billing yg sudah di calculate ?
        # query = """
        #     select count(*) hitung
        #     from marketing_billing a
        #     where a.company_id = {company_id}
        #         and a.date_start >= '{date_start}'
        #         and a.date_end <= '{date_end}'
        #         and a.status = 'calculate'
        # """.format(
        #     company_id = company_id,
        #     sync_type = sync_type,
        #     date_cutoff = date_cutoff,
        #     date_start = date_start,
        #     date_end = date_end)
        # open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        # self.env.cr.execute(query)
        # result = self.env.cr.dictfetchall()

        # if result[0]['hitung'] > 0:
        #     raise UserError(_("Billing periode {date_start} s/d {date_end} sudah pernah di generate.".format(date_start=date_start, date_end=date_end)))


        # delete from marketing_fee_line
        query = """
            delete from marketing_fee_line 
            where fee_id in(
                select t.id 
                from marketing_fee t
                where t.company_id = {company_id}
                    and t.date_start >= '{date_start}'
                    and t.date_end <= '{date_end}'
            ) 
            and billing_id in(
                select t.id 
                from marketing_billing t
                where t.company_id = {company_id}
                    and t.date_start >= '{date_start}'
                    and t.date_end <= '{date_end}'
                    and t.company_id in (
                        select exc.payor_id 
                        from marketing_exception exc
                        inner join marketing_rate rate on rate."id"=exc.rate_id 
                        where rate.company_id={company_id}
                    )
            )
            """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            reference = reference
        )

        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)



        # delete from marketing_personal_line
        query = """
            delete from marketing_personal_line 
            where fee_id in(
                select t.id 
                from marketing_personal t
                where t.company_id = {company_id}
                    and t.date_start >= '{date_start}'
                    and t.date_end <= '{date_end}'
            ) 
            and billing_id in(
                select t.id 
                from marketing_billing t
                where t.company_id = {company_id}
                    and t.date_start >= '{date_start}'
                    and t.date_end <= '{date_end}'
                    and t.company_id in (
                        select exc.payor_id 
                        from marketing_exception exc
                        inner join marketing_rate rate on rate."id"=exc.rate_id 
                        where rate.company_id={company_id}
                    )
            )
            """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            reference = reference
        )

        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


         # delete from marketing_billing
        query = """
            delete from marketing_billing 
            where company_id = {company_id}
                and date_start >= '{date_start}'
                and date_end <= '{date_end}'
                and company_id in (
                    select exc.payor_id 
                    from marketing_exception exc
                    inner join marketing_rate rate on rate."id"=exc.rate_id 
                    where rate.company_id={company_id}
                )
            """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            reference = reference
        )

        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)



        # generate billing
        query = """
            insert into marketing_billing (
                company_id, odoo_bill_id, odoo_patient_id, 
                odoo_payer_id, odoo_letter_id, 
                name, date_start, date_end, bill_no, bill_date,
                payer_id, payer_code, payer_name, 
                valid_from, valid_to, payer_new,
                patient_mrid, patient_name, patient_type,
                letter_no, receipt_date, creditnote_date, 
                adjustment_date, balance_date,
                bill_amount, credit_amount, nett_amount,
                personal_fee, fee_amount, nett_marketing, 
                status)
            select {company_id} company_id, 
                a.id odoo_bill_id, a.partner_id odoo_patient_id, 
                a.payer_id odoo_payer_id, cl.letter_id odoo_letter_id, 
                '{reference}' nama, '{date_start}' date_start, '{date_end}' date_end, 
                a.billno bill_no, date(a.bill_date) bill_date,
                b."id" payer_id, b.vendor_code payer_code, b."name" payer_name, 
                '1900-01-01' valid_from, '{date_end}' valid_to, b.payer_new,
                c.registration_code patient_mrid, 
                c."name" patient_name, a.patient_type,
                cl.letter_no, py.payment_date receipt_date, cn.creditnote_date, 
                coalesce(ar.advance_date, py.payment_date) adjustment_date, 
                (case 
                    when coalesce(cn.creditnote_date,ar.advance_date, py.payment_date) > coalesce(ar.advance_date, py.payment_date) 
                    then coalesce(cn.creditnote_date,ar.advance_date, py.payment_date) 
                    else coalesce(ar.advance_date, py.payment_date) 
                end) balance_date,
                a.total_amount bill_amount, 
                0 credit_amount, 
                (a.total_amount - 0) nett_amount, 
                0 personal_fee,
                coalesce(df.fee_amount,0.0) fee_amount,
                (a.total_amount - coalesce(df.fee_amount,0.0)) nett_marketing,
                'draft' status
            from sale_order_bill a 
            left join res_partner b on b.id = a.payer_id
            left join res_partner c on c."id" = a.partner_id
            /* 
            left join lateral (
                select bl.* 
                from sale_order_bill_history bl 
                where bl.billing_id = a.id 
                    and date(bl.datetime) <= '{date_end}'
                and bl.state in ('invoice')
                and bl.active = True
              order by bl.datetime desc, bl.id desc limit 1 
            ) bl on 0=0
            */
            left join lateral (
                select sum(coalesce(t.fee_amount,0.0)) fee_amount
                from marketing_doctor_fee_import t 
                where t.company_id = a.company_id
                    and t.bill_no = a.billno 
            ) df on 0=0
            left join lateral (
                select cl.id letter_id, cl.name letter_no 
                from account_coveringletter cl 
                inner join account_coveringletter_bill_rel clb on clb.account_coveringletter_id = cl.id 
                where clb.sale_order_bill_id = a.id 
                    and cl.state in('confirm','confirm', 'paid', 'done')
                    and cl.company_id = a.company_id 
                order by cl.date desc limit 1
            ) cl on 0=0
            left join lateral (
                select cn.id creditnote_id, 
                    cn."name" creditnote_no,
                    cn."date" creditnote_date  
                from account_creditnote_line cnl 
                inner join account_creditnote cn on cn."id" = cnl.creditnote_id
                where cn.state in ('confirm','confirm','posted','paid')
                    and cn.company_id = a.company_id
                    and cnl.billing_sale_id = a."id"
                order by cn.date desc limit 1 
            ) cn on 0=0
            left join lateral (
                select py.id payment_id, 
                    py."name" payment_no,
                    py.payment_date  
                from account_payment_bill_rel pyl 
                inner join account_payment py on py."id" = pyl.account_payment_id
                where py.state in ('confirm','confirm','posted','paid')
                    and py.company_id = a.company_id
                    and py.payment_type = 'inbound'
                    and pyl.sale_order_bill_id = a."id"
                order by py.payment_date desc limit 1 
            ) py on 0=0

            left join lateral (
                select ar.id payment_id, 
                    ar."name" advance_no,
                    ar."date" advance_date  
                from account_payment_bill_rel arl 
                inner join account_advance_realization ar on ar."id" = arl.advance_realization_id 
                where ar.state in ('confirm','confirm','posted','paid')
                    and ar.company_id = a.company_id
                    and arl.sale_order_bill_id = a."id"
                order by ar.date desc limit 1 
            ) ar on 0=0

            where a.company_id = {company_id}
                and (a."state" = 'invoice' or left(a.billno, 3) in('ISP','OSP'))
                and date(a.confirmation_date) >= '{date_start}'
                and date(a.confirmation_date) <= '{date_end}'
                and a.billno not like '%[ARCHIVE]%'
                --and coalesce(bl.payer_balance, a.payer_balance, 0) = 0 --sudah lunas baru bayar
                and a.payer_balance = 0 --sudah lunas baru bayar
                and a.payer_id not in (
                    select t.payor_id 
                    from marketing_exception t 
                    inner join marketing_rate t2 on t2."id"=t.rate_id 
                    where t2.company_id={company_id}
                )
                and b.customer_type_wipro not in(
                    select t."name" 
                    from marketing_exception_type t 
                    inner join marketing_rate t2 on t2."id"=t.rate_id 
                    where t2.company_id={company_id}
                )
                --and not exists(
                --    select 1
                --    from marketing_billing t 
                --    where t.company_id = a.company_id
                --        and t.bill_no = a.billno
                --        and t.status = 'calculate'
                --)
                and a.billno not in (
                    select t.bill_no
                    from marketing_billing t 
                    where t.company_id = a.company_id
                        and t.bill_no = a.billno
                        and t.status = 'calculate'
                )
                --pelunasan maksimal 3 bulan
                and DATE_PART('month', AGE(date(a.bill_date), (case 
                        when coalesce(cn.creditnote_date,ar.advance_date, py.payment_date) > coalesce(ar.advance_date, py.payment_date) 
                        then coalesce(cn.creditnote_date,ar.advance_date, py.payment_date) 
                        else coalesce(ar.advance_date, py.payment_date) 
                    end)
                )) <= 3

                --tidak ada tindakan PCR dan MCU
                and (
                    --patient type selain OPD
                    a.patient_type in('2','3') or
                    --atau tidak ada tindakan PCR 
                    not exists (
                        select 1
                        from sale_order_line t 
                        inner join product_product t2 on t2.id = t.product_id
                        inner join product_template t3 on t3.id = t2.product_tmpl_id
                        where t.billing_id = a.id 
                            and t.type_line in ('BILL','BILLING')
                            and (t3.name->>'en_US' ilike '%MCU%' or t3.name->>'en_US' ilike '%PCR%' or t3.name->>'en_US' ilike '%swab%')
                        limit 1
                    )
                )
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            reference = reference
        )

        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)
        
        # delete billingan pasien yang tanggal lunas nya lebih dari 3 bulan kedepan 
        query = """
            DELETE FROM marketing_billing 
            WHERE DATE(bill_date) >= '{date_start}'
                AND DATE(bill_date) <= '{date_end}'
                AND DATE_PART('month', AGE(TO_CHAR(balance_date, 'yyyy-mm-01')::date, TO_CHAR(bill_date, 'yyyy-mm-01')::date)) > 3 
                AND company_id = {company_id}
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            reference = reference
        )

        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)

        
    # @api.multi
    def compute_calculate(self):
        company_id = self.company_id.id 
        sync_type = self.company_id.sync_type 
        reference = self.reference

        date_cutoff = (self.date_cutoff).strftime('%Y-%m-%d')
        date_start = (self.date_start).strftime('%Y-%m-%d')
        date_end = (self.date_end).strftime('%Y-%m-%d')

        month_start = (self.date_start).month
        month_end = (self.date_end).month

        year_start = (self.date_start).year
        year_end = (self.date_end).year

        if month_start != month_end:
            raise UserError(_("Tanggal awal & akhir masih harus dalam satu periode bulan."))
        if year_start != year_end:
            raise UserError(_("Tanggal awal & akhir masih harus dalam satu periode bulan."))

        # hapus temp billing yg masih draft
        query = """
            delete from marketing_billing
            where company_id = {company_id}
                and date_start >= '{date_start}'
                and date_end <= '{date_end}'
                and status = 'draft'
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_cutoff = date_cutoff,
            date_start = date_start,
            date_end = date_end)
        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        # cek apakah ada temp billing yg sudah di calculate ?
        # query = """
        #     select count(*) hitung
        #     from marketing_billing a
        #     where a.company_id = {company_id}
        #         and a.date_start >= '{date_start}'
        #         and a.date_end <= '{date_end}'
        #         and a.status = 'calculate'
        # """.format(
        #     company_id = company_id,
        #     sync_type = sync_type,
        #     date_cutoff = date_cutoff,
        #     date_start = date_start,
        #     date_end = date_end)
        # open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        # self.env.cr.execute(query)
        # result = self.env.cr.dictfetchall()

        # if result[0]['hitung'] > 0:
        #     raise UserError(_("Billing periode {date_start} s/d {date_end} sudah pernah di generate.".format(date_start=date_start, date_end=date_end)))


        # delete from marketing_fee_line
        query = """
            delete from marketing_fee_line 
            where fee_id in(
                select t.id 
                from marketing_fee t
                where t.company_id = {company_id}
                    and t.date_start >= '{date_start}'
                    and t.date_end <= '{date_end}'
            ) 
            and billing_id in(
                select t.id 
                from marketing_billing t
                where t.company_id = {company_id}
                    and t.date_start >= '{date_start}'
                    and t.date_end <= '{date_end}'
                    and t.company_id in (
                        select exc.payor_id 
                        from marketing_exception exc
                        inner join marketing_rate rate on rate."id"=exc.rate_id 
                        where rate.company_id={company_id}
                    )
            )
            """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            reference = reference
        )

        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)



        # delete from marketing_personal_line
        query = """
            delete from marketing_personal_line 
            where fee_id in(
                select t.id 
                from marketing_personal t
                where t.company_id = {company_id}
                    and t.date_start >= '{date_start}'
                    and t.date_end <= '{date_end}'
            ) 
            and billing_id in(
                select t.id 
                from marketing_billing t
                where t.company_id = {company_id}
                    and t.date_start >= '{date_start}'
                    and t.date_end <= '{date_end}'
                    and t.company_id in (
                        select exc.payor_id 
                        from marketing_exception exc
                        inner join marketing_rate rate on rate."id"=exc.rate_id 
                        where rate.company_id={company_id}
                    )
            )
            """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            reference = reference
        )

        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


         # delete from marketing_billing
        query = """
            delete from marketing_billing 
            where company_id = {company_id}
                and date_start >= '{date_start}'
                and date_end <= '{date_end}'
                and company_id in (
                    select exc.payor_id 
                    from marketing_exception exc
                    inner join marketing_rate rate on rate."id"=exc.rate_id 
                    where rate.company_id={company_id}
                )
            """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            reference = reference
        )

        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)



        # generate billing
        query = """
            insert into marketing_billing (
                company_id, odoo_bill_id, odoo_patient_id, 
                odoo_payer_id, odoo_letter_id, 
                name, date_start, date_end, bill_no, bill_date,
                payer_id, payer_code, payer_name, 
                valid_from, valid_to, payer_new,
                patient_mrid, patient_name, patient_type,
                letter_no, receipt_date, creditnote_date, 
                adjustment_date, balance_date,
                bill_amount, credit_amount, nett_amount,
                personal_fee, fee_amount, nett_marketing, 
                status)
            select {company_id} company_id, 
                a.id odoo_bill_id, a.partner_id odoo_patient_id, 
                a.payer_id odoo_payer_id, cl.letter_id odoo_letter_id, 
                '{reference}' nama, '{date_start}' date_start, '{date_end}' date_end, 
                a.billno bill_no, date(a.bill_date) bill_date,
                b."id" payer_id, b.vendor_code payer_code, b."name" payer_name, 
                '1900-01-01' valid_from, '{date_end}' valid_to, b.payer_new,
                c.registration_code patient_mrid, 
                c."name" patient_name, a.patient_type,
                cl.letter_no, py.payment_date receipt_date, cn.creditnote_date, 
                coalesce(ar.advance_date, py.payment_date) adjustment_date, 
                (case 
                    when coalesce(cn.creditnote_date,ar.advance_date, py.payment_date) > coalesce(ar.advance_date, py.payment_date) 
                    then coalesce(cn.creditnote_date,ar.advance_date, py.payment_date) 
                    else coalesce(ar.advance_date, py.payment_date) 
                end) balance_date,
                a.total_amount bill_amount, 
                0 credit_amount, 
                (a.total_amount - 0) nett_amount, 
                0 personal_fee,
                coalesce(df.fee_amount,0.0) fee_amount,
                (a.total_amount - coalesce(df.fee_amount,0.0)) nett_marketing,
                'draft' status
            from sale_order_bill a 
            left join res_partner b on b.id = a.payer_id
            left join res_partner c on c.id = a.partner_id
            /* 
            left join lateral (
                select bl.* 
                from sale_order_bill_history bl 
                where bl.billing_id = a.id 
                    and date(bl.datetime) <= '{date_end}'
                and bl.state in ('invoice')
                and bl.active = True
              order by bl.datetime desc, bl.id desc limit 1 
            ) bl on 0=0
            */
            left join lateral (
                select sum(coalesce(t.fee_amount,0.0)) fee_amount
                from marketing_doctor_fee_import t 
                where t.company_id = a.company_id
                    and t.bill_no = a.billno 
            ) df on 0=0
            left join lateral (
                select cl.id letter_id, cl.name letter_no 
                from account_coveringletter cl 
                inner join account_coveringletter_bill_rel clb on clb.account_coveringletter_id = cl.id 
                where clb.sale_order_bill_id = a.id 
                    and cl.state in('confirm','confirm', 'paid', 'done')
                    and cl.company_id = a.company_id 
                order by cl.date desc limit 1
            ) cl on 0=0
            left join lateral (
                select cn.id creditnote_id, 
                    cn."name" creditnote_no,
                    cn."date" creditnote_date  
                from account_creditnote_line cnl 
                inner join account_creditnote cn on cn."id" = cnl.creditnote_id
                where cn.state in ('confirm','confirm','posted','paid')
                    and cn.company_id = a.company_id
                    and cnl.billing_sale_id = a."id"
                order by cn.date desc limit 1 
            ) cn on 0=0
            left join lateral (
                select py.id payment_id, 
                    py."name" payment_no,
                    py.payment_date  
                from account_payment_bill_rel pyl 
                inner join account_payment py on py."id" = pyl.account_payment_id
                where py.state in ('confirm','confirm','posted','paid')
                    and py.company_id = a.company_id
                    and py.payment_type = 'inbound'
                    and pyl.sale_order_bill_id = a."id"
                order by py.payment_date desc limit 1 
            ) py on 0=0

            left join lateral (
                select ar.id payment_id, 
                    ar."name" advance_no,
                    ar."date" advance_date  
                from account_payment_bill_rel arl 
                inner join account_advance_realization ar on ar."id" = arl.advance_realization_id 
                where ar.state in ('confirm','confirm','posted','paid')
                    and ar.company_id = a.company_id
                    and arl.sale_order_bill_id = a."id"
                order by ar.date desc limit 1 
            ) ar on 0=0
            where a.company_id = {company_id}
                and (a."state" = 'invoice' or left(a.billno, 3) in('ISP','OSP'))
                and date(a.confirmation_date) >= '{date_start}'
                and date(a.confirmation_date) <= '{date_end}'
                and a.billno not like '%[ARCHIVE]%'
                --and coalesce(bl.payer_balance, a.payer_balance, 0) = 0 --sudah lunas baru bayar
                and coalesce(a.payer_balance, 0) = 0 --sudah lunas baru bayar
                and a.payer_id not in (
                    select t.payor_id 
                    from marketing_exception t 
                    inner join marketing_rate t2 on t2."id"=t.rate_id 
                    where t2.company_id={company_id}
                )
                and b.customer_type_wipro not in(
                    select t."name" 
                    from marketing_exception_type t 
                    inner join marketing_rate t2 on t2."id"=t.rate_id 
                    where t2.company_id={company_id}
                )
                and not exists(
                    select 1
                    from marketing_billing t 
                    where t.company_id = a.company_id
                        and t.bill_no = a.billno
                        and t.status = 'calculate'
                )
                --pelunasan maksimal 3 bulan
                and DATE_PART('month', AGE(date(a.bill_date), (case 
                        when coalesce(cn.creditnote_date,ar.advance_date, py.payment_date) > coalesce(ar.advance_date, py.payment_date) 
                        then coalesce(cn.creditnote_date,ar.advance_date, py.payment_date) 
                        else coalesce(ar.advance_date, py.payment_date) 
                    end)
                )) <= 3

                --tidak ada tindakan PCR dan MCU
                and (
                    --patient type selain OPD
                    a.patient_type in('2','3') or
                    --atau tidak ada tindakan PCR 
                    not exists (
                        select 1
                        from sale_order_line t 
                        inner join product_product t2 on t2.id = t.product_id
                        inner join product_template t3 on t3.id = t2.product_tmpl_id
                        where t.billing_id = a.id 
                            and t.type_line in ('BILL','BILLING')
                            and (t3.name->>'en_US' ilike '%MCU%' or t3.name->>'en_US' ilike '%PCR%' or t3.name->>'en_US' ilike '%swab%')
                        limit 1
                    )
                )
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            reference = reference
        )

        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)



        # update fee doctor
        query = """
            update marketing_billing as a set 
                fee_amount = coalesce(df.fee_amount,0.0),
                nett_marketing = (a.bill_amount - coalesce(df.fee_amount,0.0))
            from (
                select t.bill_no,
                    sum(coalesce(t.fee_amount,0.0)) fee_amount
                from marketing_doctor_fee_import t 
                where t.company_id = {company_id}
                group by t.bill_no
            ) df
            where trim(df.bill_no) = trim(a.bill_no)
                and a.company_id = {company_id}
                and a.date_start >= '{date_start}'
                and a.date_end <= '{date_end}'
               -- and a.status in('draft','calculate')
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_cutoff = date_cutoff,
            date_start = date_start,
            date_end = date_end)
        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)



        # ambil total billing for calculate
        query = """
            select a.odoo_letter_id, a.total_cl, b.total_cn
            from (
                select 
                    a.odoo_letter_id,
                    sum(a.bill_amount) total_cl
                from marketing_billing a 
                where a.company_id = {company_id}
                    and a.date_start >= '{date_start}'
                    and a.date_end <= '{date_end}'
                    -- and a.name = '{reference}'
                    and a.odoo_letter_id is not null
                group by a.odoo_letter_id  
            ) a 
            left join lateral(
                select sum(b.total_discount) total_cn
                from account_creditnote b 
                where b.letter_id = a.odoo_letter_id
                    and b.state in('confirm','posted','confirm')
            ) b on 0=0
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            reference = reference
        )
        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)
        result = self.env.cr.dictfetchall()

        if result:
            for line in result:
                # update CN amount hasil prorate
                if (line['total_cl'] or 0) > 0:
                    query = """
                        update marketing_billing as a set  
                            credit_amount = ((a.bill_amount / {total_cl}) * {total_cn})
                        where a.company_id = {company_id}
                            and a.date_start >= '{date_start}'
                            and a.date_end <= '{date_end}'
                            and a.name = '{reference}'
                            and a.odoo_letter_id = {letter_id}
                            and a.status = 'draft'
                    """.format(
                        company_id = company_id,
                        date_start = date_start,
                        date_end = date_end,
                        reference = reference,
                        letter_id = line['odoo_letter_id'],
                        total_cl = line['total_cl'] or 0,
                        total_cn = line['total_cn'] or 0
                    )
                    open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
                    self.env.cr.execute(query)

        # update total referral fee 
        query = """
            update marketing_billing as a set  
                refferal_fee = (case 
                    --jika IGD/IPD ambil presentase
                    when a.bill_amount <= 0 then 0.0
                    when a.patient_type in('2','3') and a.bill_amount <= 25000000 then (2.5 / 100.0 * a.bill_amount)
                    when a.patient_type in('2','3') and a.bill_amount > 25000000 then (5.0 / 100.0 * a.bill_amount)
                    --selain IGD/IPD hitung refferal fee 1 visit = 25rb
                    else 25000.0 end)
            where a.company_id = {company_id}
                and a.date_start >= '{date_start}'
                and a.date_end <= '{date_end}'
               -- and a.status = 'draft'
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            reference = reference
        )
        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        # cek apakah ada company yg belum di mapping payer nya 
        query = """
            select distinct rp.name payor_name 
            from marketing_billing a 
            inner join res_partner rp on rp.id = a.odoo_payer_id
            where a.company_id = {company_id}
                and a.date_start >= '{date_start}'
                and a.date_end <= '{date_end}'
                and a.payer_new = 'new'
                and a.odoo_payer_id not in (
                    select t.payor_id
                    from marketing_exception t 
                    inner join marketing_rate t2 on t2.id = t.rate_id
                    where t2.company_id = {company_id}
                        and t.active = True
                )
                and rp.customer_type_wipro not in (
                    select t.name
                    from marketing_exception_type t 
                    inner join marketing_rate t2 on t2.id = t.rate_id
                    where t2.company_id = {company_id}
                )
                and rp.customer_type_wipro not in ('PERSONAL','HOSPITAL')
                -- belum di mapping ?
                and not exists (
                    select 1
                    from marketing_employee_company t 
                    inner join marketing_employee t2 on t2.id = t.employee_id
                    where t2.company_id = {company_id}
                        and t.active = True
                        and t.payor_id = a.odoo_payer_id
                )
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_cutoff = date_cutoff,
            date_start = date_start,
            date_end = date_end)
        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)
        result = self.env.cr.dictfetchall()

        if result:
            payor_names = ", \n".join(line['payor_name'] for line in result)
            raise UserError(_("Payor {payer_names} belum di mapping.".format(payer_names=payor_names)))


        # update nett final setelah CN
        query = """
            update marketing_billing as a set 
                nett_amount = a.bill_amount - coalesce(a.credit_amount,0.0),
                nett_marketing = (case 
                    when (a.bill_amount - coalesce(a.credit_amount,0.0) - coalesce(a.personal_fee, 0.0) - coalesce(a.fee_amount, 0.0) - coalesce(a.refferal_fee,0)) > 0
                    then (a.bill_amount - coalesce(a.credit_amount,0.0) - coalesce(a.personal_fee, 0.0) - coalesce(a.fee_amount, 0.0) - coalesce(a.refferal_fee,0))
                    else 0 end)
            where a.company_id = {company_id}
                and a.date_start >= '{date_start}'
                and a.date_end <= '{date_end}'
               -- and a.status in('draft','calculate')
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_cutoff = date_cutoff,
            date_start = date_start,
            date_end = date_end)
        open('/opt/odoo16/logs/log_marketing_calculate_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)
       

        # mapping direct marketing/sales 
        query = """
            update marketing_billing as a set 
                marketing_id = b.employee_id
            from marketing_employee_company b 
            inner join marketing_employee c on c.id = b.employee_id
            where a.company_id = {company_id}
                and a.date_start >= '{date_start}'
                and a.date_end <= '{date_end}'
                and a.status in('draft','calculate')
                and b.active = True 
                and b.payor_id = a.odoo_payer_id
                and c.active = True 
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_cutoff = date_cutoff,
            date_start = date_start,
            date_end = date_end)
        open('/opt/odoo16/logs/log_marketing_personal_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


    # @api.multi
    def compute_personal(self):
        company_id = self.company_id.id 
        sync_type = self.company_id.sync_type 
        reference = self.reference
        
        date_cutoff = (self.date_cutoff).strftime('%Y-%m-%d')
        date_start = (self.date_start).strftime('%Y-%m-%d')
        date_end = (self.date_end).strftime('%Y-%m-%d')

        month_start = (self.date_start).month
        month_end = (self.date_end).month

        year_start = (self.date_start).year
        year_end = (self.date_end).year

        if month_start != month_end:
            raise UserError(_("Tanggal awal & akhir masih harus dalam satu periode bulan."))
        if year_start != year_end:
            raise UserError(_("Tanggal awal & akhir masih harus dalam satu periode bulan."))

        if month_start != month_end:
            raise UserError(_("Tanggal awal & akhir masih harus dalam satu periode bulan."))
        if year_start != year_end:
            raise UserError(_("Tanggal awal & akhir masih harus dalam satu periode bulan."))


        # cek sudah pernah di generate belum ?
        query = """
            select count(*) hitung 
            from marketing_personal a 
            where a.company_id = {company_id}
                and a.date_start >= '{date_start}'
                and a.date_end <= '{date_end}'
                and a.state in('confirm','posted')
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_cutoff = date_cutoff,
            date_start = date_start,
            date_end = date_end)
        open('/opt/odoo16/logs/log_marketing_personal_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)
        result = self.env.cr.dictfetchall()

        if result[0]['hitung'] > 0:
            raise UserError(_("Personal fee periode {date_start} s/d {date_end} sudah pernah di generate.".format(date_start=date_start, date_end=date_end)))




        # query compute 
        query = """
            insert into marketing_personal(
                company_id, rate_id, year, month,
                date_start, date_end, is_npwp, npwp, 
                total_amount, total_fee, pph, thp, state
            )
            select 
                {company_id} company_id, 
                a.id rate_id, '{year}' "year", '{month}' "month",
                '{date_start}' date_start, '{date_end}' date_end, 
                a.is_npwp, a.npwp, 0 total_amount, 0 total_fee, 
                a.pph, 0 thp, 'draft' state
            from marketing_rate_personal a 
            where a.active = True
                and a.company_id = {company_id}
                and not exists (
                    select 1
                    from marketing_personal t 
                    where t.company_id = {company_id}
                        and t.rate_id = a.id
                        and t.year = '{year}' 
                        and t.month = '{month}' )        
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_cutoff = date_cutoff,
            date_start = date_start,
            date_end = date_end,
            month = month_start,
            year = year_start)
        open('/opt/odoo16/logs/log_marketing_personal_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        # query update  
        query = """
            update marketing_personal as a set  
                is_npwp = b.is_npwp, 
                npwp = b.npwp,
                pph = b.pph
            from marketing_rate_personal b
            where a.company_id = {company_id}
                and a.year = '{year}'
                and a.month = '{month}'
                and a.state = 'draft'
                and a.rate_id = b.id      
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_cutoff = date_cutoff,
            date_start = date_start,
            date_end = date_end,
            month = month_start,
            year = year_start)
        open('/opt/odoo16/logs/log_marketing_personal_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        
        # hitung personal fee
        query = """
            update marketing_personal_line as a set 
                personal_rate = c.fee_percent,
                personal_fee = coalesce((d.nett_amount * c.fee_percent / 100.0),0)
            from marketing_personal b 
            inner join marketing_rate_personal c on c.id = b.rate_id
            inner join marketing_billing d on d.company_id = b.company_id
            where b.id = a.fee_id
                and d.id = a.billing_id
                and b.company_id = {company_id}
                and b.date_start >= '{date_start}'
                and b.date_end <= '{date_end}'
                and b.state = 'draft'
                
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_cutoff = date_cutoff,
            date_start = date_start,
            date_end = date_end)
        open('/opt/odoo16/logs/log_marketing_personal_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        # insert new line
        query = """
            insert into marketing_personal_line (fee_id, billing_id, personal_rate, personal_fee)
            select b.fee_id, a.id billing_id, 
                   b.fee_percent personal_rate,
                   (b.fee_percent * a.nett_amount / 100.0) personal_fee
            from marketing_billing a 
            inner join (
                select t.company_id, t.date_start, t.date_end, 
                    t.id fee_id, t.rate_id, t3.res_partner_id, 
                    t2.fee_percent
                from marketing_personal t 
                inner join marketing_rate_personal t2 on t2.id = t.rate_id and t2.active = True
                inner join marketing_rate_personal_company t3 on t3.personal_id = t2.id 
                where t.company_id = {company_id}
                    and t.date_start >= '{date_start}'
                    and t.date_end <= '{date_end}'
                    and t.state = 'draft'
            ) b on  b.company_id = a.company_id
                and b.date_start = a.date_start
                and b.date_end = a.date_end
                and b.res_partner_id = a.odoo_payer_id
            where a.company_id = {company_id}
                and a.date_start >= '{date_start}'
                and a.date_end <= '{date_end}'
                and a.status in('draft','calculate')
                and not exists (
                    select 1
                    from marketing_personal_line t 
                    where t.billing_id = a.id
                        and t.fee_id = b.fee_id )
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end)
        open('/opt/odoo16/logs/log_marketing_personal_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        # hitung total personal_fee per billing
        query = """
            update marketing_billing as a set 
                personal_fee = coalesce(b.personal_fee, 0.0),
                nett_marketing = (case 
                    when (a.bill_amount - coalesce(a.credit_amount,0.0) - coalesce(b.personal_fee, 0.0) - coalesce(a.fee_amount, 0.0) - coalesce(a.refferal_fee,0)) > 0
                    then (a.bill_amount - coalesce(a.credit_amount,0.0) - coalesce(b.personal_fee, 0.0) - coalesce(a.fee_amount, 0.0) - coalesce(a.refferal_fee,0))
                    else 0 end)
            from (
                select t2.billing_id, sum(t2.personal_fee) personal_fee
                from marketing_personal t 
                inner join marketing_personal_line t2 on t2.fee_id = t.id 
                where t.state in('draft','confirm', 'posted')
                    and t.company_id = {company_id}
                    and t.date_start >= '{date_start}'
                    and t.date_end <= '{date_end}'
                group by t2.billing_id
            ) b 
            where a.id = b.billing_id
                and a.company_id = {company_id}
                and a.date_start >= '{date_start}'
                and a.date_end <= '{date_end}'
                -- and a.status = 'draft'
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id )
        open('/opt/odoo16/logs/log_marketing_personal_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        # flagging billing temporary as calculate
        query = """
            update marketing_billing as a set 
                status = 'calculate',
                write_date = now(),
                write_uid = {user_id}
            where a.company_id = {company_id}
                and a.date_start >= '{date_start}'
                and a.date_end <= '{date_end}'
                and a.status = 'draft'
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id )
        open('/opt/odoo16/logs/log_marketing_personal_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)

        

        # compute personal fee bruto 
        records = self.env['marketing.personal'].search([
            ('company_id','=', company_id),
            ('year','=', year_start),
            ('month','=', month_start),
            ('state','=', 'draft')])
        if records:
            for record in records:
                record.compute_bruto()



    # @api.multi
    def compute_marketing(self):
        company_id = self.company_id.id 
        sync_type = self.company_id.sync_type 
        reference = self.reference
        
        date_cutoff = (self.date_cutoff).strftime('%Y-%m-%d')
        date_start = (self.date_start).strftime('%Y-%m-%d')
        date_end = (self.date_end).strftime('%Y-%m-%d')

        month_start = (self.date_start).month
        month_end = (self.date_end).month

        year_start = (self.date_start).year
        year_end = (self.date_end).year


        if month_start != month_end:
            raise UserError(_("Tanggal awal & akhir masih harus dalam satu periode bulan."))
        if year_start != year_end:
            raise UserError(_("Tanggal awal & akhir masih harus dalam satu periode bulan."))


        # cek sudah pernah di generate belum ?
        query = """
            select count(*) hitung 
            from marketing_fee a 
            where a.company_id = {company_id}
                and a.date_start >= '{date_start}'
                and a.date_end <= '{date_end}'
                and a.state in('confirm','posted')
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_cutoff = date_cutoff,
            date_start = date_start,
            date_end = date_end)
        open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)
        result = self.env.cr.dictfetchall()

        if result[0]['hitung'] > 0:
            raise UserError(_("Marketing fee periode {date_start} s/d {date_end} sudah pernah di generate.".format(date_start=date_start, date_end=date_end)))


        # insert new header 
        query = """
            insert into marketing_fee(
                company_id, employee_id, year, month,
                date_start, date_end, is_npwp, npwp, 
                total_nett, total_fee, pph, thp, state
            )
            select 
                {company_id} company_id, 
                a.id employee_id, '{year}' "year", '{month}' "month",
                '{date_start}' date_start, '{date_end}' date_end, 
                a.is_npwp, a.npwp, 0 total_nett, 0 total_fee, 
                a.pph, 0 thp, 'draft' state
            from marketing_employee a 
            where a.active = True
                and company_id = {company_id}
                and not exists (
                    select 1
                    from marketing_fee t 
                    where t.company_id = {company_id}
                        and t.employee_id = a.id
                        and t.year = '{year}' 
                        and t.month = '{month}' )        
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_start = date_start,
            date_end = date_end,
            month = month_start,
            year = year_start)
        open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        # update existing header  
        query = """
            update marketing_fee as a set  
                is_npwp = b.is_npwp, 
                npwp = b.npwp,
                pph = b.pph
            from marketing_employee b
            where a.company_id = {company_id}
                and a.year = '{year}'
                and a.month = '{month}'
                and a.state = 'draft'
                and a.employee_id = b.id      
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_start = date_start,
            date_end = date_end,
            month = month_start,
            year = year_start)
        open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        # truncate detail
        # query = """
        #     delete from marketing_fee_bill_rel 
        #     where date_start >= '{date_start}'
        #         and date_end <= '{date_end}'
        #         and not exists (
        #             select 1
        #             from marketing_fee t 
        #             where t.company_id = {company_id}
        #                 and t.date_start >= '{date_start}'
        #                 and t.date_end <= '{date_end}'
        #                 and t.state in ('confirm','posted')
        #                 and t.id = a.fee_id )
        # """.format(
        #     company_id = company_id,
        #     date_start = date_start,
        #     date_end = date_end)
        # open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
        # self.env.cr.execute(query)


        # insert new line
        query = """
            insert into marketing_fee_bill_rel (fee_id, marketing_billing_id)
            select a.id fee_id, b.id marketing_billing_id
            from marketing_fee a
            inner join marketing_billing b 
                on b.marketing_id = a.employee_id 
                and b.company_id = a.company_id
                and b.date_start = a.date_start
                and b.date_end = a.date_end
            where a.company_id = {company_id}
                and a.date_start >= '{date_start}'
                and a.date_end <= '{date_end}'
                and a.state = 'draft'
                and not exists (
                    select 1
                    from marketing_fee_bill_rel t 
                    where t.marketing_billing_id = b.id )
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end)
        open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        # compute personal fee bruto 
        records = self.env['marketing.fee'].search([
            ('company_id','=',company_id),
            ('year','=',year_start),
            ('month','=',month_start),
            ('state','=', 'draft')])
        if records:
            for record in records:
                record.compute_bruto()



    # @api.multi
    def compute_pic(self):
        company_id = self.company_id.id 
        sync_type = self.company_id.sync_type 
        reference = self.reference
        
        date_cutoff = (self.date_cutoff).strftime('%Y-%m-%d')
        date_start = (self.date_start).strftime('%Y-%m-%d')
        date_end = (self.date_end).strftime('%Y-%m-%d')

        month_start = (self.date_start).month
        month_end = (self.date_end).month

        year_start = (self.date_start).year
        year_end = (self.date_end).year

        if date_start > date_end:
            raise UserError(_("Date start can't be greater than date end."))
        

        # if month_start != month_end:
        #     raise UserError(_("Tanggal awal & akhir masih harus dalam satu periode bulan."))
        # if year_start != year_end:
        #     raise UserError(_("Tanggal awal & akhir masih harus dalam satu periode bulan."))


        # cek sudah pernah di generate belum ?
        query = """
            select count(*) hitung 
            from marketing_pic a 
            where a.company_id = {company_id}
                and a.date_start >= '{date_start}'
                and a.date_end <= '{date_end}'
                and a.state in('confirm','posted')
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_cutoff = date_cutoff,
            date_start = date_start,
            date_end = date_end)
        open('/opt/odoo16/logs/log_marketing_pic_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)
        result = self.env.cr.dictfetchall()

        if result[0]['hitung'] > 0:
            raise UserError(_("PIC fee periode {date_start} s/d {date_end} sudah pernah di generate.".format(date_start=date_start, date_end=date_end)))



        # query compute 
        query = """
            insert into marketing_pic(
                company_id, reference, rate_id, year, month,
                date_start, date_end, is_npwp, npwp, 
                total_amount, total_fee, pph, thp, state,
                bank_name, bank_branch, bank_account, 
                bank_client, payment_type, remark
            )
            select 
                {company_id} company_id, {reference} reference,
                a.id rate_id, '{year}' "year", '{month}' "month",
                '{date_start}' date_start, '{date_end}' date_end, 
                a.is_npwp, a.npwp, 0 total_amount, 0 total_fee, 
                a.pph, 0 thp, 'draft' state,
                a.bank_name, a.bank_branch, a.bank_account, 
                a.bank_client, a.payment_type, a.remark
            from marketing_rate_pic a 
            where a.active = True
                and a.company_id = {company_id}
                and not exists (
                    select 1
                    from marketing_pic t 
                    where t.company_id = {company_id}
                        and t.rate_id = a.id
                        and t.year = '{year}' 
                        and t.month = '{month}' )        
        """.format(
            reference = (str(year_end) + str('00' +str(month_end))[-2:]),
            company_id = company_id,
            sync_type = sync_type,
            date_cutoff = date_cutoff,
            date_start = date_start,
            date_end = date_end,
            month = month_end,
            year = year_end)
        open('/opt/odoo16/logs/log_marketing_pic_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        # query update  
        query = """
            update marketing_pic as a set  
                is_npwp = b.is_npwp, 
                npwp = b.npwp,
                pph = b.pph,
                bank_name = b.bank_name, 
                bank_branch = b.bank_branch, 
                bank_account = b.bank_account, 
                bank_client = b.bank_client, 
                payment_type = b.payment_type, 
                remark = b.remark
            from marketing_rate_pic b
            where a.company_id = {company_id}
                and a.year = '{year}'
                and a.month = '{month}'
                and a.state = 'draft'
                and a.rate_id = b.id      
        """.format(
            company_id = company_id,
            sync_type = sync_type,
            date_cutoff = date_cutoff,
            date_start = date_start,
            date_end = date_end,
            month = month_end,
            year = year_end)
        open('/opt/odoo16/logs/log_marketing_pic_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        # truncate detail
        query = """
            delete from marketing_pic_line as a 
            where company_id = {company_id}
                and date_start >= '{date_start}'
                and date_end <= '{date_end}'
                and not exists (
                    select 1
                    from marketing_pic t 
                    where t.company_id = {company_id}
                        and t.date_start >= '{date_start}'
                        and t.date_end <= '{date_end}'
                        and t.state in ('confirm','posted')
                        and t.id = a.fee_id )
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end)
        open('/opt/odoo16/logs/log_marketing_pic_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        # insert new line
        query = """
            insert into marketing_pic_line (
                company_id, 
                date_start,
                date_end,
                fee_id, 
                doctor_id, 
                patient_type, 
                bill_id,
                bill_no, 
                bill_amount,   
                payer_amount, 
                payer_receipt,
                payer_balance,
                payer_id, 
                payer_name,
                payment_type, 
                payment_no,
                payment_date,    
                letter_no,
                letter_date,
                otc_no,  
                store_location,
                exc_feedoctor,
                exc_pharmacy,
                exc_chemo,
                exc_hd,
                exc_dental, 
                exc_total,
                nett_amount,
                rate_id,
                fee_percent,
                fee_amount
            )
            select 
                {company_id} company_id,
                '{date_start}' date_start,
                '{date_end}' date_end,
                pic.fee_id, 
                a.doctor_id, 
                a.patient_type, 
                a.bill_id,
                a.bill_no, 
                a.bill_amount,   
                a.payer_amount, 
                a.payer_receipt,
                a.payer_balance,
                a.payer_id, 
                a.payer_name,
                a.payment_type, 
                a.payment_no,
                a.payment_date,    
                a.letter_no,
                a.letter_date,
                a.otc_no,  
                a.store_location,
                coalesce(df.amount,0) exc_feedoctor,
                coalesce(df2.amount,0) exc_pharmacy,
                coalesce(ch.amount,0) exc_chemo,
                coalesce(hd.amount,0) exc_hd,
                coalesce(dt.amount,0) exc_dental, 
                (coalesce(df.amount,0) + 
                 coalesce(df2.amount,0) + 
                 coalesce(ch.amount,0) + 
                 coalesce(hd.amount,0) + 
                 coalesce(dt.amount,0)
                ) exc_total,

                (case 
                    when (a.payer_receipt - (coalesce(df.amount,0) + 
                     coalesce(df2.amount,0) + 
                     coalesce(ch.amount,0) + 
                     coalesce(hd.amount,0) + 
                     coalesce(dt.amount,0)
                    )) < 0 then 0 else (a.payer_receipt - (coalesce(df.amount,0) + 
                     coalesce(df2.amount,0) + 
                     coalesce(ch.amount,0) + 
                     coalesce(hd.amount,0) + 
                     coalesce(dt.amount,0)
                    )) 
                end) nett_amount,
                pic.id rate_id,
                pic.fee_percent,
                (case 
                    when coalesce(pic.fee_amount,0) > 0 then coalesce(pic.fee_amount,0) 
                    else ( (case 
                        when (a.payer_receipt - (coalesce(df.amount,0) + 
                         coalesce(df2.amount,0) + 
                         coalesce(ch.amount,0) + 
                         coalesce(hd.amount,0) + 
                         coalesce(dt.amount,0)
                        )) < 0 then 0 else (a.payer_receipt - (coalesce(df.amount,0) + 
                         coalesce(df2.amount,0) + 
                         coalesce(ch.amount,0) + 
                         coalesce(hd.amount,0) + 
                         coalesce(dt.amount,0)
                        )) 
                    end) * coalesce(pic.fee_percent,0) / 100.00) 
                end) fee_amount
            from (
                select 
                    bl.primary_doc_id doctor_id, 
                    bl.patient_type, 
                    bl.id bill_id,
                    bl.billno bill_no, 
                    bl.total_amount bill_amount,   
                    bl.payer_amount, 
                    rel.payer_receipt,
                    bl.payer_balance,
                    bl.payer_id, 
                    py."name" payer_name,
                    'RC' payment_type, 
                    rc."name" payment_no,
                    rc.payment_date,    
                    cl.letter_no,
                    cl.letter_date,
                    ''::varchar otc_no,  
                    ''::varchar store_location 
                from account_payment_bill_rel rel 
                inner join account_payment rc on rc.id = rel.account_payment_id
                inner join sale_order_bill bl on bl.id = rel.sale_order_bill_id 
                left join res_partner py on py.id = bl.payer_id
                left join lateral(
                    select cl.id letter_id, cl."date" letter_date, cl."name" letter_no
                    from account_coveringletter_bill_rel clr 
                    inner join account_coveringletter cl on cl."id" = clr.account_coveringletter_id
                    where cl.state in ('confirmed','confirm','paid','done')
                        and clr.sale_order_bill_id = bl.id 
                    limit 1
                ) cl on 0=0
                where rc.payment_type = 'inbound'
                    and rc."state" = 'posted'
                    and rc.company_id = {company_id}
                    and rc.payment_date >= '{date_start}'
                    and rc.payment_date <= '{date_end}'
                    and rc.old_receipt is not True
                    and bl.payer_balance = 0 --yang balance NOL
                    and bl."state" = 'invoice' --harus yg sudah diinvoice
                    and bl.payer_id in (
                        select t2.res_partner_id
                        from marketing_rate_pic t 
                        inner join marketing_rate_pic_company t2 on t2.pic_id = t.id
                        where t.company_id = {company_id}
                            and t.active = True 
                    )
                    
                union all 
                
                select 
                    bl.primary_doc_id doctor_id, 
                    bl.patient_type, 
                    bl.id bill_id,
                    bl.billno bill_no, 
                    bl.total_amount bill_amount,   
                    bl.payer_amount, 
                    rel.payer_receipt,
                    bl.payer_balance,
                    bl.payer_id, 
                    py."name" payer_name,
                    'AR' payment_type, 
                    rc."name" payment_no,
                    rc."date" payment_date,    
                    cl.letter_no,
                    cl.letter_date,
                    ''::varchar otc_no,  
                    ''::varchar store_location 
                from account_payment_bill_rel rel 
                inner join account_advance_realization rc on rc.id = rel.advance_realization_id
                inner join sale_order_bill bl on bl.id = rel.sale_order_bill_id 
                left join res_partner py on py.id = bl.payer_id
                left join lateral(
                    select cl.id letter_id, cl."date" letter_date, cl."name" letter_no
                    from account_coveringletter_bill_rel clr 
                    inner join account_coveringletter cl on cl."id" = clr.account_coveringletter_id
                    where cl.state in ('confirmed','confirm','paid','done')
                        and clr.sale_order_bill_id = bl.id 
                    limit 1
                ) cl on 0=0
                where rc."state" = 'posted'
                    and rc.company_id = {company_id}
                    and rc."date" >= '{date_start}'
                    and rc."date" <= '{date_end}'
                    and rc.old_receipt is not True
                    and bl.payer_balance = 0 --yang balance NOL
                    and bl."state" = 'invoice' --harus yg sudah diinvoice
                    and bl.payer_id in (
                        select t2.res_partner_id
                        from marketing_rate_pic t 
                        inner join marketing_rate_pic_company t2 on t2.pic_id = t.id
                        where t.company_id = {company_id}
                            and t.active = True 
                    )
                    
            ) as a 

            inner join lateral (
                select 
                    mp.id fee_id, pic.id, pic."name", pic.code, pic.fee_percent, 
                    pic.fee_amount, cpic.res_partner_id payor_id
                from marketing_rate_pic_company cpic
                inner join marketing_rate_pic pic on pic.id = cpic.pic_id
                inner join marketing_pic mp on mp.rate_id = pic.id 
                where pic.company_id = {company_id}
                    and pic.active = True 
                    and cpic.res_partner_id = a.payer_id
                    and (
                        pic.patient_type = a.patient_type OR 
                        pic.patient_type in('0')
                    )
                    and mp.date_start >= '{date_start}'
                    and mp.date_end <= '{date_end}'
            ) pic on 0=0

            -- doctor fee
            left join lateral (
                select 
                    sum(case 
                        when coalesce(sol.payer_amount,0) > sol.price_total 
                        then sol.price_total else coalesce(sol.payer_amount,0) 
                    end) amount
                from sale_order_line sol 
                inner join product_category pc on pc.id = sol.service_categ_id
                inner join product_product pp on pp.id = sol.product_id 
                inner join product_template pt on pt.id = pp.product_tmpl_id
                inner join sale_order_bill bl on bl.id = sol.billing_id
                where sol.billing_id = a.bill_id
                    and sol.type_line in ('BILL','BILLING')
                    and pc.sync_id in(2,3,5,11,12,13,36) --yg ada dokter fee
                    and pt.sync_id not in(2969,2970,4941,4555)
                    and bl.primary_doc_id not in(
                        select t."id"
                        from account_analytic_account t  
                        inner join account_analytic_account t2 on t2.id = t.parent_id 
                        where t.sync_wipro_type = 'doctor_internal'
                            and t.active = True 
                            and t.company_id = {company_id}
                            and (t2."name"->>'en_US' ilike '%DENTAL%' or t2."name"->>'en_US' ilike '%DENTIST%') 
                    )
            ) df on 0=0

            -- pharmacy & consumable untuk dr johanned sadikin (TG)
            left join lateral (
                select sum(coalesce(sol.payer_amount,0)) amount
                from sale_order_line sol 
                inner join product_category pc on pc.id = sol.service_categ_id
                inner join product_product pp on pp.id = sol.product_id 
                inner join product_template pt on pt.id = pp.product_tmpl_id
                inner join sale_order_bill bl on bl.id = sol.billing_id
                inner join account_analytic_account rp on rp."id" = bl.primary_doc_id
                where sol.billing_id = a.bill_id
                    and sol.type_line in ('BILL','BILLING')
                    and sol.patient_type = '2'
                    and pc.sync_id in(10,17) --Bed Rentals, Pharmacy, Consumable 
                    and rp."name"->>'en_US' ilike '%JOHANNES%SADIKIN%'
                    and rp.id not in (
                        select t."id"
                        from account_analytic_account t  
                        inner join account_analytic_account t2 on t2.id = t.parent_id 
                        where t.sync_wipro_type = 'doctor_internal'
                            and t.active = True 
                            and t.company_id = {company_id}
                            and (t2."name"->>'en_US' ilike '%DENTAL%' or t2."name"->>'en_US' ilike '%DENTIST%') 
                    )
            ) df2 on 0=0

            --chemoteraphy diluar tindakan pharmacy & consumable johanned sadikin
            left join lateral (
                select sum(coalesce(sol.payer_amount,0)) amount
                from sale_order_line sol 
                inner join product_category pc on pc.id = sol.service_categ_id
                inner join product_product pp on pp.id = sol.product_id 
                inner join product_template pt on pt.id = pp.product_tmpl_id
                inner join sale_order_bill bl on bl.id = sol.billing_id
                inner join account_analytic_account rp on rp."id" = bl.primary_doc_id
                inner join product_category ic on ic.id = sol.product_categ_id
                where sol.billing_id = a.bill_id
                    and sol.type_line in ('BILL','BILLING')
                    and pc.sync_id in(10,17) --Bed Rentals, Pharmacy, Consumable 
                    and (
                        pt.sync_id in(48331) or --KEMOTERAPI MEDICAL MIXING
                        ic.name ilike '%Kemoterapi%'
                    )
                    and (
                        rp."name"->>'en_US' not ilike '%JOHANNES%SADIKIN%' or 
                        sol.patient_type not in ('2')
                    )
                    and rp.id not in(
                        select t."id"
                        from account_analytic_account t  
                        inner join account_analytic_account t2 on t2.id = t.parent_id 
                        where t.sync_wipro_type = 'doctor_internal'
                            and t.active = True 
                            and t.company_id = {company_id}
                            and (t2."name"->>'en_US' ilike '%DENTAL%' or t2."name"->>'en_US' ilike '%DENTIST%') 
                    )
            ) ch on 0=0

            --Haemodalysis
            left join lateral (
                select sum(coalesce(sol.payer_amount,0)) amount
                from sale_order_line sol 
                inner join product_category pc on pc.id = sol.service_categ_id
                inner join product_product pp on pp.id = sol.product_id 
                inner join product_template pt on pt.id = pp.product_tmpl_id
                inner join sale_order_bill bl on bl.id = sol.billing_id
                where sol.billing_id = a.bill_id
                    and sol.type_line in ('BILL','BILLING')
                    and pc.sync_id in(5) --OP/IP Procedure
                    and pt.sync_id in(2969,2970,4941,4555) 
                    and bl.primary_doc_id not in (
                        select t."id"
                        from account_analytic_account t  
                        inner join account_analytic_account t2 on t2.id = t.parent_id 
                        where t.sync_wipro_type = 'doctor_internal'
                            and t.active = True 
                            and t.company_id = {company_id}
                            and (t2."name"->>'en_US' ilike '%DENTAL%' or t2."name"->>'en_US' ilike '%DENTIST%') 
                    )
            ) hd on 0=0

            --Dental
            left join lateral (
                select sum(coalesce(sol.payer_amount,0)) amount
                from sale_order_line sol 
                inner join product_category pc on pc.id = sol.service_categ_id
                inner join product_product pp on pp.id = sol.product_id 
                inner join product_template pt on pt.id = pp.product_tmpl_id
                inner join sale_order_bill bl on bl.id = sol.billing_id
                inner join account_analytic_account rp on rp."id" = bl.primary_doc_id
                where sol.billing_id = a.bill_id
                    and sol.type_line in ('BILL','BILLING')
                    and pc.sync_id in(10,17) 
                    and rp.id in (
                        select t."id"
                        from account_analytic_account t  
                        inner join account_analytic_account t2 on t2.id = t.parent_id 
                        where t.sync_wipro_type = 'doctor_internal'
                            and t.active = True 
                            and t.company_id = {company_id}
                            and (t2."name"->>'en_US' ilike '%DENTAL%' or t2."name"->>'en_US' ilike '%DENTIST%')     
                    )
            ) dt on 0=0

            where pic.payor_id is not null     
                and not exists(
                    select 1 
                    from marketing_pic_line t 
                    where t.bill_id = a.bill_id
                        and t.fee_id = pic.fee_id
                        and t.date_start >= '{date_start}'
                        and t.date_end >= '{date_end}'
                    limit 1
                )  
                and exists (
                    select 1 
                    from marketing_rate_pic_company t 
                    inner join marketing_rate_pic t2 on t2.id = t.pic_id 
                    where t2.active = True 
                        and t2.company_id = {company_id}
                        and t.res_partner_id = a.payer_id
                    limit 1
                )              
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end)
        open('/opt/odoo16/logs/log_marketing_pic_fee.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)

       
        # compute PIC fee bruto 
        records = self.env['marketing.pic'].search([
            ('company_id','=',company_id),
            ('year','=',year_end),
            ('month','=',month_end),
            ('state','=', 'draft')])
        if records:
            for record in records:
                record.compute_bruto()


class MarketingBilling(models.Model):
    _name = 'marketing.billing'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    odoo_letter_id = fields.Many2one('account.coveringletter', string="Odoo Letter No.")
    odoo_bill_id = fields.Many2one('sale.order.bill', string="Odoo Bill No.")
    odoo_patient_id = fields.Many2one('res.partner', string="Odoo Patient")
    odoo_payer_id = fields.Many2one('res.partner', string="Odoo Payer")

    name = fields.Char(string="No Bayar")
    date_start = fields.Date(string="Bill Date Awal")
    date_end = fields.Date(string="Bill Date Akhir")  

    bill_no = fields.Char(string="Bill No")
    bill_date = fields.Date(string="Bill Date")
    payer_id = fields.Integer(string="Payer ID")
    payer_code = fields.Char(string="Payer Code")
    payer_name = fields.Char(string="Payer Name")

    valid_from = fields.Date(string="Valid From")
    valid_to = fields.Date(string="Valid To")
    payer_new = fields.Char(string="Customer Group")

    patient_mrid = fields.Char(string="UHID") 
    patient_name = fields.Char(string="PatientName")
    patient_type = fields.Selection([('1', 'OP'), ('2', 'IP'),('3', 'Emergency'), ('4', 'Daycare'),('5', 'FO'), ('6', 'Pharmacy'),('0', 'Both')],string='Patient Type',index=True)

    letter_no = fields.Char(string="Letter No")
    receipt_date = fields.Date(string="Receipt Date")
    creditnote_date = fields.Date(string="CreditNote Date")
    adjustment_date = fields.Date(string="Adjustment date")                                     
    balance_date = fields.Date(string="Lunas Date")

    bill_amount = fields.Float(string="Bill Amount")
    credit_amount = fields.Float(string="CN Amount")
    nett_amount = fields.Float(string="Nett Amount")

    # personal_fee = (nett_billing - credit_amount) * rate
    personal_fee = fields.Float(string="Personal Fee")
    refferal_fee = fields.Float(string="Refferal Fee")
    fee_amount = fields.Float(string="Doctor Fee") 
    
    # marketing_fee = (nett_billing - credit_note - personal_fee - doctor_fee) * rate
    nett_marketing = fields.Float(string="Nett Marketing")
    marketing_id = fields.Many2one('marketing.employee', string="Marketing Code.")
    status = fields.Selection([('draft', 'Draft'),('calculate','Calculated')], string="Status Trans")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(MarketingBilling,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Billing to Calculate Personal Fee">
                    <sheet>
                            <div class="oe_title">
                            <label string="Billing Detail"/>
                                <h1>
                                    <field name="bill_no" />
                                </h1>
                            </div>
                            <group>
                                <group>
                                    <field name="company_id"/>
                                    
                                    <field name="name"/>
                                    <field name="date_start"/>
                                    <field name="date_end"/>
                                    <field name="bill_date"/>
                                    <field name="payer_code"/>
                                    <field name="payer_name"/>
                                    <field name="valid_from"/>
                                    <field name="valid_to"/>
                                    <field name="payer_new"/>
                                    
                                    <field name="patient_mrid"/>
                                    <field name="patient_name"/>
                                    <field name="patient_type"/>
                                </group>
                                <group>
                                    <field name="letter_no"/>
                                    <field name="receipt_date"/>
                                    <field name="creditnote_date"/>
                                    <field name="adjustment_date"/>                                     
                                    <field name="balance_date"/>
                                    <field name="bill_amount"/>
                                    <field name="credit_amount"/>
                                    <field name="nett_amount"/>
                                    <field name="fee_amount"/>
                                    <field name="personal_fee"/>
                                    <field name="refferal_fee"/>
                                    <field name="status"/>
                                </group>
                            </group>
                    </sheet>
                    <!--div class="oe_chatter">
                        <field name="message_follower_ids" widget="mail_followers"/>
                        <field name="message_ids" widget="mail_thread"/>
                    </div-->
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Billing Calculate for Personal Fee">
                    <field name="company_id"/>
                    <field name="bill_no"/>
                    <field name="bill_date"/>
                    <field name="payer_code"/>
                    <field name="payer_name"/>
                    <field name="name"/>
                    <field name="status"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Billing">
                    <filter name="calculate" string="Calculate" domain="[('status','=', 'calculate')]"/>
                    <filter name="draft" string="Draft" domain="[('status','=', 'draft')]"/>
                    <separator/>
                    <field name="company_id"/>
                    <field name="bill_no"/>
                    <field name="bill_date"/>
                    <field name="payer_code"/>
                    <field name="payer_name"/>
                    <field name="name"/>
                    <field name="status"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class MarketingFee(models.Model):
    _name = 'marketing.fee'
    _rec_name = 'employee_id'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    def _month(orm):
        result = []
        for loop in range(12):
            month = loop + 1
            result += [(str(month), calendar.month_name[month])]
        return result

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    employee_id = fields.Many2one('marketing.employee', string="Employee", required=True)
    employee_level = fields.Selection(related='employee_id.position_id.level')

    position_id = fields.Many2one('marketing.position', string="Job Position", related="employee_id.position_id")
    sales_id = fields.Many2one('marketing.sales', string="Marketing Type", related="employee_id.sales_id")

    year = fields.Integer(string="Year Period", required=True)
    month = fields.Selection(_month, string="Month", required=True)
    date_start = fields.Date(string="Date Start")
    date_end = fields.Date(string="Date End")

    # incentive_old_rate = fields.Float(string="Rate for Old Customer")
    # incentive_old_amount = fields.Float(string="Incentive for Old Customer")
    # incentive_new_rate = fields.Float(string="Rate for New Customer")
    # incentive_new_amount = fields.Float(string="Incentive for New Customer")

    gross_fee = fields.Float(string="Gross Fee", store=True)
    addition = fields.Float(string="Addition", compute='_compute_addition', store=True)
    total_amount = fields.Float(string="Total Billing", store=True)
    total_fee = fields.Float(string="Total Fee", store=True)
    deduction = fields.Float(string="Deduction",compute='_compute_deduction',store=True)
    total_nett = fields.Float(string="Total Nett", store=True)
    
    previous_dpp = fields.Float(string="Previous DPP", store=True)
    previous_pph = fields.Float(string="Previous PPH 21/23", store=True)
    total_dpp = fields.Float(string="DPP", store=True)
    total_dpp_50 = fields.Float(string="DPP 50%", store=True)
    total_pph = fields.Float(string="PPH 21/23", store=True)
    pph = fields.Selection([('0','Without PPH'),('21','PPH 21') ,('23','PPH 23')], string="Tipe PPH")
    thp = fields.Float(string="Take Home Pay", store=True, tracking=True)

    is_npwp = fields.Boolean(string="Is NPWP", readonly=True)
    npwp = fields.Char(string="NPWP", readonly=True)
    remark = fields.Char(string="Remark")

    billing_ids = fields.Many2many('marketing.billing','marketing_fee_bill_rel', 'fee_id', string='Bills')
    fee_line_ids = fields.One2many('marketing.fee.line', 'fee_id', string="Fee Line")
    fee_addition_ids = fields.One2many('marketing.fee.addition', 'fee_id', string="Fee Additional")
    fee_deduction_ids = fields.One2many('marketing.fee.deduction', 'fee_id', string="Fee Deduction")
    
    state = fields.Selection([
        ('draft', 'Draft Fee'),
        ('confirm', 'Confirmed'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled')], string="Status Fee", default='draft', readonly=True, index=True, tracking=True)
    journal_id = fields.Many2one('account.move', string="Journal Entries", readonly=True, tracking=True)

    @api.onchange('employee_id', 'employee_id.company_id')
    def onchange_company(self):
        for record in self:
            record.company_id = record.employee_id.company_id.id


    @api.depends('fee_addition_ids.amount')
    def _compute_addition(self):
        for record in self:
            record.addition = 0
            for line in record.fee_addition_ids:
                record.addition += line.amount


    @api.depends('fee_deduction_ids.amount')
    def _compute_deduction(self):
        for record in self:
            record.deduction = 0
            for line in record.fee_deduction_ids:
                record.deduction -= line.amount

    
    # @api.multi
    def action_print(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/marketing_report/print_marketing_fee?id=' + str(self.id)
        action['target'] = 'new'
        return action


    # @api.multi
    def confirm(self):
        for record in self:
            record.state = 'confirm'
            # for tl in record.fee_line_ids:
            #     tl.state = 'confirm'


    # @api.multi
    def unpost(self):
        for record in self:
            if record.state == 'posted':
                record.state = 'confirm'
                if record.journal_id:
                    move = record.journal_id
                    move.button_cancel()
                    move.unlink()


    # @api.multi
    def cancel(self):
        for record in self:
            record.state = 'cancel'


    # @api.multi
    def set_draft(self):
        for record in self:
            record.state = 'draft'

    # @api.multi
    def unconfirm(self):
        for record in self:
            record.state = 'draft'


    # @api.multi
    def compute_pph21(self, bruto=0, bruto_prev=0, pph21_prev=0):
        tax_level1 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',1)], limit=1)
        tax_level2 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',2)], limit=1)
        tax_level3 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',3)], limit=1)
        tax_level4 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',4)], limit=1)
        tax_level5 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',5)], limit=1)
        
        total_bruto = bruto + bruto_prev
        total_bruto_50 = total_bruto / 2
        pph_21 = pph_lapis_1 = pph_lapis_2 = pph_lapis_3 = pph_lapis_4 = pph_lapis_5 = 0

        # hitung pph lapis 1
        if total_bruto_50 <= tax_level1.tax_dpp_max:
            pph_lapis_1 = (total_bruto_50 * (tax_level1.tax_rate if self.is_npwp else tax_level1.tax_rate2) / 100.0)
        else:
            pph_lapis_1 = (tax_level1.tax_dpp_max * (tax_level1.tax_rate if self.is_npwp else tax_level1.tax_rate2) / 100.0)

        # hitung pph lapis 2
        if total_bruto_50 > tax_level2.tax_dpp_max:
            pph_lapis_2 = ((tax_level2.tax_dpp_max - tax_level1.tax_dpp_max) * (tax_level2.tax_rate if self.is_npwp else tax_level2.tax_rate2) / 100.0)
        elif total_bruto_50 > tax_level1.tax_dpp_max and total_bruto_50 <= tax_level2.tax_dpp_max:
            pph_lapis_2 = ((total_bruto_50 - tax_level1.tax_dpp_max) * (tax_level2.tax_rate if self.is_npwp else tax_level2.tax_rate2) / 100.0)

        # hitung pph lapis 3
        if total_bruto_50 > tax_level3.tax_dpp_max:
            pph_lapis_3 = ((tax_level3.tax_dpp_max - tax_level2.tax_dpp_max) * (tax_level3.tax_rate if self.is_npwp else tax_level3.tax_rate2) / 100.0)
        elif total_bruto_50 > tax_level2.tax_dpp_max and total_bruto_50 <= tax_level3.tax_dpp_max:
            pph_lapis_3 = ((total_bruto_50 - tax_level2.tax_dpp_max) * (tax_level3.tax_rate if self.is_npwp else tax_level3.tax_rate2) / 100.0)

        # hitung pph lapis 4
        if total_bruto_50 > tax_level4.tax_dpp_max:
            pph_lapis_4 = ((tax_level4.tax_dpp_max - tax_level3.tax_dpp_max) * (tax_level4.tax_rate if self.is_npwp else tax_level4.tax_rate2) / 100.0)
        elif total_bruto_50 > tax_level3.tax_dpp_max and total_bruto_50 <= tax_level4.tax_dpp_max:
            pph_lapis_4 = ((total_bruto_50 - tax_level3.tax_dpp_max) * (tax_level4.tax_rate if self.is_npwp else tax_level4.tax_rate2) / 100.0)

        # hitung pph lapis 5
        if total_bruto_50 > tax_level4.tax_dpp_max:
            pph_lapis_5 = ((total_bruto_50 - tax_level4.tax_dpp_max) * (tax_level5.tax_rate if self.is_npwp else tax_level5.tax_rate2) / 100.0)

        # hitung PPh bulan ini adalah total PPH dikurangi PPH yg sudah dibayar bulan sebelumnya
        pph_21 = (pph_lapis_1 + pph_lapis_2 + pph_lapis_3 + pph_lapis_4 + pph_lapis_5) - pph21_prev
        return pph_21


    # @api.multi 
    def compute_bruto(self):
        for record in self:
            if record.state == 'draft':

                company_id = record.company_id.id 
                sync_type = record.company_id.sync_type 
                # date_cutoff = (record.date_cutoff).strftime('%Y-%m-%d')
                date_start = (record.date_start).strftime('%Y-%m-%d')
                date_end = (record.date_end).strftime('%Y-%m-%d')

                month_start = (record.date_start).month
                month_end = (record.date_end).month
                year_start = (record.date_start).year
                year_end = (record.date_end).year

                if month_start != month_end:
                    raise UserError(_("Tanggal awal & akhir masih harus dalam satu periode bulan."))
                if year_start != year_end:
                    raise UserError(_("Tanggal awal & akhir masih harus dalam satu periode bulan."))

                # hitung staff marketing 
                query = """
                    select count(*) hitung
                    from marketing_employee a 
                    inner join marketing_position b on b.id = a.position_id
                    where b."level" = 'staff'
                        and a.company_id = {company_id}
                        and a.active = True
                """.format(
                    company_id = company_id,
                    sync_type = sync_type,
                    date_start = date_start,
                    date_end = date_end,
                    month = month_start,
                    year = year_start)
                open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
                self.env.cr.execute(query)
                result = self.env.cr.dictfetchall()
                total_staff = result[0]['hitung'] or 0

                # hitung marketing Management 
                query = """ 
                    select count(*) hitung
                    from marketing_employee a 
                    inner join marketing_position b on b.id = a.position_id
                    where b."level" = 'management'
                        and a.company_id = {company_id}
                        and a.active = True 
                """.format(
                    company_id = company_id,
                    sync_type = sync_type,
                    date_start = date_start,
                    date_end = date_end,
                    month = month_start,
                    year = year_start)
                open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
                self.env.cr.execute(query)
                result = self.env.cr.dictfetchall()
                total_management = result[0]['hitung'] or 0

                # hapus relasi yang tidak ada di billing
                query = """ 
                    delete from marketing_fee_line as a
                    where fee_id in(
                        select t.id from marketing_fee t
                        where t.company_id = {company_id}
                            and t.date_start >= '{date_start}'
                            and t.date_end <= '{date_end}'
                        )
                        and not exists (
                            select 1 from marketing_billing t
                            where t.id = a.billing_id
                        ) 
                """.format(
                    company_id = company_id,
                    sync_type = sync_type,
                    date_start = date_start,
                    date_end = date_end,
                    month = month_start,
                    year = year_start)
                open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
                self.env.cr.execute(query)

                query = """ 
                    delete from marketing_fee_bill_rel as a
                    where fee_id in(
                        select t.id from marketing_fee t
                        where t.company_id = {company_id}
                            and t.date_start >= '{date_start}'
                            and t.date_end <= '{date_end}')
                        and not exists (
                            select 1 from marketing_billing t
                            where t.id = a.marketing_billing_id) 
                """.format(
                    company_id = company_id,
                    sync_type = sync_type,
                    date_start = date_start,
                    date_end = date_end,
                    month = month_start,
                    year = year_start)
                open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
                self.env.cr.execute(query)




                # insert new dividen for old customer 
                pos = record.employee_id.position_id
                div = self.env['marketing.dividen'].search([('sales_id','=',record.employee_id.sales_id.id)], limit=1, order='id asc')

                query = """
                    insert into marketing_fee_line (
                        fee_id, billing_id, 
                        old_incentive, 
                        old_sharing, 
                        old_rate, 
                        old_amount)
                    select  
                        fee_id, billing_id, 
                        old_incentive, 
                        old_sharing, 
                        old_rate, 
                        old_amount
                    from ( 
                        select 
                            {fee_id} fee_id, 
                            a.id billing_id, 
                            b.rate old_incentive, 
                            {sharing} old_sharing,
                            {rate} old_rate, 
                            (a.nett_marketing * b.rate * {rate} / {sharing}) old_amount
                        from marketing_billing a 
                        inner join lateral (
                            select b.* from marketing_rate b
                            where b.company_id = a.company_id
                        ) b on 0=0
                        inner join res_partner py 
                            on py.id = a.odoo_payer_id
                        where a.company_id = {company_id}
                            and a.date_start >= '{date_start}'
                            and a.date_end <= '{date_end}'
                            and a.payer_new = 'old'
                            and not exists (
                                select 1 
                                from marketing_fee_line t 
                                where t.fee_id = {fee_id}
                                    and t.billing_id = a.id )

                            and a.status = 'calculate'
                            and a.odoo_payer_id not in (
                                select t.payor_id 
                                from marketing_exception t 
                                inner join marketing_rate t2 on t2."id"=t.rate_id 
                                where t2.company_id={company_id}
                            )
                            and py.customer_type_wipro not in(
                                select t."name" 
                                from marketing_exception_type t 
                                inner join marketing_rate t2 on t2."id"=t.rate_id 
                                where t2.company_id={company_id}
                            )
                    ) a 
                    where a.old_amount > 0.0
                """.format(
                    company_id = company_id,
                    sync_type = sync_type,
                    fee_id = record.id, 
                    date_start = date_start,
                    date_end = date_end,
                    sharing = (total_staff if pos.level == 'staff' else total_management),
                    rate = div.rate_old,
                    month = month_start,
                    year = year_start)
                open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
                self.env.cr.execute(query)

                # update existing dividen for old customer
                query = """
                    update marketing_fee_line as t set 
                        old_incentive = b.rate, 
                        old_sharing= {sharing},
                        old_rate={rate} , 
                        old_amount=(a.nett_marketing * b.rate * {rate} / {sharing}) 
                    from marketing_billing a 
                    inner join lateral (
                        select b.* from marketing_rate b
                        where b.company_id = a.company_id
                    ) b on 0=0 
                    inner join res_partner py
                        on py.id = a.odoo_payer_id
                    where a.company_id = {company_id}
                        and a.date_start >= '{date_start}'
                        and a.date_end <= '{date_end}'
                        and a.payer_new = 'old'
                        and a.id = t.billing_id
                        and t.fee_id = {fee_id}
                        and a.status = 'calculate'

                        and a.odoo_payer_id not in (
                            select t.payor_id 
                            from marketing_exception t 
                            inner join marketing_rate t2 on t2."id"=t.rate_id 
                            where t2.company_id={company_id}
                        )
                        and py.customer_type_wipro not in(
                            select t."name" 
                            from marketing_exception_type t 
                            inner join marketing_rate t2 on t2."id"=t.rate_id 
                            where t2.company_id={company_id}
                        )
                """.format(
                    company_id = company_id,
                    sync_type = sync_type,
                    fee_id = record.id, 
                    date_start = date_start,
                    date_end = date_end,
                    sharing = (total_staff if pos.level == 'staff' else total_management),
                    rate = div.rate_old,
                    month = month_start,
                    year = year_start)
                open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
                self.env.cr.execute(query)



                # ambil total incentive untuk new customer
                query = """
                    select 
                        a.odoo_payer_id payer_id, 
                        sum(a.nett_marketing) total_revenue
                    from marketing_billing a 
                    inner join res_partner py on py.id = a.odoo_payer_id
                    where a.company_id = {company_id}
                        and a.date_start >= '{date_start}'
                        and a.date_end <= '{date_end}'
                        and a.payer_new = 'new'

                        and a.status = 'calculate'
                        and a.odoo_payer_id not in (
                            select t.payor_id 
                            from marketing_exception t 
                            inner join marketing_rate t2 on t2."id"=t.rate_id 
                            where t2.company_id={company_id}
                        )
                        and py.customer_type_wipro not in(
                            select t."name" 
                            from marketing_exception_type t 
                            inner join marketing_rate t2 on t2."id"=t.rate_id 
                            where t2.company_id={company_id}
                        )
                    group by a.odoo_payer_id 
                """.format(
                    company_id = company_id,
                    sync_type = sync_type,
                    fee_id = record.id, 
                    date_start = date_start,
                    date_end = date_end )
                open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
                self.env.cr.execute(query)
                results = self.env.cr.dictfetchall()
                    
                # looping per company
                for line_company in results:
                    amount_for_new = line_company['total_revenue'] or 0.0
                    payer_id = line_company['payer_id']

                    query = """
                        select sum(fee) amount
                        from (
                            select 
                                a."sequence", 
                                a.range_min, a.range_max,
                                (case 
                                    when {amount} > a.range_max then (a.range_max-a.range_min)
                                    when {amount} <= a.range_max then ({amount} -a.range_min)
                                    else 0 end) amount,
                                (case 
                                    when {amount} > a.range_max then a.rate
                                    when {amount} <= a.range_max then a.rate
                                    else 0 end) rate,
                                (case 
                                    when {amount} > a.range_max then (a.range_max-a.range_min) * a.rate
                                    when {amount} <= a.range_max then ({amount} -a.range_min) * a.rate
                                    else 0 end) fee
                            from marketing_rate_line a 
                            inner join marketing_rate b on b.id = a.rate_id
                            where b.company_id = {company_id}
                                and a.range_min < {amount}
                       ) as a  
                    """.format(
                        company_id = company_id,
                        amount = amount_for_new)
                    open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
                    self.env.cr.execute(query)
                    result = self.env.cr.dictfetchall()
                    total_incentive = 0
                    if result:
                        total_incentive = result[0]['amount'] or 0


                    # insert dividen for new customer 
                    div1 = self.env['marketing.dividen'].search([('sales_id','=',record.employee_id.sales_id.id), ('is_direct','=',False)], limit=1, order='id asc')
                    div2 = self.env['marketing.dividen'].search([('sales_id','=',record.employee_id.sales_id.id), ('is_direct','=',True)], limit=1, order='id asc')

                    # update new fee
                    query = """
                        update marketing_fee_line as line set 
                            new_direct = (case when a.new_direct=1 then True else False end),
                            new_incentive = a.new_incentive, 
                            new_sharing = a.new_sharing, 
                            new_rate = a.new_rate, 
                            new_amount = a.new_amount
                        from (
                            select 
                                {fee_id} fee_id, 
                                a.id billing_id, 
                                coalesce(c.is_direct,0) new_direct,
                                {total_incentive} new_incentive, 
                                {sharing} new_sharing,
                                (case when coalesce(c.is_direct,0) =1 then {rate_direct} else {rate} end) new_rate, 
                                (a.nett_marketing / {amount_for_new}  * (case
                                    -- jika staf pisahkan logic perhitungan direct sales dan bukan
                                    when '{level}' = 'staff' then (case
                                        --jika direct sales maka langsung bagi ke jumlah direct sales
                                        when coalesce(c.is_direct,0) = 1 
                                        then ({total_incentive} * {rate_direct} / coalesce(b.total_direct_sales,0))
                                        
                                        --selain itu kurangin jumlah direct sales dulu
                                        else ({total_incentive} * {rate} / ({sharing} - coalesce(b.total_direct_sales,0)) ) 
                                    end)
                                    -- jika management langsung di kali dengan rate
                                    else ({total_incentive} * {rate} / {sharing})

                                end)) new_amount
                                -- ({total_incentive} * {rate} / ({sharing} - b.total_direct_sales) ) new_amount
                            from marketing_billing a 
                            inner join res_partner py on py.id = a.odoo_payer_id

                            --hitung jumlah direct sales 
                            left join lateral (
                                select count(*) total_direct_sales
                                from marketing_employee_company t 
                                where t.payor_id = a.odoo_payer_id 
                                    and t.active = True
                            ) b on 0=0

                            -- cek apakah transaksi direct sales ?
                            left join lateral (
                                select 1 is_direct
                                from marketing_employee_company t 
                                where t.payor_id = a.odoo_payer_id
                                    and t.active = True 
                                    and t.employee_id = {employee_id}
                            ) c on 0=0

                            where a.company_id = {company_id}
                                and a.date_start >= '{date_start}'
                                and a.date_end <= '{date_end}'
                                and a.payer_id = {payer_id}
                                and a.payer_new = 'new'
                                and not exists (
                                    select 1 
                                    from marketing_fee_line t 
                                    where t.fee_id = {fee_id}
                                        and t.billing_id = a.id )

                                and a.status = 'calculate'
                                and a.odoo_payer_id not in (
                                    select t.payor_id 
                                    from marketing_exception t 
                                    inner join marketing_rate t2 on t2."id"=t.rate_id 
                                    where t2.company_id={company_id}
                                )
                                and py.customer_type_wipro not in(
                                    select t."name" 
                                    from marketing_exception_type t 
                                    inner join marketing_rate t2 on t2."id"=t.rate_id 
                                    where t2.company_id={company_id}
                                )
                        ) a 
                        where a.new_amount > 0.0
                            and a.fee_id = line.fee_id 
                            and a.billing_id = line.billing_id 
                    """.format(
                        company_id = company_id,
                        payer_id = payer_id, 
                        sync_type = sync_type,
                        fee_id = record.id, 
                        employee_id= record.employee_id.id, 
                        date_start = date_start,
                        date_end = date_end,
                        amount_for_new = amount_for_new,
                        total_incentive = total_incentive,
                        level = pos.level,
                        sharing = (total_staff if pos.level == 'staff' else total_management),
                        rate = (div1.rate_new or 0.0),
                        rate_direct = (div2.rate_new or 0.0), 
                        month = month_start,
                        year = year_start)
                    open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
                    if amount_for_new > 0.0:
                        self.env.cr.execute(query)

                    # insert new fee
                    query = """
                        insert into marketing_fee_line (
                            fee_id, billing_id, new_direct,
                            new_incentive, 
                            new_sharing, 
                            new_rate, 
                            new_amount)
                        select
                            fee_id, billing_id, 
                            (case when new_direct=1 then True else False end) new_direct,
                            new_incentive, 
                            new_sharing, 
                            new_rate, 
                            new_amount
                        from (
                            select 
                                {fee_id} fee_id, 
                                a.id billing_id, 
                                coalesce(c.is_direct,0) new_direct,
                                {total_incentive} new_incentive, 
                                {sharing} new_sharing,
                                (case when coalesce(c.is_direct,0) =1 then {rate_direct} else {rate} end) new_rate, 
                                (a.nett_marketing / {amount_for_new}  * (case
                                    -- jika staf pisahkan logic perhitungan direct sales dan bukan
                                    when '{level}' = 'staff' then (case
                                        --jika direct sales maka langsung bagi ke jumlah direct sales
                                        when coalesce(c.is_direct,0) = 1 
                                        then ({total_incentive} * {rate_direct} / coalesce(b.total_direct_sales,0))
                                        
                                        --selain itu kurangin jumlah direct sales dulu
                                        else ({total_incentive} * {rate} / ({sharing} - coalesce(b.total_direct_sales,0)) ) 
                                    end)
                                    -- jika management langsung di kali dengan rate
                                    else ({total_incentive} * {rate} / {sharing})

                                end)) new_amount
                                -- ({total_incentive} * {rate} / ({sharing} - b.total_direct_sales) ) new_amount
                            from marketing_billing a 
                            inner join res_partner py on py.id = a.odoo_payer_id

                            --hitung jumlah direct sales 
                            left join lateral (
                                select count(*) total_direct_sales
                                from marketing_employee_company t 
                                where t.payor_id = a.odoo_payer_id 
                                    and t.active = True
                            ) b on 0=0

                            -- cek apakah transaksi direct sales ?
                            left join lateral (
                                select 1 is_direct
                                from marketing_employee_company t 
                                where t.payor_id = a.odoo_payer_id
                                    and t.active = True 
                                    and t.employee_id = {employee_id}
                            ) c on 0=0

                            where a.company_id = {company_id}
                                and a.date_start >= '{date_start}'
                                and a.date_end <= '{date_end}'
                                and a.payer_id = {payer_id}
                                and a.payer_new = 'new'
                                and not exists (
                                    select 1 
                                    from marketing_fee_line t 
                                    where t.fee_id = {fee_id}
                                        and t.billing_id = a.id )

                                and a.status = 'calculate'
                                and a.odoo_payer_id not in (
                                    select t.payor_id 
                                    from marketing_exception t 
                                    inner join marketing_rate t2 on t2."id"=t.rate_id 
                                    where t2.company_id={company_id}
                                )
                                and py.customer_type_wipro not in(
                                    select t."name" 
                                    from marketing_exception_type t 
                                    inner join marketing_rate t2 on t2."id"=t.rate_id 
                                    where t2.company_id={company_id}
                                )
                        ) a 
                        where a.new_amount > 0.0
                    """.format(
                        company_id = company_id,
                        payer_id = payer_id, 
                        sync_type = sync_type,
                        fee_id = record.id, 
                        employee_id= record.employee_id.id, 
                        date_start = date_start,
                        date_end = date_end,
                        amount_for_new = amount_for_new,
                        total_incentive = total_incentive,
                        level = pos.level,
                        sharing = (total_staff if pos.level == 'staff' else total_management),
                        rate = (div1.rate_new or 0.0),
                        rate_direct = (div2.rate_new or 0.0), 
                        month = month_start,
                        year = year_start)
                    open('/opt/odoo16/logs/log_marketing_fee.log','a+').write('\n\n' + str(query))
                    if amount_for_new > 0.0:
                        self.env.cr.execute(query)


                # hitung PPH 21/23
                tax_pph23 = self.env['doctor.tax'].search([('company_id', '=', record.company_id.id), ('tax_type','=','pph23')], limit=1)
                total_dpp = 0
                total_pph = 0 
                total_fee = 0 
                thp = 0 

                previous_dpp = 0 
                previous_pph = 0 

                record.pph = record.employee_id.pph
                record.npwp = record.employee_id.npwp
                record.is_npwp = record.employee_id.is_npwp
                record.total_amount = sum(line.nett_marketing for line in record.fee_line_ids)
                record.gross_fee = sum(line.old_amount for line in record.fee_line_ids)
                record.gross_fee += sum(line.new_amount for line in record.fee_line_ids)
                record.addition = sum(line.amount for line in record.fee_addition_ids)
                record.total_fee = (record.gross_fee or 0.0) + (record.addition or 0.0)
                record.deduction = sum(line.amount for line in record.fee_deduction_ids)
                record.total_dpp = (record.total_fee or 0.0) + (record.addition or 0.0)
                record.total_dpp_50 = (record.total_dpp or 0.00) / 2


                # hitung previous DPP & PPH
                previous = self.env['marketing.fee'].search([
                    ('employee_id', '=', record.employee_id.id),
                    ('company_id', '=', record.company_id.id),
                    ('year', '=', record.year), 
                    ('month', '<', record.month),
                    ('state', 'in', ['confirm','confirmed','posted'])
                ])
                if previous:
                    for prev in previous:
                        previous_dpp += prev.total_dpp 
                        previous_pph += prev.total_pph


                record.previous_dpp = previous_dpp or 0.0 
                record.previous_pph = previous_pph or 0.0

                total_dpp = record.total_dpp + record.previous_dpp
                total_dpp_50 = total_dpp / 2  
                total_pph = record.total_pph + record.previous_pph

                # hitung PPH 21 based on taring & previous PPH 
                if record.pph in['21']:
                    # compute_pph21(self, bruto=0, bruto_prev=0, pph21_prev=0)
                    record.total_pph = record.compute_pph21(bruto=record.total_dpp, bruto_prev=record.previous_dpp, pph21_prev=record.previous_pph)

                # 2% untuk WP yg memiliki NPWP, 4% untuk yg tidak ada NPWP
                elif record.pph in['23']:
                    record.total_pph = (record.total_dpp *  ((tax_pph23.tax_rate if record.is_npwp else tax_pph23.tax_rate2)) / 100.0)

                # tidak ada PPH 
                else:
                    record.total_pph = 0.0 

                record.thp = record.total_fee - record.total_pph - record.deduction

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(MarketingFee,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Marketing Fee" delete="false">
                    <field name="year"/>
                    <field name="month"/>
                    <field name="employee_id"/>
                    <field name="thp" sum="Total" widget="monetary"/>
                    <field name="state"/>
                    <field name="company_id"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search..">
                    <filter name="draft" string="Draft" domain="[('state','=', 'draft')]" help="Draft"/>
                    <filter name="confirm" string="Confirm" domain="[('state','=', 'confirm')]" help="Confirm"/>
                    <filter name="posted" string="Posted" domain="[('state','=', 'posted')]" help="Posted"/>
                    <separator/>
                    <filter name="thp" string="THP" domain="[('thp','>', 0)]" help="POT/GP"/>
                    <separator/>
                    <field name="employee_id"/>
                </search>"""
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class MarketingFeeLine(models.Model):
    _name = 'marketing.fee.line'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    fee_id = fields.Many2one('marketing.fee', string="Fee ID")
    billing_id = fields.Many2one('marketing.billing', string="Billing")
    bill_no = fields.Char(string="Bill No.", related="billing_id.bill_no")
    bill_date = fields.Date(string="Bill Date", related="billing_id.bill_date")
    payer_id = fields.Many2one('res.partner', string="Payer", related="billing_id.odoo_payer_id")
    payer_name = fields.Char(string="Payer Name", related="billing_id.payer_name")
    payer_new = fields.Char(string="Payer Group", related="billing_id.payer_new")
    nett_marketing = fields.Float(string="Nett For Marketing", related="billing_id.nett_marketing")
    old_incentive = fields.Float(string="Incentive for Old")
    old_sharing = fields.Float(string="Sharing for Old")
    old_rate = fields.Float(string="Rate for Old")
    old_amount = fields.Float(string="Fee for Old")

    new_direct = fields.Boolean(string="Is Direct")
    new_incentive = fields.Float(string="Incentive for New")
    new_sharing = fields.Float(string="Sharing for New")
    new_rate = fields.Float(string="Rate for New")
    new_amount = fields.Float(string="Fee for New")


class MarketingFeeAddition(models.Model):
    _name = 'marketing.fee.addition'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date


    fee_id = fields.Many2one('marketing.fee', string="Fee ID")
    name = fields.Char(string="Description")
    amount = fields.Float(string="Amount")
    date = fields.Date(string="Date")


class MarketingFeeDeduction(models.Model):
    _name = 'marketing.fee.deduction'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date


    fee_id = fields.Many2one('marketing.fee', string="Fee ID")
    name = fields.Char(string="Description")
    amount = fields.Float(string="Amount")
    date = fields.Date(string="Date")


class MarketingPersonal(models.Model):
    _name = 'marketing.personal'
    _rec_name = 'rate_id'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.company.id

    def _month(orm):
        result = []
        for loop in range(12):
            month = loop + 1
            result += [(str(month), calendar.month_name[month])]
        return result

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    rate_id = fields.Many2one('marketing.rate.personal', string="Personal Name.", required=True)
    payer_name = fields.Char(related="rate_id.payer_name")

    year = fields.Integer(string="Year Period", required=True)
    month = fields.Selection(_month, string="Month", required=True)
    date_start = fields.Date(string="Date Start")
    date_end = fields.Date(string="Date End")
    
    total_amount = fields.Float(string="Total Billing", store=True)
    total_fee = fields.Float(string="Total Fee", store=True)
    
    previous_dpp = fields.Float(string="Previous DPP", store=True)
    previous_pph = fields.Float(string="Previous PPH 21/23", store=True)
    total_dpp = fields.Float(string="DPP", store=True)
    total_dpp_50 = fields.Float(string="DPP 50%", store=True)
    total_pph = fields.Float(string="PPH 21/23", store=True)
    pph = fields.Selection([('0','Without PPH'),('21','PPH 21') ,('23','PPH 23')], string="Tipe PPH")
    thp = fields.Float(string="Take Home Pay", store=True, tracking=True)

    is_npwp = fields.Boolean(string="Is NPWP", readonly=True)
    npwp = fields.Char(string="NPWP", readonly=True)
    remark = fields.Char(string="Remark")

    fee_line_ids = fields.One2many('marketing.personal.line', 'fee_id', string="Fee Line")
    state = fields.Selection([
        ('draft', 'Draft Fee'),
        ('confirm', 'Confirmed'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled')], string="Status Fee", default='draft', readonly=True, index=True, tracking=True)
    journal_id = fields.Many2one('account.move', string="Journal Entries", readonly=True, tracking=True)

    @api.onchange('rate_id', 'rate_id.company_id')
    def onchange_company(self):
        for record in self:
            record.company_id = record.rate_id.company_id.id


   
    # @api.multi
    def action_print(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/marketing_report/print_personal_fee?id=' + str(self.id)
        action['target'] = 'new'
        return action



    # @api.multi
    def confirm(self):
        for record in self:
            record.state = 'confirm'
            for tl in record.fee_line_ids:
                tl.state = 'confirm'


    # @api.multi
    def unpost(self):
        for record in self:
            if record.state == 'posted':
                record.state = 'confirm'
                if record.journal_id:
                    move = record.journal_id
                    move.button_cancel()
                    move.unlink()


    # @api.multi
    def cancel(self):
        for record in self:
            record.state = 'cancel'


    # @api.multi
    def set_draft(self):
        for record in self:
            record.state = 'draft'

    # @api.multi
    def unconfirm(self):
        for record in self:
            record.state = 'draft'


    # @api.multi
    def compute_pph21(self, bruto=0, bruto_prev=0, pph21_prev=0):
        tax_level1 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',1)], limit=1)
        tax_level2 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',2)], limit=1)
        tax_level3 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',3)], limit=1)
        tax_level4 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',4)], limit=1)
        tax_level5 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',5)], limit=1)
        
        total_bruto = bruto + bruto_prev
        total_bruto_50 = total_bruto / 2
        pph_21 = pph_lapis_1 = pph_lapis_2 = pph_lapis_3 = pph_lapis_4 = pph_lapis_5 = 0

        # hitung pph lapis 1
        if total_bruto_50 <= tax_level1.tax_dpp_max:
            pph_lapis_1 = (total_bruto_50 * (tax_level1.tax_rate if self.is_npwp else tax_level1.tax_rate2) / 100.0)
        else:
            pph_lapis_1 = (tax_level1.tax_dpp_max * (tax_level1.tax_rate if self.is_npwp else tax_level1.tax_rate2) / 100.0)

        # hitung pph lapis 2
        if total_bruto_50 > tax_level2.tax_dpp_max:
            pph_lapis_2 = ((tax_level2.tax_dpp_max - tax_level1.tax_dpp_max) * (tax_level2.tax_rate if self.is_npwp else tax_level2.tax_rate2) / 100.0)
        elif total_bruto_50 > tax_level1.tax_dpp_max and total_bruto_50 <= tax_level2.tax_dpp_max:
            pph_lapis_2 = ((total_bruto_50 - tax_level1.tax_dpp_max) * (tax_level2.tax_rate if self.is_npwp else tax_level2.tax_rate2) / 100.0)

        # hitung pph lapis 3
        if total_bruto_50 > tax_level3.tax_dpp_max:
            pph_lapis_3 = ((tax_level3.tax_dpp_max - tax_level2.tax_dpp_max) * (tax_level3.tax_rate if self.is_npwp else tax_level3.tax_rate2) / 100.0)
        elif total_bruto_50 > tax_level2.tax_dpp_max and total_bruto_50 <= tax_level3.tax_dpp_max:
            pph_lapis_3 = ((total_bruto_50 - tax_level2.tax_dpp_max) * (tax_level3.tax_rate if self.is_npwp else tax_level3.tax_rate2) / 100.0)

        # hitung pph lapis 4
        if total_bruto_50 > tax_level4.tax_dpp_max:
            pph_lapis_4 = ((tax_level4.tax_dpp_max - tax_level3.tax_dpp_max) * (tax_level4.tax_rate if self.is_npwp else tax_level4.tax_rate2) / 100.0)
        elif total_bruto_50 > tax_level3.tax_dpp_max and total_bruto_50 <= tax_level4.tax_dpp_max:
            pph_lapis_4 = ((total_bruto_50 - tax_level3.tax_dpp_max) * (tax_level4.tax_rate if self.is_npwp else tax_level4.tax_rate2) / 100.0)

        # hitung pph lapis 5
        if total_bruto_50 > tax_level4.tax_dpp_max:
            pph_lapis_5 = ((total_bruto_50 - tax_level4.tax_dpp_max) * (tax_level5.tax_rate if self.is_npwp else tax_level5.tax_rate2) / 100.0)

        # hitung PPh bulan ini adalah total PPH dikurangi PPH yg sudah dibayar bulan sebelumnya
        pph_21 = (pph_lapis_1 + pph_lapis_2 + pph_lapis_3 + pph_lapis_4 + pph_lapis_5) - pph21_prev
        return pph_21


    # @api.multi 
    def compute_bruto(self):
        for record in self:
            if record.state == 'draft':
                tax_pph23 = self.env['doctor.tax'].search([
                    ('company_id', '=', record.company_id.id), 
                    ('tax_type','=','pph23')], limit=1)

                total_dpp = 0
                total_pph = 0 
                total_fee = 0 
                thp = 0 

                previous_dpp = 0 
                previous_pph = 0 

                # hitung additional & deduction 
                # record.addition = sum(line.amount for line in record.fee_addition_ids)
                # record.deduction = sum(line.amount for line in record.line.fee_deduction_ids)

                record.total_amount = sum(line.bill_amount for line in record.fee_line_ids)
                record.total_fee = sum(line.personal_fee for line in record.fee_line_ids)
                record.total_dpp = record.total_fee or 0.0 
                record.total_dpp_50 = (record.total_fee or 0.00) / 2


                # hitung previous DPP & PPH
                previous = self.env['marketing.personal'].search([
                    ('rate_id', '=', record.rate_id.id),
                    ('company_id', '=', record.company_id.id),
                    ('year', '=', record.year), 
                    ('month', '<', record.month),
                    ('state', 'in', ['confirm','confirmed','posted'])
                ])
                if previous:
                    for prev in previous:
                        previous_dpp += prev.total_dpp 
                        previous_pph += prev.total_pph


                record.previous_dpp = previous_dpp or 0.0 
                record.previous_pph = previous_pph or 0.0

                total_dpp = record.total_dpp + record.previous_dpp
                total_dpp_50 = total_dpp / 2  
                total_pph = record.total_pph + record.previous_pph

                # hitung PPH 21 based on taring & previous PPH 
                if record.pph in['21']:
                    # compute_pph21(self, bruto=0, bruto_prev=0, pph21_prev=0)
                    record.total_pph = record.compute_pph21(bruto=record.total_dpp, bruto_prev=record.previous_dpp, pph21_prev=record.previous_pph)

                # 2% untuk WP yg memiliki NPWP, 4% untuk yg tidak ada NPWP
                elif record.pph in['23']:
                    record.total_pph = (record.total_dpp *  ((tax_pph23.tax_rate if record.is_npwp else tax_pph23.tax_rate2)) / 100.0)

                # tidak ada PPH 
                else:
                    record.total_pph = 0.0 

                record.thp = record.total_fee - record.total_pph 

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(MarketingPersonal,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Personal Fee" delete="false">
                    <field name="year"/>
                    <field name="month"/>
                    <field name="rate_id"/>
                    <field name="thp" sum="Total" widget="monetary"/>
                    <field name="state"/>
                    <field name="company_id"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search..">
                    <filter name="draft" string="Draft" domain="[('state','=', 'draft')]" help="Draft"/>
                    <filter name="confirm" string="Confirm" domain="[('state','=', 'confirm')]" help="Confirm"/>
                    <filter name="posted" string="Posted" domain="[('state','=', 'posted')]" help="Posted"/>
                    <separator/>
                    <filter name="thp" string="THP" domain="[('thp','>', 0)]" help="POT/GP"/>
                    <separator/>
                    <field name="rate_id"/>
                </search>"""
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class MarketingPersonalLine(models.Model):
    _name = 'marketing.personal.line'
    _rec_name = 'bill_no'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    fee_id = fields.Many2one('marketing.personal', string="Fee No.")
    billing_id = fields.Many2one('marketing.billing', string="Billing")

    bill_no = fields.Char(related="billing_id.bill_no")
    bill_date = fields.Date(related="billing_id.bill_date")
    payer_name = fields.Char(related="billing_id.payer_name")
    patient_name = fields.Char(related="billing_id.patient_name")
    bill_amount = fields.Float(related="billing_id.bill_amount")
    credit_amount = fields.Float(related="billing_id.credit_amount")
    nett_amount = fields.Float(related="billing_id.nett_amount")

    personal_rate = fields.Float(string="Personal Rate")
    personal_fee = fields.Float(string="Personal Fee")


class MarketingPIC(models.Model):
    _name = 'marketing.pic'
    _rec_name = 'rate_id'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.company.id

    def _month(orm):
        result = []
        for loop in range(12):
            month = loop + 1
            result += [(str(month), calendar.month_name[month])]
        return result

    reference = fields.Char(string="Ref No.")
    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    rate_id = fields.Many2one('marketing.rate.pic',string="PIC No.",required=True)
    payer_name = fields.Char(related="rate_id.payer_name")

    year = fields.Integer(string="Year Period", required=False)
    month = fields.Selection(_month, string="Month", required=True)
    date_start = fields.Date(string="Date Start")
    date_end = fields.Date(string="Date End")
    
    total_amount = fields.Float(string="Total Billing", store=True)
    total_fee = fields.Float(string="Total Fee", store=True)
    
    previous_dpp = fields.Float(string="Previous DPP", store=True)
    previous_pph = fields.Float(string="Previous PPH 21/23", store=True)
    total_dpp = fields.Float(string="DPP", store=True)
    total_dpp_50 = fields.Float(string="DPP 50%", store=True)
    total_pph = fields.Float(string="PPH 21/23", store=True)
    pph = fields.Selection([('0','Without PPH'),('21','PPH 21') ,('23','PPH 23')], string="Tipe PPH")
    thp = fields.Float(string="Take Home Pay", store=True, tracking=True)

    is_npwp = fields.Boolean(string="Is NPWP", readonly=True)
    npwp = fields.Char(string="NPWP", readonly=True)

    bank_name = fields.Char(string="Bank Name")
    bank_branch = fields.Char(string="Bank Branch")
    bank_account = fields.Char(string="Bank Account No.")
    bank_client = fields.Char(string="Bank Account Name")
    
    payment_type = fields.Selection([('TRANSFER','BANK TRANSFER'), ('CASH','CASH')], string="Payment Method")
    remark = fields.Char(string="Remark")

    fee_line_ids = fields.One2many('marketing.pic.line', 'fee_id', string="Fee Line")
    state = fields.Selection([
        ('draft', 'Draft Fee'),
        ('confirm', 'Confirmed'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled')], string="Status Fee", default='draft', readonly=True, index=True, tracking=True)
    journal_id = fields.Many2one('account.move', string="Journal Entries", readonly=True, tracking=True)

    @api.onchange('rate_id', 'rate_id.company_id')
    def onchange_company(self):
        for record in self:
            record.company_id = record.rate_id.company_id.id

   
    # @api.multi
    def action_print(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/marketing_report/print_pic_fee?id=' + str(self.id)
        action['target'] = 'new'
        return action


    # @api.multi
    def confirm(self):
        for record in self:
            record.state = 'confirm'
            for tl in record.fee_line_ids:
                tl.state = 'confirm'


    # @api.multi
    def unpost(self):
        for record in self:
            if record.state == 'posted':
                record.state = 'confirm'
                if record.journal_id:
                    move = record.journal_id
                    move.button_cancel()
                    move.unlink()


    # @api.multi
    def cancel(self):
        for record in self:
            record.state = 'cancel'


    # @api.multi
    def set_draft(self):
        for record in self:
            record.state = 'draft'

    # @api.multi
    def unconfirm(self):
        for record in self:
            record.state = 'draft'


    # @api.multi
    def compute_pph21(self, bruto=0, bruto_prev=0, pph21_prev=0):
        tax_level1 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',1)], limit=1)
        tax_level2 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',2)], limit=1)
        tax_level3 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',3)], limit=1)
        tax_level4 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',4)], limit=1)
        tax_level5 = self.env['doctor.tax'].search([('company_id', '=', self.company_id.id), ('tax_type','=','pph21'), ('tax_level','=',5)], limit=1)
        
        total_bruto = bruto + bruto_prev
        total_bruto_50 = total_bruto / 2
        pph_21 = pph_lapis_1 = pph_lapis_2 = pph_lapis_3 = pph_lapis_4 = pph_lapis_5 = 0

        # hitung pph lapis 1
        if total_bruto_50 <= tax_level1.tax_dpp_max:
            pph_lapis_1 = (total_bruto_50 * (tax_level1.tax_rate if self.is_npwp else tax_level1.tax_rate2) / 100.0)
        else:
            pph_lapis_1 = (tax_level1.tax_dpp_max * (tax_level1.tax_rate if self.is_npwp else tax_level1.tax_rate2) / 100.0)

        # hitung pph lapis 2
        if total_bruto_50 > tax_level2.tax_dpp_max:
            pph_lapis_2 = ((tax_level2.tax_dpp_max - tax_level1.tax_dpp_max) * (tax_level2.tax_rate if self.is_npwp else tax_level2.tax_rate2) / 100.0)
        elif total_bruto_50 > tax_level1.tax_dpp_max and total_bruto_50 <= tax_level2.tax_dpp_max:
            pph_lapis_2 = ((total_bruto_50 - tax_level1.tax_dpp_max) * (tax_level2.tax_rate if self.is_npwp else tax_level2.tax_rate2) / 100.0)

        # hitung pph lapis 3
        if total_bruto_50 > tax_level3.tax_dpp_max:
            pph_lapis_3 = ((tax_level3.tax_dpp_max - tax_level2.tax_dpp_max) * (tax_level3.tax_rate if self.is_npwp else tax_level3.tax_rate2) / 100.0)
        elif total_bruto_50 > tax_level2.tax_dpp_max and total_bruto_50 <= tax_level3.tax_dpp_max:
            pph_lapis_3 = ((total_bruto_50 - tax_level2.tax_dpp_max) * (tax_level3.tax_rate if self.is_npwp else tax_level3.tax_rate2) / 100.0)

        # hitung pph lapis 4
        if total_bruto_50 > tax_level4.tax_dpp_max:
            pph_lapis_4 = ((tax_level4.tax_dpp_max - tax_level3.tax_dpp_max) * (tax_level4.tax_rate if self.is_npwp else tax_level4.tax_rate2) / 100.0)
        elif total_bruto_50 > tax_level3.tax_dpp_max and total_bruto_50 <= tax_level4.tax_dpp_max:
            pph_lapis_4 = ((total_bruto_50 - tax_level3.tax_dpp_max) * (tax_level4.tax_rate if self.is_npwp else tax_level4.tax_rate2) / 100.0)

        # hitung pph lapis 5
        if total_bruto_50 > tax_level4.tax_dpp_max:
            pph_lapis_5 = ((total_bruto_50 - tax_level4.tax_dpp_max) * (tax_level5.tax_rate if self.is_npwp else tax_level5.tax_rate2) / 100.0)

        # hitung PPh bulan ini adalah total PPH dikurangi PPH yg sudah dibayar bulan sebelumnya
        pph_21 = (pph_lapis_1 + pph_lapis_2 + pph_lapis_3 + pph_lapis_4 + pph_lapis_5) - pph21_prev
        return pph_21


    # @api.multi
    def compute_bruto(self):
        for record in self:
            if record.state == 'draft':
                tax_pph23 = self.env['doctor.tax'].search([
                    ('company_id', '=', record.company_id.id), 
                    ('tax_type','=','pph23')], limit=1)

                # query remapping line to header PIC
                query = """
                    update marketing_pic_line as a set 
                        fee_id = b.id
                    from marketing_pic b 
                    where b.company_id = a.company_id
                        and b.date_start = a.date_start
                        and b.date_end = a.date_end
                        and b.rate_id = a.rate_id
                        and b.id = {fee_id}
                """.format(fee_id=record.id)
                open('/opt/odoo16/logs/log_marketing_pic_fee.log','a+').write('\n\n' + str(query))
                self.env.cr.execute(query)

                # query update parameter PIC
                query = """
                    update marketing_pic as a set  
                        is_npwp = b.is_npwp, 
                        npwp = b.npwp,
                        bank_name = b.bank_name, 
                        bank_branch = b.bank_branch, 
                        bank_account = b.bank_account, 
                        bank_client = b.bank_client, 
                        payment_type = b.payment_type, 
                        remark = b.remark
                    from marketing_rate_pic b
                    where a.company_id = {company_id}
                        and a.rate_id = b.id
                        and a.id = {fee_id}   
                """.format(
                    company_id = record.company_id.id,
                    fee_id = record.id)
                open('/opt/odoo16/logs/log_marketing_pic_fee.log','a+').write('\n\n' + str(query))
                self.env.cr.execute(query)


                total_dpp = 0
                total_pph = 0 
                total_fee = 0 
                thp = 0 

                previous_dpp = 0 
                previous_pph = 0 

                # hitung additional & deduction 
                # record.addition = sum(line.amount for line in record.fee_addition_ids)
                # record.deduction = sum(line.amount for line in record.line.fee_deduction_ids)

                record.pph = record.rate_id.pph 
                record.npwp = record.rate_id.npwp
                record.is_npwp = record.rate_id.is_npwp
                record.total_amount = sum(line.bill_amount for line in record.fee_line_ids)
                record.total_fee = sum(line.fee_amount for line in record.fee_line_ids)
                record.total_dpp = record.total_fee or 0.0 
                record.total_dpp_50 = (record.total_fee or 0.00) / 2


                # hitung previous DPP & PPH
                previous = self.env['marketing.pic'].search([
                    ('rate_id', '=', record.rate_id.id),
                    ('company_id', '=', record.company_id.id),
                    ('year', '=', record.year), 
                    ('month', '<', record.month),
                    ('state', 'in', ['confirm','confirmed','posted'])
                ])
                if previous:
                    for prev in previous:
                        previous_dpp += prev.total_dpp 
                        previous_pph += prev.total_pph


                record.previous_dpp = previous_dpp or 0.0 
                record.previous_pph = previous_pph or 0.0

                total_dpp = record.total_dpp + record.previous_dpp
                total_dpp_50 = total_dpp / 2  
                total_pph = record.total_pph + record.previous_pph

                # hitung PPH 21 based on taring & previous PPH 
                if record.pph in['21']:
                    # compute_pph21(self, bruto=0, bruto_prev=0, pph21_prev=0)
                    record.total_pph = record.compute_pph21(bruto=record.total_dpp, bruto_prev=record.previous_dpp, pph21_prev=record.previous_pph)

                # 2% untuk WP yg memiliki NPWP, 4% untuk yg tidak ada NPWP
                elif record.pph in['23']:
                    record.total_pph = (record.total_dpp *  ((tax_pph23.tax_rate if record.is_npwp else tax_pph23.tax_rate2)) / 100.0)

                # tidak ada PPH 
                else:
                    record.total_pph = 0.0 

                record.thp = record.total_fee - record.total_pph


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(MarketingPIC,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="PIC Fee" delete="false">
                    <field name="reference"/>
                    <field name="year"/>
                    <field name="month"/>
                    <field name="rate_id"/>
                    <field name="payer_name"/>
                    <field name="thp" sum="Total" widget="monetary"/>
                    <field name="state"/>
                    <field name="company_id"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search..">
                    <filter name="draft" string="Draft" domain="[('state','=', 'draft')]" help="Draft"/>
                    <filter name="confirm" string="Confirm" domain="[('state','=', 'confirm')]" help="Confirm"/>
                    <filter name="posted" string="Posted" domain="[('state','=', 'posted')]" help="Posted"/>
                    <separator/>
                    <filter name="thp" string="THP" domain="[('thp','>', 0)]" help="POT/GP"/>
                    <separator/>
                    <field name="rate_id"/>
                </search>"""
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class MarketingPICLine(models.Model):
    _name = 'marketing.pic.line'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    fee_id = fields.Many2one('marketing.pic', string="Fee ID")
    company_id = fields.Many2one('res.company', string="Company")
    date_start = fields.Date(string="Date Start")
    date_end = fields.Date(string="Date End")
    doctor_id = fields.Many2one('account.analytic.account', string="Primary Doctor") 
    patient_type = fields.Selection([
        ('0', 'ALL'),
        ('1', 'OPD (Without Pharmacy Item)'),
        ('2', 'IPD'),
        ('3', 'EMERGENCY'),
        ('4', 'DAYCARE'),
        ('5', 'OPD (With Pharmacy Item)'),
        ('6', 'PHARMACY')], string="Patient Type")

    bill_id = fields.Many2one('sale.order.bill', string="Bill ID.")
    bill_no = fields.Char(string="Bill No")
    bill_amount = fields.Float(string="Bill Amount")
    payer_amount = fields.Float(string="Payer Amount")
    payer_receipt = fields.Float(string="Payer Receipt")
    payer_balance = fields.Float(string="Payer Balance")
    payer_id = fields.Many2one('res.partner', string="Payer ID")
    payer_name = fields.Char(string="Payer Name")
    payment_type = fields.Selection([('AR','Advance Realization'), ('RC','Receipt')], string="Payment Type")
    payment_no = fields.Char(string="Payment No.")
    payment_date = fields.Date(string="Payment Date.")
    letter_no = fields.Char(string="Letter No.")
    letter_date = fields.Char(string="Letter Date.")
    otc_no = fields.Char(string="OTC No.")  
    store_location = fields.Char(string="Store Location")
    exc_feedoctor = fields.Float(string="Exclude FeeDoctor")
    exc_pharmacy = fields.Float(string="Exlcude Pharmacy")
    exc_chemo = fields.Float(string="Eclude Chemotheraphy")
    exc_hd = fields.Float(string="Exclude HD")
    exc_dental = fields.Float(string="Exclude Dental")
    exc_total = fields.Float(string="Exclude Total")
    nett_amount = fields.Float(string="Nett for Compute")
    rate_id = fields.Float(string="PIC ID")
    fee_percent= fields.Float(string="Fee Percent")
    fee_amount = fields.Float(string="Fee Amount")
    state = fields.Selection(related="fee_id.state")


class MarketingReport(models.TransientModel):
    _name = 'marketing.report.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id

    def _month(orm):
        result = []
        for loop in range(12):
            month = loop + 1
            result += [(str(month), calendar.month_name[month])]
        return result

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    report_type = fields.Selection([
        ('marketing_fee_bank', 'Marketing Fee Summary'),
        ('marketing_fee_line', 'Marketing Fee Detail'),
        ('personal_fee_bank', 'Personal Fee Summary'),
        ('personal_fee_line', 'Personal Fee Detail'),
        ('pic_fee_bank', 'PIC Fee Summary'),
        ('pic_fee_line', 'PIC Fee Detail')], string='Report Type', required=True)
    year = fields.Integer(string="Year Period", required=True)
    month = fields.Selection(_month, string="Month", required=True)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(MarketingReport,self).get_view(view_id=view_id,view_type=view_type, **options)  
        res['arch'] = """
            <form string="Marketing Compiled Report">
                <group>
                    <group>
                        <field name="company_id" />
                        <field name="report_type" />
                    </group>
                    <group>
                        <field name="year" />
                        <field name="month" />
                    </group>
                </group>
                <footer>
                    <button name="generate_report" string="Generate Report" type="object" class="oe_highlight"/>
                </footer>
            </form>
        """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # @api.multi
    def generate_report(self):
        
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/marketing_report/marketing_report?id=' + str(self.id)
        action['target'] = 'new'
        return action


class MarketingPosting(models.TransientModel):
    _name = 'marketing.posting.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id

    def _month(orm):
        result = []
        for loop in range(12):
            month = loop + 1
            result += [(str(month), calendar.month_name[month])]
        return result
        
    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    year = fields.Integer(string="Year Period", required=True)
    month = fields.Selection(_month, string="Month", required=True)
    posting_type = fields.Selection([
        ('marketing_fee', 'Marketing Fee'), 
        ('personal_fee', 'Personal Fee'),
        ('pic_fee', 'PIC Fee')], default='marketing_fee', string='Fee Type', required=True)
    
    marketing_fee_ids = fields.Many2many('marketing.fee', relation='marketing_fee_posting_rel', string="Marketing Fee", store=True)
    personal_fee_ids = fields.Many2many('marketing.personal', relation='marketing_personal_posting_rel', string="Personal Fee", store=True)
    pic_fee_ids = fields.Many2many('marketing.pic', relation='marketing_pic_posting_rel', string="PIC Fee", store=True)
    
    expense_date = fields.Date(string="Expense Date", store=True, required=True, index=True)
    expense_journal_id = fields.Many2one('account.journal', string="Expense Journal")
    expense_account_id = fields.Many2one('account.account', string="Expense Account")
    tax_account_id = fields.Many2one('account.account', string="Tax Account")
    credit_account_id = fields.Many2one('account.account', string="Credit Account")
    auto_posting = fields.Boolean(string='Posting Entries', default=False)

    # @api.multi
    def posting(self):
        posting_type = self.posting_type
        date = self.expense_date
        account_tax_id = self.tax_account_id.id
        account_tax_code = self.tax_account_id.code
        account_credit_id = self.credit_account_id.id
        account_credit_code =  self.credit_account_id.code
        account_debit_id = self.expense_account_id.id
        account_debit_code = self.expense_account_id.code
        journal_id = self.expense_journal_id.id
        company_id = self.company_id.id 
        auto_posting = self.auto_posting

        doctor_ids = []
        move_lines = []
        fee_type = ''
        label = ''

        if posting_type == 'marketing_fee':
            fee_type = 'MARKETING'
            label = 'Marketing Fee ' + str(self.year) + '-' + str(self.month)
            records = self.marketing_fee_ids

        if posting_type == 'personal_fee':
            fee_type = 'PERSONAL'
            label = 'Personal Fee ' + str(self.year) + '-' + str(self.month)
            records = self.personal_fee_ids
        
        if posting_type == 'pic_fee':
            fee_type = 'PIC'
            label = 'PIC Fee ' + str(self.year) + '-' + str(self.month)
            records = self.pic_fee_ids

        
        # loop journal 
        for record in records:
            doctor_id = record.employee_id.id if posting_type =='marketing_fee' else record.rate_id.id 

            # ambil THP 
            query = """
                SELECT 
                    sol.tglproses,
                    sol.direction, sol.amount, 
                    sol.account_label service_label, 
                    sol.account_credit_id, 
                    sol.account_debit_id,
                    sol.doctor_id,
                    sol.patient_group, 
                    (CASE 
                        WHEN sol.direction < 1 
                        THEN COALESCE(sol.analytic_id, 0) 
                        ELSE 0 END) analytic_credit_id,
                    (CASE 
                        WHEN sol.direction = 1 
                        THEN COALESCE(sol.analytic_id, 0) 
                        ELSE 0 END) analytic_debit_id
                FROM view_account_marketing_cost sol
                WHERE sol.company_id = {company_id}
                    AND EXTRACT(YEAR FROM sol.tglproses) = {year}
                    AND EXTRACT(MONTH FROM sol.tglproses) = {month}
                    AND sol.trans_type = '{fee_type}'
                    AND sol.doctor_id = {doctor_id}
                    AND sol.amount <> 0
            """ .format(
                company_id=company_id,
                doctor_id=doctor_id,
                year=self.year, 
                month=self.month,
                fee_type=(fee_type + '-THP'))
                
            open('/opt/odoo16/logs/log_marketing_posting.log', 'a+').write('\n' + str(tools.datetime.now()) + ' Query \n' + str(query))
            self.env.cr.execute(query)
            lines = self.env.cr.dictfetchall()

            if lines:
                for line in lines:
                    debit_id = account_credit_id if line['direction'] < 1 else account_debit_id
                    credit_id = account_debit_id if line['direction'] < 1 else account_credit_id

                    if int(line['analytic_credit_id']) > 0:
                        move_lines.append([0, 0, {'name':str(line['service_label'].encode('utf8')), 'analytic_account_id':int(line['analytic_credit_id']), 'account_id':credit_id, 'debit':0.0, 'credit':line['amount'] or 0.0}])
                    else:
                        move_lines.append([0, 0, {'name':str(line['service_label'].encode('utf8')), 'account_id':credit_id, 'debit':0.0, 'credit':line['amount'] or 0.0}])
                        
                    if int(line['analytic_debit_id']) > 0:
                        move_lines.append([0, 0, {'name':str(line['service_label'].encode('utf8')), 'analytic_account_id':int(line['analytic_debit_id']), 'account_id':debit_id, 'credit':0.0, 'debit':line['amount'] or 0.0}])
                    else:
                        move_lines.append([0, 0, {'name':str(line['service_label'].encode('utf8')), 'account_id':debit_id, 'credit':0.0, 'debit':line['amount'] or 0.0}])
                
                
            # PPH
            query = """
                SELECT 
                    sol.tglproses,
                    sol.direction, sol.amount, 
                    sol.account_label service_label, 
                    sol.account_credit_id, 
                    sol.account_debit_id,
                    sol.doctor_id,
                    sol.patient_group, 
                    (CASE 
                        WHEN sol.direction < 1 
                        THEN COALESCE(sol.analytic_id, 0) 
                        ELSE 0 END) analytic_credit_id,
                    (CASE 
                        WHEN sol.direction = 1 
                        THEN COALESCE(sol.analytic_id, 0) 
                        ELSE 0 END) analytic_debit_id
                FROM view_account_marketing_cost sol
                WHERE sol.company_id = {company_id}
                    AND EXTRACT(YEAR FROM sol.tglproses) = {year}
                    AND EXTRACT(MONTH FROM sol.tglproses) = {month}
                    AND sol.trans_type ='{fee_type}'
                    AND sol.doctor_id = {doctor_id}
                    AND sol.amount <> 0
            """ .format(
                company_id=company_id,
                doctor_id=doctor_id,
                year=self.year, 
                month=self.month,
                fee_type=(fee_type + '-PPH'))

            open('/opt/odoo16/logs/log_marketing_posting.log', 'a+').write('\n' + str(tools.datetime.now()) + ' Query \n' + str(query))
            self.env.cr.execute(query)
            lines = self.env.cr.dictfetchall()

            if lines:
                for line in lines:
                    credit_id = account_debit_id if line['direction'] < 1 else account_tax_id 
                    debit_id = account_tax_id if line['direction'] < 1 else account_debit_id

                    if int(line['analytic_credit_id']) > 0:
                        move_lines.append([0, 0, {'name':str(line['service_label'].encode('utf8')), 'analytic_account_id':int(line['analytic_credit_id']), 'account_id':credit_id, 'debit':0.0, 'credit':line['amount'] or 0.0}])
                    else:
                        move_lines.append([0, 0, {'name':str(line['service_label'].encode('utf8')), 'account_id':credit_id, 'debit':0.0, 'credit':line['amount'] or 0.0}])
                        
                    if int(line['analytic_debit_id']) > 0:
                        move_lines.append([0, 0, {'name':str(line['service_label'].encode('utf8')), 'analytic_account_id':int(line['analytic_debit_id']), 'account_id':debit_id, 'credit':0.0, 'debit':line['amount'] or 0.0}])
                    else:
                        move_lines.append([0, 0, {'name':str(line['service_label'].encode('utf8')), 'account_id':debit_id, 'credit':0.0, 'debit':line['amount'] or 0.0}])
                
            if move_lines:
                move = self.env['account.move'].create({'journal_id':journal_id,'ref':label,'line_ids':move_lines,'date':date})
                if auto_posting:
                    move.action_post()
                    record.journal_id = move.id 
                    record.state = 'posted' 

        

# class MarketingHttpReport(http.Controller):

#     # Print Slip Marketing Fee
#     @http.route('/marketing_report/print_marketing_fee', type='http', auth="user")
#     @serialize_exception
#     def SlipMarketingFee(self, id, ext='pdf', **kw):
#         id = int(id)
#         sudo = request.env.user.sudo()
#         record = sudo.env['marketing.fee'].browse(id)
#         data = {}  #record.read()[0]
#         month = dict(sudo.env['marketing.fee']._fields['month'].selection)
#         file_name = record.employee_id.name.encode('utf-8').strip()

#         data['sign_1'] = record.company_id.marketing_ttd3 or ''
#         data['sign_2'] = record.company_id.marketing_ttd4 or ''
#         data['title_1'] = record.company_id.marketing_title3 or ''
#         data['title_2'] = record.company_id.marketing_title4 or ''
#         data['city'] = record.company_id.df_city or ''
#         data['company'] = record.company_id.name or ''

#         data['employee_code'] = record.employee_id.code or ''
#         data['employee_name'] = record.employee_id.name.encode('utf-8').strip() or ''
#         data['employee_title'] = record.employee_id.position_id.name or ''

#         data['period_month'] = str(month[record.month] or '')
#         data['period_year'] = str(record.year or '')

        
#         data['addition'] = float(record.addition or 0.0)
#         data['taxes'] = float(record.total_pph or 0.0)
#         data['deduction'] = float(record.deduction or 0.0) 
#         data['thp'] = float(record.thp or 0.0)
        
#         data['data_ids'] = []
#         data['addition_ids'] = []
#         data['deduction_ids'] = []

#         query = sudo.env.cr.execute("""
#             SELECT b.payer_new
#             FROM marketing_fee_line a
#             INNER JOIN marketing_billing b ON b.id = a.billing_id
#             WHERE a.fee_id = '{fee_id}'
#             GROUP BY b.payer_new
#             ORDER BY b.payer_new DESC
#         """.format(fee_id=record.id))

#         groups = sudo.env.cr.dictfetchall()
#         fee_old = 0.0 
#         fee_new = 0.0 
#         for line in groups:
#             obj = {}
#             value = line['payer_new']
#             query = sudo.env.cr.execute("""
#                 SELECT 
#                     coalesce(sum(
#                         case when b.payer_new ='new' 
#                         then coalesce(a.new_amount,0) 
#                         else coalesce(a.old_amount,0) end
#                     ), 0.00000) AS total_fee    
#                 FROM marketing_fee_line a
#                 INNER JOIN marketing_billing b ON b.id = a.billing_id 
#                 WHERE a.fee_id = '{fee_id}' 
#                     AND b.payer_new = '{group}'
#             """.format(fee_id=record.id, group=value))
#             fee = sudo.env.cr.dictfetchall()

#             obj['customer_group'] = 'New Customer' if value == 'new' else 'Old Customer'
#             obj['total_fee'] = float(fee[0]['total_fee'] or 0.0)
#             obj['line_ids'] = []

#             if value == 'new':
#                 fee_new = float(fee[0]['total_fee'] or 0.0)
#             elif value == 'old':
#                 fee_old = float(fee[0]['total_fee'] or 0.0)

            

#             # query = sudo.env.cr.execute("""
#             #     SELECT 
#             #         b.bill_date,
#             #         b.bill_no,
#             #         b.patient_name,
#             #         b.payer_name,
#             #         (case when b.payer_new = 'new' then a.new_incentive else a.old_incentive end) incentive,
#             #         (case when b.payer_new = 'new' then a.new_sharing else a.old_sharing end) sharing,
#             #         (case when b.payer_new = 'new' then a.new_rate else a.old_rate end) rate,
#             #         (case when b.payer_new = 'new' then a.new_amount else a.old_amount end) amount
#             #     FROM marketing_fee_line a
#             #     INNER JOIN marketing_billing b ON b.id = a.billing_id 
#             #     WHERE a.fee_id = '{fee_id}' 
#             #         AND b.payer_new = '{group}'
#             # """.format(fee_id=record.id, group=value))

#             query = sudo.env.cr.execute("""
#                 SELECT 
#                     b.payer_code, 
#                     b.payer_name,
#                     sum(case when b.payer_new = 'new' then a.new_incentive else a.old_incentive end) incentive,
#                     (case when b.payer_new = 'new' then a.new_sharing else a.old_sharing end) sharing,
#                     (case when b.payer_new = 'new' then a.new_rate else a.old_rate end) rate,
#                     sum(case when b.payer_new = 'new' then a.new_amount else a.old_amount end) amount
#                 FROM marketing_fee_line a
#                 INNER JOIN marketing_billing b ON b.id = a.billing_id 
#                 WHERE a.fee_id = '{fee_id}' 
#                     AND b.payer_new = '{group}'
#                 GROUP BY b.payer_code, b.payer_name,
#                     (case when b.payer_new = 'new' then a.new_sharing else a.old_sharing end),
#                     (case when b.payer_new = 'new' then a.new_rate else a.old_rate end)

#             """.format(fee_id=record.id, group=value))

#             results = sudo.env.cr.dictfetchall()
#             for row in results:
#                 detail = {}    
#                 detail['bill_date'] = 'ALL' #datetime.datetime.strptime(row['bill_date'], '%Y-%m-%d').strftime('%d-%m-%Y')
#                 detail['bill_no'] = 'ALL' #row['bill_no'].encode()
#                 # detail['patient_name'] = row['patient_name'].encode()
#                 detail['payer_code'] = row['payer_code'].encode()
#                 detail['payer_name'] = row['payer_name'].encode()
#                 detail['incentive'] = float(row['incentive'])
#                 detail['sharing'] = float(row['sharing'])
#                 detail['rate'] = row['rate'] or 0.0
#                 detail['amount'] = float(row['amount'])
#                 obj['line_ids'] += [detail]

#             data['data_ids'] += [obj]


#         data['fee_old'] = float(fee_old)
#         data['fee_new'] = float(fee_new)
                
#         for line in record.fee_addition_ids:
#             vals = {}
#             vals['date'] = datetime.datetime.strptime(line['date'], '%Y-%m-%d').strftime('%d-%m-%Y')
#             vals['name'] = line.name
#             vals['amount'] = line.amount
#             data['addition_ids'] += [vals]


#         for line in record.fee_deduction_ids:
#             vals = {}
#             vals['date'] = datetime.datetime.strptime(line['date'], '%Y-%m-%d').strftime('%d-%m-%Y')
#             vals['name'] = line.name
#             vals['amount'] = line.amount
#             data['deduction_ids'] += [vals]
           
   
#         data = convert(data)
#         data = json(data, cdata=False)
#         # data = json(data)
#         open('/opt/odoo16/logs/print_marketing_fee.log','a+').write('\n' + str(data))

#         url = request.env.company.url_host_jasper + "/services/repository?wsdl"
#         uname = request.env.company.uname_jasper
#         password = request.env.company.pass_jasper
        
#         import requests
#         from lxml import etree

#         execution = requests.post('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions',
#             auth=(uname, password),
#             json={
#                 'reportUnitUri': '/Mayapada/Marketing/Marketing_fee',
#                 'outputFormat': 'pdf',
#                 'parameters': {
#                     'reportParameter': [{
#                         'name': 'data',
#                         'value': [data]
#                     }]
#                 }
#             })
#         filename = str(file_name) + ".pdf"
#         xml = etree.XML(execution.content)
#         request_id = xml.find('.//requestId').text
#         export_id = xml.find('.//export//id').text
#         result = requests.get('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions/'+ request_id + '/exports/' + export_id + '/outputResource',cookies=execution.cookies)
#         return request.make_response(result.content,[('Content-Type', result.headers['content-type']),('Content-Disposition', content_disposition(filename))])

    


#     # Print Slip Personal Fee
#     @http.route('/marketing_report/print_personal_fee', type='http', auth="user")
#     @serialize_exception
#     def SlipPersonalFee(self, id, ext='pdf', **kw):
#         id = int(id)
#         sudo = request.env.user.sudo()
#         record = sudo.env['marketing.personal'].browse(id)
#         data = {}  #record.read()[0]
#         month = dict(sudo.env['marketing.personal']._fields['month'].selection)
#         file_name = record.rate_id.name.encode('utf-8').strip()

#         data['sign_1'] = record.company_id.marketing_ttd3 or ''
#         data['sign_2'] = record.company_id.marketing_ttd4 or ''
#         data['title_1'] = record.company_id.marketing_title3 or ''
#         data['title_2'] = record.company_id.marketing_title4 or ''
#         data['city'] = record.company_id.df_city or ''
#         data['company'] = record.company_id.name or ''

#         data['employee_code'] = record.rate_id.code or 'NONE'
#         data['employee_name'] = record.rate_id.name.encode('utf-8').strip() or ''
#         data['employee_title'] = ' PIC'
#         data['period_month'] = str(month[record.month] or '')
#         data['period_year'] = str(record.year or '')

#         data['total_billing'] = 0.0 
#         data['total_credit'] = 0.0
#         data['total_fee'] = float(record.total_fee or 0.0)
#         data['taxes'] = float(record.total_pph or 0.0)
#         data['thp'] = float(record.thp or 0.0)
#         data['data_ids'] = []

#         query = sudo.env.cr.execute("""
#             SELECT 
#                 b.bill_date,
#                 b.bill_no,
#                 b.patient_name,
#                 b.payer_name,
#                 b.bill_amount, 
#                 b.credit_amount, 
#                 b.nett_amount, 
#                 a.personal_rate rate, 
#                 a.personal_fee amount
#             FROM marketing_personal_line a
#             INNER JOIN marketing_billing b ON b.id = a.billing_id 
#             WHERE a.fee_id = '{fee_id}' 
#         """.format(fee_id=record.id))

#         results = sudo.env.cr.dictfetchall()
#         for row in results:
#             detail = {}    
#             detail['bill_date'] = datetime.datetime.strptime(row['bill_date'], '%Y-%m-%d').strftime('%d-%m-%Y')
#             detail['bill_no'] = row['bill_no'].encode()
#             detail['patient_name'] = row['patient_name'].encode()
#             detail['payer_name'] = row['payer_name'].encode()
#             detail['bill_amount'] = float(row['bill_amount'])
#             detail['credit_amount'] = float(row['credit_amount'])
#             detail['nett_amount'] = float(row['nett_amount'])
#             detail['rate'] = float(row['rate'])
#             detail['amount'] = float(row['amount'])
#             data['data_ids'] += [detail]

#             data['total_billing'] += float(row['bill_amount'])
#             data['total_credit'] += float(row['credit_amount'])

    
   
#         data = convert(data)
#         data = json(data, cdata=False)
        
#         url = request.env.company.url_host_jasper + "/services/repository?wsdl"
#         uname = request.env.company.uname_jasper
#         password = request.env.company.pass_jasper
        
#         import requests
#         from lxml import etree

#         execution = requests.post('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions',
#             auth=(uname, password),
#             json={
#                 'reportUnitUri': '/Mayapada/Marketing/Personal_fee',
#                 'outputFormat': 'pdf',
#                 'parameters': {
#                     'reportParameter': [{
#                         'name': 'data',
#                         'value': [data]
#                     }]
#                 }
#             })
#         filename = str(file_name) + ".pdf"
#         xml = etree.XML(execution.content)
#         request_id = xml.find('.//requestId').text
#         export_id = xml.find('.//export//id').text
#         result = requests.get('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions/'+ request_id + '/exports/' + export_id + '/outputResource',cookies=execution.cookies)
#         return request.make_response(result.content,[('Content-Type', result.headers['content-type']),('Content-Disposition', content_disposition(filename))])

    

#     # Print Slip PIC Fee
#     @http.route('/marketing_report/print_pic_fee', type='http', auth="user")
#     @serialize_exception
#     def SlipPICFee(self, id, ext='pdf', **kw):
#         id = int(id)
#         sudo = request.env.user.sudo()
#         record = sudo.env['marketing.pic'].browse(id)
#         data = {}  #record.read()[0]
#         month = dict(sudo.env['marketing.pic']._fields['month'].selection)
#         file_name = record.rate_id.name.encode('utf-8').strip()

#         data['sign_1'] = record.company_id.marketing_ttd3 or ''
#         data['sign_2'] = record.company_id.marketing_ttd4 or ''
#         data['title_1'] = record.company_id.marketing_title3 or ''
#         data['title_2'] = record.company_id.marketing_title4 or ''
#         data['city'] = record.company_id.df_city or ''
#         data['company'] = record.company_id.name or ''

#         data['employee_code'] = record.rate_id.code or 'NONE'
#         data['employee_name'] = record.rate_id.name.encode('utf-8').strip() or ''
#         data['employee_title'] = ' PIC'
#         data['period_month'] = str(month[record.month] or '')
#         data['period_year'] = str(record.year or '')

#         data['total_receipt'] = 0.0
#         data['total_exclude'] = 0.0
#         data['total_fee'] = float(record.total_fee or 0.0)
#         data['taxes'] = float(record.total_pph or 0.0)
#         data['thp'] = float(record.thp or 0.0)
#         data['data_ids'] = []



#         query = sudo.env.cr.execute("""
#             SELECT 
#                 a.letter_no,
#                 a.payment_no,
#                 a.bill_no,
#                 b.name doctor_name,
#                 a.payer_name,
#                 a.payer_receipt, 
#                 a.exc_total, 
#                 a.fee_percent rate, 
#                 a.fee_amount amount
#             FROM marketing_pic_line a
#             LEFT JOIN account_analytic_account b ON b.id = a.doctor_id
#             WHERE a.fee_id = '{fee_id}' 
#         """.format(fee_id=record.id))

#         results = sudo.env.cr.dictfetchall()
#         for row in results:
#             detail = {}    
#             # detail['bill_date'] = datetime.datetime.strptime(row['bill_date'], '%Y-%m-%d').strftime('%d-%m-%Y')
#             detail['letter_no'] = row['letter_no'].encode()
#             detail['payment_no'] = row['payment_no'].encode()
#             detail['bill_no'] = row['bill_no'].encode()
#             detail['doctor_name'] = row['doctor_name'].encode()
#             detail['payer_name'] = row['payer_name'].encode()
#             detail['payer_receipt'] = float(row['payer_receipt'])
#             detail['exc_total'] = float(row['exc_total'])
#             detail['rate'] = row['rate'] or 0.0
#             detail['amount'] = float(row['amount'])
#             data['data_ids'] += [detail]

#             data['total_receipt'] += row['payer_receipt']
#             data['total_exclude'] += row['exc_total']

    
#         data = convert(data)
#         data = json(data, cdata=False)
        
#         url = request.env.company.url_host_jasper + "/services/repository?wsdl"
#         uname = request.env.company.uname_jasper
#         password = request.env.company.pass_jasper
        
#         import requests
#         from lxml import etree

#         execution = requests.post('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions',
#             auth=(uname, password),
#             json={
#                 'reportUnitUri': '/Mayapada/Marketing/PIC_fee',
#                 'outputFormat': 'pdf',
#                 'parameters': {
#                     'reportParameter': [{
#                         'name': 'data',
#                         'value': [data]
#                     }]
#                 }
#             })
#         filename = str(file_name) + ".pdf"
#         xml = etree.XML(execution.content)
#         request_id = xml.find('.//requestId').text
#         export_id = xml.find('.//export//id').text
#         result = requests.get('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions/'+ request_id + '/exports/' + export_id + '/outputResource',cookies=execution.cookies)
#         return request.make_response(result.content,[('Content-Type', result.headers['content-type']),('Content-Disposition', content_disposition(filename))])

    

#     # Print Marketing Report
#     @http.route('/marketing_report/marketing_report', type='http', auth="user")
#     @serialize_exception
#     def PrintMarketingReport(self, id, **kw):
#         id = int(id)
#         sudo = request.env.user.sudo()
#         record = sudo.env['marketing.report.wizard'].browse(id)
#         month = dict(sudo.env['marketing.report.wizard']._fields['month'].selection)
#         types = dict(sudo.env['marketing.report.wizard']._fields['report_type'].selection)
       
#         report_type = str(types[record.report_type] or '')
#         period_month = str(month[record.month] or '')
#         period_year = str(record.year or '')
#         report_name = report_type + ' ' + period_month + '-' + period_year

#         import io
#         import xlsxwriter

#         output = io.BytesIO()
#         response = request.make_response(None, headers=[
#             ('Content-Type', 'application/vnd.ms-excel'),
#             ('Content-Disposition', content_disposition(report_name + '.xlsx'))
#         ])
            
#         workbook = xlsxwriter.Workbook(output, {
#             'constant_memory': True, 
#             'in_memory': True, 
#             'strings_to_numbers':False, 
#             'strings_to_formulas':True, 
#             'strings_to_urls':True, 
#             'default_date_format':'yyyy-mm-dd'})

#         workbook.set_properties({
#             'title': report_name,
#             'comments': 'Created with Odoo and XlsxWriter'
#         })
#         worksheet = workbook.add_worksheet()

#         format_title = workbook.add_format()
#         format_title.set_font_size(20)
#         # format_title.set_font_color('blue')
#         format_title.set_bold()

#         format_header = workbook.add_format()
#         format_header.set_bold()
#         format_header.set_bg_color('yellow')
#         format_header.set_border(1)
#         format_header.set_align('center')

#         format_content = workbook.add_format()
#         format_content.set_bottom(1)

#         format_currency = workbook.add_format()
#         format_currency.set_num_format('#,##0.00')
#         format_currency.set_align('right')
#         format_currency.set_bottom(1)

#         format_date = workbook.add_format()
#         format_date.set_num_format('yyyy-mm-dd')
#         format_date.set_align('left')
#         format_date.set_bottom(1)

#         format_datetime = workbook.add_format()
#         format_datetime.set_num_format('yyyy-mm-dd hh:mm')
#         format_datetime.set_align('left')
#         format_datetime.set_bottom(1)

#         format_footer = workbook.add_format()
#         format_footer.set_bold()
#         format_footer.set_bg_color('orange')
#         format_footer.set_bottom(1)
#         format_footer.set_align('right')
#         format_footer.set_num_format('#,##0.00')

#         # worksheet.set_column(0, 40, 20)
#         # worksheet.set_column(7, 7, 50) # patient_name
#         # worksheet.set_column(10, 10, 50) # payer_name

#         # create header
#         worksheet.write(0, 0, report_type + ' Report', format_title)
#         worksheet.write(1, 0, 'Company: ' + record.company_id.name)
#         worksheet.write(2, 0, 'Period: ' + period_month + '-' + period_year)


#         if record.report_type == 'marketing_fee_bank':

#             # create header
#             worksheet.write(4, 0, 'No', format_header)
#             worksheet.write(4, 1, 'Employee No.', format_header)
#             worksheet.write(4, 2, 'Employee Name', format_header)
#             worksheet.write(4, 3, 'Job Title', format_header)
#             worksheet.write(4, 4, 'Bank Name', format_header)
#             worksheet.write(4, 5, 'Bank Branch', format_header)
#             worksheet.write(4, 6, 'Bank Account No.', format_header)
#             worksheet.write(4, 7, 'Bank Account Name', format_header)
#             worksheet.write(4, 8, 'Fee Amount (Rp)', format_header)

#             query = """
#                 select 
#                     b.code employee_code, 
#                     b.name employee_name,
#                     c.name employee_title, 
#                     b.bank_name, 
#                     b.bank_branch,
#                     b.bank_account,
#                     b.bank_client,
#                     a.thp amount
#                 from marketing_fee a
#                 inner join marketing_employee b on b.id = a.employee_id 
#                 left join marketing_position c on c.id = b.position_id
#                 where a.company_id = {company_id}
#                     and a.year = {year}
#                     and a.month = {month}
#                     and a.state in('posted', 'confirm')
#             """.format(
#                 company_id = record.company_id.id,
#                 year = record.year, 
#                 month = record.month)
#             open('/opt/odoo16/logs/marketing_report.log','a+').write('\n' + str(query).encode('utf-8'))
#             sudo.env.cr.execute(query)
#             results = sudo.env.cr.dictfetchall()

#             # looping data 
#             row = 5
#             sno = 1
#             if results:
#                 for line in results:
#                     worksheet.write(row, 0, sno, format_content)
#                     worksheet.write(row, 1, line['employee_code'], format_content)
#                     worksheet.write(row, 2, line['employee_name'], format_content)
#                     worksheet.write(row, 3, line['employee_title'], format_content)
#                     worksheet.write(row, 4, line['bank_name'], format_content)
#                     worksheet.write(row, 5, line['bank_branch'], format_content)
#                     worksheet.write(row, 6, line['bank_account'], format_content)
#                     worksheet.write(row, 7, line['bank_branch'], format_content)
#                     worksheet.write(row, 8, line['amount'], format_currency)
                   
#                     row += 1
#                     sno += 1


#             worksheet.write(row, 0, 'TOTAL', format_footer)
#             worksheet.write(row, 1, '', format_footer)
#             worksheet.write(row, 2, '', format_footer)
#             worksheet.write(row, 3, '', format_footer)
#             worksheet.write(row, 4, '', format_footer)
#             worksheet.write(row, 5, '', format_footer)
#             worksheet.write(row, 6, '', format_footer)
#             worksheet.write(row, 7, '', format_footer)
#             worksheet.write(row, 8, '=SUM(I6:I'+str(row)+')', format_footer)


#             # setup column
#             worksheet.set_column(0, 0, 5) # sno
#             worksheet.set_column(1, 1, 15) # group_name
#             worksheet.set_column(2, 8, 25) # group_name


#         elif record.report_type == 'marketing_fee_line':

#             # create header
#             worksheet.write(4, 0, 'No', format_header)
#             worksheet.write(4, 1, 'Year', format_header)
#             worksheet.write(4, 2, 'Month', format_header)
#             worksheet.write(4, 3, 'Employee No.', format_header)
#             worksheet.write(4, 4, 'Employee Name', format_header)
#             worksheet.write(4, 5, 'Payor Code', format_header)
#             worksheet.write(4, 6, 'Payor Name', format_header)
#             worksheet.write(4, 7, 'Payor Group', format_header)
#             worksheet.write(4, 8, 'Refference', format_header)
#             worksheet.write(4, 9, 'Direct Sales', format_header)
#             worksheet.write(4, 10, 'Bill No', format_header)
#             worksheet.write(4, 11, 'Bill Date', format_header)
#             worksheet.write(4, 12, 'Patient UHID', format_header)
#             worksheet.write(4, 13, 'Patient Name', format_header)
#             worksheet.write(4, 14, 'Letter No', format_header)
#             worksheet.write(4, 15, 'Receipt Date', format_header)
#             worksheet.write(4, 16, 'Bill Amount', format_header)
#             worksheet.write(4, 17, 'Credit Note (Rp)', format_header)
#             worksheet.write(4, 18, 'Personal Fee (Rp)', format_header)
#             worksheet.write(4, 19, 'Refferal Fee (Rp)', format_header)
#             worksheet.write(4, 20, 'Fee Doctor (Rp)', format_header)
#             worksheet.write(4, 21, 'Nett for Marketing (Rp)', format_header)
#             worksheet.write(4, 22, 'Fee Amount (Rp)', format_header)

#             query = """
#                 select 
#                     a."year",
#                     a."month",
#                     c.code employee_code, 
#                     c."name" employee_name, 
#                     d.payer_code,
#                     d.payer_name,
#                     d.payer_new payer_group,
#                     (case when d.payer_new = 'new' then (
#                         case when b.new_direct is True 
#                             then 'Direct' else 'Overriding' 
#                         end) else '' end) refference, 
#                     e."name" direct_sales, 
#                     d.bill_no,
#                     d.bill_date,
#                     d.patient_mrid,
#                     d.patient_name,
#                     d.letter_no,
#                     d.balance_date,
#                     d.bill_amount,
#                     d.credit_amount,
#                     d.personal_fee,
#                     d.refferal_fee,
#                     d.fee_amount,
#                     d.nett_marketing,
#                     coalesce(b.old_amount,b.new_amount) fee_marketing 
#                 from marketing_fee a 
#                 inner join marketing_fee_line b on b.fee_id = a."id" 
#                 inner join marketing_employee c on c.id = a.employee_id
#                 inner join marketing_billing d on d."id" = b.billing_id
#                 left join marketing_employee e on e.id = d.marketing_id
#                 where a.company_id = {company_id}
#                     and a.year = {year}
#                     and a.month = {month}
#                     and a."state" in('confirm','confirmed','posted')
#             """.format(
#                 company_id=record.company_id.id, 
#                 year=record.year, 
#                 month=record.month)
#             open('/opt/odoo16/logs/marketing_report.log','a+').write('\n' + str(query).encode('utf-8'))
#             sudo.env.cr.execute(query)
#             results = sudo.env.cr.dictfetchall()

#             # looping data 
#             row = 5
#             sno = 1
#             if results:
#                 for line in results:
#                     worksheet.write(row, 0, sno, format_content)
#                     worksheet.write(row, 1, line['year'], format_content)
#                     worksheet.write(row, 2, line['month'], format_content)
#                     worksheet.write(row, 3, line['employee_code'], format_content)
#                     worksheet.write(row, 4, line['employee_name'], format_content)
#                     worksheet.write(row, 5, line['payer_code'], format_content)
#                     worksheet.write(row, 6, line['payer_name'], format_content)
#                     worksheet.write(row, 7, line['payer_group'], format_content)
#                     worksheet.write(row, 8, line['refference'], format_content)
#                     worksheet.write(row, 9, line['direct_sales'], format_content)
#                     worksheet.write(row, 10, line['bill_no'], format_content)
#                     worksheet.write(row, 11, line['bill_date'], format_date)
#                     worksheet.write(row, 12, line['patient_mrid'], format_content)
#                     worksheet.write(row, 13, line['patient_name'], format_content)
#                     worksheet.write(row, 14, line['letter_no'], format_content)
#                     worksheet.write(row, 15, line['balance_date'], format_date)
#                     worksheet.write(row, 16, line['bill_amount'], format_currency)
#                     worksheet.write(row, 17, line['credit_amount'], format_currency)
#                     worksheet.write(row, 18, line['personal_fee'], format_currency)
#                     worksheet.write(row, 19, line['refferal_fee'], format_currency)
#                     worksheet.write(row, 20, line['fee_amount'], format_currency)
#                     worksheet.write(row, 21, line['nett_marketing'], format_currency)
#                     worksheet.write(row, 22, line['fee_marketing'], format_currency)
                   
#                     row += 1
#                     sno += 1

#             worksheet.write(row, 0, 'TOTAL', format_footer)
#             worksheet.write(row, 1, '', format_footer)
#             worksheet.write(row, 2, '', format_footer)
#             worksheet.write(row, 3, '', format_footer)
#             worksheet.write(row, 4, '', format_footer)
#             worksheet.write(row, 5, '', format_footer)
#             worksheet.write(row, 6, '', format_footer)
#             worksheet.write(row, 7, '', format_footer)
#             worksheet.write(row, 8, '', format_footer)
#             worksheet.write(row, 9, '', format_footer)
#             worksheet.write(row, 10, '', format_footer)
#             worksheet.write(row, 11, '', format_footer)
#             worksheet.write(row, 12, '', format_footer)
#             worksheet.write(row, 13, '', format_footer)
#             worksheet.write(row, 14, '', format_footer)
#             worksheet.write(row, 15, '', format_footer)
#             worksheet.write(row, 16, '=SUM(Q6:Q'+str(row)+')', format_footer)
#             worksheet.write(row, 17, '=SUM(R6:R'+str(row)+')', format_footer)
#             worksheet.write(row, 18, '=SUM(S6:S'+str(row)+')', format_footer)
#             worksheet.write(row, 19, '=SUM(T6:T'+str(row)+')', format_footer)
#             worksheet.write(row, 20, '=SUM(U6:U'+str(row)+')', format_footer)
#             worksheet.write(row, 21, '=SUM(V6:V'+str(row)+')', format_footer)
#             worksheet.write(row, 22, '=SUM(W6:W'+str(row)+')', format_footer)

#             # setup column
#             worksheet.set_column(0, 0, 5) # sno
#             worksheet.set_column(1, 3, 15) # group_name
#             worksheet.set_column(4, 4, 25) # group_name
#             worksheet.set_column(5, 5, 15) # payor_code
#             worksheet.set_column(6, 6, 25) # payor_name
#             worksheet.set_column(7, 7, 15) # payor_group
#             worksheet.set_column(8, 8, 15) # payor_group
#             worksheet.set_column(9, 9, 25) # direct_sales
#             worksheet.set_column(10, 11, 15) # group_name
#             worksheet.set_column(12, 12, 20) # group_name
#             worksheet.set_column(13, 14, 40) # group_name
#             worksheet.set_column(15, 21, 15) # group_name



#         elif record.report_type == 'personal_fee_bank':
        
#             # create header
#             worksheet.write(4, 0, 'No', format_header)
#             worksheet.write(4, 1, 'Personal No.', format_header)
#             worksheet.write(4, 2, 'Personal Name', format_header)
#             worksheet.write(4, 3, 'Company', format_header)
#             worksheet.write(4, 4, 'Remark', format_header)
#             worksheet.write(4, 5, 'Nett Amount' , format_header)
#             worksheet.write(4, 6, 'Rate Fee' , format_header)
#             worksheet.write(4, 7, 'Total Fee (Rp)' , format_header)
#             worksheet.write(4, 8, 'PPH (Rp)', format_header)
#             worksheet.write(4, 9, 'THP (Rp)', format_header)

#             query = """
#                 select 
#                     b.code personal_code, 
#                     b.name personal_name,
#                     b.payer_name,
#                     b.remark,
#                     c.nett_amount, 
#                     b.fee_percent rate,
#                     a.total_fee fee,
#                     a.total_pph pph,
#                     a.thp amount
#                 from marketing_personal a
#                 inner join marketing_rate_personal b on b.id = a.rate_id 
#                 left join (
#                     select c.fee_id, 
#                         sum(d.nett_amount) nett_amount
#                     from marketing_personal_line c
#                     inner join marketing_billing d on d.id = c.billing_id 
#                     group by c.fee_id 
#                 ) c on c.fee_id = a.id
#                 where a.company_id = {company_id}
#                     and a.year = {year}
#                     and a.month = {month}
#                     and a.state in('posted', 'confirm')
#             """.format(
#                 company_id = record.company_id.id,
#                 year = record.year, 
#                 month = record.month)
#             open('/opt/odoo16/logs/marketing_report.log','a+').write('\n' + str(query).encode('utf-8'))
#             sudo.env.cr.execute(query)
#             results = sudo.env.cr.dictfetchall()

#             # looping data 
#             row = 5
#             sno = 1
#             if results:
#                 for line in results:
#                     worksheet.write(row, 0, sno, format_content)
#                     worksheet.write(row, 1, line['personal_code'], format_content)
#                     worksheet.write(row, 2, line['personal_name'], format_content)
#                     worksheet.write(row, 3, line['payer_name'], format_content)
#                     worksheet.write(row, 4, line['remark'], format_content)
#                     worksheet.write(row, 5, line['nett_amount'], format_currency)
#                     worksheet.write(row, 6, line['rate'], format_currency)
#                     worksheet.write(row, 7, line['fee'], format_currency)
#                     worksheet.write(row, 8, line['pph'], format_currency)
#                     worksheet.write(row, 9, line['amount'], format_currency)
#                     row += 1
#                     sno += 1

#             worksheet.write(row, 0, 'TOTAL', format_footer)
#             worksheet.write(row, 1, '', format_footer)
#             worksheet.write(row, 2, '', format_footer)
#             worksheet.write(row, 3, '', format_footer)
#             worksheet.write(row, 4, '', format_footer)
#             worksheet.write(row, 5, '=SUM(F6:F'+str(row)+')', format_footer)
#             worksheet.write(row, 6, '', format_footer)
#             worksheet.write(row, 7, '=SUM(H6:H'+str(row)+')', format_footer)
#             worksheet.write(row, 8, '=SUM(I6:I'+str(row)+')', format_footer)
#             worksheet.write(row, 9, '=SUM(J6:J'+str(row)+')', format_footer)


#             # setup column
#             worksheet.set_column(0, 0, 5) # sno
#             worksheet.set_column(1, 1, 15) # group_name
#             worksheet.set_column(2, 2, 40) # group_name
#             worksheet.set_column(3, 3, 60) # group_name
#             worksheet.set_column(4, 4, 60) # group_name
#             worksheet.set_column(5, 10, 20) # group_name


#         elif record.report_type == 'personal_fee_line':
#             # create header
#             worksheet.write(4, 0, 'No', format_header)
#             worksheet.write(4, 1, 'Year', format_header)
#             worksheet.write(4, 2, 'Month', format_header)
#             worksheet.write(4, 3, 'Personal No.', format_header)
#             worksheet.write(4, 4, 'Personal Name', format_header)
#             worksheet.write(4, 5, 'Company', format_header)
#             worksheet.write(4, 6, 'Payer Code', format_header)
#             worksheet.write(4, 7, 'Payer Name', format_header)
#             worksheet.write(4, 8, 'Payer Group', format_header)
#             worksheet.write(4, 9, 'Bill No', format_header)
#             worksheet.write(4, 10, 'Bill Date', format_header)
#             worksheet.write(4, 11, 'Bill Amount (Rp)', format_header)
#             worksheet.write(4, 12, 'Credit Note (Rp)', format_header)
#             worksheet.write(4, 13, 'Nett Amount (Rp)', format_header)
#             worksheet.write(4, 14, 'Personal Fee (Rp)', format_header)

#             query = """
#                 select 
#                     a."year",
#                     a."month",
#                     c.code pic_code, 
#                     c."name" pic_name, 
#                     c.payer_name refference,
#                     d.payer_code payor_code,
#                     d.payer_name payor_name,
#                     d.payer_new payor_group,
#                     d.bill_no,
#                     d.bill_date,
#                     d.bill_amount,
#                     d.credit_amount,
#                     d.nett_amount,
#                     b.personal_fee 
#                 from marketing_personal a 
#                 inner join marketing_personal_line b on b.fee_id = a."id" 
#                 inner join marketing_rate_personal c on c.id = a.rate_id
#                 inner join marketing_billing d on d.id = b.billing_id
#                 left join marketing_employee e on e.id = d.marketing_id
#                 where a.company_id = {company_id}
#                     and a.year = '{year}'
#                     and a.month = '{month}'
#                     and a."state" in('confirm','confirmed','posted')
#             """.format(
#                 company_id=record.company_id.id, 
#                 year=record.year, 
#                 month=record.month)
#             open('/opt/odoo16/logs/marketing_report.log','a+').write('\n' + str(query).encode('utf-8'))
#             sudo.env.cr.execute(query)
#             results = sudo.env.cr.dictfetchall()

#             # looping data 
#             row = 5
#             sno = 1
#             if results:
#                 for line in results:
#                     worksheet.write(row, 0, sno, format_content)
#                     worksheet.write(row, 1, line['year'], format_content)
#                     worksheet.write(row, 2, line['month'], format_content)
#                     worksheet.write(row, 3, line['pic_code'], format_content)
#                     worksheet.write(row, 4, line['pic_name'], format_content)
#                     worksheet.write(row, 5, line['refference'], format_content)
#                     worksheet.write(row, 6, line['payor_code'], format_content)
#                     worksheet.write(row, 7, line['payor_name'], format_content)
#                     worksheet.write(row, 8, line['payor_group'], format_content)
#                     worksheet.write(row, 9, line['bill_no'], format_content)
#                     worksheet.write(row, 10, line['bill_date'], format_date)
#                     worksheet.write(row, 11, line['bill_amount'], format_currency)
#                     worksheet.write(row, 12, line['credit_amount'], format_currency)
#                     worksheet.write(row, 13, line['nett_amount'], format_currency)
#                     worksheet.write(row, 14, line['personal_fee'], format_currency)
                   
#                     row += 1
#                     sno += 1

#             worksheet.write(row, 0, 'TOTAL', format_footer)
#             worksheet.write(row, 1, '', format_footer)
#             worksheet.write(row, 2, '', format_footer)
#             worksheet.write(row, 3, '', format_footer)
#             worksheet.write(row, 4, '', format_footer)
#             worksheet.write(row, 5, '', format_footer)
#             worksheet.write(row, 6, '', format_footer)
#             worksheet.write(row, 7, '', format_footer)
#             worksheet.write(row, 8, '', format_footer)
#             worksheet.write(row, 9, '', format_footer)
#             worksheet.write(row, 10, '', format_footer)
#             worksheet.write(row, 11, '=SUM(L6:L'+str(row)+')', format_footer)
#             worksheet.write(row, 12, '=SUM(M6:M'+str(row)+')', format_footer)
#             worksheet.write(row, 13, '=SUM(N6:N'+str(row)+')', format_footer)
#             worksheet.write(row, 14, '=SUM(O6:O'+str(row)+')', format_footer)

#             # setup column
#             worksheet.set_column(0, 0, 5) # sno
#             worksheet.set_column(1, 3, 15) # group_name
#             worksheet.set_column(4, 4, 40) # group_name
#             worksheet.set_column(5, 5, 60) # group_name
#             worksheet.set_column(6, 6, 15) # payor_code
#             worksheet.set_column(7, 7, 60) # payor_name
#             worksheet.set_column(8, 8, 17) # payor_group
#             worksheet.set_column(9, 9, 17) # payor_group
#             worksheet.set_column(10, 14, 17) # group_name


#         elif record.report_type == 'pic_fee_bank':
            
#             # create header
#             worksheet.write(4, 0, 'No', format_header)
#             worksheet.write(4, 1, 'PIC No.', format_header)
#             worksheet.write(4, 2, 'PIC Name', format_header)
#             worksheet.write(4, 3, 'Company', format_header)
#             worksheet.write(4, 4, 'Payment Type', format_header)
#             worksheet.write(4, 5, 'Bank Name', format_header)
#             worksheet.write(4, 6, 'Bank Branch', format_header)
#             worksheet.write(4, 7, 'Account No.', format_header)
#             worksheet.write(4, 8, 'Account Name', format_header)
#             worksheet.write(4, 9, 'Total Receipt (Rp)' , format_header)
#             worksheet.write(4, 10, 'Total Exclude (Rp)' , format_header)
#             worksheet.write(4, 11, 'Total Nett (Rp)' , format_header)
#             worksheet.write(4, 12, 'Rate (%)' , format_header)
#             worksheet.write(4, 13, 'PIC Fee (Rp)' , format_header)
#             worksheet.write(4, 14, 'PPH (Rp)', format_header)
#             worksheet.write(4, 15, 'THP (Rp)', format_header)

#             query = """
#                 select 
#                     b.code pic_code, 
#                     b.name pic_name,
#                     b.payer_name,
#                     a.payment_type,
#                     a.bank_name,
#                     a.bank_branch,
#                     a.bank_account,
#                     a.bank_client,
#                     c.total_receipt, 
#                     c.total_exclude, 
#                     c.total_nett,
#                     b.fee_percent rate,
#                     a.total_fee,
#                     a.total_pph,
#                     a.thp total_thp
#                 from marketing_pic a
#                 inner join marketing_rate_pic b on b.id = a.rate_id 
#                 left join ( 
#                     select c.fee_id, 
#                         sum(coalesce(c.payer_receipt,0)) total_receipt,
#                         sum(coalesce(c.exc_total,0)) total_exclude,
#                         sum(coalesce(c.nett_amount,0)) total_nett
#                     from marketing_pic_line c 
#                     group by c.fee_id 
#                 ) c on c.fee_id = a.id
#                 where a.company_id = {company_id}
#                     and a.year = {year}
#                     and a.month = {month}
#                     and a.state in('posted', 'confirm')
#             """.format(
#                 company_id = record.company_id.id,
#                 year = record.year, 
#                 month = record.month)
#             open('/opt/odoo16/logs/marketing_report.log','a+').write('\n' + str(query).encode('utf-8'))
#             sudo.env.cr.execute(query)
#             results = sudo.env.cr.dictfetchall()

#             # looping data 
#             row = 5
#             sno = 1
#             if results:
#                 for line in results:
#                     worksheet.write(row, 0, sno, format_content)
#                     worksheet.write(row, 1, line['pic_code'], format_content)
#                     worksheet.write(row, 2, line['pic_name'], format_content)
#                     worksheet.write(row, 3, line['payer_name'], format_content)
#                     worksheet.write(row, 4, line['payment_type'], format_content)
#                     worksheet.write(row, 5, line['bank_name'], format_content)
#                     worksheet.write(row, 6, line['bank_branch'], format_content)
#                     worksheet.write(row, 7, line['bank_account'], format_content)
#                     worksheet.write(row, 8, line['bank_branch'], format_content)
#                     worksheet.write(row, 9, line['total_receipt'], format_currency)
#                     worksheet.write(row, 10, line['total_exclude'], format_currency)
#                     worksheet.write(row, 11, line['total_nett'], format_currency)
#                     worksheet.write(row, 12, line['rate'], format_currency)
#                     worksheet.write(row, 13, line['total_fee'], format_currency)
#                     worksheet.write(row, 14, line['total_pph'], format_currency)
#                     worksheet.write(row, 15, line['total_thp'], format_currency)
#                     row += 1
#                     sno += 1

#             worksheet.write(row, 0, 'TOTAL', format_footer)
#             worksheet.write(row, 1, '', format_footer)
#             worksheet.write(row, 2, '', format_footer)
#             worksheet.write(row, 3, '', format_footer)
#             worksheet.write(row, 4, '', format_footer)
#             worksheet.write(row, 5, '', format_footer)
#             worksheet.write(row, 6, '', format_footer)
#             worksheet.write(row, 7, '', format_footer)
#             worksheet.write(row, 8, '', format_footer)
#             worksheet.write(row, 9, '=SUM(J6:J'+str(row)+')', format_footer)
#             worksheet.write(row, 10, '=SUM(K6:K'+str(row)+')', format_footer)
#             worksheet.write(row, 11, '=SUM(L6:L'+str(row)+')', format_footer)
#             worksheet.write(row, 12, '', format_footer)
#             worksheet.write(row, 13, '=SUM(N6:N'+str(row)+')', format_footer)
#             worksheet.write(row, 14, '=SUM(O6:O'+str(row)+')', format_footer)
#             worksheet.write(row, 15, '=SUM(P6:P'+str(row)+')', format_footer)


#             # setup column
#             worksheet.set_column(0, 0, 5) # sno
#             worksheet.set_column(1, 1, 15) # group_name
#             worksheet.set_column(2, 2, 40) # group_name
#             worksheet.set_column(3, 3, 60) # group_name
#             worksheet.set_column(4, 7, 25) # group_name
#             worksheet.set_column(8, 16, 18) # group_name    
        

#         elif record.report_type == 'pic_fee_line':
#             # create header
#             worksheet.write(4, 0, 'No', format_header)
#             worksheet.write(4, 1, 'Year', format_header)
#             worksheet.write(4, 2, 'Month', format_header)
#             worksheet.write(4, 3, 'PIC No.', format_header)
#             worksheet.write(4, 4, 'PIC Name', format_header)
#             worksheet.write(4, 5, 'Company', format_header)
#             worksheet.write(4, 6, 'Bill No', format_header)
#             worksheet.write(4, 7, 'Letter No.', format_header)
#             worksheet.write(4, 8, 'Receipt No.', format_header)
#             worksheet.write(4, 9, 'Receipt Date.', format_header)
#             worksheet.write(4, 10, 'Payer Amount (Rp)', format_header)
#             worksheet.write(4, 11, 'Payer Receipt (Rp)', format_header)
#             worksheet.write(4, 12, 'Exc Fee Doctor (Rp)', format_header)
#             worksheet.write(4, 13, 'Exc Pharmacy (Rp)', format_header)
#             worksheet.write(4, 14, 'Exc Chemo (Rp)', format_header)
#             worksheet.write(4, 15, 'Exc HD (Rp)', format_header)
#             worksheet.write(4, 16, 'Exc Dental (Rp)', format_header)
#             worksheet.write(4, 17, 'Nett for Amount (Rp)', format_header)
#             worksheet.write(4, 18, 'Fee Rate (%)', format_header)
#             worksheet.write(4, 19, 'Fee Amount (Rp)', format_header)


#             query = """
#                 select 
#                     a."year",
#                     a."month",
#                     c.code pic_code, 
#                     c."name" pic_name, 
#                     c.payer_name refference,
#                     b.bill_no,
#                     b.letter_no,
#                     b.payment_no,
#                     b.payment_date,
#                     b.payer_amount,
#                     b.payer_receipt,
#                     b.exc_feedoctor,
#                     b.exc_pharmacy,
#                     b.exc_chemo,
#                     b.exc_hd,
#                     b.exc_dental,
#                     b.nett_amount,
#                     b.fee_percent,
#                     b.fee_amount
#                 from marketing_pic a 
#                 inner join marketing_pic_line b on b.fee_id = a."id" 
#                 inner join marketing_rate_pic c on c.id = a.rate_id
#                 where a.company_id = {company_id}
#                     and a.year = '{year}'
#                     and a.month = '{month}'
#                     and a."state" in('confirm','confirmed','posted')
#             """.format(
#                 company_id=record.company_id.id, 
#                 year=record.year, 
#                 month=record.month)
#             open('/opt/odoo16/logs/marketing_report.log','a+').write('\n' + str(query).encode('utf-8'))
#             sudo.env.cr.execute(query)
#             results = sudo.env.cr.dictfetchall()

#             # looping data 
#             row = 5
#             sno = 1
#             if results:
#                 for line in results:
#                     worksheet.write(row, 0, sno, format_content)
#                     worksheet.write(row, 1, line['year'], format_content)
#                     worksheet.write(row, 2, line['month'], format_content)
#                     worksheet.write(row, 3, line['pic_code'], format_content)
#                     worksheet.write(row, 4, line['pic_name'], format_content)
#                     worksheet.write(row, 5, line['refference'], format_content)
#                     worksheet.write(row, 6, line['bill_no'], format_content)
#                     worksheet.write(row, 7, line['letter_no'], format_content)
#                     worksheet.write(row, 8, line['payment_no'], format_content)
#                     worksheet.write(row, 9, line['payment_date'], format_date)
#                     worksheet.write(row, 10, line['payer_amount'], format_currency)
#                     worksheet.write(row, 11, line['payer_receipt'], format_currency)
#                     worksheet.write(row, 12, line['exc_feedoctor'], format_currency)
#                     worksheet.write(row, 13, line['exc_pharmacy'], format_currency)
#                     worksheet.write(row, 14, line['exc_chemo'], format_currency)
#                     worksheet.write(row, 15, line['exc_hd'], format_currency)
#                     worksheet.write(row, 16, line['exc_dental'], format_currency)
#                     worksheet.write(row, 17, line['nett_amount'], format_currency)
#                     worksheet.write(row, 18, line['fee_percent'], format_currency)
#                     worksheet.write(row, 19, line['fee_amount'], format_currency)
                   
#                     row += 1
#                     sno += 1

#             worksheet.write(row, 0, 'TOTAL', format_footer)
#             worksheet.write(row, 1, '', format_footer)
#             worksheet.write(row, 2, '', format_footer)
#             worksheet.write(row, 3, '', format_footer)
#             worksheet.write(row, 4, '', format_footer)
#             worksheet.write(row, 5, '', format_footer)
#             worksheet.write(row, 6, '', format_footer)
#             worksheet.write(row, 7, '', format_footer)
#             worksheet.write(row, 8, '', format_footer)
#             worksheet.write(row, 9, '', format_footer)
#             worksheet.write(row, 10, '=SUM(K6:K'+str(row)+')', format_footer)
#             worksheet.write(row, 11, '=SUM(L6:L'+str(row)+')', format_footer)
#             worksheet.write(row, 12, '=SUM(M6:M'+str(row)+')', format_footer)
#             worksheet.write(row, 13, '=SUM(N6:N'+str(row)+')', format_footer)
#             worksheet.write(row, 14, '=SUM(O6:O'+str(row)+')', format_footer)
#             worksheet.write(row, 15, '=SUM(P6:P'+str(row)+')', format_footer)
#             worksheet.write(row, 16, '=SUM(Q6:Q'+str(row)+')', format_footer)
#             worksheet.write(row, 17, '=SUM(R6:R'+str(row)+')', format_footer)
#             worksheet.write(row, 18, '', format_footer)
#             worksheet.write(row, 19, '=SUM(T6:T'+str(row)+')', format_footer)

#             # setup column
#             worksheet.set_column(0, 0, 5) # sno
#             worksheet.set_column(1, 3, 10) # group_name
#             worksheet.set_column(4, 4, 40) # group_name
#             worksheet.set_column(5, 5, 60) # group_name
#             worksheet.set_column(6, 20, 20) # group_name


#         worksheet.set_zoom(80)
#         workbook.close()
#         output.seek(0)
#         response.stream.write(output.read())
#         output.close()
#         del output # clear 
#         return response