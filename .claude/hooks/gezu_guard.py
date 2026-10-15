#!/usr/bin/env python3
"""GeZu SEO execution-layer guard (Claude Code PreToolUse / PostToolUse / SessionStart hook).

Enforces the SEO routines' write scope in code, independent of the prompt:
  * MCP tool allowlist per connector (anything not listed is blocked).
  * Shopify Admin GraphQL mutations: allowlisted root fields, each with argument checks.
  * Per-session rate caps (articles, product SEO edits, image generations, alt edits).
  * Metaobject deletes only for objects this same session created (lock release).

Fail closed: any internal error on a write-capable tool blocks the call.
Python standard library only. Exit code 2 + stderr = block (Claude Code hook protocol).
"""
import json
import os
import re
import sys
import time

STATE_DIR = os.environ.get("GEZU_GUARD_DIR", "/tmp/gezu-guard")
ALLOWED_METAOBJECT_TYPE = "gezu_seo_doc"

# Per-session caps (execution-layer cost and blast-radius limits).
CAPS = {
    "articleCreate": 2,          # today's slot + one missed-slot recovery
    "articleUpdate": 12,         # hero image + queued reverse links
    "product_seo_edit": 10,      # productUpdate / collectionUpdate seo + seo metafields
    "file_alt_edit": 200,        # alt-text entries in fileUpdate
    "image_generation": 6,       # Higgsfield generate_image calls (credits)
    "translationsRegister": 30,  # 12 locales x up to 2 articles + slack
    "outlook_draft": 10,         # outreach drafts (never sent)
}

# ---------------------------------------------------------------- MCP tool policy
# Exact tool names (without the mcp__<server>__ prefix) or regexes, per server.
ALLOW = {
    "Shopify": [
        r"graphql_query", r"graphql_schema", r"graphql_mutation",  # mutation body checked below
        r"get-shop-info", r"get-product", r"get-collection", r"search_products",
        r"search_collections", r"search_docs_chunks", r"validate_graphql_codeblocks",
        r"run-analytics-query", r"get-inventory-levels",
    ],
    "Ryze_AI": [
        r"native__list_connections", r"native__get_workspaces", r"native__get_provider_docs",
        r"google_ads__generateKeyword(Ideas|HistoricalMetrics)", r"google_ads__listAccessibleCustomers",
        r"google_ads__getAccountSummary", r"google_ads__getAccountHierarchy", r"google_ads__runRawGaql",
        r"google_search_console__(runRawSearchAnalytics|listSites|listSitemaps|inspectUrl|getIndexationSummary)",
        r"google_analytics__(get\w+|listAccountSummaries|run(Raw|Pivot|Realtime)Report|runAdminRead)",
        r"shopify__(read|search_content)",
    ],
    "Higgsfield": [
        r"generate_image", r"generate_image_batch", r"jobs_wait", r"job_display", r"balance",
        r"show_plans_and_credits", r"show_generation_by_ids", r"show_generations", r"show_result",
        r"show_medias", r"media_import_url", r"media_upload", r"media_confirm", r"models_explore",
        r"get_preferences", r"list_workspaces", r"show_credit_reset", r"transactions",
    ],
    "Microsoft_365": [
        r"outlook_email_search", r"outlook_create_draft", r"read_resource", r"get_me",
        r"get_granted_scopes", r"search_people",
    ],
    "Klaviyo": [r"get_\w+", r"query_\w+", r"list_\w+"],
    "Supermetrics_Marketing_Analytics": [
        r"data_source_discovery", r"accounts_discovery", r"field_discovery", r"data_query",
        r"get_async_query_results", r"get_today", r"supermetrics_guide",
    ],
    "Claude_Docs": [r"guide", r"query", r"read"],
}

# --------------------------------------------------------------- GraphQL helpers

def _strip(text):
    """Remove comments and string literals so structure can be scanned safely."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "#":
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith('"""', i):
            j = text.find('"""', i + 3)
            i = n if j < 0 else j + 3
            out.append('""')
        elif c == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
            out.append('""')
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _matching(s, i, open_c, close_c):
    depth = 0
    for j in range(i, len(s)):
        if s[j] == open_c:
            depth += 1
        elif s[j] == close_c:
            depth -= 1
            if depth == 0:
                return j
    raise ValueError("unbalanced GraphQL document")


