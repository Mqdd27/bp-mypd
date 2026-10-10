# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#    Copyright (C) 2023-TODAY Cybrosys Technologies (<https://www.cybrosys.com>).
#    Author: Mruthul Raj(<https://www.cybrosys.com>)
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
################################################################################
{
    'name': 'WEB QRCODE SCAN',
    'version': '16.0.1.0.0',
    'summary': 'Time Picker Widget Using Wickedpicker',
    'description': 'Field Time Picker enhances the time input functionality in '
                   'Odoo',
    'category': 'Extra Tools',
    'author': 'Cybrosys Techno Solutions',
    'company': 'Cybrosys Techno Solutions',
    'maintainer': 'Cybrosys Techno Solutions',
    'depends': ['base'],
    'website': 'https://www.cybrosys.com/',
    "depends": [
        "web",
        "barcodes",
    ],
    "assets": {
        'web.assets_backend': [
            'web_qrcode_scan/static/wickedpicker/stylesheets/wickedpicker.css',
            'web_qrcode_scan/static/wickedpicker/src/wickedpicker.js',
            'web_qrcode_scan/static/src/xml/timepicker.xml',
            'web_qrcode_scan/static/src/js/time_widget.js',
        ],
    },
    # "data": [
    #     "static/src/xml/timepicker.xml",
    # ],
    'images': ['static/description/banner.png'],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
