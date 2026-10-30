"""Worker-only provider configuration. Never serialize credentials or raw errors."""
import logging
import os
import re
from pathlib import Path

class ProviderConfigurationError(ValueError):
    pass

def selected_adapter(value=None):
    """OpenAI is the default; offline generation is an explicit local/test opt-in."""
    adapter = value if value is not None else os.getenv('EXTRACTION_ADAPTER', 'openai')
    if adapter not in ('openai', 'deterministic'):
        raise ProviderConfigurationError('Configure a supported AI adapter')
    if adapter == 'deterministic' and os.getenv('APP_ENV', 'development') not in ('development', 'test'):
        raise ProviderConfigurationError('Offline generation is restricted to development and tests')
    return adapter


def configured_model(value=None):
    model = value or os.getenv('OPENAI_MODEL', '')
    if not model or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,119}', model) or model.startswith('sk-'):
        raise ProviderConfigurationError('Configure an allowed model identifier')
    return model

def provider_key():
    path = os.getenv('OPENAI_API_KEY_FILE', '')
    if path:
        try:
            p = Path(path)
            if not p.is_absolute() or p.stat().st_size > 8192:
                raise ValueError()
            key = p.read_text().strip()
        except (OSError, ValueError, UnicodeError):
            raise ProviderConfigurationError('Server-side provider secret could not be loaded') from None
    else:
        key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key or len(key) > 8192 or any(ch.isspace() for ch in key):
        raise ProviderConfigurationError('Configure server-side provider credentials')
    return key

def create_client(factory):
    # The SDK and transports may log request bodies at DEBUG. Suppress those
    # loggers regardless of ambient OPENAI_LOG; application logs use safe codes.
    for name in ('openai', 'httpx', 'httpx2', 'httpcore', 'httpcore2'):
        logger = logging.getLogger(name)
        logger.disabled = True
        logger.propagate = False
    # Do not honor arbitrary OPENAI_BASE_URL routing of candidate data/secrets.
    return factory(api_key=provider_key(), base_url='https://api.openai.com/v1', timeout=40.0, max_retries=0)
