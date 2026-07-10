"""Basic tests for SongSeeker verify_music helpers.

Run with: python -m pytest tests/ -q
(Requires: pip install -r requirements-dev.txt)
"""
import tempfile
from pathlib import Path
import pytest

# Import the functions we want to test
from tools.verify_music import (
    normalize_text,
    expected_filename,
    detect_csv_delimiter,
    _has_header_row,
)


def test_normalize_text():
    assert normalize_text("Mötley Crüe") == "Mötley Crüe"
    assert normalize_text("  Hello   World  ") == "Hello   World"  # only outer strip
    assert normalize_text("A/B\\C:D") == "A/B\\C:D"  # no filename sanitization here
    assert normalize_text("") == ""


def test_expected_filename():
    assert expected_filename("1985", "A-ha", "Take On Me") == "1985_A-ha_Take_On_Me.mp3"
    assert expected_filename("1999", "Lou Bega", "Mambo No. 5") == "1999_Lou_Bega_Mambo_No._5.mp3"
    # Umlauts preserved, spaces -> _, most punctuation kept unless unsafe
    assert expected_filename("1981", "Die Ärzte", "Zu spät!") == "1981_Die_Ärzte_Zu_spät!.mp3"
    # Unsafe chars (: / ? etc) are stripped; / becomes _
    assert expected_filename("2000", "A/B", "C:D?") == "2000_A_B_CD.mp3"


def test_has_header_row():
    assert _has_header_row("Artist,Title,Year", ",") is True
    assert _has_header_row("Soft Cell;Tainted Love;1981", ";") is False
    assert _has_header_row("artist,title,year,backcol", ",") is True


def test_detect_csv_delimiter():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "test.csv"

        # semicolon style (as used in source playlists)
        p.write_text("Artist;Title;Year;backcol\nSoft Cell;Tainted Love;1981;0.1,0.2,0.3\n", encoding="utf-8")
        assert detect_csv_delimiter(p) == ";"

        # comma style (generated local CSVs)
        p.write_text("Artist,Title,Year,URL\nA,B,2020,http://ex.com/a.mp3\n", encoding="utf-8")
        assert detect_csv_delimiter(p) == ","


def test_detect_csv_delimiter_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "weird.csv"
        p.write_text("just one line without much punctuation\n", encoding="utf-8")
        # Should default to comma when heuristic is inconclusive
        assert detect_csv_delimiter(p) == ","
