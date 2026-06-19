from __future__ import annotations

import html.parser
import subprocess
import tempfile
from pathlib import Path


class ScriptExtractor(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_script = False
        self.current: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script":
            attr = dict(attrs)
            if attr.get("src"):
                return
            self.in_script = True
            self.current = []

    def handle_data(self, data: str) -> None:
        if self.in_script:
            self.current.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.in_script:
            self.scripts.append("".join(self.current))
            self.in_script = False
            self.current = []


def tracked_js_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "*.js"],
        check=True,
        text=True,
        capture_output=True,
    )
    return [Path(x) for x in result.stdout.splitlines() if x.strip()]


def check_node_syntax(path: Path) -> None:
    subprocess.run(["node", "--check", str(path)], check=True)


def main() -> None:
    for path in tracked_js_files():
        check_node_syntax(path)

    html_path = Path("index.html")
    parser = ScriptExtractor()
    parser.feed(html_path.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        for idx, script in enumerate(parser.scripts, start=1):
            candidate = script.strip()
            if not candidate:
                continue

            path = tmpdir / f"inline_{idx}.js"
            path.write_text(candidate, encoding="utf-8")
            check_node_syntax(path)

    print("javascript syntax OK")


if __name__ == "__main__":
    main()
