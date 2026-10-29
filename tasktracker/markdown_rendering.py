import bleach
from markdown import Markdown
from markdown.inlinepatterns import SimpleTagInlineProcessor

INLINE_TAGS = {"a", "strong", "em", "b", "i", "code", "del", "s", "br"}
ALLOWED_TAGS = INLINE_TAGS | {
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
    "blockquote", "pre", "hr", "table", "thead", "tbody", "tr", "th", "td",
}
ALLOWED_ATTRIBUTES = {"a": ["href", "title"], "ol": ["start"]}
ALLOWED_PROTOCOLS = {"http", "https", "mailto"}


def render_markdown(source: str | None) -> str:
    """Render untrusted Markdown as sanitised HTML for an element's contents."""
    if not source:
        return ""
    # Markdown and Bleach parsers are created per call, not shared across requests.
    renderer = Markdown(extensions=["fenced_code", "tables", "sane_lists"])
    renderer.inlinePatterns.register(
        SimpleTagInlineProcessor(r"(?<!~)(~~)(?=\S)(.+?)(?<=\S)\1(?!~)", "del"),
        "strikethrough",
        175,
    )
    return bleach.clean(
        renderer.convert(source),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )


def render_markdown_preview(source: str | None) -> str:
    """Flatten block markup so the browser can clamp a single inline text flow."""
    return bleach.clean(
        render_markdown(source),
        tags=INLINE_TAGS,
        attributes={"a": ["href", "title"]},
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )
