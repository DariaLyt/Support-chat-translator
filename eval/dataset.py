"""Hand-labeled support messages for the quality score."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LabeledMessage:
    id: str
    speaker: str
    text: str
    source_language: str
    target_language: str
    mixed: bool
    rude: bool
    reference: str
    protected: tuple[str, ...]
    facts: tuple[str, ...]


def load_messages(path: Path | None = None) -> list[LabeledMessage]:
    path = path or Path(__file__).with_name("messages.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        LabeledMessage(
            id=item["id"],
            speaker=item["speaker"],
            text=item["text"],
            source_language=item["source_language"],
            target_language=item["target_language"],
            mixed=item["mixed"],
            rude=item["rude"],
            reference=item["reference"],
            protected=tuple(item["protected"]),
            facts=tuple(item["facts"]),
        )
        for item in payload
    ]
