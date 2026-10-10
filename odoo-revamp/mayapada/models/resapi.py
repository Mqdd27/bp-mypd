# convert dict to json
from json import dumps as json
# convert json to dict
from json import loads
# regexpression
from re import finditer
# ordered dict
from collections import OrderedDict as dict
from funcsigs import signature
from traceback import format_exc
# from data import isint, isfloat
# load odoo library
from odoo import fields, http, tools, exceptions
from odoo.http import request, serialize_exception, content_disposition
from odoo.service.db import list_dbs
# from odoo.addons.web.controllers.main import serialize_exception, content_disposition
from  . import sync
from bottle import route 

operations = ['browse', 'search', 'create', 'write', 'unlink']


# define split
def split(identifier):
    matches = finditer('.+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)', identifier)
    return [m.group(0) for m in matches]


# define parse
def parse(data):
    data = {key: int(value) if isinstance((value),int) else float(value) if isinstance((value), float) else True if value in ['True', 'true'] else False if value in ['False', 'false'] else None if value in ['null', 'undefined'] else loads(value) if value[0:1] in ['{', '['] else str(value) for key, value in data.items()}
    return data



# define process values
def process_values(data, request, model):
    relational_fields = {key: value.comodel_name for key, value in request.env[model]._fields.items() if type(value) in [fields.Many2one, fields.One2many]}
    #open('/opt/odoo16/logs/d.log', 'w+').write(str(relational_fields))
    #data = {'_'.join(split(key)).lower(): value for key, value in data.iteritems() if key != 'sync_type'}
    data = {key: value if not relational_fields.get(key) else request.env[relational_fields[key]].search([('sync_id_api', '=', value)], limit=1, order='id asc').id for key, value in data.items()}
    return data


# define decorate
def decorate():
    functions = ''
    for model in request.env:
        for operation in operations:
            route = '/api/%s/%s' % (operation, model)
            if route:
                function = """\n
    @http.route('reserved_route', type='http', auth='user')
    @route()
    def api_method(self, **args):
        data = {}
        args = parse(args)
        operation = 'reserved_operation'
        model = 'reserved_model'
        self = request.env[model]
        try:
            if operation == 'search' and not args.get('sql_query'):
               args, offset, limit, order, count, access_rights_uid = [args.get(key, value) for key, value in dict(args=[], offset=0, limit=None, order=None, count=False, access_rights_uid=None).iteritems()]
               self.sudo(access_rights_uid or self._uid).check_access_rights('read')
               query = self._where_calc(args)
               self._apply_ir_rules(query, 'read')
               order_by = self._generate_order_by(order, query)
               from_clause, where_clause, where_clause_params = query.get_sql()
               where_str = where_clause and (" WHERE %s" % where_clause) or ''
               if count:
                  query_str = 'SELECT count(1) FROM ' + from_clause + where_str
                  self._cr.execute(query_str, where_clause_params)
                  res = self._cr.fetchone()
                  return res[0]
               limit_str = limit and ' limit %d' % limit or ''
               offset_str = offset and ' offset %d' % offset or ''
               query_str = 'SELECT "%s".id FROM ' % self._table + from_clause + where_str + order_by + limit_str + offset_str
               self._cr.execute(query_str, where_clause_params)
               return request.make_response(json({'status': 'success', 'data': self._cr.dictfetchall()}), [('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])
            records = request.env[model][operation](**args)
            result = True
            if operation not in ['write', 'unlink']:
               result = records.read(loads=False)
            data.update({'status': 'success', 'data': result})
        except Exception as error:
            data.update({'status': 'error', 'message': str(error)})
        return request.make_response(json(data), [('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])
               """
                reserved = {'route': route, 'operation': operation, 'model': model}
                for word in reserved:
                    function = function.replace('reserved_' + word, reserved[word])
                functions += function
    return functions


