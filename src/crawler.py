import re
import ssl
import warnings
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# NHTSA 조회 대상 (주요 OEM - 한국 부품사 공급 관련 브랜드 위주)
NHTSA_VEHICLES = [
    ("Hyundai", "Tucson"),      ("Hyundai", "Santa Fe"),    ("Hyundai", "Elantra"),
    ("Hyundai", "Sonata"),      ("Hyundai", "IONIQ 5"),
    ("Kia",     "Sportage"),    ("Kia",     "Sorento"),      ("Kia",     "K5"),
    ("Kia",     "Telluride"),
    ("Genesis", "GV80"),        ("Genesis", "GV70"),
    ("Toyota",  "Camry"),       ("Toyota",  "RAV4"),         ("Toyota",  "Corolla"),
    ("Honda",   "Accord"),      ("Honda",   "CR-V"),
    ("Ford",    "F-150"),       ("Ford",    "Explorer"),
    ("Chevrolet", "Silverado"), ("Chevrolet", "Equinox"),
    ("BMW",     "X5"),          ("BMW",     "3 Series"),
    ("Mercedes-Benz", "GLE"),   ("Mercedes-Benz", "C-Class"),
    ("Volkswagen", "Tiguan"),
    ("Nissan",  "Rogue"),
    ("Stellantis", "Ram 1500"),
]
NHTSA_YEARS = [2022, 2023, 2024, 2025, 2026]


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


def _parse_nhtsa_date(date_str: str) -> datetime | None:
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


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


def fetch_cargokr_stats() -> list[dict]:
    """car.go.kr 이달/전달 리콜 통계를 요약 카드로 반환."""
    articles = []
    try:
        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst)
        year, month = now.year, now.month

        resp = SESSION.post(
            "https://www.car.go.kr/rs/stats/rcList.do",
            data={"searchYear": str(year), "searchOriginalMakerCode": ""},
            timeout=10,
        )
        soup = BeautifulSoup(resp.text, "lxml")
        tables = soup.select("table")
        if not tables:
            return articles

        # 구조: <tr><th>04월</th><td>건수</td><td>대수</td>...<td>합계</td></tr>
        month_label = f"{month:02d}월"
        prev_label = f"{(month - 1):02d}월" if month > 1 else "12월"

        for row in tables[0].select("tr"):
            th_cells = [th.get_text(strip=True) for th in row.select("th")]
            td_cells = [td.get_text(strip=True) for td in row.select("td")]
            if not th_cells or not td_cells:
                continue
            label = th_cells[0]
            if label not in (month_label, prev_label):
                continue
            if len(td_cells) >= 6:
                title = (
                    f"[car.go.kr] {year}년 {label} 리콜 통계 — "
                    f"국산 {td_cells[0]}건/{td_cells[1]}대, "
                    f"수입 {td_cells[2]}건/{td_cells[3]}대, "
                    f"합계 {td_cells[4]}건/{td_cells[5]}대"
                )
                articles.append({
                    "title":     title,
                    "summary":   "자동차리콜센터(car.go.kr) 공식 월별 리콜 통계입니다.",
                    "link":      "https://www.car.go.kr/ri/stat/list.do",
                    "published": f"{year}-{month:02d}",
                    "category":  "recall_kr",
                })
    except Exception as ex:
        print(f"  [경고] car.go.kr 통계 수집 실패: {ex}")
    return articles