def mutation_root_fields(query):
    """Return [(field_name, raw_args_text)] for every top-level field of every operation.

    Raises ValueError for anything other than plain mutation operations (fragments,
    subscriptions, anonymous/shorthand docs are rejected: fail closed)."""
    s = _strip(query)
    fields, i = [], 0
    while True:
        m = re.compile(r"\S").search(s, i)
        if not m:
            break
        k = m.start()
        head = re.compile(r"(mutation)\b[^{]*").match(s, k)
        if not head:
            raise ValueError("only named/anonymous 'mutation' operations are allowed")
        b = s.find("{", head.end())
        if b < 0:
            raise ValueError("mutation without selection set")
        e = _matching(s, b, "{", "}")
        body, p = s[b + 1:e], 0
        while p < len(body):
            fm = re.compile(r"\s*(?:([_A-Za-z]\w*)\s*:\s*)?([_A-Za-z]\w*)\s*").match(body, p)
            if not fm or fm.end() == p:
                if body[p:].strip() == "":
                    break
                raise ValueError("cannot parse selection near: %r" % body[p:p + 40])
            name, p = fm.group(2), fm.end()
            if name.startswith("__") or name == "fragment":
                raise ValueError("introspection/fragments not allowed in mutations")
            args = ""
            if p < len(body) and body[p] == "(":
                q = _matching(body, p, "(", ")")
                args, p = body[p + 1:q], q + 1
            while p < len(body) and body[p].isspace():
                p += 1
            if p < len(body) and body[p] == "{":
                p = _matching(body, p, "{", "}") + 1
            fields.append((name, args))
        i = e + 1
    if not fields:
        raise ValueError("no mutation fields found")
    return fields


def _walk(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path + (k,), v
            yield from _walk(v, path + (k,))
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v, path)


def _arg_vars(args, variables):
    """Values of the $variables referenced by a field's arguments, keyed by argument name."""
    return {a: variables.get(v) for a, v in re.findall(r"(\w+)\s*:\s*\$(\w+)", args)}


def _has_inline_object(args):
    return "{" in args or "[" in args


# --------------------------------------------------------------- state / counters

def _state_path(name):
    os.makedirs(STATE_DIR, exist_ok=True)
    return os.path.join(STATE_DIR, name)


def _load_counts():
    try:
        with open(_state_path("counts.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _bump(counts, key, by=1):
    counts[key] = counts.get(key, 0) + by
    if counts[key] > CAPS[key]:
        raise PermissionError("session cap reached for %s (%d)" % (key, CAPS[key]))


def _save_counts(counts):
    with open(_state_path("counts.json"), "w") as f:
        json.dump(counts, f)


def _created_ids():
    try:
        with open(_state_path("created_metaobjects.txt")) as f:
            return {l.strip() for l in f if l.strip()}
    except OSError:
        return set()


def log(decision, tool, detail):
    try:
        with open(_state_path("decisions.log"), "a") as f:
            f.write("%s\t%s\t%s\t%s\n" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), decision, tool, detail[:300]))
    except OSError:
        pass


# --------------------------------------------------------------- mutation policy

FORBIDDEN_TOKENS = re.compile(
    r"\b(price|compareAtPrice|inventory\w*|cost|taxable|taxCode|redirectNewHandle|"
    r"requiresShipping|weight|sku|barcode|publishDate|publishedAt|templateSuffix)\b")


def check_mutation(query, variables, counts):
    variables = variables or {}
    vtext = json.dumps(variables)
    fields = mutation_root_fields(query)
    for name, args in fields:
        if name in ("metaobjectCreate", "metaobjectUpsert"):
            types = re.findall(r'type\s*:\s*"([^"]*)"', query) + \
                [v for p, v in _walk(variables) if p and p[-1] == "type"]
            if not types or any(t != ALLOWED_METAOBJECT_TYPE for t in types):
                raise PermissionError("%s only allowed for type %s" % (name, ALLOWED_METAOBJECT_TYPE))
        elif name == "metaobjectDelete":
            ids = re.findall(r'gid://shopify/Metaobject/\d+', query + vtext)
            own = _created_ids()
            if not ids or any(i not in own for i in ids):
                raise PermissionError("metaobjectDelete only for metaobjects created in this session (lock release)")
        elif name == "articleCreate":
            blob = query + vtext
            if not re.search(r'"?isPublished"?\s*:\s*false', blob) or re.search(r'"?isPublished"?\s*:\s*true', blob):
                raise PermissionError("articleCreate must set isPublished: false (drafts only)")
            if FORBIDDEN_TOKENS.search(args) or re.search(r'"(publishDate|publishedAt)"', vtext):
                raise PermissionError("articleCreate may not schedule publication")
            _bump(counts, "articleCreate")
        elif name == "articleUpdate":
            blob = query + vtext
            if re.search(r'"?isPublished"?\s*:\s*true', blob) or re.search(r'\b(handle|redirectNewHandle|publishDate|publishedAt)\b', args + " " + " ".join(p[-1] for p, _ in _walk(variables))):
                raise PermissionError("articleUpdate may not publish, schedule or change handles")
            _bump(counts, "articleUpdate")
        elif name == "metafieldsSet":
            mfs = [v for v in _arg_vars(args, variables).values() if isinstance(v, list)]
            if _has_inline_object(args) or not mfs:
                raise PermissionError("metafieldsSet must pass metafields via variables")
            for lst in mfs:
                for mf in lst:
                    ns, key = mf.get("namespace"), mf.get("key")
                    owner = str(mf.get("ownerId", ""))
                    if ns == "global" and key in ("title_tag", "description_tag"):
                        if "/Product/" in owner or "/Collection/" in owner:
                            _bump(counts, "product_seo_edit")
                        elif "/Article/" not in owner:
                            raise PermissionError("SEO metafields only on articles, products, collections")
                    elif ns == "gezu" and "/Product/" in owner:
                        pass  # additive review data; additive-only rule enforced by playbook + changelog
                    else:
                        raise PermissionError("metafield %s.%s not in SEO allowlist" % (ns, key))
        elif name == "translationsRegister":
            if _has_inline_object(args):
                raise PermissionError("translationsRegister must use variables")
            rid = str(_arg_vars(args, variables).get("resourceId") or "")
            keys = [v for p, v in _walk(variables) if p and p[-1] == "key"]
            allowed = {"title", "body_html", "summary_html", "meta_title", "meta_description", "handle"}
            if any(k not in allowed for k in keys):
                raise PermissionError("translation key outside SEO allowlist")
            if "handle" in keys and "/Article/" not in rid:
                raise PermissionError("translated handles only for articles (no product/collection URL changes)")
            if "/Article/" not in rid and any(k in ("title", "body_html") for k in keys):
                raise PermissionError("product/collection title or description translations need owner approval")
            _bump(counts, "translationsRegister")
        elif name in ("productUpdate", "collectionUpdate"):
            if _has_inline_object(args):
                raise PermissionError("%s must pass input via variables" % name)
            top = [v for v in _arg_vars(args, variables).values() if isinstance(v, dict)]
            if len(top) != 1:
                raise PermissionError("%s needs exactly one input object" % name)
            inp = top[0]
            if set(inp) - {"id", "seo"} or set(inp.get("seo") or {}) - {"title", "description"}:
                raise PermissionError("%s may only change seo.title / seo.description" % name)
            _bump(counts, "product_seo_edit")
        elif name == "fileUpdate":
            files = [v for v in _arg_vars(args, variables).values() if isinstance(v, list)]
            if _has_inline_object(args) or not files:
                raise PermissionError("fileUpdate must pass files via variables")
            for lst in files:
                for f in lst:
                    if set(f) - {"id", "alt"}:
                        raise PermissionError("fileUpdate may only change alt text")
                    _bump(counts, "file_alt_edit")
        elif name in ("stagedUploadsCreate", "fileCreate"):
            pass  # adding new image files for drafts is non-destructive
        else:
            raise PermissionError("mutation %s is outside the SEO routines' scope" % name)
    return [n for n, _ in fields]


