import re
import hashlib
from src.config import CATEGORY_LABELS, CATEGORY_COLORS, CATEGORY_ICONS, SITE_PASSWORD

DATE_VISIBLE = 5  # 날짜 그룹별 기본 표시 건수 (초과분은 접기)

_STAT_RE = re.compile(
    r'(\d{4})년\s*(\d{2})월 리콜 통계 — '
    r'국산 ([\d,]+)건/([\d,]+)대, '
    r'수입 ([\d,]+)건/([\d,]+)대, '
    r'합계 ([\d,]+)건/([\d,]+)대'
)

# 국기는 flagcdn.com img 태그 사용 (Linux 서버에서 국기 이모지 미지원 문제 해결)
_FLAG_IMG = {
    "recall_kr": '<img src="https://flagcdn.com/20x15/kr.png" alt="KR" class="flag-img">',
    "recall_us": '<img src="https://flagcdn.com/20x15/us.png" alt="US" class="flag-img">',
}

# ── CSS ──────────────────────────────────────────────────────────────────────
_CSS = """
:root{
  --brand:#00ADE9;--brand-dk:#0066B2;--brand-dkk:#003B6F;
  --bg:#f0f8fd;--surface:#ffffff;
  --text-1:#0f172a;--text-2:#475569;--text-3:#94a3b8;--border:#dbeafe;
  --sh:0 4px 12px rgba(0,102,178,.08);--sh-lg:0 12px 28px rgba(0,102,178,.14);
  --r:12px;--r-sm:8px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Malgun Gothic","Apple SD Gothic Neo",Arial,sans-serif;background:var(--bg);color:var(--text-1);min-height:100vh;line-height:1.6}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#93c5fd;border-radius:3px}

/* Gate */
#gate{position:fixed;inset:0;background:linear-gradient(145deg,#001a33 0%,#003B6F 45%,#00264d 100%);display:flex;align-items:center;justify-content:center;z-index:999}
#gate::before{content:'';position:absolute;inset:0;background-image:radial-gradient(rgba(0,173,233,.18) 1px,transparent 1px);background-size:28px 28px;mask-image:radial-gradient(ellipse 70% 70% at 50% 50%,black 40%,transparent 100%);pointer-events:none}
.gate-card{position:relative;z-index:1;background:rgba(255,255,255,.06);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);border:1px solid rgba(0,173,233,.2);border-radius:20px;padding:48px 40px;width:400px;text-align:center;animation:cardUp .5s cubic-bezier(.34,1.56,.64,1) both}
@keyframes cardUp{from{opacity:0;transform:translateY(24px) scale(.96)}to{opacity:1;transform:translateY(0) scale(1)}}
.gate-emblem{width:72px;height:72px;background:linear-gradient(135deg,#00ADE9 0%,#0055A4 100%);border-radius:18px;margin:0 auto 18px;display:flex;align-items:center;justify-content:center;font-size:32px;box-shadow:0 8px 28px rgba(0,173,233,.5)}
.gate-logo{font-size:22px;font-weight:800;color:#fff;letter-spacing:-.4px;margin-bottom:4px}
.gate-brand{font-size:11.5px;color:#00ADE9;font-weight:700;letter-spacing:1.2px;margin-bottom:8px}
.gate-sub{font-size:12.5px;color:rgba(255,255,255,.45);margin-bottom:36px;line-height:1.65}
.gate-label{font-size:11px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:rgba(255,255,255,.5);text-align:left;margin-bottom:8px}
.gate-input{width:100%;padding:13px 16px;background:rgba(255,255,255,.07);border:1.5px solid rgba(0,173,233,.22);border-radius:var(--r-sm);font-size:15px;color:#fff;outline:none;letter-spacing:2px;transition:border-color .2s,background .2s}
.gate-input::placeholder{color:rgba(255,255,255,.28);letter-spacing:normal}
.gate-input:focus{border-color:#00ADE9;background:rgba(0,173,233,.1)}
.gate-btn{width:100%;margin-top:14px;padding:14px;background:linear-gradient(135deg,#00ADE9,#0055A4);color:#fff;border:none;border-radius:var(--r-sm);font-size:15px;font-weight:700;cursor:pointer;box-shadow:0 4px 16px rgba(0,173,233,.4);transition:transform .15s,box-shadow .15s}
.gate-btn:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,173,233,.55)}
.gate-btn:active{transform:translateY(0)}
.gate-err{margin-top:12px;font-size:13px;color:#f87171;display:none;animation:shake .35s}
@keyframes shake{0%,100%{transform:translateX(0)}25%{transform:translateX(-6px)}75%{transform:translateX(6px)}}

/* Main */
#main{display:none;animation:fadeUp .4s ease both}
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}

/* Header */
header{background:linear-gradient(135deg,#003B6F 0%,#0066B2 100%);color:#fff;padding:16px 24px;position:sticky;top:0;z-index:100;box-shadow:0 2px 20px rgba(0,50,120,.4)}
.header-inner{max-width:1000px;margin:0 auto;display:flex;align-items:center;gap:14px}
.header-icon{width:46px;height:46px;flex-shrink:0;background:linear-gradient(135deg,#00ADE9,#0055A4);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:22px;box-shadow:0 4px 14px rgba(0,173,233,.45)}
.header-title{font-size:18px;font-weight:800;letter-spacing:-.4px}
.header-org{font-size:12px;color:#00ADE9;font-weight:700;letter-spacing:.4px;margin-top:2px}
.header-meta{font-size:11px;color:rgba(255,255,255,.4);margin-top:1px}

/* Nav */
nav{background:var(--surface);border-bottom:2.5px solid #00ADE9;overflow-x:auto;white-space:nowrap;scrollbar-width:none}
nav::-webkit-scrollbar{display:none}
.nav-inner{max-width:1000px;margin:0 auto;display:flex;padding:0 16px}
.nav-link{display:inline-flex;align-items:center;gap:6px;padding:13px 15px;font-size:13px;font-weight:600;color:var(--text-2);text-decoration:none;border-bottom:2.5px solid transparent;transition:color .15s,border-color .15s;white-space:nowrap}
.nav-link:hover{color:var(--c);border-bottom-color:var(--c)}
.nav-count{font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px;background:#e8f4fd;color:var(--text-3);transition:background .15s,color .15s}
.nav-link:hover .nav-count{background:rgba(0,173,233,.12);color:var(--c)}
.flag-img{width:20px;height:15px;border-radius:2px;vertical-align:middle;object-fit:cover}

/* Main content */
main{max-width:1000px;margin:28px auto;padding:0 20px 72px}

/* Section */
.section{background:var(--surface);border-radius:var(--r);margin-bottom:24px;box-shadow:var(--sh);overflow:hidden;transition:box-shadow .2s;border-left:4px solid var(--sec-c,#00ADE9)}
.section:hover{box-shadow:var(--sh-lg)}
.section-header{display:flex;align-items:center;gap:12px;padding:17px 22px 15px;border-bottom:1px solid var(--border);cursor:pointer;user-select:none;transition:background .15s}
.section-header:hover{background:#f7fbff}
.section-icon{width:38px;height:38px;border-radius:10px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:20px;background:rgba(0,173,233,.07)}
.section-icon .flag-img{width:28px;height:21px;border-radius:3px}
.section-title{font-size:15px;font-weight:700;flex:1}
.section-badge{font-size:11px;font-weight:700;padding:4px 11px;border-radius:20px;color:#fff}
.sec-toggle{font-size:13px;color:var(--text-3);margin-left:4px;transition:transform .25s}

/* Date separator */
.date-sep{display:flex;align-items:center;gap:10px;padding:10px 22px 4px}
.date-sep::before,.date-sep::after{content:'';flex:1;height:1px;background:var(--border)}
.date-sep span{font-size:11px;font-weight:700;color:var(--text-3);background:#f0f8fd;border:1px solid var(--border);border-radius:20px;padding:2px 12px;white-space:nowrap}

/* Cards */
.cards-list{padding:4px 0}
.card{padding:15px 22px;border-bottom:1px solid #f0f8fd;transition:background .15s}
.card:last-child{border-bottom:none}
.card:hover{background:#f5faff}
.card-meta{display:flex;align-items:center;gap:7px;margin-bottom:7px;flex-wrap:wrap}
.card-date{display:inline-flex;align-items:center;font-size:11px;color:var(--text-3);background:#f0f8fd;border-radius:4px;padding:2px 8px}
.card-source{font-size:11px;color:#94a3b8;background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:2px 8px}
.card-title{font-size:14px;font-weight:600;line-height:1.55;text-decoration:none;display:block;transition:opacity .15s}
.card-title:hover{text-decoration:underline;text-underline-offset:2px;text-decoration-thickness:1px}
.card-summary{font-size:12.5px;color:var(--text-2);line-height:1.7;margin-top:6px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card-summary.expanded{display:block;-webkit-line-clamp:unset}
.more-btn{font-size:12px;font-weight:600;padding:3px 0;margin-top:5px;background:none;border:none;cursor:pointer;display:inline-block;opacity:.6;transition:opacity .15s}
.more-btn:hover{opacity:1}

/* car.go.kr 통계 카드 (폴백용) */
.recall-stat-card{padding:16px 22px;border-bottom:1px solid #f0f8fd}
.recall-stat-title{font-size:14px;font-weight:700;margin-bottom:10px}
.recall-stat-grid{display:flex;gap:10px;flex-wrap:wrap}
.recall-stat-item{background:#f0f8fd;border:1px solid #bee3f8;border-radius:8px;padding:10px 16px;text-align:center;flex:1;min-width:90px}
.rs-label{font-size:11px;color:var(--text-3);margin-bottom:2px}
.rs-value{font-size:17px;font-weight:800;color:#0066B2}
.rs-sub{font-size:11px;color:var(--text-2);margin-top:2px}
.recall-detail-link{display:inline-block;margin-top:10px;font-size:12.5px;font-weight:600;color:#00ADE9;text-decoration:none}
.recall-detail-link:hover{text-decoration:underline}

/* Expand / Collapse */
.cards-extra{display:none}
.cards-extra.open{display:block}
.expand-bar{display:flex;align-items:center;justify-content:center;gap:6px;padding:10px 22px 14px;width:100%;border:none;background:none;cursor:pointer;font-size:13px;font-weight:600;border-top:1px solid var(--border);transition:background .15s}
.expand-bar:hover{background:#f0f8fd}
.date-expand-bar{width:fit-content;margin:8px auto 12px;padding:7px 26px;font-size:12.5px;font-weight:700;background:#f0f8fd;border:1.5px solid currentColor;border-radius:20px;border-top:1.5px solid currentColor;transition:background .15s,box-shadow .15s}
.date-expand-bar:hover{background:#dbeafe;box-shadow:0 2px 10px rgba(0,102,178,.15)}

/* Empty */
.empty-state{padding:44px 24px;text-align:center}
.empty-icon{font-size:36px;margin-bottom:10px;opacity:.3}
.empty-text{font-size:13px;color:var(--text-3)}

/* Scroll top */
#scrollTop{position:fixed;bottom:28px;right:28px;width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,#00ADE9,#0055A4);color:#fff;border:none;cursor:pointer;font-size:18px;display:none;align-items:center;justify-content:center;box-shadow:0 12px 28px rgba(0,102,178,.14);transition:transform .2s;z-index:50}
#scrollTop.visible{display:flex}
#scrollTop:hover{transform:translateY(-3px)}

/* Footer */
footer{background:#003B6F;border-top:2px solid rgba(0,173,233,.25);text-align:center;font-size:12px;color:rgba(255,255,255,.4);padding:22px 16px}
footer strong{color:rgba(255,255,255,.75)}
"""

