# gezu-content: GeZu SEO routines, execution guard

This repo holds the code-level safety layer and the reference copies of the two GeZu SEO cloud routines. **Business state does not live here.** It lives in the Shopify store `079e8d-d3.myshopify.com` (gezuimpex.com) as `gezu_seo_doc` metaobjects, which every cloud run can read and write through the Shopify connector.

> This repository is **public**. Never commit secrets, keyword maps, customer data or anything from the store's state. Consider making it private (Settings > General > Danger zone > Change visibility).

## Components

| Piece | Where | Purpose |
|---|---|---|
| Routine A: GeZu - Multilingual SEO Content and Distribution | claude.ai/code/routines, `trig_01Ua4sGJUPCrc1oV6gCu54pz` | Article drafts Mon/Wed/Fri 09:30 Europe/Amsterdam, translations, calendar, outreach/social drafts |
| Routine B: GeZu - SEO Intelligence, Technical Health and AI Visibility | `trig_01MfAr3LDNPxJbLCMeZKNTTx` | Daily 06:17 Europe/Amsterdam diagnostics, backlog, product/collection SEO; Mon deep weekly |
| Prompts (reference copies) | `routines/*.prompt.md` | Same text as saved in the routines |
| Guard hook | `.claude/hooks/gezu_guard.py` + `.claude/settings.json` | Blocks out-of-scope tools and Shopify mutations, caps writes per run |
| Run protocol (mirror) | `config/run-protocol.md` | Locks, reservations, ledger, change log, rollback |
| Guard tests | `tests/test_guard.py` | `python3 -I -m unittest discover -s tests -v` |

## Shared state (Shopify metaobjects, type `gezu_seo_doc`)

`ops-config` (business config, ownership, scope, limits) · `run-protocol` · `core-standards` · `state-protocol` · `playbook-*` (module manuals) · `state-calendar` + chunks (authoritative content calendar) · `state-master-map` + chunks (keyword-to-URL map) · `state-backlog` (B's opportunity backlog) · `state-backlinks` · `state-ledger` (execution ledger) · `state-changelog` (field backups + change log) · `state-log` (ops log) · `lock-*` (short-lived locks) · `resv-slot-*`, `resv-kw-*` (permanent publishing reservations).

View them in Shopify Admin > Content > Metaobjects > GeZu SEO Doc.

## How the guard is enforced

Cloud sessions with exactly one repository load that repo's `.claude/settings.json`, so the hook only runs when **this repo is attached to the routine**. With the guard active:

- MCP tools outside a per-connector allowlist are blocked (sending mail, ads mutations, Shopify product/inventory tools, Sendcloud, Canva and so on).
- `graphql_mutation` is parsed. Allowed root fields: `metaobjectCreate/Upsert` (type `gezu_seo_doc` only), `metaobjectDelete` (only objects created in the same session, for lock release), `articleCreate` (must be `isPublished:false`, no publish date), `articleUpdate` (no publish, no handle change), `metafieldsSet` (SEO title/description tags and `gezu.*` review data only), `translationsRegister` (no product/collection handles, titles or bodies), `productUpdate`/`collectionUpdate` (`seo.title`/`seo.description` only), `fileUpdate` (alt only), `fileCreate`, `stagedUploadsCreate`. Everything else is blocked: prices, inventory, redirects, themes, discounts, webhooks, deletes.
- Per-session caps: 2 articles, 12 article updates, 10 product/collection SEO edits, 200 alt edits, 6 image generations, 10 outreach drafts.
- Any parse error on a mutation fails closed.

Without the repo attached, prompts run in `GUARD=off` mode: no edits to existing products, collections, files or published articles.

## Pause, resume, roll back

- **Pause a routine:** claude.ai/code/routines > routine > on/off switch (or ask Claude: `update_trigger enabled=false`).
- **Roll back a field change:** find the row in `state-changelog`; the routine or a session restores `before_value` if the live value still equals `after_value` (run-protocol section 6).
- **Roll back a draft article:** delete the draft in Shopify Admin > Blog posts. Drafts are never published by the routines.
- **Roll back the consolidation:** re-enable the superseded routines (they are disabled, not deleted) and restore the old prompts in `routines/superseded/`.
- **Roll back the guard:** detach this repo from the routine (the prompts fall back to GUARD=off).

## Installations

None. The hook uses the Python 3 standard library only (cloud image ships Python 3.13). No packages, no servers, no setup script.
