#!/usr/bin/env python3
"""Render an agentcore POST.md into a styled page under docs/.

Usage: python3 scripts/render-post.py agentcore/01-first-agent 2026-07-24

Creates docs/agentcore-<demo>/index.html in the site's dark theme and
copies any PNGs the post references alongside it. Run from the repo root.
"""

import datetime
import html
import json
import pathlib
import re
import shutil
import sys

import markdown

# Byline shown at the top of every post. Leave AUTHOR_LINKEDIN empty to render
# the name unlinked and drop the icon.
AUTHOR_NAME = "Andy Rea"
AUTHOR_TITLE = "Co-Founder &amp; CTO"
AUTHOR_ORG = "Levantar"
AUTHOR_ORG_URL = "https://levantar.ai"
AUTHOR_LINKEDIN = ""
AUTHOR_AVATAR = "../avatar.jpg"
WORDS_PER_MINUTE = 200

# Reading order for the series. Each post signposts back to the one before it
# at the top, and on to the next at the end.
SERIES = [
    ("agentcore-01-first-agent", "What AgentCore actually is, and getting a first agent running on it"),
    ("agentcore-02-gateway", "Giving your agent tools with AgentCore Gateway"),
    ("agentcore-03-memory", "Giving your agent memory that survives the session"),
    ("agentcore-04-builtin-tools", "Letting an agent run code, without letting it run loose"),
    ("agentcore-05-identity", "Knowing who your agent is acting for, with AgentCore Identity"),
]

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
<link rel="canonical" href="{url}">
<meta name="author" content="{author_name}">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Levantar">
<meta property="og:locale" content="en_GB">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:image" content="{url}social.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{title}">
<meta property="og:url" content="{url}">
<meta property="article:published_time" content="{date}">
<meta property="article:author" content="{author_name}">
<meta property="article:section" content="Engineering">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<meta name="twitter:image" content="{url}social.png">
<meta name="twitter:image:alt" content="{title}">
<link rel="icon" type="image/png" href="../favicon.png">
<script type="application/ld+json">
{jsonld}
</script>
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
  .post-meta .role a.org {{ color: var(--muted); text-decoration: none; border-bottom: 1px solid var(--line); }}
  .post-meta .role a.org:hover {{ color: var(--accent); border-bottom-color: var(--accent); }}
  .post-meta .facts {{ color: var(--muted); font-size: 13px; }}
  .post-meta .facts .sep {{ padding: 0 5px; opacity: 0.45; }}
  .series-nav a {{
    display: block; padding: 13px 17px; border: 1px solid var(--line);
    border-radius: 12px; background: var(--card); text-decoration: none;
    transition: border-color 0.15s ease;
  }}
  .series-nav a:hover {{ border-color: var(--accent); text-decoration: none; }}
  .series-nav .label {{
    display: block; font-size: 11.5px; color: var(--muted);
    letter-spacing: 0.05em; text-transform: uppercase;
  }}
  .series-nav .title {{
    display: block; margin-top: 3px; font-size: 15px;
    color: var(--fg); font-weight: 600; line-height: 1.4;
  }}
  .series-nav.prev {{ margin: 0 0 32px; }}
  .series-nav.next {{ margin: 44px 0 0; }}
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
  /* Image lightbox, the same behaviour as levantar.ai: a magnifier chip on each
     content image, the image as a modal on click, a close control. */
  .zoomable {{ display: block; position: relative; width: 100%; margin: 10px 0; padding: 0; border: 0; background: none; cursor: zoom-in; font: inherit; text-align: inherit; }}
  .zoomable img {{ margin: 0; }}
  .zoomable:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 3px; }}
  .zoomable-hint {{ position: absolute; right: 18px; bottom: 18px; width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; border-radius: 999px; background: rgba(11, 17, 32, 0.78); color: #e7edf7; opacity: 0.85; transition: opacity 160ms ease, transform 160ms ease; pointer-events: none; }}
  .zoomable-hint svg {{ width: 18px; height: 18px; }}
  .zoomable:hover .zoomable-hint, .zoomable:focus-visible .zoomable-hint {{ opacity: 1; transform: scale(1.06); }}
  .lightbox {{ position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 56px 24px 24px; background: rgba(5, 9, 18, 0.94); opacity: 0; transition: opacity 180ms ease; }}
  .lightbox[hidden] {{ display: none; }}
  .lightbox.is-open {{ opacity: 1; }}
  .lightbox img {{ display: block; max-width: min(96vw, 1800px); max-height: calc(100vh - 80px); width: auto; height: auto; margin: 0; padding: 10px; border: 0; border-radius: 14px; background: #fff; box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55); }}
  .lightbox-close {{ position: absolute; top: 16px; right: 16px; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(231, 237, 247, 0.35); border-radius: 999px; background: rgba(11, 17, 32, 0.6); color: #e7edf7; cursor: pointer; padding: 0; }}
  .lightbox-close svg {{ width: 19px; height: 19px; }}
  .lightbox-close:hover, .lightbox-close:focus-visible {{ background: var(--accent); border-color: var(--accent); color: #0b1120; outline: none; }}
  .lightbox-caption {{ position: absolute; left: 24px; right: 72px; bottom: 20px; margin: 0; color: rgba(231, 237, 247, 0.8); font-size: 14px; line-height: 1.4; }}
  body.lightbox-open {{ overflow: hidden; }}
  @media (prefers-reduced-motion: reduce) {{ .lightbox, .zoomable-hint {{ transition: none; }} }}
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
{prev_nav}
{body}
{next_nav}
    </article>
  </div>
  <script>
  (function () {{
    'use strict';
    var zoomable_images = document.querySelectorAll('article p > img');
    if (!zoomable_images.length) return;
    var MAGNIFIER = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3M11 8v6M8 11h6"/></svg>';
    var CLOSE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    var box = document.createElement('div');
    box.className = 'lightbox';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.hidden = true;
    box.innerHTML = '<button type="button" class="lightbox-close" aria-label="Close">' + CLOSE + '</button><img alt=""><p class="lightbox-caption"></p>';
    document.body.appendChild(box);
    var boxImg = box.querySelector('img');
    var boxCaption = box.querySelector('.lightbox-caption');
    var closeButton = box.querySelector('.lightbox-close');
    var opener = null;
    var close = function () {{
      if (box.hidden) return;
      box.classList.remove('is-open');
      box.hidden = true;
      document.body.classList.remove('lightbox-open');
      boxImg.removeAttribute('src');
      if (opener) opener.focus();
      opener = null;
    }};
    var open = function (img, trigger) {{
      opener = trigger;
      boxImg.src = img.currentSrc || img.src;
      boxImg.alt = img.alt || '';
      boxCaption.textContent = img.alt || '';
      box.setAttribute('aria-label', img.alt || 'Image');
      box.hidden = false;
      document.body.classList.add('lightbox-open');
      void box.offsetWidth;
      box.classList.add('is-open');
      closeButton.focus();
    }};
    closeButton.addEventListener('click', close);
    box.addEventListener('click', function (event) {{ if (event.target === box) close(); }});
    document.addEventListener('keydown', function (event) {{ if (event.key === 'Escape') close(); }});
    Array.prototype.forEach.call(zoomable_images, function (img) {{
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'zoomable';
      button.setAttribute('aria-label', 'Enlarge image' + (img.alt ? ': ' + img.alt : ''));
      img.parentNode.insertBefore(button, img);
      button.appendChild(img);
      var hint = document.createElement('span');
      hint.className = 'zoomable-hint';
      hint.innerHTML = MAGNIFIER;
      button.appendChild(hint);
      button.addEventListener('click', function () {{ open(img, button); }});
    }});
  }})();
  </script>
</body>
</html>
"""


def structured_data(title, description, date, url, minutes):
    """Schema.org BlogPosting, so search engines get the author, publisher
    and date from something better than guesswork."""
    return json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": title,
            "description": description,
            "image": f"{url}social.png",
            "datePublished": date,
            "dateModified": date,
            "wordCount": minutes * WORDS_PER_MINUTE,
            "inLanguage": "en-GB",
            "mainEntityOfPage": {"@type": "WebPage", "@id": url},
            "author": {
                "@type": "Person",
                "name": AUTHOR_NAME,
                "jobTitle": "Co-Founder & CTO",
                "worksFor": {"@type": "Organization", "name": AUTHOR_ORG, "url": AUTHOR_ORG_URL},
            },
            "publisher": {
                "@type": "Organization",
                "name": AUTHOR_ORG,
                "url": AUTHOR_ORG_URL,
                "logo": {
                    "@type": "ImageObject",
                    "url": "https://levantar-ai.github.io/demos/levantar-logo-white.png",
                },
            },
            "isPartOf": {"@type": "CreativeWorkSeries", "name": "AgentCore series"},
        },
        indent=2,
    )


def signposts(slug):
    """Links to the neighbouring posts, empty strings at either end."""
    slugs = [s for s, _ in SERIES]
    if slug not in slugs:
        return "", ""
    i = slugs.index(slug)

    def card(where, target, label):
        target_slug, target_title = target
        return (
            f'      <nav class="series-nav {where}">\n'
            f'        <a href="../{target_slug}/">\n'
            f'          <span class="label">{label}</span>\n'
            f'          <span class="title">{html.escape(target_title)}</span>\n'
            f"        </a>\n"
            f"      </nav>"
        )

    before = card("prev", SERIES[i - 1], "Previous in this series") if i > 0 else ""
    after = card("next", SERIES[i + 1], "Next in this series") if i < len(SERIES) - 1 else ""
    return before, after


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
          <div class="role">{AUTHOR_TITLE}, <a class="org" href="{AUTHOR_ORG_URL}" target="_blank" rel="noopener">{AUTHOR_ORG}</a></div>
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
    url = f"https://levantar-ai.github.io/demos/{slug}/"
    prev_nav, next_nav = signposts(slug)

    html = TEMPLATE.format(
        title=title,
        description=description,
        date=date,
        meta=byline(date, minutes),
        url=url,
        jsonld=structured_data(title, description, date, url, minutes),
        prev_nav=prev_nav,
        next_nav=next_nav,
        author_name=AUTHOR_NAME,
        body=body,
        slug=slug,
    )
    (out_dir / "index.html").write_text(html)
    print(f"rendered {src} -> {out_dir}/index.html")


if __name__ == "__main__":
    main()
