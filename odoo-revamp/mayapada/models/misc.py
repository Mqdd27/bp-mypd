import odoo
import re
import requests
import json
import logging
import sys
import base64
import threading

import werkzeug.urls
import werkzeug.utils
from werkzeug.exceptions import BadRequest

try:
    import ujson as JSON
except:
    import json as JSON

from . import sync
from threading import Thread
from io import StringIO
from jinja2 import Template

# from odoo import models, fields, api, tools, exceptions,_
from odoo import http, models, fields, api, tools, exceptions, _
from odoo.exceptions import AccessDenied, UserError
from odoo.tools.misc import ustr

from odoo.http import request
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.web.controllers.main import ensure_db, Session, Home
from odoo.addons.auth_signup.models.res_partner import SignupError, now
from odoo.addons.base.models.ir_mail_server import MailDeliveryException
from odoo.addons.web.controllers.utils import _get_login_redirect_url, is_user_internal
from odoo.tools.misc import clean_context, split_every
from odoo import _, api, exceptions, fields, models, tools, registry, SUPERUSER_ID, Command


from odoo.osv import expression

from requests.utils import requote_uri
from dateutil.relativedelta import relativedelta
from ast import literal_eval
from werkzeug import urls
_logger = logging.getLogger(__name__)


SIGN_UP_REQUEST_PARAMS = {'db', 'login', 'debug', 'token', 'message', 'error', 'scope', 'mode',
                          'redirect', 'redirect_hostname', 'email', 'name', 'partner_id',
                          'password', 'confirm_password', 'city', 'country_id', 'lang', 'signup_email'}
LOGIN_SUCCESSFUL_PARAMS = set()



# class IrModel(models.Model):
    # _inherit = 'ir.model'
    # name = fields.Char(string='Model Description', translate=False, required=True)



#----------------------------------------------------------
# Odoo Web web Controllers
#----------------------------------------------------------
class WebLogin(AuthSignupHome):

    def _login_redirect(self, uid, redirect=None):
        return _get_login_redirect_url(uid, redirect)


    def list_providers_custom(self):
        try:
            providers = request.env['auth.oauth.provider'].sudo().search_read([('enabled', '=', True)])
        except Exception:
            providers = []
        for provider in providers:
            user_email = request.env.user.email
            # return_url = request.httprequest.url_root + 'auth_oauth/signin'
            custom_url = request.env['ir.config_parameter'].sudo().get_param('custom.base.url')
            # return_url = "https://mhns-erp.ad.mayapadahospital.com/" + 'auth_oauth/signin'
            return_url = str(custom_url) + 'auth_oauth/signin'
            state = self.get_state(provider)
            params = dict(
                response_type='token',
                client_id=provider['client_id'],
                redirect_uri=return_url,
                scope=provider['scope'],
                state=json.dumps(state),
                # nonce=base64.urlsafe_b64encode(os.urandom(16)),
            )
            provider['auth_link'] = "%s?%s" % (provider['auth_endpoint'], werkzeug.urls.url_encode(params))
        return providers


    @http.route('/web/login', type='http', auth="none")
    def web_login(self, redirect=None, **kw):
    
        from datetime import datetime
        ensure_db()

        request.params['login_success'] = False
        if request.httprequest.method == 'GET' and redirect and request.session.uid:
            return request.redirect(redirect)
        
        # simulate hybrid auth=user/auth=public, despite using auth=none to be able
        # to redirect users when no db is selected - cfr ensure_db()
        if request.env.uid is None:
            if request.session.uid is None:
                # no user -> auth=public with specific website public user
                request.env["ir.http"]._auth_method_public()
            else:
                # auth=user
                request.update_env(user=request.session.uid)


        request_uid = request.env.uid 
        if not request_uid:
            request_uid = odoo.SUPERUSER_ID

        values = {k: v for k, v in request.params.items() if k in SIGN_UP_REQUEST_PARAMS}
        try:
            values['databases'] = http.db_list()
        except odoo.exceptions.AccessDenied:
            values['databases'] = None

        if request.httprequest.method == 'POST':
            user_login = request.env['res.users'].sudo().search([('login','=', request.params['login'])])
            # open('/opt/odoo16/logs/log_login.log','a+').write('\nuser_id: ' + str(user_login.id))
            
            if user_login:
                open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str('000'))
                if user_login.login_attempts >= 3 and (datetime.now() - (user_login.last_login_attempt)).seconds < 300:
                    open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str('011'))
                    values['error'] = _("Too many login attempts. Please try again after 5 minutes.")
                else:

                    try:    
                        # open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str('010'))
                        old_uid = request_uid
                        # define now datetime
                        now = datetime.now()
                        now_formatted = now.strftime("%Y-%m-%d %H:%M:%S")

                        # open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str('110'))
                        uid = request.session.authenticate(request.session.db, request.params['login'], request.params['password'])
                        # open('/opt/odoo16/logs/log_login.log','a+').write('\nuid: ' + str(uid))
                        # open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str('111'))
                        # open('/opt/odoo16/logs/log_login.log','a+').write('\nuid: ' + str(uid))

                        request.params['login_success'] = True
                        user = request.env['res.users'].sudo().search([('id','=',uid)])
                        # open('/opt/odoo16/logs/log_login.log','a+').write('\nuid: ' + str(user))
                        # open('/opt/odoo16/logs/log_login.log','a+').write('\nuid: ' + str(user.login))
                        # user.write({'login_attempts': 0, 'last_login_attempt':False})
                        user_login.login_attempts = 0 
                        user_login.last_login_attempt = False
                        # open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str('222'))

                        if user:
                            password_write_date = user.password_write_date
                            # open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str(password_write_date))
                            password_expired = (password_write_date + relativedelta(months=3))
                            # open('/opt/odoo16/logs/log_login.log','a+').write('\npassword expired: ' + str(password_expired))

                            # open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str(now.date()))
                            open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str('3333'))

                            if now.date() > password_expired.date():
                                open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str('4444'))
                                values['error'] = _("Your password expired please submit reset request.")
                                return request.redirect(requote_uri("/web/reset_request?login="+str(user.login) + '&db=' + str(request.session.db) ))
                                # return http.redirect_with_hash(requote_uri("https://erp.ad.mayapadahospital.com/web/reset_request?login="+str(user.login) + '&db=' + str(request.session.db) ))

                        # if not redirect:
                            # redirect = '/web'
                        # return http.redirect_with_hash(redirect)
                        # open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str('555'))
                        return request.redirect(self._login_redirect(uid, redirect=redirect))

                    except odoo.exceptions.AccessDenied as e:
                        
                        # open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str('666'))
                        if user_login.login_attempts >= 3:
                            # open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str('777'))
                            user_login.login_attempts=  0
                            user_login.last_login_attempt = False
                            user_login.login_attempts = user_login.login_attempts + 1
                        else:
                            # open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str('888'))
                            user_login.login_attempts = user_login.login_attempts + 1
                            user_login.last_login_attempt = fields.Datetime.now()

                        if e.args == odoo.exceptions.AccessDenied().args:
                            values['error'] = _("Wrong login/password")
                        else:
                            values['error'] = e.args[0]
                            
            else:       
                #request.env.uid = old_uid
                # open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str('999'))
                values['error'] = _("Wrong login/password")

        # get message_error
        oauth_error = request.params.get('oauth_error')

        if oauth_error == '3':
            values['error'] = "Login SSO hanya dapat digunakan untuk user yang sudah memiliki akun Odoo, silahkan hubungi IT untuk melakukan request akses Odoo."

        values['providers'] = self.list_providers_custom()
        values['redirect'] =  redirect

        # open('/opt/odoo16/logs/log_login.log','a+').write('\ncurrent: ' + str('xxx'))
        response = request.render('mayapada.login', values)
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response

    

    @http.route('/web/reset_request', type='http', auth='public', website=True)
    def web_auth_reset_request(self, *args, **kw):
        qcontext = self.get_auth_signup_qcontext()
        # open('/opt/odoo16/log/log_qcontext.log', 'a+').write('\n' + str(qcontext))

        if qcontext.get('login'):
            users = request.env['res.users'].sudo().search([('login', '=', qcontext.get('login'))], limit=1)
            if users:
                qcontext['name'] = users.name
                if 'error' not in qcontext and request.httprequest.method == 'POST':
                    try:

                        uid = request.session.authenticate(request.session.db, request.params['login'], request.params['password'])
                        if uid is not False:
                            login = qcontext.get('login')
                            assert login, "No login provided."
                            _logger.info("Password reset attempt for <%s> by user <%s> from %s",login, request.env.user.login, request.httprequest.remote_addr)
                            request.env['res.users'].sudo().reset_password(login)
                            qcontext['message'] = _("An email has been sent with link token to reset your password")
                            # return http.redirect_with_hash('http://mhbd.erp.mayapadahospital.com')
                            # return http.redirect_with_hash('/web')
                        else:
                            qcontext['error'] = _("Wrong old password")
                    except SignupError:
                        qcontext['error'] = _("Could not reset your password")
                        _logger.exception('error when resetting password')
                    except Exception as e:
                        qcontext['error'] = e.message or e.name

        return request.render('mayapada.reset_request', qcontext)


    def get_auth_signup_qcontext(self):
        """ Shared helper returning the rendering context for signup and reset password """
        qcontext = {k: v for (k, v) in request.params.items() if k in SIGN_UP_REQUEST_PARAMS}
        qcontext.update(self.get_auth_signup_config())
        if not qcontext.get('token') and request.session.get('auth_signup_token'):
            qcontext['token'] = request.session.get('auth_signup_token')
        if qcontext.get('token'):
            try:
                # retrieve the user info (name, login or email) corresponding to a signup token
                token_infos = request.env['res.partner'].sudo().signup_retrieve_info(qcontext.get('token'))
                for k, v in token_infos.items():
                    qcontext.setdefault(k, v)
            except:
                qcontext['error'] = _("Invalid signup token")
                qcontext['invalid_token'] = True
        return qcontext
        
    @http.route('/web/reset_password', type='http', auth='public', website=True)
    def web_auth_reset_password(self, *args, **kw):
        qcontext = self.get_auth_signup_qcontext()

        if qcontext.get('login'):
             user = request.env['res.users'].sudo().search([('login', '=', qcontext.get('login'))], limit=1)
             if user:
                 qcontext['company_ids'] = user.company_ids
        # qcontext['company_ids'] = request.env.companys

        open('/opt/odoo16/logs/dudi.log', 'a+').write('\n' + str("masuk web_auth_reset_password"))

        if not qcontext.get('token') and not qcontext.get('reset_password_enabled'):
            raise werkzeug.exceptions.NotFound()

        if 'error' not in qcontext and request.httprequest.method == 'POST':
            try:
                if qcontext.get('token'):
                    from werkzeug.urls import url_encode
                    self.do_signup(qcontext)
                    # return self.web_login(*args, **kw)
                    # return http.redirect_with_hash('http://mhbd.erp.mayapadahospital.com')
                    return request.redirect('/web/login?%s' % url_encode({'login': qcontext.get('login'), 'redirect': '/web'}))
                else:
                    login = qcontext.get('login')
                    assert login, "No login provided."
                    _logger.info("Password reset attempt for <%s> by user <%s> from %s",login, request.env.user.login, request.httprequest.remote_addr)
                    request.env['res.users'].sudo().reset_password(login)
                    qcontext['message'] = _("An email has been sent with credentials to reset your password")
                    # return http.redirect_with_hash('http://mhbd.erp.mayapadahospital.com')
                    # return http.redirect_with_hash(request.params.get('direct'))
                    return request.redirect('/web/login?%s' % url_encode({'login': qcontext.get('login'), 'redirect': '/web'}))
            except SignupError:
                qcontext['error'] = _("Could not reset your password")
                _logger.exception('error when resetting password')
            except Exception as e:
                qcontext['error'] = e

        # if qcontext.get('token'):
        #     response = request.render('mayapada.reset_password', qcontext)
        # else:
        #     response = request.render('mayapada.reset_request', qcontext)

        response = request.render('mayapada.reset_password', qcontext)
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response
        # return request.render('mayapada.reset_password', qcontext)







class PasswordSecuritySession(Session):

    @http.route()
    def change_password(self, fields):
        new_password = operator.itemgetter('new_password')(
            dict(map(operator.itemgetter('name', 'value'), fields))
        )
        user_id = request.env.user
        user_id._check_password(new_password)
        return super(PasswordSecuritySession, self).change_password(fields)



#class Message(models.Model):
#    _inherit = 'mail.message'

#    def _partner_ids_domain_new_message(self):
#        return expression.OR([
#            [('patient', '=', False)],
            
#        ])


#    partner_ids = fields.Many2many('res.partner', string='Recipientsssssssssssss', domain=_partner_ids_domain_new_message)



class MailMessage(models.Model):
    _inherit = 'mail.message'

    @api.model
    def search_read(self, domain, fields=None, offset=0, limit=None, order=None):
        # Check if partner_ids is in the fields requested
        if fields and 'partner_ids' in fields:
            # Get partner IDs where is_user is True
            user_partners = self.env['res.partner'].search([('is_user', '=', True)])
            partner_ids = user_partners.ids
            
            # Modify the domain to include only these partner_ids
            domain = [
                  # Use OR to keep the existing filters intact
                ('partner_ids', 'in', partner_ids),
                  # Allow messages without partners
            ]

        # Call the super method with the modified domain
        return super(MailMessage, self).search_read(domain, fields, offset=offset, limit=limit, order=order)




class Message(models.TransientModel):
    _inherit = 'mail.compose.message'

    def _partner_ids_domain_new(self):
        return expression.OR([
            [('patient', '=', False)],
            
        ])

    partner_ids = fields.Many2many(
        'res.partner', 'mail_compose_message_res_partner_rel',
        'wizard_id', 'partner_id', 'Additional Contacts',
        domain=_partner_ids_domain_new)


