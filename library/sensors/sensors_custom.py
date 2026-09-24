# Custom data classes for turing-smart-screen themes
#
# LLM token stats: poll the Prometheus /metrics endpoint of a vLLM (or any
# OpenAI-compatible server exposing ``vllm:*_tokens_total``) and expose
# cumulative token total + live token rate, like nvitop's LLM panel.
# Configure target with env var TURING_LLM_METRICS_URL
# (default http://127.0.0.1:8000/metrics).
#
# SPDX-License-Identifier: GPL-3.0-or-later

import math
import os
import platform
import re
import time
import urllib.request
from collections import deque
from abc import ABC, abstractmethod
from typing import List

# ---------------------------------------------------------------------------
# Base class: theme-facing custom data source (required by library/stats.py)
# ---------------------------------------------------------------------------

class CustomDataSource(ABC):
    @abstractmethod
    def as_numeric(self) -> float:
        """Numeric value used for graph / radial progress bars (empty if none)."""
        pass

    @abstractmethod
    def as_string(self) -> str:
        """Text value used for text display / radial inner text."""
        pass

    @abstractmethod
    def last_values(self) -> List[float]:
        """Recent numeric values for line graphs (empty list if none)."""
        pass


# ---------------------------------------------------------------------------
# Shared poller: one HTTP fetch per ~1 s window feeds all custom classes
# ---------------------------------------------------------------------------

_COUNTER_RE = re.compile(
    r'^vllm:(?P<kind>prompt|generation)_tokens_total'
    r'\{(?P<labels>[^}]*)\}\s+(?P<value>[0-9eE.+-]+)',
    re.MULTILINE,
)


class _LLMTokenCollector:
    """Polls vLLM metrics, keeping total tokens and per-second rate."""

    def __init__(self, url: str, history_length: int = 10):
        self.url = url
        self.timeout = 3
        self.total: float = math.nan
        self.rate: float = math.nan
        self.rate_history: deque = deque(maxlen=history_length)
        self._last_counters = None
        self._last_time = None
        self._last_poll = 0.0

    def _fetch(self):
        try:
            req = urllib.request.Request(self.url, headers={"Accept": "text/plain"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            return None

    def poll(self) -> None:
        now = time.time()
        # Multiple custom classes read in the same scheduler pass: single fetch.
        if self._last_poll and (now - self._last_poll) < 1.0:
            return
        self._last_poll = now

        text = self._fetch()
        if text is None:
            # Unreachable: keep last known total, zero the rate.
            if not math.isnan(self.total):
                self.rate = 0.0
            self.rate_history.append(self.rate if not math.isnan(self.rate) else math.nan)
            return

        prompt = generation = 0.0
        found = False
        for m in _COUNTER_RE.finditer(text):
            found = True
            value = float(m.group("value"))
            if m.group("kind") == "prompt":
                prompt += value
            else:
                generation += value

        if not found:
            return

        total = prompt + generation
        elapsed = (now - self._last_time) if self._last_time is not None else None
        if (
            self._last_counters is not None
            and elapsed
            and elapsed > 0
            and total >= self._last_counters
        ):
            self.rate = (total - self._last_counters) / elapsed
        else:
            # First sample after start-up, or counter reset (server restart).
            self.rate = 0.0

        self.total = total
        self._last_counters = total
        self._last_time = now
        self.rate_history.append(self.rate)


def _human_tokens(value: float) -> str:
    """Token counts rendered human-readably, fixed 6-char width (anti-ghosting)."""
    if math.isnan(value):
        return " offline"
    if value >= 1e9:
        return f"{value / 1e9:5.2f}G"
    if value >= 1e6:
        return f"{value / 1e6:5.2f}M"
    if value >= 1e3:
        return f"{value / 1e3:5.1f}K"
    return f"{value:6.0f}"


def _human_rate(value: float) -> str:
    if math.isnan(value):
        return "offline"
    return f"{value:6.0f} t/s"


_COLLECTOR = _LLMTokenCollector(
    os.environ.get("TURING_LLM_METRICS_URL", "http://127.0.0.1:8000/metrics")
)


# ---------------------------------------------------------------------------
# Theme-facing custom data sources
# ---------------------------------------------------------------------------

class LLMTokenTotal(CustomDataSource):
    """Cumulative LLM tokens served (prompt + generation) by the local vLLM."""

    def as_numeric(self) -> float:
        _COLLECTOR.poll()
        return _COLLECTOR.total

    def as_string(self) -> str:
        _COLLECTOR.poll()
        return _human_tokens(_COLLECTOR.total)

    def last_values(self) -> List[float]:
        pass


class LLMTokenRate(CustomDataSource):
    """Live LLM token throughput (tokens per second) of the local vLLM."""

    def as_numeric(self) -> float:
        _COLLECTOR.poll()
        return _COLLECTOR.rate

    def as_string(self) -> str:
        _COLLECTOR.poll()
        return _human_rate(_COLLECTOR.rate)

    def last_values(self) -> List[float]:
        return list(_COLLECTOR.rate_history)
