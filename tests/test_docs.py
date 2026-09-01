from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).parents[1]


class SvgInspector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.title_text = ""
        self.description_text = ""
        self._active_tag = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self._active_tag = tag

    def handle_endtag(self, tag: str) -> None:
        if self._active_tag == tag:
            self._active_tag = ""

    def handle_data(self, data: str) -> None:
        if self._active_tag == "title":
            self.title_text += data
        if self._active_tag == "desc":
            self.description_text += data


def test_readme_uses_committed_architecture_image() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "![AWS Serverless Audit Lab architecture](docs/architecture.svg)" in readme
    assert "```mermaid" not in readme


def test_architecture_svg_is_accessible_and_script_free() -> None:
    inspector = SvgInspector()
    inspector.feed((ROOT / "docs/architecture.svg").read_text(encoding="utf-8"))

    assert inspector.tags[0] == "svg"
    assert inspector.title_text.strip()
    assert inspector.description_text.strip()
    assert "script" not in inspector.tags
