from __future__ import annotations

import sys
from typing import Callable

from .models import PlaylistSummary, TrackSummary, UnlikePlan, UnlikeResult
from .spotify_client import SpotifyClient


def build_unlike_plan(
    client: SpotifyClient,
    selected_playlists: list[PlaylistSummary],
    progress_callback: Callable[[int], None] | None = None,
) -> tuple[UnlikePlan, dict[str, list[TrackSummary]], list[str]]:
    per_playlist_tracks: dict[str, list[TrackSummary]] = {}
    all_track_ids: list[str] = []
    total_rows = 0

    for playlist in selected_playlists:
        tracks = client.get_playlist_tracks(playlist.id)
        per_playlist_tracks[playlist.id] = tracks
        total_rows += len(tracks)
        if progress_callback is not None:
            progress_callback(total_rows)
        all_track_ids.extend(track.id for track in tracks)

    unique_track_ids = sorted(set(all_track_ids))
    liked_track_ids = client.filter_liked_track_ids(unique_track_ids)

    plan = UnlikePlan(
        selected_playlists=selected_playlists,
        total_playlist_track_rows=total_rows,
        unique_track_count=len(unique_track_ids),
        liked_track_count=len(liked_track_ids),
    )
    return plan, per_playlist_tracks, liked_track_ids


def execute_unlike(client: SpotifyClient, liked_track_ids: list[str]) -> UnlikeResult:
    if not liked_track_ids:
        return UnlikeResult(unliked_track_count=0, batches_sent=0)

    def _render_progress(completed: int, total: int) -> None:
        width = 30
        ratio = (completed / total) if total else 1
        filled = int(width * ratio)
        bar = "#" * filled + "-" * (width - filled)
        print(f"\rUnliking: [{bar}] {completed}/{total} ({ratio * 100:5.1f}%)", end="", flush=True)

    try:
        batches_sent = client.unlike_tracks(liked_track_ids, progress_callback=_render_progress)
    except TypeError:
        # Backward compatibility for test doubles/older client interfaces
        # that don't yet accept progress_callback.
        batches_sent = client.unlike_tracks(liked_track_ids)
    if sys.stdout.isatty():
        print()
    return UnlikeResult(unliked_track_count=len(liked_track_ids), batches_sent=batches_sent)

