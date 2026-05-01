#!/usr/bin/env python3
"""
SongSeeker Workflow Wizard

An interactive terminal wrapper that guides you through the entire
process of adding new songs to SongSeeker:

  1. Select a playlist CSV
  2. Pre-check CSV for issues
  3. Download with deemix (from CSV)
  4. Verify, match & rename local MP3s
  5. Generate printable cards

Usage:
    python tools/workflow.py

All configuration is read from your .env file. Command-line overrides
are supported for non-interactive use:
    python tools/workflow.py --csv playlists/80s.csv --music-dir music/80s --base-url http://nas:8887/music
"""

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Terminal colors
# ---------------------------------------------------------------------------
C = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "magenta": "\033[95m",
    "cyan": "\033[96m",
}


def c(text: str, color: str = "") -> str:
    if not color:
        return text
    return f"{C.get(color, '')}{text}{C['reset']}"


def print_banner():
    print()
    print(c("  ╔═══════════════════════════════════════════════════════════════╗", "cyan"))
    print(c("  ║          🎵  SongSeeker Workflow Wizard  🎵                  ║", "cyan"))
    print(c("  ║                                                               ║", "cyan"))
    print(c("  ║  Guides you through importing, downloading, verifying,       ║", "cyan"))
    print(c("  ║  renaming, and generating cards for your music.              ║", "cyan"))
    print(c("  ╚═══════════════════════════════════════════════════════════════╝", "cyan"))
    print()


def print_section(title: str):
    print()
    print(c(f"── {title} ", "bold") + c("─" * (62 - len(title)), "dim"))


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        ans = input(c(prompt + suffix + ": ", "blue")).strip().lower()
        if not ans:
            return default
        if ans in ("y", "yes", "ja", "j"):
            return True
        if ans in ("n", "no", "nein"):
            return False
        print(c("  Please answer y or n.", "yellow"))


def ask_choice(prompt: str, choices: list[str], allow_custom: bool = False) -> str:
    print(c(prompt, "blue"))
    for i, choice in enumerate(choices, 1):
        print(f"  {c(str(i), 'bold')}. {choice}")
    if allow_custom:
        print(f"  {c('0', 'bold')}. (custom path)")
    while True:
        ans = input(c("Enter number: ", "blue")).strip()
        if allow_custom and ans == "0":
            return input(c("Enter custom path: ", "blue")).strip()
        try:
            idx = int(ans)
            if 1 <= idx <= len(choices):
                return choices[idx - 1]
        except ValueError:
            pass
        print(c("  Invalid choice. Try again.", "yellow"))


def ask_input(prompt: str, default: str = "") -> str:
    if default:
        val = input(c(f"{prompt} [{default}]: ", "blue")).strip()
        return val if val else default
    return input(c(f"{prompt}: ", "blue")).strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def discover_csvs() -> list[Path]:
    root = Path(__file__).resolve().parent.parent
    csvs = sorted(root.glob("playlists/*.csv"))
    csvs += sorted(root.glob("*.csv"))
    return csvs


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


def _peek_first_line(csv_path: Path) -> str:
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        return f.readline()


def validate_csv(csv_path: Path) -> bool:
    """Check that the CSV has the minimum required columns."""
    try:
        delimiter = detect_csv_delimiter(csv_path)
        first_line = _peek_first_line(csv_path)
        has_header = _has_header_row(first_line, delimiter)

        if not has_header:
            print(c(f"  ℹ No header row detected. Assuming columns: Artist, Title, Year, backcol", "yellow"))
            return True

        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            if not reader.fieldnames:
                print(c(f"Error: {csv_path} has no header row.", "red"))
                return False
            headers = [h.strip().lower() for h in reader.fieldnames]
            missing = []
            if "artist" not in headers:
                missing.append("Artist")
            if "title" not in headers:
                missing.append("Title")
            if missing:
                print(c(f"Error: {csv_path} is missing required column(s): {', '.join(missing)}", "red"))
                print(c("Expected header row includes at least: Artist, Title, Year", "yellow"))
                return False
    except Exception as e:
        print(c(f"Error reading {csv_path}: {e}", "red"))
        return False
    return True


