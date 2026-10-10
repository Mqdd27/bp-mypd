import odoo
import re
import requests
import json
try:
    import ujson as JSON
except:
    import json as JSON
from threading import Thread
from odoo import models, fields, api, tools, exceptions
from io import StringIO
import sys
from . import sync


class HospitalPatientType(models.Model):
    _name = 'hospital.patient.type'

    sync_type = sync.type
    sync_id = sync.id
    sync_date = sync.date
    sync_id_api = sync.id_api
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date



class HospitalBedType(models.Model):
    _name = 'hospital.bed.type'

    sync_type = sync.type
    sync_id = sync.id
    sync_date = sync.date
    sync_id_api = sync.id_api
    sync_is_arcus = sync.is_arcus
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    def _get_company(self):
         return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=True, default=_get_company)
    code = fields.Char(string="Code")
    name = fields.Char(string="Bed Type")
    patient_type = fields.Selection([('1', 'OP'), ('2', 'IP'),('3', 'Emergency'), ('4', 'Daycare'),('5', 'MCU/Pharmacy Issues Only(FO)'), ('6', 'Pharmacy (Direct)'),('0', 'Both')],string='Patient Type',index=True)
    wipro_block = fields.Boolean(string="Wipro Block", default=False)
    active = fields.Boolean(string="Active", default=True)

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(HospitalBedType,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Hospital BedType" delete="false">
                  <sheet>
                    <group string="Information">
                        <group>
                            <field name="company_id"/>
                            <field name="code"/>
                        </group>
                        <group>
                            <field name="name"/>
                            <field name="wipro_block"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Technical">
                            <group>
                                <group>
                                    <field name="sync_type" readonly="1"/>
                                    <field name="sync_date" readonly="1"/>
                                    <field name="sync_id" readonly="1"/>
                                </group>
                                <group>
                                    <field name="sync_id_api" readonly="1"/>
                                    <field name="sync_consol_id_main" readonly="1"/>
                                    <field name="sync_consol_id_unit" readonly="1"/>
                                </group>
                            </group>
                        </page>
                    </notebook>
                  </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Hospital BedType" delete="false">
                    <field name="code"/>
                    <field name="name"/>
                    <field name="wipro_block"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Bed Type">
                    <filter name="sync_is_arcus" string="From Arcus" domain="[('sync_is_arcus','=', 1)]" help="From Arcus"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


    @api.model
    def _sync_hospital_bed_type(self, sync_type='1'):
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '!=',0)])}
        sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name),('sync_type', '=', sync_type)],limit=1)
        query = """
            SELECT a.sync_id,
                a.code, a.name, a.wipro_block
            from dbo.VRP_OdooHospitalBedType a
        """
        data = sync.get_data(sync.servers.get(sync_type), query)
        if not data:
            print ("No new data available")
            return
        fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and self._fields[key].required == True)
        columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
        fields_without_id += columns
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
        for object in data:
            for value in default_values:
                object[value] = default_values[value]
            if int(object['sync_id']) in sync_ids:
                object['id'] = sync_ids[object['sync_id']]
            else:
                object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'] = sync_type
            object['company_id'] = self.env['res.company'].search([('sync_type', '=', sync_type)],limit=1).id
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
        query = "INSERT into hospital_bed_type %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)



class HospitalTariff(models.Model):
    _name = 'hospital.tariff'

    sync_type = sync.type
    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_is_arcus = sync.is_arcus
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    def _get_company(self):
         return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=True, default=_get_company)
    code = fields.Char(string="Code")
    name = fields.Char(string="Tariff Name")
    reference = fields.Char(string="Reference")
    wipro_block = fields.Boolean(string="Wipro Block", default=False)
    payor_id = fields.Many2one('res.partner', string="Payor Name")
    is_tariff = fields.Boolean(string="Is Tariff")
    active = fields.Boolean(string="Active", default=False)
    
    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(HospitalTariff,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Hospital Tariff Name" delete="false">
                  <sheet>
                    <group string="Information">
                        <group>
                            <field name="company_id"/>
                            <field name="code"/>
                        </group>
                        <group>
                            <field name="name"/>
                            <field name="wipro_block"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Technical">
                            <group>
                                <group>
                                    <field name="sync_type" readonly="1"/>
                                    <field name="sync_date" readonly="1"/>
                                    <field name="sync_id" readonly="1"/>
                                </group>
                                <group>
                                    <field name="sync_id_api" readonly="1"/>
                                    <field name="sync_consol_id_main" readonly="1"/>
                                    <field name="sync_consol_id_unit" readonly="1"/>
                                </group>
                            </group>
                        </page>
                    </notebook>
                  </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Hospital Tariff" delete="false">
                    <field name="code"/>
                    <field name="name"/>
                    <field name="wipro_block"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Tarif">
                    <filter name="sync_is_arcus" string="From Arcus" domain="[('sync_is_arcus','=', 1)]" help="From Arcus"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


    @api.model
    def _sync_hospital_tariff(self, sync_type='1'):
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '!=',False)])}
        sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name),('sync_type', '=', sync_type)],limit=1)
        query = """
            SELECT a.sync_id,
                a.code, a.name, a.wipro_block
            from dbo.VRP_OdooHospitalTariff a
        """
        data = sync.get_data(sync.servers.get(sync_type), query)
        if not data:
            print ("No new data available")
            return
        fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and self._fields[key].required == True)
        columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
        fields_without_id += columns
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
        for object in data:
            for value in default_values:
                object[value] = default_values[value]
            if int(object['sync_id']) in sync_ids:
                object['id'] = sync_ids[object['sync_id']]
            else:
                object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'] = sync_type
            object['company_id'] = self.env['res.company'].search([('sync_type', '=', sync_type)],limit=1).id
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
        query = "INSERT into hospital_tariff %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)



