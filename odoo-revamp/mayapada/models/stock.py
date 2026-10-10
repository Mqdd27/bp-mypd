from collections import namedtuple, defaultdict

from . import sync
from . import misc
import logging
import calendar
import decimal
import requests
import pyodbc 
#import pandas as pd

from datetime import date as date_format, datetime, timedelta
from json import dumps, loads
# from json import loads
from odoo import models, fields, api, tools, exceptions, _
from odoo.http import request, serialize_exception, content_disposition
# from odoo.addons.web.controllers.main import serialize_exception, content_disposition
from odoo import fields, http, tools, exceptions
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo.exceptions import UserError
try:
    from multiprocess import Process, Manager
except:
    from threading import Thread as Process
# import odoo.addons.decimal_precision as dp
import json
from re import sub

class StockPicking(models.Model):
    _inherit = 'stock.picking'    

    def _create_lots_for_picking(self):
        super(StockPicking, self)._create_lots_for_picking()
        if self.picking_type_id.code == 'incoming':
          for pack_lot_id in self.mapped('pack_operation_ids').mapped('pack_lot_ids'):
              pack_lot_id.lot_id.write({'use_date': pack_lot_id.expired_date, 'life_date': pack_lot_id.expired_date, 'sync_type': self.company_id.sync_type, 'sync_id_api': str(pack_lot_id.lot_name) + ' / '+ str(pack_lot_id.id), 'name': str(pack_lot_id.lot_name) + ' / ' + str(pack_lot_id.id)})
    
    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    create_lots_for_picking = _create_lots_for_picking
    requestor_signature = fields.Binary(string="Requestor's Signature", readonly=True)
    picking_type_id = fields.Many2one('stock.picking.type', 'Picking Type', required=True, readonly=True, states={'draft': [('readonly', False)]})
    date_move = fields.Datetime(string="Rcv/Shipment Date", store=True)
    backordered = fields.Boolean(string="Backordered", default=False, readonly=True, copy=False)
    lot_number = fields.Char(string="Lot Number")
    expired_date = fields.Datetime(string="Expired Date")
    wipro_type = fields.Selection([('receiving', "Receiving")], string="Wipro Type")
    location_id = fields.Many2one(
        'stock.location', "Source Location",
        default=lambda self: self.env['stock.picking.type'].browse(self._context.get('default_picking_type_id')).default_location_src_id,
        readonly=True, required=True,
        states={'draft': [('readonly', False)]})
    location_dest_id = fields.Many2one(
        'stock.location', "Destination Location",
        default=lambda self: self.env['stock.picking.type'].browse(self._context.get('default_picking_type_id')).default_location_dest_id,
        readonly=True, required=True,
        states={'draft': [('readonly', False)]})
    
    api_post_timestamp = fields.Datetime(string="Timestamp API", readonly=True)
    api_post_status = fields.Selection([('done', 'Done'), ('failed', 'Failed')], string='Status API', readonly=True)
    api_post_payload = fields.Char(string="Payload API", readonly=True)
    api_post_response = fields.Char(string="Response API", readonly=True)
    api_post_url = fields.Char(string="URL", readonly=True)
    api_post_key = fields.Char(string="API Key", readonly=True)

    # 2021.09.09 - Flagging untuk compute stock.picking from PO, SO & SC
    move_id = fields.Many2one('account.move', string="Journal Entries", index=True)
    sales_id = fields.Many2one('sale.order', string="Sale Order", index=True) 
    po_id = fields.Many2one('purchase.order', string="Purchase Order", index=True) 
    po_number = fields.Char(string="PO Number", related="po_id.title")
    account_analytic_id = fields.Many2one('account.analytic.account', string="Account Analytic", domain=[('type_analytic', '=', 'expense')], index=True)
        
    purchase_line_ids = fields.One2many('purchase.order.line', 'picking_id', string="Purchase Receipt")
    sale_line_ids = fields.One2many('sale.order.line', 'picking_id', string="Item Sales")
    scrap_ids = fields.One2many('stock.scrap', 'picking_id', string="Scraps")
    
    # move_ids = fields.One2many('account.move', 'picking_id', string="Journals", readonly=True) 
    # move_line_ids = fields.One2many('account.move.line', 'picking_id', string='Journal Items', readonly=True)
    journal_ids = fields.One2many('account.move', 'stock_picking_id', string="Journals", readonly=True) 
    move_ids = fields.One2many('stock.move', 'picking_id', string="Stock Moves", copy=True)
    move_ids_without_package = fields.One2many(
        'stock.move', 'picking_id', string="Stock moves not in package", compute='_compute_move_without_package',
        inverse='_set_move_without_package', compute_sudo=True)

    move_line_ids = fields.One2many('stock.move.line', 'picking_id', 'Operations')
    move_line_ids_without_package = fields.One2many('stock.move.line', 'picking_id', 'Operations without package', domain=['|',('package_level_id', '=', False), ('picking_type_entire_packs', '=', False)])    
    asset_ids = fields.One2many('stock.picking.asset', 'picking_id', string="Asset Items")

    # tambahan from odoo
    recompute_pack_op = fields.Boolean(string="Recompute pack operation?", copy=False)
    pack_operation_exist = fields.Boolean(string="Has Pack Operations")
    min_date = fields.Datetime(string="Scheduled Date", states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    quant_reserved_exist = fields.Boolean(string="Has quants already reserved")
    move_lines = fields.One2many('stock.move', 'picking_id', string="Stock Moves", copy=True)
    launch_pack_operations = fields.Boolean("Launch Pack Operations", copy=False)
    # group_id = fields.Many2one('procurement.group', string="Procurement Group")

    ###########################Update
    receiving_id = fields.Many2one('stock.receiving', string="Receiving Bay")
    receiving_notes = fields.Many2one('stock.picking', string="Receiving Notes")
    is_return = fields.Boolean(string="Is Return?")

    invoice_count = fields.Integer(compute="_compute_invoice", string='# of Bills', copy=False, default=0)
    invoice_line_ids = fields.One2many('account.invoice.line', 'picking_id', string="Invoice Lines")
    invoice_ids = fields.Many2many('account.invoice', compute="_compute_invoice", string='Bills', copy=False)
    max_date = fields.Datetime(string="Max. Expected Date", store=True)
    # expired_date = fields.Datetime(string="Max. Expected Date", store=True)
    # message_last_post = fields.Datetime(string="Message Last Post", index=True, readonly=True)
    # group_id = fields.Many2one('procurement.group', 'Procurement Group', readonly=True, related='move_ids.group_id', store=True)

    
    # def action_assign(self):
    #     """ Check availability of picking moves.
    #     This has the effect of changing the state and reserve quants on available moves, and may
    #     also impact the state of the picking as it is computed based on move's states.
    #     @return: True
    #     """
    #     self.filtered(lambda picking: picking.state == 'draft').action_confirm()
    #     moves = self.move_ids.filtered(lambda move: move.state not in ('draft', 'cancel', 'done')).sorted(
    #         key=lambda move: (-int(move.priority), not bool(move.date_deadline), move.date_deadline, move.date, move.id)
    #     )
    #     if not moves:
    #         raise UserError(_('Nothing to check the availability for.'))
    #     moves._action_assign()
    #     return True
        
    # @api.depends('invoice_line_ids')
    def _compute_invoice(self):
        for order in self:
            invoices = order.invoice_line_ids.mapped('invoice_id')
            order.invoice_ids = invoices
            order.invoice_count = len(invoices)


    # @api.multi
    def name_get(self):
        res = []
        for picking in self:
            res.append((picking.id, picking.name + ((' / ' + picking.origin) if picking.origin else ''  )))
        return res


    #######################Update
    @api.onchange('receiving_id')
    def _onchange_receiving_id(self):
        if not self.receiving_id:
            return

        picking = self.receiving_id.picking_id
        if self.is_return == True:
            self.picking_type_id = picking.picking_type_id.id 
        else:
            self.picking_type_id = picking.picking_type_id.return_picking_type_id.id
        self.partner_id = picking.partner_id.id
        self.date = picking.date
        self.origin = picking.origin
        self.location_dest_id = picking.location_id.id
        self.location_id = picking.location_dest_id.id
        self.company_id = picking.company_id.id
        self.po_id = picking.po_id.id
        self.receiving_notes = picking.id


        stock_moves = []
        for line in picking.move_lines:
            # Create PO line
            stock_moves.append((0, 0, {
                'name': line.name or '',
                'product_id': line.product_id.id,
                'product_uom': line.product_uom.id,
                'date': line.date,
                'date_expected': line.date_expected,
                'location_id': line.location_dest_id.id,
                'location_dest_id': line.location_id.id,
                # 'picking_id': line.picking.id,
                'partner_id': line.partner_id.id,
                'move_dest_id': False,
                'state': 'draft',
                'purchase_line_id': line.purchase_line_id.id,
                'company_id': line.company_id.id,
                'picking_type_id': line.picking_type_id.return_picking_type_id.id,
                # 'group_id': line.group_id.id,
                # 'procurement_id': False,
                'origin': line.origin,
                # 'route_ids': [(6, 0, line.route_ids.ids)] or [],
                'warehouse_id': line.warehouse_id.id,
                 # 2021.10.05 - tambahan 
                'account_analytic_id': line.account_analytic_id.id or False,
                'move_type': 'purchase.return',
                'product_service_id': line.product_service_id.id or False,
                'product_categ_id': line.product_categ_id.id or False,
                'product_consignment': line.product_consignment or False,
                'product_supply_id': line.product_input_id.id or False,
                'product_input_id': line.product_supply_id.id or False,
                'receiving_line_id': line.receiving_line_id.id,
                'price_unit': line.price_unit,
                'sub_total': line.sub_total,
                'discount_value': line.discount_value,
                'discount_total': line.discount_total,
                'tax_discount': line.tax_discount,
                'discount_persen': line.discount_persen,
                'price_tax': line.price_tax,
                'price_total': line.price_total,
                'taxes_id': [(6, 0, line.taxes_id.ids)],
                'non_asset': line.non_asset,
                # 'base_price': line.base_price,
                'product_uom_qty': line.product_uom_qty,

                # 'price_unit': -line.price_unit if "RETURN" in self.picking_type_id.name.upper() else line.price_unit,
                # 'sub_total': -line.sub_total if "RETURN" in self.picking_type_id.name.upper() else line.sub_total,
                # 'discount_value': -line.discount_value if "RETURN" in self.picking_type_id.name.upper() else line.discount_value,
                # 'discount_total': -line.discount_total if "RETURN" in self.picking_type_id.name.upper() else line.discount_total,
                # 'tax_discount': -line.tax_discount if "RETURN" in self.picking_type_id.name.upper() else line.tax_discount,
                # 'discount_persen': -line.discount_persen if "RETURN" in self.picking_type_id.name.upper() else line.discount_persen,
                # 'price_tax': -line.price_tax if "RETURN" in self.picking_type_id.name.upper() else line.price_tax,
                # 'price_total': -line.price_total if "RETURN" in self.picking_type_id.name.upper() else line.price_total,
                # 'taxes_id': [(6, 0, line.taxes_id.ids)],
                # 'non_asset': -line.non_asset if "RETURN" in self.picking_type_id.name.upper() else line.non_asset,
                # 'product_uom_qty': -line.product_uom_qty if "RETURN" in self.picking_type_id.name.upper() else line.product_uom_qty,
            }))
        
        self.move_lines = stock_moves



    ####################### Update
    @api.onchange('receiving_notes')
    def _onchange_receiving_notes(self):
        if not self.receiving_notes:
            return

        picking = self.receiving_notes
        self.picking_type_id = picking.picking_type_id.return_picking_type_id.id
        self.partner_id = picking.partner_id.id
        self.date = picking.date
        self.origin = picking.origin
        self.location_dest_id = picking.location_id.id
        self.location_id = picking.location_dest_id.id
        self.company_id = picking.company_id.id
        self.po_id = picking.po_id.id
        self.receiving_id = picking.receiving_id.id


        stock_moves = []
        for line in picking.move_lines:
            open('/opt/odoo16/logs/dump.log', 'a+').write('\n' + "line purchaseline: " +str(line.purchase_line_id.id))
            # Create PO line
            stock_moves.append((0, 0, {
                'name': line.name or '',
                'product_id': line.product_id.id,
                'product_uom': line.product_uom.id,
                'date': line.date,
                'date_expected': line.date_expected,
                'location_id': line.location_dest_id.id,
                'location_dest_id': line.location_id.id,
                # 'picking_id': line.picking.id,
                'partner_id': line.partner_id.id,
                'move_dest_id': False,
                'state': 'draft',
                'purchase_line_id': line.purchase_line_id.id,
                'company_id': line.company_id.id,
                'picking_type_id': line.picking_type_id.return_picking_type_id.id,
                # 'group_id': line.group_id.id,
                # 'procurement_id': False,
                'origin': line.origin,
                # 'route_ids': [(6, 0, line.route_ids.ids)] or [],
                'warehouse_id': line.warehouse_id.id,
                 # 2021.10.05 - tambahan 
                'account_analytic_id': line.account_analytic_id.id or False,
                'move_type': 'purchase.return',
                'product_service_id': line.product_service_id.id or False,
                'product_categ_id': line.product_categ_id.id or False,
                'product_consignment': line.product_consignment or False,
                'product_supply_id': line.product_input_id.id or False,
                'product_input_id': line.product_supply_id.id or False,
                'receiving_line_id': line.receiving_line_id.id,
                'price_unit': line.price_unit,
                'sub_total': line.sub_total,
                'discount_value': line.discount_value,
                'discount_total': line.discount_total,
                'tax_discount': line.tax_discount,
                'discount_persen': line.discount_persen,
                'price_tax': line.price_tax,
                'price_total': line.price_total,
                'taxes_id': [(6, 0, line.taxes_id.ids)],
                'non_asset': line.non_asset,
                # 'base_price': line.base_price,
                'product_uom_qty': line.product_uom_qty,
            }))
        
        self.move_lines = stock_moves

    @api.model
    def cek_journal(self):
        self.env.cr.execute ("""    
          UPDATE stock_picking sp SET move_id = (
            SELECT id FROM account_move am 
            WHERE am.ref = sp.name 
                AND am.company_id = sp.company_id 
            LIMIT 1) 
          WHERE move_id IS NULL""")


    @api.model
    def _update_stock_picking_data(self):
        self.env.cr.execute ("""    
        UPDATE stock_picking as a 
        set origin = CONCAT  (c.name, ' (', c.rfq, ')')
        from stock_picking b
        left join purchase_order c on c.id = b.po_id
        where b.id = a.id
        and a.create_date >=(CURRENT_DATE-3) """)


    # 2021.08.31 untuk role location per user (limitation)
    @api.model
    def rule(self, domain):
        if self.env.user.id:
            # return domain
            if not domain:
                domain = []
            if self.env.user.location_ids:
                domain += [('location_dest_id', 'in', self.env.user.location_ids.ids)] #MASUKIN DISINI
            # if self.env.user.product_ids:
            #     domain += [('pack_operation_product_ids', 'in', self.env.user.product_ids.ids)]
            # if self.env.user.category_ids:
            #     domain += [('pack_operation_product_ids.id', 'in', self.env.user.product_ids.ids)]
            return domain
        
            
#     @api.model
#     def search(self, args, offset=0, limit=None, order=None, count=False):
#         args = self.rule(args) #INI MANGGIL RULE
#         return super(StockPicking, self).search(args, offset=offset, limit=limit, order=order, count=count)


#     @api.model
#     def name_search(self, name, args=None, operator='ilike', limit=100):
#         args = self.rule(args) #INI JUGA
#         return super(StockPicking, self).name_search(name, args=args, operator=operator, limit=limit)


    # @api.multi
    def manual_backorder(self):
        for record in self:
            if record.backordered:
               raise exceptions.ValidationError("Backorder already created")
            else:
                env = self.env
                view = env.ref('stock.view_backorder_confirmation')
                backorder_id = env['stock.picking'].search([('backorder_id', '=', record.id)])
                if record.state == 'cancel':
                   backorder_id = record
                if not backorder_id:
                   raise exceptions.ValidationError("Can't create backorder")
                wiz = env['stock.backorder.confirmation'].create({'pick_id': backorder_id.id})
                return {
                    'name': _('Create Backorder?'),
                    'type': 'ir.actions.act_window',
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'stock.backorder.confirmation',
                    'views': [(view.id, 'form')],
                    'view_id': view.id,
                    'target': 'new',
                    'res_id': wiz.id,
                    'context': self.with_context(manual=True).env.context,
                }


    # @api.multi
    def print_return(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/inventory/purchase_return?id=' + str(self.id)
        action['target'] = 'new'
        return action
    
    # @api.multi
    def print_notes(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/inventory/receiving_notes?id=' + str(self.id)
        action['target'] = 'new'
        return action
    
    # @api.multi
    def action_print(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/inventory/delivery_order?id=' + str(self.id)
        action['target'] = 'new'
        return action


    # @api.multi
    def action_confirm(self):
      for record in self:
        for move in record.move_lines:
          if not move.location_id:
            move.location_id = self.location_id
            move.location_dest_id = self.location_dest_id
            move.picking_type_id = self.picking_type_id
      result = super(StockPicking, self).action_confirm()


    # @api.multi
    def requestor_sign(self):
        action = {}
        action['type'] = 'ir.actions.act_window'
        action['name'] = 'Sign'
        action['res_model'] = 'signature.wizard'
        action['view_mode'] = 'form'
        action['target'] = 'new'
        action['context'] = self.with_context(active_ids=self.ids, model=self._name, field='requestor_signature').env.context
        return action


    # 2021.10.06 - modify account.move.line
    # @api.multi
    def button_journal_entries(self):
        return {
            'name': _('Journal Items'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('stock_picking_id', 'in', self.ids)],
        }


    # 2021.09.09 - check auto confirm ??
    # @api.multi
    def check_autoconfirm(self):
      if self.sync_id_api and self.pack_operation_ids:
          for r in self.pack_operation_ids:

            if not r.pack_lot_ids:
              if r.lots_visible == True:
                move = self.env['stock.move'].search([('picking_id', '=', self.id), ('product_id', '=', r.product_id.id)])
                line = []
                lot_id = False

                for m in move:
                  # lot_already_ids = self.env['stock.pack.operation.lot'].search([('lot_id', '!=', False)]).mapped('lot_id')
                  if m.lot_id:
                    lot_id = m.lot_id
                    print (lot_id)

                  else:
                    lot_id = self.env['stock.lot'].search([('product_id', '=', m.product_id.id)], order='id desc', limit=1)
                    print (lot_id)
                    print (len(lot_id))
                    print (len(move))

                  # print lot_id
                  if lot_id:
                    line = []
                    for lot in lot_id:
                      line.append([0, 0, {'lot_id': lot.id, 'qty': m.product_uom_qty}])
                      print (line)

                  else:
                    lot_create = self.env['stock.lot'].create({'product_id': r.product_id.id})
                    lot_id = lot_create.id
                    line.append([0, 0, {'lot_id': lot_id, 'qty': m.product_uom_qty}])

                r.write({'pack_lot_ids': line})
                r.write({'qty_done': r.product_qty})
              else:
                r.write({'qty_done': r.product_qty})

            else:
              for pack_lot in r.pack_lot_ids:
                pack_lot.write({'qty': pack_lot.qty_todo})
                r.write({'qty_done': r.product_qty})

    # @api.multi
    def _create_asset_entry(self, master_asset):
        now = tools.datetime.now().strftime('%Y-%m-%d')
        journal_id = self.env['account.journal'].sudo().search([('code','=','AJ'), ('name','=', 'Asset Journal'), ('company_id','=', self.company_id.id)], limit=1).id

        journal_to_create = []
        for line in master_asset:
            picking_asset = self.env['stock.picking.asset'].sudo().search([('id','=', line.picking_asset_id.id)])
            
            if picking_asset.value > 0:
                debit_amount = 0
                credit_amount = abs(picking_asset.value)
                debit_amount_2 = abs(picking_asset.value)
                credit_amount_2 = 0
            else:
                debit_amount = abs(picking_asset.value)
                credit_amount = 0
                debit_amount_2 = 0
                credit_amount_2 = abs(picking_asset.value)
                
            move_lines = []
            #1
            move_lines.append([0, 0, {
                'name' : picking_asset.name, 
                'ref' : picking_asset.name + ' / ' + line.code, 
                'partner_id' : line.picking_asset_id.picking_id.partner_id.id,
                'account_id' : picking_asset.credit_account_id.id, 
                'date_maturity' : tools.datetime.now().strftime('%Y-%m-%d'),
                'debit' : debit_amount, 
                'credit' : credit_amount
            }])
            
            #2
            move_lines.append([0, 0, {
                'name' : picking_asset.name, 
                'ref' : picking_asset.name + ' / ' + line.code,
                'partner_id' : line.picking_asset_id.picking_id.partner_id.id,
                'account_id' : picking_asset.type.account_asset_id.id, 
                'date_maturity' : tools.datetime.now().strftime('%Y-%m-%d'),
                'debit' : debit_amount_2,
                'credit' : credit_amount_2
            }])
                
            
            journal_to_create.append({
                'journal_id':journal_id,
                'ref' : picking_asset.name + ' / ' + line.code, 
                'partner_id' : line.picking_asset_id.picking_id.partner_id.id,
                'line_ids' : move_lines,
                'date' : self.date_move or now, 
                'stock_picking_id' : self.id, 
                'stock_picking_asset_id' : picking_asset.id, 
                'account_asset_id' : line.id
            })
            

        if journal_to_create:
            move = self.env['account.move'].create(journal_to_create)
            if move:
                move.action_post()


    # @api.multi
    def _create_master_asset(self):
        now = tools.datetime.now().strftime('%Y-%m-%d')
        # journal_id = self.env['account.journal'].sudo().search([('code','=','AJ'), ('name','=', 'Asset Journal'), ('company_id','=', self.company_id.id)], limit=1).id
        
        for pa in self.asset_ids:
            count_qty = 0
            for qty_line in range(int(pa.qty)):
                if pa.value < 2000000:
                    value = "{:,.2f}".format(pa.value).replace(",", "X").replace(".", ",").replace("X", ".")
                    raise exceptions.ValidationError("{name} Valuation is worth Rp. {value}, Cannot be less than Rp. 2.000.000,00".format(name=pa.name, value=value))        

                #if count_qty != int(pa.qty):
                if count_qty < int(pa.qty):
                    vals = {
                        'company_id' : self.company_id.id,
                        'category_id' : pa.type.id,
                        'subcategory_id' : pa.subcategory_id.id,
                        'location_id' : pa.receipt_location.id,
                        'picking_id' : pa.picking_id.id,
                        'picking_asset_id' : pa.id,
                        'method_number' : pa.method_number,
                        'method_period' : pa.method_period,
                        'date' : self.date_move or pa.date,
                        'name' : pa.name,
                        'qty' : 1.0,
                        'value' : pa.value,
                        'method_period' : '1',
                    }
                
                    # create master asset
                    master_asset = self.env['account.asset.asset'].create(vals)
                    if master_asset:
                        master_asset.method_number = pa.method_number
                        master_asset.method_period = pa.method_period
                    
                    # create journal asset
                    journal_asset = self._create_asset_entry(master_asset)

                    # add count_qty
                    count_qty = count_qty + 1
            
            # # create master asset
            # if assets_to_create:
            #     master_asset = self.env['account.asset.asset'].create(assets_to_create)
            
            #     # create journal asset
            #     if master_asset:
            #         journal_asset = self._create_asset_entry(master_asset)


    # # @api.multi
    # def _create_asset_entry(self, master_asset):
    #     now = tools.datetime.now().strftime('%Y-%m-%d')
    #     picking_asset = self.env['stock.picking.asset'].sudo().search([('id','=', master_asset.picking_asset_id.id)])
    #     journal_id = self.env['account.journal'].sudo().search([('code','=','AJ'), ('name','=', 'Asset Journal'), ('company_id','=', self.company_id.id)], limit=1).id
        
    #     if picking_asset.value > 0:
    #         debit_amount = 0
    #         credit_amount = abs(picking_asset.value)
    #         debit_amount_2 = abs(picking_asset.value)
    #         credit_amount_2 = 0
    #     else:
    #         debit_amount = abs(picking_asset.value)
    #         credit_amount = 0
    #         debit_amount_2 = 0
    #         credit_amount_2 = abs(picking_asset.value)
            
    #     move_lines = []
    #     #1
    #     move_lines.append([0, 0, {
    #         'name' : picking_asset.name, 
    #         'ref' : picking_asset.name + ' / ' + master_asset.code, 
    #         'partner_id' : master_asset.picking_asset_id.picking_id.partner_id.id,
    #         'account_id' : picking_asset.credit_account_id.id, 
    #         'date_maturity' : tools.datetime.now().strftime('%Y-%m-%d'),
    #         'debit' : debit_amount, 
    #         'credit' : credit_amount
    #     }])
        
    #     #2
    #     move_lines.append([0, 0, {
    #         'name' : picking_asset.name, 
    #         'ref' : picking_asset.name + ' / ' + master_asset.code,
    #         'partner_id' : master_asset.picking_asset_id.picking_id.partner_id.id,
    #         'account_id' : picking_asset.type.account_asset_id.id, 
    #         'date_maturity' : tools.datetime.now().strftime('%Y-%m-%d'),
    #         'debit' : debit_amount_2,
    #         'credit' : credit_amount_2
    #     }])
            

    #     move = self.env['account.move'].create({'journal_id':journal_id,
    #         'ref' : picking_asset.name + ' / ' + master_asset.code, 
    #         'partner_id' : master_asset.picking_asset_id.picking_id.partner_id.id,
    #         'line_ids' : move_lines,
    #         'date' : self.date_move or now, 
    #         'stock_picking_id' : self.id, 
    #         'stock_picking_asset_id' : picking_asset.id, 
    #         'account_asset_id' : master_asset.id})
        
    #     if move:
    #         move.action_post()    


    # # @api.multi
    # def _create_master_asset(self):
    #     now = tools.datetime.now().strftime('%Y-%m-%d')
    #     journal_id = self.env['account.journal'].sudo().search([('code','=','AJ'), ('name','=', 'Asset Journal'), ('company_id','=', self.company_id.id)], limit=1).id
        
    #     for pa in self.asset_ids:
    #         count_qty = 0
    #         for qty_line in range(int(pa.qty)):
    #             if count_qty != int(pa.qty):
    #                 vals = {
    #                     'journal_id' : journal_id,
    #                     'company_id' : self.company_id.id,
    #                     'category_id' : pa.type.id,
    #                     'subcategory_id' : pa.subcategory_id.id,
    #                     'location_id' : pa.receipt_location.id,
    #                     'picking_id' : pa.picking_id.id,
    #                     'picking_asset_id' : pa.id,
    #                     # 'method_number' : pa.method_number,
    #                     # 'method_period' : pa.method_period,
    #                     'date' : self.date_move or pa.date,
    #                     'name' : pa.name,
    #                     'qty' : 1.0,
    #                     'value' : pa.value,
    #                     'method_period' : '1',
    #                 }
                
    #                 # create master asset
    #                 master_asset = self.env['account.asset.asset'].create(vals)
    #                 if master_asset:
    #                     master_asset.method_number = pa.method_number
    #                     master_asset.method_period = pa.method_period
                    
    #                 # create journal asset
    #                 journal_asset = self._create_asset_entry(master_asset)

    #                 # add count_qty
    #                 count_qty = count_qty + 1

    def _sanity_check(self, separate_pickings=True):
        print ("_sanity_check")
        # """ Sanity check for `button_validate()`
        #     :param separate_pickings: Indicates if pickings should be checked independently for lot/serial numbers or not.
        # """
        # pickings_without_lots = self.browse()
        # products_without_lots = self.env['product.product']
        # pickings_without_moves = self.filtered(lambda p: not p.move_ids and not p.move_line_ids)
        # precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        # no_quantities_done_ids = set()
        # no_reserved_quantities_ids = set()
        # for picking in self:
        #     if all(float_is_zero(move_line.qty_done, precision_digits=precision_digits) for move_line in picking.move_line_ids.filtered(lambda m: m.state not in ('done', 'cancel'))):
        #         no_quantities_done_ids.add(picking.id)
        #     if all(float_is_zero(move_line.reserved_qty, precision_rounding=move_line.product_uom_id.rounding) for move_line in picking.move_line_ids):
        #         no_reserved_quantities_ids.add(picking.id)
        
        # pickings_without_quantities = self.filtered(lambda p: p.id in no_quantities_done_ids and p.id in no_reserved_quantities_ids)

        # pickings_using_lots = self.filtered(lambda p: p.picking_type_id.use_create_lots or p.picking_type_id.use_existing_lots)
        # if pickings_using_lots:
        #     lines_to_check = pickings_using_lots._get_lot_move_lines_for_sanity_check(no_quantities_done_ids, separate_pickings)
        #     for line in lines_to_check:
        #         if not line.lot_name and not line.lot_id:
        #             pickings_without_lots |= line.picking_id
        #             products_without_lots |= line.product_id

        # if not self._should_show_transfers():
        #     if pickings_without_moves:
        #         raise UserError(_('Please add some items to move.'))
        #     if pickings_without_quantities:
        #         raise UserError(self._get_without_quantities_error_message())
        #     if pickings_without_lots:
        #         raise UserError(_('You need to supply a Lot/Serial number for products %s.') % ', '.join(products_without_lots.mapped('display_name')))
        # else:
        #     message = ""
        #     if pickings_without_moves:
        #         message += _('Transfers %s: Please add some items to move.') % ', '.join(pickings_without_moves.mapped('name'))
        #     if pickings_without_quantities:
        #         message += _('\n\nTransfers %s: You cannot validate these transfers if no quantities are reserved nor done. To force these transfers, switch in edit more and encode the done quantities.') % ', '.join(pickings_without_quantities.mapped('name'))
        #     if pickings_without_lots:
        #         message += _('\n\nTransfers %s: You need to supply a Lot/Serial number for products %s.') % (', '.join(pickings_without_lots.mapped('name')), ', '.join(products_without_lots.mapped('display_name')))
        #     if message:
        #         raise UserError(message.lstrip())


    def button_validate(self):
        journal_id = self.env['account.journal'].sudo().search([('code','=','AJ'), ('name','=', 'Asset Journal'), ('company_id','=', self.company_id.id)], limit=1).id

        # generate journal grn
        # if not self.move_id:
        if not self.journal_ids:
            for p in self.move_ids:
                if p.non_asset > 0:
                    move_lines = p.create_journal_grn()

                    if move_lines:
                        move = self.env['account.move'].create({'stock_picking_id': self.id, 'journal_id': p.product_id.categ_id.property_stock_journal.id, 'name': self.name, 'ref': self.name, 'line_ids': move_lines, 'cip_id': p.asset_cip_id.id})
                        
                        if move:
                            move.state = 'posted'
                            # self.move_id = move.id
                            # overide state
                            p.state = 'done'
                            self.state = 'done'

        
        # generate master asset jika existing
        # avoid duplicate double master asset
        check_asset = self.env['account.asset.asset'].sudo().search([('picking_id','=', self.id)])
        if not check_asset:
            if self.asset_ids:
                self._create_master_asset()

        stock_move_check = self.env['stock.move'].sudo().search([('picking_id','=', self.id)], limit=1)
        if stock_move_check.non_asset <= 0:
            # raise UserError(_("1"))
            self.state = 'done'
            for line in self.move_line_ids:
                line.state = 'done'
            return True #exit
        else:
            # raise UserError(_("2"))
            result = super(StockPicking, self).button_validate()
            return result

        # result = super(StockPicking, self).button_validate()
        # return result

    # #############update
    # # @api.multi
    # def do_new_transfer(self):
    #     # self.action_confirm()
    #     # self.force_assign()
    #     if self.search([('id', 'in', self.ids), ('company_id', '!=', self.env.company.id)]):
    #         qty_move = sum(record.product_uom_qty for record in self.move_lines)
    #         # qty_op = sum(record.qty_done for record in self.pack_operation_product_ids)
    #         # if qty_op > qty_move:
    #         #     raise exceptions.ValidationError("Quantity Can't be larger than move!")


    #     # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "ced1 : ")
    #     # cost_center = self.move_lines.mapped('account_analytic_id.id')
    #     # for cc in cost_center:
    #     #     open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "ced2 : ")
    #     #     cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
    #     #     cc_name = self.env['account.analytic.account'].browse(cc).display_name
    #     #     if self.env.company.cost_center_active == True and self.env.company.cost_center_date <= self.date_move:
    #     #         open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "ced3 : ")
    #     #         order_line = self.move_lines.search([('picking_id', '=', self.id),('account_analytic_id', '=', cc)])
    #     #         amount_po = sum(r.price_total for r in order_line.purchase_line_id)
                
    #     #         budget_used = self.env['crossovered.budget.lines'].sudo().search([
    #     #             ('analytic_account_id', '=', cc),
    #     #             # ('crossovered_budget_id.state','in', ['validate','done']),
    #     #             ('crossovered_budget_id.date_from', '<=',self.date),
    #     #             ('crossovered_budget_id.date_to', '>=',self.date)])
    #     #         if budget_used:
    #     #             open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "ced4 : ")
    #     #             budget_used.budget_line_compute_balance()
    #     #             budget = sum(budget.remain_amount for budget in budget_used)
    #     #             budget = budget
    #     #             # exceed = sum(budget.exceed_amount for budget in budget_used)
    #     #             # exceed = exceed
    #     #             # real_budget = budget + exceed
    #     #             real_budget = budget
    #     #             open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "exceed2 : " + str(exceed))
    #     #             open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "budget2 : " + str(budget))
    #     #             open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "real budget2 : " + str(real_budget))
    #     #             open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "amount sp3 : " + str(amount_po))
    #     #             if cc and amount_po > real_budget:
    #     #                 raise exceptions.ValidationError("Cost center " + cc_name +" exceeds the Total of Budget's Planned Amount")
    #     #             budget_used.budget_line_compute_balance()
        
        
    #     # generate master asset jika existing
    #     if self.asset_ids:
    #         open('/opt/odoo16/logs/log_masuk_sini.log','a+').write('\n okkk: '+str(self.name))
    #         self._create_master_asset()
        
    #     result = super(StockPicking, self).button_validate()
    #     return result

    #     # if self.env.company.sync_api_active == True:
    #     #   for record in self:
    #     #         for move in record.move_lines:
    #     #             if record.date_move:
    #     #                 move.date = record.date_move
    #     #             if record.date_move and record.min_date:
    #     #                 move.date = record.date_move
    #     #             if record.min_date and not record.date_move:
    #     #                 move.date = record.min_date

    #     #             move.update_best_price_item()
    #     #         i = 0
    #     #         payload_detail = []
    #     #         payload_head = {}
    #     #         payload = {}
    #     #         post_api = True

    #     #         for pack_op in record.pack_operation_product_ids:
    #     #           moves = record.env['stock.move'].search([('product_id', '=', pack_op.product_id.id), ('picking_id', '=', record.id)])
    #     #           for m in moves:
    #     #             if pack_op.pack_lot_ids:
    #     #               for lot in pack_op.pack_lot_ids:
    #     #                   detail = {}
    #     #                   detail['itemId'] = pack_op.product_id.sync_id_api or ""
    #     #                   if lot.lot_name:
    #     #                     detail['batchNumber'] = str(lot.lot_name) + ' / ' + str(lot.id) or ""
    #     #                     detail['expiredDate'] = lot.expired_date or ""
    #     #                   else:
    #     #                     detail['batchNumber'] = str(lot.lot_id.name) or ""
    #     #                     detail['expiredDate'] = lot.lot_id.life_date or ""
    #     #                   detail['qty'] = int(lot.qty) or 0
    #     #                   detail['uomId'] = pack_op.product_uom_id.sync_id_api or ""
    #     #                   detail['UomName'] = pack_op.product_uom_id.name or ""
    #     #                   detail['cogs'] = int(m.price_unit) or 0

    #     #                   payload_detail.append(detail)
    #     #             else:
    #     #               detail = {}
    #     #               detail['itemId'] = pack_op.product_id.sync_id_api or ""
    #     #               detail['batchNumber'] = " "
    #     #               detail['expiredDate'] = ""
    #     #               detail['qty'] = int(pack_op.qty_done) or 0
    #     #               detail['uomId'] = pack_op.product_uom_id.sync_id_api or ""
    #     #               detail['UomName'] = pack_op.product_uom_id.name or ""
    #     #               detail['cogs'] = int(m.price_unit) or 0

    #     #               payload_detail.append(detail)

    #     #               i+=1

    #     #         now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    #     #         transactionDate = tools.datetime.strptime(record.create_date, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%S.%fZ')

    #     #         if str(record.picking_type_id.code) == 'internal':
    #     #             url = self.env.company.his_api_url + '/odoo/inventories/InternalTransfer'
    #     #             headers = {'Content-Type': 'application/json', 'x-api-key' : self.env.company.his_api_key}
    #     #             payload = {
    #     #                 "head" : {
    #     #                     "siteId": record.company_id.sync_type,
    #     #                     "roomIdSource": record.location_id.sync_id_api or "",
    #     #                     "roomIdDestination": record.location_dest_id.sync_id_api or "",
    #     #                     "remark": "",
    #     #                     "transactionNumber": str(record.name) or "",
    #     #                     "transactionDate": transactionDate or "",
    #     #                 },
    #     #                 "detail" : payload_detail
    #     #             }

    #     #         elif str(record.picking_type_id.code) == 'incoming':
    #     #             url = self.env.company.his_api_url + '/odoo/inventories/ReceiveStock'
    #     #             headers = {'Content-Type': 'application/json', 'x-api-key': self.env.company.his_api_key}
    #     #             payload = {
    #     #                 "head" : {
    #     #                     "siteId": record.company_id.sync_type,
    #     #                     "roomId": record.location_dest_id.sync_id_api or "",
    #     #                     "remark": "",
    #     #                     "transactionNumber": str(record.name) or "",
    #     #                     "transactionDate": transactionDate or ""
    #     #                 },
    #     #                 "detail" : payload_detail
    #     #             }

    #     #         elif str(record.picking_type_id.code) == 'outgoing' and str(record.location_dest_id.usage) == 'supplier':
    #     #             url = self.env.company.his_api_url + '/odoo/inventories/ReturnSupplier'
    #     #             headers = {'Content-Type': 'application/json', 'x-api-key': self.env.company.his_api_key}
    #     #             payload = {
    #     #                 "head" : {
    #     #                     "siteId": record.company_id.sync_type,
    #     #                     "roomId": record.location_id.sync_id_api or "",
    #     #                     "remark": "",
    #     #                     "transactionNumber": str(record.name) or "",
    #     #                     "transactionDate": transactionDate or ""
    #     #                 },
    #     #                 "detail" : payload_detail
    #     #             }

    #     #         else:
    #     #             post_api = False

    #     #         if post_api == True:
    #     #             open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n' + str(headers) + '\n' + str(payload))
    #     #             response_json = requests.post(url=url, headers=headers, json=payload, verify=False)
    #     #             open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n' + str(response_json))
    #     #             json_resp = response_json.json()

    #     #             api_post_status = 'failed'

    #     #             if 'Status' in json_resp:
    #     #                 if json_resp['Status'] == True:
    #     #                     api_post_status = 'done'

    #     #             data = {
    #     #                 'api_post_payload': payload,
    #     #                 'api_post_response': json_resp,
    #     #                 'api_post_timestamp': now,
    #     #                 'api_post_status': api_post_status,
    #     #                 'api_post_url': url,
    #     #             }

    #     #             write_result = super(StockPicking, self).write(data)
    #     # return result


    # @api.multi
    def send_internal_transfer(self): #Action to resend API to api
        print ("DO SOMETHING")
        # for record in self:
            # if self.env.company.sync_api_active == True:
            #     i = 0
            #     payload_detail = []
            #     payload_head = {}
            #     payload = {}
            #     post_api = True

            #     for pack_op in record.pack_operation_product_ids:
            #       if pack_op.pack_lot_ids:
            #         for lot in pack_op.pack_lot_ids:
            #             detail = {}
            #             detail['itemId'] = pack_op.product_id.sync_id_api or ""
            #             if lot.lot_name:
            #               detail['batchNumber'] = str(lot.lot_name)  + ' / ' + str(lot.id) or ""
            #               detail['expiredDate'] = lot.expired_date or ""
            #             else:
            #               detail['batchNumber'] = str(lot.lot_id.name) or ""
            #               detail['expiredDate'] = lot.lot_id.life_date or ""
            #             detail['qty'] = int(lot.qty) or 0
            #             detail['uomId'] = pack_op.product_uom_id.sync_id_api or ""
            #             detail['UomName'] = pack_op.product_uom_id.name or ""
            #             detail['cogs'] = int(record.move_lines[i].price_unit) or 0

            #             payload_detail.append(detail)

            #       else:
            #         detail = {}
            #         detail['itemId'] = pack_op.product_id.sync_id_api or ""
            #         detail['batchNumber'] = " "
            #         detail['expiredDate'] = ""
            #         detail['qty'] = int(pack_op.qty_done) or 0
            #         detail['uomId'] = pack_op.product_uom_id.sync_id_api or ""
            #         detail['UomName'] = pack_op.product_uom_id.name or ""
            #         detail['cogs'] = int(record.move_lines[i].price_unit) or 0

            #         payload_detail.append(detail)
                        
            #         i+=1

            #     now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            #     transactionDate = tools.datetime.strptime(record.create_date, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%S.%fZ')

            #     if str(record.picking_type_id.code) == 'internal':
            #         url = self.env.company.his_api_url + '/odoo/inventories/InternalTransfer'
            #         headers = {'Content-Type': 'application/json', 'x-api-key' : self.env.company.his_api_key}
            #         payload = {
            #             "head" : {
            #                 "siteId": record.company_id.sync_type,
            #                 "roomIdSource": record.location_id.sync_id_api or "",
            #                 "roomIdDestination": record.location_dest_id.sync_id_api or "",
            #                 "remark": "",
            #                 "transactionNumber": str(record.name) or "",
            #                 "transactionDate": transactionDate or "",
            #             },
            #             "detail" : payload_detail
            #         }

            #     elif str(record.picking_type_id.code) == 'incoming':
            #         url = self.env.company.his_api_url + '/odoo/inventories/ReceiveStock'
            #         headers = {'Content-Type': 'application/json', 'x-api-key': self.env.company.his_api_key}
            #         payload = {
            #             "head" : {
            #                 "siteId": record.company_id.sync_type,
            #                 "roomId": record.location_dest_id.sync_id_api or "",
            #                 "remark": "",
            #                 "transactionNumber": str(record.name) or "",
            #                 "transactionDate": transactionDate or ""
            #             },
            #             "detail" : payload_detail
            #         }

            #     elif str(record.picking_type_id.code) == 'outgoing' and str(record.location_dest_id.usage) == 'supplier':
            #         url = self.env.company.his_api_url + '/odoo/inventories/ReturnSupplier'
            #         headers = {'Content-Type': 'application/json', 'x-api-key': self.env.company.his_api_key}
            #         payload = {
            #             "head" : {
            #                 "siteId": record.company_id.sync_type,
            #                 "roomId": record.location_id.sync_id_api or "",
            #                 "remark": "",
            #                 "transactionNumber": str(record.name) or "",
            #                 "transactionDate": transactionDate or ""
            #             },
            #             "detail" : payload_detail
            #         }

            #     else:
            #         post_api = False

            #     if post_api == True:
            #         open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n' + str(headers) + '\n' + str(payload))
            #         response_json = requests.post(url=url, headers=headers, json=payload, verify=False)
            #         open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n' + str(response_json))
            #         json_resp = response_json.json()

            #         api_post_status = 'failed'

            #         if 'Status' in json_resp:
            #             if json_resp['Status'] == True:
            #                 api_post_status = 'done'

            #         data = {
            #             'api_post_payload': payload,
            #             'api_post_response': json_resp,
            #             'api_post_timestamp': now,
            #             'api_post_status': api_post_status,
            #         }
            #         write_result = super(StockPicking, self).write(data)



    
    # @api.multi
    def print_qrcode(self):
        # action = {}
        # action['type'] = 'ir.actions.act_url'
        # action['url'] = '/account/print_out_qr_asset?format=multiple&id=' + str(self.id)
        # action['target'] = 'new'
        # return action
    
        return {
            'name': 'Print QRCode',
            'domain': [],
            'res_model': 'account.asset.print.qrcode.wizard',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'view_type': 'form',
            'context': {
                'default_picking_id': self.id
            },
            'target': 'new',
        }


    # 2021.11.09 - override validate stock.picking to create master account.asset.asset
    # @api.multi
    def do_transfer(self):
        """ If no pack operation, we do simple action_done of the picking.
        Otherwise, do the pack operations. """
        # TDE CLEAN ME: reclean me, please
        self._create_lots_for_picking()

        ################Update
        if self.receiving_id:
            self.receiving_id.state ='posted'


        if self.is_return:
            self.receiving_id.is_po_completed = False
            self.receiving_id.purchase_id.is_po_completed = False
            self.receiving_id.is_return = True


        no_pack_op_pickings = self.filtered(lambda picking: not picking.pack_operation_ids)
        no_pack_op_pickings.action_done()
        other_pickings = self - no_pack_op_pickings
        cost_center = self.move_lines.mapped('account_analytic_id.id')
    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "MASUK SINI 1 DO TRANSFER ")

        for cc in cost_center:
            cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
            cc_name = self.env['account.analytic.account'].browse(cc).display_name
            if self.company_id.cost_center_active:
                if not self.company_id.cost_center_date or not self.company_id.cost_center_budget_date or not self.date_move:
                    raise UserError(_("Tanggal tidak boleh kosong."))
            if self.company_id.cost_center_active == True and self.company_id.cost_center_date <= self.date_move:
        # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "MASUK SINI 2 DO TRANSFER ")

                order_line = self.move_lines.search([('picking_id', '=', self.id),('account_analytic_id', '=', cc)])
                amount_po = sum(r.price_total for r in order_line.purchase_line_id)
                
                budget_used = self.env['crossovered.budget.lines'].sudo().search([
                    ('analytic_account_id', '=', cc),
                    ('crossovered_budget_id.state','in', ['validate','done']),
                    ('date_from', '<=',self.date),
                    ('date_to', '>=',self.date)])
                if budget_used:
            # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "MASUK SINI 3 DO TRANSFER ")

                    budget_used.budget_line_compute_balance()
                    budget = sum(budget.remain_amount for budget in budget_used)
                    budget = budget
                    # exceed = sum(budget.exceed_amount for budget in budget_used)
                    # exceed = exceed
                    # real_budget = budget + exceed
                    real_budget = budget
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "exceed : " + str(exceed))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "budget : " + str(budget))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "real budget : " + str(real_budget))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "amount sp1 : " + str(amount_po))
                    if cc and amount_po > real_budget and self.company_id.cost_center_budget_date <= self.date_move:
            # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "MASUK SINI 4 DO TRANSFER ")

                        raise exceptions.ValidationError("Cost center " + cc_name +" exceeds the Total of Budget's Planned Amount" + '\n' + "Current Remaining Budget : " + str(real_budget) + '\n' + "Please Submit Request for Approval Exceed Budget for this PO")
                    
        for picking in other_pickings:
            need_rereserve, all_op_processed = picking.picking_recompute_remaining_quantities()
            todo_moves = self.env['stock.move']
            toassign_moves = self.env['stock.move']

            # create extra moves in the picking (unexpected product moves coming from pack operations)
            if not all_op_processed:
                todo_moves |= picking._create_extra_moves()

            if need_rereserve or not all_op_processed:
                moves_reassign = any(x.origin_returned_move_id or x.move_orig_ids for x in picking.move_lines if x.state not in ['done', 'cancel'])
                if moves_reassign and picking.location_id.usage not in ("supplier", "production", "inventory"):
                    # unnecessary to assign other quants than those involved with pack operations as they will be unreserved anyways.
                    picking.with_context(reserve_only_ops=True, no_state_change=True).rereserve_quants(move_ids=picking.move_lines.ids)
                picking.do_recompute_remaining_quantities()

            # split move lines if needed
            for move in picking.move_lines:
                rounding = move.product_id.uom_id.rounding
                remaining_qty = move.remaining_qty
                if move.state in ('done', 'cancel'):
                    # ignore stock moves cancelled or already done
                    continue
                elif move.state == 'draft':
                    toassign_moves |= move
                if float_compare(remaining_qty, 0,  precision_rounding=rounding) == 0:
                    if move.state in ('draft', 'assigned', 'confirmed'):
                        todo_moves |= move
                elif float_compare(remaining_qty, 0, precision_rounding=rounding) > 0 and float_compare(remaining_qty, move.product_qty, precision_rounding=rounding) < 0:
                    # TDE FIXME: shoudl probably return a move - check for no track key, by the way
                    new_move_id = move.split(remaining_qty)
                    new_move = self.env['stock.move'].with_context(mail_notrack=True).browse(new_move_id)
                    todo_moves |= move
                    # Assign move as it was assigned before
                    toassign_moves |= new_move


                # 2021.11.09 - tambahkan untuk otomatis create master asset
                if move.asset_category_id:
                    vals = {
                        'name': move.name,
                        'category_id': move.asset_category_id.id,
                        'value': move.asset_value or purchase_line_id.price_subtotal or 0,
                        'partner_id': picking.partner_id.id,
                        'company_id': picking.company_id.id,
                        'currency_id': picking.company_id.currency_id.id,
                        'date': picking.date_move,
                        'picking_id': picking.id,
                        'location_id': move.asset_location_id.id,
                        'vendor_ref': picking.origin,
                        'brand': move.asset_brand,
                        'qty': move.product_uom_qty
                    }
                    changed_vals = self.env['account.asset.asset'].onchange_category_id_values(vals['category_id'])
                    vals.update(changed_vals['value'])
                    asset = self.env['account.asset.asset'].create(vals)
                    if move.asset_category_id.open_asset:
                        asset.validate()


            # TDE FIXME: do_only_split does not seem used anymore
            if todo_moves and not self.env.context.get('do_only_split'):
                todo_moves.action_done()
            elif self.env.context.get('do_only_split'):
                picking = picking.with_context(split=todo_moves.ids)

            picking._create_backorder()
        open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "exceed1 : ")
        cost_center = self.move_lines.mapped('account_analytic_id.id')
        for cc in cost_center:
            open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "exceed2 : ")
            cc_budget_true = self.env['account.analytic.account'].browse(cc).budget_true
            cc_name = self.env['account.analytic.account'].browse(cc).display_name
            if self.company_id.cost_center_active:
                if not self.company_id.cost_center_date or not self.date_move:
                    raise UserError(_("Tanggal tidak boleh kosong."))
            if self.company_id.cost_center_active == True and self.company_id.cost_center_date <= self.date_move:
                open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "exceed3 : ")
                order_line = self.move_lines.search([('picking_id', '=', self.id),('account_analytic_id', '=', cc)])
                # amount_po = sum(r.price_total for r in order_line.purchase_line_id)
                
                budget_used = self.env['crossovered.budget.lines'].sudo().search([
                    ('analytic_account_id', '=', cc),
                    ('crossovered_budget_id.state','in', ['validate','done']),
                    ('date_from', '<=',self.date),
                    ('date_to', '>=',self.date)])
                if budget_used:
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "exceed4 : ")
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "list budget_used : " + str(budget_used))
                    budget_used.budget_line_compute_balance()
                    # budget = sum(budget.remain_amount for budget in budget_used)
                    # budget = budget
                    # # exceed = sum(budget.exceed_amount for budget in budget_used)
                    # # exceed = exceed
                    # # real_budget = budget + exceed
                    # real_budget = budget
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "exceed : " + str(exceed))
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "budget : " + str(budget))
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "real budget : " + str(real_budget))
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "amount sp2 : " + str(amount_po))
                    # if cc and amount_po > real_budget:
                    #     raise exceptions.ValidationError("Cost center " + cc_name +" exceeds the Total of Budget's Planned Amount")
        return True


    # 2021.10.16 - tambahkan default credit days saat create VB dari PO 
    # @api.multi
    def action_view_invoice(self):
        '''
        This function returns an action that display existing vendor bills of given purchase order ids.
        When only one found, show the vendor bill immediately.
        '''
        action = self.env.ref('account.action_invoice_tree2')
        result = action.read()[0]

        #override the context to get rid of the default filtering
        result['context'] = {'type': 'in_invoice', 
            'default_source_type': 'rn',
            'default_picking_id': self.id, 
            'default_partner_id': self.partner_id.id}

        if not self.invoice_ids:
            # Choose a default account journal in the same currency in case a new invoice is created
            journal_domain = [
                ('type', '=', 'purchase'),
                ('company_id', '=', self.company_id.id),
                ('currency_id', '=', self.po_id.currency_id.id),
            ]
            default_journal_id = self.env['account.journal'].search(journal_domain, limit=1)
            if default_journal_id:
                result['context']['default_journal_id'] = default_journal_id.id
        else:
            # Use the same account journal than a previous invoice
            result['context']['default_journal_id'] = self.invoice_ids[0].journal_id.id

        #choose the view_mode accordingly
        if len(self.invoice_ids) != 1:
            result['domain'] = "[('id', 'in', " + str(self.invoice_ids.ids) + ")]"
        elif len(self.invoice_ids) == 1:
            res = self.env.ref('account.invoice_supplier_form', False)
            result['views'] = [(res and res.id or False, 'form')]
            result['res_id'] = self.invoice_ids.id
        return result


