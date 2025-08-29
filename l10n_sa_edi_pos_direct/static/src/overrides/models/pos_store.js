/** @odoo-module */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {

    // Load ZATCA configuration after server data is processed
    async afterProcessServerData() {
        const result = await super.afterProcessServerData();
        
        // Load ZATCA configuration for Saudi companies
        if (this.company?.country_id?.code === "SA" && 
            this.config?.l10n_sa_edi_pos_direct_mode_enabled) {
            try {
                await this.loadZatcaConfiguration();
            } catch (error) {
                console.error('ZATCA: Failed to load configuration:', error);
                // Don't block POS startup if ZATCA config fails
            }
        }
        
        return result;
    },

    async loadZatcaConfiguration() {
        try {
    
            
            // Call backend using pos_data service (Odoo 18 standard way)
            const zatcaConfig = await this.data.call('pos.config', 'get_zatca_config_for_pos', [this.config.id]);

            if (zatcaConfig && zatcaConfig.direct_mode_enabled) {
                // Store ZATCA configuration globally in POS store
                this.zatca_config = zatcaConfig;
                
                if (zatcaConfig.certificate_data && zatcaConfig.certificate_data.certificate_id) {
                    this.zatca_certificate = zatcaConfig.certificate_data;
                    
                    this.config.zatca_certificate = zatcaConfig.certificate_data;
                    

                } else {
                    console.warn('⚠️ ZATCA: No certificate data available');
                    this.zatca_certificate = null;
                    this.config.zatca_certificate = null;
                }
                
                // Validate configuration
                this.validateZatcaConfiguration();
                
            } else {
                this.zatca_config = null;
                this.zatca_certificate = null;
            }
        } catch (error) {
            console.error('ZATCA: Error loading configuration:', error);
            this.zatca_config = null;
            this.zatca_certificate = null;
            throw error;
        }
    },

    validateZatcaConfiguration() {
        const errors = [];
        
        if (!this.zatca_config) {
            errors.push('ZATCA configuration not loaded');
            return { valid: false, errors };
        }
        
        // Validate company information
        if (!this.zatca_config.company_info?.name) {
            errors.push('Company name is required');
        }
        
        if (!this.zatca_config.company_info?.vat) {
            errors.push('Company VAT number is required');
        }
        
        // Validate certificate data (if available)
        if (this.zatca_certificate) {
            if (!this.zatca_certificate.public_key) {
                errors.push('Certificate public key is missing');
            }
            
            if (!this.zatca_certificate.certificate_data) {
                errors.push('Certificate data is missing');
            }
        } else {
            // Certificate not available - will use local generation
            console.info('ZATCA: No certificate available - using local generation mode');
        }
        
        return {
            valid: errors.length === 0,
            errors: errors,
            warnings: errors.length === 0 && !this.zatca_certificate ? 
                ['Certificate not available - local mode active'] : []
        };
    },

    // Override getReceiptHeaderData to handle QR code generation
    getReceiptHeaderData(order) {
        const data = super.getReceiptHeaderData(order);
        if (order && order.company?.country_id?.code === "SA") {
            if (order.shouldUsedirectMode && order.shouldUsedirectMode()) {
                data.zatca_direct = true;
            } else {
                data.zatca_direct = false;
            }
        }
        return data;
    },

});