# ── JS ───────────────────────────────────────────────────────────────────────
_JS_TEMPLATE = """
const H = "{pw_hash}";

async function sha256(str) {{
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2,"0")).join("");
}}

async function checkPw() {{
  const val = document.getElementById("pw").value;
  const h = await sha256(val);
  if (h === H) {{
    sessionStorage.setItem("auth", H);
    show();
  }} else {{
    const err = document.getElementById("err");
    err.style.display = "block";
    err.style.animation = "none";
    requestAnimationFrame(() => {{ err.style.animation = "shake .35s"; }});
    document.getElementById("pw").value = "";
    document.getElementById("pw").focus();
  }}
}}

function show() {{
  document.getElementById("gate").style.display = "none";
  document.getElementById("main").style.display = "block";
}}

document.getElementById("pw").addEventListener("keydown", e => {{ if (e.key === "Enter") checkPw(); }});
if (sessionStorage.getItem("auth") === H) show();

function toggleSec(id) {{
  const body = document.getElementById("body-" + id);
  const tgl  = document.getElementById("tgl-" + id);
  const isOpen = tgl.classList.contains("open");
  body.style.display = isOpen ? "none" : "";
  tgl.classList.toggle("open", !isOpen);
  tgl.textContent = isOpen ? "▶" : "▼";
}}

function toggleExtra(id, total) {{
  const extra = document.getElementById("extra-" + id);
  const bar   = document.getElementById("expbar-" + id);
  const isOpen = extra.classList.toggle("open");
  bar.innerHTML = isOpen
    ? "▴ &nbsp;접기"
    : "▾ &nbsp;나머지 <strong>" + total + "</strong>건 더 보기";
}}

function toggleMore(btn) {{
  const summary = btn.previousElementSibling;
  const expanded = summary.classList.toggle("expanded");
  btn.textContent = expanded ? "접기 ▴" : "더보기 ▾";
}}

document.querySelectorAll(".card-summary").forEach(el => {{
  const lineH = parseInt(getComputedStyle(el).lineHeight);
  if (el.scrollHeight <= lineH * 2 + 4) {{
    const btn = el.nextElementSibling;
    if (btn && btn.classList.contains("more-btn")) btn.style.display = "none";
  }}
}});

const scrollBtn = document.getElementById("scrollTop");
window.addEventListener("scroll", () => {{
  scrollBtn.classList.toggle("visible", window.scrollY > 400);
}});
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _get_source(article: dict) -> str:
    link = article.get("link") or ""
    if "nhtsa.gov" in link:
        return "NHTSA (nhtsa.gov)"
    if "car.go.kr" in link:
        return "자동차리콜센터 (car.go.kr)"
    if "autoherald.co.kr" in link:
        return "오토헤럴드"
    if "molit.go.kr" in link or "korea.kr" in link:
        return "국토교통부"
    if "kama.or.kr" in link:
        return "자동차산업협회"
    if "motorgraph.com" in link:
        return "모터그래프"
    if "autodaily.co.kr" in link:
        return "오토데일리"
    return ""


def _extract_date(pub: str) -> str:
    """published 문자열에서 날짜 부분(YYYY-MM-DD)만 추출."""
    if not pub:
        return "날짜 미상"
    # YYYY-MM-DD HH:MM
    m = re.match(r'(\d{4}-\d{2}-\d{2})', pub)
    if m:
        return m.group(1)
    # YYYY.MM.DD
    m = re.match(r'(\d{4})\.(\d{2})\.(\d{2})', pub)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # YYYYMMDD
    m = re.match(r'(\d{4})(\d{2})(\d{2})', pub)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # YYYY-MM (월별 통계)
    m = re.match(r'(\d{4}-\d{2})$', pub)
    if m:
        return m.group(1)
    return pub[:10] if len(pub) >= 10 else pub


def _is_cargokr_stat(article: dict) -> bool:
    title = article.get("title") or ""
    return "[car.go.kr]" in title and "리콜 통계" in title


def _cargokr_stat_html(article: dict, color: str) -> str:
    m = _STAT_RE.search(article.get("title", ""))
    if not m:
        return ""
    year, month = m.group(1), m.group(2)
    link = _escape(article.get("link") or "#")
    return (
        f'<div class="recall-stat-card">'
        f'<div class="card-meta">'
        f'<span class="card-date">{year}-{month}</span>'
        f'<span class="card-source">자동차리콜센터 (car.go.kr)</span>'
        f'</div>'
        f'<div class="recall-stat-title" style="color:{color}">{year}년 {month}월 리콜 현황</div>'
        f'<div class="recall-stat-grid">'
        f'<div class="recall-stat-item"><div class="rs-label">국산</div>'
        f'<div class="rs-value">{m.group(3)}건</div><div class="rs-sub">{m.group(4)}대</div></div>'
        f'<div class="recall-stat-item"><div class="rs-label">수입</div>'
        f'<div class="rs-value">{m.group(5)}건</div><div class="rs-sub">{m.group(6)}대</div></div>'
        f'<div class="recall-stat-item"><div class="rs-label">합계</div>'
        f'<div class="rs-value">{m.group(7)}건</div><div class="rs-sub">{m.group(8)}대</div></div>'
        f'</div>'
        f'<a href="{link}" class="recall-detail-link" target="_blank" rel="noopener noreferrer">'
        f'→ 개별 리콜 건 상세보기 (car.go.kr)</a>'
        f'</div>'
    )


def _card_html(article: dict, color: str) -> str:
    if _is_cargokr_stat(article):
        return _cargokr_stat_html(article, color)

    title   = _escape(article.get("title") or "(제목 없음)")
    link    = _escape(article.get("link") or "#")
    pub     = _escape(article.get("published") or "")
    summary = _escape(article.get("summary") or "")
    source  = _get_source(article)

    source_tag = f'<span class="card-source">{_escape(source)}</span>' if source else ""
    summary_block = (
        f'<p class="card-summary">{summary}</p>'
        f'<button class="more-btn" style="color:{color}" onclick="toggleMore(this)">더보기 ▾</button>'
    ) if summary else ""

    return (
        f'<div class="card">'
        f'<div class="card-meta"><span class="card-date">{pub}</span>{source_tag}</div>'
        f'<a href="{link}" class="card-title" style="color:{color}" target="_blank" rel="noopener noreferrer">{title}</a>'
        f'{summary_block}'
        f'</div>'
    )


def _section_html(cat: str, label: str, color: str, icon_html: str, articles: list[dict]) -> str:
    count = len(articles)

    # 날짜 내림차순 정렬
    sorted_articles = sorted(
        articles[:60],
        key=lambda a: _extract_date(a.get("published") or ""),
        reverse=True,
    )

    # 날짜별 그룹핑
    date_groups: dict[str, list[dict]] = {}
    date_order: list[str] = []
    for a in sorted_articles:
        date = _extract_date(a.get("published") or "")
        if date not in date_groups:
            date_groups[date] = []
            date_order.append(date)
        date_groups[date].append(a)

    # 각 날짜 그룹별로 DATE_VISIBLE 건 노출, 초과분은 접기
    content_html = ""
    for date in date_order:
        group = date_groups[date]
        g_count = len(group)
        group_id = f"{cat}-{date.replace('-', '')}"

        content_html += f'<div class="date-sep"><span>{date}</span></div>'
        for a in group[:DATE_VISIBLE]:
            content_html += _card_html(a, color)

        if g_count > DATE_VISIBLE:
            remaining = g_count - DATE_VISIBLE
            extra_cards = "".join(_card_html(a, color) for a in group[DATE_VISIBLE:])
            content_html += (
                f'<div class="cards-extra" id="extra-{group_id}">{extra_cards}</div>'
                f'<button class="expand-bar date-expand-bar" id="expbar-{group_id}" '
                f'onclick="toggleExtra(\'{group_id}\',{remaining})" style="color:{color}">'
                f'▾ &nbsp;나머지 <strong>{remaining}</strong>건 더 보기</button>'
            )

    if not articles:
        body = (
            '<div class="empty-state">'
            '<div class="empty-icon">📭</div>'
            '<div class="empty-text">오늘은 수집된 정보가 없습니다.</div>'
            '</div>'
        )
    else:
        body = f'<div class="cards-list">{content_html}</div>'

    return (
        f'<section class="section" id="sec-{cat}" style="--sec-c:{color}">'
        f'<div class="section-header" onclick="toggleSec(\'{cat}\')">'
        f'<div class="section-icon">{icon_html}</div>'
        f'<div class="section-title" style="color:{color}">{label}</div>'
        f'<span class="section-badge" style="background:{color}">{count}건</span>'
        f'<span class="sec-toggle open" id="tgl-{cat}">▼</span>'
        f'</div>'
        f'<div id="body-{cat}">{body}</div>'
        f'</section>'
    )


# ── Public API ───────────────────────────────────────────────────────────────

def build_html(news_by_category: dict[str, list[dict]], report_date: str) -> str:
    pw_hash = hashlib.sha256(SITE_PASSWORD.encode()).hexdigest()

    nav_items = ""
    sections  = ""

    for cat, label in CATEGORY_LABELS.items():
        articles  = news_by_category.get(cat, [])
        color     = CATEGORY_COLORS.get(cat, "#00ADE9")
        emoji     = CATEGORY_ICONS.get(cat, "📋")
        # 국기 카테고리는 img 태그, 나머지는 이모지
        icon_html = _FLAG_IMG.get(cat, emoji)
        count     = len(articles)

        # nav용 아이콘 (인라인이므로 img 태그 그대로 사용)
        nav_icon = _FLAG_IMG.get(cat, emoji)
        nav_items += (
            f'<a href="#sec-{cat}" class="nav-link" style="--c:{color}">'
            f'{nav_icon} {label} <span class="nav-count">{count}</span></a>'
        )
        sections += _section_html(cat, label, color, icon_html, articles)

    js = _JS_TEMPLATE.format(pw_hash=pw_hash)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>자동차 산업동향 브리핑 | HL Mando CQO</title>
<style>{_CSS}</style>
</head>
<body>

<div id="gate">
  <div class="gate-card">
    <div class="gate-emblem">🚗</div>
    <div class="gate-logo">자동차 산업동향 브리핑</div>
    <div class="gate-brand">HL MANDO &nbsp;·&nbsp; CQO &nbsp;·&nbsp; QUALITY PLANNING</div>
    <div class="gate-sub">
      HL Mando CQO 조직 Quality Planning에서 관리하는<br>
      품질기획팀 전용 브리핑 페이지입니다<br>
      <span style="font-size:11.5px;opacity:.7">접근 권한이 있는 구성원만 이용할 수 있습니다</span>
    </div>
    <div class="gate-label">비밀번호</div>
    <input id="pw" class="gate-input" type="password" placeholder="비밀번호를 입력하세요" autocomplete="current-password">
    <button class="gate-btn" onclick="checkPw()">입장하기</button>
    <div id="err" class="gate-err">⚠ 비밀번호가 올바르지 않습니다.</div>
  </div>
</div>

<div id="main">
  <header>
    <div class="header-inner">
      <div class="header-icon">📋</div>
      <div>
        <div class="header-title">자동차 산업동향 브리핑</div>
        <div class="header-org">HL Mando CQO &nbsp;·&nbsp; Quality Planning</div>
        <div class="header-meta">{report_date} 기준 &nbsp;·&nbsp; 매일 오전 7시 자동 업데이트</div>
      </div>
    </div>
  </header>

  <nav>
    <div class="nav-inner">{nav_items}</div>
  </nav>

  <main>
    {sections}
  </main>

  <footer>
    <strong>HL Mando CQO &nbsp;·&nbsp; Quality Planning</strong><br>
    <span style="font-size:11px;margin-top:4px;display:inline-block">
      자동차 산업동향 브리핑 &nbsp;|&nbsp; {report_date} &nbsp;|&nbsp; 자동 수집된 공개 뉴스입니다
    </span>
  </footer>
</div>

<button id="scrollTop" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" title="맨 위로">↑</button>

<script>{js}</script>
</body>
</html>"""
