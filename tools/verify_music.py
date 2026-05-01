#!/usr/bin/env python3
"""
SongSeeker Music Verification & Renaming Tool

Comprehensive workflow script for checking, verifying, and renaming
local MP3 files against a playlist CSV. Designed for the SongSeeker
local-audio workflow.

Features:
- Scan music directories recursively (supports genre sub-folders)
- Match CSV entries to MP3 files (exact + fuzzy)
- Read ID3 metadata (Artist, Title, Year, Album)
- Optional AI verification via OpenAI-compatible APIs to detect
  covers, instrumentals, and wrong versions
- Batch AI verification for speed and cost savings
- Generate clean, predictable filenames preserving umlauts (äöüß)
- Flag issues and produce a detailed report
- Generate card-ready CSV with local URLs
- Load settings from .env file automatically

Usage:
    # Dry-run: check and report without changing anything
    python tools/verify_music.py \\
        --csv playlists/80s.csv \\
        --music-dir music/80s \\
        --base-url http://nas:8887/music/80s

    # With AI verification (batch of 20 songs per API call)
    python tools/verify_music.py \\
        --csv playlists/80s.csv \\
        --music-dir music/80s \\
        --base-url http://nas:8887/music/80s \\
        --verify-ai

    # Apply renames and generate output CSV
    python tools/verify_music.py \\
        --csv playlists/80s.csv \\
        --music-dir music/80s \\
        --base-url http://nas:8887/music/80s \\
        --rename \\
        --output-csv playlists/80s-local.csv
"""

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Load .env before anything else
# ---------------------------------------------------------------------------
DOTENV_AVAILABLE = False
try:
    from dotenv import load_dotenv
    # Look for .env in project root (one level up from tools/)
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
        DOTENV_AVAILABLE = True
except ImportError:
    pass

# Optional imports — fail gracefully with helpful messages
try:
    from mutagen.mp3 import MP3
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3
except ImportError:
    print("Error: mutagen is required. Install with: pip install -r tools/requirements.txt", file=sys.stderr)
    sys.exit(1)

try:
    from rapidfuzz import fuzz
except ImportError:
    print("Error: rapidfuzz is required. Install with: pip install -r tools/requirements.txt", file=sys.stderr)
    sys.exit(1)

OPENAI_AVAILABLE = False
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Mp3File:
    path: Path
    rel_path: Path          # relative to music_dir
    artist: str = ""
    title: str = ""
    album: str = ""
    year: str = ""
    genre: str = ""


