"""i18n/__init__.py — интернационализация."""

import json
import os
from pathlib import Path

_LANGS = {"en", "ru", "es", "fr", "de", "pl", "ro", "bg", "tr", "hi", "zh"}
_DEFAULT = "en"
_translations: dict = {}
_current_lang: str = _DEFAULT

_DIR = Path(__file__).parent


def _load(lang: str) -> dict:
    path = _DIR / f"{lang}.json"
    if not path.exists():
        fallback = _DIR / f"{_DEFAULT}.json"
        if fallback.exists():
            with open(fallback, encoding="utf-8") as f:
                return json.load(f)
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def set_lang(lang: str) -> None:
    global _current_lang, _translations
    if lang not in _LANGS:
        raise ValueError(f"unsupported language: {lang}. Available: {_LANGS}")
    _current_lang = lang
    _translations = _load(lang)


def get_lang() -> str:
    return _current_lang


def t(key: str, **kwargs) -> str:
    """Возвращает переведённую строку с подстановкой параметров."""
    text = _translations.get(key, key)  # fallback — сам ключ
    return text.format(**kwargs) if kwargs else text


# Загружаем язык из .env при импорте
_lang_from_env = os.getenv("LANG", _DEFAULT).lower()[:2]
set_lang(_lang_from_env if _lang_from_env in _LANGS else _DEFAULT)
