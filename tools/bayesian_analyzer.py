# -*- coding: utf-8 -*-
"""
贝叶斯知识库分析工具

基于朴素贝叶斯定理，对知识库内容进行主题分类、置信度评估和文档排序。

用法：
    python bayesian_analyzer.py "AI视频生成"
    python bayesian_analyzer.py "机器学习" --top-k 10
    python bayesian_analyzer.py --analyze-categories
"""
import os
import sys
import json
import math
import argparse
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

# ==================== 配置 ====================
BASE_DIR = Path(__file__).parent.resolve()
STORAGE_DIR = BASE_DIR / "storage"
KNOWLEDGE_BASE_NAME = "knowledge_base"

# 预定义的主题类别（可扩展）
CATEGORIES = {
    "AI视频生成": ["视频生成", "AI视频", "视频编辑", "剪辑", "thumbnail", "subtitle", "字幕"],
    "机器学习": ["机器学习", "ML", "classification", "分类", "regression", "回归", "训练", "模型", "神经网络", "深度学习", "BERT", "ALBERT", "TF-IDF", "SVC", "LR", "NB"],
    "政策分析": ["政策", "government", "govcn", "产业", "低空经济", "以旧换新"],
    "趋势情报": ["趋势", "trend", "日报", "Hotstar", "小红书", "B站"],
    "企业信息": ["SpaceX", "马斯克", "Tesla", "小米", "财报", "生态"],
    "员工信息": ["员工", "employee", "人事", "组织架构"],
    "工具推荐": ["工具", "tool", "推荐", "software", "开源", "open source"],
    "能源电力": ["电力", "electricity", "水电", "能源", "power"],
}

# ==================== 贝叶斯核心类 ====================

class BayesianClassifier:
    """
    朴素贝叶斯分类器（基于词频统计）
    
    P(Category|Document) ∝ P(Document|Category) × P(Category)
    """
    
    def __init__(self):
        self.category_docs = defaultdict(list)  # 类别 -> 文档列表
        self.category_counts = Counter()         # 类别 -> 文档数量
        self.word_freq = defaultdict(lambda: Counter())  # 类别 -> {词: 频次}
        self.total_words = Counter()             # 全局词频
        self.vocab = set()                       # 词汇表
        self.prior_probs = {}                    # 先验概率 P(Category)
        self.likelihoods = {}                    # 条件概率 P(Word|Category)
        self.is_trained = False
    
    def train(self, documents):
        """
        训练分类器
        
        Args:
            documents: list of (text, category) tuples
        """
        print("[INFO] 开始训练贝叶斯分类器...")
        
        for doc_text, category in documents:
            words = self._tokenize(doc_text)
            self.category_docs[category].append(doc_text)
            self.category_counts[category] += 1
            self.word_freq[category].update(words)
            self.total_words.update(words)
            self.vocab.update(words)
        
        total_docs = sum(self.category_counts.values())
        
        # 计算先验概率 P(Category)
        for cat in self.category_counts:
            self.prior_probs[cat] = self.category_counts[cat] / total_docs
        
        # 计算条件概率 P(Word|Category)，使用 Laplace 平滑
        vocab_size = len(self.vocab)
        for cat in self.word_freq:
            cat_total = sum(self.word_freq[cat].values())
            self.likelihoods[cat] = {}
            for word in self.vocab:
                count = self.word_freq[cat].get(word, 0)
                # Laplace 平滑：(count + 1) / (total + vocab_size)
                self.likelihoods[cat][word] = math.log((count + 1) / (cat_total + vocab_size))
        
        self.is_trained = True
        print("[OK] 训练完成，共 {} 个类别，{} 个文档，{} 个词汇".format(
            len(self.category_counts), total_docs, vocab_size
        ))
    
    def _tokenize(self, text):
        """简单分词：提取中英文单词"""
        import re
        # 提取中文和英文单词
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        english_words = re.findall(r'[a-zA-Z]+', text)
        return chinese_chars + english_words
    
    def predict(self, text, top_k=5):
        """
        预测文档所属类别及置信度
        
        Args:
            text: 输入文本
            top_k: 返回前 K 个类别
        
        Returns:
            list of (category, log_probability) tuples
        """
        if not self.is_trained:
            raise RuntimeError("请先调用 train() 训练分类器")
        
        words = self._tokenize(text)
        results = []
        
        for cat in self.category_counts:
            # P(Category|Document) ∝ P(Document|Category) × P(Category)
            log_prob = math.log(self.prior_probs[cat])
            
            for word in words:
                if word in self.likelihoods.get(cat, {}):
                    log_prob += self.likelihoods[cat][word]
            
            results.append((cat, log_prob))
        
        # 转换为概率分布（softmax）
        max_log_prob = max(log_prob for _, log_prob in results)
        exp_probs = [(cat, math.exp(log_prob - max_log_prob)) for cat, log_prob in results]
        total = sum(prob for _, prob in exp_probs)
        probs = [(cat, prob / total) for cat, prob in exp_probs]
        
        # 按概率降序排列
        probs.sort(key=lambda x: x[1], reverse=True)
        
        return probs[:top_k]
    
    def get_category_stats(self):
        """获取各分类的统计信息"""
        stats = {}
        for cat in self.category_counts:
            stats[cat] = {
                "document_count": self.category_counts[cat],
                "prior_probability": round(self.prior_probs.get(cat, 0), 4),
                "unique_words": len(self.word_freq[cat]),
            }
        return stats