@dataclass
class CsvSong:
    artist: str
    title: str
    year: str
    backcol: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class MatchResult:
    csv_song: CsvSong
    mp3: Optional[Mp3File] = None
    match_type: str = "none"       # exact, fuzzy, ai-verified, none
    fuzzy_score: float = 0.0
    ai_verdict: Optional[dict] = None
    suggested_filename: str = ""
    issues: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Filename / text utilities  (umlaut-aware)
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Normalize unicode and strip surrounding whitespace."""
    if not text:
        return ""
    return unicodedata.normalize('NFC', str(text).strip())


def sanitize_filename_component(name: str) -> str:
    """
    Sanitize a string for use in a filename.
    Preserves Unicode letters including German umlauts (äöüß).
    Only removes characters that are invalid or unsafe in filenames.
    """
    name = normalize_text(name)
    name = name.replace(" ", "_")
    name = name.replace("/", "_")
    # Remove control characters
    name = "".join(ch for ch in name if not unicodedata.category(ch).startswith('C'))
    # On Linux only / and \0 are truly invalid; be conservative for cross-platform
    name = re.sub(r'[<>:"\\|?*\x00]', "", name)
    # Collapse multiple underscores
    name = re.sub(r'_+', '_', name)
    return name.strip("_")


def expected_filename(year: str, artist: str, title: str) -> str:
    """Generate the standard filename for a song."""
    safe_year = sanitize_filename_component(str(year))
    safe_artist = sanitize_filename_component(artist)
    safe_title = sanitize_filename_component(title)
    return f"{safe_year}_{safe_artist}_{safe_title}.mp3"


def filename_from_id3(mp3: Mp3File) -> str:
    """Generate a filename suggestion from ID3 tags."""
    year = mp3.year if mp3.year else "0000"
    return expected_filename(year, mp3.artist, mp3.title)


# ---------------------------------------------------------------------------
# ID3 reading
# ---------------------------------------------------------------------------

def read_mp3_metadata(path: Path) -> Mp3File:
    """Read ID3 tags from an MP3 file."""
    mp3 = Mp3File(path=path, rel_path=path)
    try:
        audio = MP3(path)
        if audio.tags is None:
            audio.add_tags()
        # EasyID3 fallback for common frames
        try:
            easy = EasyID3(path)
            mp3.artist = normalize_text(easy.get("artist", [""])[0])
            mp3.title = normalize_text(easy.get("title", [""])[0])
            mp3.album = normalize_text(easy.get("album", [""])[0])
            mp3.year = normalize_text(easy.get("date", [""])[0])
            mp3.genre = normalize_text(easy.get("genre", [""])[0])
        except Exception:
            pass
        # Also try raw ID3 for year
        try:
            raw = ID3(path)
            if not mp3.year:
                for frameid in ("TDRC", "TYER", "TDRL"):
                    if frameid in raw:
                        mp3.year = normalize_text(str(raw[frameid].text[0]))[:4]
                        break
            if not mp3.artist:
                if "TPE1" in raw:
                    mp3.artist = normalize_text(str(raw["TPE1"].text[0]))
            if not mp3.title:
                if "TIT2" in raw:
                    mp3.title = normalize_text(str(raw["TIT2"].text[0]))
            if not mp3.album:
                if "TALB" in raw:
                    mp3.album = normalize_text(str(raw["TALB"].text[0]))
        except Exception:
            pass
    except Exception as e:
        print(f"Warning: could not read metadata from {path}: {e}", file=sys.stderr)
    return mp3


# ---------------------------------------------------------------------------
# File scanning & matching
# ---------------------------------------------------------------------------

def scan_music_files(music_dir: Path) -> list[Mp3File]:
    """Recursively scan for MP3 files and read their metadata."""
    files = []
    for path in sorted(music_dir.rglob("*.mp3")):
        rel = path.relative_to(music_dir)
        mp3 = read_mp3_metadata(path)
        mp3.rel_path = rel
        files.append(mp3)
    return files


def make_exact_key(year: str, artist: str, title: str) -> str:
    return expected_filename(year, artist, title).lower()


def find_exact_match(csv_song: CsvSong, mp3_files: list[Mp3File]) -> Optional[Mp3File]:
    key = make_exact_key(csv_song.year, csv_song.artist, csv_song.title)
    for mp3 in mp3_files:
        if mp3.path.name.lower() == key:
            return mp3
    return None


def fuzzy_match_score(csv_song: CsvSong, mp3: Mp3File) -> float:
    """Compute a composite fuzzy score between CSV entry and MP3 metadata."""
    expected = expected_filename(csv_song.year, csv_song.artist, csv_song.title)
    fname_score = fuzz.ratio(expected.lower(), mp3.path.name.lower()) / 100.0

    artist_score = fuzz.ratio(csv_song.artist.lower(), mp3.artist.lower()) / 100.0 if mp3.artist else 0.0
    title_score = fuzz.ratio(csv_song.title.lower(), mp3.title.lower()) / 100.0 if mp3.title else 0.0
    year_score = 1.0 if csv_song.year in mp3.year else 0.0

    score = (
        fname_score * 0.40 +
        artist_score * 0.25 +
        title_score * 0.25 +
        year_score * 0.10
    )
    return score


def find_best_fuzzy_match(csv_song: CsvSong, mp3_files: list[Mp3File]) -> tuple[Optional[Mp3File], float]:
    best_mp3 = None
    best_score = 0.0
    for mp3 in mp3_files:
        score = fuzzy_match_score(csv_song, mp3)
        if score > best_score:
            best_score = score
            best_mp3 = mp3
    return best_mp3, best_score


# ---------------------------------------------------------------------------
# AI verification  (single + batch)
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> str:
    """Extract JSON from markdown fences or plain text."""
    text = text.strip()
    if "```json" in text:
        return text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text


def call_ai_verifier_single(client, model: str, csv_song: CsvSong, mp3: Mp3File) -> Optional[dict]:
    """Call the OpenAI-compatible API to verify a single match."""
    if client is None:
        return None
    prompt = f"""You are verifying MP3 files for a music-guessing board game (like Hitster). The goal is to ensure the audio file is the correct, recognizable song — not a cover, instrumental, live recording, or remix. The CSV year is always authoritative for the printed card; never flag a year mismatch from a compilation or remaster as an issue.

