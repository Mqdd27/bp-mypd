import odoo
import re
import requests
import json
try:
    import ujson as JSON
except:
    import json as JSON
from threading import Thread
from odoo import models, fields, api, tools, exceptions, _
from io import StringIO
import sys
from . import sync

from collections import defaultdict, OrderedDict
from odoo.exceptions import UserError, ValidationError, Warning

MENU_ITEM_SEPARATOR = "/"


TYPE2FIELD = {
    'char': 'value_text',
    'float': 'value_float',
    'boolean': 'value_integer',
    'integer': 'value_integer',
    'text': 'value_text',
    'binary': 'value_binary',
    'many2one': 'value_reference',
    'date': 'value_datetime',
    'datetime': 'value_datetime',
    'selection': 'value_text',
    'monetary': 'value_float'
}

TYPE2CLEAN = {
    'boolean': bool,
    'integer': lambda val: val or False,
    'float': lambda val: val or False,
    'char': lambda val: val or False,
    'text': lambda val: val or False,
    'selection': lambda val: val or False,
    'binary': lambda val: val or False,
    'date': lambda val: val.date() if val else False,
    'datetime': lambda val: val or False,
    'monetary': lambda val: val or False,
}



class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    account_default_credit_limit = fields.Float(
        string="Default Credit Limit", readonly=False,
        help='This is the default credit limit that will be used on partners that do not have a specific limit on them.',
        compute="_compute_account_default_credit_limit", inverse="_inverse_account_default_credit_limit")



class Property(models.Model):
    _inherit = 'ir.property'
    _description = 'Company Property'

    type = fields.Selection([('char', 'Char'),
                             ('float', 'Float'),
                             ('boolean', 'Boolean'),
                             ('integer', 'Integer'),
                             ('text', 'Text'),
                             ('binary', 'Binary'),
                             ('many2one', 'Many2One'),
                             ('date', 'Date'),
                             ('datetime', 'DateTime'),
                             ('selection', 'Selection'),
                             ('monetary', 'Monetary'),
                             ],
                            required=True,
                            default='many2one',
                            index=True)


    def _update_values(self, values):
        if 'value' not in values:
            return values
        value = values.pop('value')

        prop = None
        type_ = values.get('type')
        if not type_:
            if self:
                prop = self[0]
                type_ = prop.type
            else:
                type_ = self._fields['type'].default(self)

        field = TYPE2FIELD.get(type_)
        # raise UserError(type_)
        if not field:
            raise UserError(_('Invalid type'))

        if field == 'value_reference':
            if not value:
                value = False
            elif isinstance(value, models.BaseModel):
                value = '%s,%d' % (value._name, value.id)
            elif isinstance(value, int):
                field_id = values.get('fields_id')
                if not field_id:
                    if not prop:
                        raise ValueError()
                    field_id = prop.fields_id
                else:
                    field_id = self.env['ir.model.fields'].browse(field_id)

                value = '%s,%d' % (field_id.sudo().relation, value)

        values[field] = value
        return values




class StockRule(models.Model):
    _inherit = 'stock.rule'

    name = fields.Char(string="Rule Name", translate=True)

class StockRoute(models.Model):
    _inherit = 'stock.route'

    name = fields.Char(string="Route Name", translate=True)

class PurchaseRequisitionType(models.Model):
    _inherit = 'purchase.requisition.type'

    name = fields.Char(string="PR Type", translate=True)

class ProductAttribute(models.Model):
    _inherit = 'product.attribute'

    name = fields.Char(string="Name", translate=True)    

class ConsolProductAttributeValue(models.Model):
    _inherit = 'product.attribute.value'    

    name = fields.Char(string="Name", translate=True)

class ConsolProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    name = fields.Char(string="Name", translate=True)

class ProductTag(models.Model):
    _inherit = 'product.tag'

    name = fields.Char(string="Name", translate=True)

class ResPartnerTitle(models.Model):
    _inherit = 'res.partner.title'

    name = fields.Char(string="Partner Title", translate=True)

class ConsolMailMessageSubtype(models.Model):
    _inherit = 'mail.message.subtype'

    name = fields.Char(string="Name", translate=True)
    description = fields.Char(string="Description", translate=True)

class ResCountry(models.Model):
    _inherit = 'res.country'

    name = fields.Char(string="Country Name", translate=True)


class ResCountryState(models.Model):
    _inherit = 'res.country.state'

    name = fields.Char(string="Country State", translate=True)


class AccountIncoterms(models.Model):
    _inherit = 'account.incoterms'

    name = fields.Char(string='Incoterms', translate=True)


class AccountPaymentMethod(models.Model):
    _inherit = 'account.payment.method'

    name = fields.Char(string='Payment Method', translate=True)
    

class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    name = fields.Char(string='Payment Term', translate=True)


class AccountReport(models.Model):
    _inherit = 'account.report'

    name = fields.Char(string='Account Report', translate=True)

class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    name = fields.Char(string="Analytic Name", translate=True)

class AccountTaxGroup(models.Model):
    _inherit = 'account.tax.group'

    name = fields.Char(string="Tax Group Name", translate=True)

class AccountAnalyticDistributionModel(models.Model):
    _inherit = 'account.analytic.distribution.model'

    analytic_distribution = fields.Char(string="Analytic Distribution", translate=True)

class AccountAssetAsset(models.Model):
    _inherit = 'account.asset.asset'

    analytic_distribution = fields.Char(string="Analytic Distribution", translate=True)

class AccountAssetCategory(models.Model):
    _inherit = 'account.asset.category'

    analytic_distribution = fields.Char(string="Analytic Distribution", translate=True)

class AccountCashRounding(models.Model):
    _inherit = 'account.cash.rounding'

    name = fields.Char(string="Name", translate=True)

class AccountFiscalPosition(models.Model):
    _inherit = 'account.fiscal.position'

    note = fields.Char(string="Note", translate=True)

class AccountJournalGroup(models.Model):
    _inherit = 'account.journal.group'

    name = fields.Char(string="Name", translate=True)

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    analytic_distribution = fields.Char(string="Analytic Distribution", translate=True)

class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    note = fields.Char(string="Note", translate=True)

class AccountReconcileModelLine(models.Model):
    _inherit = 'account.reconcile.model.line'

    analytic_distribution = fields.Char(string="Analytic Distribution", translate=True)

class AccountReportColumn(models.Model):
    _inherit = 'account.report.column'

    name = fields.Char(string="Name", translate=True)

class AccountReportLine(models.Model):
    _inherit = 'account.report.line'

    name = fields.Char(string="Name", translate=True)

class CrmTag(models.Model):
    _inherit = 'crm.tag'

    name = fields.Char(string="Name", translate=True)

class CrmTeam(models.Model):
    _inherit = 'crm.team'

    name = fields.Char(string="Name", translate=True)

class DigestDigest(models.Model):
    _inherit = 'digest.digest'

    name = fields.Char(string="Name", translate=True)

class DigestTip(models.Model):
    _inherit = 'digest.tip'

    name = fields.Char(string="Name", translate=True)
    tip_description = fields.Text(string="Tip Description", translate=True)

class HrContractType(models.Model):
    _inherit = 'hr.contract.type'

    name = fields.Char(string="Name", translate=True)

class HrDepartureReason(models.Model):
    _inherit = 'hr.departure.reason'

    name = fields.Char(string="Name", translate=True)

class HrJob(models.Model):
    _inherit = 'hr.job'

    name = fields.Char(string="Name", translate=True)

class IrActions(models.Model):
    _inherit = 'ir.actions.actions'

    help = fields.Text(string="Help", translate=True)
    name = fields.Char(string="Name", translate=True)

# class IrActClient(models.Model):
#     _inherit = 'ir.actions.client'

#     help = fields.Text(string="Help", translate=True)
#     name = fields.Char(string="Name", translate=True)

# class IrActReportXml(models.Model):
#     _inherit = 'ir.actions.report'

#     print_report_name = fields.Char(string="Print Report Name", translate=True)
#     help = fields.Text(string="Help", translate=True)
#     name = fields.Char(string="Name", translate=True)

# class IrActServer(models.Model):
#     _inherit = 'ir.actions.server'

#     help = fields.Text(string="Help", translate=True)
#     name = fields.Char(string="Name", translate=True)

# class IrActUrl(models.Model):
#     _inherit = 'ir.actions.act_url'

#     name = fields.Char(string="Name", translate=True)
#     help = fields.Text(string="Help", translate=True)

# class IrActWindow(models.Model):
#     _inherit = 'ir.actions.act_window'

#     name = fields.Char(string="Name", translate=True)
#     help = fields.Text(string="Help", translate=True)

# class IrActions(models.Model):
#     _inherit = 'ir.actions.actions'

#     name = fields.Char(string="Name", translate=True)
#     help = fields.Text(string="Help", translate=True)

class IrCron(models.Model):
    _inherit = 'ir.cron'

    cron_name = fields.Char(string="Cron Name", translate=True)

    # @classmethod
    # def _get_all_ready_jobs(cls, cr):
    #     """ Return a list of all jobs that are ready to be executed """
    #     cr.execute("""
    #         SELECT *, cron_name as cron_name
    #         FROM ir_cron
    #         WHERE active = true
    #           AND numbercall != 0
    #           AND (nextcall <= (now() at time zone 'UTC')
    #             OR id in (
    #                 SELECT cron_id
    #                 FROM ir_cron_trigger
    #                 WHERE call_at <= (now() at time zone 'UTC')
    #             )
    #           )
    #         ORDER BY priority
    #     """)
    #     return cr.dictfetchall()

    # @classmethod
    # def _acquire_one_job(cls, cr, job_ids):
    #     """
    #     Acquire for update one job that is ready from the job_ids tuple.

    #     The jobs that have already been processed in this worker should
    #     be excluded from the tuple.

    #     This function raises a ``psycopg2.errors.SerializationFailure``
    #     when the ``nextcall`` of one of the job_ids is modified in
    #     another transaction. You should rollback the transaction and try
    #     again later.
    #     """

    #     # We have to make sure ALL jobs are executed ONLY ONCE no matter
    #     # how many cron workers may process them. The exlusion mechanism
    #     # is twofold: (i) prevent parallel processing of the same job,
    #     # and (ii) prevent re-processing jobs that have been processed
    #     # already.
    #     #
    #     # (i) is implemented via `LIMIT 1 FOR UPDATE SKIP LOCKED`, each
    #     # worker just acquire one available job at a time and lock it so
    #     # the other workers don't select it too.
    #     # (ii) is implemented via the `WHERE` statement, when a job has
    #     # been processed, its nextcall is updated to a date in the
    #     # future and the optional triggers are removed.
    #     #
    #     # Note about (ii): it is possible that a job becomes available
    #     # again quickly (e.g. high frequency or self-triggering cron).
    #     # This function doesn't prevent from acquiring that job multiple
    #     # times at different moments. This can block a worker on
    #     # executing a same job in loop. To prevent this problem, the
    #     # callee is responsible of providing a `job_ids` tuple without
    #     # the jobs it has executed already.
    #     #
    #     # An `UPDATE` lock type is the strongest row lock, it conflicts
    #     # with ALL other lock types. Among them the `KEY SHARE` row lock
    #     # which is implicitely aquired by foreign keys to prevent the
    #     # referenced record from being removed while in use. Because we
    #     # never delete acquired cron jobs, foreign keys are safe to
    #     # concurrently reference cron jobs. Hence, the `NO KEY UPDATE`
    #     # row lock is used, it is a weaker lock that does conflict with
    #     # everything BUT `KEY SHARE`.
    #     #
    #     # Learn more: https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS

    #     query = """
    #         SELECT *, cron_name as cron_name
    #         FROM ir_cron
    #         WHERE active = true
    #           AND numbercall != 0
    #           AND (nextcall <= (now() at time zone 'UTC')
    #             OR EXISTS (
    #                 SELECT cron_id
    #                 FROM ir_cron_trigger
    #                 WHERE call_at <= (now() at time zone 'UTC')
    #                   AND cron_id = ir_cron.id
    #             )
    #           )
    #           AND id in %s
    #         ORDER BY priority
    #         LIMIT 1 FOR NO KEY UPDATE SKIP LOCKED
    #     """
    #     try:
    #         cr.execute(query, [job_ids], log_exceptions=False)
    #     except psycopg2.extensions.TransactionRollbackError:
    #         # A serialization error can occur when another cron worker
    #         # commits the new `nextcall` value of a cron it just ran and
    #         # that commit occured just before this query. The error is
    #         # genuine and the job should be skipped in this cron worker.
    #         raise
    #     except Exception as exc:
    #         _logger.error("bad query: %s\nERROR: %s", query, exc)
    #         raise
    #     return cr.dictfetchone()
    

