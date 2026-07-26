"""
analysis_archiver.py — 分析结果归档

核心职责：
1. 将分析结果（如政策对比、趋势分析）存入 analysis/ 目录
2. 每个分析带时间戳、版本、TTL
3. 支持按主题、日期范围查询分析历史
4. 支持逻辑标记过期（status=expired），不物理删除
"""
import json
from pathlib import Path
from datetime import datetime

from kb_manager.config import ANALYSIS_DIR, METADATA_DIR
from kb_manager.utils import generate_fingerprint, save_json, now_iso, ttl_until, load_json, list_files


class AnalysisArchiver:
    """分析结果归档器"""
    
    def __init__(self):
        self.analysis_dir = ANALYSIS_DIR
        self.metadata_dir = METADATA_DIR
    
    def archive(self, title: str, analysis_type: str, data: dict, 
                themes: list = None, source_files: list = None) -> dict:
        """
        归档一个分析结果
        
        Args:
            title: 分析标题
            analysis_type: 分析类型（如 "policy_comparison", "trend_analysis"）
            data: 分析数据（dict 或 list）
            themes: 关联的主题列表
            source_files: 数据来源文件列表
            
        Returns:
            归档元数据
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fingerprint = generate_fingerprint(json.dumps(data, ensure_ascii=False, default=str))
        
        filename = f"{analysis_type}_{timestamp}_{fingerprint}.json"
        filepath = self.analysis_dir / filename
        
        # 构建归档记录
        record = {
            "title": title,
            "type": analysis_type,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "valid_until": ttl_until(),  # 默认 90 天
            "status": "active",
            "themes": themes or [],
            "source_files": source_files or [],
            "fingerprint": fingerprint,
            "data": data,
        }
        
        save_json(filepath, record)
        
        # 同时保存精简版元数据（不含完整 data，方便快速索引）
        meta_record = {
            "title": title,
            "type": analysis_type,
            "created_at": record["created_at"],
            "valid_until": record["valid_until"],
            "status": record["status"],
            "themes": record["themes"],
            "fingerprint": fingerprint,
            "file_path": str(filepath),
            "data_size": len(json.dumps(data, ensure_ascii=False, default=str)),
        }
        meta_filepath = self.metadata_dir / f"{analysis_type}_{timestamp}.meta.json"
        save_json(meta_filepath, meta_record)
        
        print(f"[AnalysisArchiver] [OK] Archived: {filename}")
        print(f"   Title: {title}")
        print(f"   Type: {analysis_type}")
        print(f"   Themes: {', '.join(themes or [])}")
        print(f"   Valid Until: {record['valid_until']}")
        
        return meta_record
    
    def mark_expired(self, filename: str) -> bool:
        """逻辑标记分析结果为过期"""
        filepath = self.analysis_dir / filename
        if not filepath.exists():
            return False
        
        data = load_json(filepath)
        if not data:
            return False
        
        data["status"] = "expired"
        data["updated_at"] = now_iso()
        save_json(filepath, data)
        
        # 更新元数据
        meta_files = list(self.metadata_dir.glob(f"{filename.split('_')[0]}_*.meta.json"))
        for mf in meta_files:
            meta = load_json(mf)
            if meta and meta.get("fingerprint") == data.get("fingerprint"):
                meta["status"] = "expired"
                save_json(mf, meta)
        
        print(f"[AnalysisArchiver] ⏰ 已标记过期: {filename}")
        return True
    
    def list_analyses(self, status: str = "active", include_expired: bool = False) -> list:
        """
        列出分析结果
        
        Args:
            status: 状态过滤 ("active" | "expired" | "all")
            include_expired: 是否包含过期结果
            
        Returns:
            元数据列表
        """
        results = []
        meta_files = list_files(self.metadata_dir, ".meta.json")
        
        for mf in meta_files:
            meta = load_json(mf)
            if not meta:
                continue
            
            if status == "all" or include_expired:
                results.append(meta)
            elif meta.get("status") == status:
                results.append(meta)
        
        return sorted(results, key=lambda x: x.get("created_at", ""), reverse=True)
    
    def search_by_theme(self, theme: str, status: str = "active") -> list:
        """按主题搜索分析结果"""
        analyses = self.list_analyses(status=status)
        return [a for a in analyses if theme in a.get("themes", [])]
