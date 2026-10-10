# -*- coding: utf-8 -*-

import base64
import binascii
import hmac
import secrets
from odoo import models, fields, api, tools, exceptions, _, http

from ..models import sync


from odoo import http, models, tools
from odoo.http import request


def _db_col(env, table_name, alias, column_name, default_expr):
    """Return alias.column_name if the DB column exists, otherwise default SQL expression."""
    env.cr.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s
          AND column_name = %s
        LIMIT 1
    """, (table_name, column_name))
    return "%s.%s" % (alias, column_name) if env.cr.fetchone() else default_expr


class SaleOrderLineAccrual(models.Model):
    _name = 'sale.order.line.accrual'
    _description = 'DIL TDM - IP Payable Accrual'
    _auto = False
    _table = 'view_sale_order_line_accrual'
    _rec_name = 'name'
    _order = 'tglproses desc, id desc'

    is_eproc = fields.Boolean(string='Is Eproc', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    sync_id = sync.id_big
    sync_id_api = sync.id_api
    sync_type = sync.type
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    tglproses = fields.Date(string='TglProses', readonly=True)
    type_line = fields.Char(string='Type Line', readonly=True)
    name = fields.Text(string='Service Item', readonly=True)
    order_id = fields.Many2one('sale.order', string='Admission Number', readonly=True)
    parent_admission_no = fields.Char(string='Parent Admission No.', readonly=True)
    number_admission = fields.Char(string='Number Admission', readonly=True)
    admission_type = fields.Char(string='Admission Type', readonly=True)
    admit_date = fields.Datetime(string='Admit Date', readonly=True)
    ref_admission_id = fields.Many2one('sale.order', string='Ref Admission ID.', readonly=True)
    ref_admission_no = fields.Char(string='Ref Admission No.', readonly=True)
    billing_id = fields.Many2one('sale.order.bill', string='Billing No.', readonly=True)
    billno = fields.Char(string='Bill No', readonly=True)
    bill_date = fields.Date(string='Bill Date', readonly=True)
    discharge_date = fields.Datetime(string='Discharge Date', readonly=True)
    discharge_reason = fields.Char(string='Discharge Reason', readonly=True)
    payer_id = fields.Many2one('res.partner', string='Payer ID', readonly=True)
    payer_code = fields.Char(string='Main Payer Code', readonly=True)
    payer_name = fields.Char(string='Payer Name Rawdata', readonly=True)
    payer_type = fields.Char(string='Main Payer Type', readonly=True)
    payer = fields.Many2one('res.partner', string='Main Payer Name', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Patient Name', readonly=True)
    registration_code = fields.Char(string='Patient MRID', readonly=True)
    patient_state = fields.Char(string='Patient State', readonly=True)
    patient_nationality = fields.Char(string='Patient Nationality', readonly=True)
    patient_country = fields.Char(string='Patient Country', readonly=True)
    patient_area = fields.Char(string='Patient Area', readonly=True)
    patient_street = fields.Char(string='Patient Street', readonly=True)
    gender = fields.Selection([('male', 'Male'), ('female', 'Female'), ('unknown', 'Unknown')], string='Gender', readonly=True)
    age = fields.Integer(string='Age', readonly=True)
    patient_type = fields.Selection([('1', 'OP'), ('2', 'IP'), ('3', 'Emergency'), ('4', 'Daycare'), ('5', 'MCU/Pharmacy Issues Only(FO)'), ('6', 'Pharmacy (Direct)'), ('0', 'Both')], string='Patient Type', readonly=True)
    lob_los = fields.Char(string='LOB/LOS', readonly=True)
    patient_group = fields.Char(string='Patient Group', readonly=True)
    revenue_type = fields.Char(string='Revenue Type', readonly=True)
    special_group = fields.Char(string='Special Group', readonly=True)
    special_group2 = fields.Char(string='Special Group 2', readonly=True)
    service_group_id = fields.Many2one('product.category', string='Service Group ID', readonly=True)
    service_group = fields.Char(string='Service Group Name', readonly=True)
    service_categ_id = fields.Many2one('product.category', string='Service Category', readonly=True)
    service_categ_name = fields.Char(string='Service Category Name', readonly=True)
    department_id = fields.Char(string='Department Area', readonly=True)
    item_specialisation_id = fields.Many2one('product.category', string='Item Specialisation ID', readonly=True)
    item_specialisation = fields.Char(string='Item Specialisation', readonly=True)
    location_id = fields.Many2one('stock.location', string='Facility/Location', readonly=True)
    is_package = fields.Boolean(string='Is Component of Package', readonly=True)
    package_id = fields.Many2one('product.product', string='Package Rel', readonly=True)
    package_name = fields.Char(string='Package Name', readonly=True)
    package_type = fields.Char(string='Package Type', readonly=True)
    package_order_no = fields.Char(string='Package Order Number', readonly=True)
    package_order_date = fields.Datetime(string='Package Order Date', readonly=True)
    package_selling_price = fields.Float(string='Package Selling Price', readonly=True)
    package_contribution = fields.Float(string='Package Contribution', readonly=True)
    package_doctor_share = fields.Float(string='Package Doctor Share', readonly=True)
    product_categ_id = fields.Many2one('product.category', string='Product Category', readonly=True)
    bed_type = fields.Char(string='Bill BedTypeName', readonly=True)
    order_no = fields.Char(string='HIS Order No', readonly=True)
    order_type = fields.Char(string='HIS OrderType', readonly=True)
    order_date = fields.Datetime(string='HIS Order Date', readonly=True)
    order_item_no = fields.Char(string='HIS Order Item', readonly=True)
    cyto = fields.Boolean(string='Cyto', readonly=True)
    penyulit = fields.Boolean(string='Penyulit', readonly=True)
    sales_id = fields.Char(string='HIS SalesID', readonly=True)
    sales_date = fields.Char(string='HIS Sales Date', readonly=True)
    sales_return_id = fields.Char(string='HIS ReturnID', readonly=True)
    sales_return_date = fields.Char(string='HIS Return Date', readonly=True)
    room_id = fields.Many2one('hospital.room.name', string='Room Name', readonly=True)
    bed_id = fields.Many2one('hospital.bed.name', string='Bed Name', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    manufacture = fields.Char(string='Manufacturer Name', readonly=True)
    brand = fields.Char(string='Brand Name', readonly=True)
    antibiotic = fields.Boolean(string='Antibiotic', readonly=True)
    generic = fields.Boolean(string='Generic', readonly=True)
    narcotic = fields.Boolean(string='Narcotic', readonly=True)
    psychotropic = fields.Boolean(string='Psychotropic', readonly=True)
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure', readonly=True)
    price_unit = fields.Float(string='Unit Price', readonly=True)
    product_uom_qty = fields.Float(string='Quantity', readonly=True)
    price_subtotal = fields.Monetary(string='Subtotal', currency_field='currency_id', readonly=True)
    discount = fields.Float(string='Discount', readonly=True)
    price_total = fields.Monetary(string='Total Revenue', currency_field='currency_id', readonly=True)
    personal_amount = fields.Float(string='Personal Amount', readonly=True)
    payer_amount = fields.Float(string='Main Payer Amount', readonly=True)
    cost_unit = fields.Float(string='HIS Cost Unit', readonly=True)
    cost_total = fields.Float(string='HIS Cost Total', readonly=True)
    hna_unit = fields.Float(string='HNA Unit', readonly=True)
    hna_total = fields.Float(string='HNA Total', readonly=True)
    base_price_unit = fields.Float(string='Base Price Unit', readonly=True)
    base_price_total = fields.Float(string='Base Price Total', readonly=True)
    batch_id = fields.Char(string='HIS BatchNo', readonly=True)
    batch_rel = fields.Many2one('stock.lot', string='HIS Batch Rel', readonly=True)
    batch_expired = fields.Date(string='HIS Batch Expired', readonly=True)
    discount_id = fields.Many2one('hospital.discount.type', string='Discount Type', readonly=True)
    discount_date = fields.Datetime(string='Discount Date', readonly=True)
    discount_reason = fields.Char(string='Discount Reason', readonly=True)
    discount_level = fields.Char(string='Discount Level', readonly=True)
    discount_name = fields.Char(string='Discount Name', readonly=True)
    bed_allocation_no = fields.Char(string='Allocation No.', readonly=True)
    bed_allocation_end = fields.Datetime(string='Allocation End', readonly=True)
    bed_allocation_start = fields.Datetime(string='Allocation Start', readonly=True)
    bed_type_id = fields.Many2one('hospital.bed.type', string='Billable BedType', readonly=True)
    eligible_bed_type_id = fields.Many2one('hospital.bed.type', string='Eligible BedType', readonly=True)
    alloted_bed_type_id = fields.Many2one('hospital.bed.type', string='Alloted BedType', readonly=True)
    tariff_id = fields.Many2one('hospital.tariff', string='Tariff Name', readonly=True)
    primary_diagnosis_code = fields.Char(string='Primary Diagnosis Code', readonly=True)
    primary_diagnosis_name = fields.Char(string='Primary Diagnosis Name', readonly=True)
    secondary_diagnosis_code = fields.Char(string='Secondary Diagnosis Code', readonly=True)
    secondary_diagnosis_name = fields.Char(string='Secondary Diagnosis Name', readonly=True)
    referral_id = fields.Many2one('referral.transaction', string='Referral Trans', readonly=True)
    referral_number = fields.Char(string='Referral No.', readonly=True)
    referral_doc_id = fields.Many2one('account.analytic.account', string='Referral Doctor', readonly=True)
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Doctor', readonly=True)
    parent_analytic_id = fields.Many2one('account.analytic.account', string='Specialization (Analytic)', readonly=True)
    primary_doc_id = fields.Many2one('account.analytic.account', string='Primary Doctor', readonly=True)
    parent_analytic_primary_id = fields.Many2one('account.analytic.account', string='Specialization (Primary Doctor)', readonly=True)
    perform_doc_id = fields.Many2one('account.analytic.account', string='Perform Doctor', readonly=True)
    parent_perform_id = fields.Many2one('account.analytic.account', string='Specialization (Perform Doctor)', readonly=True)
    prescribe_doc_id = fields.Many2one('account.analytic.account', string='Prescribe Doctor', readonly=True)
    parent_prescribe_id = fields.Many2one('account.analytic.account', string='Specialization (Prescribe Doctor)', readonly=True)
    surgery_operator_id = fields.Many2one('account.analytic.account', string='Surgery Operator', readonly=True)
    surgery_operator_ass_id = fields.Many2one('account.analytic.account', string='Surgery Operator (Ass)', readonly=True)
    surgery_team_id = fields.Many2one('account.analytic.account', string='Surgery Team', readonly=True)
    surgery_team_ass_id = fields.Many2one('account.analytic.account', string='Surgery Team (Ass)', readonly=True)
    anesthetist_operator_id = fields.Many2one('account.analytic.account', string='Anesthetist Operator', readonly=True)
    anesthetist_operator_ass_id = fields.Many2one('account.analytic.account', string='Anesthetist Operator (Ass)', readonly=True)
    arcus_sub_billing_group_id = fields.Many2one('product.category', string='Arcus Sub Billing Group ID', readonly=True)
    arcus_billing_group_id = fields.Many2one('product.category', string='Arcus Billing Group ID', readonly=True)
    sales_patientorderid = fields.Char(string='Sales Patient Order Item ID', readonly=True)
    sales_chargecodeid = fields.Char(string='Sales ChargeCodeID', readonly=True)
    sales_orderitemid = fields.Char(string='Sales OrderItemID', readonly=True)
    sales_billitemid = fields.Char(string='Sales BillItemID', readonly=True)
    sales_order_status = fields.Char(string='Sales Order Status', readonly=True)
    sales_order_lastupdate = fields.Datetime(string='Sales Order Last Update', readonly=True)
    sales_order_start = fields.Datetime(string='Sales Order Start', readonly=True)
    sales_order_end = fields.Datetime(string='Sales Order End', readonly=True)
    sales_billing_datetime = fields.Datetime(string='Sales Billing Datetime', readonly=True)
    sales_admission_datetime = fields.Datetime(string='Sales Admission Datetime', readonly=True)
    sales_diagnosis_primary_code = fields.Char(string='Sales Diagnosis Primary Code', readonly=True)
    sales_procedure_name = fields.Char(string='Sales Procedure Name', readonly=True)
    sales_diagnosis_secondary_code = fields.Char(string='Sales Diagnosis Secondary Code', readonly=True)
    sales_patient_register_date = fields.Datetime(string='Sales Patient Register Date', readonly=True)
    sales_product_ingredient = fields.Char(string='Sales Product Ingredient', readonly=True)
    sales_diagnosis_secondary_name = fields.Char(string='Sales Diagnosis Secondary Name', readonly=True)
    sales_discharge_datetime = fields.Datetime(string='Sales Discharge Datetime', readonly=True)
    sales_procedure_code = fields.Char(string='Sales Procedure Code', readonly=True)
    sales_diagnosis_primary_name = fields.Char(string='Sales Diagnosis Primary Name', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW view_sale_order_line_accrual AS (
                SELECT
                    sol.id AS id,
                    TRUE AS is_eproc,
                    sol.sync_id AS sync_id,
                    sol.sync_id_api AS sync_id_api,
                    sol.sync_type AS sync_type,
                    sol.company_id AS company_id,
                    so.currency_id AS currency_id,
                    sol.tglproses AS tglproses,
                    sol.type_line AS type_line,
                    sol.name AS name,
                    sol.order_id AS order_id,
                    sol.parent_admission_no AS parent_admission_no,
                    COALESCE(so.name, '') AS number_admission,
                    sol.admission_type AS admission_type,
                    sol.admit_date AS admit_date,
                    sol.ref_admission_id AS ref_admission_id,
                    sol.ref_admission_no AS ref_admission_no,
                    sol.billing_id AS billing_id,
                    sol.billno AS billno,
                    sol.bill_date AS bill_date,
                    sol.discharge_date AS discharge_date,
                    sol.discharge_reason AS discharge_reason,
                    sol.payer AS payer_id,
                    sol.payer_code AS payer_code,
                    sol.payer_name AS payer_name,
                    sol.payer_type AS payer_type,
                    sol.payer AS payer,
                    sol.partner_id AS partner_id,
                    sol.registration_code AS registration_code,
                    sol.patient_state AS patient_state,
                    sol.patient_nationality AS patient_nationality,
                    sol.patient_country AS patient_country,
                    sol.patient_area AS patient_area,
                    sol.patient_street AS patient_street,
                    partner.gender AS gender,
                    partner.age AS age,
                    sol.patient_type AS patient_type,
                    sol.lob_los AS lob_los,
                    sol.patient_group AS patient_group,
                    sol.revenue_type AS revenue_type,
                    sol.special_group AS special_group,
                    sol.special_group2 AS special_group2,
                    sol.service_group_id AS service_group_id,
                    sol.service_group AS service_group,
                    sol.service_categ_id AS service_categ_id,
                    service_categ.name AS service_categ_name,
                    sol.department_id AS department_id,
                    sol.item_specialisation_id AS item_specialisation_id,
                    sol.item_specialisation AS item_specialisation,
                    sol.location_id AS location_id,
                    sol.is_package AS is_package,
                    sol.package_id AS package_id,
                    sol.package_name AS package_name,
                    sol.package_type AS package_type,
                    sol.package_order_no AS package_order_no,
                    sol.package_order_date AS package_order_date,
                    sol.package_selling_price AS package_selling_price,
                    sol.package_contribution AS package_contribution,
                    sol.package_doctor_share AS package_doctor_share,
                    sol.product_categ_id AS product_categ_id,
                    sol.bed_type AS bed_type,
                    sol.order_no AS order_no,
                    sol.order_type AS order_type,
                    sol.order_date AS order_date,
                    sol.order_item_no AS order_item_no,
                    sol.cyto AS cyto,
                    sol.penyulit AS penyulit,
                    sol.sales_id AS sales_id,
                    sol.sales_date AS sales_date,
                    sol.sales_return_id AS sales_return_id,
                    sol.sales_return_date AS sales_return_date,
                    sol.room_id AS room_id,
                    sol.bed_id AS bed_id,
                    sol.product_id AS product_id,
                    sol.manufacture AS manufacture,
                    sol.brand AS brand,
                    sol.antibiotic AS antibiotic,
                    sol.generic AS generic,
                    sol.narcotic AS narcotic,
                    sol.psychotropic AS psychotropic,
                    sol.product_uom AS product_uom,
                    sol.price_unit AS price_unit,
                    sol.product_uom_qty AS product_uom_qty,
                    sol.price_subtotal AS price_subtotal,
                    sol.discount AS discount,
                    sol.price_total AS price_total,
                    sol.personal_amount AS personal_amount,
                    sol.payer_amount AS payer_amount,
                    sol.cost_unit AS cost_unit,
                    sol.cost_total AS cost_total,
                    sol.hna_unit AS hna_unit,
                    sol.hna_total AS hna_total,
                    sol.base_price_unit AS base_price_unit,
                    sol.base_price_total AS base_price_total,
                    sol.batch_id AS batch_id,
                    sol.batch_rel AS batch_rel,
                    sol.batch_expired AS batch_expired,
                    sol.discount_id AS discount_id,
                    sol.discount_date AS discount_date,
                    sol.discount_reason AS discount_reason,
                    sol.discount_level AS discount_level,
                    sol.discount_name AS discount_name,
                    sol.bed_allocation_no AS bed_allocation_no,
                    sol.bed_allocation_end AS bed_allocation_end,
                    sol.bed_allocation_start AS bed_allocation_start,
                    sol.bed_type_id AS bed_type_id,
                    sol.eligible_bed_type_id AS eligible_bed_type_id,
                    sol.alloted_bed_type_id AS alloted_bed_type_id,
                    sol.tariff_id AS tariff_id,
                    sol.primary_diagnosis_code AS primary_diagnosis_code,
                    sol.primary_diagnosis_name AS primary_diagnosis_name,
                    sol.secondary_diagnosis_code AS secondary_diagnosis_code,
                    sol.secondary_diagnosis_name AS secondary_diagnosis_name,
                    sol.referral_id AS referral_id,
                    sol.referral_number AS referral_number,
                    sol.referral_doc_id AS referral_doc_id,
                    sol.account_analytic_id AS account_analytic_id,
                    sol.parent_analytic_id AS parent_analytic_id,
                    sol.primary_doc_id AS primary_doc_id,
                    sol.parent_analytic_primary_id AS parent_analytic_primary_id,
                    sol.perform_doc_id AS perform_doc_id,
                    sol.parent_perform_id AS parent_perform_id,
                    sol.prescribe_doc_id AS prescribe_doc_id,
                    sol.parent_prescribe_id AS parent_prescribe_id,
                    sol.surgery_operator_id AS surgery_operator_id,
                    sol.surgery_operator_ass_id AS surgery_operator_ass_id,
                    sol.surgery_team_id AS surgery_team_id,
                    sol.surgery_team_ass_id AS surgery_team_ass_id,
                    sol.anesthetist_operator_id AS anesthetist_operator_id,
                    sol.anesthetist_operator_ass_id AS anesthetist_operator_ass_id,
                    sol.arcus_sub_billing_group_id AS arcus_sub_billing_group_id,
                    sol.arcus_billing_group_id AS arcus_billing_group_id,
                    sol.sales_patientorderid AS sales_patientorderid,
                    sol.sales_chargecodeid AS sales_chargecodeid,
                    sol.sales_orderitemid AS sales_orderitemid,
                    sol.sales_billitemid AS sales_billitemid,
                    sol.sales_order_status AS sales_order_status,
                    sol.sales_order_lastupdate AS sales_order_lastupdate,
                    sol.sales_order_start AS sales_order_start,
                    sol.sales_order_end AS sales_order_end,
                    sol.sales_billing_datetime AS sales_billing_datetime,
                    sol.sales_admission_datetime AS sales_admission_datetime,
                    sol.sales_diagnosis_primary_code AS sales_diagnosis_primary_code,
                    sol.sales_procedure_name AS sales_procedure_name,
                    sol.sales_diagnosis_secondary_code AS sales_diagnosis_secondary_code,
                    sol.sales_patient_register_date AS sales_patient_register_date,
                    sol.sales_product_ingredient AS sales_product_ingredient,
                    sol.sales_diagnosis_secondary_name AS sales_diagnosis_secondary_name,
                    sol.sales_discharge_datetime AS sales_discharge_datetime,
                    sol.sales_procedure_code AS sales_procedure_code,
                    sol.sales_diagnosis_primary_name AS sales_diagnosis_primary_name
                FROM sale_order_line sol
                LEFT JOIN sale_order so ON so.id = sol.order_id
                LEFT JOIN res_partner partner ON partner.id = sol.partner_id
                LEFT JOIN product_category service_categ ON service_categ.id = sol.service_categ_id
                WHERE sol.sync_id_api IS NOT NULL
                  AND sol.sync_id_api <> ''
                  AND sol.type_line IN ('ACCRUAL', 'ACCRUAL REVERSAL')
            )
        """)

    @api.model_create_multi
    def create(self, vals_list):
        raise exceptions.UserError(_('IP payable accrual interface records are read-only.'))

    def write(self, vals):
        raise exceptions.UserError(_('IP payable accrual interface records cannot be edited manually.'))

    def copy(self, default=None):
        raise exceptions.UserError(_('IP payable accrual interface records cannot be duplicated.'))

    def unlink(self):
        raise exceptions.UserError(_('IP payable accrual interface records cannot be deleted.'))

