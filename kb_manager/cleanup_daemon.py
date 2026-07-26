"""
cleanup_daemon.py — 过期数据清理守护进程

核心职责：
1. 扫描 analysis/ 目录，找出 valid_until 已过期的分析
2. 逻辑标记为 expired（不物理删除）
3. 可选：清理超过 N 天的过期原始数据
4. 可定时任务运行（cron / schedule）

使用方式：
  python cleanup_daemon.py [--dry-run] [--older-than 180]
"""
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kb_manager.config import ANALYSIS_DIR, RAW_DIR, METADATA_DIR
from kb_manager.utils import load_json, save_json, list_files


def cleanup_analyses(dry_run: bool = False, older_than_days: int = None) -> dict:
    """
    清理过期的分析结果
    
    Args:
        dry_run: 仅预览，不实际修改
        older_than_days: 只清理超过 N 天的（None = 清理所有过期）
        
    Returns:
        清理统计
    """
    stats = {"expired": 0, "kept": 0, "errors": 0}
    today = datetime.now()
    
    analysis_files = list_files(ANALYSIS_DIR)
    for f in analysis_files:
        data = load_json(f)
        if not data:
            continue
        
        valid_until = data.get("valid_until", "")
        if not valid_until:
            stats["kept"] += 1
            continue
        
        try:
            expiry_date = datetime.strptime(valid_until, "%Y-%m-%d")
        except ValueError:
            stats["errors"] += 1
            continue
        
        # 判断是否过期
        is_expired = expiry_date < today
        is_old = False
        if older_than_days:
            created_at = data.get("created_at", "")
            if created_at:
                try:
                    created_date = datetime.fromisoformat(created_at.replace("Z", "+00:00").replace("+00:00", ""))
                    is_old = (today - created_date).days > older_than_days
                except:
                    pass
        
        if is_expired and (not older_than_days or is_old):
            if not dry_run:
                data["status"] = "expired"
                data["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                save_json(f, data)
            stats["expired"] += 1
            print(f"  ⏰ 过期: {f.name} (有效期至: {valid_until})")
        else:
            stats["kept"] += 1
    
    return stats


def cleanup_raw_data(dry_run: bool = False, older_than_days: int = 365) -> dict:
    """
    清理过期的原始数据（可选，默认 1 年以上）
    
    Args:
        dry_run: 仅预览
        older_than_days: 超过 N 天的原始数据
        
    Returns:
        清理统计
    """
    stats = {"deleted": 0, "kept": 0}
    today = datetime.now()
    
    raw_files = list_files(RAW_DIR)
    for f in raw_files:
        data = load_json(f)
        if not data:
            stats["kept"] += 1
            continue
        
        collected_at = data.get("collected_at", "")
        if not collected_at:
            stats["kept"] += 1
            continue
        
        try:
            collected_date = datetime.fromisoformat(collected_at.replace("Z", "").replace("+00:00", ""))
        except ValueError:
            stats["kept"] += 1
            continue
        
        age_days = (today - collected_date).days
        if age_days > older_than_days:
            if not dry_run:
                f.unlink()
                stats["deleted"] += 1
                print(f"  🗑️  删除: {f.name} (采集于: {collected_at}, 年龄: {age_days}天)")
            else:
                print(f"  🗑️  [预览] 将删除: {f.name}")
                stats["deleted"] += 1
        else:
            stats["kept"] += 1
    
    return stats


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="KB Manager 清理守护进程")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际修改")
    parser.add_argument("--analyses-only", action="store_true", help="只清理分析结果")
    parser.add_argument("--raw-only", action="store_true", help="只清理原始数据")
    parser.add_argument("--older-than", type=int, default=None, help="只清理超过 N 天的（分析）")
    parser.add_argument("--raw-older-than", type=int, default=365, help="超过 N 天的原始数据（默认365天）")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print(f"🧹 KB Manager Cleanup Daemon")
    print(f"   Dry Run: {args.dry_run}")
    print("=" * 60)
    
    # 清理分析结果
    if not args.raw_only:
        print("\n📊 清理过期分析结果...")
        stats = cleanup_analyses(dry_run=args.dry_run, older_than_days=args.older_than)
        print(f"   过期: {stats['expired']}, 保留: {stats['kept']}, 错误: {stats['errors']}")
    
    # 清理原始数据
    if not args.analyses_only:
        print(f"\n📁 清理过期原始数据 (> {args.raw_older_than}天)...")
        stats = cleanup_raw_data(dry_run=args.dry_run, older_than_days=args.raw_older_than)
        print(f"   删除: {stats['deleted']}, 保留: {stats['kept']}")
    
    print("\n✅ 清理完成")


if __name__ == "__main__":
    main()