class HospitalGrade(models.Model):
    _name = 'hospital.grade'

    sync_type = sync.type
    sync_id = sync.id
    sync_id_api = sync.id_api
    sync_date = sync.date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    def _get_company(self):
         return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=True, default=_get_company)
    tariff_id = fields.Many2one('hospital.tariff',string="Tariff Name")
    code = fields.Char(string="Code")
    name = fields.Char(string="Grade Name")
    wipro_block = fields.Boolean(string="Wipro Block", default=False)

    # @api.multi
    def name_get(self):
        res = []
        for record in self:
            if record.company_id and record.company_id.company_code:
                res.append((record.id, record.company_id.company_code + ' / ' + record.name))
            else:
                res.append((record.id, record.name))
        return res

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(HospitalGrade,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Hospital Grade Name" delete="false">
                  <sheet>
                    <group string="Information">
                        <group>
                            <field name="company_id"/>
                            <field name="tariff_id"/>
                            <field name="code"/>
                        </group>
                        <group>
                            <field name="name"/>
                            <field name="wipro_block"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Technical">
                            <group>
                                <group>
                                    <field name="sync_type" readonly="1"/>
                                    <field name="sync_date" readonly="1"/>
                                    <field name="sync_id" readonly="1"/>
                                </group>
                                <group>
                                    <field name="sync_id_api" readonly="1"/>
                                    <field name="sync_consol_id_main" readonly="1"/>
                                    <field name="sync_consol_id_unit" readonly="1"/>
                                </group>
                            </group>
                        </page>
                    </notebook>
                  </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Hospital Grade" delete="false">
                    <field name="code"/>
                    <field name="name"/>
                    <field name="tariff_id"/>
                    <field name="wipro_block"/>
                    <field name="sync_type"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    @api.model
    def _sync_hospital_grade(self, sync_type='1'):
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '!=',0)])}
        sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name),('sync_type', '=', sync_type)],limit=1)
        query = """
            SELECT a.sync_id, a.tariff_id,
                a.code, a.name, a.wipro_block
            from dbo.VRP_OdooHospitalGrade a
        """
        data = sync.get_data(sync.servers.get(sync_type), query)
        if not data:
            print ("No new data available")
            return
        fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and self._fields[key].required == True)
        columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
        fields_without_id += columns
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
        for object in data:
            for value in default_values:
                object[value] = default_values[value]
            if int(object['sync_id']) in sync_ids:
                object['id'] = sync_ids[object['sync_id']]
            else:
                object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'] = sync_type
            object['company_id'] = self.env['res.company'].search([('sync_type', '=', sync_type)],limit=1).id
            object['tariff_id'] = self.env['hospital.tariff'].search([('sync_type', '=', sync_type),('sync_id', '=', object['tariff_id'])],limit=1).id or None
            
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
        query = "INSERT into hospital_grade %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)



