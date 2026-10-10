from . import sync
from . import misc
import logging
import calendar
import requests
# import xlrd
from odoo import models, fields, api, tools, exceptions
from datetime import datetime, timedelta
import itertools
from xml.etree import ElementTree
from operator import itemgetter
try:
    from multiprocess import Process, Manager
except:
    from threading import Thread as Process
import odoo.addons.decimal_precision as dp

_logger = logging.getLogger(__name__)


READONLY_FIELD_STATES = {
    state: [('readonly', True)]
    for state in {'sale', 'done', 'cancel'}
}

LOCKED_FIELD_STATES = {
    state: [('readonly', True)]
    for state in {'done', 'cancel'}
}

INVOICE_STATUS = [
    ('upselling', 'Upselling Opportunity'),
    ('invoiced', 'Fully Invoiced'),
    ('to invoice', 'To Invoice'),
    ('no', 'Nothing to Invoice')
]




# 2021.09.17 - SaleOrder 
class SaleOrder(models.Model):
    _inherit = 'sale.order'
    # _rec_name = 'billno'

    # @api.model
    # def _get_company(self):
    #     return self.env.company.id

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    sync_is_arcus = sync.is_arcus

    #company_id = fields.Many2one('res.company', string="Company", readonly=True, required=True, default=_get_company)
    discharge_date = fields.Datetime(string="Discharge Date", index=True)
    discharge_reason = fields.Char(string="Discharge Reason", index=True)
    admission_type = fields.Char(string="Admission Type", index=True)
    ref_admission_no = fields.Char(string="Ref Admission No.", index=True)
    parent_admission_no = fields.Char(string="Parent Admission", index=True)
    date_order = fields.Datetime(string='Admit Date', required=True, readonly=True, index=True, states={ 'draft': [('readonly', False)], 'sent': [('readonly', False)] }, copy=False, default=fields.Datetime.now())
    confirmation_date = fields.Datetime(string='Bill Date', required=False, readonly=False, index=True, states={ 'draft': [('readonly', False)], 'sent': [('readonly', False)] }, copy=False)
    date_order_wib = fields.Datetime(string='Admission Date', compute="_compute_to_wib", store=True, readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]})
    billno = fields.Char(string="Bill No", readonly=False, index=True)
    primary_doc_id = fields.Many2one('account.analytic.account', string="Primary Doctor", domain=[('sync_wipro_type', '=', 'doctor_internal')], index=True)
    referral_doc_id = fields.Many2one('account.analytic.account', string="Referral Doctor", domain=[('sync_wipro_type', '=', 'doctor_internal')], index=True)
    referral_id = fields.Many2one('referral.transaction', string="Referral Trans", index=True)
    referral_number = fields.Char(string="Referral No.", readonly=False, index=True)
    
    secondary_diagnosis_code = fields.Char(string="Secondary Diagnosis Code", readonly=True, index=True)
    secondary_diagnosis_name = fields.Char(string="Secondary Diagnosis Name", readonly=True, index=True)
    primary_diagnosis_code = fields.Char(string="Primary Diagnosis Code", readonly=True, index=True)
    primary_diagnosis_name = fields.Char(string="Primary Diagnosis Name", readonly=True, index=True)
    repeat_diagnosis_code = fields.Char(string="Repeat Diagnosis Code", readonly=True, index=True)
    repeat_diagnosis_name = fields.Char(string="Repeat Diagnosis Name", readonly=True, index=True)

    bed_type_id = fields.Many2one('hospital.bed.type', string="Billable BedType")
    eligible_bed_type_id = fields.Many2one('hospital.bed.type', string="Eligible BedType")
    alloted_bed_type_id = fields.Many2one('hospital.bed.type', string="Alloted BedType")

    specialization_id = fields.Many2one('hospital.specialization', string='Specialization')
    patient_type = fields.Selection([('1', 'OP'), ('2', 'IP'), ('3', 'Emergency'), ('4', 'Daycare'), ('5', 'MCU/Pharmacy Issues Only(FO)'), ('6', 'Pharmacy (Direct)'), ('0', 'Both')], string='Patient Type', readonly=True, index=True)
    department_id = fields.Many2one('hospital.department', string="Department", index=True)
    partner_id = fields.Many2one('res.partner', string='Patient Name', readonly=True, states={ 'draft': [('readonly', False)], 'sent': [('readonly', False)] }, required=True, change_default=True, index=True, tracking=True)
    backup_partner_id = fields.Float(string="Backup Partner ID", index=True)
    updated_date = fields.Boolean(string="Update Date", readonly=True, default=False)
    patient_type_id = fields.Many2one('hospital.patient.type', string="Patient Type", readonly=True, related='partner_id.patient_type_id')
    registration_code = fields.Char(string="Patient MRID", related='partner_id.registration_code', readonly=True, index=True)
    gender = fields.Selection(related='partner_id.gender', readonly=True)
    age = fields.Integer(string="Age", default=1, compute='_age', store=True, readonly=True)
    age_full = fields.Char(string="Full Age", compute='_age', store=True, readonly=True)
    age_type = fields.Selection([('year', 'Year'), ('month', 'Month')], string='Age Type', related='partner_id.age_type', readonly=True)
    payer_type = fields.Char(string="Payer Type", readonly=True, index=True)
    payer_code = fields.Char(string="Payer Code", readonly=True, index=True)
    payer_id = fields.Many2one('res.partner', string="Payer Name", domain=[('insurance', '=', True)], index=True)
    tariff_id = fields.Many2one('hospital.tariff', string="Tariff")
    validity_date = fields.Date(string="Process Date")
    service_id = fields.Many2one('hospital.service', string="Service")
    status_bill = fields.Char(string="Status Bill", index=True)
    sync_deduction = fields.Boolean(string="Sync Done", default=False, store=True)
    sync_line_date = fields.Date(string="Latest Sync Line", store=True)
    tglproses = fields.Date(string="TglProses", store=True, index=True)
    order_no = fields.Char(string="Order Number")
    order_date = fields.Date(string="Order Date")
    payer_amount = fields.Float(string="Main Payer Amount", store=True)
    subpayer_amount = fields.Float(string="Sub Payer Amount", store=True)
    personal_amount = fields.Float(string="Personal Amount", store=True)
    total_amount = fields.Float(string="Total Amount")
    payer_adjustment = fields.Float(string="Payer Discount (Before Invoice)")
    payer_credit = fields.Float(string="Payer Credit")
    payer_receipt = fields.Float(string="Payer Receipt")
    payer_discount = fields.Float(string="Payer Discount")
    payer_balance = fields.Float(string="Payer Balance")
    payer_discount = fields.Float(string="Payer Discount")

    personal_receipt = fields.Float(string="Personal Receipt")
    personal_balance = fields.Float(string="Personal Balance")
    
    covering_id = fields.Many2one('account.coveringletter', string="Covering Letter")
    payment_id = fields.Many2one('account.payment', string="Payment")
    nama_asuransi = fields.Char(string="Insurance Card Name", index=True, readonly=True)
    nomor_asuransi = fields.Char(string="No. Kartu Asuransi", index=True, readonly=True)
    no_asuransi = fields.Char(string="Insurance Card No.", index=True, readonly=True)
    penjualanresep = fields.Boolean(string="OTC Bill", default=False, store=True)
    state = fields.Selection([
        ('draft', 'New Admission'),
        ('sent', 'Confirmed'),
        ('sale', 'Accrual'),
        ('done', 'Paid'),
        ('invoice', 'Invoiced'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True, copy=False, index=True, tracking=True, default='draft')
    scroll_receipt_ids = fields.One2many('scroll.receipt.cashier','admission_id',string="Scroll Receipt Cashier", ondelete='set null')
    inpatient_deposit_ids = fields.One2many('inpatient.deposit','admission_id',string="Deposit Collection", ondelete='set null')
    billing_ids = fields.One2many('sale.order.bill','admission_id', string="Billing Payment", ondelete='set null')

    covering_ids = fields.Many2many('account.coveringletter', relation="account_coveringletter_admission_rel", string="Covering Letter", tracking=True)
    discount_ids = fields.One2many('account.creditnote.line', 'billing_id', string="Credit Notes")
    payment_ids = fields.One2many('account.payment.admission.rel', 'sale_order_id', string="Receipts")
    procurement_group_id = fields.Many2one('procurement.group', string="Procurement Group")
    procurement_created = fields.Boolean(string="Procurement Created", default=False)

    wipro_block = fields.Boolean(string="HIS Blocked")
    message_last_post = fields.Datetime(string="Message Last Post", index=True, readonly=True)
    project_id = fields.Many2one('account.analytic.account', string="Analytic Account")

    perform_doc_id = fields.Many2one('account.analytic.account', string='Perform Doctor', index=True)
    prescribe_doc_id = fields.Many2one('account.analytic.account', string='Prescribe Doctor', index=True)
    primary_doc_spec = fields.Char(string="Perform Doc ID", store=True, index=True, readonly=True)


    cutoff_date = fields.Date(string="Cutoff Date")
    patient_type_name = fields.Char(string="Patient Type Name")
    patient_mrid = fields.Char(string="Patient MRID")
    patient_ref_no = fields.Char(string="Patient Ref No.")
    patient_name = fields.Char(string="Patient Name")
    payer_name = fields.Char(string="Payer Name")
    primary_doc_code = fields.Char(string="primary Doctor Code")
    primary_doc_name = fields.Char(string="primary Doctor Name")
    referral_doc_code = fields.Char(string="Referral Doctor Code")
    referral_doc_name = fields.Char(string="Referral Doctor Name")
    tariff_name = fields.Char(string="Tariff Name")
    bed_type_name = fields.Char(string="Bed Type Name")
    eligible_bed_type_name = fields.Char(string="Eligible Bed Type Name")
    alloted_bed_type_name = fields.Char(string="Alloted Bed Type Name")
    
    diagnoses_ids = fields.One2many('sale.diagnoses', 'admission_id', string="Diagnoses")
    procedure_ids = fields.One2many('sale.procedure', 'admission_id', string="Procedure")


    # invoice_count = fields.Integer(string="Invoice Count", compute='_get_invoiced')
    # invoice_ids = fields.Many2many(
    #     comodel_name='account.move',
    #     string="Invoices",
    #     compute='_get_invoiced',
    #     search='_search_invoice_ids',
    #     copy=False)
    # invoice_status = fields.Selection(
    #     selection=INVOICE_STATUS,
    #     string="Invoice Status",
    #     compute='_compute_invoice_status',
    #     store=True)

    # invoice_count = fields.Integer(string="Invoice Count")
    # invoice_ids = fields.Many2many(comodel_name='account.move', string="Invoices", copy=False)
    # invoice_status = fields.Selection(selection=INVOICE_STATUS, string="Invoice Status", store=True)




    # 2021.06.12 - Firgiawan Khafidli 
    # Override _amount_all() depends order_line.price_total bawaan base module odoo
    # Integrasi Dhealth berat untuk create/write data ke sale.order.line u/ transaksi sale.order yg sudah memiliki banyak child record
    @api.depends('order_line.price_total')
    def _amount_all(self):
        """
        Compute the total amounts of the SO.
        """


    # 2021.06.12 - Firgiawan Khafidli 
    # Override _get_tax_amount_by_group() bawaan base module odoo
    # Integrasi Dhealth berat untuk create/write data ke sale.order.line u/ transaksi sale.order yg sudah memiliki banyak child record
    # @api.multi
    def _get_tax_amount_by_group(self):
        self.ensure_one()
        res = {}
        # currency = self.currency_id or self.company_id.currency_id
        # for line in self.order_line:
        #     price_reduce = line.price_unit * (1.0 - line.discount / 100.0)
        #     taxes = line.tax_id.compute_all(price_reduce, quantity=line.product_uom_qty, product=line.product_id, partner=self.partner_shipping_id)['taxes']
        #     for tax in line.tax_id:
        #         group = tax.tax_group_id
        #         res.setdefault(group, 0.0)
        #         for t in taxes:
        #             if t['id'] == tax.id or t['id'] in tax.children_tax_ids.ids:
        #                 res[group] += t['amount']
        # res = sorted(res.items(), key=lambda l: l[0].sequence)
        # res = map(lambda l: (l[0].name, l[1]), res)
        return res



    # 2021.06.12 - Firgiawan Khafidli 
    # Override _get_invoiced() depends order_line.invoice_status bawaan base module odoo
    # Integrasi Dhealth berat untuk create/write data ke sale.order.line u/ transaksi sale.order yg sudah memiliki banyak child record
    @api.depends('state', 'order_line.invoice_status')
    def _get_invoiced(self):
        for order in self:
            order.invoice_ids = False
            order.invoice_count = 0

        """
        Compute the invoice status of a SO. Possible statuses:
        - no: if the SO is not in status 'sale' or 'done', we consider that there is nothing to
          invoice. This is also hte default value if the conditions of no other status is met.
        - to invoice: if any SO line is 'to invoice', the whole SO is 'to invoice'
        - invoiced: if all SO lines are invoiced, the SO is invoiced.
        - upselling: if all SO lines are invoiced or upselling, the status is upselling.

        The invoice_ids are obtained thanks to the invoice lines of the SO lines, and we also search
        for possible refunds created directly from existing invoices. This is necessary since such a
        refund is not directly linked to the SO.
        """


    # 2021.06.12 - Firgiawan Khafidli 
    # Override _compute_tax_id() depends fiscal_position_id bawaan base module odoo
    # Integrasi Dhealth berat untuk create/write data ke sale.order.line u/ transaksi sale.order yg sudah memiliki banyak child record
    @api.onchange('fiscal_position_id')
    def _compute_tax_id(self):
        """
        Trigger the recompute of the taxes if the fiscal position is changed on the SO.
        """

    # @api.multi
    def action_cancel(self):
        self.sudo().write({'state': 'cancel'})
        return


    @api.model
    def create(self, vals):
        result = super(SaleOrder, self).create(vals)
        # for record in result:
        #     record.company_id = self.env.company.id
        # for record in result:
        #     if record.env.company.sync_api_active == True:
        #         record.env.cr.execute("DELETE from sale_order where id in (select max(a.id) from sale_order a where a.sync_id_api is not null group by a.sync_id_api having count(*) > 1)")
        #         date_wib = False

        #         if record.date_order:
        #             #udah diupdate di server linux app & db serta postgreSQL datetime WIB
        #             date_wib = tools.datetime.strptime(record.date_order,'%Y-%m-%d %H:%M:%S') - tools.timedelta(hours=7)
        #             open('/opt/odoo16/logs/date.log', 'a+').write('\n' + 'BARU' + str(date_wib))
        #             record.date_order = date_wib

        #         if record.confirmation_date:
        #             #udah diupdate di server linux app & db serta postgreSQL datetime WIB
        #             date_wib = tools.datetime.strptime(record.confirmation_date,'%Y-%m-%d %H:%M:%S') - tools.timedelta(hours=7)
        #             open('/opt/odoo16/logs/date.log', 'a+').write('\n' + 'BARU' + str(date_wib))
        #             record.confirmation_date = date_wib
                
        #         #comment dulu ngg usah dibuat auto-confirm
        #         if record.billno and record.order_line and self.state == 'draft':
        #             record.action_confirm()
        return result



    # @api.multi
    def write(self, values):
        result = super(SaleOrder, self).write(values)
        if self.env.context.get('ganti_date'): return result
        self = self.with_context(ganti_date=True)

        #if values.get('date_order'):
            # date_wib = tools.datetime.strptime(str(values.get('date_order')), '%Y-%m-%d %H:%M:%S') - tools.timedelta(hours=7)
            # udah diupdate di server linux app & db serta postgreSQL datetime WIB
            # jika write sale.order (record exists) baru update date_order = date_wib
            # if self.date_order and date_wib:
            #    self.date_order = date_wib

        #if values.get('confirmation_date'):
            # date_wib = tools.datetime.strptime(str(values.get('confirmation_date')), '%Y-%m-%d %H:%M:%S') - tools.timedelta(hours=7)
            # udah diupdate di server linux app & db serta postgreSQL datetime WIB
            # jika write sale.order (record exists) baru update date_order = date_wib
            # if self.confirmation_date and date_wib:
            #    self.confirmation_date = date_wib

        # sementara comment dulu ngg usah dibuat auto confirm, biar trigger dari dhealth
        # if self.billno and self.order_line and self.state == 'draft':
        #    self.action_confirm()
        return result



    # @api.multi
    # def name_get(self):
    #     res = []
    #     for sale in self:
    #         if sale.billno:
    #             res.append((sale.id, sale.name + ' ' + sale.billno))
    #         else:
    #             res.append((sale.id, sale.name))
    #     return res

    # @api.one
    @api.depends('date_order', 'partner_id', 'partner_id.date_of_birth')
    def _age(self):
        for record in self:
            if record.partner_id.date_of_birth:
                age = tools.relativedelta(tools.datetime.strptime(record.date_order, '%Y-%m-%d %H:%M:%S'), tools.datetime.strptime(record.partner_id.date_of_birth,'%Y-%m-%d'))
                record.age = age.years
                record.age_full = "%s years and %s months" % (age.years, age.months)

    # @api.one
    @api.depends('date_order')
    def _compute_to_wib(self):
        for record in self:
            if record.date_order:
                record.date_order_wib = record.date_order - timedelta(hours=7)


    # create action model create_invoice
    @api.model
    def create_invoice_today(self):
        # order_ids = self.env['sale.order.line'].sudo().search([('type_line', '=', 'BILL'), ('order_id.tglproses', '=', tools.datetime.now().strftime('%Y-%m-%d'))]).mapped('order_id')
        # order_ids.action_invoice_create()
        print("Do something...")


    # create action model lock_bill to update sale.order to "done"
    @api.model
    def lock_bill(self):
        self.env.cr.execute("""
            SELECT distinct order_id
            from sale_order_line 
            inner join sale_order on order_id = sale_order.id
            where sale_order.state != 'done' 
                and sale_order_line.type_line = 'BILL'""")
        records = self.sudo().browse([object[0] for object in self.env.cr.fetchall() if object])
        if records:
            records.action_done()


    # ngg tau ini fungsi buat apaan ??
    # @api.multi
    def _prepare_invoice(self):
        res = super(SaleOrder, self)._prepare_invoice()
        res.update({'sync_id': self.sync_id, 'sync_type': self.sync_type})
        return res


    # create action model auto_confirm >> update state to "done"
    # sementara ngg usah pakai fungsi ini dulu biar update flag state "done" sale.order dari dhealth
    # @api.multi
    def action_confirm(self):
        for order in self:
            order.state = 'done'
        #     _logger.warning('debug %r', dir(order.order_line))
        #     order.state = 'sale'
        #     order.confirmation_date = fields.Datetime.now()

        #     # self._accrual_confirm();
        #     if self.env.context.get('send_email'):
        #         self.force_quotation_send()
        #     order.order_line._action_procurement_create()

        # if self.env['ir.values'].get_default('sale.config.settings', 'auto_done_setting'):
        #     self.action_done()
        return True


    # create action model _accrual_confirm u/ auto create journal accrual revenue ?
    # ngg usah dipakai terlebih dahulu
    # @api.multi
    def _accrual_confirm(self):
        # orderid = self.env['sale.order'].search([['name', '=', self.name]])
        # orderline = self.env['sale.order.line'].search([['order_id', '=', orderid.id]])
        # total = 0
        # for mov in self.order_line:
        #     total = total + mov.price_total
        # first_line = {}
        # second_line = {}
        # xacct = self.env['account.account'].search([['name', '=', 'Income Receivable Accrual']])
        # line_idss = []
        # for index, move in enumerate(self.order_line):
        #     income_account = move.product_id.categ_id.property_account_income_categ_id
        #     print move.product_id.categ_id.property_account_accrual_id
        #     _logger.warning('income %r', income_account.id)
        #     _logger.warning('name %r', move.name)
        #     income_account = False
        #     if move.product_id.id:
        #         income_account = move.product_id.categ_id.property_account_income_categ_id.id or move.product_id.categ_id.property_account_income_categ_id.id
        #     if not income_account:
        #         inc_acc = ir_property_obj.get('property_account_income_categ_id', 'product.category')
        #         income_account = order.fiscal_position_id.map_account(inc_acc).id if inc_acc else False
        #     if not income_account:
        #         raise exceptions.UserError(_('Please define income account for this product: "%s" (id:%d) - or for its category: "%s".') % (move.name, move.product_id, move.product_id.categ_id.name))
        #     else:
        #         vals_line_cr = {'account_id':income_account,'name':"%s %s %s" % (move.name, move.order_id.partner_id.id, self.registration_code),'credit':move.price_total,'debit': 0}
        #         vals_line_debt = {'account_id':xacct.id,'name':"%s %s %s" % (move.name, move.order_id.partner_id.id, self.registration_code),'debit':move.price_total,'credit':0}
        #         line_idss.append((0, 0, vals_line_cr))
        #         line_idss.append((0, 0, vals_line_debt))
        # _logger.info('lineids %r', line_idss)
        # vals = {'name': 'ACC/%s' % self.registration_code, 'journal_id': 2, 'date': tools.datetime.now().strftime('%Y-%m-%d %H:%M:S'), 'total': total, 'state': 'draft', 'line_ids': line_idss }
        # _logger.warning('vals %r', vals)
        # account_move = self.env['account.move'].create(vals)
        print('Do something..')


#     # auto sync sale diagnosis 
#     @api.model
#     def _sync_sale_diagnosis(self, sync_type='1'):
#         # sync_ids = { record.sync_id: record.id for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)])}
#         # sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
#         data = []
#         sync_ids = []
#         date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
#         # date = '2019-01-25'
#         print ("Proses")
#         query = """
#             SELECT 
#                 --PD.TglProses,
#                 PD.sync_type,
#                 PD.IPID sync_id,
#                 -- PD.BillID billing_id,
#                 ISNULL(DS.FinalDiagnosisCode,'') primary_diagnosis_code,
#                 ISNULL(DS.FinalDiagnosisName,'') primary_diagnosis_name,
#                 ISNULL(DS.ProvDiagnosisCode,'') secondary_diagnosis_code,
#                 ISNULL(DS.ProvDiagnosisName,'') secondary_diagnosis_name,
#                 ISNULL(DS.RepeatDiagnosisCode,'') repeat_diagnosis_code,
#                 ISNULL(DS.RepeatDiagnosisName,'') repeat_diagnosis_name,
#                 DS.PrevAdmissionId prev_admission_id
#             FROM dbo.VRP_OdooPatientDisease PD
#             OUTER APPLY dbo.fn_A_A_OdooDiagnosisPatient(PD.IPID) DS
#             WHERE PD.TglProses >= dateadd(day, -5, convert(datetime, '%s', 121))
#             """ % (date)
#         print (query)
#         values = ''
#         data += sync.get_data(sync.servers.get(sync_type), query)
#         print (data)
#         for row in data:
#             sync_ids.append(row['sync_id'])
#             primary_diagnosis_code = row['primary_diagnosis_code'].replace("'", "''").encode('utf-8')
#             primary_diagnosis_name = row['primary_diagnosis_name'].replace("'", "''").encode('utf-8')
#             secondary_diagnosis_code = row['secondary_diagnosis_code'].replace("'", "''").encode('utf-8')
#             secondary_diagnosis_name = row['secondary_diagnosis_name'].replace("'", "''").encode('utf-8')
#             repeat_diagnosis_code = row['repeat_diagnosis_code'].replace("'", "''").encode('utf-8')
#             repeat_diagnosis_name = row['repeat_diagnosis_name'].replace("'", "''").encode('utf-8')

#             # update sale.order
#             query = """
#                 UPDATE sale_order SET 
#                     primary_diagnosis_code = '{primary_diagnosis_code}',
#                     primary_diagnosis_name = '{primary_diagnosis_name}',
#                     secondary_diagnosis_code = '{secondary_diagnosis_code}',
#                     secondary_diagnosis_name = '{secondary_diagnosis_name}',
#                     repeat_diagnosis_code = '{repeat_diagnosis_code}',
#                     repeat_diagnosis_name = '{repeat_diagnosis_name}'
#                 WHERE sync_type = '{sync_type}'
#                 AND sync_id = {sync_id}
#             """ . format(
#                 primary_diagnosis_code = primary_diagnosis_code,
#                 primary_diagnosis_name = primary_diagnosis_name,
#                 secondary_diagnosis_code = secondary_diagnosis_code,
#                 secondary_diagnosis_name = secondary_diagnosis_name,
#                 repeat_diagnosis_code = repeat_diagnosis_code,
#                 repeat_diagnosis_name = repeat_diagnosis_name,
#                 sync_type = row['sync_type'],
#                 sync_id = row['sync_id']
#             )
#             print (query)
#             self.env.cr.execute(query)

#         # update sale.order.bill
#         sync_ids = tuple(sync_ids)
#         query = """
#             UPDATE sale_order_bill AS a SET 
#                 primary_diagnosis_code = b.primary_diagnosis_code,
#                 primary_diagnosis_name = b.primary_diagnosis_name,
#                 secondary_diagnosis_code = b.secondary_diagnosis_code,
#                 secondary_diagnosis_name = b.secondary_diagnosis_name,
#                 repeat_diagnosis_code = b.repeat_diagnosis_code,
#                 repeat_diagnosis_name = b.repeat_diagnosis_name
#             FROM sale_order b
#             WHERE a.admission_id = b.id 
#                 AND b.sync_type = '{sync_type}'
#                 AND b.sync_id in {sync_ids}
#         """ . format(
#             sync_type = row['sync_type'],
#             sync_ids = sync_ids)
#         print (query.encode('utf8'))
#         self.env.cr.execute(query)

#         # update sale.order.line
#         query = """
#             UPDATE sale_order_line AS a SET 
#                 primary_diagnosis_code = b.primary_diagnosis_code,
#                 primary_diagnosis_name = b.primary_diagnosis_name,
#                 secondary_diagnosis_code = b.secondary_diagnosis_code,
#                 secondary_diagnosis_name = b.secondary_diagnosis_name,
#                 repeat_diagnosis_code = b.repeat_diagnosis_code,
#                 repeat_diagnosis_name = b.repeat_diagnosis_name
#             FROM sale_order b
#             WHERE a.order_id = b.id 
#                 AND b.sync_type = '{sync_type}'
#                 AND b.sync_id in {sync_ids}
#         """ . format(
#             sync_type = row['sync_type'],
#             sync_ids = sync_ids)
#         print (query.encode('utf8'))
#         self.env.cr.execute(query)


#     # auto sync sale diagnosis 
#     @api.model
#     def _sync_sale_diagnosis_manual(self, sync_type='1', date_start = '2021-01-01', date_end = '2021-01-01'):
#         # sync_ids = { record.sync_id: record.id for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)])}
#         # sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
#         data = []
#         #date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
#         # date = '2019-01-25'
#         query = """
#             SELECT 
#                 --PD.TglProses,
#                 PD.sync_type,
#                 PD.IPID sync_id,
#                 -- PD.BillID billing_id,
#                 ISNULL(DS.FinalDiagnosisCode,'') primary_diagnosis_code,
#                 ISNULL(DS.FinalDiagnosisName,'') primary_diagnosis_name,
#                 ISNULL(DS.ProvDiagnosisCode,'') secondary_diagnosis_code,
#                 ISNULL(DS.ProvDiagnosisName,'') secondary_diagnosis_name,
#                 ISNULL(DS.RepeatDiagnosisCode,'') repeat_diagnosis_code,
#                 ISNULL(DS.RepeatDiagnosisName,'') repeat_diagnosis_name,
#                 DS.PrevAdmissionId prev_admission_id
#             FROM dbo.VRP_OdooPatientDisease PD
#             OUTER APPLY dbo.fn_A_A_OdooDiagnosisPatient(PD.IPID) DS
#             WHERE PD.TglProses >= '%s'
#                 AND PD.TglProses <= '%s'
#             """ % (date_start, date_end)
#         print (query)
#         values = ''
#         data += sync.get_data(sync.servers.get(sync_type), query)
#         print (data)
#         for row in data:
#             sync_ids.append(row['sync_id'])
#             primary_diagnosis_code = row['primary_diagnosis_code'].replace("'", "''").encode('utf-8')
#             primary_diagnosis_name = row['primary_diagnosis_name'].replace("'", "''").encode('utf-8')
#             secondary_diagnosis_code = row['secondary_diagnosis_code'].replace("'", "''").encode('utf-8')
#             secondary_diagnosis_name = row['secondary_diagnosis_name'].replace("'", "''").encode('utf-8')
#             repeat_diagnosis_code = row['repeat_diagnosis_code'].replace("'", "''").encode('utf-8')
#             repeat_diagnosis_name = row['repeat_diagnosis_name'].replace("'", "''").encode('utf-8')

#             # update sale.order
#             query = """
#                 UPDATE sale_order SET 
#                     primary_diagnosis_code = '{primary_diagnosis_code}',
#                     primary_diagnosis_name = '{primary_diagnosis_name}',
#                     secondary_diagnosis_code = '{secondary_diagnosis_code}',
#                     secondary_diagnosis_name = '{secondary_diagnosis_name}',
#                     repeat_diagnosis_code = '{repeat_diagnosis_code}',
#                     repeat_diagnosis_name = '{repeat_diagnosis_name}'
#                 WHERE sync_type = '{sync_type}'
#                 AND sync_id = {sync_id}
#             """ . format(
#                 primary_diagnosis_code = primary_diagnosis_code,
#                 primary_diagnosis_name = primary_diagnosis_name,
#                 secondary_diagnosis_code = secondary_diagnosis_code,
#                 secondary_diagnosis_name = secondary_diagnosis_name,
#                 repeat_diagnosis_code = repeat_diagnosis_code,
#                 repeat_diagnosis_name = repeat_diagnosis_name,
#                 sync_type = row['sync_type'],
#                 sync_id = row['sync_id']
#             )
#             print (query.encode('utf8'))
#             self.env.cr.execute(query)

#         # update sale.order.bill
#         sync_ids = tuple(sync_ids)
#         query = """
#             UPDATE sale_order_bill AS a SET 
#                 primary_diagnosis_code = b.primary_diagnosis_code,
#                 primary_diagnosis_name = b.primary_diagnosis_name,
#                 secondary_diagnosis_code = b.secondary_diagnosis_code,
#                 secondary_diagnosis_name = b.secondary_diagnosis_name,
#                 repeat_diagnosis_code = b.repeat_diagnosis_code,
#                 repeat_diagnosis_name = b.repeat_diagnosis_name
#             FROM sale_order b
#             WHERE a.admission_id = b.id 
#                 AND b.sync_type = '{sync_type}'
#                 AND b.sync_id in {sync_ids}
#         """ . format(
#             sync_type = row['sync_type'],
#             sync_ids = sync_ids)
#         print (query.encode('utf8'))
#         self.env.cr.execute(query)

#         # update sale.order.line
#         query = """
#             UPDATE sale_order_line AS a SET 
#                 primary_diagnosis_code = b.primary_diagnosis_code,
#                 primary_diagnosis_name = b.primary_diagnosis_name,
#                 secondary_diagnosis_code = b.secondary_diagnosis_code,
#                 secondary_diagnosis_name = b.secondary_diagnosis_name,
#                 repeat_diagnosis_code = b.repeat_diagnosis_code,
#                 repeat_diagnosis_name = b.repeat_diagnosis_name
#             FROM sale_order b
#             WHERE a.order_id = b.id 
#                 AND b.sync_type = '{sync_type}'
#                 AND b.sync_id in {sync_ids}
#         """ . format(
#             sync_type = row['sync_type'],
#             sync_ids = sync_ids)
#         print (query)
#         self.env.cr.execute(query)



#     @api.model
#     def _sync_sale_wipro(self, sync_type='1'):
#         sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)])}
#         sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
#         data = []
#         date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
#         # date = '2019-01-25'
#         query_admission = """
#             SELECT
#                 a.AdmissionID AS sync_id,
#                 a.AdmissionNumber AS name,
#                 (CASE 
#                     WHEN a.PatientID IS NULL or PatientID = 0 
#                     THEN 918273 ELSE PatientID 
#                 END) AS partner_id,
#                 a.AdmitDate AS date_order,
#                 max(a.BillNo) AS billno,
#                 max(a.BillDate) AS confirmation_date,
#                 max(a.DischargeReason) AS discharge_reason,
#                 max(a.DischargeDate) AS discharge_date,
#                 max(a.BillableBedTypeID) AS bed_type_id,
#                 max(a.EligibleBedTypeID) AS eligible_bed_type_id,
#                 max(a.AllotedBedTypeID) AS alloted_bed_type_id,
#                 max(a.PrimaryDocID) AS primary_doc_id,
#                 max(a.ReferralDoctorId) AS referral_doc_id,
#                 max(a.ReferralId) AS referral_id,
#                 max(a.ReferralNumber) AS referral_number,
#                 max(a.PayerID) AS payer_id,
#                 max(a.TariffID) AS tariff_id,
#                 max(a.PayerCode) AS payer_code,
#                 max(a.PayerType) AS payer_type,
#                 (CASE a.PatientType
#                     WHEN 'OutPatient' THEN 1
#                     WHEN 'InPatient' THEN 2
#                     WHEN 'Emergency' THEN 3
#                     WHEN 'Daycare' THEN 4
#                     WHEN 'FO' THEN 5
#                     WHEN 'Pharmacy' THEN 6
#                 END) AS patient_type,
#                 max(a.ProvDiagnosisCode) secondary_diagnosis_code,
#                 max(a.ProvDiagnosisName) secondary_diagnosis_name,
#                 max(a.FinalDiagnosisCode) primary_diagnosis_code,
#                 max(a.FinalDiagnosisName) primary_diagnosis_name,
#                 max(a.RepeatDiagnosisCode) repeat_diagnosis_code,
#                 max(a.RepeatDiagnosisName) repeat_diagnosis_name,
#                 max(a.AdmissionType) admission_type,
#                 'draft' AS state
#             FROM dbo.V_Db_A_A_RawDataH30 a
#             WHERE a.TglProses = '%s'
#                 AND a.AdmissionID IS NOT NULL
#             GROUP BY
#                 a.AdmissionNumber,
#                 a.PatientID,
#                 a.AdmitDate,
#                 a.AdmissionID,
#                 (CASE a.PatientType
#                     WHEN 'OutPatient' THEN 1
#                     WHEN 'InPatient' THEN 2
#                     WHEN 'Emergency' THEN 3
#                     WHEN 'Daycare' THEN 4
#                     WHEN 'FO' THEN 5
#                     WHEN 'Pharmacy' THEN 6
#                 END)
#             ORDER BY a.AdmissionID
#             """ % (date)
#         values = ''
#         data += sync.get_data(sync.servers.get(sync_type), query_admission)
#         query_noadmission = """
#             SELECT
#                 CONVERT(int, substring(a.BillNo, 4, 10)) as sync_id,
#                 a.BillNo AS name,
#                 (CASE 
#                     WHEN MAX(a.PatientID) IS NULL or MAX(a.PatientID) = 0 
#                     THEN 918273 ELSE MAX(a.PatientID) 
#                 END) partner_id,
#                 a.BillDate AS date_order,
#                 max(a.BillNo) AS billno,
#                 max(a.BillDate) AS confirmation_date,
#                 max(a.DischargeReason) AS discharge_reason,
#                 max(a.DischargeDate) AS discharge_date,
#                 max(a.BillableBedTypeID) AS bed_type_id,
#                 max(a.EligibleBedTypeID) AS eligible_bed_type_id,
#                 max(a.AllotedBedTypeID) AS alloted_bed_type_id,
#                 max(a.PrimaryDocID) AS primary_doc_id,
#                 max(a.ReferralDoctorId) AS referral_doc_id,
#                 max(a.ReferralId) AS referral_id,
#                 max(a.ReferralNumber) AS referral_number,
#                 max(a.TariffID) AS tariff_id,
#                 max(a.PayerID) AS payer_id,
#                 max(a.PayerCode) AS payer_code,
#                 max(a.PayerType) AS payer_type,
#                 (CASE a.PatientType 
#                     WHEN 'OutPatient' THEN 1 
#                     WHEN 'InPatient' THEN 2 
#                     WHEN 'Emergency' THEN 3 
#                     WHEN 'Daycare' THEN 4 
#                     WHEN 'FO' THEN 5 
#                     WHEN 'Pharmacy' THEN 6 
#                 END) AS patient_type,
#                 max(a.ProvDiagnosisCode) secondary_diagnosis_code,
#                 max(a.ProvDiagnosisName) secondary_diagnosis_name,
#                 max(a.FinalDiagnosisCode) primary_diagnosis_code,
#                 max(a.FinalDiagnosisName) primary_diagnosis_name,
#                 max(a.RepeatDiagnosisCode) repeat_diagnosis_code,
#                 max(a.RepeatDiagnosisName) repeat_diagnosis_name,
#                 max(a.AdmissionType) admission_type,
#                 'draft' state
#             FROM dbo.V_Db_A_A_RawDataH30 a
#             WHERE a.TglProses = '%s'
#                 AND a.AdmissionID IS NULL
#             GROUP BY
#                 a.BillNo,
#                 a.BillDate,
#                 (CASE a.PatientType 
#                     WHEN 'OutPatient' THEN 1 
#                     WHEN 'InPatient' THEN 2 
#                     WHEN 'Emergency' THEN 3 
#                     WHEN 'Daycare' THEN 4 
#                     WHEN 'FO' THEN 5 
#                     WHEN 'Pharmacy' THEN 6 
#                 END)
#             ORDER BY a.BillNo
#             """ % (date)
#         data += sync.get_data(sync.servers.get(sync_type), query_noadmission)
#         fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and 'ids' not in key and self._fields[key].required == True and self._fields[key].store == True)
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
#         default_values['pricelist_id'] = self.env.ref('product.list0').id
#         now = tools.datetime.now().strftime('%Y%m%d %H:%M:S')
#         default_values['company_id'] = self.env.company.id
#         default_values['currency_id'] = self.env.company.currency_id.id
#         #uom_id = self.env.ref('product.product_uom_categ_unit').id
#         new_sync_ids = []
#         for object in data:
#             new_sync_ids += [object['sync_id']]
#             for value in default_values:
#                 if value in object:
#                     continue
#                 object[value] = default_values[value]

#             partner_id = object['partner_id']
#             object['partner_id'] = self.env['res.partner'].search([('sync_id', '>', 0), ('sync_id', '=', partner_id), ('sync_type', '=', sync_type), ('patient', '=', True)], order="id asc", limit=1)
            
#             if object['payer_type'] == 'PRIVATE':
#                 object['payer_id'] = 5817
#             else:
#                 object['payer_id'] = self.env['res.partner'].search([('sync_id', '>', 0), ('sync_id', '=', object['payer_id']),('sync_type', '=', sync_type), ('insurance', '=', True)], order="id asc", limit=1).id or None

#             if object['primary_doc_id']:
#                 object['primary_doc_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1).id or self.env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1).id or self.env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
#             if object['referral_doc_id']:
#                 object['referral_doc_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['referral_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1).id or None
#             if object['referral_id']:
#                 object['referral_id'] = self.env['referral.transaction'].search([('sync_id', '=', object['referral_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
#             if object['tariff_id']:
#                 object['tariff_id'] = self.env['hospital.tariff'].search([('sync_id', '=', object['tariff_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
#             if object['bed_type_id']:
#                 object['bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['bed_type_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
#             if object['alloted_bed_type_id']:
#                 object['alloted_bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['eligible_bed_type_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
#             if object['eligible_bed_type_id']:
#                 object['eligible_bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['alloted_bed_type_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
                        
#             if not object['partner_id']:
#                 open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + "pasien res.partner with sync_id %s and sync_type %s doesn't exist" % (partner_id, sync_type))
#                 object['backup_partner_id'] = object['partner_id']
#                 object['partner_id'] = self.env['res.partner'].search([('sync_id', '=', 99881177), ('sync_type', '=', sync_type), ('patient', '=', True)], limit=1)
#                 # return
#             object['partner_shipping_id'] = object['partner_id'].id or None
#             object['partner_id'] = object['partner_id'].id or None
#             object['partner_invoice_id'] = object['partner_id']
#             # object['payer_id'] = object['payer_id'].id
#             # object['project_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['project_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'bed')], order="id asc", limit=1).id or None
#             if int(object['sync_id']) in sync_ids:
#                 object['id'] = sync_ids[object['sync_id']]
#             else:
#                 object['id'] = 'DEFAULT'
#             object['sync_date'] = now
#             object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
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
#                 if isinstance(object[field], str):
#                     string = object[field]
#                     value += "'" + string.replace("'", "''") + "'"
#                     continue
#                 value += sync.json(object[field])
#             value += ')'
#             values += value
#         excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
#         columns = sync.remove_unicode(str(fields)).replace("'", "")
#         columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
#         print (values.encode('utf-8'))
#         if not values:
#             print ("No data available")
#             return
#         query = "INSERT into sale_order %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
#         print (query.encode('utf8'))
#         self.env.cr.execute(query)
#         self.env.cr.execute("""UPDATE sale_order as s set date_order = s.date_order - (interval '14 hour'), updated_date = True where s.updated_date is null""")

#     @api.model
#     def _sync_sale_wipro_manual(self,sync_type='1',date_start='2019-01-01', date_end='2019-01-01'):
#         sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)])}
#         sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc',limit=1).sync_date
#         data = []
#         date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
#         # date = '2019-01-25'
#         query_admission = """
#             SELECT
#                 a.AdmissionID AS sync_id,
#                 a.AdmissionNumber AS name,
#                 (CASE 
#                     WHEN a.PatientID IS NULL or PatientID = 0 
#                     THEN 918273 ELSE PatientID 
#                 END) AS partner_id,
#                 a.AdmitDate AS date_order,
#                 max(a.BillNo) AS billno,
#                 max(a.BillDate) AS confirmation_date,
#                 max(a.DischargeReason) AS discharge_reason,
#                 max(a.DischargeDate) AS discharge_date,
#                 max(a.BillableBedTypeID) AS bed_type_id,
#                 max(a.EligibleBedTypeID) AS eligible_bed_type_id,
#                 max(a.AllotedBedTypeID) AS alloted_bed_type_id,
#                 max(a.PrimaryDocID) AS primary_doc_id,
#                 max(a.ReferralDoctorId) AS referral_doc_id,
#                 max(a.ReferralId) AS referral_id,
#                 max(a.ReferralNumber) AS referral_number,
#                 max(a.TariffID) AS tariff_id,
#                 max(a.PayerID) AS payer_id,
#                 max(a.PayerCode) AS payer_code,
#                 max(a.PayerType) AS payer_type,
#                 (CASE a.PatientType
#                     WHEN 'OutPatient' THEN 1
#                     WHEN 'InPatient' THEN 2
#                     WHEN 'Emergency' THEN 3
#                     WHEN 'Daycare' THEN 4
#                     WHEN 'FO' THEN 5
#                     WHEN 'Pharmacy' THEN 6
#                 END) AS patient_type,
#                 max(a.ProvDiagnosisCode) secondary_diagnosis_code,
#                 max(a.ProvDiagnosisName) secondary_diagnosis_name,
#                 max(a.FinalDiagnosisCode) primary_diagnosis_code,
#                 max(a.FinalDiagnosisName) primary_diagnosis_name,
#                 max(a.RepeatDiagnosisCode) repeat_diagnosis_code,
#                 max(a.RepeatDiagnosisName) repeat_diagnosis_name,
#                 max(a.AdmissionType) admission_type,
#                 'draft' AS state
#             FROM dbo.V_Db_A_A_RawDataH30 a
#             WHERE a.TglProses >= '%s' and a.TglProses <= '%s'
#                 AND a.AdmissionID IS NOT NULL
#             GROUP BY
#                 a.AdmissionNumber,
#                 a.PatientID,
#                 a.AdmitDate,
#                 a.AdmissionID,
#                 (CASE a.PatientType
#                     WHEN 'OutPatient' THEN 1
#                     WHEN 'InPatient' THEN 2
#                     WHEN 'Emergency' THEN 3
#                     WHEN 'Daycare' THEN 4
#                     WHEN 'FO' THEN 5
#                     WHEN 'Pharmacy' THEN 6
#                 END)
#             ORDER BY a.AdmissionID
#             """ % (date_start, date_end)
#         values = ''
#         data += sync.get_data(sync.servers.get(sync_type), query_admission)
#         query_noadmission = """
#             SELECT
#                 CONVERT(int, substring(a.BillNo, 4, 10)) as sync_id,
#                 a.BillNo AS name,
#                 (CASE 
#                     WHEN MAX(a.PatientID) IS NULL or MAX(a.PatientID) = 0 
#                     THEN 918273 ELSE MAX(a.PatientID) 
#                 END) partner_id,
#                 a.BillDate AS date_order,
#                 max(a.BillNo) AS billno,
#                 max(a.BillDate) AS confirmation_date,
#                 max(a.DischargeReason) AS discharge_reason,
#                 max(a.DischargeDate) AS discharge_date,
#                 max(a.BillableBedTypeID) AS bed_type_id,
#                 max(a.EligibleBedTypeID) AS eligible_bed_type_id,
#                 max(a.AllotedBedTypeID) AS alloted_bed_type_id,
#                 max(a.PrimaryDocID) AS primary_doc_id,
#                 max(a.ReferralDoctorId) AS referral_doc_id,
#                 max(a.ReferralId) AS referral_id,
#                 max(a.ReferralNumber) AS referral_number,
#                 max(a.TariffID) AS tariff_id,
#                 max(a.PayerID) AS payer_id,
#                 max(a.PayerCode) AS payer_code,
#                 max(a.PayerType) AS payer_type,
#                 (CASE a.PatientType 
#                     WHEN 'OutPatient' THEN 1 
#                     WHEN 'InPatient' THEN 2 
#                     WHEN 'Emergency' THEN 3 
#                     WHEN 'Daycare' THEN 4 
#                     WHEN 'FO' THEN 5 
#                     WHEN 'Pharmacy' THEN 6 
#                 END) AS patient_type,
#                 max(a.ProvDiagnosisCode) secondary_diagnosis_code,
#                 max(a.ProvDiagnosisName) secondary_diagnosis_name,
#                 max(a.FinalDiagnosisCode) primary_diagnosis_code,
#                 max(a.FinalDiagnosisName) primary_diagnosis_name,
#                 max(a.RepeatDiagnosisCode) repeat_diagnosis_code,
#                 max(a.RepeatDiagnosisName) repeat_diagnosis_name,
#                 max(a.AdmissionType) admission_type,
#                 'draft' state
#             FROM dbo.V_Db_A_A_RawDataH30 a
#             WHERE a.TglProses >= '%s' and a.TglProses <= '%s'
#                 AND a.AdmissionID IS NULL
#             GROUP BY
#                 a.BillNo,
#                 a.BillDate,
#                 (CASE a.PatientType 
#                     WHEN 'OutPatient' THEN 1 
#                     WHEN 'InPatient' THEN 2 
#                     WHEN 'Emergency' THEN 3 
#                     WHEN 'Daycare' THEN 4 
#                     WHEN 'FO' THEN 5 
#                     WHEN 'Pharmacy' THEN 6 
#                 END)
#             ORDER BY a.BillNo
#             """ % (date_start, date_end)
#         data += sync.get_data(sync.servers.get(sync_type), query_noadmission)
#         fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and 'ids' not in key and self._fields[key].required == True and self._fields[key].store == True)
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
#         default_values['pricelist_id'] = self.env.ref('product.list0').id
#         now = tools.datetime.now().strftime('%Y%m%d %H:%M:S')
#         default_values['company_id'] = self.env.company.id
#         default_values['currency_id'] = self.env.company.currency_id.id
#         # uom_id = self.env.ref('product.product_uom_categ_unit').id
#         new_sync_ids = []
#         for object in data:
#             new_sync_ids += [object['sync_id']]
#             for value in default_values:
#                 if value in object:
#                     continue
#                 object[value] = default_values[value]
            
#             if object['payer_type'] == 'PRIVATE':
#                 object['payer_id'] = 5817
#             else:
#                 object['payer_id'] = self.env['res.partner'].search([('sync_id', '>', 0), ('sync_id', '=', object['payer_id']),('sync_type', '=', sync_type), ('insurance', '=', True)], order="id asc", limit=1).id or None

#             if object['primary_doc_id']:
#                 object['primary_doc_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1).id or self.env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1).id or self.env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
#             if object['referral_doc_id']:
#                 object['referral_doc_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['referral_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1).id or None
#             if object['referral_id']:
#                 object['referral_id'] = self.env['referral.transaction'].search([('sync_id', '=', object['referral_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
#             if object['tariff_id']:
#                 object['tariff_id'] = self.env['hospital.tariff'].search([('sync_id', '=', object['tariff_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
#             if object['bed_type_id']:
#                 object['bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['bed_type_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
#             if object['alloted_bed_type_id']:
#                 object['alloted_bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['eligible_bed_type_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
#             if object['eligible_bed_type_id']:
#                 object['eligible_bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['alloted_bed_type_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
            
#             partner_id = object['partner_id']
#             object['partner_id'] = self.env['res.partner'].search([('sync_id', '>', 0), ('sync_id', '=', partner_id), ('sync_type', '=', sync_type), ('patient', '=', True)], order="id asc", limit=1)
#             if not object['partner_id']:
#                 open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + " res.partner with sync_id %s and sync_type %s doesn't exist" % (partner_id, sync_type))
#                 object['backup_partner_id'] = object['partner_id']
#                 object['partner_id'] = self.env['res.partner'].search([('sync_id', '=', 99881177), ('sync_type', '=', sync_type), ('patient', '=', True)], order="id asc", limit=1)
#                 #return
#             object['partner_shipping_id'] = object['partner_id'].id or None 
#             object['partner_id'] = object['partner_id'].id or None
#             object['partner_invoice_id'] = object['partner_id']
#             # object['payer_id'] = object['payer_id'].id
#             # object['project_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['project_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'bed')], order="id asc", limit=1).id or None
#             if int(object['sync_id']) in sync_ids:
#                 object['id'] = sync_ids[object['sync_id']]
#             else:
#                 object['id'] = 'DEFAULT'
#             object['sync_date'] = now
#             object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
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
#                 if isinstance(object[field], str):
#                     string = object[field]
#                     value += "'" + string.replace("'", "''") + "'"
#                     continue
#                 value += sync.json(object[field])
#             value += ')'
#             values += value
#         excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
#         columns = sync.remove_unicode(str(fields)).replace("'", "")
#         columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
#         print (values.encode('utf-8'))
#         if not values:
#             print ("No data available")
#             return
#         query = "INSERT into sale_order %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
#         print (query.encode('utf8'))
#         self.env.cr.execute(query)
#         # self.env.cr.execute("""UPDATE sale_order as s set date_order = s.date_order - (interval '14 hour'), updated_date = True where s.updated_date is null""")

#     # @api.multi
#     def tarik_data_wipro_ip(self, sync_type='1'):
#         self = self.search([('id', 'in', self.ids), ('sync_type', '=', sync_type)])
#         self.env['sale.order.line'].sudo()._sync_sale_line_wipro_ip(sync_type=sync_type, admission_ids=self.mapped('sync_id'))

#     # @api.multi
#     def tarik_data_wipro_op_emerg(self, sync_type='1'):
#         self = self.search([('id', 'in', self.ids),('sync_type', '=', sync_type)])
#         self.env['sale.order.line'].sudo()._sync_sale_line_wipro_op_emerg(sync_type=sync_type, admission_ids=self.mapped('sync_id'))

#     # @api.multi
#     def tarik_data_wipro_noadmission(self, sync_type='1'):
#         self = self.search([('id', 'in', self.ids), ('sync_type', '=', sync_type)])
#         self.env['sale.order.line'].sudo()._sync_sale_line_wipro_noadmission(sync_type=sync_type, admission_ids=self.mapped('sync_id'))

#     # @api.multi
#     # def sync_discount(self):
#     #     for r in self:
#     #         r.sync_deduction = True

#     # @api.multi
#     def action_cancel(self):
#         # self.mapped('picking_ids').action_cancel()
#         # self.mapped('order_line').write({'move_created': False})
#         return super(SaleOrder, self).action_cancel()

#     @api.model
#     def _sync_sale_wipro_freeze(self, sync_type='1'):
#         sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)])}
#         sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
#         data = []
#         date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
#         # date = '2019-01-25'
#         query = """
#             SELECT
#                 a.TglProses,
#                 a.AdmissionID 'sync_id',
#                 a.AdmissionNumber 'name',
#                 a.AdmitDate 'date_order',
#                 a.PatientType 'patient_type',
#                 a.BillID,
#                 a.BillNo 'origin',
#                 a.BillNo 'billno',
#                 a.billDate 'confirmation_date',
#                 isnull(a.DischargeDate, a.BillDate) 'discharge_date',
#                 (case when isnull(a.PatientID,0)=0 then 918273 else a.PatientID end) 'partner_id',
#                 a.RegCode,
#                 a.PatientName,
#                 a.BillAmount 'amount_total',
#                 a.BillAmount 'amount_untaxed',
#                 a.BillAmount 'total_amount',
#                 a.PayerAmount 'payer_amount',
#                 a.PatientAmount 'personal_amount',
#                 a.PayerID 'payer_id',
#                 a.PayerCode 'payer_code',
#                 a.PayerType 'payer_type',
#                 a.PayerName 'payer',
#                 'done' state,
#                 'to invoice' invoice_status,
#                 'FREEZE BILL WIPRO ON ' + convert(varchar(10),a.TglProses,121)  note,
#                 'BILL' status_bill
#             FROM dbo.VRP_OdooFreezeBills a
#             -- WHERE a.TglProses >= '2019-09-01'
#             WHERE a.TglProses = '%s'
#             """ % (date)
#         values = ''
#         print (query)
#         data += sync.get_data(sync.servers.get(sync_type), query)
#         fields_without_id = tuple(
#             key for key in self._fields
#             if key != 'id' and 'property' not in key and 'ids' not in key
#             and self._fields[key].required == True
#             and self._fields[key].store == True)
#         columns = tuple(
#             key for key in data[0].keys()
#             if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
#         fields_without_id += columns
#         columns += tuple(
#             key for key in data[0].keys()
#             if key in self._fields and key not in columns) if data else ()
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
#         default_values['pricelist_id'] = self.env.ref('product.list0').id
#         now = tools.datetime.now().strftime('%Y%m%d %H:%M:S')
#         default_values['company_id'] = self.env.company.id
#         default_values['currency_id'] = self.env.company.currency_id.id
#         #uom_id = self.env.ref('product.product_uom_categ_unit').id
#         new_sync_ids = []
#         for object in data:
#             new_sync_ids += [object['sync_id']]
#             for value in default_values:
#                 if value in object:
#                     continue
#                 object[value] = default_values[value]
#             object['payer_id'] = self.env['res.partner'].search([('sync_id', '=', object['payer_id']), ('sync_type', '=', sync_type), ('insurance', '=', True)], limit=1).id or None
#             partner_id = object['partner_id']
#             object['partner_id'] = self.env['res.partner'].search([('sync_id', '=', object['partner_id']), ('sync_type', '=', sync_type), ('patient', '=', True)], limit=1)
#             if not object['partner_id']:
#                 open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + " res.partner with sync_id %s and sync_type %s doesn't exist" % (partner_id, sync_type))
#                 return
#             object['partner_shipping_id'] = object['partner_id'].id
#             object['partner_id'] = object['partner_id'].id
#             object['partner_invoice_id'] = object['partner_id']
#             # object['payer_id'] = object['payer_id'].id
#             # object['project_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['project_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'bed')], order="id asc", limit=1).id or None
#             if int(object['sync_id']) in sync_ids:
#                 object['id'] = sync_ids[object['sync_id']]
#             else:
#                 object['id'] = 'DEFAULT'
#             object['sync_date'] = now
#             object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
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
#                 if isinstance(object[field], str):
#                     string = object[field]
#                     value += "'" + string.replace("'", "''") + "'"
#                     continue
#                 value += sync.json(object[field])
#             value += ')'
#             values += value
#         excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
#         columns = sync.remove_unicode(str(fields)).replace("'", "")
#         columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
#         print (values.encode('utf-8'))
#         if not values:
#             print ("No data available")
#             return
#         query = "INSERT into sale_order %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
#         print (query.encode('utf8'))
#         self.env.cr.execute(query)
#         # self.env.cr.execute("""UPDATE sale_order as s set date_order = s.date_order - (interval '14 hour'), updated_date = True where s.updated_date is null""")






class SaleOrderLineDhealthWizard(models.TransientModel):
    _name = 'sale.order.line.dhealth.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(SaleOrderLineDhealthWizard,self).get_view(view_id=view_id,view_type=view_type, **options)
        res['arch'] = """
                <form string="Syncronize Daily Revenue Dhealth to Odoo">
                    <sheet>
                        <group>
                            <field name="company_id" />
                            <field name="start_date" />
                            <field name="end_date" />
                        </group>
                    </sheet>
                    <footer>
                        <button name="generate" string="Sync Sale Order Line Dhealth" type="object" class="oe_highlight"/>
                    </footer>
                </form>
        """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res






    # @api.multi
    def generate(self,start_date=start_date,end_date=end_date):
        for record in self:
            start_date = record.start_date
            end_date = record.end_date
            company_id = record.company_id.id
            sync_type = record.company_id.sync_type
            line_dhealth = record.env['sale.order.line.dhealth']
            # already = payout.search([('reference_no', '=', self.reference_no)])
            # # raise exceptions.ValidationError(sync_type)
            # if already:
            #     raise exceptions.ValidationError('Billing periode tersebut masih ada di worklist payout interface!')
            # else:
            if sync_type =='8':
                line_dhealth._sync_sale_order_line_dhealth_mhbd(company_id=company_id,sync_type=sync_type,start_date=start_date,end_date=end_date)






class SaleOrderLineDhealth(models.Model):
    _name = 'sale.order.line.dhealth'
    # _sql_constraints = [('sync_id_api_unique', 'unique(sync_type, sync_id_api)', 'Can not be duplicate value for sync_id_api')]

    company_id = fields.Many2one(string='Company', store=True,  readonly=True, index=True)
    sync_type = sync.type
    cutoff_date = fields.Date(string="Cutoff Date", store=True, readonly=True, index=True)
    tglproses = fields.Date(string="TglProses", store=True, index=True, readonly=True)
    sync_id_api = sync.id_api
    product_id = fields.Char(string="Product ID", store=True, index=True, readonly=True)
    name = fields.Char(string="Product Name", store=True, index=True, readonly=True)
    product_uom = fields.Char(string="Product ID", store=True, index=True, readonly=True)
    product_uom_qty = fields.Float(string="Product Qty")
    price_unit = fields.Float(string="Price Unit")
    price_subtotal = fields.Float(string="Price Subtotal")
    price_total = fields.Float(string="Price Total")
    personal_amount = fields.Float(string="Personal Amount")
    payer_amount = fields.Float(string="Payer Amount")
    order_id = fields.Char(string="Order ID", store=True, index=True, readonly=True)
    service_categ_id = fields.Char(string="Service Categ ID", store=True, index=True, readonly=True)
    primary_doc_id = fields.Char(string="Primary Doc ID", store=True, index=True, readonly=True)
    prescribe_doc_id = fields.Char(string="Prescribe Doc ID", store=True, index=True, readonly=True)
    perform_doc_id = fields.Char(string="Perform Doc ID", store=True, index=True, readonly=True)
    location_id = fields.Char(string="Location ID", store=True, index=True, readonly=True)
    department_id = fields.Char(string="Department", store=True, index=True, readonly=True)
    billno = fields.Char(string="Bill No", store=True, index=True, readonly=True)
    bill_date = fields.Date(string="Bill Date", store=True, index=True, readonly=True)
    type_line = fields.Char(string="Type Line", store=True, index=True, readonly=True)
    revenue_type = fields.Char(string="Revenue Type", store=True, index=True, readonly=True)
    item_specialisation = fields.Char(string="Item Specialisation", store=True, index=True, readonly=True)
    patient_group = fields.Char(string="Patient Group", store=True, index=True, readonly=True)
    special_group = fields.Char(string="Special Group", store=True, index=True, readonly=True)
    special_group2 = fields.Char(string="Special Group2", store=True, index=True, readonly=True)
    service_group = fields.Char(string="Service Group", store=True, index=True, readonly=True)
    bed_type = fields.Char(string="Bed Type", store=True, index=True, readonly=True)
    payer = fields.Char(string="Payer", store=True, index=True, readonly=True)
    payer_code = fields.Char(string="Payer", store=True, index=True, readonly=True)
    payer_type = fields.Char(string="Payer Type", store=True, index=True, readonly=True)
    payer_name = fields.Char(string="Payer Name", store=True, index=True, readonly=True)
    order_no = fields.Char(string="Order No", store=True, index=True, readonly=True)
    order_item = fields.Char(string="Order Item", store=True, index=True, readonly=True)
    order_date = fields.Date(string="Order Date", store=True, index=True, readonly=True)
    is_package = fields.Boolean(string="Is Package", readonly=True)
    package_id = fields.Char(string="Package ID", store=True, index=True, readonly=True)
    package_name = fields.Char(string="Package Name", store=True, index=True, readonly=True)
    package_order_no = fields.Char(string="Package Order No", store=True, index=True, readonly=True)
    cost_unit = fields.Float(string="Cost Unit")
    cost_total = fields.Float(string="Cost Total")
    account_analytic_id = fields.Char(string="Account Analytic ID", store=True, index=True, readonly=True)
    backup_analytic_id2 = fields.Char(string="Backup Analytic2 ID", store=True, index=True, readonly=True)
    backup_analytic_id = fields.Char(string="Backup Analytic ID", store=True, index=True, readonly=True)
    kota = fields.Char(string="kota", store=True, index=True, readonly=True)
    kecamatan = fields.Char(string="Kecamatan", store=True, index=True, readonly=True)
    kelurahan = fields.Char(string="Kelurahan", store=True, index=True, readonly=True)
    partner_id = fields.Char(string="Partner ID", store=True, index=True, readonly=True)
    registration_code = fields.Char(string="Registration Code", store=True, index=True, readonly=True)
    number_admission = fields.Char(string="Number Admission", store=True, index=True, readonly=True)
    manufacture = fields.Char(string="Manufacture", store=True, index=True, readonly=True)
    discharge_date = fields.Date(string="Discharge Date", store=True, index=True, readonly=True)
    specialization_primary = fields.Char(string="Specialization Primary", store=True, index=True, readonly=True)
    jenis = fields.Char(string="Jenis", store=True, index=True, readonly=True)
    status_bill = fields.Char(string="Status Bill", store=True, index=True, readonly=True)
    state = fields.Char(string="Draft", store=True, index=True, readonly=True)
    additional_paket = fields.Char(string="Additional Paket", store=True, index=True, readonly=True)
    nama_pasien = fields.Char(string="Nama Pasien", store=True, index=True, readonly=True)
    admit_date = fields.Date(string="Admit Date", store=True, index=True, readonly=True)
    billing_id = fields.Char(string="Billing ID", store=True, index=True, readonly=True)
    subpayer_amount = fields.Float(string="Subpayer Amount")
    cob_id = fields.Char(string="COB ID", store=True, index=True, readonly=True)
    sub_cob_id = fields.Char(string="Sub COB ID", store=True, index=True, readonly=True)
    sub_payer = fields.Char(string="Sub Payer", store=True, index=True, readonly=True)
    sub_payer_code = fields.Char(string="Sub Payer Code", store=True, index=True, readonly=True)
    sub_payer_type = fields.Char(string="Sub Payer Type", store=True, index=True, readonly=True)
    discharge_reason = fields.Char(string="Discharge Reason", store=True, index=True, readonly=True)
    admission_type = fields.Char(string="Admission Type", store=True, index=True, readonly=True)
    ref_admission_no = fields.Char(string="Ref Admission No", store=True, index=True, readonly=True)
    referral_number = fields.Char(string="Ref No", store=True, index=True, readonly=True)
    product_categ_id = fields.Char(string="Product Categ ID", store=True, index=True, readonly=True)
    cyto = fields.Boolean(string="Cyto", readonly=True)
    penyulit = fields.Boolean(string="Penyulit", readonly=True)
    room_id = fields.Char(string="Room ID", store=True, index=True, readonly=True)
    bed_type_id = fields.Char(string="Bed Type ID", store=True, index=True, readonly=True)
    eligible_bed_type_id = fields.Char(string="Eligible Bed Type ID", store=True, index=True, readonly=True)
    alloted_bed_type_id = fields.Char(string="Alloted Bed Type ID", store=True, index=True, readonly=True)
    bed_id = fields.Char(string="Bed ID", store=True, index=True, readonly=True)
    bed_allocation_start = fields.Date(string="Bed Allocation Start", store=True, index=True, readonly=True)
    bed_allocation_end = fields.Date(string="Bed Allocation End", store=True, index=True, readonly=True)
    referral_doc_id = fields.Char(string="Referral Doc ID", store=True, index=True, readonly=True)
    surgery_operator_id = fields.Char(string="Surgery Operator ID", store=True, index=True, readonly=True)
    surgery_operator_ass_id = fields.Char(string="Surgery Operator Ass ID", store=True, index=True, readonly=True)
    anesthetist_operator_id = fields.Char(string="Anesthetist Operator ID", store=True, index=True, readonly=True)
    anesthetist_operator_ass_id = fields.Char(string="Anesthetist Operator Ass ID", store=True, index=True, readonly=True)
    surgery_team_id = fields.Char(string="Surgery Team ID", store=True, index=True, readonly=True)
    surgery_team_ass_id = fields.Char(string="Surgery Team Ass ID", store=True, index=True, readonly=True)
    secondary_diagnosis_code = fields.Char(string="Secondary Diagnosis Code", store=True, index=True, readonly=True)
    secondary_diagnosis_name = fields.Char(string="Secondary Diagnosis Name", store=True, index=True, readonly=True)
    repeat_diagnosis_name = fields.Char(string="Repeat Diagnosis Name", store=True, index=True, readonly=True)
    discount_name = fields.Char(string="Discount Name", store=True, index=True, readonly=True)
    discount_id = fields.Char(string="Discount ID", store=True, index=True, readonly=True)
    discount_date = fields.Date(string="Discount Date", store=True, index=True, readonly=True)
    discount_level = fields.Char(string="Discount Level", store=True, index=True, readonly=True)
    discount_reason = fields.Char(string="Discount Reason", store=True, index=True, readonly=True)
    is_baby = fields.Boolean(string="Is Child/Baby", default=False, readonly=True)
    parent_admission_no = fields.Char(string="Parent Admission Name", store=True, index=True, readonly=True)
    sales_id = fields.Char(string="Sales ID", store=True, index=True, readonly=True)
    sales_date = fields.Date(string="Sales Date", store=True, index=True, readonly=True)
    sales_return_id = fields.Char(string="Sales Return ID", store=True, index=True, readonly=True)
    sales_return_date = fields.Date(string="Sales Return Date", store=True, index=True, readonly=True)
    hna_unit = fields.Float(string="HNA Unit")
    hna_total = fields.Float(string="HNA Total")
    base_price_unit = fields.Float(string="Base Price Unit")
    base_price_total = fields.Float(string="Base Price Total")
    order_type = fields.Char(string="Order Type", store=True, index=True, readonly=True)
    batch_id = fields.Char(string="Batch ID", store=True, index=True, readonly=True)
    batch_rel = fields.Char(string="Batch Rel", store=True, index=True, readonly=True)
    batch_expired = fields.Date(string="Batch Expired", store=True, index=True, readonly=True)
    user_id = fields.Many2one('res.users', string='Responsible', store=True)


    # @api.multi
    def _sync_sale_order_line_dhealth_mhbd(self, company_id, sync_type, start_date, end_date):
        from psycopg2 import extensions, connect
        from datetime import datetime, timedelta, date as date_format
        import psycopg2.extras
        import pytz

        # company = self.company_id
        # sync_type = self.company_id.sync_type
        # date_start = tools.datetime.strptime(self.date_start, '%Y-%m-%d')
        # date_end = tools.datetime.strptime(self.date_end, '%Y-%m-%d')
        user_id = self.env.user.id
        db_host = self.env.company.his_slave_host
        db_login = self.env.company.his_slave_login
        db_pass = self.env.company.his_slave_pass
        db_name = 'db_jurnal'
        db_port = self.env.company.his_slave_port
        conn = connect(dbname=db_name, user=db_login, host=db_host, password=db_pass, port=db_port)

        local = pytz.timezone('Asia/Jakarta')
        log_file = "/opt/odoo16/logs/doctor_payout.log"
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        open(log_file, 'a').write("\n\n"+log_time+" Start process ---")


        query = """
            DELETE FROM sale_order_line_dhealth
            WHERE company_id = {company_id}
                AND user_id = {user_id}
        """.format(
            company_id=company_id,
            user_id=user_id
        )
        open('/opt/odoo16/logs/doctor_payout.log', 'a+').write('\n' + str(tools.datetime.now()) + ' Query \n' + str(query))
        self.env.cr.execute(query)

        query = """
            SELECT 
                '{company_id}' company_id,
                sync_type,
                cutoff_date,
                tglproses,
                sync_id_api,
                product_id,
                name,
                product_uom,
                product_uom_qty,
                price_unit,
                price_subtotal,
                price_total,
                personal_amount,
                payer_amount,
                order_id,
                service_categ_id,
                primary_doc_id,
                prescribe_doc_id,
                perform_doc_id,
                location_id,
                department_id,
                billno,
                bill_date,
                type_line,
                revenue_type,
                item_specialisation,
                patient_group,
                special_group,
                special_group2,
                service_group,
                bed_type,
                payer,
                payer_code,
                payer_type,
                payer_name,
                order_no,
                order_item_no as order_item,
                order_date,
                is_package,
                package_id,
                package_name,
                package_order_no,
                cost_unit,
                cost_total,
                account_analytic_id,
                null as backup_analytic_id2,
                backup_analytic_id,
                kota,
                kecamatan,
                kelurahan,
                partner_id,
                registration_code,
                number_admission,
                manufacture,
                discharge_date,
                specialization_primary,
                null as jenis,
                status_bill,
                state,
                null as additional_paket,
                nama_pasien,
                admit_date,
                billing_id,
                subpayer_amount,
                cob_id,
                sub_cob_id,
                sub_payer,
                sub_payer_code,
                sub_payer_type,
                discharge_reason,
                admission_type,
                ref_admission_no,
                referral_number,
                product_categ_id,
                cyto,
                penyulit,
                room_id,
                bed_type_id,
                eligible_bed_type_id,
                alloted_bed_type_id,
                bed_id,
                bed_allocation_start,
                bed_allocation_end,
                referral_doc_id,
                surgery_operator_id,
                surgery_operator_ass_id,
                anesthetist_operator_id,
                anesthetist_operator_ass_id,
                surgery_team_id,
                surgery_team_ass_id,
                secondary_diagnosis_code,
                secondary_diagnosis_name,
                repeat_diagnosis_code as repeat_diagnosis_name,
                discount_name,
                discount_id,
                discount_date,
                discount_level,
                discount_reason,
                is_baby,
                parent_admission_no,
                sales_id,
                sales_date,
                sales_return_id,
                sales_return_date,
                hna_unit,
                hna_total,
                base_price_unit,
                base_price_total,
                order_type,
                batch_id,
                batch_rel,
                batch_expired,
                {user_id} user_id
                from 
                saleorderline_obat
                where tglproses >='{start_date} 00:00:00' and tglproses <='{end_date} 23:59:59';
            """.format( 
                start_date=start_date, 
                end_date=end_date,
                user_id=user_id,
                company_id=company_id 
                )
        # raise exceptions.ValidationError(query)
        print(query)
        open('/opt/odoo16/logs/doctor_payout.log', 'a+').write('\n' + str(tools.datetime.now()) + ' Query \n' + str(query))


        open(log_file, 'a').write("\n\n"+str(query))
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(query)
        result = cursor.fetchall() 
        open('/opt/odoo16/logs/doctor_payout.log', 'a+').write("\n\n"+str(result))

        sudo = self.env.user.sudo()
        # open(log_file, 'a').write("\n Start looping update cost average per item ")
        if result:
            fields_without_id = tuple(key for key in result[0] if key not in['id','sync_type'])
            fields = tuple(key for key in result[0] if key)
            values = ''
            #print (fields)

            for row in result:
                if values:
                    values += ', '

                value = ''
                for key in fields:
                    if value:
                        value += ', '
                    else:
                        value = '('
                
                    #if type(row[key]) in [str, bytes]:
                    if type(row[key]) in [str, bytes, unicode]:
                        string = row[key]
                        value += "'" + string.replace("'", "''") + "'"
                        continue
                    if isinstance(row[key], datetime):
                        value += "'" + row[key].isoformat() + "'"
                        continue 
                    if isinstance(row[key], date_format):
                        value += "'" + row[key].isoformat() + "'"
                        continue
                    if isinstance(row[key], decimal.Decimal):
                        value += "'" + str(row[key]) + "'"
                        continue
                    value += sync.json(row[key])
                value += ')'
                values += value
            
            excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
            columns = remove_unicode(str(fields)).replace("'", "")
            columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

            # print (values)
            open('/opt/odoo16/logs/doctor_payout.log', 'a+').write('\n' + str(tools.datetime.now()) + ' Print \n')
            if not values:
                print ("No data available")

            # insert replace existing data 
            # query = """
            #     INSERT INTO stock_ledger %s VALUES %s 
            #     ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
            # """ % (columns, values, columns_without_id, excluded)

            query = """
                INSERT INTO sale_order_line_dhealth %s VALUES %s 
            """ % (columns, values)
            print (query)
            self.env.cr.execute(query)
            open('/opt/odoo16/logs/doctor_payout.log', 'a+').write('\n' + str(tools.datetime.now()) + ' insert into wipro_payout_line \n')
        

        query = """
            SELECT 
                '{company_id}' company_id,
                sync_type,
                cutoff_date,
                tglproses,
                sync_id_api,
                product_id,
                name,
                product_uom,
                product_uom_qty,
                price_unit,
                price_subtotal,
                price_total,
                personal_amount,
                payer_amount,
                order_id,
                service_categ_id,
                primary_doc_id,
                prescribe_doc_id,
                perform_doc_id,
                location_id,
                department_id,
                billno,
                bill_date,
                type_line,
                revenue_type,
                item_specialisation,
                patient_group,
                special_group,
                special_group2,
                service_group,
                bed_type,
                payer,
                payer_code,
                payer_type,
                payer_name,
                order_no,
                order_item_no as order_item,
                order_date,
                is_package,
                package_id,
                package_name,
                package_order_no,
                cost_unit,
                cost_total,
                account_analytic_id,
                backup_analytic_id2,
                backup_analytic_id,
                kota,
                kecamatan,
                kelurahan,
                partner_id,
                registration_code,
                number_admission,
                manufacture,
                discharge_date,
                specialization_primary,
                jenis,
                status_bill,
                state,
                additional_paket,
                nama_pasien,
                admit_date,
                billing_id,
                subpayer_amount,
                cob_id,
                sub_cob_id,
                sub_payer,
                sub_payer_code,
                sub_payer_type,
                discharge_reason,
                admission_type,
                ref_admission_no,
                referral_number,
                product_categ_id,
                cyto,
                penyulit,
                room_id,
                bed_type_id,
                eligible_bed_type_id,
                alloted_bed_type_id,
                bed_id,
                bed_allocation_start,
                bed_allocation_end,
                referral_doc_id,
                surgery_operator_id,
                surgery_operator_ass_id,
                anesthetist_operator_id,
                anesthetist_operator_ass_id,
                surgery_team_id,
                surgery_team_ass_id,
                secondary_diagnosis_code,
                secondary_diagnosis_name,
                repeat_diagnosis_code as repeat_diagnosis_name,
                discount_name,
                discount_id,
                discount_date,
                discount_level,
                discount_reason,
                is_baby,
                parent_admission_no,
                sales_id,
                sales_date,
                sales_return_id,
                sales_return_date,
                hna_unit,
                hna_total,
                base_price_unit,
                base_price_total,
                order_type,
                batch_id,
                batch_rel,
                batch_expired,
                {user_id} user_id
                from 
                saleorderline_tindakan
                where tglproses >='{start_date} 00:00:00' and tglproses <='{end_date} 23:59:59';
            """.format( 
                start_date=start_date, 
                end_date=end_date,
                user_id=user_id,
                company_id=company_id 
                )
        # raise exceptions.ValidationError(query)
        print(query)
        open('/opt/odoo16/logs/doctor_payout.log', 'a+').write('\n' + str(tools.datetime.now()) + ' Query \n' + str(query))


        open(log_file, 'a').write("\n\n"+str(query))
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(query)
        result = cursor.fetchall() 
        open('/opt/odoo16/logs/doctor_payout.log', 'a+').write("\n\n"+str(result))

        sudo = self.env.user.sudo()
        # open(log_file, 'a').write("\n Start looping update cost average per item ")
        if result:
            fields_without_id = tuple(key for key in result[0] if key not in['id','sync_type'])
            fields = tuple(key for key in result[0] if key)
            values = ''
            #print (fields)

            for row in result:
                if values:
                    values += ', '

                value = ''
                for key in fields:
                    if value:
                        value += ', '
                    else:
                        value = '('
                
                    #if type(row[key]) in [str, bytes]:
                    if type(row[key]) in [str, bytes, unicode]:
                        string = row[key]
                        value += "'" + string.replace("'", "''") + "'"
                        continue
                    if isinstance(row[key], datetime):
                        value += "'" + row[key].isoformat() + "'"
                        continue 
                    if isinstance(row[key], date_format):
                        value += "'" + row[key].isoformat() + "'"
                        continue
                    if isinstance(row[key], decimal.Decimal):
                        value += "'" + str(row[key]) + "'"
                        continue
                    value += sync.json(row[key])
                value += ')'
                values += value
            
            excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
            columns = remove_unicode(str(fields)).replace("'", "")
            columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

            # print (values)
            open('/opt/odoo16/logs/doctor_payout.log', 'a+').write('\n' + str(tools.datetime.now()) + ' Print \n')
            if not values:
                print ("No data available")

            # insert replace existing data 
            # query = """
            #     INSERT INTO stock_ledger %s VALUES %s 
            #     ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
            # """ % (columns, values, columns_without_id, excluded)

            query = """
                INSERT INTO sale_order_line_dhealth %s VALUES %s 
            """ % (columns, values)
            print (query)
            self.env.cr.execute(query)
            open('/opt/odoo16/logs/doctor_payout.log', 'a+').write('\n' + str(tools.datetime.now()) + ' insert into wipro_payout_line \n')



    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(SaleOrderLineDhealth, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        if view_type == 'tree':
            res['arch'] = """
            <tree string="Dhealth Line" create="False">
                <field name="tglproses"/>
                <field name="number_admission"/>
                <field name="nama_pasien"/>
                <field name="payer_name"/>
                <field name="service_categ_id"/>
                <field name="product_id"/>
                <field name="name"/>
                <field name="product_uom_qty" string="Qty"/>
                <field name="product_uom" string="UoM"/>
                <field name="price_unit" string="Price Unit"/>
                <field name="price_subtotal" sum="Subtotal" widget="monetary" string="Subtotal" modifiers="{'readonly': true}"/>
                <field name="price_total" sum="Total" widget="monetary" string="Total" modifiers="{'readonly': true}"/>
                <field name="account_analytic_id" />
                <field name="user_id"/>
            </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(self._name, doc, view_id)
        return res




class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    # _sql_constraints = [('sync_id_api_unique', 'unique(sync_type, sync_id_api)', 'Can not be duplicate value for sync_id_api')]
    #JANGAN LUPA EDIT /web/static/src/js/views$ sudo nano pivot_view.js untuk ilangin pivot yang gapenting

    sync_id = sync.id_big
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    tglproses = fields.Date(string="TglProses", store=True, index=True)
    company_id = fields.Many2one("res.company", string='Company', store=True, readonly=True, index=True)
    billno = fields.Char(string="Bill No", store=True, index=True)
    bill_date = fields.Date(string="Bill Date", index=True)
    merged_id = fields.Many2one('sale.order.bill', string='Billing Merge No.', required=False, index=True, copy=False)
    billing_id = fields.Many2one('sale.order.bill', string='Billing No.', required=False, index=True, copy=False)
    cob_id = fields.Many2one('sale.order.cob', string='Main COB No.', required=False, index=True, copy=False)
    sub_cob_id = fields.Many2one('sale.order.cob', string='Sub COB No.', required=False, index=True, copy=False)
    discharge_date = fields.Datetime(string="Discharge Date", index=True)
    discharge_reason = fields.Char(string="Discharge Reason", index=True)
    admit_date = fields.Datetime(string="Admit Date", index=True)
    admission_type = fields.Char(string="Admission Type", index=True)
    ref_admission_no = fields.Char(string="Ref Admission No.", readonly=False, index=True)
    parent_admission_no = fields.Char(string="Parent Admission No.", readonly=False, index=True)
    patient_type = fields.Selection([('1', 'OP'), ('2', 'IP'), ('3', 'Emergency'), ('4', 'Daycare'), ('5', 'MCU/Pharmacy Issues Only(FO)'), ('6', 'Pharmacy (Direct)'), ('0', 'Both')], string='Patient Type', readonly=True, store=True, index=True)
    
    analytic_budget_id = fields.Many2one('account.analytic.account', string='Budget', domain=[('parent_id', '!=', False)])
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Doctor', index=True)
    parent_analytic_id = fields.Many2one('account.analytic.account',string='Specialization (Analytic)', readonly=True, related='account_analytic_id.parent_id', store=True,index=True)
    parent_analytic_primary_id = fields.Many2one('account.analytic.account', string='Specialization (Primary Doctor)', readonly=True, store=True, index=True)
    primary_doc_id = fields.Many2one('account.analytic.account', string='Primary Doctor', index=True)
    specialization_primary = fields.Char(string="Specialization Primary Doctor", index=True)
    referral_doc_id = fields.Many2one('account.analytic.account', string='Referral Doctor', index=True)
    referral_id = fields.Many2one('referral.transaction', string="Referral Trans", index=True)
    referral_number = fields.Char(string="Referral No.", readonly=False, index=True)
    
    perform_doc_id = fields.Many2one('account.analytic.account', string='Perform Doctor', index=True)
    prescribe_doc_id = fields.Many2one('account.analytic.account', string='Prescribe Doctor', index=True)
    parent_perform_id = fields.Many2one('account.analytic.account', string='Specialization (Perform Doctor)', index=True)
    parent_prescribe_id = fields.Many2one('account.analytic.account', string='Specialization (Prescribe Doctor)', index=True)

    surgery_operator_id = fields.Many2one('account.analytic.account', required=False, string='Surgery Operator', index=True)
    surgery_operator_ass_id = fields.Many2one('account.analytic.account', required=False, string='Surgery Operator (Ass)', index=True)
    anesthetist_operator_id = fields.Many2one('account.analytic.account', required=False, string='Anesthetist Operator', index=True)
    anesthetist_operator_ass_id = fields.Many2one('account.analytic.account', required=False, string='Anesthetist Operator (Ass)', index=True)
    surgery_team_id = fields.Many2one('account.analytic.account', required=False, string='Surgery Team', index=True)
    surgery_team_ass_id = fields.Many2one('account.analytic.account', required=False, string='Surgery Team (Ass)', index=True)
    
    type_line = fields.Char(string="Type Line", readonly=True, index=True)
    payer_amount = fields.Float(string="Main Payer Amount")
    subpayer_amount = fields.Float(string="Sub Payer Amount")
    personal_amount = fields.Float(string="Personal Amount")
    service_categ_id = fields.Many2one('product.category', string="Service Category", required=False, readonly=True, store=True, index=True)
    product_categ_id = fields.Many2one('product.category', string="Product Category", required=False, readonly=True, store=True, index=True)
    department_id = fields.Char(string='Department Area', readonly=True, store=True, index=True)
    
    payer = fields.Many2one('res.partner', string='Main Payer Name', store=True, index=True)
    payer_code = fields.Char(string="Main Payer Code", readonly=True, index=True)
    payer_type = fields.Char(string="Main Payer Type", readonly=True, index=True)
    payer_name = fields.Char(string="Payer Name Rawdata", readonly=True, index=True)
    sub_payer = fields.Many2one('res.partner', string='Sub Payer Name', store=True, index=True)
    sub_payer_code = fields.Char(string="Sub Payer Code", readonly=True, index=True)
    sub_payer_type = fields.Char(string="Sub Payer Type", readonly=True, index=True)
    
    revenue_type = fields.Char(string="Revenue Type", index=True)
    special_group = fields.Char(string="Special Group", index=True)
    special_group2 = fields.Char(string="Special Group 2", index=True)
    service_group = fields.Char(string="Service Group Name", index=True)
    service_group_id = fields.Many2one('product.category', string='Service Group ID', store=True, index=True)

    patient_group = fields.Char(string="Patient Group", index=True)

    order_no = fields.Char(string="HIS Order No")
    order_item_no = fields.Char(string="HIS Order Item")
    order_id = fields.Many2one('sale.order', string='Admission Number', required=True, ondelete='cascade', index=True, copy=False)
    order_type = fields.Char(string="HIS OrderType")
    order_date = fields.Datetime(string="HIS Order Date", index=True)
    sales_id = fields.Char(string="HIS SalesID")
    sales_return_id = fields.Char(string="HIS ReturnID")
    sales_date = fields.Char(string="HIS Sales Date")
    sales_return_date = fields.Char(string="HIS Return Date")
    
    package_id = fields.Many2one('product.product', string="Package Rel", change_default=True, ondelete='restrict', required=False)
    package_name = fields.Char(string="Package Name", index=True)
    package_order_no = fields.Char(string="Package Order Number", index=True)
    package_type = fields.Char(string="Package Type", index=True)
    package_order_date = fields.Datetime(string="Package Order Date", index=True)
    package_contribution = fields.Float(string="Package Contribution", readonly=True)
    package_doctor_share = fields.Float(string="Package Doctor Share")

    
    package_selling_price = fields.Float(string="Package Selling Price", readonly=True)
    
    product_id = fields.Many2one('product.product', string='Product', index=True, domain=[('sale_ok', '=', True)], change_default=True, ondelete='restrict', required=True)
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure', required=True, index=True)
    item_specialisation = fields.Char(string="Item Specialisation", index=True)
    name = fields.Text(string='Service Item', required=True, index=True)
    manufacture = fields.Char(string="Manufacturer Name", index=True)
    brand = fields.Char(string="Brand Name", index=True)

    batch_id = fields.Char(string="HIS BatchNo")
    batch_rel = fields.Many2one('stock.lot', string="HIS Batch Rel")
    batch_expired = fields.Date(string="HIS Batch Expired")
    
    is_takeout = fields.Boolean(string="Is Takeout Revenue", default=False, readonly=True)
    is_baby = fields.Boolean(string="Is Child/Baby", default=False, readonly=True)
    is_surgery = fields.Boolean(string="Is Surgery", default=False, readonly=True)
    is_covid = fields.Boolean(string="Is Covid", default=False, readonly=True)
    is_hd = fields.Boolean(string="Is HD", default=False, readonly=True)
    is_homevisit = fields.Boolean(string="Is HomeVisit", default=False, readonly=True)
    is_hotel = fields.Boolean(string="Is Hotel Visit", default=False, readonly=True)
    is_icu = fields.Boolean(string="Is ICU", default=False, readonly=True)
    is_isoman = fields.Boolean(string="Is ISOMAN", default=False, readonly=True)
    is_cathlab = fields.Boolean(string="Is Cathlab", default=False, readonly=True)
    is_consultation = fields.Boolean(string="Is Consultation", default=False, readonly=True)
    is_package = fields.Boolean(string="Is Component of Package", default=False, readonly=True)
    
    # 2021-09-15 Request Pak Harits
    is_daycare = fields.Boolean(string="Is Daycare", default=False, readonly=True)
    # 2023-07-25 Penambahan Flaging untuk Akasia 365 MC
    is_akasia = fields.Boolean(string="Is Akasia 365 MC", default=False, readonly=True)

    # 2024.01.15 - penambahan flagging untuk Mayapada Eye Centre 
    is_mec = fields.Boolean(string="Is GOR of Eye Centre", default=False, readonly=True)
    
    bed_type = fields.Char(string="Bill BedTypeName", index=True)
    bed_type_id = fields.Many2one('hospital.bed.type', string='Billable BedType', required=False, index=True)
    alloted_bed_type_id = fields.Many2one('hospital.bed.type', string='Alloted BedType', required=False, index=True)
    eligible_bed_type_id = fields.Many2one('hospital.bed.type', string='Eligible BedType', required=False, index=True)
    
    partner_id = fields.Many2one('res.partner', string='Patient Name', readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)] }, required=False, change_default=True, index=True, tracking=True, store=True)
    registration_code = fields.Char(string="Patient MRID", readonly=True, store=True, index=True)
    kelurahan = fields.Char(string="Sub-district", index=True)
    kecamatan = fields.Char(string="Districts", index=True)
    kota = fields.Char(string="Patient City", index=True)
    patient_country = fields.Char(string="Patient Country", index=True)
    patient_state = fields.Char(string="Patient State", index=True)
    patient_area = fields.Char(string="Patient Area", index=True)
    patient_street = fields.Char(string="Patient Street", index=True)
    patient_nationality = fields.Char(string="Patient Nationality", index=True)  

    length_of_stay = fields.Char(string="Stay", readonly=True, index=True)
    length_of_stay_float = fields.Float(string="Length Of Stay", readonly=True)
    length_of_stay_average = fields.Float(string="Length Of Stay Average", readonly=True)

    cyto = fields.Boolean(string="Cyto", index=True, default=False)
    penyulit = fields.Boolean(string="Penyulit", index=True, default=False)
    narcotic = fields.Boolean(string="Narcotic", index=True, default=False)
    generic = fields.Boolean(string="Generic", index=True, default=False)
    psychotropic = fields.Boolean(string="Psychotropic", index=True, default=False)
    antibiotic = fields.Boolean(string="Antibiotic", index=True, default=False)

    location_id = fields.Many2one('stock.location', string="Facility/Location", readonly=True, index=True)
    room_id = fields.Many2one('hospital.room.name', string='Room Name', required=False, index=True)
    bed_id = fields.Many2one('hospital.bed.name', string='Bed Name', required=False, index=True)
    bed_allocation_start = fields.Datetime(string="Allocation Start", index=True)
    bed_allocation_end = fields.Datetime(string="Allocation End", index=True)
    bed_allocation_no = fields.Char(string="Allocation No.")
    status_bill = fields.Char(string="Status Bill", index=True)

    normal_qty = fields.Float(string="Normal Qty")
    normal_uom = fields.Many2one('uom.uom', string="Normal UoM", index=True)
    normal_uom_name = fields.Char(related="normal_uom.name", string='Normal UOM Name', readonly=True, index=True, store=True)
    uom_small = fields.Many2one('uom.uom', string="Small UoM", index=True)
    uom_small_name = fields.Char(related="uom_small.name", string='Smallest UOM Name', readonly=True, index=True, store=True)
    
    price_total = fields.Monetary(compute='_compute_amount', string='Total Revenue', readonly=True, store=True)
    tariff_id = fields.Many2one('hospital.tariff', string="Tariff Name")

    service_cost_unit = fields.Float(string="Service Cost Unit", store=True)
    service_cost_total = fields.Float(string="Service Cost Total", store=True)
    cost_unit = fields.Float(string="HIS Cost Unit", store=True)
    cost_total = fields.Float(string="HIS Cost Total", store=True)

    cost_date = fields.Date(string="Odoo Cost Date", index=True)
    cost_unit_odoo = fields.Float(string="Odoo Cost Unit")
    cost_total_odoo = fields.Float(string="Odoo Cost Total")

    hna_unit = fields.Float(string="HNA Unit", store=True)
    hna_total = fields.Float(string="HNA Total", store=True)
    base_price_unit = fields.Float(string="Base Price Unit", store=True)
    base_price_total = fields.Float(string="Base Price Total", store=True)
    
    discount_id = fields.Many2one('hospital.discount.type', string='Discount Type', required=False, index=True)
    discount_name = fields.Char(string="Discount Name", index=True)
    discount_date = fields.Datetime(string="Discount Date", index=True)
    discount_level = fields.Char(string="Discount Level", index=True)
    discount_reason = fields.Char(string="Discount Reason", index=True)

    secondary_diagnosis_code = fields.Char(string="Secondary Diagnosis Code", readonly=True, index=True)
    secondary_diagnosis_name = fields.Char(string="Secondary Diagnosis Name", readonly=True, index=True)
    primary_diagnosis_code = fields.Char(string="Primary Diagnosis Code", readonly=True, index=True)
    primary_diagnosis_name = fields.Char(string="Primary Diagnosis Name", readonly=True, index=True)
    repeat_diagnosis_code = fields.Char(string="Repeat Diagnosis Code", readonly=True, index=True)
    repeat_diagnosis_name = fields.Char(string="Repeat Diagnosis Name", readonly=True, index=True)

    # auto compute relation to stock.picking and stock.move for valuation price
    picking_id = fields.Many2one('stock.picking', string="Stock Picking")
    picking_created = fields.Boolean(string="Stock Picking Created", default=False, readonly=True, index=True)

    move_id = fields.Integer(string="Stock Move") #fields.Many2one('stock.move', string="Stock Move")   
    move_created = fields.Boolean(string="Stock Move Created", readonly=True)
    
    invoice_status = fields.Selection([('upselling', 'Upselling Opportunity'), ('invoiced', 'Fully Invoiced'), ('to invoice', 'To Invoice'), ('no', 'Nothing to Invoice')], string='Z - (Hide) Invoice Status', compute='_compute_invoice_status', store=True, readonly=True, default='no')
    salesman_id = fields.Many2one(store=True, string='Z - (Hide) Salesperson', readonly=True)
    layout_category_id = fields.Many2one('sale.layout_category', string='Z - (Hide) Section')
    qty_delivered_updateable = fields.Boolean( string='Z - (Hide) Can Edit Delivered')
    order_partner_id = fields.Many2one(store=True, string='Z - (Hide) Customer')
    analytic_tag_ids = fields.Many2many('account.analytic.tag', string='Z - (Hide) Analytic Tags')
    service_categ_name = fields.Char(related="service_categ_id.name", string='Z - (Hide) Service Category Name', readonly=True, index=True, store=True)
    currency_id = fields.Many2one(store=True,string='Z - (Hide) Currency', readonly=True)
    create_date = fields.Datetime(string='Creation Date', readonly=True, index=True, help="Date on which sales order is created.")
    converted = fields.Boolean(string='Z - (Hide) Converted', default=False, store=True, index=True)
    doctor_backup_id = fields.Float(string="Z - (Hide) Backup Doctor ID", readonly=True)
    is_conversion = fields.Boolean(string="Z - (Hide) Is Conversion", readonly=True)
    updated_date = fields.Boolean(string="Z - (Hide) Update Date", readonly=True, default=False)
    margin_percent = fields.Float(string="Z - (Hide) Margin Percent", store=True)
    uom_small = fields.Many2one('uom.uom', string="Z - (Hide) Smallest UOM", index=True)
    conversion_rate = fields.Float(string="Z - (Hide) Conversion Rate")
    mcu_updated = fields.Boolean(string="MCU Updated", index=True)
    lob_los = fields.Char(string="Z - (Hide) LOB/LOS", readonly=True, index=True)
    # qty_delivered = fields.Float( string='Z - (Hide) Delivered', copy=False, digits=dp.get_precision('Product UoM'), default=0.0, compute='_compute_delivered', store=False)
    # qty_to_invoice = fields.Float(compute='_compute_delivered', string='Z - (Hide) To Invoice', store=False, readonly=True, digits=dp.get_precision('Product UoM'))
    normal_price = fields.Float(string="Z - (Hide) Normal Price")
    jurnal_ids = fields.One2many('account.move.line', 'sale_id', string='Z - (Hide) Journal Items')

    group_analytic_doctor_id = fields.Many2one('account.analytic.account', string="Group Analytic Doctor")
    group_analytic_spec_id = fields.Many2one('account.analytic.account', string="Group Analytic Specialise")
    group_analytic_subspec_id = fields.Many2one('account.analytic.account', string="Group Analytic SubSpecialise")
    
    group_primary_doctor_id = fields.Many2one('account.analytic.account', string="Group Primary Doctor")
    group_primary_spec_id = fields.Many2one('account.analytic.account', string="Group Primary Specialise")
    group_primary_subspec_id = fields.Many2one('account.analytic.account', string="Group Primary SubSpecialise")

    group_perform_doctor_id = fields.Many2one('account.analytic.account', string="Group Perform Doctor")
    group_perform_spec_id = fields.Many2one('account.analytic.account', string="Group Perform Specialise")
    group_perform_subspec_id = fields.Many2one('account.analytic.account', string="Group Perform SubSpecialise")

    group_prescribe_doctor_id = fields.Many2one('account.analytic.account', string="Group Prescribe Doctor")
    group_prescribe_spec_id = fields.Many2one('account.analytic.account', string="Group Prescribe Specialise")
    group_prescribe_subspec_id = fields.Many2one('account.analytic.account', string="Group Prescribe SubSpecialise")
    
    throughput_order = fields.Float(string="Throughput Order", store=False)
    throughput_visit = fields.Float(string="Throughput Visit", store=False)

    sync_id_api_billing_id = fields.Char(string="Sync ID API Billing ID", store=True, index=True)
    sync_id_api_cob_id = fields.Char(string="Sync ID API Cob ID", store=True, index=True)
    sync_id_api_sub_cob_id = fields.Char(string="Sync ID API Sub Cob ID", store=True, index=True)

    is_fetched = fields.Boolean(string="Is Fetched", default=False)
    fetched_date = fields.Date(string="Fetched Date")

    sales_billitemid = fields.Char(string="Sales BillItemID", readonly=True, index=True)
    sales_chargecodeid = fields.Char(string="Sales ChargeCodeID", readonly=True, index=True)
    sales_orderitemid = fields.Char(string="Sales OrderItemID", readonly=True, index=True)
    sales_patientorderid = fields.Char(string="Sales Patient Order Item ID", index=True)
    

    item_specialisation_id = fields.Many2one('product.category', string='Item Specialisation ID', store=True, index=True)
    arcus_billing_group_id = fields.Many2one('product.category', string='Arcus Billing Group ID', store=True, index=True)
    arcus_sub_billing_group_id = fields.Many2one('product.category', string='Arcus Billing Group ID', store=True, index=True)
    sales_order_status = fields.Char(string="Sales Order Status", index=True)
    sales_order_lastupdate = fields.Datetime(string='Sales Order Last Update', index=True)
    ref_admission_id = fields.Many2one('sale.order', string='Ref Admission ID.', required=False, index=True, copy=False)
    sales_order_start = fields.Datetime(string="Sales Order Start", index=True)
    sales_order_end = fields.Datetime(string="Sales Order End", index=True)



    sales_patient_register_date = fields.Datetime(string='Sales Patient Register Date', index=True)
    sales_admission_datetime = fields.Datetime(string='Sales Admission Datetime', index=True)
    sales_discharge_datetime = fields.Datetime(string='Sales Discharge Datetime', index=True)
    sales_billing_datetime = fields.Datetime(string='Sales Billing Datetime', index=True)
    sales_product_ingredient = fields.Char(string="Sales Product Ingredient", index=True)
    
    sales_diagnosis_primary_code = fields.Char(string="Sales Diagnosis Primary Code", index=True)
    sales_diagnosis_primary_name = fields.Char(string="Sales Diagnosis Primary Name", index=True)
    sales_diagnosis_secondary_code = fields.Char(string="Sales Diagnosis Secondary Code", index=True)
    sales_diagnosis_secondary_name = fields.Char(string="Sales Diagnosis Secondary Name", index=True)
    sales_procedure_code = fields.Char(string="Sales Procedure Code", index=True)
    sales_procedure_name = fields.Char(string="Sales Procedure Name", index=True)

    



    # 2022.03.24 - Firgiawan Khafidli
    # Hide beberapa kolom yang mengganggu 
    @api.model
    def fields_get(self, allfields=None, attributes=None):
        res = super(SaleOrderLine, self).fields_get(allfields, attributes=attributes)
        pivot_id = self._context.get('view_pivot_id', False)
        
        # if pivot_id:
        #     # open('/opt/odoo16/logs/log_move_line.log','a+').write('\n\n ' + str(pivot_id))
        #     if pivot_id == 'sales_analysis':
        #         for field in res:
        #             # open('/opt/odoo16/logs/log_move_line.log','a+').write('\n\n ' + str(field))
        #             if field in ['amount_currency','amount_residual','amount_residual_currency','analytic_account_id','analytic_line_ids','analytic_tag_ids','balance_cash_basis','blocked','company_currency_id','counterpart','create_date','create_uid','credit','credit_cash_basis','currency_id','date_maturity','debit','debit_cash_basis','full_reconcile_id','id','invoice_id','matched_credit_ids','matched_debit_ids','parent_state','payment_id','product_id','product_uom_id','quantity','recompute_tax_line','reconciled','statement_id','statement_line_id','tax_base_amount','tax_exigible','tax_ids','tax_line_grouping_key','tax_line_id','write_date','write_uid','balance']:    
        #                 res[field]['store'] = False # to hide in 'Select Columns' filter in tree views
        
        for field in res:
            if field in ['invoice_status', 'salesman_id', 'layout_category_id', 'qty_delivered_updateable', 'order_partner_id', 'analytic_tag_ids', 'service_categ_name', 'currency_id', 'converted', 'doctor_backup_id', 'is_conversion', 'updated_date', 'margin_percent', 'uom_small', 'conversion_rate', 'mcu_updated', 'lob_los', 'qty_delivered', 'qty_to_invoice', 'normal_price', 'jurnal_ids']:    
                res[field]['store'] = False # to hide in 'Select Columns' filter in tree views
        return res


    # 2021.06.12 - Firgiawan Khafidli 
    # Override _get_invoice_qty() bawaan base module odoo
    # Integrasi Dhealth berat untuk create/write data ke sale.order.line u/ transaksi sale.order yg sudah memiliki banyak child record
    @api.model
    def _prepare_add_missing_fields(self, values):
        res = {}
        return res

    # 2021.06.12 - Firgiawan Khafidli 
    # Override _get_invoice_qty() bawaan base module odoo
    # Integrasi Dhealth berat untuk create/write data ke sale.order.line u/ transaksi sale.order yg sudah memiliki banyak child record
    @api.depends('invoice_lines.invoice_id.state', 'invoice_lines.quantity')
    def _get_invoice_qty(self):
        """
        Compute the quantity invoiced. If case of a refund, the quantity invoiced is decreased. Note
        that this is the case only if the refund is generated from the SO and that is intentional: if
        a refund made would automatically decrease the invoiced quantity, then there is a risk of reinvoicing
        it automatically, which may not be wanted at all. That's why the refund has to be created from the SO
        """

    # 2021.06.12 - Firgiawan Khafidli 
    # Override _prepare_invoice_line() bawaan base module odoo
    # Integrasi Dhealth berat untuk create/write data ke sale.order.line u/ transaksi sale.order yg sudah memiliki banyak child record
    # @api.multi
    def _prepare_invoice_line(self, qty):
        self.ensure_one()
        res = {}
        return res

    # 2021.06.12 - Firgiawan Khafidli 
    # Override invoice_line_create() bawaan base module odoo
    # Integrasi Dhealth berat untuk create/write data ke sale.order.line u/ transaksi sale.order yg sudah memiliki banyak child record
    # @api.multi
    def invoice_line_create(self, invoice_id, qty):
        """
        Create an invoice line. The quantity to invoice can be positive (invoice) or negative
        (refund).

        :param invoice_id: integer
        :param qty: float quantity to invoice
        """

    # 2021.06.12 - Firgiawan Khafidli 
    # Override _onchange_discount() bawaan base module odoo
    # Integrasi Dhealth berat untuk create/write data ke sale.order.line u/ transaksi sale.order yg sudah memiliki banyak child record
    @api.onchange('product_id', 'price_unit', 'product_uom', 'product_uom_qty', 'tax_id')
    def _onchange_discount(self):
        """ 
        Do something to override this function.
        """

    #@api.model
    def create(self, vals):
        # open('/opt/odoo16/logs/order_line.log', 'a+').write('\n' + "start create")
        result = super(SaleOrderLine, self).create(vals)
        # open('/opt/odoo16/logs/order_line.log', 'a+').write('\n' + "end result, next modified function")
        #for record in result:
        #    if record.env.user.company_id.sync_api_active == True:
        #        record.env.cr.execute("DELETE from sale_order_line where id in (select max(a.id) from sale_order_line a where a.sync_id_api is not null group by a.sync_id_api having count(*) > 1)")
        #        date_wib = False
                # open('/opt/odoo16/logs/order_line.log', 'a+').write('\n' + "query delete done")
                #if record.order_date:
                #    date_wib = tools.datetime.strptime(record.order_date,'%Y-%m-%d %H:%M:%S') - tools.timedelta(hours=7)
                #    record.order_date = date_wib
                    # open('/opt/odoo16/logs/order_line.log', 'a+').write('\n' + "date done")
                    # record.order_id.date_order = date_wib
                # if record.billno:
                #     record.order_id.billno = record.billno
                # if record.payer:
                #     record.order_id.payer_id = record.payer

                # open('/opt/odoo16/logs/order_line.log', 'a+').write('\n' + "update master done")
                # open('/opt/odoo16/logs/date.log', 'a+').write('\n' + 'UPDATE LINE' + str(record.order_id.date_order))
        
        # open('/opt/odoo16/logs/sale_stock_valuation.log', 'a+').write('\n' + "masuk 1")

        if result.sync_type == '3' and (result.department_id =='Rehabilitation Medic' or result.department_id =='Rehabilitasi Medis' or result.department_id =='Rehabilitasi Medik'):
            result.special_group2 ='MEDICAL REHABILITATION'
            result.revenue_type ='LOS'
        if result.sync_type == '6' and result.department_id =='REHABILITASI MEDIK':
            result.special_group2 ='MEDICAL REHABILITATION'
            result.revenue_type ='LOS'
        if result.sync_type == '6' and result.department_id =='HAEMODIALISA':
            result.special_group2 ='HAEMODIALYSIS'
            result.revenue_type ='LOS'
            
        if result.sync_id_api:
            if result.type_line in ("BILLING","BILLING CANCEL","DISCOUNT","DISCOUNT CANCEL"):
                result.send_api_billing()

        if result.company_id.sync_api_stock_active:
            # open('/opt/odoo16/logs/sale_stock_valuation.log', 'a+').write('\n' + "masuk 2")
            result.stock_valuation()
        return result

    # @api.multi
    def send_api_billing(self):
        if self.company_id.api_backend_active_mobile == True:
            if self.company_id.api_backend_endpoint_mobile and self.company_id.api_backend_key_mobile:
                api_endpoint = self.company_id.api_backend_endpoint_mobile + '/billing/billing_insert'
                api_headers = {'Content-Type': 'application/json', 'X-Behaviour':'blocking', 'Authorization': 'Basic ' + self.company_id.api_backend_key_mobile }
                
                data_patient = self.env['res.partner'].search([('id','=', self.partner_id.id)], limit=1)
                data_billing = self.env['sale.order.bill'].search([('id','=', self.billing_id.id)], limit=1)
                
                # Declare payer_name
                if data_billing.payer_type == "Pribadi":
                    payer_name = "PRIVATE"
                else:
                    payer_name = data_billing.payer_id.name
                
                # Declare type_line
                if self.type_line == "BILLING":
                    type_line = "BILL"
                elif self.type_line == "BILLING DISCOUNT":
                    type_line = "BILL DISCOUNT"
                elif self.type_line == "BILLING CANCEL":
                    type_line = "BILL CANCEL"
                else:
                    type_line = self.type_line
                    
                # Declare patient_type
                if self.patient_type == "1":
                    patient_type = "OutPatient"
                elif self.patient_type == "2":
                    patient_type = "InPatient"
                elif self.patient_type == "3":
                    patient_type = "Emergency"
                elif self.patient_type == "4":
                    patient_type = "DayCare"
                elif self.patient_type == "5":
                    patient_type = "MCU"
                elif self.patient_type == "6":
                    patient_type = "Pharmacy"
                elif self.patient_type == "0":
                    patient_type = "Both"
                    
                # Generate Payload
                payload = {}
                payload["TglProses"] = self['tglproses'] or None
                payload["RegCode"] = self['registration_code'] or ""
                payload["PatientName"] = data_patient.name or ""
                payload["DateOfBirth"] = data_patient.date_of_birth or ""
                payload["Age"] = data_patient.age or ""
                payload["AgeType"] = data_patient.age_type or ""
                payload["Gender"] = data_patient.gender or ""
                payload["PatientAddress"] = data_patient.street or ""
                payload["PatientType"] = patient_type or ""
                payload["AdmissionId"] = self.order_id.id or None
                payload["AdmissionNumber"] = self.order_id.name or ""
                payload["AdmitDate"] = self.admit_date or ""
                payload["RecordType"] = type_line or ""
                payload["BillID"] = self.billing_id.id or ""
                payload["BillNo"] = self.billno or ""
                payload["BillDate"] = data_billing.bill_date or ""
                payload["BillCancelDate"] = data_billing.cancel_date or ""
                payload["BillCancelItemDate"] = data_billing.cancel_date or ""
                payload["BillCancelReason"] = data_billing.note or ""
                payload["PayerAmount"] = self.payer_amount or 0
                payload["PatientAmount"] = self.personal_amount or 0
                payload["Value"] = self.price_total or 0
                payload["PrimaryDocName"] = self.env['account.analytic.account'].search([('id','=', self.primary_doc_id.id), ('sync_type','=', self.sync_type)], limit=1).name or ""
                payload["PrimaryDocSpec"] = self.env['account.analytic.account'].search([('id','=', self.parent_analytic_id.id), ('sync_type','=', self.sync_type)], limit=1).name or ""
                payload["DischargeDate"] = self.discharge_date or ""
                payload["PayerName"] = payer_name or ""
                payload["Ward"] = self.location_id.name or ""
                payload["ServiceItemName"] = self.service_categ_id.name or ""
                payload["BedName"] = self.bed_id.name
                
                response_json = requests.post(url=api_endpoint, headers=api_headers, json=payload, verify=False)
                
                json_resp = response_json.json()
                now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if json_resp:
                    data = {'payload': payload, 
                        'response': json_resp, 
                        'datetime': now}
                
                return data
            
    # auto create stock_picking per record transaksi untuk stockable product
    # @api.multi
    def stock_valuation(self):
        for record in self:
            # open('/opt/odoo16/logs/sale_stock_valuation.log', 'a+').write('\n' + "masuk 3")
            if record.sync_id_api and record.product_id.type == 'product':
                # open('/opt/odoo16/logs/sale_stock_valuation.log', 'a+').write('\n' + "masuk 4")
                print("Do something...")
                # create procurement
                if record.order_id.procurement_created is not True:
                    procurement_code = record.order_id.company_id.company_code + '/' + record.order_id.name 
                    group = self.env['procurement.group'].search([('name','=', procurement_code)], limit=1)
                    if not group:
                        group = self.env['procurement.group'].create({'name': procurement_code, 'move_type': 'direct'})
                    if group:
                        record.order_id.procurement_group_id = group.id 
                        record.order_id.procurement_created = True 

                # create picking 
                if record.order_id.procurement_created and record.picking_created is not True:
                    data = {}
                    if record.product_uom_qty < 0:
                        trans_type = 'sales.return'
                    else:
                        trans_type = 'sales.issue'
                    location_dest_id = self.env['stock.location'].search([('name','ilike','Customers'), ('company_id','=', record.order_id.company_id.id)], limit=1).id or None

                    data['picking_type_id'] = self.env['stock.picking.type'].search([('sync_id_api','=', trans_type),('sync_type','=', record.sync_type)], limit=1).id or None
                    data['location_id'] = location_dest_id if record.product_uom_qty < 0 else record.location_id.id 
                    data['location_dest_id'] = record.location_id.id  if record.product_uom_qty < 0 else location_dest_id
                    data['group_id'] = record.order_id.procurement_group_id.id 
                    data['company_id'] = record.order_id.company_id.id 
                    data['sales_id'] = record.order_id.id 
                    data['origin'] = record.order_no 
                    data['min_date'] = record.tglproses
                    data['max_date'] = record.tglproses
                    data['date'] = record.tglproses
                    data['date_done'] = record.tglproses
                    data['date_move'] = record.tglproses
                    data['partner_id'] = record.partner_id.id or None
                    data['move_type'] = 'direct'
                    data['note'] = record.name 
                    data['state'] = 'waiting'
                    data['sync_id_api'] = 'SALES.' + str(record.sync_id_api)
                    data['sync_date'] = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    data['sync_type'] = record.sync_type

                    # picking = self.env['stock.picking'].search([('sync_id_api','=', data['sync_id_api']), ('sync_type','=', data['sync_type'])], limit=1)
                    # if not picking:
                    picking = self.env['stock.picking'].create(data)
                    if picking:
                        record.picking_id = picking.id 
                        record.picking_created = True 

                # create move 
                if record.picking_created and record.move_created is not True:
                    data = {}
                    if record.product_uom_qty < 0:
                        trans_type = 'sales.return'
                    else:
                        trans_type = 'sales.issue'
                    location_dest_id = self.env['stock.location'].search([('name','ilike','Customers'), ('company_id','=', record.order_id.company_id.id)], limit=1).id or None

                    data['picking_type_id'] = self.env['stock.picking.type'].search([('sync_id_api','=', trans_type),('sync_type','=', record.sync_type)], limit=1).id or None
                    data['location_id'] = location_dest_id if record.product_uom_qty < 0 else record.location_id.id 
                    data['location_dest_id'] = record.location_id.id  if record.product_uom_qty < 0 else location_dest_id
                    data['group_id'] = record.order_id.procurement_group_id.id 
                    data['company_id'] = record.order_id.company_id.id 
                    data['picking_id'] = record.picking_id.id 
                    data['origin'] = record.order_no
                    data['name'] = record.name
                    data['date'] = record.tglproses
                    data['date_expected'] = record.tglproses
                    data['partner_id'] = record.partner_id.id or None
                    data['product_id'] = record.product_id.id 
                    data['product_uom_qty'] = abs(record.product_uom_qty)
                    #data['product_qty'] = abs(record.scrap_qty)
                    data['product_uom'] = record.product_id.uom_id.id 
                    data['price_unit'] = record.cost_unit
                    data['cost_unit'] = record.cost_unit
                    data['lot_id'] = record.batch_rel.id or None 
                    data['note'] = record.name 
                    data['sale_line_id'] = record.id 
                    data['procure_method'] = 'make_to_stock'
                    data['state'] = 'waiting'
                    data['sync_id_api'] = 'SALES.' + str(record.sync_id_api)
                    data['sync_date'] = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    data['sync_type'] = record.sync_type

                    # move = self.env['stock.move'].search([('sync_id_api','=', data['sync_id_api']), ('sync_type','=', data['sync_type'])], limit=1)
                    # if not move:
                    move = self.env['stock.move'].create(data)
                    if move:
                        record.move_id = move.id 
                        record.move_created = True

                # auto posting picking
                if record.move_created and record.picking_created and record.company_id.sync_api_move_active:
                    picking = record.picking_id
                    picking.force_assign()
                    for pack in picking.pack_operation_ids:
                        if pack.product_qty > 0:
                            pack.write({'qty_done': pack.product_qty})
                    picking.do_transfer()



    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id')
    def _compute_amount(self):
        """
        Compute the amounts of the SO line.
        """
        for line in self:
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            taxes = line.tax_id.compute_all(price, line.order_id.currency_id, line.product_uom_qty, product=line.product_id, partner=line.order_id.partner_shipping_id)
            line.update({
                'price_tax':taxes['total_included'] - taxes['total_excluded'],
                'price_total':taxes['total_included'],
                'price_subtotal':taxes['total_excluded']
            })

    
    
    # @api.multi
    def query_data_line(self):
        print ("Selesai Narik, Start Query UPDATE Data")

        print ("1 - Update Analytic Account")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET account_analytic_id = b.id,
                parent_analytic_id = b.parent_id
            FROM account_analytic_account b 
            WHERE b.id = a.primary_doc_id
                AND a.account_analytic_id IS NULL 
                AND a.primary_doc_id IS NOT NULL
                AND a.sync_type IN('1','2') """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET parent_perform_id = b.parent_id
            FROM account_analytic_account b 
            WHERE b.id = a.perform_doc_id
                AND a.parent_perform_id IS NULL 
                AND a.perform_doc_id IS NOT NULL
                AND a.tglproses >= (CURRENT_DATE-7)
                AND a.sync_type IN('1','2') """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET parent_prescribe_id = b.parent_id
            FROM account_analytic_account b 
            WHERE b.id = a.prescribe_doc_id
                AND a.parent_prescribe_id IS NULL 
                AND a.prescribe_doc_id IS NOT NULL
                AND a.tglproses >= (CURRENT_DATE-7)
                AND a.sync_type IN('1','2') """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET parent_analytic_id = b.parent_id
            FROM account_analytic_account b 
            LEFT JOIN account_analytic_account c 
                ON c.id = b.parent_id
            WHERE b.id = a.account_analytic_id
                AND a.parent_analytic_id IS NULL 
                AND a.account_analytic_id IS NOT NULL
                AND a.sync_type IN('1','2') """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET parent_analytic_id = b.parent_id
            FROM account_analytic_account b 
            INNER JOIN account_analytic_account c 
                ON c.id = b.parent_id
            WHERE b.id = a.account_analytic_id
                AND c.name not like '%TIDAK ADA SPESIALISASI%'
                AND a.parent_analytic_id in (
                    select t.id
                    from account_analytic_account t 
                    where t.name like '%TIDAK ADA SPESIALISASI%')
                AND a.sync_type IN('1','2') """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET parent_analytic_primary_id = b.parent_id,
                specialization_primary = c.name
            FROM account_analytic_account b 
            LEFT JOIN account_analytic_account c 
                ON c.id = b.parent_id
            WHERE b.id = a.primary_doc_id
                AND a.parent_analytic_primary_id IS NULL 
                AND a.primary_doc_id IS NOT NULL
                AND a.sync_type IN('1','2') """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET parent_analytic_primary_id = b.parent_id,
                specialization_primary = c.name
            FROM account_analytic_account b 
            INNER JOIN account_analytic_account c 
                ON c.id = b.parent_id
            WHERE b.id = a.primary_doc_id
                AND c.name not like '%TIDAK ADA SPESIALISASI%'
                AND a.parent_analytic_primary_id in (
                    select t.id
                    from account_analytic_account t 
                    where t.name like '%TIDAK ADA SPESIALISASI%')
                AND a.sync_type IN('1','2') """)

        # Update account_analytic sesuai service di Surgeon Fee
        self.env.cr.execute("""
            UPDATE sale_order_line AS a 
            SET account_analytic_id = sol.account_analytic_id,
                parent_analytic_id = sol.parent_analytic_id
            FROM sale_order_line sol
            INNER JOIN product_category sc ON sc.id = sol.service_categ_id 
            WHERE a.account_analytic_id = a.primary_doc_id
                AND a.tglproses >= (CURRENT_DATE-7)
                AND a.sync_type IN('1','2')
                AND a.order_id = sol.order_id
                AND a.order_no = sol.order_no
                AND sc.name IN ('Surgeon Fee')
                AND a.service_categ_id IN (
                    SELECT pc.id FROM product_category pc 
                    WHERE pc.name IN ('Surgery','Cath Procedure')
                ) """)

        print ("2 - Update PatientType")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET patient_type = (
                select patient_type from sale_order 
                where id = a.order_id) 
            WHERE a.patient_type IS NULL
                AND a.sync_type IN('1','2') """)

        print ("3 - Update Service Category by Product")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET service_categ_id = coalesce(d.parent_id,d.id)  
            from product_product b 
            inner join product_template c
                on c.id=b.product_tmpl_id 
            inner join product_category d 
                on d.id=c.categ_id
            WHERE b.id = a.product_id 
                AND a.service_categ_id IS NULL
                AND a.tglproses >= (CURRENT_DATE-7)
                AND a.sync_type IN('1','2') """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET manufacture = coalesce(c.manufacturer,'')
            FROM product_product b 
            INNER JOIN product_template c
                ON c.id=b.product_tmpl_id 
            WHERE b.id = a.product_id 
                AND c.sync_is_service is not true 
                AND a.manufacture IS NULL
                AND a.tglproses >= (CURRENT_DATE-7)
                AND a.sync_type IN('1','2') 
        """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET brand = coalesce(c.brand,'')
            FROM product_product b 
            INNER JOIN product_template c
                ON c.id=b.product_tmpl_id 
            WHERE b.id = a.product_id 
                AND c.sync_is_service is not true 
                AND a.brand IS NULL
                AND a.tglproses >= (CURRENT_DATE-7)
                AND a.sync_type IN('1','2') 
        """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET narcotic = c.narcotic,
                generic = c.generic,
                psychotropic = c.psychotropic,
                antibiotic = c.antibiotic
            FROM product_product b 
            INNER JOIN product_template c
                ON c.id=b.product_tmpl_id 
            WHERE b.id = a.product_id 
                AND c.sync_is_service is not true 
                AND a.tglproses >= (CURRENT_DATE-7)
                AND a.sync_type IN('1','2') 
                AND (
                    a.narcotic is not True OR
                    a.generic is not True OR
                    a.psychotropic is not True OR
                    a.antibiotic is not True 
                )""")

        print ("4 - Update Payer")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET payer = b.payer_id,
                payer_name = c.name,
                payer_code = c.vendor_code,
                payer_type = c.customer_type_wipro
            FROM sale_order b 
            INNER JOIN res_partner c 
            ON c.id=b.payer_id 
                AND c.insurance=True 
                AND c.active=True 
                AND c.sync_type=b.sync_type
            WHERE b.id = a.order_id
                AND a.payer IS NULL
                AND b.payer_id IS NOT NULL
                AND a.payer_name = 'PRIVATE' 
                AND a.sync_type IN('1','2') """)

        print ("5 - Update Payer Private")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a 
            SET payer = 5817,
                payer_type = 'PRIVATE'
            WHERE coalesce(a.payer,0) not in(5817)
                AND a.payer_name = 'PRIVATE'
                AND a.sync_type IN('1','2') 
        """)

        print ("7 - Update Patient")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET partner_id = b.partner_id,
                registration_code = c.registration_code,
                kota = c.patient_city,
                kecamatan = c.patient_district,
                kelurahan = c.patient_subdistrict
            FROM sale_order b 
            INNER JOIN res_partner c 
            ON c.id = b.partner_id
                and c.patient=True
                and c.active=True
                and c.sync_type=b.sync_type
            WHERE b.id = a.order_id
                AND a.tglproses >= (CURRENT_DATE-7)
                AND a.sync_type IN('1','2') 
                AND (
                    a.partner_id IS NULL OR 
                    a.registration_code IS NULL OR 
                    a.kecamatan IS NULL OR
                    a.kelurahan IS NULL
                )""")

        print ("8 - Update LOB LOS ")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET lob_los = revenue_type
            WHERE a.lob_los IS NULL
            AND a.tglproses >= (CURRENT_DATE-7)
            AND a.sync_type IN('1','2') """)

        # 2021.07.22 
        # update bug banyak masalah salah konversi disisi odoo 
        # konversi product.template bug sudah uom small malah di bagi dengan rate factor

        # print ("9 - Update Lowest UoM & Conversion Rate")
        # self.env.cr.execute("""
        #     UPDATE sale_order_line AS a 
        #     SET uom_small = b.uom_id,
        #         conversion_rate = b.conversion_rate
        #     FROM product_template b
        #     INNER JOIN product_product c 
        #         ON  c.product_tmpl_id = b.id
        #     WHERE c.id = a.product_id
        #         AND a.uom_small IS NULL
        #         AND a.sync_type IN('1','2') """)

        # self.env.cr.execute("""
        #     UPDATE sale_order_line AS a
        #     SET is_conversion = True, 
        #         normal_uom = a.product_uom, 
        #         normal_qty = a.product_uom_qty, 
        #         normal_price = a.price_unit 
        #     FROM product_template b
        #     INNER JOIN product_product c 
        #         ON  c.product_tmpl_id = b.id
        #     WHERE c.id = a.product_id
        #         AND a.product_uom = b.uom_po_id 
        #         AND a.is_conversion IS NULL
        #         AND a.sync_type IN('1','2') """)

        # self.env.cr.execute("""
        #     UPDATE sale_order_line as sol 
        #     SET converted = True, 
        #         product_uom_qty = sol.normal_qty * sol.conversion_rate, 
        #         price_unit = sol.normal_price / sol.conversion_rate, 
        #         product_uom = sol.uom_small 
        #     WHERE sol.is_conversion = True 
        #         AND sol.converted IS NULL
        #         AND sol.sync_type IN('1','2') """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a
            SET product_uom_qty = product_uom_qty * -1, 
                price_unit = price_unit * -1 
            WHERE a.product_uom_qty > 0 
                AND a.price_unit < 0
                AND a.sync_type IN('1','2')  """)

        print ("10 - Update Sale Order Bill")
        self.env.cr.execute("""
            UPDATE sale_order AS a SET 
                status_bill = 'BILL',
                billno = (case when a.billno is null then b.billno else a.billno end),
                sync_line_date = b.tglproses 
            FROM (
                select 
                    max(tglproses) tglproses,
                    max(billno) billno,
                    order_id
                from sale_order_line 
                where type_line='BILL'
                group by order_id
            ) b 
            WHERE a.id = b.order_id
            AND a.status_bill IS NULL 
            AND a.sync_type IN('1','2') """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a 
            SET status_bill = 'BILL',
                bill_date = (case when a.bill_date is null then b.sync_line_date else a.bill_date end),
                billno = (case when a.billno is null then b.billno else a.billno end)
            FROM sale_order b 
            WHERE b.id = a.order_id
                AND a.status_bill IS NULL
                AND b.status_bill = 'BILL'
                AND a.sync_type IN('1','2') """)

        print ("11 - Update admit_date & discharge_date")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                admit_date = date(b.date_order),
                admission_type = b.admission_type
            FROM sale_order b 
            WHERE b.id = a.order_id
            AND a.admit_date IS NULL
            AND a.tglproses >= (CURRENT_DATE-7)
            AND a.sync_type IN('1','2') """)
        
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                discharge_date = date(b.discharge_date),
                discharge_reason = b.discharge_reason
            FROM sale_order b 
            WHERE b.id = a.order_id
            AND a.discharge_date IS NULL
            AND a.tglproses >= (CURRENT_DATE-7)
            AND a.sync_type IN('1','2') """)

        
        print ("12 - Update flag untuk admission contain tindakan bedah/surgery")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET is_surgery = True 
            WHERE EXISTS (
                SELECT 1 
                FROM sale_order_line t 
                INNER JOIN product_category t2
                    ON t2.id = t.service_categ_id 
                WHERE t2.name in('Surgery')
                AND t.order_id = a.order_id )
            AND a.is_surgery is not True  
            AND a.tglproses >= (CURRENT_DATE-7) 
            AND a.sync_type IN('1','2') """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET is_cathlab = True 
            WHERE EXISTS (
                SELECT 1 
                FROM sale_order_line t 
                INNER JOIN product_category t2
                    ON t2.id = t.service_categ_id 
                WHERE t2.name ilike '%Cath%'
                AND t.order_id = a.order_id )
            AND a.is_cathlab is not True  
            AND a.tglproses >= (CURRENT_DATE-7) 
            AND a.sync_type IN('1','2') """)
        
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET is_covid = True 
            WHERE EXISTS (
                SELECT 1
                FROM sale_order_line t
                WHERE t.order_id = a.order_id
                AND (
                    t.bed_type = 'ICU-COVID' OR 
                    t.bed_type = 'ISOLATION DOUBLE' OR
                    t.bed_type = 'ISOLATION NICU' OR
                    t.bed_type = 'ISOLATION SINGLE' OR
                    t.bed_type = 'ISOLATION TRIPLE OR MORE' OR
                    t.bed_type = 'ISOLASI AAE' OR
                    t.bed_type = 'ISOLATION DOUBLE ANAK' OR
                    t.bed_type = 'ISOLATION DOUBLE DEWASA' OR
                    t.bed_type = 'ISOLATION GENERAL' OR
                    t.bed_type = 'ISOLATION INTENSIVE' OR
                    t.bed_type = 'ISOLATION MHJS2EXT' OR
                    t.bed_type = 'ISOLATION PENTA T2X' OR
                    t.bed_type = 'ISOLATION SINGLE ANAK' OR
                    t.bed_type = 'ISOLATION SINGLE DEWASA' OR
                    t.bed_type = 'ISOLATION TRIPLE T2X' OR
                    t.department_id LIKE '%ICU 05th TW2%'
                )
                LIMIT 1)
            AND a.is_covid is not True
            AND a.tglproses >= (CURRENT_DATE-7) 
            AND a.sync_type IN('1','2') """)

        self.env.cr.execute("""
            update sale_order_line set is_covid = False 
            where bed_type = 'ISOLATION' and is_covid ='true' and tglproses >= (CURRENT_DATE-3)
            """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET is_daycare = True 
            WHERE EXISTS (
                SELECT 1
                FROM sale_order_line t
                WHERE t.order_id = a.order_id
                AND (
                    t.bed_type = 'DAY CARE'
                )
                LIMIT 1)
            AND not EXISTS (
                        SELECT 1
                        FROM sale_order_line sol
                        where sol.order_id = a.order_id
                        AND (
                                sol.bed_type not in ('DAY CARE')
                        )
                        limit 1)
            AND a.is_daycare is not True
            AND a.tglproses >= (CURRENT_DATE-3) 
            AND a.sync_type IN('1','2')
            """)
        
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET is_icu = True 
            WHERE EXISTS (
                SELECT 1
                FROM sale_order_line t
                WHERE t.order_id = a.order_id
                AND (
                    t.bed_type LIKE '%ICU%' OR 
                    t.bed_type LIKE '%HCU%' OR 
                    t.bed_type LIKE '%ICCU%' OR 
                    t.department_id LIKE '%ICU%'
                )
                LIMIT 1)
            AND a.is_icu is not True
            AND a.tglproses >= (CURRENT_DATE-7) 
            AND a.sync_type IN('1','2') """)
        
            
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET is_consultation = True 
            WHERE EXISTS (
                SELECT 1 
                FROM sale_order_line t 
                INNER JOIN product_category t2
                    ON t2.id = t.service_categ_id 
                WHERE t2.name like '%Consultation%'
                AND t.order_id = a.order_id )
            AND a.is_consultation is not True  
            AND a.tglproses >= (CURRENT_DATE-7) 
            AND a.sync_type IN('1','2') """)

        print ("13 - Update Length of stay")
        self.env.cr.execute("""
            update sale_order_line as a 
            set length_of_stay_float = (SELECT DATE_PART('day', date(a.discharge_date)::timestamp - date(a.admit_date)::timestamp))
            where a.tglproses >= (CURRENT_DATE-7)
            AND a.sync_type IN('1','2')
            """)

        print ("14 - Update Department")
        self.env.cr.execute("""
            update sale_order_line as a 
            set department_id = null
            where a.tglproses >= (CURRENT_DATE-30)
            AND a.department_id = ''
            AND a.sync_type IN('1','2')
            """)

        self.env.cr.execute("""
            update sale_order_line set department_id = upper(department_id) where tglproses >= (CURRENT_DATE-3)
            """)


        print ("Selesai")

    # @api.multi
    def query_update_group_doctor(self):
        print ("UPDATE GROUP DOKTER")

        print ("01 - update group analytic specialist")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET
            group_analytic_doctor_id = COALESCE(b.group_doctor_id, NULL),
            group_analytic_spec_id = COALESCE(b.group_specialization_id, NULL),
            group_analytic_subspec_id = COALESCE(b.group_subspecialization_id, b.group_specialization_id)
        FROM sale_order_line sol
            LEFT JOIN LATERAL (SELECT * FROM account_analytic_account b 
            WHERE b.sync_type=sol.sync_type 
                    AND b.id=sol.account_analytic_id
                    AND b.active=True
                    ORDER BY id DESC LIMIT 1
            ) b ON 1=1
        WHERE a.id=sol.id
            AND a.sync_type in('7','3')
            AND (a.create_date >= date(current_date) - interval '30' day OR a.write_date >= date(current_date) - interval '30')
            AND (a.group_analytic_doctor_id IS NULL OR a.group_analytic_spec_id IS NULL OR a.group_analytic_subspec_id IS NULL)""")
        
        print ("02 - update group primary specialist")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET
                group_primary_doctor_id = COALESCE(c.group_doctor_id, NULL),
                group_primary_spec_id = COALESCE(c.group_specialization_id, NULL),
                group_primary_subspec_id = COALESCE(c.group_subspecialization_id, c.group_specialization_id)
            FROM sale_order_line sol
                LEFT JOIN LATERAL (SELECT * FROM account_analytic_account c 
                WHERE c.sync_type=sol.sync_type 
                        AND c.id=sol.primary_doc_id
                        AND c.active=True
                        ORDER BY id DESC LIMIT 1
                ) c ON 1=1
            WHERE a.id=sol.id
                AND a.sync_type = '7'
                AND (a.create_date >= date(current_date) - interval '30' day OR a.write_date >= date(current_date) - interval '30')
                AND (a.group_primary_doctor_id IS NULL OR a.group_primary_spec_id IS NULL OR a.group_primary_subspec_id IS NULL)
        """)
            
        print ("03 - update group perform specialist")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET
                group_perform_doctor_id = COALESCE(d.group_doctor_id, NULL),
                group_perform_spec_id = COALESCE(d.group_specialization_id, NULL),
                group_perform_subspec_id = COALESCE(d.group_subspecialization_id, d.group_specialization_id)
            FROM sale_order_line sol
                LEFT JOIN LATERAL (SELECT * FROM account_analytic_account d 
                WHERE d.sync_type=sol.sync_type 
                        AND d.id=sol.perform_doc_id
                        AND d.active=True
                        ORDER BY id DESC LIMIT 1
                ) d ON 1=1
            WHERE a.id=sol.id
                AND a.sync_type = '7'
                AND (a.create_date >= date(current_date) - interval '30' day OR a.write_date >= date(current_date) - interval '30')
                AND (a.group_perform_doctor_id IS NULL OR a.group_perform_spec_id IS NULL OR a.group_perform_subspec_id IS NULL)
        """)

        print ("04 - update group prescribe specialist")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET
                group_prescribe_doctor_id = COALESCE(e.group_doctor_id, NULL),
                group_prescribe_spec_id = COALESCE(e.group_specialization_id, NULL),
                group_prescribe_subspec_id = COALESCE(e.group_subspecialization_id, e.group_specialization_id)
            FROM sale_order_line sol
                LEFT JOIN LATERAL (SELECT * FROM account_analytic_account e 
                WHERE e.sync_type=sol.sync_type 
                        AND e.id=sol.prescribe_doc_id
                        AND e.active=True
                        ORDER BY id DESC LIMIT 1
                ) e ON 1=1
            WHERE a.id=sol.id
                AND a.sync_type = '7'
                AND (a.create_date >= date(current_date) - interval '30' day OR a.write_date >= date(current_date) - interval '30')
                AND (a.group_prescribe_doctor_id IS NULL OR a.group_prescribe_spec_id IS NULL OR a.group_prescribe_subspec_id IS NULL)
        """)

        print ("Selesai")

    # 2022.09.20 - Lepas related order_id field, lalu update jika Null
    # @api.multi
    def query_data_line_related_field(self):
        print ("Selesai Narik, Start Query UPDATE Data")

        print ("01 - Update related field")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET
                company_id = b.company_id
            FROM sale_order b 
            WHERE b.id = a.order_id
            AND a.company_id IS NULL
            AND a.tglproses >= (CURRENT_DATE-3)""")

        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET
                patient_type = b.patient_type
            FROM sale_order b 
            WHERE b.id = a.order_id
            AND a.patient_type IS NULL""")

        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET
                partner_id = b.partner_id
            FROM sale_order b 
            WHERE b.id = a.order_id
            AND a.partner_id IS NULL
            AND a.tglproses >= (CURRENT_DATE-3)""")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET
                salesman_id = b.user_id
            FROM sale_order b 
            WHERE b.id = a.order_id
            AND a.salesman_id IS NULL
            AND a.tglproses >= (CURRENT_DATE-3)""")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET
                order_partner_id = b.partner_id
            FROM sale_order b 
            WHERE b.id = a.order_id
            AND a.order_partner_id IS NULL
            AND a.tglproses >= (CURRENT_DATE-3)""")
        # self.env.cr.execute("""
        #     UPDATE sale_order_line AS a SET
        #         currency_id = b.currency_id
        #     FROM sale_order b 
        #     WHERE b.id = a.order_id
        #     AND a.currency_id IS NULL
        #     AND a.tglproses >= (CURRENT_DATE-3)""")

        print ("Selesai")


    # 2022.03.28 - Request Lanyta u/ flagging revenue covid MHSB
    # @api.multi
    def query_data_line_mhsb(self):
        print ("Selesai Narik, Start Query UPDATE Data")
        # update company_id yang null di sale.order
        self.env.cr.execute("""
            UPDATE sale_order AS a SET 
                company_id = cp.id, 
                write_date = CURRENT_TIMESTAMP 
            FROM res_company cp 
            WHERE cp.sync_type = a.sync_type
            AND a.company_id is null 
            AND date(a.confirmation_date) >= (CURRENT_DATE-5) 
            AND a.sync_type IN('3') """)

        # update company_id yang null di sale.order.bill
        self.env.cr.execute("""
            UPDATE sale_order_bill AS a SET 
                company_id = cp.id, 
                write_date = CURRENT_TIMESTAMP 
            FROM res_company cp 
            WHERE cp.sync_type = a.sync_type
            AND a.company_id is null 
            AND date(a.confirmation_date) >= (CURRENT_DATE-5) 
            AND a.sync_type IN('3') """)

        # update company_id yang null di sale.order.line
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                company_id = cp.id, 
                write_date = CURRENT_TIMESTAMP 
            FROM res_company cp 
            WHERE cp.sync_type = a.sync_type
            AND a.company_id is null 
            AND a.tglproses >= (CURRENT_DATE-5) 
            AND a.sync_type IN('3') """)


        # update group/spesialization/subspesialization
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET
                group_analytic_doctor_id = COALESCE(b.group_doctor_id, NULL),
                group_analytic_spec_id = COALESCE(b.group_specialization_id, NULL),
                group_analytic_subspec_id = COALESCE(b.group_subspecialization_id, b.group_specialization_id),
        
                group_primary_doctor_id = COALESCE(c.group_doctor_id, NULL),
                group_primary_spec_id = COALESCE(c.group_specialization_id, NULL),
                group_primary_subspec_id = COALESCE(c.group_subspecialization_id, c.group_specialization_id),

                group_perform_doctor_id = COALESCE(d.group_doctor_id, NULL),
                group_perform_spec_id = COALESCE(d.group_specialization_id, NULL),
                group_perform_subspec_id = COALESCE(d.group_subspecialization_id, d.group_specialization_id),

                group_prescribe_doctor_id = COALESCE(e.group_doctor_id, NULL),
                group_prescribe_spec_id = COALESCE(e.group_specialization_id, NULL),
                group_prescribe_subspec_id = COALESCE(e.group_subspecialization_id, e.group_specialization_id)
            FROM sale_order_line sol
            LEFT JOIN LATERAL (
                SELECT * FROM account_analytic_account b 
                WHERE b.sync_type=sol.sync_type 
                    AND b.id=sol.account_analytic_id
                    AND b.active=True
                ORDER BY id DESC LIMIT 1
            ) b ON 1=1
                
            LEFT JOIN LATERAL (
                SELECT * FROM account_analytic_account c 
                WHERE c.sync_type=sol.sync_type 
                    AND c.id=sol.primary_doc_id
                    AND c.active=True
                ORDER BY id DESC LIMIT 1
            ) c ON 1=1
                
            LEFT JOIN LATERAL (
                SELECT * FROM account_analytic_account d 
                WHERE d.sync_type=sol.sync_type 
                    AND d.id=sol.perform_doc_id
                    AND d.active=True
                ORDER BY id DESC LIMIT 1
            ) d ON 1=1
                
            LEFT JOIN LATERAL (
                SELECT * FROM account_analytic_account e 
                WHERE e.sync_type=sol.sync_type 
                    AND e.id=sol.prescribe_doc_id
                    AND e.active=True
                ORDER BY id DESC LIMIT 1
            ) e ON 1=1
            WHERE a.id=sol.id
                AND a.sync_type in ('3')
                AND a.tglproses >= (CURRENT_DATE-3) 
                AND a.tglproses <= (CURRENT_DATE-3)     
        """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                is_covid = True, 
                write_date = CURRENT_TIMESTAMP 
            WHERE a.tglproses >= (CURRENT_DATE-5) 
            AND a.is_covid is not True
            AND a.sync_type IN('3')
            AND EXISTS (
                SELECT 1 
                FROM sale_order_line t
                INNER JOIN product_product pp ON pp.id = t.product_id
                INNER JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE t.order_id = a.order_id
                AND (t.department_id ILIKE '%WARD%L11%'
                    OR pt.name like '%Emergency Observation Room < 6 Hours Isolation%'
                    OR pt.name like '%Emergency Observation Room >= 6 Hours Isolation%'
                    OR pt.name like '%IGD Transit < 6 Hours%'
                    OR pt.name like '%IGD Transit >= 6 Hours %'
                ) LIMIT 1
            ) """)

        # self.env.cr.execute("""
        #     update sale_order_line set is_covid = false 
        #     where tglproses >='2022-01-01' 
        #     and tglproses <='2022-02-02' 
        #     and is_covid = true """)
        
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                is_icu = True, 
                write_date = CURRENT_TIMESTAMP 
            WHERE a.is_icu is not True
            AND a.tglproses >= (CURRENT_DATE-5) 
            AND a.sync_type IN('3')
            AND EXISTS (
                SELECT 1 
                FROM sale_order_line t
                INNER JOIN product_product pp ON pp.id = t.product_id
                INNER JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE t.order_id = a.order_id
                AND (t.department_id LIKE '%ICU%' 
                    OR pt.name LIKE '%ICU%'
                ) LIMIT 1
            ) """)
        
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                is_isoman = True, 
                write_date = CURRENT_TIMESTAMP 
            WHERE a.is_isoman is not True
            AND a.tglproses >= (CURRENT_DATE-5) 
            AND a.sync_type IN('3')
            AND EXISTS (
                SELECT 1 
                FROM sale_order_line t
                INNER JOIN product_product pp ON pp.id = t.product_id
                INNER JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE t.order_id = a.order_id
                AND (
                    trim(pt.name) ilike '%Hotel Facility Covid 19%' OR
                    trim(pt.name) ilike '%Minimum Charge Hotel Facility Covid 19%' OR
                    trim(pt.name) ilike '%Hotel Facility Covid 19 - Hotel Oyo%' OR 
                    trim(t.department_id) ilike '%ISOMAN RUMAH%'
                )
                LIMIT 1
            ) """)

        # update special group 2 haemodialisa dan medical rehab
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                special_group2 ='MEDICAL REHABILITATION',
                revenue_type ='LOS' 
            WHERE a.tglproses >= (CURRENT_DATE-2) 
            and (a.department_id ='Rehabilitation Medic' or a.department_id = 'Rehabilitasi Medis' or a.department_id = 'Rehabilitasi Medik')
            AND a.sync_type IN('3')
            
            """)
        #update special group2 ke pharmacy apabila service category consumables
        self.env.cr.execute("""
            UPDATE sale_order_line as sol set
                special_group2 = 'PHARMACY OUTPATIENT'
                FROM product_category pc
                WHERE pc.id = sol.service_categ_id
                and pc.name = 'Consumables'
                and sol.special_group2 = 'MEDICAL REHABILITATION'
                and sol.patient_group = 'OPD'
                and sol.tglproses >= (CURRENT_DATE-2) 
                AND sol.sync_type IN('3')
            """)
        #update special group2 ke pharmacy apabila service category consumables
        self.env.cr.execute("""
            UPDATE sale_order_line as sol set
                special_group2 = 'PHARMACY INPATIENT'
                FROM product_category pc
                WHERE pc.id = sol.service_categ_id
                and pc.name = 'Consumables'
                and sol.special_group2 = 'MEDICAL REHABILITATION'
                and sol.patient_group = 'IPD'
                and sol.tglproses >= (CURRENT_DATE-2)
                AND sol.sync_type IN('3') 
            
            """)

        # print ("12 - Update is_akasia di MHSB apabila department mengandung kata AKASIA")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET is_akasia = True 
            WHERE EXISTS (
                SELECT 1 
                FROM sale_order_line t 
                WHERE t.department_id like '%AKASIA%'
                AND t.order_id = a.order_id )
            AND a.is_surgery is not True  
            AND a.tglproses >= (CURRENT_DATE-5) 
            AND a.sync_type IN('3') """)

        print ("Selesai")

    
    # 2021.06.16 - Request Lanyta u/ flagging revenue covid MHKN
    # @api.multi
    def query_data_line_mhkn(self):
        print ("Selesai Narik, Start Query UPDATE Data")
        # update company_id yang null di sale.order
        self.env.cr.execute("""
            UPDATE sale_order AS a SET 
                company_id = cp.id, 
                write_date = CURRENT_TIMESTAMP 
            FROM res_company cp 
            WHERE cp.sync_type = a.sync_type
            AND a.company_id is null 
            AND date(a.confirmation_date) >= (CURRENT_DATE-7) 
            AND a.sync_type IN('6') """)

        # update company_id yang null di sale.order.bill
        self.env.cr.execute("""
            UPDATE sale_order_bill AS a SET 
                company_id = cp.id, 
                write_date = CURRENT_TIMESTAMP 
            FROM res_company cp 
            WHERE cp.sync_type = a.sync_type
            AND a.company_id is null 
            AND date(a.confirmation_date) >= (CURRENT_DATE-7) 
            AND a.sync_type IN('6') """)

        # update company_id yang null di sale.order.line
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                company_id = cp.id, 
                write_date = CURRENT_TIMESTAMP 
            FROM res_company cp 
            WHERE cp.sync_type = a.sync_type
            AND a.company_id is null 
            AND a.tglproses >= (CURRENT_DATE-7) 
            AND a.sync_type IN('6') """)


        # update group/spesialization/subspesialization
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET
                group_analytic_doctor_id = COALESCE(b.group_doctor_id, NULL),
                group_analytic_spec_id = COALESCE(b.group_specialization_id, NULL),
                group_analytic_subspec_id = COALESCE(b.group_subspecialization_id, b.group_specialization_id),
        
                group_primary_doctor_id = COALESCE(c.group_doctor_id, NULL),
                group_primary_spec_id = COALESCE(c.group_specialization_id, NULL),
                group_primary_subspec_id = COALESCE(c.group_subspecialization_id, c.group_specialization_id),

                group_perform_doctor_id = COALESCE(d.group_doctor_id, NULL),
                group_perform_spec_id = COALESCE(d.group_specialization_id, NULL),
                group_perform_subspec_id = COALESCE(d.group_subspecialization_id, d.group_specialization_id),

                group_prescribe_doctor_id = COALESCE(e.group_doctor_id, NULL),
                group_prescribe_spec_id = COALESCE(e.group_specialization_id, NULL),
                group_prescribe_subspec_id = COALESCE(e.group_subspecialization_id, e.group_specialization_id)
            FROM sale_order_line sol
            LEFT JOIN LATERAL (
                SELECT * FROM account_analytic_account b 
                WHERE b.sync_type=sol.sync_type 
                    AND b.id=sol.account_analytic_id
                    AND b.active=True
                ORDER BY id DESC LIMIT 1
            ) b ON 1=1
                
            LEFT JOIN LATERAL (
                SELECT * FROM account_analytic_account c 
                WHERE c.sync_type=sol.sync_type 
                    AND c.id=sol.primary_doc_id
                    AND c.active=True
                ORDER BY id DESC LIMIT 1
            ) c ON 1=1
                
            LEFT JOIN LATERAL (
                SELECT * FROM account_analytic_account d 
                WHERE d.sync_type=sol.sync_type 
                    AND d.id=sol.perform_doc_id
                    AND d.active=True
                ORDER BY id DESC LIMIT 1
            ) d ON 1=1
                
            LEFT JOIN LATERAL (
                SELECT * FROM account_analytic_account e 
                WHERE e.sync_type=sol.sync_type 
                    AND e.id=sol.prescribe_doc_id
                    AND e.active=True
                ORDER BY id DESC LIMIT 1
            ) e ON 1=1
            WHERE a.id=sol.id
                AND a.sync_type in ('6')
                AND a.tglproses >= (CURRENT_DATE-3) 
                AND a.tglproses <= (CURRENT_DATE-3)     
        """)


        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                is_covid = True, 
                write_date = CURRENT_TIMESTAMP 
            WHERE a.tglproses >= (CURRENT_DATE-10) 
            AND a.is_covid is not True
            AND a.sync_type IN('6')
            AND EXISTS (
                SELECT 1 
                FROM sale_order_line t
                INNER JOIN product_product pp ON pp.id = t.product_id
                INNER JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE t.order_id = a.order_id
                AND (t.department_id ILIKE '%WARD%L8%'
                    OR pt.name like '%Emergency Observation Room < 6 Hours Isolation%'
                    OR pt.name like '%Emergency Observation Room >= 6 Hours Isolation%'
                    OR pt.name like '%IGD Transit < 6 Hours%'
                    OR pt.name like '%IGD Transit >= 6 Hours %'
                ) LIMIT 1
            ) """)

        # self.env.cr.execute("""
        #     update sale_order_line set is_covid = false 
        #     where tglproses >='2022-01-01' 
        #     and tglproses <='2022-02-02' 
        #     and is_covid = true """)
        
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                is_icu = True, 
                write_date = CURRENT_TIMESTAMP 
            WHERE a.is_icu is not True
            AND a.tglproses >= (CURRENT_DATE-7) 
            AND a.sync_type IN('6')
            AND EXISTS (
                SELECT 1 
                FROM sale_order_line t
                INNER JOIN product_product pp ON pp.id = t.product_id
                INNER JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE t.order_id = a.order_id
                AND (t.department_id LIKE '%ICU%' 
                    OR pt.name LIKE '%ICU%'
                ) LIMIT 1
            ) """)
        
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                is_isoman = True, 
                write_date = CURRENT_TIMESTAMP 
            WHERE a.is_isoman is not True
            AND a.tglproses >= (CURRENT_DATE-7) 
            AND a.sync_type IN('6')
            AND EXISTS (
                SELECT 1 
                FROM sale_order_line t
                INNER JOIN product_product pp ON pp.id = t.product_id
                INNER JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE t.order_id = a.order_id
                AND (
                    trim(pt.name) ilike '%Hotel Facility Covid 19%' OR
                    trim(pt.name) ilike '%Minimum Charge Hotel Facility Covid 19%' OR
                    trim(pt.name) ilike '%Hotel Facility Covid 19 - Hotel Oyo%' OR 
                    trim(t.department_id) ilike '%ISOMAN RUMAH%'
                )
                LIMIT 1
            ) """)

        # update special group 2 haemodialisa dan medical rehab
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                special_group2 ='MEDICAL REHABILITATION',
                revenue_type ='LOS' 
            WHERE a.tglproses >= (CURRENT_DATE-2) 
            and a.department_id ='REHABILITASI MEDIK'
            AND a.sync_type IN('6')
            
            """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                special_group2 ='HAEMODIALYSIS',
                revenue_type ='LOS' 
            WHERE a.tglproses >= (CURRENT_DATE-2) 
            and a.department_id ='HAEMODIALISA'
            AND a.sync_type IN('6')
            
            """)

        print ("Selesai")





    # @api.multi
    def query_data_line_mhbg(self):
        print ("Selesai Narik, Start Query UPDATE Data")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                special_group2 ='HAEMODIALYSIS',
                revenue_type ='LOS' 
            WHERE a.tglproses >= (CURRENT_DATE-2) 
            and a.department_id ='HEMODIALISA'
            AND a.sync_type IN('7') """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                special_group2 ='MEDICAL REHABILITATION',
                revenue_type ='LOS' 
            WHERE a.tglproses >= (CURRENT_DATE-2) 
            and (a.department_id ='REHABILITASI MEDIC' or a.department_id = 'Rehab Medik')
            AND a.sync_type IN('7') """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET
                revenue_type ='LOS' 
            WHERE a.tglproses >= (CURRENT_DATE-2) 
            and a.revenue_type ='LOB'
            and a.special_group2 = 'LABORATORY'
            AND a.sync_type IN('7') """)


    # @api.multi
    def query_data_line_mhbd(self):
        print ("Selesai Narik, Start Query UPDATE Data")
        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET
                revenue_type ='LOS' 
            WHERE a.tglproses >= (CURRENT_DATE-2) 
            and a.revenue_type ='LOB'
            and a.special_group2 = 'RADIOLOGY'
            AND a.sync_type IN('8') """)

        self.env.cr.execute("""
            UPDATE sale_order_line AS a SET 
                special_group2 ='MEDICAL REHABILITATION',
                revenue_type ='LOS' 
            WHERE a.tglproses >= (CURRENT_DATE-2) 
            and (a.department_id ='REHABILITATION MEDIC' or a.department_id = 'REHABILITATION MEDIC LT.2')
            AND a.sync_type IN('8') """)






    # @api.multi
    def query_cost(self):
        print ("1")

        self.env.cr.execute("""
            UPDATE sale_order_line AS line 
            SET cost_total = line.cost_unit * line.product_uom_qty 
            FROM product_category categ
            WHERE categ.id = line.service_categ_id
            AND categ.name in ('Pharmacy','Consumables','Consumable','Drugs')
            AND line.cost_total is null
            AND line.tglproses >= (CURRENT_DATE - '5 days'::interval)""")
        
        self.env.cr.execute("""
            UPDATE sale_order_line AS line 
            SET cost_date = line.order_date 
            FROM product_category categ
            WHERE categ.id = line.service_categ_id
            AND categ.name in ('Pharmacy','Consumables','Consumable','Drugs')
            AND line.cost_date is null
            AND line.tglproses >= (CURRENT_DATE - '5 days'::interval)""")
            
      

    # 2021.06.09
    # define function untuk takeout revenue, u/ selain AAE & IPD tidak ada ACCRUAL
    # @api.multi
    def query_takeout(self):
        
        print ("flag for ACCRUAL NON EMERGENCY & NON IPD")
        query = """
            UPDATE sale_order_line AS a SET is_takeout = True
            WHERE a.type_line in ('ACCRUAL','ACCRUAL REVERSAL')
            AND a.is_takeout IS NOT TRUE
            AND a.patient_type NOT IN ('2','3')
        """
        self.sudo().env.cr.execute(query)

        print ("flag for BILLING")
        query = """
            UPDATE sale_order_line AS a SET is_takeout = False
            WHERE a.type_line in ('BILL','BILLING','BILL CANCEL','BILLING CANCEL','DISCOUNT','DISCOUNT CANCEL')
            AND a.is_takeout IS NULL
        """
        self.sudo().env.cr.execute(query)

        print ("flag for ACCRUAL EMERGENCY & IPD")
        query = """
            UPDATE sale_order_line AS a SET is_takeout = False
            WHERE a.type_line in ('ACCRUAL','ACCRUAL REVERSAL')
            AND a.is_takeout IS NULL
            AND a.patient_type IN ('2','3')
        """
        self.env.cr.execute(query)

    # @api.one
    def _compute_delivered(self):
        for line in self:
            print("Do something..")
            # self.qty_delivered = sum(record.product_qty if record.picking_id.check_in_out() else - record.product_qty for record in self.env['stock.pack.operation'].sudo().search([('picking_id', 'in', self.order_id.picking_ids.ids), ('product_id', '=', self.product_id.id), ('picking_id.state', '=', 'done')]))
            # self.qty_to_invoice = self.qty_delivered if self.product_id.invoice_policy == 'delivery' else self.product_uom_qty



    # @api.one
    def _compute_delivered(self):
        print("Do something..")
        # self.qty_delivered = sum(record.product_qty if record.picking_id.check_in_out() else - record.product_qty for record in self.env['stock.pack.operation'].sudo().search([('picking_id', 'in', self.order_id.picking_ids.ids), ('product_id', '=', self.product_id.id), ('picking_id.state', '=', 'done')]))
        # self.qty_to_invoice = self.qty_delivered if self.product_id.invoice_policy == 'delivery' else self.product_uom_qty


    @api.model
    def _sync_sale_line_wipro_ip(self, sync_type='1', admission_ids=[]):
        # sync_ids = {record['sync_id']: record['id'] for record in self.sudo().search_read([('sync_type', '=', sync_type), ('sync_id', '>', 0)], ['id', 'sync_id'])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
        data = []
        date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
        # date = '2019-01-25'

        accrual_daily = """
            SELECT 
                a.TglProses 'tglproses',
                (convert(varchar(max), concat(convert(int, getdate()), 1, a.AdmissionID, a.ServiceID, a.OrderID, a.OrderItemID, a.ServiceItemID)))  'sync_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.AdmissionID 'order_id',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.RecordType 'type_line',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (CASE WHEN a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses = '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.PatientType='InPatient'
                and a.recordType in('ACCRUAL')
                and not exists (
                    select top 1 1
                    from dbo.V_Db_A_A_RawDataH30 t
                    where t.tglproses=a.tglproses
                        and t.PatientType='InPatient'
                        and t.recordType in('ACCRUAL REVERSAL')
                        and t.AdmissionID=a.AdmissionID
                        and t.ServiceID=a.ServiceID
                        and t.OrderID=a.OrderID
                        and t.OrderItemID=a.OrderItemID 
                        and t.Value=(-1*a.Value)
                )""" % (date)
        print (accrual_daily)
        data += sync.get_data(sync.servers.get(sync_type), accrual_daily)

        accrual_reversal_daily = """
            SELECT 
                a.TglProses 'tglproses',
                (convert(varchar(max), concat(convert(int, getdate()), 2, a.AdmissionID, a.OrderID, a.ServiceID, a.ServiceItemID, a.OrderItemID)))  'sync_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.RecordType 'type_line',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses = '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366)
                and a.PatientType='InPatient'
                and a.recordType in('ACCRUAL REVERSAL')
                and not exists (
                    select top 1 1
                    from dbo.V_Db_A_A_RawDataH30 t
                    where t.tglproses=a.tglproses
                        and t.PatientType='InPatient'
                        and t.recordType in('ACCRUAL')
                        and t.AdmissionID=a.AdmissionID
                        and t.ServiceID=a.ServiceID
                        and t.OrderID=a.OrderID
                        and t.OrderItemID=a.OrderItemID 
                        and t.Value=(-1*a.Value)) """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), accrual_reversal_daily)

        bill_service_item = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 3, a.AdmissionID, a.ServiceItemID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'service_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.RecordType 'type_line',
                a.DepartmentID 'location_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                b.BillNo 'billno',
                b.BillID 'billing_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 A
            outer apply (
                select top 1 b.*
                from dbo.V_Db_A_A_RawDataH30 b
                where b.TglProses=a.TglProses
                    and b.PatientType=a.PatientType
                    and b.AdmissionID=a.AdmissionID
                    and b.RecordType='BILL'
                order by a.BillID asc
                ) AS b
                where a.tglproses = '%s'
                -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                    and (a.ServiceID <> 10 AND a.ServiceID <> 17)
                    and a.RecordType in('BILL')
                    and a.PatientType = 'InPatient'""" % (date)
        data += sync.get_data(sync.servers.get(sync_type), bill_service_item)

        bill_item = """
            SELECT 
                a.TglProses 'tglproses',
                convert(varchar(max), concat(convert(int, a.TglProses), 3, a.AdmissionID, a.ServiceItemID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'service_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.RecordType 'type_line',
                a.DepartmentID 'location_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                b.BillNo 'billno',
                b.BillID 'billing_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            outer apply (
                select top 1 b.*
                from dbo.V_Db_A_A_RawDataH30 b
                where b.TglProses=a.TglProses
                    and b.PatientType=a.PatientType
                    and b.AdmissionID=a.AdmissionID
                    and b.RecordType='BILL'
                order by a.BillID asc
                ) AS b
                where a.tglproses = '%s'
                -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                    and (a.ServiceID = 10 OR a.ServiceID = 17)
                    and a.RecordType = 'BILL'
                    and a.PatientType = 'InPatient'
                """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), bill_item)

        bill_discount = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 5, a.AdmissionID, a.DiscountSLNo, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID, a.DepartmentID, a.ServiceItemID)) 'sync_id',
                a.ServiceID 'service_id',
                99881177 'product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.AdmissionID 'order_id',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses = '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.RecordType = 'DISCOUNT'
                and a.PatientType = 'InPatient'
            """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), bill_discount)

        bill_discount_cancel = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar, concat(convert(int, a.TglProses), 6, a.AdmissionID, a.DiscountSLNo, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID, a.DepartmentID, a.ServiceItemID)) 'sync_id',
                a.ServiceID 'service_id',
                99881177 'product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses = '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.RecordType = 'DISCOUNT CANCEL'
                and a.PatientType = 'InPatient'
            """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), bill_discount_cancel)

        bill_cancel = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 4, a.AdmissionID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'service_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses = '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.RecordType = 'BILL CANCEL'
                and a.PatientType = 'InPatient'
            """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), bill_cancel)

        print (data)
        if not data:
            print ("No data available")
            return
        fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and 'ids' not in key and self._fields[key].required == True and self._fields[key].store == True)
        columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
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
        now = tools.datetime.now().strftime('%Y%m%d %H:%M:%S')
        dbname = self.env.cr.dbname
        login = self.sudo().env.user.login
        import odoorpc
        request = odoorpc.ODOO('localhost', port=8085, timeout=100000000000)
        request.login(dbname, login, 'mayapada@hospital2018')
        env = request.env

        #uom_id = self.env.ref('product.product_uom_categ_unit').id
        #new_sync_ids = []
        #@asyncio.coroutine
        def process_query(object, result):
            object['sync_id'] = float(object['sync_id'])
            #new_sync_ids += [object['sync_id']]
            for value in default_values:
                object[value] = default_values[value]
            # print ("Insert SO")
            order_id = object['order_id']
            object['order_id'] = env['sale.order'].search([('sync_id', '=', object['order_id']), ('sync_type', '=', sync_type)], limit=1)
            if not object['order_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + " sale.order with sync_id %s and sync_type %s doesn't exist" % (order_id, sync_type))
                return
            # print ("Insert Product")
            # object['product_id'] = env['product.product'].search([('sync_id', '=', object['product_id']), ('sync_type', '=', sync_type)], limit=1) if object['product_id'] != 655 else env['product.product'].search([('name', 'ilike', 'administrative charges')], order="id asc", limit=1)
            product_id = object['product_id']
            object['product_id'] = env['product.template'].search([('sync_id', '=', object['product_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1)
            object['product_id'] = env['product.product'].search([('product_tmpl_id', '=', object['product_id'])], order="id asc", limit=1)
            if not object['product_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + " product.template with sync_id %s and sync_type %s doesn't exist" % (product_id, sync_type))
                return
            # object['product_id'] = env['product.product'].browse(object['product_id'])
            object['name'] = object['name'] or "DISCOUNT"

            # 2021.10.11 - product_categ_id based type of services
            if object['product_categ_id'] and object['service_categ_id'] in [10,17]:
                object['product_categ_id'] = env['product.category'].search([('sync_id', '=', object['product_categ_id']), ('sync_type', '=', sync_type), ('sync_is_category', '=', True)], order="id asc", limit=1) or None
            else:
                object['product_categ_id'] = env['product.category'].search([('sync_id', '=', object['product_categ_id']), ('sync_type', '=', sync_type), ('sync_is_surgery', '=', True)], order="id asc", limit=1) or None

            # print "Insert Service"
            object['service_categ_id'] = env['product.category'].search([('sync_id', '=', object['service_categ_id']), ('sync_type', '=', sync_type), ('sync_is_service', '=', True)], order="id asc", limit=1) or None
            # object['name'] = object['product_id'].name
            # print ("Insert UOM")
            object['product_uom'] = env['product.uom'].search([('sync_id', '=', object['product_uom']), ('sync_type', '=', sync_type)], order="id asc", limit=1) or env['product.uom'].search([('sync_id', '=', 163), ('sync_type', '=', sync_type)], order="id asc", limit=1)
            # #print ("Insert Product Lagi")
            # object['product_id'] = object['product_id'].id
            # print ("Insert Doctor")
            # c = False
            # if object['account_analytic_id'] == 1215: c = True
            object['account_analytic_id'] = env['account.analytic.account'].search([('sync_id', '=', object['account_analytic_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['account_analytic_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            # if c: print '\n\n\n\n\n\n\n', object['account_analytic_id'], sync_type
            object['prescribe_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['prescribe_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['prescribe_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            object['perform_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['perform_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['perform_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            object['primary_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            # print ("Insert Location")
            object['location_id'] = env['stock.location'].search([('sync_id', '=', object['location_id']), ('sync_type', '=', sync_type)],limit=1) or None
            # print ("Insert Payer")
            object['payer'] = env['res.partner'].search([('sync_id', '=', object['payer']), ('sync_type', '=', sync_type), ('insurance', '=', True)], limit=1) or None
            # print ("Insert Bed Name")
            if object['discount_id']:
                object['discount_id'] = env['hospital.discount.type'].search([('sync_id', '=', object['discount_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['tariff_id']:
                object['tariff_id'] = env['hospital.tariff'].search([('sync_id', '=', object['tariff_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['room_id']:
                object['room_id'] = env['hospital.room.name'].search([('sync_id', '=', object['room_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['bed_id']:
                object['bed_id'] = env['hospital.bed.name'].search([('sync_id', '=', object['bed_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['bed_type_id']:
                object['bed_type_id'] = env['hospital.bed.type'].search([('sync_id', '=', object['bed_type_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['eligible_bed_type_id']:
                object['eligible_bed_type_id'] = env['hospital.bed.type'].search([('sync_id', '=', object['eligible_bed_type_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['alloted_bed_type_id']:
                object['alloted_bed_type_id'] = env['hospital.bed.type'].search([('sync_id', '=', object['alloted_bed_type_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['referral_id']:
                object['referral_id'] = env['referral.transaction'].search([('sync_id', '=', object['referral_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['billing_id']:
                object['billing_id'] = env['sale.order.bill'].search([('sync_id', '=', object['billing_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['referral_doc_id']:
                object['referral_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['referral_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or None
            
            # if object['sync_id'] and object['sync_id'] in sync_ids:
            #    return
            #    object['id'] = sync_ids[object['sync_id']]
            # else:
            object['id'] = 'DEFAULT'
            object['sync_date'] = now
            # print ("Insert Sync Type")
            object['sync_type'], object['company_id'] = sync_type, env['res.company'].search([('sync_type', '=', sync_type)], limit=1)
            #if values:
            #   values += ', '
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
                if type(object[field]) in [list, tuple] and len(object[field]) == 1:
                    object[field] = object[field][0]
                value += sync.json(object[field])
            value += ')'
            result += [value]
            #return value
            #values += value

        #loop = asyncio.get_event_loop()
        #tasks = [asyncio.create_task(process_query(object)) for object in data]
        #for result in loop.run_until_complete(asyncio.gather(*tasks)):
        #    if result:
        #       if values:
        #          values += ', '
        #       values += result
        processes = []
        result = list()
        try:
            result = Manager().list()
        except:
            pass
        for chunk in sync.split_list(data, sync.cpu_count * 2):
            process = Process(
                target=lambda chunk, result:
                [process_query(object, result) for object in chunk],
                args=(chunk, result))
            process.start()
            processes += [process]
        for process in processes:
            process.join()
        values = ', '.join(result)
        excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        columns = sync.remove_unicode(str(fields)).replace("'", "")
        columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        print (values.encode('utf-8'))
        if not values:
            print ("No values available")
            return
        # print "Insert ALL DATA"
        query = "INSERT into sale_order_line %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)
        self.env.cr.execute("""
            UPDATE sale_order_line
            SET price_total = price_subtotal 
            WHERE price_total is null""")
        self.env.cr.execute("""
            UPDATE sale_order
            SET amount_total = (select sum(price_total)
                from sale_order_line where order_id = sale_order.id and type_line in ('BILL', 'BILL CANCEL', 'DISCOUNT', 'DISCOUNT CANCEL')) 
            WHERE amount_total is null""")
        self.env.cr.execute("""
            UPDATE sale_order
            SET amount_untaxed = (select sum(price_total)
                from sale_order_line where order_id = sale_order.id and type_line in ('BILL', 'BILL CANCEL', 'DISCOUNT', 'DISCOUNT CANCEL')) 
            WHERE amount_untaxed is null""")
        self.env.cr.execute("""
            UPDATE sale_order
            SET payer_amount = amount_total 
            WHERE payer_amount is null""")

    @api.model
    def _sync_sale_line_wipro_op_emerg(self, sync_type='1', admission_ids=[]):
        #import trollius as asyncio
        # sync_ids = {record['sync_id']: record['id'] for record in self.sudo().search_read([('sync_type', '=', sync_type), ('sync_id', '>', 0)], ['id', 'sync_id'])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
        data = []
        date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
        # date = '2019-01-25'
        #DEDUCTION

        bill_discount = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 5, a.AdmissionID, a.DiscountSLNo, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID, a.DepartmentID, a.ServiceItemID)) 'sync_id',
                a.ServiceID 'service_id',
                99881177 'product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.DepartmentID 'location_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.RecordType = 'DISCOUNT'
            and a.tglproses = '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType <> 'InPatient'
                and a.AdmissionID is not null
            """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), bill_discount)

        bill_discount_cancel = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 6, a.AdmissionID, a.DiscountSLNo, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID, a.DepartmentID, a.ServiceItemID)) 'sync_id',
                a.ServiceID 'service_id',
                99881177 'product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 A
            WHERE a.RecordType = 'DISCOUNT CANCEL'
            and a.tglproses = '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.PatientType <> 'InPatient'
                and a.AdmissionID is not null
            """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), bill_discount_cancel)

        bill_cancel = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 4, a.AdmissionID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'service_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.AdmissionID 'order_id',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            WHERE a.RecordType = 'BILL CANCEL'
            and a.tglproses = '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.PatientType <> 'InPatient'
                and a.AdmissionID is not null
            """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), bill_cancel)

        bill_op = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 3, a.AdmissionID, a.ServiceItemID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'service_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            FROM dbo.V_Db_A_A_RawDataH30 a
            WHERE a.RecordType = 'BILL'
            and a.tglproses = '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType <> 'InPatient'
                and a.AdmissionID is not null
            """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), bill_op)

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
                'sync_date', 'sync_type', 'company_id') if data else ()
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
        now = tools.datetime.now().strftime('%Y%m%d %H:%M:S')
        dbname = self.env.cr.dbname
        login = self.sudo().env.user.login
        import odoorpc
        request = odoorpc.ODOO('localhost', port=8085, timeout=100000000000)
        request.login(dbname, login, 'mayapada@hospital2018')
        env = request.env

        #uom_id = self.env.ref('product.product_uom_categ_unit').id
        #new_sync_ids = []
        #@asyncio.coroutine
        def process_query(object, result):
            object['sync_id'] = float(object['sync_id'])
            #new_sync_ids += [object['sync_id']]
            for value in default_values:
                object[value] = default_values[value]
            # print ("Insert SO")
            order_id = object['order_id']
            object['order_id'] = env['sale.order'].search([('sync_id', '=', object['order_id']), ('sync_type', '=', sync_type)], limit=1)
            if not object['order_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + " sale.order with sync_id %s and sync_type %s doesn't exist" % (order_id, sync_type))
                return
            # print ("Insert Product")
            # object['product_id'] = env['product.product'].search([('sync_id', '=', object['product_id']), ('sync_type', '=', sync_type)], limit=1) if object['product_id'] != 655 else env['product.product'].search([('name', 'ilike', 'administrative charges')], order="id asc", limit=1)
            product_id = object['product_id']
            object['product_id'] = env['product.template'].search([('sync_id', '=', object['product_id']), ('sync_type', '=', sync_type)], limit=1)
            object['product_id'] = env['product.product'].search([('product_tmpl_id', '=', object['product_id'])], limit=1)
            if not object['product_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + " product.template with sync_id %s and sync_type %s doesn't exist" % (product_id, sync_type))
                return
            # object['product_id'] = env['product.product'].browse(object['product_id'])
            object['name'] = object['name'] or "DISCOUNT"

            # 2021.10.11 - product_categ_id based type of services
            if object['product_categ_id'] and object['service_categ_id'] in [10,17]:
                object['product_categ_id'] = env['product.category'].search([('sync_id', '=', object['product_categ_id']), ('sync_type', '=', sync_type), ('sync_is_category', '=', True)], limit=1) or None
            else:
                object['product_categ_id'] = env['product.category'].search([('sync_id', '=', object['product_categ_id']), ('sync_type', '=', sync_type), ('sync_is_surgery', '=', True)], limit=1) or None

            # print ("Insert Service")
            object['service_categ_id'] = env['product.category'].search([('sync_id', '=', object['service_categ_id']), ('sync_type', '=', sync_type), ('sync_is_service', '=', True)], limit=1) or None
            # object['name'] = object['product_id'].name
            # print ("Insert UOM")
            object['product_uom'] = env['product.uom'].search([('sync_id', '=', object['product_uom']), ('sync_type', '=', sync_type)], limit=1) or env['product.uom'].search([('sync_id', '=', 163), ('sync_type', '=', sync_type)], limit=1)
            # #print ("Insert Product Lagi")
            # object['product_id'] = object['product_id'].id
            # print ("Insert Doctor")
            # c = False
            # if object['account_analytic_id'] == 1215: c = True
            object['account_analytic_id'] = env['account.analytic.account'].search([('sync_id', '=', object['account_analytic_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['account_analytic_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            # if c: print '\n\n\n\n\n\n\n', object['account_analytic_id'], sync_type
            object['prescribe_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['prescribe_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['prescribe_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            object['perform_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['perform_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['perform_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            object['primary_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            # print "Insert Location"
            object['location_id'] = env['stock.location'].search([('sync_id', '=', object['location_id']), ('sync_type', '=', sync_type)],limit=1) or None
            # print "Insert Payer"
            object['payer'] = env['res.partner'].search([('sync_id', '=', object['payer']), ('sync_type', '=', sync_type), ('insurance', '=', True)], limit=1) or None
            # print "Insert Bed Name"
            if object['discount_id']:
                object['discount_id'] = env['hospital.discount.type'].search([('sync_id', '=', object['discount_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['tariff_id']:
                object['tariff_id'] = env['hospital.tariff'].search([('sync_id', '=', object['tariff_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['room_id']:
                object['room_id'] = env['hospital.room.name'].search([('sync_id', '=', object['room_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['bed_id']:
                object['bed_id'] = env['hospital.bed.name'].search([('sync_id', '=', object['bed_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['bed_type_id']:
                object['bed_type_id'] = env['hospital.bed.type'].search([('sync_id', '=', object['bed_type_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['eligible_bed_type_id']:
                object['eligible_bed_type_id'] = env['hospital.bed.type'].search([('sync_id', '=', object['eligible_bed_type_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['alloted_bed_type_id']:
                object['alloted_bed_type_id'] = env['hospital.bed.type'].search([('sync_id', '=', object['alloted_bed_type_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['referral_id']:
                object['referral_id'] = env['referral.transaction'].search([('sync_id', '=', object['referral_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['billing_id']:
                object['billing_id'] = env['sale.order.bill'].search([('sync_id', '=', object['billing_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['referral_doc_id']:
                object['referral_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['referral_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or None
            
            # if object['sync_id'] and object['sync_id'] in sync_ids:
            #    return
            #    object['id'] = sync_ids[object['sync_id']]
            # else:
            object['id'] = 'DEFAULT'
            object['sync_date'] = now
            # print "Insert Sync Type"
            object['sync_type'], object['company_id'] = sync_type, env['res.company'].search([('sync_type', '=', sync_type)], limit=1)
            #if values:
            #   values += ', '
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
                if type(object[field]) in [list, tuple] and len(
                        object[field]) == 1:
                    object[field] = object[field][0]
                value += sync.json(object[field])
            value += ')'
            result += [value]
            #return value
            #values += value

        #loop = asyncio.get_event_loop()
        #tasks = [asyncio.create_task(process_query(object)) for object in data]
        #for result in loop.run_until_complete(asyncio.gather(*tasks)):
        #    if result:
        #       if values:
        #          values += ', '
        #       values += result
        processes = []
        result = list()
        try:
            result = Manager().list()
        except:
            pass
        for chunk in sync.split_list(data, sync.cpu_count * 2):
            process = Process(
                target=lambda chunk, result:
                [process_query(object, result) for object in chunk],
                args=(chunk, result))
            process.start()
            processes += [process]
        for process in processes:
            process.join()
        values = ', '.join(result)
        excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        columns = sync.remove_unicode(str(fields)).replace("'", "")
        columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        print (values.encode('utf-8'))
        if not values:
            print ("No data available")
            return
        query = "INSERT into sale_order_line %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)
        self.env.cr.execute("""
            UPDATE sale_order_line
            SET price_total = price_subtotal 
            WHERE price_total is null""")
        self.env.cr.execute("""
            UPDATE sale_order
            SET amount_total = (select sum(price_total)
                from sale_order_line where order_id = sale_order.id and type_line in ('BILL', 'BILL CANCEL', 'DISCOUNT', 'DISCOUNT CANCEL')) 
            WHERE amount_total is null""")
        self.env.cr.execute("""
            UPDATE sale_order
            SET amount_untaxed = (select sum(price_total)
                from sale_order_line where order_id = sale_order.id and type_line in ('BILL', 'BILL CANCEL', 'DISCOUNT', 'DISCOUNT CANCEL')) 
            WHERE amount_untaxed is null""")
        self.env.cr.execute("""
            UPDATE sale_order
            SET payer_amount = amount_total 
            WHERE payer_amount is null""")

    @api.model
    def _sync_sale_line_wipro_noadmission(self, sync_type='1', admission_ids=[]):
        #import trollius as asyncio
        # sync_ids = {record['sync_id']: record['id'] for record in self.sudo().search_read([('sync_type', '=', sync_type), ('sync_id', '>', 0)], ['id', 'sync_id'])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
        data = []
        date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
        # date = '2019-01-25'

        bill_no_admission = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 3, SUBSTRING(a.billno, 4, 10), a.OrderID, a.ServiceItemID, a.UoMID)) 'sync_id',
                a.ServiceID 'service_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.DepartmentID 'location_id',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                SUBSTRING(a.billno, 4, 10) 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RecordType 'type_line',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.RecordType = 'BILL'
            and a.tglproses = '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType = 'Pharmacy'
                and a.AdmissionID is null
            """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), bill_no_admission)

        discount_no_admission = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 5, SUBSTRING(a.billno, 4, 10), a.OrderID, a.ServiceItemID, a.UoMID)) 'sync_id',
                a.ServiceId 'service_id',
                99881177 'product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.DepartmentID 'location_id',
                SUBSTRING(a.billno, 4, 10) 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.RecordType = 'DISCOUNT'
            and a.tglproses = '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType = 'Pharmacy'
                and a.AdmissionID is null
            """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), discount_no_admission)

        discount_cancel_no_admission = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 6, SUBSTRING(a.billno, 4, 10), a.OrderID, a.ServiceItemID, a.UoMID)) 'sync_id',
                a.ServiceID 'service_id',
                99881177 'product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                SUBSTRING(a.billno, 4, 10) 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where RecordType = 'DISCOUNT CANCEL'
            and a.tglproses = '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType = 'Pharmacy'
                and a.AdmissionID is null
            """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), discount_cancel_no_admission)

        bill_cancel_no_admission = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 4, SUBSTRING(a.billno, 4, 10), a.OrderID, a.ServiceItemID, a.UoMID)) 'sync_id',
                a.ServiceID 'service_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END) 'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.DepartmentID 'location_id',
                SUBSTRING(a.billno, 4, 10) 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.RecordType = 'BILL CANCEL'
            and a.tglproses = '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType = 'Pharmacy'
                and a.AdmissionID is null
            """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), bill_cancel_no_admission)

        print (data)
        if not data:
            print ("No data available")
            return
        fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and 'ids' not in key and self._fields[key].required == True and self._fields[key].store == True)
        columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
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
        now = tools.datetime.now().strftime('%Y%m%d %H:%M:S')
        dbname = self.env.cr.dbname
        login = self.sudo().env.user.login
        import odoorpc
        request = odoorpc.ODOO('localhost', port=8085, timeout=100000000000)
        request.login(dbname, login, 'mayapada@hospital2018')
        env = request.env

        #uom_id = self.env.ref('product.product_uom_categ_unit').id
        #new_sync_ids = []
        #@asyncio.coroutine
        def process_query(object, result):
            object['sync_id'] = float(object['sync_id'])
            #new_sync_ids += [object['sync_id']]
            for value in default_values:
                object[value] = default_values[value]
            # print "Insert SO"
            order_id = object['order_id']
            object['order_id'] = env['sale.order'].search([('sync_id', '=', object['order_id']), ('sync_type', '=', sync_type)], limit=1)
            if not object['order_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + " sale.order with sync_id %s and sync_type %s doesn't exist" % (order_id, sync_type))
                return
            # print "Insert Product"
            # object['product_id'] = env['product.product'].search([('sync_id', '=', object['product_id']), ('sync_type', '=', sync_type)], limit=1) if object['product_id'] != 655 else env['product.product'].search([('name', 'ilike', 'administrative charges')], order="id asc", limit=1)
            product_id = object['product_id']
            object['product_id'] = env['product.template'].search([('sync_id', '=', object['product_id']), ('sync_type', '=', sync_type)], limit=1)
            object['product_id'] = env['product.product'].search(
                [('product_tmpl_id', '=', object['product_id'])], limit=1)
            if not object['product_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + " product.template with sync_id %s and sync_type %s doesn't exist" % (product_id, sync_type))
                return
            # object['product_id'] = env['product.product'].browse(object['product_id'])
            object['name'] = object['name'] or "DISCOUNT"

            # 2021.10.11 - product_categ_id based type of services
            if object['product_categ_id'] and object['service_categ_id'] in [10,17]:
                object['product_categ_id'] = env['product.category'].search([('sync_id', '=', object['product_categ_id']), ('sync_type', '=', sync_type), ('sync_is_category', '=', True)], limit=1) or None
            else:
                object['product_categ_id'] = env['product.category'].search([('sync_id', '=', object['product_categ_id']), ('sync_type', '=', sync_type), ('sync_is_surgery', '=', True)], limit=1) or None

            # print "Insert Service"
            object['service_categ_id'] = env['product.category'].search([('sync_id', '=', object['service_categ_id']), ('sync_type', '=', sync_type), ('sync_is_service', '=', True)], limit=1) or None
            # object['name'] = object['product_id'].name
            # print "Insert UOM"
            object['product_uom'] = env['product.uom'].search([('sync_id', '=', object['product_uom']), ('sync_type', '=', sync_type)], limit=1) or env['product.uom'].search([('sync_id', '=', 163), ('sync_type', '=', sync_type)], limit=1)
            #print "Insert Product Lagi"
            # object['product_id'] = object['product_id'].id
            # print "Insert Doctor"
            # c = False
            # if object['account_analytic_id'] == 1215: c = True
            object['account_analytic_id'] = env['account.analytic.account'].search([('sync_id', '=', object['account_analytic_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['account_analytic_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            # if c: print '\n\n\n\n\n\n\n', object['account_analytic_id'], sync_type
            object['prescribe_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['prescribe_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['prescribe_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            object['perform_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['perform_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['perform_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            object['primary_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            # print "Insert Location"
            object['location_id'] = env['stock.location'].search([('sync_id', '=', object['location_id']), ('sync_type', '=', sync_type)], limit=1) or None
            # print "Insert Payer"
            object['payer'] = env['res.partner'].search([('sync_id', '=', object['payer']), ('sync_type', '=', sync_type), ('insurance', '=', True)], limit=1) or None
            # print "Insert Bed Name"
            if object['discount_id']:
                object['discount_id'] = env['hospital.discount.type'].search([('sync_id', '=', object['discount_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['tariff_id']:
                object['tariff_id'] = env['hospital.tariff'].search([('sync_id', '=', object['tariff_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['room_id']:
                object['room_id'] = env['hospital.room.name'].search([('sync_id', '=', object['room_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['bed_id']:
                object['bed_id'] = env['hospital.bed.name'].search([('sync_id', '=', object['bed_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['bed_type_id']:
                object['bed_type_id'] = env['hospital.bed.type'].search([('sync_id', '=', object['bed_type_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['eligible_bed_type_id']:
                object['eligible_bed_type_id'] = env['hospital.bed.type'].search([('sync_id', '=', object['eligible_bed_type_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['alloted_bed_type_id']:
                object['alloted_bed_type_id'] = env['hospital.bed.type'].search([('sync_id', '=', object['alloted_bed_type_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['referral_id']:
                object['referral_id'] = env['referral.transaction'].search([('sync_id', '=', object['referral_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['billing_id']:
                object['billing_id'] = env['sale.order.bill'].search([('sync_id', '=', object['billing_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['referral_doc_id']:
                object['referral_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['referral_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or None
            
            # if object['sync_id'] and object['sync_id'] in sync_ids:
            #    return
            #    object['id'] = sync_ids[object['sync_id']]
            # else:
            object['id'] = 'DEFAULT'
            object['sync_date'] = now
            # print "Insert Sync Type"
            object['sync_type'], object['company_id'] = sync_type, env['res.company'].search([('sync_type', '=', sync_type)], limit=1)
            #if values:
            #   values += ', '
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
                if type(object[field]) in [list, tuple] and len(
                        object[field]) == 1:
                    object[field] = object[field][0]
                value += sync.json(object[field])
            value += ')'
            result += [value]
            #return value
            #values += value

        #loop = asyncio.get_event_loop()
        #tasks = [asyncio.create_task(process_query(object)) for object in data]
        #for result in loop.run_until_complete(asyncio.gather(*tasks)):
        #    if result:
        #       if values:
        #          values += ', '
        #       values += result
        processes = []
        result = list()
        try:
            result = Manager().list()
        except:
            pass
        for chunk in sync.split_list(data, sync.cpu_count * 2):
            process = Process(
                target=lambda chunk, result:
                [process_query(object, result) for object in chunk],
                args=(chunk, result))
            process.start()
            processes += [process]
        for process in processes:
            process.join()
        values = ', '.join(result)
        excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        columns = sync.remove_unicode(str(fields)).replace("'", "")
        columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        print (values.encode('utf-8'))
        if not values:
            print ("No data available")
            return
        query = "INSERT into sale_order_line %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)
        self.env.cr.execute("""
            UPDATE sale_order_line
            SET price_total = price_subtotal 
            WHERE price_total is null""")
        self.env.cr.execute("""
            UPDATE sale_order
            SET amount_total = (select sum(price_total)
                from sale_order_line where order_id = sale_order.id and type_line in ('BILL', 'BILL CANCEL', 'DISCOUNT', 'DISCOUNT CANCEL')) 
            WHERE amount_total is null""")
        self.env.cr.execute("""
            UPDATE sale_order
            SET amount_untaxed = (select sum(price_total)
                from sale_order_line where order_id = sale_order.id and type_line in ('BILL', 'BILL CANCEL', 'DISCOUNT', 'DISCOUNT CANCEL')) 
            WHERE amount_untaxed is null""")
        self.env.cr.execute("""
            UPDATE sale_order
            SET payer_amount = amount_total 
            WHERE payer_amount is null""")

    @api.model
    def _sync_sale_line_manual(self, sync_type='1', date=False, admission_ids=[], date_start='2019-01-01', date_end='2019-01-01'):
        # sync_ids = {record['sync_id']: record['id'] for record in self.sudo().search_read([('sync_type', '=', sync_type), ('sync_id', '>', 0)], ['id', 'sync_id'])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
        data = []
        if not date:
            date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
        # date = '2019-02-01'
        bill_discount = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 5, a.AdmissionID, a.DiscountSLNo, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID, a.DepartmentID, a.ServiceItemID)) 'sync_id',
                a.ServiceID 'service_id',
                99881177 'product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.DepartmentID 'location_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.RecordType = 'DISCOUNT'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType <> 'InPatient'
                and a.AdmissionID is not null
            """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), bill_discount)

        bill_discount_cancel = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 6, a.AdmissionID, a.DiscountSLNo, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID, a.DepartmentID, a.ServiceItemID)) 'sync_id',
                a.ServiceID 'service_id',
                99881177 'product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.Billid 'billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 A
            WHERE a.RecordType = 'DISCOUNT CANCEL'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.PatientType <> 'InPatient'
                and a.AdmissionID is not null
            """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), bill_discount_cancel)

        bill_cancel = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 4, a.AdmissionID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'service_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.AdmissionID 'order_id',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.BillNo 'billno',
                a.Billid 'billing_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            WHERE RecordType = 'BILL CANCEL'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.PatientType <> 'InPatient'
                and a.AdmissionID is not null
            """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), bill_cancel)

        bill_op = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 3, a.AdmissionID, a.ServiceItemID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'service_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            FROM dbo.V_Db_A_A_RawDataH30 a
            WHERE a.RecordType = 'BILL'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType <> 'InPatient'
                and a.AdmissionID is not null
            """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), bill_op)

        accrual_daily = """
            SELECT 
                a.TglProses 'tglproses',
                (convert(varchar(max), concat(convert(int, getdate()), 1, a.AdmissionID, a.ServiceID, a.OrderID, a.OrderItemID, a.ServiceItemID)))  'sync_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.AdmissionID 'order_id',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.RecordType 'type_line',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses >= '%s' and a.tglproses <= '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.PatientType='InPatient'
                and a.recordType in('ACCRUAL')
                and not exists (
                    select top 1 1
                    from dbo.V_Db_A_A_RawDataH30 t
                    where t.tglproses=a.tglproses
                        and t.PatientType='InPatient'
                        and t.recordType in('ACCRUAL REVERSAL')
                        and t.AdmissionID=a.AdmissionID
                        and t.ServiceID=a.ServiceID
                        and t.OrderID=a.OrderID
                        and t.OrderItemID=a.OrderItemID 
                        and t.Value=(-1*a.Value)
                )""" % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), accrual_daily)

        accrual_reversal_daily = """
            SELECT 
                a.TglProses 'tglproses',
                (convert(varchar(max), concat(convert(int, getdate()), 2, a.AdmissionID, a.OrderID, a.ServiceID, a.ServiceItemID, a.OrderItemID)))  'sync_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN UoMID is null THEN 187 ELSE UoMID END)  'product_uom',
                (CASE WHEN Quantity IS NULL THEN 1 ELSE Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN Quantity IS NULL OR Quantity = 0 THEN 1 ELSE Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.RecordType 'type_line',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses >= '%s' and a.tglproses <= '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366)
                and a.PatientType='InPatient'
                and a.recordType in('ACCRUAL REVERSAL')
                and not exists (
                    select top 1 1
                    from dbo.V_Db_A_A_RawDataH30 t
                    where t.tglproses=a.tglproses
                        and t.PatientType='InPatient'
                        and t.recordType in('ACCRUAL')
                        and t.AdmissionID=a.AdmissionID
                        and t.ServiceID=a.ServiceID
                        and t.OrderID=a.OrderID
                        and t.OrderItemID=a.OrderItemID 
                        and t.Value=(-1*a.Value)) """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), accrual_reversal_daily)

        bill_service_item = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 3, a.AdmissionID, a.ServiceItemID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'service_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.RecordType 'type_line',
                a.DepartmentID 'location_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                b.BillNo 'billno',
                b.BillID 'billing_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 A
            outer apply (
                select top 1 b.*
                from dbo.V_Db_A_A_RawDataH30 b
                where b.TglProses=a.TglProses
                    and b.PatientType=a.PatientType
                    and b.AdmissionID=a.AdmissionID
                    and b.RecordType='BILL'
                order by a.BillID asc
                ) AS b
                where a.tglproses >= '%s' and a.tglproses <= '%s'
                -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                    and (a.ServiceID <> 10 AND a.ServiceID <> 17)
                    and a.RecordType in('BILL')
                    and a.PatientType = 'InPatient'""" % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), bill_service_item)

        bill_item = """
            SELECT 
                a.TglProses 'tglproses',
                convert(varchar(max), concat(convert(int, a.TglProses), 3, a.AdmissionID, a.ServiceItemID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'service_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.RecordType 'type_line',
                a.DepartmentID 'location_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                b.BillNo 'billno',
                b.BillID 'billing_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            outer apply (
                select top 1 b.*
                from dbo.V_Db_A_A_RawDataH30 b
                where b.TglProses=a.TglProses
                    and b.PatientType=a.PatientType
                    and b.AdmissionID=a.AdmissionID
                    and b.RecordType='BILL'
                order by a.BillID asc
                ) AS b
                where a.tglproses >= '%s' and a.tglproses <= '%s'
                -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                    and (a.ServiceID = 10 OR a.ServiceID = 17)
                    and a.RecordType = 'BILL'
                    and a.PatientType = 'InPatient'
                """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), bill_item)

        bill_discount = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 5, a.AdmissionID, a.DiscountSLNo, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID, a.DepartmentID, a.ServiceItemID)) 'sync_id',
                a.ServiceID 'service_id',
                99881177 'product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.AdmissionID 'order_id',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses >= '%s' and a.tglproses <= '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.RecordType = 'DISCOUNT'
                and a.PatientType = 'InPatient'
            """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), bill_discount)

        bill_discount_cancel = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar, concat(convert(int, TglProses), 6, a.AdmissionID, a.DiscountSLNo, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID, a.DepartmentID, a.ServiceItemID)) 'sync_id',
                a.ServiceID 'service_id',
                99881177 'product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses >= '%s' and a.tglproses <= '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.RecordType = 'DISCOUNT CANCEL'
                and a.PatientType = 'InPatient'
            """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), bill_discount_cancel)

        bill_cancel = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 4, a.AdmissionID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'service_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.AdmissionID 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses >= '%s' and a.tglproses <= '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.RecordType = 'BILL CANCEL'
                and a.PatientType = 'InPatient'
            """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), bill_cancel)

        bill_no_admission = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 3, SUBSTRING(a.billno, 4, 10), a.OrderID, a.ServiceItemID, a.UoMID)) 'sync_id',
                a.ServiceID 'service_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.DepartmentID 'location_id',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                SUBSTRING(a.billno, 4, 10) 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RecordType 'type_line',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.RecordType = 'BILL'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType = 'Pharmacy'
                and a.AdmissionID is null
            """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), bill_no_admission)

        discount_no_admission = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 5, SUBSTRING(a.billno, 4, 10), a.OrderID, a.ServiceItemID, a.UoMID)) 'sync_id',
                a.ServiceId 'service_id',
                99881177 'product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                a.DepartmentID 'location_id',
                SUBSTRING(a.billno, 4, 10) 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.RecordType = 'DISCOUNT'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType = 'Pharmacy'
                and a.AdmissionID is null
            """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), discount_no_admission)

        discount_cancel_no_admission = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 6, SUBSTRING(a.billno, 4, 10), a.OrderID, a.ServiceItemID, a.UoMID)) 'sync_id',
                a.ServiceID 'service_id',
                99881177 'product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                SUBSTRING(a.billno, 4, 10) 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.DepartmentID 'location_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where RecordType = 'DISCOUNT CANCEL'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType = 'Pharmacy'
                and a.AdmissionID is null
            """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), discount_cancel_no_admission)

        bill_cancel_no_admission = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 4, SUBSTRING(a.billno, 4, 10), a.OrderID, a.ServiceItemID, a.UoMID)) 'sync_id',
                a.ServiceID 'service_id',
                a.ServiceItemID 'product_id',
                a.ServiceItemName 'name',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'product_categ_id',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END) 'product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.BillNo 'billno',
                a.BillID 'billing_id',
                a.DepartmentID 'location_id',
                SUBSTRING(a.billno, 4, 10) 'order_id',
                NULLIF(a.PrimaryDocID,0) 'primary_doc_id',
                NULLIF(a.PerformDocID,0) 'perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'prescribe_doc_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'room_id',
                a.BedId 'bed_id',
                a.AllotedBedTypeId 'alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'tariff_id',
                a.BillableBedTypeID 'bed_type_id',
                a.EligibleBedTypeID 'eligible_bed_type_id',
                a.ReferralId 'referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.RecordType = 'BILL CANCEL'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType = 'Pharmacy'
                and a.AdmissionID is null
            """ % (date_start, date_end)
        data += sync.get_data(sync.servers.get(sync_type), bill_cancel_no_admission)
        print (data)
        if not data:
            print ("No data available")
            return
        fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and 'ids' not in key and self._fields[key].required == True and self._fields[key].store == True)
        columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
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
        now = tools.datetime.now().strftime('%Y%m%d %H:%M:%S')
        dbname = self.env.cr.dbname
        login = self.sudo().env.user.login
        import odoorpc
        request = odoorpc.ODOO('localhost', port=8085, timeout=100000000000)
        request.login(dbname, login, 'mayapada@hospital2018')
        env = request.env

        #uom_id = self.env.ref('product.product_uom_categ_unit').id
        #new_sync_ids = []
        #@asyncio.coroutine
        def process_query(object, result):
            object['sync_id'] = float(object['sync_id'])
            #new_sync_ids += [object['sync_id']]
            for value in default_values:
                object[value] = default_values[value]
            # print "Insert SO"
            order_id = object['order_id']
            object['order_id'] = env['sale.order'].search([('sync_id', '=', object['order_id']), ('sync_type', '=', sync_type)], limit=1)
            if not object['order_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + " sync sale.order.line related sale.order with sync_id %s and sync_type %s doesn't exist" % (order_id, sync_type))
                return
            # print "Insert Product"
            # object['product_id'] = env['product.product'].search([('sync_id', '=', object['product_id']), ('sync_type', '=', sync_type)], limit=1) if object['product_id'] != 655 else env['product.product'].search([('name', 'ilike', 'administrative charges')], order="id asc", limit=1)
            product_id = object['product_id']
            object['product_id'] = env['product.template'].search([('sync_id', '=', object['product_id']), ('sync_type', '=', sync_type)], limit=1)
            object['product_id'] = env['product.product'].search([('product_tmpl_id', '=', object['product_id'])], limit=1)
            if not object['product_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + " sync sale.order.line related product.template with sync_id %s and sync_type %s doesn't exist" % (product_id, sync_type))
                return
            # object['product_id'] = env['product.product'].browse(object['product_id'])
            object['name'] = object['name'] or "DISCOUNT"

            # 2021.10.11 - product_categ_id based type of services
            if object['product_categ_id'] and object['service_categ_id'] in [10,17]:
                object['product_categ_id'] = env['product.category'].search([('sync_id', '=', object['product_categ_id']), ('sync_type', '=', sync_type), ('sync_is_category', '=', True)], limit=1) or None
            else:
                object['product_categ_id'] = env['product.category'].search([('sync_id', '=', object['product_categ_id']), ('sync_type', '=', sync_type), ('sync_is_surgery', '=', True)], limit=1) or None

            # print "Insert Service"
            object['service_categ_id'] = env['product.category'].search([('sync_id', '=', object['service_categ_id']), ('sync_type', '=', sync_type), ('sync_is_service', '=', True)], limit=1) or None
            # object['name'] = object['product_id'].name
            # print "Insert UOM"
            object['product_uom'] = env['product.uom'].search([('sync_id', '=', object['product_uom']), ('sync_type', '=', sync_type)], limit=1) or env['product.uom'].search([('sync_id', '=', 163), ('sync_type', '=', sync_type)], limit=1)
            # #print "Insert Product Lagi"
            # object['product_id'] = object['product_id'].id
            # print "Insert Doctor"
            # c = False
            # if object['account_analytic_id'] == 1215: c = True
            object['account_analytic_id'] = env['account.analytic.account'].search([('sync_id', '=', object['account_analytic_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['account_analytic_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            # if c: print '\n\n\n\n\n\n\n', object['account_analytic_id'], sync_type
            object['prescribe_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['prescribe_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['prescribe_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            object['perform_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['perform_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['perform_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            object['primary_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1) or env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1) or None
            # print "Insert Location"
            object['location_id'] = env['stock.location'].search([('sync_id', '=', object['location_id']), ('sync_type', '=', sync_type)], limit=1) or None
            # print "Insert Bed Name"
            if object['discount_id']:
                object['discount_id'] = env['hospital.discount.type'].search([('sync_id', '=', object['discount_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['tariff_id']:
                object['tariff_id'] = env['hospital.tariff'].search([('sync_id', '=', object['tariff_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['room_id']:
                object['room_id'] = env['hospital.room.name'].search([('sync_id', '=', object['room_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['bed_id']:
                object['bed_id'] = env['hospital.bed.name'].search([('sync_id', '=', object['bed_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['bed_type_id']:
                object['bed_type_id'] = env['hospital.bed.type'].search([('sync_id', '=', object['bed_type_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['eligible_bed_type_id']:
                object['eligible_bed_type_id'] = env['hospital.bed.type'].search([('sync_id', '=', object['eligible_bed_type_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['alloted_bed_type_id']:
                object['alloted_bed_type_id'] = env['hospital.bed.type'].search([('sync_id', '=', object['alloted_bed_type_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['referral_id']:
                object['referral_id'] = env['referral.transaction'].search([('sync_id', '=', object['referral_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['billing_id']:
                object['billing_id'] = env['sale.order.bill'].search([('sync_id', '=', object['billing_id']), ('sync_type', '=', sync_type)], limit=1) or None
            if object['referral_doc_id']:
                object['referral_doc_id'] = env['account.analytic.account'].search([('sync_id', '=', object['referral_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1) or None
            
            # if object['sync_id'] and object['sync_id'] in sync_ids:
            #    return
            #    object['id'] = sync_ids[object['sync_id']]
            # else:
            object['id'] = 'DEFAULT'
            object['sync_date'] = now
            # print "Insert Sync Type"
            object['sync_type'], object['company_id'] = sync_type, env['res.company'].search([('sync_type', '=', sync_type)], limit=1)
            # print "Insert Payer"
            object['payer'] = env['res.partner'].search([('sync_id', '=', object['payer']), ('sync_type', '=', sync_type), ('insurance', '=', True)], limit=1) or None
            #if values:
            #   values += ', '
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
                if type(object[field]) in [list, tuple] and len(object[field]) == 1:
                    object[field] = object[field][0]
                value += sync.json(object[field])
            value += ')'
            result += [value]
            #return value
            #values += value

        #loop = asyncio.get_event_loop()
        #tasks = [asyncio.create_task(process_query(object)) for object in data]
        #for result in loop.run_until_complete(asyncio.gather(*tasks)):
        #    if result:
        #       if values:
        #          values += ', '
        #       values += result
        processes = []
        result = list()
        try:
            result = Manager().list()
        except:
            pass
        for chunk in sync.split_list(data, sync.cpu_count * 2):
            process = Process(
                target=lambda chunk, result:
                [process_query(object, result) for object in chunk],
                args=(chunk, result))
            process.start()
            processes += [process]
        for process in processes:
            process.join()
        values = ', '.join(result)
        excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        columns = sync.remove_unicode(str(fields)).replace("'", "")
        columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        print (values.encode('utf-8'))
        if not values:
            print ("No values available")
            return
        # print "Insert ALL DATA"
        query = "INSERT into sale_order_line %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)
        self.env.cr.execute("""
            UPDATE sale_order_line
            SET price_total = price_subtotal 
            WHERE price_total is null""")
        self.env.cr.execute("""
            UPDATE sale_order
            SET amount_total = (select sum(price_total)
                from sale_order_line where order_id = sale_order.id and type_line in ('BILL', 'BILL CANCEL', 'DISCOUNT', 'DISCOUNT CANCEL')) 
            WHERE amount_total is null""")
        self.env.cr.execute("""
            UPDATE sale_order
            SET amount_untaxed = (select sum(price_total)
                from sale_order_line where order_id = sale_order.id and type_line in ('BILL', 'BILL CANCEL', 'DISCOUNT', 'DISCOUNT CANCEL')) 
            WHERE amount_untaxed is null""")
        self.env.cr.execute("""
            UPDATE sale_order
            SET payer_amount = amount_total 
            WHERE payer_amount is null""")



    # sync line manual best practice firgi
    @api.model
    def _sync_sale_line_manual_simple(self, sync_type='1', date=False, admission_ids=[], date_start='2019-01-01', date_end='2019-01-01'):
        import trollius as asyncio
        # sync_ids = {record['sync_id']: record['id'] for record in self.sudo().search_read([('sync_type', '=', sync_type), ('sync_id', '>', 0)], ['id', 'sync_id'])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
        data = []
        if not date:
            date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
        
        # drop if exists 
        query = "DROP TABLE IF EXISTS sale_order_line_temp;"
        print (query)
        self.env.cr.execute(query)
        
        # create temp table 
        query = """
            CREATE TABLE sale_order_line_temp (
                "product_uom" int4 NOT NULL,
                "wipro_product_uom" int4 NOT NULL,
                "price_unit" numeric NOT NULL,
                "product_uom_qty" numeric NOT NULL,
                "price_subtotal" numeric,
                "price_total" numeric,
                "order_id" int4 NOT NULL,
                "wipro_order_id" int4,
                "discount" numeric,
                "write_date" timestamp(6),
                "product_id" int4 NOT NULL,
                "wipro_product_id" int4 NOT NULL,
                "name" text COLLATE "pg_catalog"."default" NOT NULL,
                "sync_date" timestamp(6),
                "sync_id" float8,
                "sync_type" varchar COLLATE "pg_catalog"."default",
                "order_date" timestamp(6),
                "admit_date" timestamp(6),
                "admission_type" varchar COLLATE "pg_catalog"."default",
                "ref_admission_no" varchar COLLATE "pg_catalog"."default",
                "discharge_date" timestamp(6),
                "discharge_reason" varchar COLLATE "pg_catalog"."default",
                "account_analytic_id" int4,
                "wipro_account_analytic_id" int4,
                "type_line" varchar COLLATE "pg_catalog"."default",
                "patient_type" varchar COLLATE "pg_catalog"."default",
                "service_categ_id" int4,
                "wipro_service_categ_id" int4,
                "department_id" varchar COLLATE "pg_catalog"."default",
                "tglproses" date,
                "billno" varchar COLLATE "pg_catalog"."default",
                "payer" int4,
                "wipro_payer" int4,
                "cost_unit" float8,
                "cost_total" float8,
                "registration_code" varchar COLLATE "pg_catalog"."default",
                "payer_type" varchar COLLATE "pg_catalog"."default",
                "location_id" int4,
                "wipro_location_id" int4,
                "primary_doc_id" int4,
                "perform_doc_id" int4,
                "prescribe_doc_id" int4,
                "referral_doc_id" int4,
                "wipro_primary_doc_id" int4,
                "wipro_perform_doc_id" int4,
                "wipro_prescribe_doc_id" int4,
                "wipro_referral_doc_id" int4,
                "doctor_backup_id" float8,
                "wipro_doctor_backup_id" float8,
                "bill_date" date,
                "normal_uom" int4,
                "normal_qty" float8,
                "normal_price" float8,
                "is_conversion" bool,
                "narcotic" bool,
                "generic" bool,
                "psychotropic" bool,
                "antibiotic" bool,
                "revenue_type" varchar COLLATE "pg_catalog"."default",
                "item_specialisation" varchar COLLATE "pg_catalog"."default",
                "special_group" varchar COLLATE "pg_catalog"."default",
                "patient_group" varchar COLLATE "pg_catalog"."default",
                "service_group" varchar COLLATE "pg_catalog"."default",
                "cost_date" date,
                "bed_type" varchar COLLATE "pg_catalog"."default",
                "special_group2" varchar COLLATE "pg_catalog"."default",
                "service_categ_name" varchar COLLATE "pg_catalog"."default",
                "specialization_primary" varchar COLLATE "pg_catalog"."default",
                "package_name" varchar COLLATE "pg_catalog"."default",
                "is_surgery" bool,
                "is_package" bool,
                "kecamatan" varchar COLLATE "pg_catalog"."default",
                "kelurahan" varchar COLLATE "pg_catalog"."default",
                "kota" varchar COLLATE "pg_catalog"."default",
                "order_no" varchar COLLATE "pg_catalog"."default",
                "payer_code" varchar COLLATE "pg_catalog"."default",
                "payer_name" varchar COLLATE "pg_catalog"."default",
                "manufacture" varchar COLLATE "pg_catalog"."default",
                "secondary_diagnosis_name" varchar COLLATE "pg_catalog"."default",
                "secondary_diagnosis_code" varchar COLLATE "pg_catalog"."default",
                "primary_diagnosis_code" varchar COLLATE "pg_catalog"."default",
                "primary_diagnosis_name" varchar COLLATE "pg_catalog"."default",
                "repeat_diagnosis_code" varchar COLLATE "pg_catalog"."default",
                "repeat_diagnosis_name" varchar COLLATE "pg_catalog"."default",
                "discount_date" timestamp(6),
                "discount_reason" varchar COLLATE "pg_catalog"."default",
                "discount_level" varchar COLLATE "pg_catalog"."default",
                "discount_name" varchar COLLATE "pg_catalog"."default",
                "bed_type_id" int4,
                "wipro_bed_type_id" int4,
                "room_id" int4,
                "wipro_room_id" int4,
                "discount_id" int4,
                "wipro_discount_id" int4,
                "bed_id" int4,
                "wipro_bed_id" int4,
                "eligible_bed_type_id" int4,
                "wipro_eligible_bed_type_id" int4,
                "bed_allocation_end" timestamp(6),
                "bed_allocation_start" timestamp(6),
                "alloted_bed_type_id" int4,
                "wipro_alloted_bed_type_id" int4,
                "product_categ_id" int4,
                "wipro_product_categ_id" int4,
                "billing_id" int4,
                "wipro_billing_id" int4,
                "referral_number" varchar COLLATE "pg_catalog"."default",
                "referral_id" int4,
                "wipro_referral_id" int4,
                "tariff_id" int4,
                "wipro_tariff_id" int4
            )
            """
        print (query)
        self.env.cr.execute(query)
        

        
        
        # date = '2019-02-01'
        bill_discount = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 5, a.AdmissionID, a.DiscountSLNo, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID, a.DepartmentID, a.ServiceItemID)) 'sync_id',
                a.ServiceID 'wipro_service_id',
                99881177 'wipro_product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'wipro_product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                a.AdmissionID 'wipro_order_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.BillNo 'billno',
                a.BillID 'wipro_billing_id',
                a.DepartmentID 'wipro_location_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.RecordType = 'DISCOUNT'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType <> 'InPatient'
                and a.AdmissionID is not null
            """ % (date_start, date_end)
        print (bill_discount)
        data += sync.get_data(sync.servers.get(sync_type), bill_discount)

        bill_discount_cancel = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 6, a.AdmissionID, a.DiscountSLNo, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID, a.DepartmentID, a.ServiceItemID)) 'sync_id',
                a.ServiceID 'wipro_service_id',
                99881177 'wipro_product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'wipro_product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                a.AdmissionID 'wipro_order_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.DepartmentID 'wipro_location_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.Billid 'wipro_billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 A
            WHERE a.RecordType = 'DISCOUNT CANCEL'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.PatientType <> 'InPatient'
                and a.AdmissionID is not null
            """ % (date_start, date_end)
        print (bill_discount_cancel)
        data += sync.get_data(sync.servers.get(sync_type), bill_discount_cancel)

        bill_cancel = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 4, a.AdmissionID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'wipro_service_id',
                a.ServiceItemID 'wipro_product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'wipro_product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.AdmissionID 'wipro_order_id',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.DepartmentID 'wipro_location_id',
                a.BillNo 'billno',
                a.Billid 'wipro_billing_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            WHERE RecordType = 'BILL CANCEL'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.PatientType <> 'InPatient'
                and a.AdmissionID is not null
            """ % (date_start, date_end)
        print (bill_cancel)
        data += sync.get_data(sync.servers.get(sync_type), bill_cancel)

        bill_op = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 3, a.AdmissionID, a.ServiceItemID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'wipro_service_id',
                a.ServiceItemID 'wipro_product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'wipro_product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                a.AdmissionID 'wipro_order_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.DepartmentID 'wipro_location_id',
                a.BillNo 'billno',
                a.BillID 'wipro_billing_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            FROM dbo.V_Db_A_A_RawDataH30 a
            WHERE a.RecordType = 'BILL'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType <> 'InPatient'
                and a.AdmissionID is not null
            """ % (date_start, date_end)
        print (bill_op) 
        data += sync.get_data(sync.servers.get(sync_type), bill_op)

        accrual_daily = """
            SELECT 
                a.TglProses 'tglproses',
                (convert(varchar(max), concat(convert(int, getdate()), 1, a.AdmissionID, a.ServiceID, a.OrderID, a.OrderItemID, a.ServiceItemID)))  'sync_id',
                a.ServiceItemID 'wipro_product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'wipro_product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.AdmissionID 'wipro_order_id',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.DepartmentID 'wipro_location_id',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                a.BillNo 'billno',
                a.BillID 'wipro_billing_id',
                a.RecordType 'type_line',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses >= '%s' and a.tglproses <= '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.PatientType='InPatient'
                and a.recordType in('ACCRUAL')
                and not exists (
                    select top 1 1
                    from dbo.V_Db_A_A_RawDataH30 t
                    where t.tglproses=a.tglproses
                        and t.PatientType='InPatient'
                        and t.recordType in('ACCRUAL REVERSAL')
                        and t.AdmissionID=a.AdmissionID
                        and t.ServiceID=a.ServiceID
                        and t.OrderID=a.OrderID
                        and t.OrderItemID=a.OrderItemID 
                        and t.Value=(-1*a.Value)
                )""" % (date_start, date_end)
        print (accrual_daily) 
        data += sync.get_data(sync.servers.get(sync_type), accrual_daily)

        accrual_reversal_daily = """
            SELECT 
                a.TglProses 'tglproses',
                (convert(varchar(max), concat(convert(int, getdate()), 2, a.AdmissionID, a.OrderID, a.ServiceID, a.ServiceItemID, a.OrderItemID)))  'sync_id',
                a.ServiceItemID 'wipro_product_id',
                a.ServiceItemName 'name',
                (CASE WHEN UoMID is null THEN 187 ELSE UoMID END)  'wipro_product_uom',
                (CASE WHEN Quantity IS NULL THEN 1 ELSE Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN Quantity IS NULL OR Quantity = 0 THEN 1 ELSE Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                a.AdmissionID 'wipro_order_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.DepartmentID 'wipro_location_id',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                a.BillNo 'billno',
                a.BillID 'wipro_billing_id',
                a.RecordType 'type_line',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses >= '%s' and a.tglproses <= '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366)
                and a.PatientType='InPatient'
                and a.recordType in('ACCRUAL REVERSAL')
                and not exists (
                    select top 1 1
                    from dbo.V_Db_A_A_RawDataH30 t
                    where t.tglproses=a.tglproses
                        and t.PatientType='InPatient'
                        and t.recordType in('ACCRUAL')
                        and t.AdmissionID=a.AdmissionID
                        and t.ServiceID=a.ServiceID
                        and t.OrderID=a.OrderID
                        and t.OrderItemID=a.OrderItemID 
                        and t.Value=(-1*a.Value)) """ % (date_start, date_end)
        print (accrual_reversal_daily) 
        data += sync.get_data(sync.servers.get(sync_type), accrual_reversal_daily)

        bill_service_item = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 3, a.AdmissionID, a.ServiceItemID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'wipro_service_id',
                a.ServiceItemID 'wipro_product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'wipro_product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                a.AdmissionID 'wipro_order_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.RecordType 'type_line',
                a.DepartmentID 'wipro_location_id',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                b.BillNo 'billno',
                b.BillID 'wipro_billing_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 A
            outer apply (
                select top 1 b.*
                from dbo.V_Db_A_A_RawDataH30 b
                where b.TglProses=a.TglProses
                    and b.PatientType=a.PatientType
                    and b.AdmissionID=a.AdmissionID
                    and b.RecordType='BILL'
                order by a.BillID asc
                ) AS b
                where a.tglproses >= '%s' and a.tglproses <= '%s'
                -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                    and (a.ServiceID <> 10 AND a.ServiceID <> 17)
                    and a.RecordType in('BILL')
                    and a.PatientType = 'InPatient'""" % (date_start, date_end)
        print (bill_service_item)
        data += sync.get_data(sync.servers.get(sync_type), bill_service_item)

        bill_item = """
            SELECT 
                a.TglProses 'tglproses',
                convert(varchar(max), concat(convert(int, a.TglProses), 3, a.AdmissionID, a.ServiceItemID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'wipro_service_id',
                a.ServiceItemID 'wipro_product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'wipro_product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                a.AdmissionID 'wipro_order_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.RecordType 'type_line',
                a.DepartmentID 'wipro_location_id',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                b.BillNo 'billno',
                b.BillID 'wipro_billing_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            outer apply (
                select top 1 b.*
                from dbo.V_Db_A_A_RawDataH30 b
                where b.TglProses=a.TglProses
                    and b.PatientType=a.PatientType
                    and b.AdmissionID=a.AdmissionID
                    and b.RecordType='BILL'
                order by a.BillID asc
                ) AS b
                where a.tglproses >= '%s' and a.tglproses <= '%s'
                -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                    and (a.ServiceID = 10 OR a.ServiceID = 17)
                    and a.RecordType = 'BILL'
                    and a.PatientType = 'InPatient'
                """ % (date_start, date_end)
        print (bill_item)
        data += sync.get_data(sync.servers.get(sync_type), bill_item)

        bill_discount = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 5, a.AdmissionID, a.DiscountSLNo, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID, a.DepartmentID, a.ServiceItemID)) 'sync_id',
                a.ServiceID 'wipro_service_id',
                99881177 'wipro_product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'wipro_product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.AdmissionID 'wipro_order_id',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.DepartmentID 'wipro_location_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                a.BillNo 'billno',
                a.BillID 'wipro_billing_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses >= '%s' and a.tglproses <= '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.RecordType = 'DISCOUNT'
                and a.PatientType = 'InPatient'
            """ % (date_start, date_end)
        print (bill_discount)
        data += sync.get_data(sync.servers.get(sync_type), bill_discount)

        bill_discount_cancel = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar, concat(convert(int, TglProses), 6, a.AdmissionID, a.DiscountSLNo, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID, a.DepartmentID, a.ServiceItemID)) 'sync_id',
                a.ServiceID 'wipro_service_id',
                99881177 'wipro_product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'wipro_product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                a.AdmissionID 'wipro_order_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.DepartmentID 'wipro_location_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.BillID 'wipro_billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses >= '%s' and a.tglproses <= '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.RecordType = 'DISCOUNT CANCEL'
                and a.PatientType = 'InPatient'
            """ % (date_start, date_end)
        print (bill_discount_cancel)
        data += sync.get_data(sync.servers.get(sync_type), bill_discount_cancel)

        bill_cancel = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 4, a.AdmissionID, a.BillID, a.BillItemID, a.OrderID, a.OrderItemID)) 'sync_id',
                a.ServiceID 'wipro_service_id',
                a.ServiceItemID 'wipro_product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'wipro_product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                a.AdmissionID 'wipro_order_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.DepartmentID 'wipro_location_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.BillID 'wipro_billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.tglproses >= '%s' and a.tglproses <= '%s'
            -- where a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
            -- and a.ServiceItemID in (61123,34674,51305,51340,51366) 
                and a.RecordType = 'BILL CANCEL'
                and a.PatientType = 'InPatient'
            """ % (date_start, date_end)
        print (bill_cancel)
        data += sync.get_data(sync.servers.get(sync_type), bill_cancel)

        bill_no_admission = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 3, SUBSTRING(a.billno, 4, 10), a.OrderID, a.ServiceItemID, a.UoMID)) 'sync_id',
                a.ServiceID 'wipro_service_id',
                a.ServiceItemID 'wipro_product_id',
                a.ServiceItemName 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'wipro_product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                a.DepartmentID 'wipro_location_id',
                a.BillNo 'billno',
                a.BillID 'wipro_billing_id',
                SUBSTRING(a.billno, 4, 10) 'wipro_order_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                a.RecordType 'type_line',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.RecordType = 'BILL'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType = 'Pharmacy'
                and a.AdmissionID is null
            """ % (date_start, date_end)
        print (bill_no_admission)
        data += sync.get_data(sync.servers.get(sync_type), bill_no_admission)

        discount_no_admission = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 5, SUBSTRING(a.billno, 4, 10), a.OrderID, a.ServiceItemID, a.UoMID)) 'sync_id',
                a.ServiceId 'wipro_service_id',
                99881177 'wipro_product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'wipro_product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                a.DepartmentID 'wipro_location_id',
                SUBSTRING(a.billno, 4, 10) 'wipro_order_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.BillID 'wipro_billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.RecordType = 'DISCOUNT'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType = 'Pharmacy'
                and a.AdmissionID is null
            """ % (date_start, date_end)
        print (discount_no_admission)
        data += sync.get_data(sync.servers.get(sync_type), discount_no_admission)

        discount_cancel_no_admission = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 6, SUBSTRING(a.billno, 4, 10), a.OrderID, a.ServiceItemID, a.UoMID)) 'sync_id',
                a.ServiceID 'wipro_service_id',
                99881177 'wipro_product_id',
                (CASE WHEN a.ServiceItemName is null THEN a.DiscountReason ELSE a.ServiceItemName END) 'name',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END)  'wipro_product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                SUBSTRING(a.billno, 4, 10) 'wipro_order_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.DepartmentID 'wipro_location_id',
                a.RecordType 'type_line',
                a.BillNo 'billno',
                a.BillID 'wipro_billing_id',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where RecordType = 'DISCOUNT CANCEL'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType = 'Pharmacy'
                and a.AdmissionID is null
            """ % (date_start, date_end)
        print (discount_cancel_no_admission)
        data += sync.get_data(sync.servers.get(sync_type), discount_cancel_no_admission)

        bill_cancel_no_admission = """
            SELECT
                a.TglProses 'tglproses',
                CONVERT(varchar(max), concat(convert(int, a.TglProses), 4, SUBSTRING(a.billno, 4, 10), a.OrderID, a.ServiceItemID, a.UoMID)) 'sync_id',
                a.ServiceID 'wipro_service_id',
                a.ServiceItemID 'wipro_product_id',
                a.ServiceItemName 'name',
                a.ServiceID 'wipro_service_categ_id',
                a.CategoryID 'wipro_product_categ_id',
                (CASE WHEN a.UoMID is null THEN 187 ELSE a.UoMID END) 'wipro_product_uom',
                (CASE WHEN a.Quantity IS NULL THEN 1 ELSE a.Quantity END) 'product_uom_qty',
                a.Value / (CASE WHEN a.Quantity IS NULL OR a.Quantity = 0 THEN 1 ELSE a.Quantity END) 'price_unit',
                a.Value 'price_subtotal',
                a.PayerAmount 'payer_amount',
                a.PatientAmount 'personal_amount',
                a.BillNo 'billno',
                a.BillID 'wipro_billing_id',
                a.DepartmentID 'wipro_location_id',
                SUBSTRING(a.billno, 4, 10) 'wipro_order_id',
                NULLIF(a.PrimaryDocID,0) 'wipro_primary_doc_id',
                NULLIF(a.PerformDocID,0) 'wipro_perform_doc_id',
                NULLIF(a.PrescribeDocID,0) 'wipro_prescribe_doc_id',
                a.RecordType 'type_line',
                a.DepartmentName 'department_id',
                a.RoomId 'wipro_room_id',
                a.BedId 'wipro_bed_id',
                a.AllotedBedTypeId 'wipro_alloted_bed_type_id',
                a.RevenueType 'revenue_type',
                a.SpecializationName 'item_specialisation',
                a.PatientGroupName 'patient_group',
                a.ServiceGroupName 'service_group',
                a.SpecialGroup1 'special_group',
                a.SpecialGroup2 'special_group2',
                a.BillableBedTypeName 'bed_type',
                a.PayerID 'wipro_payer',
                a.PayerCode 'payer_code',
                a.PayerType 'payer_type',
                a.PayerName 'payer_name',
                a.OrderNo 'order_no',
                a.OrderDate 'order_date',
                a.DiscountId 'wipro_discount_id',
                a.DiscountDate 'discount_date',
                a.DiscountName 'discount_name',
                a.DiscountReason 'discount_reason',
                a.DiscountLevels 'discount_level',
                a.ProvDiagnosisCode 'secondary_diagnosis_code',
                a.ProvDiagnosisName 'secondary_diagnosis_name',
                a.FinalDiagnosisCode 'primary_diagnosis_code',
                a.FinalDiagnosisName 'primary_diagnosis_name',
                a.RepeatDiagnosisCode 'repeat_diagnosis_code',
                a.RepeatDiagnosisName 'repeat_diagnosis_name',
                a.DischargeDate 'discharge_date',
                a.DischargeReason 'discharge_reason',
                a.AdmitDate 'admit_date',
                a.AdmissionType 'admission_type',
                a.RefAdmissionNumber 'ref_admission_no',
                a.TariffID 'wipro_tariff_id',
                a.BillableBedTypeID 'wipro_bed_type_id',
                a.EligibleBedTypeID 'wipro_eligible_bed_type_id',
                a.ReferralId 'wipro_referral_id',
                a.ReferralNumber 'referral_number',
                a.ReferralDoctorId 'wipro_referral_doc_id',
                a.OrderType 'order_type',
                a.SalesID 'sales_id',
                a.SaleReturnID 'sales_return_id',
                a.SalesDate 'sales_date',
                a.SaleReturnDate 'sales_return_date',
                a.BasePrice 'base_price_unit',
                a.BaseAmount 'base_price_total',
                a.HNAPrice 'hna_unit',
                a.HNAAmount 'hna_total',
                'False' AS 'narcotic',
                'False' AS 'generic',
                'False' AS 'psychotropic',
                'False' AS 'antibiotic',
                'False' AS 'is_surgery',
                'False' AS 'is_consultation',
                a.IsBaby AS 'is_baby',
                a.ParentAdmissionNo AS 'parent_admission_no',
                a.BatchId AS 'batch_id',
                (case when a.PackageID is null then 'False' else 'True' end) 'is_package',
                a.PackageName 'package_name',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN (CASE WHEN coalesce(a.GRNAMount,0) >= 0 
                        THEN (a.GRNAMount/ (case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end) ) 
                        ELSE (a.GRNAMount/-(abs((case when coalesce(a.Quantity,0)=0 then 1 else a.Quantity end)))) 
                    END) ELSE 0 END)  'cost_unit',
                (CASE WHEN a.RecordType not in('DISCOUNT','DISCOUNT CANCEL') and a.ServiceID in(10,17) 
                    THEN a.GRNAmount ELSE 0 END) 'cost_total',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_doctor_backup_id',
                COALESCE(NULLIF(a.PerformDocID,0),NULLIF(a.PrescribeDocID,0),a.PrimaryDocID) 'wipro_account_analytic_id'
            from dbo.V_Db_A_A_RawDataH30 a
            where a.RecordType = 'BILL CANCEL'
            and a.tglproses >= '%s' and a.tglproses <= '%s'
                -- and a.tglproses >= convert(datetime,'2019-01-28',121) and a.tglproses <= convert(datetime,'2019-01-30',121)
                -- and a.ServiceItemID in (61123,34674,51305,51340,51366)  
                and a.PatientType = 'Pharmacy'
                and a.AdmissionID is null
            """ % (date_start, date_end)
        print (bill_cancel_no_admission)
        data += sync.get_data(sync.servers.get(sync_type), bill_cancel_no_admission)
        print (data)
        if not data:
            print ("No data available")
            return

        values = ''
        now = tools.datetime.now().strftime('%Y%m%d %H:%M:%S')
        fields = ['tglproses', 'sync_id', 'wipro_product_id', 'name', 'wipro_product_uom', 'product_uom_qty', 'price_unit', 'price_subtotal', 'wipro_service_categ_id', 'wipro_product_categ_id', 'wipro_order_id', 'wipro_primary_doc_id', 'wipro_perform_doc_id', 'wipro_prescribe_doc_id', 'billno', 'wipro_billing_id', 'wipro_location_id', 'type_line', 'department_id', 'wipro_room_id', 'wipro_bed_id', 'wipro_alloted_bed_type_id', 'revenue_type', 'item_specialisation', 'patient_group', 'service_group', 'special_group', 'special_group2', 'bed_type', 'wipro_payer', 'payer_code', 'payer_type', 'payer_name', 'order_no', 'order_date', 'wipro_discount_id', 'discount_date', 'discount_name', 'discount_reason', 'discount_level', 'secondary_diagnosis_code', 'secondary_diagnosis_name', 'primary_diagnosis_code', 'primary_diagnosis_name', 'wipro_tariff_id', 'wipro_bed_type_id', 'wipro_eligible_bed_type_id', 'wipro_referral_id', 'referral_number', 'wipro_referral_doc_id', 'is_surgery', 'is_package', 'package_name', 'cost_unit', 'cost_total', 'wipro_doctor_backup_id', 'wipro_account_analytic_id']
        
        @asyncio.coroutine
        def process_query(object):

            object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'] = sync_type
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

        # define columns
        columns = str(tuple(field for field in fields)).replace("'", "")   
        
        # print "Insert ALL DATA"
        query = "INSERT into sale_order_line_temp %s values %s" % (columns, values)
        print (query.encode('utf8'))
        self.env.cr.execute(query)
        
        # cleansing data sale.order.line.temp
        
        # cleansing product_uom
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                product_uom = b.id
            FROM product_uom b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_product_uom 
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing order_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                order_id = b.id
            FROM sale_order b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_order_id 
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing product_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                product_id = c.id
            FROM product_template b 
            INNER JOIN product_product c ON c.product_tmpl_id = b.id
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_product_id 
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing account_analytic_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                account_analytic_id = b.id
            FROM account_analytic_account b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_account_analytic_id 
                AND b.sync_wipro_type = 'doctor_internal'
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing service_categ_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                service_categ_id = b.id
            FROM product_category b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_service_categ_id 
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing payer
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                payer = b.id
            FROM res_partner b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_payer 
                AND b.customer = true
                AND b.active = true
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing location_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                location_id = b.id
            FROM stock_location b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_location_id 
                AND b.active = true
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing primary_doc_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                primary_doc_id = b.id
            FROM account_analytic_account b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_primary_doc_id 
                AND b.sync_wipro_type = 'doctor_internal'
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing perform_doc_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                perform_doc_id = b.id
            FROM account_analytic_account b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_perform_doc_id 
                AND b.sync_wipro_type = 'doctor_internal'
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing prescribe_doc_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                prescribe_doc_id = b.id
            FROM account_analytic_account b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_prescribe_doc_id 
                AND b.sync_wipro_type = 'doctor_internal'
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing referral_doc_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                referral_doc_id = b.id
            FROM account_analytic_account b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_referral_doc_id 
                AND b.sync_wipro_type = 'doctor_internal'
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing doctor_backup_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                doctor_backup_id = b.id
            FROM account_analytic_account b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_doctor_backup_id 
                AND b.sync_wipro_type = 'doctor_internal'
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing bed_type_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                bed_type_id = b.id
            FROM hospital_bed_type b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_bed_type_id 
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing room_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                room_id = b.id
            FROM hospital_room_name b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_room_id 
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing discount_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                discount_id = b.id
            FROM hospital_discount_type b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_discount_id 
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing bed_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                bed_id = b.id
            FROM hospital_bed_name b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_bed_id 
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing eligible_bed_type_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                eligible_bed_type_id = b.id
            FROM hospital_bed_type b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_eligible_bed_type_id 
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing alloted_bed_type_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                alloted_bed_type_id = b.id
            FROM hospital_bed_type b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_alloted_bed_type_id 
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing product_categ_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                product_categ_id = b.id
            FROM product_category b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_product_categ_id 
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing billing_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                billing_id = b.id
            FROM sale_order_bill b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_billing_id 
        """
        print (query)
        self.env.cr.execute(query)

        # cleansing referral_id
        query = """"
            UPDATE sale_order_line_temp AS a SET 
                referral_id = b.id
            FROM referral_transaction b 
            WHERE b.sync_type  = a.sync_type 
                AND b.sync_id = a.wipro_referral_id 
        """
        print (query)
        self.env.cr.execute(query)

        # end cleansing data temp


        # # insert temp to sale.order.line
        # self.env.cr.execute("""
        #     INSERT INTO sale_order_line (
        #         product_uom, price_unit, product_uom_qty, price_subtotal, price_total, 
        #         order_id, discount, product_id, name, sync_date, sync_id, sync_type, 
        #         order_date, account_analytic_id, type_line, patient_type, 
        #         service_categ_id, department_id, tglproses, billno, payer, 
        #         cost_unit, cost_total, registration_code, payer_type, location_id, 
        #         primary_doc_id, perform_doc_id, prescribe_doc_id, referral_doc_id, 
        #         doctor_backup_id, bill_date, normal_uom, normal_qty, normal_price, 
        #         is_conversion, revenue_type, item_specialisation, special_group, 
        #         patient_group, service_group, cost_date, bed_type, special_group2, 
        #         service_categ_name, specialization_primary, package_name, is_package, 
        #         is_surgery, kecamatan, kelurahan, kota, order_no, payer_code, payer_name, 
        #         manufacture, secondary_diagnosis_name, secondary_diagnosis_code, 
        #         primary_diagnosis_code, primary_diagnosis_name, 
        #         repeat_diagnosis_code, repeat_diagnosis_name, ref_admission_no,
        #         admission_type, admit_date, discharge_date, discharge_reason,
        #         discount_date, discount_reason, discount_level, discount_name, 
        #         bed_type_id, room_id, discount_id, bed_id, eligible_bed_type_id, 
        #         bed_allocation_end, bed_allocation_start, alloted_bed_type_id, 
        #         product_categ_id, billing_id, referral_number, referral_id
        #     ) 
        #     SELECT 
        #         product_uom, price_unit, product_uom_qty, price_subtotal, price_total, 
        #         order_id, discount, product_id, name, sync_date, sync_id, sync_type, 
        #         order_date, account_analytic_id, type_line, patient_type, 
        #         service_categ_id, department_id, tglproses, billno, payer, 
        #         cost_unit, cost_total, registration_code, payer_type, location_id, 
        #         primary_doc_id, perform_doc_id, prescribe_doc_id, referral_doc_id, 
        #         doctor_backup_id, bill_date, normal_uom, normal_qty, normal_price, 
        #         is_conversion, revenue_type, item_specialisation, special_group, 
        #         patient_group, service_group, cost_date, bed_type, special_group2, 
        #         service_categ_name, specialization_primary, package_name, is_package, 
        #         is_surgery, kecamatan, kelurahan, kota, order_no, payer_code, payer_name, 
        #         manufacture, secondary_diagnosis_name, secondary_diagnosis_code, 
        #         primary_diagnosis_code, primary_diagnosis_name, 
        #         repeat_diagnosis_code, repeat_diagnosis_name, ref_admission_no,
        #         admission_type, admit_date, discharge_date, discharge_reason,
        #         discount_date, discount_reason, discount_level, discount_name, bed_type_id, 
        #         room_id, discount_id, bed_id, eligible_bed_type_id, 
        #         bed_allocation_end, bed_allocation_start, alloted_bed_type_id, 
        #         product_categ_id, billing_id, referral_number, referral_id
        #     FROM sale_order_line_temp 
        # """)

        # # drop if exists 
        # query = "DROP TABLE IF EXISTS sale_order_line_temp;"
        # print query 
        # self.env.cr.execute(query)

        # # update sale.order.line
        # self.env.cr.execute("""
        #     UPDATE sale_order_line
        #     SET price_total = price_subtotal 
        #     WHERE price_total is null""")
        # self.env.cr.execute("""
        #     UPDATE sale_order
        #     SET amount_total = (select sum(price_total)
        #         from sale_order_line where order_id = sale_order.id and type_line in ('BILL', 'BILL CANCEL', 'DISCOUNT', 'DISCOUNT CANCEL')) 
        #     WHERE amount_total is null""")
        # self.env.cr.execute("""
        #     UPDATE sale_order
        #     SET amount_untaxed = (select sum(price_total)
        #         from sale_order_line where order_id = sale_order.id and type_line in ('BILL', 'BILL CANCEL', 'DISCOUNT', 'DISCOUNT CANCEL')) 
        #     WHERE amount_untaxed is null""")
        # self.env.cr.execute("""
        #     UPDATE sale_order
        #     SET payer_amount = amount_total 
        #     WHERE payer_amount is null""")



    # @api.multi
    def _prepare_invoice_line(self, qty):
        """
        Prepare the dict of values to create the new invoice line for a sales order line.
        :param qty: float quantity to invoice
        """
        # self.ensure_one()
        res = {}
        # account = self.product_id.property_account_income_id or self.product_id.categ_id.property_account_income_categ_id
        # if not account:
        #     raise exceptions.UserError(_('Please define income account for this product: "%s" (id:%d)  or for its category: "%s".') % (self.product_id.name, self.product_id.id, self.product_id.categ_id.name))

        # fpos = self.order_id.fiscal_position_id or self.order_id.partner_id.property_account_position_id
        # if fpos:
        #     account = fpos.map_account(account)

        # res = {
        #     'name': self.name,
        #     'sequence':self.sequence,
        #     'origin':self.order_id.name,
        #     'account_id':account.id,
        #     'price_unit':self.price_unit,
        #     'quantity':qty,
        #     'discount':self.discount,
        #     'uom_id':self.product_uom.id,
        #     'product_id':self.product_id.id or False,
        #     'layout_category_id':self.layout_category_id and self.layout_category_id.id or False,
        #     'invoice_line_tax_ids': [(6, 0, self.tax_id.ids)],
        #     'account_analytic_id':self.account_analytic_id.id or self.order_id.project_id.id,
        #     'analytic_tag_ids': [(6, 0, self.analytic_tag_ids.ids)],
        #     'patient_id': self.order_id.partner_id.id,
        # }
        return res



    # @api.multi
    def _action_procurement_create(self):
        return

    # if self and any(record.product_id.type not in ['consu', 'product', 'service'] and not record.move_created for record in self):
    #    if not self.env.context.get('minus'):
    #       minus_lines = self.search([('id', 'in', self.ids), ('price_total', '<', 0), ('move_created', '=', False)])
    #       if minus_lines:
    #          minus_lines.with_context(minus=True)._action_procurement_create()
    #       self = self.search([('id', 'in', self.ids), ('price_total', '>', 0), ('move_created', '=', False)])
    #    if not self:
    #       return
    #    group_id = self[0].order_id.procurement_group_id or self.env['procurement.group'].create({'name': self[0].order_id.name})
    #    picking_type_id = self[0].order_id.warehouse_id.out_type_id
    #    location_id = picking_type_id.default_location_src_id
    #    location_dest_id = self.env.ref('stock.stock_location_customers')
    #    if self.env.context.get('minus'):
    #       old_location_id = location_id
    #       location_id = location_dest_id
    #       location_dest_id = old_location_id
    #       picking_type_id = self[0].order_id.warehouse_id.in_type_id
    # picking_id = self.env['stock.picking'].create({'partner_id': self[0].order_id.partner_id.id, 'min_date': self[0].order_id.date_order, 'company_id': self[0].company_id.id, 'picking_type_id': picking_type_id.id, 'location_id': location_id.id, 'location_dest_id': location_dest_id.id, 'group_id': group_id.id, 'origin': self[0].order_id.name})
    # picking_id.origin = self[0].order_id.name
    # for line in self:
    # if line.product_id.type == 'service' or line.move_created:
    # continue
    # self.env['stock.move'].create({'sale_line_id': line.id, 'picking_id': picking_id.id, 'company_id': picking_id.company_id.id, 'location_id': picking_id.location_id.id, 'location_dest_id': picking_id.location_dest_id.id, 'product_id': line.product_id.id, 'product_uom': line.product_uom.id, 'product_uom_qty': abs(line.product_uom_qty), 'price_unit': abs(line.product_id.standard_price), 'name': line.name, 'group_id': group_id.id, 'date_expected': line.order_date, 'sync_date': line.tglproses, 'tglproses': line.tglproses})
    # line.move_created = True
    # self[0].order_id.procurement_group_id = group_id
    # self[0].order_id._compute_picking_ids()
    # picking_id.action_confirm()
    # if self.env.context.get('minus'):
    # picking_id.force_assign()
    # self.write({'picking_created': True})




class SaleOrderBill(models.Model):
    _name = 'sale.order.bill'
    _rec_name = 'billno'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']
    _description = "Sales Order Bill"
    _order = 'confirmation_date desc, id desc'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    sync_is_arcus = sync.is_arcus

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=True, index=True, default=_get_company)
    admission_id = fields.Many2one('sale.order', string="Admission Rel", required=False, readonly=False)
    admission_no = fields.Char(string="Admission No.", readonly=False, index=True)
    billno = fields.Char(string="Bill No.", readonly=False, index=True)
    otc_no = fields.Char(string="OTC No.")
    confirmation_date = fields.Datetime(string='Bill Datetime', required=False, readonly=False, index=True, states={ 'draft': [('readonly', False)] }, copy=False)
    bill_date = fields.Date(string='Bill Date', required=False, readonly=False, index=True, states={ 'draft': [('readonly', False)] }, copy=False)
    discharge_date = fields.Date(string='Discharge Date', required=False, readonly=False, index=True, states={ 'draft': [('readonly', False)] }, copy=False)
    
    cancel_date = fields.Datetime(string='Cancel Date', required=False, readonly=True, index=True, copy=False)
    patient_type = fields.Selection([('1', 'OP'), ('2', 'IP'), ('3', 'Emergency'), ('4', 'Daycare'), ('5', 'MCU/Pharmacy Issues Only(FO)'), ('6', 'Pharmacy (Direct)'), ('0', 'Both')], string='Patient Type', readonly=False, index=True)
    registration_code = fields.Char(string="Patient MRID", related='partner_id.registration_code', readonly=False, index=True)
    partner_id = fields.Many2one('res.partner', string='Patient Name', readonly=False, states={ 'draft': [('readonly', False)] }, change_default=True, index=True, tracking=True)
    gender = fields.Selection(related='partner_id.gender', readonly=False)
    patient_name = fields.Char(string="Patient Name")
    age = fields.Integer(string="Age", default=1, compute='_age', store=True, readonly=True)
    age_full = fields.Char(string="Full Age", compute='_age', store=True, readonly=True)
    age_type = fields.Selection([('year', 'Year'), ('month', 'Month')], string='Age Type', related='partner_id.age_type', readonly=True)
    
    tariff_id = fields.Many2one('hospital.tariff', string="Tariff Name")
    payer_id = fields.Many2one('res.partner', string="Main Payer", domain=[('insurance', '=', True)], index=True, tracking=True)
    payer_type = fields.Char(string="Main Payer Type", readonly=False, index=True)
    payer_code = fields.Char(string="Main Payer Code", readonly=False, index=True)
    nama_asuransi = fields.Char(string="Insurance Card Name", index=True, readonly=False)
    no_asuransi = fields.Char(string="Insurance Card No.", index=True, readonly=False)
    penjualanresep = fields.Boolean(string="OTC Bill", default=False, store=True)

    already_merged = fields.Boolean(string="Already Merged", default=False)
    merged_id = fields.Many2one('sale.order.bill', string="Merged Bill No.", index=True)
    merged_bill = fields.Boolean(string="Is Merged", default=False)

    cob_bill = fields.Boolean(string="COB Bill", default=False, store=True)
    cob_billno = fields.Char(string="COB Bill No.", readonly=False, index=True)
    cob_sequence = fields.Integer(string="COB Sequence", default=False, store=True)
    note = fields.Text(string='Notes')

    is_bpjs = fields.Boolean(string="Is BPJS", default=False, store=True)
    inacbgs_code = fields.Char(string="INACBGs Code")
    inacbgs_amount = fields.Float(string="INACBGs Amount")
    
    primary_doc_id = fields.Many2one('account.analytic.account', string="Primary Doctor", domain=[('sync_wipro_type', '=', 'doctor_internal')], index=True, required=False)
    referral_doc_id = fields.Many2one('account.analytic.account', string="Referral Doctor", domain=[('sync_wipro_type', '=', 'doctor_internal')], index=True)
    referral_id = fields.Many2one('referral.transaction', string="Referral Trans", index=True)
    referral_number = fields.Char(string="Referral No.", readonly=False, index=True)

    covering_id = fields.Many2one('account.coveringletter', string="Covering No.")
    payment_id = fields.Many2one('account.payment', string="Receipt No.")

    covering_ids = fields.Many2many('account.coveringletter', relation="account_coveringletter_bill_rel", string="Covering Letter", tracking=True)
    discount_ids = fields.One2many('account.creditnote.line', 'billing_sale_id', string="Credit Notes")
    payment_ids = fields.One2many('account.payment.bill.rel', 'sale_order_bill_id', string="Receipts")
    history_ids = fields.One2many('sale.order.bill.history', 'billing_id', string="Outstanding History")

    secondary_diagnosis_code = fields.Char(string="Secondary Diagnosis Code", readonly=True, index=True)
    secondary_diagnosis_name = fields.Char(string="Secondary Diagnosis Name", readonly=True, index=True)
    primary_diagnosis_code = fields.Char(string="Primary Diagnosis Code", readonly=True, index=True)
    primary_diagnosis_name = fields.Char(string="Primary Diagnosis Name", readonly=True, index=True)
    repeat_diagnosis_code = fields.Char(string="Repeat Diagnosis Code", readonly=True, index=True)
    repeat_diagnosis_name = fields.Char(string="Repeat Diagnosis Name", readonly=True, index=True)

    total_gross = fields.Float(string="Total Gross", tracking=True)
    total_amount = fields.Float(string="Total Nett.", tracking=True)
    service_tax = fields.Float(string="Service Tax (HIS)")

    personal_gross = fields.Float(string="Personal Gross")
    personal_rounding = fields.Float(string="Personal RoundOff")
    personal_discount = fields.Float(string="Personal Disc. Bill", store=True)
    personal_canceled = fields.Float(string="Personal Canceled", store=True)
    personal_amount = fields.Float(string="Personal Nett. Amount", tracking=True, store=True)
    personal_receipt = fields.Float(string="Personal Receipt")
    personal_deposit_availed = fields.Float(string="Personal Deposit Availed")
    personal_refund = fields.Float(string="Personal Refund")
    personal_balance = fields.Float(string="Personal Balance")
    tpa_id = fields.Char(string='TPA ID.')
    tpa_code = fields.Char(string='TPA Code')
    tpa_name = fields.Char(string='TPA Name')
    
    payer_gross = fields.Float(string="Main Payer Gross")
    payer_rounding = fields.Float(string="Main Payer RoundOff")
    payer_deduction = fields.Float(string="Main Payer Disc. Bill")
    payer_canceled = fields.Float(string="Main Payer Canceled")
    payer_amount = fields.Float(string="Main Payer Nett. Amount", tracking=True, store=True)
    payer_adjustment = fields.Float(string="Main Payer Disc. Invoice")
    payer_credit = fields.Float(string="Main Payer Invoiced")
    payer_receipt = fields.Float(string="Main Payer Receipt")
    payer_discount = fields.Float(string="Main Payer WriteOff")
    payer_balance = fields.Float(string="Main Payer Balance")
    
    subpayer_gross = fields.Float(string="Sub Payer Gross", tracking=True, store=True)
    subpayer_rounding = fields.Float(string="Sub Payer RoundOff")
    subpayer_canceled = fields.Float(string="Sub Payer Canceled")
    subpayer_deduction = fields.Float(string="Sub Payer Disc. Bill", tracking=True, store=True)
    subpayer_amount = fields.Float(string="Sub Payer Nett. Amount", tracking=True, store=True)

    state = fields.Selection([('draft', 'New Admission'), ('done', 'Close Bill'), ('cancel', 'Cancel Bill'),('invoice', 'Invoiced')], string='Status', readonly=True, copy=False, index=True, tracking=True, default='draft')
    scroll_receipt_ids = fields.One2many('scroll.receipt.cashier','billing_id',string="Scroll Receipt Cashier", ondelete='set null')
    inpatient_deposit_ids = fields.One2many('inpatient.deposit','billing_id',string="Deposit Collection", ondelete='set null')
    order_line = fields.One2many('sale.order.line','billing_id',string="Order Lines")
    invoice_status = fields.Selection([('upselling', 'Upselling Opportunity'),('invoiced', 'Fully Invoiced'),('to invoice', 'To Invoice'),('no', 'Nothing to Invoice')], string='Invoice Status')
    cob_line = fields.One2many('sale.order.cob','billing_id',string="COB Billing")
    billing_ids = fields.One2many('sale.order.bill', 'merged_id', string="Sub Billing")
    is_sent_voucher = fields.Boolean(string="Flag Send Voucher", readonly=True, default=False)
    is_sent_bsl = fields.Boolean(string="Flag Send BSL", readonly=True, default=False)
    message_last_post = fields.Datetime(string="Message Last Post", index=True, readonly=True)

    arcus_invoice_letter_ids = fields.One2many('receivable.invoice.letter', 'odoo_bill_id', string="Arcus Invoice Letter")
    arcus_invoice_letter_amount = fields.Float(string="Arcus Invoice Letter Amount",compute='_compute_arcus_invoice_letter_amount')
    arcus_invoice_letter_amount_store = fields.Float(string="Arcus Invoice Letter Amount Store", store=True)

    # @api.multi
    def _compute_arcus_invoice_letter_amount(self):
        for s in self:
            if s.arcus_invoice_letter_ids:
                for bill in s.arcus_invoice_letter_ids:
                    s.arcus_invoice_letter_amount += bill.payor_balance

    @api.model
    def create(self, vals):
        # validation input billing
        # check_bill = self.env['sale.order.bill'].search([('billno','=', vals['billno']), ('sync_type','=', vals['sync_type'])])
        # check_bill = self.env['sale.order.bill'].search([('billno','=', vals['billno']), ('company_id','=', vals['company_id'])])
        #if check_bill:
        #    raise exceptions.ValidationError("Billing No : {billno} has been created.".format(billno=vals['billno']))  
            
        result = super(SaleOrderBill, self).create(vals)
        if not result.billno:
            result.billno = self.env['ir.sequence'].sudo().next_by_code('sale.order.bill.seq')
        
        for record in result:
            # 2021.08.03 override confirmation_date -7 hours
            if record.confirmation_date and record.sync_id_api:
                date_wib = tools.datetime.strptime(record.confirmation_date,'%Y-%m-%d %H:%M:%S') - tools.timedelta(hours=7)
                record.confirmation_date = date_wib
                record.bill_date = date_wib.strftime('%Y-%m-%d')

            # 2021.08.03 override cancel_date -7 hours
            if record.cancel_date and record.sync_id_api:
                date_wib = tools.datetime.strptime(record.cancel_date,'%Y-%m-%d %H:%M:%S') - tools.timedelta(hours=7)
                record.cancel_date = date_wib

            # 2021.10.06 - rounding payer amount 
            if record.payer_amount and record.sync_id_api:
                payer_amount = round(record.payer_amount, 0)
                payer_rounding = record.payer_amount - payer_amount 
                record.payer_amount = payer_amount 
                record.payer_rounding = payer_rounding
            
            if record.state == 'done':
                record.action_history(remark="UNBILLED")

        return result




    # @api.multi
    def write(self, values):

        # 2021.09.11 - Bug fixing by pass update cancel billing untuk invoice yang sudah di CL
        if values.get('state') and self.sync_id_api:
            if self.state == 'invoice' and str(values.get('state')) == 'cancel':
                raise exceptions.UserError("Billing yang sudah di invoice tidak dapat di cancel.")

        result = super(SaleOrderBill, self).write(values)
        if self.env.context.get('ganti_date'): return result
        self = self.with_context(ganti_date=True)

        if values.get('confirmation_date') and self.sync_id_api:
            date_wib = tools.datetime.strptime(str(values.get('confirmation_date')), '%Y-%m-%d %H:%M:%S') - tools.timedelta(hours=7)
            if self.confirmation_date and date_wib:
               self.confirmation_date = date_wib
               self.bill_date = date_wib.strftime('%Y-%m-%d')

        if values.get('cancel_date') and self.sync_id_api:
            date_wib = tools.datetime.strptime(str(values.get('cancel_date')), '%Y-%m-%d %H:%M:%S') - tools.timedelta(hours=7)
            if self.cancel_date and date_wib:
               self.cancel_date = date_wib

        # 2021.10.06 - rounding payer amount 
        if values.get('payer_amount') and self.sync_id_api:
            payer_amount = round(float(values.get('payer_amount')), 0)
            payer_rounding = float(values.get('payer_amount')) - payer_amount 
            self.payer_amount = payer_amount 
            self.payer_rounding = payer_rounding

        if values.get('state'):
            if str(values.get('state')) == 'cancel':
                self.action_history("CANCEL BILLING")
            if str(values.get('state')) == 'done':
                self.action_history("UNBILLED")

        return result




    # @api.one
    @api.depends('confirmation_date', 'partner_id', 'partner_id.date_of_birth')
    def _age(self):
        if self.partner_id.date_of_birth:
            age = tools.relativedelta(datetime.strptime(str(self.confirmation_date), '%Y-%m-%d %H:%M:%S'), datetime.strptime(str(self.partner_id.date_of_birth),'%Y-%m-%d'))
            self.age = age.years
            self.age_full = "%s years and %s months" % (age.years, age.months)



    # @api.multi
    def action_cancel(self):
        current = tools.datetime.strptime(tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'%Y-%m-%d %H:%M:%S')
        for record in self:
            record.write({'state': 'cancel', 'cancel_date':current})
            for cob in record.cob_line:
                cob.write({'state': 'cancel', 'cancel_date':current})
        return



    # @api.multi
    def action_done(self):
        current = tools.datetime.strptime(tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'%Y-%m-%d %H:%M:%S')
        for record in self:
            if record.confirmation_date:
                #confirm_date = tools.datetime.strptime(record.confirmation_date.strftime('%Y-%m-%d %H:%M:%S'),'%Y-%m-%d %H:%M:%S')
                record.write({'state': 'done'})
            else:
                confirm_date = current
                record.write({'state': 'done', 'confirmation_date':confirm_date})

            for cob in record.cob_line:
                cob.write({'state': 'done', 'cancel_date':None})
        return



    # @api.multi
    def action_draft(self):
        current = tools.datetime.strptime(tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'%Y-%m-%d %H:%M:%S')
        for record in self:
            record.write({'state': 'draft', 'cancel_date':None})
            for cob in record.cob_line:
                cob.write({'state': 'draft', 'cancel_date':None})
        return



    # 2022.09.01 - Cancel History
    # @api.multi
    def cancel_history(self, letter_id=None, credit_id=None, receipt_id=None, advance_id=None):
        if letter_id:
            self.history_ids.filtered(lambda x: x.letter_id.id == letter_id).write({'active': False})
        if credit_id:
            self.history_ids.filtered(lambda x: x.credit_id.id == credit_id).write({'active': False})
        if receipt_id:
            self.history_ids.filtered(lambda x: x.receipt_id.id == receipt_id).write({'active': False})
        if advance_id:
            self.history_ids.filtered(lambda x: x.advance_id.id == advance_id).write({'active': False})
            


    # 2021.09.17 - Create History Outstanding per Billing 
    # @api.multi 
    def action_history(self, remark="", trans_date=None, letter_id=None, credit_id=None, receipt_id=None, advance_id=None):
        for record in self:
            current = tools.datetime.strptime(tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'%Y-%m-%d %H:%M:%S')
            
            if trans_date:
                query = """
                 select count(*) hitung
                 from sale_order_bill_history a
                 inner join sale_order_bill b on b.id = a.billing_id
                 where a.billing_id = {billing_id}
                     and date(a.datetime) > date('{date}')
                     and a.active = True
                """.format(
                    billing_id=record.id,
                    date=trans_date
                )
                self.env.cr.execute(query)
                print (query.encode('utf-8'))
                datas = self.env.cr.dictfetchall()
                hitung = datas[0]['hitung']
                if hitung == 0:
                    current = trans_date

            row = {}
            row['billing_id'] = record.id 
            row['datetime'] = current 
            row['payer_deduction'] = record.payer_deduction
            row['payer_canceled'] = record.payer_canceled
            row['payer_amount'] = record.payer_amount
            row['payer_adjustment'] = record.payer_adjustment
            row['payer_credit'] = record.payer_credit
            row['payer_receipt'] = record.payer_receipt 
            row['payer_discount'] = record.payer_discount
            row['payer_balance'] = record.payer_balance
            row['state'] = record.state
            row['remark'] = remark

            row['letter_id'] = letter_id or None
            row['credit_id'] = credit_id or None 
            row['receipt_id'] = receipt_id or None
            row['advance_id'] = advance_id or None
            #row['company_id'] = record.company_id.id or None
            record.history_ids.create(row)


    # 2021.12.31 create history unbilled report
    # @api.multi 
    def action_unbilled(self, remark=""):
        for record in self:
            # check init first unbilled record
            query = """
                select count(*) hitung
                from sale_order_bill_history a
                inner join sale_order_bill b on b.id = a.billing_id
                where a.billing_id = {billing_id}
                    and a.state = 'done'
                    and date(a.datetime) = date(b.confirmation_date)
            """.format(billing_id=record.id)
            self.env.cr.execute(query)
            print (query.encode('utf-8'))
            datas = self.env.cr.dictfetchall()
            hitung = datas[0]['hitung']

            # jika belum pernah ada unbilled history
            if hitung == 0:
                current = tools.datetime.strptime(tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'%Y-%m-%d %H:%M:%S')
                row = {}
                row['billing_id'] = record.id 
                row['datetime'] = record.confirmation_date 
                row['payer_deduction'] = record.payer_deduction
                row['payer_canceled'] = record.payer_canceled
                row['payer_amount'] = record.payer_amount
                row['payer_adjustment'] = record.payer_adjustment
                row['payer_credit'] = record.payer_credit
                row['payer_receipt'] = record.payer_receipt 
                row['payer_discount'] = record.payer_discount
                row['payer_balance'] = record.payer_balance
                row['state'] = record.state
                row['remark'] = remark
                record.history_ids.create(row)


    # 2021.06.16 
    # Auto bug fixing untuk admission_id relation yg missing ke sale.order
    # Mesti auto generate daily based on admission_no yg dikirim dhealth ke odoo
    # @api.multi
    def query_bill_update(self):
        print ("Selesai Narik, Start Query UPDATE sale.order.bill")
        self.env.cr.execute("""
            update sale_order_bill AS a SET 
                admission_id = b.id 
            from sale_order b
            where trim(b.name) = trim(a.admission_no)
                and a.sync_type = b.sync_type 
                and a.sync_id_api is not null 
                and a.admission_id is null 
                and date(a.confirmation_date) >= '2021-05-30'
                and date(a.confirmation_date) >= (CURRENT_DATE-30) """)
        print ("Selesai")

        self.env.cr.execute("""
            update sale_order_bill AS a SET 
                payer_id = (select b.id from res_partner b 
                    where b.vendor_code=a.payer_code 
                        and b.insurance=true 
                        and b.active=true 
                        and b.sync_id_api is not null
                    order by b.id asc limit 1)
            where a.payer_id is null 
                and a.sync_id_api is not null""")
        print ("Selesai")



#     @api.model
#     def _sync_sale_bill_wipro(self, sync_type='1'):
#         sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)])}
#         sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
#         data = []
#         date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
#         # date = '2019-01-25'
#         query_admission = """
#             SELECT 
#                 tglproses,
#                 sync_id,
#                 convert(varchar(19), dateadd(hour, -7, confirmation_date), 121) confirmation_date,
#                 convert(varchar(10), confirmation_date, 121) bill_date,
#                 convert(varchar(19), dateadd(hour, -7, cancel_date), 121) cancel_date,
#                 billno,
#                 partner_id,
#                 partner_name,
#                 admission_id,
#                 admission_no,
#                 patient_type,
#                 tariff_id,
#                 payer_id,
#                 payer_code,
#                 payer_name,
#                 payer_type,
#                 primary_doc_id,
#                 referral_doc_id,
#                 referral_id,
#                 referral_number,
#                 secondary_diagnosis_code,
#                 secondary_diagnosis_name,
#                 primary_diagnosis_code,
#                 primary_diagnosis_name,
#                 repeat_diagnosis_code,
#                 repeat_diagnosis_name,
#                 bed_type_id,
#                 alloted_bed_type_id,
#                 eligible_bed_type_id,
#                 note,
#                 service_tax,
#                 total_amount,
#                 payer_rounding,
#                 payer_amount,
#                 personal_amount,
#                 personal_rounding,
#                 personal_discount,
#                 personal_receipt,
#                 personal_balance,
#                 state,
#                 penjualanresep
#             FROM dbo.VRP_OdooSaleOrderBill a 
#             WHERE a.tglproses = '%s'
#             """ % (date)
#         values = ''
#         data += sync.get_data(sync.servers.get(sync_type), query_admission)
#         fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and 'ids' not in key and self._fields[key].required == True and self._fields[key].store == True)
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
#         now = tools.datetime.now().strftime('%Y%m%d %H:%M:S')
#         default_values['company_id'] = self.env.company.id
#         #uom_id = self.env.ref('product.product_uom_categ_unit').id
#         new_sync_ids = []
#         for object in data:
#             new_sync_ids += [object['sync_id']]
#             for value in default_values:
#                 if value in object:
#                     continue
#                 object[value] = default_values[value]
#             partner_id = object['partner_id']
            

#             if object['payer_type'] == 'PRIVATE':
#                 object['payer_id'] = 5817
#             else:
#                 object['payer_id'] = self.env['res.partner'].search([('sync_id', '>', 0), ('sync_id', '=', object['payer_id']),('sync_type', '=', sync_type), ('insurance', '=', True)],limit=1).id or None

#             object['partner_id'] = self.env['res.partner'].search([('sync_id', '>', 0), ('sync_id', '=', object['partner_id']), ('sync_type', '=', sync_type), ('patient', '=', True)], limit=1)

            
#             if object['admission_id']: 
#                 object['admission_id'] = self.env['sale.order'].search([('sync_id', '=', object['admission_id']), ('sync_type', '=', sync_type)], limit=1).id or None
#             if object['primary_doc_id']:
#                 object['primary_doc_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1).id or self.env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1).id or self.env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1).id or None 
#             if object['referral_doc_id']:
#                 object['referral_doc_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['referral_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1).id or None
#             if object['referral_id']:
#                 object['referral_id'] = self.env['referral.transaction'].search([('sync_id', '=', object['referral_id']), ('sync_type', '=', sync_type)], limit=1).id or None            
#             if object['tariff_id']:
#                 object['tariff_id'] = self.env['hospital.tariff'].search([('sync_id', '=', object['tariff_id']), ('sync_type', '=', sync_type)], limit=1).id or None            
#             if object['bed_type_id']:
#                 object['bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['bed_type_id']), ('sync_type', '=', sync_type)], limit=1).id or None            
#             if object['alloted_bed_type_id']:
#                 object['alloted_bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['eligible_bed_type_id']), ('sync_type', '=', sync_type)], limit=1).id or None
#             if object['eligible_bed_type_id']: 
#                 object['eligible_bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['alloted_bed_type_id']), ('sync_type', '=', sync_type)], limit=1).id or None
                        
#             if not object['partner_id']:
#                 open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + "pasien res.partner with sync_id %s and sync_type %s doesn't exist" % (partner_id, sync_type))
#                 # object['backup_partner_id'] = object['partner_id']
#                 object['partner_id'] = self.env['res.partner'].search([('sync_id', '=', 99881177), ('sync_type', '=', sync_type), ('patient', '=', True)], limit=1)
#                 # return
#             object['partner_id'] = object['partner_id'].id
#             if int(object['sync_id']) in sync_ids:
#                 object['id'] = sync_ids[object['sync_id']]
#             else:
#                 object['id'] = 'DEFAULT'
#             object['sync_date'] = now
#             object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
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
#                 if isinstance(object[field], str):
#                     string = object[field]
#                     value += "'" + string.replace("'", "''") + "'"
#                     continue
#                 value += sync.json(object[field])
#             value += ')'
#             values += value
#         excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
#         columns = sync.remove_unicode(str(fields)).replace("'", "")
#         columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
#         print (values.encode('utf-8'))
#         if not values:
#             print ("No data available")
#             return
#         query = "INSERT into sale_order_bill %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
#         print (query.encode('utf8'))
#         self.env.cr.execute(query)
#         # self.env.cr.execute("""UPDATE sale_order_bill as s set confirmation_date = s.date_order - (interval '14 hour'), updated_date = True where s.updated_date is null""")



#     @api.model
#     def _sync_sale_bill_wipro_manual(self, sync_type='1', date='2021-01-01'):
#         sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)])}
#         sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
#         data = []
#         # date = '' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
#         # date = '2019-01-25'
#         query_admission = """
#             SELECT 
#                 tglproses,
#                 sync_id,
#                 convert(varchar(19), dateadd(hour, -7, confirmation_date), 121) confirmation_date,
#                 convert(varchar(10), confirmation_date, 121) bill_date,
#                 convert(varchar(19), dateadd(hour, -7, cancel_date), 121) cancel_date,
#                 billno,
#                 partner_id,
#                 partner_name,
#                 admission_id,
#                 admission_no,
#                 patient_type,
#                 tariff_id,
#                 payer_id,
#                 payer_code,
#                 payer_name,
#                 payer_type,
#                 primary_doc_id,
#                 referral_doc_id,
#                 referral_id,
#                 referral_number,
#                 secondary_diagnosis_code,
#                 secondary_diagnosis_name,
#                 primary_diagnosis_code,
#                 primary_diagnosis_name,
#                 repeat_diagnosis_code,
#                 repeat_diagnosis_name,
#                 bed_type_id,
#                 alloted_bed_type_id,
#                 eligible_bed_type_id,
#                 note,
#                 service_tax,
#                 total_amount,
#                 payer_amount,
#                 payer_rounding,
#                 personal_amount,
#                 personal_rounding,
#                 personal_discount,
#                 personal_receipt,
#                 personal_balance,
#                 state,
#                 penjualanresep
#             FROM dbo.VRP_OdooSaleOrderBill a 
#             WHERE a.tglproses = '%s'
#             --where a.tglproses = '2021-08-26'
#             --   and a.billno in('ICS210000987','OCR200068980')
#             """ % (date)
#         values = ''
#         data += sync.get_data(sync.servers.get(sync_type), query_admission)
#         fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and 'ids' not in key and self._fields[key].required == True and self._fields[key].store == True)
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
#         now = tools.datetime.now().strftime('%Y%m%d %H:%M:S')
#         default_values['company_id'] = self.env.company.id
#         #uom_id = self.env.ref('product.product_uom_categ_unit').id
#         new_sync_ids = []
#         for object in data:
#             new_sync_ids += [object['sync_id']]
#             for value in default_values:
#                 if value in object:
#                     continue
#                 object[value] = default_values[value]
#             partner_id = object['partner_id']
#             object['partner_id'] = self.env['res.partner'].search([('sync_id', '>', 0), ('sync_id', '=', object['partner_id']), ('sync_type', '=', sync_type), ('patient', '=', True)], limit=1)
            
#             if object['payer_type'] == 'PRIVATE':
#                 object['payer_id'] = 5817
#             else:
#                 object['payer_id'] = self.env['res.partner'].search([('sync_id', '>', 0), ('sync_id', '=', object['payer_id']),('sync_type', '=', sync_type), ('insurance', '=', True)],limit=1).id or None

#             if object['admission_id']: 
#                 object['admission_id'] = self.env['sale.order'].search([('sync_id', '=', object['admission_id']), ('sync_type', '=', sync_type)], limit=1).id or None
#             if object['primary_doc_id']:
#                 object['primary_doc_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1).id or self.env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1).id or self.env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1).id or None
#             if object['referral_doc_id']:
#                 object['referral_doc_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['referral_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1).id or None
#             if object['referral_id']:
#                 object['referral_id'] = self.env['referral.transaction'].search([('sync_id', '=', object['referral_id']), ('sync_type', '=', sync_type)], limit=1).id or None            
#             if object['tariff_id']:
#                 object['tariff_id'] = self.env['hospital.tariff'].search([('sync_id', '=', object['tariff_id']), ('sync_type', '=', sync_type)], limit=1).id or None            
#             if object['bed_type_id']:
#                 object['bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['bed_type_id']), ('sync_type', '=', sync_type)], limit=1).id or None            
#             if object['alloted_bed_type_id']:
#                 object['alloted_bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['eligible_bed_type_id']), ('sync_type', '=', sync_type)], limit=1).id or None
#             if object['eligible_bed_type_id']: 
#                 object['eligible_bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['alloted_bed_type_id']), ('sync_type', '=', sync_type)], limit=1).id or None
                            
#             if not object['partner_id']:
#                 open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + "pasien res.partner with sync_id %s and sync_type %s doesn't exist" % (partner_id, sync_type))
#                 # object['backup_partner_id'] = object['partner_id']
#                 object['partner_id'] = self.env['res.partner'].search([('sync_id', '=', 99881177), ('sync_type', '=', sync_type), ('patient', '=', True)], limit=1)
#                 # return
#             object['partner_id'] = object['partner_id'].id
#             if int(object['sync_id']) in sync_ids:
#                 object['id'] = sync_ids[object['sync_id']]
#             else:
#                 object['id'] = 'DEFAULT'
#             object['sync_date'] = now
#             object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
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
#                 if isinstance(object[field], str):
#                     string = object[field]
#                     value += "'" + string.replace("'", "''") + "'"
#                     continue
#                 value += sync.json(object[field])
#             value += ')'
#             values += value
#         excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
#         columns = sync.remove_unicode(str(fields)).replace("'", "")
#         columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
#         print (values.encode('utf-8'))
#         if not values:
#             print ("No data available")
#             return
#         query = "INSERT into sale_order_bill %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
#         print (query.encode('utf8'))
#         self.env.cr.execute(query)
#         # self.env.cr.execute("""UPDATE sale_order as s set date_order = s.date_order - (interval '14 hour'), updated_date = True where s.updated_date is null""")



    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(SaleOrderBill,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Billing" delete="false" decoration-danger="state == 'cancel'" decoration-info="state == 'draft'" decoration-success="state=='invoice'">
                    <field name="billno"/>
                    <field name="bill_date"/>
                    <field name="admission_id"/>
                    <field name="patient_type"/>
                    <field name="partner_id"/>
                    <field name="payer_id"/>
                    <field name="total_amount"/>
                    <field name="covering_ids" widget='one2many'/> 
                    <field name="state"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Billing..">
                    <filter string="Admission" domain="[('state','=', 'draft')]" help="Admission"/>
                    <filter string="Close Bill" domain="[('state','=', 'done')]" help="Close Bill"/>
                    <filter string="Cancel Bill" domain="[('state','=', 'cancel')]" help="Cancel Bill"/>
                    <filter string="Invoiced Bill" domain="[('state','=', 'invoice')]" help="Invoice Bill"/>
                    <separator/>
                    <filter string="Already Merged" domain="[('already_merged','=', True)]" help="Billing has been merged."/>
                    <filter string="Merged Bill" domain="[('merged_bill','=', True)]" help="Is Merged billing"/>
                    <filter string="COB Bill" domain="[('cob_bill','=', True)]" help="Billing has been splited to COB"/>
                    <separator/>
                    <filter string="From Arcus" domain="[('sync_is_arcus','=', True)]" help="From Arcus"/>
                    <separator/>
                    <field name="billno"/>
                    <field name="admission_id"/>
                    <field name="partner_id"/>
                    <field name="payer_id"/>
                    <field name="order_line"/>
                    <field name="merged_id"/>
                </search>"""
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res






# 2021.09.17 - Billing historycall table 
class SaleOrderBillHistory(models.Model):
    _name = 'sale.order.bill.history'
    _rec_name = 'billing_id'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    sync_id = sync.id
    sync_type = sync.type
    sync_id_api = sync.id_api 
    sync_date = sync.date 
    sync_consol_date = sync.consol_date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main

    billing_id = fields.Many2one('sale.order.bill', string="Billing No.")
    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=True, index=True, default=_get_company)
    
    datetime = fields.Datetime(string="Datetime")
    payer_deduction = fields.Float(string="Payer Disc. Bill")
    payer_canceled = fields.Float(string="Payer Canceled")
    payer_amount = fields.Float(string="Payer Nett. Amount")
    payer_adjustment = fields.Float(string="Payer Discount (Invoice)")
    payer_credit = fields.Float(string="Payer Credit")
    payer_receipt = fields.Float(string="Payer Receipt")
    payer_discount = fields.Float(string="Payer WriteOff")
    payer_balance = fields.Float(string="Payer Balance")
    state = fields.Selection([('cancel','Cancel Billing'), ('draft','New Admission'), ('done','Close Bill'), ('invoice','Invoiced Bill')], string="State")
    remark = fields.Char(string="Remark")

    letter_id = fields.Many2one('account.coveringletter', string="Letter No.")
    credit_id = fields.Many2one('account.creditnote', string="WriteOff No.")
    receipt_id = fields.Many2one('account.payment', string="Receipt No.")
    advance_id = fields.Many2one('account.advance.realization', string="Advance No.")
    active = fields.Boolean(default=True, string="Active")







class SaleOrderCob(models.Model):
    _name = 'sale.order.cob'
    _rec_name = 'cob_no'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']
    _description = "Sales Order COB"
    _order = 'cob_date desc, id desc'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=True, index=True, default=_get_company)
    billing_id = fields.Many2one('sale.order.bill', string="Main Billing", required=True, readonly=True)
    admission_id = fields.Many2one('sale.order', string="Admission No.", required=True, readonly=True)
    cob_no = fields.Char(string="COB No.", readonly=False, index=True)
    cob_date = fields.Datetime(string='COB Date', required=True, readonly=False, index=True, states={ 'draft': [('readonly', False)] }, copy=False)
    cancel_date = fields.Datetime(string='Cancel Date', required=False, readonly=True, index=True, copy=False)
    payer_id = fields.Many2one('res.partner', string="COB Payer", domain=[('insurance', '=', True)], index=True)
    note = fields.Text(string='Notes')

    payer_amount = fields.Float(string="COB Nett. Amount", tracking=True, store=True)
    payer_adjustment = fields.Float(string="COB Disc. Invoice")
    payer_credit = fields.Float(string="COB Invoiced")
    payer_receipt = fields.Float(string="COB Receipt")
    payer_discount = fields.Float(string="COB Discount")
    payer_balance = fields.Float(string="COB Balance")

    covering_id = fields.Many2one('account.coveringletter', string="Covering No.")
    payment_id = fields.Many2one('account.payment', string="Receipt No.")
    covering_ids = fields.Many2many('account.coveringletter', relation="account_coveringletter_cob_rel", string="Covering Letter", tracking=True)
    discount_ids = fields.One2many('account.creditnote.line', 'billing_cob_id', string="Credit Notes")
    payment_ids = fields.One2many('account.payment.cob.rel', 'sale_order_cob_id', string="Receipts")
    history_ids = fields.One2many('sale.order.cob.history', 'cob_id', string="Outstanding History")

    state = fields.Selection([('draft', 'New Admission'), ('done', 'Close Bill'), ('cancel', 'Cancel Bill'),('invoice', 'Invoiced')], string='Status', readonly=True, copy=False, index=True, tracking=True, default='draft')
    order_line = fields.One2many('sale.order.line','cob_id',string="Order Lines")
    sub_order_line = fields.One2many('sale.order.line','sub_cob_id',string="Sub Order Lines")
    invoice_status = fields.Selection([('upselling', 'Upselling Opportunity'),('invoiced', 'Fully Invoiced'),('to invoice', 'To Invoice'),('no', 'Nothing to Invoice')], string='Invoice Status')

    # @api.multi
    def write(self, values):

        # 2021.09.11 - Bug fixing by pass update cancel billing untuk invoice yang sudah di CL
        if values.get('state') and self.sync_id_api:
            if self.state == 'invoice' and str(values.get('state')) == 'cancel':
                raise exceptions.UserError("Billing yang sudah di invoice tidak dapat di cancel.")

        result = super(SaleOrderCob, self).write(values)
        if self.env.context.get('ganti_date'): return result
        self = self.with_context(ganti_date=True)

        if values.get('state'):
            if str(values.get('state')) == 'cancel':
                self.action_history("CANCEL BILLING")
            if str(values.get('state')) == 'done':
                self.action_history("UNBILLED")

        return result

    # @api.multi
    def action_cancel(self):
        current = tools.datetime.strptime(tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'%Y-%m-%d %H:%M:%S')
        for record in self:
            record.write({'state': 'cancel', 'cancel_date':current})
        return

    # @api.multi
    def action_done(self):
        current = tools.datetime.strptime(tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'%Y-%m-%d %H:%M:%S')
        for record in self:
            record.write({'state': 'done', 'confirmation_date':current})
        return

    # @api.multi
    def action_draft(self):
        current = tools.datetime.strptime(tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'%Y-%m-%d %H:%M:%S')
        for record in self:
            record.write({'state': 'draft', 'confirmation_date':None, 'cancel_date':None})
        return



    # 2022.09.01 - Cancel History
    # @api.multi
    def cancel_history(self, letter_id=None, credit_id=None, receipt_id=None, advance_id=None):
        if letter_id:
            self.history_ids.filtered(lambda x: x.letter_id.id == letter_id).write({'active': False})
        if credit_id:
            self.history_ids.filtered(lambda x: x.credit_id.id == credit_id).write({'active': False})
        if receipt_id:
            self.history_ids.filtered(lambda x: x.receipt_id.id == receipt_id).write({'active': False})
        if advance_id:
            self.history_ids.filtered(lambda x: x.advance_id.id == advance_id).write({'active': False})
            

    # 2021.09.17 - Create History Outstanding per COB Billing 
    # @api.multi 
    def action_history(self, remark="", trans_date=None, letter_id=None, credit_id=None, receipt_id=None, advance_id=None):
        for record in self:
            current = tools.datetime.strptime(tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'%Y-%m-%d %H:%M:%S')
            
            if trans_date:
                query = """
                 select count(*) hitung
                 from sale_order_cob_history a
                 inner join sale_order_cob b on b.id = a.cob_id
                 where a.cob_id = {billing_id}
                     and date(a.datetime) > date('{date}')
                     and a.active = True
                """.format(
                    billing_id=record.id,
                    date=trans_date
                )
                self.env.cr.execute(query)
                print (query.encode('utf-8'))
                datas = self.env.cr.dictfetchall()
                hitung = datas[0]['hitung']
                if hitung == 0:
                    current = trans_date

            row = {}
            row['cob_id'] = record.id 
            row['datetime'] = current 
            row['payer_amount'] = record.payer_amount
            row['payer_adjustment'] = record.payer_adjustment
            row['payer_credit'] = record.payer_credit
            row['payer_receipt'] = record.payer_receipt 
            row['payer_discount'] = record.payer_discount
            row['payer_balance'] = record.payer_balance
            row['state'] = record.state
            row['remark'] = remark

            row['letter_id'] = letter_id or None
            row['credit_id'] = credit_id or None 
            row['receipt_id'] = receipt_id or None
            row['advance_id'] = advance_id or None
            record.history_ids.create(row)



    # 2021.12.31 - create history unbilled report
    # @api.multi 
    def action_unbilled(self, remark=""):
        for record in self:
            # check init first unbilled record
            query = """
                select count(*) hitung
                from sale_order_cob_history a
                inner join sale_order_cob b on b.id = a.cob_id
                where a.cob_id = {cob_id}
                    and a.state = 'done'
                    and date(a.datetime) = date(b.cob_date)
            """.format(cob_id=record.id)
            self.env.cr.execute(query)
            print (query.encode('utf-8'))
            datas = self.env.cr.dictfetchall()
            hitung = datas[0]['hitung']

            # jika belum pernah ada unbilled history
            if hitung == 0:
                current = tools.datetime.strptime(tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'%Y-%m-%d %H:%M:%S')
                row = {}
                row['cob_id'] = record.id 
                row['datetime'] = record.cob_date 
                row['payer_amount'] = record.payer_amount
                row['payer_adjustment'] = record.payer_adjustment
                row['payer_credit'] = record.payer_credit
                row['payer_receipt'] = record.payer_receipt 
                row['payer_discount'] = record.payer_discount
                row['payer_balance'] = record.payer_balance
                row['state'] = record.state
                row['remark'] = remark
                record.history_ids.create(row)


    @api.model
    def create(self, vals):
        result = super(SaleOrderCob, self).create(vals)
        if not result.cob_no:
            result.cob_no = self.env['ir.sequence'].sudo().next_by_code('sale.order.cob.seq')

        # flagging parent billing as COB
        if vals.get('billing_id'):
            billing = result.billing_id 
            billing.cob_bill = True 
        
        if vals.get('state'):
            if str(vals.get('state')) == 'done':
                result.action_history(remark="UNBILLED")
        return result


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(SaleOrderCob,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'tree':
            res['arch'] = """
                <tree string="COB" delete="false" decoration-danger="state == 'cancel'" decoration-info="state == 'draft'" decoration-success="state=='invoice'">
                    <field name="cob_no"/>
                    <field name="cob_date"/>
                    <field name="billing_id"/>
                    <field name="payer_id"/>
                    <field name="payer_amount"/>
                    <field name="covering_id"/>
                    <field name="payment_id"/>
                    <field name="state"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search COB..">
                    <filter string="Admission" domain="[('state','=', 'draft')]" help="Admission"/>
                    <filter string="Close Bill" domain="[('state','=', 'done')]" help="Close Bill"/>
                    <filter string="Cancel Bill" domain="[('state','=', 'cancel')]" help="Cancel Bill"/>
                    <separator/>
                    <field name="cob_no"/>
                    <field name="billing_id"/>
                    <field name="payer_id"/>
                </search>"""
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res





# 2021.09.17 - Billing COB History Table 
class SaleOrderCobHistory(models.Model):
    _name = 'sale.order.cob.history'
    _rec_name = 'cob_id'
    
    sync_id = sync.id
    sync_type = sync.type
    sync_id_api = sync.id_api 
    sync_date = sync.date 
    sync_consol_date = sync.consol_date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main

    cob_id = fields.Many2one('sale.order.cob', string="Cob No.")
    datetime = fields.Datetime(string="Datetime")
    payer_amount = fields.Float(string="Payer Amount")
    payer_adjustment = fields.Float(string="Payer Discount (Invoice)")
    payer_deduction = fields.Float(string="Payer Deduction")
    payer_credit = fields.Float(string="Payer Credit")
    payer_receipt = fields.Float(string="Payer Receipt")
    payer_discount = fields.Float(string="Payer Discount")
    payer_balance = fields.Float(string="Payer Balance")
    state = fields.Selection([('cancel','Cancel Billing'), ('draft','New Admission'), ('done','Close Bill'), ('invoice','Invoiced Bill')], string="State")
    remark = fields.Char(string="Remark")

    letter_id = fields.Many2one('account.coveringletter', string="Letter No.")
    credit_id = fields.Many2one('account.creditnote', string="WriteOff No.")
    receipt_id = fields.Many2one('account.payment', string="Receipt No.")
    advance_id = fields.Many2one('account.advance.realization', string="Advance No.")
    active = fields.Boolean(default=True, string="Active")




class SaleOrderWizard(models.TransientModel):
    _name = 'sale.order.wizard'

    @api.model
    def _get_user_id(self):
        return self.env.user.id

    company_id = fields.Many2one('res.company', string="Company", required=False)
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)
    sale_wizard_line = fields.One2many('sale.order.wizard.line','sale_wizard_id', string="Filter Line")
    user_id = fields.Many2one('res.users', string="User ID", default=_get_user_id)
    bulk_id = fields.Many2one('sale.order.bulk.filter', string="Saved Bulk Filter")

    @api.model
    def create(self,vals):
        if vals.get('bulk_id'):
            vals['sale_wizard_line'] = ""
        res = super(SaleOrderWizard, self).create(vals)
        return res

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(SaleOrderWizard,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Billing Analysis" delete="false">

                    <style>
                      .o_control_panel {
                          display: none;
                      }
                    </style>

                    <sheet>
                    <h1>
                        Billing Analysis
                    </h1>
                    <group>
                        <group>
                            <field name="user_id" invisible="1"/>
                            <field name="start_date" />
                            <field name="end_date" />
                        </group>
                        <group>
                            <field name="company_id" />
                            <field name="bulk_id" domain="[('user_id', '=', user_id)]"/>
                        </group>
                    </group>
                    <group>
                        <button name="show_report" string="Show" type="object" class="oe_highlight"/>
                    </group>
                    </sheet>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res
    
    # @api.model
    # def get_view(self,view_id=None, view_type='form', **options):
    #     res = super(SaleOrderWizard,self).get_view(view_id=view_id,view_type=view_type, **options)
    #     if view_type == 'form':
    #         res['arch'] = """
    #             <form string="Billing Analysis" delete="false">

    #                 <style>
    #                   .o_control_panel {
    #                       display: none;
    #                   }
    #                 </style>

    #                 <sheet>
    #                 <h1>
    #                     Billing Analysis
    #                 </h1>
    #                 <group>
    #                     <group>
    #                         <field name="user_id" invisible="1"/>
    #                         <field name="start_date" />
    #                         <field name="end_date" />
    #                         <field name="company_id" />
    #                         <field name="bulk_id" domain="[('user_id', '=', user_id)]"/>
    #                     </group>
    #                     <group>
    #                         <field name="sale_wizard_line" mode="kanban" list_options='{&quot;limit&quot;:10}'>
    #                             <!--tree editable="bottom"-->
    #                             <kanban class="o_kanban_mobile">
    #                                 <!--field name="filter_column_id" context="{&quot;order_display&quot;: &quot;field_description desc&quot; }"/>
    #                                 <field name="field_name" invisible="1"/>
    #                                 <field name="type_field" invisible="1"/>
    #                                 <field name="display_value" invisible="1"/>
    #                                 <field name="display_field" invisible="1"
    #                                 <field name="account_analytic_id" attrs="{'invisible': [('field_name', '!=', 'account_analytic_id')]}"/>
    #                                 <field name="location_id" attrs="{'invisible': [('field_name', '!=', 'location_id')]}"/>
    #                                 <field name="order_id" attrs="{'invisible': [('field_name', '!=', 'order_id')]}"/>
    #                                 <field name="parent_analytic_id" attrs="{'invisible': [('field_name', '!=', 'parent_analytic_id')]}"/>
    #                                 <field name="parent_analytic_primary_id" attrs="{'invisible': [('field_name', '!=', 'parent_analytic_primary_id')]}"/>
    #                                 <field name="partner_id" attrs="{'invisible': [('field_name', '!=', 'partner_id')]}"/>
    #                                 <field name="payer" attrs="{'invisible': [('field_name', '!=', 'payer')]}"/>
    #                                 <field name="perform_doc_id" attrs="{'invisible': [('field_name', '!=', 'perform_doc_id')]}"/>
    #                                 <field name="prescribe_doc_id" attrs="{'invisible': [('field_name', '!=', 'prescribe_doc_id')]}"/>
    #                                 <field name="primary_doc_id" attrs="{'invisible': [('field_name', '!=', 'primary_doc_id')]}"/>
    #                                 <field name="product_id" attrs="{'invisible': [('field_name', '!=', 'product_id')]}"/>
    #                                 <field name="product_uom" attrs="{'invisible': [('field_name', '!=', 'product_uom')]}"/>
    #                                 <field name="service_categ_id" attrs="{'invisible': [('field_name', '!=', 'service_categ_id')]}"/>
    #                                 <field name="value_text" attrs="{'invisible': [('type_field', 'not in', ['char', 'text'])]}"/>
    #                                 <field name="bool_filter" attrs="{'invisible': [('type_field', '!=', 'boolean')]}"/>
    #                                 <field name="date_filter" attrs="{'invisible': [('type_field', 'not in', ['date', 'datetime'])]}"/>/-->
    #                                 <templates>
    #                                     <t t-name="kanban-box">
    #                                         <div t-attf-class="oe_kanban_card oe_kanban_global_click">
    #                                             <div class="row">
    #                                                 <div class="col-8">
    #                                                     <strong>
    #                                                         <span>
    #                                                             <t t-esc="record.display_field.raw_value"/>
    #                                                         </span>
    #                                                     </strong>
    #                                                 </div>
    #                                             </div>
    #                                             <div class="row">
    #                                                 <div class="col-12 text-muted">
    #                                                     <span>
    #                                                         Filter:
    #                                                         <t t-if="record.field_name.raw_value === 'account_analytic_id'">
    #                                                             <t t-esc="record.display_value.raw_value"/>
    #                                                         </t>

    #                                                         <t t-if="record.field_name.raw_value === 'location_id'">
    #                                                             <t t-esc="record.display_value.raw_value"/>
    #                                                         </t>

    #                                                         <t t-if="record.field_name.raw_value === 'order_id'">
    #                                                             <t t-esc="record.display_value.raw_value"/>
    #                                                         </t>

    #                                                         <t t-if="record.field_name.raw_value === 'parent_analytic_id'">
    #                                                             <t t-esc="record.display_value.raw_value"/>
    #                                                         </t>

    #                                                         <t t-if="record.field_name.raw_value === 'parent_analytic_primary_id'">
    #                                                             <t t-esc="record.display_value.raw_value"/>
    #                                                         </t>

    #                                                         <t t-if="record.field_name.raw_value === 'parent_analytic_primary_id'">
    #                                                             <t t-esc="record.display_value.raw_value"/>
    #                                                         </t>

    #                                                         <t t-if="record.field_name.raw_value === 'partner_id'">
    #                                                             <t t-esc="record.display_value.raw_value"/>
    #                                                         </t>

    #                                                         <t t-if="record.field_name.raw_value === 'payer'">
    #                                                             <t t-esc="record.display_value.raw_value"/>
    #                                                         </t>

    #                                                         <t t-if="record.field_name.raw_value === 'perform_doc_id'">
    #                                                             <t t-esc="record.display_value.raw_value"/>
    #                                                         </t>

    #                                                         <t t-if="record.field_name.raw_value === 'prescribe_doc_id'">
    #                                                             <t t-esc="record.display_value.raw_value"/>
    #                                                         </t>

    #                                                         <t t-if="record.field_name.raw_value === 'primary_doc_id'">
    #                                                             <t t-esc="record.display_value.raw_value"/>
    #                                                         </t>

    #                                                         <t t-if="record.field_name.raw_value === 'product_id'">
    #                                                             <t t-esc="record.display_value.raw_value"/>
    #                                                         </t>

    #                                                         <t t-if="record.field_name.raw_value === 'product_uom'">
    #                                                             <t t-esc="record.display_value.raw_value"/>
    #                                                         </t>


    #                                                         <t t-if="record.type_field.raw_value === 'service_categ_id'">
    #                                                             <t t-esc="record.display_value.raw_value"/>
    #                                                         </t>

    #                                                         <t t-if="record.type_field.raw_value === 'char' || record.type_field.raw_value === 'text'">
    #                                                             <t t-esc="record.value_text.raw_value"/>
    #                                                         </t>

    #                                                         <t t-if="record.type_field.raw_value === 'boolean'">
    #                                                             <t t-esc="record.bool_filter.raw_value"/>
    #                                                         </t>
    #                                                         <t t-if="record.type_field.raw_value === 'date' || record.type_field.raw_value === 'datetime'">
    #                                                             <t t-esc="record.date_filter.raw_value"/>
    #                                                         </t>
    #                                                     </span>
    #                                                 </div>
    #                                             </div>
    #                                         </div>
    #                                     </t>
    #                                 </templates>
    #                             </kanban>
    #                         </field>
    #                     </group>
    #                 </group>
    #                 <group>
    #                     <button name="show_report" string="Show" type="object" class="oe_highlight"/>
    #                 </group>
    #                 </sheet>
    #             </form>
    #         """
    #     from lxml import etree
    #     doc = etree.XML(res['arch'])
    #     View = self.env['ir.ui.view'].sudo()
    #     res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
    #     return res






    @api.onchange('bulk_id')
    def onchange_filter(self):
        for record in self:
            if record.bulk_id:
                record.sale_wizard_line = record.bulk_id.filter_ids.ids

    # @api.multi
    def query_report(self, data_ids=False):
        for record in self:
            open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Start')
            domain = ""

            line_all = []
            query_field = ""
            if not record.bulk_id:
                for line in record.sale_wizard_line:
                    line_dict = line.read(load=False)[0]
                    line_all.append(line_dict)

                open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Append all line')

                line_sorted = sorted(line_all, key=itemgetter('field_name'))
                open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Sort Data')
                query_field_all = """ """
                for field, value in itertools.groupby(line_sorted, key=itemgetter('field_name')):
                    val = []
                    char = False
                    date = False
                    bool = False
                    for v in value:
                        if v['type_field'] == 'many2one':
                            val.append(v[field])
                        if v['type_field'] in ['char', 'text']:
                            val.append(v['value_text'])
                            char = True
                        if v['type_field'] == ['boolean']:
                            val.append(v['bool_filter'])
                            bool = True
                        if v['type_field'] in ['date', 'datetime']:
                            val.append(v['date_filter'])
                            date = True
                        open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Processing data')

                    open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Processing domain')

                    if len(val) > 1 and date == False and bool == False:
                        query_field = "('{field}', 'in', {value}),  ".format(field=field, value=val)
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and date == False and bool == False and char == False:
                        query_field = "('{field}', '=', {value}),  ".format(field=field, value=val[0])
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and char == True:
                        query_field = "('{field}', 'like', '{value}'),  ".format(field=field, value=(val[0]))
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and bool == True:
                        query_field = "('{field}', '=', {value}), ".format(field=field, value=(val[0]))
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field

                    domain = "{query_field_all}".format(query_field_all=query_field_all)

                    open('/opt/odoo16/logs/belajar.log',
                         'a+').write('\n' + str(domain) + '\n' + 'domain query report')

            if record.bulk_id:
                for line in record.bulk_id.filter_ids:
                    line_dict = line.read(load=False)[0]
                    line_all.append(line_dict)
                open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Append all line')

                line_sorted = sorted(line_all, key=itemgetter('field_name'))
                open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Sort Data')
                query_field_all = """ """
                for field, value in itertools.groupby(line_sorted, key=itemgetter('field_name')):
                    val = []
                    char = False
                    date = False
                    bool = False
                    for v in value:
                        if v['type_field'] == 'many2one':
                            val.append(v[field])
                        if v['type_field'] in ['char', 'text']:
                            val.append(v['value_text'])
                            char = True
                        if v['type_field'] == ['boolean']:
                            val.append(v['bool_filter'])
                            bool = True
                        if v['type_field'] in ['date', 'datetime']:
                            val.append(v['date_filter'])
                            date = True
                        open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Processing data')

                    open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Processing domain')

                    if len(val) > 1 and date == False and bool == False:
                        query_field = "('{field}', 'in', {value}),  ".format(field=field, value=val)
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and date == False and bool == False and char == False:
                        query_field = "('{field}', '=', {value}),  ".format(field=field, value=val[0])
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and char == True:
                        query_field = "('{field}', 'like', '{value}'),  ".format(field=field, value=(val[0]))
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and bool == True:
                        query_field = "('{field}', '=', {value}), ".format(field=field, value=(val[0]))
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field

                    domain = "{query_field_all}".format(query_field_all=query_field_all)

                    open('/opt/odoo16/logs/belajar.log','a+').write('\n' + str(domain) + '\n' + 'domain bulk')

            return domain


    # @api.multi
    def show_report(self):
        open('/opt/odoo16/logs/test_sale_wizard.log','a+').write('\n' + 'Start')
        query = self.query_report()
        action = {}
        action['target'] = 'current'
        # action['domain'] = "[('user_id', '=', %s)]" % (self.env.user.id)
        if query:
            if self.company_id:
                action['domain'] = "[{query}('tglproses', '>=', '{start_date}'), ('tglproses', '<=', '{end_date}'), ('company_id', '=', {company_id})]".format(query=query, start_date=self.start_date, end_date=self.end_date, company_id=self.company_id.id)
            else:
                action['domain'] = "[{query}('tglproses', '>=', '{start_date}'), ('tglproses', '<=', '{end_date}')]".format(query=query, start_date=self.start_date, end_date=self.end_date, company_id=self.company_id.id)
        else:
            if self.company_id:
                action['domain'] = "[('tglproses', '>=', '%s'), ('tglproses', '<=', '%s'), ('company_id', '=', %s)]" % (self.start_date, self.end_date, self.company_id.id)
            else:
                action['domain'] = "[('tglproses', '>=', '%s'), ('tglproses', '<=', '%s')]" % (self.start_date, self.end_date)
        # action['domain'] = "[('tglproses', '>=', '2019-01-01'), ('tglproses', '<=', '2019-02-01')]"
        # action['domain'] = "[()]"
        open('/opt/odoo16/logs/belajar.log','a+').write('\n' + str(action['domain']) + '\n' + 'domain show report')
        action['type'] = 'ir.actions.act_window'
        action['view_mode'] = 'tree,form,pivot'
        action['view_type'] = 'form'
        action['res_model'] = 'sale.order.line'
        action['name'] = 'Billing Analysis Report'
        # view_billing_analysis_real_pivot
        # action['views'] = [(self.sudo().env.ref('mayapada.view_billing_analysis_pivot').id, 'pivot'), (False, 'form'), (False, 'tree')]
        action['views'] = [(self.sudo().env.ref('mayapada.view_billing_analysis_real_pivot').id, 'pivot'), (False, 'tree'), (False, 'form')]
        return action




class SaleOrderWizardLine(models.TransientModel):
    _name = 'sale.order.wizard.line'

    sale_wizard_id = fields.Many2one('sale.order.wizard', string="wizard")
    filter_column_id = fields.Many2one('ir.model.fields', string="Field Filter", domain="[('model_id.model', '=', 'sale.order.line'), ('ttype', 'not in', ['many2many', 'one2many', 'date', 'datetime'])]")
    field_name = fields.Char(string="Field Name", compute='_compute_field_name', readonly=True, store=True)
    type_field = fields.Char(string="Type Field", compute='_compute_field_name', readonly=True, store=True)
    product_id = fields.Many2one('product.product', string="Product", domain="[('sale_ok', '=', True)]")
    account_analytic_id = fields.Many2one('account.analytic.account', string="Analytic Doctor", domain="[('sync_wipro_type', '=', 'doctor_internal')]")
    location_id = fields.Many2one('stock.location', string="Location", domain="[('sync_id', '>', 0)]")
    order_id = fields.Many2one('sale.order', string="Admission")
    parent_analytic_id = fields.Many2one('account.analytic.account', string="Analytic Specialization", domain="[('sync_wipro_type', '=', 'specialization')]")
    parent_analytic_primary_id = fields.Many2one('account.analytic.account', string="Primary Specialization", domain="[('sync_wipro_type', '=', 'specialization')]")
    partner_id = fields.Many2one('res.partner', string="Patient", domain="[('patient', '=', True)]")
    payer = fields.Many2one('res.partner', string="Payer", domain="[('customer_wipro', '=', True)]")
    perform_doc_id = fields.Many2one('account.analytic.account', string="Perform Doctor", domain="[('sync_wipro_type', '=', 'doctor_internal')]")
    prescribe_doc_id = fields.Many2one('account.analytic.account', string="Prescribe Doctor", domain="[('sync_wipro_type', '=', 'doctor_internal')]")
    primary_doc_id = fields.Many2one('account.analytic.account', string="Primary Doctor", domain="[('sync_wipro_type', '=', 'doctor_internal')]")
    product_uom = fields.Many2one('uom.uom', string="UOM")
    service_categ_id = fields.Many2one('product.category', string="Service Category", domain="[('sync_id', '>', 0)]")
    bool_filter = fields.Boolean('True or False')
    value_text = fields.Char(string="Char Filter")
    date_filter = fields.Date(string="Date Filter")
    field_import = fields.Char(string="Field Import")
    display_value = fields.Char(string="Display Value", compute='_compute_display', readonly=True, store=True)
    display_field = fields.Char(string="Display Field", compute='_compute_display', readonly=True, store=True)
    bulk_id = fields.Many2one('sale.order.bulk.filter', string="Bulk Filter")

    @api.model
    def create(self, vals):
        open('/opt/odoo16/logs/bulk.log', 'a+').write('\n' + str('START').encode('utf-8'))
        if vals.get('field_import'):
            field = self.env['ir.model.fields'].search([('field_description', '=', vals['field_import']), ('model_id.model', '=', 'sale.order.line')], order="id asc", limit=1)
            open('/opt/odoo16/logs/bulk.log', 'a+').write('\n' + str(field).encode('utf-8'))
            if not field:
                raise exceptions.UserError('Field tidak ditemukan!!!')
            else:
                vals['filter_column_id'] = field.id
        res = super(SaleOrderWizardLine, self).create(vals)
        return res

    @api.depends('filter_column_id', 'product_id', 'account_analytic_id',
                 'location_id', 'order_id', 'parent_analytic_id',
                 'parent_analytic_primary_id', 'partner_id', 'payer',
                 'perform_doc_id', 'prescribe_doc_id', 'primary_doc_id',
                 'product_uom', 'service_categ_id')
    def _compute_display(self):
        for record in self:
            record.display_value = " "
            if record.filter_column_id:
                record.display_field = record.filter_column_id.field_description
            if record.product_id:
                record.display_value = record.product_id.display_name
            if record.account_analytic_id:
                record.display_value = record.account_analytic_id.display_name
            if record.location_id:
                record.display_value = record.location_id.display_name
            if record.order_id:
                record.display_value = record.order_id.display_name
            if record.parent_analytic_id:
                record.display_value = record.parent_analytic_id.display_name
            if record.parent_analytic_primary_id:
                record.display_value = record.parent_analytic_primary_id.display_name
            if record.payer:
                record.display_value = record.payer.display_name
            if record.perform_doc_id:
                record.display_value = record.perform_doc_id.display_name
            if record.prescribe_doc_id:
                record.display_value = record.prescribe_doc_id.display_name
            if record.primary_doc_id:
                record.display_value = record.primary_doc_id.display_name
            if record.product_uom:
                record.display_value = record.product_uom.display_name
            if record.service_categ_id:
                record.display_value = record.service_categ_id.display_name
            if record.partner_id:
                record.display_value = record.partner_id.display_name

    @api.depends('filter_column_id')
    def _compute_field_name(self):
        for record in self:
            if record.filter_column_id:
                record.field_name = record.filter_column_id.name
                record.type_field = record.filter_column_id.ttype

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(SaleOrderWizardLine,self).get_view(view_id=view_id,view_type=view_type, **options)
        res['arch'] = """
            <form string="Filter Line">
                <group>
                    <field name="filter_column_id"/>
                    <field name="field_name" invisible="1"/>
                    <field name="type_field" invisible="1"/>
                    <field name="display_value" invisible="1"/>
                    <field name="display_field" invisible="1"/>
                    <field name="account_analytic_id" attrs="{'invisible': [('field_name', '!=', 'account_analytic_id')]}"/>
                    <field name="location_id" attrs="{'invisible': [('field_name', '!=', 'location_id')]}"/>
                    <field name="order_id" attrs="{'invisible': [('field_name', '!=', 'order_id')]}"/>
                    <field name="parent_analytic_id" attrs="{'invisible': [('field_name', '!=', 'parent_analytic_id')]}"/>
                    <field name="parent_analytic_primary_id" attrs="{'invisible': [('field_name', '!=', 'parent_analytic_primary_id')]}"/>
                    <field name="partner_id" attrs="{'invisible': [('field_name', '!=', 'partner_id')]}"/>
                    <field name="payer" attrs="{'invisible': [('field_name', '!=', 'payer')]}"/>
                    <field name="perform_doc_id" attrs="{'invisible': [('field_name', '!=', 'perform_doc_id')]}"/>
                    <field name="prescribe_doc_id" attrs="{'invisible': [('field_name', '!=', 'prescribe_doc_id')]}"/>
                    <field name="primary_doc_id" attrs="{'invisible': [('field_name', '!=', 'primary_doc_id')]}"/>
                    <field name="product_id" attrs="{'invisible': [('field_name', '!=', 'product_id')]}"/>
                    <field name="product_uom" attrs="{'invisible': [('field_name', '!=', 'product_uom')]}"/>
                    <field name="service_categ_id" attrs="{'invisible': [('field_name', '!=', 'service_categ_id')]}"/>
                    <field name="value_text" attrs="{'invisible': [('type_field', 'not in', ['char', 'text'])]}"/>
                    <field name="bool_filter" attrs="{'invisible': [('type_field', '!=', 'boolean')]}"/>
                    <field name="date_filter" attrs="{'invisible': [('type_field', 'not in', ['date', 'datetime'])]}"/>
                </group>
            </form>
        """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res






class SaleOrderBulkFilter(models.TransientModel):
    _name = 'sale.order.bulk.filter'

    name = fields.Char(string="Filter Name", required=True)
    user_id = fields.Many2one('res.users', string="User ID", store=True, readonly=True)
    filter_ids = fields.One2many('sale.order.wizard.line', 'bulk_id', string="Filter Line")

    @api.model
    def create(self, vals):
        res = super(SaleOrderBulkFilter, self).create(vals)
        res.user_id = self.env.user.id
        return res

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(SaleOrderBulkFilter,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Bulk Filter">
                    <style>
                        .o_control_panel {
                            display: none;
                        }
                    </style>
                    <h1>
                        Make Bulk Filter
                    </h1>
                    <group>
                        <group>
                            <field name="name"/>
                            <field name="user_id" />
                        </group>
                        <group>
                            <field name="filter_ids" mode="kanban">
                                <!--tree editable="bottom"-->
                                <kanban class="o_kanban_mobile">
                                    <!--field name="filter_column_id" context="{'order_display': 'field_description desc' }"/>
                                    <field name="field_name" invisible="1"/>
                                    <field name="type_field" invisible="1"/>
                                    <field name="display_value" invisible="1"/>
                                    <field name="display_field" invisible="1"/>
                                    <field name="account_analytic_id" attrs="{'invisible': [('field_name', '!=', 'account_analytic_id')]}"/>
                                    <field name="location_id" attrs="{'invisible': [('field_name', '!=', 'location_id')]}"/>
                                    <field name="order_id" attrs="{'invisible': [('field_name', '!=', 'order_id')]}"/>
                                    <field name="parent_analytic_id" attrs="{'invisible': [('field_name', '!=', 'parent_analytic_id')]}"/>
                                    <field name="parent_analytic_primary_id" attrs="{'invisible': [('field_name', '!=', 'parent_analytic_primary_id')]}"/>
                                    <field name="partner_id" attrs="{'invisible': [('field_name', '!=', 'partner_id')]}"/>
                                    <field name="payer" attrs="{'invisible': [('field_name', '!=', 'payer')]}"/>
                                    <field name="perform_doc_id" attrs="{'invisible': [('field_name', '!=', 'perform_doc_id')]}"/>
                                    <field name="prescribe_doc_id" attrs="{'invisible': [('field_name', '!=', 'prescribe_doc_id')]}"/>
                                    <field name="primary_doc_id" attrs="{'invisible': [('field_name', '!=', 'primary_doc_id')]}"/>
                                    <field name="product_id" attrs="{'invisible': [('field_name', '!=', 'product_id')]}"/>
                                    <field name="product_uom" attrs="{'invisible': [('field_name', '!=', 'product_uom')]}"/>
                                    <field name="service_categ_id" attrs="{'invisible': [('field_name', '!=', 'service_categ_id')]}"/>
                                    <field name="value_text" attrs="{'invisible': [('type_field', 'not in', ['char', 'text'])]}"/>
                                    <field name="bool_filter" attrs="{'invisible': [('type_field', '!=', 'boolean')]}"/>
                                    <field name="date_filter" attrs="{'invisible': [('type_field', 'not in', ['date', 'datetime'])]}"/-->
                                    <templates>    
                                        <t t-name="kanban-box">
                                            <div t-attf-class="oe_kanban_card oe_kanban_global_click">
                                                <div class="row">
                                                    <div class="col-8">
                                                        <strong>
                                                            <span>
                                                                <t t-esc="record.display_field.raw_value"/>
                                                            </span>
                                                        </strong>
                                                    </div>
                                                </div>
                                                <div class="row">
                                                    <div class="col-12 text-muted">
                                                        <span>
                                                            Filter:
                                                            <t t-if="record.field_name.raw_value === 'account_analytic_id'">
                                                                <t t-esc="record.display_value.raw_value"/>
                                                            </t>

                                                            <t t-if="record.field_name.raw_value === 'location_id'">
                                                                <t t-esc="record.display_value.raw_value"/>
                                                            </t>

                                                            <t t-if="record.field_name.raw_value === 'order_id'">
                                                                <t t-esc="record.display_value.raw_value"/>
                                                            </t>

                                                            <t t-if="record.field_name.raw_value === 'parent_analytic_id'">
                                                                <t t-esc="record.display_value.raw_value"/>
                                                            </t>

                                                            <t t-if="record.field_name.raw_value === 'parent_analytic_primary_id'">
                                                                <t t-esc="record.display_value.raw_value"/>
                                                            </t>

                                                            <t t-if="record.field_name.raw_value === 'parent_analytic_primary_id'">
                                                                <t t-esc="record.display_value.raw_value"/>
                                                            </t>

                                                            <t t-if="record.field_name.raw_value === 'partner_id'">
                                                                <t t-esc="record.display_value.raw_value"/>
                                                            </t>

                                                            <t t-if="record.field_name.raw_value === 'payer'">
                                                                <t t-esc="record.display_value.raw_value"/>
                                                            </t>

                                                            <t t-if="record.field_name.raw_value === 'perform_doc_id'">
                                                                <t t-esc="record.display_value.raw_value"/>
                                                            </t>

                                                            <t t-if="record.field_name.raw_value === 'prescribe_doc_id'">
                                                                <t t-esc="record.display_value.raw_value"/>
                                                            </t>

                                                            <t t-if="record.field_name.raw_value === 'primary_doc_id'">
                                                                <t t-esc="record.display_value.raw_value"/>
                                                            </t>

                                                            <t t-if="record.field_name.raw_value === 'product_id'">
                                                                <t t-esc="record.display_value.raw_value"/>
                                                            </t>

                                                            <t t-if="record.field_name.raw_value === 'product_uom'">
                                                                <t t-esc="record.display_value.raw_value"/>
                                                            </t>


                                                            <t t-if="record.type_field.raw_value === 'service_categ_id'">
                                                                <t t-esc="record.display_value.raw_value"/>
                                                            </t>

                                                            <t t-if="record.type_field.raw_value === 'char' || record.type_field.raw_value === 'text'">
                                                                <t t-esc="record.value_text.raw_value"/>
                                                            </t>

                                                            <t t-if="record.type_field.raw_value === 'boolean'">
                                                                <t t-esc="record.bool_filter.raw_value"/>
                                                            </t>
                                                            <t t-if="record.type_field.raw_value === 'date' || record.type_field.raw_value === 'datetime'">
                                                                <t t-esc="record.date_filter.raw_value"/>
                                                            </t>
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>
                                        </t>
                                    </templates>
                                </kanban>
                            </field>
                        </group>
                    </group>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Bulk Filter">
                    <field name="name"/>
                    <field name="user_id"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res




# 2021.09.16 - Billing Update sale.order.line (Dhealth)
class SaleBulkUpdateWizard(models.TransientModel):
    _name = 'sale.bulk.update.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    column_name = fields.Selection([('service_group', 'Service Group'), ('service_categ_id', 'Service Category'), ('account_analytic_id', 'Analytic Doctor'), ('referral_doc_id', 'Referral Doctor'), ('primary_doc_id', 'Primary Doctor'), ('prescribe_doc_id', 'Prescribe Doctor'), ('perform_doc_id', 'Perform Doctor')], string='Column Name', default='service_categ_id')
    analytic_account = fields.Many2one('account.analytic.account', string="Doctor Name")
    date_start = fields.Date(string="Date Start", default=(fields.date.today() - timedelta(days=7)))
    date_end = fields.Date(string="Date End", default=fields.date.today())
    service_group = fields.Selection([
            ('Consumables','Consumables'), 
            ('Haemodialysis','Haemodialysis'), 
            ('OP/IP Procedure','OP/IP Procedure'), 
            ('Radiology','Radiology'), 
            ('Admin Charge','Admin Charge'), 
            ('Cathlab','Cathlab'), 
            ('Drugs','Drugs'), 
            ('Hospital Facilities','Hospital Facilities'), 
            ('Others','Others'), 
            ('Surgery','Surgery'), 
            ('Bed Rentals','Bed Rentals'), 
            ('Consultation','Consultation'), 
            ('Medical Rehab','Medical Rehab'), 
            ('Laboratory','Laboratory')
        ], string="Service Group")
    service_categ_id = fields.Many2one('product.category', string="Service Category")
    sale_line_ids = fields.Many2many('sale.order.line', relation='sale_order_line_update', string="Billing Analysis", required=True, store=True)

    # @api.multi
    def bulk_update(self):
        report_id = self.id 
        column_name = self.column_name
        company_id = self.company_id.id 
        
        if column_name not in ['service_categ_id','service_group']:
            column_value = self.analytic_account.id or None
        elif column_name in ['service_categ_id']:
            column_value = self.service_categ_id.id or None
        elif column_name in ['service_group']:
            column_value = "'" + self.service_group + "'"

        open('/opt/odoo16/logs/sale_bulk_update.log', 'a+').write(str('\nStart update sale.order.line:'))
        query = """
            UPDATE sale_order_line AS a set 
                {column_name} = {column_value},
                write_date = CURRENT_TIMESTAMP
            WHERE a.id IN (
                SELECT t.sale_order_line_id
                FROM sale_order_line_update t
                WHERE t.sale_bulk_update_wizard_id = {report_id}
            ) AND a.company_id = {company_id}
        """.format(
            report_id=report_id, 
            company_id=company_id, 
            column_name=column_name, 
            column_value=column_value)
        open('/opt/odoo16/logs/sale_bulk_update.log', 'a+').write('\n'+str(query))

        self.sudo().env.cr.execute(query)
        open('/opt/odoo16/logs/sale_bulk_update.log', 'a+').write(str('\nDone'))
        print("Successfully to update sale.order.line")
        #raise exceptions.UserError('Successfully to update sale.order.line')




class SaleBulkMergingWizard(models.TransientModel):
    _name = 'sale.bulk.merging.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    merge_bill_ids = fields.Many2many('sale.order.bill', relation="sale_bulk_merging_bill", string="Merge Billing")
    merge_bill_total = fields.Float(string="Merge Bill Total", compute="_total_billing")
    merge_bill_payer_id = fields.Many2one('res.partner', string="Merge Bill Payer")
    merge_bill_no = fields.Char(string="Merge Bill No.")
    cob_bill_ids = fields.One2many('sale.bulk.merging.line', 'merge_id', string="COB Billing")
    cob_create = fields.Boolean(string="Create COB", default=False)

    @api.onchange('merge_bill_ids')
    def _total_billing(self):
        total_billing = 0
        if self.merge_bill_ids:
            for line in self.merge_bill_ids:
                total_billing += line.payer_amount
        self.merge_bill_total = total_billing

    @api.depends('merge_bill_ids')
    @api.onchange('merge_bill_ids')
    def change_domain(self):
        payer_ids = [line.payer_id.id for line in self.merge_bill_ids] 
        res = {}
        res['domain'] = {'merge_bill_payer_id': [('id','in',payer_ids), ('company_id','=', self.company_id.id), ('customer_wipro','=', True) ]}
        return res 

    # @api.multi
    def bulk_merging(self):
        report_id = self.id 
        company_id = self.company_id.id 
        sync_type = self.company_id.sync_type
        billing_total = self.merge_bill_total 
        billing_payer = self.merge_bill_payer_id or None 
        billing_no = self.merge_bill_no or False


        if billing_total > 0:
            if not billing_payer:
                raise exceptions.UserError("Pilih payor yang akan dijadikan payor utama di billing gabungan.")

            # validasi jika ada COB
            if self.cob_create:
                total_cob = sum([line.cob_amount for line in self.cob_bill_ids])
                if total_cob != billing_total:
                    raise exceptions.UserError("Pastikan total COB sama dengan total billing gabungan.")

            billing_id = max([line.id for line in self.merge_bill_ids])
            bill = self.env['sale.order.bill'].browse(billing_id)
            merged_bill = self.env['sale.order.bill'].create({
                'billno': (billing_no if billing_no else bill.billno + ' (MERGED)'), 
                'confirmation_date': bill.confirmation_date, 
                'bill_date':bill.bill_date, 
                'admission_no': bill.admission_no, 
                'admission_id': bill.admission_id.id, 
                'partner_id':bill.partner_id.id, 
                'registration_code':bill.registration_code, 
                'patient_type':bill.patient_type, 
                'payer_type': billing_payer.customer_type_wipro, 
                'payer_code': billing_payer.vendor_code, 
                'payer_id': billing_payer.id, 
                'payer_amount':billing_total, 
                'total_amount':billing_total, 
                'merged_bill':True, 
                'state':'done',
                'sync_type': sync_type
            })
            

            if merged_bill:
                patient_id = None 
                payer_id = None 
                patient_type = None

                for line in self.merge_bill_ids:
                    if patient_id:
                        if line.partner_id.id not in [patient_id]:
                            raise exceptions.UserError("Billing yang dapat di merging harus milik pasien & payor yang sama.")
                    patient_id = line.partner_id.id or None 

                    if payer_id:
                        if line.payer_id.id not in [payer_id]:
                            raise exceptions.UserError("Billing yang dapat di merging harus memiliki pasien & payor yang sama.")
                    payer_id = line.payer_id.id or None 

                    if patient_type:
                        if line.patient_type in [patient_type]:
                            raise exceptions.UserError("Billing yang dapat di merging harus memiliki Patient Type yang berbeda IPD & IGD.")
                    patient_type = line.patient_type or None 
      
                    line.already_merged = True 
                    line.merged_id = merged_bill.id 

                # create COB if checked
                for line in self.cob_bill_ids:
                    cob_bill = self.env['sale.order.cob'].create({'cob_no': merged_bill.billno + '-' + str(line.sequence), 'cob_date': merged_bill.confirmation_date, 'admission_id':merged_bill.admission_id.id, 'billing_id':merged_bill.id, 'payer_id': line.cob_payer_id.id, 'payer_amount':line.cob_amount, 'state':'done'})
                    if cob_bill:
                        merged_bill.cob_bill = True
        else:
            raise exceptions.UserError("Please select one or more billing to merging.")
        # open('/opt/odoo16/logs/log_sale_bulk_merging.log', 'a+').write(str('\nDone'))
        print("Successfully to update sale.order.bill")





# 2021.09.16 - Billing bulk closing compute for Dhealth
class SaleBulkClosingWizard(models.TransientModel):
    _name = 'sale.bulk.closing.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    date_start = fields.Date(string="Date Start", store=True, index=True)
    date_end = fields.Date(string="Date End", store=True, index=True)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(SaleBulkClosingWizard,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Sales Bulk Closing">
                    <group>
                        <group>
                            <field name="company_id" />
                        </group>
                        <group>
                            <field name="date_start" />
                            <field name="date_end" />
                        </group>
                    </group>                
                    <footer>
                        <button name="bulk_sync" string="Sync AVG Odoo Cost" type="object" class="oe_highlight"/>
                        <button name="bulk_update_general" string="Update HIS WAC Non Medical" type="object" class="oe_highlight"/>
                        <button name="bulk_update" string="Update Odoo Cost Total" type="object" class="oe_highlight"/>
                        <button name="bulk_takeout" string="Update Takeout" type="object" class="oe_highlight"/>
                        <button name="bulk_remapping" string="Remapping Group" type="object" class="oe_highlight"/>
                    </footer>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # @api.multi
    def bulk_update_general(self):
        report_id = self.id 
        company_id = self.company_id.id
        date_start = (self.date_start).strftime('%Y-%m-%d')
        date_end = (self.date_end).strftime('%Y-%m-%d')
        
        open('/opt/odoo16/logs/sale_bulk_closing_non_medical.log', 'a+').write(str('\nStart update sale.order.line:'))
        query = """
            update sale_order_line as sol set 
                cost_unit = (pcp.cost), 
                cost_total = (pcp.cost * sol.product_uom_qty),
                write_date = CURRENT_TIMESTAMP
            from product_product pp 
            inner join product_template pt on pt.id=pp.product_tmpl_id
            inner join product_price_history pcp on pcp.product_id=pp.id
            where pp.id = sol.product_id
                and date(pcp.datetime) = date('{date_end}')
                and sol.service_categ_id in(
                    select id from product_category 
                    where name in ('Pharmacy','Drug','Drugs','Consumable','Consumables','DRUG','DRUGS','PHARMACY','CONSUMABLE','CONSUMABLES'))
                and sol.company_id = {company_id}
                and sol.type_line not in ('DISCOUNT', 'DISCOUNT CANCEL')
                and sol.tglproses >= '{date_start}'
                and sol.tglproses <= '{date_end}'
                and left(pt.default_code, 3) = 'BRG'
        """.format(company_id=company_id, date_start=date_start, date_end=date_end)
        open('/opt/odoo16/logs/sale_bulk_closing_non_medical.log', 'a+').write('\n'+str(query))

        self.sudo().env.cr.execute(query)
        open('/opt/odoo16/logs/sale_bulk_closing_non_medical.log', 'a+').write(str('\nDone'))
        print("Successfully to update sale.order.line")

    # 2021.12.10 = hitung average cost disisi odoo based on mutasi stock docotel
    # @api.multi
    def bulk_sync(self):
        import psycopg
        import pyodbc
        from psycopg2 import extensions, connect
        from datetime import datetime
        import psycopg2.extras
        import pytz

        company = self.company_id
        sync_type = self.company_id.sync_type
        date_start = datetime.strptime(str(self.date_start), '%Y-%m-%d')
        date_end = datetime.strptime(str(self.date_end), '%Y-%m-%d')
        db_host = company.his_slave_host
        db_login = company.his_slave_login
        db_pass = company.his_slave_pass
        db_name = company.his_slave_db
        db_port = company.his_slave_port
        
        if company.sync_type in ('7','9'):
            conn = connect(dbname=db_name, user=db_login, host=db_host, password=db_pass, port=db_port)
        else:
            conn = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER='+db_host+';DATABASE='+db_name+';UID='+db_login+';PWD='+db_pass+';}')

        local = pytz.timezone('Asia/Jakarta')
        log_file = "/opt/odoo16/logs/sync_cost_average.log"
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        open(log_file, 'a').write("\n\n"+log_time+" Start process ---")

        query = """
            SELECT 
                '{date_end}' cost_date,
                t.sync_id_api,
                t.item_id,
                t.item_code,
                t.item_name, 
                t.item_type,
                t.uom_id,
                t.QOH,
                ROUND((
                    CASE 
                        WHEN coalesce(t.cost_unit,0) <> 0 
                        THEN t.cost_unit 
                        ELSE t.avg_price 
                    END)) cost_unit,
                t.max_price,
                t.avg_price
            FROM (

                SELECT               
                    coalesce(oa.default_code,b.default_code) item_code,
                    coalesce(oa.name,b.name) item_name,
                    coalesce(oa.sync_id_api,b.sync_id_api) sync_id_api,
                    a.item_type, 
                    a.item_id,
                    coalesce(cast(oa.uom_id as varchar),cast(b.uom_id as varchar)) uom_id,
                    sum(coalesce(a.stock_in,0)-coalesce(a.stock_out,0)) QOH, 
                    (sum((CASE 
                        WHEN a.move_type in('PURCHASE RECEIPT','PURCHASE RECEIPT WO') 
                        THEN ((a.nett_price/( --a.stock_in / 
                            (case when a.s_konversiobt_id is not null 
                                then (case 
                                    when t2.konversi_salah is true and t2.konversi_asli=1
                                    then coalesce(t2.nilai_konversi,1) 
                                    else 1 end) 
                                else (case
                                    when t3.konversi_salah is true and t3.konversi_asli=1
                                    then coalesce(t3.nilai_konversi,1)  
                                end) 
                            end))) * (coalesce(a.stock_in,0)-coalesce(a.stock_out,0))) 
                        ELSE 0 END)) / 
                        nullif(sum((
                        CASE WHEN a.move_type in('PURCHASE RECEIPT','PURCHASE RECEIPT WO')
                            THEN (coalesce(a.stock_in,0)-coalesce(a.stock_out,0)) else 0 END))
                    ,0)) cost_unit,
                        
                    sum((
                        CASE WHEN a.move_type in('PURCHASE RECEIPT','PURCHASE RECEIPT WO')
                            THEN (coalesce(a.stock_in,0)-coalesce(a.stock_out,0)) else 0 
                    END)) RcvQty,
                    max(a.nett_price) max_price,
                    avg(a.nett_price) avg_price   
                FROM (
                    SELECT  
                        a.stokobatalkes_id move_id,
                        (CASE 
                            WHEN a.terimamutasidetail_id IS NOT NULL THEN 'INTERNAL RECEIPT'
                            WHEN a.returresepdetail_id IS NOT NULL THEN 'RETURN PRESCRIPTION'
                            WHEN a.mutasiobatdetail_id IS NOT NULL THEN 'INTERNAL TRANSFER'
                            WHEN a.obatalkespasien_id IS NOT NULL THEN 'SALES'
                            WHEN a.pemusnahanobatdetail_id IS NOT NULL THEN 'LOSS BREAKAGE'
                            WHEN a.stokopnamedetail_id IS NOT NULL THEN (CASE 
                                WHEN coalesce(a.qtystok_in,0) > 0 THEN 'STOCK OPNAME IN'
                                ELSE 'STOCK OPNAME OUT' END)
                            WHEN a.pemakaianobatdetail_id IS NOT NULL THEN 'STORE CONSUMPTION'
                            WHEN a.produksiobatdetail_id IS NOT NULL THEN 'PREPARED ITEM'
                            WHEN a.storexpiredobatdetail_id IS NOT NULL THEN 'EXPIRED ITEM'
                            WHEN a.adjusmenobatmasuk_id IS NOT NULL THEN 'ADJUSTMENT RECEIPT'
                            WHEN a.adjusmenobatkeluar_id IS NOT NULL THEN 'ADJUSTMENT ISSUE'
                            WHEN a.pembatalanresep_id IS NOT NULL THEN 'CANCEL PRESCRIPTION'
                            WHEN a.penerimaanobatdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT'
                            WHEN a.penerimaansuppdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT WO'
                            WHEN a.returpenerimaanobatdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT RETURN'
                        END) move_type,   
                        coalesce(a.tglstok_in,a.tglstok_out) move_date,
                        a.ruangan_id location_id,
                        a.obatalkes_id item_id,
                        'MEDIC' item_type,
                        a.nobatch batch_no,
                        a.tglkadaluarsa expired_date,
                        a.tglstok_in stock_in_date,
                        a.qtystok_in stock_in,
                        a.tglstok_out stock_out_date,
                        a.qtystok_out stock_out,
                        ((prd.harga - (prd.discount * prd.harga / 100.00) + 
                        (coalesce(tax.pajak_persen,0) / 100.00 * (prd.harga - (prd.discount * prd.harga / 100.00)))
                        ) / uom.conversion_rate) nett_price,
                        --a.harganetto nett_price,
                        --a.satuankecil_id uom_id,
                        a.rakobat_id rack_id,
                        prd.s_konversiobt_id,
                        null::integer s_konversibrg_id  
                    FROM stokobatalkes_t a  
                    INNER JOIN penerimaanobatdetail_t prd on prd.penerimaanobatdetail_id=a.penerimaanobatdetail_id 
                    INNER JOIN penerimaanobat_t pr on pr.penerimaanobat_id = prd.penerimaanobat_id
                    INNER JOIN validasipoobat_t po on po.validasipoobat_id = pr.validasipoobat_id
                    LEFT JOIN pajak_m tax on tax.pajak_id = po.pajak_id
                    LEFT JOIN (
                        SELECT 
                            conv.obatalkes_id,
                            conv.satuankonversi_id conversion_id,
                            conv.nilai_konversi conversion_rate,
                            uom.satuanunit_id uom_id,
                            uom.satuanunit_nama uom_name, 
                            uom_po.satuanunit_id normal_uom_id,
                            uom_po.satuanunit_nama normal_uom_name
                        FROM satuanunit_m uom 
                        INNER JOIN satuankonversi_m conv on conv.satuankecil_id = uom.satuanunit_id
                        INNER JOIN satuanunit_m uom_po on uom_po.satuanunit_id = conv.satuanbesar_id
                    ) uom on uom.obatalkes_id = prd.obatalkes_id 
                        AND uom.conversion_id = prd.s_konversiobt_id
                    WHERE a.penerimaanobatdetail_id IS NOT NULL 
                        AND a.is_deleted = false 
                    
                    UNION ALL 
                    
                    SELECT 
                        a.stokobatalkes_id move_id,
                        (CASE 
                            WHEN a.terimamutasidetail_id IS NOT NULL THEN 'INTERNAL RECEIPT'
                            WHEN a.returresepdetail_id IS NOT NULL THEN 'RETURN PRESCRIPTION'
                            WHEN a.mutasiobatdetail_id IS NOT NULL THEN 'INTERNAL TRANSFER'
                            WHEN a.obatalkespasien_id IS NOT NULL THEN 'SALES'
                            WHEN a.pemusnahanobatdetail_id IS NOT NULL THEN 'LOSS BREAKAGE'
                            WHEN a.stokopnamedetail_id IS NOT NULL THEN (CASE 
                                WHEN coalesce(a.qtystok_in,0) > 0 THEN 'STOCK OPNAME IN'
                                ELSE 'STOCK OPNAME OUT' END)
                            WHEN a.pemakaianobatdetail_id IS NOT NULL THEN 'STORE CONSUMPTION'
                            WHEN a.produksiobatdetail_id IS NOT NULL THEN 'PREPARED ITEM'
                            WHEN a.storexpiredobatdetail_id IS NOT NULL THEN 'EXPIRED ITEM'
                            WHEN a.adjusmenobatmasuk_id IS NOT NULL THEN 'ADJUSTMENT RECEIPT'
                            WHEN a.adjusmenobatkeluar_id IS NOT NULL THEN 'ADJUSTMENT ISSUE'
                            WHEN a.pembatalanresep_id IS NOT NULL THEN 'CANCEL PRESCRIPTION'
                            WHEN a.penerimaanobatdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT'
                            WHEN a.penerimaansuppdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT WO'
                            WHEN a.returpenerimaanobatdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT RETURN'
                        END) move_type,   
                        coalesce(a.tglstok_in,a.tglstok_out) move_date,
                        a.ruangan_id location_id,
                        a.obatalkes_id item_id,
                        'MEDIC' item_type,
                        a.nobatch batch_no,
                        a.tglkadaluarsa expired_date,
                        a.tglstok_in stock_in_date,
                        a.qtystok_in stock_in,
                        a.tglstok_out stock_out_date,
                        a.qtystok_out stock_out,
                        ((prd.harga_netto - (prd.diskon * prd.harga_netto / 100.00) + 
                        (coalesce(tax.pajak_persen,0) / 100.00 * (prd.harga_netto - (prd.diskon * prd.harga_netto / 100.00)))
                        ) / prd.qty_besar / uom.conversion_rate) nett_price,
                        --a.harganetto nett_price,
                        --a.satuankecil_id uom_id,
                        a.rakobat_id rack_id,
                        prd.satuankonversi_id s_konversiobt_id,
                        null::integer s_konversibrg_id 
                    FROM stokobatalkes_t a  
                    INNER JOIN penerimaansuppdetail_t prd on prd.penerimaansuppdetail_id=a.penerimaansuppdetail_id 
                    INNER JOIN penerimaansupp_t pr on pr.penerimaansupp_id = prd.penerimaansupp_id
                    LEFT JOIN pajak_m tax on tax.pajak_id = pr.pajak_id
                    LEFT JOIN (
                        SELECT 
                            conv.obatalkes_id,
                            conv.satuankonversi_id conversion_id,
                            conv.nilai_konversi conversion_rate,
                            uom.satuanunit_id uom_id,
                            uom.satuanunit_nama uom_name, 
                            uom_po.satuanunit_id normal_uom_id,
                            uom_po.satuanunit_nama normal_uom_name
                        FROM satuanunit_m uom 
                        INNER JOIN satuankonversi_m conv on conv.satuankecil_id = uom.satuanunit_id
                        INNER JOIN satuanunit_m uom_po on uom_po.satuanunit_id = conv.satuanbesar_id
                    ) uom on uom.obatalkes_id = prd.obatalkes_id 
                        AND uom.conversion_id = prd.satuankonversi_id
                    WHERE a.penerimaansuppdetail_id IS NOT NULL 
                        AND a.is_deleted = false 
                    
                    UNION ALL 
                    
                    SELECT 
                        a.stokobatalkes_id move_id,
                        (CASE 
                            WHEN a.terimamutasidetail_id IS NOT NULL THEN 'INTERNAL RECEIPT'
                            WHEN a.returresepdetail_id IS NOT NULL THEN 'RETURN PRESCRIPTION'
                            WHEN a.mutasiobatdetail_id IS NOT NULL THEN 'INTERNAL TRANSFER'
                            WHEN a.obatalkespasien_id IS NOT NULL THEN 'SALES'
                            WHEN a.pemusnahanobatdetail_id IS NOT NULL THEN 'LOSS BREAKAGE'
                            WHEN a.stokopnamedetail_id IS NOT NULL THEN (CASE 
                                WHEN coalesce(a.qtystok_in,0) > 0 THEN 'STOCK OPNAME IN'
                                ELSE 'STOCK OPNAME OUT' END)
                            WHEN a.pemakaianobatdetail_id IS NOT NULL THEN 'STORE CONSUMPTION'
                            WHEN a.produksiobatdetail_id IS NOT NULL THEN 'PREPARED ITEM'
                            WHEN a.storexpiredobatdetail_id IS NOT NULL THEN 'EXPIRED ITEM'
                            WHEN a.adjusmenobatmasuk_id IS NOT NULL THEN 'ADJUSTMENT RECEIPT'
                            WHEN a.adjusmenobatkeluar_id IS NOT NULL THEN 'ADJUSTMENT ISSUE'
                            WHEN a.pembatalanresep_id IS NOT NULL THEN 'CANCEL PRESCRIPTION'
                            WHEN a.penerimaanobatdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT'
                            WHEN a.penerimaansuppdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT WO'
                            WHEN a.returpenerimaanobatdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT RETURN'
                        END) move_type,   
                        coalesce(a.tglstok_in,a.tglstok_out) move_date,
                        a.ruangan_id location_id,
                        a.obatalkes_id item_id,
                        'MEDIC' item_type,
                        a.nobatch batch_no,
                        a.tglkadaluarsa expired_date,
                        a.tglstok_in stock_in_date,
                        a.qtystok_in stock_in,
                        a.tglstok_out stock_out_date,
                        a.qtystok_out stock_out,
                        (CASE 
                            WHEN prd.penerimaanobatdetail_id IS NOT NULL 
                        THEN ((pop.harga - (pop.discount * pop.harga / 100.00) + 
                            (coalesce(tax.pajak_persen,0) / 100.00 * (pop.harga - (pop.discount * pop.harga / 100.00)))
                            ) / uom.conversion_rate) 
                            WHEN prd.penerimaansuppdetail_id IS NOT NULL  
                            THEN ((psp.harga_netto - (psp.diskon * psp.harga_netto / 100.00) + 
                            (coalesce(tax.pajak_persen,0) / 100.00 * (psp.harga_netto - (psp.diskon * psp.harga_netto / 100.00)))
                            ) / uom.conversion_rate)
                        END) nett_price,
                        --a.harganetto nett_price,
                        --a.satuankecil_id uom_id,
                        a.rakobat_id rack_id,
                        psp.satuankonversi_id s_konversiobt_id,
                        null::integer s_konversibrg_id 
                    FROM stokobatalkes_t a  
                    INNER JOIN returpenerimaanobatdetail_t prd on prd.returpenerimaanobatdetail_id=a.returpenerimaanobatdetail_id 
                    LEFT JOIN penerimaanobatdetail_t pop on pop.penerimaanobatdetail_id = prd.penerimaanobatdetail_id
                    LEFT JOIN penerimaanobat_t po on po.penerimaanobat_id = prd.penerimaanobat_id
                    LEFT JOIN validasipoobat_t vo on vo.validasipoobat_id = po.validasipoobat_id
                    LEFT JOIN penerimaansuppdetail_t psp on psp.penerimaansuppdetail_id = prd.penerimaansuppdetail_id
                    LEFT JOIN penerimaansupp_t ps on ps.penerimaansupp_id = psp.penerimaansupp_id
                    LEFT JOIN pajak_m tax on tax.pajak_id = coalesce(vo.pajak_id, ps.pajak_id)
                    LEFT JOIN (
                        SELECT 
                            conv.obatalkes_id,
                            conv.satuankonversi_id conversion_id,
                            conv.nilai_konversi conversion_rate,
                            uom.satuanunit_id uom_id,
                            uom.satuanunit_nama uom_name, 
                            uom_po.satuanunit_id normal_uom_id,
                            uom_po.satuanunit_nama normal_uom_name
                        FROM satuanunit_m uom 
                        INNER JOIN satuankonversi_m conv on conv.satuankecil_id = uom.satuanunit_id
                        INNER JOIN satuanunit_m uom_po on uom_po.satuanunit_id = conv.satuanbesar_id
                        --WHERE conv.is_deleted = false 
                    ) uom on uom.obatalkes_id = prd.obatalkes_id 
                        AND uom.conversion_id = coalesce(pop.s_konversiobt_id, psp.satuankonversi_id)
                    WHERE a.returpenerimaanobatdetail_id IS NOT NULL 
                        AND a.is_deleted = false 
                    
                    UNION ALL 
                        
                    SELECT 
                        a.stokobatalkes_id move_id,
                        (CASE 
                            WHEN a.terimamutasidetail_id IS NOT NULL THEN 'INTERNAL RECEIPT'
                            WHEN a.returresepdetail_id IS NOT NULL THEN 'RETURN PRESCRIPTION'
                            WHEN a.mutasiobatdetail_id IS NOT NULL THEN 'INTERNAL TRANSFER'
                            WHEN a.obatalkespasien_id IS NOT NULL THEN 'SALES'
                            WHEN a.pemusnahanobatdetail_id IS NOT NULL THEN 'LOSS BREAKAGE'
                            WHEN a.stokopnamedetail_id IS NOT NULL THEN (CASE 
                                WHEN coalesce(a.qtystok_in,0) > 0 THEN 'STOCK OPNAME IN'
                                ELSE 'STOCK OPNAME OUT' END)
                            WHEN a.pemakaianobatdetail_id IS NOT NULL THEN 'STORE CONSUMPTION'
                            WHEN a.produksiobatdetail_id IS NOT NULL THEN 'PREPARED ITEM'
                            WHEN a.storexpiredobatdetail_id IS NOT NULL THEN 'EXPIRED ITEM'
                            WHEN a.adjusmenobatmasuk_id IS NOT NULL THEN 'ADJUSTMENT RECEIPT'
                            WHEN a.adjusmenobatkeluar_id IS NOT NULL THEN 'ADJUSTMENT ISSUE'
                            WHEN a.pembatalanresep_id IS NOT NULL THEN 'CANCEL PRESCRIPTION'
                            WHEN a.penerimaanobatdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT'
                            WHEN a.penerimaansuppdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT WO'
                            WHEN a.returpenerimaanobatdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT RETURN'
                        END) move_type,   
                        coalesce(a.tglstok_in,a.tglstok_out) move_date,
                        a.ruangan_id location_id,
                        a.obatalkes_id item_id,
                        'MEDIC' item_type,
                        a.nobatch batch_no,
                        a.tglkadaluarsa expired_date,
                        a.tglstok_in stock_in_date,
                        a.qtystok_in stock_in,
                        a.tglstok_out stock_out_date,
                        a.qtystok_out stock_out,
                        a.harganetto nett_price,
                        --a.satuankecil_id uom_id,
                        a.rakobat_id rack_id,
                        null::integer s_konversiobt_id,
                        null::integer s_konversibrg_id 
                    FROM stokobatalkes_t a  
                    WHERE a.penerimaanobatdetail_id is null 
                        AND a.returpenerimaanobatdetail_id is null 
                        AND a.penerimaansuppdetail_id is null 
                        AND a.is_deleted = false 
                    
                    UNION ALL 
                    
                    SELECT 
                        a.stokbarang_id move_id,
                        (CASE 
                            WHEN a.terimamutasibarangdetail_id IS NOT NULL THEN 'INTERNAL RECEIPT'
                            WHEN a.mutasibarangdetail_id IS NOT NULL THEN 'INTERNAL TRANSFER'
                            WHEN a.pemusnahanbarangdetail_id IS NOT NULL THEN 'LOSS BREAKAGE'
                            WHEN a.stokopnamebarangdetail_id IS NOT NULL THEN (CASE 
                                WHEN coalesce(a.qtystok_in,0) > 0 THEN 'STOCK OPNAME IN'
                                ELSE 'STOCK OPNAME OUT' END)
                            WHEN a.pemakaianbarangdetail_id IS NOT NULL THEN 'STORE CONSUMPTION'
                            WHEN a.produksibarangdetail_id IS NOT NULL THEN 'PREPARED ITEM'
                            WHEN a.storexpiredbarangdetail_id IS NOT NULL THEN 'EXPIRED ITEM'
                            WHEN a.adjusmenbarangmasuk_id IS NOT NULL THEN 'ADJUSTMENT RECEIPT'
                            WHEN a.adjusmenbarangkeluar_id IS NOT NULL THEN 'ADJUSTMENT ISSUE'
                            WHEN a.penerimaandetail_id IS NOT NULL THEN 'PURCHASE RECEIPT'
                            WHEN a.penerimaansuppdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT WO'
                            WHEN a.returbarangdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT RETURN'
                        END) move_type,   
                        coalesce(a.tglstok_in,a.tglstok_out) move_date,
                        a.ruangan_id location_id,
                        a.barang_id item_id,
                        'NON MEDIC' item_type,
                        a.nobatch batch_no,
                        a.tglkadaluarsa expired_date,
                        a.tglstok_in stock_in_date,
                        a.qtystok_in stock_in,
                        a.tglstok_out stock_out_date,
                        a.qtystok_out stock_out,
                        ((prd.harga - (prd.discount * prd.harga / 100.00) + 
                        (coalesce(tax.pajak_persen,0) / 100.00 * (prd.harga - (prd.discount * prd.harga / 100.00)))
                        ) / uom.conversion_rate) nett_price,
                        --a.harganetto nett_price,
                        --a.satuankecil_id uom_id,
                        a.rakbarang_id rack_id,
                        null::integer s_konversiobt_id,
                        prd.s_konversibrg_id 
                    FROM stokbarang_t a  
                    INNER JOIN penerimaanbarangdetail_t prd on prd.penerimaanbarangdetail_id=a.penerimaandetail_id 
                    INNER JOIN penerimaanbarang_t pr on pr.penerimaanbarang_id = prd.penerimaanbarang_id
                    INNER JOIN validasipobarang_t po on po.validasipobarang_id = pr.validasipobarang_id
                    LEFT JOIN pajak_m tax on tax.pajak_id = po.pajak_id
                    LEFT JOIN (
                        SELECT 
                            conv.barang_id,
                            conv.satuankonversibrg_id conversion_id,
                            conv.nilai_konversi conversion_rate,
                            uom.satuanunit_id uom_id,
                            uom.satuanunit_nama uom_name, 
                            uom_po.satuanunit_id normal_uom_id,
                            uom_po.satuanunit_nama normal_uom_name
                        FROM satuanunit_m uom 
                        INNER JOIN satuankonversibrg_m conv on conv.satuankecil_id = uom.satuanunit_id
                        INNER JOIN satuanunit_m uom_po on uom_po.satuanunit_id = conv.satuanbesar_id
                        --WHERE conv.is_deleted = false 
                    ) uom on uom.barang_id = prd.barang_id 
                        AND uom.conversion_id = prd.s_konversibrg_id
                    WHERE a.penerimaandetail_id IS NOT NULL 
                        AND a.is_deleted = false 
                    
                    UNION ALL 
                    
                    SELECT 
                        a.stokbarang_id move_id,
                        (CASE 
                            WHEN a.terimamutasibarangdetail_id IS NOT NULL THEN 'INTERNAL RECEIPT'
                            WHEN a.mutasibarangdetail_id IS NOT NULL THEN 'INTERNAL TRANSFER'
                            WHEN a.pemusnahanbarangdetail_id IS NOT NULL THEN 'LOSS BREAKAGE'
                            WHEN a.stokopnamebarangdetail_id IS NOT NULL THEN (CASE 
                                WHEN coalesce(a.qtystok_in,0) > 0 THEN 'STOCK OPNAME IN'
                                ELSE 'STOCK OPNAME OUT' END)
                            WHEN a.pemakaianbarangdetail_id IS NOT NULL THEN 'STORE CONSUMPTION'
                            WHEN a.produksibarangdetail_id IS NOT NULL THEN 'PREPARED ITEM'
                            WHEN a.storexpiredbarangdetail_id IS NOT NULL THEN 'EXPIRED ITEM'
                            WHEN a.adjusmenbarangmasuk_id IS NOT NULL THEN 'ADJUSTMENT RECEIPT'
                            WHEN a.adjusmenbarangkeluar_id IS NOT NULL THEN 'ADJUSTMENT ISSUE'
                            WHEN a.penerimaandetail_id IS NOT NULL THEN 'PURCHASE RECEIPT'
                            WHEN a.penerimaansuppdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT WO'
                            WHEN a.returbarangdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT RETURN'
                        END) move_type,   
                        coalesce(a.tglstok_in,a.tglstok_out) move_date,
                        a.ruangan_id location_id,
                        a.barang_id item_id,
                        'NON MEDIC' item_type,
                        a.nobatch batch_no,
                        a.tglkadaluarsa expired_date,
                        a.tglstok_in stock_in_date,
                        a.qtystok_in stock_in,
                        a.tglstok_out stock_out_date,
                        a.qtystok_out stock_out,
                        ((prd.harga_netto - (prd.diskon * prd.harga_netto / 100.00) + 
                        (coalesce(tax.pajak_persen,0) / 100.00 * (prd.harga_netto - (prd.diskon * prd.harga_netto / 100.00)))
                        ) / prd.qty_besar / uom.conversion_rate) nett_price,
                        --a.harganetto nett_price,
                        --a.satuankecil_id uom_id,
                        a.rakbarang_id rack_id,
                        prd.satuankonversi_id s_konversiobt_id,
                        null::integer s_konversibrg_id 
                    FROM stokbarang_t a  
                    INNER JOIN penerimaansuppdetail_t prd on prd.penerimaansuppdetail_id=a.penerimaansuppdetail_id 
                    INNER JOIN penerimaansupp_t pr on pr.penerimaansupp_id = prd.penerimaansupp_id
                    LEFT JOIN pajak_m tax on tax.pajak_id = pr.pajak_id
                    LEFT JOIN (
                        SELECT 
                            conv.barang_id,
                            conv.satuankonversibrg_id conversion_id,
                            conv.nilai_konversi conversion_rate,
                            uom.satuanunit_id uom_id,
                            uom.satuanunit_nama uom_name, 
                            uom_po.satuanunit_id normal_uom_id,
                            uom_po.satuanunit_nama normal_uom_name
                        FROM satuanunit_m uom 
                        INNER JOIN satuankonversibrg_m conv on conv.satuankecil_id = uom.satuanunit_id
                        INNER JOIN satuanunit_m uom_po on uom_po.satuanunit_id = conv.satuanbesar_id
                    ) uom on uom.barang_id = prd.barang_id 
                        AND uom.conversion_id = prd.satuankonversi_id
                    WHERE a.penerimaansuppdetail_id IS NOT NULL 
                        AND a.is_deleted = false 
                    
                    UNION ALL 
                    
                    SELECT 
                        a.stokbarang_id move_id,
                        (CASE 
                            WHEN a.terimamutasibarangdetail_id IS NOT NULL THEN 'INTERNAL RECEIPT'
                            WHEN a.mutasibarangdetail_id IS NOT NULL THEN 'INTERNAL TRANSFER'
                            WHEN a.pemusnahanbarangdetail_id IS NOT NULL THEN 'LOSS BREAKAGE'
                            WHEN a.stokopnamebarangdetail_id IS NOT NULL THEN (CASE 
                                WHEN coalesce(a.qtystok_in,0) > 0 THEN 'STOCK OPNAME IN'
                                ELSE 'STOCK OPNAME OUT' END)
                            WHEN a.pemakaianbarangdetail_id IS NOT NULL THEN 'STORE CONSUMPTION'
                            WHEN a.produksibarangdetail_id IS NOT NULL THEN 'PREPARED ITEM'
                            WHEN a.storexpiredbarangdetail_id IS NOT NULL THEN 'EXPIRED ITEM'
                            WHEN a.adjusmenbarangmasuk_id IS NOT NULL THEN 'ADJUSTMENT RECEIPT'
                            WHEN a.adjusmenbarangkeluar_id IS NOT NULL THEN 'ADJUSTMENT ISSUE'
                            WHEN a.penerimaandetail_id IS NOT NULL THEN 'PURCHASE RECEIPT'
                            WHEN a.penerimaansuppdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT WO'
                            WHEN a.returbarangdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT RETURN'
                        END) move_type,   
                        coalesce(a.tglstok_in,a.tglstok_out) move_date,
                        a.ruangan_id location_id,
                        a.barang_id item_id,
                        'NON MEDIC' item_type,
                        a.nobatch batch_no,
                        a.tglkadaluarsa expired_date,
                        a.tglstok_in stock_in_date,
                        a.qtystok_in stock_in,
                        a.tglstok_out stock_out_date,
                        a.qtystok_out stock_out,
                        (CASE 
                            WHEN prd.penerimaanbarangdetail_id IS NOT NULL 
                        THEN ((pop.harga - (pop.discount * pop.harga / 100.00) + 
                            (coalesce(tax.pajak_persen,0) / 100.00 * (pop.harga - (pop.discount * pop.harga / 100.00)))
                            ) / uom.conversion_rate) 
                            WHEN prd.penerimaansuppbrgdetail_id IS NOT NULL  
                            THEN ((psp.harga_netto - (psp.diskon * psp.harga_netto / 100.00) + 
                            (coalesce(tax.pajak_persen,0) / 100.00 * (psp.harga_netto - (psp.diskon * psp.harga_netto / 100.00)))
                            ) / uom.conversion_rate)
                        END) nett_price,
                        --a.harganetto nett_price,
                        --a.satuankecil_id uom_id,
                        a.rakbarang_id rack_id,
                        null::integer s_konversiobt_id,
                        pop.s_konversibrg_id 
                    FROM stokbarang_t a  
                    INNER JOIN returpenerimaanbarangdetail_t prd on prd.returpenerimaanbarangdetail_id=a.returbarangdetail_id 
                    LEFT JOIN penerimaanbarangdetail_t pop on pop.penerimaanbarangdetail_id = prd.penerimaanbarangdetail_id
                    LEFT JOIN penerimaanbarang_t po on po.penerimaanbarang_id = prd.penerimaanbarang_id
                    LEFT JOIN validasipobarang_t vo on vo.validasipobarang_id = po.validasipobarang_id
                    LEFT JOIN penerimaansuppdetail_t psp on psp.penerimaansuppdetail_id = prd.penerimaansuppbrgdetail_id
                    LEFT JOIN penerimaansupp_t ps on ps.penerimaansupp_id = psp.penerimaansupp_id
                    LEFT JOIN pajak_m tax on tax.pajak_id = coalesce(vo.pajak_id, ps.pajak_id)
                    LEFT JOIN (
                        SELECT 
                            conv.barang_id,
                            conv.satuankonversibrg_id conversion_id,
                            conv.nilai_konversi conversion_rate,
                            uom.satuanunit_id uom_id,
                            uom.satuanunit_nama uom_name, 
                            uom_po.satuanunit_id normal_uom_id,
                            uom_po.satuanunit_nama normal_uom_name
                        FROM satuanunit_m uom 
                        INNER JOIN satuankonversibrg_m conv on conv.satuankecil_id = uom.satuanunit_id
                        INNER JOIN satuanunit_m uom_po on uom_po.satuanunit_id = conv.satuanbesar_id
                    ) uom on uom.barang_id = prd.barang_id 
                        AND uom.conversion_id = coalesce(pop.s_konversibrg_id, psp.satuankonversi_id)
                    WHERE a.returbarangdetail_id IS NOT NULL 
                        AND a.is_deleted = false 
                        
                    UNION ALL  
                        
                    SELECT 
                        a.stokbarang_id move_id,
                        (CASE 
                            WHEN a.terimamutasibarangdetail_id IS NOT NULL THEN 'INTERNAL RECEIPT'
                            WHEN a.mutasibarangdetail_id IS NOT NULL THEN 'INTERNAL TRANSFER'
                            WHEN a.pemusnahanbarangdetail_id IS NOT NULL THEN 'LOSS BREAKAGE'
                            WHEN a.stokopnamebarangdetail_id IS NOT NULL THEN (CASE 
                                WHEN coalesce(a.qtystok_in,0) > 0 THEN 'STOCK OPNAME IN'
                                ELSE 'STOCK OPNAME OUT' END)
                            WHEN a.pemakaianbarangdetail_id IS NOT NULL THEN 'STORE CONSUMPTION'
                            WHEN a.produksibarangdetail_id IS NOT NULL THEN 'PREPARED ITEM'
                            WHEN a.storexpiredbarangdetail_id IS NOT NULL THEN 'EXPIRED ITEM'
                            WHEN a.adjusmenbarangmasuk_id IS NOT NULL THEN 'ADJUSTMENT RECEIPT'
                            WHEN a.adjusmenbarangkeluar_id IS NOT NULL THEN 'ADJUSTMENT ISSUE'
                            WHEN a.penerimaandetail_id IS NOT NULL THEN 'PURCHASE RECEIPT'
                            WHEN a.penerimaansuppdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT WO'
                            WHEN a.returbarangdetail_id IS NOT NULL THEN 'PURCHASE RECEIPT RETURN'
                        END) move_type,   
                        coalesce(a.tglstok_in,a.tglstok_out) move_date,
                        a.ruangan_id location_id,
                        a.barang_id item_id,
                        'NON MEDIC' item_type,
                        a.nobatch batch_no,
                        a.tglkadaluarsa expired_date,
                        a.tglstok_in stock_in_date,
                        a.qtystok_in stock_in,
                        a.tglstok_out stock_out_date,
                        a.qtystok_out stock_out,
                        a.harganetto nett_price,
                        --a.satuankecil_id uom_id,
                        a.rakbarang_id rack_id,
                        null::integer s_konversiobt_id,
                        null::integer s_konversibrg_id 
                    FROM stokbarang_t a  
                    WHERE a.penerimaandetail_id is null 
                        AND a.returbarangdetail_id is null 
                        AND a.penerimaansuppdetail_id is null 
                        AND a.is_deleted = false 
                ) AS a  
                LEFT JOIN compare_obat oa ON oa.obatalkes_id=a.item_id AND a.item_type='MEDIC'
                LEFT JOIN int_barang_v b ON b.barang_id=a.item_id AND a.item_type='NON MEDIC'
                LEFT JOIN obatalkes_m c ON c.obatalkes_id=a.item_id AND a.item_type='MEDIC'
                LEFT JOIN barang_m d ON d.barang_id=a.item_id AND a.item_type='NON MEDIC'
                LEFT JOIN LATERAL (
                    SELECT 
                        (case 
                            when a2.satuankonversi_id=a2.obatalkes_id
                            then false else a2.is_deleted end) konversi_salah,
                        a2.nilai_konversi konversi_asli,
                        coalesce(d2.satuanbesar_id, b2.satuanbesar_id, c2.satuanbesar_id, a2.satuanbesar_id) satuanbesar_id,
                        coalesce(d2.satuankecil_id, b2.satuankecil_id, c2.satuankecil_id, a2.satuankecil_id) satuankecil_id,
                        coalesce(d2.nilai_konversi, b2.nilai_konversi, c2.nilai_konversi, a2.nilai_konversi) nilai_konversi
                    FROM satuankonversi_m a2 
                    LEFT JOIN satuankonversi_m b2 on b2.obatalkes_id = a2.obatalkes_id 
                        and b2.is_deleted=false 
                        and a2.is_deleted=true 
                        and b2.nilai_konversi <> 1
                        and b2.satuankecil_id = a2.satuankecil_id
                        and b2.satuanbesar_id <> a2.satuanbesar_id 
                    LEFT JOIN satuankonversi_m c2 
                    on c2.satuanbesar_id = c.satuanbesar_id
                        and c2.satuankecil_id = c.satuankecil_id
                        and c2.obatalkes_id = a2.obatalkes_id
                        and c2.is_deleted=false 
                    LEFT JOIN satuankonversi_m d2 
                    on d2.satuanbesar_id = a2.satuanbesar_id
                        and d2.satuankecil_id = a2.satuankecil_id
                        and d2.obatalkes_id = a2.obatalkes_id
                        and d2.is_deleted=false 
                    WHERE a2.satuankonversi_id = a.s_konversiobt_id
                        and a2.obatalkes_id = a.item_id 
                    LIMIT 1  
                ) t2 on 1=1
                LEFT JOIN LATERAL (
                    /* 
                    SELECT 
                        (case 
                            when a2.satuankonversibrg_id=a2.barang_id
                            then false else a2.is_deleted 
                        end) konversi_salah,
                        a2.nilai_konversi konversi_asli,
                        coalesce(d2.satuanbesar_id, b2.satuanbesar_id, c2.satuanbesar_id, a2.satuanbesar_id) satuanbesar_id,
                        coalesce(d2.satuankecil_id, b2.satuankecil_id, c2.satuankecil_id, a2.satuankecil_id) satuankecil_id,
                        coalesce(d2.nilai_konversi, b2.nilai_konversi, c2.nilai_konversi, a2.nilai_konversi) nilai_konversi
                    FROM satuankonversibrg_m a2 
                    LEFT JOIN satuankonversibrg_m b2 on b2.barang_id = a2.barang_id 
                        and b2.is_deleted=false 
                        and a2.is_deleted=true 
                        and b2.nilai_konversi <> 1
                        and b2.satuankecil_id = a2.satuankecil_id
                        and b2.satuanbesar_id <> a2.satuanbesar_id 
                    LEFT JOIN satuankonversibrg_m c2 
                        on c2.satuanbesar_id = d.satuan1_id
                        and c2.satuankecil_id = c.satuankecil_id
                        and c2.barang_id = a2.barang_id
                        and c2.is_deleted=false 
                    LEFT JOIN satuankonversibrg_m d2 
                        on d2.satuanbesar_id = a2.satuanbesar_id
                        and d2.satuankecil_id = a2.satuankecil_id
                        and d2.barang_id = a2.barang_id
                        and d2.is_deleted=false 
                    WHERE a2.satuankonversibrg_id = a.s_konversibrg_id
                        and a2.barang_id = a.item_id 
                    LIMIT 1  */
                    SELECT 
                        (case 
                            when a2.satuankonversi_id=a2.obatalkes_id
                            then false else a2.is_deleted end) konversi_salah,
                        a2.nilai_konversi konversi_asli,
                        a2.satuanbesar_id,
                        a2.satuankecil_id,
                        a2.nilai_konversi
                    FROM satuankonversi_m a2 
                    WHERE a2.satuankonversi_id = a.s_konversiobt_id
                        and a2.obatalkes_id = a.item_id 
                    LIMIT 1
                ) t3 on 1=1
                WHERE date(a.move_date) <= '{date_end}'
                GROUP BY a.item_type, a.item_id, 
                    coalesce(oa.default_code,b.default_code),
                    coalesce(oa.name,b.name),
                    coalesce(oa.sync_id_api,b.sync_id_api),
                    coalesce(cast(oa.uom_id as varchar),cast(b.uom_id as varchar))
            ) AS t 

            -- where t.item_code = 'BBK00000267'                        

        """.format(date_start=date_start, date_end=date_end)


        open(log_file, 'a').write("\n\n"+str(query))
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(query)
        result = cursor.fetchall() 
        open(log_file, 'a').write("\n\n"+str(result))

        sudo = self.env.user.sudo()
        open(log_file, 'a').write("\n Start looping update cost average per item ")
        if result:
            for line in result:
                # open(log_file, 'a').write("\n"+str(line))
                query = """
                    update product_template as pt set
                        -- cost_price = {cost_price},
                        write_date = CURRENT_TIMESTAMP,
                        write_uid = {user_id}
                    where pt.sync_type = '{sync_type}'
                        and pt.sync_id_api = '{sync_id_api}'
                """.format(
                    sync_type = sync_type,
                    sync_id_api = line['sync_id_api'],
                    cost_price=line['cost_unit'] or 0,
                    user_id = self.env.user.id
                )
                open(log_file, 'a').write("\n\n"+str(query))
                sudo.env.cr.execute(query)

                query = """
                    delete from ir_property
                    where name='standard_price'
                    and res_id in(
                        select concat('product.product,',cast(pp.id as varchar))
                        from product_template pt
                        inner join product_product pp on pp.product_tmpl_id=pt.id
                        where pt.sync_id_api = '{sync_id_api}'
                            and pt.sync_type = '{sync_type}'
                    )
                """.format(
                    sync_id_api=line['sync_id_api'],
                    sync_type=sync_type)
                open(log_file, 'a').write("\n\n"+str(query))
                sudo.env.cr.execute(query)

                query = """
                    insert into ir_property (
                        type, value_float, name, res_id, create_uid, write_uid,
                        create_date, write_date, fields_id, company_id)
                    select 
                        'float' type2, 
                        {cost_price} value_float, 
                        'standard_price' name2, 
                        concat('product.product,',cast(pp.id as varchar)) res_id, 
                        {user_id} create_uid, {user_id} write_uid, 
                        CURRENT_TIMESTAMP create_date, 
                        CURRENT_TIMESTAMP write_date, 
                        fl.id fields_id, {company_id} company_id 
                    from product_template pt
                    inner join product_product pp on pp.product_tmpl_id=pt.id
                    inner join ir_model_fields fl on fl.name='standard_price' and fl.model='product.product'
                    where pt.sync_id_api = '{sync_id_api}'
                        and pt.sync_type = '{sync_type}'
                """.format(
                    company_id=self.company_id.id,
                    cost_price=line['cost_unit'],
                    sync_id_api=line['sync_id_api'],
                    sync_type=sync_type,
                    user_id = self.env.user.id)
                open(log_file, 'a').write("\n\n"+str(query))
                sudo.env.cr.execute(query)


                query = """
                    delete from product_price_history
                    where date(datetime) = date('{date_end}')
                        and product_tmpl_id in(
                            select id from product_template 
                            where sync_id_api = '{sync_id_api}'
                            and sync_type = '{sync_type}')
                """.format(
                    sync_id_api=line['sync_id_api'],
                    sync_type=sync_type, date_end=date_end)
                open(log_file, 'a').write("\n\n"+str(query))
                sudo.env.cr.execute(query)


                query = """
                    insert into product_price_history (
                        company_id, datetime, product_id, product_tmpl_id, cost,
                        create_uid, write_uid, create_date, write_date)
                    select 
                        {company_id} company_id,
                        date('{date_end}') datetime,
                        pp.id product_id, 
                        pt.id product_tmpl_id, 
                        '{cost_price}'::float cost_unit, 
                        {user_id} create_uid, 
                        {user_id} write_uid, 
                        CURRENT_TIMESTAMP create_date, 
                        CURRENT_TIMESTAMP write_date 
                    from product_template pt
                    inner join product_product pp on pp.product_tmpl_id=pt.id
                    where pt.sync_id_api = '{sync_id_api}'
                        and pt.sync_type = '{sync_type}'
                """.format(
                    company_id=self.company_id.id,
                    cost_price=line['cost_unit'],
                    sync_id_api=line['sync_id_api'],
                    sync_type=sync_type,
                    date_end = date_end,
                    user_id = self.env.user.id)
                open(log_file, 'a').write("\n\n"+str(query))
                sudo.env.cr.execute(query)

                
    # @api.multi 
    def bulk_takeout(self):
        report_id = self.id 
        company_id = self.company_id.id
        date_start = datetime.strptime(str(self.date_start), '%Y-%m-%d')
        date_end = datetime.strptime(str(self.date_end), '%Y-%m-%d')
        
        print ("flag for ACCRUAL NON EMERGENCY & NON IPD")
        query = """
            UPDATE sale_order_line AS a SET is_takeout = True
            FROM sale_order so
            WHERE so.id = a.order_id
                AND a.type_line in ('ACCRUAL','ACCRUAL REVERSAL')
                AND a.is_takeout is not True
                AND so.patient_type NOT IN ('2','3')
                AND a.company_id = {company_id}
                AND a.tglproses >= '{date_start}'
                AND a.tglproses <= '{date_end}'
        """.format(company_id=company_id, date_start=date_start, date_end=date_end)
        self.sudo().env.cr.execute(query)
        open('/opt/odoo16/logs/sale_bulk_closing.log', 'a+').write(str(query))

        print ("flag is_takeout =False for selain accrual & reversal OPD & MCU")
        query = """
            UPDATE sale_order_line AS a SET is_takeout = False
            FROM sale_order so 
            WHERE so.id = a.order_id
                AND (
                    a.type_line not in('ACCRUAL','ACCRUAL REVERSAL') OR
                    so.patient_type IN ('2','3')
                )
                AND a.company_id = {company_id}
                AND a.tglproses >= '{date_start}'
                AND a.tglproses <= '{date_end}'
        """.format(company_id=company_id, date_start=date_start, date_end=date_end)
        self.sudo().env.cr.execute(query)
        open('/opt/odoo16/logs/sale_bulk_closing.log', 'a+').write(str(query))

        print ("flag for MODIFIED BILLING backdate (Issue di Doco)")
        query = """
            UPDATE sale_order_line AS a set is_takeout = True 
            FROM sale_order_bill b 
            WHERE b.id = a.billing_id 
                AND a.company_id = {company_id} 
                AND a.tglproses >= '{date_start}'
                AND a.tglproses <= '{date_end}'
                AND date(a.create_date) > '{date_end}'
                AND date(a.tglproses) < date(b.cancel_date)
                AND b."state" = 'cancel'
                AND a.is_takeout is not True
            -- AND a.type_line in('BILL CANCEL','BILLING CANCEL','DISCOUNT CANCEL')
        """.format(company_id=company_id, date_start=date_start, date_end=date_end)
        self.sudo().env.cr.execute(query)
        open('/opt/odoo16/logs/sale_bulk_closing.log', 'a+').write(str(query))

        print ("flag for BILLING")
        query = """
            UPDATE sale_order_line AS a SET is_takeout = False
            WHERE a.type_line not in ('ACCRUAL','ACCRUAL REVERSAL')
                AND a.is_takeout IS NULL
                AND a.company_id = {company_id}
                AND a.tglproses >= '{date_start}'
                AND a.tglproses <= '{date_end}'
        """.format(company_id=company_id, date_start=date_start, date_end=date_end)
        self.sudo().env.cr.execute(query)
        open('/opt/odoo16/logs/sale_bulk_closing.log', 'a+').write(str(query))


    # @api.multi
    def bulk_update(self):
        report_id = self.id 
        company_id = self.company_id.id
        date_start = datetime.strptime(str(self.date_start), '%Y-%m-%d')
        date_end = datetime.strptime(str(self.date_end), '%Y-%m-%d')
        
        open('/opt/odoo16/logs/sale_bulk_closing.log', 'a+').write(str('\nStart update sale.order.line:'))

        query = """
            update sale_order_line as sol set 
                cost_unit_odoo = (pcp.cost), 
                cost_total_odoo = (pcp.cost * sol.product_uom_qty),
                write_date = CURRENT_TIMESTAMP
            from product_product pp 
            inner join product_template pt on pt.id=pp.product_tmpl_id
            inner join product_price_history pcp on pcp.product_id=pp.id
            where pp.id = sol.product_id
                and date(pcp.datetime) = date('{date_end}')
                -- and coalesce(sol.cost_unit,0) = 0
                and sol.service_categ_id in(
                    select id from product_category 
                    where name in ('Pharmacy','Drug','Drugs','Consumable','Consumables','DRUG','DRUGS','PHARMACY','CONSUMABLE','CONSUMABLES'))
                and sol.company_id = {company_id}
                and sol.type_line not in ('DISCOUNT', 'DISCOUNT CANCEL')
                and sol.tglproses >= '{date_start}'
                and sol.tglproses <= '{date_end}'
        """.format(company_id=company_id, date_start=date_start, date_end=date_end)
        open('/opt/odoo16/logs/sale_bulk_closing.log', 'a+').write('\n'+str(query))

        self.sudo().env.cr.execute(query)
        open('/opt/odoo16/logs/sale_bulk_closing.log', 'a+').write(str('\nDone'))
        print("Successfully to update sale.order.line")





    # 2023.09.14 - remapping group doctor & speciality and special group 2
    # @api.multi 
    def bulk_remapping(self):
        # UPDATE MAIN PAYER NAME 
        query = """   
            UPDATE sale_order_line sol
                SET payer = COALESCE(sob.payer_id, so.payer_id)
            FROM sale_order_bill sob,
                sale_order so
            WHERE sol.billing_id = sob.id
            AND sol.order_id = so.id
            AND sol.company_id = {company_id}
            AND sol.tglproses >= '{date_start}'
            AND sol.tglproses <= '{date_end}'
            AND sol.payer IS NULL;
        """.format(
            company_id = self.company_id.id,
            date_start = self.date_start,
            date_end = self.date_end
        )
        open('/opt/odoo16/logs/log_sale_cleansing.log', 'a+').write("\n\n"+str(query))
        self.sudo().env.cr.execute(query)


        # UPDATE MAIN PAYER NAME 
        query = """   
            UPDATE sale_order_line sol
                SET payer = COALESCE(sob.payer_id, so.payer_id)
            FROM sale_order_bill sob,
                sale_order so
            WHERE sol.billing_id = sob.id
            AND sol.order_id = so.id
            AND sol.company_id = {company_id}
            AND sol.tglproses >= '{date_start}'
            AND sol.tglproses <= '{date_end}'
            AND sol.payer IS NULL;
        """.format(
            company_id = self.company_id.id,
            date_start = self.date_start,
            date_end = self.date_end
        )
        open('/opt/odoo16/logs/log_sale_cleansing.log', 'a+').write("\n\n"+str(query))
        self.sudo().env.cr.execute(query)


        # UPDATE SEPCIAL GROUP 2 = HAEMODALYSIS 
        query = """   
            UPDATE sale_order_line AS sol SET
                special_group2 = 'DIALYSIS'
            from sale_order_line a
            left join product_category pc on pc.id = a.service_categ_id
            WHERE sol.id = a.id
                AND sol.company_id = {company_id}
                AND sol.tglproses >= '{date_start}'
                AND sol.tglproses <= '{date_end}'
                AND sol.department_id in(
                    'DIALYSIS',
                    'HEMODIALISA',
                    'HEMODIALISIS',
                    'HAEMODIALISA',
                    'HAEMODIALISIS',
                    'BP- HEMODIALYSIS STORE',
                    'DIALYSIS',
                    'HAEMODIALYSIS STORE')
                and pc.name NOT IN ('Consumables', 'Pharmacy')
        """.format(
            company_id = self.company_id.id,
            date_start = self.date_start,
            date_end = self.date_end
        )
        open('/opt/odoo16/logs/log_sale_cleansing.log', 'a+').write("\n\n"+str(query))
        self.sudo().env.cr.execute(query)


        # UPDATE SEPCIAL GROUP 2 = MEDICAL REHABILITATION 
        query = """   
            UPDATE sale_order_line AS sol SET
                special_group2 = 'MEDICAL REHABILITATION'
            from sale_order_line a
            left join product_category pc on pc.id = a.service_categ_id
            WHERE sol.id = a.id
                AND sol.company_id = {company_id}
                AND sol.tglproses >= '{date_start}'
                AND sol.tglproses <= '{date_end}'
                AND sol.department_id in(
                    'REHABILITATION MEDIC',
                    'REHABILITASI MEDIC',
                    'REHABILITASI MEDIK',
                    'Rehab Medik',
                    'MEDICAL REHABILITATION',
                    'REHABILITIASI MEDIK',
                    'Rehabilitation Medic',
                    'Rehabilitasi Medik'
                )
                and pc.name NOT IN ('Consumables', 'Pharmacy')
        """.format(
            company_id = self.company_id.id,
            date_start = self.date_start,
            date_end = self.date_end
        )
        open('/opt/odoo16/logs/log_sale_cleansing.log', 'a+').write("\n\n"+str(query))
        self.sudo().env.cr.execute(query)


        # UPDATE SEPCIAL GROUP 2 = PHARMACY OUTPATIENT 
        query = """   
            UPDATE sale_order_line AS sol SET
                special_group2 = 'PHARMACY OUTPATIENT'
            from sale_order_line a
            left join product_category pc on pc.id = a.service_categ_id
            WHERE sol.id = a.id
                AND sol.company_id = {company_id}
                AND sol.tglproses >= '{date_start}'
                AND sol.tglproses <= '{date_end}'
                AND sol.department_id in(
                    'REHABILITATION MEDIC',
                    'REHABILITASI MEDIC',
                    'REHABILITASI MEDIK',
                    'Rehab Medik',
                    'MEDICAL REHABILITATION',
                    'REHABILITIASI MEDIK',
                    'Rehabilitation Medic',
                    'Rehabilitasi Medik',
                    'HEMODIALISIS'
                )
                and pc.name IN ('Consumables', 'Pharmacy')
                AND sol.patient_type ='1'
        """.format(
            company_id = self.company_id.id,
            date_start = self.date_start,
            date_end = self.date_end
        )
        open('/opt/odoo16/logs/log_sale_cleansing.log', 'a+').write("\n\n"+str(query))
        self.sudo().env.cr.execute(query)


        # UPDATE SEPCIAL GROUP 2 = PHARMACY INPATIENT 
        query = """   
            UPDATE sale_order_line AS sol SET
                special_group2 = 'PHARMACY INPATIENT'
            from sale_order_line a
            left join product_category pc on pc.id = a.service_categ_id
            WHERE sol.id = a.id
                AND sol.company_id = {company_id}
                AND sol.tglproses >= '{date_start}'
                AND sol.tglproses <= '{date_end}'
                AND sol.department_id in(
                    'REHABILITATION MEDIC',
                    'REHABILITASI MEDIC',
                    'REHABILITASI MEDIK',
                    'Rehab Medik',
                    'MEDICAL REHABILITATION',
                    'REHABILITIASI MEDIK',
                    'Rehabilitation Medic',
                    'Rehabilitasi Medik',
                    'HEMODIALISIS'

                )
                and pc.name IN ('Consumables', 'Pharmacy')
                AND sol.patient_type ='2'
        """.format(
            company_id = self.company_id.id,
            date_start = self.date_start,
            date_end = self.date_end
        )
        open('/opt/odoo16/logs/log_sale_cleansing.log', 'a+').write("\n\n"+str(query))
        self.sudo().env.cr.execute(query)



        # UPDATE ANALYTIC DOCTOR
        query = """   
            UPDATE sale_order_line AS a SET
                group_analytic_doctor_id = COALESCE(b.group_doctor_id, NULL),
                group_analytic_spec_id = COALESCE(b.group_specialization_id, NULL),
                group_analytic_subspec_id = COALESCE(b.group_subspecialization_id, b.group_specialization_id)
            FROM sale_order_line sol
            LEFT JOIN LATERAL (
                SELECT * FROM account_analytic_account b 
                WHERE b.sync_type=sol.sync_type 
                    AND b.id=(case 
                        when sol.department_id ilike '%lab%' 
                        then sol.prescribe_doc_id 
                        else sol.account_analytic_id end)
                    AND b.active=True
                ORDER BY id DESC LIMIT 1
            ) b ON 1=1
            WHERE a.id=sol.id
                AND a.company_id = {company_id}
                AND a.tglproses >= '{date_start}'
                AND a.tglproses <= '{date_end}'
                AND (
                    a.group_analytic_doctor_id IS NULL OR 
                    a.group_analytic_spec_id IS NULL OR a.group_analytic_spec_id != COALESCE(b.group_specialization_id, NULL) OR
                    a.group_analytic_subspec_id IS NULL OR a.group_analytic_subspec_id != COALESCE(b.group_subspecialization_id, NULL)
                )
        """.format(
            company_id = self.company_id.id,
            date_start = self.date_start,
            date_end = self.date_end
        )
        open('/opt/odoo16/logs/log_sale_cleansing.log', 'a+').write("\n\n"+str(query))
        self.sudo().env.cr.execute(query)


        # UPDATE PRIMARY DOCTOR
        query = """   
            UPDATE sale_order_line AS a SET
                group_primary_doctor_id = COALESCE(b.group_doctor_id, NULL),
                group_primary_spec_id = COALESCE(b.group_specialization_id, NULL),
                group_primary_subspec_id = COALESCE(b.group_subspecialization_id, b.group_specialization_id)
            FROM sale_order_line sol
            LEFT JOIN LATERAL (
                SELECT * FROM account_analytic_account b 
                WHERE b.sync_type=sol.sync_type 
                    AND b.id=sol.primary_doc_id
                    AND b.active=True
                ORDER BY id DESC LIMIT 1
            ) b ON 1=1
            WHERE a.id=sol.id
                AND a.company_id = {company_id}
                AND a.tglproses >= '{date_start}'
                AND a.tglproses <= '{date_end}'
                AND (
                    a.group_primary_doctor_id IS NULL OR 
                    a.group_primary_spec_id IS NULL OR 
                    a.group_primary_subspec_id IS NULL
                )
        """.format(
            company_id = self.company_id.id,
            date_start = self.date_start,
            date_end = self.date_end
        )
        open('/opt/odoo16/logs/log_sale_cleansing.log', 'a+').write("\n\n"+str(query))
        self.sudo().env.cr.execute(query)


        # UPDATE PERFORM DOCTOR
        query = """   
            UPDATE sale_order_line AS a SET
                group_perform_doctor_id = COALESCE(b.group_doctor_id, NULL),
                group_perform_spec_id = COALESCE(b.group_specialization_id, NULL),
                group_perform_subspec_id = COALESCE(b.group_subspecialization_id, b.group_specialization_id)
            FROM sale_order_line sol
            LEFT JOIN LATERAL (
                SELECT * FROM account_analytic_account b
                WHERE b.sync_type=sol.sync_type 
                    AND b.id=sol.perform_doc_id
                    AND b.active=True
                ORDER BY id DESC LIMIT 1
            ) b ON 1=1
            WHERE a.id=sol.id
                AND a.company_id = {company_id}
                AND a.tglproses >= '{date_start}'
                AND a.tglproses <= '{date_end}'
                AND (
                    a.group_perform_doctor_id IS NULL OR 
                    a.group_perform_spec_id IS NULL OR 
                    a.group_perform_subspec_id IS NULL
                )
        """.format(
            company_id = self.company_id.id,
            date_start = self.date_start,
            date_end = self.date_end
        )
        open('/opt/odoo16/logs/log_sale_cleansing.log', 'a+').write("\n\n"+str(query))
        self.sudo().env.cr.execute(query)


        # UPDATE PRESCRIBE DOCTOR
        query = """   
            UPDATE sale_order_line AS a SET
                group_prescribe_doctor_id = COALESCE(b.group_doctor_id, NULL),
                group_prescribe_spec_id = COALESCE(b.group_specialization_id, NULL),
                group_prescribe_subspec_id = COALESCE(b.group_subspecialization_id, b.group_specialization_id)
            FROM sale_order_line sol
            LEFT JOIN LATERAL (
                SELECT * FROM account_analytic_account b
                WHERE b.sync_type=sol.sync_type 
                    AND b.id=sol.prescribe_doc_id
                    AND b.active=True
                ORDER BY id DESC LIMIT 1
            ) b ON 1=1
            WHERE a.id=sol.id
                AND a.company_id = {company_id}
                AND a.tglproses >= '{date_start}'
                AND a.tglproses <= '{date_end}'
                AND (
                    a.group_prescribe_doctor_id IS NULL OR 
                    a.group_prescribe_spec_id IS NULL OR 
                    a.group_prescribe_subspec_id IS NULL
                )
        """.format(
            company_id = self.company_id.id,
            date_start = self.date_start,
            date_end = self.date_end
        )
        open('/opt/odoo16/logs/log_sale_cleansing.log', 'a+').write("\n\n"+str(query))
        self.sudo().env.cr.execute(query)






# 2021.09.23 - billing bulk syncing
class SaleBulkSyncingWizard(models.TransientModel):
    _name = 'sale.bulk.syncing.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    billing_ids = fields.One2many('sale.bulk.syncing.line', 'syncing_id', string="Billing")


    # @api.multi
    def bulk_clear(self):
        self.billing_ids = None
        return {
            'type': 'ir.actions.act_window',
            'name': 'Billing Bulk Syncing',
            'view_mode': 'form', 
            'target': 'new',
            'res_id': self.id,
            'res_model': 'sale.bulk.syncing.wizard',
            'context': {'default_id': self.id} 
        }



    # @api.multi
    def bulk_cleansing(self):
        report_id = self.id 
        company_id = self.company_id.id 
        sync_type = self.company_id.sync_type
        billing_ids = []
        data = []

        for bill in self.billing_ids:
            if " " in bill.name.strip().replace(",", " "):
                # open('/opt/odoo16/logs/log_sale_bulk_syncing.log','a+').write('\n' + str(bill.name.strip().replace(",", " ")))
                for row in bill.name.split(" "):
                    # open('/opt/odoo16/logs/log_sale_bulk_syncing.log','a+').write('\n' + str(row))
                    if row not in ['']:
                        # open('/opt/odoo16/logs/log_sale_bulk_syncing.log','a+').write('\n' + str(row))
                        billing_ids.append(row)
            else:
                billing_ids.append(bill.name.strip())

        # open('/opt/odoo16/logs/log_sale_bulk_syncing.log','a+').write('\n' + str(billing_ids))
        self.billing_ids = None
        for bill in billing_ids:
            self.env['sale.bulk.syncing.line'].create({'syncing_id': self.id, 'name': bill})
            

        return {
            'type': 'ir.actions.act_window',
            'name': 'Billing Bulk Syncing',
            'view_mode': 'form', 
            'target': 'new',
            'res_id': self.id,
            'res_model': 'sale.bulk.syncing.wizard',
            'context': {'default_id': self.id} 
        }


    # @api.multi
    def bulk_syncing(self):
        report_id = self.id 
        company_id = self.company_id.id 
        sync_type = self.company_id.sync_type
        billing_ids = []
        billing_ids.append("[NO_BILLING]")
        data = []

        for bill in self.billing_ids:
            billing_ids.append(str(bill.name))

        sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().env['sale.order.bill'].search([('sync_type', '=', sync_type), ('sync_id', '>', 0), ('billno','in', billing_ids)])}
        invoice_id = [record.billno for record in self.sudo().env['sale.order.bill'].search([('state','=','invoice'), ('sync_type', '=', sync_type), ('sync_id', '>', 0), ('billno','in', billing_ids)], limit=1)]
        billing_ids = tuple(billing_ids)

        if invoice_id:
            raise exceptions.UserError("Billing {billno} yang sudah di invoice tidak dapat di bulking.".format(billno=','.join(invoice_id)))
        
        # syncing patient if not exists
        open('/opt/odoo16/logs/log_sale_bulk_syncing.log', 'a+').write(str('\nStart update patient.'))
        query = """
            SELECT DISTINCT 
                 a.sync_id
                ,a.registration_code
                ,a.registration_code vendor_code
                ,a.name
                ,a.display_name
                ,a.gender
                ,a.title_name
                ,a.patient_city
                ,a.patient_district 
                ,a.patient_subdistrict
                ,a.date_of_birth
                ,a.street
                ,a.street2
                ,a.street3
                ,a.zip
                ,a.phone
                ,a.mobile
                ,a.email
                ,a.contact_person
                ,a.passport
                ,a.ktp
                ,a.ModDate, a.wipro_block,
                cast('False' as bit) 'supplier',
                cast('False' as bit) 'vendor_wipro',
                cast('True' as bit) 'customer',
                cast('False' as bit) 'customer_wipro',
                cast('False' as bit) 'insurance',
                cast('True' as bit) 'patient',
                cast('False' as bit) 'doctor',
                cast('True' as bit) 'active'
            FROM dbo.VRP_OdooPatients a
            INNER JOIN dbo.VRP_OdooSaleOrderBill b ON b.partner_id = a.sync_id
            WHERE b.billno in {billing_ids} 
            """ . format(billing_ids=billing_ids)
        open('/opt/odoo16/logs/log_sale_bulk_syncing.log', 'a+').write('\n'+str(query))
        data = sync.get_data(sync.servers.get(sync_type), query)

        if data:    
            # stored existing patient in res.partner
            sync_ids = [row['sync_id'] for row in data]
            sync_ids.append(0)

            self.env.cr.execute("""
                SELECT cast(sync_id as integer) sync_id, id 
                FROM res_partner 
                WHERE patient = True 
                    AND active = True 
                    AND sync_type = '{sync_type}' 
                    AND sync_id in {sync_ids}
                """.format(
                    sync_type=sync_type,
                    sync_ids=tuple(sync_ids)
                ))
            sync_ids = dict(self.env.cr.fetchall())

            fields_without_id = tuple(key for key in self.env['res.partner']._fields if key != 'id' and 'property' not in key and self.env['res.partner']._fields[key].required == True)
            columns = tuple(key for key in data[0].keys() if key in self.env['res.partner']._fields and key not in fields_without_id) + ('sync_date', 'sync_type','company_id') if data else ()
            fields_without_id += columns
            fields = fields_without_id + ('id', )
            if columns:
                columns += ('id', )
            default_values = {}
            for field in fields:
                if field in columns:
                    continue
                default = self.env['res.partner']._fields[field].default
                if callable(default):
                    default = default(self)
                if isinstance(default, models.Model):
                    default = default.id
                default_values[field] = default
            values = ''
            now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            for object in data:
                for value in default_values:
                    object[value] = default_values[value]
                if int(object['sync_id']) in sync_ids:
                    object['id'] = sync_ids[object['sync_id']]
                else:
                    object['id'] = 'DEFAULT'
                #object['customer_wipro'] = True
                object['create_uid'] = 1
                object['write_uid'] = 1 
                object['create_date'] = now
                object['write_date'] = now
                object['sync_date'] = now
                object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].search([('sync_type', '=', sync_type)],limit=1).id
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
                    if isinstance(object[field], str):
                        string = object[field]
                        value += "'" + string.replace("'", "''") + "'"
                        continue
                    value += sync.json(object[field])
                value += ')'
                values += value
            excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
            columns = sync.remove_unicode(str(fields)).replace("'", "")
            columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
            query = "INSERT into res_partner %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
            print (query.encode('utf8'))
            self.env.cr.execute(query)
        

        # syncing payer 
        open('/opt/odoo16/logs/log_sale_bulk_syncing.log', 'a+').write(str('\nStart update customer-payer'))
        query = """
            SELECT DISTINCT
                a.CustomerID 'sync_id', 
                a.CustomerCode 'vendor_code',
                a.CustomerName 'name', 
                a.CustomerName 'display_name', 
                a.CustomerTypeName 'customer_type_wipro',
                a.CreditDays 'credit_days', 
                a.OpDiscountID,
                a.IPDiscountID, 
                a.TaxID, 
                cast(a.Blocked as bit) 'wipro_block',
                cast('False' as bit) 'supplier',
                cast('False' as bit) 'vendor_wipro',
                cast('True' as bit) 'customer',
                cast('True' as bit) 'customer_wipro',
                cast('True' as bit) 'insurance',
                cast('False' as bit) 'patient',
                cast('False' as bit) 'doctor',
                cast('True' as bit) 'active'
            FROM (
                select a.*, (case 
                    when a.CompUpdated > a.SuppUpdated 
                    then a.CompUpdated else a.SuppUpdated
                end) LastUpdated
                from dbo.VRP_OdooCustomer a 
                inner join dbo.VRP_OdooSaleOrderBIll b on b.payer_id = a.CustomerID
                where b.billno in {billing_ids} 
            ) a 
        """ . format(billing_ids=billing_ids)
        open('/opt/odoo16/logs/log_sale_bulk_syncing.log', 'a+').write('\n'+str(query))
        data = sync.get_data(sync.servers.get(sync_type), query)
        if data:
            
            # stored existing insurance in res.partner
            sync_ids = [row['sync_id'] for row in data]
            sync_ids.append(0)

            self.env.cr.execute("""
                SELECT cast(sync_id as integer) sync_id, id 
                FROM res_partner 
                WHERE insurance = True 
                    AND active = True 
                    AND sync_type = '{sync_type}' 
                    AND sync_id in {sync_ids}
                """.format(
                    sync_type=sync_type,
                    sync_ids=tuple(sync_ids)
                ))
            sync_ids = dict(self.env.cr.fetchall())
            
            fields_without_id = tuple(key for key in self.env['res.partner']._fields if key != 'id' and 'property' not in key and self.env['res.partner']._fields[key].required == True)
            columns = tuple(key for key in data[0].keys() if key in self.env['res.partner']._fields and key not in fields_without_id) + ('sync_date', 'sync_type','company_id') if data else ()
            fields_without_id += columns
            fields = fields_without_id + ('id', )
            if columns:
                columns += ('id', )
            default_values = {}
            for field in fields:
                if field in columns:
                    continue
                default = self.env['res.partner']._fields[field].default
                if callable(default):
                    default = default(self)
                if isinstance(default, models.Model):
                    default = default.id
                default_values[field] = default
            values = ''
            now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            for object in data:
                for value in default_values:
                    object[value] = default_values[value]
                if int(object['sync_id']) in sync_ids:
                    object['id'] = sync_ids[object['sync_id']]
                else:
                    object['id'] = 'DEFAULT'
                #object['customer_wipro'] = True
                object['create_uid'] = 1
                object['write_uid'] = 1 
                object['create_date'] = now
                object['write_date'] = now
                object['sync_date'] = now
                object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].search([('sync_type', '=', sync_type)],limit=1).id
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
                    if isinstance(object[field], str):
                        string = object[field]
                        value += "'" + string.replace("'", "''") + "'"
                        continue
                    value += sync.json(object[field])
                value += ')'
                values += value
            excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
            columns = sync.remove_unicode(str(fields)).replace("'", "")
            columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
            query = "INSERT into res_partner %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
            set_customer = "update res_partner set customer = True and insurance = True where customer_wipro = True"
            print (query.encode('utf8'))
            self.env.cr.execute(query)
            self.env.cr.execute(set_customer)


        open('/opt/odoo16/logs/log_sale_bulk_syncing.log', 'a+').write(str('\nStart update sale.order'))
        query = """
            SELECT DISTINCT 
                sync_id,
                name,
                partner_id,
                date_order,
                billno,
                confirmation_date,
                discharge_reason,
                discharge_date,
                bed_type_id,
                eligible_bed_type_id,
                alloted_bed_type_id,
                primary_doc_id,
                referral_doc_id,
                referral_id,
                referral_number,
                payer_id,
                tariff_id,
                payer_code,
                payer_type,
                patient_type,
                secondary_diagnosis_code,
                secondary_diagnosis_name,
                primary_diagnosis_code,
                primary_diagnosis_name,
                repeat_diagnosis_code,
                repeat_diagnosis_name,
                admission_type,
                state
            FROM dbo.VRP_OdooSaleOrder a 
            WHERE a.billno in {billing_ids}
        """ . format(billing_ids=billing_ids)
        open('/opt/odoo16/logs/log_sale_bulk_syncing.log', 'a+').write('\n'+str(query))
        
        values = ''
        data = sync.get_data(sync.servers.get(sync_type), query)

        if data:
            # stored existing sale.order
            sync_ids = [row['sync_id'] for row in data]
            sync_ids.append(0)

            self.env.cr.execute("""
                SELECT cast(sync_id as integer) sync_id, id 
                FROM sale_order 
                WHERE sync_type = '{sync_type}' 
                    AND sync_id in {sync_ids}
                """.format(
                    sync_type=sync_type,
                    sync_ids=tuple(sync_ids)
                ))
            sync_ids = dict(self.env.cr.fetchall())

            fields_without_id = tuple(key for key in self.env['sale.order']._fields if key != 'id' and 'property' not in key and 'ids' not in key and self.env['sale.order']._fields[key].required == True and self.env['sale.order']._fields[key].store == True)
            # columns = tuple(key for key in data[0].keys() if key in self.env['sale.order']._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
            columns = tuple(key for key in data[0].keys() if key in self.env['sale.order']._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
            fields_without_id += columns
            columns += tuple(key for key in data[0].keys() if key in self.env['sale.order']._fields and key not in columns) if data else ()
            fields = fields_without_id + ('id', )
            if columns:
                columns += ('id', )
            default_values = {}
            for field in fields:
                if field in columns:
                    continue
                default = self.env['sale.order']._fields[field].default
                if callable(default):
                    default = default(self)
                if isinstance(default, models.Model):
                    default = default.id
                default_values[field] = default
            now = tools.datetime.now().strftime('%Y%m%d %H:%M:S')
            default_values['company_id'] = self.env.company.id
            default_values['pricelist_id'] = self.env.ref('product.list0').id
            default_values['currency_id'] = self.env.company.currency_id.id
            #uom_id = self.env.ref('product.product_uom_categ_unit').id
            new_sync_ids = []
            for object in data:
                new_sync_ids += [object['sync_id']]
                for value in default_values:
                    if value in object:
                        continue
                    object[value] = default_values[value]

                partner_id = object['partner_id']
                object['partner_id'] = self.env['res.partner'].search([('sync_id', '>', 0), ('sync_id', '=', partner_id), ('sync_type', '=', sync_type), ('patient', '=', True)], order="id asc", limit=1)
                
                if object['payer_type'] == 'PRIVATE':
                    object['payer_id'] = 5817
                else:
                    object['payer_id'] = self.env['res.partner'].search([('sync_id', '>', 0), ('sync_id', '=', object['payer_id']),('sync_type', '=', sync_type), ('insurance', '=', True)], order="id asc", limit=1).id or None

                if object['primary_doc_id']:
                    object['primary_doc_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1).id or self.env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1).id or self.env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
                if object['referral_doc_id']:
                    object['referral_doc_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['referral_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1).id or None
                if object['referral_id']:
                    object['referral_id'] = self.env['referral.transaction'].search([('sync_id', '=', object['referral_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
                if object['tariff_id']:
                    object['tariff_id'] = self.env['hospital.tariff'].search([('sync_id', '=', object['tariff_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
                if object['bed_type_id']:
                    object['bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['bed_type_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
                if object['alloted_bed_type_id']:
                    object['alloted_bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['eligible_bed_type_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
                if object['eligible_bed_type_id']:
                    object['eligible_bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['alloted_bed_type_id']), ('sync_type', '=', sync_type)], order="id asc", limit=1).id or None
                            
                if not object['partner_id']:
                    open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + "pasien res.partner with sync_id %s and sync_type %s doesn't exist" % (partner_id, sync_type))
                    object['backup_partner_id'] = object['partner_id']
                    object['partner_id'] = self.env['res.partner'].search([('sync_id', '=', 99881177), ('sync_type', '=', sync_type), ('patient', '=', True)], limit=1)
                    # return
                object['partner_shipping_id'] = object['partner_id'].id or None
                object['partner_id'] = object['partner_id'].id or None
                object['partner_invoice_id'] = object['partner_id']
                # object['payer_id'] = object['payer_id'].id
                # object['project_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['project_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'bed')], order="id asc", limit=1).id or None
                if int(object['sync_id']) in sync_ids:
                    object['id'] = sync_ids[object['sync_id']]
                else:
                    object['id'] = 'DEFAULT'
                object['warehouse_id'] = 1 #masih hardcode
                object['create_uid'] = 1
                object['write_uid'] = 1 
                object['create_date'] = now
                object['write_date'] = now
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
                    if isinstance(object[field], str):
                        string = object[field]
                        value += "'" + string.replace("'", "''") + "'"
                        continue
                    value += sync.json(object[field])
                value += ')'
                values += value
            excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
            columns = sync.remove_unicode(str(fields)).replace("'", "")
            columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
            print (values.encode('utf-8'))
            if values:   
                query = "INSERT into sale_order %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
                print (query.encode('utf8'))
                self.env.cr.execute(query)
                # self.env.cr.execute("""UPDATE sale_order as s set date_order = s.date_order - (interval '14 hour'), updated_date = True where s.updated_date is null""")



        # syncing sale.order.bill
        open('/opt/odoo16/logs/log_sale_bulk_syncing.log', 'a+').write(str('\nStart update sale.order.bill'))
        query = """
            SELECT DISTINCT
                tglproses,
                sync_id,
                convert(varchar(19), dateadd(hour, -0, confirmation_date), 121) confirmation_date,
                convert(varchar(19), dateadd(hour, -0, cancel_date), 121) cancel_date,
                convert(varchar(10), dateadd(hour, -0, confirmation_date), 121) bill_date,
                convert(varchar(10), dateadd(hour, -0, discharge_date), 121) discharge_date,
                billno,
                partner_id,
                partner_name,
                patient_name,
                admission_id,
                admission_no,
                patient_type,
                tariff_id,
                payer_id,
                payer_code,
                payer_name,
                payer_type,
                primary_doc_id,
                referral_doc_id,
                referral_id,
                referral_number,
                secondary_diagnosis_code,
                secondary_diagnosis_name,
                primary_diagnosis_code,
                primary_diagnosis_name,
                repeat_diagnosis_code,
                repeat_diagnosis_name,
                bed_type_id,
                alloted_bed_type_id,
                eligible_bed_type_id,
                note,
                total_amount,
                payer_amount,
                payer_canceled,
                payer_deduction,
                payer_rounding,
                personal_amount,
                personal_canceled,
                personal_rounding,
                penjualanresep,
                state status_bill
            FROM dbo.VRP_OdooSaleOrderBill a 
            WHERE a.billno in {billing_ids}
        """ . format(billing_ids=billing_ids)
        open('/opt/odoo16/logs/log_sale_bulk_syncing.log', 'a+').write('\n'+str(query))



        values = ''
        data = sync.get_data(sync.servers.get(sync_type), query)
        
        if data:

            # stored existing sale.order.bill
            sync_ids = [row['sync_id'] for row in data]
            sync_ids.append(0)

            self.env.cr.execute("""
                SELECT cast(sync_id as integer) sync_id, id 
                FROM sale_order_bill 
                WHERE sync_type = '{sync_type}' 
                    AND sync_id in {sync_ids}
                """.format(
                    sync_type=sync_type,
                    sync_ids=tuple(sync_ids)
                ))
            sync_ids = dict(self.env.cr.fetchall())

            fields_without_id = tuple(key for key in self.env['sale.order.bill']._fields if key != 'id' and 'property' not in key and 'ids' not in key and self.env['sale.order.bill']._fields[key].required == True and self.env['sale.order.bill']._fields[key].store == True)
            columns = tuple(key for key in data[0].keys() if key in self.env['sale.order.bill']._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id', 'state') if data else ()
            fields_without_id += columns
            columns += tuple(key for key in data[0].keys() if key in self.env['sale.order.bill']._fields and key not in columns) if data else ()
            fields = fields_without_id + ('id', )
            if columns:
                columns += ('id', )
            default_values = {}
            for field in fields:
                if field in columns:
                    continue
                default = self.env['sale.order.bill']._fields[field].default
                if callable(default):
                    default = default(self)
                if isinstance(default, models.Model):
                    default = default.id
                default_values[field] = default
            now = tools.datetime.now().strftime('%Y%m%d %H:%M:S')
            default_values['company_id'] = self.env.company.id

            new_sync_ids = []
            for object in data:
                new_sync_ids += [object['sync_id']]
                for value in default_values:
                    if value in object:
                        continue
                    object[value] = default_values[value]
                partner_id = object['partner_id']
                
                if object['payer_type'] == 'PRIVATE':
                    object['payer_id'] = 5817
                else:
                    object['payer_id'] = self.env['res.partner'].search([('sync_id', '>', 0), ('sync_id', '=', object['payer_id']),('sync_type', '=', sync_type), ('insurance', '=', True)],limit=1).id or None

                object['partner_id'] = self.env['res.partner'].search([('sync_id', '>', 0), ('sync_id', '=', object['partner_id']), ('sync_type', '=', sync_type), ('patient', '=', True)], limit=1)

                
                if object['admission_id']: 
                    object['admission_id'] = self.env['sale.order'].search([('sync_id', '=', object['admission_id']), ('sync_type', '=', sync_type)], limit=1).id or None
                if object['primary_doc_id']:
                    object['primary_doc_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_internal')], order="id asc", limit=1).id or self.env['account.analytic.account'].search([('sync_id', '=', object['primary_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1).id or self.env['account.analytic.account'].search([('name', '=', 'TIDAK ADA DOKTER'), ('sync_type', '=', sync_type)], limit=1).id or None 
                if object['referral_doc_id']:
                    object['referral_doc_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['referral_doc_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'doctor_external')], order="id asc", limit=1).id or None
                if object['referral_id']:
                    object['referral_id'] = self.env['referral.transaction'].search([('sync_id', '=', object['referral_id']), ('sync_type', '=', sync_type)], limit=1).id or None            
                if object['tariff_id']:
                    object['tariff_id'] = self.env['hospital.tariff'].search([('sync_id', '=', object['tariff_id']), ('sync_type', '=', sync_type)], limit=1).id or None            
                if object['bed_type_id']:
                    object['bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['bed_type_id']), ('sync_type', '=', sync_type)], limit=1).id or None            
                if object['alloted_bed_type_id']:
                    object['alloted_bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['eligible_bed_type_id']), ('sync_type', '=', sync_type)], limit=1).id or None
                if object['eligible_bed_type_id']: 
                    object['eligible_bed_type_id'] = self.env['hospital.bed.type'].search([('sync_id', '=', object['alloted_bed_type_id']), ('sync_type', '=', sync_type)], limit=1).id or None
                            
                if not object['partner_id']:
                    open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + "pasien res.partner with sync_id %s and sync_type %s doesn't exist" % (partner_id, sync_type))
                    # object['backup_partner_id'] = object['partner_id']
                    object['partner_id'] = self.env['res.partner'].search([('sync_id', '=', 99881177), ('sync_type', '=', sync_type), ('patient', '=', True)], limit=1)
                    # return
                object['partner_id'] = object['partner_id'].id
                if int(object['sync_id']) in sync_ids:
                    object['id'] = sync_ids[object['sync_id']]
                else:
                    object['id'] = 'DEFAULT'
                
                object['create_uid'] = self.env.user.id
                object['write_uid'] = self.env.user.id
                object['create_date'] = now
                object['write_date'] = now
                object['sync_date'] = now
                object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
                object['state'] = self.env['sale.order.bill'].sudo().search([('sync_type', '=', sync_type),('sync_id','=', object['sync_id'])], limit=1).state or object['status_bill']
            
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
                    if isinstance(object[field], str):
                        string = object[field]
                        value += "'" + string.replace("'", "''") + "'"
                        continue
                    value += sync.json(object[field])
                value += ')'
                values += value
            excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
            columns = sync.remove_unicode(str(fields)).replace("'", "")
            columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
            print (values.encode('utf-8'))
            
            if values:
                query = "INSERT into sale_order_bill %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
                open('/opt/odoo16/logs/log_sale_bulk_syncing.log', 'a+').write('\n'+str(query))
                self.env.cr.execute(query)


                query = """
                    INSERT INTO sale_order_bill_history(
                        create_uid, create_date, write_uid, write_date,
                        sync_type, datetime, billing_id, "state",
                        payer_deduction, payer_canceled, payer_amount,
                        payer_credit, payer_adjustment, payer_receipt, payer_discount,
                        payer_balance, remark  
                    )

                    SELECT 
                        a.write_uid create_uid, now() create_date, a.write_uid, now() write_date,
                        a.sync_type, a.write_date, a.id billing_id, a.state,
                        a.payer_deduction, a.payer_canceled, a.payer_amount,
                        a.payer_credit, a.payer_adjustment, a.payer_receipt, 
                        a.payer_discount, a.payer_balance, 
                        (case 
                            when a.state='done' then 'UNBILLED' 
                            when a.state='cancel' then 'CANCEL BILLING'
                            else 'BILL UPDATE'
                        end) remark      
                    FROM sale_order_bill a 
                    WHERE a.sync_type = '{sync_type}'  
                        AND a.state <> 'invoice'
                        AND NOT EXISTS(
                            SELECT 1 FROM sale_order_bill_history t 
                            WHERE t.billing_id = a.id 
                                AND t.datetime = a.write_date
                                AND t.state = a.state
                        )
                        AND a.billno in {billing_ids}
                """.format(sync_type=sync_type, billing_ids=billing_ids)
                self.env.cr.execute(query)

        open('/opt/odoo16/logs/log_sale_bulk_syncing.log', 'a+').write('\n'+str(query))
        open('/opt/odoo16/logs/log_sale_bulk_syncing.log', 'a+').write(str('\nDone'))
        print("Successfully to update sale.order")



# 2021.09.08 - Temp table revenue daily top 15 doctors
class SaleOrderLineDoctor(models.Model):
    _name = 'sale.order.line.doctor'
    _rec_name = 'account_analytic_id'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account', readonly=True, index=True)
    parent_analytic_id = fields.Many2one('account.analytic.account', string='Specialization (Analytic)', readonly=True, store=True, index=True)
    company_id = fields.Many2one('res.company', string="Company", readonly=True, index=True)
    date = fields.Date(string="Date", readonly=True, index=True)
    total = fields.Float(string="Total Revenue", readonly=True)



# 2021.09.08 - Temp table generate daily revenue top 15 by specialization
class SaleOrderLineSpesialisasi(models.Model):
    _name = 'sale.order.line.spesialisasi'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    parent_analytic_id = fields.Many2one('account.analytic.account', string='Specialization (Analytic)', readonly=True, store=True, index=True)
    company_id = fields.Many2one('res.company', string="Company", readonly=True, index=True)
    date = fields.Date(string="Date", readonly=True, index=True)
    total = fields.Float(string="Total Revenue", readonly=True)



# 2021.10.27 - billing bulk merging
class SaleBulkMergingLine(models.TransientModel):
    _name = 'sale.bulk.merging.line'

    merge_id = fields.Many2one('sale.bulk.merging.wizard', string="Merging")
    sequence = fields.Integer(string="Sequence", default=1)
    cob_payer_id = fields.Many2one('res.partner', string="COB Payer", index=True)
    cob_amount = fields.Float(string="COB Amount")



# 2021.09.23 - billing bulk syncing line
class SaleBulkSyncingLine(models.TransientModel):
    _name = 'sale.bulk.syncing.line'

    name = fields.Char(string="Bill No.", readonly=False, index=True)
    syncing_id = fields.Many2one('sale.bulk.syncing.wizard', string="Syncing")



class SaleOrderLabWizard(models.TransientModel):
    _name = 'sale.order.lab.wizard'

    @api.model
    def _get_user_id(self):
        return self.env.user.id

    @api.model
    def _get_default_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', string="Company", required=False, default=_get_default_company)
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)
    sale_wizard_line = fields.One2many('sale.order.lab.wizard.line','sale_lab_wizard_id', string="Filter Line")
    user_id = fields.Many2one('res.users', string="User ID", default=_get_user_id)
    bulk_id = fields.Many2one('sale.order.bulk.filter', string="Saved Bulk Filter")

    @api.model
    def create(self,vals):
        if vals.get('bulk_id'):
            vals['sale_wizard_line'] = ""
        res = super(SaleOrderLabWizard, self).create(vals)
        return res


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(SaleOrderLabWizard,self).get_view(view_id=view_id,view_type=view_type, **options)
        res['arch'] = """
            <form string="Billing Analysis" delete="false">
                <sheet>
                    <h1>Billing Analysis for Laboratory</h1>
                    <group>
                         <group>
                            <field name="start_date" />
                            <field name="end_date" />
                            <field name="bulk_id" domain="[('user_id', '=', user_id)]" invisible="1"/>
                        </group>
                        <group>
                            <field name="company_id" readonly="1" force_save="1" />
                            <field name="user_id" readonly="1" force_save="1"/>
                        </group>

                        <!--group>
                            <field name="sale_wizard_line" invisible="1" mode="kanban" list_options='{"limit":10}'/>
                        </group-->
                    </group>
                    <button name="show_report" string="Show" type="object" class="oe_highlight"/>
                </sheet>
            </form>
        """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res



    @api.onchange('bulk_id')
    def onchange_filter(self):
        for record in self:
            if record.bulk_id:
                record.sale_wizard_line = record.bulk_id.filter_ids.ids

    # @api.multi
    def query_report(self, data_ids=False):
        for record in self:
            open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Start')
            domain = ""

            line_all = []
            query_field = ""
            if not record.bulk_id:
                for line in record.sale_wizard_line:
                    line_dict = line.read(load=False)[0]
                    line_all.append(line_dict)

                open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Append all line')

                line_sorted = sorted(line_all, key=itemgetter('field_name'))
                open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Sort Data')
                query_field_all = """ """
                for field, value in itertools.groupby(line_sorted, key=itemgetter('field_name')):
                    val = []
                    char = False
                    date = False
                    bool = False
                    for v in value:
                        if v['type_field'] == 'many2one':
                            val.append(v[field])
                        if v['type_field'] in ['char', 'text']:
                            val.append(v['value_text'])
                            char = True
                        if v['type_field'] == ['boolean']:
                            val.append(v['bool_filter'])
                            bool = True
                        if v['type_field'] in ['date', 'datetime']:
                            val.append(v['date_filter'])
                            date = True
                        open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Processing data')

                    open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Processing domain')

                    if len(val) > 1 and date == False and bool == False:
                        query_field = "('{field}', 'in', {value}),  ".format(field=field, value=val)
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and date == False and bool == False and char == False:
                        query_field = "('{field}', '=', {value}),  ".format(field=field, value=val[0])
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and char == True:
                        query_field = "('{field}', 'like', '{value}'),  ".format(field=field, value=(val[0]))
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and bool == True:
                        query_field = "('{field}', '=', {value}), ".format(field=field, value=(val[0]))
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field

                    domain = "{query_field_all}".format(query_field_all=query_field_all)

                    open('/opt/odoo16/logs/belajar.log',
                         'a+').write('\n' + str(domain) + '\n' + 'domain query report')

            if record.bulk_id:
                for line in record.bulk_id.filter_ids:
                    line_dict = line.read(load=False)[0]
                    line_all.append(line_dict)
                open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Append all line')

                line_sorted = sorted(line_all, key=itemgetter('field_name'))
                open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Sort Data')
                query_field_all = """ """
                for field, value in itertools.groupby(line_sorted, key=itemgetter('field_name')):
                    val = []
                    char = False
                    date = False
                    bool = False
                    for v in value:
                        if v['type_field'] == 'many2one':
                            val.append(v[field])
                        if v['type_field'] in ['char', 'text']:
                            val.append(v['value_text'])
                            char = True
                        if v['type_field'] == ['boolean']:
                            val.append(v['bool_filter'])
                            bool = True
                        if v['type_field'] in ['date', 'datetime']:
                            val.append(v['date_filter'])
                            date = True
                        open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Processing data')

                    open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Processing domain')

                    if len(val) > 1 and date == False and bool == False:
                        query_field = "('{field}', 'in', {value}),  ".format(field=field, value=val)
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and date == False and bool == False and char == False:
                        query_field = "('{field}', '=', {value}),  ".format(field=field, value=val[0])
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and char == True:
                        query_field = "('{field}', 'like', '{value}'),  ".format(field=field, value=(val[0]))
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and bool == True:
                        query_field = "('{field}', '=', {value}), ".format(field=field, value=(val[0]))
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field

                    domain = "{query_field_all}".format(query_field_all=query_field_all)

                    open('/opt/odoo16/logs/belajar.log','a+').write('\n' + str(domain) + '\n' + 'domain bulk')

            return domain

    # @api.multi
    def show_report(self):
        open('/opt/odoo16/logs/test_sale_wizard.log','a+').write('\n' + 'Start')
        query = self.query_report()
        action = {}
        action['target'] = 'current'
        # action['domain'] = "[('user_id', '=', %s)]" % (self.env.user.id)
        if query:
            if self.company_id:
                action['domain'] = "[{query}('tglproses', '>=', '{start_date}'), ('tglproses', '<=', '{end_date}'), ('company_id', '=', {company_id}), ('special_group2', '=', 'LABORATORY')]".format(query=query, start_date=self.start_date, end_date=self.end_date, company_id=self.company_id.id)
            else:
                action['domain'] = "[{query}('tglproses', '>=', '{start_date}'), ('tglproses', '<=', '{end_date}'), ('special_group2', '=', 'LABORATORY')]".format(query=query, start_date=self.start_date, end_date=self.end_date, company_id=self.company_id.id)
        else:
            if self.company_id:
                action['domain'] = "[('tglproses', '>=', '%s'), ('tglproses', '<=', '%s'), ('company_id', '=', %s), ('special_group2', '=', 'LABORATORY')]" % (self.start_date, self.end_date, self.company_id.id)
            else:
                action['domain'] = "[('tglproses', '>=', '%s'), ('tglproses', '<=', '%s'), ('special_group2', '=', 'LABORATORY')]" % (self.start_date, self.end_date)
        # action['domain'] = "[('tglproses', '>=', '2019-01-01'), ('tglproses', '<=', '2019-02-01')]"
        # action['domain'] = "[()]"
        open('/opt/odoo16/logs/belajar.log','a+').write('\n' + str(action['domain']) + '\n' + 'domain show report')
        action['type'] = 'ir.actions.act_window'
        action['view_mode'] = 'tree,form,pivot'
        action['view_type'] = 'form'
        action['res_model'] = 'sale.order.line'
        action['name'] = 'Billing Analysis Report'
        # view_billing_analysis_real_pivot
        # action['views'] = [(self.sudo().env.ref('mayapada.view_billing_analysis_pivot').id, 'pivot'), (False, 'form'), (False, 'tree')]
        action['views'] = [(self.sudo().env.ref('mayapada.view_billing_analysis_real_pivot').id, 'pivot'), (False, 'tree'), (False, 'form')]
        return action



class SaleOrderLabWizardLine(models.TransientModel):
    _name = 'sale.order.lab.wizard.line'

    sale_lab_wizard_id = fields.Many2one('sale.order.lab.wizard', string="wizard")
    filter_column_id = fields.Many2one('ir.model.fields', string="Field Filter", domain="[('model_id.model', '=', 'sale.order.line'), ('ttype', 'not in', ['many2many', 'one2many', 'date', 'datetime'])]")
    field_name = fields.Char(string="Field Name", compute='_compute_field_name', readonly=True, store=True)
    type_field = fields.Char(string="Type Field", compute='_compute_field_name', readonly=True, store=True)
    product_id = fields.Many2one('product.product', string="Product", domain="[('sale_ok', '=', True)]")
    account_analytic_id = fields.Many2one('account.analytic.account', string="Analytic Doctor", domain="[('sync_wipro_type', '=', 'doctor_internal')]")
    location_id = fields.Many2one('stock.location', string="Location", domain="[('sync_id', '>', 0)]")
    order_id = fields.Many2one('sale.order', string="Admission")
    parent_analytic_id = fields.Many2one('account.analytic.account', string="Analytic Specialization", domain="[('sync_wipro_type', '=', 'specialization')]")
    parent_analytic_primary_id = fields.Many2one('account.analytic.account', string="Primary Specialization", domain="[('sync_wipro_type', '=', 'specialization')]")
    partner_id = fields.Many2one('res.partner', string="Patient", domain="[('patient', '=', True)]")
    payer = fields.Many2one('res.partner', string="Payer", domain="[('customer_wipro', '=', True)]")
    perform_doc_id = fields.Many2one('account.analytic.account', string="Perform Doctor", domain="[('sync_wipro_type', '=', 'doctor_internal')]")
    prescribe_doc_id = fields.Many2one('account.analytic.account', string="Prescribe Doctor", domain="[('sync_wipro_type', '=', 'doctor_internal')]")
    primary_doc_id = fields.Many2one('account.analytic.account', string="Primary Doctor", domain="[('sync_wipro_type', '=', 'doctor_internal')]")
    product_uom = fields.Many2one('uom.uom', string="UOM")
    service_categ_id = fields.Many2one('product.category', string="Service Category", domain="[('sync_id', '>', 0)]")
    bool_filter = fields.Boolean('True or False')
    value_text = fields.Char(string="Char Filter")
    date_filter = fields.Date(string="Date Filter")
    field_import = fields.Char(string="Field Import")
    display_value = fields.Char(string="Display Value", compute='_compute_display', readonly=True, store=True)
    display_field = fields.Char(string="Display Field", compute='_compute_display', readonly=True, store=True)
    bulk_id = fields.Many2one('sale.order.bulk.filter', string="Bulk Filter")

    @api.model
    def create(self, vals):
        open('/opt/odoo16/logs/bulk.log', 'a+').write('\n' + str('START').encode('utf-8'))
        if vals.get('field_import'):
            field = self.env['ir.model.fields'].search([('field_description', '=', vals['field_import']), ('model_id.model', '=', 'sale.order.line')], order="id asc", limit=1)
            open('/opt/odoo16/logs/bulk.log', 'a+').write('\n' + str(field).encode('utf-8'))
            if not field:
                raise exceptions.UserError('Field tidak ditemukan!!!')
            else:
                vals['filter_column_id'] = field.id
        res = super(SaleOrderLabWizardLine, self).create(vals)
        return res

    @api.depends('filter_column_id', 'product_id', 'account_analytic_id',
                 'location_id', 'order_id', 'parent_analytic_id',
                 'parent_analytic_primary_id', 'partner_id', 'payer',
                 'perform_doc_id', 'prescribe_doc_id', 'primary_doc_id',
                 'product_uom', 'service_categ_id')
    def _compute_display(self):
        for record in self:
            record.display_value = " "
            if record.filter_column_id:
                record.display_field = record.filter_column_id.field_description
            if record.product_id:
                record.display_value = record.product_id.display_name
            if record.account_analytic_id:
                record.display_value = record.account_analytic_id.display_name
            if record.location_id:
                record.display_value = record.location_id.display_name
            if record.order_id:
                record.display_value = record.order_id.display_name
            if record.parent_analytic_id:
                record.display_value = record.parent_analytic_id.display_name
            if record.parent_analytic_primary_id:
                record.display_value = record.parent_analytic_primary_id.display_name
            if record.payer:
                record.display_value = record.payer.display_name
            if record.perform_doc_id:
                record.display_value = record.perform_doc_id.display_name
            if record.prescribe_doc_id:
                record.display_value = record.prescribe_doc_id.display_name
            if record.primary_doc_id:
                record.display_value = record.primary_doc_id.display_name
            if record.product_uom:
                record.display_value = record.product_uom.display_name
            if record.service_categ_id:
                record.display_value = record.service_categ_id.display_name
            if record.partner_id:
                record.display_value = record.partner_id.display_name

    @api.depends('filter_column_id')
    def _compute_field_name(self):
        for record in self:
            if record.filter_column_id:
                record.field_name = record.filter_column_id.name
                record.type_field = record.filter_column_id.ttype

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(SaleOrderLabWizardLine, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        res['arch'] = """
                <form string="Filter Line">
                    <group>
                        <field name="filter_column_id"/>
                        <field name="field_name" invisible="1"/>
                        <field name="type_field" invisible="1"/>
                        <field name="display_value" invisible="1"/>
                        <field name="display_field" invisible="1"/>
                        <field name="account_analytic_id" attrs="{'invisible': [('field_name', '!=', 'account_analytic_id')]}"/>
                        <field name="location_id" attrs="{'invisible': [('field_name', '!=', 'location_id')]}"/>
                        <field name="order_id" attrs="{'invisible': [('field_name', '!=', 'order_id')]}"/>
                        <field name="parent_analytic_id" attrs="{'invisible': [('field_name', '!=', 'parent_analytic_id')]}"/>
                        <field name="parent_analytic_primary_id" attrs="{'invisible': [('field_name', '!=', 'parent_analytic_primary_id')]}"/>
                        <field name="partner_id" attrs="{'invisible': [('field_name', '!=', 'partner_id')]}"/>
                        <field name="payer" attrs="{'invisible': [('field_name', '!=', 'payer')]}"/>
                        <field name="perform_doc_id" attrs="{'invisible': [('field_name', '!=', 'perform_doc_id')]}"/>
                        <field name="prescribe_doc_id" attrs="{'invisible': [('field_name', '!=', 'prescribe_doc_id')]}"/>
                        <field name="primary_doc_id" attrs="{'invisible': [('field_name', '!=', 'primary_doc_id')]}"/>
                        <field name="product_id" attrs="{'invisible': [('field_name', '!=', 'product_id')]}"/>
                        <field name="product_uom" attrs="{'invisible': [('field_name', '!=', 'product_uom')]}"/>
                        <field name="service_categ_id" attrs="{'invisible': [('field_name', '!=', 'service_categ_id')]}"/>
                        <field name="value_text" attrs="{'invisible': [('type_field', 'not in', ['char', 'text'])]}"/>
                        <field name="bool_filter" attrs="{'invisible': [('type_field', '!=', 'boolean')]}"/>
                        <field name="date_filter" attrs="{'invisible': [('type_field', 'not in', ['date', 'datetime'])]}"/>
                    </group>
                </form>
        """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(self._name, doc, view_id)
        return res






class SaleOrderAkasiaWizard(models.TransientModel):
    _name = 'sale.order.akasia.wizard'

    @api.model
    def _get_user_id(self):
        return self.env.user.id

    @api.model
    def _get_default_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', string="Company", required=False, default=_get_default_company)
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)
    sale_wizard_line = fields.One2many('sale.order.akasia.wizard.line','sale_akasia_wizard_id', string="Filter Line")
    user_id = fields.Many2one('res.users', string="User ID", default=_get_user_id)
    bulk_id = fields.Many2one('sale.order.bulk.filter', string="Saved Bulk Filter")


    @api.model
    def create(self,vals):
        if vals.get('bulk_id'):
            vals['sale_wizard_line'] = ""
        res = super(SaleOrderAkasiaWizard, self).create(vals)
        return res


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(SaleOrderAkasiaWizard,self).get_view(view_id=view_id,view_type=view_type, **options)
        res['arch'] = """
            <form string="Billing Analysis" delete="false">
                <sheet>
                    <h1>Billing Analysis for Akasia 365</h1>
                    <group>
                         <group>
                            <field name="start_date" />
                            <field name="end_date" />
                            <field name="bulk_id" domain="[('user_id', '=', user_id)]" invisible="1"/>
                        </group>
                        <group>
                            <field name="company_id" readonly="1" force_save="1" />
                            <field name="user_id" readonly="1" force_save="1"/>
                        </group>

                        <!--group>
                            <field name="sale_wizard_line" invisible="1" mode="kanban" list_options='{"limit":10}'/>
                        </group-->
                    </group>
                    <button name="show_report" string="Show" type="object" class="oe_highlight"/>
                </sheet>
            </form>
        """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res





    

    @api.onchange('bulk_id')
    def onchange_filter(self):
        for record in self:
            if record.bulk_id:
                record.sale_wizard_line = record.bulk_id.filter_ids.ids

    # @api.multi
    def query_report(self, data_ids=False):
        for record in self:
            open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Start')
            domain = ""

            line_all = []
            query_field = ""
            if not record.bulk_id:
                for line in record.sale_wizard_line:
                    line_dict = line.read(load=False)[0]
                    line_all.append(line_dict)

                open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Append all line')

                line_sorted = sorted(line_all, key=itemgetter('field_name'))
                open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Sort Data')
                query_field_all = """ """
                for field, value in itertools.groupby(line_sorted, key=itemgetter('field_name')):
                    val = []
                    char = False
                    date = False
                    bool = False
                    for v in value:
                        if v['type_field'] == 'many2one':
                            val.append(v[field])
                        if v['type_field'] in ['char', 'text']:
                            val.append(v['value_text'])
                            char = True
                        if v['type_field'] == ['boolean']:
                            val.append(v['bool_filter'])
                            bool = True
                        if v['type_field'] in ['date', 'datetime']:
                            val.append(v['date_filter'])
                            date = True
                        open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Processing data')

                    open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Processing domain')

                    if len(val) > 1 and date == False and bool == False:
                        query_field = "('{field}', 'in', {value}),  ".format(field=field, value=val)
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and date == False and bool == False and char == False:
                        query_field = "('{field}', '=', {value}),  ".format(field=field, value=val[0])
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and char == True:
                        query_field = "('{field}', 'like', '{value}'),  ".format(field=field, value=(val[0]))
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and bool == True:
                        query_field = "('{field}', '=', {value}), ".format(field=field, value=(val[0]))
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field

                    domain = "{query_field_all}".format(query_field_all=query_field_all)

                    open('/opt/odoo16/logs/belajar.log',
                         'a+').write('\n' + str(domain) + '\n' + 'domain query report')

            if record.bulk_id:
                for line in record.bulk_id.filter_ids:
                    line_dict = line.read(load=False)[0]
                    line_all.append(line_dict)
                open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Append all line')

                line_sorted = sorted(line_all, key=itemgetter('field_name'))
                open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Sort Data')
                query_field_all = """ """
                for field, value in itertools.groupby(line_sorted, key=itemgetter('field_name')):
                    val = []
                    char = False
                    date = False
                    bool = False
                    for v in value:
                        if v['type_field'] == 'many2one':
                            val.append(v[field])
                        if v['type_field'] in ['char', 'text']:
                            val.append(v['value_text'])
                            char = True
                        if v['type_field'] == ['boolean']:
                            val.append(v['bool_filter'])
                            bool = True
                        if v['type_field'] in ['date', 'datetime']:
                            val.append(v['date_filter'])
                            date = True
                        open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Processing data')

                    open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Processing domain')

                    if len(val) > 1 and date == False and bool == False:
                        query_field = "('{field}', 'in', {value}),  ".format(field=field, value=val)
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and date == False and bool == False and char == False:
                        query_field = "('{field}', '=', {value}),  ".format(field=field, value=val[0])
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and char == True:
                        query_field = "('{field}', 'like', '{value}'),  ".format(field=field, value=(val[0]))
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field
                    if len(val) == 1 and bool == True:
                        query_field = "('{field}', '=', {value}), ".format(field=field, value=(val[0]))
                        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                        query_field_all = query_field_all + query_field

                    domain = "{query_field_all}".format(query_field_all=query_field_all)

                    open('/opt/odoo16/logs/belajar.log','a+').write('\n' + str(domain) + '\n' + 'domain bulk')

            return domain

    # @api.multi
    def show_report(self):
        open('/opt/odoo16/logs/test_sale_wizard.log','a+').write('\n' + 'Start')
        query = self.query_report()
        action = {}
        action['target'] = 'current'
        # action['domain'] = "[('user_id', '=', %s)]" % (self.env.user.id)
        if query:
            if self.company_id:
                action['domain'] = "[{query}('tglproses', '>=', '{start_date}'), ('tglproses', '<=', '{end_date}'), ('company_id', '=', {company_id}), ('is_akasia', '=', True)]".format(query=query, start_date=self.start_date, end_date=self.end_date, company_id=self.company_id.id)
            else:
                action['domain'] = "[{query}('tglproses', '>=', '{start_date}'), ('tglproses', '<=', '{end_date}'), ('is_akasia', '=', True)]".format(query=query, start_date=self.start_date, end_date=self.end_date, company_id=self.company_id.id)
        else:
            if self.company_id:
                action['domain'] = "[('tglproses', '>=', '%s'), ('tglproses', '<=', '%s'), ('company_id', '=', %s), ('is_akasia', '=', True)]" % (self.start_date, self.end_date, self.company_id.id)
            else:
                action['domain'] = "[('tglproses', '>=', '%s'), ('tglproses', '<=', '%s'), ('is_akasia', '=', True)]" % (self.start_date, self.end_date)
        # action['domain'] = "[('tglproses', '>=', '2019-01-01'), ('tglproses', '<=', '2019-02-01')]"
        # action['domain'] = "[()]"
        open('/opt/odoo16/logs/belajar.log','a+').write('\n' + str(action['domain']) + '\n' + 'domain show report')
        action['type'] = 'ir.actions.act_window'
        action['view_mode'] = 'tree,form,pivot'
        action['view_type'] = 'form'
        action['res_model'] = 'sale.order.line'
        action['name'] = 'Billing Analysis Report'
        # view_billing_analysis_real_pivot
        # action['views'] = [(self.sudo().env.ref('mayapada.view_billing_analysis_pivot').id, 'pivot'), (False, 'form'), (False, 'tree')]
        action['views'] = [(self.sudo().env.ref('mayapada.view_billing_analysis_real_pivot').id, 'pivot'), (False, 'tree'), (False, 'form')]
        return action


# 2024.02.15 - BA Wizard for Eye Centre
class SaleOrderEyeCentreWizard(models.TransientModel):
    _name = 'sale.order.mec.wizard'

    @api.model
    def _get_user_id(self):
        return self.env.user.id

    @api.model
    def _get_default_company(self):
        return self.env.user.company_id.id
    
    company_id = fields.Many2one('res.company', string="Company", required=True, domain=[('sync_type','=','1')])
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)
    user_id = fields.Many2one('res.users', string="User ID", default=_get_user_id)
    

    @api.model
    def create(self,vals):
        res = super(SaleOrderEyeCentreWizard, self).create(vals)
        return res
    

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(SaleOrderEyeCentreWizard,self).get_view(view_id=view_id,view_type=view_type, **options)
        res['arch'] = """
            <form string="Billing Analysis for Eye Centre" delete="false">
                <sheet>
                    <h1>Billing Analysis for Eye Centre</h1>
                    <group>
                         <group>
                            <field name="start_date" />
                            <field name="end_date" />
                        </group>
                        <group>
                            <field name="company_id" readonly="0" force_save="1" />
                            <field name="user_id" readonly="1" force_save="1"/>
                        </group>
                    </group>
                    <button name="show_report" string="Show" type="object" class="oe_highlight"/>
                </sheet>
            </form>
        """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # @api.multi
    def query_report(self, data_ids=False):
        for record in self:
            open('/opt/odoo16/logs/log_revenue_eye_centre.log','a+').write('\n' + 'Start')
            domain = ""

            line_all = []
            query_field = ""
            
            # for line in record.sale_wizard_line:
            #     line_dict = line.read(load=False)[0]
            #     line_all.append(line_dict)
            # open('/opt/odoo16/logs/log_revenue_eye_centre.log','a+').write('\n' + 'Append all line')

            line_sorted = sorted(line_all, key=itemgetter('field_name'))
            open('/opt/odoo16/logs/log_revenue_eye_centre.log','a+').write('\n' + 'Sort Data')
            query_field_all = """ """

            for field, value in itertools.groupby(line_sorted, key=itemgetter('field_name')):
                val = []
                char = False
                date = False
                bool = False

                for v in value:
                    if v['type_field'] == 'many2one':
                        val.append(v[field])

                    if v['type_field'] in ['char', 'text']:
                        val.append(v['value_text'])
                        char = True

                    if v['type_field'] == ['boolean']:
                        val.append(v['bool_filter'])
                        bool = True

                    if v['type_field'] in ['date', 'datetime']:
                        val.append(v['date_filter'])
                        date = True
                
                open('/opt/odoo16/logs/log_revenue_eye_centre.log','a+').write('\n' + 'Processing data')
                open('/opt/odoo16/logs/log_revenue_eye_centre.log','a+').write('\n' + 'Processing domain')

                if len(val) > 1 and date == False and bool == False:
                    query_field = "('{field}', 'in', {value}),  ".format(field=field, value=val)
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                    query_field_all = query_field_all + query_field
                
                if len(val) == 1 and date == False and bool == False and char == False:
                    query_field = "('{field}', '=', {value}),  ".format(field=field, value=val[0])
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                    query_field_all = query_field_all + query_field
                
                if len(val) == 1 and char == True:
                    query_field = "('{field}', 'like', '{value}'),  ".format(field=field, value=(val[0]))
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                    query_field_all = query_field_all + query_field
                
                if len(val) == 1 and bool == True:
                    query_field = "('{field}', '=', {value}), ".format(field=field, value=(val[0]))
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + str(query_field) + '\n')
                    query_field_all = query_field_all + query_field

                domain = "{query_field_all}".format(query_field_all=query_field_all)
                open('/opt/odoo16/logs/log_revenue_eye_centre.log', 'a+').write('\n' + str(domain) + '\n' + 'domain query report')    
            return domain


    # @api.multi
    def show_report(self):
        open('/opt/odoo16/logs/log_revenue_eye_centre.log','a+').write('\n' + 'Start')
        query = self.query_report()
        action = {}
        action['target'] = 'current'
        # action['domain'] = "[('user_id', '=', %s)]" % (self.env.user.id)
        if query:
            if self.company_id:
                action['domain'] = "[{query}('tglproses', '>=', '{start_date}'), ('tglproses', '<=', '{end_date}'), ('company_id', '=', {company_id}), ('is_mec', '=', True)]".format(query=query, start_date=self.start_date, end_date=self.end_date, company_id=self.company_id.id)
            else:
                action['domain'] = "[{query}('tglproses', '>=', '{start_date}'), ('tglproses', '<=', '{end_date}'), ('is_mec', '=', True)]".format(query=query, start_date=self.start_date, end_date=self.end_date, company_id=self.company_id.id)
        else:
            if self.company_id:
                action['domain'] = "[('tglproses', '>=', '%s'), ('tglproses', '<=', '%s'), ('company_id', '=', %s), ('is_mec', '=', True)]" % (self.start_date, self.end_date, self.company_id.id)
            else:
                action['domain'] = "[('tglproses', '>=', '%s'), ('tglproses', '<=', '%s'), ('is_mec', '=', True)]" % (self.start_date, self.end_date)
        
        open('/opt/odoo16/logs/log_revenue_eye_centre.log','a+').write('\n' + str(action['domain']) + '\n' + 'domain show report')
        action['type'] = 'ir.actions.act_window'
        action['view_mode'] = 'tree,form,pivot'
        action['view_type'] = 'form'
        action['res_model'] = 'sale.order.line'
        action['name'] = 'Billing Analysis Report'
        
        action['views'] = [(self.sudo().env.ref('mayapada.view_billing_analysis_real_pivot').id, 'pivot'), (False, 'tree'), (False, 'form')]
        return action



class SaleOrderAkasiaWizardLine(models.TransientModel):
    _name = 'sale.order.akasia.wizard.line'

    sale_akasia_wizard_id = fields.Many2one('sale.order.akasia.wizard', string="wizard")
    filter_column_id = fields.Many2one('ir.model.fields', string="Field Filter", domain="[('model_id.model', '=', 'sale.order.line'), ('ttype', 'not in', ['many2many', 'one2many', 'date', 'datetime'])]")
    field_name = fields.Char(string="Field Name", compute='_compute_field_name', readonly=True, store=True)
    type_field = fields.Char(string="Type Field", compute='_compute_field_name', readonly=True, store=True)
    product_id = fields.Many2one('product.product', string="Product", domain="[('sale_ok', '=', True)]")
    account_analytic_id = fields.Many2one('account.analytic.account', string="Analytic Doctor", domain="[('sync_wipro_type', '=', 'doctor_internal')]")
    location_id = fields.Many2one('stock.location', string="Location", domain="[('sync_id', '>', 0)]")
    order_id = fields.Many2one('sale.order', string="Admission")
    parent_analytic_id = fields.Many2one('account.analytic.account', string="Analytic Specialization", domain="[('sync_wipro_type', '=', 'specialization')]")
    parent_analytic_primary_id = fields.Many2one('account.analytic.account', string="Primary Specialization", domain="[('sync_wipro_type', '=', 'specialization')]")
    partner_id = fields.Many2one('res.partner', string="Patient", domain="[('patient', '=', True)]")
    payer = fields.Many2one('res.partner', string="Payer", domain="[('customer_wipro', '=', True)]")
    perform_doc_id = fields.Many2one('account.analytic.account', string="Perform Doctor", domain="[('sync_wipro_type', '=', 'doctor_internal')]")
    prescribe_doc_id = fields.Many2one('account.analytic.account', string="Prescribe Doctor", domain="[('sync_wipro_type', '=', 'doctor_internal')]")
    primary_doc_id = fields.Many2one('account.analytic.account', string="Primary Doctor", domain="[('sync_wipro_type', '=', 'doctor_internal')]")
    product_uom = fields.Many2one('uom.uom', string="UOM")
    service_categ_id = fields.Many2one('product.category', string="Service Category", domain="[('sync_id', '>', 0)]")
    bool_filter = fields.Boolean('True or False')
    value_text = fields.Char(string="Char Filter")
    date_filter = fields.Date(string="Date Filter")
    field_import = fields.Char(string="Field Import")
    display_value = fields.Char(string="Display Value", compute='_compute_display', readonly=True, store=True)
    display_field = fields.Char(string="Display Field", compute='_compute_display', readonly=True, store=True)
    bulk_id = fields.Many2one('sale.order.bulk.filter', string="Bulk Filter")


    @api.model
    def create(self, vals):
        open('/opt/odoo16/logs/bulk.log', 'a+').write('\n' + str('START').encode('utf-8'))
        if vals.get('field_import'):
            field = self.env['ir.model.fields'].search([('field_description', '=', vals['field_import']), ('model_id.model', '=', 'sale.order.line')], order="id asc", limit=1)
            open('/opt/odoo16/logs/bulk.log', 'a+').write('\n' + str(field).encode('utf-8'))
            if not field:
                raise exceptions.UserError('Field tidak ditemukan!!!')
            else:
                vals['filter_column_id'] = field.id
        res = super(SaleOrderAkasiaWizardLine, self).create(vals)
        return res

    @api.depends('filter_column_id', 'product_id', 'account_analytic_id',
                 'location_id', 'order_id', 'parent_analytic_id',
                 'parent_analytic_primary_id', 'partner_id', 'payer',
                 'perform_doc_id', 'prescribe_doc_id', 'primary_doc_id',
                 'product_uom', 'service_categ_id')
    def _compute_display(self):
        for record in self:
            record.display_value = " "
            if record.filter_column_id:
                record.display_field = record.filter_column_id.field_description
            if record.product_id:
                record.display_value = record.product_id.display_name
            if record.account_analytic_id:
                record.display_value = record.account_analytic_id.display_name
            if record.location_id:
                record.display_value = record.location_id.display_name
            if record.order_id:
                record.display_value = record.order_id.display_name
            if record.parent_analytic_id:
                record.display_value = record.parent_analytic_id.display_name
            if record.parent_analytic_primary_id:
                record.display_value = record.parent_analytic_primary_id.display_name
            if record.payer:
                record.display_value = record.payer.display_name
            if record.perform_doc_id:
                record.display_value = record.perform_doc_id.display_name
            if record.prescribe_doc_id:
                record.display_value = record.prescribe_doc_id.display_name
            if record.primary_doc_id:
                record.display_value = record.primary_doc_id.display_name
            if record.product_uom:
                record.display_value = record.product_uom.display_name
            if record.service_categ_id:
                record.display_value = record.service_categ_id.display_name
            if record.partner_id:
                record.display_value = record.partner_id.display_name

    @api.depends('filter_column_id')
    def _compute_field_name(self):
        for record in self:
            if record.filter_column_id:
                record.field_name = record.filter_column_id.name
                record.type_field = record.filter_column_id.ttype

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(SaleOrderAkasiaWizardLine, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        res['arch'] = """
                <form string="Filter Line">
                    <group>
                        <field name="filter_column_id"/>
                        <field name="field_name" invisible="1"/>
                        <field name="type_field" invisible="1"/>
                        <field name="display_value" invisible="1"/>
                        <field name="display_field" invisible="1"/>
                        <field name="account_analytic_id" attrs="{'invisible': [('field_name', '!=', 'account_analytic_id')]}"/>
                        <field name="location_id" attrs="{'invisible': [('field_name', '!=', 'location_id')]}"/>
                        <field name="order_id" attrs="{'invisible': [('field_name', '!=', 'order_id')]}"/>
                        <field name="parent_analytic_id" attrs="{'invisible': [('field_name', '!=', 'parent_analytic_id')]}"/>
                        <field name="parent_analytic_primary_id" attrs="{'invisible': [('field_name', '!=', 'parent_analytic_primary_id')]}"/>
                        <field name="partner_id" attrs="{'invisible': [('field_name', '!=', 'partner_id')]}"/>
                        <field name="payer" attrs="{'invisible': [('field_name', '!=', 'payer')]}"/>
                        <field name="perform_doc_id" attrs="{'invisible': [('field_name', '!=', 'perform_doc_id')]}"/>
                        <field name="prescribe_doc_id" attrs="{'invisible': [('field_name', '!=', 'prescribe_doc_id')]}"/>
                        <field name="primary_doc_id" attrs="{'invisible': [('field_name', '!=', 'primary_doc_id')]}"/>
                        <field name="product_id" attrs="{'invisible': [('field_name', '!=', 'product_id')]}"/>
                        <field name="product_uom" attrs="{'invisible': [('field_name', '!=', 'product_uom')]}"/>
                        <field name="service_categ_id" attrs="{'invisible': [('field_name', '!=', 'service_categ_id')]}"/>
                        <field name="value_text" attrs="{'invisible': [('type_field', 'not in', ['char', 'text'])]}"/>
                        <field name="bool_filter" attrs="{'invisible': [('type_field', '!=', 'boolean')]}"/>
                        <field name="date_filter" attrs="{'invisible': [('type_field', 'not in', ['date', 'datetime'])]}"/>
                    </group>
                </form>
        """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(self._name, doc, view_id)
        return res



class SalesDataArcus(models.Model):
    _name = 'sales.data.arcus'


    tglproses = fields.Char(string="Tanggal Proses", index=True)
    sync_id_api = sync.id_api
    sync_type = sync.type
    sales_type_line = fields.Char(string="Sales Type Line", index=True)
    sales_patient_group = fields.Char(string="Sales Patient Group", index=True)
    sales_patient_type = fields.Char(string="Sales Patient Type", index=True)
    sales_patient_type_name = fields.Char(string="Sales Patient Type Name", index=True)
    sales_admission_id = fields.Char(string="Sales Admission ID", index=True)
    sales_admission_number = fields.Char(string="Sales Admission Number", index=True)
    sales_admission_date = fields.Char(string="Sales Admission Date", index=True)
    sales_patient_id = fields.Char(string="Sales Patient ID", index=True)
    sales_patient_code = fields.Char(string="Sales Patient Code", index=True)
    sales_patient_name = fields.Char(string="Sales Patient Name", index=True)
    sales_genderid = fields.Char(string="Sales Gender ID", index=True)
    sales_gender = fields.Char(string="Sales Gender", index=True)
    sales_age = fields.Integer(string="Sales Age", index=True)
    sales_agetype = fields.Char(string="Sales Age Type", index=True)
    sales_patient_city = fields.Char(string="Sales Patient City", index=True)
    sales_patient_district = fields.Char(string="Sales Patient District", index=True)
    sales_patient_subdistrict = fields.Char(string="Sales Patient Subdistrict", index=True)
    sales_payor_sequence = fields.Char(string="Sales Payor Sequence", index=True)
    sales_payor_id = fields.Char(string="Sales Payor ID", index=True)
    sales_payor_code = fields.Char(string="Sales Payor Code", index=True)
    sales_payor_name = fields.Char(string="Sales Payor Name", index=True)
    sales_payor_type = fields.Char(string="Sales Payor Type", index=True)
    sales_tariffid = fields.Char(string="Sales Tariff ID", index=True)
    sales_tariffname = fields.Char(string="Sales Tariff Name", index=True)
    sales_note = fields.Text(string='Sales Note')
    sales_order_no = fields.Char(string="Sales Order No", index=True)
    sales_order_type = fields.Char(string="Sales Order Type", index=True)
    sales_order_datetime = fields.Datetime(string="Sales Order Datetime")
    sales_return_datetime = fields.Datetime(string="Sales Return Datetime")
    


    sales_order_cyto = fields.Char(string="Sales Order Cyto", index=True)
    sales_order_penyulit = fields.Char(string="Sales Order Penyulit", index=True)
    room_id = fields.Char(string="Room ID", index=True)
    room_name = fields.Char(string="Room Name", index=True)
    bed_id = fields.Char(string="Bed ID", index=True)
    bed_name = fields.Char(string="Bed Name", index=True)
    sales_service_group_id = fields.Char(string="Sales Service Group ID", index=True)
    sales_service_group = fields.Char(string="Sales Service Group", index=True)
    sales_service_category_id = fields.Char(string="Sales Service Category ID", index=True)
    sales_service_category = fields.Char(string="Sales Service Category", index=True)
    sales_product_category_id = fields.Char(string="Sales Product Category ID", index=True)
    sales_product_category = fields.Char(string="Sales Product Category", index=True)

    sales_department_id = fields.Char(string="Sales Department ID", index=True)
    sales_department = fields.Char(string="Sales Department", index=True)
    sales_location_id = fields.Char(string="Sales Location ID", index=True)
    sales_location = fields.Char(string="Sales Location", index=True)

    sales_specialisation_id = fields.Char(string="Sales Specialisation ID", index=True)

    sales_specialisation = fields.Char(string="Sales Specialisation", index=True)
    sales_billable_bed_type_name = fields.Char(string="Sales Billable Bed Type Name", index=True)
    sales_billable_bed_type_id = fields.Char(string="Sales Billable Bed Type ID", index=True)
    sales_alloted_bed_type_id = fields.Char(string="Sales Alloted Bed Type ID", index=True)
    sales_alloted_bed_type_name = fields.Char(string="Sales Alloted Bed Type Name", index=True)
    sales_eligible_bed_type_id = fields.Char(string="Sales Eligible Bed Type ID", index=True)
    sales_eligible_bed_type_name = fields.Char(string="Sales Eligible Bed Type Name", index=True)
    sales_ward_id = fields.Char(string="Sales Ward ID", index=True)
    sales_ward_name = fields.Char(string="Sales Ward Name", index=True)
    sales_bed_allocation_id = fields.Char(string="Sales Bed Allocation ID", index=True)
    sales_bed_allocation_no = fields.Char(string="Sales Bed Allocation No", index=True)

    sales_bed_allocation_start = fields.Datetime(string="Sales Bed Allocation Start Datetime")
    sales_bed_allocation_end = fields.Datetime(string="Sales Bed Allocation End Datetime")

    sales_billitemid = fields.Char(string="Sales Bill Item ID", index=True)
    sales_chargecodeid = fields.Char(string="Sales Charge Code ID", index=True)
    sales_itemsequence = fields.Char(string="Sales Item Sequence", index=True)
    sales_product_id = fields.Char(string="Sales Product ID", index=True)
    sales_product_code = fields.Char(string="Sales Product Code", index=True)
    sales_product_name = fields.Char(string="Sales Product Name", index=True)
    sales_orderitemid = fields.Char(string="Sales Order Item ID", index=True)
    sales_patientorderid = fields.Char(string="Sales Patient Order Item ID", index=True)
    package_doctor_share = fields.Float(string="Package Doctor Share")

    sales_username_order = fields.Char(string="Sales UserName Order", index=True)
    sales_product_uom_id = fields.Char(string="Sales Product UoM ID", index=True)
    sales_product_uom_name = fields.Char(string="Sales Product UoM Name", index=True)
    
    sales_product_qty = fields.Float(string="Sales Product Qty")
    sales_price_unit = fields.Float(string="Sales Price Unit")
    sales_price_total = fields.Float(string="Sales Price Total")
    sales_cost_unit = fields.Float(string="Sales Cost Unit")
    sales_cost_total = fields.Float(string="Sales Cost Total")
    sales_hna_unit = fields.Float(string="Sales HNA Unit")
    sales_hna_total = fields.Float(string="Sales HNA Total")
    sales_baseprice_unit = fields.Float(string="Sales BasePrice Unit")
    sales_baseprice_total = fields.Float(string="Sales BasePrice Total")
        

    sales_discount_slno = fields.Char(string="Sales Discount SL No", index=True)
    
    sales_discount_id = fields.Char(string="Sales Discount ID", index=True)
    sales_discount_name = fields.Char(string="Sales Discount Name", index=True)
    sales_discount_datetime = fields.Datetime(string="Sales Discount Datetime", index=True)
    sales_discount_authorized_id = fields.Char(string="Sales Discount Authorized ID", index=True)
    sales_discount_authorized_by = fields.Char(string="Sales Discount Authorized By", index=True)
    sales_discount_cancel_datetime = fields.Datetime(string="Sales Discount Cancel Datetime", index=True)
    sales_discount_type = fields.Char(string="Sales Discount Type", index=True)
    sales_discount_reason = fields.Text(string="Sales Discount Reason")
    sales_provisional_primary_disease_code = fields.Text(string="Sales Provisional Primary Disease Code")
    sales_provisional_primary_disease_name = fields.Text(string="Sales Provisional Primary Disease Name")
    sales_provisional_secondary_disease_code = fields.Text(string="Sales Provisional Secondary Disease Code")
    sales_provisional_secondary_disease_name = fields.Text(string="Sales Provisional Secondary Disease Name")
    sales_doctor_primary_id = fields.Char(string="Sales Doctor Primary ID", index=True)
    sales_doctor_primary_code = fields.Char(string="Sales Doctor Primary Code", index=True)
    sales_doctor_primary_name = fields.Char(string="Sales Doctor Primary Name", index=True)
    sales_spec_primary_id = fields.Char(string="Sales Spec Primary ID", index=True)
    sales_spec_primary_code = fields.Char(string="Sales Spec Primary Code", index=True)
    sales_spec_primary_name = fields.Char(string="Sales Spec Primary Name", index=True)
    sales_sub_spec_primary_id = fields.Char(string="Sales Sub Spec Primary ID", index=True)
    sales_sub_spec_primary_code = fields.Text(string="Sales Sub Spec Primary Code")
    sales_sub_spec_primary_name = fields.Text(string="Sales Sub Spec Primary Name")
    sales_doctor_prescribe_id = fields.Char(string="Sales Doctor Prescribe ID", index=True)
    sales_doctor_prescribe_code = fields.Char(string="Sales Doctor Prescribe Code", index=True)
    sales_doctor_prescribe_name = fields.Char(string="Sales Doctor Prescribe Name", index=True)
    sales_spec_prescribe_id = fields.Char(string="Sales Spec Prescribe ID", index=True)
    sales_spec_prescribe_code = fields.Char(string="Sales Spec Prescribe Code", index=True)
    sales_spec_prescribe_name = fields.Char(string="Sales Spec Prescribe Name", index=True)
    sales_sub_spec_prescribe_id = fields.Char(string="Sales Sub Spec Prescribe ID", index=True)
    sales_sub_spec_prescribe_code = fields.Text(string="Sales Sub Spec Prescribe Code")
    sales_sub_spec_prescribe_name = fields.Text(string="Sales Sub Spec Prescribe Name")
    sales_doctor_perform_id = fields.Char(string="Sales Doctor Perform ID", index=True)
    sales_doctor_perform_code = fields.Char(string="Sales Doctor Perform Code", index=True)
    sales_doctor_perform_name = fields.Char(string="Sales Doctor Perform Name", index=True)
    sales_spec_perform_id = fields.Char(string="Sales Spec Perform ID", index=True)
    sales_spec_perform_code = fields.Char(string="Sales Spec Perform Code", index=True)
    sales_spec_perform_name = fields.Char(string="Sales Spec Perform Name", index=True)
    sales_sub_spec_perform_id = fields.Char(string="Sales Sub Spec Perform ID", index=True)
    sales_sub_spec_perform_code = fields.Text(string="Sales Sub Spec Perform Code")
    sales_sub_spec_perform_name = fields.Text(string="Sales Sub Spec Perform Name")
    sales_as_icu = fields.Boolean(string="Sales As ICU")
    sales_as_aps = fields.Boolean(string="Sales As APS")
    sales_as_surgery = fields.Boolean(string="Sales As Surgery")
    sales_as_daycare = fields.Boolean(string="Sales As Daycare")
    sales_as_consultation = fields.Boolean(string="Sales As Consultation")
    sales_as_baby = fields.Boolean(string="Sales As Baby")
    sales_as_package = fields.Boolean(string="Sales As Package")
    sales_doctor_analytic_id = fields.Char(string="Sales Doctor Analytic ID", index=True)
    sales_doctor_analytic_code = fields.Char(string="Sales Doctor Analytic Code", index=True)
    sales_doctor_analytic_name = fields.Char(string="Sales Doctor Analytic Name", index=True)
    arcus_billing_group_id = fields.Char(string="Arcus Billing Group ID", index=True)
    arcus_billing_group_name = fields.Char(string="Arcus Billing Group Name", index=True)
    arcus_sub_billing_group_id = fields.Char(string="Arcus Sub Billing Group ID", index=True)
    arcus_sub_billing_group_name = fields.Char(string="Arcus Sub Billing Group Name", index=True)
    sales_company = fields.Char(string="Sales Company", index=True)
    sales_revenue_type = fields.Char(string="Sales Revenue Type", index=True)
    sales_special_group = fields.Char(string="Sales Special Group", index=True)
    sales_special_group2 = fields.Char(string="Sales Special Group 2", index=True)
    sales_ref_admission_type = fields.Char(string="Sales Ref Admission Type", index=True)
    sales_ref_admission_no = fields.Char(string="Sales Ref Admission No", index=True)
    sales_parent_admission_id = fields.Char(string="Sales Parent Admission ID", index=True)
    sales_parent_admission_no = fields.Char(string="Sales Parent Admission No", index=True)
    sales_billing_id = fields.Char(string="Sales Billing ID", index=True)
    sales_billing_no = fields.Char(string="Sales Billing No", index=True)
    sales_billing_date = fields.Datetime(string="Sales Billing Date", index=True)
    sales_bill_cancel_datetime = fields.Datetime(string="Sales Bill Cancel Datetime", index=True)
    sales_bill_cancel_item_date_item = fields.Char(string="Sales Bill Cancel Item Date Item", index=True)
    sales_bill_cancel_reason = fields.Char(string="Sales Bill Cancel Reason", index=True)
    sales_discharge_date = fields.Datetime(string="Sales Discharge Date", index=True)
    sales_discharge_reason = fields.Char(string="Sales Discharge Reason", index=True)
    sales_patient_ref_no = fields.Char(string="Sales Patient Ref No", index=True)
    sales_batch_id = fields.Char(string="Sales Batch ID", index=True)
    sales_batch_no = fields.Char(string="Sales Batch No", index=True)
    sales_batch_expiry = fields.Date(string="Sales Batch Expiry", index=True)
    sales_package_type = fields.Char(string="Sales Package Type", index=True)
    sales_package_id = fields.Char(string="Sales Package ID", index=True)
    sales_package_name = fields.Char(string="Sales Package Name", index=True)
    sales_package_contribution = fields.Float(string="Sales Package Contribution")
    sales_package_selling_price = fields.Float(string="Sales Package Selling Price")
    sales_package_order_date = fields.Datetime(string="Sales Package Order Date", index=True)
    sales_package_order_no = fields.Char(string="Sales Package Order No", index=True)
    sales_inacbg_group_code = fields.Char(string="Sales INACBG Group Code", index=True)
    sales_inacbg_group_name = fields.Char(string="Sales INACBG Group Name", index=True)
    sales_surgery_type = fields.Char(string="Sales Surgery Type", index=True)
    sales_product_manufacture_id = fields.Char(string="Sales Product Manufacture ID", index=True)
    sales_product_manufacture = fields.Char(string="Sales Product Manufacture", index=True)
    sales_product_brand_id = fields.Char(string="Sales Product Brand ID", index=True)
    sales_product_brand = fields.Char(string="Sales Product Brand", index=True)
    sales_product_antibiotic = fields.Char(string="Sales Product Antibiotic", index=True)
    sales_product_generic = fields.Char(string="Sales Product Generic", index=True)
    sales_product_narcotic = fields.Char(string="Sales Product Narcotic", index=True)
    sales_product_psychotropic = fields.Char(string="Sales Product Psychotropic", index=True)
    sales_as_cathlab = fields.Boolean(string="Sales As Cathlab")
    sales_patient_total_receipt_amount = fields.Float(string="Sales Patient Total Receipt Amount")
    sales_patient_latest_receipt_datetime = fields.Datetime(string="Sales Patient Latest Receipt Datetime", index=True)
    sales_payer_total_receipt_amount = fields.Float(string="Sales Payer Total Receipt Amount")
    sales_payer_latest_receipt_datetime = fields.Datetime(string="Sales Payer Latest Receipt Datetime", index=True)
    sales_total_round_off_bill_amount = fields.Float(string="Sales Total Round Off Bill Amount")
    sales_final_primary_disease_code = fields.Char(string="Sales Final Primary Disease Code", index=True)
    sales_final_primary_disease_name = fields.Char(string="Sales Final Primary Disease Name", index=True)
    sales_final_secondary_disease_code = fields.Char(string="Sales Final Secondary Disease Code", index=True)
    sales_final_secondary_disease_name = fields.Char(string="Sales Final Secondary Disease Name", index=True)
    sales_referral_type = fields.Char(string="Sales Referral Type", index=True)
    sales_referral_number = fields.Char(string="Sales Referral Number", index=True)
    sales_doctor_referral_id = fields.Char(string="Sales Doctor Referral ID", index=True)
    sales_doctor_referral_code = fields.Char(string="Sales Doctor Referral Code", index=True)
    sales_doctor_referral_name = fields.Char(string="Sales Doctor Referral Name", index=True)
    sales_referral_remarks = fields.Text(string="Sales Referral Remarks")
    sales_spec_referral_id = fields.Char(string="Sales Spec Referral ID", index=True)
    sales_spec_referral_code = fields.Char(string="Sales Spec Referral Code", index=True)
    sales_spec_referral_name = fields.Char(string="Sales Spec Referral Name", index=True)
    sales_group_primary_doctor_id = fields.Char(string="Sales Group Primary Doctor ID", index=True)
    sales_group_primary_doctor_code = fields.Char(string="Sales Group Primary Doctor Code", index=True)
    sales_group_primary_doctor_name = fields.Char(string="Sales Group Primary Doctor Name", index=True)
    sales_group_primary_spec_id = fields.Char(string="Sales Group Primary Spec ID", index=True)
    sales_group_primary_spec_code = fields.Char(string="Sales Group Primary Spec Code", index=True)
    sales_group_primary_spec_name = fields.Char(string="Sales Group Primary Spec Name", index=True)
    sales_group_primary_subspec_id = fields.Char(string="Sales Group Primary Subspec ID", index=True)
    sales_group_primary_subspec_code = fields.Char(string="Sales Group Primary Subspec Code", index=True)
    sales_group_primary_subspec_name = fields.Char(string="Sales Group Primary Subspec Name", index=True)
    sales_group_analytic_doctor_id = fields.Char(string="Sales Group Analytic Doctor ID", index=True)
    sales_group_analytic_doctor_code = fields.Char(string="Sales Group Analytic Doctor Code", index=True)
    sales_group_analytic_doctor_name = fields.Char(string="Sales Group Analytic Doctor Name", index=True)
    sales_group_analytic_spec_id = fields.Char(string="Sales Group Analytic Spec ID", index=True)
    sales_group_analytic_spec_code = fields.Char(string="Sales Group Analytic Spec Code", index=True)
    sales_group_analytic_spec_name = fields.Char(string="Sales Group Analytic Spec Name", index=True)
    sales_group_analytic_subspec_id = fields.Char(string="Sales Group Analytic Subspec ID", index=True)
    sales_group_analytic_subspec_code = fields.Char(string="Sales Group Analytic Subspec Code", index=True)
    sales_group_analytic_subspec_name = fields.Char(string="Sales Group Analytic Subspec Name", index=True)
    surgery_operator_id = fields.Char(string="Surgery Operator ID", index=True)
    surgery_operator_code = fields.Char(string="Surgery Operator Code", index=True)
    surgery_operator_name = fields.Char(string="Surgery Operator Name", index=True)
    surgery_operator_ass_id = fields.Char(string="Surgery Operator Assistant ID", index=True)
    surgery_operator_ass_code = fields.Char(string="Surgery Operator Assistant Code", index=True)
    surgery_operator_ass_name = fields.Char(string="Surgery Operator Assistant Name", index=True)
    anesthetist_operator_id = fields.Char(string="Anesthetist Operator ID", index=True)
    anesthetist_operator_code = fields.Char(string="Anesthetist Operator Code", index=True)
    anesthetist_operator_name = fields.Char(string="Anesthetist Operator Name", index=True)
    anesthetist_operator_ass_id = fields.Char(string="Anesthetist Operator Assistant ID", index=True)
    anesthetist_operator_ass_code = fields.Char(string="Anesthetist Operator Assistant Code", index=True)
    anesthetist_operator_ass_name = fields.Char(string="Anesthetist Operator Assistant Name", index=True)
    surgery_team_id = fields.Char(string="Surgery Team ID", index=True)
    surgery_team_code = fields.Char(string="Surgery Team Code", index=True)
    surgery_team_name = fields.Char(string="Surgery Team Name", index=True)
    surgery_team_ass_id = fields.Char(string="Surgery Team Assistant ID", index=True)
    surgery_team_ass_code = fields.Char(string="Surgery Team Assistant Code", index=True)
    surgery_team_ass_name = fields.Char(string="Surgery Team Assistant Name", index=True)
    sales_patient_member_card_number = fields.Char(string="Sales Patient Member Card Number", index=True)
    sales_order_status = fields.Char(string="Sales Order Status", index=True)
    sales_order_lastupdate = fields.Datetime(string='Sales Order Last Update', index=True)
    sales_ref_admission_id = fields.Char(string="Sales Ref Admission ID", index=True)
    sales_order_start = fields.Datetime(string="Sales Order Start", index=True)
    sales_order_end = fields.Datetime(string="Sales Order End", index=True)


    sales_patient_register_date = fields.Datetime(string='Sales Patient Register Date', index=True)
    sales_admission_datetime = fields.Datetime(string='Sales Admission Datetime', index=True)
    sales_discharge_datetime = fields.Datetime(string='Sales Discharge Datetime', index=True)
    sales_billing_datetime = fields.Datetime(string='Sales Billing Datetime', index=True)
    sales_product_ingredient = fields.Char(string="Sales Product Ingredient", index=True)
    
    sales_diagnosis_primary_code = fields.Char(string="Sales Diagnosis Primary Code", index=True)
    sales_diagnosis_primary_name = fields.Char(string="Sales Diagnosis Primary Name", index=True)
    sales_diagnosis_secondary_code = fields.Char(string="Sales Diagnosis Secondary Code", index=True)
    sales_diagnosis_secondary_name = fields.Char(string="Sales Diagnosis Secondary Name", index=True)
    sales_procedure_code = fields.Char(string="Sales Procedure Code", index=True)
    sales_procedure_name = fields.Char(string="Sales Procedure Name", index=True)
    
    




class SaleDiagnoses(models.Model):
    _name = 'sale.diagnoses'


    visit_id = fields.Char(string="Visit ID", index=True)
    visit_no = fields.Char(string="Visit No.", index=True)
    problemcode = fields.Char(string="Problem Code", index=True)
    problemname = fields.Char(string="Problem Name", index=True)
    isprimary = fields.Boolean(string="Is Primary", index=True)
    admission_id = fields.Many2one('sale.order', string="Admission ID", index=True)

    company_id = fields.Many2one('res.company', string="Company", index=True)
    
    sync_id_api = sync.id_api
    sync_type = sync.type
    
        
class SaleProcedure(models.Model):
    _name = 'sale.procedure'


    visit_id = fields.Char(string="Visit ID", index=True)
    visit_no = fields.Char(string="Visit No.", index=True)
    procedurecode = fields.Char(string="Procedure Code", index=True)
    procedurename = fields.Char(string="Procedure Name", index=True)
    admission_id = fields.Many2one('sale.order', string="Admission ID", index=True)
    
    company_id = fields.Many2one('res.company', string="Company", index=True)
    
    sync_id_api = sync.id_api
    sync_type = sync.type



class RevenuePLActual(models.Model):
    _name = 'pmo.revenue.pl.actual'
    _rec_name = 'idactual'
    _description = "Revenue by PL Actual"

    @api.model
    def _get_company(self):
        return self.env.company.id
			
    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    periode = fields.Date(string="Periode")
    unit = fields.Char(string="Unit")
    idf = fields.Char(string="Idf")
    finance = fields.Char(string="Finance")
    idactual = fields.Char(string="Actual ID.")
    categ_id = fields.Char(string="Category ID.")
    category = fields.Char(string="Category")
    code = fields.Char(string="Code")
    desc = fields.Char(string="Description")
    actual = fields.Float(string="Actual")
    update_date = fields.Date(string="Update Date") 

    @api.model_create_multi
    def create(self, vals_list):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for vals in vals_list:
            if not isinstance(vals, dict):
                continue

            if lock_setting and lock_setting.lock_date and vals.get('periode'):
                periode = fields.Date.to_date(vals['periode'])

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records has been Lock: {lock_setting.lock_date}, cannot import pmo dashboard: {periode}"
                    )

            # Validasi double upload
            existing = self.search([('company_id', '=', self.env.company.id), ('periode', '=', periode)], limit=1)

            if existing:
                raise exceptions.ValidationError(
                    f"Records with periode: {periode} is duplicated."
                )

        # update_date = current_date
        vals['update_date'] = fields.Date.context_today(self)

        result = super(RevenuePLActual, self).create(vals_list)
        return result


    def unlink(self):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for rec in self:
            if rec.periode:
                periode = fields.Date.to_date(rec.periode)

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records cannot be deleted because has been lock: {lock_setting.lock_date}"
                    )

        return super(RevenuePLActual, self).unlink()


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(RevenuePLActual,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Revenue by PL Actual">
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" readonly="1" />
                                <field name="periode" readonly="1" />
                                <field name="unit" readonly="1" />
                                <field name="idf" readonly="1" />
                                <field name="finance" readonly="1" />
                                <field name="idactual" readonly="1" />
                            </group>
                            <group>
                                <field name="categ_id" invisible="1" readonly="1" />
                                <field name="category" readonly="1" />
                                <field name="code" readonly="1" />
                                <field name="desc" readonly="1" />
                                <field name="actual" readonly="1" />
                                <field name="update_date" readonly="1" />
                            </group>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Revenue by PL Actual">
                    <field name="periode"/>
                    <field name="finance"/>
                    <field name="idactual"/>
                    <field name="category"/>
                    <field name="code"/>
                    <field name="desc" />
                    <!--field name="actual" sum="Total" widget="monetary" string="Total" modifiers="{'readonly': true}"/-->
                    <field name="actual" />
                    <field name="company_id" />
                    <field name="update_date" />
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

class RevenuePLBudget(models.Model):
    _name = 'pmo.revenue.pl.budget'
    _rec_name = 'idbudget'
    _description = "Revenue by PL Budget"

    @api.model
    def _get_company(self):
        return self.env.company.id
			
    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    periode = fields.Date(string="Periode")
    unit = fields.Char(string="Unit")
    idf = fields.Char(string="Idf")
    finance = fields.Char(string="Finance")
    idactual = fields.Char(string="Actual ID.")
    idbudget = fields.Char(string="Budget ID.")
    categ_id = fields.Char(string="Category ID.")
    category = fields.Char(string="Category")
    code = fields.Char(string="Code")
    desc = fields.Char(string="Description")
    budget = fields.Float(string="Budget")
    update_date = fields.Date(string="Update Date")


    @api.model_create_multi
    def create(self, vals_list):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for vals in vals_list:
            if not isinstance(vals, dict):
                continue

            if lock_setting and lock_setting.lock_date and vals.get('periode'):
                periode = fields.Date.to_date(vals['periode'])

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records has been Lock: {lock_setting.lock_date}, cannot import pmo dashboard: {periode}"
                    )

            # Validasi double upload
            existing = self.search([('company_id', '=', self.env.company.id), ('periode', '=', periode)], limit=1)

            if existing:
                raise exceptions.ValidationError(
                    f"Records with periode: {periode} is duplicated."
                )

        # update_date = current_date
        vals['update_date'] = fields.Date.context_today(self)

        result = super(RevenuePLBudget, self).create(vals_list)
        return result


    def unlink(self):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for rec in self:
            if rec.periode:
                periode = fields.Date.to_date(rec.periode)

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records cannot be deleted because has been lock: {lock_setting.lock_date}"
                    )

        return super(RevenuePLBudget, self).unlink()

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(RevenuePLBudget,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Revenue by PL Budget">
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" readonly="1" />
                                <field name="periode" readonly="1" />
                                <field name="unit" readonly="1" />
                                <field name="idf" readonly="1" />
                                <field name="finance" readonly="1" />
                                <field name="idactual" readonly="1" />
                                <field name="idbudget" readonly="1" />
                            </group>
                            <group>
                                <field name="categ_id" invisible="1" readonly="1" />
                                <field name="category" readonly="1" />
                                <field name="code" readonly="1" />
                                <field name="desc" readonly="1" />
                                <field name="budget" readonly="1" />
                                <field name="update_date" readonly="1" />
                            </group>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Revenue by PL Budget">
                    <field name="periode"/>
                    <field name="finance"/>
                    <field name="idactual"/>
                    <field name="category"/>
                    <field name="code"/>
                    <field name="desc" />
                    <field name="budget" />
                    <field name="company_id" />
                    <field name="update_date" />
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class RevenuePayorActual(models.Model):
    _name = 'pmo.revenue.payor.actual'
    _rec_name = 'idactual'
    _description = "Revenue by Payor Actual"

    @api.model
    def _get_company(self):
        return self.env.company.id
			
    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    periode = fields.Date(string="Periode")
    unit = fields.Char(string="Unit")
    idf = fields.Char(string="Idf")
    finance = fields.Char(string="Finance")
    idactual = fields.Char(string="Actual ID.")
    categ_id = fields.Char(string="Category ID.")
    category = fields.Char(string="Category")
    code = fields.Char(string="Code")
    desc = fields.Char(string="Description")
    actual = fields.Float(string="Actual")
    update_date = fields.Date(string="Update Date")


    @api.model_create_multi
    def create(self, vals_list):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for vals in vals_list:
            if not isinstance(vals, dict):
                continue

            if lock_setting and lock_setting.lock_date and vals.get('periode'):
                periode = fields.Date.to_date(vals['periode'])

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records has been Lock: {lock_setting.lock_date}, cannot import pmo dashboard: {periode}"
                    )

            # Validasi double upload
            existing = self.search([('company_id', '=', self.env.company.id), ('periode', '=', periode)], limit=1)

            if existing:
                raise exceptions.ValidationError(
                    f"Records with periode: {periode} is duplicated."
                )

        # update_date = current_date
        vals['update_date'] = fields.Date.context_today(self)

        result = super(RevenuePayorActual, self).create(vals_list)
        return result


    def unlink(self):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for rec in self:
            if rec.periode:
                periode = fields.Date.to_date(rec.periode)

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records cannot be deleted because has been lock: {lock_setting.lock_date}"
                    )

        return super(RevenuePayorActual, self).unlink()

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(RevenuePayorActual,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Revenue by Payor Actual">
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" readonly="1" />
                                <field name="periode" readonly="1" />
                                <field name="unit" readonly="1" />
                                <field name="idf" readonly="1" />
                                <field name="finance" readonly="1" />
                                <field name="idactual" readonly="1" />
                            </group>
                            <group>
                                <field name="categ_id" invisible="1" readonly="1" />
                                <field name="category" readonly="1" />
                                <field name="code" readonly="1" />
                                <field name="desc" readonly="1" />
                                <field name="actual" readonly="1" />
                                <field name="update_date" readonly="1" />
                            </group>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Revenue by Payor Actual">
                    <field name="periode"/>
                    <field name="finance"/>
                    <field name="idactual"/>
                    <field name="category"/>
                    <field name="code"/>
                    <field name="desc" />
                    <field name="actual" />
                    <field name="company_id" />
                    <field name="update_date" />
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class RevenuePayorBudget(models.Model):
    _name = 'pmo.revenue.payor.budget'
    _rec_name = 'idbudget'
    _description = "Revenue by Payor Budget"

    @api.model
    def _get_company(self):
        return self.env.company.id
			
    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    periode = fields.Date(string="Periode")
    unit = fields.Char(string="Unit")
    idf = fields.Char(string="Idf")
    finance = fields.Char(string="Finance")
    idactual = fields.Char(string="Actual ID.")
    idbudget = fields.Char(string="Budget ID.")
    categ_id = fields.Char(string="Category ID.")
    category = fields.Char(string="Category")
    code = fields.Char(string="Code")
    desc = fields.Char(string="Description")
    budget = fields.Float(string="Budget")
    update_date = fields.Date(string="Update Date")

    @api.model_create_multi
    def create(self, vals_list):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for vals in vals_list:
            if not isinstance(vals, dict):
                continue

            if lock_setting and lock_setting.lock_date and vals.get('periode'):
                periode = fields.Date.to_date(vals['periode'])

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records has been Lock: {lock_setting.lock_date}, cannot import pmo dashboard: {periode}"
                    )

            # Validasi double upload
            existing = self.search([('company_id', '=', self.env.company.id), ('periode', '=', periode)], limit=1)

            if existing:
                raise exceptions.ValidationError(
                    f"Records with periode: {periode} is duplicated."
                )

        # update_date = current_date
        vals['update_date'] = fields.Date.context_today(self)

        result = super(RevenuePayorBudget, self).create(vals_list)
        return result


    def unlink(self):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for rec in self:
            if rec.periode:
                periode = fields.Date.to_date(rec.periode)

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records cannot be deleted because has been lock: {lock_setting.lock_date}"
                    )

        return super(RevenuePayorBudget, self).unlink()

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(RevenuePayorBudget,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Revenue by Payor Budget">
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" readonly="1" />
                                <field name="periode" readonly="1" />
                                <field name="unit" readonly="1" />
                                <field name="idf" readonly="1" />
                                <field name="finance" readonly="1" />
                                <field name="idactual" readonly="1" />
                                <field name="idbudget" readonly="1" />
                            </group>
                            <group>
                                <field name="categ_id" invisible="1" readonly="1" />
                                <field name="category" readonly="1" />
                                <field name="code" readonly="1" />
                                <field name="desc" readonly="1" />
                                <field name="budget" readonly="1" />
                                <field name="update_date" readonly="1" />
                            </group>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Revenue by Payor Budget">
                    <field name="periode"/>
                    <field name="finance"/>
                    <field name="idactual"/>
                    <field name="category"/>
                    <field name="code"/>
                    <field name="desc" />
                    <field name="budget" />
                    <field name="company_id" />
                    <field name="update_date" />
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class RevenueTfsActual(models.Model):
    _name = 'pmo.revenue.tfs.actual'
    _rec_name = 'idactual'
    _description = "Revenue by TFS Actual"

    @api.model
    def _get_company(self):
        return self.env.company.id
			
    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    periode = fields.Date(string="Periode")
    unit = fields.Char(string="Unit")
    idf = fields.Char(string="Idf")
    finance = fields.Char(string="Finance")
    idactual = fields.Char(string="Actual ID.")
    categ_id = fields.Char(string="Category ID.")
    category = fields.Char(string="Category")
    code = fields.Char(string="Code")
    desc = fields.Char(string="Description")
    actual = fields.Float(string="Actual")
    update_date = fields.Date(string="Update Date")

    @api.model_create_multi
    def create(self, vals_list):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for vals in vals_list:
            if not isinstance(vals, dict):
                continue

            if lock_setting and lock_setting.lock_date and vals.get('periode'):
                periode = fields.Date.to_date(vals['periode'])

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records has been Lock: {lock_setting.lock_date}, cannot import pmo dashboard: {periode}"
                    )

            # Validasi double upload
            existing = self.search([('company_id', '=', self.env.company.id), ('periode', '=', periode)], limit=1)

            if existing:
                raise exceptions.ValidationError(
                    f"Records with periode: {periode} is duplicated."
                )

        # update_date = current_date
        vals['update_date'] = fields.Date.context_today(self)

        result = super(RevenueTfsActual, self).create(vals_list)
        return result


    def unlink(self):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for rec in self:
            if rec.periode:
                periode = fields.Date.to_date(rec.periode)

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records cannot be deleted because has been lock: {lock_setting.lock_date}"
                    )

        return super(RevenueTfsActual, self).unlink()


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(RevenueTfsActual,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Revenue by TFS Actual">
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" readonly="1" />
                                <field name="periode" readonly="1" />
                                <field name="unit" readonly="1" />
                                <field name="idf" readonly="1" />
                                <field name="finance" readonly="1" />
                                <field name="idactual" readonly="1" />
                            </group>
                            <group>
                                <field name="categ_id" invisible="1" readonly="1" />
                                <field name="category" readonly="1" />
                                <field name="code" readonly="1" />
                                <field name="desc" readonly="1" />
                                <field name="actual" readonly="1" />
                                <field name="update_date" readonly="1" />
                            </group>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Revenue by TFS Actual">
                    <field name="periode"/>
                    <field name="finance"/>
                    <field name="idactual"/>
                    <field name="category"/>
                    <field name="code"/>
                    <field name="desc" />
                    <field name="actual" />
                    <field name="company_id" />
                    <field name="update_date" />
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class RevenueTfsBudget(models.Model):
    _name = 'pmo.revenue.tfs.budget'
    _rec_name = 'idbudget'
    _description = "Revenue by TFS Budget"

    @api.model
    def _get_company(self):
        return self.env.company.id
			
    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    periode = fields.Date(string="Periode")
    unit = fields.Char(string="Unit")
    idf = fields.Char(string="Idf")
    finance = fields.Char(string="Finance")
    idactual = fields.Char(string="Actual ID.")
    idbudget = fields.Char(string="Budget ID.")
    categ_id = fields.Char(string="Category ID.")
    category = fields.Char(string="Category")
    code = fields.Char(string="Code")
    desc = fields.Char(string="Description")
    budget = fields.Float(string="Budget")
    update_date = fields.Date(string="Update Date")

    @api.model_create_multi
    def create(self, vals_list):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for vals in vals_list:
            if not isinstance(vals, dict):
                continue

            if lock_setting and lock_setting.lock_date and vals.get('periode'):
                periode = fields.Date.to_date(vals['periode'])

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records has been Lock: {lock_setting.lock_date}, cannot import pmo dashboard: {periode}"
                    )

            # Validasi double upload
            existing = self.search([('company_id', '=', self.env.company.id), ('periode', '=', periode)], limit=1)

            if existing:
                raise exceptions.ValidationError(
                    f"Records with periode: {periode} is duplicated."
                )

        # update_date = current_date
        vals['update_date'] = fields.Date.context_today(self)

        result = super(RevenueTfsBudget, self).create(vals_list)
        return result


    def unlink(self):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for rec in self:
            if rec.periode:
                periode = fields.Date.to_date(rec.periode)

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records cannot be deleted because has been lock: {lock_setting.lock_date}"
                    )

        return super(RevenueTfsBudget, self).unlink()


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(RevenueTfsBudget,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Revenue by TFS Budget">
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" readonly="1" />
                                <field name="periode" readonly="1" />
                                <field name="unit" readonly="1" />
                                <field name="idf" readonly="1" />
                                <field name="finance" readonly="1" />
                                <field name="idactual" readonly="1" />
                                <field name="idbudget" readonly="1" />
                            </group>
                            <group>
                                <field name="categ_id" invisible="1" readonly="1" />
                                <field name="category" readonly="1" />
                                <field name="code" readonly="1" />
                                <field name="desc" readonly="1" />
                                <field name="budget" readonly="1" />
                                <field name="update_date" readonly="1" />
                            </group>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Revenue by TFS Budget">
                    <field name="periode"/>
                    <field name="finance"/>
                    <field name="idactual"/>
                    <field name="category"/>
                    <field name="code"/>
                    <field name="desc" />
                    <field name="budget" />
                    <field name="company_id" />
                    <field name="update_date" />
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res



class RevenueThroughputActual(models.Model):
    _name = 'pmo.throughput.actual'
    _rec_name = 'idactual'
    _description = "Throughtput Actual"

    @api.model
    def _get_company(self):
        return self.env.company.id
			
    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    periode = fields.Date(string="Periode")
    unit = fields.Char(string="Unit")
    idf = fields.Char(string="Idf")
    finance = fields.Char(string="Finance")
    idactual = fields.Char(string="Actual ID.")
    categ_id = fields.Char(string="Category ID.")
    category = fields.Char(string="Category")
    code = fields.Char(string="Code")
    desc = fields.Char(string="Description")
    actual = fields.Float(string="Actual")
    update_date = fields.Date(string="Update Date")

    @api.model_create_multi
    def create(self, vals_list):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for vals in vals_list:
            if not isinstance(vals, dict):
                continue

            if lock_setting and lock_setting.lock_date and vals.get('periode'):
                periode = fields.Date.to_date(vals['periode'])

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records has been Lock: {lock_setting.lock_date}, cannot import pmo dashboard: {periode}"
                    )

            # Validasi double upload
            existing = self.search([('company_id', '=', self.env.company.id), ('periode', '=', periode)], limit=1)

            if existing:
                raise exceptions.ValidationError(
                    f"Records with periode: {periode} is duplicated."
                )

        # update_date = current_date
        vals['update_date'] = fields.Date.context_today(self)

        result = super(RevenueThroughputActual, self).create(vals_list)
        return result


    def unlink(self):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for rec in self:
            if rec.periode:
                periode = fields.Date.to_date(rec.periode)

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records cannot be deleted because has been lock: {lock_setting.lock_date}"
                    )

        return super(RevenueThroughputActual, self).unlink()


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(RevenueThroughputActual,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Throughtput Actual">
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" readonly="1" />
                                <field name="periode" readonly="1" />
                                <field name="unit" readonly="1" />
                                <field name="idf" readonly="1" />
                                <field name="finance" readonly="1" />
                                <field name="idactual" readonly="1" />
                            </group>
                            <group>
                                <field name="categ_id" invisible="1" readonly="1" />
                                <field name="category" readonly="1" />
                                <field name="code" readonly="1" />
                                <field name="desc" readonly="1" />
                                <field name="actual" readonly="1" />
                                <field name="update_date" readonly="1" />
                            </group>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Throughtput Actual">
                    <field name="periode"/>
                    <field name="finance"/>
                    <field name="idactual"/>
                    <field name="category"/>
                    <field name="code"/>
                    <field name="desc" />
                    <field name="actual" />
                    <field name="company_id" />
                    <field name="update_date" />
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

class RevenueThroughputBudget(models.Model):
    _name = 'pmo.throughput.budget'
    _rec_name = 'idbudget'
    _description = "Throughput Budget"

    @api.model
    def _get_company(self):
        return self.env.company.id
			
    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    periode = fields.Date(string="Periode")
    unit = fields.Char(string="Unit")
    idf = fields.Char(string="Idf")
    finance = fields.Char(string="Finance")
    idactual = fields.Char(string="Actual ID.")
    idbudget = fields.Char(string="Budget ID.")
    categ_id = fields.Char(string="Category ID.")
    category = fields.Char(string="Category")
    code = fields.Char(string="Code")
    desc = fields.Char(string="Description")
    budget = fields.Float(string="Budget")
    update_date = fields.Date(string="Update Date")

    @api.model_create_multi
    def create(self, vals_list):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for vals in vals_list:
            if not isinstance(vals, dict):
                continue

            if lock_setting and lock_setting.lock_date and vals.get('periode'):
                periode = fields.Date.to_date(vals['periode'])

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records has been Lock: {lock_setting.lock_date}, cannot import pmo dashboard: {periode}"
                    )


            # Validasi double upload
            existing = self.search([('company_id', '=', self.env.company.id), ('periode', '=', periode)], limit=1)

            if existing:
                raise exceptions.ValidationError(
                    f"Records with periode: {periode} is duplicated."
                )

        # update_date = current_date
        vals['update_date'] = fields.Date.context_today(self)

        result = super(RevenueThroughputBudget, self).create(vals_list)
        return result


    def unlink(self):
        lock_setting = self.env['pmo.lock.settings'].search([('company_id', '=', self.env.company.id)], limit=1)

        if not lock_setting:
            raise exceptions.ValidationError(
                f"Lock setting must be setup."
            )

        for rec in self:
            if rec.periode:
                periode = fields.Date.to_date(rec.periode)

                if periode <= lock_setting.lock_date:
                    raise exceptions.ValidationError(
                        f"Records cannot be deleted because has been lock: {lock_setting.lock_date}"
                    )


        return super(RevenueThroughputBudget, self).unlink()


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(RevenueThroughputBudget,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Throughput Budget">
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" readonly="1" />
                                <field name="periode" readonly="1" />
                                <field name="unit" readonly="1" />
                                <field name="idf" readonly="1" />
                                <field name="finance" readonly="1" />
                                <field name="idactual" readonly="1" />
                                <field name="idbudget" readonly="1" />
                            </group>
                            <group>
                                <field name="categ_id" invisible="1" readonly="1" />
                                <field name="category" readonly="1" />
                                <field name="code" readonly="1" />
                                <field name="desc" readonly="1" />
                                <field name="budget" readonly="1" />
                                <field name="update_date" readonly="1" />
                            </group>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Throughput Budget">
                    <field name="periode"/>
                    <field name="finance"/>
                    <field name="idactual"/>
                    <field name="category"/>
                    <field name="code"/>
                    <field name="desc" />
                    <field name="budget" />
                    <field name="company_id" />
                    <field name="update_date" />
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class PmoLockSettings(models.Model):
    _name = 'pmo.lock.settings'
    _rec_name = 'company_id'
    _description = "Lock Settings"

    @api.model
    def _get_company(self):
        return self.env.company.id
			
    company_id = fields.Many2one('res.company',string="Company",default=_get_company)
    lock_date = fields.Date(string="Lock Date")


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(PmoLockSettings,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Lock Settings">
                    <sheet>
                        <group>
                            <field name="company_id" required="1" />
                            <field name="lock_date" required="1" />
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Lock Settings">
                    <field name="company_id"/>
                    <field name="lock_date"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res