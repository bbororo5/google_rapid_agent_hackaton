from app.agents.adk_agents import _text_stream_chunks


def test_text_stream_chunks_prefers_readable_boundaries() -> None:
    text = "First sentence. Second sentence with more detail. Third sentence closes the answer."

    chunks = _text_stream_chunks(text, 32)

    assert len(chunks) > 1
    assert "".join(chunks) == text
    assert chunks[0].endswith(" ")
    assert "First sentence." in chunks[0]
