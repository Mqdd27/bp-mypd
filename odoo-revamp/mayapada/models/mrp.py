from collections import namedtuple

import logging
import calendar
import datetime
import requests
from json import dumps, loads

# from json import loads
from odoo import models, fields, api, tools, exceptions
from odoo.http import request, serialize_exception, content_disposition
# from odoo.addons.web.controllers.main import serialize_exception, content_disposition
# from odoo.addons.web.controllers.main import 
from odoo import fields, http, tools, exceptions
from odoo.tools.float_utils import float_compare, float_round
try:
    from multiprocess import Process, Manager
except:
    from threading import Thread as Process
import odoo.addons.decimal_precision as dp
import json

from . import sync
from . import misc