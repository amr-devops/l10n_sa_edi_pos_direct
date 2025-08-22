# l10n_sa_edi_pos_direct

**Enhanced Saudi Arabia ZATCA Integration for Point of Sale**

An optimized replacement for the standard `l10n_sa_edi_pos` module, providing direct ZATCA integration with significant performance improvements and enhanced functionality.

## Overview / نظرة عامة

An optimized replacement for the standard `l10n_sa_edi_pos` module, providing direct ZATCA integration with significant performance improvements and enhanced functionality designed specifically for high-volume retail environments in Saudi Arabia.

موديول محسن بديل عن `l10n_sa_edi_pos` الافتراضي، يوفر تكامل مباشر مع هيئة الزكاة والضريبة مع تحسينات كبيرة في الأداء ووظائف محسنة

## Module Comparison / مقارنة الموديولات

| Feature / الخاصية | l10n_sa_edi_pos (Standard / الافتراضي) | l10n_sa_edi_pos_direct (Enhanced / المحسن) |
|---------|---------------------------|-----------------------------------|
| **Customer Data Requirement / متطلبات بيانات العميل** | ❌ Requires full customer data for every POS transaction<br/>يتطلب بيانات العميل كاملة مع كل عملية | ✅ Cash customer support (no customer data needed)<br/>دعم العميل النقدي (لا يتطلب بيانات العميل) |
| **PDF Generation / إنشاء ملف PDF** | ❌ Creates A4 PDF invoice for every POS order<br/>ينشئ فاتورة PDF مع كل طلب | ✅ No PDF generation - POS receipts only<br/>لا ينشئ PDF - إيصالات نقاط البيع فقط |
| **Database Load / حمل قاعدة البيانات** | ❌ Need to connect database with every transaction<br/>يتطلب الاتصال بقاعدة البيانات مع كل عملية | ✅ Minimal database impact - frontend processing<br/>تأثير قليل على قاعدة البيانات - معالجة على واجهة نقاط البيع فقط |
| **QR Code Compliance / امتثال رمز QR** | ❌ POS Receipts QR Code with Basic Phase 1 (only 5 fields)<br/>رمز QR بالمرحلة الأولى الأساسية (5 حقول فقط) | ✅ POS Receipts QR Code with Full Phase 2 (9 fields + digital signatures)<br/>رمز QR بالمرحلة الثانية كاملة (9 حقول + توقيعات رقمية) |
| **ZATCA Synchronization / مزامنة هيئة الزكاة** | ❌ Immediate sync required (not required for simplified)<br/>مزامنة فورية مطلوبة (غير مطلوبة للمبسطة) | ✅ Compliant 24-hour async reporting<br/>تقارير غير متزامنة خلال 24 ساعة حسب اللوائح |
| **Record Duplication / تكرار السجلات** | ❌ POS Order + Account Invoice (double records)<br/>طلب نقاط البيع + فاتورة محاسبية (سجلات مضاعفة) | ✅ Single POS record - no duplication<br/>سجل نقاط البيع واحد - لا تكرار |



## Installation & Configuration

1. **Remove Standard Module**: Uninstall the existing `l10n_sa_edi_pos` module from your system to avoid conflicts
2. **Install Enhanced Module**: Install `l10n_sa_edi_pos_direct` through the Apps menu or via command line
3. **Verify Configuration**: Ensure your ZATCA certificate is properly configured in the invoice journal settings
4. **Enable Direct Mode**: Navigate to POS Configuration and enable "ZATCA Direct Mode" for your point of sale
5. **Test Transactions**: Perform test transactions to verify QR code generation and ZATCA submission workflow

## Changelog

### Version 18.0.1.2.0
🔧 **Fixed Arabic Character Encoding:** Resolved btoa() InvalidCharacterError when using Arabic language interface

### Version 18.0.1.1.0
✅ **Added ZATCA Refund Features:** Interactive refund reason popup with 6 predefined codes and full ZATCA compliance (BR-KSA-17, BR-KSA-F-04)

## Support

This module is designed for **Saudi Arabian businesses** requiring **high-performance ZATCA compliance** in retail environments.

---

**Author**: EasyERPS, AMR Hawsawi  
**License**: LGPL-3  
**Website**: https://easyerps.com
