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

# Supports vLLM ("vllm:prompt_tokens_total{model=...} N"), veloGB10
# ("velogb10_prompt_tokens_total N") and TensorFold ("tensorfold:prompt_...").
_COUNTER_RE = re.compile(
    r'^(?:vllm:|velogb10_|tensorfold:)(?P<kind>prompt|generation)_tokens_total'
    r'(?:\{[^}]*\})?\s+(?P<value>[0-9eE.+-]+)',
    re.MULTILINE,
)
# True LIVE generation speed for veloGB10: token totals commit only when a
# request FINISHES. The scheduler step gauge advances continuously while
# decoding; instant speed = d(steps)/dt * (spec_emitted_total / steps_total).
_STEPS_RE = re.compile(r'^velogb10_scheduler_steps_total\s+([0-9eE.+-]+)', re.MULTILINE)
_EMIT_RE = re.compile(r'^velogb10_spec_emitted_tokens_total\s+([0-9eE.+-]+)', re.MULTILINE)
_RUNNING_RE = re.compile(r'^(?:velogb10_requests_running|tensorfold:requests_running)'
                         r'(?:\{[^}]*\})?\s+([0-9eE.+-]+)', re.MULTILINE)
# TensorFold commits every *_total at request finish too, but
# generation_tokens_running (tokens held by live streams) moves every decode
# round: d(running)/dt is the instant tokens/s directly.
_TF_RUNTOK_RE = re.compile(
    r'^tensorfold:generation_tokens_running(?:\{[^}]*\})?\s+([0-9eE.+-]+)',
    re.MULTILINE)


class _LLMTokenCollector:
    """Polls vLLM metrics, keeping total tokens and per-second rate."""

    def __init__(self, url: str, history_length: int = 10, api_key: str = ""):
        self.url = url
        # Bearer token for servers that gate /metrics behind an API key
        # (e.g. TensorFold with TENSORFOLD_API_KEY set).
        self.api_key = api_key or os.environ.get("TURING_LLM_API_KEY", "")
        self.timeout = 3
        self.total: float = math.nan
        self.rate: float = math.nan
        self.rate_history: deque = deque(maxlen=history_length)
        self._last_counters = None
        self._last_time = None
        self._last_poll = 0.0
        self._decode_hist = None
        self._decode_ema = None
        self._decode_time = None

    def _fetch(self):
        try:
            headers = {"Accept": "text/plain"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            req = urllib.request.Request(self.url, headers=headers)
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

        # veloGB10 / TensorFold freeze token totals until each request
        # finishes. veloGB10: step gauge moves continuously, instant speed ~=
        # d(steps)/dt * (spec_emitted_total / steps_total). TensorFold:
        # generation_tokens_running (live-stream tokens) moves every round,
        # d(running)/dt is tokens/s directly. Both EMA'd.
        st = _STEPS_RE.search(text)
        tf = None if st else _TF_RUNTOK_RE.search(text)
        r = _RUNNING_RE.search(text)
        running = float(r.group(1)) if r else 0.0
        if st or tf:
            if st:
                qty = float(st.group(1))
                em = _EMIT_RE.search(text)
                emit = float(em.group(1)) if em else None
            else:
                qty = float(tf.group(1)) if tf else 0.0
                emit = None  # qty already in tokens: multiplier 1
            elapsed = (now - self._decode_time) if self._decode_time else 0.0
            inst = None
            if self._decode_hist is not None and elapsed > 0:
                d = qty - self._decode_hist[0]
                if d >= 0:
                    if emit is not None and qty > 0:
                        inst = (d / elapsed) * (emit / qty)
                    else:
                        inst = d / elapsed
            self._decode_hist = (qty, emit)
            self._decode_time = now
            if inst is not None:
                self._decode_ema = (inst if self._decode_ema is None
                                    else 0.3 * inst + 0.7 * self._decode_ema)
            if running > 0 and self._decode_ema is not None:
                self.rate = max(self.rate, self._decode_ema)

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
