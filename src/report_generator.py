import hashlib
from src.config import CATEGORY_LABELS, CATEGORY_COLORS, SITE_PASSWORD


def _articles_html(articles: list[dict], color: str) -> str:
    if not articles:
        return '<p class="no-news">수집된 뉴스가 없습니다.</p>'
    items = []
    for a in articles[:15]:
        title = (a.get("title") or "(제목 없음)").replace("<", "&lt;").replace(">", "&gt;")
        link = a.get("link", "#")
        pub = a.get("published", "")
        summary = (a.get("summary") or "").replace("<", "&lt;").replace(">", "&gt;")
        items.append(f"""
          <div class="card">
            <div class="card-date">{pub}</div>
            <a href="{link}" class="card-title" style="color:{color}" target="_blank" rel="noopener noreferrer">{title}</a>
            {"<p class='card-summary'>" + summary + "</p>" if summary else ""}
          </div>""")
    return "".join(items)


def build_html(news_by_category: dict[str, list[dict]], report_date: str) -> str:
    pw_hash = hashlib.sha256(SITE_PASSWORD.encode()).hexdigest()
    total = sum(len(v) for v in news_by_category.values())

    sections = ""
    nav_items = ""
    for cat, label in CATEGORY_LABELS.items():
        articles = news_by_category.get(cat, [])
        color = CATEGORY_COLORS.get(cat, "#333")
        count = len(articles)
        sections += f"""
        <section class="section" id="sec-{cat}">
          <div class="section-header" style="border-left-color:{color}">
            <h2 style="color:{color}">{label}</h2>
            <span class="badge" style="background:{color}">{count}건</span>
          </div>
          {_articles_html(articles, color)}
        </section>"""
        nav_items += f'<a href="#sec-{cat}" class="nav-link" style="--c:{color}">{label} <span>{count}</span></a>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>자동차 산업동향 브리핑</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: "Malgun Gothic", "Apple SD Gothic Neo", Arial, sans-serif; background: #f0f2f5; color: #222; min-height: 100vh; }}

  /* ── 비밀번호 게이트 ── */
  #gate {{
    position: fixed; inset: 0; background: #1a1a2e;
    display: flex; align-items: center; justify-content: center; z-index: 1000;
  }}
  .gate-card {{
    background: #fff; border-radius: 16px; padding: 48px 40px; width: 360px;
    box-shadow: 0 20px 60px rgba(0,0,0,.4); text-align: center;
  }}
  .gate-logo {{ font-size: 28px; font-weight: 800; color: #1a1a2e; margin-bottom: 4px; }}
  .gate-sub {{ font-size: 13px; color: #888; margin-bottom: 32px; }}
  .gate-label {{ font-size: 13px; color: #555; text-align: left; margin-bottom: 6px; }}
  .gate-input {{
    width: 100%; padding: 12px 16px; border: 1.5px solid #ddd; border-radius: 8px;
    font-size: 15px; outline: none; transition: border-color .2s;
  }}
  .gate-input:focus {{ border-color: #3b82f6; }}
  .gate-btn {{
    width: 100%; margin-top: 16px; padding: 13px; background: #1a1a2e; color: #fff;
    border: none; border-radius: 8px; font-size: 15px; font-weight: 700; cursor: pointer;
    transition: background .2s;
  }}
  .gate-btn:hover {{ background: #2d2d4e; }}
  .gate-err {{ margin-top: 12px; font-size: 13px; color: #ef4444; display: none; }}

  /* ── 메인 콘텐츠 ── */
  #main {{ display: none; }}
  header {{
    background: #1a1a2e; color: #fff; padding: 20px 24px;
    position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 8px rgba(0,0,0,.3);
  }}
  .header-inner {{ max-width: 900px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }}
  .header-title {{ font-size: 20px; font-weight: 800; }}
  .header-meta {{ font-size: 12px; color: #9ba4c4; }}
  .header-total {{ font-size: 13px; color: #fbbf24; font-weight: 700; }}

  nav {{
    background: #fff; border-bottom: 1px solid #e5e7eb;
    overflow-x: auto; white-space: nowrap;
  }}
  .nav-inner {{ max-width: 900px; margin: 0 auto; display: flex; gap: 0; padding: 0 16px; }}
  .nav-link {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 14px 18px; font-size: 13px; font-weight: 600; color: #555;
    text-decoration: none; border-bottom: 3px solid transparent;
    transition: color .15s, border-color .15s;
  }}
  .nav-link:hover {{ color: var(--c); border-bottom-color: var(--c); }}
  .nav-link span {{ background: #f3f4f6; color: #666; font-size: 11px; padding: 2px 7px; border-radius: 10px; }}

  main {{ max-width: 900px; margin: 28px auto; padding: 0 16px 48px; }}

  .section {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.07); }}
  .section-header {{ display: flex; align-items: center; gap: 12px; border-left: 4px solid; padding-left: 14px; margin-bottom: 18px; }}
  .section-header h2 {{ font-size: 16px; font-weight: 700; }}
  .badge {{ color: #fff; font-size: 11px; font-weight: 700; padding: 3px 9px; border-radius: 12px; }}

  .card {{ border-bottom: 1px solid #f3f4f6; padding: 14px 0; }}
  .card:last-child {{ border-bottom: none; padding-bottom: 0; }}
  .card-date {{ font-size: 11px; color: #aaa; margin-bottom: 4px; }}
  .card-title {{ font-size: 14px; font-weight: 700; line-height: 1.5; text-decoration: none; }}
  .card-title:hover {{ text-decoration: underline; }}
  .card-summary {{ font-size: 13px; color: #666; line-height: 1.6; margin-top: 5px; }}
  .no-news {{ font-size: 13px; color: #aaa; font-style: italic; padding: 8px 0; }}

  footer {{ text-align: center; font-size: 12px; color: #bbb; padding: 24px; }}
</style>
</head>
<body>

<!-- 비밀번호 게이트 -->
<div id="gate">
  <div class="gate-card">
    <div class="gate-logo">자동차 산업동향</div>
    <div class="gate-sub">접근 권한이 있는 구성원만 이용할 수 있습니다</div>
    <div class="gate-label">비밀번호</div>
    <input id="pw" class="gate-input" type="password" placeholder="비밀번호를 입력하세요" autocomplete="current-password">
    <button class="gate-btn" onclick="checkPw()">입장하기</button>
    <div id="err" class="gate-err">비밀번호가 올바르지 않습니다.</div>
  </div>
</div>

<!-- 메인 콘텐츠 -->
<div id="main">
  <header>
    <div class="header-inner">
      <div>
        <div class="header-title">자동차 산업동향 브리핑</div>
        <div class="header-meta">{report_date} 기준 · 매일 오전 7시 업데이트</div>
      </div>
      <div class="header-total">총 {total}건</div>
    </div>
  </header>
  <nav>
    <div class="nav-inner">{nav_items}</div>
  </nav>
  <main>{sections}
    <footer>자동차 산업동향 브리핑 · {report_date} · 자동 수집된 공개 뉴스입니다</footer>
  </main>
</div>

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
    document.getElementById("err").style.display = "block";
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
</script>
</body>
</html>"""