def _fetch_nhtsa_one(make: str, model: str, year: int, cutoff: datetime) -> list[dict]:
    """단일 차종 NHTSA 리콜 조회 (스레드별 독립 세션)."""
    articles = []
    try:
        session = requests.Session()
        session.verify = False
        session.headers.update(HEADERS)

        url = (
            f"https://api.nhtsa.gov/recalls/recallsByVehicle"
            f"?make={requests.utils.quote(make)}"
            f"&model={requests.utils.quote(model)}"
            f"&modelYear={year}"
        )
        resp = session.get(url, timeout=12)
        if resp.status_code != 200:
            return articles
        for r in resp.json().get("results", []):
            pub = _parse_nhtsa_date(r.get("ReportReceivedDate", ""))
            if pub is None or pub < cutoff:
                continue
            campaign = r.get("NHTSACampaignNumber", "")
            component = r.get("Component", "")
            summary = _clean(r.get("Summary", ""), 250)
            consequence = _clean(r.get("Consequence", ""), 150)
            articles.append({
                "title":     f"[NHTSA] {make} {model} {year} — {component}",
                "summary":   f"{summary} {consequence}".strip(),
                "link":      f"https://www.nhtsa.gov/vehicle-safety/recalls#{campaign}",
                "published": pub.strftime("%Y-%m-%d"),
                "category":  "recall_us",
            })
    except Exception:
        pass
    return articles


def fetch_nhtsa_recalls(max_days: int = 90) -> list[dict]:
    """NHTSA 주요 차종 최근 리콜 병렬 수집."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    tasks = [(make, model, year) for make, model in NHTSA_VEHICLES for year in NHTSA_YEARS]

    results: list[dict] = []
    seen: set[str] = set()

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_nhtsa_one, m, mo, y, cutoff): None for m, mo, y in tasks}
        for future in as_completed(futures):
            for article in future.result():
                key = article["title"]
                if key not in seen:
                    seen.add(key)
                    results.append(article)

    results.sort(key=lambda x: x["published"], reverse=True)
    return results


def collect_all_news() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {cat: [] for cat in ["recall_kr", "recall_us", "oem", "regulation"]}
    max_days = NEWS_MAX_AGE_DAYS

    print("뉴스 수집 시작...")

    # 1. 오토헤럴드 RSS
    print("  [오토헤럴드] RSS 수집 중...")
    ah_articles = fetch_rss("recall_kr", "https://www.autoherald.co.kr/rss/allArticle.xml", max_days)
    recall_kw = ["리콜", "결함", "시정조치"]
    reg_kw = ["법규", "규제", "기준", "인증", "환경부", "국토부", "배출"]
    for a in ah_articles:
        t = a["title"]
        if any(k in t for k in recall_kw):
            result["recall_kr"].append(a)
        elif any(k in t for k in reg_kw):
            result["regulation"].append({**a, "category": "regulation"})
        else:
            result["oem"].append({**a, "category": "oem"})
    print(f"  [오토헤럴드] {len(ah_articles)}건")

    # 2. 네이버 뉴스
    print("  [네이버] 검색 수집 중...")
    for category, queries in NAVER_QUERIES.items():
        naver_articles = fetch_naver_news(category, queries, max_days)
        existing = {a["title"] for a in result[category]}
        for a in naver_articles:
            if a["title"] not in existing:
                result[category].append(a)
                existing.add(a["title"])
        print(f"  [네이버/{category}] {len(naver_articles)}건")

    # 3. car.go.kr 이달 리콜 통계
    print("  [car.go.kr] 리콜 통계 수집 중...")
    cargokr = fetch_cargokr_stats()
    existing = {a["title"] for a in result["recall_kr"]}
    for a in cargokr:
        if a["title"] not in existing:
            result["recall_kr"].append(a)
    print(f"  [car.go.kr] {len(cargokr)}건")

    # 4. NHTSA 미국 리콜
    print("  [NHTSA] 주요 차종 리콜 수집 중 (병렬)...")
    nhtsa = fetch_nhtsa_recalls(max_days=90)
    existing = {a["title"] for a in result["recall_us"]}
    for a in nhtsa:
        if a["title"] not in existing:
            result["recall_us"].append(a)
    print(f"  [NHTSA] {len(nhtsa)}건")

    total = sum(len(v) for v in result.values())
    print(f"총 {total}건 수집 완료")
    return result
