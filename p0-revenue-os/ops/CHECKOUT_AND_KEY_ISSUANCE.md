# P0 — Checkout and key issuance

Canonical path on intel.cyberdudebivash.com: `/upgrade.html`

## Flow
1. User picks SKU from `config/sku_catalog.json`.
2. India + GSTIN present → Razorpay (UPI/card/netbanking) + 18% GST line item.
3. Rest of world → Gumroad or invoice (Enterprise / MSSP).
4. Payment webhook marks entitlement in the same store the API auth reads.
5. System emails API key, curl smoke test, onboarding link, GST invoice PDF when INR.
6. SLA: key in inbox ≤ 10 minutes for Pro.
