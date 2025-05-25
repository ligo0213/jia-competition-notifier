import os
import json
import requests
from bs4 import BeautifulSoup
import pandas as pd

def send_messages(webhook_url, entries):
    MAX_LEN = 1900
    messages = []
    current_msg = "**🆕 新着公募情報**\n\n"

    for title, link in entries:
        line = f"🔹 {title}\n{link}\n\n"
        if len(current_msg) + len(line) > MAX_LEN:
            messages.append(current_msg)
            current_msg = "**🆕 新着公募情報 続き**\n\n"
        current_msg += line

    if current_msg.strip():
        messages.append(current_msg)

    success_all = True
    for idx, msg in enumerate(messages, 1):
        res = requests.post(webhook_url, json={"content": msg})
        if res.status_code == 204:
            print(f"✅ Discord通知完了（メッセージ{idx}）")
        else:
            print(f"⚠️ Discord通知失敗（メッセージ{idx}）: {res.status_code}")
            success_all = False
    return success_all

def jia_parser(url):
    res = requests.get(url)
    soup = BeautifulSoup(res.text, "html.parser")
    results = []
    for article in soup.find_all("article"):
        a_tag = article.find("a", href=True)
        h2_tag = article.find("h2")
        if a_tag and h2_tag:
            title = h2_tag.get_text(strip=True)
            link = a_tag["href"]
            if not link.startswith("http"):
                link = requests.compat.urljoin(url, link)
            results.append((title, link))
    return results

def mlit_parser(url):
    res = requests.get(url)
    res.encoding = res.apparent_encoding
    soup = BeautifulSoup(res.text, "html.parser")
    results = []
    items = soup.select("ul.js-pullDownFilterContents li.js-pullDownFilterContentsItem")
    for item in items:
        status_span = item.select_one("span.st-news-list__tag")
        if status_span and "募集中" in status_span.text:
            link_tag = item.find("a", href=True)
            if not link_tag:
                continue
            link = link_tag["href"]
            if not link.startswith("http"):
                link = requests.compat.urljoin(url, link)
            title_p = item.select_one("p")
            title = title_p.text.strip() if title_p else "タイトル不明"
            results.append((title, link))
    return results

def generic_parser(url, item_selector, title_selector, link_selector):
    res = requests.get(url)
    soup = BeautifulSoup(res.text, "html.parser")
    results = []
    for item in soup.select(item_selector):
        title_elem = item.select_one(title_selector)
        link_elem = item.select_one(link_selector)
        if not title_elem or not link_elem:
            continue
        title = title_elem.get_text(strip=True)
        link = link_elem.get("href")
        if link and not link.startswith("http"):
            link = requests.compat.urljoin(url, link)
        results.append((title, link))
    return results

def main():
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("❗DISCORD_WEBHOOK_URLが環境変数に設定されていません。")
        return

    df = pd.read_csv("sites_list.csv")
    all_results = []
    for _, row in df.iterrows():
        print(f"📡 {row['サイト名']} の情報を取得中...")
        parser_type = row["パーサータイプ"]
        url = row["URL"]

        if parser_type == "jia_parser":
            results = jia_parser(url)
            print(f"JIAパーサー取得件数: {len(results)}")
        elif parser_type == "mlit_parser":
            results = mlit_parser(url)
            print(f"観光庁パーサー取得件数: {len(results)}")
            for title, link in results:
                print(f"  タイトル: {title}")
        elif parser_type == "generic":
            results = generic_parser(url, row["item_selector"], row["title_selector"], row["link_selector"])
            print(f"汎用パーサー取得件数: {len(results)}")
        else:
            print(f"⚠️ 未知のパーサータイプ: {parser_type}")
            results = []

        print(f"  → {len(results)} 件取得")
        all_results.extend(results)

    posted_file = "posted.json"
    if os.path.exists(posted_file):
        with open(posted_file, "r", encoding="utf-8") as f:
            posted_urls = set(json.load(f))
    else:
        posted_urls = set()

    new_entries = [(t, l) for t, l in all_results if l not in posted_urls]
    if not new_entries:
        print("ℹ️ 新しい情報はありません。")
        return

    if send_messages(webhook_url, new_entries):
        print("Discord通知成功。posted.jsonを更新します。")
        try:
            with open(posted_file, "w", encoding="utf-8") as f:
                json.dump(list(posted_urls.union([link for _, link in new_entries])), f, ensure_ascii=False, indent=2)
            print("✅ posted.jsonを正常に更新しました。")
        except Exception as e:
            print(f"❌ posted.jsonの更新に失敗しました: {e}")
    else:
        print("Discord通知失敗。posted.jsonの更新はスキップします。")

if __name__ == "__main__":
    main()