# class IrModel(models.Model):
#     _inherit = 'ir.model'

#     name = fields.Char(string="Name", translate=True)


class IrModelConstraint(models.Model):
    _inherit = 'ir.model.constraint'

    message = fields.Text(string="Message", translate=True)

class IrModelFields(models.Model):
    _inherit = 'ir.model.fields'

    field_description = fields.Char(string="Field Description", translate=True)
    help = fields.Text(string="Help", translate=True)

class IrModelSelection(models.Model):
    _inherit = 'ir.model.fields.selection'

    name = fields.Char(string="Name", translate=True)

    # def _get_selection_data(self, field_id):
    #     # return selection as expected on registry (no translations)
    #     self._cr.execute("""
    #         SELECT value, name
    #         FROM ir_model_fields_selection
    #         WHERE field_id=%s
    #         ORDER BY sequence, id
    #     """, (field_id,))
    #     return self._cr.fetchall()
    

    # def _reflect_selections(self, model_names):
    #     """ Reflect the selections of the fields of the given models. """
    #     fields = [
    #         field
    #         for model_name in model_names
    #         for field_name, field in self.env[model_name]._fields.items()
    #         if field.type in ('selection', 'reference')
    #         if isinstance(field.selection, list)
    #     ]
    #     if not fields:
    #         return

    #     # determine expected and existing rows
    #     IMF = self.env['ir.model.fields']
    #     expected = {
    #         (field_id, value): (label, index)
    #         for field in fields
    #         for field_id in [IMF._get_ids(field.model_name)[field.name]]
    #         for index, (value, label) in enumerate(field.selection)
    #     }

    #     cr = self.env.cr
    #     query = """
    #         SELECT s.field_id, s.value, s.name, s.sequence
    #         FROM ir_model_fields_selection s, ir_model_fields f
    #         WHERE s.field_id = f.id AND f.model IN %s
    #     """
    #     cr.execute(query, [tuple(model_names)])
    #     existing = {row[:2]: row[2:] for row in cr.fetchall()}

    #     # create or update rows
    #     cols = ['field_id', 'value', 'name', 'sequence']
    #     rows = [key + val for key, val in expected.items() if existing.get(key) != val]
    #     if rows:
    #         ids = upsert_en(self, cols, rows, ['field_id', 'value'])
    #         self.pool.post_init(mark_modified, self.browse(ids), cols[2:])

    #     # update their XML ids
    #     module = self._context.get('module')
    #     if not module:
    #         return

    #     query = """
    #         SELECT f.model, f.name, s.value, s.id
    #         FROM ir_model_fields_selection s, ir_model_fields f
    #         WHERE s.field_id = f.id AND f.model IN %s
    #     """
    #     cr.execute(query, [tuple(model_names)])
    #     selection_ids = {row[:3]: row[3] for row in cr.fetchall()}

    #     data_list = []
    #     for field in fields:
    #         model = self.env[field.model_name]
    #         for value, modules in field._selection_modules(model).items():
    #             for m in modules:
    #                 xml_id = selection_xmlid(m, field.model_name, field.name, value)
    #                 record = self.browse(selection_ids[field.model_name, field.name, value])
    #                 data_list.append({'xml_id': xml_id, 'record': record})
    #     self.env['ir.model.data']._update_xmlids(data_list)
    

    # def _existing_selection_data(self, model_name, field_name):
    #     """ Return the selection data of the given model, by field and value, as
    #         a dict {field_name: {value: row_values}}.
    #     """
    #     query = """
    #         SELECT s.*, s.name AS name
    #         FROM ir_model_fields_selection s
    #         JOIN ir_model_fields f ON s.field_id=f.id
    #         WHERE f.model=%s and f.name=%s
    #     """
    #     self._cr.execute(query, [model_name, field_name])
    #     return {row['value']: row for row in self._cr.dictfetchall()}



# class IrModuleCategory(models.Model):
#     _inherit = 'ir.module.category'

#     description = fields.Text(string="Description", translate=True)
#     name = fields.Char(string="Name", translate=True)

# class IrModuleModule(models.Model):
#     _inherit = 'ir.module.module'

#     summary = fields.Text(string="Summary", translate=True)
#     description = fields.Text(string="Description", translate=True)
#     shortdesc = fields.Text(string="Short Description", translate=True)

# class IrUiMenu(models.Model):
#     _inherit = 'ir.ui.menu'

#     name = fields.Char(string="Name", translate=True)

# class IrUiView(models.Model):
#     _inherit = 'ir.ui.view'

#     arch_db = fields.Text(string="Architecture", translate=True)

# class MailActivityType(models.Model):
#     _inherit = 'mail.activity.type'

