from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 1
SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ATTRIBUTE_RE = re.compile(r"^[A-Za-z_:][A-Za-z0-9_.:-]{0,63}$")
SURFACE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CONFIG = SURFACE_DIR / "conf" / "event_sources.json"
DEFAULT_STUDIO_ROOT = SURFACE_DIR / ".env" / "local_event_studio"


class StudioRuleError(RuntimeError):
    """Base error for Local Event Studio rule storage operations."""


class UnknownSourceError(StudioRuleError):
    """Raised when a rule references a source absent from event_sources.json."""


class UnknownListingError(StudioRuleError):
    """Raised when a rule references a listing URL not configured for its source."""


class RuleNotFoundError(StudioRuleError):
    """Raised when a requested draft, published rule, or history version is missing."""


class RuleConflictError(StudioRuleError):
    """Raised when immutable history or a storage invariant would be overwritten."""


class RuleStorageError(StudioRuleError):
    """Raised when persisted rule content is malformed or unsafe to use."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_listing_url(value: object) -> str:
    """Normalize configured listing URLs for exact source/listing identity checks."""

    raw = str(value or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("listing_url must be an absolute HTTP or HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("listing_url must not contain user information")
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.query,
            "",
        )
    )


def _selector(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("selector must not be empty")
    if len(text) > 500:
        raise ValueError("selector must not exceed 500 characters")
    if any(ord(character) < 32 for character in text):
        raise ValueError("selector must not contain control characters")
    return text


class SelectorRule(BaseModel):
    """One explicit DOM selector and optional attribute extraction rule."""

    model_config = ConfigDict(extra="forbid")

    selector: str = Field(..., description="CSS selector evaluated inside the owning card or detail page.")
    attribute: str | None = Field(None, description="HTML attribute to read instead of text content.")
    optional: bool = Field(False, description="Whether a missing value may be accepted.")

    @field_validator("selector", mode="before")
    @classmethod
    def validate_selector(cls, value: object) -> str:
        return _selector(value)

    @field_validator("attribute", mode="before")
    @classmethod
    def validate_attribute(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not ATTRIBUTE_RE.fullmatch(text):
            raise ValueError("attribute must be a valid HTML attribute name")
        return text.lower()


class VenueSelectorRule(SelectorRule):
    """Venue selector with an explicit opt-in for the configured source default."""

    allow_source_default: bool = Field(
        False,
        description="Allow the source default venue only when no mapped venue exists.",
    )


class CardRule(BaseModel):
    """DOM selector contract for repeated activity cards on one listing page."""

    model_config = ConfigDict(extra="forbid")

    selector: str
    exclude_selectors: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("selector", mode="before")
    @classmethod
    def validate_selector(cls, value: object) -> str:
        return _selector(value)

    @field_validator("exclude_selectors", mode="before")
    @classmethod
    def validate_exclusions(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("exclude_selectors must be a list")
        output: list[str] = []
        for raw in value:
            selector = _selector(raw)
            if selector not in output:
                output.append(selector)
        return output


class FieldMappings(BaseModel):
    """Typed field selectors supported by the Local Event Studio rule format."""

    model_config = ConfigDict(extra="forbid")

    title: SelectorRule | None = None
    when: SelectorRule | None = None
    where: VenueSelectorRule | None = None
    url: SelectorRule | None = None
    summary: SelectorRule | None = None
    image: SelectorRule | None = None

    @model_validator(mode="after")
    def validate_attributes(self) -> "FieldMappings":
        for name in ("title", "when", "where", "summary"):
            rule = getattr(self, name)
            if rule is not None and rule.attribute is not None:
                raise ValueError(f"{name} must read text content, not an attribute")
        if self.url is not None and self.url.attribute != "href":
            raise ValueError("url must read the href attribute")
        if self.image is not None and self.image.attribute not in {"src", "data-src", "data-lazy-src"}:
            raise ValueError("image must read src, data-src, or data-lazy-src")
        return self


class DetailPageRule(BaseModel):
    """Optional detail-page field mappings for one admitted public detail URL."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    fields: FieldMappings = Field(default_factory=FieldMappings)

    @model_validator(mode="after")
    def validate_enabled_fields(self) -> "DetailPageRule":
        if not self.enabled and any(
            getattr(self.fields, name) is not None
            for name in ("title", "when", "where", "url", "summary", "image")
        ):
            raise ValueError("detail_page fields require enabled=true")
        if self.fields.url is not None:
            raise ValueError("detail_page must not replace the admitted public detail URL")
        return self


