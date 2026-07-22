from __future__ import annotations

import copy
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from .event_review import EventReviewStore, ReviewState


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CollectionAlreadyRunning(RuntimeError):
    def __init__(self, job: dict[str, Any]) -> None:
        super().__init__("event candidate collection is already running")
        self.job = job


class CollectionStoreView:
    """Expose an optional listing scope without mutating listing decisions.

    Per-listing Preview previously changed persisted decisions to make one page look
    confirmed, ran the synchronous collector, then restored the decisions. That is
    unsafe once collection runs in the background. This view supplies a scoped copy
    to the collector while all writes still target the real Review store.
    """

    def __init__(
        self,
        store: EventReviewStore,
        mutation_lock: threading.Lock,
        listing_candidate_ids: Iterable[str] | None = None,
    ) -> None:
        self._store = store
        self._mutation_lock = mutation_lock
        self._listing_candidate_ids = {
            str(value).strip()
            for value in (listing_candidate_ids or [])
            if str(value).strip()
        }

    def load(self) -> ReviewState:
        state = self._store.load()
        if not self._listing_candidate_ids:
            return state

        scoped = state.model_copy(deep=True)
        found: set[str] = set()
        for listing in scoped.listing_pages:
            if listing.candidate_id in self._listing_candidate_ids:
                listing.decision = "confirmed"
                found.add(listing.candidate_id)
            elif listing.decision == "confirmed":
                listing.decision = "pending"

        missing = self._listing_candidate_ids - found
        if missing:
            raise ValueError(
                "listing candidate not found: " + ", ".join(sorted(missing))
            )
        return scoped

    def inventory(self) -> list[dict[str, Any]]:
        return self._store.inventory()

    def replace_events(
        self,
        candidates,
        collection: dict[str, Any],
    ) -> ReviewState:
        with self._mutation_lock:
            return self._store.replace_events(candidates, collection)


class EventCollectionJobManager:
    """Own one non-blocking Review Event collection job per server process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._job: dict[str, Any] = {
            "job_id": "",
            "status": "idle",
            "stage": "idle",
            "message": "No Event collection is running.",
            "started_at": None,
            "updated_at": utc_now(),
            "completed_at": None,
            "elapsed_seconds": 0,
            "listing_candidate_ids": [],
            "candidate_count": 0,
            "confirmed_listing_count": 0,
            "error_count": 0,
            "errors": [],
        }
        self._started_monotonic: float | None = None
        self._thread: threading.Thread | None = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            payload = copy.deepcopy(self._job)
            if payload.get("status") == "running" and self._started_monotonic is not None:
                payload["elapsed_seconds"] = max(
                    0,
                    int(time.monotonic() - self._started_monotonic),
                )
            payload["thread_alive"] = bool(self._thread and self._thread.is_alive())
            return payload

    def start(
        self,
        runner: Callable[[], ReviewState],
        listing_candidate_ids: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        scope = sorted(
            {
                str(value).strip()
                for value in (listing_candidate_ids or [])
                if str(value).strip()
            }
        )
        with self._lock:
            if self._job.get("status") == "running":
                raise CollectionAlreadyRunning(self.snapshot_unlocked())

            job_id = uuid.uuid4().hex
            timestamp = utc_now()
            self._started_monotonic = time.monotonic()
            self._job = {
                "job_id": job_id,
                "status": "running",
                "stage": "collecting",
                "message": (
                    f"Collecting {len(scope)} selected Event list page(s) in the background."
                    if scope
                    else "Collecting all confirmed Event list pages in the background."
                ),
                "started_at": timestamp,
                "updated_at": timestamp,
                "completed_at": None,
                "elapsed_seconds": 0,
                "listing_candidate_ids": scope,
                "candidate_count": 0,
                "confirmed_listing_count": len(scope),
                "error_count": 0,
                "errors": [],
            }
            self._thread = threading.Thread(
                target=self._run,
                args=(job_id, runner),
                name=f"local-event-review-{job_id[:8]}",
                daemon=True,
            )
            self._thread.start()
            return self.snapshot_unlocked()

    def snapshot_unlocked(self) -> dict[str, Any]:
        payload = copy.deepcopy(self._job)
        if payload.get("status") == "running" and self._started_monotonic is not None:
            payload["elapsed_seconds"] = max(
                0,
                int(time.monotonic() - self._started_monotonic),
            )
        payload["thread_alive"] = bool(self._thread and self._thread.is_alive())
        return payload

    def _run(self, job_id: str, runner: Callable[[], ReviewState]) -> None:
        try:
            state = runner()
            collection = dict(state.event_collection or {})
            errors = [
                dict(value)
                for value in collection.get("errors") or []
                if isinstance(value, dict)
            ]
            self._finish(
                job_id,
                status="completed",
                stage="completed",
                message=f"Collected {len(state.events)} Event candidate(s).",
                candidate_count=len(state.events),
                confirmed_listing_count=int(
                    collection.get("confirmed_listing_count") or 0
                ),
                error_count=len(errors),
                errors=errors[:50],
            )
        except Exception as exc:
            self._finish(
                job_id,
                status="failed",
                stage="failed",
                message=f"{type(exc).__name__}: {exc}",
                error_count=1,
                errors=[{"error": f"{type(exc).__name__}: {exc}"[:1000]}],
            )

    def _finish(self, job_id: str, **updates: Any) -> None:
        with self._lock:
            if self._job.get("job_id") != job_id:
                return
            elapsed = (
                max(0, int(time.monotonic() - self._started_monotonic))
                if self._started_monotonic is not None
                else 0
            )
            timestamp = utc_now()
            self._job.update(
                updates,
                updated_at=timestamp,
                completed_at=timestamp,
                elapsed_seconds=elapsed,
            )


__all__ = [
    "CollectionAlreadyRunning",
    "CollectionStoreView",
    "EventCollectionJobManager",
]
