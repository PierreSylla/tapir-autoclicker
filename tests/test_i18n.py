import ast
from pathlib import Path
from string import Formatter

import pytest

from tapir import i18n

SOURCES = Path(__file__).parent.parent / "tapir"


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name is not None}


def _tr_literals() -> set[str]:
    return {
        node.args[0].value
        for path in SOURCES.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr"
        and node.args and isinstance(node.args[0], ast.Constant)
    }


def test_every_text_has_a_french_translation():
    texts = _tr_literals()
    assert len(texts) > 30  # the scan really finds the calls
    assert sorted(texts - i18n.FR.keys()) == []


def test_translations_keep_the_placeholders():
    for english, french in i18n.FR.items():
        assert _fields(french) == _fields(english), english


@pytest.mark.parametrize(("env", "expected"), [
    ({"LANG": "fr_FR.UTF-8"}, "fr"),
    ({"LANG": "fr_FR.UTF-8", "LC_MESSAGES": "en_US.UTF-8"}, "en"),
    ({"LANG": "en_US.UTF-8", "LANGUAGE": "fr:en"}, "fr"),
    ({"LANG": "de_DE.UTF-8"}, "en"),
    ({}, "en"),
])
def test_system_language(monkeypatch, env, expected):
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)
    for var, value in env.items():
        monkeypatch.setenv(var, value)
    assert i18n.system_language() == expected


def test_unknown_language_follows_the_system(monkeypatch):
    monkeypatch.setattr(i18n, "_language", "en")
    monkeypatch.setattr(i18n, "system_language", lambda: "fr")
    i18n.set_language("de")
    assert i18n.language() == "fr"
    i18n.set_language("en")
    assert i18n.language() == "en"


def test_english(monkeypatch):
    monkeypatch.setattr(i18n, "_language", "en")
    assert i18n.tr("Starting in {n} s", n=3) == "Starting in 3 s"
    assert i18n.number(1234567) == "1,234,567"
    assert i18n.translate_label("Alt+Mouse 5") == "Alt+Mouse 5"


def test_french(monkeypatch):
    monkeypatch.setattr(i18n, "_language", "fr")
    assert i18n.tr("Starting in {n} s", n=3) == "Démarrage dans 3 s"
    assert i18n.tr("Not in the table") == "Not in the table"
    assert i18n.number(1234567) == "1 234 567"
    assert i18n.translate_label("Alt+Mouse 5") == "Alt+Souris 5"
    assert i18n.translate_label("Super+F8") == "Super+F8"
