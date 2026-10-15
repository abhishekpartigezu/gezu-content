# Routine backups taken 2026-10-15 before consolidation into routines A and B

Each entry: trigger id, name, cron (UTC unless prefixed), model, enabled state before the change. The two prompts that get overwritten (A, B) are stored verbatim in `prompts-2026-10-15.json`; disabled routines keep their own prompt unchanged inside the trigger, so re-enabling restores them exactly.

| trigger | name (before) | cron before | model | action 2026-10-15 |
|---|---|---|---|---|
| trig_01Ua4sGJUPCrc1oV6gCu54pz | GeZu SEO — blog draft (Mon/Wed/Fri) | 30 7 * * 1,3,5 | claude-opus-5-5 | became routine A |
| trig_01MfAr3LDNPxJbLCMeZKNTTx | GeZu SEO — daily agent (Mon-Sat) | 45 6 * * 1-6 | claude-sonnet-5-5 | became routine B |
| trig_01PjTLJLuxNpMUkXmh9az1Fx | GeZu SEO Daily Auditor | 30 5 * * * | claude-sonnet-5 | disabled (folded into B daily core) |
| trig_01Jgf1Na84wBg6CZvwz8CTz7 | GeZu SEO — search data + GEO + social (Mon) | 0 6 * * 1 | claude-sonnet-5-5 | disabled (B Monday + A Monday social) |
| trig_01LzhQY9wdfTam2YHpLxEEQM | GeZu SEO — store hygiene (Tue) | 30 7 * * 2 | claude-sonnet-5-5 | disabled (B Tuesday) |
| trig_01Cwu2w8Nd7QowWfo5xcjUos | GeZu SEO — question mining (Thu) | 30 7 * * 4 | claude-sonnet-5-5 | disabled (B Thursday) |
| trig_01S9at3WX8yLHseo7z21p96F | GeZu SEO — monthly (1st health / 15th competitors) | 30 7 1,15 * * | claude-sonnet-5-5 | disabled (B day 1/15) |
| trig_01MsqXJFS78ZLrXTfyUFmMQu | GeZu SEO — backlink builder (Wed) | 30 8 * * 3 | claude-sonnet-5-5 | disabled (A Wednesday) |

Restore: update_trigger(trigger_id, name=<before>, cron_expression=<before>, prompt=<from json>, enabled=true).
