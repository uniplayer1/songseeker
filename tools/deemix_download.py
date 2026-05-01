#!/usr/bin/env python3
"""
SongSeeker Deemix Downloader

Downloads MP3s directly from a CSV track list using deemix.
When a track is not found on Deezer, uses AI to suggest better
search terms and retries — all missed tracks are handled in a
single batch API call.

Requires a Deezer ARL token.

Usage:
    python tools/deemix_download.py \
        --from-csv playlists/80s.csv \
        --output music/80s

How to get your ARL:
    1. Log into Deezer in your web browser
    2. Open Developer Tools (F12) → Application/Storage → Cookies
    3. Find the cookie named 'arl' and copy its value
    4. Paste it into your .env as DEEMIX_ARL=...
"""

import argparse
import csv
import json
import os
import sys
import time
import unicodedata
from pathlib import Path
from typing import Optional

# Load .env if available
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
except ImportError:
    pass

DEEMIX_AVAILABLE = False
try:
    from deemix import generateDownloadObject
    from deemix.downloader import Downloader
    from deemix.utils import getBitrateNumberFromText, formatListener
    from deezer import Deezer
    DEEMIX_AVAILABLE = True
except ImportError:
    pass

REQUESTS_AVAILABLE = False
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    pass

OPENAI_AVAILABLE = False
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    pass

DEEZER_API = "https://api.deezer.com"


def detect_csv_delimiter(csv_path: Path) -> str:
    """Auto-detect CSV delimiter (comma or semicolon).
    Uses a simple heuristic: if there are more semicolons than commas
    in the first line, it's likely semicolon-delimited.
    """
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        first_line = f.readline()
        if first_line.count(";") > first_line.count(","):
            return ";"
        return ","


def _has_header_row(first_line: str, delimiter: str) -> bool:
    """Heuristic: check if first line looks like a header row."""
    parts = first_line.strip().split(delimiter)
    header_keywords = {"artist", "title", "year", "backcol", "url"}
    lower_parts = {p.strip().lower() for p in parts}
    return bool(lower_parts & header_keywords)


def normalize_text(text: str) -> str:
    if not text:
        return ""
    return unicodedata.normalize('NFC', str(text).strip())


def get_deemix_settings(output_path: Path, bitrate: str = "320"):
    """Build a complete deemix settings dict based on library defaults."""
    return {
        "downloadLocation": str(output_path),
        "tracknameTemplate": "%artist% - %title%",
        "albumTracknameTemplate": "%tracknumber% - %title%",
        "playlistTracknameTemplate": "%position% - %artist% - %title%",
        "createPlaylistFolder": False,
        "playlistNameTemplate": "%playlist%",
        "createArtistFolder": False,
        "artistNameTemplate": "%artist%",
        "createAlbumFolder": False,
        "albumNameTemplate": "%artist% - %album%",
        "createCDFolder": False,
        "createStructurePlaylist": False,
        "createSingleFolder": False,
        "padTracks": True,
        "paddingSize": "0",
        "illegalCharacterReplacer": "_",
        "queueConcurrency": 3,
        "maxBitrate": getBitrateNumberFromText(bitrate) if DEEMIX_AVAILABLE else 3,
        "feelingLucky": False,
        "fallbackBitrate": True,
        "fallbackSearch": False,
        "fallbackISRC": False,
        "logErrors": True,
        "logSearched": False,
        "overwriteFile": "n",
        "createM3U8File": False,
        "playlistFilenameTemplate": "playlist",
        "syncedLyrics": False,
        "embeddedLRC": False,
        "explicitLyrics": False,
        "embeddedArtworkSize": 800,
        "embeddedArtworkPNG": False,
        "localArtworkSize": 1400,
        "localArtworkFormat": "jpg",
        "saveArtwork": True,
        "coverImageTemplate": "cover",
        "saveArtworkArtist": False,
        "artistImageTemplate": "folder",
        "saveImageInPath": False,
        "localImage": False,
        "jpegImageQuality": 90,
        "dateFormat": "Y-M-D",
        "albumVariousArtists": True,
        "removeAlbumVersion": False,
        "removeDuplicateArtists": True,
        "featuredToTitle": "0",
        "titleCasing": "nothing",
        "artistCasing": "nothing",
        "executeCommand": "",
        "embeddedArtists": False,
        "tags": {
            "title": True,
            "artist": True,
            "artists": True,
            "album": True,
            "cover": True,
            "trackNumber": True,
            "trackTotal": False,
            "discNumber": True,
            "discTotal": False,
            "albumArtist": True,
            "genre": True,
            "year": True,
            "date": True,
            "explicit": False,
            "isrc": True,
            "length": True,
            "barcode": True,
            "bpm": True,
            "replayGain": False,
            "label": True,
            "lyrics": False,
            "syncedLyrics": False,
            "copyright": False,
            "composer": False,
            "involvedPeople": False,
            "source": False,
            "rating": False,
            "savePlaylistAsCompilation": False,
            "useNullSeparator": False,
            "saveID3v1": True,
            "multiArtistSeparator": "default",
            "singleAlbumArtist": False,
            "coverDescriptionUTF8": False,
        },
    }