def discover_music_dirs() -> list[Path]:
    root = Path(__file__).resolve().parent.parent
    music_root = root / "music"
    if not music_root.exists():
        return []
    return sorted([d for d in music_root.iterdir() if d.is_dir()])


def check_env() -> dict:
    """Check which .env variables are set."""
    return {
        "openai_key": bool(os.getenv("OPENAI_API_KEY", "")),
        "deemix_arl": bool(os.getenv("DEEMIX_ARL", "")),
        "base_url": os.getenv("DEFAULT_BASE_URL", ""),
    }


def run_command(cmd: list[str], description: str) -> int:
    """Run a subprocess and stream output."""
    print(c(f"\n▶ Running: {description}", "dim"))
    print(c("  ", "dim") + " ".join(cmd))
    print()
    result = subprocess.run(cmd)
    return result.returncode


def pre_check_csv(csv_path: Path, non_interactive: bool = False) -> bool:
    """Deep-check the CSV for common issues before downloading."""
    print_section("Pre-check: Playlist CSV")

    try:
        delimiter = detect_csv_delimiter(csv_path)
        first_line = _peek_first_line(csv_path)
        has_header = _has_header_row(first_line, delimiter)

        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            if has_header:
                reader = csv.DictReader(f, delimiter=delimiter)
                rows = list(reader)
            else:
                # No header — assume standard column order: Artist, Title, Year, backcol
                reader = csv.reader(f, delimiter=delimiter)
                rows = []
                for parts in reader:
                    rows.append({
                        "Artist": parts[0] if len(parts) > 0 else "",
                        "Title": parts[1] if len(parts) > 1 else "",
                        "Year": parts[2] if len(parts) > 2 else "",
                        "backcol": parts[3] if len(parts) > 3 else "",
                    })
    except Exception as e:
        print(c(f"Error reading CSV: {e}", "red"))
        return False

    issues = []
    seen = {}
    empty_artist = 0
    empty_title = 0
    missing_year = 0

    for idx, row in enumerate(rows, start=(2 if has_header else 1)):
        artist = str(row.get("Artist", "")).strip()
        title = str(row.get("Title", "")).strip()
        year = str(row.get("Year", "")).strip()

        if not artist:
            empty_artist += 1
            issues.append((idx, "Empty Artist"))
        if not title:
            empty_title += 1
            issues.append((idx, "Empty Title"))
        if not year:
            missing_year += 1

        key = (artist.lower(), title.lower())
        if key in seen:
            issues.append((idx, f"Duplicate of row {seen[key]}: {artist} - {title}"))
        else:
            seen[key] = idx

    # Report
    print(f"  Total rows:   {len(rows)}")
    print(f"  Empty Artist: {empty_artist}")
    print(f"  Empty Title:  {empty_title}")
    print(f"  Missing Year: {missing_year}")
    print(f"  Duplicates:   {len([i for i in issues if i[1].startswith('Duplicate')])}")

    if issues:
        print()
        print(c("  ⚠ Issues found:", "yellow"))
        for row_num, msg in issues[:20]:
            print(f"    Row {row_num}: {msg}")
        if len(issues) > 20:
            print(f"    ... and {len(issues) - 20} more")
        print()

        if non_interactive:
            print(c("  Non-interactive mode: aborting due to CSV issues.", "red"))
            return False

        if not ask_yes_no("Continue anyway?", default=False):
            print(c("  Fix your CSV and re-run.", "yellow"))
            return False
    else:
        print(c("  ✅ CSV looks good!", "green"))

    return True


# ---------------------------------------------------------------------------
# Wizard steps
# ---------------------------------------------------------------------------

def step_select_csv() -> Path:
    print_section("Step 1: Select Playlist CSV")
    csvs = discover_csvs()
    if csvs:
        choices = [str(p.relative_to(Path(__file__).resolve().parent.parent)) for p in csvs]
        choice = ask_choice("Available playlists:", choices, allow_custom=True)
        return Path(__file__).resolve().parent.parent / choice
    else:
        print(c("No CSV files found in playlists/ or project root.", "yellow"))
        path = ask_input("Enter path to your CSV file")
        return Path(path)


