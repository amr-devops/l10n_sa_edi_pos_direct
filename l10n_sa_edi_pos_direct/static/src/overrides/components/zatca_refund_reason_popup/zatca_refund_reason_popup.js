/** @odoo-module */

import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { Component, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

export class ZatcaRefundReasonPopup extends Component {
    static template = "l10n_sa_edi_pos_direct.ZatcaRefundReasonPopup";
    static components = { Dialog };
    static props = {
        order: { type: Object, optional: false },
        getPayload: { type: Function, optional: false },
        close: { type: Function, optional: false },
    };

    setup() {
        this.pos = usePos();
        this.state = useState({
            l10n_sa_zatca_refund_reason: this.props.order.l10n_sa_zatca_refund_reason || "DESC_ERROR",
        });
    }

    /**
     * Get available ZATCA refund reasons
     */
    get zatcaRefundReasons() {
        return [
            { value: "DESC_ERROR", name: "عيب في الوصف - Description Error" },
            { value: "QTY_ERROR", name: "خطأ في الكمية - Quantity Error" },
            { value: "PRICE_ERROR", name: "خطأ في السعر - Price Error" },
            { value: "PRODUCT_DEFECT", name: "عطل في المنتج - Product Defect" },
            { value: "CUSTOMER_REQUEST", name: "إلغاء بطلب العميل - Customer Cancellation" },
            { value: "OTHER_REASON", name: "أسباب أخرى - Other Reasons" },
        ];
    }

    /**
     * Get the description for selected reason
     */
    get selectedReasonName() {
        const reason = this.zatcaRefundReasons.find(
            r => r.value === this.state.l10n_sa_zatca_refund_reason
        );
        return reason ? reason.name : "";
    }

    /**
     * Handle reason selection change
     */
    onReasonChange(ev) {
        this.state.l10n_sa_zatca_refund_reason = ev.target.value;
    }

    /**
     * Validate and confirm the selection
     */
    confirm() {
        // Validate required fields
        if (!this.state.l10n_sa_zatca_refund_reason) {
            this.notification.add({
                title: _t("ZATCA Refund Reason Required"),
                message: _t("Please select a refund reason for ZATCA compliance."),
                type: "warning",
            });
            return;
        }

        // Return the selected values
        this.props.getPayload({
            l10n_sa_zatca_refund_reason: this.state.l10n_sa_zatca_refund_reason,
        });
        this.props.close();
    }

    /**
     * Cancel the popup
     */
    cancel() {
        this.props.close();
    }
}
