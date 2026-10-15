# Owner checklist (one pass, about 10 minutes)

The platform does not let an agent edit routines created through the HTTP API, attach repositories or connectors to a routine, or change an environment's network policy. These steps need the account owner. Everything else is already in place.

## 1. Switch the routines to the A/B design (claude.ai/code/routines)

Edit, do not recreate, so run history is kept.

**Routine `trig_01Ua4sGJUPCrc1oV6gCu54pz` (now "GeZu SEO — blog draft") becomes A**
- Name: `GeZu — Multilingual SEO Content and Distribution`
- Instructions: paste `routines/A-content-distribution.prompt.md` (whole file)
- Schedule: custom cron `CRON_TZ=Europe/Amsterdam 30 9 * * 1,3,5` (or weekly Mon/Wed/Fri 09:30 in the form with your timezone set to Amsterdam)
- Repository: add `abhishekpartigezu/gezu-content` (loads the guard hook)
- Connectors: keep Shopify, Ryze_AI, Higgsfield, Microsoft_365. Remove Sendcloud, Canva, Klaviyo, Supermetrics, Claude_Docs, Claude_Code_Remote.
- Model: keep claude-opus-5-5.

**Routine `trig_01MfAr3LDNPxJbLCMeZKNTTx` (now "GeZu SEO — daily agent") becomes B**
- Name: `GeZu — SEO Intelligence, Technical Health and AI Visibility`
- Instructions: paste `routines/B-intelligence-health.prompt.md`
- Schedule: `CRON_TZ=Europe/Amsterdam 17 6 * * *` (daily 06:17 Amsterdam)
- Repository: add `abhishekpartigezu/gezu-content`
- Connectors: keep Shopify, Ryze_AI, Klaviyo, Microsoft_365. Remove Sendcloud, Canva, Higgsfield, Supermetrics, Claude_Docs, Claude_Code_Remote.
- Model: keep claude-sonnet-5-5.

**Turn OFF (switch only, do not delete)**: Daily Auditor `trig_01PjTLJLuxNpMUkXmh9az1Fx`, search data Mon `trig_01Jgf1Na84wBg6CZvwz8CTz7`, store hygiene Tue `trig_01LzhQY9wdfTam2YHpLxEEQM`, question mining Thu `trig_01Cwu2w8Nd7QowWfo5xcjUos`, monthly `trig_01S9at3WX8yLHseo7z21p96F`, backlink builder Wed `trig_01MsqXJFS78ZLrXTfyUFmMQu`. Their work is now modules inside A and B.

Then click **Run now** on each with the text `DRY-RUN` to confirm (no content writes; one ledger row each).

## 2. Network access for live site checks (cloud environment "Default")

- Where: claude.ai/code, environment menu > Default > Edit > Network access.
- Change: keep the package-manager defaults and add the allowed domains `gezuimpex.com` and `www.gezuimpex.com`.
- Why: every storefront check (robots, sitemap, titles, canonicals, hreflang, JSON-LD, page weight) has been failing with `403 host_not_allowed` since the auditor started. Shopify Admin, GSC, GA4 and Ads work through connectors and are not affected.
- Scope: two hosts only. Do not choose Full access.

## 3. Outlook mailbox (Microsoft 365 connector)

- Error since 2026-10-14: `MailboxNotEnabledForRESTAPI` for the connected account.
- Change: reconnect the Microsoft 365 connector (claude.ai/customize/connectors) with an Exchange Online mailbox that has REST/Graph access, or enable it for the current mailbox in Microsoft 365 admin.
- Why: question mining (read-only) and outreach drafts (never sent) depend on it.
- Scope: read mail + create drafts. Sending stays blocked by the guard.

## 4. Optional

- Make `abhishekpartigezu/gezu-content` private (GitHub > Settings > Change visibility). It holds no secrets, but it does describe the automation.
- Distribb: no project or API was found (`distribb.io` does not resolve; no connector). If you use Distribb, send the project name; adding it as a destination needs your approval and an API key stored as a network secret (environment > Network secrets), never in chat.
- Ahrefs plugin connector currently fails to connect (proxy 403). Paid tiers are not approved; free data only.

## Pause or roll back at any time

- Pause: the on/off switch on each routine.
- Roll back a field: `state-changelog` row > run-protocol section 6.
- Roll back drafts: delete the draft in Shopify Admin > Blog posts.
- Undo the consolidation: switch the six routines back on and restore the two old prompts from `routines/superseded/prompts-2026-10-15.json`.