def step_select_music_dir(csv_path: Path) -> Path:
    print_section("Step 2: Select Music Output Folder")
    dirs = discover_music_dirs()
    default_name = csv_path.stem.replace("-local", "").replace("_local", "")
    default_dir = f"music/{default_name}"
    root = Path(__file__).resolve().parent.parent
    default_path = root / default_dir

    # If the suggested folder already exists, use it by default
    if default_path.exists():
        print(c(f"Using existing folder: {default_dir}", "green"))
        return default_path

    # Otherwise suggest creating it
    print(c(f"Suggested folder: {default_dir}", "dim"))
    if dirs:
        choices = [str(d.relative_to(root)) for d in dirs]
        choice = ask_choice("Available music folders:", choices, allow_custom=True)
        if choice != "(custom path)":
            return root / choice

    if ask_yes_no(f"Create folder '{default_dir}'?", default=True):
        default_path.mkdir(parents=True, exist_ok=True)
        return default_path

    path = ask_input("Enter music folder path", default_dir)
    p = root / path
    p.mkdir(parents=True, exist_ok=True)
    return p


def step_download(csv_path: Path, music_dir: Path, non_interactive: bool = False) -> bool:
    print_section("Step 3: Download with deemix (optional)")
    env = check_env()

    if not env["deemix_arl"]:
        print(c("ℹ DEEMIX_ARL not found in .env", "yellow"))
        print(c("  Skip this step if you already downloaded the music.", "dim"))
        if non_interactive:
            return False
        if ask_yes_no("Show guide to get your ARL token?", default=True):
            print(c("""
  ═══════════════════════════════════════════════════════════════
   How to get your Deezer ARL token for deemix
  ═══════════════════════════════════════════════════════════════

  1. Open your web browser and go to https://www.deezer.com
  2. Log into your Deezer account (free account works)
  3. Open Developer Tools:
     - Chrome/Edge:   Press F12
     - Firefox:       Press F12 or Ctrl+Shift+K
     - Safari:        Enable Develop menu first
  4. Go to the Application (Chrome) or Storage (Firefox) tab
  5. In the left sidebar, click  Cookies → https://www.deezer.com
  6. Find the row with Name =  arl
  7. Double-click the Value field and copy the long string
     (looks like: 1234567890abcdef...)
  8. Open your .env file and add:
     DEEMIX_ARL=your_copied_value
  9. Save the file and re-run this wizard.

  Tip: The ARL token is long (~192 chars). Make sure you copy
  the entire value without spaces.
  ═══════════════════════════════════════════════════════════════
            """, "cyan"))
            input(c("Press Enter to continue...", "dim"))
        return False

    if non_interactive:
        do_dl = True
    else:
        do_dl = ask_yes_no("Download tracks with deemix?", default=True)
    if not do_dl:
        return False

    cmd = [
        sys.executable, "tools/deemix_download.py",
        "--from-csv", str(csv_path),
        "--output", str(music_dir),
    ]
    if env["openai_key"]:
        cmd.append("--ai-fallback")

    rc = run_command(cmd, f"Downloading to: {music_dir}")
    return rc == 0


