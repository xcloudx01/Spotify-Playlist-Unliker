from __future__ import annotations

from dataclasses import dataclass


APP_HEADER = "+---------------------------+\n| Spotify Playlist Unliker  |\n+---------------------------+"


def render_header() -> None:
    print(APP_HEADER)
    print()


@dataclass(frozen=True)
class PlaylistSummary:
    id: str
    name: str
    track_count: int


@dataclass(frozen=True)
class TrackSummary:
    id: str
    uri: str
    name: str
    artists: str


@dataclass(frozen=True)
class UnlikePlan:
    selected_playlists: list[PlaylistSummary]
    total_playlist_track_rows: int
    unique_track_count: int
    liked_track_count: int


@dataclass(frozen=True)
class UnlikeResult:
    unliked_track_count: int
    batches_sent: int