#     name = fields.Char(string="Name", translate=True)
#     summary = fields.Text(string="Summary", translate=True)
#     default_note = fields.Text(string="Default Note", translate=True)

# class MailAlias(models.Model):
#     _inherit = 'mail.alias'

#     alias_bounced_content = fields.Text(string="Alias Bounced Content", translate=True)

# class MailTemplate(models.Model):
#     _inherit = 'mail.template'

#     description = fields.Text(string="Description", translate=True)
#     name = fields.Char(string="Name", translate=True)
#     report_name = fields.Char(string="Report Name", translate=True)
#     body_html = fields.Html(string="Body HTML", translate=True)
#     subject = fields.Char(string="Subject", translate=True)

# class PaymentProvider(models.Model):
#     _inherit = 'payment.provider'

#     auth_msg = fields.Text(string="Authorization Message", translate=True)
#     cancel_msg = fields.Text(string="Cancel Message", translate=True)
#     done_msg = fields.Text(string="Done Message", translate=True)
#     name = fields.Char(string="Name", translate=True)
#     pre_msg = fields.Text(string="Pre-message", translate=True)
#     display_as = fields.Char(string="Display As", translate=True)
#     pending_msg = fields.Text(string="Pending Message", translate=True)

# class PurchaseOrderLine(models.Model):
#     _inherit = 'purchase.order.line'

#     analytic_distribution = fields.Char(string="Analytic Distribution", translate=True)

# class PurchaseRequisitionLine(models.Model):
#     _inherit = 'purchase.requisition.line'

#     analytic_distribution = fields.Char(string="Analytic Distribution", translate=True)

# class ResCompany(models.Model):
#     _inherit = 'res.company'

#     invoice_terms = fields.Text(string="Invoice Terms", translate=True)
#     report_footer = fields.Text(string="Report Footer", translate=True)
#     invoice_terms_html = fields.Html(string="Invoice Terms HTML", translate=True)

# # class ResConfigSettings(models.TransientModel):
# #     _inherit = 'res.config.settings'

# #     report_footer = fields.Text(string="Report Footer", translate=True)


# class BaseDocumentLayout(models.TransientModel):
#     _inherit = 'base.document.layout'

#     report_footer = fields.Text(string="Report Footer", translate=True)

# class ResConfigSettings(models.TransientModel):
#     _inherit = 'res.config.settings'

#     invoice_terms = fields.Text(string="Invoice Terms", translate=True)
#     invoice_terms_html = fields.Html(string="Invoice Terms HTML", translate=True)

# class ResCountry(models.Model):
#     _inherit = 'res.country'

#     vat_label = fields.Char(string="VAT Label", translate=True)

# class ResCountryGroup(models.Model):
#     _inherit = 'res.country.group'

#     name = fields.Char(string="Name", translate=True)

# class ResPartnerCategory(models.Model):
#     _inherit = 'res.partner.category'

#     name = fields.Char(string="Name", translate=True)

# class ResPartnerIndustry(models.Model):
#     _inherit = 'res.partner.industry'

#     full_name = fields.Char(string="Full Name", translate=True)
#     name = fields.Char(string="Name", translate=True)

# class ResPartnerTitle(models.Model):
#     _inherit = 'res.partner.title'

#     shortcut = fields.Char(string="Shortcut", translate=True)
#     shortcut2 = fields.Char(string="Shortcut 2", translate=True)

# class SaleOrderLine(models.Model):
#     _inherit = 'sale.order.line'

#     analytic_distribution = fields.Char(string="Analytic Distribution", translate=True)

# class SaleOrderTemplate(models.Model):
#     _inherit = 'sale.order.template'

#     note = fields.Text(string="Note", translate=True)

# class SaleOrderTemplateLine(models.Model):
#     _inherit = 'sale.order.template.line'

#     name = fields.Char(string="Name", translate=True)

# class SaleOrderTemplateOption(models.Model):
#     _inherit = 'sale.order.template.option'

#     name = fields.Char(string="Name", translate=True)

# class SmsTemplate(models.Model):
#     _inherit = 'sms.template'

#     body = fields.Text(string="Body", translate=True)
#     name = fields.Char(string="Name", translate=True)

# class UtmCampaign(models.Model):
#     _inherit = 'utm.campaign'

#     title = fields.Char(string="Title", translate=True)

# class UtmStage(models.Model):
#     _inherit = 'utm.stage'

#     name = fields.Char(string="Name", translate=True)

# class UtmTag(models.Model):
#     _inherit = 'utm.tag'

#     name = fields.Char(string="Name", translate=True)

# class IrModuleCategory(models.Model):
#     _inherit = 'ir.module.category'
    
#     name = fields.Char(string="Name", translate=True)

# class IrModelAccess(models.Model):
#     _inherit = 'ir.model.access'

#     @api.model
#     def group_names_with_access(self, model_name, access_mode):
#         """ Return the names of visible groups which have been granted
#             ``access_mode`` on the model ``model_name``.
#            :rtype: list
#         """
#         assert access_mode in ('read', 'write', 'create', 'unlink'), 'Invalid access mode'
#         self._cr.execute(f"""
#             SELECT c.name, g.name
#               FROM ir_model_access a
#               JOIN ir_model m ON (a.model_id = m.id)
#               JOIN res_groups g ON (a.group_id = g.id)
#          LEFT JOIN ir_module_category c ON (c.id = g.category_id)
#              WHERE m.model = %s
#                AND a.active = TRUE
#                AND a.perm_{access_mode} = TRUE
#           ORDER BY c.name, g.name NULLS LAST
#         """, [model_name])
#         return [('%s/%s' % x) if x[0] else x[1] for x in self._cr.fetchall()]

#     # The context parameter is useful when the method translates error messages.
#     # But as the method raises an exception in that case,  the key 'lang' might
#     # not be really necessary as a cache key, unless the `ormcache_context`
#     # decorator catches the exception (it does not at the moment.)