class HospitalDiscountType(models.Model):
    _name = 'hospital.discount.type'

    sync_type = sync.type
    sync_id = sync.id
    sync_date = sync.date
    sync_id_api = sync.id_api
    sync_is_arcus = sync.is_arcus
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    def _get_company(self):
         return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=True, default=_get_company)
    code = fields.Char(string="Code")
    name = fields.Char(string="Discount Name")
    patient_type = fields.Selection([('1', 'OP'), ('2', 'IP'), ('3', 'Emergency'), ('4', 'Daycare'), ('5', 'MCU'), ('6', 'Pharmacy'), ('0', 'Both')], string='Patient Type', readonly=True, index=True)
    wipro_block = fields.Boolean(string="Wipro Block", default=False)
    active = fields.Boolean(string="Active", default=False)
    journal_id = fields.Many2one('account.journal',string="Account Journal")
    account_id = fields.Many2one('account.account',string="Account Account")

    # @api.multi
    def name_get(self):
        res = []
        for record in self:
            if record.company_id and record.company_id.company_code:
                res.append((record.id, record.company_id.company_code + ' / ' + record.name))
            else:
                res.append((record.id, record.name))
        return res

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(HospitalDiscountType,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Hospital Discount Type" delete="false">
                  <sheet>
                    <group string="Information">
                        <group>
                            <field name="company_id"/>
                            <field name="code"/>
                        </group>
                        <group>
                            <field name="name"/>
                            <field name="wipro_block"/>
                            <field name="account_id" domain="[('company_id','=',company_id), ('parent','=',False), ('deprecated','=',False)]"/>
                            <field name="journal_id" domain="[('company_id','=',company_id)]"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Technical">
                            <group>
                                <group>
                                    <field name="sync_type" readonly="1"/>
                                    <field name="sync_date" readonly="1"/>
                                    <field name="sync_id" readonly="1"/>
                                </group>
                                <group>
                                    <field name="sync_id_api" readonly="1"/>
                                    <field name="sync_consol_id_main" readonly="1"/>
                                    <field name="sync_consol_id_unit" readonly="1"/>
                                </group>
                            </group>
                        </page>
                    </notebook>
                  </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Hospital Discount Type" delete="false">
                    <field name="code"/>
                    <field name="name"/>
                    <field name="wipro_block"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Discount Type">
                    <filter name="sync_is_arcus" string="From Arcus" domain="[('sync_is_arcus','=', 1)]" help="From Arcus"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


    @api.model
    def _sync_hospital_discount_type(self, sync_type='1'):
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '!=',0)])}
        sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name),('sync_type', '=', sync_type)],limit=1)
        query = """
            SELECT a.sync_id,
                a.code, a.name, a.patient_type, 
                a.wipro_block
            from dbo.VRP_OdooHospitalDiscountType a
        """
        data = sync.get_data(sync.servers.get(sync_type), query)
        if not data:
            print ("No new data available")
            return
        fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and self._fields[key].required == True)
        columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
        fields_without_id += columns
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
        for object in data:
            for value in default_values:
                object[value] = default_values[value]
            if int(object['sync_id']) in sync_ids:
                object['id'] = sync_ids[object['sync_id']]
            else:
                object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'] = sync_type
            object['company_id'] = self.env['res.company'].search([('sync_type', '=', sync_type)],limit=1).id
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
        query = "INSERT into hospital_discount_type %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)



class HospitalBedName(models.Model):
    _name = 'hospital.bed.name'

    sync_type = sync.type
    sync_id = sync.id
    sync_date = sync.date
    sync_id_api = sync.id_api
    sync_is_arcus = sync.is_arcus
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    def _get_company(self):
         return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=True, default=_get_company)
    code = fields.Char(string="Code")
    name = fields.Char(string="Bed Name")
    room_id = fields.Many2one('hospital.room.name', string='Room Name', index=True)
    ward_id = fields.Many2one('hr.department', string='Ward Name', index=True)
    wipro_block = fields.Boolean(string="Wipro Block", default=False)
    active = fields.Boolean(string="Active", default=False)

    # @api.multi
    def name_get(self):
        res = []
        for record in self:
            if record.company_id and record.company_id.company_code:
                res.append((str(record.id), str(record.company_id.company_code) + ' / ' + str(record.name)))
            else:
                res.append((record.id, record.name))
        return res

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(HospitalBedName,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Hospital BedName" delete="false">
                  <sheet>
                    <group string="Information">
                        <group>
                            <field name="code"/>
                            <field name="name"/>
                            <field name="room_id"/>
                        </group>
                        <group>
                            <field name="company_id"/>
                            <field name="ward_id"/>
                            <field name="wipro_block"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Technical">
                            <group>
                                <group>
                                    <field name="sync_type" readonly="1"/>
                                    <field name="sync_date" readonly="1"/>
                                    <field name="sync_id" readonly="1"/>
                                </group>
                                <group>
                                    <field name="sync_id_api" readonly="1"/>
                                    <field name="sync_consol_id_main" readonly="1"/>
                                    <field name="sync_consol_id_unit" readonly="1"/>
                                </group>
                            </group>
                        </page>
                    </notebook>
                  </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Hospital BedName" delete="false">
                    <field name="code"/>
                    <field name="name"/>
                    <field name="room_id"/>
                    <field name="ward_id"/>
                    <field name="wipro_block"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Search Bed">
                    <filter name="sync_is_arcus" string="From Arcus" domain="[('sync_is_arcus','=', 1)]" help="From Arcus"/>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    
    @api.model
    def _sync_hospital_bed_name(self, sync_type='1'):
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '!=',0)])}
        sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name),('sync_type', '=', sync_type)],limit=1)
        query = """
            SELECT a.sync_id,
                a.code, a.name, a.room_id, a.ward_id, a.wipro_block
            from dbo.VRP_OdooHospitalBedName a
        """
        data = sync.get_data(sync.servers.get(sync_type), query)
        if not data:
            print ("No new data available")
            return
        fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and self._fields[key].required == True)
        columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
        fields_without_id += columns
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
        for object in data:
            for value in default_values:
                object[value] = default_values[value]
            if int(object['sync_id']) in sync_ids:
                object['id'] = sync_ids[object['sync_id']]
            else:
                object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'] = sync_type
            object['ward_id'] = self.env['hr.department'].search([('sync_id', '=', object['ward_id']), ('sync_type', '=', sync_type)], limit=1).id or None
            object['room_id'] = self.env['hospital.room.name'].search([('sync_id', '=', object['room_id']), ('sync_type', '=', sync_type)], limit=1).id or None
            object['company_id'] = self.env['res.company'].search([('sync_type', '=', sync_type)],limit=1).id
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
        query = "INSERT into hospital_bed_name %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)



