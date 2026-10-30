"""Configuration tests never send a live provider request."""
from pathlib import Path
import pytest
from app import provider_config, ai_gateway, career_gateway


def test_openai_is_default_and_missing_key_fails_closed(monkeypatch):
    for name in ('EXTRACTION_ADAPTER','OPENAI_API_KEY','OPENAI_API_KEY_FILE'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('OPENAI_MODEL','synthetic-model')
    assert provider_config.selected_adapter() == 'openai'
    assert career_gateway.adapter() == 'openai'
    with pytest.raises(ai_gateway.GatewayError) as exc:
        ai_gateway.extract_facts('Used Python to prepare reports.')
    assert exc.value.code == 'configuration'
    with pytest.raises(ai_gateway.GatewayError) as exc:
        career_gateway.extract_requirements('Python required')
    assert exc.value.code == 'configuration'


@pytest.mark.parametrize('app_env',['production','staging'])
def test_offline_mode_forbidden_outside_local_test(monkeypatch,app_env):
    monkeypatch.setenv('APP_ENV',app_env)
    monkeypatch.setenv('EXTRACTION_ADAPTER','deterministic')
    with pytest.raises(provider_config.ProviderConfigurationError):provider_config.selected_adapter()
    with pytest.raises(ai_gateway.GatewayError):ai_gateway.extract_facts('Used Python')
    with pytest.raises(ai_gateway.GatewayError):career_gateway.extract_requirements('Python required')


def test_offline_mode_requires_explicit_selection(monkeypatch):
    monkeypatch.setenv('APP_ENV','test')
    monkeypatch.delenv('EXTRACTION_ADAPTER',raising=False)
    assert provider_config.selected_adapter() == 'openai'
    monkeypatch.setenv('EXTRACTION_ADAPTER','deterministic')
    assert provider_config.selected_adapter() == 'deterministic'


def test_secret_file_precedence_fails_closed_without_env_fallback(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY_FILE','/tmp/does-not-exist-career-test-secret')
    monkeypatch.setenv('OPENAI_API_KEY','sk-synthetic-test-only')
    with pytest.raises(provider_config.ProviderConfigurationError) as exc:provider_config.provider_key()
    assert 'sk-synthetic' not in str(exc.value)


def test_compose_only_worker_mounts_provider_secret():
    text=(Path(__file__).parents[2]/'compose.yaml').read_text()
    worker=text.split('  worker:\n',1)[1].split('  web:\n',1)[0]
    assert 'OPENAI_API_KEY_FILE: /run/secrets/openai_api_key' in worker
    assert 'secrets: [openai_api_key]' in worker
    assert 'OPENAI_API_KEY:' not in text
    assert 'OPENAI_API_KEY_FILE' not in text.split('  worker:\n',1)[0]
    assert 'NEXT_PUBLIC_OPENAI' not in text
    assert 'EXTRACTION_ADAPTER: ${EXTRACTION_ADAPTER:-openai}' in text
