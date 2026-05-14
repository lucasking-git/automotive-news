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

# NHTSA 조회 대상 (한국 부품사 공급 관련 OEM + 주요 글로벌 OEM 확대)
NHTSA_VEHICLES = [
    ("Hyundai", "Tucson"),      ("Hyundai", "Santa Fe"),    ("Hyundai", "Elantra"),
    ("Hyundai", "Sonata"),      ("Hyundai", "IONIQ 5"),     ("Hyundai", "Palisade"),
    ("Kia",     "Sportage"),    ("Kia",     "Sorento"),      ("Kia",     "K5"),
    ("Kia",     "Telluride"),   ("Kia",     "Carnival"),
    ("Genesis", "GV80"),        ("Genesis", "GV70"),         ("Genesis", "G80"),
    ("Toyota",  "Camry"),       ("Toyota",  "RAV4"),         ("Toyota",  "Corolla"),
    ("Toyota",  "Tacoma"),      ("Toyota",  "Tundra"),       ("Toyota",  "Highlander"),
    ("Toyota",  "4Runner"),     ("Toyota",  "Sequoia"),      ("Toyota",  "Sienna"),
    ("Toyota",  "Prius"),       ("Toyota",  "bZ4X"),         ("Toyota",  "Crown"),
    ("Honda",   "Accord"),      ("Honda",   "CR-V"),         ("Honda",   "Pilot"),
    ("Honda",   "Civic"),       ("Honda",   "Odyssey"),      ("Honda",   "HR-V"),
    ("Honda",   "Passport"),    ("Honda",   "Ridgeline"),
    ("Ford",    "F-150"),       ("Ford",    "Explorer"),     ("Ford",    "Escape"),
    ("Ford",    "Bronco"),      ("Ford",    "Edge"),         ("Ford",    "Expedition"),
    ("Ford",    "F-250"),       ("Ford",    "F-350"),        ("Ford",    "Maverick"),
    ("Ford",    "Ranger"),      ("Ford",    "Mustang"),      ("Ford",    "Transit"),
    ("Ford",    "Bronco Sport"), ("Ford",   "Mustang Mach-E"), ("Ford",  "Transit Connect"),
    ("Ford",    "EcoSport"),
    ("Chevrolet", "Silverado"), ("Chevrolet", "Equinox"),    ("Chevrolet", "Malibu"),
    ("Chevrolet", "Traverse"),  ("Chevrolet", "Tahoe"),      ("Chevrolet", "Colorado"),
    ("Chevrolet", "Suburban"),  ("Chevrolet", "Blazer"),     ("Chevrolet", "Trailblazer"),
    ("Chevrolet", "Bolt EV"),   ("Chevrolet", "Express"),    ("Chevrolet", "Camaro"),
    ("GMC",     "Sierra"),      ("GMC",     "Yukon"),        ("GMC",     "Terrain"),
    ("GMC",     "Canyon"),      ("GMC",     "Acadia"),
    ("Cadillac", "Escalade"),   ("Cadillac", "XT5"),
    ("BMW",     "X5"),          ("BMW",     "3 Series"),     ("BMW",     "X3"),
    ("BMW",     "5 Series"),    ("BMW",     "X7"),
    ("Mercedes-Benz", "GLE"),   ("Mercedes-Benz", "C-Class"), ("Mercedes-Benz", "GLC"),
    ("Mercedes-Benz", "E-Class"),
    ("Volkswagen", "Tiguan"),   ("Volkswagen", "Jetta"),     ("Volkswagen", "Atlas"),
    ("Nissan",  "Rogue"),       ("Nissan",  "Altima"),       ("Nissan",  "Pathfinder"),
    ("Nissan",  "Frontier"),
    ("Subaru",  "Forester"),    ("Subaru",  "Outback"),      ("Subaru",  "Crosstrek"),
    ("Tesla",   "Model 3"),     ("Tesla",   "Model Y"),      ("Tesla",   "Model S"),
    ("Tesla",   "Model X"),
    ("Jeep",    "Grand Cherokee"), ("Jeep", "Wrangler"),     ("Jeep",    "Compass"),
    ("Ram",     "1500"),        ("Ram",     "2500"),
    ("Dodge",   "Charger"),     ("Dodge",   "Durango"),
    ("Chrysler", "Pacifica"),
    ("Stellantis", "Ram 1500"),
    ("Lincoln",  "Navigator"),  ("Lincoln", "Corsair"),
    ("Mazda",   "CX-5"),        ("Mazda",   "CX-9"),        ("Mazda",   "3"),
    ("Volvo",   "XC90"),        ("Volvo",   "XC60"),
    ("Audi",    "Q5"),          ("Audi",    "A4"),           ("Audi",    "Q7"),
    ("Porsche", "Cayenne"),     ("Porsche", "Macan"),
]
NHTSA_YEARS = [2020, 2021, 2022, 2023, 2024, 2025, 2026]