class StockReceiving(models.Model):
    _name = 'stock.receiving'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    @api.model
    def _get_company(self):
        return self.env.company.id

    @api.model
    def _get_user_id(self):
        return self.env.user.id

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company',string="Company",default=_get_company)
    name = fields.Char(string="Receiving No.")
    date = fields.Date(string="Receiving Date")
    ref = fields.Char(string="Ref No.")
    user_id = fields.Many2one('res.users', string="Responsible", default=_get_user_id)
    purchase_id = fields.Many2one('purchase.order', string="PO No.")
    partner_id = fields.Many2one('res.partner', string="PO Supplier", related="purchase_id.partner_id")
    purchase_date = fields.Datetime(string="PO Date", related="purchase_id.date_order")
    state = fields.Selection([('draft', 'Draft'),('confirmed','Confirmed'),('posted','Posted'),('cancel','Cancelled')], string="Status", default='draft')
    line_ids = fields.One2many('stock.receiving.line', 'receiving_id', string="Receipt Items")
    picking_id = fields.Many2one('stock.picking', string="Receiving Notes")
    is_po_completed = fields.Boolean(string="Is PO Completed", readonly=True)
    is_return = fields.Boolean(string="Is Return?")
    
    @api.model
    def create(self, vals):
        vals['name'] = self.env["ir.sequence"].search([('company_id', '=', self.company_id.id)]).next_by_code("stock.receiving.order")
        result = super(StockReceiving, self).create(vals)
        return result


    @api.onchange('purchase_id')
    def _onchange_purchase_id(self):
        if not self.purchase_id:
            return

        purchase = self.purchase_id

        self.partner_id = purchase.partner_id.id
        self.purchase_date = purchase.wipro_date
        self.ref = purchase.rfq

        order_lines = []
        for line in purchase.order_line:
            if line.product_id.type in ['product', 'consu']:

                # Create PO line
                order_lines.append((0, 0, {
                    'name':line.name,
                    'product_id':line.product_id.id,
                    'product_uom':line.product_uom.id,
                    'qty_issue':line.product_qty - line.qty_received_srb,
                    'company_id':line.company_id.id,
                    'line_id' : line.id,
                }))
        open('/opt/odoo16/logs/dudi.log','a+').write('\n' + "order_lines: " + str(order_lines))
        self.line_ids = order_lines

    # @api.multi
    def action_line_cancel(self):
        self.mapped('line_ids').unlink()
        self.state = 'cancel'
        return True

    # @api.multi
    def unlink(self):
        for r in self:
            r.mapped('line_ids').unlink()
        return super(StockReceiving, self).unlink()


    # @api.multi
    def action_confirm(self):
        self._create_picking()
        qty_total = 0
        for rec in self.line_ids:
            if rec.qty_receive > rec.qty_pending:
                raise UserError(_("Qty Receive can not more than Qty Pending"))
            rec.qty_received = rec.qty_receive
            qty_total += rec.qty_receive 

        if qty_total == 0:
            raise UserError(_("Qty Receive can not be empty"))
        self.state = 'confirmed'


    # @api.multi
    def action_cancel(self):
        for rec in self.line_ids:
            rec.qty_received = rec.qty_received - rec.qty_receive
            rec.qty_receive = 0
        self.picking_id.action_cancel()
        self.picking_id = False
        self.state = 'cancel'
        
        if self.is_po_completed:
            self.purchase_id.is_po_completed = False
            self.is_po_completed = False

    # @api.multi
    def set_to_draft(self):
        self.state = 'draft'

    # @api.multi
    def set_po_completed(self):
        self.purchase_id.is_po_completed = True
        self.is_po_completed = True


    # @api.multi
    def _create_picking(self):
        StockPicking = self.env['stock.picking']
        for order in self:
            res = order._prepare_picking()
            picking = StockPicking.create(res)
            self.picking_id = picking.id
            moves = order.line_ids._create_stock_moves(picking)
            # moves.force_assign() --DR

        return True



    @api.model
    def _prepare_picking(self):
        if self.purchase_id.purchase_name and self.purchase_id.purchase_name != self.purchase_id.name:
            origin_name = self.purchase_id.name + ' ('+self.purchase_id.purchase_name+')' 
        else:
            origin_name = self.purchase_id.name

        return {
            'receiving_id': self.id,
            'picking_type_id': self.purchase_id.picking_type_id.id,
            'partner_id': self.partner_id.id,
            'date': self.purchase_id.date_order,
            'origin': origin_name,
            'location_dest_id': self.purchase_id._get_destination_location(),
            'location_id': self.partner_id.property_stock_supplier.id,
            'company_id': self.company_id.id,
            'po_id': self.purchase_id.id
        }

    # @api.multi
    def print_rcv(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/accounting/receiving_bay_report?id=' + str(self.id)
        action['target'] = 'new'
        return action

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(StockReceiving,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'tree':
            res['arch'] = """
                <tree decoration-info="state == 'confirmed'" decoration-muted="state=='cancel'" decoration-success="state =='posted'" string="Receiving" delete="1">
                    <field name="name" colspan="1" modifiers="{&quot;readonly&quot;: [[&quot;state&quot;, &quot;in&quot;, [&quot;done&quot;]]], &quot;required&quot;: true}"/>
                    <field name="date"/>
                    <field name="ref"/>
                    <field name="state" modifiers="{&quot;readonly&quot;: true, &quot;required&quot;: true}"/>
                    <field name="company_id" options="{&quot;no_create&quot;: True}" can_create="true" can_write="true" modifiers="{&quot;required&quot;: true}"/>
                </tree>
           """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Receiving">
                    <field name="name" filter_domain="[('name','ilike',self)]" string="Receiving"/>
                    <filter string="Draft" domain="[('state','=','draft')]" help="Draft"/>
                    <filter string="Confirmed" domain="[('state','=','confirmed')]" help="Confirmed"/>
                    <filter string="Posted" domain="[('state','=','posted')]" help="Posted"/>
                    <field name="state"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res





class StockReceivingLine(models.Model):
    _name = 'stock.receiving.line'

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    receiving_id = fields.Many2one('stock.receiving', string="Receiving No.",ondelete='cascade')
    line_id = fields.Many2one('purchase.order.line', string="Order Line")
    product_id = fields.Many2one('product.product', string="Product")
    product_uom = fields.Many2one('uom.uom', string="UOM")
    name = fields.Char(string="Description")
    qty_issue = fields.Float(string="Qty Issue")
    qty_received = fields.Float(string="Qty Received")
    qty_pending = fields.Float(string="Qty Pending", compute='_compute_pending')
    qty_receive = fields.Float(string="Qty Receive")

    # @api.multi
    def write(self, vals):
        result = super(StockReceivingLine, self).write(vals)
        if self.qty_receive > self.qty_issue:
            raise UserError(_("Qty Receive can not more than Qty Issue"))
        return result


    @api.depends('qty_issue', 'qty_received')
    def _compute_pending(self):
        for r in self:
            qty_pending_round = r.qty_issue - r.qty_received
            r.qty_pending = round(qty_pending_round, 2)

    # @api.multi
    def _create_stock_moves(self, picking):
        moves = self.env['stock.move'].sudo()
        done = self.env['stock.move'].browse()
        for line in self:
            for val in line._prepare_stock_moves(picking):
                done += moves.create(val)
                open('/opt/odoo16/logs/stock_move.log','a+').write('\n\n'+str(val))
        return done


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
        price_unit = self.line_id._get_stock_move_price_unit()

        for move in self.line_id.move_ids.filtered(lambda x: x.state != 'cancel'):
            qty += move.product_qty

        template = {
            'name': self.line_id.name or '',
            'product_id': self.line_id.product_id.id,
            'product_uom': self.line_id.product_uom.id,
            'date': self.line_id.order_id.date_order,
            'date_expected': self.line_id.date_planned,
            'location_id': self.line_id.order_id.partner_id.property_stock_supplier.id,
            'location_dest_id': self.line_id.order_id._get_destination_location(),
            'picking_id': picking.id,
            'partner_id': self.line_id.order_id.dest_address_id.id,
            'move_dest_id': False,
            'state': 'draft',
            'purchase_line_id': self.line_id.id,
            'company_id': self.line_id.order_id.company_id.id,
            # 'price_unit': price_unit,
            'base_price': price_unit,
            'picking_type_id': self.line_id.order_id.picking_type_id.id,
            # 'group_id': self.line_id.order_id.group_id.id,
            # 'procurement_id': False,
            'origin': self.line_id.order_id.name,
            # 'route_ids': self.line_id.order_id.picking_type_id.warehouse_id and [(6, 0, [x.id for x in self.line_id.order_id.picking_type_id.warehouse_id.route_ids])] or [],
            'warehouse_id': self.line_id.order_id.picking_type_id.warehouse_id.id,
             # 2021.10.05 - tambahan 
            'account_analytic_id': self.line_id.account_analytic_id.id or False,
            'move_type': 'purchase.receipt',
            'product_service_id': self.line_id.product_id.categ_id.id or False,
            'product_categ_id': self.line_id.product_id.categ_id.id or False,
            'product_consignment': self.line_id.is_consignment or False,
            'product_supply_id': self.line_id.product_id.categ_id.property_stock_valuation_account_id.id or False,
            'product_input_id': self.line_id.product_id.categ_id.property_stock_account_input_categ_id.id or False,
            'receiving_line_id': self.id,
            'price_unit': self.line_id.price_unit,
            'sub_total': (self.line_id.price_subtotal) * (self.qty_receive/self.line_id.product_qty),
            'discount_value': self.line_id.discount_value,
            'discount_total': (self.line_id.discount_total) * (self.qty_receive/self.line_id.product_qty),
            'tax_discount': (self.line_id.tax_discount) * (self.qty_receive/self.line_id.product_qty),
            'discount_persen': self.line_id.discount_persen,
            'price_tax': (self.line_id.price_tax) * (self.qty_receive/self.line_id.product_qty),
            'price_total': (self.line_id.price_total) * (self.qty_receive/self.line_id.product_qty),
            'taxes_id': [(6, 0, self.line_id.taxes_id.ids)],
            'non_asset': (self.line_id.price_total) * (self.qty_receive/self.line_id.product_qty),
        }
        # 2021.10.05 - Koreksi 
        # template['price_unit'] = self.line_id.price_subtotal / self.line_id.product_qty
        template['base_price'] = (self.line_id.price_unit * self.line_id.product_qty) / self.line_id.product_qty
        # 2021.10.05 - Koreksi jika GRN untuk PO not GRN from HIS
        if not self.line_id.sync_id and not self.line_id.sync_id_api and self.line_id.price_tax >= 1:
            # template['price_unit'] = self.line_id.price_total / self.line_id.product_qty
            template['base_price'] = (self.line_id.price_unit * self.line_id.product_qty * 1.1) / self.line_id.product_qty


        open('/opt/odoo16/logs/stock_move.log','a+').write('\n\n'+str(template))
        # Fullfill all related procurements with this po line
        diff_quantity = self.qty_receive
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
        if float_compare(diff_quantity, 0.0,  precision_rounding=self.line_id.product_uom.rounding) > 0:
            template['product_uom_qty'] = diff_quantity
            # 2021.10.05 - Koreksi jurnal account.
            res.append(template)
        open('/opt/odoo16/logs/stock_move.log','a+').write('\n\n'+str(res))
        return res

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(StockReceivingLine,self).get_view(view_id=view_id,view_type=view_type, **options)        
        if view_type == 'form':
            res['arch'] = """
                <form string="Stock Receiving Line">
                    <sheet>
                        <group col="4">
                            <field name="receiving_id"/>
                            <field name="line_id" invisible="1"/>
                            <field name="product_id"/>
                            <field name="product_uom"/>
                            <field name="name"/>
                            <field name="company_id"/>
                        </group>
                        <group col="4">
                            <field name="qty_issue"/>
                            <field name="qty_received"/>
                            <field name="qty_pending"/>
                            <field name="qty_receive"/>
                        </group>
                        
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Stock Receiving Line">
                    <field name="receiving_id"/>
                    <field name="line_id"/>
                    <field name="product_id"/>
                    <field name="name"/>
                    <field name="company_id"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class StockPickingAsset(models.Model):
    _name = 'stock.picking.asset'

    def _default_today(self):
        today = tools.datetime.today()
        return 
    
    picking_id = fields.Many2one('stock.picking', string="Picking ID.", index=True)
    name = fields.Char(string="Asset Name")
    date = fields.Date(string="Date", default=_default_today)
    type = fields.Many2one('account.asset.category', string="Asset Type", index=True)
    subcategory_id = fields.Many2one('account.asset.subcategory', string='Sub Category', index=True)
    receipt_location = fields.Many2one('hr.department', string="Receipt Location", index=True)
    remarks = fields.Char(string="Remark")
    total = fields.Float(string="Asset Total Valuasi/Kapital", compute='_generate_total', store=True, readonly=True)
    qty = fields.Float(default=1.0, string="Asset Qty")
    value = fields.Float(string="Value Per Asset", compute='_generate_total', store=True, readonly=True)
    method_number = fields.Integer(default=0, string='Asset Depreciation')
    method_period = fields.Integer(default=0, string='Depreciation Every')
    credit_account_id = fields.Many2one('account.account', readonly=False, string='Credit Account')
    picking_asset_ids = fields.One2many('stock.picking.asset.line','picking_asset_id', string="Capitalization", store=True)
    account_asset_ids = fields.One2many('account.asset.asset','picking_asset_id', string="Final Asset", store=True, readonly=True)
    move_asset_ids = fields.One2many('account.move', 'stock_picking_asset_id', domain=[('journal_name','=','Asset Journal')], string='Journal Asset', store=True, readonly=True)

    @api.onchange('credit_account_id')
    def _onchange_account_id(self):
        if self.picking_id.move_lines:
            account_ids = [line.product_input_id.id for line in self.picking_id.move_lines]
            return {'domain': {'credit_account_id': [('id', 'in', account_ids)]}}
        
    @api.onchange('type')
    def _onchange_type(self):
        if self.type:
            self.method_number = self.type.method_number
            self.method_period = self.type.method_period
    
    # @api.multi
    def unlink(self):    
        query = self.env.cr.execute("""
            select dt.move_id, 
                sum(dt.capitalization) capitalization 
            from stock_picking_asset_line dt
            left join stock_picking_asset hd on dt.picking_asset_id=hd.id
            where hd.picking_id={picking_id}
                and hd.id = {id}
            group by dt.move_id 
        """.format(id=self.id, picking_id=self.picking_id.id))
        asset_line = self.env.cr.dictfetchall()
        
        for line in asset_line:
            move_id = line['move_id']
            capitalization = line['capitalization']
            
            # update non_asset unlink
            self.env.cr.execute("""
            UPDATE stock_move SET
                non_asset = non_asset + {capitalization},
                capitalization = capitalization - {capitalization}
            WHERE id = {move_id}
            """.format(move_id=move_id, capitalization=capitalization))
        return super(StockPickingAsset, self).unlink()

    @api.model
    def write(self, vals):
        result = super(StockPickingAsset, self).write(vals)
        
        query = self.env.cr.execute("""
            select dt.move_id, 
                sum(dt.capitalization) capitalization
            from stock_picking_asset_line dt
            left join stock_picking_asset hd on dt.picking_asset_id=hd.id
            where hd.picking_id={picking_id}
            group by dt.move_id 
            """.format(picking_id=self.picking_id.id))
        asset_line = self.env.cr.dictfetchall()
        

        for line in asset_line:
            move_id = line['move_id']
            capitalization = line['capitalization']
            
            # update non_asset write
            self.env.cr.execute("""
                UPDATE stock_move SET
                    non_asset = price_total - {capitalization},
                    capitalization = {capitalization}
                WHERE id = {move_id}
            """.format(
                move_id=move_id, 
                capitalization=capitalization))
        return result
    

    @api.depends('picking_asset_ids.capitalization','qty')
    def _generate_total(self):
        for record in self:
            record.total = 0
            for line in record.picking_asset_ids:
                if line.capitalization > line.move_id.price_total:
                    line.capitalization = 0
                # elif line.capitalization < 0:
                #     line.capitalization = 0
                    
                record.total += line.capitalization
            record.value = float(record.total) / float(record.qty)
    

    @api.onchange('qty')
    def onchange_val(self):
        self.value = 0
        if self.qty == 0:
            self.value = 0
        else:
            self.value = float(self.total) / float(self.qty)


    # @api.model
    # def write(self, vals):
    #     query = self.env.cr.execute("""
    #         select dt.move_id, 
    #             sum(dt.capitalization) capitalization 
    #         from stock_picking_asset_line dt
    #         left join stock_picking_asset hd on dt.picking_asset_id=hd.id
    #         where hd.picking_id={picking_id}
    #         group by dt.move_id 
    #         """.format(picking_id=self.picking_id.id))
        
    #     asset_line = self.env.cr.dictfetchall()
        
    #     for line in asset_line:
    #         move_id = line['move_id']
    #         capitalization = line['capitalization']
            
    #         # update non_asset create
    #         self.env.cr.execute("""
    #             UPDATE stock_move SET
    #                 non_asset = price_total - {capitalization},
    #                 capitalization = {capitalization}
    #             WHERE id = {move_id}
    #         """.format(move_id=move_id, capitalization=capitalization))


class StockPickingAssetLine(models.Model):
    _name = 'stock.picking.asset.line'
    _rec_name = 'picking_asset_id'
    
    def _default_today(self):
        today = tools.datetime.today()
        return today
    
    picking_asset_id = fields.Many2one('stock.picking.asset', string="Asset ID", ondelete='cascade')
    picking_id = fields.Many2one(related='picking_asset_id.picking_id', string="Picking ID", store=False)
    move_id = fields.Many2one('stock.move', string="Product Item")
    name = fields.Char(string="Description", store=True)
    qty = fields.Float(string="Qty", store=True)
    unit_price = fields.Float(string="Unit Price", store=True)
    sub_total = fields.Float(string="Sub Total", store=True)
    capitalization = fields.Float(string="Capitalization", default=False)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(StockPickingAssetLine,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'form':
            res['arch'] = """
                <form string="Stock Picking Asset Line">
                    <sheet>
                        <group>
                            <group>
                                <field name="picking_asset_id" />
                                <field name="picking_id" />
                                <field name="move_id" />
                                <field name="qty" />
                                <field name="unit_price"/>
                            </group>
                            <group>
                                <field name="sub_total" />
                                <field name="capitalization"/>
                            </group>
                        </group>
                    </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Stock Picking Asset" editable="bottom" >
                    <field name="picking_asset_id" invisible="1" />
                    <!--field name="picking_id" invisible="1" />
                    <field name="move_id" domain="[('picking_id','=', picking_id), ('asset_cip_id','=', False)]" />
                    <field name="name" readonly="1" />
                    <field name="qty"/>
                    <field name="unit_price" readonly="1" />
                    <field name="sub_total" readonly="1" />
                    <field name="capitalization"/-->
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # @api.onchange('move_id')
    # def get_move(self):
    #     self.move_id =  self.env['stock.move'].search([('picking_id', '=', self.picking_id.id)]).id

    @api.model
    def create(self, vals):
        result = super(StockPickingAssetLine, self).create(vals)
        
        query = self.env.cr.execute("""
            select dt.move_id, 
                sum(dt.capitalization) capitalization 
            from stock_picking_asset_line dt
            left join stock_picking_asset hd on dt.picking_asset_id=hd.id
            where hd.picking_id={picking_id}
            group by dt.move_id 
            """.format(picking_id=result.picking_id.id))
        asset_line = self.env.cr.dictfetchall()
        
        for line in asset_line:
            move_id = line['move_id']
            capitalization = line['capitalization']
            
            # update non_asset create
            self.env.cr.execute("""
                UPDATE stock_move SET
                    non_asset = price_total - {capitalization},
                    capitalization = {capitalization}
                WHERE id = {move_id}
            """.format(move_id=move_id, capitalization=capitalization))
        
        # for record in result:
        #     name = vals.get('name',record.name)

        #     record.write({
        #         'name': name
        #     })

        return result
    
    @api.model
    def write(self, vals):
        result = super(StockPickingAssetLine, self).write(vals)
        
        # for record in result:
        #     name = vals.get('name',record.name)

        #     record.write({
        #         'name': name
        #     })
        
        return result

    # @api.multi
    def name_get(self):
        return [(record.move_id, record.move_id.name) for record in self]
    

    @api.onchange('move_id')
    def onchange_item(self):
        price_unit = (self.move_id.price_total / self.move_id.product_uom_qty) if self.move_id.product_uom_qty != 0 else 0

        self.name = self.move_id.name
        self.qty = self.move_id.product_qty
        self.unit_price = price_unit
        self.sub_total =  (price_unit * self.move_id.product_uom_qty)
        # capitalization
        self.capitalization = self.move_id.price_total

    # @api.onchange('qty')
    # def onchange_qty(self):
    #     price_unit = (self.move_id.price_total / self.move_id.product_uom_qty) if self.move_id.product_uom_qty != 0 else 0
    #     qty = self.qty
    #     product_qty = self.move_id.product_qty

    #     self.sub_total = (price_unit * qty)
    #     self.unit_price = price_unit
    #     self.capitalization = (price_unit * qty)
        
    #     if qty > product_qty:
    #         self.qty = 0
    #         self.sub_total = 0
    #         self.capitalization = 0
    #         return {
    #             'warning': {
    #             'title': 'Odoo Warning',
    #             'message': ("Qty not more than " + str(self.move_id.product_qty))}
    #         }
            
    #     elif qty < 0:
    #         self.qty = 0
    #         self.sub_total = 0
    #         self.capitalization = 0
    #         return {
    #             'warning': {
    #             'title': "Odoo Warning",
    #             'message': "Qty not less than 0"}
    #         }
    

    # @api.onchange('capitalization','qty')
    # def onchange_cap(self):
    #     capitalization = self.capitalization
    #     price_subtotal = self.move_id.purchase_line_id.price_total
        
    #     if capitalization > price_subtotal:
    #         self.capitalization = 0
    #         return {
    #             'warning': {
    #             'title': 'Odoo Warning',
    #             'message': ("Capitalization not more than " + str(self.move_id.price_total))}
    #         }
            

# 2021.09.09 - Custom Lot/Batch
class StockProductionLot(models.Model):
    _inherit = 'stock.lot'

    order_line_id = fields.Many2one('eproc.order.line', string='Purchase Item', index=True)
    sync_date = sync.date
    sync_id_api = sync.id_api
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    
# 2021.09.09 - Custom PickingType
class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    sync_date = sync.date
    sync_id_api = sync.id_api
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    item_type = fields.Char(string="Item Type")
    # name = fields.Char(string="Item Type", translate=False)


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(StockPickingType,self).get_view(view_id=view_id,view_type=view_type, **options)        
        if view_type == 'form':
            res['arch'] = """
                <form string="Operation Types" delete="0">
                    <sheet>
                        <widget name="web_ribbon" title="Archived" bg_color="bg-danger" modifiers="{&quot;invisible&quot;: [[&quot;active&quot;, &quot;=&quot;, true]]}"/>
                        <label for="name"/>
                        <h1><field name="name" placeholder="e.g. Receptions" modifiers="{&quot;required&quot;: true}"/></h1>
                        <group name="first">
                            <group>
                                <field name="code" on_change="1" modifiers="{&quot;required&quot;: true}"/>
                                <field name="active" modifiers="{&quot;invisible&quot;: true}"/>
                                <field name="company_id" on_change="1" modifiers="{&quot;invisible&quot;: true, &quot;required&quot;: true}" can_create="true" can_write="true"/>
                                <field name="hide_reservation_method" modifiers="{&quot;invisible&quot;: true, &quot;readonly&quot;: true}"/>
                                <field name="sequence_id" can_create="true" can_write="true"/>
                                <field name="sequence_code" modifiers="{&quot;required&quot;: true}"/>
                                <field name="reservation_method" widget="radio" modifiers="{&quot;invisible&quot;: [[&quot;hide_reservation_method&quot;, &quot;=&quot;, true]], &quot;required&quot;: true}"/>
                                <label for="reservation_days_before" string="Reserve before scheduled date" modifiers="{&quot;invisible&quot;: [&quot;|&quot;, [&quot;code&quot;, &quot;=&quot;, &quot;incoming&quot;], [&quot;reservation_method&quot;, &quot;!=&quot;, &quot;by_date&quot;]]}"/>
                                <div class="o_row" modifiers="{&quot;invisible&quot;: [&quot;|&quot;, [&quot;code&quot;, &quot;=&quot;, &quot;incoming&quot;], [&quot;reservation_method&quot;, &quot;!=&quot;, &quot;by_date&quot;]]}">
                                    <span><field name="reservation_days_before" style="width: 23px;"/> days before/</span>
                                    <span><field name="reservation_days_before_priority" style="width: 23px;"/> days before when starred</span>
                                </div>
                            </group>
                            <group>
                                <field name="company_id" options="{'no_create': True}" on_change="1" modifiers="{&quot;required&quot;: true}" can_create="true" can_write="true"/>
                                <field name="return_picking_type_id" string="Returns Type" modifiers="{&quot;invisible&quot;: [[&quot;code&quot;, &quot;not in&quot;, [&quot;incoming&quot;, &quot;outgoing&quot;, &quot;internal&quot;]]]}" can_create="true" can_write="true"/>
                                <field name="create_backorder" modifiers="{&quot;required&quot;: true}"/>
                                <field name="show_operations" on_change="1" modifiers="{&quot;invisible&quot;: [[&quot;code&quot;, &quot;=&quot;, &quot;mrp_operation&quot;]]}"/>
                                <field name="show_reserved" modifiers="{&quot;invisible&quot;: [[&quot;code&quot;, &quot;!=&quot;, &quot;incoming&quot;]]}"/>
                            </group>
                        </group>
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="sync_type"/>
                                        <field name="sync_date"/>
                                        <field name="sync_id_api"/>
                                    </group>
                                    <group>
                                        <field name="sync_consol_id_main" modifiers="{&quot;readonly&quot;: true}"/>
                                        <field name="sync_consol_id_unit" modifiers="{&quot;readonly&quot;: true}"/>
                                        <field name="sync_consol_date" modifiers="{&quot;readonly&quot;: true}"/>
                                        <field name="trigger_create" modifiers="{&quot;invisible&quot;: true}"/>
                                        <field name="trigger_write" modifiers="{&quot;invisible&quot;: true}"/>
                                    </group>
                                </group>
                                <group>
                                    <group string="Packs and Lots" groups="stock.group_tracking_lot,stock.group_production_lot">
                                        <field name="show_entire_packs" groups="stock.group_tracking_lot"/>
                                        <field name="use_create_lots" groups="stock.group_production_lot"/>
                                        <field name="use_existing_lots" groups="stock.group_production_lot"/>
                                    </group>
                                    <group string="Locations">
                                        <field name="default_location_src_id" attrs="{'required': [('code', '=', 'internal')]}"/>
                                        <field name="default_location_dest_id" attrs="{'required': [('code', 'in', ('internal', 'incoming'))]}"/>
                                    </group>
                                </group>
                            </page>
                        </notebook>
                        <group name="second">
                            <!-- As this group will be hidden without multi_loccation, you will not be able to create a
                                picking type with the code 'Internal', which make sense, but as the field 'code' on picking
                                types can't be partially hidden, you can still select the code internal in the form view -->
                            </group>
                    </sheet>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res



class StockScrap(models.Model):
    _inherit = 'stock.scrap'
    # _inherit = ['stock.scrap','mail.thread', 'ir.needaction_mixin']

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_is_arcus = sync.is_arcus
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    transaction_date = fields.Date(string="Trans Date")
    transaction_datetime = fields.Datetime(string="Trans Datetime")
    categ_id = fields.Many2one('product.category', string="Product Category", readonly=False, store=True)
    service_categ_id = fields.Many2one('product.category', string="Service Category", readonly=False, store=True)
    
    cost = fields.Float(string="HIS Cost Unit", store=True)
    cost_total = fields.Float(string="HIS Cost Total", store=True)
    odoo_cost = fields.Float(string="Odoo Cost Unit", store=True)
    odoo_cost_total = fields.Float(string="Odoo Cost Total", store=True)

    updated_date = fields.Boolean(string="Update Date", readonly=True, default=False)
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env['res.company']._company_default_get('stock.move'), index=True, required=True)
    transaction_type = fields.Selection([('scrap', 'Scrap'), ('consumption', 'Consumption'), ('adjustment_issue', 'Adjustment Issue'), ('adjustment_receipt', 'Adjustment Receive'), ('prepared_item','Prepared Item'), ('prepared_receipt','Prepared Receipt'), ('stock_entry','Physical Stock Entry')], default='consumption', string='Scrap Type')
    # transaction_type = fields.Char(string="Scrap Type", default='SC', store=True, index=True)
    trans_type = fields.Char(string="Trans Type", default='SC', store=True, index=True)
    trans_type_name = fields.Char(string="Trans Type Name", store=True, index=True)
    batch_no = fields.Char(string="Batch No")
    batch_id = fields.Many2one("stock.lot", string="Batch ID")
    expiry_date = fields.Date(string="Expiry Date")

    api_post_timestamp = fields.Datetime(string="Timestamp API", readonly=True)
    api_post_status = fields.Selection([('done', 'Done'), ('failed', 'Failed')], string='Status API', readonly=True)
    api_post_payload = fields.Char(string="Payload API", readonly=True)
    api_post_response = fields.Char(string="Response API", readonly=True)
    no_stock = fields.Boolean(string="No Stock", default=False, readonly=True, index=True)
    admission_id = fields.Many2one('sale.order', string="Admission No.", readonly=True, index=True)
    is_takeout = fields.Boolean(string="Takeout", default=False)

    # auto compute relation to stock.picking and stock.move for valuation price
    picking_id = fields.Many2one('stock.picking', string="Stock Picking")
    picking_created = fields.Boolean(string="Stock Picking Created", default=False, readonly=True, index=True)
    move_id = fields.Many2one('stock.move', string="Stock Move")
    move_created = fields.Boolean(string="Stock Move Created", readonly=True)
    procurement_group_id = fields.Many2one('procurement.group', string="Procurement Group")
    procurement_created = fields.Boolean(string="Procurement Created", default=False)
    date_expected = fields.Datetime(string="Expected Date", default=fields.Datetime.now)

    status_sc = fields.Char(string="Status SC",index=True,store=True)

    # @api.multi
    def query_cost(self):

        print ("1")
        self.env.cr.execute("""
            UPDATE stock_scrap as s set 
            transaction_datetime = s.transaction_datetime - (interval '7 hour 40 minute'), 
            updated_date = True 
            where s.updated_date is null
            """)

        self.env.cr.execute("""
            UPDATE stock_scrap
            set transaction_date = transaction_datetime + (interval '7 hour 40 minute') 
            where transaction_date is null""")

        # self.env.cr.execute("""
            # UPDATE stock_scrap
            # set cost = (select price.cost from product_price_history AS price where price.product_id = stock_scrap.product_id and price.cost > 0 order by datetime desc limit 1) where cost is null""")
        
        # self.env.cr.execute("""
            # UPDATE stock_scrap 
            # set cost = (select price.cost from product_price_history AS price where price.product_id = stock_scrap.product_id and price.cost > 0 order by datetime desc limit 1) where cost = 0""")
        
        self.env.cr.execute("""
            UPDATE stock_scrap 
            set cost_total = cost * scrap_qty 
            where cost_total is null""")

        self.env.cr.execute("""
            UPDATE stock_scrap as sc
            set categ_id = (
                select categ_id from product_template 
                where id = (select product_tmpl_id from product_product where id = sc.product_id)
            ) where categ_id is null""")

        self.env.cr.execute("""
            UPDATE stock_scrap
            set service_categ_id = (
                select (case when parent_id is not null then parent_id else id end) 
                from product_category 
                where id = (
                    select categ_id from product_template 
                    where id = (select product_tmpl_id 
                        from product_product 
                        where id = stock_scrap.product_id))) 
            where service_categ_id is null""")

        self.env.cr.execute("""
            UPDATE stock_scrap
            set service_categ_id = (select (case when parent_id is not null then parent_id else id end)
            from product_category
            where id = stock_scrap.service_categ_id)""")

        self.env.cr.execute("""
            UPDATE stock_scrap set cost_total = cost_total * -1 
            where cost_total > 0 
            and trans_type in ('AR','SE','PE') """)

        self.env.cr.execute("""
            UPDATE stock_scrap set cost = cost * -1 
            where cost_total > 0 
            and trans_type in('AR', 'SE','PE') """)

        self.env.cr.execute("""
            UPDATE stock_scrap set scrap_location_id = location_id 
            where location_id <> 4 
            and trans_type in ('AR','SE','PE') """)

        self.env.cr.execute("""
            UPDATE stock_scrap set location_id = 4 
            where scrap_location_id <> 4 
            and trans_type in ('AR','SE','PE') """)


    # @api.multi
    def stock_valuation(self):
        for record in self:
            if record.sync_id_api:
                print("Do something...")
                # create procurement
                if record.procurement_created is not True:
                    procurement_code = record.company_id.company_code + '/' + record.origin
                    group = self.env['procurement.group'].search([('name','=', procurement_code)], limit=1)
                    if not group:
                        group = self.env['procurement.group'].create({'name': procurement_code, 'move_type': 'direct'})
                    if group:
                        record.procurement_group_id = group.id 
                        record.procurement_created = True 

                # create picking 
                if record.procurement_created and record.picking_created is not True:
                    data = {}
                    if record.trans_type == 'SC':
                        trans_type = 'stock.scrap'
                    elif record.trans_type == 'AI':
                        trans_type = 'adjustment.issue'
                    elif record.trans_type == 'AR':
                        trans_type = 'adjustment.receipt'
                    elif record.trans_type == 'PI':
                        trans_type = 'prepared.item'
                    elif record.trans_type == 'SE':
                        trans_type = 'prepared.receipt'
                    elif record.trans_type == 'PE':
                        trans_type = 'physical.entry'
                    else:
                        trans_type = 'stock.breakage'

                    data['picking_type_id'] = self.env['stock.picking.type'].search([('sync_id_api','=', trans_type),('sync_type','=', record.sync_type)], limit=1).id or None
                    data['location_id'] = record.location_id.id if record.trans_type != 'AR' else record.scrap_location_id.id 
                    data['location_dest_id'] = record.scrap_location_id.id if record.trans_type != 'AR' else record.location_id.id 
                    data['group_id'] = record.procurement_group_id.id 
                    data['company_id'] = record.company_id.id 
                    data['origin'] = record.origin
                    data['min_date'] = record.transaction_date
                    data['max_date'] = record.transaction_date
                    data['date'] = record.transaction_date
                    data['date_done'] = record.transaction_date
                    data['date_move'] = record.transaction_date
                    data['partner_id'] = record.admission_id.partner_id.id if record.admission_id else None
                    data['move_type'] = 'direct'
                    data['note'] = record.transaction_type 
                    data['state'] = 'waiting'
                    data['sync_id_api'] = 'STOCK.' + str(record.sync_id_api)
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
                    if record.trans_type == 'SC':
                        trans_type = 'stock.scrap'
                    elif record.trans_type == 'AI':
                        trans_type = 'adjustment.issue'
                    elif record.trans_type == 'AR':
                        trans_type = 'adjustment.receipt'
                    elif record.trans_type == 'PI':
                        trans_type = 'prepared.item'
                    elif record.trans_type == 'SE':
                        trans_type = 'prepared.receipt'
                    elif record.trans_type == 'PE':
                        trans_type = 'physical.entry'
                    else:
                        trans_type = 'stock.breakage'

                    data['picking_type_id'] = self.env['stock.picking.type'].search([('sync_id_api','=', trans_type),('sync_type','=', record.sync_type)], limit=1).id or None
                    data['location_id'] = record.location_id.id if record.trans_type != 'AR' else record.scrap_location_id.id 
                    data['location_dest_id'] = record.scrap_location_id.id if record.trans_type != 'AR' else record.location_id.id 
                    data['group_id'] = record.procurement_group_id.id 
                    data['picking_id'] = record.picking_id.id 
                    data['company_id'] = record.company_id.id 
                    data['origin'] = record.origin
                    data['name'] = record.name
                    data['date'] = record.transaction_date
                    data['date_expected'] = record.transaction_date
                    data['partner_id'] = record.admission_id.partner_id.id if record.admission_id else None
                    data['product_id'] = record.product_id.id 
                    data['product_uom_qty'] = abs(record.scrap_qty)
                    #data['product_qty'] = abs(record.scrap_qty)
                    data['product_uom'] = record.product_id.uom_id.id 
                    data['price_unit'] = record.odoo_cost if record.odoo_cost != 0 else record.cost
                    data['cost_unit'] = record.odoo_cost if record.odoo_cost != 0 else record.cost
                    data['lot_id'] = record.batch_id.id or None 
                    data['note'] = record.transaction_type 
                    data['scrap_id'] = record.id 
                    data['procure_method'] = 'make_to_stock'
                    data['state'] = 'waiting'
                    data['sync_id_api'] = 'STOCK.' + str(record.sync_id_api)
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


    # @api.multi
    def do_scrap(self):
        for scrap in self:
            if scrap.trans_type == 'AI':
                scrap.transaction_type = 'adjustment_issue'
            if scrap.trans_type == 'AR':
                scrap.transaction_type = 'adjustment_receipt'
            if scrap.trans_type == 'PI':
                scrap.transaction_type = 'prepared_item'
            if scrap.trans_type == 'SE':
                scrap.transaction_type = 'prepared_receipt'
            if scrap.trans_type == 'PE':
                scrap.transaction_type = 'physical.entry'

            if scrap.company_id.sync_api_stock_active:
                scrap.stock_valuation()

            # 2021.09.02 disable stock move auto_done (agar tidak masuk account.move)
            return

            # moves = scrap._get_origin_moves() or self.env['stock.move']
            # move = self.env['stock.move'].create(scrap._prepare_move_values())           

            # if move.product_id.type == 'product' and move.location_id.usage == 'internal':
            #     quants = self.env['stock.quant'].quants_get_preferred_domain(move.product_qty, move, domain=[('qty', '>', 0),('package_id', '=', self.package_id.id)], preferred_domain_list=scrap._get_preferred_domain())
            #     if any([not x[0] for x in quants]):
            #       move.write({'no_stock': True})
            #       return
            #         # raise UserError(_('You cannot scrap a move without having available stock for %s. You can correct it with an inventory adjustment.') % move.product_id.name)
            #     self.env['stock.quant'].quants_reserve(quants, move)
            # move.write({'company_id': scrap.company_id.id, 'date': scrap.date_expected})
            # move.action_done()
            # scrap.write({'move_id': move.id, 'state': 'done'})
            # moves.recalculate_move_state()
            # scrap.move_id.tglproses = scrap.transaction_date
            # now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # transactionDate = tools.datetime.strptime(scrap.date_expected, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            
            # expired_date = ""
            # if hasattr(scrap.lot_id, 'life_date'):
            #     if(scrap.lot_id.life_date):
            #         expired_date = tools.datetime.strptime(scrap.lot_id.life_date, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            # hit_api = False

            # if self.env.user.company_id.sync_api_active == True:
            #     if scrap.transaction_type == 'scrap':
            #         url = self.env.user.company_id.his_api_url + '/odoo/inventories/Scrap'
            #         hit_api = True
            #     elif scrap.transaction_type == 'consumption':
            #         url = self.env.user.company_id.his_api_url + '/odoo/inventories/StoreConsumption'
            #         hit_api = True
            #     # elif scrap.transaction_type == 'adjustment_issue':
            #     #     url = self.env.user.company_id.his_api_url + '/odoo/inventories/StockAdjustmentIssue'
            #     #     hit_api = True
            #     # elif scrap.transaction_type == 'adjustment_receipt':
            #     #     url = self.env.user.company_id.his_api_url + '/odoo/inventories/StockAdjustmentReceive'
            #     #     hit_api = True

            #     if hit_api == True:
            #         headers = {'Content-Type': 'application/json', 'x-api-key' : self.env.user.company_id.his_api_key}
            #         payload = {
            #             "head" : {
            #                 "siteId": scrap.company_id.sync_type,
            #                 "roomId": str(scrap.location_id.sync_id_api) or "",
            #                 "remark": "",
            #                 "transactionNumber": str(scrap.name),
            #                 "transactionDate": transactionDate or "",
            #             },
            #             "detail" : [{
            #                 "itemId": str(scrap.product_id.sync_id_api) or "",
            #                 "batchNumber": str(scrap.lot_id.name) or "",
            #                 "expiredDate": expired_date,
            #                 "qty": int(scrap.scrap_qty),
            #                 "uomId": str(scrap.product_uom_id.sync_id_api),
            #                 "uomName": str(scrap.product_uom_id.name),
            #                 "cogs": int(scrap.cost) or 0
            #             }]
            #         }

            #         open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n' + str(headers) + '\n' + str(payload))
            #         response_json = requests.post(url=url, headers=headers, json=payload, verify=False)
            #         open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n' + str(response_json))
            #         json_resp = response_json.json()

            #         api_post_status = 'failed'

            #         if 'Status' in json_resp:
            #             if json_resp['Status'] == True:
            #                 api_post_status = 'done'

            #         data = {
            #             'api_post_payload': payload,
            #             'api_post_response': json_resp,
            #             'api_post_timestamp': now,
            #             'api_post_status': api_post_status,
            #         }

            #         write_result = super(StockScrap, self).write(data)
        return True


    # @api.multi
    def scraping(self):
        print ("DO SCRAPING")
        # if self.env.company.sync_api_active == True:
        #     for scrap in self:
        #         if scrap.transaction_type == 'scrap':
        #             url = self.env.company.his_api_url + '/odoo/inventories/Scrap'
        #             hit_api = True
        #         elif scrap.transaction_type == 'consumption':
        #             url = self.env.company.his_api_url + '/odoo/inventories/StoreConsumption'
        #             hit_api = True
        #         # elif scrap.transaction_type == 'adjustment_issue':
        #         #     url = self.env.company.his_api_url + '/odoo/inventories/StockAdjustmentIssue'
        #         #     hit_api = True
        #         # elif scrap.transaction_type == 'adjustment_receipt':
        #         #     url = self.env.company.his_api_url + '/odoo/inventories/StockAdjustmentReceive'
        #         #     hit_api = True
        #         now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        #         transactionDate = tools.datetime.strptime(scrap.date_expected, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%S.%fZ')
                
        #         expired_date = ""
        #         if hasattr(scrap.lot_id, 'life_date'):
        #             if(scrap.lot_id.life_date):
        #                 expired_date = tools.datetime.strptime(scrap.lot_id.life_date, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%S.%fZ')

        #         if hit_api == True:
        #             headers = {'Content-Type': 'application/json', 'x-api-key' : self.env.company.his_api_key}
        #             payload = {
        #                 "head" : {
        #                     "siteId": scrap.company_id.sync_type,
        #                     "roomId": str(scrap.location_id.sync_id_api) or "",
        #                     "remark": "",
        #                     "transactionNumber": str(scrap.name),
        #                     "transactionDate": transactionDate or "",
        #                 },
        #                 "detail" : [{
        #                     "itemId": str(scrap.product_id.sync_id_api) or "",
        #                     "batchNumber": str(scrap.lot_id.name) or "",
        #                     "expiredDate": expired_date,
        #                     "qty": int(scrap.scrap_qty),
        #                     "uomId": str(scrap.product_uom_id.sync_id_api),
        #                     "cogs": int(scrap.cost) or 0
        #                 }]
        #             }

        #             open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n' + str(headers) + '\n' + str(payload))
        #             response_json = requests.post(url=url, headers=headers, json=payload, verify=False)
        #             open('/opt/odoo16/logs/api_odoo_api.log', 'a+').write('\n' + str(response_json))
        #             json_resp = response_json.json()

        #             api_post_status = 'failed'

        #             if 'Status' in json_resp:
        #                 if json_resp['Status'] == True:
        #                     api_post_status = 'done'

        #             data = {
        #                 'api_post_payload': payload,
        #                 'api_post_response': json_resp,
        #                 'api_post_timestamp': now,
        #                 'api_post_status': api_post_status,
        #             }

        #             write_result = super(StockScrap, self).write(data)


    @api.model
    def create(self, vals):
        if 'name' not in vals or vals['name'] == ('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('stock.scrap') or ('New')
        scrap = super(StockScrap, self).create(vals)
        return scrap


    @api.model
    def _sync_store_consumption(self, sync_type='1', date=False):
         sync_ids = {int(record.sync_id): record.id for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)])}
         sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
         data = []
         if not date:
            date ='' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
         # date = '2019-01-25'
         store_consumption = """
            SELECT
              a.TransType 'trans_type',
              a.ConsumptionNo 'origin',
              a.ConsumptionNo 'name',
              a.ConsumptionDate 'transaction_datetime',
              a.ConsumptionDate 'date_expected',
              a.ConsumptionDate 'create_date',
              a.ItemID 'sync_id',
              a.ItemID 'product_id',
              a.HospDeptId 'location_id',
              4 'scrap_location_id',
              a.BatchNo 'lot_id',
              a.UoMID 'product_uom_id',
              a.Quantity 'scrap_qty',
              a.UEPR 'cost',
              a.Total 'cost_total',
              'draft' 'state'
          FROM dbo.VRP_OdooAdjustmentIssue a
          WHERE convert(varchar(10), a.ConsumptionDate, 121) = '%s'
          """ % (date)
         values = ''
         data += sync.get_data(sync.servers.get(sync_type), store_consumption)
         print (data)
         if not data:
            print ("No data available")
            return 
         fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and 'ids' not in key and self._fields[key].required == True and self._fields[key].store == True)
         # columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
         columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
         fields_without_id += columns
         columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
         fields = fields_without_id + ('id',)
         if columns:
            columns += ('id',)
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
         #uom_id = self.env.ref('product.product_uom_categ_unit').id
         new_sync_ids = []
         for object in data:
             new_sync_ids += [object['sync_id']]
             for value in default_values:
                 if value in object:
                    continue
                 object[value] = default_values[value]
             product_id = object['product_id']
             object['product_id'] = self.env['product.product'].search([('sync_id', '=', object['product_id']), ('sync_type' ,'=', sync_type), ('sync_is_service' ,'=', False), ('sync_is_package' ,'=', False)], limit=1).id or None
             object['uom'] = self.env['product.product'].search([('sync_id', '=', object['product_id']), ('sync_type' ,'=', sync_type), ('sync_is_service' ,'=', False), ('sync_is_package' ,'=', False)], limit=1).uom_id.id or None
             if not object['product_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + " product.template with sync_id %s and sync_type %s doesn't exist" % (product_id, sync_type))
                return
             object['product_uom_id'] = self.env['uom.uom'].search([('sync_id', '=', object['product_uom_id']), ('sync_type' ,'=', sync_type)], limit=1).id or object['uom']
             object['location_id'] = self.env['stock.location'].search([('sync_id', '=', object['location_id']), ('sync_type' ,'=', sync_type)], limit=1).id or self.env['stock.location'].search([('sync_id', '=', 1), ('sync_type' ,'=', sync_type)], limit=1).id
             object['lot_id'] = self.env['stock.production.lot'].search([('name', '=', object['lot_id'])], limit=1).id or None
             # object['workorder_id'] = None
             # object['payer_id'] = object['payer_id'].id
             # object['project_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['project_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'bed')], limit=1).id or None
             # if object['sync_id'] in sync_ids:
             #    object['id'] = sync_ids[object['sync_id']]
             # else:
             object['id'] = 'DEFAULT'
             object['sync_date'] = now
             object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].search([('sync_type', '=', sync_type)], limit=1).id
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
         query = "INSERT into stock_scrap %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
         print (query.encode('utf8'))
         self.env.cr.execute(query)


    @api.model
    def _sync_store_consumption_manual(self, sync_type='1', date_start='2019-01-01', date_end='2019-01-01'):
         sync_ids = {int(record.sync_id): record.id for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)])}
         sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
         data = []
         # if not date:
           # date ='' + (tools.datetime.now() + tools.timedelta(hours=7) - tools.timedelta(days=1)).strftime('%Y-%m-%d')
         # date = '2019-01-25'
         store_consumption = """
           SELECT
              a.TransType 'trans_type',
              a.ConsumptionNo 'origin',
              a.ConsumptionNo 'name',
              a.ConsumptionDate 'transaction_datetime',
              a.ConsumptionDate 'date_expected',
              a.ConsumptionDate 'create_date',
              a.ItemID 'sync_id',
              a.ItemID 'product_id',
              a.HospDeptId 'location_id',
              4 'scrap_location_id',
              a.BatchNo 'lot_id',
              a.UoMID 'product_uom_id',
              a.Quantity 'scrap_qty',
              a.UEPR 'cost',
              a.Total 'cost_total',
              'draft' 'state'
          FROM dbo.VRP_OdooAdjustmentIssue a
          -- WHERE convert(varchar(10), a.ConsumptionDate, 121) in ('2020-06-20','2020-06-21')
          WHERE convert(varchar(10), a.ConsumptionDate, 121) >= '%s' and convert(varchar(10), a.ConsumptionDate, 121) <= '%s'
          """ % (date_start, date_end)
         values = ''
         data += sync.get_data(sync.servers.get(sync_type), store_consumption)
         print (data)
         if not data:
            print ("No data available")
            return
         fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and 'ids' not in key and self._fields[key].required == True and self._fields[key].store == True)
         # columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
         columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
         fields_without_id += columns
         columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
         fields = fields_without_id + ('id',)
         if columns:
            columns += ('id',)
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
         #uom_id = self.env.ref('product.product_uom_categ_unit').id
         new_sync_ids = []
         for object in data:
             new_sync_ids += [object['sync_id']]
             for value in default_values:
                 if value in object:
                    continue
                 object[value] = default_values[value]
             product_id = object['product_id']
             object['product_id'] = self.env['product.product'].search([('sync_id', '=', object['product_id']), ('sync_type' ,'=', sync_type), ('sync_is_service' ,'=', False), ('sync_is_package' ,'=', False)], limit=1).id or None
             object['uom'] = self.env['product.product'].search([('sync_id', '=', object['product_id']), ('sync_type' ,'=', sync_type), ('sync_is_service' ,'=', False), ('sync_is_package' ,'=', False)], limit=1).uom_id.id or None
             if not object['product_id']:
                open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(tools.datetime.now()) + " product.template with sync_id %s and sync_type %s doesn't exist" % (product_id, sync_type))
                return
             object['product_uom_id'] = self.env['product.uom'].search([('sync_id', '=', object['product_uom_id']), ('sync_type' ,'=', sync_type)], limit=1).id or object['uom']
             object['location_id'] = self.env['stock.location'].search([('sync_id', '=', object['location_id']), ('sync_type' ,'=', sync_type)], limit=1).id or self.env['stock.location'].search([('sync_id', '=', 1), ('sync_type' ,'=', sync_type)], limit=1).id
             object['lot_id'] = self.env['stock.production.lot'].search([('name', '=', object['lot_id'])], limit=1).id or None
             # object['workorder_id'] = None
             # object['payer_id'] = object['payer_id'].id
             # object['project_id'] = self.env['account.analytic.account'].search([('sync_id', '=', object['project_id']), ('sync_type', '=', sync_type), ('sync_wipro_type', '=', 'bed')], limit=1).id or None
             # if object['sync_id'] in sync_ids:
             #    object['id'] = sync_ids[object['sync_id']]
             # else:
             object['id'] = 'DEFAULT'
             object['sync_date'] = now
             object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].search([('sync_type', '=', sync_type)], limit=1).id
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
         query = "INSERT into stock_scrap %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
         print (query.encode('utf8'))
         self.env.cr.execute(query)


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(StockScrap,self).get_view(view_id=view_id,view_type=view_type, **options)        
        if view_type == 'tree':
            res['arch'] = """
                <tree decoration-info="state == 'draft'" decoration-success="state == 'done'" create="false" delete="false" edit="false">
                    <field name="origin"/>
                    <field name="trans_type"/>
                    <field name="transaction_date"/>
                    <field name="product_id" on_change="1" can_create="true" can_write="true" modifiers="{'readonly': [['state', 'in', ['done']]], 'required': true}"/>
                    <field name="scrap_qty" modifiers="{'readonly': [['state', 'in', ['done']]], 'required': true}"/>
                    <field name="product_uom_id" string="UoM" can_create="true" can_write="true" modifiers="{'readonly': [['state', 'in', ['done']]], 'required': true}"/>
                    <field name="location_id" can_create="true" can_write="true" modifiers="{'readonly': [['state', 'in', ['done']]], 'required': true}"/>
                    <field name="cost_total"/>
                    <field name="odoo_cost_total"/>
                    <field name="state" invisible="1" modifiers="{'tree_invisible': true}"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <search string="Search COGS...">
                    <filter name="draft" string="Draft" domain="[('state','=', 'draft')]" help="Draft"/>
                    <filter name="done" string="Done" domain="[('state','=', 'done')]" help="Done"/>
                    <separator/>
                    <filter name="SC" string="Store Consumption" domain="[('trans_type','=', 'SC')]" help="Store Consumption"/>
                    <filter name="AI" string="Adjustment Issue" domain="[('trans_type','=', 'AI')]" help="Adjustment Issue"/>
                    <filter name="AR" string="Adjustment Receipt" domain="[('trans_type','=', 'AR')]" help="Adjustment Receipt"/>
                    <filter name="LB" string="Loss Breakage" domain="[('trans_type','=', 'LB')]" help="Loss Breakage"/>
                    <filter name="BR" string="Breakage" domain="[('trans_type','=', 'BR')]" help="Breakage"/>
                    <filter name="PI" string="Prepared Item" domain="[('trans_type','=', 'PI')]" help="Prepared Item"/>
                    <filter name="SE" string="Prepared Receipt" domain="[('trans_type','=', 'SE')]" help="Prepared Receipt"/>
                    <filter name="PE" string="Physical Entry" domain="[('trans_type','=', 'PE')]" help="Physical Entry"/>
                    <separator/>
                    <filter name="takeout" string="Takeout" domain="[('is_takeout','=', 1)]" help="Takeout"/>
                    <filter name="not_takeout" string="Not Takeout" domain="[('is_takeout','!=', 1)]" help="Not Takeout"/>
                    <separator/>
                    <field name="origin"/>
                    <field name="product_id"/>
                    <field name="service_categ_id"/>
                    <field name="categ_id"/>
                    <field name="location_id"/>
                    <field name="scrap_location_id"/>
                    <field name="admission_id"/>
                    <group expand="0" string="Group By">
                        <filter string="Status" domain="[]" context="{'group_by':'state'}"/>
                        <filter string="Trans Type" domain="[]" context="{'group_by':'trans_type'}"/>
                        <filter string="Trans Date" domain="[]" context="{'group_by':'transaction_date'}"/>
                        <filter string="Origin" domain="[]" context="{'group_by':'origin'}"/>
                    </group>
                </search>"""
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res







