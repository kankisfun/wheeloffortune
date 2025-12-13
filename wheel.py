import math
import random
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

try:
    import simpleaudio  # type: ignore
except Exception:  # pragma: no cover - fallback for environments without simpleaudio
    simpleaudio = None  # type: ignore

try:
    import winsound  # type: ignore
except Exception:  # pragma: no cover - fallback for non-Windows platforms
    winsound = None  # type: ignore


class WheelOfFortune:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Wheel of Fortune")

        self.canvas_size = 700
        self.radius = 280
        self.center = self.canvas_size // 2

        self.canvas = tk.Canvas(
            self.root,
            width=self.canvas_size,
            height=self.canvas_size,
            bg="white",
            highlightthickness=0,
        )
        self.canvas.pack()

        self.status = tk.Label(self.root, text="Press space to spin", font=("Arial", 14))
        self.status.pack(pady=10)

        self.auto_spin_var = tk.BooleanVar(value=False)
        self.heartbeat_enabled_var = tk.BooleanVar(value=True)
        bottom_bar = tk.Frame(self.root)
        bottom_bar.pack(fill="x", pady=5)
        self.auto_spin_check = tk.Checkbutton(
            bottom_bar,
            text="Automatic spinning",
            variable=self.auto_spin_var,
            command=self.toggle_auto_spin,
        )
        self.auto_spin_check.pack(side="right", padx=10)

        self.heartbeat_check = tk.Checkbutton(
            bottom_bar,
            text="Heartbeat sound",
            variable=self.heartbeat_enabled_var,
            command=self.toggle_heartbeat,
        )
        self.heartbeat_check.pack(side="left", padx=10)

        self.auto_spin_job: str | None = None
        self.heartbeat_job: str | None = None

        self.items = self.prompt_for_items()
        if not self.items:
            self.root.destroy()
            return

        self.colors = self.generate_colors(len(self.items))
        self.angle_offset = 0.0
        self.spinning = False
        self.pending_multiplier = 1
        self.break_active = False
        self.break_end_time = 0.0
        self.break_timer_job: str | None = None
        self.jitter = 0.02
        self.initial_speed = 0.0
        self.deceleration = 0.0
        self.spin_start = 0.0
        self.last_update = 0.0
        self.last_pointer_index = 0
        self.click_sound = self.load_click_sound()
        self.heartbeat_sound = self.load_heartbeat_sound()

        self.bps = 60
        self.consecutive_multiplier_count = 0

        self.root.bind("<space>", self.start_spin)
        self.draw_wheel()
        self.last_pointer_index = self.pointer_index()
        self.schedule_heartbeat()

    def prompt_for_items(self) -> list[str]:
        path = filedialog.askopenfilename(
            title="Select a text file",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if not path:
            return []

        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            messagebox.showerror("Error", f"Unable to read file: {exc}")
            return []

        items = [line.strip() for line in lines if line.strip()]
        if not items:
            messagebox.showerror("Error", "The selected file is empty.")
            return []
        return items

    @staticmethod
    def generate_colors(count: int) -> list[str]:
        palette = [
            "#FF6B6B",
            "#4ECDC4",
            "#FFD93D",
            "#1A535C",
            "#FF9F1C",
            "#9B5DE5",
            "#00BBF9",
            "#F15BB5",
        ]
        colors = []
        for idx in range(count):
            colors.append(palette[idx % len(palette)])
        return colors

    def load_click_sound(self):  # type: ignore[override]
        path = Path(__file__).with_name("click.wav")
        if not path.exists():
            return None

        if simpleaudio is not None:
            try:
                return simpleaudio.WaveObject.from_wave_file(str(path))
            except Exception:
                return None

        if winsound is not None:
            return path

        return None

    def load_heartbeat_sound(self):  # type: ignore[override]
        path = Path(__file__).with_name("Heartbeat.wav")
        if not path.exists():
            return None

        if simpleaudio is not None:
            try:
                return simpleaudio.WaveObject.from_wave_file(str(path))
            except Exception:
                return None

        if winsound is not None:
            return path

        return None

    def play_click_sound(self) -> None:
        if self.click_sound is None:
            return

        if simpleaudio is not None and hasattr(self.click_sound, "play"):
            try:
                self.click_sound.play()
            except Exception:
                pass
            return

        if winsound is not None:
            try:
                winsound.PlaySound(
                    str(self.click_sound),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
            except Exception:
                pass

    def play_heartbeat_sound(self) -> None:
        if not self.heartbeat_enabled_var.get():
            return

        if self.heartbeat_sound is None:
            return

        if simpleaudio is not None and hasattr(self.heartbeat_sound, "play"):
            try:
                self.heartbeat_sound.play()
            except Exception:
                pass
            return

        if winsound is not None:
            try:
                winsound.PlaySound(
                    str(self.heartbeat_sound),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
            except Exception:
                pass

    def draw_wheel(self) -> None:
        self.canvas.delete("all")
        sector_angle = 360 / len(self.items)
        pointer_angle = 90
        bbox = (
            self.center - self.radius,
            self.center - self.radius,
            self.center + self.radius,
            self.center + self.radius,
        )

        text_items = []
        for index, label in enumerate(self.items):
            start_angle = (
                pointer_angle - sector_angle / 2 + index * sector_angle + self.angle_offset
            )
            self.canvas.create_arc(
                bbox,
                start=start_angle,
                extent=sector_angle,
                fill=self.colors[index],
                outline="white",
                width=2,
            )

            segment_center = start_angle + sector_angle / 2
            angle_rad = math.radians(segment_center)
            text_radius = self.radius * 0.65
            x = self.center + text_radius * math.cos(angle_rad)
            y = self.center - text_radius * math.sin(angle_rad)
            text_items.append((x, y, label, segment_center - 90))

        for x, y, label, angle in text_items:
            self.canvas.create_text(
                x,
                y,
                text=label,
                font=("Arial", 14, "bold"),
                fill="white",
                angle=angle,
            )

        pointer_size = 18
        self.canvas.create_polygon(
            self.center - pointer_size,
            self.center - self.radius - 10,
            self.center + pointer_size,
            self.center - self.radius - 10,
            self.center,
            self.center - self.radius - 40,
            fill="black",
        )

    def pointer_index(self) -> int:
        sector_angle = 360 / len(self.items)
        relative = (sector_angle / 2 - self.angle_offset) % 360
        return int(relative // sector_angle)

    def toggle_auto_spin(self) -> None:
        if self.auto_spin_var.get():
            self.status.config(text="Automatic spinning enabled. Press space to spin manually.")
            self.schedule_auto_spin()
        else:
            self.status.config(text="Press space to spin")
            self.cancel_auto_spin()

    def toggle_heartbeat(self) -> None:
        if self.heartbeat_enabled_var.get():
            self.schedule_heartbeat()
        else:
            self.cancel_heartbeat()

    def schedule_auto_spin(self) -> None:
        self.cancel_auto_spin()
        if self.auto_spin_var.get() and not self.break_active:
            self.auto_spin_job = self.root.after(5000, self.auto_spin_tick)

    def schedule_heartbeat(self) -> None:
        self.cancel_heartbeat()
        if self.heartbeat_enabled_var.get():
            interval_ms = max(1, int(60000 / max(1, self.bps)))
            self.heartbeat_job = self.root.after(interval_ms, self.heartbeat_tick)

    def cancel_auto_spin(self) -> None:
        if self.auto_spin_job is not None:
            self.root.after_cancel(self.auto_spin_job)
            self.auto_spin_job = None

    def cancel_heartbeat(self) -> None:
        if self.heartbeat_job is not None:
            self.root.after_cancel(self.heartbeat_job)
            self.heartbeat_job = None

    def auto_spin_tick(self) -> None:
        self.auto_spin_job = None
        if not self.auto_spin_var.get():
            return
        if not self.spinning:
            self.start_spin()
        self.schedule_auto_spin()

    def heartbeat_tick(self) -> None:
        self.heartbeat_job = None
        self.play_heartbeat_sound()
        self.schedule_heartbeat()

    def start_spin(self, event: tk.Event | None = None) -> None:
        if self.break_active:
            return
        if self.spinning:
            return

        self.spinning = True
        self.spin_start = time.perf_counter()
        self.last_update = self.spin_start
        self.initial_speed = random.uniform(4.7, 5.3) * 360
        self.deceleration = self.initial_speed / 3.0
        self.jitter = random.uniform(0.01, 0.05)
        self.last_pointer_index = self.pointer_index()
        self.status.config(text="Spinning...")
        self.update_spin()

    def current_speed(self, elapsed: float) -> float:
        noise = 1 + random.uniform(-self.jitter, self.jitter)
        if elapsed < 2:
            return self.initial_speed * noise
        if elapsed < 5:
            slow_time = elapsed - 2
            speed = max(self.initial_speed - self.deceleration * slow_time, 0)
            return speed * noise
        return 0.0

    def update_spin(self) -> None:
        if not self.spinning:
            return

        now = time.perf_counter()
        elapsed = now - self.spin_start
        dt = now - self.last_update
        self.last_update = now

        speed = self.current_speed(elapsed)
        self.angle_offset = (self.angle_offset + speed * dt) % 360
        self.draw_wheel()

        pointer_index = self.pointer_index()
        if pointer_index != self.last_pointer_index:
            self.play_click_sound()
            self.last_pointer_index = pointer_index

        if elapsed >= 5:
            self.finish_spin()
            return

        self.root.after(16, self.update_spin)

    def finish_spin(self) -> None:
        self.spinning = False
        index = self.pointer_index()
        self.last_pointer_index = index
        winner = self.items[index]
        lowered_winner = winner.strip().lower()
        is_multiplier = lowered_winner == "2x"
        is_relax = lowered_winner == "relax"
        is_speed_up = lowered_winner == "speed up"

        if is_multiplier:
            self.pending_multiplier *= 2
            self.consecutive_multiplier_count += 1
            self.status.config(text=f"Result: {winner}. Press space to spin again.")
            return

        consecutive_bonus = self.consecutive_multiplier_count
        self.consecutive_multiplier_count = 0

        if is_relax:
            duration = 5 * self.pending_multiplier
            self.start_relax_timer(duration)
            return

        if is_speed_up:
            increment = 5 * (2 ** consecutive_bonus)
            self.bps += increment
            self.pending_multiplier = 1
            self.schedule_heartbeat()
            self.status.config(
                text=(
                    f"Result: Speed Up (+{increment}). BPS is now {self.bps}. "
                    "Press space to spin again."
                )
            )
            return

        display_winner = winner
        if self.pending_multiplier > 1:
            display_winner = f"{self.pending_multiplier}x {winner}"
            self.pending_multiplier = 1

        self.status.config(text=f"Result: {display_winner}. Press space to spin again.")

    def start_relax_timer(self, duration: float) -> None:
        self.break_active = True
        self.break_end_time = time.perf_counter() + duration
        self.cancel_auto_spin()
        self.update_relax_timer()

    def update_relax_timer(self) -> None:
        remaining = self.break_end_time - time.perf_counter()
        if remaining <= 0:
            self.break_active = False
            self.break_timer_job = None
            if self.auto_spin_var.get():
                self.status.config(text="Relax over. Spinning automatically.")
                self.start_spin()
                self.schedule_auto_spin()
            else:
                self.status.config(text="Relax over. Press space to spin.")
            return

        seconds_left = max(1, math.ceil(remaining))
        self.status.config(text=f"Relax: {seconds_left} seconds remaining.")
        self.break_timer_job = self.root.after(200, self.update_relax_timer)

    def run(self) -> None:
        if self.items:
            self.root.mainloop()


def main() -> None:
    root = tk.Tk()
    app = WheelOfFortune(root)
    app.run()


if __name__ == "__main__":
    main()