def step_verify(csv_path: Path, music_dir: Path, base_url: str, non_interactive: bool = False) -> tuple[bool, Path]:
    print_section("Step 4: Verify, Match & Rename")

    if non_interactive:
        do_verify = True
    else:
        do_verify = ask_yes_no("Run verification now?", default=True)
    if not do_verify:
        return False, Path()

    env = check_env()
    use_ai = False
    if env["openai_key"]:
        if non_interactive:
            use_ai = True
        else:
            use_ai = ask_yes_no("Use AI verification (detects covers/instrumentals)?", default=True)
    else:
        print(c("ℹ OPENAI_API_KEY not found in .env — AI verification skipped.", "yellow"))
        print(c("  Add it to .env to enable AI verification.", "dim"))

    if non_interactive:
        rename = True
    else:
        rename = ask_yes_no("Automatically rename files to standard format?", default=True)

    local_csv = csv_path.parent / f"{csv_path.stem}-local.csv"
    if local_csv.name == csv_path.name:
        local_csv = csv_path.parent / f"{csv_path.stem}-local.csv"

    report_json = csv_path.parent / f"{csv_path.stem}-report.json"

    cmd = [
        sys.executable, "tools/verify_music.py",
        "--csv", str(csv_path),
        "--music-dir", str(music_dir),
        "--base-url", base_url,
        "--output-csv", str(local_csv),
        "--report-json", str(report_json),
    ]
    if rename:
        cmd.append("--rename")
    if use_ai:
        cmd.append("--verify-ai")

    rc = run_command(cmd, "Verifying and renaming")

    # Handle flagged songs (exit code 2 = issues found)
    if rc == 2 and report_json.exists() and not non_interactive:
        try:
            import json as _json
            with open(report_json, "r", encoding="utf-8") as f:
                report = _json.load(f)
            flagged = [r for r in report if r.get("issues") and r.get("file")]
            if flagged:
                print()
                print(c("⚠️  AI flagged the following songs:", "yellow"))
                for r in flagged:
                    print(f"  • {r['artist']} - {r['title']} ({r['year']})")
                    for issue in r["issues"]:
                        print(f"    → {issue}")
                print()

                # Ask per-song which ones to retry
                retry_songs = []
                for r in flagged:
                    bad_file = music_dir / r["file"]
                    if bad_file.exists():
                        print(f"\n  File: {bad_file.name}")
                        if ask_yes_no(f"Delete and retry '{r['artist']} - {r['title']}'?", default=False):
                            bad_file.unlink()
                            print(c(f"  🗑️  Deleted: {bad_file.name}", "dim"))
                            retry_songs.append(r)

                if retry_songs:
                    # Build a retry CSV with ai_notes for smarter re-download
                    retry_csv = csv_path.parent / f"{csv_path.stem}-retry.csv"
                    with open(retry_csv, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f, delimiter=",")
                        writer.writerow(["Artist", "Title", "Year", "backcol", "ai_notes"])
                        for r in retry_songs:
                            writer.writerow([
                                r["artist"],
                                r["title"],
                                r["year"],
                                "",
                                r.get("ai_notes", ""),
                            ])
                    print(c(f"\nRetrying {len(retry_songs)} song(s) with smarter search...", "yellow"))
                    dl_cmd = [
                        sys.executable, "tools/deemix_download.py",
                        "--from-csv", str(retry_csv),
                        "--output", str(music_dir),
                    ]
                    if env.get("openai_key"):
                        dl_cmd.append("--ai-fallback")
                    run_command(dl_cmd, f"Re-downloading {len(retry_songs)} song(s)")
                    retry_csv.unlink(missing_ok=True)

                    # Re-run verification after re-download
                    print(c("\nRe-running verification...", "cyan"))
                    rc = run_command(cmd, "Re-verifying after re-download")
        except Exception as e:
            print(c(f"Could not process flag report: {e}", "red"))

    if local_csv.exists():
        return True, local_csv
    return False, Path()