class EprocReportOrderView(models.Model):
    _name = 'eproc.report.order.view'
    _description = 'Jasper SQL View - Eproc Order'
    _auto = False
    _table = 'view_eproc_order'

    order_id = fields.Many2one('eproc.order', string='Order', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    company_name = fields.Char(string='Company Name', readonly=True)
    company_parent = fields.Char(string='Company Parent', readonly=True)

    order_no = fields.Char(string='Order No', readonly=True)
    rfq_no = fields.Char(string='RFQ No', readonly=True)
    order_purchase_no = fields.Char(string='Purchase No', readonly=True)
    po_no = fields.Char(string='PO No', readonly=True)
    order_valid_no = fields.Char(string='Order Valid No', readonly=True)
    order_ref = fields.Char(string='Reference', readonly=True)
    order_origin = fields.Char(string='Origin', readonly=True)
    order_type = fields.Char(string='Order Type', readonly=True)
    order_type_name = fields.Char(string='Order Type Name', readonly=True)

    purchase_type_id = fields.Many2one('eproc.type', string='Procurement Type', readonly=True)
    purchase_type_name = fields.Char(string='Procurement Type Name', readonly=True)
    procurement_type = fields.Char(string='Procurement Type', readonly=True)

    term_id = fields.Many2one('eproc.term', string='Term', readonly=True)
    term_name = fields.Char(string='Term Name', readonly=True)

    location_receipt_id = fields.Many2one('stock.location', string='Receipt Location', readonly=True)
    location_receipt_name = fields.Char(string='Receipt Location Name', readonly=True)
    location_receipt_address = fields.Text(string='Receipt Location Address', readonly=True)
    deliver_to = fields.Char(string='Deliver To', readonly=True)

    supplier_id = fields.Many2one('res.partner', string='Supplier', readonly=True)
    supplier_code = fields.Char(string='Supplier Code', readonly=True)
    supplier_vendor_code = fields.Char(string='Supplier Vendor Code', readonly=True)
    supplier_name = fields.Char(string='Supplier Name', readonly=True)
    supplier_phone = fields.Char(string='Supplier Phone', readonly=True)
    supplier_fax = fields.Char(string='Supplier Fax', readonly=True)
    supplier_pic = fields.Char(string='Supplier PIC', readonly=True)
    supplier_address = fields.Text(string='Supplier Address', readonly=True)
    supplier_city_state = fields.Char(string='Supplier City/State', readonly=True)

    address1 = fields.Char(string='Address 1', readonly=True)
    address2 = fields.Char(string='Address 2', readonly=True)
    address3 = fields.Char(string='Address 3', readonly=True)
    street = fields.Char(string='Street', readonly=True)
    city = fields.Char(string='City', readonly=True)
    zip = fields.Char(string='Zip', readonly=True)
    phone = fields.Char(string='Phone', readonly=True)
    fax = fields.Char(string='Fax', readonly=True)

    user_id = fields.Many2one('res.users', string='Responsible', readonly=True)
    user_name = fields.Char(string='Responsible Name', readonly=True)
    user_alias_name = fields.Char(string='Responsible Alias', readonly=True)
    user_display_name = fields.Char(string='Responsible Display Name', readonly=True)
    user_sipa_no = fields.Char(string='Responsible SIPA', readonly=True)
    user_signature = fields.Binary(string='Responsible Signature', readonly=True)
    user_position_name = fields.Char(string='Responsible Position', readonly=True)
    user_position_alias_name = fields.Char(string='Responsible Position Alias', readonly=True)
    user_position_display_name = fields.Char(string='Responsible Position Display', readonly=True)
    user_position = fields.Char(string='Responsible Position', readonly=True)

    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    department_name = fields.Char(string='Department Name', readonly=True)

    order_date = fields.Datetime(string='Order Date', readonly=True)
    order_valid_date = fields.Datetime(string='Order Valid Date', readonly=True)
    date_planned = fields.Datetime(string='Date Planned', readonly=True)
    notes = fields.Text(string='Notes', readonly=True)

    total_price = fields.Float(string='Total Price', readonly=True)
    total_discount = fields.Float(string='Total Discount', readonly=True)
    total_taxes = fields.Float(string='Total Taxes', readonly=True)
    total_netprice = fields.Float(string='Total Net Price', readonly=True)

    state = fields.Char(string='State', readonly=True)
    state_name = fields.Char(string='State Name', readonly=True)
    title = fields.Char(string='Title', readonly=True)
    document_no_label = fields.Char(string='Document No Label', readonly=True)
    document_no = fields.Char(string='Document No', readonly=True)
    active = fields.Boolean(string='Active', readonly=True)

    def init(self):
        order_purchase_no_expr = _db_col(
            self.env, 'eproc_order', 'o', 'order_purchase_no', "''::varchar"
        )
        order_ref_expr = _db_col(
            self.env, 'eproc_order', 'o', 'order_ref', "''::varchar"
        )
        order_origin_expr = _db_col(
            self.env, 'eproc_order', 'o', 'order_origin', "''::varchar"
        )
        order_type_expr = _db_col(
            self.env, 'eproc_order', 'o', 'order_type', "''::varchar"
        )
        order_date_expr = _db_col(
            self.env, 'eproc_order', 'o', 'order_date', "NULL::timestamp"
        )
        order_valid_date_expr = _db_col(
            self.env, 'eproc_order', 'o', 'order_valid_date', "NULL::timestamp"
        )
        date_planned_expr = _db_col(
            self.env, 'eproc_order', 'o', 'date_planned', order_valid_date_expr
        )
        notes_expr = _db_col(
            self.env, 'eproc_order', 'o', 'notes', "''::text"
        )
        active_expr = _db_col(
            self.env, 'eproc_order', 'o', 'active', "TRUE"
        )

        user_alias_expr = _db_col(
            self.env, 'res_users', 'ru', 'alias_name', "''::varchar"
        )
        user_sipa_expr = _db_col(
            self.env, 'res_users', 'ru', 'sipa_no', "''::varchar"
        )
        # Prefer the working field from the old report view: res_users.user_signature.
        # Fallback to res_users.sign when the database uses that field name.
        user_signature_expr = _db_col(
            self.env,
            'res_users',
            'ru',
            'user_signature',
            _db_col(self.env, 'res_users', 'ru', 'sign', "NULL")
        )
        user_position_alias_expr = _db_col(
            self.env, 'res_position', 'user_position', 'alias_name', "''::varchar"
        )

        total_price_expr = _db_col(
            self.env, 'eproc_order', 'o', 'total_price', "0.0"
        )
        total_discount_expr = _db_col(
            self.env, 'eproc_order', 'o', 'total_discount', "0.0"
        )
        total_taxes_expr = _db_col(
            self.env, 'eproc_order', 'o', 'total_taxes', "0.0"
        )
        total_netprice_expr = _db_col(
            self.env, 'eproc_order', 'o', 'total_netprice', "0.0"
        )

        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW view_eproc_order AS (
                SELECT
                    o.id AS id,
                    o.id AS order_id,
                    o.company_id AS company_id,

                    COALESCE(c.name, '') AS company_name,
                    COALESCE(c.name, '') AS company_parent,

                    COALESCE(o.order_no, '') AS order_no,
                    COALESCE(o.order_no, '') AS rfq_no,

                    COALESCE({order_purchase_no_expr}, '') AS order_purchase_no,
                    COALESCE({order_purchase_no_expr}, '') AS po_no,

                    ''::varchar AS order_valid_no,

                    COALESCE({order_ref_expr}, '') AS order_ref,
                    COALESCE({order_origin_expr}, '') AS order_origin,
                    COALESCE({order_type_expr}, '') AS order_type,

                    CASE COALESCE({order_type_expr}, '')
                        WHEN 'normal' THEN 'Normal'
                        WHEN 'repeat' THEN 'Repeat Order'
                        WHEN 'auto' THEN 'Auto PR/RFQ'
                        WHEN 'stock' THEN 'Stock'
                        WHEN 'non_stock' THEN 'Non Stock'
                        WHEN 'nonstock' THEN 'Non Stock'
                        ELSE COALESCE({order_type_expr}, '')
                    END AS order_type_name,

                    o.purchase_type_id AS purchase_type_id,
                    COALESCE(purchase_type.name::text, '') AS purchase_type_name,
                    COALESCE(purchase_type.name::text, '') AS procurement_type,

                    o.term_id AS term_id,
                    COALESCE(term.name::text, '') AS term_name,

                    o.location_receipt_id AS location_receipt_id,
                    COALESCE(location.complete_name, location.name, '') AS location_receipt_name,
                    COALESCE(location.complete_name, location.name, '') AS deliver_to,

                    o.supplier_id AS supplier_id,
                    COALESCE(supplier.ref, '') AS supplier_code,
                    COALESCE(supplier.ref, '') AS supplier_vendor_code,
                    COALESCE(supplier.name, '') AS supplier_name,

                    COALESCE(supplier.street, '') AS address1,
                    COALESCE(supplier.street2, '') AS address2,
                    ''::varchar AS address3,
                    COALESCE(supplier.street, '') AS street,
                    COALESCE(supplier.city, '') AS city,
                    COALESCE(supplier.zip, '') AS zip,
                    COALESCE(supplier.phone, '') AS phone,
                    COALESCE(supplier.fax, '') AS fax,

                    COALESCE(supplier.phone, '') AS supplier_phone,
                    COALESCE(supplier.fax, '') AS supplier_fax,
                    ''::varchar AS supplier_pic,

                    COALESCE(
                        CONCAT_WS(
                            E'\\n',
                            NULLIF(supplier.street, ''),
                            NULLIF(supplier.street2, '')
                        ),
                        ''
                    ) AS supplier_address,

                    COALESCE(
                        CONCAT_WS(
                            ', ',
                            NULLIF(supplier.city, ''),
                            NULLIF(supplier.zip, '')
                        ),
                        ''
                    ) AS supplier_city_state,

                    COALESCE(
                        CONCAT_WS(
                            E'\\n',
                            NULLIF(COALESCE(location.complete_name, location.name, ''), '')
                        ),
                        ''
                    ) AS location_receipt_address,

                    o.user_id AS user_id,
                    COALESCE(user_partner.name, '') AS user_name,
                    COALESCE({user_alias_expr}, '') AS user_alias_name,
                    COALESCE(NULLIF({user_alias_expr}, ''), user_partner.name, '') AS user_display_name,
                    COALESCE({user_sipa_expr}, '') AS user_sipa_no,
                    {user_signature_expr} AS user_signature,

                    COALESCE(user_position.name::text, '') AS user_position_name,
                    COALESCE({user_position_alias_expr}, '') AS user_position_alias_name,

                    COALESCE(
                        NULLIF({user_position_alias_expr}, ''),
                        NULLIF(user_position.name::text, ''),
                        NULLIF(dept.name, ''),
                        ''
                    ) AS user_position_display_name,

                    COALESCE(
                        NULLIF({user_position_alias_expr}, ''),
                        NULLIF(user_position.name::text, ''),
                        NULLIF(dept.name, ''),
                        ''
                    ) AS user_position,

                    o.department_id AS department_id,
                    COALESCE(dept.name, '') AS department_name,

                    {order_date_expr} AS order_date,
                    {order_valid_date_expr} AS order_valid_date,
                    {date_planned_expr} AS date_planned,

                    COALESCE({notes_expr}, '') AS notes,

                    COALESCE({total_price_expr}, 0.0) AS total_price,
                    COALESCE({total_discount_expr}, 0.0) AS total_discount,
                    COALESCE({total_taxes_expr}, 0.0) AS total_taxes,
                    COALESCE({total_netprice_expr}, 0.0) AS total_netprice,

                    COALESCE(o.state, '') AS state,

                    CASE COALESCE(o.state, '')
                        WHEN 'draft' THEN 'Draft'
                        WHEN 'approval' THEN 'Approval'
                        WHEN 'ready' THEN 'Ready to Procure'
                        WHEN 'tender' THEN 'Tender'
                        WHEN 'purchase' THEN 'Purchase'
                        WHEN 'expired' THEN 'Expired'
                        WHEN 'partial' THEN 'Partial Receipt'
                        WHEN 'done' THEN 'Completed'
                        WHEN 'rejected' THEN 'Rejected'
                        WHEN 'cancelled' THEN 'Cancelled'
                        ELSE COALESCE(o.state, '')
                    END AS state_name,

                    CASE
                        WHEN COALESCE(NULLIF({order_purchase_no_expr}, ''), '') <> ''
                          OR COALESCE(o.state, '') IN ('purchase', 'partial', 'done', 'expired')
                        THEN 'PURCHASE ORDER'
                        ELSE 'REQUEST FOR QUOTATION'
                    END AS title,

                    CASE
                        WHEN COALESCE(NULLIF({order_purchase_no_expr}, ''), '') <> ''
                          OR COALESCE(o.state, '') IN ('purchase', 'partial', 'done', 'expired')
                        THEN 'PO No'
                        ELSE 'RFQ No'
                    END AS document_no_label,

                    COALESCE(
                        NULLIF({order_purchase_no_expr}, ''),
                        NULLIF(o.order_no, ''),
                        ''
                    ) AS document_no,

                    COALESCE({active_expr}, TRUE) AS active

                FROM eproc_order o
                LEFT JOIN res_company c
                    ON c.id = o.company_id
                LEFT JOIN res_partner supplier
                    ON supplier.id = o.supplier_id
                LEFT JOIN res_country_state state
                    ON state.id = supplier.state_id
                LEFT JOIN res_users ru
                    ON ru.id = o.user_id
                LEFT JOIN res_partner user_partner
                    ON user_partner.id = ru.partner_id
                LEFT JOIN res_position user_position
                    ON user_position.id = ru.position_id
                LEFT JOIN hr_department dept
                    ON dept.id = o.department_id
                LEFT JOIN eproc_type purchase_type
                    ON purchase_type.id = o.purchase_type_id
                LEFT JOIN eproc_term term
                    ON term.id = o.term_id
                LEFT JOIN stock_location location
                    ON location.id = o.location_receipt_id
                WHERE COALESCE({active_expr}, TRUE) = TRUE
            )
        """.format(
            order_purchase_no_expr=order_purchase_no_expr,
            order_ref_expr=order_ref_expr,
            order_origin_expr=order_origin_expr,
            order_type_expr=order_type_expr,
            order_date_expr=order_date_expr,
            order_valid_date_expr=order_valid_date_expr,
            date_planned_expr=date_planned_expr,
            notes_expr=notes_expr,
            active_expr=active_expr,
            total_price_expr=total_price_expr,
            total_discount_expr=total_discount_expr,
            total_taxes_expr=total_taxes_expr,
            total_netprice_expr=total_netprice_expr,
            user_alias_expr=user_alias_expr,
            user_sipa_expr=user_sipa_expr,
            user_signature_expr=user_signature_expr,
            user_position_alias_expr=user_position_alias_expr,
        ))


class EprocReportOrderLineView(models.Model):
    _name = 'eproc.report.order.line.view'
    _description = 'Jasper SQL View - Eproc Order Line'
    _auto = False
    _table = 'view_eproc_order_line'

    order_line_id = fields.Many2one('eproc.order.line', string='Order Line', readonly=True)
    order_id = fields.Many2one('eproc.order', string='Order', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    sequence = fields.Integer(string='Sequence', readonly=True)
    date_planned = fields.Datetime(string='Date Planned', readonly=True)
    date_planned_text = fields.Char(string='Date Planned Text', readonly=True)

    order_no = fields.Char(string='Order No', readonly=True)
    order_purchase_no = fields.Char(string='Purchase No', readonly=True)

    product_tmpl_id = fields.Many2one('product.template', string='Product', readonly=True)
    product_code = fields.Char(string='Product Code', readonly=True)
    product_name = fields.Char(string='Product Name', readonly=True)
    description = fields.Text(string='Description', readonly=True)
    remark = fields.Text(string='Remark', readonly=True)

    product_categ_id = fields.Many2one('product.category', string='Product Category', readonly=True)
    product_categ_name = fields.Char(string='Product Category Name', readonly=True)

    pack_id = fields.Many2one('eproc.pack', string='Pack', readonly=True)
    pack_type = fields.Char(string='Pack Type', readonly=True)
    pack_name = fields.Char(string='Pack Name', readonly=True)
    units = fields.Char(string='Units', readonly=True)
    full_uom = fields.Char(string='Full UoM', readonly=True)

    pack_qty = fields.Float(string='Pack Qty', readonly=True)
    pack_price = fields.Float(string='Pack Price', readonly=True)
    pack_rate = fields.Float(string='Pack Rate', readonly=True)

    uom_id = fields.Many2one('uom.uom', string='UoM', readonly=True)
    uom_name = fields.Char(string='UoM Name', readonly=True)
    uom_qty = fields.Float(string='UoM Qty', readonly=True)
    uom_price = fields.Float(string='UoM Price', readonly=True)

    disc_rate = fields.Float(string='Discount Rate', readonly=True)
    tax_list = fields.Char(string='Taxes', readonly=True)
    tax_rate_text = fields.Char(string='Tax Rate Text', readonly=True)

    total_price = fields.Float(string='Total Price', readonly=True)
    total_discount = fields.Float(string='Total Discount', readonly=True)
    total_taxes = fields.Float(string='Total Taxes', readonly=True)
    total_netprice = fields.Float(string='Total Net Price', readonly=True)

    analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account', readonly=True)
    analytic_name = fields.Char(string='Analytic Name', readonly=True)

    agreement_line_id = fields.Many2one('eproc.agreement.line', string='Agreement Line', readonly=True)
    orderpoint_log_id = fields.Many2one('eproc.orderpoint.log', string='Orderpoint Log', readonly=True)
    request_line_id = fields.Many2one('eproc.request.line', string='Request Line', readonly=True)

    active = fields.Boolean(string='Active', readonly=True)
    state = fields.Char(string='State', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW view_eproc_order_line AS (
                SELECT
                    l.id AS id,
                    l.id AS order_line_id,
                    l.order_id AS order_id,
                    o.company_id AS company_id,

                    l.sequence AS sequence,
                    l.date_planned AS date_planned,
                    TO_CHAR(l.date_planned, 'DD/MM/YYYY') AS date_planned_text,

                    COALESCE(o.order_no, '') AS order_no,
                    COALESCE(o.order_purchase_no, '') AS order_purchase_no,

                    l.product_tmpl_id AS product_tmpl_id,
                    COALESCE(pt.default_code, '') AS product_code,
                    COALESCE(pt.name->>'en_US', pt.name->>'id_ID', pt.name::text, '') AS product_name,
                    COALESCE(l.name, '') AS description,
                    COALESCE(l.name, '') AS remark,

                    l.product_categ_id AS product_categ_id,
                    COALESCE(pc.name, '') AS product_categ_name,

                    l.pack_id AS pack_id,
                    COALESCE(pp.name::text, '') AS pack_type,
                    COALESCE(pp.name::text, '') AS pack_name,
                    COALESCE(pp.name::text, '') AS units,
                    COALESCE(pp.name::text, '') AS full_uom,

                    COALESCE(l.pack_qty, 0.0) AS pack_qty,
                    COALESCE(l.pack_price, 0.0) AS pack_price,
                    COALESCE(l.pack_rate, 1.0) AS pack_rate,

                    l.uom_id AS uom_id,
                    COALESCE(uom.name->>'en_US', uom.name->>'id_ID', uom.name::text, '') AS uom_name,

                    COALESCE(l.uom_qty, 0.0) AS uom_qty,
                    COALESCE(l.uom_price, 0.0) AS uom_price,

                    COALESCE(l.disc_rate, 0.0) AS disc_rate,

                    COALESCE(tax.tax_list, '') AS tax_list,
                    COALESCE(tax.tax_list, '') AS tax_rate_text,

                    COALESCE(l.total_price, 0.0) AS total_price,
                    COALESCE(l.total_discount, 0.0) AS total_discount,
                    COALESCE(l.total_taxes, 0.0) AS total_taxes,
                    COALESCE(l.total_netprice, 0.0) AS total_netprice,

                    l.analytic_id AS analytic_id,
                    COALESCE(analytic.name::text, '') AS analytic_name,

                    l.agreement_line_id AS agreement_line_id,
                    l.orderpoint_log_id AS orderpoint_log_id,
                    l.request_line_id AS request_line_id,

                    COALESCE(l.active, TRUE) AS active,
                    COALESCE(l.state, '') AS state

                FROM eproc_order_line l
                LEFT JOIN eproc_order o
                    ON o.id = l.order_id
                LEFT JOIN product_template pt
                    ON pt.id = l.product_tmpl_id
                LEFT JOIN product_category pc
                    ON pc.id = l.product_categ_id
                LEFT JOIN eproc_pack pp
                    ON pp.id = l.pack_id
                LEFT JOIN uom_uom uom
                    ON uom.id = l.uom_id
                LEFT JOIN account_analytic_account analytic
                    ON analytic.id = l.analytic_id
                LEFT JOIN LATERAL (
                    SELECT
                        STRING_AGG(COALESCE(et.name::text, ''), ', ' ORDER BY et.name::text) AS tax_list
                    FROM eproc_order_line_tax_rel rel
                    LEFT JOIN eproc_taxes et
                        ON et.id = rel.tax_id
                    WHERE rel.order_line_id = l.id
                ) tax ON TRUE
                WHERE COALESCE(l.active, TRUE) = TRUE
            )
        """)

