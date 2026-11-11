"""Build standalone presentation assets, browser demo and Markdown references."""
from html import escape, unescape
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DOCS = [ROOT / "README.md", ROOT / "PROVENANCE.md", *(
    ROOT / "docs" / name for name in (
        "USER_GUIDE.md", "IMPORTING.md", "KNOWN_ISSUES.md", "ARCHITECTURE.md", "CHANGELOG.md",
    )
)]
TARGETS = {source.resolve(): f"reference/{source.stem}.html" for source in DOCS}
TARGETS.update({
    (ROOT / "site/index.html").resolve(): "index.html",
    (ROOT / "web/index.html").resolve(): "demo/index.html",
    (ROOT / "docs/images/web-demo.png").resolve(): "assets/web-demo.png",
    (ROOT / "docs/images/desktop-demo.jpg").resolve(): "assets/desktop-demo.jpg",
    (ROOT / "LICENSE").resolve(): "reference/LICENSE.txt",
})


def relative_link(raw, source):
    """Keep documentation links inside the generated site when a copy exists."""
    parsed = urlsplit(unescape(raw))
    if parsed.scheme or parsed.netloc or not parsed.path:
        return raw
    target = (source.parent / parsed.path).resolve()
    if target not in TARGETS:
        raise ValueError(f"No site copy for a link in {source.name}: {parsed.path}")
    result = "../" + TARGETS[target]
    if parsed.query:
        result += "?" + parsed.query
    if parsed.fragment:
        result += "#" + parsed.fragment
    return result


def inline(text, source):
    # The maintained docs use code, emphasis, images and ordinary Markdown links.
    codes = []

    def keep_code(match):
        codes.append("<code>" + escape(match[1]) + "</code>")
        return f"TTCODE{len(codes) - 1}TT"

    text = re.sub(r"`([^`]+)`", keep_code, text)
    text = escape(text)
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", lambda m: f'<img src="{escape(relative_link(m[2], source), quote=True)}" alt="{m[1]}">', text)
    text = re.sub(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{escape(relative_link(m[2], source), quote=True)}">{m[1]}</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    for i, code in enumerate(codes):
        text = text.replace(f"TTCODE{i}TT", code)
    return text


def heading_id(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def markdown(source):
    """Render the small Markdown subset used by these reference pages."""
    lines = source.read_text(encoding="utf-8").splitlines()
    result, i = [], 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("```"):
            code, i = [], i + 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            result.append("<pre><code>" + escape("\n".join(code)) + "</code></pre>")
            i += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            level, text = len(heading[1]), heading[2]
            result.append(f'<h{level} id="{heading_id(text)}">{inline(text, source)}</h{level}>')
            i += 1
            continue
        if "|" in line and i + 1 < len(lines) and re.fullmatch(r"[| :\-]+", lines[i + 1].strip()):
            rows = [[cell.strip() for cell in line.strip("|").split("|")]]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([cell.strip() for cell in lines[i].strip().strip("|").split("|")])
                i += 1
            table = '<div class="table-scroll"><table><thead><tr>'
            table += "".join("<th>" + inline(cell, source) + "</th>" for cell in rows[0])
            table += "</tr></thead><tbody>"
            for row in rows[1:]:
                table += "<tr>" + "".join("<td>" + inline(cell, source) + "</td>" for cell in row) + "</tr>"
            result.append(table + "</tbody></table></div>")
            continue
        bullet = re.match(r"^(?:[-*]|\d+\.)\s+(.+)$", line)
        if bullet:
            tag = "ol" if line[0].isdigit() else "ul"
            items, current = [], []
            while i < len(lines) and lines[i].strip():
                item = re.match(r"^\s*(?:[-*]|\d+\.)\s+(.+)$", lines[i])
                if item:
                    if current:
                        items.append(" ".join(current))
                    current = [item[1]]
                else:
                    current.append(lines[i].strip())
                i += 1
            if current:
                items.append(" ".join(current))
            result.append(f"<{tag}>" + "".join("<li>" + inline(item, source) + "</li>" for item in items) + f"</{tag}>")
            continue
        paragraph = [line]
        i += 1
        while i < len(lines) and lines[i].strip():
            if re.match(r"^(?:#{1,6}\s|```|[-*]\s|\d+\.\s)", lines[i].strip()):
                break
            paragraph.append(lines[i].strip())
            i += 1
        result.append("<p>" + inline(" ".join(paragraph), source) + "</p>")
    return "\n".join(result)


def build():
    for name in ("index.html", "app.js", "styles.css", "sample-data.js", "assets/icon.png"):
        destination = SITE / "demo" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "web" / name, destination)
    (SITE / "assets").mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "docs/images/web-demo.png", SITE / "assets/web-demo.png")
    desktop_screenshot = ROOT / "docs/images/desktop-demo.jpg"
    if desktop_screenshot.exists():
        shutil.copyfile(desktop_screenshot, SITE / "assets/desktop-demo.jpg")
    (SITE / "reference").mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "LICENSE", SITE / "reference/LICENSE.txt")
    for source in DOCS:
        body = markdown(source)
        first_heading = next(line for line in source.read_text(encoding="utf-8").splitlines() if line.startswith("# "))[2:]
        page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(first_heading)} | Tiny Tasklist</title><link rel="stylesheet" href="../styles.css"></head>
<body><a class="skip" href="#main">Skip to content</a>
<header class="page-header"><a class="brand" href="../index.html"><img src="../demo/assets/icon.png" alt="" width="30" height="30">Tiny Tasklist</a><nav aria-label="Main"><a href="../index.html">Project page</a><a href="../demo/?demo=1">Browser prototype</a></nav></header>
<main class="reference" id="main">{body}</main>
<footer class="page-footer"><a href="../index.html">Back to Tiny Tasklist</a><a href="LICENSE.txt">MIT license</a></footer></body></html>
'''
        (SITE / TARGETS[source.resolve()]).write_text(page, encoding="utf-8")
    print(f"Built site/: presentation assets, browser prototype and {len(DOCS)} reference pages.")


if __name__ == "__main__":
    build()
