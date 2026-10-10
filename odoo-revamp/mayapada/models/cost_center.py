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


class CostCenterReportWizard(models.TransientModel):
    _name = 'cost.center.report.wizard'

    def _year(orm):
        result = []
        year = 2019
        now = tools.datetime.now().year
        for loop in range(now - year):
            value = str(year + loop + 1)
            result += [(value, value)]
        return result

    def _month(orm):
        result = []
        for loop in range(12):
            month = loop + 1
            result += [(str(month), calendar.month_name[month])]
        return result

    @api.model
    def _get_user(self):
        return self.env.user.id

    @api.onchange('user_id')
    def _onchange_user_id_check(self):
        domain = {'cost_center_ids': [], 'analytic_account_ids': []}
        if self.user_id:
            domain = {'cost_center_ids': [('id', 'in', self.cost_center_user_ids.ids)], 'analytic_account_ids': [('id', 'in', self.analytic_account_user_ids.ids)], 'company_id': [('id', '=', self.env.company.id)]}
        else:
            domain = {'cost_center_ids': [], 'analytic_account_ids': []}


        return {'domain': domain}


    type_report = fields.Selection([('1', 'Cost Center Standard Report'),('2', 'Cost Center Trend Report'),('3', 'Cost Center Trend Budget')], string="Type Report", required=True, default='1')    
    type_filter = fields.Selection([('1', 'By Cost Center'),('2', 'By Analytic Account'), ('3', 'No Filter')],string="Type Filter",required=True,default='1')    
    type_period = fields.Selection([('BOTH', 'YTD & MTD'), ('PERIOD', 'PERIODE')], string="Type Period", required=True)    
    reconcile_type = fields.Selection([
        ('view_account_sales_accrual','Revenue Accrual'),
        ('view_account_sales_accrual_reversal','Revenue Accrual Reversal'),
        ('view_account_sales_bill','Revenue Bill'),
        ('view_account_sales_bill_cancel','Revenue Bill Cancel'),
        ('view_account_sales_discount','Revenue Discount'),
        ('view_account_sales_discount_cancel','Revenue Discount Cancel'),
        ('view_account_sales_cost','Sales Cost'),
        ('view_account_scrap','Scrap Cost'),
        ('view_account_service_cost','Service Cost'),
        ('view_account_referral_cost','Referral Cost')
    ], string="Reconcile Type", required=False)
    # periode = fields.Selection(_year, string="Periode", required=True)
    # month = fields.Selection(_month, string="Month", required=True)
    date_start = fields.Date(string="Date Start", required=False)
    date_end = fields.Date(string="Date End", required=False)

    company_id = fields.Many2one('res.company',string="Company",required=True)
    analytic_account_ids = fields.Many2many('account.analytic.account',string="Analytic Account",domain=[('type_analytic', '=','expense')])
    cost_center_ids = fields.Many2many('cost.center.master',string="Cost Center")
    state = fields.Selection([('draft', 'Draft'),('posted', 'Posted')], string="Journal Entries",required=True,default='posted')
    cost_center_user_ids = fields.Many2many('cost.center.master', related="user_id.cost_center_ids", string="Cost Center User")
    analytic_account_user_ids = fields.Many2many('account.analytic.account',related="user_id.analytic_ids", string="Analytic Account User")
    user_id = fields.Many2one('res.users',string="Responsible",required=True, default=_get_user)

    @api.onchange('type_report')
    def _onchange_type_report(self):
        if self.type_report == '1':
            self.type_period = 'BOTH'
        elif self.type_report == '2':
            self.type_period = 'PERIOD'
        elif self.type_report == '3':
            self.type_period = 'PERIOD' 



    # @api.multi 
    def reconcile_report(self):
        from dateutil.relativedelta import relativedelta
        from datetime import datetime

        open('/opt/odoo16/logs/cost_center_reconcile.log', 'a+').write('\n\n Start reconcile cost center report ===================')
        
        # set range period        
        if self.type_period == 'PERIOD':
            date_start = str((self.date_start).strftime('%Y-%m-%d'))
            date_end   = str((self.date_end).strftime('%Y-%m-%d'))
        elif self.type_period == 'MONTH':
            date_start = str((self.date_end).strftime('%Y-%m-%d'))[:7] + '-01'
            date_end   = str((self.date_end).strftime('%Y-%m-%d'))
        else:
            date_start = str((self.date_end).strftime('%Y-%m-%d'))[:4] + '-01-01'
            date_end = str((self.date_end).strftime('%Y-%m-%d'))
            
        
        # delete temp table
        query = """
            DELETE FROM cost_center_reconcile 
            WHERE user_id = {user_id}
        """.format(user_id = self.env.user.id)
        open('/opt/odoo16/logs/cost_center_reconcile.log', 'a+').write('\n' + query)
        self.sudo().env.cr.execute(query)

        # insert reconcile mapping to temp table
        query = """
            INSERT INTO cost_center_reconcile(
                sync_type, company_id, tglproses, 
                trans_type, direction, amount, account_label,
                account_credit_id, account_debit_id, doctor_id,
                patient_group, service_group, service_name, 
                department_name, analytic_id, user_id, cost_master_id)
            SELECT 
                a.sync_type, a.company_id, a.tglproses, 
                a.trans_type, a.direction, a.amount, a.account_label,
                a.account_credit_id, a.account_debit_id, a.doctor_id,
                a.patient_group, a.service_group, a.service_name, 
                a.department_id, a.analytic_id, {user_id} user_id,
                aac.cost_master_id
            FROM {table_name} a 
            LEFT JOIN account_analytic_account aac ON aac.id=a.analytic_id
            WHERE a.company_id = {company_id} 
                AND a.tglproses >= '{date_start}'
                AND a.tglproses <= '{date_end}'
        """.format(
            table_name=self.reconcile_type, 
            company_id=self.company_id.id, 
            date_start=date_start, 
            date_end=date_end,
            user_id=self.env.user.id)
        open('/opt/odoo16/logs/cost_center_reconcile.log', 'a+').write('\n' + query)
        self.sudo().env.cr.execute(query)

        # show action windows
        type_report = dict(self.sudo().env['cost.center.report.wizard']._fields['type_report'].selection)
        for key, value in type_report.items():
            action = {}
            action['target'] = 'current'
            action['domain'] = "[('user_id', '=', %s)]" % (self.env.user.id)
            action['type'] = 'ir.actions.act_window'
            action['view_mode'] = 'tree,form,pivot'
            action['view_type'] = 'form'
            action['res_model'] = 'cost.center.reconcile'
            action['name'] = 'Cost Center Reconcile'
            action['views'] = [(self.sudo().env.ref('mayapada.view_cost_center_reconcile_pivot').id, 'pivot'),(False, 'form'), (False, 'tree')]
            # open('/opt/odoo16/logs/cost_center_reconcile.log', 'a+').write('\n' + str(action).encode('utf-8'))
            return action




    # @api.multi 
    def generate_report(self):
        from dateutil.relativedelta import relativedelta
        from datetime import datetime, timedelta

        open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n Start debug cost center report ===================')
        def enumerate_month_dates(start_date, end_date):
            current = start_date
            while current <= end_date:
                if current.month >= 12:
                    next = datetime.date(current.year + 1, 1, 1)
                else:
                    next = datetime.date(current.year, current.month + 1, 1)
                last = min(next - timedelta(1), end_date)
                yield current.strftime('%Y-%m-%d'), last.strftime('%Y-%m-%d')
                current = next

        # delete temporary table based on user_id
        query = """
            DELETE FROM cost_center_report 
            WHERE user_id = {user_id}
        """ . format(user_id = self.env.user.id)
        open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n' + query)
        self.sudo().env.cr.execute(query)


        # specific filter based on analytic_id OR cost_center_id 
        account_ids = False
        
        # based on cost center           
        if self.type_filter == '1' and len(self.cost_center_ids) > 1:
            account_ids = """and ccm.id in {}""".format(tuple(self.cost_center_ids.ids))
        if self.type_filter == '1' and len(self.cost_center_ids) <= 1:
            account_ids = """and ccm.id = {}""".format(self.cost_center_ids.id)

        # based on analytic_account
        if self.type_filter == '2' and len(self.analytic_account_ids) > 1:
            account_ids = """and aac.id in {}""".format(tuple(self.analytic_account_ids.ids))
        if self.type_filter == '2' and len(self.analytic_account_ids) <= 1:
            account_ids = """and aac.id = {}""".format(self.analytic_account_ids.id)

        # set range period        
        if self.type_period == 'PERIOD':
            per_start_date = str((self.date_start).strftime('%Y-%m-%d'))
            per_end_date   = str((self.date_end).strftime('%Y-%m-%d'))
            per_start_date_ly = str((datetime.strptime(per_start_date, '%Y-%m-%d') - relativedelta(years=1)).strftime("%Y-%m-%d"))
            per_end_date_ly   = str((datetime.strptime(per_end_date, '%Y-%m-%d') - relativedelta(years=1)).strftime("%Y-%m-%d"))
        # set YTD & MTD period
        else:
            ytd_start_date = str((self.date_end).strftime('%Y-%m-%d'))[:4] + '-01-01'
            ytd_end_date = str((self.date_end).strftime('%Y-%m-%d'))
            ytd_start_date_ly = str((datetime.strptime(ytd_start_date, '%Y-%m-%d') - relativedelta(years=1)).strftime("%Y-%m-%d"))
            ytd_end_date_ly   = str((datetime.strptime(ytd_end_date, '%Y-%m-%d') - relativedelta(years=1)).strftime("%Y-%m-%d"))

            mtd_start_date = str((self.date_end).strftime('%Y-%m-%d'))[:7] + '-01'
            mtd_end_date = str((self.date_end).strftime('%Y-%m-%d'))
            mtd_start_date_ly = str((datetime.strptime(mtd_start_date, '%Y-%m-%d') - relativedelta(years=1)).strftime("%Y-%m-%d"))
            mtd_end_date_ly = str((datetime.strptime(mtd_end_date, '%Y-%m-%d') - relativedelta(years=1)).strftime("%Y-%m-%d"))


        # Detail report
        
            
        if self.company_id.company_corporate_type != 'main':

            # Standard Report
            if self.type_report == '1':

                

                # YTD generate 
                if self.type_period in['BOTH']:

                    query_delete = """
                            DELETE FROM cost_center_sum_account
                            where user_id = {user_id}
                        """.format(user_id = self.env.user.id)
                    self.sudo().env.cr.execute(query_delete)


                    query_insert_sum_account_ytd = """
                        insert into cost_center_sum_account (user_id, balance, account_id, analytic_account_id, journal_id, date)
                        select {user_id} AS user_id, sum(a.balance) balance, a.account_id, a.analytic_account_id, a.journal_id, a.date
                        from account_move_line a
                        left join account_move am on am.id = a.move_id
                        where a.account_id is not null 
                        and a.analytic_account_id is not null 
                        and am.state = '{state}'
                        AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                        AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                        and a.company_id = {company_id}
                        group by a.account_id, a.analytic_account_id, a.journal_id, a.date

                    """.format(
                            user_id = self.env.user.id,
                            type_report = self.type_report,
                            type_date = 'YTD',
                            company_id = self.company_id.id,
                            state = self.state,
                            start_date = ytd_start_date,
                            end_date = ytd_end_date,
                            no_detail = "<> 'no_detail' ",
                            filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                            )
                    self.sudo().env.cr.execute(query_insert_sum_account_ytd)

                    # YTD actual 
                    query_actual_ytd = """
                    INSERT INTO cost_center_report (
                        company_id, move_number, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        cc_dimension_name, budget_id) 
                    SELECT * 
                    FROM (
            SELECT 
                            {company_id} company_id,
                            'tes null' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            null account_id, 
                            null analytic_id, 
                            null parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            0 last_balance, 
                            0 last_variance,
                            null department_id, null head_id,
                            '{end_date}' date,
                            null cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
            WHERE ccdl.company_id = {company_id}

            UNION ALL 

                        SELECT 
                            aac.company_id,
                            'tes1' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0) * -1) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0) * -1) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id} 
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes2' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (-1*a.balance) balance, 
                            0 budget_amount, 
                            (-1*a.balance) variance,
                            0 last_balance, 
                            (-1*a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes3' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0) * -1) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0) * -1) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALL
                        -- ---- tesssssssssss
                        -- SELECT 
                        --     aac.company_id,
                        --     'tes3' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                        --     0 budget_amount, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) variance,
                        --     0 last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '-1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes01' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (-1*a.balance) balance, 
                            0 budget_amount, 
                            (-1*a.balance) variance,
                            0 last_balance, 
                            (-1*a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes111' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0)) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0)) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes112' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (a.balance) balance, 
                            0 budget_amount, 
                            (a.balance) variance,
                            0 last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes113' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0)) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0)) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}

                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALL
                        -- ---tessssssssssssss
                        -- SELECT 
                        --     aac.company_id,
                        --     'tes113' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     SUM(COALESCE(ccsa.balance,0)) balance, 
                        --     0 budget_amount, 
                        --     SUM(COALESCE(ccsa.balance,0)) variance,
                        --     0 last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes02' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (a.balance) balance, 
                            0 budget_amount, 
                            (a.balance) variance,
                            0 last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}


                    ) AS a 
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'YTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = ytd_start_date,
                        end_date = ytd_end_date,
                        no_detail = "<> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n CC PL YTD Actual.')
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_actual_ytd))

                    self.sudo().env.cr.execute(query_actual_ytd)

                    query_delete = """
                        DELETE FROM cost_center_sum_account
                        where user_id = {user_id}
                    """.format(user_id = self.env.user.id)
                    self.sudo().env.cr.execute(query_delete)

                    query_insert_sum_account_ytd_ly = """
                        insert into cost_center_sum_account (user_id, balance, account_id, analytic_account_id, journal_id, date)
                        select {user_id} AS user_id, sum(a.balance) balance, a.account_id, a.analytic_account_id, a.journal_id, a.date
                        from account_move_line a
                        left join account_move am on am.id = a.move_id
                        where a.account_id is not null 
                        and a.analytic_account_id is not null 
                        and am.state = '{state}'
                        AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                        AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                        and a.company_id = {company_id}
                        group by a.account_id, a.analytic_account_id, a.journal_id, a.date

                    """.format(
                            user_id = self.env.user.id,
                            type_report = self.type_report,
                            type_date = 'YTD',
                            company_id = self.company_id.id,
                            state = self.state,
                            start_date = ytd_start_date_ly,
                            end_date = ytd_end_date_ly,
                            end_date_ly = ytd_end_date,
                            no_detail = "<> 'no_detail' ",
                            filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                            )
                    self.sudo().env.cr.execute(query_insert_sum_account_ytd_ly)


                    # YTD actual LY
                    query_actual_ytd_ly = """
                    INSERT INTO cost_center_report (
                        company_id, move_number, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        cc_dimension_name, budget_id) 
                    SELECT * 
                    FROM (
                        SELECT 
                            aac.company_id,
                            'tes4' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        
                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes5' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (-1*a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes6' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALL
                        -- --- tessssss
                        -- SELECT 
                        --     aac.company_id,
                        --     'tes6' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL-LY' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     0 balance, 
                        --     0 budget_amount, 
                        --     0 variance,
                        --     SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '-1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes03' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (-1*a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes114' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0)) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes115' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes116' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0)) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALL
                        -- ---tessssssssssssss
                        -- SELECT 
                        --     aac.company_id,
                        --     'tes116' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL-LY' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     0 balance, 
                        --     0 budget_amount, 
                        --     0 variance,
                        --     SUM(COALESCE(ccsa.balance,0)) last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes04' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                    ) AS a 
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'YTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = ytd_start_date_ly,
                        end_date = ytd_end_date_ly,
                        end_date_ly = ytd_end_date,
                        no_detail = "<> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n CC PL YTD Actual LY.')
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_actual_ytd_ly))

                    self.sudo().env.cr.execute(query_actual_ytd_ly)



                    # YTD budget not include consumables & drugs
                    query_budget_ytd1 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    SELECT 
                        aac.company_id,
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0)) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0)) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes7' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code not in ('5301000000','5302000000')
                        AND ccdl.sign_on_report != '-1'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

        
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'YTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = ytd_start_date,
                        end_date = ytd_end_date,
                        no_detail = "<> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_ytd1)

                    # YTD budget not include consumables & drugs
                    query_budget_ytd2 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    

                    SELECT 
                        aac.company_id,
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes7' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code not in ('5301000000','5302000000')
                        AND ccdl.sign_on_report != '1'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'YTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = ytd_start_date,
                        end_date = ytd_end_date,
                        no_detail = "<> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_ytd2)
            


                    # YTD budget consumables & drugs only
                    query_budget_ytd3 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    SELECT 
                        aac.company_id,
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0)) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0)) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes7' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_journal aj on aj.id = ccdl.journal_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code in ('5301000000','5302000000')
                        -- AND aj.name ='Sales Cost'
                        AND aj.name->>'en_US' ='Sales Cost'
                        AND ccdl.sign_on_report != '-1'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

        
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'YTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = ytd_start_date,
                        end_date = ytd_end_date,
                        no_detail = "<> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_ytd3)

                    # YTD budget consumables & drugs only 
                    query_budget_ytd4 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    

                    SELECT 
                        aac.company_id,
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes7' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_journal aj on aj.id = ccdl.journal_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code in ('5301000000','5302000000')
                        --AND aj.name ='Sales Cost'
                        AND aj.name->>'en_US' ='Sales Cost'
                        AND ccdl.sign_on_report != '1'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'YTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = ytd_start_date,
                        end_date = ytd_end_date,
                        no_detail = "<> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_ytd4)
            
            
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n YTD ACTUAL.')
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_insert_sum_account_ytd))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_ytd))

                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n YTD ACTUAL LY.')
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_insert_sum_account_ytd_ly))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_ytd_ly))

                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n YTD Budget.')
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_ytd1))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_ytd2))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_ytd3))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_ytd4))
                            
                    

                    # self.sudo().env.cr.execute(query_actual_ytd)
                    # self.sudo().env.cr.execute(query_actual_ytd_ly)
                    # self.sudo().env.cr.execute(query_budget_ytd)


                    

               
                
                # MTD generate 
                if self.type_period in['BOTH']:

                    query_delete = """
                        DELETE FROM cost_center_sum_account
                        where user_id = {user_id}
                    """.format(user_id = self.env.user.id)
                    self.sudo().env.cr.execute(query_delete)

                    query_insert_sum_account_mtd = """
                        insert into cost_center_sum_account (user_id, balance, account_id, analytic_account_id, journal_id, date)
                        select {user_id} AS user_id, sum(a.balance) balance, a.account_id, a.analytic_account_id, a.journal_id, a.date
                        from account_move_line a
                        left join account_move am on am.id = a.move_id
                        where a.account_id is not null 
                        and a.analytic_account_id is not null 
                        and am.state = '{state}'
                        AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                        AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                        and a.company_id = {company_id}
                        group by a.account_id, a.analytic_account_id, a.journal_id, a.date

                    """.format(
                            user_id = self.env.user.id,
                            type_report = self.type_report,
                            type_date = 'MTD',
                            company_id = self.company_id.id,
                            state = self.state,
                            start_date = mtd_start_date,
                            end_date = mtd_end_date,
                            no_detail = " <> 'no_detail' ",
                            filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                            )
                    self.sudo().env.cr.execute(query_insert_sum_account_mtd)


                    # MTD actual 
                    query_actual_mtd = """
                    INSERT INTO cost_center_report (
                        company_id, move_number, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        cc_dimension_name, budget_id) 
                    SELECT * 
                    FROM (
            SELECT 
                            {company_id} company_id,
                            'tes null' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            null account_id, 
                            null analytic_id, 
                            null parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            0 last_balance, 
                            0 last_variance,
                            null department_id, null head_id,
                            '{end_date}' date,
                            null cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
            WHERE ccdl.company_id = {company_id}

            UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes8' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0) * -1) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0) * -1) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        
                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes9' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (-1*a.balance) balance, 
                            0 budget_amount, 
                            (-1*a.balance) variance,
                            0 last_balance,  
                            (-1*a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes10' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0) * -1) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0) * -1) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -------------------tes
                        -- UNION ALL

                        -- SELECT 
                        --     aac.company_id,
                        --     'tes10' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                        --     0 budget_amount, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) variance,
                        --     0 last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '-1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes05' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (-1*a.balance) balance, 
                            0 budget_amount, 
                            (-1*a.balance) variance,
                            0 last_balance,  
                            (-1*a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes118' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0)) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0)) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        
                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes119' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (a.balance) balance, 
                            0 budget_amount, 
                            (a.balance) variance,
                            0 last_balance,  
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes1110' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0)) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0)) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        --tess

                        -- UNION ALL

                        -- SELECT 
                        --     aac.company_id,
                        --     'tes1115555555555' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     SUM(COALESCE(ccsa.balance,0)) balance, 
                        --     0 budget_amount, 
                        --     SUM(COALESCE(ccsa.balance,0)) variance,
                        --     0 last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes07' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (a.balance) balance, 
                            0 budget_amount, 
                            (a.balance) variance,
                            0 last_balance,  
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}


                    ) AS a 
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'MTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = mtd_start_date,
                        end_date = mtd_end_date,
                        no_detail = " <> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n CC PL MTD Actual.')
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_actual_mtd))
                    self.sudo().env.cr.execute(query_actual_mtd)

                    query_delete = """
                        DELETE FROM cost_center_sum_account
                        where user_id = {user_id}
                    """.format(user_id = self.env.user.id)
                    self.sudo().env.cr.execute(query_delete)

                    query_insert_sum_account_mtd_ly = """
                        insert into cost_center_sum_account (user_id, balance, account_id, analytic_account_id, journal_id, date)
                        select {user_id} AS user_id, sum(a.balance) balance, a.account_id, a.analytic_account_id, a.journal_id, a.date
                        from account_move_line a
                        left join account_move am on am.id = a.move_id
                        where a.account_id is not null 
                        and a.analytic_account_id is not null 
                        and am.state = '{state}'
                        AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                        AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                        and a.company_id = {company_id}
                        group by a.account_id, a.analytic_account_id, a.journal_id, a.date

                    """.format(
                            user_id = self.env.user.id,
                            type_report = self.type_report,
                            type_date = 'MTD',
                            company_id = self.company_id.id,
                            state = self.state,
                            start_date = mtd_start_date_ly,
                            end_date = mtd_end_date_ly,
                            end_date_ly = mtd_end_date,
                            no_detail = " <> 'no_detail' ",
                            filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                            )
                    self.sudo().env.cr.execute(query_insert_sum_account_mtd_ly)


                    # MTD actual LY
                    query_actual_mtd_ly = """
                    INSERT INTO cost_center_report (
                        company_id, move_number, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        cc_dimension_name, budget_id) 
                    SELECT * 
                    FROM (
                        SELECT 
                            aac.company_id,
                            'tes11' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes12' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (-1*a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes13' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALL
                        -- ---tesssss
                        -- SELECT 
                        --     aac.company_id,
                        --     'tes13' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL-LY' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     0 balance, 
                        --     0 budget_amount, 
                        --     0 variance,
                        --     SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '-1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes08' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (-1*a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes1111' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0)) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                       
                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes1112' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes1113' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0)) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALl
                        -- ---tessss
                        -- SELECT 
                        --     aac.company_id,
                        --     'tes1113' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL-LY' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     0 balance, 
                        --     0 budget_amount, 
                        --     0 variance,
                        --     SUM(COALESCE(ccsa.balance,0)) last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes09' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                    ) AS a 
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'MTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = mtd_start_date_ly,
                        end_date = mtd_end_date_ly,
                        end_date_ly = mtd_end_date,
                        no_detail = " <> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n CC PL MTD Actual LY.')
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_actual_mtd_ly))
                    self.sudo().env.cr.execute(query_actual_mtd_ly)

                    # MTD budget not include consumable & drugs
                    query_budget_mtd1 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    SELECT 
                        aac.company_id, 
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0)) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0)) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes14' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code not in ('5301000000','5302000000')
                        AND ccdl.sign_on_report != '-1'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                    
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'MTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = mtd_start_date,
                        end_date = mtd_end_date,
                        no_detail = " <> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_mtd1)


                    # MTD budget not include consumable & drugs
                    query_budget_mtd2 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    

                    SELECT 
                        aac.company_id, 
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes14' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code not in ('5301000000','5302000000')
                        AND ccdl.sign_on_report != '1'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'MTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = mtd_start_date,
                        end_date = mtd_end_date,
                        no_detail = " <> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_mtd2)



                    # MTD budget consumable & drugs only
                    query_budget_mtd3 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    SELECT 
                        aac.company_id, 
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0)) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0)) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes14' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_journal aj on aj.id = ccdl.journal_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code in ('5301000000','5302000000')
                        --AND aj.name ='Sales Cost'
                        AND aj.name->>'en_US' ='Sales Cost'
                        AND ccdl.sign_on_report != '-1'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                    
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'MTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = mtd_start_date,
                        end_date = mtd_end_date,
                        no_detail = " <> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_mtd3)


                    # MTD budget consumable & drugs only
                    query_budget_mtd4 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    

                    SELECT 
                        aac.company_id, 
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes14' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_journal aj on aj.id = ccdl.journal_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code in ('5301000000','5302000000')
                        --AND aj.name ='Sales Cost'
                        AND aj.name->>'en_US' ='Sales Cost'
                        AND ccdl.sign_on_report != '1'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'MTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = mtd_start_date,
                        end_date = mtd_end_date,
                        no_detail = " <> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_mtd4)
                    
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n MTD ACTUAL.')
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_insert_sum_account_mtd))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_mtd))

                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n MTD ACTUAL LY.')
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_insert_sum_account_mtd_ly))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_mtd_ly))

                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n MTD Budget.')
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_mtd1))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_mtd2))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_mtd3))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_mtd4))




                    # self.sudo().env.cr.execute(query_actual_mtd)
                    # self.sudo().env.cr.execute(query_actual_mtd_ly)
                    # self.sudo().env.cr.execute(query_budget_mtd)



            # Trend Report
            if self.type_report == '2':

                # YTD generate 
                if self.type_period in['PERIOD']:


                    query_delete = """
                            DELETE FROM cost_center_sum_account
                            where user_id = {user_id}
                        """.format(user_id = self.env.user.id)
                    self.sudo().env.cr.execute(query_delete)


                    query_insert_sum_account_actual_period = """
                        insert into cost_center_sum_account (user_id, balance, account_id, analytic_account_id, journal_id, date)
                        select {user_id} AS user_id, sum(a.balance) balance, a.account_id, a.analytic_account_id, a.journal_id, a.date
                        from account_move_line a
                        left join account_move am on am.id = a.move_id
                        where a.account_id is not null 
                        and a.analytic_account_id is not null 
                        and am.state = '{state}'
                        AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                        AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                        and a.company_id = {company_id}
                        group by a.account_id, a.analytic_account_id, a.journal_id, a.date

                    """.format(
                            user_id = self.env.user.id,
                            type_report = self.type_report,
                            type_date = 'PERIOD',
                            company_id = self.company_id.id,
                            state = self.state,
                            start_date = per_start_date,
                            end_date = per_end_date,
                            no_detail = " <> 'no_detail' ",
                            filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                            )
                    self.sudo().env.cr.execute(query_insert_sum_account_actual_period)


                    # Period actual 
                    query_actual_period = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        cc_dimension_name, budget_id) 
                    SELECT * 
                    FROM (
            SELECT 
                            {company_id} company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            null account_id, 
                            null analytic_id, 
                            null parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            0 last_balance, 
                            0 last_variance,
                            null department_id, null head_id,
                            '{end_date}' date,
                            null cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
            WHERE ccdl.company_id = {company_id}

            UNION ALL

                        SELECT 
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0) * -1) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            AND aac.company_id = {company_id} 
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (-1*a.balance) balance, 
                            0 budget_amount, 
                            (-1*a.balance) variance,
                            0 last_balance, 
                            a.balance last_variance,  
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0) * -1) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            AND aac.company_id = {company_id} 
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALL
                        -- --tessss
                        -- SELECT 
                        --     aac.company_id,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                        --     0 budget_amount, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) variance,
                        --     0 last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id,
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '-1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        --     AND aac.company_id = {company_id} 
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (-1*a.balance) balance, 
                            0 budget_amount, 
                            (-1*a.balance) variance,
                            0 last_balance, 
                            a.balance last_variance,  
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0)) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0)) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            AND aac.company_id = {company_id} 
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (a.balance) balance, 
                            0 budget_amount, 
                            (a.balance) variance,
                            0 last_balance, 
                            a.balance last_variance,  
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0)) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0)) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            AND aac.company_id = {company_id} 
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALL
                        -- ---tesss
                        -- SELECT 
                        --     aac.company_id,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     SUM(COALESCE(ccsa.balance,0)) balance, 
                        --     0 budget_amount, 
                        --     SUM(COALESCE(ccsa.balance,0)) variance,
                        --     0 last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id,
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        --     AND aac.company_id = {company_id} 
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (a.balance) balance, 
                            0 budget_amount, 
                            (a.balance) variance,
                            0 last_balance, 
                            a.balance last_variance,  
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}


                    ) AS a 
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'PERIOD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = per_start_date,
                        end_date = per_end_date,
                        no_detail = " <> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )


                    #query_delete = """
                    #        DELETE FROM cost_center_sum_account
                    #    """.format(user_id = self.env.user.id)
                    #self.sudo().env.cr.execute(query_delete)


                    #query_insert_sum_account_actual_period_ly = """
                    #    insert into cost_center_sum_account (balance, account_id, analytic_account_id, journal_id, date)
                    #    select sum(a.balance) balance, a.account_id, a.analytic_account_id, a.journal_id, a.date
                    #    from account_move_line a
                    #    left join account_move am on am.id = a.move_id
                    #    where a.account_id is not null 
                    #    and a.analytic_account_id is not null 
                    #    and am.state = '{state}'
                    #    AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                    #    AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                    #    and a.company_id = {company_id}
                    #    group by a.account_id, a.analytic_account_id, a.journal_id, a.date

                    #""".format(
                    #        user_id = self.env.user.id,
                    #        type_report = self.type_report,
                    #        type_date = 'PERIOD',
                    #        company_id = self.company_id.id,
                    #        state = self.state,
                    #        start_date = per_start_date_ly,
                    #        end_date = per_end_date_ly,
                    #        end_date_ly = per_end_date,
                    #        no_detail = " <> 'no_detail' ",
                    #        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    #        )
                    #self.sudo().env.cr.execute(query_insert_sum_account_actual_period_ly)

                    


                    ## YTD actual LY
                    #query_actual_period_ly = """
                    #INSERT INTO cost_center_report (
                    #    company_id, create_uid, write_uid, create_date, write_date, 
                    #    type_data, type_report, user_id, account_id, 
                    #    analytic_account_id, parent_analytic_id, 
                    #    type_date, balance, budget_amount, variance,
                    #    last_balance, last_variance, 
                    #    department_id, head_id, date, 
                    #    cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                    #    cc_dimension_name, budget_id)
                    #SELECT * 
                    #FROM (
                    #    SELECT 
                    #        aa.company_id, 
                    #        {user_id} AS create_uid, 
                    #        {user_id} AS write_uid, 
                    #        CURRENT_TIMESTAMP AS create_date, 
                    #        CURRENT_TIMESTAMP AS write_date, 
                    #        'ACTUAL-LY' type_data, 
                    #        '{type_report}' AS type_report, 
                    #        {user_id} AS user_id, 
                    #        aa.id account_id, 
                    #        aac.id analytic_id, 
                    #        aap.id parent_analytic_id, 
                    #        '{type_date}' as type_date, 
                    #        0 balance, 
                    #        0 budget_amount, 
                    #        0 variance,
                    #        SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                    #        SUM(0 - (COALESCE(ccsa.balance,0) * -1)) last_variance,
                    #        hdp.id department_id, hdp.head_id,
                    #        (date(COALESCE(ccsa.date, '{end_date}')) + interval '1 year') date,
                    #        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                    #        ccd.id cc_dimension_id, 
                    #        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null budget_id
                    #    from cost_center_dimension_line ccdl
                    #        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                    #        left join account_account aa on aa.id = ccdl.account_id
                    #        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                    #        left join account_analytic_account aap ON aap.id=aac.parent_id
                    #        LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                    #        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    #        LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id
                    #    WHERE aac.type_analytic = 'expense' 
                    #        AND LEFT(aac.code,1) <> '1' --bukan asset  
                    #        AND aac.active=true --active
                    #        AND ccdl.account_id is not null
                    #        AND ccdl.journal_id is null
                    #        AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                    #        AND aac.company_id = {company_id} 
                    #        {filter_ids}
                    #    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                    #        (date(COALESCE(ccsa.date, '{end_date}')) + interval '1 year'),
                    #        ccm.id, ccd.parent_id, ccd.id, 
                    #        CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        
                    #    UNION ALL 

                    #    -- COST CENTER IMPORT
                    #    SELECT
                    #        aac.company_id,
                    #        {user_id} AS create_uid, 
                    #        {user_id} AS write_uid, 
                    #        CURRENT_TIMESTAMP AS create_date, 
                    #        CURRENT_TIMESTAMP AS write_date, 
                    #        'ACTUAL-LY' AS type_data, 
                    #        '{type_report}' AS type_report, 
                    #        {user_id} AS user_id, 
                    #        a.account_id, 
                    #        a.analytic_account_id, 
                    #        a.parent_analytic_id, 
                    #        '{type_date}' as type_date, 
                    #        0 balance, 
                    #        0 budget_amount, 
                    #        0 variance,
                    #        a.balance last_balance, 
                    #        a.balance last_variance, 
                    #        hdp.id department_id, hdp.head_id, 
                    #        (date(COALESCE(a.date, '{end_date}')) + interval '1 year') date, 
                    #        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                    #        ccd.id cc_dimension_id,
                    #        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                    #    FROM cost_center_import a 
                    #        INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                    #        LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                    #        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    #        left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                    #        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                    #    WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                    #        AND aac.active=true  --selalu yang masih aktif
                    #        AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                    #        AND aac.company_id = {company_id}  --company_id 
                    #        AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                    #        AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                    #        {filter_ids}


                    #    UNION ALL


                    #    SELECT 
                    #        aa.company_id, 
                    #        {user_id} AS create_uid, 
                    #        {user_id} AS write_uid, 
                    #        CURRENT_TIMESTAMP AS create_date, 
                    #        CURRENT_TIMESTAMP AS write_date, 
                    #        'ACTUAL-LY' type_data, 
                    #        '{type_report}' AS type_report, 
                    #        {user_id} AS user_id, 
                    #        aa.id account_id, 
                    #        aac.id analytic_id, 
                    #        aap.id parent_analytic_id, 
                    #        '{type_date}' as type_date, 
                    #        0 balance, 
                    #        0 budget_amount, 
                    #        0 variance,
                    #        SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                    #        SUM(0 - (COALESCE(ccsa.balance,0) * -1)) last_variance,
                    #        hdp.id department_id, hdp.head_id,
                    #        (date(COALESCE(ccsa.date, '{end_date}')) + interval '1 year') date,
                    #        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                    #        ccd.id cc_dimension_id,
                    #        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null budget_id
                    #    from cost_center_dimension_line ccdl
                    #        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                    #        left join account_account aa on aa.id = ccdl.account_id
                    #        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                    #        left join account_analytic_account aap ON aap.id=aac.parent_id
                    #        LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                    #        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    #        LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id
                    #    WHERE aac.type_analytic = 'expense' 
                    #        AND LEFT(aac.code,1) <> '1' --bukan asset  
                    #        AND aac.active=true --active
                    #        AND ccdl.account_id is not null
                    #        AND coalesce(ccdl.journal_id, 0000000) != 0000000
                    #        AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                    #        AND aac.company_id = {company_id} 
                    #        {filter_ids}
                    #    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                    #        (date(COALESCE(ccsa.date, '{end_date}')) + interval '1 year'),
                    #        ccm.id, ccd.parent_id, ccd.id, 
                    #        CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                    #) AS a
                    #""".format(
                    #    user_id = self.env.user.id,
                    #    type_report = self.type_report,
                    #    type_date = 'PERIOD',
                    #    company_id = self.company_id.id,
                    #    state = self.state,
                    #    start_date = per_start_date_ly,
                    #    end_date = per_end_date_ly,
                    #    end_date_ly = per_end_date,
                    #    no_detail = " <> 'no_detail' ",
                    #    filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    #)


                    ## YTD budget 
                    #query_budget_period = """
                    #INSERT INTO cost_center_report (
                    #    company_id, create_uid, write_uid, create_date, write_date, 
                    #    type_data, type_report, user_id, account_id, 
                    #    analytic_account_id, parent_analytic_id, 
                    #    type_date, balance, budget_amount, variance,
                    #    last_balance, last_variance, 
                    #    department_id, head_id, date, 
                    #    cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                    #    move_id, move_number, cc_dimension_name, budget_id) 
                    #SELECT 
                    #    aac.company_id,
                    #    {user_id} AS create_uid, 
                    #    {user_id} AS write_uid, 
                    #    CURRENT_TIMESTAMP AS create_date, 
                    #    CURRENT_TIMESTAMP AS write_date, 
                    #    'BUDGET' type_data, 
                    #    '{type_report}' AS type_report, 
                    #    {user_id} AS user_id, 
                    #    aa.id account_id, 
                    #    aac.id analytic_id, 
                    #    aap.id parent_analytic_id, 
                    #    '{type_date}' as type_date, 
                    #    0 balance, 
                    #    SUM(COALESCE(cbl.planned_amount,0)) budget_amount, 
                    #    SUM(COALESCE(cbl.planned_amount,0) - 0) variance,
                    #    0 last_balance, 
                    #    0 last_variance,
                    #    hdp.id department_id, hdp.head_id,
                    #    COALESCE(cbl.date_from, '{end_date}') date,
                    #    ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                    #    ccd.id cc_dimension_id, null::integer move_id, null move_number, 
                    #    CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    #from cost_center_dimension_line ccdl
                    #    left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                    #    left join account_account aa on aa.id = ccdl.account_id
                    #    LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                    #    LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                    #    LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                    #    LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                    #    LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                    #    LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    #WHERE aac.type_analytic = 'expense' 
                    #    AND LEFT(aac.code,1) <> '1' --bukan asset  
                    #    AND aac.active=true --active
                    #    AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                    #    AND aac.company_id = {company_id} 
                    #    -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                    #    AND cbl.date_from >= '{start_date}' 
                    #    AND cbl.date_to <= '{end_date}' 
                    #    {filter_ids}
                    #GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                    #    COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                    #    ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                    #""".format(
                    #    user_id = self.env.user.id,
                    #    type_report = self.type_report,
                    #    type_date = 'PERIOD',
                    #    company_id = self.company_id.id,
                    #    state = self.state,
                    #    start_date = per_start_date,
                    #    end_date = per_end_date,
                    #    no_detail = " <> 'no_detail' ",
                    #    filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    #)
                    #open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n CC PL YTD Budget.')
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_period))
                    #open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_period_ly))
                    #open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_period))
                    

                    self.sudo().env.cr.execute(query_actual_period)
                    #self.sudo().env.cr.execute(query_actual_period_ly)
                    #self.sudo().env.cr.execute(query_budget_period)


            # Trend Budget Report
            if self.type_report == '3':

                # YTD generate 
                if self.type_period in['PERIOD']:


                    # YTD budget not include consumables & drugs
                    query_budget_period1 = """
                    INSERT INTO cost_center_report (
                       company_id, create_uid, write_uid, create_date, write_date, 
                       type_data, type_report, user_id, account_id, 
                       analytic_account_id, parent_analytic_id, 
                       type_date, balance, budget_amount, variance,
                       last_balance, last_variance, 
                       department_id, head_id, date, 
                       cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                       move_id, move_number, cc_dimension_name, budget_id) 
                    SELECT 
                        aac.company_id, 
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0)) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0)) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes14' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code not in ('5301000000','5302000000')
                        AND ccdl.sign_on_report != '-1'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                    

                    """.format(
                       user_id = self.env.user.id,
                       type_report = self.type_report,
                       type_date = 'PERIOD',
                       company_id = self.company_id.id,
                       state = self.state,
                       start_date = per_start_date,
                       end_date = per_end_date,
                       no_detail = " <> 'no_detail' ",
                       filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )


                    # YTD budget not include consumables & drugs
                    query_budget_period2 = """
                    INSERT INTO cost_center_report (
                       company_id, create_uid, write_uid, create_date, write_date, 
                       type_data, type_report, user_id, account_id, 
                       analytic_account_id, parent_analytic_id, 
                       type_date, balance, budget_amount, variance,
                       last_balance, last_variance, 
                       department_id, head_id, date, 
                       cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                       move_id, move_number, cc_dimension_name, budget_id) 
                    

                    SELECT 
                        aac.company_id, 
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes14' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code not in ('5301000000','5302000000')
                        AND ccdl.sign_on_report != '1'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                    """.format(
                       user_id = self.env.user.id,
                       type_report = self.type_report,
                       type_date = 'PERIOD',
                       company_id = self.company_id.id,
                       state = self.state,
                       start_date = per_start_date,
                       end_date = per_end_date,
                       no_detail = " <> 'no_detail' ",
                       filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )



                    # YTD budget consumables & drugs only
                    query_budget_period3 = """
                    INSERT INTO cost_center_report (
                       company_id, create_uid, write_uid, create_date, write_date, 
                       type_data, type_report, user_id, account_id, 
                       analytic_account_id, parent_analytic_id, 
                       type_date, balance, budget_amount, variance,
                       last_balance, last_variance, 
                       department_id, head_id, date, 
                       cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                       move_id, move_number, cc_dimension_name, budget_id) 
                    SELECT 
                        aac.company_id, 
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0)) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0)) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes14' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_journal aj on aj.id = ccdl.journal_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code in ('5301000000','5302000000')
                        --AND aj.name ='Sales Cost'
                        AND aj.name->>'en_US' ='Sales Cost'
                        AND ccdl.sign_on_report != '-1'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                    

                    """.format(
                       user_id = self.env.user.id,
                       type_report = self.type_report,
                       type_date = 'PERIOD',
                       company_id = self.company_id.id,
                       state = self.state,
                       start_date = per_start_date,
                       end_date = per_end_date,
                       no_detail = " <> 'no_detail' ",
                       filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )


                    # YTD budget consumables & drugs only
                    query_budget_period4 = """
                    INSERT INTO cost_center_report (
                       company_id, create_uid, write_uid, create_date, write_date, 
                       type_data, type_report, user_id, account_id, 
                       analytic_account_id, parent_analytic_id, 
                       type_date, balance, budget_amount, variance,
                       last_balance, last_variance, 
                       department_id, head_id, date, 
                       cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                       move_id, move_number, cc_dimension_name, budget_id) 
                    

                    SELECT 
                        aac.company_id, 
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes14' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_journal aj on aj.id = ccdl.journal_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code in ('5301000000','5302000000')
                        --AND aj.name ='Sales Cost'
                        AND aj.name->>'en_US' ='Sales Cost'
                        AND ccdl.sign_on_report != '1'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                    """.format(
                       user_id = self.env.user.id,
                       type_report = self.type_report,
                       type_date = 'PERIOD',
                       company_id = self.company_id.id,
                       state = self.state,
                       start_date = per_start_date,
                       end_date = per_end_date,
                       no_detail = " <> 'no_detail' ",
                       filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )

                    query_budget_period_null = """
                    INSERT INTO cost_center_report (
                       company_id, create_uid, write_uid, create_date, write_date, 
                       type_data, type_report, user_id, account_id, 
                       analytic_account_id, parent_analytic_id, 
                       type_date, balance, budget_amount, variance,
                       last_balance, last_variance, 
                       department_id, head_id, date, 
                       cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                       move_id, move_number, cc_dimension_name, budget_id) 
                    SELECT 
                       {company_id} company_id,
                       {user_id} AS create_uid, 
                       {user_id} AS write_uid, 
                       CURRENT_TIMESTAMP AS create_date, 
                       CURRENT_TIMESTAMP AS write_date, 
                       'BUDGET' type_data, 
                       '{type_report}' AS type_report, 
                       {user_id} AS user_id, 
                       null account_id, 
                       null analytic_id, 
                       null parent_analytic_id, 
                       '{type_date}' as type_date, 
                       0 balance, 
                       0 budget_amount, 
                       0 variance,
                       0 last_balance, 
                       0 last_variance,
                       null department_id, null head_id,
                       '{end_date}' date,
                       null cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                       ccd.id cc_dimension_id, null::integer move_id, null move_number, 
                       CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null budget_id
                    from cost_center_dimension_line ccdl
                       left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                       
                    WHERE ccdl.company_id = {company_id}
                    
                    """.format(
                       user_id = self.env.user.id,
                       type_report = self.type_report,
                       type_date = 'PERIOD',
                       company_id = self.company_id.id,
                       state = self.state,
                       start_date = per_start_date,
                       end_date = per_end_date,
                       no_detail = " <> 'no_detail' ",
                       filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n CC PL YTD Budget.')
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_period))
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_period_ly))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_period1))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_period2))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_period3))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_period4))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_period_null))
                    

                    # self.sudo().env.cr.execute(query_actual_period)
                    # self.sudo().env.cr.execute(query_actual_period_ly)
                    self.sudo().env.cr.execute(query_budget_period1)
                    self.sudo().env.cr.execute(query_budget_period2)
                    self.sudo().env.cr.execute(query_budget_period3)
                    self.sudo().env.cr.execute(query_budget_period4)
                    self.sudo().env.cr.execute(query_budget_period_null)
            

                
                

                # query_delete = """
                #     DELETE FROM cost_center_report
                #     WHERE user_id = {user_id} 
                #     AND pl_name LIKE '%- 1 -%'
                # """.format(user_id = self.env.user.id)
                # open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n Delete BS.')
                # open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_delete))
                # self.sudo().env.cr.execute(query_delete)

                # query_delete_parent = """
                #     DELETE FROM cost_center_report
                #     WHERE user_id = {user_id} 
                #     AND parent_pl_id IN (
                #         SELECT id FROM account_financial_report t
                #         WHERE t.name LIKE '%- 1 -%')
                # """.format(user_id = self.env.user.id)
                # open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n Delete BS Child.')
                # open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_delete_parent))
                # self.sudo().env.cr.execute(query_delete_parent)

                # # delete parent Not Profit Loss
                # query_delete_parent = """
                #     DELETE FROM cost_center_report
                #     WHERE user_id = {user_id} 
                #     AND parent_pl_id IN (
                #         SELECT id FROM account_financial_report t
                #         WHERE t.name NOT LIKE '%Profit and Loss%')
                # """.format(user_id = self.env.user.id)
                # open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n Delete Child of Parent not Profit Loss.')
                # open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_delete_parent))
                # self.sudo().env.cr.execute(query_delete_parent)


        if self.company_id.company_corporate_type == 'main':

            # Standard Report
            if self.type_report == '1':

                

                # YTD generate 
                if self.type_period in['BOTH']:

                    query_delete = """
                            DELETE FROM cost_center_sum_account
                            where user_id = {user_id}
                        """.format(user_id = self.env.user.id)
                    self.sudo().env.cr.execute(query_delete)


                    query_insert_sum_account_ytd = """
                        insert into cost_center_sum_account (user_id, balance, account_id, analytic_account_id, journal_id, date)
                        select {user_id} AS user_id, sum(a.balance) balance, a.account_id, a.analytic_account_id, a.journal_id, a.date
                        from account_move_line a
                        left join account_move am on am.id = a.move_id
                        left join res_company rc on rc.id = a.company_id
                        where a.account_id is not null 
                        and a.analytic_account_id is not null 
                        and am.state = '{state}'
                        AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                        AND COALESCE(a.date, '{end_date}') <= '{end_date}'
                        and rc.company_corporate_type in ('main','secondary') 
                        group by a.account_id, a.analytic_account_id, a.journal_id, a.date

                    """.format(
                            user_id = self.env.user.id,
                            type_report = self.type_report,
                            type_date = 'YTD',
                            company_id = self.company_id.id,
                            state = self.state,
                            start_date = ytd_start_date,
                            end_date = ytd_end_date,
                            no_detail = "<> 'no_detail' ",
                            filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                            )
                    self.sudo().env.cr.execute(query_insert_sum_account_ytd)

                    # YTD actual 
                    query_actual_ytd = """
                    INSERT INTO cost_center_report (
                        company_id, move_number, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        cc_dimension_name, budget_id) 
                    SELECT * 
                    FROM (
            SELECT 
                            {company_id} company_id,
                            'tes null' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            null account_id, 
                            null analytic_id, 
                            null parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            0 last_balance, 
                            0 last_variance,
                            null department_id, null head_id,
                            '{end_date}' date,
                            null cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
            WHERE ccdl.company_id = {company_id}

            UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes1' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0) * -1) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0) * -1) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes2' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (-1*a.balance) balance, 
                            0 budget_amount, 
                            (-1*a.balance) variance,
                            0 last_balance, 
                            (-1*a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes3' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0) * -1) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0) * -1) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALL
                        -- ---- tesssssssssss
                        -- SELECT 
                        --     aac.company_id,
                        --     'tes3' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                        --     0 budget_amount, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) variance,
                        --     0 last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '-1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes01' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (-1*a.balance) balance, 
                            0 budget_amount, 
                            (-1*a.balance) variance,
                            0 last_balance, 
                            (-1*a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes111' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0)) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0)) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes112' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (a.balance) balance, 
                            0 budget_amount, 
                            (a.balance) variance,
                            0 last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes113' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0)) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0)) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}

                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALL
                        -- ---tessssssssssssss
                        -- SELECT 
                        --     aac.company_id,
                        --     'tes113' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     SUM(COALESCE(ccsa.balance,0)) balance, 
                        --     0 budget_amount, 
                        --     SUM(COALESCE(ccsa.balance,0)) variance,
                        --     0 last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes02' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (a.balance) balance, 
                            0 budget_amount, 
                            (a.balance) variance,
                            0 last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}


                    ) AS a 
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'YTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = ytd_start_date,
                        end_date = ytd_end_date,
                        no_detail = "<> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n CC PL YTD Actual.')
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_actual_ytd))

                    self.sudo().env.cr.execute(query_actual_ytd)

                    query_delete = """
                        DELETE FROM cost_center_sum_account
                        where user_id = {user_id}
                    """.format(user_id = self.env.user.id)
                    self.sudo().env.cr.execute(query_delete)

                    query_insert_sum_account_ytd_ly = """
                        insert into cost_center_sum_account (user_id, balance, account_id, analytic_account_id, journal_id, date)
                        select {user_id} AS user_id, sum(a.balance) balance, a.account_id, a.analytic_account_id, a.journal_id, a.date
                        from account_move_line a
                        left join account_move am on am.id = a.move_id
                        left join res_company rc on rc.id = a.company_id
                        where a.account_id is not null 
                        and a.analytic_account_id is not null 
                        and am.state = '{state}'
                        AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                        AND COALESCE(a.date, '{end_date}') <= '{end_date}'
                        and rc.company_corporate_type in ('main','secondary') 
                        group by a.account_id, a.analytic_account_id, a.journal_id, a.date

                    """.format(
                            user_id = self.env.user.id,
                            type_report = self.type_report,
                            type_date = 'YTD',
                            company_id = self.company_id.id,
                            state = self.state,
                            start_date = ytd_start_date_ly,
                            end_date = ytd_end_date_ly,
                            end_date_ly = ytd_end_date,
                            no_detail = "<> 'no_detail' ",
                            filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                            )
                    self.sudo().env.cr.execute(query_insert_sum_account_ytd_ly)


                    # YTD actual LY
                    query_actual_ytd_ly = """
                    INSERT INTO cost_center_report (
                        company_id, move_number, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        cc_dimension_name, budget_id) 
                    SELECT * 
                    FROM (
                        SELECT 
                            aac.company_id,
                            'tes4' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes5' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (-1*a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes6' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALL
                        -- --- tessssss
                        -- SELECT 
                        --     aac.company_id,
                        --     'tes6' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL-LY' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     0 balance, 
                        --     0 budget_amount, 
                        --     0 variance,
                        --     SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '-1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id


                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes03' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (-1*a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes114' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0)) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes115' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes116' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0)) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALL
                        -- ---tessssssssssssss
                        -- SELECT 
                        --     aac.company_id,
                        --     'tes116' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL-LY' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     0 balance, 
                        --     0 budget_amount, 
                        --     0 variance,
                        --     SUM(COALESCE(ccsa.balance,0)) last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes04' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        


                    ) AS a 
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'YTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = ytd_start_date_ly,
                        end_date = ytd_end_date_ly,
                        end_date_ly = ytd_end_date,
                        no_detail = "<> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n CC PL YTD Actual LY.')
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_actual_ytd_ly))

                    self.sudo().env.cr.execute(query_actual_ytd_ly)



                    # YTD budget not include consumables & drugs
                    query_budget_ytd1 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    SELECT 
                        aac.company_id,
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0)) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0)) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes7' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code not in ('5301000000','5302000000')
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        AND ccdl.sign_on_report != '-1'
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'YTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = ytd_start_date,
                        end_date = ytd_end_date,
                        no_detail = "<> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_ytd1)


                    # YTD budget not include consumables & drugs
                    query_budget_ytd2 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    

                    SELECT 
                        aac.company_id,
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes7' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code not in ('5301000000','5302000000')
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        AND ccdl.sign_on_report != '1'
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'YTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = ytd_start_date,
                        end_date = ytd_end_date,
                        no_detail = "<> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_ytd2)




                    # YTD budget consumables & drugs only
                    query_budget_ytd3 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    SELECT 
                        aac.company_id,
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0)) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0)) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes7' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_journal aj on aj.id = ccdl.journal_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code in ('5301000000','5302000000')
                        --AND aj.name ='Sales Cost'
                        AND aj.name->>'en_US' ='Sales Cost'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        AND ccdl.sign_on_report != '-1'
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'YTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = ytd_start_date,
                        end_date = ytd_end_date,
                        no_detail = "<> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_ytd3)


                    # YTD budget consumables & drugs only
                    query_budget_ytd4 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    

                    SELECT 
                        aac.company_id,
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes7' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_journal aj on aj.id = ccdl.journal_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code in ('5301000000','5302000000')
                        --AND aj.name ='Sales Cost'
                        AND aj.name->>'en_US' ='Sales Cost'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        AND ccdl.sign_on_report != '1'
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'YTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = ytd_start_date,
                        end_date = ytd_end_date,
                        no_detail = "<> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_ytd4)
            
            
            
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n YTD ACTUAL.')
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_insert_sum_account_ytd))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_ytd))

                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n YTD ACTUAL LY.')
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_insert_sum_account_ytd_ly))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_ytd_ly))

                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n YTD Budget.')
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_ytd1))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_ytd2))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_ytd3))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_ytd4))
                            
                    

                    # self.sudo().env.cr.execute(query_actual_ytd)
                    # self.sudo().env.cr.execute(query_actual_ytd_ly)
                    # self.sudo().env.cr.execute(query_budget_ytd)


                    

               
                
                # MTD generate 
                if self.type_period in['BOTH']:

                    query_delete = """
                        DELETE FROM cost_center_sum_account
                        where user_id = {user_id}
                    """.format(user_id = self.env.user.id)
                    self.sudo().env.cr.execute(query_delete)

                    query_insert_sum_account_mtd = """
                        insert into cost_center_sum_account (user_id, balance, account_id, analytic_account_id, journal_id, date)
                        select {user_id} AS user_id, sum(a.balance) balance, a.account_id, a.analytic_account_id, a.journal_id, a.date
                        from account_move_line a
                        left join account_move am on am.id = a.move_id
                        left join res_company rc on rc.id = a.company_id
                        where a.account_id is not null 
                        and a.analytic_account_id is not null 
                        and am.state = '{state}'
                        AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                        AND COALESCE(a.date, '{end_date}') <= '{end_date}'
                        and rc.company_corporate_type in ('main','secondary') 
                        group by a.account_id, a.analytic_account_id, a.journal_id, a.date

                    """.format(
                            user_id = self.env.user.id,
                            type_report = self.type_report,
                            type_date = 'MTD',
                            company_id = self.company_id.id,
                            state = self.state,
                            start_date = mtd_start_date,
                            end_date = mtd_end_date,
                            no_detail = " <> 'no_detail' ",
                            filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                            )
                    self.sudo().env.cr.execute(query_insert_sum_account_mtd)
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n CC query_insert_sum_account_mtd')
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_insert_sum_account_mtd))
                    


                    # MTD actual 
                    query_actual_mtd = """
                    INSERT INTO cost_center_report (
                        company_id, move_number, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        cc_dimension_name, budget_id) 
                    SELECT * 
                    FROM (
            SELECT 
                            {company_id} company_id,
                            'tes null' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            null account_id, 
                            null analytic_id, 
                            null parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            0 last_balance, 
                            0 last_variance,
                            null department_id, null head_id,
                            '{end_date}' date,
                            null cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
            WHERE ccdl.company_id = {company_id}

            UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes8' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0) * -1) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0) * -1) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes9' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (-1*a.balance) balance, 
                            0 budget_amount, 
                            (-1*a.balance) variance,
                            0 last_balance,  
                            (-1*a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes10' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0) * -1) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0) * -1) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -------------------tes
                        -- UNION ALL

                        -- SELECT 
                        --     aac.company_id,
                        --     'tes10' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                        --     0 budget_amount, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) variance,
                        --     0 last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '-1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes05' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (-1*a.balance) balance, 
                            0 budget_amount, 
                            (-1*a.balance) variance,
                            0 last_balance,  
                            (-1*a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes118' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0)) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0)) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes119' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (a.balance) balance, 
                            0 budget_amount, 
                            (a.balance) variance,
                            0 last_balance,  
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes1110' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0)) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0)) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        --tess

                        -- UNION ALL

                        -- SELECT 
                        --     aac.company_id,
                        --     'tes1115555555555' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     SUM(COALESCE(ccsa.balance,0)) balance, 
                        --     0 budget_amount, 
                        --     SUM(COALESCE(ccsa.balance,0)) variance,
                        --     0 last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes07' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (a.balance) balance, 
                            0 budget_amount, 
                            (a.balance) variance,
                            0 last_balance,  
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}


                    ) AS a 
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'MTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = mtd_start_date,
                        end_date = mtd_end_date,
                        no_detail = " <> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n CC PL MTD Actual.')
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_actual_mtd))
                    self.sudo().env.cr.execute(query_actual_mtd)

                    query_delete = """
                        DELETE FROM cost_center_sum_account
                        where user_id = {user_id}
                    """.format(user_id = self.env.user.id)
                    self.sudo().env.cr.execute(query_delete)

                    query_insert_sum_account_mtd_ly = """
                        insert into cost_center_sum_account (user_id, balance, account_id, analytic_account_id, journal_id, date)
                        select {user_id} AS user_id, sum(a.balance) balance, a.account_id, a.analytic_account_id, a.journal_id, a.date
                        from account_move_line a
                        left join account_move am on am.id = a.move_id
                        left join res_company rc on rc.id = a.company_id
                        where a.account_id is not null 
                        and a.analytic_account_id is not null 
                        and am.state = '{state}'
                        AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                        AND COALESCE(a.date, '{end_date}') <= '{end_date}'
                        and rc.company_corporate_type in ('main','secondary') 
                        group by a.account_id, a.analytic_account_id, a.journal_id, a.date

                    """.format(
                            user_id = self.env.user.id,
                            type_report = self.type_report,
                            type_date = 'MTD',
                            company_id = self.company_id.id,
                            state = self.state,
                            start_date = mtd_start_date_ly,
                            end_date = mtd_end_date_ly,
                            end_date_ly = mtd_end_date,
                            no_detail = " <> 'no_detail' ",
                            filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                            )
                    self.sudo().env.cr.execute(query_insert_sum_account_mtd_ly)


                    # MTD actual LY
                    query_actual_mtd_ly = """
                    INSERT INTO cost_center_report (
                        company_id, move_number, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        cc_dimension_name, budget_id) 
                    SELECT * 
                    FROM (
                        SELECT 
                            aac.company_id,
                            'tes11' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes12' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (-1*a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes13' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALL
                        -- ---tesssss
                        -- SELECT 
                        --     aac.company_id,
                        --     'tes13' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL-LY' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     0 balance, 
                        --     0 budget_amount, 
                        --     0 variance,
                        --     SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '-1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes08' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (-1*a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes1111' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0)) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes1112' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            'tes1113' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            SUM(COALESCE(ccsa.balance,0)) last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                            
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALl
                        -- ---tessss
                        -- SELECT 
                        --     aac.company_id,
                        --     'tes1113' as move_number,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL-LY' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     0 balance, 
                        --     0 budget_amount, 
                        --     0 variance,
                        --     SUM(COALESCE(ccsa.balance,0)) last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            'tes09' as move_number,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL-LY' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            (a.balance) last_balance, 
                            (a.balance) last_variance, 
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}
                        


                    ) AS a 
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'MTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = mtd_start_date_ly,
                        end_date = mtd_end_date_ly,
                        end_date_ly = mtd_end_date,
                        no_detail = " <> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n CC PL MTD Actual LY.')
                    open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_actual_mtd_ly))
                    self.sudo().env.cr.execute(query_actual_mtd_ly)

                    # MTD budget not include consumables & drugs
                    query_budget_mtd1 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    SELECT 
                        aac.company_id, 
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0)) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0)) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes14' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code not in ('5301000000','5302000000')
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        AND ccdl.sign_on_report != '-1'
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

           
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'MTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = mtd_start_date,
                        end_date = mtd_end_date,
                        no_detail = " <> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_mtd1)


                    # MTD budget not include consumables & drugs
                    query_budget_mtd2 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    

                    SELECT 
                        aac.company_id, 
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes14' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code not in ('5301000000','5302000000')
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        AND ccdl.sign_on_report != '1'
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'MTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = mtd_start_date,
                        end_date = mtd_end_date,
                        no_detail = " <> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_mtd2)




                    # MTD budget consumables & drugs only
                    query_budget_mtd3 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    SELECT 
                        aac.company_id, 
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0)) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0)) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes14' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_journal aj on aj.id = ccdl.journal_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code in ('5301000000','5302000000')
                        --AND aj.name ='Sales Cost'
                        AND aj.name->>'en_US' ='Sales Cost'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        AND ccdl.sign_on_report != '-1'
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

           
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'MTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = mtd_start_date,
                        end_date = mtd_end_date,
                        no_detail = " <> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_mtd3)


                    # MTD budget consumables & drugs only
                    query_budget_mtd4 = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        move_id, move_number, cc_dimension_name, budget_id) 
                    

                    SELECT 
                        aac.company_id, 
                        {user_id} AS create_uid, 
                        {user_id} AS write_uid, 
                        CURRENT_TIMESTAMP AS create_date, 
                        CURRENT_TIMESTAMP AS write_date, 
                        'BUDGET' type_data, 
                        '{type_report}' AS type_report, 
                        {user_id} AS user_id, 
                        aa.id account_id, 
                        aac.id analytic_id, 
                        aap.id parent_analytic_id, 
                        '{type_date}' as type_date, 
                        0 balance, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) budget_amount, 
                        SUM(COALESCE(cbl.planned_amount,0) * -1) variance,
                        0 last_balance, 
                        0 last_variance,
                        hdp.id department_id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}') date,
                        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        ccd.id cc_dimension_id, null::integer move_id, 'tes14' as move_number, 
                        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        left join account_journal aj on aj.id = ccdl.journal_id
                        left join account_account aa on aa.id = ccdl.account_id
                        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                        LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                        LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                        LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                        LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                        AND LEFT(aac.code,1) <> '1' --bukan asset  
                        AND aac.active=true --active
                        -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        AND aac.company_id = {company_id} 
                        AND ccdl.company_id = {company_id}
                        AND aa.code in ('5301000000','5302000000')
                        --AND aj.name ='Sales Cost'
                        AND aj.name->>'en_US' ='Sales Cost'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                        AND cbl.date_from >= '{start_date}' 
                        AND cbl.date_to <= '{end_date}' 
                        AND ccdl.sign_on_report != '1'
                        {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                        ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                    
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'MTD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = mtd_start_date,
                        end_date = mtd_end_date,
                        no_detail = " <> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    self.sudo().env.cr.execute(query_budget_mtd4)
                    
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n MTD ACTUAL.')
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_insert_sum_account_mtd))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_mtd))

                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n MTD ACTUAL LY.')
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_insert_sum_account_mtd_ly))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_mtd_ly))

                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n MTD Budget.')
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_mtd1))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_mtd2))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_mtd3))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_mtd4))




                    # self.sudo().env.cr.execute(query_actual_mtd)
                    # self.sudo().env.cr.execute(query_actual_mtd_ly)
                    # self.sudo().env.cr.execute(query_budget_mtd)



            # Trend Report
            if self.type_report == '2':

                # YTD generate 
                if self.type_period in['PERIOD']:


                    query_delete = """
                            DELETE FROM cost_center_sum_account
                            where user_id = {user_id}
                        """.format(user_id = self.env.user.id)
                    self.sudo().env.cr.execute(query_delete)


                    query_insert_sum_account_actual_period = """
                        insert into cost_center_sum_account (user_id, balance, account_id, analytic_account_id, journal_id, date)
                        select {user_id} AS user_id, sum(a.balance) balance, a.account_id, a.analytic_account_id, a.journal_id, a.date
                        from account_move_line a
                        left join account_move am on am.id = a.move_id
                        left join res_company rc on rc.id = a.company_id
                        where a.account_id is not null 
                        and a.analytic_account_id is not null 
                        and am.state = '{state}'
                        AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                        AND COALESCE(a.date, '{end_date}') <= '{end_date}'
                        and rc.company_corporate_type in ('main','secondary') 
                        group by a.account_id, a.analytic_account_id, a.journal_id, a.date

                    """.format(
                            user_id = self.env.user.id,
                            type_report = self.type_report,
                            type_date = 'PERIOD',
                            company_id = self.company_id.id,
                            state = self.state,
                            start_date = per_start_date,
                            end_date = per_end_date,
                            no_detail = " <> 'no_detail' ",
                            filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                            )
                    self.sudo().env.cr.execute(query_insert_sum_account_actual_period)


                    # Period actual 
                    query_actual_period = """
                    INSERT INTO cost_center_report (
                        company_id, create_uid, write_uid, create_date, write_date, 
                        type_data, type_report, user_id, account_id, 
                        analytic_account_id, parent_analytic_id, 
                        type_date, balance, budget_amount, variance,
                        last_balance, last_variance, 
                        department_id, head_id, date, 
                        cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                        cc_dimension_name, budget_id) 
                    SELECT * 
                    FROM (
            SELECT 
                            {company_id} company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            null account_id, 
                            null analytic_id, 
                            null parent_analytic_id, 
                            '{type_date}' as type_date, 
                            0 balance, 
                            0 budget_amount, 
                            0 variance,
                            0 last_balance, 
                            0 last_variance,
                            null department_id, null head_id,
                            '{end_date}' date,
                            null cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
            WHERE ccdl.company_id = {company_id}

            UNION ALL

                        SELECT 
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0) * -1) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            AND aac.company_id = {company_id} 
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (-1*a.balance) balance, 
                            0 budget_amount, 
                            (-1*a.balance) variance,
                            0 last_balance, 
                            a.balance last_variance,  
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0) * -1) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '-1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            AND aac.company_id = {company_id} 
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALL
                        -- --tessss
                        -- SELECT 
                        --     aac.company_id,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) balance, 
                        --     0 budget_amount, 
                        --     SUM(COALESCE(ccsa.balance,0) * -1) variance,
                        --     0 last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id,
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '-1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        --     AND aac.company_id = {company_id} 
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (-1*a.balance) balance, 
                            0 budget_amount, 
                            (-1*a.balance) variance,
                            0 last_balance, 
                            a.balance last_variance,  
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '-1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}


                        UNION ALL

                        SELECT 
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0)) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0)) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.user_id = {user_id}
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            AND aac.company_id = {company_id} 
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                        
                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (a.balance) balance, 
                            0 budget_amount, 
                            (a.balance) variance,
                            0 last_balance, 
                            a.balance last_variance,  
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND ccdl.journal_id is null
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}

                        UNION ALL

                        SELECT 
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            aa.id account_id, 
                            aac.id analytic_id, 
                            aap.id parent_analytic_id, 
                            '{type_date}' as type_date, 
                            SUM(COALESCE(ccsa.balance,0)) balance, 
                            0 budget_amount, 
                            SUM(COALESCE(ccsa.balance,0)) variance,
                            0 last_balance, 
                            SUM(COALESCE(ccsa.balance,0)) last_variance,
                            hdp.id department_id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}') date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        from cost_center_dimension_line ccdl
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                            left join account_account aa on aa.id = ccdl.account_id
                            LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                            left join account_analytic_account aap ON aap.id=aac.parent_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id and ccsa.journal_id = ccdl.journal_id and ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        WHERE aac.type_analytic = 'expense' 
                            AND LEFT(aac.code,1) <> '1' --bukan asset  
                            AND aac.active = true --active
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            AND ccdl.company_id = {company_id}
                            AND ccd.sign_on_report != '1'
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                            AND aac.company_id = {company_id} 
                            {filter_ids}
                        GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                            COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                            CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        -- UNION ALL
                        -- ---tesss
                        -- SELECT 
                        --     aac.company_id,
                        --     {user_id} AS create_uid, 
                        --     {user_id} AS write_uid, 
                        --     CURRENT_TIMESTAMP AS create_date, 
                        --     CURRENT_TIMESTAMP AS write_date, 
                        --     'ACTUAL' AS type_data, 
                        --     '{type_report}' AS type_report, 
                        --     {user_id} AS user_id, 
                        --     aa.id account_id, 
                        --     aac.id analytic_id, 
                        --     aap.id parent_analytic_id, 
                        --     '{type_date}' as type_date, 
                        --     SUM(COALESCE(ccsa.balance,0)) balance, 
                        --     0 budget_amount, 
                        --     SUM(COALESCE(ccsa.balance,0)) variance,
                        --     0 last_balance, 
                        --     SUM(COALESCE(ccsa.balance,0)) last_variance,
                        --     hdp.id department_id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}') date,
                        --     ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                        --     ccd.id cc_dimension_id,
                        --     CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        -- from cost_center_dimension_line ccdl
                        --     left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        --     left join account_journal aj on aj.id = ccdl.journal_id
                        --     LEFT JOIN cost_center_sum_account ccsa on ccsa.account_id = ccdl.account_id and ccsa.user_id = {user_id}
                        --     left join account_account aa on aa.id = ccsa.account_id
                        --     LEFT JOIN account_analytic_account aac ON aac.id = ccsa.analytic_account_id
                        --     left join account_analytic_account aap ON aap.id=aac.parent_id
                        --     LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                        --     LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            
                            
                        -- WHERE aac.type_analytic = 'expense' 
                        --     AND LEFT(aac.code,1) <> '1' --bukan asset  
                        --     AND LEFT(aac.code,10) <> LEFT(aa.code,10)
                        --     AND aj.name = 'Store Consumption Cost' 
                        --     AND aj.company_id = 3
                        --     AND aac.active = true --active
                        --     AND ccdl.account_id is not null
                        --     AND coalesce(ccdl.journal_id, 0000000) != 0000000
                        --     AND ccdl.company_id = {company_id}
                        --     AND ccd.sign_on_report != '1'
                        --     AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                        --     AND aac.company_id = {company_id} 
                        --     {filter_ids}
                        -- GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                        --     COALESCE(ccsa.date, '{end_date}'), ccm.id, ccd.parent_id, ccd.id, 
                        --     CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        UNION ALL

                        -- COST CENTER IMPORT
                        SELECT
                            aac.company_id,
                            {user_id} AS create_uid, 
                            {user_id} AS write_uid, 
                            CURRENT_TIMESTAMP AS create_date, 
                            CURRENT_TIMESTAMP AS write_date, 
                            'ACTUAL' AS type_data, 
                            '{type_report}' AS type_report, 
                            {user_id} AS user_id, 
                            a.account_id, 
                            a.analytic_account_id, 
                            a.parent_analytic_id, 
                            '{type_date}' as type_date, 
                            (a.balance) balance, 
                            0 budget_amount, 
                            (a.balance) variance,
                            0 last_balance, 
                            a.balance last_variance,  
                            hdp.id department_id, 
                            hdp.head_id, a.date,
                            ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                            ccd.id cc_dimension_id,
                            CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                        FROM cost_center_import a 
                            INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                            LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                            LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                            left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id and ccdl.journal_id = a.journal_id
                            left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                        WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                            AND aac.active=true  --selalu yang masih aktif
                            AND ccd.sign_on_report != '1'
                            AND ccdl.account_id is not null
                            AND coalesce(ccdl.journal_id, 0000000) != 0000000
                            -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                            AND aac.company_id = {company_id}  --company_id 
                            AND a.company_id = {company_id}
                            AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                            AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                            {filter_ids}


                    ) AS a 
                    """.format(
                        user_id = self.env.user.id,
                        type_report = self.type_report,
                        type_date = 'PERIOD',
                        company_id = self.company_id.id,
                        state = self.state,
                        start_date = per_start_date,
                        end_date = per_end_date,
                        no_detail = " <> 'no_detail' ",
                        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )


                    #query_delete = """
                    #        DELETE FROM cost_center_sum_account
                    #    """.format(user_id = self.env.user.id)
                    #self.sudo().env.cr.execute(query_delete)


                    #query_insert_sum_account_actual_period_ly = """
                    #    insert into cost_center_sum_account (balance, account_id, analytic_account_id, journal_id, date)
                    #    select sum(a.balance) balance, a.account_id, a.analytic_account_id, a.journal_id, a.date
                    #    from account_move_line a
                    #    left join account_move am on am.id = a.move_id
                    #    where a.account_id is not null 
                    #    and a.analytic_account_id is not null 
                    #    and am.state = '{state}'
                    #    AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                    #    AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                    #    and a.company_id = {company_id}
                    #    group by a.account_id, a.analytic_account_id, a.journal_id, a.date

                    #""".format(
                    #        user_id = self.env.user.id,
                    #        type_report = self.type_report,
                    #        type_date = 'PERIOD',
                    #        company_id = self.company_id.id,
                    #        state = self.state,
                    #        start_date = per_start_date_ly,
                    #        end_date = per_end_date_ly,
                    #        end_date_ly = per_end_date,
                    #        no_detail = " <> 'no_detail' ",
                    #        filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    #        )
                    #self.sudo().env.cr.execute(query_insert_sum_account_actual_period_ly)

                    


                    ## YTD actual LY
                    #query_actual_period_ly = """
                    #INSERT INTO cost_center_report (
                    #    company_id, create_uid, write_uid, create_date, write_date, 
                    #    type_data, type_report, user_id, account_id, 
                    #    analytic_account_id, parent_analytic_id, 
                    #    type_date, balance, budget_amount, variance,
                    #    last_balance, last_variance, 
                    #    department_id, head_id, date, 
                    #    cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                    #    cc_dimension_name, budget_id)
                    #SELECT * 
                    #FROM (
                    #    SELECT 
                    #        aa.company_id, 
                    #        {user_id} AS create_uid, 
                    #        {user_id} AS write_uid, 
                    #        CURRENT_TIMESTAMP AS create_date, 
                    #        CURRENT_TIMESTAMP AS write_date, 
                    #        'ACTUAL-LY' type_data, 
                    #        '{type_report}' AS type_report, 
                    #        {user_id} AS user_id, 
                    #        aa.id account_id, 
                    #        aac.id analytic_id, 
                    #        aap.id parent_analytic_id, 
                    #        '{type_date}' as type_date, 
                    #        0 balance, 
                    #        0 budget_amount, 
                    #        0 variance,
                    #        SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                    #        SUM(0 - (COALESCE(ccsa.balance,0) * -1)) last_variance,
                    #        hdp.id department_id, hdp.head_id,
                    #        (date(COALESCE(ccsa.date, '{end_date}')) + interval '1 year') date,
                    #        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                    #        ccd.id cc_dimension_id, 
                    #        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null budget_id
                    #    from cost_center_dimension_line ccdl
                    #        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                    #        left join account_account aa on aa.id = ccdl.account_id
                    #        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                    #        left join account_analytic_account aap ON aap.id=aac.parent_id
                    #        LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                    #        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    #        LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id
                    #    WHERE aac.type_analytic = 'expense' 
                    #        AND LEFT(aac.code,1) <> '1' --bukan asset  
                    #        AND aac.active=true --active
                    #        AND ccdl.account_id is not null
                    #        AND ccdl.journal_id is null
                    #        AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                    #        AND aac.company_id = {company_id} 
                    #        {filter_ids}
                    #    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                    #        (date(COALESCE(ccsa.date, '{end_date}')) + interval '1 year'),
                    #        ccm.id, ccd.parent_id, ccd.id, 
                    #        CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                        
                    #    UNION ALL 

                    #    -- COST CENTER IMPORT
                    #    SELECT
                    #        aac.company_id,
                    #        {user_id} AS create_uid, 
                    #        {user_id} AS write_uid, 
                    #        CURRENT_TIMESTAMP AS create_date, 
                    #        CURRENT_TIMESTAMP AS write_date, 
                    #        'ACTUAL-LY' AS type_data, 
                    #        '{type_report}' AS type_report, 
                    #        {user_id} AS user_id, 
                    #        a.account_id, 
                    #        a.analytic_account_id, 
                    #        a.parent_analytic_id, 
                    #        '{type_date}' as type_date, 
                    #        0 balance, 
                    #        0 budget_amount, 
                    #        0 variance,
                    #        a.balance last_balance, 
                    #        a.balance last_variance, 
                    #        hdp.id department_id, hdp.head_id, 
                    #        (date(COALESCE(a.date, '{end_date}')) + interval '1 year') date, 
                    #        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                    #        ccd.id cc_dimension_id,
                    #        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null::integer budget_id 
                    #    FROM cost_center_import a 
                    #        INNER JOIN account_analytic_account aac ON aac.id = a.analytic_account_id
                    #        LEFT JOIN cost_center_master ccm ON ccm.id = a.cost_master_id
                    #        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    #        left join cost_center_dimension_line ccdl on ccdl.account_id = a.account_id
                    #        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                    #    WHERE LEFT(aac.code,1) <> '1' --bukan asset 
                    #        AND aac.active=true  --selalu yang masih aktif
                    #        AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) 
                    #        AND aac.company_id = {company_id}  --company_id 
                    #        AND COALESCE(a.date, '{start_date}') >= '{start_date}' 
                    #        AND COALESCE(a.date, '{end_date}') <= '{end_date}' 
                    #        {filter_ids}


                    #    UNION ALL


                    #    SELECT 
                    #        aa.company_id, 
                    #        {user_id} AS create_uid, 
                    #        {user_id} AS write_uid, 
                    #        CURRENT_TIMESTAMP AS create_date, 
                    #        CURRENT_TIMESTAMP AS write_date, 
                    #        'ACTUAL-LY' type_data, 
                    #        '{type_report}' AS type_report, 
                    #        {user_id} AS user_id, 
                    #        aa.id account_id, 
                    #        aac.id analytic_id, 
                    #        aap.id parent_analytic_id, 
                    #        '{type_date}' as type_date, 
                    #        0 balance, 
                    #        0 budget_amount, 
                    #        0 variance,
                    #        SUM(COALESCE(ccsa.balance,0) * -1) last_balance, 
                    #        SUM(0 - (COALESCE(ccsa.balance,0) * -1)) last_variance,
                    #        hdp.id department_id, hdp.head_id,
                    #        (date(COALESCE(ccsa.date, '{end_date}')) + interval '1 year') date,
                    #        ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                    #        ccd.id cc_dimension_id,
                    #        CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null budget_id
                    #    from cost_center_dimension_line ccdl
                    #        left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                    #        left join account_account aa on aa.id = ccdl.account_id
                    #        LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                    #        left join account_analytic_account aap ON aap.id=aac.parent_id
                    #        LEFT JOIN cost_center_master ccm ON ccm.id = aac.cost_master_id AND ccm.company_id = aac.company_id
                    #        LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    #        LEFT JOIN cost_center_sum_account ccsa on ccsa.analytic_account_id = aac.id
                    #    WHERE aac.type_analytic = 'expense' 
                    #        AND LEFT(aac.code,1) <> '1' --bukan asset  
                    #        AND aac.active=true --active
                    #        AND ccdl.account_id is not null
                    #        AND coalesce(ccdl.journal_id, 0000000) != 0000000
                    #        AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                    #        AND aac.company_id = {company_id} 
                    #        {filter_ids}
                    #    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                    #        (date(COALESCE(ccsa.date, '{end_date}')) + interval '1 year'),
                    #        ccm.id, ccd.parent_id, ccd.id, 
                    #        CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                    #) AS a
                    #""".format(
                    #    user_id = self.env.user.id,
                    #    type_report = self.type_report,
                    #    type_date = 'PERIOD',
                    #    company_id = self.company_id.id,
                    #    state = self.state,
                    #    start_date = per_start_date_ly,
                    #    end_date = per_end_date_ly,
                    #    end_date_ly = per_end_date,
                    #    no_detail = " <> 'no_detail' ",
                    #    filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    #)


                    ## YTD budget 
                    #query_budget_period = """
                    #INSERT INTO cost_center_report (
                    #    company_id, create_uid, write_uid, create_date, write_date, 
                    #    type_data, type_report, user_id, account_id, 
                    #    analytic_account_id, parent_analytic_id, 
                    #    type_date, balance, budget_amount, variance,
                    #    last_balance, last_variance, 
                    #    department_id, head_id, date, 
                    #    cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                    #    move_id, move_number, cc_dimension_name, budget_id) 
                    #SELECT 
                    #    aac.company_id,
                    #    {user_id} AS create_uid, 
                    #    {user_id} AS write_uid, 
                    #    CURRENT_TIMESTAMP AS create_date, 
                    #    CURRENT_TIMESTAMP AS write_date, 
                    #    'BUDGET' type_data, 
                    #    '{type_report}' AS type_report, 
                    #    {user_id} AS user_id, 
                    #    aa.id account_id, 
                    #    aac.id analytic_id, 
                    #    aap.id parent_analytic_id, 
                    #    '{type_date}' as type_date, 
                    #    0 balance, 
                    #    SUM(COALESCE(cbl.planned_amount,0)) budget_amount, 
                    #    SUM(COALESCE(cbl.planned_amount,0) - 0) variance,
                    #    0 last_balance, 
                    #    0 last_variance,
                    #    hdp.id department_id, hdp.head_id,
                    #    COALESCE(cbl.date_from, '{end_date}') date,
                    #    ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                    #    ccd.id cc_dimension_id, null::integer move_id, null move_number, 
                    #    CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    #from cost_center_dimension_line ccdl
                    #    left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                    #    left join account_account aa on aa.id = ccdl.account_id
                    #    LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                    #    LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                    #    LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                    #    LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                    #    LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                    #    LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    #WHERE aac.type_analytic = 'expense' 
                    #    AND LEFT(aac.code,1) <> '1' --bukan asset  
                    #    AND aac.active=true --active
                    #    AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                    #    AND aac.company_id = {company_id} 
                    #    -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                    #    AND cbl.date_from >= '{start_date}' 
                    #    AND cbl.date_to <= '{end_date}' 
                    #    {filter_ids}
                    #GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                    #    COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                    #    ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                    #""".format(
                    #    user_id = self.env.user.id,
                    #    type_report = self.type_report,
                    #    type_date = 'PERIOD',
                    #    company_id = self.company_id.id,
                    #    state = self.state,
                    #    start_date = per_start_date,
                    #    end_date = per_end_date,
                    #    no_detail = " <> 'no_detail' ",
                    #    filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    #)
                    #open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n CC PL YTD Budget.')
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_period))
                    #open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_period_ly))
                    #open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_period))
                    

                    self.sudo().env.cr.execute(query_actual_period)
                    #self.sudo().env.cr.execute(query_actual_period_ly)
                    #self.sudo().env.cr.execute(query_budget_period)


            

                
            # Trend Budget Report
            if self.type_report == '3':

                # YTD generate 
                if self.type_period in['PERIOD']:


                    # YTD budget not include consumables & drugs
                    query_budget_period1 = """
                    INSERT INTO cost_center_report (
                       company_id, create_uid, write_uid, create_date, write_date, 
                       type_data, type_report, user_id, account_id, 
                       analytic_account_id, parent_analytic_id, 
                       type_date, balance, budget_amount, variance,
                       last_balance, last_variance, 
                       department_id, head_id, date, 
                       cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                       move_id, move_number, cc_dimension_name, budget_id) 
                    SELECT 
                       aac.company_id,
                       {user_id} AS create_uid, 
                       {user_id} AS write_uid, 
                       CURRENT_TIMESTAMP AS create_date, 
                       CURRENT_TIMESTAMP AS write_date, 
                       'BUDGET' type_data, 
                       '{type_report}' AS type_report, 
                       {user_id} AS user_id, 
                       aa.id account_id, 
                       aac.id analytic_id, 
                       aap.id parent_analytic_id, 
                       '{type_date}' as type_date, 
                       0 balance, 
                       SUM(COALESCE(cbl.planned_amount,0)) budget_amount, 
                       SUM(COALESCE(cbl.planned_amount,0)) variance,
                       0 last_balance, 
                       0 last_variance,
                       hdp.id department_id, hdp.head_id,
                       COALESCE(cbl.date_from, '{end_date}') date,
                       ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                       ccd.id cc_dimension_id, null::integer move_id, null move_number, 
                       CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                       left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                       left join account_account aa on aa.id = ccdl.account_id
                       LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                       LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                       LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                       LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                       LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                       LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                       AND LEFT(aac.code,1) <> '1' --bukan asset  
                       AND aac.active=true --active
                       -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                       AND aac.company_id = {company_id} 
                       AND ccdl.company_id = {company_id}
                       AND aa.code not in ('5301000000','5302000000')
                       -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                       AND cbl.date_from >= '{start_date}' 
                       AND cbl.date_to <= '{end_date}' 
                       AND ccdl.sign_on_report != '-1'
                       {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                       COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                       ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                   
                    """.format(
                       user_id = self.env.user.id,
                       type_report = self.type_report,
                       type_date = 'PERIOD',
                       company_id = self.company_id.id,
                       state = self.state,
                       start_date = per_start_date,
                       end_date = per_end_date,
                       no_detail = " <> 'no_detail' ",
                       filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )

                    # YTD budget not include consumables & drugs
                    query_budget_period2 = """
                    INSERT INTO cost_center_report (
                       company_id, create_uid, write_uid, create_date, write_date, 
                       type_data, type_report, user_id, account_id, 
                       analytic_account_id, parent_analytic_id, 
                       type_date, balance, budget_amount, variance,
                       last_balance, last_variance, 
                       department_id, head_id, date, 
                       cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                       move_id, move_number, cc_dimension_name, budget_id) 
                    

                    SELECT 
                       aac.company_id,
                       {user_id} AS create_uid, 
                       {user_id} AS write_uid, 
                       CURRENT_TIMESTAMP AS create_date, 
                       CURRENT_TIMESTAMP AS write_date, 
                       'BUDGET' type_data, 
                       '{type_report}' AS type_report, 
                       {user_id} AS user_id, 
                       aa.id account_id, 
                       aac.id analytic_id, 
                       aap.id parent_analytic_id, 
                       '{type_date}' as type_date, 
                       0 balance, 
                       SUM(COALESCE(cbl.planned_amount,0) * -1) budget_amount, 
                       SUM(COALESCE(cbl.planned_amount,0) * -1) variance,
                       0 last_balance, 
                       0 last_variance,
                       hdp.id department_id, hdp.head_id,
                       COALESCE(cbl.date_from, '{end_date}') date,
                       ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                       ccd.id cc_dimension_id, null::integer move_id, null move_number, 
                       CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                       left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                       left join account_account aa on aa.id = ccdl.account_id
                       LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                       LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                       LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                       LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                       LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                       LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                       AND LEFT(aac.code,1) <> '1' --bukan asset  
                       AND aac.active=true --active
                       -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                       AND aac.company_id = {company_id} 
                       AND ccdl.company_id = {company_id}
                       AND aa.code not in ('5301000000','5302000000')
                       -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                       AND cbl.date_from >= '{start_date}' 
                       AND cbl.date_to <= '{end_date}' 
                       AND ccdl.sign_on_report != '1'
                       {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                       COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                       ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                    """.format(
                       user_id = self.env.user.id,
                       type_report = self.type_report,
                       type_date = 'PERIOD',
                       company_id = self.company_id.id,
                       state = self.state,
                       start_date = per_start_date,
                       end_date = per_end_date,
                       no_detail = " <> 'no_detail' ",
                       filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )



                    # YTD budget consumables & drugs only
                    query_budget_period3 = """
                    INSERT INTO cost_center_report (
                       company_id, create_uid, write_uid, create_date, write_date, 
                       type_data, type_report, user_id, account_id, 
                       analytic_account_id, parent_analytic_id, 
                       type_date, balance, budget_amount, variance,
                       last_balance, last_variance, 
                       department_id, head_id, date, 
                       cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                       move_id, move_number, cc_dimension_name, budget_id) 
                    SELECT 
                       aac.company_id,
                       {user_id} AS create_uid, 
                       {user_id} AS write_uid, 
                       CURRENT_TIMESTAMP AS create_date, 
                       CURRENT_TIMESTAMP AS write_date, 
                       'BUDGET' type_data, 
                       '{type_report}' AS type_report, 
                       {user_id} AS user_id, 
                       aa.id account_id, 
                       aac.id analytic_id, 
                       aap.id parent_analytic_id, 
                       '{type_date}' as type_date, 
                       0 balance, 
                       SUM(COALESCE(cbl.planned_amount,0)) budget_amount, 
                       SUM(COALESCE(cbl.planned_amount,0)) variance,
                       0 last_balance, 
                       0 last_variance,
                       hdp.id department_id, hdp.head_id,
                       COALESCE(cbl.date_from, '{end_date}') date,
                       ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                       ccd.id cc_dimension_id, null::integer move_id, null move_number, 
                       CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                       left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                       left join account_journal aj on aj.id = ccdl.journal_id
                       left join account_account aa on aa.id = ccdl.account_id
                       LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                       LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                       LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                       LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                       LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                       LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                       AND LEFT(aac.code,1) <> '1' --bukan asset  
                       AND aac.active=true --active
                       -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                       AND aac.company_id = {company_id} 
                       AND ccdl.company_id = {company_id}
                       AND aa.code in ('5301000000','5302000000')
                       --AND aj.name ='Sales Cost'
                       AND aj.name->>'en_US' ='Sales Cost'
                        -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                       AND cbl.date_from >= '{start_date}' 
                       AND cbl.date_to <= '{end_date}' 
                       AND ccdl.sign_on_report != '-1'
                       {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                       COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                       ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id

                   
                    """.format(
                       user_id = self.env.user.id,
                       type_report = self.type_report,
                       type_date = 'PERIOD',
                       company_id = self.company_id.id,
                       state = self.state,
                       start_date = per_start_date,
                       end_date = per_end_date,
                       no_detail = " <> 'no_detail' ",
                       filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )

                    # YTD budget consumables & drugs only
                    query_budget_period4 = """
                    INSERT INTO cost_center_report (
                       company_id, create_uid, write_uid, create_date, write_date, 
                       type_data, type_report, user_id, account_id, 
                       analytic_account_id, parent_analytic_id, 
                       type_date, balance, budget_amount, variance,
                       last_balance, last_variance, 
                       department_id, head_id, date, 
                       cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                       move_id, move_number, cc_dimension_name, budget_id) 
                    

                    SELECT 
                       aac.company_id,
                       {user_id} AS create_uid, 
                       {user_id} AS write_uid, 
                       CURRENT_TIMESTAMP AS create_date, 
                       CURRENT_TIMESTAMP AS write_date, 
                       'BUDGET' type_data, 
                       '{type_report}' AS type_report, 
                       {user_id} AS user_id, 
                       aa.id account_id, 
                       aac.id analytic_id, 
                       aap.id parent_analytic_id, 
                       '{type_date}' as type_date, 
                       0 balance, 
                       SUM(COALESCE(cbl.planned_amount,0) * -1) budget_amount, 
                       SUM(COALESCE(cbl.planned_amount,0) * -1) variance,
                       0 last_balance, 
                       0 last_variance,
                       hdp.id department_id, hdp.head_id,
                       COALESCE(cbl.date_from, '{end_date}') date,
                       ccm.id cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                       ccd.id cc_dimension_id, null::integer move_id, null move_number, 
                       CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, cb.id budget_id
                    from cost_center_dimension_line ccdl
                       left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                       left join account_journal aj on aj.id = ccdl.journal_id
                       left join account_account aa on aa.id = ccdl.account_id
                       LEFT JOIN account_analytic_account aac ON LEFT(aac.code, 10) = LEFT(aa.code,10) AND aa.company_id = aac.company_id
                       LEFT JOIN account_analytic_account aap ON aap.id = aac.parent_id
                       LEFT JOIN crossovered_budget_lines cbl ON cbl.analytic_account_id = aac.id 
                       LEFT JOIN crossovered_budget cb ON cb.id = cbl.crossovered_budget_id
                       LEFT JOIN cost_center_master ccm ON ccm."id" = aac.cost_master_id
                       LEFT JOIN hr_department hdp ON hdp.id = ccm.department_id
                    WHERE aac.type_analytic = 'expense' 
                       AND LEFT(aac.code,1) <> '1' --bukan asset  
                       AND aac.active=true --active
                       -- AND NOT EXISTS (SELECT 1 FROM account_analytic_account t WHERE t.parent_id = aac.id) --not have childs
                       AND aac.company_id = {company_id} 
                       AND ccdl.company_id = {company_id}
                       AND aa.code in ('5301000000','5302000000')
                       --AND aj.name ='Sales Cost'
                       AND aj.name->>'en_US' ='Sales Cost'
                         -- AND COALESCE(cc.move_state, '{state}') = '{state}' 
                       AND cbl.date_from >= '{start_date}' 
                       AND cbl.date_to <= '{end_date}' 
                       AND ccdl.sign_on_report != '1'
                       {filter_ids}
                    GROUP BY aa.id, aac.id, aap.id, hdp.id, hdp.head_id,
                       COALESCE(cbl.date_from, '{end_date}'), ccm.id, ccd.parent_id,
                       ccd.id, cb.id, CONCAT(ccd.sequence, ' - ', ccd.name), aac.company_id
                    """.format(
                       user_id = self.env.user.id,
                       type_report = self.type_report,
                       type_date = 'PERIOD',
                       company_id = self.company_id.id,
                       state = self.state,
                       start_date = per_start_date,
                       end_date = per_end_date,
                       no_detail = " <> 'no_detail' ",
                       filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )

                    query_budget_period_null = """
                    INSERT INTO cost_center_report (
                       company_id, create_uid, write_uid, create_date, write_date, 
                       type_data, type_report, user_id, account_id, 
                       analytic_account_id, parent_analytic_id, 
                       type_date, balance, budget_amount, variance,
                       last_balance, last_variance, 
                       department_id, head_id, date, 
                       cost_master_id, parent_cc_dimension_id, cc_dimension_id, 
                       move_id, move_number, cc_dimension_name, budget_id) 
                    SELECT 
                       {company_id} company_id,
                       {user_id} AS create_uid, 
                       {user_id} AS write_uid, 
                       CURRENT_TIMESTAMP AS create_date, 
                       CURRENT_TIMESTAMP AS write_date, 
                       'BUDGET' type_data, 
                       '{type_report}' AS type_report, 
                       {user_id} AS user_id, 
                       null account_id, 
                       null analytic_id, 
                       null parent_analytic_id, 
                       '{type_date}' as type_date, 
                       0 balance, 
                       0 budget_amount, 
                       0 variance,
                       0 last_balance, 
                       0 last_variance,
                       null department_id, null head_id,
                       '{end_date}' date,
                       null cost_master_id, ccd.parent_id parent_cc_dimension_id, 
                       ccd.id cc_dimension_id, null::integer move_id, null move_number, 
                       CONCAT(ccd.sequence, ' - ', ccd.name) cc_dimension_name, null budget_id
                    from cost_center_dimension_line ccdl
                       left join cost_center_dimension ccd on ccd.id = ccdl.dimension_id
                       
                    WHERE ccdl.company_id = {company_id}
                    
                    """.format(
                       user_id = self.env.user.id,
                       type_report = self.type_report,
                       type_date = 'PERIOD',
                       company_id = self.company_id.id,
                       state = self.state,
                       start_date = per_start_date,
                       end_date = per_end_date,
                       no_detail = " <> 'no_detail' ",
                       filter_ids = (account_ids if self.type_filter in ['1', '2'] else " ")
                    )
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n CC PL YTD Budget.')
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_period))
                    # open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_actual_period_ly))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_period1))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_period2))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_period3))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_period4))
                    open('/opt/odoo16/logs/belajar.log', 'a+').write('\n\n' + str(query_budget_period_null))
                    

                    # self.sudo().env.cr.execute(query_actual_period)
                    # self.sudo().env.cr.execute(query_actual_period_ly)
                    self.sudo().env.cr.execute(query_budget_period1)
                    self.sudo().env.cr.execute(query_budget_period2)
                    self.sudo().env.cr.execute(query_budget_period3)
                    self.sudo().env.cr.execute(query_budget_period4)
                    self.sudo().env.cr.execute(query_budget_period_null)   

                # query_delete = """
                #     DELETE FROM cost_center_report
                #     WHERE user_id = {user_id} 
                #     AND pl_name LIKE '%- 1 -%'
                # """.format(user_id = self.env.user.id)
                # open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n Delete BS.')
                # open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_delete))
                # self.sudo().env.cr.execute(query_delete)

                # query_delete_parent = """
                #     DELETE FROM cost_center_report
                #     WHERE user_id = {user_id} 
                #     AND parent_pl_id IN (
                #         SELECT id FROM account_financial_report t
                #         WHERE t.name LIKE '%- 1 -%')
                # """.format(user_id = self.env.user.id)
                # open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n Delete BS Child.')
                # open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_delete_parent))
                # self.sudo().env.cr.execute(query_delete_parent)

                # # delete parent Not Profit Loss
                # query_delete_parent = """
                #     DELETE FROM cost_center_report
                #     WHERE user_id = {user_id} 
                #     AND parent_pl_id IN (
                #         SELECT id FROM account_financial_report t
                #         WHERE t.name NOT LIKE '%Profit and Loss%')
                # """.format(user_id = self.env.user.id)
                # open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n Delete Child of Parent not Profit Loss.')
                # open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n\n' + str(query_delete_parent))
                # self.sudo().env.cr.execute(query_delete_parent)
                

    # @api.multi 
    def show_report(self):
        # generate report first
        self.generate_report()

        # show action windows
        type_report = dict(self.sudo().env['cost.center.report.wizard']._fields['type_report'].selection)
        for key, value in type_report.items():
            action = {}
            action['target'] = 'current'
            action['domain'] = "[('user_id', '=', %s), ('type_report', '=', %s)]" % (self.env.user.id, self.type_report)
            action['type'] = 'ir.actions.act_window'
            action['view_mode'] = 'tree,form,pivot'
            action['view_type'] = 'form'
            action['res_model'] = 'cost.center.report'
            action['name'] = 'Cost Center Report'

            if self.type_report == '1':
                action['views'] = [(self.sudo().env.ref('mayapada.view_cost_center_detail_pivot').id, 'pivot'),(False, 'form'), (False, 'tree')]
            if self.type_report == '2':
                action['views'] = [(self.sudo().env.ref('mayapada.view_cost_center_pl_pivot').id, 'pivot'),(False, 'form'), (False, 'tree')]
            if self.type_report == '3':
                action['views'] = [(self.sudo().env.ref('mayapada.view_cost_center_trend_budget').id, 'pivot'),(False, 'form'), (False, 'tree')]
            
            #open('/opt/odoo16/logs/cost_center_report.log', 'a+').write('\n' + str(action).encode('utf-8'))
            return action


    # @api.multi
    def print_report_xls(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/accounting/cost_center_report?format=xls&id=%s' % (self.id)
        action['target'] = 'new'
        return action

    # @api.multi
    def print_report_pdf(self):
        action = {}
        action['type'] = 'ir.actions.act_url'
        action['url'] = '/accounting/cost_center_report?format=pdf&id=%s' % (self.id)
        action['target'] = 'new'
        return action






class CostCenterMaster(models.Model):
    _name = 'cost.center.master'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    @api.model
    def _get_company(self):
        return self.env.company.id

    company_id = fields.Many2one('res.company',string="Company",required=True,default=_get_company)
    code = fields.Char(string="CC Code",index=True, tracking=True)
    name = fields.Char(string="CC Name",index=True, tracking=True)
    department_id = fields.Many2one('hr.department', string="Division/Department", index=True, tracking=True)
    head_id = fields.Char(string="Head of Division", related='department_id.head_id.name', readonly=False, index=True, store=True)
    analytic_ids = fields.One2many('account.analytic.account','cost_master_id',string="Analytic Account")





class CostCenterReport(models.Model):
    _name = 'cost.center.report'

    company_id = fields.Many2one('res.company', string="Company")
    type_report = fields.Selection([('1', 'Cost Center Report Detail'),('2', 'PnL Cost Center Level Report'),('3', 'Cost Center Trend Report')],string="Report Type",index=True,readonly=False)
    type_data = fields.Char(string="Data Type", index=True, readonly=True)
    type_date = fields.Char(string="Period Type", readonly=True, index=True)
    user_id = fields.Many2one('res.users',string="User Ref.",index=True,readonly=False)
    date = fields.Date(string="Date", readonly=True, index=True)
    
    budget_id = fields.Many2one('crossovered.budget', string="Budget", readonly=True, index=True)
    move_id = fields.Many2one('account.move', string="Journal Entries", readonly=True, index=True)
    move_number = fields.Char(string="Journal No.", index=True, readonly=True)
    
    cost_master_id = fields.Many2one('cost.center.master', string="Cost Center", readonly=True, index=True)
    department_id = fields.Many2one('hr.department', string="Division/Department", readonly=False, index=True)
    head_id = fields.Many2one('res.users', string="Head of Division", readonly=False, index=True)
    
    parent_analytic_id = fields.Many2one('account.analytic.account',string="Analytic (Parent)",index=True,readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account',string="Analytic Account",index=True,readonly=True)
    account_id = fields.Many2one('account.account',string="Account (COA)",index=True,readonly=True)    
    
    parent_pl_id = fields.Many2one('account.financial.report',string="Financial Report (Parent)",readonly=True,index=True)
    pl_id = fields.Many2one('account.financial.report',string="Financial Report (ID)",readonly=True,index=True)
    pl_name = fields.Char(string="Financial Report (Name)",readonly=True,index=True)
    pl_detail = fields.Char(string="Financial Report (Display)", readonly=True,index=True)
    sequence = fields.Integer(string="Financial Report (Sequence)", readonly=True, index=True)

    ###CC Dimensi###
    parent_cc_dimension_id = fields.Many2one('cost.center.dimension',string="Dimension (Parent)",readonly=True,index=True)
    cc_dimension_id = fields.Many2one('cost.center.dimension',string="Dimension (ID)",readonly=True,index=True)
    cc_dimension_name = fields.Char(string="Dimension (Name)",readonly=True,index=True)
    cc_dimension_detail = fields.Char(string="Dimension (Display)", readonly=True,index=True)
    cc_dimension_sequence = fields.Integer(string="Dimension (Sequence)", readonly=True, index=True)
    cc_dimension_account_id = fields.Many2one('cost.center.dimension.account.line',string="Dimension Line(Account)",readonly=True,index=True)
    cc_dimension_analytic_id = fields.Many2one('cost.center.dimension.analytic.line',string="Dimension Line(Analytic)",readonly=True,index=True)
    cc_dimension_journal_id = fields.Many2one('cost.center.dimension.journal.line',string="Dimension Line(Journal)",readonly=True,index=True)
    


    budget_amount = fields.Float(string="Budget", readonly=True)
    balance = fields.Float(string="Actual", readonly=True)
    last_balance = fields.Float(string="LY", readonly=True)
    variance = fields.Float(string="Actual Vs Budget", readonly=True)
    last_variance = fields.Float(string="Actual Vs LY", readonly=True)

    margin_variance = fields.Float(string="Actual Vs Budget (%)", compute='_compute_margin_variance', group_operator='avg', readonly=True, store=True)
    margin_last_variance = fields.Float(string="Actual Vs LY (%)", compute='_compute_margin_last_variance', group_operator='avg', readonly=True, store=True)
    



    @api.depends('balance')
    def _compute_margin_variance(self):
        for rec in self:
            rec.margin_variance = 0.0

    @api.depends('balance')
    def _compute_margin_last_variance(self):
        for rec in self:
            rec.margin_last_variance = 0.0


    def get_query(self, args, apply_ir_rules=False):
        query = self._where_calc(args)
        if apply_ir_rules:
            self._apply_ir_rules(query, 'read')
        from_clause, where_clause, where_clause_params = query.get_sql()
        where_str = where_clause and (" WHERE %s" % where_clause) or ''
        query_str = 'SELECT (sum(coalesce(balance,0))/(case when sum(last_balance) <> 0 then sum(last_balance) else null end) - 1) margin_last_variance, (sum(coalesce(balance,0))/(case when sum(budget_amount) <> 0 then sum(budget_amount) else null end) - 1) margin_variance FROM ' + from_clause + where_str
        where_clause_params = map(lambda x: "'" + str(x) + "'" , where_clause_params)
        return query_str % tuple(where_clause_params)


    @api.model 
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        res = super(CostCenterReport, self).read_group(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
        open('/opt/odoo16/logs/log_profitability_domain.log','a+').write('\n' + str(fields))
                    
        if 'margin_last_variance' and 'margin_variance' in fields:
            for line in res:
                if '__domain' in line:
                    # open('/opt/odoo16/logs/log_profitability_domain.log','a+').write('\n' + str(line['__domain']))
                    query = self.get_query(line['__domain'])
                    
                    #open('/opt/odoo16/logs/log_profitability_domain.log','a+').write('\n' + str(query))                    
                    self.env.cr.execute(query)
                    result = self.env.cr.dictfetchone()
                    if result:
                        line['margin_last_variance'] = result['margin_last_variance'] 
                        line['margin_variance'] = result['margin_variance']

                    # lines = self.search(line['__domain'])
                    # margin_total = 0.0
                    # revenue_total = 0.0
                    # for record in lines:
                    #     revenue_total += record.price_total
                    #     margin_total += record.margin_total
                    # if revenue_total > 0:
                    #     line['margin_percent'] = (margin_total / revenue_total * 100.0)
                    # else:
                    #     line['margin_percent'] = 0.0
        return res


# 2021.08.23
# untuk kebutuhan kelengkapan data cost center actual 2021
# maka perlu dibuat tampungan actual amount dari cost center report yg ditampung dalam satu table sendiri
# namun akan tetap di join waktu user melakukan print cost_center_report wizard
class CostCenterImport(models.Model):
    _name = 'cost.center.import'
    _inherit = ['mail.thread']

    @api.model
    def _get_company(self):
        return self.env.company.id

    sync_id = sync.id
    sync_type = sync.type
    sync_date = sync.date
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date

    company_id = fields.Many2one('res.company', string="Company", default=_get_company)
    date = fields.Date(string="Date", index=True)
    cost_master_id = fields.Many2one('cost.center.master', string="Cost Center", index=True)
    
    analytic_account_id = fields.Many2one('account.analytic.account',string="Analytic Account",index=True, tracking=True)
    parent_analytic_id = fields.Many2one('account.analytic.account', related='analytic_account_id.parent_id', readonly=True, store=True, string="Analytic (Parent)")
    account_id = fields.Many2one('account.account',string="Account (COA)",index=True)    
    balance = fields.Float(string="Actual", tracking=True)
    journal_id = fields.Many2one('account.journal',string="Account Journal",index=True)




class CostCenterReconcile(models.Model):
    _name = 'cost.center.reconcile'

    sync_type = sync.type
    company_id = fields.Many2one('res.company', string="Company", index=True)
    tglproses = fields.Date(string="TglProses", store=True, index=True)
    trans_type = fields.Char(string="Trans Type", index=True, readonly=True)
    direction = fields.Integer(string="Direction", readonly=True, index=True)
    amount = fields.Float(string="Amount", readonly=True)
    account_label = fields.Char(string="Account Label", index=True, readonly=True)
    account_credit_id = fields.Many2one('account.account', string="Account Credit", index=True, readonly=True)
    account_debit_id = fields.Many2one('account.account', string="Account Debit", index=True, readonly=True)
    doctor_id = fields.Many2one('account.analytic.account', string="Analytic Doctor", index=True, readonly=True)
    patient_group = fields.Char(string="Patient Group", index=True, readonly=True)
    service_group = fields.Char(string="Service Group", index=True, readonly=True)
    service_name = fields.Char(string="Service/Product Category", index=True, readonly=True)
    department_name = fields.Char(string="Faciliy/Department", index=True, readonly=True)
    analytic_id = fields.Many2one('account.analytic.account', string="Cost Center Analytic", index=True, readonly=True)
    user_id = fields.Many2one('res.users',string="User Ref.",index=True,readonly=False)
    cost_master_id = fields.Many2one('cost.center.master',string="Master Cost Center", index=True)



class CostCenterDimension(models.Model):
    _name = 'cost.center.dimension'



    @api.model
    def _get_company(self):
        return self.env.company.id
    
    sequence = fields.Integer('Sequence', index=True)
    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=True, index=True, default=_get_company)
    dimension_type = fields.Selection([('journal', 'Journal'),('account', 'Account'),('analytic', 'Analytic')],string="Type")

    parent_id = fields.Many2one('cost.center.dimension', string='Parent', store=True, index=True)
    name = fields.Char(string="Name", required=True)
    line_ids = fields.One2many('cost.center.dimension.line','dimension_id', string="Dimension Line")
    line_account_ids = fields.One2many('cost.center.dimension.account.line','dimension_id', string="Dimension Account")
    line_analytic_ids = fields.One2many('cost.center.dimension.analytic.line','dimension_id', string="Dimension Analytic")
    line_journal_ids = fields.One2many('cost.center.dimension.journal.line','dimension_id', string="Dimension Journal")
    item_line_account_ids = fields.Many2many('account.account', relation='account_account_cost_center_dimension', string="Dimension Account", required=False, store=True)
    item_line_analytic_ids = fields.Many2many('account.analytic.account', relation='account_analytic_cost_center_dimension', string="Dimension Analytic", required=False, store=True)
    item_line_journal_ids = fields.Many2many('account.journal', relation='account_journal_cost_center_dimension', string="Dimension Journal", required=False, store=True)
    sign_on_report = fields.Selection([('1', 'Reverse'), ('-1', 'Preserve')],string="Sign on Report")




class CostCenterDimensionLine(models.Model):
    _name = 'cost.center.dimension.line'

    @api.model
    def _get_company(self):
        return self.env.company.id

    dimension_id = fields.Many2one('cost.center.dimension', string='Cost Center Dimension', store=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=True, index=True, default=_get_company)
    account_id = fields.Many2one('account.account', string='Account', store=True, index=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', store=True, index=True)
    journal_id = fields.Many2one('account.journal', string='Journal', store=True, index=True)
    dimension_type = fields.Selection([('journal', 'Journal'),('account', 'Account'),('analytic', 'Analytic')],string="Type")
    sign_on_report = fields.Selection([('1', 'Reverse'), ('-1', 'Preserve')],string="Sign on Report")


class CostCenterDimensionAccountLine(models.Model):
    _name = 'cost.center.dimension.account.line'

    @api.model
    def _get_company(self):
        return self.env.company.id

    dimension_id = fields.Many2one('cost.center.dimension', string='Cost Center Dimension', store=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=True, index=True, default=_get_company)
    account_id = fields.Many2one('account.account', string='Account', store=True, index=True)



class CostCenterDimensionAnalyticLine(models.Model):
    _name = 'cost.center.dimension.analytic.line'

    @api.model
    def _get_company(self):
        return self.env.company.id

    dimension_id = fields.Many2one('cost.center.dimension', string='Cost Center Dimension', store=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=True, index=True, default=_get_company)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', store=True, index=True)
    

class CostCenterDimensionJournalLine(models.Model):
    _name = 'cost.center.dimension.journal.line'

    @api.model
    def _get_company(self):
        return self.env.company.id

    dimension_id = fields.Many2one('cost.center.dimension', string='Cost Center Dimension', store=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=True, index=True, default=_get_company)
    journal_id = fields.Many2one('account.journal', string='Journal', store=True, index=True)



class CostCenterSumAccount(models.Model):
    _name = 'cost.center.sum.account'




    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=True, index=True)
    dimension_type = fields.Selection([('journal', 'Journal'),('account', 'Account'),('analytic', 'Analytic')],string="Type")
    user_id = fields.Many2one('res.users',string="User Ref.",index=True,readonly=False)
    account_id = fields.Many2one('account.account', string='Account', store=True, index=True)
    journal_id = fields.Many2one('account.journal', string='Journal', store=True, index=True)
    move_id = fields.Many2one('account.move', string='Move', store=True, index=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Move', store=True, index=True)
    name = fields.Char(string="Name", store=True)
    date = fields.Date('Date', store=True)
    due_date = fields.Date('Due Date', store=True)
    balance = fields.Float(string="Balance", store=True)
    debit = fields.Float(string="Debit", store=True)
    credit = fields.Float(string="Credit", store=True)
