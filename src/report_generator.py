import hashlib
from src.config import CATEGORY_LABELS, CATEGORY_COLORS, SITE_PASSWORD

CATEGORY_ICONS = {
    "recall_kr":  ("🔔", "#fff1f2"),
    "recall_us":  ("🌐", "#fff7ed"),
    "oem":        ("📊", "#eff6ff"),
    "regulation": ("📜", "#f0fdf4"),
}

CATEGORY_NAV_EMOJI = {
    "recall_kr":  "🔴",
    "recall_us":  "🟠",
    "oem":        "🔵",
    "regulation": "🟢",
}


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _articles_html(articles: list[dict], color: str) -> str:
    if not articles:
        return """
      <div class="empty-state">
        <div class="empty-icon">📭</div>
        <div class="empty-text">오늘은 수집된 뉴스가 없습니다.</div>
      </div>"""
    items = []
    for a in articles[:15]:
        title   = _escape(a.get("title") or "(제목 없음)")
        link    = a.get("link", "#")
        pub     = _escape(a.get("published", ""))
        summary = _escape(a.get("summary") or "")
        summary_html = (
            f'<p class="card-summary">{summary}</p>'
            f'<button class="more-btn" style="color:{color}" onclick="toggleMore(this)">더보기 ▾</button>'
        ) if summary else ""
        items.append(f"""
        <div class="card">
          <div class="card-meta"><span class="card-date">{pub}</span></div>
          <a href="{link}" class="card-title" style="color:{color}" target="_blank" rel="noopener noreferrer">{title}</a>
          {summary_html}
        </div>""")
    return '<div class="cards-list">' + "".join(items) + "</div>"


def build_html(news_by_category: dict[str, list[dict]], report_date: str) -> str:
    pw_hash = hashlib.sha256(SITE_PASSWORD.encode()).hexdigest()
    total   = sum(len(v) for v in news_by_category.values())

    sections   = ""
    nav_items  = ""
    for cat, label in CATEGORY_LABELS.items():
        articles    = news_by_category.get(cat, [])
        color       = CATEGORY_COLORS.get(cat, "#333")
        count       = len(articles)
        icon, icon_bg = CATEGORY_ICONS.get(cat, ("📋", "#f8fafc"))
        nav_emoji   = CATEGORY_NAV_EMOJI.get(cat, "")

        sections += f"""
    <section class="section" id="sec-{cat}">
      <div class="section-header">
        <div class="section-icon" style="background:{icon_bg};color:{color}">{icon}</div>
        <div class="section-title" style="color:{color}">{label}</div>
        <span class="section-badge" style="background:{color}">{count}건</span>
      </div>
      {_articles_html(articles, color)}
    </section>"""

        nav_items += (
            f'<a href="#sec-{cat}" class="nav-link" style="--c:{color}">'
            f'{nav_emoji} {label} <span class="nav-count" style="--c:{color}">{count}</span></a>'
        )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>자동차 산업동향 브리핑</title>
<style>
:root{{
  --bg:#f1f5f9;--surface:#ffffff;
  --text-1:#0f172a;--text-2:#475569;--text-3:#94a3b8;--border:#e2e8f0;
  --sh:0 4px 12px rgba(0,0,0,.07);--sh-lg:0 12px 24px rgba(0,0,0,.1);
  --r:12px;--r-sm:8px;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:"Malgun Gothic","Apple SD Gothic Neo",Arial,sans-serif;background:var(--bg);color:var(--text-1);min-height:100vh;line-height:1.6}}