def search_deezer_track(artist: str, title: str, strict: bool = True) -> dict | None:
    """Search Deezer public API for a track (no auth required).
    strict=True uses quoted artist/track fields.
    strict=False uses a broader free-text search.
    """
    if not REQUESTS_AVAILABLE:
        return None
    if strict:
        q = f'artist:"{artist}" track:"{title}"'
    else:
        q = f"{artist} {title}"
    try:
        resp = requests.get(
            f"{DEEZER_API}/search",
            params={"q": q, "limit": 5},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("data"):
            return data["data"][0]
    except Exception as e:
        print(f"    Search error: {e}", file=sys.stderr)
    return None


def download_single_track(dz, track_id: int, settings: dict):
    """Download a single track via deemix."""
    if not DEEMIX_AVAILABLE:
        return False
    try:
        track_url = f"https://www.deezer.com/track/{track_id}"
        bitrate = settings.get("maxBitrate", 3)
        download_object = generateDownloadObject(dz, track_url, bitrate)
        if not download_object:
            return False
        listener = formatListener("download")
        downloader = Downloader(dz, download_object, settings, listener)
        downloader.start()
        return True
    except Exception as e:
        print(f"    Download error: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# AI fallback for missed tracks
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> str:
    """Extract JSON from markdown fences or plain text."""
    text = text.strip()
    if "```json" in text:
        return text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text


def build_search_suggestion_prompt(missed_songs: list[dict]) -> str:
    """Build a prompt asking the AI for better Deezer search queries."""
    lines = [
        "You are helping find songs on Deezer. Some searches failed using strict artist+title matching.",
        "For each song, suggest alternative search strategies that might find the track.",
        "Consider these approaches:",
        "- Remove featured artists (e.g. 'Dr. Dre feat. Snoop Dogg' → artist: 'Dr. Dre')",
        "- Remove version info like '(Album Version)', '(Extended)', '(Remastered)' from the title",
        "- Try alternative spellings or known aliases (e.g. '99 Luftballons' → 'Neunundneunzig Luftballons')",
        "- Try English vs. original language titles",
        "- Simplify punctuation or special characters",
        "- If the artist is a band, try searching with just the song title",
        "",
        "Respond ONLY with a JSON object containing a single key 'results' which is an array.",
        "Each element must be an object in this exact format:",
        '{\n  "index": 0,\n  "suggested_artist": "Simplified Artist (or empty string)",\n  "suggested_title": "Simplified Title",\n  "reason": "brief explanation"\n}',
        "",
        "Here are the songs that were not found:",
        "",
    ]
    for idx, song in enumerate(missed_songs):
        lines.append(f"--- ENTRY {idx} ---")
        lines.append(f"Original Artist: {song['artist']}")
        lines.append(f"Original Title: {song['title']}")
        lines.append("")
    return "\n".join(lines)


def ai_suggest_search_terms(client, model: str, missed_songs: list[dict]) -> list[dict]:
    """Call AI to get better search terms for missed tracks. Returns list of suggestions."""
    if not missed_songs or client is None:
        return []

    prompt = build_search_suggestion_prompt(missed_songs)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a music search assistant. Your response must be a valid JSON object."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2000 + len(missed_songs) * 200,
            response_format={"type": "json_object"},
        )
        raw_content = response.choices[0].message.content
        if not raw_content or not raw_content.strip():
            print(f"  Warning: AI returned empty content for search suggestions.", file=sys.stderr)
            return []
        content = _extract_json(raw_content)
        parsed = json.loads(content)

        if isinstance(parsed, dict) and "results" in parsed:
            parsed = parsed["results"]
        if not isinstance(parsed, list):
            print(f"  Warning: AI returned non-array for search suggestions: {type(parsed)}", file=sys.stderr)
            return []

        suggestions = []
        for item in parsed:
            if isinstance(item, dict) and "index" in item:
                idx = int(item["index"])
                if 0 <= idx < len(missed_songs):
                    suggestions.append({
                        "original": missed_songs[idx],
                        "suggested_artist": item.get("suggested_artist", missed_songs[idx]["artist"]),
                        "suggested_title": item.get("suggested_title", missed_songs[idx]["title"]),
                        "reason": item.get("reason", ""),
                    })
        return suggestions
    except Exception as e:
        print(f"  AI search suggestion failed: {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Main download logic
# ---------------------------------------------------------------------------

def download_from_csv(csv_path: Path, output_path: Path, arl: str, bitrate: str = "320", delay: float = 0.2,
                      ai_client=None, ai_model: str = ""):
    """Download tracks directly from a CSV."""
    if not DEEMIX_AVAILABLE:
        print("Error: deemix is not installed. Run: pip install deemix", file=sys.stderr)
        sys.exit(1)
    if not REQUESTS_AVAILABLE:
        print("Error: requests is required. Install with: pip install requests", file=sys.stderr)
        sys.exit(1)

    # Load CSV
    songs = []
    delimiter = detect_csv_delimiter(csv_path)
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        first_line = f.readline()
        has_header = _has_header_row(first_line, delimiter)
        f.seek(0)

        if has_header:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                artist = normalize_text(row.get("Artist", ""))
                title = normalize_text(row.get("Title", ""))
                year = normalize_text(row.get("Year", ""))
                if artist and title:
                    songs.append({"artist": artist, "title": title, "year": year})
        else:
            # No header — assume standard column order: Artist, Title, Year, backcol
            reader = csv.reader(f, delimiter=delimiter)
            for parts in reader:
                artist = normalize_text(parts[0] if len(parts) > 0 else "")
                title = normalize_text(parts[1] if len(parts) > 1 else "")
                year = normalize_text(parts[2] if len(parts) > 2 else "")
                if artist and title:
                    songs.append({"artist": artist, "title": title, "year": year})

    print(f"Loaded {len(songs)} songs from {csv_path}")
    print(f"Output folder: {output_path}")
    output_path.mkdir(parents=True, exist_ok=True)

    # Login to Deezer via deemix
    dz = Deezer()
    if not dz.login_via_arl(arl):
        print("Error: Invalid ARL token. Please check your DEEMIX_ARL in .env", file=sys.stderr)
        sys.exit(1)

    settings = get_deemix_settings(output_path, bitrate)

    found = 0
    missed = 0
    missed_songs: list[dict] = []

    print("\nSearching and downloading tracks...")
    print(f"Rate limit: ~{1/delay:.0f} req/sec (Deezer allows ~50 req / 5 sec)\n")

    for i, song in enumerate(songs, 1):
        print(f"  [{i}/{len(songs)}] {song['artist']} - {song['title']}", end=" ", flush=True)

        track = search_deezer_track(song["artist"], song["title"])
        time.sleep(delay)

        if track:
            track_id = int(track["id"])
            print(f"→ ID {track_id}", end=" ", flush=True)
            ok = download_single_track(dz, track_id, settings)
            if ok:
                print(c("✅ OK", "green"))
                found += 1
            else:
                print(c("❌ Download failed", "red"))
                missed += 1
                missed_songs.append(song)
        else:
            print(c("❌ Not found", "red"))
            missed += 1
            missed_songs.append(song)

    # -----------------------------------------------------------------------
    # AI fallback: suggest better search terms for missed tracks
    # -----------------------------------------------------------------------
    if missed_songs and ai_client and ai_model:
        print(f"\n{'─'*60}")
        print(f"AI Fallback: {len(missed_songs)} track(s) not found. Asking AI for better search terms...")
        suggestions = ai_suggest_search_terms(ai_client, ai_model, missed_songs)

        if suggestions:
            print(f"AI suggested {len(suggestions)} alternative search(es). Retrying...\n")
            still_missed = []
            for sug in suggestions:
                orig = sug["original"]
                new_artist = sug["suggested_artist"]
                new_title = sug["suggested_title"]
                print(f"  [RETRY] {orig['artist']} - {orig['title']}", end=" ", flush=True)
                print(f"→ trying '{new_artist}' - '{new_title}'", end=" ", flush=True)

                track = search_deezer_track(new_artist, new_title)
                time.sleep(delay)

                if track:
                    track_id = int(track["id"])
                    print(f"→ ID {track_id}", end=" ", flush=True)
                    ok = download_single_track(dz, track_id, settings)
                    if ok:
                        print(c("✅ OK", "green"))
                        found += 1
                        missed -= 1
                        continue

                # AI suggestion failed — try broader search
                print("→ broader search", end=" ", flush=True)
                track = search_deezer_track(new_artist or orig["artist"], new_title, strict=False)
                time.sleep(delay)

                if track:
                    track_id = int(track["id"])
                    print(f"→ ID {track_id}", end=" ", flush=True)
                    ok = download_single_track(dz, track_id, settings)
                    if ok:
                        print(c("✅ OK", "green"))
                        found += 1
                        missed -= 1
                        continue

                print(c("❌ Still not found", "red"))
                still_missed.append(orig)

            missed_songs = still_missed
        else:
            print("No AI suggestions received. Skipping fallback.")

    print(f"\n{'='*60}")
    print(f"Downloaded: {found}/{len(songs)}")
    print(f"Missed:     {missed}")
    print(f"Output:     {output_path}")
    print(f"{'='*60}")

    if missed:
        sys.exit(2)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def c(text: str, color: str = "") -> str:
    codes = {
        "green": "\033[92m",
        "red": "\033[91m",
        "reset": "\033[0m",
    }
    return f"{codes.get(color, '')}{text}{codes.get('reset', '')}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    env_arl = os.getenv("DEEMIX_ARL", "")
    env_api_key = os.getenv("OPENAI_API_KEY", "")
    env_api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    env_model = os.getenv("AI_MODEL", "gpt-4o-mini")

    parser = argparse.ArgumentParser(
        description="Download MP3s from Deezer using deemix.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/deemix_download.py --from-csv playlists/80s.csv --output music/80s
        """
    )
    parser.add_argument("--from-csv", required=True, help="Download tracks directly from a playlist CSV (searches Deezer per track)")
    parser.add_argument("--output", required=True, help="Output directory for downloaded MP3s")
    parser.add_argument("--arl", default=env_arl, help="Deezer ARL token (or set DEEMIX_ARL in .env)")
    parser.add_argument("--bitrate", default="320", choices=["128", "320", "flac"], help="Download bitrate (default: 320)")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between API searches in seconds (default: 0.2)")
    parser.add_argument("--ai-fallback", action="store_true", help="Use AI to suggest better search terms for tracks not found on Deezer")
    parser.add_argument("--api-key", default=env_api_key, help="OpenAI-compatible API key for AI fallback (or set OPENAI_API_KEY in .env)")
    parser.add_argument("--api-base", default=env_api_base, help="OpenAI-compatible API base URL")
    parser.add_argument("--model", default=env_model, help="Model name for AI fallback")
    args = parser.parse_args()

    if not args.arl:
        print("Error: --arl is required (or set DEEMIX_ARL in .env)", file=sys.stderr)
        print("""
How to get your ARL:
  1. Log into Deezer in your web browser
  2. Open Developer Tools (F12) → Application/Storage → Cookies
  3. Find the cookie named 'arl' and copy its value
  4. Paste it into your .env file as DEEMIX_ARL=...
        """)
        sys.exit(1)

    # Setup AI client if fallback requested
    ai_client = None
    if args.ai_fallback:
        if not OPENAI_AVAILABLE:
            print("Warning: openai package not installed. AI fallback disabled. Install with: pip install openai", file=sys.stderr)
        elif not args.api_key:
            print("Warning: --api-key required for AI fallback (or set OPENAI_API_KEY in .env). AI fallback disabled.", file=sys.stderr)
        else:
            ai_client = OpenAI(api_key=args.api_key, base_url=args.api_base)
            print(f"AI fallback enabled (model: {args.model})")

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    download_from_csv(Path(args.from_csv), output_path, args.arl, args.bitrate, args.delay,
                      ai_client=ai_client, ai_model=args.model if ai_client else "")


if __name__ == "__main__":
    main()
