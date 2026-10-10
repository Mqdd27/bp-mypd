from . import datas
from . import sync
from datetime import datetime, timedelta
from pyjasperclient import JasperClient
from decimal import Decimal, ROUND_HALF_UP
#from datetime import datetime
import calendar
from functools import reduce
from odoo.osv import expression
from odoo import models, http, fields, api, tools, exceptions, _
from odoo.exceptions import UserError, ValidationError, Warning
from odoo.http import request, serialize_exception, content_disposition
from odoo.tools import float_is_zero, float_compare
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from odoo.addons import decimal_precision as dp
from num2words import num2words
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
from bottle import route
import re

import io
import csv
import hashlib
import base64
logger = logging.getLogger(__name__)

def to_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except:
        return None

class PayableSupplier(models.Model):
    _name = 'payable.supplier'
    _description = 'AP Supplier'
    _rec_name = 'title'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    title = fields.Char(string="Title") 
    supplier_code = fields.Char(string='Supplier Code', track_visibility='always')
    supplier_name = fields.Char(string='Supplier Name', track_visibility='always')
    supplier_term_day = fields.Integer(string="Supplier T.O.P", track_visibility='always')
    supplier_address = fields.Text(string='Supplier Address', track_visibility='always')
    supplier_type = fields.Selection([
        ('AP CASHCHEQUE','AP CASHCHEQUE'),
        ('AP CATHLAB','AP CATHLAB'),
        ('AP DOCTOR FEE','AP DOCTOR FEE'),
        ('AP GENERAL','AP GENERAL'),
        ('AP MEDICAL','AP MEDICAL'),
        ('AP FIXED ASSET','AP FIXED ASSET'),
        ('AP CATERING','AP CATERING'),
        ('AP HOUSEKEEPING','AP HOUSEKEEPING'),
        ('AP OTHERS','AP OTHERS')
    ], string="Supplier Type", track_visibility='always', default='AP GENERAL')
    supplier_account_payable_id = fields.Many2one('account.account', string="Supplier COA AP", track_visibility='always')
    supplier_account_interim_id = fields.Many2one('account.account', string="Supplier COA Interim", track_visibility='always')
    supplier_notes = fields.Char(string='Supplier Notes')
    supplier_bank_ids = fields.One2many('payable.supplier.bank', 'supplier_id', string="Supplier Banks")
    supplier_mapping_ids = fields.One2many('res.partner', 'supplier_id', string="Supplier Mapping")    


    @api.model
    def create(self, vals):
        record = super(PayableSupplier, self).create(vals)
        supplier_code = self.env['ir.sequence'].sudo().next_by_code('payable.supplier.sequence')
        
        record.with_context(skip_name_update=True).write({
            'supplier_code': supplier_code,
            'supplier_name': (record.supplier_name or '').upper(),
            'title': '{} {}'.format(supplier_code, (record.supplier_name or '').upper()),
        })

        if record.supplier_bank_ids:
            for bank in record.supplier_bank_ids:
                bank.write({'title': '{} {} / {} - {}'.format(record.supplier_code, record.supplier_name, bank.supplier_bank_id.name, bank.supplier_bank_account) })
        return record


    # @api.multi
    def write(self, vals):
        if self.env.context.get('skip_name_update'):
            return super(PayableSupplier, self).write(vals)

        res = super(PayableSupplier, self).write(vals)

        for record in self:
            # Refresh data supaya cache lama nggak dipakai
            record.refresh()

            supplier_name = (record.supplier_name or '').upper()
            title = '{} {}'.format(record.supplier_code or '', supplier_name)

            # Update lagi secara langsung dengan context khusus
            record.with_context(skip_name_update=True).write({
                'supplier_name': supplier_name,
                'title': title
            })

            if record.supplier_bank_ids:
                for bank in record.supplier_bank_ids:
                    bank.write({'title': '{} {} / {} - {}'.format(record.supplier_code, record.supplier_name, bank.supplier_bank_id.name, bank.supplier_bank_account) })
        return res



class PayableSupplierBank(models.Model):
    _name = 'payable.supplier.bank'
    _description = 'AP Supplier Bank'
    _rec_name = 'title'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    supplier_id = fields.Many2one('payable.supplier', string='Supplier')
    title = fields.Char(string='Title')
    supplier_bank_id = fields.Many2one('res.bank', string="Bank")
    supplier_bank_account = fields.Char(string='Account')
    supplier_bank_beneficary = fields.Char(string='Beneficary')
    supplier_bank_branch = fields.Char(string='Branch')
    supplier_bank_llg = fields.Float(string='LLG')
    supplier_bank_rtgs = fields.Float(string='RTGS')
    supplier_bank_bifast = fields.Float(string='BI-Fast')


    @api.model
    def create(self, vals):
        record = super(PayableSupplierBank, self).create(vals)
        record.with_context(skip_name_update=True).write({'title': '{} / {} - {}'.format(record.supplier_bank_id.name, record.supplier_bank_beneficary, record.supplier_bank_account) })
        return record


    # @api.multi
    def write(self, vals):
        if self.env.context.get('skip_name_update'):
            return super(PayableSupplierBank, self).write(vals)
        res = super(PayableSupplierBank, self).write(vals)

        for record in self:
            record.refresh()
            record.with_context(skip_name_update=True).write({'title': '{} / {} - {}'.format(record.supplier_bank_id.name, record.supplier_bank_beneficary, record.supplier_bank_account) })
        return res