# class AccountJournal(models.Model):
#     _inherit = 'account.journal'

#     # json_activity_data = fields.Text(compute='_get_json_activity_data')

#     def _get_json_activity_data(self):
#         for journal in self:
#             activities = []
#             # search activity on move on the journal
#             sql_query = '''
#                 SELECT act.id,
#                     act.res_id,
#                     act.res_model,
#                     act.summary,
#                     act_type.name as act_type_name,
#                     act_type.category as activity_category,
#                     act.date_deadline,
#                     m.date,
#                     m.ref,
#                     CASE WHEN act.date_deadline < CURRENT_DATE THEN 'late' ELSE 'future' END as status
#                 FROM account_move m
#                     LEFT JOIN mail_activity act ON act.res_id = m.id
#                     LEFT JOIN mail_activity_type act_type ON act.activity_type_id = act_type.id
#                 WHERE act.res_model = 'account.move'
#                     AND m.journal_id = %s
#             '''
#             self.env.cr.execute(sql_query, (journal.id,))
#             for activity in self.env.cr.dictfetchall():
#                 act = {
#                     'id': activity.get('id'),
#                     'res_id': activity.get('res_id'),
#                     'res_model': activity.get('res_model'),
#                     'status': activity.get('status'),
#                     'name': (activity.get('summary') or activity.get('act_type_name')),
#                     'activity_category': activity.get('activity_category'),
#                     'date': odoo_format_date(self.env, activity.get('date_deadline'))
#                 }
#                 if activity.get('activity_category') == 'tax_report' and activity.get('res_model') == 'account.move':
#                     act['name'] = activity.get('ref')

#                 activities.append(act)
#             journal.json_activity_data = json.dumps({'activities': activities})
            


# class BaseModel(models.BaseModel):
#     _inherit = 'base'

#     @api.depends(lambda self: (self._rec_name,) if self._rec_name else ())
#     def _compute_display_name(self):
#         """Compute the value of the `display_name` field.

#         In general `display_name` is equal to calling `name_get()[0][1]`.

#         In that case, it is recommended to use `display_name` to uniformize the
#         code and to potentially take advantage of prefetch when applicable.

#         However some models might override this method. For them, the behavior
#         might differ, and it is important to select which of `display_name` or
#         `name_get()[0][1]` to call depending on the desired result.
#         """
#         names = dict(self.name_get())
#         for record in self:
#             record.display_name = names.get(record.id)

#     @api.model
#     def _inherits_join_calc(self, alias, fname, query):
#         """
#         Adds missing table select and join clause(s) to ``query`` for reaching
#         the field coming from an '_inherits' parent table (no duplicates).

#         :param alias: name of the initial SQL alias
#         :param fname: name of inherited field to reach
#         :param query: query object on which the JOIN should be added
#         :return: qualified name of field, to be used in SELECT clause
#         """
#         # INVARIANT: alias is the SQL alias of model._table in query
#         model, field = self, self._fields[fname]
        
#         while field.inherited:
#             # retrieve the parent model where field is inherited from
#             parent_model = self.env[field.related_field.model_name]
#             parent_fname = field.related.split('.')[0]
#             # JOIN parent_model._table AS parent_alias ON alias.parent_fname = parent_alias.id
#             parent_alias = query.left_join(
#                 alias, parent_fname, parent_model._table, 'id', parent_fname,
#             )
#             model, alias, field = parent_model, parent_alias, field.related_field

#         if field.type == 'many2many':
#             # special case for many2many fields: prepare a query on the comodel
#             # in order to reuse the mechanism _apply_ir_rules, then inject the
#             # query as an extra condition of the left join
#             comodel = self.env[field.comodel_name]
#             subquery = Query(self.env.cr, comodel._table)
#             comodel._apply_ir_rules(subquery)
#             # add the extra join condition only if there is an actual subquery
#             extra, extra_params = None, ()
#             if subquery.where_clause:
#                 subquery_str, extra_params = subquery.select()
#                 extra = '"{rhs}"."%s" IN (%s)' % (field.column2, subquery_str)
#             # LEFT JOIN field_relation ON
#             #     alias.id = field_relation.field_column1
#             #     AND field_relation.field_column2 IN (subquery)
#             rel_alias = query.left_join(
#                 alias, 'id', field.relation, field.column1, field.name,
#                 extra=extra, extra_params=extra_params,
#             )
#             return '"%s"."%s"' % (rel_alias, field.column2)
#         elif field.translate:
#             lang = self.env.lang or 'en_US'
#             if lang == 'en_US':
#                 return f'"{alias}"."{fname}"->>\'en_US\''
#             return f'COALESCE("{alias}"."{fname}"->>\'{lang}\', "{alias}"."{fname}"->>\'en_US\')'
#         else:
#             return '"%s"."%s"' % (alias, fname)
        

# class IrUiMenu(models.Model):
#     _inherit = 'ir.ui.menu'
    
#     def _get_full_name(self, level=6):
#         """ Return the full name of ``self`` (up to a certain level). """
#         if level <= 0:
#             return '...'
#         if self.parent_id:
#             return self.parent_id._get_full_name(level - 1) + MENU_ITEM_SEPARATOR + (self.name or "")
#         else:
#             return self.name
        

# class account_journal(models.Model):
#     _inherit = "account.journal"

