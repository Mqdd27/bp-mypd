from odoo import models, fields, api, tools, exceptions, _
import logging
from . import sync

_logger = logging.getLogger(__name__)