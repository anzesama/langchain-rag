"""
Quality Assessment Module for RAG Chunks
=========================================
Evaluates chunk quality based on:
1. Completeness (sentence/heading/list integrity)
2. Readability (average sentence length, encoding issues)
3. Relevance (heading presence, structural signals)
4. Optional LLM-based evaluation
"""

import re
import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class QualityScore:
    """Single chunk quality score."""
    overall: float = 0.0          # 0-100
    completeness: float = 0.0     # 0-100
    readability: float = 0.0      # 0-100
    relevance: float = 0.0        # 0-100
    issues: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


class QualityAssessor:
    """
    Rule-based quality assessment for document chunks.
    
    Can optionally integrate with LLM for semantic relevance scoring.
    """
    
    # Minimum thresholds
    MIN_GOOD_SCORE = 60
    MIN_ACCEPTABLE_SCORE = 40
    
    # Sentence length limits (Chinese chars or English words)
    MAX_AVG_SENTENCE_LEN = 80       # characters/words
    MIN_AVG_SENTENCE_LEN = 5
        
    def __init__(self, llm_client=None, llm_model=None):
        """
        Args:
            llm_client: Optional LLM client for advanced evaluation
            llm_model: Optional model name to use
        """
        self.llm_client = llm_client
        self.llm_model = llm_model
        
    def assess_chunk(self, text: str, metadata: Dict = None) -> QualityScore:
        """
        Assess quality of a single chunk.
        
        Args:
            text: Chunk text content
            metadata: Optional chunk metadata
            
        Returns:
            QualityScore object
        """
        if not text or not text.strip():
            return QualityScore(
                overall=0, completeness=0, 
                readability=0, relevance=0,
                issues=["Empty chunk"]
            )
            
        issues = []
        
        # Run all assessments
        comp_score, comp_issues = self._assess_completeness(text)
        read_score, read_issues = self._assess_readability(text)
        rel_score, rel_issues = self._assess_relevance(text, metadata)
        
        issues.extend(comp_issues)
        issues.extend(read_issues)
        issues.extend(rel_issues)
        
        # Weighted overall score
        overall = (
            comp_score * 0.4 +
            read_score * 0.3 +
            rel_score * 0.3
        )
        
        return QualityScore(
            overall=round(overall, 1),
            completeness=round(comp_score, 1),
            readability=round(read_score, 1),
            relevance=round(rel_score, 1),
            issues=issues[:10],  # Limit issues listed
            metadata={
                "char_count": len(text),
                "word_count": self._count_words(text),
                "sentence_count": self._count_sentences(text),
                "heading_count": len(re.findall(r'^#{1,6}\s', text, re.MULTILINE)),
                "list_item_count": len(re.findall(r'^[\s]*[-*•]\s', text, re.MULTILINE)),
            }
        )
    
    def _assess_completeness(self, text: str) -> Tuple[float, List[str]]:
        """
        Assess structural completeness.
        
        Checks:
        - Does text end mid-sentence?
        - Are there incomplete lists?
        - Are there unclosed code blocks?
        - Are there orphaned headings?
        """
        score = 100.0
        issues = []
        
        # Check if ends mid-sentence
        if text.strip() and not re.match(r'[.!?。！？\]\)}"]\s*$', text.strip()):
            # Ends without terminal punctuation
            last_chars = text.strip()[-20:]
            if not any(marker in last_chars for marker in ['\n\n', '\n#', '\n-']):
                score -= 20
                issues.append("可能截断：文本不以句号/换行/列表结尾")
        
        # Check for incomplete lists
        lines = text.split('\n')
        in_list = False
        list_lines = []
        for line in lines:
            stripped = line.strip()
            if re.match(r'^[-*•]\s', stripped):
                in_list = True
                list_lines.append(stripped)
            elif in_list and stripped:
                if not re.match(r'^[-*•]\s', stripped):
                    # Non-list item after list items
                    if len(list_lines) > 2:
                        score -= 10
                        issues.append(f"可能不完整列表：{len(list_lines)}个列表项后出现非列表内容")
                    in_list = False
                    list_lines = []
        
        # Check for unclosed code blocks
        code_block_count = len(re.findall(r'```', text))
        if code_block_count % 2 != 0:
            score -= 15
            issues.append("可能不完整：存在未闭合的代码块")
        
        # Check for orphaned headings (heading at very end without content)
        heading_at_end = re.search(r'#{1,6}\s.*$', text.strip(), re.MULTILINE)
        if heading_at_end:
            remaining = text[heading_at_end.end():].strip()
            if not remaining or len(remaining) < 10:
                score -= 10
                issues.append("可能不完整：末尾有标题但无正文内容")
        
        return max(0, score), issues
    
    def _assess_readability(self, text: str) -> Tuple[float, List[str]]:
        """
        Assess text readability.
        
        Checks:
        - Average sentence length
        - Character encoding issues
        - Special character ratio
        """
        score = 100.0
        issues = []
        
        # Count sentences
        sentences = self._split_sentences(text)
        if not sentences:
            return 50, ["无法分割句子"]
        
        # Calculate average sentence length
        avg_len = sum(len(s.strip()) for s in sentences) / len(sentences)
        
        if avg_len > self.MAX_AVG_SENTENCE_LEN:
            penalty = min(40, (avg_len - self.MAX_AVG_SENTENCE_LEN) / 10)
            score -= penalty
            issues.append(f"句子过长：平均{avg_len:.0f}字符（建议<{self.MAX_AVG_SENTENCE_LEN}）")
        elif avg_len < self.MIN_AVG_SENTENCE_LEN and len(text) > 100:
            score -= 10
            issues.append(f"句子过短：平均{avg_len:.0f}字符")
        
        # Check for encoding issues
        try:
            text.encode('utf-8')
        except UnicodeEncodeError:
            score -= 30
            issues.append("存在编码问题")
        
        # Check special character ratio (symbols, emojis, etc.)
        special_chars = len(re.findall(r'[^\w\s\u4e00-\u9fff.,;:!?\-()\[\]{}""''/\\@#&]', text))
        special_ratio = special_chars / max(1, len(text))
        if special_ratio > 0.1:
            score -= 15
            issues.append(f"特殊字符比例过高：{special_ratio:.1%}")
        
        return max(0, score), issues
    
    def _assess_relevance(self, text: str, metadata: Dict = None) -> Tuple[float, List[str]]:
        """
        Assess structural relevance signals.
        
        Checks:
        - Has heading/title?
        - Has sufficient content?
        - Is it mostly whitespace/formatting?
        """
        score = 100.0
        issues = []
        
        # Check for heading presence
        has_heading = bool(re.search(r'^#{1,6}\s', text, re.MULTILINE))
        if not has_heading:
            score -= 15
            issues.append("无标题：可能缺少上下文标识")
        
        # Check content density (non-whitespace ratio)
        non_ws = len(re.sub(r'\s', '', text))
        ws_ratio = 1 - (non_ws / max(1, len(text)))
        if ws_ratio > 0.7:
            score -= 25
            issues.append(f"内容密度低：空白占比{ws_ratio:.0%}")
        
        # Check minimum length
        if len(text.strip()) < 20:
            score -= 20
            issues.append("内容过短：可能无实际信息量")
        
        return max(0, score), issues
    
    def _llm_assess_relevance(self, chunk: str, query: str) -> Optional[float]:
        """
        Use LLM to assess semantic relevance to query.
        
        Args:
            chunk: Chunk text
            query: User query
            
        Returns:
            Relevance score 0-1, or None if LLM unavailable
        """
        if not self.llm_client:
            return None
            
        prompt = f"""评估以下文本片段与查询的相关性，给出0-10的分数：

查询：{query}

文本片段：
{chunk[:500]}

请直接回复一个0-10的数字。"""
        
        try:
            response = self.llm_client.chat(prompt, model=self.llm_model)
            score_str = re.search(r'(\d+)', response)
            if score_str:
                return int(score_str.group(1)) / 10.0
        except Exception as e:
            print(f"LLM评估失败: {e}")
        
        return None
    
    def batch_assess(self, chunks: List[Dict]) -> List[QualityScore]:
        """
        Assess quality of multiple chunks.
        
        Args:
            chunks: List of dicts with 'text' and optional 'metadata'
            
        Returns:
            List of QualityScore objects
        """
        scores = []
        for chunk in chunks:
            score = self.assess_chunk(
                chunk.get('text', ''),
                chunk.get('metadata', {})
            )
            scores.append(score)
        return scores
    
    def filter_low_quality(self, chunks: List[Dict], min_score: float = None) -> List[Dict]:
        """
        Filter out low-quality chunks.
        
        Args:
            chunks: List of chunk dicts
            min_score: Minimum acceptable overall score (default: MIN_GOOD_SCORE)
            
        Returns:
            Filtered list of high-quality chunks
        """
        if min_score is None:
            min_score = self.MIN_GOOD_SCORE
            
        filtered = []
        for chunk in chunks:
            score = self.assess_chunk(chunk.get('text', ''), chunk.get('metadata', {}))
            if score.overall >= min_score:
                filtered.append(chunk)
        
        return filtered
    
    def get_quality_report(self, chunks: List[Dict]) -> Dict:
        """
        Generate summary report for a batch of chunks.
        
        Args:
            chunks: List of chunk dicts
            
        Returns:
            Report dict with statistics
        """
        scores = self.batch_assess(chunks)
        
        if not scores:
            return {"error": "No chunks to assess"}
        
        overall_scores = [s.overall for s in scores]
        comp_scores = [s.completeness for s in scores]
        read_scores = [s.readability for s in scores]
        rel_scores = [s.relevance for s in scores]
        
        # Categorize chunks
        good = sum(1 for s in overall_scores if s >= self.MIN_GOOD_SCORE)
        acceptable = sum(1 for s in overall_scores if 
                        self.MIN_ACCEPTABLE_SCORE <= s < self.MIN_GOOD_SCORE)
        poor = sum(1 for s in overall_scores if s < self.MIN_ACCEPTABLE_SCORE)
        
        return {
            "total_chunks": len(scores),
            "statistics": {
                "overall": {
                    "mean": round(sum(overall_scores) / len(overall_scores), 1),
                    "min": round(min(overall_scores), 1),
                    "max": round(max(overall_scores), 1),
                },
                "completeness": {
                    "mean": round(sum(comp_scores) / len(comp_scores), 1),
                },
                "readability": {
                    "mean": round(sum(read_scores) / len(read_scores), 1),
                },
                "relevance": {
                    "mean": round(sum(rel_scores) / len(rel_scores), 1),
                },
            },
            "distribution": {
                "good": good,
                "acceptable": acceptable,
                "poor": poor,
            },
            "low_quality_chunks": [
                {"index": i, "score": s.overall, "issues": s.issues}
                for i, s in enumerate(scores)
                if s.overall < self.MIN_ACCEPTABLE_SCORE
            ],
        }
    
    # --- Helper methods ---
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences (handles Chinese and English)."""
        # Split on terminal punctuation
        sentences = re.split(r'(?<=[.!?。！？\n])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _count_words(self, text: str) -> int:
        """Count words (Chinese characters + English words)."""
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        return chinese_chars + english_words
    
    def _count_sentences(self, text: str) -> int:
        """Count sentences."""
        return len(self._split_sentences(text))