# # 2021.09.09 - Custom Stock Inventory (Not Used)
# class StockInventory(models.Model):
#     _inherit = 'stock.inventory'
#     _order = 'date desc'

#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

#     api_post_timestamp_min = fields.Datetime(string="Timestamp API Minus", readonly=True)
#     api_post_status_min = fields.Selection([('done', 'Done'), ('failed', 'Failed')], string='Status API Minus', readonly=True)
#     api_post_payload_min = fields.Char(string="Payload API Minus", readonly=True)
#     api_post_response_min = fields.Char(string="Response API Minus", readonly=True)
#     api_post_timestamp = fields.Datetime(string="Timestamp API Plus", readonly=True)
#     api_post_status = fields.Selection([('done', 'Done'), ('failed', 'Failed')], string='Status API Plus', readonly=True)
#     api_post_payload = fields.Char(string="Payload API Plus", readonly=True)
#     api_post_response = fields.Char(string="Response API Plus", readonly=True)

#     transaction_number = fields.Char(string="Transaction Number", readonly=True, compute='_trans_number', store=True)
#     accounting_date = fields.Date(required=True)

#     rack_id = fields.Many2one("master.rack",string="Rack")
#     shelf_id = fields.Many2one("master.shelf",string="Shelf")

#     # @api.one
#     def _trans_number(self):
#         self.transaction_number = "ADJ/" + str(self.id).zfill(5)