class EprocReportReceiptView(models.Model):
    _name = 'eproc.report.receipt.view'
    _description = 'Jasper SQL View - Eproc Receipt'
    _auto = False
    _table = 'view_eproc_receipt'

    def init(self):
        active_expr = _db_col(
            self.env, 'eproc_receipt', 'r', 'active', "TRUE"
        )
        department_id_expr = _db_col(
            self.env, 'eproc_receipt', 'r', 'department_id', "NULL::integer"
        )

        user_alias_expr = _db_col(
            self.env, 'res_users', 'ru', 'alias_name', "''::varchar"
        )
        user_sipa_expr = _db_col(
            self.env, 'res_users', 'ru', 'sipa_no', "''::varchar"
        )
        user_signature_expr = _db_col(
            self.env,
            'res_users',
            'ru',
            'user_signature',
            _db_col(self.env, 'res_users', 'ru', 'sign', "NULL")
        )
        user_position_id_expr = _db_col(
            self.env, 'res_users', 'ru', 'position_id', "NULL::integer"
        )
        user_position_alias_expr = _db_col(
            self.env, 'res_position', 'user_position', 'alias_name', "''::varchar"
        )

        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW view_eproc_receipt AS (
                SELECT
                    r.id AS id,
                    r.id AS receipt_id,
                    r.company_id AS company_id,

                    COALESCE(c.name, '') AS company_name,

                    COALESCE(r.receipt_no, '') AS receipt_no,
                    COALESCE(r.receipt_valid_no, '') AS receipt_valid_no,
                    r.receipt_date AS receipt_date,
                    r.receipt_valid_date AS receipt_valid_date,
                    COALESCE(r.receipt_ref, '') AS receipt_ref,
                    COALESCE(r.receipt_type, '') AS receipt_type,
                    COALESCE(r.state, '') AS state,

                    COALESCE(rp.ref, '') AS supplier_code,
                    COALESCE(rp.name, '') AS supplier_name,
                    COALESCE(rp.street, '') AS addresss1,
                    COALESCE(rp.street2, '') AS address2,
                    NULL::varchar AS address3,
                    COALESCE(rp.street, '') AS street,
                    COALESCE(rp.city, '') AS city,
                    COALESCE(rp.zip, '') AS zip,
                    COALESCE(rp.phone, '') AS phone,
                    COALESCE(rp.fax, '') AS fax,

                    r.user_id AS user_id,
                    COALESCE(user_partner.name, '') AS user_name,
                    COALESCE({user_alias_expr}, '') AS user_alias_name,
                    COALESCE(NULLIF({user_alias_expr}, ''), user_partner.name, '') AS user_display_name,
                    COALESCE({user_sipa_expr}, '') AS user_sipa_no,
                    {user_signature_expr} AS user_signature,

                    COALESCE(user_position.name::text, '') AS user_position_name,
                    COALESCE({user_position_alias_expr}, '') AS user_position_alias_name,

                    COALESCE(
                        NULLIF({user_position_alias_expr}, ''),
                        NULLIF(user_position.name::text, ''),
                        NULLIF(dept.name, ''),
                        ''
                    ) AS user_position_display_name,

                    COALESCE(
                        NULLIF({user_position_alias_expr}, ''),
                        NULLIF(user_position.name::text, ''),
                        NULLIF(dept.name, ''),
                        ''
                    ) AS user_position,

                    {department_id_expr} AS department_id,
                    COALESCE(dept.name, '') AS department_name,

                    COALESCE(r.notes, '') AS notes,

                    COALESCE(r.total_price, 0.0) AS total_price,
                    COALESCE(r.total_discount, 0.0) AS total_discount,
                    COALESCE(r.total_taxes, 0.0) AS total_taxes,
                    COALESCE(r.total_netprice, 0.0) AS total_netprice,

                    eo.id AS order_id,
                    COALESCE(eo.order_no, '') AS order_no,
                    COALESCE(eo.order_purchase_no, '') AS order_purchase_no

                FROM eproc_receipt r
                LEFT JOIN res_company c
                    ON c.id = r.company_id
                LEFT JOIN res_partner rp
                    ON rp.id = r.supplier_id
                LEFT JOIN res_users ru
                    ON ru.id = r.user_id
                LEFT JOIN res_partner user_partner
                    ON user_partner.id = ru.partner_id
                LEFT JOIN res_position user_position
                    ON user_position.id = {user_position_id_expr}
                LEFT JOIN hr_department dept
                    ON dept.id = {department_id_expr}
                LEFT JOIN eproc_order eo
                    ON eo.id = r.order_id
                WHERE COALESCE({active_expr}, TRUE) = TRUE
            )
        """.format(
            active_expr=active_expr,
            department_id_expr=department_id_expr,
            user_alias_expr=user_alias_expr,
            user_sipa_expr=user_sipa_expr,
            user_signature_expr=user_signature_expr,
            user_position_id_expr=user_position_id_expr,
            user_position_alias_expr=user_position_alias_expr,
        ))


class EprocReportReceiptLineView(models.Model):
    _name = 'eproc.report.receipt.line.view'
    _description = 'Jasper SQL View - Eproc Receipt Line'
    _auto = False
    _table = 'view_eproc_receipt_line'

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW view_eproc_receipt_line AS (
                SELECT
                    l.id AS id,
                    l.id AS receipt_line_id,
                    l.receipt_id AS receipt_id,
                    l.company_id AS company_id,

                    l.sequence AS sequence,

                    l.product_tmpl_id AS product_tmpl_id,
                    COALESCE(pt.default_code, '') AS product_code,
                    COALESCE(pt.name->>'en_US', pt.name->>'id_ID', pt.name::text, '') AS product_name,
                    COALESCE(l.name, '') AS name,

                    l.product_categ_id AS product_categ_id,
                    COALESCE(pc.name, '') AS product_categ_name,

                    l.pack_id AS pack_id,
                    COALESCE(pack.name::text, '') AS pack_name,

                    COALESCE(l.pack_order, 0.0) AS pack_order,
                    COALESCE(l.pack_processed, 0.0) AS pack_processed,
                    COALESCE(l.pack_available, 0.0) AS pack_available,
                    COALESCE(l.pack_receipt, 0.0) AS pack_receipt,

                    COALESCE(ol.pack_qty, req_l.pack_qty, l.pack_receipt, 0.0) AS pack_qty,

                    COALESCE(l.pack_price, 0.0) AS pack_price,
                    COALESCE(l.pack_netprice, 0.0) AS pack_netprice,
                    COALESCE(l.pack_rate, 1.0) AS pack_rate,

                    l.uom_id AS uom_id,
                    COALESCE(uom.name->>'en_US', uom.name->>'id_ID', uom.name::text, '') AS uom_name,

                    COALESCE(l.uom_order, 0.0) AS uom_order,
                    COALESCE(l.uom_processed, 0.0) AS uom_processed,
                    COALESCE(l.uom_available, 0.0) AS uom_available,
                    COALESCE(l.uom_receipt, 0.0) AS uom_receipt,
                    COALESCE(l.uom_price, 0.0) AS uom_price,
                    COALESCE(l.uom_netprice, 0.0) AS uom_netprice,

                    COALESCE(l.disc_rate, 0.0) AS disc_rate,

                    COALESCE(tax.tax_list, '') AS tax_list,

                    COALESCE(l.total_price, 0.0) AS total_price,
                    COALESCE(l.total_discount, 0.0) AS total_discount,
                    COALESCE(l.total_taxes, 0.0) AS total_taxes,
                    COALESCE(l.total_netprice, 0.0) AS total_netprice,

                    l.analytic_id AS analytic_id,
                    l.orderpoint_log_id AS orderpoint_log_id,
                    l.order_line_id AS order_line_id,
                    l.request_line_id AS request_line_id,
                    l.move_id AS move_id,

                    COALESCE(l.is_return, FALSE) AS is_return,

                    COALESCE(l.receipt_no, '') AS receipt_no,
                    l.receipt_date AS receipt_date,
                    COALESCE(l.receipt_valid_no, '') AS receipt_valid_no,
                    l.receipt_valid_date AS receipt_valid_date,
                    COALESCE(l.receipt_origin, '') AS receipt_origin,
                    COALESCE(l.receipt_ref, '') AS receipt_ref,
                    COALESCE(l.receipt_type, '') AS receipt_type,

                    l.purchase_type_id AS purchase_type_id,
                    l.supplier_id AS supplier_id,
                    l.user_id AS user_id,

                    COALESCE(l.state_parent, '') AS state_parent,
                    COALESCE(l.state, '') AS state,

                    TRUE AS active

                FROM eproc_receipt_line l
                LEFT JOIN product_template pt
                    ON pt.id = l.product_tmpl_id
                LEFT JOIN product_category pc
                    ON pc.id = l.product_categ_id
                LEFT JOIN eproc_pack pack
                    ON pack.id = l.pack_id
                LEFT JOIN uom_uom uom
                    ON uom.id = l.uom_id
                LEFT JOIN eproc_order_line ol
                    ON ol.id = l.order_line_id
                LEFT JOIN eproc_request_line req_l
                    ON req_l.id = l.request_line_id
                LEFT JOIN LATERAL (
                    SELECT
                        STRING_AGG(COALESCE(et.name, ''), ', ' ORDER BY et.name) AS tax_list
                    FROM eproc_taxes_rel rel
                    LEFT JOIN eproc_taxes et
                        ON et.id = rel.tax_id
                    WHERE rel.receipt_line_id = l.id
                ) tax ON TRUE
            )
        """)
        
