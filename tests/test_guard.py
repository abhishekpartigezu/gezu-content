"""Unit tests for the GeZu execution-layer guard. Run: python3 -I -m unittest discover -s tests -v"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "gezu_guard.py")


def run(event, mode="pre", state=None):
    env = dict(os.environ, GEZU_GUARD_DIR=state)
    p = subprocess.run([sys.executable, "-I", HOOK, mode], input=json.dumps(event),
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stderr


def mut(query, variables=None):
    return {"tool_name": "mcp__Shopify__graphql_mutation",
            "tool_input": {"query": query, "variables": variables or {}}}


class Guard(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp()

    def ok(self, event, mode="pre"):
        rc, err = run(event, mode, self.state)
        self.assertEqual(rc, 0, err)

    def blocked(self, event, mode="pre"):
        rc, err = run(event, mode, self.state)
        self.assertEqual(rc, 2, "expected block, got rc=%s %s" % (rc, err))
        self.assertIn("GEZU GUARD", err)

    # --- tool allowlist
    def test_reads_allowed(self):
        self.ok({"tool_name": "mcp__Shopify__graphql_query", "tool_input": {"query": "{shop{name}}"}})
        self.ok({"tool_name": "mcp__Ryze_AI__google_search_console__runRawSearchAnalytics", "tool_input": {}})

    def test_uuid_named_connector_tools(self):
        self.ok({"tool_name": "mcp__6c296c0f-fbbf-46f7-b2d8-82186bb67c0f__graphql_query", "tool_input": {"query": "{shop{name}}"}})
        self.blocked({"tool_name": "mcp__6c296c0f-fbbf-46f7-b2d8-82186bb67c0f__set-inventory", "tool_input": {}})
        self.blocked({"tool_name": "mcp__1aa4e762-1355-4968-a613-622ea8d85d6c__outlook_send_mail", "tool_input": {}})
        self.blocked({"tool_name": "mcp__316ac0fd-9999-4d7d-8700-68becc0e66eb__orders_orders_get_list_orders", "tool_input": {}})
        q = {"tool_name": "mcp__6c296c0f-fbbf-46f7-b2d8-82186bb67c0f__graphql_mutation",
             "tool_input": {"query": 'mutation { urlRedirectCreate(urlRedirect:{path:"/a", target:"/b"}){ urlRedirect{id} } }'}}
        self.blocked(q)

    def test_unknown_connector_blocked(self):
        self.blocked({"tool_name": "mcp__0000-unknown__anything", "tool_input": {}})

    def test_non_mcp_tools_untouched(self):
        self.ok({"tool_name": "Bash", "tool_input": {"command": "ls"}})

    def test_unlisted_tools_blocked(self):
        for t in ["mcp__Shopify__set-inventory", "mcp__Shopify__update-product",
                  "mcp__Ryze_AI__google_ads__runRawMutate", "mcp__Ryze_AI__shopify__write",
                  "mcp__Microsoft_365__outlook_send_mail", "mcp__Klaviyo__send_campaign",
                  "mcp__Sendcloud__orders_orders_delete_delete_order", "mcp__Higgsfield__publish_website"]:
            self.blocked({"tool_name": t, "tool_input": {}})

    # --- state metaobjects + locks
    def test_state_upsert_allowed(self):
        self.ok(mut('mutation { metaobjectUpsert(handle:{type:"gezu_seo_doc",handle:"state-log"}, metaobject:{fields:[{key:"body",value:"x"}]}){ metaobject{id} userErrors{message} } }'))

    def test_other_metaobject_type_blocked(self):
        self.blocked(mut('mutation { metaobjectUpsert(handle:{type:"product_review",handle:"x"}, metaobject:{fields:[]}){ metaobject{id} } }'))

    def test_metaobject_definition_blocked(self):
        self.blocked(mut('mutation { metaobjectDefinitionDelete(id:"gid://shopify/MetaobjectDefinition/1"){ deletedId } }'))

    def test_delete_only_own_lock(self):
        gid = "gid://shopify/Metaobject/123"
        q = 'mutation { metaobjectDelete(id:"%s"){ deletedId } }' % gid
        self.blocked(mut(q))
        create = mut('mutation { metaobjectCreate(metaobject:{type:"gezu_seo_doc",handle:"lock-run-a",fields:[]}){ metaobject{id handle} } }')
        self.ok(create)
        create["tool_response"] = {"data": {"metaobjectCreate": {"metaobject": {"id": gid, "handle": "lock-run-a"}}}}
        self.ok(create, mode="post")
        self.ok(mut(q))
        self.blocked(mut('mutation { metaobjectDelete(id:"gid://shopify/Metaobject/999"){ deletedId } }'))

    # --- articles
    def test_article_draft_allowed_and_capped(self):
        q = 'mutation($a: ArticleCreateInput!){ articleCreate(article:$a){ article{ id handle publishedAt } userErrors{message} } }'
        v = {"a": {"blogId": "gid://shopify/Blog/106549412163", "title": "T", "isPublished": False}}
        self.ok(mut(q, v))
        self.ok(mut(q, v))
        self.blocked(mut(q, v))  # cap 2

    def test_article_publish_blocked(self):
        q = 'mutation($a: ArticleCreateInput!){ articleCreate(article:$a){ article{id} } }'
        self.blocked(mut(q, {"a": {"title": "T", "isPublished": True}}))
        self.blocked(mut(q, {"a": {"title": "T"}}))
        self.blocked(mut(q, {"a": {"title": "T", "isPublished": False, "publishDate": "2026-11-01T00:00:00Z"}}))

    def test_article_update_rules(self):
        q = 'mutation($id: ID!, $a: ArticleUpdateInput!){ articleUpdate(id:$id, article:$a){ article{ id handle } } }'
        self.ok(mut(q, {"id": "gid://shopify/Article/1", "a": {"body": "<p>x</p>"}}))
        self.blocked(mut(q, {"id": "gid://shopify/Article/1", "a": {"isPublished": True}}))
        self.blocked(mut(q, {"id": "gid://shopify/Article/1", "a": {"handle": "new-url"}}))

    # --- product / collection SEO
    def test_product_seo_only(self):
        q = 'mutation($p: ProductUpdateInput!){ productUpdate(product:$p){ product{id} userErrors{message} } }'
        self.ok(mut(q, {"p": {"id": "gid://shopify/Product/1", "seo": {"title": "a", "description": "b"}}}))
        self.blocked(mut(q, {"p": {"id": "gid://shopify/Product/1", "handle": "x"}}))
        self.blocked(mut(q, {"p": {"id": "gid://shopify/Product/1", "descriptionHtml": "x"}}))
        self.blocked(mut(q, {"p": {"id": "gid://shopify/Product/1", "status": "DRAFT"}}))
        self.blocked(mut('mutation { productUpdate(product:{id:"gid://shopify/Product/1", seo:{title:"x"}}){ product{id} } }'))

    def test_product_seo_cap(self):
        q = 'mutation($p: CollectionInput!){ collectionUpdate(input:$p){ collection{id} } }'
        v = {"p": {"id": "gid://shopify/Collection/1", "seo": {"title": "a"}}}
        for _ in range(10):
            self.ok(mut(q, v))
        self.blocked(mut(q, v))

    def test_prices_inventory_redirects_theme_blocked(self):
        for q in ['mutation { productVariantsBulkUpdate(productId:"gid://shopify/Product/1", variants:[{id:"x", price:"1"}]){ product{id} } }',
                  'mutation { inventorySetQuantities(input:{reason:"x", name:"available", quantities:[]}){ userErrors{message} } }',
                  'mutation { urlRedirectCreate(urlRedirect:{path:"/a", target:"/b"}){ urlRedirect{id} } }',
                  'mutation { themePublish(id:"gid://shopify/OnlineStoreTheme/1"){ theme{id} } }',
                  'mutation { themeFilesUpsert(themeId:"x", files:[]){ job{id} } }',
                  'mutation { discountCodeBasicCreate(basicCodeDiscount:{}){ userErrors{message} } }',
                  'mutation { webhookSubscriptionCreate(topic:ORDERS_CREATE, webhookSubscription:{}){ userErrors{message} } }',
                  '{ shop { name } }',
                  'mutation { a: metaobjectUpsert(handle:{type:"gezu_seo_doc",handle:"x"}, metaobject:{fields:[]}){ metaobject{id} } b: productDelete(input:{id:"x"}){ deletedProductId } }']:
            self.blocked(mut(q))

    def test_metafields(self):
        q = 'mutation($m: [MetafieldsSetInput!]!){ metafieldsSet(metafields:$m){ userErrors{message} } }'
        self.ok(mut(q, {"m": [{"ownerId": "gid://shopify/Article/1", "namespace": "global", "key": "title_tag", "value": "x", "type": "single_line_text_field"}]}))
        self.ok(mut(q, {"m": [{"ownerId": "gid://shopify/Product/1", "namespace": "global", "key": "description_tag", "value": "x", "type": "single_line_text_field"}]}))
        self.blocked(mut(q, {"m": [{"ownerId": "gid://shopify/Product/1", "namespace": "custom", "key": "specs", "value": "x", "type": "single_line_text_field"}]}))
        self.blocked(mut(q, {"m": [{"ownerId": "gid://shopify/Shop/1", "namespace": "global", "key": "title_tag", "value": "x", "type": "single_line_text_field"}]}))

    def test_translations(self):
        q = 'mutation($resourceId: ID!, $t: [TranslationInput!]!){ translationsRegister(resourceId:$resourceId, translations:$t){ userErrors{message} } }'
        self.ok(mut(q, {"resourceId": "gid://shopify/Article/1", "t": [{"locale": "nl", "key": "handle", "value": "x", "translatableContentDigest": "d"}]}))
        self.blocked(mut(q, {"resourceId": "gid://shopify/Product/1", "t": [{"locale": "nl", "key": "handle", "value": "x", "translatableContentDigest": "d"}]}))
        self.ok(mut(q, {"resourceId": "gid://shopify/Product/1", "t": [{"locale": "nl", "key": "meta_title", "value": "x", "translatableContentDigest": "d"}]}))

    def test_alt_text_only(self):
        q = 'mutation($f: [FileUpdateInput!]!){ fileUpdate(files:$f){ files{id} userErrors{message} } }'
        self.ok(mut(q, {"f": [{"id": "gid://shopify/MediaImage/1", "alt": "Galvanised post support"}]}))
        self.blocked(mut(q, {"f": [{"id": "gid://shopify/MediaImage/1", "originalSource": "https://x/y.jpg"}]}))

    def test_image_generation_cap(self):
        e = {"tool_name": "mcp__Higgsfield__generate_image", "tool_input": {}}
        for _ in range(6):
            self.ok(e)
        self.blocked(e)

    def test_garbage_fails_closed(self):
        self.blocked(mut("mutation { articleCreate(article:{ "))

    def test_session_marker(self):
        self.ok({}, mode="session")
        self.assertTrue(os.path.exists(os.path.join(self.state, "ACTIVE")))


if __name__ == "__main__":
    unittest.main()
