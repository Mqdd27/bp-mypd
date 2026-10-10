from odoo import models, fields, api, tools, exceptions, _
from odoo.addons import decimal_precision as dp
import requests
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.exceptions import UserError
import requests
import json
try:
    import ujson as JSON
except:
    import json as JSON

from . import sync


class ProductIncomePrice(models.Model):
    _name = 'product.income.history'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    product_id = fields.Many2one('product.template', string="Product")
    move_id = fields.Integer(string="Move ID")
    move_type = fields.Char(string="Move Type")
    order_no = fields.Char(string="Order No.")
    stock_in_date = fields.Datetime(string="Stock In Date")
    stock_in_qty = fields.Float(string="Stock In Qty")
    stock_in_uom = fields.Char(string="Stock In UoM")
    stock_in_price = fields.Float(string="Stock In Price")



class BasePriceHistory(models.Model):
    _name = 'product.base_price_manual_line'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    price = fields.Float(string="Base Price Manual")
    product_tmpl_id = fields.Many2one('product.template', string="Product Template")
    price_before = fields.Float(string="Base Price Before")
    input_timestamp = fields.Datetime(string="Timestamp")






class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _default_get_company(self):
        return self.env.company.id

    def _get_default_category_id(self):
        # return self.env.ref('product.product_category_all')
        return self.categ_id.id
    
    sync_categ_id = fields.Float(string="Product Category (Synchronization)", index=True)
    sync_id = sync.id
    sync_date = sync.date
    sync_id_api = sync.id_api
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    sync_is_arcus = sync.is_arcus
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")
    company_id = fields.Many2one('res.company', 'Company', index=True, default=_default_get_company)
    

    # name = fields.Char(string="Product", translate=False)
    service_group_id = fields.Many2one('service.group', string="Service Group")
    asset_category_id = fields.Many2one('account.asset.category', string='Asset Type', company_dependent=False, ondelete="restrict")
    sync_is_service = fields.Boolean(string="Is Service Wipro", default=False, index=True)
    sync_is_package = fields.Boolean(string="Is Package Wipro", default=False, index=True)
    sync_max_days = fields.Integer(string="Package Max Days")
    catalog_code = fields.Char(string="Catalog Code")
    brand = fields.Char(string="Brand Name")
    manufacturer_code = fields.Char(string="Manufacturer Code")
    manufacturer = fields.Char(string="Manufacturer Name")
    categ_id = fields.Many2one('product.category', 'Product Category', index=True, default=_get_default_category_id)
    
    pharmacalogy = fields.Char(string="Pharmacalogy")
    shelf = fields.Char(string="Shelf")
    substore_ids = fields.Many2many('product.substore', string='Substore')
    strength = fields.Integer(string="Strength")
    narcotic = fields.Boolean(string="Narcotic", index=True, default=False)
    generic = fields.Boolean(string="Generic", index=True, default=False)
    psychotropic = fields.Boolean(string="Psychotropic", index=True, default=False)
    antibiotic = fields.Boolean(string="Antibiotic", index=True, default=False)

    # base_price_ids = fields.One2many('product.base_price', 'product_id', string='Base Price') --DR
    # cost_price_ids = fields.One2many('product.cost.price', 'product_id', string='Cost Price') --DR
    price_history_ids = fields.One2many('product.price.history', 'product_tmpl_id', string='History Price')
    product_income_ids = fields.One2many('product.income.history', 'product_id', string="Stock Income")

    # generic_ids = fields.Many2many('product.generic', string='Generic')
    # administrationroute_ids = fields.Many2many('product.administration.route', string='Route of Administration')
    uom2_id = fields.Many2one('uom.uom', string="Purchase UoM")
    conversion_rate = fields.Float(string="Conversion Rate", default=1)
    loblos = fields.Char(string="LOB / LOS")
    consignment = fields.Boolean(string="Consignment", default=False)
    is_pr_item = fields.Boolean(string="PR Item?", default=False)
    mims_ref = fields.Char(string='MIMS Reference')
    mims_type = fields.Char(string='MIMS Type')
    wipro_block = fields.Boolean(string="HIS Blocked")

    base_price = fields.Float(string="Base Price", default=0, readonly=True)
    base_price_manual = fields.Float(string="Base Price (Manual)", default=0)
    base_price_manual_active = fields.Boolean(string="Base Price (Manual) Active")

    product_rack_ids = fields.One2many('product.rack','product_tmpl_id', string="Product Rack")
    base_price_manual_ids = fields.One2many('product.base_price_manual_line', 'product_tmpl_id', string="Base Price Manual history", readonly=True)

    api_post_timestamp = fields.Datetime(string="Timestamp", readonly=True)
    api_post_status = fields.Selection([('done', 'Done'), ('failed', 'Failed')], string='Status', readonly=True)
    api_post_payload = fields.Char(string="Payload", readonly=True)
    api_post_response = fields.Char(string="Response", readonly=True)
    api_post_url = fields.Char(string="URL", readonly=True)
    api_post_key = fields.Char(string="API Key", readonly=True)

    # 2021.09.11 Firgi
    # qty_available = fields.Float('Quantity On Hand', compute='_compute_avail_qty', search='_search_qty_available', digits=dp.get_precision('Product Unit of Measure'))
    qty_available = fields.Float('Quantity On Hand', digits=dp.get_precision('Product Unit of Measure'))
    tracking = fields.Selection([('serial', 'By Unique Serial Number'),('lot', 'By Lots'), ('none', 'No Tracking')], string="Tracking", default='none')
    property_valuation = fields.Selection([
        ('manual_periodic', 'Periodic (manual)'),
        ('real_time', 'Perpetual (automated)')], string='Inventory Valuation',
        company_dependent=True, copy=True, default='manual_periodic',
        help="If perpetual valuation is enabled for a product, the system will automatically create journal entries corresponding to stock moves, with product price as specified by the 'Costing Method'" \
             "The inventory variation account set on the product category will represent the current inventory value, and the stock input and stock output account will hold the counterpart moves for incoming and outgoing products.")
    property_cost_method = fields.Selection([
        ('standard', 'Standard Price'),
        ('average', 'Average Price'),
        ('real', 'Real Price')], string='Costing Method', default='standard',
        company_dependent=True, copy=True,
        help="""Standard Price: The cost price is manually updated at the end of a specific period (usually once a year).
                Average Price: The cost price is recomputed at each incoming shipment and used for the product valuation.
                Real Price: The cost price displayed is the price of the last outgoing product (will be use in case of inventory loss for example).""")
    
    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")

    warranty = fields.Float(string="Warranty")
    rental = fields.Boolean(string="Can be Rent")
    location_id = fields.Many2one('stock.location', string="Location", store=True)
    warehouse_id = fields.Many2one('stock.warehouse', string="Warehouse", store=True)
    use_time = fields.Integer(string="Product Use Time")
    life_time = fields.Integer(string="Product Life Time")
    removal_time = fields.Integer(string="Product Removal Time")
    alert_time = fields.Integer(string="Product Alert Time")
    message_last_post = fields.Datetime(string="Last Message Date")
    track_service = fields.Selection([('manual', 'Manually set quantities on order')], string='Track Service')
    purchase_requisition = fields.Selection([('rfq', 'Create a draft purchase order'), ('tenders', 'Propose a call for tenders')], string='Procurement', default='rfq')

    # description2 = fields.Char(string="Description2", translate=False)
    # description_purchase2 = fields.Char(string="Description Purchase2", translate=False)
    # description_sale2 = fields.Char(string="Description Sale2", translate=False)
    # description_picking2 = fields.Char(string="Description Picking2", translate=False)
    # description_pickingout2 = fields.Char(string="Description Pickingout2", translate=False)
    # description_pickingin2 = fields.Char(string="Description Pickingin2", translate=False)
    # description = fields.Char(string="Description", translate=False)
    # description_purchase = fields.Char(string="Description Purchase", translate=False)
    # description_sale = fields.Char(string="Description Sale", translate=False)
    # description_picking = fields.Char(string="Description Picking", translate=False)
    # description_pickingout = fields.Char(string="Description Pickingout", translate=False)
    # description_pickingin = fields.Char(string="Description Pickingin", translate=False)

    @api.depends('product_variant_ids', 'product_variant_ids.stock_quant_ids')
    def _compute_avail_qty(self):
        for record in self:
            for product in record.product_variant_ids:
                record.env.cr.execute("""SELECT COALESCE(sum(quantity), 0) as qty from stock_quant where product_id = {} and location_id in (select id from stock_location where usage = 'internal')""".format(product.id))
                qty = record.env.cr.dictfetchall()
                # open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(product.id))
                # open('/opt/odoo16/logs/missing.log', 'a+').write('\n' + str(qty))
                for q in qty:
                    record.qty_available += int(q['qty'])

    @api.constrains('sync_id_api', 'sync_type')
    def sync_id_constrains(self):
        for rec in self:
            if rec.sync_id_api and not rec.sync_type:
                raise exceptions.ValidationError(_('Sorry, sync_type cannot be empty!'))


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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'product.template' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'product.template'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        done = super(ProductTemplate, self).create(vals)
        for record in done:

            if record.conversion_rate < 1:
                record.conversion_rate = 1

            if record.env.company.sync_api_active:
                record.env.cr.execute("""
                    DELETE FROM product_template WHERE id IN (
                        SELECT max(a.id) 
                        FROM product_template a 
                        WHERE a.active = True 
                            AND a.sync_id_api IS NOT NULL
                        GROUP BY a.sync_id_api 
                        HAVING count(*) > 1
                    ) """)
        
        if vals.get('company_id'):
            company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
            done.sync_type = company_id.sync_type

        if done.trigger_create == False:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger create product template")
            done.send_api_consol_company()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " +str(done.id)

        open(log_file, 'a').write(message_log)
        return done



    # By Pass Contraint category UOM
    @api.constrains('uom_id', 'uom_po_id')
    def _check_uom(self):
        return True



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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'product.template' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'product.template'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        # kondisi ada perubahan UoM di master tindakan/item dhealth
        if vals.get('uom_id') and vals.get('id') and vals.get('uom_po_id') and vals.get('uom2_id'):
            check_uom = vals['uom_id']
            check_id = vals['id']
            check_uom_po_id = vals['uom_po_id']
            check_uom2 = vals['uom2_id']
            query = """update product_template set uom_id = '%s', uom_po_id='%s', uom2_id ='%s' where id ='%s'""" % (check_uom, check_uom_po_id, check_uom2, check_id)
            self.env.cr.execute(query)

            check_conversion_rate = vals['conversion_rate']
            if check_conversion_rate < 1:                
                vals['conversion_rate'] = 1
            if self.company_id:
                self.sync_type = self.company_id.sync_type
            if self.trigger_write == True:
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger write product template 1")
                query = """
                UPDATE product_template set trigger_write = false
                WHERE id = {self_id}""".format(self_id = self.id)
                self.env.cr.execute(query)
                self.send_api_consol_write_company()
            return super(ProductTemplate, self).write(vals)
        else:
            done = super(ProductTemplate, self).write(vals)
            if self.env.context.get('updated'):
                return done
            self = self.with_context(updated=True)

            for record in self:
                if record.conversion_rate < 1:
                    record.conversion_rate = 1
            if self.company_id:
                self.sync_type = self.company_id.sync_type
            if self.trigger_write == True:
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger write product template 2")
                query = """
                UPDATE product_template set trigger_write = false
                WHERE id = {self_id}""".format(self_id = self.id)
                self.env.cr.execute(query)
                self.send_api_consol_write_company()
            log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
            message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
            message_log += "\n\nuser: " + self.env.user.login + "\n\n Write before return" + "\n ID: " +str(self.id)

            open(log_file, 'a').write(message_log)
            return done



    @api.onchange('sync_type', 'name','type','sale_ok','purchase_ok','default_code','catalog_code','manufacturer_code','manufacturer','brand','pharmacalogy','strength','shelf','mims_ref','mims_type','consignment','sync_max_days','list_price','base_price','base_price_manual','base_price_manual_active','standard_price','conversion_rate','categ_id','uom_id','uom2_id','uom_po_id')
    def onchange_trigger_write(self):
        self.trigger_write = True



    # @api.multi
    def send_api_consol_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_product_template
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "masuk create pt 1")
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""

            if consol_active:
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "masuk create pt 2")
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/product.template"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/product.template"
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
                # values['sync_type'] = int(record.env.company.sync_type)
                # values[consol_id_from] = record.id
                values[consol_id_from] = str(record.id)
                values['name'] = record.name
                values['type'] = str(record.type)
                values['sale_ok'] = record.sale_ok
                values['purchase_ok'] = record.purchase_ok
                values['default_code'] = record.default_code
                values['catalog_code'] = record.catalog_code
                values['manufacturer_code'] = record.manufacturer_code
                values['manufacturer'] = record.manufacturer
                values['brand'] = record.brand
                values['pharmacalogy'] = record.pharmacalogy
                values['strength'] = record.strength
                values['shelf'] = record.shelf
                values['mims_ref'] = record.mims_ref
                values['mims_type'] = record.mims_type
                values['consignment'] = record.consignment
                values['trigger_create'] = True
                values['active'] = record.active
                # values['barcode'] = str(record.barcode)
                values['sync_max_days'] = record.sync_max_days
                values['list_price'] = record.list_price
                values['base_price'] = record.base_price
                values['base_price_manual'] = record.base_price_manual
                values['base_price_manual_active'] = record.base_price_manual_active
                # values['property_cost_method'] = str(record.property_cost_method)
                # values['standard_price'] = record.standard_price
                values['conversion_rate'] = record.conversion_rate
                
                

                if record.categ_id.id == False:
                    values['categ_id'] = record.categ_id.id
                else:
                    values['categ_id'] = str(record.categ_id.id)

                if record.uom_id.id == False:
                    values['uom_id'] = record.uom_id.id
                else:
                    values['uom_id'] = str(record.uom_id.id)

                if record.uom2_id.id == False:
                    values['uom2_id'] = record.uom2_id.id
                else:
                    values['uom2_id'] = str(record.uom2_id.id)

                if record.uom_po_id.id == False:
                    values['uom_po_id'] = record.uom_po_id.id
                else:
                    values['uom_po_id'] = str(record.uom_po_id.id)
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
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "body create product template : " + str(body))
                
                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "response_json create product template : " + str(response_json))
                
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
                super(ProductTemplate, self).write(data_update)

    # @api.multi
    def send_api_consol_write_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "masuk write pt 1")
            consol_active = record.company_id.sync_consol_product_template
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "masuk write pt 2")
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/product.template"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/product.template"
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
                # values['sync_type'] = int(record.env.company.sync_type)
                # values[consol_id_from] = record.id
                values[consol_id_from] = str(record.id)
                values['name'] = record.name
                values['type'] = str(record.type)
                values['sale_ok'] = record.sale_ok
                values['purchase_ok'] = record.purchase_ok
                values['default_code'] = record.default_code
                values['catalog_code'] = record.catalog_code
                values['manufacturer_code'] = record.manufacturer_code
                values['manufacturer'] = record.manufacturer
                values['brand'] = record.brand
                values['pharmacalogy'] = record.pharmacalogy
                values['strength'] = record.strength
                values['trigger_write'] = False
                values['shelf'] = record.shelf
                values['mims_ref'] = record.mims_ref
                values['mims_type'] = record.mims_type
                values['consignment'] = record.consignment
                # values['barcode'] = str(record.barcode)
                values['sync_max_days'] = record.sync_max_days
                values['list_price'] = record.list_price
                values['base_price'] = record.base_price
                values['base_price_manual'] = record.base_price_manual
                values['base_price_manual_active'] = record.base_price_manual_active
                # values['property_cost_method'] = str(record.property_cost_method)
                # values['standard_price'] = record.standard_price
                values['conversion_rate'] = record.conversion_rate
                
                

                if record.categ_id.id == False:
                    values['categ_id'] = record.categ_id.id
                else:
                    values['categ_id'] = str(record.categ_id.id)

                if record.uom_id.id == False:
                    values['uom_id'] = record.uom_id.id
                else:
                    values['uom_id'] = str(record.uom_id.id)

                if record.uom2_id.id == False:
                    values['uom2_id'] = record.uom2_id.id
                else:
                    values['uom2_id'] = str(record.uom2_id.id)

                if record.uom_po_id.id == False:
                    values['uom_po_id'] = record.uom_po_id.id
                else:
                    values['uom_po_id'] = str(record.uom_po_id.id)
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
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "body write product template : " + str(body))
                response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "response_json write product template : " + str(response_json))
                
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
                super(ProductTemplate, self).write(data_update)


    # @api.model
    # def _sync_service_wipro(self, sync_type='1'):
    #     sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '!=', 0)])}
    #     sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name),('sync_type', '=', sync_type)],limit=1)
    #     last_update = tools.datetime.strptime(sync_date.date,'%Y-%m-%d %H:%M:%S').date()
    #     query = """
    #         SELECT 
    #             a.ServiceItemID 'sync_id', 
    #             a.ServiceID 'sync_categ_id', 
    #             a.Name 'name', 
    #             isnull(a.Code,'[NULL]') 'default_code',
    #             convert(bit, 'true') 'sync_is_service', 
    #             cast(BLOCKED-1 as bit) 'wipro_block', 
    #             'service' 'type', 
    #             'True' active, 
    #             'True' sale_ok, 
    #             'False' purchase_ok
    #         FROM dbo.VRP_OdooServiceItems a
    #         WHERE (a.ServiceItemID IN (
    #             SELECT DISTINCT t.ServiceItemID 
    #             FROM dbo.v_DB_A_A_RawDataH30 t 
    #             WHERE convert(varchar(10), t.tglproses, 121) >= '{0}'
    #         ) OR convert(varchar(10), a.CREATEDATE, 121) >= '{0}'
    #           OR convert(varchar(10), a.MODDATE, 121) >= '{0}') 
    #     """.format(last_update)

    #     if sync_date:
    #         # query += " OR date(a.CREATEDATE) >= '{0}' OR date   ".format(tools.datetime.strptime(sync_date.date, '%Y-%m-%d %H:%M:%S').date())
    #         print (query)
    #         sync_date.date = tools.datetime.now()
    #     else:
    #         self.env['sync.date'].sudo().create({
    #             'name':sync.getframe().f_code.co_name,
    #             'sync_type':sync_type
    #         })
    #     data = sync.get_data(sync.servers.get(sync_type), query)
    #     if not data:
    #         print ("No new data available")
    #         return
    #     fields_without_id = tuple(
    #         key for key in self._fields
    #         if key != 'id' and key != 'active' and 'property' not in key
    #         and 'ids' not in key and self._fields[key].required == True
    #         and self._fields[key].store == True)
    #     columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
    #     # fields_without_id += columns
    #     fields = fields_without_id + columns + ('id', )
    #     columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
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
    #     now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:S')
    #     categ_id = self.env.ref('mayapada.product_category_service').id
    #     uom_id = self.env.ref('product.product_uom_categ_unit').id
    #     new_sync_ids = []
    #     for object in data:
    #         new_sync_ids += [object['sync_id']]
    #         for value in default_values:
    #             object[value] = default_values[value]
    #         object['categ_id'] = self.env['product.category'].search([('sync_id', '=', object['sync_categ_id']),('sync_type', '=', sync_type),('sync_is_service', '=', True)],limit=1).id or categ_id
    #         object['uom_id'] = uom_id
    #         object['uom_po_id'] = uom_id
    #         object['uom2_id'] = uom_id
    #         if int(object['sync_id']) in sync_ids:
    #             object['id'] = sync_ids[object['sync_id']]
    #         else:
    #             object['id'] = 'DEFAULT'
    #         object['sync_date'] = now
    #         object['active'] = True
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
        
    #     # insert & update product_template 
    #     query = "INSERT into product_template %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
    #     print (query.encode('utf8'))
    #     self.env.cr.execute(query)
    #     self.env['product.template'].sudo().search([('sync_id', 'in', new_sync_ids)]).create_variant_ids()
        
    #     # update product.product default_code 
    #     query = "UPDATE product_product AS pp SET default_code = pt.default_code FROM product_template pt WHERE pt.id = pp.product_tmpl_id"
    #     print (query.encode('utf8'))
    #     self.env.cr.execute(query)
        

    # @api.model
    # def _sync_product_wipro(self, sync_type='1', date=False):
    #     sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '!=',0)])}
    #     sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name),('sync_type', '=', sync_type)],limit=1)
    #     if not date:
    #         date = tools.datetime.strptime(sync_date.date,'%Y-%m-%d %H:%M:%S').date()

    #     query = """
    #         SELECT DISTINCT 
    #              p.sync_id
    #             ,p.active
    #             ,p.sale_ok
    #             ,p.purchase_ok
    #             ,p.name
    #             ,p.sync_categ_id
    #             ,p.uom_po_id
    #             ,p.uom_id
    #             ,isnull(p.default_code,'[NULL]') default_code
    #             ,p.type
    #             ,p.wipro_block
    #             ,p.strength
    #             ,p.catalog_code
    #             ,p.brand
    #             ,p.manufacturer_code
    #             ,p.manufacturer
    #             ,p.pharmacalogy
    #             ,p.shelf
    #             ,p.narcotic
    #             ,p.generic
    #             ,p.psychotropic
    #             ,p.antibiotic
    #             ,p.conversion_rate 
    #         FROM dbo.VRP_OdooItems p
    #         WHERE p.uom_id IS NOT NULL
    #             AND ( p.sync_id IN (
    #                 --Sales Revenue
    #                 SELECT DISTINCT t.ServiceItemID AS product_id 
    #                 FROM dbo.v_DB_A_A_RawDataH30 t 
    #                 WHERE convert(varchar(10), t.tglproses, 121) >= '{0}' 
    #                 AND t.ServiceID IN(10,17)
                        
    #                 UNION ALL 
    #                 --GRN Items 
    #                 SELECT DISTINCT t.product_id 
    #                 FROM dbo.VRP_OdooModPurchaseReceiptItems t 
    #                 WHERE t.wipro_date >= '{0}'

    #                 UNION ALL 
    #                 --GRN Returns
    #                 SELECT DISTINCT t.product_id 
    #                 FROM dbo.VRP_OdooPurchaseReturnItemsLowest t 
    #                 WHERE convert(varchar(10), t.order_date, 121) >= '{0}'

    #                 UNION ALL 
    #                 --Adjustment 
    #                 SELECT DISTINCT t.ItemID AS product_id
    #                 FROM dbo.VRP_OdooAdjustmentIssue t 
    #                 WHERE convert(varchar(10), t.ConsumptionDate, 121) >= '{0}'
    #             ) OR p.moddate >= '{0}' )
    #         """.format(date)
    #     if sync_date:
    #         # query = query.replace(") sh", ") sh where (i.ItemID in () or i.ItemID in ()) ".
    #         # query = query.replace(") sh", "and i.ItemID in (55256,49008,47386,46852,46965,49053,54742,47424,49095,49096,50278,39414,49035,49013,43777,47760,48158,43804,43808,43807,43806,43809,43859,43803,44718,43805,45244,44578,44578,54998,49038,46505,46506,46508,46507,46511,46509,46510,39435,39436,40666,39451,49019,49023,50040,44357,49000,50256,47433,48867,44357,49044,32873,34131,49031,49006,44652,49055,49747,46504)) sh".format(tools.datetime.strptime(sync_date.date, '%Y-%m-%d %H:%M:%S').date()))
    #         print (query)
    #         sync_date.date = tools.datetime.now()
    #     else:
    #         self.env['sync.date'].sudo().create({
    #             'name':sync.getframe().f_code.co_name,
    #             'sync_type':sync_type
    #         })
    #     data = sync.get_data(sync.servers.get(sync_type), query)
    #     if not data:
    #         print ("No new data available")
    #         return
    #     fields_without_id = tuple(
    #         key for key in self._fields
    #         if key != 'id' and key != 'active' and key != 'wipro_block'
    #         and 'property' not in key and 'ids' not in key and self.
    #         _fields[key].required == True and self._fields[key].store == True)
    #     columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
    #     fields = fields_without_id + columns + ('id', )
    #     fields_without_id += columns
    #     columns += tuple(key for key in data[0].keys() if key in self._fields and key not in columns) if data else ()
    #     if columns:
    #         columns += ('id', )
    #     default_values = {}
    #     uom_id = self.env.ref('product.product_uom_categ_unit').id
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
    #     now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:S')
    #     new_sync_ids = []

    #     # open('/opt/odoo16/logs/debug.log', 'w+').write(str(fields))
    #     # open('/etc/odoo/log_custom/report.log', 'w+').write(str(fields))
    #     for object in data:
    #         new_sync_ids += [object['sync_id']]
    #         for value in default_values:
    #             object[value] = default_values[value]
    #         if object['uom_id'] and object['uom_po_id']:
    #             object['uom_id'] = self.env['uom.uom'].search([('sync_type', '=', sync_type), ('sync_id', '=', object['uom_id'])], limit=1).id
    #             object['uom2_id'] = self.env['uom.uom'].search([('sync_type', '=', sync_type), ('sync_id', '=', object['uom_po_id'])], limit=1).id
    #             object['uom_po_id'] = object['uom_id']
    #             if not object['uom_id']:
    #                 object['uom_id'] = uom_id
    #             if not object['uom_po_id']:
    #                 object['uom_po_id'] = object['uom_id']
    #                 object['uom2_id'] = object['uom_id']
    #         if object['sync_categ_id']:
    #             object['categ_id'] = self.env['product.category'].search([('sync_type', '=', sync_type), ('sync_id', '=', object['sync_categ_id'])], limit=1).id
    #             if not object['categ_id']:
    #                 object['categ_id'] = self.env['product.category'].search([('sync_type', '=', sync_type), ('name', 'ilike', 'Obat Keras')], limit=1).id
    #         if int(object['sync_id']) in sync_ids:
    #             object['id'] = sync_ids[object['sync_id']]
    #         else:
    #             object['id'] = 'DEFAULT'
    #         object['sync_date'] = now
    #         object['active'] = True
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
        
    #     # insert & update product_template 
    #     query = "INSERT into product_template %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
    #     self.env.cr.execute(query)
    #     print (query.encode('utf8'))
    #     self.env['product.template'].sudo().search([('sync_id', 'in', new_sync_ids)]).create_variant_ids()
        
    #     # update product.product default_code 
    #     query = "UPDATE product_product AS pp SET default_code = pt.default_code FROM product_template pt WHERE pt.id = pp.product_tmpl_id"
    #     self.env.cr.execute(query)
    #     print (query.encode('utf8'))