# 2021.09.09 - Stock Bulk Closing 
# untuk generate Average cost & Valuaton Inventory based on Stock Moving PRC, SO & SC
class StockBulkClosingWizard(models.TransientModel):
    _name = 'stock.bulk.closing.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    date_start = fields.Date(string="Date Start", store=True, index=True)
    date_end = fields.Date(string="Date End", store=True, index=True)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(StockBulkClosingWizard,self).get_view(view_id=view_id,view_type=view_type, **options)        
        if view_type == 'form':
            res['arch'] = """
                <form string="Stock Scrap Bulk Closing">
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
                    <button name="bulk_update_general" string="Update HIS WAC Non Medical" type="object" class="oe_highlight"/>
                    <button name="bulk_update" string="Update AVG Cost" type="object" class="oe_highlight"/>
                    <button name="bulk_valuation" string="Compute Valuation" type="object" class="oe_highlight" invisible="1" />
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
        # date_start = tools.datetime.strptime(self.date_start, '%Y-%m-%d')
        # date_end = tools.datetime.strptime(self.date_end, '%Y-%m-%d')
        date_start = (self.date_start).strftime('%Y-%m-%d')
        date_end = (self.date_end).strftime('%Y-%m-%d')

 
        #  update WAC from Product Cost History
        open('/opt/odoo16/logs/stock_bulk_closing_non_medical.log', 'a+').write(str('\nStart update stock.scrap'))
        query = """
            update stock_scrap as sol set 
                cost = (case 
                    when coalesce(pcp.cost,0) = 0 then sol.cost 
                    else coalesce(pcp.cost,0) end),
                cost_total = (
                    (case 
                        when coalesce(pcp.cost,0) = 0 then sol.cost 
                        else coalesce(pcp.cost,0) 
                    end) * sol.scrap_qty),
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            from product_product pp 
            inner join product_template pt on pt.id=pp.product_tmpl_id
            inner join product_price_history pcp on pcp.product_id=pp.id
            where pp.id = sol.product_id
                and date(pcp.datetime) = date('{date_end}')
                and sol.company_id = {company_id}
                and sol.transaction_date >= '{date_start}'
                and sol.transaction_date <= '{date_end}'
                and (
                    left(pt.default_code, 3) = 'BRG' or 
                    left(sol.origin, 3) in ('PMB','AJB','SOB')
                )
        """.format(
            company_id=company_id,
            date_start=date_start, 
            date_end=date_end,
            user_id=self.env.user.id 
        )
        open('/opt/odoo16/logs/stock_bulk_closing_non_medical.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


        # Update by code product
        if self.company_id.company_code == 'MHSB':
            query = """
            with product_price_history_temp as (
                select distinct on (pt2.default_code)
                    pt2.default_code,
                    pcp.cost,
                    pcp.datetime
                from product_price_history pcp
                inner join product_product pp2
                    on pp2.id = pcp.product_id
                inner join product_template pt2
                    on pt2.id = pp2.product_tmpl_id
                where date(pcp.datetime) = date('{date_end}')
                order by pt2.default_code, pcp.datetime desc
            )

            update stock_scrap sol
            set
                cost = case
                    when coalesce(pcp.cost, 0) = 0 then sol.cost
                    else pcp.cost
                end,
                cost_total = (
                    case
                        when coalesce(pcp.cost, 0) = 0 then sol.cost
                        else pcp.cost
                    end * sol.scrap_qty
                ),
                write_date = CURRENT_TIMESTAMP,
                write_uid  = {user_id}
            from product_product pp
            inner join product_template pt
                on pt.id = pp.product_tmpl_id
            inner join product_price_history_temp pcp
                on pcp.default_code = pt.default_code
            where pp.id = sol.product_id
            and sol.company_id = {company_id}
            and sol.transaction_date >= '{date_start}'
            and sol.transaction_date <= '{date_end}'
            and (
                    left(pt.default_code, 3) = 'BRG'
                    or left(sol.origin, 3) in ('PMB','AJB','SOB')
                );
            """.format(
                company_id=company_id, 
                date_start=date_start, 
                date_end=date_end,
                user_id=self.env.user.id 
            )

            open('/opt/odoo16/logs/stock_bulk_closing_non_medical.log', 'a+').write('\n'+str(query))
            self.sudo().env.cr.execute(query)
            

         # update QR Qty to MINUS
        query = """
            update stock_scrap as sol set 
                scrap_qty = ((case when sol.scrap_qty < 0 then 1 else -1 end) * sol.scrap_qty) ,
                cost_total = (((case when sol.scrap_qty < 0 then 1 else -1 end) * sol.scrap_qty) * sol.cost),
                odoo_cost_total = (((case when sol.scrap_qty < 0 then 1 else -1 end) * sol.scrap_qty) * sol.odoo_cost),
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            from product_product pp 
            inner join product_template pt on pt.id=pp.product_tmpl_id
            where sol.company_id = {company_id}
                and sol.transaction_date >= '{date_start}'
                and sol.transaction_date <= '{date_end}'
                and sol.trans_type in('AR','SE','PE')
                and (
                    left(pt.default_code, 3) = 'BRG' or 
                    left(sol.origin, 3) in ('PMB','AJB','SOB')
                )
        """.format(
            company_id=company_id, 
            date_start=date_start, 
            date_end=date_end,
            user_id=self.env.user.id 
        )
        open('/opt/odoo16/logs/stock_bulk_closing_non_medical.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


    
    # @api.multi
    def bulk_valuation(self):
        report_id = self.id 
        company_id = self.company_id.id
        date_start = (self.date_start).strftime('%Y-%m-%d')
        date_end = (self.date_end).strftime('%Y-%m-%d')
        sync_id_field = 'sync_id' if self.company_id.sync_type in['1','2'] else 'sync_id_api'

        # compute valuation from stock.scrap
        query = """
            insert into procurement_group (name, move_type, create_uid, create_date, write_uid, write_date)
            select distinct 
                concat(coalesce(concat(cp.company_code,'/'),''), a.origin) "name", 'direct' move_type,
                {user_id} create_uid, CURRENT_TIMESTAMP create_date,
                {user_id} write_uid, CURRENT_TIMESTAMP write_date
            from stock_scrap a 
            left join res_company cp on cp.id = a.company_id
            where a.procurement_created is not True 
                and a.procurement_group_id is null 
                and a.company_id = {company_id}
                and a.is_takeout is not True
                and date(a.transaction_date) >= '{date_start}'
                and date(a.transaction_date) <= '{date_end}'
                and (a.sync_id_api is not null or coalesce(a.sync_id,0) <> 0)
                and not exists(
                    select 1 
                    from procurement_group t
                    where t.name = concat(coalesce(concat(cp.company_code,'/'),''), a.origin))
            """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id 
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)

        query = """
            update stock_scrap as a set 
                procurement_group_id = p.id,
                procurement_created = True,
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            from res_company cp 
            inner join procurement_group p on left(p.name,4) = cp.company_code
            where p.name = concat(coalesce(concat(cp.company_code,'/'),''), a.origin)
                and cp.id = a.company_id
                and a.procurement_created is not True 
                and a.procurement_group_id is null 
                and a.is_takeout is not True
                and a.company_id = {company_id}
                and date(a.transaction_date) >= '{date_start}'
                and date(a.transaction_date) <= '{date_end}'
                and (a.sync_id_api is not null or coalesce(a.sync_id,0) <> 0)
            """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id 
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


        query = """
            insert into stock_picking (
                picking_type_id, company_id, group_id, origin, "name",
                min_date,max_date,"date",date_done,date_move,
                write_uid, create_uid,create_date,write_date,
                recompute_pack_op,launch_pack_operations,priority,
                partner_id,move_type,location_id,location_dest_id,
                note,state,owner_id, backorder_id,backordered,
                printed,sync_id_api,sync_date,sync_type
            )
            select 
                spt.id, a.company_id, a.procurement_group_id, a.origin,
                concat(coalesce(concat(cp.company_code,'/'), ''), a.origin,'/', a.{sync_id_field}) "name",
                date(a.transaction_date) min_date,
                date(a.transaction_date) max_date,
                date(a.transaction_date) "date",
                date(a.transaction_date) date_done,
                date(a.transaction_date) date_move,
                {user_id} write_uid, 
                {user_id} create_uid,
                CURRENT_TIMESTAMP create_date,
                CURRENT_TIMESTAMP write_date,
                false recompute_pack_op,
                false launch_pack_operations,
                1 priority,
                so.partner_id as partner_id,
                'direct' move_type,
                (case when a.transaction_type in ('AR','SE','PE') then a.scrap_location_id else a.location_id end) location_id,
                (case when a.transaction_type in ('AR','SE','PE') then a.location_id else a.scrap_location_id end) location_dest_id,
                a.transaction_type note,
                'waiting' state,
                null::integer owner_id, 
                null::integer backorder_id,
                false backordered,
                false printed,
                concat('STOCK.', a.{sync_id_field}) sync_id_api,
                a.sync_date,
                a.sync_type
            from stock_scrap a
            inner join res_company cp on cp.id = a.company_id
            inner join stock_warehouse sw on sw.company_id = a.company_id 
            inner join stock_picking_type spt on spt.warehouse_id = sw.id 
                and spt.sync_id_api = (case a.trans_type 
                    when 'AI' then 'adjustment.issue'
                    when 'AR' then 'adjustment.receipt'
                    when 'SC' then 'stock.scrap'
                    when 'PI' then 'prepared.item'
                    when 'SE' then 'prepared.receipt'
                    else 'stock.breakage' end)
            left join sale_order so on so.id = a.admission_id
            where a.company_id = {company_id}
                and date(a.transaction_date) >= '{date_start}'
                and date(a.transaction_date) <= '{date_end}'
                and a.is_takeout is not True
                and (a.sync_id_api is not null or coalesce(a.sync_id,0) <> 0)
                and a.picking_id is null 
                and a.picking_created is not True
                and a.procurement_created is True 
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id,
            sync_id_field = sync_id_field
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


        # update flagging picking_id
        query = """
            update stock_scrap a set 
                picking_id = sp.id,
                picking_created = True,
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            from stock_picking sp
            where a.company_id = {company_id}
                and date(a.transaction_date) >= '{date_start}'
                and date(a.transaction_date) <= '{date_end}'
                and (a.sync_id_api is not null or coalesce(a.sync_id,0) <> 0)
                and a.picking_id is null 
                and a.picking_created is not True
                and a.procurement_created is True
                and a.is_takeout is not True
                and sp.sync_type = a.sync_type
                and sp.sync_id_api = concat('STOCK.', a.{sync_id_field})
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id,
            sync_id_field = sync_id_field
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


        query = """
            insert into stock_move (
                group_id, picking_id, picking_type_id, company_id, origin, "name","date",
                create_date, write_date, create_uid, write_uid,
                priority, product_id, product_uom_qty, product_qty,
                product_uom, price_unit, cost_unit, note, "state", date_expected,
                partially_available, propagate, procure_method,
                lot_id, sync_id_api, sync_type, location_id, location_dest_id
            )
            select 
                a.procurement_group_id,
                a.picking_id, 
                spt.id,
                a.company_id,
                a.origin,
                a."name",
                date(a.transaction_date) "date",
                CURRENT_TIMESTAMP create_date,
                CURRENT_TIMESTAMP write_date,
                {user_id} create_uid,
                {user_id} write_uid,
                1 priority,
                a.product_id,
                abs(a.scrap_qty) product_uom_qty,
                abs(a.scrap_qty) product_qty,
                pt.uom_id product_uom,
                coalesce(a.odoo_cost, a."cost") price_unit,
                coalesce(a.odoo_cost, a."cost") cost_unit,
                a.transaction_type note,
                'waiting' "state",
                a.date_expected,
                false partially_available,
                true propagate,
                'make_to_stock' procure_method,
                a.batch_id lot_id,
                concat('STOCK.', a.{sync_id_field}) sync_id_api, 
                a.sync_type,
                (case when a.transaction_type in ('AR','SE','PE') then a.scrap_location_id else a.location_id end) location_id,
                (case when a.transaction_type in ('AR','SE','PE') then a.location_id else a.scrap_location_id end) location_dest_id
            from stock_scrap a
            inner join product_product pp on pp.id = a.product_id 
            inner join product_template pt on pt.id = pp.product_tmpl_id
            inner join stock_warehouse sw on sw.company_id = a.company_id 
            inner join stock_picking_type spt on spt.warehouse_id = sw.id 
                and spt.sync_id_api = (case a.trans_type 
                    when 'AI' then 'adjustment.issue'
                    when 'AR' then 'adjustment.receipt'
                    when 'SC' then 'stock.scrap'
                    when 'PI' then 'prepared.item'
                    when 'SE' then 'prepared.receipt'
                    when 'PE' then 'physical.entry'
                    else 'stock.breakage' end)
            left join sale_order so on so.id = a.admission_id
            where a.company_id = {company_id}
                and date(a.transaction_date) >= '{date_start}'
                and date(a.transaction_date) <= '{date_end}'
                and (a.sync_id_api is not null or coalesce(a.sync_id,0) <> 0)
                and a.move_id is null 
                and a.is_takeout is not True
                and a.move_created is not True
                and a.picking_created is True
                and a.procurement_created is True
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id,
            sync_id_field = sync_id_field
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)

        # update flagging move_id
        query = """
            update stock_scrap a set 
                move_id = sp.id,
                move_created = True,
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            from stock_move sp
            where a.company_id = {company_id}
                and date(a.transaction_date) >= '{date_start}'
                and date(a.transaction_date) <= '{date_end}'
                and (a.sync_id_api is not null or coalesce(a.sync_id,0) <> 0)
                and a.move_id is null 
                and a.is_takeout is not True
                and a.move_created is not True
                and sp.sync_type = a.sync_type
                and sp.picking_id = a.picking_id
                and sp.sync_id_api = concat('STOCK.', a.{sync_id_field})
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id,
            sync_id_field = sync_id_field
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


        # compute valuation from sale.order.line
        query = """
            insert into procurement_group (name, move_type, create_uid, create_date, write_uid, write_date)
            select distinct 
                concat(coalesce(concat(cp.company_code,'/'),''), a.name) "name", 'direct' move_type,
                {user_id} create_uid, CURRENT_TIMESTAMP create_date,
                {user_id} write_uid, CURRENT_TIMESTAMP write_date
            from sale_order a 
            inner join sale_order_line sol on sol.order_id = a.id
            left join res_company cp on cp.id = a.company_id
            where a.procurement_created is not True 
            and a.procurement_group_id is null 
            and sol.is_takeout is not True
            and a.company_id = {company_id}
            and date(sol.tglproses) >= '{date_start}'
            and date(sol.tglproses) <= '{date_end}'
            and not exists(
                select 1 
                from procurement_group t
                where t.name = concat(coalesce(concat(cp.company_code,'/'),''), a.name)
            )
            """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id 
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)

        query = """
            select distinct sol.order_id
            from sale_order_line sol 
            where sol.company_id = {company_id}
                and date(sol.tglproses) >= '{date_start}'
                and date(sol.tglproses) <= '{date_end}'
                and sol.is_takeout is not True
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end)
        self.sudo().env.cr.execute(query)
        results = self.sudo().env.cr.dictfetchall()
        order_ids = ""
        for line in results:
            order_ids += (str(line['order_id']) if str(order_ids) == "" else (","+str(line['order_id'])))

        if order_ids != "":
            query = """
                update sale_order as a set 
                    procurement_group_id = p.id,
                    procurement_created = True,
                    write_date = CURRENT_TIMESTAMP,
                    write_uid = {user_id}
                from procurement_group p 
                left join res_company cp on cp.id = {company_id}
                where p.name = concat(coalesce(concat(cp.company_code,'/'),''), a.name)
                    and a.procurement_created is not True 
                    and a.procurement_group_id is null 
                    and a.company_id = {company_id}
                    and a.id in ({order_ids})
                """.format(
                company_id = company_id,
                date_start = date_start,
                date_end = date_end,
                user_id = self.env.user.id,
                order_ids = order_ids 
            )
            open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
            self.sudo().env.cr.execute(query)


        # compute valuation from sale.order.line
        query = """
            insert into stock_picking (
                sales_id, picking_type_id, group_id, company_id, origin,"name",
                min_date,max_date,"date",date_done,date_move,
                write_uid, create_uid,create_date,write_date,
                recompute_pack_op,launch_pack_operations,priority,
                partner_id,move_type,location_id,location_dest_id,
                note,state,owner_id, backorder_id,backordered,
                printed,sync_id_api,sync_date,sync_type
            )
            select 
                so.id, spt.id, so.procurement_group_id,
                a.company_id, 
                coalesce(a.order_no,'[NONE]') origin,
                concat(coalesce(concat(cp.company_code,'/'),''), 
                concat(coalesce(a.order_no,'[NONE]'),'/',a.sync_id_api)) "name",
                date(a.order_date) min_date,
                date(a.order_date) max_date,
                date(a.order_date) "date",
                date(a.order_date) date_done,
                date(a.order_date) date_move,
                {user_id} write_uid, 
                {user_id} create_uid,
                CURRENT_TIMESTAMP create_date,
                CURRENT_TIMESTAMP write_date,
                false recompute_pack_op,
                false launch_pack_operations,
                1 priority,
                so.partner_id,
                'direct' move_type,
                (case when a.product_uom_qty < 0 then sl.scrap_location_id else a.location_id end) location_id,
                (case when a.product_uom_qty < 0 then a.location_id else sl.scrap_location_id end) location_dest_id,
                a."name" note,
                'waiting' state,
                null::integer owner_id, 
                null::integer backorder_id,
                false backordered,
                false printed,
                concat('SALES.', a.{sync_id_field}) sync_id_api,
                a.sync_date,
                a.sync_type
            from sale_order_line a
            inner join sale_order so on so.id = a.order_id
            inner join res_company cp on cp.id = so.company_id
            inner join product_product pp on pp.id = a.product_id
            inner join product_template pt on pt.id = pp.product_tmpl_id
            inner join stock_warehouse sw on sw.company_id = a.company_id 
            inner join stock_picking_type spt on spt.warehouse_id = sw.id 
                and spt.sync_id_api = (case when a.product_uom_qty < 0 
                    then 'sales.return' else 'sales.issue' end)
            left join lateral (
                select sl.id scrap_location_id 
                from stock_location sl 
                where sl.name = 'Customers' 
                limit 1 
            ) sl on 0=0
            where a.company_id = {company_id}
                and date(a.tglproses) >= '{date_start}'
                and date(a.tglproses) <= '{date_end}'
                and (a.sync_id_api is not null or coalesce(a.sync_id,0) <> 0)
                and a.picking_id is null
                and a.picking_created is not True 
                and a.is_takeout is not True
                and so.procurement_created is True 
                and pt.type = 'product'
                and not exists (select 1 from stock_picking where sync_id_api=concat('SALES.', a.{sync_id_field}))
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id,
            sync_id_field = sync_id_field
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


        # update flagging picking_id
        query = """
            update sale_order_line a set 
                picking_id = sp.id,
                picking_created = True,
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            from stock_picking sp
            where a.company_id = {company_id}
                and date(a.tglproses) >= '{date_start}'
                and date(a.tglproses) <= '{date_end}'
                and (a.sync_id_api is not null or coalesce(a.sync_id,0) <> 0)
                and a.picking_id is null
                and a.picking_created is not True 
                and a.is_takeout is not True
                and sp.sync_type = a.sync_type
                and sp.sync_id_api = concat('SALES.', a.{sync_id_field})
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id,
            sync_id_field = sync_id_field 
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


        query = """
            insert into stock_move (
                sale_line_id, group_id, picking_id, picking_type_id, company_id,origin,"name","date",
                create_date,write_date,create_uid,write_uid,
                priority,product_id,product_uom_qty, product_qty,
                product_uom,price_unit,note,"state",date_expected,
                partially_available,propagate,lot_id,procure_method, 
                sync_id_api, sync_type, location_id, location_dest_id
            )
            select 
                a.id, so.procurement_group_id, a.picking_id, spt.id, a.company_id,
                coalesce(a.order_no,'[NONE]') origin,
                coalesce(a."name", coalesce(a.order_no,'[NONE]')) "name",
                date(a.order_date) "date",
                CURRENT_TIMESTAMP create_date,
                CURRENT_TIMESTAMP write_date,
                {user_id} create_uid,
                {user_id} write_uid,
                1 priority,
                a.product_id,
                abs(a.product_uom_qty) product_uom_qty,
                abs(a.product_uom_qty) product_qty,
                pt.uom_id product_uom,
                coalesce(a.cost_unit) price_unit,
                a.type_line note,
                'waiting' "state",
                coalesce(a.batch_expired,CURRENT_DATE) date_expected,
                false partially_available,
                true propagate,
                a.batch_rel lot_id,
                'make_to_stock' procure_method,
                concat('SALES.',a.{sync_id_field}) sync_id_api,
                a.sync_type,
                (case when a.product_uom_qty < 0 then sl.scrap_location_id else a.location_id end) location_id,
                (case when a.product_uom_qty < 0 then a.location_id else sl.scrap_location_id end) location_dest_id
            from sale_order_line a
            inner join sale_order so on so.id = a.order_id
            inner join product_product pp on pp.id = a.product_id 
            inner join product_template pt on pt.id = pp.product_tmpl_id
            inner join stock_warehouse sw on sw.company_id = a.company_id
            inner join stock_picking_type spt on spt.warehouse_id = sw.id 
                and spt.sync_id_api = (case when a.product_uom_qty < 0 
                    then 'sales.return' else 'sales.issue' end)
            left join lateral (
                select sl.id scrap_location_id 
                from stock_location sl 
                where sl.name = 'Customers' 
                limit 1 
            ) sl on 0=0
            where a.company_id = {company_id}
            and date(a.tglproses) >= '{date_start}'
            and date(a.tglproses) <= '{date_end}'
            and (a.sync_id_api is not null or coalesce(a.sync_id,0) <> 0)
            and a.move_id is null 
            and a.move_created is not True
            and a.picking_created is True
            and a.is_takeout is not True
            and pt.type='product' 
            and not exists(select 1 from stock_move 
                where sync_type=a.sync_type 
                and sync_id_api=concat('SALES.',a.{sync_id_field})) 
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id,
            sync_id_field = sync_id_field
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


        # update flagging move_id
        query = """
            update sale_order_line a set 
                move_id = sp.id,
                move_created = True,
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            from stock_move sp
            where a.company_id = {company_id}
                and date(a.tglproses) >= '{date_start}'
                and date(a.tglproses) <= '{date_end}'
                and (a.sync_id_api is not null or coalesce(a.sync_id,0) <> 0)
                and a.move_id is null 
                and a.move_created is not True
                and a.picking_created is True 
                and a.is_takeout is not True
                and sp.sync_type = a.sync_type
                and sp.picking_id = a.picking_id
                and sp.sync_id_api = concat('SALES.', a.{sync_id_field})
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id,
            sync_id_field = sync_id_field
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


        # compute valuation from purchase.order
        query = """
            insert into procurement_group (name, move_type, create_uid, create_date, write_uid, write_date)
            select 
                concat(coalesce(concat(cp.company_code,'/'),''), a.title) "name",
                'direct' move_type, {user_id} create_uid, CURRENT_TIMESTAMP create_date,
                {user_id} write_uid, CURRENT_TIMESTAMP write_date
            from purchase_order a 
            left join res_company cp on cp.id = a.company_id
            where a.procurement_created is not True 
            and a.procurement_group_id is null 
            and a.company_id = {company_id}
            and date(coalesce(a.wipro_date,a.date_order)) >= '{date_start}'
            and date(coalesce(a.wipro_date,a.date_order)) <= '{date_end}'
            and not exists(
                select 1 
                from procurement_group t
                where t.name = concat(coalesce(concat(cp.company_code,'/'),''), a.title))
            """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id,
            sync_id_field = sync_id_field
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)

        query = """
            update purchase_order as a set 
                procurement_group_id = p.id,
                procurement_created = True,
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            from procurement_group p
            left join res_company cp on cp.id = {company_id}
            where p.name = concat(coalesce(concat(cp.company_code,'/'),''), a.title)
            and a.procurement_created is not True 
            and a.procurement_group_id is null 
            and a.company_id = {company_id}
            and date(coalesce(a.wipro_date,a.date_order)) >= '{date_start}'
            and date(coalesce(a.wipro_date,a.date_order)) <= '{date_end}'
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id,
            sync_id_field = sync_id_field 
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


        query = """
            insert into stock_picking (
                po_id, picking_type_id, group_id, company_id, origin,"name",
                min_date,max_date,"date",date_done,date_move,
                write_uid, create_uid,create_date,write_date,
                recompute_pack_op,launch_pack_operations,priority,
                partner_id,move_type,location_id,location_dest_id,
                note,state,owner_id, backorder_id,backordered,
                printed,sync_id_api,sync_date,sync_type
            )
            select 
                po.id, spt.id, po.procurement_group_id, po.company_id, 
                coalesce(po."name",'[NONE]') origin,
                concat(coalesce(concat(cp.company_code,'/'),''),po."name", '(', pol.{sync_id_field}, ')') "name",
                date(coalesce(po.wipro_date,po.date_order)) min_date,
                date(coalesce(po.wipro_date,po.date_order)) max_date,
                date(coalesce(po.wipro_date,po.date_order)) "date",
                date(coalesce(po.wipro_date,po.date_order)) date_done,
                date(coalesce(po.wipro_date,po.date_order)) date_move,
                {user_id} write_uid, 
                {user_id} create_uid,
                CURRENT_TIMESTAMP create_date,
                CURRENT_TIMESTAMP write_date,
                false recompute_pack_op,
                false launch_pack_operations,
                1 priority,
                po.partner_id,
                'direct' move_type,
                (case when po.is_return is True then sl.scrap_location_id else dl.location_id end) location_id,
                (case when po.is_return is True then dl.location_id else sl.scrap_location_id end) location_dest_id,
                pol."name" note,
                'waiting' state,
                null::integer owner_id, 
                null::integer backorder_id,
                false backordered,
                false printed,
                concat('POL.', pol.{sync_id_field}) sync_id_api,
                po.sync_date,
                po.sync_type
            from purchase_order po
            inner join purchase_order_line pol on pol.order_id = po.id
            inner join res_company cp on cp.id = po.company_id
            inner join stock_warehouse sw on sw.company_id = po.company_id 
            inner join stock_picking_type spt on spt.warehouse_id = sw.id 
                and spt.sync_id_api = (case 
                    when po.is_return is True 
                    then 'purchase.return' 
                    else 'purchase.receipt' end)
            left join lateral (
                select sl.id scrap_location_id 
                from stock_location sl 
                where sl.name = 'Vendors' 
                limit 1 
            ) sl on 0=0
            left join lateral (
                select dl.id location_id 
                from stock_location dl
                where dl.name ilike '%stock%' 
                    and dl.company_id = po.company_id
                limit 1 
            ) dl on 0=0
            where po.company_id = {company_id}
            and date(coalesce(po.wipro_date,po.date_order)) >= '{date_start}'
            and date(coalesce(po.wipro_date,po.date_order)) <= '{date_end}'
            and (pol.sync_id_api is not null or coalesce(pol.sync_id,0) <> 0)
            and pol.picking_id is null 
            and pol.picking_created is not True
            and po.procurement_created is True
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id,
            sync_id_field = sync_id_field 
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


        # update flagging picking_id
        query = """
            update purchase_order_line a set 
                picking_id = sp.id,
                picking_created = True,
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            from stock_picking sp
            inner join purchase_order po on po.id = sp.po_id
            where po.id = a.order_id
                and a.company_id = {company_id}
                and date(coalesce(po.wipro_date,po.date_order)) >= '{date_start}'
                and date(coalesce(po.wipro_date,po.date_order)) <= '{date_end}'
                and (a.sync_id_api is not null or coalesce(a.sync_id,0) <> 0)
                and a.picking_id is null 
                and a.picking_created is not True
                and po.procurement_created is True
                and sp.sync_type = a.sync_type
                and sp.sync_id_api = concat('POL.', a.{sync_id_field})
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id,
            sync_id_field = sync_id_field
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


        query = """
            insert into stock_move (
                purchase_line_id, group_id, picking_id, picking_type_id, 
                company_id,origin,"name","date",
                create_date,write_date,create_uid,write_uid,
                priority,product_id,product_uom_qty, product_qty,
                product_uom,price_unit,note,"state",date_expected,
                partially_available,propagate,lot_id, procure_method, 
                sync_type, sync_id_api, location_id, location_dest_id
            )
            select 
                pol.id, po.procurement_group_id, po.picking_id, spt.id, po.company_id,
                coalesce(po."name",'[NONE]') origin,
                coalesce(pol."name",'[NONE]') "name",
                date(coalesce(po.wipro_date,po.date_order)) "date",
                CURRENT_TIMESTAMP create_date,
                CURRENT_TIMESTAMP write_date,
                {user_id} create_uid,
                {user_id} write_uid,
                1 priority,
                pol.product_id,
                abs(pol.product_qty) product_uom_qty,
                abs(pol.product_qty) product_qty,
                pol.product_uom,
                coalesce(pol.price_subtotal/pol.product_qty) price_unit,
                pol."name" note,
                'waiting' "state",
                coalesce(pol.expiry_date,CURRENT_DATE) date_expected,
                false partially_available,
                true propagate,
                pol.batch_id lot_id,
                'make_to_stock' procure_method,
                pol.sync_type,
                concat('POL.', pol.{sync_id_field}) sync_id_api,
                (case when po.is_return is True then sl.scrap_location_id else dl.location_id end) location_id,
                (case when po.is_return is True then dl.location_id else sl.scrap_location_id end) location_dest_id
            from purchase_order po
            inner join purchase_order_line pol on pol.order_id = po."id"
            inner join stock_warehouse sw on sw.company_id = po.company_id 
            inner join stock_picking_type spt on spt.warehouse_id = sw.id 
                and spt.sync_id_api = (case when po.is_return is True then 'purchase.return' else 'purchase.receipt' end)
            left join lateral (
                select sl.id scrap_location_id 
                from stock_location sl 
                where sl.name = 'Vendors' 
                limit 1 
            ) sl on 0=0
            left join lateral (
                select dl.id location_id 
                from stock_location dl
                where dl.name ilike '%stock%' 
                    and dl.company_id = po.company_id
                limit 1 
            ) dl on 0=0
            where po.company_id = {company_id}
            and date(coalesce(po.wipro_date,po.date_order)) >= '{date_start}'
            and date(coalesce(po.wipro_date,po.date_order)) <= '{date_end}'
            and (pol.sync_id_api is not null or coalesce(pol.sync_id,0) <> 0)
            and pol.move_id is null 
            and pol.move_created is not True
            and pol.picking_created is True
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id,
            sync_id_field = sync_id_field 
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)

        # update flagging move_id
        query = """
            update purchase_order_line pol set 
                move_id = sp.id,
                move_created = True,
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            from purchase_order po
            inner join stock_move sp on sp.company_id = po.company_id
            where po.id = pol.order_id
                and sp.picking_id = pol.picking_id
                and pol.company_id = {company_id}
                and pol.picking_id is not null
                and pol.picking_created is True
                and date(coalesce(po.wipro_date,po.date_order)) >= '{date_start}'
                and date(coalesce(po.wipro_date,po.date_order)) <= '{date_end}'
                and (pol.sync_id_api is not null or coalesce(pol.sync_id,0) <> 0)
                and pol.move_id is null 
                and pol.move_created is not True
                and sp.sync_type = pol.sync_type
                and sp.sync_id_api = concat('POL.', pol.{sync_id_field})
        """.format(
            company_id = company_id,
            date_start = date_start,
            date_end = date_end,
            user_id = self.env.user.id,
            sync_id_field = sync_id_field
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)

        # force confirm stock.picking
        # update flagging move_id
        # query = """
        #     select a.id
        #     from stock_picking a
        #     where a.company_id = {company_id}
        #         and a.sync_id_api is not null
        #         and date(a.date_move) >= '{date_start}'
        #         and date(a.date_move) <= '{date_end}'
        #         and a.state = 'waiting'
        # """.format(
        #     company_id = company_id,
        #     date_start = date_start,
        #     date_end = date_end,
        #     user_id = self.env.user.id,
        #     sync_id_field = sync_id_field
        # )
        # open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        # self.sudo().env.cr.execute(query)
        # picking_ids = self.sudo().env.cr.dictfetchall()

        # if picking_ids:
        #     for picking_id in picking_ids:
        #         picking = self.env['stock.picking'].browse(picking_id['id'])
        #         if picking:
        #             picking.force_assign()
        #             picking.do_new_transfer()


    # @api.multi
    def bulk_update(self):
        report_id = self.id 
        company_id = self.company_id.id
        date_start = (self.date_start).strftime('%Y-%m-%d')
        date_end = (self.date_end).strftime('%Y-%m-%d')
        
        # reset semua odoo_cost
        query = """
            update stock_scrap as sol set 
                odoo_cost = 0,
                odoo_cost_total = 0,
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            where sol.company_id = {company_id}
                and sol.transaction_date >= '{date_start}'
                and sol.transaction_date <= '{date_end}'
        """.format(
            company_id=company_id, 
            date_start=date_start, 
            date_end=date_end,
            user_id=self.env.user.id 
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)

        # update odoo cost_total 
        # 2024.02.13 - MHBD untuk hasil cogs odoo yang angka nya terlalu besar lebih dari 120% x dari Cogs HIS, maka ambil nilai cogs dari HIS
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write(str('\nStart update stock.scrap'))
        query = """
            update stock_scrap as sol set 
                odoo_cost = (case 
                    when coalesce(pcp.cost,0) = 0 then sol.cost 
                    --when coalesce(pcp.cost,0) > (sol.cost * 2) then sol.cost
                    else coalesce(pcp.cost,0) end),
                odoo_cost_total = (
                    (case 
                        when coalesce(pcp.cost,0) = 0 then sol.cost 
                        --when coalesce(pcp.cost,0) > (sol.cost * 2) then sol.cost
                        else coalesce(pcp.cost,0) 
                    end) * sol.scrap_qty),
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            from product_product pp 
            inner join product_template pt on pt.id=pp.product_tmpl_id
            inner join product_price_history pcp on pcp.product_id=pp.id
            where pp.id = sol.product_id
                and date(pcp.datetime) = date('{date_end}')
                and coalesce(sol.odoo_cost,0) = 0
                and sol.company_id = {company_id}
                and sol.transaction_date >= '{date_start}'
                and sol.transaction_date <= '{date_end}'
        """.format(
            company_id=company_id,
            date_start=date_start, 
            date_end=date_end,
            user_id=self.env.user.id 
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


        # Update by code product
        if self.company_id.company_code == 'MHSB':
            query = """
                with product_price_history_temp as (
                    select distinct on (pt2.default_code)
                        pt2.default_code,
                        pcp.cost,
                        pcp.datetime
                    from product_price_history pcp
                    inner join product_product pp2
                        on pp2.id = pcp.product_id
                    inner join product_template pt2
                        on pt2.id = pp2.product_tmpl_id
                    where date(pcp.datetime) = date('{date_end}')
                    order by pt2.default_code, pcp.datetime desc
                )

                update stock_scrap sol
                set
                    odoo_cost = case
                        when coalesce(pcp.cost, 0) = 0 then sol.cost
                        else pcp.cost
                    end,
                    odoo_cost_total = (
                        case
                            when coalesce(pcp.cost, 0) = 0 then sol.cost
                            else pcp.cost
                        end * sol.scrap_qty
                    ),
                    write_date = CURRENT_TIMESTAMP,
                    write_uid  = {user_id}
                from product_product pp
                inner join product_template pt
                    on pt.id = pp.product_tmpl_id
                inner join product_price_history_temp pcp
                    on pcp.default_code = pt.default_code
                where pp.id = sol.product_id
                and coalesce(sol.odoo_cost, 0) = 0
                and sol.company_id = {company_id}
                and sol.transaction_date >= '{date_start}'
                and sol.transaction_date <= '{date_end}';
            """.format(
                company_id=company_id, 
                date_start=date_start, 
                date_end=date_end,
                user_id=self.env.user.id 
            )
            
            open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
            self.sudo().env.cr.execute(query)

        
        # update odoo AR
        query = """
            update stock_scrap as sol set 
                scrap_qty = ((case when sol.scrap_qty < 0 then 1 else -1 end) * sol.scrap_qty) ,
                cost_total = (((case when sol.scrap_qty < 0 then 1 else -1 end) * sol.scrap_qty) * sol.cost),
                odoo_cost_total = (((case when sol.scrap_qty < 0 then 1 else -1 end) * sol.scrap_qty) * sol.odoo_cost),
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            where sol.company_id = {company_id}
                and sol.transaction_date >= '{date_start}'
                and sol.transaction_date <= '{date_end}'
                and sol.trans_type in('AR','SE','PE')
        """.format(
            company_id=company_id, 
            date_start=date_start, 
            date_end=date_end,
            user_id=self.env.user.id 
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)






# 2021.09.09 - Update StockMove by Firgi
class StockMove(models.Model):
    _inherit = 'stock.move'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']
    _description = "Stock Move"
    _order = 'sequence, id'

    def _default_group_id(self):
        if self.env.context.get('default_picking_id'):
            return self.env['stock.picking'].browse(self.env.context['default_picking_id']).group_id.id
        return False
    
    def get_removal_strategy(self):
        ''' Returns the removal strategy to consider for the given move/ops '''
        print ("disinikah?")
        if self.product_id.categ_id.removal_strategy_id:
            return self.product_id.categ_id.removal_strategy_id.method
        print ("oh bukan")
        loc = self.location_id
        print ("coba disini")
        # while loc:
        #     if loc.removal_strategy_id:
        #         return loc.removal_strategy_id.method
        #     loc = loc.location_id
        print ("kelar")
        return 'fifo'

    sync_id = sync.id_big
    sync_date = sync.date
    sync_id_api = sync.id_api
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    group_id = fields.Many2one('procurement.group', 'Procurement Group', default=_default_group_id)
    tglproses = fields.Date(string="TglProses", store=True)
    min_date = fields.Date(string="Scheduled Date")
    move_type = fields.Selection([
        ('purchase.receipt', 'Purchase Receipt'), 
        ('purchase.return', 'Purchase Return'),
        ('sales.issue','Sales Issue'),
        ('sales.return','Sales Return'),
        ('stock.scrap', 'Store Consumption'),
        ('adjustment.issue', 'Adjustment Issue'),
        ('adjustment.receipt', 'Adjustment Receipt'),
        ('stock.breakage','Loss Breakage'),
        ('internal','Internal Transfer'),
        ('incoming','Incoming'),
        ('outgoing','Outgoing')], string="Move Type", store=True)

    @api.model
    def _get_account_input(self):
        return self.product_id.categ_id.property_stock_account_input_categ_id.id or False

    @api.model
    def _get_account_valuation(self):
        return self.product_id.categ_id.property_stock_valuation_account_id.id or False
    
    account_analytic_id = fields.Many2one('account.analytic.account', string="Analytic Account", domain=[('type_analytic', '=', 'expense')], index=True)
    product_service_id = fields.Many2one('product.category', string="Product Service", readonly=True, related='product_id.categ_id.parent_id', store=True)
    product_categ_id = fields.Many2one('product.category', string="Product Category", related='product_id.categ_id')
    product_supply_id = fields.Many2one('account.account', string="Account Valuation", default=_get_account_valuation, store=True)
    product_supply_code = fields.Char(related='product_supply_id.code', string="Account Valuation Code", store=True, readonly=True)
    product_input_id = fields.Many2one('account.account', string="Account Input", default=_get_account_input, store=True)
    product_consignment = fields.Boolean(string="Product Consignment", default=False, store=True)
    # product_conversion_rate = fields.Float(string="Product Conversion Rate", related='product_id.conversion_rate', store=True)
    product_uom2 = fields.Many2one('uom.uom', string="Purchase UoM", readonly=True, store=True)
    product_uom2_qty = fields.Float(string="Purchase Qty", digits=(16, 4))
    asset_category_id = fields.Many2one('account.asset.category', string="Asset Type")
    asset_location_id = fields.Many2one('hr.department', string="Asset Location")
    asset_value = fields.Float(string="Asset Value", default=lambda self: self.purchase_line_id.price_subtotal or 0)
    asset_brand = fields.Char(string="Asset Brand")

    # route_ids = fields.Many2many('stock.location.route', 'stock_location_route_move', 'move_id', 'route_id', 'Destination route', help="Preferred route to be followed by the procurement order")
    warehouse_id = fields.Many2one('stock.warehouse', 'Warehouse', help="Technical field depicting the warehouse to consider for the route selection on the next procurement (if any).")
    warehouse_name = fields.Char(string="Source Warehouse", store=True, compute='_compute_warehouse')
    
    location_id = fields.Many2one('stock.location', 'Source Location', auto_join=True, index=True, required=False, states={'done': [('readonly', True)]}, help="Sets a location if you produce at a fixed location. This can be a partner location if you subcontract the manufacturing operations.")
    location_dest_id = fields.Many2one('stock.location', 'Destination Location', auto_join=True, index=True, required=False, states={'done': [('readonly', True)]}, help="Location where the system will stock the finished products.")
    lot_id = fields.Many2one('stock.lot', string="Lot/Batch", index=True)
    
    stock_beginning = fields.Float(string="Stock Beginning", compute='_compute_stock_moving', store=False)
    stock_moving = fields.Float(string="Stock Moving", compute='_compute_stock_moving', store=False)
    stock_ending = fields.Float(string="Stock Ending", compute='_compute_stock_moving', store=False)
    
    cost_type = fields.Selection([('delivery', 'Delivery'), ('store', 'Store Consumption'), ('in', 'Cost In Purchase'), ('internal', 'Internal'), ('return_c', 'Cost In Return Customer'), ('return_s', 'Cost Out Return Supplier')], string="Cost Type", store=True)
    cost_unit = fields.Float(string="Cost Unit")
    
    purchase_backup_id = fields.Float(string="Purchase ID")
    purchase_line_id = fields.Many2one('purchase.order.line', string="Purchase Line ID")
    sale_line_id = fields.Integer(string='Sale Line ID') # fields.Many2one('sale.order.line', string="Sale Line ID", ondelete='set null')
    scrap_id = fields.Many2one('stock.scrap', string="Scrap ID")

    api_post_timestamp = fields.Datetime(string="Timestamp API", readonly=True)
    api_post_status = fields.Selection([('done', 'Done'), ('failed', 'Failed')], string='Status API', readonly=True)
    api_post_payload = fields.Char(string="Payload API", readonly=True)
    api_post_response = fields.Char(string="Response API", readonly=True)
    api_post_url = fields.Char(string="URL", readonly=True)
    api_post_key = fields.Char(string="API Key", readonly=True)

    asset_detail = fields.Char(string="Asset Detail", compute="_get_detail_asset", store=False)
    capitalization = fields.Float(string="Capitalization Asset", store=True)
    non_asset = fields.Float(string="Non Asset", store=True)
    asset_cip_id = fields.Many2one('account.asset.cip', string='Asset CIP')

    ######################### Update
    receiving_line_id = fields.Many2one('stock.receiving.line', string='Receiving Line')
    discount_persen = fields.Float(string='Discount Percent', digits=(16, 9))
    discount_value = fields.Float(string="Discount Value", store=True, digits=(16, 4))
    discount_total = fields.Float(string='Discount Total', store=True)
    tax_discount = fields.Float(string='Tax Discount', readonly=True)
    taxes_id = fields.Many2many('account.tax', string='Taxes', domain=['|', ('active', '=', False), ('active', '=', True)])
    price_tax = fields.Float(string='Tax', store=True)
    sub_total = fields.Float(string="Sub Total")
    price_total = fields.Float(string='Total', store=True)
    ######################### From Odoo10
    date_expected = fields.Datetime(string="Expected Date")
    move_dest_id = fields.Many2one('stock.move', string="Destination Move")
    base_price = fields.Float(string="Base Price", default=0)
    ordered_qty = fields.Float(string="Ordered Quantity")
    product_packaging = fields.Many2one('product.packaging', string="Preferred Packaging")
    partially_available = fields.Boolean(string="Partially Available")
    propagate = fields.Boolean(string="Propagate cancel and split", default=True)
    push_rule_id = fields.Many2one('stock.location.path', string="Push Rule")
    split_from = fields.Many2one('stock.move', string="Move Split From")
    wipro_type = fields.Selection([('receiving', "Receiving")], string="Wipro Type")
    note = fields.Text('Notes')

    # def _should_bypass_reservation(self, forced_location=False):
    #     # self.ensure_one()
    #     # location = forced_location or self.location_id
    #     # return location.should_bypass_reservation() or self.product_id.type != 'product'

    #     return True

    # def action_confirm(self):
    #     open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + "masuk action_confirm : " +  str(self.move_ids) )
    #     self._check_company()
    #     self.mapped('package_level_ids').filtered(lambda pl: pl.state == 'draft' and not pl.move_ids)._generate_moves()
    #     # call `_action_confirm` on every draft move
    #     self.move_ids.filtered(lambda move: move.state == 'draft')._action_confirm()

    #     # run scheduler for moves forecasted to not have enough in stock
    #     open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + "action_confirm : " +  str(self.move_ids) )
    #     self.move_ids.filtered(lambda move: move.state not in ('draft', 'cancel', 'done'))._trigger_scheduler()
    #     open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + "action_confirm2 : " +  str(self.move_ids) )
    #     return True

    # def _action_confirm(self, merge=True, merge_into=False):
    #     from odoo.tools.misc import clean_context, OrderedSet, groupby
    #     """ Confirms stock move or put it in waiting if it's linked to another move.
    #     :param: merge: According to this boolean, a newly confirmed move will be merged
    #     in another move of the same picking sharing its characteristics.
    #     """
    #     # Use OrderedSet of id (instead of recordset + |= ) for performance
    #     move_create_proc, move_to_confirm, move_waiting = OrderedSet(), OrderedSet(), OrderedSet()
    #     to_assign = defaultdict(OrderedSet)
    #     for move in self:
    #         if move.state != 'draft':
    #             continue
    #         # if the move is preceded, then it's waiting (if preceding move is done, then action_assign has been called already and its state is already available)
    #         if move.move_orig_ids:
    #             move_waiting.add(move.id)
    #         else:
    #             if move.procure_method == 'make_to_order':
    #                 move_create_proc.add(move.id)
    #             else:
    #                 move_to_confirm.add(move.id)
    #         if move._should_be_assigned():
    #             key = (move.group_id.id, move.location_id.id, move.location_dest_id.id)
    #             to_assign[key].add(move.id)

    #     move_create_proc, move_to_confirm, move_waiting = self.browse(move_create_proc), self.browse(move_to_confirm), self.browse(move_waiting)

    #     # create procurements for make to order moves
    #     procurement_requests = []
    #     for move in move_create_proc:
    #         values = move._prepare_procurement_values()
    #         origin = move._prepare_procurement_origin()
    #         procurement_requests.append(self.env['procurement.group'].Procurement(
    #             move.product_id, move.product_uom_qty, move.product_uom,
    #             move.location_id, move.rule_id and move.rule_id.name or "/",
    #             origin, move.company_id, values))
    #     self.env['procurement.group'].run(procurement_requests, raise_user_error=not self.env.context.get('from_orderpoint'))

    #     move_to_confirm.write({'state': 'confirmed'})
    #     (move_waiting | move_create_proc).write({'state': 'waiting'})
    #     # procure_method sometimes changes with certain workflows so just in case, apply to all moves
    #     (move_to_confirm | move_waiting | move_create_proc).filtered(lambda m: m.picking_type_id.reservation_method == 'at_confirm')\
    #         .write({'reservation_date': fields.Date.today()})

    #     # assign picking in batch for all confirmed move that share the same details
    #     for moves_ids in to_assign.values():
    #         self.browse(moves_ids).with_context(clean_context(self.env.context))._assign_picking()
    #     new_push_moves = self.filtered(lambda m: not m.picking_id.immediate_transfer)._push_apply()
    #     self._check_company()
    #     moves = self
    #     if merge:
    #         moves = self._merge_moves(merge_into=merge_into)

    #     # Transform remaining move in return in case of negative initial demand
    #     # neg_r_moves = moves.filtered(lambda move: float_compare(
    #     #     move.product_uom_qty, 0, precision_rounding=move.product_uom.rounding) < 0)
    #     neg_r_moves = moves.filtered(
    #         lambda move: "RETURN" in move.picking_type_id.name.upper()
    #     )
    #     # raise UserError(_(str(neg_r_moves)))
    #     for move in neg_r_moves:
    #         move.location_id, move.location_dest_id = move.location_dest_id, move.location_id
    #         orig_move_ids, dest_move_ids = [], []
    #         for m in move.move_orig_ids | move.move_dest_ids:
    #             from_loc, to_loc = m.location_id, m.location_dest_id
    #             if float_compare(m.product_uom_qty, 0, precision_rounding=m.product_uom.rounding) < 0:
    #                 from_loc, to_loc = to_loc, from_loc
    #             if to_loc == move.location_id:
    #                 orig_move_ids += m.ids
    #             elif move.location_dest_id == from_loc:
    #                 dest_move_ids += m.ids
    #         move.move_orig_ids, move.move_dest_ids = [(6, 0, orig_move_ids)], [(6, 0, dest_move_ids)]
    #         move.product_uom_qty *= -1
    #         if move.picking_type_id.return_picking_type_id:
    #             move.picking_type_id = move.picking_type_id.return_picking_type_id
    #         # We are returning some products, we must take them in the source location
    #         move.procure_method = 'make_to_stock'
    #     neg_r_moves._assign_picking()

    #     # call `_action_assign` on every confirmed move which location_id bypasses the reservation + those expected to be auto-assigned
    #     moves.filtered(lambda move: not move.picking_id.immediate_transfer
    #                    and move.state in ('confirmed', 'partially_available')
    #                    and (move._should_bypass_reservation()
    #                         or move.picking_type_id.reservation_method == 'at_confirm'
    #                         or (move.reservation_date and move.reservation_date <= fields.Date.today())))\
    #          ._action_assign()
    #     if new_push_moves:
    #         neg_push_moves = new_push_moves.filtered(lambda sm: float_compare(sm.product_uom_qty, 0, precision_rounding=sm.product_uom.rounding) < 0)
    #         (new_push_moves - neg_push_moves)._action_confirm()
    #         # Negative moves do not have any picking, so we should try to merge it with their siblings
    #         neg_push_moves._action_confirm(merge_into=neg_push_moves.move_orig_ids.move_dest_ids)

    #     # raise UserError(_("moves: " + str(moves)))
    #     return moves

    ################
    @api.onchange('product_uom_qty', 'price_unit', 'taxes_id','discount_total', 'discount_value', 'discount_persen')
    def _onchange_amount(self):
        for line in self:
            taxes = line.taxes_id.compute_all(line.price_unit - line.discount_value, line.purchase_line_id.order_id.currency_id, line.product_uom_qty, product=line.product_id, partner=line.purchase_line_id.order_id.partner_id)
            line.update({
                'price_tax': taxes['total_included'] - taxes['total_excluded'],
                'price_total': taxes['total_included'],
                'non_asset': taxes['total_included'],
                'sub_total': taxes['total_excluded'],
            })

    ##############update
    @api.onchange('discount_value', 'product_uom_qty')
    def _onchange_discount(self):
        for r in self:
            r.discount_total = r.discount_value * r.product_uom_qty
            for tax in r.taxes_id:
                tax_disc = tax._compute_amount(round(r.discount_value * r.product_uom_qty),r.price_unit,r.product_uom_qty,product=r.product_id,partner=r.picking_id.partner_id)
                r.tax_discount = tax_disc

    ##########update
    @api.onchange('taxes_id', 'discount_persen','price_unit')  # if these fields are changed, call method
    def _discount_persen(self):
        for r in self:
            if r.price_unit:
                discount_val = (r.discount_persen / 100) * r.price_unit
                r.discount_value = discount_val

    ###########update
    @api.onchange('taxes_id', 'discount_value','price_unit')  # if these fields are changed, call method
    def _discount_value(self):
        for r in self:
            if r.price_unit:
                r.discount_persen = (r.discount_value / r.price_unit) * 100
    
    # @api.multi
    def _get_detail_asset(self):
        print ('1')
        
        for sm in self:
            asset_ids = self.env['stock.picking.asset'].search([('picking_id','=', sm.picking_id.id)])

            detail_asset = ''
            for asset in asset_ids:
                
                picking_asset_ids = self.env['stock.picking.asset.line'].search([('picking_asset_id','=', asset['id']), ('move_id','=', sm.id)])
                if picking_asset_ids:
                    detail_asset = detail_asset + ('' if detail_asset == '' else ', ') + asset['name']
            
            sm.asset_detail = detail_asset
        
    ### By Pass Constraint check_uom Chaelvin 20/04/2021 ###
    @api.constrains('product_uom')
    def _check_uom(self):
        return True
    
    def name_get(self):
        res = []
        for move in self:
            res.append((move.id, move.product_id.product_tmpl_id.name + ' / ' + move.name))
        return res

    
    # 
    def _store_average_cost_price(self):
        print('do something !!!')
        


    # 2021.10.05 - compute account.move.line 
    def _prepare_account_move_line(self, qty, cost, credit_account_id, debit_account_id, svl_id, description):
        """
        Generate the account.move.line values to post to track the stock valuation difference due to the
        processing of the given quant.
        """
        self.ensure_one()

        if self._context.get('force_valuation_amount'):
            valuation_amount = self._context.get('force_valuation_amount')
        else:
            if self.product_id.cost_method == 'average':
                valuation_amount = cost if self.location_id.usage in ['supplier', 'production'] and self.location_dest_id.usage == 'internal' else self.product_id.standard_price
            else:
                valuation_amount = cost if self.product_id.cost_method == 'real' else self.product_id.standard_price
        # the standard_price of the product may be in another decimal precision, or not compatible with the coinage of
        # the company currency... so we need to use round() before creating the accounting entries.
        debit_value = self.company_id.currency_id.round(valuation_amount * qty)
        
        # overwrite amount
        debit_value = self.non_asset
    
        # check that all data is correct
        if self.company_id.currency_id.is_zero(debit_value):
            if self.product_id.cost_method == 'standard':
                raise UserError(_("The found valuation amount for product %s is zero. Which means there is probably a configuration error. Check the costing method and the standard price") % (self.product_id.name,))
            return []
        credit_value = debit_value

        if self.product_id.cost_method == 'average' and self.company_id.anglo_saxon_accounting:
            # in case of a supplier return in anglo saxon mode, for products in average costing method, the stock_input
            # account books the real purchase price, while the stock account books the average price. The difference is
            # booked in the dedicated price difference account.
            if self.location_dest_id.usage == 'supplier' and self.origin_returned_move_id and self.origin_returned_move_id.purchase_line_id:
                debit_value = self.origin_returned_move_id.price_unit * qty
            # in case of a customer return in anglo saxon mode, for products in average costing method, the stock valuation
            # is made using the original average price to negate the delivery effect.
            if self.location_id.usage == 'customer' and self.origin_returned_move_id:
                debit_value = self.origin_returned_move_id.price_unit * qty
                credit_value = debit_value

        partner_id = (self.picking_id.partner_id and self.env['res.partner']._find_accounting_partner(self.picking_id.partner_id).id) or False
        debit_line_vals = {
            'name': self.name,
            'product_id': self.product_id.id,
            'quantity': qty,
            'product_uom_id': self.product_id.uom_id.id,
            'ref': self.picking_id.name,
            'partner_id': partner_id,
            'debit': debit_value if debit_value > 0 else 0,
            'credit': -debit_value if debit_value < 0 else 0,
            'account_id': self.product_supply_id and self.product_supply_id.id or debit_account_id,
            # tambahan 
            'analytic_account_id': self.account_analytic_id.id or False,
            'stock_picking_id': self.picking_id and self.picking_id.id or False,
            'stock_move_id': self.id,
            'stock_categ_id': self.product_categ_id and self.product_categ_id.id or False,
            'stock_product_id': self.product_id.id,
            'stock_location_id': self.location_dest_id and self.location_dest_id.id or False,
            'sales_id': self.sale_line_id and self.sale_line_id.order_id.id or False,
            'purchase_id': self.purchase_line_id and self.purchase_line_id.order_id.id or False,
            'cip_id': self.asset_cip_id.id
        }
        credit_line_vals = {
            'name': self.name,
            'product_id': self.product_id.id,
            'quantity': qty,
            'product_uom_id': self.product_id.uom_id.id,
            'ref': self.picking_id.name,
            'partner_id': partner_id,
            'credit': credit_value if credit_value > 0 else 0,
            'debit': -credit_value if credit_value < 0 else 0,
            'account_id': self.product_input_id and self.product_input_id.id or credit_account_id,
            'analytic_account_id': False,
            'stock_picking_id': self.picking_id and self.picking_id.id or False,
            'stock_move_id': self.id,
            'stock_categ_id': self.product_categ_id and self.product_categ_id.id or False,
            'stock_product_id': self.product_id.id,
            'stock_location_id': self.location_id and self.location_id.id or False,
            'sales_id': self.sale_line_id and self.sale_line_id.order_id.id or False,
            'purchase_id': self.purchase_line_id and self.purchase_line_id.order_id.id or False,
            'cip_id': self.asset_cip_id.id
        }
        res = [(0, 0, debit_line_vals), (0, 0, credit_line_vals)]
        if credit_value != debit_value:
            # for supplier returns of product in average costing method, in anglo saxon mode
            diff_amount = debit_value - credit_value
            price_diff_account = self.product_id.property_account_creditor_price_difference
            if not price_diff_account:
                price_diff_account = self.product_id.categ_id.property_account_creditor_price_difference_categ
            if not price_diff_account:
                raise UserError(_('Configuration error. Please configure the price difference account on the product or its category to process this operation.'))
            price_diff_line = {
                'name': self.name,
                'product_id': self.product_id.id,
                'quantity': qty,
                'product_uom_id': self.product_id.uom_id.id,
                'ref': self.picking_id.name,
                'partner_id': partner_id,
                'credit': diff_amount > 0 and diff_amount or 0,
                'debit': diff_amount < 0 and -diff_amount or 0,
                'account_id': price_diff_account.id,
                'stock_picking_id': self.picking_id and self.picking_id.id or False,
                'stock_move_id': self.id,
                'stock_categ_id': self.product_categ_id and self.product_categ_id.id or False,
                'stock_product_id': self.product_id.id,
                'stock_location_id': self.location_id and self.location_id.id or False,
                'cip_id': self.asset_cip_id.id
            }
            res.append((0, 0, price_diff_line))
        return res

    @api.model
    def create(self, vals):
        # TDE CLEANME: why doing this tracking on picking here ? seems weird
        perform_tracking = not self.env.context.get('mail_notrack') and vals.get('picking_id')
        # if perform_tracking:
            # picking = self.env['stock.picking'].browse(vals['picking_id'])
            # initial_values = {picking.id: {'state': picking.state}}
        # vals['ordered_qty'] = vals.get('product_uom_qty')

        res = super(StockMove, self).create(vals)
        # for record in res: 
        #     # if record.product_id.conversion_rate > 0:
        #     # record.product_uom2_qty = record.product_uom_qty / record.product_id.conversion_rate
        #     if record.inventory_id.accounting_date:
        #       record.date = record.inventory_id.accounting_date
        #     if record.picking_id.state in ('assigned', 'done'):
        #       raise exceptions.ValidationError("Cannot create move with validated header!!")
        
        # if perform_tracking:
            # picking.message_track(picking.fields_get(['state']), initial_values)
        return res
    

    # @api.one
    def _compute_moving_stock(self):
         self.stock_moving = self.product_uom_qty
         if self.env.context.get('mutasi_location_id') == self.location_id.id:
            self.stock_beginning = sum(record.product_uom_qty for record in self.sudo().search([('date', '<', self.date), ('product_id', '=', self.product_id.id), ('location_dest_id', '=', self.location_id.id), ('state', '=', 'done')])) - sum(record.product_uom_qty for record in self.sudo().search([('date', '<', self.date), ('product_id', '=', self.product_id.id), ('location_id', '=', self.location_id.id), ('state', '=', 'done')]))
            self.stock_moving *= -1
         else:
            self.stock_beginning = sum(record.product_uom_qty for record in self.sudo().search([('date', '<', self.date), ('product_id', '=', self.product_id.id), ('location_dest_id', '=', self.location_dest_id.id), ('state', '=', 'done')])) - sum(record.product_uom_qty for record in self.sudo().search([('date', '<', self.date), ('product_id', '=', self.product_id.id), ('location_id', '=', self.location_dest_id.id), ('state', '=', 'done')]))
         if self.state == 'done':
            self.stock_ending = self.stock_beginning + self.stock_moving

    # @api.one
    @api.depends('location_id', 'location_dest_id')
    def _compute_warehouse(self):
        for record in self:
            record.warehouse_name = str(record.location_id.display_name) + ", " + str(record.location_dest_id.display_name)


    # @api.multi
    def create_journal_grn(self):
        move_lines = []
        # credit
        move_lines.append([0, 0, {
            'name' : self.name, 
            'ref' : self.name,
            'partner_id' : self.picking_id.partner_id.id,
            'account_id' : self.product_input_id.id,
            'date_maturity' : datetime.now().strftime('%Y-%m-%d'),
            'debit' : 0.0, 
            'credit' : self.non_asset or 0.0,
            'cip_id' : self.asset_cip_id.id
        }])
        
        # debit
        move_lines.append([0, 0, {
            'name' : self.name, 
            'ref' : self.name,
            'partner_id' : self.picking_id.partner_id.id,
            'account_id' : self.product_supply_id.id,
            'date_maturity' : datetime.now().strftime('%Y-%m-%d'),
            'credit' : 0.0, 
            'debit' : self.non_asset or 0.0,
            'cip_id' : self.asset_cip_id.id
        }])

        return move_lines

    def create_journal_grn_return(self):
        move_lines = []
        # credit
        move_lines.append([0, 0, {
            'name' : self.name, 
            'ref' : self.name,
            'partner_id' : self.picking_id.partner_id.id,
            'account_id' : self.product_input_id.id,
            'date_maturity' : datetime.now().strftime('%Y-%m-%d'),
            'debit' : 0.0, 
            'credit' : self.price_total or 0.0,
            'cip_id' : self.asset_cip_id.id
        }])
        
        # debit
        move_lines.append([0, 0, {
            'name' : self.name, 
            'ref' : self.name,
            'partner_id' : self.picking_id.partner_id.id,
            'account_id' : self.product_supply_id.id,
            'date_maturity' : datetime.now().strftime('%Y-%m-%d'),
            'credit' : 0.0, 
            'debit' : self.price_total or 0.0,
            'cip_id' : self.asset_cip_id.id
        }])

        return move_lines
    


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(StockMove,self).get_view(view_id=view_id,view_type=view_type, **options)        
        if view_type == 'tree':
            res['arch'] = """
                <tree decoration-info="state == 'draft'" decoration-success="state == 'done'" decoration-danger="state == 'cancel'" create="false" delete="false">
                    <field name="origin" string="Origin"/>
                    <field name="product_id" string="Product" on_change="1" can_create="true" can_write="true" modifiers="{'readonly': [['state', 'in', ['done']]], 'required': true}"/>
                    <field name="product_uom_qty" string="Qty" modifiers="{'readonly': [['state', 'in', ['done']]], 'required': true}"/>
                    <field name="product_uom" string="UoM" options="{'no_open': True, 'no_create': True}" can_create="true" can_write="true" modifiers="{'readonly': [['state', 'in', ['done']]], 'required': true}"/>
                    <!--field name="account_analytic_id" string="Account Analytic" /-->
                    <field name="location_id" string="From Facility" can_create="true" can_write="true" modifiers="{'readonly': [['state', 'in', ['done']]]}"/>
                    <field name="location_dest_id" string="To Facility" can_create="true" can_write="true" modifiers="{'readonly': [['state', 'in', ['done']]]}"/>
                    <field name="date" modifiers="{'readonly': [['state', 'in', ['done']]], 'required': true}"/>
                    <field name="state" modifiers="{'readonly': true}"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search COGS...">
                    <filter name="draft" string="Draft" domain="[('state','=', 'draft')]" help="Draft"/>
                    <filter name="waiting" string="Waiting Another Move" domain="[('state','=', 'waiting')]" help="Waiting Another Move"/>
                    <filter name="confirmed" string="Waiting Availavility" domain="[('state','=', 'confirmed')]" help="Waiting Availability"/>
                    <filter name="assigned" string="Available" domain="[('state','=', 'assigned')]" help="Available"/>
                    <filter name="done" string="Done" domain="[('state','=', 'done')]" help="Done"/>
                    <filter name="cancel" string="Cancelled" domain="[('state','=', 'cancel')]" help="Cancelled"/>
                    <separator/>
                    <field name="origin"/>
                    <field name="product_id"/>
                    <field name="picking_type_id"/>
                    <field name="picking_id"/>
                    <field name="account_analytic_id"/>
                    <field name="location_id"/>
                    <field name="location_dest_id"/>
                    <group expand="0" string="Group By">
                        <filter string="Status" domain="[]" context="{'group_by':'state'}"/>
                        <filter string="Order Date" domain="[]" context="{'group_by':'date'}"/>
                        <filter string="Origin" domain="[]" context="{'group_by':'origin'}"/>
                        <filter name="picking_type" string="Picking Type" domain="[]" context="{'group_by':'picking_type_id'}"/>
                    </group>
                </search>"""
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res







# 2022.07.11 - Stock Scrap Closing 
# untuk resync ulang data store consumption dari Wipro MHTG/MHJS ke Odoo untuk periode waktu tertentu
# case ini karena sering terjadi perubahan GRN di HIS Wipro MHJS
class StockLedgerClosing(models.TransientModel):
    _name = 'stock.ledger.closing.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    date_start = fields.Date(string="Date Start", store=True, index=True)
    date_end = fields.Date(string="Date End", store=True, index=True)

    # def db select MSSQL
    def sql_read(self, sync_type, query):
        company = self.sudo().env['res.company'].search([('sync_type','=', sync_type)], limit=1)
        db_host = company.his_slave_host
        db_name = company.his_slave_db
        db_user = company.his_slave_login
        db_pass = company.his_slave_pass
        
        result = None
        connect = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER='+db_host+';DATABASE='+db_name+';UID='+db_user+';PWD='+db_pass+';}')
            
        try:
            connect.autocommit = False
            cursor = connect.cursor().execute(query)
            data = cursor.fetchall()
            result = []
            column_names = [column[0] for column in cursor.description]
            for row in data:
                result.append(dict(zip(column_names, row)))
            return result

        except pyodbc.DatabaseError as err:
            connect.rollback()
        else:
            connect.commit()
        finally:
            print('Finally')
            connect.autocommit = True

    # MSSQL
    def sql_exec(self, sync_type, query):
        company = self.sudo().env['res.company'].search([('sync_type','=', sync_type)], limit=1)
        db_host = company.his_slave_host
        db_name = company.his_slave_db
        db_user = company.his_slave_login
        db_pass = company.his_slave_pass
        
        result = None
        connect = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER='+db_host+';DATABASE='+db_name+';UID='+db_user+';PWD='+db_pass+';}')

        try:
            connect.autocommit = False
            cursor = connect.cursor()
            results = cursor.execute(query)
            return results
        except pyodbc.DatabaseError as err:
            connect.rollback()
        else:
            connect.commit()
        finally:
            print('Finally')
            connect.autocommit = True


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(StockLedgerClosing,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Re-Sync SC/AI/AR for Closing">
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
                        <button name="syncing_ledger" string="Resync Ledger" type="object" class="oe_highlight"/>
                        <button name="syncing_scrap" string="Resync Scrap" type="object" class="oe_highlight"/>
                        <button name="syncing_costing" string="Resync AVG Cost" type="object" class="oe_highlight"/>
                        <button name="syncing_update" string="Update AVG Cost" type="object" class="oe_highlight"/>
                    </footer>
                </form>
           """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


    # @api.multi
    def syncing_ledger(self):
        report_id = self.id 
        company_id = self.company_id.id
        sync_type = self.company_id.sync_type
        date_start = datetime.strptime(str(self.date_start), '%Y-%m-%d')
        date_end = datetime.strptime(str(self.date_end), '%Y-%m-%d')
        
        # if sync_type not in MHJS & MHTG
        if self.company_id.sync_type not in['1','2']:
            raise exceptions.ValidationError("Fitur ini hanya dapat dilakukan untuk Integrasi Wipro-Odoo MHTG/MHJS.")

       
        # hapus dulu stock_ledger di periode berjalan 
        query = """
            DELETE FROM stock_ledger
            WHERE sync_type = '{sync_type}'
                AND tglproses >= '{date_start}'
                AND tglproses <= '{date_end}'
        """.format(
            sync_type=sync_type,
            date_start=date_start,
            date_end=date_end
        )
        open('/opt/odoo16/logs/log_stock_ledger.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)

        # sync stock_ledger dari Staging Odoo
        query  = """
            select 
                a.tglproses,
                a.sync_type,
                a.trans_type,
                a.trans_subtype,
                a.trans_datetime,
                a.trans_date,
                a.trans_direction,
                a.trans_internal,
                a.category_id,
                a.category_name,
                a.department_id,
                a.department_name,
                a.product_id,
                a.product_code,
                a.product_name,
                a.uom_id,
                a.uom_name,
                a.consignment,
                a.medical_type,
                a.stat_department,
                a.bpjs,
                sum(a.cost_unit) cost_unit,
                sum(a.cost_total) cost_total,
                sum(a.prev_cost_unit) prev_cost_unit,
                sum(a.prev_cost_total) prev_cost_total,
                sum(a.grn_unit) grn_unit,
                sum(a.grn_total) grn_total,
                sum(a.product_qty) product_qty
            from dbo.VRP_OdooStockInventory a 
            where a.sync_type = '{sync_type}'
                and a.tglproses >= '{date_start}'
                and a.tglproses <= '{date_end}'
            group by 
                a.tglproses,
                a.sync_type,
                a.trans_type,
                a.trans_subtype,
                a.trans_datetime,
                a.trans_date,
                a.trans_direction,
                a.trans_internal,
                a.category_id,
                a.category_name,
                a.product_id,
                a.product_code,
                a.product_name,
                a.uom_id,
                a.uom_name,
                a.consignment,
                a.medical_type,
                a.stat_department, a.bpjs,
                a.department_id,
                a.department_name
        """.format(
            sync_type=sync_type, 
            date_start=date_start,
            date_end=date_end)
        open('/opt/odoo16/logs/log_stock_ledger.log','a+').write('\n\n' + str(query))
        result = self.sql_read(sync_type, query)
        
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
                
                    if type(row[key]) in [str, bytes]:
                    # if type(row[key]) in [str, bytes, unicode]:
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
            
            excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
            columns = sync.remove_unicode(str(fields)).replace("'", "")
            columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")

            print (values)
            if not values:
                print ("No data available")

            # insert replace existing data 
            
            # query = """
            #     INSERT INTO stock_ledger %s VALUES %s 
            #     ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
            # """ % (columns, values, columns_without_id, excluded)

            query = """
                INSERT INTO stock_ledger %s VALUES %s 
            """ % (columns, values)
            print (query)
            self.env.cr.execute(query)

            # cleansing res.company
            query = """
                UPDATE stock_ledger as a set 
                    company_id = b.id,
                    create_date = now(),
                    create_uid = {user_id},
                    write_date = now(),
                    write_uid = {user_id}
                FROM res_company b 
                WHERE a.sync_type = '{sync_type}'
                    and a.tglproses >= '{date_start}'
                    and a.tglproses <= '{date_end}'
                    and b.sync_type = a.sync_type
            """.format(
                sync_type = sync_type,
                date_start = date_start,
                date_end = date_end,
                user_id = self.env.user.id
            )
            self.env.cr.execute(query)


            # cleansing stock.location
            query = """
                update stock_ledger as a set 
                    odoo_department_id = b.id
                from stock_location b 
                where a.sync_type = '{sync_type}'
                    and a.tglproses >= '{date_start}'
                    and a.tglproses <= '{date_end}'
                    and b.sync_type = a.sync_type
                    and b.sync_id = cast(a.department_id as integer)
            """.format(
                sync_type = sync_type,
                date_start = date_start,
                date_end = date_end
            )
            self.env.cr.execute(query)

            # cleansing product.category
            query = """
                update stock_ledger as a set 
                    odoo_category_id = b.id,
                    odoo_account_id = b.stock_valuation_id
                from product_category b 
                where a.sync_type = '{sync_type}'
                    and a.tglproses >= '{date_start}'
                    and a.tglproses <= '{date_end}'
                    and b.sync_type = a.sync_type
                    and b.sync_id = cast(a.category_id as integer)
            """.format(
                sync_type = sync_type,
                date_start = date_start,
                date_end = date_end
            )
            self.env.cr.execute(query)

            # cleansing product.product
            query = """
                update stock_ledger as a set 
                    odoo_product_id = pp.id
                from product_template b 
                inner join product_product pp on pp.product_tmpl_id = b.id
                where a.sync_type = '{sync_type}'
                    and a.tglproses >= '{date_start}'
                    and a.tglproses <= '{date_end}'
                    and b.sync_type = a.sync_type
                    and b.sync_id = cast(a.product_id as integer)
            """.format(
                sync_type = sync_type,
                date_start = date_start,
                date_end = date_end
            )
            self.env.cr.execute(query)

            # cleansing stock.lot
            # query = """
            #     update stock_ledger as a set 
            #         odoo_batch_id = b.id
            #     from stock_production_lot b 
            #     where a.sync_type = '{sync_type}'
            #         and a.tglproses >= '{date_start}'
            #         and a.tglproses <= '{date_end}'
            #         and b.sync_type = a.sync_type
            #         and b.sync_id = cast(a.batch_id as integer)
            # """.format(
            #     sync_type = sync_type,
            #     date_start = date_start,
            #     date_end = date_end
            # )
            # self.env.cr.execute(query)

            # cleansing uom.uom
            query = """
                update stock_ledger as a set 
                    odoo_uom_id = b.id
                from uom_uom b 
                where a.sync_type = '{sync_type}'
                    and a.tglproses >= '{date_start}'
                    and a.tglproses <= '{date_end}'
                    and b.sync_type = a.sync_type
                    and b.sync_id = cast(a.uom_id as integer)
            """.format(
                sync_type = sync_type,
                date_start = date_start,
                date_end = date_end
            )
            self.env.cr.execute(query)



    # update COGS Average khusus WIPRO
    # @api.multi
    def syncing_update(self):
        report_id = self.id 
        company_id = self.company_id.id
        sync_type = self.company_id.sync_type
        date_start = datetime.strptime(str(self.date_start), '%Y-%m-%d')
        date_end = datetime.strptime(str(self.date_end), '%Y-%m-%d')
        
        # if sync_type not in MHJS & MHTG
        if self.company_id.sync_type not in['1','2']:
            raise exceptions.ValidationError("Fitur ini hanya dapat dilakukan untuk Integrasi Wipro-Odoo MHTG/MHJS.")

       
        # reset semua odoo_cost
        query = """
            update stock_scrap as sol set 
                odoo_cost = 0,
                odoo_cost_total = 0,
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            where sol.company_id = {company_id}
                and sol.transaction_date >= '{date_start}'
                and sol.transaction_date <= '{date_end}'
        """.format(
            company_id=company_id, 
            date_start=date_start, 
            date_end=date_end,
            user_id=self.env.user.id 
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)

        # update odoo cost_total 
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write(str('\nStart update stock.scrap'))
        query = """
            update stock_scrap as sol set 
                odoo_cost = (case when coalesce(pcp.cost,0) = 0 then sol.cost else coalesce(pcp.cost,0) end),
                odoo_cost_total = ((case when coalesce(pcp.cost,0) = 0 then sol.cost else coalesce(pcp.cost,0) end) * sol.scrap_qty),
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            from product_product pp 
            inner join product_template pt on pt.id=pp.product_tmpl_id
            inner join product_price_history pcp on pcp.product_id=pp.id
            where pp.id = sol.product_id
                and date(pcp.datetime) = date('{date_end}')
                and coalesce(sol.odoo_cost,0) = 0
                and sol.company_id = {company_id}
                and sol.transaction_date >= '{date_start}'
                and sol.transaction_date <= '{date_end}'
        """.format(
            company_id=company_id,
            date_start=date_start, 
            date_end=date_end,
            user_id=self.env.user.id 
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)

        # update odoo AR
        query = """
            update stock_scrap as sol set 
                scrap_qty = ((case when sol.scrap_qty < 0 then 1 else -1 end) * sol.scrap_qty) ,
                cost_total = (((case when sol.scrap_qty < 0 then 1 else -1 end) * sol.scrap_qty) * sol.cost),
                odoo_cost_total = (((case when sol.scrap_qty < 0 then 1 else -1 end) * sol.scrap_qty) * sol.odoo_cost),
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            where sol.company_id = {company_id}
                and sol.transaction_date >= '{date_start}'
                and sol.transaction_date <= '{date_end}'
                and sol.trans_type in('AR','SE','PE')
        """.format(
            company_id=company_id, 
            date_start=date_start, 
            date_end=date_end,
            user_id=self.env.user.id 
        )
        open('/opt/odoo16/logs/stock_bulk_closing.log', 'a+').write('\n'+str(query))
        self.sudo().env.cr.execute(query)


        query = """
            update sale_order_line as sol set 
                cost_unit_odoo = (pcp.cost), 
                cost_total_odoo = (pcp.cost * sol.product_uom_qty),
                write_date = CURRENT_TIMESTAMP,
                write_uid = {user_id}
            from product_product pp 
            inner join product_template pt on pt.id=pp.product_tmpl_id
            inner join product_price_history pcp on pcp.product_id=pp.id
            where pp.id = sol.product_id
                and date(pcp.datetime) = date('{date_end}')
                -- and coalesce(sol.cost_unit,0) = 0
                and sol.service_categ_id in(
                    select id from product_category 
                    where name in ('Pharmacy','Drug','Drugs','Consumable','Consumables'))
                and sol.company_id = {company_id}
                and sol.tglproses >= '{date_start}'
                and sol.tglproses <= '{date_end}'
        """.format(
            company_id=company_id, 
            date_start=date_start, 
            date_end=date_end,
            user_id=self.env.user.id
        )
        open('/opt/odoo16/logs/sale_bulk_closing.log', 'a+').write('\n'+str(query))

        self.sudo().env.cr.execute(query)
        open('/opt/odoo16/logs/sale_bulk_closing.log', 'a+').write(str('\nDone'))
        print("Successfully to update sale.order.line")




    # @api.multi
    def syncing_costing(self):
        report_id = self.id 
        company_id = self.company_id.id
        sync_type = self.company_id.sync_type
        date_start = datetime.strptime(str(self.date_start), '%Y-%m-%d')
        date_end = datetime.strptime(str(self.date_end), '%Y-%m-%d')
        
        # if sync_type not in MHJS & MHTG
        if self.company_id.sync_type not in['1','2']:
            raise exceptions.ValidationError("Fitur ini hanya dapat dilakukan untuk Integrasi Wipro-Odoo MHTG/MHJS.")

        # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str('step 1'))
        # hapus dulu temporary cost price
        query = """
            DELETE FROM odoo10_product_price_history
            WHERE sync_type = '{sync_type}'
        """.format(sync_type=sync_type)
        # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)


        # sync price cost history
        query  = """
            SELECT
                a.sync_type,
                a.datetime,
                a.product_id,
                a.product_tmpl_id,
                a.cost
            FROM dbo.VRP_OdooPriceHistory a
            WHERE convert(varchar(10), a.datetime, 121) >= '{date_start}'
                AND convert(varchar(10), a.datetime, 121) <= '{date_end}'
        """.format(
            sync_type=sync_type, 
            date_start=date_start,
            date_end=date_end)
        # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str(query))
        result = self.sql_read(sync_type, query)
        # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str('step 2'))

        if result:
            # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str('step 3'))
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
                
                    if type(row[key]) in [str, bytes]:
                    # if type(row[key]) in [str, bytes, unicode]:
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
            
            excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
            columns = sync.remove_unicode(str(fields)).replace("'", "")
            columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")

            print (values)
            if not values:
                print ("No data available")
            # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str('step 4'))

            # insert replace existing data 
            query = """
                INSERT INTO odoo10_product_price_history %s VALUES %s 
            """ % (columns, values)
            print (query)
            self.env.cr.execute(query)
            # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str(query))

            # cleansing company_id
            query = """
                UPDATE odoo10_product_price_history as a SET company_id = b.id
                FROM res_company b WHERE b.sync_type = a.sync_type;
            """
            print (query)
            self.env.cr.execute(query)
            # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str(query))


            # cleansing res.company
            query = """
                UPDATE odoo10_product_price_history SET 
                    write_uid={user_id}, create_uid={user_id}, 
                    create_date=CURRENT_TIMESTAMP, 
                    write_date=CURRENT_TIMESTAMP
                WHERE sync_type = '{sync_type}'
            """.format(
                sync_type = sync_type,
                date_start = date_start,
                date_end = date_end,
                user_id = self.env.user.id)
            self.env.cr.execute(query)
            # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str('step 7'))


            # truncate consol data vendor wipro
            query = """
                DELETE FROM product_price_history
                WHERE sync_type = '{sync_type}'
                    AND date(datetime) >= '{date_start}'
                    AND date(datetime) <= '{date_end}'
            """.format(
                sync_type=sync_type,
                date_start=date_start,
                date_end=date_end)
            print (query)
            self.env.cr.execute(query)
            # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str('step 8'))


            # sync price cost history
            query  = """
                SELECT DISTINCT
                    a.write_date,
                    a.create_date,
                    a.write_uid,
                    a.create_uid,
                    a.company_id,
                    a.datetime,
                    a.cost,
                    a.sync_type,
                    b.product_tmpl_id,
                    b.product_id
                FROM odoo10_product_price_history a 
                LEFT JOIN LATERAL (
                    SELECT 
                        pp.product_tmpl_id,
                        pp.id product_id
                    FROM product_template pt 
                    INNER JOIN product_product pp ON pp.product_tmpl_id = pt.id
                    WHERE pt.sync_type = a.sync_type
                        AND pt.sync_id = a.product_tmpl_id
                    ORDER BY pp.id ASC LIMIT 1
                ) b on 1=1
                
                WHERE a.sync_type = '{sync_type}'
                    AND b.product_id is not null
            """.format(
                sync_type=sync_type, 
                date_start=date_start,
                date_end=date_end)
            # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str(query))
            self.env.cr.execute(query)
            result2 = self.env.cr.dictfetchall()
            # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str('step 9'))
            
            if result2:
                # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str('step 10'))
                fields_without_id = tuple(key for key in result2[0] if key not in['id','sync_type'])
                fields = tuple(key for key in result2[0] if key)
                values = ''

                for row in result2:
                    if values:
                        values += ', '

                    value = ''
                    for key in fields:
                        if value:
                            value += ', '
                        else:
                            value = '('
                    
                        if type(row[key]) in [str, bytes]:
                        # if type(row[key]) in [str, bytes, unicode]:
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
                
                excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                columns = sync.remove_unicode(str(fields)).replace("'", "")
                columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")

                print (values)
                if not values:
                    print ("No data available")
                # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str('step 11'))

                # insert replace existing data 
                query = """
                    INSERT INTO product_price_history %s VALUES %s 
                """ % (columns, values)
                print (query)
                self.env.cr.execute(query)
                # open('/opt/odoo16/logs/log_syncing_costing.log','a+').write('\n\n' + str(query))
            
            
        

    # @api.multi
    def syncing_scrap(self):
        report_id = self.id 
        company_id = self.company_id.id
        sync_type = self.company_id.sync_type
        date_start = datetime.strptime(str(self.date_start), '%Y-%m-%d')
        date_end = datetime.strptime(str(self.date_end), '%Y-%m-%d')
        
        # if sync_type not in MHJS & MHTG
        if self.company_id.sync_type not in['1','2']:
            raise exceptions.ValidationError("Fitur ini hanya dapat dilakukan untuk Integrasi Wipro-Odoo MHTG/MHJS.")

       
        # truncate consol data vendor wipro
        query = """
            DELETE FROM odoo10_stock_scrap
            WHERE sync_type = '{sync_type}'
        """.format(sync_type=sync_type)
        self.env.cr.execute(query)

        # select query from staging DB
        query  = """
            SELECT
                a.sync_id_api,
                a.TransType 'trans_type',
                a.ConsumptionNo 'origin',
                a.ConsumptionNo 'name',
                convert(varchar(10), a.ConsumptionDate, 121) 'transaction_datetime',
                convert(varchar(10), a.ConsumptionDate, 121) 'transaction_date',
                a.ConsumptionDate 'date_expected',
                a.ConsumptionDate 'create_date',
                a.ConsumptionID 'sync_id',
                a.ItemID 'product_id',
                a.ServiceID 'service_categ_id',
                a.CategoryID 'categ_id',
                a.HospDeptId 'location_id',
                4 'scrap_location_id',
                a.BatchNo 'batch_no',
                a.UoMID 'product_uom_id',
                a.Quantity 'scrap_qty',
                a.UEPR 'cost',
                a.Total 'cost_total',
                'draft' 'state',
                '{sync_type}' sync_type
            FROM dbo.VRP_OdooAdjustmentIssue a
            WHERE convert(varchar(10), a.ConsumptionDate, 121) >= '{date_start}'
                AND convert(varchar(10), a.ConsumptionDate, 121) <= '{date_end}'
        """.format(
            sync_type=sync_type, 
            date_start=date_start,
            date_end=date_end)    
        result = self.sql_read(sync_type, query)
        

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
                
                    if type(row[key]) in [str, bytes]:
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
            
            excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
            columns = sync.remove_unicode(str(fields)).replace("'", "")
            columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")

            print (values)
            if not values:
                print ("No data available")

            # insert replace existing data 
            query = """
                INSERT INTO odoo10_stock_scrap %s VALUES %s 
                ON CONFLICT (id, sync_type) DO UPDATE SET %s = %s
            """ % (columns, values, columns_without_id, excluded)
            self.env.cr.execute(query)

        
            # cleansing company_id
            query = """
                UPDATE odoo10_stock_scrap as a SET company_id = b.id
                FROM res_company b WHERE b.sync_type = a.sync_type;
            """
            self.env.cr.execute(query)

            # cleansing default data parameter
            ### sementara cleansing default nya segini dlu buat di tanya ambil darimana enak nya
            query = """
                UPDATE odoo10_stock_scrap SET 
                write_uid={user_id}, create_uid={user_id}, 
                create_date=CURRENT_TIMESTAMP, 
                write_date=CURRENT_TIMESTAMP,
                sync_date=CURRENT_TIMESTAMP, 
                sync_consol_date=CURRENT_TIMESTAMP
                WHERE sync_type = '{sync_type}'
            """.format(sync_type=sync_type, user_id=self.env.user.id)
            self.env.cr.execute(query)

            # fetch data for update 
            query = """
                SELECT DISTINCT
                    coalesce(b.id, 0) id,
                    coalesce(b.state, a.state) state,
                    (case a.trans_type 
                        when 'SC' then 'consumption' 
                        when 'AI' then 'adjustment_issue'
                        when 'AR' then 'adjustment_receipt'
                        when 'PI' then 'prepared_item'
                        when 'SE' then 'prepared_receipt'
                        else 'scrap' end) transaction_type,
                    a.trans_type, a.origin, a.name, a.date_expected,
                    a.transaction_date, a.transaction_datetime, 
                    (case when a.trans_type in ('AR','SE','PE') then sl2.id else sl1.id end) as location_id, 
                    (case when a.trans_type in ('AR','SE','PE') then sl1.id else sl2.id end) as scrap_location_id, 
                    a.batch_no, a.scrap_qty, a.cost, a.cost_total, a.company_id,
                    coalesce(b.service_categ_id, sc.id) as service_categ_id, 
                    coalesce(b.categ_id, pc.id) as categ_id, 
                    coalesce(b.product_id, pp.id) as product_id, 
                    coalesce(b.product_uom_id, pu.id) as product_uom_id, 
                    coalesce(b.create_uid,a.create_uid) create_uid, 
                    coalesce(b.create_date,a.create_date) create_date,
                    a.write_uid, a.write_date, 
                    a.sync_id, a.sync_id_api, a.sync_type
                FROM odoo10_stock_scrap a 
                LEFT JOIN LATERAL (
                    SELECT * FROM stock_scrap b 
                    WHERE b.sync_type=a.sync_type 
                    AND b.sync_id_api=a.sync_id_api
                    ORDER BY id ASC LIMIT 1
                ) b on 1=1
                LEFT JOIN LATERAL (
                    SELECT * FROM product_category sc 
                    WHERE sc.sync_type=a.sync_type 
                    AND sc.sync_id=a.service_categ_id
                    AND sc.sync_is_service is True
                    AND sc.sync_is_category is not True
                    AND sc.active is True
                    ORDER BY id ASC LIMIT 1
                ) sc on 1=1
                LEFT JOIN LATERAL (
                    SELECT * FROM product_category pc 
                    WHERE pc.sync_type=a.sync_type 
                    AND pc.sync_id=a.categ_id
                    AND pc.sync_is_service is not True
                    AND pc.sync_is_category is True
                    AND pc.active is True
                    ORDER BY id ASC LIMIT 1
                ) pc on 1=1
                LEFT JOIN LATERAL (
                    select sl.id
                    from stock_location sl
                    where sl.sync_type = a.sync_type 
                        and sl.sync_id=a.location_id 
                        and sl.active=True
                    order by id asc limit 1
                ) sl1 on 1=1
                LEFT JOIN LATERAL (
                    select sl.id
                    from stock_location sl
                    where sl.id = 4 -- sl.sync_type = a.sync_type and sl.sync_id = a.scrap_location_id 
                        and sl.active = True
                    order by id asc limit 1
                ) sl2 on 1=1
                LEFT JOIN LATERAL (
                    select pp.id 
                    from product_product pp
                    inner join product_template pt on pt.id = pp.product_tmpl_id
                    where pt.sync_type = a.sync_type 
                        and pt.sync_id = a.product_id 
                        and pt.active = True
                    order by id asc limit 1
                ) pp on 1=1
                LEFT JOIN LATERAL (
                    select pu.id 
                    from uom_uom pu
                    where pu.sync_type = a.sync_type 
                        and pu.sync_id = a.product_uom_id 
                        and pu.active = True
                    order by id asc limit 1
                ) pu on 1=1
                WHERE a.sync_type = '{sync_type}'
            """.format(sync_type=sync_type)
            self.env.cr.execute(query)
            result = self.env.cr.dictfetchall()
        
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
                        
                        if key == 'id' and row[key] == 0:
                            value += 'DEFAULT'
                            continue 
                    
                        if type(row[key]) in [str, bytes]:
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
                
                excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
                columns = sync.remove_unicode(str(fields)).replace("'", "")
                columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")

                print (values)
                if not values:
                    print ("No data available")
            
                # insert replace existing data 
                query = """
                    INSERT INTO stock_scrap %s VALUES %s 
                    ON CONFLICT (id) DO UPDATE SET %s = %s
                """ % (columns, values, columns_without_id, excluded)
                self.env.cr.execute(query)



                query = """
                    UPDATE stock_scrap 
                    SET cost_total = cost * scrap_qty 
                    WHERE cost_total is null
                    AND sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                self.env.cr.execute(query)

                query = """
                    UPDATE stock_scrap as sc
                    SET categ_id = (
                        select categ_id from product_template 
                        where id = (select product_tmpl_id from product_product where id = sc.product_id)) 
                    WHERE categ_id is null
                    AND sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                self.env.cr.execute(query)

                query = """
                    UPDATE stock_scrap
                    set service_categ_id = (
                        select (case when parent_id is not null then parent_id else id end) 
                        from product_category 
                        where id = (
                            select categ_id from product_template 
                            where id = (select product_tmpl_id 
                                from product_product 
                                where id = stock_scrap.product_id))) 
                    where service_categ_id is null
                    and sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                self.env.cr.execute(query)

                query = """
                    UPDATE stock_scrap
                    SET service_categ_id = (
                        select (case when parent_id is not null then parent_id else id end)
                        FROM product_category
                        where id = stock_scrap.service_categ_id)
                    WHERE service_categ_id is null 
                    AND sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                self.env.cr.execute(query)

                query = """
                    UPDATE stock_scrap set cost_total = cost_total * -1 
                    WHERE cost_total > 0 
                    AND trans_type in ('AR','SE','PE')
                    AND sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                self.env.cr.execute(query)

                query = """
                    UPDATE stock_scrap set cost = cost * -1 
                    where cost_total > 0 
                    and trans_type in ('AR','SE','PE')
                    AND sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                self.env.cr.execute(query)


                query = """
                    UPDATE stock_scrap set scrap_location_id = location_id 
                    where location_id <> 4 
                    and trans_type in ('AR','SE','PE')
                    AND sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                self.env.cr.execute(query)

                query = """
                    UPDATE stock_scrap set location_id = 4 
                    where scrap_location_id <> 4 
                    and trans_type in ('AR','SE','PE')
                    AND sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                self.env.cr.execute(query)


                # truncate consol data
                query = """
                    DELETE FROM odoo10_stock_scrap 
                    WHERE sync_type = '{sync_type}'
                """.format(sync_type=sync_type)
                self.env.cr.execute(query)




# 2022.11.08 - Firgiawan Khafidli
# Stock ledger report untuk export stock ledger analysis odoo sesuai kebutuhan user.
class StockLedgerReportWizard(models.TransientModel):
    _name = 'stock.ledger.report.wizard'

    @api.model
    def _get_user_id(self):
        return self.env.user.id

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', string="Company", required=False, default=_get_company)
    user_id = fields.Many2one('res.users', string="User ID", default=_get_user_id)
    start_date = fields.Date(string="Date Start", required=True)
    end_date = fields.Date(string="Date End", required=True)

    consignment = fields.Selection([
        ('2', 'All'),
        ('0', 'Consignment'),
        ('1', 'Non Consignment')
    ], default='2', string="Consignment")

    medical_type = fields.Selection([
        ('2', 'All'),
        ('0', 'Medic'),
        ('1', 'Non Medic')
    ], default='2', string="Medical Type")

    bpjs = fields.Selection([
        ('2', 'All'),
        ('0', 'Non BPJS'),
        ('1', 'BPJS')
    ], default='2', string="BPJS")


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(StockLedgerReportWizard,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Stock Ledger Report" delete="false">
                    <style>
                      .o_control_panel { display: none; }
                    </style>
                    
                    <group>
                        <group>
                            <field name="company_id" readonly="1" />
                            <field name="user_id" invisible="1"/>
                            <field name="start_date" />
                            <field name="end_date" />
                        </group>
                        <group> 
                            <field name="medical_type" required="1" />
                            <field name="consignment" required="1" />
                            <field name="bpjs" required="1" />
                        </group>
                    </group>
                    <footer>
                        <button name="show_report" string="Export Excel" type="object" class="oe_highlight" />
                    </footer>
                </form>
           """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


    # @api.multi
    def show_report(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/report/stock_ledger_report?id=' + str(self.id)
        action['target'] = 'new'
        return action


# 2022.08.25 - Stock Ledger Reconcile
class StockLedgerReconcile(models.TransientModel):
    _name = 'stock.ledger.reconcile.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id

    @api.model
    def _get_user(self):
        return self.env.user.id 
    

    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    date_start = fields.Date(string="Date Start", store=True, index=True)
    date_end = fields.Date(string="Date End", store=True, index=True)
    user_id = fields.Many2one('res.users', string="Responsible", default=_get_user)
    remark = fields.Char(string="Remarks")
    line_ids = fields.One2many('stock.ledger.reconcile.line', 'wizard_id', string="Lines")

    # @api.multi
    def button_compute(self):
        report_id = self.id 
        company_id = self.company_id.id
        sync_type = self.company_id.sync_type
        year_start = datetime.strptime(str(self.date_start), '%Y-%m-%d').strftime('%Y-01-01')
        date_start = datetime.strptime(str(self.date_start), '%Y-%m-%d')
        date_end = datetime.strptime(str(self.date_end), '%Y-%m-%d')
        
        # if sync_type not in MHJS & MHTG
        if self.company_id.sync_type not in['1','2','9','10','11','13']:
            raise exceptions.ValidationError("Fitur ini hanya dapat dilakukan untuk Integrasi Wipro-Odoo MHTG/MHJS.")

        query = """
            SELECT COUNT(*) hitung
            FROM stock_ledger t
            WHERE t.company_id = {company_id}
                AND date(t.tglproses) >= '{date_start}'
                AND date(t.tglproses) <= '{date_end}'
        """.format(
            company_id=company_id,
            date_start=date_start,
            date_end=date_end
        )
        open('/opt/odoo16/logs/log_stock_ledger_reconcile.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)
        result = self.env.cr.dictfetchall()

        if result[0]['hitung'] == 0:
            raise exceptions.ValidationError("Stock Ledger dari WIPRO masih kosong, silahkan lakukan syncronize terlebih dahulu.")

        query = """
            DELETE FROM stock_ledger_reconcile_line 
            WHERE wizard_id = {wizard_id}
            """ .format(wizard_id = self.id)
        self.env.cr.execute(query)

        query = """
            INSERT INTO stock_ledger_reconcile_line(
                wizard_id, account_id, account_balance,
                stock_balance, variance_balance,
                variance_account_id, 
                variance_analytic_id, write_uid, create_uid, write_date, create_date
            )
            SELECT
                {wizard_id} wizard_id, 
                a.account_id, 
                a.account_balance,
                b.stock_balance, 
                (coalesce(b.stock_balance,0) - coalesce(a.account_balance,0)) variance_balance,
                c.variance_account_id, 
                d.variance_analytic_id, {user_id} write_uid, {user_id} create_uid, now() write_date, now() create_date
            FROM (
                SELECT 
                    a.company_id, 
                    a.id account_id, 
                    a.code account_code,
                coalesce(am.account_balance,0) account_balance
                FROM account_account a
                LEFT JOIN (
                    SELECT am.company_id, 
                        aml.account_id, 
                    aa.code account_code,
                    sum(aml.balance) account_balance
                    FROM account_move am 
                INNER JOIN account_move_line aml ON aml.move_id=am.id
                INNER JOIN account_account aa ON aa.id = aml.account_id
                WHERE am.company_id = {company_id}
                        AND date(am.date) >= date('{year_start}')
                    AND date(am.date) <= date('{date_end}')
                    AND aa.code in('1106010000','1106020000', '1106010010','1106020010')
                    --AND aml.year_close is not True
                    AND am.state = 'posted'
                GROUP BY am.company_id, aml.account_id, aa.code
                ) am on am.account_id = a.id  
                WHERE a.company_id = {company_id}
                        AND a.code in('1106010000','1106020000', '1106010010','1106020010')
                    
            ) AS a 
            LEFT JOIN LATERAL(
                SELECT SUM(t.cost_total) stock_balance
                FROM stock_ledger t
                WHERE t.company_id = {company_id}
                    AND date(t.tglproses) >= '{date_start}'
                    AND date(t.tglproses) <= '{date_end}'
                    AND t.consignment = '0'
                    AND t.medical_type = (CASE 
                        WHEN a.account_code = '1106010000' THEN '0'
                        WHEN a.account_code = '1106010010' THEN '0'
                        WHEN a.account_code = '1106020000' THEN '1'
                        WHEN a.account_code = '1106020010' THEN '1'
                    END)
                    AND t.bpjs = (CASE 
                        WHEN a.account_code = '1106010000' THEN '0'
                        WHEN a.account_code = '1106020000' THEN '0'
                        WHEN a.account_code = '1106010010' THEN '1'
                        WHEN a.account_code = '1106020010' THEN '1'
                    END)
            ) AS b ON 1=1
            LEFT JOIN LATERAL (
                SELECT t.id variance_account_id
                FROM account_account t 
                WHERE t.company_id = {company_id}
                    AND t.code = '7999040000'
                    AND t.deprecated = False
                LIMIT 1
            ) AS c ON 1=1
            LEFT JOIN LATERAL (
                SELECT t.id variance_analytic_id
                FROM account_analytic_account t 
                WHERE t.company_id = {company_id}
                    AND t.code = '7999040000 - 701 - 00'
                    AND t.active = True
                LIMIT 1
            ) AS d ON 1=1
        """.format(
            wizard_id=self.id, 
            company_id=company_id,
            year_start =year_start,
            date_start=date_start,
            date_end=date_end,
	    user_id=self.env.user.id
        )
        open('/opt/odoo16/logs/log_stock_ledger_reconcile.log','a+').write('\n\n' + str(query))
        self.env.cr.execute(query)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Reconcile Stock Ledger vs Inventory',
            'view_mode': 'form', 
            'target': 'new',
            'res_id': self.id,
            'res_model': 'stock.ledger.reconcile.wizard',
            'context': {'default_id': self.id} 
        }



    # @api.multi
    def button_journal(self):
        report_id = self.id 
        company_id = self.company_id.id
        sync_type = self.company_id.sync_type
        date_start = datetime.strptime(str(self.date_start), '%Y-%m-%d')
        date_end = datetime.strptime(str(self.date_end), '%Y-%m-%d')
        
        # if sync_type not in MHJS & MHTG
        if self.company_id.sync_type not in['1','2','9','10','11','13']:
            raise exceptions.ValidationError("Fitur ini hanya dapat dilakukan untuk Integrasi Wipro-Odoo MHTG/MHJS.")

       
        query = """
            SELECT 
                abs(a.variance_balance) amount, 
                'STOCK LEDGER RECONCILE' service_label, 
                (CASE WHEN a.variance_balance < 0 THEN a.variance_account_id ELSE a.account_id END) account_debit_id,
                (CASE WHEN a.variance_balance < 0 THEN a.account_id ELSE a.variance_account_id END) account_credit_id,
                (CASE WHEN a.variance_balance < 0 THEN COALESCE(a.variance_analytic_id, 0) ELSE 0 END) analytic_debit_id,
                (CASE WHEN a.variance_balance < 0 THEN 0 ELSE COALESCE(a.variance_analytic_id, 0) END) analytic_credit_id
            FROM stock_ledger_reconcile_line a 
            WHERE a.wizard_id = {wizard_id}
            """ .format(wizard_id = self.id)
        self.env.cr.execute(query)
        lines = self.env.cr.dictfetchall()
        if not lines:
            print ("There are no lines to make journal")
            return

        move_lines = []
        for line in lines:
           
            if int(line['analytic_credit_id']) > 0:
                move_lines.append([0, 0, {
                    'name':str(line['service_label']), 
                    'analytic_account_id':int(line['analytic_credit_id']), 
                    'account_id':int(line['account_credit_id']), 
                    'debit':0.0, 
                    'credit':line['amount'] or 0.0, 
                    'map_journal':True
                }])
            else:
                move_lines.append([0, 0, {
                    'name':str(line['service_label']), 
                    'account_id':int(line['account_credit_id']), 
                    'debit':0.0, 
                    'credit':line['amount'] or 0.0, 
                }])
            
            if int(line['analytic_debit_id']) > 0:
                move_lines.append([0, 0, {
                    'name':str(line['service_label']), 
                    'analytic_account_id':int(line['analytic_debit_id']), 
                    'account_id':int(line['account_debit_id']), 
                    'credit':0.0, 
                    'debit':line['amount'] or 0.0, 
                    'map_journal':True
                }])
            else:
                move_lines.append([0, 0, {
                    'name':str(line['service_label']), 
                    'account_id':int(line['account_debit_id']), 
                    'credit':0.0, 
                    'debit':line['amount'] or 0.0
                }])
            
        journal_id = self.env['account.journal'].search([('name', 'ilike', 'Stock Reconcile'),('company_id', '=', company_id)],limit=1).id
        self.env['account.move'].create({'journal_id':journal_id,'line_ids':move_lines,'date':date_end, 'ref': 'STOCK RECONCILE at ' + str(date_end)})
        




class StockLedgerReconcileLine(models.TransientModel):
    _name = 'stock.ledger.reconcile.line'

    wizard_id = fields.Many2one('stock.ledger.reconcile.wizard', string="Wizard")
    account_id = fields.Many2one('account.account', string="Supply Account")
    account_balance = fields.Float(string='Supply Balance (Odoo)')
    stock_balance = fields.Float(string='Stock Balance (HIS)')
    variance_balance = fields.Float(string='Variance')
    variance_account_id = fields.Many2one('account.account', string="Adjust Account")
    variance_analytic_id = fields.Many2one('account.analytic.account', string="Adjust Analytic")


class StockLedgerWizard(models.TransientModel):
    _name = 'stock.ledger.wizard'

    @api.model
    def _get_user_id(self):
        return self.env.user.id

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', string="Company", required=False, default=_get_company)
    user_id = fields.Many2one('res.users', string="User ID", default=_get_user_id)
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(StockLedgerWizard,self).get_view(view_id=view_id,view_type=view_type, **options)        
        if view_type == 'form':
            res['arch'] = """
                <form string="Stock Ledger Analysis" delete="false">
                    <style>
                      .o_control_panel {
                          display: none;
                      }
                    </style>
                    <sheet>
                    <h1>
                        Stock Ledger Analysis
                    </h1>
                    <group>
                        <group>
                            <field name="company_id" readonly="1" />
                            <field name="user_id" invisible="1"/>
                        </group>
                        <group> 
                            <field name="start_date" />
                            <field name="end_date" />
                        </group>
                    </group>
                    
                    <button name="show_report" string="Show Analysis" type="object" class="oe_highlight" />
                    </sheet>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # @api.multi
    def show_report(self):
        # open('/opt/odoo16/logs/stock_ledger_analysis.log','a+').write('\n' + 'Start')
        action = {}
        action['target'] = 'current'
        
        if self.company_id:
            action['domain'] = "[('tglproses', '>=', '%s'), ('tglproses', '<=', '%s'), ('company_id', '=', %s)]" % (self.start_date, self.end_date, self.company_id.id)
        else:
            action['domain'] = "[('tglproses', '>=', '%s'), ('tglproses', '<=', '%s')]" % (self.start_date, self.end_date)
        
        # open('/opt/odoo16/logs/stock_ledger_analysis.log','a+').write('\n' + str(action['domain']) + '\n' + 'domain show report')
        action['type'] = 'ir.actions.act_window'
        action['view_mode'] = 'tree,form,pivot'
        action['view_type'] = 'form'
        action['res_model'] = 'stock.ledger'
        action['name'] = 'Stock Ledger Analysis Report'
        # action['context'] = {'view_pivot_id': 'view_stock_ledger_analysis' }
        action['views'] = [(self.sudo().env.ref('mayapada.view_stock_ledger_analysis').id, 'pivot'), (False, 'tree'), (False, 'form')]
        return action






# 2021.08.25 StockScrap Compiled Report
# Untuk menampilkan seluruh report stock scrap C, AI, AR, LB, BR
class StockScrapCompiledWizard(models.TransientModel):
    _name = 'stock.scrap.compiled.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    location_id = fields.Many2one('stock.location', string='Facility', required=False, domain=[('usage','=','internal')])
    category_id = fields.Many2one('product.category', string='Category', required=False)    
    report_type = fields.Selection([
            ('SC','Store Consumption'),
            ('AI','Adjustment Issue'),
            ('AR','Adjustment Receipt'),
            ('PI','Prepared Item'),
            ('SE','Prepared Receipt'),
            ('BR','Breakage'),
            ('LB','Loss Breakage')], required=False, string='Trans Type')
    date_start = fields.Date(string='Date Start', required=False)
    date_end = fields.Date(string='Date End', required=False)
    format_print_id = fields.Selection([('pdf','PDF'),('xls','EXCEL')], string="Format", required=True, default='xls')

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(StockScrapCompiledWizard,self).get_view(view_id=view_id,view_type=view_type, **options)        
        if view_type == 'form':
            res['arch'] = """
                <form string="Store Scrap Compiled Report">
                    <group>
                        <group>
                            <field name="company_id" />
                            <field name="report_type" />
                            <field name="format_print_id" />
                        </group>
                        <group>
                            <field name="location_id" domain="[('company_id','=',company_id)]" />
                            <field name="category_id" domain="[('company_id','=',company_id)]"  />
                            <field name="date_start" />
                            <field name="date_end" />
                        </group>
                    </group>
                    <footer>
                        <button name="print_all" string="Print" type="object" class="oe_highlight"/>
                    </footer>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # @api.multi
    def print_all(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/inventory/stock_scrap_report?id=' + str(self.id)
        action['target'] = 'new'
        return action





# 2021.08.26 - Stock Movement Compiled Report 
# Kebutuhan report u/ Pergerakan Stock Inventory
class StockMovementCompiledWizard(models.TransientModel):
    _name = 'stock.movement.compiled.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    location_id = fields.Many2one('stock.location', string='Facility', domain=[('usage','=','internal')])
    category_id = fields.Many2one('product.category', string='Category')
    product_id = fields.Many2one('product.product', string='Product')
    date_start = fields.Date(string='Date Start', required=False)
    date_end = fields.Date(string='Date End', required=False)
    report_type = fields.Selection([('detail','Movement Detail'),('summary','Movement Summary')], string="Report Type", required=True, default='summary')
    format_print_id = fields.Selection([('pdf','PDF'),('xls','EXCEL')], string="Format", required=True, default='xls')
    
    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(StockMovementCompiledWizard,self).get_view(view_id=view_id,view_type=view_type, **options)        
        if view_type == 'form':
            res['arch'] = """
                <form string="Stock Movement Compiled Report">
                    <group>
                        <group>
                            <field name="company_id" />
                            <field name="report_type" />
                            <field name="format_print_id" />
                        </group>
                        <group>
                            <field name="location_id"  domain="[('company_id','=',company_id)]" />
                            <field name="category_id" attrs="{'invisible': [('report_type','!=','summary')]}"  domain="[('company_id','=',company_id)]" />
                            <field name="product_id" attrs="{'invisible': [('report_type','!=','detail')]}" domain="[('company_id','=',company_id),('type','=','product')]" />                        
                            
                            <field name="date_start" />
                            <field name="date_end" />                        
                        </group>
                    </group>
                    <footer>
                        <button name="print_all" string="Print" type="object" class="oe_highlight"/>
                    </footer>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # @api.multi
    def print_all(self):
        if self.report_type == 'detail':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/inventory/stock_movement_detail_report?id=' + str(self.id)
            action['target'] = 'new'
            return action
        if self.report_type == 'summary':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/inventory/stock_movement_summary_report?id=' + str(self.id)
            action['target'] = 'new'
            return action


# 2021.08.26 - Stock Valuation Report 
# Menampilkan nilai valuation inventory Odoo based on Facility, Category, Product
class StockValuationCompiledWizard(models.TransientModel):
    _name = 'stock.valuation.compiled.wizard'
    
    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', string="Company", required=True, default=_get_company)
    location_id = fields.Many2one('stock.location', string='Facility', required=False, domain=[('usage','=','internal')])
    category_id = fields.Many2one('product.category', string='Category', required=False)
    product_id = fields.Many2one('product.product', string='Product', required=False)
    date_as = fields.Date(string='Date As', required=False)
    report_type = fields.Selection([('supply','Supply Inventory'),('summary','StockWise Summary By Category'),('detail','StockWise Detail By Product'),('location','StockWise By Location')], string="Report Type", required=True, default='summary')
    format_print_id = fields.Selection([('pdf','PDF'),('xls','EXCEL')], string="Format", required=True, default='xls')

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(StockValuationCompiledWizard,self).get_view(view_id=view_id,view_type=view_type, **options)        
        if view_type == 'form':
            res['arch'] = """
                <form string="Stock Valuation Compiled Report">
                    <group>
                        <group>
                            <field name="company_id" />
                            <field name="format_print_id" />
                        </group>
                        <group>
                            <field name="report_type" />
                            <field name="location_id" attrs="{'invisible': [('report_type','!=','location')]}" domain="[('company_id','=',company_id)]" />
                            <field name="product_id" attrs="{'invisible': [('report_type','!=','detail')]}" domain="[('company_id','=',company_id),('type','=','product')]" />                        
                            <field name="date_as" /> 
                        </group>
                    </group>
                    <footer>
                        <button name="print_all" string="Print" type="object" class="oe_highlight"/>
                    </footer>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # @api.multi
    def print_all(self):
        if self.report_type == 'supply':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/inventory/stock_supply_inventory?id=' + str(self.id)
            action['target'] = 'new'
            return action
        if self.report_type == 'summary':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/inventory/stock_summary_category?id=' + str(self.id)
            action['target'] = 'new'
            return action
        if self.report_type == 'detail':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/inventory/stock_detail_product?id=' + str(self.id)
            action['target'] = 'new'
            return action
        if self.report_type == 'location':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/inventory/stock_location?id=' + str(self.id)
            action['target'] = 'new'
            return action







# 2021.09.09 - Custom Stock Location 
class StockLocation(models.Model):
    _inherit = 'stock.location'

    # @api.multi
    def get_putaway_strategy(self, product):
        ''' Returns the location where the product has to be put, if any compliant putaway strategy is found. Otherwise returns None.'''
        current_location = self
        putaway_location = self.env['stock.location']
        # while current_location and not putaway_location:
        #     if current_location.putaway_strategy_id:
        #         putaway_location = current_location.putaway_strategy_id.putaway_apply(product)
        #     current_location = current_location.location_id
        return putaway_location


    sync_id = sync.id
    sync_date = sync.date
    sync_id_api = sync.id_api
    sync_type = sync.type
    sync_is_arcus = sync.is_arcus
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    is_mainstore = fields.Boolean(string="Is MainStore", default=False)
    is_substore = fields.Boolean(string="Is SubStore", default=False)
    is_cartstore = fields.Boolean(string="Is CartStore", default=False) 
    # rack_ids = fields.One2many('master.rack', 'location_id', string="Rack") 
    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    parent_left = fields.Integer(string="Left Parent", index=True)
    parent_right = fields.Integer(string="Right Parent", index=True)
    putaway_strategy_id = fields.Many2one('product.putaway', string="Put Away Strategy")
    partner_id = fields.Many2one('res.partner', string="Owner")


    @api.model
    def _sync_department_api(self, sync_type='4'):
         sync_ids = {key: value for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id_api', '!=', False)]) for key, value in zip([record.sync_id_api, record.name], [record.id, record.id])}
         sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
         now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
         data = [{'name': record.name, 'sync_id_api': record.sync_id_api, 'sync_type': record.sync_type, 'is_mainstore':record.is_mainstore, 'is_substore':record.is_substore, 'is_cartstore':record.is_cartstore, 'sync_date': now} for record in self.env['hr.department'].sudo().search([('sync_type', '=', sync_type), ('is_store', '=', True)])]
         for object in data:
             if object['sync_id_api'] in sync_ids:
                 id = sync_ids.get(object['sync_id_api'])
                 self.sudo().browse(id).write(object)
             else:
                 self.sudo().create(object)
                 
class StockLedger(models.Model):
    _name = 'stock.ledger'
    _rec_name = 'trans_no'
    # _inherit = ['mail.thread', 'ir.needaction_mixin']

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_is_arcus = sync.is_arcus
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    company_id = fields.Many2one('res.company', index=True, string='Company', default=_get_company)
    tglproses = fields.Date(string="TglProses", index=True)
    trans_type = fields.Char(string="Trans Type", index=True)
    trans_subtype = fields.Char(string="Trans Sub Type", index=True)
    trans_date = fields.Date(string="Trans Date", index=True)
    trans_datetime = fields.Datetime(string="Trans Datetime", index=True)
    trans_direction = fields.Selection([('1', 'Stock In'),('-1', 'Stock Out'),('0', 'Stock Initial')], string="Trans Direction", index=True)
    trans_internal = fields.Selection([('1','Internal Transfer'), ('0', 'In-Out Transfer')], string="Stock Transfer")
    trans_no = fields.Char(string="Transaction No.", index=True)
    department_id = fields.Char(string="Department ID", index=True)
    department_name = fields.Char(string="Department Name", index=True)
    category_id = fields.Char(string="Category ID", readonly=False, store=True, index=True)
    category_name = fields.Char(string="Category Name", readonly=True, store=True, index=True)
    discontinue = fields.Selection([('1','Discontinue'),('0', 'Continue')], string="Discontinue", index=True)
    stat_department = fields.Selection([('1','Inactive'),('0', 'Active')], string="Blocked Department", index=True)
    
    consignment = fields.Selection([('1','Consignment'),('0', 'Non Consignment')], string="Consignment", index=True)
    bpjs = fields.Selection([('1','BPJS'),('0', 'Non BPJS')], string="BPJS", index=True)

    product_id = fields.Char(string="Product ID", store=True, index=True)
    product_code = fields.Char(string="Product Code", store=True, index=True)
    product_name = fields.Char(string="Product Name", store=True, index=True)
    medical_type = fields.Selection([('0', 'Medic'), ('1', 'Non Medic')], string="Medical Type", index=True)
    batch_id = fields.Char(string="Batch ID", index=True)
    batch_no = fields.Char(string="Batch No.", index=True)
    product_qty = fields.Float(string="Quantity")
    uom_id = fields.Char(string="UoM ID")
    uom_name = fields.Char(string="UoM", index=True)
    
    odoo_account_id = fields.Many2one('account.account', string="Account", index=True)
    odoo_department_id = fields.Many2one('stock.location', string="Odoo Department", index=True)
    odoo_category_id = fields.Many2one('product.category', string="Odoo Category", readonly=False, store=True, index=True)
    odoo_product_id = fields.Many2one('product.product', string="Odoo Product", store=True, index=True)
    odoo_batch_id = fields.Many2one('stock.lot', string="Odoo Batch", index=True)
    odoo_uom_id = fields.Many2one('uom.uom', string="Odoo UoM", index=True)

    cost_unit = fields.Float(string="Cost Unit")
    cost_total = fields.Float(string="Cost Total")

    prev_cost_unit = fields.Float(string="Prev Cost Unit")
    prev_cost_total = fields.Float(string="Prev Cost Total")

    grn_unit = fields.Float(string="GRN Unit")
    grn_total = fields.Float(string="GRN Total")





# 2021.09.09 - Stock Warehouse 
class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    sync_date = sync.date
    sync_id_api = sync.id_api
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    default_resupply_wh_id = fields.Many2one('stock.warehouse', string="Default Resupply Warehouse")


class StockImmediateTransfer(models.TransientModel):
    _inherit = 'stock.immediate.transfer'
    _description = 'Immediate Transfer'

    def process(self):
        pickings_to_do = self.env['stock.picking']
        pickings_not_to_do = self.env['stock.picking']
        for line in self.immediate_transfer_line_ids:
            if line.to_immediate is True:
                pickings_to_do |= line.picking_id
            else:
                pickings_not_to_do |= line.picking_id

        for picking in pickings_to_do:
            # If still in draft => confirm and assign
            if picking.picking_type_id.name and 'RETURN' in picking.picking_type_id.name.upper():
                for stock_move in picking.move_ids:
                    move_lines = stock_move.create_journal_grn_return()

                    # raise exceptions.ValidationError(_(str(move_lines)))
                    if move_lines:
                        move = self.env['account.move'].create({'stock_picking_id': stock_move.picking_id.id, 'journal_id': stock_move.product_id.categ_id.property_stock_journal.id, 'name': stock_move.name, 'ref': stock_move.name, 'line_ids': move_lines, 'cip_id': stock_move.asset_cip_id.id})
                        if move:
                            move.state = 'posted'
                            stock_move.state = 'done'
                            stock_move.state = 'done'
                return True
            else:
                if picking.state == 'draft':
                    # open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + "picking_id : " +  str(picking) )
                    # open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + "picking_id : " +  str(picking.move_ids) )
                    picking.action_confirm()
                    # open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + "picking_id2 : " +  str(picking) )
                    # open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + "picking_id2 : " +  str(picking.move_ids) )
                    if picking.state != 'assigned':
                        picking.action_assign()
                        if picking.state != 'assigned':
                            raise UserError(_("Could not reserve all requested products. Please use the \'Mark as Todo\' button to handle the reservation manually."))
                picking.move_ids._set_quantities_to_reservation()

        raise exceptions.ValidationError("masuk def process")
        pickings_to_validate = self.env.context.get('button_validate_picking_ids')
        if pickings_to_validate:
            pickings_to_validate = self.env['stock.picking'].browse(pickings_to_validate)
            pickings_to_validate = pickings_to_validate - pickings_not_to_do
            
            # Skip auto generate journal grn bawaan odoo.
            stock_move_check = self.env['stock.move'].sudo().search([('picking_id','=', pickings_to_do.id)], limit=1)
            if stock_move_check.non_asset <= 0:
                return True #exit
            else:
                return pickings_to_validate.with_context(skip_immediate=True).button_validate()
        return True

        # def process(self):
        #     pickings_to_do = self.env['stock.picking']
        #     pickings_not_to_do = self.env['stock.picking']
        #     for line in self.immediate_transfer_line_ids:
        #         if line.to_immediate is True:
        #             pickings_to_do |= line.picking_id
        #         else:
        #             pickings_not_to_do |= line.picking_id

        #     for picking in pickings_to_do:
        #         # If still in draft => confirm and assign
        #         if picking.state == 'draft':
        #             picking.action_confirm()
        #             if picking.state != 'assigned':
        #                 picking.action_assign()
        #                 if picking.state != 'assigned':
        #                     raise UserError(_("Could not reserve all requested products. Please use the \'Mark as Todo\' button to handle the reservation manually."))
        #         picking.move_ids._set_quantities_to_reservation()

        #     pickings_to_validate = self.env.context.get('button_validate_picking_ids')
        #     if pickings_to_validate:
        #         pickings_to_validate = self.env['stock.picking'].browse(pickings_to_validate)
        #         pickings_to_validate = pickings_to_validate - pickings_not_to_do
        #         return pickings_to_validate.with_context(skip_immediate=True).button_validate()
        #     return True
