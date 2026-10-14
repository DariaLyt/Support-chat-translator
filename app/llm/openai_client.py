"""Chat client for any API that speaks the OpenAI chat completions schema."""

import httpx2

from app.llm.base import (
    Completion,
    CompletionRequest,
    ModelNotConfigured,
    ModelResponseError,
)

_TEMPERATURE = 0


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        http: httpx2.Client | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._http = http or httpx2.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    def complete(self, request: CompletionRequest) -> Completion:
        if not self._api_key:
            raise ModelNotConfigured("LLM API key is not configured")

        try:
            response = self._http.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": request.model,
                    "temperature": _TEMPERATURE,
                    "messages": [
                        {"role": message.role, "content": message.content}
                        for message in request.messages
                    ],
                },
            )
        except httpx2.HTTPError as exc:
            raise ModelResponseError("Model request failed") from exc

        if response.status_code >= 400:
            raise ModelResponseError(
                f"Model request failed with status {response.status_code}"
            )

        return _parse_completion(response.json(), request.model)


def _parse_completion(payload: object, model: str) -> Completion:
    if not isinstance(payload, dict):
        raise ModelResponseError("Model response was not a JSON object")

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ModelResponseError("Model response did not include a completion")

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    text = _message_text(content)
    if text is None:
        raise ModelResponseError("Model response did not include translation text")

    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise ModelResponseError("Model response did not include token counts")

    input_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("completion_tokens")
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        raise ModelResponseError("Model response did not include token counts")

    returned_model = payload.get("model")
    return Completion(
        text=text,
        model=returned_model if isinstance(returned_model, str) else model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _message_text(content: object) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "".join(parts)
    return None