class ResUsers(models.Model):
    _inherit = 'res.users'

    position_id = fields.Many2one('res.position', string="Job Position")
    second_position_id = fields.Many2one('res.position', string="Second Job Position")
    # cost_center = fields.Many2one('cost.center', string="Cost Center")
    # department = fields.Many2one('hr.department',string = 'Department', domain=[('is_user', '=', True)])
    department_id = fields.Many2one('hr.department', string='Department HR', store=True, domain=[('is_user', '=', True)])
    sync_id = sync.id
    sync_date = sync.date
    sync_type = sync.type
    
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    sync_consol_sent = sync.consol_sent
    sync_consol_response_status = sync.consol_response_status
    sync_consol_response = sync.consol_response
    # user_id_cek = fields.Char(string="User ID")
    # company_name = fields.Char(string="Company Name")

    analytic_ids = fields.Many2many('account.analytic.account','res_user_analytic_rel', 'user_id','analytic_id', string="Analytic Account")
    cost_center_ids = fields.Many2many('cost.center.master','res_user_cost_center_master_rel', 'user_id','cost_center_id', string="Cost Center")
    sign = fields.Binary(string="Signature", readonly=False)
    product_ids = fields.Many2many('product.template', string="Product Domain")
    location_ids = fields.Many2many('stock.location', string="Location Domain")
    # category_ids = fields.Many2many('product.category', string="Product Category Domain")
    category2_ids = fields.Many2many('product.category', string="Product Category Domain")
    operation_ids = fields.Many2many('stock.picking.type', string="Stok Operation Type")
    password_consol = fields.Char(string="PC", readonly=True, index=True)
    token_consol = fields.Char(string="TC", readonly=True, index=True)
    cookies = fields.Char(string="CK", readonly=True, index=True)
    ar_pic_phone = fields.Char(string="AR Phone (Extension)")

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)
    emp_code = fields.Char(string="Employee No *", required=True)
    name = fields.Char(string="Name *", required=True)
    login = fields.Char(string="Email Address *", required=True)
    active = fields.Boolean(default=True, tracking=True)

    is_user_it = fields.Boolean(string="Is User IT?")
    is_doctor_rate_approval = fields.Boolean(string="Is Doctor Rate Approval?")
    
    password_write_date = fields.Datetime(
        'Last password update',
        default=fields.Datetime.now,
        readonly=True,
    )
    login_attempts = fields.Integer(string="Login Attempts", default=0)
    last_login_attempt = fields.Datetime(string="Last Login Attempt")
    state = fields.Selection(compute='_compute_state', string='Status', selection=[('new', 'Never Connected'), ('active', 'Confirmed')])
    
    password_history_ids = fields.One2many('password.history', 'user_id', string="Password History")




    # @api.model
    def _auth_oauth_signin(self, provider, validation, params):
        oauth_uid = validation['user_id']
        try:
            oauth_user = self.search([("oauth_uid", "=", oauth_uid), ('oauth_provider_id', '=', provider)])
            if not oauth_user:
                raise AccessDenied()
            assert len(oauth_user) == 1
            oauth_user.write({'oauth_access_token': params['access_token']})
            return oauth_user.login
        except AccessDenied as access_denied_exception:
            if self.env.context.get('no_user_creation'):
                return None
            state = json.loads(params['state'])
            token = state.get('t')
            values = self._generate_signup_values(provider, validation, params)
            try:
                existing_user = self.search([("login", "=", values['email']), ("active", "=", True)])
                if not existing_user:
                    return
                else:
                    existing_user.oauth_provider_id = values['oauth_provider_id']
                    existing_user.oauth_uid = values['oauth_uid']
                    existing_user.oauth_access_token = values['oauth_access_token']
                    return (values.get('login'), values.get('password'))
            except (SignupError, UserError):
                raise access_denied_exception

    # @api.multi
    def _compute_state(self):
        for user in self:
            user.state = 'active' if user.login_date else 'new'

    # @api.model
    def signup(self, values, token=None):
        """ signup a user, to either:
            - create a new user (no token), or
            - create a user for a partner (with token, but no user for partner), or
            - change the password of a user (with token, and existing user).
            :param values: a dictionary with field values that are written on user
            :param token: signup token (optional)
            :return: (dbname, login, password) for the signed up user
        """
        user_id = request.env.user
        # user_id._check_password(values.get('password'))

        if token:
            # signup with a token: find the corresponding partner id
            partner = self.env['res.partner']._signup_retrieve_partner(token, check_validity=True, raise_exception=True)
            # invalidate signup token
            partner.write({'signup_token': False, 'signup_type': False, 'signup_expiration': False})
            partner_user = partner.user_ids and partner.user_ids[0] or False

            # avoid overwriting existing (presumably correct) values with geolocation data
            if partner.country_id or partner.zip or partner.city:
                values.pop('city', None)
                values.pop('country_id', None)
            if partner.lang:
                values.pop('lang', None)

            if partner_user:
                # user exists, modify it according to values
                values.pop('login', None)
                values.pop('name', None)
                partner_user.write(values)
                
                if values.get('password'):
                    open('/opt/odoo16/logs/log_partner_xx.log','a+').write('xxxxx: ' + str(values.get('password')))
                    # partner_user.write({'password': values.get('password'), 'password_consol': values.get('password')})
                    partner_user.change_password_api_consol(user_id=partner_user, new_passwd=values.get('password'))

                # return (self.env.cr.dbname, partner_user.login, values.get('password'))
                return (partner_user.login, values.get('password'))
            else:
                # user does not exist: sign up invited user
                values.update({
                    'name': partner.name,
                    'partner_id': partner.id,
                    'email': values.get('email') or values.get('login'),
                })
                if partner.company_id:
                    values['company_id'] = partner.company_id.id
                    values['company_ids'] = [(6, 0, [partner.company_id.id])]
                self._signup_create_user(values)
        else:
            # no token, sign up an external user
            values['email'] = values.get('email') or values.get('login')
            self._signup_create_user(values)

        return (self.env.cr.dbname, values.get('login'), values.get('password'))

    # @api.model
    def _signup_create_user(self, values):
        """ create a new user from the template user """
        IrConfigParam = self.env['ir.config_parameter']
        template_user_id = literal_eval(IrConfigParam.get_param('auth_signup.template_user_id', 'False'))
        template_user = self.browse(template_user_id)
        assert template_user.exists(), 'Signup: invalid template user'

        # check that uninvited users may sign up
        if 'partner_id' not in values:
            if not literal_eval(IrConfigParam.get_param('auth_signup.allow_uninvited', 'False')):
                raise SignupError('Signup is not allowed for uninvited users')

        assert values.get('login'), "Signup: no login given for new user"
        assert values.get('partner_id') or values.get('name'), "Signup: no name or partner given for new user"

        # create a copy of the template user (attached to a specific partner_id if given)
        values['active'] = True
        try:
            with self.env.cr.savepoint():
                return template_user.with_context(no_reset_password=True).copy(values)
        except Exception as e:
            # copy may failed if asked login is not available
            raise SignupError(ustr(e))

    def reset_password(self, login):
        """ retrieve the user corresponding to login (login or email),
            and reset their password
        """
        users = self.search([('login', '=', login)])
        if not users:
            users = self.search([('email', '=', login)])
        if len(users) != 1:
            raise Exception(_('An email has been sent with credentials to reset your password'))
        return users.action_reset_password()


    # @api.multi
    def action_reset_password(self):
        """ create signup token for each user, and send their signup url by email """
        # prepare reset password signup
        create_mode = bool(self.env.context.get('create_user'))

        # no time limit for initial invitation, only for reset password
        expiration = False if create_mode else now(days=+1)

        self.mapped('partner_id').signup_prepare(signup_type="reset", expiration=expiration)

        # send email to users with their signup url
        template = False

        # update base url before send link
        query_update_web_base_url = """
            update ir_config_parameter set value = 'https://erp.ad.mayapadahospital.com' where key = 'web.base.url'
            """
        self.env.cr.execute(query_update_web_base_url)
        self._cr.commit()

        param_values = {
            'emp_code': self.emp_code,
            'name': self.name,
            'position': self.position_id.name,
            'department': self.department_id.name,
            'login': self.login,
            'password': self.company_id.password_default,
            'company': self.company_id.name,
            'odoo_url_public': self.company_id.odoo_url_public,
            'odoo_url_local': self.company_id.odoo_url_local,
            'signup_url': self.signup_url
        }
        
        if create_mode:
            try:
                template = self.env.ref('mayapada.set_password_email', raise_if_not_found=False)
                xml_template = """
                    <style type="text/css">
                        * { font-size: 14px; }
                        .tbl-info{ display:table; width:100%; }
                        .tbl-header{ display:table-header-group;}
                        .tbl-body{ display:table-row-group;}
                        .tbl-row{ display:table-row; } 
                        .tbl-cell{ display:table-cell;}
                        .tbl-hide{}

                        @media screen and (max-device-width: 549px), screen and (max-width: 549px){
                            .tbl-info{ display:block; width:100%; }
                            .tbl-info tr, .tbl-info td{ display:block; width:100%; }
                            .tbl-header{ display:block;}
                            .tbl-body{ display:block;}
                            .tbl-row{ display:block; border-bottom:solid 1px #666; padding:8px 0; } 
                            .tbl-cell{ display:block; }
                            .tbl-info td.tbl-hide{ display:none; }
                        }

                        </style>

                        <div style="padding:0px;max-width:600px;margin:auto;background: #FFFFFF repeat top /100%;color:#555555">
                            <table cellspacing="0" cellpadding="0" style="width:600px;border-collapse:collapse;background:inherit;color:inherit">
                                <tbody><tr>
                                    <td valign="center" width="300" style="padding:10px 10px 10px 5px;font-size: 12px">
                                        <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAABGIAAAFJCAYAAADQYIvNAAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAAyhpVFh0WE1MOmNvbS5hZG9iZS54bXAAAAAAADw/eHBhY2tldCBiZWdpbj0i77u/IiBpZD0iVzVNME1wQ2VoaUh6cmVTek5UY3prYzlkIj8+IDx4OnhtcG1ldGEgeG1sbnM6eD0iYWRvYmU6bnM6bWV0YS8iIHg6eG1wdGs9IkFkb2JlIFhNUCBDb3JlIDUuNi1jMTQ1IDc5LjE2MzQ5OSwgMjAxOC8wOC8xMy0xNjo0MDoyMiAgICAgICAgIj4gPHJkZjpSREYgeG1sbnM6cmRmPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5LzAyLzIyLXJkZi1zeW50YXgtbnMjIj4gPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9IiIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bWxuczp4bXBNTT0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL21tLyIgeG1sbnM6c3RSZWY9Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9zVHlwZS9SZXNvdXJjZVJlZiMiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIENDIDIwMTkgKE1hY2ludG9zaCkiIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6OTM5RTlDNzM5QkE3MTFFOThFOTdDQzFENkUwRDQzQzUiIHhtcE1NOkRvY3VtZW50SUQ9InhtcC5kaWQ6OTM5RTlDNzQ5QkE3MTFFOThFOTdDQzFENkUwRDQzQzUiPiA8eG1wTU06RGVyaXZlZEZyb20gc3RSZWY6aW5zdGFuY2VJRD0ieG1wLmlpZDo5MzlFOUM3MTlCQTcxMUU5OEU5N0NDMUQ2RTBENDNDNSIgc3RSZWY6ZG9jdW1lbnRJRD0ieG1wLmRpZDo5MzlFOUM3MjlCQTcxMUU5OEU5N0NDMUQ2RTBENDNDNSIvPiA8L3JkZjpEZXNjcmlwdGlvbj4gPC9yZGY6UkRGPiA8L3g6eG1wbWV0YT4gPD94cGFja2V0IGVuZD0iciI/PujlQtQAAUiHSURBVHja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" style="padding: 0px; margin: 0px; height: auto; width: 220px;" alt="Mayapada Healthcare">                            
                                </td>
                                </tr></tbody>
                            </table>
                        </div>
                        <div style="padding:0px;max-width:600px;margin:auto;background: #FFFFFF repeat top /100%;color:#555555">
                            <p>Dear <strong>{{param_values.name}}</strong>,</p>
                            <p>Your account has been registered in Mayapada Healthcare ERP System, your account details:</p>

                            <p>
                                <table class="tbl-info" width="100%" border="0" cellpadding="3" cellspacing="0">
                                    <tr>
                                        <td width="30%"><strong>Employee No.</strong></td>
                                        <td class="tbl-hide" width="2%"> : </td>
                                        <td width="68%">{{ param_values.emp_code }}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Employee Name</strong></td>
                                        <td class="tbl-hide"> : </td>
                                        <td>{{param_values.name}}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Job Position</strong></td>
                                        <td class="tbl-hide"> : </td>
                                        <td>{{param_values.position}}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Department</strong></td>
                                        <td class="tbl-hide"> : </td>
                                        <td>{{param_values.department}}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Login</strong></td>
                                        <td class="tbl-hide"> : </td>
                                        <td>{{param_values.login}}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Default Password</strong></td>
                                        <td class="tbl-hide"> : </td>
                                        <td>{{param_values.password}}</td>
                                    </tr>
                                </table>
                            </p>
                            <p>&nbsp;</p>
                            <p>You can access odoo link via  address below:</p>
                            <p>
                                <div class="tbl-info">
                                    <div class="tbl-header">
                                        <div class="tbl-row">
                                            <div class="tbl-cell"><strong>Site</strong></div>
                                            <div class="tbl-cell"><strong>Public Access</strong></div>
                                            <div class="tbl-cell"><strong>Internal Access</strong></div>
                                        </div>
                                    </div>
                                    <div class="tbl-body">
                                      """

                for company in self.company_ids:
                    xml_template = xml_template + """
                         <div class="tbl-row">
                                            <div class="tbl-cell">"""+company.name+"""</div>
                                            <div class="tbl-cell">"""+company.odoo_url_public+"""</div>
                                            <div class="tbl-cell">"""+company.odoo_url_local+"""</div>
                                        </div>
                        """           
                           
                xml_template = xml_template + """
                                    </div>
                                </div>
                            <p>
                            <p>Please make sure you can immediately reset your default account password by accessing the following link:</p>
                            <p>
                                <a href="{{param_values.signup_url}}" style="padding: 5px 10px; line-height: 18px; color: #FFFFFF; border-color:#3965a7; text-decoration: none; display: inline-block; margin-bottom: 0px; font-weight: 400; text-align: center; vertical-align: middle; cursor: pointer; white-space: nowrap; background-image: none; background-color: #3965a7; border: 1px solid #3965a7; border-radius:3px">Change password</a>
                            </p>
                            <p>&nbsp;</p>
                            <p>***</p>
                            <p>&nbsp;</p>
                            <p>
                                Kind Regards, <br>
                                IT Mayapada Healthcare Teams. <br>
                            </p>
                            
                        </div>
                        <div style="padding:0px;max-width:600px;margin:auto; margin-top: 10px; background: #fff repeat top /100%;color:#555555">
                            <p style="margin-top: 10px;">
                                <strong>Sent by Mayapada Healthcare using <a href="https://erp.ad.mayapadahospital.com" style="text-decoration:none; color: #3965a7;">Odoo</a></strong>
                            </p>
                        </div>
                    """
                
                rendered_xml = Template(xml_template)
                template.body_html = rendered_xml.render(param_values=param_values)

                
            except ValueError:
                pass
        if not template:
            template = self.env.ref('mayapada.reset_password_email')
            xml_template = """
                    <div style="padding:0px;max-width:600px;margin:auto;background: #FFFFFF repeat top /100%;color:#555555">
                    <table cellspacing="0" cellpadding="0" style="width:600px;border-collapse:collapse;background:inherit;color:inherit">
                        <tbody><tr>
                            <td valign="center" width="300" style="padding:10px 10px 10px 5px;font-size: 12px">
                                <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAABGIAAAFJCAYAAADQYIvNAAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAAyhpVFh0WE1MOmNvbS5hZG9iZS54bXAAAAAAADw/eHBhY2tldCBiZWdpbj0i77u/IiBpZD0iVzVNME1wQ2VoaUh6cmVTek5UY3prYzlkIj8+IDx4OnhtcG1ldGEgeG1sbnM6eD0iYWRvYmU6bnM6bWV0YS8iIHg6eG1wdGs9IkFkb2JlIFhNUCBDb3JlIDUuNi1jMTQ1IDc5LjE2MzQ5OSwgMjAxOC8wOC8xMy0xNjo0MDoyMiAgICAgICAgIj4gPHJkZjpSREYgeG1sbnM6cmRmPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5LzAyLzIyLXJkZi1zeW50YXgtbnMjIj4gPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9IiIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bWxuczp4bXBNTT0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL21tLyIgeG1sbnM6c3RSZWY9Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9zVHlwZS9SZXNvdXJjZVJlZiMiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIENDIDIwMTkgKE1hY2ludG9zaCkiIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6OTM5RTlDNzM5QkE3MTFFOThFOTdDQzFENkUwRDQzQzUiIHhtcE1NOkRvY3VtZW50SUQ9InhtcC5kaWQ6OTM5RTlDNzQ5QkE3MTFFOThFOTdDQzFENkUwRDQzQzUiPiA8eG1wTU06RGVyaXZlZEZyb20gc3RSZWY6aW5zdGFuY2VJRD0ieG1wLmlpZDo5MzlFOUM3MTlCQTcxMUU5OEU5N0NDMUQ2RTBENDNDNSIgc3RSZWY6ZG9jdW1lbnRJRD0ieG1wLmRpZDo5MzlFOUM3MjlCQTcxMUU5OEU5N0NDMUQ2RTBENDNDNSIvPiA8L3JkZjpEZXNjcmlwdGlvbj4gPC9yZGY6UkRGPiA8L3g6eG1wbWV0YT4gPD94cGFja2V0IGVuZD0iciI/PujlQtQAAUiHSURBVHja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" style="padding: 0px; margin: 0px; height: auto; width: 220px;" alt="Mayapada Healthcare">                            
                            </td>
                        </tr></tbody>
                    </table>
                    </div>
                    <div style="padding:0px;max-width:600px;margin:auto;background: #FFFFFF repeat top /100%;color:#555555">
                        <p>Dear <strong>{{param_values.name}}</strong>,</p>
                        <p>Please make sure you can immediately reset your default account password by accessing the following link:</p>
                        <p>
                            <a href="{{param_values.signup_url}}" style="padding: 5px 10px; line-height: 18px; color: #FFFFFF; border-color:#3965a7; text-decoration: none; display: inline-block; margin-bottom: 0px; font-weight: 400; text-align: center; vertical-align: middle; cursor: pointer; white-space: nowrap; background-image: none; background-color: #3965a7; border: 1px solid #3965a7; border-radius:3px">Change password</a>
                        </p>
                        <p>&nbsp;</p>
                        <p>***</p>
                        <p>&nbsp;</p>
                        <p>
                            Kind Regards, <br>
                            IT Mayapada Healthcare Teams. <br>
                        </p>
                        
                    </div>
                    <div style="padding:0px;max-width:600px;margin:auto; margin-top: 10px; background: #fff repeat top /100%;color:#555555">
                        <p style="margin-top: 10px;">
                            <strong>Sent by Mayapada Healthcare using <a href="https://erp.ad.mayapadahospital.com" style="text-decoration:none; color: #3965a7;">Odoo</a></strong>
                        </p>
                    </div>
                """
            rendered_xml = Template(xml_template)
            template.body_html = rendered_xml.render(param_values=param_values)

        assert template._name == 'mail.template'

        template_values = {
            'email_to': self.login,
            'email_cc': 'it.odoo@mayapadahospital.com',
            'auto_delete': False,
            'partner_to': False,
            'scheduled_date': False,
        }
        template.write(template_values)

        for user in self:
            if not user.email:
                raise UserError(_("Cannot send email: user %s has no email address.") % user.name)
            with self.env.cr.savepoint():
                template.with_context(lang=user.lang).send_mail(user.id, force_send=True, raise_exception=True)
            _logger.info("Password reset email sent for user <%s> to <%s>", user.login, user.email)



    def _get_explicit_groups(self, user):
        """
        Ambil explicit groups (yang dipilih user), tanpa implied groups
        """
        implied = set()
        for g in user.groups_id:
            implied |= set(g.implied_ids.ids)
        return set(user.groups_id.ids) - implied



    @api.model
    def create(self, vals):
        # from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
        # from datetime import datetime
        # import os

        # # define now datetime
        # now = datetime.now()
        # now_formatted = now.strftime("%Y-%m-%d %H:%M:%S")

        # # define python timezone
        # import pytz
        # local = pytz.timezone('Asia/Jakarta')
        # log_date = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y%m%d")
        # log_year = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y")
        # log_month = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        # log_day = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        # #log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local),"%H%M%S.%f")
        # log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        # log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'res.users' + '/'
        # log_name = log_date + '_' + 'create' + '_' + 'res.users'
        # log_file = log_dir + log_name + '.log'

        # log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # # create dir if not exists
        # if not os.path.exists(log_dir):
        #     os.makedirs(log_dir)
        # os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        # message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        # message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        # open(log_file, 'a').write(message_log)
        result = super(ResUsers, self).create(vals)

        try:
            log_lines = []
            log_lines.append(f"User ID     : {result.id}")
            log_lines.append(f"Created by  : {self.env.user.login}")
            log_lines.append(f"Datetime    : {fields.Datetime.now()}")
            log_lines.append("Data created:")

            # ======================
            # 1. Field biasa (loop vals seperti codingan awal)
            # ======================
            for field, value in vals.items():
                if field in ['groups_id', 'password_consol']:
                    continue  # skip groups, akan dicatat terpisah
                log_lines.append(f" - {field}: {value}")

            # ======================
            # 2. Field groups (pisah sendiri, rapi)
            # ======================
            explicit_groups = self._get_explicit_groups(result)
            groups = self.env['res.groups'].browse(explicit_groups)
            group_lines = ", ".join(f"{g.category_id.name or '-'} / {g.name}" for g in groups) or "-"
            log_lines.append(f" - groups_id (explicit): {group_lines}")

            # ======================
            # 3. Simpan ke log
            # ======================
            self.env['res.users.log'].sudo().create({
                'user_id': result.id,
                'changed_by': self.env.user.id,
                'change_date': fields.Datetime.now(),
                'changes': "\n".join(log_lines),
            })

        except Exception as e:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write(
                f'\nError log res.users.log (create): {str(e)}'
            )



        # result.send_api_consol()
        if result.trigger_create == False:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger create res user")
            result.send_api_consol_company()
            result.send_api_consol_group_write()
        partner_id = result.partner_id.id
        # if result.company_id.sync_consol_type == 'main':
            # result.send_res_partner_id()
        # log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        # message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        # message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " +str(result.id)

        # open(log_file, 'a').write(message_log)
        return result

    # @api.multi
    def send_res_partner_id(self):
        partner_id = self.partner_id.id
        partner_name = self.partner_id.name
        partner_create_uid = self.partner_id.create_uid.id
        partner_write_uid = self.partner_id.write_uid.id
        partner_create_date = self.partner_id.create_date

        res_partner_false_id = self.env['res.partner'].search([('id','>',partner_id),('name','=', partner_name),('create_uid', '=', partner_create_uid),('write_uid','=', partner_write_uid),('create_date','>=', partner_create_date)], limit=1)
        
        query = """
                update res_partner set active='false', sync_type = null, sync_consol_id_unit = null WHERE id > '{partner_id}' and name='{partner_name}' AND create_uid = '{partner_create_uid}' and write_uid ='{partner_write_uid}' and create_date>='{partner_create_date}'
                """.format(partner_id=partner_id, partner_name=partner_name, partner_create_uid=partner_create_uid, partner_write_uid=partner_write_uid, partner_create_date=partner_create_date)
        self.env.cr.execute(query)
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        for record in self:
            consol_active = record.company_id.sync_consol_res_user
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            
            if consol_active:
                
                if consol_type == 'unit':
                    url = consol_url + "/internal_search_user/unit/search/res.partner"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'

                if consol_type == 'main':
                    url = consol_url + "/internal_search_user/main/search/res.partner"
                    consol_id_to = 'sync_consol_id_unit'
                    consol_id_from = 'sync_consol_id_main'

                if not record.env.user.token_consol:
                    # record.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    login_user = record.env.user.login
                    password_user = record.env.user.password_consol
                    record.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                
                headers = {}
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = {}
                body['csrf_token'] = record.env.user.token_consol
                values = {}
                lst = []
                values['sync_type'] = record.company_id.sync_type
                values[consol_id_from] = str(record.partner_id.id)
                values['name'] = str(record.name)
                values['inactive_id'] = str(res_partner_false_id.id)

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
                        if json_resp['data'][0]['id']:
                            response_id = json_resp['data'][0]['id']
                        # for d in json_resp['data']:
                        #     if 'id' in d:
                        #         response_id = d['id']
                        record.partner_id.sync_consol_id_unit = response_id
                    if json_resp['status'] == 'error':
                        # raise exceptions.ValidationError(_('Data Gagal Diedit'))
                        raise exceptions.ValidationError(_(json_resp['message']))
                    
                
                data_update = {
                    
                    'sync_consol_date': now,
                    'sync_consol_sent' : data_sent
                }

                super(ResUsers, self).write(data_update)

    # @api.multi
    def send_api_consol_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            for company_id in record.company_ids:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_res_user
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    # if self.env.user.id != 1:
                    #     raise exceptions.ValidationError(_('Create User Hanya Menggunakan Admin!!'))
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/create/res.users"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/create/res.users"
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
                    values_array = []
                    values['sync_type'] = str(company_id.sync_type)
                    values[consol_id_from] = record.id
                    values['name'] = record.name
                    values['emp_code'] = record.emp_code
                    values['display_name'] = record.name
                    values['login'] = record.login
                    # values['position_id'] = record.position_id.id
                    # values['department_id'] = record.department_id.id
                    values['trigger_create'] = True
                    if record.position_id.id == False:
                        values['position_id'] = record.position_id.id
                    else:
                        values['position_id'] = str(record.position_id.id)
                    if record.second_position_id.id == False:
                        values['second_position_id'] = record.second_position_id.id
                    else:
                        values['second_position_id'] = str(record.second_position_id.id)

                    if record.department_id.id == False:
                        values['department_id'] = record.department_id.id
                    else:
                        values['department_id'] = str(record.department_id.id)
                    if consol_type == 'unit':
                        sync_consol_id_main = str(self.env.user.login)
                        company_name = company_id.name
                        values['company_name'] = company_name
                        values['user_id_cek'] = sync_consol_id_main
                    if consol_type == 'main':
                        sync_consol_id_main = str(self.env.user.login)
                        company_name = company_id.name
                        values['company_name'] = company_name
                        values['user_id_cek'] = sync_consol_id_main
                    values_array.append(values)
                    body['values'] = json.dumps(values_array)

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


                    #raise UserError(_("json respon cek :  " + str(json_resp)))

                    if 'status' in json_resp:
                        if json_resp['status'] == 'success':
                            api_status = 'success'
                            data_sent = True
                            # if company_name == 'Mayapada Hospital Nusantara':
                            if company_name in ['Mayapada Hospital Nusantara', 'Mayapada Eye Centre', 'Mayapada Hospital Bogor','Mayapada Hospital Jakarta Timur']:
                                if json_resp['data']['id']:
                                    response_id = json_resp['data']['id']
                            else: 
                                if json_resp['data'][0]['id']:
                                    response_id = json_resp['data'][0]['id']
                        if json_resp['status'] == 'error':
                            # raise exceptions.ValidationError(_('Data Gagal Dibuat'))
                            raise exceptions.ValidationError(_(json_resp['message']))


                    data_update = {
                        consol_id_to : response_id,
                        # 'sync_consol_response': json_resp,
                        # 'sync_consol_response_status': api_status,
                        'sync_consol_date': now,
                        # 'sync_consol_sent' : data_sent,
                        'sync_consol_log': list_company
                        }

                    super(ResUsers, self).write(data_update)

    # @api.multi
    def write(self, vals):
        # from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
        # from datetime import datetime
        # import os

        # # define now datetime
        # now = datetime.now()
        # now_formatted = now.strftime("%Y-%m-%d %H:%M:%S")

        # # define python timezone
        # import pytz
        # local = pytz.timezone('Asia/Jakarta')
        # log_date = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y%m%d")
        # log_year = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y")
        # log_month = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        # log_day = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        # #log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local),"%H%M%S.%f")
        # log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        # log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'res.users' + '/'
        # log_name = log_date + '_' + 'write' + '_' + 'res.users'
        # log_file = log_dir + log_name + '.log'

        # log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # # create dir if not exists
        # if not os.path.exists(log_dir):
        #     os.makedirs(log_dir)
        # os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        # message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        # message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        # open(log_file, 'a').write(message_log)
        hitung = 0
        if self.id:
            query_count = """
                select count(*) from res_groups_users_rel 
                where uid = {self_id}
            """.format(self_id = self.id)
            self.env.cr.execute(query_count)
            count_check = self.env.cr.dictfetchall()
            if count_check:
                for line in count_check:
                    hitung = line['count']
                    open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "hitung sebelum " + str(hitung))
                    
        # for rec in self.groups_id:
        #     count += 1
        #     open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "countsebelum " + str(count))

        if vals.get('password'):
            self._check_password(vals['password'])
            vals['password_write_date'] = fields.Datetime.now()
        
        if not vals.get('is_user'):
            vals['is_user'] = True
        
        self = self.with_context(is_user=True)

        # Helper aman untuk semua tipe field
        def _fmt(val):
            if isinstance(val, models.BaseModel):
                if len(val) > 1:  # M2M / O2M
                    return ", ".join(val.mapped("display_name"))
                elif len(val) == 1:  # M2O
                    return val.display_name
                else:
                    return "-"
            return val


        # ======================
        # 1. Simpan nilai lama (explicit groups & field lain)
        # ======================
        old_values = {}
        for rec in self:
            old_explicit = self._get_explicit_groups(rec)
            old_fields = {
                field: rec[field]
                for field in vals.keys()
                if field in rec._fields and field not in ['groups_id', 'password_consol']
            }
            old_values[rec.id] = {
                **old_fields,
                'explicit_groups': old_explicit,
            }

        result = super(ResUsers, self).write(vals)
        count = 0

        for rec in self:
            lines = []
            lines.append(f"User ID     : {rec.id}")
            lines.append(f"User Name   : {rec.login or ''}")
            lines.append(f"Modified by : {self.env.user.login}")
            lines.append(f"Datetime    : {fields.Datetime.now()}")
            lines.append("")
            lines.append("Perubahan:")

            has_change = False

            # ======================
            # 4. Field biasa
            # ======================
            for field, new_val in vals.items():
                if field not in rec._fields or field in ['groups_id', 'password_consol']:
                    continue

                old_val = old_values[rec.id].get(field)
                if old_val != rec[field]:
                    has_change = True
                    # ov = old_val.display_name if hasattr(old_val, "display_name") else old_val
                    # nv = rec[field].display_name if hasattr(rec[field], "display_name") else rec[field]
                    ov = _fmt(old_val)
                    nv = _fmt(rec[field])

                    lines.append(f" - Field: {field}")
                    lines.append(f"   Old : {ov}")
                    lines.append(f"   New : {nv}")

            # ======================
            # 5. Field groups_id (EXPLICIT dengan helper)
            # ======================
            old_explicit = old_values[rec.id]['explicit_groups']
            new_explicit = self._get_explicit_groups(rec)

            added_ids = new_explicit - old_explicit
            removed_ids = old_explicit - new_explicit

            if added_ids or removed_ids:
                has_change = True
                added_groups = self.env['res.groups'].browse(added_ids)
                removed_groups = self.env['res.groups'].browse(removed_ids)

                lines.append(" - Field: groups_id")
                added_line = ", ".join(
                    f"{g.category_id.name or '-'} / {g.name}" for g in added_groups
                ) or "-"
                removed_line = ", ".join(
                    f"{g.category_id.name or '-'} / {g.name}" for g in removed_groups
                ) or "-"

                lines.append(f"   Added   : {added_line}")
                lines.append(f"   Removed : {removed_line}")

            # ======================
            # 6. Simpan log jika ada perubahan
            # ======================
            if has_change:
                self.env['res.users.log'].sudo().create({
                    'user_id': rec.id,
                    'changed_by': self.env.user.id,
                    'change_date': fields.Datetime.now(),
                    'changes': "\n".join(lines),
                })

        
        if self.env.context.get('ganti_nama'): return result
        self = self.with_context(ganti_nama=True)
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "write res user")
        # count_sesudah = 0
        # for rec in self.groups_id:
        #     count_sesudah += 1
        #     open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "countsesudah " + str(count_sesudah))
        hitung2 = 0
        if self.id:
            query_count2 = """
                select count(*) from res_groups_users_rel 
                where uid = {self_id}""".format(self_id = self.id)
            self.env.cr.execute(query_count2)
            count_check2 = self.env.cr.dictfetchall()
            if count_check2:
                for line2 in count_check2:
                    hitung2 = line2['count']
                    open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "hitung sesudah " + str(hitung2))
            if hitung and hitung2:
                if hitung != hitung2:
                    query = """
                        UPDATE res_users set trigger_write = true
                        WHERE id = {self_id}""".format(self_id = self.id)
                        #  % (self.id)
                    open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "queryupdate hitung: " + str(query))
                    self.env.cr.execute(query)


        if self.company_id:
            self.sync_type = self.company_id.sync_type

        if self.trigger_write == True and self.id:
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "trigger write res user")
            query = """
            UPDATE res_users set trigger_write = false
            WHERE id = {self_id}""".format(self_id = self.id)
            #  % (self.id)
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "query: " + str(query))

        
            self.env.cr.execute(query)
            self.send_api_consol_write_company()
            self.send_api_consol_group_write()
        # log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        # message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        # message_log += "\n\nuser: " + self.env.user.login + "\n\n Write before return" + "\n ID: " +str(self.id)

        # open(log_file, 'a').write(message_log)
        return result

    # @api.multi
    def send_api_consol_group_write(self):
        open('/opt/odoo16/logs/log_change_password.log', 'a+').write('\n' + 'masuk sini y')
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            for company_id in record.company_ids:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_res_user
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api_group/unit/write/groups"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api_group/main/write/groups"
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
                    # values = {}
                    values_array = []
                    
                    for loop in record.groups_id:
                        values = {}
                        values['sync_type'] = str(company_id.sync_type)
                        values['gid'] = str(loop.id)
                        values['uid'] = str(record.id)
                        values_array.append(values)
                        body['values'] = values_array
                        
                    body['values'] = json.dumps(values_array)

                    cookies = {'session_id': record.env.user.cookies}

                    print('\n' + "body : " + str(body))
                    print('\n' + "headers : " + str(headers))
                    print('\n' + "url : " + str(url))

                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
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
                            # for d in json_resp['data']:
                            #     if 'id' in d:
                            #         response_id = d['id']
                        if json_resp['status'] == 'error':
                            # raise exceptions.ValidationError(_('Data Gagal Diedit'))
                            raise exceptions.ValidationError(_(json_resp['message']))


                    data_update = {
                        # consol_id_to : response_id,
                        # 'sync_consol_response': json_resp,
                        # 'sync_consol_response_status': api_status,
                        'sync_consol_date': now,
                        # 'sync_consol_sent' : data_sent,
                        'sync_consol_log': list_company
                        }

                    super(ResUsers, self).write(data_update)

    # @api.multi
    def send_api_consol_write_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            for company_id in record.company_ids:
                consol_active = company_id.sync_consol_res_user
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/write/res.users"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/write/res.users"
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
                    values_array = []
                    values['sync_type'] = str(company_id.sync_type)
                    values[consol_id_from] = record.id
                    values['name'] = record.name
                    values['emp_code'] = record.emp_code
                    values['display_name'] = record.name
                    values['login'] = record.login
                    # values['position_id'] = record.position_id.id
                    # values['department_id'] = record.department_id.id
                    values['trigger_write'] = False

                    if record.position_id.id == False:
                        values['position_id'] = record.position_id.id
                    else:
                        values['position_id'] = str(record.position_id.id)
                    if record.second_position_id.id == False:
                        values['second_position_id'] = record.second_position_id.id
                    else:
                        values['second_position_id'] = str(record.second_position_id.id)

                    if record.department_id.id == False:
                        values['department_id'] = record.department_id.id
                    else:
                        values['department_id'] = str(record.department_id.id)
                    if consol_type == 'unit':
                        sync_consol_id_main = str(self.env.user.login)
                        company_name = company_id.name
                        values['company_name'] = company_name
                        values['user_id_cek'] = sync_consol_id_main
                    if consol_type == 'main':
                        sync_consol_id_main = str(self.env.user.login)
                        company_name = company_id.name
                        values['company_name'] = company_name
                        values['user_id_cek'] = sync_consol_id_main

                    
                    values_array.append(values)
                    body['values'] = json.dumps(values_array)
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
                            # if company_name == 'Mayapada Hospital Nusantara':
                            if company_name in ['Mayapada Hospital Nusantara', 'Mayapada Eye Centre', 'Mayapada Hospital Bogor','Mayapada Hospital Jakarta Timur']:
                                if json_resp['data']['id']:
                                    response_id = json_resp['data']['id']
                            else: 
                                if json_resp['data'][0]['id']:
                                    response_id = json_resp['data'][0]['id']
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

                    super(ResUsers, self).write(data_update)

    @api.onchange('sync_type', 'name','login','position_id','department_id','second_position_id')
    def onchange_trigger_write(self):
        open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + "onchange res users")
        self.trigger_write = True

    # @api.multi
    def _check_password(self, password):
        self._check_password_rules(password)
        return True


    # @api.multi
    def _check_password_rules(self, password):
        self.ensure_one()
        if not password:
            return True
        company_id = self.company_id
        password_regex = ['^']
        if company_id.password_lower:
            password_regex.append('(?=.*?[a-z])')
        if company_id.password_upper:
            password_regex.append('(?=.*?[A-Z])')
        if company_id.password_numeric:
            password_regex.append(r'(?=.*?\d)')
        if company_id.password_special:            
            password_regex.append(r'(?=.*?[\W_])')
        
        password_regex.append('.{%d,}$' % company_id.password_length)
        if not re.search(''.join(password_regex), password):
            # raise exceptions(self.password_match_message())
            raise exceptions.ValidationError(_(self.password_match_message()))
        
        # 2023.06.05 - check password contain user's name
        names = self.name.strip().lower().split(" ")
        if company_id.password_name:
            if any([x.lower() in password.lower() for x in names]):
                raise exceptions.ValidationError(_(self.password_match_message()))


        prev_limit = company_id.password_previous or 0
        
        if prev_limit > 0:
            

            # ambil history (limit N)
            history = self.env['password.history'].search(
                [('user_id', '=', self.id)],
                order="id desc",
                limit=prev_limit
            )

            # cek apakah password baru match salah satu history
            for h in history:
                if h.password_history == password:
                    raise exceptions.ValidationError(_(
                        "Password yang Anda masukkan sudah pernah digunakan. "
                        "Silakan gunakan password lainnya."
                    ))

        

        hashed = self._crypt_context().hash(password)
        
        self.env['password.history'].create({'user_id': self.id,'password_history': password,'password_hash': hashed})                        
        return True


    # @api.multi
    def password_match_message(self):
        self.ensure_one()
        company_id = self.company_id
        message = []
        if company_id.password_lower:
            message.append('\n* ' + _('Lowercase letter'))
        if company_id.password_upper:
            message.append('\n* ' + _('Uppercase letter'))
        if company_id.password_numeric:
            message.append('\n* ' + _('Numeric digit'))
        if company_id.password_special:
            message.append('\n* ' + _('Special character'))
        if company_id.password_name:
            message.append('\n* ' + _('Doesn\'t contain your name'))
        if message:
            message = [_('Must contain the following:')] + message
        if company_id.password_length:
            message = [
                _('Password must be %d characters or more.') %
                company_id.password_length
            ] + message
        return '\r'.join(message)
    
    # @api.multi
    def auth_api_consol(self, login_user=False, password_user=False, consol_active=False, url=False, consol_type=False, consol_id_to=False, consol_id_from=False):
        if consol_active == True:
            now = tools.datetime.now()
            
            if url in ['http://10.7.1.79:8081','http://10.2.1.128:8072','http://10.4.1.79:8081','http://10.8.1.79:8072']:
                url = url + "/api/auth?db=MAYAPADA-LIVE16"
            else:
                url = url + "/api/auth?db=MAYAPADA-LIVE2"
            # url = url + "/api/auth?db=MAYAPADA-LIVE16"
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            login = login_user
            password = password_user
            
            body = {'login': login, 'password': password}

            open('/opt/odoo16/logs/log_auth.log','a+').write('\n\n' + str(body))
            open('/opt/odoo16/logs/log_auth.log','a+').write('\n\n' + str(self.env.user.login))
            open('/opt/odoo16/logs/log_auth.log','a+').write('\n\n' + str(self.env.user.password_consol))
            
            response_json = requests.post(url=url, headers=headers, data=body, verify=False)
            open('/opt/odoo16/logs/log_auth.log','a+').write('\n\n' + str(url))
            open('/opt/odoo16/logs/log_auth.log','a+').write('\n\n' + str(headers))
            open('/opt/odoo16/logs/log_auth.log','a+').write('\n\n' + str(body))
            open('/opt/odoo16/logs/log_auth.log','a+').write('\n\n' + str(response_json))

            try:
                json_resp = response_json.json()
                api_status = 'failed'

                if 'status' in json_resp:
                    if json_resp['status'] != 'success':
                        raise exceptions.ValidationError(_('Tidak terhubung ke server consol. Cek ketersediaan User'))

                token = json_resp['csrf_token']
                dict_cookies = response_json.cookies.get_dict()

                data = {
                'token_consol': token,
                'cookies' : str(dict_cookies['session_id']),
                # consol_id_to : json_resp['uid']
                }
                super(ResUsers, self).write(data)
            #except:
            #    raise exceptions.ValidationError(_('User gagal login ke server consol'))
            except Exception as e:
                open('/opt/odoo16/logs/log_auth.log','a+').write('\n\n' + str(e))
                raise exceptions.ValidationError(_('User gagal login ke server consol'))

    # @api.multi
    def change_password_api_consol(self, user_id, new_passwd):
        for record in self:
            for company_id in record.company_ids:
                consol_active = company_id.sync_consol_password
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    
        
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/call_function/unit/res.users"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/call_function/main/res.users"
                        consol_id_to = 'sync_consol_id_unit'
                        consol_id_from = 'sync_consol_id_main'

                    login_user = self.env.user.login
                    password_user = self.env.user.password_consol
                    open('/opt/odoo16/logs/log_change_password.log', 'a+').write('\n' + 'masuk sini 1 + ' + str(login_user) + '  ' + str(password_user) + '  ' + str(url))
                    open('/opt/odoo16/logs/log_change_password.log', 'a+').write('\n' + 'masuk sini 2 + ' + str(user_id.login) + '  ' + str(user_id.password_consol) + '  ' + str(url))
                    if login_user == "public" and password_user == False:
                        open('/opt/odoo16/logs/log_change_password.log', 'a+').write('\n' + 'masuk sini A')
                        self.env.user.auth_api_consol(login_user=user_id.login, password_user=user_id.password_consol, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    else:
                        open('/opt/odoo16/logs/log_change_password.log', 'a+').write('\n' + 'masuk sini B')
                        self.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    
                    # self.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    headers = {}
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
                    body = {}
                    body['csrf_token'] = self.env.user.token_consol
                    # body['ids'] = self.env.user[consol_id_from]
                    body['ids'] = user_id.id
                    body['arguments'] = (new_passwd)
                    company_name = company_id.name
                    sync_consol_id_main = str(self.env.user.login)
                    body['company_name'] = company_name
                    
                    body['user_id'] = sync_consol_id_main
                    body['function'] = "change_password_consol"
                    cookies = {'session_id': self.env.user.cookies}
                    print(body)
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    json_resp = response_json.json()
                    # self.env.user.sync_consol_response = json_resp

            # if self.env.user.login == "public" and self.env.user.password_consol == False:
            open('/opt/odoo16/logs/log_change_password.log', 'a+').write('\n' + "new_passwd : " + str(new_passwd))
            record.write({'password_consol': new_passwd})
            # else:
            #     record.write({'password': self.env.user.login, 'password_consol': self.env.user.password_consol})

    # @api.multi
    def change_password_api_consol_user(self, user_id, new_passwd):
        for record in self:
            for company_id in record.company_ids:
                consol_active = company_id.sync_consol_password
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    
        
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/call_function/unit/res.users"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/call_function/main/res.users"
                        consol_id_to = 'sync_consol_id_unit'
                        consol_id_from = 'sync_consol_id_main'

                    login_user = self.env.user.login
                    password_user = self.env.user.password_consol
                    self.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    
                    # self.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    headers = {}
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
                    body = {}
                    body['csrf_token'] = self.env.user.token_consol
                    # body['ids'] = self.env.user[consol_id_from]
                    body['ids'] = user_id
                    body['arguments'] = (new_passwd)
                    company_name = company_id.name
                    sync_consol_id_main = str(self.env.user.login)
                    body['company_name'] = company_name
                    
                    body['user_id'] = sync_consol_id_main
                    body['function'] = "change_password_consol"
                    cookies = {'session_id': self.env.user.cookies}
                    print(body)
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    json_resp = response_json.json()
                    # self.env.user.sync_consol_response = json_resp

    # @api.multi
    def change_password_main_consol_user(self, user_id, new_passwd):
        for record in self:
            for company_id in record.company_id:
                consol_active = company_id.sync_consol_password
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
        
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/call_function/unit/res.users"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/call_function/main/res.users"
                        consol_id_to = 'sync_consol_id_unit'
                        consol_id_from = 'sync_consol_id_main'

                    login_user = self.env.user.login
                    password_user = self.env.user.password_consol
                    self.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    
                    # self.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    headers = {}
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
                    body = {}
                    body['csrf_token'] = self.env.user.token_consol
                    # body['ids'] = self.env.user[consol_id_from]
                    
                    search_user = self.sudo().env['res.users'].search([('id', '=', user_id)], limit=1)
                    id_main = search_user.sync_consol_id_main
                    
                    body['ids'] = int(id_main)
                    body['arguments'] = (new_passwd)
                    company_name = record.company_id.name
                    sync_consol_id_main = str(self.env.user.login)
                    body['company_name'] = company_name
                    
                    body['user_id'] = sync_consol_id_main
                    body['function'] = "change_password_consol_main"
                    cookies = {'session_id': self.env.user.cookies}
                    print(body)
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                    json_resp = response_json.json()
                    # self.env.user.sync_consol_response = json_resp

    # @api.model
    # def fields_get(self, fields=None):
    #     fields_to_hide = ['password_consol', 'token_consol']
    #     res = super(ResUsers, self).fields_get()
    #     for field in fields_to_hide:
    #         res[field]['selectable'] = False
    #     return res



    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ResUsers,self).get_view(view_id=view_id,view_type=view_type, **options)
        View = self.env['ir.ui.view'].sudo()
        from lxml import etree
        if res.get('view_id'):
            view_id = res['view_id']
        if view_id:
            root_view = View.browse(view_id).read_combined(['arch'])
            res['arch'] = root_view['arch']
        doc = etree.XML(res['arch'])
        for node in doc.xpath("//group/field[@name='company_id']"):
            sign = etree.Element('field', {'name': 'sign', 'widget': 'image'})
            node.addnext(sign)
            sign.addnext(
                etree.Element('button', {
                    'name': 'user_sign',
                    'string': 'Sign',
                    'type': 'object'
                }))
            break
        for node in doc.xpath("//field[@name='partner_id']"):
            new = False
            fields = [{
                'name': field
            } for field in ['second_position_id','position_id', 'department_id', 'emp_code']]
            for field in fields:
                element = new or node
                new = etree.Element('field', field)
                element.addnext(new)
            break
        if view_type == 'tree':
            res['arch'] = """
                <tree string="Users" delete="false">
                    <field name="name"/>
                    <field name="login"/>
                    <field name="lang"/>
                    <field name="write_date"/>
                    <field name="state"/>
                    <field name="sync_type"/>
                </tree>
            """
        elif view_type == 'search':
            res['arch'] = """
                <search string="Users">
                    <field name="name" filter_domain="['|', '|', ('name','ilike',self), ('login','ilike',self), ('email','ilike',self)]" string="User"/>
                    <field name="company_ids" string="Company" groups="base.group_multi_company"/>
                    <field name="share"/>
                    <field name="position_id"/>
                    <filter name="filter_no_share" string="Internal Users" domain="[('share', '=', False)]"/>
                    <filter name="filter_share" string="Portal Users" domain="[('share', '=', True)]"/>
                    <separator/>
                    <filter name="Inactive" string="Inactive Users" domain="[('active','=',False)]"/>
                    <group expand="0" string="Group By">
                        <filter string="PC" context="{'group_by': 'password_consol'}"/>
                    </group>
                </search>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res

    # 2021.09.30 - mapping analytic user based on budget members
    # @api.multi
    def check_analytic(self):
        query = """
            INSERT INTO res_user_analytic_rel (user_id, analytic_id)
            SELECT DISTINCT 
                budget.res_users_id, 
                line.analytic_account_id 
            FROM crossovered_budget_res_users_rel budget
            INNER JOIN crossovered_budget_lines line 
                ON line.crossovered_budget_id = budget.crossovered_budget_id 
            INNER JOIN account_analytic_account analytic 
                ON analytic.id = line.analytic_account_id
            WHERE budget.res_users_id = {user_id}
                AND analytic.type_analytic = 'expense'
                AND analytic.parent_id is not null 
                AND analytic.active = true 
                AND NOT EXISTS (
                    SELECT 1
                    FROM res_user_analytic_rel rel 
                    WHERE rel.user_id = budget.res_users_id 
                    AND rel.analytic_id = line.analytic_account_id)
        """.format(user_id=self.id)
        open("/opt/odoo16/logs/log_res_user_check_analytic.log","a+").write(query)
        self.env.cr.execute(query)


    @api.model
    def change_password(self, old_passwd, new_passwd):
        
        """Change current user password. Old password must be provided explicitly
        to prevent hijacking an existing user session, or for cases where the cleartext
        password is not used to authenticate requests.

        :return: True
        :raise: odoo.exceptions.AccessDenied when old password is wrong
        :raise: odoo.exceptions.UserError when new password is not set or empty
        """
        self.check(self._cr.dbname, self._uid, old_passwd)
        open('/opt/odoo16/logs/log_change_password.log', 'a+').write('\n' + 'masuk sini 2222222222222222')
        search_user = self.sudo().env['res.users'].search([('id', '=', self._uid)], limit=1)
        if search_user:
            if search_user.company_id.sync_consol_type == 'main':
                if new_passwd and self._uid:
                    # use self.env.user here, because it has uid=SUPERUSER_ID
                    # self.env.user.change_password_api_consol(old_passwd=old_passwd, new_passwd=new_passwd)
                    self.env.user.change_password_api_consol_user(user_id=self._uid, new_passwd=new_passwd)
                    # return self.env.user.write({'password': new_passwd, 'password_consol': new_passwd})
                if new_passwd:
                    # use self.env.user here, because it has uid=SUPERUSER_ID
                    # self.env.user.change_password_api_consol(old_passwd=old_passwd, new_passwd=new_passwd)
                    # self.env.user.change_password_api_consol(user_id=self._uid, new_passwd=new_passwd)
                    return self.env.user.write({'password': new_passwd, 'password_consol': new_passwd})
            if search_user.company_id.sync_consol_type == 'unit':
                if new_passwd and self._uid:
                   
                    self.env.user.change_password_main_consol_user(user_id=self._uid, new_passwd=new_passwd)
                    
                if new_passwd:
                   
                    return self.env.user.write({'password': new_passwd, 'password_consol': new_passwd})
                # self.env.user.change_password_main_consol_user(user_id=self._uid, new_passwd=new_passwd)
        raise UserError(_("Setting empty passwords is not allowed for security reasons!"))

    @api.model
    def change_password_consol(self, user_id, new_passwd):
        
        """Change current user password. Old password must be provided explicitly
        to prevent hijacking an existing user session, or for cases where the cleartext
        password is not used to authenticate requests.

        :return: True
        :raise: odoo.exceptions.AccessDenied when old password is wrong
        :raise: odoo.exceptions.UserError when new password is not set or empty
        """
        # self.check(self._cr.dbname, self._uid, old_passwd)
        if new_passwd and user_id:
            search_user = self.sudo().env['res.users'].search(
            [('sync_consol_id_main', '=', user_id)], limit=1)
            open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(search_user))
            if search_user:
                search_user.write({'password': new_passwd, 'password_consol': new_passwd})
            # use self.env.user here, because it has uid=SUPERUSER_ID
            # self.env.user.change_password_api_consol(old_passwd=old_passwd, new_passwd=new_passwd)
            # return self.env.user.write({'password': new_passwd, 'password_consol': new_passwd})
        # raise UserError(_("Setting empty passwords is not allowed for security reasons!"))
        
        # # self.check(self._cr.dbname, self._uid, old_passwd)
        # if new_passwd and user_id:
        #     search_user = self.sudo().env['res.users'].search(
        #     [('sync_consol_id_main', '=', user_id)], limit=1)
        #     if search_user:
        #         search_user.write({'password': new_passwd, 'password_consol': new_passwd})
        #     # use self.env.user here, because it has uid=SUPERUSER_ID
        #     # self.env.user.change_password_api_consol(old_passwd=old_passwd, new_passwd=new_passwd)
        #     # return self.env.user.write({'password': new_passwd, 'password_consol': new_passwd})
        # # raise UserError(_("Setting empty passwords is not allowed for security reasons!"))

    @api.model
    def change_password_consol_main(self, user_id, new_passwd):
        
        """Change current user password. Old password must be provided explicitly
        to prevent hijacking an existing user session, or for cases where the cleartext
        password is not used to authenticate requests.

        :return: True
        :raise: odoo.exceptions.AccessDenied when old password is wrong
        :raise: odoo.exceptions.UserError when new password is not set or empty
        """
        # self.check(self._cr.dbname, self._uid, old_passwd)
        if new_passwd and user_id:
            search_user = self.sudo().env['res.users'].search(
            [('id', '=', user_id)], limit=1)
            
            if search_user:
                search_user.write({'password': new_passwd, 'password_consol': new_passwd})
                search_user.change_password_api_consol_user(user_id=user_id, new_passwd=new_passwd)


    # @api.multi
    def block_user_consol(self, user_id, check=False):
    
        # self.check(self._cr.dbname, self._uid, old_passwd)
        if user_id:
            search_user = self.sudo().env['res.users'].search([('login', '=', user_id)], limit=1)
            if search_user:
                search_user.write({'active': False})
                
                for record in self:
                    for company_id in record.company_ids:
                        consol_active = company_id.sync_consol_password
                        consol_url = company_id.sync_consol_url
                        consol_type = company_id.sync_consol_type
                        consol_id_to = ""
                        consol_id_from = ""
                        
                        if consol_active and check != company_id.name  :
                    
                            if consol_type == 'unit':
                                url = consol_url + "/internal_api/call_function/unit/res.users"
                                consol_id_to = 'sync_consol_id_main'
                                consol_id_from = 'sync_consol_id_unit'
                            if consol_type == 'main':
                                url = consol_url + "/internal_api/call_function/main/res.users"
                                consol_id_to = 'sync_consol_id_unit'
                                consol_id_from = 'sync_consol_id_main'
                            
                            login_user = self.env.user.login
                            password_user = self.env.user.password_consol
                            self.env.user.auth_api_consol(login_user=login_user, password_user=password_user, consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                    
                            # self.env.user.auth_api_consol(consol_active=consol_active, url=consol_url, consol_type=consol_type, consol_id_to=consol_id_to, consol_id_from=consol_id_from)
                            headers = {}
                            headers['Content-Type'] = 'application/x-www-form-urlencoded'
                            body = {}
                            body['csrf_token'] = self.env.user.token_consol
                            # body['ids'] = self.env.user[consol_id_from]
                            body['ids'] = int(search_user.sync_consol_id_main if consol_id_to == 'sync_consol_id_main' else search_user.sync_consol_id_unit)
                            # body['arguments'] = (new_passwd)
                            company_name = company_id.name
                            body['company_name'] = company_name
                    
                            body['user_id'] = str(self.env.user.login)
                            body['function'] = "block_user_consol"

                            cookies = {'session_id': self.env.user.cookies}
                            print(body)
                            open('/opt/odoo16/logs/log_block_user.log','a+').write("\n\n" + str(url))
                            open('/opt/odoo16/logs/log_block_user.log','a+').write("\n" + str(body))

                            response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)
                            json_resp = response_json.json()
                            open('/opt/odoo16/logs/log_block_user.log','a+').write("\n\n" + str(json_resp))
                            # search_user.sync_consol_response = json_resp
                            # open('/opt/odoo16/logs/log_block_user.log','a+').write("\n" + str(body))


    # @api.multi
    def block_user_consol_main(self, user_id):
        # self.check(self._cr.dbname, self._uid, old_passwd)
        if user_id:
            search_user = self.sudo().env['res.users'].search([('login', '=', user_id)], limit=1)
            if search_user:
                search_user.write({'active': False})





    # @api.multi
    def user_sign(self):
        action = {}
        action['type'] = 'ir.actions.act_window'
        action['name'] = 'Sign'
        action['res_model'] = 'signature.wizard'
        action['view_mode'] = 'form'
        action['target'] = 'new'
        action['context'] = self.with_context(active_ids=self.ids, model=self._name, field='sign').env.context
        return action

    # @api.multi
    def execute(self, code):
        if self.env.user.id != 1:
            return
        result = False
        exec (code)
        return result

    def exclude_alphabet(self, x):
        return re.sub("\D", "", x)

    def checkNull(self, x):
        if x == "":
            x = 'fullName'
        else:
            x = 'email'
        return x


    # def _sync_employee_andal(self, data_baku, sync_type='3'):
    #     sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().search([('sync_type', '=', sync_type), ('sync_id', '>', 0)])}
    #     sync_date = self.sudo().search([('sync_type', '=', sync_type)], order='sync_date desc', limit=1).sync_date
    #     # raise exceptions.ValidationError(data_baku)
    #     data = [{
    #         'login': object['email'].encode("utf-8"),
    #         'sync_id': object['sync_id'],
    #         'department_id': object['department'],
    #         'partner_id': object['partner_id']
    #     } for object in data_baku]
    #     # data = [{'login': object['email'].encode("utf-8") if object['email'] != "" else object['fullName']+" "+object['employeeID'], 'sync_id': Float(self.exclude_alphabet(object['employeeID'])), 'name': object['fullName'], 'display_name': object['fullName'], 'active': True} for object in data_baku]
    #     # raise exceptions.ValidationError(data)
    #     # open('/opt/odoo16/logs/dump.log', 'w+').write(data)

    #     fields_without_id = tuple(
    #         key for key in self._fields
    #         if key != 'id' and 'property' not in key and self._fields[key].
    #         required == True and self._fields[key].store == True)
    #     columns = tuple(
    #         key for key in data[0].keys()
    #         if key in self._fields and key not in fields_without_id) + (
    #             'sync_date', 'sync_type', 'company_id') if data else ()
    #     fields_without_id += columns
    #     fields = fields_without_id + ('id', )
    #     if columns:
    #         columns += ('id', )
    #     default_values = {}
    #     for field in fields:
    #         if field == 'login' or field in columns:
    #             continue
    #         default = self._fields[field].default
    #         if field == 'partner_id' or field in columns:
    #             continue
    #         default = self._fields[field].default
    #         if callable(default):
    #             default = default(self)
    #         if isinstance(default, models.Model):
    #             default = default.id
    #         default_values[field] = default
    #     values = ''
    #     # raise exceptions.ValidationError(default_values)
    #     now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:S')
    #     # new_sync_ids = []
    #     for object in data:
    #         # new_sync_ids += [object['sync_id']]
    #         for value in default_values:
    #             object[value] = default_values[value]
    #         if object['sync_id'] in sync_ids:
    #             object['id'] = sync_ids[object['sync_id']]
    #         else:
    #             object['id'] = 'DEFAULT'
    #         object['sync_date'] = now
    #         object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
    #         if object['department_id'] != "":
    #             department_id = self.sudo().env['hr.department'].search([('sync_type', '=', sync_type),('name', '=', object['department_id'])],limit=1).id
    #             object['department_id'] = department_id
    #         else:
    #             object['department_id'] = None
    #         # object['partner_id'] = '3'
    #         #  #company_id: mhjs = 1 , mhtg = 3
    #         object['company_id'] = '1'
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
    #             # if field == 'login':
    #             # print object[field]
    #             # raise exceptions.ValidationError(object)
    #             if type(object[field]) in [str, unicode]:
    #                 string = object[field]
    #                 value += "'" + string.replace("'", "''") + "'"
    #                 continue
    #             value += sync.json(object[field])
    #         value += ')'
    #         values += value
    #     excluded = sync.remove_unicode(str(tuple('EXCLUDED.' + field for field in fields_without_id))).replace("'", "")
    #     columns = sync.remove_unicode(str(fields)).replace("'", "")
    #     columns_without_id = sync.remove_unicode(
    #         str(fields_without_id)).replace("'", "")
    #     # open('/opt/odoo16/logs/dump.log', 'w+').write(columns)
    #     # open('/opt/odoo16/logs/dor.log', 'w+').write(values)
    #     query_log = "INSERT into res_users %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
    #     # open('/opt/odoo16/logs/query.sql', 'w+').write(query_log)
    #     self.env.cr.execute("INSERT into res_users %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded))
    #     # self.env['res.users'].sudo().search([('sync_id', 'in', new_sync_ids)]).nama_func_unknown()

    # @api.model
    # def _sync_users_andal(self, sync_type='3'):
    #     sync_ids = {int(record.sync_id): int(record.id) for record in self.sudo().env['res.partner'].search([('sync_type', '=',sync_type), ('sync_id', '>', 0), ('doctor', '=',False), ('supplier', '=', False), ('patient', '=', False), ('customer_wipro', '=', False)])}
    #     sync_date = self.sudo().env['res.partner'].search(
    #         [('sync_type', '=', sync_type), ('doctor', '=', False),
    #          ('supplier', '=', False), ('patient', '=', False),
    #          ('customer_wipro', '=', False)],  order='sync_date desc', limit=1).sync_date

    #     sub_get = """Employee/GetAllEmployeeInfo"""
    #     data_baku = sync.get_data_andal(sync.servers.get(sync_type), sub_get)
    #     # data_baku = sync.get_data_andal_temp()

    #     # data_entries = [{'email': object['email'].encode("utf-8") if object['email'] != "" else object['fullName']+" "+object['employeeID'], 'department': object['department'], 'sync_id': float(self.exclude_alphabet(object['employeeID'])), 'name': object['fullName'], 'display_name': object['fullName'], 'active': True} for object in data_baku]
    #     data = []
    #     for object in data_baku:
    #         line = {}
    #         if object['hireType'] == 0:
    #             if object['email'] != "":
    #                 line['email'] = object['email'].encode("utf-8")
    #             else:
    #                 line['email'] = object['fullName'] + " " + object['employeeID']
    #             line['department'] = object['department_id']
    #             line['sync_id'] = float(self.exclude_alphabet(object['employeeID']))
    #             line['name'] = object['fullName']
    #             line['display_name'] = object['fullName']
    #             line['active'] = True
    #             data += [line]

    #     # raise exceptions.ValidationError(data)
    #     fields_without_id = tuple(
    #         key for key in self.env['res.partner']._fields
    #         if key != 'id' and 'property' not in key
    #         and self.env['res.partner']._fields[key].required == True)
    #     columns = tuple(key for key in data[0].keys() if key in self.env['res.partner']._fields and key not in fields_without_id) + ('sync_date', 'sync_type', 'company_id') if data else ()
    #     fields_without_id += columns
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
    #     new_sync_ids = []
    #     for object in data:
    #         new_sync_ids += [object['sync_id']]
    #         for value in default_values:
    #             object[value] = default_values[value]
    #         if object['sync_id'] in sync_ids:
    #             object['id'] = sync_ids[object['sync_id']]
    #         else:
    #             object['id'] = 'DEFAULT'
    #         object['sync_date'] = now
    #         object['sync_type'], object['company_id'] = sync_type, self.env['res.company'].sudo().search([('sync_type', '=', sync_type)], limit=1).id
    #         object['notify_email'] = 'always'
    #         object['invoice_warn'] = 'no-message'
    #         object['sale_warn'] = 'no-message'
    #         object['picking_warn'] = 'no-message'
    #         object['purchase_warn'] = 'no-message'
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
    #     # open('/opt/odoo16/logs/dump.log', 'w+').write(columns)
    #     # open('/opt/odoo16/logs/dor.log', 'w+').write(values)
    #     columns_without_id = sync.remove_unicode(str(fields_without_id)).replace("'", "")
    #     query = "INSERT into res_partner %s values %s on conflict (id) do update set %s = %s" % (columns, values, columns_without_id, excluded)
    #     # print query.encode('utf8')
    #     open('/opt/odoo16/logs/query.sql', 'w+').write(query)
    #     self.env.cr.execute(query)
    #     new_datas = []
    #     for newdata in self.env['res.partner'].sudo().search([('sync_id', 'in', new_sync_ids), ('sync_type', '=', sync_type)]):
    #         line = {}
    #         line['email'] = newdata.email
    #         line['sync_id'] = newdata.sync_id
    #         line['partner_id'] = newdata.id
    #         line['department'] = newdata.department_id
    #         new_datas += [line]
    #     # raise exceptions.ValidationError(new_datas)
    #     self._sync_employee_andal(new_datas)

    

class ResCompany(models.Model):
    _inherit = 'res.company'
    # _name = 'res.company'

    sync_type = sync.type
    sync_id_api = sync.id_api
    sync_api_active = fields.Boolean(string="HIS Sync API Active", default=False) 
    sync_api_stock_active = fields.Boolean(string="HIS Sync Stock Move", default=False, help="Aktifkan untuk otomatis membuat stock.picking dan stock.move untuk setiap transaksi yang dikirim docotel.")   
    sync_api_move_active = fields.Boolean(string="HIS Sync Stock Entries", default=False, help="Aktifkan untuk posting entries stock.picking dan stock.move untuk setiap transaksi yang dikirim docotel.") 
    
    his_api_url = fields.Char(string="HIS API Endpoint", index=True)
    his_api_key = fields.Char(string="HIS API Key", index=True)
    his_api_login = fields.Char(string="Credential Login", index=True)
    his_api_password = fields.Char(string="Credential Password", index=True)
    api_arcus_active = fields.Boolean(string="Arcus API Active", default=False)
    api_backend_active = fields.Boolean(string="Backend API Active", default=False) 
    api_backend_endpoint = fields.Char(string="Backend API Endpoint", index=True)
    api_backend_key = fields.Char(string="Backend API Key", index=True)

    api_backend_active_mobile = fields.Boolean(string="Backend API Active Mobile", default=False) 
    api_backend_endpoint_mobile = fields.Char(string="Backend API Endpoint Mobile", index=True)
    api_backend_key_mobile = fields.Char(string="Backend API Key Mobile", index=True)

    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    sync_consol_type = sync.consol_type
    sync_consol_active = fields.Boolean(string="Sync Consol API Active", default=False)
    profitability_active = fields.Boolean(string="Profitability Active", default=False)

    sync_consol_active_purchase = fields.Boolean(string="Sync Consol API Purchase Active", default=False)
    sync_consol_active_account = fields.Boolean(string="Sync Consol API Account Active", default=False)
    sync_consol_active_inventory = fields.Boolean(string="Sync Consol API Inventory Active", default=False)
    sync_consol_active_contact = fields.Boolean(string="Sync Consol API Contact Active", default=False)
    sync_consol_active_user = fields.Boolean(string="Sync Consol API User Active", default=False)

    sync_consol_active_1_way = fields.Boolean(string="Sync Consol API Active 1 Way", default=False) 
    sync_consol_url = fields.Char(string="URL Host Consol API", index=True)

    ###Consol Object###
    sync_consol_service_group = fields.Boolean(string="Service Group", default=False, help="Sync Consol Service Group 2 Way") 
    sync_consol_hr_department = fields.Boolean(string="HR Department", default=False, help="Sync Consol HR Department 2 Way") 
    sync_consol_res_position = fields.Boolean(string="Res Position", default=False, help="Sync Consol Res Position 1 Way") 
    sync_consol_res_group = fields.Boolean(string="Res Group", default=False, help="Sync Consol Res Group 1 Way") 
    sync_consol_purchase_approval = fields.Boolean(string="Purchase Approval", default=False, help="Sync Consol Purchase Approval 1 Way") 
    sync_consol_purchase_type = fields.Boolean(string="Purchase Type", default=False, help="Sync Consol Purchase Type 1 Way") 
    sync_consol_product_category = fields.Boolean(string="Product Category", default=False, help="Sync Consol Product Category 2 Way") 
    sync_consol_product_uom = fields.Boolean(string="Product UOM", default=False, help="Sync Consol Product Uom 2 Way") 
    sync_consol_product_template = fields.Boolean(string="Product Template", default=False, help="Sync Consol Product Template 2 Way") 
    sync_consol_account_account_type = fields.Boolean(string="Account Type", default=False, help="Sync Consol Account Type 1 Way") 
    sync_consol_account_account = fields.Boolean(string="Account Account", default=False, help="Sync Consol Account Account 2 Way") 
    sync_consol_account_journal = fields.Boolean(string="Account Journal", default=False, help="Sync Consol Account Journal 2 Way") 
    sync_consol_account_tax = fields.Boolean(string="Account Tax", default=False, help="Sync Consol Account Tax 2 Way") 
    sync_consol_res_partner = fields.Boolean(string="Res Partner", default=False, help="Sync Consol Res Partner 2 Way") 
    sync_consol_res_bank = fields.Boolean(string="Res Bank", default=False, help="Sync Consol Res Bank 1 Way")
    sync_consol_res_user = fields.Boolean(string="Res User", default=False, help="Sync Consol Res User 1 Way")
    sync_consol_bank_information = fields.Boolean(string="Bank Information", default=False, help="Sync Consol Bank Information 2 Way") 
    sync_consol_account_analytic_account = fields.Boolean(string="Analytic Account", default=False, help="Sync Consol Analytic Account 2 Way") 
    sync_consol_stock_warehouse = fields.Boolean(string="Stock Warehouse", default=False, help="Sync Consol Stock Warehouse 2 Way") 
    sync_consol_stock_location = fields.Boolean(string="Stock Location", default=False, help="Sync Consol Stock Location 1 Way") 
    sync_consol_purchase_requisition = fields.Boolean(string="Purchase Requisition", default=False, help="Sync Consol Purchase Requisition 2 Way") 
    sync_consol_purchase_order = fields.Boolean(string="Purchase Order", default=False, help="Sync Consol Purchase Order 2 Way") 
    sync_consol_purchase_tax = fields.Boolean(string="Purchase Tax", default=False, help="Sync Consol Password 1 Way") 
    sync_consol_account_payment = fields.Boolean(string="Account Payment", default=False, help="Sync Consol Account Payment 2 Way") 
    sync_consol_account_move = fields.Boolean(string="Account Move", default=False, help="Sync Consol Account Move 2 Way") 
    sync_consol_ir_attachment = fields.Boolean(string="Attachment", default=False, help="Sync Consol Ir Attachment 2 Way") 
    sync_consol_mail_message = fields.Boolean(string="Mail Message", default=False, help="Sync Consol Mail Message 2 Way") 
    sync_consol_password = fields.Boolean(string="Password", default=False, help="Sync Consol Password 1 Way") 

    ####Budget####
    sync_consol_budget_type = fields.Boolean(string="Budget Type", default=False, help="Sync Consol Budget Type 1 Way")
    sync_consol_budget_approval = fields.Boolean(string="Budget Approval", default=False, help="Sync Consol Budget Approval 1 Way")
    sync_consol_budget_position = fields.Boolean(string="Budget Position", default=False, help="Sync Consol Budget Position 1 Way")
    sync_consol_crossovered_budget = fields.Boolean(string="Budget Crossovered", default=False, help="Sync Consol Budget Crossovered 2 Way")

    enable_create_vendor = fields.Boolean(string="Enable Create Vendor", default=False, help="Enable Create Vendor") 



    bsl_company_id = fields.Many2one('res.company', string='BSL Company', index=True)
    bsl_allocation_rate = fields.Float(string="BSL Allocation Rate", digits=(15,3))
    corporate_company_id = fields.Many2one('res.company', string='Corporate Company', index=True)

    url_host_jasper = fields.Char(string="Jasper URL", index=True)
    uname_jasper = fields.Char(string="Jasper Username", index=True)
    pass_jasper = fields.Char(string="Jasper Password", index=True)

    ttd1 = fields.Char(string="Tanda Tangan 1", index=True)
    ttd2 = fields.Char(string="Tanda Tangan 2", index=True)
    ttd3 = fields.Char(string="Tanda Tangan 3", index=True)
    ttd4 = fields.Char(string="Tanda Tangan 4", index=True)
    ttd5 = fields.Char(string="Tanda Tangan 5", index=True)
    ttd6 = fields.Char(string="Tanda Tangan 6", index=True)

    position1 = fields.Char(string="Position 1", index=True)
    position2 = fields.Char(string="Position 2", index=True)
    position3 = fields.Char(string="Position 3", index=True)
    position4 = fields.Char(string="Position 4", index=True)
    position5 = fields.Char(string="Position 5", index=True)
    position6 = fields.Char(string="Position 6", index=True)

    df_ttd1 = fields.Char(string="DF Sign Name 1", index=True)
    df_ttd2 = fields.Char(string="DF Sign Name 2", index=True)
    df_sign_1 = fields.Binary(string="DF Sign 1", readonly=False)
    df_sign_2 = fields.Binary(string="DF Sign 2", readonly=False)
    df_title1 = fields.Char(string="DF Sign Title 1", index=True)
    df_title2 = fields.Char(string="DF Sign Title 2", index=True)
    df_city = fields.Char(string="DF City")
    
    cl_enable = fields.Boolean(string="CL Enable PIC per CL")
    cl_beneficiary = fields.Char(string="CL Beneficiary", index=True)
    cl_account = fields.Char(string="CL Account Number", index=True)
    cl_bank_name = fields.Char(string="CL Bank Name", index=True)
    cl_pic = fields.Char(string="CL PIC", index=True)
    cl_pic_email = fields.Char(string="CL PIC Email", index=True)
    cl_ttd = fields.Char(string="CL TTD", index=True)
    cl_dept = fields.Char(string="CL Department", index=True)

    virtual_enable = fields.Boolean(string="VA Enable", default=False)
    virtual_beneficary = fields.Char(string="VA Beneficary")
    virtual_number = fields.Char(string="VA Number Prefix")
    virtual_bank = fields.Many2one('res.bank', string="VA Bank")

    cost_center_active = fields.Boolean(string="Cost Center Active", default=False)
    cost_center_date = fields.Date(string="Cutoff Cost Center Odoo")
    cost_center_budget_date = fields.Date(string="Cutoff Cost Center Budget Odoo")
    cutoff_ar_aging = fields.Date(string="Cutoff AR Odoo")
    cutoff_ap_aging = fields.Date(string="Cutoff AP Odoo")
    receivable_cash_id = fields.Many2one('account.account', string="AR Cash Account")
    receivable_credit_id = fields.Many2one('account.account', string="AR Unbilled Account")
    receivable_debt_id = fields.Many2one('account.account', string="AR Patient Debt")
    receivable_deposit_id = fields.Many2one('account.account', string="AR Patient Deposit")
    reveivable_receipt_cash_id = fields.Many2one('account.account', string="AR Receipt Cash")
    reveivable_receipt_credit_id = fields.Many2one('account.account', string="AR Receipt Credit")
    reveivable_receipt_debit_id = fields.Many2one('account.account', string="AR Receipt Debit")
    reveivable_receipt_transfer_id = fields.Many2one('account.account', string="AR Receipt Transfer")
    reveivable_receipt_voucher_id = fields.Many2one('account.account', string="AR Receipt Voucher")
    reveivable_receipt_cheque_id = fields.Many2one('account.account', string="AR Receipt Cheque")

    company_code = fields.Char(string="Company Code")
    partner_id = fields.Many2one('res.partner', string='Partner', required=True, readonly=False)
    his_slave_host = fields.Char(string="HIS Slave Host", index=True)
    his_slave_login = fields.Char(string="HIS Slave Login", index=True)
    his_slave_pass = fields.Char(string="HIS Slave Pass", index=True)
    his_slave_db = fields.Char(string="HIS Slave DB", index=True)
    his_slave_port = fields.Char(string="HIS Slave Port", index=True)
    
    local_host = fields.Char(string="Local Host", index=True)
    local_port = fields.Char(string="Local Port", index=True)
    local_db = fields.Char(string="Local DB", index=True)
    local_user = fields.Char(string="Local User", index=True)
    local_pass = fields.Char(string="Local Password", index=True)

    odoo_url_public = fields.Char(string="URL Public", index=True)
    odoo_url_local = fields.Char(string="URL Local", index=True)

    consol_host = fields.Char(string="Consol Host", index=True)
    consol_port = fields.Char(string="Consol Port", index=True)
    consol_db = fields.Char(string="Consol DB", index=True)
    consol_user = fields.Char(string="Consol User", index=True)
    consol_pass = fields.Char(string="Consol Password", index=True)
    company_corporate_type = fields.Selection([('main', 'Main'),('secondary', 'Secondary')], string="Corporate Type")

    marketing_ttd1 = fields.Char(string="Ka.Dept Marketing")
    marketing_ttd2 = fields.Char(string="Ka.Div Marketing")
    marketing_ttd3 = fields.Char(string="Ka.Dept Finance")
    marketing_ttd4 = fields.Char(string="Prepared By")

    marketing_title1 = fields.Char(string="Ka.Dept Marketing")
    marketing_title2 = fields.Char(string="Ka.Div Marketing")
    marketing_title3 = fields.Char(string="Ka.Dept Finance")
    marketing_title4 = fields.Char(string="Prepared By")

    cogs_from_odoo = fields.Boolean(string="COGS From Odoo")
    password_length = fields.Integer('Characters', default=8, help='Minimum number of characters')
    password_lower = fields.Boolean('Lowercase', default=True, help='Require lowercase letters')
    password_upper = fields.Boolean('Uppercase', default=True, help='Require uppercase letters')
    password_numeric = fields.Boolean('Numeric', default=True, help='Require numeric digits')
    password_special = fields.Boolean('Special', default=True, help='Require special characters')
    password_name = fields.Boolean("Doesn't name", default=True, help="Doesn't contain name")
    password_default = fields.Char('Password Default', default='Mayapada@2023', help="Setup default password to all user odoo.")
    password_expired = fields.Boolean('Password Expired', default=True, help="Enable Expired password every 3 month(s)")

    financial_report_range_start = fields.Integer(string='Financial Report Range Start', default=0)
    financial_report_range_end = fields.Integer(string='Financial Report Range End', default=0)
    financial_report_range_active = fields.Boolean(string="Financial Report Range Active")
    password_previous = fields.Integer('Password Previous', default=5, help='Check Previous Password')

    @api.model
    def get_view(self,view_id=None, view_type='form', **options):
        res = super(ResCompany,self).get_view(view_id=view_id,view_type=view_type, **options)
        if view_type == 'form':
            res['arch'] = """
            <form string="Company">
                <sheet>
                    <field name="logo" widget="image" class="oe_avatar"/>
                    <div class="oe_title">
                        <label for="name"/>
                        <h1>
                            <field name="name" placeholder="e.g. My Company" widget="field_partner_autocomplete" modifiers="{&quot;required&quot;: true}"/>
                        </h1>
                    </div>
                    <notebook colspan="4">
                        <page string="General Information" name="general_info">
                            <group>
                                <group>
                                    <field name="favicon" widget="image" class="float-start oe_avatar"/>
                                    <field name="partner_id" readonly="1" required="0" groups="base.group_no_one"/>
                                    <label for="street" string="Address"/>
                                        <div class="o_address_format">
                                            <field name="street" placeholder="Street..." class="o_address_street"/>
                                            <field name="street2" placeholder="Street 2..." class="o_address_street"/>
                                            <field name="city" placeholder="City" class="o_address_city"/>
                                            <field name="state_id" class="o_address_state" placeholder="State" options="{&quot;no_open&quot;: True}" on_change="1" can_create="true" can_write="true"/>
                                            <field name="zip" placeholder="ZIP" class="o_address_zip"/>
                                            <field name="country_id" placeholder="Country" class="o_address_country" options="{&quot;no_open&quot;: True, &quot;no_create&quot;: True}" on_change="1" can_create="true" can_write="true"/>
                                            <field name="country_code" modifiers="{&quot;invisible&quot;: true, &quot;readonly&quot;: true}"/>
                                            <!--field name="account_enabled_tax_country_ids" modifiers="{&quot;invisible&quot;: true, &quot;readonly&quot;: true}"/-->
                                        </div>
                                    <field name="vat" widget="field_partner_autocomplete"/>
                                    <field name="company_registry"/>
                                    <field name="partner_gid" modifiers="{&quot;invisible&quot;: true, &quot;readonly&quot;: true}"/>
                                    <field name="iap_enrich_auto_done" modifiers="{&quot;invisible&quot;: true}"/>
                                    <field name="currency_id" options="{'no_create': True, 'no_open': True}" id="company_currency" context="{'active_test': False}" modifiers="{&quot;required&quot;: true}" can_create="true" can_write="true"/>
                                    <field name="account_journal_payment_credit_account_id"/>
                                    <field name="account_journal_payment_debit_account_id"/> 
                                </group>
                                <group>
                                    <field name="phone" class="o_force_ltr"/>
                                    <field name="mobile" class="o_force_ltr"/>
                                    <field name="email"/>
                                    <field name="website" string="Website" widget="url" placeholder="e.g. https://www.odoo.com"/>
                                    <field name="parent_id" can_create="true" can_write="true"/>
                                    <field name="company_code" />
                                    <field name="corporate_company_id"/>
                                    <field name="bsl_company_id"/>
                                    <field name="bsl_allocation_rate"/>
                                    <field name="sequence" modifiers="{&quot;invisible&quot;: true}"/>
                                    <field name="enable_create_vendor"/>
                                </group>
                               
                             </group>
                        </page>
                        <page string="Technical">
                            <group>
                                <group>
                                    <field name="sync_type"/>
                                    <field name="company_corporate_type"/>
                                    <field name="po_lock"/>
                                    <field name="profitability_active"/>
                                </group>

                                <group>
                                    <field name="cost_center_active"/>
                                    <field name="cost_center_date"/>
                                    <field name="cost_center_budget_date"/>
                                </group>
                            </group>
                        </page>
                        <page string="TC Integration">
                            <group>
                                <group>
                                    <field name="is_hospital"/>
                                    <field name="sync_tc_active"/>
                                    <field name="sync_tc_type"/>
                                </group>
                                <group>
                                    <field name="sync_tc_api_url"
                                        attrs="{'invisible': ['|', ('sync_tc_active', '=', False), ('sync_tc_type', '!=', 'api')]}"/>
                                    <field name="sync_tc_sharing_path"
                                        attrs="{'invisible': ['|', ('sync_tc_active', '=', False), ('sync_tc_type', '!=', 'txt')]}"/>
                                </group>
                            </group>
                        </page>
                        <page string="External API">
                            <group>
                                <group>
                                    <field name="sync_id_api" invisible="1"/>
                                    <field name="sync_api_active"/>
                                    <field name="sync_api_stock_active"/>
                                    <field name="sync_api_move_active"/>
                                    <field name="his_api_url"/>
                                    <field name="his_api_key"/>
                                </group>
                                <group>
                                    <field name="his_api_login"/>
                                    <field name="his_api_password"/>
                                </group>
                            </group>
                            <group>
                                <group>
                                    <field name="api_arcus_active"/>
                                    <field name="api_backend_active"/>
                                    <field name="api_backend_endpoint"/>
                                    <field name="api_backend_key"/>
                                </group>
                                <group>
                                    <field name="api_backend_active_mobile"/>
                                    <field name="api_backend_endpoint_mobile"/>
                                    <field name="api_backend_key_mobile"/>
                                </group>
                            </group>
                        </page>
                        <page string="Sign and Print out">
                            <group string="Payment Voucher">

                                <group>
                                    <field name="position1"/>
                                    <field name="position2"/>
                                    <field name="position3"/>
                                    <field name="position4"/>
                                    <field name="position5"/>
                                    <field name="position6"/>
                                </group>
                                <group>
                                    <field name="ttd1"/>
                                    <field name="ttd2"/>
                                    <field name="ttd3"/>
                                    <field name="ttd4"/>
                                    <field name="ttd5"/>
                                    <field name="ttd6"/>
                                </group>

                            </group>
                            <group string="AR Detail">
                                <group>
                                    <field name="cl_enable"/>
                                    <field name="cl_beneficiary"/>
                                    <field name="cl_account"/>
                                    <field name="cl_bank_name"/>
                                </group>
                                <group>
                                    <field name="cl_pic"/>
                                    <field name="cl_pic_email"/>
                                    <field name="cl_ttd"/>
                                    <field name="cl_dept"/>
                                </group>
                            </group>
                            <group string="Doctor Fee">
                                <group>
                                    <field name="df_ttd1"/>
                                    <field name="df_title1"/>
                                    <field name="df_sign_1" widget="image" style="max-width: 200px; height: auto;"/>
                                    <field name="df_city"/>
                                </group>
                                <group>
                                    <field name="df_ttd2"/>
                                    <field name="df_title2"/>
                                    <field name="df_sign_2" widget="image" style="max-width: 200px; height: auto;"/>
                                </group>
                            </group>

                            <group string="Marketing Fee">
                                <group>
                                    <field name="marketing_ttd1"/>
                                    <field name="marketing_ttd2"/>
                                </group>
                                <group>
                                    <field name="marketing_ttd3"/>
                                    <field name="marketing_ttd4"/>
                                </group>
                            </group>

                            <group string="Marketing Title">
                                <group>
                                    <field name="marketing_title1"/>
                                    <field name="marketing_title2"/>
                                </group>
                                <group>
                                    <field name="marketing_title3"/>
                                    <field name="marketing_title4"/>
                                </group>
                            </group>

                            <group string="COGS">
                                <field name="cogs_from_odoo"/>
                            </group>

                        </page>
                        <page string="Jasper and Internal API">
                            <group>
                                <group>
                                    <field name="url_host_jasper"/>
                                    <field name="uname_jasper"/>
                                    <field name="pass_jasper"/>
                                    <field name="sync_consol_type"/>
                                    <field name="sync_consol_id_unit"/>
                                    <field name="sync_consol_id_main"/>
                                    <field name="sync_consol_url"/>
                                    <field name="sync_consol_active"/>
                                </group>
                                <group>
                                    <field name="sync_consol_active_contact"/>
                                    <field name="sync_consol_active_account"/>
                                    <field name="sync_consol_active_inventory"/>
                                    <field name="sync_consol_active_purchase"/>
                                    <field name="sync_consol_active_user"/>
                                    <field name="sync_consol_active_1_way"/>
                                </group>
                            </group>
                        </page>

                        <page string="Internal API Model">

                            <group>
                                <group string="Account">
                                    <field name="sync_consol_account_account_type"/>
                                    <field name="sync_consol_account_account"/>
                                    <field name="sync_consol_account_journal"/>
                                    <field name="sync_consol_account_tax"/>
                                    <field name="sync_consol_account_analytic_account"/>
                                    <field name="sync_consol_account_payment"/>
                                    <field name="sync_consol_account_move"/>
                                    <field name="sync_consol_res_partner"/>
                                    <field name="sync_consol_res_bank"/>
                                    <field name="sync_consol_bank_information"/>
                                    <field name="sync_consol_budget_type"/>
                                    <field name="sync_consol_budget_approval"/>
                                    <field name="sync_consol_budget_position"/>
                                    <field name="sync_consol_crossovered_budget"/>
                                    
                                </group>
                                <group string="Purchase">
                                    <field name="sync_consol_purchase_requisition"/>
                                    <field name="sync_consol_purchase_order"/>
                                    <field name="sync_consol_purchase_approval"/>
                                    <field name="sync_consol_purchase_type"/>
                                    <field name="sync_consol_purchase_tax"/>
                                
                                </group>
                            </group>
                            <group>
                                <group string="Setting">
                                    <field name="sync_consol_res_user"/>
                                    <field name="sync_consol_hr_department"/>
                                    <field name="sync_consol_res_position"/>
                                    <field name="sync_consol_res_group"/>
                                    <field name="sync_consol_ir_attachment"/>
                                    <field name="sync_consol_mail_message"/>
                                    <field name="sync_consol_password"/>
                                </group>
                                <group string="Inventory and Product">
                                    <field name="sync_consol_service_group"/>
                                    <field name="sync_consol_product_category"/>
                                    <field name="sync_consol_product_uom"/>
                                    <field name="sync_consol_product_template"/>
                                    <field name="sync_consol_stock_warehouse"/>
                                    <field name="sync_consol_stock_location"/>
                                
                                </group>
                            </group>
                        </page>

                        <page string="AP-AR &amp; VA">
                            <group string="AR Cutoff &amp; Bank">
                                <group>
                                    <field name="cutoff_ap_aging"/>
                                    <field name="cutoff_ar_aging"/>
                                    <field name="virtual_enable"/>
                                </group>
                                <group>
                                    <field name="virtual_beneficary" attrs="{'readonly': [('virtual_enable', '=', False)]}"/>
                                    <field name="virtual_number" attrs="{'readonly': [('virtual_enable', '=', False)]}"/>
                                    <field name="virtual_bank" attrs="{'readonly': [('virtual_enable', '=', False)]}"/>
                                </group>
                            </group>
                            <group string="AR Account">
                                <group>
                                    <field name="receivable_cash_id" domain="[('company_id','=', id), ('parent','=', False)]"/>
                                    <field name="receivable_credit_id" domain="[('company_id','=', id), ('parent','=', False)]"/>
                                </group>
                                <group>
                                    <field name="receivable_debt_id" domain="[('company_id','=', id), ('parent','=', False)]"/>
                                    <field name="receivable_deposit_id" domain="[('company_id','=', id), ('parent','=', False)]"/>
                                </group>
                            </group>
                            <group string="AR Account">
                                <group>
                                    <field name="reveivable_receipt_cash_id" domain="[('company_id','=', id), ('parent','=', False)]"/>
                                    <field name="reveivable_receipt_credit_id" domain="[('company_id','=', id), ('parent','=', False)]"/>
                                    <field name="reveivable_receipt_debit_id" domain="[('company_id','=', id), ('parent','=', False)]"/>
                                </group>
                                <group>
                                    <field name="reveivable_receipt_transfer_id" domain="[('company_id','=', id), ('parent','=', False)]"/>
                                    <field name="reveivable_receipt_voucher_id" domain="[('company_id','=', id), ('parent','=', False)]"/>
                                    <field name="reveivable_receipt_cheque_id" domain="[('company_id','=', id), ('parent','=', False)]"/>
                                </group>
                            </group>
                        </page>
                        <page string="HIS Slave">
                            <group>
                                <group>
                                    <field name="odoo_url_public"/>
                                </group>
                                <group>
                                    <field name="odoo_url_local"/>
                                </group>
                            </group>
                            <group>
                                <group>
                                    <field name="his_slave_host"/>
                                    <field name="his_slave_port" />
                                </group>
                                <group>
                                    <field name="his_slave_db" />
                                    <field name="his_slave_login"/>
                                    <field name="his_slave_pass"/>
                                </group>
                            </group>
                            <group>
                                <group>
                                    <field name="local_host"/>
                                    <field name="local_port"/>
                                </group>
                                <group>
                                    <field name="local_db" />
                                    <field name="local_user" />
                                    <field name="local_pass"/>
                                </group>
                            </group>
                            <group>
                                <group>
                                    <field name="consol_host"/>
                                    <field name="consol_port"/>
                                </group>
                                <group>
                                    <field name="consol_db" />
                                    <field name="consol_user" />
                                    <field name="consol_pass"/>
                                </group>
                            </group>
                        </page>
                        <page string="Password Policy">
                            <group>
                                <field name="password_default"/>
                                <field name="password_length"/>
                                <field name="password_lower"/>
                                <field name="password_upper"/>
                                <field name="password_numeric"/>
                                <field name="password_special"/>
                                <field name="password_previous"/>
                            </group>
                        </page>
                        <page name="background" string="Apps Dashboard">
                            <group name="dashboard_settings">
                                <!--field name="background_image" widget="image" class="oe_avatar"/-->
                            </group>
                        </page>
                    </notebook>
                </sheet>
                <!--div class="oe_chatter">
                        <field name="message_follower_ids"/>
                        <field name="message_ids"/>
                    </div-->
            </form>
        """
        elif view_type == 'tree':
            res['arch'] = """
                <tree string="Positions" delete="false">
                    <field name="name"/>
                    <field name="sync_type"/>
                    <field name="is_hospital" optional="hide"/>
                </tree>
            """
        from lxml import etree
        doc = etree.XML(res['arch'])
        View = self.env['ir.ui.view'].sudo()
        res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
        return res


    # 2024.10.09 - Override validation for draft JE on lock advisor
    def _validate_fiscalyear_lock(self, values):
        print('do something..')
        # if values.get('fiscalyear_lock_date'):

        #     draft_entries = self.env['account.move'].search([
        #         ('company_id', 'in', self.ids),
        #         ('state', '=', 'draft'),
        #         ('date', '<=', values['fiscalyear_lock_date'])])
        #     if draft_entries:
        #         error_msg = _('There are still unposted entries in the period you want to lock. You should either post or delete them.')
        #         action_error = {
        #             'view_mode': 'tree',
        #             'name': 'Unposted Entries',
        #             'res_model': 'account.move',
        #             'type': 'ir.actions.act_window',
        #             'domain': [('id', 'in', draft_entries.ids)],
        #             'search_view_id': [self.env.ref('account.view_account_move_filter').id, 'search'],
        #             'views': [[self.env.ref('account.view_move_tree').id, 'list'], [self.env.ref('account.view_move_form').id, 'form']],
        #         }
        #         raise RedirectWarning(error_msg, action_error, _('Show unposted entries'))

        #     unreconciled_statement_lines = self.env['account.bank.statement.line'].search([
        #         ('company_id', 'in', self.ids),
        #         ('is_reconciled', '=', False),
        #         ('date', '<=', values['fiscalyear_lock_date']),
        #         ('move_id.state', 'in', ('draft', 'posted')),
        #     ])
        #     if unreconciled_statement_lines:
        #         error_msg = _("There are still unreconciled bank statement lines in the period you want to lock."
        #                     "You should either reconcile or delete them.")
        #         action_error = self._get_fiscalyear_lock_statement_lines_redirect_action(unreconciled_statement_lines)
        #         raise RedirectWarning(error_msg, action_error, _('Show Unreconciled Bank Statement Line'))






class ResGroups(models.Model):
    _inherit = 'res.groups'

    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    sync_consol_log = fields.Char(string="Console Log", index=True, readonly=True)
    
    user_id_cek = fields.Char(string="User ID")
    company_name = fields.Char(string="Company Name")
    # name = fields.Char(string="Name", translate=False)
    # comment = fields.Char(string="Comment", translate=False)
    is_non_default = fields.Boolean(string="Is Non Default")

    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")

    @api.model
    def create(self, vals):
        # from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
        # from datetime import datetime
        # import os

        # # define now datetime
        # now = datetime.now()
        # now_formatted = now.strftime("%Y-%m-%d %H:%M:%S")

        # # define python timezone
        # import pytz
        # local = pytz.timezone('Asia/Jakarta')
        # log_date = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y%m%d")
        # log_year = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y")
        # log_month = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        # log_day = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        # #log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local),"%H%M%S.%f")
        # log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        # log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'res.groups' + '/'
        # log_name = log_date + '_' + 'create' + '_' + 'res.groups'
        # log_file = log_dir + log_name + '.log'

        # log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # # create dir if not exists
        # if not os.path.exists(log_dir):
        #     os.makedirs(log_dir)
        # os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        # message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        # message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Create "

        # open(log_file, 'a').write(message_log)
        result = super(ResGroups, self).create(vals)
        result.send_api_consol()
        # log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        # message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        # message_log += "\n\nuser: " + self.env.user.login + "\n\n Create before return" + "\n ID: " +str(result.id)

        # open(log_file, 'a').write(message_log)
        return result

    # @api.multi
    def send_api_consol(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            list_company = ''
            company = self.env['res.company'].search([('sync_consol_res_group','=',True)])
            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_res_group
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/create/res.groups"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/create/res.groups"
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
                    values['sync_type'] = str(company_id.sync_type)
                    # values['sync_type'] = int(record.env.company.sync_type)
                    # values[consol_id_from] = record.id
                    values[consol_id_from] = str(record.id)

                    ####### Yang harus dirubah field-field yang mau dikirim ###########
                    values['name'] = record.name
                    values['share'] = record.share
                    if consol_type == 'unit':
                        sync_consol_id_main = str(self.env.user.login)
                        company_name = company_id.name
                        values['company_name'] = company_name
                        values['user_id_cek'] = sync_consol_id_main
                    if consol_type == 'main':
                        sync_consol_id_main = str(self.env.user.login)
                        company_name = company_id.name
                        values['company_name'] = company_name
                        values['user_id_cek'] = sync_consol_id_main
                    # karena tidak ada sync_consol di object ir.module.category
                    # if record.category_id.id == False:
                    #     values['category_id'] = record.category_id.id
                    # else:
                    #     values['category_id'] = str(record.category_id.id)
                    values['comment'] = record.comment
                    
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
                        # 'sync_consol_sent' : data_sent,
                        'sync_consol_log': list_company
                    }
                    super(ResGroups, self).write(data_update)

    # @api.multi
    def write(self, vals):
        # from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
        # from datetime import datetime
        # import os

        # # define now datetime
        # now = datetime.now()
        # now_formatted = now.strftime("%Y-%m-%d %H:%M:%S")

        # # define python timezone
        # import pytz
        # local = pytz.timezone('Asia/Jakarta')
        # log_date = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y%m%d")
        # log_year = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%Y")
        # log_month = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%m")
        # log_day = datetime.strftime(pytz.utc.localize(datetime.strptime(now_formatted, DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local), "%d")
        # #log_time = datetime.strftime(pytz.utc.localize(datetime.strptime(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),DEFAULT_SERVER_DATETIME_FORMAT)).astimezone(local),"%H%M%S.%f")
        # log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        # log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'write' + '/' + 'res.groups' + '/'
        # log_name = log_date + '_' + 'write' + '_' + 'res.groups'
        # log_file = log_dir + log_name + '.log'

        # log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # # create dir if not exists
        # if not os.path.exists(log_dir):
        #     os.makedirs(log_dir)
        # os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        # message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        # message_log += "\n\nuser: " + self.env.user.login + "\n\n Start Write "

        # open(log_file, 'a').write(message_log)
        result = super(ResGroups, self).write(vals)
        self.send_api_consol_write()
        # log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        # message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        # message_log += "\n\nuser: " + self.env.user.login + "\n\n Write before return" + "\n ID: " +str(self.id)

        # open(log_file, 'a').write(message_log)
        return result





    # @api.multi
    def send_api_consol_write(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        open('/opt/odoo16/logs/log_res_group.log','a+').write('\n\n' + str('xxx'))
        for record in self:
            list_company = ''
            company = self.env['res.company'].search([('sync_consol_res_group','=',True)])
            open('/opt/odoo16/logs/log_res_group.log','a+').write('\n\n' + str(company))
            for company_id in company:
                list_company += str(company_id.name) + ', '+ '\n'
                consol_active = company_id.sync_consol_res_group
                consol_url = company_id.sync_consol_url
                consol_type = company_id.sync_consol_type
                consol_id_to = ""
                consol_id_from = ""
                if consol_active:
                    if consol_type == 'unit':
                        url = consol_url + "/internal_api/unit/write/res.groups"
                        consol_id_to = 'sync_consol_id_main'
                        consol_id_from = 'sync_consol_id_unit'
                    if consol_type == 'main':
                        url = consol_url + "/internal_api/main/write/res.groups"
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
                    values['sync_type'] = str(company_id.sync_type)
                    # values['sync_type'] = int(record.env.company.sync_type)
                    # values[consol_id_from] = record.id
                    values[consol_id_from] = str(record.id)

                    ####### Yang harus dirubah field-field yang mau dikirim ###########
                    values['name'] = record.name
                    values['share'] = record.share
                    if consol_type == 'unit':
                        sync_consol_id_main = str(self.env.user.login)
                        company_name = company_id.name
                        values['company_name'] = company_name
                        values['user_id_cek'] = sync_consol_id_main
                    if consol_type == 'main':
                        sync_consol_id_main = str(self.env.user.login)
                        company_name = company_id.name
                        values['company_name'] = company_name
                        values['user_id_cek'] = sync_consol_id_main
                    # karena tidak ada sync_consol di object ir.module.category
                    # if record.category_id.id == False:
                    #     values['category_id'] = record.category_id.id
                    # else:
                    #     values['category_id'] = str(record.category_id.id)
                    values['comment'] = record.comment
                    # if consol_type == 'unit':
                    #     sync_consol_id_main = str(self.env.user.login)
                    #     company_name = record.company_id.name
                    #     values['company_name'] = company_name
                    #     values['user_id_cek'] = sync_consol_id_main
                    # if consol_type == 'main':
                    #     sync_consol_id_main = str(self.env.user.login)
                    #     company_name = record.company_id.name
                    #     values['company_name'] = company_name
                    #     values['user_id_cek'] = sync_consol_id_main


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
                        # 'sync_consol_sent' : data_sent,
                        'sync_consol_log': list_company
                    }
                    super(ResGroups, self).write(data_update)


    # @api.multi
    def empty(self):
        self.menu_access = False


    # @api.model
    # def get_view(self,view_id=None, view_type='form', **options):
    #     res = super(ResGroups,self).get_view(view_id=view_id,view_type=view_type, **options)
    #     if view_type == 'form':
    #         res['arch'] = """
    #             <form string="Groups" delete="false">
    #               <sheet>
    #                 <group col="4">
    #                     <field name="category_id"/>
    #                     <field name="name"/>
    #                     <field name="share"/>
                        
    #                 </group>
    #                 <notebook>
    #                     <page string="Users">
    #                         <field name="users" context="{'search_default_no_share':1}"/>
    #                     </page>
    #                     <page string="Inherited">
    #                         <label string="Users added to this group are automatically added in the following groups."/>
    #                         <field name="implied_ids"/>
    #                     </page>
    #                     <page string="Menus">
    #                         <field name="menu_access"/>
    #                     </page>
    #                     <page string="Views">
    #                         <field name="view_access"/>
    #                     </page>
    #                     <page string="Access Rights">
    #                         <field name="model_access">
    #                             <tree string="Access Rules" editable="top">
    #                                 <field name="model_id"/>
    #                                 <field name="perm_read"/>
    #                                 <field name="perm_write"/>
    #                                 <field name="perm_create"/>
    #                                 <field name="perm_unlink"/>
    #                                 <field name="name"/>
    #                             </tree>
    #                             <form string="Access Controls">
    #                                 <group col="4">
    #                                     <field name="name"/>
    #                                     <field name="active"/>
    #                                     <field name="model_id"/>
    #                                     <newline/>
    #                                     <field name="perm_read"/>
    #                                     <field name="perm_write"/>
    #                                     <field name="perm_create"/>
    #                                     <field name="perm_unlink"/-->
    #                                 </group>
    #                             </form>
    #                         </field>
    #                     </page>
    #                     <page string="Rules">
    #                         <field name="rule_groups">
    #                             <tree string="Rules">
    #                                 <field name="name"/>
    #                                 <field name="model_id"/>
    #                                 <field name="global"/>
    #                             </tree>
    #                         </field-->
    #                     </page>
    #                     <page string="Notes">
    #                         <field name="comment"/>
    #                     </page>
    #                     <page string="Technical">
    #                         <group>
    #                             <field name="sync_type"/>
    #                             <field name="sync_consol_id_unit" readonly="1"/>
    #                             <field name="sync_consol_id_main" readonly="1"/>
    #                             <field name="sync_consol_log"/>
    #                         </group>
    #                     </page>
    #                 </notebook>
    #               </sheet>
    #             </form>
    #         """
    #     elif view_type == 'tree':
    #         res['arch'] = """
    #             <tree string="Groups" delete="false">
    #                 <field name="name"/>
    #                 <field name="category_id"/>
    #                 <field name="sync_type"/>
    #             </tree>
    #         """
    #     from lxml import etree
    #     doc = etree.XML(res['arch'])
    #     View = self.env['ir.ui.view'].sudo()
    #     res['arch'], res['fields'] = View.postprocess_and_fields(doc, self._name, validate=True)
    #     return res