#     def _get_json_activity_data(self):
#         today = fields.Date.context_today(self)
#         activities = defaultdict(list)
#         # search activity on move on the journal
#         lang = self.env.user.lang or get_lang(self.env).code
#         sql_query = """
#             SELECT activity.id,
#                    activity.res_id,
#                    activity.res_model,
#                    activity.summary,
#                    CASE WHEN activity.date_deadline < %(today)s THEN 'late' ELSE 'future' END as status,
#                    COALESCE(act_type.name->> %(lang)s, act_type.name) as act_type_name,
#                    act_type.category as activity_category,
#                    activity.date_deadline,
#                    move.date,
#                    move.ref,
#                    move.journal_id
#               FROM account_move move
#               JOIN mail_activity activity ON activity.res_id = move.id AND activity.res_model = 'account.move'
#          LEFT JOIN mail_activity_type act_type ON activity.activity_type_id = act_type.id
#              WHERE move.journal_id = ANY(%(ids)s)
#         """
#         self.env.cr.execute(sql_query, {'ids': self.ids, 'today': today, 'lang': lang})
#         for activity in self.env.cr.dictfetchall():
#             act = {
#                 'id': activity['id'],
#                 'res_id': activity['res_id'],
#                 'res_model': activity['res_model'],
#                 'status': activity['status'],
#                 'name': activity['summary'] or activity['act_type_name'],
#                 'activity_category': activity['activity_category'],
#                 'date': odoo_format_date(self.env, activity['date_deadline'])
#             }
#             if activity['activity_category'] == 'tax_report' and activity['res_model'] == 'account.move':
#                 act['name'] = activity['ref']

#             activities[activity['journal_id']].append(act)
#         for journal in self:
#             journal.json_activity_data = json.dumps({'activities': activities[journal.id]})


# class IrFieldsConverter(models.AbstractModel):
#     _inherit = 'ir.fields.converter'

#     @api.model
#     def _get_selection_translations(self, field, src):
#         if not src:
#             return []
#         # Cache translations so they don't have to be reloaded from scratch on
#         # every row of the file
#         tnx_cache = self._cr.cache.setdefault(self._name, {})
#         if src in tnx_cache:
#             return tnx_cache[src]

#         values = OrderedSet()
#         self.env['ir.model.fields.selection'].flush_model()
#         query = """
#             SELECT s.name
#             FROM ir_model_fields_selection s
#             JOIN ir_model_fields f ON s.field_id = f.id
#             WHERE f.model = %s AND f.name = %s AND s.name = %s
#         """
#         self.env.cr.execute(query, [field.model_name, field.name, src])
#         for (name,) in self.env.cr.fetchall():
#             name.pop('en_US')
#             values.update(name.values())

#         result = tnx_cache[src] = list(values)
#         return result
    

# class IrFilters(models.Model):
#     _inherit = 'ir.filters'

#     @api.model
#     def _list_all_models(self):
#         lang = self.env.lang or 'en_US'
#         self._cr.execute(
#             "SELECT model, COALESCE(name, name) FROM ir_model ORDER BY 2",
#             [lang],
#         )
#         return self._cr.fetchall()






class OldPartner(models.Model):
    _inherit = 'res.partner'
    old_id = fields.Float(string="Old ID")

class OldCompany(models.Model):
    _inherit = 'res.company'

    old_id = fields.Float(string="Old ID")
    sync_tc_active = fields.Boolean(string="Enable TC Sync", default=False, tracking=True)
    sync_tc_type = fields.Selection(
        [('api', 'API'), ('txt', 'TXT')],
        string="TC Sync Type",
        default='api',
        tracking=True,
    )
    sync_tc_api_url = fields.Char(string="TC API URL", tracking=True)
    sync_tc_sharing_path = fields.Char(string="TC Sharing Path", tracking=True)

class OldGroups(models.Model):
    _inherit = 'res.groups'
    old_id = fields.Float(string="Old ID")

class OldModelAccess(models.Model):
    _inherit = 'ir.model.access'
    old_id = fields.Float(string="Old ID")

# class OldMenuGroup(models.Model):
#     _inherit = 'ir.ui.menu.group.rel'
#     old_id = fields.Float(string="Old ID")

class OldPosition(models.Model):
    _inherit = 'res.position'

    old_id = fields.Float(string="Old ID")
    position_code = fields.Char(
        string='Position Code',
        required=True,
        copy=False,
        default='/',
    )
    alias_name = fields.Char(string='Alias Name')

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()
        for vals in vals_list:
            if not vals.get('position_code') or vals.get('position_code') == '/':
                sequence = self.env['ir.sequence'].next_by_code('seq_erp_mdm_job_position')
                if not sequence:
                    raise UserError(_(
                        'Sequence seq_erp_mdm_job_position is not configured.'
                    ))
                vals['position_code'] = sequence
            # The existing res.position create override accepts one dictionary.
            records |= super(OldPosition, self).create(vals)
        return records


class OldDepartment(models.Model):
    _inherit = 'hr.department'
    old_id = fields.Float(string="Old ID")


class OldUsers(models.Model):
    _inherit = 'res.users'

    old_id = fields.Float(string="Old ID")
    user_code = fields.Char(
        string='User Code',
        required=True,
        copy=False,
        default='/',
    )
    alias_name = fields.Char(string='Alias Name')
    sipa_no = fields.Char(string='SIPA No')

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()
        for vals in vals_list:
            if not vals.get('user_code') or vals.get('user_code') == '/':
                sequence = self.env['ir.sequence'].next_by_code('seq_erp_mdm_user')
                if not sequence:
                    raise UserError(_('Sequence seq_erp_mdm_user is not configured.'))
                vals['user_code'] = sequence
            # The existing res.users create override accepts one dictionary.
            records |= super(OldUsers, self).create(vals)
        return records

# class OldGroupUsersRel(models.Model):
#     _inherit = 'res.groups.users.rel'
#     old_id = fields.Float(string="Old ID")

# class OldCompanyUsers(models.Model):
#     _inherit = 'res.company.users.rel'
#     old_id = fields.Float(string="Old ID")

class OldRules(models.Model):
    _inherit = 'ir.rule'
    old_id = fields.Float(string="Old ID")

class OldFilters(models.Model):
    _inherit = 'ir.filters'
    old_id = fields.Float(string="Old ID")

