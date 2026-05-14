"""Transcribe a guitar .wav into note events using Spotify's Basic Pitch.

Writes a MIDI file and a CSV of note events alongside each other in
3_guitar_transcription/notes/, mirroring the layout of step 2's guitar_audios/.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
NOTES_OUT_DIR = SCRIPT_DIR / "notes"
ALLOWED_SUFFIXES = {".wav"}

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def midi_to_name(pitch_midi: int) -> str:
    return f"{NOTE_NAMES[pitch_midi % 12]}{pitch_midi // 12 - 1}"


def midi_to_hz(pitch_midi: int) -> float:
    return 440.0 * (2.0 ** ((pitch_midi - 69) / 12.0))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to input guitar .wav file")
    parser.add_argument("--onset-threshold", type=float, default=0.5,
                        help="Note-onset confidence threshold (Basic Pitch default 0.5)")
    parser.add_argument("--frame-threshold", type=float, default=0.3,
                        help="Per-frame pitch-activation threshold (Basic Pitch default 0.3)")
    parser.add_argument("--min-note-ms", type=int, default=58,
                        help="Drop notes shorter than this many ms (suppresses spurious blips)")
    parser.add_argument("--min-freq", type=float, default=73.4,
                        help="Hz floor (~D2, one semitone below low-E for drop-D tolerance)")
    parser.add_argument("--max-freq", type=float, default=1320.0,
                        help="Hz ceiling (~E6, top of guitar's range)")
    args = parser.parse_args()

    src = args.input.resolve()
    if not src.is_file():
        sys.exit(f"Not a file: {src}")
    if src.suffix.lower() not in ALLOWED_SUFFIXES:
        sys.exit(f"Expected .wav, got {src.suffix}: {src}")

    NOTES_OUT_DIR.mkdir(parents=True, exist_ok=True)
    target_mid = NOTES_OUT_DIR / f"{src.stem}.mid"
    target_csv = NOTES_OUT_DIR / f"{src.stem}.csv"
    if target_mid.exists() and target_csv.exists():
        print(f"Skipping — already exists: {target_mid} and {target_csv}")
        return

    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict

    print(f"Transcribing: {src}")
    _model_output, midi_data, note_events = predict(
        str(src),
        model_or_model_path=ICASSP_2022_MODEL_PATH,
        onset_threshold=args.onset_threshold,
        frame_threshold=args.frame_threshold,
        minimum_note_length=args.min_note_ms,
        minimum_frequency=args.min_freq,
        maximum_frequency=args.max_freq,
        multiple_pitch_bends=False,
        melodia_trick=True,
    )

    midi_data.write(str(target_mid))
    print(f"Saved MIDI to: {target_mid}")

    with target_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "start_s", "end_s", "duration_s",
            "pitch_midi", "pitch_name", "pitch_hz",
            "velocity", "confidence",
        ])
        for event in note_events:
            start_s, end_s, pitch_midi, amplitude, *_ = event
            writer.writerow([
                f"{start_s:.4f}",
                f"{end_s:.4f}",
                f"{end_s - start_s:.4f}",
                pitch_midi,
                midi_to_name(int(pitch_midi)),
                f"{midi_to_hz(int(pitch_midi)):.3f}",
                max(1, min(127, int(round(amplitude * 127)))),
                f"{amplitude:.4f}",
            ])
    print(f"Saved {len(note_events)} note events to: {target_csv}")


if __name__ == "__main__":
    main()
