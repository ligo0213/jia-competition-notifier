import os
import requests
from bs4 import BeautifulSoup
import json

webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

url = "https://www.jia.or.jp/competition/"
res = requests.get(url)
soup = BeautifulSoup(res.text, "html.parser")

competitions = []
for article in soup.find_all("article"):
    a_tag = article.find("a", href=True)
    h2_tag = article.find("h2")
    if a_tag and h2_tag:
        title = h2_tag.get_text(strip=True)
        link = a_tag["href"]
        competitions.append((title, link))

if os.path.exists("posted.json"):
    with open("posted.json", "r", encoding="utf-8") as f:
        posted = json.load(f)
else:
    posted = []

new_competitions = [(title, link) for title, link in competitions if link not in posted]

if new_competitions:
    content = "**🧱 JIA 新着コンペ情報**\n\n"
    for title, link in new_competitions:
        content += f"🔹 {title}\n{link}\n\n"

    res = requests.post(webhook_url, json={"content": content})
    if res.status_code == 204:
        print("✅ 投稿完了")
        posted.extend([link for _, link in new_competitions])
        with open("posted.json", "w", encoding="utf-8") as f:
            json.dump(posted, f, ensure_ascii=False, indent=2)
    else:
        print(f"⚠️ エラー: {res.status_code}")
else:
    print("ℹ️ 新しいコンペ情報はありません。")
