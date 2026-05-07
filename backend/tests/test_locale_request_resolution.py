"""Integration test: Flask request locale drives ``t()`` lookups.

Exercises the request-context branch of ``app.utils.locale`` end-to-end
by spinning up a minimal Flask app, registering a route that returns a
known translated key, and asserting the response varies with the
``Accept-Language`` header.
"""

import json
import os

import pytest
from flask import Flask, jsonify

from tests.conftest import load_module_directly

LOCALE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app",
    "utils",
    "locale.py",
)

locale_module = load_module_directly("mirofish_locale_for_request_test", LOCALE_PATH)
t = locale_module.t


@pytest.fixture
def client():
    app = Flask(__name__)

    @app.route("/echo")
    def echo():
        return jsonify({"error": t("api.error.simulation.m018")})

    return app.test_client()


def test_accept_language_en_returns_english(client):
    resp = client.get("/echo", headers={"Accept-Language": "en"})
    body = resp.get_json()
    # m018 is "Missing simulation_id" in en.json.
    assert "Missing simulation_id" in body["error"]


def test_accept_language_zh_returns_chinese(client):
    resp = client.get("/echo", headers={"Accept-Language": "zh"})
    body = resp.get_json()
    # zh.json preserves the original Chinese verbatim.
    assert any("一" <= ch <= "鿿" for ch in body["error"])


def test_missing_accept_language_defaults_to_zh(client):
    resp = client.get("/echo")
    body = resp.get_json()
    assert any("一" <= ch <= "鿿" for ch in body["error"])