# 제조사 목록 (NHTSA_VEHICLES에서 추출) — 모델 미지정으로 전체 차종 커버
_NHTSA_MAKES = sorted({make for make, _ in NHTSA_VEHICLES})


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
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"):  # NHTSA API returns DD/MM/YYYY
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
            link = f"{base}/ri/stat/list.do"
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


def fetch_cargokr_recall_stats() -> dict:
    """car.go.kr 연도별/월별 리콜 현황 수집 (rs/stats/rcList.do)."""
    stats: dict = {"yearly": [], "monthly": []}
    url = "https://www.car.go.kr/rs/stats/rcList.do"
    month_re = re.compile(r'^\d{2}월$')
    year_re  = re.compile(r'^\d{4}년\*?$')
    total_re = re.compile(r'^계\*?$')

    def _parse_table(soup, patterns: list) -> list:
        rows = []
        for table in soup.select("table")[:1]:
            for row in table.select("tr"):
                ths = [th.get_text(strip=True) for th in row.select("th")]
                tds = [td.get_text(strip=True) for td in row.select("td")]
                if not ths or len(tds) < 6:
                    continue
                label = ths[0]
                if not any(p.match(label) for p in patterns):
                    continue
                rows.append({
                    "label": label,
                    "dom_types": tds[0], "dom_count": tds[1],
                    "imp_types": tds[2], "imp_count": tds[3],
                    "total_types": tds[4], "total_count": tds[5],
                    "is_total": bool(total_re.match(label)),
                })
        return rows

    base_data = {
        "rcType": "", "statType": "", "recallDateFrom": "",
        "recallYear": "", "recallMonth": "0", "organ": "",
    }

    try:
        # 월별 현황 (2026년) — rcType 공백, recallYear=2026
        r1 = SESSION.post(url, data={**base_data, "recallYear": "2026"}, timeout=12)
        if r1.status_code == 200:
            monthly = _parse_table(BeautifulSoup(r1.text, "lxml"), [month_re, total_re])
            if monthly:
                stats["monthly"] = monthly
                print(f"  [car.go.kr 현황] 월별 {len(monthly)}행 수집")

        # 연도별 현황 (2025~2026) — rcType=Y, recallYear=2025 (시작연도)
        r2 = SESSION.post(url, data={**base_data, "rcType": "Y", "recallYear": "2025"}, timeout=12)
        if r2.status_code == 200:
            yearly = _parse_table(BeautifulSoup(r2.text, "lxml"), [year_re, total_re])
            if yearly:
                stats["yearly"] = yearly
                print(f"  [car.go.kr 현황] 연도별 {len(yearly)}행 수집")

    except Exception as ex:
        print(f"  [car.go.kr 현황] 수집 실패: {ex}")

    return stats


def _fetch_nhtsa_one(
    make: str, model: str, year: int, article_cutoff: datetime
) -> tuple[list[dict], list[tuple[str, str]]]:
    """단일 차종 NHTSA 리콜 조회.

    Returns:
        articles: article_cutoff 이후 리콜 기사
        campaigns: 현재연도 캠페인 [(campaign_id, manufacturer), ...]
    """
    articles: list[dict] = []
    campaigns: list[tuple[str, str]] = []
    cur_year_prefix = f"{datetime.now(timezone.utc).year % 100:02d}V"
    try:
        s = requests.Session()
        s.verify = False
        s.headers.update(HEADERS)
        url = (
            f"https://api.nhtsa.gov/recalls/recallsByVehicle"
            f"?make={requests.utils.quote(make)}"
            f"&model={requests.utils.quote(model)}"
            f"&modelYear={year}"
        )
        resp = s.get(url, timeout=15)
        if resp.status_code != 200:
            return articles, campaigns
        for r in resp.json().get("results", []):
            campaign     = r.get("NHTSACampaignNumber", "")
            manufacturer = r.get("Manufacturer", make)

            # 현재연도 캠페인 → 제조사 통계용
            if campaign.startswith(cur_year_prefix):
                campaigns.append((campaign, manufacturer))

            # 기사 수집 (날짜 필터)
            pub = _parse_nhtsa_date(r.get("ReportReceivedDate", ""))
            if pub is None or pub < article_cutoff:
                continue
            component   = r.get("Component", "")
            summary     = _clean(r.get("Summary", ""), 250)
            consequence = _clean(r.get("Consequence", ""), 150)
            articles.append({
                "title":     f"[NHTSA] {make} {model} {year} — {component}",
                "summary":   f"{summary} {consequence}".strip(),
                "link":      f"https://www.nhtsa.gov/vehicle-safety/recalls?nhtsaId={campaign}",
                "published": pub.strftime("%Y-%m-%d"),
                "category":  "recall_us",
            })
    except Exception:
        pass
    return articles, campaigns