class OldWarehouse(models.Model):
    _inherit = 'stock.warehouse'
    old_id = fields.Float(string="Old ID")

class OldPickingType(models.Model):
    _inherit = 'stock.picking.type'
    old_id = fields.Float(string="Old ID")

class OldLocation(models.Model):
    _inherit = 'stock.location'
    old_id = fields.Float(string="Old ID")

class OldCashflowType(models.Model):
    _inherit = 'account.cashflow.type'
    old_id = fields.Float(string="Old ID")

# class OldConsoleCompanyMapping(models.Model):
#     _inherit = 'account.console.company.mapping'
#     old_id = fields.Float(string="Old ID")

# class OldConsoleCompanyMappingRel(models.Model):
#     _inherit = 'account.console.company.mapping.res.company.rel'
#     old_id = fields.Float(string="Old ID")

class OldBank(models.Model):
    _inherit = 'res.bank'
    old_id = fields.Float(string="Old ID")

class OldBankInformation(models.Model):
    _inherit = 'bank.information'
    old_id = fields.Float(string="Old ID")

class OldAccountAccount(models.Model):
    _inherit = 'account.account'
    old_id = fields.Float(string="Old ID")

class OldAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'
    old_id = fields.Float(string="Old ID")

class OldAccountJournal(models.Model):
    _inherit = 'account.journal'
    old_id = fields.Float(string="Old ID")

class OldAccountTax(models.Model):
    _inherit = 'account.tax'
    old_id = fields.Float(string="Old ID")

# class OldFinancialReport(models.Model):
#     _inherit = 'account.financial.report'
#     old_id = fields.Float(string="Old ID")

# class OldFinancialReportDetail(models.Model):
#     _inherit = 'account.account.financial.report'
#     old_id = fields.Float(string="Old ID")

class OldCostCenterMaster(models.Model):
    _inherit = 'cost.center.master'
    old_id = fields.Float(string="Old ID")

class OldCostCenterDimension(models.Model):
    _inherit = 'cost.center.dimension'
    old_id = fields.Float(string="Old ID")

class OldCostCenterSumAccount(models.Model):
    _inherit = 'cost.center.sum.account'
    old_id = fields.Float(string="Old ID")

class OldCrossoveredBudget(models.Model):
    _inherit = 'crossovered.budget'
    old_id = fields.Float(string="Old ID")

class OldBudgetPost(models.Model):
    _inherit = 'account.budget.post'
    old_id = fields.Float(string="Old ID")

class OldBudgetApproval(models.Model):
    _inherit = 'budget.approval'
    old_id = fields.Float(string="Old ID")

class OldBudgetApprovalRule(models.Model):
    _inherit = 'budget.approval.rule'
    old_id = fields.Float(string="Old ID")

class OldBudgetType(models.Model):
    _inherit = 'budget.type'
    old_id = fields.Float(string="Old ID")

# class OldBudgetApprovalRel(models.Model):
#     _inherit = 'budget.approval.budget.type.rel'
#     old_id = fields.Float(string="Old ID")

class OldAccountSalary(models.Model):
    _inherit = 'account.salary'
    old_id = fields.Float(string="Old ID")

class OldDepartmentCostReport(models.Model):
    _inherit = 'department.cost.report'
    old_id = fields.Float(string="Old ID")

class OldDepartmentReport(models.Model):
    _inherit = 'department.report'
    old_id = fields.Float(string="Old ID")

class OldProductCategory(models.Model):
    _inherit = 'product.category'
    old_id = fields.Float(string="Old ID")

class OldUom(models.Model):
    _inherit = 'uom.uom'
    old_id = fields.Float(string="Old ID")

class OldProductTemplate(models.Model):
    _inherit = 'product.template'
    old_id = fields.Float(string="Old ID")

class OldProductProduct(models.Model):
    _inherit = 'product.product'
    old_id = fields.Float(string="Old ID")

class OldPurchaseApprovalRule(models.Model):
    _inherit = 'purchase.approval.rule'
    old_id = fields.Float(string="Old ID")

class OldPurchaseApproval(models.Model):
    _inherit = 'purchase.approval'
    old_id = fields.Float(string="Old ID")

class OldPurchaseType(models.Model):
    _inherit = 'purchase.type'
    old_id = fields.Float(string="Old ID")

# class OldPurchaseApprovalPurchaseTypeRel(models.Model):
#     _inherit = 'purchase.approval.purchase.type.rel'
#     old_id = fields.Float(string="Old ID")

class OldPurchaseRequisition(models.Model):
    _inherit = 'purchase.requisition'
    old_id = fields.Float(string="Old ID")

class OldPurchaseRequisitionLine(models.Model):
    _inherit = 'purchase.requisition.line'
    old_id = fields.Float(string="Old ID")

class OldPurchaseOrder(models.Model):
    _inherit = 'purchase.order'
    old_id = fields.Float(string="Old ID")

class OldPurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'
    old_id = fields.Float(string="Old ID")

# class OldPurchaseOrderLineRel(models.Model):
#     _inherit = 'account.tax.purchase.order.line.rel'
#     old_id = fields.Float(string="Old ID")

class OldStockReceiving(models.Model):
    _inherit = 'stock.receiving'
    old_id = fields.Float(string="Old ID")

class OldStockReceivingLine(models.Model):
    _inherit = 'stock.receiving.line'
    old_id = fields.Float(string="Old ID")

class OldStockPicking(models.Model):
    _inherit = 'stock.picking'
    old_id = fields.Float(string="Old ID")

class OldStockMove(models.Model):
    _inherit = 'stock.move'
    old_id = fields.Float(string="Old ID")

class OldStockScrap(models.Model):
    _inherit = 'stock.scrap'
    old_id = fields.Float(string="Old ID")

class OldStockLedger(models.Model):
    _inherit = 'stock.ledger'
    old_id = fields.Float(string="Old ID")

