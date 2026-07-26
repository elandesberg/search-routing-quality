"""Lightweight structural invariants for the self-contained framing document."""

from html.parser import HTMLParser
from pathlib import Path


class StructureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.figure_count = 0
        self.ids = []

    def handle_starttag(self, tag, attrs):
        if tag == "figure":
            self.figure_count += 1
        for name, value in attrs:
            if name == "id":
                self.ids.append(value)


def main():
    source = Path("docs/index.html").read_text(encoding="utf-8")
    parser = StructureParser()
    parser.feed(source)
    parser.close()
    if parser.figure_count != 5:
        raise SystemExit(f"expected 5 figures, found {parser.figure_count}")
    if len(parser.ids) != len(set(parser.ids)):
        raise SystemExit("duplicate HTML id attributes found")
    required_theme_markers = (
        "prefers-color-scheme: dark",
        'data-theme="dark"',
        'id="t"',
    )
    missing = [marker for marker in required_theme_markers if marker not in source]
    if missing:
        raise SystemExit(f"missing theme-support markers: {missing}")
    print("HTML invariants passed: 5 figures, unique ids, light/dark theme support")


if __name__ == "__main__":
    main()
