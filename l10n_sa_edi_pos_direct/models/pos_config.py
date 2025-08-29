from odoo import models, fields, api, _
from odoo.exceptions import RedirectWarning


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
        for config in self:
            if (
                    config.company_id.country_id.code == 'SA'
                    and config.invoice_journal_id
                    and (config.invoice_journal_id.edi_format_ids.filtered(lambda f: f.code == "sa_zatca")
                         and not config.invoice_journal_id._l10n_sa_ready_to_submit_einvoices())
            ):
                msg = _("The invoice journal of the point of sale %s must be properly onboarded "
                        "according to ZATCA specifications.\n", config.name)
                action = {
                    "view_mode": "form",
                    "res_model": "account.journal",
                    "type": "ir.actions.act_window",
                    "res_id": config.invoice_journal_id.id,
                    "views": [[False, "form"]],
                }
                raise RedirectWarning(msg, action, _('Go to Journal configuration'))
        return super().open_ui()
    

class ResConfigSettings(models.TransientModel):
        _inherit = 'res.config.settings'

        l10n_sa_edi_pos_direct_mode_enabled = fields.Boolean(related='pos_config_id.l10n_sa_edi_pos_direct_mode_enabled', readonly=False)
        l10n_sa_is_saudi_company = fields.Boolean(related='pos_config_id.l10n_sa_is_saudi_company', readonly=False)




