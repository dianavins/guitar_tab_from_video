"""Turn a guitar-transcription MIDI (+ sibling CSV) into a tab PDF via MuseScore.

Pipeline: CSV -> cleanup & quantize -> music21 Score with TabClef -> MusicXML
-> MuseScore CLI -> tab-only PDF + editable .mscz.

The sibling CSV (same stem as the input .mid) is required because MIDI itself
does not preserve Basic Pitch's per-note confidence, which the cleanup needs.
"""
import argparse
import csv
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TABS_OUT_DIR = SCRIPT_DIR / "tabs"
ALLOWED_SUFFIXES = {".mid"}
DEFAULT_MUSESCORE = Path(r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe")

GUITAR_MIDI_MIN = 40  # E2
GUITAR_MIDI_MAX = 88  # E6

STANDARD_TUNING = "EADGBE"
NOTE_SEMITONES = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4,
    "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8,
    "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


def parse_tuning(s: str) -> list[str]:
    """Parse a tuning string like 'DADF#BD' or 'EbADGBE' into 6 note names (low-to-high)."""
    notes: list[str] = []
    i = 0
    while i < len(s):
        c = s[i].upper()
        if c not in "ABCDEFG":
            sys.exit(f"Invalid character {s[i]!r} in tuning at position {i}: {s!r}")
        note = c
        if i + 1 < len(s) and s[i + 1] in "#b":
            note += s[i + 1]
            i += 1
        notes.append(note)
        i += 1
    if len(notes) != 6:
        sys.exit(f"Tuning must have 6 notes, got {len(notes)} ({notes}) from {s!r}")
    return notes


def tuning_with_octaves(tuning_notes: list[str]) -> list[str]:
    """Assign octaves so each string is strictly higher than the previous (lowest = octave 2)."""
    def midi(note: str, octave: int) -> int:
        return 12 * (octave + 1) + NOTE_SEMITONES[note]

    pitches: list[str] = []
    prev_midi = -1
    octave = 2
    for note in tuning_notes:
        while midi(note, octave) <= prev_midi:
            octave += 1
        pitches.append(f"{note}{octave}")
        prev_midi = midi(note, octave)
    return pitches


def load_csv_notes(csv_path: Path) -> list[dict]:
    notes: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            notes.append({
                "start": float(row["start_s"]),
                "duration_s": float(row["duration_s"]),
                "pitch": int(row["pitch_midi"]),
                "confidence": float(row["confidence"]),
            })
    return notes


def clean_notes(
    notes: list[dict],
    min_confidence: float,
    min_note_ms: int,
    dedup_window_ms: int,
) -> list[dict]:
    kept = [
        n for n in notes
        if n["confidence"] >= min_confidence
        and n["duration_s"] * 1000.0 >= min_note_ms
        and GUITAR_MIDI_MIN <= n["pitch"] <= GUITAR_MIDI_MAX
    ]
    kept.sort(key=lambda n: (n["start"], n["pitch"]))

    dedup_window_s = dedup_window_ms / 1000.0
    deduped: list[dict] = []
    for n in kept:
        match_idx = None
        for i, existing in enumerate(deduped):
            if (existing["pitch"] == n["pitch"]
                    and abs(existing["start"] - n["start"]) < dedup_window_s):
                match_idx = i
                break
        if match_idx is None:
            deduped.append(n)
        elif n["duration_s"] > deduped[match_idx]["duration_s"]:
            deduped[match_idx] = n
    return deduped


def build_score(notes: list[dict], bpm: float, title: str, tuning_notes: list[str]):
    from music21 import (
        clef, duration, expressions, instrument, metadata, meter, note, stream, tempo,
    )

    part = stream.Part()
    part.insert(0, instrument.AcousticGuitar())
    part.insert(0, clef.TabClef())
    part.insert(0, tempo.MetronomeMark(number=bpm))
    part.insert(0, meter.TimeSignature("4/4"))
    part.insert(0, expressions.TextExpression(f"Tuning: {' '.join(tuning_notes)}"))

    beats_per_second = bpm / 60.0
    for n in notes:
        offset_ql = n["start"] * beats_per_second
        dur_ql = max(n["duration_s"] * beats_per_second, 0.0625)
        m21_note = note.Note(n["pitch"])
        m21_note.duration = duration.Duration(quarterLength=dur_ql)
        part.insert(offset_ql, m21_note)

    part.quantize([4], processOffsets=True, processDurations=True, inPlace=True)
    part.makeMeasures(inPlace=True)
    part.makeRests(fillGaps=True, inPlace=True)

    score = stream.Score()
    score.metadata = metadata.Metadata(title=title, composer="")
    score.insert(0, part)
    return score


def inject_staff_tuning(xml_path: Path, pitches: list[str]) -> None:
    """Insert <staff-details> with <staff-tuning> after the first <clef>.

    music21 does not emit MusicXML staff-tuning even when stringPitches is set,
    so MuseScore otherwise assumes standard tuning when computing fret numbers.
    Line 1 in MusicXML = the bottom line of the tab staff = the lowest string.
    """
    text = xml_path.read_text(encoding="utf-8")
    lines = [
        '        <staff-details>',
        '          <staff-lines>6</staff-lines>',
    ]
    for line_num, pitch in enumerate(pitches, start=1):
        step = pitch[0]
        accidental = pitch[1] if pitch[1] in "#b" else ""
        octave = pitch[1 + len(accidental):]
        lines.append(f'          <staff-tuning line="{line_num}">')
        lines.append(f'            <tuning-step>{step}</tuning-step>')
        if accidental:
            alter = "1" if accidental == "#" else "-1"
            lines.append(f'            <tuning-alter>{alter}</tuning-alter>')
        lines.append(f'            <tuning-octave>{octave}</tuning-octave>')
        lines.append('          </staff-tuning>')
    lines.append('        </staff-details>')
    block = "\n".join(lines)

    marker = "</clef>"
    idx = text.find(marker)
    if idx < 0:
        sys.exit("Could not find <clef> in MusicXML to inject staff-tuning")
    end = idx + len(marker)
    xml_path.write_text(text[:end] + "\n" + block + text[end:], encoding="utf-8")


def render_with_musescore(musescore: Path, musicxml: Path, output: Path) -> None:
    if not musescore.is_file():
        sys.exit(f"MuseScore not found at: {musescore}")
    cmd = [str(musescore), "-o", str(output), str(musicxml)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"MuseScore failed rendering {output.name}:\n{result.stderr}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to input .mid file")
    parser.add_argument("--bpm", type=float, default=120.0,
                        help="Assumed tempo for quantization (default 120)")
    parser.add_argument("--confidence", type=float, default=0.4,
                        help="Drop notes with Basic Pitch confidence below this (default 0.4)")
    parser.add_argument("--min-note-ms", type=int, default=58,
                        help="Drop notes shorter than this many ms")
    parser.add_argument("--dedup-window-ms", type=int, default=50,
                        help="Treat same-pitch notes within this window as duplicates")
    parser.add_argument("--tuning", type=str, default=STANDARD_TUNING,
                        help="6-string tuning low-to-high, e.g. EADGBE or DADF#BD (default EADGBE)")
    parser.add_argument("--musescore-path", type=Path, default=DEFAULT_MUSESCORE,
                        help="Path to MuseScore4.exe")
    args = parser.parse_args()

    src = args.input.resolve()
    if not src.is_file():
        sys.exit(f"Not a file: {src}")
    if src.suffix.lower() not in ALLOWED_SUFFIXES:
        sys.exit(f"Expected .mid, got {src.suffix}: {src}")

    csv_src = src.with_suffix(".csv")
    if not csv_src.is_file():
        sys.exit(f"Missing sibling CSV (needed for confidence filtering): {csv_src}")

    TABS_OUT_DIR.mkdir(parents=True, exist_ok=True)
    target_xml = TABS_OUT_DIR / f"{src.stem}.musicxml"
    target_pdf = TABS_OUT_DIR / f"{src.stem}.pdf"
    target_mscz = TABS_OUT_DIR / f"{src.stem}.mscz"
    if target_xml.exists() and target_pdf.exists() and target_mscz.exists():
        print(f"Skipping — already exists: {target_pdf} and {target_mscz}")
        return

    raw = load_csv_notes(csv_src)
    cleaned = clean_notes(raw, args.confidence, args.min_note_ms, args.dedup_window_ms)
    print(f"Cleaned: {len(raw)} -> {len(cleaned)} notes")

    tuning_notes = parse_tuning(args.tuning)
    string_pitches = tuning_with_octaves(tuning_notes)
    score = build_score(cleaned, args.bpm, title=src.stem, tuning_notes=tuning_notes)
    score.write("musicxml", fp=str(target_xml))
    inject_staff_tuning(target_xml, string_pitches)
    print(f"Saved MusicXML to: {target_xml}")

    render_with_musescore(args.musescore_path, target_xml, target_pdf)
    print(f"Saved PDF to: {target_pdf}")
    render_with_musescore(args.musescore_path, target_xml, target_mscz)
    print(f"Saved MuseScore file to: {target_mscz}")


if __name__ == "__main__":
    main()
