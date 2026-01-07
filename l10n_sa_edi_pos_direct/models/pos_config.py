import json
import logging
from base64 import b64decode

from odoo import models, fields, api, _
from odoo.exceptions import RedirectWarning

_logger = logging.getLogger(__name__)


class PosConfig(models.Model):
    _inherit = 'pos.config'

    # ZATCA direct Mode Configuration
    l10n_sa_edi_pos_direct_mode_enabled = fields.Boolean(
        string="Enable ZATCA direct Mode",
        default=False,
        help="Enable simplified invoices with ZATCA reporting"
    )
    country_code = fields.Char(related='company_id.account_fiscal_country_id.code', readonly=True)

    def _get_zatca_certificate_data(self):
        """Get ZATCA certificate data for POS frontend (Odoo 17 compatible)"""
        self.ensure_one()
        if not self.l10n_sa_edi_pos_direct_mode_enabled:
            return {}
            
        journal = self.invoice_journal_id
        # Odoo 17: Certificate is stored as JSON in l10n_sa_production_csid_json field
        pcsid_json = journal.sudo().l10n_sa_production_csid_json
        
        if not pcsid_json:
            return {}
        
        try:
            pcsid_data = json.loads(pcsid_json)
            x509_cert = pcsid_data.get('binarySecurityToken', '')
            
            # Extract certificate info from the base64 encoded certificate
            # IMPORTANT: binarySecurityToken is double-base64 encoded in Odoo 17
            if x509_cert:
                from cryptography.x509 import load_der_x509_certificate
                from cryptography.hazmat.backends import default_backend
                from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
                
                # First decode to get the inner base64 string, then decode again to get DER
                b64_decoded_cert = b64decode(x509_cert)
                cert_der = b64decode(b64_decoded_cert.decode())
                certificate = load_der_x509_certificate(cert_der, default_backend())
                
                # Get public key in base64 format
                public_key_bytes = certificate.public_key().public_bytes(
                    Encoding.DER, 
                    PublicFormat.SubjectPublicKeyInfo
                )
                import base64
                public_key_b64 = base64.b64encode(public_key_bytes).decode('utf-8')
                
                return {
                    'certificate_id': None,  # No certificate model in Odoo 17
                    'public_key': public_key_b64,
                    'certificate_data': x509_cert,
                    'issuer_name': certificate.issuer.rfc4514_string(),
                    'serial_number': str(certificate.serial_number),
                }
        except Exception as e:
            _logger.warning(f"ZATCA: Error extracting certificate data: {e}")
            return {}
            
        return {}

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




