from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class StudioSelectorError(ValueError):
    """Raised when a Studio selector is malformed or outside the supported subset."""


@dataclass(frozen=True)
class SelectorPart:
    combinator: str | None
    simple: str


class SnapshotDom:
    """Parent/child graph reconstructed from captured DOM evidence."""

    def __init__(self, payload: dict[str, Any]) -> None:
        elements = payload.get("elements")
        if not isinstance(elements, list):
            raise StudioSelectorError("snapshot DOM elements are missing")
        self.order: list[str] = []
        self.nodes: dict[str, dict[str, Any]] = {}
        self.children: dict[str | None, list[str]] = {}
        for raw in elements:
            if not isinstance(raw, dict):
                continue
            node_id = str(raw.get("id") or "").strip()
            if not node_id or node_id in self.nodes:
                continue
            node = dict(raw)
            parent_id = str(node.get("parent_id") or "").strip() or None
            node["parent_id"] = parent_id
            self.nodes[node_id] = node
            self.order.append(node_id)
            self.children.setdefault(parent_id, []).append(node_id)

    def node(self, node_id: object) -> dict[str, Any] | None:
        return self.nodes.get(str(node_id or ""))

    def descendants(self, node_id: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        pending = list(self.children.get(node_id, []))
        visited: set[str] = set()
        while pending:
            child_id = pending.pop(0)
            if child_id in visited:
                continue
            visited.add(child_id)
            child = self.node(child_id)
            if child is None:
                continue
            output.append(child)
            pending[0:0] = self.children.get(child_id, [])
        return output

    def siblings_of_same_tag(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        tag = str(node.get("tag") or "").lower()
        return [
            sibling
            for child_id in self.children.get(node.get("parent_id"), [])
            if (sibling := self.node(child_id)) is not None
            and str(sibling.get("tag") or "").lower() == tag
        ]


def split_selector(selector: object) -> list[SelectorPart]:
    """Split child and descendant relationships without splitting inside brackets."""

    text = str(selector or "").strip()
    if not text:
        raise StudioSelectorError("selector must not be empty")
    if "," in text:
        raise StudioSelectorError("selector groups are not supported")

    values: list[SelectorPart] = []
    buffer: list[str] = []
    depth = 0
    quote: str | None = None
    next_combinator: str | None = None

    def flush() -> None:
        nonlocal buffer, next_combinator
        simple = "".join(buffer).strip()
        if simple:
            values.append(SelectorPart(next_combinator if values else None, simple))
            next_combinator = " "
        buffer = []

    index = 0
    while index < len(text):
        character = text[index]
        if quote:
            buffer.append(character)
            if character == quote and (index == 0 or text[index - 1] != "\\"):
                quote = None
            index += 1
            continue
        if character in {"'", '"'} and depth:
            quote = character
            buffer.append(character)
            index += 1
            continue
        if character in "[(":
            depth += 1
            buffer.append(character)
            index += 1
            continue
        if character in "])":
            depth -= 1
            if depth < 0:
                raise StudioSelectorError("selector has an unmatched closing token")
            buffer.append(character)
            index += 1
            continue
        if depth == 0 and character == ">":
            flush()
            if not values:
                raise StudioSelectorError("selector cannot start with a combinator")
            next_combinator = ">"
            index += 1
            while index < len(text) and text[index].isspace():
                index += 1
            continue
        if depth == 0 and character.isspace():
            flush()
            while index < len(text) and text[index].isspace():
                index += 1
            if index < len(text) and text[index] == ">":
                next_combinator = ">"
                index += 1
                while index < len(text) and text[index].isspace():
                    index += 1
            continue
        buffer.append(character)
        index += 1

    if quote or depth:
        raise StudioSelectorError("selector has an unclosed quote, bracket, or parenthesis")
    flush()
    if not values:
        raise StudioSelectorError("selector has no supported parts")
    return values


def _attributes(node: dict[str, Any]) -> dict[str, Any]:
    value = node.get("attributes")
    return value if isinstance(value, dict) else {}


def _classes(node: dict[str, Any]) -> set[str]:
    return {value for value in str(_attributes(node).get("class") or "").split() if value}


def _take_name(text: str, start: int) -> tuple[str, int]:
    index = start
    while index < len(text) and (text[index].isalnum() or text[index] in "_-:"):
        index += 1
    return text[start:index], index


def _parse_simple(selector: str) -> dict[str, Any]:
    text = selector.strip()
    parsed: dict[str, Any] = {"tag": "", "id": "", "classes": [], "attrs": [], "nth": None}
    index = 0
    if text and (text[0].isalpha() or text[0] == "*"):
        parsed["tag"], index = _take_name(text, 0)
    while index < len(text):
        marker = text[index]
        if marker == "#":
            name, index = _take_name(text, index + 1)
            if not name:
                raise StudioSelectorError(f"invalid ID selector: {selector}")
            parsed["id"] = name
            continue
        if marker == ".":
            name, index = _take_name(text, index + 1)
            if not name:
                raise StudioSelectorError(f"invalid class selector: {selector}")
            parsed["classes"].append(name)
            continue
        if marker == "[":
            end = text.find("]", index + 1)
            if end < 0:
                raise StudioSelectorError(f"unclosed attribute selector: {selector}")
            body = text[index + 1:end].strip()
            if "=" in body:
                name, expected = body.split("=", 1)
                expected = expected.strip().strip("\"").strip("'")
            else:
                name, expected = body, None
            name = name.strip()
            if not name:
                raise StudioSelectorError(f"invalid attribute selector: {selector}")
            parsed["attrs"].append((name, expected))
            index = end + 1
            continue
        prefix = ":nth-of-type("
        if text.startswith(prefix, index):
            end = text.find(")", index + len(prefix))
            if end < 0:
                raise StudioSelectorError(f"unclosed nth-of-type selector: {selector}")
            raw = text[index + len(prefix):end]
            if not raw.isdigit() or int(raw) < 1:
                raise StudioSelectorError(f"invalid nth-of-type selector: {selector}")
            parsed["nth"] = int(raw)
            index = end + 1
            continue
        raise StudioSelectorError(f"unsupported selector syntax: {selector}")
    return parsed


def matches_simple(dom: SnapshotDom, node: dict[str, Any], selector: object) -> bool:
    parsed = _parse_simple(str(selector or ""))
    tag = str(node.get("tag") or "").lower()
    if parsed["tag"] and parsed["tag"] != "*" and tag != str(parsed["tag"]).lower():
        return False
    attributes = _attributes(node)
    if parsed["id"] and str(attributes.get("id") or "") != parsed["id"]:
        return False
    node_classes = _classes(node)
    if any(name not in node_classes for name in parsed["classes"]):
        return False
    for name, expected in parsed["attrs"]:
        actual = attributes.get(name)
        if actual is None and name == "href":
            actual = node.get("href")
        if actual is None and name == "src":
            actual = node.get("src")
        if actual in {None, ""} or (expected is not None and str(actual) != expected):
            return False
    if parsed["nth"] is not None:
        siblings = dom.siblings_of_same_tag(node)
        position = next(
            (index for index, sibling in enumerate(siblings, 1) if sibling.get("id") == node.get("id")),
            None,
        )
        if position != parsed["nth"]:
            return False
    return True


def matches_selector(
    dom: SnapshotDom,
    node: dict[str, Any],
    selector: object,
    *,
    boundary_id: str | None = None,
) -> bool:
    parts = split_selector(selector)
    if not matches_simple(dom, node, parts[-1].simple):
        return False
    current = node
    for index in range(len(parts) - 1, 0, -1):
        previous = parts[index - 1]
        if parts[index].combinator == ">":
            if boundary_id and current.get("id") == boundary_id:
                return False
            parent = dom.node(current.get("parent_id"))
            if parent is None or not matches_simple(dom, parent, previous.simple):
                return False
            current = parent
            continue
        parent = dom.node(current.get("parent_id"))
        matched = None
        while parent is not None:
            if matches_simple(dom, parent, previous.simple):
                matched = parent
                break
            if boundary_id and parent.get("id") == boundary_id:
                break
            parent = dom.node(parent.get("parent_id"))
        if matched is None:
            return False
        current = matched
    return not (boundary_id and current.get("id") == boundary_id and len(parts) == 1)


def select_nodes(
    dom: SnapshotDom,
    selector: object,
    *,
    within_id: str | None = None,
) -> list[dict[str, Any]]:
    candidates = dom.descendants(within_id) if within_id else [dom.nodes[node_id] for node_id in dom.order]
    return [node for node in candidates if matches_selector(dom, node, selector, boundary_id=within_id)]


__all__ = [
    "SelectorPart",
    "SnapshotDom",
    "StudioSelectorError",
    "matches_selector",
    "matches_simple",
    "select_nodes",
    "split_selector",
]
