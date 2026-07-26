"""
data_ingestor.py — 数据采集与入库

核心职责：
1. 调用 trend-radar 的 policy_collector 抓取政策数据
2. 将原始数据存入 kb_manager/raw/
3. 生成元数据和指纹，用于去重和追踪
"""
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kb_manager.config import RAW_DIR, COLLECTOR_CONFIG
from kb_manager.utils import generate_fingerprint, save_json, now_iso, ttl_until


class DataIngestor:
    """数据采集器"""
    
    def __init__(self):
        self.raw_dir = RAW_DIR
        self.trend_radar_dir = Path(COLLECTOR_CONFIG["trend_radar_dir"])
    
    def fetch_via_mcp(self, keyword: str, start_date: str, end_date: str, limit: int = 30) -> list:
        """
        通过 MCP 服务器抓取政策数据
        
        Args:
            keyword: 搜索关键词
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            limit: 最多返回条数
            
        Returns:
            政策列表
        """
        mcp_script = self.trend_radar_dir / "node_modules" / "@iflow-mcp" / "guangxiangdebizi-central-policy-mcp" / "build" / "index.js"
        
        if not mcp_script.exists():
            raise FileNotFoundError(f"MCP 服务器不存在: {mcp_script}")
        
        proc = subprocess.Popen(
            ["node", str(mcp_script)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="ignore"
        )
        
        # Initialize
        init = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "kb-manager", "version": "1.0"}}
        }
        proc.stdin.write(json.dumps(init) + "\n")
        proc.stdin.flush()
        proc.stdout.readline()  # consume init response
        
        # Call
        call = {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {
                "name": "get_latest_policies",
                "arguments": {"keyword": keyword, "startdate": start_date,
                              "enddate": end_date, "limit": limit}
            }
        }
        proc.stdin.write(json.dumps(call) + "\n")
        proc.stdin.flush()
        resp = proc.stdout.readline()
        proc.stdin.close()
        proc.wait(timeout=60)
        
        if "result" not in resp:
            return []
        
        data = json.loads(resp)
        content = data["result"]["content"][0]["text"]
        parsed = json.loads(content)
        return parsed.get("items", [])
    
    def fetch_and_save(self, keyword: str = "国务院", days: int = 30, limit: int = 30) -> dict:
        """
        抓取政策数据并保存到 raw/ 目录
        
        Args:
            keyword: 搜索关键词
            days: 最近 N 天
            limit: 最多条数
            
        Returns:
            保存的文件路径和元数据
        """
        from datetime import timedelta
        
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        print(f"[DataIngestor] 抓取政策数据: {keyword}, {start_date} ~ {end_date}")
        
        # 抓取
        items = self.fetch_via_mcp(keyword, start_date, end_date, limit)
        if not items:
            print("[DataIngestor] ⚠️ 未获取到数据")
            return {"success": False, "reason": "no_data"}
        
        # 构建原始数据
        raw_data = {
            "source": "gov.cn (中央政策 MCP)",
            "keyword": keyword,
            "date_range": {"start": start_date, "end": end_date},
            "count": len(items),
            "collected_at": now_iso(),
            "items": items,
        }
        
        # 生成指纹
        fingerprint = generate_fingerprint(json.dumps(raw_data, ensure_ascii=False))
        
        # 保存文件
        filename = f"policy_{start_date.replace('-','')}_{end_date.replace('-','')}_{fingerprint}.json"
        filepath = self.raw_dir / filename
        
        metadata = {
            "filename": filename,
            "fingerprint": fingerprint,
            "source": raw_data["source"],
            "keyword": keyword,
            "date_range": raw_data["date_range"],
            "count": raw_data["count"],
            "collected_at": raw_data["collected_at"],
            "status": "active",
            "valid_until": ttl_until(),  # 默认 90 天有效
            "file_path": str(filepath),
        }
        
        save_json(filepath, raw_data)
        print(f"[DataIngestor] ✅ 已保存: {filepath}")
        print(f"   指纹: {fingerprint}")
        print(f"   条数: {len(items)}")
        
        return metadata