EXPECTED SONG:
- Artist: {csv_song.artist}
- Title: {csv_song.title}
- Year (authoritative for the game): {csv_song.year}

ACTUAL MP3 METADATA:
- Filename: {mp3.path.name}
- ID3 Artist: {mp3.artist or '(missing)'}
- ID3 Title: {mp3.title or '(missing)'}
- ID3 Album: {mp3.album or '(missing)'}
- ID3 Year: {mp3.year or '(missing)'}
- ID3 Genre: {mp3.genre or '(missing)'}

TASK:
1. Determine if the actual file is the correct, recognizable song.
2. Flag ONLY these real problems in the "issues" array:
   - "cover": A different artist performing the song.
   - "instrumental": No vocals / karaoke version.
   - "live": A live concert recording (audience noise, different arrangement).
   - "remix": A significantly altered version (DJ remix, dub mix) that changes the familiar sound.
   - "wrong song": Completely different song than expected.
   - "extended": Extended version with very long intro/outro beats that could confuse gameplay.
3. DO NOT flag these as issues:
   - Year mismatch from compilations, greatest hits, or remasters (the CSV year is authoritative).
   - "Album Version" — this is usually the version people remember.
   - "Remastered" — remasters often sound better and are preferred.
4. Suggest a clean filename in the format: YYYY_Artist_Title.mp3
   - Use the CSV year, NOT the MP3 metadata year.
   - Preserve German umlauts (ä, ö, ü, ß) and other Unicode characters.
   - Replace spaces with underscores.
   - Remove unsafe filename characters.

Respond ONLY with a JSON object in this exact format:
{{
  "is_correct": true/false,
  "is_cover": true/false,
  "is_instrumental": true/false,
  "is_live": true/false,
  "is_remix": true/false,
  "confidence": 0.0-1.0,
  "issues": ["list any real issues here, or empty list"],
  "suggested_filename": "YYYY_Artist_Title.mp3",
  "notes": "brief explanation"
}}
"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a precise music metadata verifier. Your response must be a valid JSON object."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        raw_content = response.choices[0].message.content
        if not raw_content or not raw_content.strip():
            print(f"  Warning: AI returned empty content. Skipping AI verification.", file=sys.stderr)
            return None
        content = _extract_json(raw_content)
        return json.loads(content)
    except Exception as e:
        print(f"  AI verification failed: {e}", file=sys.stderr)
        return None


