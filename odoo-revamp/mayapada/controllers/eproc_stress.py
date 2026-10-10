import json
import logging

from odoo import http
from odoo.exceptions import AccessDenied, AccessError, MissingError, UserError, ValidationError
from odoo.http import request


_logger = logging.getLogger(__name__)


class _BadRequest(Exception):
    pass


class _NotFound(Exception):
    pass


class EprocStressController(http.Controller):
    """HTTP adapters for existing eProc ORM and wizard workflows."""

    @staticmethod
    def _response(body, status=200):
        response = request.make_response(
            json.dumps(body), headers=[('Content-Type', 'application/json')]
        )
        response.status_code = status
        return response

    @staticmethod
    def _payload():
        raw = request.httprequest.get_data(as_text=True)
        if not raw:
            return {}
        if request.httprequest.mimetype != 'application/json':
            raise _BadRequest('Content-Type must be application/json.')
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            raise _BadRequest('Malformed JSON request body.')
        if not isinstance(payload, dict):
            raise _BadRequest('JSON request body must be an object.')
        return payload

    @staticmethod
    def _fields(payload, allowed, required=()):
        unknown = set(payload) - set(allowed)
        if unknown:
            raise _BadRequest('Unsupported field(s): %s.' % ', '.join(sorted(unknown)))
        missing = [key for key in required if key not in payload or payload[key] in (None, '')]
        if missing:
            raise _BadRequest('Required field(s): %s.' % ', '.join(missing))
        for key, value in payload.items():
            if key.endswith('_id') and value is not None and value is not False:
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    raise _BadRequest('%s must be a positive integer Odoo ID.' % key)
        return dict(payload)

    @staticmethod
    def _id(value, name):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise _BadRequest('%s must be a positive integer Odoo ID.' % name)
        return value

    def _ids(self, values, name):
        if not isinstance(values, list) or not values:
            raise _BadRequest('%s must be a nonempty array of Odoo IDs.' % name)
        ids = [self._id(value, name) for value in values]
        if len(ids) != len(set(ids)):
            raise _BadRequest('%s contains duplicate IDs.' % name)
        return ids

    def _lines(self, payload, allowed, required=(), taxes=False):
        lines = payload.get('line_ids')
        if not isinstance(lines, list) or not lines:
            raise _BadRequest('line_ids must be a nonempty array of objects.')
        commands = []
        for index, line in enumerate(lines, start=1):
            if not isinstance(line, dict):
                raise _BadRequest('line_ids[%s] must be an object.' % index)
            values = self._fields(line, allowed, required)
            if taxes and 'tax_ids' in values:
                tax_ids = values['tax_ids']
                values['tax_ids'] = [(6, 0, self._ids(tax_ids, 'tax_ids') if tax_ids else [])]
            commands.append((0, 0, values))
        return commands

    @staticmethod
    def _document(record, number_field):
        return {
            'id': record.id,
            'document_no': record[number_field] or record.display_name,
            'name': record.display_name,
            'state': record.state,
        }

    def _record(self, model, record_id):
        record = request.env[model].browse(record_id).exists()
        if not record:
            raise _NotFound('%s record %s was not found.' % (model, record_id))
        record.check_access_rights('read')
        record.check_access_rule('read')
        record.check_access_rights('write')
        record.check_access_rule('write')
        return record

    @staticmethod
    def _check_company(company_id):
        if company_id:
            company = request.env['res.company'].browse(company_id).exists()
            if not company:
                raise _NotFound('Company was not found.')
            if company not in request.env.companies:
                raise AccessError('Company is not available to the current user.')

    @staticmethod
    def _action_summary(action):
        if not isinstance(action, dict):
            return None
        result = {key: action[key] for key in (
            'type', 'name', 'res_model', 'res_id', 'target', 'view_mode'
        ) if key in action}
        for term in action.get('domain', []):
            if isinstance(term, (list, tuple)) and len(term) == 3 and term[0] == 'id' and term[1] == 'in':
                result['record_ids'] = term[2]
        if action.get('res_model') == 'eproc.orderpoint.realize.confirm.wizard' and action.get('res_id'):
            confirm = request.env[action['res_model']].browse(action['res_id'])
            result['confirmation'] = {
                'warning_type': confirm.warning_type,
                'message': confirm.message,
            }
        return result

    def _run(self, operation):
        try:
            payload = self._payload()
            with request.env.cr.savepoint():
                status, data = operation(payload)
            _logger.info('eProc stress API %s completed for user %s',
                         request.httprequest.path, request.env.user.id)
            return self._response({'success': True, 'data': data}, status)
        except _BadRequest as error:
            _logger.warning('eProc stress API bad request on %s: %s', request.httprequest.path, error)
            return self._response({'success': False, 'error': 'bad_request', 'message': str(error)}, 400)
        except _NotFound as error:
            return self._response({'success': False, 'error': 'not_found', 'message': str(error)}, 404)
        except (AccessError, AccessDenied) as error:
            _logger.warning('eProc stress API access denied on %s for user %s: %s',
                            request.httprequest.path, request.env.user.id, error)
            return self._response({'success': False, 'error': 'access_error', 'message': str(error)}, 403)
        except ValidationError as error:
            _logger.warning('eProc stress API validation failed on %s: %s', request.httprequest.path, error)
            return self._response({'success': False, 'error': 'validation_error', 'message': str(error)}, 422)
        except (UserError, MissingError) as error:
            _logger.warning('eProc stress API workflow failed on %s: %s', request.httprequest.path, error)
            return self._response({'success': False, 'error': 'user_error', 'message': str(error)}, 422)
        except Exception:
            _logger.exception('eProc stress API failed on %s for user %s',
                              request.httprequest.path, request.env.user.id)
            return self._response({'success': False, 'error': 'internal_error',
                                   'message': 'An internal error occurred.'}, 500)

    def _create(self, payload, model, number_field, header_fields, required_fields,
                line_fields, required_line_fields):
        values = self._fields(payload, set(header_fields) | {'line_ids'}, required_fields)
        self._check_company(values.get('company_id'))
        values['line_ids'] = self._lines(
            payload, line_fields, required_line_fields, taxes='tax_ids' in line_fields
        )
        record = request.env[model].create(values)
        return 201, self._document(record, number_field)

    def _transition(self, payload, model, record_id, method, number_field):
        self._fields(payload, ())
        record = self._record(model, record_id)
        action = getattr(record, method)()
        data = self._document(record, number_field)
        if isinstance(action, dict):
            data['action'] = self._action_summary(action)
            data['pending_action'] = True
        return 200, data

    @http.route('/api/stress/eproc/health', type='http', auth='user', methods=['GET'])
    def health(self, **kwargs):
        return self._response({'success': True, 'service': 'eproc-stress'})

    @http.route('/api/stress/eproc/pr', type='http', auth='user', methods=['POST'], csrf=False)
    def create_pr(self, **kwargs):
        return self._run(lambda data: self._create(
            data, 'eproc.request', 'request_no',
            {'company_id', 'purchase_type_id', 'supplier_id', 'approval_type_id', 'user_id',
             'department_id', 'request_date', 'request_ref', 'request_type', 'notes'},
            {'purchase_type_id'},
            {'product_tmpl_id', 'name', 'pack_id', 'pack_qty', 'pack_price', 'analytic_id'},
            {'product_tmpl_id', 'pack_qty'},
        ))

    @http.route('/api/stress/eproc/pr/<int:record_id>/confirm', type='http', auth='user', methods=['POST'], csrf=False)
    def confirm_pr(self, record_id, **kwargs):
        return self._run(lambda data: self._transition(data, 'eproc.request', record_id, 'action_confirm', 'request_no'))

    @http.route('/api/stress/eproc/pr/<int:record_id>/approve', type='http', auth='user', methods=['POST'], csrf=False)
    def approve_pr(self, record_id, **kwargs):
        return self._run(lambda data: self._transition(data, 'eproc.request', record_id, 'action_approve', 'request_no'))

    @http.route('/api/stress/eproc/rfq', type='http', auth='user', methods=['POST'], csrf=False)
    def create_rfq(self, **kwargs):
        return self._run(lambda data: self._create(
            data, 'eproc.order', 'order_no',
            {'company_id', 'purchase_type_id', 'approval_type_id', 'supplier_id', 'term_id',
             'agreement_id', 'order_ref', 'order_origin', 'stock_type', 'lead_time',
             'date_planned', 'department_id', 'user_id', 'location_receipt_id',
             'location_supplier_id', 'notes'},
            {'purchase_type_id', 'supplier_id'},
            {'product_tmpl_id', 'pack_id', 'pack_qty', 'pack_price', 'name', 'date_planned',
             'disc_rate', 'tax_ids', 'analytic_id', 'agreement_line_id'},
            {'product_tmpl_id', 'pack_qty', 'pack_price'},
        ))

    @http.route('/api/stress/eproc/rfq/<int:record_id>/confirm', type='http', auth='user', methods=['POST'], csrf=False)
    def confirm_rfq(self, record_id, **kwargs):
        return self._run(lambda data: self._transition(data, 'eproc.order', record_id, 'action_confirm', 'order_no'))

    @http.route('/api/stress/eproc/rfq/<int:record_id>/approve', type='http', auth='user', methods=['POST'], csrf=False)
    def approve_rfq(self, record_id, **kwargs):
        return self._run(lambda data: self._transition(data, 'eproc.order', record_id, 'action_approve', 'order_no'))

    @http.route('/api/stress/eproc/rfq/from-pr', type='http', auth='user', methods=['POST'], csrf=False)
    def rfq_from_pr(self, **kwargs):
        return self._run(self._rfq_from_pr)

    def _rfq_from_pr(self, payload):
        values = self._fields(payload, {
            'company_id', 'purchase_type_id', 'approval_type_id', 'realize_method', 'supplier_id',
            'supplier_ids', 'agreement_id', 'term_id', 'lead_time', 'date_planned', 'ref', 'line_ids',
        }, {'purchase_type_id', 'approval_type_id', 'line_ids'})
        self._check_company(values.get('company_id'))
        lines = values.pop('line_ids')
        if not isinstance(lines, list) or not lines:
            raise _BadRequest('line_ids must be a nonempty array.')
        line_values = []
        for index, line in enumerate(lines, start=1):
            if not isinstance(line, dict):
                raise _BadRequest('line_ids[%s] must be an object.' % index)
            line_values.append(self._fields(line, {'request_line_id', 'pack_order'}, {'request_line_id'}))
        request_line_ids = self._ids([line['request_line_id'] for line in line_values], 'request_line_id')
        request_lines = request.env['eproc.request.line'].browse(request_line_ids).exists()
        if len(request_lines) != len(request_line_ids):
            raise _NotFound('One or more Purchase Request lines were not found.')
        request_lines.check_access_rights('read')
        request_lines.check_access_rule('read')
        realize_method = values.get('realize_method', 'direct')
        if realize_method not in ('direct', 'tender'):
            raise _BadRequest('realize_method must be direct or tender.')
        if realize_method == 'direct' and not values.get('agreement_id'):
            raise _BadRequest('agreement_id is required for direct realization.')
        if realize_method == 'tender' and not values.get('supplier_ids'):
            raise _BadRequest('supplier_ids is required for tender realization.')
        if 'supplier_ids' in values:
            values['supplier_ids'] = [(6, 0, self._ids(values['supplier_ids'], 'supplier_ids'))]
        overrides = {key: values.pop(key) for key in ('term_id', 'lead_time', 'date_planned') if key in values}
        values['request_line_ids'] = [(6, 0, request_line_ids)]
        wizard = request.env['eproc.request.realize.wizard'].create(values)
        if realize_method == 'direct':
            wizard._onchange_agreement_id()
        if overrides:
            wizard.write(overrides)
        wizard._onchange_request_line_ids()
        for line in wizard.line_ids:
            selected = next(item for item in line_values if item['request_line_id'] == line.request_line_id.id)
            if 'pack_order' in selected:
                line.pack_order = selected['pack_order']
                line._onchange_pack_order()
        action = wizard.action_validate()
        summary = self._action_summary(action)
        rfq_ids = [summary['res_id']] if summary and summary.get('res_id') else (summary or {}).get('record_ids', [])
        if not rfq_ids:
            raise UserError('Request realization did not return an RFQ.')
        rfqs = request.env['eproc.order'].browse(rfq_ids).exists()
        return 201, {'rfqs': [self._document(record, 'order_no') for record in rfqs], 'action': summary}

    @http.route('/api/stress/eproc/agreement', type='http', auth='user', methods=['POST'], csrf=False)
    def create_agreement(self, **kwargs):
        return self._run(self._create_agreement)

    def _create_agreement(self, payload):
        if payload.get('type', 'rate') != 'rate':
            raise _BadRequest('Only rate agreements are supported by this endpoint.')
        return self._create(
            payload, 'eproc.agreement', 'code',
            {'type', 'ref', 'purchase_type_id', 'supplier_id', 'lead_time', 'date_start',
             'date_end', 'amount_limit', 'term_id', 'approval_type_id', 'user_id', 'company_id'},
            {'ref', 'purchase_type_id', 'supplier_id', 'date_start', 'date_end', 'approval_type_id'},
            {'product_tmpl_id', 'name', 'pack_id', 'pack_min', 'pack_max', 'pack_price',
             'pack_rate', 'disc_rate', 'tax_ids', 'pack_max_ordered', 'effective_date'},
            {'product_tmpl_id', 'pack_min', 'pack_price'},
        )

    @http.route('/api/stress/eproc/agreement/<int:record_id>/confirm', type='http', auth='user', methods=['POST'], csrf=False)
    def confirm_agreement(self, record_id, **kwargs):
        return self._run(lambda data: self._transition(data, 'eproc.agreement', record_id, 'action_confirm', 'code'))

    @http.route('/api/stress/eproc/agreement/<int:record_id>/approve', type='http', auth='user', methods=['POST'], csrf=False)
    def approve_agreement(self, record_id, **kwargs):
        return self._run(lambda data: self._transition(data, 'eproc.agreement', record_id, 'action_approve', 'code'))

    @http.route('/api/stress/eproc/orderpoint/generate', type='http', auth='user', methods=['POST'], csrf=False)
    def generate_orderpoint(self, **kwargs):
        return self._run(self._generate_orderpoint)

    def _generate_orderpoint(self, payload):
        self._fields(payload, {'company_id'})
        company = request.env.company
        if 'company_id' in payload:
            company = request.env['res.company'].browse(self._id(payload['company_id'], 'company_id')).exists()
            if not company:
                raise _NotFound('Company was not found.')
        if company not in request.env.companies:
            raise AccessError('Company is not available to the current user.')
        request.env['eproc.orderpoint'].check_access_rights('read')
        logs_model = request.env['eproc.orderpoint.log']
        logs_model.check_access_rights('create')
        logs = logs_model._generate_orderpoint_logs(company=company)
        return 200, {'company_id': company.id, 'created_log_ids': logs.ids, 'created_count': len(logs)}

    @http.route('/api/stress/eproc/orderpoint/realize-pr', type='http', auth='user', methods=['POST'], csrf=False)
    def realize_orderpoint_pr(self, **kwargs):
        return self._run(self._realize_orderpoint_pr)

    def _realize_orderpoint_pr(self, payload):
        values = self._fields(payload, {
            'company_id', 'user_id', 'purchase_type_id', 'approval_type_id', 'log_ids',
            'ref', 'analytic_id',
        }, {'purchase_type_id', 'approval_type_id', 'log_ids'})
        self._check_company(values.get('company_id'))
        log_ids = self._ids(values['log_ids'], 'log_ids')
        logs = request.env['eproc.orderpoint.log'].browse(log_ids).exists()
        if len(logs) != len(log_ids):
            raise _NotFound('One or more Orderpoint Logs were not found.')
        logs.check_access_rights('read')
        logs.check_access_rule('read')
        if any(log.company_id not in request.env.companies for log in logs):
            raise AccessError('An Orderpoint Log company is not available to the current user.')
        values['log_ids'] = [(6, 0, log_ids)]
        wizard = request.env['eproc.orderpoint.realize.wizard'].create(values)
        action = wizard.action_confirm_realize()
        summary = self._action_summary(action)
        if summary and summary.get('res_model') == 'eproc.orderpoint.realize.confirm.wizard':
            return 202, {'pending_action': True, 'action': summary}
        if not summary or summary.get('res_model') != 'eproc.request' or not summary.get('res_id'):
            raise UserError('Orderpoint realization did not return a Purchase Request.')
        record = request.env['eproc.request'].browse(summary['res_id']).exists()
        return 201, {'request': self._document(record, 'request_no'), 'action': summary}

    @http.route('/api/stress/eproc/receipt', type='http', auth='user', methods=['POST'], csrf=False)
    def create_receipt(self, **kwargs):
        return self._run(self._create_receipt)

    def _create_receipt(self, payload):
        receipt_type = payload.get('receipt_type', 'PO')
        if receipt_type not in ('PO', 'WO', 'RT'):
            raise _BadRequest('receipt_type must be PO, WO, or RT.')
        header = {'receipt_type', 'receipt_method', 'receipt_ref', 'receipt_date', 'company_id',
                  'purchase_type_id', 'approval_type_id', 'user_id', 'department_id',
                  'supplier_id', 'location_receipt_id', 'location_supplier_id', 'order_id',
                  'notes', 'line_ids'}
        values = self._fields(payload, header, {'supplier_id', 'line_ids'})
        self._check_company(values.get('company_id'))
        if receipt_type in ('PO', 'RT'):
            if not values.get('purchase_type_id'):
                raise _BadRequest('purchase_type_id is required for PO/RT receipts.')
            allowed_line = {'order_line_id', 'pack_receipt', 'pack_price', 'disc_rate', 'tax_ids',
                            'lot_id', 'lot_name', 'lot_expiration_date', 'analytic_id'}
            lines = self._lines(payload, allowed_line, {'order_line_id', 'pack_receipt'}, taxes=True)
            order_line_ids = [line[2]['order_line_id'] for line in lines]
            self._ids(order_line_ids, 'order_line_id')
            if values.get('receipt_method', 'single') == 'single' and not values.get('order_id'):
                raise _BadRequest('order_id is required for single PO/RT receipts.')
            values['order_line_ids'] = [(6, 0, order_line_ids)]
        else:
            allowed_line = {'product_tmpl_id', 'product_categ_id', 'name', 'pack_id',
                            'pack_receipt', 'pack_price', 'pack_rate', 'uom_id', 'disc_rate',
                            'tax_ids', 'lot_id', 'lot_name', 'lot_expiration_date', 'analytic_id'}
            lines = self._lines(payload, allowed_line,
                                {'product_tmpl_id', 'name', 'pack_id', 'pack_receipt',
                                 'pack_price', 'pack_rate', 'uom_id'}, taxes=True)
        values['line_ids'] = lines
        record = request.env['eproc.receipt'].create(values)
        return 201, self._document(record, 'receipt_no')

    @http.route('/api/stress/eproc/receipt/<int:record_id>/confirm-bay', type='http', auth='user', methods=['POST'], csrf=False)
    def confirm_receipt_bay(self, record_id, **kwargs):
        return self._run(lambda data: self._transition(data, 'eproc.receipt', record_id, 'action_confirm_srb', 'receipt_no'))

    @http.route('/api/stress/eproc/receipt/<int:record_id>/validate', type='http', auth='user', methods=['POST'], csrf=False)
    def validate_receipt(self, record_id, **kwargs):
        return self._run(lambda data: self._transition(data, 'eproc.receipt', record_id, 'action_confirm_srv', 'receipt_no'))

    @http.route('/api/stress/eproc/receipt/<int:record_id>/confirm-return', type='http', auth='user', methods=['POST'], csrf=False)
    def confirm_return(self, record_id, **kwargs):
        return self._run(lambda data: self._transition(data, 'eproc.receipt', record_id, 'action_confirm_return', 'receipt_no'))
