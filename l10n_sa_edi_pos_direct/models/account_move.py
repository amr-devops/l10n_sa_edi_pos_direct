from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _l10n_sa_check_refund_reason(self):
        """Check refund reason for ZATCA - same as l10n_sa_edi_pos"""
        return super()._l10n_sa_check_refund_reason() or (
            self.pos_order_ids and 
            self.pos_order_ids[0].refunded_orders_count > 0 and 
            self.ref
        )
