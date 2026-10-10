from . import sync
from datetime import datetime, timedelta
#from datetime import datetime
import calendar
from functools import reduce
from odoo.osv import expression
from odoo import models, fields, api, tools, exceptions, _
from odoo.exceptions import UserError, ValidationError, Warning
from odoo.tools import float_is_zero, float_compare
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from odoo.addons import decimal_precision as dp
import requests
import json
try:
    import ujson as JSON
except:
    import json as JSON
import logging
import pytz
from xml.etree import ElementTree
# import urllib2
import urllib.request as urllib2
import mimetypes
import xmltodict
from dateutil.relativedelta import relativedelta
from multiprocess import Queue, Process, Manager
from odoo.tools.safe_eval import safe_eval
from xlrd import open_workbook
import re

import io
import csv
import hashlib
import base64
import posixpath
import zipfile
from decimal import Decimal, InvalidOperation
logger = logging.getLogger(__name__)

MAGIC_COLUMNS = ('id', 'create_uid', 'create_date', 'write_uid', 'write_date')


# mapping invoice type to journal type
TYPE2JOURNAL = {
    'out_invoice': 'sale',
    'in_invoice': 'purchase',
    'out_refund': 'sale',
    'in_refund': 'purchase',
}

# mapping invoice type to refund type
TYPE2REFUND = {
    'out_invoice': 'out_refund',        # Customer Invoice
    'in_invoice': 'in_refund',          # Vendor Bill
    'out_refund': 'out_invoice',        # Customer Refund
    'in_refund': 'in_invoice',          # Vendor Refund
}


# class CoveringLetterRel(models.Model):
#     _name = 'account.coveringletter.bill.rel'

#     account_coveringletter_id = fields.Many2one('account.coveringletter', string="Covering Letter")
#     sale_order_bill_id = fields.Many2one('sale.order.bill', string="Sale Order Bill")



# 2021.09.23 
class CoveringLetter(models.Model):
    _name = 'account.coveringletter'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    sync_id = sync.id
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.company.id

    draft_no = fields.Char(string="Draft No.", readonly=True, index=True)
    name = fields.Char(string="Letter No.", readonly=True, index=True)
    payer = fields.Many2one('res.partner', domain="['|', ('insurance','=',True),('customer_wipro','=',True)]", index=True)
    address_id = fields.Many2one('res.partner.address', string="Sub Address", domain="[('partner_id','=',payer)]")
    date = fields.Date(string="Date", required=True, index=True)
    sent_date = fields.Date(string="Sent Date")
    received_date = fields.Date(string="Received Date", copy=False, tracking=True)
    received_by = fields.Char(string="Received By")
    received_ref = fields.Char(string="Received Ref No.")
    due_day = fields.Integer(string="Due Day", required=False)
    due_date = fields.Date(string="Due Date", states={'confirm': [('readonly', True)]})
    due_day_payer = fields.Integer(string="Due Day (Backup Old)")
    remark = fields.Char(string="Remark", states={'confirm': [('readonly', True)]})
    billing_type = fields.Selection([('bill', 'Billing'),('cob', 'COB Bill'), ('admission','Admission')], string="Based On",required=True,default='bill')

    # ada kebutuhan dari FA u/ membuat tagihan CL per Penjamin satu virtual account
    virtual_enable = fields.Boolean(string="Enable VA Payer", default=False)
    virtual_beneficary = fields.Char(string="VA Beneficary")
    virtual_number = fields.Char(string="VA Number")
    virtual_bank = fields.Many2one('res.bank', string="VA Bank")

    journal_ids = fields.One2many('account.move', 'covering_id', string="Journal", readonly=True)
    billing_cob_ids = fields.Many2many('sale.order.cob', 'account_coveringletter_cob_rel', 'account_coveringletter_id', string="COB Bill", store=True, states={'confirm': [('readonly', True)]})
    billing_sale_ids = fields.Many2many('sale.order.bill', 'account_coveringletter_bill_rel', 'account_coveringletter_id', string="Billing", store=True, states={'confirm': [('readonly', True)]})
    # billing_ids = fields.Many2many('sale.order', 'account_coveringletter_admission_rel', 'account_coveringletter_id', string="Admission", states={'confirm': [('readonly', True)]}, ondelete='set null')
    billing_ids = fields.Many2many('sale.order', 'account_coveringletter_admission_rel', 'account_coveringletter_id', string="Admission", states={'confirm': [('readonly', True)]})

    creditnote_ids = fields.One2many('account.creditnote','letter_id', string="Credit Note", readonly=True)
    receipt_ids = fields.One2many('account.payment', 'covering_id', string="AR Receipt", readonly=True)
    advance_realization_ids = fields.One2many('account.advance.realization', 'covering_id', string="AR Advance Receipt", readonly=True)
    
    total_billing = fields.Float(string="Total Billing", readonly=True, store=True)
    total_adjustment = fields.Float(string="Disc. Adjustment", readonly=True, store=True)
    total_covering_letter = fields.Float(string="Total Covering Letter", readonly=True, store=True)
    total_payment = fields.Float(string="Total Receipt", readonly=True)
    total_discount = fields.Float(string="Total Discount", readonly=True)
    total_balance_amount = fields.Float(string="Total Balance", readonly=True)
    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm'), ('paid', 'Paid'), ('cancel', 'Cancel')], 'Status', default='draft', index=True, required=True, readonly=True, copy=False, tracking=True, store=True)
    company_id = fields.Many2one('res.company', string="Company", readonly=True, required=True, default=_get_company)
    revisi = fields.Boolean(string="Revisi", readonly=True)
    revisi_name = fields.Char(string="Revisi Name", readonly=True)
    revisi_sequence = fields.Integer(string="Revisi Sequence", readonly=True)
    api_post_timestamp = fields.Datetime(string="Timestamp", readonly=True)
    api_post_status = fields.Selection([('done', 'Done'), ('failed', 'Failed')], string='Status API Post', readonly=True)
    api_post_payload = fields.Char(string="Payload", readonly=True)
    api_post_response = fields.Char(string="Response", readonly=True)
    api_post_timestamp_cancel = fields.Datetime(string="Timestamp", readonly=True)
    api_post_status_cancel = fields.Selection([('done', 'Done'),('failed', 'Failed')], string='Status API Cancel', readonly=True)
    api_post_payload_cancel = fields.Char(string="Payload", readonly=True)
    api_post_response_cancel = fields.Char(string="Response", readonly=True)

    letter_discount = fields.Boolean(string="Enable Discount Before Invoice", default=False)
    letter_discount_reason = fields.Char(string="Discount Reason")
    letter_discount_percent = fields.Float(string="Discount Percent", digits=(16,2))
    letter_discount_account = fields.Many2one('account.account', string="Discount Account")
    letter_discount_account_code = fields.Char(string="Discount Account Code", related="letter_discount_account.code", readonly=True, store=False)
    letter_discount_analytic = fields.Many2one('account.analytic.account', string="Discount Analytic")
    move_line_ids = fields.One2many('account.move.line','covering_id', string="Move Items", readonly=True)
    bill_count = fields.Char(string="Bill Count",readonly=True,compute='_billcount',store=False)
    cl_enable = fields.Boolean(string="CL per PIC", related="company_id.cl_enable")
    # cl_enable = fields.Boolean(string="CL per PIC")

    cl_pic = fields.Char(string="CL PIC", index=True)
    cl_pic_email = fields.Char(string="CL PIC Email", index=True)
    cl_phone = fields.Char(string="CL Phone")
    cl_customer_remark = fields.Char(string="Customer Remarks")
    message_last_post = fields.Datetime(string="Message Last Post", index=True, readonly=True)


    @api.onchange('payer')
    def _onchange_payer(self):
        for record in self:
            if record.payer:
                record.due_day = record.payer.credit_days

    @api.onchange('due_day')
    def _onchange_due_day(self):
        for record in self:
            if (record.sent_date):
                record.due_date = datetime.strptime(str(record.sent_date),'%Y-%m-%d') + timedelta(days=int(record.due_day))
                # self.due_date = self.sent_date + tools.timedelta(days=int(self.due_day))

    @api.onchange('sent_date')
    def _onchange_sent_date(self):
        for record in self:
            if (record.due_day):
                # record.due_date = tools.datetime.strptime(record.sent_date,'%Y-%m-%d') + tools.timedelta(days=int(record.due_day))
                record.due_date = datetime.strptime(str(record.sent_date), '%Y-%m-%d') + timedelta(days=int(record.due_day))
    
    @api.onchange('cl_enable','payer')
    def _onchange_payer_cl(self):
        for record in self:
            if record.cl_enable == True:
                record.cl_pic = self.env.user.partner_id.name
                record.cl_pic_email = record.company_id.cl_pic_email
                # 20221014 - request mhtg
                record.cl_phone = self.env.user.ar_pic_phone or record.company_id.phone
                #record.cl_pic_email = self.env.user.partner_id.email
                
    # @api.one
    def _billcount(self):
        self.bill_count = len(self.billing_sale_ids)

    # @api.multi
    def button_journal_entries(self):
        return {
            'name': _('Journal Items'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('covering_id', 'in', self.ids)],
        }


    # @api.model
    # def _sync_coveringletter(self, sync_type='1'):
    #     sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>', 0)])}
    #     sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
    #     data = []
    #     date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
    #     # date = '2019-01-31'
    #     query_wipro = """
    #     SELECT 
    #         a.sync_id,
    #         a.name,
    #         convert(varchar(10),a.date, 121) as date,
    #         a.sent_date, 
    #         a.due_day,
    #         a.due_date,
    #         a.payer,
    #         a.count_invoice,
    #         a.total_invoice as total_billing,
    #         a.total_invoice as total_covering_letter,
    #         a.total_invoice as total_balance_amount,
    #         'bill' billing_type,
    #         a.STATUS,
    #         a.MODDATE 
    #     from dbo.VRP_OdooCoveringLetter a
    #     where convert(varchar(10), a.CreateDate, 121) = '%s'
    #     """ % (date)
    #     values = ''
    #     print (query_wipro)
    #     data += sync.get_data(sync.servers.get(sync_type), query_wipro)
    #     print (data)
    #     if not data:
    #         print ("No data available")
    #         return
    #     print ("jalan?")
    #     fields_without_id = tuple(
    #         key for key in self._fields
    #         if key != 'id' and 'property' not in key and 'ids' not in key
    #         and self._fields[key].required == True
    #         and self._fields[key].store == True)
    #     columns = tuple(
    #         key for key in data[0].keys()
    #         if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
    #     fields_without_id += columns
    #     columns += tuple(
    #         key for key in data[0].keys()
    #         if key in self._fields and key not in columns) if data else ()
    #     fields = fields_without_id + ('id', )
    #     if columns:
    #         columns += ('id', )
    #     default_values = {}
    #     for field in fields:
    #         if field in columns:
    #             continue
    #         default = self._fields[field].default
    #         if callable(default):
    #             default = default(self)
    #         if isinstance(default, models.Model):
    #             default = default.id
    #         default_values[field] = default
    #     now = tools.datetime.now().strftime('%Y%m%d %H:%M:%S')
    #     new_sync_ids = []
    #     for object in data:
    #         new_sync_ids += [object['sync_id']]
    #         for value in default_values:
    #             if value in object:
    #                 continue
    #             object[value] = default_values[value]
    #         payer = object['payer']
    #         object['payer'] = self.env['res.partner'].search([('sync_id', '=', object['payer']),('sync_type', '=', sync_type), ('customer_wipro', '=', True)], order="id asc", limit=1).id
    #         if not object['payer']:
    #             error_msg = '\n' + str(tools.datetime.now()) + " payer with sync_id %s and sync_type %s doesn't exist" % (payer, sync_type)
    #             print (error_msg)
    #             open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) +" payer with sync_id %s and sync_type %s doesn't exist" %(payer, sync_type))
    #             return
    #         if int(object['sync_id']) in sync_ids:
    #             object['id'] = sync_ids[object['sync_id']]
    #         else:
    #             object['id'] = 'DEFAULT'
    #         object['sync_date'] = now
    #         object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)],limit=1).id
    #         if values:
    #             values += ', '
    #         value = False
    #         for field in fields:
    #             if value:
    #                 value += ', '
    #             else:
    #                 value = '('
    #             if field == 'id' and object['id'] == 'DEFAULT':
    #                 value += object['id']
    #                 continue
    #             if type(object[field]) in [str, unicode]:
    #                 string = object[field]
    #                 value += "'" + string.replace("'", "''") + "'"
    #                 continue
    #             value += sync.json(object[field])
    #         value += ')'
    #         values += value
    #     excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
    #     columns = sync.remove_unicode(str(fields)).replace("'", "")
    #     columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
    #     print ("ni query?")
    #     query = "INSERT into account_coveringletter %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
    #     print (query.encode('utf8'))
    #     print ("execute bosq")
    #     self.env.cr.execute(query)

    # @api.model
    # def _sync_coveringletter_manual(self, sync_type='1', date_start='2019-01-01', date_end='2019-01-01'):
    #     sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)])}
    #     sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
    #     data = []
    #     date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
    #     # date = '2019-01-31'
    #     query_wipro = """
    #     SELECT 
    #         a.sync_id,
    #         a.name,
    #         convert(varchar(10),a.date, 121) as date,
    #         a.sent_date, 
    #         a.due_day,
    #         a.due_date,
    #         a.payer,
    #         a.count_invoice,
    #         a.total_invoice as total_billing,
    #         a.total_invoice as total_covering_letter,
    #         a.total_invoice as total_balance_amount,
    #         'bill' billing_type,
    #         a.STATUS,
    #         a.MODDATE 
    #     from dbo.VRP_OdooCoveringLetter a
    #     where convert(varchar(10), a.CreateDate, 121) >= '%s' and convert(varchar(10), a.CreateDate, 121) <= '%s'
    #     """ % (date_start, date_end)
    #     values = ''
    #     print (query_wipro)
    #     data += sync.get_data(sync.servers.get(sync_type), query_wipro)
    #     print (data)
    #     if not data:
    #         print ("No data available")
    #         return
    #     print ("jalan?")
    #     fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and 'ids' not in key and self._fields[key].required == True and self._fields[key].store == True)
    #     columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
    #     fields_without_id += columns
    #     columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
    #     fields = fields_without_id + ('id', )
    #     if columns:
    #         columns += ('id', )
    #     default_values = {}
    #     for field in fields:
    #         if field in columns:
    #             continue
    #         default = self._fields[field].default
    #         if callable(default):
    #             default = default(self)
    #         if isinstance(default, models.Model):
    #             default = default.id
    #         default_values[field] = default
    #     now = tools.datetime.now().strftime('%Y%m%d %H:%M:%S')
    #     new_sync_ids = []
    #     for object in data:
    #         new_sync_ids += [object['sync_id']]
    #         for value in default_values:
    #             if value in object:
    #                 continue
    #             object[value] = default_values[value]
    #         payer = object['payer']
    #         object['payer'] = self.env['res.partner'].search([('sync_id', '=', object['payer']), ('sync_type', '=', sync_type), ('customer_wipro', '=', True)], order="id asc", limit=1).id
    #         if not object['payer']:
    #             error_msg = '\n' + str(tools.datetime.now()) + " payer with sync_id %s and sync_type %s doesn't exist" % (payer, sync_type)
    #             print (error_msg)
    #             open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) +" payer with sync_id %s and sync_type %s doesn't exist" %(payer, sync_type))
    #             return
    #         if int(object['sync_id']) in sync_ids:
    #             object['id'] = sync_ids[object['sync_id']]
    #         else:
    #             object['id'] = 'DEFAULT'
    #         object['sync_date'] = now
    #         object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
    #         if values:
    #             values += ', '
    #         value = False
    #         for field in fields:
    #             if value:
    #                 value += ', '
    #             else:
    #                 value = '('
    #             if field == 'id' and object['id'] == 'DEFAULT':
    #                 value += object['id']
    #                 continue
    #             if type(object[field]) in [str, unicode]:
    #                 string = object[field]
    #                 value += "'" + string.replace("'", "''") + "'"
    #                 continue
    #             value += sync.json(object[field])
    #         value += ')'
    #         values += value
    #     excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
    #     columns = sync.remove_unicode(str(fields)).replace("'", "")
    #     columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
    #     print ("ni query?")
    #     query = "INSERT into account_coveringletter %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
    #     print (query.encode('utf8'))
    #     print ("execute bosq")
    #     self.env.cr.execute(query)


    # @api.multi 
    def action_cancel_call(self):
        for record in self:
            if record.state == 'draft':
                record.state = 'cancel'
                if record.billing_type == 'bill':
                    for line in record.billing_sale_ids:
                        line.write({'covering_id':None})
                elif record.billing_type == 'cob':
                    for line in record.billing_cob_ids:
                        line.write({'covering_id':None})
                elif record.billing_type == 'admission':
                    for line in record.billing_ids:
                        line.write({'covering_id':None})

    # @api.multi
    def action_draft(self):
        self.revisi = True
        self.revisi_sequence += 1
        self.state = 'draft'
        self.update({'revisi_name': 'R' + str(self.revisi_sequence)})  #self.env["ir.sequence"].next_by_code("coveringletter.revisi.seq")}


    @api.model
    def generate_payload(self, action = 'confirm'):
        payload = {}
        for record in self:
            payload["sync_type"] = record.company_id.sync_type
            payload["invoice_id"] = record.id # invoice_id odoo
            payload["invoice_date"] = record.date.strftime("%Y-%m-%d") # tgl invoice
            payload["invoie_due_date"] = record.due_date.strftime("%Y-%m-%d") # tgl jatuh tempo
            payload["invoice_sent_date"] = record.sent_date.strftime("%Y-%m-%d") # tgl pengiriman invice
            payload["invoice_number"] = record.name # nomor invoice
            payload["invoice_total"] = record.total_covering_letter # total tagihan invoice
            payload["invoice_status"] = action # status invoice confirm/cancel
            payload["payer_id"] = record.payer.id # payer_id di odoo 
            payload["payer_code"] = record.payer.vendor_code # payer code
            payload["payer_name"] = record.payer.name # nama payer
            payload["payer_sync_id_api"] = record.payer.sync_id_api # sync_id_api payer dari dhealth
            payload["create_uid"] = record.create_uid.id # user_id odoo yg create invoice
            payload["create_by"] = record.create_uid.partner_id.name # user_name odoo yg create invoice
            payload["create_date"] = record.create_date.strftime("%Y-%m-%d") #str(datetime.strptime(record.create_date, "%Y-%m-%d %H:%M:%S")) # tgl create invoice
            payload["write_uid"] = record.write_uid.id # user_id odoo yg update invoice
            payload["write_by"] = record.write_uid.partner_id.name # user_name odoo yg update invoice
            payload["write_date"] = record.write_date.strftime("%Y-%m-%d") #str(datetime.datetime.strptime(record.write_date, "%Y-%m-%d %H:%M:%S")) # tgl update invoice odoo
            details = []

            # Jika CL based on Admission
            if record.billing_type == 'admission':
                for bill in record.billing_ids:
                    if bill.sync_id_api or bill.sync_id > 0:
                        row = {}
                        row["order_id"] = bill.id # id sale.order yg dari odoo
                        row["order_sync_id_api"] = bill.sync_id_api or '' # sync_id_api dari dhealth
                        row["order_date"] = bill.date_order.strftime("%Y-%m-%d %H:%M:%S") # tgl pendaftaran
                        row["order_no"] = bill.name # nomor pendaftaran
                        date_source = bill.confirmation_date or bill.date_order
                        row["bill_date"] = date_source.strftime("%Y-%m-%d %H:%M:%S") if date_source else None
                        row["bill_no"] = bill.billno # nomor billing
                        row["payer_id"] = bill.payer_id.id # id asuransi odoo
                        row["payer_code"] = bill.payer_id.vendor_code # kode asuransi
                        row["payer_name"] = bill.payer_id.name # nama asuransi
                        row["payer_sync_id_api"] = bill.payer_id.sync_id_api # id_sync_api asuransi dhealth
                        row["patient_type"] = ("IPD" if bill.patient_type == '2' else "OPD" if bill.patient_type == "1" else "IGD" if bill.patient_type == "3" else "MCU" if bill.patient_type == "5" else "OPD") # patient_type OPD, IPD, IGD, MCU
                        row["patient_id"] = bill.partner_id.id # id pasien di odoo
                        row["patient_sync_id_api"] = bill.partner_id.sync_id_api # sync_id_api pasien dr dhealth
                        row["patient_regcode"] = bill.partner_id.registration_code # nomor MR pasien
                        row["patient_name"] = bill.partner_id.name # nama pasien
                        row["total_amount"] = bill.total_amount # total nett billing
                        row["payer_amount"] = bill.payer_amount # total nett tagihan payer
                        row["personal_amount"] = bill.personal_amount # total nett tagihan pasien
                        details.append(row)

            # Jika CL based on Billing
            elif record.billing_type == 'bill':
                for bill in record.billing_sale_ids:
                    if bill.sync_id_api or bill.sync_id > 0:
                        row = {}
                        row["order_id"] = bill.admission_id.id or '' # id sale.order yg dari odoo
                        row["order_sync_id_api"] = bill.admission_id.sync_id_api or '' # sync_id_api dari dhealth
                        # row["order_date"] = datetime.strptime(str(bill.admission_id.date_order) or str(bill.confirmation_date), "%Y-%m-%d %H:%M:%S") # tgl pendaftaran
                        date_source = bill.admission_id.date_order or bill.confirmation_date
                        row["order_date"] = date_source.strftime("%Y-%m-%d %H:%M:%S") if date_source else None
                        row["order_no"] = bill.admission_id.name or bill.admission_no # nomor pendaftaran
                        row["bill_id"] = bill.id # id sale.order.bill yg dari odoo
                        # row["cob_id"] = bill.id # id sale.order.cob spesific for multi payer cob
                        row["bill_sync_id_api"] = bill.sync_id_api or '' # sync_id_api dari dhealth
                        # row["bill_date"] = datetime.strptime((str(bill.confirmation_date) or str(bill.admission_id.date_order)), "%Y-%m-%d %H:%M:%S") # tgl billing
                        date_source = bill.confirmation_date or bill.admission_id.date_order
                        row["bill_date"] = date_source.strftime("%Y-%m-%d %H:%M:%S") if date_source else None
                        row["bill_no"] = bill.billno # nomor billing
                        row["payer_id"] = bill.payer_id.id # id asuransi odoo
                        row["payer_code"] = bill.payer_id.vendor_code # kode asuransi
                        row["payer_name"] = bill.payer_id.name # nama asuransi
                        row["payer_sync_id_api"] = bill.payer_id.sync_id_api # id_sync_api asuransi dhealth
                        row["patient_type"] = ("IPD" if bill.patient_type == '2' else "OPD" if bill.patient_type == "1" else "IGD" if bill.patient_type == "3" else "MCU" if bill.patient_type == "5" else "OPD") # patient_type OPD, IPD, IGD, MCU
                        row["patient_id"] = bill.partner_id.id # id pasien di odoo
                        row["patient_sync_id_api"] = bill.partner_id.sync_id_api # sync_id_api pasien dr dhealth
                        row["patient_regcode"] = bill.partner_id.registration_code # nomor MR pasien
                        row["patient_name"] = bill.partner_id.name # nama pasien
                        row["total_amount"] = bill.total_amount # total nett billing
                        row["payer_amount"] = bill.payer_amount # total nett tagihan payer
                        row["personal_amount"] = bill.personal_amount # total nett tagihan pasien
                        details.append(row)

            # Jika CL based on COB Bill
            elif record.billing_type == 'cob':
                for cob in record.billing_cob_ids:
                    if cob.sync_id_api:
                        row = {}
                        row["order_id"] = cob.admission_id.id # id sale.order yg dari odoo
                        row["order_sync_id_api"] = cob.admission_id.sync_id_api or '' # sync_id_api dari dhealth
                        row["order_date"] = cob.admission_id.date_order.strftime("%Y-%m-%d %H:%M:%S") # tgl pendaftaran
                        row["order_no"] = cob.admission_id.name # nomor pendaftaran
                        row["cob_id"] = cob.id # id sale.order.cob spesific for multi payer cob
                        row["cob_no"] = cob.cob_no # id sale.order.cob spesific for multi payer cob
                        row["cob_date"] = cob.cob_date.strftime("%Y-%m-%d %H:%M:%S") # tgl cob
                        row["cob_sync_id_api"] = cob.sync_id_api #id sale.order.cob fot multi payer
                        row["bill_id"] = cob.billing_id.id # id sale.order.bill yg dari odoo
                        row["bill_sync_id_api"] = cob.billing_id.sync_id_api or '' # sync_id_api dari dhealth
                        # row["bill_date"] = datetime.strptime((str(cob.confirmation_date) or str(cob.admission_id.date_order)), "%Y-%m-%d %H:%M:%S") # tgl billing
                        date_source = cob.confirmation_date or cob.admission_id.date_order
                        row["bill_date"] = date_source.strftime("%Y-%m-%d %H:%M:%S") if date_source else None
                        row["bill_no"] = cob.billing_id.billno # nomor billing
                        row["payer_id"] = cob.payer_id.id # id asuransi odoo
                        row["payer_code"] = cob.payer_id.vendor_code # kode asuransi
                        row["payer_name"] = cob.payer_id.name # nama asuransi
                        row["payer_sync_id_api"] = cob.payer_id.sync_id_api # id_sync_api asuransi dhealth
                        row["patient_type"] = ("IPD" if cob.billing_id.patient_type == '2' else "OPD" if cob.billing_id.patient_type == "1" else "IGD" if cob.billing_id.patient_type == "3" else "MCU" if cob.billing_id.patient_type == "5" else "OPD") # patient_type OPD, IPD, IGD, MCU
                        row["patient_id"] = cob.billing_id.partner_id.id # id pasien di odoo
                        row["patient_sync_id_api"] = cob.billing_id.partner_id.sync_id_api # sync_id_api pasien dr dhealth
                        row["patient_regcode"] = cob.billing_id.partner_id.registration_code # nomor MR pasien
                        row["patient_name"] = cob.billing_id.partner_id.name # nama pasien
                        row["payer_amount"] = cob.payer_amount # total nett billing
                        details.append(row)

            payload['details'] = details
        return payload

    
    # @api.multi
    def action_cancel(self):
        # LOCK AR
        lock_date = self.env['lock.ar.configuration'].sudo().search([('company_id', '=', self.company_id.id)], limit=1).date
        if lock_date:
            if self.date <= lock_date:
                raise exceptions.UserError(_('You cannot add/modify AR record prior to and inclusive of the lock date "%s".') % (lock_date))

        if self.journal_ids:
            for journal in self.journal_ids:
                journal.button_cancel()
                journal.unlink()

        # Jika CL based on billing
        if self.billing_type == 'bill':
            for bill in self.billing_sale_ids:
                if bill.state == 'invoice':
                     bill.state = 'done'
                bill.payer_adjustment = 0
                bill.payer_credit =  0
                bill.payer_balance = (0) - (bill.payer_receipt or 0) - (bill.payer_discount or 0)
                # bill.action_history(remark="CANCEL " + self.name)
                bill.cancel_history(letter_id=self.id)

        # Jika CL based on split billing COB
        elif self.billing_type == 'cob':
            for bill in self.billing_cob_ids:
                if bill.state == 'invoice':
                     bill.state = 'done'
                bill.payer_adjustment = 0
                bill.payer_credit =  0
                bill.payer_balance = (0) - (bill.payer_receipt or 0) - (bill.payer_discount or 0)
                # bill.action_history(remark="CANCEL " + self.name)
                bill.cancel_history(letter_id=self.id)

        # Jika CL based on Admission No.
        elif self.billing_type == 'admission':
            for bill in self.billing_ids:
                if bill.state == 'invoice':
                     bill.state = 'done'
                bill.payer_adjustment = 0
                bill.payer_credit =  0
                bill.payer_balance = (0) - (bill.payer_receipt or 0) - (bill.payer_discount or 0)


        # send cancel payload
        self.action_cancel_api()
        self.state = 'cancel'


    # @api.multi
    def action_cancel_api(self):
        for record in self:
            # api unfreeze bills
            # kondisi CL sudah di confirn maka bisa send "cancel"
            # kondisi CL sudah "cancel" tapi gagal submit ke dhealth, maka bisa resend 
            if self.company_id.sync_api_active == True and ((record.state == 'cancel' and record.api_post_status_cancel != 'done') or record.state=='confirm'):
                api_payload = self.generate_payload('cancel')
                api_endpoint = self.company_id.his_api_url + '/on/freezebilling/create'
                api_headers = {'Content-Type': 'application/json', 'X-Behaviour':'blocking', 'Authorization': 'Basic ' + self.company_id.his_api_key }

                # open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n' + str(api_headers) + '\n' + str(api_payload))
                response_json = requests.post(url=api_endpoint, headers=api_headers, json=api_payload, verify=False)
                json_resp = response_json.json()
                open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n' + str(json_resp))
                api_post_status = 'failed'
                if 'status' in json_resp:
                    api_post_status = ('done' if json_resp['status'] == 'success' else 'failed')
                now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                data = {'api_post_payload_cancel': api_payload, 'api_post_response_cancel': json_resp, 'api_post_timestamp_cancel': now, 'api_post_status_cancel': api_post_status}
                write_result = super(CoveringLetter, self).write(data)


    # @api.multi
    def action_confirm(self):
        # LOCK AR
        lock_date = self.env['lock.ar.configuration'].sudo().search([('company_id', '=', self.company_id.id)], limit=1).date
        if lock_date:
            if self.date <= lock_date:
                raise exceptions.UserError(_('You cannot add/modify entries prior to and inclusive of the lock date "%s".') % (lock_date))

        if self.letter_discount:
            if self.letter_discount_percent < 0 or self.letter_discount_percent > 100:
                raise exceptions.UserError("Letter discount range must set to 0-100 (%)")

        # 2021.08.19 - Crosscheck ada billing yang sudah status invoice atau belum ??
        if self.billing_type == 'bill' and self.sync_id == 0:
            for bill in self.billing_sale_ids:
                if bill.state == 'invoice':
                    raise exceptions.UserError(_('You cannot add/modify bill "%s" cause it was invoiced before.') % (bill.billno))
        
        if self.billing_type == 'cob' and self.sync_id == 0:
            for bill in self.billing_cob_ids:
                if bill.state == 'invoice':
                    raise exceptions.UserError(_('You cannot add/modify bill "%s" cause it was invoiced before.') % (bill.cob_no))
        
        if self.billing_type == 'admission' and self.sync_id == 0:
            for bill in self.billing_ids:
                if bill.state == 'invoice':
                    raise exceptions.UserError(_('You cannot add/modify bill "%s" cause it was invoiced before.') % (bill.billno))

        # 2022.11.01 - update number of covering letter
        if not self.name:
            if self.company_id.name == 'Mayapada Hospital Bogor':
                self.name = self.env['ir.sequence'].sudo().next_by_code('account.coveringletter.seq.mhbg')
            else:
                self.name = self.env['ir.sequence'].sudo().next_by_code('account.coveringletter.seq')

        if not self.journal_ids:
            # self.total_covering_letter = 0
            self._compute_total()
            
            line_ids = []
            journal_id = self.env['account.journal'].search([('name', 'like', 'Payer Covering Letter'), ('company_id', '=', self.company_id.id)], limit=1)
            account_private = self.env['account.account'].search([('code', 'like', '1104020101'), ('company_id', '=', self.company_id.id)], limit=1)
            account_discount = self.letter_discount_account 
            analytic_discount = self.letter_discount_analytic
            line_ids = []

            # 2022.01.31 - Ambil COA Credit dari res.company untuk seluruh CL > 31-Jan-2022
            if (self.date).strftime('%Y-%m-%d') > '2022-01-31':
                account_private = self.company_id.receivable_credit_id
            
            debit_vals = {
                'name': self.name,
                'date_maturity': (self.due_date).strftime('%Y-%m-%d'),
                'covering_letter': self.name,
                'covering_id': self.id,
                'debit': abs(self.total_covering_letter),
                'credit': 0.0,
                'partner_id': self.payer.id,
                'account_id': self.payer.account_ar_id.id,
            }
            credit_vals = {
                'name': self.name,
                'date_maturity': (self.due_date).strftime('%Y-%m-%d'),
                'covering_letter': self.name,
                'covering_id': self.id,
                'debit': 0.0,
                'credit': abs(self.total_covering_letter),
                'partner_id': self.payer.id,
                'account_id': account_private.id
            }
            line_ids.append((0, 0, debit_vals))
            line_ids.append((0, 0, credit_vals))
            open('/opt/odoo16/logs/dudi.log','a+').write('\n'+str("dudi"))
            open('/opt/odoo16/logs/dudi.log','a+').write('\n'+str(line_ids))
            # jika ada discount 
            if self.letter_discount:
                # open('/opt/odoo16/logs/log_covering_letter.log','a+').write('\n'+str(analytic_discount.id))
                
                debit_vals2 = {
                    'name': self.name + ' - DISCOUNT INVOICE',
                    'date_maturity': (self.due_date).strftime('%Y-%m-%d'),
                    'covering_letter': self.name,
                    'covering_id': self.id,
                    'debit': abs(self.total_adjustment),
                    'credit': 0.0,
                    'partner_id': self.payer.id,
                    'account_id': account_discount.id,
                    'analytic_account_id': analytic_discount.id 
                }
                # open('/opt/odoo16/logs/log_covering_letter.log','a+').write('\n'+str(debit_vals2))

                credit_vals2 = {
                    'name': self.name + ' - DISCOUNT INVOICE',
                    'date_maturity': (self.due_date).strftime('%Y-%m-%d'),
                    'covering_letter': self.name,
                    'covering_id': self.id,
                    'debit': 0.0,
                    'credit': abs(self.total_adjustment),
                    'partner_id': self.payer.id,
                    'account_id': account_private.id
                }

                line_ids.append((0, 0, debit_vals2))
                line_ids.append((0, 0, credit_vals2))

            vals = {'journal_id': journal_id.id, 'date': (self.date).strftime('%Y-%m-%d'), 'state': 'draft', 'ref': self.name, 'covering_id': self.id, 'partner_id': self.payer.id, 'line_ids': line_ids}
            move = self.env['account.move'].create(vals)
            move.action_post()

            # Jika CL based on billing
            if self.billing_type == 'bill':
                for bill in self.billing_sale_ids:
                    bill.state = 'invoice'
                    bill.payer_adjustment = ((bill.payer_amount * self.letter_discount_percent / 100) if self.letter_discount else 0)
                    bill.payer_credit = (bill.payer_amount or 0) - (bill.payer_adjustment or 0)
                    bill.payer_balance = (bill.payer_credit or 0) - (bill.payer_receipt or 0) - (bill.payer_discount or 0)
                    bill.action_history(remark="CONFIRM " + self.name, trans_date=self.date, letter_id=self.id)

            # Jika CL based on split billing COB
            elif self.billing_type == 'cob':
                for bill in self.billing_cob_ids:
                    bill.state = 'invoice'
                    bill.payer_adjustment = ((bill.payer_amount * self.letter_discount_percent / 100) if self.letter_discount else 0)
                    bill.payer_credit = (bill.payer_amount or 0) - (bill.payer_adjustment or 0)
                    bill.payer_balance = (bill.payer_credit or 0) - (bill.payer_receipt or 0) - (bill.payer_discount or 0)
                    bill.action_history(remark="CONFIRM " + self.name, trans_date=self.date, letter_id=self.id)

            # Jika CL based on Admission No.
            elif self.billing_type == 'admission':
                for bill in self.billing_ids:
                    bill.state = 'invoice'
                    bill.payer_adjustment = ((bill.payer_amount * self.letter_discount_percent / 100) if self.letter_discount else 0)
                    bill.payer_credit = (bill.payer_amount or 0) - (bill.payer_adjustment or 0)
                    bill.payer_balance = (bill.payer_credit or 0) - (bill.payer_receipt or 0) - (bill.payer_discount or 0)

        # Post Freeze AR Wipro
        self.action_confirm_api()
        self.state = 'confirm'


    # @api.multi
    def action_confirm_api(self):
        for record in self:
            # post api freeze bills
            # kondisi CL masih "draft" maka bisa send "confirm"
            # kondisi CL sudah "confirm" tapi gagal submit ke dhealth, maka bisa resend
            if self.env.company.sync_api_active == True and ((record.state == 'confirm' and record.api_post_status != 'done') or record.state == 'draft'):
                api_payload = self.generate_payload('confirm')
                api_endpoint = self.company_id.his_api_url + '/on/freezebilling/create'
                api_headers = {'Content-Type': 'application/json', 'X-Behaviour':'blocking', 'Authorization': 'Basic ' + self.company_id.his_api_key }
                open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n' + str(api_headers) + '\n' + str(api_payload))
               
                response_json = requests.post(url=api_endpoint, headers=api_headers, json=api_payload, verify=False)
                json_resp = response_json.json()
                api_post_status = 'failed'
                if 'status' in json_resp:
                    api_post_status = ('done' if json_resp['status'] == 'success' else 'failed')
                now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                data = {'api_post_payload': api_payload, 'api_post_response': json_resp, 'api_post_timestamp': now, 'api_post_status': api_post_status}
                write_result = super(CoveringLetter, self).write(data)


    @api.depends('billing_ids','billing_sale_ids','billing_cob_ids')
    def _compute_other(self):
        self._compute_total()
            

    # @api.multi
    def _compute_total(self):
        if self.letter_discount:
            if self.letter_discount_percent < 0 or self.letter_discount_percent > 100:
                raise exceptions.UserError("Letter discount range must set to 0-100 (%)")

        for r in self:
            # reset balance dari total_covering_letter
            r.total_balance_amount = r.total_covering_letter

            # Jika CL based on billing
            if r.billing_type == 'bill':
                if r.billing_sale_ids:
                    r.total_covering_letter = 0
                    r.total_balance_amount = 0
                    for invoice in r.billing_sale_ids:
                        r.total_covering_letter += invoice.payer_amount
                        r.total_balance_amount += invoice.payer_amount

            # Jika CL based on split billing COB
            elif r.billing_type == 'cob':
                if r.billing_cob_ids:
                    r.total_covering_letter = 0
                    r.total_balance_amount = 0
                    for invoice in r.billing_cob_ids:
                        r.total_covering_letter += invoice.payer_amount
                        r.total_balance_amount += invoice.payer_amount

            # Jika CL based on admission No
            elif r.billing_type == 'admission':
                if r.billing_ids:
                    r.total_covering_letter = 0
                    r.total_balance_amount = 0
                    for invoice in r.billing_ids:
                        r.total_covering_letter += invoice.payer_amount
                        r.total_balance_amount += invoice.payer_amount

            r.total_billing = r.total_covering_letter 
            r.total_adjustment = ((r.total_covering_letter * r.letter_discount_percent / 100) if r.letter_discount else 0)
            r.total_covering_letter -= r.total_adjustment
            r.total_balance_amount -= r.total_adjustment
            r.total_balance_amount -= r.total_payment
            r.total_balance_amount -= r.total_discount



    # @api.multi
    def action_compute_balance(self):
        if self.letter_discount:
            if self.letter_discount_percent < 0 or self.letter_discount_percent > 100:
                raise exceptions.UserError("Letter discount range must set to 0-100 (%)")

        for head in self:
            head.total_discount = 0
            head.total_payment = 0
            head.total_balance_amount = 0

            # Jika CL based on billing
            if head.billing_type == 'bill':
                if head.billing_sale_ids:
                    head.total_covering_letter = 0
                    head.total_covering_letter = sum(line.payer_amount for line in head.billing_sale_ids)
                    # for line in head.billing_sale_ids:
                        # head.total_covering_letter += line.payer_amount
                        
            # Jika CL based on split billing COB
            elif head.billing_type == 'cob':
                if head.billing_cob_ids:
                    head.total_covering_letter = 0
                    head.total_covering_letter = sum(line.payer_amount for line in head.billing_cob_ids)
                    # for line in head.billing_cob_ids:
                    #     head.total_covering_letter += line.payer_amount

            # Jika CL based on Admission No.
            elif head.billing_type == 'admission':
                if head.billing_ids:
                    head.total_covering_letter = 0
                    head.total_covering_letter = sum(line.payer_amount for line in head.billing_ids)                    
                    # for line in head.billing_ids:
                    #     head.total_covering_letter += line.payer_amount

            if head.creditnote_ids:
                for line in head.creditnote_ids:
                    if line.state == 'confirm':
                        head.total_discount += line.total_discount

            if head.receipt_ids:
                for line in head.receipt_ids:
                    if line.state in ['posted','sent','reconciled']:
                        head.total_payment += line.amount

            if head.advance_realization_ids:
                for line in head.advance_realization_ids:
                    if line.state in ['confirm']:
                        head.total_payment += line.amount_receipt

            head.total_balance_amount = head.total_covering_letter
            head.total_billing = head.total_covering_letter 
            head.total_adjustment = ((head.total_covering_letter * head.letter_discount_percent / 100) if head.letter_discount else 0)
            head.total_covering_letter -= head.total_adjustment
            head.total_balance_amount -= head.total_adjustment
            head.total_balance_amount -= head.total_payment
            head.total_balance_amount -= head.total_discount

            if head.total_balance_amount <= 0 and head.state == 'confirm':
                head.total_balance_amount = 0
                head.state = 'paid'
            else:
                if head.journal_ids:
                    head.state = 'confirm'
                # else:
                #     head.state = 'draft'


    # @api.multi
    def action_export(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/report/covering_letter_billing?id=' + str(self.id)
        action['target'] = 'new'
        return action
    
    # @api.multi
    def action_print_cover(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/report/covering_letter?format=pdf&id=' + str(self.id)
        action['target'] = 'new'
        return action

    # @api.multi
    def action_print_cover_doc(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/report/covering_letter?format=doc&id=' + str(self.id)
        action['target'] = 'new'
        return action

    # @api.multi
    def action_print_tanda_terima(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/report/covering_letter_tanda_terima?format=pdf&id=' + str(self.id)
        action['target'] = 'new'
        return action
    

    # @api.multi
    def action_kwitansi(self):
        action = {}
        action['target'] = 'new'
        action['type'] = 'ir.actions.act_window'
        action['view_mode'] = 'form'
        action['view_type'] = 'form'
        action['res_model'] = 'account.coveringletter.wizard'
        action['name'] = 'Print Kwitansi Wizard'
        action['views'] = [(self.sudo().env.ref('mayapada.print_kwitansi_wizard').id, 'form'),(False, 'pivot'), (False, 'tree')]
        action['context'] = {
            'default_letter_id': self.id,
            'default_name': self.name,
            'default_payer': self.payer.id, 
            'default_date': self.date, 
            'default_address_id': self.address_id.id or None, 
            'default_total_covering_letter': self.total_covering_letter,
        }
        return action


    # @api.multi
    # def action_print_bill(self):
    #     action = {}
    #     action['type'] = 'ir.actions.act_url'
    #     action['url'] = '/report/coveringletter_billing?id=' + str(self.id)
    #     action['target'] = 'new'
    #     return action

    @api.model
    def create(self, vals):
        result = super(CoveringLetter, self).create(vals)
        result.draft_no = self.env['ir.sequence'].sudo().next_by_code('account.draftletter.seq')
        # result.name = self.env['ir.sequence'].sudo().next_by_code('account.coveringletter.seq')

        # 2021.10.21 - ambil VA config per payer baru per company
        if result.payer.virtual_enable:
            result.virtual_enable = result.payer.virtual_enable
            result.virtual_beneficary = result.payer.virtual_beneficary
            result.virtual_number = result.payer.virtual_number
            result.virtual_bank = result.payer.virtual_bank.id 
        elif result.company_id.virtual_enable:
            result.virtual_enable = result.company_id.virtual_enable
            result.virtual_beneficary = result.company_id.virtual_beneficary
            result.virtual_number = result.company_id.virtual_number + str(result.draft_no[-8:])
            result.virtual_bank = result.company_id.virtual_bank.id 
        self._compute_total()
        return result


    # @api.model
    # def get_view(self,view_id=None, view_type='form', **options):
    #     res = super(CoveringLetter,self).get_view(view_id=view_id,view_type=view_type, **options)        
    #     if view_type == 'tree':
    #         res['arch'] = """
    #             <tree string="Covering Letter" delete="false" decoration-muted="state == 'cancel'" decoration-info="state == 'draft'" decoration-success="state == 'confirm'">
    #                 <field name="draft_no"/>
    #                 <field name="name"/>
    #                 <field name="date"/>
    #                 <field name="sent_date"/>
    #                 <field name="due_date" invisible="1"/>
    #                 <field name="payer"/>
    #                 <field name="total_covering_letter" string="Invoice Amt." sum="Total CL"/>
    #                 <field name="total_payment" invisible="1" string="Receipt Amt." sum="Total Receipt"/>
    #                 <field name="total_discount" invisible="1" string="Disc Amt." sum="Total Discount"/>
    #                 <field name="total_balance_amount" string="Balance" sum="Total Balance"/>
    #                 <field name="state" string="Status"/>
    #                 <field name="remark"/>
    #             </tree>
    #         """
    #     elif view_type == 'search':
    #         res['arch'] = """
    #             <search string="CL Search">
    #                 <filter string="Draft" domain="[('state','=', 'draft')]" help="Draft"/>
    #                 <filter string="Confirm" domain="[('state','=', 'confirm')]" help="Confirm"/>
    #                 <filter string="Paid" domain="[('state','=', 'paid')]" help="Paid"/>
    #                 <filter string="Cancelled" domain="[('state','=', 'cancel')]" help="Cancelled"/>
    #                 <separator/>
    #                 <field name="receipt_ids"/>
    #                 <field name="creditnote_ids"/>
    #                 <field name="draft_no"/>
    #                 <field name="name"/>
    #                 <field name="payer"/>
    #                 <field name="remark"/>
    #             </search>
    #         """
    #     from lxml import etree
    #     doc = etree.XML(res['arch'])
    #     View = self.env['ir.ui.view'].sudo()
    #     res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
    #     return res





class CreditNote(models.Model):
    _name = 'account.creditnote'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_id = sync.id
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    name = fields.Char(string="Number", readonly=True, index=True)
    covering_letter_name = fields.Char(string="Covering Letter No.", readonly=True, store=True, index=True, related='letter_id.name')
    date = fields.Date(string="Date", required=True, index=True, states={'confirm': [('readonly', True)], 'cancel': [('readonly', True)]})
    total_discount = fields.Float(string="Total Discount", states={'confirm': [('readonly', True)], 'cancel': [('readonly', True)]})
    remark = fields.Char(string="Notes", states={'confirm': [('readonly', True)], 'cancel': [('readonly', True)]})
    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm'),  ('cancel', 'Cancel')], 'Status', default='draft', index=True, required=True, readonly=True, copy=False, tracking=True, store=True)
    payer_id = fields.Many2one('res.partner', string="Payer Name", index=True, domain="[('customer_wipro','=',True),('account_ar_id','!=',False)]", states={'confirm': [('readonly', True)], 'cancel': [('readonly', True)]})
    letter_id = fields.Many2one('account.coveringletter', string="Letter No.", domain="[('payer.id','=',payer_id),('state','=','confirm')]", index=True, states={'confirm': [('readonly', True)], 'cancel': [('readonly', True)]})
    letter_duedate = fields.Date(string="Letter Due date", related="letter_id.due_date", store=True)
    company_id = fields.Many2one('res.company', string="Company", readonly=True, required=True, default=_get_company)
    creditnote_line_ids = fields.One2many('account.creditnote.line', 'creditnote_id', string="Billing", states={'confirm': [('readonly', True)], 'cancel': [('readonly', True)]})
    journal_ids = fields.One2many('account.move', 'creditnote_id', string="Journal", readonly=True)
    billing_type = fields.Selection([('bill', 'Billing'),('cob', 'COB Bill'), ('admission','Admission')], default="bill", string="Based On",required=True)
    debit_account_id = fields.Many2one('account.account', string="Againts Account")
    debit_account_code = fields.Char(string="Againts Account (Code)", related="debit_account_id.code", readonly=True, store=False)
    debit_analytic_id = fields.Many2one('account.analytic.account', string="Againts Analytic")
    settlement_type = fields.Selection([('rate','Rate Percentage'), ('amount','Total Amount')], string="Settlement Type")
    settlement_rate = fields.Float(string="Settlement Rate")
    message_last_post = fields.Datetime(string="Message Last Post", index=True, readonly=True)

    def action_open_import_wizard(self):
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError(_("Excel import is only available for Draft Credit Notes."))
        if not self.letter_id:
            raise ValidationError(_("Please select a Covering Letter before importing."))
        if self.billing_type != 'bill':
            raise ValidationError(_("Credit Note Excel import currently supports Bill billing type only."))

        action = self.env.ref('mayapada.account_creditnote_import_wizard_action').read()[0]
        action['context'] = {
            'default_creditnote_id': self.id,
            'active_id': self.id,
            'active_model': self._name,
        }
        return action

    # @api.multi 
    def action_show_billing(self):
        for record in self:
            if record.state == 'draft' and record.letter_id:
                # delete payment if exists
                self.env.cr.execute("""
                    delete from account_creditnote_line 
                    where creditnote_id={credit_id}
                """.format(credit_id=record.id))

                if record.billing_type == 'bill':
                
                    # insert new billing from MHCL 
                    self.env.cr.execute("""
                        insert into account_creditnote_line (
                            creditnote_id, billing_type, cover_id, 
                            billing_sale_id, billing_amount, payer_ending) 
                        select 
                            {credit_id} as creditnote_id, 
                            '{credit_type}' as credit_type,
                            a.account_coveringletter_id as cover_id, 
                            a.sale_order_bill_id as billing_sale_id,
                            b.payer_balance billing_amount,
                            b.payer_balance payer_ending
                        from account_coveringletter_bill_rel a 
                        inner join sale_order_bill b on b.id = a.sale_order_bill_id 
                        where a.account_coveringletter_id = {letter_id}
                            and b.payer_balance <> 0
                    """.format(
                        credit_id=record.id, 
                        credit_type=record.billing_type,
                        letter_id=record.letter_id.id
                    ))


                if record.billing_type == 'cob':

                    # insert new billing from MHCL 
                    self.env.cr.execute("""
                        insert into account_creditnote_line (
                            creditnote_id, billing_type, cover_id, billing_cob_id) 
                        select 
                            {credit_id} as creditnote_id, 
                            '{credit_type}' as credit_type,
                            a.account_coveringletter_id as cover_id, 
                            a.sale_order_cob_id as billing_cob_id
                        from account_coveringletter_cob_rel a 
                        inner join sale_order_cob b on b.id = a.sale_order_cob_id  
                        where a.account_coveringletter_id = {letter_id}
                    """.format(
                        credit_id=record.id, 
                        credit_type=record.billing_type,
                        letter_id=record.letter_id.id
                    ))
                   

                if record.billing_type == 'admission':
                    # insert new billing from MHCL 
                    self.env.cr.execute("""
                        insert into account_creditnote_line (
                            creditnote_id, billing_type, cover_id, billing_id) 
                        select 
                            {credit_id} as creditnote_id, 
                            '{credit_type}' as credit_type,
                            a.account_coveringletter_id as cover_id, 
                            a.sale_order_id as billing_id
                        from account_coveringletter_admission_rel a 
                        inner join sale_order b on b.id = a.sale_order_id   
                        where a.account_coveringletter_id = {letter_id}
                    """.format(
                        credit_id=record.id, 
                        credit_type=record.billing_type,
                        letter_id=record.letter_id.id
                    ))
                    

            else:
                raise exceptions.ValidationError("Hanya Discount dengan status Draft dan Letter yang sudah dipilih yang dapat di settlement.")
                

    # @api.multi 
    def action_apply_settlement(self):
        for record in self:
            if record.settlement_type and record.settlement_rate and record.state == 'draft':
                total_writeoff = record.settlement_rate
                
                total_discount_tmp = 0
                for bill in record.creditnote_line_ids:
                    if record.settlement_type == 'rate':
                        bill.discount_percent = total_writeoff
                        bill.amount_discount = (bill.billing_amount * total_writeoff / 100.0)
                        bill.payer_ending = bill.billing_amount - (bill.billing_amount * total_writeoff / 100.0)
                        total_discount_tmp += bill.amount_discount

                    elif record.settlement_type == 'amount':
                        if total_writeoff >= bill.billing_amount:
                            bill.discount_percent = 0
                            bill.amount_discount = bill.billing_amount
                            bill.payer_ending = 0
                            total_writeoff -= bill.billing_amount
                            total_discount_tmp += bill.amount_discount
                        else:
                            bill.discount_percent = 0
                            bill.amount_discount = total_writeoff
                            bill.payer_ending = bill.billing_amount - total_writeoff
                            total_writeoff = 0
                            total_discount_tmp += bill.amount_discount                

                record.total_discount = total_discount_tmp

            else:
                raise exceptions.ValidationError("Please choose settlement type & rate before.")
               

    # @api.multi
    def write(self, vals):
        result = super(CreditNote, self).write(vals)
        if self.env.context.get('sudah_total'): return result
        self = self.with_context(sudah_total=True)

        if self.company_id.cost_center_active:
            if not self.company_id.cost_center_date or not self.date:
                raise UserError(_("Tanggal tidak boleh kosong."))
        if not self.debit_analytic_id and self.company_id.cost_center_active and self.company_id.cost_center_date <= self.date:
            account_code = self.debit_account_id.code
            if (account_code[:1] in ['4','5','6','7','8','9'] and account_code[:4] not in ['6901','6902','5100']):
                raise exceptions.ValidationError("Account code {code} harus dimapping dengan Cost Center Analytic".format(code=self.debit_account_id.code + " " + self.debit_account_id.name))
                
        if self.creditnote_line_ids:
            self.total_discount = 0
            for line in self.creditnote_line_ids:
                self.total_discount += line.amount_discount
        return result


    @api.onchange('letter_id')
    def _domain_billing(self):
        res={}
        if self.letter_id:
            self.billing_type = self.letter_id.billing_type
        return res


    # @api.multi
    def action_print_cn(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/report/credit_note?id=' + str(self.id)
        action['target'] = 'new'
        return action


    @api.model
    def create(self, vals):
        result = super(CreditNote, self).create(vals)
        result.name = self.env['ir.sequence'].sudo().next_by_code('account.creditnote.seq')
        if result.creditnote_line_ids:
            result.total_discount = 0
            for line in result.creditnote_line_ids:
                result.total_discount += line.amount_discount
        return result


    # @api.multi
    def action_cancel(self):
        # LOCK AR
        lock_date = self.env['lock.ar.configuration'].sudo().search([('company_id', '=', self.company_id.id)], limit=1).date
        if self.date <= lock_date:
            raise exceptions.UserError(_('You cannot add/modify AR record prior to and inclusive of the lock date "%s".') % (lock_date))

        self.state = 'cancel'
        if self.journal_ids:
            for journal in self.journal_ids:
                journal.button_cancel()
                journal.unlink()

        # Create By Dudi 2021/03/09
        if self.creditnote_line_ids:
            for cl in self.creditnote_line_ids:
                # Jika CL based on admission
                if cl.billing_type == 'admission':
                    cl.billing_id.payer_discount -= cl.amount_discount or 0 
                    cl.billing_id.payer_balance += cl.amount_discount or 0
                
                # Jika CL based on split billing COB
                elif cl.billing_type == 'cob':
                    cl.billing_cob_id.payer_discount -= cl.amount_discount or 0 
                    cl.billing_cob_id.payer_balance += cl.amount_discount or 0
                    # cl.billing_cob_id.action_history(remark="CANCEL " + self.name)
                    if (cl.amount_discount or 0) != 0:
                        cl.billing_cob_id.cancel_history(credit_id=self.id)
                
                # Jika CL based on Billing
                elif cl.billing_type == 'bill':
                    cl.billing_sale_id.payer_discount -= cl.amount_discount or 0 
                    cl.billing_sale_id.payer_balance += cl.amount_discount or 0
                    # cl.billing_sale_id.action_history(remark="CANCEL " + self.name)
                    if (cl.amount_discount or 0) != 0:
                        cl.billing_sale_id.cancel_history(credit_id=self.id)
        # recompute CL No.
        self.letter_id.action_compute_balance()


    # @api.multi
    def action_cancel_call(self):
        for record in self:
            if record.state == 'draft':
                record.state = 'cancel'
    
    # @api.multi
    def action_draft(self):
        for record in self:
            if record.state == 'cancel':
                record.state = 'draft'

    # @api.multi
    def action_confirm(self):
        # open('/opt/odoo16/logs/dudi.log','a+').write('\n ' + str("MASUK bill 0000"))
        # LOCK AR
        lock_date = self.env['lock.ar.configuration'].sudo().search([('company_id', '=', self.company_id.id)], limit=1).date
        if self.date <= lock_date:
            raise exceptions.UserError(_('You cannot add/modify AR record prior to and inclusive of the lock date "%s".') % (lock_date))

        if self.creditnote_line_ids:
            self._compute_total()

        # open('/opt/odoo16/logs/dudi.log','a+').write('\n ' + str("MASUK bill 1111"))
        self.state = 'confirm'
        # Tambahin validasi jika total CN melebihi total_balance di CL
        # Suka ada masalah di service auto-confirm receipt
        # Jika MHCL itu tarikan dari Wipro (skip ngg usah validasi u/ cek balance)
        if self.letter_id.sync_id or self.sync_id:
            print("Skip validasi Balance Karena ini data MHCL Wipro.")
        else:    
            if self.letter_id.total_balance_amount < self.total_discount:
                raise exceptions.ValidationError("Total discount exceeds balance of covering letter.")

        # create journal ids
        # open('/opt/odoo16/logs/dudi.log','a+').write('\n ' + str("MASUK bill 33333"))
        # open('/opt/odoo16/logs/dudi.log','a+').write('\n ' + str("self.journal_ids: " + str(self.journal_ids)))
        if not self.journal_ids:
            # open('/opt/odoo16/logs/dudi.log','a+').write('\n ' + str("MASUK bill 44444444"))
            covering_letter = self.covering_letter_name if not self.letter_id else self.letter_id.name  
            journal_id = self.env['account.journal'].search([('name', 'like', 'Credit Note'),('company_id', '=', self.company_id.id)],limit=1)
            
            if not journal_id:
                raise exceptions.ValidationError("Please create Master Journal with name Credit Note")
            if not self.debit_account_id:
                account_cn = self.env['account.account'].search([('code', 'like', '7999000000'),('company_id', '=', self.company_id.id)],limit=1)
            else:
                account_cn = self.debit_account_id
            
                # open('/opt/odoo16/logs/dudi.log','a+').write('\n ' + str("MASUK bill 555555555"))
            # jika debit note
            if self.total_discount < 0:
                credit_vals = {'date_maturity': self.letter_duedate, 'name': covering_letter, 'debit': abs(self.total_discount), 'covering_letter': covering_letter, 'covering_id': self.letter_id.id or None, 'creditnote_id': self.id or None, 'credit': 0.0, 'partner_id': self.payer_id.id, 'account_id': self.payer_id.account_ar_id.id}
                debit_vals = {'date_maturity': self.letter_duedate, 'name': covering_letter, 'debit': 0.0, 'covering_letter': covering_letter, 'covering_id': self.letter_id.id or None, 'creditnote_id': self.id or None, 'credit': abs(self.total_discount), 'partner_id': self.payer_id.id, 'account_id': account_cn.id, 'analytic_account_id': self.debit_analytic_id.id or False}
            
                # open('/opt/odoo16/logs/dudi.log','a+').write('\n ' + str("MASUK bill 6666666"))
            # jika credit note
            elif self.total_discount > 0:
                debit_vals = {'date_maturity': self.letter_duedate, 'name': covering_letter, 'debit': abs(self.total_discount), 'covering_letter': covering_letter, 'covering_id': self.letter_id.id or None, 'creditnote_id': self.id or None, 'credit': 0.0, 'partner_id': self.payer_id.id, 'account_id': account_cn.id, 'analytic_account_id': self.debit_analytic_id.id or False}
                credit_vals = {'date_maturity': self.letter_duedate, 'name': covering_letter, 'debit': 0.0, 'covering_letter': covering_letter, 'covering_id': self.letter_id.id or None, 'creditnote_id': self.id or None, 'credit': abs(self.total_discount), 'partner_id': self.payer_id.id, 'account_id': self.payer_id.account_ar_id.id}
            vals = {'journal_id': journal_id.id, 'date': self.date, 'state': 'draft', 'ref': self.name, 'creditnote_id': self.id, 'line_ids': [(0, 0, debit_vals), (0, 0, credit_vals)]}

            # Create By Dudi 2021/03/09
            if self.creditnote_line_ids:
                # raise exceptions.ValidationError("masuk creditnote_line_ids1111")
                # open('/opt/odoo16/logs/dudi.log','a+').write('\n ' + str("MASUK bill 333"))
                for cl in self.creditnote_line_ids:
                    # open('/opt/odoo16/logs/dudi.log','a+').write('\n ' + str("MASUK bill 4444"))
                    # Jika CL based on admission
                    if cl.billing_type == 'admission':
                        cl.billing_id.payer_discount += cl.amount_discount or 0 
                        cl.billing_id.payer_balance -= cl.amount_discount or 0
                    # Jika CL based on split billing COB
                    elif cl.billing_type == 'cob':
                        cl.billing_cob_id.payer_discount += cl.amount_discount or 0 
                        cl.billing_cob_id.payer_balance -= cl.amount_discount or 0
                        if (cl.amount_discount or 0) != 0:
                            cl.billing_cob_id.action_history(remark="CONFIRM " + self.name, trans_date=self.date, credit_id=self.id)
                    # Jika CL based on billing
                    elif cl.billing_type == 'bill':
                        # open('/opt/odoo16/logs/dudi.log','a+').write('\n ' + str("MASUK bill 555"))
                        # open('/opt/odoo16/logs/dudi.log','a+').write('\n ' + str("MASUK no bill: " + str(cl.billing_sale_id.billno)))
                        cl.billing_sale_id.payer_discount += cl.amount_discount or 0 
                        cl.billing_sale_id.payer_balance -= cl.amount_discount or 0
                        if (cl.amount_discount or 0) != 0:
                            cl.billing_sale_id.action_history(remark="CONFIRM " + self.name, trans_date=self.date, credit_id=self.id)

            move = self.env['account.move'].create(vals)
            move.action_post()
            self.letter_id.action_compute_balance()

            # 2021.09.28 - Reconcile AR aging
            for move_cl in self.letter_id.journal_ids:
                invoice_line = self.env['account.move.line'].search([('move_id', '=', move_cl.id),('move_id.state','=','posted'),('account_id.reconcile','=',True),('debit','>',0)], limit=1)
                if invoice_line and not self.sync_id:    
                    if not invoice_line.full_reconcile_id:
                        full_recon = self.sudo().env['account.full.reconcile'].create({'name': "CL" + str(self.letter_id.id)})
                        invoice_line.write({'full_reconcile_id': full_recon.id,'reconciled': True})
                    else:
                        full_recon = invoice_line.full_reconcile_id

                    # update reconcile payment_line
                    payment_line = self.env['account.move.line'].search([('account_id','=', invoice_line.account_id.id), ('move_id', '=', move.id)], limit=1)
                    # Komen
                    if not payment_line:
                        raise UserError(_("Counterpart not found for Account " + invoice_line.account_id.code + ' ' + invoice_line.account_id.name))
                    payment_line.write({'full_reconcile_id': full_recon.id, 'reconciled': True})


    # @api.multi
    def _compute_total(self):
        for head in self:
            if head.creditnote_line_ids:
                head.total_discount = 0
                for line in head.creditnote_line_ids:
                    head.total_discount += line.amount_discount

    # @api.multi
    def action_print(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/report/account_creditnote?id=' + str(self.id)
        action['target'] = 'new'
        return action

    # @api.model
    # def _sync_wipro_creditnote(self, sync_type='1'):
    #     sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)])}
    #     sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
    #     data = []
    #     date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
    #     # date = '2019-01-31'
    #     query_wipro = """
    #     SELECT 
    #         a.CreditNoteID 'sync_id',
    #         a.LetterNo + '/' + convert(varchar(max), a.CreditNoteID, 121) 'name', 
    #         a.LetterNo 'covering_letter_name',
    #         convert(varchar(10),a.EntryDate, 121) 'date',
    #         a.LetterID 'letter_id',
    #         a.CustomerID 'payer_id',
    #         a.Remarks 'remark',
    #         a.CreditNote 'total_discount',
    #         'bill' billing_type,
    #         'draft' 'state'
    #     from dbo.VRP_OdooCreditNote a
    #     where convert(varchar(10), a.EntryDate, 121) = '%s'
    #     """ % (date)
    #     values = ''
    #     print (query_wipro)
    #     data += sync.get_data(sync.servers.get(sync_type), query_wipro)
    #     print (data)
    #     if not data:
    #         print ("No data available")
    #         return
    #     print ("jalan?")
    #     fields_without_id = tuple(
    #         key for key in self._fields
    #         if key != 'id' and 'property' not in key and 'ids' not in key
    #         and self._fields[key].required == True
    #         and self._fields[key].store == True)
    #     columns = tuple(
    #         key for key in data[0].keys()
    #         if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
    #     fields_without_id += columns
    #     columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
    #     fields = fields_without_id + ('id', )
    #     if columns:
    #         columns += ('id', )
    #     default_values = {}
    #     for field in fields:
    #         if field in columns:
    #             continue
    #         default = self._fields[field].default
    #         if callable(default):
    #             default = default(self)
    #         if isinstance(default, models.Model):
    #             default = default.id
    #         default_values[field] = default
    #     now = tools.datetime.now().strftime('%Y%m%d %H:%M:%S')
    #     new_sync_ids = []
    #     for object in data:
    #         new_sync_ids += [object['sync_id']]
    #         for value in default_values:
    #             if value in object:
    #                 continue
    #             object[value] = default_values[value]
    #         payer = object['payer_id']
    #         object['payer_id'] = self.env['res.partner'].search([('sync_id', '=', object['payer_id']),('sync_type', '=', sync_type), ('customer_wipro', '=', True)], order="id asc", limit=1).id
    #         if not object['payer_id']:
    #             error_msg = '\n' + str(tools.datetime.now()) + " payer with sync_id %s and sync_type %s doesn't exist" % (payer, sync_type)
    #             print (error_msg)
    #             open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) +" payer with sync_id %s and sync_type %s doesn't exist" %(payer, sync_type))
    #             return
    #         letter = object['letter_id']
    #         object['letter_id'] = self.env['account.coveringletter'].search([('sync_id', '=', object['letter_id']),('sync_type', '=', sync_type)],limit=1).id
    #         if not object['letter_id']:
    #             object['letter_id'] = None
    #             error_msg = '\n' + str(tools.datetime.now()) + " covering letter with sync_id %s and sync_type %s doesn't exist" % (letter, sync_type)
    #             print (error_msg)
    #             open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) +" covering letter with sync_id %s and sync_type %s doesn't exist"% (letter, sync_type))
    #             #return

    #         if int(object['sync_id']) in sync_ids:
    #             object['id'] = sync_ids[object['sync_id']]
    #         else:
    #             object['id'] = 'DEFAULT'
    #         object['sync_date'] = now
    #         object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)],limit=1).id
    #         if values:
    #             values += ', '
    #         value = False
    #         for field in fields:
    #             if value:
    #                 value += ', '
    #             else:
    #                 value = '('
    #             if field == 'id' and object['id'] == 'DEFAULT':
    #                 value += object['id']
    #                 continue
    #             if type(object[field]) in [str, unicode]:
    #                 string = object[field]
    #                 value += "'" + string.replace("'", "''") + "'"
    #                 continue
    #             value += sync.json(object[field])
    #         value += ')'
    #         values += value
    #     excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
    #     columns = sync.remove_unicode(str(fields)).replace("'", "")
    #     columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
    #     print ("ni query?")
    #     query = "INSERT into account_creditnote %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
    #     print (query.encode('utf8'))
    #     print ("execute bosq")
    #     self.env.cr.execute(query)


    # @api.model
    # def _sync_wipro_creditnote_manual(self, sync_type='1', date_start='2019-01-01', date_end='2019-01-01'):
    #     sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)]) }
    #     sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
    #     data = []
    #     date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
    #     # date = '2019-01-31'
    #     query_wipro = """
    #     SELECT 
    #         a.CreditNoteID 'sync_id',
    #         a.LetterNo + '/' + convert(varchar(max), a.CreditNoteID, 121) 'name', 
    #         a.LetterNo 'covering_letter_name',
    #         convert(varchar(10),a.EntryDate, 121) 'date',
    #         a.LetterID 'letter_id',
    #         a.CustomerID 'payer_id',
    #         a.Remarks 'remark',
    #         a.CreditNote 'total_discount',
    #         'bill' billing_type,
    #         'draft' 'state'
    #     from dbo.VRP_OdooCreditNote a
    #     where convert(varchar(10), a.EntryDate, 121) >= '%s' and convert(varchar(10), a.EntryDate, 121) <= '%s'
    #     """ % (date_start, date_end)
    #     values = ''
    #     print (query_wipro)
    #     data += sync.get_data(sync.servers.get(sync_type), query_wipro)
    #     print (data)
    #     if not data:
    #         print ("No data available")
    #         return
    #     print ("jalan?")
    #     fields_without_id = tuple(
    #         key for key in self._fields
    #         if key != 'id' and 'property' not in key and 'ids' not in key
    #         and self._fields[key].required == True
    #         and self._fields[key].store == True)
    #     columns = tuple(
    #         key for key in data[0].keys()
    #         if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
    #     fields_without_id += columns
    #     columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
    #     fields = fields_without_id + ('id', )
    #     if columns:
    #         columns += ('id', )
    #     default_values = {}
    #     for field in fields:
    #         if field in columns:
    #             continue
    #         default = self._fields[field].default
    #         if callable(default):
    #             default = default(self)
    #         if isinstance(default, models.Model):
    #             default = default.id
    #         default_values[field] = default
    #     now = tools.datetime.now().strftime('%Y%m%d %H:%M:%S')
    #     new_sync_ids = []
    #     for object in data:
    #         new_sync_ids += [object['sync_id']]
    #         for value in default_values:
    #             if value in object:
    #                 continue
    #             object[value] = default_values[value]
    #         payer = object['payer_id']
    #         object['payer_id'] = self.env['res.partner'].search([('sync_id', '=', object['payer_id']),('sync_type', '=', sync_type), ('customer_wipro', '=', True)], order="id asc", limit=1).id
    #         if not object['payer_id']:
    #             error_msg = '\n' + str(tools.datetime.now()) + " payer with sync_id %s and sync_type %s doesn't exist" % (payer, sync_type)
    #             print (error_msg)
    #             open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) +" payer with sync_id %s and sync_type %s doesn't exist" %(payer, sync_type))
    #             return
    #         letter = object['letter_id']
    #         object['letter_id'] = self.env['account.coveringletter'].search([('sync_id', '=', object['letter_id']),('sync_type', '=', sync_type)],limit=1).id
    #         if not object['letter_id']:
    #             object['letter_id'] = None
    #             error_msg = '\n' + str(tools.datetime.now()) + " covering letter with sync_id %s and sync_type %s doesn't exist" % (letter, sync_type)
    #             print (error_msg)
    #             open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) +" covering letter with sync_id %s and sync_type %s doesn't exist"% (letter, sync_type))
    #             #return

    #         if int(object['sync_id']) in sync_ids:
    #             object['id'] = sync_ids[object['sync_id']]
    #         else:
    #             object['id'] = 'DEFAULT'
    #         object['sync_date'] = now
    #         object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
    #         if values:
    #             values += ', '
    #         value = False
    #         for field in fields:
    #             if value:
    #                 value += ', '
    #             else:
    #                 value = '('
    #             if field == 'id' and object['id'] == 'DEFAULT':
    #                 value += object['id']
    #                 continue
    #             if type(object[field]) in [str, unicode]:
    #                 string = object[field]
    #                 value += "'" + string.replace("'", "''") + "'"
    #                 continue
    #             value += sync.json(object[field])
    #         value += ')'
    #         values += value
    #     excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
    #     columns = sync.remove_unicode(str(fields)).replace("'", "")
    #     columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
    #     print ("ni query?")
    #     query = "INSERT into account_creditnote %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
    #     print (query.encode('utf8'))
    #     print ("execute bosq")
    #     self.env.cr.execute(query)


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(CreditNote,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Credit Note" delete="false" decoration-info="state == 'draft'" decoration-success="state == 'confirm'" decoration-muted="state == 'cancel'">
                    <field name="name"/>
                    <field name="date"/>
                    <field name="payer_id"/>
                    <field name="letter_id"/>
                    <field name="remark" invisible="1"/>
                    <field name="total_discount" sums="Amount Total"/>
                    <field name="state" string="Status" widget="badge" decoration-info="state == 'draft'" decoration-success="state == 'confirm'" decoration-muted="state == 'cancel'"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="CN Search">
                    <filter string="Draft" domain="[('state','=', 'draft')]" help="Draft"/>
                    <filter string="Confirm" domain="[('state','=', 'confirm')]" help="Confirm"/>
                    <filter string="Cancelled" domain="[('state','=', 'cancel')]" help="Cancelled"/>
                    <separator/>
                    <field name="name"/>
                    <field name="payer_id"/>
                    <field name="letter_id"/>
                    <field name="remark"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    @api.model
    def _sync_wipro_creditnote(self, sync_type='1'):
        sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
        data = []
        date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
        # date = '2019-01-31'
        query_wipro = """
        SELECT 
            a.CreditNoteID 'sync_id',
            a.LetterNo + '/' + convert(varchar(max), a.CreditNoteID, 121) 'name', 
            a.LetterNo 'covering_letter_name',
            convert(varchar(10),a.EntryDate, 121) 'date',
            a.LetterID 'letter_id',
            a.CustomerID 'payer_id',
            a.Remarks 'remark',
            a.CreditNote 'total_discount',
            'bill' billing_type,
            'draft' 'state'
        from dbo.VRP_OdooCreditNote a
        where convert(varchar(10), a.EntryDate, 121) = '%s'
        """ % (date)
        values = ''
        print (query_wipro)
        data += sync.get_data(sync.servers.get(sync_type), query_wipro)
        print (data)
        if not data:
            print ("No data available")
            return
        print ("jalan?")
        fields_without_id = tuple(
            key for key in self._fields
            if key != 'id' and 'property' not in key and 'ids' not in key
            and self._fields[key].required == True
            and self._fields[key].store == True)
        columns = tuple(
            key for key in data[0].keys()
            if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
        fields_without_id += columns
        columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
        fields = fields_without_id + ('id', )
        if columns:
            columns += ('id', )
        default_values = {}
        for field in fields:
            if field in columns:
                continue
            default = self._fields[field].default
            if callable(default):
                default = default(self)
            if isinstance(default, models.Model):
                default = default.id
            default_values[field] = default
        now = tools.datetime.now().strftime('%Y%m%d %H:%M:%S')
        new_sync_ids = []
        for object in data:
            new_sync_ids += [object['sync_id']]
            for value in default_values:
                if value in object:
                    continue
                object[value] = default_values[value]
            payer = object['payer_id']
            object['payer_id'] = self.env['res.partner'].search([('sync_id', '=', object['payer_id']),('sync_type', '=', sync_type), ('customer_wipro', '=', True)], order="id asc", limit=1).id
            if not object['payer_id']:
                error_msg = '\n' + str(tools.datetime.now()) + " payer with sync_id %s and sync_type %s doesn't exist" % (payer, sync_type)
                print (error_msg)
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) +" payer with sync_id %s and sync_type %s doesn't exist" %(payer, sync_type))
                return
            letter = object['letter_id']
            object['letter_id'] = self.env['account.coveringletter'].search([('sync_id', '=', object['letter_id']),('sync_type', '=', sync_type)],limit=1).id
            if not object['letter_id']:
                object['letter_id'] = None
                error_msg = '\n' + str(tools.datetime.now()) + " covering letter with sync_id %s and sync_type %s doesn't exist" % (letter, sync_type)
                print (error_msg)
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) +" covering letter with sync_id %s and sync_type %s doesn't exist"% (letter, sync_type))
                #return

            if int(object['sync_id']) in sync_ids:
                object['id'] = sync_ids[object['sync_id']]
            else:
                object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)],limit=1).id
            if values:
                values += ', '
            value = False
            for field in fields:
                if value:
                    value += ', '
                else:
                    value = '('
                if field == 'id' and object['id'] == 'DEFAULT':
                    value += object['id']
                    continue
                if type(object[field]) in [str, unicode]:
                    string = object[field]
                    value += "'" + string.replace("'", "''") + "'"
                    continue
                value += sync.json(object[field])
            value += ')'
            values += value
        excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        columns = sync.remove_unicode(str(fields)).replace("'", "")
        columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        print ("ni query?")
        query = "INSERT into account_creditnote %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        print ("execute bosq")
        self.env.cr.execute(query)


    @api.model
    def _sync_wipro_creditnote_manual(self, sync_type='1', date_start='2019-01-01', date_end='2019-01-01'):
        sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)]) }
        sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
        data = []
        date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
        # date = '2019-01-31'
        query_wipro = """
        SELECT 
            a.CreditNoteID 'sync_id',
            a.LetterNo + '/' + convert(varchar(max), a.CreditNoteID, 121) 'name', 
            a.LetterNo 'covering_letter_name',
            convert(varchar(10),a.EntryDate, 121) 'date',
            a.LetterID 'letter_id',
            a.CustomerID 'payer_id',
            a.Remarks 'remark',
            a.CreditNote 'total_discount',
            'bill' billing_type,
            'draft' 'state'
        from dbo.VRP_OdooCreditNote a
        where convert(varchar(10), a.EntryDate, 121) >= '%s' and convert(varchar(10), a.EntryDate, 121) <= '%s'
        """ % (date_start, date_end)
        values = ''
        print (query_wipro)
        data += sync.get_data(sync.servers.get(sync_type), query_wipro)
        print (data)
        if not data:
            print ("No data available")
            return
        print ("jalan?")
        fields_without_id = tuple(
            key for key in self._fields
            if key != 'id' and 'property' not in key and 'ids' not in key
            and self._fields[key].required == True
            and self._fields[key].store == True)
        columns = tuple(
            key for key in data[0].keys()
            if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
        fields_without_id += columns
        columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
        fields = fields_without_id + ('id', )
        if columns:
            columns += ('id', )
        default_values = {}
        for field in fields:
            if field in columns:
                continue
            default = self._fields[field].default
            if callable(default):
                default = default(self)
            if isinstance(default, models.Model):
                default = default.id
            default_values[field] = default
        now = tools.datetime.now().strftime('%Y%m%d %H:%M:%S')
        new_sync_ids = []
        for object in data:
            new_sync_ids += [object['sync_id']]
            for value in default_values:
                if value in object:
                    continue
                object[value] = default_values[value]
            payer = object['payer_id']
            object['payer_id'] = self.env['res.partner'].search([('sync_id', '=', object['payer_id']),('sync_type', '=', sync_type), ('customer_wipro', '=', True)], order="id asc", limit=1).id
            if not object['payer_id']:
                error_msg = '\n' + str(tools.datetime.now()) + " payer with sync_id %s and sync_type %s doesn't exist" % (payer, sync_type)
                print (error_msg)
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) +" payer with sync_id %s and sync_type %s doesn't exist" %(payer, sync_type))
                return
            letter = object['letter_id']
            object['letter_id'] = self.env['account.coveringletter'].search([('sync_id', '=', object['letter_id']),('sync_type', '=', sync_type)],limit=1).id
            if not object['letter_id']:
                object['letter_id'] = None
                error_msg = '\n' + str(tools.datetime.now()) + " covering letter with sync_id %s and sync_type %s doesn't exist" % (letter, sync_type)
                print (error_msg)
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) +" covering letter with sync_id %s and sync_type %s doesn't exist"% (letter, sync_type))
                #return

            if int(object['sync_id']) in sync_ids:
                object['id'] = sync_ids[object['sync_id']]
            else:
                object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
            if values:
                values += ', '
            value = False
            for field in fields:
                if value:
                    value += ', '
                else:
                    value = '('
                if field == 'id' and object['id'] == 'DEFAULT':
                    value += object['id']
                    continue
                if type(object[field]) in [str, unicode]:
                    string = object[field]
                    value += "'" + string.replace("'", "''") + "'"
                    continue
                value += sync.json(object[field])
            value += ')'
            values += value
        excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        columns = sync.remove_unicode(str(fields)).replace("'", "")
        columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        print ("ni query?")
        query = ("INSERT into account_creditnote %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded))
        print (query.encode('utf8'))
        print ("execute bosq")
        self.env.cr.execute(query)


class CreditNoteLine(models.Model):
    _name = 'account.creditnote.line'

    _sql_constraints = [
        (
            'creditnote_billing_sale_uniq',
            'unique(creditnote_id, billing_sale_id)',
            'A Credit Note can only contain one line for the same Billing.',
        ),
    ]

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    creditnote_id = fields.Many2one('account.creditnote')
    creditnote_no = fields.Char(string="CN No.", related='creditnote_id.name')
    creditnote_date = fields.Date(string="CN Date", related='creditnote_id.date')
    creditnote_state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm'),  ('cancel', 'Cancel')], string="CN State", related='creditnote_id.state')
    cover_id = fields.Many2one('account.coveringletter', related="creditnote_id.letter_id", store=True, readonly=True, string="Letter No.")
    billing_type = fields.Selection([('bill', 'Billing'),('cob', 'COB Bill'), ('admission','Admission')], string="Based On", related="creditnote_id.billing_type", default="bill", store=True, readonly=False)
    billing_id = fields.Many2one('sale.order', string="Admission No")
    billing_sale_id = fields.Many2one('sale.order.bill', string="Billing No") 
    billing_cob_id = fields.Many2one('sale.order.cob', string="COB No") 
    category_id = fields.Many2one('product.category', string="Service Category")

    # ini versi baru ambil payer_amount dari sale.order.bill
    billing_amount = fields.Float(string="Payer Balance", store=True, readonly=False, related='billing_sale_id.payer_balance')
    # ini versi shan yang lama ambil dari sale.order
    total_billing = fields.Float(string="Payer Amount", store=True, readonly=False)
    takeout_amount = fields.Float(string="Takeout From Disc", store=True)
    discount_percent = fields.Float(string="Discount Percent", store=True)
    amount_discount = fields.Float(string="Discount Amount", readonly=False, store=True) #, compute='_depent_amount')
    # backup old value
    total_discount = fields.Float(string="Total Ending", store=True)
    # u/ lihat ending payer_amount setelah discount
    payer_ending = fields.Float(string="Payer Ending", store=True)
    remark = fields.Char(string="Remark")


    @api.depends('billing_id', 'billing_sale_id', 'billing_cob_id')
    def _depend_billing(self):
        for record in self:
            if record.billing_type == 'admission':
                record.billing_amount = record.billing_id.payer_balance
            elif record.billing_type == 'bill':
                record.billing_amount = record.billing_sale_id.payer_balance 
            elif record.billing_type == 'cob':
                record.billing_amount = record.billing_cob_id.payer_balance 
    
    @api.onchange('billing_id', 'billing_sale_id', 'billing_cob_id')
    def _change_billing(self):
        for record in self:
            if record.billing_type == 'admission':
                record.billing_amount = record.billing_id.payer_balance 
            elif record.billing_type == 'bill':
                record.billing_amount = record.billing_sale_id.payer_balance 
            elif record.billing_type == 'cob':
                record.billing_amount = record.billing_cob_id.payer_balance 
            

    @api.depends('billing_amount', 'takeout_amount', 'discount_percent')
    def _depent_amount(self):
        for record in self:
            if record.discount_percent > 0:
                record.amount_discount = (record.billing_amount - record.takeout_amount) * record.discount_percent / 100
            else:
                record.amount_discount = record.billing_amount - record.takeout_amount
            record.payer_ending = record.billing_amount - record.amount_discount

    @api.onchange('billing_amount', 'takeout_amount', 'discount_percent')
    def _change_amount(self):
        for record in self:
            if record.discount_percent > 0:
                record.amount_discount = (record.billing_amount - record.takeout_amount) * record.discount_percent / 100
            else:
                record.amount_discount = record.billing_amount - record.takeout_amount
            record.payer_ending = record.billing_amount - record.amount_discount

    @api.onchange('amount_discount')
    def _change_amount(self):
        for record in self:
            record.payer_ending = record.billing_amount - record.amount_discount


class CreditNoteImportWizard(models.TransientModel):
    _name = 'account.creditnote.import.wizard'
    _description = 'Credit Note Excel Import'

    _HEADERS = ('letter_no', 'admission_no', 'bill_no', 'apply_amount', 'notes')
    _XLSX_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    _REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    _PACKAGE_REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'

    creditnote_id = fields.Many2one(
        'account.creditnote',
        string='Credit Note',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    upload_file = fields.Binary(string='Excel File', attachment=False)
    filename = fields.Char(string='Filename')
    template_file = fields.Binary(string='Template File', readonly=True, attachment=False)
    template_filename = fields.Char(string='Template Filename', readonly=True)

    @api.model
    def _normalize_text(self, value):
        if value is None or value is False:
            return ''
        text = str(value).strip()
        if re.fullmatch(r'[+-]?\d+\.0+', text):
            text = text.split('.', 1)[0]
        return text

    @api.model
    def _normalized_key(self, value):
        return self._normalize_text(value).casefold()

    @api.model
    def _column_index(self, cell_reference):
        letters = ''.join(character for character in cell_reference if character.isalpha())
        index = 0
        for character in letters.upper():
            index = (index * 26) + ord(character) - ord('A') + 1
        return index - 1

    @api.model
    def _build_xlsx(self, rows):
        import xlsxwriter

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Credit Note Import')
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D9EAF7'})
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                cell_format = header_format if row_index == 0 else None
                worksheet.write(row_index, column_index, value, cell_format)
        worksheet.set_column('A:C', 22)
        worksheet.set_column('D:D', 18)
        worksheet.set_column('E:E', 35)
        worksheet.autofilter(0, 0, 0, len(self._HEADERS) - 1)
        workbook.close()
        return output.getvalue()

    def action_download_template(self):
        self.ensure_one()
        self.template_filename = 'credit_note_import_template.xlsx'
        self.template_file = base64.b64encode(self._build_xlsx([self._HEADERS]))
        return {
            'type': 'ir.actions.act_url',
            'url': (
                '/web/content/?model=account.creditnote.import.wizard&id=%s'
                '&field=template_file&filename_field=template_filename&download=true'
            ) % self.id,
            'target': 'self',
        }

    @api.model
    def _xlsx_rows(self, file_content):
        try:
            archive = zipfile.ZipFile(io.BytesIO(file_content), 'r')
        except (zipfile.BadZipFile, TypeError, ValueError):
            raise ValidationError(_("The uploaded file is not a valid .xlsx workbook."))

        try:
            workbook_root = ElementTree.fromstring(archive.read('xl/workbook.xml'))
            relationships_root = ElementTree.fromstring(
                archive.read('xl/_rels/workbook.xml.rels')
            )
            sheets = workbook_root.findall('{%s}sheets/{%s}sheet' % (self._XLSX_NS, self._XLSX_NS))
            if not sheets:
                raise ValidationError(_("The uploaded workbook does not contain a worksheet."))

            relationship_id = sheets[0].get('{%s}id' % self._REL_NS)
            targets = {
                relation.get('Id'): relation.get('Target')
                for relation in relationships_root.findall('{%s}Relationship' % self._PACKAGE_REL_NS)
            }
            target = targets.get(relationship_id)
            if not target:
                raise ValidationError(_("The first worksheet in the uploaded workbook is invalid."))
            sheet_path = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)

            shared_strings = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                shared_root = ElementTree.fromstring(archive.read('xl/sharedStrings.xml'))
                for item in shared_root.findall('{%s}si' % self._XLSX_NS):
                    shared_strings.append(''.join(
                        node.text or '' for node in item.iter('{%s}t' % self._XLSX_NS)
                    ))

            sheet_root = ElementTree.fromstring(archive.read(sheet_path))
            parsed_rows = []
            for row in sheet_root.findall('.//{%s}sheetData/{%s}row' % (self._XLSX_NS, self._XLSX_NS)):
                row_number = int(row.get('r') or (len(parsed_rows) + 1))
                values = []
                for cell in row.findall('{%s}c' % self._XLSX_NS):
                    column_index = self._column_index(cell.get('r') or '')
                    while len(values) <= column_index:
                        values.append('')
                    cell_type = cell.get('t')
                    if cell_type == 'inlineStr':
                        value = ''.join(
                            node.text or '' for node in cell.iter('{%s}t' % self._XLSX_NS)
                        )
                    else:
                        value_node = cell.find('{%s}v' % self._XLSX_NS)
                        value = value_node.text if value_node is not None else ''
                        if cell_type == 's' and value != '':
                            value = shared_strings[int(value)]
                    values[column_index] = value
                parsed_rows.append((row_number, values))
            return parsed_rows
        except ValidationError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, ElementTree.ParseError):
            raise ValidationError(_("The uploaded file is not a valid .xlsx workbook."))
        finally:
            archive.close()

    @api.model
    def _parse_apply_amount(self, value, row_number):
        text = self._normalize_text(value)
        if not text:
            raise ValidationError(_("Row %s: Apply Amount is required.") % row_number)
        normalized = text.replace(' ', '')
        if re.fullmatch(r'[+-]?\d{1,3}(,\d{3})+(\.\d+)?', normalized):
            normalized = normalized.replace(',', '')
        try:
            amount = Decimal(normalized)
        except (InvalidOperation, ValueError):
            raise ValidationError(_("Row %s: Apply Amount %s is not a valid numeric value.") % (row_number, text))
        if not amount.is_finite():
            raise ValidationError(_("Row %s: Apply Amount %s is not a valid numeric value.") % (row_number, text))
        return float(amount)

    @api.model
    def _format_amount(self, amount):
        return '{:,.2f}'.format(amount).rstrip('0').rstrip('.')

    def _validate_creditnote(self):
        self.ensure_one()
        creditnote = self.creditnote_id.exists()
        if not creditnote:
            raise ValidationError(_("The Credit Note was not found."))
        if creditnote.state != 'draft':
            raise ValidationError(_("Excel import is only available for Draft Credit Notes."))
        if not creditnote.letter_id:
            raise ValidationError(_("Please select a Covering Letter before importing."))
        if creditnote.billing_type != 'bill':
            raise ValidationError(_("Credit Note Excel import currently supports Bill billing type only."))
        return creditnote

    def _validated_import_rows(self, creditnote, workbook_rows):
        if not workbook_rows:
            raise ValidationError(_("The uploaded workbook is empty."))

        header_row_number, header_values = workbook_rows[0]
        headers = tuple(self._normalize_text(value) for value in header_values)
        while headers and not headers[-1]:
            headers = headers[:-1]
        if header_row_number != 1 or headers != self._HEADERS:
            raise ValidationError(_(
                "Row 1 must contain exactly these columns in order: %s."
            ) % ', '.join(self._HEADERS))

        source_bills = creditnote.letter_id.billing_sale_ids
        source_bills.invalidate_recordset(['billno', 'admission_no', 'payer_balance'])
        bills_by_number = {}
        for bill in source_bills:
            bills_by_number.setdefault(self._normalized_key(bill.billno), self.env['sale.order.bill'])
            bills_by_number[self._normalized_key(bill.billno)] |= bill

        rounding = creditnote.company_id.currency_id.rounding or 0.01
        selected_letter_no = self._normalize_text(creditnote.letter_id.name)
        selected_letter_key = self._normalized_key(selected_letter_no)
        prepared_rows = []
        duplicate_rows = {}

        for row_number, raw_values in workbook_rows[1:]:
            values = list(raw_values[:5])
            values += [''] * (5 - len(values))
            if not any(self._normalize_text(value) for value in values):
                continue

            letter_no, admission_no, bill_no, apply_amount, notes = values
            letter_no = self._normalize_text(letter_no)
            admission_no = self._normalize_text(admission_no)
            bill_no = self._normalize_text(bill_no)
            notes = self._normalize_text(notes)

            if not letter_no:
                raise ValidationError(_("Row %s: Letter No is required.") % row_number)
            if self._normalized_key(letter_no) != selected_letter_key:
                raise ValidationError(_(
                    "Row %s: Letter No %s does not match the selected Covering Letter %s."
                ) % (row_number, letter_no, selected_letter_no or '-'))
            if not bill_no:
                raise ValidationError(_("Row %s: Bill No is required.") % row_number)

            matching_bills = bills_by_number.get(self._normalized_key(bill_no), self.env['sale.order.bill'])
            if not matching_bills:
                raise ValidationError(_(
                    "Row %s: Bill No %s was not found in the selected Covering Letter."
                ) % (row_number, bill_no))
            if len(matching_bills) > 1 and admission_no:
                admission_key = self._normalized_key(admission_no)
                matching_admissions = matching_bills.filtered(
                    lambda bill: self._normalized_key(bill.admission_no) == admission_key
                )
                if len(matching_admissions) == 1:
                    matching_bills = matching_admissions
            if len(matching_bills) != 1:
                raise ValidationError(_(
                    "Row %s: Bill No %s is ambiguous within the selected Covering Letter."
                ) % (row_number, bill_no))

            bill = matching_bills
            amount = self._parse_apply_amount(apply_amount, row_number)
            if float_compare(amount, 0.0, precision_rounding=rounding) <= 0:
                raise ValidationError(_("Row %s: Apply Amount must be greater than zero.") % row_number)
            live_balance = bill.payer_balance or 0.0
            if float_compare(amount, live_balance, precision_rounding=rounding) > 0:
                raise ValidationError(_(
                    "Row %s: Apply Amount %s exceeds the current billing balance %s."
                ) % (
                    row_number,
                    self._format_amount(amount),
                    self._format_amount(live_balance),
                ))

            duplicate_rows.setdefault(bill.id, []).append(row_number)
            prepared_rows.append({
                'row_number': row_number,
                'bill': bill,
                'bill_no': bill_no,
                'amount_discount': amount,
                'payer_ending': live_balance - amount,
                'remark': notes or False,
            })

        if not prepared_rows:
            raise ValidationError(_("The uploaded workbook does not contain any populated data rows."))

        for bill_id, row_numbers in duplicate_rows.items():
            if len(row_numbers) > 1:
                duplicate = next(row for row in prepared_rows if row['bill'].id == bill_id)
                raise ValidationError(_(
                    "Rows %s: Bill No %s is duplicated in the uploaded file."
                ) % (' and '.join(str(number) for number in row_numbers), duplicate['bill_no']))

        existing_by_bill = {}
        for line in creditnote.creditnote_line_ids.filtered('billing_sale_id'):
            existing_by_bill.setdefault(line.billing_sale_id.id, self.env['account.creditnote.line'])
            existing_by_bill[line.billing_sale_id.id] |= line
        for prepared in prepared_rows:
            matching_lines = existing_by_bill.get(
                prepared['bill'].id,
                self.env['account.creditnote.line'],
            )
            matching_lines = matching_lines.sorted('id')
            prepared['existing_line'] = matching_lines[:1]
            prepared['duplicate_lines'] = matching_lines[1:]
        return prepared_rows

    def action_import(self):
        self.ensure_one()
        creditnote = self._validate_creditnote()
        if not self.upload_file:
            raise ValidationError(_("Please upload an Excel file."))
        if not self.filename or not self.filename.lower().endswith('.xlsx'):
            raise ValidationError(_("Please upload a file with the .xlsx extension."))

        try:
            file_content = base64.b64decode(self.upload_file, validate=True)
        except (ValueError, TypeError):
            raise ValidationError(_("The uploaded file could not be decoded."))

        workbook_rows = self._xlsx_rows(file_content)
        prepared_rows = self._validated_import_rows(creditnote, workbook_rows)

        created_values = []
        updated_count = 0
        for prepared in prepared_rows:
            values = {
                'amount_discount': prepared['amount_discount'],
                'payer_ending': prepared['payer_ending'],
                'remark': prepared['remark'],
            }
            if prepared['existing_line']:
                prepared['duplicate_lines'].unlink()
                prepared['existing_line'].write(values)
                updated_count += 1
            else:
                values.update({
                    'creditnote_id': creditnote.id,
                    'billing_sale_id': prepared['bill'].id,
                })
                created_values.append(values)

        if created_values:
            self.env['account.creditnote.line'].create(created_values)
        creditnote.write({
            'total_discount': sum(creditnote.creditnote_line_ids.mapped('amount_discount')),
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Credit Note Import'),
                'message': _(
                    'Import completed: %s lines created and %s existing lines updated.'
                ) % (len(created_values), updated_count),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }



class AccountAdvance(models.Model):
    _name = 'account.advance'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_id = sync.id
    sync_type = sync.type
    sync_date = sync.date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    name = fields.Char(string="Number", readonly=True, index=True)
    date = fields.Date(string="Date", required=True, index=True)
    company_id = fields.Many2one('res.company', string="Company", index=True, default=_get_company)
    payer_id = fields.Many2one('res.partner', string="Partner", index=True)
    bank_id = fields.Many2one('account.journal', string="Bank Journal")
    journal_id = fields.Many2one('account.move', string="Journal", readonly=True)
    account_id = fields.Many2one('account.account', string="Deposit Account")

    receipt_amount = fields.Float(string="Receipt Amount")
    unadjustment_amount = fields.Float(string="UnAdjustment")
    adjustment_amount = fields.Float(string="Adjustment")


    receipt_ids = fields.One2many('account.advance.realization', 'advance_id', string="Advance Relization", states={'posted':[('readonly', True)], 'reconciled':[('readonly', True)]}, ondelete='set null')
    revisi = fields.Boolean(string="Revisi", readonly=True)
    revisi_name = fields.Char(string="Revisi Name", readonly=True)
    revisi_sequence = fields.Integer(string="Revisi Sequence", readonly=True)
    remark = fields.Char(string="Remarks", index=True)
    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm'), ('reverse', 'Reverse'), ('cancel', 'Cancel')], 'Status', default='draft', index=True, required=True, readonly=True, copy=False, tracking=True, store=True)

    reverse_amount = fields.Float(string="Reverse Amount")
    reverse_date = fields.Date(string="Reverse Date")
    reverse_bank_id = fields.Many2one('account.journal', string="Reverse Journal")
    reverse_account_id = fields.Many2one('account.account', string="Reversal COA")
    reverse_journal_id = fields.Many2one('account.move', string="Reverse Entries", readonly=True)    
    reverse_remark = fields.Char(string="Reverse Remarks", index=True)
    move_line_ids = fields.One2many('account.move.line','advance_id', string="Move Items", readonly=True)
    message_last_post = fields.Datetime(string="Message Last Post", index=True, readonly=True)

    @api.model
    def create(self, vals):
        result = super(AccountAdvance, self).create(vals)
        result.name = self.env['ir.sequence'].sudo().next_by_code('account.advance.seq')
        self.compute_total()
        return result

    # @api.multi
    def write(self, vals):
        result = super(AccountAdvance, self).write(vals)
        if self.env.context.get('sudah_total'): return result
        self = self.with_context(sudah_total=True)
        self.compute_total()
        return result


    # @api.multi
    def action_reverse(self):
        # LOCK AR
        lock_date = self.env['lock.ar.configuration'].sudo().search([('company_id', '=', self.company_id.id)], limit=1).date
        if self.reverse_date <= lock_date:
            raise exceptions.UserError(_('You cannot add/modify entries prior to and inclusive of the lock date "%s".') % (lock_date))


        self.state = 'reverse'
        if not self.reverse_journal_id:
            self.compute_total()

            if self.unadjustment_amount < 0.:
                raise exceptions.UserError("Nilai reverse/refund tidak boleh melebihi sisa advance.")

            debit_vals = {
                'name': self.name,
                'advance_id': self.id,
                'debit': abs(self.reverse_amount),
                'credit': 0.0,
                'partner_id': self.payer_id.id or None,
                'account_id': self.account_id.id,
            }
            credit_vals = {
                'name': self.name,
                'advance_id': self.id,
                'debit': 0.0,
                'credit': abs(self.reverse_amount),
                'partner_id': self.payer_id.id or None,
                'account_id': self.reverse_account_id.id
            }
            vals = {'journal_id': self.reverse_bank_id.id, 'date': self.reverse_date, 'ref': 'AR ADVANCE REVERSE ' + self.name + ' / ' + str(self.reverse_remark), 'advance_id': self.id, 'line_ids': [(0, 0, debit_vals), (0, 0, credit_vals)]}
            move = self.env['account.move'].create(vals)
            move.action_post()
            self.reverse_journal_id = move.id


            # 2021.09.28 - Reconcile advance deposit reverse
            # invoice_line = self.env['account.move.line'].search([('move_id', '=', self.journal_id.id),('move_id.state','=','posted'),('credit','>',0)], limit=1)
            # if invoice_line:    
            #     if not invoice_line.full_reconcile_id:
            #         full_recon = self.sudo().env['account.full.reconcile'].create({'name': "AD" + str(self.id)})
            #         invoice_line.write({'full_reconcile_id': full_recon.id,'reconciled': True})
            #     else:
            #         full_recon = invoice_line.full_reconcile_id

            #     # update reconcile payment_line
            #     payment_line = self.env['account.move.line'].search([('account_id','=', invoice_line.account_id.id), ('move_id', '=', move.id)], limit=1)
            #     if not payment_line:
            #         raise UserError(_("Counterpart not found for Account " + line.account_id.code + ' ' + line.account_id.name))
            #     payment_line.write({'full_reconcile_id': full_recon.id,'reconciled': True})


    # @api.multi
    def button_journal_entries(self):
        return {
            'name': _('Journal Items'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('advance_id', 'in', self.ids)],
        }


    # @api.multi
    def action_confirm(self):
        # LOCK AR
        lock_date = self.env['lock.ar.configuration'].sudo().search([('company_id', '=', self.company_id.id)], limit=1).date
        if self.date <= lock_date:
            raise exceptions.UserError(_('You cannot add/modify entries prior to and inclusive of the lock date "%s".') % (lock_date))

        self.state = 'confirm'
        if not self.journal_id:
            self.compute_total()

            debit_vals = {
                'name': self.name,
                'advance_id': self.id,
                'debit': abs(self.receipt_amount),
                'credit': 0.0,
                'partner_id': self.payer_id.id or None,
                'account_id': self.bank_id.default_debit_account_id.id,
            }
            credit_vals = {
                'name': self.name,
                'advance_id': self.id,
                'debit': 0.0,
                'credit': abs(self.receipt_amount),
                'partner_id': self.payer_id.id or None,
                'account_id': self.account_id.id
            }
            vals = {'journal_id': self.bank_id.id, 'date': self.date, 'ref': 'AR ADVANCE ' + str(self.name), 'advance_id': self.id, 'line_ids': [(0, 0, debit_vals), (0, 0, credit_vals)]}
            move = self.env['account.move'].create(vals)
            move.action_post()
            self.journal_id = move.id


    # @api.multi
    def action_cancel(self):
        # LOCK AR
        lock_date = self.env['lock.ar.configuration'].sudo().search([('company_id', '=', self.company_id.id)], limit=1).date
        if self.date <= lock_date:
            raise exceptions.UserError(_('You cannot add/modify AR record prior to and inclusive of the lock date "%s".') % (lock_date))

        self.state = 'cancel'
        if self.journal_id:
            self.journal_id.button_cancel()
            self.journal_id.unlink()


    # @api.multi
    def action_cancel_reverse(self):
        # LOCK AR
        lock_date = self.env['lock.ar.configuration'].sudo().search([('company_id', '=', self.company_id.id)], limit=1).date
        if self.reverse_date <= lock_date:
            raise exceptions.UserError(_('You cannot add/modify AR record prior to and inclusive of the lock date "%s".') % (lock_date))

        if self.state == 'reverse':
            self.state = 'confirm'
            if self.reverse_journal_id:
                self.reverse_journal_id.button_cancel()
                self.reverse_journal_id.unlink()


    # @api.multi
    def action_draft(self):
        self.revisi = True
        self.revisi_sequence += 1
        self.state = 'draft'
        self.update({'revisi_name': 'R' + str(self.revisi_sequence)})  


    # @api.multi
    def compute_total(self):
        for record in self:
            unadjustment_amount = record.receipt_amount
            adjustment_amount = 0
            
            adjustment_amount += record.reverse_amount
            unadjustment_amount -= record.reverse_amount

            if record.receipt_ids:
                for line in record.receipt_ids:
                    if line.state == 'confirm':
                        adjustment_amount += line.amount_receipt
                        unadjustment_amount -= line.amount_receipt
            record.adjustment_amount = adjustment_amount
            record.unadjustment_amount = unadjustment_amount


class AccountAdvanceRealization(models.Model):
    _name = 'account.advance.realization'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_id = sync.id
    sync_type = sync.type
    sync_date = sync.date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    name = fields.Char(string="Number", readonly=True, index=True)
    date = fields.Date(string="Date", required=True, index=True)
    company_id = fields.Many2one('res.company', string="Company", index=True, default=_get_company)
    advance_id = fields.Many2one('account.advance', string="Advance No.")
    payer_id = fields.Many2one('res.partner', string="Partner", index=True)
    payer_patient = fields.Boolean(string="Patient", related="payer_id.patient", store=False, readonly=True)
    covering_id = fields.Many2one('account.coveringletter', string="Letter No.", index=True)
    covering_duedate = fields.Date(string="Letter Due Date", related="covering_id.due_date", store=True)
    amount_advance = fields.Float(string="Advance Balance", related="advance_id.unadjustment_amount")
    amount_receipt = fields.Float(string="Advance Relization")
    billing_type = fields.Selection([('bill', 'Billing'),('cob', 'COB Bill'), ('admission','Admission')], string="Based On",required=True,default='bill')
    journal_id = fields.Many2one('account.move', string="Journal", readonly=True, copy=False)
    account_id = fields.Many2one('account.account', string="Account Code", index=True)

    billing_ids = fields.One2many('account.payment.admission.rel', 'advance_realization_id', string="Admission", states={'posted':[('readonly', True)], 'reconciled':[('readonly', True)]}, ondelete='set null')
    billing_sale_ids = fields.One2many('account.payment.bill.rel', 'advance_realization_id', string="Billing", states={'posted':[('readonly', True)], 'reconciled':[('readonly', True)]}, ondelete='set null')
    billing_cob_ids = fields.One2many('account.payment.cob.rel', 'advance_realization_id', string="COB Bill", states={'posted':[('readonly', True)], 'reconciled':[('readonly', True)]}, ondelete='set null')
    
    old_receipt = fields.Boolean(string="Old Record (HIS)")
    revisi = fields.Boolean(string="Revisi", readonly=True)
    revisi_name = fields.Char(string="Revisi Name", readonly=True)
    revisi_sequence = fields.Integer(string="Revisi Sequence", readonly=True)
    remark = fields.Char(string="Remarks", index=True)
    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm'),('cancel', 'Cancel')], 'Status', default='draft', index=True, required=True, readonly=True, copy=False, tracking=True, store=True)
    message_last_post = fields.Datetime(string="Message Last Post", index=True, readonly=True)

    def action_open_import_wizard(self):
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError(_("Excel import is only available for Draft Advance Realizations."))
        if not self.covering_id:
            raise ValidationError(_("Please select a Covering Letter before importing."))
        if self.billing_type != 'bill':
            raise ValidationError(_("Advance Realization Excel import currently supports Bill billing type only."))

        action = self.env.ref('mayapada.account_advance_realization_import_wizard_action').read()[0]
        action['context'] = {
            'default_advance_realization_id': self.id,
            'active_id': self.id,
            'active_model': self._name,
        }
        return action

    
    @api.model
    def create(self, vals):
        result = super(AccountAdvanceRealization, self).create(vals)
        result.name = self.env['ir.sequence'].sudo().next_by_code('account.advance.realization.seq')
        self._compute_total_receipt_adjustment()
        return result

    # @api.multi
    def write(self, vals):
        result = super(AccountAdvanceRealization, self).write(vals)
        if self.env.context.get('sudah_total'): return result
        self = self.with_context(sudah_total=True)
        self._compute_total_receipt_adjustment()
        return result


    # @api.multi 
    def compute_total(self):
        self._compute_total_receipt_adjustment()


    # @api.multi
    def action_confirm(self):
        # Validation Receipt
        payer_receipt = sum(billing.payer_receipt for billing in self.billing_sale_ids)
        if float(payer_receipt) != float(self.amount_receipt):
            raise exceptions.ValidationError("Billing receipt must be same with advance realization...!!!")
        
        # LOCK AR
        lock_date = self.env['lock.ar.configuration'].sudo().search([('company_id', '=', self.company_id.id)], limit=1).date
        if self.date <= lock_date:
            raise exceptions.UserError(_('You cannot add/modify entries prior to and inclusive of the lock date "%s".') % (lock_date))
        
        if self.date < self.covering_id.date:
            raise exceptions.UserError(_('You cannot add/modify receipt prior to and inclusive of covering letter date "%s".') % (self.covering_id.date))

        if self.date < self.advance_id.date:
            raise exceptions.UserError(_('You cannot add/modify receipt prior to and inclusive of advance date "%s".') % (self.advance_id.date))

        total_receipt = 0
        for bill in self.billing_sale_ids:
            total_receipt += bill.payer_receipt

        if self.amount_receipt != total_receipt:
            raise exceptions.UserError(_('Your total settlement receipt not balance with realization receipt".')) 

        self._compute_total_receipt_adjustment()
        self.state = 'confirm'

        if not self.journal_id:
            journal_id = self.env['account.journal'].search([('name', 'like', '%Advance Realization%'), ('company_id', '=', self.company_id.id)], limit=1)
            #debit_account = self.env['account.account'].search([('code', 'like', '2106020000'), ('company_id', '=', self.company_id.id)], limit=1)
            debit_vals = {
                'name': self.name,
                'date_maturity': self.covering_id and self.covering_id.due_date,
                'advance_id': self.advance_id.id,
                'realization_id': self.id,
                'covering_id': self.covering_id and self.covering_id.id, 
                'covering_letter': self.covering_id and self.covering_id.name,
                'debit': abs(self.amount_receipt),
                'credit': 0.0,
                'partner_id': self.payer_id.id or None,
                'account_id': self.advance_id.account_id.id or None # debit_account.id,
            }
            credit_vals = {
                'name': self.name,
                'date_maturity': self.covering_id and self.covering_id.due_date,
                'advance_id': self.advance_id.id,
                'realization_id': self.id,
                'covering_id': self.covering_id and self.covering_id.id, 
                'covering_letter': self.covering_id and self.covering_id.name,
                'debit': 0.0,
                'credit': abs(self.amount_receipt),
                'partner_id': self.payer_id.id or None,
                'account_id': self.account_id.id if self.payer_id.patient is True else self.payer_id.account_ar_id.id
            }
            vals = {'journal_id': journal_id.id, 'date': self.date, 'ref': 'AR ADVANCE REALIZATION ' + str(self.name), 'partner_id': self.payer_id.id, 'advance_id': self.advance_id.id, 'realization_id': self.id, 'covering_id': self.covering_id.id, 'covering_letter': self.covering_id.name, 'line_ids': [(0, 0, debit_vals), (0, 0, credit_vals)]}
            move = self.env['account.move'].create(vals)
            move.action_post()
            self.journal_id = move.id

            # 2021.09.28 - Reconcile AR aging
            # for move_cl in self.covering_id.journal_ids:
            #     invoice_line = self.env['account.move.line'].search([('move_id', '=', move_cl.id),('move_id.state','=','posted'),('account_id.reconcile','=',True),('debit','>',0)], limit=1)
            #     if invoice_line:    
            #         if not invoice_line.full_reconcile_id:
            #             full_recon = self.sudo().env['account.full.reconcile'].create({'name': "CL" + str(self.covering_id.id)})
            #             invoice_line.write({'full_reconcile_id': full_recon.id,'reconciled': True})
            #         else:
            #             full_recon = invoice_line.full_reconcile_id

            #         # update reconcile payment_line
            #         payment_line = self.env['account.move.line'].search([('account_id','=', invoice_line.account_id.id), ('move_id', '=', move.id)], limit=1)
            #         if not payment_line:
            #             # raise UserError(_("Counterpart not found for Account " + line.account_id.code + ' ' + line.account_id.name))
            #             payment_line.write({'full_reconcile_id': full_recon.id,'reconciled': True})


            # 2021.09.28 - Reconcile advance deposit
            # for move_adv in self.advance_id.journal_id:
            #     invoice_line = self.env['account.move.line'].search([('move_id', '=', move_adv.id),('move_id.state','=','posted'),('credit','>',0)], limit=1)
            #     if invoice_line:    
            #         if not invoice_line.full_reconcile_id:
            #             full_recon = self.sudo().env['account.full.reconcile'].create({'name': "AD" + str(self.advance_id.id)})
            #             invoice_line.write({'full_reconcile_id': full_recon.id,'reconciled': True})
            #         else:
            #             full_recon = invoice_line.full_reconcile_id

            #         # update reconcile payment_line
            #         payment_line = self.env['account.move.line'].search([('account_id','=', invoice_line.account_id.id), ('move_id', '=', move.id)], limit=1)
            #         if not payment_line:
            #             # raise UserError(_("Counterpart not found for Account " + line.account_id.code + ' ' + line.account_id.name))
            #             payment_line.write({'full_reconcile_id': full_recon.id,'reconciled': True})


            # update Outstanding dari Advance
            if self.advance_id.state in ['confirm']:
                self.advance_id.unadjustment_amount -= self.amount_receipt
                self.advance_id.adjustment_amount += self.amount_receipt

            # 20210819 - Firgiawan Khafidli
            # Realisasi advance ke billing otomatis mengubah outstanding billing 
            # Serta outstanding CL/Invoice
            # compute balance CL on confirm receipt payment
            if self.covering_id:
                if self.covering_id.sync_id:
                    print("Skip validasi Balance Karena ini data MHCL Wipro.")
                else:
                    self.covering_id.total_payment += self.amount_receipt
                    self.covering_id.total_balance_amount -= self.amount_receipt
            # Jika receipt based on Admission
            if self.billing_type == 'admission':
                for bill in self.billing_ids:
                    bill.sale_order_id.payer_receipt += bill.payer_receipt
                    bill.sale_order_id.payer_balance -= bill.payer_receipt
            # Jika receipt based on billing
            elif self.billing_type == 'bill':
                for bill in self.billing_sale_ids:
                    if (bill.payer_receipt or 0) != 0:
                        bill.sale_order_bill_id.payer_receipt += (bill.payer_receipt or 0)
                        bill.sale_order_bill_id.payer_balance -= (bill.payer_receipt or 0)
                        bill.sale_order_bill_id.action_history(remark="CONFIRM " + str(self.name), trans_date=self.date, advance_id=self.id)
            
            # Jika receipt based on billing COB
            elif self.billing_type == 'cob':
                for bill in self.billing_cob_ids:
                    if (bill.payer_receipt or 0) != 0:
                        bill.sale_order_cob_id.payer_receipt += bill.payer_receipt
                        bill.sale_order_cob_id.payer_balance -= bill.payer_receipt
                        bill.sale_order_cob_id.action_history(remark="CONFIRM " + str(self.name), trans_date=self.date, advance_id=self.id)




    # @api.multi
    def action_cancel(self):
        # LOCK AR
        lock_date = self.env['lock.ar.configuration'].sudo().search([('company_id', '=', self.company_id.id)], limit=1).date
        if self.date <= lock_date:
            raise exceptions.UserError(_('You cannot add/modify AR record prior to and inclusive of the lock date "%s".') % (lock_date))

        self.state = 'cancel'
        if self.journal_id:
            self.journal_id.button_cancel()
            self.journal_id.unlink()

            # 20210819 - Firgiawan Khafidli
            # Realisasi advance ke billing otomatis mengubah outstanding billing 
            # Serta outstanding CL/Invoice
            # compute balance CL on confirm receipt payment
            if self.covering_id:
                if self.covering_id.sync_id:
                    print("Skip validasi Balance Karena ini data MHCL Wipro.")
                else:
                    self.covering_id.total_payment -= self.amount_receipt
                    self.covering_id.total_balance_amount += self.amount_receipt
            # Jika receipt based on Admission
            if self.billing_type == 'admission':
                for bill in self.billing_ids:
                    bill.sale_order_id.payer_receipt -= bill.payer_receipt
                    bill.sale_order_id.payer_balance += bill.payer_receipt
            # Jika receipt based on billing
            elif self.billing_type == 'bill':
                for bill in self.billing_sale_ids:
                    bill.sale_order_bill_id.payer_receipt -= bill.payer_receipt
                    bill.sale_order_bill_id.payer_balance += bill.payer_receipt
                    # bill.sale_order_bill_id.action_history(remark="CANCEL " + self.name)
                    if (bill.payer_receipt or 0) != 0:
                        bill.sale_order_bill_id.cancel_history(advance_id=self.id)
            # Jika receipt based on billing COB
            elif self.billing_type == 'cob':
                for bill in self.billing_cob_ids:
                    bill.sale_order_cob_id.payer_receipt -= bill.payer_receipt
                    bill.sale_order_cob_id.payer_balance += bill.payer_receipt
                    # bill.sale_order_cob_id.action_history(remark="CANCEL " + self.name)
                    if (bill.payer_receipt or 0) != 0:
                        bill.sale_order_bill_id.cancel_history(advance_id=self.id)


    # @api.multi
    def action_draft(self):
        self.revisi = True
        self.revisi_sequence += 1
        self.state = 'draft'
        self.update({'revisi_name': 'R' + str(self.revisi_sequence)})  


    @api.depends('billing_sale_ids.sale_order_bill_id', 'billing_sale_ids.payer_receipt')
    def _depend_amount(self):
        for record in self.billing_sale_ids:
            record.payer_amount = (record.sale_order_bill_id.payer_balance or 0)
            record.payer_ending = (record.payer_amount or 0) - (record.payer_receipt or 0)


    @api.depends('billing_cob_ids.sale_order_cob_id', 'billing_cob_ids.payer_receipt')
    def _depend_amount(self):
        for record in self.billing_cob_ids:
            record.payer_amount = (record.sale_order_cob_id.payer_balance or 0)
            record.payer_ending = (record.payer_amount or 0) - (record.payer_receipt or 0)

    @api.depends('billing_ids.sale_order_id', 'billing_ids.payer_receipt')
    def _depend_amount(self):
        for record in self.billing_ids:
            record.payer_amount = (record.sale_order_id.payer_balance or 0)
            record.payer_ending = (record.payer_amount or 0) - (record.payer_receipt or 0)


    # 2021.10.04 - compute total advance realization by billing settlement for payer/insurance only
    # @api.multi 
    def _compute_total_receipt_adjustment(self): 
        for record in self:   
            if record.payer_id.patient is not True and record.amount_receipt == 0:
                amount_receipt = 0

                if record.billing_ids:
                    for line in record.billing_ids:
                        amount_receipt += line.payer_receipt 
                if record.billing_sale_ids:
                    for line in record.billing_sale_ids:
                        amount_receipt += line.payer_receipt
                if record.billing_cob_ids:
                    for line in record.billing_cob_ids:
                        amount_receipt += line.payer_receipt

                record.amount_receipt = amount_receipt


    # @api.multi 
    def action_show_billing(self):
        for record in self:
            if record.covering_id and record.state == 'draft':
                if record.billing_type == 'bill':
                    # delete payment if exists
                    self.env.cr.execute("""
                        delete from account_payment_bill_rel 
                        where advance_realization_id={advance_id}
                        """.format(advance_id=record.id))

                    # insert new billing from MHCL 
                    self.env.cr.execute("""
                        insert into account_payment_bill_rel (
                            advance_realization_id, covering_id, sale_order_bill_id, payer_amount, payer_ending) 
                        select {advance_id} advance_realization_id, a.account_coveringletter_id covering_id, 
                            a.sale_order_bill_id, b.payer_balance as payer_amount, b.payer_balance as payer_ending 
                        from account_coveringletter_bill_rel a 
                        inner join sale_order_bill b on b.id = a.sale_order_bill_id 
                        where a.account_coveringletter_id = {letter_id}
                    """.format(
                        advance_id=record.id, 
                        letter_id=record.covering_id.id
                    ))


                if record.billing_type == 'cob':
                    # delete payment if exists
                    self.env.cr.execute("""
                        delete from account_payment_cob_rel 
                        where advance_realization_id={advance_id}
                        """.format(advance_id=record.id))

                    # insert new billing from MHCL 
                    self.env.cr.execute("""
                        insert into account_payment_cob_rel (
                            advance_realization_id, covering_id, sale_order_cob_id, payer_amount, payer_ending) 
                        select {advance_id} advance_realization_id, a.account_coveringletter_id covering_id,
                            a.sale_order_cob_id, b.payer_balance as payer_amount, b.payer_balance as payer_ending
                        from account_coveringletter_cob_rel a 
                        inner join sale_order_cob b on b.id = a.sale_order_cob_id 
                        where a.account_coveringletter_id = {letter_id}
                    """.format(
                        advance_id=record.id, 
                        letter_id=record.covering_id.id
                    ))

                if record.billing_type == 'admission':
                    # delete payment if exists
                    self.env.cr.execute("""
                        delete from account_payment_admission_rel 
                        where advance_realization_id={advance_id}
                        """.format(advance_id=record.id))

                    # insert new billing from MHCL 
                    self.env.cr.execute("""
                        insert into account_payment_admission_rel (
                            advance_realization_id, covering_id, sale_order_id, payer_amount, payer_ending) 
                        select {advance_id} advance_realization_id, a.account_coveringletter_id as covering_id,
                            a.sale_order_id, b.payer_balance as payer_amount, b.payer_balance as payer_ending
                        from account_coveringletter_admission_rel a 
                        inner join sale_order b on b.id = a.sale_order_id 
                        where a.account_coveringletter_id = {letter_id}
                    """.format(
                        advance_id=record.id, 
                        letter_id=record.covering_id.id
                    ))
            else:
                raise exceptions.ValidationError("Hanya receipt dengan status Draft dan Letter yang sudah dipilih yang dapat di settlement.")
                
    

    # @api.multi 
    def action_auto_settlement(self):
        for record in self:
            if record.amount_receipt and record.state == 'draft':
                total_receipt = record.amount_receipt
                if record.billing_type == 'bill':
                    for bill in record.billing_sale_ids:
                        if total_receipt >= bill.payer_amount:
                            bill.payer_receipt = bill.payer_amount
                            bill.payer_ending = 0
                            total_receipt -= bill.payer_amount
                        else:
                            bill.payer_receipt = total_receipt
                            bill.payer_ending = bill.payer_amount - total_receipt
                            total_receipt = 0

                if record.billing_type == 'cob':
                    for bill in record.billing_cob_ids:
                        if total_receipt >= bill.payer_amount:
                            bill.payer_receipt = bill.payer_amount
                            bill.payer_ending = 0
                            total_receipt -= bill.payer_amount
                        else:
                            bill.payer_receipt = total_receipt
                            bill.payer_ending = bill.payer_amount - total_receipt
                            total_receipt = 0

                if record.billing_type == 'admission':
                    for bill in record.billing_ids:
                        if total_receipt >= bill.payer_amount:
                            bill.payer_receipt = bill.payer_amount
                            bill.payer_ending = 0
                            total_receipt -= bill.payer_amount
                        else:
                            bill.payer_receipt = total_receipt
                            bill.payer_ending = bill.payer_amount - total_receipt
                            total_receipt = 0
            else:
                raise exceptions.ValidationError("Nominal receipt harus diisi.")


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(AccountAdvanceRealization,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Advance Realization" delete="false" decoration-info="state == 'draft'" decoration-success="state == 'confirm'" decoration-muted="state == 'cancel'">
                    <field name="name"/>
                    <field name="advance_id"/>
                    <field name="payer_id"/>
                    <field name="covering_id"/>
                    <field name="amount_receipt" sum="Receipt Amount"/>
                    <field name="state" widget="badge" decoration-info="state == 'draft'" decoration-success="state == 'confirm'" decoration-muted="state == 'cancel'"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Advance Search">
                    <filter string="Draft" domain="[('state','=', 'draft')]" help="Draft"/>
                    <filter string="Confirm" domain="[('state','=', 'confirm')]" help="Confirm"/>
                    <filter string="Cancelled" domain="[('state','=', 'cancel')]" help="Cancelled"/>
                    <separator/>
                    <field name="name"/>
                    <field name="advance_id"/>
                    <field name="payer_id"/>
                    <field name="covering_id"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res
         

class AccountPaymentAdmissionRel(models.Model):
    _name = 'account.payment.admission.rel'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    name = fields.Char(string="Admission No.")
    date = fields.Datetime(string="Admit Date", related="sale_order_id.confirmation_date")
    patient_name = fields.Char(string="Patient Name", related="sale_order_id.partner_id.name")
    account_payment_id = fields.Many2one('account.payment')
    advance_realization_id = fields.Many2one('account.advance.realization', string="Advance No.")
    sale_order_id = fields.Many2one('sale.order', string="Admission No.")
    covering_id = fields.Many2one('account.coveringletter', string="Letter No.")
    payer_amount = fields.Float(string="Outstanding Amt")
    payer_receipt = fields.Float(string="Receipt Amt")
    payer_ending = fields.Float(string="Ending Balance")

    @api.onchange('sale_order_id', 'payer_receipt')
    def _depend_amount(self):
        for record in self:
            record.payer_amount = (record.sale_order_id.payer_balance or 0)
            record.payer_ending = (record.payer_amount or 0) - (record.payer_receipt or 0)
        # self._compute_total_receipt_adjustment()

class AccountPaymentBillRel(models.Model):
    _name = 'account.payment.bill.rel'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    name = fields.Char(string="Bill No.")
    date = fields.Datetime(string="Bill Date", related="sale_order_bill_id.confirmation_date")
    patient_name = fields.Char(string="Patient Name", related="sale_order_bill_id.partner_id.name")
    account_payment_id = fields.Many2one('account.payment', "Receipt No.")
    advance_realization_id = fields.Many2one('account.advance.realization', string="Advance No.")
    sale_order_bill_id = fields.Many2one('sale.order.bill', string="Bill No.")
    covering_id = fields.Many2one('account.coveringletter', string="Letter No.")
    payer_amount = fields.Float(string="Outstanding Amt")
    payer_receipt = fields.Float(string="Receipt Amt")
    payer_ending = fields.Float(string="Ending Balance")
    remark = fields.Char(string="Remark")


    @api.onchange('sale_order_bill_id', 'payer_receipt')
    def _depend_amount(self):
        for record in self:
            record.payer_amount = (record.sale_order_bill_id.payer_balance or 0)
            record.payer_ending = (record.payer_amount or 0) - (record.payer_receipt or 0)
        # self._compute_total_receipt_adjustment()

    @api.constrains('advance_realization_id', 'sale_order_bill_id')
    def _check_duplicate_bill_id(self):
        for record in self.filtered(
            lambda line: line.advance_realization_id and line.sale_order_bill_id
        ):
            duplicate = self.search([
                ('id', '!=', record.id),
                ('advance_realization_id', '=', record.advance_realization_id.id),
                ('sale_order_bill_id', '=', record.sale_order_bill_id.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    "The same billing line cannot be settled more than once in one Advance Realization."
                ))

    @api.constrains('payer_receipt', 'payer_amount')
    def _check_payer_receipt(self):
        for record in self:
            if record.payer_receipt < 0:
                raise ValidationError(_("Billing realization amount cannot be negative."))
            if record.payer_receipt > (record.payer_amount or 0.0):
                raise ValidationError(_("Billing realization amount cannot exceed payer balance."))



class AccountPaymentCobRel(models.Model):
    _name = 'account.payment.cob.rel'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    name = fields.Char(string="COB No.")
    date = fields.Datetime(string="COB Date", related="sale_order_cob_id.cob_date")
    patient_name = fields.Char(string="Patient Name", related="sale_order_cob_id.billing_id.partner_id.name")
    account_payment_id = fields.Many2one('account.payment', string="Receipt No.")
    advance_realization_id = fields.Many2one('account.advance.realization', string="Advance No.")
    sale_order_cob_id = fields.Many2one('sale.order.cob', string="COB No.")
    covering_id = fields.Many2one('account.coveringletter', string="Letter No.")
    payer_amount = fields.Float(string="Outstanding Amt")
    payer_receipt = fields.Float(string="Receipt Amt")
    payer_ending = fields.Float(string="Ending Balance")

    @api.onchange('sale_order_cob_id', 'payer_receipt')
    def _depend_amount(self):
        for record in self:
            record.payer_amount = (record.sale_order_cob_id.payer_balance or 0)
            record.payer_ending = (record.payer_amount or 0) - (record.payer_receipt or 0)
        # self._compute_total_receipt_adjustment()

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(AccountPaymentCobRel,self).get_view(view_id=view_id,view_type=view_type, **options)
        res['arch'] = """
            <form string="Payment Receipt" delete="false" readonly="1">
                <sheet>
                    <group>
                        <group>
                            <field name="advance_realization_id" />
                            <field name="account_payment_id" />
                            <field name="covering_id"/>
                            <field name="sale_order_cob_id"/>
                            <field name="name"/>
                        </group>
                        <group>
                            <field name="date"/>
                            <field name="patient_name"/>
                            <field name="payer_amount"/>
                            <field name="payer_receipt"/>
                            <field name="payer_ending"/>
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


class AccountAdvanceRealizationImportWizard(models.TransientModel):
    _name = 'account.advance.realization.import.wizard'
    _description = 'AR Advance Realization Excel Import'

    _HEADERS = ('letter_no', 'admission_no', 'bill_no', 'apply_amount', 'notes')
    _XLSX_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    _REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    _PACKAGE_REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'

    advance_realization_id = fields.Many2one(
        'account.advance.realization',
        string='Advance Realization',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    upload_file = fields.Binary(string='Excel File', attachment=False)
    filename = fields.Char(string='Filename')
    template_file = fields.Binary(string='Template File', readonly=True, attachment=False)
    template_filename = fields.Char(string='Template Filename', readonly=True)

    @api.model
    def _normalize_text(self, value):
        if value is None or value is False:
            return ''
        text = str(value).strip()
        if re.fullmatch(r'[+-]?\d+\.0+', text):
            text = text.split('.', 1)[0]
        return text

    @api.model
    def _normalized_key(self, value):
        return self._normalize_text(value).casefold()

    @api.model
    def _column_index(self, cell_reference):
        letters = ''.join(character for character in cell_reference if character.isalpha())
        index = 0
        for character in letters.upper():
            index = (index * 26) + ord(character) - ord('A') + 1
        return index - 1

    @api.model
    def _build_xlsx(self, rows):
        import xlsxwriter

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Advance Realization Import')
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D9EAF7'})
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                cell_format = header_format if row_index == 0 else None
                worksheet.write(row_index, column_index, value, cell_format)
        worksheet.set_column('A:C', 22)
        worksheet.set_column('D:D', 18)
        worksheet.set_column('E:E', 35)
        worksheet.autofilter(0, 0, 0, len(self._HEADERS) - 1)
        workbook.close()
        return output.getvalue()

    def action_download_template(self):
        self.ensure_one()
        self.template_filename = 'ar_advance_realization_import_template.xlsx'
        self.template_file = base64.b64encode(self._build_xlsx([self._HEADERS]))
        return {
            'type': 'ir.actions.act_url',
            'url': (
                '/web/content/?model=account.advance.realization.import.wizard&id=%s'
                '&field=template_file&filename_field=template_filename&download=true'
            ) % self.id,
            'target': 'self',
        }

    @api.model
    def _xlsx_rows(self, file_content):
        try:
            archive = zipfile.ZipFile(io.BytesIO(file_content), 'r')
        except (zipfile.BadZipFile, TypeError, ValueError):
            raise ValidationError(_("The uploaded file is not a valid .xlsx workbook."))

        try:
            workbook_root = ElementTree.fromstring(archive.read('xl/workbook.xml'))
            relationships_root = ElementTree.fromstring(
                archive.read('xl/_rels/workbook.xml.rels')
            )
            sheets = workbook_root.findall(
                '{%s}sheets/{%s}sheet' % (self._XLSX_NS, self._XLSX_NS)
            )
            if not sheets:
                raise ValidationError(_("The uploaded workbook does not contain a worksheet."))

            relationship_id = sheets[0].get('{%s}id' % self._REL_NS)
            targets = {
                relation.get('Id'): relation.get('Target')
                for relation in relationships_root.findall(
                    '{%s}Relationship' % self._PACKAGE_REL_NS
                )
            }
            target = targets.get(relationship_id)
            if not target:
                raise ValidationError(_("The first worksheet in the uploaded workbook is invalid."))
            sheet_path = (
                target.lstrip('/')
                if target.startswith('/')
                else posixpath.normpath('xl/' + target)
            )

            shared_strings = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                shared_root = ElementTree.fromstring(archive.read('xl/sharedStrings.xml'))
                for item in shared_root.findall('{%s}si' % self._XLSX_NS):
                    shared_strings.append(''.join(
                        node.text or '' for node in item.iter('{%s}t' % self._XLSX_NS)
                    ))

            sheet_root = ElementTree.fromstring(archive.read(sheet_path))
            parsed_rows = []
            for row in sheet_root.findall(
                './/{%s}sheetData/{%s}row' % (self._XLSX_NS, self._XLSX_NS)
            ):
                row_number = int(row.get('r') or (len(parsed_rows) + 1))
                values = []
                for cell in row.findall('{%s}c' % self._XLSX_NS):
                    column_index = self._column_index(cell.get('r') or '')
                    while len(values) <= column_index:
                        values.append('')
                    cell_type = cell.get('t')
                    if cell_type == 'inlineStr':
                        value = ''.join(
                            node.text or '' for node in cell.iter('{%s}t' % self._XLSX_NS)
                        )
                    else:
                        value_node = cell.find('{%s}v' % self._XLSX_NS)
                        value = value_node.text if value_node is not None else ''
                        if cell_type == 's' and value != '':
                            value = shared_strings[int(value)]
                    values[column_index] = value
                parsed_rows.append((row_number, values))
            return parsed_rows
        except ValidationError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, ElementTree.ParseError):
            raise ValidationError(_("The uploaded file is not a valid .xlsx workbook."))
        finally:
            archive.close()

    @api.model
    def _parse_apply_amount(self, value, row_number):
        text = self._normalize_text(value)
        if not text:
            raise ValidationError(_("Row %s: Apply Amount is required.") % row_number)
        normalized = text.replace(' ', '')
        if re.fullmatch(r'[+-]?\d{1,3}(,\d{3})+(\.\d+)?', normalized):
            normalized = normalized.replace(',', '')
        try:
            amount = Decimal(normalized)
        except (InvalidOperation, ValueError):
            raise ValidationError(_(
                "Row %s: Apply Amount %s is not a valid numeric value."
            ) % (row_number, text))
        if not amount.is_finite():
            raise ValidationError(_(
                "Row %s: Apply Amount %s is not a valid numeric value."
            ) % (row_number, text))
        return float(amount)

    @api.model
    def _format_amount(self, amount):
        return '{:,.2f}'.format(amount).rstrip('0').rstrip('.')

    def _validate_advance_realization(self):
        self.ensure_one()
        realization = self.advance_realization_id.exists()
        if not realization:
            raise ValidationError(_("The Advance Realization was not found."))
        if realization.state != 'draft':
            raise ValidationError(_(
                "Excel import is only available for Draft Advance Realizations."
            ))
        if not realization.covering_id:
            raise ValidationError(_("Please select a Covering Letter before importing."))
        if realization.billing_type != 'bill':
            raise ValidationError(_(
                "Advance Realization Excel import currently supports Bill billing type only."
            ))
        return realization

    def _validated_import_rows(self, realization, workbook_rows):
        if not workbook_rows:
            raise ValidationError(_("The uploaded workbook is empty."))

        header_row_number, header_values = workbook_rows[0]
        headers = tuple(self._normalize_text(value) for value in header_values)
        while headers and not headers[-1]:
            headers = headers[:-1]
        if header_row_number != 1 or headers != self._HEADERS:
            raise ValidationError(_(
                "Row 1 must contain exactly these columns in order: %s."
            ) % ', '.join(self._HEADERS))

        source_bills = realization.covering_id.billing_sale_ids
        source_bills.invalidate_recordset(['billno', 'admission_no', 'payer_balance'])
        bills_by_number = {}
        for bill in source_bills:
            key = self._normalized_key(bill.billno)
            bills_by_number.setdefault(key, self.env['sale.order.bill'])
            bills_by_number[key] |= bill

        rounding = realization.company_id.currency_id.rounding or 0.01
        selected_letter_no = self._normalize_text(realization.covering_id.name)
        selected_letter_key = self._normalized_key(selected_letter_no)
        prepared_rows = []
        duplicate_rows = {}

        for row_number, raw_values in workbook_rows[1:]:
            values = list(raw_values[:5])
            values += [''] * (5 - len(values))
            if not any(self._normalize_text(value) for value in values):
                continue

            letter_no, admission_no, bill_no, apply_amount, notes = values
            letter_no = self._normalize_text(letter_no)
            admission_no = self._normalize_text(admission_no)
            bill_no = self._normalize_text(bill_no)
            notes = self._normalize_text(notes)

            if not letter_no:
                raise ValidationError(_("Row %s: Letter No is required.") % row_number)
            if self._normalized_key(letter_no) != selected_letter_key:
                raise ValidationError(_(
                    "Row %s: Letter No %s does not match the selected Covering Letter %s."
                ) % (row_number, letter_no, selected_letter_no or '-'))
            if not bill_no:
                raise ValidationError(_("Row %s: Bill No is required.") % row_number)

            matching_bills = bills_by_number.get(
                self._normalized_key(bill_no), self.env['sale.order.bill']
            )
            if not matching_bills:
                raise ValidationError(_(
                    "Row %s: Bill No %s was not found in the selected Covering Letter."
                ) % (row_number, bill_no))
            if len(matching_bills) > 1 and admission_no:
                admission_key = self._normalized_key(admission_no)
                matching_admissions = matching_bills.filtered(
                    lambda bill: self._normalized_key(bill.admission_no) == admission_key
                )
                if len(matching_admissions) == 1:
                    matching_bills = matching_admissions
            if len(matching_bills) != 1:
                raise ValidationError(_(
                    "Row %s: Bill No %s is ambiguous within the selected Covering Letter."
                ) % (row_number, bill_no))

            bill = matching_bills
            amount = self._parse_apply_amount(apply_amount, row_number)
            if float_compare(amount, 0.0, precision_rounding=rounding) <= 0:
                raise ValidationError(_(
                    "Row %s: Apply Amount must be greater than zero."
                ) % row_number)
            live_balance = bill.payer_balance or 0.0
            if float_compare(amount, live_balance, precision_rounding=rounding) > 0:
                raise ValidationError(_(
                    "Row %s: Apply Amount %s exceeds the current billing balance %s."
                ) % (
                    row_number,
                    self._format_amount(amount),
                    self._format_amount(live_balance),
                ))

            duplicate_rows.setdefault(bill.id, []).append(row_number)
            prepared_rows.append({
                'row_number': row_number,
                'bill': bill,
                'bill_no': bill_no,
                'payer_amount': live_balance,
                'payer_receipt': amount,
                'payer_ending': live_balance - amount,
                'remark': notes or False,
            })

        if not prepared_rows:
            raise ValidationError(_(
                "The uploaded workbook does not contain any populated data rows."
            ))

        for bill_id, row_numbers in duplicate_rows.items():
            if len(row_numbers) > 1:
                duplicate = next(
                    row for row in prepared_rows if row['bill'].id == bill_id
                )
                raise ValidationError(_(
                    "Rows %s: Bill No %s is duplicated in the uploaded file."
                ) % (
                    ' and '.join(str(number) for number in row_numbers),
                    duplicate['bill_no'],
                ))

        existing_by_bill = {}
        for line in realization.billing_sale_ids.filtered('sale_order_bill_id'):
            bill_id = line.sale_order_bill_id.id
            existing_by_bill.setdefault(bill_id, self.env['account.payment.bill.rel'])
            existing_by_bill[bill_id] |= line
        for prepared in prepared_rows:
            matching_lines = existing_by_bill.get(
                prepared['bill'].id, self.env['account.payment.bill.rel']
            ).sorted('id')
            prepared['existing_line'] = matching_lines[:1]
            prepared['duplicate_lines'] = matching_lines[1:]
        return prepared_rows

    def action_import(self):
        self.ensure_one()
        realization = self._validate_advance_realization()
        if not self.upload_file:
            raise ValidationError(_("Please upload an Excel file."))
        if not self.filename or not self.filename.lower().endswith('.xlsx'):
            raise ValidationError(_("Please upload a file with the .xlsx extension."))

        try:
            file_content = base64.b64decode(self.upload_file, validate=True)
        except (ValueError, TypeError):
            raise ValidationError(_("The uploaded file could not be decoded."))

        workbook_rows = self._xlsx_rows(file_content)
        prepared_rows = self._validated_import_rows(realization, workbook_rows)

        created_values = []
        updated_count = 0
        for prepared in prepared_rows:
            values = {
                'covering_id': realization.covering_id.id,
                'payer_amount': prepared['payer_amount'],
                'payer_receipt': prepared['payer_receipt'],
                'payer_ending': prepared['payer_ending'],
                'remark': prepared['remark'],
            }
            if prepared['existing_line']:
                prepared['duplicate_lines'].unlink()
                prepared['existing_line'].write(values)
                updated_count += 1
            else:
                values.update({
                    'advance_realization_id': realization.id,
                    'sale_order_bill_id': prepared['bill'].id,
                })
                created_values.append(values)

        if created_values:
            self.env['account.payment.bill.rel'].create(created_values)
        total_realization = sum(realization.billing_sale_ids.mapped('payer_receipt'))
        realization.with_context(sudah_total=True).write({
            'amount_receipt': total_realization,
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("AR Advance Realization Import"),
                'message': _(
                    "Import completed: %s lines created and %s existing lines updated."
                ) % (len(created_values), updated_count),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }






class LockArConfiguration(models.Model):
    _name = 'lock.ar.configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'company_id'

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_type = sync.type
    sync_date = sync.date 
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    date = fields.Date(string="Date", required=True)
    remark = fields.Char(string="Remarks", required=True)

    @api.onchange('company_id')
    def _domain_service(self):
        self.sync_type = self.company_id.sync_type


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(LockArConfiguration,self).get_view(view_id=view_id,view_type=view_type, **options)

        if view_type == 'form':
            res['arch'] = """
                <form string="Lock AR Configuration">
                    <sheet>
                        <group>
                            <field name="company_id" />
                            <field name="date" />
                            <field name="remark" />
                        </group>
                        <notebook>
                            <page string="Technical">
                                 <group>
                                    <group>
                                        <field name="sync_type"/>
                                        <field name="sync_date"/>
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
                    <div class="o_attachment_preview"/>
                    <div class="oe_chatter">
                        <field name="message_follower_ids"/>
                        <field name="activity_ids"/>
                        <field name="message_ids"/>
                    </div>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Referral Fee Deduction">
                    <field name="date"/>
                    <field name="company_id"/>
                    <field name="sync_type"/>
                </tree>
            """
        
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res





class ScrollReceiptCashier(models.Model):
    _name = 'scroll.receipt.cashier'
    _rec_name = 'facility_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    sync_id = sync.id
    sync_date = sync.date
    sync_type = sync.type
    sync_id_api = sync.id_api
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    tglproses = fields.Date(string="TglProses")
    trans_type = fields.Char(string="Transaction Type")
    user_name = fields.Char(string="User Name")
    facility_name = fields.Char(string="Facility Name")
    payment_name = fields.Char(string="Payment Name")
    edc_machine = fields.Char(string="EDC Machine")
    total_collect = fields.Float(string="Total Collect")
    partner_id = fields.Many2one('res.partner', string="Patient")
    billing_id = fields.Many2one('sale.order.bill',string="Billing No.",required=False)
    admission_id = fields.Many2one('sale.order',string="Admission No.",required=False)
    company_id = fields.Many2one('res.company',string="Company",required=True,readonly=True,default=_get_company)
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')],string="Status",readonly=True,default='draft', track_visibility='always')
    journal_id = fields.Many2one('account.move',string="Journal")
    note = fields.Text(string="Notes")
    is_akasia = fields.Boolean(string="Is Akasia")

    # untuk send payload dari dhealth cuma kirim sync_type, auto-fill company_id
    @api.model
    def create(self, vals):
        result = super(ScrollReceiptCashier, self).create(vals)
        # if not vals.get('company_id'):
        #     result.company_id = self.env['res.company'].sudo().search([('sync_type', '=', vals.get('sync_type'))],limit=1).id
        
        if not vals.get('partner_id') and vals.get('admission_id'):
            result.partner_id = result.admission_id.partner_id.id or None
        return result

    # @api.multi
    def unlink(self):
        for r in self:
            if r.state == 'confirmed':
                raise exceptions.ValidationError("Please cancel the record before delete")
        return super(ScrollReceiptCashier, self).unlink()


    # @api.multi
    def action_draft(self):
        for record in self:
            record.state = 'draft'

            
    # @api.multi
    def action_confirm(self):
        journal_id = self.env['account.journal'].search([('name', 'ilike', '%Scroll Cashier Receipt%'),('company_id', '=', self.company_id.id)],limit=1)
        account_partner = self.env['account.account'].search([('name', '=', 'Private Outstanding'),('company_id', '=', self.company_id.id)],limit=1)
        
        # 2022.01.31 - Ambil COA dari res.company untuk seluruh Scroll Receipt Cashier > 31-Jan-2022
        if self.tglproses > datetime.strptime('2022-01-31', '%Y-%m-%d').date(): 
            account_partner = self.company_id.receivable_cash_id

            if self.trans_type in['Cash']:
                account = self.company_id.reveivable_receipt_cash_id
            elif self.trans_type in['CreditCard']:
                account = self.company_id.reveivable_receipt_credit_id
            elif self.trans_type in['DebitCard','debit card']:
                account = self.company_id.reveivable_receipt_debit_id
            elif self.trans_type in['BankTransfer']:
                account = self.company_id.reveivable_receipt_transfer_id
            elif self.trans_type in['Voucher']:
                account = self.company_id.reveivable_receipt_voucher_id
            elif self.trans_type in['Cheque']:
                account = self.company_id.reveivable_receipt_cheque_id
            elif not self.trans_type:
                account = self.company_id.reveivable_receipt_cash_id
            
        else:
            if self.trans_type == 'Cash':
                account = self.env['account.account'].search([('type_scroll', '=', 'cash'),('company_id', '=', self.company_id.id)],limit=1)
            else:
                account = self.env['account.account'].search([('type_scroll', '=', 'credit'),('company_id', '=', self.company_id.id)],limit=1)
            
        
        if not self.facility_name:
            self.facility_name = ' '

        if self.total_collect == 0:
            self.state = 'confirmed'

        if self.total_collect > 0:
            debit_vals = {
                'name':"Receipt " + str(self.user_name or "") + " " + str(self.facility_name or "") + " " + str(self.trans_type or "") + " " + str(self.edc_machine or "") + " " + str(self.admission_id.name or ""),
                'debit':abs(self.total_collect),
                'credit':0.0,
                'partner_id': self.partner_id.id or None,
                'account_id':account.id
            }
            credit_vals = {
                'name':"Receipt " + str(self.user_name or "") + " " + str(self.facility_name or "") + " " + str(self.trans_type or "") + " " + str(self.edc_machine or "") + " " + str(self.admission_id.name or ""),
                'debit':0.0,
                'credit':abs(self.total_collect),
                'partner_id': self.partner_id.id or None,
                'account_id':account_partner.id
            }

            vals = {
                'journal_id': journal_id.id,
                'date': self.tglproses,
                'state': 'draft',
                'line_ids': [(0, 0, debit_vals), (0, 0, credit_vals)]
            }
            move = self.env['account.move'].create(vals)
            move.action_post()
            self.journal_id = move.id
            self.state = 'confirmed'

        if self.total_collect < 0:
            debit_vals = {
                'name':"Refund " + str(self.user_name or "") + " " + str(self.facility_name or "") + " " + str(self.trans_type or "") + " " + str(self.edc_machine or "") + " " + str(self.admission_id.name or ""),
                'debit':abs(self.total_collect),
                'credit':0.0,
                'partner_id': self.partner_id.id or None,
                'account_id':account_partner.id
            }
            credit_vals = {
                'name':"Refund " + str(self.user_name or "") + " " + str(self.facility_name or "") + " " + str(self.trans_type or "") + " " + str(self.edc_machine or "") + " " + str(self.admission_id.name or ""),
                'debit':0.0,
                'credit':abs(self.total_collect),
                'partner_id': self.partner_id.id or None,
                'account_id':account.id
            }

            vals = {
                'journal_id': journal_id.id,
                'date': self.tglproses,
                'state': 'draft',
                'line_ids': [(0, 0, debit_vals), (0, 0, credit_vals)]
            }
            move = self.env['account.move'].create(vals)
            self.journal_id = move.id
            move.action_post()
            self.state = 'confirmed'

            # 20210819 - update personal_balance pada billing
            if self.sync_id == 0 and self.payment_name in['RECEIPT','REFUND']:
                if self.billing_id:
                    if (self.billing_id.personal_receipt or 0) == 0:
                        self.billing_id.personal_balance = self.billing_id.personal_amount
                    self.billing_id.personal_receipt += self.total_collect 
                    self.billing_id.personal_balance -= self.total_collect

                if self.admission_id:
                    if (self.admission_id.personal_receipt or 0) == 0:
                        self.admission_id.personal_balance = self.admission_id.personal_amount
                    self.admission_id.personal_receipt += self.total_collect 
                    self.admission_id.personal_balance -= self.total_collect

        return True

    # @api.multi
    def action_cancel_call(self):
        for record in self:
            record.state = 'cancel'

    # @api.multi
    def action_cancel(self):
        if self.state == 'confirmed':
            self.state = 'draft'
            self.journal_id.button_cancel()
            self.journal_id.unlink()

            if self.sync_id == 0 and self.payment_name in['RECEIPT','REFUND']:
                if self.billing_id and self.billing_id.personal_receipt > 0:
                    self.billing_id.personal_receipt -= self.total_collect 
                    self.billing_id.personal_balance += self.total_collect
                if self.admission_id and self.admission_id.personal_receipt:
                    self.admission_id.personal_receipt -= self.total_collect 
                    self.admission_id.personal_balance += self.total_collect

    @api.model
    def _sync_scroll_receipt_cashier_wipro(self, sync_type='1'):
        import trollius as asyncio
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>',0)])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)],order='sync_date desc',limit=1).sync_date
        data = []
        date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
        query = """
            SELECT 
                'draft' 'state',
                TglProses 'tglproses',
                UserID 'sync_id',
                UserName 'user_name',
                FacilityName 'facility_name',
                PaymentMode 'trans_type',
                TotalCollect 'total_collect',
                SummaryNote 'note'
            from dbo.VRP_OdooWiseCollectionSummary a
            where a.tglproses = '%s'
            -- where a.tglproses >= '2019-01-01' and a.tglproses <= '2019-01-31'
            """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), query)
        print (data)
        if not data:
            print ("No data available")
            return
        fields_without_id = tuple(
            key for key in self._fields
            if key != 'id' and 'property' not in key and 'ids' not in key
            and self._fields[key].required == True
            and self._fields[key].store == True)
        columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
        fields_without_id += columns
        columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
        fields = fields_without_id + ('id', )
        if columns:
            columns += ('id', )
        default_values = {}
        for field in fields:
            if field in columns:
                continue
            default = self._fields[field].default
            if callable(default):
                default = default(self)
            if isinstance(default, models.Model):
                default = default.id
            default_values[field] = default
        values = ''
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        @asyncio.coroutine
        def process_query(object):
            for value in default_values:
                object[value] = default_values[value]

            object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)],limit=1).id
            value = False
            for field in fields:
                if value:
                    value += ', '
                else:
                    value = '('
                if field == 'id' and object['id'] == 'DEFAULT':
                    value += object['id']
                    continue
                if type(object[field]) in [str, unicode]:
                    string = object[field]
                    value += "'" + string.replace("'", "''") + "'"
                    continue
                value += sync.json(object[field])
            value += ')'
            return value
            #values += value

        loop = asyncio.get_event_loop()
        tasks = [asyncio.create_task(process_query(object)) for object in data]
        for result in loop.run_until_complete(asyncio.gather(*tasks)):
            if result:
                if values:
                    values += ', '
                values += result
        excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        columns = sync.remove_unicode(str(fields)).replace("'", "")
        columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        print (values)
        if not values:
            print ("No data available")
            return
        query = "INSERT into scroll_receipt_cashier %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)


    @api.model
    def _sync_scroll_receipt_cashier_wipro_manual(self,sync_type='1',date_start='2019-01-01',date_end='2019-01-01'):
        import trollius as asyncio
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>',0)])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)],order='sync_date desc',limit=1).sync_date
        data = []
        date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
        query = """
            SELECT 
                'draft' 'state',
                TglProses 'tglproses',
                UserID 'sync_id',
                UserName 'user_name',
                FacilityName 'facility_name',
                PaymentMode 'trans_type',
                TotalCollect 'total_collect',
                SummaryNote 'note'
            from dbo.VRP_OdooWiseCollectionSummary a
            -- where a.tglproses = ''
            where a.tglproses >= '%s' and a.tglproses <= '%s'
            """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), query)
        print (data)
        if not data:
            print ("No data available")
            return
        fields_without_id = tuple(
            key for key in self._fields
            if key != 'id' and 'property' not in key and 'ids' not in key
            and self._fields[key].required == True
            and self._fields[key].store == True)
        columns = tuple(
            key for key in data[0].keys()
            if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
        fields_without_id += columns
        columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
        fields = fields_without_id + ('id', )
        if columns:
            columns += ('id', )
        default_values = {}
        for field in fields:
            if field in columns:
                continue
            default = self._fields[field].default
            if callable(default):
                default = default(self)
            if isinstance(default, models.Model):
                default = default.id
            default_values[field] = default
        values = ''
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        @asyncio.coroutine
        def process_query(object):
            for value in default_values:
                object[value] = default_values[value]

            object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)],limit=1).id
            value = False
            for field in fields:
                if value:
                    value += ', '
                else:
                    value = '('
                if field == 'id' and object['id'] == 'DEFAULT':
                    value += object['id']
                    continue
                if type(object[field]) in [str, unicode]:
                    string = object[field]
                    value += "'" + string.replace("'", "''") + "'"
                    continue
                value += sync.json(object[field])
            value += ')'
            return value
            #values += value

        loop = asyncio.get_event_loop()
        tasks = [asyncio.create_task(process_query(object)) for object in data]
        for result in loop.run_until_complete(asyncio.gather(*tasks)):
            if result:
                if values:
                    values += ', '
                values += result
        excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        columns = sync.remove_unicode(str(fields)).replace("'", "")
        columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        print (values)
        if not values:
            print ("No data available")
            return
        query = "INSERT into scroll_receipt_cashier %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)

    # @api.model
    # def _sync_scroll_receipt_cashier_wipro(self, sync_type='1'):
    #     import trollius as asyncio
    #     sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>',0)])}
    #     sync_date = self.sudo().search([('sync_type', '=', sync_type)],order='sync_date desc',limit=1).sync_date
    #     data = []
    #     date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
    #     query = """
    #         SELECT 
    #             'draft' 'state',
    #             TglProses 'tglproses',
    #             UserID 'sync_id',
    #             UserName 'user_name',
    #             FacilityName 'facility_name',
    #             PaymentMode 'trans_type',
    #             TotalCollect 'total_collect',
    #             SummaryNote 'note'
    #         from dbo.VRP_OdooWiseCollectionSummary a
    #         where a.tglproses = '%s'
    #         -- where a.tglproses >= '2019-01-01' and a.tglproses <= '2019-01-31'
    #         """ % (date)
    #     data += sync.get_data(sync.servers.get(sync_type), query)
    #     print (data)
    #     if not data:
    #         print ("No data available")
    #         return
    #     fields_without_id = tuple(
    #         key for key in self._fields
    #         if key != 'id' and 'property' not in key and 'ids' not in key
    #         and self._fields[key].required == True
    #         and self._fields[key].store == True)
    #     columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
    #     fields_without_id += columns
    #     columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
    #     fields = fields_without_id + ('id', )
    #     if columns:
    #         columns += ('id', )
    #     default_values = {}
    #     for field in fields:
    #         if field in columns:
    #             continue
    #         default = self._fields[field].default
    #         if callable(default):
    #             default = default(self)
    #         if isinstance(default, models.Model):
    #             default = default.id
    #         default_values[field] = default
    #     values = ''
    #     now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    #     @asyncio.coroutine
    #     def process_query(object):
    #         for value in default_values:
    #             object[value] = default_values[value]

    #         object['id'] = 'DEFAULT'
    #         object['sync_date'] = now
    #         object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)],limit=1).id
    #         value = False
    #         for field in fields:
    #             if value:
    #                 value += ', '
    #             else:
    #                 value = '('
    #             if field == 'id' and object['id'] == 'DEFAULT':
    #                 value += object['id']
    #                 continue
    #             if type(object[field]) in [str, unicode]:
    #                 string = object[field]
    #                 value += "'" + string.replace("'", "''") + "'"
    #                 continue
    #             value += sync.json(object[field])
    #         value += ')'
    #         return value
    #         #values += value

    #     # loop = asyncio.get_event_loop() --DR
    #     # tasks = [asyncio.create_task(process_query(object)) for object in data]
    #     # for result in loop.run_until_complete(asyncio.gather(*tasks)):
    #     #     if result:
    #     #         if values:
    #     #             values += ', '
    #     #         values += result
    #     # excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
    #     # columns = sync.remove_unicode(str(fields)).replace("'", "")
    #     # columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
    #     # print (values)
    #     # if not values:
    #     #     print ("No data available")
    #     #     return
    #     # query = "INSERT into scroll_receipt_cashier %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
    #     # print (query.encode('utf8'))
    #     # self.env.cr.execute(query)


    # @api.model
    # def _sync_scroll_receipt_cashier_wipro_manual(self,sync_type='1',date_start='2019-01-01',date_end='2019-01-01'):
    #     import trollius as asyncio
    #     sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>',0)])}
    #     sync_date = self.sudo().search([('sync_type', '=', sync_type)],order='sync_date desc',limit=1).sync_date
    #     data = []
    #     date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
    #     query = """
    #         SELECT 
    #             'draft' 'state',
    #             TglProses 'tglproses',
    #             UserID 'sync_id',
    #             UserName 'user_name',
    #             FacilityName 'facility_name',
    #             PaymentMode 'trans_type',
    #             TotalCollect 'total_collect',
    #             SummaryNote 'note'
    #         from dbo.VRP_OdooWiseCollectionSummary a
    #         -- where a.tglproses = ''
    #         where a.tglproses >= '%s' and a.tglproses <= '%s'
    #         """ % (date_start, date_end)
    #     data += sync.get_data(sync.servers.get(sync_type), query)
    #     print (data)
    #     if not data:
    #         print ("No data available")
    #         return
    #     fields_without_id = tuple(
    #         key for key in self._fields
    #         if key != 'id' and 'property' not in key and 'ids' not in key
    #         and self._fields[key].required == True
    #         and self._fields[key].store == True)
    #     columns = tuple(
    #         key for key in data[0].keys()
    #         if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
    #     fields_without_id += columns
    #     columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
    #     fields = fields_without_id + ('id', )
    #     if columns:
    #         columns += ('id', )
    #     default_values = {}
    #     for field in fields:
    #         if field in columns:
    #             continue
    #         default = self._fields[field].default
    #         if callable(default):
    #             default = default(self)
    #         if isinstance(default, models.Model):
    #             default = default.id
    #         default_values[field] = default
    #     values = ''
    #     now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    #     @asyncio.coroutine
    #     def process_query(object):
    #         for value in default_values:
    #             object[value] = default_values[value]

    #         object['id'] = 'DEFAULT'
    #         object['sync_date'] = now
    #         object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)],limit=1).id
    #         value = False
    #         for field in fields:
    #             if value:
    #                 value += ', '
    #             else:
    #                 value = '('
    #             if field == 'id' and object['id'] == 'DEFAULT':
    #                 value += object['id']
    #                 continue
    #             if type(object[field]) in [str, unicode]:
    #                 string = object[field]
    #                 value += "'" + string.replace("'", "''") + "'"
    #                 continue
    #             value += sync.json(object[field])
    #         value += ')'
    #         return value
    #         #values += value

    #     # loop = asyncio.get_event_loop() --DR
    #     # tasks = [asyncio.create_task(process_query(object)) for object in data]
    #     # for result in loop.run_until_complete(asyncio.gather(*tasks)):
    #     #     if result:
    #     #         if values:
    #     #             values += ', '
    #     #         values += result
    #     # excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
    #     # columns = sync.remove_unicode(str(fields)).replace("'", "")
    #     # columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
    #     # print values
    #     # if not values:
    #     #     print ("No data available")
    #     #     return
    #     # query = "INSERT into scroll_receipt_cashier %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
    #     # print (query.encode('utf8'))
    #     # self.env.cr.execute(query)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ScrollReceiptCashier,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Cashier Scroll" delete="false" decoration-muted="state == 'cancel'" decoration-info="state == 'draft'">
                    <field name="tglproses"/>
                    <field name="user_name"/>
                    <field name="payment_name" />
                    <field name="trans_type"/>
                    <field name="edc_machine"/>
                    <field name="facility_name"/>
                    <field name="total_collect"/>
                    <field name="state"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Receipt..">
                    <filter string="Cancelled" domain="[('state','=', 'cancel')]" help="Cancelled"/>
                    <filter string="Draft" domain="[('state','=', 'draft')]" help="Draft"/>
                    <filter string="Confirm" domain="[('state','=', 'confirmed')]" help="Confirm"/>
                    <separator/>
                    <field name="user_name"/>
                    <field name="facility_name"/>
                    <field name="payment_name"/>
                    <field name="trans_type"/>
                    <field name="note"/>
                    <field name="edc_machine"/>
                    <field name="admission_id"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res



class AccountInvoiceLine(models.Model):
    _name = "account.invoice.line"
    _description = "Invoice Line"
    _order = "invoice_id,sequence,id"

    @api.model
    def _default_account(self):
        if self._context.get('journal_id'):
            journal = self.env['account.journal'].browse(self._context.get('journal_id'))
            if self._context.get('type') in ('out_invoice', 'in_refund'):
                return journal.default_credit_account_id.id
            return journal.default_debit_account_id.id


    # @api.multi
    def _get_analytic_line(self):
        ref = self.invoice_id.number
        return {
            'name': self.name,
            'date': self.invoice_id.date_invoice,
            'account_id': self.account_analytic_id.id,
            'unit_amount': self.quantity,
            'amount': self.price_subtotal_signed,
            'product_id': self.product_id.id,
            'product_uom_id': self.uom_id.id,
            'general_account_id': self.account_id.id,
            'ref': ref,
        }


    # @api.one
    # @api.depends('price_unit', 'discount', 'invoice_line_tax_ids', 'quantity',
    #     'product_id', 'invoice_id.partner_id', 'invoice_id.currency_id', 'invoice_id.company_id',
    #     'invoice_id.date_invoice', 'invoice_id.date')
    @api.depends('quantity','price_unit', 'discount_persen', 'discount_value', 'discount_total', 'invoice_line_tax_ids', 'price_subtotal')
    def _compute_price(self):
        for record in self:
            currency = record.invoice_id and record.invoice_id.currency_id or None
            price = record.price_unit * (1 - (record.discount or 0.0) / 100.0)
            taxes = False
            if record.invoice_line_tax_ids:
                taxes = record.invoice_line_tax_ids.compute_all(price, currency, record.quantity, product=record.product_id, partner=record.invoice_id.partner_id)
            record.price_subtotal = price_subtotal_signed = taxes['total_excluded'] if taxes else record.quantity * price
            if record.invoice_id.currency_id and record.invoice_id.company_id and record.invoice_id.currency_id != record.invoice_id.company_id.currency_id:
                price_subtotal_signed = record.invoice_id.currency_id.with_context(date=record.invoice_id._get_currency_rate_date()).compute(price_subtotal_signed, record.invoice_id.company_id.currency_id)
            sign = record.invoice_id.type in ['in_refund', 'out_refund'] and -1 or 1
            record.price_subtotal_signed = price_subtotal_signed * sign

            record.price_subtotal -= record.discount_total
            record.price_subtotal_signed -= record.discount_total



    name = fields.Text(string='Description', required=True)
    origin = fields.Char(string='Source Document',
        help="Reference of the document that produced this invoice.")
    sequence = fields.Integer(default=10,
        help="Gives the sequence of this line when displaying the invoice.")
    invoice_id = fields.Many2one('account.invoice', string='Invoice Reference',
        ondelete='cascade', index=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure',
        ondelete='set null', index=True, oldname='uos_id')
    product_id = fields.Many2one('product.product', string='Product',
        ondelete='restrict', index=True)
    account_id = fields.Many2one('account.account', string='Account',
        required=True, domain=[('deprecated', '=', False)],
        default=_default_account,
        help="The income or expense account related to the selected product.")
    price_unit = fields.Float(string='Unit Price', required=True, digits=dp.get_precision('Product Price'))
    price_subtotal = fields.Float(string='Amount',
        store=True, readonly=True, compute='_compute_price')
    price_subtotal_signed = fields.Float(string='Amount Signed', currency_field='company_currency_id',
        store=True, readonly=True, compute='_compute_price',
        help="Total amount in the currency of the company, negative for credit notes.")
    quantity = fields.Float(string='Quantity', digits=dp.get_precision('Product Unit of Measure'),
        required=True, default=1)
    discount = fields.Float(string='Discount (%)', digits=dp.get_precision('Discount'),
        default=0.0)
    invoice_line_tax_ids = fields.Many2many('account.tax',
        'account_invoice_line_tax', 'invoice_line_id', 'tax_id',
        string='Taxes', domain=[('type_tax_use','!=','none'), '|', ('active', '=', False), ('active', '=', True)], oldname='invoice_line_tax_id')
    account_analytic_id = fields.Many2one('account.analytic.account',
        string='Analytic Account')
    analytic_tag_ids = fields.Many2many('account.analytic.tag', string='Analytic Tags')
    company_id = fields.Many2one('res.company', string='Company',
        related='invoice_id.company_id', store=True, readonly=True, related_sudo=False)
    partner_id = fields.Many2one('res.partner', string='Partner',
        related='invoice_id.partner_id', store=True, readonly=True, related_sudo=False)
    currency_id = fields.Many2one('res.currency', related='invoice_id.currency_id', store=True, related_sudo=False)
    company_currency_id = fields.Many2one('res.currency', related='invoice_id.company_currency_id', readonly=True, related_sudo=False)


    purchase_line_id = fields.Many2one('purchase.order.line', 'Purchase Order Line', ondelete='set null', index=True, readonly=False)
    purchase_id = fields.Many2one('purchase.order', related='purchase_line_id.order_id', string='Purchase Order', store=False, readonly=True, related_sudo=False,
        help='Associated Purchase Order. Filled in automatically when a PO is chosen on the vendor bill.')


    sale_line_ids = fields.Many2many(
        'sale.order.line',
        'sale_order_line_invoice_rel_new',
        'invoice_line_id', 'order_line_id',
        string='Sale Order Lines', readonly=True, copy=False)
    layout_category_id = fields.Many2one('sale.layout_category', string='Section')
    layout_category_sequence = fields.Integer(string='Layout Sequence')
    # TODO: remove layout_category_sequence in master or make it work properly

    sync_id = sync.id
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    patient_id = fields.Many2one('res.partner',string="Patient",readonly=True)
    average_cost = fields.Float(string="Average Cost")
    purchase_backup_id = fields.Float(string="Purchase ID")
    purchase_backup_name = fields.Char(string="Purchase Name")
    analytic_budget_id = fields.Many2one('account.analytic.account',string='Analytic Budget',domain=[('parent_id', '!=', False),('type_analytic', '=','expense')],index=True)
    discount_persen = fields.Float(string="Discount Persen", digits=(16, 9))
    discount_value = fields.Float(string="Discount Value", digits=(16, 4))
    discount_total = fields.Float(string='Discount Total',readonly=True,store=True)
    account_analytic_id = fields.Many2one('account.analytic.account',string="Analytic Account",domain=[('type_analytic', '=','expense')],index=True)
    date_invoice = fields.Date(string="Date Invoice",related='invoice_id.date_invoice',store=True)
    account_id = fields.Many2one('account.account',string='Account',required=True,domain=['|', ('deprecated', '=', False), ('parent', '=', False)],help="The partner account used for this invoice.")

    # 2023.08.14 - Input account analytic account
    account_code = fields.Char(string="Account (Code)", related="account_id.code", readonly=True, store=False)


    # 2021.10.12 - asset dependecy from account_asset default
    asset_category_id = fields.Many2one('account.asset.category', string='Asset Category')
    asset_start_date = fields.Date(string='Asset Start Date', readonly=True, store=True)
    asset_end_date = fields.Date(string='Asset End Date', readonly=True, store=True)
    asset_mrr = fields.Float(string='Monthly Recurring Revenue', readonly=True, digits=dp.get_precision('Account'), store=True)
    # link ke picking untuk vendor bills based on GRN
    picking_id = fields.Many2one('stock.picking', string="Picking No.")
    stock_move_id = fields.Many2one('stock.move', string="Move No.")




    # @api.v8
    def get_invoice_line_account(self, type, product, fpos, company):
        accounts = product.product_tmpl_id.get_product_accounts(fpos)
        if type in ('out_invoice', 'out_refund'):
            return accounts['income']
        if company.anglo_saxon_accounting and type in ('in_invoice', 'in_refund') and product and product.type == 'product':
            accounts = product.product_tmpl_id.get_product_accounts(fiscal_pos=fpos)
            if accounts['stock_input']:
                return accounts['stock_input']
        return accounts['expense']

    def _set_currency(self):
        company = self.invoice_id.company_id
        currency = self.invoice_id.currency_id
        if company and currency:
            if company.currency_id != currency:
                self.price_unit = self.price_unit * currency.with_context(dict(self._context or {}, date=self.invoice_id.date_invoice)).rate

    def _set_taxes(self):
        """ Used in on_change to set taxes and price."""
        if self.invoice_id.type in ('out_invoice', 'out_refund'):
            taxes = self.product_id.taxes_id or self.account_id.tax_ids
        else:
            taxes = self.product_id.supplier_taxes_id or self.account_id.tax_ids

        # Keep only taxes of the company
        company_id = self.company_id or self.env.company
        taxes = taxes.filtered(lambda r: r.company_id == company_id)

        # self.invoice_line_tax_ids = fp_taxes = self.invoice_id.fiscal_position_id.map_tax(taxes, self.product_id, self.invoice_id.partner_id)
        self.invoice_line_tax_ids = fp_taxes = self.invoice_id.fiscal_position_id.map_tax(taxes)

        fix_price = self.env['account.tax']._fix_tax_included_price
        if self.invoice_id.type in ('in_invoice', 'in_refund'):
            prec = self.env['decimal.precision'].precision_get('Product Price')
            if not self.price_unit or float_compare(self.price_unit, self.product_id.standard_price, precision_digits=prec) == 0:
                self.price_unit = fix_price(self.product_id.standard_price, taxes, fp_taxes)
                self._set_currency()
        else:
            self.price_unit = fix_price(self.product_id.lst_price, taxes, fp_taxes)
            self._set_currency()

    @api.onchange('discount_persen', 'quantity','price_unit')  # if these fields are changed, call method
    def _discount_persen(self):
        for r in self:
            discount_val = (r.discount_persen / 100) * r.price_unit
            r.discount_value = discount_val
            r.discount_total = discount_val * r.quantity



    @api.onchange('discount_value', 'quantity','price_unit')  # if these fields are changed, call method
    def _discount_value(self):
        for r in self:
            r.discount_total = r.discount_value * r.quantity
            if r.discount_value and r.price_unit:
                r.discount_persen = (r.discount_value / r.price_unit) * 100


    # @api.model
    def create(self, vals):
        result = super(AccountInvoiceLine, self).create(vals)

        if result.invoice_id.type in ['in_invoice','in_refund']:
            raise exceptions.UserError("Tidak Bisa Create Invoice line")


        for record in result:

            if not record.account_analytic_id and record.company_id.cost_center_active and record.company_id.cost_center_date <= record.invoice_id.date_invoice:
                account_code = record.account_id.code
                if (account_code[:1] in ['4','5','6','7','8','9'] and account_code[:4] not in ['6901','6902','5100']):
                    raise exceptions.ValidationError("Account code {code} harus dimapping dengan Cost Center Analytic".format(code=record.account_id.code + " " + record.account_id.name))



            discount = record.discount_value * record.quantity
            # price_subtotal = vals.get('price_subtotal',record.price_subtotal) - discount
            # price_subtotal_signed = vals.get('price_subtotal_signed',record.price_subtotal_signed) - discount
            price_subtotal = record.price_subtotal - discount
            price_subtotal_signed = record.price_subtotal_signed - discount
            record.write({
                'price_subtotal': price_subtotal,
                'price_subtotal_signed': price_subtotal_signed,
                'discount_total': discount
            })
        return result


    # @api.multi
    def write(self, vals):
        result = super(AccountInvoiceLine, self).write(vals)
        if self.env.context.get('sudah_total'): return result
        self = self.with_context(sudah_total=True)


        if not self.account_analytic_id and self.company_id.cost_center_active and self.company_id.cost_center_date <= self.invoice_id.date_invoice:
            account_code = self.account_id.code
            if (account_code[:1] in ['4','5','6','7','8','9'] and account_code[:4] not in ['6901','6902','5100']):
                raise exceptions.ValidationError("Account code {code} harus dimapping dengan Cost Center Analytic".format(code=self.account_id.code + " " + self.account_id.name))

        
        for record in self:


            if record.invoice_id.type in ['in_invoice','in_refund']:
                raise exceptions.UserError("Tidak Bisa Edit Invoice Vendor")

            discount = record.discount_value * record.quantity
            # price_subtotal = vals.get('price_subtotal',record.price_subtotal) - discount
            # price_subtotal_signed = vals.get('price_subtotal_signed',record.price_subtotal_signed) - discount
            price_subtotal = record.price_subtotal - discount
            price_subtotal_signed = record.price_subtotal_signed - discount
            record.write({
                'price_subtotal': price_subtotal,
                'price_subtotal_signed': price_subtotal_signed,
                'discount_total': discount
            })
        return result




    @api.onchange('product_id')
    def _onchange_product_id(self):
        domain = {}
        if not self.invoice_id:
            return

        part = self.invoice_id.partner_id
        fpos = self.invoice_id.fiscal_position_id
        company = self.invoice_id.company_id
        currency = self.invoice_id.currency_id
        type = self.invoice_id.type

        if not part:
            warning = {
                    'title': _('Warning!'),
                    'message': _('You must first select a partner!'),
                }
            return {'warning': warning}

        if not self.product_id:
            if type not in ('in_invoice', 'in_refund'):
                self.price_unit = 0.0
            domain['uom_id'] = []
        else:
            if part.lang:
                product = self.product_id.with_context(lang=part.lang)
            else:
                product = self.product_id

            self.name = product.partner_ref
            account = self.get_invoice_line_account(type, product, fpos, company)
            if account:
                self.account_id = account.id
            self._set_taxes()

            if type in ('in_invoice', 'in_refund'):
                if product.description_purchase:
                    self.name += '\n' + product.description_purchase
            else:
                if product.description_sale:
                    self.name += '\n' + product.description_sale

            if not self.uom_id or product.uom_id.category_id.id != self.uom_id.category_id.id:
                self.uom_id = product.uom_id.id
            domain['uom_id'] = [('category_id', '=', product.uom_id.category_id.id)]

            if company and currency:

                if self.uom_id and self.uom_id.id != product.uom_id.id:
                    self.price_unit = product.uom_id._compute_price(self.price_unit, self.uom_id)

        if self.product_id:
            if self.invoice_id.type == 'out_invoice':
                self.asset_category_id = self.product_id.product_tmpl_id.deferred_revenue_category_id
            elif self.invoice_id.type == 'in_invoice':
                self.asset_category_id = self.product_id.product_tmpl_id.asset_category_id
        return {'domain': domain}


    @api.onchange('account_id')
    def _onchange_account_id(self):
        if not self.account_id:
            return
        if not self.product_id:
            fpos = self.invoice_id.fiscal_position_id
            self.invoice_line_tax_ids = fpos.map_tax(self.account_id.tax_ids).ids
        elif not self.price_unit:
            self._set_taxes()



    @api.onchange('uom_id')
    def _onchange_uom_id(self):
        warning = {}
        result = {}
        if not self.uom_id:
            self.price_unit = 0.0
        if self.product_id and self.uom_id:
            if self.product_id.uom_id.category_id.id != self.uom_id.category_id.id:
                warning = {
                    'title': _('Warning!'),
                    'message': _('The selected unit of measure is not compatible with the unit of measure of the product.'),
                }
                self.uom_id = self.product_id.uom_id.id
        if warning:
            result['warning'] = warning
        self.onchange_asset_category_id()
        return result



    def _set_additional_fields(self, invoice):
        """ Some modules, such as Purchase, provide a feature to add automatically pre-filled
            invoice lines. However, these modules might not be aware of extra fields which are
            added by extensions of the accounting module.
            This method is intended to be overridden by these extensions, so that any new field can
            easily be auto-filled as well.
            :param invoice : account.invoice corresponding record
            :rtype line : account.invoice.line record
        """


        if not self.asset_category_id:
            if invoice.type == 'out_invoice':
                self.asset_category_id = self.product_id.product_tmpl_id.deferred_revenue_category_id.id
            elif invoice.type == 'in_invoice':
                self.asset_category_id = self.product_id.product_tmpl_id.asset_category_id.id
            self.onchange_asset_category_id()
        pass

    # @api.one
    # @api.depends('price_unit', 'discount', 'invoice_line_tax_ids', 'quantity','product_id', 'invoice_id.partner_id','invoice_id.currency_id', 'invoice_id.company_id','invoice_id.date_invoice', 'invoice_id.date','discount_total')
    # def _compute_price(self):
    #     super(AccountInvoiceLine, self)._compute_price()
    #     self.price_subtotal -= self.discount_total
    #     self.price_subtotal_signed -= self.discount_total

    # @api.multi
    def unlink(self):
        if self.filtered(lambda r: r.invoice_id and r.invoice_id.state != 'draft'):
            raise UserError(_('You can only delete an invoice line if the invoice is in draft state.'))
        return super(AccountInvoiceLine, self).unlink()



    # @api.one
    @api.depends('asset_category_id', 'invoice_id.date_invoice')
    def _get_asset_date(self):
        self.asset_mrr = 0
        self.asset_start_date = False
        self.asset_end_date = False
        cat = self.asset_category_id
        if cat:
            months = cat.method_number * cat.method_period
            if self.invoice_id.type in ['out_invoice', 'out_refund']:
                self.asset_mrr = self.price_subtotal_signed / months
            if self.invoice_id.date_invoice:
                start_date = datetime.datetime.strptime(self.invoice_id.date_invoice, DF).replace(day=1)
                end_date = (start_date + relativedelta(months=months, days=-1))
                self.asset_start_date = start_date.strftime(DF)
                self.asset_end_date = end_date.strftime(DF)

    # @api.one
    def asset_create(self):
        # if self.asset_category_id:
        #     vals = {
        #         'name': self.name,
        #         'code': self.invoice_id.number or False,
        #         'category_id': self.asset_category_id.id,
        #         'value': self.price_subtotal_signed,
        #         'partner_id': self.invoice_id.partner_id.id,
        #         'company_id': self.invoice_id.company_id.id,
        #         'currency_id': self.invoice_id.company_currency_id.id,
        #         'date': self.invoice_id.date_invoice,
        #         'invoice_id': self.invoice_id.id,
        #     }
        #     changed_vals = self.env['account.asset.asset'].onchange_category_id_values(vals['category_id'])
        #     vals.update(changed_vals['value'])
        #     asset = self.env['account.asset.asset'].create(vals)
        #     if self.asset_category_id.open_asset:
        #         asset.validate()
        return True

    # 2021.10.05 - disable depens account_id on change asset_category_id
    @api.onchange('asset_category_id')
    def onchange_asset_category_id(self):
        print("Do something..")
        # if self.invoice_id.type == 'out_invoice' and self.asset_category_id:
        #     self.account_id = self.asset_category_id.account_asset_id.id
        #     self.account_analytic_id = self.asset_category_id.account_analytic_id.id 
        # elif self.invoice_id.type == 'in_invoice' and self.asset_category_id:
        #     self.account_id = self.asset_category_id.account_asset_id.id
        #     self.account_analytic_id = self.asset_category_id.account_analytic_id.id


    def _get_anglo_saxon_price_unit(self):
        # price_unit = super(AccountInvoiceLine, self)._get_anglo_saxon_price_unit()
        price_unit = 0
        # in case of anglo saxon with a product configured as invoiced based on delivery, with perpetual
        # valuation and real price costing method, we must find the real price for the cost of good sold
        if self.product_id.invoice_policy == "delivery":
            for s_line in self.sale_line_ids:
                # qtys already invoiced
                qty_done = sum([x.uom_id._compute_quantity(x.quantity, x.product_id.uom_id) for x in s_line.invoice_lines if x.invoice_id.state in ('open', 'paid')])
                quantity = self.uom_id._compute_quantity(self.quantity, self.product_id.uom_id)
                # Put moves in fixed order by date executed
                moves = s_line.mapped('procurement_ids.move_ids').sorted(lambda x: x.date)
                # Go through all the moves and do nothing until you get to qty_done
                # Beyond qty_done we need to calculate the average of the price_unit
                # on the moves we encounter.
                bom = s_line.product_id.product_tmpl_id.bom_ids and s_line.product_id.product_tmpl_id.bom_ids[0]
                if bom.type == 'phantom':
                    average_price_unit = 0
                    components = s_line._get_bom_component_qty(bom)
                    for product_id in components.keys():
                        factor = components[product_id]['qty']
                        prod_moves = [m for m in moves if m.product_id.id == product_id]
                        prod_qty_done = factor * qty_done
                        prod_quantity = factor * quantity
                        average_price_unit += factor * self._compute_average_price(prod_qty_done, prod_quantity, prod_moves)
                    price_unit = average_price_unit or price_unit
                    price_unit = self.product_id.uom_id._compute_price(price_unit, self.uom_id)

        if self.product_id.invoice_policy == "delivery":
            for s_line in self.sale_line_ids:
                # qtys already invoiced
                qty_done = sum([x.uom_id._compute_quantity(x.quantity, x.product_id.uom_id) for x in s_line.invoice_lines if x.invoice_id.state in ('open', 'paid')])
                quantity = self.uom_id._compute_quantity(self.quantity, self.product_id.uom_id)
                # Put moves in fixed order by date executed
                moves = s_line.mapped('procurement_ids.move_ids').sorted(lambda x: x.date)
                # Go through all the moves and do nothing until you get to qty_done
                # Beyond qty_done we need to calculate the average of the price_unit
                # on the moves we encounter.
                average_price_unit = self._compute_average_price(qty_done, quantity, moves)
                price_unit = average_price_unit or price_unit
                price_unit = self.product_id.uom_id._compute_price(price_unit, self.uom_id)
        self.ensure_one()
        if not self.product_id:
            return self.price_unit

        return price_unit

    def _compute_average_price(self, qty_done, quantity, moves):
        average_price_unit = 0
        qty_delivered = 0
        invoiced_qty = 0
        for move in moves:
            if move.state != 'done':
                continue
            invoiced_qty += move.product_qty
            if invoiced_qty <= qty_done:
                continue
            qty_to_consider = move.product_qty
            if invoiced_qty - move.product_qty < qty_done:
                qty_to_consider = invoiced_qty - qty_done
            qty_to_consider = min(qty_to_consider, quantity - qty_delivered)
            qty_delivered += qty_to_consider
            if qty_delivered:
                average_price_unit = (average_price_unit * (qty_delivered - qty_to_consider) + move.price_unit * qty_to_consider) / qty_delivered
            if qty_delivered == quantity:
                break
        return average_price_unit

    def _get_price(self, company_currency, price_unit):
        if self.invoice_id.currency_id.id != company_currency.id:
            price = company_currency.with_context(date=self.invoice_id.date_invoice).compute(price_unit * self.quantity, self.invoice_id.currency_id)
        else:
            price = price_unit * self.quantity
        return round(price, self.invoice_id.currency_id.decimal_places)





# 2021.09.25 
class AccountInvoice(models.Model):
    # _inherit = 'account.invoice'
    _name = 'account.invoice'
    _inherit = ['mail.thread']
    _description = "Invoice"
    _order = "date_invoice desc, number desc, id desc"
    _rec_name = 'number'



    @api.model
    def _default_currency(self):
        journal = self._default_journal()
        return journal.currency_id or journal.company_id.currency_id or self.env.company.currency_id

    @api.model
    def _default_journal(self):
        if self._context.get('default_journal_id', False):
            return self.env['account.journal'].browse(self._context.get('default_journal_id'))
        if self._context.get('default_type') == 'out_invoice':
            inv_type = 'sale'
        if self._context.get('default_type') == 'in_invoice':
            inv_type = 'purchase'
        if self.type == False:
            inv_type = 'purchase'
        company_id = self._context.get('company_id', self.env.company.id)                
        domain = [
            ('type', '=', inv_type),
            ('company_id', '=', company_id),
        ]
        return self.env['account.journal'].search(domain, limit=1)

    def compute_dp(self):
        dp_amount = 0
        for line in self.purchase_dp_invoice_ids:
            dp_amount += line.amount_total

        return dp_amount

    # @api.one
    @api.depends('invoice_line_ids.price_subtotal', 'purchase_dp_invoice_ids', 'tax_line_ids.amount', 'currency_id', 'company_id', 'date_invoice', 'type')
    def _compute_amount(self):
        for rec in self:
            round_curr = rec.currency_id.round
            rec.amount_untaxed = sum(line.price_subtotal for line in rec.invoice_line_ids)
            rec.amount_tax = sum(round_curr(line.amount) for line in rec.tax_line_ids)
            rec.amount_total = rec.amount_untaxed + rec.amount_tax - rec.compute_dp()
            amount_total_company_signed = rec.amount_total
            amount_untaxed_signed = rec.amount_untaxed
            if rec.currency_id and rec.company_id and rec.currency_id != rec.company_id.currency_id:
                currency_id = rec.currency_id.with_context(date=rec.date_invoice)
                amount_total_company_signed = currency_id.compute(rec.amount_total, rec.company_id.currency_id)
                amount_untaxed_signed = currency_id.compute(rec.amount_untaxed, rec.company_id.currency_id)
            sign = rec.type in ['in_refund', 'out_refund'] and -1 or 1
            rec.amount_total_company_signed = amount_total_company_signed * sign
            rec.amount_total_signed = rec.amount_total * sign
            rec.amount_untaxed_signed = amount_untaxed_signed * sign



    @api.model
    def _get_reference_type(self):
        return [('none', _('Free Reference'))]


    # 2021.09.27 - ambil residual dari account.move.line
    # @api.one
    @api.depends(
        'state', 'currency_id', 'invoice_line_ids.price_subtotal',
        'move_id.line_ids.amount_residual',
        'payment_settle_ids.state',
        'move_id.line_ids.currency_id')
    def _compute_residual(self):
        for rec in self:
            residual = 0.0
            residual_signed = 0.0
            residual_company_signed = 0.0
            received_payment = 0
            sign = rec.type in ['in_refund', 'out_refund'] and -1 or 1

            invoice_line_ids = rec.sudo().env['account.move.line'].search([('account_id','=', rec.account_id.id),('invoice_id','=', rec.id),('company_id','=', rec.company_id.id),('move_id.state','=','posted')])
            for line in invoice_line_ids:
                open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + "masuk sini check check 1 : " + str(line.id))
            
                # if line.account_id.account_type in ('receivable', 'payable'):
                if line.account_id.account_type in ('asset_receivable', 'liability_payable'):
                    # residual_company_signed += line.balance
                    # residual_signed += line.balance
                    # residual += line.balance

                    # # hitung receipt payment atau payment voucher atas invoice
                    # if line.balance > 0 and line.account_id.account_type == 'liability_payable':
                    #     received_payment += abs(line.balance)
                    # elif line.balance < 0 and line.account_id.account_type == 'asset_receivable':
                    #     received_payment += abs(line.balance)

                    if line.account_id.account_type == 'liability_payable':
                        if line.balance and line.debit > 0:
                            residual_company_signed += -abs(line.balance)
                            residual_signed += -abs(line.balance)
                            open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + "RESIDUAL  debit > 0 SINI COBA CEK BALANCE: " + str(line.balance))
            
                            residual += -abs(line.balance)
                        elif line.balance and line.credit > 0:
                            residual_company_signed += abs(line.balance)
                            residual_signed += abs(line.balance)
                            open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + "RESIDUAL  CREDIT > 0 SINI COBA CEK BALANCE: " + str(line.balance))
            
                            residual += abs(line.balance)
                    elif line.account_id.account_type == 'asset_receivable':
                        residual_company_signed += line.balance
                        residual_signed += line.balance
                        residual += line.balance
                        
                    # hitung receipt payment atau payment voucher atas invoice
                    if line.balance > 0 and line.account_id.account_type == 'liability_payable':
                        if line.balance and line.debit > 0:
                            received_payment += -abs(line.balance)
                        elif line.balance and line.credit > 0:
                            received_payment += abs(line.balance)
                    elif line.balance < 0 and line.account_id.account_type == 'asset_receivable':
                        received_payment += abs(line.balance)

            # self.residual_company_signed = abs(residual_company_signed) 
            # self.residual_signed = abs(residual) 
            # self.residual = abs(residual)
            # self.settlement_amount = abs(received_payment)
            open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + "Residual Sini Check : " + str(residual))
            #raise exceptions.ValidationError("Residual Sini Check : " + str(residual))
            rec.residual_company_signed = residual_company_signed
            rec.residual_signed = residual
            rec.residual = residual
            rec.settlement_amount = received_payment
            digits_rounding_precision = self.currency_id.rounding
            if float_is_zero(rec.residual, precision_rounding=digits_rounding_precision) and rec.amount_total > 0 and rec.settlement_amount > 0:
                self.reconciled = True
            else:
                self.reconciled = False





    # @api.multi
    def _compute_payment_ids(self):
        for r in self:
            payment = r.env['account.payment'].search([('bill_ids', '=', r.id),('state','not in',['cancel'])]).ids
            r.payment_settle_ids = payment



    @api.depends('invoice_line_ids.discount_total')
    def _compute_discount(self):
        for record in self:
            record.total_discount, record.total_tampilan = 0, 0
            for line in record.invoice_line_ids:
                record.total_discount += line.discount_total
                record.total_tampilan += line.discount_total + line.price_subtotal



    @api.depends('invoice_line_ids.price_subtotal')
    def _compute_taxes(self):
        for invoice in self:
            amount_pph = amount_ppn = 0.0
            for line in invoice.invoice_line_ids:
                for tax in line.invoice_line_tax_ids:
                    taxes = tax._compute_amount(round(line.price_unit * line.quantity - (line.discount_value * line.quantity)),
                        line.price_unit,
                        line.quantity,
                        product=line.product_id,
                        partner=invoice.partner_id)
                    if 'PPH' in (tax.name).upper():
                        amount_pph += taxes
                    elif 'PPN' in (tax.name).upper():
                        amount_ppn += taxes
            invoice.update({
                'pph': amount_pph,
                'ppn': amount_ppn,
            })


    @api.depends('payment_ids')
    def _compute_payments_name(self):
        for invoice in self:
            list_payment = []
            seperator = ', '
            for payment in invoice.payment_settle_ids:
                list_payment.append(payment.name)
            payments_name = seperator.join(list_payment)
            invoice.payments_name = payments_name



    # @api.one
    def _get_outstanding_info_JSON(self):
        self.outstanding_credits_debits_widget = json.dumps(False)
        if self.state == 'open':
            domain = [('account_id', '=', self.account_id.id),
                      ('partner_id', '=', self.env['res.partner']._find_accounting_partner(self.partner_id).id),
                      ('reconciled', '=', False),
                      '|',
                        '&', ('amount_residual_currency', '!=', 0.0), ('currency_id','!=', None),
                        '&', ('amount_residual_currency', '=', 0.0), '&', ('currency_id','=', None), ('amount_residual', '!=', 0.0)]
            if self.type in ('out_invoice', 'in_refund'):
                domain.extend([('credit', '>', 0), ('debit', '=', 0)])
                type_payment = _('Outstanding credits')
            else:
                domain.extend([('credit', '=', 0), ('debit', '>', 0)])
                type_payment = _('Outstanding debits')
            info = {'title': '', 'outstanding': True, 'content': [], 'invoice_id': self.id}
            lines = self.env['account.move.line'].search(domain)
            currency_id = self.currency_id
            if len(lines) != 0:
                for line in lines:
                    # get the outstanding residual value in invoice currency
                    if line.currency_id and line.currency_id == self.currency_id:
                        amount_to_show = abs(line.amount_residual_currency)
                    else:
                        amount_to_show = line.company_id.currency_id.with_context(date=line.date).compute(abs(line.amount_residual), self.currency_id)
                    if float_is_zero(amount_to_show, precision_rounding=self.currency_id.rounding):
                        continue
                    info['content'].append({
                        'journal_name': line.ref or line.move_id.name,
                        'amount': amount_to_show,
                        'currency': currency_id.symbol,
                        'id': line.id,
                        'position': currency_id.position,
                        'digits': [69, self.currency_id.decimal_places],
                    })
                info['title'] = type_payment
                self.outstanding_credits_debits_widget = json.dumps(info)
                self.has_outstanding = True



    # @api.one
    @api.depends('payment_move_line_ids.amount_residual')
    def _get_payment_info_JSON(self):
        self.payments_widget = json.dumps(False)
        if self.payment_move_line_ids:
            info = {'title': _('Less Payment'), 'outstanding': False, 'content': []}
            currency_id = self.currency_id
            for payment in self.payment_move_line_ids:
                payment_currency_id = False
                if self.type in ('out_invoice', 'in_refund'):
                    amount = sum([p.amount for p in payment.matched_debit_ids if p.debit_move_id in self.move_id.line_ids])
                    amount_currency = sum([p.amount_currency for p in payment.matched_debit_ids if p.debit_move_id in self.move_id.line_ids])
                    if payment.matched_debit_ids:
                        payment_currency_id = all([p.currency_id == payment.matched_debit_ids[0].currency_id for p in payment.matched_debit_ids]) and payment.matched_debit_ids[0].currency_id or False
                elif self.type in ('in_invoice', 'out_refund'):
                    amount = sum([p.amount for p in payment.matched_credit_ids if p.credit_move_id in self.move_id.line_ids])
                    amount_currency = sum([p.amount_currency for p in payment.matched_credit_ids if p.credit_move_id in self.move_id.line_ids])
                    if payment.matched_credit_ids:
                        payment_currency_id = all([p.currency_id == payment.matched_credit_ids[0].currency_id for p in payment.matched_credit_ids]) and payment.matched_credit_ids[0].currency_id or False
                # get the payment value in invoice currency
                if payment_currency_id and payment_currency_id == self.currency_id:
                    amount_to_show = amount_currency
                else:
                    amount_to_show = payment.company_id.currency_id.with_context(date=payment.date).compute(amount, self.currency_id)
                if float_is_zero(amount_to_show, precision_rounding=self.currency_id.rounding):
                    continue
                payment_ref = payment.move_id.name
                if payment.move_id.ref:
                    payment_ref += ' (' + payment.move_id.ref + ')'
                info['content'].append({
                    'name': payment.name,
                    'journal_name': payment.journal_id.name,
                    'amount': amount_to_show,
                    'currency': currency_id.symbol,
                    'digits': [69, currency_id.decimal_places],
                    'position': currency_id.position,
                    'date': payment.date,
                    'payment_id': payment.id,
                    'move_id': payment.move_id.id,
                    'ref': payment_ref,
                })
            self.payments_widget = json.dumps(info)


    # @api.one
    @api.depends('move_id.line_ids.amount_residual','payment_settle_ids.state')
    def _compute_payments(self):
        payment_lines = []
        for line in self.move_id.line_ids.filtered(lambda l: l.account_id.id == self.account_id.id):
            payment_lines.extend(filter(None, [rp.credit_move_id.id for rp in line.matched_credit_ids]))
            payment_lines.extend(filter(None, [rp.debit_move_id.id for rp in line.matched_debit_ids]))
        self.payment_move_line_ids = self.env['account.move.line'].browse(list(set(payment_lines)))
        self.payment_move_line_ids = self.env['account.move.line'].search([('company_id','=', self.company_id.id),('account_id','=', self.account_id.id),('invoice_id','=',self.id), ('payment_id','in', self.payment_settle_ids.ids), ('move_id.state','=','posted')])


    name = fields.Char(string='Reference/Description', index=True,
        readonly=True, states={'draft': [('readonly', False)]}, copy=False, help='The name that will be used on account move lines')
    origin = fields.Char(string='Source Document',
        help="Reference of the document that produced this invoice.",
        readonly=True, states={'draft': [('readonly', False)]})
    type = fields.Selection([
            ('out_invoice','Customer Invoice'),
            ('in_invoice','Vendor Bill'),
            ('out_refund','Customer Refund'),
            ('in_refund','Vendor Refund'),
        ], readonly=True, index=True, change_default=True,
        tracking=True)

    refund_invoice_id = fields.Many2one('account.invoice', string="Invoice for which this invoice is the refund")
    number = fields.Char(related='move_id.name', store=True, readonly=True, copy=False)
    move_name = fields.Char(string='Journal Entry Name', readonly=False,
        default=False, copy=False,
        help="Technical field holding the number given to the invoice, automatically set when the invoice is validated then stored to set the same number again if the invoice is cancelled, set to draft and re-validated.")
    reference = fields.Char(string='Vendor Reference', copy=False,
        help="The partner reference of this invoice.", readonly=True, states={'draft': [('readonly', False)]})
    reference_type = fields.Selection('_get_reference_type', string='Payment Reference',
        required=True, readonly=True, states={'draft': [('readonly', False)]},
        default='none')
    comment = fields.Text('Additional Information', readonly=True, states={'draft': [('readonly', False)]})

    state = fields.Selection([
            ('draft','Draft'),
            ('proforma', 'Pro-forma'),
            ('proforma2', 'Pro-forma'),
            ('open', 'Open'),
            ('paid', 'Paid'),
            ('cancel', 'Cancelled'),
        ], string='Status', default='draft', store=True, copy=False)
    sent = fields.Boolean(readonly=True, default=False, copy=False,
        help="It indicates that the invoice has been sent.")
    date_invoice = fields.Date(string='Invoice Date',
        readonly=True, states={'draft': [('readonly', False)]}, index=True,
        help="Keep empty to use the current date", copy=False)
    date_due = fields.Date(string='Due Date',
        readonly=True, states={'draft': [('readonly', False)]}, index=True, copy=False,
        help="If you use payment terms, the due date will be computed automatically at the generation "
             "of accounting entries. The payment term may compute several due dates, for example 50% "
             "now and 50% in one month, but if you want to force a due date, make sure that the payment "
             "term is not set on the invoice. If you keep the payment term and the due date empty, it "
             "means direct payment.")
    partner_id = fields.Many2one('res.partner', string='Partner', change_default=True,
        required=True, readonly=True, states={'draft': [('readonly', False)]},
        tracking=True)
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Terms', oldname='payment_term',
        readonly=True, states={'draft': [('readonly', False)]},
        help="If you use payment terms, the due date will be computed automatically at the generation "
             "of accounting entries. If you keep the payment term and the due date empty, it means direct payment. "
             "The payment term may compute several due dates, for example 50% now, 50% in one month.")
    date = fields.Date(string='Accounting Date',
        copy=False,
        help="Keep empty to use the invoice date.",
        readonly=True, states={'draft': [('readonly', False)]})

    account_id = fields.Many2one('account.account', string='Account',
        required=True, readonly=True, states={'draft': [('readonly', False)]},
        domain=[('deprecated', '=', False)], help="The partner account used for this invoice.")
    invoice_line_ids = fields.One2many('account.invoice.line', 'invoice_id', string='Invoice Lines', oldname='invoice_line',
        readonly=True, states={'draft': [('readonly', False)]}, copy=True)
    tax_line_ids = fields.One2many('account.invoice.tax', 'invoice_id', string='Tax Lines', oldname='tax_line',
        readonly=True, states={'draft': [('readonly', False)]}, copy=True)
    move_id = fields.Many2one('account.move', string='Journal Entry',
        readonly=True, index=True, ondelete='set null', copy=False,
        help="Link to the automatically generated Journal Items.")

    amount_untaxed = fields.Float(string='Untaxed Amount', store=True, compute='_compute_amount')
    amount_untaxed_signed = fields.Float(string='Untaxed Amount in Company Currency', store=True, compute='_compute_amount')
    amount_tax = fields.Float(string='Tax', store=True, compute='_compute_amount')
    amount_total = fields.Float(string='Total', store=True, compute='_compute_amount')
    amount_total_signed = fields.Float(string='Total in Invoice Currency', store=True, compute='_compute_amount')
    amount_total_company_signed = fields.Float(string='Total in Company Currency', currency_field='company_currency_id', store=True, compute='_compute_amount')
    currency_id = fields.Many2one('res.currency', string='Currency',
        required=True, readonly=True, states={'draft': [('readonly', False)]},
        default=_default_currency, tracking=True)
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string="Company Currency", readonly=True)
    journal_id = fields.Many2one('account.journal', string='Journal',
        required=True, readonly=True, states={'draft': [('readonly', False)]},
        default=_default_journal,
        )
    company_id = fields.Many2one('res.company', string='Company', change_default=True,
        required=True, readonly=True, states={'draft': [('readonly', False)]},
        default=lambda self: self.env['res.company']._company_default_get('account.invoice'))

    reconciled = fields.Boolean(string='Paid/Reconciled', store=True, readonly=True,
        help="It indicates that the invoice has been paid and the journal entry of the invoice has been reconciled with one or several journal entries of payment.")
    partner_bank_id = fields.Many2one('res.partner.bank', string='Bank Account',
        help='Bank Account Number to which the invoice will be paid. A Company bank account if this is a Customer Invoice or Vendor Refund, otherwise a Partner bank account number.',
        readonly=True, states={'draft': [('readonly', False)]})

    residual = fields.Monetary(string='Amount Due',
        compute='_compute_residual', store=True, help="Remaining amount due.")
    residual_signed = fields.Monetary(string='Amount Due in Invoice Currency', currency_field='currency_id',
        compute='_compute_residual', store=True, help="Remaining amount due in the currency of the invoice.")
    residual_company_signed = fields.Monetary(string='Amount Due in Company Currency', currency_field='company_currency_id',
        compute='_compute_residual', store=True, help="Remaining amount due in the currency of the company.")
    payment_ids = fields.Many2many('account.payment', 'account_invoice_payment_rel', 'invoice_id', 'payment_id', string="Payments", copy=False, readonly=True)
    payment_move_line_ids = fields.Many2many('account.move.line', string='Payment Move Lines', store=True)
    user_id = fields.Many2one('res.users', string='Salesperson', tracking=True,
        readonly=True, states={'draft': [('readonly', False)]},
        default=lambda self: self.env.user)
    fiscal_position_id = fields.Many2one('account.fiscal.position', string='Fiscal Position', oldname='fiscal_position',
        readonly=True, states={'draft': [('readonly', False)]})
    commercial_partner_id = fields.Many2one('res.partner', string='Commercial Entity', 
        related='partner_id.commercial_partner_id', store=True, readonly=True,
        help="The commercial entity that will be used on Journal Entries for this invoice")

    outstanding_credits_debits_widget = fields.Text(string='Widget')
    payments_widget = fields.Text(string='Payment Widget')
    has_outstanding = fields.Boolean(string='Has Outstanding')

    purchase_id = fields.Many2one('purchase.order', string='Add Purchase Order',
        help='Encoding help. When selected, the associated purchase order lines are added to the vendor bill. Several PO can be selected.')

    team_id = fields.Many2one('crm.team', string='Sales Team', oldname='section_id')
    comment = fields.Text(string='Comment')
    partner_shipping_id = fields.Many2one(
        'res.partner',
        string='Delivery Address',
        readonly=True,
        states={'draft': [('readonly', False)]},
        help="Delivery address for current invoice.")

    incoterms_id = fields.Many2one('stock.incoterms', string="Incoterms",
        help="Incoterms are series of sales terms. They are used to divide transaction costs and responsibilities between buyer and seller and reflect state-of-the-art transportation practices.",
        readonly=True, states={'draft': [('readonly', False)]})

    sync_id = sync.id
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    #budget = fields.Boolean(string="Is Budget", readonly=True, compute='_budget', store=False)
    locked = fields.Boolean(string="Locked", default=False)
    #covering_id = fields.Many2one('account.coveringletter', string="Covering Letter")
    no_faktur = fields.Char(string="Nomor Faktur")
    lot_number = fields.Char(string="Lot Number")
    expired_date = fields.Datetime(string="Expired Date")
    faktur_date = fields.Datetime(string="Tukar Faktur Date")
    vendor_bill_wipro = fields.Boolean(string="Vendor Bill from Wipro")
    no_bill = fields.Char(string="No. Bill")
    bank_id = fields.Many2one('bank.information', string="Bank Information")
    remarks = fields.Char(string="Cancel Remarks")
    total_discount = fields.Float(string="Total Discount",store=True, compute='_compute_discount')
    total_tampilan = fields.Float(string="Untaxed Amount",store=True, compute='_compute_discount')
    ppn = fields.Float(string="PPN",store=True,readonly=True, compute='_compute_taxes')
    pph = fields.Float(string="PPh",store=True,readonly=True, compute='_compute_taxes')
    payments_name = fields.Char(string="List of Payments",store=True,readonly=True)
    payment_settle_ids = fields.Many2many('account.payment',string='Payment',readonly=True,store=True)
    asset_ids = fields.One2many('account.asset.asset', 'invoice_id', string='Assets', readonly=True)
    move_line_ids = fields.One2many('account.move.line','invoice_id', string="Move Items", readonly=True)
    due_day = fields.Integer(string="HIS Due Day", required=False)

    settlement_amount = fields.Float('Settlement Amount', readonly=True, store=True)
    status = fields.Selection([
            ('draft','Draft'),
            ('proforma', 'Pro-forma'),
            ('proforma2', 'Pro-forma'),
            ('open', 'Open'),
            ('process', 'In Payment Process'),
            ('partial', 'Partially Paid'),
            ('paid', 'Paid'),
            ('cancel', 'Cancelled'),
        ], string='Status', index=True, store=False, readonly=True, default='draft', compute="_get_status",
        tracking=True, copy=False)

    ####################Update
    source_type = fields.Selection([
            ('po','Purchase Order'),
            ('rn', 'Receiving Notes'),
        ], string='Source Type', index=True, store=False, default='po')
    picking_id = fields.Many2one('stock.picking', string='Add Receiving Notes')
    is_picking_validate = fields.Boolean(string="Is Picking Validate?")
    purchase_ids = fields.Many2many('purchase.order', string="Purchase Rels")
    purchase_dp_id = fields.Many2one('purchase.order', string="DP of PO No.")
    purchase_po_id = fields.Many2one('purchase.order', string="PO No.")
    purchase_dp_invoice_ids = fields.Many2many('account.invoice', 'account_invoice_down_payment_rel', 'invoice_id', 'down_payment_id', 'Reverse Down Payment')
    

    def _get_status(self):
        for rec in self:
            if rec.state:
                rec.status = rec.state


    @api.model
    def create(self, vals):
        record = super(AccountInvoice, self).create(vals)

        if record.type in ['in_invoice','in_refund']:
            raise exceptions.UserError("Tidak Bisa Create Invoice")

        return record


    # @api.multi
    def write(self, vals):
        for rec in self:
            if rec.type in ['in_invoice','in_refund']:
                raise exceptions.UserError("Tidak Bisa Edit Invoice Vendor")


        result = super(AccountInvoice, self).write(vals)



        return result



    # @api.model
    # def create(self, vals):
    #     onchanges = {
    #         '_onchange_partner_id': ['account_id', 'payment_term_id', 'fiscal_position_id', 'partner_bank_id'],
    #         '_onchange_journal_id': ['currency_id'],
    #     }
    #     for onchange_method, changed_fields in onchanges.items():
    #         if any(f not in vals for f in changed_fields):
    #             invoice = self.new(vals)
    #             getattr(invoice, onchange_method)()
    #             for field in changed_fields:
    #                 if field not in vals and invoice[field]:
    #                     vals[field] = invoice._fields[field].convert_to_write(invoice[field], invoice)
    #     if not vals.get('account_id',False):
    #         raise UserError(_('Configuration error!\nCould not find any account to create the invoice, are you sure you have a chart of account installed?'))

    #     invoice = super(AccountInvoice, self.with_context(mail_create_nolog=True)).create(vals)

    #     if any(line.invoice_line_tax_ids for line in invoice.invoice_line_ids) and not invoice.tax_line_ids:
    #         invoice.compute_taxes()

    #     purchase = invoice.invoice_line_ids.mapped('purchase_line_id.order_id')
    #     if purchase and not invoice.refund_invoice_id:
    #         message = _("This vendor bill has been created from: %s") % (",".join(["<a href=# data-oe-model=purchase.order data-oe-id="+str(order.id)+">"+order.name+"</a>" for order in purchase]))
    #         invoice.message_post(body=message)
    #     return invoice

    # @api.multi
    # def _write(self, vals):
    #     pre_not_reconciled = self.filtered(lambda invoice: not invoice.reconciled)
    #     pre_reconciled = self - pre_not_reconciled
    #     res = super(AccountInvoice, self)._write(vals)
    #     reconciled = self.filtered(lambda invoice: invoice.reconciled)
    #     not_reconciled = self - reconciled
    #     (reconciled & pre_reconciled).filtered(lambda invoice: invoice.state == 'open').action_invoice_paid()
    #     (not_reconciled & pre_not_reconciled).filtered(lambda invoice: invoice.state == 'paid').action_invoice_re_open()
    #     return res


    # @api.multi
    # def write(self, vals):
    #     result = True
    #     for invoice in self:
    #         purchase_old = invoice.invoice_line_ids.mapped('purchase_line_id.order_id')
    #         result = result and super(AccountInvoice, invoice).write(vals)
    #         purchase_new = invoice.invoice_line_ids.mapped('purchase_line_id.order_id')
    #         #To get all po reference when updating invoice line or adding purchase order reference from vendor bill.
    #         purchase = (purchase_old | purchase_new) - (purchase_old & purchase_new)
    #         if purchase:
    #             message = _("This vendor bill has been modified from: %s") % (",".join(["<a href=# data-oe-model=purchase.order data-oe-id="+str(order.id)+">"+order.name+"</a>" for order in purchase]))
    #             invoice.message_post(body=message)

    #     if vals.get('state') == 'cancel' and (self.locked == True or vals.get('locked') == True):
    #         raise exceptions.ValidationError("Invoice is locked")
    #     return result


    # @api.multi
    def lock_invoice(self):
        self.write({'locked': True})

    # @api.multi
    def unlock_invoice(self):
        self.write({'locked': False})



    # @api.onchange('partner_shipping_id')
    # def _onchange_partner_shipping_id(self):
    #     """
    #     Trigger the change of fiscal position when the shipping address is modified.
    #     """
    #     fiscal_position = self.env['account.fiscal.position'].get_fiscal_position(self.partner_id.id, self.partner_shipping_id.id)
    #     if fiscal_position:
    #         self.fiscal_position_id = fiscal_position


    # @api.onchange('partner_id', 'company_id')
    # def _onchange_delivery_address(self):
    #     addr = self.partner_id.address_get(['delivery'])
    #     self.partner_shipping_id = addr and addr.get('delivery')
    #     if self.env.context.get('type', 'out_invoice') == 'out_invoice':
    #         company = self.company_id or self.env.company
    #         self.comment = company.with_context(lang=self.partner_id.lang).sale_note


    # @api.multi
    def invoice_print(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/account/print_out_tenant?id=' + str(self.id)
        action['target'] = 'new'
        return action



    # @api.multi
    def action_invoice_sent(self):
        """ Open a window to compose an email, with the edi invoice template
            message loaded by default
        """
        self.ensure_one()
        template = self.env.ref('account.email_template_edi_invoice', False)
        compose_form = self.env.ref('mail.email_compose_message_wizard_form', False)
        ctx = dict(
            default_model='account.invoice',
            default_res_id=self.id,
            default_use_template=bool(template),
            default_template_id=template and template.id or False,
            default_composition_mode='comment',
            mark_invoice_as_sent=True,
            custom_layout="account.mail_template_data_notification_email_account_invoice"
        )
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'new',
            'context': ctx,
        }


    # @api.multi
    def compute_taxes(self):
        """Function used in other module to compute the taxes on a fresh invoice created (onchanges did not applied)"""
        account_invoice_tax = self.env['account.invoice.tax']
        ctx = dict(self._context)
        for invoice in self:
            # Delete non-manual tax lines
            self._cr.execute("DELETE FROM account_invoice_tax WHERE invoice_id=%s AND manual is False", (invoice.id,))
            if self._cr.rowcount:
                self.invalidate_cache()

            # Generate one tax line per tax, however many invoice lines it's applied to
            tax_grouped = invoice.get_taxes_values()

            # Create new tax lines
            for tax in tax_grouped.values():
                account_invoice_tax.create(tax)

        # dummy write on self to trigger recomputations
        return self.with_context(ctx).write({'invoice_line_ids': []})



    # @api.multi
    def unlink(self):
        for invoice in self:
            if invoice.state not in ('draft', 'cancel'):
                raise UserError(_('You cannot delete an invoice which is not draft or cancelled. You should refund it instead.'))
            elif invoice.move_name:
                raise UserError(_('You cannot delete an invoice after it has been validated (and received a number). You can set it back to "Draft" state and modify its content, then re-confirm it.'))
        return super(AccountInvoice, self).unlink()


    @api.onchange('invoice_line_ids')
    def _onchange_invoice_line_ids(self):
        taxes_grouped = self.get_taxes_values()
        tax_lines = self.tax_line_ids.filtered('manual')
        for tax in taxes_grouped.values():
            tax_lines += tax_lines.new(tax)
        self.tax_line_ids = tax_lines
        return


    # 2021.10.06 - depends on change partner_id 
    @api.onchange('partner_id', 'company_id')
    def _onchange_partner_id(self):
        account_id = False
        payment_term_id = False
        fiscal_position = False
        bank_id = False
        due_day = 0
        warning = {}
        domain = {}
        company_id = self.company_id.id
        p = self.partner_id if not company_id else self.partner_id.with_context(force_company=company_id)
        type = self.type
        if p:
            rec_account = p.property_account_receivable_id
            pay_account = p.property_account_payable_id
            if not rec_account and not pay_account:
                action = self.env.ref('account.action_account_config')
                msg = _('Cannot find a chart of accounts for this company, You should configure it. \nPlease go to Account Configuration.')
                # raise RedirectWarning(msg, action.id, _('Go to the configuration panel'))
                raise exceptions.ValidationError(str(msg) + ' ' + str(action.id) + ' Go to the configuration panel')

            if type in ('in_invoice', 'in_refund'):
                account_id = pay_account.id
                payment_term_id = p.property_supplier_payment_term_id.id
                due_day = p.credit_days
            else:
                account_id = rec_account.id
                payment_term_id = p.property_payment_term_id.id
                due_day = p.credit_days

            # delivery_partner_id = self.get_delivery_partner_id()
            # fiscal_position = self.env['account.fiscal.position'].get_fiscal_position(self.partner_id.id, delivery_id=delivery_partner_id)

            # If partner has no warning, check its company
            if p.invoice_warn == 'no-message' and p.parent_id:
                p = p.parent_id
            if p.invoice_warn != 'no-message':
                # Block if partner only has warning but parent company is blocked
                if p.invoice_warn != 'block' and p.parent_id and p.parent_id.invoice_warn == 'block':
                    p = p.parent_id
                warning = {
                    'title': _("Warning for %s") % p.name,
                    'message': p.invoice_warn_msg
                    }
                if p.invoice_warn == 'block':
                    self.partner_id = False

        self.account_id = account_id
        self.payment_term_id = payment_term_id
        self.due_day = due_day
        self.date_due = False
        # self.fiscal_position_id = fiscal_position

        if type in ('in_invoice', 'out_refund'):
            bank_ids = p.commercial_partner_id.bank_ids
            bank_id = bank_ids[0].id if bank_ids else False
            self.partner_bank_id = bank_id
            domain = {'partner_bank_id': [('id', 'in', bank_ids.ids)]}

        res = {}
        if warning:
            res['warning'] = warning
        if domain:
            res['domain'] = domain
        return res

    # @api.multi
    def get_delivery_partner_id(self):
        self.ensure_one()
        return self.partner_id.address_get(['delivery'])['delivery']

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        if self.journal_id:
            self.currency_id = self.journal_id.currency_id.id or self.journal_id.company_id.currency_id.id



    # @api.multi
    def button_journal_entries(self):
        return {
            'name': _('Journal Items'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('invoice_id', 'in', self.ids)],
        }


    # 2021.09.28 - Jika ada pembayaran masuk update state menjadi partially paid
    # @api.one
    def _status(self):
        if self.state == 'open':
            if self.residual > 0 and self.settlement_amount > 0:
                self.status = 'partial'
            elif self.payment_settle_ids:
                self.status = 'process' 
            else: 
                self.status = 'open' 
            # self.status = 'open' 
        else:
            self.status = self.state



    # 2021.10.06 - onchange payment terms 
    @api.onchange('payment_term_id', 'date_invoice', 'due_day')
    def _onchange_payment_term_date_invoice(self):


        date_invoice = self.date_invoice
        if not date_invoice:
            date_invoice = fields.Date.context_today(self)

        if self.due_day:
            self.date_due = date_invoice + timedelta(days=int(self.due_day))                

        elif self.payment_term_id:
            pterm = self.payment_term_id
            pterm_list = pterm.with_context(currency_id=self.company_id.currency_id.id).compute(value=1, date_ref=date_invoice)[0]
            self.date_due = max(line[0] for line in [pterm_list])
        else:
            self.date_due = self.date_due or date_invoice


    # @api.multi
    def action_invoice_draft(self):
        if self.filtered(lambda inv: inv.state != 'cancel'):
            raise UserError(_("Invoice must be cancelled in order to reset it to draft."))
        # go from canceled state to draft state
        self.write({'state': 'draft', 'date': False})
        # # Delete former printed invoice
        # try:
        #     report_invoice = self.env['report']._get_report_from_name('account.report_invoice')
        # except IndexError:
        #     report_invoice = False
        # if report_invoice and report_invoice.attachment:
        #     for invoice in self:
        #         with invoice.env.do_in_draft():
        #             invoice.number, invoice.state = invoice.move_name, 'open'
        #             attachment = self.env['report']._attachment_stored(invoice, report_invoice)[invoice.id]
        #         if attachment:
        #             attachment.unlink()
        # return True



    # @api.multi
    def action_invoice_proforma2(self):
        if self.filtered(lambda inv: inv.state != 'draft'):
            raise UserError(_("Invoice must be a draft in order to set it to Pro-forma."))
        return self.write({'state': 'proforma2'})

    # 2021.09.27 - modify action_invoice_open
    # @api.multi
    def action_invoice_open(self):

        for inv in self:
            if inv.type in ['in_invoice','in_refund']:
                raise exceptions.UserError("Tidak Bisa Validate Invoice")

        for line in self.invoice_line_ids:
            purchase = self.env['purchase.order'].search([('id', '=', line.purchase_id.id)])
            for p in purchase:
                p.write({'bill_date': self.date_invoice})
                line.write({'date_invoice': self.date_invoice})

        # lots of duplicate calls to action_invoice_open, so we remove those already open
        to_open_invoices = self.filtered(lambda inv: inv.state != 'open')
        if to_open_invoices.filtered(lambda inv: inv.state not in ['proforma2', 'draft']):
            raise UserError(_("Invoice must be in draft or Pro-forma state in order to validate it."))
        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("DUDI 1"))
        to_open_invoices.action_date_assign()
        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("DUDI 2"))
        to_open_invoices.action_move_create()
        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("DUDI 3"))
        to_open_invoices.invoice_validate()

        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("DUDI 4"))
        cost_center = self.invoice_line_ids.mapped('account_analytic_id.id')
        for cc in cost_center:
            cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
            if self.company_id.cost_center_active == True:
                if not self.company_id.cost_center_date or not self.date_invoice:
                    raise UserError(_("Tanggal tidak boleh kosong."))
            if self.company_id.cost_center_active == True and self.company_id.cost_center_date <= self.date_invoice:
                budget_used = self.env['crossovered.budget.lines'].sudo().search([
                    ('analytic_account_id', '=', cc),
                    ('crossovered_budget_id.state','in', ['validate','done']),
                    ('date_from', '<=',self.date_invoice),
                    ('date_to', '>=',self.date_invoice)])
                if budget_used:
                    budget_used.budget_line_compute_balance()


    # @api.multi
    def action_invoice_paid(self):
        # lots of duplicate calls to action_invoice_paid, so we remove those already paid
        to_pay_invoices = self.filtered(lambda inv: inv.state != 'paid')
        if to_pay_invoices.filtered(lambda inv: inv.state != 'open'):
            raise UserError(_('Invoice must be validated in order to set it to register payment.'))
        if to_pay_invoices.filtered(lambda inv: not inv.reconciled):
            raise UserError(_('You cannot pay an invoice which is partially paid. You need to reconcile payment entries first.'))


        todo = set()
        for invoice in self:
            for line in invoice.invoice_line_ids:
                for sale_line in line.sale_line_ids:
                    todo.add((sale_line.order_id, invoice.number))
        for (order, name) in todo:
            order.message_post(body=_("Invoice %s paid") % (name))

        for rec in self:
            cost_center = rec.invoice_line_ids.mapped('account_analytic_id.id')
            for cc in cost_center:
                cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
                if rec.company_id.cost_center_active == True:
                    if not rec.company_id.cost_center_date or not rec.date_invoice:
                        raise UserError(_("Tanggal tidak boleh kosong."))
                if rec.company_id.cost_center_active == True and rec.company_id.cost_center_date <= rec.date_invoice:
                    budget_used = self.env['crossovered.budget.lines'].sudo().search([
                        ('analytic_account_id', '=', cc),
                        ('crossovered_budget_id.state','in', ['validate','done']),
                        ('date_from', '<=',rec.date_invoice),
                        ('date_to', '>=',rec.date_invoice)])
                    if budget_used:
                        budget_used.budget_line_compute_balance()


        return to_pay_invoices.write({'state': 'paid'})

    # @api.multi
    def action_invoice_re_open(self):
        if self.filtered(lambda inv: inv.state != 'paid'):
            raise UserError(_('Invoice must be paid in order to set it to register payment.'))
        return self.write({'state': 'open'})


    # @api.multi
    def action_invoice_cancel(self):
        if self.filtered(lambda inv: inv.state not in ['proforma2', 'draft', 'open']):
            raise UserError(_("Invoice must be in draft, Pro-forma or open state in order to be cancelled."))
        self._compute_residual()
        if not self.remarks:
            raise exceptions.ValidationError(("Fill remarks before cancel"))
        return self.action_cancel()

    # @api.multi
    def get_formview_id(self):
        """ Update form view id of action to open the invoice """
        if self.type in ('in_invoice', 'in_refund'):
            return self.env.ref('account.invoice_supplier_form').id
        else:
            return self.env.ref('account.invoice_form').id


    def _prepare_tax_line_vals(self, line, tax):
        """ Prepare values to create an account.invoice.tax line

        The line parameter is an account.invoice.line, and the
        tax parameter is the output of account.tax.compute_all().
        """
        vals = {
            'invoice_id': self.id,
            'name': tax['name'],
            'tax_id': tax['id'],
            'amount': tax['amount'],
            'base': tax['base'],
            'manual': False,
            'sequence': tax['sequence'],
            'account_analytic_id': tax['analytic'] and line.account_analytic_id.id or False,
            'account_id': False,
            # 'account_id': self.type in ('out_invoice', 'in_invoice') and (tax['account_id'] or line.account_id.id) or (tax['refund_account_id'] or line.account_id.id),
        }

        # If the taxes generate moves on the same financial account as the invoice line,
        # propagate the analytic account from the invoice line to the tax line.
        # This is necessary in situations were (part of) the taxes cannot be reclaimed,
        # to ensure the tax move is allocated to the proper analytic account.
        if not vals.get('account_analytic_id') and line.account_analytic_id and vals['account_id'] == line.account_id.id:
            vals['account_analytic_id'] = line.account_analytic_id.id
            vals['amount'] -= (line.discount_persen / 100) * vals['amount']
        # res['amount'] -= (line.discount_persen / 100) * res['amount']

        return vals


    @api.depends('invoice_line_ids')
    def _compute_purchase_ids(self):
        for order in self:
            order.purchase_ids = order.invoice_line_ids.mapped('purchase_id')


    ###############Update
    @api.onchange('picking_id')
    def picking_id_change(self):
        if not self.picking_id:
            result = {}
            result['domain'] = {'picking_id': [('state', '=', 'done')]}

            return result
        if not self.partner_id:
            self.partner_id = self.picking_id.partner_id.id
            self.origin = (self.picking_id.po_id.name + ' / ' if self.picking_id.po_id else '') + self.picking_id.name

        new_lines = self.env['account.invoice.line']
        for line in self.picking_id.move_lines:
            data = self._prepare_invoice_line_from_stock_move(line)
            new_line = new_lines.new(data)
            new_line._set_additional_fields(self)
            new_lines += new_line
        
        self.invoice_line_ids += new_lines
        self.picking_id = False
        return {}


    #################update
    def _prepare_invoice_line_from_stock_move(self, line):
        if line.picking_id.is_return is True:
            qty = line.product_uom_qty  * -1
        elif line.product_id.purchase_method == 'purchase':
            # qty yg di invoice bill dari GRN adalah maksimal senilai Qty GRN
            qty = (line.product_uom_qty - line.purchase_line_id.qty_invoiced) if (line.product_uom_qty - line.purchase_line_id.qty_invoiced) > 0.0 else 0.0
        else:
            qty = line.purchase_line_id.qty_received_srb - line.purchase_line_id.qty_invoiced
        # if float_compare(qty, 0.0, precision_rounding=line.product_uom.rounding) <= 0:
        #     qty = 0.0

        # taxes = line.taxes_id
        # invoice_line_tax_ids = line.order_id.fiscal_position_id.map_tax(taxes)
        invoice_line = self.env['account.invoice.line']
        data = {
            'purchase_line_id': line.purchase_line_id.id,
            'picking_id': line.picking_id.id,
            'stock_move_id': line.id, 
            'name': line.picking_id.name+': '+line.name,
            'origin': line.picking_id.origin,
            'uom_id': line.product_uom.id,
            'product_id': line.product_id.id,
            'account_id': line.product_input_id.id, #default input account sesuai GRN
            'price_unit': line.price_unit,
            'quantity': qty,
            'discount_persen': line.discount_persen,
            'discount_value': line.discount_value,
            'discount_total': (line.discount_total or (line.discount_value * qty)),
            'account_analytic_id': line.account_analytic_id.id,
            # 'analytic_tag_ids': line.analytic_tag_ids.ids,
            'invoice_line_tax_ids': [(6, 0, line.taxes_id.ids)],
            'price_tax': line.price_tax,
            'price_subtotal': line.sub_total
        }

        
        account = invoice_line.get_invoice_line_account('in_invoice', line.product_id, line.purchase_line_id.order_id.fiscal_position_id, self.env.company)
        if account:
            data['account_id'] = account.id
        return data



    # @api.multi
    def get_taxes_values(self):
        tax_grouped = {}
        round_curr = self.currency_id.round
        for line in self.invoice_line_ids:
            # Avoid DP
            if line.product_id.name != 'Down Payment':
                price_unit = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                if line.quantity != 0:
                    price_subtotal = line.price_subtotal / line.quantity
                else: 
                    price_subtotal = line.price_subtotal
                # taxes = line.invoice_line_tax_ids.compute_all(price_unit, self.currency_id, line.quantity, line.product_id, self.partner_id)['taxes']
                taxes = line.invoice_line_tax_ids.compute_all(price_subtotal, self.currency_id, line.quantity, line.product_id, self.partner_id)['taxes']
                for tax in taxes:
                    val = self._prepare_tax_line_vals(line, tax)
                    key = self.env['account.tax'].browse(tax['id']).get_grouping_key(val)

                    if key not in tax_grouped:
                        tax_grouped[key] = val
                        tax_grouped[key]['base'] = round_curr(val['base'])
                    else:
                        tax_grouped[key]['amount'] += val['amount']
                        tax_grouped[key]['base'] += round_curr(val['base'])

                    # modify
                    tax_grouped[key]['account_id'] = tax['account_id']

        return tax_grouped


    # @api.multi
    def register_payment(self, payment_line, writeoff_acc_id=False, writeoff_journal_id=False):
        """ Reconcile payable/receivable lines from the invoice with payment_line """
        line_to_reconcile = self.env['account.move.line']
        # for inv in self:
        #     line_to_reconcile += inv.move_id.line_ids.filtered(lambda r: not r.reconciled and r.account_id.internal_type in ('payable', 'receivable'))
        # # return (line_to_reconcile + payment_line).reconcile(writeoff_acc_id, writeoff_journal_id)
        # return (line_to_reconcile + payment_line).reconcile()
        return True 




    # @api.multi
    def assign_outstanding_credit(self, credit_aml_id):
        self.ensure_one()
        credit_aml = self.env['account.move.line'].browse(credit_aml_id)
        if not credit_aml.currency_id and self.currency_id != self.company_id.currency_id:
            credit_aml.with_context(allow_amount_currency=True, check_move_validity=False).write({
                'amount_currency': self.company_id.currency_id.with_context(date=credit_aml.date).compute(credit_aml.balance, self.currency_id),
                'currency_id': self.currency_id.id})
        if credit_aml.payment_id:
            credit_aml.payment_id.write({'invoice_ids': [(4, self.id, None)]})
        return self.register_payment(credit_aml)

    # @api.multi
    def action_date_assign(self):
        for inv in self:
            # Here the onchange will automatically write to the database
            inv._onchange_payment_term_date_invoice()
        return True


    # @api.multi
    def finalize_invoice_move_lines(self, move_lines):
        """ finalize_invoice_move_lines(move_lines) -> move_lines

            Hook method to be overridden in additional modules to verify and
            possibly alter the move lines to be created by an invoice, for
            special cases.
            :param move_lines: list of dictionaries with the account.move.lines (as for create())
            :return: the (possibly updated) final move_lines to create for this invoice
        """
        return move_lines

    # @api.multi
    def compute_invoice_totals(self, company_currency, invoice_move_lines):
        total = 0
        total_currency = 0
        for line in invoice_move_lines:
            if self.currency_id != company_currency:
                currency = self.currency_id.with_context(date=self._get_currency_rate_date() or fields.Date.context_today(self))
                if not (line.get('currency_id') and line.get('amount_currency')):
                    line['currency_id'] = currency.id
                    line['amount_currency'] = currency.round(line['price'])
                    line['price'] = currency.compute(line['price'], company_currency)
            else:
                line['currency_id'] = False
                line['amount_currency'] = False
                line['price'] = self.currency_id.round(line['price'])
            if self.type in ('out_invoice', 'in_refund'):
                total += line['price']
                total_currency += line['amount_currency'] or line['price']
                line['price'] = - line['price']
            else:
                total -= line['price']
                total_currency -= line['amount_currency'] or line['price']
        return total, total_currency, invoice_move_lines


    @api.model
    def invoice_line_move_line_get(self):
        res = []
        for line in self.invoice_line_ids:
            if line.quantity==0:
                continue
            tax_ids = []
            for tax in line.invoice_line_tax_ids:
                tax_ids.append((4, tax.id, None))
                for child in tax.children_tax_ids:
                    if child.type_tax_use != 'none':
                        tax_ids.append((4, child.id, None))
            # analytic_tag_ids = [(4, analytic_tag.id, None) for analytic_tag in line.analytic_tag_ids]

            move_line_dict = {
                'invl_id': line.id,
                'type': 'src',
                'name': line.name.split('\n')[0][:64],
                'price_unit': line.price_unit,
                'quantity': line.quantity,
                'price': line.price_subtotal,
                'account_id': line.account_id.id,
                'product_id': line.product_id.id,
                'uom_id': line.uom_id.id,
                'account_analytic_id': line.account_analytic_id.id,
                'tax_ids': tax_ids,
                'invoice_id': self.id,
                'purchase_id': line.purchase_id.id
                # 'stock_product_id': line.product_id.id,
                # 'stock_categ_id': line.product_id.categ_id.id,
                # 'analytic_tag_ids': analytic_tag_ids
            }
            res.append(move_line_dict)

        if self.env.company.anglo_saxon_accounting:
            if self.type in ['in_invoice', 'in_refund']:
                for i_line in self.invoice_line_ids:
                    res.extend(self._anglo_saxon_purchase_move_lines(i_line, res))

        if self.company_id.anglo_saxon_accounting and self.type in ('out_invoice', 'out_refund'):
            for i_line in self.invoice_line_ids:
                res.extend(self._anglo_saxon_sale_move_lines(i_line))

        return res


    @api.model
    def _anglo_saxon_sale_move_lines(self, i_line):
        """Return the additional move lines for sales invoices and refunds.

        i_line: An account.invoice.line object.
        res: The move line entries produced so far by the parent move_line_get.
        """
        inv = i_line.invoice_id
        company_currency = inv.company_id.currency_id
        price_unit = i_line._get_anglo_saxon_price_unit()
        if inv.currency_id != company_currency:
            currency = inv.currency_id
            amount_currency = i_line._get_price(company_currency, price_unit)
        else:
            currency = False
            amount_currency = False

        return self.env['product.product']._anglo_saxon_sale_move_lines(i_line.name, i_line.product_id, i_line.uom_id, i_line.quantity, price_unit, currency=currency, amount_currency=amount_currency, fiscal_position=inv.fiscal_position_id, account_analytic=i_line.account_analytic_id, analytic_tags=i_line.analytic_tag_ids)




    @api.model
    def _anglo_saxon_purchase_move_lines(self, i_line, res):
        """Return the additional move lines for purchase invoices and refunds.

        i_line: An account.invoice.line object.
        res: The move line entries produced so far by the parent move_line_get.
        """
        inv = i_line.invoice_id
        company_currency = inv.company_id.currency_id
        if i_line.product_id and i_line.product_id.valuation == 'real_time' and i_line.product_id.type == 'product':
            # get the fiscal position
            fpos = i_line.invoice_id.fiscal_position_id
            # get the price difference account at the product
            acc = i_line.product_id.property_account_creditor_price_difference
            if not acc:
                # if not found on the product get the price difference account at the category
                acc = i_line.product_id.categ_id.property_account_creditor_price_difference_categ
            acc = fpos.map_account(acc).id
            # reference_account_id is the stock input account
            reference_account_id = i_line.product_id.product_tmpl_id.get_product_accounts(fiscal_pos=fpos)['stock_input'].id
            diff_res = []
            account_prec = inv.company_id.currency_id.decimal_places
            # calculate and write down the possible price difference between invoice price and product price
            for line in res:
                if line.get('invl_id', 0) == i_line.id and reference_account_id == line['account_id']:
                    valuation_price_unit = i_line.product_id.uom_id._compute_price(i_line.product_id.standard_price, i_line.uom_id)
                    if i_line.product_id.cost_method != 'standard' and i_line.purchase_line_id:
                        #for average/fifo/lifo costing method, fetch real cost price from incomming moves
                        valuation_price_unit = i_line.purchase_line_id.product_uom._compute_price(i_line.purchase_line_id.price_unit, i_line.uom_id)
                        # stock_move_obj = self.env['stock.move']
                        # valuation_stock_move = stock_move_obj.search([('purchase_line_id', '=', i_line.purchase_line_id.id), ('state', '=', 'done')])
                        # if valuation_stock_move:
                        #     valuation_price_unit_total = 0
                        #     valuation_total_qty = 0
                        #     for val_stock_move in valuation_stock_move:
                        #         valuation_price_unit_total += val_stock_move.price_unit * val_stock_move.product_qty
                        #         valuation_total_qty += val_stock_move.product_qty
                        #     valuation_price_unit = valuation_price_unit_total / valuation_total_qty
                        #     valuation_price_unit = i_line.product_id.uom_id._compute_price(valuation_price_unit, i_line.uom_id)
                    if inv.currency_id.id != company_currency.id:
                        valuation_price_unit = company_currency.with_context(date=inv.date_invoice).compute(valuation_price_unit,inv.currency_id,round=False)
                    # if valuation_price_unit != i_line.price_unit and line['price_unit'] == i_line.price_unit and acc:
                    # price with discount and without tax included
                    # price_unit = i_line.price_unit * (1 - (i_line.discount or 0.0) / 100.0)
                    # tax_ids = []
                    # if line['tax_ids']:
                    #line['tax_ids'] is like [(4, tax_id, None), (4, tax_id2, None)...]
                    # taxes = self.env['account.tax'].browse([x[1] for x in line['tax_ids']])
                    # price_unit = taxes.compute_all(price_unit, currency=inv.currency_id, quantity=1.0)['total_excluded']
                    # for tax in taxes:
                    # tax_ids.append((4, tax.id, None))
                    # for child in tax.children_tax_ids:
                    # if child.type_tax_use != 'none':
                    # tax_ids.append((4, child.id, None))
                    # price_before = line.get('price', 0.0)
                    # line.update({'price': round(valuation_price_unit * line['quantity'], account_prec)})
                    # diff_res.append({
                    #     'type': 'src',
                    #     'name': i_line.name[:64],
                    #     'price_unit': round(price_unit - valuation_price_unit, account_prec),
                    #     'quantity': line['quantity'],
                    #     'price': round(price_before - line.get('price', 0.0), account_prec),
                    #     'account_id': acc,
                    #     'product_id': line['product_id'],
                    #     'uom_id': line['uom_id'],
                    #     'account_analytic_id': line['account_analytic_id'],
                    #     'tax_ids': tax_ids,
                    #     })
            return diff_res
        return []


    # @api.multi
    def send_api_consol_company_invoice(self, payment_id=False):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            
            consol_active = record.company_id.sync_consol_account_payment
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/account.payment.line"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/account.payment.line"
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

                
                values['number'] = record.number
                values['bill_date'] = record.date_invoice
                values['due_date'] = record.date_due
                values['vendor_reference'] = record.reference
                values['source_document'] = record.origin
                values['vendor_name'] = record.partner_id.name
                values['nomor_seri_faktur_pajak'] = record.no_faktur
                values['total'] = record.amount_total_signed
                values['to_pay'] = record.residual_signed
                values['status'] = record.state
                values['trigger_create'] = True
                
                
                if payment_id == False:
                    values['account_payment_id'] = False
                else:
                    values['account_payment_id'] = str(payment_id)
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
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "BODY INVOICE DI SINI" +str(body))
                
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
                    
                }
                super(AccountInvoice, self).write(data_update)





    @api.model
    def tax_line_move_line_get(self):
        res = []
        # keep track of taxes already processed
        done_taxes = []
        # loop the invoice.tax.line in reversal sequence
        for tax_line in sorted(self.tax_line_ids, key=lambda x: -x.sequence):
            if tax_line.amount:
                tax = tax_line.tax_id
                if tax.amount_type == "group":
                    for child_tax in tax.children_tax_ids:
                        done_taxes.append(child_tax.id)
                res.append({
                    'invoice_tax_line_id': tax_line.id,
                    'tax_line_id': tax_line.tax_id.id,
                    'type': 'tax',
                    'name': tax_line.name,
                    'price_unit': tax_line.amount,
                    'quantity': 1,
                    'price': tax_line.amount,
                    'account_id': tax_line.account_id.id,
                    #'account_analytic_id': tax_line.account_analytic_id.id,
                    'invoice_id': self.id,
                    'tax_ids': [(6, 0, list(done_taxes))] if tax_line.tax_id.include_base_amount else []
                })
                done_taxes.append(tax.id)
        return res

    def inv_line_characteristic_hashcode(self, invoice_line):
        """Overridable hashcode generation for invoice lines. Lines having the same hashcode
        will be grouped together if the journal has the 'group line' option. Of course a module
        can add fields to invoice lines that would need to be tested too before merging lines
        or not."""
        return "%s-%s-%s-%s-%s-%s-%s" % (
            invoice_line['account_id'],
            invoice_line.get('tax_ids', 'False'),
            invoice_line.get('tax_line_id', 'False'),
            invoice_line.get('product_id', 'False'),
            invoice_line.get('analytic_account_id', 'False'),
            invoice_line.get('date_maturity', 'False'),
            invoice_line.get('analytic_tag_ids', 'False'),
        )


    def group_lines(self, iml, line):
        """Merge account move lines (and hence analytic lines) if invoice line hashcodes are equals"""
        if self.journal_id.group_invoice_lines:
            line2 = {}
            for x, y, l in line:
                tmp = self.inv_line_characteristic_hashcode(l)
                if tmp in line2:
                    am = line2[tmp]['debit'] - line2[tmp]['credit'] + (l['debit'] - l['credit'])
                    line2[tmp]['debit'] = (am > 0) and am or 0.0
                    line2[tmp]['credit'] = (am < 0) and -am or 0.0
                    line2[tmp]['amount_currency'] += l['amount_currency']
                    line2[tmp]['analytic_line_ids'] += l['analytic_line_ids']
                    qty = l.get('quantity')
                    if qty:
                        line2[tmp]['quantity'] = line2[tmp].get('quantity', 0.0) + qty
                else:
                    line2[tmp] = l
            line = []
            for key, val in line2.items():
                line.append((0, 0, val))
        return line


     # 2021.09.27 - modify action_move_create
    # @api.multi
    def action_move_create(self):
        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("action_move_create 1"))
        """ Creates invoice related analytics and financial move lines """
        account_move = self.env['account.move']

        for inv in self:
            if not inv.journal_id.sequence_id:
                raise UserError(_('Please define sequence on the journal related to this invoice.'))
            if not inv.invoice_line_ids:
                raise UserError(_('Please create some invoice lines.'))
            if inv.move_id:
                continue

            ctx = dict(self._context, lang=inv.partner_id.lang)

            if not inv.date_invoice:
                inv.with_context(ctx).write({'date_invoice': fields.Date.context_today(self)})
            company_currency = inv.company_id.currency_id

            # create move lines (one per invoice line + eventual taxes and analytic lines)
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("action_move_create 2"))
            iml = inv.invoice_line_move_line_get()
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("action_move_create 3"))
            iml += inv.tax_line_move_line_get()
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("action_move_create 4"))

            # 2022.11.25 tambahkan reverse DP invoice
            iml += inv.invoice_line_move_line_get_dp()
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("action_move_create 5"))
            iml += inv.tax_line_move_line_get_dp()
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("action_move_create 6"))

            diff_currency = inv.currency_id != company_currency
            # create one move line for the total and possibly adjust the other lines amount
            total, total_currency, iml = inv.with_context(ctx).compute_invoice_totals(company_currency, iml)

            name = inv.name or '/'
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(inv.payment_term_id))
            if inv.payment_term_id:
            #     totlines = inv.with_context(ctx).payment_term_id.with_context(currency_id=company_currency.id).compute(total, inv.date_invoice)[0]
            #     res_amount_currency = total_currency
            #     ctx['date'] = inv._get_currency_rate_date()
            #     for i, t in enumerate(totlines):
            #         if inv.currency_id != company_currency:
            #             amount_currency = company_currency.with_context(ctx).compute(t[1], inv.currency_id)
            #         else:
            #             amount_currency = False

            #         # last line: add the diff
            #         res_amount_currency -= amount_currency or 0
            #         if i + 1 == len(totlines):
            #             amount_currency += res_amount_currency

            #         iml.append({
            #             'type': 'dest',
            #             'name': name,
            #             'price': t[1],
            #             'account_id': inv.account_id.id,
            #             'date_maturity': inv.date_due,
            #             # 'date_maturity': t[0],
            #             'amount_currency': diff_currency and amount_currency,
            #             'currency_id': diff_currency and inv.currency_id.id,
            #             'invoice_id': inv.id
            #         })
            # else:
                open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(inv.account_id.id))
                iml.append({
                    'type': 'dest',
                    'name': name,
                    'price': total,
                    'account_id': inv.account_id.id,
                    'amount_currency': diff_currency and total_currency,
                    'currency_id': diff_currency and inv.currency_id.id,
                    # 'currency_id': inv.currency_id.id if diff_currency else company_currency.id,
                    'invoice_id': inv.id
                })
            part = self.env['res.partner']._find_accounting_partner(inv.partner_id)
            # line = [(0, 0, self.line_get_convert(l, part.id)) for l in iml]
            # line = inv.group_lines(iml, line)

            line_ids = []
            # raise exceptions.ValidationError(_(str(iml)))
            # Generate account.move.line
            if iml:
                for l in iml:
                    line = {}
                    line['date_maturity'] = (inv.date_due).strftime('%Y-%m-%d') or False
                    line['partner_id'] = part.id
                    line['name'] = l['name']
                    line['debit'] = l['price'] > 0 and l['price']
                    line['credit'] = l['price'] < 0 and -l['price']
                    line['account_id'] = l['account_id']
                    # line['analytic_line_ids'] = l['analytic_line_ids']
                    line['amount_currency'] = l['price'] > 0 and abs(l['amount_currency'] or False) or -abs(l['amount_currency'] or False)
                    line['currency_id'] = l['currency_id'] or False
                    # line['quantity'] = l['quantity']
                    # line['product_id'] = l['product_id'] or False
                    # line['product_uom_id'] = l['uom_id'] or False
                    # line['analytic_account_id'] = l['account_analytic_id'] or False
                    line['invoice_id'] = l['invoice_id'] or False
                    # line['payment_id'] = l['payment_id'] or False
                    # line['purchase_id'] = l['purchase_id'] or False
                    # line['sales_id'] = l['sales_id'] or False
                    # line['stock_picking_id'] = l['stock_picking_id'] or False
                    # line['stock_move_id'] = l['stock_move_id'] or False
                    # line['stock_product_id'] = l['stock_product_id'] or False
                    # line['stock_categ_id'] = l['stock_categ_id'] or False
                    # line['tax_ids'] = l['tax_ids'] or False
                    # line['tax_line_id'] = l['tax_line_id'] or False
                    # line['analytic_tag_ids'] = l['analytic_tag_ids'] or False

                    line_ids.append([0, 0, line])
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(inv))
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(line_ids))
            journal = inv.journal_id.with_context(ctx)
            # line = inv.finalize_invoice_move_lines(line)

            date = inv.date or inv.date_invoice
            move_vals = {
                'ref': inv.name,
                'name': inv.name,
                'line_ids': line_ids,
                'journal_id': journal.id,
                'partner_id': inv.partner_id.id,
                'invoice_id': inv.id,
                'date': date,
                'narration': inv.comment,
            }
            ctx['company_id'] = inv.company_id.id
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("TTT"))
            ctx['invoice'] = inv
            ctx_nolang = ctx.copy()
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("BBB"))
            ctx_nolang.pop('lang', None)
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("CCC"))
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(move_vals))
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(ctx_nolang))
            # raise UserError(_(str(move_vals)))
            move = account_move.with_context(ctx_nolang).create(move_vals)
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("OOO"))
            # Pass invoice in context in method post: used if you want to get the same
            # account move reference when creating the same invoice after a cancelled one:
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("AAA"))
            if move:
                move.action_post()
                # make the invoice point to that move
                vals = {
                    'move_id': move.id,
                    'date': date,
                    'move_name': move.name,
                }

                # compute residual/update to_pay
                self._compute_residual()

            inv.with_context(ctx).write(vals)

            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("XXX"))
            # 2021.10.01 - return asset auto create 
            context = dict(self.env.context)
            # Within the context of an invoice,
            # this default value is for the type of the invoice, not the type of the asset.
            # This has to be cleaned from the context before creating the asset,
            # otherwise it tries to create the asset with the type of the invoice.
            context.pop('default_type', None)
            open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("zzz"))
            inv.invoice_line_ids.with_context(context).asset_create()
        
        return True


    # 2022.11.25 - invoice_line_move_line_get
    @api.model
    def invoice_line_move_line_get_dp(self):
        res = []
        for line in self.purchase_dp_invoice_ids.invoice_line_ids:
            if line.quantity==0:
                continue
            tax_ids = []
            for tax in line.invoice_line_tax_ids:
                tax_ids.append((4, tax.id, None))
                for child in tax.children_tax_ids:
                    if child.type_tax_use != 'none':
                        tax_ids.append((4, child.id, None))
            analytic_tag_ids = [(4, analytic_tag.id, None) for analytic_tag in line.analytic_tag_ids]

            move_line_dict = {
                'invl_id': line.id,
                'type': 'src',
                'name': line.name.split('\n')[0][:64],
                'price_unit': line.price_unit,
                'quantity': ((line.quantity * -1) if line.quantity not in[0] else 0) ,
                'price': (line.price_subtotal * -1),
                'account_id': line.account_id.id,
                'product_id': line.product_id.id,
                'uom_id': line.uom_id.id,
                #'account_analytic_id': line.account_analytic_id.id,
                'tax_ids': tax_ids,
                'invoice_id': self.id,
                'purchase_id': line.purchase_id.id,
                # 'stock_product_id': line.product_id.id,
                # 'stock_categ_id': line.product_id.categ_id.id,
                'analytic_tag_ids': analytic_tag_ids
            }
            res.append(move_line_dict)
        return res


    # 2021.09.27 - tax_line_move_line_get
    @api.model
    def tax_line_move_line_get_dp(self):
        res = []
        # keep track of taxes already processed
        done_taxes = []
        # loop the invoice.tax.line in reversal sequence
        for tax_line in sorted(self.purchase_dp_invoice_ids.tax_line_ids, key=lambda x: -x.sequence):
            if tax_line.amount:
                tax = tax_line.tax_id
                if tax.amount_type == "group":
                    for child_tax in tax.children_tax_ids:
                        done_taxes.append(child_tax.id)
                res.append({
                    'invoice_tax_line_id': tax_line.id,
                    'tax_line_id': tax_line.tax_id.id,
                    'type': 'tax',
                    'name': tax_line.name,
                    'price_unit': tax_line.amount,
                    'quantity': -1,
                    'price': (tax_line.amount * -1),
                    'account_id': tax_line.account_id.id,
                    #'account_analytic_id': tax_line.account_analytic_id.id,
                    'invoice_id': self.id,
                    'tax_ids': [(6, 0, list(done_taxes))] if tax_line.tax_id.include_base_amount else []
                })
                done_taxes.append(tax.id)
        return res




    def _check_invoice_reference(self):
        for invoice in self:
            #refuse to validate a vendor bill/refund if there already exists one with the same reference for the same partner,
            #because it's probably a double encoding of the same bill/refund
            if invoice.type in ('in_invoice', 'in_refund') and invoice.reference:
                if self.search([('type', '=', invoice.type), ('reference', '=', invoice.reference), ('company_id', '=', invoice.company_id.id), ('commercial_partner_id', '=', invoice.commercial_partner_id.id), ('id', '!=', invoice.id)]):
                    raise UserError(_("Duplicated vendor reference detected. You probably encoded twice the same vendor bill/refund."))

    # @api.multi
    def invoice_validate(self):
        self._check_invoice_reference()

        for invoice in self:
            if invoice.partner_id not in invoice.message_partner_ids:
                invoice.message_subscribe([invoice.partner_id.id])
        self.purchase_dp_invoice_ids.write({'is_picking_validate': True})
        return self.write({'state': 'open'})

    # @api.multi
    def get_signup_url(self):
        self.ensure_one()
        return self.partner_id.with_context(signup_valid=True)._get_signup_url_for_action(
            action='/mail/view',
            model=self._name,
            res_id=self.id)[self.partner_id.id]

    @api.onchange('state', 'partner_id', 'invoice_line_ids')
    def _onchange_allowed_purchase_ids(self):
        '''
        The purpose of the method is to define a domain for the available
        purchase orders.
        '''
        result = {}

        # A PO can be selected only if at least one PO line is not already in the invoice
        purchase_line_ids = self.invoice_line_ids.mapped('purchase_line_id')
        purchase_ids = self.invoice_line_ids.mapped('purchase_id').filtered(lambda r: r.order_line <= purchase_line_ids)

        # domain = [('invoice_status', '=', 'to invoice')]
        domain = [('state', 'in', ['purchase','done'])]
        if self.partner_id:
            domain += [('partner_id', 'child_of', self.partner_id.id)]
        if purchase_ids:
            domain += [('id', 'not in', purchase_ids.ids)]
        result['domain'] = {'purchase_id': domain}
        return result


    def _prepare_invoice_line_from_po_line(self, line):
        # if line.product_id.purchase_method == 'purchase':
        #     qty = line.product_qty - line.qty_invoiced
        # else:
        #     qty = line.qty_received - line.qty_invoiced

        # # 2021.10.06 - by pass validasi untuk GRN return qty minus
        # if float_compare(qty, 0.0, precision_rounding=line.product_uom.rounding) <= 0 and line.product_qty >= 0:
        #     qty = 0.0
        
        # 2021.11.30 - qty vendor bill
        if line.product_qty >= 0 and line.order_id.is_return == False:
            # 2022.11.25 update invoice capex/opex dari qty srb
            if line.product_id.purchase_method == 'purchase' or line.sync_id or line.sync_id_api:
                qty = line.product_qty - line.qty_invoiced
            else:
                qty = line.qty_received_srb - line.qty_invoiced
            
            if qty < 0:
                qty = 0.0
            #qty = line.product_qty

        elif line.product_qty >= 0 and line.order_id.is_return == True:
            qty = line.product_qty * -1
        elif line.product_qty < 0:
            qty = line.product_qty

        taxes = line.taxes_id
        invoice_line_tax_ids = line.order_id.fiscal_position_id.map_tax(taxes)
        invoice_line = self.env['account.invoice.line']
        data = {
            'purchase_line_id': line.id,
            'name': line.order_id.name+': '+line.name,
            'origin': line.order_id.origin,
            'uom_id': line.product_uom.id,
            'product_id': line.product_id.id,
            'account_id': invoice_line.with_context({'journal_id': self.journal_id.id, 'type': 'in_invoice'})._default_account(),
            'price_unit': line.order_id.currency_id.with_context(date=self.date_invoice).compute(line.price_unit, self.currency_id, round=False),
            'quantity': (1 if line.product_id.name == 'Down Payment' else qty),
            'discount': 0.0,
            'account_analytic_id': line.account_analytic_id.id,
            # 'analytic_tag_ids': line.analytic_tag_ids.ids,
            'invoice_line_tax_ids': invoice_line_tax_ids.ids,
            # tambahan 
            'discount_value': line.discount_value,
            'discount_persen': line.discount_persen,
            'discount_total': line.discount_total,
            # 'price_tax': line.price_tax,
            'price_subtotal': line.price_subtotal
        }
        account = invoice_line.get_invoice_line_account('in_invoice', line.product_id, line.order_id.fiscal_position_id, self.env.company)
        if account:
            data['account_id'] = account.id
        return data

    def _onchange_product_id(self):
        domain = super(AccountInvoice, self)._onchange_product_id()
        if self.purchase_id:
            # Use the purchase uom by default
            self.uom_id = self.product_id.uom_po_id
        return domain


    # Load all unsold PO lines
    @api.onchange('purchase_id')
    def purchase_order_change(self):
        if not self.purchase_id:
            return {}
        if not self.partner_id:
            self.partner_id = self.purchase_id.partner_id.id

        new_lines = self.env['account.invoice.line']
        for line in self.purchase_id.order_line - self.invoice_line_ids.mapped('purchase_line_id'):
            data = self._prepare_invoice_line_from_po_line(line)
            new_line = new_lines.new(data)
            new_line._set_additional_fields(self)
            new_lines += new_line

        self.invoice_line_ids += new_lines
        self.purchase_id = False
        return {}


    @api.onchange('currency_id')
    def _onchange_currency_id(self):
        if self.currency_id:
            for line in self.invoice_line_ids.filtered(lambda r: r.purchase_line_id):
                line.price_unit = line.purchase_id.currency_id.with_context(date=self.date_invoice).compute(line.purchase_line_id.price_unit, self.currency_id, round=False)

    @api.onchange('invoice_line_ids')
    @api.depends('invoice_line_ids')
    def _onchange_origin(self):
        picking_ids = self.invoice_line_ids.mapped('picking_id')
        purchase_ids = self.invoice_line_ids.mapped('purchase_id')
        self.purchase_ids = self.invoice_line_ids.mapped('purchase_id')

        # jika VB by picking id
        if picking_ids:
            purchase_name = []
            for picking in picking_ids:
                if picking.name and picking.po_id:
                    title_name = picking.po_id.title + " ("+picking.name+")"
                else:
                    title_name = picking.name
                purchase_name.append(title_name)
            self.origin = ', '.join(purchase_name)

        elif purchase_ids:
            purchase_name = []
            for po in purchase_ids:
                if po.purchase_name and po.name != str(po.purchase_name):
                    title_name = po.name + " ("+po.purchase_name+")"
                else:
                    title_name = po.name
                purchase_name.append(title_name)
            self.origin = ', '.join(purchase_name)


    @api.model
    def line_get_convert(self, line, part):
        return self.env['product.product']._convert_prepared_anglosaxon_line(line, part)


    # @api.multi
    def action_cancel(self):
        moves = self.env['account.move']
        for inv in self:
            if inv.move_id:
                moves += inv.move_id
            if inv.payment_move_line_ids:
                raise UserError(_('You cannot cancel an invoice which is partially paid. You need to unreconcile related payment entries first.'))

        # First, set the invoices as cancelled and detach the move ids
        self.write({'state': 'cancel', 'move_id': False})
        if moves:
            # second, invalidate the move(s)
            moves.button_cancel()
            # delete the move this invoice was pointing to
            # Note that the corresponding move_lines and move_reconciles
            # will be automatically deleted too
            moves.unlink()
        self.env['account.asset.asset'].sudo().search([('invoice_id', 'in', self.ids)]).write({'active': False})

        return True


   # # @api.multi
   #  def name_get(self):
   #      TYPES = {
   #          'out_invoice': _('Invoice'),
   #          'in_invoice': _('Vendor Bill'),
   #          'out_refund': _('Refund'),
   #          'in_refund': _('Vendor Refund'),
   #      }
   #      result = []
   #      for inv in self:
   #          result.append((inv.id, "%s %s" % (inv.number or TYPES[inv.type], inv.name or '')))
   #      return result

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        recs = self.browse()
        if name:
            recs = self.search([('number', '=', name)] + args, limit=limit)
        if not recs:
            recs = self.search([('name', operator, name)] + args, limit=limit)
        return recs.name_get()


    @api.model
    def _refund_cleanup_lines(self, lines):
        """ Convert records to dict of values suitable for one2many line creation

            :param recordset lines: records to convert
            :return: list of command tuple for one2many line creation [(0, 0, dict of valueis), ...]
        """
        result = []
        for line in lines:
            values = {}
            for name, field in line._fields.items():
                if name in MAGIC_COLUMNS:
                    continue
                # elif field.type == 'many2one':
                    # values[name] = line[name].id
                elif field.type == 'many2one':
                    record = line[name]
                    if record and hasattr(record, 'id'):
                        values[name] = record.id
                    else:
                        values[name] = False
                elif field.type not in ['many2many', 'one2many']:
                    values[name] = line[name]
                elif name == 'invoice_line_tax_ids':
                    values[name] = [(6, 0, line[name].ids)]
            result.append((0, 0, values))
        for i, line in enumerate(lines):
            for name, field in line._fields.items():
                if name == 'asset_category_id':
                    result[i][2][name] = False
                    break

        if self.env.context.get('mode') == 'modify':
            for i in xrange(0, len(lines)):
                for name, field in lines[i]._fields.iteritems():
                    if name == 'sale_line_ids':
                        result[i][2][name] = [(6, 0, lines[i][name].ids)]
                        lines[i][name] = False
        return result



    # @api.multi
    def order_lines_layouted(self):
        """
        Returns this sale order lines ordered by sale_layout_category sequence. Used to render the report.
        """
        self.ensure_one()
        report_pages = [[]]
        for category, lines in groupby(self.invoice_line_ids, lambda l: l.layout_category_id):
            # If last added category induced a pagebreak, this one will be on a new page
            if report_pages[-1] and report_pages[-1][-1]['pagebreak']:
                report_pages.append([])
            # Append category to current report page
            report_pages[-1].append({
                'name': category and category.name or 'Uncategorized',
                'subtotal': category and category.subtotal,
                'pagebreak': category and category.pagebreak,
                'lines': list(lines)
            })

        return report_pages


    @api.model
    def _refund_tax_lines_account_change(self, lines, taxes_to_change):
        # Let's change the account on tax lines when
        # @param {list} lines: a list of orm commands
        # @param {dict} taxes_to_change
        #   key: tax ID, value: refund account

        if not taxes_to_change:
            return lines

        for line in lines:
            if isinstance(line[2], dict) and line[2]['tax_id'] in taxes_to_change:
                line[2]['account_id'] = taxes_to_change[line[2]['tax_id']]
        return lines



    def _get_refund_common_fields(self):
        return ['partner_id', 'payment_term_id', 'account_id', 'currency_id', 'journal_id']

    def _get_refund_prepare_fields(self):
        return ['name', 'reference', 'comment', 'date_due']

    def _get_refund_modify_read_fields(self):
        read_fields = ['type', 'number', 'invoice_line_ids', 'tax_line_ids', 'date']
        return self._get_refund_common_fields() + self._get_refund_prepare_fields() + read_fields

    def _get_refund_copy_fields(self):
        copy_fields = ['company_id', 'user_id', 'fiscal_position_id']
        return self._get_refund_common_fields() + self._get_refund_prepare_fields() + copy_fields

    def _get_currency_rate_date(self):
        return self.date or self.date_invoice

    @api.model
    def _prepare_refund(self, invoice, date_invoice=None, date=None, description=None, journal_id=None):
        """ Prepare the dict of values to create the new refund from the invoice.
            This method may be overridden to implement custom
            refund generation (making sure to call super() to establish
            a clean extension chain).

            :param record invoice: invoice to refund
            :param string date_invoice: refund creation date from the wizard
            :param integer date: force date from the wizard
            :param string description: description of the refund from the wizard
            :param integer journal_id: account.journal from the wizard
            :return: dict of value to create() the refund
        """
        values = {}
        for field in self._get_refund_copy_fields():
            if invoice._fields[field].type == 'many2one':
                values[field] = invoice[field].id
            else:
                values[field] = invoice[field] or False

        values['invoice_line_ids'] = self._refund_cleanup_lines(invoice.invoice_line_ids)

        tax_lines = invoice.tax_line_ids
        taxes_to_change = {
            line.tax_id.id: line.tax_id.refund_account_id.id
            for line in tax_lines.filtered(lambda l: l.tax_id.refund_account_id != l.tax_id.account_id)
        }
        cleaned_tax_lines = self._refund_cleanup_lines(tax_lines)
        values['tax_line_ids'] = self._refund_tax_lines_account_change(cleaned_tax_lines, taxes_to_change)

        if journal_id:
            journal = self.env['account.journal'].browse(journal_id)
        elif invoice['type'] == 'in_invoice':
            journal = self.env['account.journal'].search([('type', '=', 'purchase')], limit=1)
        else:
            journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
        values['journal_id'] = journal.id

        values['type'] = TYPE2REFUND[invoice['type']]
        values['date_invoice'] = date_invoice or fields.Date.context_today(invoice)
        if values.get('date_due', False) and values['date_invoice'] > values['date_due']:
            values['date_due'] = values['date_invoice']
        values['state'] = 'draft'
        values['number'] = False
        values['origin'] = invoice.number
        values['payment_term_id'] = False
        values['refund_invoice_id'] = invoice.id

        if date:
            values['date'] = date
        if description:
            values['name'] = description
        return values

    # @api.multi
    @api.returns('self')
    def refund(self, date_invoice=None, date=None, description=None, journal_id=None):
        new_invoices = self.browse()
        for invoice in self:
            # create the new invoice
            values = self._prepare_refund(invoice, date_invoice=date_invoice, date=date,
                                    description=description, journal_id=journal_id)
            refund_invoice = self.create(values)
            invoice_type = {'out_invoice': ('customer invoices refund'),
                'in_invoice': ('vendor bill refund')}
            message = _("This %s has been created from: <a href=# data-oe-model=account.invoice data-oe-id=%d>%s</a>") % (invoice_type[invoice.type], invoice.id, invoice.number)
            refund_invoice.message_post(body=message)
            new_invoices += refund_invoice
        return new_invoices


    # @api.multi
    def pay_and_reconcile(self, pay_journal, pay_amount=None, date=None, writeoff_acc=None):
        """ Create and post an account.payment for the invoice self, which creates a journal entry that reconciles the invoice.

            :param pay_journal: journal in which the payment entry will be created
            :param pay_amount: amount of the payment to register, defaults to the residual of the invoice
            :param date: payment date, defaults to fields.Date.context_today(self)
            :param writeoff_acc: account in which to create a writeoff if pay_amount < self.residual, so that the invoice is fully paid
        """
        if isinstance( pay_journal, ( int, long ) ):
            pay_journal = self.env['account.journal'].browse([pay_journal])
        assert len(self) == 1, "Can only pay one invoice at a time."
        payment_type = self.type in ('out_invoice', 'in_refund') and 'inbound' or 'outbound'
        if payment_type == 'inbound':
            payment_method = self.env.ref('account.account_payment_method_manual_in')
            journal_payment_methods = pay_journal.inbound_payment_method_ids
        else:
            payment_method = self.env.ref('account.account_payment_method_manual_out')
            journal_payment_methods = pay_journal.outbound_payment_method_ids
        if payment_method not in journal_payment_methods:
            raise UserError(_('No appropriate payment method enabled on journal %s') % pay_journal.name)

        communication = self.type in ('in_invoice', 'in_refund') and self.reference or self.number
        if self.origin:
            communication = '%s (%s)' % (communication, self.origin)

        payment_vals = {
            'invoice_ids': [(6, 0, self.ids)],
            'amount': pay_amount or self.residual,
            'payment_date': date or fields.Date.context_today(self),
            'communication': communication,
            'partner_id': self.partner_id.id,
            'partner_type': self.type in ('out_invoice', 'out_refund') and 'customer' or 'supplier',
            'journal_id': pay_journal.id,
            'payment_type': payment_type,
            'payment_method_id': payment_method.id,
            'payment_difference_handling': writeoff_acc and 'reconcile' or 'open',
            'writeoff_account_id': writeoff_acc and writeoff_acc.id or False,
        }
        if self.env.context.get('tx_currency_id'):
            payment_vals['currency_id'] = self.env.context.get('tx_currency_id')

        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()

        return True


    # @api.multi
    def _track_subtype(self, init_values):
        self.ensure_one()
        if 'state' in init_values and self.state == 'paid' and self.type in ('out_invoice', 'out_refund'):
            return 'account.mt_invoice_paid'
        elif 'state' in init_values and self.state == 'open' and self.type in ('out_invoice', 'out_refund'):
            return 'account.mt_invoice_validated'
        elif 'state' in init_values and self.state == 'draft' and self.type in ('out_invoice', 'out_refund'):
            return 'account.mt_invoice_created'
        return super(AccountInvoice, self)._track_subtype(init_values)


    # @api.multi
    def _get_tax_amount_by_group(self):
        self.ensure_one()
        res = {}
        currency = self.currency_id or self.company_id.currency_id
        for line in self.tax_line_ids:
            res.setdefault(line.tax_id.tax_group_id, 0.0)
            res[line.tax_id.tax_group_id] += line.amount
        res = sorted(res.items(), key=lambda l: l[0].sequence)
        res = [(
            r[0].name, r[1], formatLang(self.with_context(lang=self.partner_id.lang).env, r[1], currency_obj=currency)
        ) for r in res]
        return res

    def invoice_refund_invoice(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.invoice.refund',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_invoice_id': self.id,
            }
        }
        


class AccountInvoiceRefund(models.TransientModel):
    _name = "account.invoice.refund"
    _description = "Invoice Refund"

    @api.model
    def _get_reason(self):
        context = dict(self._context or {})
        active_id = context.get('active_id', False)
        if active_id:
            inv = self.env['account.invoice'].browse(active_id)
            return inv.name
        return ''

    date_invoice = fields.Date(string='Refund Date', default=fields.Date.context_today, required=True)
    date = fields.Date(string='Accounting Date')
    description = fields.Char(string='Reason', required=True, default=_get_reason)
    refund_only = fields.Boolean(string='Technical field to hide filter_refund in case invoice is partially paid', compute='_get_refund_only')
    filter_refund = fields.Selection([('refund', 'Create a draft refund'), ('cancel', 'Cancel: create refund and reconcile'), ('modify', 'Modify: create refund, reconcile and create a new draft invoice')],
        default='refund', string='Refund Method', required=True, help='Refund base on this type. You can not Modify and Cancel if the invoice is already reconciled')

    @api.depends('date_invoice')
    # @api.one
    def _get_refund_only(self):
        invoice_id = self.env['account.invoice'].browse(self._context.get('active_id',False))
        if len(invoice_id.payment_move_line_ids) != 0 and invoice_id.state != 'paid':
            self.refund_only = True
        else:
            self.refund_only = False


    # @api.multi
    def compute_refund(self, mode='refund'):
        inv_obj = self.env['account.invoice']
        inv_tax_obj = self.env['account.invoice.tax']
        inv_line_obj = self.env['account.invoice.line']
        context = dict(self._context or {})
        xml_id = False
        
        for form in self:
            created_inv = []
            date = False
            description = False
            for inv in inv_obj.browse(context.get('active_ids')):
                if inv.state in ['draft', 'proforma2', 'cancel']:
                    raise UserError(_('Cannot refund draft/proforma/cancelled invoice.'))
                if inv.reconciled and mode in ('cancel', 'modify'):
                    raise UserError(_('Cannot refund invoice which is already reconciled, invoice should be unreconciled first. You can only refund this invoice.'))

                date = form.date or False
                description = form.description or inv.name
                refund = inv.refund(form.date_invoice, date, description, inv.journal_id.id)

                created_inv.append(refund.id)
                if mode in ('cancel', 'modify'):
                    movelines = inv.move_id.line_ids
                    to_reconcile_ids = {}
                    to_reconcile_lines = self.env['account.move.line']
                    for line in movelines:
                        if line.account_id.id == inv.account_id.id:
                            to_reconcile_lines += line
                            to_reconcile_ids.setdefault(line.account_id.id, []).append(line.id)
                        if line.reconciled:
                            line.remove_move_reconcile()
                    refund.action_invoice_open()
                    for tmpline in refund.move_id.line_ids:
                        if tmpline.account_id.id == inv.account_id.id:
                            to_reconcile_lines += tmpline
                    to_reconcile_lines.filtered(lambda l: l.reconciled == False).reconcile()
                    if mode == 'modify':
                        invoice = inv.read(inv_obj._get_refund_modify_read_fields())
                        invoice = invoice[0]
                        del invoice['id']
                        invoice_lines = inv_line_obj.browse(invoice['invoice_line_ids'])
                        invoice_lines = inv_obj.with_context(mode='modify')._refund_cleanup_lines(invoice_lines)
                        tax_lines = inv_tax_obj.browse(invoice['tax_line_ids'])
                        tax_lines = inv_obj._refund_cleanup_lines(tax_lines)
                        invoice.update({
                            'type': inv.type,
                            'date_invoice': form.date_invoice,
                            'state': 'draft',
                            'number': False,
                            'invoice_line_ids': invoice_lines,
                            'tax_line_ids': tax_lines,
                            'date': date,
                            'origin': inv.origin,
                            'fiscal_position_id': inv.fiscal_position_id.id,
                        })
                        for field in inv_obj._get_refund_common_fields():
                            if inv_obj._fields[field].type == 'many2one':
                                invoice[field] = invoice[field] and invoice[field][0]
                            else:
                                invoice[field] = invoice[field] or False
                        inv_refund = inv_obj.create(invoice)
                        if inv_refund.payment_term_id.id:
                            inv_refund._onchange_payment_term_date_invoice()
                        created_inv.append(inv_refund.id)
                xml_id = (inv.type in ['out_refund', 'out_invoice']) and 'action_invoice_tree1' or \
                         (inv.type in ['in_refund', 'in_invoice']) and 'action_invoice_tree2'
                # Put the reason in the chatter
                subject = _("Invoice refund")
                body = description
                refund.message_post(body=body, subject=subject)

        # Setelah looping for form in self selesai
        if created_inv:
            if len(created_inv) > 1:
                action = {
                    'name': _('Refunded Invoices'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'account.invoice',
                    'view_mode': 'tree,form',
                    'domain': [('id', 'in', created_inv)],
                    'target': 'current',
                }
            else:
                action = {
                    'name': _('Refund Invoice'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'account.invoice',
                    'view_mode': 'form',
                    'res_id': created_inv[0],
                    'target': 'current',
                }
            return action
        return True

        # if xml_id:
        #     result = self.env.ref('account.%s' % (xml_id)).read()[0]
        #     invoice_domain = safe_eval(result['domain'])
        #     invoice_domain.append(('id', 'in', created_inv))
        #     result['domain'] = invoice_domain
        #     return result
        # return True

    # @api.multi
    def invoice_refund(self):
        data_refund = self.read(['filter_refund'])[0]['filter_refund']
        # raise exceptions.UserError(_(str(data_refund)))
        return self.compute_refund(data_refund)


class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"
    _description = "Payment Term"
    _order = "name"

    def _default_line_ids(self):
        return [(0, 0, {'value': 'balance', 'value_amount': 0.0, 'sequence': 9, 'days': 0, 'option': 'day_after_invoice_date'})]

    name = fields.Char(string='Payment Terms', translate=True, required=True)
    active = fields.Boolean(default=True, help="If the active field is set to False, it will allow you to hide the payment term without removing it.")
    note = fields.Text(string='Description on the Invoice', translate=True)
    line_ids = fields.One2many('account.payment.term.line', 'payment_id', string='Terms', copy=True, default=_default_line_ids)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)

    # @api.one
    def compute(self, value, date_ref=False):
        date_ref = date_ref or fields.Date.today()
        amount = value
        sign = value < 0 and -1 or 1
        result = []
        if self.env.context.get('currency_id'):
            currency = self.env['res.currency'].browse(self.env.context['currency_id'])
        else:
            currency = self.env.company.currency_id
        prec = currency.decimal_places
        for line in self.line_ids:
            if line.value == 'fixed':
                amt = sign * round(line.value_amount, prec)
            elif line.value == 'percent':
                amt = round(value * (line.value_amount / 100.0), prec)
            elif line.value == 'balance':
                amt = round(amount, prec)
            if amt:
                next_date = fields.Date.from_string(date_ref)
                if line.option == 'day_after_invoice_date':
                    next_date += relativedelta(days=line.days)
                elif line.option == 'fix_day_following_month':
                    next_first_date = next_date + relativedelta(day=1, months=1)  # Getting 1st of next month
                    next_date = next_first_date + relativedelta(days=line.days - 1)
                elif line.option == 'last_day_following_month':
                    next_date += relativedelta(day=31, months=1)  # Getting last day of next month
                elif line.option == 'last_day_current_month':
                    next_date += relativedelta(day=31, months=0)  # Getting last day of next month
                result.append((fields.Date.to_string(next_date), amt))
                amount -= amt
        amount = reduce(lambda x, y: x + y[1], result, 0.0)
        dist = round(value - amount, prec)
        if dist:
            last_date = result and result[-1][0] or fields.Date.today()
            result.append((last_date, dist))
        return result
    

class AccountPaymentTermLine(models.Model):
    _inherit = "account.payment.term.line"
    _description = "Payment Term Line"

    option = fields.Selection([
            ('day_after_invoice_date', 'Day(s) after the invoice date'),
            ('fix_day_following_month', 'Day(s) after the end of the invoice month (Net EOM)'),
            ('last_day_following_month', 'Last day of following month'),
            ('last_day_current_month', 'Last day of current month'),
        ],
        default='day_after_invoice_date', required=True, string='Options'
        )
    
# 2021.12.28 Patient Debt Collection
# Record data piutang pasien
class PatientDebt(models.Model):
    _name = 'patient.debt'
    _rec_name = 'trans_no'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    tglproses = fields.Date(string="TglProses")
    patient_type = fields.Selection([('1', 'OP'), ('2', 'IP'), ('3', 'Emergency'), ('4', 'Daycare'), ('5', 'MCU/Pharmacy Issues Only(FO)'), ('6', 'Pharmacy (Direct)'), ('0', 'Both')], string='Patient Type', readonly=False, index=True)
    trans_type = fields.Selection([('Debt','Debt'), ('Payment', 'Payment of Debt')], string="Trans Type")
    trans_no = fields.Char(string="Trans No")
    trans_date = fields.Date(string="Trans Date")
    billing_id = fields.Many2one('sale.order.bill', string="Billing", required=False)
    billing_no = fields.Char(string="Billing No.")
    admission_id = fields.Many2one('sale.order',string="Admission", required=False)
    admission_no = fields.Char(string="Admission No.")
    patient_name = fields.Char(string="Patient Name")
    reference_no = fields.Char(string="Ref Debt/Receipt No.")
    payment_name = fields.Char(string="Payment Name")
    edc_machine = fields.Char(string="EDC Machine")
    partner_id = fields.Many2one('res.partner', string="Patient")
    amount = fields.Float(string="Amount")
    user_name = fields.Char(string="User Name")
    company_id = fields.Many2one('res.company',string="Company",)
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel','Cancelled')],string="Status",readonly=True,default='draft',track_visibility='always')
    journal_id = fields.Many2one('account.move',string="Journal")
    note = fields.Text(string="Notes")

    # untuk send payload dari dhealth cuma kirim sync_type, auto-fill company_id
    @api.model
    def create(self, vals):
        result = super(PatientDebt, self).create(vals)
        
        # if self.env.context.get('updated'): return result
        # self = self.with_context(updated=True)

        if not vals.get('company_id') and vals.get('sync_type'):
            result.company_id = self.env['res.company'].sudo().search([('sync_type', '=', vals.get('sync_type'))],limit=1).id
        
        if not vals.get('patient_type') and vals.get('admission_id'):
            result.patient_type = result.admission_id.patient_type
            result.partner_id = result.admission_id.partner_id.id or None
        
        return result

    # @api.multi
    def unlink(self):
        for r in self:
            if r.state == 'confirmed':
                raise exceptions.ValidationError("Please cancel the record before delete")
        return super(PatientDebt, self).unlink()
    
    # @api.multi 
    def action_draft(self):
        for record in self:
            record.state = 'draft'

    # @api.multi 
    def action_cancel_call(self):
        for record in self:
            record.state = 'cancel'
            
    # @api.multi
    def action_confirm(self):
        journal_id = self.env['account.journal'].search([('name', 'ilike', '%Patient Receviable%'),('company_id', '=', self.company_id.id)],limit=1)
        account_partner = self.env['account.account'].search([('code', 'ilike', '%1104020105%'),('company_id', '=', self.company_id.id)],limit=1)
        account = self.env['account.account'].search([('name', '=', 'Private Outstanding'),('company_id', '=', self.company_id.id)],limit=1)
        
        # 2022.01.31 - Ambil COA Credit dari res.company untuk seluruh patient.debt > 31-Jan-2022
        if self.tglproses > datetime.strptime('2022-01-31', '%Y-%m-%d').date():
            account = self.company_id.receivable_cash_id 
            account_partner = self.company_id.receivable_debt_id


        if self.trans_type == 'Debt':
            debit_vals = {
                'name': str(self.trans_type) + ": " + str(self.patient_name) + " by " + str(self.user_name) + " on " + str(self.tglproses) + "",
                'debit':abs(self.amount),
                'credit':0.0,
                'partner_id': self.partner_id.id or None,
                'account_id':account_partner.id,
            }
            credit_vals = {
                'name': str(self.trans_type) + ": " + str(self.patient_name) + " by " + str(self.user_name) + " on " + str(self.tglproses) + "",
                'debit':0.0,
                'credit':abs(self.amount),
                'partner_id': self.partner_id.id or None,
                'account_id':account.id,
            }

            vals = {
                'journal_id':journal_id.id,
                'date':self.tglproses,
                'ref': (self.trans_type or '') + ": " + (self.trans_no or '') + " - " + (self.admission_no or ''),
                'state':'draft',
                'line_ids': [(0, 0, debit_vals), (0, 0, credit_vals)]
            }
            move = self.env['account.move'].create(vals)
            move.action_post()
            self.journal_id = move.id
            self.state = 'confirmed'


        if self.trans_type == 'Payment':
            debit_vals = {
                'name': str(self.trans_type) + ": " + str(self.patient_name) + " by " + str(self.user_name) + " on " + str(self.tglproses) + "",
                'debit':abs(self.amount),
                'credit':0.0,
                'partner_id': self.partner_id.id or None,
                'account_id':account.id,
            }
            credit_vals = {
                'name': str(self.trans_type) + ":  " + str(self.patient_name) + " by " + str(self.user_name) + " on " + str(self.tglproses) + "",
                'debit':0.0,
                'credit':abs(self.amount),
                'partner_id': self.partner_id.id or None,
                'account_id': account_partner.id,
            }

            vals = {
                'journal_id':journal_id.id,
                'date':self.tglproses,
                'ref': (self.trans_type or '') + ": " + (self.trans_no or '') + " - " + (self.admission_no or ''),
                'state':'draft',
                'line_ids': [(0, 0, debit_vals), (0, 0, credit_vals)]
            }
            move = self.env['account.move'].create(vals)
            self.journal_id = move.id
            move.action_post()
            self.state = 'confirmed'


            # 20210819 - update personal_balance pada billing
            if self.sync_id == 0 and self.trans_type in['Payment']:
                if self.billing_id:
                    if (self.billing_id.personal_receipt or 0) == 0:
                        self.billing_id.personal_balance = self.billing_id.personal_amount
                    self.billing_id.personal_receipt -= self.amount 
                    self.billing_id.personal_balance += self.amount

                if self.admission_id:
                    if (self.admission_id.personal_receipt or 0) == 0:
                        self.admission_id.personal_balance = self.admission_id.personal_amount
                    self.admission_id.personal_receipt -= self.amount 
                    self.admission_id.personal_balance += self.amount

        return True


    # @api.multi
    def action_cancel(self):
        if self.state == 'confirmed':
            self.state = 'draft'
            self.journal_id.button_cancel()
            self.journal_id.unlink()

            # 20210819 - update personal_balance pada billing
            if self.sync_id == 0 and self.trans_type in['Payment']:
                if self.billing_id:
                    self.billing_id.personal_receipt += self.amount 
                    self.billing_id.personal_balance -= self.amount
                if self.admission_id:
                    self.admission_id.personal_receipt += self.amount 
                    self.admission_id.personal_balance -= self.amount

    @api.model
    def _sync_patient_debt_collect_wipro(self, sync_type='1'):
        import trollius as asyncio
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>',0)])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)],order='sync_date desc',limit=1).sync_date
        data = []
        date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
        query = """
            SELECT
                'draft' 'state',
                a.TransEntryID 'sync_id',
                a.tglproses 'tglproses',
                a.TransType 'trans_type',
                a.TransNo 'trans_no',
                a.DepositDate 'trans_date',
                a.AdmissionNumber 'admission_no',
                a.PatientName 'patient_name',
                a.ReferenceNo 'reference_no',
                a.PaymentName 'payment_name',
                a.EDCMachine 'edc_machine',
                a.Amount 'amount',
                a.UserName 'user_name'
            from dbo.VRP_OdooPatientDeposits a 
            where a.tglproses = '%s'
            """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), query)
        print (data)
        if not data:
            print ("No data available")
            return
        fields_without_id = tuple(
            key for key in self._fields
            if key != 'id' and 'property' not in key and 'ids' not in key
            and self._fields[key].required == True
            and self._fields[key].store == True)
        columns = tuple(
            key for key in data[0].keys()
            if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
        fields_without_id += columns
        columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
        fields = fields_without_id + ('id', )
        if columns:
            columns += ('id', )
        default_values = {}
        for field in fields:
            if field in columns:
                continue
            default = self._fields[field].default
            if callable(default):
                default = default(self)
            if isinstance(default, models.Model):
                default = default.id
            default_values[field] = default
        values = ''
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        @asyncio.coroutine
        def process_query(object):
            for value in default_values:
                object[value] = default_values[value]

            object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'] = sync_type
            object['company_id'] = self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
            value = False
            for field in fields:
                if value:
                    value += ', '
                else:
                    value = '('
                if field == 'id' and object['id'] == 'DEFAULT':
                    value += object['id']
                    continue
                if type(object[field]) in [str, unicode]:
                    string = object[field]
                    value += "'" + string.replace("'", "''") + "'"
                    continue
                value += sync.json(object[field])
            value += ')'
            return value
            #values += value

        loop = asyncio.get_event_loop()
        tasks = [asyncio.create_task(process_query(object)) for object in data]
        for result in loop.run_until_complete(asyncio.gather(*tasks)):
            if result:
                if values:
                    values += ', '
                values += result
        excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        columns = sync.remove_unicode(str(fields)).replace("'", "")
        columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        print (values)
        if not values:
            print ("No data available")
            return
        query = "INSERT into patient_debt %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)
        self.env.cr.execute("""
            UPDATE patient_debt AS a 
            SET company_id = b.id
            FROM res_company AS b 
            WHERE b.sync_type=a.sync_type
                AND a.company_id IS NULL
            """)

    @api.model
    def _sync_patient_debt_collect_wipro_manual(self,sync_type='1',date_start='2019-01-01',date_end='2019-01-01'):
        import trollius as asyncio
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>',0)])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)],order='sync_date desc',limit=1).sync_date
        data = []
        date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
        query = """
            SELECT
                'draft' 'state',
                a.TransEntryID 'sync_id',
                a.tglproses 'tglproses',
                a.TransType 'trans_type',
                a.TransNo 'trans_no',
                a.DepositDate 'trans_date',
                a.AdmissionNumber 'admission_no',
                a.PatientName 'patient_name',
                a.ReferenceNo 'reference_no',
                a.PaymentName 'payment_name',
                a.EDCMachine 'edc_machine',
                a.Amount 'amount',
                a.UserName 'user_name'
            from dbo.VRP_OdooPatientDeposits a 
            where a.tglproses >= '%s' and a.tglproses <= '%s'
            """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), query)
        print (data)
        if not data:
            print ("No data available")
            return
        fields_without_id = tuple(
            key for key in self._fields
            if key != 'id' and 'property' not in key and 'ids' not in key
            and self._fields[key].required == True
            and self._fields[key].store == True)
        columns = tuple(
            key for key in data[0].keys()
            if key in self._fields and key not in fields_without_id) + (
                'sync_date', 'sync_type') if data else ()
        fields_without_id += columns
        columns += tuple(
            key for key in data[0].keys()
            if key in self._fields and key not in columns) if data else ()
        fields = fields_without_id + ('id', )
        if columns:
            columns += ('id', )
        default_values = {}
        for field in fields:
            if field in columns:
                continue
            default = self._fields[field].default
            if callable(default):
                default = default(self)
            if isinstance(default, models.Model):
                default = default.id
            default_values[field] = default
        values = ''
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        @asyncio.coroutine
        def process_query(object):
            for value in default_values:
                object[value] = default_values[value]

            object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'] = sync_type
            object['company_id'] = self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
            value = False
            for field in fields:
                if value:
                    value += ', '
                else:
                    value = '('
                if field == 'id' and object['id'] == 'DEFAULT':
                    value += object['id']
                    continue
                if type(object[field]) in [str, unicode]:
                    string = object[field]
                    value += "'" + string.replace("'", "''") + "'"
                    continue
                value += sync.json(object[field])
            value += ')'
            return value
            #values += value

        loop = asyncio.get_event_loop()
        tasks = [asyncio.create_task(process_query(object)) for object in data]
        for result in loop.run_until_complete(asyncio.gather(*tasks)):
            if result:
                if values:
                    values += ', '
                values += result
        excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        columns = sync.remove_unicode(str(fields)).replace("'", "")
        columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        print (values)
        if not values:
            print ("No data available")
            return
        query = "INSERT into patient_debt %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)
        self.env.cr.execute("""
            UPDATE patient_debt AS a 
            SET company_id = b.id
            FROM res_company AS b 
            WHERE b.sync_type=a.sync_type
                AND a.company_id IS NULL
            """)

        # @asyncio.coroutine --DR
        # def process_query(object):
        #     for value in default_values:
        #         object[value] = default_values[value]

        #     object['id'] = 'DEFAULT'
        #     object['sync_date'] = now
        #     object['sync_type'] = sync_type
        #     object['company_id'] = self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
        #     value = False
        #     for field in fields:
        #         if value:
        #             value += ', '
        #         else:
        #             value = '('
        #         if field == 'id' and object['id'] == 'DEFAULT':
        #             value += object['id']
        #             continue
        #         if type(object[field]) in [str, unicode]:
        #             string = object[field]
        #             value += "'" + string.replace("'", "''") + "'"
        #             continue
        #         value += sync.json(object[field])
        #     value += ')'
        #     return value
        #     #values += value

        # loop = asyncio.get_event_loop()
        # tasks = [asyncio.create_task(process_query(object)) for object in data]
        # for result in loop.run_until_complete(asyncio.gather(*tasks)):
        #     if result:
        #         if values:
        #             values += ', '
        #         values += result
        # excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        # columns = sync.remove_unicode(str(fields)).replace("'", "")
        # columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        # print values
        # if not values:
        #     print "No data available"
        #     return
        # query = "INSERT into patient_debt %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        # print query.encode('utf8')
        # self.env.cr.execute(query)
        # self.env.cr.execute("""
        #     UPDATE patient_debt AS a 
        #     SET company_id = b.id
        #     FROM res_company AS b 
        #     WHERE b.sync_type=a.sync_type
        #         AND a.company_id IS NULL
        #     """)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(PatientDebt,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Patient Receivable" decoration-muted="state == 'cancel'" decoration-info="state == 'draft'" delete="false">
                    <field name="tglproses"/>
                    <field name="trans_type"/>
                    <field name="trans_no"/>
                    <field name="admission_no"/>
                    <field name="patient_name"/>
                    <field name="amount"/>
                    <field name="payment_name"/>
                    <field name="user_name"/>
                    <field name="state"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Debt..">
                    <filter string="Draft" domain="[('state','=', 'draft')]" help="Draft"/>
                    <filter string="Confirm" domain="[('state','=', 'confirmed')]" help="Confirm"/>
                    <separator/>
                    <field name="trans_no"/>
                    <field name="user_name"/>
                    <field name="payment_name"/>
                    <field name="trans_type"/>
                    <field name="note"/>
                    <field name="edc_machine"/>
                    <field name="admission_id"/>
                </search>
            """
        
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


    # @api.model
    # def _sync_patient_debt_collect_wipro_manual(self,sync_type='1',date_start='2019-01-01',date_end='2019-01-01'):
    #     import trollius as asyncio
    #     sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>',0)])}
    #     sync_date = self.sudo().search([('sync_type', '=', sync_type)],order='sync_date desc',limit=1).sync_date
    #     data = []
    #     date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
    #     query = """
    #         SELECT
    #             'draft' 'state',
    #             a.TransEntryID 'sync_id',
    #             a.tglproses 'tglproses',
    #             a.TransType 'trans_type',
    #             a.TransNo 'trans_no',
    #             a.DepositDate 'trans_date',
    #             a.AdmissionNumber 'admission_no',
    #             a.PatientName 'patient_name',
    #             a.ReferenceNo 'reference_no',
    #             a.PaymentName 'payment_name',
    #             a.EDCMachine 'edc_machine',
    #             a.Amount 'amount',
    #             a.UserName 'user_name'
    #         from dbo.VRP_OdooPatientDeposits a 
    #         where a.tglproses >= '%s' and a.tglproses <= '%s'
    #         """ % (date_start, date_end)
    #     data += sync.get_data(sync.servers.get(sync_type), query)
    #     print (data)
    #     if not data:
    #         print ("No data available")
    #         return
    #     fields_without_id = tuple(
    #         key for key in self._fields
    #         if key != 'id' and 'property' not in key and 'ids' not in key
    #         and self._fields[key].required == True
    #         and self._fields[key].store == True)
    #     columns = tuple(
    #         key for key in data[0].keys()
    #         if key in self._fields and key not in fields_without_id) + (
    #             'sync_date', 'sync_type') if data else ()
    #     fields_without_id += columns
    #     columns += tuple(
    #         key for key in data[0].keys()
    #         if key in self._fields and key not in columns) if data else ()
    #     fields = fields_without_id + ('id', )
    #     if columns:
    #         columns += ('id', )
    #     default_values = {}
    #     for field in fields:
    #         if field in columns:
    #             continue
    #         default = self._fields[field].default
    #         if callable(default):
    #             default = default(self)
    #         if isinstance(default, models.Model):
    #             default = default.id
    #         default_values[field] = default
    #     values = ''
    #     now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # @asyncio.coroutine --DR
        # def process_query(object):
        #     for value in default_values:
        #         object[value] = default_values[value]

        #     object['id'] = 'DEFAULT'
        #     object['sync_date'] = now
        #     object['sync_type'] = sync_type
        #     object['company_id'] = self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
        #     value = False
        #     for field in fields:
        #         if value:
        #             value += ', '
        #         else:
        #             value = '('
        #         if field == 'id' and object['id'] == 'DEFAULT':
        #             value += object['id']
        #             continue
        #         if type(object[field]) in [str, unicode]:
        #             string = object[field]
        #             value += "'" + string.replace("'", "''") + "'"
        #             continue
        #         value += sync.json(object[field])
        #     value += ')'
        #     return value
        #     #values += value

        # loop = asyncio.get_event_loop()
        # tasks = [asyncio.create_task(process_query(object)) for object in data]
        # for result in loop.run_until_complete(asyncio.gather(*tasks)):
        #     if result:
        #         if values:
        #             values += ', '
        #         values += result
        # excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        # columns = sync.remove_unicode(str(fields)).replace("'", "")
        # columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        # print values
        # if not values:
        #     print ("No data available")
        #     return
        # query = "INSERT into patient_debt %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        # print (query.encode('utf8'))
        # self.env.cr.execute(query)
        # self.env.cr.execute("""
        #     UPDATE patient_debt AS a 
        #     SET company_id = b.id
        #     FROM res_company AS b 
        #     WHERE b.sync_type=a.sync_type
        #         AND a.company_id IS NULL
        #     """)


# 2021.09.23 
class ARBulkReceivingWizard(models.TransientModel):
    _name = 'account.bulk.receiving.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    receiving_filename = fields.Char(string='Filename')
    csv_import = fields.Boolean(default=False, readonly=True)
    receiving_file = fields.Binary(
        string='Receiving file for update Letter', required=True,
        help="Upload a Receiving file. Supported formats: CSV, XML and PDF (PDF with an embeded XML file).")
    description = fields.Html(string="Notes", default="File harus dalam bentuk CSV dengan format seperti berikut ini:<br>leter_no,sent_date,received_date,received_by,received_ref >> MHCL20190001,10/22/2021,10/22/2021,FIRGI,JNE211000001")

    @api.onchange('receiving_file')
    def receiving_file_change(self):
        if self.receiving_filename and self.receiving_file:
            filetype = mimetypes.guess_type(self.receiving_filename)
            logger.debug('Order file mimetype: %s', filetype)
            if filetype and filetype[0] in ('text/csv', 'text/plain'):
                self.csv_import = True
            else:
                return {'warning': {
                    'title': _('Unsupported file format'),
                    'message': _("This file '%s' is not recognised as a CSV, file. Please check the file and it's extension.") % self.receiving_filename
                    }}
        else:
            self.csv_import = False

    # @api.multi
    def bulk_receiving(self):
        company_id = self.company_id.id 
        user_id = self.env.user.id 

        filetype = mimetypes.guess_type(self.receiving_filename)
        logger.debug('Order file mimetype: %s', filetype)
        if filetype and filetype[0] not in ('text/csv', 'text/plain'):
            raise UserError(_("Please make sure file import is CSV format."))

        if company_id:
            csv_data = base64.b64decode(self.receiving_file)
            data_file = io.StringIO(csv_data.decode(encoding='ASCII',errors="ignore"))
            csv_reader = csv.reader(data_file, delimiter=',')

            i = 0
            for row in csv_reader:
                i += 1
                if i == 1 and row[0] not in['letter_no']:
                    raise UserError(_("Format CSV import harus s3suai."))
                
                if i == 1 and row[0] in['letter_no']:
                    continue

                letter_no = row[0]
                sent_date = datetime.datetime.strptime(row[1], "%m/%d/%Y").strftime("%Y-%m-%d")
                received_date = datetime.datetime.strptime(row[2], "%m/%d/%Y").strftime("%Y-%m-%d")
                # sent_date = datetime.datetime.strptime(row[1], "%Y-%m-%d").date()
                # received_date = datetime.datetime.strptime(row[2], "%Y-%m-%d").date()
                
                received_by = row[3]
                received_ref = row[4]

                letter = self.env['account.coveringletter'].search([('company_id','=',company_id),('name','=',letter_no)], limit=1)
                if letter:
                    letter.write({'sent_date':sent_date, 'received_date':received_date, 'received_by':received_by, 'received_ref':received_ref})
                    open('/opt/odoo16/logs/log_import_receiving.log', 'a+').write(str("update CL " + letter_no + " by user_id " + str(user_id)))


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ARBulkReceivingWizard,self).get_view(view_id=view_id,view_type=view_type, **options)
        res['arch'] = """
            <form string="Bulk Receiving">
                <group>
                    <group>
                        <field name="company_id" readonly="1" />
                        <field name="receiving_file" filename="receiving_filename"/>
                        <field name="receiving_filename" invisible="1"/>
                        <field name="csv_import" readonly="1"/>
                    </group>
                    <group>
                        <field name="description" nolabel="1" readonly="1"/>
                    </group>
                </group>
                <footer>
                    <button name="bulk_receiving" attrs="{'readonly':[('csv_import','=',0)]}" string="Bulk Receiving Letter" type="object" class="oe_highlight"/>
                </footer>
            </form>
        """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

class AccountPaymentWizard(models.TransientModel):
    _name = 'account.payment.wizard'

    bank_id = fields.Many2one('account.journal', string="Ganti bank ke")
    cheque_number = fields.Char(string="Cheque Number")
    payment_date = fields.Date(string="Payment Date")
    payment_ids = fields.Many2many('account.payment', string="Payment")

    # @api.multi
    def confirm(self):
        for p in self.payment_ids:
            open('/opt/odoo16/logs/payment_w.log', 'a+').write('\n' + str(p.id))
            if not p.partner_id.property_account_receivable_id:
                raise exceptions.ValidationError("Partner " + p.partner_id.name +" doesn't have receivable Account!!")
            p.journal_id = self.bank_id
            p.cheque = self.cheque_number
            if self.payment_date:
                p.payment_date = self.payment_date
            open('/opt/odoo16/logs/payment_w.log','a+').write('\n' + "create_journal")
            p.create_journal()
            open('/opt/odoo16/logs/payment_w.log', 'a+').write('\n' + "post")
            p.action_post()
        return

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(AccountPaymentWizard,self).get_view(view_id=view_id,view_type=view_type, **options)
        res['arch'] = """
            <form string="Stock Status">
                <group>
                    <field name="bank_id" />
                    <field name="cheque_number" />
                    <field name="payment_date" />
                </group>
                <group>
                    <field name="payment_ids" />
                </group>
                <footer>
                    <button name="confirm" string="Confirm" type="object" class="oe_highlight"/>
                </footer>
            </form>
        """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


# Customer Type Wizard
class CustomerTypeWizard(models.TransientModel):
    _name = "customer.type.wizard"

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    partner_id = fields.Many2one('res.partner', string="Customer")
    partner_type = fields.Char(related='partner_id.customer_type_wipro', string="Customer Type")
    partner_account = fields.Many2one('account.account', related='partner_id.account_ar_id', string="Customer Account")
    journal_id = fields.Many2one('account.journal', string="Journal")
    ref = fields.Char(string="Reference")

    new_partner_type = fields.Selection([
        ('PRIVATE CASH','PRIVATE CASH'),
        ('PRIVATE CREDIT','PRIVATE CREDIT'),
        ('PRIVATE','PRIVATE'),
        ('EMPLOYEE','EMPLOYEE'),
        ('REFFERAL','REFFERAL'),
        ('BPJS','BPJS'),
        ('INSURANCE','INSURANCE'),
        ('E-COMMERCE','E-COMMERCE'),
        ('PERSONAL','PERSONAL'),
        ('CORPORATE','CORPORATE'),
        ('VOUCHER','VOUCHER'),
        ('GOVERNMENT','GOVERNMENT')], string="New Type")
    new_partner_account = fields.Many2one('account.account', string="New Account")

    # @api.multi
    def update(self):
        partner = self.env['res.partner'].browse(self.partner_id.id)
        if partner:
            old_account_id = partner.property_account_receivable_id.id or partner.account_ar_id.id 
            old_type = partner.customer_type_wipro or ''
            journal_id = self.journal_id.id 
            partner_id = self.partner_id.id 
            ref = self.ref or '' 
            date = tools.datetime.now().strftime('%Y-%m-%d')

            if self.new_partner_type not in[old_type]:
                partner.customer_type_wipro = self.new_partner_type 

            # jika ada yang berubah di account AR
            if self.new_partner_account.id not in[old_account_id]:
                partner.account_ar_id = self.new_partner_account.id 
                partner.property_account_receivable_id = self.new_partner_account.id 

                # buat jurnal reklas 
                query = """
                    select aml.account_id, 
                        aml.covering_id, 
                        cl.name covering_no,
                        coalesce(aml.date_maturity, cl.due_date, cl.date) date_maturity,
                        sum(aml.balance) balance
                    from account_move_line aml 
                    inner join account_move am on am."id" = aml.move_id 
                    inner join account_account aa on aa."id" = aml.account_id
                    inner join account_coveringletter cl on cl.id = aml.covering_id 
                    where am."state" = 'posted'
                        and am.company_id = {company_id}
                        and aml.partner_id = {partner_id}
                        and aml.covering_id is not null 
                        and left(aa.code,8) = '11040102'
                    group by aml.covering_id, aml.account_id, cl.name, 
                        coalesce(aml.date_maturity, cl.due_date, cl.date) 
                    having sum(aml.balance) <> 0
                """.format(
                    company_id = self.company_id.id,
                    partner_id = self.partner_id.id 
                )
                self.env.cr.execute(query)
                results = self.env.cr.dictfetchall()


                if results:
                    move_lines = []
                    action = {}

                    # looping per account & invoice 
                    for row in results:

                        if row['balance'] >= 0.0:
                            account_credit_id = row['account_id'] or None
                            account_debit_id = self.new_partner_account.id or None
                            covering_id = row['covering_id'] or None
                            covering_no = row['covering_no'] or ''
                            date_maturity = row['date_maturity'] or date
                            amount  = abs(row['balance']) or 0.0
                        else:
                            account_credit_id = self.new_partner_account.id or None
                            account_debit_id = row['account_id'] or None
                            covering_id = row['covering_id'] or None
                            covering_no = row['covering_no'] or ''
                            date_maturity = row['date_maturity'] or date
                            amount  = abs(row['balance']) or 0.0

                        move_lines.append([0, 0, {'partner_id': partner_id, 'date_maturity': date_maturity, 'name':"Reklas " + covering_no, 'debit':amount, 'credit':0.0,'account_id':account_debit_id }])
                        move_lines.append([0, 0, {'partner_id': partner_id, 'date_maturity': date_maturity, 'name':"Reklas " + covering_no, 'debit':0.0, 'credit':amount,'account_id':account_credit_id }])
                        open('/opt/odoo16/logs/log_change_payer_type.log','a+').write('\n' + str(move_lines) + '\n' + 'domain show report')
                            

                    move = self.env['account.move'].create({'partner_id': partner_id, 'journal_id':journal_id,'line_ids':move_lines,'date':date, 'ref': 'Update CustomerType: ' + ref})
                    if move:
                        move.action_post()

                        action['type'] = 'ir.actions.act_window'
                        action['view_mode'] = 'tree,form,pivot'
                        action['view_type'] = 'form'
                        action['res_model'] = 'account.move'
                        action['res_id'] = move.id 
                        action['name'] = 'Account Move'
                        action['views'] = [(self.sudo().env.ref('account.view_move_form').id, 'form'), (False, 'tree'), (False, 'pivot')]
                        open('/opt/odoo16/logs/log_change_payer_type.log','a+').write('\n' + str(action) + '\n' + 'domain show report')
                        return action


# 2021.09.17 - Compiled AR Report
class ARReportCompiledWizard(models.TransientModel):
    _name = 'account.receivable.report.compiled.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    format_print_id = fields.Selection([('pdf','PDF'),('xls','EXCEL')], string="Format", required=True, default='xls')
    date_start = fields.Date(string="Date Start", required=False)
    date_end = fields.Date(string="Date End", required=False)
    payment_date_start = fields.Date(string="Payment Date Start", required=False)
    payment_date_end = fields.Date(string="Payment Date End", required=False)
    cutoff_date = fields.Date(string="Cutoff Date", required=False)
    partner_id = fields.Many2one('res.partner', index=False, string="Customer")
    partner_ids = fields.Many2many('res.partner', string="Customers")
    bank_ids = fields.Many2many('account.account', string="Bank")
    type_report = fields.Selection([
        ('accrual', 'Outstanding Admission (Accrual)'),
        #('unbilled2', 'Unbilled Invoice (HIS)'),
        ('advance', 'Advance Realization'),
        ('tenant', 'Invoice Tenant'),
        ('tenant_new', 'Invoice Tenant (New)'),
        ('discount', 'Credit Note'),
        ('receipt', 'Receipt Payment'),
        ('receipt_new', 'Receipt Payment (New)'),
        ('rekap_discount', 'AR Discount After Invoice (Bills)'),
        ('rekap_discount_summary', 'AR Discount After Invoice (Summary)'),
        ('unbilled', 'AR Unbilled Per Patient Bills'),
        ('unbilled_cob', 'AR Unbilled Per COB Bills'),
        ('aging_patient_bill', 'AR Aging Per Patient Bills'),
        ('aging_cob', 'AR Aging Per COB Bills'),
        ('aging_invoice', 'AR Aging Per Invoice Letter'), 
        ('aging_payer', 'AR Aging Per Payer'),
        ('aging_payer_mutation', 'AR Aging Per Payer Mutation'),
        ('aging_summary', 'AR Aging Per PayerType'),
        ('bank_receipt_settlement', 'Bank Receipt Settlement'),
        ('aging_tracking_payer', 'AR Tracking Per Payer'),
        ('aging_tracking_invoice', 'AR Tracking Per Invoice')], string='Type Report', required=True)

    interval_month = fields.Selection([('1','1'),('2','2'),('3','3'),('4','4'),('5','5'),('6','6')], string="Interval Month", default='1')


    # @api.multi
    def print_all(self):
        if self.type_report in ('tenant_new', 'receipt_new'):
            if self.format_print_id != 'xls':
                raise exceptions.ValidationError(_(
                    'Invoice Tenant (New) and Receipt Payment (New) are available in Excel format only.'
                ))
            if not self.date_start or not self.date_end:
                raise exceptions.ValidationError(_('Date Start and Date End are required.'))
            if self.date_start > self.date_end:
                raise exceptions.ValidationError(_('Date Start cannot be after Date End.'))

        if self.type_report in ('aging_tracking_payer', 'aging_tracking_invoice'):
            if any([self.payment_date_start <= self.cutoff_date, self.payment_date_end <= self.cutoff_date]):
                raise exceptions.ValidationError(_("Payment date harus lebih besar dari cutoff date."))
                
        if self.type_report == 'aging_payer':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/aging_report_detail?id=' + str(self.id)
            action['target'] = 'new'
            return action
            
        if self.type_report == 'aging_payer_mutation':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/aging_report_mutation_detail?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'bank_receipt_settlement':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/bank_receipt_settlement_detail?id=' + str(self.id)
            action['target'] = 'new'
            return action


        if self.type_report == 'aging_summary':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/aging_report_summary?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'aging_invoice':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/aging_report_invoice?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'rekap_discount':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/discount_summary_bills?id=' + str(self.id)
            action['target'] = 'new'
            return action
        
        if self.type_report == 'rekap_discount_summary':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/discount_summary_invoice?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'unbilled':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/new_outstanding_billing_payer?id=' + str(self.id)
            action['target'] = 'new'
            return action
        
        if self.type_report == 'aging_patient_bill':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/new_outstanding_billing_payer?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'unbilled_cob':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/new_outstanding_billing_payer?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'aging_cob':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/new_outstanding_billing_payer?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'unbilled2':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/unbilled_report_detail?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'tenant':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_invoice_tenant?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'tenant_new':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_invoice_tenant_new?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'advance':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/advance_report?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'accrual':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_accrual_revenue?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'discount':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_payer_discount?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'receipt':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_payer_receipt?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'receipt_new':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_payer_receipt_new?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'aging_tracking_payer':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_aging_tracking_payer?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'aging_tracking_invoice':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_aging_tracking_invoice?id=' + str(self.id)
            action['target'] = 'new'
            return action


class AccountInvoiceTax(models.Model):
    _name = "account.invoice.tax"
    _description = "Invoice Tax"
    _order = 'sequence'

    def _compute_base_amount(self):
        tax_grouped = {}
        for invoice in self.mapped('invoice_id'):
            tax_grouped[invoice.id] = invoice.get_taxes_values()
        for tax in self:
            tax.base = 0.0
            if tax.tax_id:
                key = tax.tax_id.get_grouping_key({
                    'tax_id': tax.tax_id.id,
                    'account_id': tax.account_id.id,
                    'account_analytic_id': tax.account_analytic_id.id,
                })
                if tax.invoice_id and key in tax_grouped[tax.invoice_id.id]:
                    tax.base = tax_grouped[tax.invoice_id.id][key]['base']
                else:
                    _logger.warning('Tax Base Amount not computable probably due to a change in an underlying tax (%s).', tax.tax_id.name)

    invoice_id = fields.Many2one('account.invoice', string='Invoice', ondelete='cascade', index=True)
    name = fields.Char(string='Tax Description', required=True)
    tax_id = fields.Many2one('account.tax', string='Tax', ondelete='restrict')
    account_id = fields.Many2one('account.account', string='Tax Account', required=True, domain=[('deprecated', '=', False)])
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic account')
    amount = fields.Monetary()
    manual = fields.Boolean(default=True)
    sequence = fields.Integer(help="Gives the sequence order when displaying a list of invoice tax.")
    company_id = fields.Many2one('res.company', string='Company', related='account_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', related='invoice_id.currency_id', store=True, readonly=True)
    base = fields.Monetary(string='Base', compute='_compute_base_amount')
    invoice_id = fields.Many2one('account.invoice', string='Invoice', ondelete='cascade', index=True)

    # DO NOT FORWARD-PORT!!! ONLY FOR v10
    @api.model
    def create(self, vals):
        inv_tax = super(AccountInvoiceTax, self).create(vals)
        # Workaround to make sure the tax amount is rounded to the currency precision since the ORM
        # won't round it automatically at creation.
        if inv_tax.company_id.tax_calculation_rounding_method == 'round_globally':
            inv_tax.amount = inv_tax.currency_id.round(inv_tax.amount)
        return inv_tax






class InpatientDeposit(models.Model):
    _name = 'inpatient.deposit'
    _rec_name = 'trans_no'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    tglproses = fields.Date(string="TglProses")
    patient_type = fields.Selection([('1', 'OP'), ('2', 'IP'), ('3', 'Emergency'), ('4', 'Daycare'), ('5', 'MCU/Pharmacy Issues Only(FO)'), ('6', 'Pharmacy (Direct)'), ('0', 'Both')], string='Patient Type', readonly=False, index=True)
    trans_type = fields.Char(string="Trans Type")
    trans_no = fields.Char(string="Trans No")
    trans_date = fields.Date(string="Trans Date")
    billing_id = fields.Many2one('sale.order.bill', string="Billing", required=False)
    billing_no = fields.Char(string="Billing No.")
    admission_id = fields.Many2one('sale.order',string="Admission", required=False)
    admission_no = fields.Char(string="Admission No.")
    patient_name = fields.Char(string="Patient Name")
    reference_no = fields.Char(string="Ref Deposit No.")
    payment_name = fields.Char(string="Payment Name")
    edc_machine = fields.Char(string="EDC Machine")
    partner_id = fields.Many2one('res.partner', string="Patient")
    amount = fields.Float(string="Amount")
    user_name = fields.Char(string="User Name")
    company_id = fields.Many2one('res.company',string="Company",)
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel','Cancelled')],string="Status",readonly=True,default='draft',track_visibility='always')
    journal_id = fields.Many2one('account.move',string="Journal")
    note = fields.Text(string="Notes")
    contact = fields.Char(string="Paid To")
    is_akasia = fields.Boolean(string="Is Akasia")

    # untuk send payload dari dhealth cuma kirim sync_type, auto-fill company_id
    @api.model
    def create(self, vals):
        result = super(InpatientDeposit, self).create(vals)
        
        # if self.env.context.get('updated'): return result
        # self = self.with_context(updated=True)

        if not vals.get('company_id') and vals.get('sync_type'):
            result.company_id = self.env['res.company'].sudo().search([('sync_type', '=', vals.get('sync_type'))],limit=1).id
        
        if not vals.get('patient_type') and vals.get('admission_id'):
            result.patient_type = result.admission_id.patient_type
            result.partner_id = result.admission_id.partner_id.id or None
        return result


    # @api.multi
    def unlink(self):
        for r in self:
            if r.state == 'confirmed':
                raise exceptions.ValidationError("Please cancel the record before delete")
        return super(InpatientDeposit, self).unlink()
    

    # @api.multi 
    def action_draft(self):
        for record in self:
            record.state = 'draft'


    # @api.multi 
    def action_cancel_call(self):
        for record in self:
            record.state = 'cancel'
            
            
    # @api.multi
    def action_confirm(self):
        journal_id = self.env['account.journal'].search([('name', 'ilike', '%IP Deposit Collection%'),('company_id', '=', self.company_id.id)],limit=1)
        account_partner = self.env['account.account'].search([('name', '=', 'Private Outstanding'),('company_id', '=', self.company_id.id)],limit=1)
        account = self.env['account.account'].search([('code', 'ilike', '%2103000000%'),('company_id', '=', self.company_id.id)],limit=1)
        account_credit = self.env['account.account'].search([('code', 'ilike', '%1104030100%'),('company_id', '=', self.company_id.id)],limit=1)
        account_other = self.env['account.account'].search([('code', 'ilike', '%7999990000%'),('company_id', '=', self.company_id.id)],limit=1)

        # 2022.01.31 
        # transaksi per 1-Feb-2022 automatic ambil dari konfigurasi res.company
        if (self.tglproses).strftime('%Y-%m-%d') > '2022-01-31':
            account_partner = self.company_id.receivable_cash_id 
            account = self.company_id.receivable_deposit_id

        line_ids = []
        if self.amount > 0:
            debit_vals = {
                'name':"IP " + str(self.trans_type) + ": " + str(self.patient_name) + " by " + str(self.user_name) + " on " + str((self.tglproses).strftime('%Y-%m-%d')) + "",
                'debit':abs(self.amount),
                'credit':0.0,
                'partner_id': self.partner_id.id or None,
                'account_id':account_partner.id,
            }
            line_ids.append((0, 0, debit_vals))
            
            credit_vals = {
                'name':"IP " + str(self.trans_type) + ": " + str(self.patient_name) + " by " + str(self.user_name) + " on " + str((self.tglproses).strftime('%Y-%m-%d')) + "",
                'debit':0.0,
                'credit':abs(self.amount),
                'partner_id': self.partner_id.id or None,
                'account_id':account.id,
            }
            line_ids.append((0, 0, credit_vals))
            

            # automatic jurnal balik untuk deposit refund ke mayapada
            # flagging by contact contain "MAYAPADA"
            # untuk refund deposit pasien dari MobileApps
            if "refund" in self.trans_type.lower():
                contact = str(self.contact).lower() or ""
                if "mayapada" in contact: 
                    debit_vals2 = {
                        'name': "IP " + str(self.trans_type) + ": " + str(self.patient_name) + " by " + str(self.user_name) + " to " + str(self.contact) + "",
                        'debit': abs(self.amount),
                        'credit': 0.0,
                        'partner_id': self.partner_id.id or None,
                        'account_id': account_other.id,
                    }
                    line_ids.append((0, 0, debit_vals2))
                    
                    credit_vals2 = {
                        'name': "IP " + str(self.trans_type) + ": " + str(self.patient_name) + " by " + str(self.user_name) + " to " + str(self.contact) + "",
                        'debit': 0.0,
                        'credit': abs(self.amount),
                        'partner_id': self.partner_id.id or None,
                        'account_id': account_credit.id,
                    }
                    line_ids.append((0, 0, credit_vals2))
            
            vals = {
                'journal_id':journal_id.id,
                'date':self.tglproses,
                'ref':"IP " + (self.trans_type or '') + ": " + (self.trans_no or '') + " - " + (self.admission_no or ''),
                'state':'draft',
                'line_ids': line_ids
            }

            move = self.env['account.move'].create(vals)
            move.action_post()
            self.journal_id = move.id
            self.state = 'confirmed'

        if self.amount < 0:
            debit_vals = {
                'name':"IP " + str(self.trans_type) + ": " + str(self.patient_name) + " by " + str(self.user_name) + " on " + str((self.tglproses).strftime('%Y-%m-%d')) + "",
                'debit':abs(self.amount),
                'credit':0.0,
                'partner_id': self.partner_id.id or None,
                'account_id':account.id,
            }
            line_ids.append((0, 0, debit_vals))

            credit_vals = {
                'name':"IP " + str(self.trans_type) + ":  " + str(self.patient_name) + " by " + str(self.user_name) + " on " + str((self.tglproses).strftime('%Y-%m-%d')) + "",
                'debit':0.0,
                'credit':abs(self.amount),
                'partner_id': self.partner_id.id or None,
                'account_id':account_partner.id,
            }
            line_ids.append((0, 0, credit_vals))

            # automatic jurnal balik untuk deposit refund ke mayapada
            # flagging by contact contain "MAYAPADA"
            # untuk refund deposit pasien dari MobileApps
            if "refund" in self.trans_type.lower():
                contact = str(self.contact).lower() or ""
                if "mayapada hospital" in contact:
                    debit_vals2 = {
                        'name': "IP " + str(self.trans_type) + ": " + str(self.patient_name) + " by " + str(self.user_name) + " to " + str(self.contact) + "",
                        'debit': abs(self.amount),
                        'credit': 0.0,
                        'partner_id': self.partner_id.id or None,
                        'account_id': account_credit.id,
                    }
                    line_ids.append((0, 0, debit_vals2))
                    
                    credit_vals2 = {
                        'name': "IP " + str(self.trans_type) + ": " + str(self.patient_name) + " by " + str(self.user_name) + " to " + str(self.contact) + "",
                        'debit': 0.0,
                        'credit': abs(self.amount),
                        'partner_id': self.partner_id.id or None,
                        'account_id': account_other.id,
                    }
                    line_ids.append((0, 0, credit_vals2))

            vals = {
                'journal_id':journal_id.id,
                'date':self.tglproses,
                'ref':"IP " + (self.trans_type or '') + ": " + (self.trans_no or '') + " - " + (self.admission_no or ''),
                'state':'draft',
                'line_ids': line_ids
            }
            move = self.env['account.move'].create(vals)
            self.journal_id = move.id
            move.action_post()
            self.state = 'confirmed'


            # 20210819 - update personal_balance pada billing
            if self.sync_id == 0 and self.trans_type in['Deposit Availed']:
                if self.billing_id:
                    if (self.billing_id.personal_receipt or 0) == 0:
                        self.billing_id.personal_balance = self.billing_id.personal_amount
                    self.billing_id.personal_receipt -= self.amount 
                    self.billing_id.personal_balance += self.amount

                if self.admission_id:
                    if (self.admission_id.personal_receipt or 0) == 0:
                        self.admission_id.personal_balance = self.admission_id.personal_amount
                    self.admission_id.personal_receipt -= self.amount 
                    self.admission_id.personal_balance += self.amount

        return True


    # @api.multi
    def action_cancel(self):
        if self.state == 'confirmed':
            self.state = 'draft'
            self.journal_id.button_cancel()
            self.journal_id.unlink()

            # 20210819 - update personal_balance pada billing
            if self.sync_id == 0 and self.trans_type in['Deposit Availed']:
                if self.billing_id:
                    self.billing_id.personal_receipt += self.amount 
                    self.billing_id.personal_balance -= self.amount
                if self.admission_id:
                    self.admission_id.personal_receipt += self.amount 
                    self.admission_id.personal_balance -= self.amount

    @api.model
    def _sync_inpatient_deposit_collect_wipro(self, sync_type='1'):
        import trollius as asyncio
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>',0)])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)],order='sync_date desc',limit=1).sync_date
        data = []
        date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
        query = """
            SELECT
                'draft' 'state',
                a.TransEntryID 'sync_id',
                a.tglproses 'tglproses',
                a.TransType 'trans_type',
                a.TransNo 'trans_no',
                a.DepositDate 'trans_date',
                a.AdmissionNumber 'admission_no',
                a.PatientName 'patient_name',
                a.ReferenceNo 'reference_no',
                a.PaymentName 'payment_name',
                a.EDCMachine 'edc_machine',
                a.Amount 'amount',
                a.UserName 'user_name',
                a.Contact 'contact'
            from dbo.VRP_OdooPatientDeposits a 
            where a.tglproses = '%s'
            """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), query)
        print (data)
        if not data:
            print ("No data available")
            return
        fields_without_id = tuple(
            key for key in self._fields
            if key != 'id' and 'property' not in key and 'ids' not in key
            and self._fields[key].required == True
            and self._fields[key].store == True)
        columns = tuple(
            key for key in data[0].keys()
            if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
        fields_without_id += columns
        columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
        fields = fields_without_id + ('id', )
        if columns:
            columns += ('id', )
        default_values = {}
        for field in fields:
            if field in columns:
                continue
            default = self._fields[field].default
            if callable(default):
                default = default(self)
            if isinstance(default, models.Model):
                default = default.id
            default_values[field] = default
        values = ''
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        @asyncio.coroutine
        def process_query(object):
            for value in default_values:
                object[value] = default_values[value]

            object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'] = sync_type
            object['company_id'] = self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
            value = False
            for field in fields:
                if value:
                    value += ', '
                else:
                    value = '('
                if field == 'id' and object['id'] == 'DEFAULT':
                    value += object['id']
                    continue
                if type(object[field]) in [str, unicode]:
                    string = object[field]
                    value += "'" + string.replace("'", "''") + "'"
                    continue
                value += sync.json(object[field])
            value += ')'
            return value
            #values += value

        loop = asyncio.get_event_loop()
        tasks = [asyncio.create_task(process_query(object)) for object in data]
        for result in loop.run_until_complete(asyncio.gather(*tasks)):
            if result:
                if values:
                    values += ', '
                values += result
        excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        columns = sync.remove_unicode(str(fields)).replace("'", "")
        columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        print (values)
        if not values:
            print ("No data available")
            return
        query = "INSERT into inpatient_deposit %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)
        self.env.cr.execute("""
            UPDATE inpatient_deposit AS a 
            SET company_id = b.id
            FROM res_company AS b 
            WHERE b.sync_type=a.sync_type
                AND a.company_id IS NULL
            """)

    @api.model
    def _sync_inpatient_deposit_collect_wipro_manual(self,sync_type='1',date_start='2019-01-01',date_end='2019-01-01'):
        import trollius as asyncio
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>',0)])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)],order='sync_date desc',limit=1).sync_date
        data = []
        date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
        query = """
            SELECT
                'draft' 'state',
                a.TransEntryID 'sync_id',
                a.tglproses 'tglproses',
                a.TransType 'trans_type',
                a.TransNo 'trans_no',
                a.DepositDate 'trans_date',
                a.AdmissionNumber 'admission_no',
                a.PatientName 'patient_name',
                a.ReferenceNo 'reference_no',
                a.PaymentName 'payment_name',
                a.EDCMachine 'edc_machine',
                a.Amount 'amount',
                a.UserName 'user_name',
                a.Contact 'contact'
            from dbo.VRP_OdooPatientDeposits a 
            where a.tglproses >= '%s' and a.tglproses <= '%s'
            """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), query)
        print (data)
        if not data:
            print ("No data available")
            return
        fields_without_id = tuple(
            key for key in self._fields
            if key != 'id' and 'property' not in key and 'ids' not in key
            and self._fields[key].required == True
            and self._fields[key].store == True)
        columns = tuple(
            key for key in data[0].keys()
            if key in self._fields and key not in fields_without_id) + (
                'sync_date', 'sync_type') if data else ()
        fields_without_id += columns
        columns += tuple(
            key for key in data[0].keys()
            if key in self._fields and key not in columns) if data else ()
        fields = fields_without_id + ('id', )
        if columns:
            columns += ('id', )
        default_values = {}
        for field in fields:
            if field in columns:
                continue
            default = self._fields[field].default
            if callable(default):
                default = default(self)
            if isinstance(default, models.Model):
                default = default.id
            default_values[field] = default
        values = ''
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        @asyncio.coroutine
        def process_query(object):
            for value in default_values:
                object[value] = default_values[value]

            object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'] = sync_type
            object['company_id'] = self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
            value = False
            for field in fields:
                if value:
                    value += ', '
                else:
                    value = '('
                if field == 'id' and object['id'] == 'DEFAULT':
                    value += object['id']
                    continue
                if type(object[field]) in [str, unicode]:
                    string = object[field]
                    value += "'" + string.replace("'", "''") + "'"
                    continue
                value += sync.json(object[field])
            value += ')'
            return value
            #values += value

        loop = asyncio.get_event_loop()
        tasks = [asyncio.create_task(process_query(object)) for object in data]
        for result in loop.run_until_complete(asyncio.gather(*tasks)):
            if result:
                if values:
                    values += ', '
                values += result
        excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        columns = sync.remove_unicode(str(fields)).replace("'", "")
        columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        print (values)
        if not values:
            print ("No data available")
            return
        query = "INSERT into inpatient_deposit %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)
        self.env.cr.execute("""
            UPDATE inpatient_deposit AS a 
            SET company_id = b.id
            FROM res_company AS b 
            WHERE b.sync_type=a.sync_type
                AND a.company_id IS NULL
            """)

    # @api.model
    # def _sync_inpatient_deposit_collect_wipro(self, sync_type='1'):
    #     import trollius as asyncio
    #     sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>',0)])}
    #     sync_date = self.sudo().search([('sync_type', '=', sync_type)],order='sync_date desc',limit=1).sync_date
    #     data = []
    #     date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
    #     query = """
    #         SELECT
    #             'draft' 'state',
    #             a.TransEntryID 'sync_id',
    #             a.tglproses 'tglproses',
    #             a.TransType 'trans_type',
    #             a.TransNo 'trans_no',
    #             a.DepositDate 'trans_date',
    #             a.AdmissionNumber 'admission_no',
    #             a.PatientName 'patient_name',
    #             a.ReferenceNo 'reference_no',
    #             a.PaymentName 'payment_name',
    #             a.EDCMachine 'edc_machine',
    #             a.Amount 'amount',
    #             a.UserName 'user_name',
    #             a.Contact 'contact'
    #         from dbo.VRP_OdooPatientDeposits a 
    #         where a.tglproses = '%s'
    #         """ % (date)
    #     data += sync.get_data(sync.servers.get(sync_type), query)
    #     print (data)
    #     if not data:
    #         print ("No data available")
    #         return
    #     fields_without_id = tuple(
    #         key for key in self._fields
    #         if key != 'id' and 'property' not in key and 'ids' not in key
    #         and self._fields[key].required == True
    #         and self._fields[key].store == True)
    #     columns = tuple(
    #         key for key in data[0].keys()
    #         if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
    #     fields_without_id += columns
    #     columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
    #     fields = fields_without_id + ('id', )
    #     if columns:
    #         columns += ('id', )
    #     default_values = {}
    #     for field in fields:
    #         if field in columns:
    #             continue
    #         default = self._fields[field].default
    #         if callable(default):
    #             default = default(self)
    #         if isinstance(default, models.Model):
    #             default = default.id
    #         default_values[field] = default
    #     values = ''
    #     now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    #     # @asyncio.coroutine --DR
    #     # def process_query(object):
    #     #     for value in default_values:
    #     #         object[value] = default_values[value]

    #     #     object['id'] = 'DEFAULT'
    #     #     object['sync_date'] = now
    #     #     object['sync_type'] = sync_type
    #     #     object['company_id'] = self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
    #     #     value = False
    #     #     for field in fields:
    #     #         if value:
    #     #             value += ', '
    #     #         else:
    #     #             value = '('
    #     #         if field == 'id' and object['id'] == 'DEFAULT':
    #     #             value += object['id']
    #     #             continue
    #     #         if type(object[field]) in [str, unicode]:
    #     #             string = object[field]
    #     #             value += "'" + string.replace("'", "''") + "'"
    #     #             continue
    #     #         value += sync.json(object[field])
    #     #     value += ')'
    #     #     return value
    #     #     #values += value

    #     # loop = asyncio.get_event_loop()
    #     # tasks = [asyncio.create_task(process_query(object)) for object in data]
    #     # for result in loop.run_until_complete(asyncio.gather(*tasks)):
    #     #     if result:
    #     #         if values:
    #     #             values += ', '
    #     #         values += result
    #     # excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
    #     # columns = sync.remove_unicode(str(fields)).replace("'", "")
    #     # columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
    #     # print values
    #     # if not values:
    #     #     print ("No data available")
    #     #     return
    #     # query = "INSERT into inpatient_deposit %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
    #     # print (query.encode('utf8'))
    #     # self.env.cr.execute(query)
    #     # self.env.cr.execute("""
    #     #     UPDATE inpatient_deposit AS a 
    #     #     SET company_id = b.id
    #     #     FROM res_company AS b 
    #     #     WHERE b.sync_type=a.sync_type
    #     #         AND a.company_id IS NULL
    #     #     """)

    # @api.model
    # def _sync_inpatient_deposit_collect_wipro_manual(self,sync_type='1',date_start='2019-01-01',date_end='2019-01-01'):
    #     import trollius as asyncio
    #     sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>',0)])}
    #     sync_date = self.sudo().search([('sync_type', '=', sync_type)],order='sync_date desc',limit=1).sync_date
    #     data = []
    #     date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
    #     query = """
    #         SELECT
    #             'draft' 'state',
    #             a.TransEntryID 'sync_id',
    #             a.tglproses 'tglproses',
    #             a.TransType 'trans_type',
    #             a.TransNo 'trans_no',
    #             a.DepositDate 'trans_date',
    #             a.AdmissionNumber 'admission_no',
    #             a.PatientName 'patient_name',
    #             a.ReferenceNo 'reference_no',
    #             a.PaymentName 'payment_name',
    #             a.EDCMachine 'edc_machine',
    #             a.Amount 'amount',
    #             a.UserName 'user_name',
    #             a.Contact 'contact'
    #         from dbo.VRP_OdooPatientDeposits a 
    #         where a.tglproses >= '%s' and a.tglproses <= '%s'
    #         """ % (date_start, date_end)
    #     data += sync.get_data(sync.servers.get(sync_type), query)
    #     print (data)
    #     if not data:
    #         print ("No data available")
    #         return
    #     fields_without_id = tuple(
    #         key for key in self._fields
    #         if key != 'id' and 'property' not in key and 'ids' not in key
    #         and self._fields[key].required == True
    #         and self._fields[key].store == True)
    #     columns = tuple(
    #         key for key in data[0].keys()
    #         if key in self._fields and key not in fields_without_id) + (
    #             'sync_date', 'sync_type') if data else ()
    #     fields_without_id += columns
    #     columns += tuple(
    #         key for key in data[0].keys()
    #         if key in self._fields and key not in columns) if data else ()
    #     fields = fields_without_id + ('id', )
    #     if columns:
    #         columns += ('id', )
    #     default_values = {}
    #     for field in fields:
    #         if field in columns:
    #             continue
    #         default = self._fields[field].default
    #         if callable(default):
    #             default = default(self)
    #         if isinstance(default, models.Model):
    #             default = default.id
    #         default_values[field] = default
    #     values = ''
    #     now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    #     # @asyncio.coroutine --DR
    #     # def process_query(object):
    #     #     for value in default_values:
    #     #         object[value] = default_values[value]

    #     #     object['id'] = 'DEFAULT'
    #     #     object['sync_date'] = now
    #     #     object['sync_type'] = sync_type
    #     #     object['company_id'] = self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
    #     #     value = False
    #     #     for field in fields:
    #     #         if value:
    #     #             value += ', '
    #     #         else:
    #     #             value = '('
    #     #         if field == 'id' and object['id'] == 'DEFAULT':
    #     #             value += object['id']
    #     #             continue
    #     #         if type(object[field]) in [str, unicode]:
    #     #             string = object[field]
    #     #             value += "'" + string.replace("'", "''") + "'"
    #     #             continue
    #     #         value += sync.json(object[field])
    #     #     value += ')'
    #     #     return value
    #     #     #values += value

    #     # loop = asyncio.get_event_loop()
    #     # tasks = [asyncio.create_task(process_query(object)) for object in data]
    #     # for result in loop.run_until_complete(asyncio.gather(*tasks)):
    #     #     if result:
    #     #         if values:
    #     #             values += ', '
    #     #         values += result
    #     # excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
    #     # columns = sync.remove_unicode(str(fields)).replace("'", "")
    #     # columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
    #     # print (values)
    #     # if not values:
    #     #     print ("No data available")
    #     #     return
    #     # query = "INSERT into inpatient_deposit %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
    #     # print (query.encode('utf8'))
    #     # self.env.cr.execute(query)
    #     # self.env.cr.execute("""
    #     #     UPDATE inpatient_deposit AS a 
    #     #     SET company_id = b.id
    #     #     FROM res_company AS b 
    #     #     WHERE b.sync_type=a.sync_type
    #     #         AND a.company_id IS NULL
    #     #     """)



    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(InpatientDeposit,self).get_view(view_id=view_id,view_type=view_type, **options)

        if view_type == 'tree':
            res['arch'] = """
                <tree string="Deposit Collection" decoration-muted="state == 'cancel'" decoration-info="state == 'draft'" delete="false">
                    <field name="tglproses"/>
                    <field name="trans_type"/>
                    <field name="trans_no"/>
                    <field name="patient_type"/>
                    <field name="admission_no" />
                    <field name="patient_name"/>
                    <field name="contact"/>
                    <field name="amount"/>
                    <field name="payment_name"/>
                    <field name="user_name" invisible="1"/>
                    <field name="state"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Deposit..">
                    <filter string="Draft" domain="[('state','=', 'draft')]" help="Draft"/>
                    <filter string="Confirm" domain="[('state','=', 'confirmed')]" help="Confirm"/>
                    <separator/>
                    <field name="trans_no"/>
                    <field name="contact"/>
                    <field name="user_name"/>
                    <field name="payment_name"/>
                    <field name="trans_type"/>
                    <field name="note"/>
                    <field name="edc_machine"/>
                    <field name="admission_id"/>
                </search>
            """
        
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


# Covering letter print wizard
class CoveringLetterWizard(models.TransientModel):
    _name = "account.coveringletter.wizard"

    @api.model
    def _get_company(self):
        return self.env.company.id

    @api.model 
    def _get_user(self):
        return self.env.user.id 

    company_id = fields.Many2one('res.company',string="Company", required=True, default=_get_company)
    user_id = fields.Many2one('res.users',string="Responsible", required=True, default=_get_user)
    letter_id = fields.Many2one('account.coveringletter', string="Letter ID")

    name = fields.Char(string="Letter No.")
    date = fields.Date(string="Letter Date")
    payer = fields.Many2one('res.partner', string="Payer Name")
    address_id = fields.Many2one('res.partner.address', string="Address")
    total_covering_letter = fields.Float(string="Letter Amount")

    remark1 = fields.Char(string="Remark 1st")
    remark2 = fields.Char(string="Remark 2nd")
    remark3 = fields.Char(string="Remark 3rd")

    # @api.model
    # def get_view(self,view_id=None, view_type='form', **options):
    #     res = super(CoveringLetterWizard,self).get_view(view_id=view_id,view_type=view_type, **options)
    #     if view_type == 'form':
    #         res['arch'] = """
    #             <form string="Print Kwitansi Wizard">
    #                 <group>
    #                     <group>
    #                         <field name="company_id"/>
    #                         <field name="user_id"/>
    #                         <field name="payer" domain="[('company_id','=', company_id),('insurance','=', True)]"/>
    #                         <field name="address_id"/>
    #                     </group>
    #                     <group>
    #                         <field name="letter_id" invisible="1"/>
    #                         <field name="name"/>
    #                         <field name="date"/>
    #                         <field name="total_covering_letter"/>
    #                     </group>
    #                 </group>

    #                 <group string="Tambahkan Catatan">
    #                     <field name="remark1"/>
    #                     <field name="remark2"/>
    #                     <field name="remark3"/>
    #                 </group> 

    #                 <footer>
    #                     <button name="print_kwitansi" type="object" string="Print Kwitansi" class="oe_highlight"/>
    #                 </footer>
    #             </form>
    #         """
    #     from lxml import etree
    #     doc = etree.XML(res['arch'])
    #     View = self.env['ir.ui.view'].sudo()
    #     res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
    #     return res

    # @api.multi
    def print_kwitansi(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/report/covering_letter_kwitansi?format=doc&id=' + str(self.id)
        action['target'] = 'new'
        return action


# AR Arcus
class ReceivableScrollReceiptCashier(models.Model):
    _name = 'receivable.scroll.receipt.cashier'
    _rec_name = 'bill_no'
    _description = 'Receivable Scroll Receipt Cashier'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
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
    
    cutoff_date = fields.Date(string='Cutoff Date')
    company_id = fields.Many2one('res.company',string="Company",required=True,readonly=True,default=_get_company)
    # odoo_tpa_id = fields.Many2one('res.partner', string="Odoo Tpa")
    # odoo_payor_id = fields.Many2one('res.partner', string="Odoo Payer")
    # payor_id = fields.Char(string='Payor ID')
    # payor_code = fields.Char(string='Payor Code')
    # payor_name = fields.Char(string='Payor Name')
    transaction_datetime = fields.Datetime(string='Transaction Datetime')
    transaction_type = fields.Char(string='Transaction Type')
    user_name = fields.Char(string='User Name')
    payment_type = fields.Char(string='Payment Type')
    facility_name = fields.Char(string='Facility Name')
    edc_machine = fields.Char(string='EDC Machine')
    total_collect = fields.Float(string='Total Collect')
    note = fields.Char(string='Note')
    partner_id = fields.Char(string='Partner ID')
    patient_mrid = fields.Char(string='Patient MRID')
    patient_name = fields.Char(string='Patient Name')
    admission_id = fields.Char(string='Admission ID')
    admission_no = fields.Char(string='Admission No')
    bill_no = fields.Char(string='Bill No')
    # state = fields.Char(string='State')
    state = fields.Selection([
        ('confirm', 'Confirm'),
        ('cancel', 'Cancel')
    ], string='State', default='confirm', required=True)

    odoo_admission_id = fields.Many2one('sale.order', string="Odoo Admission ID")
    admission_date= fields.Datetime(string='Admission Date')
    patient_id = fields.Char(string='Patient ID')
    patient_ref_no = fields.Char(string='Patient Ref No')
    odoo_patient_id = fields.Many2one('res.partner', string="Odoo Patient ID")
    bill_id = fields.Char(string='Bill ID')
    odoo_bill_id = fields.Many2one('sale.order.bill', string="Odoo Bill ID")
    bill_date= fields.Datetime(string='Bill Date')
    tpa_id = fields.Char(string='TPA ID')
    odoo_tpa_id = fields.Many2one('res.partner', string="Odoo TPA ID")
    tpa_code = fields.Char(string='TPA Code')
    tpa_name = fields.Char(string='TPA Name')
    payor_id = fields.Char(string='Payor ID')
    odoo_payor_id = fields.Many2one('res.partner', string="Odoo Payor ID")
    payor_code = fields.Char(string='Payor Code')
    payor_name = fields.Char(string='Payor Name')
    payor_type = fields.Char(string='Payor Type')
    transaction_no = fields.Char(string='Transaction No')
    transaction_date = fields.Datetime(string='Transaction Date')
    odoo_payment_id = fields.Many2one('receivable.payment.mode', string='Odoo Payment ID')
    payment_id = fields.Char(string='Payment ID')
    deposit_id = fields.Char(string='Deposit ID')
    odoo_deposit_id = fields.Many2one('receivable.patient.deposit', string='Odoo Deposit ID')
    deposit_no = fields.Char(string='Deposit No')
    deposit_date = fields.Datetime(string='Deposit Date')
    deposit_adjust_id = fields.Char(string='Deposit Adjust ID')
    odoo_deposit_adjust_id = fields.Many2one('receivable.patient.deposit', string='Odoo Deposit Adjust ID')
    deposit_adjust_no = fields.Char(string='Deposit Adjust No')
    deposit_adjust_date = fields.Datetime(string='Deposit Adjust Date')
    creditnote_id = fields.Char(string='Creditnote ID')
    creditnote_no = fields.Char(string='Creditnote No')
    creditnote_date = fields.Datetime(string='Creditnote Date')
    creditnote_adjust_id = fields.Char(string='Creditnote ID')
    creditnote_adjust_no = fields.Char(string='Creditnote No')
    creditnote_adjust_date = fields.Datetime(string='Creditnote Date')
    reference = fields.Char(string='Reference')
    bank_id = fields.Char(string='Bank ID')
    odoo_bank_id = fields.Many2one('receivable.bank.name', string='Odoo Bank ID')
    bank_name = fields.Char(string='Bank Name')
    bank_date = fields.Char(string='Bank Date')
    remark = fields.Char(string='Remark')
    notes = fields.Char(string='Notes')
    amount = fields.Float(string='Amount')    

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReceivableScrollReceiptCashier,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Scroll Receipt Cashier" delete="0" edit="0" create="0">
                    <header>
                        <field name="state" widget="statusbar" modifiers="{'readonly': true}"/>
                    </header>
                    <sheet>
                        <group>
                            <group>
                                <field name="cutoff_date" />
                                <field name="transaction_datetime" />
                                <field name="transaction_type" />
                                <field name="user_name" />
                                <field name="payment_type" />
                                <field name="odoo_payment_id" />
                                <field name="facility_name" />
                                <field name="edc_machine" />
                                <field name="total_collect" />
                                <field name="patient_id"/>
                                <field name="patient_ref_no"/>
                                <field name="bill_id"/>
                                <field name="odoo_bill_id"/>
                                <field name="bill_date"/>
                                <field name="tpa_id"/>
                                <field name="odoo_tpa_id"/>
                                <field name="tpa_code"/>
                                <field name="tpa_name"/>
                                <field name="payor_id"/>
                                <field name="odoo_payor_id"/>
                                <field name="payor_name"/>
                                <field name="payor_code"/>
                                <field name="payor_type"/>
                                <field name="transaction_no"/>
                                <field name="transaction_date"/>
                                
                            </group>
                            <group>
                                <field name="company_id" />
                                <field name="partner_id" />
                                <field name="patient_mrid" />
                                <field name="patient_name" />
                                <field name="odoo_admission_id"/>
                                <field name="admission_id" />
                                <field name="admission_no" />
                                <field name="admission_date"/>
                                <field name="bill_no" />
                                <field name="payment_id"/>
                                <field name="deposit_id"/>
                                <field name="odoo_deposit_id"/>
                                <field name="deposit_no"/>
                                <field name="deposit_date"/>
                                <field name="deposit_adjust_id"/>
                                <field name="odoo_deposit_adjust_id"/>
                                <field name="deposit_adjust_no"/>
                                <field name="deposit_adjust_date"/>
                                <field name="creditnote_id"/>
                                <field name="creditnote_no"/>
                                <field name="creditnote_date"/>
                                <field name="creditnote_adjust_id"/>
                                <field name="creditnote_adjust_no"/>
                                <field name="creditnote_adjust_date"/>
                                <field name="reference"/>
                                <field name="bank_id"/>
                                <field name="odoo_bank_id"/>
                                <field name="bank_name"/>
                                <field name="bank_date"/>
                                <field name="remark"/>
                                <field name="note" />
                            </group>
                        </group>  
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" />
                                        <field name="sync_id_api" readonly="1" />
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
                <tree string="Scroll Receipt Cashier" delete="false" create="false" decoration-danger="state == 'cancel'" decoration-info="state == 'draft'" decoration-success="state=='confirm'">
                    <field name="cutoff_date"/>
                    <field name="transaction_datetime"/>
                    <field name="transaction_type"/>
                    <field name="patient_mrid"/>
                    <field name="patient_name"/>
                    <field name="bill_no"/>
                    <field name="payment_type"/>
                    <field name="note"/>
                    <field name="amount"/>
                    <field name="state"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Scroll Receipt Cashier Search">
                    <field name="user_name"/>
                    <field name="facility_name"/>
                    <field name="admission_no"/>
                    <field name="bill_no"/>
                    <field name="note"/>
                    <field name="patient_name"/>
                </search>
            """

        elif view_type == 'pivot':
            res['arch'] = """
                <pivot string="Scroll Receipt Cashier">
                    <field name="amount" type="measure"/>
                </pivot>
           """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


    @api.model
    def _create_journal_arcus_scroll_cashier(self, sync_type='1', date=False):
        if not date:
            date = '' + (tools.datetime.now() + tools.timedelta(hours=7)-tools.timedelta(days=1)).strftime('%Y-%m-%d')
        company = self.env['res.company'].search([('sync_type', '=', sync_type)], limit=1)
        company_id = company.id 
        
        query = """
            SELECT 
                sol.direction, sol.amount, sol.account_label, 
                sol.account_credit_id, sol.account_debit_id, 
                (CASE WHEN sol.direction < 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_debit_id,
                (CASE WHEN sol.direction = 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_credit_id
            FROM view_account_arcus_scroll_cashier sol 
            WHERE sol.tglproses = '{date}'
                AND sol.sync_type = '{sync_type}'
                AND sol.amount <> 0
            """ .format(date=date, sync_type=sync_type)
        self.env.cr.execute(query)
        lines = self.env.cr.dictfetchall()
        if not lines:
            print ("There are no lines to make journal")
            return
        move_lines = []
        for line in lines:
            # validasi COA 
            if not line['account_credit_id']:
                raise exceptions.ValidationError("Please mapping credit account")
            if not line['account_debit_id']:
                raise exceptions.ValidationError("Please mapping debit account")

            
        journal_id = self.env['account.journal'].search([('name', 'ilike', 'Arcus Scroll Cashier'),('company_id', '=', company_id)],limit=1).id
        
        if journal_id:
            self.env['account.move'].create({'journal_id':journal_id,'line_ids':move_lines,'date':date, 'ref': 'ARCUS SCROLL CASHIER as ' + str(date)})



class ReceivablePatientDeposit(models.Model):
    _name = 'receivable.patient.deposit'
    _rec_name = 'trans_no'
    _description = 'Receivable Patient Deposit'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    cutoff_date = fields.Date(string='Cutoff Date')
    # odoo_tpa_id = fields.Many2one('res.partner', string="Odoo Tpa")
    # odoo_payor_id = fields.Many2one('res.partner', string="Odoo Payer")
    # payor_id = fields.Char(string='Payor ID.')
    # payor_code = fields.Char(string='Payor Code')
    # payor_name = fields.Char(string='Payor Name')
    cutoff_date = fields.Date(string='Cutoff Date')
    trans_datetime = fields.Datetime(string='Transaction Date')
    trans_no = fields.Char(string='Transaction No.')
    user_name = fields.Char(string='User Name')
    trans_type = fields.Char(string='Transaction Type')
    reference_no = fields.Char(string='Reference No.')
    partner_id = fields.Char(string='Partner ID.')
    odoo_partner_id = fields.Many2one('res.partner', string="Odoo Partner.")
    patient_mrid = fields.Char(string='Patient MRID')
    patient_name = fields.Char(string='Patient Name')
    admission_id = fields.Char(string='Admission ID.')
    odoo_admission_id = fields.Many2one('sale.order', string="Odoo Admission.")
    admission_no = fields.Char(string='Admission No.')
    bill_no = fields.Char(string='Bill No.')
    payment_name = fields.Char(string='Payment Name')
    edc_machine = fields.Char(string='EDC Machine')
    amount = fields.Float(string='Amount')
    note = fields.Char(string='Note')
    patient_type = fields.Selection([('1','OP'),('2','IP'),('3','Emergency'),('4','DayCare'),('5','MCU'),('6','Pharmacy')], string='Patient Type')
    state = fields.Selection([
        ('confirm', 'Confirm'),
        ('cancel', 'Cancel')
    ], string='State', default='confirm', required=True)
    trans_date = fields.Datetime(string="Transaction Date")
    admission_date = fields.Datetime(string="Admission Date")
    bill_date = fields.Datetime(string="Billing Date")
    payment_id = fields.Char(string="Payment ID")
    odoo_payment_id = fields.Many2one('receivable.payment.mode', string="Odoo Payment")
    odoo_bank_id = fields.Many2one('receivable.bank.name', string="Bank ID.")
    bank_id = fields.Char(string='Bank ID')
    bank_name = fields.Char(string='Bank Name')
    bank_account = fields.Char(string='Bank Account')
    bank_date = fields.Datetime(string="Bank Date")
    bill_id = fields.Char(string="Billing ID.")
    odoo_bill_id = fields.Many2one('sale.order.bill', string="Odoo Billing ID")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReceivablePatientDeposit,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Patient Deposit" delete="0" create="0" edit="0">
                    <header>
                        <field name="state" widget="statusbar" modifiers="{'readonly': true}"/>
                    </header>
                    <sheet>
                        <group>
                            <group>
                                <field name="cutoff_date" />
                                <field name="trans_date" />
                                <field name="trans_datetime" />
                                <field name="trans_no" />
                                <field name="user_name" />
                                <field name="trans_type" />
                                <field name="reference_no" />
                                <field name="odoo_partner_id" />
                                <field name="partner_id" />
                                <field name="patient_name" />
                                <field name="patient_mrid" />
                                <field name="patient_type" />
                            </group>
                            <group>
                                <field name="odoo_admission_id" />
                                <field name="admission_id" />
                                <field name="admission_no" />
                                <field name="admission_date" />
                                <field name="bill_id" />
                                <field name="odoo_bill_id" />
                                <field name="bill_no" />
                                <field name="bill_date" />
                                <field name="payment_name" />
                                <field name="payment_id" />
                                <field name="odoo_payment_id" />

                                <field name="odoo_bank_id" />
                                <field name="bank_id" />
                                <field name="bank_name" />
                                <field name="bank_account" />
                                <field name="bank_date" />

                                <field name="edc_machine" />
                                <field name="amount" />
                                <field name="note" />
                            </group>
                        </group>    
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" />
                                        <field name="sync_id_api" readonly="1" />
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
                <tree string="Patient Deposit" delete="false" create="false" decoration-danger="state == 'cancel'" decoration-info="state == 'draft'" decoration-success="state=='confirm'">
                    <field name="cutoff_date"/>
                    <field name="trans_type"/>
                    <field name="trans_no"/>
                    <field name="reference_no"/>
                    <field name="patient_mrid"/>
                    <field name="patient_name"/>
                    <field name="bill_no"/>
                    <field name="amount"/>
                    <field name="state"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Patient Deposit Search">
                    <field name="reference_no"/>
                    <field name="trans_no"/>
                    <field name="note"/>
                    <field name="patient_name"/>
                </search>
            """

        elif view_type == 'pivot':
            res['arch'] = """
                <pivot string="Patient Deposit">
                    <field name="amount" type="measure"/>
                </pivot>
           """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


    @api.model
    def _create_journal_arcus_patient_deposit(self, sync_type='1', date=False):
        if not date:
            date = '' + (tools.datetime.now() + tools.timedelta(hours=7)-tools.timedelta(days=1)).strftime('%Y-%m-%d')
        company = self.env['res.company'].search([('sync_type', '=', sync_type)], limit=1)
        company_id = company.id 
        
        query = """
            SELECT 
                sol.direction, sol.amount, sol.account_label, 
                sol.account_credit_id, sol.account_debit_id, 
                (CASE WHEN sol.direction < 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_debit_id,
                (CASE WHEN sol.direction = 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_credit_id
            FROM view_account_arcus_patient_deposit sol 
            WHERE sol.tglproses = '{date}'
                AND sol.sync_type = '{sync_type}'
                AND sol.amount <> 0
            """ .format(date=date, sync_type=sync_type)
        self.env.cr.execute(query)
        lines = self.env.cr.dictfetchall()
        if not lines:
            print ("There are no lines to make journal")
            return
        move_lines = []
        for line in lines:
            # validasi COA 
            if not line['account_credit_id']:
                raise exceptions.ValidationError("Please mapping credit account")
            if not line['account_debit_id']:
                raise exceptions.ValidationError("Please mapping debit account")

            
        journal_id = self.env['account.journal'].search([('name', 'ilike', 'Arcus Patient Deposit'),('company_id', '=', company_id)],limit=1).id
        
        if journal_id:
            self.env['account.move'].create({'journal_id':journal_id,'line_ids':move_lines,'date':date, 'ref': 'ARCUS PATIENT DEPOSIT as ' + str(date)})



    
class ReceivableInvoiceLetter(models.Model):
    _name = 'receivable.invoice.letter'
    _rec_name = 'invoice_no'
    _description = 'Receivable Invoice Letter'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    cutoff_date = fields.Date(string='Cutoff Date')
    odoo_tpa_id = fields.Many2one('res.partner', string="Odoo Tpa")
    odoo_payor_id = fields.Many2one('res.partner', string="Odoo Payer")
    payor_id = fields.Char(string='Payor ID')
    payor_code = fields.Char(string='Payor Code')
    payor_name = fields.Char(string='Payor Name')
    tpa_id = fields.Char(string='Tpa ID')
    tpa_code = fields.Char(string='Tpa Code')
    tpa_name = fields.Char(string='Tpa Name')
    payor_type = fields.Char(string='Payor Type')
    invoice_no = fields.Char(string='Invoice No')
    invoice_date = fields.Date(string='Invoice Date')
    invoice_sent = fields.Date(string='Invoice Sent Date')
    invoice_maturity = fields.Date(string='Invoice Maturity Date')
    amount_total = fields.Float(string='Total Amount')
    amount_receipt = fields.Float(string='Receipt Amount')
    amount_writeoff = fields.Float(string='Writeoff Amount')
    amount_balance = fields.Float(string='Balance Amount')
    bill_id = fields.Char(string='Bill ID')
    bill_type = fields.Char(string='Bill Type')
    bill_no = fields.Char(string='Bill No')
    bill_date = fields.Datetime(string='Bill Date')
    admission_id = fields.Char(string='Admission ID')
    admission_no = fields.Char(string='Admission No')
    admission_date = fields.Datetime(string='Admission Date')
    patient_id = fields.Char(string='Patient ID')
    patient_mrid = fields.Char(string='Patient MRID')
    patient_ref_no = fields.Char(string='Patient Ref No')
    patient_name = fields.Char(string='Patient Name')
    payor_coverage = fields.Float(string='Payor Coverage')
    payor_invoice = fields.Float(string='Payor Invoice')
    payor_writeoff = fields.Float(string='Payor Writeoff')
    payor_balance = fields.Float(string='Payor Balance')
    # state = fields.Char(string='State')
    state = fields.Selection([
        ('confirm', 'Confirm'),
        ('cancel', 'Cancel')
    ], string='State', default='confirm', required=True)

    invoice_id = fields.Char(string='Invoice ID')
    invoice_crediterm = fields.Char(string='Invoice Crediterm')
    invoice_total = fields.Float(string='Invoice Total')
    odoo_bill_id = fields.Many2one('sale.order.bill', string="Odoo Bill ID")
    aggreement_id = fields.Char(string='Aggreement ID')
    aggreement_code = fields.Char(string='Aggreement Code')
    aggreement_name = fields.Char(string='Aggreement Name')
    odoo_admission_id = fields.Many2one('sale.order', string="Odoo Admission ID")
    odoo_patient_id = fields.Many2one('res.partner', string="Odoo Patient ID")
    status = fields.Char(string='Status')
    user_name = fields.Char(string='User Name')
    facility_name = fields.Char(string='Facility Name')

    # payment_type = fields.Selection([
    #     ('Cash', 'Direct Cash Payment'),
    #     ('BankTransfer', 'Direct Bank Transfer Payment'),
    #     ('CreditCard', 'Direct Credit Card Payment'),
    #     ('DebitCard', 'Debit Card Payment'),
    #     ('Voucher', 'Voucher Payment'),
    #     ('CreditNote', 'Accrued Credit Note'),
    #     ('Deposit', 'Company Deposit/Advance')
    # ], string='Payment Type', required=True)
    # deposit_no = fields.Char(string='Deposit No.')
    # deposit_date = fields.Datetime(string='Deposit Date')
    # creditnote_no = fields.Char(string='Credit Note No.')
    # creditnote_date = fields.Datetime(string='Credit Note Date')
    # bank_name = fields.Char(string='Bank Name')
    # reference = fields.Char(string='Reference')
    # amount = fields.Float(string='Amount', required=True)
    # notes = fields.Char(string='Notes')

    # @api.constrains('payment_type', 'deposit_no', 'deposit_date', 'creditnote_no', 'creditnote_date', 'bank_name')
    # def _check_payment_details(self):
    #     for record in self:
    #         if record.payment_type == 'Deposit':
    #             if not record.deposit_no or not record.deposit_date:
    #                 raise ValidationError("Deposit No. and Deposit Date must be filled for payment type 'Deposit'.")
    #         elif record.payment_type == 'CreditNote':
    #             if not record.creditnote_no or not record.creditnote_date:
    #                 raise ValidationError("Credit Note No. and Credit Note Date must be filled for payment type 'CreditNote'.")
    #         elif record.payment_type == 'BankTransfer':
    #             if not record.bank_name:
    #                 raise ValidationError("Bank Name must be filled for payment type 'BankTransfer'.")

    
    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReceivableInvoiceLetter,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Invoice Letter" delete="0" edit="0" create="0">
                    <header>
                        <field name="state" widget="statusbar" modifiers="{'readonly': true}"/>
                    </header>
                    <sheet>
                        <group>
                            <group>
                                <field name="cutoff_date" />
                                <field name="payor_id" />
                                <field name="payor_code" />
                                <field name="payor_name" />
                                <field name="payor_type" />
                                <field name="invoice_id" />
                                <field name="invoice_crediterm" />
                                <field name="invoice_total" />
                                <field name="invoice_no" />
                                <field name="invoice_date" />
                                <field name="invoice_sent" />
                                <field name="invoice_maturity" />
                                <field name="amount_total" />
                                <field name="amount_receipt" />
                                <field name="amount_writeoff" />
                                <field name="amount_balance" />
                                <field name="odoo_tpa_id" />
                                <field name="odoo_payor_id" />
                            </group>
                            <group>
                                <field name="aggreement_id"/>
                                <field name="aggreement_code"/>
                                <field name="aggreement_name"/>
                                <field name="odoo_bill_id" />
                                <field name="bill_id" />
                                <field name="bill_type" />
                                <field name="bill_no" />
                                <field name="bill_date" />
                                <field name="odoo_admission_id"/>
                                <field name="admission_id" />
                                <field name="admission_no" />
                                <field name="admission_date" />
                                <field name="odoo_patient_id"/>
                                <field name="patient_id" />
                                <field name="patient_mrid" />
                                <field name="patient_ref_no" />
                                <field name="patient_name" />
                                <field name="payor_coverage" />
                                <field name="payor_invoice" />
                                <field name="payor_writeoff" />
                                <field name="payor_balance" />
                                <field name="status"/>
                                <field name="user_name"/>
                                <field name="facility_name"/>
                            </group>
                        </group>    
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" />
                                        <field name="sync_id_api" readonly="1" />
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
                <tree string="Invoice Claim" delete="0" create="0" decoration-danger="state == 'cancel'" decoration-info="state == 'draft'" decoration-success="state=='confirm'">
                    <field name="cutoff_date" />
                    <field name="invoice_no"/>
                    <field name="invoice_date"/>
                    <field name="patient_mrid"/>
                    <field name="patient_name"/>
                    <field name="bill_no"/>
                    <field name="payor_coverage"/>
                    <field name="payor_invoice"/>
                    <field name="invoice_total"/>
                    <field name="state"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Invoice Letter Search">
                    <field name="invoice_no"/>
                    <field name="bill_no"/>
                    <field name="patient_name"/>
                </search>
            """

        elif view_type == 'pivot':
            res['arch'] = """
                <pivot string="Invoice Letter">
                    <field name="payor_balance" type="measure"/>
                </pivot>
           """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


    @api.model
    def _create_journal_arcus_invoice_letter(self, sync_type='1', date=False):
        if not date:
            date = '' + (tools.datetime.now() + tools.timedelta(hours=7)-tools.timedelta(days=1)).strftime('%Y-%m-%d')
        company = self.env['res.company'].search([('sync_type', '=', sync_type)], limit=1)
        company_id = company.id 
        
        query = """
            SELECT 
                sol.direction, sol.amount, sol.account_label, 
                sol.account_credit_id, sol.account_debit_id, 
                (CASE WHEN sol.direction < 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_debit_id,
                (CASE WHEN sol.direction = 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_credit_id
            FROM view_account_arcus_invoice_letter sol 
            WHERE sol.tglproses = '{date}'
                AND sol.sync_type = '{sync_type}'
                AND sol.amount <> 0
            """ .format(date=date, sync_type=sync_type)
        self.env.cr.execute(query)
        lines = self.env.cr.dictfetchall()
        if not lines:
            print ("There are no lines to make journal")
            return
        move_lines = []
        for line in lines:
            # validasi COA 
            if not line['account_credit_id']:
                raise exceptions.ValidationError("Please mapping credit account")
            if not line['account_debit_id']:
                raise exceptions.ValidationError("Please mapping debit account")

            
        journal_id = self.env['account.journal'].search([('name', 'ilike', 'Arcus Invoice Letter'),('company_id', '=', company_id)],limit=1).id
        
        if journal_id:
            self.env['account.move'].create({'journal_id':journal_id,'line_ids':move_lines,'date':date, 'ref': 'ARCUS INVOICE LETTER as ' + str(date)})




class ReceivableCreditNote(models.Model):
    _name = 'receivable.credit.note'
    _rec_name = 'creditnote_no'
    _description = 'Receivable Credit Note'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    cutoff_date = fields.Date(string='Cutoff Date')
    odoo_tpa_id = fields.Many2one('res.partner', string="Odoo Tpa")
    odoo_payor_id = fields.Many2one('res.partner', string="Odoo Payer")
    payor_id = fields.Char(string='Payor ID')
    payor_code = fields.Char(string='Payor Code')
    payor_name = fields.Char(string='Payor Name')
    payor_type = fields.Char(string='Payor Type')
    tpa_id = fields.Char(string='Tpa ID')
    tpa_code = fields.Char(string='Tpa Code')
    tpa_name = fields.Char(string='Tpa Name')
    creditnote_no = fields.Char(string='Credit Note No')
    creditnote_date = fields.Date(string='Credit Note Date')
    creditnote_type = fields.Char(string='Credit Note Type')
    creditnote_remark = fields.Char(string='Credit Note Remark')
    creditnote_reason = fields.Char(string='Credit Note Reason')
    odoo_admission_id = fields.Many2one('sale.order', string="Odoo Admission", index=True)
    admission_id = fields.Char(string='Admission ID')
    admission_no = fields.Char(string='Admission No')
    admission_date = fields.Datetime(string='Admission Date')
    odoo_patient_id = fields.Many2one('res.partner', string="Odoo Patient", index=True)
    patient_id = fields.Char(string='Patient ID')
    patient_mrid = fields.Char(string='Patient MRID')
    patient_ref_no = fields.Char(string='Patient Ref No')
    patient_name = fields.Char(string='Patient Name')
    odoo_bill_id = fields.Many2one('sale.order.bill', string="Odoo Billing", index=True)
    bill_id = fields.Char(string='Bill ID')
    # bill_type = fields.Char(string='Bill Type')
    bill_type = fields.Selection([
        ('CR', 'Credit'),
        ('CS', 'Cash')
    ], string='Bill Type', required=True)
    bill_no = fields.Char(string='Bill No')
    bill_date = fields.Datetime(string='Bill Date')
    order_no = fields.Char(string='Order No')
    order_date = fields.Datetime(string='Order Date')
    order_line_seq = fields.Char(string='Order Line Seq')
    service_id = fields.Char(string='Service ID')
    service_name = fields.Char(string='Service Name')
    department_id = fields.Char(string='Department ID')
    department_name = fields.Char(string='Department Name')
    product_id = fields.Char(string='Product ID')
    product_name = fields.Char(string='Product Name')
    quantity = fields.Float(string='Quantity')
    percentage = fields.Float(string='Percentage')
    amount = fields.Float(string='Amount')
    # state = fields.Char(string='State')
    state = fields.Selection([
        ('confirm', 'Confirm'),
        ('cancel', 'Cancel')
    ], string='State', default='confirm', required=True)
    reference = fields.Char(string='Reference')
    odoo_bank_id = fields.Many2one('receivable.bank.name', string="Odoo Bank", index=True)
    bank_id = fields.Char(string='Bank ID')
    bank_name = fields.Char(string='Bank Name')
    bank_date = fields.Datetime(string='Bank Date')
    odoo_payment_id = fields.Many2one('receivable.payment.mode', string="Odoo Payment", index=True)
    payment_id = fields.Char(string='Payment ID')
    payment_type = fields.Char(string='Payment Type')
    payment_date = fields.Datetime(string='Payment Date')

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReceivableCreditNote,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Credit Note" delete="0" create="0" edit="0">
                    <header>
                        <field name="state" widget="statusbar" modifiers="{'readonly': true}"/>
                    </header>
                    <sheet>
                        <group>
                            <group>
                                <field name="cutoff_date" />
                                <field name="payor_id" />
                                <field name="payor_code" />
                                <field name="payor_name" />
                                <field name="payor_type" />
                                <field name="creditnote_no" />
                                <field name="creditnote_date" />
                                <field name="creditnote_type" />
                                <field name="creditnote_remark" />
                                <field name="creditnote_reason" />
                                <field name="admission_id" />
                                <field name="admission_no" />
                                <field name="admission_date" />
                                <field name="patient_id" />
                                <field name="patient_mrid" />
                                <field name="patient_ref_no" />
                                <field name="patient_name" />
                                <field name="odoo_payor_id" />
                                <field name="odoo_patient_id" />
                                <field name="odoo_admission_id" />
                            </group>
                            <group>
                                <field name="odoo_tpa_id" />
                                <field name="tpa_id" />
                                <field name="tpa_code" />
                                <field name="tpa_name" />
                                <field name="odoo_bill_id" />
                                <field name="bill_id" />
                                <field name="bill_type" />
                                <field name="bill_no" />
                                <field name="bill_date" />
                                <field name="order_no" />
                                <field name="order_date" />
                                <field name="order_line_seq" />
                                <field name="service_id" />
                                <field name="service_name" />
                                <field name="department_id" />
                                <field name="department_name" />
                                <field name="product_id" />
                                <field name="product_name" />
                                <field name="quantity" />
                                <field name="percentage" />
                                <field name="amount" />
                            </group>
                        </group>

                        <group>
                            <group>
                                <field name="odoo_payment_id" />
                                <field name="payment_id" />
                                <field name="payment_type" />
                                <field name="payment_date" />
                            </group>
                            <group>
                                <field name="odoo_bank_id" />
                                <field name="bank_id" />
                                <field name="bank_name" />
                                <field name="bank_date" />
                            </group>
                        </group>
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" />
                                        <field name="sync_id_api" readonly="1" />
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
                <tree string="Credit Note" delete="false" create="false" decoration-danger="state == 'cancel'" decoration-info="state == 'draft'" decoration-success="state=='confirm'">
                    <field name="cutoff_date"/>
                    <field name="creditnote_no"/>
                    <field name="creditnote_type"/>
                    <field name="creditnote_reason"/>
                    <field name="patient_name"/>
                    <field name="bill_no"/>
                    <field name="amount"/>
                    <field name="state"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Credit Note Search">
                    <field name="creditnote_no"/>
                    <field name="bill_no"/>
                    <field name="patient_name"/>
                </search>
            """

        elif view_type == 'pivot':
            res['arch'] = """
                <pivot string="Credit Note">
                    <field name="amount" type="measure"/>
                </pivot>
           """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


    @api.model
    def _create_journal_arcus_credit_note(self, sync_type='1', date=False):
        if not date:
            date = '' + (tools.datetime.now() + tools.timedelta(hours=7)-tools.timedelta(days=1)).strftime('%Y-%m-%d')
        company = self.env['res.company'].search([('sync_type', '=', sync_type)], limit=1)
        company_id = company.id 
        
        query = """
            SELECT 
                sol.direction, sol.amount, sol.account_label, 
                sol.account_credit_id, sol.account_debit_id, 
                (CASE WHEN sol.direction < 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_debit_id,
                (CASE WHEN sol.direction = 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_credit_id
            FROM view_account_arcus_credit_note sol 
            WHERE sol.tglproses = '{date}'
                AND sol.sync_type = '{sync_type}'
                AND sol.amount <> 0
            """ .format(date=date, sync_type=sync_type)
        self.env.cr.execute(query)
        lines = self.env.cr.dictfetchall()
        if not lines:
            print ("There are no lines to make journal")
            return
        move_lines = []
        for line in lines:
            # validasi COA 
            if not line['account_credit_id']:
                raise exceptions.ValidationError("Please mapping credit account")
            if not line['account_debit_id']:
                raise exceptions.ValidationError("Please mapping debit account")

            
        journal_id = self.env['account.journal'].search([('name', 'ilike', 'Arcus Credit Note'),('company_id', '=', company_id)],limit=1).id
        
        if journal_id:
            self.env['account.move'].create({'journal_id':journal_id,'line_ids':move_lines,'date':date, 'ref': 'ARCUS CREDIT NOTE as ' + str(date)})


    

class ReceivableWriteoff(models.Model):
    _name = 'receivable.writeoff'
    _rec_name = 'writeoff_no'
    _description = 'Receivable Write-Off'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    cutoff_date = fields.Date(string='Cutoff Date')
    odoo_tpa_id = fields.Many2one('res.partner', string="Odoo Tpa")
    odoo_payor_id = fields.Many2one('res.partner', string="Odoo Payer")
    payor_id = fields.Char(string='Payor ID')
    payor_code = fields.Char(string='Payor Code')
    payor_name = fields.Char(string='Payor Name')
    payor_type = fields.Char(string='Payor Type')
    tpa_id = fields.Char(string='Tpa ID')
    tpa_code = fields.Char(string='Tpa Code')
    tpa_name = fields.Char(string='Tpa Name')
    invoice_id = fields.Char(string='Invoice ID')
    invoice_no = fields.Char(string='Invoice No')
    invoice_date = fields.Date(string='Invoice Date')
    invoice_sent = fields.Date(string='Invoice Sent')
    invoice_maturity = fields.Date(string='Invoice Maturity')
    writeoff_no = fields.Char(string='Write-Off No')
    writeoff_date = fields.Date(string='Write-Off Date')
    writeoff_amount = fields.Float(string='Write-Off Amount')
    # writeoff_type = fields.Char(string='Write-Off Type')
    writeoff_type = fields.Selection([
        ('On Bill', 'On Bill'),
        ('On Service', 'On Service'),
        ('On Department', 'On Department'),
        ('On Items', 'On Items')
    ], string='WriteOff Type', required=True)
    writeoff_notes = fields.Char(string='Write-Off Notes')
    writeoff_reason = fields.Char(string='Write-Off Reason')
    odoo_discount_id = fields.Many2one('hospital.discount.type', string='Odoo Discount')
    discount_id = fields.Char(string='Discount ID')
    discount_name = fields.Char(string='Discount Name')
    discount_code = fields.Char(string='Discount Code')
    odoo_admission_id = fields.Many2one('sale.order', string='Odoo Admission')
    admission_id = fields.Char(string='Admission ID')
    admission_no = fields.Char(string='Admission No')
    admission_date = fields.Datetime(string='Admission Date')
    odoo_patient_id = fields.Many2one('res.partner', string='Odoo Patient')
    patient_id = fields.Char(string='Patient ID')
    patient_mrid = fields.Char(string='Patient MRID')
    patient_ref_no = fields.Char(string='Patient Ref No')
    patient_name = fields.Char(string='Patient Name')
    odoo_bill_id = fields.Many2one('sale.order.bill', string='Odoo Billing')
    bill_id = fields.Char(string='Bill ID')
    # bill_type = fields.Char(string='Bill Type')
    bill_type = fields.Selection([
        ('CR', 'Credit'),
        ('CS', 'Cash')
    ], string='Bill Type', required=True)
    bill_no = fields.Char(string='Bill No')
    bill_date = fields.Datetime(string='Bill Date')
    order_no = fields.Char(string='Order No')
    order_date = fields.Datetime(string='Order Date')
    order_line_seq = fields.Char(string='Order Line Seq')
    service_id = fields.Char(string='Service ID')
    service_name = fields.Char(string='Service Name')
    department_id = fields.Char(string='Department ID')
    department_name = fields.Char(string='Department Name')
    product_id = fields.Char(string='Product ID')
    product_name = fields.Char(string='Product Name')
    quantity = fields.Float(string='Quantity')
    percentage = fields.Float(string='Percentage')
    amount = fields.Float(string='Amount')
    state = fields.Selection([
        ('confirm', 'Confirm'),
        ('cancel', 'Cancel')
    ], string='State', default='confirm', required=True)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReceivableWriteoff,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Writeoff Billing" delete="0" create="0" edit="0">
                    <header>
                        <field name="state" widget="statusbar" modifiers="{'readonly': true}"/>
                    </header>
                    <sheet>
                        <group>
                            <group>
                                <field name="cutoff_date" />
                                <field name="payor_id" />
                                <field name="payor_code" />
                                <field name="payor_name" />
                                <field name="payor_type" />
                                <field name="invoice_no" />
                                <field name="invoice_date" />
                                <field name="invoice_sent" />
                                <field name="invoice_maturity" />
                                <field name="writeoff_no" />
                                <field name="writeoff_date" />
                                <field name="writeoff_amount" />
                                <field name="writeoff_type" />
                                <field name="writeoff_notes" />
                                <field name="writeoff_reason" />
                                <field name="odoo_discount_id" />
                                <field name="discount_id" />
                                <field name="discount_name" />
                                <field name="odoo_admission_id" />
                                <field name="admission_id" />
                                <field name="admission_no" />
                                <field name="admission_date" />
                                <field name="odoo_tpa_id" />
                                <field name="odoo_payor_id" />
                            </group>
                            <group>
                                <field name="tpa_id" />
                                <field name="tpa_code" />
                                <field name="tpa_name" />
                                <field name="odoo_patient_id" />
                                <field name="patient_id" />
                                <field name="patient_mrid" />
                                <field name="patient_ref_no" />
                                <field name="patient_name" />
                                <field name="odoo_bill_id" />
                                <field name="bill_id" />
                                <field name="bill_type" />
                                <field name="bill_no" />
                                <field name="bill_date" />
                                <field name="order_no" />
                                <field name="order_date" />
                                <field name="order_line_seq" />
                                <field name="service_id" />
                                <field name="service_name" />
                                <field name="department_id" />
                                <field name="department_name" />
                                <field name="product_id" />
                                <field name="product_name" />
                                <field name="quantity" />
                                <field name="percentage" />
                                <field name="amount" />
                            </group>
                        </group>    
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" />
                                        <field name="sync_id_api" readonly="1" />
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
                <tree string="Writeoff Billng" delete="0" create="0" decoration-danger="state == 'cancel'" decoration-info="state == 'draft'" decoration-success="state=='confirm'">
                    <field name="cutoff_date"/>
                    <field name="writeoff_no"/>
                    <field name="writeoff_notes"/>
                    <field name="discount_name"/>
                    <field name="patient_name"/>
                    <field name="bill_no"/>
                    <field name="amount"/>
                    <field name="state"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Writeoff Billng Search">
                    <field name="invoice_no"/>
                    <field name="bill_no"/>
                    <field name="patient_name"/>
                </search>
            """


        elif view_type == 'pivot':
            res['arch'] = """
                <pivot string="Writeoff Billing">
                    <field name="amount" type="measure"/>
                </pivot>
           """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    
    @api.model
    def _create_journal_arcus_writeoff(self, sync_type='1', date=False):
        if not date:
            date = '' + (tools.datetime.now() + tools.timedelta(hours=7)-tools.timedelta(days=1)).strftime('%Y-%m-%d')
        company = self.env['res.company'].search([('sync_type', '=', sync_type)], limit=1)
        company_id = company.id 
        
        query = """
            SELECT 
                sol.direction, sol.amount, sol.account_label, 
                sol.account_credit_id, sol.account_debit_id, 
                (CASE WHEN sol.direction < 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_debit_id,
                (CASE WHEN sol.direction = 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_credit_id
            FROM view_account_arcus_writeoff sol 
            WHERE sol.tglproses = '{date}'
                AND sol.sync_type = '{sync_type}'
                AND sol.amount <> 0
            """ .format(date=date, sync_type=sync_type)
        self.env.cr.execute(query)
        lines = self.env.cr.dictfetchall()
        if not lines:
            print ("There are no lines to make journal")
            return
        move_lines = []
        for line in lines:
            # validasi COA 
            if not line['account_credit_id']:
                raise exceptions.ValidationError("Please mapping credit account")
            if not line['account_debit_id']:
                raise exceptions.ValidationError("Please mapping debit account")

            
        journal_id = self.env['account.journal'].search([('name', 'ilike', 'Arcus Writeoff'),('company_id', '=', company_id)],limit=1).id
        
        if journal_id:
            self.env['account.move'].create({'journal_id':journal_id,'line_ids':move_lines,'date':date, 'ref': 'ARCUS WRITEOFF as ' + str(date)})


class ReceivableAdvance(models.Model):
    _name = 'receivable.advance'
    _rec_name = 'deposit_no'
    _description = 'Receivable Advance'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    cutoff_date = fields.Date(string='Cutoff Date')
    odoo_tpa_id = fields.Many2one('res.partner', string="Odoo Tpa")
    odoo_payor_id = fields.Many2one('res.partner', string="Odoo Payer")
    payor_id = fields.Char(string='Payor ID')
    payor_code = fields.Char(string='Payor Code')
    payor_name = fields.Char(string='Payor Name')
    payor_type = fields.Char(string='Payor Type')
    tpa_id = fields.Char(string='Tpa ID')
    tpa_code = fields.Char(string='Tpa Code')
    tpa_name = fields.Char(string='Tpa Name')
    deposit_no = fields.Char(string='Deposit No')
    deposit_date = fields.Datetime(string='Deposit Date')
    # type = fields.Char(string='Type')
    type = fields.Selection([
        ('advance', 'Advance'),
        ('refund', 'Refund')
    ], string='Type', required=True)
    amount = fields.Float(string='Amount')
    odoo_payment_id = fields.Many2one('receivable.payment.mode', String='Odoo Payment')
    payment_id = fields.Char(string='Payment ID')
    payment_type = fields.Selection([
        ('BankTransfer', 'BankTransfer'),
        ('Cash', 'Cash'),
        ('CreditCard', 'CreditCard'),
        ('DebitCard', 'DebitCard'),
        ('Voucher', 'Voucher')
    ], string='Payment Type', required=True)
    odoo_bank_id = fields.Many2one('receivable.bank.name', String='Odoo Bank')
    bank_id = fields.Char(string='Bank ID')
    bank_name = fields.Char(string='Bank Name')
    bank_account = fields.Char(string='Bank Account')
    bank_date = fields.Datetime(string='Bank Date')
    reference_no = fields.Char(string='Reference No.')
    notes = fields.Char(string='Notes')
    remark = fields.Char(string='Remark')
    state = fields.Selection([
        ('confirm', 'Confirm'),
        ('cancel', 'Cancel')
    ], string='State', default='confirm', required=True)

    # @api.onchange('payment_type')
    # def _onchange_payment_type(self):
    #     if self.payment_type != 'BankTransfer':
    #         self.bank_name = False

    # @api.constrains('bank_name', 'payment_type')
    # def _check_bank_name(self):
    #     for record in self:
    #         if record.payment_type == 'BankTransfer' and not record.bank_name:
    #             raise ValidationError("Bank Name must be filled for Bank Transfer payment type.")


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReceivableAdvance,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Company Deposit" delete="0" create="0" edit="0">
                    <header>
                        <field name="state" widget="statusbar" modifiers="{'readonly': true}"/>
                    </header>
                    <sheet>
                        <group>
                            <group>
                                <field name="cutoff_date" />
                                <field name="tpa_id" />
                                <field name="tpa_code" />
                                <field name="tpa_name" />
                                <field name="payor_type" />
                                <field name="payor_id" />
                                <field name="payor_code" />
                                <field name="payor_name" />
                                <field name="deposit_no" />
                                <field name="reference_no" />
                                <field name="deposit_date" />
                                <field name="odoo_tpa_id" />
                                <field name="odoo_payor_id" />
                            </group>
                            <group>
                                <field name="type" />
                                <field name="amount" />
                                <field name="odoo_payment_id" />
                                <field name="payment_id" />
                                <field name="payment_type" />
                                <field name="odoo_bank_id" />
                                <field name="bank_id" />
                                <field name="bank_name" />
                                <field name="bank_account" />
                                <field name="bank_date" />
                                <field name="remark" />
                                <field name="notes" />
                            </group>
                        </group>
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" />
                                        <field name="sync_id_api" readonly="1" />
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
                <tree string="Company Deposit" delete="false" create="false" decoration-danger="state == 'cancel'" decoration-info="state == 'draft'" decoration-success="state=='confirm'">
                    <field name="cutoff_date"/>
                    <field name="deposit_no"/>
                    <field name="reference_no"/>
                    <field name="tpa_name"/>
                    <field name="payment_type"/>
                    <field name="type"/>
                    <field name="amount"/>
                    <field name="state"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Advance Search">
                    <field name="payor_code"/>
                    <field name="payor_name"/>
                    <field name="amount"/>
                </search>
            """

        elif view_type == 'pivot':
            res['arch'] = '''
                <pivot string="Advance">
                    <field name="amount" type="measure"/>
                </pivot>
           '''
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    
    @api.model
    def _create_journal_arcus_company_deposit(self, sync_type='1', date=False):
        if not date:
            date = '' + (tools.datetime.now() + tools.timedelta(hours=7)-tools.timedelta(days=1)).strftime('%Y-%m-%d')
        company = self.env['res.company'].search([('sync_type', '=', sync_type)], limit=1)
        company_id = company.id 
        
        query = """
            SELECT 
                sol.direction, sol.amount, sol.account_label, 
                sol.account_credit_id, sol.account_debit_id, 
                (CASE WHEN sol.direction < 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_debit_id,
                (CASE WHEN sol.direction = 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_credit_id
            FROM view_account_arcus_company_deposit sol 
            WHERE sol.tglproses = '{date}'
                AND sol.sync_type = '{sync_type}'
                AND sol.amount <> 0
            """ .format(date=date, sync_type=sync_type)
        self.env.cr.execute(query)
        lines = self.env.cr.dictfetchall()
        if not lines:
            print ("There are no lines to make journal")
            return
        move_lines = []
        for line in lines:
            # validasi COA 
            if not line['account_credit_id']:
                raise exceptions.ValidationError("Please mapping credit account")
            if not line['account_debit_id']:
                raise exceptions.ValidationError("Please mapping debit account")

            
        journal_id = self.env['account.journal'].search([('name', 'ilike', 'Arcus Company Deposit'),('company_id', '=', company_id)],limit=1).id
        
        if journal_id:
            self.env['account.move'].create({'journal_id':journal_id,'line_ids':move_lines,'date':date, 'ref': 'ARCUS COMPANY DEPOSIT as ' + str(date)})



class ReceivableSettlementSource(models.Model):
    _name = 'receivable.settlement.source'
    _rec_name = 'transaction_no'
    _description = 'Receivable Settlement Source'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    cutoff_date = fields.Date(string='Cutoff Date')

    odoo_payor_id = fields.Many2one('res.partner', string="Odoo Payer")
    payor_id = fields.Char(string='Payor ID')
    payor_code = fields.Char(string='Payor Code')
    payor_name = fields.Char(string='Payor Name')
    payor_type = fields.Char(string='Payor Type')

    odoo_tpa_id = fields.Many2one('res.partner', string="Odoo Tpa")
    tpa_id = fields.Char(string='Tpa ID')
    tpa_code = fields.Char(string='Tpa Code')
    tpa_name = fields.Char(string='Tpa Name')

    transaction_no = fields.Char(string='Transaction No')
    transaction_type = fields.Char(string='Transaction Type')
    transaction_date = fields.Datetime(string='Transaction Date')
    transaction_datetime = fields.Datetime(string='Transaction Datetime')

    odoo_payment_id = fields.Many2one('receivable.payment.mode', string='Odoo Payment')
    payment_id = fields.Char(string='Payment ID')
    # payment_type = fields.Char(string='Payment Type')
    payment_type = fields.Selection([
        ('Cash', 'Cash'),
        ('Transfer', 'BankTransfer'),
        ('CreditCard', 'CreditCard'),
        ('DebitCard', 'DebitCard'),
        ('Voucher', 'Voucher'),
        ('CreditNote', 'CreditNote'),
        ('PayorDeposit', 'Deposit')
    ], string='Payment Type', required=True)

    deposit_id = fields.Char(string='Deposit ID')
    deposit_no = fields.Char(string='Deposit No')
    deposit_date = fields.Datetime(string='Deposit Date')

    deposit_adjust_id = fields.Char(string='Deposit Adjust ID')
    deposit_adjust_no = fields.Char(string='Deposit Adjust No')
    deposit_adjust_date = fields.Datetime(string='Deposit Adjust Date')

    creditnote_id = fields.Char(string='CreditNote ID')
    creditnote_no = fields.Char(string='CreditNote No')
    creditnote_date = fields.Datetime(string='CreditNote Date')

    creditnote_adjust_id = fields.Char(string='CN Adjust ID')
    creditnote_adjust_no = fields.Char(string='CN Adjust No')
    creditnote_adjust_date = fields.Datetime(string='CN Adjust Date')

    odoo_bank_id = fields.Many2one('receivable.bank.name', string='Odoo Bank')
    bank_id = fields.Char(string='Bank ID')
    bank_name = fields.Char(string='Bank Name')
    bank_date = fields.Datetime(string='Bank Date')

    reference = fields.Char(string='Reference')
    amount = fields.Float(string='Amount')
    notes = fields.Char(string='Notes')
    remark = fields.Char(string='Remark')

    state = fields.Selection([
        ('confirm', 'Confirm'),
        ('cancel', 'Cancel')
    ], string='State', default='confirm', required=True)


    admission_id = fields.Char(string='Admission ID')
    odoo_admission_id = fields.Many2one('sale.order', string="Odoo Admission ID")
    admission_no = fields.Char(string='Admission No.')
    admission_date = fields.Datetime(string='Admission Date')

    patient_id = fields.Char(string='Patient ID')
    odoo_patient_id = fields.Many2one('res.partner', string="Odoo Patient ID")
    patient_mrid = fields.Char(string='Patient MR ID')
    patient_ref_no = fields.Char(string='Patient Ref No')
    patient_name = fields.Char(string='Patient Name')

    bill_id = fields.Char(string='Bill ID')
    odoo_bill_id = fields.Many2one('sale.order.bill', string="Odoo Bill")
    bill_date = fields.Datetime(string='Bill Date')
    bill_no = fields.Char(string='Bill No')

    user_name = fields.Char(string='User Name')
    facility_name = fields.Char(string='Facility Name')


    # @api.onchange('payment_type')
    # def _onchange_payment_type(self):
    #     if self.payment_type != 'Deposit':
    #         self.deposit_no = False
    #         self.deposit_date = False
    #     if self.payment_type != 'CreditNote':
    #         self.creditnote_no = False
    #         self.creditnote_date = False
    #     if self.payment_type != 'BankTransfer':
    #         self.bank_name = False

    # @api.constrains('deposit_no', 'deposit_date', 'payment_type')
    # def _check_deposit_fields(self):
    #     for record in self:
    #         if record.payment_type == 'Deposit' and (not record.deposit_no or not record.deposit_date):
    #             raise ValidationError("Deposit No. and Deposit Date must be filled for Deposit payment type.")

    # @api.constrains('creditnote_no', 'creditnote_date', 'payment_type')
    # def _check_creditnote_fields(self):
    #     for record in self:
    #         if record.payment_type == 'CreditNote' and (not record.creditnote_no or not record.creditnote_date):
    #             raise ValidationError("Credit Note No. and Credit Note Date must be filled for Credit Note payment type.")

    # @api.constrains('bank_name', 'payment_type')
    # def _check_bank_name(self):
    #     for record in self:
    #         if record.payment_type == 'BankTransfer' and not record.bank_name:
    #             raise ValidationError("Bank Name must be filled for Bank Transfer payment type.")      


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReceivableSettlementSource,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="AR Settlement Billing" delete="0" create="0" edit="0">
                    <header>
                        <field name="state" widget="statusbar" modifiers="{'readonly': true}"/>
                    </header>
                    <sheet>
                        <group>
                            <group>
                                <field name="cutoff_date" />
                                <field name="transaction_no" />
                                <field name="transaction_date" />
                                <field name="transaction_datetime"/>
                                <field name="transaction_type"/>
                                <field name="odoo_payment_id" />
                                <field name="payment_id" />
                                <field name="payment_type" />
                                <field name="amount" />
                                <field name="user_name" />
                                <field name="facility_name" />
                                <field name="bank_id" />
                                <field name="bank_name" />
                                <field name="odoo_bank_id" />
                                <field name="creditnote_id" />
                                <field name="creditnote_no" />
                                <field name="creditnote_date" />
                                <field name="creditnote_adjust_id" />
                                <field name="creditnote_adjust_no" />
                                <field name="creditnote_adjust_date"/>
                                <field name="tpa_id" />
                                <field name="tpa_code" />
                                <field name="tpa_name" />
                                <field name="odoo_tpa_id" />
                            </group>
                            <group>
                                <field name="admission_id"/>
                                <field name="odoo_admission_id"/>
                                <field name="admission_no"/>
                                <field name="admission_date"/>
                                <field name="patient_id"/>
                                <field name="odoo_patient_id"/>
                                <field name="patient_mrid"/>
                                <field name="patient_ref_no"/>
                                <field name="patient_name"/>
                                <field name="bill_id"/>
                                <field name="odoo_bill_id"/>
                                <field name="bill_no" />
                                <field name="bill_date"/>
                                <field name="deposit_id"/>
                                <field name="deposit_no"/>
                                <field name="deposit_date"/>
                                <field name="deposit_adjust_id"/>
                                <field name="deposit_adjust_no"/>
                                <field name="deposit_adjust_date"/>
                                <field name="reference" />
                                <field name="notes" />
                                <field name="remark"/>
                                <field name="payor_id" />
                                <field name="payor_code" />
                                <field name="payor_name" />
                                <field name="odoo_payor_id" />
                            </group>
                        </group>
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" />
                                        <field name="sync_id_api" readonly="1" />
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
                <tree string="AR Settlement Billing" delete="false" create="false" decoration-danger="state == 'cancel'" decoration-info="state == 'draft'" decoration-success="state=='confirm'">
                    <field name="cutoff_date"/>
                    <field name="transaction_no"/>
                    <field name="tpa_code"/>
                    <field name="tpa_name"/>
                    <field name="patient_name"/>
                    <field name="bill_no"/>
                    <field name="payment_type" />
                    <field name="amount" sum="Total" widget="monetary"/>
                    <field name="state"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Settlement Source Search">
                    <field name="transaction_no"/>
                    <field name="tpa_name"/>
                    <field name="payor_name"/>
                    <field name="reference"/>
                </search>
            """

        elif view_type == 'pivot':
            res['arch'] = '''
                <pivot string="Settlement Source">
                    <field name="amount" type="measure"/>
                </pivot>
           '''
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res
    

    @api.model
    def _create_journal_arcus_settlement_source(self, sync_type='1', date=False):
        if not date:
            date = '' + (tools.datetime.now() + tools.timedelta(hours=7)-tools.timedelta(days=1)).strftime('%Y-%m-%d')
        company = self.env['res.company'].search([('sync_type', '=', sync_type)], limit=1)
        company_id = company.id 
        
        query = """
            SELECT 
                sol.direction, sol.amount, sol.account_label, 
                sol.account_credit_id, sol.account_debit_id, 
                (CASE WHEN sol.direction < 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_debit_id,
                (CASE WHEN sol.direction = 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_credit_id
            FROM view_account_arcus_settlement_source sol 
            WHERE sol.tglproses = '{date}'
                AND sol.sync_type = '{sync_type}'
                AND sol.amount <> 0
            """ .format(date=date, sync_type=sync_type)
        self.env.cr.execute(query)
        lines = self.env.cr.dictfetchall()
        if not lines:
            print ("There are no lines to make journal")
            return
        move_lines = []
        for line in lines:
            # validasi COA 
            if not line['account_credit_id']:
                raise exceptions.ValidationError("Please mapping credit account")
            if not line['account_debit_id']:
                raise exceptions.ValidationError("Please mapping debit account")

            
        journal_id = self.env['account.journal'].search([('name', 'ilike', 'Arcus Settlement Source'),('company_id', '=', company_id)],limit=1).id
        
        if journal_id:
            self.env['account.move'].create({'journal_id':journal_id,'line_ids':move_lines,'date':date, 'ref': 'ARCUS SETTLEMENT SOURCE as ' + str(date)})


class ReceivableSettlementBilling(models.Model):
    _name = 'receivable.settlement.billing'
    _rec_name = 'transaction_no'
    _description = 'Receivable Settlement Billing'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

    cutoff_date = fields.Date(string='Cutoff Date')
    odoo_tpa_id = fields.Many2one('res.partner', string="Odoo Tpa")
    odoo_payor_id = fields.Many2one('res.partner', string="Odoo Payer")
    payor_id = fields.Char(string='Payor ID')
    payor_code = fields.Char(string='Payor Code')
    payor_name = fields.Char(string='Payor Name')
    payor_type = fields.Char(string='Payor Type')
    tpa_id = fields.Char(string='Tpa ID')
    tpa_code = fields.Char(string='Tpa Code')
    tpa_name = fields.Char(string='Tpa Name')
    transaction_no = fields.Char(string='Transaction No')
    transaction_date = fields.Datetime(string='Transaction Date')
    invoice_no = fields.Char(string='Invoice No')
    invoice_date = fields.Date(string='Invoice Date')
    invoice_sent = fields.Date(string='Invoice Sent')
    invoice_maturity = fields.Date(string='Invoice Maturity')
    bill_id = fields.Char(string='Bill ID')
    bill_no = fields.Char(string='Bill No')
    bill_date = fields.Datetime(string='Bill Date')
    admission_id = fields.Char(string='Admission ID')
    admission_no = fields.Char(string='Admission No')
    admission_date = fields.Datetime(string='Admission Date')
    patient_id = fields.Char(string='Patient ID')
    patient_mrid = fields.Char(string='Patient MRID')
    patient_ref_no = fields.Char(string='Patient Ref No')
    patient_name = fields.Char(string='Patient Name')
    payor_invoice = fields.Float(string='Payor Invoice')
    payor_balance = fields.Float(string='Payor Balance')
    payor_receipt = fields.Float(string='Payor Receipt')
    # state = fields.Char(string='State')
    state = fields.Selection([
        ('confirm', 'Confirm'),
        ('cancel', 'Cancel')
    ], string='State', default='confirm', required=True)


    # @api.constrains('invoice_date', 'invoice_sent', 'invoice_maturity')
    # def _check_invoice_dates(self):
    #     for record in self:
    #         if record.invoice_date > record.invoice_sent:
    #             raise ValidationError("Invoice Sent Date cannot be before Invoice Date.")
    #         if record.invoice_date > record.invoice_maturity:
    #             raise ValidationError("Invoice Maturity Date cannot be before Invoice Date.")                        


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReceivableSettlementBilling,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Settlement Billing" delete="false">
                    <header>
                        <field name="state" widget="statusbar" modifiers="{&quot;readonly&quot;: true}"/>
                    </header>
                    <sheet>
                        <group>
                            <group>
                                <field name="cutoff_date" />
                                <field name="payor_id" />
                                <field name="payor_code" />
                                <field name="payor_name" />
                                <field name="payor_type" />
                                <field name="tpa_id" />
                                <field name="tpa_code" />
                                <field name="tpa_name" />
                                <field name="transaction_no" />
                                <field name="transaction_date" />
                                <field name="invoice_no" />
                                <field name="invoice_date" />
                                <field name="invoice_sent" />
                                <field name="invoice_maturity" />
                                <field name="bill_id" />
                                <field name="bill_no" />
                            </group>
                            <group>
                                <field name="bill_date" />
                                <field name="admission_id" />
                                <field name="admission_no" />
                                <field name="admission_date" />
                                <field name="patient_id" />
                                <field name="patient_mrid" />
                                <field name="patient_ref_no" />
                                <field name="patient_name" />
                                <field name="payor_invoice" />
                                <field name="payor_balance" />
                                <field name="payor_receipt" />
                            </group>
                        </group>    
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" />
                                        <field name="sync_id_api" readonly="1" />
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
                <tree string="Settlement Billing" delete="false">
                    <field name="transaction_no"/>
                    <field name="bill_no"/>
                    <field name="patient_mrid"/>
                    <field name="patient_name"/>
                    <field name="payor_balance"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Settlement Billing Search">
                    <field name="transaction_no"/>
                    <field name="bill_no"/>
                    <field name="patient_name"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


    @api.model
    def _create_journal_arcus_settlement_billing(self, sync_type='1', date=False):
        if not date:
            date = '' + (tools.datetime.now() + tools.timedelta(hours=7)-tools.timedelta(days=1)).strftime('%Y-%m-%d')
        company = self.env['res.company'].search([('sync_type', '=', sync_type)], limit=1)
        company_id = company.id 
        
        query = """
            SELECT 
                sol.direction, sol.amount, sol.account_label, 
                sol.account_credit_id, sol.account_debit_id, 
                (CASE WHEN sol.direction < 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_debit_id,
                (CASE WHEN sol.direction = 1 
                    THEN COALESCE(sol.analytic_id, 0) 
                    ELSE 0 END) analytic_credit_id
            FROM view_account_arcus_settlement_billing sol 
            WHERE sol.tglproses = '{date}'
                AND sol.sync_type = '{sync_type}'
                AND sol.amount <> 0
            """ .format(date=date, sync_type=sync_type)
        self.env.cr.execute(query)
        lines = self.env.cr.dictfetchall()
        if not lines:
            print ("There are no lines to make journal")
            return
        move_lines = []
        for line in lines:
            # validasi COA 
            if not line['account_credit_id']:
                raise exceptions.ValidationError("Please mapping credit account")
            if not line['account_debit_id']:
                raise exceptions.ValidationError("Please mapping debit account")

            
        journal_id = self.env['account.journal'].search([('name', 'ilike', 'Arcus Settlement Billing'),('company_id', '=', company_id)],limit=1).id
        
        if journal_id:
            self.env['account.move'].create({'journal_id':journal_id,'line_ids':move_lines,'date':date, 'ref': 'ARCUS SETTLEMENT BILLING as ' + str(date)})




class ReceivableBankName(models.Model):
    _name = 'receivable.bank.name'
    _description = 'Receivable Bank Name'
    _rec_name = 'bank_name'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    bank_code = fields.Char(string='Bank Code')
    bank_name = fields.Char(string='Bank Name')
    journal_id = fields.Many2one('account.journal', string='Journal')
    account_id = fields.Many2one('account.account', string='Account Bank')

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReceivableBankName,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Receivable Bank Name" delete="false" create="false">
                    <!--header>
                        <field name="state" widget="statusbar" modifiers="{'readonly': true}"/>
                    </header-->
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" />
                                <field name="bank_code" />
                                <field name="bank_name" />
                            </group>
                            <group>
                                <field domain="[('company_id','=',company_id)]" name="journal_id" />
                                <field domain="[('company_id','=',company_id), ('deprecated','=',False), ('parent','=',False)]" name="account_id" />
                            </group>
                        </group>    
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" />
                                        <field name="sync_id_api" readonly="1" />
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
                <tree string="Receivable Bank Name" delete="false" create="false">
                    <field name="bank_code"/>
                    <field name="bank_name"/>
                    <field name="journal_id"/>
                    <field name="account_id"/>
                    <field name="company_id"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Receivable Bank Name Search">
                    <field name="bank_code"/>
                    <field name="bank_name"/>
                    <field name="journal_id"/>
                    <field name="account_id"/>
                    <field name="company_id"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


# class ReceivableAccrualBilling(models.Model):
#     _name = 'receivable.accrual.billing'
#     _description = 'IQVIA - IP Accrual'
#     _rec_name = 'admission_no'

#     sync_id = sync.id
#     sync_id_api = sync.id_api
#     sync_date = sync.date
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

#     trigger_create = fields.Boolean(string="Trigger Create")
#     trigger_write = fields.Boolean(string="Trigger Write")
#     sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

#     @api.model
#     def _get_company(self):
#         return self.env.user.company_id.id

#     company_id = fields.Many2one('res.company', string='Company', default=_get_company)
#     cutoff_date = fields.Date(string='Cutoff Date')
#     odoo_tpa_id = fields.Many2one('res.partner', string="Odoo Tpa")
#     odoo_payor_id = fields.Many2one('res.partner', string="Odoo Payer")
#     payor_id = fields.Char(string='Payor ID')
#     payor_code = fields.Char(string='Payor Code')
#     payor_name = fields.Char(string='Payor Name')
#     tpa_id = fields.Char(string='Tpa ID')
#     tpa_code = fields.Char(string='Tpa Code')
#     tpa_name = fields.Char(string='Tpa Name')
#     payor_type = fields.Char(string='Payor Type')
#     admission_id = fields.Char(string='Admission ID')
#     admission_no = fields.Char(string='Admission No')
#     admission_date = fields.Datetime(string='Admission Date')
#     patient_id = fields.Char(string='Patient ID')
#     patient_mrid = fields.Char(string='Patient MRID')
#     patient_ref_no = fields.Char(string='Patient Ref No')
#     patient_name = fields.Char(string='Patient Name')
#     payor_balance = fields.Float(string='Payor Balance')
#     patient_type = fields.Selection([('1','OP'),('2','IP'),('3','Emergency'),('4','DayCare'),('5','MCU'),('6','Pharmacy')], string='Patient Type')

#     aggreement_id = fields.Char(string='Aggreement ID')
#     aggreement_code = fields.Char(string='Aggreement Code')
#     aggreement_name = fields.Char(string='Aggreement Name')
#     odoo_admission_id = fields.Many2one('sale.order', string="Odoo Admission ID")
#     odoo_patient_id = fields.Many2one('res.partner', string="Odoo Patient ID")
    
    
#     patient_group = fields.Char(string='Patient Group')
#     patient_type_name = fields.Char(string='Patient Type Name')
#     admission_number = fields.Char(string='Admission Number')
#     tariff_id = fields.Char(string='Tariff ID')
#     odoo_tariff_id = fields.Many2one('hospital.tariff', string="Odoo Tariff ID")
#     tariff_name = fields.Char(string='Tariff Name')
#     alloted_bed_type_id = fields.Char(string='Alloted Bed Type ID')
#     odoo_alloted_bed_type_id = fields.Many2one('hospital.bed.type', string="Odoo Alloted Bed Type ID")
#     alloted_bed_type_name = fields.Char(string='Alloted Bed Type Name')
#     eligible_bed_type_id = fields.Char(string='Eligible Bed Type ID')
#     odoo_eligible_bed_type_id = fields.Many2one('hospital.bed.type', string="Odoo Eligible Bed Type ID")
#     eligible_bed_type_name = fields.Char(string='Eligible Bed Type Name')
#     room_id = fields.Char(string='Room ID')
#     odoo_room_id = fields.Many2one('hospital.room.name', string="Odoo Room ID")
#     room_name = fields.Char(string='Room Name')
#     bed_id = fields.Char(string='Bed ID')
#     odoo_bed_id = fields.Many2one('hospital.bed.name', string="Odoo Bed ID")
#     bed_name = fields.Char(string='Bed Name')
#     ward_id = fields.Char(string='Ward ID')
#     odoo_ward_id = fields.Many2one('hr.department', string="Odoo Ward ID")
#     ward_name = fields.Char(string='Ward Name')
#     doctor_primary_id = fields.Char(string='Doctor Primary ID')
#     odoo_doctor_primary_id = fields.Many2one('account.analytic.account', string="Odoo Doctor Primary ID")
#     doctor_primary_code = fields.Char(string='Doctor Primary Code')
#     doctor_primary_name = fields.Char(string='Doctor Primary Name')
#     amount = fields.Float(string='Amount')
#     state = fields.Selection([
#         ('confirm', 'Confirm'),
#         ('cancel', 'Cancel')
#     ], string='State', default='confirm', required=True)        



class ReceivablePaymentMode(models.Model):
    _name = 'receivable.payment.mode'
    _description = 'Receivable Payment Mode'
    _rec_name = 'name'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    code = fields.Char(string='Payment Code')
    name = fields.Char(string='Payment Name')
    journal_id = fields.Many2one('account.journal', string='Journal')
    account_id = fields.Many2one('account.account', string='Account Payment')

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReceivablePaymentMode,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Receivable Payment Mode" delete="false" create="false">
                    <!--header>
                        <field name="state" widget="statusbar" modifiers="{'readonly': true}"/>
                    </header-->
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" />
                                <field name="code" />
                                <field name="name" />
                            </group>
                            <group>
                                <field domain="[('company_id','=',company_id)]" name="journal_id" />
                                <field domain="[('company_id','=',company_id), ('deprecated','=',False), ('parent','=',False)]" name="account_id" />
                            </group>
                        </group>    
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" />
                                        <field name="sync_id_api" readonly="1" />
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
                <tree string="Receivable Bank Name" delete="false" create="false">
                    <field name="code"/>
                    <field name="name"/>
                    <field name="journal_id"/>
                    <field name="account_id"/>
                    <field name="company_id"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Receivable Bank Name Search">
                    <field name="code"/>
                    <field name="name"/>
                    <field name="journal_id"/>
                    <field name="account_id"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res




class ReceivableAccrualBilling(models.Model):
    _name = 'receivable.accrual.billing'
    _description = 'IQVIA - IP Accrual'
    _rec_name = 'admission_no'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    cutoff_date = fields.Date(string='Cutoff Date')
    odoo_tpa_id = fields.Many2one('res.partner', string="Odoo Tpa")
    odoo_payor_id = fields.Many2one('res.partner', string="Odoo Payer")
    payor_id = fields.Char(string='Payor ID')
    payor_code = fields.Char(string='Payor Code')
    payor_name = fields.Char(string='Payor Name')
    tpa_id = fields.Char(string='Tpa ID')
    tpa_code = fields.Char(string='Tpa Code')
    tpa_name = fields.Char(string='Tpa Name')
    payor_type = fields.Char(string='Payor Type')
    admission_id = fields.Char(string='Admission ID')
    admission_no = fields.Char(string='Admission No')
    admission_date = fields.Datetime(string='Admission Date')
    patient_id = fields.Char(string='Patient ID')
    patient_mrid = fields.Char(string='Patient MRID')
    patient_ref_no = fields.Char(string='Patient Ref No')
    patient_name = fields.Char(string='Patient Name')
    payor_balance = fields.Float(string='Payor Balance')
    patient_type = fields.Selection([('1','OP'),('2','IP'),('3','Emergency'),('4','DayCare'),('5','MCU'),('6','Pharmacy')], string='Patient Type')

    aggreement_id = fields.Char(string='Aggreement ID')
    aggreement_code = fields.Char(string='Aggreement Code')
    aggreement_name = fields.Char(string='Aggreement Name')
    odoo_admission_id = fields.Many2one('sale.order', string="Odoo Admission ID")
    odoo_patient_id = fields.Many2one('res.partner', string="Odoo Patient ID")
    
    
    patient_group = fields.Char(string='Patient Group')
    patient_type_name = fields.Char(string='Patient Type Name')
    admission_number = fields.Char(string='Admission Number')
    tariff_id = fields.Char(string='Tariff ID')
    odoo_tariff_id = fields.Many2one('hospital.tariff', string="Odoo Tariff ID")
    tariff_name = fields.Char(string='Tariff Name')
    alloted_bed_type_id = fields.Char(string='Alloted Bed Type ID')
    odoo_alloted_bed_type_id = fields.Many2one('hospital.bed.type', string="Odoo Alloted Bed Type ID")
    alloted_bed_type_name = fields.Char(string='Alloted Bed Type Name')
    eligible_bed_type_id = fields.Char(string='Eligible Bed Type ID')
    odoo_eligible_bed_type_id = fields.Many2one('hospital.bed.type', string="Odoo Eligible Bed Type ID")
    eligible_bed_type_name = fields.Char(string='Eligible Bed Type Name')
    room_id = fields.Char(string='Room ID')
    odoo_room_id = fields.Many2one('hospital.room.name', string="Odoo Room ID")
    room_name = fields.Char(string='Room Name')
    bed_id = fields.Char(string='Bed ID')
    odoo_bed_id = fields.Many2one('hospital.bed.name', string="Odoo Bed ID")
    bed_name = fields.Char(string='Bed Name')
    ward_id = fields.Char(string='Ward ID')
    odoo_ward_id = fields.Many2one('hr.department', string="Odoo Ward ID")
    ward_name = fields.Char(string='Ward Name')
    doctor_primary_id = fields.Char(string='Doctor Primary ID')
    odoo_doctor_primary_id = fields.Many2one('account.analytic.account', string="Odoo Doctor Primary ID")
    doctor_primary_code = fields.Char(string='Doctor Primary Code')
    doctor_primary_name = fields.Char(string='Doctor Primary Name')
    amount = fields.Float(string='Amount')
    state = fields.Selection([
        ('confirm', 'Confirm'),
        ('cancel', 'Cancel')
    ], string='State', default='confirm', required=True)


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ReceivableAccrualBilling,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="IP Payable Accrual" delete="0" edit="0" create="0">
                    <header>
                        <field name="state" widget="statusbar" modifiers="{'readonly': true}"/>
                    </header>
                    <sheet>
                        <group>
                            <group>
                                <field name="cutoff_date" />
                                <field name="patient_group"/>
                                <field name="patient_type"/>
                                <field name="patient_type_name"/>
                                <field name="admission_id"/>
                                <field name="odoo_admission_id"/>
                                <field name="admission_number"/>
                                <field name="admission_date"/>
                                <field name="patient_id"/>
                                <field name="odoo_patient_id"/>
                                <field name="patient_mrid"/>
                                <field name="patient_ref_no"/>
                                <field name="patient_name"/>
                                <field name="ward_id"/>
                                <field name="odoo_ward_id"/>
                                <field name="ward_name"/>
                                <field name="doctor_primary_id"/>
                                <field name="odoo_doctor_primary_id"/>
                                <field name="doctor_primary_code"/>
                                <field name="doctor_primary_name"/>
                                <field name="amount"/>
                            </group>
                            <group>
                                <field name="payor_id"/>
                                <field name="odoo_payor_id"/>
                                <field name="payor_code"/>
                                <field name="payor_name"/>
                                <field name="payor_type"/>
                                <field name="tariff_id"/>
                                <field name="odoo_tariff_id"/>
                                <field name="tariff_name"/>
                                <field name="alloted_bed_type_id"/>
                                <field name="odoo_alloted_bed_type_id"/>
                                <field name="alloted_bed_type_name"/>
                                <field name="eligible_bed_type_id"/>
                                <field name="odoo_eligible_bed_type_id"/>
                                <field name="eligible_bed_type_name"/>
                                <field name="room_id"/>
                                <field name="odoo_room_id"/>
                                <field name="room_name"/>
                                <field name="bed_id"/>
                                <field name="odoo_bed_id"/>
                                <field name="bed_name"/>
                                
                            </group>
                        </group>
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" />
                                        <field name="sync_id_api" readonly="1" />
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
                <tree string="Accrual Billing" delete="0" create="0" decoration-danger="state == 'cancel'" decoration-info="state == 'draft'" decoration-success="state=='confirm'">
                    <field name="cutoff_date" />
                    <field name="admission_number"/>
                    <field name="admission_date"/>
                    <field name="patient_name"/>
                    <field name="patient_group"/>
                    <field name="tpa_name"/>
                    <field name="amount"/>
                    <field name="state"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Accrual Billing Search">
                    <field name="admission_number"/>
                    <field name="tpa_name"/>
                    <field name="payor_name"/>
                    <field name="patient_name"/>
                </search>
            """
        elif view_type == 'pivot':
            res['arch'] = """
                <pivot string="Accrual Billing">
                    <field name="amount" type="measure"/>
                </pivot>
           """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class ReceivableUnbilledWizard(models.TransientModel):
    _name = 'receivable.unbilled.wizard'

    @api.model
    def _get_user_id(self):
        return self.env.user.id

    company_id = fields.Many2one('res.company', string="Company", required=False)
    start_date = fields.Date(string="Bill Start", required=True)
    end_date = fields.Date(string="Bill End", required=True)
    user_id = fields.Many2one('res.users', string="User ID", default=_get_user_id)



    # @api.multi
    def show_report(self):
        action = {}
        action['target'] = 'current'
        if self.company_id:
            action['domain'] = "[('state', 'not in', ('invoice', 'cancel')), ('sync_is_arcus', '=', True), ('bill_date', '>=', '%s'), ('bill_date', '<=', '%s'), ('company_id', '=', %s)]" % (self.start_date, self.end_date, self.company_id.id)
        else:
            action['domain'] = "[('state', 'not in', ('invoice', 'cancel')), ('sync_is_arcus', '=', True), ('bill_date', '>=', '%s'), ('bill_date', '<=', '%s')]" % (self.start_date, self.end_date)

        action['type'] = 'ir.actions.act_window'
        action['view_mode'] = 'tree,form,pivot'
        action['view_type'] = 'form'
        action['res_model'] = 'sale.order.bill'
        action['name'] = 'Unbilled Analysis Report'
        action['views'] = [(self.sudo().env.ref('mayapada.view_unbilled_analysis_pivot').id, 'pivot'), (False, 'tree'), (False, 'form')]
        return action



class ARReportWizard(models.TransientModel):
    _name = 'account.receivable.report.wizard'

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    format_print_id = fields.Selection([('pdf','PDF'),('xls','EXCEL')], string="Format", required=True, readonly=True, default='xls')
    date_start = fields.Date(string="Date Start", required=False)
    date_end = fields.Date(string="Date End", required=False)
    payment_date_start = fields.Date(string="Payment Date Start", required=False)
    payment_date_end = fields.Date(string="Payment Date End", required=False)
    cutoff_date = fields.Date(string="Cutoff Date", required=False)
    partner_id = fields.Many2one('res.partner', index=False, string="Customer")
    partner_ids = fields.Many2many('res.partner', string="Customers")
    # bank_ids = fields.Many2many('account.account', string="Bank")
    type_report = fields.Selection([
        ('deposit', 'Deposit Patient'),
        ('advance', 'Deposit Payor'),
        ('discount', 'Deposit Credit Note'),
        ('accrual', 'AR Accrual'),
        ('unbilled', 'AR Patient Unbilled'),
        ('aging_bill', 'AR Aging Per Billing'),
        ('aging_payor', 'AR Aging Per Payor'),
        ('aging_invoice', 'AR Aging Per Invoice'),
        ('aging_tracking_payer', 'AR Tracking Per Payer'),
        ('aging_tracking_invoice', 'AR Tracking Per Invoice')], string='Type Report', required=True)

    interval_month = fields.Selection([('1','1'),('2','2'),('3','3'),('4','4'),('5','5'),('6','6')], string="Interval Month", default='1')


    def print_ar(self):
        if self.type_report in ('aging_tracking_payer', 'aging_tracking_invoice'):
            if any([self.payment_date_start <= self.cutoff_date, self.payment_date_end <= self.cutoff_date]):
                raise exceptions.ValidationError(_("Payment date harus lebih besar dari cutoff date."))

        if self.type_report == 'discount':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_deposit_creditnote?id=' + str(self.id)
            action['target'] = 'new'
            return action
            
        if self.type_report == 'deposit':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_deposit_patient?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'advance':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_deposit_payor?id=' + str(self.id)
            action['target'] = 'new'
            return action
        
        if self.type_report == 'unbilled':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_patient_unbilled?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'accrual':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_ip_accrual?id=' + str(self.id)
            action['target'] = 'new'
            return action
        
        if self.type_report == 'aging_bill':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_aging_bill?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'aging_payor':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_aging_payor?id=' + str(self.id)
            action['target'] = 'new'
            return action
        
        if self.type_report == 'aging_invoice':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/report_aging_invoice?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'aging_tracking_payer':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/aging_tracking_payer_arcus?id=' + str(self.id)
            action['target'] = 'new'
            return action

        if self.type_report == 'aging_tracking_invoice':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/aging_tracking_invoice_arcus?id=' + str(self.id)
            action['target'] = 'new'
            return action
