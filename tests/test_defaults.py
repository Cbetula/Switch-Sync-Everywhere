from pathlib import Path


def test_default_template_contains_codex_provider_settings():
    source = (Path(__file__).parents[1] / "cbe_switch/static/app.js").read_text(encoding="utf-8")
    assert 'model = "gpt-6-astra"' in source
    assert 'base_url = "{{URL}}"' in source
    assert 'experimental_bearer_token = "{{KEY}}"' in source
    assert 'requires_openai_auth = false' in source
    assert 'http_headers = { "x-openai-actor-authorization" = "local-image-extension" }' in source
    assert '\"api_key\":\"{{KEY}}\"' in source
