"""In-memory model client for tests. It records the request and returns fixed text."""

from app.llm.base import Completion, CompletionRequest


class FakeLanguageModel:
    def __init__(
        self,
        translation: str = "translated",
        input_tokens: int = 10,
        output_tokens: int = 5,
    ) -> None:
        self.translation = translation
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> Completion:
        self.requests.append(request)
        return Completion(
            text=self.translation,
            model=request.model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )
