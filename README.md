# Spotify Playlist Unliker

Simple CLI tool to remove songs from your Liked Songs if they're already in one of your playlists.
> Because my shuffle shouldn’t jump from pop anthems to bedtime tracks.

## Quick start

1. Create an app at <https://developer.spotify.com/dashboard>
2. Run [`SpotifyPlaylistUnliker.exe`](SpotifyPlaylistUnliker.exe).
3. Input app ID and Secret from step 1.
4. Select playlist numbers (e.g., `4`, `1,3,5`, or `2-6`).

## Preview

```text
+---------------------------+
| Spotify Playlist Unliker  |
+---------------------------+

Your playlists:
    1. 2 AM Focus Session (485 tracks)
    2. Night Ambience (87 tracks)
    3. Disco Fever (62 tracks)
    4. DOOM (5 tracks)
    5. Energy (44 tracks)
    ...

Type which playlist number you want to unlike

Select playlists:
```

---

## What it does

- Signs in to Spotify via Web API.
- Lists your playlists and lets you multi-select by number.
- Unlikes matching tracks from your library after confirmation.
- Unlikes are sent immediately; Spotify clients usually reflect changes within seconds.
- Can optionally save app credentials in Windows Credential Manager.

## Requirements (Running from source)

- Python 3.10+
