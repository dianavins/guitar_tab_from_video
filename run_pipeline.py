"""Run the full pipeline on a video: separate guitar -> transcribe -> tab."""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEP1_SCRIPT = ROOT / "1_audio_seperation" / "separate_guitar.py"
STEP2_SCRIPT = ROOT / "2_guitar_transcription" / "transcribe.py"
STEP3_SCRIPT = ROOT / "3_tab_creation" / "generate_tab.py"
GUITAR_AUDIOS_DIR = ROOT / "1_audio_seperation" / "guitar_audios"
NOTES_DIR = ROOT / "2_guitar_transcription" / "notes"


def run_step(name: str, cmd: list[str]) -> None:
    print(f"\n=== {name} ===", flush=True)
    print(f"$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(f"{name} failed (exit {result.returncode})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Path to input .mp4 video")
    parser.add_argument("--tuning", type=str, default="EADGBE",
                        help="6-string tuning low-to-high, e.g. EADGBE or DADF#BD (default EADGBE)")
    args = parser.parse_args()

    src = args.video.resolve()
    if not src.is_file():
        sys.exit(f"Not a file: {src}")
    if src.suffix.lower() != ".mp4":
        sys.exit(f"Expected .mp4, got {src.suffix}: {src}")
    stem = src.stem
    py = sys.executable

    run_step("1: separate guitar", [py, str(STEP1_SCRIPT), str(src)])
    guitar_wav = GUITAR_AUDIOS_DIR / f"{stem}.wav"
    if not guitar_wav.is_file():
        sys.exit(f"Missing expected step-1 output: {guitar_wav}")

    run_step("2: transcribe", [py, str(STEP2_SCRIPT), str(guitar_wav)])
    mid = NOTES_DIR / f"{stem}.mid"
    if not mid.is_file():
        sys.exit(f"Missing expected step-2 output: {mid}")

    run_step("3: generate tab", [
        py, str(STEP3_SCRIPT), str(mid),
        "--tuning", args.tuning,
    ])


if __name__ == "__main__":
    main()
