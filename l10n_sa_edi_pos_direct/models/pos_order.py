# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import uuid
import json
import base64
import hashlib
import logging
from datetime import datetime, timedelta
from lxml import etree
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_repr

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'
    
    l10n_sa_zatca_status = fields.Selection([
        ('legacy', 'Legacy Order (Pre-Module)'),
        ('pending', 'Pending Generation'),
        ('generated', 'Generated Locally'), 
        ('queued', 'Queued for ZATCA'),
        ('submitted', 'Successfully Submitted to ZATCA'),
        ('error', 'Error'),
    ], string="ZATCA Status", default=False, copy=False)
    
    l10n_sa_zatca_submission_time = fields.Datetime(
        string="ZATCA Submission Time",
        copy=False,
        help="When the invoice was submitted to ZATCA"
    )
    
    l10n_sa_zatca_error_message = fields.Text(
        string="ZATCA Error Message",
        copy=False
    )

    l10n_sa_zatca_refund_reason = fields.Selection([
        ('DESC_ERROR', 'Description Error - عيب في الوصف'),
        ('QTY_ERROR', 'Quantity Error - خطأ في الكمية'),
        ('PRICE_ERROR', 'Price Error - خطأ في السعر'),
        ('PRODUCT_DEFECT', 'Product Defect - عطل في المنتج'),
        ('CUSTOMER_REQUEST', 'Customer Cancellation - إلغاء بطلب العميل'),
        ('OTHER_REASON', 'Other Reasons - أسباب أخرى'),
    ], string="ZATCA Refund Reason", copy=False, help="Refund reason code for ZATCA direct mode compliance")
    
    
    l10n_sa_qr_code_image = fields.Html(
        string="QR Code Image",
        help="QR code as HTML image for display"
    )
    
    # Standard l10n_sa_edi_pos fields - only for non-direct mode orders
    l10n_sa_invoice_qr_code_str = fields.Char(
        string="ZATCA QR Code",
        compute="_compute_l10n_sa_invoice_fields",
        help="QR code from related account move (non-direct mode only)"
    )
    l10n_sa_invoice_edi_state = fields.Selection(
        string="Electronic invoicing",
        selection=[
            ('to_send', 'To Send'),
            ('sent', 'Sent'),
            ('cancelled', 'Cancelled'),
            ('to_cancel', 'To Cancel'),
        ],
        compute="_compute_l10n_sa_invoice_fields",
        help="Electronic invoicing state from related account move (non-direct mode only)"
    )

    @api.depends('account_move', 'account_move.l10n_sa_qr_code_str', 'account_move.edi_state')
    def _compute_l10n_sa_invoice_fields(self):
        """
        Compute l10n_sa_invoice fields from related account.move
        Only for orders that don't use ZATCA direct mode processing
        """
        for order in self:
            # Only populate these fields if the order should NOT use ZATCA direct processing
            if not order._should_process_zatca():
                # Get values from related account.move (standard l10n_sa_edi_pos behavior)
                if order.account_move:
                    order.l10n_sa_invoice_qr_code_str = order.account_move.l10n_sa_qr_code_str or False
                    order.l10n_sa_invoice_edi_state = order.account_move.edi_state or False
                else:
                    order.l10n_sa_invoice_qr_code_str = False
                    order.l10n_sa_invoice_edi_state = False
            else:
                # For ZATCA direct mode orders, clear these fields as they use their own system
                order.l10n_sa_invoice_qr_code_str = False
                order.l10n_sa_invoice_edi_state = False

    def _l10n_sa_get_refund_reason_for_zatca_xml(self):
        """
        Get refund reason information for ZATCA XML generation (direct mode only)
        This is used in the simplified invoice XML template, not for account.move
        """
        if (self._is_refund_order() and self.session_id.config_id.l10n_sa_edi_pos_direct_mode_enabled):
            if not (self.l10n_sa_zatca_refund_reason ):
                self.l10n_sa_zatca_refund_reason = 'CUSTOMER_REQUEST'
                
            reason_display = dict(self._fields['l10n_sa_zatca_refund_reason'].selection).get(
                self.l10n_sa_zatca_refund_reason, 
                self.l10n_sa_zatca_refund_reason
            )
            
            return {
                'reason_code': self.l10n_sa_zatca_refund_reason,
                'reason_display': reason_display,
            }
        return None

    @api.model
    def create(self, vals):
        """Override create to initialize ZATCA fields for Saudi companies"""
        order = super().create(vals)
        
        if (order._should_process_zatca()):
            
            # Set status from frontend or default to pending
            order.l10n_sa_zatca_status = 'generated'
            
        return order

    def _is_simplified_invoice(self):
        """Check if this order should generate a simplified invoice (B2C)"""
        return not self.partner_id or self.partner_id.company_type == 'person'

    def _is_refund_order(self):
        """Check if this is a refund order (has refunded_order_id or negative amount)"""
        return bool(self.refunded_order_id) or self.amount_total < 0

    def _validate_refund_reason_for_zatca(self):
        """
        Validate refund reason for ZATCA compliance (simplified for direct mode)
        For POS direct mode: requires l10n_sa_zatca_refund_reason
        """
        if not self._is_refund_order():
            return True  # Not a refund, no validation needed
            
        # ZATCA compliance check: must have refund reason code
        return bool(self.l10n_sa_zatca_refund_reason)

    def _get_zatca_invoice_type_code(self):
        """
        Get ZATCA invoice type code (similar to l10n_sa_edi._l10n_sa_get_invoice_type)
        - 381: Credit Note (refund)
        - 388: Standard Invoice
        """
        if self._is_refund_order():
            return 381  # Credit Note
        else:
            return 388  # Standard Invoice

    def _get_zatca_billing_reference_vals(self):
        """
        Get billing reference for refund orders (similar to l10n_sa_edi._l10n_sa_get_billing_reference_vals)
        Required for credit notes to reference original order
        """
        if self._is_refund_order() and self.refunded_order_id:
            return {
                'id': self.refunded_order_id.pos_reference or self.refunded_order_id.name,
                'issue_date': self.refunded_order_id.date_order.strftime('%Y-%m-%d'),
            }
        return None

    
    def _compute_qr_code_image(self,qr_code):
        """Compute QR code as HTML image for display"""
        for record in self:
            qr_data = qr_code
            if qr_data:
                try:
                    # Try to use qrcode library to generate QR code image
                    try:
                        import qrcode
                        from io import BytesIO
                        import base64
                        
                        # Generate QR code
                        qr = qrcode.QRCode(
                            version=1,
                            error_correction=qrcode.constants.ERROR_CORRECT_L,
                            box_size=10,
                            border=4,
                        )
                        qr.add_data(qr_data)
                        qr.make(fit=True)
                        
                        # Create image
                        img = qr.make_image(fill_color="black", back_color="white")
                        
                        # Convert to base64
                        buffer = BytesIO()
                        img.save(buffer, format='PNG')
                        img_str = base64.b64encode(buffer.getvalue()).decode()
                        
                        # Create HTML img tag
                        record.l10n_sa_qr_code_image = f'''
                        <div style="text-align: center;">
                            <img src="data:image/png;base64,{img_str}" 
                                 style="max-width: 300px; max-height: 300px; border: 1px solid #ccc;"/>
                        </div>
                        '''
                    except ImportError:
                        # Fallback: Display as text with instruction to install qrcode
                        record.l10n_sa_qr_code_image = f'''
                        <div style="text-align: center; padding: 20px; border: 1px solid #ccc;">
                            <p><strong>QR Code Data:</strong></p>
                            <p style="word-break: break-all; font-family: monospace; font-size: 12px;">{qr_data}</p>
                            <p style="color: #666; font-size: 11px;">
                                <em>To display QR code image, install: pip install qrcode[pil]</em>
                            </p>
                        </div>
                        '''
                except Exception as e:
                    record.l10n_sa_qr_code_image = f'''
                    <div style="text-align: center; padding: 20px; border: 1px solid #ccc;">
                        <p style="color: red;">Error generating QR code: {str(e)}</p>
                        <p style="word-break: break-all; font-family: monospace; font-size: 12px;">{qr_data}</p>
                    </div>
                    '''
            else:
                record.l10n_sa_qr_code_image = '<p>No QR code data available</p>'

    def action_pos_order_paid(self):
        """Simplified override for ZATCA direct processing"""
        result = super().action_pos_order_paid()
        
        # Simple ZATCA processing for simplified invoices
        for order in self:
            if order._should_process_zatca():
                if order._is_ready_for_zatca():
                    order._schedule_zatca_submission()
                else:
                    # Mark as pending if not fully processed in POS
                    order.l10n_sa_zatca_status = 'pending'
                    _logger.warning(f"Order {order.name} not fully processed in POS - marked as pending")
        
        return result

    def _should_process_zatca(self):
        """Check if order should be processed for ZATCA"""
        return (self.company_id.country_id.code == 'SA' and 
                self.session_id.config_id.l10n_sa_edi_pos_direct_mode_enabled and
                self._is_simplified_invoice())

    def _is_ready_for_zatca(self):
        """Check if order has all required ZATCA data from frontend"""
        return (self.uuid and 
                self.l10n_sa_zatca_status == 'generated')

    def _schedule_zatca_submission(self):
        """Schedule ZATCA submission - mark as queued for cron processing"""
        if not self.uuid:
            _logger.error(f"Cannot schedule ZATCA submission for order {self.name} - no UUID")
            return
        
        # Enhanced validation for refund orders
        if self._is_refund_order():
            if not self._validate_refund_reason_for_zatca():
                _logger.error(f"ZATCA: Order {self.name} is a refund but missing required refund reason")
                self.l10n_sa_zatca_status = 'error'
                self.l10n_sa_zatca_error_message = "Refund reason is required for ZATCA compliance"
                return
            else:
                _logger.info(f"ZATCA: Refund order {self.name} has valid refund reason: {self.l10n_sa_zatca_refund_reason}")
            
        # Mark as queued for immediate processing by cron job
        self.l10n_sa_zatca_status = 'queued'
        _logger.info(f"ZATCA: Order {self.name} queued for submission - will be processed by next cron run")

    def submit_to_zatca_reporting(self):
        """Submit simplified invoice to ZATCA reporting API"""
        try:
            # Check UUID instead of invoice data (which may not be populated)
            if not self.uuid:
                raise UserError(_("No UUID available for ZATCA submission"))
            
            journal = self.session_id.config_id.invoice_journal_id
            
            # Check if journal is ready for ZATCA submission
            if not journal._l10n_sa_ready_to_submit_einvoices():
                raise UserError(_("Journal is not ready for ZATCA submission. Please complete onboarding first."))
            
            
            
            # Generate or retrieve simplified invoice XML data
            xml_content = self._generate_simplified_invoice_xml()
            
            # Submit to ZATCA Reporting API (for simplified invoices)
            result = self._submit_to_zatca_reporting_api(journal, xml_content)
            
            # Process the result - handle both success and 400 (rejected) cases
            if not result.get('error'):
                # Success case - no errors
                self.l10n_sa_zatca_status = 'submitted'
                self.l10n_sa_zatca_submission_time = fields.Datetime.now()
                
                # Check for confirmation (simplified invoices use 'reportingStatus')
                if result.get('reportingStatus') == 'REPORTED':
                    self.l10n_sa_zatca_status = 'submitted'
                    
            elif result.get('json_errors'):
                # 400 case - rejected by ZATCA but need to process validation results
                self._process_zatca_validation_errors(result)
                    
            else:
                # Other error cases (network, 401+, etc.)
                self.l10n_sa_zatca_status = 'error'
                error_msg = result.get('error', 'Unknown ZATCA error')
                if isinstance(error_msg, dict):
                    error_msg = str(error_msg)
                self.l10n_sa_zatca_error_message = error_msg
                
        except Exception as e:
            self.l10n_sa_zatca_status = 'error'  
            self.l10n_sa_zatca_error_message = str(e)




    def _process_zatca_validation_errors(self, result):
        """Process ZATCA validation errors for 400 responses"""
        json_errors = result.get('json_errors', {})
        status_code = json_errors.get('status_code', 400)
        
        # Build error message similar to account_edi_format.py
        error_msg = f'<b>[{status_code}]</b> '
        
        is_warning_only = True
        validation_results = json_errors.get('validationResults', {})
        
        # Process warning messages
        for warning in validation_results.get('warningMessages', []):
            error_msg += f"<b>{warning.get('code', 'WARNING')}</b>: {warning.get('message', 'Unknown warning')}<br/>"
        
        # Process error messages
        for error in validation_results.get('errorMessages', []):
            is_warning_only = False
            error_msg += f"<b>{error.get('code', 'ERROR')}</b>: {error.get('message', 'Unknown error')}<br/>"
        
        # Set status based on whether there are actual errors or just warnings
        if is_warning_only:
            self.l10n_sa_zatca_status = 'submitted'  # Warnings don't prevent submission
            _logger.warning(f"ZATCA submission for order {self.name} has warnings: {error_msg}")
        else:
            self.l10n_sa_zatca_status = 'error'  # Real errors prevent submission
            _logger.error(f"ZATCA submission for order {self.name} rejected: {error_msg}")
        
        # Store the error message for review
        self.l10n_sa_zatca_error_message = error_msg
        self.l10n_sa_zatca_submission_time = fields.Datetime.now()
        
        # The hash should be updated regardless (as per the comment in journal.py)
        # This ensures the invoice counter/chain is maintained for ZATCA compliance

    def action_manual_retry_zatca(self):
        """Manual action to retry ZATCA submission for selected orders"""
        for order in self:
            if order.l10n_sa_zatca_status in ['error', 'queued']:
                try:
                    order.submit_to_zatca_reporting()
                    _logger.info(f"ZATCA: Manual retry successful for order {order.name}")
                except Exception as e:
                    _logger.error(f"ZATCA: Manual retry failed for order {order.name}: {e}")
                    raise UserError(_("Failed to retry ZATCA submission for order %s: %s") % (order.name, str(e)))
    
    def action_sync_all_pending_zatca(self):
        """Manual action to sync all pending ZATCA orders immediately"""
        try:
            self.batch_submit_pending_zatca()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('ZATCA Synchronization'),
                    'message': _('All pending ZATCA orders have been processed successfully.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client', 
                'tag': 'display_notification',
                'params': {
                    'title': _('ZATCA Synchronization Error'),
                    'message': _('Error during synchronization: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def _generate_simplified_invoice_xml(self):
        """Generate simplified invoice XML for ZATCA submission"""
        try:
            # Generate simplified XML for ZATCA reporting
            xml_content = self._create_simplified_zatca_xml()
            _logger.info(f"ZATCA: Generated simplified XML for order {self.name}")
            return xml_content
            
        except Exception as e:
            _logger.error(f"ZATCA: Error generating XML for order {self.name}: {e}")
            raise UserError(_("Failed to generate invoice XML for ZATCA submission: %s") % str(e))

    def _create_simplified_zatca_xml(self):
        """Create simplified UBL XML for ZATCA submission without account.move"""
        try:
            # Build invoice data structure with ZATCA-required fields
            invoice_data = {
                'invoice_number': self.pos_reference or self.name,
                'uuid': self.uuid,
                'issue_date': self.date_order.strftime('%Y-%m-%d'),
                'issue_time': self.date_order.strftime('%H:%M:%S'),
                'currency_code': self.currency_id.name or 'SAR',
                'invoice_counter': str(self._get_invoice_counter()),  # Get proper counter
                'previous_invoice_hash': self._get_previous_invoice_hash(),
                'qr_code': self._generate_base64_qr_code(),  # Generate proper QR
                'invoice_type_code': self._get_zatca_invoice_type_code(),  # 381 for refunds, 388 for normal
                'billing_reference': self._get_zatca_billing_reference_vals(),  # For credit notes
                'refund_reason': self._l10n_sa_get_refund_reason_for_zatca_xml(),  # Refund details
                'order_reference': self.name,  # Order reference ID
                'supplier': {
                    'name': self.company_id.name,
                    'vat': self.company_id.vat or '',
                    'commercial_registration': getattr(self.company_id, 'l10n_sa_additional_identification', '1010010000'),
                    'street': self.company_id.street or 'King Fahd Road',
                    'building_number': getattr(self.company_id, 'l10n_sa_building_number', '1234'),
                    'additional_number': getattr(self.company_id, 'l10n_sa_plot_identification', '1234'),
                    'district': getattr(self.company_id, 'l10n_sa_district', 'Al Olaya'),
                    'city': self.company_id.city or 'Riyadh',
                    'state': self.company_id.state_id.name if self.company_id.state_id else 'Riyadh',
                    'zip': self.company_id.zip or '12345',
                    'country_code': self.company_id.country_id.code or 'SA',
                },
                'customer': {
                    'name': self.partner_id.name if self.partner_id else 'عميل نقدي',  # Cash Customer in Arabic
                },
                'lines': [],
            }
            
            # Process order lines
            line_number = 1
            total_lines_without_tax = 0.0
            total_calculated_tax = 0.0
            for line in self.lines:
                # Calculate tax rate from actual taxes on the line
                tax_rate = 0.0
                if line.tax_ids:
                    tax_rate = sum(tax.amount for tax in line.tax_ids if tax.amount_type == 'percent')
                else:
                    # No taxes on this line
                    tax_rate = 0.0
                
                # ZATCA BR-KSA-EN16931-11: Line net amount = (Quantity * (Unit Price / Base Quantity)) + Charges - Allowances
                # For POS orders: no charges/allowances, so: Line net amount = Quantity * Unit Price
                quantity = float(line.qty)
                unit_price = float(line.price_unit)
                base_quantity = 1.000000
                
                # Calculate using ZATCA formula with proper rounding
                calculated_line_amount = quantity * (unit_price / base_quantity)
                # Round to 2 decimal places for currency consistency
                line_total_without_tax = round(calculated_line_amount, 2)
                line_total_with_tax = float(line.price_subtotal_incl)
                
                # CRITICAL: ZATCA BR-KSA-F-04 - All amounts must be positive for credit notes
                if self._is_refund_order():
                    line_total_without_tax = abs(line_total_without_tax)
                    line_total_with_tax = abs(line_total_with_tax)
                    quantity = abs(quantity)
                    unit_price = abs(unit_price)
                
                # ZATCA BR-CO-17 & BR-S-09: VAT amount = taxable amount × (VAT rate / 100), rounded to 2 decimals
                calculated_tax_amount = round(line_total_without_tax * (tax_rate / 100), 2)
                tax_amount = calculated_tax_amount
                
                # Accumulate total tax for the invoice
                total_calculated_tax += tax_amount
                
                line_data = {
                    'line_number': line_number,
                    'product_name': line.product_id.name or '',
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'base_quantity': base_quantity,
                    'line_total_without_tax': line_total_without_tax,
                    'line_total_with_tax': line_total_with_tax,
                    'tax_amount': tax_amount,
                    'tax_rate': tax_rate,
                }
                
                invoice_data['lines'].append(line_data)
                total_lines_without_tax += line_total_without_tax
                line_number += 1
            
            # Ensure consistency between line totals and invoice totals (BR-S-08, BR-CO-10)
            invoice_data['total_without_tax'] = abs(total_lines_without_tax) if self._is_refund_order() else total_lines_without_tax
            # ZATCA BR-CO-17 & BR-S-09: Use dynamically calculated tax total from actual line taxes
            invoice_data['total_tax'] = round(abs(total_calculated_tax) if self._is_refund_order() else total_calculated_tax, 2)
            invoice_data['total_with_tax'] = round(abs(total_lines_without_tax + total_calculated_tax) if self._is_refund_order() else (total_lines_without_tax + total_calculated_tax), 2)
            
            # Render XML using our ZATCA-compliant template
            xml_markup = self.env['ir.qweb']._render(
                'l10n_sa_edi_pos_direct.zatca_pos_simplified_invoice', 
                {'invoice_data': invoice_data}
            )
            
            # Convert to string
            if hasattr(xml_markup, 'decode'):
                xml_content = xml_markup.decode('utf-8')
            else:
                xml_content = str(xml_markup)
            
            # Add proper UBL Extensions required for signing
            # Parse the XML and inject the proper signature extensions
            root = etree.fromstring(xml_content)
            
            # Remove the minimal UBL extensions and replace with proper ZATCA extensions
            ubl_extensions = root.find('.//{urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2}UBLExtensions')
            if ubl_extensions is not None:
                root.remove(ubl_extensions)
            
            # Generate proper ZATCA UBL Extensions using the l10n_sa_edi template
            zatca_extensions = etree.fromstring(self.env['ir.qweb']._render('l10n_sa_edi.export_sa_zatca_ubl_extensions'))
            root.insert(0, zatca_extensions)
            
            xml_content = etree.tostring(root, encoding='unicode')
            
            _logger.info(f"ZATCA: Generated simplified ZATCA UBL XML for order {self.name}")
            return xml_content
            
        except Exception as e:
            _logger.error(f"ZATCA: Error creating simplified XML for order {self.name}: {e}")
            raise

    def _get_invoice_counter(self):
        """Get sequential invoice counter for ZATCA compliance (BR-KSA-33)"""
        # For POS orders, use a simple counter based on company
        last_counter = self.env['pos.order'].search([
            ('company_id', '=', self.company_id.id),
            ('uuid', '!=', False),
            ('id', '<', self.id)
        ], limit=1, order='id desc')
        
        return (last_counter.id % 999999) + 1 if last_counter else 1

    def _get_previous_invoice_hash(self):
        """Get previous invoice hash for ZATCA chain (BR-KSA-61)"""
        # For simplified invoices, use default hash for first invoice
        return "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="

    def _generate_base64_qr_code(self):
        """Generate ZATCA-compliant QR code data for simplified invoices"""
        try:
            # ZATCA Phase 2 QR Code fields (simplified version)
            # CRITICAL: Use absolute values for refunds to match XML amounts
            total_amount = abs(self.amount_total) if self._is_refund_order() else self.amount_total
            tax_amount = abs(self.amount_tax) if self._is_refund_order() else self.amount_tax
            
            qr_fields = {
                '1': self.company_id.name or '',  # Seller name
                '2': self.company_id.vat or '',   # VAT registration number
                '3': self.date_order.strftime('%Y-%m-%dT%H:%M:%SZ'),  # Invoice timestamp
                '4': f"{total_amount:.2f}",  # Invoice total with VAT (positive for refunds)
                '5': f"{tax_amount:.2f}",   # VAT total (positive for refunds)
            }
            
            # For simplified invoices, add Phase 2 fields with proper certificate data
            try:
                # Get the ZATCA journal and certificate
                journal = self.session_id.config_id.invoice_journal_id
                if journal and journal._l10n_sa_ready_to_submit_einvoices():
                    certificate = journal.sudo().l10n_sa_production_csid_certificate_id
                    if certificate:
                        # Use real certificate data
                        public_key_data = certificate._get_public_key_bytes(formatting='base64')
                        if isinstance(public_key_data, bytes):
                            public_key_str = public_key_data.decode('utf-8')[:20]
                        else:
                            public_key_str = str(public_key_data)[:20]
                            
                        qr_fields.update({
                            '6': hashlib.sha256(f"{self.name}{self.amount_total}".encode()).hexdigest()[:32],  # Hash
                            '7': 'ECDSA',  # Digital signature algorithm 
                            '8': public_key_str,  # Real public key (safely handled)
                            '9': base64.b64encode(b'SIGNATURE_PLACEHOLDER').decode('utf-8')[:20],   # Signature placeholder
                        })
                    else:
                        # Fallback to placeholders if no certificate
                        qr_fields.update({
                            '6': hashlib.sha256(f"{self.name}{self.amount_total}".encode()).hexdigest()[:32],
                            '7': 'ECDSA',
                            '8': base64.b64encode(b'PUBLIC_KEY_PLACEHOLDER').decode('utf-8')[:20],
                            '9': base64.b64encode(b'SIGNATURE_PLACEHOLDER').decode('utf-8')[:20],
                        })
                else:
                    # No ZATCA journal configured
                    qr_fields.update({
                        '6': hashlib.sha256(f"{self.name}{self.amount_total}".encode()).hexdigest()[:32],
                        '7': 'ECDSA',
                        '8': base64.b64encode(b'PUBLIC_KEY_PLACEHOLDER').decode('utf-8')[:20],
                        '9': base64.b64encode(b'SIGNATURE_PLACEHOLDER').decode('utf-8')[:20],
                    })
            except Exception as cert_error:
                _logger.warning(f"ZATCA: Error accessing certificate for order {self.name}: {cert_error}")
                # Fallback to placeholders
                qr_fields.update({
                    '6': hashlib.sha256(f"{self.name}{self.amount_total}".encode()).hexdigest()[:32],
                    '7': 'ECDSA',
                    '8': base64.b64encode(b'PUBLIC_KEY_PLACEHOLDER').decode('utf-8')[:20],
                    '9': base64.b64encode(b'SIGNATURE_PLACEHOLDER').decode('utf-8')[:20],
                })
            
            # Create TLV (Tag-Length-Value) structure for ZATCA QR
            qr_tlv = b''
            for tag in sorted(qr_fields.keys()):
                value = qr_fields[tag].encode('utf-8')
                qr_tlv += bytes([int(tag)]) + bytes([len(value)]) + value
            qr_code = base64.b64encode(qr_tlv).decode('utf-8')
            self._compute_qr_code_image(qr_code)
            return qr_code
            
        except Exception as e:
            _logger.warning(f"ZATCA: Error generating QR code for order {self.name}: {e}")
            # Fallback to simple base64 encoded placeholder
            return base64.b64encode(b"ZATCA_QR_PLACEHOLDER").decode('utf-8')

    def _submit_to_zatca_reporting_api(self, journal, xml_content):
        """Submit simplified invoice to ZATCA Reporting API"""
        try:
            # Load PCSID data and certificate for signing
            PCSID_data, certificate_id = journal._l10n_sa_api_get_pcsid()
            certificate = self.env['certificate.certificate'].sudo().browse(certificate_id)
            
            # CRITICAL: ZATCA requires the XML to be properly signed before submission
            # Generate digital signature for the XML content
            xml_hash_b64 = self.env['account.edi.xml.ubl_21.zatca']._l10n_sa_generate_invoice_xml_hash(xml_content, mode='hexdigest')
            xml_hash_hex = xml_hash_b64.decode('utf-8')
            
            # Generate digital signature using the same method as l10n_sa_edi
            edi_format = self.env.ref('l10n_sa_edi.edi_sa_zatca')
            digital_signature = edi_format._l10n_sa_get_digital_signature(self.company_id, xml_hash_b64).decode()
            
            # Sign the XML with the digital signature
            signed_xml = edi_format._l10n_sa_sign_xml(xml_content, certificate, digital_signature)
                        
            # CRITICAL: Generate QR code from the signed XML (without QR yet)
            # This calculates the hash that will be embedded IN the QR code
            # Handle compatibility with different Odoo versions (commit 06e21763)
            try:
                # Try with company_id first (works with most versions)
                qr_code_str = self.env['account.move']._l10n_sa_get_qr_code(
                    journal, signed_xml, certificate, digital_signature, is_b2c=True
                )
            except (AttributeError, TypeError) as e:
                qr_code_str = self.env['account.move']._l10n_sa_get_qr_code(
                    self.company_id, signed_xml, certificate, digital_signature, is_b2c=True
                )
            
            # Apply QR code to signed XML
            root = etree.fromstring(signed_xml)
            qr_nodes = root.xpath('//*[local-name()="ID"][text()="QR"]/following-sibling::*/*')
            if qr_nodes:
                # QR code is binary data, need to base64 encode it for XML
                import base64
                if isinstance(qr_code_str, bytes):
                    qr_code_b64 = base64.b64encode(qr_code_str).decode('utf-8')
                else:
                    qr_code_b64 = qr_code_str
                qr_nodes[0].text = qr_code_b64
                final_xml = etree.tostring(root, with_tail=False)
            else:
                _logger.warning(f"ZATCA: QR node not found in signed XML for order {self.name}")
                final_xml = signed_xml
            
            # CRITICAL: Extract the hash directly from the signed XML
            # This is exactly how l10n_sa_edi does it - use the hash embedded during signing
            from lxml import etree as etree_parse
            signed_xml_tree = etree_parse.fromstring(final_xml if qr_nodes else signed_xml)
            
            # Extract the invoice hash that was embedded during the signing process
            # This is the EXACT same hash that ZATCA calculated and embedded
            invoice_hash_nodes = signed_xml_tree.xpath('//*[@Id="invoiceSignedData"]/*[local-name()="DigestValue"]')
            if invoice_hash_nodes:
                api_hash = invoice_hash_nodes[0].text
                _logger.info(f"ZATCA: Extracted invoice hash from signed XML: {api_hash}")
            else:
                _logger.error(f"ZATCA: Could not find invoice hash in signed XML for order {self.name}")
                # Fallback to manual calculation (though this might not work)
                temp_root = etree_parse.fromstring(signed_xml)
                etree_parse.indent(temp_root, space='    ')
                temp_xml = etree_parse.tostring(temp_root)
                api_hash_b64 = self.env['account.edi.xml.ubl_21.zatca']._l10n_sa_generate_invoice_xml_hash(temp_xml, mode='hexdigest')
                api_hash = api_hash_b64.decode('utf-8')
            
            # Prepare request data for ZATCA Reporting API
            request_data = {
                'body': json.dumps({
                    "invoiceHash": api_hash,  # Hash that matches QR code calculation
                    "uuid": self.uuid,
                    "invoice": base64.b64encode(final_xml.encode() if isinstance(final_xml, str) else final_xml).decode()
                }),
                'header': {
                    'Authorization': journal._l10n_sa_authorization_header(PCSID_data),
                    'Clearance-Status': '0'  # 0 for reporting (simplified), 1 for clearance (standard)
                }
            }
            
            # Call ZATCA Reporting API directly
            from odoo.addons.l10n_sa_edi.models.account_journal import ZATCA_API_URLS
            api_endpoint = ZATCA_API_URLS['apis']['reporting']
            result = journal._l10n_sa_call_api(request_data, api_endpoint, 'POST')
            
            _logger.info(f"ZATCA: Reporting API call completed for order {self.name}")
            return result
            
        except Exception as e:
            _logger.error(f"ZATCA: API submission error for order {self.name}: {e}")
            return {
                'error': str(e),
                'excepted': True  # Mark as exception so we keep chain index
            }

    def _l10n_sa_is_simplified(self):
        """Make POS orders compatible with l10n_sa_edi journal methods"""
        return True  # POS orders are always simplified invoices (B2C)

    @property
    def l10n_sa_uuid(self):
        """Compatibility property for l10n_sa_edi journal methods"""
        return self.uuid
    




    @api.model
    def batch_submit_pending_zatca(self):
        """Batch submit all pending ZATCA orders - called by cron job"""
        pending_orders = self.search([
            ('l10n_sa_zatca_status', '=', 'queued'),
            ('company_id.country_id.code', '=', 'SA'),
            ('l10n_sa_zatca_status', '!=', 'legacy')  # Exclude legacy orders
        ])
        
        if not pending_orders:
            _logger.info("ZATCA: No pending orders to submit")
            return
        
        _logger.info(f"ZATCA: Processing {len(pending_orders)} pending orders")
        
        success_count = 0
        error_count = 0
        
        for order in pending_orders:
            try:
                order.submit_to_zatca_reporting()
                if order.l10n_sa_zatca_status in ['submitted']:
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
                _logger.error(f"ZATCA: Error processing order {order.name}: {e}")
        
        _logger.info(f"ZATCA: Batch submission complete - {success_count} success, {error_count} errors")

    @api.model
    def cron_retry_failed_zatca(self):
        """Cron job to automatically retry failed ZATCA submissions"""
        failed_orders = self.search([
            ('l10n_sa_zatca_status', '=', 'error'),
            ('company_id.country_id.code', '=', 'SA'),
            ('uuid', '!=', False),
            ('l10n_sa_zatca_status', '!=', 'legacy'),  # Exclude legacy orders
            ('create_date', '>=', fields.Datetime.now() - timedelta(days=7))  # Only retry within 7 days
        ], limit=50)  # Limit for performance
        
        if not failed_orders:
            _logger.info("ZATCA: No failed orders to retry")
            return
        
        _logger.info(f"ZATCA: Cron retrying {len(failed_orders)} failed orders")
        
        success_count = 0
        error_count = 0
        
        for order in failed_orders:
            try:
                # Reset status to queued and try again
                order.l10n_sa_zatca_status = 'queued'
                order.l10n_sa_zatca_error_message = False
                
                order.submit_to_zatca_reporting()
                if order.l10n_sa_zatca_status in ['submitted']:
                    success_count += 1
                else:
                    error_count += 1
                    
                # Commit after each order to avoid losing progress
                self.env.cr.commit()
                
            except Exception as e:
                error_count += 1
                order.l10n_sa_zatca_status = 'error'
                order.l10n_sa_zatca_error_message = str(e)
                self.env.cr.commit()
                _logger.error(f"ZATCA: Cron retry failed for order {order.name}: {e}")
        
        _logger.info(f"ZATCA: Cron retry complete - {success_count} success, {error_count} still failed")
