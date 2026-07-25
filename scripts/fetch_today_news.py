#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取今日新闻脚本
"""

import requests
from datetime import datetime
import re
import json

def fetch_google_news():
    """从Google News获取今日新闻"""
    try:
        url = "https://news.google.com/rss/search?q=%E4%BB%8A%E6%97%A5%E6%96%B0%E9%97%BB&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            # 解析RSS
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.content)
            items = []
            for item in root.findall('.//item'):
                title = item.find('title').text
                link = item.find('link').text
                pub_date = item.find('pubDate').text
                items.append({'title': title, 'link': link, 'date': pub_date})
            return items
    except Exception as e:
        print(f"Google News error: {e}")
    return []

def fetch_bbc_chinese():
    """从BBC中文网获取今日新闻"""
    try:
        url = "https://www.bbc.com/zhongwen/simp/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            # 提取新闻标题
            headlines = re.findall(r'<h3[^>]*><a[^>]*>([^<]+)</a></h3>', resp.text)
            return [{'title': h.strip(), 'link': '', 'date': 'BBC Chinese'} for h in headlines[:15]]
    except Exception as e:
        print(f"BBC Chinese error: {e}")
    return []

def fetch_cctv_chinese():
    """从央视网获取今日新闻"""
    try:
        url = "https://news.cctv.com/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            # 提取头条新闻
            headlines = re.findall(r'<a[^>]*class="[^"]*headline[^"]*"[^>]*>([^<]+)</a>', resp.text)
            return [{'title': h.strip(), 'link': '', 'date': 'CCTV'} for h in headlines[:15]]
    except Exception as e:
        print(f"CCTV error: {e}")
    return []

def main():
    print("=" * 60)
    print(f"今日新闻采集 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    all_news = []

    print("\n📡 正在从 Google News 获取新闻...")
    google_news = fetch_google_news()
    if google_news:
        all_news.extend(google_news[:20])
        print(f"✅ 获取 {len(google_news)} 条 Google News")

    print("\n📡 正在从 BBC中文网 获取新闻...")
    bbc_news = fetch_bbc_chinese()
    if bbc_news:
        all_news.extend(bbc_news[:10])
        print(f"✅ 获取 {len(bbc_news)} 条 BBC新闻")

    print("\n📡 正在从 央视网 获取新闻...")
    cctv_news = fetch_cctv_chinese()
    if cctv_news:
        all_news.extend(cctv_news[:10])
        print(f"✅ 获取 {len(cctv_news)} 条 CCTV新闻")

    # 去重并排序
    unique_news = {}
    for news in all_news:
        title = news['title']
        if title not in unique_news:
            unique_news[title] = news

    sorted_news = sorted(unique_news.values(), key=lambda x: x.get('date', ''), reverse=True)

    print(f"\n📊 总计获取 {len(sorted_news)} 条新闻\n")

    # 输出结果
    for i, news in enumerate(sorted_news[:30], 1):
        print(f"{i}. {news['title']}")
        if news.get('date'):
            print(f"   来源: {news['date']}")
        print()

    # 保存到文件
    output_file = f"今日新闻_20260630_{datetime.now().strftime('%H%M%S')}.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# 今日新闻 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for i, news in enumerate(sorted_news, 1):
            f.write(f"{i}. [{news['title']}]({news.get('link', 'N/A')})\n")
            if news.get('date'):
                f.write(f"   - 来源: {news['date']}\n")
            f.write("\n")

    print(f"\n✅ 已保存到: {output_file}")

if __name__ == "__main__":
    main()
