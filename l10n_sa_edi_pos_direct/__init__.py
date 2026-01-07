# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import models

def post_init_hook(env):
    """
    Post-installation hook to configure ZATCA settings for POS
    """
    # Enable direct mode for Saudi companies
    saudi_companies = env['res.company'].search([('country_id.code', '=', 'SA')])
    for company in saudi_companies:
        # Enable direct ZATCA mode
        env['ir.config_parameter'].sudo().set_param(
            f'l10n_sa_pos_direct_zatca.enabled.company_{company.id}', 
            'True'
        )
