import json
from pathlib import Path

import pytest

from cbe_switch.storage import ConfigStore, ValidationError


def payload():
    return {"name":"Demo","key":"secret","url":"https://example.test/v1","config_template":"[provider]\nbase_url = '{{URL}}'\n","auth_template":"{\"token\": \"{{KEY}}\"}"}


def test_profile_render_and_persist(tmp_path: Path):
    store=ConfigStore(tmp_path/'app',tmp_path/'codex')
    profile=store.save_profile(payload())
    assert "https://example.test/v1" in store.render(profile['config_template'],profile['auth_template'],profile['key'],profile['url'])[0]
    assert json.loads(store.render(profile['config_template'],profile['auth_template'],profile['key'],profile['url'])[1])['token']=='secret'


def test_invalid_template_rejected(tmp_path):
    store=ConfigStore(tmp_path/'app',tmp_path/'codex')
    bad=payload();bad['auth_template']='not json'
    with pytest.raises(ValidationError): store.save_profile(bad)


def test_activate_backup_and_restore(tmp_path):
    codex=tmp_path/'codex';codex.mkdir();(codex/'config.toml').write_text('[old]\nvalue=1');(codex/'auth.json').write_text('{"old":true}')
    store=ConfigStore(tmp_path/'app',codex); profile=store.save_profile(payload()); result=store.activate(profile['id'])
    assert 'example.test' in (codex/'config.toml').read_text(); assert json.loads((codex/'auth.json').read_text())['token']=='secret'
    store.restore(result['backup_id']); assert '[old]' in (codex/'config.toml').read_text(); assert json.loads((codex/'auth.json').read_text())['old'] is True

