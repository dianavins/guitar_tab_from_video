# guitar_tab_from_video

Turn a video of someone playing fingerstyle guitar into a printable guitar
tablature PDF. The pipeline isolates the guitar from any singing, transcribes
the audio to MIDI, then renders a tab in your chosen tuning.

## Setup

1. Install [Conda](https://docs.conda.io/) and [MuseScore 4](https://musescore.org/).
   MuseScore is expected at `C:\Program Files\MuseScore 4\bin\MuseScore4.exe`
   (override with `--musescore-path` if it lives elsewhere).
2. Create the environment:
   ```powershell
   conda env create -f environment.yml
   conda activate guitar-tab
   ```

## Quick start

One command takes a video all the way to a tab PDF:

```powershell
python run_pipeline.py sample_videos\jigsaw_fingerstyle.mp4 --tuning DADF#BD
```

Arguments:
- positional: path to a `.mp4` video.
- `--tuning`: 6-string tuning low-to-high, e.g. `EADGBE`, `DADF#BD`, `CGCFG#D`.
  Letters are case-insensitive; `#` and `b` are accepted for accidentals.
  Default `EADGBE`.

The driver invokes the three step scripts below in order. Each step has a
skip-if-exists check on its output, so re-running on the same video is a no-op
and re-running with new flags only reruns the affected step (delete the
relevant output to force a regeneration).

Outputs land in:
- `1_audio_seperation/guitar_audios/<stem>.wav`
- `2_guitar_transcription/notes/<stem>.{mid,csv}`
- `3_tab_creation/tabs/<stem>.{musicxml,pdf,mscz}`

The final `.pdf` is the printable tab; the `.mscz` opens in MuseScore for
manual cleanup of fingerings if needed.

## Pipeline

### Step 1 — isolate the guitar
`1_audio_seperation/separate_guitar.py <input.mp4|input.wav>`

Runs Facebook's [Demucs](https://github.com/facebookresearch/demucs) with the
`htdemucs_6s` model, which separates a mix into six stems (drums, bass, other,
vocals, piano, guitar). Only the guitar stem is kept. Singing, percussion, and
other instruments are discarded so step 2 has a cleaner signal to transcribe.

### Step 2 — transcribe audio to MIDI
`2_guitar_transcription/transcribe.py <guitar.wav>`

Runs Spotify's [Basic Pitch](https://github.com/spotify/basic-pitch) (ICASSP
2022 model) to detect note onsets and pitches. Outputs both a standard `.mid`
file and a `.csv` with one row per note event including the model's
per-note confidence (Basic Pitch is noisy on dense polyphony — confidence is
what step 3 uses to filter out spurious detections).

Useful flags: `--onset-threshold`, `--frame-threshold`, `--min-note-ms`,
`--min-freq`, `--max-freq`. Defaults are tuned for fingerstyle guitar.

### Step 3 — render the tab
`3_tab_creation/generate_tab.py <notes.mid> --tuning <T>`

Reads the MIDI and its sibling CSV, then:
1. **Cleans up** the note stream — drops notes below a confidence threshold,
   drops notes shorter than a minimum duration, dedupes near-duplicate
   same-pitch notes, and clamps to guitar range (E2–E6).
2. **Quantizes** timing to a 16th-note grid at the supplied BPM.
3. **Builds a [music21](https://www.music21.org/) score** with a TAB clef, the
   `AcousticGuitar` instrument, and the requested tuning.
4. **Writes MusicXML** with `<staff-tuning>` injected per string so MuseScore
   computes fret numbers against the actual tuning (not standard EADGBE).
5. **Invokes the MuseScore 4 CLI** to render `tabs/<stem>.pdf` and an editable
   `tabs/<stem>.mscz`.

Useful flags: `--tuning`, `--confidence` (drop threshold, default 0.4),
`--bpm` (default 120), `--min-note-ms`, `--dedup-window-ms`.

## Running steps individually

Each step script accepts a single input file and writes to a fixed sibling
directory, so they compose cleanly outside the driver:

```powershell
# just resaw audio
python 1_audio_seperation\separate_guitar.py path\to\song.mp4

# just retranscribe
python 2_guitar_transcription\transcribe.py 1_audio_seperation\guitar_audios\song.wav

# just re-render the tab with different settings
python 3_tab_creation\generate_tab.py 2_guitar_transcription\notes\song.mid `
    --tuning DADF#BD --confidence 0.3 --bpm 100
```
