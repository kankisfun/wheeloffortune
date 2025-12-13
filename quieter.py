import wave
import struct
from pathlib import Path

# =========================
# CONFIG
# =========================
INPUT_FILE = "click.wav"
OUTPUT_FILE = "click_quiet.wav"
VOLUME_FACTOR = 0.35   # 35% volume (0.5 = 50%, 0.2 = 20%)

# =========================
# LOAD WAV
# =========================
input_path = Path(INPUT_FILE)
output_path = Path(OUTPUT_FILE)

with wave.open(str(input_path), "rb") as wf:
    params = wf.getparams()
    frames = wf.readframes(wf.getnframes())

# =========================
# PROCESS AUDIO
# =========================
sample_width = params.sampwidth
num_samples = len(frames) // sample_width

if sample_width != 2:
    raise ValueError("This script supports only 16-bit WAV files")

samples = struct.unpack("<" + "h" * num_samples, frames)

quieter_samples = [
    int(sample * VOLUME_FACTOR)
    for sample in samples
]

quieter_frames = struct.pack(
    "<" + "h" * len(quieter_samples),
    *quieter_samples
)

# =========================
# SAVE WAV
# =========================
with wave.open(str(output_path), "wb") as wf:
    wf.setparams(params)
    wf.writeframes(quieter_frames)

print(f"Saved quieter file as: {OUTPUT_FILE}")
