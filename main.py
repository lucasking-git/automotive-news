import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.crawler import collect_all_news
from src.report_generator import build_html


def main():
    print("=" * 50)
    print("자동차 산업동향 웹사이트 업데이트")
    print("=" * 50)

    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).strftime("%Y년 %m월 %d일")

    news = collect_all_news()
    html = build_html(news, today)

    docs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
    os.makedirs(docs_dir, exist_ok=True)
    output_path = os.path.join(docs_dir, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    total = sum(len(v) for v in news.values())
    print(f"\n완료: docs/index.html 생성 (총 {total}건)")


if __name__ == "__main__":
    main()