def fetch_nhtsa_data(max_days: int = 90) -> tuple[list[dict], list[dict]]:
    """NHTSA 주요 차종 최근 리콜 기사 + 현재연도 제조사 통계 동시 수집.

    Returns: (articles, mfr_stats_top12)
    """
    from collections import defaultdict

    article_cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    tasks = [(make, model, year) for make, model in NHTSA_VEHICLES for year in NHTSA_YEARS]
    print(f"  [NHTSA] {len(tasks)}개 차종×연도 병렬 조회 중...")

    all_articles: list[dict] = []
    seen_link: set[str] = set()
    seen_campaign: set[str] = set()
    mfr_counts: dict[str, int] = defaultdict(int)

    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {
            executor.submit(_fetch_nhtsa_one, m, mo, y, article_cutoff): None
            for m, mo, y in tasks
        }
        for future in as_completed(futures):
            articles, campaigns = future.result()
            for item in articles:
                if item["link"] not in seen_link:
                    seen_link.add(item["link"])
                    all_articles.append(item)
            for camp_id, mfr in campaigns:
                if camp_id not in seen_campaign:
                    seen_campaign.add(camp_id)
                    mfr_counts[mfr] += 1

    sorted_articles = sorted(all_articles, key=lambda x: x["published"], reverse=True)
    mfr_stats = sorted(
        [{"manufacturer": k, "recalls": v} for k, v in mfr_counts.items()],
        key=lambda x: x["recalls"],
        reverse=True,
    )[:12]

    print(f"  [NHTSA] 기사 {len(sorted_articles)}건, 캠페인 {len(seen_campaign)}개")
    return sorted_articles, mfr_stats


def fetch_nhtsa_recall_stats() -> dict:
    """NHTSA 연도별/월별/제조사별 리콜 현황 수집 (루트 API).

    루트 API를 페이지 순회하여 현재연도 + 전년도 캠페인을 집계한다.
    Returns:
        {
          "yearly":  [{"year": 2025, "count": N}, {"year": 2026, "count": N}],
          "monthly": [{"month": 1, "count": N}, ...],   # 현재연도 월별
          "mfr":     [{"manufacturer": "...", "recalls": N}, ...]  # Top 12
        }
    API 실패 시 빈 구조 반환 → collect_all_news에서 차종별 통계로 보완.
    """
    from collections import defaultdict

    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    cur_year = now.year
    prev_year = cur_year - 1
    cur_month = now.month

    cur_prefix  = f"{cur_year  % 100:02d}V"
    prev_prefix = f"{prev_year % 100:02d}V"

    seen_cur:  set[str] = set()
    seen_prev: set[str] = set()
    monthly_counts: dict[int, int] = defaultdict(int)
    mfr_counts:     dict[str, int] = defaultdict(int)

    s = requests.Session()
    s.verify = False
    s.headers.update(HEADERS)

    offset = 0
    page_size = 1000
    max_pages = 12

    print(f"  [NHTSA 현황] {cur_year}/{prev_year}년 통계 수집 중...")
    for _ in range(max_pages):
        try:
            resp = s.get(
                "https://api.nhtsa.gov/recalls/",
                params={"offset": offset, "max": page_size},
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"  [NHTSA 현황] 루트 API {resp.status_code}")
                break
            results = resp.json().get("results", [])
            if not results:
                break

            too_old = False
            for rec in results:
                camp = rec.get("campaignId", "")
                mfr  = rec.get("manufacturerName", "")

                m = re.match(r"(\d{2})V", camp)
                if not m:
                    continue
                yy = int(m.group(1))
                camp_year = 2000 + yy if yy <= 50 else 1900 + yy

                if camp_year == cur_year:
                    if camp not in seen_cur:
                        seen_cur.add(camp)
                        mfr_counts[mfr] += 1
                        # ISO 8601 날짜 파싱 (예: "2026-05-11T18:11:52Z")
                        raw_date = rec.get("recall573ReceivedDate", "") or rec.get("createDate", "")
                        try:
                            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                            monthly_counts[dt.month] += 1
                        except Exception:
                            pass
                elif camp_year == prev_year:
                    if camp not in seen_prev:
                        seen_prev.add(camp)
                elif camp_year < prev_year:
                    too_old = True

            if too_old:
                break
            offset += len(results)
        except Exception as ex:
            print(f"  [NHTSA 현황] 수집 오류: {ex}")
            break

    mfr_stats = sorted(
        [{"manufacturer": k, "recalls": v} for k, v in mfr_counts.items()],
        key=lambda x: x["recalls"],
        reverse=True,
    )[:12]

    print(f"  [NHTSA 현황] {cur_year}년: {len(seen_cur)}건, {prev_year}년: {len(seen_prev)}건")
    return {
        "yearly": [
            {"year": prev_year, "count": len(seen_prev)},
            {"year": cur_year,  "count": len(seen_cur)},
        ],
        "monthly": [
            {"month": m, "count": monthly_counts.get(m, 0)}
            for m in range(1, cur_month + 1)
        ],
        "mfr": mfr_stats,
    }


