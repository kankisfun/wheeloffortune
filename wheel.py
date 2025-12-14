import copy
import math
import random
import re
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

        top_bar = tk.Frame(self.root)
        top_bar.pack(fill="x", padx=10, pady=(10, 0))

        self.bpm_label = tk.Label(top_bar, font=("Arial", 12, "bold"))
        self.bpm_label.pack(side="right")

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

        self.restart_button = tk.Button(
            bottom_bar,
            text="Restart",
            command=self.restart_game,
        )
        self.restart_button.pack(side="right", padx=10)

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
        self.original_items = list(self.items)
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

        self.mercy_configs: list[dict[str, int | str]] = []
        self.mercy_jobs: list[str] = []
        self.mercy_started = False

        self.base_names: list[str] = []
        self.item_modules: list[dict[str, int]] = []

        self.initial_bps = 60
        self.bps = self.initial_bps
        self.special_targets_by_name: dict[str, int] = {}
        self.special_counts_by_name: dict[str, int] = {}
        self.game_over = False
        self.has_invalid_config = False

        self.parse_items_and_modules()
        if self.has_invalid_config:
            self.root.destroy()
            return

        self.update_bpm_display()

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

    def parse_items_and_modules(self) -> None:
        self.base_names.clear()
        self.item_modules.clear()
        self.mercy_configs.clear()
        self.special_targets_by_name.clear()
        self.special_counts_by_name.clear()
        seen_modules: dict[str, dict[str, int | bool]] = {}

        parsed_items: list[str] = []

        parsed_entries: list[tuple[str, dict[str, int | bool], bool]] = []
        non_missing_count = 0
        for raw_item in self.items:
            base_name, module_texts = self.extract_base_and_modules(raw_item)
            modules = self.interpret_modules(module_texts)
            if base_name in seen_modules and seen_modules[base_name] != modules:
                messagebox.showerror(
                    "Error",
                    (
                        "Conflicting modules found for choice "
                        f"'{base_name}'. All occurrences must use the same modules."
                    ),
                )
                self.has_invalid_config = True
                return

            seen_modules[base_name] = copy.deepcopy(modules)
            is_missing = bool(modules.get("missing"))
            parsed_entries.append((base_name, modules, is_missing))
            if not is_missing:
                non_missing_count += 1

        self.colors = self.generate_colors(non_missing_count)

        color_idx = 0
        for base_name, modules, is_missing in parsed_entries:
            color = self.colors[color_idx] if not is_missing else None

            if not is_missing:
                current_index = len(parsed_items)
                self.register_modules(current_index, base_name, modules, color)
                self.base_names.append(base_name)
                self.item_modules.append(modules)
                parsed_items.append(self.format_item_label(current_index))
                color_idx += 1
            else:
                self.register_modules(None, base_name, modules, color)

        self.items = parsed_items

    @staticmethod
    def extract_base_and_modules(item: str) -> tuple[str, list[str]]:
        module_matches = re.findall(r"\([^)]*\)", item)
        base_name = re.sub(r"\([^)]*\)", "", item).strip()
        module_texts = [match.strip("() ") for match in module_matches]
        return base_name or item.strip(), module_texts

    def interpret_modules(self, module_texts: list[str]) -> dict[str, int | bool]:
        modules: dict[str, int | bool] = {}
        for module_text in module_texts:
            lower = module_text.lower()

            mercy_match = re.fullmatch(r"mercy\s+(\d+)\s+(\d+)", lower)
            if mercy_match:
                modules["mercy_initial"] = int(mercy_match.group(1))
                modules["mercy_repeat"] = int(mercy_match.group(2))
                continue

            target_match = re.fullmatch(r"1\s*/\s*(\d+)", lower)
            if target_match:
                modules["special_target"] = int(target_match.group(1))
                continue

            bpm_match = re.fullmatch(r"\+\s*(\d+)", lower)
            if bpm_match:
                modules["bpm_boost"] = int(bpm_match.group(1))
                continue

            if lower == "fragile":
                modules["fragile"] = True
                continue

            if lower == "missing":
                modules["missing"] = True
                continue

        return modules

    def register_modules(
        self,
        idx: int | None,
        base_name: str,
        modules: dict[str, int | bool],
        color: str | None,
    ) -> None:
        if "mercy_initial" in modules and "mercy_repeat" in modules:
            self.mercy_configs.append(
                {
                    "index": idx,
                    "base_name": base_name,
                    "initial_delay": modules["mercy_initial"],
                    "repeat_delay": modules["mercy_repeat"],
                    "color": color,
                    "modules": copy.deepcopy(modules),
                }
            )

        if "special_target" in modules:
            target = modules["special_target"]
            if base_name not in self.special_targets_by_name:
                self.special_targets_by_name[base_name] = target
                self.special_counts_by_name[base_name] = 0

    def format_item_label(self, idx: int) -> str:
        label = self.base_names[idx]
        modules = self.item_modules[idx]
        if "special_target" in modules:
            target = modules["special_target"]
            base_name = self.base_names[idx]
            current = self.special_counts_by_name.get(base_name, 0)
            label = f"{label} ({current}/{target})"
        return label

    def add_item_with_modules(
        self,
        base_name: str,
        modules: dict[str, int],
        color: str | None = None,
        register_mercy: bool = False,
    ) -> None:
        if color is None:
            palette = self.generate_colors(len(self.items) + 1)
            color = palette[len(self.items)]

        self.base_names.append(base_name)
        self.item_modules.append(copy.deepcopy(modules))
        self.colors.append(str(color))

        new_index = len(self.items)
        if "special_target" in modules:
            target = modules["special_target"]
            if base_name not in self.special_targets_by_name:
                self.special_targets_by_name[base_name] = target
                self.special_counts_by_name[base_name] = 0

        self.items.append(self.format_item_label(new_index))

        if (
            register_mercy
            and "mercy_initial" in modules
            and "mercy_repeat" in modules
        ):
            self.mercy_configs.append(
                {
                    "index": new_index,
                    "base_name": base_name,
                    "initial_delay": modules["mercy_initial"],
                    "repeat_delay": modules["mercy_repeat"],
                    "color": color,
                    "modules": copy.deepcopy(modules),
                }
            )

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

        if self.break_active:
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
        if (
            self.auto_spin_var.get()
            and not self.break_active
            and not self.game_over
            and not self.spinning
        ):
            self.auto_spin_job = self.root.after(300, self.auto_spin_tick)

    def schedule_heartbeat(self) -> None:
        if self.heartbeat_job is not None:
            return

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

    def cancel_mercy_jobs(self) -> None:
        for job in self.mercy_jobs:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self.mercy_jobs.clear()

    def start_mercy_timers_if_needed(self) -> None:
        if self.mercy_started:
            return

        self.mercy_started = True
        self.schedule_mercy_items()

    def schedule_mercy_items(self) -> None:
        self.cancel_mercy_jobs()
        for config in self.mercy_configs:
            delay = config["initial_delay"] if config["initial_delay"] > 0 else config["repeat_delay"]
            if delay <= 0:
                continue
            job = self.root.after(
                int(delay * 1000),
                lambda cfg=config: self.apply_mercy_effect(cfg),
            )
            self.mercy_jobs.append(job)

    def apply_mercy_effect(self, config: dict[str, int | str]) -> None:
        repeat_delay = int(config["repeat_delay"])
        self.duplicate_mercy_item(config)

        if repeat_delay > 0:
            job = self.root.after(
                int(repeat_delay * 1000),
                lambda cfg=config: self.apply_mercy_effect(cfg),
            )
            self.mercy_jobs.append(job)

    def auto_spin_tick(self) -> None:
        self.auto_spin_job = None
        if not self.auto_spin_var.get():
            return
        if self.game_over:
            return
        if self.break_active:
            return
        if not self.spinning:
            self.start_spin()

    def heartbeat_tick(self) -> None:
        self.heartbeat_job = None
        self.play_heartbeat_sound()
        self.schedule_heartbeat()

    def start_spin(self, event: tk.Event | None = None) -> None:
        if self.game_over:
            self.status.config(text="Game over. Press Restart to play again.")
            return
        if self.break_active:
            return
        if self.spinning:
            return

        self.start_mercy_timers_if_needed()
        self.spinning = True
        self.spin_start = time.perf_counter()
        self.last_update = self.spin_start
        self.initial_speed = random.uniform(4.7, 5.3) * 360
        self.deceleration = self.initial_speed / 3.0
        self.jitter = random.uniform(0.01, 0.05)
        self.last_pointer_index = self.pointer_index()
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
        base_name = self.base_names[index]
        modules = self.item_modules[index]
        lowered_winner = base_name.strip().lower()
        multiplier_match = re.fullmatch(r"(\d+)x", lowered_winner)
        multiplier_value = int(multiplier_match.group(1)) if multiplier_match else None
        is_relax = lowered_winner == "relax"
        applied_multiplier = self.pending_multiplier

        if multiplier_value is not None:
            self.pending_multiplier *= multiplier_value
            self.status.config(text=f"Result: {winner}. Press space to spin again.")
            self.schedule_auto_spin()
            return

        display_winner = winner
        if applied_multiplier > 1:
            display_winner = f"{applied_multiplier}x {winner}"

        module_messages = []
        if "bpm_boost" in modules:
            boost = modules["bpm_boost"] * applied_multiplier
            self.bps += boost
            self.update_bpm_display()
            self.schedule_heartbeat()
            module_messages.append(f"BPM increased by {boost} to {self.bps}.")

        ended, message = self.handle_special_result(
            index, display_winner, applied_multiplier
        )
        self.pending_multiplier = 1

        if "fragile" in modules and not ended:
            message = self.handle_fragile_result(index, display_winner)
            ended = self.game_over

        if module_messages:
            message = f"{message} {' '.join(module_messages)}".strip()

        if ended:
            return

        if is_relax:
            duration = 5 * applied_multiplier
            self.start_relax_timer(duration)
            return

        self.status.config(text=message)
        self.schedule_auto_spin()

    def handle_special_result(
        self, index: int, display_winner: str, applied_multiplier: int = 1
    ) -> tuple[bool, str]:
        base_name = self.base_names[index]
        if base_name not in self.special_targets_by_name:
            return False, f"Result: {display_winner}. Press space to spin again."

        self.special_counts_by_name[base_name] += max(1, applied_multiplier)
        target = self.special_targets_by_name[base_name]
        name = base_name
        current = self.special_counts_by_name[base_name]
        display_current = min(current, target)
        if current >= target:
            message = f"{name} was chosen {target} times"
            self.end_game(message)
            return True, message

        return (
            False,
            f"Result: {display_winner}. {name} chosen {display_current}/{target}. Press space to spin again.",
        )

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
            else:
                self.status.config(text="Relax over. Press space to spin.")
            return

        seconds_left = max(1, math.ceil(remaining))
        self.status.config(text=f"Relax: {seconds_left} seconds remaining.")
        self.break_timer_job = self.root.after(200, self.update_relax_timer)

    def end_game(self, message: str) -> None:
        self.game_over = True
        self.auto_spin_var.set(False)
        self.cancel_auto_spin()
        self.cancel_break_timer()
        self.break_active = False
        self.status.config(text=message)

    def cancel_break_timer(self) -> None:
        if self.break_timer_job is not None:
            self.root.after_cancel(self.break_timer_job)
            self.break_timer_job = None

    def update_special_label(self, index: int) -> None:
        self.items[index] = self.format_item_label(index)
        self.draw_wheel()

    def handle_fragile_result(self, index: int, display_winner: str) -> str:
        self.remove_item(index)
        if not self.items:
            end_message = f"{display_winner} was destroyed. No items remain."
            self.end_game(end_message)
            return end_message

        return (
            f"{display_winner} was destroyed after being chosen. Press space to spin again."
        )

    def remove_item(self, index: int) -> None:
        if index < 0 or index >= len(self.items):
            return

        del self.items[index]
        del self.base_names[index]
        del self.item_modules[index]
        del self.colors[index]
        self.draw_wheel()

    def duplicate_mercy_item(self, config: dict[str, int | str]) -> None:
        base_name = str(config["base_name"])
        modules = config.get("modules", {})
        color = config.get("color")
        self.add_item_with_modules(base_name, dict(modules), str(color) if color else None)
        self.draw_wheel()

    def restart_game(self) -> None:
        self.cancel_auto_spin()
        self.cancel_heartbeat()
        self.cancel_break_timer()
        self.cancel_mercy_jobs()
        self.items = list(self.original_items)
        self.colors = self.generate_colors(len(self.items))
        self.parse_items_and_modules()
        self.mercy_started = False
        self.game_over = False
        self.spinning = False
        self.pending_multiplier = 1
        self.bps = self.initial_bps
        self.angle_offset = 0.0
        self.break_active = False
        self.break_end_time = 0.0
        self.auto_spin_var.set(False)
        self.last_pointer_index = self.pointer_index()
        self.draw_wheel()
        self.schedule_heartbeat()
        self.update_bpm_display()
        self.status.config(text="Press space to spin")

    def run(self) -> None:
        if self.items:
            self.root.mainloop()

    def bpm_text(self) -> str:
        return f"BPM: {self.bps}"

    def update_bpm_display(self) -> None:
        self.bpm_label.config(text=self.bpm_text())


def main() -> None:
    root = tk.Tk()
    app = WheelOfFortune(root)
    app.run()


if __name__ == "__main__":
    main()
