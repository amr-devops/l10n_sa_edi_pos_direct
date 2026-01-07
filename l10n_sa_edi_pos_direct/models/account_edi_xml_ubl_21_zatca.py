from odoo import models


class AccountEdiXmlUBL21Zatca(models.AbstractModel):
    _inherit = "account.edi.xml.ubl_21.zatca"

    def _l10n_sa_get_payment_means_code(self, invoice):
        """
        Return payment means code to be used in ZATCA XML file.
        For POS invoices, get the payment method type from POS payment.
        Same as l10n_sa_edi_pos - required for B2B invoices from POS.
        """
        res = super()._l10n_sa_get_payment_means_code(invoice)
        if invoice._l10n_sa_is_simplified() and invoice.sudo().pos_order_ids:
            pos_payments = invoice.sudo().pos_order_ids.payment_ids
            if pos_payments:
                res = pos_payments[0].payment_method_id.type
        return res
