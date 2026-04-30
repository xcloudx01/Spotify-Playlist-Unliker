from __future__ import annotations

import os
import re

from .models import APP_HEADER, PlaylistSummary


def _clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _render_playlist_menu(playlists: list[PlaylistSummary], warning: str | None = None) -> None:
    print(APP_HEADER)
    print("\nYour playlists:")
    for idx, pl in enumerate(playlists, start=1):
        print(f"  {idx:>3}. {pl.name} ({pl.track_count} tracks)")
    print("\nType which playlist number you want to unlike")
    print("or type 'exit' to quit")
    if warning:
        print(f"\n{warning}")


def parse_selection(selection: str, max_index: int) -> list[int]:
    if max_index < 1:
        raise ValueError("No playlists available to select.")

    selected: set[int] = set()
    normalized = re.sub(r"\s+", ",", selection.strip())
    tokens = [token.strip() for token in normalized.split(",") if token.strip()]
    if not tokens:
        raise ValueError("Selection cannot be empty.")

    for token in tokens:
        if "-" in token:
            start_str, end_str = token.split("-", 1)
            try:
                start = int(start_str)
                end = int(end_str)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid selection token '{token}'.")
            if start > end:
                raise ValueError(f"Invalid range '{token}'.")
            for i in range(start, end + 1):
                if i < 1 or i > max_index:
                    raise ValueError(f"Selection {i} out of range 1..{max_index}.")
                selected.add(i)
        else:
            try:
                i = int(token)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid selection token '{token}'.")
            if i < 1 or i > max_index:
                raise ValueError(f"Selection {i} out of range 1..{max_index}.")
            selected.add(i)

    return sorted(selected)


def prompt_for_playlist_selection(playlists: list[PlaylistSummary]) -> list[PlaylistSummary] | None:
    if not playlists:
        return []

    warning: str | None = None

    while True:
        _clear_screen()
        _render_playlist_menu(playlists, warning)
        raw = input("\nSelect playlists: ").strip()
        if raw.lower() == "exit":
            return None
        try:
            indices = parse_selection(raw, len(playlists))
            return [playlists[i - 1] for i in indices]
        except (ValueError, TypeError) as exc:
            warning = f"Invalid input: {exc}"
