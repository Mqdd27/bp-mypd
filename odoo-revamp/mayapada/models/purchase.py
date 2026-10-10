from odoo.exceptions import AccessError, UserError
from odoo.tools.float_utils import float_is_zero, float_compare

import logging
from odoo.tools import float_round
import copy
import requests
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
from datetime import datetime, timedelta
try:
    from multiprocess import Process, Manager
except:
    from threading import Thread as Process
from odoo import models, fields, api, tools, exceptions, _
import requests
import json
try:
    import ujson as JSON
except:
    import json as JSON

from . import sync
from . import misc

import itertools
from xml.etree import ElementTree
from operator import itemgetter


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'
    _rec_name = 'title'
    #_sql_constraints = [('sync_id_api_unique', 'unique(sync_type, sync_id_api)', 'Can not be duplicate value for sync_id_api')]

    # @api.multi
    def primary_uom(self):
        for line in self.sudo().order_line:
            line.compute_primary_uom()

    # @api.multi
    def secondary_uom(self):
        for line in self.sudo().order_line:
            line.compute_secondary_uom()

    @api.depends('order_line.price_subtotal')
    def _compute_taxes(self):
        for order in self:
            amount_pph = amount_ppn = 0.0
            for line in order.order_line:
                for tax in line.taxes_id:
                    taxes = tax._compute_amount(round(line.price_unit * line.product_qty - line.discount_total), line.price_unit, line.product_qty, product=line.product_id, partner=order.partner_id)
                    if 'PPH' in (tax.name).upper():
                        amount_pph += taxes
                    elif 'PPN' in (tax.name).upper():
                        amount_ppn += taxes
                    elif 'PB' in (tax.name).upper():
                        amount_ppn += taxes
            order.update({'pph': amount_pph,'ppn': amount_ppn})

    ##################Update#####################
    def _compute_receiving(self):
        for order in self:
            receivings = self.env['stock.receiving']
            for line in order.order_line:
                # We keep a limited scope on purpose. Ideally, we should also use move_orig_ids and
                # do some recursive search, but that could be prohibitive if not done correctly.
                moves = line.receiving_line_ids
                receivings |= moves.mapped('receiving_id')
            order.receiving_ids = receivings
            order.receiving_count = len(receivings)


    ##################Update#####################
    def _compute_receiving(self):
        for order in self:
            receivings = self.env['stock.receiving']
            for line in order.order_line:
                # We keep a limited scope on purpose. Ideally, we should also use move_orig_ids and
                # do some recursive search, but that could be prohibitive if not done correctly.
                moves = line.receiving_line_ids
                receivings |= moves.mapped('receiving_id')
            order.receiving_ids = receivings
            order.receiving_count = len(receivings)


    ##################Update#####################
    def _compute_srb_temporary(self):
        for order in self:
            srb_temporarys = self.env['srb.temporary']
            for line in order.order_line:
                # We keep a limited scope on purpose. Ideally, we should also use move_orig_ids and
                # do some recursive search, but that could be prohibitive if not done correctly.
                moves = line.srb_temporary_ids
                srb_temporarys |= moves
            order.srb_temporary_ids = srb_temporarys
            order.srb_temporary_count = len(srb_temporarys)




    ##################Update#####################
    def _compute_grn_temporary(self):
        for order in self:
            grn_temporarys = self.env['grn.temporary']
            for line in order.order_line:
                # We keep a limited scope on purpose. Ideally, we should also use move_orig_ids and
                # do some recursive search, but that could be prohibitive if not done correctly.
                moves = line.grn_temporary_ids
                grn_temporarys |= moves
            order.grn_temporary_ids = grn_temporarys
            order.grn_temporary_count = len(grn_temporarys)



    @api.depends('order_line.price_total')
    def _amount_all(self):
        for order in self:
            amount_untaxed = amount_tax = 0.0
            for line in order.order_line:
                amount_untaxed += line.price_subtotal
                # FORWARDPORT UP TO 10.0
                if order.company_id.tax_calculation_rounding_method == 'round_globally':
                    taxes = line.taxes_id.compute_all(line.price_unit - line.discount_value, line.order_id.currency_id, line.product_qty, product=line.product_id, partner=line.order_id.partner_id)
                    amount_tax += sum(t.get('amount', 0.0) for t in taxes.get('taxes', []))
                else:
                    amount_tax += line.price_tax
                order.update({
                    'amount_untaxed':order.currency_id.round(amount_untaxed),
                    'amount_tax':order.currency_id.round(amount_tax),
                    'amount_total':amount_untaxed + amount_tax,
                })

    # 2021.09.30 - return current user_id        
    @api.model
    def _get_user(self):
        return self.requisition_id.user_id.id if self.requisition_id else self.env.user.id



    @api.depends('order_line.variance_total')
    def _compute_variance_header_total(self):
        for order in self:
            variance_header_total = 0
            for line in order.order_line:
                variance_header_total += line.variance_total
            order.variance_header_total = variance_header_total



    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type

    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    sync_consol_sent = sync.consol_sent
    sync_is_arcus = sync.is_arcus
    sync_consol_response_status = sync.consol_response_status
    sync_consol_response = sync.consol_response
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")

    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    partner_id = fields.Many2one('res.partner', string='Vendor', change_default=False, domain="[('supplier','=',True), ('company_id', '=', context.get('company_id'))]", help="You can find a vendor by its Name, TIN, Email or Internal Reference.")
    sync_purchase_type = fields.Char(string="Purchase Type", index=True)
    item_type = fields.Selection([('1', 'CAPEX & OPEX'),('3', 'Medis (Stock)'),('5', 'Non Medis (Stock)')], default='1', string='Item Type',required=False)
    sync_rate_contract = fields.Char(string="Rate Contract")
    vendor_ref = fields.Char(string="Ref Number", index=True)
    po_from = fields.Selection([('purchase', 'Purchase'), ('grn', 'GRN')],string="Purchase from")
    is_consignment = fields.Boolean(string="Consignment",readonly=False,default=False,index=True)
    type_id = fields.Many2one('purchase.type',string="Approval Type",required=False,domain=[('purchase_type', '=', 'po')])
    approve_id = fields.Many2one('purchase.approval',string="Approval Level Rule",readonly=True,compute='_approval',store=False,copy=False)
    approve_rule_id = fields.Many2one('purchase.approval.rule',string="Status App",readonly=True,store=True,copy=False)
    approve_status = fields.Char(string="Approval Status",readonly=True,related='approve_rule_id.position_id.name',store=True,copy=False)
    approve_next = fields.Char(string="Next Approval",readonly=True,compute='_approval',store=False,copy=False)
    approve_next_store = fields.Char(string="Stored Next Approval",readonly=False,store=True,index=True)
    remarks = fields.Char(string="Cancel Remarks")
    title = fields.Char(string="Title",readonly=True,compute='_title',store=True,copy=False)
    purchase_name = fields.Char(string="Purchase Number",readonly=True,copy=False)
    rfq = fields.Char(string="RFQ Number", readonly=True, index=True)
    revisi = fields.Boolean(string="Revisi", readonly=True)
    confirm_by = fields.Char(string="Confirmed By", readonly=True)
    revisi_name = fields.Char(string="Revisi Name", readonly=True)
    title_tampilan = fields.Char(string="Title", compute='_title_tampilan', readonly=True)
    no_approval = fields.Boolean(string="No Approval",readonly=False,index=True)
    revisi_sequence = fields.Integer(string="Revisi Sequence", readonly=True)
    updated_date = fields.Boolean(string="Update Date",readonly=True,default=False)
    ppn = fields.Float(string="PPN",store=True,readonly=True, compute='_compute_taxes')
    pph = fields.Float(string="PPh",store=True,readonly=True,compute='_compute_taxes')
    bill_date = fields.Date(string="Bill Date", index=True)
    wipro_date = fields.Date(string="HIS GRN Date", index=True, store=True)
    wipro_type = fields.Char(string="HIS Transaction Type",index=True,store=True)
    due_day = fields.Integer(string="HIS Due Day", required=False)
    requisition_id = fields.Many2one('purchase.requisition',string='Purchase Request',copy=False)
    dp_value = fields.Float(string="DP Amount")
    end_approval = fields.Char(string="End Approval",compute="_get_end_approval")
    state = fields.Selection([('draft', 'RFQ'), ('sent', 'RFQ Sent'),('to approve', 'To Approve'),('purchase', 'Purchase Order'),('done', 'Close Bill'), ('cancel', 'Cancelled')],string='State',readonly=True,index=True,copy=False,default='draft',tracking=True)
    status = fields.Selection([('draft', 'RFQ'), ('sent', 'RFQ Sent'),('to approve', 'To Approve'),('waiting', 'Waiting for Approval'),('approved', 'Approved'),('purchase', 'Purchase Order'),('done', 'Close Bill'),('cancel', 'Cancelled')],string='Status Approval',readonly=True,compute='_status',store=False)
    total_discount = fields.Float(compute="_compute_discount", store=True)
    total_tampilan = fields.Float(string="Untaxed Amount",compute='_compute_discount',store=True)
    is_return = fields.Boolean(string="Is Return", store=True)

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")

    # auto compute relation to stock.picking and stock.move for valuation price
    receipt_location_id = fields.Many2one('stock.location', string="HIS Receipt Location")
    procurement_group_id = fields.Many2one('procurement.group', string="Procurement Group")
    procurement_created = fields.Boolean(string="Procurement Created", default=False)

    # 2021.09.30 - validasi analytic_ids jika buat RFQ/PO manual oleh user.
    user_id = fields.Many2one('res.users', string="Responsible (PR)", readonly=False)
    user_po_id = fields.Many2one('res.users', string='Responsible (RFQ/PO)', default=_get_user, store=True)
    analytic_ids = fields.Many2many('account.analytic.account', store=False, string="Analytic Users")
    invoice_status = fields.Selection([
        ('no', 'Nothing to Bill'),
        ('to invoice', 'Waiting Bills'),
        ('invoiced', 'Bills Received'),
        ], string='Billing Status', compute='_get_invoiced', store=True, readonly=True, copy=False, default='no')

    vendor_char = fields.Char(string="Vendor Char")

    #Sync Arcus
    purchase_date = fields.Date(string="Purchase Date", index=True)
    challan_no = fields.Char(string="Challan No.",index=True,store=True)
    receipt_type = fields.Char(string="Receipt Type",index=True,store=True)
    status_grn = fields.Char(string="Status GRN",index=True,store=True)
    status_grn_arcus = fields.Char(string="Status GRN Arcus",index=True,store=True)
    state_arcus = fields.Char(string="State Arcus",index=True,store=True)
    
    active = fields.Boolean(string="Active", default=True)
    purchase_grn = fields.Many2one('purchase.order', string="Purchase GRN")
    grn_modified = fields.Boolean(string="GRN Modified?")
    grn_has_modified = fields.Boolean(string="GRN Has Been Modified?")
    variance_header_total = fields.Float(string="Variance Header Total",compute="_compute_variance_header_total")
    account_move_id = fields.Many2one('account.move', string="Account Move ID")
    is_validate_grn_modification = fields.Boolean(string="Is Validate GRN Modification?")
    grn_history_ids = fields.Many2many('purchase.order', 'purchase_order_grn_detail_rel', 'purchase_id', 'grn_detail_id', string='GRN History 2')


    ####################Update#####################
    picking_count = fields.Integer(compute='_compute_picking', string='Receptions', default=0)
    receiving_count = fields.Integer(compute='_compute_receiving', string='Receiving', default=0)
    receiving_ids = fields.Many2many('stock.receiving', compute='_compute_receiving', string='Receivings', copy=False)
    srb_temporary_count = fields.Integer(compute='_compute_srb_temporary', string='SRB Temporary', default=0)
    srb_temporary_ids = fields.Many2many('srb.temporary', compute='_compute_srb_temporary', string='SRB Temporarys', copy=False)
    grn_temporary_count = fields.Integer(compute='_compute_grn_temporary', string='GRN Temporary', default=0)
    grn_temporary_ids = fields.Many2many('grn.temporary', compute='_compute_grn_temporary', string='GRN Temporarys', copy=False)
    down_payment_ids = fields.One2many('account.invoice', 'purchase_dp_id', string="Down Payment")
    down_payment_count = fields.Integer(compute="_compute_down_payment", string='# of DP', copy=False, default=0)
    is_po_completed = fields.Boolean(string="Is PO Completed", readonly=True)
    is_ask_approval = fields.Boolean(string="Is Ask Approval?", default=False, readonly=True)
    vendor_bill_count = fields.Integer(compute="_compute_invoice_new", string='Bill Count', copy=False, default=0)
    vendor_bill_ids = fields.Many2many('account.invoice', compute="_compute_invoice_new", string="Bills", copy=False)
    is_grn_done = fields.Boolean(string="Is GRN Done")
    is_srb_done = fields.Boolean(string="Is SRB Done")
    

    active = fields.Boolean(string="Active", default=True)
    purchase_grn = fields.Many2one('purchase.order',string="Purchase GRN",domain=['&','|',('sync_id_api', '!=', False),('sync_id', '!=', False),('invoice_status', '!=', 'invoiced')])

    grn_modified = fields.Boolean(string="GRN Modified?")
    grn_has_modified = fields.Boolean(string="GRN Has Been Modified?")
    variance_header_total = fields.Float(string="Variance Header Total",compute="_compute_variance_header_total")
    account_move_id = fields.Many2one('account.move', string="Account Move ID")
    grn_history_ids = fields.Many2many('purchase.order', 'purchase_order_grn_detail_rel', 'purchase_id', 'grn_detail_id', string='GRN History 2')
    
    payable_invoice_id = fields.Many2one('payable.invoice', string="AP Invoice")
    is_validate_grn_modification = fields.Boolean(string="Is Validate GRN Modification?")
    
    date_order = fields.Datetime('Order Deadline', required=True, index=True, copy=False, default=fields.Datetime.now, help="Depicts the date within which the Quotation should be confirmed and converted into a purchase order.")
    partner_id = fields.Many2one('res.partner', string='Vendor', required=True, change_default=True, tracking=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]", help="You can find a vendor by its Name, TIN, Email or Internal Reference.")
    currency_id = fields.Many2one('res.currency', 'Currency', required=True,default=lambda self: self.env.company.currency_id.id)
    company_id = fields.Many2one('res.company', 'Company', required=True, index=True, default=lambda self: self.env.company.id)
    pending_request_date = fields.Datetime(string="Pending RFQ Date")
    

    def action_send_rfq_email(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
    
        for rec in self:
            notification_setting = rec.sudo().env['purchase.notification.setting'].search(
                [('company_id', '=', rec.company_id.id)], limit=1)
            if not notification_setting:
                raise UserError(_("Notification Setting Not Found."))

            recipient_emails = notification_setting.user_ids.mapped('partner_id.email')

            if not recipient_emails:
                raise UserError(_("Selected users have no email addresses."))

            pr_url = f"{base_url}/web#id={rec.id}&model={rec._name}&view_type=form"


            body_html = f"""
                <p>Dear Procurement,</p>
                <p>Silahkan proses RFQ yang telah anda buat, klik tombol "Ask Approval" untuk memulai proses approval pada RFQ, atau klik "Cancel Call" untuk membatalkan RFQ jika sudah tidak digunakan kembali.</p>
                <p>
                    <a href="{pr_url}" target="_blank" style="
                        display: inline-block;
                        padding: 10px 20px;
                        background-color: #1abc9c;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        font-weight: bold;">
                        {rec.name}
                    </a>
                </p>
                <p>Terima kasih.</p>
            """

            mail_values = {
                'subject': f'Notification Odoo: {rec.name}',
                'body_html': body_html,
                'email_from': 'odoo@mayapadahospital.com',
                'email_to': ','.join(recipient_emails),
                'auto_delete': True,
                'model': rec._name,
                'res_id': rec.id,
            }

            rec.env['mail.mail'].create(mail_values).send()
            rec.pending_request_date = tools.datetime.now()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Email sent to: {", ".join(recipient_emails)}',
                'type': 'success',
                'sticky': False,
            }
        }





    # @api.multi
    def open_validation_wizard(self):
        self.ensure_one()
        return {
            'name': _('Confirm Validation'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order.validation.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('mayapada.view_purchase_order_validation_wizard_form').id,
            'target': 'new',
            'context': {'default_purchase_id': self.id},
        }


    # @api.multi
    def validate_modification(self):
        self.ensure_one()

        journal = self.env['account.journal'].sudo().search([
            ('name', '=', 'GRN Modification'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)

        if not journal:
            raise UserError(_("Journal GRN Modification Tidak Ditemukan"))


        account_ap_not_invoice = self.env['account.account'].sudo().search([
            ('code', '=', '2102060000'), ('company_id', '=', self.company_id.id)
        ], limit=1)


        if not account_ap_not_invoice:
            raise UserError(_("Chart Of Account AP Not Invoice Tidak Ditemukan"))


        move_lines = []
        skip_keywords = ('CGN', 'CGI', 'CGBP', 'KN-', 'CL-')
        for line in self.order_line:
            default_code = (line.product_id.default_code or '').upper()
            if any(keyword in default_code for keyword in skip_keywords):
                continue


            account_stock_output = (
                line.product_categ_id.stock_output_id or
                line.product_id.product_tmpl_id.categ_id.stock_output_id
            )

            if not account_stock_output:
                raise UserError(_("Tidak ditemukan 'Stock Output Account' pada kategori produk: %s") % (
                    line.product_categ_id.name or line.product_id.product_tmpl_id.categ_id.name or 'Tidak diketahui'
                ))
            

            if line.variance_total >= 0:
                debit_account_id = account_stock_output
                credit_account_id = account_ap_not_invoice
            else:
                credit_account_id = account_stock_output
                debit_account_id = account_ap_not_invoice

            move_lines.append((0, 0, {
                'account_id': debit_account_id.id,
                'name': line.name,
                'debit': abs(line.variance_total),
                'credit': 0.0,
            }))

            move_lines.append((0, 0, {
                'account_id': credit_account_id.id,
                'name': line.name,
                'debit': 0.0,
                'credit': abs(line.variance_total),
            }))

        if not move_lines:

            self.is_validate_grn_modification = True
            return True
            # raise UserError(_("Tidak ada baris yang valid untuk dimodifikasi (semua mengandung 'CGN')."))
            
        move_vals = {
            'journal_id': journal.id,
            'date': fields.Date.today(),
            'ref': self.name,
            'line_ids': move_lines,
        }

        move = self.env['account.move'].create(move_vals)

        # Optional: post the move
        move.action_post()

        # Link it to purchase.order
        self.account_move_id = move.id
        self.is_validate_grn_modification = True
            
        return True





    @api.depends('order_line.variance_total')
    def _compute_variance_header_total(self):
        for order in self:
            variance_header_total = 0
            for line in order.order_line:
                variance_header_total += line.variance_total
            order.variance_header_total = variance_header_total


    @api.depends('order_line.move_ids')
    def _compute_picking(self):
        for order in self:
            pickings = self.env['stock.picking']
            for line in order.order_line:
                # We keep a limited scope on purpose. Ideally, we should also use move_orig_ids and
                # do some recursive search, but that could be prohibitive if not done correctly.
                moves = line.move_ids | line.move_ids.mapped('returned_move_ids')
                moves = moves.filtered(lambda r: r.state != 'cancel')
                pickings |= moves.mapped('picking_id')
            order.picking_ids = pickings
            order.picking_count = len(pickings)
            
    @api.depends('order_line.invoice_lines.invoice_id.state')
    def _compute_down_payment(self):
        for order in self:
            order.down_payment_count = len(self.down_payment_ids)


    @api.depends('order_line.vendor_bill_lines.invoice_id.state')
    def _compute_invoice_new(self):
        for order in self:
            invoices = self.env['account.invoice']
            for line in order.order_line:
                invoices |= line.vendor_bill_lines.mapped('invoice_id')
            order.vendor_bill_ids = invoices
            order.vendor_bill_count = len(invoices)

    @api.depends('order_line.invoice_lines.invoice_id.state')
    def _compute_vendor_bill(self):
        for order in self:
            order.vendor_bill_count = len(self.vendor_bill_ids)
            
    # 2021.10.13 - override invoice_status
    @api.depends('state', 'order_line.qty_invoiced', 'order_line.qty_received', 'order_line.product_qty')
    def _get_invoiced(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for order in self:
            if order.state not in ('purchase', 'done'):
                
                if order.sync_id or order.sync_id_api:
                    
                    order.invoice_status = 'to invoice'
                else:
                    
                    order.invoice_status = 'no'
                continue

            if any(float_compare(line.qty_invoiced, line.product_qty if line.product_id.purchase_method == 'purchase' else line.qty_received, precision_digits=precision) == -1 for line in order.order_line):
                
                order.invoice_status = 'to invoice'
            elif all(float_compare(line.qty_invoiced, line.product_qty if line.product_id.purchase_method == 'purchase' else line.qty_received, precision_digits=precision) >= 0 for line in order.order_line) and order.vendor_bill_ids:
                
                order.invoice_status = 'invoiced'
            else:
                
                order.invoice_status = 'no'

                
    # @api.depends('requisition_id','user_id','order_line')
    # @api.onchange('requisition_id','user_id','order_line')
    # def _change_analytic_domain(self):
    #     for record in self:
    #         if not record.user_id:
    #             if record.requisition_id:
    #                 record.user_id = record.requisition_id.user_id.id 
    #             else:
    #                 record.user_id = self.env.user.id 

    #         if record.order_line:
    #             for line in record.order_line:
    #                 line._change_analytic_domain(record.analytic_ids.ids)


    # @api.multi
    # def action_view_picking(self):
    #     '''
    #     This function returns an action that display existing picking orders of given purchase order ids.
    #     When only one found, show the picking immediately.
    #     '''
    #     action = self.env.ref('stock.action_picking_tree')
    #     result = action.read()[0]

    #     #override the context to get rid of the default filtering on picking type
    #     result.pop('id', None)
    #     result['context'] = {}
    #     pick_ids = sum([order.picking_ids.ids for order in self], [])
    #     #choose the view_mode accordingly
    #     if len(pick_ids) > 1:
    #         result['domain'] = "[('id','in',[" + ','.join(map(str, pick_ids)) + "])]"
    #     elif len(pick_ids) == 1:
    #         res = self.env.ref('stock.view_picking_form', False)
    #         result['views'] = [(res and res.id or False, 'form')]
    #         result['res_id'] = pick_ids and pick_ids[0] or False
    #     return result

    ########################update
    # @api.multi
    def action_view_receiving(self):
        # action = self.env.ref('stock.action_picking_tree')
        # result = action.read()[0]
        result = {}
        result['target'] = 'current'

        #override the context to get rid of the default filtering on picking type
        # result.pop('id', None)
        # result['context'] = {}
        receive_ids = sum([order.receiving_ids.ids for order in self], [])
        #choose the view_mode accordingly
        if len(receive_ids) > 1:
            res = self.env.ref('mayapada.stock_receiving_tree_action', False)
            result['views'] = [(res and res.id or False, 'tree')]
            result['domain'] = "[('id','in',[" + ','.join(map(str, receive_ids)) + "])]"
            result['type'] = 'ir.actions.act_window'
            result['view_mode'] = 'tree,form'
            result['view_type'] = 'form'
            result['name'] = 'Stock Receiving'
            result['res_model'] = 'stock.receiving'
        elif len(receive_ids) == 1:
            res = self.env.ref('mayapada.stock_receiving_form_action', False)
            result['views'] = [(res and res.id or False, 'form')]
            result['res_id'] = receive_ids and receive_ids[0] or False
            result['type'] = 'ir.actions.act_window'
            
            result['res_model'] = 'stock.receiving'
        return result




    ########################update
    # @api.multi
    def action_view_receiving(self):
        '''
        This function returns an action that display existing picking orders of given purchase order ids.
        When only one found, show the picking immediately.
        '''
        action = self.env.ref('mayapada.stock_receiving_action')
        result = action.read()[0]

        #override the context to get rid of the default filtering on picking type
        result.pop('id', None)
        if self.is_po_completed == True:
            result['context'] = {}
        else:
            result['context'] = {'default_purchase_id': self.id}
        receive_ids = sum([order.receiving_ids.ids for order in self], [])
        #choose the view_mode accordingly
        if len(receive_ids) > 1:
            result['domain'] = "[('id','in',[" + ','.join(map(str, receive_ids)) + "])]"
        elif len(receive_ids) == 1:
            res = self.env.ref('mayapada.stock_receiving_form_action', False)
            result['views'] = [(res and res.id or False, 'form')]
            result['res_id'] = receive_ids and receive_ids[0] or False
        return result


    # @api.multi
    def send_api_consol(self):
        for record in self:
            if record.env.company.sync_consol_purchase_order:
                if record.env.company.sync_consol_type == 'unit':
                    url = record.env.company.sync_consol_url + "/internal_api/unit/create/purchase.order"
                if record.env.company.sync_consol_type == 'main':
                    url = record.env.company.sync_consol_url + "/internal_api/main/create/purchase.order"

                if not record.env.user.token_consol:
                    # record.env.user.auth_api_consol()
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)

                headers = {}
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = {}
                body['csrf_token'] = record.env.user.token_consol
                array_values = []
                values = {}
                values['sync_type'] = record.env.company.sync_type
                values['sync_id_consol_unit'] = record.id
                values['name'] = record.name
                values['title'] = record.title
                values['is_consignment'] = record.is_consignment
                values['partner_id'] = record.partner_id.id
                values['vendor_ref'] = record.vendor_ref
                values['date_order'] = record.date_order
                values['no_approval'] = record.no_approval
                values['date_planned'] = record.date_planned
                values['state'] = record.state
                array_values.append(values)
                body['values'] = array_values

                print("body : " + str(body))
                print("headers : " + str(headers))
                print("url : " + str(url))

                # response_json = requests.post(url=url, headers=headers, data=body, verify=False)
                # json_resp = response_json.json()
                # api_status = 'failed'
                # if 'status' in json_resp:
                #     if json_resp['status'] == 'success':
                #         api_status = 'success'
                # data = {
                #     'api_post_payload': body,
                #     'api_post_response': json_resp,
                #     'api_status': api_status,
                #     'sync_consol_date': now
                #     }
                # super(PurchaseOrder, self).write(data)


    # @api.multi
    def function_consol(self, function=False):
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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'function' + '/' + 'purchase.order' + '/'
        log_name = log_date + '_' + 'function' + '_' + 'purchase.order'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Function "

        open(log_file, 'a').write(message_log)
        for record in self:
            if not record.sync_id and not record.sync_id_api:
                consol_active = record.company_id.sync_consol_purchase_order
                consol_url = record.company_id.sync_consol_url
                consol_type = record.company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                name_function = function
                if consol_active and consol_type == 'main':
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/call_function/unit/purchase.order"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/call_function/main/purchase.order"
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
                    query = """
                        update res_users set company_id = (select(id) from res_company where name = '{company_name}') where id = {sync_consol_id_main}
                        """.format(company_name=self.env.company.name, sync_consol_id_main=int(self.env.user.sync_consol_id_main))
                    body['query'] = query
                    company_name = record.company_id.name
                    sync_consol_id_main = str(self.env.user.login)
                    body['company_name'] = company_name
                    
                    body['user_id'] = sync_consol_id_main
                    body['function'] = name_function
                    cookies = {'session_id': self.env.user.cookies}
                    print(body)
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    json_resp = response_json.json()
                    # self.env.user.sync_consol_response = json_resp
                    log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
                    message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
                    message_log += "\n\nuser: " + self.env.user.login + "\n\n End Function"

                    open(log_file, 'a').write(message_log)


################Update
    # 2021.10.05 - modifikasi saat confirm_po untuk create picking
    # @api.multi
    def button_approve(self, force=False):
        self.write({'state': 'purchase', 'date_approve': fields.Date.context_today(self)})
        # jika bukan PO dari HIS maka buat picking/GRN/Shipment
        if not self.sync_id and not self.sync_id_api:
            
            #self._create_picking()
            self._create_receiving()
            
        print ('a')
        self.filtered(lambda p: p.company_id.po_lock == 'lock').write({'state': 'done'})
        return {}

################Update
    # @api.multi
    def _create_receiving(self):
        StockReceiving = self.env['stock.receiving']
        for order in self:
            if any([ptype in ['product', 'consu'] for ptype in order.order_line.mapped('product_id.type')]):
        
                receivings = order.receiving_ids.filtered(lambda x: x.state not in ('done','cancel'))
                if not receivings:
        
                    res = order._prepare_receiving()
                    receiving = StockReceiving.create(res)
                    open('/opt/odoo16/logs/stock_picking.log','a+').write('\n\n'+str(res))
                else:
        
                    receiving = receivings[0]
                moves = order.order_line._create_receiving_line(receiving)
                
        return True

###############Update
    @api.model
    def _prepare_receiving(self):
        # if not self.group_id:
        #     if self.company_id.company_code:
        #         group_name = self.company_id.company_code + '/' + self.name
        #     else:
        #         group_name = self.name

        #     self.group_id = self.group_id.create({
        #         'name': group_name,
        #         'partner_id': self.partner_id.id
        #     })

        # if not self.partner_id.property_stock_supplier.id:
        #     raise UserError(_("You must set a Vendor Location for this partner %s") % self.partner_id.name)


        # Komen TES
        from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
        from datetime import datetime
        import os
        #if self.purchase_name and self.purchase_name != self.name:
        #    # origin_name = self.name + ' ('+self.purchase_name+')' 
        #    origin_name = self.name or '-'
        #else:
        #    origin_name = self.name or '-'

        origin_name = '-'
        return {
            'purchase_id': self.id,
            'partner_id': self.partner_id.id,
            'purchase_date' : self.wipro_date or self.date_order,
            'date' : datetime.now(),
            'ref': origin_name,
            'company_id': self.company_id.id,
        }



    # 2021.10.05 - redefined _create_picking
    # @api.multi
    def _create_picking(self):
        StockPicking = self.env['stock.picking']
        for order in self:
            if any([ptype in ['product', 'consu'] for ptype in order.order_line.mapped('product_id.type')]):
                pickings = order.picking_ids.filtered(lambda x: x.state not in ('done','cancel'))
                if not pickings:
                    res = order._prepare_picking()
                    picking = StockPicking.create(res)
                    open('/opt/odoo16/logs/stock_picking.log','a+').write('\n\n'+str(res))
                else:
                    picking = pickings[0]
                moves = order.order_line._create_stock_moves(picking)
                moves = moves.filtered(lambda x: x.state not in ('done', 'cancel')).action_confirm()
                seq = 0
                for move in sorted(moves, key=lambda move: move.date_expected):
                    seq += 5
                    move.sequence = seq
                moves.force_assign()
                picking.message_post_with_view('mail.message_origin_link',
                    values={'self': picking, 'origin': order},
                    subtype_id=self.env.ref('mail.mt_note').id)
        return True


    # 2021.10.06 - redefined _prepare_stock_picking
    @api.model
    def _prepare_picking(self):
        if not self.group_id:
            if self.company_id.company_code:
                group_name = self.company_id.company_code + '/' + self.name
            else:
                group_name = self.name

            self.group_id = self.group_id.create({
                'name': group_name,
                'partner_id': self.partner_id.id
            })

        if not self.partner_id.property_stock_supplier.id:
            raise UserError(_("You must set a Vendor Location for this partner %s") % self.partner_id.name)

        if self.purchase_name and self.purchase_name != self.name:
            # origin_name = self.name + ' ('+self.purchase_name+')' 
            origin_name = self.name
        else:
            origin_name = self.name

        return {
            'picking_type_id': self.picking_type_id.id,
            'partner_id': self.partner_id.id,
            'date': self.date_order,
            'origin': origin_name,
            'location_dest_id': self._get_destination_location(),
            'location_id': self.partner_id.property_stock_supplier.id,
            'company_id': self.company_id.id,
            'po_id': self.id
        }



    # @api.multi
    def button_done(self):
        self.function_consol(function="button_done_consol")
        record = super(PurchaseOrder, self).button_done()
        if self.requisition_id.state in ['done', 'open']:
            self.requisition_id.state = 'in_progress'

    # @api.multi
    def button_done_consol(self):
        record = super(PurchaseOrder, self).button_done()
        if self.requisition_id.state in ['done', 'open']:
            self.requisition_id.state = 'in_progress'

    # @api.multi
    def button_cancel(self):
        self.function_consol(function="button_cancel_consol")

        #############################Update
        for order in self:
            if order.is_po_completed == True:
                raise UserError(_('Unable to cancel purchase order %s because already set to Completed.') % (order.name))

            if order.srb_temporary_ids:
                raise UserError(_('Unable to cancel purchase order %s because already SRB.') % (order.name))
            if order.grn_temporary_ids:
                raise UserError(_('Unable to cancel purchase order %s because already GRN.') % (order.name))

            for receive in order.receiving_ids:
                if receive.state == 'posted':
                    raise UserError(_('Unable to cancel purchase order %s as some receiving have already been posted.') % (order.name))
                if receive.state == 'confirmed':
                    raise UserError(_('Unable to cancel purchase order %s as some receiving have already been confirmed.') % (order.name))
            
            for receive in order.receiving_ids.filtered(lambda r: r.state != 'cancel'):
                receive.action_line_cancel()
        record = super(PurchaseOrder, self).button_cancel()
        self.approve_rule_id = False
        self.approve_next_store = False
        if self.requisition_id.state in ['done', 'open']:
            self.requisition_id.state = 'in_progress'

        now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
        partner_id_check_list = []
        if self.user_id:
            user_id = self.user_id.id
        elif self.requisition_id.user_id:
            user_id = self.requisition_id.user_id.id
        else:
            user_id = self.env.user.id
        partner_id_check = self.env['res.users'].sudo().search([('id', '=', user_id)]).partner_id.id

        if partner_id_check:

            partner_id_check_list.append(partner_id_check)
            notification_ids = [((0, 0, {'res_partner_id': partner_id_check,'notification_type': 'email'}))]    
            self.message_post(body='This PO is Cancelled by ' +self.env.user.name + " at " + now,message_type='notification',content_subtype='plaintext', subtype_id=False,notification_ids=notification_ids,partner_ids=partner_id_check_list,notify_by_email=True)
        else:
             self.message_post(body='This PO is Cancelled by ' +self.env.user.name + " at " + now,message_type='notification',content_subtype='plaintext', subtype_id=False)
        #cost_center = self.order_line.mapped('account_analytic_id.id')
        #for cc in cost_center:
        #    cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
        #    date = (tools.datetime.strptime(self.date_order, '%Y-%m-%d %H:%M:%S')).strftime('%Y-%m-%d')
        #    if self.company_id.cost_center_active == True:
        #        if not self.company_id.cost_center_date or not date:
        #            raise UserError(_("Tanggal tidak boleh kosong."))
        #    if self.company_id.cost_center_active == True and self.company_id.cost_center_date <= date:
        #        budget_used = self.env['crossovered.budget.lines'].sudo().search([
        #            ('analytic_account_id', '=', cc),
        #            ('crossovered_budget_id.state','in', ['validate','done']),
        #            ('date_from', '<=',date),
        #            ('date_to', '>=',date)])
        #        if budget_used:
        #            budget_used.budget_line_compute_balance()

    # @api.multi
    def button_cancel_consol(self):

        #############################Update
        for order in self:
            if order.is_po_completed == True:
                raise UserError(_('Unable to cancel purchase order %s because already set to Completed.') % (order.name))
            for receive in order.receiving_ids:
                if receive.state == 'posted':
                    raise UserError(_('Unable to cancel purchase order %s as some receiving have already been posted.') % (order.name))
                if receive.state == 'confirmed':
                    raise UserError(_('Unable to cancel purchase order %s as some receiving have already been confirmed. Please cancel first.') % (order.name))
            for receive in order.receiving_ids.filtered(lambda r: r.state != 'cancel'):
                receive.action_line_cancel()

        record = super(PurchaseOrder, self).button_cancel()
        self.approve_rule_id = False
        self.approve_next_store = False
        if self.requisition_id.state in ['done', 'open']:
            self.requisition_id.state = 'in_progress'
        #cost_center = self.order_line.mapped('account_analytic_id.id')
        #for cc in cost_center:
        #    cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
        #    date = (tools.datetime.strptime(self.date_order, '%Y-%m-%d %H:%M:%S')).strftime('%Y-%m-%d')
        #    if self.company_id.cost_center_active == True:
        #        if not self.company_id.cost_center_date or not date:
        #            raise UserError(_("Tanggal tidak boleh kosong."))
        #    if self.company_id.cost_center_active == True and self.company_id.cost_center_date <= date:
        #        budget_used = self.env['crossovered.budget.lines'].sudo().search([
        #            ('analytic_account_id', '=', cc),
        #            ('crossovered_budget_id.state','in', ['validate','done']),
        #            ('date_from', '<=',date),
        #            ('date_to', '>=',date)])
        #        if budget_used:
        #            budget_used.budget_line_compute_balance()

    # @api.one
    def _get_end_approval(self):
        record = self.sudo()
        end_approval = ''
        for at in record.type_id.approval_ids:
            if at.min_amount <= record.amount_total and at.max_amount >= record.amount_total:
                for apv in at.rule_ids:
                    if apv.enabled == True:
                        end_approval = apv.position_id.name
        record.end_approval = end_approval


    # @api.multi
    def check_grn(self):
        for line in self.order_line:
            if line.move_ids:
                for move in line.move_ids:
                    if move.state == 'done':
                        line.qty_received = line.product_qty
                        self.invoice_status == 'invoiced'


    @api.constrains('state')
    def _action_cancel(self):
        if self.state == 'cancel' and not self.remarks:
            raise exceptions.ValidationError(_("Fill remarks before cancel"))

    @api.depends('order_line.discount_total')
    def _compute_discount(self):
        for record in self:
            record.total_discount = 0
            record.total_tampilan = 0
            for line in record.order_line:
                record.total_discount += line.discount_total
                record.total_tampilan += line.price_subtotal + line.discount_total
                # record.total_tampilan = 0

    # delivery_date = fields.Datetime(string="Delivery Date")

    @api.model
    def create(self, vals):
        """if self.env.context.get('params') and self.env.context['params'].get('action'):
           open('/opt/odoo16/logs/qu.log', 'w+').write('iya')
           task_id = self.env['sync.task'].sudo().create({'function_ext': 'purchase.order.create', 'args': [vals], 'uid': self.env.user.id})
           task_id.sudo().run()
           return self.new(vals).id"""
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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'purchase.order' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'purchase.order'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        result = super(PurchaseOrder, self).create(vals)

        ###############Update
        # if result.order_id.state == 'purchase':
        #     print 'a'
            #result.order_id._create_picking()
            #msg = _("Extra line with %s ") % (result.product_id.display_name,)
            #result.order_id.message_post(body=msg)

        # tambahan auto fill partnr_ref sesuai yang dikirim docotel partner_ref
        if result.vendor_ref:
            result.partner_ref = result.vendor_ref

        # tambahan auto fill purchase name agar tidak null
        # result.purchase_name = '-'



        if result.purchase_grn:
            #result.purchase_grn.active = False
            result.purchase_grn.grn_has_modified = True
            new_sync_id_api = str(result.purchase_grn.sync_id_api) + " - " + str(result.id)
            result.sync_id_api = new_sync_id_api
            result.state = 'purchase'
            result.name = result.purchase_grn.name
            result.title = result.purchase_grn.title
            result.revisi_sequence = result.purchase_grn.revisi_sequence + 1
            result.revisi_name = 'R' + str(result.revisi_sequence) 

            parent_id = vals.get('purchase_grn')
            if parent_id:
                # force include inactive records
                parent = self.browse(parent_id).with_context(active_test=False)
                history = parent.grn_history_ids.with_context(active_test=False).ids
                result.grn_history_ids = [(6, 0, list(set(history + [parent.id])))]

                parent.active = False   


        result._amount_all()
        if result.requisition_id:
            if result.requisition_id.lock_pr:
                raise UserError(_('You cannot create an RFQ from a locked PR.'))
            if result.trigger_create == False:
                attachment_id = self.env['ir.attachment'].search([('res_model','=', 'purchase.requisition'),('res_id','=',result.requisition_id.id)])
                if attachment_id:
                    for attach in attachment_id:
                        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "attach id PR " + str(attach.id))
                        check_copy = attach.copy()
                        # check_copy.res_model = 'purchase.order'
                        # check_copy.res_id = result.id
                        query = """
                        UPDATE ir_attachment set res_model = 'purchase.order', res_id ='{res_id}'
                        WHERE id = {check_copy}""".format(res_id = result.id, check_copy = check_copy.id)
                        self.env.cr.execute(query)

            if result.trigger_create == True:
                now = (datetime.now() - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK SINI true 33333333333333333 now jam " + str(now))
                attachment_id = self.env['ir.attachment'].search([('res_model','=', 'purchase.requisition'),('res_id','=',result.requisition_id.id),('create_date','>=', now)])
                if attachment_id:
                    for attach in attachment_id:
                        query = """
                        UPDATE ir_attachment set res_model = 'purchase.order', res_id ='{res_id}'
                        WHERE id = {check_copy}""".format(res_id = result.id, check_copy = attach.id)
                        self.env.cr.execute(query)
                #     for attach in attachment_id:
                #         open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "attach id PR true " + str(attach.id))
                #         check_copy = attach.copy()
                #         # check_copy.res_model = 'purchase.order'
                #         # check_copy.res_id = result.id
                #         open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "attach copy id PR true " + str(check_copy.id))
                #         open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "result id true " + str(result.id))
                #         query = """
                #         UPDATE ir_attachment set res_model = 'purchase.order', res_id ='{res_id}'
                #         WHERE id = {check_copy}""".format(res_id = result.id, check_copy = check_copy.id)
                #         self.env.cr.execute(query)
            if result.requisition_id.state == 'in_progress':
                result.requisition_id.action_open()
        if self.env.company.sync_api_active == True:
            if result.date_order:
                #comment udh disetup datetime di os linux app & db, odoo & postgresql sesuai WIB.
                #date_wib = tools.datetime.strptime(result.date_order,'%Y-%m-%d %H:%M:%S') - timedelta(hours=7)
                #result.date_order = date_wib
                result.wipro_date = result.date_order
        if vals.get('company_id'):
            company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
            result.sync_type = company_id.sync_type
            # if company_id.id == 16 and company_id.sync_consol_type == 'main':
            #     raise exceptions.ValidationError("Not Allowed to Create PR/PO for Surabaya, Please Create PR/PO on Odoo MHSB http://10.5.1.79")
            # if company_id.id == 8 and company_id.sync_consol_type == 'unit':
                # raise exceptions.ValidationError("Not Allowed to Create PR/PO for MHTG-Corporate, Please Create PR/PO on Odoo MHTG-Corporate https://erp.ad.mayapadahospital.com")
        if result.trigger_create == False and not result.sync_id and not result.sync_id_api:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger create purchase order")
            result.send_api_consol_company()
            for tes_loop in result.order_line:
                
                tes_loop.send_api_consol_company()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " +str(result.id)

        open(log_file, 'a').write(message_log)
        return result

    # @api.multi
    def send_api_consol_company(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_purchase_order
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/purchase.order"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/purchase.order"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
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
                values['title'] = str(record.title)
                values['name'] = str(record.name)

                if record.company_id.id == False:
                    values['company_id'] = record.company_id.id
                else:
                    values['company_id'] = str(record.company_id.id)

                if record.partner_id.id == False:
                    values['partner_id'] = record.partner_id.id
                else:
                    values['partner_id'] = str(record.partner_id.id)

                values['partner_ref'] = record.partner_ref

                if record.requisition_id.id == False:
                    values['requisition_id'] = record.requisition_id.id
                else:
                    values['requisition_id'] = str(record.requisition_id.id)

                values['rfq'] = record.rfq
                values['remarks'] = record.remarks
                values['dp_value'] = record.dp_value
                values['date_order'] = record.date_order
                values['item_type'] = record.item_type
                if record.origin:
                    values['origin'] = str(record.origin)
                else:
                    values['origin'] = ''

                if record.notes:
                    values['notes'] = str(record.notes)
                else:
                    values['notes'] = ''
                values['no_approval'] = record.no_approval

                if record.type_id.id == False:
                    values['type_id'] = record.type_id.id
                else:
                    values['type_id'] = str(record.type_id.id)
                
                values['trigger_create'] = True
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
                super(PurchaseOrder, self).write(data_update)

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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'purchase.order' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'purchase.order'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        result = super(PurchaseOrder, self).write(vals)
        if self.env.context.get('ganti_date'):
            return result
        self = self.with_context(ganti_date=True)
        # try:
        # self._amount_all()

        if vals.get('company_id'):
            company_id = vals.get('company_id')
        else:
            company_id = self.company_id.id 
            
        if self.env.company.id:
            user_company_id = self.env.company.id
        else:
            user_company_id = company_id
        
        # ambil child dari existing company yg active di user
        child_company_ids = self.env['res.company'].search([('parent_id', '=', self.env.company.id)]).ids
        # loop_ids = child_company_ids
        # looping ambil sub childs per unit
        # for cp in loop_ids:
        sub_company_ids = self.env['res.company'].search([('parent_id', 'in', child_company_ids)]).ids
        child_company_ids += sub_company_ids

        open('/opt/odoo16/logs/purchase_view.log', 'a+').write('\n company_id: ' + str(company_id))
        open('/opt/odoo16/logs/purchase_view.log', 'a+').write('\n child_company_ids: ' + str(child_company_ids))
        open('/opt/odoo16/logs/purchase_view.log', 'a+').write('\n user_company_id: ' + str(user_company_id))
        
        # if company_id is not False:
        #     if company_id != user_company_id and self.env.user.id not in [1] and company_id not in child_company_ids:
        #         raise exceptions.ValidationError("Not allowed to edit PO with different company.")



        if self.env.company.sync_api_active == True:
            
            if vals.get('date_order'):
                #comment udh disetup datetime di os linux app & db, odoo & postgresql sesuai WIB.
                #date_wib = tools.datetime.strptime(str(vals.get('date_order')),'%Y-%m-%d %H:%M:%S')
                #self.date_order = date_wib
                self.date_order = tools.datetime.strptime(str(vals.get('date_order')),'%Y-%m-%d %H:%M:%S')
        # if self.company_id:
        #     self.sync_type = self.company_id.sync_type
        if self.trigger_write == True and not self.sync_id and not self.sync_id_api:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger write purchase order")
            query = """
            UPDATE purchase_order set trigger_write = false
            WHERE id = {self_id}""".format(self_id = self.id)
            self.env.cr.execute(query)
            self.send_api_consol_write_company()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Write before return" + "\n ID: " +str(self.id)

        open(log_file, 'a').write(message_log)
        return result

    # except:
    # import traceback
    # raise UserError(traceback.format_exc())

    # @api.multi
    def send_api_consol_write_company(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_purchase_order
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/purchase.order"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/purchase.order"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
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
                values['title'] = str(record.title)
                values['name'] = str(record.name)

                if record.partner_id.id == False:
                    values['partner_id'] = record.partner_id.id
                else:
                    values['partner_id'] = str(record.partner_id.id)

                values['partner_ref'] = record.partner_ref

                if record.requisition_id.id == False:
                    values['requisition_id'] = record.requisition_id.id
                else:
                    values['requisition_id'] = str(record.requisition_id.id)

                values['rfq'] = record.rfq
                values['remarks'] = record.remarks
                values['dp_value'] = record.dp_value
                values['date_order'] = record.date_order
                values['item_type'] = record.item_type
                if record.origin:
                    values['origin'] = str(record.origin)
                else:
                    values['origin'] = ''

                if record.notes:
                    values['notes'] = str(record.notes)
                else:
                    values['notes'] = ''
                values['no_approval'] = record.no_approval

                if record.type_id.id == False:
                    values['type_id'] = record.type_id.id
                else:
                    values['type_id'] = str(record.type_id.id)
                values['trigger_write'] = False
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
                        # for d in json_resp['data']:
                        #     if 'id' in d:
                        #         response_id = d['id']
                        if json_resp['data']['id']:
                            response_id = json_resp['data']['id']
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
                super(PurchaseOrder, self).write(data_update)

    @api.onchange('sync_type', 'name','partner_id','partner_ref','requisition_id','rfq','remarks','dp_value','date_order','item_type','origin','type_id','no_approval','notes')
    def onchange_trigger_write(self):
        self.trigger_write = True

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        self.vendor_char = self.partner_id.name

    # @api.multi
    def button_draft(self):
        self.function_consol(function="button_draft_consol")
        self.revisi_sequence += 1
        self.state = 'draft'
        self.update({'revisi_name': 'R' + str(self.revisi_sequence)})  #self.env["ir.sequence"].next_by_code("coveringletter.revisi.seq")}

    # @api.multi
    def button_draft_consol(self):
        self.revisi_sequence += 1
        self.state = 'draft'
        self.update({'revisi_name': 'R' + str(self.revisi_sequence)})  #self.env["ir.sequence"].next_by_code("coveringletter.revisi.seq")}

    # @api.multi
    def button_dp(self):
        self.function_consol(function="button_dp_consol")
        dp = self.env['product.product'].search([('name', 'ilike', 'Down payment'),('company_id', '=', self.company_id.id)])
        if not dp:
            raise exceptions.ValidationError("Down payment product in this company not found, please create the product")
        if self.dp_value <= 0.0:
            raise exceptions.ValidationError("Down payment cannot be 0 or less than 0")
        else:
            vals = {
                'product_id': dp.id,
                'name': dp.name,
                'date_planned': self.date_order,
                'product_qty': 1,
                'product_qty2': 1,
                'price_unit': self.dp_value * -1,
                'product_uom': dp.uom_id.id,
                # 'price_unit' : -1,
                'order_id': self.id
            }
            self.env['purchase.order.line'].create(vals)
            self.dp_value = 0


    # @api.multi
    def button_dp_consol(self):

        dp = self.env['product.product'].search([('name', 'ilike', 'Down payment'),('company_id', '=', self.company_id.id)])
        if not dp:
            raise exceptions.ValidationError("Down payment product in this company not found, please create the product")
        if self.dp_value <= 0.0:
            raise exceptions.ValidationError("Down payment cannot be 0 or less than 0")
        else:
            vals = {
                'product_id': dp.id,
                'name': dp.name,
                'date_planned': self.date_order,
                'product_qty': 1,
                'price_unit': self.dp_value * -1,
                'product_uom': dp.uom_id.id,
                # 'price_unit' : -1,
                'order_id': self.id
            }
            self.env['purchase.order.line'].create(vals)
            self.dp_value = 0


    # @api.multi
    def subscribe_approval(self):
        self.ensure_one()
        user_ids = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id),('position_id.name', '=', self.approve_next_store)])
        if user_ids:
            self.sudo().message_subscribe_users(user_ids=user_ids.ids)
        user_ids2 = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id),('position_id.name', '=', self.approve_next)])
        if user_ids2:
            self.sudo().message_subscribe_users(user_ids=user_ids2.ids)

    # @api.multi
    def message_subscribe_users(self, user_ids=None, subtype_ids=None):
        """ Wrapper on message_subscribe, using users. If user_ids is not
            provided, subscribe uid instead. """
        if user_ids is None:
            user_ids = [self._uid]
        return self.message_subscribe(self.env['res.users'].browse(user_ids).mapped('partner_id').ids, subtype_ids=subtype_ids)


    # @api.multi
    def ask_approve(self):
        if not self.type_id:
            raise exceptions.ValidationError('Please define your approval type, contact IT for more Information.')
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "ASK APPROVE")
        self.function_consol(function="ask_approve_consol")
        self._amount_all()
        if len(self) > 1: return [record.ask_approve() for record in self][0]

        query_update_web_base_url = """
            update ir_config_parameter set value = 'https://erp.ad.mayapadahospital.com' where key = 'web.base.url'
            """
        self.env.cr.execute(query_update_web_base_url)
        self._cr.commit()
        
        
        # if self.requisition_id:
        #    for p in self.requisition_id.purchase_ids:
        #        if p.status != 'draft':
        #           raise exceptions.ValidationError("This PR already have a PO")

        self.approve_status = 'Waiting for Approval'
        
        #user_ids = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id), ('position_id', 'in', self.type_id.approval_ids.mapped('rule_ids').mapped('position_id').ids)])
        #self.sudo().message_subscribe_users(user_ids=user_ids.ids)
        
        record = self.sudo()
        record.subscribe_approval()
        now = (datetime.now() +timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
        


        partner_id_check_list = []
        user_id = False
        user_ids = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id),('position_id.name', '=', self.approve_next_store)], limit=1)
        if user_ids:
            #user_ids=user_ids.ids
            user_id=int(user_ids.id)
        user_ids2 = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id),('position_id.name', '=', self.approve_next)], limit=1)
        if user_ids2:
            #user_ids=user_ids2.ids
            user_id=int(user_ids2.id)
        partner_id_check = self.env['res.users'].sudo().search([('id', '=', user_id)]).partner_id.id
        if partner_id_check:

            partner_id_check_list.append(partner_id_check)

            open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini USER IDS :  " + str(user_ids))
            open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini USER ID :  " + str(user_id))
            open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini partner ID :  " + str(partner_id_check))
            open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini partner ID LIST :  " + str(partner_id_check_list))
            notification_ids = [((0, 0, {'res_partner_id': partner_id_check,'notification_type': 'email'}))]    
            self.message_post(body='Please Approve This PO, ' + 'Asked by ' +self.env.user.name + " at " + now,message_type='notification',content_subtype='plaintext', subtype_id=False,notification_ids=notification_ids,partner_ids=partner_id_check_list,notify_by_email=True)
        else:
             self.message_post(body='Please Approve This PO, ' + 'Asked by ' +self.env.user.name + " at " + now,message_type='notification',content_subtype='plaintext', subtype_id=False)       

        planned = self.amount_total
        approval = self.env['purchase.approval'].sudo()
        if self.approve_id:
            # rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
            rule_ids = self.get_store_rule(approval_id=self.approve_id.id)
            if not self.approve_rule_id:
                self.approve_next_store = rule_ids[0].position_id.name
            else:
                # rule_id = rule_ids.filtered(lambda data: data.active == True and data.sequence == record.approve_rule_id.sequence + 1)
                rule_id = self.get_next_rule(approval_id=self.approve_id.id, sequence=record.approve_rule_id.sequence)
                if rule_id:
                    if len(rule_id) > 1:
                        raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                    self.approve_next_store = rule_id.position_id.name
                else:
                    self.approve_next_store = "Completed"
                    
        #cost_center = self.order_line.mapped('account_analytic_id.id')
        #for cc in cost_center:
        #    cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
        #    cc_name = self.env['account.analytic.account'].browse(cc).display_name
        #    date = (tools.datetime.strptime(self.date_order, '%Y-%m-%d %H:%M:%S')).strftime('%Y-%m-%d')
        #    if self.company_id.cost_center_active == True:
        #        if not self.company_id.cost_center_date or not date:
        #            raise UserError(_("Tanggal tidak boleh kosong."))
        #    if self.company_id.cost_center_active == True and self.company_id.cost_center_date <= date:
        #        order_line = self.order_line.search([('order_id', '=', self.id),('account_analytic_id', '=', cc)])
        #        amount_po = sum(r.price_total for r in order_line)
        #        # for line in self.order_line:
        #        budget_used = self.env['crossovered.budget.lines'].sudo().search([('crossovered_budget_id.state','in',['validate','done']),('analytic_account_id', '=', cc),('date_from', '<=', date),('date_to', '>=', date)])
                
                # if not budget_used:
                #     raise exceptions.ValidationError("No budget available for "+cc_name+" in period "+ str(self.ordering_date))
                # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "parameter PO ask approve: " + str(self.approve_next_store) + '  ' + str(self.state))
                
       #         budget_used.budget_line_compute_balance()
                # budget = sum(budget.remain_amount for budget in budget_used)
                # budget = -budget
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(budget))
                # if cc and amount_po > budget:
                #     raise exceptions.ValidationError("Cost center " + cc_name +" exceeds the Total of Budget's Planned Amount")
        self._amount_all()



    # @api.multi
    def get_next_rule(self, approval_id=None, sequence=1):
        rule_id = None
        if approval_id:
            rule_id = self.sudo().env['purchase.approval.rule'].search([('approval_id','=',approval_id), ('enabled','=', True), ('sequence','>', sequence)], order='sequence asc', limit=1)
        return rule_id

    # @api.multi
    def get_store_rule(self, approval_id=None):
        rule_ids = None
        if approval_id:
            rule_ids = self.sudo().env['purchase.approval.rule'].search([('approval_id','=',approval_id), ('enabled','=', True)], order='sequence asc')
        return rule_ids


    # @api.multi
    def ask_approve_consol(self):
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "ASK APPROVE consol")
        self._amount_all()
        if len(self) > 1: return [record.ask_approve() for record in self][0]
        
        
        # if self.requisition_id:
        #    for p in self.requisition_id.purchase_ids:
        #        if p.status != 'draft':
        #           raise exceptions.ValidationError("This PR already have a PO")
        
        self.approve_status = 'Waiting for Approval'
        #user_ids = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id), ('position_id', 'in', self.type_id.approval_ids.mapped('rule_ids').mapped('position_id').ids)])
        #self.sudo().message_subscribe_users(user_ids=user_ids.ids)
        
        record = self.sudo()
        record.subscribe_approval()
        now = (datetime.now() +timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
        self.message_post(body='Please Approve This PO, ' + 'Asked by ' +self.env.user.name + " at " + now,message_type='notification',content_subtype='plaintext',subtype_xmlid='mail.mt_comment')
        planned = self.amount_total
        approval = self.env['purchase.approval'].sudo()
        
        if self.approve_id:
            # rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
            rule_ids = self.get_store_rule(approval_id=self.approve_id.id)
                
            if not self.approve_rule_id:
                self.approve_next_store = rule_ids[0].position_id.name
            else:
                # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                rule_id = self.get_next_rule(approval_id=self.approve_id.id, sequence=record.approve_rule_id.sequence)
                
                if rule_id:
                    if len(rule_id) > 1:
                        raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                    self.approve_next_store = rule_id.position_id.name
                else:
                    self.approve_next_store = "Completed"
        #cost_center = self.order_line.mapped('account_analytic_id.id')
        #for cc in cost_center:
        #    cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
        #    cc_name = self.env['account.analytic.account'].browse(cc).display_name
        #    date = (tools.datetime.strptime(self.date_order, '%Y-%m-%d %H:%M:%S')).strftime('%Y-%m-%d')
        #    if self.company_id.cost_center_active == True:
        #        if not self.company_id.cost_center_date or not date:
        #            raise UserError(_("Tanggal tidak boleh kosong."))
        #    if self.company_id.cost_center_active == True and self.company_id.cost_center_date <= date:
        #        order_line = self.order_line.search([('order_id', '=', self.id),('account_analytic_id', '=', cc)])
        #        amount_po = sum(r.price_total for r in order_line)
        #        # for line in self.order_line:
        #        budget_used = self.env['crossovered.budget.lines'].sudo().search([('crossovered_budget_id.state','in',['validate','done']),('analytic_account_id', '=', cc),('date_from', '<=', date),('date_to', '>=', date)])
                
                # if not budget_used:
                #     raise exceptions.ValidationError("No budget available for "+cc_name+" in period "+ str(self.ordering_date))
                # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "parameter PO ask approve: " + str(self.approve_next_store) + '  ' + str(self.state))
                
        #        budget_used.budget_line_compute_balance()
                # budget = sum(budget.remain_amount for budget in budget_used)
                # budget = -budget
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(budget))
                # if cc and amount_po > budget:
                #     raise exceptions.ValidationError("Cost center " + cc_name +" exceeds the Total of Budget's Planned Amount")
        self._amount_all()


    """
    @api.multi
    def write(self, vals):
        result = super(PurchaseOrder, self).write(vals)
        if vals.get('requisition_id'):
           follower_ids = self.env['purchase.requisition'].sudo().browse(vals['requisition_id']).message_partner_ids
           self.sudo().message_subscribe(partner_ids=follower_ids.ids)
        return result
    """

    # @api.one
    def _status(self):
        if self.approve_next and self.state not in ['cancel', 'purchase', 'done']:
            if not self.approve_status:
                self.status = 'draft'
            elif not self.approve_next == 'Completed':
                self.status = 'waiting'
            else:
                self.status = 'approved'
        else:
            self.status = self.state
            if self.state == 'cancel':
                self.write({'approve_rule_id': False})


    # @api.one
    def _approval(self):
        for rec in self:

            record = rec.sudo()
            planned = rec.amount_total
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
    @api.depends('name', 'purchase_name')
    def _title(self):
        #if self.purchase_name:
        #   self.title = self.purchase_name
        #else:
        for record in self:
            record.title = record.name

    # @api.one
    def _title_tampilan(self):
        for record in self:
            if record.revisi_name:
                record.title_tampilan = record.name + record.revisi_name
            else:
                record.title_tampilan = record.name



    # @api.multi
    def print_grn(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/purchase/grn_modified?id=' + str(self.id)
        action['target'] = 'new'
        return action


    # @api.multi
    def print_po(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/purchase/purchase_order?id=' + str(self.id)
        action['target'] = 'new'
        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(action))
        return action

        # self.ensure_one()
 
        # params = {
        #     '_flowId': 'viewReportFlow',
        #     'ParentFolderUri': '/Mayapada/Purchase/Print_Out_POjrxml',
        #     'reportUnit':'/Mayapada/Purchase/Print_Out_POjrxml',
        #     'decorate':'no',
        #     'j_username': self.company_id.uname_jasper,
        #     'j_password': self.company_id.pass_jasper, 
        #     'viewAsDashboardFrame': 'false',
        #     'standAlone': 'true',
        #     'user_id': self.env.user.partner_id.name,
        #     'po_id': self.id, 
        # }

 
        # import urllib
        # return {
        #     'name': _("Print Preview"),
        #     'view_mode': 'form',
        #     'view_type': 'form',
        #     'res_model': 'wizard.dialog.report',
        #     'type': 'ir.actions.act_window',
        #     'nodestroy': True,
        #     'target': 'new',
        #     'context': {
        #         'default_company_id': self.company_id.id, 
        #         'default_parameter': urllib.parse.urlencode(params)
        #     }
        # }

    # @api.multi
    def print_po_service(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/purchase/purchase_order_non_medic?id=' + str(self.id)
        action['target'] = 'new'
        return action

    # @api.multi
    def print_po_project(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/purchase/new_purchase_order_project?id=' + str(self.id)
        action['target'] = 'new'
        return action


    @api.model
    def _sync_purchase_wipro(self, sync_type='1'):
        import trollius as asyncio
        sync_ids = { int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>', 0), ('wipro_type', '=','RECEIPT')])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)],order='sync_date desc',limit=1).sync_date
        data = []
        date = '' + (datetime.now() + timedelta(hours=7) - timedelta(days=1)).strftime('%Y-%m-%d')
        # date = '2019-01-25'
        query = """
            SELECT 
                a.sync_id,
                a.name,
                a.title,
                a.is_consignment,
                a.partner_id,
                a.vendor_ref,
                a.wipro_date,
                a.date_order,
                a.no_approval, 
                a.date_planned, 
                a.state,
                a.receipt_type,
                a.PONumber purchase_name,
                a.PODate,
                a.wipro_type
            from dbo.VRP_OdooModPurchaseReceipt a 
            where a.wipro_date = '%s'
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
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        default_values['currency_id'] = self.env.company.currency_id.id
        #uom_id = self.env.ref('product.product_uom_categ_unit').id
        #new_sync_ids = []
        # @asyncio.coroutine --DR
        # def process_query(object):
        #     #new_sync_ids += [object['sync_id']]
        #     for value in default_values:
        #         object[value] = default_values[value]

        #     partner_id = object['partner_id']
        #     object['partner_id'] = self.env['res.partner'].search([('sync_id', '=', object['partner_id']),('sync_type', '=', sync_type), ('vendor_wipro', '=', True)], order="id asc", limit=1).id
        #     if not object['partner_id']:
        #         open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(datetime.now()) +" PRC Header: res.partner with sync_id %s and sync_type %s doesn't exist" % (partner_id, sync_type))
        #         return
        #     #if not object['date_planned']:
        #     #   object['date_planned'] = object['date_order'] or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        #     if int(object['sync_id']) in sync_ids:
        #         object['id'] = sync_ids[object['sync_id']]
        #     else:
        #         object['id'] = 'DEFAULT'
        #     object['sync_date'] = now
        #     object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)],limit=1).id
        #     #if values:
        #     #   values += ', '
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
        # tasks = [asyncio.async(process_query(object)) for object in data]
        # for result in loop.run_until_complete(asyncio.gather(*tasks)):
        #     if result:
        #         if values:
        #             values += ', '
        #         values += result
        # excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        # columns = sync.remove_unicode(str(fields)).replace("'", "")
        # columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        
        # # print values
        # if not values:
        #     print ("No data available")
        #     return
        # query = "INSERT into purchase_order %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        # print (query.encode('utf8'))
        # self.env.cr.execute(query)
        
        # # self.env.cr.execute("""
        # # UPDATE purchase_order as s set date_order = s.date_order - (interval '14 hour'), updated_date = True where s.updated_date is null""")
        # self.env.cr.execute("""
        #     UPDATE purchase_order AS a 
        #         set picking_type_id = b.id 
        #     from stock_picking_type b 
        #     inner join stock_warehouse c 
        #         on c.id = b.warehouse_id
        #     where b.code = 'incoming' 
        #         AND b.sync_id_api not ilike '%purchase%'
        #         and c.company_id = a.company_id
        #         and b.active=True
        #         and a.picking_type_id is null """)

        # self.env.cr.execute("""
        #     UPDATE purchase_order 
        #     set wipro_date = date_order 
        #     where wipro_date is null""")
        
        # self.env.cr.execute("""
        #     UPDATE purchase_order_line AS a 
        #     set wipro_date = b.wipro_date 
        #     from purchase_order b 
        #     where b.id = a.order_id and b.name like 'PRC%'
        #         and a.wipro_date is null""")

        # self.env.cr.execute("""
        #     UPDATE purchase_order_line AS a 
        #     set wipro_date = b.date 
        #     from stock_move b 
        #     where b.purchase_line_id = a.id and b.state = 'done' 
        #     and a.order_id in (select id from purchase_order where name not like 'PRC%')
        #     and a.wipro_date is null""")

    @api.model
    def _sync_purchase_wipro_return(self, sync_type='1'):
        import trollius as asyncio
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>',0), ('wipro_type', '=','RETURN')])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)],order='sync_date desc',limit=1).sync_date
        data = []
        date = '' + (datetime.now() + timedelta(hours=7) - timedelta(days=1)).strftime('%Y-%m-%d')
        # date = '2019-01-25'
        query_return = """
            SELECT 
                a.sync_id,
                a.name,
                a.title,
                a.is_consignment,
                a.is_return,
                a.partner_id,
                a.vendor_ref,
                a.date_order,
                a.date_planned,
                a.no_approval,
                a.state,
                a.wipro_type,
                a.ReturnType,
                a.PRType,
                a.POTypeName,
                a.PRID,
                a.POID,
                a.origin,
                a.Purchasereceiptdate,
                a.ORDERSLNO purchase_name,
                a.PODate
            FROM dbo.VRP_OdooPurchaseReturn a 
            WHERE convert(varchar(10), a.date_order, 121) = '%s'
         """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), query_return)
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
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        default_values['currency_id'] = self.env.company.currency_id.id
        #uom_id = self.env.ref('product.product_uom_categ_unit').id
        #new_sync_ids = []
        # @asyncio.coroutine --DR
        # def process_query(object):
        #     #new_sync_ids += [object['sync_id']]
        #     for value in default_values:
        #         object[value] = default_values[value]

        #     partner_id = object['partner_id']
        #     object['partner_id'] = self.env['res.partner'].search([('sync_id', '=', object['partner_id']),('sync_type', '=', sync_type), ('vendor_wipro', '=', True)], order="id asc", limit=1).id
        #     if not object['partner_id']:
        #         open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(datetime.now()) +" PRC Return Header: res.partner with sync_id %s and sync_type %s doesn't exist" % (partner_id, sync_type))
        #         return
        #     #if not object['date_planned']:
        #     #   object['date_planned'] = object['date_order'] or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        #     if int(object['sync_id']) in sync_ids:
        #         object['id'] = sync_ids[object['sync_id']]
        #     else:
        #         object['id'] = 'DEFAULT'
        #     object['sync_date'] = now
        #     object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)],limit=1).id
        #     #if values:
        #     #   values += ', '
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
        # tasks = [asyncio.async(process_query(object)) for object in data]
        # for result in loop.run_until_complete(asyncio.gather(*tasks)):
        #     if result:
        #         if values:
        #             values += ', '
        #         values += result
        # excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        # columns = sync.remove_unicode(str(fields)).replace("'", "")
        # columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
        # # print values
        # if not values:
        #     print ("No data available")
        #     return
        # query = "INSERT into purchase_order %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        # print (query.encode('utf8'))
        # self.env.cr.execute(query)
        # # self.env.cr.execute("""
        # # UPDATE purchase_order as s set date_order = s.date_order - (interval '14 hour'), updated_date = True where s.updated_date is null""")
        # self.env.cr.execute("""
        #     UPDATE purchase_order AS a 
        #         set picking_type_id = b.id 
        #     from stock_picking_type b 
        #     inner join stock_warehouse c 
        #         on c.id = b.warehouse_id
        #     where b.code = 'incoming' 
        #         AND b.sync_id_api not ilike '%purchase%'
        #         and c.company_id = a.company_id
        #         and b.active=True
        #         and a.picking_type_id is null """)
        # self.env.cr.execute("""
        #     UPDATE purchase_order 
        #     set wipro_date = date_order 
        #     where wipro_date is null""")
        # self.env.cr.execute("""
        #     UPDATE purchase_order_line AS a 
        #     set wipro_date = b.wipro_date 
        #     from purchase_order b 
        #     where b.id = a.order_id
        #         and a.wipro_date is null and b.name like 'PRC%'""")

    #START QUERY MANUAL

    @api.model
    def _sync_purchase_wipro_manual(self,sync_type='1',date_start='2019-01-01',date_end='2019-01-01'):
        import trollius as asyncio
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '>', 0), ('wipro_type', '=','RECEIPT')])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)],order='sync_date desc', limit=1).sync_date
        data = []
        date = '' + (datetime.now() + timedelta(hours=7) - timedelta(days=1)).strftime('%Y-%m-%d')
        # date = '2019-01-25'
        query = """
            SELECT 
                a.sync_id,
                a.name,
                a.title,
                a.is_consignment,
                a.partner_id,
                a.vendor_ref,
                a.wipro_date,
                a.date_order,
                a.no_approval, 
                a.date_planned, 
                a.state,
                a.receipt_type,
                a.PONumber purchase_name,
                a.PODate,
                a.wipro_type
            from dbo.VRP_OdooModPurchaseReceipt a 
            where a.wipro_date >= '%s' and a.wipro_date <= '%s'
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
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        default_values['currency_id'] = self.env.company.currency_id.id
        #uom_id = self.env.ref('product.product_uom_categ_unit').id
        #new_sync_ids = []
        @asyncio.coroutine
        def process_query(object):
            #new_sync_ids += [object['sync_id']]
            for value in default_values:
                object[value] = default_values[value]

            partner_id = object['partner_id']
            object['partner_id'] = self.env['res.partner'].search([('sync_id', '=', object['partner_id']), ('sync_type', '=', sync_type), ('vendor_wipro', '=', True)], order="id asc", limit=1).id
            if not object['partner_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(datetime.now()) + " PRC Header: res.partner with sync_id %s and sync_type %s doesn't exist" % (partner_id, sync_type))
                return
            #if not object['date_planned']:
            #   object['date_planned'] = object['date_order'] or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if int(object['sync_id']) in sync_ids:
                object['id'] = sync_ids[object['sync_id']]
            else:
                object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
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
                value += sync.json(object[field])
            value += ')'
            return value
            #values += value

        # loop = asyncio.get_event_loop()
        # tasks = [asyncio.async(process_query(object)) for object in data]
        # for result in loop.run_until_complete(asyncio.gather(*tasks)):
        #     if result:
        #         if values:
        #             values += ', '
        #         values += result
        # excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
        # columns = sync.remove_unicode(str(fields)).replace("'", "")
        # columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")

        # print values
        if not values:
            print ("No data available")
            return
        query = "INSERT into purchase_order %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        
        open('/opt/odoo16/logs/query_po.log', 'a+').write(query.encode('utf8'))
        self.env.cr.execute(query)
        # self.env.cr.execute("""
        # UPDATE purchase_order as s set date_order = s.date_order - (interval '14 hour'), updated_date = True where s.updated_date is null""")
        self.env.cr.execute("""
            UPDATE purchase_order AS a 
                set picking_type_id = b.id 
            from stock_picking_type b 
            inner join stock_warehouse c 
                on c.id = b.warehouse_id
            where b.code = 'incoming' 
                AND b.sync_id_api not ilike '%purchase%'
                and c.company_id = a.company_id
                and b.active=True
                and a.picking_type_id is null """)

        self.env.cr.execute("""
            UPDATE purchase_order 
            set wipro_date = date_order 
            where wipro_date is null""")
        self.env.cr.execute("""
            UPDATE purchase_order_line AS a 
            set wipro_date = b.wipro_date 
            from purchase_order b 
            where b.id = a.order_id and b.name like 'PRC%'
                and a.wipro_date is null""")
        self.env.cr.execute("""
            UPDATE purchase_order_line AS a 
            set wipro_date = b.date 
            from stock_move b 
            where b.purchase_line_id = a.id and b.state = 'done' and a.order_id in (select id from purchase_order where name not like 'PRC%')
            and a.wipro_date is null
            """)

    #END QUERY MANUAL


    # 2021.10.16 - tambahkan default credit days saat create VB dari PO 
    # @api.multi
    def action_view_invoice_dp(self):
        '''
        This function returns an action that display existing vendor bills of given purchase order ids.
        When only one found, show the vendor bill immediately.
        '''
        # action = self.env.ref('account.action_invoice_tree2')
        # result = action.read()[0]
        result = self.env["ir.actions.actions"]._for_xml_id('mayapada.vendor_bill_action')
        down_payment = self.env['product.product'].search([('name','ilike','%Down Payment%'), ('company_id','=', self.company_id.id)], limit=1)

        #override the context to get rid of the default filtering
        result['context'] = {'type': 'in_invoice', 
            'default_purchase_dp_id': self.id, 
            'default_partner_id': self.partner_id.id,
            'default_origin':self.title,
            'default_invoice_line_ids': [(0, 0, {'name': 'Down Payment of ' + self.title, 'product_id': down_payment.id or None, 'quantity':1.0 })],
            'default_reference': 'Down Payment of ' + self.title}

        if not self.down_payment_ids:
            # Choose a default account journal in the same currency in case a new invoice is created
            journal_domain = [
                ('type', '=', 'purchase'),
                ('company_id', '=', self.company_id.id),
                ('currency_id', '=', self.currency_id.id),
            ]
            default_journal_id = self.env['account.journal'].search(journal_domain, limit=1)
            if default_journal_id:
                result['context']['default_journal_id'] = default_journal_id.id
        else:
            # Use the same account journal than a previous invoice
            result['context']['default_journal_id'] = self.down_payment_ids[0].journal_id.id

        #choose the view_mode accordingly
        if len(self.down_payment_ids) != 1:
            result['domain'] = "[('id', 'in', " + str(self.down_payment_ids.ids) + ")]"
        elif len(self.down_payment_ids) == 1:
            res = self.env.ref('account.invoice_supplier_form', False)
            result['views'] = [(res and res.id or False, 'form')]
            result['res_id'] = self.down_payment_ids.id
        return result

    # def action_view_invoice_dp(self):
    #     self.ensure_one()
    #     result = self.env["ir.actions.actions"]._for_xml_id('mayapada.vendor_bill_action')
    #     result['context'] = {'default_type': 'in_invoice', 'default_purchase_dp_id': self.id}
    
    #     #override the context to get rid of the default filtering
    #     result['context'] = {'default_type': 'in_invoice', 
    #         'default_purchase_dp_id': self.id, 
    #         'default_partner_id': self.partner_id.id,
    #         'default_origin':self.title
    #     }
        
    #     if not self.vendor_bill_ids:
    #         # Choose a default account journal in the same currency in case a new invoice is created
    #         journal_domain = [
    #             ('type', '=', 'purchase'),
    #             ('company_id', '=', self.company_id.id),
    #             ('currency_id', '=', self.currency_id.id),
    #         ]
    #         default_journal_id = self.env['account.journal'].search(journal_domain, limit=1)
    #         if default_journal_id:
    #             result['context']['default_journal_id'] = default_journal_id.id
    #     else:
    #         # Use the same account journal than a previous invoice
    #         result['context']['default_journal_id'] = self.vendor_bill_ids[0].journal_id.id

    #     #choose the view_mode accordingly
    #     if len(self.vendor_bill_ids) != 1:
    #         result['domain'] = "[('id', 'in', " + str(self.vendor_bill_ids.ids) + ")]"
    #     elif len(self.vendor_bill_ids) == 1:
    #         res = self.env.ref('mayapada.mayapada_account_invoice_inherited', False)
    #         result['views'] = [(res and res.id or False, 'form')]
    #         result['res_id'] = self.vendor_bill_ids.id

    #     return result


    # # 2021.10.16 - tambahkan default credit days saat create VB dari PO 
    # # @api.multi
    # def action_view_invoice(self):
    #     '''
    #     This function returns an action that display existing vendor bills of given purchase order ids.
    #     When only one found, show the vendor bill immediately.
    #     '''
    #     action = self.env.ref('mayapada.mayapada_account_invoice_supplier_tree_inherited')
    #     result = action.read()[0]

    #     #override the context to get rid of the default filtering
    #     result['context'] = {'type': 'in_invoice', 'default_purchase_id': self.id}

    #     if not self.invoice_ids:
    #         # Choose a default account journal in the same currency in case a new invoice is created
    #         journal_domain = [
    #             ('type', '=', 'purchase'),
    #             ('company_id', '=', self.company_id.id),
    #             ('currency_id', '=', self.currency_id.id),
    #         ]
    #         default_journal_id = self.env['account.journal'].search(journal_domain, limit=1)
    #         if default_journal_id:
    #             result['context']['default_journal_id'] = default_journal_id.id
    #     else:
    #         # Use the same account journal than a previous invoice
    #         result['context']['default_journal_id'] = self.invoice_ids[0].journal_id.id

    #     #choose the view_mode accordingly
    #     if len(self.invoice_ids) != 1:
    #         result['domain'] = "[('id', 'in', " + str(self.invoice_ids.ids) + ")]"
    #     elif len(self.invoice_ids) == 1:
    #         res = self.env.ref('mayapada.mayapada_account_invoice_inherited', False)
    #         result['views'] = [(res and res.id or False, 'form')]
    #         result['res_id'] = self.invoice_ids.id
    #     return result

    def action_view_invoice(self):
        return self._get_action_view_invoice(self.invoice_ids)

    # def _get_action_view_invoice(self, invoices):
    #     """ This function returns an action that display existing picking orders of given purchase order ids. When only one found, show the picking immediately.
    #     """
    #     self.ensure_one()
    #     result = self.env["ir.actions.actions"]._for_xml_id('mayapada.vendor_bill_action')
    #     # override the context to get rid of the default filtering on operation type
    #     result['context'] = {'type': 'in_invoice', 'default_purchase_id': self.id}
    #     # choose the view_mode accordingly
    #     if not invoices or len(invoices) > 1:
    #         result['domain'] = [('id', 'in', invoices.ids)]
    #     elif len(invoices) == 1:
    #         res = self.env.ref('mayapada.mayapada_account_invoice_inherited', False)
    #         form_view = [(res and res.id or False, 'form')]
    #         result['views'] = form_view + [(state, view) for state, view in result.get('views', []) if view != 'form']
    #         result['res_id'] = invoices.id
    #     return result

    def _get_action_view_invoice(self, invoices):
        self.ensure_one()
        result = self.env["ir.actions.actions"]._for_xml_id('mayapada.vendor_bill_action')
        result['context'] = {'default_type': 'in_invoice', 'default_purchase_id': self.id}

        #override the context to get rid of the default filtering
        result['context'] = {'default_type': 'in_invoice', 
            'default_purchase_id': self.id, 
            'default_purchase_po_id': self.id, 
            'default_partner_id': self.partner_id.id,
            'default_origin':self.title
        }

        if not self.vendor_bill_ids:
            # Choose a default account journal in the same currency in case a new invoice is created
            journal_domain = [
                ('type', '=', 'purchase'),
                ('company_id', '=', self.company_id.id),
                ('currency_id', '=', self.currency_id.id),
            ]
            default_journal_id = self.env['account.journal'].search(journal_domain, limit=1)
            if default_journal_id:
                result['context']['default_journal_id'] = default_journal_id.id
        else:
            # Use the same account journal than a previous invoice
            result['context']['default_journal_id'] = self.vendor_bill_ids[0].journal_id.id

        #choose the view_mode accordingly
        if len(self.vendor_bill_ids) != 1:
            result['domain'] = "[('id', 'in', " + str(self.vendor_bill_ids.ids) + ")]"
        elif len(self.vendor_bill_ids) == 1:
            res = self.env.ref('mayapada.mayapada_account_invoice_inherited', False)
            result['views'] = [(res and res.id or False, 'form')]
            result['res_id'] = self.vendor_bill_ids.id

        return result


    def action_view_srb(self):
        self.ensure_one()
        result = self.env["ir.actions.actions"]._for_xml_id('mayapada.srb_temporary_action')
        result['domain'] = [('id', 'in', self.srb_temporary_ids.ids)]
        result['view_mode'] = 'tree,form'  # Ensures tree view first, form second
        return result



    def action_view_grn(self):
        self.ensure_one()
        result = self.env["ir.actions.actions"]._for_xml_id('mayapada.grn_temporary_action')
        result['domain'] = [('id', 'in', self.grn_temporary_ids.ids)]
        result['view_mode'] = 'tree,form'  # Ensures tree view first, form second
        return result



#    def action_view_srb(self):
#        return self._get_action_view_srb(self.srb_temporary_ids)

#    def _get_action_view_srb(self, srb_temporarys):
#        self.ensure_one()
#        result = self.env["ir.actions.actions"]._for_xml_id('mymodule.srb_temporary_action')

#        #choose the view_mode accordingly
#        if len(self.srb_temporary_ids) != 1:
#            result['domain'] = "[('id', 'in', " + str(self.srb_temporary_ids.ids) + ")]"
#        elif len(self.srb_temporary_ids) == 1:
#            res = self.env.ref('mymodule.mymodule_srb_temporary_inherited', False)
#            result['views'] = [(res and res.id or False, 'form')]
#            result['res_id'] = self.srb_temporary_ids.id

#        return result


    # @api.multi
    def button_confirm(self):
        self.function_consol(function="button_confirm_consol")
        if self.requisition_id:
            self.requisition_id.state = 'done'
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.requisition_id.message_post(body='Purchase Requisition Done by ' +self.env.user.name + " at " + now,message_type='notification',content_subtype='plaintext', subtype_id=False)

        company_lama = self.env.company.id
        if not self.purchase_name and not self.sync_date:
            if self.env.company != self.company_id:
                self.env.user.write({'company_id': self.company_id.id})
                self.rfq = self.name
                self.purchase_name = self.name

                search_sequence = self.env['ir.sequence'].search([('company_id','=', self.company_id.id),('code','=', 'purchase.order.confirm')],limit=1)
                next_number_name = search_sequence._next(sequence_date=None)
                self.name = next_number_name
                # self.name = self.env["ir.sequence"].search([('company_id', '=', self.company_id.id)]).next_by_code("purchase.order.confirm")
                # raise exceptions.ValidationError("User's Company and Document Company Must Be The Same!")
            else:
                self.rfq = self.name
                self.purchase_name = self.name
                self.name = self.env["ir.sequence"].search([('company_id', '=', self.company_id.id)]).next_by_code("purchase.order.confirm")

        self = self.sudo()
        # self._amount_all()
        self.confirm_by = self.env.user.name
        if not self.no_approval:
            if self.approve_next != 'Completed': #or not self.env.context.get('approved'):
                raise exceptions.ValidationError("Waiting for Approval")

        result = super(PurchaseOrder, self).button_confirm()
        self.sudo().env.user.write({'company_id': company_lama})
        for move_id in self.env['stock.move'].sudo().search([('purchase_line_id', 'in', self.mapped('order_line').ids)]):
            move_id.tglproses = move_id.purchase_line_id.order_id.date_order
            move_id.non_asset = move_id.price_total - move_id.capitalization

        query1 = """UPDATE purchase_order_line 
              set price_tax = has_tax 
              where sync_date is not null 
                and price_tax is null 
                and has_tax is not null 
                and order_id = %s""" % (self.id)

        query2 = """UPDATE purchase_order AS a
            set amount_total = a.amount_total
            from (
                select order_id, 
                    sum(price_subtotal) amount_total
                from purchase_order_line 
                group by order_id
            ) AS b
            where b.order_id = a.id
                and a.sync_id is not null 
                and a.sync_date is not null 
                and a.id = %s""" % (self.id)
        self.env.cr.execute(query1)
        self.env.cr.execute(query2)
        # self._amount_all()
        self.send_api_consol_write_company()
        return result

    # @api.multi
    def button_confirm_consol(self):
        if self.requisition_id:
            self.requisition_id.state = 'done'
        company_lama = self.env.company.id
        if not self.purchase_name and not self.sync_date:
            if self.env.company != self.company_id:
                self.env.user.write({'company_id': self.company_id.id})
                self.rfq = self.name
                self.purchase_name = self.name
                self.name = self.env["ir.sequence"].search([('company_id', '=', self.company_id.id)]).next_by_code("purchase.order.confirm")
                # raise exceptions.ValidationError("User's Company and Document Company Must Be The Same!")
            else:
                self.rfq = self.name
                self.purchase_name = self.name
                self.name = self.env["ir.sequence"].search([('company_id', '=', self.company_id.id)]).next_by_code("purchase.order.confirm")
        self = self.sudo()
        # self._amount_all()
        self.confirm_by = self.env.user.name
        if not self.no_approval:
            if self.approve_next != 'Completed' or not self.env.context.get('approved'):
                raise exceptions.ValidationError("Waiting for Approval")
        result = super(PurchaseOrder, self).button_confirm()
        self.sudo().env.user.write({'company_id': company_lama})
        for move_id in self.env['stock.move'].sudo().search([('purchase_line_id', 'in', self.mapped('order_line').ids)]):
            move_id.tglproses = move_id.purchase_line_id.order_id.date_order
            move_id.non_asset = move_id.price_total - move_id.capitalization

        query1 = """UPDATE purchase_order_line 
              set price_tax = has_tax 
              where sync_date is not null 
                and price_tax is null 
                and has_tax is not null 
                and order_id = %s""" % (self.id)

        query2 = """UPDATE purchase_order AS a
            set amount_total = a.amount_total
            from (
                select order_id, 
                    sum(price_subtotal) amount_total
                from purchase_order_line 
                group by order_id
            ) AS b
            where b.order_id = a.id
                and a.sync_id is not null 
                and a.sync_date is not null 
                and a.id = %s""" % (self.id)
        self.env.cr.execute(query1)
        self.env.cr.execute(query2)
        # self._amount_all()
        return result

    # @api.multi
    def button_confirm_tambahan(self):

        if self.requisition_id:
            self.requisition_id.state = 'done'
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.requisition_id.message_post(body='Purchase Requisition Done by ' +self.env.user.name + " at " + now,message_type='notification',content_subtype='plaintext', subtype_id=False)
            
        company_lama = self.env.company.id
        if not self.purchase_name and not self.sync_date:
            if self.env.company != self.company_id:
                self.env.user.write({'company_id': self.company_id.id})
                self.rfq = self.name
                self.purchase_name = self.name
                self.name = self.env["ir.sequence"].search([('company_id', '=', self.company_id.id)]).next_by_code("purchase.order.confirm")
                # raise exceptions.ValidationError("User's Company and Document Company Must Be The Same!")
            else:
                self.rfq = self.name
                self.purchase_name = self.name
                self.name = self.env["ir.sequence"].search([('company_id', '=', self.company_id.id)]).next_by_code("purchase.order.confirm")
        self = self.sudo()
        # self._amount_all()
        self.confirm_by = self.env.user.name
        if not self.no_approval:
            if self.approve_next != 'Completed' or not self.env.context.get('approved'):
                raise exceptions.ValidationError("Waiting for Approval")
        result = super(PurchaseOrder, self).button_confirm()
        self.sudo().env.user.write({'company_id': company_lama})
        for move_id in self.env['stock.move'].sudo().search([('purchase_line_id', 'in', self.mapped('order_line').ids)]):
            move_id.tglproses = move_id.purchase_line_id.order_id.date_order
            move_id.non_asset = move_id.price_total - move_id.capitalization

        query1 = """UPDATE purchase_order_line 
              set price_tax = has_tax 
              where sync_date is not null 
                and price_tax is null 
                and has_tax is not null 
                and order_id = %s""" % (self.id)

        query2 = """UPDATE purchase_order AS a
            set amount_total = a.amount_total
            from (
                select order_id, 
                    sum(price_subtotal) amount_total
                from purchase_order_line 
                group by order_id
            ) AS b
            where b.order_id = a.id
                and a.sync_id is not null 
                and a.sync_date is not null 
                and a.id = %s""" % (self.id)
        self.env.cr.execute(query1)
        self.env.cr.execute(query2)

        for order in self:
            if order.state not in ['draft', 'sent']:
                continue
            order._add_supplier_to_product()
            # Deal with double validation process
            if order.company_id.po_double_validation == 'one_step'\
                    or (order.company_id.po_double_validation == 'two_step'\
                        and order.amount_total < self.env.company.currency_id.compute(order.company_id.po_double_validation_amount, order.currency_id))\
                    or order.user_has_groups('purchase.group_purchase_manager'):
                order.button_approve()
            else:
                order.write({'state': 'to approve'})
        return True

    # @api.multi
    def approve(self):
        open('/opt/odoo16/logs/log_test_sync_id_api.log', 'a+').write('\n' + "APPROVE PO 1 " + str(self.name))
        self.function_consol(function="approve_consol")
        record = self.sudo()
        record._amount_all()
        query_update_web_base_url = """
            update ir_config_parameter set value = 'https://erp.ad.mayapadahospital.com' where key = 'web.base.url'
            """
        self.env.cr.execute(query_update_web_base_url)
        self._cr.commit()
        

        if not record.approve_id:
            raise exceptions.ValidationError("There are no rule defined for this Budget")
        # rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
        rule_ids = self.get_store_rule(approval_id=record.approve_id.id)
                
        
        if not rule_ids:
            raise exceptions.ValidationError("There are no rule defined for this Budget")
        
        if not self.approve_rule_id:
            position_id = self.env.user.position_id.id
            # if self.env.user.position_id.name == 'MHG - CHIEF OPERATING OFFICER':
            #     if self.env.user.position_id.id != rule_ids[0].position_id.get_parent_ids():
            #         position_id = self.env['res.position'].search([('name','=','MHG - GROUP FINANCE DIRECTOR')]).id #CFO


                        
            if position_id in rule_ids[0].position_id.get_parent_ids() or self.env.user.second_position_id.id in rule_ids[0].position_id.get_parent_ids():
                open('/opt/odoo16/logs/log_test_sync_id_api.log', 'a+').write('\n' + "APPROVE PO 2 " + str(self.name))
        
                self.approve_rule_id = rule_ids[0]
                #self.approve_history("Approved by " + self.approve_status)
                record = self.sudo()
                now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')

                # self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now, message_type='notification', content_subtype='plaintext', subtype='mt_comment')
                # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                if not rule_id:
                    open('/opt/odoo16/logs/log_test_sync_id_api.log', 'a+').write('\n' + "APPROVE PO 3 " + str(self.name))
        
                    if len(rule_ids) == 1:
                        self.approve_next = 'Completed'

                    self.status = 'approved'
                    if self.env.company.sync_consol_type =='main' and self.sync_consol_id_unit:
                        self.with_context(approved=True).button_confirm()
                        open('/opt/odoo16/logs/log_test_sync_id_api.log', 'a+').write('\n' + "APPROVE PO 4 " + str(self.name))
        
                        #self.state = 'purchase'
                        #self.send_search_po()
                    else:
                        self.with_context(approved=True).button_confirm()
            else:
                raise exceptions.ValidationError("You doesn't have authority to approve this Transaction")
        else:
            # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
            rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                
            if rule_id:
                # raise exceptions.ValidationError(str(rule_id.position_id.get_parent_ids))
                position_id = self.env.user.position_id.id
                # if self.env.user.position_id.name == 'MHG - CHIEF OPERATING OFFICER':
                #     if self.env.user.position_id.id != rule_id.position_id.get_parent_ids()[0]:
                #         # raise exceptions.ValidationError(str(rule_id.position_id.get_parent_ids()[0]))
                #         position_id = self.env['res.position'].search([('name','=','MHG - GROUP FINANCE DIRECTOR')]).id #CFO
                
                
                if position_id in rule_id.position_id.get_parent_ids() or self.env.user.second_position_id.id in rule_id.position_id.get_parent_ids():
                    self.approve_rule_id = rule_id
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    # self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now, message_type='notification', content_subtype='plaintext', subtype='mt_comment')
                    #self.approve_history("Approved by " + self.approve_status)
                    rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                    # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1):
                    if not rule_id:
                        self.status = 'approved'
                        self.approve_next = 'Completed' #Penambahan 20230626
                        if self.env.company.sync_consol_type =='main' and self.sync_consol_id_unit:
                            self.with_context(approved=True).button_confirm()
                            #self.state = 'purchase'
                            #self.send_search_po()
                        else:
                            self.with_context(approved=True).button_confirm()
                else:
                    raise exceptions.ValidationError("You doesn't have authority to approve this Transaction")
            else:
                raise exceptions.ValidationError("There are no Approval anymore for this Budget")
                

        if self.approve_id:
            # rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
            rule_ids = self.get_store_rule(approval_id=record.approve_id.id)
                
            if not self.approve_rule_id:
                self.approve_next_store = rule_ids[0].position_id.name
            else:
                # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                
                if rule_id:
                    if len(rule_id) > 1:
                        raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                    self.approve_next_store = rule_id.position_id.name
                else:
                    
                    self.approve_next_store = "Completed"
        
        record.subscribe_approval()
        # if record.company_id.sync_consol_type == 'main':
        #     open('/opt/odoo16/logs/log_test_sync_id_api.log', 'a+').write('\n' + "MASUK Search PO NAME")
        #     record.send_search_po()
        ##cost_center = self.order_line.mapped('account_analytic_id.id')
        ##for cc in cost_center:
        ##    cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
        ##    cc_name = self.env['account.analytic.account'].browse(cc).display_name
        ##    date = (tools.datetime.strptime(self.date_order, '%Y-%m-%d %H:%M:%S')).strftime('%Y-%m-%d')
        ##    if self.company_id.cost_center_active == True:
        ##        if not self.company_id.cost_center_date or not date:
        ##            raise UserError(_("Tanggal tidak boleh kosong."))
        ##    if self.company_id.cost_center_active == True and self.company_id.cost_center_date <= date:
        ##        order_line = self.order_line.search([('order_id', '=', self.id),('account_analytic_id', '=', cc)])
        ##        amount_po = sum(r.price_total for r in order_line)
        ##        # for line in self.order_line:
        ##        budget_used = self.env['crossovered.budget.lines'].sudo().search([('crossovered_budget_id.state','in',['validate','done']),('analytic_account_id', '=', cc),('date_from', '<=', date),('date_to', '>=', date)])
                
                # if not budget_used:
                #     raise exceptions.ValidationError("No budget available for "+cc_name+" in period "+ str(self.ordering_date))
                # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "parameter PO approve: " + str(self.approve_next_store) + '  ' + str(self.state))
        ##        budget_used.budget_line_compute_balance()
                # budget = sum(budget.remain_amount for budget in budget_used)
                # budget = -budget
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(budget))
                # if cc and amount_po > budget:
                #     raise exceptions.ValidationError("Cost center " + cc_name +" exceeds the Total of Budget's Planned Amount")

            



        if self.approve_next_store =='MHG - PROCUREMENT MANAGER':


            partner_id_check_list = []
            user_id = False
            user_ids = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id),('second_position_id.name', '=', self.approve_next_store)], limit=1)
            if user_ids:
                user_id=int(user_ids.id)
            partner_id_check = self.env['res.users'].sudo().search([('id', '=', user_id)]).partner_id.id
            if partner_id_check:
                partner_id_check_list.append(partner_id_check)
                if (self.type_id and 'PROJECT' in (self.type_id.name or '') and self.env.user.second_position_id and self.env.user.second_position_id.name == 'MHG - PROCUREMENT MANAGER'):
                    partner_id_cc = self.env['res.users'].sudo().search([('position_id', '=', 'MHG - ASSOCIATE DIRECTOR PROCUREMENT')], limit=1).partner_id.id
                    if partner_id_cc:
                        partner_id_check_list.append(partner_id_cc)
                partner_id_check_list = list(set(partner_id_check_list))

                notification_ids = [((0, 0, {'res_partner_id': partner_id_check,'notification_type': 'email'}))]    
                self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now ,message_type='notification',content_subtype='plaintext', subtype_id=False,notification_ids=notification_ids,partner_ids=partner_id_check_list,notify_by_email=True)
            else:
                if self.user_id.id:
                    search_partner_id = self.user_id.id
                else:
                    search_partner_id = self.env.user.id
                partner_id_check2 = self.env['res.users'].sudo().search([('id', '=', search_partner_id)]).partner_id.id
                # partner_id_check2 = self.env['res.users'].sudo().search([('id', '=', (self.user_id.id or self.user_po_id.id))]).partner_id.id
                
                partner_id_check_list.append(partner_id_check2)

                if (self.type_id and 'PROJECT' in (self.type_id.name or '') and self.env.user.second_position_id and self.env.user.second_position_id.name == 'MHG - ASSOCIATE DIRECTOR PROCUREMENT (PROJECT)'):
                    partner_id_cc2 = self.env['res.users'].sudo().search([('position_id', '=', 'MHG - ASSOCIATE DIRECTOR PROCUREMENT')], limit=1).partner_id.id
                    if partner_id_cc2:
                        partner_id_check_list.append(partner_id_cc2)
                
                partner_id_check_list = list(set(partner_id_check_list))

                notification_ids = [((0, 0, {'res_partner_id': partner_id_check2,'notification_type': 'email'}))] 
                
                self.message_post(body='Approved Complited by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now ,message_type='notification',content_subtype='plaintext', subtype_id=False,notification_ids=notification_ids,partner_ids=partner_id_check_list,notify_by_email=True)
                # self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now ,message_type='notification',content_subtype='plaintext', subtype_id=False)    





        else:


            partner_id_check_list = []
            user_id = False
            user_ids = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id),('position_id.name', '=', self.approve_next_store)], limit=1)
            if user_ids:
                user_id=int(user_ids.id)
            partner_id_check = self.env['res.users'].sudo().search([('id', '=', user_id)]).partner_id.id
            if partner_id_check:
                partner_id_check_list.append(partner_id_check)
                if (self.type_id and 'PROJECT' in (self.type_id.name or '') and self.env.user.second_position_id and self.env.user.second_position_id.name == 'MHG - ASSOCIATE DIRECTOR PROCUREMENT (PROJECT)'):
                    partner_id_cc = self.env['res.users'].sudo().search([('position_id', '=', 'MHG - ASSOCIATE DIRECTOR PROCUREMENT')], limit=1).partner_id.id
                    if partner_id_cc:
                        partner_id_check_list.append(partner_id_cc)
                partner_id_check_list = list(set(partner_id_check_list))

                notification_ids = [((0, 0, {'res_partner_id': partner_id_check,'notification_type': 'email'}))]    
                self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now ,message_type='notification',content_subtype='plaintext', subtype_id=False,notification_ids=notification_ids,partner_ids=partner_id_check_list,notify_by_email=True)
            else:
                if self.user_id.id:
                    search_partner_id = self.user_id.id
                else:
                    search_partner_id = self.env.user.id
                partner_id_check2 = self.env['res.users'].sudo().search([('id', '=', search_partner_id)]).partner_id.id
                # partner_id_check2 = self.env['res.users'].sudo().search([('id', '=', (self.user_id.id or self.user_po_id.id))]).partner_id.id
                
                partner_id_check_list.append(partner_id_check2)

                if (self.type_id and 'PROJECT' in (self.type_id.name or '') and self.env.user.second_position_id and self.env.user.second_position_id.name == 'MHG - ASSOCIATE DIRECTOR PROCUREMENT (PROJECT)'):
                    partner_id_cc2 = self.env['res.users'].sudo().search([('position_id', '=', 'MHG - ASSOCIATE DIRECTOR PROCUREMENT')], limit=1).partner_id.id
                    if partner_id_cc2:
                        partner_id_check_list.append(partner_id_cc2)
                
                partner_id_check_list = list(set(partner_id_check_list))

                notification_ids = [((0, 0, {'res_partner_id': partner_id_check2,'notification_type': 'email'}))] 
                
                self.message_post(body='Approved Complited by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now ,message_type='notification',content_subtype='plaintext', subtype_id=False,notification_ids=notification_ids,partner_ids=partner_id_check_list,notify_by_email=True)
                # self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now ,message_type='notification',content_subtype='plaintext', subtype_id=False)    




    # @api.multi
    def approve_consol(self):
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK SINI APPROVE CONSOL PO")
        record = self.sudo()
        # record._amount_all()
        if not record.approve_id:
            raise exceptions.ValidationError("There are no rule defined for this Budget")
        # rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
        rule_ids = self.get_store_rule(approval_id=record.approve_id.id)
                
        if not rule_ids:
            raise exceptions.ValidationError("There are no rule defined for this Budget")
        if not self.approve_rule_id:
            position_id = self.env.user.position_id.id
            # if self.env.user.position_id.name == 'MHG - CHIEF OPERATING OFFICER':
            #     if self.env.user.position_id.id != rule_ids[0].position_id.get_parent_ids():
            #         position_id = self.env['res.position'].search([('name','=','MHG - GROUP FINANCE DIRECTOR')]).id #CFO
                        
            if position_id in rule_ids[0].position_id.get_parent_ids():
                self.approve_rule_id = rule_ids[0]
                #self.approve_history("Approved by " + self.approve_status)
                record = self.sudo()
                now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
                # self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now, message_type='notification', content_subtype='plaintext', subtype_xmlid='mail.mt_comment')
                # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1):
                rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                
                if not rule_id:
                    if len(rule_ids) == 1:
                        self.approve_next = 'Completed'

                    #self.state = 'validate'
                    self.status = 'approved'
                    if self.env.company.sync_consol_type =='main':
                        self.state = 'purchase'
                    if self.env.company.sync_consol_type =='unit':
                        self.with_context(approved=True).button_confirm_tambahan()
            else:
                raise exceptions.ValidationError("You doesn't have authority to approve this Transaction")
        else:
            # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
            rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                
            if rule_id:
                # raise exceptions.ValidationError(str(rule_id.position_id.get_parent_ids))
                position_id = self.env.user.position_id.id
                # if self.env.user.position_id.name == 'MHG - CHIEF OPERATING OFFICER':
                #     if self.env.user.position_id.id != rule_id.position_id.get_parent_ids()[0]:
                #         # raise exceptions.ValidationError(str(rule_id.position_id.get_parent_ids()[0]))
                #         position_id = self.env['res.position'].search([('name','=','MHG - GROUP FINANCE DIRECTOR')]).id #CFO
                
                    
                if position_id in rule_id.position_id.get_parent_ids():
                    self.approve_rule_id = rule_id
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    # self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now, message_type='notification', content_subtype='plaintext', subtype_xmlid='mail.mt_comment')
                    #self.approve_history("Approved by " + self.approve_status)
                    # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1):
                    rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                
                    if not rule_id:
                        #self.state = 'validate'
                        self.status = 'approved'
                        if self.env.company.sync_consol_type =='main':
                            self.state = 'purchase'
                        if self.env.company.sync_consol_type =='unit':
                            self.with_context(approved=True).button_confirm_tambahan()
                else:
                    raise exceptions.ValidationError("You doesn't have authority to approve this Transaction")
            else:
                raise exceptions.ValidationError("There are no Approval anymore for this Budget")
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK SINI APPROVE CONSOL2")
        
        if self.approve_id:
            # rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
            rule_ids = self.get_store_rule(approval_id=record.approve_id.id)
                
            if not self.approve_rule_id:
                self.approve_next_store = rule_ids[0].position_id.name
            else:
                # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                
                if rule_id:
                    if len(rule_id) > 1:
                        raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                    self.approve_next_store = rule_id.position_id.name
                else:
                    self.approve_next_store = "Completed"
        record.subscribe_approval()
        self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now, message_type='notification', content_subtype='plaintext', subtype_id=False)


    # @api.multi
    def send_search_po(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_purchase_order
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_search/unit/search/purchase.order"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_search/main/search/purchase.order"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
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
                # values['name'] = str(record.name)


                
                lst.append(values)
                body['values'] = json.dumps(lst)
                # body['values'] = json.dumps(values)
                
                cookies = {'session_id': record.env.user.cookies}

                print('\n' + "body : " + str(body))
                print('\n' + "headers : " + str(headers))
                print('\n' + "url : " + str(url))
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(body))
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(headers))
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(url))
            

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
                        # for d in json_resp['data']:
                        #     if 'id' in d:
                        #         response_id = d['id']
                        #     if 'name' in d:
                        #         response_name = d['name']
                        if json_resp['data']['id']:
                            response_id = json_resp['data']['id']
                        if json_resp['data']['name']:
                            response_name = json_resp['data']['name']
                    if json_resp['status'] == 'error':
                        # raise exceptions.ValidationError(_('Data Gagal Diedit'))
                        raise exceptions.ValidationError(_(json_resp['message']))


                data_update = {
                    'name' : response_name
                }
                super(PurchaseOrder, self).write(data_update)


    # @api.multi
    @api.depends('title', 'partner_ref')
    def name_get(self):
        result = super(PurchaseOrder, self).name_get()
        new_result = []
        for object in result:
            record = self.browse(object[0])
            if record.title:
                new_result += [(object[0], object[1].replace(record.name, record.title))]
        return new_result


    @api.onchange('purchase_grn')
    def _onchange_purchase_grn(self):
        if not self.purchase_grn:
            return

        purchase_grn = self.purchase_grn
        self.partner_id = purchase_grn.partner_id.id
        self.fiscal_position_id = purchase_grn.fiscal_position_id.id
        self.payment_term_id = purchase_grn.payment_term_id.id
        self.company_id = purchase_grn.company_id.id
        self.currency_id = purchase_grn.currency_id.id
        self.origin = purchase_grn.origin
        self.notes = purchase_grn.notes
        self.date_order = purchase_grn.date_order
        self.picking_type_id = purchase_grn.picking_type_id.id
        self.user_id = purchase_grn.user_id.id
        #self.state = purchase_grn.state
        
        #purchase_grn.active = False
        self.grn_modified = True

        # Create PO lines if necessary
        order_lines = []
        for line in purchase_grn.order_line:
            # Create PO line
            order_lines.append((0, 0, {
                'name':line.name,
                'product_id':line.product_id.id,
                'product_uom':line.product_id.uom_po_id.id,
                'product_qty':line.product_qty,
                'price_unit':line.price_unit,
                'discount_persen':line.discount_persen,
                'discount_value':line.discount_value,
                # 'taxes_id': [(6, 0, taxes_ids)],
                'taxes_id': [(6, 0, [tax.id for tax in line.taxes_id])],
                'date_planned': line.date_planned,
                # 'procurement_ids': [(6, 0, [purchase_grn.procurement_id.id])] if purchase_grn.procurement_id else False,
                'account_analytic_id':line.account_analytic_id.id,
                'purchase_line_grn' : line.id,
                'product_char' : line.product_char,
            }))
        self.order_line = order_lines


    @api.onchange('requisition_id')
    def _onchange_requisition_id(self):
        if not self.requisition_id:
            return

        requisition = self.requisition_id
        if self.partner_id:
            partner = self.partner_id
        else:
            partner = requisition.vendor_id
        payment_term = partner.property_supplier_payment_term_id
        currency = partner.property_purchase_currency_id or requisition.company_id.currency_id

        # FiscalPosition = self.env['account.fiscal.position']
        # fpos = FiscalPosition.get_fiscal_position(partner.id)
        # fpos = FiscalPosition.browse(fpos)

        self.partner_id = partner.id
        # self.fiscal_position_id = fpos.id
        self.payment_term_id = payment_term.id
        self.company_id = requisition.company_id.id
        self.currency_id = currency.id
        if requisition.origin:
            self.origin = requisition.name + ' / ' + str(requisition.origin)
        else:
            self.origin = requisition.name + ' / '
        self.notes = requisition.description
        self.date_order = requisition.date_end or fields.Datetime.now()
        self.picking_type_id = requisition.picking_type_id.id
        self.user_id = requisition.user_id.id

        if requisition.type_id.line_copy != 'copy':
            return

        # Create PO lines if necessary
        order_lines = []
        for line in requisition.line_ids:
            # Compute name
            product_lang = line.product_id.with_context({'lang': partner.lang,'partner_id': partner.id})
            name = product_lang.display_name
            if product_lang.description_purchase:
                name += '\n' + product_lang.description_purchase

            # Compute taxes
            # if fpos:
            #     taxes_ids = fpos.map_tax(line.product_id.supplier_taxes_id.filtered(lambda tax: tax.company_id == requisition.company_id)).ids
            # else:
            #     taxes_ids = line.product_id.supplier_taxes_id.filtered(lambda tax: tax.company_id == requisition.company_id).ids
            taxes_ids = line.product_id.supplier_taxes_id.filtered(lambda tax: tax.company_id == requisition.company_id).ids

            # Compute quantity and price_unit
            # if line.product_uom_id != line.product_id.uom_po_id:
            if (line.product_uom_id != line.product_id.uom_po_id) and line.product_uom_id:
                product_qty = line.product_uom_id._compute_quantity(line.product_qty, line.product_id.uom_po_id)
                price_unit = line.product_uom_id._compute_price(line.price_unit, line.product_id.uom_po_id)
            else:
                product_qty = line.product_qty
                price_unit = line.price_unit

            if requisition.type_id.quantity_copy != 'copy':
                product_qty = 0

            # Compute price_unit in appropriate currency
            if requisition.company_id.currency_id != currency:
                price_unit = requisition.company_id.currency_id.compute(price_unit, currency)

            # Create PO line
            order_lines.append((0, 0, {
                'product_id':line.product_id.id,
                'name':line.description,
                'product_uom':line.product_id.uom_po_id.id,
                'product_qty':product_qty,
                'price_unit':price_unit,
                'taxes_id': [(6, 0, taxes_ids)],
                'date_planned':requisition.schedule_date or fields.Date.today(),
                # 'procurement_ids': [(6, 0, [requisition.procurement_id.id])] if requisition.procurement_id else False,
                'account_analytic_id':line.account_analytic_id.id,
                'request_line_id' : line.id,
                'product_char' : line.product_char,
            }))
            open('/opt/odoo16/logs/fp.log', 'a+').write('\n' + "name : " + str(line))
            open('/opt/odoo16/logs/fp.log', 'a+').write('\n' + "name : " + str(line.description))
            open('/opt/odoo16/logs/fp.log', 'a+').write('\n' + "name : " + str(order_lines))
            

        self.order_line = order_lines




class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'
    #_sql_constraints = [('sync_id_api_unique', 'unique(sync_type, sync_id_api)', 'Can not be duplicate value for sync_id_api')]
    

    def _default_get_company(self):
        return self.env.company.id


    # @api.depends('order_id.vendor_bill_ids.state')
    # def _compute_qty_invoiced(self):
    #     if self:
    #         for line in self:
    #             open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "_computed_qty_invoiced 1")
            
    #             line.qty_invoiced = 0.00
    #             if line.order_id.vendor_bill_ids:
    #                 open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "_computed_qty_invoiced 2")
            
    #                 for invoice in line.order_id.vendor_bill_ids:
    #                     open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "_computed_qty_invoiced 3")
            
    #                     if line.order_id == invoice.purchase_po_id and invoice.state != 'draft':
    #                         open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "_computed_qty_invoiced 4")
            
    #                         for inv_line in invoice.invoice_line_ids:
    #                             open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "_computed_qty_invoiced 5")
            
    #                             if inv_line.product_id == line.product_id:
    #                                 open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "_computed_qty_invoiced 6")
            
    #                                 line.qty_invoiced += inv_line.quantity


    @api.depends('vendor_bill_lines.invoice_id.state')
    def _compute_qty_invoiced(self):
        for line in self:
            qty = 0.0
            for inv_line in line.vendor_bill_lines:
                if inv_line.invoice_id.state not in ['cancel']:
                    if inv_line.invoice_id.type == 'in_invoice':
                        qty += inv_line.uom_id._compute_quantity(inv_line.quantity, line.product_uom)
                    elif inv_line.invoice_id.type == 'in_refund':
                        qty -= inv_line.uom_id._compute_quantity(inv_line.quantity, line.product_uom)
            line.qty_invoiced = qty

    ##############################Update
    @api.depends('order_id.state', 'receiving_note_ids.picking_id.state', 'receiving_note_ids.picking_id.is_return')
    def _compute_qty_received_srb(self):
        for line in self:
            if line.order_id.state not in ['purchase', 'done']:
                line.qty_received_srb = 0.0
                continue
          
            total = 0.0
            for move in line.receiving_note_ids:
                if move.picking_id.state in ['done']:
                    if move.product_uom != line.product_uom:
                        total += (move.product_uom._compute_quantity(move.product_uom_qty, line.product_uom) * (-1 if move.picking_id.is_return is True else 1))
                    else:
                        total += (move.product_uom_qty * (-1 if move.picking_id.is_return is True else 1))
            line.qty_received_srb = total


    @api.depends('srb_temporary_ids.line_qty_rcv')
    def _compute_qty_srb(self):
        for line in self:          
            total = 0.0
            for move in line.srb_temporary_ids:
                total += move.line_qty_rcv
            line.qty_srb = total


    @api.depends('grn_temporary_ids.line_qty_grn')
    def _compute_qty_grn(self):
        for line in self:          
            total = 0.0
            for move in line.grn_temporary_ids:
                total += move.line_qty_grn
            line.qty_grn = total



    sync_id = sync.id_big
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_is_arcus = sync.is_arcus
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")

    sync_id_product = fields.Float(string="Sync ID Product")
    invoice_id = fields.Float(string="invoice ID")
    discount_value = fields.Float(string="Discount Value", store=True, digits=(16, 4))
    discount_total = fields.Float(string='Discount Total', readonly=True,compute='_compute_discount', store=True)
    tax_discount = fields.Float(string='Tax Discount', readonly=True, compute='_compute_discount', store=True)
    status_contract = fields.Html(string="Status Contract")
    discount_persen = fields.Float(string='Discount Percent', digits=(16, 9))
    normal_qty = fields.Float(string="Normal Qty")
    normal_price = fields.Float(string="Normal Price")
    has_tax = fields.Float(string="Has Tax")
    normal_uom = fields.Many2one('uom.uom', string="Normal UOM")
    uom_small = fields.Many2one('uom.uom', string="Smallest UOM")
    is_conversion = fields.Boolean(string="Is Conversion", readonly=True)
    product_uom2 = fields.Many2one('uom.uom', string="Purchase UoM", readonly=True, compute='_product_uom2', store=True)
    product_qty2 = fields.Float(string="Purchase Qty", digits=(16, 4))
    price_unit2 = fields.Float(string="Price Unit UoM Purchase", digits=(16, 4))
    # conversion_rate = fields.Float(string="Conversion Rate", related='product_id.conversion_rate', store=True)
    converted = fields.Boolean(string='Converted', default=False, store=True, index=True)
    product_categ_id = fields.Many2one('product.category', string="Product Category", store=True, index=True, related='product_id.categ_id')
    wipro_date = fields.Date(string="Wipro PO Date", index=True, store=True)
    is_consignment = fields.Boolean(string="Is Consignment", readonly=False, default=False, index=True, store=True)
    qty_received = fields.Float(compute='_compute_qty_received', string="Received Qty", store=True)
    tanggal_terima = fields.Date(string="Receive/Shiptment Date")
    no_grn = fields.Char(string="GRN No.", store=True, index=True)
    account_analytic_id = fields.Many2one('account.analytic.account', string="Analytic Account", index=True)
    
    # cost_center_active = fields.Boolean(string="Cost Center Active", readonly=True, related='company_id.cost_center_active', store=True)
    cost_center_active = fields.Boolean(string="Cost Center Active", readonly=True, store=True)

    company_id = fields.Many2one('res.company', default=_default_get_company, string='Company', store=True, readonly=True)
    ppn = fields.Float(string="PPN Rate")
    pph = fields.Float(string="PPH rate")

    batch_no = fields.Char(string="Batch No")
    batch_id = fields.Many2one("stock.lot", string="Batch ID")
    expiry_date = fields.Date(string="Expiry Date")

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    order_id = fields.Many2one('purchase.order', string='Order Reference', index=True, required=False, ondelete='cascade')
    
    # auto compute relation to stock.picking and stock.move for valuation price
    picking_id = fields.Many2one('stock.picking', string="Stock Picking")
    picking_created = fields.Boolean(string="Stock Picking Created", default=False, readonly=True, index=True)
    move_id = fields.Many2one('stock.move', string="Stock Move")
    move_created = fields.Boolean(string="Stock Move Created", readonly=True)
    analytic_ids = fields.Many2many('account.analytic.account', string="Analytic Users")

    request_line_id = fields.Many2one('purchase.requisition.line', string="Request Line ID")
    product_char = fields.Char(string="Product Char")

    vendor_char = fields.Many2one(related='order_id.partner_id', string='Vendor Char', readonly=True, store=True)
    vendor_filter = fields.Char(related='order_id.partner_id.name', string='Vendor Filter', readonly=True, store=True)

    ####################Update#######################
    receiving_line_ids = fields.One2many('stock.receiving.line', 'line_id', string='Receiving Line', readonly=True, ondelete='set null', copy=False)
    receiving_note_ids = fields.One2many('stock.move', 'purchase_line_id', string='Receiving Note Line', readonly=True, ondelete='set null', copy=False)
    qty_invoiced = fields.Float(compute='_compute_qty_invoiced', string="Received Qty Inv", store=True)
    qty_received_srb = fields.Float(compute='_compute_qty_received_srb', string="Received Qty SRB", store=True)
    variance_total = fields.Float(string="Variance Total")
    purchase_line_grn = fields.Many2one('purchase.order.line', string="Purchase GRN Line")
    vendor_bill_lines = fields.One2many('account.invoice.line', 'purchase_line_id', string="Bill Lines", readonly=True, copy=False)

    #Sync Arcus
    is_return = fields.Boolean(string="Is Return", index=True,store=True)
    
    discount_level = fields.Char(string="Discount Level",index=True,store=True)
    status_grn = fields.Char(string="Status GRN",index=True,store=True)
    status_grn_arcus = fields.Char(string="Status GRN Arcus",index=True,store=True)
    state_arcus = fields.Char(string="State Arcus",index=True,store=True)
    variance_total = fields.Float(string="Variance Total")
    purchase_line_grn = fields.Many2one('purchase.order.line', string="Purchase GRN Line")
    srb_temporary_ids = fields.One2many('srb.temporary', 'po_line_id', string='SRB Temporary Lines', readonly=True, ondelete='set null', copy=False)
    grn_temporary_ids = fields.One2many('grn.temporary', 'po_line_id', string='GRN Temporary Lines', readonly=True, ondelete='set null', copy=False)
    qty_srb = fields.Float(compute='_compute_qty_srb', string="Received Qty SRB", store=True)
    qty_grn = fields.Float(compute='_compute_qty_grn', string="Received Qty GRN", store=True)
        

    @api.onchange('product_id')
    def _onchange_product_id_new(self):
        open('/opt/odoo16/logs/fp.log', 'a+').write('\n' + "GASSSSSSSSSSSS : ")
        

    @api.onchange('product_id','order_id.user_id','name')
    # @api.depends('product_id','order_id.user_id')
    def _change_analytic_domain(self, analytic_ids=[]):
        res={}
        res['domain'] = {'account_analytic_id': [('parent_id', '!=', False),('type_analytic', '=','expense'),('id','in', self.order_id.user_id.analytic_ids.ids if self.order_id.user_id.analytic_ids else [0])]}
        return res


    # 2021.10.05 - redefined _create_stock_moves
    # @api.multi
    def _create_stock_moves(self, picking):
        moves = self.env['stock.move']
        done = self.env['stock.move'].browse()
        for line in self:
            for val in line._prepare_stock_moves(picking):
                done += moves.create(val)
        return done

    ##############Update
    # @api.multi
    def _create_receiving_line(self, receiving):
        stock_line = self.env['stock.receiving.line']
        done = self.env['stock.receiving.line'].browse()
        for line in self:
            for val in line._prepare_receiving_line(receiving):
                done += stock_line.create(val)
        return done

    #############Update
    # @api.multi
    def _prepare_receiving_line(self, receiving):
        """ Prepare the stock moves data for one order line. This function returns a list of
        dictionary ready to be used in stock.move's create()
        """
        self.ensure_one()
        res = []
        if self.product_id.type not in ['product', 'consu']:
            return res
        template = {
            'company_id': self.order_id.company_id.id,
            'receiving_id': receiving.id,
            'line_id': self.id,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom.id,
            'name': self.name or '',
            'qty_issue': self.product_qty,
            
        }
        res.append(template)
        open('/opt/odoo16/logs/stock_move.log','a+').write('\n\n'+str(res))
        return res



    ##############Update
    # @api.multi
    def _create_receiving_line(self, receiving):
        stock_line = self.env['stock.receiving.line']
        done = self.env['stock.receiving.line'].browse()
        for line in self:
            if line.product_id.name != 'Down Payment':
                for val in line._prepare_receiving_line(receiving):
                    done += stock_line.create(val)
        return done

    #############Update
    # @api.multi
    def _prepare_receiving_line(self, receiving):
        """ Prepare the stock moves data for one order line. This function returns a list of
        dictionary ready to be used in stock.move's create()
        """
        self.ensure_one()
        res = []
        if self.product_id.type not in ['product', 'consu']:
            return res
        template = {
            'company_id': self.order_id.company_id.id,
            'receiving_id': receiving.id,
            'line_id': self.id,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom.id,
            'name': self.name or '',
            'qty_issue': self.product_qty,
            
        }
        res.append(template)
        open('/opt/odoo16/logs/stock_move.log','a+').write('\n\n'+str(res))
        return res


    # @api.multi
    # def _prepare_stock_moves(self, picking):
    #     moves = super(PurchaseOrderLine, self)._prepare_stock_moves(picking)
    #     for move in moves:
    #         line_id = self.browse(move['purchase_line_id'])
    #         if line_id:
    #             move['price_unit'] = line_id.price_subtotal / line_id.product_qty
    #             move['base_price'] = (line_id.price_unit * line_id.product_qty) / line_id.product_qty
    #         if not line_id.sync_date and line_id.price_tax >= 1:
    #             move['price_unit'] = line_id.price_total / line_id.product_qty
    #             move['base_price'] = (line_id.price_unit * line_id.product_qty * 1.1) / line_id.product_qty
    #     return moves


    # 2021.10.05 - redefined _prepare_stock_move 
    # @api.multi
    def _prepare_stock_moves(self, picking):
        """ Prepare the stock moves data for one order line. This function returns a list of
        dictionary ready to be used in stock.move's create()
        """
        self.ensure_one()
        res = []
        if self.product_id.type not in ['product', 'consu']:
            return res
        qty = 0.0
        price_unit = self._get_stock_move_price_unit()
        for move in self.move_ids.filtered(lambda x: x.state != 'cancel'):
            qty += move.product_qty
        template = {
            'name': self.name or '',
            'product_id': self.product_id.id,
            'product_uom': self.product_uom.id,
            'date': self.order_id.date_order,
            'date_expected': self.date_planned,
            'location_id': self.order_id.partner_id.property_stock_supplier.id,
            'location_dest_id': self.order_id._get_destination_location(),
            'picking_id': picking.id,
            'partner_id': self.order_id.dest_address_id.id,
            'move_dest_id': False,
            'state': 'draft',
            'purchase_line_id': self.id,
            'company_id': self.order_id.company_id.id,
            'price_unit': price_unit,
            'base_price': price_unit,
            'picking_type_id': self.order_id.picking_type_id.id,
            'group_id': self.order_id.group_id.id,
            # 'procurement_id': False,
            'origin': self.order_id.name,
            'route_ids': self.order_id.picking_type_id.warehouse_id and [(6, 0, [x.id for x in self.order_id.picking_type_id.warehouse_id.route_ids])] or [],
            'warehouse_id': self.order_id.picking_type_id.warehouse_id.id,
             # 2021.10.05 - tambahan 
            'account_analytic_id': self.account_analytic_id.id or False,
            'move_type': 'purchase.receipt',
            'product_service_id': self.product_id.categ_id.id or False,
            'product_categ_id': self.product_id.categ_id.id or False,
            'product_consignment': self.is_consignment or False,
            'product_supply_id': self.product_id.categ_id.property_stock_valuation_account_id.id or False,
            'product_input_id': self.product_id.categ_id.property_stock_account_input_categ_id.id or False,
            'sub_total': self.price_total
        }

        # 2021.10.05 - Koreksi 
        template['price_unit'] = self.price_subtotal / self.product_qty
        template['base_price'] = (self.price_unit * self.product_qty) / self.product_qty
        # 2021.10.05 - Koreksi jika GRN untuk PO not GRN from HIS
        if not self.sync_id and not self.sync_id_api and self.price_tax >= 1:
            template['price_unit'] = self.price_total / self.product_qty
            template['base_price'] = (self.price_unit * self.product_qty * 1.1) / self.product_qty


        open('/opt/odoo16/logs/stock_move.log','a+').write('\n\n'+str(template))
        # Fullfill all related procurements with this po line
        diff_quantity = self.product_qty - qty
        # for procurement in self.procurement_ids.filtered(lambda p: p.state != 'cancel'):
        #     # If the procurement has some moves already, we should deduct their quantity
        #     sum_existing_moves = sum(x.product_qty for x in procurement.move_ids if x.state != 'cancel')
        #     existing_proc_qty = procurement.product_id.uom_id._compute_quantity(sum_existing_moves, procurement.product_uom)
        #     procurement_qty = procurement.product_uom._compute_quantity(procurement.product_qty, self.product_uom) - existing_proc_qty
        #     if float_compare(procurement_qty, 0.0, precision_rounding=procurement.product_uom.rounding) > 0 and float_compare(diff_quantity, 0.0, precision_rounding=self.product_uom.rounding) > 0:
        #         tmp = template.copy()
        #         tmp.update({
        #             'product_uom_qty': min(procurement_qty, diff_quantity),
        #             'move_dest_id': procurement.move_dest_id.id,  # move destination is same as procurement destination
        #             'procurement_id': procurement.id,
        #             'propagate': procurement.rule_id.propagate,
        #         })
        #         res.append(tmp)
        #         diff_quantity -= min(procurement_qty, diff_quantity)
        if float_compare(diff_quantity, 0.0,  precision_rounding=self.product_uom.rounding) > 0:
            template['product_uom_qty'] = diff_quantity
            # 2021.10.05 - Koreksi jurnal account.
            res.append(template)
            open('/opt/odoo16/logs/stock_move.log','a+').write('\n\n'+str(res))
        return res


    @api.onchange('product_qty', 'product_uom')
    def _onchange_quantity(self):
        if not self.product_id:
            return

        if self.date_planned:
            date = tools.datetime.strptime(str(self.date_planned), '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d')
        else:
            date = datetime.now().strftime('%Y-%m-%d')
            
        seller_id = self.env['product.supplierinfo'].search([('product_tmpl_id', '=', self.product_id.product_tmpl_id.id), ('min_qty', '>=', self.product_qty), ('partner_id', '=', self.order_id.partner_id.id), ('date_start', '<=', date), ('date_end', '>=', date)], limit=1)
        open('/opt/odoo16/logs/check_onchange.log', 'a+').write('\n' + str(date))
        seller = self.env['product.supplierinfo'].browse(seller_id.id)

        if seller or not self.date_planned:
            self.date_planned = self._get_date_planned(seller).strftime(DEFAULT_SERVER_DATETIME_FORMAT)

        if not seller:
            return

        price_unit = self.env['account.tax']._fix_tax_included_price_company(seller.price, self.product_id.supplier_taxes_id, self.taxes_id, self.company_id) if seller else 0.0
        if price_unit and seller and self.order_id.currency_id and seller.currency_id != self.order_id.currency_id:
            price_unit = seller.currency_id.compute(price_unit, self.order_id.currency_id)

        if seller and self.product_uom and seller.product_uom != self.product_uom:
            price_unit = seller.product_uom._compute_price(price_unit, self.product_uom)

        self.price_unit = price_unit
        self.discount_value = seller.discount_value
        self.discount_persen = seller.discount_persen
        self.taxes_id = seller.taxes_id.ids

    # @api.multi
    def unlink(self):
        for rec in self:
            if rec.sync_consol_id_unit and not rec.sync_id and not rec.sync_id_api or rec.sync_consol_id_main and not rec.sync_id and not rec.sync_id_api:
                rec.send_api_consol_unlink_company()
            check_model_exist = self.env['ir.model'].search([('model', '=', 'tampung.purchase.order.line')])
            if check_model_exist:
                now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
                query_insert = """insert into tampung_purchase_order_line (po_id,po_line_id,sync_type,date_delete) values ('%s','%s','%s','%s') """ % (rec.order_id.id,rec.id, rec.order_id.company_id.sync_type, now)
                self.env.cr.execute(query_insert)

        result = super(PurchaseOrderLine, self).unlink()

    # @api.multi
    def send_api_consol_unlink_company(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_purchase_order
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api_unlink/unit/purchase.order.line"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api_unlink/main/purchase.order.line"
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
                body['csrf_token'] = self.env.user.token_consol
                # body['ids'] = self.env.user[consol_id_from]
                if consol_type == 'unit':
                    body['ids'] = int(record.sync_consol_id_main)
                    company_name = record.company_id.name
                    sync_consol_id_main = str(self.env.user.login)
                    body['company_name'] = company_name
                    
                    body['user_id'] = sync_consol_id_main
                if consol_type == 'main':
                    body['ids'] = int(record.sync_consol_id_unit)
                    company_name = record.company_id.name
                    sync_consol_id_main = str(self.env.user.login)
                    body['company_name'] = company_name
                
                    body['user_id'] = sync_consol_id_main
                cookies = {'session_id': self.env.user.cookies}
                print(body)
                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                json_resp = response_json.json()
                # self.env.user.sync_consol_response = json_resp


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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'purchase.order.line' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'purchase.order.line'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        result = super(PurchaseOrderLine, self).create(vals)
        #for record in result:
        #    if record.env.company.sync_api_active == True:
        #        record.env.cr.execute("DELETE from purchase_order_line where id in (select max(a.id) from purchase_order_line a where a.sync_id_api is not null group by a.sync_id_api having count(*) > 1)")

        # 2022.04.04 - Firgiawan
        # Modifikasi perubahan Rate PPN 11%
        #if result.has_tax > 0:
        #    ppn_id_api = 'ppn_11' if result.ppn == 11.0 else 'ppn'
        #    tax = self.env['account.tax'].search([('sync_id_api', '=', ppn_id_api), ('type_tax_use', '=', 'purchase')],limit=1).ids
        #    # vals.update({'taxes_id': tax})
        #    result.taxes_id = tax
        if result.company_id.cost_center_active:
            if not result.company_id.cost_center_date or not result.date_order:
                raise UserError(_("Tanggal tidak boleh kosong."))
        if result.company_id.cost_center_active and result.order_id.item_type =='1' and not result.account_analytic_id and result.company_id.cost_center_date <= result.date_order.date():
            raise exceptions.ValidationError("Item {code} harus dimapping dengan Cost Center Analytic".format(code=result.product_id.name + " " + str(result.name) or ""))        

        #if self.env.company.sync_api_active == True:
        #    if result.date_order:
        #        date_wib = tools.datetime.strptime(result.date_order, '%Y-%m-%d %H:%M:%S') - timedelta(hours=7)
        #        result.date_order = date_wib

        #    if result.conversion_rate < 1:
        #        result.conversion_rate = 1

        #    if result.sync_id_api:
        #        # 2021.10.06 - tambahan u/ GRN return Qty dibuat minus
        #        if result.order_id.is_return:
        #            result.product_qty = result.product_qty * -1
        #        result.qty_received = result.product_qty
        open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + "result.company_id.sync_type : " + str(result.company_id.sync_type))
        open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + "result.order_id.sync_type : " + str(result.order_id.sync_type))
        open('/opt/odoo16/logs/dor.log', 'a+').write('\n' + "vals.get('company_id') : " + str(vals.get('company_id')))

        if result.company_id.sync_type:
            result.sync_type = result.company_id.sync_type

        #if vals.get('company_id'):
        #    company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
        #    result.sync_type = company_id.sync_type

        if result.trigger_create == False and not result.sync_id and not result.sync_id_api:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger create purchase order line")
            result.send_api_consol_company()
            result.send_api_consol_tax_write()


        if result.request_line_id and result.request_line_id.description:
            result.name = result.request_line_id.description

        if result.purchase_line_grn:
            result.variance_total = result.price_total - result.purchase_line_grn.price_total


        if result.company_id.sync_api_stock_active:
            result.stock_valuation()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " +str(result.id)

        open(log_file, 'a').write(message_log)
        return result


    # auto create stock.picking & stock.move 
    # auto create stock_picking per record transaksi untuk stockable product
    # @api.multi
    def stock_valuation(self):
        for record in self:
            # open('/opt/odoo16/logs/sale_stock_valuation.log', 'a+').write('\n' + "masuk 3")
            # jalankan hanya untuk product stockable dan yang bukan consignment
            if record.sync_id_api and record.product_id.type == 'product' and record.order_id.is_consignment is not True:
                # open('/opt/odoo16/logs/sale_stock_valuation.log', 'a+').write('\n' + "masuk 4")
                print("Do something...")
                # create procurement
                if record.order_id.procurement_created is not True:
                    procurement_code = record.order_id.company_id.company_code + '/' + record.order_id.title 
                    group = self.env['procurement.group'].search([('name','=', procurement_code)], limit=1)
                    if not group:
                        group = self.env['procurement.group'].create({'name': procurement_code, 'move_type': 'direct'})
                    if group:
                        record.order_id.group_id = group.id
                        record.order_id.procurement_group_id = group.id 
                        record.order_id.procurement_created = True 

                # create picking 
                if record.order_id.procurement_created and record.picking_created is not True:
                    data = {}
                    location_id = self.env['stock.location'].search([('name','ilike','Vendors'), ('company_id','=', record.order_id.company_id.id)], limit=1).id or None
                    location_dest_id = record.order_id.receipt_location_id.id if record.order_id.receipt_location_id else self.env['stock.location'].search([('name','ilike','stock'), ('company_id','=', record.order_id.company_id.id)], limit=1).id

                    if record.order_id.is_return:
                        trans_type = 'purchase.return'
                    else:
                        trans_type = 'purchase.receipt'

                    data['picking_type_id'] = self.env['stock.picking.type'].search([('sync_id_api','=', trans_type),('sync_type','=', record.sync_type)], limit=1).id or None
                    data['location_id'] = location_dest_id if record.order_id.is_return else location_id
                    data['location_dest_id'] = location_id if record.order_id.is_return else location_dest_id
                    data['group_id'] = record.order_id.procurement_group_id.id 
                    data['company_id'] = record.order_id.company_id.id 
                    data['po_id'] = record.order_id.id 
                    data['origin'] = record.order_id.title 
                    data['min_date'] = record.order_id.date_order
                    data['max_date'] = record.order_id.date_order
                    data['date'] = record.order_id.date_order
                    data['date_done'] = record.order_id.date_order
                    data['date_move'] = record.order_id.date_order
                    data['partner_id'] = record.order_id.partner_id.id or None
                    data['move_type'] = 'direct'
                    data['note'] = record.name 
                    data['state'] = 'waiting'
                    data['sync_id_api'] = 'POL.' + str(record.sync_id_api)
                    data['sync_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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

                    location_id = self.env['stock.location'].search([('name','ilike','Vendors'), ('company_id','=', record.order_id.company_id.id)], limit=1).id or None
                    location_dest_id = record.order_id.receipt_location_id.id if record.order_id.receipt_location_id else self.env['stock.location'].search([('name','ilike','stock'), ('company_id','=', record.order_id.company_id.id)], limit=1).id

                    if record.order_id.is_return:
                        trans_type = 'purchase.return'
                    else:
                        trans_type = 'purchase.receipt'

                    data['picking_type_id'] = self.env['stock.picking.type'].search([('sync_id_api','=', trans_type),('sync_type','=', record.sync_type)], limit=1).id or None
                    data['location_id'] = location_dest_id if record.order_id.is_return else location_id
                    data['location_dest_id'] = location_id if record.order_id.is_return else location_dest_id
                    data['group_id'] = record.order_id.procurement_group_id.id 
                    data['company_id'] = record.order_id.company_id.id 
                    data['po_id'] = record.order_id.id 
                    data['picking_id'] = record.picking_id.id 
                    data['origin'] = record.order_id.title
                    data['name'] = record.name
                    data['date'] = record.order_id.date_order
                    data['date_expected'] = record.order_id.date_order
                    data['partner_id'] = record.order_id.partner_id.id or None
                    data['product_id'] = record.product_id.id 
                    data['product_uom_qty'] = abs(record.product_qty)
                    #data['product_qty'] = abs(record.scrap_qty)
                    data['product_uom'] = record.product_id.uom_id.id 
                    data['price_unit'] = (record.price_subtotal / abs(record.product_qty))
                    data['cost_unit'] = (record.price_subtotal / abs(record.product_qty))
                    data['lot_id'] = record.batch_id.id or None 
                    data['note'] = record.name 
                    data['purchase_line_id'] = record.id 
                    data['procure_method'] = 'make_to_stock'
                    data['state'] = 'waiting'
                    data['sync_id_api'] = 'POL.' + str(record.sync_id_api)
                    data['sync_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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


    # @api.multi
    def send_api_consol_company(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_purchase_order
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/purchase.order.line"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/purchase.order.line"
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

                if record.product_id.id == False:
                    values['product_id'] = record.product_id.product_tmpl_id.id
                else:
                    values['product_id'] = str(record.product_id.product_tmpl_id.id)
                if record.order_id.id == False:
                    values['order_id'] = record.order_id.id
                else:
                    values['order_id'] = str(record.order_id.id)

                # if record.account_analytic_id.id == False:
                #     values['account_analytic_id'] = record.account_analytic_id.id
                # else:
                #     values['account_analytic_id'] = str(record.account_analytic_id.id)

                values['product_qty'] = record.product_qty
                values['product_qty2'] = record.product_qty2

                if record.product_uom.id == False:
                    values['product_uom'] = record.product_uom.id
                else:
                    values['product_uom'] = str(record.product_uom.id)
                values['price_unit'] = record.price_unit
                values['price_unit2'] = record.price_unit2
                values['discount_persen'] = record.discount_persen
                values['discount_value'] = record.discount_value
                values['date_planned'] = record.date_planned
                values['trigger_create'] = True

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
                super(PurchaseOrderLine, self).write(data_update)


    # 2021.10.08 - Sudah total PO
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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'purchase.order.line' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'purchase.order.line'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        result = super(PurchaseOrderLine, self).write(vals)

        for record in self:
            if record.env.context.get('ganti_date'): return result
            if record.company_id.cost_center_active:
                if not record.company_id.cost_center_date or not record.date_order:
                    raise UserError(_("Tanggal tidak boleh kosong."))
            if record.company_id.cost_center_active and record.order_id.item_type =='1' and not record.account_analytic_id and record.company_id.cost_center_date <= record.date_order.date():
                # open('/opt/odoo16/logs/log_purchase_order_line_write.log', 'a+').write('\n cek ' + record.cost_center_active)
                raise exceptions.ValidationError("Item {code} harus dimapping dengan Cost Center Analytic".format(code=record.product_id.name + " " + str(record.name) or ""))
            
            #open('/opt/odoo16/logs/log_purchase_order_line_write.log', 'a+').write('\n' + "Cek write PO Line")
            record = record.with_context(ganti_date=True)
            
            # for record in record:
            #     discount = record.discount_value * record.product_qty
            #     price_total = vals.get('price_total', record.price_total) - discount
            #     price_subtotal = vals.get('price_subtotal', record.price_subtotal) - discount
            #     record.write({'price_total': price_total, 'price_subtotal': price_subtotal, 'discount_total': discount})
            if record.product_qty == 0:
                raise UserError(_('Quantity should greater than 0'))

            if record.purchase_line_grn:
                record.variance_total = record.price_total - record.purchase_line_grn.price_total


            #if record.env.company.sync_api_active == True: 
            #    if vals.get('date_order'):
            #        date_wib = tools.datetime.strptime(str(vals.get('date_order')),'%Y-%m-%d %H:%M:%S') - timedelta(hours=7)
            #        record.date_order = date_wib

            #    if vals.get('conversion_rate'):
            #        if vals.get('conversion_rate') < 1:
            #            record.conversion_rate = 1

            #    if vals.get('sync_id_api'):
            #        record.qty_received = record.product_qty

            #    if vals.get('has_tax') > 0:
            #        tax = record.env['account.tax'].search([('sync_id_api', '=', 'ppn'), ('type_tax_use', '=', 'purchase')],limit=1).ids
            #        record.taxes_id = tax
            
            # if record.company_id:
            #     record.sync_type = record.company_id.sync_type
            if record.trigger_write == True and not record.sync_id and not record.sync_id_api:
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger write purchase order line")
                query = """
                UPDATE purchase_order_line set trigger_write = false
                WHERE id = {record_id}""".format(record_id = record.id)
                record.env.cr.execute(query)
                record.send_api_consol_write_company()
                record.send_api_consol_tax_write()
            log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
            message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
            message_log += "\n\nuser: " + record.env.user.login + "\n\n Write before return" + "\n ID: " +str(record.id)

            open(log_file, 'a').write(message_log)
            
        return result



    # @api.multi
    def send_api_consol_write_company(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_purchase_order
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/purchase.order.line"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/purchase.order.line"
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

                if record.product_id.id == False:
                    values['product_id'] = record.product_id.product_tmpl_id.id
                else:
                    values['product_id'] = str(record.product_id.product_tmpl_id.id)
                if record.order_id.id == False:
                    values['order_id'] = record.order_id.id
                else:
                    values['order_id'] = str(record.order_id.id)

                # if record.account_analytic_id.id == False:
                #     values['account_analytic_id'] = record.account_analytic_id.id
                # else:
                #     values['account_analytic_id'] = str(record.account_analytic_id.id)

                values['product_qty'] = record.product_qty
                values['product_qty2'] = record.product_qty2

                if record.product_uom.id == False:
                    values['product_uom'] = record.product_uom.id
                else:
                    values['product_uom'] = str(record.product_uom.id)
                values['price_unit'] = record.price_unit
                values['price_unit2'] = record.price_unit2
                values['discount_persen'] = record.discount_persen
                values['discount_value'] = record.discount_value
                values['date_planned'] = record.date_planned
                values['trigger_write'] = False
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
                super(PurchaseOrderLine, self).write(data_update)

    # @api.multi
    def send_api_consol_tax_write(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_purchase_tax
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active and record.taxes_id:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api_purchase/unit/write/tax"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api_purchase/main/write/tax"
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
                # values = {}
                # lst = []
                    # values = {}
                values_array = []
                    
                for loop in record.taxes_id:
                    values = {}
                    values['sync_type'] = str(record.company_id.sync_type)
                    values['account_tax_id'] = str(loop.id)
                    values['purchase_order_line_id'] = str(record.id)
                    values_array.append(values)
                    body['values'] = values_array
                        
                body['values'] = json.dumps(values_array)

                cookies = {'session_id': record.env.user.cookies}

                print('\n' + "body : " + str(body))
                print('\n' + "headers : " + str(headers))
                print('\n' + "url : " + str(url))

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
                    # 'sync_consol_sent' : data_sent,
                    }

                super(PurchaseOrderLine, self).write(data_update)


            if consol_active and not record.taxes_id:
                if consol_type == 'unit':
                    url = consol_url + "/delete_purchase_tax_internal_api/unit/write/tax"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/delete_purchase_tax_internal_api/main/write/tax"
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
                # values = {}
                # lst = []
                    # values = {}
                values_array = []
                    
                for loop in record:
                    values = {}
                    values['sync_type'] = str(record.company_id.sync_type)
                    values['purchase_order_line_id'] = str(record.id)
                    values_array.append(values)
                    body['values'] = values_array
                        
                body['values'] = json.dumps(values_array)

                cookies = {'session_id': record.env.user.cookies}

                print('\n' + "body : " + str(body))
                print('\n' + "headers : " + str(headers))
                print('\n' + "url : " + str(url))

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
                    # 'sync_consol_sent' : data_sent,
                    }

                super(PurchaseOrderLine, self).write(data_update)

                
    @api.onchange('taxes_id','sync_type', 'name','product_id','account_analytic_id','product_qty','product_qty2','product_uom','price_unit','price_unit2','discount_persen','discount_value')
    def onchange_trigger_write(self):
        self.trigger_write = True

    @api.onchange('product_id')
    def onchange_product_char(self):
        self.product_char = self.product_id.name

    # @api.onchange('order_id.partner_id')
    # def onchange_vendor_char(self):
    #     self.vendor_char = self.order_id.partner_id.name

    ## @api.one
    @api.depends('product_id')
    def _product_uom2(self):
        for rec in self:
        # supp_info = self.env['product.supplierinfo'].search([('name','=',self.partner_id.id),('product_tmpl_id','=',self.product_id.product_tmpl_id.id)], limit=1)
        # tax_info = self.env['account.tax.product.supplierinfo.rel'].search([('product_supplierinfo_id','=',supp_info.id)], limit=1)
        # raise exceptions.ValidationError(_(tax_info))
        # self.price_unit = supp_info.price
            rec.product_uom2 = rec.product_id.uom2_id.id
            if rec.product_uom2 and rec.product_qty != 0 and rec.product_id.conversion_rate != 0:
                rec.update({'product_qty2':rec.product_qty / rec.product_id.conversion_rate})

    # @api.multi
    def compute_primary_uom(self):
        if self.product_uom2.id == self.product_id.uom2_id.id and self.product_qty != 0:
            self.product_qty2 = self.product_qty / self.product_id.conversion_rate

    # @api.multi
    def compute_secondary_uom(self):
        if self.product_uom2.id == self.product_id.uom2_id.id and self.product_qty2 != 0:
            self.product_qty = self.product_qty2 * self.product_id.conversion_rate

    # @api.one
    # def _status_contract(self):
    #     if self.product_id:
    #         contract = self.env['product.supplierinfo'].search([('product_tmpl_id', '=', self.product_id.product_tmpl_id.id), ('name', '=', self.order_id.partner_id.id), ('date_start', '<=', self.order_id.date_order), ('date_end', '>=', self.order_id.date_order)], limit=1)
    #         if contract:
    #             self.status_contact = '<span>This product have a contract</span>'
    #         else:
    #             self.status_contact = '<span style="font-weight: 900; color: red;">This partner does not have contract</span>'

    @api.depends('product_qty', 'price_unit', 'taxes_id', 'discount_total')
    def _compute_amount(self):
        for line in self:
            taxes = line.taxes_id.compute_all(line.price_unit - line.discount_value,line.order_id.currency_id,line.product_qty,product=line.product_id,partner=line.order_id.partner_id)
            line.update({
                'price_tax': taxes['total_included'] - taxes['total_excluded'],
                # 'price_total': taxes['total_included'] - line.discount_total,
                # 'price_subtotal': taxes['total_excluded'] - line.discount_total,
                'price_total': taxes['total_included'],
                'price_subtotal': taxes['total_excluded'],
            })


    @api.depends('order_id.state', 'move_ids.state')
    def _compute_qty_received(self):
        # received = super(PurchaseOrderLine, self)._compute_qty_received()
        received = super()._compute_qty_received()
        for line in self:
            if line.order_id.state not in ['purchase', 'done']:
                line.qty_received = 0.0
                continue
            if line.product_id.type not in ['consu', 'product'] or line.sync_date:
                line.qty_received = line.product_qty
                # continue
            # total = 0.0
            # for move in line.move_ids:
            #     if move.state == 'done' and move.location_id == 8:
            #         if move.product_uom != line.product_uom:
            #             total += move.product_uom._compute_quantity(move.product_uom_qty, line.product_uom)
            #         else:
            #             total += move.product_uom_qty
            # elif move.state == 'done' and move.location_dest_id == 8:
            #     if move.product_uom != line.product_uom:
            #         total -= move.product_uom._compute_quantity(move.product_uom_qty, line.product_uom)
            #     else:
            #         total -= move.product_uom_qty
            # line.qty_received = total
        return received

    

    # @api.multi
    def query_conversion(self):
        print ("12")
        # self.env.cr.execute("""
        # UPDATE purchase_order_line as pol set uom_small =
        # (select uom_id from product_template where id =
        # (select product_tmpl_id from product_product where id = pol.product_id))""")
        # self.env.cr.execute("""
        # UPDATE purchase_order_line set conversion_rate =
        # (select conversion_rate from product_template where id =
        # (select product_tmpl_id from product_product where id = purchase_order_line.product_id))""")
        # self.env.cr.execute("""
        # UPDATE purchase_order_line set is_conversion = True, normal_uom = purchase_order_line.product_uom, normal_qty = purchase_order_line.product_qty, normal_price = purchase_order_line.price_unit
        # where purchase_order_line.product_uom =
        # (select uom_po_id from product_template where id =
        # (select product_tmpl_id from product_product where id = purchase_order_line.product_id))""")
        # self.env.cr.execute("""
        # UPDATE purchase_order_line as pol set product_uom = pol.uom_small, converted = True, product_qty = pol.normal_qty * pol.conversion_rate, price_unit = pol.normal_price / conversion_rate
        # where pol.is_conversion = True and pol.converted is null and pol.normal_qty > 0 and pol.conversion_rate > 0 and pol.normal_price > 0""")
        print ("SELESAI")

    # @api.depends('price_unit', 'discount_value')
    # def _change_price(self):
    #     for r in self:
    #         if not r.price_unit:
    #             r.discount_value = 0.00
    #         else:
    #             r.discount_value = (r.discount_persen * r.price_unit) / 100

    @api.depends('discount_value', 'product_qty')
    def _compute_discount(self):
        for r in self:
            r.discount_total = r.discount_value * r.product_qty
            for tax in r.taxes_id:
                tax_disc = tax._compute_amount(round(r.discount_value * r.product_qty),r.price_unit,r.product_qty,product=r.product_id,partner=r.order_id.partner_id)
                r.tax_discount = tax_disc

    @api.onchange('taxes_id', 'discount_persen','price_unit')  # if these fields are changed, call method
    def _discount_persen(self):
        for r in self:
            if r.price_unit:
                discount_val = (r.discount_persen / 100) * r.price_unit
                r.discount_value = discount_val

    @api.onchange('taxes_id', 'discount_value','price_unit')  # if these fields are changed, call method
    def _discount_value(self):
        for r in self:
            if r.price_unit:
                r.discount_persen = (r.discount_value / r.price_unit) * 100

    @api.onchange('product_uom','product_qty')  # if these fields are changed, call method
    def _convert_uom2(self):
        for r in self:
            if r.product_qty > 0:
                r.product_qty2 = r.product_qty / r.product_id.conversion_rate

    @api.onchange('product_uom2','product_qty2')  # if these fields are changed, call method
    def _convert_uom(self):
        for r in self:
            if r.product_qty2 > 0:
                r.product_qty = r.product_qty2 * r.product_id.conversion_rate

    @api.onchange('product_uom2','price_unit2')  # if these fields are changed, call method
    def _convert_price(self):
        for r in self:
            if r.price_unit2 > 0:
                r.price_unit = r.price_unit2 / r.product_id.conversion_rate

    @api.onchange('product_uom','price_unit')  # if these fields are changed, call method
    def _convert_price2(self):
        for r in self:
            if r.price_unit > 0:
                r.price_unit2 = r.price_unit * r.product_id.conversion_rate

    @api.model
    def _sync_purchase_line_data(self):
        # update line consigment khusus PRC dari wipro
        self.env.cr.execute("""
            UPDATE purchase_order_line AS a set 
                is_consignment = (case 
                    when a.is_consignment is not True
                    then (case
                            when b.name like 'CL-%' then True
                            when b.name like 'KN-%' then True
                            when b.name like 'BP-CL-%' then True
                            when b.name like 'BP-KN-%' then True
                            when b.name like 'IN-CL-%' then True  
                            when b.name like 'IN-KN-%' then True
                            else False
                        end)                
                    else a.is_consignment end)
            from product_template b 
            inner join product_product c 
                on c.product_tmpl_id=b.id
            where c.id = a.product_id
                and a.is_consignment is not True
                and (a.is_consignment is not True)
                and (a.name like 'PRC%' or a.name like 'PRT%')
                and a.sync_type in ('1','2')
        """)

        self.env.cr.execute("""
            UPDATE purchase_order_line
            set price_tax = has_tax 
            where sync_date is not null 
              and has_tax is not null
              and price_tax is null
              and sync_type in ('1','2') """)

        # self.env.cr.execute("""
        #     UPDATE purchase_order_line
        #     set discount_value = ((coalesce(discount_persen,0) / 100) * price_unit)
        #     where sync_date is not null
        #         and discount_value is null""")

        # ini maksud nya apa ??
        # self.env.cr.execute("""
        #     UPDATE purchase_order_line
        #     set discount_value = ((coalesce(discount_persen,0) / 100) * price_unit)
        #     where sync_date is not null
        #         and discount_value < 1""")

        self.env.cr.execute("""
            UPDATE purchase_order_line
            set discount_total = discount_value  * product_qty 
            where sync_date is not null 
                and discount_value is not null
                and discount_total is null
                and sync_type in ('1','2')
        """)

        self.env.cr.execute("""
            UPDATE purchase_order_line
            set price_subtotal = ((price_unit * product_qty) - coalesce(discount_total, 0) + coalesce(price_tax, 0)),
                price_total = ((price_unit * product_qty) - coalesce(discount_total, 0) + coalesce(price_tax, 0))
            where sync_date is not null
                and sync_type in ('1','2')
        """)

        self.env.cr.execute("""
            UPDATE purchase_order AS a set 
                amount_untaxed = b.amount_untaxed,
                total_tampilan = b.amount_untaxed,
                total_discount = b.total_discount,
                ppn = b.ppn,
                pph = 0,
                amount_total = b.amount_total
            from (
                select order_id,
                    sum(coalesce(price_unit,0) * coalesce(product_qty,0)) amount_untaxed,
                    sum(coalesce(discount_total,0)) total_discount,
                    sum(coalesce(price_tax,0)) ppn,
                    sum(coalesce(price_total,0)) amount_total
                from purchase_order_line 
                group by order_id 
            ) b 
            where b.order_id = a.id
                and a.sync_id is not null 
                and a.sync_date is not null
                and a.total_tampilan is null
                and a.sync_type in ('1','2')
            """)

        #PPN MHJS
        self.env.cr.execute("""
            INSERT into account_tax_purchase_order_line_rel (
                purchase_order_line_id, account_tax_id)
            SELECT 
                a.id as purchase_order_line_id, 
                b.id as account_tax_id 
            FROM purchase_order_line a 
            LEFT JOIN account_tax b on b.id = 4
            WHERE a.sync_type = '1' 
                AND a.has_tax > 0 
                AND NOT EXISTS (
                    SELECT 1 
                    FROM account_tax_purchase_order_line_rel t
                    WHERE t.purchase_order_line_id=a.id)
            """)

        #PPN MHTG
        self.env.cr.execute("""
            INSERT into account_tax_purchase_order_line_rel (
                purchase_order_line_id, account_tax_id)
            SELECT 
                a.id as purchase_order_line_id, 
                b.id as account_tax_id 
            FROM purchase_order_line a 
            LEFT JOIN account_tax b on b.id = 5 
            WHERE a.sync_type = '2' 
                AND a.has_tax > 0 
                AND NOT EXISTS (
                    SELECT 1 
                    FROM account_tax_purchase_order_line_rel t
                    WHERE t.purchase_order_line_id=a.id)
            """)

        # update wipro grn date
        self.env.cr.execute("""
            UPDATE purchase_order_line AS a
            set wipro_date = b.wipro_date 
            from purchase_order b 
            where b.id = a.order_id
                and a.wipro_date is null and b.name like 'PRC%'
                and a.sync_type in ('1','2')
            """)

        self.env.cr.execute("""
            UPDATE purchase_order_line AS a 
            set partner_id = b.partner_id 
            from purchase_order b 
            where b.id=a.order_id
                and a.partner_id is null
                and a.sync_type in ('1','2')
            """)

        self.env.cr.execute("""
            UPDATE purchase_order_line AS a 
            set product_categ_id = b.categ_id 
            from product_template b 
            inner join product_product c 
                on c.product_tmpl_id = b.id
            where c.id = a.product_id
                and a.product_categ_id is null
                and a.sync_type in ('1','2') """)


    @api.model
    def _sync_purchase_line_wipro(self, sync_type='1'):
        # sync_ids = {record['sync_id']: record['id'] for record in self.sudo().search_read([('sync_type', '=', sync_type), ('sync_id', '>', 0)], ['id', 'sync_id'])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
        data = []
        date = '' + (datetime.now() + timedelta(hours=7) - timedelta(days=1)).strftime('%Y-%m-%d')
        # date = '2019-01-25'
        query = """
            SELECT 
                a.order_id, 
                a.sync_id,
                a.order_no,
                a.order_date,
                a.is_consignment,
                a.product_id,
                a.name,
                a.product_uom,
                a.uom_name,
                a.batch_id as batch_no,
                a.product_qty,
                a.price_unit,
                a.discount_persen,
                a.discount_value,
                a.discount_total,
                a.tax_persen,
                a.tax_value,
                a.has_tax,
                a.price_tax,
                a.price_nett,
                a.price_total,
                a.price_subtotal,
                a.PackId,
                a.PRType,
                a.partner_ref
            FROM dbo.VRP_OdooModPurchaseReceiptItemsLowest a 
            WHERE a.wipro_date = '%s'
            """ % (date)
        print (query)
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
        now = datetime.now().strftime('%Y%m%d %H:%M:%S')
        date_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        dbname = self.env.cr.dbname
        login = self.sudo().env.user.login
        import odoorpc
        request = odoorpc.ODOO('localhost', port=8085, timeout=5000)
        request.login(dbname, login, 'mayapada@hospital2018')
        env = request.env

        #uom_id = self.env.ref('product.product_uom_categ_unit').id
        #new_sync_ids = []
        #@asyncio.coroutine
        def process_query(object, result):
            #object['sync_id'] = float(object['sync_id'])
            #new_sync_ids += [object['sync_id']]
            for value in default_values:
                object[value] = default_values[value]
            order_id = object['order_id']
            object['order_id'] = env['purchase.order'].search([('sync_id', '=', object['order_id']), ('sync_type', '=', sync_type), ('wipro_type', '=', 'RECEIPT')], limit=1) or None
            if not object['order_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(datetime.now()) + " purchase.order with sync_id %s and sync_type %s doesn't exist" % (order_id, sync_type))
                return
            product_id = object['product_id']
            object['product_id'] = env['product.product'].search([('sync_id', '=', object['product_id']), ('sync_type', '=', sync_type), ('sync_is_service', '=', False), ('sync_is_package', '=', False)], order="id asc", limit=1) or None
            if not object['product_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(datetime.now()) + " product.te,plate with sync_id %s and sync_type %s doesn't exist" % (product_id, sync_type))
                return
            # object['product_id'] = env['product.product'].browse(object['product_id'])
            if not object['price_unit']:
                object['price_unit'] = 0
            object['product_uom'] = env['uom.uom'].search( [('sync_id', '=', object['product_uom']), ('sync_type', '=', sync_type)], order="id asc", limit=1) or env['uom.uom'].search( [('sync_id', '=', 163), ('sync_type', '=', sync_type)], limit=1)
            if not object['date_planned']:
                object['date_planned'] = now
            # if object['sync_id'] in sync_ids:
            #    object['id'] = sync_ids[object['sync_id']]
            # else:
            object['id'] = 'DEFAULT'
            object['sync_date'] = date_now
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
        # print values
        if not values:
            print ("No values available")
            return
        query = "INSERT into purchase_order_line %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)


    @api.model
    def _sync_purchase_line_return_wipro(self, sync_type='1'):
        # sync_ids = {record['sync_id']: record['id'] for record in self.sudo().search_read([('sync_type', '=', sync_type), ('sync_id', '>', 0)], ['id', 'sync_id'])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
        data = []
        date = '' + (datetime.now() + timedelta(hours=7) - timedelta(days=1)).strftime('%Y-%m-%d')
        # date = '2019-01-25'
        query_return = """
            SELECT
                a.order_id,
                a.sync_id,
                a.order_no,
                a.order_date,
                a.is_consignment,
                a.product_id,
                a.name,
                a.product_uom,
                a.uom_name,
                a.batch_id as batch_no,
                a.product_qty,
                a.price_unit,
                a.discount_persen,
                a.discount_value,
                a.discount_total,
                a.tax_persen,
                a.tax_value,
                (a.has_tax * -1) has_tax,
                (a.price_tax * -1) price_tax,
                a.price_nett,
                a.price_total,
                a.price_subtotal,
                a.PackId,
                a.ReturnType,
                a.PRType,
                a.POTypeName,
                a.PRID,
                a.POID,
                a.partner_ref,
                a.PODate 
            FROM dbo.VRP_OdooPurchaseReturnItemsLowest a
            WHERE convert(varchar(10), a.order_date, 121) = '%s'
         """ % (date)
        data += sync.get_data(sync.servers.get(sync_type), query_return)
        print (data)
        if not data:
            print ("No data available")
            return
        fields_without_id = tuple(
            key for key in self._fields
            if key != 'id' and 'property' not in key and 'ids' not in key
            and self._fields[key].required == True
            and self._fields[key].store == True)
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
        now = datetime.now().strftime('%Y%m%d %H:%M:%S')
        date_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        dbname = self.env.cr.dbname
        login = self.sudo().env.user.login
        import odoorpc
        request = odoorpc.ODOO('localhost', port=8085, timeout=5000)
        request.login(dbname, login, 'mayapada@hospital2018')
        env = request.env

        #uom_id = self.env.ref('product.product_uom_categ_unit').id
        #new_sync_ids = []
        #@asyncio.coroutine
        def process_query(object, result):
            #object['sync_id'] = float(object['sync_id'])
            #new_sync_ids += [object['sync_id']]
            for value in default_values:
                object[value] = default_values[value]
            order_id = object['order_id']
            object['order_id'] = env['purchase.order'].search([('sync_id', '=', object['order_id']), ('sync_type', '=', sync_type), ('wipro_type', '=', 'RETURN')], limit=1) or None
            if not object['order_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(datetime.now()) + " purchase.order with sync_id %s and sync_type %s doesn't exist" % (order_id, sync_type))
                return
            product_id = object['product_id']
            object['product_id'] = env['product.product'].search([('sync_id', '=', object['product_id']), ('sync_type', '=', sync_type), ('sync_is_service', '=', False), ('sync_is_package', '=', False)], order="id asc", limit=1) or None
            if not object['product_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(datetime.now()) + " product.te,plate with sync_id %s and sync_type %s doesn't exist" % (product_id, sync_type))
                return
            # object['product_id'] = env['product.product'].browse(object['product_id'])
            if not object['price_unit']:
                object['price_unit'] = 0
            object['product_uom'] = env['uom.uom'].search([('sync_id', '=', object['product_uom']), ('sync_type', '=', sync_type)], order="id asc", limit=1) or env['uom.uom'].search([('sync_id', '=', 163), ('sync_type', '=', sync_type)], limit=1)
            if not object['date_planned']:
                object['date_planned'] = now
            # if object['sync_id'] in sync_ids:
            #    object['id'] = sync_ids[object['sync_id']]
            # else:
            object['id'] = 'DEFAULT'
            object['sync_date'] = date_now
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
        # print values
        if not values:
            print ("No values available")
            return
        query = "INSERT into purchase_order_line %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)
        

    #START OF QUERY MANUAL
    @api.model
    def _sync_purchase_line_wipro_manual(self, sync_type='1', date_start='2019-01-01', date_end='2019-01-01'):
        # sync_ids = {record['sync_id']: record['id'] for record in self.sudo().search_read([('sync_type', '=', sync_type), ('sync_id', '>', 0)], ['id', 'sync_id'])}
        sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
        data = []
        date = '' + (datetime.now() + timedelta(hours=7) - timedelta(days=1)).strftime('%Y-%m-%d')
        # date = '2019-01-25'
        query = """
            SELECT 
                a.order_id, 
                a.sync_id,
                a.order_no,
                a.order_date,
                a.is_consignment,
                a.product_id,
                a.name,
                a.product_uom,
                a.uom_name,
                a.batch_id batch_no,
                a.product_qty,
                a.price_unit,
                a.discount_persen,
                a.discount_value,
                a.discount_total,
                a.tax_persen,
                a.tax_value,
                a.has_tax,
                a.price_tax,
                a.price_nett,
                a.price_total,
                a.price_subtotal,
                a.PackId,
                a.PRType,
                a.partner_ref
            FROM dbo.VRP_OdooModPurchaseReceiptItemsLowest a 
            WHERE a.wipro_date >= '%s' and a.wipro_date <= '%s'
            """ % (date_start, date_end)
        print (query)
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
        columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
        fields_without_id += columns
        columns += tuple( key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
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
        now = datetime.now().strftime('%Y%m%d %H:%M:%S')
        date_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        dbname = self.env.cr.dbname
        login = self.sudo().env.user.login
        import odoorpc
        request = odoorpc.ODOO('localhost', port=8085, timeout=5000)
        request.login(dbname, login, 'mayapada@hospital2018')
        env = request.env

        #uom_id = self.env.ref('product.product_uom_categ_unit').id
        #new_sync_ids = []
        #@asyncio.coroutine
        def process_query(object, result):
            #object['sync_id'] = float(object['sync_id'])
            #new_sync_ids += [object['sync_id']]
            for value in default_values:
                object[value] = default_values[value]
            order_id = object['order_id']
            object['order_id'] = env['purchase.order'].search([('sync_id', '=', object['order_id']), ('sync_type', '=', sync_type), ('wipro_type', '=', 'RECEIPT')], limit=1) or None
            if not object['order_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(datetime.now()) + " purchase.order with sync_id %s and sync_type %s doesn't exist" % (order_id, sync_type))
                return
            product_id = object['product_id']
            object['product_id'] = env['product.product'].search([('sync_id', '=', object['product_id']), ('sync_type', '=', sync_type), ('sync_is_service', '=', False), ('sync_is_package', '=', False)], order="id asc", limit=1) or None
            if not object['product_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write( '\n' + str(datetime.now()) + " product.te,plate with sync_id %s and sync_type %s doesn't exist" % (product_id, sync_type))
                return
            # object['product_id'] = env['product.product'].browse(object['product_id'])
            if not object['price_unit']:
                object['price_unit'] = 0
            object['product_uom'] = env['uom.uom'].search( [('sync_id', '=', object['product_uom']), ('sync_type', '=', sync_type)], order="id asc", limit=1) or env['uom.uom'].search([('sync_id', '=', 163), ('sync_type', '=', sync_type)], limit=1)
            if not object['date_planned']:
                object['date_planned'] = now
            # if object['sync_id'] in sync_ids:
            #    object['id'] = sync_ids[object['sync_id']]
            # else:
            object['id'] = 'DEFAULT'
            object['sync_date'] = date_now
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
        # print values
        if not values:
            print ("No values available")
            return
        query = "INSERT into purchase_order_line %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        open('/opt/odoo16/logs/query_po_line.log','a+').write(query.encode('utf8'))
        self.env.cr.execute(query)

    #END OF QUERY MANUAL



class PurchaseApproval(models.Model):
    _name = 'purchase.approval'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")

    name = fields.Char(string="Rule Name")
    rule_name = fields.Char(string="Name", compute='_rule_name', store=True)
    min_amount = fields.Float(string="Minimum Amount", required=True)
    max_amount = fields.Float(string="Maximum Amount", required=True)
    rule_ids = fields.One2many('purchase.approval.rule','approval_id',string="Rules")
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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'purchase.approval' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'purchase.approval'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        result = super(PurchaseApproval, self).create(vals)
        result.send_api_consol()
        for tes_loop in result.rule_ids:
            tes_loop.send_api_consol()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " +str(result.id)

        open(log_file, 'a').write(message_log)
        return result

    # @api.multi
    def send_api_consol(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUKK SINI ")
        for record in self:
            list_company = ''
            company = self.env['res.company'].search([('sync_consol_purchase_approval','=',True)])
            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_purchase_approval
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/create/purchase.approval"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/create/purchase.approval"
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
                            #for d in json_resp['data']:
                                #if 'id' in d:
                                #open('/opt/odoo16/logs/dump.log', 'a+').write('\n' + str(d))
                                #open('/opt/odoo16/logs/dump.log', 'a+').write('\n' + d['id'])
                            if json_resp['data']['id']:
                                response_id = json_resp['data']['id']
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

                    super(PurchaseApproval, self).write(data_update)

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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'purchase.approval' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'purchase.approval'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        result = super(PurchaseApproval, self).write(vals)
        self.send_api_consol_write()
        for tes_loop in self.rule_ids:
            tes_loop.send_api_consol_write()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Write before return" + "\n ID: " +str(self.id)

        open(log_file, 'a').write(message_log)
        return result
    
    
    # @api.multi
    def send_api_consol_write(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            company = self.env['res.company'].search([('sync_consol_purchase_approval','=',True)])
            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_purchase_approval
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/write/purchase.approval"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/write/purchase.approval"
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

                    super(PurchaseApproval, self).write(data_update)

    # @api.one
    @api.depends('name', 'min_amount', 'max_amount')
    def _rule_name(self):
        name = False
        if not self.name:
            name = ""
        else:
            name = self.name + " "
        self.rule_name = name + "%s - %s" % (self.min_amount, self.max_amount)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(PurchaseApproval,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'tree':
            res['arch'] = '''
                <tree string="Purchase Approval" delete="false">
                    <field name="name"/>
                    <field name="min_amount"/>
                    <field name="max_amount"/>
                    <field name="sync_type"/>
                </tree>
           '''
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res





class PurchaseApprovalRule(models.Model):
    _name = 'purchase.approval.rule'
    _order = 'sequence'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")


    approval_id = fields.Many2one('purchase.approval', string="Approval Rule")
    position_id = fields.Many2one('res.position', string="Position")
    sequence = fields.Integer(string="Sequence", default=1)
    enabled = fields.Boolean(string="Enabled", default=True)
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)

    # @api.multi
    def unlink(self):
        self.send_api_consol_delete()
        result = super(PurchaseApprovalRule, self).unlink()

    # @api.multi
    def send_api_consol_delete(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            company = self.env['res.company'].search([('sync_consol_purchase_approval','=',True)])
            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_purchase_approval
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/unlink/purchase.approval.rule"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/unlink/purchase.approval.rule"
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
                    values['enabled'] = record.enabled

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
                        
                            
                        if json_resp['status'] == 'error':
                            # raise exceptions.ValidationError(_('Data Gagal Dibuat'))
                            raise exceptions.ValidationError(_(json_resp['message']))

        super(PurchaseApprovalRule, self).unlink()


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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'purchase.approval.rule' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'purchase.approval.rule'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        result = super(PurchaseApprovalRule, self).create(vals)
        result.send_api_consol()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " +str(result.id)

        open(log_file, 'a').write(message_log)
        return result

    # @api.multi
    def send_api_consol(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            company = self.env['res.company'].search([('sync_consol_purchase_approval','=',True)])
            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_purchase_approval
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/create/purchase.approval.rule"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/create/purchase.approval.rule"
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
                    values['enabled'] = record.enabled

                    if record.approval_id.id == False:
                        values['approval_id'] = record.approval_id.id
                    else:
                        values['approval_id'] = str(record.approval_id.id)
                    if record.position_id.id == False:
                        values['position_id'] = record.position_id.id
                    else:
                        values['position_id'] = str(record.position_id.id)
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

                    super(PurchaseApprovalRule, self).write(data_update)

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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'purchase.approval.rule' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'purchase.approva.rule'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        result = super(PurchaseApprovalRule, self).write(vals)
        self.send_api_consol_write()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Write before return" + "\n ID: " +str(self.id)

        open(log_file, 'a').write(message_log)
        return result

    # @api.multi
    def send_api_consol_write(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            company = self.env['res.company'].search([('sync_consol_purchase_approval','=',True)])
            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_purchase_approval
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/write/purchase.approval.rule"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/write/purchase.approval.rule"
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
                    values['enabled'] = record.enabled

                    if record.approval_id.id == False:
                        values['approval_id'] = record.approval_id.id
                    else:
                        values['approval_id'] = str(record.approval_id.id)
                    if record.position_id.id == False:
                        values['position_id'] = record.position_id.id
                    else:
                        values['position_id'] = str(record.position_id.id)
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

                    super(PurchaseApprovalRule, self).write(data_update)







class PurchaseType(models.Model):
    _name = 'purchase.type'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")

    name = fields.Char(string="Type", required=True)
    approval_ids = fields.Many2many('purchase.approval',string="Approval Rules")
    purchase_type = fields.Selection([('po', 'Purchase Order'),('pr', 'Purchase Requisition'),('payment', 'Payment Voucher'), ('costing', 'Costing Package'), ('memorial', 'Memorial/Reverse/Adjustment')],string="Purchase Type")
    company_id = fields.Many2one('res.company',string='Company',required=True)
    department_id = fields.Many2one('hr.department',string="Department",domain=[('is_user', '=', True)])
    item_type = fields.Selection([('1', 'CAPEX & OPEX'),('3', 'Medis (Stock)'),('5', 'Non Medis (Stock)')],string='Item Type',required=True)

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)
    active = fields.Boolean(string="Active", default=True)

    pr_it_type = fields.Selection([('infra', 'PR IT Infra'), ('apps', 'PR IT Apps')],string='PR IT Type')

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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'purchase.type' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'purchase.type'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        result = super(PurchaseType, self).create(vals)
        if vals.get('company_id'):
            company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
            result.sync_type = company_id.sync_type
        if result.trigger_create == False:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger create purchase type")
            result.send_api_consol_company()
            result.send_api_consol_many2many()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " +str(result.id)

        open(log_file, 'a').write(message_log)
        return result

    # @api.multi
    def send_api_consol_company(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            list_company += str(record.company_id.name) + ', '+ '\n'
            consol_active = record.company_id.sync_consol_purchase_type
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/purchase.type"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/purchase.type"
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
                values['purchase_type'] = record.purchase_type
                values['trigger_create'] = True
                if record.department_id.id == False:
                    values['department_id'] = record.department_id.id
                else:
                    values['department_id'] = str(record.department_id.id)

                values['item_type'] = record.item_type
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

                super(PurchaseType, self).write(data_update)

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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'purchase.type' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'purchase.type'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        result = super(PurchaseType, self).write(vals)
        if self.env.context.get('ganti_nama'): return result
        self = self.with_context(ganti_nama=True)
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "write purchase type")
        if self.company_id:
            self.sync_type = self.company_id.sync_type
        if self.trigger_write == True:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger write purchase type")
            query = """
            UPDATE purchase_type set trigger_write = false
            WHERE id = {self_id}""".format(self_id = self.id)
            self.env.cr.execute(query)
            self.send_api_consol_write_company()
        self.send_api_consol_many2many()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Write before return" + "\n ID: " +str(self.id)

        open(log_file, 'a').write(message_log)
        return result
    
    
    # @api.multi
    def send_api_consol_write_company(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            list_company += str(record.company_id.name) + ', '+ '\n'
            consol_active = record.company_id.sync_consol_purchase_type
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/purchase.type"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/purchase.type"
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
                values['purchase_type'] = record.purchase_type
                values['trigger_write'] = False
                if record.department_id.id == False:
                    values['department_id'] = record.department_id.id
                else:
                    values['department_id'] = str(record.department_id.id)

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

                values['item_type'] = record.item_type

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

                super(PurchaseType, self).write(data_update)

    # @api.multi
    def send_api_consol_many2many(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_purchase_type
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api_many2many/unit/write/type"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api_many2many/main/write/type"
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
                        values['purchase_approval_id'] = str(loop.id)
                        values['purchase_type_id'] = str(record.id)
                        values_array.append(values)
                        body['values'] = values_array
                else:
                    values = {}
                    values['sync_type'] = False
                    values['purchase_approval_id'] = False
                    values['purchase_type_id'] = self.id
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

                super(PurchaseType, self).write(data_update)


    @api.onchange('sync_type', 'name','purchase_type','department_id','item_type','company_id')
    def onchange_trigger_write(self):
        self.trigger_write = True

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(PurchaseType,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'tree':
            res['arch'] = '''
                <tree string="Purchase Type" delete="false">
                    <field name="name"/>
                    <field name="purchase_type"/>
                    <field name="department_id"/>
                    <field name="item_type"/>
                    <field name="company_id"/>
                    <field name="sync_type"/>
                </tree>
           '''
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res





class PurchaseRequest(models.Model):
    _inherit = 'purchase.requisition'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")

    @api.model
    def _get_picking_in(self):
        # pick_in = self.env.ref('stock.picking_type_in')
        # if not pick_in:
        # company = self.env['res.company']._company_default_get('purchase.requisition')
        pick = self.env['stock.picking.type'].search(
            [('warehouse_id.company_id', '=', self.company_id.id), ('code', '=', 'incoming')], #, ('item_type', '=', self.item_type)],
            limit=1
        )
        return pick
    

    @api.model
    def _get_user(self):
        return self.env.user.id


    name = fields.Char(string='PR Number', required=False, copy=False, default=False)
    type_pr = fields.Selection([('1', 'Repeat Order'), ('2', 'Normal')], string="Type PR")
    item_type = fields.Selection([('1', 'CAPEX & OPEX')],string='Item Type',required=True)
    user_id = fields.Many2one('res.users', string='Responsible', default=_get_user, store=True)

    approval_type_id = fields.Many2one('purchase.type', string="Approval Type",required=False,readonly=True,domain=[('purchase_type', '=', 'pr')],compute='_compute_approve_type', store=False)
    approve_id = fields.Many2one('purchase.approval', string="Approval Level Rule",readonly=True,compute='_approval',store=False,copy=False)
    approve_rule_id = fields.Many2one('purchase.approval.rule', string="Rule",readonly=True,store=True,copy=False)
    approve_status = fields.Char(string="Approval Status", readonly=True,related='approve_rule_id.position_id.name',store=True,copy=False)
    approve_next = fields.Char(string="Next Approval", readonly=True,compute='_approval',store=False,copy=False)
    approve_next_store = fields.Char(string="Stored Next Approval", readonly=False,store=True)
    
    revisi = fields.Boolean(string="Revisi", readonly=True)
    revisi_name = fields.Char(string="Revisi Name", readonly=True)
    revisi_sequence = fields.Integer(string="Revisi Sequence", readonly=True)
    picking_type_id = fields.Many2one('stock.picking.type', string="Picking Type", required=False, readonly=False)
    ordering_date = fields.Date(string="Ordering Date",default=lambda self: datetime.now())
    approval_date = fields.Date(string="Confirmed Date", readonly=True, default=lambda self: datetime.now())
    state = fields.Selection([('draft', 'Draft'), ('in_progress', 'Confirmed'),('open', 'RFQ Created'), ('done', 'PO Completed'), ('cancel', 'Cancelled')], 'Status', tracking=True, copy=False, default='draft')
    status = fields.Selection([('draft', 'Draft'),('waiting', 'Waiting for Approval'),('approved', 'Approved'),('in_progress', 'Confirmed'),('open', 'RFQ Created'),('done', 'PO Completed'),('cancel', 'Cancelled')],string='Status',readonly=True,compute='_status',store=False,copy=False)
    
    # delivery_date = fields.Datetime(string="Delivery Date")
    account_analytic_id = fields.Many2one('account.analytic.account', string="Analytic Account", domain=[('approved_budget_ids', '!=', False)])
    # cashflow_line_ids = fields.One2many('cashflow.line','purchase_requisition_id',string="Cashflow")
    budget_total = fields.Float(string="Budget Total", readonly=True)
    remaining_budget = fields.Float(string="Remaining Budget", readonly=True)
    # budget_total = fields.Float(string="Budget Total", readonly=True, compute='_compute_budget')
    # remaining_budget = fields.Float(string="Remaining Budget", readonly=True, compute='_compute_budget')
    
    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    analytic_ids = fields.Many2many('account.analytic.account', string="Analytic Users")

    reject_reason = fields.Char(string='Reject Reason')
    reject_state = fields.Selection([('draft', 'Draft'), ('in_progress', 'Confirmed'),('open', 'RFQ Created'), ('done', 'PO Completed'), ('cancel', 'Cancelled')], 'Status', tracking=True, copy=False, default='draft', required=True)

    is_user_it = fields.Boolean(string="Is User IT?")
    is_ask_approval = fields.Boolean(string="Is Ask Approval?", default=False, readonly=True)
    pr_it_type = fields.Selection([('infra', 'PR IT Infra'), ('apps', 'PR IT Apps')],string='PR IT Type')

    pending_request_date = fields.Datetime(string="Pending PR Date")
    complete_request_date = fields.Datetime(string="Complete PR Date")
    lock_pr = fields.Boolean(string="Lock PR")
    

    def action_send_requisition_email(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        for rec in self:
            if not rec.user_id or not rec.user_id.email:
                raise UserError(_("Responsible user has no email address."))

            pr_url = f"{base_url}/web#id={rec.id}&model={rec._name}&view_type=form"

            body_html = f"""
                <p>Dear {rec.user_id.name},</p>
                <p>
                    Silahkan proses <strong>Purchase Request</strong> yang telah anda buat, 
                    klik tombol <strong>"Ask Approval"</strong> untuk memulai proses approval pada PR, 
                    atau klik <strong>"Cancel Call"</strong> untuk membatalkan PR jika sudah tidak digunakan kembali.
                </p>
                <p>
                    <a href="{pr_url}" target="_blank" style="
                        display: inline-block;
                        padding: 10px 20px;
                        background-color: #1abc9c;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        font-weight: bold;">
                        {rec.name}
                    </a>
                </p>
            """

            mail_values = {
                'subject': f'Notification Odoo: {rec.name}',
                'body_html': body_html,
                'email_from': 'odoo@mayapadahospital.com',
                'email_to': rec.user_id.email,
                'auto_delete': True,
                'model': rec._name,
                'res_id': rec.id,
            }

            rec.env['mail.mail'].create(mail_values).send()
            rec.pending_request_date = tools.datetime.now()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Email sent successfully.',
                'type': 'success',
                'sticky': False,
            }
        }





    def action_send_requisition_to_po_email(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
    
        for rec in self:
            notification_setting = rec.sudo().env['purchase.notification.setting'].search(
                [('company_id', '=', rec.company_id.id)], limit=1)
            if not notification_setting:
                raise UserError(_("Notification Setting Not Found."))

            recipient_emails = notification_setting.user_ids.mapped('partner_id.email')

            if not recipient_emails:
                raise UserError(_("Selected users have no email addresses."))

            pr_url = f"{base_url}/web#id={rec.id}&model={rec._name}&view_type=form"


            body_html = f"""
                <p>Dear Procurement,</p>
                <p>Silahkan proses lebih lanjut untuk Purchase Request yang sudah selesai proses approval berikut ini:</p>
                <p>
                    <a href="{pr_url}" target="_blank" style="
                        display: inline-block;
                        padding: 10px 20px;
                        background-color: #1abc9c;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        font-weight: bold;">
                        {rec.name}
                    </a>
                </p>
                <p>Terima kasih.</p>
            """

            mail_values = {
                'subject': f'Notification Odoo: {rec.name}',
                'body_html': body_html,
                'email_from': 'odoo@mayapadahospital.com',
                'email_to': ','.join(recipient_emails),
                'auto_delete': True,
                'model': rec._name,
                'res_id': rec.id,
            }

            rec.env['mail.mail'].create(mail_values).send()
            rec.complete_request_date = tools.datetime.now()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Email sent to: {", ".join(recipient_emails)}',
                'type': 'success',
                'sticky': False,
            }
        }





    # 2021.09.30 - Fungsi ini tidak dipakai karena satu PR bisa multi budget mapping 
    # @api.one
    def _compute_budget(self):
        if self.account_analytic_id:
            for r in self:
                for budget in r.account_analytic_id.crossovered_budget_line:
                    r.budget_total += abs(budget.planned_amount)
                    r.remaining_budget += abs(budget.remain_amount)


    # @api.multi
    def function_consol(self, function=False):
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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'function' + '/' + 'purchase.requisition' + '/'
        log_name = log_date + '_' + 'function' + '_' + 'purchase.requisition'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Function "

        open(log_file, 'a').write(message_log)
        for record in self:
            consol_active = record.company_id.sync_consol_purchase_requisition
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            name_function = function
            if consol_active and consol_type == 'main':
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/call_function/unit/purchase.requisition"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/call_function/main/purchase.requisition"
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
                query = """
                    update res_users set company_id = (select(id) from res_company where name = '{company_name}') where id = {sync_consol_id_main}
                    """.format(company_name=self.env.company.name, sync_consol_id_main=int(self.env.user.sync_consol_id_main))
                body['query'] = query
                company_name = record.company_id.name
                sync_consol_id_main = str(self.env.user.login)
                body['company_name'] = company_name
                    
                body['user_id'] = sync_consol_id_main
                body['function'] = name_function
                cookies = {'session_id': self.env.user.cookies}
                print(body)
                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                json_resp = response_json.json()
                # self.env.user.sync_consol_response = json_resp
                log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
                message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
                message_log += "\n\nuser: " + self.env.user.login + "\n\n End Function"

                open(log_file, 'a').write(message_log)


    # @api.multi
    def set_rfq_created(self):
        self.function_consol(function="set_rfq_created_consol")
        self.sudo().write({'state': 'open'})


    # @api.multi
    def set_rfq_created_consol(self):
        self.sudo().write({'state': 'open'})


    # @api.multi
    def set_po_completed(self):
        self.function_consol(function="set_po_completed_consol")
        self.sudo().write({'state': 'done'})

    # @api.multi
    def set_po_completed_consol(self):
        self.sudo().write({'state': 'done'})



    # @api.multi
    def set_pr_lock(self):
        self.sudo().write({'state': 'done',
                           'lock_pr': True})


    # @api.multi
    def action_reject(self):
        self.function_consol(function="action_reject_consol")
        now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
        self.message_post(body='This PR Rejected by ' + self.env.user.name + " at " + now, message_type='notification', content_subtype='plaintext', subtype_id=False)
        self.sudo().write({'state': 'draft',
                            'approve_rule_id': False,
                            'approve_next_store': False,
                            'approve_status': False})


    # @api.multi
    def action_reject_consol(self):
        now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
        self.message_post(body='This PR Rejected by ' + self.env.user.name + " at " + now, message_type='notification', content_subtype='plaintext', subtype_id=False)
        self.sudo().write({'state': 'draft',
                            'approve_rule_id': False,
                            'approve_next_store': False,
                            'approve_status': False})


    @api.onchange('company_id', 'item_type')
    def _onchange_picking_type(self):
        picking = self.env['stock.picking.type'].search([('code', '=', 'incoming'), ('warehouse_id.company_id', '=', self.company_id.id), ('item_type', '=', self.item_type)],limit=1)
        self.picking_type_id = picking.id
        # return picking

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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'purchase.requisition' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'purchase.requisition'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        # try:
        # for record in self:
        # picking = self.env['stock.picking.type'].search([('code', '=', 'incoming'), ('warehouse_id.company_id', '=', self.company_id.id), ('item_type', '=', self.item_type)], limit=1)
        # self.picking_type_id = picking.id
        # picking = self.env['stock.picking.type'].search([('code', '=', 'incoming'), ('warehouse_id.company_id', '=', self.company_id.id), ('item_type', '=', self.item_type)], limit=1)
        result = super(PurchaseRequest, self).create(vals)
        if result.trigger_create == False:
            result.name = self.env['ir.sequence'].sudo().next_by_code('purchase.order.requisition')
        # result.picking_type_id = picking.id
        if vals.get('company_id'):
            company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
            result.sync_type = company_id.sync_type
            # if company_id.id == 16 and company_id.sync_consol_type == 'main':
            #     raise exceptions.ValidationError("Not Allowed to Create PR/PO for Surabaya, Please Create PR/PO on Odoo MHSB http://10.5.1.79")
            #if company_id.id == 8 and company_id.sync_consol_type == 'unit':
            #    raise exceptions.ValidationError("Not Allowed to Create PR/PO for MHTG-Corporate, Please Create PR/PO on Odoo MHTG-Corporate https://erp.ad.mayapadahospital.com")

        if result.trigger_create == False:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger create purchase requisition")
            result.send_api_consol_company()
            for tes_loop in result.line_ids:
                tes_loop.send_api_consol_company()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " +str(result.id)

        open(log_file, 'a').write(message_log)
        return result
        # picking = result.env['stock.picking.type'].search([('code', '=', 'incoming'), ('warehouse_id.company_id', '=', self.company_id.id), ('item_type', '=', self.item_type)], limit=1)
        # result.update({'picking_type_id': picking.id})
        # result._onchange_picking_type()

    # except:
    #     import traceback
    #     raise UserError(traceback.format_exc())


    # @api.multi
    def send_api_consol_company(self):
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str("creat PR"))
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_purchase_requisition
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/purchase.requisition"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/purchase.requisition"
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

                if record.company_id.sync_consol_type == 'unit':

                    if record.user_id.id == False:
                        values['user_id'] = record.user_id.id
                    else:
                        values['user_id'] = str(int(record.user_id.sync_consol_id_main))
                
                if record.company_id.sync_consol_type == 'main':

                    if record.user_id.id == False:
                        values['user_id'] = record.user_id.id
                    else:
                        values['user_id'] = str(record.user_id.id)

                # if record.company_id.id == False:
                #     values['company_id'] = record.company_id.id
                # else:
                #     values['company_id'] = str(record.company_id.id)


                values['type_pr'] = record.type_pr
                values['item_type'] = record.item_type
                values['ordering_date'] = record.ordering_date
                values['approval_date'] = record.approval_date
                # values['origin'] = str(record.origin)
                if record.origin:
                    values['origin'] = str(record.origin)
                else:
                    values['origin'] = ''
                values['trigger_create'] = True
                if record.reject_reason:
                    values['reject_reason'] = str(record.reject_reason)
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
                super(PurchaseRequest, self).write(data_update)


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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'purchase.requisition' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'purchase.requisition'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        result = super(PurchaseRequest, self).write(vals)
        if self.env.context.get('writed'):
            return result

        self = self.with_context(writed=True)
        # if self.company_id:
        #     self.sync_type = self.company_id.sync_type
        if self.trigger_write == True:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger write purchase request")
            query = """
            UPDATE purchase_requisition set trigger_write = false
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
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_purchase_requisition
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/purchase.requisition"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/purchase.requisition"
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

                if record.company_id.sync_consol_type == 'unit':

                    if record.user_id.id == False:
                        values['user_id'] = record.user_id.id
                    else:
                        values['user_id'] = str(int(record.user_id.sync_consol_id_main))
                
                if record.company_id.sync_consol_type == 'main':

                    if record.user_id.id == False:
                        values['user_id'] = record.user_id.id
                    else:
                        values['user_id'] = str(record.user_id.id)

                # if record.company_id.id == False:
                #     values['company_id'] = record.company_id.id
                # else:
                #     values['company_id'] = str(record.company_id.id)

                # if record.company_id.id == False:
                #     values['company_id'] = record.company_id.id
                # else:
                #     values['company_id'] = str(record.company_id.id)

                values['type_pr'] = record.type_pr
                values['item_type'] = record.item_type
                values['ordering_date'] = record.ordering_date
                values['approval_date'] = record.approval_date
                # values['origin'] = str(record.origin)
                if record.origin:
                    values['origin'] = str(record.origin)
                else:
                    values['origin'] = ''
                values['trigger_write'] = False
                if record.reject_reason:
                    values['reject_reason'] = str(record.reject_reason)
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
                super(PurchaseRequest, self).write(data_update)


    @api.onchange('sync_type', 'name','user_id','type_pr','item_type','ordering_date','approval_date','origin')
    def onchange_trigger_write(self):
        self.trigger_write = True


    @api.onchange('user_id')
    def onchange_user_id(self):
        self.is_user_it = self.user_id.is_user_it

    # @api.multi
    def _compute_approve_type(self):
        for r in self:
            if r.user_id:
                approval = r.env['purchase.type'].search([('department_id', '=', r.user_id.department_id.id),('company_id', '=', r.company_id.id),('purchase_type', '=', 'pr'),('item_type', '=', r.item_type),('pr_it_type', '=', r.pr_it_type)],limit=1)
                # approval = r.env['purchase.type'].search([('department_id', '=', r.user_id.department_id.id), ('company_id', '=', r.company_id.id), ('purchase_type', '=', 'pr')], limit=1)
                r.approval_type_id = approval
            else:
                r.approval_type_id = ''



    # @api.multi
    def get_next_rule(self, approval_id=None, sequence=1):
        rule_id = None
        if approval_id:
            rule_id = self.sudo().env['purchase.approval.rule'].search([('approval_id','=',approval_id), ('enabled','=', True), ('sequence','>', sequence)], order='sequence asc', limit=1)
        return rule_id

    # @api.multi
    def get_store_rule(self, approval_id=None):
        rule_ids = None
        if approval_id:
            rule_ids = self.sudo().env['purchase.approval.rule'].search([('approval_id','=',approval_id), ('enabled','=', True)], order='sequence asc')
        return rule_ids


    # @api.multi
    def subscribe_approval(self):
        self.ensure_one()
        user_ids = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id), ('position_id.name', '=', self.approve_next_store)])
        if user_ids:
            self.sudo().message_subscribe_users(user_ids=user_ids.ids)


    def message_subscribe_users(self, user_ids=None, subtype_ids=None):
        """ Wrapper on message_subscribe, using users. If user_ids is not
            provided, subscribe uid instead. """
        if user_ids is None:
            user_ids = [self._uid]
        return self.message_subscribe(self.env['res.users'].browse(user_ids).mapped('partner_id').ids, subtype_ids=subtype_ids)

    # @api.multi
    def ask_approve(self):
        if not self.approval_type_id:
            raise exceptions.ValidationError('Please define your approval type, contact IT for more Information.')
        self.is_ask_approval = True
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "ASK APPROVE PR")
        self.function_consol(function="ask_approve_consol")

        query_update_web_base_url = """
            update ir_config_parameter set value = 'https://erp.ad.mayapadahospital.com' where key = 'web.base.url'
            """
        self.env.cr.execute(query_update_web_base_url)
        self._cr.commit()



        #Komen Dulu
        # query = """
        #     UPDATE purchase_requisition pr SET picking_type_id = (
        #         SELECT id FROM stock_picking_type 
        #         WHERE warehouse_id = ( 
        #             SELECT id 
        #             FROM stock_warehouse 
        #             WHERE company_id = pr.company_id 
        #                 AND active = True 
        #             ORDER BY id ASC 
        #             LIMIT 1) 
        #         AND code = 'incoming' 
        #         AND sync_id_api not ilike '%purchase%'
        #         AND item_type = '1' 
        #         AND active = True
        #         LIMIT 1 ) 
        #     WHERE id = {self_id}""".format(self_id = self.id)
        #     #  % (self.id)

        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "ASK APPROVE PR 1 QUERY" + str(query))

        # self.env.cr.execute(query)
        self.approve_status = 'Waiting for Approval'
  
        record = self.sudo()
        record.subscribe_approval()
        now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')



        partner_id_check_list = []
        user_id = False
        user_ids = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id),('position_id.name', '=', self.approve_next_store)], limit=1)
        if user_ids:
            #user_ids=user_ids.ids
            user_id=int(user_ids.id)
        user_ids2 = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id),('position_id.name', '=', self.approve_next)], limit=1)
        if user_ids2:
            #user_ids=user_ids2.ids
            user_id=int(user_ids2.id)
        partner_id_check = self.env['res.users'].sudo().search([('id', '=', user_id)]).partner_id.id

        if partner_id_check:

            partner_id_check_list.append(partner_id_check)
            notification_ids = [((0, 0, {'res_partner_id': partner_id_check,'notification_type': 'email'}))]    
            self.message_post(body='Please Approve This PR, ' + 'Asked by ' +self.env.user.name + " at " + now,message_type='notification',content_subtype='plaintext', subtype_id=False,notification_ids=notification_ids,partner_ids=partner_id_check_list,notify_by_email=True)
        else:
             self.message_post(body='Please Approve This PR, ' + 'Asked by ' +self.env.user.name + " at " + now,message_type='notification',content_subtype='plaintext', subtype_id=False)       

        
        

        record = self.sudo()
        if self.approve_id:
            # rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
            rule_ids = self.get_store_rule(approval_id=self.approve_id.id)
            if not self.approve_rule_id:
                self.approve_next_store = rule_ids[0].position_id.name
            else:
                # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                rule_id = self.get_next_rule(approval_id=self.approve_id.id, sequence=record.approve_rule_id.sequence)
                if rule_id:
                    if len(rule_id) > 1:
                        raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                    self.approve_next_store = rule_id.position_id.name
                else:
                    self.approve_next_store = "Completed"

        #cost_center = self.line_ids.mapped('account_analytic_id.id')
        #for cc in cost_center:
        #    cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
        #    cc_name = self.env['account.analytic.account'].browse(cc).display_name
        #    if self.company_id.cost_center_active:
        #        if not self.company_id.cost_center_date or not self.ordering_date:
        #            raise UserError(_("Tanggal tidak boleh kosong."))
        #    if self.company_id.cost_center_active == True and self.company_id.cost_center_date <= self.ordering_date:
        #        order_line = self.line_ids.search([('requisition_id', '=', self.id),('account_analytic_id', '=', cc)])
        #        amount_po = sum(r.price_subtotal for r in order_line)
        #        budget_used = self.env['crossovered.budget.lines'].sudo().search([
        #            ('analytic_account_id', '=', cc),
        #            ('crossovered_budget_id.state','in', ['validate','done']),
        #            ('date_from', '<=',self.ordering_date),
        #            ('date_to', '>=',self.ordering_date)])

                # if not budget_used:
                #     raise exceptions.ValidationError("No budget available for "+cc_name+" in period "+ str(self.ordering_date))

                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(budget_used))
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(amount_po))
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(date))
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(date))
        #        budget_used.budget_line_compute_balance()
        #        budget = sum(budget.remain_amount for budget in budget_used)
        #        budget = -budget
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(budget))
                # if cc and amount_po > budget:
                #     raise exceptions.ValidationError("Cost center " + cc_name +" exceeds the Total of Budget's Planned Amount")

        # user_ids = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id), ('position_id', 'in', self.approval_type_id.approval_ids.mapped('rule_ids').mapped('position_id').ids)])
        # self.sudo().message_subscribe_users(user_ids=user_ids.ids)


    # @api.multi
    def ask_approve_consol(self):
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "ASK APPROVE consol PR")
        #Komen Dulu
        # query = """
        #     UPDATE purchase_requisition pr SET picking_type_id = (
        #         SELECT id FROM stock_picking_type 
        #         WHERE warehouse_id = ( 
        #             SELECT id 
        #             FROM stock_warehouse 
        #             WHERE company_id = pr.company_id 
        #                 AND active = True 
        #             ORDER BY id ASC 
        #             LIMIT 1) 
        #         AND code = 'incoming'
        #         AND sync_id_api not ilike '%purchase%' 
        #         AND item_type = '1' 
        #         AND active = True
        #         LIMIT 1 ) 
        #     WHERE id = {self_id}""".format(self_id = self.id)
        #     #  % (self.id)
        # self.env.cr.execute(query)
        self.approve_status = 'Waiting for Approval'
        
        record = self.sudo()
        record.subscribe_approval()
        now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
        self.message_post(body='Please Approve This PR, ' + 'Asked by ' + self.env.user.name + " at " + now, message_type='notification', content_subtype='plaintext', subtype_id=False)
        
        

        record = self.sudo()
        if self.approve_id:
            # rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
            rule_ids = self.get_store_rule(approval_id=self.approve_id.id)
            if not self.approve_rule_id:
                self.approve_next_store = rule_ids[0].position_id.name
            else:
                # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                rule_id = self.get_next_rule(approval_id=self.approve_id.id, sequence=record.approve_rule_id.sequence)
                if rule_id:
                    if len(rule_id) > 1:
                        raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                    self.approve_next_store = rule_id.position_id.name
                else:
                    self.approve_next_store = "Completed"
        #user_ids = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id), ('position_id', 'in', self.approval_type_id.approval_ids.mapped('rule_ids').mapped('position_id').ids)])
        #self.sudo().message_subscribe_users(user_ids=user_ids.ids)
        
        #cost_center = self.line_ids.mapped('account_analytic_id.id')
        #for cc in cost_center:
        #    cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
        #    cc_name = self.env['account.analytic.account'].browse(cc).display_name
        #    if self.company_id.cost_center_active:
        #        if not self.company_id.cost_center_date or not self.ordering_date:
        #            raise UserError(_("Tanggal tidak boleh kosong."))
        #    if self.company_id.cost_center_active == True and self.company_id.cost_center_date <= self.ordering_date:
        #        order_line = self.line_ids.search([('requisition_id', '=', self.id),('account_analytic_id', '=', cc)])
        #        amount_po = sum(r.price_subtotal for r in order_line)
        #        budget_used = self.env['crossovered.budget.lines'].sudo().search([
        #            ('analytic_account_id', '=', cc),
        #            ('crossovered_budget_id.state','in', ['validate','done']),
        #            ('date_from', '<=',self.ordering_date),
        #            ('date_to', '>=',self.ordering_date)])

                # if not budget_used:
                #     raise exceptions.ValidationError("No budget available for "+cc_name+" in period "+ str(self.ordering_date))

                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(budget_used))
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(amount_po))
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(date))
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(date))
        #        budget_used.budget_line_compute_balance()
        #        budget = sum(budget.remain_amount for budget in budget_used)
        #        budget = -budget
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(budget))
                # if cc and amount_po > budget:
                #     raise exceptions.ValidationError("Cost center " + cc_name +" exceeds the Total of Budget's Planned Amount")


    # @api.one
    def _status(self):
        # if self.approve_next and self.state not in ['cancel', 'in_progress', 'done']:
        #     if not self.approve_status:
        #         self.status = 'draft'
        #     if not self.approve_next == 'Completed':
        #         self.status = 'waiting'
        #     if self.approve_next == 'Completed':
        #         self.status = self.state
        #     # else:
        #     #    self.status = 'in_progress'
        # else:
        #     self.status = self.state
        #     if self.state == 'cancel':
        #         self.write({'approve_rule_id': False})

        if self.approve_next and self.state not in ['cancel', 'in_progress', 'done']:
            if self.is_ask_approval == False:
                self.status = 'draft'
            if self.is_ask_approval == True:
                self.status = 'waiting'
            if self.approve_next == 'Completed':
                self.status = self.state
            # else:
            #    self.status = 'in_progress'
        else:
            self.status = self.state
            if self.state == 'cancel':
                self.write({'approve_rule_id': False})


    # @api.one
    def _approval(self):
        record = self[0].sudo()
        # planned = self.amount_total#sum(line.planned_amount for line in record.crossovered_budget_line)
        approval = self.env['purchase.approval'].sudo()
        self.approve_id = approval.search([('id', 'in', record.approval_type_id.approval_ids.ids)], limit=1)  #, ('max_amount', '>=', planned), ('min_amount', '<=', planned)], limit=1)
        if self.approve_id:
            # rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
            rule_ids = self.get_store_rule(approval_id=self.approve_id.id)

            if not self.approve_rule_id:
                self.approve_next = rule_ids[0].position_id.name
                # self.approve_next_store = rule_ids[0].position_id.name
            else:
                # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                rule_id = self.get_next_rule(approval_id=self.approve_id.id, sequence=record.approve_rule_id.sequence)
                if rule_id:
                    if len(rule_id) > 1:
                        raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                    self.approve_next = rule_id.position_id.name
                    # 2021.04.12 >> tambahan firgi auto-update next_store
                    # self.approve_next_store = rule_id.position_id.name
                else:
                    self.approve_next = "Completed"
                    # 2021.04.12 >> tambahan firgi auto-update next_store
                    # self.approve_next_store = "Completed"

        else:
            self.approve_next =''


    # @api.multi
    def action_in_progress(self):
        # self.function_consol(function="action_in_progress_consol")
        if self.approve_next != 'Completed' or not self.env.context.get('approved'):
            raise exceptions.ValidationError("Waiting for Approval")
        now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
        self.approval_date = now
        return super(PurchaseRequest, self).action_in_progress()


    # @api.multi
    def action_in_progress_consol(self):
        if self.approve_next != 'Completed' or not self.env.context.get('approved'):
            raise exceptions.ValidationError("Waiting for Approval")
        now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
        self.approval_date = now
        return super(PurchaseRequest, self).action_in_progress()


    # @api.multi
    def action_cancel(self):
        self.function_consol(function="action_cancel_consol")
        
        if self.lock_pr:
            raise UserError(_('A locked PR cannot be cancelled.'))

        # try to set all associated quotations to cancel state
        for requisition in self:

            active_po = requisition.purchase_ids.filtered(lambda po: po.state != 'cancel')
            if active_po:
                po_list = ", ".join(active_po.mapped("name"))
                raise UserError(_(
                    "Tidak bisa membatalkan Purchase Agreement karena masih ada Purchase Order "
                    "yang belum dibatalkan:\n%s" % po_list
                ))



            if requisition.purchase_ids:
                requisition.purchase_ids.button_cancel()
                for po in requisition.purchase_ids:
                    po.message_post(body=_('Cancelled by the agreement associated to this quotation.'))
        self.write({'state': 'cancel'})

        now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
        partner_id_check_list = []
        user_id = self.user_id.id
        partner_id_check = self.env['res.users'].sudo().search([('id', '=', user_id)]).partner_id.id

        if partner_id_check:

            partner_id_check_list.append(partner_id_check)
            notification_ids = [((0, 0, {'res_partner_id': partner_id_check,'notification_type': 'email'}))]    
            self.message_post(body='This PR is Cancelled by ' +self.env.user.name + " at " + now,message_type='notification',content_subtype='plaintext', subtype_id=False,notification_ids=notification_ids,partner_ids=partner_id_check_list,notify_by_email=True)
        else:
             self.message_post(body='This PR is Cancelled by ' +self.env.user.name + " at " + now,message_type='notification',content_subtype='plaintext', subtype_id=False)

        #cost_center = self.line_ids.mapped('account_analytic_id.id')
        #for cc in cost_center:
        #    cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
        #    if self.company_id.cost_center_active:
        #        if not self.company_id.cost_center_date or not self.ordering_date:
        #            raise UserError(_("Tanggal tidak boleh kosong."))
        #    if self.company_id.cost_center_active == True and self.company_id.cost_center_date <= self.ordering_date:
        #        budget_used = self.env['crossovered.budget.lines'].sudo().search([
        #            ('analytic_account_id', '=', cc),
        #            ('crossovered_budget_id.state','in', ['validate','done']),
        #            ('date_from', '<=',self.ordering_date),
        #            ('date_to', '>=',self.ordering_date)])
        #        if budget_used:
        #            budget_used.budget_line_compute_balance()


    # @api.multi
    def action_cancel_consol(self):
        # try to set all associated quotations to cancel state
        for requisition in self:
            if requisition.purchase_ids:
                requisition.purchase_ids.button_cancel()
                for po in requisition.purchase_ids:
                    po.message_post(body=_('Cancelled by the agreement associated to this quotation.'))
        
        self.write({'state': 'cancel'})
        #cost_center = self.line_ids.mapped('account_analytic_id.id')
        #for cc in cost_center:
        #    cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
        #    if self.company_id.cost_center_active:
        #        if not self.company_id.cost_center_date or not self.ordering_date:
        #            raise UserError(_("Tanggal tidak boleh kosong."))
        #    if self.company_id.cost_center_active == True and self.company_id.cost_center_date <= self.ordering_date:
        #        budget_used = self.env['crossovered.budget.lines'].sudo().search([
        #            ('analytic_account_id', '=', cc),
        #            ('crossovered_budget_id.state','in', ['validate','done']),
        #            ('date_from', '<=',self.ordering_date),
        #            ('date_to', '>=',self.ordering_date)])
        #        if budget_used:
        #            budget_used.budget_line_compute_balance()


    # @api.multi
    def action_done(self):
        self.function_consol(function="action_done_consol")
        """
        Generate all purchase order based on selected lines, should only be called on one agreement at a time
        """
        if any(purchase_order.state in ['draft', 'sent', 'to approve'] for purchase_order in self.mapped('purchase_ids')):
            raise UserError(_('You have to cancel or validate every RfQ before closing the purchase requisition.'))
        self.write({'state': 'done'})


    # @api.multi
    def action_done_consol(self):
        """
        Generate all purchase order based on selected lines, should only be called on one agreement at a time
        """
        if any(purchase_order.state in ['draft', 'sent', 'to approve'] for purchase_order in self.mapped('purchase_ids')):
            raise UserError(_('You have to cancel or validate every RfQ before closing the purchase requisition.'))
        self.write({'state': 'done'})


    # @api.multi
    def action_draft(self):
        self.function_consol(function="action_draft_consol")
        self.revisi_sequence += 1
        self.state = 'draft'
        self.is_ask_approval = False
        self.update({'revisi_name': 'R' + str(self.revisi_sequence)})


    # @api.multi
    def action_draft_consol(self):
        self.revisi_sequence += 1
        self.state = 'draft'
        self.update({'revisi_name': 'R' + str(self.revisi_sequence)})


    # @api.multi
    def print_pr(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/purchase/purchase_requisition?id=' + str(self.id)
        action['target'] = 'new'
        return action

    # @api.multi
    def button_reject(self):
        return {
            'name': _('Change Destination Location'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': False,
            'res_model': 'purchase.requisition.reject.wizard',
            'target': 'new',
            'context': {'default_user_id': self.user_id.id,
                        'default_requisition_id': self.id,
                        'default_proc_user_id': self.env.user.id,
                        },
            }

    
    # @api.multi
    def approve(self):
        self.function_consol(function="approve_consol")

        query_update_web_base_url = """
            update ir_config_parameter set value = 'https://erp.ad.mayapadahospital.com' where key = 'web.base.url'
            """
        self.env.cr.execute(query_update_web_base_url)
        self._cr.commit()


        record = self.sudo()

        if not record.approve_id:
            raise exceptions.ValidationError("There are no rule defined for this Budget")
        # rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
        rule_ids = self.get_store_rule(approval_id=record.approve_id.id)
                
        if not rule_ids:
            raise exceptions.ValidationError("There are no rule defined for this Budget")

        if not self.approve_rule_id:
            position_id = self.env.user.position_id.id
            # if self.env.user.position_id.name == 'MHG - CHIEF OPERATING OFFICER':
            #     if self.env.user.position_id.id != rule_ids[0].position_id.get_parent_ids():
            #         position_id = self.env['res.position'].search([('name','=','MHG - GROUP FINANCE DIRECTOR')]).id #CFO
                        
            if position_id in rule_ids[0].position_id.get_parent_ids() or self.env.user.second_position_id.id in rule_ids[0].position_id.get_parent_ids():
                self.approve_rule_id = rule_ids[0]
                #self.approve_history("Approved by " + self.approve_status)
                record = self.sudo()
                now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
                # self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now, message_type='notification', content_subtype='plaintext', subtype_xmlid='mail.mt_comment')
                # if not rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1):
                
                rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                if not rule_id:
                    self.state = 'in_progress'
                    self.status = 'in_progress'
                    if len(rule_ids) == 1:
                        self.approve_next = 'Completed'

                    self.with_context(approved=True).action_in_progress()
                    
            
            else:
                raise exceptions.ValidationError("You doesn't have authority to approve this Transaction")
        else:
            # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
            rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                
            if rule_id:
                # raise exceptions.ValidationError(str(rule_id.position_id.get_parent_ids))
                position_id = self.env.user.position_id.id
                # if self.env.user.position_id.name == 'MHG - CHIEF OPERATING OFFICER':
                #     if self.env.user.position_id.id != rule_id.position_id.get_parent_ids()[0]:
                #         # raise exceptions.ValidationError(str(rule_id.position_id.get_parent_ids()[0]))
                #         position_id = self.env['res.position'].search([('name','=','MHG - GROUP FINANCE DIRECTOR')]).id #CFO
                
                    
                if position_id in rule_id.position_id.get_parent_ids() or self.env.user.second_position_id.id in rule_id.position_id.get_parent_ids():
                    self.approve_rule_id = rule_id
                    #self.approve_history("Approved by " + self.approve_status)
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    # self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now, message_type='notification', content_subtype='plaintext', subtype_xmlid='mail.mt_comment')
                    # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1):
                    rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                    if not rule_id:
                        self.state = 'in_progress'
                        self.status = 'in_progress'
                        self.approve_next = 'Completed' #Penambahan 20230626
                        self.with_context(approved=True).action_in_progress()
                        
                else:
                    raise exceptions.ValidationError("You doesn't have authority to approve this Transaction")
            else:
                raise exceptions.ValidationError("There are no Approval anymore for this Budget")

        if self.approve_id:
            # rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
            rule_ids = self.get_store_rule(approval_id=record.approve_id.id)
                

            if not self.approve_rule_id:
                self.approve_next_store = rule_ids[0].position_id.name
            else:
                # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                
                if rule_id:
                    if len(rule_id) > 1:
                        raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                    self.approve_next_store = rule_id.position_id.name
                else:
                    
                    self.approve_next_store = "Completed"

        record.subscribe_approval()
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "self state terakhir : " + str(self.state))
        #cost_center = self.line_ids.mapped('account_analytic_id.id')
        #for cc in cost_center:
        #    cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
        #    cc_name = self.env['account.analytic.account'].browse(cc).display_name
        #    if self.company_id.cost_center_active:
        #        if not self.company_id.cost_center_date or not self.ordering_date:
        #            raise UserError(_("Tanggal tidak boleh kosong."))
        #    if self.company_id.cost_center_active == True and self.company_id.cost_center_date <= self.ordering_date:
        #        order_line = self.line_ids.search([('requisition_id', '=', self.id),('account_analytic_id', '=', cc)])
        #        amount_po = sum(r.price_subtotal for r in order_line)
        #        budget_used = self.env['crossovered.budget.lines'].sudo().search([
        #            ('analytic_account_id', '=', cc),
        #            ('crossovered_budget_id.state','in', ['validate','done']),
        #            ('date_from', '<=',self.ordering_date),
        #            ('date_to', '>=',self.ordering_date)])

                # if not budget_used:
                #     raise exceptions.ValidationError("No budget available for "+cc_name+" in period "+ str(self.ordering_date))

                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(budget_used))
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(amount_po))
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(date))
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(date))
        #        budget_used.budget_line_compute_balance()
        #        budget = sum(budget.remain_amount for budget in budget_used)
        #        budget = -budget
                # open('/opt/odoo16/logs/test.log', 'a+').write('\n' + str(budget))
                # if cc and amount_po > budget:
                #     raise exceptions.ValidationError("Cost center " + cc_name +" exceeds the Total of Budget's Planned Amount")


        partner_id_check_list = []
        user_id = False
        user_ids = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id),('position_id.name', '=', self.approve_next_store)], limit=1)
        if user_ids:
            #user_ids=user_ids.ids
            user_id=int(user_ids.id)
        #user_ids2 = self.env['res.users'].sudo().search([('company_ids', '=', self.company_id.id),('position_id.name', '=', self.approve_next)], limit=1)
        #if user_ids2:
        #    #user_ids=user_ids2.ids
        #    user_id=int(user_ids2.id)
        partner_id_check = self.env['res.users'].sudo().search([('id', '=', user_id)]).partner_id.id
        if partner_id_check:
            partner_id_check_list.append(partner_id_check)

            notification_ids = [((0, 0, {'res_partner_id': partner_id_check,'notification_type': 'email'}))]    
            self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now ,message_type='notification',content_subtype='plaintext', subtype_id=False,notification_ids=notification_ids,partner_ids=partner_id_check_list,notify_by_email=True)
        else:
            if self.user_id.id:
                search_partner_id = self.user_id.id
            else:
                search_partner_id = self.env.user.id
            partner_id_check2 = self.env['res.users'].sudo().search([('id', '=', search_partner_id)]).partner_id.id
            # partner_id_check2 = self.env['res.users'].sudo().search([('id', '=', (self.user_id.id or self.user_po_id.id))]).partner_id.id
            
            partner_id_check_list.append(partner_id_check2)
            notification_ids = [((0, 0, {'res_partner_id': partner_id_check2,'notification_type': 'email'}))] 
            
            self.message_post(body='Approved Complited by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now ,message_type='notification',content_subtype='plaintext', subtype_id=False,notification_ids=notification_ids,partner_ids=partner_id_check_list,notify_by_email=True)
            # self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now ,message_type='notification',content_subtype='plaintext', subtype_id=False)    


    # @api.multi
    def approve_consol(self):
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "APPROVE consol PR")
        record = self.sudo()
        if not record.approve_id:
            raise exceptions.ValidationError("There are no rule defined for this Budget")
        # rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
        rule_ids = self.get_store_rule(approval_id=record.approve_id.id)
                
        if not rule_ids:
            raise exceptions.ValidationError("There are no rule defined for this Budget")
        
        if not self.approve_rule_id:
            position_id = self.env.user.position_id.id
            # if self.env.user.position_id.name == 'MHG - CHIEF OPERATING OFFICER':
            #     if self.env.user.position_id.id != rule_ids[0].position_id.get_parent_ids():
            #         position_id = self.env['res.position'].search([('name','=','MHG - GROUP FINANCE DIRECTOR')]).id #CFO
                        
            if position_id in rule_ids[0].position_id.get_parent_ids() or self.env.user.second_position_id.id in rule_ids[0].position_id.get_parent_ids():
                self.approve_rule_id = rule_ids[0]
                #self.approve_history("Approved by " + self.approve_status)
                record = self.sudo()
                now = (datetime.now() +timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
                # self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now, message_type='notification', content_subtype='plaintext', subtype_xmlid='mail.mt_comment')
                # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1):
                rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                if not rule_id:
                    self.state = 'in_progress'
                    self.status = 'in_progress'
                    if len(rule_ids) == 1:
                        self.approve_next = 'Completed'

                    self.with_context(approved=True).action_in_progress()
            else:
                raise exceptions.ValidationError("You doesn't have authority to approve this Transaction")
        else:
            # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
            rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                
            if rule_id:
                # raise exceptions.ValidationError(str(rule_id.position_id.get_parent_ids))
                position_id = self.env.user.position_id.id
                # if self.env.user.position_id.name == 'MHG - CHIEF OPERATING OFFICER':
                #     if self.env.user.position_id.id != rule_id.position_id.get_parent_ids()[0]:
                #         # raise exceptions.ValidationError(str(rule_id.position_id.get_parent_ids()[0]))
                #         position_id = self.env['res.position'].search([('name','=','MHG - GROUP FINANCE DIRECTOR')]).id #CFO
                
                    
                if position_id in rule_id.position_id.get_parent_ids() or self.env.user.second_position_id.id in rule_id.position_id.get_parent_ids():
                    self.approve_rule_id = rule_id
                    #self.approve_history("Approved by " + self.approve_status)
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    # self.message_post(body='Approved by ' + self.approve_status + ' by ' + self.env.user.name + " at " + now, message_type='notification', content_subtype='plaintext', subtype_xmlid='mail.mt_comment')
                    # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1):
                    rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                
                    if not rule_id:
                        self.state = 'in_progress'
                        self.status = 'in_progress'
                        self.with_context(approved=True).action_in_progress()
                else:
                    raise exceptions.ValidationError("You doesn't have authority to approve this Transaction")
            else:
                raise exceptions.ValidationError("There are no Approval anymore for this Budget")
        
        if self.approve_id:
            # rule_ids = record.approve_id.rule_ids.sorted(key=lambda data: data.sequence)
            rule_ids = self.get_store_rule(approval_id=record.approve_id.id)
                
            if not self.approve_rule_id:
                self.approve_next_store = rule_ids[0].position_id.name
            else:
                # rule_id = rule_ids.filtered(lambda data: data.sequence == record.approve_rule_id.sequence + 1)
                rule_id = self.get_next_rule(approval_id=record.approve_id.id, sequence=record.approve_rule_id.sequence)
                
                if rule_id:
                    if len(rule_id) > 1:
                        raise exceptions.ValidationError("The sequence in Approval Rule Positions is double!")
                    self.approve_next_store = rule_id.position_id.name
                else:
                    self.approve_next_store = "Completed"
        record.subscribe_approval()
        self.message_post(body='Approved by ' + self.approve_status + ' by ' +self.env.user.name + " at " + now,message_type='notification',content_subtype='plaintext', subtype_id=False)


    
    # @api.model
    # def get_view(self,view_id=None, view_type='form', **options):
    #     res = super(PurchaseRequest,self).get_view(view_id=view_id,view_type=view_type, **options)  
    #     if view_type == 'tree':
    #         res['arch'] = """
    #             <tree default_order="approval_date desc" decoration-bf="message_needaction==True" decoration-muted="state == 'cancel'" decoration-info="state == 'draft'" decoration-success="state in ['done','open','in_progress']" decoration-danger="date_end and date_end&lt;current_date" string="Purchase Agreements" delete="0">
    #                 <field name="message_needaction" invisible="1" modifiers="{'readonly': true, 'tree_invisible': true}"/>
    #                 <field name="name" on_change="1"/>
    #                 <field name="user_id" on_change="1" can_create="true" can_write="true"/>
    #                 <field name="origin" on_change="1"/>
    #                 <field name="ordering_date" on_change="1"/>
    #                 <field name="date_end"/>
    #                 <field name="approval_date" on_change="1" modifiers="{'readonly': true}"/>
    #                 <field name="write_date" string="Last Update"/>
    #                 <field name="approve_status" modifiers="{'readonly': true}"/>
    #                 <field name="approve_next_store"/>
    #                 <field name="state" modifiers="{'required': true}"/>
    #                 <field name="company_id" options="{'no_create': True}" on_change="1" can_create="true" can_write="true" modifiers="{'required': true}"/>
    #             </tree>  
    #         """
    #     elif view_type == 'search':
    #         res['arch'] = """
    #             <search string="Search Purchase Request">
    #                 <field name="name" string="PR Number" filter_domain="['|', ('name','ilike',self), ('origin','ilike',self)]"/>
    #                 <field name="type_id"/>
    #                 <filter name="draft" string="Draft" domain="[('state','=','draft')]" help="New Agreements"/>
    #                 <filter string="Confirmed" domain="[('state','in',('in_progress','open'))]" help="In negotiation"/>
    #                 <filter string="Done" domain="[('state','=','done')]"/>
    #                 <separator/>
    #                 <filter string="Unassigned" domain="[('user_id','=', False)]" help="Unassigned  Requisition"/>
    #                 <field name="user_id"/>
    #                 <group expand="0" string="Group By">
    #                     <filter string="Responsible" domain="[]" context="{'group_by':'user_id'}"/>
    #                     <filter string="Source" domain="[]" context="{'group_by':'origin'}"/>
    #                     <filter string="Status" domain="[]" context="{'group_by':'state'}"/>
    #                     <filter string="Ordering Date" domain="[]" context="{'group_by':'ordering_date'}"/>
    #                     <filter string="End Month" domain="[]" context="{'group_by':'date_end'}"/>
    #                 </group>
    #             </search>
    #         """
    #     from lxml import etree
    #     doc = etree.XML(res['arch'])
    #     View = self.env['ir.ui.view'].sudo()
    #     res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
    #     return res






class PurchaseRequestLine(models.Model):
    _inherit = 'purchase.requisition.line'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")

    company_id = fields.Many2one('res.company', related='requisition_id.company_id', string='Company', store=True, readonly=True, default= lambda self: self.env['res.company']._company_default_get('purchase.requisition.line'))
    requisition_id = fields.Many2one('purchase.requisition', string='Purchase Agreement', ondelete='cascade')
    description = fields.Char(string="Notes")
    price_subtotal = fields.Float(string='Price Subtotal', readonly=True, compute='subtotal', store=True)
    product_name = fields.Char(related='product_id.name', store=False)
    request_date = fields.Date(string="Date", related='requisition_id.ordering_date', store=True)
    user_id = fields.Many2one('res.users', string="Responsible", related='requisition_id.user_id', store=False)
    
    analytic_ids = fields.Many2many('account.analytic.account', string="Analytic Users")
    account_analytic_id = fields.Many2one('account.analytic.account', string="Analytic Account", store=True, index=True)    
    # cost_center_active = fields.Boolean(string="Cost Center Active", readonly=True, related='company_id.cost_center_active', store=False)
    cost_center_active = fields.Boolean(string="Cost Center Active", readonly=True, store=True)

    state = fields.Selection([('draft', 'Draft'), ('in_progress', 'Confirmed'),('open', 'RFQ Created'),('done', 'PO Completed'),('cancel', 'Cancelled')], 'Status', related='requisition_id.state', store=True, required=False)
    historical_price = fields.Float(string='Historical Price', readonly=True)
    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")

    product_char = fields.Char(string="Product Char")


    @api.onchange('cost_center_active','product_id','requisition_id','user_id','description')
    # @api.depends('cost_center_active','product_id','requisition_id','user_id','account_analytic_id')
    def _change_analytic(self):
        res = {}
        analytic_ids = (self.env.context.get('analytic_ids', [[0,0,[]]]))[0][2]
        res['domain'] = {'account_analytic_id': [('parent_id', '!=', False),('type_analytic', '=','expense'),('id','in', analytic_ids if analytic_ids else self.user_id.analytic_ids.ids)] }
        # open('/opt/odoo16/logs/log_domain.log', 'a+').write(str(res))
        return res

    # @api.multi
    def unlink(self):
        for rec in self:
            if rec.sync_consol_id_unit or rec.sync_consol_id_main:
                rec.send_api_consol_unlink_company()
            check_model_exist = self.env['ir.model'].search([('model', '=', 'tampung.purchase.requisition.line')])
            if check_model_exist:
                now = (datetime.now() + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
                query_insert = """insert into tampung_purchase_requisition_line (pr_id,pr_line_id,sync_type,date_delete) values ('%s','%s','%s','%s') """ % (rec.requisition_id.id, rec.id, rec.requisition_id.company_id.sync_type, now)
                self.env.cr.execute(query_insert)
        result = super(PurchaseRequestLine, self).unlink()

    # @api.multi
    def send_api_consol_unlink_company(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_purchase_requisition
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api_unlink/unit/purchase.requisition.line"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api_unlink/main/purchase.requisition.line"
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
                body['csrf_token'] = self.env.user.token_consol
                # body['ids'] = self.env.user[consol_id_from]
                if consol_type == 'unit':
                    body['ids'] = int(record.sync_consol_id_main)
                    company_name = record.company_id.name
                    sync_consol_id_main = str(self.env.user.login)
                    body['company_name'] = company_name
                    
                    body['user_id'] = sync_consol_id_main
                if consol_type == 'main':
                    body['ids'] = int(record.sync_consol_id_unit)
                    company_name = record.company_id.name
                    sync_consol_id_main = str(self.env.user.login)
                    body['company_name'] = company_name
                
                    body['user_id'] = sync_consol_id_main
                cookies = {'session_id': self.env.user.cookies}
                print(body)
                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                json_resp = response_json.json()
                # self.env.user.sync_consol_response = json_resp

    
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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'purchase.requisition.line' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'purchase.requisition.line'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        result = super(PurchaseRequestLine, self).create(vals)

        if result.company_id.sync_type:
            result.sync_type = result.company_id.sync_type

        #if vals.get('company_id'):
        #    company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
        #    result.sync_type = company_id.sync_type

        if result.company_id.cost_center_active:
            if not result.company_id.cost_center_date or not result.request_date:
                raise UserError(_("Tanggal tidak boleh kosong."))
        if result.company_id.cost_center_active and result.requisition_id.item_type =='1' and not result.account_analytic_id and result.company_id.cost_center_date <= result.request_date:
            raise exceptions.ValidationError("Item {code} harus dimapping dengan Cost Center Analytic".format(code=result.product_id.name + " " + str(result.description) or ""))

        if result.trigger_create == False:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger create purchase requisition line")
            result.send_api_consol_company()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " +str(result.id)

        open(log_file, 'a').write(message_log)
        return result


    # @api.multi
    def send_api_consol_company(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_purchase_requisition
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/purchase.requisition.line"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/purchase.requisition.line"
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
                values['description'] = record.description
                values['product_qty'] = record.product_qty
                values['schedule_date'] = record.schedule_date
                values['price_unit'] = record.price_unit
                
                values['trigger_create'] = True

                if record.product_id.id == False:
                    values['product_id'] = record.product_id.product_tmpl_id.id
                else:
                    values['product_id'] = str(record.product_id.product_tmpl_id.id)

                if record.product_uom_id.id == False:
                    values['product_uom_id'] = record.product_uom_id.id
                else:
                    values['product_uom_id'] = str(record.product_uom_id.id)
                # if record.account_analytic_id.id == False:
                #     values['account_analytic_id'] = record.account_analytic_id.id
                # else:
                #     values['account_analytic_id'] = str(record.account_analytic_id.id)
                if record.requisition_id.id == False:
                    values['requisition_id'] = record.requisition_id.id
                else:
                    values['requisition_id'] = str(record.requisition_id.id)

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
                super(PurchaseRequestLine, self).write(data_update)


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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'purchase.requisition.line' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'purchase.requisition.line'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        result = super(PurchaseRequestLine, self).write(vals)
        if self.env.context.get('writed'):
            return result
        if self.company_id.cost_center_active:
            if not self.company_id.cost_center_date or not self.request_date:
                raise UserError(_("Tanggal tidak boleh kosong."))
        if self.company_id.cost_center_active and self.requisition_id.item_type =='1' and not self.account_analytic_id and self.company_id.cost_center_date <= self.request_date:
            raise exceptions.ValidationError("Item {code} harus dimapping dengan Cost Center Analytic".format(code=self.product_id.name + " " + str(self.description) or ""))
        
        self = self.with_context(writed=True)

        # if self.company_id:
        #     self.sync_type = self.company_id.sync_type
        if self.trigger_write == True:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger write purchase request line")
            query = """
            UPDATE purchase_requisition_line set trigger_write = false
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
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_purchase_requisition
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/purchase.requisition.line"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/purchase.requisition.line"
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
                values['description'] = record.description
                values['product_qty'] = record.product_qty
                values['schedule_date'] = record.schedule_date
                values['price_unit'] = record.price_unit
                values['trigger_write'] = False
                

                if record.product_id.id == False:
                    values['product_id'] = record.product_id.product_tmpl_id.id
                else:
                    values['product_id'] = str(record.product_id.product_tmpl_id.id)

                if record.product_uom_id.id == False:
                    values['product_uom_id'] = record.product_uom_id.id
                else:
                    values['product_uom_id'] = str(record.product_uom_id.id)
                # if record.account_analytic_id.id == False:
                #     values['account_analytic_id'] = record.account_analytic_id.id
                # else:
                #     values['account_analytic_id'] = str(record.account_analytic_id.id)
                if record.requisition_id.id == False:
                    values['requisition_id'] = record.requisition_id.id
                else:
                    values['requisition_id'] = str(record.requisition_id.id)
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
                super(PurchaseRequestLine, self).write(data_update)


    @api.onchange('sync_type', 'description','product_qty','schedule_date','price_unit','product_id','product_uom_id','account_analytic_id','requisition_id')
    def onchange_trigger_write(self):
        self.trigger_write = True

    @api.onchange('product_id')
    def onchange_product_char(self):
        self.product_char = self.product_id.name


    @api.onchange('product_id')  # if these fields are changed, call method
    def _hpvalue(self):
        if self.product_id.id:
            historical_price = self.env['purchase.requisition.line'].search([('product_id', '=', self.product_id.id)],order='price_unit asc',limit=1)
            # raise exceptions.ValidationError(historical_price)
            if historical_price.price_unit:
                self.historical_price = historical_price.price_unit
            else:
                self.historical_price = 0


    @api.depends('price_unit', 'product_qty')
    def subtotal(self):
        for r in self:
            if r.product_id:
                r.price_subtotal = (r.price_unit * r.product_qty)



class AskForApprovalBatchWizard(models.TransientModel):
    _name = 'ask.for.approval.batch.wizard'
    po_ids = fields.Many2many('purchase.order', domain=[('status', '=', 'draft')],string="RFQ")



    # @api.multi
    def confirm_all(self):
        for rec in self:
            for po in rec.po_ids:
                po.ask_approve()






class ApprovalBatchWizard(models.TransientModel):
    _name = 'approval.batch.wizard'
    po_ids = fields.Many2many('purchase.order',domain=[('status', '=', 'waiting')],string="To Approve")



    # @api.multi
    def confirm_all(self):
        for rec in self:
            for po in rec.po_ids:
                po.approve()



class PurchaseBulkConfirmWizard(models.TransientModel):
    _name = 'purchase.bulk.confirm.wizard'
    po_ids = fields.Many2many('purchase.order',string="RFQ")



    # @api.multi
    def confirm_all(self):
        for record in self:
            for purchase_id in self.po_ids:
                record.env['purchase.order'].browse(purchase_id.id).button_confirm()



# Model: ReportPurchaseRequisitionWizard
# Module: Purchase/Report/Purchase Requisition
class ReportPurchaseRequisitionWizard(models.TransientModel):
    _name = 'report.purchase.requisition.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    start_date = fields.Date(string="PR Date Start", required=True)
    end_date = fields.Date(string="PR Date End", required=True)
    vendor_id = fields.Many2one('res.partner', string='PR Vendor', index=True)
    state = fields.Selection([('draft', 'Draft'), ('waiting', 'Waiting for Approval'), ('approved', 'Approved'), ('in_progress', 'Confirmed'), ('open', 'RFQ Created'), ('done', 'PO Completed'), ('cancel', 'Cancel')], string='PR Status', index=True, copy=False, default='draft')    
    format_print_id = fields.Selection([('pdf', 'PDF'), ('xls', 'EXCEL')], string="Format", required=True, default='xls')
    description = fields.Html(string='Descriptions', readonly=True, default='Report ini digunakan untuk export data status Purchase requsition per line item/product yang sudah di realisasikan menjadi PO atau belum, berdasarkan Periode Transaksi PR, Status PR & spesifik Supplier (Jika ada)')


    # @api.multi
    def generate_report_purchase_requisition(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/purchase/report_purchase_requisition?id=' + str(self.id)
        action['target'] = 'new'
        return action



class PurchaseRequisitionRejectWizard(models.TransientModel):
    _name = 'purchase.requisition.reject.wizard'


    user_id = fields.Many2one('res.users',string="Responsible",readonly=True)
    requisition_id = fields.Many2one('purchase.requisition',string="PR No.",readonly=True)
    proc_user_id = fields.Many2one('res.users',string="Procurement PIC",readonly=True)
    reject_state = fields.Selection([('draft', 'Draft'), ('in_progress', 'Confirmed'),('open', 'RFQ Created'), ('done', 'PO Completed'), ('cancel', 'Cancelled')], 'Status', tracking=True, copy=False, default='draft', required=True)
    reject_reason = fields.Char(string="Reject Reason", required=True)

    # @api.multi
    def reject(self):
        if self.reject_state == 'draft':
            self.requisition_id.action_reject()
            self.requisition_id.reject_reason = self.reject_reason
            # self.requisition_id.action_cancel()
            # self.requisition_id.state = self.reject_state
            
            # self.requisition_id.approve_rule_id = False
            # self.requisition_id.approve_status = False
            # self.requisition_id.approve_next_store = False
            self.requisition_id.send_api_consol_write_company()


class ReportPurchaseResponseTimeWizard(models.TransientModel):
    _name = 'report.purchase.response.time.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    start_date = fields.Date(string="Date Start", required=True)
    end_date = fields.Date(string="Date End", required=True)
    type_print = fields.Selection([('pr', 'Purchase Requisition'), ('po', 'Purchase Order')], string="Based On", required=True, default='pr')
    pr_state = fields.Selection([('draft', 'Draft'), ('waiting', 'Waiting for Approval'), ('approved', 'Approved'), ('in_progress', 'Confirmed'), ('open', 'RFQ Created'), ('done', 'PO Completed'), ('cancel', 'Cancel')], string='PR Status', index=True, copy=False, default='draft')    
    po_state = fields.Selection([('draft', 'RFQ'), ('sent', 'RFQ Sent'),('to approve', 'To Approve'),('purchase', 'Purchase Order'),('done', 'Close Bill'), ('cancel', 'Cancelled')],string='PO Status',index=True,copy=False,default='draft')
    
    res_company_ids = fields.Many2many('res.company', relation='res_company_purchase_response_time_update', string="Company")
    res_partner_ids = fields.Many2many('res.partner', relation='res_partner_purchase_response_time_update', string="Supplier")
    product_product_ids = fields.Many2many('product.product', relation='product_product_purchase_response_time_update', string="Product")
    
    company_ids = fields.One2many('company.search', 'response_id', string="Company")
    supplier_ids = fields.One2many('supplier.search', 'response_id', string="Supplier")
    product_ids = fields.One2many('product.search', 'response_id', string="Product")
    description_ids = fields.One2many('description.search', 'response_id', string="Description")

    # @api.multi
    def print_all(self):
        if self.type_print == 'pr':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/purchase/pr_response_time?id=' + str(self.id)
            action['target'] = 'new'
            return action
        if self.type_print == 'po':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/purchase/po_response_time?id=' + str(self.id)
            action['target'] = 'new'
            return action




class SupplierSearch(models.TransientModel):
    _name = 'supplier.search'

    name = fields.Char(string="Name")
    response_id = fields.Many2one('report.purchase.response.time.wizard', string="Response ID")

class ProductSearch(models.TransientModel):
    _name = 'product.search'

    name = fields.Char(string="Name")
    response_id = fields.Many2one('report.purchase.response.time.wizard', string="Response ID")

class DescriptionSearch(models.TransientModel):
    _name = 'description.search'

    name = fields.Char(string="Name")
    response_id = fields.Many2one('report.purchase.response.time.wizard', string="Response ID")

class CompanySearch(models.TransientModel):
    _name = 'company.search'

    name = fields.Char(string="Name")
    response_id = fields.Many2one('report.purchase.response.time.wizard', string="Response ID")






"""
Model: ReportPurchaseAnalyzeWizard
Module: Purchase/Report/PurchaseAnalyze
Function: 
- Menampilkan summary total Qty & Nett GRN Amount per vendor dan UoM dalam periode tertentu 
- Berguna untuk monitoring realisasi pembelian obat/alkes/consumables by vendor setiap bulan
- Mengukur compliance rate dari pembelian yang dilakukan melalui vendor utama (preferred) dan yang non-utama
- Menganalisis dampak pembelian vendor non-utama terhadap Beban Harga Pokok Perolehan (selisih diskon)
"""

class ReportPurchaseAnalyzeWizard(models.TransientModel):
    _name = 'report.purchase.analyze.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    date_start = fields.Date(string="GRN Date Start", required=True)
    date_end = fields.Date(string="GRN Date End", required=True)
    category = fields.Many2one('product.category', string="Product Category", required=False)
    report_type = fields.Selection([('1','Purchase Analyze By Item Supplier'), ('2','Purchase Analyze By Supplier'), ('3','Purchase Analyze By UoM')], string="Report Type", required=True)
    format_print_id = fields.Selection([('pdf', 'PDF'), ('xls', 'EXCEL')], string="Format Export", required=True, default='xls')
    description = fields.Html(string='Descriptions', readonly=True, default="Data ditarik dalam satu periode tahun yang sama dan disummary perbulan.\nItem supplier = purchase per item, vendor & uom.\nSummary per vendor = grouping total per vendor,\nSummary UoM = grouping total per UoM.\nPeriode transaksi berdasarkan tanggal GRN di masing-masing unit HIS")



    # @api.multi
    def generate_report_purchase_analyze(self):
        start_year = (self.date_start).strftime('%Y')
        end_year = (self.date_end).strftime('%Y')


        if str(start_year) != str(end_year):
            raise exceptions.ValidationError(_("Period Must Be In The Current Year !!!"))

        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/purchase/report_purchase_analyze?id=' + str(self.id)
        action['target'] = 'new'
        return action



# 2021.08.26 - Purchase Receipt untuk Stock (PRC)
# GRN & PO yang dibuat di HIS dan di transfer ke Odoo
class PurchaseReceiptReportWizard(models.TransientModel):
    _name = 'purchase.receipt.report.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', string="Company", required=True,default=_get_company)
    partner_id = fields.Many2one('res.partner', string='Partner', index=True)
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)
    format_print_id = fields.Selection([('pdf','PDF'),('xls','EXCEL')],string="Format", required=True, default='xls')



    # @api.multi
    def print_all(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/purchase/purchase_receipt_report?id=' + str(self.id)
        action['target'] = 'new'
        return action



# 2021.09.09 Purchase Receipt (Non Stock)
class PickingReceiptReportWizard(models.TransientModel):
    _name = 'picking.receipt.report.wizard'
    
    company_id = fields.Many2one('res.company', string="Company", required=True)
    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date', required=True)
    partner_id = fields.Many2one('res.partner', string='Partner', index=True)
    format_print_id = fields.Selection([('pdf','PDF'),('xls','EXCEL')], string="Format", required=True, default='xls')



    # @api.multi
    def print_all(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/purchase/picking_receipt_report?id=' + str(self.id)
        action['target'] = 'new'
        return action


# 2021.09.09 Purchase Return (Non Stock)
class PickingReturnReportWizard(models.TransientModel):
    _name = 'picking.return.report.wizard'
    
    company_id = fields.Many2one('res.company', string="Company", required=True)
    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date', required=True)
    partner_id = fields.Many2one('res.partner', string='Partner', index=True)
    format_print_id = fields.Selection([('pdf','PDF'),('xls','EXCEL')], string="Format", required=True, default='xls')



    # @api.multi
    def print_all(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/purchase/picking_return_report?id=' + str(self.id)
        action['target'] = 'new'
        return action

class TampungPurchaseOrderLine(models.Model):
    _name = 'tampung.purchase.order.line'

    po_id = fields.Many2one('purchase.order', index=True)
    po_line_id = fields.Integer(string="PO Line ID")
    date_delete = fields.Datetime(string="Date Delete")    
    sync_type = sync.type

class TampungPurchaseRequisitionLine(models.Model):
    _name = 'tampung.purchase.requisition.line'


    pr_id = fields.Many2one('purchase.requisition', index=True)
    pr_line_id = fields.Integer(string="PR Line ID")
    date_delete = fields.Datetime(string="Date Delete")
    sync_type = sync.type


from datetime import datetime, timedelta, date as date_format
from json import JSONEncoder
from re import sub
import json
import decimal
#import pandas as pd
import psycopg2



class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            # wanted a simple yield str(o) in the next line,
            # but that would mean a yield on the line with super(...),
            # which wouldn't work (see my comment below), so...
            return (str(o) for o in [o])
        return super(DecimalEncoder, self).default(o)


def remove_unicode(string):
    return sub("u'([^']*)'", r'\1', string)


def _json(data):
    return json.dumps(data)
    # if not isinstance(data, decimal.Decimal):
    #     data = json.dumps(data)
    # return data 



def search(iterable, default=False):
    return next(iter(iterable), default)


def split_list(a, n):
    k, m = divmod(len(a), n)
    return (a[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in xrange(n))



def db_read(connect, query):
    result = None
    try:
        cursor = connect.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # execute query
        cursor.execute(query)
        affected = cursor.rowcount
        # fetch all data
        result = cursor.fetchall()
        cursor.close()
        connect.commit()
        # convert object to dict
        return result
    except psycopg2.Error as error:
        cursor.close()
        connect.rollback()
        raise



#pr/po syncing
class PurchaseSyncingWizard(models.TransientModel):
    _name = 'purchase.syncing.wizard'

    def _default_get_company(self):
        return self.env.company.id
    
    company_id = fields.Many2one('res.company', string='Company', default=_default_get_company)
    date_start = fields.Date(string="Date Start")
    date_end = fields.Date(string="Date End")
    type = fields.Selection([('pr', 'PR'),('po','PO')], string="Type",default='pr')
    pr_ids = fields.One2many('pr.syncing.line', 'syncing_pr_id', string="PR")
    po_ids = fields.One2many('po.syncing.line', 'syncing_po_id', string="PO")

    def syncing(self):
        from odoo.http import request
        from datetime import datetime
        import pytz
        import calendar
        import psycopg2
        
        company = self.company_id
        sync_type = company.sync_type
        
        # localdb 
        db_host = company.local_host
        db_login = company.local_user
        db_pass = company.local_pass
        db_name = company.local_db
        db_port = company.local_port
        conn_local = psycopg2.connect(database=db_name, user=db_login, host=db_host, password=db_pass, port=db_port)
        
        # consoldb 
        db_consol_host = company.consol_host
        db_consol_login = company.consol_user
        db_consol_pass = company.consol_pass
        db_consol_name = company.consol_db
        db_consol_port = company.consol_port
        conn_consol = psycopg2.connect(database=db_consol_name, user=db_consol_login, host=db_consol_host, password=db_consol_pass, port=db_consol_port)


        start_date = self.date_start
        end_date = self.date_end
        sync_type = self.company_id.sync_type
        if self.type =='po':
            for rec in self.po_ids:



                # delete odoo10_res_partner
                query = """
                DELETE FROM odoo10_res_partner 
                WHERE sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(query)



                # select from odoo16
                query = """
                          SELECT 
                              a.id, a.color, a.insurance, a.wipro_block, a.account_ar_updated, 
                              a.parent_doctor_id, a.partner_share, a.is_company, a.patient, 
                              a.state_id, a.customer_wipro, a.commercial_partner_id, a.active, 
                              a.patient_type_id, a.message_last_post, a.opt_out, a.message_bounce, 
                              a.title, a.signup_expiration, a.country_id, a.end_date_doc, a.team_id, 
                              a.debit_limit, a.last_time_entries_checked, a.vendor_wipro, 
                              a.account_ap_id, a.company_id, a.parent_id, a.tariff_id, 
                              a.specialise_id,  
                              a.supplier, a.write_date, a.doctor, a.date, a.employee, a.write_uid, 
                              a.customer, a.age, a.date_of_birth, a.sync_consol_id_main, 
                              a.sync_consol_date, a.sync_consol_id_unit, a.credit_days, 
                              a.sync_consol_sent, a.create_uid, a.credit_limit, 
                              a.virtual_bank, a.user_id, 
                              a.virtual_enable, a.create_date, a.account_ar_id, 
                              a.sync_id, a.sync_date, a.registration_code, 
                              a.type_employment, a.department, a.vendor_code, 
                              a.customer_type_wipro, a.ssn, a.sync_consol_response_status, 
                              a.sync_consol_response, a.npwp, a.virtual_number, 
                              a.virtual_beneficary, a.customer_category, 
                              a.patient_district, a.patient_city, a.patient_subdistrict, 
                              a.name, a.comment, a.website, a.street, a.city, a.display_name, 
                              a.zip, a.commercial_company_name, a.company_name, 
                              a.ref, a.email, a.function, a.lang, a.fax, a.street2, 
                              a.phone, a.tz, a.mobile, a.type, a.vat, 
                              'always' notify_email, 
                              a.signup_type, a.signup_token, 
                              a.invoice_warn_msg, a.invoice_warn, a.sale_warn, 
                              a.sale_warn_msg, a.picking_warn, a.picking_warn_msg, 
                              a.purchase_warn, a.purchase_warn_msg, a.spec, a.background, 
                              a.specialise_api_id, a.gender, a.bpjs_number, 
                              a.employee_number, a.street3, 
                              a.akl, a.contact_person, a.customer_type_api, 
                              a.practice_doctor_location, a.loa, a.reference, 
                              a.type_doctor, a.check_double, a.passport, 
                              a.sync_id_api, a.age_type, a.title_name, 
                              a.doctor_code, a.ktp, a.sip_number,
                              coalesce(a.sync_type,'{sync_type}') sync_type
                          FROM res_partner a 
                          left join purchase_order po on po.partner_id =a.id
                          WHERE coalesce(a.sync_type,'{sync_type}') = '{sync_type}'
                          and po.name ='{po_name}'
                """.format(sync_type=sync_type,po_name=rec.name)
                #cursor = conn_consol.cursor()
                #cursor.execute(query)
                result = db_read(conn_consol, query)

                if result:

                    fields_without_id = tuple(key for key in result[0] if key not in['id','sync_type'])
                    fields = tuple(key for key in result[0] if key)
                    values = ''
                    print (fields)
                            
                    for row in result:
                        if values:
                            values += ', '

                        value = ''
                        for key in fields:
                            if value:
                                value += ', '
                            else:
                                value = '('
                            #raise UserError(_(type(row[key])))
                            if type(row[key]) in [str, bytes]:
                                string = row[key]
                                #raise UserError(row[key])
                                value += "'" + string.replace("'", "''") + "'"
                                continue
                            if isinstance(row[key], str):
                                
                                value += "'" + row[key] + "'"
                                #raise UserError(value)
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

                            value += _json(row[key])
                        value += ')'
                        values += value
                    
                    excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                    columns = remove_unicode(str(fields)).replace("'", "")
                    columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                    print (values)
                    if not values:
                        print ("No data available")


                    # insert replace existing data 
                    query = """
                        INSERT INTO odoo10_res_partner %s VALUES %s 
                        ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
                    """ % (columns, values, columns_without_id, excluded)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE res_partner SET commercial_partner_id = id 
                        WHERE commercial_partner_id IS NULL
                    """
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)



                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_res_partner as a SET company_id = b.id
                        FROM res_company b WHERE b.sync_type = a.sync_type;
                    """
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                              UPDATE odoo10_res_partner SET 
                              parent_id=NULL, commercial_partner_id=NULL,
                              account_ar_id=NULL, account_ap_id=NULL, 
                              user_id=NULL, country_id=NULL, create_uid=3, write_uid=3, 
                              state_id=NULL, sync_date=CURRENT_TIMESTAMP, 
                              sync_consol_date=CURRENT_TIMESTAMP
                              WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)

                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_res_partner SET sync_consol_id_main = id 
                        WHERE coalesce(sync_consol_id_main, 0) = 0
                        --AND coalesce(sync_consol_id_main,0) = 0
                        AND sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # fetch data for update 
                    query = """
                        SELECT DISTINCT
                            coalesce(b.id,0) id, 
                            a.color, a.insurance, a.wipro_block, a.account_ar_updated, 
                            a.parent_doctor_id, a.partner_share, a.is_company, a.patient, 
                            a.state_id, a.customer_wipro, d.id as commercial_partner_id, a.active, 
                            a.patient_type_id, a.message_last_post, a.opt_out, a.message_bounce, 
                            a.title, a.signup_expiration, a.country_id, a.end_date_doc, a.team_id, 
                            a.debit_limit, a.last_time_entries_checked, a.vendor_wipro, 
                            a.account_ap_id, a.company_id, c.id as parent_id, a.tariff_id, 
                            a.specialise_id,  
                            a.supplier, a.write_date, a.doctor, a.date, a.employee, a.write_uid, 
                            a.customer, a.age, a.date_of_birth, a.sync_consol_id_main, 
                            a.sync_consol_date, a.sync_consol_id_unit, a.credit_days, 
                            a.sync_consol_sent, a.create_uid, a.credit_limit, 
                            a.virtual_bank, a.user_id, 
                            a.virtual_enable, a.create_date, a.account_ar_id, 
                            a.sync_id, a.sync_date, a.registration_code, 
                            a.type_employment, a.department, a.vendor_code, 
                            a.customer_type_wipro, a.ssn, a.sync_consol_response_status, 
                            a.sync_consol_response, a.npwp, a.virtual_number, 
                            a.virtual_beneficary, a.customer_category, 
                            a.patient_district, a.patient_city, a.patient_subdistrict, 
                            a.name, a.comment, a.website, a.street, a.city, a.display_name, 
                            a.zip, a.commercial_company_name, a.company_name, 
                            a.ref, a.email, a.function, a.lang, a.fax, a.street2, 
                            /*a.barcode,*/ a.phone, a.tz, a.mobile, a.type, a.vat, 
                            a.notify_email,
                            a.signup_type, a.signup_token, 
                            a.invoice_warn_msg, a.invoice_warn, a.sale_warn, 
                            a.sale_warn_msg, a.picking_warn, a.picking_warn_msg, 
                            a.purchase_warn, a.purchase_warn_msg, a.spec, a.background, 
                            a.specialise_api_id, a.gender, a.bpjs_number, 
                            a.employee_number, a.street3, 
                            a.akl, a.contact_person, a.customer_type_api, 
                            a.practice_doctor_location, a.loa, a.reference, 
                            a.type_doctor, a.check_double, a.passport, 
                            a.sync_id_api, a.age_type, a.title_name, 
                            a.doctor_code, a.ktp, a.sip_number, a.sync_type
                        FROM odoo10_res_partner a 
                        LEFT JOIN lateral (
                            select * from res_partner b 
                            where b.sync_type=a.sync_type 
                            AND b.sync_consol_id_main=a.sync_consol_id_main
                            order by id asc limit 1 
                        ) b on 1=1
                        LEFT JOIN lateral (
                            select * from res_partner c
                            where c.sync_type=a.sync_type 
                            AND c.sync_consol_id_main=a.parent_id
                            order by id asc limit 1
                        ) c on 1=1
                        LEFT JOIN lateral (
                            select * from res_partner d
                            where d.sync_type=a.sync_type 
                            AND d.sync_consol_id_main=a.commercial_partner_id
                            order by id asc limit 1
                        ) d on 1=1
                        WHERE 0=0
                            --AND coalesce(a.sync_consol_id_main,0) = 0
                            AND a.sync_type = '{sync_type}' 
                    """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    result = db_read(conn_local, query)
                    #raise UserError(_(str(result)))

                    # print (result) 

                    if result:
                        fields_without_id = tuple(key for key in result[0] if key not in['id'])
                        fields = fields_without_id + ('id',)
                        values = ''
                        print (fields)

                        for row in result:
                            if values:
                                values += ', '

                            value = ''
                            for key in fields:
                                if value:
                                    value += ', '
                                else:
                                    value = '('

                                if key == 'id' and row[key] == 0:
                                    value += 'DEFAULT'
                                    continue 
                              
                                if type(row[key]) in [str, bytes]:
                                    string = row[key]
                                    value += "'" + string.replace("'", "''") + "'"
                                    continue
                                if isinstance(row[key], str):
                                
                                    value += "'" + row[key] + "'"
                                    #raise UserError(value)
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

                                #print (value)
                                value += _json(row[key])
                            value += ')'
                            values += value
                        
                        excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                        columns = remove_unicode(str(fields)).replace("'", "")
                        columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                        print (values)
                        if not values:
                            print ("No data available")


                        # insert replace existing data 
                        query = """
                            INSERT INTO res_partner %s VALUES %s 
                            ON CONFLICT (id) DO UPDATE SET %s = %s
                        """ % (columns, values, columns_without_id, excluded)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        


                        # truncate consol data
                        query = """
                            DELETE FROM odoo10_res_partner 
                            WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()





                # delete odoo10_product_uom
                query = """
                DELETE FROM odoo10_uom_uom 
                WHERE sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(query)



                # select from odoo16
                query = """
                        SELECT 
                            a.id, a.wipro_block, a.create_uid, a.sync_date, a.sync_consol_date, 
                            a.sync_consol_id_main, a.sync_consol_id_unit, a.rounding, 
                            a.write_uid, a.write_date, a.factor, a.active, a.create_date, 
                            a.category_id, a.sync_id, a.name, a.sync_id_api, 
                            a.uom_type, a.code, coalesce(a.sync_type,'{sync_type}') sync_type
                            FROM uom_uom a
                            left join purchase_order_line pol on pol.product_uom = a.id
                            left join purchase_order po on po.id = pol.order_id
                            WHERE coalesce(a.sync_type,'{sync_type}') = '{sync_type}'
                            and po.name ='{po_name}'
                """.format(sync_type=sync_type,po_name=rec.name)
                #cursor = conn_consol.cursor()
                #cursor.execute(query)
                result = db_read(conn_consol, query)

                if result:

                    fields_without_id = tuple(key for key in result[0] if key not in['id','sync_type'])
                    fields = tuple(key for key in result[0] if key)
                    values = ''
                    print (fields)
                            
                    for row in result:
                        if values:
                            values += ', '

                        value = ''
                        for key in fields:
                            if value:
                                value += ', '
                            else:
                                value = '('
                            #raise UserError(_(type(row[key])))
                            if type(row[key]) in [str, bytes]:
                                string = row[key]
                                #raise UserError(row[key])
                                value += "'" + string.replace("'", "''") + "'"
                                continue
                            if isinstance(row[key], str):
                                
                                value += "'" + row[key] + "'"
                                #raise UserError(value)
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

                            value += _json(row[key])
                        value += ')'
                        values += value
                    
                    excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                    columns = remove_unicode(str(fields)).replace("'", "")
                    columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                    print (values)
                    if not values:
                        print ("No data available")


                    # insert replace existing data 
                    query = """
                        INSERT INTO odoo10_uom_uom %s VALUES %s 
                        ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
                    """ % (columns, values, columns_without_id, excluded)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_uom_uom as a SET company_id = b.id
                        FROM res_company b WHERE b.sync_type = a.sync_type;
                    """
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_uom_uom SET 
                        create_uid=3, write_uid=3, 
                        sync_date=CURRENT_TIMESTAMP, 
                        sync_consol_date=CURRENT_TIMESTAMP
                        WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)

                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_uom_uom SET sync_consol_id_main = id 
                        WHERE coalesce(sync_consol_id_main, 0) = 0
                        --AND coalesce(sync_consol_id_main,0) = 0
                        AND sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # fetch data for update 
                    query = """
                        SELECT DISTINCT
                        coalesce(b.id,0) id, 
                        a.wipro_block, a.create_uid, a.sync_date, a.sync_consol_date, 
                        a.sync_consol_id_main, a.sync_consol_id_unit, a.rounding, 
                        a.write_uid, a.write_date, a.factor, a.active, a.create_date, 
                        a.category_id, a.sync_id, a.name, a.sync_id_api, 
                        a.uom_type, a.code, a.sync_type
                        FROM odoo10_uom_uom a 
                        LEFT JOIN LATERAL (
                            SELECT * FROM uom_uom b 
                            WHERE b.sync_type=a.sync_type 
                            AND b.sync_consol_id_main=a.sync_consol_id_main
                            ORDER BY id ASC LIMIT 1
                        ) b on 1=1
                        WHERE 0=0
                            --AND coalesce(a.sync_consol_id_main,0) = 0
                            AND a.sync_type = '{sync_type}' 
 
                    """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    result = db_read(conn_local, query)
                    #raise UserError(_(str(result)))

                    # print (result) 

                    if result:
                        fields_without_id = tuple(key for key in result[0] if key not in['id'])
                        fields = fields_without_id + ('id',)
                        values = ''
                        print (fields)

                        for row in result:
                            if values:
                                values += ', '

                            value = ''
                            for key in fields:
                                if value:
                                    value += ', '
                                else:
                                    value = '('

                                if key == 'id' and row[key] == 0:
                                    value += 'DEFAULT'
                                    continue 
                              
                                if type(row[key]) in [str, bytes]:
                                    string = row[key]
                                    value += "'" + string.replace("'", "''") + "'"
                                    continue
                                if isinstance(row[key], str):
                                
                                    value += "'" + row[key] + "'"
                                    #raise UserError(value)
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

                                #print (value)
                                value += _json(row[key])
                            value += ')'
                            values += value
                        
                        excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                        columns = remove_unicode(str(fields)).replace("'", "")
                        columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                        print (values)
                        if not values:
                            print ("No data available")


                        # insert replace existing data 
                        query = """
                            INSERT INTO uom_uom %s VALUES %s 
                            ON CONFLICT (id) DO UPDATE SET %s = %s
                        """ % (columns, values, columns_without_id, excluded)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        


                        # truncate consol data
                        query = """
                            DELETE FROM odoo10_uom_uom 
                            WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()



                # delete odoo10_product_category
                query = """
                DELETE FROM odoo10_product_category 
                WHERE sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(query)



                # select from odoo16
                query = """

                        SELECT 
                            a.id, a.parent_left, a.parent_right, a.create_uid, a.stock_output_id, 
                            a.income_account_id, a.wipro_block, a.sync_consol_id_main, a.sync_consol_id_unit, 
                            a.sync_consol_date, a.write_uid, a.parent_id, a.write_date, a.create_date, 
                            a.removal_strategy_id, a.parent_sync_id, a.sync_id, a.sync_is_service, 
                            a.sync_date, a.company_id, a.stock_valuation_id, a.stock_input_id, 
                            a.active, a.stock_journal_id, a.expense_account_id, a.property_account_accrual_id, 
                            a.name, a.sync_id_api, a.lob_los, a.code, a.type, 
                            coalesce(a.sync_type,'{sync_type}') sync_type
                            FROM product_category a 
                            left join product_template pt on pt.categ_id = a.id
                            left join product_product pp on pp.product_tmpl_id = pt.id
                            left join purchase_order_line pol on pol.product_id = pp.id
                            left join purchase_order po on po.id = pol.order_id
                            WHERE coalesce(a.sync_type,'{sync_type}') = '{sync_type}'
                            and po.name ='{po_name}'
                """.format(sync_type=sync_type,po_name=rec.name)
                #cursor = conn_consol.cursor()
                #cursor.execute(query)
                result = db_read(conn_consol, query)

                if result:

                    fields_without_id = tuple(key for key in result[0] if key not in['id','sync_type'])
                    fields = tuple(key for key in result[0] if key)
                    values = ''
                    print (fields)
                            
                    for row in result:
                        if values:
                            values += ', '

                        value = ''
                        for key in fields:
                            if value:
                                value += ', '
                            else:
                                value = '('
                            #raise UserError(_(type(row[key])))
                            if type(row[key]) in [str, bytes]:
                                string = row[key]
                                #raise UserError(row[key])
                                value += "'" + string.replace("'", "''") + "'"
                                continue
                            if isinstance(row[key], str):
                                
                                value += "'" + row[key] + "'"
                                #raise UserError(value)
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

                            value += _json(row[key])
                        value += ')'
                        values += value
                    
                    excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                    columns = remove_unicode(str(fields)).replace("'", "")
                    columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                    print (values)
                    if not values:
                        print ("No data available")


                    # insert replace existing data 
                    query = """
                        INSERT INTO odoo10_product_category %s VALUES %s 
                        ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
                    """ % (columns, values, columns_without_id, excluded)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_product_category as a SET company_id = b.id
                        FROM res_company b WHERE b.sync_type = a.sync_type;
                    """
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_product_category SET
                        parent_left=NULL, parent_right=NULL, create_uid=3, write_uid=3, 
                        removal_strategy_id=NULL, parent_sync_id=NULL, 
                        --property_account_accrual_id=NULL, stock_valuation_id=NULL, 
                        --stock_input_id=NULL, stock_output_id=NULL, income_account_id=NULL, 
                        --stock_journal_id=NULL, expense_account_id=NULL, 
                        sync_date=CURRENT_TIMESTAMP, 
                        sync_consol_date=CURRENT_TIMESTAMP
                           WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)

                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_product_category SET sync_consol_id_main = id 
                        WHERE coalesce(sync_consol_id_main, 0) = 0
                        --AND coalesce(sync_consol_id_main,0) = 0
                        AND sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # fetch data for update 
                    query = """
                        SELECT DISTINCT
                            coalesce(b.id,0) id, 
                            a.parent_left, a.parent_right, a.create_uid, 
                            a.wipro_block, a.sync_consol_id_main, a.sync_consol_id_unit, 
                            a.sync_consol_date, a.write_uid, c.id parent_id, a.write_date, a.create_date, 
                            a.removal_strategy_id, a.parent_sync_id, a.sync_id, a.sync_is_service, 
                            a.sync_date, a.company_id, 
                            --a.stock_valuation_id, a.stock_input_id, a.stock_output_id, a.income_account_id,
                            --a.stock_journal_id, a.expense_account_id, a.property_account_accrual_id, 
                            a.active, a.name, a.sync_id_api, a.lob_los, a.code, a.type, a.sync_type
                        FROM odoo10_product_category a 
                        LEFT JOIN LATERAL (
                            SELECT * FROM product_category b 
                            WHERE b.sync_type=a.sync_type 
                            AND b.sync_consol_id_main=a.sync_consol_id_main
                            ORDER BY id ASC LIMIT 1
                        ) b on 1=1
                        LEFT JOIN LATERAL (
                            SELECT * FROM product_category c 
                            WHERE c.sync_type=a.sync_type
                            AND c.sync_consol_id_main=a.parent_id
                            ORDER BY id ASC LIMIT 1 
                        ) c on 1=1
                        WHERE 0=0
                            -- AND coalesce(a.sync_consol_id_main,0) = 0
                            AND a.sync_type = '{sync_type}' 
 
                    """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    result = db_read(conn_local, query)
                    #raise UserError(_(str(result)))

                    # print (result) 

                    if result:
                        fields_without_id = tuple(key for key in result[0] if key not in['id'])
                        fields = fields_without_id + ('id',)
                        values = ''
                        print (fields)

                        for row in result:
                            if values:
                                values += ', '

                            value = ''
                            for key in fields:
                                if value:
                                    value += ', '
                                else:
                                    value = '('

                                if key == 'id' and row[key] == 0:
                                    value += 'DEFAULT'
                                    continue 
                              
                                if type(row[key]) in [str, bytes]:
                                    string = row[key]
                                    value += "'" + string.replace("'", "''") + "'"
                                    continue
                                if isinstance(row[key], str):
                                
                                    value += "'" + row[key] + "'"
                                    #raise UserError(value)
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

                                #print (value)
                                value += _json(row[key])
                            value += ')'
                            values += value
                        
                        excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                        columns = remove_unicode(str(fields)).replace("'", "")
                        columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                        print (values)
                        if not values:
                            print ("No data available")


                        # insert replace existing data 
                        query = """
                            INSERT INTO product_category %s VALUES %s 
                            ON CONFLICT (id) DO UPDATE SET %s = %s
                        """ % (columns, values, columns_without_id, excluded)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        


                        # truncate consol data
                        query = """
                            DELETE FROM odoo10_product_category 
                            WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()



                # delete odoo10_product_template
                query = """
                DELETE FROM odoo10_product_template 
                WHERE sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(query)



                # select from odoo16
                query = """
                    SELECT 
                        a.id, a.write_date, a.warranty, a.list_price, a.weight, a.sequence, a.color, 
                        a.write_uid, a.uom_id, a.active, a.categ_id, a.rental, a.location_id, 
                        a.warehouse_id, a.sale_delay, a.produce_delay, a.sync_id, a.sync_date, 
                        a.wipro_block, a.api_post_timestamp, a.base_price_manual, 
                        a.base_price_manual_active, a.uom2_id, a.conversion_rate, 
                        a.sync_is_service, a.sync_max_days, a.base_price, a.strength, 
                        a.sync_is_package, a.sync_categ_id, a.consignment, 
                        a.sync_consol_date, 
                        a.sync_consol_id_unit, a.sync_consol_id_main, a.antibiotic, 
                        a.narcotic, a.psychotropic, a.generic, a.create_date, 
                        a.create_uid, a.sale_ok, a.purchase_ok, a.message_last_post, 
                        a.company_id, a.uom_po_id, a.volume, a.description_purchase, 
                        a.default_code, a.pharmacalogy, a.mims_type, 
                        a.catalog_code, a.api_post_payload, a.api_post_key, 
                        a.api_post_url, a.description_sale, a.description, 
                        a.api_post_response, a.api_post_status, a.manufacturer_code, 
                        a.sync_id_api, a.name, a.mims_ref, a.detailed_type, a.sale_line_warn, 
                        a.sale_line_warn_msg, a.track_service, a.invoice_policy, 
                        a.expense_policy, a.tracking, a.manufacturer, a.description_picking, 
                        a.shelf, a.brand, a.loblos, a.purchase_line_warn_msg, 
                        a.purchase_method, a.purchase_line_warn, a.purchase_requisition, 
                        coalesce(a.sync_type,'{sync_type}') sync_type
                    FROM product_template a 
                    left join product_product pp on pp.product_tmpl_id =a.id
                    left join purchase_order_line pol on pol.product_id =pp.id 
                    left join purchase_order po on po.id = pol.order_id
                    WHERE coalesce(a.sync_type,'{sync_type}') = '{sync_type}'
                        AND po.name='{po_name}'
                """.format(sync_type=sync_type,po_name=rec.name)
                #cursor = conn_consol.cursor()
                #cursor.execute(query)
                result = db_read(conn_consol, query)

                if result:

                    fields_without_id = tuple(key for key in result[0] if key not in['id','sync_type'])
                    fields = tuple(key for key in result[0] if key)
                    values = ''
                    print (fields)
                            
                    for row in result:
                        if values:
                            values += ', '

                        value = ''
                        for key in fields:
                            if value:
                                value += ', '
                            else:
                                value = '('
                            #raise UserError(_(type(row[key])))
                            if type(row[key]) in [str, bytes]:
                                string = row[key]
                                #raise UserError(row[key])
                                value += "'" + string.replace("'", "''") + "'"
                                continue
                            if isinstance(row[key], str):
                                
                                value += "'" + row[key] + "'"
                                #raise UserError(value)
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

                            value += _json(row[key])
                        value += ')'
                        values += value
                    
                    excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                    columns = remove_unicode(str(fields)).replace("'", "")
                    columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                    print (values)
                    if not values:
                        print ("No data available")


                    # insert replace existing data 
                    query = """
                        INSERT INTO odoo10_product_template %s VALUES %s 
                        ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
                    """ % (columns, values, columns_without_id, excluded)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)



                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_product_template as a SET company_id = b.id
                        FROM res_company b WHERE b.sync_type = a.sync_type;
                    """
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_product_template SET
                        create_uid=3, write_uid=3, warranty=NULL, list_price=NULL, weight=NULL, 
                        "sequence"=NULL, color=NULL, description_purchase=NULL, message_last_post=NULL,
                        description_sale=NULL, description=NULL, volume=NULL, rental=NULL, 
                        sale_line_warn='no-message', sale_line_warn_msg=NULL, sale_delay=NULL,
                        purchase_line_warn_msg=NULL, sync_date=CURRENT_TIMESTAMP, 
                        sync_consol_date=CURRENT_TIMESTAMP
                        WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)

                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_product_template SET sync_consol_id_main = id 
                        WHERE coalesce(sync_consol_id_main, 0) = 0
                        --AND coalesce(sync_consol_id_main,0) = 0
                        AND sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_product_template SET default_code = '[NULL]'
                        WHERE default_code IS NULL
                            AND sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)



                    # fetch data for update 
                    query = """
                        SELECT DISTINCT
                            coalesce(b.id,0) id, 
                            a.write_date, a.warranty, a.list_price, a.weight, a.sequence, a.color, 
                            a.write_uid, coalesce(uom.id,1) as uom_id, a.active, coalesce(c.id,10) as categ_id, a.rental, 
                            a.location_id, a.warehouse_id, a.sale_delay, a.produce_delay, a.sync_id, 
                            a.sync_date, a.wipro_block, a.api_post_timestamp, a.base_price_manual, 
                            a.base_price_manual_active, uom_po.id uom2_id, a.conversion_rate, 
                            a.sync_is_service, a.sync_max_days, a.base_price, a.strength, 
                            a.sync_is_package, a.sync_categ_id, a.consignment, a.sync_consol_date, 
                            a.sync_consol_id_unit, a.sync_consol_id_main, a.antibiotic, 
                            a.narcotic, a.psychotropic, a.generic, a.create_date, 
                            a.create_uid, a.sale_ok, a.purchase_ok, a.message_last_post, 
                            a.company_id, coalesce(uom_po.id,1) uom_po_id, a.volume, a.description_purchase, 
                            a.default_code, a.pharmacalogy, a.mims_type, 
                            a.catalog_code, a.api_post_payload, a.api_post_key, 
                            a.api_post_url, a.description_sale, a.description, 
                            a.api_post_response, a.api_post_status, a.manufacturer_code, 
                            a.sync_id_api, a.name, a.mims_ref, a.detailed_type, a.sale_line_warn, 
                            a.sale_line_warn_msg, a.track_service, a.invoice_policy,
                            a.expense_policy, a.tracking, a.manufacturer, a.description_picking, 
                            a.shelf, a.brand, a.loblos, a.purchase_line_warn_msg, 
                            a.purchase_method, a.purchase_line_warn, a.purchase_requisition, a.sync_type
                        FROM odoo10_product_template a 
                        LEFT JOIN LATERAL (
                            SELECT * FROM product_template b 
                            WHERE b.sync_type=a.sync_type 
                            AND b.sync_consol_id_main=a.sync_consol_id_main
                            ORDER BY id ASC LIMIT 1 
                        ) b on 1=1
                        LEFT JOIN lateral (
                            select * from product_category c 
                            where c.sync_type=a.sync_type 
                            AND c.sync_consol_id_main=a.categ_id
                            order by id asc limit 1
                        ) c on 1=1
                        LEFT JOIN lateral (
                            select * from uom_uom uom 
                            where uom.sync_type=a.sync_type 
                            AND uom.sync_consol_id_main=a.uom_id
                            order by id asc limit 1
                        ) uom on 1=1
                        LEFT JOIN lateral (
                            select * from uom_uom uom2 
                            where uom2.sync_type=a.sync_type 
                            AND uom2.sync_consol_id_main=a.uom2_id
                            order by id asc limit 1
                        ) uom2 on 1=1
                        LEFT JOIN lateral (
                            select * from uom_uom uom_po
                            where uom_po.sync_type=a.sync_type 
                            AND uom_po.sync_consol_id_main=a.uom_po_id
                            order by id asc limit 1
                        ) uom_po on 1=1
                        WHERE 0=0
                            --AND coalesce(a.sync_consol_id_main,0) = 0
                            AND a.sync_type = '{sync_type}' 
                    """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    result = db_read(conn_local, query)
                    #raise UserError(_(str(result)))

                    # print (result) 

                    if result:
                        fields_without_id = tuple(key for key in result[0] if key not in['id'])
                        fields = fields_without_id + ('id',)
                        values = ''
                        print (fields)

                        for row in result:
                            if values:
                                values += ', '

                            value = ''
                            for key in fields:
                                if value:
                                    value += ', '
                                else:
                                    value = '('

                                if key == 'id' and row[key] == 0:
                                    value += 'DEFAULT'
                                    continue 
                              
                                if type(row[key]) in [str, bytes]:
                                    string = row[key]
                                    value += "'" + string.replace("'", "''") + "'"
                                    continue
                                if isinstance(row[key], str):
                                
                                    value += "'" + row[key] + "'"
                                    #raise UserError(value)
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

                                #print (value)
                                value += _json(row[key])
                            value += ')'
                            values += value
                        
                        excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                        columns = remove_unicode(str(fields)).replace("'", "")
                        columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                        print (values)
                        if not values:
                            print ("No data available")


                        # insert replace existing data 
                        query = """
                            INSERT INTO product_template %s VALUES %s 
                            ON CONFLICT (id) DO UPDATE SET %s = %s
                        """ % (columns, values, columns_without_id, excluded)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()
                        

                        # insert replace existing data 
                        query = """
                            UPDATE product_product AS pp SET 
                                default_code = pt.default_code, 
                                write_date = pt.write_date
                            FROM product_template pt 
                            WHERE pt.id = pp.product_tmpl_id 
                            AND pt.sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()



                        # insert replace existing data 
                        query = """
                            INSERT INTO product_product(
                                product_tmpl_id, default_code, create_uid, 
                                create_date, write_uid, write_date)
                            SELECT 
                                pt.id product_tmpl_id, 
                                coalesce(pt.default_code,'[NULL]') default_code,
                                pt.create_uid, pt.create_date, 
                                pt.write_uid, pt.write_date
                            FROM product_template pt 
                            WHERE NOT EXISTS(
                                SELECT 1 FROM product_product t 
                                WHERE t.product_tmpl_id = pt."id"
                            ) AND pt.sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()



                        # truncate consol data
                        query = """
                            DELETE FROM odoo10_product_template 
                            WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        






                # delete odoo10_purchase_order
                query = """
                DELETE FROM odoo10_purchase_order 
                WHERE sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(query)



                # select from odoo16
                query = """
                SELECT 
                    a.id, a.date_approve::date, a.date_planned::date, a.group_id, 
                    a.updated_date, a.is_return, a.sync_id, a.ppn, a.wipro_date, 
                    a.revisi, a.type_id, a.total_tampilan, a.no_approval, 
                    a.bill_date, a.pph, a.total_discount, a.revisi_sequence, 
                    a.sync_date, a.approve_rule_id, a.is_consignment, a.dp_value, 
                    a.sync_consol_date, a.sync_consol_id_main, a.sync_consol_id_unit, 
                    a.sync_consol_sent, a.create_date, a.write_uid, a.currency_id, 
                    a.date_order, a.partner_id, a.dest_address_id, a.create_uid, 
                    a.amount_untaxed, a.picking_type_id, 
                    --a.message_last_post, 
                    a.company_id, a.amount_tax, a.incoterm_id,  
                    a.write_date, a.fiscal_position_id, a.amount_total, a.origin, 
                    a.notes, a.purchase_name, a.confirm_by, a.item_type, a.po_from, 
                    a.vendor_ref, a.rfq, a.sync_consol_response_status, a.sync_id_api, 
                    a.approve_next_store, a.name, a.remarks, a.state::text, a.wipro_type, 
                    a.approve_status, a.revisi_name, a.sync_rate_contract, a.partner_ref, 
                    a.title, a.sync_consol_response, a.invoice_status, a.sync_purchase_type, 
                    coalesce(a.sync_type,'{sync_type}') sync_type
                FROM purchase_order a 
                WHERE coalesce(a.sync_type,'{sync_type}') = '{sync_type}'
                    and a.name ='{po_name}'
                """.format(sync_type=sync_type,po_name=rec.name)
                #cursor = conn_consol.cursor()
                #cursor.execute(query)
                result = db_read(conn_consol, query)

                #result = cursor.fetchall() 
                #raise UserError(_(str(result)))
                    

                if result:

                    fields_without_id = tuple(key for key in result[0] if key not in['id','sync_type'])
                    fields = tuple(key for key in result[0] if key)
                    values = ''
                    print (fields)
                            
                    for row in result:
                        if values:
                            values += ', '

                        value = ''
                        for key in fields:
                            if value:
                                value += ', '
                            else:
                                value = '('
                            #raise UserError(_(type(row[key])))
                            if type(row[key]) in [str, bytes]:
                                string = row[key]
                                #raise UserError(row[key])
                                value += "'" + string.replace("'", "''") + "'"
                                continue
                            if isinstance(row[key], str):
                                
                                value += "'" + row[key] + "'"
                                #raise UserError(value)
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

                            value += _json(row[key])
                        value += ')'
                        values += value
                    
                    excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                    columns = remove_unicode(str(fields)).replace("'", "")
                    columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                    print (values)
                    if not values:
                        print ("No data available")


                    # insert replace existing data 
                    query = """
                        INSERT INTO odoo10_purchase_order %s VALUES %s 
                        ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
                    """ % (columns, values, columns_without_id, excluded)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_purchase_order as a SET company_id = b.id
                        FROM res_company b WHERE b.sync_type = a.sync_type;
                    """
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_purchase_order SET 
                        create_uid=3, write_uid=3, currency_id=12, 
                        dest_address_id=NULL, payment_term_id=NULL, 
                        incoterm_id=NULL, fiscal_position_id=NULL, 
                        group_id=NULL, 
                        --type_id=NULL, approve_rule_id=NULL,
                        sync_date=CURRENT_TIMESTAMP, 
                        sync_consol_date=CURRENT_TIMESTAMP
                        WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)

                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_purchase_order SET sync_consol_id_main = id 
                        WHERE coalesce(sync_consol_id_main, 0) = 0
                        --AND coalesce(sync_consol_id_main,0) = 0
                        AND sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # fetch data for update 
                    query = """
                        SELECT DISTINCT
                            coalesce(b.id,0) id, 
                            a.date_approve, a.date_planned, 
                            a.updated_date, a.is_return, a.sync_id, a.ppn, a.wipro_date, 
                            a.revisi, d.id type_id, a.total_tampilan, a.no_approval, 
                            a.bill_date, a.pph, a.total_discount, a.revisi_sequence, 
                            a.sync_date, e.id approve_rule_id, a.is_consignment, a.dp_value, 
                            a.sync_consol_date, a.sync_consol_id_main, a.sync_consol_id_unit, 
                            a.sync_consol_sent, a.create_date, a.write_uid, a.currency_id, 
                            a.date_order, c.id as partner_id, a.dest_address_id, 
                            a.amount_untaxed, spt.id as picking_type_id, 
                            --a.message_last_post, 
                            a.company_id, a.amount_tax,  
                            a.write_date, a.fiscal_position_id, a.amount_total, a.origin, 
                            a.notes, a.purchase_name, a.confirm_by, a.item_type, a.po_from, 
                            a.vendor_ref, a.rfq, a.sync_consol_response_status, a.sync_id_api, 
                            a.approve_next_store, a.name, a.remarks, a.wipro_type, 
                            a.approve_status, a.revisi_name, a.sync_rate_contract, a.partner_ref, 
                            a.title, a.sync_consol_response, a.sync_purchase_type,
                            coalesce(b.create_uid,a.create_uid) create_uid,
                            coalesce(b.create_date,a.create_date) create_date,
                            coalesce(b.invoice_status, 'to invoice') invoice_status,
                            coalesce(b.state, a.state) state, a.sync_type
                        FROM odoo10_purchase_order a 
                        LEFT JOIN lateral (
                            select * from purchase_order b 
                            where b.sync_type=a.sync_type 
                            AND (b.sync_consol_id_main=a.sync_consol_id_main) -- or b.sync_id_api=a.sync_id_api)
                            order by id asc limit 1
                        ) b on 1=1
                        INNER JOIN lateral (
                            select * from res_partner c
                            where c.sync_type=a.sync_type 
                            AND c.sync_consol_id_main=a.partner_id
                            order by id asc limit 1
                        ) c on 1=1
                        LEFT JOIN lateral (
                            select * from purchase_type d
                            where d.sync_type=a.sync_type 
                            AND d.sync_consol_id_main=a.type_id
                            order by id asc limit 1
                        ) d on 1=1

                        LEFT JOIN lateral (
                            select * from purchase_approval_rule e
                            where e.sync_consol_id_main=a.approve_rule_id
                            order by id asc limit 1
                        ) e on 1=1

                        LEFT JOIN lateral (
                            select * from stock_picking_type spt 
                            where spt.sync_type=a.sync_type 
                            AND spt.sync_consol_id_main=a.picking_type_id
                            order by id asc limit 1 
                        ) spt on 1=1
                        --WHERE coalesce(a.sync_consol_id_main,0) = 0
                            AND a.sync_type = '{sync_type}' 
                    """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    result = db_read(conn_local, query)
                    #raise UserError(_(str(result)))

                    # print (result) 

                    if result:
                        fields_without_id = tuple(key for key in result[0] if key not in['id'])
                        fields = fields_without_id + ('id',)
                        values = ''
                        print (fields)

                        for row in result:
                            if values:
                                values += ', '

                            value = ''
                            for key in fields:
                                if value:
                                    value += ', '
                                else:
                                    value = '('

                                if key == 'id' and row[key] == 0:
                                    value += 'DEFAULT'
                                    continue 
                              
                                if type(row[key]) in [str, bytes]:
                                    string = row[key]
                                    value += "'" + string.replace("'", "''") + "'"
                                    continue
                                if isinstance(row[key], str):
                                
                                    value += "'" + row[key] + "'"
                                    #raise UserError(value)
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

                                #print (value)
                                value += _json(row[key])
                            value += ')'
                            values += value
                        
                        excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                        columns = remove_unicode(str(fields)).replace("'", "")
                        columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                        print (values)
                        if not values:
                            print ("No data available")


                        # insert replace existing data 
                        query = """
                            INSERT INTO purchase_order %s VALUES %s 
                            ON CONFLICT (id) DO UPDATE SET %s = %s
                        """ % (columns, values, columns_without_id, excluded)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        


                        # truncate consol data
                        query = """
                            DELETE FROM odoo10_purchase_order 
                            WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()



                # delete odoo10_purchase_order_line
                query = """
                DELETE FROM odoo10_purchase_order_line 
                WHERE sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(query)
                



                # select from odoo16
                query = """
                SELECT 
                    a.id, a.discount_total, a.create_date, a.product_uom, a.price_unit, 
                    a.qty_invoiced, a.write_uid, a.currency_id, a.product_qty, a.partner_id, 
                    a.qty_received, a.create_uid, a.price_tax, a.sequence, a.company_id, 
                    a.picking_id, a.cost_center_active, a.sync_consol_id_unit, a.sync_consol_date, 
                    a.sync_consol_id_main, a.account_analytic_id, a.order_id, a.price_subtotal, 
                    a.write_date, pp.product_tmpl_id as product_id, a.price_total, a.date_planned, 
                    a.ppn, a.has_tax, a.wipro_date, a.sync_date, 
                    --a.conversion_rate, 
                    a.normal_price, 
                    a.discount_persen, a.product_categ_id, a.price_unit2, a.sync_id_product, 
                    a.normal_uom, a.is_conversion, a.uom_small, a.product_uom2, a.normal_qty, 
                    a.invoice_id, a.product_qty2, a.is_consignment, a.sync_id, a.converted, 
                    a.tanggal_terima, a.discount_value, a.state, a.name, a.no_grn, 
                    a.status_contract, concat(a.sync_id_api,'-', cast(a.id as varchar)) sync_id_api, 
                    coalesce(a.sync_type,'{sync_type}') sync_type
                FROM purchase_order_line a 
                INNER JOIN purchase_order po ON po.id = a.order_id
                LEFT JOIN product_product pp ON pp.id = a.product_id
                --LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE coalesce(a.sync_type,'{sync_type}') = '{sync_type}'
                    AND po.name ='{po_name}'
                """.format(sync_type=sync_type,po_name=rec.name)
                #cursor = conn_consol.cursor()
                #cursor.execute(query)
                result = db_read(conn_consol, query)

                #result = cursor.fetchall() 
                #raise UserError(_(str(result)))
                    

                if result:

                    fields_without_id = tuple(key for key in result[0] if key not in['id','sync_type'])
                    fields = tuple(key for key in result[0] if key)
                    values = ''
                    print (fields)
                            
                    for row in result:
                        if values:
                            values += ', '

                        value = ''
                        for key in fields:
                            if value:
                                value += ', '
                            else:
                                value = '('
                            #raise UserError(_(type(row[key])))
                            if type(row[key]) in [str, bytes]:
                                string = row[key]
                                #raise UserError(row[key])
                                value += "'" + string.replace("'", "''") + "'"
                                continue
                            if isinstance(row[key], str):
                                
                                value += "'" + row[key] + "'"
                                #raise UserError(value)
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

                            value += _json(row[key])
                        value += ')'
                        values += value
                    
                    excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                    columns = remove_unicode(str(fields)).replace("'", "")
                    columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                    print (values)
                    if not values:
                        print ("No data available")


                    # insert replace existing data 
                    query = """
                        INSERT INTO odoo10_purchase_order_line %s VALUES %s 
                        ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
                    """ % (columns, values, columns_without_id, excluded)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_purchase_order_line as a SET company_id = b.id
                        FROM res_company b WHERE b.sync_type = a.sync_type;
                    """
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_purchase_order_line SET 
                        create_uid=3, write_uid=3, currency_id=12, 
                        account_analytic_id=NULL, 
                        invoice_id=NULL, --picking_id=NULL, 
                        normal_uom=NULL, uom_small=NULL,
                        sync_date=CURRENT_TIMESTAMP, 
                        sync_consol_date=CURRENT_TIMESTAMP
                        WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)

                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_purchase_order_line SET sync_consol_id_main = id 
                        WHERE coalesce(sync_consol_id_main, 0) = 0
                        --AND coalesce(sync_consol_id_main,0) = 0
                        AND sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # fetch data for update 
                    query = """
                        SELECT DISTINCT
                            coalesce(b.id,0) id, 
                            a.discount_total, a.create_date, coalesce(uom.id,1) as product_uom, a.price_unit, 
                            a.qty_invoiced, a.write_uid, a.currency_id, a.product_qty, rp.id as partner_id, 
                            a.qty_received, a.create_uid, a.price_tax, a.sequence, a.company_id, 
                            sp.id as picking_id, a.cost_center_active, a.sync_consol_id_unit, a.sync_consol_date, 
                            a.sync_consol_id_main, a.account_analytic_id, po.id as order_id, a.price_subtotal, 
                            a.write_date, pp.id as product_id, a.price_total, a.date_planned, a.has_tax, 
                            a.wipro_date, a.sync_date, 
                            --a.conversion_rate, 
                            a.normal_price, a.ppn, 
                            a.discount_persen, pc.id as product_categ_id, a.price_unit2, a.sync_id_product, 
                            a.normal_uom, a.is_conversion, a.uom_small, uom2.id as product_uom2, a.normal_qty, 
                            a.invoice_id, a.product_qty2, a.is_consignment, a.sync_id, a.converted, 
                            a.tanggal_terima, a.discount_value, a.state, a.name, a.no_grn, 
                            a.status_contract, a.sync_id_api, a.sync_type
                        FROM odoo10_purchase_order_line a 
                        LEFT JOIN lateral (
                            select * from purchase_order_line b 
                            where b.sync_type=a.sync_type 
                            AND (b.sync_consol_id_main=a.sync_consol_id_main)
                            order by id asc limit 1
                        ) b on 1=1
                        LEFT JOIN lateral (
                            select * from res_partner rp
                            where rp.sync_type=a.sync_type 
                            AND rp.sync_consol_id_main=a.partner_id
                            order by id asc limit 1
                        ) rp on 1=1
                        LEFT JOIN lateral (
                            select * from product_template c
                            where c.sync_type=a.sync_type 
                            AND c.sync_consol_id_main=a.product_id
                            order by id asc limit 1
                        ) c on 1=1
                        LEFT JOIN lateral (
                            select * from product_product pp
                            where pp.product_tmpl_id=c.id
                            order by id asc limit 1
                        ) pp on 1=1
                        LEFT JOIN lateral (
                            select * from purchase_order po
                            where po.sync_type=a.sync_type
                            AND po.sync_consol_id_main=a.order_id
                            order by id asc limit 1
                        ) po on 1=1
                        LEFT JOIN lateral (
                            select * from product_category pc
                            where pc.sync_type=a.sync_type
                            AND pc.sync_consol_id_main=a.product_categ_id
                            order by id asc limit 1
                        ) pc on 1=1
                        LEFT JOIN lateral (
                            select * from uom_uom uom
                            where uom.sync_type=a.sync_type
                            AND uom.sync_consol_id_main=a.product_uom
                            order by id asc limit 1 
                        ) uom on 1=1
                        LEFT JOIN lateral (
                            select * from uom_uom uom2
                            where uom2.sync_type=a.sync_type
                            AND uom2.sync_consol_id_main=a.product_uom
                            order by id asc limit 1 
                        ) uom2 on 1=1
                        LEFT JOIN lateral (
                            select * from stock_picking sp
                            where sp.sync_type=a.sync_type
                            AND sp.sync_consol_id_main=a.picking_id
                            order by id asc limit 1 
                        ) sp on 1=1
                            -- AND coalesce(a.sync_consol_id_main,0) = 0
                            AND a.sync_type = '{sync_type}' 


                        --WHERE coalesce(a.sync_consol_id_main,0) = 0
                          --  AND a.sync_type = '{sync_type}' 
                           -------- AND not exists(select 1 from purchase_order_line t where t.sync_type=a.sync_type and t.sync_id_api=a.sync_id_api)
                    """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    result = db_read(conn_local, query)
                    #raise UserError(_(str(result)))

                    # print (result) 
                    pol_ids = []
                    if result:
                        fields_without_id = tuple(key for key in result[0] if key not in['id','sync_id_api'])
                        fields = fields_without_id + ('id',)
                        values = ''
                        print (fields)

                        for row in result:

                            if row['id'] > 0:
                                pol_ids.append(row['id'])


                            if values:
                                values += ', '
                                values += ', '

                            value = ''
                            for key in fields:
                                if value:
                                    value += ', '
                                else:
                                    value = '('

                                if key == 'id' and row[key] == 0:
                                    value += 'DEFAULT'
                                    continue 
                              
                                if type(row[key]) in [str, bytes]:
                                    string = row[key]
                                    value += "'" + string.replace("'", "''") + "'"
                                    continue
                                if isinstance(row[key], str):
                                
                                    value += "'" + row[key] + "'"
                                    #raise UserError(value)
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

                                #print (value)
                                value += _json(row[key])
                            value += ')'
                            values += value
                        
                        excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                        columns = remove_unicode(str(fields)).replace("'", "")
                        columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                        print (values)
                        if not values:
                            print ("No data available")


                        # insert replace existing data 
                        query = """
                            INSERT INTO purchase_order_line %s VALUES %s 
                            ON CONFLICT (id) DO UPDATE SET %s = %s
                        """ % (columns, values, columns_without_id, excluded)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()



                        if pol_ids:
                            pol_ids.append(0)
                            # delete from pol_rel
                            query = """
                                delete from account_tax_purchase_order_line_rel 
                                where purchase_order_line_id in (
                                    select id from purchase_order_line
                                    where id in {pol_ids}
                                    and sync_type = '{sync_type}'
                                )
                            """.format(sync_type=sync_type, pol_ids=tuple(pol_ids))
                            print (query)
                            #raise UserError(query)
                            cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                            cursor.execute(query)
                            conn_local.commit()



                        # truncate consol data
                        query = """
                            DELETE FROM odoo10_purchase_order_line 
                            WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)



                # select from odoo16
                query = """
                    SELECT a.id purchase_order_line_id, b.account_tax_id tax_id
                FROM purchase_order_line a 
                inner join account_tax_purchase_order_line_rel b on b.purchase_order_line_id = a.id
                inner join purchase_order po on po.id = a.order_id
                WHERE coalesce(a.sync_type,'{sync_type}') = '{sync_type}'
                    AND po.name ='{po_name}'                
                """.format(sync_type=sync_type,po_name=rec.name)
                #cursor = conn_consol.cursor()
                #cursor.execute(query)
                result = db_read(conn_consol, query)

                if result:
                    for row in result:
                        # insert replace existing data 
                        query = """
                            INSERT INTO account_tax_purchase_order_line_rel (
                                purchase_order_line_id, account_tax_id)
                            SELECT a.id, b.id 
                            FROM purchase_order_line a
                            inner join account_tax b on b.sync_consol_id_main={tax_id} and a.sync_type=b.sync_type
                            where a.sync_type='{sync_type}'
                            and a.sync_consol_id_main = {purchase_order_line_id}
                        """ . format(sync_type=sync_type, purchase_order_line_id=row['purchase_order_line_id'], tax_id=row['tax_id'])
                        print (query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()


                # select from odoo16
                query  = """
                    SELECT 
                    tpol.po_line_id
                    from tampung_purchase_order_line tpol
                    left join purchase_order po on po.id = tpol.po_id
                    where po.name ='{po_name}' and tpol.sync_type='{sync_type}'
                    
                """.format(sync_type=sync_type,po_name=rec.name)
                #cursor = conn_consol.cursor()
                #cursor.execute(query)
                result = db_read(conn_consol, query)

                #result = cursor.fetchall() 
                #raise UserError(_(str(result)))
                    

                if result:
                    for row in result:
                        # insert replace existing data 
                        query = """
                            delete from purchase_order_line where sync_consol_id_main = '{po_line_id}' and sync_type ='{sync_type}'
                        """ . format(sync_type=sync_type, po_line_id=row['po_line_id'])
                        print (query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()







        if self.type =='pr':
            for rec in self.pr_ids:



                # delete odoo10_product_uom
                query = """
                DELETE FROM odoo10_uom_uom 
                WHERE sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(query)



                # select from odoo16
                query = """
                        SELECT 
                            a.id, a.wipro_block, a.create_uid, a.sync_date, a.sync_consol_date, 
                            a.sync_consol_id_main, a.sync_consol_id_unit, a.rounding, 
                            a.write_uid, a.write_date, a.factor, a.active, a.create_date, 
                            a.category_id, a.sync_id, a.name, a.sync_id_api, 
                            a.uom_type, a.code, coalesce(a.sync_type,'{sync_type}') sync_type
                            FROM uom_uom a
                            left join purchase_requisition_line prl on prl.product_uom_id = a.id
                            left join purchase_requisition pr on pr.id = prl.requisition_id
                            WHERE coalesce(a.sync_type,'{sync_type}') = '{sync_type}'
                            and pr.name ='{pr_name}'
                """.format(sync_type=sync_type,pr_name=rec.name)
                #cursor = conn_consol.cursor()
                #cursor.execute(query)
                result = db_read(conn_consol, query)

                if result:

                    fields_without_id = tuple(key for key in result[0] if key not in['id','sync_type'])
                    fields = tuple(key for key in result[0] if key)
                    values = ''
                    print (fields)
                            
                    for row in result:
                        if values:
                            values += ', '

                        value = ''
                        for key in fields:
                            if value:
                                value += ', '
                            else:
                                value = '('
                            #raise UserError(_(type(row[key])))
                            if type(row[key]) in [str, bytes]:
                                string = row[key]
                                #raise UserError(row[key])
                                value += "'" + string.replace("'", "''") + "'"
                                continue
                            if isinstance(row[key], str):
                                
                                value += "'" + row[key] + "'"
                                #raise UserError(value)
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

                            value += _json(row[key])
                        value += ')'
                        values += value
                    
                    excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                    columns = remove_unicode(str(fields)).replace("'", "")
                    columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                    print (values)
                    if not values:
                        print ("No data available")


                    # insert replace existing data 
                    query = """
                        INSERT INTO odoo10_uom_uom %s VALUES %s 
                        ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
                    """ % (columns, values, columns_without_id, excluded)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_uom_uom as a SET company_id = b.id
                        FROM res_company b WHERE b.sync_type = a.sync_type;
                    """
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_uom_uom SET 
                        create_uid=3, write_uid=3, 
                        sync_date=CURRENT_TIMESTAMP, 
                        sync_consol_date=CURRENT_TIMESTAMP
                        WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)

                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_uom_uom SET sync_consol_id_main = id 
                        WHERE coalesce(sync_consol_id_main, 0) = 0
                        --AND coalesce(sync_consol_id_main,0) = 0
                        AND sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # fetch data for update 
                    query = """
                        SELECT DISTINCT
                        coalesce(b.id,0) id, 
                        a.wipro_block, a.create_uid, a.sync_date, a.sync_consol_date, 
                        a.sync_consol_id_main, a.sync_consol_id_unit, a.rounding, 
                        a.write_uid, a.write_date, a.factor, a.active, a.create_date, 
                        a.category_id, a.sync_id, a.name, a.sync_id_api, 
                        a.uom_type, a.code, a.sync_type
                        FROM odoo10_uom_uom a 
                        LEFT JOIN LATERAL (
                            SELECT * FROM uom_uom b 
                            WHERE b.sync_type=a.sync_type 
                            AND b.sync_consol_id_main=a.sync_consol_id_main
                            ORDER BY id ASC LIMIT 1
                        ) b on 1=1
                        WHERE 0=0
                            --AND coalesce(a.sync_consol_id_main,0) = 0
                            AND a.sync_type = '{sync_type}' 
 
                    """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    result = db_read(conn_local, query)
                    #raise UserError(_(str(result)))

                    # print (result) 

                    if result:
                        fields_without_id = tuple(key for key in result[0] if key not in['id'])
                        fields = fields_without_id + ('id',)
                        values = ''
                        print (fields)

                        for row in result:
                            if values:
                                values += ', '

                            value = ''
                            for key in fields:
                                if value:
                                    value += ', '
                                else:
                                    value = '('

                                if key == 'id' and row[key] == 0:
                                    value += 'DEFAULT'
                                    continue 
                              
                                if type(row[key]) in [str, bytes]:
                                    string = row[key]
                                    value += "'" + string.replace("'", "''") + "'"
                                    continue
                                if isinstance(row[key], str):
                                
                                    value += "'" + row[key] + "'"
                                    #raise UserError(value)
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

                                #print (value)
                                value += _json(row[key])
                            value += ')'
                            values += value
                        
                        excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                        columns = remove_unicode(str(fields)).replace("'", "")
                        columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                        print (values)
                        if not values:
                            print ("No data available")


                        # insert replace existing data 
                        query = """
                            INSERT INTO uom_uom %s VALUES %s 
                            ON CONFLICT (id) DO UPDATE SET %s = %s
                        """ % (columns, values, columns_without_id, excluded)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        


                        # truncate consol data
                        query = """
                            DELETE FROM odoo10_uom_uom 
                            WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()




                # delete odoo10_product_category
                query = """
                DELETE FROM odoo10_product_category 
                WHERE sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(query)



                # select from odoo16
                query = """

                        SELECT 
                            a.id, a.parent_left, a.parent_right, a.create_uid, a.stock_output_id, 
                            a.income_account_id, a.wipro_block, a.sync_consol_id_main, a.sync_consol_id_unit, 
                            a.sync_consol_date, a.write_uid, a.parent_id, a.write_date, a.create_date, 
                            a.removal_strategy_id, a.parent_sync_id, a.sync_id, a.sync_is_service, 
                            a.sync_date, a.company_id, a.stock_valuation_id, a.stock_input_id, 
                            a.active, a.stock_journal_id, a.expense_account_id, a.property_account_accrual_id, 
                            a.name, a.sync_id_api, a.lob_los, a.code, a.type, 
                            coalesce(a.sync_type,'{sync_type}') sync_type
                            FROM product_category a 
                            left join product_template pt on pt.categ_id = a.id
                            left join product_product pp on pp.product_tmpl_id = pt.id
                            left join purchase_requisition_line prl on prl.product_id = pp.id
                            left join purchase_requisition pr on pr.id = prl.requisition_id
                            WHERE coalesce(a.sync_type,'{sync_type}') = '{sync_type}'
                            and pr.name ='{pr_name}'
                """.format(sync_type=sync_type,pr_name=rec.name)
                #cursor = conn_consol.cursor()
                #cursor.execute(query)
                result = db_read(conn_consol, query)

                if result:

                    fields_without_id = tuple(key for key in result[0] if key not in['id','sync_type'])
                    fields = tuple(key for key in result[0] if key)
                    values = ''
                    print (fields)
                            
                    for row in result:
                        if values:
                            values += ', '

                        value = ''
                        for key in fields:
                            if value:
                                value += ', '
                            else:
                                value = '('
                            #raise UserError(_(type(row[key])))
                            if type(row[key]) in [str, bytes]:
                                string = row[key]
                                #raise UserError(row[key])
                                value += "'" + string.replace("'", "''") + "'"
                                continue
                            if isinstance(row[key], str):
                                
                                value += "'" + row[key] + "'"
                                #raise UserError(value)
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

                            value += _json(row[key])
                        value += ')'
                        values += value
                    
                    excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                    columns = remove_unicode(str(fields)).replace("'", "")
                    columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                    print (values)
                    if not values:
                        print ("No data available")


                    # insert replace existing data 
                    query = """
                        INSERT INTO odoo10_product_category %s VALUES %s 
                        ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
                    """ % (columns, values, columns_without_id, excluded)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_product_category as a SET company_id = b.id
                        FROM res_company b WHERE b.sync_type = a.sync_type;
                    """
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_product_category SET
                        parent_left=NULL, parent_right=NULL, create_uid=3, write_uid=3, 
                        removal_strategy_id=NULL, parent_sync_id=NULL, 
                        --property_account_accrual_id=NULL, stock_valuation_id=NULL, 
                        --stock_input_id=NULL, stock_output_id=NULL, income_account_id=NULL, 
                        --stock_journal_id=NULL, expense_account_id=NULL, 
                        sync_date=CURRENT_TIMESTAMP, 
                        sync_consol_date=CURRENT_TIMESTAMP
                           WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)

                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_product_category SET sync_consol_id_main = id 
                        WHERE coalesce(sync_consol_id_main, 0) = 0
                        --AND coalesce(sync_consol_id_main,0) = 0
                        AND sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # fetch data for update 
                    query = """
                        SELECT DISTINCT
                            coalesce(b.id,0) id, 
                            a.parent_left, a.parent_right, a.create_uid, 
                            a.wipro_block, a.sync_consol_id_main, a.sync_consol_id_unit, 
                            a.sync_consol_date, a.write_uid, c.id parent_id, a.write_date, a.create_date, 
                            a.removal_strategy_id, a.parent_sync_id, a.sync_id, a.sync_is_service, 
                            a.sync_date, a.company_id, 
                            --a.stock_valuation_id, a.stock_input_id, a.stock_output_id, a.income_account_id,
                            --a.stock_journal_id, a.expense_account_id, a.property_account_accrual_id, 
                            a.active, a.name, a.sync_id_api, a.lob_los, a.code, a.type, a.sync_type
                        FROM odoo10_product_category a 
                        LEFT JOIN LATERAL (
                            SELECT * FROM product_category b 
                            WHERE b.sync_type=a.sync_type 
                            AND b.sync_consol_id_main=a.sync_consol_id_main
                            ORDER BY id ASC LIMIT 1
                        ) b on 1=1
                        LEFT JOIN LATERAL (
                            SELECT * FROM product_category c 
                            WHERE c.sync_type=a.sync_type
                            AND c.sync_consol_id_main=a.parent_id
                            ORDER BY id ASC LIMIT 1 
                        ) c on 1=1
                        WHERE 0=0
                            -- AND coalesce(a.sync_consol_id_main,0) = 0
                            AND a.sync_type = '{sync_type}' 
 
                    """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    result = db_read(conn_local, query)
                    #raise UserError(_(str(result)))

                    # print (result) 

                    if result:
                        fields_without_id = tuple(key for key in result[0] if key not in['id'])
                        fields = fields_without_id + ('id',)
                        values = ''
                        print (fields)

                        for row in result:
                            if values:
                                values += ', '

                            value = ''
                            for key in fields:
                                if value:
                                    value += ', '
                                else:
                                    value = '('

                                if key == 'id' and row[key] == 0:
                                    value += 'DEFAULT'
                                    continue 
                              
                                if type(row[key]) in [str, bytes]:
                                    string = row[key]
                                    value += "'" + string.replace("'", "''") + "'"
                                    continue
                                if isinstance(row[key], str):
                                
                                    value += "'" + row[key] + "'"
                                    #raise UserError(value)
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

                                #print (value)
                                value += _json(row[key])
                            value += ')'
                            values += value
                        
                        excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                        columns = remove_unicode(str(fields)).replace("'", "")
                        columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                        print (values)
                        if not values:
                            print ("No data available")


                        # insert replace existing data 
                        query = """
                            INSERT INTO product_category %s VALUES %s 
                            ON CONFLICT (id) DO UPDATE SET %s = %s
                        """ % (columns, values, columns_without_id, excluded)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        


                        # truncate consol data
                        query = """
                            DELETE FROM odoo10_product_category 
                            WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()






                # delete odoo10_product_template
                query = """
                DELETE FROM odoo10_product_template 
                WHERE sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(query)



                # select from odoo16
                query = """
                    SELECT 
                        a.id, a.write_date, a.warranty, a.list_price, a.weight, a.sequence, a.color, 
                        a.write_uid, a.uom_id, a.active, a.categ_id, a.rental, a.location_id, 
                        a.warehouse_id, a.sale_delay, a.produce_delay, a.sync_id, a.sync_date, 
                        a.wipro_block, a.api_post_timestamp, a.base_price_manual, 
                        a.base_price_manual_active, a.uom2_id, a.conversion_rate, 
                        a.sync_is_service, a.sync_max_days, a.base_price, a.strength, 
                        a.sync_is_package, a.sync_categ_id, a.consignment, 
                        a.sync_consol_date, 
                        a.sync_consol_id_unit, a.sync_consol_id_main, a.antibiotic, 
                        a.narcotic, a.psychotropic, a.generic, a.create_date, 
                        a.create_uid, a.sale_ok, a.purchase_ok, a.message_last_post, 
                        a.company_id, a.uom_po_id, a.volume, a.description_purchase, 
                        a.default_code, a.pharmacalogy, a.mims_type, 
                        a.catalog_code, a.api_post_payload, a.api_post_key, 
                        a.api_post_url, a.description_sale, a.description, 
                        a.api_post_response, a.api_post_status, a.manufacturer_code, 
                        a.sync_id_api, a.name, a.mims_ref, a.detailed_type, a.sale_line_warn, 
                        a.sale_line_warn_msg, a.track_service, a.invoice_policy, 
                        a.expense_policy, a.tracking, a.manufacturer, a.description_picking, 
                        a.shelf, a.brand, a.loblos, a.purchase_line_warn_msg, 
                        a.purchase_method, a.purchase_line_warn, a.purchase_requisition, 
                        coalesce(a.sync_type,'{sync_type}') sync_type
                    FROM product_template a 
                    left join product_product pp on pp.product_tmpl_id =a.id
                    left join purchase_requisition_line prl on prl.product_id =pp.id 
                    left join purchase_requisition pr on pr.id = prl.requisition_id
                    WHERE coalesce(a.sync_type,'{sync_type}') = '{sync_type}'
                        AND pr.name='{pr_name}'
                """.format(sync_type=sync_type,pr_name=rec.name)
                #cursor = conn_consol.cursor()
                #cursor.execute(query)
                result = db_read(conn_consol, query)

                if result:

                    fields_without_id = tuple(key for key in result[0] if key not in['id','sync_type'])
                    fields = tuple(key for key in result[0] if key)
                    values = ''
                    print (fields)
                            
                    for row in result:
                        if values:
                            values += ', '

                        value = ''
                        for key in fields:
                            if value:
                                value += ', '
                            else:
                                value = '('
                            #raise UserError(_(type(row[key])))
                            if type(row[key]) in [str, bytes]:
                                string = row[key]
                                #raise UserError(row[key])
                                value += "'" + string.replace("'", "''") + "'"
                                continue
                            if isinstance(row[key], str):
                                
                                value += "'" + row[key] + "'"
                                #raise UserError(value)
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

                            value += _json(row[key])
                        value += ')'
                        values += value
                    
                    excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                    columns = remove_unicode(str(fields)).replace("'", "")
                    columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                    print (values)
                    if not values:
                        print ("No data available")


                    # insert replace existing data 
                    query = """
                        INSERT INTO odoo10_product_template %s VALUES %s 
                        ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
                    """ % (columns, values, columns_without_id, excluded)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)



                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_product_template as a SET company_id = b.id
                        FROM res_company b WHERE b.sync_type = a.sync_type;
                    """
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_product_template SET
                        create_uid=3, write_uid=3, warranty=NULL, list_price=NULL, weight=NULL, 
                        "sequence"=NULL, color=NULL, description_purchase=NULL, message_last_post=NULL,
                        description_sale=NULL, description=NULL, volume=NULL, rental=NULL, 
                        sale_line_warn='no-message', sale_line_warn_msg=NULL, sale_delay=NULL,
                        purchase_line_warn_msg=NULL, sync_date=CURRENT_TIMESTAMP, 
                        sync_consol_date=CURRENT_TIMESTAMP
                        WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)

                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_product_template SET sync_consol_id_main = id 
                        WHERE coalesce(sync_consol_id_main, 0) = 0
                        --AND coalesce(sync_consol_id_main,0) = 0
                        AND sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_product_template SET default_code = '[NULL]'
                        WHERE default_code IS NULL
                            AND sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)



                    # fetch data for update 
                    query = """
                        SELECT DISTINCT
                            coalesce(b.id,0) id, 
                            a.write_date, a.warranty, a.list_price, a.weight, a.sequence, a.color, 
                            a.write_uid, coalesce(uom.id,1) as uom_id, a.active, coalesce(c.id,10) as categ_id, a.rental, 
                            a.location_id, a.warehouse_id, a.sale_delay, a.produce_delay, a.sync_id, 
                            a.sync_date, a.wipro_block, a.api_post_timestamp, a.base_price_manual, 
                            a.base_price_manual_active, uom_po.id uom2_id, a.conversion_rate, 
                            a.sync_is_service, a.sync_max_days, a.base_price, a.strength, 
                            a.sync_is_package, a.sync_categ_id, a.consignment, a.sync_consol_date, 
                            a.sync_consol_id_unit, a.sync_consol_id_main, a.antibiotic, 
                            a.narcotic, a.psychotropic, a.generic, a.create_date, 
                            a.create_uid, a.sale_ok, a.purchase_ok, a.message_last_post, 
                            a.company_id, coalesce(uom_po.id,1) uom_po_id, a.volume, a.description_purchase, 
                            a.default_code, a.pharmacalogy, a.mims_type, 
                            a.catalog_code, a.api_post_payload, a.api_post_key, 
                            a.api_post_url, a.description_sale, a.description, 
                            a.api_post_response, a.api_post_status, a.manufacturer_code, 
                            a.sync_id_api, a.name, a.mims_ref, a.detailed_type, a.sale_line_warn, 
                            a.sale_line_warn_msg, a.track_service, a.invoice_policy,
                            a.expense_policy, a.tracking, a.manufacturer, a.description_picking, 
                            a.shelf, a.brand, a.loblos, a.purchase_line_warn_msg, 
                            a.purchase_method, a.purchase_line_warn, a.purchase_requisition, a.sync_type
                        FROM odoo10_product_template a 
                        LEFT JOIN LATERAL (
                            SELECT * FROM product_template b 
                            WHERE b.sync_type=a.sync_type 
                            AND b.sync_consol_id_main=a.sync_consol_id_main
                            ORDER BY id ASC LIMIT 1 
                        ) b on 1=1
                        LEFT JOIN lateral (
                            select * from product_category c 
                            where c.sync_type=a.sync_type 
                            AND c.sync_consol_id_main=a.categ_id
                            order by id asc limit 1
                        ) c on 1=1
                        LEFT JOIN lateral (
                            select * from uom_uom uom 
                            where uom.sync_type=a.sync_type 
                            AND uom.sync_consol_id_main=a.uom_id
                            order by id asc limit 1
                        ) uom on 1=1
                        LEFT JOIN lateral (
                            select * from uom_uom uom2 
                            where uom2.sync_type=a.sync_type 
                            AND uom2.sync_consol_id_main=a.uom2_id
                            order by id asc limit 1
                        ) uom2 on 1=1
                        LEFT JOIN lateral (
                            select * from uom_uom uom_po
                            where uom_po.sync_type=a.sync_type 
                            AND uom_po.sync_consol_id_main=a.uom_po_id
                            order by id asc limit 1
                        ) uom_po on 1=1
                        WHERE 0=0
                            --AND coalesce(a.sync_consol_id_main,0) = 0
                            AND a.sync_type = '{sync_type}' 
                    """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    result = db_read(conn_local, query)
                    #raise UserError(_(str(result)))

                    # print (result) 

                    if result:
                        fields_without_id = tuple(key for key in result[0] if key not in['id'])
                        fields = fields_without_id + ('id',)
                        values = ''
                        print (fields)

                        for row in result:
                            if values:
                                values += ', '

                            value = ''
                            for key in fields:
                                if value:
                                    value += ', '
                                else:
                                    value = '('

                                if key == 'id' and row[key] == 0:
                                    value += 'DEFAULT'
                                    continue 
                              
                                if type(row[key]) in [str, bytes]:
                                    string = row[key]
                                    value += "'" + string.replace("'", "''") + "'"
                                    continue
                                if isinstance(row[key], str):
                                
                                    value += "'" + row[key] + "'"
                                    #raise UserError(value)
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

                                #print (value)
                                value += _json(row[key])
                            value += ')'
                            values += value
                        
                        excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                        columns = remove_unicode(str(fields)).replace("'", "")
                        columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                        print (values)
                        if not values:
                            print ("No data available")


                        # insert replace existing data 
                        query = """
                            INSERT INTO product_template %s VALUES %s 
                            ON CONFLICT (id) DO UPDATE SET %s = %s
                        """ % (columns, values, columns_without_id, excluded)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()
                        

                        # insert replace existing data 
                        query = """
                            UPDATE product_product AS pp SET 
                                default_code = pt.default_code, 
                                write_date = pt.write_date
                            FROM product_template pt 
                            WHERE pt.id = pp.product_tmpl_id 
                            AND pt.sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()



                        # insert replace existing data 
                        query = """
                            INSERT INTO product_product(
                                product_tmpl_id, default_code, create_uid, 
                                create_date, write_uid, write_date)
                            SELECT 
                                pt.id product_tmpl_id, 
                                coalesce(pt.default_code,'[NULL]') default_code,
                                pt.create_uid, pt.create_date, 
                                pt.write_uid, pt.write_date
                            FROM product_template pt 
                            WHERE NOT EXISTS(
                                SELECT 1 FROM product_product t 
                                WHERE t.product_tmpl_id = pt."id"
                            ) AND pt.sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()



                        # truncate consol data
                        query = """
                            DELETE FROM odoo10_product_template 
                            WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)





                # delete odoo10_purchase_requisition
                query = """
                DELETE FROM odoo10_purchase_requisition 
                WHERE sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(query)
                



                # select from odoo16
                query = """
                    SELECT 
                        a.id, a.origin, a.revisi_sequence, 
                        a.picking_type_id, a.reject_reason, a.approve_next_store, 
                        a.sync_consol_date, a.sync_consol_id_main, a.sync_consol_id_unit, 
                        a.create_date, a.write_uid, 
                        a.type_pr, a.item_type, a.ordering_date, a.approval_date,
                        a.create_uid, 
                        a.user_id,
                        12 currency_id,
                        a.reject_state,
                        --a.message_last_post, 
                        a.company_id,  
                        a.write_date, a.approve_rule_id,
                        a.name, a.state, 
                        a.approve_status, a.revisi, a.is_user_it, a.pr_it_type,
                        coalesce(a.sync_type,'{sync_type}') sync_type
                    FROM purchase_requisition a 
                    WHERE coalesce(a.sync_type,'{sync_type}') = '{sync_type}'
                        AND a.name ='{pr_name}'
                """.format(sync_type=sync_type,pr_name=rec.name)
                #cursor = conn_consol.cursor()
                #cursor.execute(query)
                result = db_read(conn_consol, query)

                #result = cursor.fetchall() 
                #raise UserError(_(str(result)))
                    

                if result:

                    fields_without_id = tuple(key for key in result[0] if key not in['id','sync_type'])
                    fields = tuple(key for key in result[0] if key)
                    values = ''
                    print (fields)
                            
                    for row in result:
                        if values:
                            values += ', '

                        value = ''
                        for key in fields:
                            if value:
                                value += ', '
                            else:
                                value = '('
                            #raise UserError(_(type(row[key])))
                            if type(row[key]) in [str, bytes]:
                                string = row[key]
                                #raise UserError(row[key])
                                value += "'" + string.replace("'", "''") + "'"
                                continue
                            if isinstance(row[key], str):
                                
                                value += "'" + row[key] + "'"
                                #raise UserError(value)
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

                            value += _json(row[key])
                        value += ')'
                        values += value
                    
                    excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                    columns = remove_unicode(str(fields)).replace("'", "")
                    columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                    print (values)
                    if not values:
                        print ("No data available")


                    # insert replace existing data 
                    query = """
                        INSERT INTO odoo10_purchase_requisition %s VALUES %s 
                        ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
                    """ % (columns, values, columns_without_id, excluded)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_purchase_requisition as a SET company_id = b.id
                        FROM res_company b WHERE b.sync_type = a.sync_type;
                    """
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_purchase_requisition SET 
                        create_uid=3, write_uid=3, 
                        sync_consol_date=CURRENT_TIMESTAMP
                        WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)

                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_purchase_requisition SET sync_consol_id_main = id 
                        WHERE coalesce(sync_consol_id_main, 0) = 0
                        --AND coalesce(sync_consol_id_main,0) = 0
                        AND sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # fetch data for update 
                    query = """
                        SELECT DISTINCT
                            coalesce(b.id,0) id, 
                            a.origin, a.revisi_sequence, spt.id as picking_type_id,
                            a.reject_reason, a.approve_next_store, a.sync_consol_date, a.sync_consol_id_main, a.sync_consol_id_unit,
                            a.create_date, a.write_uid,
                            a.type_pr, a.item_type, a.ordering_date, a.approval_date,
                            a.create_uid,
                            a.company_id,  
                            a.write_date, 
                            e.id approve_rule_id,
                            '1' type_id,
                            f.id user_id,
                            12 currency_id,
                            a.reject_state,
                            a.name, a.state, 
                            a.approve_status, a.revisi, a.is_user_it, a.pr_it_type,
                            a.sync_type
                        FROM odoo10_purchase_requisition a 
                        LEFT JOIN lateral (
                            select * from purchase_requisition b 
                            where b.sync_type=a.sync_type 
                            AND (b.sync_consol_id_main=a.sync_consol_id_main) -- or b.sync_id_api=a.sync_id_api)
                            order by id asc limit 1
                        ) b on 1=1

                        LEFT JOIN lateral (
                            select * from purchase_approval_rule e
                            where e.sync_consol_id_main=a.approve_rule_id
                            order by id asc limit 1
                        ) e on 1=1

                        LEFT JOIN lateral (
                            select * from res_users f
                            where f.sync_consol_id_main=a.user_id
                            order by id asc limit 1
                        ) f on 1=1


                        LEFT JOIN lateral (
                            select * from stock_picking_type spt 
                            where spt.sync_type=a.sync_type 
                            AND spt.sync_consol_id_main=a.picking_type_id
                            order by id asc limit 1 
                        ) spt on 1=1
                        --WHERE coalesce(a.sync_consol_id_main,0) = 0
                            AND a.sync_type = '{sync_type}' 
 
                    """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    result = db_read(conn_local, query)
                    #raise UserError(_(str(result)))

                    # print (result) 

                    if result:
                        fields_without_id = tuple(key for key in result[0] if key not in['id'])
                        fields = fields_without_id + ('id',)
                        values = ''
                        print (fields)

                        for row in result:
                            if values:
                                values += ', '

                            value = ''
                            for key in fields:
                                if value:
                                    value += ', '
                                else:
                                    value = '('

                                if key == 'id' and row[key] == 0:
                                    value += 'DEFAULT'
                                    continue 
                              
                                if type(row[key]) in [str, bytes]:
                                    string = row[key]
                                    value += "'" + string.replace("'", "''") + "'"
                                    continue
                                if isinstance(row[key], str):
                                
                                    value += "'" + row[key] + "'"
                                    #raise UserError(value)
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

                                #print (value)
                                value += _json(row[key])
                            value += ')'
                            values += value
                        
                        excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                        columns = remove_unicode(str(fields)).replace("'", "")
                        columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                        print (values)
                        if not values:
                            print ("No data available")


                        # insert replace existing data 
                        query = """
                            INSERT INTO purchase_requisition %s VALUES %s 
                            ON CONFLICT (id) DO UPDATE SET %s = %s
                        """ % (columns, values, columns_without_id, excluded)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        


                        # truncate consol data
                        query = """
                            DELETE FROM odoo10_purchase_requisition 
                            WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()



                # delete odoo10_purchase_requisition_line
                query = """
                DELETE FROM odoo10_purchase_requisition_line 
                WHERE sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(query)
                



                # select from odoo16
                query = """
                    SELECT 
                        a.id, 
                        pp.product_tmpl_id as product_id,
                        pr.id requisition_id,
                        --a.product_uom,
                        a.company_id, a.create_uid, a.write_uid,
                        a.schedule_date, a.product_qty, a.price_unit, a.create_date, a.write_date,
                        a.account_analytic_id, a.description,  a.state, a.product_char, a.request_date,
                        a.sync_consol_date, a.sync_consol_id_unit, a.sync_consol_id_main, a.price_subtotal,
                        a.historical_price,
                        coalesce(a.sync_type,'{sync_type}') sync_type
                    FROM purchase_requisition_line a 
                    INNER JOIN purchase_requisition pr ON pr.id = a.requisition_id
                    LEFT JOIN product_product pp ON pp.id = a.product_id

                    WHERE coalesce(a.sync_type,'{sync_type}') = '{sync_type}'
                        AND pr.name ='{pr_name}'
                """.format(sync_type=sync_type,pr_name=rec.name)
                #cursor = conn_consol.cursor()
                #cursor.execute(query)
                result = db_read(conn_consol, query)

                #result = cursor.fetchall() 
                #raise UserError(_(str(result)))
                    

                if result:

                    fields_without_id = tuple(key for key in result[0] if key not in['id','sync_type'])
                    fields = tuple(key for key in result[0] if key)
                    values = ''
                    print (fields)
                            
                    for row in result:
                        if values:
                            values += ', '

                        value = ''
                        for key in fields:
                            if value:
                                value += ', '
                            else:
                                value = '('
                            #raise UserError(_(type(row[key])))
                            if type(row[key]) in [str, bytes]:
                                string = row[key]
                                #raise UserError(row[key])
                                value += "'" + string.replace("'", "''") + "'"
                                continue
                            if isinstance(row[key], str):
                                
                                value += "'" + row[key] + "'"
                                #raise UserError(value)
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

                            value += _json(row[key])
                        value += ')'
                        values += value
                    
                    excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                    columns = remove_unicode(str(fields)).replace("'", "")
                    columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                    print (values)
                    if not values:
                        print ("No data available")


                    # insert replace existing data 
                    query = """
                        INSERT INTO odoo10_purchase_requisition_line %s VALUES %s 
                        ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
                    """ % (columns, values, columns_without_id, excluded)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_purchase_requisition_line as a SET company_id = b.id
                        FROM res_company b WHERE b.sync_type = a.sync_type;
                    """
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_purchase_requisition_line SET 
                        create_uid=3, write_uid=3, 
                        sync_consol_date=CURRENT_TIMESTAMP
                        WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)

                    # insert replace existing data 
                    query = """
                        UPDATE odoo10_purchase_requisition_line SET sync_consol_id_main = id 
                        WHERE coalesce(sync_consol_id_main, 0) = 0
                        --AND coalesce(sync_consol_id_main,0) = 0
                        AND sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(query)


                    # fetch data for update 
                    query = """
                        SELECT DISTINCT
                            coalesce(b.id,0) id, 
                            pp.id as product_id,
                            pr.id as requisition_id,
                           -- f.id product_uom,
                            a.company_id, a.create_uid, a.write_uid,
                            a.schedule_date, a.product_qty, a.price_unit, a.create_date, a.write_date,
                            aac.id account_analytic_id, a.description,  a.state, a.product_char, a.request_date,
                            a.sync_consol_date, a.sync_consol_id_unit, a.sync_consol_id_main, a.price_subtotal,
                            a.historical_price,                
                            a.sync_type
                        FROM odoo10_purchase_requisition_line a 
                        LEFT JOIN lateral (
                            select * from purchase_requisition_line b 
                            where b.sync_type=a.sync_type 
                            AND (b.sync_consol_id_main=a.sync_consol_id_main) -- or b.sync_id_api=a.sync_id_api)
                            order by id asc limit 1
                        ) b on 1=1

                        LEFT JOIN lateral (
                            select * from product_template c
                            where c.sync_type=a.sync_type 
                            AND c.sync_consol_id_main=a.product_id
                            order by id asc limit 1
                        ) c on 1=1
                        LEFT JOIN lateral (
                            select * from product_product pp
                            where pp.product_tmpl_id=c.id
                            order by id asc limit 1
                        ) pp on 1=1

                        LEFT JOIN lateral (
                            select * from purchase_requisition pr
                            where pr.sync_type=a.sync_type
                            AND pr.sync_consol_id_main=a.requisition_id
                            order by id asc limit 1
                        ) pr on 1=1


                        --LEFT JOIN lateral (
                        --    select * from product_uom f
                        --    where f.sync_consol_id_main=a.user_id
                        --    AND f.sync_type = a.sync_type
                        --    order by id asc limit 1
                        --) f on 1=1


                        LEFT JOIN lateral (
                            select * from account_analytic_account aac 
                            where aac.sync_type=a.sync_type 
                            AND aac.sync_consol_id_main=a.account_analytic_id
                            order by id asc limit 1 
                        ) aac on 1=1
                        --WHERE coalesce(a.sync_consol_id_main,0) = 0
                            AND a.sync_type = '{sync_type}'
                    """.format(sync_type=sync_type)
                    print (query)
                    #raise UserError(query)
                    result = db_read(conn_local, query)
                    #raise UserError(_(str(result)))

                    # print (result) 

                    if result:
                        fields_without_id = tuple(key for key in result[0] if key not in['id'])
                        fields = fields_without_id + ('id',)
                        values = ''
                        print (fields)

                        for row in result:
                            if values:
                                values += ', '

                            value = ''
                            for key in fields:
                                if value:
                                    value += ', '
                                else:
                                    value = '('

                                if key == 'id' and row[key] == 0:
                                    value += 'DEFAULT'
                                    continue 
                              
                                if type(row[key]) in [str, bytes]:
                                    string = row[key]
                                    value += "'" + string.replace("'", "''") + "'"
                                    continue
                                if isinstance(row[key], str):
                                
                                    value += "'" + row[key] + "'"
                                    #raise UserError(value)
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

                                #print (value)
                                value += _json(row[key])
                            value += ')'
                            values += value
                        
                        excluded = remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                        columns = remove_unicode(str(fields)).replace("'", "")
                        columns_without_id = remove_unicode(str(fields_without_id)).replace("'", "")

                        print (values)
                        if not values:
                            print ("No data available")


                        # insert replace existing data 
                        query = """
                            INSERT INTO purchase_requisition_line %s VALUES %s 
                            ON CONFLICT (id) DO UPDATE SET %s = %s
                        """ % (columns, values, columns_without_id, excluded)
                        print (query)
                        #raise UserError(query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()


                        # truncate consol data
                        query = """
                            DELETE FROM odoo10_purchase_requisition_line 
                            WHERE sync_type = '{sync_type}'
                        """.format(sync_type=sync_type)
                        print (query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                



                # select from odoo16
                query  = """
                    SELECT 
                    tprl.pr_line_id
                    from tampung_purchase_requisition_line tprl
                    left join purchase_requisition pr on pr.id = tprl.pr_id
                    where pr.name ='{pr_name}' and tprl.sync_type='{sync_type}'

                """.format(sync_type=sync_type,pr_name=rec.name)
                #cursor = conn_consol.cursor()
                #cursor.execute(query)
                result = db_read(conn_consol, query)

                #result = cursor.fetchall() 
                #raise UserError(_(str(result)))
                    

                if result:
                    for row in result:
                        # insert replace existing data 
                        query = """
                            delete from purchase_requisition_line where sync_consol_id_main = '{pr_line_id}' and sync_type ='{sync_type}'
                        """ . format(sync_type=sync_type, pr_line_id=row['pr_line_id'])
                        print (query)
                        cursor = conn_local.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(query)
                        conn_local.commit()



class PrSyncingLine(models.TransientModel):
    _name = 'pr.syncing.line'

    name = fields.Char(string="PR No.", readonly=False, index=True)
    syncing_pr_id = fields.Many2one('purchase.syncing.wizard', string="Syncing")

class PoSyncingLine(models.TransientModel):
    _name = 'po.syncing.line'

    name = fields.Char(string="PO No.", readonly=False, index=True)
    syncing_po_id = fields.Many2one('purchase.syncing.wizard', string="Syncing")




class PurchaseOrderValidationWizard(models.TransientModel):
    _name = 'purchase.order.validation.wizard'
    _description = 'Validate Purchase Order Wizard'

    purchase_id = fields.Many2one('purchase.order', string="Purchase Order", required=True)

    # @api.multi
    def confirm_validation(self):
        self.ensure_one()
        self.purchase_id.validate_modification()
        return {'type': 'ir.actions.act_window_close'}



class PurchaseNotificationSetting(models.Model):
    _name = 'purchase.notification.setting'

    sync_type = sync.type

    name = fields.Char(string="Name", required=True)
    user_ids = fields.Many2many('res.users',string="Responsible Purchasing")
    company_id = fields.Many2one('res.company',string='Company',required=True)
    pr_notif_internal = fields.Integer(string="PR Interval")
    po_notif_internal = fields.Integer(string="PO Interval")




        

    def crontab_send_email_pr(self):
        settings = self.sudo().search([])

        for setting in settings:
            if not setting.pr_notif_internal:
                raise UserError(_("Notification setting not found for company: %s") % setting.company_id.name)

            real_date = datetime.now() - timedelta(days=setting.pr_notif_internal)

            query = """
                SELECT id
                FROM purchase_requisition
                WHERE company_id = %s
                  AND state = 'draft'
                  AND (approve_status IS NULL OR approve_status = '')
                  AND coalesce(pending_request_date,create_date) < %s
                ORDER BY pending_request_date DESC
                LIMIT 50
            """

            self.env.cr.execute(query, (setting.company_id.id, real_date))
            requisition_ids = [row[0] for row in self.env.cr.fetchall()]

            requisitions = self.env['purchase.requisition'].browse(requisition_ids)
            requisitions.action_send_requisition_email()



    def crontab_send_email_pr_to_po(self):
        settings = self.sudo().search([])

        for setting in settings:
            if not setting.pr_notif_internal:
                raise UserError(_("Notification setting not found for company: %s") % setting.company_id.name)

            real_date = datetime.now() - timedelta(days=setting.pr_notif_internal)

            query = """
                SELECT id
                FROM purchase_requisition
                WHERE company_id = %s
                  AND state = 'in_progress'
                  and approve_next_store ='Completed'
                  AND coalesce(complete_request_date,create_date) < %s
                ORDER BY complete_request_date DESC
                LIMIT 50
            """

            self.env.cr.execute(query, (setting.company_id.id, real_date))
            requisition_ids = [row[0] for row in self.env.cr.fetchall()]

            requisitions = self.env['purchase.requisition'].browse(requisition_ids)
            requisitions.action_send_requisition_to_po_email()



    def crontab_send_email_rfq(self):
        settings = self.sudo().search([])

        for setting in settings:
            if not setting.po_notif_internal:
                raise UserError(_("Notification setting not found for company: %s") % setting.company_id.name)

            real_date = datetime.now() - timedelta(days=setting.po_notif_internal)

            query = """
                SELECT id
                FROM purchase_order
                WHERE company_id = %s
                  AND state = 'draft'
                  AND (approve_status IS NULL OR approve_status = '')
                  AND coalesce(pending_request_date,create_date) < %s
                ORDER BY pending_request_date DESC
                LIMIT 50
            """

            self.env.cr.execute(query, (setting.company_id.id, real_date))
            rfq_ids = [row[0] for row in self.env.cr.fetchall()]

            rfqs = self.env['purchase.order'].browse(rfq_ids)
            rfqs.action_send_rfq_email()



class PurchaseOrderLineWizard(models.TransientModel):
    _name = 'purchase.order.line.wizard'

    @api.model
    def _get_user_id(self):
        return self.env.user.id

    company_id = fields.Many2one('res.company', string="Company", required=False)
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)
    po_wizard_line = fields.One2many('sale.order.wizard.line','sale_wizard_id', string="Filter Line")
    user_id = fields.Many2one('res.users', string="User ID", default=_get_user_id)
    bulk_id = fields.Many2one('sale.order.bulk.filter', string="Saved Bulk Filter")
    

    @api.model
    def create(self,vals):
        if vals.get('bulk_id'):
            vals['po_wizard_line'] = ""
        res = super(PurchaseOrderLineWizard, self).create(vals)
        return res



    @api.onchange('bulk_id')
    def onchange_filter(self):
        for record in self:
            if record.bulk_id:
                record.po_wizard_line = record.bulk_id.filter_ids.ids

    # @api.multi
    def query_report(self, data_ids=False):
        for record in self:
            open('/opt/odoo16/logs/belajar.log','a+').write('\n' + 'Start')
            domain = ""

            line_all = []
            query_field = ""
            if not record.bulk_id:
                for line in record.po_wizard_line:
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
        query = self.query_report()
        action = {}
        action['target'] = 'current'
        # action['domain'] = "[('user_id', '=', %s)]" % (self.env.user.id)
        if query:
            if self.company_id:
                action['domain'] = "[{query}('date_planned', '>=', '{start_date}'), ('date_planned', '<=', '{end_date}'), ('company_id', '=', {company_id})]".format(query=query, start_date=self.start_date, end_date=self.end_date, company_id=self.company_id.id)
            else:
                action['domain'] = "[{query}('date_planned', '>=', '{start_date}'), ('date_planned', '<=', '{end_date}')]".format(query=query, start_date=self.start_date, end_date=self.end_date, company_id=self.company_id.id)
        else:
            if self.company_id:
                action['domain'] = "[('date_planned', '>=', '%s'), ('date_planned', '<=', '%s'), ('company_id', '=', %s)]" % (self.start_date, self.end_date, self.company_id.id)
            else:
                action['domain'] = "[('date_planned', '>=', '%s'), ('date_planned', '<=', '%s')]" % (self.start_date, self.end_date)
        open('/opt/odoo16/logs/belajar.log','a+').write('\n' + str(action['domain']) + '\n' + 'domain show report')
        action['type'] = 'ir.actions.act_window'
        action['view_mode'] = 'tree,form,pivot'
        action['view_type'] = 'form'
        action['res_model'] = 'purchase.order.line'
        action['name'] = 'Purchase Order Analysis Report'
        action['views'] = [(self.sudo().env.ref('mayapada.mayapada_purchase_order_line_inherited').id, 'tree'), (False, 'pivot'), (False, 'form')]
        return action



    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(PurchaseOrderLineWizard,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Purchase Order Analysis" delete="false">

                    <style>
                      .o_control_panel {
                          display: none;
                      }
                    </style>

                    <sheet>
                    <h1>
                        Purchase Order Analysis
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





class SrbTemporary(models.Model):
    _name = 'srb.temporary'

    sync_type = sync.type
    company_id = fields.Many2one('res.company',string='Company',required=True)
    consol_id_main_header = fields.Integer(string="Consol ID Main Header")
    consol_id_main_detail = fields.Integer(string="Consol ID Main Detail")
    srb_id = fields.Integer(string="SRB ID")
    srb_line_id = fields.Integer(string="SRB Line ID")
    srb_no = fields.Char(string="SRB No.")
    srb_date = fields.Date(string="SRB Date")
    srb_responsible = fields.Char(string="SRB Responsible")
    srb_ref_no = fields.Char(string="SRB Ref No.")
    srb_supplier = fields.Char(string="SRB Supplier")
    srb_po = fields.Char(string="SRB Po.")
    po_line_id = fields.Many2one('purchase.order.line',string='PO Line ID')
    product_id = fields.Many2one('product.product',string='Product')
    description = fields.Char(string="Description")
    line_qty_rcv = fields.Float(string="QTY Rcv")



class GrnTemporary(models.Model):
    _name = 'grn.temporary'

    sync_type = sync.type
    company_id = fields.Many2one('res.company',string='Company',required=True)
    consol_id_main_header = fields.Integer(string="Consol ID Main Header")
    consol_id_main_detail = fields.Integer(string="Consol ID Main Detail")
    picking_id = fields.Integer(string="Picking ID")
    picking_line_id = fields.Integer(string="Picking Line ID")
    picking_no = fields.Char(string="Picking No.")
    shipment_rcv_date = fields.Date(string="Shipment RCV Date")
    source_document = fields.Char(string="Source Document")
    grn_supplier = fields.Char(string="GRN Supplier")
    po_line_id = fields.Many2one('purchase.order.line',string='PO Line ID')
    product_id = fields.Many2one('product.product',string='Product')
    description = fields.Char(string="Description")
    line_qty_grn = fields.Float(string="QTY Rcv")

    