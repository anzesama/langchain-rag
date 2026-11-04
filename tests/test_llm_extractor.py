import pytest
from rag_core.llm_extractor import LLMExtractor


def test_llm_extractor_initialization():
    extractor = LLMExtractor()
    assert extractor.api_key is not None
    assert extractor.api_base is not None
    assert extractor.model == "agnes-2.0-flash"


def test_llm_extract_returns_structure():
    extractor = LLMExtractor()
    text = "交叉验证是一种评估机器学习模型性能的方法。"
    result = extractor._llm_extract(text)

    assert isinstance(result, dict)
    assert "entities" in result
    assert "relations" in result
    assert isinstance(result["entities"], list)
    assert isinstance(result["relations"], list)


def test_llm_extract_with_valid_text():
    extractor = LLMExtractor()
    text = """
    ResNet是一种深度残差学习网络。它通过跳跃连接解决了深度神经网络的退化问题。
    ResNet常用于图像分类任务。
    """
    result = extractor._llm_extract(text)

    # Should find ResNet entity
    entity_names = [e["name"] for e in result["entities"]]
    assert "ResNet" in entity_names

    # Should find relationship
    rel_names = [r["source"] + "-" + r["type"] + "-" + r["target"] for r in result["relations"]]
    assert any("ResNet" in r for r in rel_names)
