# Phase 0 Shopify Embed Spike

Verified at: 2026-04-11T18:34:01.845356-07:00

## Summary

Tested live Shopify checkout URLs generated through Storefront MCP for the two supplement merchants currently in MVP scope.

| Merchant | Product | HTTP | Iframe allowed | Why |
| --- | --- | --- | --- | --- |
| transparentlabs.com | Creatine HMB | 200 | no | Merchant CSP frame-ancestors does not allow Shopper origins. |
| livemomentous.com | Magnesium L-Threonate | 200 | no | Merchant CSP frame-ancestors does not allow Shopper origins. |

## Recommendation

Keep `SHOPIFY_CHECKOUT_EMBED_MODE=auto`, but treat auto as `external` unless the live probe explicitly allows Shopper origins. The current live merchants block iframe embedding via CSP frame-ancestors.

## Notes

- This spike validates browser iframe embedding against live merchant headers.
- A controlled fallback handoff remains the safe default for Shopify supplement checkout in the current app shell.
