# GeZu SEO routines

This repo is attached to the GeZu SEO cloud routines to load the execution guard (`.claude/hooks/gezu_guard.py`). The routine prompt is the task; the operating manual and all state live in Shopify `gezu_seo_doc` metaobjects (start with `ops-config` and `run-protocol`).

- Do not write business state, reports or keyword data into this repo (it is public). Never commit secrets.
- A guard block (`GEZU GUARD BLOCKED`) is final: log it as a blocked action in the ledger and continue with safe work. Never try to work around it with another tool.
- Changing the guard or tests requires a reviewed commit to `main` by the owner, never by a routine run.
