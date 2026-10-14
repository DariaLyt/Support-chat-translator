"""The completion call every model client implements."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class CompletionRequest:
    model: str
    messages: tuple[ChatMessage, ...]


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


class LanguageModel(Protocol):
    def complete(self, request: CompletionRequest) -> Completion:
        """Return the model text and the token counts for this call."""


class ModelError(Exception):
    """The model call did not return a translation."""


class ModelNotConfigured(ModelError):
    """No API key is available for the real client."""


class ModelResponseError(ModelError):
    """The provider request failed or the body was unusable."""