::-webkit-scrollbar{{width:5px;height:5px}}
::-webkit-scrollbar-track{{background:transparent}}
::-webkit-scrollbar-thumb{{background:#cbd5e1;border-radius:3px}}

/* Gate */
#gate{{position:fixed;inset:0;background:linear-gradient(145deg,#0c0e1a 0%,#13172e 40%,#0e1628 100%);display:flex;align-items:center;justify-content:center;z-index:999}}
#gate::before{{content:'';position:absolute;inset:0;background-image:radial-gradient(rgba(99,102,241,.18) 1px,transparent 1px);background-size:28px 28px;mask-image:radial-gradient(ellipse 70% 70% at 50% 50%,black 40%,transparent 100%);pointer-events:none}}
.gate-card{{position:relative;z-index:1;background:rgba(255,255,255,.05);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);border:1px solid rgba(255,255,255,.1);border-radius:20px;padding:48px 40px;width:380px;text-align:center;animation:cardUp .5s cubic-bezier(.34,1.56,.64,1) both}}
@keyframes cardUp{{from{{opacity:0;transform:translateY(24px) scale(.96)}}to{{opacity:1;transform:translateY(0) scale(1)}}}}
.gate-emblem{{width:68px;height:68px;background:linear-gradient(135deg,#6366f1,#8b5cf6);border-radius:18px;margin:0 auto 22px;display:flex;align-items:center;justify-content:center;font-size:30px;box-shadow:0 8px 28px rgba(99,102,241,.5)}}
.gate-logo{{font-size:21px;font-weight:800;color:#fff;letter-spacing:-.4px;margin-bottom:6px}}
.gate-sub{{font-size:12.5px;color:rgba(255,255,255,.45);margin-bottom:36px;line-height:1.5}}
.gate-label{{font-size:11px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:rgba(255,255,255,.5);text-align:left;margin-bottom:8px}}
.gate-input{{width:100%;padding:13px 16px;background:rgba(255,255,255,.07);border:1.5px solid rgba(255,255,255,.14);border-radius:var(--r-sm);font-size:15px;color:#fff;outline:none;letter-spacing:2px;transition:border-color .2s,background .2s}}
.gate-input::placeholder{{color:rgba(255,255,255,.28);letter-spacing:normal}}
.gate-input:focus{{border-color:#6366f1;background:rgba(255,255,255,.1)}}
.gate-btn{{width:100%;margin-top:14px;padding:14px;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;border:none;border-radius:var(--r-sm);font-size:15px;font-weight:700;cursor:pointer;box-shadow:0 4px 16px rgba(99,102,241,.45);transition:transform .15s,box-shadow .15s}}
.gate-btn:hover{{transform:translateY(-2px);box-shadow:0 8px 24px rgba(99,102,241,.55)}}
.gate-btn:active{{transform:translateY(0)}}
.gate-err{{margin-top:12px;font-size:13px;color:#f87171;display:none;animation:shake .35s}}
@keyframes shake{{0%,100%{{transform:translateX(0)}}25%{{transform:translateX(-6px)}}75%{{transform:translateX(6px)}}}}

/* Main */
#main{{display:none;animation:fadeUp .4s ease both}}
@keyframes fadeUp{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:translateY(0)}}}}

/* Header */
header{{background:linear-gradient(135deg,#0f172a 0%,#1e1b4b 100%);color:#fff;padding:16px 24px;position:sticky;top:0;z-index:100;box-shadow:0 2px 20px rgba(0,0,0,.35)}}
.header-inner{{max-width:960px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}}
.header-left{{display:flex;align-items:center;gap:14px}}
.header-icon{{width:40px;height:40px;flex-shrink:0;background:linear-gradient(135deg,#6366f1,#8b5cf6);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;box-shadow:0 4px 12px rgba(99,102,241,.4)}}
.header-title{{font-size:18px;font-weight:800;letter-spacing:-.4px}}
.header-meta{{font-size:11px;color:rgba(255,255,255,.45);margin-top:2px}}
.stat-chip{{display:flex;align-items:center;gap:6px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:20px;padding:7px 14px;font-size:12.5px;color:rgba(255,255,255,.7)}}
.stat-chip strong{{color:#fbbf24;font-weight:700}}

/* Nav */
nav{{background:var(--surface);border-bottom:1px solid var(--border);overflow-x:auto;white-space:nowrap;scrollbar-width:none}}
nav::-webkit-scrollbar{{display:none}}
.nav-inner{{max-width:960px;margin:0 auto;display:flex;padding:0 16px}}
.nav-link{{display:inline-flex;align-items:center;gap:7px;padding:14px 16px;font-size:13px;font-weight:600;color:var(--text-2);text-decoration:none;border-bottom:2.5px solid transparent;transition:color .15s,border-color .15s}}
.nav-link:hover{{color:var(--c);border-bottom-color:var(--c)}}
.nav-count{{font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px;background:#f1f5f9;color:var(--text-3);transition:background .15s,color .15s}}
.nav-link:hover .nav-count{{color:var(--c)}}

/* Sections */
main{{max-width:960px;margin:28px auto;padding:0 20px 72px}}
.section{{background:var(--surface);border-radius:var(--r);margin-bottom:24px;box-shadow:var(--sh);overflow:hidden;transition:box-shadow .2s}}
.section:hover{{box-shadow:var(--sh-lg)}}
.section-header{{display:flex;align-items:center;gap:12px;padding:18px 22px 16px;border-bottom:1px solid var(--border)}}
.section-icon{{width:36px;height:36px;border-radius:10px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:16px}}
.section-title{{font-size:15px;font-weight:700;flex:1}}
.section-badge{{font-size:11px;font-weight:700;padding:4px 11px;border-radius:20px;color:#fff}}

/* Cards */
.cards-list{{padding:4px 0}}
.card{{padding:15px 22px;border-bottom:1px solid #f8fafc;transition:background .15s}}
.card:last-child{{border-bottom:none}}
.card:hover{{background:#fafbff}}
.card-meta{{display:flex;align-items:center;gap:8px;margin-bottom:7px}}
.card-date{{display:inline-flex;align-items:center;font-size:11px;color:var(--text-3);background:#f8fafc;border-radius:4px;padding:2px 8px}}
.card-title{{font-size:14px;font-weight:600;line-height:1.55;text-decoration:none;display:block;transition:opacity .15s}}
.card-title:hover{{text-decoration:underline;text-underline-offset:2px;text-decoration-thickness:1px}}
.card-summary{{font-size:12.5px;color:var(--text-2);line-height:1.7;margin-top:6px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.card-summary.expanded{{display:block;-webkit-line-clamp:unset}}
.more-btn{{font-size:12px;font-weight:600;padding:3px 0;margin-top:5px;background:none;border:none;cursor:pointer;display:inline-block;opacity:.65;transition:opacity .15s}}
.more-btn:hover{{opacity:1}}

/* Empty */
.empty-state{{padding:44px 24px;text-align:center}}
.empty-icon{{font-size:36px;margin-bottom:10px;opacity:.3}}
.empty-text{{font-size:13px;color:var(--text-3)}}

/* Scroll-to-top */
#scrollTop{{position:fixed;bottom:28px;right:28px;width:44px;height:44px;border-radius:50%;background:var(--text-1);color:#fff;border:none;cursor:pointer;font-size:18px;display:none;align-items:center;justify-content:center;box-shadow:var(--sh-lg);transition:transform .2s;z-index:50}}
#scrollTop.visible{{display:flex}}
#scrollTop:hover{{transform:translateY(-3px)}}

/* Footer */
footer{{background:var(--surface);border-top:1px solid var(--border);text-align:center;font-size:12px;color:var(--text-3);padding:16px}}
</style>
</head>
<body>

<div id="gate">
  <div class="gate-card">
    <div class="gate-emblem">🚗</div>
    <div class="gate-logo">자동차 산업동향</div>
    <div class="gate-sub">품질기획팀 전용 브리핑 페이지입니다<br>접근 권한이 있는 구성원만 이용할 수 있습니다</div>
    <div class="gate-label">비밀번호</div>
    <input id="pw" class="gate-input" type="password" placeholder="비밀번호를 입력하세요" autocomplete="current-password">
    <button class="gate-btn" onclick="checkPw()">입장하기</button>
    <div id="err" class="gate-err">⚠ 비밀번호가 올바르지 않습니다.</div>
  </div>
</div>

<div id="main">
  <header>
    <div class="header-inner">
      <div class="header-left">
        <div class="header-icon">📋</div>
        <div>
          <div class="header-title">자동차 산업동향 브리핑</div>
          <div class="header-meta">{report_date} 기준 · 매일 오전 7시 자동 업데이트</div>
        </div>
      </div>
      <div class="stat-chip">총 <strong>{total}</strong>건 수집</div>
    </div>
  </header>
  <nav>
    <div class="nav-inner">{nav_items}</div>
  </nav>
  <main>
    {sections}
  </main>
  <footer>자동차 산업동향 브리핑 &nbsp;·&nbsp; {report_date} &nbsp;·&nbsp; 자동 수집된 공개 뉴스입니다</footer>
</div>

<button id="scrollTop" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" title="맨 위로">↑</button>

<script>
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
</script>
</body>
</html>"""
