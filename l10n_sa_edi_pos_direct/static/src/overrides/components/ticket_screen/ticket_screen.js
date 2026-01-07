/** @odoo-module */
// Odoo 17 compatible version - uses popup.add instead of makeAwaitable

import { patch } from "@web/core/utils/patch";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { ZatcaRefundReasonPopup } from "@l10n_sa_edi_pos_direct/overrides/components/zatca_refund_reason_popup/zatca_refund_reason_popup";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { _t } from "@web/core/l10n/translation";

patch(TicketScreen.prototype, {
    /**
     * Override to add ZATCA refund reason popup for Saudi Arabian companies
     * This applies to ALL refunds in ZATCA direct mode (no invoice dependency)
     */
    async addAdditionalRefundInfo(order, destinationOrder) {
        // Check if this is a Saudi Arabian company with ZATCA direct mode enabled
        if (this.isSaudiCompany && this.pos.config.l10n_sa_edi_pos_direct_mode_enabled) {
            // Show popup for ALL refunds in ZATCA direct mode (simplified invoices)
            // Odoo 17: Use popup.add() pattern instead of makeAwaitable
            try {
                const { confirmed, payload } = await this.popup.add(ZatcaRefundReasonPopup, {
                    order: destinationOrder,
                });

                if (confirmed && payload) {
                    // Set ZATCA refund reason fields on the destination order
                    destinationOrder.l10n_sa_zatca_refund_reason = payload.l10n_sa_zatca_refund_reason;
                } else {
                    // User cancelled - don't proceed with refund
                    this.popup.add(ErrorPopup, {
                        title: _t("ZATCA Refund Reason Required"),
                        body: _t("Refund reason is required for ZATCA compliance. Please try again."),
                    });
                    return;
                }
            } catch (error) {
                console.error("ZATCA refund reason popup error:", error);
                return;
            }
        }

        // Call parent method for other localizations
        return super.addAdditionalRefundInfo(...arguments);
    },

    /**
     * Check if company is Saudi Arabian
     */
    get isSaudiCompany() {
        // Odoo 17: Access country through .country (not .country_id)
        return this.pos.company.country?.code === "SA";
    },
});
