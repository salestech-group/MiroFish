import json
import logging
import os
import threading
from flask import request, has_request_context

_thread_local = threading.local()

_locales_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'locales')

# Load language registry
with open(os.path.join(_locales_dir, 'languages.json'), 'r', encoding='utf-8') as f:
    _languages = json.load(f)

# Load translation files
_translations = {}
for filename in os.listdir(_locales_dir):
    if filename.endswith('.json') and filename != 'languages.json':
        locale_name = filename[:-5]
        with open(os.path.join(_locales_dir, filename), 'r', encoding='utf-8') as f:
            _translations[locale_name] = json.load(f)

# Per-process dedup cache for missing-translation warnings.
# Each (locale, key) pair triggers exactly one warning until reset.
_missing_key_cache: set = set()
_missing_key_lock = threading.Lock()
_locale_logger = logging.getLogger("mirofish.locale")


def _reset_missing_key_cache() -> None:
    """Clear the missing-key dedup cache.

    Intended for tests that need to re-assert the warning behavior between
    cases. Not part of the public runtime API.
    """
    with _missing_key_lock:
        _missing_key_cache.clear()


def _warn_missing_key_once(key: str, locale: str) -> None:
    """Emit a warning for a missing translation key, deduped per (locale, key)."""
    pair = (locale, key)
    with _missing_key_lock:
        if pair in _missing_key_cache:
            return
        _missing_key_cache.add(pair)
    _locale_logger.warning("missing translation key: %s (locale=%s)", key, locale)


def set_locale(locale: str):
    """Set locale for current thread. Call at the start of background threads."""
    _thread_local.locale = locale


def get_locale() -> str:
    if has_request_context():
        raw = request.headers.get('Accept-Language', 'zh')
        return raw if raw in _translations else 'zh'
    return getattr(_thread_local, 'locale', 'zh')


def _resolve(messages, key: str):
    """Walk the dotted ``key`` path through ``messages``; return the leaf or None."""
    value = messages
    for part in key.split('.'):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value if isinstance(value, str) else None


def t(key: str, **kwargs) -> str:
    locale = get_locale()
    messages = _translations.get(locale, _translations.get('zh', {}))

    value = _resolve(messages, key)

    if value is None and locale != 'zh':
        value = _resolve(_translations.get('zh', {}), key)

    if value is None:
        _warn_missing_key_once(key, locale)
        return key

    if kwargs:
        for k, v in kwargs.items():
            value = value.replace(f'{{{k}}}', str(v))

    return value


def get_language_instruction() -> str:
    locale = get_locale()
    lang_config = _languages.get(locale, _languages.get('zh', {}))
    return lang_config.get('llmInstruction', '请使用中文回答。')