def build_batch_prompt(items: list[tuple[CsvSong, Mp3File]]) -> str:
    """Build a prompt that verifies multiple songs at once."""
    lines = [
        "You are verifying MP3 files for a music-guessing board game (like Hitster). The goal is to ensure each audio file is the correct, recognizable song — not a cover, instrumental, live recording, or remix.",
        "You will receive a numbered list of EXPECTED songs and their ACTUAL MP3 metadata.",
        "The CSV year is always authoritative for the printed card. Do NOT flag year mismatches from compilations or remasters as issues.",
        "",
        "For each entry, determine if the file is the correct song, and flag ONLY these real problems in the 'issues' array:",
        '- "cover": A different artist performing the song.',
        '- "instrumental": No vocals / karaoke version.',
        '- "live": A live concert recording (audience noise, different arrangement).',
        '- "remix": A significantly altered version (DJ remix, dub mix) that changes the familiar sound.',
        '- "wrong song": Completely different song than expected.',
        '- "extended": Extended version with very long intro/outro beats that could confuse gameplay.',
        "",
        "DO NOT flag these as issues:",
        '- Year mismatch from compilations, greatest hits, or remasters (the CSV year is authoritative).',
        '- "Album Version" — this is usually the version people remember.',
        '- "Remastered" — remasters often sound better and are preferred.',
        "",
        "Respond ONLY with a JSON object containing a single key 'results' which is an array.",
        "Each element in the results array must be an object in this exact format:",
        '{\n  "index": 0,\n  "is_correct": true/false,\n  "is_cover": true/false,\n  "is_instrumental": true/false,\n  "is_live": true/false,\n  "is_remix": true/false,\n  "confidence": 0.0-1.0,\n  "issues": ["list any real issues here, or empty list"],\n  "suggested_filename": "YYYY_Artist_Title.mp3",\n  "notes": "brief explanation"\n}',
        "",
        "Rules for suggested_filename:",
        "- Use the CSV year, NOT the MP3 metadata year.",
        "- Preserve German umlauts (ä, ö, ü, ß) and other Unicode characters.",
        "- Replace spaces with underscores.",
        "- Remove unsafe filename characters.",
        "",
        "Here are the entries:",
        "",
    ]
    for idx, (csv_song, mp3) in enumerate(items):
        lines.append(f"--- ENTRY {idx} ---")
        lines.append(f"Expected Artist: {csv_song.artist}")
        lines.append(f"Expected Title: {csv_song.title}")
        lines.append(f"Expected Year: {csv_song.year}")
        lines.append(f"Actual Filename: {mp3.path.name}")
        lines.append(f"ID3 Artist: {mp3.artist or '(missing)'}")
        lines.append(f"ID3 Title: {mp3.title or '(missing)'}")
        lines.append(f"ID3 Album: {mp3.album or '(missing)'}")
        lines.append(f"ID3 Year: {mp3.year or '(missing)'}")
        lines.append(f"ID3 Genre: {mp3.genre or '(missing)'}")
        lines.append("")
    return "\n".join(lines)


def call_ai_verifier_batch(client, model: str, items: list[tuple[CsvSong, Mp3File]]) -> list[Optional[dict]]:
    """Verify a batch of songs in a single API call."""
    if client is None or not items:
        return [None] * len(items)

    prompt = build_batch_prompt(items)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a precise music metadata verifier. Your response must be a valid JSON array."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=4000 + len(items) * 400,
            response_format={"type": "json_object"},
        )
        raw_content = response.choices[0].message.content
        if not raw_content or not raw_content.strip():
            print(f"  Warning: AI returned empty content. Skipping AI verification.", file=sys.stderr)
            return [None] * len(items)
        content = _extract_json(raw_content)
        parsed = json.loads(content)

        # Normalize to list
        if isinstance(parsed, dict) and "results" in parsed:
            parsed = parsed["results"]
        if not isinstance(parsed, list):
            print(f"  Warning: AI returned non-array, wrapping: {type(parsed)}", file=sys.stderr)
            parsed = [parsed]

        # Map by index
        results: list[Optional[dict]] = [None] * len(items)
        for item in parsed:
            if isinstance(item, dict) and "index" in item:
                idx = int(item["index"])
                if 0 <= idx < len(items):
                    results[idx] = item
        return results
    except Exception as e:
        print(f"  Batch AI verification failed: {e}", file=sys.stderr)
        print(f"  Falling back to individual verification for {len(items)} song(s)...", file=sys.stderr)
        results: list[Optional[dict]] = [None] * len(items)
        for idx, (csv_song, mp3) in enumerate(items):
            result = call_ai_verifier_single(client, model, csv_song, mp3)
            if result:
                result["index"] = idx
                results[idx] = result
        return results