# 2021.09.27 - Firgi
class ProductProduct(models.Model):
    _inherit = 'product.product'

    #sync_type = sync.type
    #sync_consol_id_unit = sync.consol_id_unit
    #sync_consol_id_main = sync.consol_id_main
    #sync_consol_date = sync.consol_date
    qty_available = fields.Float('Quantity On Hand',compute='_compute_avail_qty',search='_search_qty_available',digits=dp.get_precision('Product Unit of Measure'))


    @api.depends('stock_quant_ids')
    def _compute_avail_qty(self):
        for record in self:
            record.env.cr.execute("SELECT COALESCE(sum(quantity), 0) as qty from stock_quant where product_id = {} and location_id in (select id from stock_location where usage = 'internal')".format(record.id))
            qty = record.env.cr.dictfetchall()
            for q in qty:
                record.qty_available += int(q['qty'])


    # 2021.09.11 custom column u/ standard price
    # @api.multi
    def _set_standard_price(self, value):
        ''' Store the standard price change in order to be able to retrieve the cost of a product for a given date'''
        PriceHistory = self.env['product.price.history']
        for product in self:
            PriceHistory.create({
                'product_id': product.id,
                'product_tmpl_id': product.product_tmpl_id.id,
                'cost': value,
                'company_id': self._context.get('force_company', self.env.company.id),
            })



    @api.model
    def _convert_prepared_anglosaxon_line(self, line, partner):
        return {
            'date_maturity': line.get('date_maturity', False),
            'partner_id': partner,
            'name': line['name'],
            'debit': line['price'] > 0 and line['price'],
            'credit': line['price'] < 0 and -line['price'],
            'account_id': line['account_id'],
            'analytic_line_ids': line.get('analytic_line_ids', []),
            'amount_currency': line['price'] > 0 and abs(line.get('amount_currency', False)) or -abs(line.get('amount_currency', False)),
            'currency_id': line.get('currency_id', False),
            'quantity': line.get('quantity', 1.00),
            'product_id': line.get('product_id', False),
            'product_uom_id': line.get('uom_id', False),
            'analytic_account_id': line.get('account_analytic_id', False),
            'invoice_id': line.get('invoice_id', False),
            'payment_id': line.get('payment_id', False),
            'purchase_id': line.get('purchase_id', False),
            'sales_id': line.get('sales_id', False),
            'stock_picking_id': line.get('stock_picking_id', False),
            'stock_move_id': line.get('stock_move_id', False),
            'stock_product_id': line.get('stock_product_id', False),
            'stock_categ_id': line.get('stock_categ_id', False),
            'tax_ids': line.get('tax_ids', False),
            'tax_line_id': line.get('tax_line_id', False),
            'analytic_tag_ids': line.get('analytic_tag_ids', False),
        }

    @api.model
    def _anglo_saxon_sale_move_lines(self, name, product, uom, qty, price_unit, currency=False, amount_currency=False, fiscal_position=False, account_analytic=False, analytic_tags=False):
        """Prepare dicts describing new journal COGS journal items for a product sale.

        Returns a dict that should be passed to `_convert_prepared_anglosaxon_line()` to
        obtain the creation value for the new journal items.

        :param Model product: a product.product record of the product being sold
        :param Model uom: a product.uom record of the UoM of the sale line
        :param Integer qty: quantity of the product being sold
        :param Integer price_unit: unit price of the product being sold
        :param Model currency: a res.currency record from the order of the product being sold
        :param Interger amount_currency: unit price in the currency from the order of the product being sold
        :param Model fiscal_position: a account.fiscal.position record from the order of the product being sold
        :param Model account_analytic: a account.account.analytic record from the line of the product being sold
        """
        
        if product.type == 'product' and product.valuation == 'real_time':
            accounts = product.product_tmpl_id.get_product_accounts(fiscal_pos=fiscal_position)
            # debit account dacc will be the output account
            dacc = accounts['stock_output'].id
            # credit account cacc will be the expense account
            cacc = accounts['expense'].id
            if dacc and cacc:
                return [
                    {
                        'type': 'src',
                        'name': name[:64],
                        'price_unit': price_unit,
                        'quantity': qty,
                        'price': price_unit * qty,
                        'currency_id': currency and currency.id,
                        'amount_currency': amount_currency,
                        'account_id': dacc,
                        'product_id': product.id,
                        'uom_id': uom.id,
                        'account_analytic_id': account_analytic and account_analytic.id,
                        'analytic_tag_ids': analytic_tags and analytic_tags.ids and [(6, 0, analytic_tags.ids)] or False,
                    },

                    {
                        'type': 'src',
                        'name': name[:64],
                        'price_unit': price_unit,
                        'quantity': qty,
                        'price': -1 * price_unit * qty,
                        'currency_id': currency and currency.id,
                        'amount_currency': -1 * amount_currency,
                        'account_id': cacc,
                        'product_id': product.id,
                        'uom_id': uom.id,
                        'account_analytic_id': account_analytic and account_analytic.id,
                        'analytic_tag_ids': analytic_tags and analytic_tags.ids and [(6, 0, analytic_tags.ids)] or False,
                    },
                ]
        return []





