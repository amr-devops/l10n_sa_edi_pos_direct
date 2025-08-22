/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { ZatcaRefundReasonPopup } from "@l10n_sa_edi_pos_direct/overrides/components/zatca_refund_reason_popup/zatca_refund_reason_popup";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

patch(TicketScreen.prototype, {
    setup() {
        super.setup();
        this.notification = useService("notification");
    },

    /**
     * Override to add ZATCA refund reason popup for Saudi Arabian companies
     * This applies to ALL refunds in ZATCA direct mode (no invoice dependency)
     */
    async addAdditionalRefundInfo(order, destinationOrder) {
        // Check if this is a Saudi Arabian company with ZATCA direct mode enabled
        if (this.isSaudiCompany && this.pos.config.l10n_sa_edi_pos_direct_mode_enabled) {
            // Show popup for ALL refunds in ZATCA direct mode (simplified invoices)
            try {
                const payload = await makeAwaitable(this.dialog, ZatcaRefundReasonPopup, {
                    order: destinationOrder,
                });

                if (payload) {
                    // Set ZATCA refund reason fields on the destination order
                    destinationOrder.l10n_sa_zatca_refund_reason = payload.l10n_sa_zatca_refund_reason;
                    
                } else {
                    // User cancelled - don't proceed with refund
                    this.notification.add(
                        _t("Refund reason is required for ZATCA compliance. Please try again."),
                        { type: "warning" }
                    );
                    return;
                }
            } catch (error) {
                console.error("ZATCA refund reason popup error:", error);
                // Show notification to user
                this.notification.add(
                    _t("Refund reason is required for ZATCA compliance. Please try again."),
                    { type: "warning" }
                );
                // Re-throw to prevent refund from proceeding
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
        return this.pos.company.country_id?.code === "SA";
    },
});
