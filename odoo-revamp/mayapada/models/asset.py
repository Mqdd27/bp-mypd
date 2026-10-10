from . import sync
import datetime
#from datetime import datetime
import calendar
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
from xlrd import open_workbook
import re

import io
import csv
import hashlib
import base64
logger = logging.getLogger(__name__)






class AccountAssetCip(models.Model):
    _name = 'account.asset.cip'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    def _default_get_company(self):
        return self.env.company.id
    
    company_id = fields.Many2one('res.company', default=_default_get_company, string='Company', readonly=True)
    date = fields.Date(string="Date")
    name = fields.Char(string="CIP Name")
    number = fields.Char(string="CIP No.")
    reference_no = fields.Char(string="Reference")
    estimation = fields.Float(string="Estimasi Value")
    total_value = fields.Float(string="Total Value", compute="_get_value")
    total_realization = fields.Float(string="Total Realisasi", compute="_get_realization")
    total_pending = fields.Float(string="Total Pending", compute="_get_pending")
    classification = fields.Selection([('purchase', 'Purchase Item'),('work','Work Order')], string="Classification")
    file_src = fields.Char(string="File Source", compute="_get_file_src", store=False)
    account_type = fields.Many2one('account.account', string="Account Type")
    asset_move_ids = fields.One2many('account.move', 'cip_id', domain=[('account_asset_id','!=',False)], string="Asset Journal")
    move_line_ids = fields.One2many('account.move.line', 'cip_id', string="CIP Movement")
    
    move_ids = fields.Many2many('account.move.line', compute='_compute_move_ids', string="CIP Movement")
    asset_ids = fields.One2many('account.asset.asset', 'cip_id', string="Asset")    
    state = fields.Selection([('draft', 'Draft'),('progress', 'In-Progress'),('posted','Posted')], string="Status", default='draft')

    # def _compute_move_ids(self):
    #     for record in self:
    #         if record.move_line_ids:
    #             for line in record.move_line_ids:
    #                 line.move_ids = line.move_line_ids.filtered(lambda x: x.state == 'posted' and x.account_id.id == line.account_type.id)
                
    def _compute_move_ids(self):
        self.move_ids = self.move_line_ids

    # @api.multi
    def name_get(self):
        res = []
        for record in self:
            res.append((record.id, '[' +(record.number or 'NONE') + '] ' + (record.name or '')))
        return res


    @api.model
    def create(self, vals):
        result = super(AccountAssetCip, self).create(vals)
        if not result.number:
            if result.company_id.company_code == 'MHJS':
                result.number = self.env['ir.sequence'].sudo().next_by_code('account.asset.cip.mhjs.seq')
            if result.company_id.company_code == 'MHTG':
                result.number = self.env['ir.sequence'].sudo().next_by_code('account.asset.cip.mhtg.seq')
            if result.company_id.company_code == 'MHKN':
                result.number = self.env['ir.sequence'].sudo().next_by_code('account.asset.cip.mhkn.seq')
            if result.company_id.company_code == 'MHBG':
                result.number = self.env['ir.sequence'].sudo().next_by_code('account.asset.cip.mhbg.seq')
            if result.company_id.company_code == 'MHSB':
                result.number = self.env['ir.sequence'].sudo().next_by_code('account.asset.cip.mhsb.seq')
            if result.company_id.company_code == 'MHBD':
                result.number = self.env['ir.sequence'].sudo().next_by_code('account.asset.cip.mhbd.seq')
            if result.company_id.company_code == 'MHNS':
                result.number = self.env['ir.sequence'].sudo().next_by_code('account.asset.cip.mhns.seq')
            if result.company_id.company_code == 'MHJT':
                result.number = self.env['ir.sequence'].sudo().next_by_code('account.asset.cip.mhjt.seq')
            else:
                result.number = self.env['ir.sequence'].sudo().next_by_code('account.asset.cip.mh.seq')
        result.name = result.name.upper()
        return result
    
    # @api.one
    def _get_file_src(self):
        record = self.sudo()
        self.file_src = ""
        if record:
            from . import datas
            # from mayapada.models.datas import convert, json, encode
            from odoo.http import request
            sudo = request.env.user.sudo()
            
            if record.asset_ids.ids:
                asset_ids = record.asset_ids.ids
            
                if asset_ids:
                    asset_ids.append(0)
                
                query = """SELECT asst.id, rsc.name company_id, asst.code, asst.name, asst.date, asst.brand, asst.vendor_ref  
                    FROM account_asset_asset asst
                    INNER JOIN res_company rsc ON asst.company_id=rsc.id
                    WHERE asst.company_id={company_id} AND asst.id IN {asset_ids}
                """.format(
                    company_id=record.company_id.id, 
                    asset_ids = tuple(asset_ids))
            
                query = sudo.env.cr.execute(query)
                asset = sudo.env.cr.dictfetchall()
                
                data = {}
                data['data_ids'] = []
                
                for line in asset:
                    obj = {}
                    obj['asset_code'] = line['code'] or ' '
                    obj['asset_name'] = line['name'] or ' '
                    obj['company_id'] = line['company_id'] or ' '
                    obj['date'] = (line['date']).strftime('%Y-%m-%d') or ' '
                    obj['asset_brand'] = line['brand'] or ' '
                    obj['asset_vendor'] = line['vendor_ref'] or ' '
                    data['data_ids'] += [obj] or ' '

                data = datas.convert(data)
                data = datas.json(data, cdata=False)

                import requests
                uname = request.env.company.uname_jasper
                password = request.env.company.pass_jasper
                execution = requests.post('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions',
                    auth=(uname, password),
                    json={
                        'reportUnitUri':
                        '/Mayapada16/Accounting/Print_Out_fix_Asset_Barcode_Multiple',
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
                url = "http://10.2.1.120:8080/jasperserver/services/repository?wsdl"
                
                # Encode binary data to base64
                encoded_data = base64.b64encode(result.content)
                self.file_src = encoded_data.decode('utf-8')
                
    # @api.one
    @api.depends('move_line_ids','move_ids')
    def _get_value(self):
        for record in self.sudo():
            record.total_value = 0
            if record.move_ids:
                total_value = 0
                for line in record.move_ids:
                    total_value += line.debit
                record.total_value = total_value

                
    # @api.one
    @api.depends('move_line_ids','move_ids')
    def _get_pending(self):
        for record in self.sudo():
            record.total_pending = 0
            if record.move_ids:
                for line in record.move_ids:
                    record.total_pending += line.balance

    # @api.one
    @api.depends('move_line_ids','move_ids')
    def _get_realization(self):
        for record in self.sudo():
            record.total_realization = 0
            if record.move_ids:
                for line in record.move_ids:
                    record.total_realization += line.credit

    # @api.multi
    def qrcode_print(self):
        print ("qrcode_print")
    
    # @api.multi
    def print_qrcode_pdf(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/account/print_out_qrcode_pdf?id=' + str(self.id)
        action['target'] = 'new'
        return action
    
    # @api.multi
    def confirm(self):
        record = self.sudo()
        if record:
            record.state = "posted"
    
    # @api.multi
    def post(self):
        action = {}
        action['name'] = 'Asset CIP Posting'
        action['type'] = 'ir.actions.act_window'
        action['res_model'] = 'account.asset.cip.posting.wizard'
        action['view_type'] = 'form'
        action['view_mode'] = 'form'
        action['target'] = 'new'
        action['context'] = {'default_cip_id': self.id, 'default_account_id': self.account_type.id }
        return action

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(AccountAssetCip,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Construction in Progress" delete="0" decoration-warning="state=='posted'" decoration-info="state=='draft'" decoration-success="state=='progress'">
                    <field name="date" />
                    <field name="number"/>
                    <field name="name" />
                    <field name="reference_no" />
                    <field name="total_value" invisible="1" />
                    <field name="state" widget="badge" decoration-warning="state=='posted'" decoration-info="state=='draft'" decoration-success="state=='progress'" />
                    <field name="move_ids" invisible="1"/>
                    <field name="move_line_ids" invisible="1"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Construction in Progress Search">
                    <filter string="Draft" domain="[('state','=', 'draft')]" />
                    <filter string="Posted" domain="[('state','=', 'posted')]" />
                    <separator/>
                    <field name="name"/>
                    <field name="reference_no"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res



class AssetDepreciationConfirmationWizard(models.TransientModel):
    _inherit = "asset.depreciation.confirmation.wizard"
    _description = "asset.depreciation.confirmation.wizard"

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    #category_id = fields.Many2one('account.asset.category', string='Category', index=True, required=True)
    category_ids = fields.Many2many('account.asset.category', relation='asset_depreciation_category', string="Asset Categories", required=True, store=True, readonly=False)
    date_start = fields.Date('Account Start Date', required=True, help="Choose the period for which you want to automatically post the depreciation lines of running assets", default='2021-04-01')
    date_end = fields.Date('Account End Date', required=True, help="Choose the period for which you want to automatically post the depreciation lines of running assets", default=fields.Date.context_today)
    post_move = fields.Boolean('Auto Post Move', default=False, required=False)

    # @api.multi
    def asset_compute(self):
        if not self.category_ids:
            raise UserError(_("Asset Type Cannot Be Empty."))
        self.ensure_one()
        context = self._context
        created_move_ids = self.env['account.asset.asset'].compute_generated_entries(date_start=self.date_start, date_end=self.date_end, asset_type=context.get('asset_type'), category_ids=self.category_ids.ids, company_id=self.company_id.id, post_move=self.post_move)

        return {
            'name': _('Created Asset Moves') if context.get('asset_type') == 'purchase' else _('Created Revenue Moves'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            'view_id': False,
            'domain': "[('id','in',[" + ','.join(map(str, created_move_ids)) + "])]",
            'type': 'ir.actions.act_window',
        }



class AccountAssetSubcategory(models.Model):
    _name = 'account.asset.subcategory'

    sync_type = sync.type
    sync_date = sync.date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    name = fields.Char(string="Sub Category")
    category_id = fields.Many2one('account.asset.category', string="Asset Type", index=True)
    sequence_id = fields.Many2one('ir.sequence', string="Sequence Number", required=True)
    company_id = fields.Many2one('res.company', related="category_id.company_id")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(AccountAssetSubcategory,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Asset Sub Category">
                    <field name="name" />
                    <field name="category_id" />
                    <field name="sequence_id" />
                    <field name="company_id" />
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class AccountAssetStockOpname(models.Model):
    _name = 'account.asset.stock.opname'

    def _default_today(self):
        today = tools.datetime.today()
        return today

    @api.model
    def _get_company(self):
        return self.env.company.id

    @api.model
    def _get_responsible(self):
        return self.env.user.id
        
    sync_type = sync.type
    sync_date = sync.date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date



class AccountAssetOpname(models.Model):
    _name = 'account.asset.opname'
    
    @api.model
    def _get_responsible(self):
        return self.env.user.id
    
    @api.model
    def _get_company(self):
        return self.env.company.id
    
    sync_type = sync.type
    sync_date = sync.date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company', related=None, string='Company', store=True, readonly=False, index=True, default=_get_company)
    name = fields.Char(string="SO No.")
    date = fields.Date(string="SO Date")
    location_id = fields.Many2one('hr.department', string="SO Location", index=True)
    user_id = fields.Many2one('res.users', string="Responsible", readonly=False, default=_get_responsible)
    reference = fields.Char(string="Ref No.")
    link = fields.Char(string="Scan")
    state = fields.Selection([('draft', 'Draft'), ('progress', 'In-Progress'), ('posted', 'Posted')], string="Status", readonly=True, default='draft')
    opname_ids = fields.One2many('account.asset.opname.line','opname_id', string="Opname", index=True)



    @api.model
    def create(self, vals):
        
        result = super(AccountAssetOpname, self).create(vals)
        return result
    

    @api.onchange('link')
    def _scan(self):
        if self.link:
            json = {}
            data = self.env['account.asset.asset'].search([('code', '=',self.link)])
            opname = self.env['account.asset.opname.line'].search([('asset_id', '=', data.id), ('opname_id','=', self._origin.id)])
            
            self.link = None
            # if asset exist in opndame_ids
            for line in self.opname_ids:
                if line.asset_id.id == data.id and line.confirmed == True:
                    json['warning'] = {'title': 'Warning','message': 'Asset already scanned'}
                    
            if not data:
                json['warning'] = {'title': 'Warning','message': 'Asset not found'}
            elif data.id in self.opname_ids.mapped('asset_id.id'):
                if opname:
                    opname.confirmed = True
                    opname.update_location_id = self.location_id.id
            
            if json:
                return json

            # opname_view = self.opname_ids.mapped('asset_id.id')
            if data and not opname:
                lines = {}
                lines['opname_id'] = self._origin.id
                lines['asset_id'] = data.id
                lines['asset_category_id'] = data.category_id.id
                lines['location_id'] = data.location_id.id
                lines['update_location_id'] = self.location_id.id
                lines['confirmed'] = True
                
                new_lines = self.env['account.asset.opname.line']
                new_lines = new_lines.new(lines)
                self.opname_ids += new_lines
                
                # record = super(AccountAssetOpname, self).write(lines)
                
    # @api.multi
    def set_to_draft(self):
        record = self.sudo()
        if record:
            record.state = 'draft'
        
    # @api.multi
    def confirm(self):
        record = self.sudo()
        if record:
            record.state = 'progress'
            
            # delete list asset if exists
            self.env.cr.execute("""
                delete from account_asset_opname_line 
                where opname_id={opname_id}
                """.format(opname_id=record.id))

            # insert new asset from master asset 
            self.env.cr.execute("""
                insert into account_asset_opname_line (
                    opname_id, asset_id, location_id, confirmed) 
                select {opname_id} opname_id, a.id, a.location_id, False confirmed
                    from account_asset_asset a 
                    where a.location_id = {location_id} 
                        and a.company_id = {company_id}
                        and a.state not in('close')
            """.format(
                opname_id=record.id, 
                location_id=record.location_id.id,
                company_id=record.company_id.id,
            ))
    
    # @api.multi
    def post(self):
        record = self.sudo()
        if record:
            record.state = 'posted'
            
            # validation confirmed
            for a in record.opname_ids:
                if a.confirmed == False:
                    raise exceptions.ValidationError("List Asset Must Be Confirmed")
                
            for line in record.opname_ids:
                if line.location_id and line.update_location_id:
                    self.env.cr.execute("""
                        insert into account_asset_location_history (
                            asset_id, source_id, location_id, date_modified) 
                        values ('{asset_id}','{source_id}','{location_id}','{date_modified}')
                    """.format(
                        asset_id = line.asset_id.id,
                        source_id = line.location_id.id, 
                        location_id = line.update_location_id.id,
                        date_modified = tools.datetime.now().strftime('%Y-%m-%d')
                    ))
                    
                    line.asset_id.location_id = line.update_location_id.id
                    line['location_id'] = line.update_location_id.id
                
    # @api.multi
    def action_print(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/accounting/asset_opname_pdf?id=' + str(self.id)
        action['target'] = 'new'
        return action

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(AccountAssetOpname,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Asset Stock Opname">
                    <field name="name"/>
                    <field name="location_id"/>
                    <field name="reference"/>
                    <field name="user_id"/>
                    <field name="state"/>
                    <field name="sync_type"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res
        

class AccountAssetOpnameLine(models.Model):
    _name = 'account.asset.opname.line'
    
    sync_type = sync.type
    sync_date = sync.date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    
    opname_id = fields.Many2one('account.asset.opname', string="Opname No.", index=True)
    asset_id = fields.Many2one('account.asset.asset', string="Asset Name", index=True)
    asset_category_id = fields.Many2one('account.asset.category', string="Asset Category", related="asset_id.category_id")
    location_id = fields.Many2one('hr.department', string="Asset Location", index=True)
    confirmed = fields.Boolean(string="Confirmed")
    update_location_id = fields.Many2one('hr.department', string="Update Location", index=True)


class AssetCheckingWizard(models.TransientModel):
    _name = 'account.asset.checking.wizard'
    
    link = fields.Char(string="Scan")
    account_asset_id = fields.Many2one('account.asset.asset', string="Asset Code", index=True)
    location_id = fields.Many2one('hr.department', string="Location")

    vendor_ref = fields.Char(string="Vendor Reference")
    date = fields.Date(string='Date')
    calibration_date = fields.Date(string="Calibration Date")
    guarantee_date = fields.Date(string="Guarantee Date")
    qty = fields.Float(string="Quantity")
    brand = fields.Char(string="Brand")
    remarks = fields.Char(string="Cancel Remarks")
    type_char = fields.Char(string="Type Char")
    status = fields.Selection([('1', 'Layak Pakai'),('2', 'Tidak Layak Pakai')],string="Status")
    company_id = fields.Many2one('res.company',string='Company')
    picking_id = fields.Many2one('stock.picking', string="Shipment/Rcv No.")
    sequence = fields.Char(string="Serial Number", readonly=False)
    account_analytic_id = fields.Many2one('account.analytic.account',string="Analytic Account")
    serial_number = fields.Char(string="SN Manual Asset")
    category_id = fields.Many2one('account.asset.category',string='Category')
    salvage_value = fields.Float(string="Salvage Value")
    value = fields.Float(string="Gross Value")
    value_residual = fields.Float(string="Residual Value")
    partner_id = fields.Many2one('res.partner',string='Partner')
    picking_id = fields.Many2one('stock.picking', string="Shipment/Rcv No.")
    currency_id = fields.Many2one('res.currency', string="Currency")

    @api.onchange('link')
    def onchange_link(self):
        if self:
            if self.link:
                records = self.env['account.asset.asset'].search([('code','=', self.link)], limit=1)
                
    # @api.multi
    def action_show_asset(self):
        opname_ids = self.env['account.asset.stock.opname.line'].search([('asset_code','=', self.link), ('opname_id','!=',None)], limit=1)
        url = """web#id={opname_id}&view_type=form&model=account.asset.stock.opname""".format(opname_id=opname_ids.opname_id.id)
        if not opname_ids:
            raise exceptions.UserError("Stock Opname Not Found")
        
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/' + str(url)
        action['target'] = 'new'
        return action



class AssetGenerateSeqWizard(models.TransientModel):
    _name = 'asset.generate.seq.wizard'
    
    @api.model
    def _get_company(self):
        return self.env.company.id
    
    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=False, index=True, default=_get_company)
    name = fields.Char(string="Name", required=True)
    implementation = fields.Selection([('standard','Standard'), ('no_gap','No gap')], default="standard")
    code = fields.Char(string="Sequence Code", required=True)
    active = fields.Boolean(string="Active", default=True)
    prefix = fields.Char(string="Prefix")
    suffix = fields.Char(string="Suffix")
    use_date_range = fields.Boolean(string="Use subsequences per date_range", default=False)
    padding = fields.Integer(string="Sequence Size", default="3")
    number_increment = fields.Integer(string="Step", default="1")
    number_next_actual = fields.Integer(string="Next Number", default="1")
    # date_range_ids = fields.One2many('ir.sequence.date.range','sequence_id', string="Date Range")
    
    @api.onchange('company_id')
    def _onchange_code(self):
        self.code = "fixed.asset." + (self.company_id.company_code or "").lower() + ".seq"

    # @api.multi
    def generate_seq(self):
        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("AAA"))
        record = self.sudo()
        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(record.name))
        if record:
            ir_sequence = record.env['ir.sequence']
            ir_sequence.create({
             'company_id' : record.company_id.id,
             'name' : record.name,
             'implementation' : record.implementation,
             'code' : record.code,
             'active' : record.active,
             'prefix' : record.prefix,
             'suffix' : record.suffix,
             'use_date_range' : record.use_date_range,
             'padding' : record.padding,
             'number_increment' : record.number_increment,
             'number_next_actual' : record.number_next_actual
            })


class AccountAssetModifyWizard(models.TransientModel):
    _name = 'account.asset.modify.wizard'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    def _default_get_company(self):
        return self.env.user.company_id.id

    def _get_asset_id(self):
        return self.env.context.get('asset_id')

    @api.model
    def _get_user_id(self):
        return self.env.user.id

    asset_id = fields.Many2one('account.asset.asset', string="Asset ID.", default=_get_asset_id, index=True)
    asset_name = fields.Char(string="Asset")
    company_id = fields.Many2one('res.company', default=_default_get_company, string='Company', readonly=True)
    date = fields.Date(string="Tgl Perolehan")
    value = fields.Float(string="Nilai Perolehan")
    salvage_value = fields.Float(string="Total Salvage")
    depreciation_number = fields.Float(string="Masa Depresiasi")
    depreciation_amount = fields.Float(string="Depresiasi Per Bulan")
    depreciation_residual = fields.Float(string="Sisa Usia Pakai")
    value_residual = fields.Float(string="Total Residual")
    value_depreciation = fields.Float(string="Total Depresiasi")
    
    modify_residual_value = fields.Float(string="New Residual Value")
    modify_salvage_value = fields.Float(string="New Salvage Value")
    modify_depreciation_residual = fields.Float(string="New Sisa Usia")
    modify_depreciation_amount = fields.Float(string="Depresiasi Per Bulan")
    modify_value_depreciation = fields.Float(string="Depresiasi Total")
    modify_value = fields.Float(string="New Asset Value")
    account_id = fields.Many2one('account.account', string="Adjustment Account")
    category_id = fields.Many2one('account.asset.category', string="Category Asset")
    user_id = fields.Many2one('res.users', string="Responsible", default=_get_user_id)
    remarks = fields.Char(string="Remarks")
    notes = fields.Char(string="Notes", default="""Jika tidak ingin mengubah Category Asset, bisa di kosongkan.""")

    @api.onchange('asset_id')
    def get_asset(self):
        record = self.sudo()
        if record:
            record.asset_name = record.asset_id.name
            record.date = record.asset_id.date
            record.value = record.asset_id.value
            record.salvage_value = record.asset_id.salvage_value
            record.depreciation_number = record.asset_id.method_number
            record.depreciation_amount = (float(record.value) - float(record.salvage_value)) / float(record.depreciation_number)
            record.depreciation_residual = len(record.env['account.asset.depreciation.line'].search([('asset_id','=', record.asset_id.id), ('move_check','=', False)]))
            value_depreciation = record.get_depreciation()
            record.value_residual = float(record.value) - float(record.salvage_value) - float(record.value_depreciation)

            record.modify_residual_value = float(record.value_residual)
            record.modify_value = float(record.value)
            record.modify_salvage_value = float(record.salvage_value)
            record.modify_depreciation_residual = len(record.env['account.asset.depreciation.line'].search([('asset_id','=', record.asset_id.id), ('move_check','=', False)]))
            record.modify_depreciation_amount = float(record.depreciation_amount)
            record.modify_value_depreciation = record.value_depreciation


    @api.onchange('modify_residual_value','modify_depreciation_residual','modify_salvage_value')
    def _onchange_depreciation_amount(self):
        record = self.sudo()
        if record:
            depreciation_run = len(record.env['account.asset.depreciation.line'].search([('asset_id','=', record.asset_id.id), ('move_check','=', True)]))
            record.modify_depreciation_amount = 0 if record.modify_depreciation_residual == 0 else (float(record.modify_residual_value) / float(record.modify_depreciation_residual))
            record.modify_value = (record.modify_residual_value + record.modify_salvage_value + record.value_depreciation)


    # @api.one
    def get_depreciation(self):
        record = self.sudo()
        value_depreciation = 0
        if record:
            line = record.env['account.asset.depreciation.line'].search([('asset_id','=', record.asset_id.id), ('move_check','=', True)])
            for a in line:
                value_depreciation += float(a['amount'])
            record.value_depreciation = value_depreciation


    # @api.multi
    def modify(self):
        record = self.sudo()
        if record:
            depreciation_run = len(record.env['account.asset.depreciation.line'].search([('asset_id','=', record.asset_id.id), ('move_check','=', True)]))
            if record.modify_depreciation_residual <= depreciation_run:
                raise exceptions.ValidationError("Modify depreciation : " + str(int(record.modify_depreciation_residual)) + " not less than : " + str(depreciation_run))
            
            # record.asset_id.value = record.modify_value
            # record.asset_id.salvage_value = record.modify_salvage_value
            # record.asset_id.method_number = record.modify_depreciation_residual
            # selisih = (float(record.modify_value) - float(record.modify_salvage_value)) - float(record.asset_id.value_residual)
            selisih = (float(record.modify_value) - float(record.asset_id.value))
            
            obj_debit = {}
            obj_debit['name'] = record.asset_id.code
            obj_debit['journal_id']  = record.asset_id.category_id.journal_id.id
            obj_debit['account_id'] = record.asset_id.category_id.account_asset_id.id
            obj_debit['debit'] = abs(selisih)
            obj_debit['credit'] = 0
            obj_debit['account_asset_id'] = record.asset_id.id
            
            obj_credit = {}
            obj_credit['name'] = record.asset_id.code
            obj_credit['journal_id'] = record.asset_id.category_id.journal_id.id
            obj_credit['account_id'] = record.account_id.id
            obj_credit['debit'] = 0
            obj_credit['credit'] = abs(selisih)
            obj_credit['account_asset_id'] = record.asset_id.id

            move_line = [(0, 0, obj_debit), (0, 0, obj_credit)]

            if move_line:
                move = record.env['account.move'].create({
                    'company_id' : record.company_id.id,
                    'name' : record.asset_id.code,
                    'journal_id' : record.asset_id.category_id.journal_id.id,
                    'date' : tools.datetime.now().strftime('%Y-%m-%d'),
                    'ref' : "MODIFY : " + str(record.asset_id.code),
                    'account_asset_id' : record.asset_id.id,
                    'line_ids' : move_line
                })
                move.post()

            if record.category_id:
                # nilai asset baru
                obj_debit_asset = {}
                obj_debit_asset['name'] = record.asset_id.code
                obj_debit_asset['journal_id']  = record.category_id.journal_id.id
                obj_debit_asset['account_id'] = record.category_id.account_asset_id.id
                obj_debit_asset['debit'] = abs(record.modify_value)
                obj_debit_asset['credit'] = 0
                obj_debit_asset['account_asset_id'] = record.asset_id.id

                # nilai asset lama
                obj_credit_asset = {}
                obj_credit_asset['name'] = record.asset_id.code
                obj_credit_asset['journal_id'] = record.asset_id.category_id.journal_id.id
                obj_credit_asset['account_id'] = record.asset_id.category_id.account_asset_id.id
                obj_credit_asset['debit'] = 0
                obj_credit_asset['credit'] = abs(float(record.modify_value))
                obj_credit_asset['account_asset_id'] = record.asset_id.id

                # nilai depresiasi lama
                obj_debit_depreciation = {}
                obj_debit_depreciation['name'] = record.asset_id.code
                obj_debit_depreciation['journal_id']  = record.asset_id.category_id.journal_id.id
                obj_debit_depreciation['account_id'] = record.asset_id.category_id.account_depreciation_id.id
                obj_debit_depreciation['debit'] = abs(record.value_depreciation)
                obj_debit_depreciation['credit'] = 0
                obj_debit_depreciation['account_asset_id'] = record.asset_id.id
                
                # nilai depresiasi baru
                obj_credit_depreciation = {}
                obj_credit_depreciation['name'] = record.asset_id.code
                obj_credit_depreciation['journal_id'] = record.category_id.journal_id.id
                obj_credit_depreciation['account_id'] = record.category_id.account_depreciation_id.id
                obj_credit_depreciation['debit'] = 0
                obj_credit_depreciation['credit'] = abs(record.value_depreciation)
                obj_credit_depreciation['account_asset_id'] = record.asset_id.id

                move_line_add = [(0, 0, obj_debit_asset), (0, 0, obj_credit_asset), (0, 0, obj_debit_depreciation), (0, 0, obj_credit_depreciation)]

                # raise exceptions.ValidationError(_(str(move_line_add)))
            
                if move_line_add:
                    move = record.env['account.move'].create({
                        'company_id' : record.company_id.id,
                        'name' : record.asset_id.code,
                        'journal_id' : record.asset_id.category_id.journal_id.id,
                        'date' : tools.datetime.now().strftime('%Y-%m-%d'),
                        'ref' : "MODIFY : " + str(record.asset_id.code),
                        'account_asset_id' : record.asset_id.id,
                        'line_ids' : move_line_add
                    })
                    move.post()
            
            # update value
            depreciation_run = len(record.env['account.asset.depreciation.line'].search([('asset_id','=', record.asset_id.id), ('move_check','=', True)]))
            record.asset_id.value = record.modify_value
            record.asset_id.salvage_value = record.modify_salvage_value
            record.asset_id.method_number = record.modify_depreciation_residual + depreciation_run



    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(AccountAssetModifyWizard,self).get_view(view_id=view_id,view_type=view_type, **options)

        if view_type == 'form':
            res['arch'] = """
                <form string="Asset Modify">
                <sheet>
                    <group>
                        <group>
                            <field name="asset_id" invisible="1" />
                            <field name="asset_name" readonly="1" />
                            <field name="date" readonly="1" />
                            <field name="value" readonly="1" />
                            <field name="depreciation_number" readonly="1" />
                            <field name="depreciation_amount" readonly="1" />
                        </group>
                        <group>
                            <field name="company_id" readonly="1" />
                            <field name="depreciation_residual" readonly="1" />
                            <field name="salvage_value" readonly="1" />
                            <field name="value_depreciation" readonly="1" />
                            <field name="value_residual" string="Nilai Sisa" readonly="1" />
                        </group>
                    </group>
                    <notebook>
                        <page string="Modify">
                            <group>
                                <group>
                                    <field name="modify_residual_value" required="1" />
                                    <field name="modify_salvage_value" />
                                    <field name="modify_value_depreciation" readonly="1" />
                                    <field name="modify_value" required="1" />
                                    <field name="modify_depreciation_residual" />
                                    <field name="modify_depreciation_amount" readonly="1" />
                                </group>
                                <group>
                                    <field name="account_id" domain="[('parent','!=', True), ('company_id','=', company_id)]" required="1" string="Adjustment Account"/>
                                    <field name="category_id" domain="[('company_id','=', company_id)]"/>
                                    <field name="user_id" />
                                    <field name="remarks" />
                                    <field name="notes" nolabel="1" readonly="1" />
                                </group>
                            </group>
                        </page>
                        <page string="Technical">
                            <group>
                                <group>
                                    <field name="sync_type" readonly="1"/>
                                    <field name="sync_consol_date" readonly="1"/>
                                </group>
                                <group>
                                    <field name="sync_consol_id_main" readonly="1"/>
                                    <field name="sync_consol_id_unit" readonly="1" />
                                </group>
                            </group>
                        </page>
                    </notebook>
                </sheet>
                <footer>
                    <button name="modify" string="Modify" type="object" class="oe_highlight"/>
                </footer>
            </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res




class AssetRelocation(models.Model):
    _name = 'asset.relocation'
    _rec_name = 'trans_no'

    sync_type = sync.type
    sync_date = sync.date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_user_id(self):
        return self.env.user.id

    def _default_get_company(self):
        return self.env.user.company_id.id
    
    company_id = fields.Many2one('res.company', default=_default_get_company, string='Company', readonly=True)
    trans_no = fields.Char(string="Trans No.")
    ref = fields.Char(string="Trans Ref")
    location_id = fields.Many2one('hr.department', string="Location", index=True, required=True)
    remarks = fields.Char(string="Remarks")
    user_id = fields.Many2one('res.users', string="Responsible", default=_get_user_id)
    asset_ids = fields.Many2many('account.asset.asset', string="Asset Outcome")
    asset_return_ids = fields.Many2many('account.asset.asset', compute='_return_asset', string="Asset Return")
    state = fields.Selection([('draft', 'Draft'),('posted','Posted'),('completed','Completed')], string="Status", default='draft')
    move_ids = fields.One2many('account.move', 'relocation_id', string="Entries")

    def _return_asset(self):
        self.asset_return_ids = self.asset_ids.filtered(lambda x: x.asset_status != 'loaned')


    @api.model 
    def create(self, vals):
        result = super(AssetRelocation, self).create(vals)
        result.trans_no = self.env['ir.sequence'].sudo().next_by_code('asset.relocation.seq')
        return result

        
    # @api.multi
    def post(self):
        record = self.sudo()
        if record:
            record.state = "posted"
            for line in record.asset_ids:
                line.origin_location_id = line.location_id
                line.location_id = record.location_id
                line.asset_status = "loaned"
                line.relocation_id = record.id
                hist = line.create_location_history(line.id, line.origin_location_id.id, record.location_id.id)

                # Create Journal Charge
                if line.relocation_charge > 0:
                    obj_debit = {}
                    obj_debit['name']  = record.trans_no
                    obj_debit['journal_id']  = line.category_id.journal_id.id
                    obj_debit['account_id'] = line.account_id.id
                    obj_debit['debit'] = abs(line.relocation_charge)
                    obj_debit['credit'] = 0
                    # obj_debit['account_asset_id'] = line.id

                    obj_credit = {}
                    obj_credit['name']  = record.trans_no
                    obj_credit['journal_id'] = line.category_id.journal_id.id
                    obj_credit['account_id'] = line.credit_account_id.id
                    obj_credit['debit'] = 0
                    obj_credit['credit'] = abs(line.relocation_charge)
                    # obj_credit['account_asset_id'] = line.id

                    move_line = [(0, 0, obj_debit), (0, 0, obj_credit)]

                    if move_line:
                        move = record.env['account.move'].create({
                            'company_id' : line.company_id.id,
                            'journal_id' : line.category_id.journal_id.id,
                            'date' : tools.datetime.now().strftime('%Y-%m-%d'),
                            'ref' : "RELOCATION CHARGE : " + str(record.trans_no) + "(" + str(line.code) + ")",
                            'relocation_id' : record.id,
                            'line_ids' : move_line
                        })
                        move.action_post()

    # @api.multi
    def completed(self):
        action = {}
        action['name'] = 'Refund Asset'
        action['type'] = 'ir.actions.act_window'
        action['res_model'] = 'account.relocation.return.wizard'
        action['view_type'] = 'form'
        action['view_mode'] = 'form'
        action['target'] = 'new'
        action['context'] = {'default_relocation_id': self.id }
        return action

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(AssetRelocation,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Asset Relocation">
                    <field name="trans_no" />
                    <field name="ref" />
                    <field name="location_id" />
                    <field name="state" />
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


class AccountRelocationReturn(models.TransientModel):
    _name = 'account.relocation.return.wizard'

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_user_id(self):
        return self.env.user.id

    def _default_get_company(self):
        return self.env.user.company_id.id
    
    company_id = fields.Many2one('res.company', default=_default_get_company, string='Company', readonly=True)
    relocation_id = fields.Many2one('asset.relocation', string="Relocation No.", index=True)
    relocation_asset_ids = fields.Many2many('account.asset.asset', compute='_compute_asset', string="Asset Item")
    location_id = fields.Many2one('hr.department', string="Return Location")
    user_id = fields.Many2one('res.users', string="Responsible", default=_get_user_id)
    asset_ids = fields.Many2many('account.asset.asset', string="Asset Item")


    @api.onchange('relocation_id')
    def _compute_asset(self):
        self.relocation_asset_ids = self.relocation_id.asset_ids.filtered(lambda x: x.asset_status == 'loaned')


    # @api.multi
    def action_return(self):
        for record in self:
            for asset in record.asset_ids:
                if asset.asset_status == 'loaned':
                    asset.origin_location_id = record.location_id.id
                    asset.return_asset()
            
            if not record.relocation_asset_ids:
                record.relocation_id.state = 'completed'

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(AccountRelocationReturn,self).get_view(view_id=view_id,view_type=view_type, **options)

        if view_type == 'form':
            res['arch'] = """
                <form string="Return Asset">
                    <sheet>
                        <group>
                            <group>
                                <field name="company_id" readonly="1" />
                                <field name="relocation_id" readonly="1" />
                            </group>
                            <group>
                                <field name="user_id" />
                                <field name="location_id" required="1" domain="[('company_id','=', company_id)]"/>
                            </group>
                        </group>
                        <notebook>
                            <page string="List Assets">
                                <field name="relocation_asset_ids" invisible="1"/>
                                <!--field name="asset_ids" can_create="false" domain="[('id','in', [relocation_asset_ids[0][1]])]"/-->
                                <field name="asset_ids" can_create="false" domain="[('id', 'in', relocation_asset_ids)]"/>
                            </page>
                            
                        </notebook>
                    </sheet>
                    <footer>
                        <button name="action_return" string="Return Asset" type="object" class="oe_highlight"/>
                    </footer>
                </form>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res




class AccountAssetClose(models.Model):
    _name = 'account.asset.close'
    _rec_name = "trans_no"
    
    sync_type = sync.type
    sync_date = sync.date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_user_id(self):
        return self.env.user.id

    def _default_get_company(self):
        return self.env.user.company_id.id
    
    company_id = fields.Many2one('res.company', default=_default_get_company, string='Company', readonly=True)
    journal_id = fields.Many2one('account.journal', string="Journal", index=True)
    trans_no = fields.Char(string="Trans No.")
    ref = fields.Char(string="Trans Ref")
    remarks = fields.Char(string="Remarks")
    user_id = fields.Many2one('res.users', string="Responsible", default=_get_user_id)
    asset_ids = fields.Many2many('account.asset.asset', string="Asset List") 
    move_ids = fields.One2many('account.move', 'asset_close_id', string="Journal Entries")
    state = fields.Selection([('draft', 'Draft'),('posted','Posted')], string="Status", default='draft')

    @api.model 
    def create(self, vals):
        result = super(AccountAssetClose, self).create(vals)
        result.trans_no = self.env['ir.sequence'].sudo().next_by_code('account.asset.close.seq')
        return result

    # @api.multi
    def post(self):
        for record in self:
            if record.state == 'draft':
                for line in record.asset_ids:
                    if line.state == 'open':
                        if line.item_status == "dispose":
                            move = record.create_move_dispose(line)
                            move.action_post()
                            line.state = 'close'
                        elif line.item_status == "sell":
                            move = record.create_move_sell(line)
                            move.action_post()
                            line.state = 'close'
                record.state = 'posted'

                   
    # @api.multi
    def create_move_sell(self, line):
        revenue = float(line.selling_price) - float(line.value_residual)

        obj_value = {}
        obj_value['name']  = self.trans_no
        obj_value['journal_id']  = line.category_id.journal_id.id
        obj_value['account_id'] = line.category_id.account_asset_id.id
        obj_value['analytic_account_id'] = line.account_analytic_id.id
        obj_value['debit'] = 0
        obj_value['credit'] = abs(line.value)
        obj_value['account_asset_id'] = line.id

        obj_depreciation = {}
        obj_depreciation['name']  = self.trans_no
        obj_depreciation['journal_id'] = line.category_id.journal_id.id
        obj_depreciation['account_id'] = line.category_id.account_depreciation_id.id
        obj_depreciation['analytic_account_id'] = line.account_analytic_id.id
        obj_depreciation['debit'] = abs(line.value_depreciation)
        obj_depreciation['credit'] = 0
        obj_depreciation['account_asset_id'] = line.id
        
        obj_gainloss = {}
        obj_gainloss['name']  = self.trans_no
        obj_gainloss['journal_id'] = line.category_id.journal_id.id
        obj_gainloss['account_id'] = line.account_id.id
        obj_gainloss['analytic_account_id'] = line.account_analytic_id.id
        obj_gainloss['debit'] = abs(revenue) if revenue < 0 else 0
        obj_gainloss['credit'] = abs(revenue) if revenue > 0 else 0 
        obj_gainloss['account_asset_id'] = line.id
        
        obj_bank = {}
        obj_bank['name']  = self.trans_no
        obj_bank['journal_id'] = line.category_id.journal_id.id
        obj_bank['account_id'] = self.journal_id.default_debit_account_id.id
        obj_bank['analytic_account_id'] = line.account_analytic_id.id
        obj_bank['debit'] = abs(line.selling_price)
        obj_bank['credit'] = 0 
        obj_bank['account_asset_id'] = line.id

        move_line = [(0, 0, obj_value), (0, 0, obj_depreciation), (0, 0, obj_gainloss), (0, 0,obj_bank)]
        # raise exceptions.ValidationError(_(move_line))

        if move_line:
            move = self.env['account.move'].create({
                'company_id' : line.company_id.id,
                'journal_id' : line.category_id.journal_id.id,
                'date' : tools.datetime.now().strftime('%Y-%m-%d'),
                'ref' : "SELL : " + str(self.trans_no) + "(" + str(line.code) + ")",
                'account_asset_id' : line.id,
                'asset_close_id' : self.id,
                'line_ids' : move_line
            })
        
        return move


    # @api.multi
    def create_move_dispose(self, line):
        obj_value = {}
        obj_value['name']  = self.trans_no
        obj_value['journal_id']  = line.category_id.journal_id.id
        obj_value['account_id'] = line.category_id.account_asset_id.id
        obj_value['analytic_account_id'] = line.account_analytic_id.id
        obj_value['debit'] = 0
        obj_value['credit'] = abs(line.value)
        obj_value['account_asset_id'] = line.id

        obj_depreciation = {}
        obj_depreciation['name']  = self.trans_no
        obj_depreciation['journal_id'] = line.category_id.journal_id.id
        obj_depreciation['account_id'] = line.category_id.account_depreciation_id.id
        obj_depreciation['analytic_account_id'] = line.account_analytic_id.id
        obj_depreciation['debit'] = abs(line.value_depreciation)
        obj_depreciation['credit'] = 0
        obj_depreciation['account_asset_id'] = line.id
        
        obj_gainloss = {}
        obj_gainloss['name']  = self.trans_no
        obj_gainloss['journal_id'] = line.category_id.journal_id.id
        obj_gainloss['account_id'] = line.account_id.id
        obj_gainloss['analytic_account_id'] = line.account_analytic_id.id
        obj_gainloss['debit'] = abs(line.value_residual)
        obj_gainloss['credit'] = 0 
        obj_gainloss['account_asset_id'] = line.id
        
        move_line = [(0, 0, obj_value), (0, 0, obj_depreciation), (0, 0, obj_gainloss)]
        # raise exceptions.ValidationError(_(move_line))

        if move_line:
            move = self.env['account.move'].create({
                'company_id' : line.company_id.id,
                'journal_id' : line.category_id.journal_id.id,
                'date' : tools.datetime.now().strftime('%Y-%m-%d'),
                'ref' : "DISPOSE : " + str(self.trans_no) + "(" + str(line.code) + ")",
                'account_asset_id' : line.id,
                'asset_close_id' : self.id,
                'line_ids' : move_line
            })

        return move


    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(AccountAssetClose,self).get_view(view_id=view_id,view_type=view_type, **options)  
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Construction in Progress">
                    <field name="trans_no" />
                    <field name="ref" />
                    <field name="user_id" />
                    <field name="state" />
                    <field name="company_id" />
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res



class AssetReportWizard(models.TransientModel):
    _name = "asset.report.wizard"
    
    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company', related=None, string='Company', store=True, readonly=False, index=True, default=_get_company)
    type_report = fields.Selection([('category', 'Asset Category'), ('subcategory', 'Asset SubCategory'), ('item', 'Asset Item'), ('opname', 'Asset Opname')], string='Report Type')
    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date")
    category_ids = fields.Many2many('account.asset.category', string="Category")

    # @api.multi
    def print_asset(self):
        if self.type_report == 'category':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/asset_category_report?id=' + str(self.id)
            action['target'] = 'new'
            return action
        
        if self.type_report == 'subcategory':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/asset_subcategory_report?id=' + str(self.id)
            action['target'] = 'new'
            return action
        
        if self.type_report == 'item':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/asset_item_report?id=' + str(self.id)
            action['target'] = 'new'
            return action
        
        if self.type_report == 'opname':
            action = {}
            action['type'] = 'ir.actions.act_url'
            action['url'] = '/accounting/asset_opname_report?id=' + str(self.id)
            action['target'] = 'new'
            return action





class AssetPrintQRCodeWizard(models.TransientModel):
    _name = 'account.asset.print.qrcode.wizard'
    
    @api.model
    def _get_company(self):
        return self.env.company.id
    
    company_id = fields.Many2one('res.company', string='Company', store=True, index=True, default=_get_company)
    account_asset_ids = fields.Many2many('account.asset.asset', string="Asset Code", required=True)
    file_src = fields.Char(string="File Source", store=False)
    picking_id = fields.Many2one('stock.picking', string="Picking No.")

    # @api.multi
    def print_qrcode_pdf(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/account/print_out_qrcode?id=' + str(self.id)
        action['target'] = 'new'
        return action
    
    @api.onchange('account_asset_ids')
    def onchange_file_src(self):
        if self:
            from . import datas
            from odoo.http import request
            sudo = request.env.user.sudo()
            # record = self.sudo()
            
            if self.account_asset_ids.ids:
                account_asset_ids = self.account_asset_ids.ids
            
                if account_asset_ids:
                    account_asset_ids.append(0)
                
                query = """SELECT asst.id, rsc.name company_id, asst.code, asst.name, asst.date, asst.brand, asst.vendor_ref  
                    FROM account_asset_asset asst
                    INNER JOIN res_company rsc ON asst.company_id=rsc.id
                    WHERE asst.company_id={company_id} AND asst.id IN {account_asset_ids}
                """.format(
                    company_id=self.company_id.id, 
                    account_asset_ids = tuple(account_asset_ids))
            
                query = sudo.env.cr.execute(query)
                asset = sudo.env.cr.dictfetchall()
                
                data = {}
                data['data_ids'] = []
                
                for line in asset:
                    obj = {}
                    obj['asset_code'] = line['code'] or ' '
                    obj['asset_name'] = line['name'] or ' '
                    obj['company_id'] = line['company_id'] or ' '
                    obj['date'] = (line['date']).strftime('%Y-%m-%d') or ' '
                    obj['asset_brand'] = line['brand'] or ' '
                    obj['asset_vendor'] = line['vendor_ref'] or ' '
                    data['data_ids'] += [obj] or ' '

                data = datas.convert(data)
                data = datas.json(data, cdata=False)
                open('/opt/odoo16/logs/belajar.log','a+').write('\n' + str(data))
                
                import requests
                uname = request.env.company.uname_jasper
                password = request.env.company.pass_jasper
                execution = requests.post('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions',
                    auth=(uname, password),
                    json={
                        'reportUnitUri':
                        '/Mayapada16/Accounting/Print_Out_fix_Asset_Barcode_Multiple',
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
                
                # Encode binary data to base64
                encoded_data = base64.b64encode(result.content)
                self.file_src = encoded_data
                
    # @api.multi
    def print_qrcode_termal(self):
        print ("On-Progress")
        # raise exceptions.ValidationError("On-Progress")
        # action = {}
        # action['type'] = 'ir.actions.act_url'
        # action['url'] = '/account/print_out_qr_asset?format=multiple&id=' + str(self.id)
        # action['target'] = 'new'
        # return action


class AccountAssetCipPostingWizard(models.TransientModel):
    _name = 'account.asset.cip.posting.wizard'
    
    sync_type = sync.type
    sync_date = sync.date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    def _default_get_company(self):
        return self.env.company.id

    def _get_cip_id(self):
        return self.env.context.get('cip_id')

    company_id = fields.Many2one('res.company', default=_default_get_company, string='Company', readonly=True)
    cip_id = fields.Many2one('account.asset.cip', string="CIP ID.", default=_get_cip_id, index=True)
    cip_no = fields.Char(string='CIP No.')
    cip_name = fields.Char(string='CIP Name')
    total_value = fields.Float(string="Total Value")
    classification = fields.Selection([('purchase', 'Purchase Item'),('work','Work Order')], string="Classification", store=True)
    location_id = fields.Many2one('hr.department', string="Location", index=True)
    depreciation_number = fields.Float(string="Depreciation Number")
    asset_categ_id = fields.Many2one('account.asset.category', string="Asset Category", index=True)
    asset_subcateg_id = fields.Many2one('account.asset.subcategory', string="Asset SubCategory", index=True)
    asset_name = fields.Char(string="Asset Name")
    # warning_value = fields.Char(string="Warning", store=True)
    accounting_date = fields.Date(string="Accounting Date")
    account_id = fields.Many2one('account.account', string="CIP Account", index=True)
    # journal_id = fields.Many2one('account.journal', string="Expense Journal", index=True)
    # Tambahan 20221125
    estimation = fields.Float(string="Estimasi Value")
    total_value = fields.Float(string="Total Value")
    total_realization = fields.Float(string="Total Realisasi")
    total_pending = fields.Float(string="Total Pending")
    qty = fields.Float(string="Asset Qty")
    value = fields.Float(string="Asset Value Per Item")
    total_asset= fields.Float(string="Asset Value Total")
    move_ids = fields.Many2many('account.move', string="Journal Entries")


    @api.onchange('cip_id')
    def _get_cip(self):
        if self:
            self.cip_no = self.cip_id.number
            self.cip_name = self.cip_id.name
            self.total_value = self.cip_id.total_value
            self.classification = self.cip_id.classification
            self.total_value = self.cip_id.total_value
            self.total_realization = self.cip_id.total_realization
            self.total_pending = self.cip_id.total_pending
            self.total_asset = self.cip_id.total_pending
            self.value = 0
            # self.warning_value = self.get_value_info()


    @api.onchange('qty','total_asset')
    def _onchange_value(self):
        if self:
            if self.total_asset != 0 and self.qty != 0:
                self.value = self.total_asset / self.qty


    # @api.multi
    def post(self):
        record = self.sudo()
        if record:
            for line in range(int(record.qty)):
                asset = record.env['account.asset.asset'].create({
                    'name' : record.asset_name,
                    'category_id' : record.asset_categ_id.id,
                    'subcategory_id' : record.asset_subcateg_id.id,
                    'date' : record.accounting_date,
                    'location_id' : record.location_id.id,
                    'method_number' : record.depreciation_number,
                    'value' : record.value,
                    'cip_id' : record.cip_id.id,
                    'method_period' : '1'
                })

                # Create Account Move
                if asset:
                    move = record.create_move(record, asset)
                    move.action_post()
                    if move:
                        record.cip_id.state = 'progress'


    # @api.multi
    def create_move(self, record, asset):
        obj_debit = {}
        obj_debit['name'] = record.asset_name
        obj_debit['journal_id']  = record.asset_categ_id.journal_id.id
        obj_debit['account_id'] = record.asset_categ_id.account_asset_id.id
        obj_debit['debit'] = abs(asset.value)
        obj_debit['credit'] = 0
        obj_debit['account_asset_id'] = asset.id or None
        obj_debit['cip_id'] = record.cip_id.id

        obj_credit = {}
        obj_credit['name'] = record.asset_name
        obj_credit['journal_id'] = record.asset_categ_id.journal_id.id
        obj_credit['account_id'] = record.account_id.id
        obj_credit['debit'] = 0
        obj_credit['credit'] = abs(asset.value)
        obj_credit['account_asset_id'] = asset.id or None
        obj_credit['cip_id'] = record.cip_id.id

        move_line = [(0, 0, obj_debit), (0, 0, obj_credit)]
        
        if move_line:
            move = record.env['account.move'].create({
                'company_id' : record.company_id.id,
                'name' : record.asset_name,
                'journal_id' : record.asset_categ_id.journal_id.id,
                'date' : record.accounting_date,
                'ref' : "CIP : " + str(record.cip_id.reference_no),
                'account_asset_id' : asset.id or None,
                'cip_id' : record.cip_id.id,
                'line_ids' : move_line
            })
        
        return move


# bikinan eca
class AssetMoveWizard(models.TransientModel):
    _name = 'account.asset.move.wizard'
    move_ids = fields.Many2many('account.move', string="Account Move")

    # @api.multi
    def post(self):
        if self.move_ids:
            # Validate To One Payer Select
            move_ids = self.move_ids.ids
            if move_ids:
                move_ids.append(0)
            
            move_ids = tuple(move_ids)
            query = "UPDATE account_move set state = 'posted' where id in {}".format(move_ids)
            self.env.cr.execute(query)



class PrintAssetPdfWizard(models.TransientModel):
    _name = 'print.asset.pdf.wizard'
    _description = 'PDF Viewer Wizard'
    
    pdf_file = fields.Binary('PDF File')
    pdf_filename = fields.Char('PDF Filename')
    iframe_code = fields.Html(string="Embedded Form", sanitize=False)
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        pdf_base64 = res.get('pdf_file').decode('utf-8') if res.get('pdf_file') else ""

        pdf_data_url = f"data:application/pdf;base64,{pdf_base64}" if pdf_base64 else ""

        iframe_html = f"""
            <iframe 
                src="{pdf_data_url}"
                width="100%" 
                height="600px" 
                style="border: none;">
            </iframe>
        """

        res['iframe_code'] = iframe_html
        return res

    # @api.model
    # def default_get(self, fields_list):
    #     res = super().default_get(fields_list)
    #     pdf_base64 = res.get('pdf_file').decode('utf-8') if res.get('pdf_file') else ""
    #     pdf_filename = res.get('pdf_filename') or "download.pdf"

    #     pdf_data_url = f"data:application/pdf;base64,{pdf_base64}" if pdf_base64 else ""

    #     iframe_html = f"""
    #         <div style="margin-bottom: 10px;">
    #             <a 
    #                 href="{pdf_data_url}" 
    #                 download="{pdf_filename}" 
    #                 style="padding: 8px 12px; background-color: #007bff; color: white; text-decoration: none; border-radius: 4px;">
    #                 📥 Download PDF
    #             </a>
    #         </div>
    #         <iframe 
    #             src="{pdf_data_url}"
    #             width="100%" 
    #             height="600px" 
    #             style="border: none;">
    #         </iframe>
    #     """

    #     res['iframe_code'] = iframe_html
    #     return res



class AccountAssetAsset(models.Model):
    _inherit = 'account.asset.asset'

    sync_type = sync.type
    sync_date = sync.date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    account_analytic_id = fields.Many2one('account.analytic.account',string="Analytic Account",related='category_id.account_analytic_id')
    serial_number = fields.Char(string="SN Manual Asset")
    calibration_date = fields.Date(string="Calibration Date")
    guarantee_date = fields.Date(string="Guarantee Date")
    status = fields.Selection([('1', 'Layak Pakai'),('2', 'Tidak Layak Pakai')],string="Status")
    qty = fields.Float(string="Quantity")
    remarks = fields.Char(string="Cancel Remarks")
    brand = fields.Char(string="Brand")
    type_char = fields.Char(string="Type Char")
    location_ids = fields.Many2many('stock.location', string="Location")
    vendor_ref = fields.Char(string="Vendor Reference")

    # location_freetext = fields.Char(string="Location")
    # location = fields.Many2one('stock.location',string="Location Asset",domain=[('usage', '=', 'internal')])
    location_id = fields.Many2one('hr.department', string="Location")
    origin_location_id = fields.Many2one('hr.department', string="Origin Location")
    
    #Start----edited by eca
    sequence = fields.Char(string="Serial Number", readonly=False)
    location_history_ids = fields.One2many('account.asset.location.history','asset_id',string="Location history")
    #End----edited by eca
    name = fields.Char(string='Asset Name',required=True,readonly=True,index=True,states={'draft': [('readonly', False)]})
    code = fields.Char(string='Reference',index=True,readonly=True,states={'draft': [('readonly', False)]})
    company_id = fields.Many2one('res.company',string='Company',index=True,required=True,readonly=True,states={'draft': [('readonly', False)]},default=lambda self: self.env['res.company']._company_default_get('account.asset.asset'))
    category_id = fields.Many2one('account.asset.category',string='Category',index=True,required=True,change_default=True,readonly=True,states={'draft': [('readonly', False)]})
    subcategory_id = fields.Many2one('account.asset.subcategory',string='Sub Category', index=True, states={'draft': [('readonly', False)]})
    date = fields.Date(string='Date',index=True,required=False,readonly=True,states={'draft': [('readonly', False)]},default=fields.Date.context_today,oldname="purchase_date")
    partner_id = fields.Many2one('res.partner',string='Partner',index=True,readonly=True,states={'draft': [('readonly', False)]})
    invoice_id = fields.Many2one('account.invoice',index=True,string='Invoice',states={'draft': [('readonly', False)]},copy=False)
    picking_id = fields.Many2one('stock.picking', string="Shipment/Rcv No.")
    picking_asset_id = fields.Many2one('stock.picking.asset', string="Picking Asset ID")
    type = fields.Selection(related="category_id.type",index=True,string='Type',required=True)

    modify_enabled = fields.Boolean(string="Modify Enabled", compute="_get_rule")
    file_src = fields.Char(string="File Source", compute="_get_src")
    cip_id = fields.Many2one('account.asset.cip', string="CIP No.", index=True)
    value_depreciation = fields.Float(string="Total Depresiasi", compute="_get_depreciation")

    # Sell/Dispose
    selling_price = fields.Float(string="Selling Price")
    item_status = fields.Selection([('sell', 'Sell'), ('dispose','Dispose')], string="Item Status")
    item_status_desc = fields.Char(string="Status", compute="_get_item_status")
    close_id = fields.Many2one('account.asset.close', string="Close No.", index=True)

    # Relocation
    relocation_id = fields.Many2one('asset.relocation', string="Relocation No.", index=True)
    asset_status = fields.Selection([('inplace', 'In-place'),('loaned','Loaned')], string="Asset Status", default='inplace')
    loan_date = fields.Date(string="Loan Date")
    return_date = fields.Date(string="Return Date")
    relocation_charge = fields.Float(string="Relocation Charge")
    account_id = fields.Many2one('account.account', string="Account", index=True)
    credit_account_id = fields.Many2one('account.account', string="Credit Account", index=True)


    def _get_item_status(self):
        record = self.sudo()
        if record:
            for asset in record:
                if asset.item_status == "sell":
                    asset.item_status_desc = "SOLD"
                elif asset.item_status == "dispose":
                    asset.item_status_desc = "DISPOSE"
                else:
                    asset.item_status_desc = "-"
    
    def _get_depreciation(self):
        record = self.sudo()
        if record:
            for asset in record:
                value_depreciation = 0
                line = record.env['account.asset.depreciation.line'].search([('asset_id','=', asset.id), ('move_check','=', True)])
                for a in line:
                    value_depreciation += float(a.amount)
                asset.value_depreciation = value_depreciation

    # @api.one
    def _get_rule(self):
        record = self.sudo()
        if record:
            record.env.cr.execute("""
                SELECT rs.id, rg.name from res_groups_users_rel rl 
                        INNER JOIN res_groups rg ON rl.gid=rg.id
                        INNER JOIN res_users rs ON rl.uid=rs.id
                WHERE rs.id={res_id} and UPPER(rg.name->>'en_US') LIKE '%CORP%'
            """.format(
                res_id=record.env.user.id))

            rule = record.env.cr.dictfetchall()
            record.modify_enabled = True if rule else False
            
    # @api.multi
    def _get_src(self):
        from . import datas
        # from datas import convert, json, encode
        from odoo.http import request

        record = self.sudo()
        if record:
            id = int(record.id)

            asset = record.env['account.asset.asset'].search([('id', '=', id)])
            
            data = {}
            data['data_ids'] = []
            
            for record in asset:
                obj = {}
                obj['asset_code'] = record.code
                obj['asset_name'] = record.name
                obj['company_id'] = record.company_id.name
                obj['date'] = (record.date).strftime('%Y-%m-%d')
                obj['asset_brand'] = record.brand
                obj['asset_vendor'] = record.vendor_ref
                data['data_ids'] += [obj]

            # data = datas.convert(data)
            data = datas.json(data, cdata=False)

            import requests
            uname = request.env.company.uname_jasper
            password = request.env.company.pass_jasper
            execution = requests.post('http://10.2.1.120:8080/jasperserver/rest_v2/reportExecutions',
                auth=(uname, password),
                json={
                    'reportUnitUri':
                    '/Mayapada16/Accounting/Print_Out_fix_Asset_Barcode',
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
            url = "http://10.2.1.120:8080/jasperserver/services/repository?wsdl"
            
            # Encode binary data to base64
            encoded_data = base64.b64encode(result.content)
            self.file_src = encoded_data.decode('utf-8')


    # @api.multi
    def return_asset(self):
        record = self.sudo()
        if record:
            # validation return
            if not record.origin_location_id:
                raise exceptions.ValidationError(_('Asset has been returned....!!!'))

            asset_id = record.id
            source_id = record.location_id.id
            location_id = record.origin_location_id.id

            hist = record.create_location_history(asset_id, source_id, location_id)
            if hist:
                record.loan_date = None
                record.return_date = None
                record.relocation_charge = None
                record.account_id = None
                record.credit_account_id = None
                record.relocation_id = None
                record.location_id = record.origin_location_id
                record.origin_location_id = None
                record.asset_status = "inplace"

    # @api.multi
    def create_location_history(self, asset_id, source_id, location_id):
        record = self.sudo()
        # adding hitory location
        hist = record.env['account.asset.location.history'].create({
            'asset_id' : asset_id,
            'source_id' : source_id,
            'location_id' : location_id,
            'date_modified' : tools.datetime.now().strftime('%Y-%m-%d')
        })

        return hist

    # @api.multi
    def set_to_modify(self):
        action = {}
        action['name'] = 'Asset Modify'
        action['type'] = 'ir.actions.act_window'
        action['res_model'] = 'account.asset.modify.wizard'
        action['view_type'] = 'form'
        action['view_mode'] = 'form'
        action['target'] = 'new'
        action['context'] = {'asset_id': self.id}
        return action

    # @api.multi
    def name_get(self):
        res = []
        for record in self:
            res.append((record.id, record.code or "[None]"))
        return res
    
    @api.model
    def compute_generated_entries(self, date_start, date_end, asset_type=None, category_ids=[], company_id=None, post_move=False):
        # Entries generated : one by grouped category and one by asset from ungrouped category
        created_move_ids = []
        type_domain = []
        category_ids += [0]

        if asset_type:
            type_domain = [('type', '=', asset_type)]

        # open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'cari aset')
        ungrouped_assets = self.env['account.asset.asset'].search(type_domain + [('state', '=', 'open'), ('category_id.group_entries', '=', False),('category_id','in',category_ids),('company_id','=',company_id)])
        # open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'ketemu ungrouped asset')
        created_move_ids += ungrouped_assets._compute_entries(date_start=date_start, date_end=date_end, group_entries=False, category_ids=category_ids, company_id=company_id, post_move=post_move)
        # open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'done compute ungrouped asset')
        for grouped_category in self.env['account.asset.category'].search(type_domain + [('group_entries', '=', True),('id','in',category_ids)]):
            assets = self.env['account.asset.asset'].search([('state', '=', 'open'), ('category_id', '=', grouped_category.id),('category_id','in',category_ids),('company_id','=',company_id)])
            # open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'ketemu asset')
            created_move_ids += assets._compute_entries(date_start=date_start, date_end=date_end, group_entries=True, category_ids=category_ids, company_id=company_id, post_move=post_move)
            # open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'done compute asset')
        return created_move_ids


    # 2021.10.02 - revisi depresiasi asset bedain analytic untuk depresiasi dan expense depresiasi
    # @api.multi
    def _compute_entries(self, date_start='2021-01-01', date_end='2021-01-01', group_entries=False, category_ids=[], company_id=None, post_move=False):
        query = """
            SELECT 
                asdl.id, 
                asdl.depreciation_date, 
                concat('DEPRE ', to_char(asdl.depreciation_date, 'YYYY-MM'), '/', cast(asdl.sequence as varchar), ' of ', cast(coalesce(ass.sequence, ass.code, ass.name) as varchar)) move_name, 
                asdl.amount,
                asdl.asset_id,
                ass.company_id,
                ass.category_id,
                aac.name category_name,
                ass.currency_id current_currency,
                rc.currency_id company_currency,
                aac.name line1_name_group,
                concat(ass.name, ' (', asdl.sequence,'/', asdl_total.total_depreciation,')') line1_name,
                aac.account_depreciation_id line1_account_id,
                ass.partner_id line1_partner_id,
                asdl.amount line1_amount,
                aac.journal_id line1_journal_id,
                aac.account_analytic_id line1_analytic_account_id,
                aac.name line2_name_group,
                concat(ass.name, ' (', asdl.sequence,'/', asdl_total.total_depreciation,')') line2_name,
                aac.account_depreciation_expense_id line2_account_id,
                ass.partner_id line2_partner_id,
                asdl.amount line2_amount,
                aac.journal_id line2_journal_id,
                aac.expense_analytic_id line2_analytic_account_id,
                aac.name move_ref_group,
                coalesce(ass.code,'') move_ref,
                asdl.depreciation_date move_date,
                aac.journal_id move_journal_id,
                ass.partner_id move_partner_id
            FROM account_asset_depreciation_line asdl 
            INNER JOIN account_asset_asset ass ON ass.id = asdl.asset_id  
            LEFT JOIN account_asset_category aac ON aac.id = ass.category_id
            LEFT JOIN res_company rc ON rc.id = ass.company_id 
            LEFT JOIN (
                SELECT t.asset_id, count(*) total_depreciation
                FROM account_asset_depreciation_line t 
                GROUP BY t.asset_id 
            ) asdl_total ON asdl_total.asset_id=asdl.asset_id
            WHERE asdl.depreciation_date >= '{date_start}'
            AND asdl.depreciation_date <= '{date_end}' 
            AND asdl.move_check is not True 
            AND asdl.move_id is null
            AND ass.state = 'open'
            AND ass.active is True
            AND ass.company_id = {company_id}
            AND ass.category_id in {category_ids}
            """ . format(
                date_start=date_start, 
                date_end=date_end,
                company_id=company_id,
                category_ids=tuple(category_ids)
            )
        open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'query \n' + query)
        self.env.cr.execute(query)
        result = self.env.cr.dictfetchall()
        result_ids = []
        sno = 0
        # for row in result:
        #     sno += 1
        #     created_move = self.env['account.move']
        #     depreciation_id = self.env['account.asset.depreciation.line'].browse(row['id'])
        #     prec = self.env['decimal.precision'].precision_get('Account')

        #     move_line_1 = {
        #         'name': row['line1_name'],
        #         'account_id': row['line1_account_id'],
        #         'debit': (0.0 if row['line1_amount'] > 0.0 else abs(row['line1_amount'])),
        #         'credit': (row['line1_amount'] if row['line1_amount'] > 0.0 else 0.0),
        #         'journal_id': row['line1_journal_id'],
        #         'partner_id': row['line1_partner_id'],
        #         'analytic_account_id': row['line1_analytic_account_id'] or None,
        #         'currency_id': row['company_currency'] != row['current_currency'] and row['current_currency'] or False,
        #         'amount_currency': 0.0
        #         #'amount_currency': row.company_currency != row.current_currency and - 1.0 * row.amount or 0.0,
        #     }
            
        #     move_line_2 = {
        #         'name': row['line2_name'],
        #         'account_id': row['line2_account_id'],
        #         'credit': (0.0 if row['line2_amount'] > 0.0 else abs(row['line2_amount'])),
        #         'debit': (row['line2_amount'] if row['line2_amount'] > 0.0 else 0.0),
        #         'journal_id': row['line2_journal_id'],
        #         'partner_id': row['line2_partner_id'],
        #         'analytic_account_id': row['line2_analytic_account_id'] or None,
        #         'currency_id': row['company_currency'] != row['current_currency'] and row['current_currency'] or False,
        #         'amount_currency': 0.0
        #         #'amount_currency': company_currency != current_currency and line.amount or 0.0,
        #     }
        #     move_vals = {
        #         'company_id': company_id,
        #         'ref': row['move_ref'],
        #         'date': row['move_date'] or False,
        #         'journal_id': row['move_journal_id'],
        #         'line_ids': [(0, 0, move_line_1), (0, 0, move_line_2)],
        #     }
        #     move = self.env['account.move'].create(move_vals)
        #     depreciation_id.write({'move_id': move.id, 'move_check': True})
        #     created_move |= move
        #     # open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + str(sno) + ' created move for asset_id = ' + str(row['asset_id']))
        #     # open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + str(post_move))
        #     if post_move and created_move:
        #         created_move.action_post()
        #         depreciation_id.write({'move_posted_check': True})
        #     result_ids += [created_move.id]
        # return result_ids

        for row in result:
            sno += 1

            # begin debug
            open('/opt/odoo16/logs/log_depreciation_asset.log', 'a+').write('\n\n' + ' ****** Begin for ' + row['move_name'] + ' ****** ')

            # create account_move
            move_sql = """
                INSERT INTO public.account_move (
                    create_uid, create_date, write_uid, write_date, 
                    company_id, currency_id, "date", "name", "state", "ref",
                    journal_id, journal_name, amount, /*matched_percentage,*/ partner_id, 
                    account_asset_id, asset_line_id, sync_type, sync_consol_date, 
                    trigger_write, trigger_create, move_type, auto_post) 
                SELECT 
                    {user_id} as create_uid, now() as create_date, 
                    {user_id} as write_uid, now() as write_date, 
                    aj.company_id as company_id, 
                    coalesce(aj.currency_id, rc.currency_id) as currency_id,
                    '{date}' as "date",
                    '{name}' as "name", 
                    '{state}' as "state", 
                    '{ref}' as "ref", 
                    aj."id" as journal_id, 
                    aj."name" as journal_name, 
                    {amount}::float amount, 
                    --'1.0' as matched_percentage, 
                    {partner_id} as partner_id, 
                    {asset_id} as account_asset_id, 
                    {asset_id} as asset_line_id, 
                    rc.sync_type, 
                    now() as sync_consol_date, 
                    False::bool as trigger_write, 
                    False::bool as trigger_create,
                    'entry' move_type,
                    'no' auto_post
                FROM account_journal aj 
                INNER JOIN res_company rc ON rc.id = aj.company_id 
                WHERE aj.id = {journal_id}
                RETURNING id
            """.format(
                user_id = self.env.user.id, 
                date = row['move_date'],
                name = row['move_name'].replace("'", "") or "",
                state = 'posted' if post_move else 'draft',
                ref = row['move_ref'].replace("'", "") or "",
                amount = row['amount'],
                partner_id = row['move_partner_id'] or "null",
                asset_id = row['asset_id'],
                journal_id = row['move_journal_id']
            )
            open('/opt/odoo16/logs/log_depreciation_asset.log', 'a+').write('\n' + str(move_sql))
            self.env.cr.execute(move_sql)
            move_id = self.env.cr.fetchone()[0]

            if not move_id:
                raise UserError("Failed to create move entries for " + str(row['move_name']))
            
            # update depreciation_line
            depreciation_line_sql = """
                UPDATE public.account_asset_depreciation_line AS dpl SET 
                    move_id = {move_id}, move_check = {move_check}, move_posted_check = {move_posted_check}
                WHERE dpl.id = {depreciation_id}
            """.format(
                depreciation_id = row['id'],
                move_id = move_id,
                move_check = "True", 
                move_posted_check = "True" if post_move else "False"
            )
            open('/opt/odoo16/logs/log_depreciation_asset.log', 'a+').write('\n' + str(depreciation_line_sql))
            self.env.cr.execute(depreciation_line_sql)


            # create move_line credit
            move_credit_sql = """
                INSERT INTO public.account_move_line (
                    create_uid, create_date, write_uid, write_date,
                    move_id, company_id, journal_id,
                    date, date_maturity, partner_id, ref, name, 
                    account_id, analytic_account_id,
                    debit, credit, balance, 
                    amount_currency, currency_id,
                    display_type
                )
                SELECT 
                    am.create_uid, am.create_date, 
                    am.write_uid, am.write_date,
                    am.id as move_id, am.company_id, 
                    {journal_id} as journal_id,
                    am.date, am.date as date_maturity, 
                    {partner_id} as partner_id, 
                    am.ref, '{name}' as "name", 
                    {account_id} as account_id, 
                    {analytic_account_id} as analytic_account_id,
                    {debit} as debit, {credit} as credit, 
                    {balance} as balance, 
                    0.0::float as amount_currency, 
                    am.currency_id,
                    'product' display_type
                FROM account_move am
                WHERE am.id = {move_id}
            """.format(
                move_id = move_id, 
                name = row['line1_name'].replace("'", "") or "",
                account_id = row['line1_account_id'],
                debit = (0.0 if row['line1_amount'] > 0.0 else abs(row['line1_amount'])),
                credit = (row['line1_amount'] if row['line1_amount'] > 0.0 else 0.0),
                balance = (-1 * row['line1_amount'] or 0.0),
                journal_id = row['line1_journal_id'],
                partner_id = row['line1_partner_id'] or "null",
                analytic_account_id = row['line1_analytic_account_id'] or "null",
                currency_id = row['company_currency'] != row['current_currency'] and row['current_currency'] or False
            )
            open('/opt/odoo16/logs/log_depreciation_asset.log', 'a+').write('\n' + str(move_credit_sql))
            self.env.cr.execute(move_credit_sql)

            # create move_line debit
            move_debit_sql = """
                INSERT INTO public.account_move_line (
                    create_uid, create_date, write_uid, write_date,
                    move_id, company_id, journal_id,
                    date, date_maturity, partner_id, ref, name, 
                    account_id, analytic_account_id,
                    debit, credit, balance, 
                    amount_currency, currency_id,
                    display_type
                )
                SELECT 
                    am.create_uid, am.create_date, 
                    am.write_uid, am.write_date,
                    am.id as move_id, am.company_id, 
                    {journal_id} as journal_id,
                    am.date, am.date as date_maturity, 
                    {partner_id} as partner_id, 
                    am.ref, '{name}' as "name", 
                    {account_id} as account_id, 
                    {analytic_account_id} as analytic_account_id,
                    {debit} as debit, {credit} as credit, 
                    {balance} as balance, 
                    0.0::float as amount_currency, 
                    am.currency_id,
                    'product' display_type
                FROM account_move am
                WHERE am.id = {move_id}
            """.format(
                move_id = move_id, 
                name = row['line2_name'].replace("'", "") or "",
                account_id = row['line2_account_id'],
                credit = (0.0 if row['line2_amount'] > 0.0 else abs(row['line2_amount'])),
                debit = (row['line2_amount'] if row['line2_amount'] > 0.0 else 0.0),
                balance = (row['line2_amount'] or 0.0),
                journal_id = row['line2_journal_id'],
                partner_id = row['line2_partner_id'] or "null",
                analytic_account_id = row['line2_analytic_account_id'] or "null",
                currency_id = row['company_currency'] != row['current_currency'] and row['current_currency'] or False,
            )
            open('/opt/odoo16/logs/log_depreciation_asset.log', 'a+').write('\n' + str(move_debit_sql))
            self.env.cr.execute(move_debit_sql)

            open('/opt/odoo16/logs/log_depreciation_asset.log', 'a+').write(' ****** Ending for ' + row['move_name'] + ' ****** \n')
            # End for debug

            result_ids += [move_id]
        return result_ids
        
    


    # @api.multi
    # def _compute_entries(self, date, group_entries=False, category_id=None, company_id=None):
    #     query = """
    #         SELECT asdl.id 
    #         FROM account_asset_depreciation_line asdl 
    #         INNER JOIN account_asset_asset ass ON ass.id = asdl.asset_id 
    #         WHERE asdl.depreciation_date <= '{date}' 
    #             AND asdl.move_check is not True 
    #             AND ass.state = 'open'
    #             AND ass.company_id = {company_id}
    #             AND ass.category_id = {category_id}
    #         """ . format(
    #             date=date, 
    #             company_id=company_id,
    #             category_id=category_id
    #         )
    #     open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'query \n' + query)
    #     self.env.cr.execute(query)
    #     fetch = self.env.cr.dictfetchall()
    #     ids = [row['id'] for row in fetch]
    #     open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'data \n' + str(ids))
    #     depreciation_ids = self.env['account.asset.depreciation.line'].browse(ids)
    #     # depreciation_ids = self.env['account.asset.depreciation.line'].search([('company_id', '=', company_id), ('depreciation_date', '<=', date), ('move_check', '=', False)])
    #     count = len(depreciation_ids)
    #     open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'count: ' + str(count))
    #     # move_ids = []
    #     # if group_entries:
    #     #     open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'create group entries')
    #     #     #return depreciation_ids.create_grouped_move()
    #     #     for record in depreciation_ids:
    #     #         result_ids = Queue()
    #     #         open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'create proess ' + str(record))
    #     #         p = Process(target=record.create_grouped_move(post_move=True, result_ids=result_ids),args=(True,result_ids))
    #     #         p.start()
    #     #         p.join()
    #     #         move_ids += result_ids.get()
    #     # else:
    #     #     open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'create group entries')
    #     #     #return depreciation_ids.create_grouped_move()
    #     #     for record in depreciation_ids:
    #     #         result_ids = Queue()
    #     #         open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'create proess ' + str(record))
    #     #         p = Process(target=record.create_move(post_move=True, result_ids=result_ids),args=(True,result_ids))
    #     #         p.start()
    #     #         p.join()
    #     #         move_ids += result_ids.get()
    #     # return move_ids
    #     # open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + str(depreciation_ids))
    #     # open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'start')
    #     # depreciation_ids = self.env['account.asset.depreciation.line'].search([('asset_id', 'in', self.ids), ('depreciation_date', '<=', date), ('move_check', '=', False)])
    #     # open('/opt/odoo16/logs/asset.log', 'a+').write('\n' + 'start create_move')
    #     # result = super(AccountAssetAsset, self)._compute_entries(date, group_entries)
    #     if group_entries:
    #         return depreciation_ids.create_grouped_move()
    #     return depreciation_ids.create_move()
        
        
    #Start----edited by eca
    @api.model
    def create(self, vals):
        company = self.env.company
        result = super(AccountAssetAsset, self).create(vals)
        # if result.category_id and not result.code:
        #     asset_code = result.category_id.sequence_id.next_by_id()
        if result.category_id and result.subcategory_id and not result.code:
            asset_code = result.subcategory_id.sequence_id.next_by_id()    
            result.sequence = asset_code
            result.code = asset_code

        return result

    # @api.model
    def print_asset_pdf(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'print.asset.pdf.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_pdf_file': self.file_src,
                'default_pdf_filename': self.name + '.pdf',
            }
        }


    # @api.multi
    def qrcode_print(self):
        print('test')
        # import base64
        # import io

        # decoded_data = base64.b64decode(self.report_data)
        # buffer = io.BytesIO(decoded_data)

        # action = {}
        # action['type'] = 'ir.actions.act_url'
        # action['url'] = '/web/pdf_viewer?data=%s' % (self.file_src)
        # action['target'] = 'new'
        # return action
    
        # return {
        #     'type': 'ir.actions.act_url',
        #     'url': '/web/content/%s?download=true' % (pdf.id),
        #     'target': 'self',
        # }

class AccountAssetCategory(models.Model):
    _inherit = 'account.asset.category'

    sync_type = sync.type
    sync_date = sync.date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    account_analytic_id = fields.Many2one('account.analytic.account', string="Analytic Account", domain=[('type_analytic', '=', 'expense')], index=True)
    expense_analytic_id = fields.Many2one('account.analytic.account', string="Analytic Expense", domain=[('type_analytic', '=', 'expense')], index=True)
    sequence_id = fields.Many2one('ir.sequence', string="Sequence Number", required=True)
    parent_id = fields.Many2one('account.asset.category', domain="[('company_id','=', company_id)]", string="Parent Asset Type", index=True)
    cost_master_id = fields.Many2one('cost.center.master', string="Cost Center", index=True)
    subcateg_ids = fields.One2many('account.asset.subcategory','category_id', index=True, string='Sub Category')

    @api.onchange('parent_id')
    def _sequence_number(self):
        parent_type = str(self.parent_id.name)
    
        if "Building" in parent_type:
            self.sequence_id = self.env['ir.sequence'].search([('name','=', 'Building')], limit=1).id or None
        elif "Vehicles" in parent_type:
            self.sequence_id = self.env['ir.sequence'].search([('name','=', 'Vehicles')], limit=1).id or None
        elif "Medical Equipment" in parent_type:
            self.sequence_id = self.env['ir.sequence'].search([('name','=', 'Medical Equipment')], limit=1).id or None
        elif "Furniture & Fixture" in parent_type:
            self.sequence_id = self.env['ir.sequence'].search([('name','=', 'Furniture & Fixture')], limit=1).id or None
        elif "Machinery" in parent_type:
            self.sequence_id = self.env['ir.sequence'].search([('name','=', 'Machinery')], limit=1).id or None
        elif "Office Equipment" in parent_type:
            self.sequence_id = self.env['ir.sequence'].search([('name','=', 'Office Equipment')], limit=1).id or None
        else:
            self.sequence_id = None


class AccountAssetLocationHistory(models.Model):
    _name = 'account.asset.location.history'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    asset_id = fields.Many2one('account.asset.asset',string='Asset',index=True,required=True,ondelete='cascade')
    location_id = fields.Many2one('hr.department', string="To Location")
    source_id = fields.Many2one('hr.department', string="From Location")
    date_modified = fields.Date(string="Date Modified")



class AccountAssetDateRangeWizard(models.TransientModel):
    _name = 'account.asset.date.range.wizard'

    @api.model
    def _get_company(self):
        return self.env.user.company_id.id
    
    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)
    date_range_ids = fields.Many2many('account.asset.subcategory', string="Sub Category")



    # @api.model
    # def get_view(self,view_id=None, view_type='form', **options):
    #     res = super(AccountAssetDateRangeWizard,self).get_view(view_id=view_id,view_type=view_type, **options)
    #     res['arch'] = """
    #         <form string="Closing Journal">
    #             <group>
    #                 <field name="company_id" />
    #                 <field name="start_date" />
    #                 <field name="end_date" />
    #             </group>
    #             <notebook>
    #                 <page string="Sub Category">
    #                     <field nolabel="1" name="date_range_ids" domain="[('company_id','=',company_id)]">
    #                         <tree>
    #                             <field name="category_id"/>
    #                             <field name="name"/>
    #                             <field name="sequence_id"/>
    #                         </tree>
    #                     </field>
    #                 </page>
    #             </notebook>
    #             <footer>
    #                 <button name="imports" string="Imports" type="object" class="oe_highlight"/>
    #             </footer>
    #         </form>
    #     """
    #     from lxml import etree
    #     doc = etree.XML(res['arch'])
    #     View = self.env['ir.ui.view'].sudo()
    #     res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
    #     return res


    # @api.multi
    def imports(self):
        from datetime import datetime, timedelta

        def loop_through_dates(start_date, end_date, sequence_id):
            # Convert start_date and end_date strings to datetime objects
            start_date = datetime.strptime(str(start_date), "%Y-%m-%d")
            end_date = datetime.strptime(str(end_date), "%Y-%m-%d")

            # Initialize the current_date to start_date
            current_date = start_date

            # Loop through the months and years between start_date and end_date
            while current_date <= end_date:
                # Get the first date of the current month
                first_date_of_month = current_date.replace(day=1)
                
                # Get the last date of the current month
                last_date_of_month = (current_date.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)

                # Print or process current_date, first_date_of_month, and last_date_of_month however you want
                first_date = current_date.strftime("%Y") + "-" + current_date.strftime("%m") + "-" + first_date_of_month.strftime("%d")
                last_date = current_date.strftime("%Y") + "-" + current_date.strftime("%m") + "-" + last_date_of_month.strftime("%d")
                
                # Move to the first day of the next month
                current_date = (current_date.replace(day=1) + timedelta(days=32)).replace(day=1)

                date_range = self.env['ir.sequence.date_range']
                date_range_exist = date_range.search([('date_from','=',first_date), ('date_to','=',last_date), ('sequence_id','=', sequence_id)])
                if not date_range_exist:
                    date_range.create({
                        'sequence_id' : sequence_id,
                        'date_from' : first_date,
                        'date_to' : last_date,
                        'number_next' : 1,
                        'number_next_actual' : 1
                    })

        # Example usage:
        start_date = self.start_date
        end_date = self.end_date

        for line in self.date_range_ids:
            loop_through_dates(start_date, end_date, line.sequence_id.id)