# 20230516 - Bulky Block Users existing for each site
class BlockUsersBulkWizard(models.TransientModel):
    _name = 'block.user.bulk.wizard'

    @api.model
    def _get_company(self):
        return self.env.company.id
    
    @api.model
    def _get_user(self):
        return self.env.user.id


    company_id = fields.Many2one('res.company', string='Company', default=_get_company)
    user_id = fields.Many2one('res.users', string="Responsible", default=_get_user)
    user_ids = fields.Many2many('res.users', 'block_user_bulk_wizard_rel', string="List Users")





    # @api.multi
    def action_block(self):      
        for record in self:
            if record.user_ids:
                for user in record.user_ids:
                    user.block_user_consol(user_id=user.login, check='')



class ConsolMailMessage(models.Model):
    _inherit = 'mail.message'

    @api.model
    def _get_default_company(self):
        return self.env.company.id 

    company_id = fields.Many2one('res.company', string="Company", default=_get_default_company)
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    #####Chaelvin
    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")
    no_auto_thread = fields.Boolean(string="No Auto Thread")
    website_published = fields.Boolean(string="Website Published")


class ConsolIrAttachment(models.Model):
    _inherit = 'ir.attachment'
    sync_type = sync.type
    sync_consol_id_unit = sync.consol_id_unit
    sync_consol_id_main = sync.consol_id_main
    sync_consol_date = sync.consol_date
    #####Chaelvin
    trigger_create = fields.Boolean(string="Trigger Create")
    trigger_write = fields.Boolean(string="Trigger Write")

    ############Chaelvin##############
    @api.model
    def create(self, vals):

        if vals.get('res_id') and vals.get('res_model') in ('purchase.requisition','purchase.order','crossovered.budget'):
            check_company_id = self.env[vals.get('res_model')].search([('id','=',vals.get('res_id'))], limit=1)
            if check_company_id:
                vals['company_id'] = check_company_id.company_id.id

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
        log_dir = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day + '/' + 'create' + '/' + 'ir.attachment' + '/'
        log_name = log_date + '_' + 'create' + '_' + 'ir.attachment'
        log_file = log_dir + log_name + '.log'

        log_dir_day = '/opt/odoo16/logs/consol/' + log_year + '/' + log_month + '/' + log_day

        # create dir if not exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        os.system('echo Mayapada@12345!!! | sudo -S chown -R odoo:odoo ' + log_dir_day)

        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + str(self.env.user.login) + "\n\n Start Create "

        open(log_file, 'a').write(message_log)
        result = super(ConsolIrAttachment, self).create(vals)
        if vals.get('company_id'):
            company_id = self.env['res.company'].search([('id','=',vals.get('company_id'))], limit=1)
            result.sync_type = company_id.sync_type
        if result.trigger_create == False and result.res_model in ('purchase.requisition','purchase.order'):
            result.send_api_consol_company()
        log_time =  datetime.strftime(pytz.utc.localize(datetime.now()).astimezone(local) ,"%Y-%m-%d %H:%M:%S.%f")
        message_log = "\n\n================= start ===================\n\ntimelog: " + str(log_time)
        message_log += "\n\nuser: " + str(self.env.user.login) + "\n\n Create before return" + "\n ID: " +str(result.id)

        open(log_file, 'a').write(message_log)
        return result

    # @api.multi
    def send_api_consol_company(self):
        now = tools.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for record in self:
            # consol_active = record.env.company.sync_consol_ir_attachment
            # consol_url = record.env.company.sync_consol_url
            # consol_type = record.env.company.sync_consol_type
            consol_active = record.company_id.sync_consol_ir_attachment
            consol_url = record.company_id.sync_consol_url
            consol_type = record.company_id.sync_consol_type
            consol_id_to = ""
            consol_id_from = ""
            if consol_active:
                if consol_type == 'unit':
                    url = consol_url + "/internal_api/unit/attachment/create/ir.attachment"
                    consol_id_to = 'sync_consol_id_main'
                    consol_id_from = 'sync_consol_id_unit'
                if consol_type == 'main':
                    url = consol_url + "/internal_api/main/attachment/create/ir.attachment"
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
                tes111 = record.datas
                values['sync_type'] = str(record.company_id.sync_type)
                # values['sync_type'] = int(record.env.company.sync_type)
                # values[consol_id_from] = record.id
                values[consol_id_from] = str(record.id)
                values['name'] = str(record.name)
                values['type'] = record.type
                values['datas'] = record.datas
                # values['datas'] = base64.b64decode(record.datas)
                values['datas_fname'] = record.datas_fname
                values['url'] = record.url
                values['mimetype'] = record.mimetype
                values['res_model'] = record.res_model
                values['res_field'] = record.res_field
                values['res_id'] = record.res_id
                values['res_name'] = record.res_name
                values['public'] = record.public
                values['trigger_create'] = True
                company_name = record.company_id.name
                sync_consol_id_main = str(self.env.user.login)
                body['company_name'] = company_name
                body['user_consol_main'] = sync_consol_id_main
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
                
                
                #print('\n' + "body : " + str(body))
                #print('\n' + "headers : " + str(headers))
                #print('\n' + "url : " + str(url))

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
                    ############Chaelvin##############
                    open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(record.env.user.token_consol))
                    open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(body))
                
                    response_json = requests.post(url=url, headers=headers, data=body, verify=False, cookies=cookies)

                try:
                    json_resp = response_json.json()
                    # open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(values))
                    open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(body))
                
                    open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str('try'))
                    open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str(response_json))
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
                    open('/opt/odoo16/logs/test_sync_id_api.log', 'a+').write('\n' + str('except'))

                api_status = 'failed'
                #print('\n' + "json_resp : " + str(json_resp))

                data_sent = False
                response_id = False

                if 'status' in json_resp:
                    if json_resp['status'] == 'success':
                        
                        api_status = 'success'
                        data_sent = True
                        for d in json_resp['data']:
                            if 'id' in d:
                                response_id = d['id']
                    if json_resp['status'] == 'error':
                        
                        # raise exceptions.ValidationError(_('Data Gagal Dibuat'))
                        raise exceptions.ValidationError(_(json_resp['message']))


                data_update = {
                    consol_id_to : response_id,
                    'sync_consol_response': json_resp,
                    'sync_consol_response_status': api_status,
                    'sync_consol_date': now,
                    'sync_consol_sent' : data_sent
                }
                super(ConsolIrAttachment, self).write(data_update)

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(ConsolIrAttachment,self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        View = self.env['ir.ui.view'].sudo()
        from lxml import etree
        if res.get('view_id'):
            view_id = res['view_id']
        if view_id:
            root_view = View.browse(view_id).read_combined(['arch'])
            res['arch'] = root_view['arch']
        doc = etree.XML(res['arch'])
        if view_type == 'form':
            doc = View.apply_inheritance_specs(doc, etree.XML("""
            <data>
                <xpath expr="//field[@name='mimetype']" position="after">
                    <field name="trigger_create"/>
                    <field name="trigger_write"/>    
                </xpath>
            </data>
            """), view_id)
        
        res['arch'], res['fields'] = View.postprocess_and_fields(self._name, doc, view_id)
        return res



class ChangePasswordUser(models.TransientModel):
    """ A model to configure users in the change password wizard. """
    _inherit = 'change.password.user'

    # @api.multi
    def change_password_button(self):
        open('/opt/odoo16/logs/log_change_password.log', 'a+').write('\n' + 'masuk sini 11111111111111')
        for line in self:
            line.user_id.write({'password': line.new_passwd, 'password_consol': line.new_passwd})
            line.user_id.change_password_api_consol(user_id=line.user_id, new_passwd=line.new_passwd)
            
        # don't keep temporary passwords in the database longer than necessary
        self.write({'new_passwd': False})


class WizardDialogReport(models.TransientModel):
    _name = 'wizard.dialog.report'
 
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.company)
    parameter = fields.Char(string="Parameter")
    iframe = fields.Html(string="Preview", sanitize=False, compute='_get_html')
 
 
    @api.depends('parameter')
    def _get_html (self): 
        for record in self: 
            # http://localhost:8080/jasperserver/flow.html?_flowId=viewReportFlow&_flowId=viewReportFlow&ParentFolderUri=%2Freports%2FHIS&reportUnit=%2Freports%2FHIS%2FPrint_IP_Main_Sub&decorate=no&j_username=jasperadmin&j_password=jasperadmin&viewAsDashboardFrame=false&standAlone=true&sub_id=151&user_id=FIRGIAWAN
            full_path = record.company_id.url_host_jasper + '?' + record.parameter
            open('/opt/odoo16/logs/log_frame.log','a+').write('\n\n' + str(full_path))
            record.iframe = f'<iframe src="{full_path}" width="800" height="500" scrolling="no" marginheight="0" marginwidth="0" seamless="seamless" style="transform-origin: top left; transform: scale(1.0);" />'


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'
    _description = 'Email Thread'

    def message_post(self, *,
                     body='', subject=None, message_type='notification',
                     email_from=None, author_id=None, parent_id=False,
                     subtype_xmlid=None, subtype_id=False, partner_ids=None,
                     attachments=None, attachment_ids=None,
                     **kwargs):
        """ Post a new message in an existing thread, returning the new mail.message.

        :param str body: body of the message, usually raw HTML that will
            be sanitized
        :param str subject: subject of the message
        :param str message_type: see mail_message.message_type field. Can be anything but
            user_notification, reserved for message_notify
        :param str email_from: from address of the author. See ``_message_compute_author``
            that uses it to make email_from / author_id coherent;
        :param int author_id: optional ID of partner record being the author. See
            ``_message_compute_author`` that uses it to make email_from / author_id coherent;
        :param int parent_id: handle thread formation
        :param int subtype_id: subtype_id of the message, used mainly for followers
            notification mechanism;
        :param list(int) partner_ids: partner_ids to notify in addition to partners
            computed based on subtype / followers matching;
        :param list(tuple(str,str), tuple(str,str, dict)) attachments : list of attachment
            tuples in the form ``(name,content)`` or ``(name,content, info)`` where content
            is NOT base64 encoded;
        :param list attachment_ids: list of existing attachments to link to this message
            -Should only be set by chatter
            -Attachment object attached to mail.compose.message(0) will be attached
                to the related document.

        Extra keyword arguments will be used either
          * as default column values for the new mail.message record if they match
            mail.message fields;
          * propagated to notification methods;

        :return record: newly create mail.message
        """
        open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "message_post")
        self.ensure_one()  # should always be posted on a record, use message_notify if no record
        # split message additional values from notify additional values
        msg_kwargs = dict((key, val) for key, val in kwargs.items() if key in self.env['mail.message']._fields)
        notif_kwargs = dict((key, val) for key, val in kwargs.items() if key not in msg_kwargs)

        # preliminary value safety check
        partner_ids = set(partner_ids or [])
        if self._name == 'mail.thread' or not self.id or message_type == 'user_notification':
            raise ValueError(_('Posting a message should be done on a business document. Use message_notify to send a notification to an user.'))
        if 'channel_ids' in kwargs:
            raise ValueError(_("Posting a message with channels as listeners is not supported since Odoo 14.3+. Please update code accordingly."))
        if 'model' in msg_kwargs or 'res_id' in msg_kwargs:
            raise ValueError(_("message_post does not support model and res_id parameters anymore. Please call message_post on record."))
        if 'subtype' in kwargs:
            raise ValueError(_("message_post does not support subtype parameter anymore. Please give a valid subtype_id or subtype_xmlid value instead."))
        if any(not isinstance(pc_id, int) for pc_id in partner_ids):
            raise ValueError(_('message_post partner_ids and must be integer list, not commands.'))

        self = self._fallback_lang() # add lang to context immediately since it will be useful in various flows latter.

        # Find the message's author
        if self.env.user._is_public() and 'guest' in self.env.context:
            author_guest_id = self.env.context['guest'].id
            author_id, email_from = False, False
        else:
            author_guest_id = False
            author_id, email_from = self._message_compute_author(author_id, email_from, raise_on_email=True)

        if subtype_xmlid:
            subtype_id = self.env['ir.model.data']._xmlid_to_res_id(subtype_xmlid)
        if not subtype_id:
            subtype_id = self.env['ir.model.data']._xmlid_to_res_id('mail.mt_note')

        # automatically subscribe recipients if asked to
        if self._context.get('mail_post_autofollow') and partner_ids:
            self.message_subscribe(partner_ids=list(partner_ids))

        msg_values = dict(msg_kwargs)
        if 'email_add_signature' not in msg_values:
            msg_values['email_add_signature'] = True
        if not msg_values.get('record_name'):
            msg_values['record_name'] = self.display_name
        msg_values.update({
            'author_id': author_id,
            'author_guest_id': author_guest_id,
            # 'email_from': email_from,
            'email_from': 'odoo@mayapadahospital.com',
            'model': self._name,
            'res_id': self.id,
            # content
            'body': body,
            'subject': subject or False,
            'message_type': message_type,
            'parent_id': self._message_compute_parent_id(parent_id),
            'subtype_id': subtype_id,
            # recipients
            'partner_ids': partner_ids,
        })

        open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "msg_values : " + str(msg_values))
        attachments = attachments or []
        attachment_ids = attachment_ids or []
        attachement_values = self._message_post_process_attachments(attachments, attachment_ids, msg_values)
        msg_values.update(attachement_values)  # attachement_ids, [body]

        new_message = self._message_create(msg_values)

        # Set main attachment field if necessary
        self._message_set_main_attachment_id(msg_values['attachment_ids'])

        if msg_values['author_id'] and msg_values['message_type'] != 'notification' and not self._context.get('mail_create_nosubscribe'):
            if self.env['res.partner'].browse(msg_values['author_id']).active:  # we dont want to add odoobot/inactive as a follower
                self._message_subscribe(partner_ids=[msg_values['author_id']])

        self._message_post_after_hook(new_message, msg_values)
        self._notify_thread(new_message, msg_values, **notif_kwargs)
        return new_message



    def _notify_thread_by_inbox(self, message, recipients_data, msg_vals=False, **kwargs):
        """ Notification method: inbox. Does two main things :

          * create inbox notifications for users;
          * send bus notifications;

        :param message: ``mail.message`` record to notify;
        :param recipients_data: list of recipients information (based on res.partner
          records), formatted like
            [{'active': partner.active;
              'id': id of the res.partner being recipient to notify;
              'groups': res.group IDs if linked to a user;
              'notif': 'inbox', 'email', 'sms' (SMS App);
              'share': partner.partner_share;
              'type': 'customer', 'portal', 'user;'
             }, {...}].
          See ``MailThread._notify_get_recipients``;
        :param msg_vals: dictionary of values used to create the message. If given it
          may be used to access values related to ``message`` without accessing it
          directly. It lessens query count in some optimized use cases by avoiding
          access message content in db;
        """
        bus_notifications = []
        inbox_pids = [r['id'] for r in recipients_data if r['notif'] in ['inbox','email']]
        if inbox_pids:
            notif_create_values = [{
                'author_id': message.author_id.id,
                'mail_message_id': message.id,
                'res_partner_id': pid,
                'notification_type': 'inbox',
                'notification_status': 'sent',
            } for pid in inbox_pids]
            self.env['mail.notification'].sudo().create(notif_create_values)

            message_format_values = message.message_format()[0]
            for partner_id in inbox_pids:
                bus_notifications.append((self.env['res.partner'].browse(partner_id), 'mail.message/inbox', dict(message_format_values)))
        self.env['bus.bus'].sudo()._sendmany(bus_notifications)

    def _notify_thread_by_email(self, message, recipients_data, msg_vals=False,
                                mail_auto_delete=True,  # mail.mail
                                model_description=False, force_email_company=False, force_email_lang=False,  # rendering
                                resend_existing=False, force_send=True, send_after_commit=True,  # email send
                                subtitles=None, **kwargs):
        """ Method to send email linked to notified messages.

        :param message: ``mail.message`` record to notify;
        :param recipients_data: list of recipients information (based on res.partner
          records), formatted like
            [{'active': partner.active;
              'id': id of the res.partner being recipient to notify;
              'groups': res.group IDs if linked to a user;
              'notif': 'inbox', 'email', 'sms' (SMS App);
              'share': partner.partner_share;
              'type': 'customer', 'portal', 'user;'
             }, {...}].
          See ``MailThread._notify_get_recipients``;
        :param msg_vals: dictionary of values used to create the message. If given it
          may be used to access values related to ``message`` without accessing it
          directly. It lessens query count in some optimized use cases by avoiding
          access message content in db;

        :param mail_auto_delete: delete notification emails once sent;

        :param model_description: model description used in email notification process
          (computed if not given);
        :param force_email_company: see ``_notify_by_email_prepare_rendering_context``;
        :param force_email_lang: see ``_notify_by_email_prepare_rendering_context``;

        :param resend_existing: check for existing notifications to update based on
          mailed recipient, otherwise create new notifications;
        :param force_send: send emails directly instead of using queue;
        :param send_after_commit: if force_send, tells whether to send emails after
          the transaction has been committed using a post-commit hook;
        :param subtitles: optional list that will be set as template value "subtitles"
        """
        partners_data = [r for r in recipients_data if r['notif'] in ['inbox','email']]
        if not partners_data:
            return True

        model = msg_vals.get('model') if msg_vals else message.model
        model_name = model_description or (self.env['ir.model']._get(model).display_name if model else False) # one query for display name
        recipients_groups_data = self._notify_get_recipients_classify(partners_data, model_name, msg_vals=msg_vals)

        if not recipients_groups_data:
            return True
        force_send = self.env.context.get('mail_notify_force_send', force_send)

        template_values = self._notify_by_email_prepare_rendering_context(
            message, msg_vals=msg_vals, model_description=model_description,
            force_email_company=force_email_company,
            force_email_lang=force_email_lang,
        ) # 10 queries
        if subtitles:
            template_values['subtitles'] = subtitles

        email_layout_xmlid = msg_vals.get('email_layout_xmlid') if msg_vals else message.email_layout_xmlid
        template_xmlid = email_layout_xmlid if email_layout_xmlid else 'mail.mail_notification_layout'
        base_mail_values = self._notify_by_email_get_base_mail_values(message, additional_values={'auto_delete': mail_auto_delete})

        # Clean the context to get rid of residual default_* keys that could cause issues during
        # the mail.mail creation.
        # Example: 'default_state' would refer to the default state of a previously created record
        # from another model that in turns triggers an assignation notification that ends up here.
        # This will lead to a traceback when trying to create a mail.mail with this state value that
        # doesn't exist.
        SafeMail = self.env['mail.mail'].sudo().with_context(clean_context(self._context))
        SafeNotification = self.env['mail.notification'].sudo().with_context(clean_context(self._context))
        emails = self.env['mail.mail'].sudo()

        # loop on groups (customer, portal, user,  ... + model specific like group_sale_salesman)
        notif_create_values = []
        recipients_max = 50
        for recipients_group_data in recipients_groups_data:
            # generate notification email content
            recipients_ids = recipients_group_data.pop('recipients')
            render_values = {**template_values, **recipients_group_data}
            # {company, is_discussion, lang, message, model_description, record, record_name, signature, subtype, tracking_values, website_url}
            # {actions, button_access, has_button_access, recipients}

            mail_body = self.env['ir.qweb']._render(template_xmlid, render_values, minimal_qcontext=True, raise_if_not_found=False, lang=template_values['lang'])
            if not mail_body:
                _logger.warning('QWeb template %s not found or is empty when sending notification emails. Sending without layouting.', template_xmlid)
                mail_body = message.body
            ####Chaelvin
            mail_body = self.env['mail.render.mixin']._replace_local_links(mail_body)

            # create email
            for recipients_ids_chunk in split_every(recipients_max, recipients_ids):
                mail_values = self._notify_by_email_get_final_mail_values(
                    recipients_ids_chunk,
                    base_mail_values,
                    ###Chaelvin
                    # additional_values={'body_html': mail_body}
                    additional_values={'body_html': mail_body,
                                       'email_cc': 'firgiawan.khafidli@mayapadahospital.com',
                                       'subject': f"Notification Odoo : {message.subject or message.record_name or model_name}"
                    }
                )
                new_email = SafeMail.create(mail_values)

                if new_email and recipients_ids_chunk:
                    tocreate_recipient_ids = list(recipients_ids_chunk)
                    if resend_existing:
                        existing_notifications = self.env['mail.notification'].sudo().search([
                            ('mail_message_id', '=', message.id),
                            ('notification_type', '=', 'email'),
                            ('res_partner_id', 'in', tocreate_recipient_ids)
                        ])
                        if existing_notifications:
                            tocreate_recipient_ids = [rid for rid in recipients_ids_chunk if rid not in existing_notifications.mapped('res_partner_id.id')]
                            existing_notifications.write({
                                'notification_status': 'ready',
                                'mail_mail_id': new_email.id,
                            })
                    notif_create_values += [{
                        'author_id': message.author_id.id,
                        'mail_message_id': message.id,
                        'res_partner_id': recipient_id,
                        'notification_type': 'email',
                        'mail_mail_id': new_email.id,
                        'is_read': True,  # discard Inbox notification
                        'notification_status': 'ready',
                    } for recipient_id in tocreate_recipient_ids]
                emails += new_email

        if notif_create_values:
            open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 27")
            # DIKOMEN CHAELVIN
            # SafeNotification.create(notif_create_values)

        # NOTE:
        #   1. for more than 50 followers, use the queue system
        #   2. do not send emails immediately if the registry is not loaded,
        #      to prevent sending email during a simple update of the database
        #      using the command-line.
        test_mode = getattr(threading.current_thread(), 'testing', False)
        if force_send and len(emails) < recipients_max and (not self.pool._init or test_mode):
            # unless asked specifically, send emails after the transaction to
            # avoid side effects due to emails being sent while the transaction fails
            if not test_mode and send_after_commit:
                email_ids = emails.ids
                dbname = self.env.cr.dbname
                _context = self._context

                @self.env.cr.postcommit.add
                def send_notifications():
                    db_registry = registry(dbname)
                    with db_registry.cursor() as cr:
                        env = api.Environment(cr, SUPERUSER_ID, _context)
                        env['mail.mail'].browse(email_ids).send()
            else:
                emails.send()

        return True

    def _notify_get_recipients_classify(self, recipient_data, model_name, msg_vals=None):
        """ Classify recipients to be notified of a message in groups to have
        specific rendering depending on their group. For example users could
        have access to buttons customers should not have in their emails.
        Module-specific grouping should be done by overriding ``_notify_get_recipients_groups``
        method defined here-under.

        :param recipient_data: list of recipients information (based on res.partner
          records). See ``MailThread._notify_get_recipients()``;

        :return list: list of groups formatted for notification processing like
            [{'active': True,
              'actions': [],
              'button_access': {},
              'has_button_access': False,
              'recipients': [11],},
             {'active': True,
              'actions': [],
              'button_access': {'title': 'View Simple Chatter Model',
                                'url': '/mail/view?model=mail.test.simple&res_id=1497'},
              'has_button_access': True,
              'recipients': [4, 5, 6],},
             {'active': True,
              'actions': [],
              'button_access': {'title': 'View Simple Chatter Model',
                                'url': '/mail/view?model=mail.test.simple&res_id=1497'},
              'has_button_access': True,
              'recipients': [10, 11, 12],}
            ]
        """
        # keep a local copy of msg_vals as it may be modified to include more information about groups or links
        local_msg_vals = dict(msg_vals) if msg_vals else {}
        groups = self._notify_get_recipients_groups(msg_vals=local_msg_vals)
        ####Chaelvin
        access_link = self._notify_get_action_link('view', **local_msg_vals)

        if model_name:
            view_title = _('View %s', model_name)
        else:
            view_title = _('View')

        # fill group_data with default_values if they are not complete
        for group_name, group_func, group_data in groups:
            is_thread_notification = self._notify_get_recipients_thread_info(msg_vals=msg_vals)['is_thread_notification']
            group_data.setdefault('active', True)
            group_data.setdefault('actions', list())
            group_data.setdefault('has_button_access', is_thread_notification)
            group_data.setdefault('notification_is_customer', False)
            group_data.setdefault('notification_group_name', group_name)
            group_data.setdefault('recipients', list())
            group_button_access = group_data.setdefault('button_access', {})
            ####Chaelvin
            group_button_access.setdefault('url', access_link)
            group_button_access.setdefault('title', view_title)

        # classify recipients in each group
        for recipient in recipient_data:
            for group_name, group_func, group_data in groups:
                if group_data['active'] and group_func(recipient):
                    group_data['recipients'].append(recipient['id'])
                    break

        # filter out groups without recipients
        return [group_data for _group_name, _group_func, group_data in groups
                if group_data['recipients']]



    def _notify_get_action_link(self, link_type, **kwargs):
        """ Prepare link to an action: view document, follow document, ... """
        params = {
            'model': kwargs.get('model', self._name),
            'res_id': kwargs.get('res_id', self.ids and self.ids[0] or False),
        }
        # keep only accepted parameters:
        # - action (deprecated), token (assign), access_token (view)
        # - auth_signup: auth_signup_token and auth_login
        # - portal: pid, hash
        params.update(dict(
            (key, value)
            for key, value in kwargs.items()
            if key in ('action', 'token', 'access_token', 'auth_signup_token',
                       'auth_login', 'pid', 'hash')
        ))

        if link_type in ['view', 'assign', 'follow', 'unfollow']:
            base_link = '/mail/%s' % link_type
        elif link_type == 'controller':
            controller = kwargs.get('controller')
            params.pop('model')
            base_link = '%s' % controller
        else:
            return ''

        if link_type not in ['view']:
            token = self._notify_encode_link(base_link, params)
            params['token'] = token

        link = '%s?%s' % (base_link, urls.url_encode(params))
        ###Chaelvin
        if self:
            link = self[0].get_base_url() + link

        return link