class UomUom(models.Model):
    _inherit = 'uom.uom'

    @api.model
    def _get_default_company(self):
        company_id = self.env.company.id
        return self.env.company.id     
    company_id = fields.Many2one('res.company', string="Company", default=_get_default_company)
    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")

    sync_id = sync.id
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")
    sync_id_api = sync.id_api
    sync_is_arcus = sync.is_arcus
    code = fields.Char(string="Code")
    # name = fields.Char(string="Unit of Measure", translate=False)
    wipro_block = fields.Boolean(string="Wipro Block", default=False)


    #By Pass Error Different Category#
    # @api.multi
    def _compute_quantity(self, qty, to_unit, round=True, rounding_method='UP'):
        if not self:
            return qty
        self.ensure_one()
        if self.category_id.id != to_unit.category_id.id:
            if self._context.get('raise-exception', False):
                return qty
                #raise UserError(_('Conversion from Product UoM %s to Default UoM %s is not possible as they both belong to different Category!.') % (self.name, to_unit.name))
            else:
                return qty
        amount = qty / self.factor
        if to_unit:
            amount = amount * to_unit.factor
            if round:
                amount = tools.float_round(amount, precision_rounding=to_unit.rounding, rounding_method=rounding_method)
        return amount



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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'uom.uom' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'uom.uom'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        result = super(UomUom, self).create(vals)
        if vals.get('company_id'):
            company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
            result.sync_type = company_id.sync_type
        if result.trigger_create == False:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger create product uom")
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
            consol_active = record.company_id.sync_consol_product_uom
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/uom.uom"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/uom.uom"
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
                values['uom_type'] = str(record.uom_type)
                values['active'] = str(record.active)
                values['rounding'] = record.rounding
                values['factor_inv'] = record.factor_inv
                values['factor'] = record.factor
                values['trigger_create'] = True

                if record.category_id.id == False:
                    values['category_id'] = record.category_id.id
                else:
                    values['category_id'] = str(record.category_id.id)
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
                super(UomUom, self).write(data_update)



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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'uom.uom' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'uom.uom'
        log_file = log_dir + log_name + '.log'
        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day


        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        result = super(UomUom, self).write(vals)
        if self.env.context.get('writed'):
            return result
        self = self.with_context(writed=True)
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "write product uom")
        if self.company_id:
            self.sync_type = self.company_id.sync_type
        if self.trigger_write == True:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger write product uom")
            query = """
            UPDATE uom_uom set trigger_write = false
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
            consol_active = record.company_id.sync_consol_product_uom
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/uom.uom"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/uom.uom"
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
                values['uom_type'] = str(record.uom_type)
                values['active'] = str(record.active)
                values['rounding'] = record.rounding
                values['factor_inv'] = record.factor_inv
                values['factor'] = record.factor
                values['trigger_write'] = False

                if record.category_id.id == False:
                    values['category_id'] = record.category_id.id
                else:
                    values['category_id'] = str(record.category_id.id)
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
                super(UomUom, self).write(data_update)
    


    @api.onchange('sync_type', 'name','uom_type','active','rounding','factor_inv','factor','category_id')
    def onchange_trigger_write(self):
        self.trigger_write = True




    # @api.model
    # def _sync_uom_wipro(self, sync_type='1'):
    #     sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '!=',0)])}
    #     sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name),('sync_type', '=', sync_type)],limit=1)
    #     query = "SELECT a.UoMID 'sync_id', a.UOM 'name', 1 'category_id' from dbo.v_UOMS AS a "
    #     # % (str(sync_ids.keys())[1:-1] or 'NULL')#, sync_date or 'NULL')
    #     #WHERE UoMID NOT IN (%s) OR MODDATE > %s
    #     if sync_date:
    #         query += " where convert(varchar(10), a.MODDATE, 121) >= '{0}'".format(tools.datetime.strptime(sync_date.date,'%Y-%m-%d %H:%M:%S').date())
    #         print (query)
    #         sync_date.date = tools.datetime.now()
    #     else:
    #         self.env['sync.date'].sudo().create({
    #             'name':sync.getframe().f_code.co_name,
    #             'sync_type':sync_type
    #         })
    #     data = sync.get_data(sync.servers.get(sync_type), query)
    #     if not data:
    #         print ("No new data available")
    #         return
    #     fields_without_id = tuple(
    #         key for key in self._fields
    #         if key != 'id' and 'property' not in key and self._fields[key].
    #         required == True and self._fields[key].store == True)
    #     columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'active') if data else ()
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
    #     now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:S')
    #     for object in data:
    #         for value in default_values:
    #             object[value] = default_values[value]
    #         if int(object['sync_id']) in sync_ids:
    #             object['id'] = sync_ids[object['sync_id']]
    #         else:
    #             object['id'] = 'DEFAULT'
    #         object['sync_date'] = now
    #         object['sync_type'] = sync_type
    #         object['active'] = True
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
    #     query = "INSERT into uom_uom %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
    #     print (query.encode('utf8'))
    #     self.env.cr.execute(query)




    # @api.model
    # def get_view(self,view_id=None, view_type='form', **options):
    #     res = super(UomUom,self).get_view(view_id=view_id,view_type=view_type, **options)
    #     if view_type == 'form':
    #         res['arch'] = """
    #             <form string="Units of Measure" delete="0">
    #                 <sheet>
    #                     <group>
    #                         <group>
    #                             <field name="name" on_change="1" modifiers="{&quot;required&quot;: true}"/>
    #                             <field name="category_id" on_change="1" can_create="true" can_write="true" modifiers="{&quot;required&quot;: true}"/>
    #                             <field name="uom_type" on_change="1" modifiers="{&quot;required&quot;: true}"/>
    #                             <field name="factor" digits="[42,5]" attrs="{&quot;invisible&quot;:[(&quot;uom_type&quot;,&quot;!=&quot;,&quot;smaller&quot;)], &quot;readonly&quot;:[(&quot;uom_type&quot;,&quot;=&quot;,&quot;bigger&quot;)]}" on_change="1" modifiers="{&quot;invisible&quot;: [[&quot;uom_type&quot;, &quot;!=&quot;, &quot;smaller&quot;]], &quot;readonly&quot;: [[&quot;uom_type&quot;, &quot;=&quot;, &quot;bigger&quot;]], &quot;required&quot;: true}"/>
    #                             <field name="factor_inv" digits="[42,5]" attrs="{&quot;invisible&quot;:[(&quot;uom_type&quot;,&quot;!=&quot;,&quot;bigger&quot;)], &quot;readonly&quot;:[(&quot;uom_type&quot;,&quot;!=&quot;,&quot;bigger&quot;)]}" on_change="1" modifiers="{&quot;invisible&quot;: [[&quot;uom_type&quot;, &quot;!=&quot;, &quot;bigger&quot;]], &quot;readonly&quot;: [[&quot;uom_type&quot;, &quot;!=&quot;, &quot;bigger&quot;]], &quot;required&quot;: true}"/>
    #                             <p attrs="{&quot;invisible&quot;:[(&quot;uom_type&quot;,&quot;!=&quot;,&quot;smaller&quot;)]}" class="oe_grey" colspan="2" modifiers="{&quot;invisible&quot;: [[&quot;uom_type&quot;, &quot;!=&quot;, &quot;smaller&quot;]]}">
                            
    #                                     e.g: 1 * (reference unit) = ratio * (this unit)
                                    
    #                             </p>
    #                             <p attrs="{&quot;invisible&quot;:[(&quot;uom_type&quot;,&quot;!=&quot;,&quot;bigger&quot;)]}" class="oe_grey" colspan="2" modifiers="{&quot;invisible&quot;: [[&quot;uom_type&quot;, &quot;!=&quot;, &quot;bigger&quot;]]}">
                                    
    #                                             e.g: 1 * (this unit) = ratio * (reference unit)
                                            
    #                             </p>
    #                         </group>
    #                         <group>
    #                             <field name="active" on_change="1" modifiers="{}"/>
    #                             <field name="rounding" digits="[42, 5]" on_change="1" modifiers="{&quot;required&quot;: true}"/>
    #                             <field name="company_id" can_create="true" can_write="true" modifiers="{}"/>
    #                         </group>
    #                     </group>
    #                     <notebook>
    #                         <page string="Technical">
    #                             <group>
    #                                 <group>
    #                                     <field name="trigger_create" invisible="1" modifiers="{&quot;invisible&quot;: true}"/>
    #                                     <field name="trigger_write" invisible="1" modifiers="{&quot;invisible&quot;: true}"/>
    #                                     <field name="sync_type" readonly="1"/>
    #                                     <field name="sync_id" readonly="1"/>
    #                                     <field name="sync_id_api" readonly="1"/>
    #                                 </group>
    #                                 <group>
    #                                     <field name="sync_consol_id_main" readonly="1"/>
    #                                     <field name="sync_consol_id_unit" readonly="1"/>
    #                                     <field name="sync_consol_date" readonly="1"/>
    #                                 </group>
    #                             </group>
    #                         </page>
    #                     </notebook>
    #                 </sheet>
    #             </form>
    #         """
    #     elif view_type == 'tree':
    #         res['arch'] = """
    #             <tree string="Units of Measure" delete="0">
    #                 <field name="name" on_change="1" modifiers="{&quot;required&quot;: true}"/>
    #                 <field name="wipro_block" modifiers="{}"/>
    #                 <field name="sync_type" on_change="1" modifiers="{}"/>
    #                 <field name="trigger_create" invisible="1" modifiers="{&quot;tree_invisible&quot;: true}"/>
    #                 <field name="trigger_write" invisible="1" modifiers="{&quot;tree_invisible&quot;: true}"/>
    #                 <field name="category_id" on_change="1" can_create="true" can_write="true" modifiers="{&quot;required&quot;: true}"/>
    #                 <field name="uom_type" on_change="1" modifiers="{&quot;required&quot;: true}"/>
    #             </tree>
    #         """
    #     elif view_type == 'search':
    #         res['arch'] = """
    #             <search string="Search UoM..">
    #                 <filter name="sync_is_arcus" string="From Arcus" domain="[('sync_is_arcus','=', 1)]" help="From Arcus"/>
    #             </search>
    #         """
    #     from lxml import etree
    #     doc = etree.XML(res['arch'])
    #     View = self.env['ir.ui.view'].sudo()
    #     res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
    #     return res






