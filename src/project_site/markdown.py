"""The small Markdown subset the Context view renders: the hub's `CONTEXT.md` (og-dev-hub#15).

Headings, paragraphs, bulleted and numbered lists, bold, italics, code spans and
links, and nothing else: that is all a glossary uses. Every character of the
source is escaped before any markup is added, so text can never become markup,
and a link is kept only when it goes to `http(s)`, an anchor, or a relative path,
which is resolved against `base` (the file's directory on GitHub).
"""

from __future__ import annotations

import html
import re
from urllib.parse import urljoin

HEADING = re.compile(r"(#{1,6})\s+(.*?)\s*#*\s*\Z")
BULLET = re.compile(r"\s{0,3}[-*+]\s+(.*)\Z")
NUMBERED = re.compile(r"\s{0,3}\d+[.)]\s+(.*)\Z")
FENCE = re.compile(r"\s{0,3}(```|~~~)")
CODE = re.compile(r"`([^`]+)`")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
ITALIC = re.compile(r"(?<![\w*])([*_])(?=\S)(.+?)(?<=\S)\1(?![\w*])")


def slug(text: str) -> str:
    """A heading's anchor: lower case, words joined by `-`, nothing else."""
    words = re.sub(r"[^\w\s-]", "", re.sub(r"<[^>]+>", "", text).lower())
    return re.sub(r"[\s_]+", "-", words.strip()).strip("-")


def _url(target: str, base: str) -> str | None:
    if target.startswith("#"):
        return target
    if re.match(r"https?://", target):
        return target
    if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("//"):
        return None  # another scheme (`javascript:`, `data:`) is never a link
    return urljoin(base, target)


def inline(text: str, base: str) -> str:
    """One line's inline markup; `text` is raw source, escaped here first."""
    codes: list[str] = []

    def keep(match: re.Match[str]) -> str:
        codes.append(f"<code>{html.escape(match.group(1), quote=False)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = CODE.sub(keep, text)
    out: list[str] = []
    position = 0
    for match in LINK.finditer(text):
        out.append(_emphasis(html.escape(text[position:match.start()], quote=False)))
        label = _emphasis(html.escape(match.group(1), quote=False))
        url = _url(match.group(2), base)
        out.append(f'<a href="{html.escape(url, quote=True)}">{label}</a>' if url else label)
        position = match.end()
    out.append(_emphasis(html.escape(text[position:], quote=False)))
    return re.sub("\x00(\\d+)\x00", lambda m: codes[int(m.group(1))], "".join(out))


def _emphasis(text: str) -> str:
    text = BOLD.sub(lambda m: f"<strong>{m.group(2)}</strong>", text)
    return ITALIC.sub(lambda m: f"<em>{m.group(2)}</em>", text)


def render(text: str, *, base: str) -> str:
    """`text` as HTML. `base` is the URL a relative link is resolved against (ending in `/`)."""
    blocks: list[str] = []
    paragraph: list[str] = []
    items: list[str] = []
    kind = ""
    fence: list[str] | None = None

    def close() -> None:
        nonlocal kind
        if paragraph:
            blocks.append(f"<p>{inline(' '.join(paragraph), base)}</p>")
            paragraph.clear()
        if items:
            blocks.append(f"<{kind}>\n" + "\n".join(f"<li>{inline(i, base)}</li>" for i in items) + f"\n</{kind}>")
            items.clear()
        kind = ""

    for line in text.splitlines():
        if fence is not None:
            if FENCE.match(line):
                blocks.append("<pre><code>" + html.escape("\n".join(fence), quote=False) + "</code></pre>")
                fence = None
            else:
                fence.append(line)
            continue
        if FENCE.match(line):
            close()
            fence = []
            continue
        if not line.strip():
            close()
            continue
        if heading := HEADING.match(line):
            close()
            level, words = len(heading.group(1)), heading.group(2)
            body = inline(words, base)
            blocks.append(f'<h{level} id="{slug(body)}">{body}</h{level}>')
            continue
        listed = BULLET.match(line) or NUMBERED.match(line)
        if listed:
            wanted = "ul" if BULLET.match(line) else "ol"
            if paragraph or (kind and kind != wanted):
                close()
            kind = wanted
            items.append(listed.group(1))
            continue
        if items and line.startswith((" ", "\t")):
            items[-1] += " " + line.strip()  # a list item's continuation line
            continue
        if items:
            close()
        paragraph.append(line.strip())
    if fence is not None:
        blocks.append("<pre><code>" + html.escape("\n".join(fence), quote=False) + "</code></pre>")
    close()
    return "\n".join(blocks) + "\n"
