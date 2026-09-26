from translaterany.subtitles.chunking import (
    ContextLine,
    DialogueBatch,
    DialogueLine,
    create_dialogue_batches,
    estimate_tokens,
    format_batch_prompt,
)


def test_chunking_creates_batches_with_sliding_context():
    lines = [DialogueLine(id=str(i), text=f"Line number {i} with some english content.") for i in range(1, 61)]
    # Com teto baixo de tokens, deve gerar múltiplos blocos
    batches = create_dialogue_batches(lines, max_tokens_per_batch=150, max_context_lines=5)
    assert len(batches) > 1
    assert isinstance(batches[0], DialogueBatch)

    # O primeiro lote não tem contexto anterior
    assert len(batches[0].context) == 0
    assert len(batches[0].lines) > 0

    # O segundo lote deve conter contexto das falas anteriores
    assert len(batches[1].context) > 0
    assert batches[1].context[-1].text == batches[0].lines[-1].text


def test_prompt_formatting():
    batch_lines = [DialogueLine(id="1", text="Hello"), DialogueLine(id="2", text="World")]
    context = [ContextLine(text="Previous statement")]
    prompt = format_batch_prompt(batch_lines, context)
    assert "[CONTEXTO RECENTE" in prompt
    assert "Previous statement" in prompt
    assert "[FALAS A TRADUZIR" in prompt
    assert "[1] Hello" in prompt
    assert "[2] World" in prompt


def test_prompt_formatting_without_context():
    batch_lines = [DialogueLine(id="1", text="Hello"), DialogueLine(id="2", text="World")]
    prompt = format_batch_prompt(batch_lines, [])
    assert "[CONTEXTO RECENTE" not in prompt
    assert "[FALAS A TRADUZIR]:\n[1] Hello\n[2] World" in prompt


def test_estimate_tokens():
    assert estimate_tokens("") == 1
    assert estimate_tokens("Hi") == 1
    assert estimate_tokens("12345678") == 2
    assert estimate_tokens("A" * 40) == 10


def test_chunking_empty_lines():
    batches = create_dialogue_batches([])
    assert batches == []


def test_chunking_context_window_limit():
    lines = [DialogueLine(id=str(i), text=f"Short {i}") for i in range(1, 30)]
    batches = create_dialogue_batches(lines, max_tokens_per_batch=20, max_context_lines=3)
    assert len(batches) > 3
    for batch in batches:
        assert len(batch.context) <= 3


def test_chunking_zero_max_context_lines():
    lines = [DialogueLine(id=str(i), text=f"Line {i}") for i in range(1, 10)]
    batches = create_dialogue_batches(lines, max_tokens_per_batch=10, max_context_lines=0)
    for batch in batches:
        assert len(batch.context) == 0

