import re

from eval.dataset import load_messages


def test_labeled_set_covers_real_support_cases() -> None:
    messages = load_messages()

    assert len(messages) == 30
    assert len({message.id for message in messages}) == 30
    assert any(message.rude for message in messages)
    assert any(len(message.text) <= 6 for message in messages)
    assert any(message.mixed for message in messages)
    assert {message.source_language for message in messages} == {"fi", "en"}
    assert {message.target_language for message in messages} == {"fi", "en"}
    assert any(message.speaker == "courier" for message in messages)
    assert any(message.speaker == "customer" for message in messages)

    corpus = "\n".join(message.text for message in messages)
    assert re.search(r"#\d+", corpus)
    assert "Mannerheimintie 12" in corpus
    assert "🍕" in corpus or "👍" in corpus


def test_labels_agree_with_the_reference() -> None:
    for message in load_messages():
        assert message.source_language != message.target_language
        assert message.facts
        reference = message.reference.casefold()
        for fact in message.facts:
            assert fact.casefold() in reference
        for protected in message.protected:
            assert protected in message.text
            assert protected in message.reference