_KATECH_LIST_URL = "https://www.katech.re.kr/page/07090450-89fd-4a3f-8373-ee74cbb3e738"


def fetch_katech_reports(max_items: int = 10) -> list[dict]:
    """KATECH 산업분석 레포트 목록 수집 (최근 max_items개).

    각 행의 data-post_key UUID를 이용해 상세 URL을 구성한다.
    상세 URL: /page/{LIST_UUID}?ac=view&post={post_key}&page=1
    """
    base_url = "https://www.katech.re.kr"
    articles: list[dict] = []
    try:
        resp = SESSION.get(_KATECH_LIST_URL, timeout=15)
        if resp.status_code != 200:
            print(f"  [KATECH] HTTP {resp.status_code}")
            return articles
        soup = BeautifulSoup(resp.content, "lxml")
        for row in soup.select("table tbody tr"):
            post_key = row.get("data-post_key", "")
            if not post_key:
                continue
            title_tag = row.select_one("a.view_btn")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            if not title:
                continue
            tds = row.select("td")
            pub = tds[2].get_text(strip=True) if len(tds) > 2 else ""
            link = (
                f"{base_url}/page/07090450-89fd-4a3f-8373-ee74cbb3e738"
                f"?ac=view&post={post_key}&page=1"
            )
            articles.append({
                "title":     title,
                "summary":   "",
                "link":      link,
                "published": pub,
                "category":  "katech",
            })
            if len(articles) >= max_items:
                break
        print(f"  [KATECH] {len(articles)}건 수집")
    except Exception as ex:
        print(f"  [KATECH] 수집 실패: {ex}")
    return articles


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


def collect_all_news() -> tuple[dict[str, list[dict]], dict]:
    """뉴스·리콜 데이터 수집.

    반환: (news_by_category, nhtsa_recall_stats)
      - news_by_category:  카테고리별 기사 dict
      - nhtsa_recall_stats: {yearly, monthly, mfr} 미국 NHTSA 리콜 현황
    """
    result: dict[str, list[dict]] = {
        cat: [] for cat in ["recall_kr", "recall_us", "news", "regulation", "katech"]
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

    # 4. NHTSA 미국 리콜 기사 + 차종별 제조사 통계 동시 수집
    nhtsa_articles, vehicle_mfr_stats = fetch_nhtsa_data(max_days=90)
    existing = {a["title"] for a in result["recall_us"]}
    for a in nhtsa_articles:
        if a["title"] not in existing:
            result["recall_us"].append(a)

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

    # 7. NHTSA 연도별/월별/제조사 현황 (루트 API → 실패 시 차종별 통계로 보완)
    nhtsa_recall_stats = fetch_nhtsa_recall_stats()
    if not nhtsa_recall_stats.get("mfr") and vehicle_mfr_stats:
        nhtsa_recall_stats["mfr"] = vehicle_mfr_stats
        print(f"  [NHTSA 현황] 제조사 통계: 차종별 집계 {len(vehicle_mfr_stats)}개 사용")

    # 8. KATECH 산업분석 레포트
    print("  [KATECH] 산업분석 레포트 수집 중...")
    katech_articles = fetch_katech_reports(max_items=10)
    result["katech"] = katech_articles

    total = sum(len(v) for v in result.values())
    print(f"총 {total}건 수집 완료")
    return result, nhtsa_recall_stats
