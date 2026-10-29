from html.parser import HTMLParser

import pytest

from tasktracker.markdown_rendering import ALLOWED_TAGS, render_markdown, render_markdown_preview


class Elements(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


@pytest.mark.parametrize('renderer', [render_markdown, render_markdown_preview])
def test_inline_markdown_and_safe_links(renderer):
    html = renderer('**Bold** *italic* ~~removed~~ `inline` [web](https://example.com)')
    assert '<strong>Bold</strong>' in html
    assert '<em>italic</em>' in html
    assert '<del>removed</del>' in html
    assert '<code>inline</code>' in html
    assert '<a href="https://example.com">web</a>' in html
    assert renderer(None) == ''
    assert renderer('') == ''


def test_full_markdown_blocks():
    source = '''# Heading

Paragraph.

1. Ordered
2. Second

- Unordered

> Quoted

```python
print("code")
```

| Name | Value |
| --- | --- |
| A | B |
'''
    full = render_markdown(source)
    for tag in ['h1', 'p', 'ol', 'ul', 'li', 'blockquote', 'pre', 'code', 'table', 'th', 'td']:
        assert f'<{tag}>' in full
    preview = render_markdown_preview(source)
    assert '<h1>' not in preview and '<table>' not in preview and '<pre>' not in preview
    assert 'Heading' in preview and 'Ordered' in preview and 'Quoted' in preview
    assert '<code>' in preview


@pytest.mark.parametrize('renderer', [render_markdown, render_markdown_preview])
@pytest.mark.parametrize('url', ['http://example.com', 'https://example.com', 'mailto:hello@example.com'])
def test_allowed_link_schemes(renderer, url):
    assert f'href="{url}"' in renderer(f'[Link]({url})')


@pytest.mark.parametrize('renderer', [render_markdown, render_markdown_preview])
@pytest.mark.parametrize('payload', [
    '<script>alert(1)</script>',
    '<img src="https://tracker.invalid/pixel" onerror="alert(1)">',
    '<p onclick="alert(1)" style="color:red">Text</p>',
    '<a href="javascript:alert(1)" onmouseover="alert(1)">Link</a>',
    '<a href="java&#x73;cript:alert(1)">Link</a>',
    '<a href="java\nscript:alert(1)">Link</a>',
    '[Link](javascript:alert(1))',
    '[Link](data:text/html;base64,PHNjcmlwdD4=)',
    '<a href="vbscript:msgbox(1)">Link</a>',
    '<iframe srcdoc="<script>alert(1)</script>"></iframe>',
    '<svg><a xlink:href="javascript:alert(1)">Link</a></svg>',
    '<math><mtext><img src=x onerror=alert(1)></mtext></math>',
    '<form action="/tasks/1/complete"><button>Submit</button></form>',
    '<a href="https://example.com" target="_blank" id="x" class="task">Safe</a>',
    '<!-- hidden --><style>body { display:none }</style>',
])
def test_untrusted_html_is_sanitized(renderer, payload):
    html = renderer(payload)
    for tag, attributes in Elements(html).elements:
        assert tag in ALLOWED_TAGS
        assert set(attributes) <= ({'href', 'title'} if tag == 'a' else {'start'} if tag == 'ol' else set())
        href = attributes.get('href', '').lower()
        assert not any(scheme in href for scheme in ['javascript:', 'data:', 'vbscript:'])
    assert '<!--' not in html


def test_code_is_escaped_not_executed():
    html = render_markdown('```html\n<script>alert(1)</script>\n```')
    assert '<pre><code>' in html
    assert '&lt;script&gt;' in html
    assert all(tag != 'script' for tag, _ in Elements(html).elements)
