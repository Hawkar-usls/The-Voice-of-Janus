#!/usr/bin/env python3
"""Dry-larynx conditioning for a softer JANUS articulation source.

This module deliberately runs before Pyramid117121Filter. It changes the dry
voice timbre only; the Pyramid Language acoustic operator remains unchanged.
"""

from __future__ import annotations

import math
from typing import Iterable


def soften_block(
    samples: Iterable[float],
    *,
    sample_rate_hz: int,
    lowpass_hz: float = 5400.0,
    dry_blend: float = 0.12,
    compression_drive: float = 1.12,
    output_gain: float = 0.92,
) -> list[float]:
    if sample_rate_hz < 8000:
        raise ValueError("sample_rate_hz must be >= 8000")
    if not 0.0 < lowpass_hz < sample_rate_hz / 2.0:
        raise ValueError("lowpass_hz must be below Nyquist")
    if not 0.0 <= dry_blend <= 1.0:
        raise ValueError("dry_blend must be in [0,1]")
    if compression_drive <= 0.0:
        raise ValueError("compression_drive must be > 0")
    if not 0.0 < output_gain <= 1.0:
        raise ValueError("output_gain must be in (0,1]")

    alpha = math.exp(-2.0 * math.pi * lowpass_hz / sample_rate_hz)
    state_1 = 0.0
    state_2 = 0.0
    denom = math.tanh(compression_drive)
    output: list[float] = []

    for sample in samples:
        x = float(sample)
        state_1 = (1.0 - alpha) * x + alpha * state_1
        state_2 = (1.0 - alpha) * state_1 + alpha * state_2
        smoothed = (1.0 - dry_blend) * state_2 + dry_blend * x
        compressed = math.tanh(compression_drive * smoothed) / denom
        output.append(compressed * output_gain)

    return output
