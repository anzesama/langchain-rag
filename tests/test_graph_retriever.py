"""Test graph retrieval with real data"""
import pytest
from rag_core.graph_retriever import retrieve, to_prompt_context
from rag_core.wiki_db_libsql import WikiDB


def test_graph_retrieval_with_real_data():
    """Test graph retrieval with imported AAAMLP-CN data"""
    wiki_db = WikiDB()

    # Get some entities and relations
    entities = wiki_db.get_all_entities()
    relations = wiki_db.get_all_relationships()

    print(f"\nDatabase has {len(entities)} entities and {len(relations)} relations")

    assert len(entities) > 0, "Database should have entities"
    assert len(relations) > 0, "Database should have relationships"

    # Test retrieval
    result = retrieve('CatBoost XGBoost comparison', top_k=5, hops=2)

    print(f"\nRetrieval results:")
    print(f"  Seed relations: {len(result['seed_relations'])}")
    print(f"  Expanded nodes: {len(result['expanded_nodes'])}")
    print(f"  Expanded edges: {len(result['expanded_edges'])}")
    print(f"  Fact list: {len(result['fact_list'])}")

    # Check that we got some results
    assert len(result['fact_list']) > 0, "Should retrieve some facts"

    # Check that facts have correct format
    for fact in result['fact_list']:
        assert '--' in fact, "Fact should contain relationship marker"

    print(f"\nTop facts:")
    for i, fact in enumerate(result['fact_list'][:5]):
        print(f"  {i+1}. {fact}")


def test_graph_retrieval_specific_queries():
    """Test graph retrieval with specific queries"""
    test_queries = [
        'CatBoost XGBoost',
        '逻辑回归',
        '特征工程',
        '超参数优化'
    ]

    for query in test_queries:
        print(f"\nTesting query: {query}")
        result = retrieve(query, top_k=3, hops=1)

        print(f"  Seed relations: {len(result['seed_relations'])}")
        print(f"  Fact list: {len(result['fact_list'])}")

        assert len(result['fact_list']) > 0, f"Should retrieve facts for {query}"


def test_prompt_context_generation():
    """Test that prompt context is generated correctly"""
    # Use a query that should return results
    result = retrieve('逻辑回归', top_k=3, hops=1)

    context = to_prompt_context(result)

    print(f"\nPrompt context length: {len(context)} characters")
    print(f"Prompt context:\n{context}")

    assert len(context) > 0, "Context should not be empty"
    assert '【已知知识图谱事实】' in context, "Context should have header"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
