from __future__ import annotations

from typing import Dict, List

from src.models import PlaylistSummary, TrackSummary
from src.unliker import build_unlike_plan, execute_unlike


class FakeClient:
    def __init__(self) -> None:
        self.playlist_tracks: Dict[str, List[TrackSummary]] = {
            "p1": [
                TrackSummary(id="t1", uri="spotify:track:t1", name="Song 1", artists="A"),
                TrackSummary(id="t2", uri="spotify:track:t2", name="Song 2", artists="B"),
            ],
            "p2": [
                TrackSummary(id="t2", uri="spotify:track:t2", name="Song 2", artists="B"),
                TrackSummary(id="t3", uri="spotify:track:t3", name="Song 3", artists="C"),
            ],
        }
        self.unliked: list[str] = []

    def get_playlist_tracks(self, playlist_id: str) -> list[TrackSummary]:
        return self.playlist_tracks[playlist_id]

    def filter_liked_track_ids(self, track_ids: list[str]) -> list[str]:
        return [tid for tid in track_ids if tid in {"t1", "t3"}]

    def unlike_tracks(self, track_ids: list[str], progress_callback=None) -> int:
        if progress_callback:
            progress_callback(len(track_ids), len(track_ids))
        self.unliked.extend(track_ids)
        return 1 if track_ids else 0


def test_build_unlike_plan_deduplicates_and_counts() -> None:
    client = FakeClient()
    playlists = [
        PlaylistSummary(id="p1", name="One", track_count=2),
        PlaylistSummary(id="p2", name="Two", track_count=2),
    ]

    plan, _, liked_track_ids = build_unlike_plan(client, playlists)

    assert plan.total_playlist_track_rows == 4
    assert plan.unique_track_count == 3
    assert plan.liked_track_count == 2
    assert liked_track_ids == ["t1", "t3"]


def test_build_unlike_plan_reports_progress_rows() -> None:
    client = FakeClient()
    playlists = [
        PlaylistSummary(id="p1", name="One", track_count=2),
        PlaylistSummary(id="p2", name="Two", track_count=2),
    ]
    progress_updates: list[int] = []

    build_unlike_plan(
        client,
        playlists,
        progress_callback=lambda rows: progress_updates.append(rows),
    )

    assert progress_updates == [2, 4]


def test_execute_unlike_returns_counts() -> None:
    client = FakeClient()
    result = execute_unlike(client, ["t1", "t3"])

    assert result.unliked_track_count == 2
    assert result.batches_sent == 1
    assert client.unliked == ["t1", "t3"]