def _db_column_exists(env, table_name, column_name):
    env.cr.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
              AND column_name = %s
        )
    """, (table_name, column_name))
    return bool(env.cr.fetchone()[0])

def _db_col(env, table_name, alias, column_name, fallback_sql):
    if _db_column_exists(env, table_name, column_name):
        return "%s.%s" % (alias, column_name)
    return fallback_sql

class EprocReportRequestView(models.Model):
    _name = 'eproc.report.request.view'
    _description = 'E-Proc Request Report View'
    _auto = False
    _table = 'view_eproc_request'

    request_id = fields.Many2one('eproc.request', string='Request', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    company_name = fields.Char(string='Company Name', readonly=True)
    company_parent = fields.Char(string='Company Parent', readonly=True)
    request_no = fields.Char(string='Request No.', readonly=True)
    request_revise = fields.Integer(string='Request Revise', readonly=True)
    request_date = fields.Datetime(string='Request Date', readonly=True)
    request_valid_date = fields.Datetime(string='Request Valid Date', readonly=True)
    request_ref = fields.Char(string='Reference', readonly=True)
    request_type = fields.Selection([
        ('normal', 'Normal'),
        ('repeat', 'Repeat Order'),
        ('auto', 'Auto-PR'),
    ], string='Request Type', readonly=True)
    request_type_name = fields.Char(string='Request Type Name', readonly=True)
    supplier_id = fields.Many2one('res.partner', string='Supplier', readonly=True)
    supplier_code = fields.Char(string='Supplier Code', readonly=True)
    supplier_name = fields.Char(string='Supplier Name', readonly=True)
    supplier_pic = fields.Char(string='Supplier PIC', readonly=True)
    supplier_pic_div = fields.Char(string='Supplier PIC Division', readonly=True)
    city = fields.Char(string='City', readonly=True)
    zip = fields.Char(string='Zip', readonly=True)
    street = fields.Char(string='Street', readonly=True)
    phone = fields.Char(string='Phone', readonly=True)
    email = fields.Char(string='Email', readonly=True)
    fax = fields.Char(string='Fax', readonly=True)
    purchase_type_id = fields.Many2one('eproc.type', string='Procurement Type', readonly=True)
    purchase_type_name = fields.Char(string='Procurement Type Name', readonly=True)
    approval_type_id = fields.Many2one('eproc.approval.type', string='Approval Type', readonly=True)
    approval_type_name = fields.Char(string='Approval Type Name', readonly=True)
    user_id = fields.Many2one('res.users', string='Responsible', readonly=True)
    user_name = fields.Char(string='Responsible Name', readonly=True)
    user_alias = fields.Char(string='User Alias', readonly=True)
    user_signature = fields.Binary(string='User Signature', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    department_name = fields.Char(string='Department Name', readonly=True)
    notes = fields.Text(string='Notes', readonly=True)
    cancel_reason = fields.Text(string='Cancel Reason', readonly=True)
    cancel_datetime = fields.Datetime(string='Cancel Datetime', readonly=True)
    total_price = fields.Float(string='Total Price', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approval', 'Approval'),
        ('ready', 'Ready to Procure'),
        ('partial', 'Partial/Fully RFQ Created'),
        ('done', 'Completed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], string='State', readonly=True)
    state_name = fields.Char(string='State Name', readonly=True)
    active = fields.Boolean(string='Active', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    a.id AS id,
                    a.id AS request_id,
                    a.company_id,
                    b.name AS company_name,
                    c.name AS company_parent,
                    a.request_no,
                    a.request_revise,
                    a.request_date,
                    a.request_valid_date,
                    a.request_ref,
                    a.request_type,
                    (CASE a.request_type
                        WHEN 'normal' THEN 'Normal'
                        WHEN 'repeat' THEN 'Repeat Order'
                        WHEN 'auto' THEN 'Auto-PR'
                    END) AS request_type_name,
                    a.supplier_id,
                    d.vendor_code AS supplier_code,
                    d.name AS supplier_name,
                    d.customer_pic AS supplier_pic,
                    d.customer_pic_div AS supplier_pic_div,
                    d.city,
                    d.zip,
                    d.street,
                    d.phone,
                    d.email,
                    d.fax,
                    a.purchase_type_id,
                    e.name AS purchase_type_name,
                    a.approval_type_id,
                    f.name AS approval_type_name,
                    a.user_id,
                    h.name AS user_name,
                    g.user_signature AS user_signature,
                    g.alias_name AS user_alias,
                    a.department_id,
                    i.name AS department_name,
                    a.notes,
                    a.cancel_reason,
                    a.cancel_datetime,
                    a.total_price,
                    a.state,
                    (CASE a.state
                        WHEN 'draft' THEN 'Draft'
                        WHEN 'approval' THEN 'Approval'
                        WHEN 'ready' THEN 'Ready to Procure'
                        WHEN 'partial' THEN 'Partial/Fully RFQ Created'
                        WHEN 'done' THEN 'Completed'
                        WHEN 'rejected' THEN 'Rejected'
                        WHEN 'cancelled' THEN 'Cancelled'
                    END) AS state_name,
                    a.active
                FROM eproc_request a
                LEFT JOIN res_company b ON b.id = a.company_id
                LEFT JOIN res_company c ON c.id = b.parent_id
                LEFT JOIN res_partner d ON d.id = a.supplier_id
                LEFT JOIN eproc_type e ON e.id = a.purchase_type_id
                LEFT JOIN eproc_approval_type f ON f.id = a.approval_type_id
                LEFT JOIN res_users g ON g.id = a.user_id
                LEFT JOIN res_partner h ON h.id = g.partner_id
                LEFT JOIN hr_department i ON i.id = a.department_id
            )
        """ % self._table)


