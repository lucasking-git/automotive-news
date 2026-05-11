import re
import ssl
import time
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

# NHTSA 조회 대상 (한국 부품사 공급 관련 OEM 위주)
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


def fetch_cargokr_individual_recalls(max_days: int = 60) -> list[dict]:
    """car.go.kr 리콜현황(/ri/stat/list.do) 개별 리콜 건별 수집."""
    articles = []
    kst = timezone(timedelta(hours=9))
    cutoff = datetime.now(kst) - timedelta(days=max_days)
    base = "https://www.car.go.kr"
    list_url = f"{base}/ri/stat/list.do"
    seen: set[str] = set()

    def _parse_page(soup) -> bool:
        """li 목록 파싱. 기간 초과 항목이 나오면 False 반환."""
        items = soup.select("ul.board-hrznt-list > li")
        if not items:
            return False
        for item in items:
            a_tag = item.select_one("a[onclick]")
            if not a_tag:
                continue
            m = re.search(r"detailView\('(\w+)'", a_tag.get("onclick", ""))
            if not m:
                continue
            recall_id = m.group(1)
            if recall_id in seen:
                continue

            strong = item.select_one("strong")
            title = strong.get_text(strip=True) if strong else ""
            if not title:
                continue

            # 날짜 추출 (YYYY-MM-DD 형식 meta li에서)
            pub_str = ""
            for li in item.select("ul li"):
                dm = re.match(r"(\d{4}-\d{2}-\d{2})", li.get_text(strip=True))
                if dm:
                    pub_str = dm.group(1)
                    break
            if not pub_str:
                continue

            # 날짜 기준 컷오프
            try:
                y, mo, d = pub_str.split("-")
                pub_dt = datetime(int(y), int(mo), int(d), tzinfo=kst)
                if pub_dt < cutoff:
                    return False  # 이후 페이지는 더 오래된 항목 → 중단
            except ValueError:
                continue

            seen.add(recall_id)
            link = f"{base}/ri/stat/detail.do?recallId={recall_id}&ctype=O"
            articles.append({
                "title":     title,
                "summary":   "",
                "link":      link,
                "published": pub_str,
                "category":  "recall_kr",
            })
        return True

    try:
        # 1페이지 (GET)
        resp = SESSION.get(list_url, timeout=12)
        if resp.status_code != 200:
            raise ValueError(f"HTTP {resp.status_code}")
        soup = BeautifulSoup(resp.text, "lxml")
        keep_going = _parse_page(soup)

        # 2~6페이지 (POST 페이지네이션, 기간 내 항목이 있는 동안)
        for page in range(2, 7):
            if not keep_going:
                break
            resp = SESSION.post(list_url, data={"currentPageNo": str(page)}, timeout=12)
            if resp.status_code != 200:
                break
            soup = BeautifulSoup(resp.text, "lxml")
            keep_going = _parse_page(soup)

        if articles:
            print(f"  [car.go.kr] 개별 리콜 {len(articles)}건 수집")
        else:
            print("  [car.go.kr] 기간 내 개별 리콜 없음 - 통계 방식으로 전환")
    except Exception as ex:
        print(f"  [car.go.kr] 개별 리콜 수집 실패: {ex}")

    return articles