class UomCategory(models.Model):
    _inherit = 'uom.category'

    sync_id = sync.id
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    sync_id_api = sync.id_api
    # name = fields.Char(string="UoM Name", translate=False)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(UomCategory,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Product UoM Categories">
                    <field name="name" modifiers="{'required': true}"/>
                    <field name="sync_type"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res




class ProductCategory(models.Model):
    _inherit = 'product.category'
    _rec_name = 'name'

    @api.model
    def _get_default_company(self):
        company_id = self.env.company.id
        return self.env.company.id

    parent_sync_id = fields.Float(string="Parent Category (Synchronization)")
    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")

    sync_is_arcus = sync.is_arcus
    sync_is_service = fields.Boolean(string="Is Service from Wipro", default=False)
    sync_is_surgery = fields.Boolean(string="Is Surgery from Wipro", default=False)
    sync_is_category = fields.Boolean(string="Is Category from Wipro", default=False)
    sync_is_specialist	 = fields.Boolean(string="Is Specialist", default=False)
    lob_los = fields.Selection([('LOB', 'LOB'), ('LOS', 'LOS')], string="LOB / LOS")
    code = fields.Char(string="Code")
    wipro_block = fields.Boolean(string="Wipro Block", default=False)
    active = fields.Boolean(string="Active", default=True)
    
    company_id = fields.Many2one('res.company', string="Company", default=_get_default_company)
    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")

    stock_input_id = fields.Many2one('account.account',string="Stock Input Stored",store=True,index=True)
    stock_output_id = fields.Many2one('account.account',string="Stock Output Stored",store=True,index=True)
    stock_valuation_id = fields.Many2one('account.account',string="Stock Valuation Stored",store=True,index=True)
    income_account_id = fields.Many2one('account.account',string="Income Account Stored",store=True,index=True)
    expense_account_id = fields.Many2one('account.account',string="Expense Account Stored",store=True,index=True)
    stock_journal_id = fields.Many2one('account.journal',string="Stock Journal Stored",store=True,index=True)
    property_account_accrual_id = fields.Many2one('account.account')
    child_ids = fields.One2many('product.category','parent_id', string="Childs")
    parent_left = fields.Integer('Left Parent', index=1)
    parent_right = fields.Integer('Right Parent', index=1)
    type = fields.Selection([('view', 'View'), ('normal', 'Normal')], string="Category Type", default='normal')
    product_count = fields.Integer(string="Product Count")

    # @api.multi
    # @api.depends('name')
    def name_get(self):
        def get_names(cat):
            """ Return the list [cat.name, cat.parent_id.name, ...] """
            res = []
            while cat:
                res.append(cat.name)
                cat = cat.parent_id
            return res

        return [(cat.id, " / ".join(reversed(get_names(cat)))) for cat in self]
    
    
    # @api.multi
    # def write(self,vals):
    #     record = super(ProductCategory, self).write(vals)
    #     if self.parent_id.id == self.id:
    #         raise exceptions.ValidationError(_('Please dont be stupid selecting self id to parent!'))

    # @api.model
    # def create(self,vals):
    #     record = super(ProductCategory, self).create(vals)
    #     if record.parent_id.id == record.id:
    #         raise exceptions.ValidationError(_('Please dont be stupid selecting self id to parent!'))

    def _compute_product_count(self):
        self.product_count = 0
        # read_group_res = self.env['product.template'].read_group([('categ_id', 'child_of', self.ids)], ['categ_id'], ['categ_id'])
        # group_data = dict((data['categ_id'][0], data['categ_id_count']) for data in read_group_res)
        # for categ in self:
        #     product_count = 0
        #     for sub_categ_id in categ.search([('id', 'child_of', categ.ids)]).ids:
        #         product_count += group_data.get(sub_categ_id, 0)
        #     categ.product_count = product_count
        
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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'product.category' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'product.category'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        
        result = super(ProductCategory, self).create(vals)
        if vals.get('company_id'):
            company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
            result.sync_type = company_id.sync_type
        if result.trigger_create == False and not result.sync_id_api:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger create product category")
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
            consol_active = record.company_id.sync_consol_product_category
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""

            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/product.category"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/product.category"
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
                values['name'] = record.name
                values['lob_los'] = record.lob_los
                values['type'] = record.type
                values['active'] = record.active
                values['property_cost_method'] = record.property_cost_method
                values['property_valuation'] = record.property_valuation
                values['trigger_create'] = True

                if record.parent_id.id == False:
                    values['parent_id'] = record.parent_id.id
                else:
                    values['parent_id'] = str(record.parent_id.id)
                if record.company_id.id == False:
                    values['company_id'] = record.company_id.id
                else:
                    values['company_id'] = str(record.company_id.id)
                if record.property_account_creditor_price_difference_categ.id == False:
                    values['property_account_creditor_price_difference_categ'] = record.property_account_creditor_price_difference_categ.id
                else:
                    values['property_account_creditor_price_difference_categ'] = str(record.property_account_creditor_price_difference_categ.id)
                if record.property_account_income_categ_id.id == False:
                    values['property_account_income_categ_id'] = record.property_account_income_categ_id.id
                else:
                    values['property_account_income_categ_id'] = str(record.property_account_income_categ_id.id)
                if record.property_account_expense_categ_id.id == False:
                    values['property_account_expense_categ_id'] = record.property_account_expense_categ_id.id
                else:
                    values['property_account_expense_categ_id'] = str(record.property_account_expense_categ_id.id)
                
                if record.property_account_accrual_id.id == False:
                    values['property_account_accrual_id'] = record.property_account_accrual_id.id
                else:
                    values['property_account_accrual_id'] = str(record.property_account_accrual_id.id)
                if record.property_stock_account_input_categ_id.id == False:
                    values['property_stock_account_input_categ_id'] = record.property_stock_account_input_categ_id.id
                else:
                    values['property_stock_account_input_categ_id'] = str(record.property_stock_account_input_categ_id.id)
                if record.property_stock_account_output_categ_id.id == False:
                    values['property_stock_account_output_categ_id'] = record.property_stock_account_output_categ_id.id
                else:
                    values['property_stock_account_output_categ_id'] = str(record.property_stock_account_output_categ_id.id)
                if record.property_stock_valuation_account_id.id == False:
                    values['property_stock_valuation_account_id'] = record.property_stock_valuation_account_id.id
                else:
                    values['property_stock_valuation_account_id'] = str(record.property_stock_valuation_account_id.id)
                if record.property_stock_journal.id == False:
                    values['property_stock_journal'] = record.property_stock_journal.id
                else:
                    values['property_stock_journal'] = str(record.property_stock_journal.id)

                if record.stock_input_id.id == False:
                    values['stock_input_id'] = record.stock_input_id.id
                else:
                    values['stock_input_id'] = str(record.stock_input_id.id)

                if record.stock_output_id.id == False:
                    values['stock_output_id'] = record.stock_output_id.id
                else:
                    values['stock_output_id'] = str(record.stock_output_id.id)

                if record.stock_valuation_id.id == False:
                    values['stock_valuation_id'] = record.stock_valuation_id.id
                else:
                    values['stock_valuation_id'] = str(record.stock_valuation_id.id)

                if record.income_account_id.id == False:
                    values['income_account_id'] = record.income_account_id.id
                else:
                    values['income_account_id'] = str(record.income_account_id.id)

                if record.expense_account_id.id == False:
                    values['expense_account_id'] = record.expense_account_id.id
                else:
                    values['expense_account_id'] = str(record.expense_account_id.id)

                if record.stock_journal_id.id == False:
                    values['stock_journal_id'] = record.stock_journal_id.id
                else:
                    values['stock_journal_id'] = str(record.stock_journal_id.id)

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
                super(ProductCategory, self).write(data_update)

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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'product.category' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'product.category'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        result = super(ProductCategory, self).write(vals)
        if self.env.context.get('writed'):
            return result
        self = self.with_context(writed=True)
        #####Chaelvin
        if self.company_id:
            self.sync_type = self.company_id.sync_type
        if self.trigger_write == True and not self.sync_id_api:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger write product category")
            query = """
            UPDATE product_category set trigger_write = false
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
            consol_active = record.company_id.sync_consol_product_category
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/product.category"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/product.category"
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
                values['lob_los'] = record.lob_los
                values['type'] = str(record.type)
                values['active'] = record.active
                values['property_cost_method'] = str(record.property_cost_method)
                values['property_valuation'] = str(record.property_valuation)
                values['trigger_write'] = False

                if record.parent_id.id == False:
                    values['parent_id'] = record.parent_id.id
                else:
                    values['parent_id'] = str(record.parent_id.id)
                if record.company_id.id == False:
                    values['company_id'] = record.company_id.id
                else:
                    values['company_id'] = str(record.company_id.id)
                if record.property_account_creditor_price_difference_categ.id == False:
                    values['property_account_creditor_price_difference_categ'] = record.property_account_creditor_price_difference_categ.id
                else:
                    values['property_account_creditor_price_difference_categ'] = str(record.property_account_creditor_price_difference_categ.id)
                if record.property_account_income_categ_id.id == False:
                    values['property_account_income_categ_id'] = record.property_account_income_categ_id.id
                else:
                    values['property_account_income_categ_id'] = str(record.property_account_income_categ_id.id)
                if record.property_account_expense_categ_id.id == False:
                    values['property_account_expense_categ_id'] = record.property_account_expense_categ_id.id
                else:
                    values['property_account_expense_categ_id'] = str(record.property_account_expense_categ_id.id)
                
                if record.property_account_accrual_id.id == False:
                    values['property_account_accrual_id'] = record.property_account_accrual_id.id
                else:
                    values['property_account_accrual_id'] = str(record.property_account_accrual_id.id)
                if record.property_stock_account_input_categ_id.id == False:
                    values['property_stock_account_input_categ_id'] = record.property_stock_account_input_categ_id.id
                else:
                    values['property_stock_account_input_categ_id'] = str(record.property_stock_account_input_categ_id.id)
                if record.property_stock_account_output_categ_id.id == False:
                    values['property_stock_account_output_categ_id'] = record.property_stock_account_output_categ_id.id
                else:
                    values['property_stock_account_output_categ_id'] = str(record.property_stock_account_output_categ_id.id)
                if record.property_stock_valuation_account_id.id == False:
                    values['property_stock_valuation_account_id'] = record.property_stock_valuation_account_id.id
                else:
                    values['property_stock_valuation_account_id'] = str(record.property_stock_valuation_account_id.id)
                if record.property_stock_journal.id == False:
                    values['property_stock_journal'] = record.property_stock_journal.id
                else:
                    values['property_stock_journal'] = str(record.property_stock_journal.id)

                if record.stock_input_id.id == False:
                    values['stock_input_id'] = record.stock_input_id.id
                else:
                    values['stock_input_id'] = str(record.stock_input_id.id)

                if record.stock_output_id.id == False:
                    values['stock_output_id'] = record.stock_output_id.id
                else:
                    values['stock_output_id'] = str(record.stock_output_id.id)

                if record.stock_valuation_id.id == False:
                    values['stock_valuation_id'] = record.stock_valuation_id.id
                else:
                    values['stock_valuation_id'] = str(record.stock_valuation_id.id)

                if record.income_account_id.id == False:
                    values['income_account_id'] = record.income_account_id.id
                else:
                    values['income_account_id'] = str(record.income_account_id.id)

                if record.expense_account_id.id == False:
                    values['expense_account_id'] = record.expense_account_id.id
                else:
                    values['expense_account_id'] = str(record.expense_account_id.id)

                if record.stock_journal_id.id == False:
                    values['stock_journal_id'] = record.stock_journal_id.id
                else:
                    values['stock_journal_id'] = str(record.stock_journal_id.id)
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
                super(ProductCategory, self).write(data_update)

    @api.onchange('sync_type', 'name','lob_los','type','active','property_cost_method','property_valuation','parent_id','company_id','property_account_creditor_price_difference_categ','property_account_income_categ_id','property_account_expense_categ_id','property_account_accrual_id','property_stock_account_input_categ_id','property_stock_account_output_categ_id','property_stock_valuation_account_id','property_stock_journal','stock_input_id','stock_output_id','stock_valuation_id','income_account_id','expense_account_id','stock_journal_id')
    def onchange_trigger_write(self):
        self.trigger_write = True


    @api.constrains('sync_id_api', 'sync_type')
    def sync_id_constrains(self):
        for rec in self:
            if rec.sync_id_api and not rec.sync_type:
                raise exceptions.ValidationError(_('Sorry, sync_type cannot be empty!'))

    # @api.model
    # def get_view(self,view_id=None, view_type='form', **options):
    #     res = super(ProductCategory,self).get_view(view_id=view_id,view_type=view_type, **options)
    #     if view_type == 'tree':
    #         res['arch'] = """
    #             <tree string="Product Category" delete="false">
    #                 <field name="display_name" />
    #                 <!--field name="name" /-->
    #                 <field name="parent_id" />
    #                 <field name="company_id" />
    #                 <field name="sync_type" />
    #                 <field name="stock_output_id" />
    #             </tree>
    #         """
    #     from lxml import etree
    #     doc = etree.XML(res['arch'])
    #     View = self.env['ir.ui.view'].sudo()
    #     res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
    #     return res


    @api.model
    def _update_account_stored(self):
        self.env.cr.execute("""
            UPDATE product_category as pc set stock_input_id = (select replace(value_reference, 'account.account,', '')::integer from ir_property where res_id = concat('product.category,', pc.id) 
            and company_id = pc.company_id and name = 'property_stock_account_input_categ_id' limit 1) where stock_input_id is null"""
                            )
        self.env.cr.execute("""
            UPDATE product_category as pc set stock_output_id = (select replace(value_reference, 'account.account,', '')::integer from ir_property where res_id = concat('product.category,', pc.id)
            and company_id = pc.company_id and name = 'property_stock_account_output_categ_id' limit 1) where stock_output_id is null"""
                            )
        self.env.cr.execute("""
            UPDATE product_category as pc set stock_valuation_id = (select replace(value_reference, 'account.account,', '')::integer from ir_property where res_id = concat('product.category,', pc.id)
            and company_id = pc.company_id and name = 'property_stock_valuation_account_id' limit 1) where stock_valuation_id is null"""
                            )
        self.env.cr.execute("""
            UPDATE product_category as pc set income_account_id = (select replace(value_reference, 'account.account,', '')::integer from ir_property where res_id = concat('product.category,', pc.id)
            and company_id = pc.company_id and name = 'property_account_income_categ_id' limit 1) where income_account_id is null"""
                            )
        self.env.cr.execute("""
            UPDATE product_category as pc set expense_account_id = (select replace(value_reference, 'account.account,', '')::integer from ir_property where res_id = concat('product.category,', pc.id)
            and company_id = pc.company_id and name = 'property_account_expense_categ_id' limit 1) where expense_account_id is null"""
                            )
        self.env.cr.execute("""
            UPDATE product_category as pc set stock_journal_id = (select replace(value_reference, 'account.journal,', '')::integer from ir_property where res_id = concat('product.category,', pc.id)
            and company_id = pc.company_id and name = 'property_stock_journal' limit 1) where stock_journal_id is null"""
                            )
        self.env.cr.execute("""
            UPDATE product_category as pc set stock_input_id = (select replace(value_reference, 'account.account,', '')::integer from ir_property where res_id is null
            and company_id = pc.company_id and name = 'property_stock_account_input_categ_id' limit 1) where stock_input_id is null"""
                            )
        self.env.cr.execute("""
            UPDATE product_category as pc set stock_output_id = (select replace(value_reference, 'account.account,', '')::integer from ir_property where res_id is null
            and company_id = pc.company_id and name = 'property_stock_account_output_categ_id' limit 1) where stock_output_id is null"""
                            )
        self.env.cr.execute("""
            UPDATE product_category as pc set stock_valuation_id = (select replace(value_reference, 'account.account,', '')::integer from ir_property where res_id is null
            and company_id = pc.company_id and name = 'property_stock_valuation_account_id' limit 1) where stock_valuation_id is null"""
                            )
        self.env.cr.execute("""
            UPDATE product_category as pc set income_account_id = (select replace(value_reference, 'account.account,', '')::integer from ir_property where res_id is null
            and company_id = pc.company_id and name = 'property_account_income_categ_id' limit 1) where income_account_id is null"""
                            )
        self.env.cr.execute("""
            UPDATE product_category as pc set expense_account_id = (select replace(value_reference, 'account.account,', '')::integer from ir_property where res_id is null
            and company_id = pc.company_id and name = 'property_account_expense_categ_id' limit 1) where expense_account_id is null"""
                            )
        self.env.cr.execute("""
            UPDATE product_category as pc set stock_journal_id = (select replace(value_reference, 'account.journal,', '')::integer from ir_property where res_id is null
            and company_id = pc.company_id and name = 'property_stock_journal' limit 1) where stock_journal_id is null"""
                            )



    # @api.model
    # def _sync_category_wipro(self, sync_type='1'):
    #     sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '!=', False), ('sync_is_service', '=',False)])}
    #     sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name), ('sync_type', '=', sync_type)], limit=1)
    #     query = """
    #         SELECT 
    #             a.sync_id, 
    #             a.name, a.parent_sync_id, 
    #             a.MODDATE, a.active,
    #             cast(a.sync_is_service as bit) sync_is_service,
    #             cast(a.sync_is_surgery as bit) sync_is_surgery,
    #             cast(a.sync_is_category as bit) sync_is_category
    #         FROM dbo.VRP_OdooItemCategories AS a
    #     """
    #     if sync_date:
    #         query += " where convert(varchar(10), a.MODDATE, 121) >=  '{0}'".format(tools.datetime.strptime(sync_date.date, '%Y-%m-%d %H:%M:%S').date())
    #         print (query)
    #         sync_date.date = tools.datetime.now()
    #     else:
    #         self.env['sync.date'].sudo().create({
    #             'name':sync.getframe().f_code.co_name,
    #             'sync_type':sync_type
    #         })
    #     data = sync.get_data(sync.servers.get(sync_type), query)
    #     if not data:
    #         print ("No new data available")
    #         return

    #     now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:S')
    #     for object in data:
    #         object['sync_date'] = now
    #         object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)],limit=1).id
    #         if int(object['sync_id']) in sync_ids:
    #             self.sudo().browse(sync_ids[object['sync_id']]).write(object)
    #         else:
    #             self.sudo().create(object)
    #     for record in self.sudo().search([('parent_id', '=', False),('parent_sync_id', '!=', 0)]):
    #         record.parent_id = self.sudo().search([('sync_type', '=', record.sync_type),('sync_is_service', '=', record.sync_is_service),('sync_is_surgery', '=', record.sync_is_surgery),('sync_is_category', '=', record.sync_is_category), ('sync_is_surgery', '=', record.sync_is_surgery),('sync_id', '=', record.parent_sync_id)],limit=1)




    # @api.model
    # def _sync_category_service_wipro(self, sync_type='1'):
    #     sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '!=', 0), ('sync_is_service', '=',True)])}
    #     sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name),('sync_type', '=', sync_type)],limit=1)
    #     query = """
    #         SELECT 
    #             a.sync_id, 
    #             a.name, 
    #             a.parent_sync_id,
    #             a.MODDATE,
    #             cast('True' as bit) sync_is_service,
    #             cast('False' as bit) sync_is_category,
    #             cast('False' as bit) sync_is_surgery
    #         FROM dbo.VRP_OdooServices AS a 
    #     """
    #     if sync_date:
    #         query += " where convert(varchar(10), a.MODDATE, 121) >=  '{0}'".format(tools.datetime.strptime(sync_date.date,'%Y-%m-%d %H:%M:%S').date())
    #         print (query)
    #         sync_date.date = tools.datetime.now()
    #     else:
    #         self.env['sync.date'].sudo().create({
    #             'name':sync.getframe().f_code.co_name,
    #             'sync_type':sync_type
    #         })
    #     data = sync.get_data(sync.servers.get(sync_type), query)
    #     if not data:
    #         print ("No new data available")
    #         return

    #     now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:S')
    #     for object in data:
    #         object['sync_date'] = now
    #         object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)],limit=1).id
    #         # object['sync_is_service'] = True
    #         if int(object['sync_id']) in sync_ids:
    #             self.sudo().browse(sync_ids[object['sync_id']]).write(object)
    #         else:
    #             self.sudo().create(object)
    #     for record in self.sudo().search([('parent_id', '=', False),('parent_sync_id', '!=', 0)]):
    #         record.parent_id = self.sudo().search([('sync_type', '=', record.sync_type),('sync_is_service', '=', True),('sync_id', '=', record.parent_sync_id)],limit=1)




    # 2921.10.16 block dependency account from parent category
    # @api.multi
    def _update_account(self):
        print ("Do something")
        # categ = self.env['product.category'].search([('parent_id', '!=', False)])
        # for c in categ:
        #     c.property_account_income_categ_id = c.parent_id.property_account_income_categ_id
        #     c.property_account_expense_categ_id = c.parent_id.property_account_expense_categ_id
        #     c.property_stock_account_input_categ_id = c.parent_id.property_stock_account_input_categ_id
        #     c.property_stock_account_output_categ_id = c.parent_id.property_stock_account_output_categ_id
        #     c.property_stock_valuation_account_id = c.parent_id.property_stock_valuation_account_id






