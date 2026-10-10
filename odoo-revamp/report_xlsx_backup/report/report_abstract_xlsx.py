# Copyright 2015 ACSONE SA/NV (<http://acsone.eu>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import logging
import re
from io import BytesIO

from odoo import models

_logger = logging.getLogger(__name__)

try:
    import xlsxwriter

    class PatchedXlsxWorkbook(xlsxwriter.Workbook):
        def _check_sheetname(self, sheetname, is_chartsheet=False):
            """We want to avoid duplicated sheet names exceptions the same following
            the same philosophy that Odoo implements overriding the main library
            to avoid the 31 characters limit triming the strings before sending them
            to the library.

            In some cases, there's not much control over this as the reports send
            automated data and the potential exception is hidden underneath making it
            hard to debug the original issue. Even so, different names can become the
            same one as their strings are trimmed to those 31 character limit.

            This way, once we come across with a duplicated, we set that final 3
            characters with a sequence that we evaluate on the fly. So for instance:

            - 'Sheet name' will be 'Sheet name~01'
            - The next 'Sheet name' will try to rename to 'Sheet name~01' as well and
              then that will give us 'Sheet name~02'.
            - And the next 'Sheet name' will try to rename to 'Sheet name~01' and then
              to 'Sheet name~02' and finally it will be able to 'Sheet name~03'.
            - An so on as many times as duplicated sheet names come to the workbook up
              to 100 for each sheet name. We set such limit as we don't want to truncate
              the strings too much and keeping in mind that this issue don't usually
              ocurrs.
            """
            try:
                return super()._check_sheetname(sheetname, is_chartsheet=is_chartsheet)
            except xlsxwriter.exceptions.DuplicateWorksheetName:
                pattern = re.compile(r"~[0-9]{2}$")
                duplicated_secuence = (
                    re.search(pattern, sheetname) and int(sheetname[-2:]) or 0
                )
                # Only up to 100 duplicates
                deduplicated_secuence = "~{:02d}".format(duplicated_secuence + 1)
                if duplicated_secuence > 99:
                    raise xlsxwriter.exceptions.DuplicateWorksheetName
                if duplicated_secuence:
                    sheetname = re.sub(pattern, deduplicated_secuence, sheetname)
                elif len(sheetname) <= 28:
                    sheetname += deduplicated_secuence
                else:
                    sheetname = sheetname[:28] + deduplicated_secuence
            # Refeed the method until we get an unduplicated name
            return self._check_sheetname(sheetname, is_chartsheet=is_chartsheet)

    # "Short string"

    xlsxwriter.Workbook = PatchedXlsxWorkbook

except ImportError:
    _logger.debug("Can not import xlsxwriter`.")