def fetch_cargokr_stats() -> list[dict]:
    """car.go.kr 월별 리콜 통계 (개별 수집 실패 시 폴백)."""
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

        month_label = f"{month:02d}월"
        prev_label  = f"{(month - 1):02d}월" if month > 1 else "12월"

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
    """단일 차종 NHTSA 리콜 조회."""
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
            campaign  = r.get("NHTSACampaignNumber", "")
            component = r.get("Component", "")
            summary   = _clean(r.get("Summary", ""), 250)
            consequence = _clean(r.get("Consequence", ""), 150)
            articles.append({
                "title":     f"[NHTSA] {make} {model} {year} — {component}",
                "summary":   f"{summary} {consequence}".strip(),
                # ✅ 수정: #fragment 방식 → ?nhtsaId= 쿼리 파라미터 방식
                "link":      f"https://www.nhtsa.gov/vehicle-safety/recalls?nhtsaId={campaign}",
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


_RECALL_KW = ["리콜", "시정조치", "결함", "자발적 시정"]

# 부처별 설정: (repCode, 출처 레이블, 키워드 필터)
_MINISTRY_CFG = {
    "A00006": ("국토부", [
        "자동차", "모빌리티", "자율주행", "전기차", "수소차", "친환경차",
        "교통안전", "차량", "리콜", "시정조치",
    ]),
    "A00009": ("환경부", [
        "자동차", "배출", "전기차", "수소차", "내연기관", "탄소", "온실가스",
        "친환경차", "차량", "연비",
    ]),
    "A00012": ("산업부", [
        "자동차", "전기차", "수소차", "자동차산업", "이차전지", "배터리",
        "미래차", "자율주행",
    ]),
}


def fetch_autowein_news(max_days: int) -> list[dict]:
    """아우토바인(autowein.com) RSS - 글로벌 자동차 산업동향."""
    return fetch_rss("news", "https://autowein.com/feed/", max_days)


def _fetch_korea_kr_ministry(rep_code: str, label: str, kw: list[str],
                              max_days: int = 14) -> list[dict]:
    """정책브리핑(korea.kr) 경유 부처 보도자료 수집 (공통 로직)."""
    articles = []
    kst = timezone(timedelta(hours=9))
    cutoff = datetime.now(kst) - timedelta(days=max_days)
    try:
        resp = None
        for attempt in range(3):
            try:
                resp = SESSION.get(
                    "https://www.korea.kr/briefing/pressReleaseList.do",
                    params={"repCode": rep_code, "pageIndex": 1},
                    timeout=15,
                )
                break
            except Exception:
                if attempt < 2:
                    time.sleep(2)
        if resp is None or resp.status_code != 200:
            return articles
        soup = BeautifulSoup(resp.text, "lxml")
        for item in soup.select("div.list_type ul li"):
            link_tag = item.find("a", href=lambda h: h and "pressReleaseView" in h)
            if not link_tag:
                continue
            strong = link_tag.find("strong")
            if not strong:
                continue
            title = strong.get_text(strip=True)
            if kw and not any(k in title for k in kw):
                continue

            href = link_tag.get("href", "")
            link = ("https://www.korea.kr" + href) if href.startswith("/") else href

            pub_str = ""
            for tag in item.find_all(["span", "em", "p"]):
                m = re.match(r"(\d{4}-\d{2}-\d{2})", tag.get_text(strip=True))
                if m:
                    pub_str = m.group(1)
                    try:
                        y, mo, d = pub_str.split("-")
                        pub_dt = datetime(int(y), int(mo), int(d), tzinfo=kst)
                        if pub_dt < cutoff:
                            pub_str = ""
                    except ValueError:
                        pub_str = ""
                    break
            if not pub_str:
                continue

            cat = "recall_kr" if any(k in title for k in _RECALL_KW) else "regulation"
            articles.append({
                "title":     f"[{label}] {title}",
                "summary":   "",
                "link":      link,
                "published": pub_str,
                "category":  cat,
            })
    except Exception as ex:
        print(f"  [경고] {label} 보도자료 수집 실패: {ex}")
    return articles


def fetch_molit_press_releases(max_days: int = 14) -> list[dict]:
    """국토교통부·환경부·산업부 자동차 관련 보도자료 통합 수집."""
    articles = []
    seen: set[str] = set()
    for rep_code, (label, kw) in _MINISTRY_CFG.items():
        for a in _fetch_korea_kr_ministry(rep_code, label, kw, max_days):
            if a["title"] not in seen:
                seen.add(a["title"])
                articles.append(a)
    return articles


def collect_all_news() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {
        cat: [] for cat in ["recall_kr", "recall_us", "news", "regulation"]
    }
    max_days = NEWS_MAX_AGE_DAYS

    print("뉴스 수집 시작...")

    # 1. 오토헤럴드 RSS — 법규는 regulation, 나머지(리콜 기사 포함)는 모두 news
    #    국내 리콜(recall_kr)은 car.go.kr 공식 데이터만 수록
    print("  [오토헤럴드] RSS 수집 중...")
    ah_articles = fetch_rss("news", "https://www.autoherald.co.kr/rss/allArticle.xml", max_days)
    reg_kw = ["법규", "규제", "기준", "인증", "환경부", "국토부", "배출"]
    for a in ah_articles:
        if any(k in a["title"] for k in reg_kw):
            result["regulation"].append({**a, "category": "regulation"})
        else:
            result["news"].append({**a, "category": "news"})
    print(f"  [오토헤럴드] {len(ah_articles)}건")

    # 2. 네이버 뉴스 — recall_kr 쿼리 결과도 news로 이동 (car.go.kr 공식 데이터만 recall_kr)
    print("  [네이버] 검색 수집 중...")
    for category, queries in NAVER_QUERIES.items():
        actual_cat = "news" if category == "recall_kr" else category
        if actual_cat not in result:
            continue
        naver_articles = fetch_naver_news(category, queries, max_days)
        existing = {a["title"] for a in result[actual_cat]}
        for a in naver_articles:
            if a["title"] not in existing:
                result[actual_cat].append({**a, "category": actual_cat})
                existing.add(a["title"])
        print(f"  [네이버/{category}→{actual_cat}] {len(naver_articles)}건")

    # 3. car.go.kr 개별 리콜 공고 (건별)
    print("  [car.go.kr] 개별 리콜 공고 수집 중...")
    cargokr_individual = fetch_cargokr_individual_recalls(max_days=60)
    if cargokr_individual:
        existing = {a["title"] for a in result["recall_kr"]}
        for a in cargokr_individual:
            if a["title"] not in existing:
                result["recall_kr"].append(a)
        print(f"  [car.go.kr] 개별 리콜 {len(cargokr_individual)}건")
    else:
        # 폴백: 월별 통계 카드
        print("  [car.go.kr] 월별 통계로 전환...")
        cargokr_stats = fetch_cargokr_stats()
        existing = {a["title"] for a in result["recall_kr"]}
        for a in cargokr_stats:
            if a["title"] not in existing:
                result["recall_kr"].append(a)
        print(f"  [car.go.kr] 통계 {len(cargokr_stats)}건")

    # 4. NHTSA 미국 리콜
    print("  [NHTSA] 주요 차종 리콜 수집 중 (병렬)...")
    nhtsa = fetch_nhtsa_recalls(max_days=90)
    existing = {a["title"] for a in result["recall_us"]}
    for a in nhtsa:
        if a["title"] not in existing:
            result["recall_us"].append(a)
    print(f"  [NHTSA] {len(nhtsa)}건")

    # 5. 아우토바인 RSS
    print("  [아우토바인] RSS 수집 중...")
    autowein = fetch_autowein_news(max_days)
    existing = {a["title"] for a in result["news"]}
    for a in autowein:
        if a["title"] not in existing:
            result["news"].append(a)
            existing.add(a["title"])
    print(f"  [아우토바인] {len(autowein)}건")

    # 6. 국토교통부 모빌리티·자동차 보도자료
    print("  [국토부] 보도자료 수집 중...")
    molit = fetch_molit_press_releases(max(max_days, 7))
    for a in molit:
        cat = a["category"]
        existing_cat = {x["title"] for x in result[cat]}
        if a["title"] not in existing_cat:
            result[cat].append(a)
    print(f"  [국토부] {len(molit)}건")

    total = sum(len(v) for v in result.values())
    print(f"총 {total}건 수집 완료")
    return result
