"""Detect Finnish or English before the model call."""

from typing import Protocol

from lingua import Language, LanguageDetector, LanguageDetectorBuilder

SUPPORTED_LANGUAGES = ("fi", "en")
LANGUAGE_NAMES = {"fi": "Finnish", "en": "English"}

_LINGUA_LANGUAGES = {
    Language.FINNISH: "fi",
    Language.ENGLISH: "en",
}


class LanguageDetectorProtocol(Protocol):
    def detect(self, text: str) -> str | None:
        """Return fi or en, or None when the text has no clear language."""


class LinguaDetector:
    def __init__(self) -> None:
        self._detector: LanguageDetector | None = None

    def detect(self, text: str) -> str | None:
        if self._detector is None:
            self._detector = (
                LanguageDetectorBuilder.from_languages(Language.FINNISH, Language.ENGLISH)
                .build()
            )
        detected = self._detector.detect_language_of(text)
        if detected is None:
            return None
        return _LINGUA_LANGUAGES.get(detected)