class ServiceGroup(models.Model):
    _name = 'service.group'

    @api.model
    def _get_default_company(self):
        company_id = self.env.company.id
        return self.env.company.id

    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")

    code = fields.Char(string="Code")
    name = fields.Char(string="Group Name")
    active = fields.Boolean(string="Active", default=True)
    
    company_id = fields.Many2one('res.company', string="Company", default=_get_default_company)
    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ServiceGroup,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Service Group" delete="false">
                    <sheet>
                        <div class="oe_button_box" name="button_box">
                            <button name="toggle_active" type="object" class="oe_stat_button" icon="fa-archive">
                                <field name="active" widget="boolean_button" options="{&quot;terminology&quot;: &quot;active&quot;}"/>
                            </button>
                        </div>
                        <group>
                            <group>
                                <field name="code"/>
                                <field name="name"/>
                            </group>
                            <group>
                                <field name="company_id"/>
                                <field name="sync_type"/>
                            </group>
                        </group>
                        <notebook>
                            <page string="Technical">
                                <group>
                                    <group>
                                        <field name="trigger_create" invisible="1"/>
                                        <field name="trigger_write" invisible="1"/>
                                        <field name="sync_date"/>
                                        <field name="sync_id"/>
                                    </group>
                                    <group>
                                        <field name="sync_id_api"/>
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
                <tree string="Service Group" decoration-muted="(not active)" delete="false">
                    <field name="code"/>
                    <field name="name"/>
                    <field name="company_id"/>
                    <field name="sync_type"/>
                    <field name="active"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Service Group..">
                    <filter string="Active" domain="[('active','=', True)]" help="Active"/>
                    <filter string="Non Active" domain="[('active','=', False)]" help="Non Active"/>
                    <separator/>
                    <field name="code"/>
                    <field name="name"/>
                    <field name="company_id"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res




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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'service.group' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'service.group'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        result = super(ServiceGroup, self).create(vals)
        if vals.get('company_id'):
            company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
            result.sync_type = company_id.sync_type
        if result.trigger_create == False and not result.sync_id_api:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger create service_group")
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
            consol_active = record.company_id.sync_consol_service_group
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""

            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/create/service.group"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/create/service.group"
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
                values['name'] = str(record.name)
                values['code'] = str(record.code)
                values['active'] = record.active
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
                super(ServiceGroup, self).write(data_update)

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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'service.group' + '/'
        log_name = log_date + '_' + 'write' + '_' + 'service.group'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        open(log_file, 'a').write(message_log)
        result = super(ServiceGroup, self).write(vals)
        if self.env.context.get('writed'):
            return result
        self = self.with_context(writed=True)
        #####Chaelvin
        if self.company_id:
            self.sync_type = self.company_id.sync_type
        if self.trigger_write == True and not self.sync_id_api:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger write service group")
            query = """
            UPDATE service_group set trigger_write = false
            WHERE id = {self_id}""".format(self_id = self.id)
            self.env.cr.execute(query)
            self.send_api_consol_write_company()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " + str(result.id)

        open(log_file, 'a').write(message_log)
        return result
    
    # @api.multi
    def send_api_consol_write_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            consol_active = record.company_id.sync_consol_service_group
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/write/service.group"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/write/service.group"
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
                values['code'] = str(record.code)
                values['active'] = record.active
                values['trigger_write'] = False

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
                        # raise exceptions.ValidationError(_('Data Gagal Diedit'))
                        raise exceptions.ValidationError(_(json_resp['message']))


                data_update = {
                    consol_id_to : response_id,
                    # 'sync_consol_response': json_resp,
                    # 'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    # 'sync_consol_sent' : data_sent
                }
                super(ServiceGroup, self).write(data_update)


    @api.onchange('sync_type', 'name','active','code','company_id')
    def onchange_trigger_write(self):
        self.trigger_write = True


    @api.constrains('sync_id_api', 'sync_type')
    def sync_id_constrains(self):
        for rec in self:
            if rec.sync_id_api and not rec.sync_type:
                raise exceptions.ValidationError(_('Sorry, sync_type cannot be empty!'))







class ProductPriceHistory(models.Model):
    """ Keep track of the ``product.template`` standard prices as they are changed. """
    _name = 'product.price.history'
    _rec_name = 'datetime'
    _order = 'datetime desc'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    
    def _get_default_company_id(self):
        return self._context.get('force_company', self.env.company.id)

    company_id = fields.Many2one('res.company', string='Company', default=_get_default_company_id, required=True)
    product_id = fields.Many2one('product.product', 'Product', ondelete='cascade', required=True)
    datetime = fields.Datetime('Date', default=fields.Datetime.now)
    cost = fields.Float('Cost', digits=dp.get_precision('Product Price'))
    product_tmpl_id = fields.Many2one('product.template', string="Product Template")




class ProductRack(models.Model):
    _name = 'product.rack'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    
    location_id = fields.Many2one("stock.location", string="Location")
    rack_id = fields.Many2one("master.rack", string="Rack")
    shelf_id = fields.Many2one("master.shelf", string="Shelf")
    product_tmpl_id = fields.Many2one("product.template", String="Produk")


class Substore(models.Model):
    _name = 'product.substore'

    sync_id = sync.id
    sync_date = sync.date
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    name = fields.Char(string="Name")
    product_template_ids = fields.Many2many('product.template', string="Product")