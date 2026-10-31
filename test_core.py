import pytest

def dummy_process(query: str):
    if not query or not query.strip():
        raise ValueError("Empty query")
    return {"status": "success", "result": f"Processed {query}"}

# Test 1: Standard happy path
def test_valid_input():
    res = dummy_process("Hello")
    assert res["status"] == "success"
    assert "Hello" in res["result"]

# Test 2: Edge case - empty string handling
def test_empty_input():
    with pytest.raises(ValueError):
        dummy_process("")

# Test 3: Edge case - whitespace handling
def test_whitespace_input():
    with pytest.raises(ValueError):
        dummy_process("   ")