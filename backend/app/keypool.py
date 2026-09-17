"""
Round-robin API key pool with cooldown handling for 429 rate limits.

This file existed but was completely empty in the previous version even
though llm.py and stt.py both import `KeyPool` from it -- meaning the app
could not actually run. This is the fix.
"""
import time


class KeyPool:
    def __init__(self, keys: list[str], cooldown_seconds: int = 60):
        self.keys = [k for k in keys if k]
        self.cooldown_seconds = cooldown_seconds
        self._idx = 0
        self._cooldown_until: dict[str, float] = {}

    def available(self) -> bool:
        return len(self.keys) > 0

    def _is_cooling_down(self, key: str) -> bool:
        until = self._cooldown_until.get(key)
        return until is not None and time.monotonic() < until

    def next_key(self) -> str | None:
        """Round-robins through keys, skipping ones currently in cooldown."""
        if not self.keys:
            return None
        for _ in range(len(self.keys)):
            key = self.keys[self._idx % len(self.keys)]
            self._idx += 1
            if not self._is_cooling_down(key):
                return key
        # every key is cooling down -- just hand back the next one anyway
        return self.keys[self._idx % len(self.keys)]

    def mark_rate_limited(self, key: str):
        self._cooldown_until[key] = time.monotonic() + self.cooldown_seconds
