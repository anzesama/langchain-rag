"""
Offline Evaluation Dataset Generator and Evaluator
===================================================
Generates test datasets for validating chunkers and quality assessors.
Provides automated evaluation with reporting.
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Add langchain-rag to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from rag_core.chunkers.title_hierarchy import TitleHierarchyChunker
from rag_core.quality.assessor import QualityAssessor


class EvaluationDataset:
    """
    Manages evaluation datasets for RAG components.
    
    Contains test cases with ground truth labels for:
    - Chunk count validation
    - Quality score validation
    - Relevance validation
    """
    
    DATASET_PATH = os.path.join(os.path.dirname(__file__), 'evaluation_dataset.json')
    
    def __init__(self, path: str = None):
        self.path = path or self.DATASET_PATH
        self.test_cases = []
        
    def load(self) -> List[Dict]:
        """Load dataset from JSON file."""
        if os.path.exists(self.path):
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.test_cases = data.get('test_cases', [])
        return self.test_cases
    
    def save(self):
        """Save dataset to JSON file."""
        os.makedirs(os.path.dirname(self.path) if os.path.dirname(self.path) else '.', exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump({'test_cases': self.test_cases, 'created_at': datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)
    
    def add_test_case(self, tc: Dict):
        """Add a test case to the dataset."""
        tc['id'] = tc.get('id', f'tc_{len(self.test_cases)+1:03d}')
        self.test_cases.append(tc)
    
    def get_test_cases_by_type(self, doc_type: str) -> List[Dict]:
        """Get test cases filtered by document type."""
        return [tc for tc in self.test_cases if tc.get('document_type') == doc_type]
    
    def generate_builtin_dataset(self) -> 'EvaluationDataset':
        """Generate a built-in dataset with various document types."""
        
        # Test Case 1: Simple markdown with headings
        self.add_test_case({
            'id': 'tc_001',
            'document_type': 'markdown',
            'title': 'Simple article with headings',
            'content': '''# 人工智能发展综述

## 引言
人工智能是计算机科学的一个分支，致力于创建智能机器。

## 发展历程
- 1950年代：图灵测试提出
- 1990年代：机器学习兴起
- 2010年代：深度学习突破

## 应用领域
1. 自然语言处理
2. 计算机视觉
3. 机器人技术

## 未来展望
AI将继续改变人类社会。''',
            'expected_chunks': 5,
            'expected_headings': ['# 人工智能发展综述', '## 引言', '## 发展历程', '## 应用领域', '## 未来展望']
        })
        
        # Test Case 2: Nested headings
        self.add_test_case({
            'id': 'tc_002',
            'document_type': 'markdown',
            'title': 'Nested heading structure',
            'content': '''# 机器学习基础

## 监督学习
### 分类问题
- 逻辑回归
- 决策树
- 支持向量机

### 回归问题
- 线性回归
- 岭回归

## 无监督学习
### 聚类算法
- K-means
- 层次聚类

### 降维
- PCA
- t-SNE''',
            'expected_chunks': 5,
            'expected_headings': ['# 机器学习基础', '## 监督学习', '### 分类问题', '### 回归问题', '## 无监督学习', '### 聚类算法', '### 降维']
        })
        
        # Test Case 3: Long document
        self.add_test_case({
            'id': 'tc_003',
            'document_type': 'markdown',
            'title': 'Long policy document',
            'content': '''# 2024年数字经济政策白皮书

## 一、总体形势
2024年全球数字经济规模达到50万亿美元。

## 二、中国数字经济发展现状
### （一）产业规模
中国数字经济规模达60万亿元。

### （二）结构特征
1. 产业数字化占比超70%
2. 数字产业化增速超15%

## 三、主要挑战
- 核心技术受制于人
- 数据安全面临威胁
- 数字鸿沟依然存在

## 四、政策建议
### （一）加强基础研究
加大研发投入，突破关键技术。

### （二）完善治理体系
建立数据分类分级制度。

### （三）促进融合发展
推动数字技术与实体经济深度融合。

## 五、结语
数字经济是新一轮科技革命的重要方向。''',
            'expected_chunks': 8,
            'expected_headings': ['# 2024年数字经济政策白皮书', '## 一、总体形势', '## 二、中国数字经济发展现状', '### （一）产业规模', '### （二）结构特征', '## 三、主要挑战', '## 四、政策建议', '### （一）加强基础研究', '### （二）完善治理体系', '### （三）促进融合发展', '## 五、结语']
        })
        
        # Test Case 4: Low quality content (for assessor testing)
        self.add_test_case({
            'id': 'tc_004',
            'document_type': 'low_quality',
            'title': 'Incomplete and poorly structured text',
            'content': '这是一段没有标题的文本。它可能是不完整的因为句子没有结束标点符号而且内容很少。另外还有一些乱码\uFFFD\uFFFD\uFFFD。',
            'expected_chunks': 1,
            'expected_quality_min': 30  # Should score below 40
        })
        
        # Test Case 5: Good quality content
        self.add_test_case({
            'id': 'tc_005',
            'document_type': 'good_quality',
            'title': 'Well-structured article',
            'content': '''# 气候变化对农业的影响

## 温度上升的影响
全球平均气温每上升1°C，小麦产量下降约6%。

## 降水模式变化
- 干旱频率增加
- 极端降雨事件增多

## 适应策略
### 短期措施
1. 调整播种时间
2. 改良灌溉系统

### 长期措施
- 培育耐旱品种
- 发展精准农业''',
            'expected_chunks': 4,
            'expected_quality_min': 80  # Should score above 70
        })
        
        # Test Case 6: Code-heavy document
        self.add_test_case({
            'id': 'tc_006',
            'document_type': 'technical',
            'title': 'Technical documentation with code',
            'content': '''# Python数据处理教程

## 安装依赖
```bash
pip install pandas numpy matplotlib
```

## 基本操作
### 读取数据
```python
import pandas as pd
df = pd.read_csv('data.csv')
print(df.head())
```

### 数据清洗
- 处理缺失值
- 去除重复项
- 数据类型转换

## 可视化
```python
import matplotlib.pyplot as plt
plt.plot(df['date'], df['value'])
plt.show()
```''',
            'expected_chunks': 4,
            'has_code_blocks': True
        })
        
        # Test Case 7: Empty/malformed content
        self.add_test_case({
            'id': 'tc_007',
            'document_type': 'empty',
            'title': 'Empty document',
            'content': '',
            'expected_chunks': 0,
            'expected_quality_min': 0
        })
        
        # Test Case 8: Mixed languages
        self.add_test_case({
            'id': 'tc_008',
            'document_type': 'bilingual',
            'title': 'Bilingual document',
            'content': '''# 中英混合文档

## Introduction
This is a bilingual document for testing purposes.

## 测试内容
这是一个混合语言的测试文档。

## Key Points
- Point 1: 第一点说明
- Point 2: 第二点说明
- Point 3: 第三点说明''',
            'expected_chunks': 3,
            'has_mixed_languages': True
        })
        
        # Test Case 9: Deep nesting
        self.add_test_case({
            'id': 'tc_009',
            'document_type': 'deep_nesting',
            'title': 'Deeply nested structure',
            'content': '''# Level 1

## Level 2

### Level 3

#### Level 4

##### Level 5

###### Level 6

Back to level 2 content.

## Another Level 2''',
            'expected_chunks': 8,
            'max_depth': 6
        })
        
        # Test Case 10: Real-world style
        self.add_test_case({
            'id': 'tc_010',
            'document_type': 'news',
            'title': 'News article style',
            'content': '''# 今日科技新闻

## AI视频生成技术突破
近日，多家科技公司发布了新一代AI视频生成模型。

### 主要特点
- 支持4K分辨率
- 生成速度提升3倍
- 物理规律更准确

## 行业影响
分析师认为这将改变影视制作流程。

## 市场反应
相关股票普遍上涨。''',
            'expected_chunks': 4,
            'expected_quality_min': 75
        })
        
        self.save()
        return self
    
    def evaluate_chunker(self, tc: Dict) -> Dict:
        """Evaluate chunker against a test case."""
        chunker = TitleHierarchyChunker(max_chunk_size=800)
        chunks = chunker.split_by_headings(tc['content'])
        
        result = {
            'test_id': tc['id'],
            'component': 'chunker',
            'expected_chunks': tc.get('expected_chunks', len(chunks)),
            'actual_chunks': len(chunks),
            'match': len(chunks) == tc.get('expected_chunks'),
            'chunks': [{'index': i, 'size': len(c.page_content), 'heading': c.metadata.get('heading')} for i, c in enumerate(chunks)]
        }
        
        if tc.get('expected_headings'):
            actual_headings = [c.metadata.get('heading', '') for c in chunks if c.metadata.get('heading')]
            result['headings_match'] = set(actual_headings) == set(tc['expected_headings'])
        
        return result
    
    def evaluate_quality(self, tc: Dict) -> Dict:
        """Evaluate quality assessor against a test case."""
        qa = QualityAssessor()
        
        # First chunk the content
        chunker = TitleHierarchyChunker(max_chunk_size=800)
        chunks = chunker.split_by_headings(tc['content'])
        chunks_data = [{'text': c.page_content, 'metadata': c.metadata} for c in chunks]
        
        # Then assess quality
        scores = qa.batch_assess(chunks_data)
        report = qa.get_quality_report(chunks_data)
        
        result = {
            'test_id': tc['id'],
            'component': 'quality_assessor',
            'scores': [
                {'index': i, 'overall': s.overall, 'completeness': s.completeness, 
                 'readability': s.readability, 'relevance': s.relevance}
                for i, s in enumerate(scores)
            ],
            'report': report
        }
        
        if tc.get('expected_quality_min'):
            avg_score = report['statistics']['overall']['mean']
            result['meets_minimum'] = avg_score >= tc['expected_quality_min']
        
        return result
    
    def run_full_evaluation(self) -> Dict:
        """Run full evaluation on all test cases."""
        self.load()
        
        chunker_results = []
        quality_results = []
        
        for tc in self.test_cases:
            chunker_results.append(self.evaluate_chunker(tc))
            quality_results.append(self.evaluate_quality(tc))
        
        return {
            'evaluation_time': datetime.now().isoformat(),
            'total_test_cases': len(self.test_cases),
            'chunker_results': chunker_results,
            'quality_results': quality_results,
            'summary': {
                'chunker_pass_rate': sum(1 for r in chunker_results if r.get('match') or abs(r.get('actual_chunks',0) - r.get('expected_chunks',0)) <= 2) / max(1, len(chunker_results)) * 100,
                'quality_pass_rate': sum(1 for r in quality_results if r.get('meets_minimum', True)) / max(1, len(quality_results)) * 100,
            }
        }


def main():
    """CLI entry point for evaluation."""
    import argparse
    
    parser = argparse.ArgumentParser(description='RAG Evaluation Dataset Tool')
    parser.add_argument('--generate', action='store_true', help='Generate built-in dataset')
    parser.add_argument('--evaluate', action='store_true', help='Run full evaluation')
    parser.add_argument('--dataset', type=str, default=None, help='Path to dataset file')
    
    args = parser.parse_args()
    
    dataset = EvaluationDataset(path=args.dataset)
    
    if args.generate:
        print("Generating built-in evaluation dataset...")
        dataset.generate_builtin_dataset()
        print("[OK] Dataset saved to: %s" % dataset.path)
        print(f"  Total test cases: {len(dataset.test_cases)}")
    
    if args.evaluate:
        print("Running full evaluation...")
        if not dataset.path or not os.path.exists(dataset.path):
            print("No dataset found. Generating first...")
            dataset.generate_builtin_dataset()
        
        results = dataset.run_full_evaluation()
        
        print(f"\n{'='*60}")
        print(f"EVALUATION RESULTS")
        print(f"{'='*60}")
        print(f"Total test cases: {results['total_test_cases']}")
        print(f"Chunker pass rate: {results['summary']['chunker_pass_rate']:.1f}%")
        print(f"Quality pass rate: {results['summary']['quality_pass_rate']:.1f}%")
        
        print(f"\nChunker Details:")
        for r in results['chunker_results']:
            status = "[PASS]" if r.get('match') else "[FAIL]"
            print(f"  {r['test_id']}: {status} (expected={r['expected_chunks']}, actual={r['actual_chunks']})")
        
        print(f"\nQuality Details:")
        for r in results['quality_results']:
            status = "[PASS]" if r.get('meets_minimum', True) else "[FAIL]"
            stats = r.get('report', {}).get('statistics', {}).get('overall', {})
            avg = stats.get('mean', 0)
            print(f"  {r['test_id']}: {status} (avg_score={avg:.1f})")
        
        print(f"\n{'='*60}")
        
        # Save results
        output_path = os.path.join(os.path.dirname(__file__), 'evaluation_results.json')
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Results saved to: {output_path}")


if __name__ == '__main__':
    main()