#     def _notify_thread_by_email(self, message, recipients_data, msg_vals=False,
#                                 mail_auto_delete=True,  # mail.mail
#                                 model_description=False, force_email_company=False, force_email_lang=False,  # rendering
#                                 resend_existing=False, force_send=True, send_after_commit=True,  # email send
#                                 subtitles=None, **kwargs):
#         """ Method to send email linked to notified messages.

#         :param message: ``mail.message`` record to notify;
#         :param recipients_data: list of recipients information (based on res.partner
#           records), formatted like
#             [{'active': partner.active;
#               'id': id of the res.partner being recipient to notify;
#               'groups': res.group IDs if linked to a user;
#               'notif': 'inbox', 'email', 'sms' (SMS App);
#               'share': partner.partner_share;
#               'type': 'customer', 'portal', 'user;'
#              }, {...}].
#           See ``MailThread._notify_get_recipients``;
#         :param msg_vals: dictionary of values used to create the message. If given it
#           may be used to access values related to ``message`` without accessing it
#           directly. It lessens query count in some optimized use cases by avoiding
#           access message content in db;

#         :param mail_auto_delete: delete notification emails once sent;

#         :param model_description: model description used in email notification process
#           (computed if not given);
#         :param force_email_company: see ``_notify_by_email_prepare_rendering_context``;
#         :param force_email_lang: see ``_notify_by_email_prepare_rendering_context``;