class HospitalRoomName(models.Model):
    _name = 'hospital.room.name'

    sync_type = sync.type
    sync_id = sync.id
    sync_date = sync.date
    sync_id_api = sync.id_api
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    def _get_company(self):
         return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=True, default=_get_company)
    code = fields.Char(string="Code")
    name = fields.Char(string="Room Name")
    bed_type_id = fields.Many2one('hospital.bed.type', string='Bed Type Room', index=True)
    ward_id = fields.Many2one('hr.department', string='Ward Name', index=True)
    wipro_block = fields.Boolean(string="Wipro Block", default=False)
    active = fields.Boolean(string="Active", default=False)

    # @api.multi
    def name_get(self):
        res = []
        for record in self:
            if record.company_id and record.company_id.company_code:
                res.append((record.id, record.company_id.company_code + ' / ' + record.name))
            else:
                res.append((record.id, record.name))
        return res

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(HospitalRoomName,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
                <form string="Hospital RoomName" delete="false">
                  <sheet>
                    <group string="Information">
                        <group>
                            <field name="company_id"/>
                            <field name="code"/>
                            <field name="name"/>
                        </group>
                        <group>
                            <field name="bed_type_id"/>
                            <field name="ward_id"/>
                            <field name="wipro_block"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Technical">
                            <group>
                                <group>
                                    <field name="sync_type" readonly="1"/>
                                    <field name="sync_date" readonly="1"/>
                                    <field name="sync_id" readonly="1"/>
                                </group>
                                <group>
                                    <field name="sync_id_api" readonly="1"/>
                                    <field name="sync_consol_id_main" readonly="1"/>
                                    <field name="sync_consol_id_unit" readonly="1"/>
                                </group>
                            </group>
                        </page>
                    </notebook>
                  </sheet>
                </form>
            """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Hospital RoomName" delete="false">
                    <field name="code"/>
                    <field name="name"/>
                    <field name="ward_id"/>
                    <field name="wipro_block"/>
                    <field name="sync_type"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


    @api.model
    def _sync_hospital_room_name(self, sync_type='1'):
        sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=',sync_type), ('sync_id', '!=',0)])}
        sync_date = self.sudo().env['sync.date'].search([('name', '=', sync.getframe().f_code.co_name),('sync_type', '=', sync_type)],limit=1)
        query = """
            SELECT a.sync_id,
                a.code, a.name, a.ward_id, a.wipro_block
            from dbo.VRP_OdooHospitalRoomName a
        """
        data = sync.get_data(sync.servers.get(sync_type), query)
        if not data:
            print ("No new data available")
            return
        fields_without_id = tuple(key for key in self._fields if key != 'id' and 'property' not in key and self._fields[key].required == True)
        columns = tuple(key for key in data[0].keys() if key in self._fields and key not in fields_without_id) + ('sync_date', 'sync_type') if data else ()
        fields_without_id += columns
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
        for object in data:
            for value in default_values:
                object[value] = default_values[value]
            if int(object['sync_id']) in sync_ids:
                object['id'] = sync_ids[object['sync_id']]
            else:
                object['id'] = 'DEFAULT'
            object['sync_date'] = now
            object['sync_type'] = sync_type
            object['ward_id'] = self.env['hr.department'].search([('sync_id', '=', object['ward_id']), ('sync_type', '=', sync_type)], limit=1).id or None
            object['company_id'] = self.env['res.company'].search([('sync_type', '=', sync_type)],limit=1).id
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
        query = "INSERT into hospital_room_name %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
        print (query.encode('utf8'))
        self.env.cr.execute(query)



# class ConsolAccountAccountAccountTag(models.Model):
#     _inherit = 'account.account.account.tag'

#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountAccountFinancialReport(models.Model):
#     _inherit = 'account.account.financial.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountAccountAccountFinancialReportType(models.Model):
#     _inherit = 'account.account.financial.report.type'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountAccountTag(models.Model):
#     _inherit = 'account.account.tag'

#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountAccountTemplate(models.Model):
#     _inherit = 'account.account.template'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountAccountTemplateAccountTag(models.Model):
#     _inherit = 'account.account.template.account.tag'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountAccountType(models.Model):
#     _inherit = 'account.account.type'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountAgedTrialBalance(models.Model):
#     _inherit = 'account.aged.trial.balance'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountAnalyticLine(models.Model):
#     _inherit = 'account.analytic.line'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountAnalyticTag(models.Model):
#     _inherit = 'account.analytic.tag'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountBalance(models.Model):
#     _inherit = 'account.balance'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountBalanceReport(models.Model):
#     _inherit = 'account.balance.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountBankStatement(models.Model):
#     _inherit = 'account.bank.statement'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountBankStatementCashbox(models.Model):
#     _inherit = 'account.bank.statement.cashbox'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountBankStatementClosebalance(models.Model):
#     _inherit = 'account.bank.statement.closebalance'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountCashboxLine(models.Model):
#     _inherit = 'account.cashbox.line'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountChartTemplate(models.Model):
#     _inherit = 'account.chart.template'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountCommonAccountReport(models.Model):
#     _inherit = 'account.common.account.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountCommonJournalReport(models.Model):
#     _inherit = 'account.common.journal.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountCommonPartnerReport(models.Model):
#     _inherit = 'account.common.partner.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountCommonReport(models.Model):
#     _inherit = 'account.common.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountConfigSettings(models.Model):
#     _inherit = 'account.config.settings'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountFinancialReport(models.Model):
#     _inherit = 'account.financial.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountFiscalPosition(models.Model):
#     _inherit = 'account.fiscal.position'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountFiscalPositionAccount(models.Model):
#     _inherit = 'account.fiscal.position.account'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountFiscalPositionAccountTemplate(models.Model):
#     _inherit = 'account.fiscal.position.account.template'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountFiscalPositionTax(models.Model):
#     _inherit = 'account.fiscal.position.tax'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountFiscalPositionTaxTemplate(models.Model):
#     _inherit = 'account.fiscal.position.tax.template'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountFiscalPositionTemplate(models.Model):
#     _inherit = 'account.fiscal.position.template'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountFullReconcile(models.Model):
#     _inherit = 'account.full.reconcile'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountInvoiceCancel(models.Model):
#     _inherit = 'account.invoice.cancel'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountInvoiceConfirm(models.Model):
#     _inherit = 'account.invoice.confirm'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountInvoiceLineTax(models.Model):
#     _inherit = 'account.invoice.line.tax'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountInvoiceRefund(models.Model):
#     _inherit = 'account.invoice.refund'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountInvoiceReport(models.Model):
#     _inherit = 'account.invoice.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountInvoicesTax(models.Model):
#     _inherit = 'account.invoice.tax'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountMoveLineReconcile(models.Model):
#     _inherit = 'account.move.line.reconcile'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountMoveLineReconcileWriteoff(models.Model):
#     _inherit = 'account.move.line.reconcile.writeoff'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountMoveReversal(models.Model):
#     _inherit = 'account.move.reversal'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountMrBor(models.Model):
#     _inherit = 'account.mr.bor'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountMrBTO(models.Model):
#     _inherit = 'account.mr.bto'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountMrKunjungan(models.Model):
#     _inherit = 'account.mr.kunjungan'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountMrLos(models.Model):
#     _inherit = 'account.mr.los'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountMrToi(models.Model):
#     _inherit = 'account.mr.toi'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountPartialReconcile(models.Model):
#     _inherit = 'account.partial.reconcile'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountPaymentMethod(models.Model):
#     _inherit = 'account.payment.method'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountPaymentTerm(models.Model):
#     _inherit = 'account.payment.term'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountPaymentTermLine(models.Model):
#     _inherit = 'account.payment.term.line'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountPrintJournal(models.Model):
#     _inherit = 'account.print.journal'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountReceipt(models.Model):
#     _inherit = 'account.receipt'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountReceiptLine(models.Model):
#     _inherit = 'account.receipt.line'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountReconcileModel(models.Model):
#     _inherit = 'account.reconcile.model'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountReconcileModelTemplate(models.Model):
#     _inherit = 'account.reconcile.model.template'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountRegisterPayments(models.Model):
#     _inherit = 'account.register.payments'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountReportGeneralLedger(models.Model):
#     _inherit = 'account.report.general.ledger'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountReportPartnerLedger(models.Model):
#     _inherit = 'account.report.partner.ledger'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountReportStandardLedgerLine(models.Model):
#     _inherit = 'account.report.standard.ledger.line'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountReportStandardLedgerPeriode(models.Model):
#     _inherit = 'account.report.standard.ledger.periode'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountReportStandardLedgerReport(models.Model):
#     _inherit = 'account.report.standard.ledger.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountReportStandardLedgerReportObject(models.Model):
#     _inherit = 'account.report.standard.ledger.report.object'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountTaxAccountTag(models.Model):
#     _inherit = 'account.tax.account.tag'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountTaxGroup(models.Model):
#     _inherit = 'account.tax.group'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountTaxTemplate(models.Model):
#     _inherit = 'account.tax.template'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountUnbilledStatusReport(models.Model):
#     _inherit = 'account.unbilled.status.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountUnreconcile(models.Model):
#     _inherit = 'account.unreconcile'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAccountingReport(models.Model):
#     _inherit = 'accounting.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAssetAssetReport(models.Model):
#     _inherit = 'asset.asset.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAssetModify(models.Model):
#     _inherit = 'asset.modify'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolAudittailRulesUsers(models.Model):
#     _inherit = 'audittail.rules.users'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolBarcodeNomenclature(models.Model):
#     _inherit = 'barcode.nomenclature'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolBarcodeRule(models.Model):
#     _inherit = 'barcode.rule'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolBillPackageDetail(models.Model):
#     _inherit = 'bill.package.detail'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolBusBus(models.Model):
#     _inherit = 'bus.bus'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolBusPresence(models.Model):
#     _inherit = 'bus.presence'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolCashBoxIn(models.Model):
#     _inherit = 'cash.box.in'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolCashBoxOut(models.Model):
#     _inherit = 'cash.box.out'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolChangePasswordUser(models.Model):
#     _inherit = 'change.password.user'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolChangePrductionQty(models.Model):
#     _inherit = 'change.production.qty'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolCostCenterReport(models.Model):
#     _inherit = 'cost.center.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolCoveringBillingId(models.Model):
#     _inherit = 'covering.billing.id'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolCoveringId(models.Model):
#     _inherit = 'covering.id'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolDecimalPrecision(models.Model):
#     _inherit = 'decimal.precision'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolDecimalPrecisionTest(models.Model):
#     _inherit = 'decimal.precision.test'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolDoctorFeeOthersDetail(models.Model):
#     _inherit = 'doctor.fee.others.detail'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolDoctorFeePajak(models.Model):
#     _inherit = 'doctor.fee.pajak'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolEfaktur(models.Model):
#     _inherit = 'efaktur'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolEfakturAuto(models.Model):
#     _inherit = 'efaktur.auto'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolEfakturPartner(models.Model):
#     _inherit = 'efaktur.partner'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolEfakturPk(models.Model):
#     _inherit = 'efaktur.pk'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolEfakturPm(models.Model):
#     _inherit = 'efaktur.pm'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolEfakturProduct(models.Model):
#     _inherit = 'efaktur.product'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolEmailTemplatePreview(models.Model):
#     _inherit = 'email.template.preview'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolGenerateEfaktur(models.Model):
#     _inherit = 'generate.efaktur'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolHrEmployee(models.Model):
#     _inherit = 'hr.employee'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolHrEmployeeCategory(models.Model):
#     _inherit = 'hr.employee.category'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolHrJob(models.Model):
#     _inherit = 'hr.job'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrActClient(models.Model):
#     _inherit = 'ir.act.client'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrActReportXml(models.Model):
#     _inherit = 'ir.act.report.xml'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrActServer(models.Model):
#     _inherit = 'ir.act.server'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrActUrl(models.Model):
#     _inherit = 'ir.act.url'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrActWindow(models.Model):
#     _inherit = 'ir.act.window'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrActWindowView(models.Model):
#     _inherit = 'ir.act.window.view'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrActions(models.Model):
#     _inherit = 'ir.actions'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrActionsTodo(models.Model):
#     _inherit = 'ir.actions.todo'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrAttachment(models.Model):
#     _inherit = 'ir.attachment'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrConfigParameter(models.Model):
#     _inherit = 'ir.config.parameter'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrCron(models.Model):
#     _inherit = 'ir.cron'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrExports(models.Model):
#     _inherit = 'ir.exports'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrExportsLine(models.Model):
#     _inherit = 'ir.exports.line'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrFilters(models.Model):
#     _inherit = 'ir.filters'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrLogging(models.Model):
#     _inherit = 'ir.logging'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrMailServer(models.Model):
#     _inherit = 'ir.mail.server'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrModel(models.Model):
#     _inherit = 'ir.model'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrModelAccess(models.Model):
#     _inherit = 'ir.model.access'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrModelConstraint(models.Model):
#     _inherit = 'ir.model.constraint'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrModelData(models.Model):
#     _inherit = 'ir.model.data'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrModelFields(models.Model):
#     _inherit = 'ir.model.fields'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrModuleCategory(models.Model):
#     _inherit = 'ir.module.category'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrModuleModule(models.Model):
#     _inherit = 'ir.module.module'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrModuleModuleDependency(models.Model):
#     _inherit = 'ir.module.module.dependency'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrProperty(models.Model):
#     _inherit = 'ir.property'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrRule(models.Model):
#     _inherit = 'ir.rule'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrSequence(models.Model):
#     _inherit = 'ir.sequence'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrSequenceDateRange(models.Model):
#     _inherit = 'ir.sequence.date.range'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrServerObjectLines(models.Model):
#     _inherit = 'ir.server.object.lines'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrTranslation(models.Model):
#     _inherit = 'ir.translation'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrUiMenu(models.Model):
#     _inherit = 'ir.ui.menu'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrUiView(models.Model):
#     _inherit = 'ir.ui.view'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrUiViewCustom(models.Model):
#     _inherit = 'ir.ui.view.custom'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolIrValues(models.Model):
#     _inherit = 'ir.values'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolKecamatan(models.Model):
#     _inherit = 'kecamatan'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolKelurahan(models.Model):
#     _inherit = 'kelurahan'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolKota(models.Model):
#     _inherit = 'kota'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolLoginDetail(models.Model):
#     _inherit = 'login.detail'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolMakeProcurement(models.Model):
#     _inherit = 'make.procurement'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolMrpConfigSettings(models.Model):
#     _inherit = 'mrp.config.settings'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolMrpMessage(models.Model):
#     _inherit = 'mrp.message'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolMrpProduceStockMoveLots(models.Model):
#     _inherit = 'mrp.produce.stock.move.lots'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolMrpRouting(models.Model):
#     _inherit = 'mrp.routing'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolMrpRoutingworkcenter(models.Model):
#     _inherit = 'mrp.routing.workcenter'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolMrpUnbuild(models.Model):
#     _inherit = 'mrp.unbuild'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolMrpWorkcenter(models.Model):
#     _inherit = 'mrp.workcenter'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolMrpWorkcenterProductivity(models.Model):
#     _inherit = 'mrp.workcenter.productivity'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolMrpWorkcenterProductivityLoss(models.Model):
#     _inherit = 'mrp.workcenter.productivity.loss'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolMrpWorkorder(models.Model):
#     _inherit = 'mrp.workorder'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolPaymentAcquirer(models.Model):
#     _inherit = 'payment.acquirer'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolPaymentToken(models.Model):
#     _inherit = 'payment.token'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolPaymentTrasaction(models.Model):
#     _inherit = 'payment.transaction'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolPortalWizardUser(models.Model):
#     _inherit = 'portal.wizard.user'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProcurementGroup(models.Model):
#     _inherit = 'procurement.group'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProcurementOrder(models.Model):
#     _inherit = 'procurement.order'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProcurementOrderComputeAll(models.Model):
#     _inherit = 'procurement.order.compute.all'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProcurementOrderpointCompute(models.Model):
#     _inherit = 'procurement.orderpoint.compute'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProcurementRule(models.Model):
#     _inherit = 'procurement.rule'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProductAttribute(models.Model):
#     _inherit = 'product.attribute'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProductAttributeLine(models.Model):
#     _inherit = 'product.attribute.line'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProductAttributePrice(models.Model):
#     _inherit = 'product.attribute.price'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProductAttributeValue(models.Model):
#     _inherit = 'product.attribute.value'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProductPackaging(models.Model):
#     _inherit = 'product.packaging'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProductPriceList(models.Model):
#     _inherit = 'product.price.list'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProductPricelist(models.Model):
#     _inherit = 'product.pricelist'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProductPricelistItem(models.Model):
#     _inherit = 'product.pricelist.item'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProductPutaway(models.Model):
#     _inherit = 'product.putaway'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolProductRemoval(models.Model):
#     _inherit = 'product.removal'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolPurchaseConfigSettings(models.Model):
#     _inherit = 'purchase.config.settings'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolPurchaseReport(models.Model):
#     _inherit = 'purchase.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolPurchaseRequisitionType(models.Model):
#     _inherit = 'purchase.requisition.type'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolReport(models.Model):
#     _inherit = 'report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolReportPaperformat(models.Model):
#     _inherit = 'report.paperformat'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolReportStockCard(models.Model):
#     _inherit = 'report.stock.card'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolReportStockCheckQty(models.Model):
#     _inherit = 'report.stock.check.qty'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolReportStockForecast(models.Model):
#     _inherit = 'report.stock.forecast'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolReportStockLinesDate(models.Model):
#     _inherit = 'report.stock.lines.date'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResConfig(models.Model):
#     _inherit = 'res.config'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResConfigInstaller(models.Model):
#     _inherit = 'res.config.installer'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResConfigSettings(models.Model):
#     _inherit = 'res.config.settings'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResCountry(models.Model):
#     _inherit = 'res.country'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResCountryGroup(models.Model):
#     _inherit = 'res.country.group'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResCountryState(models.Model):
#     _inherit = 'res.country.state'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResFont(models.Model):
#     _inherit = 'res.font'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResLang(models.Model):
#     _inherit = 'res.lang'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResPartnerBank(models.Model):
#     _inherit = 'res.partner.bank'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResPartnerCategory(models.Model):
#     _inherit = 'res.partner.category'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResPartnerTitle(models.Model):
#     _inherit = 'res.partner.title'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResRequestLink(models.Model):
#     _inherit = 'res.request.link'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResUsersLog(models.Model):
#     _inherit = 'res.users.log'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResourceCalendar(models.Model):
#     _inherit = 'resource.calendar'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResourceCalendarAttendance(models.Model):
#     _inherit = 'resource.calendar.attendance'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResourceCalendarLeaves(models.Model):
#     _inherit = 'resource.calendar.leaves'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolResourceResource(models.Model):
#     _inherit = 'resource.resource'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolSaleAdvancePaymentInv(models.Model):
#     _inherit = 'sale.advance.payment.inv'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolSaleConfigSettings(models.Model):
#     _inherit = 'sale.config.settings'

#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolSaleLayoutCategory(models.Model):
#     _inherit = 'sale.layout.category'

#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolSaleOrderBulkFilter(models.Model):
#     _inherit = 'sale.order.bulk.filter'

#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolSaleOrderWizardLine(models.Model):
#     _inherit = 'sale.order.wizard.line'

#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolSaleOverview(models.Model):
#     _inherit = 'sale.overview'

#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolSaleOverviewTemp(models.Model):
#     _inherit = 'sale.overview.temp'

#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolSaleReport(models.Model):
#     _inherit = 'sale.report'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockBackorderConfirmation(models.Model):
#     _inherit = 'stock.backorder.confirmation'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockChangeProductQty(models.Model):
#     _inherit = 'stock.change.product.qty'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockChangeStandardPrice(models.Model):
#     _inherit = 'stock.change.standard.price'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockConfigSettings(models.Model):
#     _inherit = 'stock.config.settings'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockFixedPutawayStrat(models.Model):
#     _inherit = 'stock.fixed.putaway.strat'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockHistory(models.Model):
#     _inherit = 'stock.history'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockImmediateTransfer(models.Model):
#     _inherit = 'stock.immediate.transfer'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockIncoterms(models.Model):
#     _inherit = 'stock.incoterms'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockInventoryLineTemp(models.Model):
#     _inherit = 'stock.inventory.line.temp'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockLocationPath(models.Model):
#     _inherit = 'stock.location.path'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockLocationRoute(models.Model):
#     _inherit = 'stock.location.route'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockLocationRouteCateg(models.Model):
#     _inherit = 'stock.location.route.categ'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockLocationRouteMove(models.Model):
#     _inherit = 'stock.location.route.move'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockLocationRouteProcurement(models.Model):
#     _inherit = 'stock.location.route.procurement'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockMoveLots(models.Model):
#     _inherit = 'stock.move.lots'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockMoveOperationLink(models.Model):
#     _inherit = 'stock.move.operation.link'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockQuantPackage(models.Model):
#     _inherit = 'stock.quant.package'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockReturnPicking(models.Model):
#     _inherit = 'stock.return.picking'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockReturnPickingLine(models.Model):
#     _inherit = 'stock.return.picking.line'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockRouteProduct(models.Model):
#     _inherit = 'stock.route.product'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockRouteWarehouse(models.Model):
#     _inherit = 'stock.route.warehouse'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockWarehouse(models.Model):
#     _inherit = 'stock.warehouse'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockWarehouseOrderpoint(models.Model):
#     _inherit = 'stock.warehouse.orderpoint'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolStockWhResupplyTable(models.Model):
#     _inherit = 'stock.wh.resupply.table'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolTableStandardReportAccount(models.Model):
#     _inherit = 'table.standard.report.accounts'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolTableStandardReportLineTotal(models.Model):
#     _inherit = 'table.standard.report.line.total'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolTableStandardReportPartner(models.Model):
#     _inherit = 'table.standard.report.partner'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolTurnover(models.Model):
#     _inherit = 'turnover'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolValidateAccountMove(models.Model):
#     _inherit = 'validate.account.move'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolVitKecamatan(models.Model):
#     _inherit = 'vit.kecamatan'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolVitKelurahan(models.Model):
#     _inherit = 'vit.kelurahan'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date

# class ConsolVitKota(models.Model):
#     _inherit = 'vit.kota'
#     sync_type = sync.type
#     sync_consol_id_unit = sync.consol_id_unit
#     sync_consol_id_main = sync.consol_id_main
#     sync_consol_date = sync.consol_date