class ValidationRule(BaseModel):
    """Mandatory output checks applied when a Studio rule is published."""

    model_config = ConfigDict(extra="forbid")

    require_public_detail_url: bool = True
    require_current_or_future_date: bool = True


class LocalEventStudioRule(BaseModel):
    """Persisted draft or published rule bound to one configured listing page."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    source_id: str
    listing_url: str
    version: int = Field(0, ge=0)
    status: Literal["draft", "published"] = "draft"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    published_at: datetime | None = None
    based_on_version: int | None = Field(None, ge=1)
    card: CardRule | None = None
    fields: FieldMappings = Field(default_factory=FieldMappings)
    detail_page: DetailPageRule = Field(default_factory=DetailPageRule)
    validation: ValidationRule = Field(default_factory=ValidationRule)

    @field_validator("source_id", mode="before")
    @classmethod
    def validate_source_id(cls, value: object) -> str:
        text = str(value or "").strip()
        if not SOURCE_ID_RE.fullmatch(text):
            raise ValueError("source_id must be a safe configured identifier")
        return text

    @field_validator("listing_url", mode="before")
    @classmethod
    def validate_listing_url(cls, value: object) -> str:
        return canonical_listing_url(value)

    @model_validator(mode="after")
    def validate_status_contract(self) -> "LocalEventStudioRule":
        if self.status == "draft":
            if self.version != 0:
                raise ValueError("draft version must be 0")
            if self.published_at is not None or self.based_on_version is not None:
                raise ValueError("draft must not carry publication metadata")
            return self

        if self.version < 1:
            raise ValueError("published version must be at least 1")
        if self.card is None:
            raise ValueError("published rule requires card selector")
        missing = [
            name
            for name in ("title", "when", "where", "url")
            if getattr(self.fields, name) is None
        ]
        if missing:
            raise ValueError(f"published rule missing required fields: {', '.join(missing)}")
        return self


class SourceDefinition(BaseModel):
    """Subset of event_sources.json required for rule binding validation."""

    model_config = ConfigDict(extra="allow")

    id: str
    listing_urls: list[str] = Field(default_factory=list)


class SourceInventory(BaseModel):
    """Typed event source inventory loaded from the committed configuration."""

    model_config = ConfigDict(extra="allow")

    sources: list[SourceDefinition] = Field(default_factory=list)


class LocalEventStudioRuleStore:
    """Validate, version, and atomically persist Local Event Studio rules."""

    def __init__(
        self,
        root: Path | str = DEFAULT_STUDIO_ROOT,
        source_config_path: Path | str = DEFAULT_SOURCE_CONFIG,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.source_config_path = Path(source_config_path).expanduser().resolve()

    def _inventory(self) -> SourceInventory:
        try:
            raw = json.loads(self.source_config_path.read_text(encoding="utf-8"))
            return SourceInventory.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise RuleStorageError(f"invalid source configuration: {exc}") from exc

    def configured_sources(self) -> list[SourceDefinition]:
        """Return typed configured sources without exposing mutable config dictionaries."""

        return list(self._inventory().sources)

    def _binding(self, source_id: object, listing_url: object) -> tuple[str, str]:
        safe_source = str(source_id or "").strip()
        if not SOURCE_ID_RE.fullmatch(safe_source):
            raise UnknownSourceError("source_id is not a safe configured identifier")
        canonical_url = canonical_listing_url(listing_url)

        source = next(
            (item for item in self._inventory().sources if item.id == safe_source),
            None,
        )
        if source is None:
            raise UnknownSourceError(f"unknown source_id: {safe_source}")

        allowed = {canonical_listing_url(value) for value in source.listing_urls}
        if canonical_url not in allowed:
            raise UnknownListingError(
                f"listing URL is not configured for source {safe_source}: {canonical_url}"
            )
        return safe_source, canonical_url

    def _rules_root(self) -> Path:
        rules_root = self.root / "rules"
        if rules_root.is_symlink():
            raise RuleStorageError("rules root must not be a symlink")
        rules_root.mkdir(parents=True, exist_ok=True)
        try:
            rules_root.resolve().relative_to(self.root)
        except ValueError as exc:
            raise RuleStorageError("rules root escapes the Studio root") from exc
        return rules_root

    def _binding_dir(self, source_id: object, listing_url: object) -> tuple[Path, str, str]:
        safe_source, canonical_url = self._binding(source_id, listing_url)
        listing_key = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:20]
        rules_root = self._rules_root()
        source_dir = rules_root / safe_source
        if source_dir.is_symlink():
            raise RuleStorageError("rule source directory must not be a symlink")
        source_dir.mkdir(parents=True, exist_ok=True)
        target = source_dir / listing_key
        if target.is_symlink():
            raise RuleStorageError("rule listing directory must not be a symlink")
        try:
            target.resolve().relative_to(rules_root.resolve())
        except ValueError as exc:
            raise RuleStorageError("resolved rule path escapes the Studio root") from exc
        return target, safe_source, canonical_url

    @staticmethod
    def _model_payload(rule: LocalEventStudioRule) -> dict[str, Any]:
        return rule.model_dump(mode="json", exclude_none=True)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        try:
            descriptor = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _safe_parent(self, target: Path) -> Path:
        parent = target.parent
        if parent.is_symlink():
            raise RuleStorageError(f"rule parent must not be a symlink: {parent.name}")
        parent.mkdir(parents=True, exist_ok=True)
        try:
            parent.resolve().relative_to(self._rules_root().resolve())
        except ValueError as exc:
            raise RuleStorageError("rule parent escapes the Studio root") from exc
        return parent

    def _atomic_write(
        self,
        target: Path,
        payload: dict[str, Any],
        *,
        immutable: bool = False,
    ) -> None:
        parent = self._safe_parent(target)
        if target.is_symlink():
            raise RuleStorageError(f"refusing to replace symlink: {target.name}")

        temporary = parent / f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            if immutable:
                try:
                    os.link(temporary, target)
                except FileExistsError as exc:
                    raise RuleConflictError(
                        f"immutable history already exists: {target.name}"
                    ) from exc
                finally:
                    temporary.unlink(missing_ok=True)
            else:
                os.replace(temporary, target)
            self._fsync_directory(parent)
        finally:
            temporary.unlink(missing_ok=True)

    def _read_rule(self, path: Path, *, required: bool = False) -> LocalEventStudioRule | None:
        if path.is_symlink():
            raise RuleStorageError(f"refusing to read symlink rule: {path.name}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return LocalEventStudioRule.model_validate(raw)
        except FileNotFoundError:
            if required:
                raise RuleNotFoundError(f"rule not found: {path.name}")
            return None
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise RuleStorageError(f"invalid persisted rule {path}: {exc}") from exc

    def _draft_path(self, source_id: object, listing_url: object) -> tuple[Path, str, str]:
        directory, safe_source, canonical_url = self._binding_dir(source_id, listing_url)
        return directory / "draft.json", safe_source, canonical_url

    def _published_path(self, source_id: object, listing_url: object) -> tuple[Path, str, str]:
        directory, safe_source, canonical_url = self._binding_dir(source_id, listing_url)
        return directory / "published.json", safe_source, canonical_url

    def _history_dir(self, source_id: object, listing_url: object) -> tuple[Path, str, str]:
        directory, safe_source, canonical_url = self._binding_dir(source_id, listing_url)
        history = directory / "history"
        if history.is_symlink():
            raise RuleStorageError("rule history directory must not be a symlink")
        return history, safe_source, canonical_url

    def save_draft(
        self,
        raw: LocalEventStudioRule | dict[str, Any],
    ) -> LocalEventStudioRule:
        """Validate and atomically replace the draft for one configured listing."""

        data = raw.model_dump(mode="python") if isinstance(raw, LocalEventStudioRule) else dict(raw)
        source_id, listing_url = self._binding(
            data.get("source_id"),
            data.get("listing_url"),
        )
        draft_path, _, _ = self._draft_path(source_id, listing_url)
        previous = self._read_rule(draft_path)
        current = utc_now()

        data.update(
            {
                "schema_version": SCHEMA_VERSION,
                "source_id": source_id,
                "listing_url": listing_url,
                "version": 0,
                "status": "draft",
                "created_at": previous.created_at if previous else current,
                "updated_at": current,
                "published_at": None,
                "based_on_version": None,
            }
        )
        draft = LocalEventStudioRule.model_validate(data)
        self._atomic_write(draft_path, self._model_payload(draft))
        return draft

    def load_draft(
        self,
        source_id: object,
        listing_url: object,
    ) -> LocalEventStudioRule | None:
        """Load the current draft for a configured listing, when present."""

        path, _, _ = self._draft_path(source_id, listing_url)
        return self._read_rule(path)

    def delete_draft(self, source_id: object, listing_url: object) -> bool:
        """Delete only the mutable draft; published and history files are untouched."""

        path, _, _ = self._draft_path(source_id, listing_url)
        if path.is_symlink():
            raise RuleStorageError("refusing to delete a symlink draft")
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        self._fsync_directory(path.parent)
        return True

    def load_published(
        self,
        source_id: object,
        listing_url: object,
    ) -> LocalEventStudioRule | None:
        """Load the active published rule for a configured listing, when present."""

        path, _, _ = self._published_path(source_id, listing_url)
        return self._read_rule(path)

    def list_history(
        self,
        source_id: object,
        listing_url: object,
    ) -> list[LocalEventStudioRule]:
        """Return every immutable published version in ascending order."""

        history_dir, _, _ = self._history_dir(source_id, listing_url)
        if not history_dir.exists():
            return []
        output: list[LocalEventStudioRule] = []
        for path in sorted(history_dir.glob("v*.json")):
            rule = self._read_rule(path, required=True)
            if rule is None or rule.status != "published":
                raise RuleStorageError(f"history entry is not published: {path.name}")
            output.append(rule)
        output.sort(key=lambda item: item.version)
        return output

    def _next_version(self, source_id: str, listing_url: str) -> int:
        versions = [rule.version for rule in self.list_history(source_id, listing_url)]
        published = self.load_published(source_id, listing_url)
        if published is not None:
            versions.append(published.version)
        return max(versions, default=0) + 1

    def _publish_rule(
        self,
        data: dict[str, Any],
        *,
        source_id: str,
        listing_url: str,
        based_on_version: int | None = None,
    ) -> LocalEventStudioRule:
        current = utc_now()
        version = self._next_version(source_id, listing_url)
        data.update(
            {
                "schema_version": SCHEMA_VERSION,
                "source_id": source_id,
                "listing_url": listing_url,
                "version": version,
                "status": "published",
                "updated_at": current,
                "published_at": current,
                "based_on_version": based_on_version,
            }
        )
        data.setdefault("created_at", current)
        published = LocalEventStudioRule.model_validate(data)

        history_dir, _, _ = self._history_dir(source_id, listing_url)
        history_path = history_dir / f"v{version:06d}.json"
        published_path, _, _ = self._published_path(source_id, listing_url)

        payload = self._model_payload(published)
        self._atomic_write(history_path, payload, immutable=True)
        self._atomic_write(published_path, payload)
        return published

    def publish(
        self,
        source_id: object,
        listing_url: object,
    ) -> LocalEventStudioRule:
        """Publish the current draft as the next immutable version."""

        safe_source, canonical_url = self._binding(source_id, listing_url)
        draft_path, _, _ = self._draft_path(safe_source, canonical_url)
        draft = self._read_rule(draft_path, required=True)
        if draft is None:
            raise RuleNotFoundError("draft not found")
        published = self._publish_rule(
            draft.model_dump(mode="python"),
            source_id=safe_source,
            listing_url=canonical_url,
        )
        self.delete_draft(safe_source, canonical_url)
        return published

    def rollback(
        self,
        source_id: object,
        listing_url: object,
        version: int,
    ) -> LocalEventStudioRule:
        """Republish one historical version as a new monotonic version."""

        safe_source, canonical_url = self._binding(source_id, listing_url)
        if version < 1:
            raise RuleNotFoundError("history version must be at least 1")
        history_dir, _, _ = self._history_dir(safe_source, canonical_url)
        historical = self._read_rule(
            history_dir / f"v{version:06d}.json",
            required=True,
        )
        if historical is None:
            raise RuleNotFoundError(f"history version not found: {version}")
        data = historical.model_dump(mode="python")
        data.pop("published_at", None)
        data.pop("updated_at", None)
        return self._publish_rule(
            data,
            source_id=safe_source,
            listing_url=canonical_url,
            based_on_version=version,
        )

    def export_rule(
        self,
        source_id: object,
        listing_url: object,
        *,
        status: Literal["draft", "published"] = "published",
        version: int | None = None,
    ) -> str:
        """Export one validated rule as stable JSON without exposing filesystem paths."""

        safe_source, canonical_url = self._binding(source_id, listing_url)
        if version is not None:
            if version < 1:
                raise RuleNotFoundError("history version must be at least 1")
            history_dir, _, _ = self._history_dir(safe_source, canonical_url)
            rule = self._read_rule(
                history_dir / f"v{version:06d}.json",
                required=True,
            )
        elif status == "draft":
            rule = self.load_draft(safe_source, canonical_url)
        else:
            rule = self.load_published(safe_source, canonical_url)

        if rule is None:
            raise RuleNotFoundError(f"{status} rule not found")
        return json.dumps(
            self._model_payload(rule),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"

    def import_draft(
        self,
        payload: str | bytes | dict[str, Any] | LocalEventStudioRule,
    ) -> LocalEventStudioRule:
        """Import validated JSON as a mutable draft without importing version history."""

        if isinstance(payload, LocalEventStudioRule):
            raw: dict[str, Any] = payload.model_dump(mode="python")
        elif isinstance(payload, dict):
            raw = dict(payload)
        else:
            try:
                text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
                decoded = json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuleStorageError(f"invalid rule import: {exc}") from exc
            if not isinstance(decoded, dict):
                raise RuleStorageError("imported rule must be a JSON object")
            raw = decoded

        validated = LocalEventStudioRule.model_validate(raw)
        return self.save_draft(validated)


__all__ = [
    "CardRule",
    "DEFAULT_SOURCE_CONFIG",
    "DEFAULT_STUDIO_ROOT",
    "DetailPageRule",
    "FieldMappings",
    "LocalEventStudioRule",
    "LocalEventStudioRuleStore",
    "RuleConflictError",
    "RuleNotFoundError",
    "RuleStorageError",
    "SCHEMA_VERSION",
    "SelectorRule",
    "SourceDefinition",
    "SourceInventory",
    "StudioRuleError",
    "UnknownListingError",
    "UnknownSourceError",
    "ValidationRule",
    "VenueSelectorRule",
    "canonical_listing_url",
]
