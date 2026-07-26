"""
TrendRadar 新闻导入器

功能：
- 读取 trend-radar 目录下的最新趋势日报和政策情报（Markdown 格式）
- 解析新闻/政策条目，提取结构化数据
- 自动导入到 RAG 知识库（ChromaDB + Wiki）
- 支持增量导入（跳过已导入的新闻/政策）

用法：
    python tools/trend_importer.py              # 导入所有未导入的报告
    python tools/trend_importer.py --latest     # 仅导入最新的日报
    python tools/trend_importer.py --count 3    # 导入最近 3 份报告
    python tools/trend_importer.py --type trend  # 仅导入趋势日报
    python tools/trend_importer.py --type policy # 仅导入政策情报
    python tools/trend_importer.py --force       # 强制重新导入
"""

import sys
import os
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rag_config import logger
from rag_core.knowledge_base import KnowledgeBase
from rag_core.wiki_db import get_wiki_db
from langchain_core.documents import Document


class TrendImporter:
    """TrendRadar 新闻/政策导入器"""

    def __init__(self, kb: Optional[KnowledgeBase] = None):
        """
        Args:
            kb: 知识库实例，默认自动创建
        """
        self.kb = kb or KnowledgeBase()
        
        # trend-radar 目录
        self.trend_radar_dir = project_root.parent / "trend-radar"
        self.trend_dir = self.trend_radar_dir / "documents" / "趋势情报"
        self.policy_dir = self.trend_radar_dir / "documents" / "政策情报"
        
        # 已导入记录
        self.imported_file = project_root / "data" / "trend_import_log.json"
        self._load_import_log()

    def _load_import_log(self):
        """加载已导入日志"""
        import json
        
        if self.imported_file.exists():
            try:
                with open(self.imported_file, 'r', encoding='utf-8') as f:
                    self.import_log = json.load(f)
            except Exception:
                self.import_log = {"imported_files": [], "imported_titles": []}
        else:
            self.import_log = {"imported_files": [], "imported_titles": []}

    def _save_import_log(self):
        """保存导入日志"""
        import json
        
        self.imported_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.imported_file, 'w', encoding='utf-8') as f:
            json.dump(self.import_log, f, ensure_ascii=False, indent=2)

    def get_available_reports(self, count: int = None, doc_type: str = None) -> List[Path]:
        """
        获取可用的报告文件列表
        
        Args:
            count: 返回数量，None 表示全部
            doc_type: 报告类型，'trend'(趋势日报), 'policy'(政策情报), 或 None(全部)
            
        Returns:
            文件路径列表（按时间倒序）
        """
        report_files = []
        
        if doc_type is None or doc_type == 'trend':
            if self.trend_dir.exists():
                trend_files = sorted(
                    [f for f in self.trend_dir.glob("*.md")],
                    key=lambda x: x.stat().st_mtime,
                    reverse=True
                )
                report_files.extend(trend_files)
        
        if doc_type is None or doc_type == 'policy':
            if self.policy_dir.exists():
                policy_files = sorted(
                    [f for f in self.policy_dir.glob("*.md")],
                    key=lambda x: x.stat().st_mtime,
                    reverse=True
                )
                report_files.extend(policy_files)
        
        if not report_files:
            print(f"[WARNING] 未找到任何报告文件")
            return []
        
        # 按时间排序并截取
        report_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        if count:
            report_files = report_files[:count]
        
        return report_files

    def parse_trend_report(self, filepath: Path) -> Dict:
        """解析趋势日报 Markdown 文件"""
        content = filepath.read_text(encoding='utf-8')
        
        date_match = re.search(r'# 趋势日报 — (.+)', content)
        date_str = date_match.group(1).strip() if date_match else "未知日期"
        
        platform_match = re.search(r'> 平台覆盖：(.+)', content)
        platforms = platform_match.group(1).strip() if platform_match else ""
        
        # 提取新闻条目
        news_items = []
        news_pattern = r'### (\d+)\.\s+(.+?)\n- \*\*平台\*\*: (.+?)\n- \*\*热度\*\*: (.+?)\n- \*\*链接\*\*: (.+?)\n- \*\*URL\*\*: (.+?)\n'
        
        for match in re.finditer(news_pattern, content):
            news_items.append({
                "title": match.group(2).strip(),
                "platform": match.group(3).strip(),
                "hotness": match.group(4).strip(),
                "link": match.group(5).strip(),
                "url": match.group(6).strip(),
            })
        
        if not news_items:
            news_items = self._parse_loose_format(content)
        
        return {
            "filename": filepath.name,
            "date": date_str,
            "platforms": platforms,
            "news_count": len(news_items),
            "news_items": news_items,
            "raw_content": content,
            "doc_type": "trend"
        }

    def parse_policy_report(self, filepath: Path) -> Dict:
        """解析政策情报 Markdown 文件"""
        content = filepath.read_text(encoding='utf-8')
        
        date_match = re.search(r'# 政策情报日报 — (.+)', content)
        date_str = date_match.group(1).strip() if date_match else "未知日期"
        
        source_match = re.search(r'> 数据来源：(.+?)(?:\n|$)', content)
        source = source_match.group(1).strip() if source_match else "中国政府网"
        
        # 提取政策条目
        policy_items = []
        policy_pattern = r'### (\d+)\.\s+(.+?)\n- \*\*发文机关\*\*: (.+?)\n- \*\*发布日期\*\*: (.+?)\n- \*\*文件编号\*\*: (.+?)\n- \*\*分类\*\*: (.+?)\n- \*\*摘要\*\*: (.+?)\n- \*\*链接\*\*: (.+?)\n'
        
        for match in re.finditer(policy_pattern, content):
            policy_items.append({
                "title": match.group(2).strip(),
                "authority": match.group(3).strip(),
                "publish_date": match.group(4).strip(),
                "doc_number": match.group(5).strip(),
                "category": match.group(6).strip(),
                "summary": match.group(7).strip(),
                "link": match.group(8).strip(),
            })
        
        if not policy_items:
            policy_items = self._parse_policy_loose_format(content)
        
        return {
            "filename": filepath.name,
            "date": date_str,
            "source": source,
            "policy_count": len(policy_items),
            "policy_items": policy_items,
            "raw_content": content,
            "doc_type": "policy"
        }

    def _parse_loose_format(self, content: str) -> List[Dict]:
        """宽松格式解析（趋势日报备用方案）"""
        news_items = []
        sections = re.split(r'### \d+\.\s+', content)
        
        for section in sections[1:]:
            lines = section.strip().split('\n')
            title = lines[0].strip() if lines else ""
            
            platform = ""
            hotness = ""
            link = ""
            url = ""
            
            for line in lines[1:]:
                if '**平台**:' in line:
                    platform = line.split('**平台**:')[-1].strip()
                elif '**热度**:' in line:
                    hotness = line.split('**热度**:')[-1].strip()
                elif '**链接**:' in line:
                    link = line.split('**链接**:')[-1].strip()
                elif '**URL**:' in line:
                    url = line.split('**URL**:')[-1].strip()
            
            if title:
                news_items.append({
                    "title": title,
                    "platform": platform,
                    "hotness": hotness,
                    "link": link,
                    "url": url,
                })
        
        return news_items

    def _parse_policy_loose_format(self, content: str) -> List[Dict]:
        """宽松格式解析（政策情报备用方案）"""
        policy_items = []
        sections = re.split(r'### \d+\.\s+', content)
        
        for section in sections[1:]:
            lines = section.strip().split('\n')
            title = lines[0].strip() if lines else ""
            
            authority = ""
            publish_date = ""
            doc_number = ""
            category = ""
            summary = ""
            link = ""
            
            for line in lines[1:]:
                if '**发文机关**:' in line:
                    authority = line.split('**发文机关**:')[-1].strip()
                elif '**发布日期**:' in line:
                    publish_date = line.split('**发布日期**:')[-1].strip()
                elif '**文件编号**:' in line:
                    doc_number = line.split('**文件编号**:')[-1].strip()
                elif '**分类**:' in line:
                    category = line.split('**分类**:')[-1].strip()
                elif '**摘要**:' in line:
                    summary = line.split('**摘要**:')[-1].strip()
                elif '**链接**:' in line:
                    link = line.split('**链接**:')[-1].strip()
            
            if title:
                policy_items.append({
                    "title": title,
                    "authority": authority,
                    "publish_date": publish_date,
                    "doc_number": doc_number,
                    "category": category,
                    "summary": summary,
                    "link": link,
                })
        
        return policy_items

    def create_documents(self, report_data: Dict) -> List[Document]:
        """将解析后的报告转换为 LangChain Document 对象"""
        documents = []
        
        if report_data['doc_type'] == 'trend':
            # 趋势日报
            for i, item in enumerate(report_data['news_items'], 1):
                page_content = f"""## 新闻 {i}: {item['title']}
- 平台: {item['platform']}
- 热度: {item['hotness']}
- 链接: {item['link']}
- URL: {item['url']}

来源: 趋势日报-{report_data['date']}
"""
                metadata = {
                    "source": f"trend/{report_data['filename']}",
                    "news_title": item['title'],
                    "news_platform": item['platform'],
                    "news_hotness": item['hotness'],
                    "news_url": item['url'],
                    "report_date": report_data['date'],
                    "report_filename": report_data['filename'],
                    "document_type": "trend_news",
                }
                
                doc = Document(page_content=page_content, metadata=metadata)
                documents.append(doc)
        
        elif report_data['doc_type'] == 'policy':
            # 政策情报
            for i, item in enumerate(report_data['policy_items'], 1):
                page_content = f"""## 政策 {i}: {item['title']}
- 发文机关: {item['authority']}
- 发布日期: {item['publish_date']}
- 文件编号: {item['doc_number']}
- 分类: {item['category']}
- 摘要: {item['summary']}
- 链接: {item['link']}

来源: 政策情报日报-{report_data['date']}
"""
                metadata = {
                    "source": f"policy/{report_data['filename']}",
                    "policy_title": item['title'],
                    "policy_authority": item['authority'],
                    "policy_publish_date": item['publish_date'],
                    "policy_doc_number": item['doc_number'],
                    "policy_category": item['category'],
                    "policy_summary": item['summary'],
                    "policy_link": item['link'],
                    "report_date": report_data['date'],
                    "report_filename": report_data['filename'],
                    "document_type": "policy_intel",
                }
                
                doc = Document(page_content=page_content, metadata=metadata)
                documents.append(doc)
        
        return documents

    def _add_policy_relations(self, report_data: Dict):
        """为政策情报添加关系到 Wiki 层"""
        if report_data['doc_type'] != 'policy':
            return
        
        wiki_db = get_wiki_db()
        if not wiki_db:
            return
        
        relations_added = 0
        relations_skipped = 0
        
        for item in report_data['policy_items']:
            title = item['title']
            authority = item['authority']
            category = item['category']
            filename = report_data['filename']
            
            # 确保政策标题作为实体存在
            if title:
                wiki_db.add_entity(title, '政策', {
                    'doc_number': item.get('doc_number', ''),
                    'publish_date': item.get('publish_date', ''),
                    'source_file': filename
                })
            
            # 1. 添加发文机关关系
            if authority and title:
                try:
                    # 确保发文机关作为实体存在
                    wiki_db.add_entity(authority, '机构', {})
                    
                    # 检查关系是否已存在
                    source_id = wiki_db.get_entity_id(authority)
                    target_id = wiki_db.get_entity_id(title)
                    
                    if source_id and target_id:
                        conn = wiki_db.connect()
                        cursor = conn.cursor()
                        cursor.execute('''
                            SELECT id FROM relationships
                            WHERE source_id = ? AND target_id = ? AND rel_type = ?
                        ''', (source_id, target_id, '发文'))
                        
                        if not cursor.fetchone():
                            # 添加发文关系
                            wiki_db.add_relationship(
                                source_name=authority,
                                target_name=title,
                                rel_type='发文',
                                properties={'doc_number': item.get('doc_number', ''), 'publish_date': item.get('publish_date', '')},
                                source_chapter=f"policy/{filename}"
                            )
                            relations_added += 1
                            logger.info(f"[Wiki] 添加关系: {authority} -发文-> {title}")
                        else:
                            relations_skipped += 1
                        conn.close()
                except Exception as e:
                    logger.warning(f"[Wiki] 添加发文关系失败: {e}")
            
            # 2. 添加分类关系
            if category and title:
                try:
                    # 确保分类作为实体存在
                    wiki_db.add_entity(category, '分类', {})
                    
                    # 检查关系是否已存在
                    source_id = wiki_db.get_entity_id(title)
                    target_id = wiki_db.get_entity_id(category)
                    
                    if source_id and target_id:
                        conn = wiki_db.connect()
                        cursor = conn.cursor()
                        cursor.execute('''
                            SELECT id FROM relationships
                            WHERE source_id = ? AND target_id = ? AND rel_type = ?
                        ''', (source_id, target_id, '属于'))
                        
                        if not cursor.fetchone():
                            # 添加属于关系
                            wiki_db.add_relationship(
                                source_name=title,
                                target_name=category,
                                rel_type='属于',
                                properties={},
                                source_chapter=f"policy/{filename}"
                            )
                            relations_added += 1
                            logger.info(f"[Wiki] 添加关系: {title} -属于-> {category}")
                        else:
                            relations_skipped += 1
                        conn.close()
                except Exception as e:
                    logger.warning(f"[Wiki] 添加分类关系失败: {e}")
        
        if relations_added > 0:
            print(f"  [Wiki] 新增关系: {relations_added} 条, 跳过: {relations_skipped} 条")

    def is_already_imported(self, filename: str) -> bool:
        """检查文件是否已导入"""
        return filename in self.import_log.get("imported_files", [])

    def is_title_imported(self, title: str) -> bool:
        """检查标题是否已导入（用于去重）"""
        return title in self.import_log.get("imported_titles", [])

    def import_report(self, filepath: Path) -> Dict:
        """导入单个报告"""
        filename = filepath.name
        
        # 检查是否已导入
        if self.is_already_imported(filename):
            print(f"  [SKIP] 已导入: {filename}")
            return {"skipped": 1, "added": 0, "errors": 0}
        
        print(f"\n  [IMPORT] 正在导入: {filename}")
        
        try:
            # 解析报告
            if '趋势' in filename:
                report_data = self.parse_trend_report(filepath)
            elif '政策' in filename:
                report_data = self.parse_policy_report(filepath)
            else:
                # 尝试自动检测
                content = filepath.read_text(encoding='utf-8')
                if '趋势日报' in content:
                    report_data = self.parse_trend_report(filepath)
                elif '政策情报' in content:
                    report_data = self.parse_policy_report(filepath)
                else:
                    print(f"  [WARN] 无法识别的报告格式")
                    return {"skipped": 0, "added": 0, "errors": 1}
            
            # 创建文档
            documents = self.create_documents(report_data)
            
            if not documents:
                print(f"  [WARN] 未解析到任何条目")
                return {"skipped": 0, "added": 0, "errors": 1}
            
            # 添加图谱关系到 Wiki 层
            if report_data['doc_type'] == 'policy':
                self._add_policy_relations(report_data)
            
            # 添加到知识库
            added_count = 0
            skipped_count = 0
            
            for doc in documents:
                title = doc.metadata.get('news_title', '') or doc.metadata.get('policy_title', '')
                if self.is_title_imported(title):
                    skipped_count += 1
                    continue
                
                self.kb.vector_store.add_documents([doc])
                
                # 同步 Wiki 层（实体提取）
                self.kb._sync_wiki_layer([doc], str(filepath))
                
                # 记录导入
                if title not in self.import_log["imported_titles"]:
                    self.import_log["imported_titles"].append(title)
                
                added_count += 1
            
            # 更新日志
            if filename not in self.import_log["imported_files"]:
                self.import_log["imported_files"].append(filename)
            
            self._save_import_log()
            
            print(f"  [OK] 导入完成: {added_count} 条, {skipped_count} 条已存在")
            
            return {
                "skipped": skipped_count,
                "added": added_count,
                "errors": 0
            }
            
        except Exception as e:
            print(f"  [ERROR] 导入失败: {e}")
            import traceback
            traceback.print_exc()
            return {"skipped": 0, "added": 0, "errors": 1}

    def import_all(self, count: int = None, doc_type: str = None) -> Dict:
        """批量导入报告"""
        print("=" * 60)
        print("TrendRadar 数据导入开始")
        print("=" * 60)
        
        # 获取可用报告
        report_files = self.get_available_reports(count, doc_type)
        
        if not report_files:
            print("\n[ERROR] 未找到任何报告文件")
            return {"total_skipped": 0, "total_added": 0, "total_errors": 0}
        
        print(f"\n[INFO] 找到 {len(report_files)} 份报告")
        
        # 统计
        total_stats = {"skipped": 0, "added": 0, "errors": 0}
        
        for filepath in report_files:
            stats = self.import_report(filepath)
            total_stats["skipped"] += stats["skipped"]
            total_stats["added"] += stats["added"]
            total_stats["errors"] += stats["errors"]
        
        # 总结
        print("\n" + "=" * 60)
        print("导入完成！")
        print(f"   新增: {total_stats['added']} 条")
        print(f"   跳过: {total_stats['skipped']} 条（已存在）")
        print(f"   错误: {total_stats['errors']} 份报告")
        print("=" * 60)
        
        return total_stats


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="TrendRadar 数据导入器")
    parser.add_argument("--latest", action="store_true", help="仅导入最新的报告")
    parser.add_argument("--count", type=int, default=None, help="导入最近 N 份报告")
    parser.add_argument("--type", choices=["trend", "policy"], default=None, help="报告类型")
    parser.add_argument("--force", action="store_true", help="强制重新导入")
    
    args = parser.parse_args()
    
    # 创建导入器
    importer = TrendImporter()
    
    # 如果 force 模式，清空导入日志
    if args.force:
        importer.import_log = {"imported_files": [], "imported_titles": []}
        importer._save_import_log()
        print("[INFO] 强制模式：已清空导入记录")
    
    # 确定数量
    count = 1 if args.latest else args.count
    
    # 执行导入
    result = importer.import_all(count=count, doc_type=args.type)
    
    # 退出码
    sys.exit(0 if result["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