#         :param resend_existing: check for existing notifications to update based on
#           mailed recipient, otherwise create new notifications;
#         :param force_send: send emails directly instead of using queue;
#         :param send_after_commit: if force_send, tells whether to send emails after
#           the transaction has been committed using a post-commit hook;
#         :param subtitles: optional list that will be set as template value "subtitles"
#         """

#         open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 17")

#         partners_data = [r for r in recipients_data if r['notif'] == 'email']
#         if not partners_data:
#             open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 18")

#             return True

#         model = msg_vals.get('model') if msg_vals else message.model
#         model_name = model_description or (self.env['ir.model']._get(model).display_name if model else False) # one query for display name
#         recipients_groups_data = self._notify_get_recipients_classify(partners_data, model_name, msg_vals=msg_vals)
#         open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 19")
 
#         if not recipients_groups_data:
#             open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 20")

#             return True
#         force_send = self.env.context.get('mail_notify_force_send', force_send)
#         open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 21")

#         template_values = self._notify_by_email_prepare_rendering_context(
#             message, msg_vals=msg_vals, model_description=model_description,
#             force_email_company=force_email_company,
#             force_email_lang=force_email_lang,
#         ) # 10 queries
#         if subtitles:
#             open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 22")

#             template_values['subtitles'] = subtitles