class PayableInvoice(models.Model):
    _name = 'payable.invoice'
    _description = 'AP Invoice'
    _rec_name = 'title'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id
    
    @api.model
    def _get_user(self):
        return self.env.user.id

    @api.model 
    def _get_ctx_readonly(self):
        return bool(self.env.context.get('default_readonly', False))

    ctx_readonly = fields.Boolean(store=False, default=_get_ctx_readonly)
    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    title = fields.Char(string="Title") 
    invoice_no = fields.Char(string="Invoice No.", help="No. invoice vendor pada internal sistem ERP, Auto-generate by Odoo") 
    invoice_date = fields.Date(string="Invoice Date", help="Tgl. invoice diisi sesuai tanggal perhitungan AP", default=fields.Date.today, track_visibility='always')
    invoice_duedate = fields.Date(string="Invoice DueDate", help="Tgl. jatuh tempo sesuai pengakuan tgl. invoice + supplier T.O.P")
    invoice_exchange_date = fields.Date(string="Invoice Exchange Date", help="Tgl. aktual proses tukar faktur di lapangan")
    
    invoice_type = fields.Selection([
        ('INVOICE_DP', 'DOWN PAYMENT'),
        ('INVOICE_IB', 'INBOUND INVOICE'),
        ('INVOICE_RF', 'REFUND INVOICE')
    ], string="Invoice Type", default='INVOICE_IB', help="DOWN PAYMENT = Untuk penerbitan invoice DP/Advance ke Supplier atas PO Non Stock \nINBOUND INVOICE = Untuk penerbitan invoice dari supplier baik untuk PO/GR/Cash\nREFUND INVOICE = Untuk penerbitan refund atas invoice vendor guna mengurangi tagihan invoice vendor.", track_visibility='always')
    invoice_ref = fields.Char(string="Invoice Ref", help="Isi dengan referensi nomor PO/GRN yang sudah diterbitkan faktur")
    invoice_notes = fields.Char(string='Invoice Notes', help="Isi dengan data berkas faktur asli dari supplier.")
    invoice_source = fields.Selection([
        ('PO_HIS','PO HIS_STOCK'),
        ('PO_ERP','PO ERP_NON_STOCK'),
        ('WITHOUT_PO','WITHOUT_PO')
    ], string="Invoice Sources", default='PO_HIS', help="Tentukan jenis sumber dokumen yang ingin diterbitkan invoice sesuai faktur supplier")
    invoice_po_id = fields.Many2one('purchase.order', string="Purchase No.", help="Pilih referensi PO yang ingin dilakuan pembayaran")
    invoice_responsible_id = fields.Many2one('res.users', string="Responsible", help="Pilih user yang bertanggungjawab atas penerbitan faktur vendor ini.", default=_get_user)
    invoice_reverse_id = fields.Many2one('payable.invoice', string="Reverse Invoice")


    supplier_type = fields.Selection([
        ('AP CASHCHEQUE','AP CASHCHEQUE'),
        ('AP CATHLAB','AP CATHLAB'),
        ('AP DOCTOR FEE','AP DOCTOR FEE'),
        ('AP GENERAL','AP GENERAL'),
        ('AP MEDICAL','AP MEDICAL'),
        ('AP FIXED ASSET','AP FIXED ASSET'),
        ('AP CATERING','AP CATERING'),
        ('AP HOUSEKEEPING','AP HOUSEKEEPING'),
        ('AP OTHERS','AP OTHERS')
    ], string="Supplier Type", help="Pilih tipe supplier", default='AP GENERAL')
    supplier_id = fields.Many2one('payable.supplier', string='AP Supplier', help="Pilih group supplier untuk penentuan tracking AP Aging")
    supplier_account_payable_id = fields.Many2one('account.account', string="Supplier COA AP", help="Tentukan COA AP yang akan di plot pada ledger")
    supplier_account_interim_id = fields.Many2one('account.account', string="Supplier COA Interim", help="Tentukan COA Debit yang akan di plot pada ledger")
    supplier_term_day = fields.Integer(string='Supplier T.O.P', help="Tentukan T.O.P untuk menghitung tanggal jatuh tempo faktur supplier")
    
    invoice_total = fields.Float(string="Invoice Total", help="Invoice Total = Total tagihan pada GR sebelum Discount dan Taxes")
    invoice_discount = fields.Float(string="Invoice Discount", help="Invoice Dicount = Total discount pada GR")
    invoice_untaxed = fields.Float(string="Invoice Untaxed", help="Invoice Untaxed = Total tagihan dari seluruh GR setelah dikurangi Discount")
    invoice_tax = fields.Float(string="Invoice Tax", help="Invoice Tax = Total tax dari seluruh tagihan GR")
    invoice_subtotal = fields.Float(string="Invoice Taxed", help="Invoiced Taxed = Total invoice yang akan diakui sebagai AP Aging", track_visibility='always')
    invoice_deduction = fields.Float(string="Deduction", help="Deduction = Total pengurangan tagihan atas AP Invoice bisa berasal dari Payment Outbound, CreditNote/WriteOff, ataupun pengurangan dari Down-Payment yang sudah dibayarkan sebelumnya.")
    invoice_addition = fields.Float(string="Addition", help="Addition = Total penambahan tagihan atas AP Invoice bisa berasal dari DebitNote Supplier")
    invoice_balance = fields.Float(string="Balance", help="Balance = Nilai Balance/Outstanding atas AP Invoice berasal dari Invoice Taxed - Deduction + Addition")
    dp_amount = fields.Float(string="DP Amount")
    refund_amount = fields.Float(string="Refund Amount")
    
    efaktur_no = fields.Char(string="E-Faktur No.", help="Isi dengan No. EFaktur yang diterbitkan dari supplier")
    efaktur_date = fields.Date(string="E-Faktur Date.", help="Isi dengan Tgl. Efaktur yang diterbitkan dari supplier")
    state = fields.Selection([('draft', 'Draft'),('confirm', 'Confirm'),('cancel', 'Cancel') ], string='State', default='draft', required=True, track_visibility='always')
    move_id = fields.Many2one('account.move', string="Entries No.")

    invoice_payment_ids = fields.One2many('payable.payment.line', 'payable_invoice_id', string="Invoice Payments", help="List pembayaran atas AP Invoice")
    invoice_adjustment_ids = fields.One2many('payable.adjustment', 'invoice_id', string="Invoice Credit/DebitNote", help="List Credit/DebitNote atas AP Invoice")
    invoice_deduction_ids = fields.One2many('payable.invoice', 'invoice_reverse_id', string="Deductions", help="List pengurangan dari Refund dan DP atas AP Invoice")
    invoice_purchase_ids = fields.Many2many('purchase.order', 'payable_invoice_purchase_rel', 'payable_invoice_id', string="PO", help="List PO/GRN yang ingin diterbitkan faktur supplier")
    invoice_entries_ids = fields.One2many('account.move', 'payable_invoice_id', string="Entries", help="List journal AP Traceability")
    invoice_line_ids = fields.One2many('payable.invoice.line', 'payable_invoice_id', string="Items", help="List invoice items")
    move_line_ids = fields.One2many('account.move.line', 'payable_invoice_id', string="Entry Items")

    # @api.multi
    def action_print(self):
        print ("print action_print")

    @api.model
    def default_get(self, fields):
        res = super(PayableInvoice, self).default_get(fields)
        if self.env.context.get('trigger_on_edit'):
            self._onchange_invoice_source()
        return res

    @api.onchange('supplier_id')
    def _onchange_supplier_id(self):
        for record in self:
            if record.supplier_id:
                record.supplier_term_day = record.supplier_id.supplier_term_day
                record.supplier_account_payable_id = record.supplier_id.supplier_account_payable_id
                record.supplier_account_interim_id = record.supplier_id.supplier_account_interim_id
                record._onchange_supplier_term_day()


    @api.onchange('supplier_type')
    def _onchange_supplier_type(self):
        for record in self:
            if record.supplier_type and not self.env.context.get('default_supplier_id'):
                record.supplier_id = False 
                record.supplier_term_day = False
                record.supplier_account_payable_id = False
                record.supplier_account_interim_id = False 
  


    @api.onchange('supplier_term_day','invoice_exchange_date')
    def _onchange_supplier_term_day(self):
        for record in self:
            if record.supplier_term_day and record.invoice_exchange_date:
                record.invoice_duedate = record.invoice_exchange_date + timedelta(days=int(record.supplier_term_day))
    

    @api.onchange('invoice_source', 'company_id')
    @api.depends('invoice_source', 'company_id')
    def _onchange_invoice_source(self):
        domain = [('company_id', '=', self.company_id.id)]
        domain += [('state','in', ['done','purchase'])]
        domain += [('payable_invoice_id','=', False)]

        if self.invoice_source == 'PO_ERP':
            domain += [('sync_id_api', '=', False), ('sync_id', '=', False)]

        elif self.invoice_source == 'PO_HIS':
            domain += ['|', ('sync_id_api', '!=', False), ('sync_id', '>', 0)]

        return {'domain': {'invoice_purchase_ids': domain}}



    @api.onchange('invoice_type','dp_amount','refund_amount')
    @api.depends('invoice_type','dp_amount','refund_amount')
    def _onchange_invoice_type(self):
        for record in self:
            if record.invoice_type == 'INVOICE_DP':
                total = record.dp_amount or 0.0 
                record.invoice_total = total 
                record.invoice_subtotal = total 
                record.invoice_balance = total 
            if record.invoice_type == 'INVOICE_RF':
                total = record.refund_amount or 0.0 
                record.invoice_total = total 
                record.invoice_subtotal = total 
                record.invoice_balance = total




    
    @api.onchange('invoice_purchase_ids')
    def _onchange_invoice_purchase_ids(self):
        for record in self:
            if record.invoice_purchase_ids and not self.env.context.get('invoice_ref'):
                # Ambil semua title dari PO yang dipilih
                po_titles = record.invoice_purchase_ids.mapped('title')
                # Gabungkan jadi satu string, misalnya dipisah koma
                record.invoice_ref = ', '.join([t for t in po_titles if t])
                record.action_compute_total()
            

                

    @api.model
    def create(self, vals):
        self._check_invoice_date(vals.get('invoice_date'))
        record = super(PayableInvoice, self).create(vals)

        if record.invoice_type == 'INVOICE_RF':
            sequence_id = 'payable.invoice.refund.sequence'
        elif record.invoice_type == 'INVOICE_DP':
            sequence_id = 'payable.invoice.dp.sequence'
        else:
            sequence_id = 'payable.invoice.inbound.sequence'
    
        record.invoice_no = self.env['ir.sequence'].sudo().next_by_code(sequence_id)
        record.with_context(skip_name_update=True).write({'title': '{} / {}'.format(record.invoice_no, record.supplier_id.title) })
        return record


    # @api.multi
    def write(self, vals):
        # Cek hanya jika invoice_date diubah
        if 'invoice_date' in vals:
            self._check_invoice_date(vals.get('invoice_date'))
        # if self.state == 'draft' and not self.env.context.get('skip_total_compute'):
        #     self.action_compute_total()

        if not self.env.context.get('skip_total_compute'):
            for rec in self:
                if rec.state == 'draft':
                    rec.action_compute_total()

        if self.env.context.get('skip_name_update') or self.env.context.get('skip_total_compute'):
            return super(PayableInvoice, self).write(vals)

        res = super(PayableInvoice, self).write(vals)
        for record in self:
            record.refresh()
            record.with_context(skip_name_update=True).write({'title': '{} / {}'.format(record.invoice_no, record.supplier_id.title) })
        return res

    

    # @api.multi
    def button_journal_entries(self):
        return {
            'name': _('Journal Items'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('payable_invoice_id', 'in', self.ids)],
        }

    # # fungsi rounding
    # def round2(value):
    #     return float(Decimal(value).quantize(Decimal('0.00'), rounding=ROUND_HALF_UP))

    # @api.multi
    def action_compute_total(self):
        from odoo.tools import float_round
        for record in self:

            if record.state != 'draft':
                raise UserError(_('Only invoices with Draft status can be compute total.'))

            total_po = total_discount = total_tax = total_net = 0
            if record.invoice_type == 'INVOICE_IB':
                # source dari PO ERP/HIS
                if record.invoice_source in ['PO_HIS','PO_ERP'] and record.invoice_purchase_ids:
                    for po in record.invoice_purchase_ids:
                        if po.is_return is True:
                            total_tax -= abs(po.ppn or 0.0)
                            total_discount -= abs(po.total_discount or 0.0)
                            total_net -= abs(po.amount_total or 0.0)
                            total_po -= (abs(po.amount_total or 0.0) - abs(po.ppn or 0.0) + abs(po.total_discount or 0.0))
                        else:
                            total_tax += po.ppn
                            total_discount += po.total_discount
                            total_net += po.amount_total 
                            total_po += (po.amount_total - po.ppn + po.total_discount)

                # WITHOUT_PO, PO_HIS, PO_ERP > akomodir total item dari invoice_line_ids
                if record.invoice_line_ids:
                    for line in record.invoice_line_ids:
                        total_po += line.item_amount or 0.0
                        total_net += line.item_amount or 0.0

            if record.invoice_type == 'INVOICE_DP':
                total_po = record.dp_amount or 0.0
                total_net = record.dp_amount or 0.0 

            if record.invoice_type == 'INVOICE_RF':
                total_po = record.refund_amount or 0.0
                total_net = record.refund_amount or 0.0 

            total_po = float_round(total_po, precision_digits=2)
            total_discount = float_round(total_discount, precision_digits=2)
            total_tax = float_round(total_tax, precision_digits=2)
            total_net = total_po - total_discount + total_tax

            record.with_context(skip_name_update=True, skip_total_compute=True).write({
                'invoice_total': total_po,
                'invoice_discount': total_discount,
                'invoice_untaxed': total_po - total_discount,
                'invoice_tax': total_tax, 
                'invoice_subtotal': total_net, 
                'invoice_deduction': 0, 
                'invoice_addition': 0, 
                'invoice_balance': 0
            })

            # record.with_context(skip_name_update=True, skip_total_compute=True).write({
            #     'invoice_total': round2(total_po),
            #     'invoice_discount': round2(total_discount),
            #     'invoice_untaxed': round2(total_po - total_discount),
            #     'invoice_tax': round2(total_tax),
            #     'invoice_subtotal': round2(total_net),
            #     'invoice_deduction': round2(0),
            #     'invoice_addition': round2(0),
            #     'invoice_balance': round2(0),
            # })
        return True 


    # @api.multi
    def action_compute_balance(self):
        for record in self:
            total_deduction = total_addition = 0

            # pengurangan ivnoice DP
            if record.invoice_deduction_ids:
                for deduct in record.invoice_deduction_ids:
                    if deduct.state == 'confirm' and deduct.invoice_type in['INVOICE_DP','INVOICE_RF']:
                        total_deduction += deduct.invoice_subtotal or 0.0 

            # ambil adjustment
            if record.invoice_adjustment_ids:
                for adjust in record.invoice_adjustment_ids:
                    if adjust.state == 'confirm' and adjust.adjust_type == 'CN':
                        total_deduction += adjust.adjust_amount or 0.0 
                    if adjust.state == 'confirm' and adjust.adjust_type == 'DN':
                        total_addition += adjust.adjust_amount or 0.0 

            # ambil payment
            if record.invoice_payment_ids:
                for payment in record.invoice_payment_ids:
                    if payment.state == 'confirm':
                        total_deduction += payment.payment_amount or 0.0 
            
            record.invoice_addition = total_addition
            record.invoice_deduction = total_deduction 
            record.invoice_balance = record.invoice_subtotal + total_addition - total_deduction

            # jika ada source invoice, invoice awal harus di compute 
            if record.invoice_reverse_id:
                record.invoice_reverse_id.action_compute_balance()

        return True 


    # @api.multi
    def action_create_entries(self):
        for record in self:
            account_interim_id = record.supplier_account_interim_id.id or None 
            account_payable_id = record.supplier_account_payable_id.id or None 
            account_journal_id = self.sudo().env['account.journal'].search([('name','=', 'AP Traceability'), ('company_id','=', record.company_id.id)], limit=1).id or None 

            if not account_interim_id:
                raise UserError(_('Please mapping account interim.'))
            if not account_payable_id:
                raise UserError(_('Please mapping account payable.'))
            if not account_journal_id:
                raise UserError(_('Please define jpournal AP Traceability.'))


            line_ids = []
            if record.invoice_type == 'INVOICE_IB':
                credit_vals = { 'name': str(record.invoice_no) + ' / ' + str(record.supplier_id.title) + ' / ' + (record.invoice_ref or ''), 'date_maturity': record.invoice_duedate, 'credit': abs(record.invoice_subtotal), 'debit': 0.0, 'account_id': account_payable_id, 'payable_invoice_id': record.id}
                line_ids.append((0, 0, credit_vals))

                # jika ada invoice_item maka breakdown journal_item per line diluar total PO+taxes
                invoice_total_item = 0
                if record.invoice_line_ids:
                    for line in record.invoice_line_ids:
                        invoice_total_item += line.item_amount or 0.0
                        line_ids.append((0, 0, {
                            'name': str(record.invoice_no) + ' / ' + str(line.item_name) + ' / ' + (record.invoice_ref or ''), 
                            'date_maturity': record.invoice_duedate, 
                            'credit': abs(0.0 if line.item_amount > 0 else line.item_amount), 
                            'debit': abs(line.item_amount if line.item_amount > 0 else 0.0), 
                            'account_id': line.item_account_id.id or account_interim_id, 
                            'payable_invoice_id': record.id
                        }))

                invoice_subtotal = record.invoice_subtotal or 0.0 
                invoice_subtotal -= invoice_total_item

                if invoice_subtotal > 0:
                    if (record.invoice_tax or 0.0) == 0:
                        debit_vals = { 'name': str(record.invoice_no) + ' / ' + str(record.supplier_id.title) + ' / ' + (record.invoice_ref or ''), 'date_maturity': record.invoice_duedate, 'debit': abs(invoice_subtotal), 'credit': 0.0, 'account_id': account_interim_id, 'payable_invoice_id': record.id}
                        line_ids.append((0, 0, debit_vals))

                    # jika ada taxes maka line items dibuat terpisah u/ rekon PPN masukan
                    else:
                        invoice_subtotal_wo_tax = invoice_subtotal - record.invoice_tax
                        invoice_tax = record.invoice_tax
                            
                        debit_vals = { 'name': str(record.invoice_no) + ' / ' + str(record.supplier_id.title) + ' / ' + (record.invoice_ref or ''), 'date_maturity': record.invoice_duedate, 'debit': abs(invoice_subtotal_wo_tax), 'credit': 0.0, 'account_id': account_interim_id, 'payable_invoice_id': record.id}
                        debit_tax_vals = { 'name': 'TAX OF ' + str(record.invoice_no) + ' / ' + str(record.supplier_id.title) + ' / ' + (record.invoice_ref or ''), 'date_maturity': record.invoice_duedate, 'debit': abs(invoice_tax if invoice_tax > 0 else 0.0), 'credit': abs(0 if invoice_tax > 0 else invoice_tax), 'account_id': account_interim_id, 'payable_invoice_id': record.id}

                        line_ids.append((0, 0, debit_vals))
                        line_ids.append((0, 0, debit_tax_vals))

                


                #  reverse DP yang di attach pertama kali
                if record.invoice_deduction_ids:
                    for dp in record.invoice_deduction_ids:
                        # bentuk jurnal pembalik jika ada reverse INVOICE_DP, jika reverse INVOICE_RF tidak perlu dibentuk jurnal pembalik karena sudah ada jurnal sebelumnya (hanya perlu di netting)
                        if dp.invoice_type == 'INVOICE_DP' and dp.state == 'confirm':
                            line_ids.append((0, 0, { 'name': 'REVERSE DP FOR ' + str(dp.invoice_no) + ' / ' + str(record.supplier_id.title) + ' / ' + (dp.invoice_ref or ''), 'date_maturity': record.invoice_duedate, 'credit': abs(dp.invoice_subtotal), 'debit': 0.0, 'account_id': account_interim_id, 'payable_invoice_id': record.id}))
                            line_ids.append((0, 0, { 'name': 'REVERSE DP FOR ' + str(dp.invoice_no) + ' / ' + str(record.supplier_id.title) + ' / ' + (dp.invoice_ref or ''), 'date_maturity': record.invoice_duedate, 'debit': abs(dp.invoice_subtotal), 'credit': 0.0, 'account_id': account_payable_id, 'payable_invoice_id': record.id}))


            if record.invoice_type == 'INVOICE_RF':
                debit_vals = { 'name': 'REFUND OF ' + str(record.invoice_reverse_id.invoice_no) + ' / ' + str(record.supplier_id.title) + ' / ' + (record.invoice_reverse_id.invoice_ref or ''), 'date_maturity': record.invoice_duedate, 'debit': abs(record.invoice_subtotal), 'credit': 0.0, 'account_id': account_payable_id, 'payable_invoice_id': record.invoice_reverse_id.id}
                credit_vals = { 'name': 'REFUND OF' + str(record.invoice_reverse_id.invoice_no) + ' / ' + str(record.supplier_id.title) + ' / ' + (record.invoice_reverse_id.invoice_ref or ''), 'date_maturity': record.invoice_duedate, 'credit': abs(record.invoice_subtotal), 'debit': 0.0, 'account_id': account_interim_id, 'payable_invoice_id': record.invoice_reverse_id.id}

                line_ids.append((0, 0, debit_vals))
                line_ids.append((0, 0, credit_vals))


            if record.invoice_type == 'INVOICE_DP':
                debit_vals = { 'name': str(record.invoice_no) + ' / ' + str(record.supplier_id.title) + ' / ' + (record.invoice_ref or ''), 'date_maturity': record.invoice_duedate, 'debit': abs(record.invoice_subtotal), 'credit': 0.0, 'account_id': account_interim_id, 'payable_invoice_id': record.id}
                credit_vals = { 'name': str(record.invoice_no) + ' / ' + str(record.supplier_id.title) + ' / ' + (record.invoice_ref or ''), 'date_maturity': record.invoice_duedate, 'credit': abs(record.invoice_subtotal), 'debit': 0.0, 'account_id': account_payable_id, 'payable_invoice_id': record.id}

                line_ids.append((0, 0, debit_vals))
                line_ids.append((0, 0, credit_vals))

            

            # open('/opt/odoo16/logs/dudi.log','a+').write('\n ' + 'line_ids4: ' + str(line_ids))
            record.move_id = record.env['account.move'].create({'journal_id': account_journal_id, 'date': record.invoice_date, 'state': 'draft', 'name': record.invoice_no, 'ref': str(record.invoice_no) + ' / ' + str(record.supplier_id.title), 'payable_invoice_id': record.id, 'line_ids': line_ids})
            record.move_id.action_post()
            record.move_id.name = record.invoice_no     
        return True




    @api.onchange('invoice_reverse_id')
    def _onchange_invoice_reverse_id(self):
        for record in self:
            if record.invoice_type == 'INVOICE_RF' and record.invoice_reverse_id:
                today = fields.Date.context_today(self)
                record.invoice_date = today
                record.supplier_type = record.invoice_reverse_id.supplier_type or False
                record.supplier_id = record.invoice_reverse_id.supplier_id.id or False
                record.supplier_term_day = record.invoice_reverse_id.supplier_term_day
                record.supplier_account_payable_id = record.invoice_reverse_id.supplier_account_payable_id.id or False
                record.supplier_account_interim_id = record.invoice_reverse_id.supplier_account_interim_id.id or False
                record.invoice_duedate = record.invoice_reverse_id.invoice_duedate
                record.invoice_exchange_date = today
                record.invoice_ref = record.invoice_reverse_id.invoice_ref
                record.invoice_source = record.invoice_reverse_id.invoice_source
                record.invoice_notes = 'REFUND OF ' + (record.invoice_reverse_id.invoice_no or '')
                record.refund_amount = record.invoice_reverse_id.invoice_balance or 0.0


    @api.onchange('invoice_po_id')
    def _onchange_invoice_po_id(self):
        for record in self:
            if record.invoice_type == 'INVOICE_DP' and record.invoice_po_id:
                record.invoice_ref = record.invoice_po_id.title
                record.invoice_notes = 'DP FOR ' + (record.invoice_po_id.title or '')
                record.dp_amount = record.invoice_po_id.amount_total or 0.0


    
    # @api.multi
    def action_refund(self):
        for record in self:
            if record.invoice_type not in ['INVOICE_IB','INVOICE_DP']:
                raise UserError(_('Only DP/Inbound invoices with Confirm status can be refund.'))

            # ambil tanggal hari ini sesuai timezone Odoo user
            today = fields.Date.context_today(self)

            # hitung due date = hari ini + supplier_term_day
            supplier_term_days = record.supplier_term_day or 0
            due_date = fields.Date.to_string(
                fields.Date.from_string(today) + timedelta(days=supplier_term_days)
            )

            action = {
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'view_type': 'form',
                'res_model': 'payable.invoice',
                'name': _('Create Refund for AP Invoice'),
                'views': [(False, 'form')],
                'context': {
                    'default_company_id': record.company_id.id,
                    'default_invoice_date': today,
                    'default_supplier_type': record.supplier_type or False,
                    'default_supplier_id': record.supplier_id.id or False,
                    'default_supplier_term_day': supplier_term_days,
                    'default_supplier_account_payable_id': record.supplier_account_payable_id.id or False,
                    'default_supplier_account_interim_id': record.supplier_account_interim_id.id or False,
                    'default_invoice_duedate': record.invoice_duedate,
                    'default_invoice_exchange_date': today,
                    'default_invoice_type': 'INVOICE_RF',
                    'default_invoice_ref': record.invoice_ref,
                    'default_invoice_source': record.invoice_source,
                    'default_invoice_notes': 'REFUND OF ' + (record.invoice_no or ''),
                    'default_invoice_reverse_id': record.id,
                    'default_readonly': True,
                    'default_refund_amount': record.invoice_balance or 0.0
                }
            }
            return action
        return True



            

    # @api.multi
    def action_confirm(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only invoices with Draft status can be confirm.'))

            record._check_invoice_date()
            record.action_compute_total()
            if record.invoice_subtotal < 0:
                raise UserError(_('Invoice subtotal (invoice taxed) cannot be negative.'))

            record.action_compute_balance()
            record.state = 'confirm'
            #if record.invoice_purchase_ids:
            #    record.sudo().invoice_purchase_ids.write({'payable_invoice_id': record.id})

            if record.invoice_purchase_ids:
                for po in record.invoice_purchase_ids:
                    po.sudo().write({'payable_invoice_id': record.id})

            record.action_create_entries()
            record.action_compute_balance()
        return True

    
    # @api.multi
    def action_unconfirm(self):
        for record in self:
            if record.state != 'confirm':
                raise UserError(_('Only invoices with Confirm status can be unconfirm.'))

            if record.invoice_payment_ids.filtered(lambda x : x.state in['draft','confirm']):
                raise UserError(_('Only invoices without Payment Outbound can be unconfirm.'))

            if record.invoice_adjustment_ids.filtered(lambda x : x.state in['draft','confirm']):
                raise UserError(_('Only invoices without Credit/DebitNote can be unconfirm.'))

            if record.invoice_deduction_ids.filtered(lambda x: x.invoice_type == 'INVOICE_RF' and x.state in ['draft','confirm']):
                raise UserError(_('Only invoices without Deduction (Refund) can be unconfirm.'))

                

            record.state = 'draft'

            if record.move_id:
                record.move_id.button_cancel()
                record.move_id.unlink()

            #if record.invoice_purchase_ids:
            #    record.sudo().invoice_purchase_ids.write({'payable_invoice_id': None})

            if record.invoice_purchase_ids:
                for po in record.invoice_purchase_ids:
                    po.sudo().write({'payable_invoice_id': None})

            for dp in record.invoice_deduction_ids.filtered(lambda x: x.invoice_type == 'INVOICE_DP'):
                dp.invoice_reverse_id = False

        return True



    # @api.multi
    def action_cancel(self):
        for record in self:
            # Hanya invoice draft yang boleh dibatalkan
            if record.state != 'draft':
                raise UserError(_('Only invoices with Draft status can be cancelled.'))
            record.state = 'cancel'
        return True


    
    # @api.multi
    def action_creditnote(self):
        for record in self:
            if record.invoice_type not in ['INVOICE_IB','INVOICE_DP']:
                raise UserError(_('Only DP/Inbound invoices with Confirm status can be given a credit note.'))

            # ambil tanggal hari ini sesuai timezone Odoo user
            today = fields.Date.context_today(self)

            action = {
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'view_type': 'form',
                'res_model': 'payable.adjustment',
                'name': _('Create DebitNote for AP Invoice'),
                'views': [(False, 'form')],
                'context': {
                    'default_company_id': record.company_id.id,
                    'default_adjust_date': today,
                    'default_adjust_type': 'CN',
                    'default_adjust_notes': 'CreditNote for ' + record.invoice_no,
                    'default_supplier_type': record.supplier_type,
                    'default_supplier_id': record.supplier_id.id or False,
                    'default_invoice_id': record.id or False, 
                    'default_invoice_date': record.invoice_date or False, 
                    'default_invoice_duedate': record.invoice_duedate or False,
                    'default_readonly': True
                }
            }
            return action
        return True


    # @api.multi
    def action_debitnote(self):
        for record in self:
            if record.invoice_type not in ['INVOICE_IB','INVOICE_DP']:
                raise UserError(_('Only DP/Inbound invoices with Confirm status can be given a debit note.'))
            
            # ambil tanggal hari ini sesuai timezone Odoo user
            today = fields.Date.context_today(self)

            action = {
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'view_type': 'form',
                'res_model': 'payable.adjustment',
                'name': _('Create DebitNote for AP Invoice'),
                'views': [(False, 'form')],
                'context': {
                    'default_company_id': record.company_id.id,
                    'default_adjust_date': today,
                    'default_adjust_type': 'DN',
                    'default_adjust_notes': 'DebitNote for ' + record.invoice_no,
                    'default_supplier_type': record.supplier_type,
                    'default_supplier_id': record.supplier_id.id or False,
                    'default_invoice_id': record.id or False, 
                    'default_invoice_date': record.invoice_date or False, 
                    'default_invoice_duedate': record.invoice_duedate or False,
                    'default_readonly': True
                }
            }
            return action
        return True



    def _check_invoice_date(self, date_str=None):
        if not date_str:
            date_str = self.invoice_date
            if not date_str:
                return
        
        # invoice_date = datetime.strptime(str(date_str), "%Y-%m-%d")
        if isinstance(date_str, str):
            invoice_date = fields.Date.from_string(date_str)
        else:
            invoice_date = date_str
        today = fields.Date.today()
        today = fields.Date.today()
        limit_date = today - timedelta(days=10)

        if invoice_date < limit_date:
            raise UserError(_("Invoice Date can't be backdated more than 10 days, maximum allowed backdate is: %s." % limit_date))



class PayableInvoiceLine(models.Model):
    _name = 'payable.invoice.line'
    _description = 'AP Invoice Line'
    _rec_name = 'payable_invoice_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    payable_invoice_id = fields.Many2one('payable.invoice', string="Invoice No.")   
    item_name = fields.Char(string="Description")
    item_amount = fields.Float(string="Amount") 
    item_account_id = fields.Many2one("account.account", string="Account")
    state = fields.Selection(related="payable_invoice_id.state")
    
    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(PayableInvoiceLine, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        if view_type == 'form':
            res['arch'] = """
                <form string="AP Invoice Item">
                    <sheet>
                        <div class="oe_title" attrs="{'invisible':[('state','=','draft')]}">
                            <label string="Payment No."/>
                            <h1>
                                <field name="payable_invoice_id" readonly="1" />
                            </h1>
                        </div>

                        <group readonly="1">
                            <group>
                                <field name="item_name" />
                                <field name="state" />
                            </group>
                            <group>
                                <field name="item_amount" />
                                <field name="item_account_id" />
                            </group>
                        </group>

                        <notebook>       
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" readonly="1" />
                                        <field name="sync_id" readonly="1"/>
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

                    <div class="oe_chatter">
                        <field name="message_follower_ids" widget="mail_followers"/>
                        <field name="message_ids" widget="mail_thread"/>
                    </div>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="AP Invoice Item" delete="false" create="false" edit="false">
                    <field name="payable_invoice_id"/>
                    <field name="item_name"/>
                    <field name="item_account_id"/>
                    <field name="item_amount"/>
                    <field name="state"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="AP Invoice Item..">
                    <field name="payable_invoice_id"/>
                    <field name="item_name"/>
                    <field name="item_account_id"/>
                    <field name="item_amount"/>
                    <field name="state"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(self._name, doc, view_id)
        return res



class PayableAdjustment(models.Model):
    _name = 'payable.adjustment'
    _description = 'AP Adjustment'
    _rec_name = 'title'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id
    
    @api.model
    def _get_user(self):
        return self.env.user.id

    @api.model 
    def _get_ctx_readonly(self):
        return bool(self.env.context.get('default_readonly', False))

    ctx_readonly = fields.Boolean(store=False, default=_get_ctx_readonly)
    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    title = fields.Char(string="Title") 
    adjust_no = fields.Char(string="Adjust No.")
    adjust_type = fields.Selection([('CN', 'Credit Note'),('DN', 'Debit Note')], string="Adjust Type", default='CN', track_visibility='always')
    adjust_date = fields.Date(string="Adjust Date", track_visibility='always')
    adjust_notes = fields.Char(string="Adjust Notes")
    adjust_amount = fields.Float(string="Adjust Amount", track_visibility='always')
    adjust_account_id = fields.Many2one('account.account', string="Adjust Account")
    adjust_user_id = fields.Many2one('res.users', string="Responsible", default=_get_user)

    supplier_type = fields.Selection([
        ('AP CASHCHEQUE','AP CASHCHEQUE'),
        ('AP CATHLAB','AP CATHLAB'),
        ('AP DOCTOR FEE','AP DOCTOR FEE'),
        ('AP GENERAL','AP GENERAL'),
        ('AP MEDICAL','AP MEDICAL'),
        ('AP FIXED ASSET','AP FIXED ASSET'),
        ('AP CATERING','AP CATERING'),
        ('AP HOUSEKEEPING','AP HOUSEKEEPING'),
        ('AP OTHERS','AP OTHERS')
    ], string="Supplier Type", help="Pilih tipe supplier", default='AP GENERAL')
    supplier_id = fields.Many2one('payable.supplier', string='AP Supplier', help="Pilih group supplier untuk penentuan tracking AP Aging")

    invoice_id = fields.Many2one('payable.invoice', string="Invoice No.", help="Pilih AP invoice yang ingin diberikan CreditNote/WriteOff")
    invoice_date = fields.Date(string="Invoice Date", help="Tgl. invoice diisi sesuai tanggal perhitungan AP")
    invoice_duedate = fields.Date(string="Invoice DueDate", help="Tgl. jatuh tempo sesuai pengakuan tgl. invoice + supplier T.O.P")
    state = fields.Selection([('draft', 'Draft'),('confirm', 'Confirm'),('cancel', 'Cancel') ], string='State', default='draft', required=True, track_visibility='always')
    move_id = fields.Many2one('account.move', string="Entries No.")


    @api.model
    def create(self, vals):
        result = super(PayableAdjustment, self).create(vals)
        sequence_id = 'payable.creditnote.sequence' if result.adjust_type == 'CN' else 'payable.debitnote.sequence'
        result.adjust_no = self.env['ir.sequence'].sudo().next_by_code(sequence_id)
        # result.title = str(result.adjust_no) + ' / ' + str(result.supplier_id.supplier_name)
        return result


    @api.model
    def create(self, vals):
        record = super(PayableAdjustment, self).create(vals)
        if record.adjust_type == 'CN':
            sequence_id = 'payable.creditnote.sequence'
        else:
            sequence_id = 'payable.debitnote.sequence'
    
        record.adjust_no = self.env['ir.sequence'].sudo().next_by_code(sequence_id)
        record.with_context(skip_name_update=True).write({'title': '{} / {}'.format(record.adjust_no, record.supplier_id.title) })
        return record


    # @api.multi
    def write(self, vals):
        if self.env.context.get('skip_name_update'):
            return super(PayableAdjustment, self).write(vals)
        res = super(PayableAdjustment, self).write(vals)

        for record in self:
            record.refresh()
            record.with_context(skip_name_update=True).write({'title': '{} / {}'.format(record.adjust_no, record.supplier_id.title) })
            # record.actio
        return res 



    @api.onchange('supplier_id')
    def _onchange_supplier_id(self):
        for record in self:
            if not self.env.context.get('default_invoice_id', False):
                record.invoice_id = False 
                record.invoice_date = False 
                record.invoice_duedate = False 


    @api.onchange('invoice_id')
    def _onchange_invoice_id(self):
        for record in self:
            record.invoice_date = record.invoice_id.invoice_date 
            record.invoice_duedate = record.invoice_id.invoice_duedate
     
    

    # @api.multi
    def action_create_entries(self):
        for record in self:
            account_payable_id = record.invoice_id.supplier_account_payable_id.id or None 
            account_adjustment_id = record.adjust_account_id.id or None 
            account_journal_id = self.sudo().env['account.journal'].search([('name','=', 'AP Traceability'), ('company_id','=', record.company_id.id)], limit=1).id or None 

            if not account_adjustment_id:
                raise UserError(_('Please mapping account adjustment.'))
            if not account_payable_id:
                raise UserError(_('Please mapping account payable.'))
            if not account_journal_id:
                raise UserError(_('Please define jpournal AP Traceability.'))
            line_ids = []

            if record.adjust_type == 'CN':
                debit_vals = { 'name': 'CN FOR ' + record.invoice_id.invoice_no + ' / ' + record.supplier_id.title, 'date_maturity': record.invoice_id.invoice_duedate, 'debit': abs(record.adjust_amount), 'credit': 0.0, 'account_id': account_payable_id, 'payable_invoice_id': record.invoice_id.id}
                credit_vals = { 'name': 'CN FOR ' + record.invoice_id.invoice_no + ' / ' + record.supplier_id.title, 'date_maturity': record.invoice_id.invoice_duedate, 'credit': abs(record.adjust_amount), 'debit': 0.0, 'account_id': account_adjustment_id, 'payable_invoice_id': record.invoice_id.id}
            else:
                debit_vals = { 'name': 'DN FOR ' + record.invoice_id.invoice_no + ' / ' + record.supplier_id.title, 'date_maturity': record.invoice_id.invoice_duedate, 'debit': abs(record.adjust_amount), 'credit': 0.0, 'account_id': account_adjustment_id, 'payable_invoice_id': record.invoice_id.id}
                credit_vals = { 'name': 'DN FOR ' + record.invoice_id.invoice_no + ' / ' + record.supplier_id.title, 'date_maturity': record.invoice_id.invoice_duedate, 'credit': abs(record.adjust_amount), 'debit': 0.0, 'account_id': account_payable_id, 'payable_invoice_id': record.invoice_id.id}

            line_ids.append((0, 0, debit_vals))
            line_ids.append((0, 0, credit_vals))

            record.move_id = record.env['account.move'].create({'journal_id': account_journal_id, 'date': record.adjust_date, 'state': 'draft', 'name': record.adjust_no, 'ref': record.adjust_no + ' / ' + record.supplier_id.title, 'payable_invoice_id': record.invoice_id.id, 'line_ids': line_ids})
            record.move_id.action_post()
            record.move_id.name = record.adjust_no     
        return True



    # @api.multi
    def action_confirm(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only Adjustment with Draft status can be confirm.'))
            record.state = 'confirm'
            record.action_create_entries()
            record.move_id.action_post()

            if record.invoice_id:
                record.invoice_id.action_compute_balance()
        return True

    
    # @api.multi
    def action_unconfirm(self):
        for record in self:
            if record.state != 'confirm':
                raise UserError(_('Only Adjustment with Confirm status can be unconfirm.'))

            record.state = 'draft'
            
            if record.move_id:
                record.move_id.button_cancel()
                record.move_id.unlink()

            if record.invoice_id:
                record.invoice_id.action_compute_balance()

        return True



    # @api.multi
    def action_cancel(self):
        for record in self:
            # Hanya invoice draft yang boleh dibatalkan
            if record.state != 'draft':
                raise UserError(_('Only Adjustment with Draft status can be cancelled.'))
            record.state = 'cancel'
        return True


class PayablePayment(models.Model):
    _name = 'payable.payment'
    _description = 'AP Payment'
    _rec_name = 'title'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id
    
    @api.model
    def _get_user(self):
        return self.env.user.id

    @api.model 
    def _get_ctx_readonly(self):
        return bool(self.env.context.get('default_readonly', False))

    ctx_readonly = fields.Boolean(store=False, default=_get_ctx_readonly)
    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    title = fields.Char(string="Title") 
    payment_no = fields.Char(string="Payment No.")
    payment_date = fields.Date(string="Payment Date", track_visibility='always')
    payment_ref = fields.Char(string="Payment Ref.")
    payment_account_id = fields.Many2one('account.account', string="Payment Account")   
    payment_cheque = fields.Char(string="Payment Cheque No.") 
    payment_amount = fields.Float(string="Payment Amount", track_visibility='always')
    payment_notes = fields.Char(string="Payment Notes")
    payment_type = fields.Selection([
        ('WITH_INVOICE','WITH INVOICE'),
        ('WITHOUT_INVOICE','WITHOUT INVOICE'),
    ], string="Payment Type", default="WITH_INVOICE")

    payment_tax_type = fields.Selection([
        ('NO_TAX','NO_TAX'),
        ('ART_21','ART_21'),
        ('ART_23','ART_23'),
        ('ART_41','ART_4(1)'),
        ('ART_42','ART_4(2)'),
        ('VAT_11','VAT_11')
    ], string="Tax Type", default="NO_TAX")
    payment_tax_account_id = fields.Many2one('account.account', string="Tax Account")
    payment_tax_expense_id = fields.Many2one('account.account', string="Tax Expense")
    payment_tax_amount = fields.Float(string="Tax Amount")
    payment_net_amount = fields.Float(string="Payment Net", compute="_onchange_payment_net_amount", store=True)
    payment_group_id = fields.Many2one('payable.payment.group', string="Payment Group")
    payment_user_id = fields.Many2one('res.users', string="Responsible", default=_get_user)

    settlement_type = fields.Selection([
        ('AMOUNT', 'BY AMOUNT'),
        ('PERCENT', 'BY PERCENT')
    ], string="Settlement Type", default='AMOUNT')
    settlement_rate = fields.Float(string="Settlement Rate")

    supplier_type = fields.Selection([
        ('AP CASHCHEQUE','AP CASHCHEQUE'),
        ('AP CATHLAB','AP CATHLAB'),
        ('AP DOCTOR FEE','AP DOCTOR FEE'),
        ('AP GENERAL','AP GENERAL'),
        ('AP MEDICAL','AP MEDICAL'),
        ('AP FIXED ASSET','AP FIXED ASSET'),
        ('AP CATERING','AP CATERING'),
        ('AP HOUSEKEEPING','AP HOUSEKEEPING'),
        ('AP OTHERS','AP OTHERS')
    ], string="Supplier Type", help="Pilih tipe supplier", default="AP GENERAL")
    supplier_id = fields.Many2one('payable.supplier', string='Supplier Name', help="Pilih group supplier untuk penentuan tracking AP Aging")
    supplier_account_payable_id = fields.Many2one('account.account', string="Expense/AP Account", track_visibility='always')

    bank_transfer_id =fields.Many2one('payable.supplier.bank', string="Bank Transfer")
    bank_transfer_type = fields.Selection([
        ('CASH','CASH'),
        ('LLG','LLG'),
        ('RTGS','RTGS'),
        ('BI_FAST','BI_FAST')
    ], string="Transfer Type", default="CASH")
    bank_transfer_fee = fields.Float(string="Transfer Fee")
    bank_transfer_account_id = fields.Many2one('account.account', string="Transfer Fee Account")
    
    payment_invoice_ids = fields.Many2many('payable.invoice', 'payable_payment_invoice_rel', 'payable_payment_id', string="Pilih list AP invoice yang ingin dilakukan pembayaran")
    payment_line_ids = fields.One2many('payable.payment.line', 'payable_payment_id', string="Payment Invoices")
    payment_item_ids = fields.One2many('payable.payment.item', 'payable_payment_id', string="Payment Item")
    state = fields.Selection([('draft', 'Draft'),('confirm', 'Confirm'),('cancel', 'Cancel') ], string='State', default='draft', required=True, track_visibility='always')
    move_id = fields.Many2one('account.move', string="Entries No.")

    payment_invoice_amount = fields.Float(string="Payment Inv. Amount")
    difference_amount = fields.Float(string="Difference Amount", compute="_compute_difference", store=True)
    difference_handling = fields.Selection([
        ('open', 'Keep open, partial payment'),
        ('writeoff', 'WriteOff')
    ], default="open", string="Differencce Handling")
    difference_notes = fields.Char(string="Difference Notes")

    ttd1 = fields.Char(string="Tanda Tangan 1")
    ttd2 = fields.Char(string="Tanda Tangan 2")
    ttd3 = fields.Char(string="Tanda Tangan 3")
    ttd4 = fields.Char(string="Tanda Tangan 4")
    ttd5 = fields.Char(string="Tanda Tangan 5")
    ttd6 = fields.Char(string="Tanda Tangan 6")
    no_approval = fields.Boolean(string="No Approval")
    

    @api.model
    def create(self, vals):
        record = super(PayablePayment, self).create(vals)
        record.payment_no = self.env['ir.sequence'].sudo().next_by_code('payable.payment.sequence')
        record.with_context(skip_name_update=True).write({
            'title': '{} / {}'.format(record.payment_no, record.supplier_id.title),
            'ttd1': record.company_id.ttd1 or '',
            'ttd2': record.company_id.ttd2 or '',
            'ttd3': record.company_id.ttd3 or '',
            'ttd4': record.company_id.ttd4 or '',
            'ttd5': record.company_id.ttd5 or '',
            'ttd6': record.company_id.ttd6 or ''
        })
        return record


    # @api.multi
    def write(self, vals):
        if self.env.context.get('skip_name_update'):
            return super(PayablePayment, self).write(vals)
        res = super(PayablePayment, self).write(vals)

        for record in self:
            record.refresh()
            record.with_context(skip_name_update=True).write({'title': '{} / {}'.format(record.payment_no, record.supplier_id.title) })
        return res


    # @api.multi
    def action_create_entries(self):
        for record in self:
            payment_account_id  = record.payment_account_id.id or None 
            payment_account_tax_id = record.payment_tax_account_id.id or None 
            payment_account_fee_id = record.bank_transfer_account_id.id or None 
            payment_account_supplier_id = record.supplier_account_payable_id.id or None 
            account_journal_id = self.sudo().env['account.journal'].search([('name','=', 'AP Traceability'), ('company_id','=', record.company_id.id)], limit=1).id or None 

            if not payment_account_id:
                raise UserError(_('Please mapping Bank account.'))
            if not payment_account_tax_id and record.payment_tax_type != 'NO_TAX' and record.payment_tax_amount != 0:
                raise UserError(_('Please mapping Tax account, unless the payment is genuinely tax-exempt.'))
            if not payment_account_fee_id and record.bank_transfer_type != 'CASH' and record.bank_transfer_fee > 0:
                raise UserError(_('Please mapping Transfer fee account, unless the payment is made in cash or without a transfer fee.'))
            if not payment_account_supplier_id:
                raise UserError(_('Please map default Payment Expense Account, or AP Account in the AP Supplier master data for ' + record.supplier_id.title))
            line_ids = []

            # jika ada payment_items maka debit per item
            payment_amount = record.payment_amount or 0.0
            if record.payment_item_ids:
                for line in record.payment_item_ids:
                    payment_amount -= line.item_amount or 0.0
                    debit_vals = { 
                        'name': record.payment_no + ' / ' + line.item_name, 
                        'date_maturity': record.payment_date, 
                        'debit': abs(line.item_amount if line.item_amount > 0 else 0), 
                        'credit': abs(line.item_amount if line.item_amount < 0 else 0),
                        'account_id': line.item_account_id.id or payment_account_supplier_id, 
                        'cheque': record.payment_cheque,
                        'payable_payment_id':record.id or None}
                    line_ids.append((0, 0, debit_vals))

            # stored debit adjustment to AP account by vendor/invoices
            if record.payment_type == 'WITH_INVOICE':
                for inv in record.payment_line_ids.filtered(lambda x: x.payment_amount > 0):
                    payment_amount -= inv.payment_amount or 0.0
                    debit_vals = { 
                        'name': record.payment_no + ' / ' + inv.payable_invoice_id.invoice_no, 
                        'date_maturity': inv.payable_invoice_id.invoice_duedate, 
                        'debit': abs(inv.payment_amount), 
                        'credit': 0.0, 
                        'account_id': inv.payable_invoice_id.supplier_account_payable_id.id, 
                        'payable_invoice_id': inv.payable_invoice_id.id,
                        'payable_payment_id':record.id or None, 
                        'cheque': record.payment_cheque} 
                    line_ids.append((0, 0, debit_vals))


            if payment_amount > 0:                
                debit_vals = { 
                    'name': record.payment_no + ' / ' + record.payment_ref,
                    'date_maturity': record.payment_date, 
                    'debit': abs(payment_amount), 
                    'credit': 0.0, 
                    'account_id': payment_account_supplier_id, 
                    'payable_invoice_id': False,
                    'payable_payment_id':record.id or None,
                    'cheque': record.payment_cheque}
                line_ids.append((0, 0, debit_vals))

            


            # stored credit adjustment to Bank Account by vendor/invoices
            payment_amount = record.payment_amount or 0.0 
            tax_amount = record.payment_tax_amount if record.payment_tax_type != 'NO_TAX' else 0.0
            fee_amount = record.bank_transfer_fee if record.bank_transfer_type != 'CASH' else 0.0 
           
            # jika fee_amount < 0 maka dipotong dari pembayaran ke vendor 
            if fee_amount < 0:
                payment_amount -= abs(fee_amount)
                credit_vals = { 
                    'name': record.payment_no + ' / FEE TRANSFER', 
                    'date_maturity': record.payment_date, 
                    'credit': abs(fee_amount), 
                    'debit': 0.0, 
                    'account_id': payment_account_id, 
                    'payable_invoice_id': False,
                    'payable_payment_id':record.id or None,
                    'cheque': record.payment_cheque}
                line_ids.append((0, 0, credit_vals))
            
            # jika fee_amount > 0 maka tambahkan beban expense biaya admin charge di tanggung perusahaan
            elif fee_amount > 0:
                debit_vals = { 
                    'name': record.payment_no + ' / FEE TRANSFER', 
                    'date_maturity': record.payment_date, 
                    'debit': abs(fee_amount), 
                    'credit': 0.0, 
                    'account_id': payment_account_fee_id, 
                    'payable_invoice_id': False,
                    'payable_payment_id':record.id or None,
                    'cheque': record.payment_cheque}
                line_ids.append((0, 0, debit_vals))

                credit_vals = { 
                    'name': record.payment_no + ' / FEE TRANSFER', 
                    'date_maturity': record.payment_date, 
                    'credit': abs(fee_amount), 
                    'debit': 0.0, 
                    'account_id': payment_account_id, 
                    'payable_invoice_id': False,
                    'payable_payment_id':record.id or None,
                    'cheque': record.payment_cheque}
                line_ids.append((0, 0, credit_vals))


            # taxes dipotong ke vendor 
            if tax_amount < 0:
                payment_amount -= abs(tax_amount)
                credit_vals = { 
                    'name': record.payment_no + ' / ' + record.payment_tax_type, 
                    'date_maturity': record.payment_date, 
                    'credit': abs(tax_amount), 
                    'debit': 0.0, 
                    'account_id': payment_account_tax_id, 
                    'payable_invoice_id': False,
                    'payable_payment_id':record.id or None, 
                    'cheque': record.payment_cheque}
                line_ids.append((0, 0, credit_vals))

            # taxes dibebankan ke perusahaan
            elif tax_amount > 0:
                payment_expense_tax_id = record.payment_tax_expense_id.id or None 
                if not payment_expense_tax_id:
                    raise UserError(_('Please mapping Tax expense account, unless the payment is genuinely tax-exempt.'))

                debit_vals = { 
                    'name': record.payment_no + ' / ' + record.payment_tax_type, 
                    'date_maturity': record.payment_date, 
                    'debit': abs(tax_amount), 
                    'credit': 0.0, 
                    'account_id': payment_expense_tax_id, 
                    'payable_invoice_id': False,
                    'payable_payment_id':record.id or None,
                    'cheque': record.payment_cheque}
                line_ids.append((0, 0, debit_vals))

                credit_vals = { 
                    'name': record.payment_no + ' / ' + record.payment_tax_type, 
                    'date_maturity': record.payment_date, 
                    'credit': abs(tax_amount), 
                    'debit': 0.0, 
                    'account_id': payment_account_tax_id, 
                    'payable_invoice_id': False,
                    'payable_payment_id':record.id or None,
                    'cheque': record.payment_cheque}
                line_ids.append((0, 0, credit_vals))

                
            # set actual payment to vendor (credited to bank account)
            credit_vals = { 
                'name': record.payment_no + ' / PAYMENT', 
                'date_maturity': record.payment_date, 
                'credit': abs(payment_amount), 
                'debit': 0.0, 
                'account_id': payment_account_id, 
                'payable_invoice_id': False,
                'payable_payment_id':record.id or None,
                'cheque': record.payment_cheque}
            line_ids.append((0, 0, credit_vals))

            record.move_id = record.env['account.move'].create({'journal_id': account_journal_id, 'date': record.payment_date, 'state': 'draft', 'name': record.payment_no, 'ref': record.payment_no + ' / ' + record.supplier_id.title, 'cheque': record.payment_cheque, 'line_ids': line_ids, 'payable_payment_id':record.id})
            record.move_id.action_post()
            record.move_id.name = record.payment_no 
        return True


    # @api.multi
    def action_confirm(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only Payment with Draft status can be confirm.'))
            
            from odoo.tools.float_utils import float_compare

            record._check_payment_amount()
            record.state = 'confirm'
            record.action_create_entries()

            if record.payment_line_ids:
                for pay in record.payment_line_ids:
                    pay.payable_invoice_id.action_compute_balance()
        return True


    # @api.multi
    def _check_payment_amount(self):
        for record in self:
            if record.payment_type == 'WITH_INVOICE' and record.state not in ['confirm']:
                payment_lines = sum(x.payment_amount for x in record.payment_line_ids) or 0.0
                payment_items = sum(x.item_amount for x in record.payment_item_ids) or 0.0
                payment_total = payment_lines + payment_items
                precision = 2  # bisa juga pakai fixed 2

                # bandingkan dengan toleransi pembulatan
                if float_compare(record.payment_amount, payment_total, precision_digits=precision) != 0:
                    expected = "{:,.2f}".format(payment_total)
                    got = "{:,.2f}".format(record.payment_amount)
                    raise UserError(_(
                        'Payment amount must be equal to the total settlement invoices and items\n'
                        '(Total invoices + items: %s, Payment Amount: %s)'
                    ) % (expected, got))
                
                if not record.payment_line_ids:
                    raise UserError(_('There is no individual settlement payment to an invoice. Please perform the settlement payment on the list of invoices.'))

                if record.payment_line_ids.filtered(lambda x: (x.invoice_balance - x.payment_amount) < -1 ):
                    raise UserError(_('There is a settlement payment that exceeds the outstanding amount of the invoice.'))

                if record.payment_line_ids.filtered(lambda x: x.payable_invoice_id.state != 'confirm'):
                    raise UserError(_('There are invoices in the settlement list that are in Draft/Cancelled status.'))

            if record.payment_type == 'WITHOUT_INVOICE' and record.state not in ['confirm']:
                payment_items = sum(x.item_amount for x in record.payment_item_ids) or 0.0
                payment_amount = record.payment_amount or 0.0

                if payment_amount < payment_items:
                    raise UserError(_('The payment amount cannot be smaller than the total payment items.'))

    
    # @api.multi
    def action_unconfirm(self):
        for record in self:
            if record.state != 'confirm':
                raise UserError(_('Only Payment with Confirm status can be unconfirm.'))

            record.state = 'draft'
            if record.move_id:
                record.move_id.button_cancel()
                record.move_id.unlink()

            if record.payment_line_ids:
                for pay in record.payment_line_ids:
                    pay.payable_invoice_id.action_compute_balance()
        return True



    # @api.multi
    def action_cancel(self):
        for record in self:
            # Hanya invoice draft yang boleh dibatalkan
            if record.state != 'draft':
                raise UserError(_('Only Payment with Draft status can be cancelled.'))
            record.state = 'cancel'
        return True



    # @api.multi
    def action_print(self):
        for record in self:
            record._check_payment_amount()

        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/reporting/payable_payment?id=' + str(self.id)
        action['target'] = 'new'
        return action


    
    # @api.multi 
    def action_settlement_fetch(self):
        for record in self:
            if record.state  != 'draft':
                raise exceptions.ValidationError("Only payment with Draft status can be fetch data to settlement payment.")
            if not record.payment_invoice_ids:
                raise exceptions.ValidationError("Please select several vendor invoices in the AP Invoices section before fetching the data.")
            record.payment_line_ids.unlink()

            for inv in record.payment_invoice_ids:
                record.payment_line_ids.create({
                    'company_id': record.company_id.id, 
                    'payable_invoice_id': inv.id,
                    'payable_payment_id': record.id,          
                    'payment_amount': 0.0
                })
        return True 
                
    
    @api.onchange('bank_transfer_type')
    @api.depends('bank_transfer_type')
    def _onchange_bank_transfer_type(self):
        for record in self:
            if record.state == 'draft':
                reverse = -1 if (record.bank_transfer_fee or 0.0) < 0 else 1
                if record.bank_transfer_type == 'LLG':
                    transfer_fee = record.bank_transfer_id.supplier_bank_llg or 0.0 
                elif record.bank_transfer_type == 'RTGS':
                    transfer_fee = record.bank_transfer_id.supplier_bank_rtgs or 0.0 
                elif record.bank_transfer_type == 'BI_FAST':
                    transfer_fee = record.bank_transfer_id.supplier_bank_bifast or 0.0
                else:
                    transfer_fee = 0
                record.bank_transfer_fee = transfer_fee * reverse


    @api.onchange('supplier_id')
    @api.depends('supplier_id')
    def _onchange_supplier_id(self):
        for record in self:
            if record.state == 'draft':
                record.supplier_account_payable_id = record.supplier_id.supplier_account_payable_id.id or None 

    
    
    @api.onchange('payment_amount','payment_tax_amount','bank_transfer_fee')
    @api.depends('payment_amount','payment_tax_amount','bank_transfer_fee')
    def _onchange_payment_net_amount(self):
        for record in self:
            if record.state == 'draft':
                payment_net_amount = record.payment_amount or 0.0 

                if record.payment_tax_type == 'NO_TAX':
                    record.payment_tax_amount = 0.0 
                elif record.payment_tax_amount < 0:
                    payment_net_amount += record.payment_tax_amount or 0.0 

                if record.bank_transfer_type == 'CASH':
                    record.bank_transfer_fee = 0 
                elif record.bank_transfer_fee < 0:
                    payment_net_amount += record.bank_transfer_fee or 0.0 

                record.payment_net_amount = payment_net_amount

    @api.onchange('payment_amount','payment_invoice_amount')
    @api.depends('payment_amount','payment_invoice_amount')
    def _compute_difference(self):
        for record in self:
            if record.state == 'draft':
                record.difference_amount = (record.payment_amount or 0.0) - (record.payment_invoice_amount or 0.0)
                


    # @api.multi 
    def action_settlement_apply(self):
        for record in self:
            if record.state  != 'draft':
                raise exceptions.ValidationError("Only payment with Draft status can be fetch data to settlement payment.")
            if not record.settlement_type:
                raise exceptions.ValidationError("Please select the settlement type value.")
            if not record.settlement_rate:
                raise exceptions.ValidationError("Please enter the settlement rate value.")
            if not record.payment_line_ids:
                raise exceptions.ValidationError("Please apply the settlement to retrieve the invoice lines and fill in the payment amount.")

            if record.settlement_type == 'AMOUNT':
                amount = record.settlement_rate or 0.0 

                for inv in record.payment_line_ids:
                    inv_balance = inv.invoice_balance or 0.0 
                    if amount > 0:
                        if inv_balance > 0 and inv_balance <= amount:
                            pay_amount = inv_balance 
                        elif inv_balance > 0 and inv_balance >= amount:
                            pay_amount = amount 
                        else:
                            pay_amount = 0
                        inv.payment_amount = pay_amount
                        amount -= pay_amount

            if record.settlement_type == 'PERCENT':
                amount = record.settlement_rate or 0.0 
                for inv in record.payment_line_ids:
                    inv_balance = inv.invoice_balance or 0.0
                    pay_amount = inv_balance * record.settlement_rate / 100.0
                    inv.payment_amount = pay_amount

            total_payment_line = sum(x.payment_amount for x in record.payment_line_ids) or 0.0
            total_payment_item = sum(x.item_amount for x in record.payment_item_ids) or 0.0

            record.payment_amount = (total_payment_item + total_payment_line)
            record.payment_invoice_amount = sum(x.invoice_balance for x in record.payment_line_ids) or 0.0
            # record._compute_differece()
        return True 


class PayablePaymentLine(models.Model):
    _name = 'payable.payment.line'
    _description = 'AP Payment Line'
    _rec_name = 'payable_invoice_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    payable_invoice_id = fields.Many2one('payable.invoice', string="Invoice No.")   
    payable_payment_id = fields.Many2one('payable.payment', string="Payment No.")
    invoice_no = fields.Char(related="payable_invoice_id.invoice_no")
    invoice_date = fields.Date(related="payable_invoice_id.invoice_date")
    invoice_duedate = fields.Date(related="payable_invoice_id.invoice_duedate")
    invoice_balance = fields.Float(related="payable_invoice_id.invoice_balance") 
    payment_amount = fields.Float(string="Payment Amount")
    state = fields.Selection(related="payable_payment_id.state")


    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(PayablePaymentLine, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        if view_type == 'form':
            res['arch'] = """
                    <form string="AP Payment Invoices">
                        <sheet>
                            <div class="oe_title" attrs="{'invisible':[('state','=','draft')]}">
                                <label for="payable_payment_id"/>
                                <h1>
                                    <field name="payable_payment_id" readonly="1" />
                                </h1>
                            </div>

                            <group readonly="1">
                                <group>
                                    <field name="invoice_no" />
                                    <field name="invoice_date" />
                                    <field name="invoice_duedate" />
                                </group>
                                <group>
                                    <field name="payment_amount" />
                                    <field name="state" />
                                </group>
                            </group>

                            <notebook>       
                                <page string="Technical">
                                    <group>
                                        <group>
                                            <field name="sync_type" readonly="1" />
                                            <field name="sync_id" readonly="1"/>
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
                        <div class="oe_chatter">
                            <field name="message_follower_ids" widget="mail_followers"/>
                            <field name="message_ids" widget="mail_thread"/>
                        </div>
                    </form>
            """

        elif view_type == 'tree':
            res['arch'] = """
                <tree string="AP Payment Invoices" delete="false" create="false" edit="false">
                    <field name="payable_payment_id"/>
                    <field name="payment_amount"/>
                    <field name="invoice_no"/>
                    <field name="invoice_date"/>
                    <field name="invoice_duedate"/>
                    <field name="state"/>
                </tree>
            """

        elif view_type == 'search':
            res['arch'] = """
                <search string="AP Payment Invoices..">
                    <field name="payable_payment_id"/>
                    <field name="payment_amount"/>
                    <field name="invoice_no"/>
                    <field name="invoice_date"/>
                    <field name="invoice_duedate"/>
                    <field name="state"/>
                </search>"""
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(self._name, doc, view_id)
        return res






class PayablePaymentItem(models.Model):
    _name = 'payable.payment.item'
    _description = 'AP Payment Item'
    _rec_name = 'payable_payment_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    payable_payment_id = fields.Many2one('payable.payment', string="Payment No.")   
    item_name = fields.Char(string="Description")
    item_amount = fields.Float(string="Amount") 
    item_account_id = fields.Many2one("account.account", string="Account")
    state = fields.Selection(related="payable_payment_id.state")
    
    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(PayablePaymentItem, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        if view_type == 'form':
            res['arch'] = """
                <form string="AP Payment Item">
                    <sheet>
                        <div class="oe_title" attrs="{'invisible':[('state','=','draft')]}">
                            <label string="Payment No."/>
                            <h1>
                                <field name="payable_payment_id" readonly="1" />
                            </h1>
                        </div>

                        <group readonly="1">
                            <group>
                                <field name="item_name" />
                                <field name="state" />
                            </group>
                            <group>
                                <field name="item_amount" />
                                <field name="item_account_id" />
                            </group>
                        </group>

                        <notebook>       
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type" readonly="1" />
                                        <field name="sync_id" readonly="1"/>
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

                    <div class="oe_chatter">
                        <field name="message_follower_ids" widget="mail_followers"/>
                        <field name="message_ids" widget="mail_thread"/>
                    </div>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="AP Payment Item" delete="false" create="false" edit="false">
                    <field name="payable_payment_id"/>
                    <field name="item_name"/>
                    <field name="item_account_id"/>
                    <field name="item_amount"/>
                    <field name="state"/>
                </tree>
            """

        elif view_type == 'search':
            res['arch'] = """
                <search string="AP Payment Item..">
                    <field name="payable_payment_id"/>
                    <field name="item_name"/>
                    <field name="item_account_id"/>
                    <field name="item_amount"/>
                    <field name="state"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(self._name, doc, view_id)
        return res



class PayablePaymentGroup(models.Model):
    _name = 'payable.payment.group'
    _description = 'AP Payment Group'
    _rec_name = 'title'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id
    
    @api.model
    def _get_user(self):
        return self.env.user.id

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    title = fields.Char(string="Title") 
    payment_group_no = fields.Char(string="Payment Group No.")
    payment_group_date = fields.Date(string="Payment Date", track_visibility='always')
    payment_group_account_id = fields.Many2one('account.account', string="Payment Group Bank", track_visibility='always')
    payment_group_cheque = fields.Char(string="Payment Cheque No.")
    payment_group_ref = fields.Char(string="Payment Ref.")
    payment_group_user_id = fields.Many2one('res.users', string="Responsible", default=_get_user)
    payment_ids = fields.Many2many('payable.payment', 'payable_payment_group_rel', 'payable_payment_group_id', string="AP Payment List", help="List AP Payment")
    state = fields.Selection([('draft', 'Draft'),('confirm', 'Confirm'),('cancel', 'Cancel') ], string='State', default='draft', required=True, track_visibility='always')

    ttd1 = fields.Char(string="Tanda Tangan 1")
    ttd2 = fields.Char(string="Tanda Tangan 2")
    ttd3 = fields.Char(string="Tanda Tangan 3")
    ttd4 = fields.Char(string="Tanda Tangan 4")
    ttd5 = fields.Char(string="Tanda Tangan 5")
    ttd6 = fields.Char(string="Tanda Tangan 6")
    no_approval = fields.Boolean(string="No Approval")


    item_type = fields.Selection([('1', 'Service'), ('2', 'Fix Asset'),('3', 'Medis'), ('4', 'Non Medis')],string="Item Type", states={'posted':[('readonly', True)], 'reconciled':[('readonly', True)]})
    type_id = fields.Many2one('purchase.type',string="Approval Type",required=False,domain=[('purchase_type', '=', 'payment')], states={'posted':[('readonly', True)], 'reconciled':[('readonly', True)]})
    approve_id = fields.Many2one('purchase.approval',string="Approval Level Rule",readonly=True,compute='_approval',store=False,copy=False)
    approve_rule_id = fields.Many2one('purchase.approval.rule',string="Status App",readonly=True,copy=False)
    approve_status = fields.Char(string="Approval Status",readonly=True,related='approve_rule_id.position_id.name',store=True,copy=False)
    approve_next = fields.Char(string="Next Approval",readonly=True,compute='_approval',store=False,copy=False)
    approve_next_store = fields.Char(string="Stored Next Approval",readonly=False,store=True,index=True)
    end_approval = fields.Char(string="End Approval",compute="_get_end_approval")
    # no_approval = fields.Boolean(string="No Approval", states={'posted':[('readonly', True)], 'reconciled':[('readonly', True)]})
    approved_bool = fields.Boolean(string="Approved")
    payment_amount = fields.Float(string="Payment Total", compute="_payment_amount")
    
    status = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting for Approval'),
        ('approved', 'Approved'),
        ('confirm', 'Confirmed'),
        ('cancel', 'Cancelled')
    ],string='Status Approval',readonly=True,compute='_status',store=False)
    current_user_position = fields.Char(string="Current Position",compute='_get_current_position')


    # @api.multi
    def get_next_rule(self, approval_id=None, sequence=1):
        rule_id = None
        if approval_id:
            rule_id = self.sudo().env['purchase.approval.rule'].search([('approval_id','=',approval_id), ('enabled','=', True), ('sequence','>', sequence)], order='sequence asc', limit=1)
        # raise UserError(_(rule_id))
        return rule_id

    # @api.multi
    def get_store_rule(self, approval_id=None):
        rule_ids = None
        if approval_id:
            rule_ids = self.sudo().env['purchase.approval.rule'].search([('approval_id','=',approval_id), ('enabled','=', True)], order='sequence asc')
        # raise UserError(_(rule_ids))
        return rule_ids


    # @api.one
    # def _approval(self):
    #     for record in self:
    #         recor = record.sudo()
    #         planned = record.payment_amount 
    #         approval = record.env['purchase.approval'].sudo()
    #         record.approve_id = approval.search([('id', 'in', record.type_id.approval_ids.ids),('max_amount', '>=', planned), ('min_amount', '<=', planned)],limit=1)
    #         if record.approve_id:
    #             _ref_approval_id = record.approve_id.id
    #             rule_ids = record.get_store_rule(approval_id=_ref_approval_id)
                    
    #             if not record.approve_rule_id:
    #                 record.approve_next = rule_ids[0].position_id.name
    #             else:
    #                 rule_id = record.get_next_rule(approval_id=_ref_approval_id, sequence=record.approve_rule_id.sequence)
                    
    #                 if rule_id:
    #                     if len(rule_id) > 1:
    #                         raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
    #                     record.approve_next = rule_id.position_id.name
    #                     record.approve_next_store = "Completed"
    #                 else:
    #                     record.approve_next = "Completed"
    #                     record.approved_bool = True
    #                     record.approve_next_store = "Completed"
    #         else:
    #             record.approve_next = "-"

    def _approval(self):
        for rec in self:

            record = rec.sudo()
            planned = rec.payment_amount
            approval = rec.env['purchase.approval'].sudo()
            rec.approve_id = approval.search([('id', 'in', record.type_id.approval_ids.ids),('max_amount', '>=', planned), ('min_amount', '<=', planned)],limit=1)
            if rec.approve_id:
                # rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
                rule_ids = rec.get_store_rule(approval_id=rec.approve_id.id)
                    
                if not rec.approve_rule_id:
                    rec.approve_next = rule_ids[0].position_id.name
                    # rec.approve_next_store = rule_ids[0].position_id.name
                else:
                    # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                    rule_id = rec.get_next_rule(approval_id=rec.approve_id.id, sequence=record.approve_rule_id.sequence)
                    
                    if rule_id:
                        if len(rule_id) > 1:
                            raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                        rec.approve_next = rule_id.position_id.name
                        # rec.approve_next_store = rule_id.position_id.name
                    else:
                        rec.approve_next = "Completed"
                        # rec.approve_next_store = "Completed"
            else:
                rec.approve_next = ''


    # @api.one
    def _status(self):
        for record in self:
            if record.approve_next and record.state not in ['cancel', 'confirm']:
                if not record.approve_status:
                    record.status = 'draft'
                elif not record.approve_next == 'Completed':
                    record.status = 'waiting'
                else:
                    record.status = 'approved'
            else:
                record.status = record.state
                # if record.state == 'cancel':
                #     record.write({'approve_rule_id': False})


    # @api.multi
    def ask_approve(self):
        
        if self.type_id == False:
            raise exceptions.ValidationError("Fill Approval Type Before Ask Approve!!")

        if len(self) > 1: return [record.ask_approve() for record in self][0]
        self.approve_status = 'Waiting for Approval'

        record = self.sudo()
        # record.subscribe_approval()
        
        # now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
        now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
        approval_link = "https://erp.ad.mayapadahospital.com/web#min=1&limit=80&view_type=list&model=payable.payment.group&menu_id=565&action=689"
        # self.message_post(body='Please Approve This PV, ' + 'Asked by ' + self.env.user.name + " at " + now + '\n' +"Please Click This Link To Approve " + approval_link,message_type='notification',content_subtype='plaintext',subtype='mt_comment',approval_link_payment=True)
        self.message_post(body='Please Approve This PV, ' + 'Asked by ' + self.env.user.name + " at " + now + '\n' + "Please Click This Link To Approve " + approval_link, message_type='notification',content_subtype='plaintext', subtype_xmlid='mail.mt_comment', approval_link_payment=True)

        
        approval = self.env['purchase.approval'].sudo()
        if self.approve_id:
            rule_ids = self.get_store_rule(approval_id=self.approve_id.id)
                
            if not self.approve_rule_id:
                self.approve_next_store = rule_ids[0].position_id.name
            else:
                rule_id = self.get_next_rule(approval_id=self.approve_id.id, sequence=record.approve_rule_id.sequence)

                if rule_id:
                    if len(rule_id) > 1:
                        raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                    self.approve_next_store = rule_id.position_id.name
                else:
                    self.approve_next_store = "Completed"
                    self.approved_bool = True


    # @api.multi
    def subscribe_approval(self):
        self.ensure_one()
        user_ids = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id),('position_id.name', '=', self.approve_next_store)])
        if user_ids:
            self.sudo().message_subscribe_users(user_ids=user_ids.ids)
        user_ids2 = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id),('position_id.name', '=', self.approve_next)])
        if user_ids2:
            self.sudo().message_subscribe_users(user_ids=user_ids2.ids)


    # @api.one
    def _get_end_approval(self):
        record = self.sudo()
        end_approval = ''
        amount = record.payment_amount 
        for at in record.type_id.approval_ids:
            if at.min_amount <= amount and at.max_amount >= amount:
                for apv in at.rule_ids:
                    end_approval = apv.position_id.name
        record.end_approval = end_approval



    # @api.one
    def _get_current_position(self):
        for rec in self:
            rec.current_user_position = self.env.user.position_id.name


    # @api.one
    def _payment_amount(self):
        for rec in self:
            rec.payment_amount = sum(pay.payment_amount for pay in rec.payment_ids) or 0.0


    # @api.multi
    def approve(self):
        open('/opt/odoo16/logs/payable_payment.log', 'a+').write('\n' + "APPROVE PV")
        # self.function_consol(function="approve_consol")
        
        record = self.sudo()
        if record.approve_status == False:
            raise exceptions.ValidationError("Ask for Approve befor Approving this PV %s" % (record.payment_group_no))
        if not record.approve_id:
            raise exceptions.ValidationError("There are no rule defined for this PV %s" % (record.payment_group_no))
        ref_approval_id = self.approve_id.id
        rule_ids = self.get_store_rule(approval_id=ref_approval_id)
                
        
        if not rule_ids:
            raise exceptions.ValidationError("There are no rule defined for this PV %s" % (record.payment_group_no))

        if not self.approve_rule_id:
            if self.env.user.position_id.id in rule_ids[0].position_id.get_parent_ids():

                self.approve_rule_id = rule_ids[0]
                record = self.sudo()
                now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
                self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now,message_type='notification',content_subtype='plaintext',subtype_xmlid='mail.mt_comment')
                
                rule_id = self.get_next_rule(approval_id=ref_approval_id, sequence=record.approve_rule_id.sequence)
                if not rule_id:
                    self.status = 'approved'
            else:
                raise exceptions.ValidationError("You doesn't have authority to approve this - PV %s" % (record.payment_group_no))
        else:
            rule_id = self.get_next_rule(approval_id=self.approve_id.id, sequence=record.approve_rule_id.sequence)
                
            if rule_id:
                if self.env.user.position_id.id in rule_id.position_id.get_parent_ids():
                    self.approve_rule_id = rule_id
                    now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now,message_type='notification',content_subtype='plaintext',subtype_xmlid='mail.mt_comment')
                    # self.approve_history("Approved by " + self.approve_status)

                    rule_id = self.get_next_rule(approval_id=self.approve_id.id, sequence=record.approve_rule_id.sequence)
                    if not rule_id:
                        self.status = 'approved'
        
                else:
                    raise exceptions.ValidationError("You doesn't have authority to approve this PV %s" % (record.payment_group_no))
            else:
                raise exceptions.ValidationError("There are no Approval anymore for this PV %s" % (record.payment_group_no))
        
        # if self.approve_id:
        if ref_approval_id:
            rule_ids = self.get_store_rule(approval_id=ref_approval_id)
                
            if not self.approve_rule_id:
                self.approve_next_store = rule_ids[0].position_id.name
            else:
                rule_id = self.get_next_rule(approval_id=ref_approval_id, sequence=record.approve_rule_id.sequence)
                
                if rule_id:
                    if len(rule_id) > 1:
                        raise exceptions.ValidationError("The sequence in Approval Rule Positions is double! - PV %s" % (record.payment_group_no))
                    self.approve_next_store = rule_id.position_id.name
                else:
                    self.approve_next_store = "Completed"
                    self.approved_bool = True

        # record.subscribe_approval()
        # approval_link = "https://erp.ad.mayapadahospital.com/web#min=1&limit=80&view_type=list&model=payable.payment.group&menu_id=565&action=689"
        

    

    @api.model
    def create(self, vals):
        record = super(PayablePaymentGroup, self).create(vals)
        record.payment_group_no = self.env['ir.sequence'].sudo().next_by_code('payable.payment.group.sequence')
        record.with_context(skip_name_update=True).write({
            'title': '{} / {}'.format(record.payment_group_no, record.payment_group_account_id.name),
            'ttd1': record.company_id.ttd1 or '',
            'ttd2': record.company_id.ttd2 or '',
            'ttd3': record.company_id.ttd3 or '',
            'ttd4': record.company_id.ttd4 or '',
            'ttd5': record.company_id.ttd5 or '',
            'ttd6': record.company_id.ttd6 or ''
         })
        return record


    # @api.multi
    def write(self, vals):
        if self.env.context.get('skip_name_update'):
            return super(PayablePaymentGroup, self).write(vals)
        res = super(PayablePaymentGroup, self).write(vals)

        for record in self:
            record.refresh()
            record.with_context(skip_name_update=True).write({'title': '{} / {}'.format(record.payment_group_no, record.payment_group_account_id.name) })
        return res




    # @api.multi
    def action_confirm(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only Payment with Draft status can be confirm.'))

            if record.status != 'approved' and record.no_approval is not True:
                raise UserError(_('Only Payment with Approved approval status can be confirm.'))
            
            payment_confirmed = record.payment_ids.filtered(lambda x: x.state == 'confirm')
            if payment_confirmed:
                for payment in payment_confirmed:
                    raise UserError(_(payment.payment_no + ': Only payments with draft status can be confirmed.'))

            for payment in record.payment_ids:
                payment.payment_date = record.payment_group_date
                payment.payment_group_id = record.id 
                payment.action_confirm()

            record.state = 'confirm'
        return True

    
    # @api.multi
    def action_unconfirm(self):
        for record in self:
            if record.state != 'confirm':
                raise UserError(_('Only Payment with Confirm status can be unconfirm.'))

            payment_draft = record.payment_ids.filtered(lambda x: x.state == 'draft')
            if payment_draft:
                for payment in payment_draft:
                    raise UserError(_(payment.payment_no + ': Only payments with confirm status can be unconfirm.'))
            
            for payment in record.payment_ids:
                payment.action_unconfirm()
        return True



    # @api.multi
    def action_cancel(self):
        for record in self:
            # Hanya invoice draft yang boleh dibatalkan
            if record.state != 'draft':
                raise UserError(_('Only Payment with Draft status can be cancelled.'))
            
            for payment in record.payment_ids:
                payment.action_cancel()

            record.state = 'cancel'
        return True



    # @api.multi
    def action_print(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/reporting/payable_payment_group?id=' + str(self.id)
        action['target'] = 'new'
        return action

    # @api.multi
    def action_print_xls(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/reporting/payable_payment_group?id=' + str(self.id) +'&ext=xls'
        action['target'] = 'new'
        return action

    
    # @api.multi
    def action_approval_sheet(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/reporting/payable_payment_group_approval_sheet?id=' + str(self.id)
        action['target'] = 'new'
        return action


class PayableReportWizard(models.TransientModel):
    _name = 'payable.report.wizard'

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    cutoff_date = fields.Date(string="Cutoff Date", required=False)
    type_report = fields.Selection([('aging_supplier', 'AP Aging Per Supplier'),('aging_invoice', 'AP Aging Per Invoice')], string='Type Report', required=True)
    interval_month = fields.Selection([('0','0'),('1','1'),('2','2'),('3','3'),('4','4'),('5','5'),('6','6')], string="Interval Month", default='3')
    supplier_ids = fields.Many2many('payable.supplier', string="Supplier")
    
    # @api.multi
    def action_export(self):
        if self.type_report == 'aging_supplier':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/reporting/payable_aging_supplier?id=' + str(self.id)
            action['target'] = 'new'
            return action
        
        if self.type_report == 'aging_invoice':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/reporting/payable_aging_invoice?id=' + str(self.id)
            action['target'] = 'new'
            return action
            
    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(PayableReportWizard,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="AP Tracking Report Compiled">
                <group>
                    <group>
                        <field name="company_id" required="1"/>
                        <field name="type_report" required="1"/>
                    </group>
                    <group>
                        <field name="cutoff_date" required="1" />
                        <field name="interval_month" required="1" />
                    </group>
                </group>
                <notebook>
                    <page string="AP Suppliers">
                        <field nolabel="1" name="supplier_ids" domain="[('company_id','=',company_id)]"
                            options="{'no_create': True, 'no_create_edit': True}">
                            <tree editable="bottom">
                                <field name="supplier_code"/>
                                <field name="supplier_name"/>
                                <field name="supplier_type"/>
                                <field name="company_id"/>
                            </tree>
                        </field>
                    </page>
                </notebook>
                <footer>
                    <button name="action_export" string="Export Excel" type="object" class="oe_highlight"/>
                </footer>
            </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res



class PayableReport(http.Controller):

    @http.route('/reporting/payable_aging_invoice', type='http', auth="user")
    @route()
    def PayableReportAgingInvoice(self, id, **kw):
        id = int(id)
        sudo = request.env.user.sudo()
        record = sudo.env['payable.report.wizard'].browse(id)
        data = record.read()[0]      
        file_name  = "AP Aging Invoice Traceability as {cutoff}".format(cutoff=record.cutoff_date)
        
        import io
        import xlsxwriter

        output = io.BytesIO()
        response = request.make_response(None, headers=[('Content-Type', 'application/vnd.ms-excel'),('Content-Disposition', content_disposition(file_name + '.xlsx'))])
        workbook = xlsxwriter.Workbook(output, {
            'constant_memory': True, 
            'in_memory': True, 
            'strings_to_numbers':False, 
            'strings_to_formulas':True, 
            'strings_to_urls':True, 
            'default_date_format':'yyyy-mm-dd'
        })

        workbook.set_properties({
            'title':    file_name,
            'comments': 'Created with Odoo and XlsxWriter'
        })
        worksheet = workbook.add_worksheet()
        worksheet.hide_gridlines(2)

        format_title = workbook.add_format()
        format_title.set_font_size(20)
        format_title.set_bold()

        format_header = workbook.add_format()
        format_header.set_bold()
        format_header.set_bg_color('yellow')
        format_header.set_border(1)
        format_header.set_align('center')

        format_content = workbook.add_format()
        format_content.set_bottom(1)

        format_content_normal = workbook.add_format()

        format_currency = workbook.add_format({
            'num_format': '#,##0.00_);(#,##0.00);"-"',
            'align': 'right',
            'bottom': 1,
        })

        format_date = workbook.add_format()
        format_date.set_num_format('dd-mmm-yyyy')
        format_date.set_align('left')
        format_date.set_bottom(1)

        format_datetime = workbook.add_format()
        format_datetime.set_num_format('dd-mmm-yyyy hh:mm')
        format_datetime.set_align('left')
        format_datetime.set_bottom(1)

        format_footer = workbook.add_format()
        format_footer.set_bold()
        format_footer.set_bg_color('#F59C27')
        format_footer.set_bottom(1)
        format_footer.set_align('right')
        format_footer.set_num_format('#,##0.00_);(#,##0.00);"-"')
        
        # setup column
        worksheet.set_column(0, 40, 20)
        worksheet.set_column(7, 7, 50) # patient_name
        worksheet.set_column(10, 10, 50) # payer_name

        # create header
        worksheet.write(0, 0,  file_name, format_title)
        worksheet.write(1, 0, 'Company: ' + record.company_id.name)
        worksheet.write(2, 0, 'Periode: ' + str(record.cutoff_date))

        
        # siapkan supplier filter jika ada supplier dipilih
        supplier_ids = record.supplier_ids.ids
        supplier_filter = ""
        if supplier_ids:
            supplier_filter = " AND inv.supplier_id IN ({})".format(
                ",".join(str(s) for s in supplier_ids)
            )


        query = """
            select inv.*, 
                (case when (inv.aging_days <= 0) then inv.invoice_balance else 0 end) aging_not_overdue,
                (case when (inv.aging_days >= 1 and inv.aging_days <= 30) then inv.invoice_balance else 0 end) aging_30_days, 
                (case when (inv.aging_days >= 31 and inv.aging_days <= 60) then inv.invoice_balance else 0 end) aging_60_days, 
                (case when (inv.aging_days >= 61 and inv.aging_days <= 90) then inv.invoice_balance else 0 end) aging_90_days, 
                (case when (inv.aging_days >= 91) then inv.invoice_balance else 0 end) aging_90_over 
            from (
                select 
                    inv."id", 
                    inv.supplier_type,
                    sup.supplier_code,
                    sup.supplier_name,
                    inv.invoice_no,
                    inv.invoice_type,
                    inv.invoice_source,
                    inv.invoice_notes,
                    inv.invoice_ref,
                    rp."name" invoice_responsible,
                    inv.invoice_date,
                    inv.invoice_exchange_date,
                    inv.invoice_duedate,
                    acc.code invoice_account_code, 
                    acc."name"->>'en_US' invoice_account_name,
                    ((case when inv.invoice_type='INVOICE_RF' then -1 else 1 end) * coalesce(inv.invoice_subtotal,0)) invoice_total,
                    coalesce(dn.total_dn,0) invoice_dn, 
                    coalesce(cn.total_cn,0) invoice_cn,
                    coalesce(dp.total_dp,0) invoice_dp, 
                    coalesce(rf.total_rf,0) invoice_rf,
                    coalesce(py.total_py,0) invoice_py,
                    py.last_payment_date invoice_py_date,
                    (((case when inv.invoice_type='INVOICE_RF' then -1 else 1 end) * coalesce(inv.invoice_subtotal,0))
                    + coalesce(dn.total_dn,0) 
                    + coalesce(cn.total_cn,0)
                    + coalesce(dp.total_dp,0)
                    + coalesce(rf.total_rf,0)
                    + coalesce(py.total_py,0)
                    ) invoice_balance,
                    (DATE('{cutoff_date}') - inv.invoice_duedate) AS aging_days
                from payable_invoice inv 
                inner join payable_supplier sup on sup."id" = inv.supplier_id
                inner join account_account acc on acc."id" = inv.supplier_account_payable_id
                left join res_users ru on ru."id" = inv.invoice_responsible_id 
                left join res_partner rp on rp."id" = ru.partner_id
                left join lateral (
                    select sum(dn.adjust_amount) total_dn 
                    from payable_adjustment dn
                    where dn.invoice_id = inv.id 
                        and dn.company_id = inv.company_id 
                        and dn.state = 'confirm'
                        and dn.adjust_type = 'DN'
                        and date(dn.adjust_date) <= '{cutoff_date}'
                ) dn on 1=1 

                left join lateral (
                    select sum(cn.adjust_amount * -1) total_cn 
                    from payable_adjustment cn 
                    where cn.invoice_id = inv.id 
                        and cn.company_id = inv.company_id 
                        and cn.state = 'confirm'
                        and cn.adjust_type = 'CN'
                        and date(cn.adjust_date) <= '{cutoff_date}'
                ) cn on 1=1 

                left join lateral (
                    select sum(pyl.payment_amount * -1) total_py, max(py.payment_date) last_payment_date  
                    from payable_payment py 
                    inner join payable_payment_line pyl on pyl.payable_payment_id = py.id
                    where py.company_id = inv.company_id 
                        and py.state = 'confirm'
                        and date(py.payment_date) <= '{cutoff_date}'
                        and pyl.payable_invoice_id = inv.id 
                ) py on 1=1 

                left join lateral (
                    select sum(rf.invoice_subtotal * -1) total_rf
                    from payable_invoice rf 
                    where rf.company_id = inv.company_id 
                        and rf.invoice_reverse_id = inv.id 
                        and rf.state = 'confirm'
                        and rf.invoice_type = 'INVOICE_RF'
                        and date(rf.invoice_date) <= '{cutoff_date}'
                ) rf on 1=1 

                left join lateral (
                    select sum(dp.invoice_subtotal * -1) total_dp 
                    from payable_invoice dp
                    where dp.company_id = inv.company_id 
                        and dp.invoice_reverse_id = inv.id 
                        and dp.state = 'confirm'
                        and dp.invoice_type = 'INVOICE_DP'
                        and date(dp.invoice_date) <= '{cutoff_date}'
                ) dp on 1=1 

                where inv.company_id = {company_id}
                    and inv."state" = 'confirm'
                    and (inv.invoice_type in('INVOICE_DP','INVOICE_IB')
                        or (inv.invoice_type in('INVOICE_RF') and coalesce(inv.invoice_reverse_id,0) = 0)
                    )
                    and date(inv.invoice_date) <= '{cutoff_date}'
                    {supplier_filter}
            ) inv 
            where (inv.invoice_balance > 0
                or (
                    inv.invoice_balance <= 0
                    and inv.invoice_duedate >= (date('{cutoff_date}') - interval '{interval} month')
                ))
            order by inv.supplier_code, inv.supplier_name, 
                inv.invoice_type, inv.invoice_no  	
        """.format(
            cutoff_date = record.cutoff_date,
            company_id = record.company_id.id,
            interval = record.interval_month,
            supplier_filter = supplier_filter
        )
        sudo.env.cr.execute(query)
        result = sudo.env.cr.dictfetchall()

        # create header
        worksheet.write(4, 0, 'No', format_header)
        worksheet.write(4, 1, 'Supplier Type', format_header)
        worksheet.write(4, 2, 'Supplier Code', format_header)
        worksheet.write(4, 3, 'Supplier Name', format_header)
        worksheet.write(4, 4, 'Invoice No', format_header)
        worksheet.write(4, 5, 'Invoice Type', format_header)
        worksheet.write(4, 6, 'Source', format_header)
        worksheet.write(4, 7, 'Notes', format_header)
        worksheet.write(4, 8, 'Reference', format_header)
        worksheet.write(4, 9, 'Responsible', format_header)
        worksheet.write(4, 10, 'Invoice Date', format_header)
        worksheet.write(4, 11, 'Exchange Date', format_header)
        worksheet.write(4, 12, 'Due Date', format_header)
        worksheet.write(4, 13, 'Account Code', format_header)
        worksheet.write(4, 14, 'Account Name', format_header)
        worksheet.write(4, 15, 'Invoice Total', format_header)
        worksheet.write(4, 16, 'DebitNote', format_header)
        worksheet.write(4, 17, 'CreditNote', format_header)
        worksheet.write(4, 18, 'DownPayment', format_header)
        worksheet.write(4, 19, 'Refund', format_header)
        worksheet.write(4, 20, 'Payment', format_header)
        worksheet.write(4, 21, 'Last Payment Date', format_header)
        worksheet.write(4, 22, 'Balance', format_header)
        worksheet.write(4, 23, 'Aging Days', format_header)
        worksheet.write(4, 24, 'Not Overdue', format_header)
        worksheet.write(4, 25, '< 30 Days', format_header)
        worksheet.write(4, 26, '< 60 Days', format_header)
        worksheet.write(4, 27, '< 90 Days', format_header)
        worksheet.write(4, 28, '> 90 Days', format_header)

        row = 4
        sno = 0

        for line in result:
            sno += 1
            row += 1

            worksheet.write(row, 0, sno, format_content)
            worksheet.write(row, 1, line['supplier_type'], format_content)
            worksheet.write(row, 2, line['supplier_code'], format_content)
            worksheet.write(row, 3, line['supplier_name'], format_content)
            worksheet.write(row, 4, line['invoice_no'], format_content)
            worksheet.write(row, 5, line['invoice_type'], format_content)
            worksheet.write(row, 6, line['invoice_source'], format_content)
            worksheet.write(row, 7, line['invoice_notes'], format_content)
            worksheet.write(row, 8, line['invoice_ref'], format_content)
            worksheet.write(row, 9, line['invoice_responsible'], format_content)
            worksheet.write(row, 10, to_date(line['invoice_date']), format_date)
            worksheet.write(row, 11, to_date(line['invoice_exchange_date']), format_date)
            worksheet.write(row, 12, to_date(line['invoice_duedate']), format_date)
            worksheet.write(row, 13, line['invoice_account_code'], format_content)
            worksheet.write(row, 14, str(line['invoice_account_name']), format_content)
            worksheet.write(row, 15, line['invoice_total'] or 0, format_currency)
            worksheet.write(row, 16, line['invoice_dn'] or 0, format_currency)
            worksheet.write(row, 17, line['invoice_cn'] or 0, format_currency)
            worksheet.write(row, 18, line['invoice_dp'] or 0, format_currency)
            worksheet.write(row, 19, line['invoice_rf'] or 0, format_currency)
            worksheet.write(row, 20, line['invoice_py'] or 0, format_currency)
            worksheet.write(row, 21, to_date(line['invoice_py_date']), format_date)
            worksheet.write(row, 22, line['invoice_balance'] or 0, format_currency)
            worksheet.write(row, 23, line['aging_days'] or 0, format_currency)
            worksheet.write(row, 24, line['aging_not_overdue'] or 0, format_currency)
            worksheet.write(row, 25, line['aging_30_days'] or 0, format_currency)
            worksheet.write(row, 26, line['aging_60_days'] or 0, format_currency)
            worksheet.write(row, 27, line['aging_90_days'] or 0, format_currency)
            worksheet.write(row, 28, line['aging_90_over'] or 0, format_currency)


        total_row = row + 1
        worksheet.write(total_row, 0, 'TOTAL', format_footer)
        for col in range(1, 15):  
            worksheet.write(total_row, col, '', format_footer)

        for col in range(15, 29):  # kolom numeric dari invoice_total sampai aging_90_over
            col_letter = xlsxwriter.utility.xl_col_to_name(col)
            worksheet.write(total_row, col, '=SUM({}6:{}{})'.format(col_letter, col_letter, row+1), format_footer)
            

        worksheet.set_column(total_row, 0, 5)  
        worksheet.set_column(total_row, 1, 20)  
        worksheet.set_column(total_row, 2, 20)  
        worksheet.set_column(total_row, 3, 40)
        worksheet.set_column(total_row, 4, 20)
        worksheet.set_column(total_row, 5, 20)
        worksheet.set_column(total_row, 6, 20)
        worksheet.set_column(total_row, 7, 40)
        worksheet.set_column(total_row, 8, 40)
        worksheet.set_column(total_row, 9, 40)
        worksheet.set_column(total_row, 10, 20)
        worksheet.set_column(total_row, 11, 20)
        worksheet.set_column(total_row, 12, 20)
        worksheet.set_column(total_row, 13, 20)
        worksheet.set_column(total_row, 14, 50)
        worksheet.set_column(total_row, 15, 20)
        worksheet.set_column(total_row, 16, 20)
        worksheet.set_column(total_row, 17, 20)
        worksheet.set_column(total_row, 18, 20)
        worksheet.set_column(total_row, 19, 20)
        worksheet.set_column(total_row, 20, 20)
        worksheet.set_column(total_row, 21, 20)
        worksheet.set_column(total_row, 22, 20)
        worksheet.set_column(total_row, 23, 20)
        worksheet.set_column(total_row, 24, 20)
        worksheet.set_column(total_row, 25, 20)
        worksheet.set_column(total_row, 26, 20)
        worksheet.set_column(total_row, 27, 20)
        worksheet.set_column(total_row, 28, 20)
        

        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()
        del output # clear 
        return response




    @http.route('/reporting/payable_aging_supplier', type='http', auth="user")
    @route()
    def PayableReportAgingSupplier(self, id, **kw):
        id = int(id)
        sudo = request.env.user.sudo()
        record = sudo.env['payable.report.wizard'].browse(id)
        data = record.read()[0]      
        file_name  = "AP Aging Supplier Traceability as {cutoff}".format(cutoff=record.cutoff_date)
        
        import io
        import xlsxwriter

        output = io.BytesIO()
        response = request.make_response(None, headers=[('Content-Type', 'application/vnd.ms-excel'),('Content-Disposition', content_disposition(file_name + '.xlsx'))])
        workbook = xlsxwriter.Workbook(output, {
            'constant_memory': True, 
            'in_memory': True, 
            'strings_to_numbers':False, 
            'strings_to_formulas':True, 
            'strings_to_urls':True, 
            'default_date_format':'yyyy-mm-dd'
        })

        workbook.set_properties({
            'title':    file_name,
            'comments': 'Created with Odoo and XlsxWriter'
        })
        worksheet = workbook.add_worksheet()
        worksheet.hide_gridlines(2)

        format_title = workbook.add_format()
        format_title.set_font_size(20)
        format_title.set_bold()

        format_header = workbook.add_format()
        format_header.set_bold()
        format_header.set_bg_color('yellow')
        format_header.set_border(1)
        format_header.set_align('center')

        format_content = workbook.add_format()
        format_content.set_bottom(1)

        format_content_normal = workbook.add_format()

        format_currency = workbook.add_format({
            'num_format': '#,##0.00_);(#,##0.00);"-"',
            'align': 'right',
            'bottom': 1,
        })

        format_date = workbook.add_format()
        format_date.set_num_format('dd-mmm-yyyy')
        format_date.set_align('left')
        format_date.set_bottom(1)

        format_datetime = workbook.add_format()
        format_datetime.set_num_format('dd-mmm-yyyy hh:mm')
        format_datetime.set_align('left')
        format_datetime.set_bottom(1)

        format_footer = workbook.add_format()
        format_footer.set_bold()
        format_footer.set_bg_color('#F59C27')
        format_footer.set_bottom(1)
        format_footer.set_align('right')
        format_footer.set_num_format('#,##0.00_);(#,##0.00);"-"')
        
        # setup column
        worksheet.set_column(0, 40, 20)
        worksheet.set_column(7, 7, 50) # patient_name
        worksheet.set_column(10, 10, 50) # payer_name

        # create header
        worksheet.write(0, 0,  file_name, format_title)
        worksheet.write(1, 0, 'Company: ' + record.company_id.name)
        worksheet.write(2, 0, 'Periode: ' + str(record.cutoff_date))

        
        # siapkan supplier filter jika ada supplier dipilih
        supplier_ids = record.supplier_ids.ids
        supplier_filter = ""
        if supplier_ids:
            supplier_filter = " AND inv.supplier_id IN ({})".format(
                ",".join(str(s) for s in supplier_ids)
            )


        query = """
            select 
                inv.supplier_type, inv.supplier_code, inv.supplier_name, 
                inv.invoice_account_code, inv.invoice_account_name->>'en_US' as invoice_account_name,
                sum(inv.invoice_total) invoice_total,
                sum(inv.invoice_dn) invoice_dn,
                sum(inv.invoice_cn) invoice_cn,
                sum(inv.invoice_dp) invoice_dp,
                sum(inv.invoice_rf) invoice_rf,
                sum(inv.invoice_py) invoice_py,
                sum(inv.invoice_balance) invoice_balance,
                sum(case when (inv.aging_days <= 0) then inv.invoice_balance else 0 end) aging_not_overdue,
                sum(case when (inv.aging_days >= 1 and inv.aging_days <= 30) then inv.invoice_balance else 0 end) aging_30_days, 
                sum(case when (inv.aging_days >= 31 and inv.aging_days <= 60) then inv.invoice_balance else 0 end) aging_60_days, 
                sum(case when (inv.aging_days >= 61 and inv.aging_days <= 90) then inv.invoice_balance else 0 end) aging_90_days, 
                sum(case when (inv.aging_days >= 91) then inv.invoice_balance else 0 end) aging_90_over 
            from (
                select 
                    sup.supplier_type,
                    sup.supplier_code,
                    sup.supplier_name,
                    inv.invoice_duedate,
                    acc.code invoice_account_code, 
                    acc."name" invoice_account_name,
                    ((case when inv.invoice_type='INVOICE_RF' then -1 else 1 end) * coalesce(inv.invoice_subtotal,0)) invoice_total,
                    coalesce(dn.total_dn,0) invoice_dn, 
                    coalesce(cn.total_cn,0) invoice_cn,
                    coalesce(dp.total_dp,0) invoice_dp, 
                    coalesce(rf.total_rf,0) invoice_rf,
                    coalesce(py.total_py,0) invoice_py,
                    py.last_payment_date invoice_py_date,
                    (((case when inv.invoice_type='INVOICE_RF' then -1 else 1 end) * coalesce(inv.invoice_subtotal,0))
                    + coalesce(dn.total_dn,0) 
                    + coalesce(cn.total_cn,0)
                    + coalesce(dp.total_dp,0)
                    + coalesce(rf.total_rf,0)
                    + coalesce(py.total_py,0)
                    ) invoice_balance,
                    (DATE('{cutoff_date}') - inv.invoice_duedate) AS aging_days
                from payable_invoice inv 
                inner join payable_supplier sup on sup."id" = inv.supplier_id
                inner join account_account acc on acc."id" = inv.supplier_account_payable_id
                left join res_users ru on ru."id" = inv.invoice_responsible_id 
                left join res_partner rp on rp."id" = ru.partner_id
                left join lateral (
                    select sum(dn.adjust_amount) total_dn 
                    from payable_adjustment dn
                    where dn.invoice_id = inv.id 
                        and dn.company_id = inv.company_id 
                        and dn.state = 'confirm'
                        and dn.adjust_type = 'DN'
                        and date(dn.adjust_date) <= '{cutoff_date}'
                ) dn on 1=1 

                left join lateral (
                    select sum(cn.adjust_amount * -1) total_cn 
                    from payable_adjustment cn 
                    where cn.invoice_id = inv.id 
                        and cn.company_id = inv.company_id 
                        and cn.state = 'confirm'
                        and cn.adjust_type = 'CN'
                        and date(cn.adjust_date) <= '{cutoff_date}'
                ) cn on 1=1 

                left join lateral (
                    select sum(pyl.payment_amount * -1) total_py, max(py.payment_date) last_payment_date  
                    from payable_payment py 
                    inner join payable_payment_line pyl on pyl.payable_payment_id = py.id
                    where py.company_id = inv.company_id 
                        and py.state = 'confirm'
                        and date(py.payment_date) <= '{cutoff_date}'
                        and pyl.payable_invoice_id = inv.id 
                ) py on 1=1 

                left join lateral (
                    select sum(rf.invoice_subtotal * -1) total_rf
                    from payable_invoice rf 
                    where rf.company_id = inv.company_id 
                        and rf.invoice_reverse_id = inv.id 
                        and rf.state = 'confirm'
                        and rf.invoice_type = 'INVOICE_RF'
                        and date(rf.invoice_date) <= '{cutoff_date}'
                ) rf on 1=1 

                left join lateral (
                    select sum(dp.invoice_subtotal * -1) total_dp 
                    from payable_invoice dp
                    where dp.company_id = inv.company_id 
                        and dp.invoice_reverse_id = inv.id 
                        and dp.state = 'confirm'
                        and dp.invoice_type = 'INVOICE_DP'
                        and date(dp.invoice_date) <= '{cutoff_date}'
                ) dp on 1=1 

                where inv.company_id = {company_id}
                    and inv."state" = 'confirm'
                    and (inv.invoice_type in('INVOICE_DP','INVOICE_IB')
                        or (inv.invoice_type in('INVOICE_RF') and coalesce(inv.invoice_reverse_id,0) = 0)
                    )
                    and date(inv.invoice_date) <= '{cutoff_date}'
                    {supplier_filter}
            ) inv 
            group by inv.supplier_type, inv.supplier_code, inv.supplier_name, inv.invoice_account_code, inv.invoice_account_name
            order by inv.supplier_type, inv.supplier_code, inv.supplier_name, inv.invoice_account_code 	
        """.format(
            cutoff_date = record.cutoff_date,
            company_id = record.company_id.id,
            interval = record.interval_month,
            supplier_filter = supplier_filter
        )
        sudo.env.cr.execute(query)
        result = sudo.env.cr.dictfetchall()

        # create header
        worksheet.write(4, 0, 'No', format_header)
        worksheet.write(4, 1, 'Supplier Type', format_header)
        worksheet.write(4, 2, 'Supplier Code', format_header)
        worksheet.write(4, 3, 'Supplier Name', format_header)
        worksheet.write(4, 4, 'Account Code', format_header)
        worksheet.write(4, 5, 'Account Name', format_header)
        worksheet.write(4, 6, 'Invoice Total', format_header)
        worksheet.write(4, 7, 'DebitNote', format_header)
        worksheet.write(4, 8, 'CreditNote', format_header)
        worksheet.write(4, 9, 'DownPayment', format_header)
        worksheet.write(4, 10, 'Refund', format_header)
        worksheet.write(4, 11, 'Payment', format_header)
        worksheet.write(4, 12, 'Balance', format_header)
        worksheet.write(4, 13, 'Not Overdue', format_header)
        worksheet.write(4, 14, '< 30 Days', format_header)
        worksheet.write(4, 15, '< 60 Days', format_header)
        worksheet.write(4, 16, '< 90 Days', format_header)
        worksheet.write(4, 17, '> 90 Days', format_header)

        row = 4
        sno = 0

        for line in result:
            sno += 1
            row += 1

            worksheet.write(row, 0, sno, format_content)
            worksheet.write(row, 1, line['supplier_type'], format_content)
            worksheet.write(row, 2, line['supplier_code'], format_content)
            worksheet.write(row, 3, line['supplier_name'], format_content)
            worksheet.write(row, 4, line['invoice_account_code'], format_content)
            worksheet.write(row, 5, str(line['invoice_account_name']), format_content)
            worksheet.write(row, 6, line['invoice_total'] or 0, format_currency)
            worksheet.write(row, 7, line['invoice_dn'] or 0, format_currency)
            worksheet.write(row, 8, line['invoice_cn'] or 0, format_currency)
            worksheet.write(row, 9, line['invoice_dp'] or 0, format_currency)
            worksheet.write(row, 10, line['invoice_rf'] or 0, format_currency)
            worksheet.write(row, 11, line['invoice_py'] or 0, format_currency)
            worksheet.write(row, 12, line['invoice_balance'] or 0, format_currency)
            worksheet.write(row, 13, line['aging_not_overdue'] or 0, format_currency)
            worksheet.write(row, 14, line['aging_30_days'] or 0, format_currency)
            worksheet.write(row, 15, line['aging_60_days'] or 0, format_currency)
            worksheet.write(row, 16, line['aging_90_days'] or 0, format_currency)
            worksheet.write(row, 17, line['aging_90_over'] or 0, format_currency)


        total_row = row + 1
        worksheet.write(total_row, 0, 'TOTAL', format_footer)
        for col in range(1, 5):  
            worksheet.write(total_row, col, '', format_footer)

        for col in range(5, 18):  # kolom numeric dari invoice_total sampai aging_90_over
            col_letter = xlsxwriter.utility.xl_col_to_name(col)
            worksheet.write(total_row, col, '=SUM({}6:{}{})'.format(col_letter, col_letter, row+1), format_footer)
            

        worksheet.set_column(total_row, 0, 5)  
        worksheet.set_column(total_row, 1, 20)  
        worksheet.set_column(total_row, 2, 20)  
        worksheet.set_column(total_row, 3, 40)
        worksheet.set_column(total_row, 4, 20)
        worksheet.set_column(total_row, 5, 40)
        worksheet.set_column(total_row, 6, 20)
        worksheet.set_column(total_row, 7, 20)
        worksheet.set_column(total_row, 8, 20)
        worksheet.set_column(total_row, 9, 20)
        worksheet.set_column(total_row, 10, 20)
        worksheet.set_column(total_row, 11, 20)
        worksheet.set_column(total_row, 12, 20)
        worksheet.set_column(total_row, 13, 20)
        worksheet.set_column(total_row, 14, 50)
        worksheet.set_column(total_row, 15, 20)
        worksheet.set_column(total_row, 16, 20)
        worksheet.set_column(total_row, 17, 20)

        

        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()
        del output # clear 
        return response


    # Payable Payment Print
    @http.route('/reporting/payable_payment', type='http', auth="user")
    @route()
    def PayablePaymentVoucher(self, id, **kw):
        # open('/opt/odoo16/logs/print_pv.log','a+').write('\n\n OK routing berhasil')
        id = int(id)
        sudo = request.env.user.sudo()
        # get data filter wizard
        record = sudo.env['payable.payment'].browse(id)
        data = {}

        data['company'] = record.company_id.name
        data['address'] = record.company_id.street
        data['city'] = record.company_id.city
        data['zip'] = record.company_id.zip
        data['date'] = (record.payment_date).strftime('%Y-%m-%d')
        data['no'] = record.payment_no
        data['no_cek'] = record.payment_cheque
        data['total_debit'] = 0
        data['total_credit'] = 0

        # data['terbilang'] = num2words(int(record.amount), lang='id', to='currency').title()
        data['ttd1'] = record.ttd1
        data['ttd2'] = record.ttd2
        data['ttd3'] = record.ttd3
        data['ttd4'] = record.ttd4
        data['ttd5'] = record.ttd5
        data['ttd6'] = record.ttd6
        data['position1'] = record.company_id.position1
        data['position2'] = record.company_id.position2
        data['position3'] = record.company_id.position3
        data['position4'] = record.company_id.position4
        data['position5'] = record.company_id.position5
        data['position6'] = record.company_id.position6

        data['line_ids'] = []
        data['terbilang'] = num2words(int(record.payment_amount), lang='id',to='currency').title()


        query = """
            select 
                aa.code account_code,
                aa.name->>'en_US' AS account_name,
                sp.supplier_name partner_name,
                py.description,
                py.payment_ref reference,
                py.debit,
                py.credit
            from (

                -- debit total AP Invoice
                select 
                    pi.supplier_account_payable_id as account_id,  
                    concat('INVOICES') as description,
                    sum(pyl.payment_amount) as debit, 
                    0 as credit, 
                    py.supplier_id,
                    py.payment_ref 
                from payable_payment py
                inner join payable_payment_line pyl on pyl.payable_payment_id = py.id
                inner join payable_invoice pi on pi.id = pyl.payable_invoice_id
                where py.id={payment_id}
                    and py.payment_type = 'WITH_INVOICE'
                GROUP BY pi.supplier_account_payable_id,  
                    py.supplier_id,
                    py.payment_ref 

                
                union all 

                -- debit detail Items
                select 
                    coalesce(pyl.item_account_id, py.supplier_account_payable_id) as account_id,  
                    pyl.item_name as description,
                    abs(case when pyl.item_amount > 0 then pyl.item_amount else 0 end) as debit, 
                    abs(case when pyl.item_amount < 0 then pyl.item_amount else 0 end) as credit, 
                    py.supplier_id,
                    py.payment_ref 
                from payable_payment py
                inner join payable_payment_item pyl on pyl.payable_payment_id = py.id
                where py.id={payment_id}


                union all

                -- sisa selisih = payment_amount - total payment invoice - total payment item > jurnal gelondonhan ke AP
                select 
                    py.supplier_account_payable_id as account_id,  
                    py.payment_ref as description,
                    (py.payment_amount - coalesce(inv.payment_line,0) - coalesce(itm.payment_item,0)) as debit, 
                    0 as credit, 
                    py.supplier_id,
                    py.payment_ref 
                from payable_payment py
                left join lateral (
                    select sum(inv.payment_amount) payment_line
                    from payable_payment_line inv 
                    where inv.payable_payment_id=py.id
                        and py.payment_type = 'WITH_INVOICE'
                ) inv on 1=1
                left join lateral (
                    select sum(itm.item_amount) payment_item
                    from payable_payment_item itm 
                    where itm.payable_payment_id=py.id
                ) itm on 1=1
                where py.id={payment_id}    
                    and (py.payment_amount - coalesce(inv.payment_line,0) - coalesce(itm.payment_item,0)) > 0


                union all 

                -- jika ada credit ke bank (payment_amount - tax_amount + bank_transfer_fee)
                select 
                    py.payment_account_id as account_id,  
                    py.payment_ref as description,
                    0 as debit, 
                    (py.payment_amount 
                        - (case when py.payment_tax_amount < 0 and py.payment_tax_type <> 'NO_TAX' then abs(py.payment_tax_amount) else 0 end)
                        - (case when py.bank_transfer_fee < 0 and py.bank_transfer_type <> 'CASH' then abs(py.bank_transfer_fee) else 0 end)
                    ) as credit, 
                    py.supplier_id,
                    py.payment_ref 
                from payable_payment py
                where py.id={payment_id}

                union all 
                
                -- tambahkan bank transfer fee expense
                select 
                    py.bank_transfer_account_id as account_id,  
                    concat('FEE TRANSFER') as description,
                    py.bank_transfer_fee as debit, 
                    0 as credit, 
                    py.supplier_id,
                    py.payment_ref 
                from payable_payment py
                where py.id={payment_id}
                    and py.bank_transfer_type <> 'CASH'
                    and py.bank_transfer_fee > 0
                
                union all

                -- tambahkan bank transfer fee credit to bank_account
                select 
                    py.payment_account_id as account_id,  
                    concat('FEE TRANSFER') as description,
                    0 as debit, 
                    abs(py.bank_transfer_fee) as credit, 
                    py.supplier_id,
                    py.payment_ref 
                from payable_payment py
                where py.id={payment_id}
                    and py.bank_transfer_type <> 'CASH'
                    and py.bank_transfer_fee <> 0

                union all 


                -- tambahkan tax_amount fee expense
                select 
                    py.payment_tax_expense_id as account_id,  
                    concat(py.payment_tax_type) as description,
                    py.payment_tax_amount as debit, 
                    0 as credit, 
                    py.supplier_id,
                    py.payment_ref 
                from payable_payment py
                where py.id={payment_id}
                    and py.payment_tax_type <> 'NO_TAX'
                    and py.payment_tax_amount > 0

                union all 

                -- tambahkan tax_amount credit to accrue tax
                select 
                    py.payment_tax_account_id as account_id,  
                    concat(py.payment_tax_type) as description,
                    0 as debit, 
                    abs(py.payment_tax_amount) as credit, 
                    py.supplier_id,
                    py.payment_ref 
                from payable_payment py
                where py.id={payment_id}
                    and py.payment_tax_type <> 'NO_TAX'
                    and py.payment_tax_amount <> 0                    

            ) py 
            left join payable_supplier sp on sp.id = py.supplier_id
            left join account_account aa on aa.id = py.account_id
            order by py.debit desc, py.credit, aa.code
        """.format(payment_id=record.id)
        sudo.env.cr.execute(query)
        result_line = sudo.env.cr.dictfetchall()
        # open('/opt/odoo16/logs/print_pv.log','a+').write('\n\n'+str(results))

        for line in result_line:
            obj2 = {}
            obj2['acc_code'] = line['account_code'] or ' '
            obj2['acc'] = line['account_name'] or ' '
            obj2['vendor'] = line['partner_name'] or ' '
            obj2['desc'] = (line['description'] + ' -') or ' '
            obj2['ref'] = line['reference'] or ' '
            obj2['debit'] = line['debit'] or 0.0
            obj2['credit'] = line['credit'] or 0.0
            data['total_debit'] += line['debit'] or 0.0
            data['total_credit'] += line['credit'] or 0.0
            data['line_ids'] += [obj2]

        data = datas.convert(data)
        data = datas.json(data, cdata=False)
        
        # url = request.env.user.company_id.url_host_jasper + "/services/repository?wsdl"
        # uname = request.env.user.company_id.uname_jasper
        # password = request.env.user.company_id.pass_jasper

        # jasper = JasperClient()
        # jasper.login(url, uname, password)

        # if str(record.company_id.name) == 'Mayapada Hospital Surabaya': #MHSB
        #     report = jasper.run('/Mayapada/Accounting/Approval_Payment_Voucher_New', 'PDF',{'data': data})
        # elif str(record.company_id.name) == 'Mayapada Hospital Tangerang': #MHTG
        #     report = jasper.run('/Mayapada/Accounting/Approval_Payment_Voucher_MHTG', 'PDF',{'data': data})
        # else:
        #     report = jasper.run('/Mayapada/Accounting/Approval_Payment_Voucher', 'PDF',{'data': data})
        # filename = "PRINT "+record.payment_no+".pdf"

        # return request.make_response(report[1]["data"],[('Content-Type', report[1]["content-type"]),('Content-Disposition', content_disposition(filename))])

        if str(record.company_id.name) == 'Mayapada Hospital Surabaya': #MHSB
            filepath = '/Mayapada/Accounting/Approval_Payment_Voucher_New'
        elif str(record.company_id.name) == 'Mayapada Hospital Tangerang': #MHTG
            filepath = '/Mayapada/Accounting/Approval_Payment_Voucher_MHTG'
        else:
            filepath = '/Mayapada/Accounting/Approval_Payment_Voucher'

        import requests
        uname = request.env.company.uname_jasper
        password = request.env.company.pass_jasper
        execution = requests.post('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions',
            auth=(uname, password),
            json={
                'reportUnitUri': str(filepath),
                'outputFormat': 'pdf',
                'parameters': {
                    'reportParameter': [{
                        'name': 'data',
                        'value': [data]
                    }]
                }
            })
    
        from lxml import etree
        xml = etree.XML(execution.content)
        request_id = xml.find('.//requestId').text
        export_id = xml.find('.//export//id').text
        result = requests.get('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions/' +request_id + '/exports/' + export_id + '/outputResource',cookies=execution.cookies)
        
        filename = "PRINT " + record.payment_no + ".pdf"
        return request.make_response(result.content,[('Content-Type', result.headers['content-type']),('Content-Disposition', content_disposition(filename))])



    # Payment Grouping AP
    @http.route('/reporting/payable_payment_group', type='http', auth="user")
    @route()
    def PayablePaymentGroup(self, id, ext='pdf', **kw):
        id = int(id)
        sudo = request.env.user.sudo()

        # get data filter wizard
        record = sudo.env['payable.payment.group'].browse(id)
        # data = record.read()[0]
        user = request.env.user
        data = {}
        data['summary'] = " pada tanggal " + (record.payment_group_date).strftime('%Y-%m-%d')

        data['address'] = record.company_id.street or ""
        data['city'] = record.company_id.city or ""
        data['zip'] = record.company_id.zip or ""
        data['phone'] = record.company_id.phone or ""
        data['fax'] = "" #record.company_id.fax or ""
        data['bank_asal'] = record.payment_group_account_id.name or ""
        data['no_giro'] = record.payment_group_cheque or ""
        data['date'] = (record.payment_group_date).strftime('%Y-%m-%d')
        data['total_nominal'] = 0
        data['total_biaya'] = 0
        data['net_total'] = 0
        data['company'] = record.company_id.name or ""
        data['line_ids'] = []
        
        
        if record.payment_ids:
            for pay in record.payment_ids:
                obj = {} 
                obj['bank'] = pay.bank_transfer_id.supplier_bank_id.name or ''
                obj['branch'] = pay.bank_transfer_id.supplier_bank_branch or ''
                obj['journal'] = pay.payment_no
                obj['vendor'] = pay.supplier_id.supplier_name or ''
                obj['no_rekening'] = pay.bank_transfer_id.supplier_bank_account or ''
                obj['untuk'] = pay.bank_transfer_id.supplier_bank_beneficary or ''
                #obj['nominal'] = (pay.payment_amount - (abs(pay.bank_transfer_fee) if pay.bank_transfer_fee < 0 else 0) - (abs(pay.payment_tax_amount) if pay.payment_tax_amount < 0 else 0) )
                obj['nominal'] = pay.payment_amount or 0.0
                #obj['biaya'] = pay.bank_transfer_fee or 0
                obj['biaya'] = (-1.0* (pay.bank_transfer_fee if pay.bank_transfer_fee < 0.0 else 0.0)) or 0.0 # akui biaya jika dipotong dari tagihan vendor
                obj['total'] = obj['nominal'] + obj['biaya']

                data['total_nominal'] += obj['nominal']
                data['total_biaya'] += obj['biaya']
                data['net_total'] += obj['total']
                data['line_ids'] += [obj]

            data = datas.convert(data)
            # open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(data))
            data = datas.json(data, cdata=False)
            # open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(data))

            if str(ext) == 'xls':
                filepath = '/Mayapada/Accounting/Payment_Grouping'
                filename = record.payment_group_no + ".xls"
            elif str(ext) == 'pdf':
                filepath = '/Mayapada/Accounting/Payment_Grouping'
                filename = record.payment_group_no + ".pdf"

            import requests
            uname = request.env.company.uname_jasper
            password = request.env.company.pass_jasper
            execution = requests.post('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions',
                auth=(uname, password),
                json={
                    'reportUnitUri': str(filepath),
                    'outputFormat': 'pdf',
                    'parameters': {
                        'reportParameter': [{
                            'name': 'data',
                            'value': [data]
                        }]
                    }
                })
        
            from lxml import etree
            xml = etree.XML(execution.content)
            request_id = xml.find('.//requestId').text
            export_id = xml.find('.//export//id').text
            result = requests.get('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions/' +request_id + '/exports/' + export_id + '/outputResource',cookies=execution.cookies)
            
            filename = filename
            return request.make_response(result.content,[('Content-Type', result.headers['content-type']),('Content-Disposition', content_disposition(filename))])


        else:
            # return "OOPSSS.... NO DATA AVAILABLE (^_^)"
            return "Oppss.... No Data Available"
            # obj = {}
        # return json.dumps(data)

    

    @http.route('/reporting/payable_payment_group_approval_sheet', type='http', auth="user")
    @route()
    def PayableGroupApprovalSheet(self, id, **kw):
        id = int(id)
        sudo = request.env.user.sudo()

        # get data filter wizard
        record = sudo.env['payable.payment.group'].browse(id)
        #data = record.read()[0]
        ttd = 1
        sign = 1
        data = {}
        data['company'] = record.company_id.name or ''
        data['address'] = record.company_id.street or ''
        data['city'] = record.company_id.city + " " or ' '
        data['zip'] = record.company_id.zip or ''
        data['date'] = (record.payment_group_date).strftime('%Y-%m-%d')
        data['no'] = record.payment_group_no or ''
        data['no_cek'] = record.payment_group_cheque or ''
        data['journal'] = record.payment_group_account_id.name or ''
        data['total_debit'] = 0
        data['total_credit'] = 0
        data['ttd1'] = record.ttd1
        data['ttd2'] = record.ttd2
        data['ttd3'] = record.ttd3
        data['ttd4'] = record.ttd4
        data['ttd_auto1'] = ""
        data['ttd_auto2'] = ""
        data['sign1'] = ""
        data['sign2'] = ""
        for rule_id in record.approve_id.rule_ids.sorted(key=lambda data: data.sequence, reverse=True):
            data['ttd_auto' + str(ttd)] = sudo.env['res.users'].sudo().search([('company_ids', '=', record.company_id.id),('position_id', '=', rule_id.position_id.id)],limit=1).name
            # data['ttd' + str(ttd)] = sudo.env['res.users'].sudo().search([('position_id', '=', rule_id.position_id.id)], limit=1).name
            ttd += 1
        for rule_id in record.approve_id.rule_ids.sorted(key=lambda data: data.sequence, reverse=True):
            data['sign' + str(sign)] = sudo.env['res.users'].sudo().search([('company_ids', '=', record.company_id.id),('position_id', '=', rule_id.position_id.id)],limit=1).sign
            # data['sign' + str(sign)] = sudo.env['res.users'].sudo().search([('position_id', '=', rule_id.position_id.id)], limit=1).sign
            sign += 1
       

        sums = 0
        for pay in record.payment_ids:
            sums += (pay.payment_amount - (abs(pay.bank_transfer_fee) if pay.bank_transfer_fee < 0 else 0) - (abs(pay.payment_tax_amount) if pay.payment_tax_amount < 0 else 0) )
        data['terbilang'] = num2words(int(sums), lang='id',to='currency').title() or ''

        data = datas.convert(data)
        # for k, v in data.items():
        #     data[k] = xml_escape(v)
        data = datas.json(data, cdata=False)
        #data = JSON.dumps(data)
        # print(data)
        
        # url = request.env.user.company_id.url_host_jasper + "/services/repository?wsdl"
        # uname = request.env.user.company_id.uname_jasper
        # password = request.env.user.company_id.pass_jasper

        # jasper = JasperClient()
        # jasper.login(url, uname, password)
        # report = jasper.run('/Mayapada/Accounting/ApprovalPVSheet', 'PDF',{'data': data})
        # filename = "Approval Sheet " + record.payment_group_no +  ".pdf"
        # # return data
        # return request.make_response(report[1]["data"],[('Content-Type', report[1]["content-type"]),('Content-Disposition', content_disposition(filename))])

        import requests
        uname = request.env.company.uname_jasper
        password = request.env.company.pass_jasper
        execution = requests.post('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions',
            auth=(uname, password),
            json={
                'reportUnitUri': '/Mayapada/Accounting/ApprovalPVSheet',
                'outputFormat': 'pdf',
                'parameters': {
                    'reportParameter': [{
                        'name': 'data',
                        'value': [data]
                    }]
                }
            })
    
        from lxml import etree
        xml = etree.XML(execution.content)
        request_id = xml.find('.//requestId').text
        export_id = xml.find('.//export//id').text
        result = requests.get('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions/' +request_id + '/exports/' + export_id + '/outputResource',cookies=execution.cookies)
        
        filename = "Approval Sheet " + str(record.payment_group_no) +  ".pdf"
        return request.make_response(result.content,[('Content-Type', result.headers['content-type']),('Content-Disposition', content_disposition(filename))])