class EprocReportRequestLineView(models.Model):
    _name = 'eproc.report.request.line.view'
    _description = 'E-Proc Request Line Report View'
    _auto = False
    _table = 'view_eproc_request_line'

    request_line_id = fields.Many2one('eproc.request.line', string='Request Line', readonly=True)
    request_id = fields.Many2one('eproc.request', string='Request', readonly=True)
    sequence = fields.Integer(string='Sno', readonly=True)
    product_tmpl_id = fields.Many2one('product.template', string='Product', readonly=True)
    product_code = fields.Char(string='Product Code', readonly=True)
    product_name = fields.Char(string='Product Name', readonly=True)
    name = fields.Char(string='Description', readonly=True)
    uom_qty_on_hand = fields.Float(string='UoM Qty On Hand', readonly=True)
    uom_qty_min = fields.Float(string='UoM Qty Min', readonly=True)
    uom_qty_max = fields.Float(string='UoM Qty Max', readonly=True)
    uom_qty_suggested = fields.Float(string='UoM Qty Suggested', readonly=True)
    pack_id = fields.Many2one('eproc.pack', string='Pack Type', readonly=True)
    pack_name = fields.Char(string='Pack Name', readonly=True)
    pack_qty = fields.Float(string='Pack Qty', readonly=True)
    pack_qty_processed = fields.Float(string='Pack Qty Processed', readonly=True)
    pack_price = fields.Float(string='Pack Price', readonly=True)
    pack_rate = fields.Float(string='Pack Rate', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', readonly=True)
    uom_name = fields.Char(string='UoM Name', readonly=True)
    uom_qty = fields.Float(string='UoM Qty', readonly=True)
    uom_qty_processed = fields.Float(string='UoM Qty Processed', readonly=True)
    uom_price = fields.Float(string='UoM Price', readonly=True)
    total_price = fields.Float(string='Total Price', readonly=True)
    analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account', readonly=True)
    analytic_code = fields.Char(string='Analytic Code', readonly=True)
    analytic_name = fields.Char(string='Analytic Name', readonly=True)
    orderpoint_log_id = fields.Many2one('eproc.orderpoint.log', string='Suggestion Log', readonly=True)
    usage_in_7 = fields.Float(string='Usage in 7 Day(s)', readonly=True)
    usage_in_14 = fields.Float(string='Usage in 14 Day(s)', readonly=True)
    usage_in_30 = fields.Float(string='Usage in 30 Day(s)', readonly=True)
    usage_in_90 = fields.Float(string='Usage in 90 Day(s)', readonly=True)
    move_type = fields.Char(string='Moving Type', readonly=True)
    days_safety = fields.Float(string='Days Safety', readonly=True)
    days_inventory = fields.Float(string='Days of Inventory', readonly=True)
    days_out = fields.Float(string='Days of Stock Out', readonly=True)
    days_average = fields.Float(string='Days Average', readonly=True)
    qty_on_hand = fields.Float(string='Qty On Hand', readonly=True)
    qty_max_day = fields.Float(string='Qty Max Day', readonly=True)
    qty_min_order = fields.Float(string='Qty Min Order', readonly=True)
    qty_average = fields.Float(string='Qty Average', readonly=True)
    qty_safety = fields.Float(string='Qty Safety', readonly=True)
    qty_maximum = fields.Float(string='Qty Maximum', readonly=True)
    qty_suggested = fields.Float(string='Qty Suggested', readonly=True)
    request_no = fields.Char(string='Request No', readonly=True)
    request_revise = fields.Integer(string='Request Revise', readonly=True)
    request_date = fields.Datetime(string='Request Date', readonly=True)
    request_valid_date = fields.Datetime(string='Request Valid Date', readonly=True)
    request_ref = fields.Char(string='Request Ref', readonly=True)
    request_type = fields.Char(string='Request Type', readonly=True)
    request_amount = fields.Float(string='Request Total Price', readonly=True)
    purchase_type_id = fields.Many2one('eproc.type', string='Procurement Type', readonly=True)
    approval_type_id = fields.Many2one('eproc.approval.type', string='Approval Type', readonly=True)
    user_id = fields.Many2one('res.users', string='Responsible', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    state_parent = fields.Char(string='State Parent', readonly=True)
    state = fields.Char(string='State', readonly=True)
    state_name = fields.Char(string='State Name', readonly=True)
    state_aging = fields.Char(string='Aging Status', readonly=True)
    state_aging_name = fields.Char(string='Aging Status Name', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""CREATE OR REPLACE VIEW %s AS (
                SELECT
                    a.id AS id,
                    a.id AS request_line_id,
                    a.request_id,
                    a.sequence,
                    a.product_tmpl_id,
                    pt.default_code AS product_code,
                    pt.name AS product_name,
                    a.name,
                    a.uom_qty_on_hand,
                    a.uom_qty_min,
                    a.uom_qty_max,
                    a.uom_qty_suggested,
                    a.pack_id,
                    pp.name AS pack_name,
                    a.pack_qty,
                    a.pack_qty_processed,
                    a.pack_price,
                    a.pack_rate,
                    a.uom_id,
                    pu.name AS uom_name,
                    a.uom_qty,
                    a.uom_qty_processed,
                    a.uom_price,
                    a.total_price,
                    a.analytic_id,
                    aa.code AS analytic_code,
                    aa.name AS analytic_name,
                    a.orderpoint_log_id,
                    c.usage_in_7,
                    c.usage_in_14,
                    c.usage_in_30,
                    c.usage_in_90,
                    c.move_type,
                    c.days_safety,
                    c.days_inventory,
                    c.days_out,
                    c.days_average,
                    c.qty_on_hand,
                    c.qty_max_day,
                    c.qty_min_order,
                    c.qty_average,
                    c.qty_safety,
                    c.qty_maximum,
                    c.qty_suggested,
                    b.request_no,
                    b.request_revise,
                    b.request_date,
                    b.request_valid_date,
                    b.request_ref,
                    b.request_type,
                    a.request_amount,
                    b.purchase_type_id,
                    b.approval_type_id,
                    b.user_id,
                    b.department_id,
                    b.company_id,
                    b.state AS state_parent,
                    a.state,
                    (CASE a.state
                        WHEN 'draft' THEN 'Draft'
                        WHEN 'ready' THEN 'Ready to Procure'
                        WHEN 'partial' THEN 'Partial'
                        WHEN 'done' THEN 'Completed'
                        WHEN 'closed' THEN 'Closed'
                        WHEN 'cancelled' THEN 'Cancelled'
                    END) AS state_name,
                    a.state_aging,
                    (CASE a.state_aging
                        WHEN 'draft' THEN 'Draft'
                        WHEN 'ready' THEN 'Ready to Procure'
                        WHEN 'partial' THEN 'Partial'
                        WHEN 'done' THEN 'Completed'
                        WHEN 'closed' THEN 'Closed'
                        WHEN 'cancelled' THEN 'Cancelled'
                        WHEN 'need_approval' THEN 'Stuck Approval ( > 2 Days)'
                        WHEN 'need_realize' THEN 'Need Realize to RFQ'
                        WHEN 'overdue_receipt' THEN 'PO Delivery Overdue'
                    END) AS state_aging_name
                FROM eproc_request_line a
                INNER JOIN eproc_request b ON b.id = a.request_id
                LEFT JOIN eproc_orderpoint_log c ON c.id = a.orderpoint_log_id
                LEFT JOIN product_template pt ON pt.id = a.product_tmpl_id
                LEFT JOIN eproc_pack pp ON pp.id = a.pack_id
                LEFT JOIN uom_uom pu ON pu.id = a.uom_id
                LEFT JOIN account_analytic_account aa ON aa.id = a.analytic_id
            )
        """ % self._table)


class EprocReportApprovalLogView(models.Model):
    _name = 'eproc.report.approval.log.view'
    _description = 'E-Proc Approval Log Report View'
    _auto = False
    _table = 'view_eproc_approval_log'

    log_id = fields.Many2one('eproc.approval.log', string='Approval Log', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    order_id = fields.Many2one('eproc.order', string='Order No', readonly=True)
    order_no = fields.Char(string='Order No', readonly=True)
    order_purchase_no = fields.Char(string='Purchase No', readonly=True)
    receipt_id = fields.Many2one('eproc.receipt', string='Receiving No', readonly=True)
    receipt_no = fields.Char(string='Receiving No', readonly=True)
    receipt_valid_no = fields.Char(string='Receiving Valid No', readonly=True)
    request_id = fields.Many2one('eproc.request', string='Request No', readonly=True)
    request_no = fields.Char(string='Request No', readonly=True)
    agreement_id = fields.Many2one('eproc.agreement', string='Agreement', readonly=True)
    agreement_no = fields.Char(string='Agreement No', readonly=True)
    approval_type_id = fields.Many2one('eproc.approval.type', string='Approval Type', readonly=True)
    approval_type_name = fields.Char(string='Approval Type Name', readonly=True)
    approval_rule_id = fields.Many2one('eproc.approval.rule', string='Approval Rule', readonly=True)
    sequence = fields.Integer(string='Sno', readonly=True)
    type = fields.Selection([
        ('check', 'Checking'),
        ('approve', 'Approval'),
        ('verify', 'Verifying'),
        ('review', 'Review'),
    ], string='Type', readonly=True)
    type_name = fields.Char(string='Type Name', readonly=True)
    show = fields.Boolean(string='Show', readonly=True)
    position_id = fields.Many2one('res.position', string='Position', readonly=True)
    position_name = fields.Char(string='Position Name', readonly=True)
    position_alias = fields.Char(string='Position Alias', readonly=True)
    user_id = fields.Many2one('res.users', string='Responsible', readonly=True)
    user_name = fields.Char(string='Responsible Name', readonly=True)
    action_user_id = fields.Many2one('res.users', string='Action User', readonly=True)
    action_user_name = fields.Char(string='Action User Name', readonly=True)
    action_user_alias = fields.Char(string='Action User Alias', readonly=True)
    action_user_sipa = fields.Char(string='Action User SIPA', readonly=True)
    action_user_signature = fields.Binary(string='Action User Signature', readonly=True)
    approval_date = fields.Datetime(string='Approval Date', readonly=True)
    amount_snapshot = fields.Float(string='Amount Snapshot', readonly=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('skipped', 'Skipped'),
    ], string='State', readonly=True)
    state_name = fields.Char(string='State Name', readonly=True)
    active = fields.Boolean(string='Active', readonly=True)

    def init(self):
        action_user_alias_expr = _db_col(
            self.env, 'res_users', 'ru', 'alias_name', "NULL::varchar"
        )
        action_user_sipa_expr = _db_col(
            self.env, 'res_users', 'ru', 'sipa_no', "''::varchar"
        )
        position_alias_expr = _db_col(
            self.env, 'res_position', 'rp', 'alias_name', "NULL::varchar"
        )
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    a.id AS id,
                    a.id AS log_id,
                    COALESCE(b.company_id, c.company_id, d.company_id, e.company_id) AS company_id,
                    a.order_id,
                    d.order_no,
                    d.order_purchase_no,
                    a.receipt_id,
                    e.receipt_no,
                    e.receipt_valid_no,
                    a.request_id,
                    c.request_no,
                    a.agreement_id,
                    b.code AS agreement_no,
                    a.approval_type_id,
                    f.name AS approval_type_name,
                    a.approval_rule_id,
                    a.sequence,
                    a.type,
                    (CASE a.type
                        WHEN 'check' THEN 'Checking'
                        WHEN 'approve' THEN 'Approval'
                        WHEN 'verify' THEN 'Verifying'
                        WHEN 'review' THEN 'Review'
                    END) AS type_name,
                    a.show,
                    a.position_id,
                    rp.name AS position_name,
                    COALESCE(NULLIF({position_alias_expr}, ''), rp.name, '') AS position_alias,
                    usr.user_id,
                    usr.user_name,
                    a.action_user_id,
                    rup.name AS action_user_name,
                    COALESCE(NULLIF({action_user_alias_expr}, ''), rup.name, '') AS action_user_alias,
                    COALESCE({action_user_sipa_expr}, '') AS action_user_sipa,
                    ru.user_signature AS action_user_signature,
                    a.approval_date,
                    a.amount_snapshot,
                    a.state,
                    (CASE a.state
                        WHEN 'pending' THEN 'Pending'
                        WHEN 'approved' THEN 'Approved'
                        WHEN 'rejected' THEN 'Rejected'
                        WHEN 'cancelled' THEN 'Cancelled'
                        WHEN 'skipped' THEN 'Skipped'
                    END) AS state_name,
                    a.active
                FROM eproc_approval_log a
                LEFT JOIN eproc_agreement b ON b.id = a.agreement_id
                LEFT JOIN eproc_request c ON c.id = a.request_id
                LEFT JOIN eproc_order d ON d.id = a.order_id
                LEFT JOIN eproc_receipt e ON e.id = a.receipt_id
                LEFT JOIN eproc_approval_type f ON f.id = a.approval_type_id
                LEFT JOIN eproc_approval_rule g ON g.id = a.approval_rule_id
                LEFT JOIN res_position rp ON rp.id = a.position_id
                LEFT JOIN res_users ru ON ru.id = a.action_user_id
                LEFT JOIN res_partner rup ON rup.id = ru.partner_id
                LEFT JOIN LATERAL (
                    SELECT
                        t.id AS user_id,
                        t2.name AS user_name,
                        t.user_signature AS user_signature
                    FROM res_users t
                    INNER JOIN res_partner t2 ON t2.id = t.partner_id
                    WHERE t.position_id = a.position_id
                        AND t.active = TRUE
                    LIMIT 1
                ) usr ON 1 = 1
            )
        """.format(
            table=self._table,
            action_user_alias_expr=action_user_alias_expr,
            action_user_sipa_expr=action_user_sipa_expr,
            position_alias_expr=position_alias_expr,
        ))


class ReceivableInvoiceReportView(models.Model):
    _name = 'receivable.invoice.report.view'
    _description = 'AR Tenant Invoice Report View'
    _auto = False
    _table = 'view_receivable_invoice'

    invoice_id = fields.Many2one('receivable.invoice', string='Invoice', readonly=True)
    invoice_no = fields.Char(string='Invoice No', readonly=True)
    invoice_date = fields.Date(string='Invoice Date', readonly=True)
    invoice_duedate = fields.Date(string='Invoice Due Date', readonly=True)
    invoice_ref = fields.Char(string='Invoice Ref.', readonly=True)
    invoice_origin = fields.Char(string='Invoice Origin', readonly=True)
    invoice_type = fields.Selection([
        ('OUT_INVOICE', 'TENANT INVOICE'),
        ('OUT_REFUND', 'REFUND TENANT'),
    ], string='Invoice Type', readonly=True)
    customer_term_day = fields.Integer(string='Customer T.O.P', readonly=True)
    invoice_tax_type = fields.Selection([
        ('NO_TAX', 'No Tax'),
        ('ART_21', 'Art 21'),
        ('ART_22', 'Art 22'),
        ('ART_23', 'Art 23'),
        ('ART_4_2', 'Art 4(2)'),
        ('VAT_11', 'VAT 11'),
    ], string='Tax Type', readonly=True)
    invoice_amount = fields.Float(string='Total Amount', readonly=True)
    invoice_tax_amount = fields.Float(string='Tax Amount', readonly=True)
    invoice_amount_net = fields.Float(string='Total Net', readonly=True)
    invoice_amount_words = fields.Text(string='Amount in Words', readonly=True)
    invoice_receipt = fields.Float(string='Total Receipt', readonly=True)
    invoice_refund = fields.Float(string='Total Refund', readonly=True)
    invoice_balance = fields.Float(string='Invoice Balance', readonly=True)
    notes = fields.Text(string='Notes', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Confirmed'),
        ('cancel', 'Cancelled'),
    ], string='State', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    company_name = fields.Char(string='Company Name', readonly=True)
    company_parent_id = fields.Many2one('res.company', string='Company Parent', readonly=True)
    company_parent_name = fields.Char(string='Company Parent Name', readonly=True)
    company_cl_beneficiary = fields.Char(string='Company CL Beneficiary', readonly=True)
    company_cl_account = fields.Char(string='Company CL Account Number', readonly=True)
    company_cl_bank_name = fields.Char(string='Company CL Bank Name', readonly=True)
    company_cl_pic = fields.Char(string='Company CL PIC', readonly=True)
    company_cl_pic_email = fields.Char(string='Company CL PIC Email', readonly=True)
    company_cl_ttd = fields.Char(string='Company CL TTD', readonly=True)
    company_cl_dept = fields.Char(string='Company CL Department', readonly=True)
    customer_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    customer_code = fields.Char(string='Customer Code', readonly=True)
    customer_name = fields.Char(string='Customer Name', readonly=True)
    customer_street = fields.Char(string='Customer Street', readonly=True)
    customer_street2 = fields.Char(string='Customer Street 2', readonly=True)
    customer_street3 = fields.Char(string='Customer Street 3', readonly=True)
    customer_city = fields.Char(string='Customer City', readonly=True)
    customer_zip = fields.Char(string='Customer Zip', readonly=True)
    customer_phone = fields.Char(string='Customer Phone', readonly=True)
    customer_mobile = fields.Char(string='Customer Mobile', readonly=True)
    customer_fax = fields.Char(string='Customer Fax', readonly=True)
    customer_email = fields.Char(string='Customer Email', readonly=True)
    customer_pic = fields.Char(string='Customer PIC', readonly=True)
    customer_pic_div = fields.Char(string='Customer PIC Division', readonly=True)
    customer_cl_beneficiary = fields.Char(string='Customer CL Beneficiary', readonly=True)
    customer_cl_account = fields.Char(string='Customer CL Account Number', readonly=True)
    customer_cl_bank_name = fields.Char(string='Customer CL Bank Name', readonly=True)
    customer_cl_pic = fields.Char(string='Customer CL PIC', readonly=True)
    customer_cl_pic_email = fields.Char(string='Customer CL PIC Email', readonly=True)
    customer_cl_ttd = fields.Char(string='Customer CL TTD', readonly=True)
    user_id = fields.Many2one('res.users', string='Responsible', readonly=True)
    user_name = fields.Char(string='Responsible Name', readonly=True)
    user_email = fields.Char(string='Responsible Email', readonly=True)
    user_ar_pic_phone = fields.Char(string='AR Phone', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    a.id AS id,
                    a.id AS invoice_id,
                    a.invoice_no,
                    a.invoice_date,
                    a.invoice_duedate,
                    a.invoice_ref,
                    a.invoice_origin,
                    a.invoice_type,
                    a.customer_term_day,
                    a.invoice_tax_type,
                    a.invoice_amount,
                    a.invoice_tax_amount,
                    a.invoice_amount_net,
                    a.invoice_amount_words,
                    a.invoice_receipt,
                    a.invoice_refund,
                    a.invoice_balance,
                    a.notes,
                    a.state,
                    a.company_id,
                    b.name AS company_name,
                    b.parent_id AS company_parent_id,
                    c.name AS company_parent_name,
                    b.cl_beneficiary AS company_cl_beneficiary,
                    b.cl_account AS company_cl_account,
                    b.cl_bank_name AS company_cl_bank_name,
                    b.cl_pic AS company_cl_pic,
                    b.cl_pic_email AS company_cl_pic_email,
                    b.cl_ttd AS company_cl_ttd,
                    b.cl_dept AS company_cl_dept,
                    a.customer_id,
                    d.vendor_code AS customer_code,
                    d.name AS customer_name,
                    d.street AS customer_street,
                    d.street2 AS customer_street2,
                    d.street3 AS customer_street3,
                    d.city AS customer_city,
                    d.zip AS customer_zip,
                    d.phone AS customer_phone,
                    d.mobile AS customer_mobile,
                    d.fax AS customer_fax,
                    d.email AS customer_email,
                    d.customer_pic,
                    d.customer_pic_div,
                    d.cl_beneficiary AS customer_cl_beneficiary,
                    d.cl_account AS customer_cl_account,
                    d.cl_bank_name AS customer_cl_bank_name,
                    d.cl_pic AS customer_cl_pic,
                    d.cl_pic_email AS customer_cl_pic_email,
                    d.cl_ttd AS customer_cl_ttd,
                    a.user_id,
                    f.name AS user_name,
                    f.email AS user_email,
                    e.ar_pic_phone AS user_ar_pic_phone
                FROM receivable_invoice a
                LEFT JOIN res_company b ON b.id = a.company_id
                LEFT JOIN res_company c ON c.id = b.parent_id
                LEFT JOIN res_partner d ON d.id = a.customer_id
                LEFT JOIN res_users e ON e.id = a.user_id
                LEFT JOIN res_partner f ON f.id = e.partner_id
                WHERE a.invoice_type = 'OUT_INVOICE'
            )
        """ % self._table)


class ReceivableInvoiceItemReportView(models.Model):
    _name = 'receivable.invoice.item.report.view'
    _description = 'AR Tenant Invoice Item Report View'
    _auto = False
    _table = 'view_receivable_invoice_item'

    invoice_item_id = fields.Many2one('receivable.invoice.item', string='Invoice Item', readonly=True)
    invoice_id = fields.Many2one('receivable.invoice', string='Invoice', readonly=True)
    invoice_no = fields.Char(string='Invoice No', readonly=True)
    sequence = fields.Integer(string='Sequence', readonly=True)
    name = fields.Char(string='Description', readonly=True)
    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    account_code = fields.Char(string='Account Code', readonly=True)
    account_name = fields.Char(string='Account Name', readonly=True)
    amount = fields.Float(string='Amount', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    a.id AS id,
                    a.id AS invoice_item_id,
                    a.invoice_id,
                    b.invoice_no,
                    ROW_NUMBER() OVER (
                        PARTITION BY a.invoice_id
                        ORDER BY a.id
                    )::integer AS sequence,
                    a.name,
                    a.account_id,
                    c.code AS account_code,
                    COALESCE(c.name->>'en_US', c.name->>'id_ID') AS account_name,
                    a.amount,
                    a.company_id
                FROM receivable_invoice_item a
                INNER JOIN receivable_invoice b ON b.id = a.invoice_id
                LEFT JOIN account_account c ON c.id = a.account_id
                WHERE b.invoice_type = 'OUT_INVOICE'
            )
        """ % self._table)