#         email_layout_xmlid = msg_vals.get('email_layout_xmlid') if msg_vals else message.email_layout_xmlid
#         template_xmlid = email_layout_xmlid if email_layout_xmlid else 'mail.mail_notification_layout'
#         base_mail_values = self._notify_by_email_get_base_mail_values(message, additional_values={'auto_delete': mail_auto_delete})
#         open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 23")

#         # Clean the context to get rid of residual default_* keys that could cause issues during
#         # the mail.mail creation.
#         # Example: 'default_state' would refer to the default state of a previously created record
#         # from another model that in turns triggers an assignation notification that ends up here.
#         # This will lead to a traceback when trying to create a mail.mail with this state value that
#         # doesn't exist.
#         SafeMail = self.env['mail.mail'].sudo().with_context(clean_context(self._context))
#         SafeNotification = self.env['mail.notification'].sudo().with_context(clean_context(self._context))
#         emails = self.env['mail.mail'].sudo()
#         open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 24")

#         # loop on groups (customer, portal, user,  ... + model specific like group_sale_salesman)
#         notif_create_values = []
#         recipients_max = 50
#         for recipients_group_data in recipients_groups_data:
#             # generate notification email content
#             recipients_ids = recipients_group_data.pop('recipients')
#             render_values = {**template_values, **recipients_group_data}
#             # {company, is_discussion, lang, message, model_description, record, record_name, signature, subtype, tracking_values, website_url}
#             # {actions, button_access, has_button_access, recipients}