def run_ai_verification(client, model: str, batch_size: int, fuzzy_results: list[tuple[MatchResult, float]]) -> None:
    """
    Run AI verification on fuzzy matches.
    Supports batching for efficiency.
    """
    if not fuzzy_results:
        return

    total = len(fuzzy_results)
    if batch_size <= 1 or total == 1:
        # Single-mode
        for r, score in fuzzy_results:
            print(f"  [FUZZY] {r.csv_song.artist} - {r.csv_song.title} (score: {score:.0%}) -> verifying with AI...")
            verdict = call_ai_verifier_single(client, model, r.csv_song, r.mp3)
            _apply_verdict(r, verdict)
    else:
        # Batch mode
        print(f"\nAI batch verification: {total} song(s) to check in batches of {batch_size}...")
        for i in range(0, total, batch_size):
            batch = fuzzy_results[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total + batch_size - 1) // batch_size
            print(f"  Batch {batch_num}/{total_batches} ({len(batch)} songs)...", end=" ", flush=True)

            items = [(r.csv_song, r.mp3) for r, _ in batch]
            verdicts = call_ai_verifier_batch(client, model, items)

            ok_count = sum(1 for v in verdicts if v is not None)
            print(f"OK: {ok_count}/{len(batch)}")

            for (r, score), verdict in zip(batch, verdicts):
                _apply_verdict(r, verdict)


def _apply_verdict(r: MatchResult, verdict: Optional[dict]) -> None:
    """Apply an AI verdict to a MatchResult."""
    if verdict:
        r.match_type = "ai-verified"
        r.ai_verdict = verdict
        if verdict.get("suggested_filename"):
            r.suggested_filename = verdict["suggested_filename"]
        if not verdict.get("is_correct", True):
            r.issues.append(f"AI says file is incorrect: {verdict.get('notes', '')}")
        if verdict.get("is_cover"):
            r.issues.append("AI flagged as cover version")
        if verdict.get("is_instrumental"):
            r.issues.append("AI flagged as instrumental")
        if verdict.get("is_live"):
            r.issues.append("AI flagged as live recording")
        if verdict.get("is_remix"):
            r.issues.append("AI flagged as remix")
        if verdict.get("issues"):
            r.issues.extend(verdict["issues"])
    else:
        r.issues.append("AI verification failed")


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

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


def load_csv(csv_path: Path) -> list[CsvSong]:
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
                backcol = normalize_text(row.get("backcol", ""))
                if not artist or not title or not year:
                    print(f"Warning: skipping row with missing data: {row}", file=sys.stderr)
                    continue
                extra = {k: v for k, v in row.items() if k is not None and k not in ("Artist", "Title", "Year", "URL", "backcol")}
                songs.append(CsvSong(artist=artist, title=title, year=year, backcol=backcol, extra=extra))
        else:
            # No header — assume standard column order: Artist, Title, Year, backcol
            reader = csv.reader(f, delimiter=delimiter)
            for parts in reader:
                artist = normalize_text(parts[0] if len(parts) > 0 else "")
                title = normalize_text(parts[1] if len(parts) > 1 else "")
                year = normalize_text(parts[2] if len(parts) > 2 else "")
                backcol = normalize_text(parts[3] if len(parts) > 3 else "")
                if not artist or not title or not year:
                    print(f"Warning: skipping row with missing data: {parts}", file=sys.stderr)
                    continue
                songs.append(CsvSong(artist=artist, title=title, year=year, backcol=backcol))
    return songs


