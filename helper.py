import wave
import struct
import tkinter as tk
from tkinter import filedialog
from pathlib import Path


SPEEDS = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]


def speed_up_wav(input_path: Path, speed: float) -> None:
    with wave.open(str(input_path), "rb") as wf:
        params = wf.getparams()
        frames = wf.readframes(wf.getnframes())

    sample_width = params.sampwidth
    channels = params.nchannels

    fmt = "<" + "h" * (len(frames) // 2)
    samples = struct.unpack(fmt, frames)

    new_length = int(len(samples) / speed)
    new_samples = [
        samples[int(i * speed)]
        for i in range(new_length)
    ]

    new_frames = struct.pack("<" + "h" * len(new_samples), *new_samples)

    output_path = input_path.with_stem(f"{input_path.stem}_{speed}x")

    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(params.framerate)
        wf.writeframes(new_frames)

    print(f"Created: {output_path.name}")



def main():
    root = tk.Tk()
    root.withdraw()

    file_path = filedialog.askopenfilename(
        title="Select a WAV file",
        filetypes=[("WAV files", "*.wav")],
    )

    if not file_path:
        print("No file selected.")
        return

    input_path = Path(file_path)

    for speed in SPEEDS:
        speed_up_wav(input_path, speed)

    print("Done.")


if __name__ == "__main__":
    main()
