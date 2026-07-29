import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_llm_refiner_init():
    from rag_core.llm_refiner import LLMRefiner
    r = LLMRefiner(endpoint='http://localhost:8080/v1', api_key='sk-test', model='gpt-3.5', domain='machine-learning')
    assert r.domain == 'machine-learning'
    assert r.endpoint == 'http://localhost:8080/v1'


def test_build_refine_prompt_ml_domain():
    from rag_core.llm_refiner import LLMRefiner
    r = LLMRefiner(endpoint='http://a', api_key='k', model='m', domain='machine-learning')
    entities = [{'name': '欠拟合', 'type': '方法'}, {'name': 'is', 'type': '未分类'}]
    chunks = [{'chunk_text': '欠拟合是ML中的常见问题。'}]
    prompt = r._build_refine_prompt(entities, chunks)
    # content assertions
    assert len(prompt) > 100
    assert 'JSON' in prompt


def test_build_refine_prompt_novel_domain():
    from rag_core.llm_refiner import LLMRefiner
    r = LLMRefiner(endpoint='http://a', api_key='k', model='m', domain='novel')
    entities = [{'name': '古月方源', 'type': '人物'}]
    chunks = [{'chunk_text': '古月方源手中握着春秋蝉。'}]
    prompt = r._build_refine_prompt(entities, chunks)
    assert '古月方源' in prompt
    assert '人物' in prompt


def test_build_relation_prompt():
    from rag_core.llm_refiner import LLMRefiner
    r = LLMRefiner(endpoint='http://a', api_key='a', model='m', domain='machine-learning')
    entities = [{'name': '梯度下降'}, {'name': '鞍点'}]
    chunks = [{'chunk_text': '梯度下降在鞍点附近收敛较慢。'}]
    prompt = r._build_relation_prompt(chunks, entities)
    assert '梯度下降' in prompt
    assert '鞍点' in prompt
    assert '关系' in prompt


def test_domain_configs():
    from rag_core.llm_refiner import DOMAIN_CONFIGS
    assert 'machine-learning' in DOMAIN_CONFIGS
    assert 'novel' in DOMAIN_CONFIGS
    assert 'ontology' in DOMAIN_CONFIGS
    ml = DOMAIN_CONFIGS['machine-learning']
    assert 'entity_types' in ml
    assert 'rel_types' in ml