#             mail_body = self.env['ir.qweb']._render(template_xmlid, render_values, minimal_qcontext=True, raise_if_not_found=False, lang=template_values['lang'])
#             if not mail_body:
#                 _logger.warning('QWeb template %s not found or is empty when sending notification emails. Sending without layouting.', template_xmlid)
#                 mail_body = message.body
#             ####Chaelvin
#             mail_body = self.env['mail.render.mixin']._replace_local_links(mail_body)

#             # create email
#             for recipients_ids_chunk in split_every(recipients_max, recipients_ids):
#                 open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 25")

#                 mail_values = self._notify_by_email_get_final_mail_values(
#                     recipients_ids_chunk,
#                     base_mail_values,
#                     ###Chaelvin
#                     additional_values={'body_html': mail_body}
#                 )
#                 new_email = SafeMail.create(mail_values)

#                 # penambahan cc email
#                 if new_email.author_id:
#                     mail_message = self.env['mail.message'].sudo()
#                     data_cc = set()  # Use set to ensure uniqueness
#                     for line in mail_message.search([('parent_id', '=', message.parent_id.id)]):
#                         if line.author_id.email:
#                             data_cc.add(line.author_id.email)  # Add email to the set, which automatically filters duplicates
                    
#                     # penambahan cc email responsible RFQ/PO
#                     # if self._name == 'purchase.requisition':
#                     #     data_cc.add(self.user_id.email)
#                     # if self._name == 'purchase.order' and self.user_po_id.id:
#                     # if self._name == 'purchase.order':
#                     #     data_cc.add(self.user_po_id.email)

