import os
import json
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urlparse, urlunparse
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import sys

# ✅ Discord Webhook を直接埋め込み
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

# ✅ 専用パーサー定義（必要に応じて追加）

def jia_parser(url):
    session = requests_retry_session()
    try:
        res = session.get(url)
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

def mlit_parser(url):
    session = requests_retry_session()
    try:
        res = session.get(url)
        soup = BeautifulSoup(res.text, "html.parser")
        results = []
        items = soup.select("ul.js-pullDownFilterContents li.js-pullDownFilterContentsItem")
        for item in items:
            status_span = item.select_one("span.st-news-list__tag")
            if status_span and "募集中" in status_span.text:
                link_tag = item.find("a", href=True)
                title_tag = item.select_one("p")
                title = title_tag.text.strip() if title_tag else "タイトル不明"
                link = link_tag["href"] if link_tag else None
                if link and not link.startswith("http"):
                    link = requests.compat.urljoin(url, link)
                results.append((title, link))
        return results
    except Exception as e:
        print(f"⚠️ 観光庁パーサー リクエストエラー: {e}")
        return []

def mext_parser(url):
    session = requests_retry_session()
    try:
        res = session.get(url)
        soup = BeautifulSoup(res.text, "html.parser")
        results = []
        for dl in soup.find_all("dl"):
            dd = dl.find("dd")
            a = dd.find("a", href=True) if dd else None
            if a:
                title = a.get_text(strip=True)
                link = a["href"]
                if not link.startswith("http"):
                    link = requests.compat.urljoin(url, link)
                results.append((title, link))
        return results
    except Exception as e:
        print(f"⚠️ 文科省パーサー リクエストエラー: {e}")
        return []

def tokyo_kosha_parser(url):
    session = requests_retry_session()
    try:
        res = session.get(url)
        soup = BeautifulSoup(res.text, "html.parser")
        results = []
        for a_tag in soup.select("a.bl_support_item"):
            status_div = a_tag.find("div", class_="un_josei_status")
            if status_div and "募集中" in status_div.text:
                title_div = a_tag.find("div", class_="bl_support_item_ttl")
                title = title_div.get_text(strip=True) if title_div else "タイトル不明"
                link = a_tag.get("href")
                if link and not link.startswith("http"):
                    link = requests.compat.urljoin(url, link)
                results.append((title, link))
        return results
    except Exception as e:
        print(f"⚠️ 東京都中小企業振興公社パーサー リクエストエラー: {e}")
        return []

def tokyo_artscouncil_grant_parser(url):
    session = requests_retry_session()
    try:
        res = session.get(url)
        soup = BeautifulSoup(res.text, "html.parser")
        results = []
        sections = soup.select("section.box_harf_02.box_harf_02--support")
        for section in sections:
            title_tag = section.select_one("h2")
            link_tag = section.select_one("a[href]")
            if title_tag and link_tag:
                title = title_tag.get_text(strip=True)
                link = link_tag["href"]
                if not link.startswith("http"):
                    link = requests.compat.urljoin(url, link)
                results.append((title, link))
        return results
    except Exception as e:
        print(f"⚠️ アーツカウンシル東京パーサー リクエストエラー: {e}")
        return []

# ✅ メイン関数

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
        elif parser_type == "mlit_parser":
            results = mlit_parser(url)
        elif parser_type == "mext_parser":
            results = mext_parser(url)
        elif parser_type == "tokyo_kosha_parser":
            results = tokyo_kosha_parser(url)
        elif parser_type == "tokyo_artscouncil_grant_parser":
            results = tokyo_artscouncil_grant_parser(url)
        else:
            print(f"⚠️ 未知のパーサータイプ: {parser_type}")
            results = []

        print(f"  → {len(results)} 件取得")
        site_results[site_name] = results

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
