from __future__ import annotations

from .locales.en import STRINGS as EN_STRINGS
from .locales.zh_cn import STRINGS as ZH_CN_STRINGS


LOCALES = {
    "en": EN_STRINGS,
    "zh_cn": ZH_CN_STRINGS,
}

LANGUAGE_LABELS = {
    "en": "English",
    "zh_cn": "简体中文",
}

DEFAULT_LANGUAGE = "zh_cn"


class Localizer:
    def __init__(self, language: str = DEFAULT_LANGUAGE) -> None:
        self.language = DEFAULT_LANGUAGE
        self.set_language(language)

    def set_language(self, language: str) -> None:
        normalized = (language or "").strip().lower()
        self.language = normalized if normalized in LOCALES else DEFAULT_LANGUAGE

    def t(self, key: str, **kwargs: object) -> str:
        text = LOCALES.get(self.language, {}).get(key)
        if text is None:
            text = EN_STRINGS.get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text

    def language_options(self) -> list[str]:
        return [LANGUAGE_LABELS[code] for code in LANGUAGE_LABELS]

    def language_label(self, code: str) -> str:
        return LANGUAGE_LABELS.get(code, LANGUAGE_LABELS[DEFAULT_LANGUAGE])

    def language_code_from_label(self, label: str) -> str:
        cleaned = (label or "").strip()
        for code, display_label in LANGUAGE_LABELS.items():
            if cleaned == display_label:
                return code
        return DEFAULT_LANGUAGE
