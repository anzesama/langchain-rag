"""
agent_bridge.py — Agent 决策入口

核心职责：
1. 接收用户问题
2. 先查知识库，判断覆盖度和新鲜度
3. 如果不足 → 触发数据采集 → 存入知识库 → 再回答

使用方式：
  from kb_manager.agent_bridge import AgentBridge
  
  bridge = AgentBridge()
  answer = bridge.answer_query("最近中国有哪些重大政策变化？")
"""
import sys
from pathlib import Path

# 确保能导入 kb_manager 模块
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kb_manager.config import FRESHNESS_THRESHOLD_DAYS, THEME_KEYWORDS
from kb_manager.utils import load_json, list_files, now_iso, ttl_until
from kb_manager.data_ingestor import DataIngestor
from kb_manager.analysis_archiver import AnalysisArchiver


class AgentBridge:
    """Agent 决策桥接器"""
    
    def __init__(self):
        self.ingestor = DataIngestor()
        self.archiver = AnalysisArchiver()
    
    def check_coverage(self, query: str) -> dict:
        """
        检查知识库对某个问题的覆盖度
        
        Returns:
            {
                "covered": bool,       # 是否有相关内容
                "sources": [...],      # 命中的知识库来源
                "freshness": "fresh" | "stale" | "none",
                "missing_themes": [...]  # 缺失的主题
            }
        """
        from kb_manager import utils
        
        result = {
            "covered": False,
            "sources": [],
            "freshness": "none",
            "missing_themes": [],
        }
        
        # 1. 扫描 raw/ 目录，检查是否有相关原始数据
        raw_files = list_files(utils.RAW_DIR)
        for f in raw_files:
            meta = load_json(f)
            if meta and meta.get("status") == "active":
                result["sources"].append(str(f.name))
                created = meta.get("created_at", "")
                if created:
                    try:
                        created_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        age_days = (datetime.now() - created_date).days
                        if age_days <= FRESHNESS_THRESHOLD_DAYS:
                            result["freshness"] = "fresh"
                        else:
                            result["freshness"] = "stale"
                    except:
                        pass
                result["covered"] = True
        
        # 2. 扫描 analysis/ 目录，检查是否有相关分析结果
        analysis_files = list_files(utils.ANALYSIS_DIR)
        for f in analysis_files:
            meta = load_json(f)
            if meta and meta.get("status") == "active":
                result["sources"].append(str(f.name))
                valid_until = meta.get("valid_until", "")
                if valid_until:
                    try:
                        from datetime import datetime
                        valid_date = datetime.strptime(valid_until, "%Y-%m-%d")
                        if valid_date > datetime.now():
                            result["freshness"] = "fresh"
                        elif result["freshness"] != "fresh":
                            result["freshness"] = "stale"
                    except:
                        pass
                result["covered"] = True
        
        # 3. 检查缺失的主题
        query_lower = query.lower()
        for theme, keywords in THEME_KEYWORDS.items():
            if any(kw in query for kw in keywords):
                # 主题被提及，检查是否已有相关数据
                has_theme_data = any(
                    theme in str(f) or theme in load_json(f).get("theme", "")
                    for f in raw_files + analysis_files
                    if load_json(f)
                )
                if not has_theme_data:
                    result["missing_themes"].append(theme)
        
        return result
    
    def answer_query(self, query: str) -> str:
        """
        回答用户问题 — 自动判断是否需要补充数据
        
        Args:
            query: 用户问题
            
        Returns:
            回答字符串
        """
        # 1. 检查覆盖度
        coverage = self.check_coverage(query)
        
        # 2. 如果覆盖不足，触发数据采集
        if not coverage["covered"] or coverage["freshness"] == "stale":
            print(f"[KB Manager] 知识库覆盖不足，触发数据采集...")
            print(f"  覆盖: {coverage['covered']}, 新鲜度: {coverage['freshness']}")
            print(f"  缺失主题: {coverage['missing_themes']}")
            
            # 自动调用 trend-radar 采集相关政策数据
            try:
                self.ingestor.fetch_and_save("国务院", days=90, limit=50)
                print("[KB Manager] ✅ 数据采集完成")
            except Exception as e:
                print(f"[KB Manager] ⚠️ 数据采集失败: {e}")
        
        # 3. 返回指引（实际回答由上层 LLM 完成）
        sources_info = ", ".join(coverage["sources"][:5])
        if coverage["sources"]:
            return f"[知识库来源: {sources_info}{'...' if len(coverage['sources']) > 5 else ''}]"
        else:
            return "[知识库无相关数据]"
