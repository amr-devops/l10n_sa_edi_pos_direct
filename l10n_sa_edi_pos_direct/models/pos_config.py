# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosConfig(models.Model):
    _inherit = 'pos.config'

    # ZATCA direct Mode Configuration
    l10n_sa_edi_pos_direct_mode_enabled = fields.Boolean(
        string="Enable ZATCA direct Mode",
        default=False,
        help="Enable simplified invoices with ZATCA reporting"
    )

    l10n_sa_is_saudi_company = fields.Boolean(
        string="Is Saudi Company",
        compute='_compute_l10n_sa_is_saudi_company',
        store=False,
        help="Computed field to check if company is Saudi Arabian"
    )

    @api.depends('company_id.country_id.code')
    def _compute_l10n_sa_is_saudi_company(self):
        """Compute if company is Saudi Arabian"""
        for config in self:
            config.l10n_sa_is_saudi_company = (
                config.company_id and 
                config.company_id.country_id and 
                config.company_id.country_id.code == 'SA'
            )

    def _get_zatca_certificate_data(self):
        """Get ZATCA certificate data for POS frontend"""
        self.ensure_one()
        if not self.l10n_sa_edi_pos_direct_mode_enabled:
            return {}
            
        journal = self.invoice_journal_id
        certificate = journal.sudo().l10n_sa_production_csid_certificate_id
        
        if not certificate:
            return {}
            
        return {
            'certificate_id': certificate.id,
            'public_key': certificate._get_public_key_bytes(formatting='base64'),
            'certificate_data': certificate._get_der_certificate_bytes(formatting='base64'),
            'issuer_name': certificate._l10n_sa_get_issuer_name(),
            'serial_number': certificate.serial_number,
        }

    @api.model
    def get_zatca_config_for_pos(self, config_id):
        """API method to get ZATCA configuration for POS"""
        config = self.browse(config_id)
        if not config.exists():
            return {}
            
        return {
            'direct_mode_enabled': config.l10n_sa_edi_pos_direct_mode_enabled,
            'certificate_data': config._get_zatca_certificate_data(),
            'company_info': {
                'name': config.company_id.name,
                'vat': config.company_id.vat,
                'street': config.company_id.street,
                'city': config.company_id.city,
                'country_code': config.company_id.country_id.code,
            }
        }
    

    def open_ui(self):
        """Override to check ZATCA direct configuration before opening POS"""
        self.ensure_one()
        
        # Check ZATCA configuration for Saudi companies with direct mode enabled
        if (self.company_id.country_id.code == 'SA' and 
            self.l10n_sa_edi_pos_direct_mode_enabled):
            
            # Check if journal is properly configured for ZATCA
            if not self.invoice_journal_id._l10n_sa_ready_to_submit_einvoices():
                raise UserError(_(
                    "ZATCA direct Mode Error:\n\n"
                    "The POS configuration '%s' has ZATCA direct mode enabled, "
                    "but the invoice journal is not properly configured.\n\n"
                    "Please complete the ZATCA onboarding process first:\n"
                    "• Go to Accounting > Configuration > Journals\n"
                    "• Configure your invoice journal for ZATCA\n"
                    "• Obtain production certificates from ZATCA"
                ) % self.name)
        
        return super().open_ui()
    

class ResConfigSettings(models.TransientModel):
        _inherit = 'res.config.settings'

        l10n_sa_edi_pos_direct_mode_enabled = fields.Boolean(related='pos_config_id.l10n_sa_edi_pos_direct_mode_enabled', readonly=False)
        l10n_sa_is_saudi_company = fields.Boolean(related='pos_config_id.l10n_sa_is_saudi_company', readonly=False)




