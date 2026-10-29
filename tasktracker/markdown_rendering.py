import re

import bleach
from markdown import Markdown
from markdown.inlinepatterns import SimpleTagInlineProcessor

INLINE_TAGS = {"a", "strong", "em", "b", "i", "code", "del", "s", "br"}
PREVIEW_TAGS = INLINE_TAGS | {"p", "ul", "ol", "li"}
ALLOWED_TAGS = INLINE_TAGS | {
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
    "blockquote", "pre", "hr", "table", "thead", "tbody", "tr", "th", "td",
}
ALLOWED_ATTRIBUTES = {"a": ["href", "title"], "ol": ["start"]}
ALLOWED_PROTOCOLS = {"http", "https", "mailto"}
LIST_ITEM = re.compile(r"^[ ]{0,3}(?:[*+-]|\d+\.)[ \t]+")
FENCE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})")


def _allow_list_after_text(source: str) -> str:
    """Let a list start after a single newline, as users commonly expect."""
    lines = source.splitlines()
    rendered_lines: list[str] = []
    fence: tuple[str, int] | None = None

    for line in lines:
        fence_match = FENCE.match(line)
        if fence is not None:
            rendered_lines.append(line)
            if (fence_match is not None
                    and fence_match.group(1)[0] == fence[0]
                    and len(fence_match.group(1)) >= fence[1]
                    and not line[fence_match.end():].strip()):
                fence = None
            continue

        if fence_match is not None:
            marker = fence_match.group(1)
            fence = (marker[0], len(marker))
        elif (LIST_ITEM.match(line) and rendered_lines
              and rendered_lines[-1].strip()
              and not LIST_ITEM.match(rendered_lines[-1])):
            rendered_lines.append("")

        rendered_lines.append(line)

    return "\n".join(rendered_lines)


def render_markdown(source: str | None) -> str:
    """Render untrusted Markdown as sanitised HTML for an element's contents."""
    if not source:
        return ""
    # Markdown and Bleach parsers are created per call, not shared across requests.
    renderer = Markdown(extensions=["fenced_code", "tables", "sane_lists", "nl2br"])
    renderer.inlinePatterns.register(
        SimpleTagInlineProcessor(r"(?<!~)(~~)(?=\S)(.+?)(?<=\S)\1(?!~)", "del"),
        "strikethrough",
        175,
    )
    return bleach.clean(
        renderer.convert(_allow_list_after_text(source)),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )


def render_markdown_preview(source: str | None) -> str:
    """Keep paragraphs and lists while omitting large block elements in previews."""
    return bleach.clean(
        render_markdown(source),
        tags=PREVIEW_TAGS,
        attributes={"a": ["href", "title"], "ol": ["start"]},
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )
