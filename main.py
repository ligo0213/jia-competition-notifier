import os
import json
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urlparse, urlunparse
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import sys

webhook_url = "https://discord.com/api/webhooks/1375852715107811368/MoMpF5sA5GJ9EqJKBg0Z2dgFvvDXYE6F5oAnxYXnre0EeVxWBpfGpsnX8wXnAWWIUULD"

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

    success_all = True
    for idx, msg in enumerate(messages, 1):
        res = requests.post(webhook_url, json={"content": msg, "username": bot_name})
        if res.status_code == 204:
            print(f"✅ Discord通知完了（メッセージ{idx}）")
        else:
            print(f"⚠️ Discord通知失敗（メッセージ{idx}）: {res.status_code}")
            success_all = False
    return success_all

def normalize_url(url):
    parsed = urlparse(url)
    clean = parsed._replace(fragment="", query="")
    return urlunparse(clean)

def requests_retry_session(retries=3, backoff_factor=0.5, status_forcelist=(500, 502, 504)):
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session

def jia_parser(url):
    session = requests_retry_session()
    try:
        res = session.get(url)
        res.encoding = res.apparent_encoding
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
    except Exception as e:
        print(f"⚠️ JIAパーサー リクエストエラー: {e}")
        return []

def generic_parser(url, item_selector, title_selector, link_selector, status_selector=None, status_text=None):
    session = requests_retry_session()
    try:
        res = session.get(url)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")
        results = []
        items = soup.select(item_selector)
        if not items:
            print(f"⚠️ item_selector '{item_selector}' に一致する要素が見つかりませんでした。")
        for item in items:
            if status_selector and status_text:
                status_elem = item.select_one(status_selector)
                if not status_elem or status_text not in status_elem.get_text():
                    continue
            title_elem = item.select_one(title_selector)
            link_elem = item.select_one(link_selector)
            if not title_elem or not link_elem:
                continue
            title = title_elem.get_text(strip=True).encode('utf-8', errors='replace').decode('utf-8')
            link = link_elem.get("href")
            if link and not link.startswith("http"):
                link = requests.compat.urljoin(url, link)
            results.append((title, link))
        return results
    except Exception as e:
        print(f"⚠️ generic_parser リクエストエラー: {e}")
        return []

def main():
    test_target = None
    if len(sys.argv) > 2 and sys.argv[1] == "--test":
        test_target = sys.argv[2]

    df = pd.read_csv("sites_list.csv")
    site_results = {}

    for _, row in df.iterrows():
        site_name = row["サイト名"]
        parser_type = row["パーサータイプ"]
        url = row["URL"]

        if test_target and site_name != test_target:
            continue

        print(f"📡 {site_name} の情報を取得中…")

        if parser_type == "jia_parser":
            results = jia_parser(url)
        elif parser_type == "generic":
            results = generic_parser(
                url,
                row["item_selector"],
                row["title_selector"],
                row["link_selector"],
                row.get("status_selector"),
                row.get("status_text")
            )
        else:
            print(f"⚠️ 未知のパーサータイプ: {parser_type}")
            results = []

        print(f"  → {len(results)} 件取得")
        site_results[site_name] = results

    if not site_results:
        print("ℹ️ 新しい情報はありません")
        return

    posted_file = "posted.json"
    if os.path.exists(posted_file):
        with open(posted_file, "r", encoding="utf-8") as f:
            posted_urls = set(normalize_url(u) for u in json.load(f))
    else:
        posted_urls = set()

    filtered_results = {}
    for site_name, entries in site_results.items():
        filtered = [(t, l) for t, l in entries if normalize_url(l) not in posted_urls]
        if filtered:
            filtered_results[site_name] = filtered

    if not filtered_results:
        print("ℹ️ 新しい情報はありません。")
        return

    if send_messages(webhook_url, filtered_results):
        print("Discord通知成功。posted.jsonを更新します。")
        all_new_urls = [normalize_url(link) for entries in filtered_results.values() for _, link in entries]
        posted_urls.update(all_new_urls)
        try:
            with open(posted_file, "w", encoding="utf-8") as f:
                json.dump(list(posted_urls), f, ensure_ascii=False, indent=2)
            print("✅ posted.jsonを正常に更新しました。")
        except Exception as e:
            print(f"❌ posted.jsonの更新に失敗しました: {e}")
    else:
        print("Discord通知失敗。posted.jsonの更新はスキップします。")

if __name__ == "__main__":
    main()