class OldAccountInvoice(models.Model):
    _inherit = 'account.invoice'
    old_id = fields.Float(string="Old ID")

class OldAccountInvoiceTax(models.Model):
    _inherit = 'account.invoice.tax'
    old_id = fields.Float(string="Old ID")

class OldAccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'
    old_id = fields.Float(string="Old ID")

# class OldAccountInvoiceLineTax(models.Model):
#     _inherit = 'account.invoice.line.tax'
#     old_id = fields.Float(string="Old ID")

# class OldAccountInvoiceDownPaymentRel(models.Model):
#     _inherit = 'account.invoice.down.payment.rel'
#     old_id = fields.Float(string="Old ID")

class OldAccountPayment(models.Model):
    _inherit = 'account.payment'
    old_id = fields.Float(string="Old ID")

# class OldAccountInvoiceAccountPaymentRel(models.Model):
#     _inherit = 'account.invoice.account.payment.rel'
#     old_id = fields.Float(string="Old ID")

class OldAccountMove(models.Model):
    _inherit = 'account.move'
    old_id = fields.Float(string="Old ID")

class OldAccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    old_id = fields.Float(string="Old ID")


class OldServiceGroup(models.Model):
    _inherit = 'service.group'
    old_id = fields.Float(string="Old ID")

class OldHospitalTariff(models.Model):
    _inherit = 'hospital.tariff'
    old_id = fields.Float(string="Old ID")

class OldHospitalGrade(models.Model):
    _inherit = 'hospital.grade'
    old_id = fields.Float(string="Old ID")

class HospitalBedType(models.Model):
    _inherit = 'hospital.bed.type'
    old_id = fields.Float(string="Old ID")

class OldHospitalDiscountType(models.Model):
    _inherit = 'hospital.discount.type'
    old_id = fields.Float(string="Old ID")

class OldHospitalRoomName(models.Model):
    _inherit = 'hospital.room.name'
    old_id = fields.Float(string="Old ID")

class OldHospitalBedName(models.Model):
    _inherit = 'hospital.bed.name'
    old_id = fields.Float(string="Old ID")

class OldSaleOrder(models.Model):
    _inherit = 'sale.order'
    old_id = fields.Float(string="Old ID")

class OldSaleOrderBill(models.Model):
    _inherit = 'sale.order.bill'
    old_id = fields.Float(string="Old ID")

class OldSaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    old_id = fields.Float(string="Old ID")

class OldProfitabilityAnalysis(models.Model):
    _inherit = 'profitability.analysis'
    old_id = fields.Float(string="Old ID")

class OldAccountAssetType(models.Model):
    _inherit = 'account.asset.category'
    old_id = fields.Float(string="Old ID")

class OldAccountAssetSubCategory(models.Model):
    _inherit = 'account.asset.subcategory'
    old_id = fields.Float(string="Old ID")

class OldAccountAsset(models.Model):
    _inherit = 'account.asset.asset'
    old_id = fields.Float(string="Old ID")

class OldAccountAssetDepreciationLine(models.Model):
    _inherit = 'account.asset.depreciation.line'
    old_id = fields.Float(string="Old ID")

class OldAccountCoveringLetter(models.Model):
    _inherit = 'account.coveringletter'
    old_id = fields.Float(string="Old ID")

# class ResPartner(models.Model):
#     _inherit = 'account.coveringletter.bill.rel'
#     old_id = fields.Float(string="Old ID")

class OldCreditNote(models.Model):
    _inherit = 'account.creditnote'
    old_id = fields.Float(string="Old ID")

class OldCreditNoteLine(models.Model):
    _inherit = 'account.creditnote.line'
    old_id = fields.Float(string="Old ID")

class OldAccountAdvance(models.Model):
    _inherit = 'account.advance'
    old_id = fields.Float(string="Old ID")

class OldAccountAdvanceRealization(models.Model):
    _inherit = 'account.advance.realization'
    old_id = fields.Float(string="Old ID")

class OldBslMapping(models.Model):
    _inherit = 'bsl.mapping'
    old_id = fields.Float(string="Old ID")

# class OldBslMappingLocation(models.Model):
#     _inherit = 'bsl.mapping.location'
#     old_id = fields.Float(string="Old ID")

# class OldBslProduct(models.Model):
#     _inherit = 'bsl.mapping.product'
#     old_id = fields.Float(string="Old ID")

class OldBslSpecialise(models.Model):
    _inherit = 'bsl.mapping.specialise'
    old_id = fields.Float(string="Old ID")

class OldAnalyticRevenueMappingNew(models.Model):
    _inherit = 'account.analytic.revenue.mapping.new'
    old_id = fields.Float(string="Old ID")

class OldAnalyticRevenueMapping(models.Model):
    _inherit = 'account.analytic.revenue.mapping'
    old_id = fields.Float(string="Old ID")

class OldAnalyticCostMapping(models.Model):
    _inherit = 'account.analytic.cost.mapping'
    old_id = fields.Float(string="Old ID")

class OldAnalyticCostMappingNew(models.Model):
    _inherit = 'account.analytic.cost.mapping.new'
    old_id = fields.Float(string="Old ID")

class OldAnalyticScrapMapping(models.Model):
    _inherit = 'account.analytic.scrap.mapping'
    old_id = fields.Float(string="Old ID")

class OldAnalyticServiceCostMapping(models.Model):
    _inherit = 'account.analytic.service.cost.mapping'
    old_id = fields.Float(string="Old ID")

class OldAnalyticDoctorCostMapping(models.Model):
    _inherit = 'account.analytic.doctor.cost.mapping'
    old_id = fields.Float(string="Old ID")


class OldMailMessage(models.Model):
    _inherit = 'mail.message'
    old_id = fields.Float(string="Old ID")


class OldIrAttachment(models.Model):
    _inherit = 'ir.attachment'
    old_id = fields.Float(string="Old ID")