class ReportXlsxAbstract(models.AbstractModel):
    _name = "report.report_xlsx.abstract"
    _description = "Abstract XLSX Report"

    def _get_objs_for_report(self, docids, data):
        """
        Returns objects for xlx report.  From WebUI these
        are either as docids taken from context.active_ids or
        in the case of wizard are in data.  Manual calls may rely
        on regular context, setting docids, or setting data.

        :param docids: list of integers, typically provided by
            qwebactionmanager for regular Models.
        :param data: dictionary of data, if present typically provided
            by qwebactionmanager for TransientModels.
        :param ids: list of integers, provided by overrides.
        :return: recordset of active model for ids.
        """
        if docids:
            ids = docids
        elif data and "context" in data:
            ids = data["context"].get("active_ids", [])
        else:
            ids = self.env.context.get("active_ids", [])
        return self.env[self.env.context.get("active_model")].browse(ids)

    def _report_xlsx_currency_format(self, currency):
        """Get the format to be used in cells (symbol included).
        Used in account_financial_report addon"""
        s_before = currency.symbol if currency.position == "before" else ""
        s_after = " %s" % currency.symbol if currency.position == "after" else ""
        return f"{f'{s_before}'}#,##0.{'0' * currency.decimal_places}{f'{s_after}'}"


    def create_xlsx_report(self, docids, data):
        # from odoo import models, _
        # from odoo.http import request, serialize_exception, content_disposition
        # import io
        # import xlsxwriter
        # open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("masuk create_xlsx_report"))

        # # objs = self._get_objs_for_report(docids, data)
        # output = io.BytesIO()
        # response = request.make_response(None, headers=[
        #     ('Content-Type', 'application/vnd.ms-excel'),
        #     ('Content-Disposition', content_disposition("Standard Report" + '.xlsx'))
        # ])
        
        # workbook = xlsxwriter.Workbook(output, self.get_workbook_options())
        # # self.generate_xlsx_report(workbook, data, objs)

        # wizard = docids
        # open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("masuk generate_xlsx_report"))
        # num_format = wizard.company_currency_id.excel_format
        # bold = workbook.add_format({'bold': True})
        # middle = workbook.add_format({'bold': True, 'top': 1})
        # left = workbook.add_format({'left': 1, 'top': 1, 'bold': True})
        # right = workbook.add_format({'right': 1, 'top': 1})
        # top = workbook.add_format({'top': 1})
        # currency_format = workbook.add_format({'num_format': num_format})
        # c_middle = workbook.add_format({'bold': True, 'top': 1, 'num_format': num_format})
        # report_format = workbook.add_format({'font_size': 24})
        # rounding = self.env.user.company_id.currency_id.decimal_places or 2
        # lang_code = self.env.user.lang or 'en_US'
        # date_format = self.env['res.lang']._lang_get(lang_code).date_format

        # report = wizard.report_id

        # def _get_data_float(data):
        #     if data is None or not data:
        #         return 0.0
        #     else:
        #         return wizard.company_currency_id.round(data) + 0.0

        # def get_date_format(date):
        #     if date:
        #         date = date.strftime(date_format)
        #     return date

        # def _header_sheet(sheet):
        #     sheet.write(0, 4, report.name, report_format)
        #     sheet.write(2, 0, _('Company:'), bold)
        #     sheet.write(3, 0, wizard.company_id.name,)
        #     sheet.write(4, 0, _('Print on %s') % report.print_time)

        #     sheet.write(2, 2, _('Start Date : %s ') % wizard.date_from if wizard.date_from else '')
        #     sheet.write(3, 2, _('End Date : %s ') % wizard.date_to if wizard.date_to else '')

        #     sheet.write(2, 4, _('Target Moves:'), bold)
        #     sheet.write(3, 4, _('All Entries') if wizard.target_move == 'all' else _('All Posted Entries'))

        #     sheet.write(2, 6, _('Only UnReconciled Entries') if wizard.reconciled is False else _('With Reconciled Entries'), bold)

        # if wizard.ledger_type == 'aged':

        #     if wizard.summary:
        #         sheet = workbook.add_worksheet(report.name)
        #         _header_sheet(sheet)

        #         head = [
        #             {'name': 'Code',
        #              'larg': 10,
        #              'col': {}},
        #             {'name': 'Name',
        #              'larg': 30,
        #              'col': {}},
        #             {'name': _('Not Due'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('0-30'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('30-60'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('60-90'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('90-120'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('Older'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('Total'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #         ]

        #         all_lines = wizard._sql_get_line_for_report(type_l=('4_total',))
        #         # print(all_lines)
        #         if all_lines:

        #             row = 6
        #             row += 1
        #             start_row = row
        #             for i, line in enumerate(all_lines):
        #                 i += row
        #                 sheet.write(i, 0, line.get('code', ''))
        #                 sheet.write(i, 1, line.get('name', ''))
        #                 sheet.write(i, 2, _get_data_float(line.get('current')), currency_format)
        #                 sheet.write(i, 3, _get_data_float(line.get('age_30_days')), currency_format)
        #                 sheet.write(i, 4, _get_data_float(line.get('age_60_days')), currency_format)
        #                 sheet.write(i, 5, _get_data_float(line.get('age_90_days')), currency_format)
        #                 sheet.write(i, 6, _get_data_float(line.get('age_120_days')), currency_format)
        #                 sheet.write(i, 7, _get_data_float(line.get('older')), currency_format)
        #                 sheet.write(i, 8, _get_data_float(line.get('balance')), currency_format)
        #             row = i

        #             for j, h in enumerate(head):
        #                 sheet.set_column(j, j, h['larg'])

        #             table = []
        #             for h in head:
        #                 col = {}
        #                 col['header'] = h['name']
        #                 col.update(h['col'])
        #                 table.append(col)

        #             sheet.add_table(start_row - 1, 0, row + 1, len(head) - 1,
        #                             {'total_row': 1,
        #                              'columns': table,
        #                              'style': 'Table Style Light 9',
        #                              })

        #     else:  # aged not summary
        #         head = [
        #             {'name': _('Date'),
        #              'larg': 10,
        #              'col': {}},
        #             {'name': _('JRNL'),
        #              'larg': 10,
        #              'col': {}},
        #             {'name': _('Account'),
        #              'larg': 10,
        #              'col': {}},
        #             {'name': _('Account Name'),
        #              'larg': 15,
        #              'col': {}},
        #             {'name': _('Journal entries'),
        #              'larg': 20,
        #              'col': {}},
        #             {'name': _('Ref'),
        #              'larg': 40,
        #              'col': {}},
        #             {'name': _('Partner'),
        #              'larg': 20,
        #              'col': {}},
        #             {'name': _('Due Date'),
        #              'larg': 10,
        #              'col': {}},
        #             {'name': _('Not Due'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('0-30'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('30-60'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('60-90'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('90-120'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('Older'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('Total'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('Match.'),
        #              'larg': 10,
        #              'col': {}},
        #         ]
        #         table = []
        #         for h in head:
        #             col = {'header': h['name']}
        #             col.update(h['col'])
        #             table.append(col)

        #         def _set_line(line):
        #             sheet.write(i, 0, get_date_format(line.get('date', '')))
        #             sheet.write(i, 1, line.get('j_code', ''))
        #             sheet.write(i, 2, line.get('a_code', ''))
        #             sheet.write(i, 3, line.get('a_name', ''))
        #             sheet.write(i, 4, line.get('move_name', ''))
        #             sheet.write(i, 5, line.get('displayed_name', ''))
        #             sheet.write(i, 6, line.get('partner_name', ''))
        #             sheet.write(i, 7, get_date_format(line.get('date_maturity', '')))
        #             sheet.write(i, 8, _get_data_float(line.get('current')), currency_format)
        #             sheet.write(i, 9, _get_data_float(line.get('age_30_days')), currency_format)
        #             sheet.write(i, 10, _get_data_float(line.get('age_60_days')), currency_format)
        #             sheet.write(i, 11, _get_data_float(line.get('age_90_days')), currency_format)
        #             sheet.write(i, 12, _get_data_float(line.get('age_120_days')), currency_format)
        #             sheet.write(i, 13, _get_data_float(line.get('older')), currency_format)
        #             sheet.write(i, 14, _get_data_float(line.get('balance')), currency_format)
        #             sheet.write(i, 15, line.get('matching_number', ''))

        #         def _set_table(start_row, row):
        #             sheet.add_table(start_row - 1, 0, row + 1, len(head) - 1,
        #                             {'total_row': 1,
        #                              'columns': table,
        #                              'style': 'Table Style Light 9',
        #                              })
        #             #sheet.write(row + 1, 10, "=I%s-J%s" % (row + 2, row + 2), currency_format)

        #         # With total workbook
        #         sheet = workbook.add_worksheet(report.name + _(' Totals'))
        #         _header_sheet(sheet)

        #         row = 6
        #         all_lines = wizard._sql_get_line_for_report(type_l=('1_init_line', '2_line'))
        #         for obj in report.report_object_ids:

        #             lines_obj = []
        #             obj_id = obj.id
        #             for line in all_lines:
        #                 if line.get('report_object_id') == obj_id:
        #                     lines_obj.append(line)
        #             if lines_obj:
        #                 row += 1
        #                 sheet.write(row, 0, obj.partner_id.name, left)  # obj.partner_id.name
        #                 sheet.write(row, 1, '', top)
        #                 sheet.write(row, 2, '', top)
        #                 sheet.write(row, 3, '', top)
        #                 sheet.write(row, 4, '', top)
        #                 sheet.write(row, 5, '', top)
        #                 sheet.write(row, 6, '', c_middle)
        #                 sheet.write(row, 7, '', c_middle)
        #                 sheet.write(row, 8, '', c_middle)
        #                 sheet.write(row, 9, '', c_middle)
        #                 sheet.write(row, 10, '', c_middle)
        #                 sheet.write(row, 11, '', c_middle)
        #                 sheet.write(row, 12, '', c_middle)
        #                 sheet.write(row, 13, '', c_middle)
        #                 sheet.write(row, 14, '', c_middle)
        #                 sheet.write(row, 15, '', right)

        #                 row += 2
        #                 start_row = row
        #                 for i, line in enumerate(lines_obj):
        #                     i += row
        #                     _set_line(line)

        #                 row = i

        #                 for j, h in enumerate(head):
        #                     sheet.set_column(j, j, h['larg'])

        #                 _set_table(start_row, row)
        #                 row += 2

        #         # Pivot
        #         sheet = workbook.add_worksheet(report.name)
        #         _header_sheet(sheet)

        #         # Head
        #         if all_lines:
        #             row = 6
        #             row += 1
        #             start_row = row
        #             for i, line in enumerate(all_lines):
        #                 i += row
        #                 _set_line(line)
        #             row = i

        #             for j, h in enumerate(head):
        #                 sheet.set_column(j, j, h['larg'])

        #             _set_table(start_row, row)

        # else:  # standard report

        #     if wizard.summary:
        #         sheet = workbook.add_worksheet(report.name)
        #         _header_sheet(sheet)

        #         all_lines = wizard._sql_get_line_for_report(type_l=('4_total',))
        #         if all_lines:
        #             # Head
        #             head = [
        #                 {'name': 'Code',
        #                  'larg': 10,
        #                  'col': {}},
        #                 {'name': 'Name',
        #                  'larg': 30,
        #                  'col': {}},
        #                 {'name': 'Debit',
        #                  'larg': 15,
        #                  'col': {'total_function': 'sum', 'format': currency_format}},
        #                 {'name': 'Credit',
        #                  'larg': 15,
        #                  'col': {'total_function': 'sum', 'format': currency_format}},
        #                 {'name': 'Balance',
        #                  'larg': 15,
        #                  'col': {'total_function': 'sum', 'format': currency_format}},
        #             ]

        #             row = 6
        #             row += 1
        #             start_row = row
        #             for i, line in enumerate(all_lines):
        #                 i += row
        #                 sheet.write(i, 0, line.get('code', ''))
        #                 sheet.write(i, 1, line.get('name', ''))
        #                 sheet.write(i, 2, line.get('debit', ''), currency_format)
        #                 sheet.write(i, 3, line.get('credit', ''), currency_format)
        #                 sheet.write(i, 4, line.get('balance', ''), currency_format)
        #             row = i

        #             for j, h in enumerate(head):
        #                 sheet.set_column(j, j, h['larg'])

        #             table = []
        #             for h in head:
        #                 col = {}
        #                 col['header'] = h['name']
        #                 col.update(h['col'])
        #                 table.append(col)

        #             sheet.add_table(start_row - 1, 0, row + 1, len(head) - 1,
        #                             {'total_row': 1,
        #                              'columns': table,
        #                              'style': 'Table Style Light 9',
        #                              })

        #     else:  # not summary

        #         head = [
        #             {'name': _('Date'),
        #              'larg': 10,
        #              'col': {}},
        #             {'name': _('JRNL'),
        #              'larg': 10,
        #              'col': {}},
        #             {'name': _('Account'),
        #              'larg': 10,
        #              'col': {}},
        #             {'name': _('Account Name'),
        #              'larg': 15,
        #              'col': {}},
        #             {'name': _('Analytic'),
        #              'larg': 20,
        #              'col': {}},
        #             {'name': _('Journal entries'),
        #              'larg': 20,
        #              'col': {}},
        #             {'name': _('Ref'),
        #              'larg': 40,
        #              'col': {}},
        #             {'name': _('Name'),
        #              'larg': 40,
        #              'col': {}},
        #             {'name': _('Partner'),
        #              'larg': 20,
        #              'col': {}},
        #             {'name': _('Due Date'),
        #              'larg': 10,
        #              'col': {}},
        #             {'name': _('Debit'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('Credit'),
        #              'larg': 15,
        #              'col': {'total_function': 'sum', 'format': currency_format}},
        #             {'name': _('Balance'),
        #              'larg': 15,
        #              'col': {'format': currency_format}},
        #             {'name': _('Amount Currency'),
        #                 'larg': 15,
        #                 'col': {}},
        #             {'name': _('Match.'),
        #              'larg': 10,
        #              'col': {}},
        #         ]
        #         table = []
        #         for h in head:
        #             col = {'header': h['name']}
        #             col.update(h['col'])
        #             table.append(col)

        #         def _set_line(line):
        #             sheet.write(i, 0, get_date_format(line.get('date', '')) if line.get('view_type') != 'init' else 'INIT')
        #             sheet.write(i, 1, line.get('j_code', ''))
        #             sheet.write(i, 2, line.get('a_code', ''))
        #             sheet.write(i, 3, line.get('a_name', ''))
        #             sheet.write(i, 4, "%s - %s" % (line.get('an_code', ''), line.get('an_name', '')) if line.get('an_code', '') else line.get('an_name', ''))
        #             sheet.write(i, 5, line.get('move_name', ''))
        #             sheet.write(i, 6, line.get('displayed_ref', ''))
        #             sheet.write(i, 7, line.get('displayed_name', ''))
        #             sheet.write(i, 8, line.get('partner_name', ''))
        #             sheet.write(i, 9, get_date_format(line.get('date_maturity', '')))
        #             sheet.write(i, 10, _get_data_float(line.get('debit', '')), currency_format)
        #             sheet.write(i, 11, _get_data_float(line.get('credit', '')), currency_format)
        #             sheet.write(i, 12, _get_data_float(line.get('cumul_balance', '')), currency_format)
        #             if line.get('amount_currency', ''):
        #                 sheet.write(i, 13, _get_data_float(line.get('amount_currency', '')), workbook.add_format({'num_format': line.get('currency')}))
        #             sheet.write(i, 14, line.get('matching_number', ''))

        #         def _set_table(start_row, row):
        #             sheet.add_table(start_row - 1, 0, row + 1, len(head) - 1,
        #                             {'total_row': 1,
        #                              'columns': table,
        #                              'style': 'Table Style Light 9',
        #                              })

        #         # With total workbook
        #         sheet = workbook.add_worksheet(report.name + _(' Totals'))
        #         _header_sheet(sheet)

        #         row = 6

        #         all_lines = wizard._sql_get_line_for_report(type_l=('0_init', '1_init_line', '2_line', '3_compact'))
        #         for obj in report.report_object_ids:
        #             lines_obj = []
        #             obj_id = obj.id
        #             for line in all_lines:
        #                 if line.get('report_object_id') == obj_id:
        #                     lines_obj.append(line)
        #             if lines_obj:
        #                 row += 1
        #                 name_view = ''
        #                 if wizard.report_type == 'account':
        #                     name_view = obj.account_id.display_name
        #                 if wizard.report_type == 'partner':
        #                     name_view = obj.partner_id.display_name
        #                 if wizard.report_type == 'journal':
        #                     name_view = obj.journal_id.display_name
        #                 if wizard.report_type == 'analytic':
        #                     name_view = obj.analytic_account_id.display_name

        #                 sheet.write(row, 0, name_view, left)
        #                 sheet.write(row, 1, '', top)
        #                 sheet.write(row, 2, '', top)
        #                 sheet.write(row, 3, '', top)
        #                 sheet.write(row, 4, '', top)
        #                 sheet.write(row, 5, '', top)
        #                 sheet.write(row, 6, '', top)
        #                 sheet.write(row, 7, '', top)
        #                 sheet.write(row, 8, '', top)
        #                 sheet.write(row, 9, '', top)
        #                 sheet.write(row, 10, '', top)
        #                 sheet.write(row, 11, '', top)
        #                 sheet.write(row, 12, '', top)
        #                 sheet.write(row, 13, '', top)
        #                 sheet.write(row, 14, '', right)

        #                 row += 2
        #                 start_row = row
        #                 for i, line in enumerate(lines_obj):
        #                     i += row
        #                     _set_line(line)

        #                 row = i

        #                 for j, h in enumerate(head):
        #                     sheet.set_column(j, j, h['larg'])

        #                 _set_table(start_row, row)
        #                 row += 2

        #         # Pivot workbook
        #         sheet = workbook.add_worksheet(report.name)
        #         _header_sheet(sheet)

        #         # Head
        #         if all_lines:
        #             row = 6
        #             row += 1
        #             start_row = row
        #             for i, line in enumerate(all_lines):
        #                 i += row
        #                 _set_line(line)
        #             row = i

        #             for j, h in enumerate(head):
        #                 sheet.set_column(j, j, h['larg'])

        #             _set_table(start_row, row)

        # workbook.close()
        # output.seek(0)
        # response.stream.write(output.read())
        # output.close()
        # del output # clear 
        # open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("tinggal return response"))
        # open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(sheet))
        # open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(workbook))
        # open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(response))
        # return response

        # open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(output))
        # return file_data.read(), "xlsx"



        from odoo.http import request, serialize_exception, content_disposition

        import io
        import xlsxwriter

        output = io.BytesIO()
        response = request.make_response(None, headers=[
            ('Content-Type', 'application/vnd.ms-excel'),
            ('Content-Disposition', content_disposition('Report standard ledger report.xlsx'))
        ])
        
        workbook = xlsxwriter.Workbook(output, {
            'constant_memory': True, 
            'in_memory': True, 
            'strings_to_numbers':False, 
            'strings_to_formulas':True, 
            'strings_to_urls':True, 
            'default_date_format':'yyyy-mm-dd'})

        workbook.set_properties({
            'title':    'Standard ledger report',
            'comments': 'Created with Odoo and XlsxWriter'
        })
        worksheet = workbook.add_worksheet()

        format_title = workbook.add_format()
        format_title.set_font_size(20)
        # format_title.set_font_color('blue')
        format_title.set_bold()

        format_header = workbook.add_format()
        format_header.set_bold()
        format_header.set_bg_color('yellow')
        format_header.set_border(1)
        format_header.set_align('center')

        format_content = workbook.add_format()
        format_content.set_bottom(1)

        format_currency = workbook.add_format()
        format_currency.set_num_format('#,##0.00')
        format_currency.set_align('right')
        format_currency.set_bottom(1)

        format_date = workbook.add_format()
        format_date.set_num_format('yyyy-mm-dd')
        format_date.set_align('left')
        format_date.set_bottom(1)

        format_datetime = workbook.add_format()
        format_datetime.set_num_format('yyyy-mm-dd hh:mm')
        format_datetime.set_align('left')
        format_datetime.set_bottom(1)

        format_footer = workbook.add_format()
        format_footer.set_bold()
        format_footer.set_bg_color('gray')
        format_footer.set_bottom(1)
        format_footer.set_align('right')
        format_footer.set_num_format('#,##0.00')
        
        # setup column
        worksheet.set_column(0, 40, 20)
        worksheet.set_column(7, 7, 50) # patient_name
        worksheet.set_column(10, 10, 50) # payer_name

        # create header
        worksheet.write(0, 0, 'XXX Report', format_title)
        worksheet.write(1, 0, 'Company: ')
        worksheet.write(2, 0, 'Date as: ')

        # create header
        worksheet.write(4, 0, 'Admission No', format_header)
        worksheet.write(4, 1, 'Admit Date', format_header)
        worksheet.write(4, 2, 'Patient Type', format_header)
        worksheet.write(4, 3, 'Bill No', format_header)
        worksheet.write(4, 4, 'Bill Date', format_header)
        worksheet.write(4, 5, 'Bill COB', format_header)
        worksheet.write(4, 6, 'Patient MRID', format_header)
        worksheet.write(4, 7, 'Patient Name', format_header)
        worksheet.write(4, 8, 'Patient DOB', format_header)
        worksheet.write(4, 9, 'Payer Code', format_header)
        worksheet.write(4, 10, 'Payer Name', format_header)
        worksheet.write(4, 11, 'Payer Type', format_header)
        worksheet.write(4, 12, 'Payer Category', format_header)
        worksheet.write(4, 13, 'Bill Amount (Nett)', format_header)
        worksheet.write(4, 14, 'Patient RoundOff', format_header)
        worksheet.write(4, 15, 'Patient Discount', format_header)
        worksheet.write(4, 16, 'Patient Canceled', format_header)
        worksheet.write(4, 17, 'Patient Amount', format_header)
        worksheet.write(4, 18, 'Patient Receipt', format_header)
        worksheet.write(4, 19, 'Patient Balance', format_header)
        worksheet.write(4, 20, 'Payer RoundOff', format_header)
        worksheet.write(4, 21, 'Payer Canceled', format_header)
        worksheet.write(4, 22, 'Payer Deduction', format_header)
        worksheet.write(4, 23, 'Payer Amount', format_header)
        worksheet.write(4, 24, 'Payer Unbilled', format_header)
        worksheet.write(4, 25, 'Letter No', format_header)
        worksheet.write(4, 26, 'Letter Date', format_header)
        worksheet.write(4, 27, 'Letter Due Date', format_header)
        worksheet.write(4, 28, 'Letter Sent Date', format_header)
        worksheet.write(4, 29, 'Letter Received Date', format_header)
        worksheet.write(4, 30, 'Letter Received By', format_header)
        worksheet.write(4, 31, 'Payer Disc. Invoice', format_header)
        worksheet.write(4, 32, 'Payer Invoiced', format_header)
        worksheet.write(4, 33, 'Payer Receipt', format_header)
        worksheet.write(4, 34, 'Payer WriteOff', format_header)
        worksheet.write(4, 35, 'Payer Balance', format_header)
        worksheet.write(4, 36, 'Aging Not OverDue', format_header)
        worksheet.write(4, 37, 'Aging 30 Days', format_header)
        worksheet.write(4, 38, 'Aging 60 Days', format_header)
        worksheet.write(4, 39, 'Aging 90 Days', format_header)
        worksheet.write(4, 40, 'Aging Older', format_header)


        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()
        del output # clear 
        
        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("unbilled"))
        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(workbook))
        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str(response))
        return response




    def get_workbook_options(self):
        """
        See https://xlsxwriter.readthedocs.io/workbook.html constructor options
        :return: A dictionary of options
        """
        return {}

    def generate_xlsx_report(self, workbook, data, objs):
        raise NotImplementedError()