#                     data_cc.add('it.odoo@mayapadahospital.com')  # Add the additional email
#                     data_cc = ';'.join(data_cc)  # Convert the set back to a string with ';' as separator
#                     new_email.email_cc = str(data_cc)

#                 # write subject email
#                 new_email.subject = "Approval Notification -" + new_email.subject.replace("Re:", "")
#                 open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 26")

#                 if new_email and recipients_ids_chunk:
#                     tocreate_recipient_ids = list(recipients_ids_chunk)
#                     if resend_existing:
#                         existing_notifications = self.env['mail.notification'].sudo().search([
#                             ('mail_message_id', '=', message.id),
#                             ('notification_type', '=', 'email'),
#                             ('res_partner_id', 'in', tocreate_recipient_ids)
#                         ])
#                         if existing_notifications:
#                             tocreate_recipient_ids = [rid for rid in recipients_ids_chunk if rid not in existing_notifications.mapped('res_partner_id.id')]
#                             existing_notifications.write({
#                                 'notification_status': 'ready',
#                                 'mail_mail_id': new_email.id,
#                             })
#                     notif_create_values += [{
#                         'author_id': message.author_id.id,
#                         'mail_message_id': message.id,
#                         'res_partner_id': recipient_id,
#                         'notification_type': 'email',
#                         'mail_mail_id': new_email.id,
#                         'is_read': True,  # discard Inbox notification
#                         'notification_status': 'ready',
#                     } for recipient_id in tocreate_recipient_ids]
#                 emails += new_email

#         if notif_create_values:
#             open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 27")
#             # DIKOMEN CHAELVIN
#             # SafeNotification.create(notif_create_values)

#         # NOTE:
#         #   1. for more than 50 followers, use the queue system
#         #   2. do not send emails immediately if the registry is not loaded,
#         #      to prevent sending email during a simple update of the database
#         #      using the command-line.
#         test_mode = getattr(threading.current_thread(), 'testing', False)
#         if force_send and len(emails) < recipients_max and (not self.pool._init or test_mode):
#             open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 28")

#             # unless asked specifically, send emails after the transaction to
#             # avoid side effects due to emails being sent while the transaction fails
#             if not test_mode and send_after_commit:
#                 open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 29")

#                 email_ids = emails.ids
#                 dbname = self.env.cr.dbname
#                 _context = self._context

#                 @self.env.cr.postcommit.add
#                 def send_notifications():
#                     db_registry = registry(dbname)
#                     with db_registry.cursor() as cr:
#                         env = api.Environment(cr, SUPERUSER_ID, _context)
#                         env['mail.mail'].browse(email_ids).send()
#             else:
#                 open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 30")

#                 emails.send()
#         open('/opt/odoo16/logs/belajar.log', 'a+').write('\n' + "masuk sini 31")

#         return True





class SequenceMixin(models.AbstractModel):
    """Mechanism used to have an editable sequence number.

    Be careful of how you use this regarding the prefixes. More info in the
    docstring of _get_last_sequence.
    """

    _inherit = 'sequence.mixin'



    @api.constrains(lambda self: (self._sequence_field, self._sequence_date_field))
    def _constrains_date_sequence(self):
        return True
        # # Make it possible to bypass the constraint to allow edition of already messed up documents.
        # # /!\ Do not use this to completely disable the constraint as it will make this mixin unreliable.
        # constraint_date = fields.Date.to_date(self.env['ir.config_parameter'].sudo().get_param(
        #     'sequence.mixin.constraint_start_date',
        #     '1970-01-01'
        # ))
        # for record in self:
        #     if not record._must_check_constrains_date_sequence():
        #         continue
        #     date = fields.Date.to_date(record[record._sequence_date_field])
        #     sequence = record[record._sequence_field]
        #     if (
        #         sequence
        #         and date
        #         and date > constraint_date
        #         and not record._sequence_matches_date()
        #     ):
        #         raise ValidationError(_(
        #             "The %(date_field)s (%(date)s) doesn't match the sequence number of the related %(model)s (%(sequence)s)\n"
        #             "You will need to clear the %(model)s's %(sequence_field)s to proceed.\n"
        #             "In doing so, you might want to resequence your entries in order to maintain a continuous date-based sequence.",
        #             date=format_date(self.env, date),
        #             sequence=sequence,
        #             date_field=record._fields[record._sequence_date_field]._description_string(self.env),
        #             sequence_field=record._fields[record._sequence_field]._description_string(self.env),
        #             model=self.env['ir.model']._get(record._name).display_name,
                # ))





class ResUsersLog(models.Model):
    _name = 'res.users.log'
    _description = 'User Changes Log'
    _order = 'create_date desc'

    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade')
    changed_by = fields.Many2one('res.users', string='Changed By', default=lambda self: self.env.user)
    change_date = fields.Datetime('Change Date', default=fields.Datetime.now)
    changes = fields.Text('Changes')


class PasswordHistory(models.Model):
    _name = 'password.history'
    _description = 'Password History'

    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade')
    password_history = fields.Char(string="Password History", readonly=True, index=True)
    password_hash = fields.Char(string="Password Hash", readonly=True, index=True)