import copy
import unittest

from wheel import WheelOfFortune


class DummyVar:
    def __init__(self, value: bool):
        self.value = value

    def get(self) -> bool:
        return self.value

    def set(self, value: bool) -> None:
        self.value = value


class DummyWidget:
    def __init__(self) -> None:
        self.properties: dict[str, str] = {}
        self.config_calls: list[dict[str, str]] = []

    def config(self, **kwargs: str) -> None:
        self.config_calls.append(kwargs)
        self.properties.update(kwargs)

    def cget(self, key: str) -> str:
        return self.properties.get(key, "")


class DummyRoot:
    def after(self, ms: int, func=None):
        return "job"

    def after_cancel(self, job) -> None:  # pragma: no cover - no-op in tests
        return None


def build_test_wheel(base_name: str, modules: dict[str, int | float], bps: int) -> WheelOfFortune:
    wheel = WheelOfFortune.__new__(WheelOfFortune)
    wheel.root = DummyRoot()
    wheel.status = DummyWidget()
    wheel.top_bar = DummyWidget()
    wheel.bottom_bar = DummyWidget()
    wheel.timer_label = DummyWidget()
    wheel.session_timer_label = DummyWidget()
    wheel.bpm_label = DummyWidget()
    wheel.canvas = DummyWidget()
    wheel.auto_spin_var = DummyVar(False)
    wheel.heartbeat_enabled_var = DummyVar(False)
    wheel.items = [base_name]
    wheel.base_names = [base_name]
    wheel.item_modules = [copy.deepcopy(modules)]
    wheel.colors = ["#fff"]
    wheel.hidden_items = []
    wheel.spawn_configs = []
    wheel.spawn_jobs = []
    wheel.spawn_started = False
    wheel.cooldown_jobs = []
    wheel.special_targets_by_name = {}
    wheel.special_counts_by_name = {}
    wheel.max_targets_by_name = {base_name: int(modules.get("max", 0))} if "max" in modules else {}
    wheel.max_counts_by_name = {base_name: 0} if "max" in modules else {}
    wheel.max_blocked_names = set()
    wheel.initial_bps = bps
    wheel.bps = bps
    wheel.jitter = 0.0
    wheel.initial_speed = 0.0
    wheel.deceleration = 0.0
    wheel.pending_multiplier = 1
    wheel.angle_offset = 0.0
    wheel.last_pointer_index = 0
    wheel.wheel_pause_active = False
    wheel.wheel_pause_job = None
    wheel.wheel_pause_end_time = 0.0
    wheel.heartbeat_pause_active = False
    wheel.heartbeat_pause_job = None
    wheel.heartbeat_pause_end_time = 0.0
    wheel.auto_spin_job = None
    wheel.heartbeat_poll_job = None
    wheel.timer_job = None
    wheel.first_spin_time = None
    wheel.session_start_time = None
    wheel.post_pause_reset_pending = False
    wheel.sound_cache = {}
    wheel.game_over = False
    wheel.has_invalid_config = False
    wheel.hidden_items = []

    wheel.draw_wheel = lambda: None
    wheel.schedule_heartbeat = lambda: None
    wheel.schedule_auto_spin = lambda: None
    wheel.start_heartbeat_pause_timer = lambda duration: None
    wheel.start_wheel_pause_timer = lambda duration: None
    wheel.cancel_auto_spin = lambda: None
    wheel.cancel_wheel_pause_timer = lambda: None
    wheel.cancel_heartbeat_pause_timer = lambda: None
    wheel.reset_spin_timer = lambda: None

    return wheel


class WheelFinishSpinTests(unittest.TestCase):
    def test_max_item_blocked_after_bpm_filtering(self) -> None:
        modules = {"max": 1, "bps_min": 90, "bpm_multiplier": 0.1}
        wheel = build_test_wheel("Maxer", modules, bps=120)
        wheel.spawn_configs.append(
            {
                "index": 0,
                "base_name": "Maxer",
                "initial_delay": 1,
                "repeat_delay": 1,
                "color": "#fff",
                "modules": modules,
            }
        )

        wheel.finish_spin()

        self.assertIn("Maxer", wheel.max_blocked_names)
        self.assertEqual(wheel.max_counts_by_name["Maxer"], 1)
        self.assertEqual(wheel.base_names, [])
        self.assertEqual(wheel.items, [])
        self.assertEqual(wheel.hidden_items, [])
        self.assertEqual(wheel.spawn_configs, [])

        wheel.add_item_with_modules("Maxer", modules, color="#abc")
        self.assertEqual(wheel.base_names, [])
        self.assertEqual(wheel.items, [])

        wheel.apply_spawn_effect(
            {"base_name": "Maxer", "modules": modules, "repeat_delay": 1}
        )
        self.assertEqual(wheel.spawn_jobs, [])
        wheel.duplicate_spawn_item({"base_name": "Maxer", "modules": modules, "color": "#fff"})
        self.assertEqual(wheel.base_names, [])
        self.assertEqual(wheel.items, [])


if __name__ == "__main__":
    unittest.main()
