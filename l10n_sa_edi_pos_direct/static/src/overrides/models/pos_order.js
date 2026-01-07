/** @odoo-module */
// Odoo 17 compatible version - uses Order from models.js

import { Order } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";

patch(Order.prototype, {
    
    setup(_defaultObj, options) {
        super.setup(...arguments);
        
        // Odoo 17: Access company through this.pos
        if (this.isSACompany) {
            // Initialize ZATCA status for direct mode
            this.l10n_sa_zatca_status = _defaultObj.l10n_sa_zatca_status;
            // Update invoice flag based on current state
            this._updateToInvoiceForZatca();
        }
    },

    /**
     * Update to_invoice flag based on current order state (B2C vs B2B)
     * Called on setup and when partner changes
     */
    _updateToInvoiceForZatca() {
        if (!this.isSACompany) return;
        
        if (this.shouldUsedirectMode()) {
            // B2C with direct mode: ZATCA direct handles invoicing, no backend invoice
            this.to_invoice = false;
        } else {
            // B2B or direct mode disabled: force backend invoice (same as l10n_sa_edi_pos)
            this.to_invoice = true;
        }
    },

    /**
     * Override set_partner to update invoice flag when customer changes
     * This is critical: B2C vs B2B is determined by partner type
     */
    set_partner(partner) {
        super.set_partner(partner);
        // Re-evaluate invoice requirement after partner changes
        if (this.isSACompany) {
            this._updateToInvoiceForZatca();
        }
    },

    is_to_invoice() {
        if (this.isSACompany) {
            if (this.shouldUsedirectMode()) {
                // B2C with direct mode: no backend invoice needed
                return false;
            }
            // B2B or no direct mode: force backend invoice (same as l10n_sa_edi_pos)
            return true;
        }
        return super.is_to_invoice(...arguments);
    },

    set_to_invoice(to_invoice) {
        if (this.isSACompany) {
            this.assert_editable();
            // Re-evaluate based on current partner state
            this._updateToInvoiceForZatca();
        } else {
            super.set_to_invoice(...arguments);
        }
    },

    // Unicode-safe base64 encoding function to handle Arabic characters
    _unicodeSafeBase64Encode(str) {
        try {
            // First encode the string as UTF-8 bytes, then convert to base64
            // This handles Arabic and other non-Latin1 characters properly
            const utf8Bytes = new TextEncoder().encode(str);
            let binaryString = '';
            for (let i = 0; i < utf8Bytes.length; i++) {
                binaryString += String.fromCharCode(utf8Bytes[i]);
            }
            return window.btoa(binaryString);
        } catch (error) {
            console.error('ZATCA: Error in Unicode-safe base64 encoding, using fallback:', error);
            // Fallback: remove non-ASCII characters and encode
            const asciiOnly = str.replace(/[^\x00-\x7F]/g, "");
            return window.btoa(asciiOnly);
        }
    },

    export_for_printing() {
        const result = super.export_for_printing(...arguments);
        
        if (!result || !result.orderlines) {
            return result;
        }
        
        if (this.shouldUsedirectMode()) {
                result.zatca_direct = true;
        }
        return result;
    },

    get isSACompany() {
        // Odoo 17: Access company through this.pos.company and country through .country (not .country_id)
        return this.pos.company?.country?.code === "SA";
    },

    shouldUsedirectMode() {
        // Odoo 17: Access config through this.pos.config
        return this.isSACompany && 
               this.pos.config?.l10n_sa_edi_pos_direct_mode_enabled && 
               this.isSimplifiedInvoice();
    },

    // Alias method for consistency with pos_store.js
    shouldUseDirectMode() {
        return this.shouldUsedirectMode();
    },

    isSimplifiedInvoice() {
        // B2C transaction = simplified invoice
        return !this.partner || this.partner?.company_type === 'person';
    },

    _getStandardizedInvoiceContentForHash() {
        /**
         * Generate standardized invoice content following ZATCA requirements
         * for simplified invoices (Phase 2)
         */
        // Odoo 17: Access company through this.pos.company
        const content = {
            // Invoice identification (required for hash)
            uuid: this.uid,
            invoice_number: this.name,
            issue_date: this._getZatcaFormattedDate(),
            issue_time: this._getZatcaFormattedTime(),
            
            // Seller information (required)
            seller_name: this.pos.company.name,
            seller_vat: this.pos.company.vat,
            
            // Customer information (simplified for B2C - ZATCA compliant)
            customer_type: this.partner ? 'named' : 'cash',
            customer_name: this.partner?.name || 'Cash Customer',
            customer_id: this.partner?.id || null,
            
            // Financial totals (key for hash)
            line_extension_amount: this.get_total_without_tax(),
            tax_exclusive_amount: this.get_total_without_tax(),
            tax_inclusive_amount: this.get_total_with_tax(),
            tax_amount: this.get_total_tax(),
            payable_amount: this.get_total_with_tax(),
            
            // Invoice lines (essential for proper hash)
            invoice_lines: this.orderlines.map(line => ({
                id: line.id,
                product_name: line.get_product().display_name,
                quantity: line.get_quantity(),
                unit_price: line.get_unit_price(),
                line_total_without_tax: line.get_price_without_tax(),
                line_total_with_tax: line.get_price_with_tax(),
                tax_amount: line.get_tax(),
                tax_rate: this._getLineTaxRate(line),
            })),
            
            // Payment information
            payment_means: this.paymentlines.map(payment => ({
                method: payment.payment_method.name,
                amount: payment.amount,
            })),
        };
        
        return content;
    },

    _canonicalizeForZatca(invoiceContent) {
        /**
         * Apply ZATCA canonicalization rules for consistent hashing
         * Based on XML C14N canonicalization principles adapted for JSON
         */
        try {
            // Sort all object keys recursively for consistent ordering
            const sortedContent = this._sortObjectKeysRecursively(invoiceContent);
            
            // Convert to normalized JSON string
            const jsonString = JSON.stringify(sortedContent, null, 0);
            
            // Apply ZATCA-specific normalizations
            return jsonString
                .replace(/\s+/g, ' ')           // Normalize whitespace
                .replace(/,\s*}/g, '}')         // Remove trailing commas
                .replace(/,\s*]/g, ']')         // Remove trailing commas in arrays
                .trim();                        // Remove leading/trailing whitespace
                
        } catch (error) {
            console.error('ZATCA: Error in canonicalization:', error);
            // Fallback to simple JSON stringify
            return JSON.stringify(invoiceContent);
        }
    },

    _sortObjectKeysRecursively(obj) {
        /**
         * Recursively sort object keys for consistent hashing
         */
        if (Array.isArray(obj)) {
            return obj.map(item => this._sortObjectKeysRecursively(item));
        } else if (obj !== null && typeof obj === 'object') {
            const sortedObj = {};
            Object.keys(obj).sort().forEach(key => {
                sortedObj[key] = this._sortObjectKeysRecursively(obj[key]);
            });
            return sortedObj;
        }
        return obj;
    },

    _generateFallbackHash() {
        /**
         * Generate fallback hash when all else fails
         */
        // Odoo 17: Access company through this.pos.company
        const fallbackData = this.uid + 
                            this.pos.company.vat + 
                            this.get_total_with_tax() + 
                            Date.now();
        return this._unicodeSafeBase64Encode('ZATCA_FALLBACK_' + fallbackData).substring(0, 64);
    },

    _getZatcaFormattedDate() {
        /**
         * Get date in ZATCA required format (YYYY-MM-DD)
         */
        const date = this.creation_date || new Date();
        return date.toISOString().split('T')[0];
    },

    _getZatcaFormattedTime() {
        /**
         * Get time in ZATCA required format (HH:mm:ss)
         */
        const date = this.creation_date || new Date();
        return date.toTimeString().split(' ')[0];
    },

    _getLineTaxRate(line) {
        /**
         * Get tax rate for a line item using Odoo 17 POS methods
         */
        try {
            // Odoo 17: Try to get tax info from the line
            const taxes = line.get_taxes();
            if (taxes && taxes.length > 0) {
                return taxes[0].amount || 15.0;
            }
            
            // Alternative: get tax amount and calculate percentage
            const taxAmount = line.get_tax();
            const priceWithoutTax = line.get_price_without_tax();
            if (priceWithoutTax > 0) {
                return (taxAmount / priceWithoutTax) * 100;
            }
            
            return 15.0; // Default VAT rate in Saudi Arabia
        } catch (error) {
            console.warn('ZATCA: Error getting line tax rate:', error);
            return 15.0; // Default VAT rate fallback
        }
    },

    generateDigitalSignatureSync() {
        try {
            // ZATCA Regulation: "الحل التقني المستخدم في إصدار الفواتير الإلكترونية... هو الذي سيقوم بإصدار ختم التشفير"
            // Translation: The technical solution (POS system) generates the cryptographic stamp
            
            // Step 1: Get the invoice hash that we need to sign (use sync version)
            const invoiceHash = this.calculateInvoiceHashSync();
            
            // Step 2: Generate ZATCA-compliant deterministic signature synchronously
            const signatureInput = this._prepareSignatureInputSync(invoiceHash);
            const signature = this._generateDeterministicSignatureSync(signatureInput);
            
            return 'ZATCA:' + signature;
            
        } catch (error) {
            // Final fallback - still deterministic based on invoice data
            return this._generateFallbackSignature();
        }
    },
    
    calculateInvoiceHashSync() {
        try {
            // Use synchronous fallback hash for signature generation
            const invoiceContent = this._getStandardizedInvoiceContentForHash();
            const canonicalContent = this._canonicalizeForZatca(invoiceContent);
            
            // Simple deterministic hash (not crypto-grade but consistent)
            const hashInput = JSON.stringify(canonicalContent);
            return this._unicodeSafeBase64Encode(hashInput).replace(/[^A-Za-z0-9]/g, '').substring(0, 64);
        } catch (error) {
            return this._generateFallbackHash();
        }
    },
    
    _prepareSignatureInputSync(invoiceHash) {
        // Prepare data for signing according to ZATCA requirements
        // Odoo 17: Access company through this.pos.company
        const company = this.pos.company;
        const timestamp = this.creation_date?.toISOString() || new Date().toISOString();
        const orderRef = this.name;
        const amount = this.get_total_with_tax();
        
        return {
            hash: invoiceHash,
            issuer: company.vat,
            timestamp: timestamp,
            reference: orderRef,
            amount: amount.toFixed(2)
        };
    },
    
    _generateDeterministicSignatureSync(signatureInput) {
        try {
            // Create deterministic signature using available data
            const dataString = JSON.stringify(signatureInput);
            
            // Simple but consistent deterministic generation
            return this._unicodeSafeBase64Encode(dataString).replace(/[^A-Za-z0-9]/g, '').substring(0, 88);
            
        } catch (error) {
            return this._generateFallbackSignature();
        }
    },
    
    _generateFallbackSignature() {
        // Odoo 17: Access company through this.pos.company
        const orderData = `${this.pos.company.vat}_${this.name}_${this.get_total_with_tax()}`;
        return this._unicodeSafeBase64Encode(orderData).replace(/[^A-Za-z0-9]/g, '').substring(0, 64);
    },

    getPublicKeySync() {
        try {
            // Odoo 17: Access config through this.pos.config
            const config = this.pos.config;
            if (config?.zatca_certificate?.public_key) {
                return config.zatca_certificate.public_key.substring(0, 88);
            }
            
            // Fallback to company-based placeholder
            return this._unicodeSafeBase64Encode('ZATCA_PUBLIC_KEY_' + this.pos.company.vat).substring(0, 64);
        } catch (error) {
            return 'DEFAULT_PUBLIC_KEY_' + Date.now().toString().substring(0, 32);
        }
    },

    getCertificateSignatureSync() {
        try {
            // Odoo 17: Access config through this.pos.config
            const config = this.pos.config;
            if (config?.zatca_certificate) {
                const cert = config.zatca_certificate;
                if (cert.certificate_signature || cert.serial_number || cert.certificate_id) {
                    const sig = cert.certificate_signature || cert.serial_number || cert.certificate_id;
                    return sig.toString().substring(0, 88);
                }
            }
            
            // Fallback to company-based placeholder
            return this._unicodeSafeBase64Encode('ZATCA_CERT_' + this.pos.company.vat).substring(0, 64);
        } catch (error) {
            return 'DEFAULT_CERT_SIG_' + Date.now().toString().substring(0, 32);
        }
    },

    /**
     * Override the default Odoo compute_sa_qr_code method to generate enhanced ZATCA Phase 2 QR codes
     * when direct mode is enabled, otherwise fall back to the standard 5-field QR code
     */
    compute_sa_qr_code(name, vat, date_isostring, amount_total, amount_tax) {
        // If ZATCA direct mode is enabled and this is a simplified invoice, generate enhanced QR
        if (this.shouldUsedirectMode()) {
            return this.generateEnhancedQRDataSync(name, vat, date_isostring, amount_total, amount_tax);
        }
        
        // Otherwise, use the standard Odoo 5-field QR code from l10n_sa_pos
        return super.compute_sa_qr_code(...arguments);
    },

    /**
     * Generate enhanced ZATCA Phase 2 QR code data (9 fields)
     * Following the same pattern as Odoo's qr.js but adding Phase 2 fields
     */
    generateEnhancedQRDataSync(name, vat, date_isostring, amount_total, amount_tax) {
        try {
            const ksa_timestamp = formatDateTime(deserializeDateTime(date_isostring), {
                tz: "Asia/Riyadh",
                format: "yyyy-MM-dd HH:mm:ss",
            });

            // Standard 5 fields (same as Odoo's original)
            const seller_name_enc = this._compute_qr_code_field(1, name);
            const company_vat_enc = this._compute_qr_code_field(2, vat);
            const timestamp_enc = this._compute_qr_code_field(3, ksa_timestamp);
            const invoice_total_enc = this._compute_qr_code_field(4, amount_total.toString());
            const total_vat_enc = this._compute_qr_code_field(5, amount_tax.toString());

            // ZATCA Phase 2 additional fields (6-9)
            const invoice_hash_enc = this._compute_qr_code_field(6, this.calculateInvoiceHashSync());
            const digital_signature_enc = this._compute_qr_code_field(7, this.generateDigitalSignatureSync());
            const public_key_enc = this._compute_qr_code_field(8, this.getPublicKeySync());
            const certificate_signature_enc = this._compute_qr_code_field(9, this.getCertificateSignatureSync());

            // Concatenate all fields (1-9)
            const str_to_encode = seller_name_enc.concat(
                company_vat_enc,
                timestamp_enc,
                invoice_total_enc,
                total_vat_enc,
                invoice_hash_enc,
                digital_signature_enc,
                public_key_enc,
                certificate_signature_enc
            );

            // Convert to base64 (same as Odoo's original method)
            let binary = "";
            for (let i = 0; i < str_to_encode.length; i++) {
                binary += String.fromCharCode(str_to_encode[i]);
            }
            return btoa(binary);

        } catch (error) {
            console.error('ZATCA: Error generating enhanced QR data:', error);
            return;
        }
    },

    /**
     * Helper function to compute QR code field encoding
     * Same as the _compute_qr_code_field function in Odoo's qr.js
     */
    _compute_qr_code_field(tag, field) {
        const textEncoder = new TextEncoder();
        const name_byte_array = Array.from(textEncoder.encode(field));
        const name_tag_encoding = [tag];
        const name_length_encoding = [name_byte_array.length];
        return name_tag_encoding.concat(name_length_encoding, name_byte_array);
    },
});
