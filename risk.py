# risk.py
from __future__ import annotations
import time
import datetime as dt
from typing import Tuple, Optional

class Risk:
    def __init__(self, max_per_order=5.0, max_daily=25.0, cooldown=60, trail_pct=0.8):
        """
        Args:
            max_per_order: max USD per single order (pre-fees).
            max_daily:     max USD BUY spend per UTC day (pre-fees).
            cooldown:      seconds after each filled BUY during which BUYs are blocked.
            trail_pct:     trailing stop threshold in PERCENT (e.g., 2.0 => 2% drop from peak).
        """
        self.max_per_order = float(max_per_order)
        self.max_daily = float(max_daily)
        self.cooldown = int(cooldown)
        self.trail_pct = float(trail_pct)  # PERCENT
        # runtime state
        self._day_utc: Optional[dt.date] = None
        self._spent: float = 0.0          # USD spent on BUYs today
        self._last_buy_ts_wallclock: float = 0.0
        self._cooldown_deadline_mono: Optional[float] = None

        self._roll_day_if_needed()

    # ---- internals ----
    def _roll_day_if_needed(self) -> None:
        today = dt.datetime.utcnow().date()
        if self._day_utc != today:
            self._day_utc = today
            self._spent = 0.0

    # ---- public API (backward compatible) ----
    def allow(self, notional: float, side: str = "buy") -> Tuple[bool, str]:
        """
        Returns (ok, reason). reason == "ok" if permitted.
        - Per-order cap always enforced.
        - Daily cap & cooldown apply to BUYs only.
        """
        self._roll_day_if_needed()

        n = float(notional)
        if n <= 0:
            return False, "invalid_notional"
        if n > self.max_per_order:
            return False, f"over_per_order_cap({n:.2f}>{self.max_per_order:.2f})"

        if side.lower() == "buy":
            projected = self._spent + n
            if projected > self.max_daily:
                return False, f"over_daily_cap({projected:.2f}>{self.max_daily:.2f})"
            if self._cooldown_deadline_mono is not None:
                remaining = self._cooldown_deadline_mono - time.monotonic()
                if remaining > 0:
                    return False, f"cooldown_active({int(remaining)}s_left)"

        return True, "ok"

    def record(self, notional: float, side: str = "buy") -> None:
        """
        Call after a filled order.
        - BUY: increments daily spend and starts cooldown.
        - SELL: no effect on spend/cooldown.
        """
        self._roll_day_if_needed()

        if side.lower() == "buy":
            n = max(0.0, float(notional))
            self._spent += n
            self._last_buy_ts_wallclock = time.time()
            if self.cooldown > 0:
                self._cooldown_deadline_mono = time.monotonic() + float(self.cooldown)

    # ---- helpers (optional) ----
    def spent_today(self) -> float:
        self._roll_day_if_needed()
        return self._spent

    def cooldown_remaining(self) -> int:
        if self._cooldown_deadline_mono is None:
            return 0
        rem = int(self._cooldown_deadline_mono - time.monotonic())
        return rem if rem > 0 else 0
