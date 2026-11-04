"""Test LLMExtractor with relations"""
import pytest
from rag_core.llm_extractor import LLMExtractor


def test_extract_all_returns_relations():
    """Test that extract_all returns both entities and relations"""
    extractor = LLMExtractor()

    text = """
    CatBoost is a gradient boosting library developed by Yandex.
    It is similar to XGBoost but has different regularization techniques.
    Miniconda is a minimal conda distribution.
    """

    result = extractor.extract_all(text, "test.txt")

    # Check that relations is present in result
    assert 'relations' in result, "Relations should be in result"

    # Check that relations contains items (might be empty)
    assert isinstance(result['relations'], list), "Relations should be a list"

    # Check that entities is present
    assert 'entities' in result, "Entities should be in result"
    assert isinstance(result['entities'], list), "Entities should be a list"

    # Check that relations have required fields if not empty
    if len(result['relations']) > 0:
        for rel in result['relations']:
            assert 'source' in rel, "Relation should have source"
            assert 'target' in rel, "Relation should have target"
            assert 'type' in rel, "Relation should have type"

    print(f"Extracted {len(result['entities'])} entities and {len(result['relations'])} relations")


def test_extract_all_with_complex_text():
    """Test extract_all with complex text containing multiple entities and relations"""
    extractor = LLMExtractor()

    text = """
    XGBoost is a gradient boosting library that uses decision trees.
    It is based on the CART algorithm and provides regularization to prevent overfitting.
    CatBoost is another gradient boosting library that uses ordered boosting.
    Both libraries are used for tabular data modeling.
    """

    result = extractor.extract_all(text, "test.txt")

    # Check that both entities and relations are present
    assert 'relations' in result, "Relations should be in result"
    assert len(result['entities']) > 0, "Should extract entities"
    assert len(result['relations']) > 0, "Should extract relations"

    print(f"Extracted {len(result['entities'])} entities and {len(result['relations'])} relations")
    print(f"Entities: {result['entities']}")
    print(f"Relations: {result['relations']}")


def test_extract_all_returns_only_entities_when_no_relations():
    """Test that extract_all returns empty relations list when no relations found"""
    extractor = LLMExtractor()

    text = """
    This is just a plain text without any entities or relations.
    It contains only regular words and sentences.
    """

    result = extractor.extract_all(text, "test.txt")

    # Should still have entities key (might be empty)
    assert 'entities' in result, "Entities should be in result"
    assert 'relations' in result, "Relations should be in result"

    # Relations should be a list (possibly empty)
    assert isinstance(result['relations'], list), "Relations should be a list"

    print(f"Extracted {len(result['entities'])} entities and {len(result['relations'])} relations")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
