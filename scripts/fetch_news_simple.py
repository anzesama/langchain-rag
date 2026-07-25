#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
from datetime import datetime
import re

def fetch_google_news():
    try:
        url = "https://news.google.com/rss/search?q=%E4%BB%8A%E6%97%A5%E6%96%B0%E9%97%BB&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.content)
            items = []
            for item in root.findall('.//item'):
                title = item.find('title').text
                link = item.find('link').text
                items.append({'title': title, 'link': link})
            return items
    except:
        pass
    return []

def fetch_bbc_chinese():
    try:
        url = "https://www.bbc.com/zhongwen/simp/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            headlines = re.findall(r'<h3[^>]*><a[^>]*>([^<]+)</a></h3>', resp.text)
            return [{'title': h.strip(), 'link': '', 'date': 'BBC'} for h in headlines[:15]]
    except:
        pass
    return []

def main():
    print("=" * 60)
    print(f"今日新闻采集 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    all_news = []

    print("\n从 Google News 获取新闻...")
    google_news = fetch_google_news()
    if google_news:
        all_news.extend(google_news[:20])
        print(f"获取 {len(google_news)} 条")

    print("\n从 BBC中文网 获取新闻...")
    bbc_news = fetch_bbc_chinese()
    if bbc_news:
        all_news.extend(bbc_news[:10])
        print(f"获取 {len(bbc_news)} 条")

    # 去重
    unique_news = {}
    for news in all_news:
        title = news['title']
        if title not in unique_news:
            unique_news[title] = news

    sorted_news = sorted(unique_news.values(), key=lambda x: x.get('date', ''), reverse=True)

    print(f"\n总计获取 {len(sorted_news)} 条新闻\n")

    for i, news in enumerate(sorted_news[:30], 1):
        print(f"{i}. {news['title']}")
        if news.get('date'):
            print(f"   来源: {news['date']}")
        print()

    # 保存
    output_file = f"今日新闻_20260630_{datetime.now().strftime('%H%M%S')}.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# 今日新闻 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for i, news in enumerate(sorted_news, 1):
            f.write(f"{i}. [{news['title']}]({news.get('link', 'N/A')})\n")
            if news.get('date'):
                f.write(f"   - 来源: {news['date']}\n")
            f.write("\n")

    print(f"\n已保存到: {output_file}")

if __name__ == "__main__":
    main()