# define API controller
class ApiController(http.Controller):

    # define overview_data
    @http.route('/api/overview_data', type='http', auth='public', csrf=False)
    @route()
    def overview_data(self, **post):
        filecontent = {}
        if (post.get('login') and post.get('password')) or request.session.uid:
            if not post.get('database'):
                #If no database is passed on the ajax post, get one random database
                #from odoo.service.db import list_dbs
                post['database'] = 'MAYAPADA-LIVE16'  #list_dbs()[0]
            login = request.session.uid
            if not login:
                login = request.session.authenticate(post['database'], post['login'], post['password'])
            #If login doesn't return uid, return json with status denied
            if not login:
                filecontent['status'] = 'denied'
                return request.make_response(json(filecontent), [('Access-Control-Allow-Origin', '*')])
            #If login successful, you can execute functions and access datas
            filecontent = {'status':'success','data':request.env['sale.overview.template'].search([('company_id', '=', request.env.company.id)], limit=1).read()}
        #If no data filled in the dict, return error
        if not filecontent:
            filecontent = {'status': 'error'}
        return request.make_response(json(filecontent),[('Access-Control-Allow-origin', '*')])


    # define api authentication
    @http.route('/api/auth', type='http', auth='public', csrf=False)
    @route()
    def auth(self, login, password, db='MAYAPADA-LIVE16', **kw):
        open('/opt/odoo16/logs/auth.log', 'a+').write('\n' + str('xxx'))
        from odoo.http import request
        data = {}
        
        uid = request.session.authenticate('MAYAPADA-LIVE16', login, password)
        open('/opt/odoo16/logs/auth.log', 'a+').write('\n' + str(uid))
        if not uid:
            data['status'] = 'denied'
        else:
            token = request.csrf_token()
            data.update({'status': 'success', 'csrf_token': token, 'uid': uid})
            open('/opt/odoo16/logs/auth.log', 'a+').write('\n' + str(data))
        return request.make_response(json(data),[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])


    # define api list models
    @http.route('/api/models', type='http', auth='user', csrf=False)
    @route()
    def models(self, **kw):
        data = {'status': 'success', 'models': request.env.keys()}
        return request.make_response(json(data),[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])


    # define api list fields
    @http.route('/api/fields', type='http', auth='user', csrf=False)
    @route()
    def fields(self, model, **kw):
        data = {'status': 'error'}
        if model in request.env:
            data.update({'status': 'success', 'fields': request.env[model]._fields.keys()})
        else:
            data['message'] = "Model doesn't exist"
        return request.make_response(json(data),[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])


    # define api field details
    @http.route('/api/fields_details', type='http', auth='user', csrf=False)
    @route()
    def fields_details(self, model, **kw):
        data = {'status': 'error'}
        if model in request.env:
            data.update({'status': 'success', 'fields': request.env['ir.model.fields'].sudo().search([('model', '=', model)]).read(load=False) })
        else:
            data['message'] = "Model doesn't exist"
        return request.make_response(json(data),[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])


    # define api function parameter
    @http.route('/api/function_parameters', type='http', auth='user', csrf=False)
    @route()
    def function_parameters(self, model, function, **kw):
        data = {'status': 'error'}
        if model in request.env:
            data.update({'status':'success', 'function_parameters': str(signature(getattr(request.env[model], function))).replace('True', 'true').replace('False', 'false')})
        else:
            data['message'] = "Model doesn't exist"
        return request.make_response(json(data),[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])


    # define api operation
    # HIS-Odoo Integration data 
    @http.route('/api/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_method(self, operation, model, **args):
        #open('/opt/odoo16/logs/jancoks.log', 'a+').write('\n' + str(request.env.user.login))
        data = {}
        origin_args = args
        args = parse(args)


        # define log
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
        log_dir = '/opt/odoo16/logs/api/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        # if os.path.exists(log_file):
        #     if os.path.getsize(log_file) > 1000000:
        #         time_name_ren = '_' + datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S")
        #         log_file_ren = log_dir + log_name + time_name_ren + '.log'
        #         os.rename(log_file, log_file_ren)
        open(log_file, 'a').write(message)

        # 2021.09.06 integrasi stock.picking dan stock.move sementara disable
        # Sampai docotel bisa kirim mutasi stock ke stock.picking sesuai dokumentasi terbaru
        if model in['stock.picking','stock.move']:
            data.update({'status': 'error', 'message': "Integration model for stock.picking & stock.move temporary disabled."})
            json_data = json(data)
            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

        # for args in argss:
        # args = eval(args)

        self = request.env[model]
        # if args.get('context'):
        #     self = self.with_context(**args['context'])
        #     del args['context']

        try:
            # if operation search
            if operation == 'search' and args.get('sql_query'):
                kwargs = dict(args)
                default = dict(args=[],offset=0,limit=None,order=None,count=False,access_rights_uid=None)
                args, offset, limit, order, count, access_rights_uid = [kwargs.get(variable, default.get(variable)) for variable in ['args', 'offset', 'limit', 'order', 'count', 'access_rights_uid']]
                self.sudo(access_rights_uid or self._uid).check_access_rights('read')
                query = self._where_calc(args)
                self._apply_ir_rules(query, 'read')
                order_by = self._generate_order_by(order, query)
                from_clause, where_clause, where_clause_params = query.get_sql()
                where_str = where_clause and (" WHERE %s" % where_clause) or ''
                #if count request
                if count:
                    query_str = 'SELECT count(1) FROM ' + from_clause + where_str
                    self._cr.execute(query_str, where_clause_params)
                    res = self._cr.fetchone()
                    return res[0]

                limit_str = limit and ' limit %d' % limit or ''
                offset_str = offset and ' offset %d' % offset or ''
                query_str = 'SELECT "%s" FROM ' % self._table + from_clause + where_str + order_by + limit_str + offset_str
                self._cr.execute(query_str, where_clause_params)
                return request.make_response( json({'status': 'success', 'data': self._cr.dictfetchall() }), [('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])


            # browse all record model
            records = request.env[model].browse()
            # filter record by ids parameter
            if 'ids' in args:
                records = records.browse(args['ids'])
                del args['ids']


            # define unit ids
            api_ids = []
            #conflict_ids = []
            values_or_vals = 'vals'
            relational_fields = {}


            # if create operation
            if operation == 'create':
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                open(log_file, 'a').write("\n" + datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f") + " --start search sync_id_api")
                for value in args['values']:
                    self.env.cr.execute("SELECT sync_id_api FROM {model} WHERE sync_type = '{sync_type}' AND sync_id_api = '{sync_id}'" . format(model=model.replace(".", "_"), sync_type=value['sync_type'], sync_id=value['sync_id_api']))
                    api_ids += [object[0] for object in self.env.cr.fetchall()]
                open(log_file, 'a').write("\n" + datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f") + " --end search sync_id_api")

            # if operation create or write
            if operation in ['create', 'write']:
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                # by pass parameter "value"
                if args.get('value'):
                    raise Exception('Unrecognized parameter "value"')
                values_or_vals = 'values' if signature(getattr(request.env[model], operation)).parameters.get('values', False) else 'vals'
                
                # stored data relation fields
                relational_fields = {key: value.comodel_name for key, value in request.env[model]._fields.items() if type(value) in [fields.Many2one, fields.One2many]}


            for args in [args] if operation not in ['create', 'write'] else [{values_or_vals:value} for value in (args.get('vals', []) + args.get('values', []))]:
                # records = eval('request.env[model].%s(**args)' % (operation))
                
                #Checking Tanggal Proses
                if model in ['sale.order.line']:
                    if args[values_or_vals]['sync_type'] == '6':
                        tanggal_lock = request.env['res.company'].search([('name', '=', 'Mayapada Hospital Kuningan'),('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').period_lock_date
                        if args[values_or_vals]['tglproses'] <= tanggal_lock:
                            data.update({'status': 'error', 'message': 'Tanggal Proses Melewati Tanggal Lock Date'})
                            data.update({'data': 'Tanggal Lock : ' + tanggal_lock})
                            json_data = json(data)
                            log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
                            message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                            message += "\n\n================= end ==================="
                            open(log_file, 'a').write(message)
                            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])
                    if args[values_or_vals]['sync_type'] == '3':
                        tanggal_lock = request.env['res.company'].search([('name', '=', 'Mayapada Hospital Surabaya'),('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').period_lock_date
                        if args[values_or_vals]['tglproses'] <= tanggal_lock:
                            data.update({'status': 'error', 'message': 'Tanggal Proses Melewati Tanggal Lock Date'})
                            data.update({'data': 'Tanggal Lock : ' + tanggal_lock})
                            json_data = json(data)
                            log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
                            message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                            message += "\n\n================= end ==================="
                            open(log_file, 'a').write(message)
                            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])
                    if args[values_or_vals]['sync_type'] == '7':
                        tanggal_lock = request.env['res.company'].search([('name', '=', 'Mayapada Hospital Bogor'),('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').period_lock_date
                        if args[values_or_vals]['tglproses'] <= tanggal_lock:
                            data.update({'status': 'error', 'message': 'Tanggal Proses Melewati Tanggal Lock Date'})
                            data.update({'data': 'Tanggal Lock : ' + tanggal_lock})
                            json_data = json(data)
                            log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
                            message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                            message += "\n\n================= end ==================="
                            open(log_file, 'a').write(message)
                            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])
                #if operation == 'create':
                #    # define conflict_ids
                #    if args[values_or_vals]['sync_id_api'] in api_ids:
                #        conflict_ids += [args[values_or_vals]['sync_id_api']]
                #        continue


                # if create/write operation
                if operation in ['create', 'write']:
                    # reformat args values, convert relation sync_id_api to odoo object id
                    # for key, value in args[values_or_vals].iteritems():
                    #     open(log_file, 'a+').write('\n' + 'SEBELUM ' + 'key  ' + str(key) + 'value   ' + str(value))
                    #     if relational_fields.get(key) and type(value) in [str, unicode]:
                    #         open(log_file, 'a+').write('\n' + 'SEBELUM ' + 'relational field  ' + str(relational_fields[key]))

                    

                    # open(log_file, 'a+').write('\n' + 'SEBELUM ' +str(relational_fields))
                    # open(log_file, 'a+').write('\n' + 'SEBELUM ' +str(args[values_or_vals]))
                    
                    args[values_or_vals] = {key: request.env[relational_fields[key]].search([('sync_id_api', '=', value),('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id if relational_fields.get(key) and type(value) in [str] else value for key, value in args[values_or_vals].items()}
                    # open(log_file, 'a+').write('\n' + 'Sesudah ' +str(args[values_or_vals]))
                    

                # if operation not write
                if not operation == 'write':
                    result = False

                    # if operation create
                    if operation == 'create':
                        # create log message
                        message = "\n\nExecute API Create"
                        open(log_file, 'a').write(message)
                        open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK CREATE 0")
                    
                        # create new record data
                        result = request.env[model].create(**args)
                        open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK CREATE 1 : " + str(result))
                    # open('/opt/odoo16/logs/debugcheck.log', 'a+').write('\n'+ '\n'+ '\n' + str(args) + 'print diatas sini Args')
                        # open(log_file, 'a').write(json(result))

                        # add latest id to temp variable
                        api_ids.append(result.sync_id_api)

                    # if operation unlink
                    # else:
                        # autocall operation method in records
                        # result = getattr(records, operation)(**args)

                    # if create operation, add new record data to result
                    if operation != 'unlink':
                        records += result
                        open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK CREATE 2 : " + str(records))
                    

                # if write operation
                else:
                    open(log_file, 'a').write("\n"+datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f") + " --action write")
                    if args[values_or_vals].get('sync_id_api'):
                        args[values_or_vals]['id'] = request.env[model].search([('sync_id_api', '=', args[values_or_vals]['sync_id_api']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                        open(log_file, 'a').write("\n"+datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f") + " --done search model.id")
                    
                        record = request.env[model].browse(args[values_or_vals]['id'])
                        open(log_file, 'a').write("\n"+datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f") + " --done browse record")
                        if record:
                    
                            # autocall write method in record
                            getattr(record, operation)(**args)
                            open(log_file, 'a').write("\n"+datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f") + " --done update record")
                            records += record

                            result = records.read(load=False)
                            import datetime
                            if result:
                                for rec in result:
                                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                            else:
                                rec = True    



                            open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK SINI 0 ")
                
                            data.update({'status': 'success', 'data': rec})




                        if not record:
                            data.update({'status': 'error', 'message': "Record tidak ditemukan"})
                            json_data = json(data)
                            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

            # kenapa harus taruh result True disini ??
            result = True

            # if operation not write or unlink
            if operation not in ['write', 'unlink']:
                open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK SINI 1 ")
                result = records.read(load=False)
                open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK CREATE 3 : " + str(records))
                open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK CREATE 4 : " + str(result))
                import datetime
                if result:
                    for rec in result:
                        open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK SINI 1  looping")
                    
                        rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                        rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                else:
                    rec = True
                        

                if model == 'res.partner':
                    list_create = []
                    value_create = {}
                    value_create["id"] = result[0]["id"]
                    list_create.append(value_create)
                    result_create = list_create
                    import datetime
                    for rec in result_create:
                        rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                        rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}

                    data.update({'status': 'success', 'data': rec})


                open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK SINI 2 ")
                
                data.update({'status': 'success', 'data': rec})

            # update data result
            open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK SINI 3 ")
                
            data.update({'status': 'success', 'data': rec})

            ## if have conflict_ids
            #if conflict_ids:
            #    data.update({'message': 'Some of the id are already created'})
            #    # data.update({'data': '(%s)' % (json(conflict_ids))})
            #    data.update({'data': conflict_ids})

        # show error exception
        except:
            data.update({'status': 'error', 'message': format_exc()})

        json_data = json(data)
        # log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message = "\n\ntimelog: " + "\n\nresponse: " + json_data
        message += "\n\n================= end ==================="
        open(log_file, 'a').write(message)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])





    # define api operation
    # HIS-Odoo Integration data 
    @http.route('/qa_api/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def qa_api_method(self, operation, model, **args):
        open('/opt/odoo16/logs/jancoks.log', 'a+').write('\n' + str(request.env.user.login))
        data = {}
        origin_args = args
        args = parse(args)


        # define log
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
        log_dir = '/opt/odoo16/logs/api/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        # if os.path.exists(log_file):
        #     if os.path.getsize(log_file) > 1000000:
        #         time_name_ren = '_' + datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S")
        #         log_file_ren = log_dir + log_name + time_name_ren + '.log'
        #         os.rename(log_file, log_file_ren)
        open(log_file, 'a').write(message)

        # 2021.09.06 integrasi stock.picking dan stock.move sementara disable
        # Sampai docotel bisa kirim mutasi stock ke stock.picking sesuai dokumentasi terbaru
        if model in['stock.picking','stock.move']:
            data.update({'status': 'error', 'message': "Integration model for stock.picking & stock.move temporary disabled."})
            json_data = json(data)
            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

        # for args in argss:
        # args = eval(args)

        open('/opt/odoo16/logs/jancoks.log', 'a+').write('\n' + str(request.env.user.login) + "  sini 01")
        self = request.env[model]
        # if args.get('context'):
        #     self = self.with_context(**args['context'])
        #     del args['context']

        try:
            # if operation search
            if operation == 'search' and args.get('sql_query'):
                kwargs = dict(args)
                default = dict(args=[],offset=0,limit=None,order=None,count=False,access_rights_uid=None)
                args, offset, limit, order, count, access_rights_uid = [kwargs.get(variable, default.get(variable)) for variable in ['args', 'offset', 'limit', 'order', 'count', 'access_rights_uid']]
                self.sudo(access_rights_uid or self._uid).check_access_rights('read')
                query = self._where_calc(args)
                self._apply_ir_rules(query, 'read')
                order_by = self._generate_order_by(order, query)
                from_clause, where_clause, where_clause_params = query.get_sql()
                where_str = where_clause and (" WHERE %s" % where_clause) or ''
                #if count request
                if count:
                    query_str = 'SELECT count(1) FROM ' + from_clause + where_str
                    self._cr.execute(query_str, where_clause_params)
                    res = self._cr.fetchone()
                    return res[0]

                limit_str = limit and ' limit %d' % limit or ''
                offset_str = offset and ' offset %d' % offset or ''
                query_str = 'SELECT "%s" FROM ' % self._table + from_clause + where_str + order_by + limit_str + offset_str
                self._cr.execute(query_str, where_clause_params)
                return request.make_response( json({'status': 'success', 'data': self._cr.dictfetchall() }), [('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])


            # browse all record model
            records = request.env[model].browse()
            # filter record by ids parameter
            if 'ids' in args:
                records = records.browse(args['ids'])
                del args['ids']


            # define unit ids
            api_ids = []
            #conflict_ids = []
            values_or_vals = 'vals'
            relational_fields = {}


            # if create operation
            if operation == 'create':
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                open(log_file, 'a').write("\n" + datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f") + " --start search sync_id_api")
                # for value in args['values']:
                #     self.env.cr.execute("SELECT sync_id_api FROM {model} WHERE sync_type = '{sync_type}' AND sync_id_api = '{sync_id}'" . format(model=model.replace(".", "_"), sync_type=value['sync_type'], sync_id=value['sync_id_api']))
                #     api_ids += [object[0] for object in self.env.cr.fetchall()]
                # open(log_file, 'a').write("\n" + datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f") + " --end search sync_id_api")

            # if operation create or write
            if operation in ['create', 'write']:
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                # by pass parameter "value"
                if args.get('value'):
                    raise Exception('Unrecognized parameter "value"')
                values_or_vals = 'values' if signature(getattr(request.env[model], operation)).parameters.get('values', False) else 'vals'
                
                # stored data relation fields
                relational_fields = {key: value.comodel_name for key, value in request.env[model]._fields.items() if type(value) in [fields.Many2one, fields.One2many]}


            for args in [args] if operation not in ['create', 'write'] else [{values_or_vals:value} for value in (args.get('vals', []) + args.get('values', []))]:
                # records = eval('request.env[model].%s(**args)' % (operation))
                
                #Checking Tanggal Proses
                if model in ['sale.order.line']:
                    if args[values_or_vals]['sync_type'] == '6':
                        tanggal_lock = request.env['res.company'].search([('name', '=', 'Mayapada Hospital Kuningan'),('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').period_lock_date
                        if args[values_or_vals]['tglproses'] <= tanggal_lock:
                            data.update({'status': 'error', 'message': 'Tanggal Proses Melewati Tanggal Lock Date'})
                            data.update({'data': 'Tanggal Lock : ' + tanggal_lock})
                            json_data = json(data)
                            log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
                            message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                            message += "\n\n================= end ==================="
                            open(log_file, 'a').write(message)
                            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])
                    if args[values_or_vals]['sync_type'] == '3':
                        tanggal_lock = request.env['res.company'].search([('name', '=', 'Mayapada Hospital Surabaya'),('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').period_lock_date
                        if args[values_or_vals]['tglproses'] <= tanggal_lock:
                            data.update({'status': 'error', 'message': 'Tanggal Proses Melewati Tanggal Lock Date'})
                            data.update({'data': 'Tanggal Lock : ' + tanggal_lock})
                            json_data = json(data)
                            log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
                            message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                            message += "\n\n================= end ==================="
                            open(log_file, 'a').write(message)
                            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])
                    if args[values_or_vals]['sync_type'] == '7':
                        tanggal_lock = request.env['res.company'].search([('name', '=', 'Mayapada Hospital Bogor'),('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').period_lock_date
                        if args[values_or_vals]['tglproses'] <= tanggal_lock:
                            data.update({'status': 'error', 'message': 'Tanggal Proses Melewati Tanggal Lock Date'})
                            data.update({'data': 'Tanggal Lock : ' + tanggal_lock})
                            json_data = json(data)
                            log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
                            message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                            message += "\n\n================= end ==================="
                            open(log_file, 'a').write(message)
                            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])
                #if operation == 'create':
                #    # define conflict_ids
                #    if args[values_or_vals]['sync_id_api'] in api_ids:
                #        conflict_ids += [args[values_or_vals]['sync_id_api']]
                #        continue


                # if create/write operation
                if operation in ['create', 'write']:
                    # reformat args values, convert relation sync_id_api to odoo object id
                    # for key, value in args[values_or_vals].iteritems():
                    #     open(log_file, 'a+').write('\n' + 'SEBELUM ' + 'key  ' + str(key) + 'value   ' + str(value))
                    #     if relational_fields.get(key) and type(value) in [str, unicode]:
                    #         open(log_file, 'a+').write('\n' + 'SEBELUM ' + 'relational field  ' + str(relational_fields[key]))

                    

                    # open(log_file, 'a+').write('\n' + 'SEBELUM ' +str(relational_fields))
                    # open(log_file, 'a+').write('\n' + 'SEBELUM ' +str(args[values_or_vals]))
                    
                    args[values_or_vals] = {key: request.env[relational_fields[key]].search([('id', '=', value)], limit=1, order='id asc').id if relational_fields.get(key) and type(value) in [str] else value for key, value in args[values_or_vals].items()}
                    # open(log_file, 'a+').write('\n' + 'Sesudah ' +str(args[values_or_vals]))
                    

                # if operation not write
                if not operation == 'write':
                    result = False

                    # if operation create
                    if operation == 'create':
                        open('/opt/odoo16/logs/jancoks.log', 'a+').write('\n' + str(request.env.user.login) + "  sini 02")
        
                        # create log message
                        message = "\n\nExecute API Create"
                        open(log_file, 'a').write(message)
                        open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK CREATE 0")
                    
                        # create new record data
                        open('/opt/odoo16/logs/jancoks.log', 'a+').write('\n' + str(args) + "  sini 02.5")
                        result = request.env[model].create(**args)
                        open('/opt/odoo16/logs/jancoks.log', 'a+').write('\n' + str(request.env.user.login) + "  sini 03")
                        open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK CREATE 1 : " + str(result))
                    # open('/opt/odoo16/logs/debugcheck.log', 'a+').write('\n'+ '\n'+ '\n' + str(args) + 'print diatas sini Args')
                        # open(log_file, 'a').write(json(result))

                        # add latest id to temp variable
                        api_ids.append(result.id)

                    # if operation unlink
                    # else:
                        # autocall operation method in records
                        # result = getattr(records, operation)(**args)

                    # if create operation, add new record data to result
                    if operation != 'unlink':
                        records += result
                        open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK CREATE 2 : " + str(records))
                    

                # if write operation
                else:
                    open(log_file, 'a').write("\n"+datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f") + " --action write")
                    if args[values_or_vals].get('sync_id_api'):
                        args[values_or_vals]['id'] = request.env[model].search([('sync_id_api', '=', args[values_or_vals]['sync_id_api']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                        open(log_file, 'a').write("\n"+datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f") + " --done search model.id")
                    
                        record = request.env[model].browse(args[values_or_vals]['id'])
                        open(log_file, 'a').write("\n"+datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f") + " --done browse record")
                        if record:
                    
                            # autocall write method in record
                            getattr(record, operation)(**args)
                            open(log_file, 'a').write("\n"+datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f") + " --done update record")
                            records += record

                            result = records.read(load=False)
                            import datetime
                            if result:
                                for rec in result:
                                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                            else:
                                rec = True    



                            open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK SINI 0 ")
                
                            data.update({'status': 'success', 'data': rec})




                        if not record:
                            data.update({'status': 'error', 'message': "Record tidak ditemukan"})
                            json_data = json(data)
                            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

            # kenapa harus taruh result True disini ??
            result = True
            open('/opt/odoo16/logs/jancoks.log', 'a+').write('\n' + str(request.env.user.login) + "  sini 04")
        
            # if operation not write or unlink
            if operation not in ['write', 'unlink']:
                open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK SINI 1 ")
                result = records.read(load=False)
                open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK CREATE 3 : " + str(records))
                open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK CREATE 4 : " + str(result))
                import datetime
                if result:
                    for rec in result:
                        open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK SINI 1  looping")
                    
                        rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                        rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                else:
                    rec = True
                        

                if model == 'res.partner':
                    list_create = []
                    value_create = {}
                    value_create["id"] = result[0]["id"]
                    list_create.append(value_create)
                    result_create = list_create
                    import datetime
                    for rec in result_create:
                        rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                        rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}

                    data.update({'status': 'success', 'data': rec})


                open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK SINI 2 ")
                
                data.update({'status': 'success', 'data': rec})

            # update data result
            open('/opt/odoo16/logs/dump.log','a+').write('\n\n'+ "MASUK SINI 3 ")
                
            data.update({'status': 'success', 'data': rec})

            ## if have conflict_ids
            #if conflict_ids:
            #    data.update({'message': 'Some of the id are already created'})
            #    # data.update({'data': '(%s)' % (json(conflict_ids))})
            #    data.update({'data': conflict_ids})

        # show error exception
        except:
            data.update({'status': 'error', 'message': format_exc()})

        json_data = json(data)
        # log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message = "\n\ntimelog: " + "\n\nresponse: " + json_data
        message += "\n\n================= end ==================="
        open(log_file, 'a').write(message)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])


    @http.route('/internal_api_unlink/unit/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_run_unlink_unittes(self, model, **args):
        data = {}
        origin_args = args
        args = parse(args)
        self = request.env[model]
        # query3 = """ {query} """.format(query=args['query'])
        cek1 = str(args['company_name'])
        cek2 = str(args['user_id'])
        query_update = """
        update res_users set company_id = (select(id) from res_company where name = '{company_name}') where login = '{user_id}'
        """.format(company_name=cek1, user_id = cek2)
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "query update unit " + str(query_update))
        self.env.cr.execute(query_update)
        if args['ids']:
            # try:
            try:
                model_string = str(model)
                object_model = model_string.replace('.',"_")
                id_record = args['ids']
                query_delete = """
                delete from {object_model} where id = {id_record}
                """.format(object_model=object_model, id_record=id_record)
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "query delete unit " + str(query_delete))
                self.env.cr.execute(query_delete)
                data.update({'status': 'success', 'message': "Function Executed"})
            except:
                data.update({'status': 'error', 'message': format_exc()})


        else:
            data.update({'status': 'error', 'message': "Data Record must be sent!!"})

        json_data = json(data)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

    @http.route('/internal_api_unlink/main/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_run_unlink_maintes(self, model, **args):
        data = {}
        origin_args = args
        args = parse(args)
        self = request.env[model]
        # query3 = """ {query} """.format(query=args['query'])
        cek1 = str(args['company_name'])
        cek2 = str(args['user_id'])
        query_update = """
        update res_users set company_id = (select(id) from res_company where name = '{company_name}') where login = '{user_id}'
        """.format(company_name=cek1, user_id = cek2)
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "query update unit " + str(query_update))
        self.env.cr.execute(query_update)
        if args['ids']:
            # try:
            try:
                model_string = str(model)
                object_model = model_string.replace('.',"_")
                id_record = args['ids']
                query_delete = """
                delete from {object_model} where id = {id_record}
                """.format(object_model=object_model, id_record=id_record)
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "query delete unit " + str(query_delete))
                self.env.cr.execute(query_delete)
                data.update({'status': 'success', 'message': "Function Executed"})
            except:
                data.update({'status': 'error', 'message': format_exc()})


        else:
            data.update({'status': 'error', 'message': "Data Record must be sent!!"})

        json_data = json(data)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])



    # Define API Operation
    # Consol to Unit Integration data
    @http.route('/internal_api/unit/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_unit_method(self, operation, model, **args):
        #open('/opt/odoo16/logs/jancoks.log', 'a+').write('\n' + str(request.env.user.login))
        open('/opt/odoo16/logs/dump.log', 'a+').write('\n' + "masuk sini 1 : " + str(args))

        data = {}
        origin_args = args
        args = parse(args)


        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/unit/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        # if os.path.exists(log_file):
        #     if os.path.getsize(log_file) > 1000000:
        #         time_name_ren = '_' + datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S")
        #         log_file_ren = log_dir + log_name + time_name_ren + '.log'
        #         os.rename(log_file, log_file_ren)
        open(log_file, 'a').write(message)

        # for args in argss:
        # args = eval(args)

        self = request.env[model]
        # if args.get('context'):
        #     self = self.with_context(**args['context'])
        #     del args['context']

        try:
            if operation == 'search' and args.get('sql_query'):
                kwargs = dict(args)
                default = dict(args=[], offset=0, limit=None, order=None, count=False, access_rights_uid=None)
                args, offset, limit, order, count, access_rights_uid = [kwargs.get(variable, default.get(variable)) for variable in ['args', 'offset', 'limit', 'order', 'count', 'access_rights_uid']]
                self.sudo(access_rights_uid or self._uid).check_access_rights('read')
                query = self._where_calc(args)
                self._apply_ir_rules(query, 'read')
                order_by = self._generate_order_by(order, query)
                from_clause, where_clause, where_clause_params = query.get_sql()
                where_str = where_clause and (" WHERE %s" % where_clause) or ''
                #if count request
                if count:
                    query_str = 'SELECT count(1) FROM ' + from_clause + where_str
                    self._cr.execute(query_str, where_clause_params)
                    res = self._cr.fetchone()
                    return res[0]

                limit_str = limit and ' limit %d' % limit or ''
                offset_str = offset and ' offset %d' % offset or ''
                query_str = 'SELECT "%s" FROM ' % self._table + from_clause + where_str + order_by + limit_str + offset_str
                self._cr.execute(query_str, where_clause_params)
                return request.make_response(json({'status': 'success', 'data': self._cr.dictfetchall() }), [('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

            # browse all record model
            records = request.env[model].browse()
            # filter record by ids parameter
            if 'ids' in args:
                records = records.browse(args['ids'])
                del args['ids']

            # define unit ids
            unit_ids = []
            conflict_ids = []
            values_or_vals = 'vals'
            relational_fields = {}

            # if create operation
            if operation == 'create':
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                for value in args['values']:
                    self.env.cr.execute("SELECT sync_consol_id_unit FROM {model} WHERE sync_type='{sync_type}' AND sync_consol_id_unit = '{sync_id}'".format(model=model.replace(".", "_"), sync_type=value['sync_type'], sync_id=value['sync_consol_id_unit']))
                    unit_ids += [object[0] for object in self.env.cr.fetchall()]
                    
            # if operation create or write
            if operation in ['create', 'write','unlink']:
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                # by pass parameter "value"
                if args.get('value'):
                    raise Exception('Unrecognized parameter "value"')
                values_or_vals = 'values' if signature(
                    getattr(request.env[model], operation)).parameters.get('values', False) else 'vals'
                # stored data relation fields
                relational_fields = {key: value.comodel_name for key, value in request.env[model]._fields.items() if type(value) in [fields.Many2one, fields.One2many]}

            for args in [args] if operation not in ['create', 'write'] else [{values_or_vals: value} for value in (args.get('vals', []) + args.get('values', []))]:
                ####Chaelvin tess#####
                if args[values_or_vals]['company_name'] and args[values_or_vals]['user_id_cek']:
                    cek1 = str(args[values_or_vals]['company_name'])
                    cek2 = str(args[values_or_vals]['user_id_cek'])
                    query_update = """
                    update res_users set company_id = (select(id) from res_company where name = '{company_name}') where login = '{user_id}'
                    """.format(company_name=cek1, user_id = cek2)
                    #open('/opt/odoo16/logs/cn_debug.log', 'a+').write('\n' + "sini 1" + str(query_update))
                    self.env.cr.execute(query_update)
                    user_before_company = self.env.company.name
                    if user_before_company != cek1:
                        id_company = self.env['res.company'].search([('name','=',cek1)])
                        self.env.company = id_company
                if operation =='write':
                    if args[values_or_vals].get('sync_consol_id_unit'):
                        check_record = request.env[model].search([('sync_consol_id_unit', '=', args[values_or_vals]['sync_consol_id_unit']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                        if not check_record:
                            operation = 'create'
                            args[values_or_vals]['trigger_create'] = True
                elif operation =='create':
                    if args[values_or_vals].get('sync_consol_id_unit'):
                        check_record = request.env[model].search([('sync_consol_id_unit', '=', args[values_or_vals]['sync_consol_id_unit']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                        if check_record:
                            operation ='write'
                            args[values_or_vals]['trigger_write'] = False
                elif operation =='unlink':
                    if args[values_or_vals].get('sync_consol_id_unit'):
                        check_record = request.env[model].search([('sync_consol_id_unit', '=', args[values_or_vals]['sync_consol_id_unit']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                        if check_record:
                            operation = 'unlink'
                            args[values_or_vals]['trigger_create'] = True
                
                ####Conflict di komen####
                # if operation == 'create':
                #     # define conflict_ids
                #     if args[values_or_vals]['sync_consol_id_unit'] in unit_ids:
                #         conflict_ids += [args[values_or_vals]['sync_consol_id_unit']]
                #         continue


                # if create/write operation
                if operation in ['create', 'write', 'unlink']:
                    import datetime
                    # reformat args values, convert relation sync_id_api to odoo object id
                    # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + 'sebelum 2 ' + str(args[values_or_vals]))
                    args[values_or_vals] = {key: request.env[relational_fields[key]].search([('id', '=', value)], limit=1, order='id asc').id if relational_fields.get(key) and type(value) in [str] and key in ['user_id','user_type_id', 'bank_name','position_id','second_position_id','approval_id', 'category_id'] else value for key, value in args[values_or_vals].items()}
                    args[values_or_vals] = {key: request.env[relational_fields[key]].search([('sync_consol_id_unit', '=', value), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id if relational_fields.get(key) and type(value) in [str] and key not in ['user_type_id', 'bank_name','position_id','second_position_id','approval_id', 'payment_method_id', 'category_id'] else value for key, value in args[values_or_vals].items()}
                    # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + 'sesudah 2 ' + str(args[values_or_vals]))
                # if operation not write
                if not operation == 'write':
                    result = False

                    # if operation create
                    if operation == 'create':
                        # create log message
                        message = "\n\nExecute API Create"
                        open(log_file, 'a').write(message)
                        # create new record data
                        result = request.env[model].create(**args)
                        # open(log_file, 'a').write(json(result))

                        # add latest id to temp variable
                        unit_ids.append(result.sync_consol_id_unit)
                    elif operation == 'unlink':
                        if args[values_or_vals].get('sync_consol_id_unit'):
                            args[values_or_vals]['id'] = request.env[model].search([('sync_consol_id_unit', '=', args[values_or_vals]['sync_consol_id_unit']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                            cek_record = records.browse(args[values_or_vals]['id'])
                            cek_record.unlink()

                    # if operation not create & write
                    else:
                        # autocall operation method in records
                        result = getattr(records, operation)(**args)

                    # if create operation, add new record data to result
                    if operation != 'unlink':
                        records += result

                # if write operation
                else:
                    if args[values_or_vals].get('sync_consol_id_unit'):
                        args[values_or_vals]['id'] = request.env[model].search([('sync_consol_id_unit', '=', args[values_or_vals]['sync_consol_id_unit']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                        
                        ####Chaelvin####
                        get_id = args[values_or_vals]['id']
                        
                        if model == 'bank.information' and args[values_or_vals]['id']:
                            search_record = request.env[model].search([('id', '=', args[values_or_vals]['id'])],limit=1)
                            if search_record:
                                search_record.bank_name.trigger_write = False
                                search_record.bank_name.trigger_create = True
                    
                    record = request.env[model].browse(args[values_or_vals]['id'])
                    # autocall write method in record
                    getattr(record, operation)(**args)
                    records += record

            # kenapa harus taruh result True disini ??
            result = True
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + 'ID DI BWH TRUE' + str(tes123))

            # if operation not write or unlink
            if operation not in ['write', 'unlink']:
                result = records.read(load=False)
                import datetime
                for rec in result:
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                
                if model == 'res.partner':
                    list_create = []
                    value_create = {}
                    value_create["id"] = result[0]["id"]
                    list_create.append(value_create)
                    result_create = list_create
                    import datetime
                    for rec in result_create:
                        rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                        rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}

                    data.update({'status': 'success', 'data': rec})

                data.update({'status': 'success', 'data': rec})  
                for r in result:
                    for image in ['image_small', 'image_medium', 'image', 'sign']:
                        if image in r:
                            r[image] = False

            ####Chaelvin####
            elif operation in ['write']:
                list_write = []
                value_write = {}
                value_write["id"] = get_id
                list_write.append(value_write)
                result = list_write
                import datetime
                for rec in result:
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}

                data.update({'status': 'success', 'data': rec})
                

            # update data result
            data.update({'status': 'success', 'data': rec})

            # if have conflict_ids
            # if conflict_ids:
            #     data.update({'message': 'Some of the id are already created'})
            #     # data.update({'data': '(%s)' % (json(conflict_ids))})
            #     data.update({'data_conflict': conflict_ids})

        # show error exception
        except:
            data.update({'status': 'error', 'message': format_exc()})

        json_data = json(data)
        # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
        message = "\n\ntimelog: " + "\n\nresponse: " + json_data
        message += "\n\n================= end ==================="

        open(log_file, 'a').write(message)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])



    # Define API Operation
    # Consol to Unit Integration data
    @http.route('/internal_api/main/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_main_method(self, operation, model, **args):
        #open('/opt/odoo16/logs/jancoks.log', 'a+').write('\n' + str(request.env.user.login))
        data = {}
        origin_args = args
        args = parse(args)

        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/main/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        # if os.path.exists(log_file):
        #     if os.path.getsize(log_file) > 1000000:
        #         time_name_ren = '_' + datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S")
        #         log_file_ren = log_dir + log_name + time_name_ren + '.log'
        #         os.rename(log_file, log_file_ren)
        open(log_file, 'a').write(message)

        # for args in argss:
        # args = eval(args)

        self = request.env[model]
        # if args.get('context'):
        #     self = self.with_context(**args['context'])
        #     del args['context']

        try:
            if operation == 'search' and args.get('sql_query'):
                kwargs = dict(args)
                default = dict(args=[], offset=0, limit=None, order=None, count=False, access_rights_uid=None)
                args, offset, limit, order, count, access_rights_uid = [kwargs.get(variable, default.get(variable)) for variable in ['args', 'offset', 'limit', 'order', 'count', 'access_rights_uid']]
                self.sudo(access_rights_uid or self._uid).check_access_rights('read')
                query = self._where_calc(args)
                self._apply_ir_rules(query, 'read')
                order_by = self._generate_order_by(order, query)
                from_clause, where_clause, where_clause_params = query.get_sql()
                where_str = where_clause and (" WHERE %s" % where_clause) or ''
                #if count request
                if count:
                    query_str = 'SELECT count(1) FROM ' + from_clause + where_str
                    self._cr.execute(query_str, where_clause_params)
                    res = self._cr.fetchone()
                    return res[0]

                limit_str = limit and ' limit %d' % limit or ''
                offset_str = offset and ' offset %d' % offset or ''
                query_str = 'SELECT "%s" FROM ' % self._table + from_clause + where_str + order_by + limit_str + offset_str
                self._cr.execute(query_str, where_clause_params)
                return request.make_response(json({'status': 'success', 'data': self._cr.dictfetchall() }), [('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

            # browse all record model
            records = request.env[model].browse()
            # filter record by ids parameter
            if 'ids' in args:
                records = records.browse(args['ids'])
                del args['ids']

            # define unit ids
            main_ids = []
            conflict_ids = []
            values_or_vals = 'vals'
            relational_fields = {}

            # if create operation
            if operation == 'create':
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                for value in args['values']:
                    self.env.cr.execute("SELECT sync_consol_id_main FROM {model} WHERE sync_type='{sync_type}' AND sync_consol_id_main = '{sync_id}'".format(model=model.replace(".", "_"), sync_type=value['sync_type'], sync_id=value['sync_consol_id_main']))
                    main_ids += [object[0] for object in self.env.cr.fetchall()]
                    
            # if operation create or write
            if operation in ['create', 'write','unlink']:
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                # by pass parameter "value"
                if args.get('value'):
                    raise Exception('Unrecognized parameter "value"')
                values_or_vals = 'values' if signature(
                    getattr(request.env[model], operation)).parameters.get('values', False) else 'vals'
                # stored data relation fields
                relational_fields = {key: value.comodel_name for key, value in request.env[model]._fields.items() if type(value) in [fields.Many2one, fields.One2many]}


            for args in [args] if operation not in ['create', 'write','unlink'] else [{values_or_vals: value} for value in (args.get('vals', []) + args.get('values', []))]:
                ####Chaelvin tess#####
                if args[values_or_vals]['company_name'] and args[values_or_vals]['user_id_cek']:
                    cek1 = str(args[values_or_vals]['company_name'])
                    cek2 = str(args[values_or_vals]['user_id_cek'])
                    query_update = """
                    update res_users set company_id = (select(id) from res_company where name = '{company_name}') where login = '{user_id}'
                    """.format(company_name=cek1, user_id = cek2)
                    open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "query update SINI INTERNAL API UNIT2 " + str(query_update))
                    self.env.cr.execute(query_update)
                if operation =='write':
                    if args[values_or_vals].get('sync_consol_id_main'):
                        check_record = request.env[model].search([('sync_consol_id_main', '=', args[values_or_vals]['sync_consol_id_main']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                        if not check_record:
                            operation = 'create'
                            args[values_or_vals]['trigger_create'] = True
                elif operation =='create':
                    if args[values_or_vals].get('sync_consol_id_main'):
                        check_record = request.env[model].search([('sync_consol_id_main', '=', args[values_or_vals]['sync_consol_id_main']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                        if check_record:
                            operation ='write'
                            args[values_or_vals]['trigger_write'] = False
                elif operation =='unlink':
                    if args[values_or_vals].get('sync_consol_id_main'):
                        check_record = request.env[model].search([('sync_consol_id_main', '=', args[values_or_vals]['sync_consol_id_main']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                        if check_record:
                            operation = 'unlink'
                            args[values_or_vals]['trigger_create'] = True
                
                ####Conflict di komen####
                # if operation == 'create':
                #     # define conflict_ids
                #     if args[values_or_vals]['sync_consol_id_main'] in main_ids:
                #         conflict_ids += [args[values_or_vals]['sync_consol_id_main']]
                #         continue


                # if create/write operation
                if operation in ['create', 'write', 'unlink']:
                    import datetime
                    # reformat args values, convert relation sync_id_api to odoo object id
                    args[values_or_vals] = {key: request.env[relational_fields[key]].search([('sync_consol_id_main', '=', value)], limit=1, order='id asc').id if relational_fields.get(key) and type(value) in [str] and key in ['user_id','user_type_id', 'bank_name','position_id','second_position_id','approval_id', 'category_id'] else value for key, value in args[values_or_vals].items()}
                    args[values_or_vals] = {key: request.env[relational_fields[key]].search([('sync_consol_id_main', '=', value), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id if relational_fields.get(key) and type(value) in [str] and key not in ['user_type_id', 'bank_name','position_id','second_position_id','approval_id', 'payment_method_id', 'category_id'] else value for key, value in args[values_or_vals].items()}
                    # args[values_or_vals] = {key: str(datetime.datetime.strftime(value, "%d-%m-%Y %I:%M:%S")) if type(value) in [datetime]  else value for key, value in args[values_or_vals].items()}
                    
                    
                # if operation not write
                if not operation == 'write':
                    result = False

                    # if operation create
                    if operation == 'create':
                        # create log message
                        message = "\n\nExecute API Create"
                        open(log_file, 'a').write(message)
                        # create new record data
                        result = request.env[model].create(**args)
                        # open(log_file, 'a').write(json(result))
                        check = result.read(load=False)
                        # add latest id to temp variable
                        main_ids.append(result.sync_consol_id_unit)
                    elif operation == 'unlink':
                        if args[values_or_vals].get('sync_consol_id_main'):
                            args[values_or_vals]['id'] = request.env[model].search([('sync_consol_id_main', '=', args[values_or_vals]['sync_consol_id_main']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                            cek_record = records.browse(args[values_or_vals]['id'])
                            cek_record.unlink()
                            
                        
                    # if operation not create & write
                    else:
                        # autocall operation method in records
                        result = getattr(records, operation)(**args)

                    # if create operation, add new record data to result
                    if operation != 'unlink':
                        records += result

                # if write operation
                else:
                    if args[values_or_vals].get('sync_consol_id_main'):
                        
                        args[values_or_vals]['id'] = request.env[model].search([('sync_consol_id_main', '=', args[values_or_vals]['sync_consol_id_main']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                        
                        get_id = args[values_or_vals]['id']
                        
                        if model == 'bank.information' and args[values_or_vals]['id']:
                            
                            search_record = request.env[model].search([('id', '=', args[values_or_vals]['id'])],limit=1)
                            if search_record:
                                search_record.bank_name.trigger_write = False
                                search_record.bank_name.trigger_create = True
                    
                    record = request.env[model].browse(args[values_or_vals]['id'])
                    # autocall write method in record
                    getattr(record, operation)(**args)
                    
                    records += record

            # kenapa harus taruh result True disini ??
            result = True
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + 'ID DI BWH TRUE' + str(tes123))
            # if operation not write or unlink
            if operation not in ['write', 'unlink']:
                result = records.read(load=False)
                import datetime
                for rec in result:
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                    

                if model == 'res.partner':
                    list_create = []
                    value_create = {}
                    value_create["id"] = result[0]["id"]
                    list_create.append(value_create)
                    result_create = list_create
                    import datetime
                    for rec in result_create:
                        rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                        rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}

                    data.update({'status': 'success', 'data': rec})

                if model == 'res.users':
                    list_create = []
                    value_create = {}
                    value_create["id"] = result[0]["id"]
                    list_create.append(value_create)
                    result_create = list_create
                    import datetime
                    for rec in result_create:
                        rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                        rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                    
                    data.update({'status': 'success', 'data': rec})
                
                data.update({'status': 'success', 'data': rec})      
                for r in result:
                    for image in ['image_small', 'image_medium', 'image', 'sign']:
                        if image in r:
                            r[image] = False

            ####Chaelvin####
            elif operation in ['write']:
                list_write = []
                value_write = {}
                value_write["id"] = get_id
                list_write.append(value_write)
                result = list_write
                import datetime
                for rec in result:
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                    


                

                data.update({'status': 'success', 'data': rec})

            # update data result
            data.update({'status': 'success', 'data': rec})
                        
            # if have conflict_ids
            # if conflict_ids:
            #     data.update({'message': 'Some of the id are already created'})
            #     # data.update({'data': '(%s)' % (json(conflict_ids))})
            #     data.update({'data_conflict': conflict_ids})

        # show error exception
        except:
            data.update({'status': 'error', 'message': format_exc()})
        json_data = json(data)
        # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
        message = "\n\ntimelog: " + "\n\nresponse: " + json_data
        message += "\n\n================= end ==================="

        open(log_file, 'a').write(message)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])


    # Define API Operation
    # Consol to Unit Integration data Group User
    ############ Chaelvin Edit ##############
    @http.route('/internal_api_group/main/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_main_method_group(self, operation, model, **args):
        data_return = {}
        origin_args = args
        args = parse(args)

        

        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/main/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'
        
        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        self = request.env['res.users']


        open(log_file, 'a').write(message)
        query = """
                SELECT sync_consol_id_main FROM res_users WHERE sync_type='{sync_type}' AND sync_consol_id_main = '{sync_id}'
                """.format(sync_type=args['values'][0]['sync_type'], sync_id=args['values'][0]['uid'])
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK sini query 1")
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(query))
                    
        self.env.cr.execute(query)
        data = self.env.cr.fetchall()
        if data:
            search_user = request.env['res.users'].search([('sync_consol_id_main','=', args['values'][0]['uid'])], limit=1)
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "Search User")        
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(search_user))
        
            check = []
            for value in args['values']:
                
                gid = value['gid']
                check.append(str(gid))
                
                search_group = request.env['res.groups'].search([('sync_consol_id_main','=', gid)], limit=1)
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "Search group")        
                open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(search_group))
        
                if search_group:
                    query2 = """
                            SELECT gid FROM res_groups_users_rel WHERE gid='{gid}' AND uid = '{uid}'
                            """.format(gid=search_group.id, uid=search_user.id)
                    open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK sini query 2")
                    open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(query2))
                        

                    self.env.cr.execute(query2)
                    data2 = self.env.cr.fetchall()
                    if data2:
                        print ("data2")
                    else:
                        query3 = """
                                insert into res_groups_users_rel (gid,uid) values('{gid}','{uid}');
                                """.format(gid=search_group.id, uid=search_user.id)

                        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK sini query 3")
                        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(query3))
                        self.env.cr.execute(query3)
            
            search_group_hide = request.env['res.groups'].search([('sync_consol_id_main','!=', False)])
            for rec in search_group_hide:
                check_tes = str(int(rec.sync_consol_id_main))
                
                if check_tes in check:
                    print ("check tes 1")
                else:
                    query4 = """
                               delete from res_groups_users_rel where uid = '{uid}' and gid ='{gid}'
                                """.format(gid=rec.id, uid=search_user.id)
                    open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK sini query 4")
                    open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(query4))

                    self.env.cr.execute(query4)


            result = True
            data_return.update({'status': 'success', 'data': result})
            json_data = json(data_return)
            # json_data = json(data)
            # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
            message = "\n\ntimelog: " + "\n\nresponse: " + json_data
            message += "\n\n================= end ==================="

            open(log_file, 'a').write(message)
            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

        else:
            print ("tidak ada data")


    # Define API Operation
    # Consol to Unit Integration data Group User
    ############ Chaelvin Edit ##############
    @http.route('/internal_api_purchase/unit/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_main_method_po_tax(self, operation, model, **args):
        data_return = {}
        origin_args = args
        args = parse(args)

        

        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/main/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'
        
        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        self = request.env['purchase.order.line']


        open(log_file, 'a').write(message)
        query = """
                SELECT sync_consol_id_unit FROM purchase_order_line WHERE sync_type='{sync_type}' AND sync_consol_id_unit = '{sync_id}'
                """.format(sync_type=args['values'][0]['sync_type'], sync_id=args['values'][0]['purchase_order_line_id'])
        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK sini query 1")
        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(query))
                    
        self.env.cr.execute(query)
        data = self.env.cr.fetchall()
        if data:
            search_user = request.env['purchase.order.line'].search([('sync_consol_id_unit','=', args['values'][0]['purchase_order_line_id']),('sync_type','=',args['values'][0]['sync_type'])], limit=1)
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "Search User")        
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(search_user))
        
            check = []
            for value in args['values']:
                
                account_tax_id = value['account_tax_id']
                check.append(str(account_tax_id))
                
                search_group = request.env['account.tax'].search([('sync_consol_id_unit','=', account_tax_id), ('sync_type','=', args['values'][0]['sync_type'])], limit=1)
                # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "Search group")        
                # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(search_group))
        
                if search_group:
                    query2 = """
                            SELECT account_tax_id FROM account_tax_purchase_order_line_rel WHERE account_tax_id='{account_tax_id}' AND purchase_order_line_id = '{purchase_order_line_id}'
                            """.format(account_tax_id=search_group.id, purchase_order_line_id=search_user.id)
                    # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK sini query 2")
                    # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(query2))
                        

                    self.env.cr.execute(query2)
                    data2 = self.env.cr.fetchall()
                    if data2:
                        print ("data2")
                    else:
                        query3 = """
                                insert into account_tax_purchase_order_line_rel (account_tax_id,purchase_order_line_id) values('{account_tax_id}','{purchase_order_line_id}');
                                """.format(account_tax_id=search_group.id, purchase_order_line_id=search_user.id)

                        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK sini query 3")
                        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(query3))
                        self.env.cr.execute(query3)
            
            # search_group_hide = request.env['res.groups'].search([('sync_consol_id_main','!=', False)])
            # for rec in search_group_hide:
            #     check_tes = str(int(rec.sync_consol_id_main))
                
            #     if check_tes in check:
            #         print "check tes 1"
            #     else:
            #         query4 = """
            #                    delete from res_groups_users_rel where uid = '{uid}' and gid ='{gid}'
            #                     """.format(gid=rec.id, uid=search_user.id)
            #         open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK sini query 4")
            #         open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(query4))

            #         self.env.cr.execute(query4)


            result = True
            data_return.update({'status': 'success', 'data': result})
            json_data = json(data_return)
            # json_data = json(data)
            # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
            message = "\n\ntimelog: " + "\n\nresponse: " + json_data
            message += "\n\n================= end ==================="

            open(log_file, 'a').write(message)
            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

        else:
            print ("tidak ada data")


    # Define API Operation
    # Consol to Unit Integration data Group User
    ############ Chaelvin Edit ##############
    @http.route('/delete_purchase_tax_internal_api/unit/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def delete_purchase_tax_internal_api_unit(self, operation, model, **args):
        data_return = {}
        origin_args = args
        args = parse(args)

        

        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/main/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'
        
        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        self = request.env['purchase.order.line']


        open(log_file, 'a').write(message)
        query = """
                SELECT sync_consol_id_unit FROM purchase_order_line WHERE sync_type='{sync_type}' AND sync_consol_id_unit = '{sync_id}'
                """.format(sync_type=args['values'][0]['sync_type'], sync_id=args['values'][0]['purchase_order_line_id'])
                    
        self.env.cr.execute(query)
        data = self.env.cr.fetchall()
        if data:
            search_user = request.env['purchase.order.line'].search([('sync_consol_id_unit','=', args['values'][0]['purchase_order_line_id']),('sync_type','=',args['values'][0]['sync_type'])], limit=1)
            if search_user:
                query_delete = """
                        delete from account_tax_purchase_order_line_rel where purchase_order_line_id = '{purchase_order_line_id}'
                        """.format(purchase_order_line_id=search_user.id)

                self.env.cr.execute(query_delete)


            
            



            result = True
            data_return.update({'status': 'success', 'data': result})
            json_data = json(data_return)
            # json_data = json(data)
            # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
            message = "\n\ntimelog: " + "\n\nresponse: " + json_data
            message += "\n\n================= end ==================="

            open(log_file, 'a').write(message)
            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

        else:
            print ("tidak ada data")




    # Define API Operation
    # Consol to Main Integration data Group User
    ############ Chaelvin Edit ##############
    @http.route('/internal_api_purchase/main/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_unit_method_po_tax(self, operation, model, **args):
        data_return = {}
        origin_args = args
        args = parse(args)

        

        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/unit/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'
        
        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        self = request.env['purchase.order.line']


        open(log_file, 'a').write(message)
        query = """
                SELECT sync_consol_id_main FROM purchase_order_line WHERE sync_type='{sync_type}' AND sync_consol_id_main = '{sync_id}'
                """.format(sync_type=args['values'][0]['sync_type'], sync_id=args['values'][0]['purchase_order_line_id'])
        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK sini query 1")
        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(query))
                    
        self.env.cr.execute(query)
        data = self.env.cr.fetchall()
        if data:
            search_user = request.env['purchase.order.line'].search([('sync_consol_id_main','=', args['values'][0]['purchase_order_line_id']),('sync_type','=',args['values'][0]['sync_type'])], limit=1)
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "Search User")        
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(search_user))
        
            check = []
            for value in args['values']:
                
                account_tax_id = value['account_tax_id']
                check.append(str(account_tax_id))
                
                search_group = request.env['account.tax'].search([('sync_consol_id_main','=', account_tax_id), ('sync_type','=', args['values'][0]['sync_type'])], limit=1)
                # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "Search group")        
                # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(search_group))
        
                if search_group:
                    query2 = """
                            SELECT account_tax_id FROM account_tax_purchase_order_line_rel WHERE account_tax_id='{account_tax_id}' AND purchase_order_line_id = '{purchase_order_line_id}'
                            """.format(account_tax_id=search_group.id, purchase_order_line_id=search_user.id)
                    # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK sini query 2")
                    # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(query2))
                        

                    self.env.cr.execute(query2)
                    data2 = self.env.cr.fetchall()
                    if data2:
                        print ("data2")
                    else:
                        query3 = """
                                insert into account_tax_purchase_order_line_rel (account_tax_id,purchase_order_line_id) values('{account_tax_id}','{purchase_order_line_id}');
                                """.format(account_tax_id=search_group.id, purchase_order_line_id=search_user.id)

                        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK sini query 3")
                        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(query3))
                        self.env.cr.execute(query3)
            
            # search_group_hide = request.env['res.groups'].search([('sync_consol_id_main','!=', False)])
            # for rec in search_group_hide:
            #     check_tes = str(int(rec.sync_consol_id_main))
                
            #     if check_tes in check:
            #         print "check tes 1"
            #     else:
            #         query4 = """
            #                    delete from res_groups_users_rel where uid = '{uid}' and gid ='{gid}'
            #                     """.format(gid=rec.id, uid=search_user.id)
            #         open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "MASUK sini query 4")
            #         open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(query4))

            #         self.env.cr.execute(query4)


            result = True
            data_return.update({'status': 'success', 'data': result})
            json_data = json(data_return)
            # json_data = json(data)
            # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
            message = "\n\ntimelog: " + "\n\nresponse: " + json_data
            message += "\n\n================= end ==================="

            open(log_file, 'a').write(message)
            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

        else:
            print ("tidak ada data")




    # Define API Operation
    # Consol to Unit Integration data Group User
    ############ Chaelvin Edit ##############
    @http.route('/delete_purchase_tax_internal_api/main/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def delete_purchase_tax_internal_api_main(self, operation, model, **args):
        data_return = {}
        origin_args = args
        args = parse(args)

        

        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/main/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'
        
        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        self = request.env['purchase.order.line']


        open(log_file, 'a').write(message)
        query = """
                SELECT sync_consol_id_main FROM purchase_order_line WHERE sync_type='{sync_type}' AND sync_consol_id_main = '{sync_id}'
                """.format(sync_type=args['values'][0]['sync_type'], sync_id=args['values'][0]['purchase_order_line_id'])
                    
        self.env.cr.execute(query)
        data = self.env.cr.fetchall()
        if data:
            search_user = request.env['purchase.order.line'].search([('sync_consol_id_main','=', args['values'][0]['purchase_order_line_id']),('sync_type','=',args['values'][0]['sync_type'])], limit=1)
            if search_user:
                query_delete = """
                        delete from account_tax_purchase_order_line_rel where purchase_order_line_id = '{purchase_order_line_id}'
                        """.format(purchase_order_line_id=search_user.id)

                self.env.cr.execute(query_delete)


            
            



            result = True
            data_return.update({'status': 'success', 'data': result})
            json_data = json(data_return)
            # json_data = json(data)
            # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
            message = "\n\ntimelog: " + "\n\nresponse: " + json_data
            message += "\n\n================= end ==================="

            open(log_file, 'a').write(message)
            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

        else:
            print ("tidak ada data")


    # Define API Operation
    # Consol to Unit Integration data Group User
    ############ Chaelvin Edit ##############
    @http.route('/internal_api_many2many/main/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_main_method_many2many(self, operation, model, **args):
        data_return = {}
        origin_args = args
        args = parse(args)

        

        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/main/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'
        
        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        self = request.env['purchase.type']


        open(log_file, 'a').write(message)
        
        if args['values'][0]['sync_type'] != False:

            query = """
                    SELECT sync_consol_id_main FROM purchase_type WHERE sync_type='{sync_type}' AND sync_consol_id_main = '{sync_id}'
                    """.format(sync_type=args['values'][0]['sync_type'], sync_id=args['values'][0]['purchase_type_id'])

            self.env.cr.execute(query)
            data = self.env.cr.fetchall()
            if data:
                search_purchase_type = request.env['purchase.type'].search([('sync_consol_id_main','=', args['values'][0]['purchase_type_id'])], limit=1)
                check = []
                for value in args['values']:
                    
                    purchase_approval_id = value['purchase_approval_id']
                    check.append(str(purchase_approval_id))
                    
                    search_purchase_approval = request.env['purchase.approval'].search([('sync_consol_id_main','=', purchase_approval_id)], limit=1)
                    if search_purchase_approval:
                        query2 = """
                                SELECT purchase_approval_id FROM purchase_approval_purchase_type_rel WHERE purchase_approval_id='{purchase_approval_id}' AND purchase_type_id = '{purchase_type_id}'
                                """.format(purchase_approval_id=search_purchase_approval.id, purchase_type_id=search_purchase_type.id)

                        self.env.cr.execute(query2)
                        data2 = self.env.cr.fetchall()
                        if data2:
                            print ("data2")
                        else:
                            query3 = """
                                    insert into purchase_approval_purchase_type_rel (purchase_approval_id,purchase_type_id) values('{purchase_approval_id}','{purchase_type_id}');
                                    """.format(purchase_approval_id=search_purchase_approval.id, purchase_type_id=search_purchase_type.id)

                            self.env.cr.execute(query3)
                
                search_purchase_approval_hide = request.env['purchase.approval'].search([('sync_consol_id_main','!=', False)])
                for rec in search_purchase_approval_hide:
                    check_tes = str(int(rec.sync_consol_id_main))
                    
                    if check_tes in check:
                        print ("check tes")
                    else:
                        
                        query4 = """
                                delete from purchase_approval_purchase_type_rel where purchase_type_id = '{purchase_type_id}' and purchase_approval_id ='{purchase_approval_id}'
                                    """.format(purchase_approval_id=rec.id, purchase_type_id=search_purchase_type.id)

                        self.env.cr.execute(query4)


                result = True
                data_return.update({'status': 'success', 'data': result})
                json_data = json(data_return)
                # json_data = json(data)
                # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
                message = "\n\ntimelog: " + "\n\nresponse: " + json_data
                message += "\n\n================= end ==================="

                open(log_file, 'a').write(message)
                return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])
                            

                        

            else:
                print ("tidak ada data")
                
        else:
            search_purchase_type = request.env['purchase.type'].search([('sync_consol_id_main','=', args['values'][0]['purchase_type_id'])], limit=1)
            if search_purchase_type:
                query_delete = """
                delete from purchase_approval_purchase_type_rel where purchase_type_id = '{purchase_type_id}'
                """.format(purchase_type_id=search_purchase_type.id)
                self.env.cr.execute(query_delete)
            data_return.update({'status': 'success', 'data': False})
            json_data = json(data_return)
            return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])
            
    @http.route('/internal_api/call_function/main/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_run_function_main(self, model, **args):
        data = {}
        origin_args = args
        args = parse(args)
        self = request.env[model]
        # query3 = """ {query} """.format(query=args['query'])
        cek1 = str(args['company_name'])
        cek2 = str(args['user_id'])
        query_update = """
        update res_users set company_id = (select(id) from res_company where name = '{company_name}') where login = '{user_id}'
        """.format(company_name=cek1, user_id = cek2)
        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "query update: " + str(query_update))
        # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "query args: " + str(args['ids']))
        self.env.cr.execute(query_update)
        if args['ids']:
            # # try:
            # record_ids = request.env[model].browse(args['ids'])
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "record_ids : " + str(record_ids))
                
            # for record in record_ids:
            #     open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "record : " + str(record.id))
            #     open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "args argument : " + str(args['arguments']))
        
            try:
                # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "args argument : " + str(args['arguments']))
                if model =='res.users':
                    # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "args FUnction : " + str(args['function']))
                    
                    if args['function'] == 'change_password':
                        self.change_password(user_id=args['ids'],new_passwd=args['arguments'])
                    if args['function'] == 'change_password_consol':
                        self.change_password_consol(user_id=args['ids'],new_passwd=args['arguments'])
                    if args['function'] == 'change_password_consol_main':
                        self.change_password_consol_main(user_id=args['ids'],new_passwd=args['arguments'])
                    else:
                        getattr(self, args['function'])(*args['arguments'])
                else:
                    search_record = request.env[model].search([('id','=', args['ids'])], limit=1)
                    search_record.trigger_write = False
                    getattr(search_record, args['function'])()

                data.update({'status': 'success', 'message': "Function Executed"})
            except:
                data.update({'status': 'error', 'message': format_exc()})

            # except:
            #     data.update({'status': 'error', 'message': "Model or Data not Found"})

        else:
            data.update({'status': 'error', 'message': "Data Record must be sent!!"})

        json_data = json(data)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])
    

    @http.route('/internal_api/call_function/unit/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_run_function_unit(self, model, **args):
        data = {}
        origin_args = args
        args = parse(args)
        self = request.env[model]
        # query3 = """ {query} """.format(query=args['query'])
        cek1 = str(args['company_name'])
        cek2 = str(args['user_id'])
        query_update = """
        update res_users set company_id = (select(id) from res_company where name = '{company_name}') where login = '{user_id}'
        """.format(company_name=cek1, user_id = cek2)
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "query update" + str(query_update))
        self.env.cr.execute(query_update)
        if args['ids']:
            open('/opt/odoo16/logs/dump.log', 'a+').write('\n' + "query search cek args ids : " + str(args['ids']))
                        
            try:

                if model =='res.users':
                    open('/opt/odoo16/logs/dump.log', 'a+').write('\n' + "query search cek model : " + str(model))
                    
                else:
                    search_record = request.env[model].search([('id','=', args['ids'])], limit=1)
                    open('/opt/odoo16/logs/dump.log', 'a+').write('\n' + "query search: " + str(search_record))
                    getattr(search_record, args['function'])()

                data.update({'status': 'success', 'message': "Function Executed"})
            except:
                data.update({'status': 'error', 'message': format_exc()})

            # except:
            #     data.update({'status': 'error', 'message': "Model or Data not Found"})

        else:
            data.update({'status': 'error', 'message': "Data Record must be sent!!"})

        json_data = json(data)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

    # @http.route('/internal_api/call_function/<model>', type='http', auth='user')
    # @route()
    # def api_consol_run_function(self, model, **args):
    #     data = {}
    #     origin_args = args
    #     args = parse(args)
    #     if args['ids']:
    #         # try:
    #         record_ids = request.env[model].browse(args['ids'])
    #         for record in record_ids:
    #             try:

    #                 if args['arguments']:
    #                     # open('/opt/odoo16/logs/api_function.log', 'a+').write('\n' + str(record))
    #                     open('/opt/odoo16/logs/api_function.log', 'a+').write('\n' + str(args))
    #                     getattr(record, args['function'])(*args['arguments'])
    #                 else:
    #                     getattr(record, args['function'])()

    #                 data.update({'status': 'success', 'message': "Function Executed"})
    #             except:
    #                 data.update({'status': 'error', 'message': format_exc()})

    #         # except:
    #         #     data.update({'status': 'error', 'message': "Model or Data not Found"})

    #     else:
    #         data.update({'status': 'error', 'message': "Data Record must be sent!!"})

    #     json_data = json(data)
    #     return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])


    # Define API Operation
    # Consol to Unit Integration data
    @http.route('/internal_api/main/attachment/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_main_attachment_method(self, operation, model, **args):
        data = {}
        origin_args = args
        args = parse(args)

        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/main/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        # if os.path.exists(log_file):
        #     if os.path.getsize(log_file) > 1000000:
        #         time_name_ren = '_' + datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S")
        #         log_file_ren = log_dir + log_name + time_name_ren + '.log'
        #         os.rename(log_file, log_file_ren)
        open(log_file, 'a').write(message)

        # for args in argss:
        # args = eval(args)

        self = request.env[model]
        cek1 = str(args['company_name'])
        cek2 = str(args['user_consol_main'])
        query_update = """
        update res_users set company_id = (select(id) from res_company where name = '{company_name}') where login = '{user_consol_main}'
        """.format(company_name=cek1, user_consol_main = cek2)
        self.env.cr.execute(query_update)
        # if args.get('context'):
        #     self = self.with_context(**args['context'])
        #     del args['context']

        try:
            if operation == 'search' and args.get('sql_query'):
                kwargs = dict(args)
                default = dict(args=[], offset=0, limit=None, order=None, count=False, access_rights_uid=None)
                args, offset, limit, order, count, access_rights_uid = [kwargs.get(variable, default.get(variable)) for variable in ['args', 'offset', 'limit', 'order', 'count', 'access_rights_uid']]
                self.sudo(access_rights_uid or self._uid).check_access_rights('read')
                query = self._where_calc(args)
                self._apply_ir_rules(query, 'read')
                order_by = self._generate_order_by(order, query)
                from_clause, where_clause, where_clause_params = query.get_sql()
                where_str = where_clause and (" WHERE %s" % where_clause) or ''
                #if count request
                if count:
                    query_str = 'SELECT count(1) FROM ' + from_clause + where_str
                    self._cr.execute(query_str, where_clause_params)
                    res = self._cr.fetchone()
                    return res[0]

                limit_str = limit and ' limit %d' % limit or ''
                offset_str = offset and ' offset %d' % offset or ''
                query_str = 'SELECT "%s" FROM ' % self._table + from_clause + where_str + order_by + limit_str + offset_str
                self._cr.execute(query_str, where_clause_params)
                return request.make_response(json({'status': 'success', 'data': self._cr.dictfetchall() }), [('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

            # browse all record model
            records = request.env[model].browse()
            # filter record by ids parameter
            if 'ids' in args:
                records = records.browse(args['ids'])
                del args['ids']

            # define unit ids
            main_ids = []
            conflict_ids = []
            values_or_vals = 'vals'
            relational_fields = {}

            

            # if create operation
            if operation == 'create':
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                # for value in args['values']:
                #     self.env.cr.execute("SELECT sync_consol_id_main FROM {model} WHERE sync_type='{sync_type}' AND sync_consol_id_main = '{sync_id}'".format(model=model.replace(".", "_"), sync_type=value['sync_type'], sync_id=value['sync_consol_id_main']))
                #     main_ids += [object[0] for object in self.env.cr.fetchall()]
                #     open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(main_ids))

            # if operation create or write
            if operation in ['create', 'write']:
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                # by pass parameter "value"
                if args.get('value'):
                    raise Exception('Unrecognized parameter "value"')
                values_or_vals = 'values' if signature(
                    getattr(request.env[model], operation)).parameters.get('values', False) else 'vals'
                # stored data relation fields
                relational_fields = {key: value.comodel_name for key, value in request.env[model]._fields.items() if type(value) in [fields.Many2one, fields.One2many]}

            


            for args in [args] if operation not in ['create', 'write'] else [{values_or_vals: value} for value in (args.get('vals', []) + args.get('values', []))]:
                # records = eval('request.env[model].%s(**args)' % (operation))
                
                ####Conflict di komen####
                # if operation == 'create':
                #     # define conflict_ids
                #     if args[values_or_vals]['sync_consol_id_main'] in main_ids:
                #         conflict_ids += [args[values_or_vals]['sync_consol_id_main']]
                #         continue




                # if create/write operation
                if operation in ['create', 'write']:
                    # reformat args values, convert relation sync_id_api to odoo object id
                    # self.env.cr.execute("SELECT sync_consol_id_main FROM {model} WHERE sync_type='{sync_type}' AND sync_consol_id_main = '{sync_id}'".format(model=model.replace(".", "_"), sync_type=value['sync_type'], sync_id=value['sync_consol_id_main']))

                    model_test = value['res_model']

                    args[values_or_vals] = {key: request.env[model_test].search([('sync_consol_id_main', '=', value), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id if key in ['res_id'] else value for key, value in args[values_or_vals].items()}
                    # args[values_or_vals] = {key: request.env[relational_fields[key]].search([('sync_consol_id_main', '=', value), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id if relational_fields.get(key) and type(value) in [str, unicode] and key not in ['user_type_id','bank_name','position_id','approval_id','payment_method_id'] else value for key, value in args[values_or_vals].iteritems()}
                    
                # if operation not write
                if not operation == 'write':
                    result = False

                    # if operation create
                    if operation == 'create':
                        # create log message
                        message = "\n\nExecute API Create"
                        open(log_file, 'a').write(message)
                        # create new record data
                        result = request.env[model].create(**args)
                        # open(log_file, 'a').write(json(result))

                        # add latest id to temp variable
                        # main_ids.append(result.sync_consol_id_unit)

                    # if operation not create & write
                    else:
                        # autocall operation method in records
                        result = getattr(records, operation)(**args)

                    # if create operation, add new record data to result
                    if operation != 'unlink':
                        records += result

                # if write operation
                else:
                    if args[values_or_vals].get('sync_consol_id_main'):
                        if model != 'product.product':
                            args[values_or_vals]['id'] = request.env[model].search([('sync_consol_id_main', '=', args[values_or_vals]['sync_consol_id_main']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                            
                            ####Chaelvin####
                            get_id = args[values_or_vals]['id']
                            
                            if model == 'bank.information' and args[values_or_vals]['id']:
                                search_record = request.env[model].search([('id', '=', args[values_or_vals]['id'])],limit=1)
                                if search_record:
                                    search_record.bank_name.trigger_write = False
                                    search_record.bank_name.trigger_create = True
                        # elif model == 'product.product':
                        #     args[values_or_vals]['id'] = request.env[model].search([('name', '=', args[values_or_vals]['name']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                            
                        #     ####Chaelvin####
                        #     get_id = args[values_or_vals]['id']
                    
                    
                    record = request.env[model].browse(args[values_or_vals]['id'])
                    # autocall write method in record
                    getattr(record, operation)(**args)
                    records += record

            # kenapa harus taruh result True disini ??
            result = True
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + 'ID DI BWH TRUE' + str(tes123))

            # if operation not write or unlink
            if operation not in ['write', 'unlink']:
                result = records.read(load=False)
                import datetime
                for rec in result:
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                    




                data.update({'status': 'success', 'data': rec})
                for r in result:
                    for image in ['image_small', 'image_medium', 'image', 'sign']:
                        if image in r:
                            r[image] = False

            ####Chaelvin####
            elif operation in ['write']:
                list_write = []
                value_write = {}
                value_write["id"] = get_id
                list_write.append(value_write)
                result = list_write
                import datetime
                for rec in result:
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                    




                data.update({'status': 'success', 'data': rec})
                

            # update data result
            data.update({'status': 'success', 'data': rec})

            # if have conflict_ids
            # if conflict_ids:
            #     data.update({'message': 'Some of the id are already created'})
            #     # data.update({'data': '(%s)' % (json(conflict_ids))})
            #     data.update({'data_conflict': conflict_ids})

        # show error exception
        except:
            data.update({'status': 'error', 'message': format_exc()})

        json_data = json(data)
        # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
        message = "\n\ntimelog: " + "\n\nresponse: " + json_data
        message += "\n\n================= end ==================="

        open(log_file, 'a').write(message)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

    # Define API Operation
    # Consol to Unit Integration data
    @http.route('/internal_api/main/message/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_main_message_method(self, operation, model, **args):
        data = {}
        origin_args = args
        args = parse(args)

        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/main/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        # if os.path.exists(log_file):
        #     if os.path.getsize(log_file) > 1000000:
        #         time_name_ren = '_' + datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S")
        #         log_file_ren = log_dir + log_name + time_name_ren + '.log'
        #         os.rename(log_file, log_file_ren)
        open(log_file, 'a').write(message)

        # for args in argss:
        # args = eval(args)

        self = request.env[model]
        cek1 = str(args['company_name'])
        cek2 = str(args['user_consol_main'])
        query_update = """
        update res_users set company_id = (select(id) from res_company where name = '{company_name}') where login = '{user_consol_main}'
        """.format(company_name=cek1, user_consol_main = cek2)
        self.env.cr.execute(query_update)
        # if args.get('context'):
        #     self = self.with_context(**args['context'])
        #     del args['context']

        try:
            if operation == 'search' and args.get('sql_query'):
                kwargs = dict(args)
                default = dict(args=[], offset=0, limit=None, order=None, count=False, access_rights_uid=None)
                args, offset, limit, order, count, access_rights_uid = [kwargs.get(variable, default.get(variable)) for variable in ['args', 'offset', 'limit', 'order', 'count', 'access_rights_uid']]
                self.sudo(access_rights_uid or self._uid).check_access_rights('read')
                query = self._where_calc(args)
                self._apply_ir_rules(query, 'read')
                order_by = self._generate_order_by(order, query)
                from_clause, where_clause, where_clause_params = query.get_sql()
                where_str = where_clause and (" WHERE %s" % where_clause) or ''
                #if count request
                if count:
                    query_str = 'SELECT count(1) FROM ' + from_clause + where_str
                    self._cr.execute(query_str, where_clause_params)
                    res = self._cr.fetchone()
                    return res[0]

                limit_str = limit and ' limit %d' % limit or ''
                offset_str = offset and ' offset %d' % offset or ''
                query_str = 'SELECT "%s" FROM ' % self._table + from_clause + where_str + order_by + limit_str + offset_str
                self._cr.execute(query_str, where_clause_params)
                return request.make_response(json({'status': 'success', 'data': self._cr.dictfetchall() }), [('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

            # browse all record model
            records = request.env[model].browse()
            # filter record by ids parameter
            if 'ids' in args:
                records = records.browse(args['ids'])
                del args['ids']

            # define unit ids
            main_ids = []
            conflict_ids = []
            values_or_vals = 'vals'
            relational_fields = {}

            

            # if create operation
            if operation == 'create':
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                # for value in args['values']:
                #     self.env.cr.execute("SELECT sync_consol_id_main FROM {model} WHERE sync_type='{sync_type}' AND sync_consol_id_main = '{sync_id}'".format(model=model.replace(".", "_"), sync_type=value['sync_type'], sync_id=value['sync_consol_id_main']))
                #     main_ids += [object[0] for object in self.env.cr.fetchall()]
                #     open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(main_ids))

            # if operation create or write
            if operation in ['create', 'write']:
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                # by pass parameter "value"
                if args.get('value'):
                    raise Exception('Unrecognized parameter "value"')
                values_or_vals = 'values' if signature(
                    getattr(request.env[model], operation)).parameters.get('values', False) else 'vals'
                # stored data relation fields
                relational_fields = {key: value.comodel_name for key, value in request.env[model]._fields.items() if type(value) in [fields.Many2one, fields.One2many]}

            


            for args in [args] if operation not in ['create', 'write'] else [{values_or_vals: value} for value in (args.get('vals', []) + args.get('values', []))]:
                # records = eval('request.env[model].%s(**args)' % (operation))
                
                ####Conflict di komen####
                # if operation == 'create':
                #     # define conflict_ids
                #     if args[values_or_vals]['sync_consol_id_main'] in main_ids:
                #         conflict_ids += [args[values_or_vals]['sync_consol_id_main']]
                #         continue




                # if create/write operation
                if operation in ['create', 'write']:
                    # reformat args values, convert relation sync_id_api to odoo object id
                    # self.env.cr.execute("SELECT sync_consol_id_main FROM {model} WHERE sync_type='{sync_type}' AND sync_consol_id_main = '{sync_id}'".format(model=model.replace(".", "_"), sync_type=value['sync_type'], sync_id=value['sync_consol_id_main']))

                    model_test = value['model']
                    # args[values_or_vals] = {key: request.env[model_test].search([('sync_consol_id_main', '=', value)], limit=1, order='id asc').id if key in ['res_id','author_id'] else value for key, value in args[values_or_vals].iteritems()}
                    args[values_or_vals] = {key: request.env[model_test].search([('sync_consol_id_main', '=', value)], limit=1, order='id asc').id if key in ['author_id'] else request.env[model_test].search([('sync_consol_id_main', '=', value), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id if key in ['res_id'] else value for key, value in args[values_or_vals].items()}
                    
                    # args[values_or_vals] = {key: request.env[model_test].search([('sync_consol_id_main', '=', value), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id if key not in ['res_id'] else value for key, value in args[values_or_vals].iteritems()}
                    # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + 'sesudah 2 ' + str(args[values_or_vals]))
                    
                    # args[values_or_vals] = {key: request.env[relational_fields[key]].search([('sync_consol_id_main', '=', value), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id if relational_fields.get(key) and type(value) in [str, unicode] and key not in ['user_type_id','bank_name','position_id','approval_id','payment_method_id'] else value for key, value in args[values_or_vals].iteritems()}
                    
                # if operation not write
                if not operation == 'write':
                    result = False

                    # if operation create
                    if operation == 'create':
                        # create log message
                        message = "\n\nExecute API Create"
                        open(log_file, 'a').write(message)
                        # create new record data
                        result = request.env[model].create(**args)
                        # open(log_file, 'a').write(json(result))

                        # add latest id to temp variable
                        # main_ids.append(result.sync_consol_id_unit)

                    # if operation not create & write
                    else:
                        # autocall operation method in records
                        result = getattr(records, operation)(**args)

                    # if create operation, add new record data to result
                    if operation != 'unlink':
                        records += result

                # if write operation
                else:
                    if args[values_or_vals].get('sync_consol_id_main'):
                        if model != 'product.product':
                            args[values_or_vals]['id'] = request.env[model].search([('sync_consol_id_main', '=', args[values_or_vals]['sync_consol_id_main']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                            
                            ####Chaelvin####
                            get_id = args[values_or_vals]['id']
                            
                            if model == 'bank.information' and args[values_or_vals]['id']:
                                search_record = request.env[model].search([('id', '=', args[values_or_vals]['id'])],limit=1)
                                if search_record:
                                    search_record.bank_name.trigger_write = False
                                    search_record.bank_name.trigger_create = True
                        # elif model == 'product.product':
                        #     args[values_or_vals]['id'] = request.env[model].search([('name', '=', args[values_or_vals]['name']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                            
                        #     ####Chaelvin####
                        #     get_id = args[values_or_vals]['id']
                    
                    
                    record = request.env[model].browse(args[values_or_vals]['id'])
                    # autocall write method in record
                    getattr(record, operation)(**args)
                    records += record

            # kenapa harus taruh result True disini ??
            result = True
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + 'ID DI BWH TRUE' + str(tes123))

            # if operation not write or unlink
            if operation not in ['write', 'unlink']:
                result = records.read(load=False)
                import datetime
                for rec in result:
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                    




                data.update({'status': 'success', 'data': rec})

                for r in result:
                    for image in ['image_small', 'image_medium', 'image', 'sign']:
                        if image in r:
                            r[image] = False

            ####Chaelvin####
            elif operation in ['write']:
                list_write = []
                value_write = {}
                value_write["id"] = get_id
                list_write.append(value_write)
                result = list_write
                import datetime
                for rec in result:
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                    




                data.update({'status': 'success', 'data': rec})
                

            # update data result
            data.update({'status': 'success', 'data': rec})

            # if have conflict_ids
            # if conflict_ids:
            #     data.update({'message': 'Some of the id are already created'})
            #     # data.update({'data': '(%s)' % (json(conflict_ids))})
            #     data.update({'data_conflict': conflict_ids})

        # show error exception
        except:
            data.update({'status': 'error', 'message': format_exc()})

        json_data = json(data)
        # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
        message = "\n\ntimelog: " + "\n\nresponse: " + json_data
        message += "\n\n================= end ==================="

        open(log_file, 'a').write(message)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

    # Define API Operation
    # Consol to Unit Integration data
    @http.route('/internal_api/unit/attachment/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_unit_attachment_method(self, operation, model, **args):
        data = {}
        origin_args = args
        args = parse(args)

        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/main/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        # if os.path.exists(log_file):
        #     if os.path.getsize(log_file) > 1000000:
        #         time_name_ren = '_' + datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S")
        #         log_file_ren = log_dir + log_name + time_name_ren + '.log'
        #         os.rename(log_file, log_file_ren)
        open(log_file, 'a').write(message)

        # for args in argss:
        # args = eval(args)

        self = request.env[model]
        cek1 = str(args['company_name'])
        cek2 = str(args['user_consol_main'])
        query_update = """
        update res_users set company_id = (select(id) from res_company where name = '{company_name}') where login = '{user_consol_main}'
        """.format(company_name=cek1, user_consol_main = cek2)
        self.env.cr.execute(query_update)
        # if args.get('context'):
        #     self = self.with_context(**args['context'])
        #     del args['context']

        try:
            if operation == 'search' and args.get('sql_query'):
                kwargs = dict(args)
                default = dict(args=[], offset=0, limit=None, order=None, count=False, access_rights_uid=None)
                args, offset, limit, order, count, access_rights_uid = [kwargs.get(variable, default.get(variable)) for variable in ['args', 'offset', 'limit', 'order', 'count', 'access_rights_uid']]
                self.sudo(access_rights_uid or self._uid).check_access_rights('read')
                query = self._where_calc(args)
                self._apply_ir_rules(query, 'read')
                order_by = self._generate_order_by(order, query)
                from_clause, where_clause, where_clause_params = query.get_sql()
                where_str = where_clause and (" WHERE %s" % where_clause) or ''
                #if count request
                if count:
                    query_str = 'SELECT count(1) FROM ' + from_clause + where_str
                    self._cr.execute(query_str, where_clause_params)
                    res = self._cr.fetchone()
                    return res[0]

                limit_str = limit and ' limit %d' % limit or ''
                offset_str = offset and ' offset %d' % offset or ''
                query_str = 'SELECT "%s" FROM ' % self._table + from_clause + where_str + order_by + limit_str + offset_str
                self._cr.execute(query_str, where_clause_params)
                return request.make_response(json({'status': 'success', 'data': self._cr.dictfetchall() }), [('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

            # browse all record model
            records = request.env[model].browse()
            # filter record by ids parameter
            if 'ids' in args:
                records = records.browse(args['ids'])
                del args['ids']

            # define unit ids
            main_ids = []
            conflict_ids = []
            values_or_vals = 'vals'
            relational_fields = {}

            

            # if create operation
            if operation == 'create':
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                # for value in args['values']:
                #     self.env.cr.execute("SELECT sync_consol_id_main FROM {model} WHERE sync_type='{sync_type}' AND sync_consol_id_main = '{sync_id}'".format(model=model.replace(".", "_"), sync_type=value['sync_type'], sync_id=value['sync_consol_id_main']))
                #     main_ids += [object[0] for object in self.env.cr.fetchall()]
                #     open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(main_ids))

            # if operation create or write
            if operation in ['create', 'write']:
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                # by pass parameter "value"
                if args.get('value'):
                    raise Exception('Unrecognized parameter "value"')
                values_or_vals = 'values' if signature(
                    getattr(request.env[model], operation)).parameters.get('values', False) else 'vals'
                # stored data relation fields
                relational_fields = {key: value.comodel_name for key, value in request.env[model]._fields.items() if type(value) in [fields.Many2one, fields.One2many]}

            


            for args in [args] if operation not in ['create', 'write'] else [{values_or_vals: value} for value in (args.get('vals', []) + args.get('values', []))]:
                # records = eval('request.env[model].%s(**args)' % (operation))
                
                ####Conflict di komen####
                # if operation == 'create':
                #     # define conflict_ids
                #     if args[values_or_vals]['sync_consol_id_main'] in main_ids:
                #         conflict_ids += [args[values_or_vals]['sync_consol_id_main']]
                #         continue


                # if create/write operation
                if operation in ['create', 'write']:
                    # reformat args values, convert relation sync_id_api to odoo object id
                    # self.env.cr.execute("SELECT sync_consol_id_main FROM {model} WHERE sync_type='{sync_type}' AND sync_consol_id_main = '{sync_id}'".format(model=model.replace(".", "_"), sync_type=value['sync_type'], sync_id=value['sync_consol_id_main']))

                    model_test = value['res_model']

                    args[values_or_vals] = {key: request.env[model_test].search([('sync_consol_id_unit', '=', value), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id if key in ['res_id'] else value for key, value in args[values_or_vals].items()}
                    # args[values_or_vals] = {key: request.env[relational_fields[key]].search([('sync_consol_id_main', '=', value), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id if relational_fields.get(key) and type(value) in [str, unicode] and key not in ['user_type_id','bank_name','position_id','approval_id','payment_method_id'] else value for key, value in args[values_or_vals].iteritems()}
                    
                # if operation not write
                if not operation == 'write':
                    result = False

                    # if operation create
                    if operation == 'create':
                        # create log message
                        message = "\n\nExecute API Create"
                        open(log_file, 'a').write(message)
                        # create new record data
                        result = request.env[model].create(**args)
                        # open(log_file, 'a').write(json(result))

                        # add latest id to temp variable
                        # main_ids.append(result.sync_consol_id_unit)

                    # if operation not create & write
                    else:
                        # autocall operation method in records
                        result = getattr(records, operation)(**args)

                    # if create operation, add new record data to result
                    if operation != 'unlink':
                        records += result

                # if write operation
                else:
                    if args[values_or_vals].get('sync_consol_id_main'):
                        if model != 'product.product':
                            args[values_or_vals]['id'] = request.env[model].search([('sync_consol_id_main', '=', args[values_or_vals]['sync_consol_id_main']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                            
                            ####Chaelvin####
                            get_id = args[values_or_vals]['id']
                            
                            if model == 'bank.information' and args[values_or_vals]['id']:
                                search_record = request.env[model].search([('id', '=', args[values_or_vals]['id'])],limit=1)
                                if search_record:
                                    search_record.bank_name.trigger_write = False
                                    search_record.bank_name.trigger_create = True
                        # elif model == 'product.product':
                        #     args[values_or_vals]['id'] = request.env[model].search([('name', '=', args[values_or_vals]['name']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                            
                        #     ####Chaelvin####
                        #     get_id = args[values_or_vals]['id']
                    
                    
                    record = request.env[model].browse(args[values_or_vals]['id'])
                    # autocall write method in record
                    getattr(record, operation)(**args)
                    records += record

            # kenapa harus taruh result True disini ??
            result = True
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + 'ID DI BWH TRUE' + str(tes123))

            # if operation not write or unlink
            if operation not in ['write', 'unlink']:
                result = records.read(load=False)
                import datetime
                for rec in result:
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                    




                data.update({'status': 'success', 'data': rec})
                for r in result:
                    for image in ['image_small', 'image_medium', 'image', 'sign']:
                        if image in r:
                            r[image] = False

            ####Chaelvin####
            elif operation in ['write']:
                list_write = []
                value_write = {}
                value_write["id"] = get_id
                list_write.append(value_write)
                result = list_write
                import datetime
                for rec in result:
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                    




                data.update({'status': 'success', 'data': rec})
                

            # update data result
            data.update({'status': 'success', 'data': rec})

            # if have conflict_ids
            # if conflict_ids:
            #     data.update({'message': 'Some of the id are already created'})
            #     # data.update({'data': '(%s)' % (json(conflict_ids))})
            #     data.update({'data_conflict': conflict_ids})

        # show error exception
        except:
            data.update({'status': 'error', 'message': format_exc()})

        json_data = json(data)
        # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
        message = "\n\ntimelog: " + "\n\nresponse: " + json_data
        message += "\n\n================= end ==================="

        open(log_file, 'a').write(message)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])



    # Define API Operation
    # Consol to Unit Integration data
    @http.route('/internal_api/unit/message/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_unit_message_method(self, operation, model, **args):
        data = {}
        origin_args = args
        args = parse(args)
        

        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/main/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        # if os.path.exists(log_file):
        #     if os.path.getsize(log_file) > 1000000:
        #         time_name_ren = '_' + datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S")
        #         log_file_ren = log_dir + log_name + time_name_ren + '.log'
        #         os.rename(log_file, log_file_ren)
        open(log_file, 'a').write(message)

        # for args in argss:
        # args = eval(args)

        self = request.env[model]
        
        cek1 = str(args['company_name'])
        cek2 = str(args['user_consol_main'])
        query_update = """
        update res_users set company_id = (select(id) from res_company where name = '{company_name}') where login = '{user_consol_main}'
        """.format(company_name=cek1, user_consol_main = cek2)
        self.env.cr.execute(query_update)
        # if args.get('context'):
        #     self = self.with_context(**args['context'])
        #     del args['context']

        try:
            if operation == 'search' and args.get('sql_query'):
                kwargs = dict(args)
                default = dict(args=[], offset=0, limit=None, order=None, count=False, access_rights_uid=None)
                args, offset, limit, order, count, access_rights_uid = [kwargs.get(variable, default.get(variable)) for variable in ['args', 'offset', 'limit', 'order', 'count', 'access_rights_uid']]
                self.sudo(access_rights_uid or self._uid).check_access_rights('read')
                query = self._where_calc(args)
                self._apply_ir_rules(query, 'read')
                order_by = self._generate_order_by(order, query)
                from_clause, where_clause, where_clause_params = query.get_sql()
                where_str = where_clause and (" WHERE %s" % where_clause) or ''
                #if count request
                if count:
                    query_str = 'SELECT count(1) FROM ' + from_clause + where_str
                    self._cr.execute(query_str, where_clause_params)
                    res = self._cr.fetchone()
                    return res[0]

                limit_str = limit and ' limit %d' % limit or ''
                offset_str = offset and ' offset %d' % offset or ''
                query_str = 'SELECT "%s" FROM ' % self._table + from_clause + where_str + order_by + limit_str + offset_str
                self._cr.execute(query_str, where_clause_params)
                return request.make_response(json({'status': 'success', 'data': self._cr.dictfetchall() }), [('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

            # browse all record model
            records = request.env[model].browse()
            # filter record by ids parameter
            if 'ids' in args:
                records = records.browse(args['ids'])
                del args['ids']

            # define unit ids
            main_ids = []
            conflict_ids = []
            values_or_vals = 'vals'
            relational_fields = {}

            

            # if create operation
            if operation == 'create':
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                # for value in args['values']:
                #     self.env.cr.execute("SELECT sync_consol_id_main FROM {model} WHERE sync_type='{sync_type}' AND sync_consol_id_main = '{sync_id}'".format(model=model.replace(".", "_"), sync_type=value['sync_type'], sync_id=value['sync_consol_id_main']))
                #     main_ids += [object[0] for object in self.env.cr.fetchall()]
                #     open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(main_ids))

            # if operation create or write
            if operation in ['create', 'write']:
                if len(args['values']) > 50:
                    data.update({'status': 'error', 'message': "Payload melebihi batas 50!!"})
                    json_data = json(data)
                    message = "\n\ntimelog: " + str(log_time) + "\n\nresponse: " + json_data
                    message += "\n\n================= end ==================="
                    open(log_file, 'a').write(message)
                    return request.make_response(json_data,[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')])

                # by pass parameter "value"
                if args.get('value'):
                    raise Exception('Unrecognized parameter "value"')
                values_or_vals = 'values' if signature(
                    getattr(request.env[model], operation)).parameters.get('values', False) else 'vals'
                # stored data relation fields
                relational_fields = {key: value.comodel_name for key, value in request.env[model]._fields.items() if type(value) in [fields.Many2one, fields.One2many]}

            


            for args in [args] if operation not in ['create', 'write'] else [{values_or_vals: value} for value in (args.get('vals', []) + args.get('values', []))]:
                # records = eval('request.env[model].%s(**args)' % (operation))
                
                ####Conflict di komen####
                # if operation == 'create':
                #     # define conflict_ids
                #     if args[values_or_vals]['sync_consol_id_main'] in main_ids:
                #         conflict_ids += [args[values_or_vals]['sync_consol_id_main']]
                #         continue


                # if create/write operation
                if operation in ['create', 'write']:
                    # reformat args values, convert relation sync_id_api to odoo object id
                    # self.env.cr.execute("SELECT sync_consol_id_main FROM {model} WHERE sync_type='{sync_type}' AND sync_consol_id_main = '{sync_id}'".format(model=model.replace(".", "_"), sync_type=value['sync_type'], sync_id=value['sync_consol_id_main']))

                    model_test = value['model']
                    # args[values_or_vals] = {key: request.env[model_test].search([('sync_consol_id_unit', '=', value)], limit=1, order='id asc').id if key in ['res_id','author_id'] else value for key, value in args[values_or_vals].iteritems()}
                    args[values_or_vals] = {key: request.env[model_test].search([('sync_consol_id_unit', '=', value)], limit=1, order='id asc').id if key in ['author_id'] else request.env[model_test].search([('sync_consol_id_unit', '=', value), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id if key in ['res_id'] else value for key, value in args[values_or_vals].items()}
                    
                    # args[values_or_vals] = {key: request.env[model_test].search([('sync_consol_id_unit', '=', value), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id if key not in ['res_id'] else value for key, value in args[values_or_vals].iteritems()}
                    # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + 'sesudah 2 ' + str(args[values_or_vals]))
                    
                    # args[values_or_vals] = {key: request.env[relational_fields[key]].search([('sync_consol_id_main', '=', value), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id if relational_fields.get(key) and type(value) in [str, unicode] and key not in ['user_type_id','bank_name','position_id','approval_id','payment_method_id'] else value for key, value in args[values_or_vals].iteritems()}
                # if operation not write
                if not operation == 'write':
                    result = False

                    # if operation create
                    if operation == 'create':
                        # create log message
                        message = "\n\nExecute API Create"
                        open(log_file, 'a').write(message)
                        # create new record data
                        result = request.env[model].create(**args)
                        # open(log_file, 'a').write(json(result))

                        # add latest id to temp variable
                        # main_ids.append(result.sync_consol_id_unit)

                    # if operation not create & write
                    else:
                        # autocall operation method in records
                        result = getattr(records, operation)(**args)

                    # if create operation, add new record data to result
                    if operation != 'unlink':
                        records += result

                # if write operation
                else:
                    if args[values_or_vals].get('sync_consol_id_main'):
                        if model != 'product.product':
                            args[values_or_vals]['id'] = request.env[model].search([('sync_consol_id_main', '=', args[values_or_vals]['sync_consol_id_main']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                            
                            ####Chaelvin####
                            get_id = args[values_or_vals]['id']
                            
                            if model == 'bank.information' and args[values_or_vals]['id']:
                                search_record = request.env[model].search([('id', '=', args[values_or_vals]['id'])],limit=1)
                                if search_record:
                                    search_record.bank_name.trigger_write = False
                                    search_record.bank_name.trigger_create = True
                        # elif model == 'product.product':
                        #     args[values_or_vals]['id'] = request.env[model].search([('name', '=', args[values_or_vals]['name']), ('sync_type', '=', args[values_or_vals]['sync_type'])], limit=1, order='id asc').id
                            
                        #     ####Chaelvin####
                        #     get_id = args[values_or_vals]['id']
                    
                    
                    record = request.env[model].browse(args[values_or_vals]['id'])
                    # autocall write method in record
                    getattr(record, operation)(**args)
                    records += record

            # kenapa harus taruh result True disini ??
            result = True
            # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + 'ID DI BWH TRUE' + str(tes123))

            # if operation not write or unlink
            if operation not in ['write', 'unlink']:
                result = records.read(load=False)
                import datetime
                for rec in result:
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                    




                data.update({'status': 'success', 'data': rec})
                for r in result:
                    for image in ['image_small', 'image_medium', 'image', 'sign']:
                        if image in r:
                            r[image] = False

            ####Chaelvin####
            elif operation in ['write']:
                list_write = []
                value_write = {}
                value_write["id"] = get_id
                list_write.append(value_write)
                result = list_write
                import datetime
                for rec in result:
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d %I:%M:%S")) if type(value) == datetime.datetime  else value for key, value in rec.items()}
                    rec = {key: str(datetime.datetime.strftime(value, "%Y-%m-%d")) if type(value) == datetime.date  else value for key, value in rec.items()}
                    




                data.update({'status': 'success', 'data': rec})
                

            # update data result
            data.update({'status': 'success', 'data': rec})

            # if have conflict_ids
            # if conflict_ids:
            #     data.update({'message': 'Some of the id are already created'})
            #     # data.update({'data': '(%s)' % (json(conflict_ids))})
            #     data.update({'data_conflict': conflict_ids})

        # show error exception
        except:
            data.update({'status': 'error', 'message': format_exc()})

        json_data = json(data)
        # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
        message = "\n\ntimelog: " + "\n\nresponse: " + json_data
        message += "\n\n================= end ==================="

        open(log_file, 'a').write(message)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

    # Define API Operation
    # Consol to Unit Integration data
    @http.route('/internal_search/main/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_unit_search_model_method(self, operation, model, **args):
        data = {}
        origin_args = args
        args = parse(args)

        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/main/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        # if os.path.exists(log_file):
        #     if os.path.getsize(log_file) > 1000000:
        #         time_name_ren = '_' + datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S")
        #         log_file_ren = log_dir + log_name + time_name_ren + '.log'
        #         os.rename(log_file, log_file_ren)
        open(log_file, 'a').write(message)

        # for args in argss:
        # args = eval(args)

        self = request.env[model]
        # if args.get('context'):
        #     self = self.with_context(**args['context'])
        #     del args['context']

        try:
            
            # # browse all record model
            records = request.env[model].browse()
            # # filter record by ids parameter
            # if 'ids' in args:
            #     records = records.browse(args['ids'])
            #     del args['ids']

            # # define unit ids
            # main_ids = []
            # conflict_ids = []
            # values_or_vals = 'vals'
            # relational_fields = {}

            # if args.get('value'):
            #     raise Exception('Unrecognized parameter "value"')
            # values_or_vals = 'values' if signature(
            #     getattr(request.env[model], operation)).parameters.get('values', False) else 'vals'
            # # stored data relation fields
            # relational_fields = {key: value.comodel_name for key, value in request.env[model]._fields.iteritems() if type(value) in [fields.Many2one, fields.One2many]}
            for value in args['values']:
                sync_id = value['sync_consol_id_main']
                sync_type = value['sync_type']
            
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(args))
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(sync_id))
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(sync_type))
            check_record = request.env[model].search([('sync_consol_id_main', '=', sync_id), ('sync_type', '=', sync_type)], limit=1, order='id asc').id
                        
            # tes123 = args['values']['sync_consol_id_unit']
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(check_record))
        
            record_po = request.env[model].browse(check_record)
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(record_po))
            

                                
            
            # kenapa harus taruh result True disini ??
            result = True
            ####Chaelvin####
            if operation in ['search']:
                list_write = []
                value_write = {}
                value_write["id"] = record_po.id
                value_write["name"] = record_po.name
                list_write.append(value_write)
                result = list_write
                

            # update data result
            data.update({'status': 'success', 'data': result})

        # show error exception
        except:
            data.update({'status': 'error', 'message': 'data tidak ketemu'})

        json_data = json(data)
        # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
        message = "\n\ntimelog: " + "\n\nresponse: " + json_data
        message += "\n\n================= end ==================="

        open(log_file, 'a').write(message)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])


    # Define API Operation
    # Consol to Unit Integration data
    @http.route('/internal_search/unit/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_main_search_model_method(self, operation, model, **args):
        data = {}
        origin_args = args
        args = parse(args)

        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/main/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        # if os.path.exists(log_file):
        #     if os.path.getsize(log_file) > 1000000:
        #         time_name_ren = '_' + datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S")
        #         log_file_ren = log_dir + log_name + time_name_ren + '.log'
        #         os.rename(log_file, log_file_ren)
        open(log_file, 'a').write(message)

        # for args in argss:
        # args = eval(args)

        self = request.env[model]
        # if args.get('context'):
        #     self = self.with_context(**args['context'])
        #     del args['context']

        try:
            
            # # browse all record model
            records = request.env[model].browse()
            # # filter record by ids parameter
            # if 'ids' in args:
            #     records = records.browse(args['ids'])
            #     del args['ids']

            # # define unit ids
            # main_ids = []
            # conflict_ids = []
            # values_or_vals = 'vals'
            # relational_fields = {}

            # if args.get('value'):
            #     raise Exception('Unrecognized parameter "value"')
            # values_or_vals = 'values' if signature(
            #     getattr(request.env[model], operation)).parameters.get('values', False) else 'vals'
            # # stored data relation fields
            # relational_fields = {key: value.comodel_name for key, value in request.env[model]._fields.iteritems() if type(value) in [fields.Many2one, fields.One2many]}
            for value in args['values']:
                sync_id = value['sync_consol_id_unit']
                sync_type = value['sync_type']
            
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(args))
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(sync_id))
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(sync_type))
            check_record = request.env[model].search([('sync_consol_id_unit', '=', sync_id), ('sync_type', '=', sync_type)], limit=1, order='id asc').id
                        
            # tes123 = args['values']['sync_consol_id_unit']
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(check_record))
        
            record_po = request.env[model].browse(check_record)
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(record_po))
            

                                
            
            # kenapa harus taruh result True disini ??
            result = True
            ####Chaelvin####
            if operation in ['search']:
                list_write = []
                value_write = {}
                value_write["id"] = record_po.id
                value_write["name"] = record_po.name
                list_write.append(value_write)
                result = list_write
                

            # update data result
            data.update({'status': 'success', 'data': result})

        # show error exception
        except:
            data.update({'status': 'error', 'message': 'data tidak ketemu'})

        json_data = json(data)
        # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
        message = "\n\ntimelog: " + "\n\nresponse: " + json_data
        message += "\n\n================= end ==================="

        open(log_file, 'a').write(message)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

    # Define API Operation
    # Consol to Unit Integration data
    @http.route('/internal_search_user/main/<operation>/<model>', type='http', auth='user', csrf=False)
    @route()
    def api_consol_unit_search_user_model_method(self, operation, model, **args):
        data = {}
        origin_args = args
        args = parse(args)

        # define log
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
        log_month= datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        log_day  = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S.%f")
        log_dir = '/opt/odoo16/logs/internal_api/main/' + log_year + '/' + log_month + '/' + log_day + '/' + operation + '/' + model + '/'
        log_name = log_date + '_' + operation + '_' + model
        log_file = log_dir + log_name + '.log'

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        message = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message += "\n\nuser: " + request.env.user.login + "\n\nparams: " + str(origin_args) + "\n\ntoken: "

        # if os.path.exists(log_file):
        #     if os.path.getsize(log_file) > 1000000:
        #         time_name_ren = '_' + datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H%M%S")
        #         log_file_ren = log_dir + log_name + time_name_ren + '.log'
        #         os.rename(log_file, log_file_ren)
        open(log_file, 'a').write(message)

        # for args in argss:
        # args = eval(args)

        self = request.env[model]
        # if args.get('context'):
        #     self = self.with_context(**args['context'])
        #     del args['context']

        try:
            
            # # browse all record model
            records = request.env[model].browse()
            # # filter record by ids parameter
            # if 'ids' in args:
            #     records = records.browse(args['ids'])
            #     del args['ids']

            # # define unit ids
            # main_ids = []
            # conflict_ids = []
            # values_or_vals = 'vals'
            # relational_fields = {}

            # if args.get('value'):
            #     raise Exception('Unrecognized parameter "value"')
            # values_or_vals = 'values' if signature(
            #     getattr(request.env[model], operation)).parameters.get('values', False) else 'vals'
            # # stored data relation fields
            # relational_fields = {key: value.comodel_name for key, value in request.env[model]._fields.iteritems() if type(value) in [fields.Many2one, fields.One2many]}
            for value in args['values']:
                sync_id = value['sync_consol_id_main']
                sync_type = value['sync_type']
                inactive_id = value['inactive_id']
            
            check_record = request.env[model].search([('sync_consol_id_main', '=', sync_id), ('sync_type', '=', sync_type)], limit=1, order='id asc').id
            check_record_inactive_id = request.env[model].search([('sync_consol_id_main', '=', inactive_id), ('sync_type', '=', sync_type)], limit=1, order='id asc').id
                        
            
            query1 = """
                    update res_partner set active='false', sync_type = null, sync_consol_id_main = null WHERE id = '{check_record}'
                    """.format(check_record=check_record)
            self.env.cr.execute(query1)
            
            query2 = """
                    update res_partner set sync_consol_id_main='{sync_id}' 
                    WHERE id = '{check_record_inactive_id}'
                    """.format(sync_id=sync_id, check_record_inactive_id=check_record_inactive_id)
            self.env.cr.execute(query2)

            record_partner = request.env[model].browse(check_record_inactive_id)
                                
            # kenapa harus taruh result True disini ??
            result = True
            ####Chaelvin####
            if operation in ['search']:
                list_write = []
                value_write = {}
                value_write["id"] = record_partner.id
                value_write["name"] = record_partner.name
                list_write.append(value_write)
                result = list_write

            # update data result
            data.update({'status': 'success', 'data': result})

        # show error exception
        except:
            data.update({'status': 'error', 'message': 'data tidak ketemu'})

        json_data = json(data)
        # log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%H:%M:%S.%f")
        message = "\n\ntimelog: " + "\n\nresponse: " + json_data
        message += "\n\n================= end ==================="

        open(log_file, 'a').write(message)
        return request.make_response(json_data,[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])




    # TAKS DUDI
    @http.route('/api/referral/agen/<model>', type='http', auth='none', csrf=True)
    @route()
    def api_consol_get_agen(self, model, **args):
        from odoo.http import request
        ref_agen = request.env[model]
        record_partner = request.env['res.partner'].sudo()
        data = {}
        args = parse(args)
        values = args['values']
        action = values['action']
        record = values['data']

        if record:
            row = {}
            row['sync_type'] = record['sync_type']
            row['sync_id'] = record['sync_id']
            row['sync_id_api'] = record['sync_id_api']
            row['company_id'] = ref_agen.env['res.company'].sudo().search([('sync_type', '=', row['sync_type'])], limit=1).id or None
            row['sync_date'] = tools.datetime.now().strftime('%Y-%m-%d')
            row['no_rekening'] = record['no_rekening']
            row['code'] = record['code']
            row['name'] = record['name'].upper()
            row['external_group_code'] = record['external_group_code']
            row['blocked'] = bool(int(record['blocked']))
            row['date_of_birth'] = record['date_of_birth']
            row['no_ktp'] = record['no_ktp']
            row['email'] = record['email']
            row['bank_name'] = record['bank_name'].upper()
            row['specialise_name'] = record['specialise_name'].upper()
            row['bank_account_name'] = record['bank_account_name'].upper()
            row['address'] = record['address']

            sync_partner = record_partner.env['res.partner'].search([('sync_type', '=', record['sync_type']), ('sync_id','=', record['sync_id']), ('doctor','=', True), ('type_doctor','=','external'), ('active','=', True)], limit=1)
            sync_partner_institution = record_partner.env['res.partner'].search([('sync_type', '=', record['sync_type']), ('sync_id','=', record['InstitutionId']), ('doctor','=', True), ('type_doctor','=', 'external'), ('active','=', True)], limit=1)
            
            sync_id_partner = sync_partner['sync_id']
            sync_id_institution = sync_partner_institution['sync_id']
            InstitutionId = (0 if record['InstitutionId'] == "" else record['InstitutionId']) # Convert Str To Integer
            
            # Check res.partner
            if record['sync_type'] in ['1','2']: # MHJS & MHTG
                if int(sync_id_partner) == int(record['sync_id']):
                    sync_partner['sync_id_api'] = row['sync_id_api']
                    sync_partner['sync_id'] = row['sync_id']
                    sync_partner['sync_type'] = row['sync_type']
                    sync_partner['company_id'] = False
                    sync_partner['doctor_code'] = row['code']
                    sync_partner['doctor'] = True
                    sync_partner['is_eproc'] = True
                    sync_partner['active'] = True
                    sync_partner['type_doctor'] = 'external'
                    sync_partner['spec'] = row['specialise_name']
                    sync_partner['name'] = row['name'].upper()
                else:
                    vals = {
                        'sync_id_api': row['sync_id_api'],
                        'sync_id': row['sync_id'],
                        'sync_type': row['sync_type'],
                        'company_id': False,
                        'doctor_code': row['code'],
                        'doctor': True,
                        'is_eproc': True,
                        'active': True,
                        'type_doctor': 'external',
                        'spec': row['specialise_name'],
                        'name': row['name'].upper()
                    }
                    record_partner.sudo().create(vals)
            
            # Check res.partner.institution
            if InstitutionId != 0:
                if int(sync_id_institution) == int(InstitutionId):
                    sync_partner_institution['sync_id'] = record['InstitutionId']
                    sync_partner_institution['sync_type'] = row['sync_type']
                    sync_partner_institution['company_id'] = False
                    sync_partner_institution['doctor'] = True
                    sync_partner_institution['is_eproc'] = True
                    sync_partner_institution['active'] = True
                    sync_partner_institution['type_doctor'] = 'external'
                    sync_partner_institution['name'] = record['InstitutionName'].upper()
                else:
                    vals = {
                        'sync_id': record['InstitutionId'],
                        'sync_type': row['sync_type'],
                        'company_id': False,
                        'doctor': True,
                        'is_eproc': True,
                        'active': True,
                        'type_doctor': 'external',
                        'name': record['InstitutionName'].upper()
                    }
                    record_partner.sudo().create(vals)

            row['institution_id'] = ref_agen.env['res.partner'].sudo().search([('sync_id', '=', record['InstitutionId']), ('sync_type', '=', record['sync_type']), ('doctor','=', True), ('type_doctor','=', 'external'), ('active','=', True)], limit=1).id or None
            
            row['phone'] = record['phone']
            row['mobile'] = record['mobile']
            row['gender'] = record['gender']
            row['specialise_id'] = record['specialise_id']
            row['spec_name'] = record['spec_name'].upper()
            row['external_group_id'] = record['external_group_id']
            row['category_id'] = record['category_id']
            
            # Validate SpecID
            spec_id = ref_agen.env['account.analytic.account'].sudo().search([('sync_id', '=', record['spec_id']), ('sync_wipro_type', '=', 'specialization'), ('sync_type', '=', record['sync_type'])],limit=1).id or None
            if spec_id:
                row['spec_id'] = spec_id

            if str(action) == "update":
                sync_ids = ref_agen.sudo().search([('sync_type', '=', str(row['sync_type'])), ('sync_id', '=', str(row['sync_id']))])
                # Check Data Empty
                if sync_ids:
                    update = sync_ids.sudo().write(row)
                    data.update({'status': 'success', 'message': 'data has been updated'})
                else:
                    data.update({'status': 'failed', 'message': 'no data updated'})
            if str(action) == "insert":
                # Check Data Double
                sync_ids = ref_agen.sudo().search([('sync_type', '=', str(row['sync_type'])), ('sync_id', '=', str(row['sync_id']))])
                if sync_ids:
                    data.update({'status': 'failed', 'message': 'data already exists'})
                else:
                    ref_agen.sudo().create(row)
                    data.update({'status': 'success', 'message': 'data has been inserted'})

                    if data['status'] == 'success': 
                        # Update referral.agen
                        ref_agen._update_referral_agen(sync_type=row['sync_type'], sync_id_partner=row['sync_id_api'], code=row['code'], sync_id_spec=row['specialise_name'])
                        
        return request.make_response(json(data),[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])


    @http.route('/api/referral/transaction/<model>', type='http', auth='none', csrf=True)
    @route()
    def api_consol_get_transaction(self, model, **args):
        from odoo.http import request
        ref_tranc = request.env[model]
        data = {}
        args = parse(args)
        values = args['values']
        action = values['action']
        record = values['data']
        
        if record:
            row = {}
            row['admission_number'] = record['admission_number']
            row['sync_type'] = record['sync_type']
            row['patient_name'] = record['patient_name'].upper()
            row['transaction_date'] = record['transaction_date']
            row['email'] = record['email']
            row['mobile_phone'] = record['mobile_phone']
            row['date_of_birth'] = record['date_of_birth']
            row['appointment_date'] = record['appointment_date']
            row['doctor_external_name'] = record['doctor_external_name'].upper()
            row['gender_name'] = record['gender_name']
            row['transaction_no'] = record['transaction_no']
            row['is_merge_bill'] = record['is_merge_bill']
            row['blocked'] = bool(int(record['blocked']))
            row['sync_id'] = record['sync_id']
            row['sync_date'] = tools.datetime.now().strftime('%Y-%m-%d')
            row['company_id'] = ref_tranc.env['res.company'].sudo().search([('sync_type', '=', row['sync_type'])], limit=1).id or None
            row['external_name'] = record['external_name'].upper()
            row['admission_id'] = record['admission_id']
            row['admission_no'] = record['admission_no']
            row['odoo_admission_id'] = ref_tranc.env['sale.order'].sudo().search([('sync_id', '=', record['admission_id']), ('sync_type', '=', row['sync_type'])],limit=1).id or None
            if row['odoo_admission_id']:
                row['odoo_bill_id'] = ref_tranc.env['sale.order.bill'].sudo().search([('admission_id', '=', row['odoo_admission_id']), ('sync_type', '=', record['sync_type'])],limit=1).id or None
                row['bill_no'] = ref_tranc.env['sale.order.bill'].sudo().search([('admission_id', '=', row['odoo_admission_id']), ('sync_type', '=', record['sync_type'])],limit=1).billno or None
                row['bill_date'] = ref_tranc.env['sale.order.bill'].sudo().search([('admission_id', '=', row['odoo_admission_id']), ('sync_type', '=', record['sync_type'])],limit=1).confirmation_date or None            
            row['odoo_external_id'] = ref_tranc.env['referral.agen'].sudo().search([('sync_type','=', record['sync_type']), ('sync_id', '=', record['external_id'])],limit=1).id or None
            row['gender'] = record['gender']
            row['external_id'] = record['external_id']
            row['bill_id'] = record['bill_id']

            if str(action) == "update":
                sync_ids = ref_tranc.sudo().search([('sync_type', '=', str(row['sync_type'])), ('sync_id', '=', str(row['sync_id']))])
                # Check Data Empty
                if sync_ids:
                    update = sync_ids.sudo().write(row)
                    # Create ir.attahcment
                    if record['image']:
                        ref_tranc.create_ir_attachment(record, action='update')
                    data.update({'status': 'success', 'message': 'data has been updated'})
                else:
                    data.update({'status': 'failed', 'message': 'no data updated'})

            if str(action) == "insert":
                sync_ids = ref_tranc.sudo().search([('sync_type', '=', str(row['sync_type'])), ('sync_id', '=', str(row['sync_id']))])
                # Check Data Double
                if sync_ids:
                    data.update({'status': 'failed', 'message': 'data already exists'})
                else:
                    ref_tranc.sudo().create(row)
                    # Create ir.attahcment
                    if record['image']:
                        ref_tranc.create_ir_attachment(record, action='insert')
                    data.update({'status': 'success', 'message': 'data has been inserted'})

        return request.make_response(json(data),[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])


    @http.route('/api/referral/worklist', type='http', auth='none', csrf=False)
    @route()
    def api_get_worklist(self, **kw):
        from odoo.http import request
        data = {}
        
        # declare model
        self = request.env['sale.order.bill']
        
        try:
            result = []
            
            query = """SELECT ROW_NUMBER() OVER (ORDER BY rf.billno)as page, rf.* FROM (
                SELECT DISTINCT
                    a.sync_type,
                    a.sync_id,
                    a.billno, 
                    c.id patient_id,
                    c.name patient_name, 
                    c.email,
                    a.referral_doc_id, 
                    ac.name referral_doc_name,
                    COALESCE(a.is_sent_voucher, False) is_sent_voucher,
                    COALESCE(a.is_sent_bsl, False) is_sent_bsl
                FROM sale_order_bill a 
                    INNER JOIN sale_order_line b ON b.billing_id=a.id AND b.sync_type=a.sync_type
                    INNER JOIN res_partner c ON b.partner_id=c.id
                    INNER JOIN account_analytic_account ac ON b.referral_doc_id=ac.id
                    INNER JOIN referral_agen rg ON rg.doctor_id=ac.id
                WHERE b.type_line in ('BILL','BILLING') --AND rg.category_id='10' 
                AND COALESCE(a.is_sent_bsl, False) = False
                ORDER BY c.name) rf """
            
            self.env.cr.execute(query)
            result = self.env.cr.dictfetchall()

            print("BERHASIL")
            data.update({'status' : 'success', 'message' : 'Get KOL Information has been successfully', 'result' : result})
            
        # except BaseException as err:
        except:
            print("GAGAL")
            data.update({'status' : 'failed', 'message' : format_exc(), 'result' : result})
            
        return request.make_response(json(data),[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])

    @http.route('/api/referral/worklist/<model>', type='http', auth='none', csrf=True)
    @route()
    def api_update_worklist(self, model, **args):
        from odoo.http import request
        sob = request.env[model]
        data = {}
        args = parse(args)
        values = args['values']
        record = values['data']
        
        try:
            if record:
                for r in record:
                    row = {}
                    # update flag
                    if r['flag'] == 'is_sent_voucher':
                        row['is_sent_voucher'] = r['sent']
                    elif r['flag'] == 'is_sent_bsl':
                        row['is_sent_bsl'] = r['sent']
                    
                    update_sob = sob.sudo().search([('sync_type', '=', r['sync_type']), ('sync_id', '=', r['sync_id'])])
                    update =update_sob.sudo().write(row)
                    
                    # Send Email
                    # sob._send_email()
            
            data.update({'status' : 'success', 'message' : 'Update Flaging has been successfully'})
            
        except:
            data.update({'status' : 'failed', 'message' : format_exc()})
        
        return request.make_response(json(data),[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])



    # 2022.12.21 - Tambahan GET json preview fee doctor untuk Dhealth MHBG
    @http.route('/api/fee_doctor', type='http', auth='user')
    @route()
    def api_get_fee_doctor_preview(self, **args):
        from odoo.http import request
        data = {}
        result = []
        args = parse(args)
        sync_type = args['sync_type'] if args.has_key('sync_type') else False
        sync_id_api = args['sync_id_api'] if args.has_key('sync_id_api') else False
        year = args['year'] if args.has_key('year') else False
        month = args['month'] if args.has_key('month') else False

        if not year:
            data.update({'status' : 'error', 'message' : 'Year period parameter is mandatory.'})
        if not month:
            data.update({'status' : 'error', 'message' : 'Month period parameter is mandatory.'})
        if not sync_type:
            data.update({'status' : 'error', 'message' : 'Sync type parameter is mandatory.'})
        
        try:
            self = request.env['doctor.fee']
            query = """
                select 
                    dc.sync_type,
                    dc.sync_id_api,
                    rc."name" company_name,
                    dc.code doctor_code,
                    dc."name" doctor_name,
                    a."year" period_year,
                    a."month" period_month, 
                    (case a."month" 
                        when 1 then 'January'
                        when 2 then 'February'
                        when 3 then 'March'
                        when 4 then 'April'
                        when 5 then 'May'
                        when 6 then 'June'
                        when 7 then 'July'
                        when 8 then 'August'
                        when 9 then 'September'
                        when 10 then 'October'
                        when 11 then 'November'
                        when 12 then 'December'
                    end) period_month_name,
                    a.gross_fee current_gross,
                    a.other current_others,
                    a.allowance current_allowance,
                    a.total_fee current_total_fee, 
                    a.bruto current_dpp,
                    a.gross_up current_grossup,
                    a.total current_total_fee_grossup,
                    a.dpp current_dpp_grossup,
                    a.dpp_50 current_dpp_50,
                    a.pph_21 current_pph,
                    a.total_nett current_nett_fee,
                    a.deduction current_deduction,
                    a.thp current_thp,
                    a.gf doctor_guarantee_fee,
                    a.is_npwp doctor_have_npwp,
                    a.npwp doctor_npwp,
                    a.is_grossup doctor_grossup,
                    a.lapis doctor_tax_level,
                    a.previous_bruto doctor_prev_dpp,
                    a.previous_pph21 doctor_prev_pph,
                    a.is_dental doctor_dental,
                    a.is_pot_gp doctor_pot_gp,
                    a.pot_point doctor_pot_point,
                    a.pot_share doctor_pot_share,
                    a.state doctor_state
                from doctor_fee a 
                inner join res_company rc on rc."id" = a.company_id 
                inner join account_analytic_account dc on dc."id" = a.doctor_id 
                where a."year" = {year}
                    and a."month" = {month}
                    and dc.sync_type = '{sync_type}'
                    and dc.sync_id_api = coalesce({sync_id_api}, dc.sync_id_api)
            """.format(
                year=year, 
                month=month,
                sync_type=sync_type,
                sync_id_api=('null' if not sync_id_api else ("'" + sync_id_api + "'"))
            )
            open('/opt/odoo16/logs/log_api_doctor_fee.log', 'a+').write('\n\1' + str(query))
            self.env.cr.execute(query)

            if not sync_id_api:
                result = self.env.cr.dictfetchall()
            else:
                result = self.env.cr.dictfetchone()

                # get transaction details
                query = """
                    select 
                        dfl.patient_group,
                        (case dfl.patient_type 
                            when '1' then 'OP'
                            when '2' then 'IP'
                            when '3' then 'Emergency'
                            when '4' then 'DayCare'
                            when '5' then 'MCU'
                            when '6' then 'Pharmacy'
                        end) patient_type, 
                        dfl.admission_no,
                        dfl.bill_no,
                        dfl.bill_date,
                        dfl.patient_regcode,
                        dfl.patient_name,
                        dfl.service_group,
                        dfl.payer_name,
                        pc."name" service_category,
                        dfl.specialise_name,
                        dfl.department_name,
                        dfl.bed_type,
                        dfl.order_no,
                        dfl.order_date,
                        dfl.order_item_no,
                        pt.default_code product_code, 
                        pt."name" product_name,
                        dfl.total bill_amount,
                        dfl.rate fee_amount 
                    from doctor_fee a 
                    inner join account_analytic_account dc on dc."id" = a.doctor_id 
                    inner join doctor_fee_line dfl on dfl.doctor_fee_id = a."id"
                    left join product_product pp on pp.id = dfl.odoo_service_item_id 
                    left join product_template pt on pt."id" = pp.product_tmpl_id 
                    left join product_category pc on pc."id" = dfl.odoo_service_id 
                    where a."year" = {year}
                        and a."month" = {month}
                        and dc.sync_type = '{sync_type}'
                        and dc.sync_id_api = '{sync_id_api}'
                        and dfl.is_bpjs is not True
                """.format(year=year, month=month, sync_type=sync_type, sync_id_api=sync_id_api)
                open('/opt/odoo16/logs/log_api_doctor_fee.log', 'a+').write('\n' + str(query))
                self.env.cr.execute(query)
                lines = self.env.cr.dictfetchall()
                result['transaction_lines'] = lines


                # get BPJS details
                query = """
                    select 
                        dfl.patient_group,
                        (case dfl.patient_type 
                            when '1' then 'OP'
                            when '2' then 'IP'
                            when '3' then 'Emergency'
                            when '4' then 'DayCare'
                            when '5' then 'MCU'
                            when '6' then 'Pharmacy'
                        end) patient_type, 
                        dfl.admission_no,
                        dfl.bill_no,
                        dfl.bill_date,
                        dfl.patient_regcode,
                        dfl.patient_name,
                        dfl.service_group,
                        dfl.payer_name,
                        pc."name" service_category,
                        dfl.specialise_name,
                        dfl.department_name,
                        dfl.bed_type,
                        dfl.order_no,
                        dfl.order_date,
                        dfl.order_item_no,
                        pt.default_code product_code, 
                        pt."name" product_name,
                        dfl.total bill_amount,
                        dfl.rate fee_accrual 
                    from doctor_fee a 
                    inner join account_analytic_account dc on dc."id" = a.doctor_id 
                    inner join doctor_fee_line dfl on dfl.doctor_fee_id = a."id"
                    left join product_product pp on pp.id = dfl.odoo_service_item_id 
                    left join product_template pt on pt."id" = pp.product_tmpl_id 
                    left join product_category pc on pc."id" = dfl.odoo_service_id 
                    where a."year" = {year}
                        and a."month" = {month}
                        and dc.sync_type = '{sync_type}'
                        and dc.sync_id_api = '{sync_id_api}'
                        and dfl.is_bpjs is True
                """.format(year=year, month=month, sync_type=sync_type, sync_id_api=sync_id_api)
                open('/opt/odoo16/logs/log_api_doctor_fee.log', 'a+').write('\n' + str(query))
                self.env.cr.execute(query)
                lines = self.env.cr.dictfetchall()
                result['bpjs_lines'] = lines

                # get addition details
                query = """
                    select 
                        ot.other_type,
                        ot.description,
                        ot.item,
                        ot.amount,
                        ot.credit_gf
                    from doctor_fee a 
                    inner join account_analytic_account dc on dc."id" = a.doctor_id 
                    inner join other_transaction ot on ot.doctor_fee_id = a."id" 
                    where a."state" = 'draft'
                        and a."year" = {year}
                        and a."month" = {month}
                        and dc.sync_type = '{sync_type}'
                        and dc.sync_id_api = '{sync_id_api}'
                """.format(year=year, month=month, sync_type=sync_type, sync_id_api=sync_id_api)
                open('/opt/odoo16/logs/log_api_doctor_fee.log', 'a+').write('\n' + str(query))
                self.env.cr.execute(query)
                additions = self.env.cr.dictfetchall()
                result['addition_lines'] = additions

                # get deductions details
                query = """
                    select 
                        ot.description,
                        ot.item,
                        ot.amount
                    from doctor_fee a 
                    inner join account_analytic_account dc on dc."id" = a.doctor_id 
                    inner join deduction_transaction ot on ot.doctor_fee_id = a."id" 
                    where a."state" = 'draft'
                        and a."year" = {year}
                        and a."month" = {month}
                        and dc.sync_type = '{sync_type}'
                        and dc.sync_id_api = '{sync_id_api}'
                """.format(year=year, month=month, sync_type=sync_type, sync_id_api=sync_id_api)
                open('/opt/odoo16/logs/log_api_doctor_fee.log', 'a+').write('\n' + str(query))
                self.env.cr.execute(query)
                deductions = self.env.cr.dictfetchall()
                result['deduction_lines'] = deductions
            
            data.update({'status' : 'success', 'result': result, 'message' : 'Retreived data successfully'})
        except:
            data.update({'status' : 'failed', 'message' : format_exc()})
        
        return request.make_response(json(data),[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])


    @http.route('/api/doctor_fee/compute/<model>', type='http', auth='none', csrf=False)
    @route()
    def api_compute_doctor_fee(self, model, **args):
        from odoo.http import request
        record = request.env[model].sudo()
        data = {}
        args = parse(args)
        company_id = args['company_id']
        year = args['year']
        month = args['month']
        state = args['state']
        
        if not company_id:
            data.update({'status' : 'error', 'message' : 'Company parameter is mandatory.'})
        if not year:
            data.update({'status' : 'error', 'message' : 'Year period parameter is mandatory.'})
        if not month:
            data.update({'status' : 'error', 'message' : 'Month period parameter is mandatory.'})
        if not state:
            data.update({'status' : 'error', 'message' : 'State parameter is mandatory.'})
        
        try:
            
            doctor = record.env['doctor.fee'].search([('company_id', '=', company_id),('year', '=', year),('month', '=', month),('state', '=', str(state))], limit=10)
            
            # if not doctor:
            record.env.cr.execute("""
                SELECT distinct 
                    a.doctor_id, 
                    a.is_pot_gp, 
                    a.is_pot_total, 
                    a.is_dental,
                    a.is_external,
                    a.is_grossup,
                    a.is_npwp,
                    a.npwp,
                    a.guarantee_fee
                FROM doctor_rate a
                WHERE a.company_id = '%s' 
                    AND a.doctor_id not in (
                        select t.doctor_id 
                        from doctor_fee t
                        where t.company_id = a.company_id
                            and t.year = '%s'
                            and t.month = '%s' ) 
            """ % (company_id, year, month))

            lines = record.env.cr.dictfetchall()
            if lines:
                for line in lines:
                    record.env['doctor.fee'].create({
                        'doctor_id':int(line['doctor_id']),
                        'is_pot_gp':line['is_pot_gp'],
                        'is_pot_total':line['is_pot_total'],
                        'is_dental':line['is_dental'],
                        'is_grossup':line['is_grossup'],
                        'is_external':line['is_external'],
                        'is_npwp':line['is_npwp'],
                        'gf': line['guarantee_fee'],
                        'npwp':line['npwp'],
                        'company_id':company_id,
                        'year':year,
                        'month':month
                    })
                return
            for d in doctor:
                d.compute_bruto()
            
            data.update({'status' : 'success', 'message' : 'Compute doctor fee successfully'})
        except:
            data.update({'status' : 'failed', 'message' : format_exc()})
        
        return request.make_response(json(data),[('Content-Type', 'application/json'),('Access-Control-Allow-Origin', '*')])
