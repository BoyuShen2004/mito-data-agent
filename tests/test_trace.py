"""Tests for LangGraph trace mode."""

from mito_data_agent.runner import run_agent


def test_trace_returns_steps():
    prompt = (
        "Please update only the MitoVerse metadata row.\n"
        "Volume: trace_test\n"
        "Dataset: test\n"
        "Modality: FIB-SEM\n"
        "Organism: Human\n"
        "Organ: Test\n"
        "Tissue / region: Test\n"
        "Resolution: 8x8x40 nm\n"
        "Shape: 100x100x50\n"
        "# Mito: 5\n"
    )
    result = run_agent(prompt, trace=True, print_trace=False)

    assert result["trace"]
    assert len(result["trace"]) >= 3
    assert result["trace"][0]["node"] == "validate_input"
    assert result["trace_text"]
    assert "llm" in result["trace_text"]
