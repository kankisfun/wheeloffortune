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

        self.timer_label = tk.Label(top_bar, font=("Arial", 12, "bold"))
        self.timer_label.config(text="Timer: 00:00")
        self.timer_label.pack(side="left")

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

        self.status = tk.Label(self.root, text="Press Start to spin", font=("Arial", 14))
        self.status.pack(pady=10)

        self.auto_spin_var = tk.BooleanVar(value=True)
        self.heartbeat_enabled_var = tk.BooleanVar(value=True)
        bottom_bar = tk.Frame(self.root)
        bottom_bar.pack(fill="x", pady=5)
        self.auto_spin_label = tk.Label(bottom_bar, text="Automatic spinning enabled")
        self.auto_spin_label.pack(side="right", padx=10)

        self.restart_button = tk.Button(
            bottom_bar,
            text="Restart",
            command=self.restart_game,
        )
        self.restart_button.pack(side="right", padx=10)

        self.start_button = tk.Button(
            bottom_bar,
            text="Start spinning",
            command=self.start_spin,
        )
        self.start_button.pack(side="left", padx=10)

        self.heartbeat_check = tk.Checkbutton(
            bottom_bar,
            text="Heartbeat sound",
            variable=self.heartbeat_enabled_var,
            command=self.toggle_heartbeat,
        )
        self.heartbeat_check.pack(side="left", padx=10)

        self.auto_spin_job: str | None = None
        self.heartbeat_job: str | None = None

        self.config_dir = Path(__file__).parent
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
        self.timer_job: str | None = None
        self.jitter = 0.02
        self.initial_speed = 0.0
        self.deceleration = 0.0
        self.spin_start = 0.0
        self.first_spin_time: float | None = None
        self.last_update = 0.0
        self.last_pointer_index = 0
        self.sound_cache: dict[str, object | None] = {}
        self.click_sound = self.load_click_sound()
        self.heartbeat_sound = self.load_heartbeat_sound()

        self.mercy_configs: list[dict[str, int | str]] = []
        self.mercy_jobs: list[str] = []
        self.mercy_started = False

        self.cooldown_jobs: list[str] = []

        self.base_names: list[str] = []
        self.item_modules: list[dict[str, int | bool | float | str]] = []
        self.hidden_items: list[dict[str, str | dict[str, int | bool | float | str] | None]] = []

        self.initial_bps = 60
        self.bps = self.initial_bps
        self.special_targets_by_name: dict[str, int] = {}
        self.special_counts_by_name: dict[str, int] = {}
        self.max_targets_by_name: dict[str, int] = {}
        self.max_counts_by_name: dict[str, int] = {}
        self.max_blocked_names: set[str] = set()
        self.game_over = False
        self.has_invalid_config = False

        self.parse_items_and_modules()
        if self.has_invalid_config:
            self.root.destroy()
            return

        self.update_bpm_display()

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

        self.config_dir = Path(path).parent

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
        self.max_targets_by_name.clear()
        self.max_counts_by_name.clear()
        self.max_blocked_names.clear()
        seen_modules: dict[str, dict[str, int | bool | float | str]] = {}

        parsed_items: list[str] = []

        parsed_entries: list[tuple[str, dict[str, int | bool | float | str], bool]] = []
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

        self.hidden_items.clear()

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
        self.apply_bps_conditions()

    @staticmethod
    def extract_base_and_modules(item: str) -> tuple[str, list[str]]:
        module_matches = re.findall(r"\([^)]*\)", item)
        base_name = re.sub(r"\([^)]*\)", "", item).strip()
        module_texts = [match.strip("() ") for match in module_matches]
        return base_name or item.strip(), module_texts

    def interpret_modules(self, module_texts: list[str]) -> dict[str, int | bool | float | str]:
        modules: dict[str, int | bool | float | str] = {}
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

            cooldown_match = re.fullmatch(r"cooldown\s+(\d+)", lower)
            if cooldown_match:
                modules["cooldown"] = int(cooldown_match.group(1))
                continue

            max_match = re.fullmatch(r"max\s+(\d+)", lower)
            if max_match:
                modules["max"] = int(max_match.group(1))
                continue

            bpm_match = re.fullmatch(r"\+\s*(-?\d+)", lower)
            if bpm_match:
                modules["bpm_boost"] = int(bpm_match.group(1))
                continue

            multiplier_match = re.fullmatch(r"\*\s*([-+]?\d+(?:\.\d+)?)", lower)
            if multiplier_match:
                modules["bpm_multiplier"] = float(multiplier_match.group(1))
                continue

            greater_than_match = re.fullmatch(r">\s*(-?\d+)", lower)
            if greater_than_match:
                modules["bps_min"] = int(greater_than_match.group(1))
                continue

            less_than_match = re.fullmatch(r"<\s*(-?\d+)", lower)
            if less_than_match:
                modules["bps_max"] = int(less_than_match.group(1))
                continue

            timer_greater_match = re.fullmatch(r">\s*(\d+)s", lower)
            if timer_greater_match:
                modules["timer_min_seconds"] = int(timer_greater_match.group(1))
                continue

            timer_less_match = re.fullmatch(r"<\s*(\d+)s", lower)
            if timer_less_match:
                modules["timer_max_seconds"] = int(timer_less_match.group(1))
                continue

            if lower.endswith(".wav"):
                modules["sound_effect"] = module_text.strip()
                continue

            if lower == "fragile":
                modules["fragile"] = True
                continue

            if lower == "missing":
                modules["missing"] = True
                continue

            if lower == "reset":
                modules["reset_timer"] = True
                continue

        return modules

    def is_item_allowed_by_bps(self, modules: dict[str, int | bool | float | str]) -> bool:
        min_bps = modules.get("bps_min")
        max_bps = modules.get("bps_max")

        if isinstance(min_bps, int) and self.bps <= min_bps:
            return False
        if isinstance(max_bps, int) and self.bps >= max_bps:
            return False
        return True

    def current_timer_seconds(self) -> float:
        if self.first_spin_time is None:
            return 0.0
        return time.perf_counter() - self.first_spin_time

    def is_item_allowed_by_timer(
        self, modules: dict[str, int | bool | float | str]
    ) -> bool:
        min_seconds = modules.get("timer_min_seconds")
        max_seconds = modules.get("timer_max_seconds")
        elapsed = self.current_timer_seconds()

        if isinstance(min_seconds, int) and elapsed <= min_seconds:
            return False
        if isinstance(max_seconds, int) and elapsed >= max_seconds:
            return False
        return True

    def is_item_allowed(self, modules: dict[str, int | bool | float | str]) -> bool:
        return self.is_item_allowed_by_bps(modules) and self.is_item_allowed_by_timer(modules)

    def register_modules(
        self,
        idx: int | None,
        base_name: str,
        modules: dict[str, int | bool | float | str],
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

        if "max" in modules:
            target = int(modules["max"])
            if base_name not in self.max_targets_by_name:
                self.max_targets_by_name[base_name] = target
                self.max_counts_by_name[base_name] = 0

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
        modules: dict[str, int | bool | float | str],
        color: str | None = None,
        register_mercy: bool = False,
    ) -> None:
        modules = copy.deepcopy(modules)
        if base_name in self.max_blocked_names:
            return

        if not self.is_item_allowed(modules):
            self.hidden_items.append(
                {"base_name": base_name, "modules": modules, "color": color}
            )
            return

        if "max" in modules and base_name not in self.max_targets_by_name:
            self.max_targets_by_name[base_name] = int(modules["max"])
            self.max_counts_by_name[base_name] = 0

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

    def apply_bps_conditions(self) -> None:
        removed_any = False
        for idx in range(len(self.item_modules) - 1, -1, -1):
            modules = self.item_modules[idx]
            if self.is_item_allowed(modules):
                continue

            record: dict[str, str | dict[str, int | bool | float | str] | None] = {
                "base_name": self.base_names[idx],
                "modules": copy.deepcopy(modules),
                "color": self.colors[idx],
            }
            self.hidden_items.append(record)
            self.remove_item(idx)
            removed_any = True

        added_any = False
        for record in list(self.hidden_items):
            modules = record.get("modules")
            base_name = record.get("base_name")
            color = record.get("color")
            if not isinstance(modules, dict) or not isinstance(base_name, str):
                continue

            if not self.is_item_allowed(modules):
                continue

            self.add_item_with_modules(
                base_name,
                copy.deepcopy(modules),
                str(color) if color else None,
                register_mercy=False,
            )
            self.hidden_items.remove(record)
            added_any = True

        if removed_any or added_any:
            self.draw_wheel()

    def load_sound_file(self, filename: str):  # type: ignore[override]
        candidate_paths = []
        name = Path(filename)
        if name.is_absolute():
            candidate_paths.append(name)
        else:
            if hasattr(self, "config_dir"):
                candidate_paths.append(Path(self.config_dir) / name)
            candidate_paths.append(Path(__file__).with_name(filename))
            candidate_paths.append(Path.cwd() / name)

        path: Path | None = None
        for candidate in candidate_paths:
            if candidate.exists():
                path = candidate
                break

        if path is None:
            return None

        if simpleaudio is not None:
            try:
                return simpleaudio.WaveObject.from_wave_file(str(path))
            except Exception:
                return None

        if winsound is not None:
            return path

        return None

    def load_click_sound(self):  # type: ignore[override]
        return self.load_sound_file("click.wav")

    def load_heartbeat_sound(self):  # type: ignore[override]
        return self.load_sound_file("Heartbeat.wav")

    def play_sound(self, sound: object | None) -> None:
        if sound is None:
            return

        if simpleaudio is not None and hasattr(sound, "play"):
            try:
                sound.play()
            except Exception:
                pass
            return

        if winsound is not None:
            try:
                winsound.PlaySound(
                    str(sound),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
            except Exception:
                pass

    def play_click_sound(self) -> None:
        self.play_sound(self.click_sound)

    def play_heartbeat_sound(self) -> None:
        if not self.heartbeat_enabled_var.get():
            return

        if self.break_active:
            return

        self.play_sound(self.heartbeat_sound)

    def draw_wheel(self) -> None:
        self.canvas.delete("all")
        if not self.items:
            return
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
        if not self.items:
            return 0
        sector_angle = 360 / len(self.items)
        relative = (sector_angle / 2 - self.angle_offset) % 360
        return int(relative // sector_angle)

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

    def schedule_timer_update(self) -> None:
        if self.timer_job is None:
            self.timer_job = self.root.after(500, self.update_timer_label)

    def update_timer_label(self) -> None:
        if self.first_spin_time is None:
            self.timer_label.config(text="Timer: 00:00")
        else:
            elapsed = time.perf_counter() - self.first_spin_time
            minutes, seconds = divmod(int(elapsed), 60)
            self.timer_label.config(text=f"Timer: {minutes:02d}:{seconds:02d}")
        self.apply_bps_conditions()
        self.timer_job = self.root.after(500, self.update_timer_label)

    def cancel_timer(self) -> None:
        if self.timer_job is not None:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None

    def reset_spin_timer(self) -> None:
        self.first_spin_time = time.perf_counter()
        self.cancel_timer()
        self.update_timer_label()
        self.apply_bps_conditions()

    def cancel_mercy_jobs(self) -> None:
        for job in self.mercy_jobs:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self.mercy_jobs.clear()

    def cancel_cooldown_jobs(self) -> None:
        for job in self.cooldown_jobs:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self.cooldown_jobs.clear()

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
        if not self.items:
            self.status.config(text="No available choices. Adjust BPM or restart.")
            return

        if self.first_spin_time is None:
            self.first_spin_time = time.perf_counter()
            self.schedule_timer_update()

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
        if not self.items:
            self.end_game("No items remain. Ending game.")
            return

        index = self.pointer_index()
        if index >= len(self.base_names):
            self.end_game("All items were removed during the spin.")
            return

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
            self.status.config(text=f"Result: {winner}. Spinning again shortly.")
            self.schedule_auto_spin()
            return

        display_winner = winner
        if applied_multiplier > 1:
            display_winner = f"{applied_multiplier}x {winner}"

        module_messages = []
        bpm_changed = False
        if "bpm_multiplier" in modules:
            multiplier = float(modules["bpm_multiplier"])
            total_multiplier = math.pow(multiplier, applied_multiplier)
            self.bps *= total_multiplier
            bpm_changed = True
            module_messages.append(
                f"BPM multiplied by {total_multiplier} to {self.display_bps_value()}."
            )

        if "bpm_boost" in modules:
            boost = modules["bpm_boost"] * applied_multiplier
            self.bps += boost
            bpm_changed = True
            module_messages.append(
                f"BPM increased by {boost} to {self.display_bps_value()}."
            )

        if bpm_changed:
            self.update_bpm_display()
            self.schedule_heartbeat()
            self.apply_bps_conditions()

        if "sound_effect" in modules:
            filename = str(modules["sound_effect"])
            if filename not in self.sound_cache:
                self.sound_cache[filename] = self.load_sound_file(filename)
            self.play_sound(self.sound_cache.get(filename))

        if modules.get("reset_timer"):
            self.reset_spin_timer()
            module_messages.append("Timer reset.")

        ended, message = self.handle_special_result(
            index, display_winner, applied_multiplier
        )
        self.pending_multiplier = 1

        max_ended, max_message = self.handle_max_result(base_name, display_winner)
        if max_message:
            message = max_message
        ended = ended or max_ended
        reached_max = False
        if base_name in self.max_targets_by_name:
            reached_max = (
                self.max_counts_by_name.get(base_name, 0)
                >= self.max_targets_by_name.get(base_name, 0)
            )

        if "fragile" in modules and not ended and not reached_max:
            message = self.handle_fragile_result(index, display_winner)
            ended = self.game_over

        if (
            "cooldown" in modules
            and not ended
            and base_name not in self.max_blocked_names
            and not reached_max
        ):
            cooldown_index = None
            for idx, name in enumerate(self.base_names):
                if name == base_name:
                    cooldown_index = idx
                    break

            if cooldown_index is not None:
                ended, message = self.handle_cooldown_result(
                    cooldown_index, display_winner
                )

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
            return False, f"Result: {display_winner}. Spinning again shortly."

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
            f"Result: {display_winner}. {name} chosen {display_current}/{target}. Spinning again shortly.",
        )

    def remove_all_items_by_base_name(self, base_name: str) -> int:
        removed = 0
        for idx in range(len(self.base_names) - 1, -1, -1):
            if self.base_names[idx] == base_name:
                removed += 1
                self.remove_item(idx)
        return removed

    def handle_max_result(self, base_name: str, display_winner: str) -> tuple[bool, str | None]:
        if base_name not in self.max_targets_by_name:
            return False, None

        self.max_counts_by_name[base_name] += 1
        current = self.max_counts_by_name[base_name]
        target = self.max_targets_by_name[base_name]
        if current < target:
            return False, (
                f"{display_winner} progress {current}/{target} towards Max. Spinning again shortly."
            )

        self.max_blocked_names.add(base_name)
        removed = self.remove_all_items_by_base_name(base_name)
        if not self.items:
            message = f"{display_winner} reached Max {target}. No items remain."
            self.end_game(message)
            return True, message

        return (
            False,
            f"{display_winner} reached Max {target}. Removed {removed} choice(s). Spinning again shortly.",
        )

    def handle_cooldown_result(self, index: int, display_winner: str) -> tuple[bool, str]:
        modules = self.item_modules[index]
        base_name = self.base_names[index]
        duration = int(modules.get("cooldown", 0))
        if duration <= 0:
            return False, f"Result: {display_winner}. Spinning again shortly."

        color = self.colors[index]
        modules_copy = dict(modules)
        self.remove_item(index)

        job: str | None = None

        def restore() -> None:
            self.restore_cooldown_item(base_name, modules_copy, color)
            if job in self.cooldown_jobs:
                self.cooldown_jobs.remove(job)  # type: ignore[arg-type]

        job = self.root.after(int(duration * 1000), restore)
        self.cooldown_jobs.append(job)

        if not self.items:
            message = f"{display_winner} is on cooldown for {duration} seconds. No items remain."
            self.end_game(message)
            return True, message

        return (
            False,
            f"{display_winner} is on cooldown for {duration} seconds. Spinning again shortly.",
        )

    def restore_cooldown_item(
        self, base_name: str, modules: dict[str, int | bool | float | str], color: str | None
    ) -> None:
        self.add_item_with_modules(base_name, modules, color)
        self.draw_wheel()

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
                self.status.config(text="Relax over. Spinning automatically.")
            return

        seconds_left = max(1, math.ceil(remaining))
        self.status.config(text=f"Relax: {seconds_left} seconds remaining.")
        self.break_timer_job = self.root.after(200, self.update_relax_timer)

    def end_game(self, message: str) -> None:
        self.game_over = True
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
            f"{display_winner} was destroyed after being chosen. Spinning again shortly."
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
        self.cancel_cooldown_jobs()
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
        self.auto_spin_var.set(True)
        self.last_pointer_index = self.pointer_index()
        self.cancel_timer()
        self.first_spin_time = None
        self.timer_label.config(text="Timer: 00:00")
        self.draw_wheel()
        self.schedule_heartbeat()
        self.update_bpm_display()
        self.status.config(text="Press Start to spin")

    def run(self) -> None:
        if self.items:
            self.root.mainloop()

    def display_bps_value(self) -> int:
        return int(round(self.bps))

    def bpm_text(self) -> str:
        return f"BPM: {self.display_bps_value()}"

    def update_bpm_display(self) -> None:
        self.bpm_label.config(text=self.bpm_text())


def main() -> None:
    root = tk.Tk()
    app = WheelOfFortune(root)
    app.run()


if __name__ == "__main__":
    main()
