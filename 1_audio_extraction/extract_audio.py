"""Extract audio from an mp4 video using ffmpeg.

Output is 44.1 kHz stereo WAV, the format expected by downstream
source-separation models like Demucs.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import ffmpeg

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "audios"


def extract_audio(
    video_path: Path,
    output_path: Path,
    sample_rate: int = 44100,
    channels: int = 2,
    overwrite: bool = False,
) -> Path:
    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {output_path} (use --overwrite to replace)"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    stream = ffmpeg.input(str(video_path))
    stream = ffmpeg.output(
        stream,
        str(output_path),
        acodec="pcm_s16le",
        ac=channels,
        ar=sample_rate,
        vn=None,
    )
    ffmpeg.run(stream, overwrite_output=overwrite, quiet=True)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Path to input mp4 video")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=(
            "Output WAV path (default: "
            "1_audio_extraction/audios/<video stem>.wav)"
        ),
    )
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--channels", type=int, default=2, choices=[1, 2])
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    output = args.output or DEFAULT_OUTPUT_DIR / f"{args.video.stem}.wav"
    result = extract_audio(
        args.video,
        output,
        sample_rate=args.sample_rate,
        channels=args.channels,
        overwrite=args.overwrite,
    )
    print(f"Wrote {result}")


if __name__ == "__main__":
    main()
