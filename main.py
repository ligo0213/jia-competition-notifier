# main.py（強化版 + Webhookハードコード）

import os
import json
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urlparse, urlunparse
import argparse

def normalize_url(url):
    parsed = urlparse(url)
    clean = parsed._replace(fragment="", query="")
    return urlunparse(clean)

def send_messages(webhook_url, site_entries_dict, bot_name="公募情報"):
    MAX_LEN = 1900
    messages = []
    current_msg = "**新着情報**\n\n"

    for site_name, entries in site_entries_dict.items():
        current_msg += f"◇{site_name}\n"
        for title, link in entries:
            line = f"・{title}\n{link}\n"
            if len(current_msg) + len(line) > MAX_LEN:
                messages.append(current_msg)
                current_msg = ""
            current_msg += line
        current_msg += "\n"

    if current_msg.strip():
        messages.append(current_msg)

    success = True
    for i, msg in enumerate(messages, 1):
        res = requests.post(webhook_url, json={"content": msg, "username": bot_name})
        if res.status_code == 204:
            print(f"✅ Discord通知完了（{i}）")
        else:
            print(f"⚠️ Discord通知失敗（{i}）: {res.status_code}")
            success = False
    return success

def generic_parser(url, item_sel, title_sel, link_sel, status_sel=None, status_text=None):
    res = requests.get(url)
    res.encoding = res.apparent_encoding
    soup = BeautifulSoup(res.text, "html.parser")
    results = []
    items = soup.select(item_sel)
    if not items:
        print(f"⚠️ item_selector '{item_sel}' が一致しません")
    for item in items:
        if status_sel and status_text:
            status = item.select_one(status_sel)
            if not status or status_text not in status.get_text():
                continue
        title_elem = item.select_one(title_sel)
        link_elem = item.select_one(link_sel)
        if not title_elem or not link_elem:
            continue
        title = title_elem.get_text(strip=True).encode('utf-8', errors='replace').decode('utf-8')
        link = link_elem.get("href")
        if link and not link.startswith("http"):
            link = requests.compat.urljoin(url, link)
        results.append((title, link))
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", help="特定のサイト名だけ処理")
    args = parser.parse_args()

    # 🔐 Webhook URL をハードコード
    webhook_url = "https://discord.com/api/webhooks/1375852715107811368/MoMpF5sA5GJ9EqJKBg0Z2dgFvvDXYE6F5oAnxYXnre0EeVxWBpfGpsnX8wXnAWWIUULD"

    df = pd.read_csv("sites_list.csv")
    if args.test:
        df = df[df["サイト名"] == args.test]
        if df.empty:
            print(f"❗サイト '{args.test}' が見つかりません")
            return

    posted_file = "posted.json"
    if os.path.exists(posted_file):
        with open(posted_file, "r", encoding="utf-8") as f:
            posted_urls = set(normalize_url(u) for u in json.load(f))
    else:
        posted_urls = set()

    all_new = {}
    for _, row in df.iterrows():
        name, url, parser_type = row["サイト名"], row["URL"], row["パーサータイプ"]
        print(f"📡 {name} の情報を取得中…")

        if parser_type == "generic":
            results = generic_parser(
                url,
                row.get("item_selector", ""),
                row.get("title_selector", ""),
                row.get("link_selector", ""),
                row.get("status_selector", None),
                row.get("status_text", None)
            )
        else:
            print(f"⚠️ 未知のパーサータイプ: {parser_type}")
            results = []

        filtered = [(t, l) for t, l in results if normalize_url(l) not in posted_urls]
        print(f"  → {len(filtered)} 件取得")
        if filtered:
            all_new[name] = filtered

    if not all_new:
        print("ℹ️ 新しい情報はありません")
        return

    if send_messages(webhook_url, all_new):
        print("✅ Discord通知成功。posted.jsonを更新します")
        new_links = [normalize_url(l) for entries in all_new.values() for _, l in entries]
        posted_urls.update(new_links)
        with open(posted_file, "w", encoding="utf-8") as f:
            json.dump(list(posted_urls), f, ensure_ascii=False, indent=2)
        print("✅ posted.json更新完了")
    else:
        print("❌ Discord通知失敗。posted.jsonは更新されません")

if __name__ == "__main__":
    main()
