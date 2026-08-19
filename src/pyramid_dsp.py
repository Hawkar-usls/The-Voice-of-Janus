#!/usr/bin/env python3
"""Shared Pyramid Language acoustic operator.

This is a bounded modal-resonator approximation, not a measured impulse response.
It is intentionally reusable by offline WAV processing, JSON sonification and the
optional explicit-start microphone front end.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from voice_of_janus import calculate_modes


@dataclass(frozen=True)
class AcousticMode:
    physical_hz: float
    render_hz: float
    octave_multiplier: int


def load_preset(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("preset must be a JSON object")
    return data


def derive_acoustic_modes(
    preset: dict[str, Any],
    *,
    count: int = 8,
    minimum_hz: float = 35.0,
    maximum_hz: float = 900.0,
) -> list[AcousticMode]:
    if count < 1:
        raise ValueError("count must be >= 1")
    if minimum_hz <= 0 or maximum_hz <= minimum_hz:
        raise ValueError("invalid acoustic frequency band")

    modes = calculate_modes(preset)
    derived: list[AcousticMode] = []
    seen: set[float] = set()
    for mode in modes:
        physical = float(mode.physical_hz)
        render = physical
        multiplier = 1
        while render < minimum_hz:
            render *= 2.0
            multiplier *= 2
        while render > maximum_hz and multiplier > 1:
            render /= 2.0
            multiplier //= 2
        if not minimum_hz <= render <= maximum_hz:
            continue
        key = round(render, 6)
        if key in seen:
            continue
        seen.add(key)
        derived.append(
            AcousticMode(
                physical_hz=physical,
                render_hz=render,
                octave_multiplier=multiplier,
            )
        )
        if len(derived) >= count:
            break
    if not derived:
        raise ValueError("no usable acoustic modes in requested band")
    return derived


class ModalAcousticFilter:
    """Stateful parallel resonator bank suitable for block-by-block processing.

    The recurrence is a damped two-pole resonator. Wet output is normalized by
    (1-r), then mixed with the dry signal. It is a model-based coloration layer,
    not a claim to reconstruct an exact historical chamber response.
    """

    def __init__(
        self,
        frequencies_hz: Iterable[float],
        *,
        sample_rate_hz: int = 44100,
        decay_s: float = 0.32,
        wet: float = 0.72,
        dry: float = 0.62,
        output_gain: float = 0.85,
    ) -> None:
        self.sample_rate_hz = int(sample_rate_hz)
        if self.sample_rate_hz < 8000:
            raise ValueError("sample_rate_hz must be >= 8000")
        if decay_s <= 0:
            raise ValueError("decay_s must be > 0")
        if not 0.0 <= wet <= 1.0 or not 0.0 <= dry <= 1.0:
            raise ValueError("wet and dry must be within [0,1]")
        if not 0.0 < output_gain <= 1.0:
            raise ValueError("output_gain must be within (0,1]")

        freqs = [float(value) for value in frequencies_hz]
        if not freqs:
            raise ValueError("at least one frequency is required")
        nyquist = self.sample_rate_hz / 2.0
        if any(not math.isfinite(f) or f <= 0 or f >= nyquist for f in freqs):
            raise ValueError("all frequencies must be finite and below Nyquist")

        self.frequencies_hz = tuple(freqs)
        self.wet = float(wet)
        self.dry = float(dry)
        self.output_gain = float(output_gain)
        self._r = math.exp(-1.0 / (decay_s * self.sample_rate_hz))
        self._r2 = self._r * self._r
        self._coeff = tuple(
            2.0 * self._r * math.cos(2.0 * math.pi * f / self.sample_rate_hz)
            for f in self.frequencies_hz
        )
        self._z1 = [0.0] * len(self.frequencies_hz)
        self._z2 = [0.0] * len(self.frequencies_hz)
        self._wet_scale = (1.0 - self._r) / len(self.frequencies_hz)

    def reset(self) -> None:
        for index in range(len(self._z1)):
            self._z1[index] = 0.0
            self._z2[index] = 0.0

    def process_sample(self, sample: float) -> float:
        x = float(sample)
        resonant_sum = 0.0
        for index, coeff in enumerate(self._coeff):
            y = x + coeff * self._z1[index] - self._r2 * self._z2[index]
            self._z2[index] = self._z1[index]
            self._z1[index] = y
            resonant_sum += y
        wet_sample = resonant_sum * self._wet_scale
        mixed = (self.dry * x + self.wet * wet_sample) * self.output_gain
        # Soft limiting prevents pathological peaks without introducing a hard clip.
        return math.tanh(mixed)

    def process_block(self, samples: Iterable[float]) -> list[float]:
        return [self.process_sample(value) for value in samples]


def build_filter_from_preset(
    preset: dict[str, Any],
    *,
    sample_rate_hz: int = 44100,
    mode_count: int = 8,
    decay_s: float = 0.32,
    wet: float = 0.72,
    dry: float = 0.62,
    output_gain: float = 0.85,
) -> tuple[ModalAcousticFilter, list[AcousticMode]]:
    modes = derive_acoustic_modes(preset, count=mode_count)
    filter_ = ModalAcousticFilter(
        [mode.render_hz for mode in modes],
        sample_rate_hz=sample_rate_hz,
        decay_s=decay_s,
        wet=wet,
        dry=dry,
        output_gain=output_gain,
    )
    return filter_, modes
