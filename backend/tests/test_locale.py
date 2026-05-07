"""Unit tests for ``app.utils.locale``.

Covers the missing-key warning behavior introduced for ticket #6:

- Resolving a known key returns the translated value.
- Active locale falls back to ``zh`` when a key is only defined there.
- A missing key returns the raw key string and never raises.
- Each missing ``(locale, key)`` pair emits exactly one warning across the
  process lifetime (deduplicated).
- The private ``_reset_missing_key_cache`` hook clears the dedup memoization
  so successive tests can re-assert the warning behavior.
"""

import logging
import os

import pytest

from tests.conftest import load_module_directly

LOCALE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app",
    "utils",
    "locale.py",
)

locale_module = load_module_directly("mirofish_locale_under_test", LOCALE_PATH)
_reset_missing_key_cache = locale_module._reset_missing_key_cache
set_locale = locale_module.set_locale
t = locale_module.t


@pytest.fixture(autouse=True)
def _clear_dedup_cache():
    """Reset the missing-key dedup cache around every test."""
    _reset_missing_key_cache()
    yield
    _reset_missing_key_cache()


def test_known_key_returns_active_locale_value():
    set_locale("en")
    # ``api.projectNotFound`` is a long-standing key in both en.json and zh.json.
    assert t("api.projectNotFound", id="abc") != ""
    assert t("api.projectNotFound", id="abc") != "api.projectNotFound"


def test_zh_fallback_when_active_locale_lacks_key():
    set_locale("en")
    # Inject a zh-only key for this test, then assert lookup falls back to it.
    locale_module._translations.setdefault("zh", {})["__test_zh_only_key__"] = "中文回退"
    try:
        assert t("__test_zh_only_key__") == "中文回退"
    finally:
        locale_module._translations["zh"].pop("__test_zh_only_key__", None)


def test_missing_key_returns_raw_key_string():
    set_locale("en")
    assert t("definitely.not.a.real.key.path") == "definitely.not.a.real.key.path"


def test_missing_key_never_raises_for_invalid_path_segments():
    set_locale("en")
    # ``api.projectNotFound`` resolves to a string; descending into it would
    # otherwise crash. The helper must guard against that.
    assert t("api.projectNotFound.deeper") == "api.projectNotFound.deeper"


def test_missing_key_emits_exactly_one_warning_per_pair(caplog):
    set_locale("en")
    target_logger_name = "mirofish.locale"
    with caplog.at_level(logging.WARNING, logger=target_logger_name):
        t("definitely.not.a.real.key.path")
        t("definitely.not.a.real.key.path")
        t("definitely.not.a.real.key.path")
    warnings = [r for r in caplog.records if r.name == target_logger_name and r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "definitely.not.a.real.key.path" in warnings[0].getMessage()
    assert "en" in warnings[0].getMessage()


def test_reset_hook_allows_warning_to_fire_again(caplog):
    set_locale("en")
    target_logger_name = "mirofish.locale"
    with caplog.at_level(logging.WARNING, logger=target_logger_name):
        t("another.missing.key")
        _reset_missing_key_cache()
        t("another.missing.key")
    warnings = [r for r in caplog.records if r.name == target_logger_name and r.levelno == logging.WARNING]
    assert len(warnings) == 2


def test_distinct_missing_keys_each_warn_once(caplog):
    set_locale("en")
    target_logger_name = "mirofish.locale"
    with caplog.at_level(logging.WARNING, logger=target_logger_name):
        t("missing.key.one")
        t("missing.key.two")
        t("missing.key.one")
        t("missing.key.two")
    warnings = [r for r in caplog.records if r.name == target_logger_name and r.levelno == logging.WARNING]
    assert len(warnings) == 2