def write_output_csv(results: list[MatchResult], fieldnames: list[str], out_path: Path, base_url: str):
    """Write the card-ready CSV with local URLs."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for r in results:
        if r.mp3 is None:
            continue
        url_path = "/".join(r.mp3.rel_path.parts)
        full_url = f"{base_url.rstrip('/')}/{url_path}"
        row = {
            "Artist": r.csv_song.artist,
            "Title": r.csv_song.title,
            "Year": r.csv_song.year,
            "URL": full_url,
            "backcol": r.csv_song.backcol,
        }
        for k, v in r.csv_song.extra.items():
            if k not in row:
                row[k] = v
        rows.append(row)

    all_keys = {k for k in fieldnames if k is not None}
    for row in rows:
        all_keys.update({k for k in row.keys() if k is not None})
    final_fieldnames = [k for k in fieldnames if k in all_keys]
    for k in sorted(all_keys):
        if k not in final_fieldnames:
            final_fieldnames.append(k)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=final_fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def main():
    # Environment defaults
    env_api_key = os.getenv("OPENAI_API_KEY", "")
    env_api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    env_model = os.getenv("AI_MODEL", "gpt-4o-mini")
    env_batch_size = int(os.getenv("AI_BATCH_SIZE", "20"))
    env_fuzzy = float(os.getenv("FUZZY_THRESHOLD", "0.45"))
    env_base_url = os.getenv("DEFAULT_BASE_URL", "")

    parser = argparse.ArgumentParser(
        description="Verify and rename local MP3 files against a SongSeeker playlist CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Configuration:
  Settings are read from a .env file in the project root automatically.
  Command-line flags always override .env values.
  See .env.example for all available options.

Examples:
  # Dry-run check
  python tools/verify_music.py --csv playlists/80s.csv --music-dir music/80s --base-url http://nas:8887/music/80s

  # With AI verification (batch size from .env or --batch-size)
  python tools/verify_music.py --csv playlists/80s.csv --music-dir music/80s --base-url http://nas:8887/music/80s --verify-ai

  # Rename files and generate card CSV
  python tools/verify_music.py --csv playlists/80s.csv --music-dir music/80s --base-url http://nas:8887/music/80s --rename --output-csv playlists/80s-local.csv
        """
    )
    parser.add_argument("--csv", required=True, help="Path to the input playlist CSV")
    parser.add_argument("--music-dir", required=True, help="Path to the music directory (may contain sub-folders)")
    parser.add_argument("--base-url", default=env_base_url, help="Base URL for the music directory (e.g. http://nas:8887/music/80s)")
    parser.add_argument("--output-csv", help="Path to write the card-ready CSV with local URLs")
    parser.add_argument("--rename", action="store_true", help="Actually rename MP3 files on disk (default: dry-run)")
    parser.add_argument("--verify-ai", action="store_true", help="Use AI to verify ambiguous matches and detect covers/instrumentals")
    parser.add_argument("--api-key", default=env_api_key, help="OpenAI / compatible API key (or set OPENAI_API_KEY in .env)")
    parser.add_argument("--api-base", default=env_api_base, help="OpenAI-compatible API base URL")
    parser.add_argument("--model", default=env_model, help="Model name to use for AI verification")
    parser.add_argument("--batch-size", type=int, default=env_batch_size, help="Number of songs to verify per API call (default: from .env or 20)")
    parser.add_argument("--fuzzy-threshold", type=float, default=env_fuzzy, help="Minimum fuzzy score to consider a match (0.0-1.0)")
    parser.add_argument("--strict", action="store_true", help="Only accept exact filename matches")
    parser.add_argument("--report-json", help="Path to write a machine-readable JSON report of all results")
    args = parser.parse_args()

    # Validate required args
    if not args.base_url:
        parser.error("--base-url is required (or set DEFAULT_BASE_URL in .env)")

    csv_path = Path(args.csv)
    music_dir = Path(args.music_dir)

    if not csv_path.exists():
        print(f"Error: CSV not found: {csv_path}", file=sys.stderr)
        sys.exit(1)
    if not music_dir.is_dir():
        print(f"Error: Music directory not found: {music_dir}", file=sys.stderr)
        sys.exit(1)

    # Load data
    print(f"Loading CSV: {csv_path}")
    csv_songs = load_csv(csv_path)
    print(f"  -> {len(csv_songs)} songs in playlist")

    print(f"Scanning music directory: {music_dir}")
    mp3_files = scan_music_files(music_dir)
    print(f"  -> {len(mp3_files)} MP3 files found")

    # Prepare AI client
    ai_client = None
    if args.verify_ai:
        if not OPENAI_AVAILABLE:
            print("Error: openai package not installed. Run: pip install -r tools/requirements.txt", file=sys.stderr)
            sys.exit(1)
        if not args.api_key:
            print("Error: --api-key is required when using --verify-ai (or set OPENAI_API_KEY in .env)", file=sys.stderr)
            sys.exit(1)
        ai_client = OpenAI(api_key=args.api_key, base_url=args.api_base)
        print(f"AI verifier ready (model: {args.model}, base: {args.api_base}, batch: {args.batch_size})")

    # Track which MP3s have been claimed
    claimed = set()
    results: list[MatchResult] = []
    fuzzy_needs_ai: list[tuple[MatchResult, float]] = []

    print("\nMatching songs...")
    for song in csv_songs:
        expected = expected_filename(song.year, song.artist, song.title)

        # 1. Exact match
        mp3 = find_exact_match(song, [m for m in mp3_files if id(m) not in claimed])
        if mp3:
            results.append(MatchResult(
                csv_song=song,
                mp3=mp3,
                match_type="exact",
                fuzzy_score=1.0,
                suggested_filename=expected,
            ))
            claimed.add(id(mp3))
            print(f"  [EXACT] {song.artist} - {song.title} ({song.year})")
            continue

        if args.strict:
            results.append(MatchResult(
                csv_song=song,
                mp3=None,
                match_type="none",
                issues=["No exact match found (--strict enabled)"],
                suggested_filename=expected,
            ))
            print(f"  [MISS]  {song.artist} - {song.title} ({song.year})")
            continue

        # 2. Fuzzy match
        best_mp3, best_score = find_best_fuzzy_match(song, [m for m in mp3_files if id(m) not in claimed])

        if best_mp3 and best_score >= args.fuzzy_threshold:
            r = MatchResult(
                csv_song=song,
                mp3=best_mp3,
                match_type="fuzzy",
                fuzzy_score=best_score,
                suggested_filename=expected,
            )
            results.append(r)
            claimed.add(id(best_mp3))

            if args.verify_ai and ai_client:
                fuzzy_needs_ai.append((r, best_score))
            else:
                print(f"  [FUZZY] {song.artist} - {song.title} (score: {best_score:.0%})")
        else:
            results.append(MatchResult(
                csv_song=song,
                mp3=None,
                match_type="none",
                issues=[f"No match found (best fuzzy score: {best_score:.0%})"],
                suggested_filename=expected,
            ))
            print(f"  [MISS]  {song.artist} - {song.title} ({song.year})")

    # Run AI verification in batches
    if fuzzy_needs_ai and ai_client:
        run_ai_verification(ai_client, args.model, args.batch_size, fuzzy_needs_ai)

    # Report
    print("\n" + "=" * 70)
    print("VERIFICATION REPORT")
    print("=" * 70)

    exact = sum(1 for r in results if r.match_type == "exact")
    fuzzy = sum(1 for r in results if r.match_type == "fuzzy")
    ai_ver = sum(1 for r in results if r.match_type == "ai-verified")
    missing = sum(1 for r in results if r.match_type == "none")
    flagged = sum(1 for r in results if r.issues)

    print(f"Exact matches:     {exact}")
    print(f"Fuzzy matches:     {fuzzy}")
    print(f"AI-verified:       {ai_ver}")
    print(f"Missing:           {missing}")
    print(f"With issues:       {flagged}")

    # Detailed issues
    issue_results = [r for r in results if r.issues]
    if issue_results:
        print("\n⚠️  FLAGGED SONGS:\n")
        for r in issue_results:
            print(f"  {r.csv_song.artist} - {r.csv_song.title} ({r.csv_song.year})")
            print(f"    Match: {r.match_type}")
            if r.mp3:
                print(f"    File:  {r.mp3.rel_path}")
            for issue in r.issues:
                print(f"    Issue: {issue}")
            print()

    missing_results = [r for r in results if r.match_type == "none"]
    if missing_results:
        print("\n❌ MISSING SONGS:\n")
        for r in missing_results:
            print(f"  Expected: {r.suggested_filename}")

    # Unclaimed MP3s
    unclaimed = [m for m in mp3_files if id(m) not in claimed]
    if unclaimed:
        print("\n📁 UNCLAIMED MP3 FILES (not matched to any CSV entry):\n")
        for m in unclaimed:
            meta = f"[{m.artist} - {m.title}]" if m.artist or m.title else "[no metadata]"
            print(f"  {m.rel_path}  {meta}")

    # Renaming
    renames = 0
    if args.rename:
        print("\n" + "=" * 70)
        print("RENAMING FILES")
        print("=" * 70)
        for r in results:
            if r.mp3 is None:
                continue
            target_name = r.suggested_filename
            if not target_name:
                target_name = expected_filename(r.csv_song.year, r.csv_song.artist, r.csv_song.title)
            source = r.mp3.path
            target = source.parent / target_name
            if source.name == target_name:
                continue
            if target.exists():
                print(f"  SKIP (target exists): {source.name} -> {target_name}")
                continue
            try:
                source.rename(target)
                print(f"  RENAME: {source.name} -> {target_name}")
                renames += 1
            except OSError as e:
                print(f"  ERROR:  {source.name} -> {target_name}: {e}")
        print(f"\nRenamed {renames} file(s).")
    else:
        would_rename = 0
        for r in results:
            if r.mp3 is None:
                continue
            target_name = r.suggested_filename or expected_filename(r.csv_song.year, r.csv_song.artist, r.csv_song.title)
            if r.mp3.path.name != target_name:
                would_rename += 1
        if would_rename:
            print(f"\n{would_rename} file(s) would be renamed. Use --rename to apply.")

    # Generate output CSV
    if args.output_csv:
        # Re-scan if we renamed, so paths are current
        if args.rename and renames > 0:
            print("\nRe-scanning after rename for output CSV...")
            mp3_files = scan_music_files(music_dir)
            fresh_results = []
            for r in results:
                if r.mp3 is None:
                    fresh_results.append(r)
                    continue
                expected_name = r.suggested_filename or expected_filename(r.csv_song.year, r.csv_song.artist, r.csv_song.title)
                found = None
                for m in mp3_files:
                    if m.path.name == expected_name:
                        found = m
                        break
                if found:
                    fresh_results.append(MatchResult(
                        csv_song=r.csv_song,
                        mp3=found,
                        match_type=r.match_type,
                        fuzzy_score=r.fuzzy_score,
                        ai_verdict=r.ai_verdict,
                        suggested_filename=r.suggested_filename,
                        issues=r.issues,
                    ))
                else:
                    fresh_results.append(r)
            results = fresh_results

        delimiter = detect_csv_delimiter(csv_path)
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            fieldnames = reader.fieldnames or ["Artist", "Title", "Year", "URL", "backcol"]

        out_path = Path(args.output_csv)
        write_output_csv(results, fieldnames, out_path, args.base_url)
        print(f"\nCard-ready CSV written to: {out_path}")
        print(f"  -> {sum(1 for r in results if r.mp3)} song(s) with URLs")

    # Write JSON report if requested
    if args.report_json:
        report = []
        for r in results:
            entry = {
                "artist": r.csv_song.artist,
                "title": r.csv_song.title,
                "year": r.csv_song.year,
                "match_type": r.match_type,
                "fuzzy_score": r.fuzzy_score,
                "issues": r.issues,
                "suggested_filename": r.suggested_filename,
            }
            if r.ai_verdict:
                entry["ai_notes"] = r.ai_verdict.get("notes", "")
            if r.mp3:
                entry["file"] = str(r.mp3.path.name)
                entry["id3_artist"] = r.mp3.artist
                entry["id3_title"] = r.mp3.title
                entry["id3_year"] = r.mp3.year
            else:
                entry["file"] = None
            report.append(entry)
        report_path = Path(args.report_json)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    # Final summary & exit code
    print("\n" + "=" * 70)
    if missing:
        print("Result: SOME FILES ARE MISSING")
        sys.exit(1)
    elif flagged:
        print("Result: ALL FILES FOUND, BUT SOME HAVE ISSUES (see above)")
        sys.exit(2)
    else:
        print("Result: ALL FILES FOUND AND VERIFIED")
        sys.exit(0)


if __name__ == "__main__":
    main()