def step_generate_cards(local_csv: Path, set_name: str = "", non_interactive: bool = False) -> bool:
    print_section("Step 5: Generate Printable Cards")

    if not local_csv.exists():
        print(c("Local CSV not found. Skipping card generation.", "yellow"))
        return False

    if non_interactive:
        do_gen = True
    else:
        do_gen = ask_yes_no("Generate PDF cards now?", default=True)
    if not do_gen:
        return False

    # Ask about icon (default: no)
    if non_interactive:
        use_icon = False
    else:
        use_icon = ask_yes_no("Embed icon in QR codes?", default=False)

    icon_path = ""
    if use_icon:
        icon_path = os.getenv("ICON_PATH", "icons/icon-96x96.png")
        if not Path(icon_path).exists():
            print(c(f"  Icon not found at {icon_path}. Generating without icon.", "yellow"))
            icon_path = ""

    # Ask about colored backs (default: no)
    if non_interactive:
        use_color = False
    else:
        use_color = ask_yes_no("Use colored card backs (backcol from CSV)?", default=False)

    pdf_name = f"cards-{local_csv.stem.replace('-local', '')}.pdf"
    pdf_path = Path("cards") / pdf_name
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "tools/generate_cards.py",
        str(local_csv),
        str(pdf_path),
    ]
    if icon_path:
        cmd += ["--icon", icon_path]
    if use_color:
        cmd.append("--color")
    if set_name:
        cmd += ["--set-name", set_name]

    rc = run_command(cmd, f"Generating PDF: {pdf_path}")

    if rc == 0 and pdf_path.exists():
        print(c(f"\n✅ Cards saved to: {pdf_path}", "green"))
        return True
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="SongSeeker Workflow Wizard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--csv", help="Path to playlist CSV (skips selection)")
    parser.add_argument("--music-dir", help="Path to music folder (skips selection)")
    parser.add_argument("--base-url", help="Base URL for music (e.g. http://nas:8887/music/80s)")
    parser.add_argument("--skip-download", action="store_true", help="Skip deemix download step")
    parser.add_argument("--skip-verify", action="store_true", help="Skip verification step")
    parser.add_argument("--skip-cards", action="store_true", help="Skip card generation")
    parser.add_argument("--non-interactive", action="store_true", help="Use defaults without asking")
    args = parser.parse_args()

    print_banner()

    # Env check
    env = check_env()
    print(c("Configuration status:", "bold"))
    print(f"  OpenAI API:  {c('✅ configured', 'green') if env['openai_key'] else c('❌ not set', 'red')}")
    print(f"  Deemix ARL:  {c('✅ configured', 'green') if env['deemix_arl'] else c('❌ not set', 'red')}")
    print(f"  Default URL: {env['base_url'] or c('not set', 'red')}")
    print()

    # Step 1: CSV
    if args.csv:
        csv_path = Path(args.csv)
    else:
        csv_path = step_select_csv()

    if not csv_path.exists():
        print(c(f"Error: CSV not found: {csv_path}", "red"))
        sys.exit(1)

    if not validate_csv(csv_path):
        sys.exit(1)

    if not pre_check_csv(csv_path, non_interactive=args.non_interactive):
        sys.exit(1)

    # Step 2: Music dir
    if args.music_dir:
        music_dir = Path(args.music_dir)
        music_dir.mkdir(parents=True, exist_ok=True)
    else:
        music_dir = step_select_music_dir(csv_path)

    # Step 2.5: Base URL
    # If --base-url is given, use it directly.
    # If DEFAULT_BASE_URL is in .env, append the music folder name automatically.
    base_url = ""
    if args.base_url:
        base_url = args.base_url
    elif env["base_url"]:
        base_url = env["base_url"].rstrip("/") + "/" + music_dir.name
    else:
        folder_name = music_dir.name
        base_url = ask_input("Enter base URL for this music folder", f"http://localhost:8887/music/{folder_name}")

    # Step 3: Download
    if not args.skip_download:
        step_download(csv_path, music_dir, non_interactive=args.non_interactive)

    # Step 4: Verify
    local_csv = Path()
    if not args.skip_verify:
        ok, local_csv = step_verify(csv_path, music_dir, base_url, non_interactive=args.non_interactive)

    # Step 5: Cards
    if not args.skip_cards and local_csv.exists():
        step_generate_cards(local_csv, set_name=music_dir.name, non_interactive=args.non_interactive)

    # Final message
    print()
    print(c("╔═══════════════════════════════════════════════════════════════╗", "green"))
    print(c("║                  🎉  Workflow Complete!  🎉                  ║", "green"))
    print(c("╚═══════════════════════════════════════════════════════════════╝", "green"))
    print()
    print(f"  CSV:        {csv_path}")
    print(f"  Music:      {music_dir}")
    if local_csv.exists():
        print(f"  Local CSV:  {local_csv}")
    print()
    print(c("Next steps:", "bold"))
    print("  1. Restart Docker if you added new music folders:")
    print(c("     docker compose restart", "dim"))
    print("  2. Print the PDF and cut the cards.")
    print("  3. Scan and play! 🎵")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print(c("\n👋 Interrupted by user. Goodbye!", "yellow"))
        sys.exit(130)
