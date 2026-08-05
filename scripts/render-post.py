#!/usr/bin/env python3
"""Render an agentcore POST.md into a styled page under docs/.

Usage: python3 scripts/render-post.py agentcore/01-first-agent 2026-07-24

Creates docs/agentcore-<demo>/index.html in the site's dark theme and
copies any PNGs the post references alongside it. Run from the repo root.
"""

import datetime
import pathlib
import re
import shutil
import sys

import markdown

# Byline shown at the top of every post. Leave AUTHOR_LINKEDIN empty to render
# the name unlinked and drop the icon.
AUTHOR_NAME = "Andy Rea"
AUTHOR_TITLE = "Co-Founder &amp; CTO, Levantar"
AUTHOR_LINKEDIN = ""
AUTHOR_AVATAR = "../avatar.jpg"
WORDS_PER_MINUTE = 200

LINKEDIN_ICON = (
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
    '<path d="M20.45 20.45h-3.56v-5.57c0-1.33-.03-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 '
    "2.94v5.67H9.35V9h3.41v1.56h.05c.47-.9 1.63-1.85 3.36-1.85 3.6 0 4.27 2.37 4.27 "
    "5.45v6.29zM5.34 7.43a2.06 2.06 0 1 1 0-4.13 2.06 2.06 0 0 1 0 4.13zM7.12 "
    "20.45H3.55V9h3.57v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.72v20.56C0 23.23.79 24 "
    '1.77 24h20.45c.98 0 1.78-.77 1.78-1.72V1.72C24 .77 23.2 0 22.22 0z"/></svg>'
)

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title} — Levantar Demos</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{description}">
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:image" content="https://levantar-ai.github.io/demos/{slug}/social.png">
<meta property="og:url" content="https://levantar-ai.github.io/demos/{slug}/">
<meta property="article:published_time" content="{date}">
<meta property="article:author" content="{author_name}">
<meta name="author" content="{author_name}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="https://levantar-ai.github.io/demos/{slug}/social.png">
<link rel="icon" type="image/png" href="../favicon.png">
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7C1NXQ0H0E"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-7C1NXQ0H0E');
</script>
<style>
  :root {{
    --bg: #0b1120; --card: #152037; --line: #243352; --fg: #e7edf7;
    --muted: #93a4c3; --accent: #22d3ee; --hl: #fbbf24;
  }}
  * {{ box-sizing: border-box; }}
  html {{ -webkit-text-size-adjust: 100%; }}
  body {{
    margin: 0; min-height: 100vh; padding: 48px 24px 80px; color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    background: radial-gradient(1100px 500px at 75% -10%, #1b2a4a 0%, #0b1120 55%) var(--bg);
    line-height: 1.7; overflow-wrap: break-word;
  }}
  .wrap {{ max-width: 820px; margin: 0 auto; }}
  .top {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 36px; }}
  .top a {{ color: var(--muted); text-decoration: none; font-size: 14px; }}
  .top a:hover {{ color: var(--accent); }}
  .brand {{ display: inline-flex; align-items: center; gap: 11px; color: var(--fg) !important; font-weight: 600; font-size: 15px; }}
  .brand img {{ height: 32px; }}
  article h1 {{ font-size: 30px; letter-spacing: -0.02em; line-height: 1.25; margin: 0 0 6px; }}
  article h2 {{ font-size: 21px; margin: 40px 0 12px; letter-spacing: -0.01em; }}
  article p, article li {{ color: #c6d2e6; font-size: 16px; }}
  article a {{ color: var(--accent); text-decoration: none; overflow-wrap: anywhere; }}
  article a:hover {{ text-decoration: underline; }}
  article img {{ max-width: 100%; height: auto; border-radius: 14px; border: 1px solid var(--line); background: #fff; padding: 10px; margin: 10px 0; }}
  article code {{ background: var(--card); border: 1px solid var(--line); border-radius: 5px; padding: 1px 6px; font-size: 14px; overflow-wrap: anywhere; }}
  article pre {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 18px 20px; max-width: 100%; overflow-x: auto; overscroll-behavior-x: contain; }}
  article pre code {{ background: none; border: none; padding: 0; font-size: 13.5px; line-height: 1.6; color: #d8e2f3; overflow-wrap: normal; }}
  .table-wrap {{ max-width: 100%; margin: 14px 0; overflow-x: auto; overscroll-behavior-x: contain; }}
  article table {{ border-collapse: collapse; width: 100%; margin: 0; font-size: 14.5px; }}
  article th, article td {{ border: 1px solid var(--line); padding: 8px 12px; text-align: left; }}
  article th {{ background: var(--card); }}
  article blockquote {{ border-left: 3px solid var(--accent); margin: 0; padding: 2px 18px; color: var(--muted); }}
  .post-meta {{
    display: flex; align-items: center; gap: 14px;
    margin: 16px 0 34px; padding-bottom: 22px; border-bottom: 1px solid var(--line);
  }}
  .post-meta .avatar {{
    width: 52px; height: 52px; flex: 0 0 52px; border-radius: 50%;
    object-fit: cover; border: 1px solid var(--line); background: var(--card);
  }}
  .post-meta .who {{ min-width: 0; line-height: 1.45; }}
  .post-meta .name {{
    display: inline-flex; align-items: center; gap: 6px;
    color: var(--fg); font-weight: 600; font-size: 15px; text-decoration: none;
  }}
  .post-meta a.name:hover {{ color: var(--accent); text-decoration: none; }}
  .post-meta a.name:hover svg {{ color: var(--accent); }}
  .post-meta .name svg {{ width: 13px; height: 13px; flex: none; color: var(--muted); }}
  .post-meta .role {{ color: var(--muted); font-size: 13.5px; }}
  .post-meta .facts {{ color: var(--muted); font-size: 13px; }}
  .post-meta .facts .sep {{ padding: 0 5px; opacity: 0.45; }}
  @media (max-width: 640px) {{
    body {{ padding: 32px 16px 64px; }}
    .top {{ margin-bottom: 28px; }}
    article h1 {{ font-size: 25px; }}
    article h2 {{ font-size: 19px; margin: 32px 0 10px; }}
    article p, article li {{ font-size: 15.5px; }}
    article pre {{ padding: 14px 15px; border-radius: 10px; }}
    article pre code {{ font-size: 12.5px; }}
    .post-meta {{ gap: 12px; margin-bottom: 28px; }}
    .post-meta .avatar {{ width: 46px; height: 46px; flex-basis: 46px; }}
  }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <a class="brand" href="https://levantar.ai" target="_blank" rel="noopener">
        <img src="../levantar-logo-white.png" alt="Levantar"><span>Levantar</span>
      </a>
      <a href="../">← All demos</a>
    </div>
    <article>
      <h1>{title}</h1>
{meta}
{body}
    </article>
  </div>
</body>
</html>
"""


def reading_time(text):
    """Minutes to read, counting prose only — fenced code blocks are skipped."""
    prose = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    return max(1, round(len(re.findall(r"\S+", prose)) / WORDS_PER_MINUTE))


def byline(date, minutes):
    """The author meta block: avatar, name, title, date, reading time, series."""
    day = datetime.date.fromisoformat(date)
    shown = f"{day.day} {day:%B %Y}"

    if AUTHOR_LINKEDIN:
        name = (
            f'<a class="name" href="{AUTHOR_LINKEDIN}" target="_blank" rel="noopener me">'
            f"{AUTHOR_NAME}{LINKEDIN_ICON}</a>"
        )
    else:
        name = f'<span class="name">{AUTHOR_NAME}</span>'

    return f"""      <div class="post-meta">
        <img class="avatar" src="{AUTHOR_AVATAR}" alt="{AUTHOR_NAME}" width="52" height="52">
        <div class="who">
          <div>{name}</div>
          <div class="role">{AUTHOR_TITLE}</div>
          <div class="facts"><time datetime="{date}">{shown}</time><span class="sep">·</span>\
{minutes} min read<span class="sep">·</span>AgentCore series</div>
        </div>
      </div>"""


def main():
    demo = sys.argv[1].rstrip("/")
    date = sys.argv[2]
    src = pathlib.Path(demo) / "POST.md"
    slug = demo.replace("/", "-")
    out_dir = pathlib.Path("docs") / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    text = src.read_text()
    title_match = re.match(r"# (.+)\n", text)
    title = title_match.group(1)
    text = text[title_match.end():]

    description = re.sub(r"\s+", " ", text.split("## Longer version")[0])
    description = re.sub(r"^.*?TL;DR;?", "", description).strip()
    description = description.split("SOURCE CODE")[0].strip()[:300]

    minutes = reading_time(text)

    for png in re.findall(r"!\[[^\]]*\]\(([^)]+\.png)\)", text):
        shutil.copy(pathlib.Path(demo) / png, out_dir / pathlib.Path(png).name)

    for name in ("social.png", "social-square.png"):
        card = pathlib.Path(demo) / name
        if card.exists():
            shutil.copy(card, out_dir / name)

    # Auto-link bare URLs (outside fenced code blocks) so the SOURCE CODE
    # line and References render as clickable anchors.
    linked, in_fence = [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            line = re.sub(r"(?<![(<`\[])(https?://[^\s)>\"]+)", r"<\1>", line)
        linked.append(line)
    text = "\n".join(linked)

    body = markdown.markdown(text, extensions=["fenced_code", "tables"])

    # Tables scroll inside their own container rather than widening the page.
    body = re.sub(
        r"<table>.*?</table>",
        lambda m: f'<div class="table-wrap">{m.group(0)}</div>',
        body,
        flags=re.DOTALL,
    )

    # If the demo has a recorded terminal video, place it after the diagram.
    video_src = pathlib.Path(demo) / "demo.mp4"
    if video_src.exists():
        shutil.copy(video_src, out_dir / "demo.mp4")
        video = (
            '<video controls muted playsinline preload="metadata" '
            'style="width:100%;border-radius:14px;border:1px solid var(--line);margin:10px 0;">'
            '<source src="demo.mp4" type="video/mp4"></video>'
        )
        body = re.sub(
            r"(<p><img[^>]*architecture[^>]*></p>)",
            r"\1\n" + video,
            body,
            count=1,
        )
    html = TEMPLATE.format(
        title=title,
        description=description,
        date=date,
        meta=byline(date, minutes),
        author_name=AUTHOR_NAME,
        body=body,
        slug=slug,
    )
    (out_dir / "index.html").write_text(html)
    print(f"rendered {src} -> {out_dir}/index.html")


if __name__ == "__main__":
    main()
