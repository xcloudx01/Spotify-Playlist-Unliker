from __future__ import annotations

import time
from collections.abc import Callable, Iterable

import spotipy
from spotipy.exceptions import SpotifyException

from .models import PlaylistSummary, TrackSummary


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class SpotifyClient:
    def __init__(self, sp: spotipy.Spotify) -> None:
        self.sp = sp

    @staticmethod
    def _is_transient_status(status: int | None) -> bool:
        return status in {429, 500, 502, 503, 504}

    @staticmethod
    def _retry_sleep_seconds(exc: SpotifyException, attempt: int, default_sleep_seconds: float) -> float:
        headers = getattr(exc, "headers", None)
        retry_after: str | None = None
        if isinstance(headers, dict):
            retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after is not None:
            try:
                parsed = float(retry_after)
                if parsed > 0:
                    return parsed
            except (TypeError, ValueError):
                pass
        return default_sleep_seconds * (attempt + 1)

    @staticmethod
    def _is_too_many_uris_error(exc: SpotifyException) -> bool:
        status = getattr(exc, "http_status", None)
        if status != 400:
            return False
        text = str(exc).lower()
        return "too many uris requested" in text or "too many ids" in text

    def _call_with_retries(
        self,
        fn: Callable[[], object],
        retries: int = 3,
        sleep_seconds: float = 1.0,
    ) -> object:
        for attempt in range(retries):
            try:
                return fn()
            except SpotifyException as exc:
                status = getattr(exc, "http_status", None)
                if not self._is_transient_status(status) or attempt == retries - 1:
                    raise
                time.sleep(self._retry_sleep_seconds(exc, attempt, sleep_seconds))
            except (TimeoutError, ConnectionError, OSError):
                if attempt == retries - 1:
                    raise
                time.sleep(sleep_seconds * (attempt + 1))
        raise RuntimeError("Retry loop exhausted unexpectedly")

    def get_current_user_playlists(
        self,
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[PlaylistSummary]:
        playlists: list[PlaylistSummary] = []
        pages_fetched = 0
        results = self._call_with_retries(lambda: self.sp.current_user_playlists(limit=50))
        while results:
            if not isinstance(results, dict):
                raise RuntimeError("Spotify API returned unexpected playlist payload type.")
            pages_fetched += 1
            if progress_callback is not None:
                progress_callback(pages_fetched)
            for item in results.get("items", []):
                name = item.get("name", "<unnamed playlist>")
                if name.lower().startswith("similar songs to"):
                    continue
                playlist_id = item.get("id")
                if not playlist_id:
                    continue
                playlists.append(
                    PlaylistSummary(
                        id=playlist_id,
                        name=name,
                        track_count=item.get("tracks", {}).get("total", 0),
                    )
                )
            if not results.get("next"):
                break
            results = self._call_with_retries(lambda: self.sp.next(results))
        playlists.sort(key=lambda p: p.name.casefold())
        return playlists

    def get_playlist_tracks(self, playlist_id: str) -> list[TrackSummary]:
        tracks: list[TrackSummary] = []
        results = self._call_with_retries(
            lambda: self.sp.playlist_items(
                playlist_id,
                additional_types=("track",),
                fields="items(track(id,uri,name,artists(name),is_local)),next",
                limit=100,
            )
        )
        while results:
            if not isinstance(results, dict):
                raise RuntimeError("Spotify API returned unexpected playlist-track payload type.")
            for item in results.get("items", []):
                track = item.get("track")
                if not track or track.get("is_local"):
                    continue
                track_id = track.get("id")
                uri = track.get("uri")
                if not track_id or not uri:
                    continue
                artists = ", ".join(a.get("name", "") for a in track.get("artists", []) if a.get("name"))
                tracks.append(
                    TrackSummary(
                        id=track_id,
                        uri=uri,
                        name=track.get("name", "<unknown track>"),
                        artists=artists,
                    )
                )
            if not results.get("next"):
                break
            results = self._call_with_retries(lambda: self.sp.next(results))
        return tracks

    def filter_liked_track_ids(self, track_ids: list[str]) -> list[str]:
        if not track_ids:
            return []

        # Prefer direct membership checks (fast for small and medium selections).
        # If Spotify rejects URI payload size, adapt batch size down automatically.
        liked: list[str] = []
        max_batch_size = 20
        min_batch_size = 1
        batch_size = max_batch_size
        i = 0

        while i < len(track_ids):
            batch = track_ids[i : i + batch_size]
            try:
                flags = self._call_with_retries(lambda: self.sp.current_user_saved_tracks_contains(batch))
                liked.extend([track_id for track_id, is_liked in zip(batch, flags) if is_liked])
                i += len(batch)
            except SpotifyException as exc:
                if self._is_too_many_uris_error(exc) and batch_size > min_batch_size:
                    batch_size = max(min_batch_size, batch_size // 2)
                    continue
                if self._is_too_many_uris_error(exc) and batch_size == min_batch_size:
                    # Fall back to full liked-library scan only if direct membership
                    # checks are still rejected at the minimum request size.
                    break
                raise

        if i >= len(track_ids):
            return liked

        # Avoid /me/library/contains URI-size edge cases by building liked IDs from
        # paged /me/tracks results and intersecting locally.
        liked_ids: set[str] = set()
        offset = 0
        limit = 50

        while True:
            results = self._call_with_retries(
                lambda: self.sp.current_user_saved_tracks(
                    limit=limit,
                    offset=offset,
                )
            )
            if not isinstance(results, dict):
                raise RuntimeError("Spotify API returned unexpected liked-tracks payload type.")

            items = results.get("items", [])
            for item in items:
                track = item.get("track") if isinstance(item, dict) else None
                track_id = track.get("id") if isinstance(track, dict) else None
                if track_id:
                    liked_ids.add(track_id)

            if not results.get("next"):
                break
            offset += limit

        return [track_id for track_id in track_ids if track_id in liked_ids]

    def get_liked_songs_count(self) -> int:
        results = self._call_with_retries(lambda: self.sp.current_user_saved_tracks(limit=1))
        return int(results.get("total", 0))

    def unlike_tracks(
        self,
        track_ids: list[str],
        retries: int = 3,
        sleep_seconds: float = 1.0,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> int:
        batches_sent = 0
        total = len(track_ids)
        completed = 0
        for batch in _chunks(track_ids, 50):
            for attempt in range(retries):
                try:
                    self.sp.current_user_saved_tracks_delete(batch)
                    batches_sent += 1
                    completed += len(batch)
                    if progress_callback is not None:
                        progress_callback(completed, total)
                    break
                except SpotifyException as exc:
                    status = getattr(exc, "http_status", None)
                    # Retry only transient API/server/rate-limit failures.
                    if not self._is_transient_status(status):
                        raise
                    if attempt == retries - 1:
                        raise
                    time.sleep(self._retry_sleep_seconds(exc, attempt, sleep_seconds))
                except (TimeoutError, ConnectionError, OSError):
                    if attempt == retries - 1:
                        raise
                    time.sleep(sleep_seconds * (attempt + 1))
        return batches_sent

