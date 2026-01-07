/** @odoo-module */
// Odoo 17 compatible version - uses AbstractAwaitablePopup pattern

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

export class ZatcaRefundReasonPopup extends AbstractAwaitablePopup {
    static template = "l10n_sa_edi_pos_direct.ZatcaRefundReasonPopup";
    static defaultProps = {
        confirmText: _t("Confirm Refund"),
        cancelText: _t("Cancel"),
        title: _t("ZATCA Refund Reason"),
    };

    setup() {
        super.setup();
        this.pos = usePos();
        this.state = useState({
            l10n_sa_zatca_refund_reason: this.props.order?.l10n_sa_zatca_refund_reason || "DESC_ERROR",
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
     * Override getPayload to return the refund reason data
     * This is called by AbstractAwaitablePopup when confirm is clicked
     */
    getPayload() {
        return {
            l10n_sa_zatca_refund_reason: this.state.l10n_sa_zatca_refund_reason,
        };
    }
}
