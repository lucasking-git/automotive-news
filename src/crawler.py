import re
import ssl
import warnings
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen
from urllib.error import URLError
import urllib.request

from src.config import NAVER_QUERIES, NEWS_MAX_AGE_DAYS

warnings.filterwarnings("ignore", message="Unverified HTTPS request")
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update(HEADERS)


def _parse_date(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            return datetime(*val[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _is_recent(pub_date: datetime, max_days: int) -> bool:
    return pub_date >= datetime.now(timezone.utc) - timedelta(days=max_days)


def _clean(text: str, max_len: int = 200) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = " ".join(text.split())
    return text[:max_len] + "..." if len(text) > max_len else text


def fetch_rss(category: str, url: str, max_days: int) -> list[dict]:
    articles = []
    try:
        https_handler = urllib.request.HTTPSHandler(context=SSL_CTX)
        opener = urllib.request.build_opener(https_handler)
        response = opener.open(url, timeout=15)
        content = response.read()
        feed = feedparser.parse(content)
        for e in feed.entries:
            pub = _parse_date(e)
            if not _is_recent(pub, max_days):
                continue
            articles.append({
                "title":     e.get("title", "").strip(),
                "summary":   _clean(e.get("summary", e.get("description", ""))),
                "link":      e.get("link", ""),
                "published": pub.strftime("%Y-%m-%d %H:%M"),
                "category":  category,
            })
    except Exception as ex:
        print(f"  [경고] RSS 실패 ({url[:50]}): {ex}")
    return articles


def fetch_naver_news(category: str, queries: list[str], max_days: int) -> list[dict]:
    articles = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    start_date = cutoff.strftime("%Y.%m.%d")
    end_date = datetime.now().strftime("%Y.%m.%d")

    for query in queries:
        try:
            url = (
                "https://search.naver.com/search.naver"
                f"?where=news&query={requests.utils.quote(query)}"
                f"&sort=1&ds={start_date}&de={end_date}"
            )
            resp = SESSION.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, "lxml")
            for item in soup.select("div.news_area")[:8]:
                title_tag = item.select_one("a.news_tit")
                desc_tag = item.select_one(".dsc_wrap") or item.select_one(".news_contents")
                date_tag = item.select_one(".info_group span.info") or item.select_one("span.date")
                if not title_tag:
                    continue
                articles.append({
                    "title":     title_tag.get_text(strip=True),
                    "summary":   _clean(desc_tag.get_text() if desc_tag else ""),
                    "link":      title_tag.get("href", ""),
                    "published": date_tag.get_text(strip=True) if date_tag else "",
                    "category":  category,
                })
        except Exception as ex:
            print(f"  [경고] 네이버 검색 실패 ({query}): {ex}")

    seen: set[str] = set()
    return [a for a in articles if a["title"] not in seen and not seen.add(a["title"])]


def fetch_molit_recalls(max_days: int) -> list[dict]:
    articles = []
    url = "https://www.car.go.kr/home/main.do"
    try:
        resp = SESSION.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")
        for row in soup.select("table tbody tr")[:10]:
            cols = row.select("td")
            if len(cols) < 3:
                continue
            title = cols[1].get_text(strip=True) if len(cols) > 1 else ""
            date = cols[-1].get_text(strip=True)
            link_tag = cols[1].select_one("a")
            link = "https://www.car.go.kr" + link_tag["href"] if link_tag and link_tag.get("href") else url
            if title:
                articles.append({
                    "title":     f"[국토부 리콜] {title}",
                    "summary":   "",
                    "link":      link,
                    "published": date,
                    "category":  "recall_kr",
                })
    except Exception as ex:
        print(f"  [경고] 국토부 리콜 수집 실패: {ex}")
    return articles


def collect_all_news() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {cat: [] for cat in ["recall_kr", "recall_us", "oem", "regulation"]}
    max_days = NEWS_MAX_AGE_DAYS

    print("뉴스 수집 시작...")

    print("  [오토헤럴드] RSS 수집 중...")
    ah_articles = fetch_rss("recall_kr", "https://www.autoherald.co.kr/rss/allArticle.xml", max_days)
    recall_kw = ["리콜", "결함", "시정조치"]
    reg_kw = ["법규", "규제", "기준", "인증", "환경부", "국토부", "배출"]
    oem_kw = ["현대", "기아", "BMW", "벤츠", "도요타", "폭스바겐", "GM", "포드"]
    for a in ah_articles:
        t = a["title"]
        if any(k in t for k in recall_kw):
            result["recall_kr"].append(a)
        elif any(k in t for k in reg_kw):
            result["regulation"].append({**a, "category": "regulation"})
        else:
            result["oem"].append({**a, "category": "oem"})
    print(f"  [오토헤럴드] {len(ah_articles)}건")

    print("  [네이버] 검색 수집 중...")
    for category, queries in NAVER_QUERIES.items():
        naver_articles = fetch_naver_news(category, queries, max_days)
        existing = {a["title"] for a in result[category]}
        for a in naver_articles:
            if a["title"] not in existing:
                result[category].append(a)
                existing.add(a["title"])
        print(f"  [네이버/{category}] {len(naver_articles)}건")

    print("  [국토부] 리콜 공고 수집 중...")
    molit = fetch_molit_recalls(max_days)
    existing = {a["title"] for a in result["recall_kr"]}
    for a in molit:
        if a["title"] not in existing:
            result["recall_kr"].append(a)
    print(f"  [국토부] {len(molit)}건")

    total = sum(len(v) for v in result.values())
    print(f"총 {total}건 수집 완료")
    return result
