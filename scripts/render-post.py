#!/usr/bin/env python3
"""Render an agentcore POST.md into a styled page under docs/.

Usage: python3 scripts/render-post.py agentcore/01-first-agent 2026-07-24

Creates docs/agentcore-<demo>/index.html in the site's dark theme and
copies any PNGs the post references alongside it. Run from the repo root.
"""

import pathlib
import re
import shutil
import sys

import markdown

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title} — Levantar Demos</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{description}">
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
  body {{
    margin: 0; min-height: 100vh; padding: 48px 24px 80px; color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    background: radial-gradient(1100px 500px at 75% -10%, #1b2a4a 0%, #0b1120 55%) var(--bg);
    line-height: 1.7;
  }}
  .wrap {{ max-width: 820px; margin: 0 auto; }}
  .top {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 36px; }}
  .top a {{ color: var(--muted); text-decoration: none; font-size: 14px; }}
  .top a:hover {{ color: var(--accent); }}
  .brand {{ display: inline-flex; align-items: center; gap: 11px; color: var(--fg) !important; font-weight: 600; font-size: 15px; }}
  .brand img {{ height: 32px; }}
  article h1 {{ font-size: 30px; letter-spacing: -0.02em; line-height: 1.25; margin: 0 0 6px; }}
  article .date {{ color: var(--muted); font-size: 13px; margin-bottom: 28px; }}
  article h2 {{ font-size: 21px; margin: 40px 0 12px; letter-spacing: -0.01em; }}
  article p, article li {{ color: #c6d2e6; font-size: 16px; }}
  article a {{ color: var(--accent); text-decoration: none; }}
  article a:hover {{ text-decoration: underline; }}
  article img {{ max-width: 100%; border-radius: 14px; border: 1px solid var(--line); background: #fff; padding: 10px; margin: 10px 0; }}
  article code {{ background: var(--card); border: 1px solid var(--line); border-radius: 5px; padding: 1px 6px; font-size: 14px; }}
  article pre {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 18px 20px; overflow-x: auto; }}
  article pre code {{ background: none; border: none; padding: 0; font-size: 13.5px; line-height: 1.6; color: #d8e2f3; }}
  article table {{ border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 14.5px; }}
  article th, article td {{ border: 1px solid var(--line); padding: 8px 12px; text-align: left; }}
  article th {{ background: var(--card); }}
  article blockquote {{ border-left: 3px solid var(--accent); margin: 0; padding: 2px 18px; color: var(--muted); }}
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
      <div class="date">{date} · AgentCore series</div>
{body}
    </article>
  </div>
</body>
</html>
"""


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

    for png in re.findall(r"!\[[^\]]*\]\(([^)]+\.png)\)", text):
        shutil.copy(pathlib.Path(demo) / png, out_dir / pathlib.Path(png).name)

    body = markdown.markdown(text, extensions=["fenced_code", "tables"])

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
    html = TEMPLATE.format(title=title, description=description, date=date, body=body)
    (out_dir / "index.html").write_text(html)
    print(f"rendered {src} -> {out_dir}/index.html")


if __name__ == "__main__":
    main()
