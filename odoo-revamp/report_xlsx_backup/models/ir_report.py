# Copyright 2015 ACSONE SA/NV (<http://acsone.eu>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ReportAction(models.Model):
    _inherit = "ir.actions.report"

    report_type = fields.Selection(
        selection_add=[("xlsx", "XLSX")], ondelete={"xlsx": "set default"}
    )

    open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("masuk ReportAction"))
    @api.model
    def _render_xlsx(self, docids, data):
        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("masuk _render_xlsx"))
        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(self))
        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(self.report_name))
        report_model_name = "report.%s" % self.report_name
        report_model = self.env.get(report_model_name)
        if report_model is None:
            raise UserError(_("%s model was not found") % report_model_name)
        # return (
        #     report_model.with_context(active_model=self.model)
        #     .sudo(False)
        #     .create_xlsx_report(docids, data)  # noqa
        # )
        save_excel = self.env['report.report_xlsx.abstract'].create_xlsx_report(docids, data)
        return save_excel

    @api.model
    def _get_report_from_name(self, report_name):
        res = super(ReportAction, self)._get_report_from_name(report_name)
        if res:
            return res
        report_obj = self.env["ir.actions.report"]
        qwebtypes = ["xlsx"]
        conditions = [
            ("report_type", "in", qwebtypes),
            ("report_name", "=", report_name),
        ]
        context = self.env["res.users"].context_get()
        return report_obj.with_context(context).search(conditions, limit=1)
