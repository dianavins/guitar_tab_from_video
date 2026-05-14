"""Isolate guitar audio from an mp4 or wav using Demucs htdemucs_6s."""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
GUITAR_OUT_DIR = SCRIPT_DIR / "guitar_audios"
MODEL = "htdemucs_6s"
ALLOWED_SUFFIXES = {".mp4", ".wav"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Isolate guitar from an mp4 or wav with Demucs.")
    parser.add_argument("input", type=Path, help="Path to input .mp4 or .wav file")
    args = parser.parse_args()

    src = args.input.resolve()
    if not src.is_file():
        sys.exit(f"Not a file: {src}")
    if src.suffix.lower() not in ALLOWED_SUFFIXES:
        sys.exit(f"Expected .mp4 or .wav, got {src.suffix}: {src}")

    GUITAR_OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = GUITAR_OUT_DIR / f"{src.stem}.wav"
    if target.exists():
        print(f"Skipping — already exists: {target}")
        return

    with tempfile.TemporaryDirectory(prefix="demucs_") as tmp:
        tmp_dir = Path(tmp)
        cmd = ["demucs", "-n", MODEL, "--out", str(tmp_dir), str(src)]
        print(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)

        guitar_stem = tmp_dir / MODEL / src.stem / "guitar.wav"
        if not guitar_stem.is_file():
            sys.exit(f"Demucs did not produce expected output: {guitar_stem}")

        shutil.move(str(guitar_stem), target)
        print(f"Saved guitar stem to: {target}")


if __name__ == "__main__":
    main()
