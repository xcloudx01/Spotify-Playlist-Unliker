from __future__ import annotations

import argparse
import logging
import os
import sys

import spotipy

if __package__ is None or __package__ == "":
    # Support running as a script: `python src/main.py`
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from src.auth import build_auth_manager, clear_saved_credentials
    from src.models import APP_HEADER, render_header
    from src.selector import prompt_for_playlist_selection
    from src.spotify_client import SpotifyClient
    from src.unliker import build_unlike_plan, execute_unlike
else:
    from .auth import build_auth_manager, clear_saved_credentials
    from .models import APP_HEADER, render_header
    from .selector import prompt_for_playlist_selection
    from .spotify_client import SpotifyClient
    from .unliker import build_unlike_plan, execute_unlike

SCOPE = "user-library-read user-library-modify playlist-read-private playlist-read-collaborative"


def _ui_print(message: str) -> None:
    print(message)


def _pause_before_menu() -> None:
    input("\nPress Enter to return to playlist menu...")


def _clear_screen() -> None:
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")


def _finalize_inline_line() -> None:
    # Ensure spinner/progress carriage-return output is finalized before next screen updates.
    if sys.stdout.isatty():
        print()


def _render_spinner(label: str, tick: int) -> None:
    frames = "|/-\\"
    frame = frames[tick % len(frames)]
    print(f"\r{label} {frame}", end="", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Unlike songs from your Liked Songs if they appear in selected playlists. "
            "This script never modifies playlists."
        )
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear the terminal before running.",
    )
    parser.add_argument(
        "--clear-saved-credentials",
        action="store_true",
        help="Delete locally saved Spotify client ID/secret and exit.",
    )
    return parser


def main() -> int:
    try:
        # Suppress noisy library warnings like Spotipy's rate-limit warning with missing retry-after.
        logging.getLogger().setLevel(logging.ERROR)

        args = build_parser().parse_args()

        if args.clear_saved_credentials:
            cleared, message = clear_saved_credentials()
            _ui_print(message)
            return 0

        if not args.no_clear:
            _clear_screen()
        render_header()

        _ui_print("Starting authentication...")
        auth_manager = build_auth_manager(scope=SCOPE)
        _ui_print("Authentication ready. Connecting to Spotify API...")
        sp = spotipy.Spotify(auth_manager=auth_manager)
        client = SpotifyClient(sp)

        # After credential entry, refresh screen so the next view starts at header + playlists.
        if not args.no_clear:
            _clear_screen()
        render_header()

        _ui_print("Fetching your Liked Songs count...")
        liked_count_before = client.get_liked_songs_count()
        _ui_print(f"Liked Songs count: {liked_count_before}")

        _ui_print("Loading your playlists...")
        playlists = client.get_current_user_playlists(
            progress_callback=lambda page: _render_spinner(
                f"Loading your playlists... pages fetched: {page}",
                page,
            )
        )
        _finalize_inline_line()
        if not args.no_clear:
            _clear_screen()
        render_header()
        _ui_print(f"Playlists loaded: {len(playlists)}")
        if not playlists:
            _ui_print("No playlists found for this account.")
            return 0

        while True:
            selected = prompt_for_playlist_selection(playlists)
            if selected is None:
                _ui_print("Exiting.")
                return 0
            if not selected:
                _ui_print("No playlists selected. Nothing to do.")
                _pause_before_menu()
            else:
                _ui_print(
                    f"Processing selection: {len(selected)} playlist(s) "
                    f"({', '.join(pl.name for pl in selected[:3])}{'...' if len(selected) > 3 else ''})"
                )
                estimated_rows = sum(pl.track_count for pl in selected)
                progress_threshold = 250
                last_progress_bucket = 0

                def _selection_progress(loaded_rows: int) -> None:
                    nonlocal last_progress_bucket
                    bucket = loaded_rows // progress_threshold
                    if bucket > last_progress_bucket and loaded_rows >= progress_threshold:
                        last_progress_bucket = bucket
                        _ui_print(f"Loading playlists... {loaded_rows} songs discovered so far.")

                selection_progress = _selection_progress if estimated_rows > progress_threshold else None
                plan, _, liked_track_ids = build_unlike_plan(
                    client,
                    selected,
                    progress_callback=selection_progress,
                )

                if plan.liked_track_count == 0:
                    if not args.no_clear:
                        _clear_screen()
                    render_header()
                    _ui_print("\nNo matching liked songs found in the selected playlists. No changes made.")
                    _pause_before_menu()
                else:
                    _ui_print(
                        f"\nYou selected {len(plan.selected_playlists)} playlists. "
                        f"Found {plan.unique_track_count:,} songs total, "
                        f"with {plan.liked_track_count:,} currently in your Liked Songs."
                    )

                if plan.liked_track_count == 0:
                    continue
                else:
                    confirm = input(
                        f"\nAre you sure? This will unlike ({plan.liked_track_count}) songs from your Liked Songs list (y/N): "
                    ).strip().lower()
                    if confirm in {"y", "yes"}:
                        result = execute_unlike(client, liked_track_ids)
                        _ui_print(f"Tracks unliked: {result.unliked_track_count}")
                        liked_count_before = client.get_liked_songs_count()
                        _pause_before_menu()
                        continue
                    else:
                        _ui_print("Aborted.")
                        continue

            run_again = input("\nReturn to playlist menu? (Y/n): ").strip().lower()
            if run_again in {"n", "no"}:
                return 0
    except KeyboardInterrupt:
        print("\nCancelled by user.")
        return 130
    except spotipy.SpotifyException as exc:
        status = getattr(exc, "http_status", "unknown")
        _ui_print(f"\nSpotify API error (status {status}): {exc}")
        _ui_print("Check network/API status and retry. If it persists, verify app scopes and credentials.")
        return 1
    except (TimeoutError, ConnectionError, OSError) as exc:
        _ui_print(f"\nNetwork/system error: {exc}")
        _ui_print("Retry shortly. If this repeats, check internet connection and local firewall settings.")
        return 1
    except Exception as exc:
        _ui_print(f"\nUnexpected error: {exc}")
        _ui_print(
            "If login stops working, run with --clear-saved-credentials to reset saved credentials, "
            "then re-enter Client ID and Client Secret."
        )
        _ui_print("Re-run with the same inputs and capture output for troubleshooting.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
