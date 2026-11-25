"""Utilities for converting provider job descriptions from HTML to plain text."""

from __future__ import annotations

import re
from html.parser import HTMLParser

_BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "body",
    "dd", "div", "dl", "dt", "fieldset", "figcaption",
    "figure", "footer", "form", "h1", "h2", "h3",
    "h4", "h5", "h6", "header", "hr", "li", "main",
    "nav", "ol", "p", "pre", "section", "table",
    "tbody", "tfoot", "thead", "tr", "ul",
}

_SKIP_TAGS = {"script", "style", "noscript", "svg"}

_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img",
    "input", "link", "meta", "param", "source", "track", "wbr",
}


class _HTMLTextExtractor(HTMLParser):
    """Extract readable text while retaining basic document structure."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_stack: list[str] = []

    def _newline(self) -> None:
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def _last_visible_char(self) -> str | None:
        for part in reversed(self.parts):
            for char in reversed(part):
                if not char.isspace():
                    return char
        return None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag = tag.lower()

        if self.skip_stack:
            if tag in _SKIP_TAGS:
                self.skip_stack.append(tag)
            return

        if tag in _SKIP_TAGS:
            self.skip_stack.append(tag)
            return

        if tag in _BLOCK_TAGS or tag == "br":
            self._newline()

        if tag == "li":
            self.parts.append("• ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if self.skip_stack:
            for index in range(len(self.skip_stack) - 1, -1, -1):
                if self.skip_stack[index] == tag:
                    del self.skip_stack[index:]
                    break
            return

        if tag in _BLOCK_TAGS:
            self._newline()

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)

        if tag.lower() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.skip_stack:
            return

        # Normalize soft line wraps inside a paragraph or list item.
        data = re.sub(r"\s+", " ", data)
        if not data:
            return

        first = next((char for char in data if not char.isspace()), None)
        previous = self._last_visible_char()

        # HTML may split adjacent words into separate text chunks.
        if (
            first is not None
            and previous is not None
            and first.isalnum()
            and previous.isalnum()
        ):
            self.parts.append(" ")

        self.parts.append(data)


def clean_job_description(description: str | None) -> str:
    """Convert an HTML job description into readable plain text.

    Keeps headings, paragraphs and list items on separate lines.
    Does not modify the original description stored in JobPosting.
    """
    if not description or not description.strip():
        return ""

    parser = _HTMLTextExtractor()
    parser.feed(description)
    parser.close()

    raw_text = "".join(parser.parts).replace("\xa0", " ")

    # Repair missing spaces after punctuation at HTML tag boundaries.
    raw_text = re.sub(r"(?<=[,;:!?])(?=\w)", " ", raw_text)

    lines = []
    for line in raw_text.splitlines():
        normalized = re.sub(r"\s+", " ", line).strip()

        # An empty HTML list item must not become a standalone bullet.
        if normalized and normalized != "•":
            lines.append(normalized)

    return "\n".join(lines)