class BayesianKnowledgeAnalyzer:
    """
    贝叶斯知识库分析器
    
    功能：
    1. 从 ChromaDB 加载所有文档块
    2. 基于关键词构建先验类别
    3. 对每个文档块进行贝叶斯分类
    4. 输出分类结果和置信度
    """
    
    def __init__(self):
        self.classifier = BayesianClassifier()
        self.documents = []
        self.results = []
    
    def load_documents_from_chroma(self):
        """
        从 ChromaDB 加载所有文档块
        
        Returns:
            list of (text, metadata) tuples
        """
        from rag_core.knowledge_base import KnowledgeBase
        
        print("[INFO] 从 ChromaDB 加载文档...")
        
        kb = KnowledgeBase(auto_import=False)
        docs = kb.vector_store.list_documents()
        
        # 获取文档内容（分批获取避免内存问题）
        all_docs = kb.vector_store.vectorstore._collection.get(
            include=["documents", "metadatas"],
            limit=len(docs)
        )
        documents = all_docs.get("documents", [])
        metadatas = all_docs.get("metadatas", [])
        
        print("[OK] 加载了 {} 个文档块".format(len(documents)))
        
        return [(doc, meta or {}) for doc, meta in zip(documents, metadatas)]
    
    def assign_initial_categories(self, documents):
        """
        基于关键词为文档分配初始类别
        
        Args:
            documents: list of (text, metadata) tuples
        
        Returns:
            list of (text, category) tuples
        """
        categorized = []
        
        for text, meta in documents:
            # 合并文本和元数据
            full_text = text + " " + str(meta.get("source", "")) + " " + str(meta.get("title", ""))
            
            # 匹配类别
            best_cat = "其他"
            best_score = 0
            
            for cat, keywords in CATEGORIES.items():
                score = sum(1 for kw in keywords if kw.lower() in full_text.lower())
                if score > best_score:
                    best_score = score
                    best_cat = cat
            
            if best_score > 0:
                categorized.append((full_text, best_cat))
        
        print("[OK] 已为 {} 个文档分配类别".format(len(categorized)))
        return categorized
    
    def analyze(self):
        """
        执行完整的贝叶斯分析流程
        
        Returns:
            dict: 分析结果
        """
        print("=" * 60)
        print("贝叶斯知识库分析")
        print("=" * 60)
        
        # 1. 加载文档
        documents = self.load_documents_from_chroma()
        
        # 2. 分配初始类别
        categorized = self.assign_initial_categories(documents)
        
        if not categorized:
            print("[WARN] 没有找到可分类的文档")
            return {}
        
        # 3. 训练分类器
        self.classifier.train(categorized)
        
        # 4. 对每个文档进行分类
        print("\n[INFO] 正在对文档进行分类...")
        results = []
        
        for text, meta in documents[:100]:  # 抽样分析前 100 个
            full_text = text + " " + str(meta.get("source", ""))
            predictions = self.classifier.predict(full_text, top_k=3)
            
            results.append({
                "source": meta.get("source", "unknown"),
                "predictions": [
                    {"category": cat, "probability": round(prob, 4)}
                    for cat, prob in predictions
                ],
                "top_category": predictions[0][0] if predictions else "未知",
                "confidence": round(predictions[0][1], 4) if predictions else 0,
            })
        
        self.results = results
        
        # 5. 生成统计
        category_distribution = Counter(r["top_category"] for r in results)
        
        output = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "total_documents": len(documents),
            "analyzed_documents": len(results),
            "category_distribution": dict(category_distribution),
            "category_stats": self.classifier.get_category_stats(),
            "sample_results": results[:20],
        }
        
        return output
    
    def search_with_confidence(self, query, top_k=5):
        """
        带置信度的贝叶斯搜索
        
        使用关键词匹配 + 贝叶斯置信度，避免向量搜索的网络请求
        
        Args:
            query: 搜索查询
            top_k: 返回结果数
        
        Returns:
            list of dicts with category predictions
        """
        from rag_core.knowledge_base import KnowledgeBase
        
        kb = KnowledgeBase(auto_import=False)
        all_docs = kb.vector_store.vectorstore._collection.get(
            include=["documents", "metadatas"],
            limit=1000  # 抽样搜索
        )
        documents = all_docs.get("documents", [])
        metadatas = all_docs.get("metadatas", [])
        
        # 对每个文档进行贝叶斯分类
        scored_results = []
        for doc_text, meta in zip(documents, metadatas):
            # 关键词匹配评分
            score = sum(1 for kw in query.split() if kw.lower() in doc_text.lower())
            if score == 0:
                continue
            
            predictions = self.classifier.predict(doc_text, top_k=1)
            top_cat, conf = predictions[0] if predictions else ("未知", 0)
            
            scored_results.append({
                "text": doc_text[:200],
                "source": meta.get("source", "unknown") if meta else "unknown",
                "predicted_category": top_cat,
                "confidence": round(conf, 4),
                "keyword_score": score,
            })
        
        # 按综合得分排序（关键词匹配 + 置信度）
        scored_results.sort(key=lambda x: x["keyword_score"] * x["confidence"], reverse=True)
        
        return scored_results[:top_k]


# ==================== CLI 入口 ====================

def main():
    parser = argparse.ArgumentParser(description="贝叶斯知识库分析工具")
    parser.add_argument("query", nargs="?", help="搜索查询（可选）")
    parser.add_argument("--top-k", type=int, default=5, help="返回结果数（默认5）")
    parser.add_argument("--analyze-categories", action="store_true", help="分析知识库类别分布")
    parser.add_argument("--output-file", help="输出文件路径（JSON）")
    
    args = parser.parse_args()
    
    analyzer = BayesianKnowledgeAnalyzer()
    
    if args.analyze_categories:
        # 完整分析
        result = analyzer.analyze()
        
        if result:
            print("\n" + "=" * 60)
            print("分析结果")
            print("=" * 60)
            print("\n类别分布:")
            for cat, count in sorted(result["category_distribution"].items(), key=lambda x: x[1], reverse=True):
                print("  {}: {} 个文档 ({:.1f}%)".format(
                    cat, count, count / result["analyzed_documents"] * 100
                ))
            
            print("\n分类器统计:")
            for cat, stats in result["category_stats"].items():
                print("  {}: {} 文档, 先验概率 {:.4f}, {} 唯一词".format(
                    cat, stats["document_count"], stats["prior_probability"], stats["unique_words"]
                ))
            
            # 保存结果
            if args.output_file:
                with open(args.output_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print("\n[OK] 结果已保存到: {}".format(args.output_file))
            else:
                print("\n" + json.dumps(result, ensure_ascii=False, indent=2)[:2000])
    
    elif args.query:
        # 带置信度的搜索
        analyzer.classifier.is_trained = True  # 跳过训练，直接分析
        
        # 先训练
        documents = analyzer.load_documents_from_chroma()
        categorized = analyzer.assign_initial_categories(documents)
        analyzer.classifier.train(categorized)
        
        # 搜索
        print("\n[INFO] 搜索: {}".format(args.query))
        results = analyzer.search_with_confidence(args.query, args.top_k)
        
        print("\n" + "-" * 60)
        print("搜索结果（按置信度排序）")
        print("-" * 60)
        
        for i, r in enumerate(results, 1):
            print("\n{}. [{}] 置信度: {:.2%}".format(i, r["predicted_category"], r["confidence"]))
            print("   来源: {}".format(r["source"]))
            print("   内容: {}...".format(r["text"]))
            print("   关键词匹配: {}".format(r.get("keyword_score", 0)))
    
    else:
        parser.print_help()


if __name__ == "__main__":
    # Fix GBK encoding issue on Windows console
    if sys.platform == "win32":
        import io
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
    main()