# --------------------------------------------------------------- hook entrypoints

def pre_tool_use(event):
    tool = event.get("tool_name", "")
    tinput = event.get("tool_input") or {}
    if not tool.startswith("mcp__"):
        return
    parts = tool.split("__", 2)
    server, name = (parts[1], parts[2]) if len(parts) == 3 else ("", "")
    patterns = ALLOW.get(server)
    if patterns is None or not any(re.fullmatch(p, name) for p in patterns):
        raise PermissionError("tool %s is not in the GeZu SEO allowlist" % tool)
    counts = _load_counts()
    if server == "Shopify" and name == "graphql_mutation":
        roots = check_mutation(tinput.get("query", ""), tinput.get("variables"), counts)
        log("allow", tool, ",".join(roots))
    elif server == "Higgsfield" and name.startswith("generate_image"):
        n = len(tinput.get("jobs") or tinput.get("requests") or [1]) if name.endswith("batch") else 1
        _bump(counts, "image_generation", n)
    elif server == "Microsoft_365" and name == "outlook_create_draft":
        _bump(counts, "outlook_draft")
    elif server == "Ryze_AI" and name == "google_ads__runRawGaql":
        if re.search(r"\b(mutate|create|update|remove)\b", json.dumps(tinput), re.I):
            raise PermissionError("GAQL is read-only here")
    _save_counts(counts)


def post_tool_use(event):
    """Remember metaobjects this session created so it may release (delete) them later."""
    if event.get("tool_name") != "mcp__Shopify__graphql_mutation":
        return
    resp = json.dumps(event.get("tool_response", ""))
    if "metaobjectCreate" not in resp and "metaobjectCreate" not in json.dumps(event.get("tool_input", "")):
        return
    ids = set(re.findall(r"gid://shopify/Metaobject/\d+", resp))
    if ids:
        with open(_state_path("created_metaobjects.txt"), "a") as f:
            for i in sorted(ids):
                f.write(i + "\n")


def session_start(_event):
    with open(_state_path("ACTIVE"), "w") as f:
        f.write("gezu-guard active %s\n" % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "pre"
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except ValueError:
        event = {}
    try:
        {"pre": pre_tool_use, "post": post_tool_use, "session": session_start}[mode](event)
    except PermissionError as e:
        log("block", event.get("tool_name", ""), str(e))
        sys.stderr.write("GEZU GUARD BLOCKED: %s. Log it as a blocked action and continue with safe work.\n" % e)
        sys.exit(2)
    except Exception as e:  # fail closed on write-capable calls, open on pure reads
        tool = event.get("tool_name", "")
        log("error", tool, repr(e))
        if mode == "pre" and tool.startswith("mcp__"):
            sys.stderr.write("GEZU GUARD ERROR (fail closed): %r\n" % e)
            sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
