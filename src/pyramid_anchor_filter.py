#!/usr/bin/env python3
"""Pyramid Language v0.3 — 117-121 Hz anchored audio-space filter.

Processes ordinary mono PCM16 audio through a dominant 117-121 Hz acoustic
anchor plus a geometry-derived reverberant tail. This is a model-based effect,
not a measured impulse response and not proof of intentional ancient tuning.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import wave
from pathlib import Path


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class PeakingEQ:
    """RBJ-style peaking biquad used to emphasize the selected anchor band."""

    def __init__(self, sample_rate_hz: int, center_hz: float, q: float, gain_db: float) -> None:
        amplitude = 10.0 ** (gain_db / 40.0)
        omega = 2.0 * math.pi * center_hz / sample_rate_hz
        alpha = math.sin(omega) / (2.0 * q)
        cosine = math.cos(omega)

        b0 = 1.0 + alpha * amplitude
        b1 = -2.0 * cosine
        b2 = 1.0 - alpha * amplitude
        a0 = 1.0 + alpha / amplitude
        a1 = -2.0 * cosine
        a2 = 1.0 - alpha / amplitude

        self.b0 = b0 / a0
        self.b1 = b1 / a0
        self.b2 = b2 / a0
        self.a1 = a1 / a0
        self.a2 = a2 / a0
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0

    def process_sample(self, sample: float) -> float:
        output = (
            self.b0 * sample
            + self.b1 * self.x1
            + self.b2 * self.x2
            - self.a1 * self.y1
            - self.a2 * self.y2
        )
        self.x2 = self.x1
        self.x1 = sample
        self.y2 = self.y1
        self.y1 = output
        return output


class DampedResonator:
    def __init__(self, sample_rate_hz: int, frequency_hz: float, decay_s: float) -> None:
        radius = math.exp(-1.0 / (max(decay_s, 1e-6) * sample_rate_hz))
        self.coefficient = 2.0 * radius * math.cos(
            2.0 * math.pi * frequency_hz / sample_rate_hz
        )
        self.radius_squared = radius * radius
        self.z1 = 0.0
        self.z2 = 0.0
        self.scale = max(1.0 - radius, 1e-7)

    def process_sample(self, sample: float) -> float:
        output = sample + self.coefficient * self.z1 - self.radius_squared * self.z2
        self.z2 = self.z1
        self.z1 = output
        return output * self.scale


class FeedbackDelay:
    def __init__(self, delay_samples: int, feedback: float, damping: float) -> None:
        self.buffer = [0.0] * max(1, delay_samples)
        self.index = 0
        self.feedback = feedback
        self.damping = damping
        self.low_pass_state = 0.0

    def process_sample(self, sample: float) -> float:
        delayed = self.buffer[self.index]
        self.low_pass_state = (
            (1.0 - self.damping) * delayed + self.damping * self.low_pass_state
        )
        self.buffer[self.index] = sample + self.low_pass_state * self.feedback
        self.index = (self.index + 1) % len(self.buffer)
        return delayed


class Pyramid117121Filter:
    """Stateful real-time-compatible Pyramid Language filter.

    Ordinary input audio is preserved in the dry path. The wet path receives a
    strong 117-121 Hz anchor and a geometry-derived feedback-delay tail.
    """

    def __init__(
        self,
        sample_rate_hz: int,
        *,
        anchor_low_hz: float = 117.0,
        anchor_high_hz: float = 121.0,
        anchor_gain_db: float = 11.5,
        anchor_decay_s: float = 1.65,
        room_decay: float = 0.78,
        wet: float = 0.72,
        dry: float = 0.62,
        speed_of_sound_m_s: float = 343.0,
        geometry_m: tuple[float, float, float] = (10.45, 5.20, 5.80),
    ) -> None:
        if anchor_high_hz <= anchor_low_hz:
            raise ValueError("anchor_high_hz must exceed anchor_low_hz")
        if not 0.0 <= wet <= 1.0 or not 0.0 <= dry <= 1.0:
            raise ValueError("wet and dry must be in [0, 1]")

        center_hz = (anchor_low_hz + anchor_high_hz) / 2.0
        bandwidth_hz = anchor_high_hz - anchor_low_hz
        q = center_hz / bandwidth_hz

        self.anchor_band_hz = (anchor_low_hz, anchor_high_hz)
        self.anchor_center_hz = center_hz
        self.anchor_q = q
        self.peaking_eq = PeakingEQ(sample_rate_hz, center_hz, q, anchor_gain_db)
        self.resonators = [
            DampedResonator(sample_rate_hz, frequency, anchor_decay_s)
            for frequency in (anchor_low_hz, center_hz, anchor_high_hz)
        ]

        delay_samples: list[int] = []
        for length_m in geometry_m:
            round_trip_s = 2.0 * length_m / speed_of_sound_m_s
            delay_samples.append(max(1, int(round(round_trip_s * sample_rate_hz))))
        mixed_path_s = (geometry_m[1] + geometry_m[2]) / speed_of_sound_m_s
        delay_samples.append(max(1, int(round(mixed_path_s * sample_rate_hz))))

        feedbacks = (
            room_decay,
            room_decay * 0.94,
            room_decay * 0.91,
            room_decay * 0.88,
        )
        self.room_delays = [
            FeedbackDelay(delay, feedback, 0.22)
            for delay, feedback in zip(delay_samples, feedbacks)
        ]
        self.wet = wet
        self.dry = dry

    def process_sample(self, sample: float) -> float:
        colored = self.peaking_eq.process_sample(float(sample))
        anchor = sum(r.process_sample(colored) for r in self.resonators) / len(
            self.resonators
        )
        room = sum(
            delay.process_sample(colored + 1.8 * anchor) for delay in self.room_delays
        ) / len(self.room_delays)
        wet_signal = 0.58 * colored + 1.55 * anchor + 0.82 * room
        return math.tanh(self.dry * sample + self.wet * wet_signal)

    def process_block(self, samples: list[float]) -> list[float]:
        return [self.process_sample(sample) for sample in samples]


def read_mono_pcm16(path: Path) -> tuple[int, list[float]]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate_hz = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if channels != 1 or sample_width != 2:
        raise ValueError("input must be mono PCM16 WAV")
    values = struct.unpack("<" + "h" * (len(raw) // 2), raw)
    return sample_rate_hz, [value / 32768.0 for value in values]


def write_mono_pcm16(path: Path, sample_rate_hz: int, samples: list[float]) -> dict[str, float | int | str]:
    peak = max((abs(sample) for sample in samples), default=0.0)
    normalization_gain = 0.92 / peak if peak > 0.92 else 1.0
    pcm = bytearray()
    output_peak = 0.0
    for sample in samples:
        value = max(-1.0, min(1.0, sample * normalization_gain))
        output_peak = max(output_peak, abs(value))
        pcm.extend(struct.pack("<h", int(round(value * 32767.0))))

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate_hz)
        wav.writeframes(bytes(pcm))

    return {
        "normalization_gain": normalization_gain,
        "peak": output_peak,
        "bytes": path.stat().st_size,
        "sha256": sha256_path(path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply JANUS 117-121 Hz Pyramid Language effect")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sample_rate_hz, samples = read_mono_pcm16(args.input)
    filter_ = Pyramid117121Filter(sample_rate_hz)
    output = filter_.process_block(samples)
    output.extend(filter_.process_sample(0.0) for _ in range(int(sample_rate_hz * 2.0)))
    metadata = write_mono_pcm16(args.output, sample_rate_hz, output)

    receipt = {
        "receipt_type": "JANUS_PYRAMID_117_121_ANCHORED_AUDIO_RUN",
        "status": "LOCAL_EXECUTION_PASS",
        "input": {
            "path": args.input.name,
            "sha256": sha256_path(args.input),
            "sample_rate_hz": sample_rate_hz,
            "frames": len(samples),
        },
        "operator": {
            "anchor_band_hz": [117.0, 121.0],
            "anchor_center_hz": 119.0,
            "anchor_q": 29.75,
            "anchor_gain_db": 11.5,
            "anchor_decay_s": 1.65,
            "room_geometry_m": [10.45, 5.20, 5.80],
            "speed_of_sound_m_s": 343.0,
            "room_model": "geometry-derived feedback delays + anchored resonator bank",
            "wet": 0.72,
            "dry": 0.62,
            "claim_boundary": "MODEL_BASED_117_121_HZ_ANCHORED_EFFECT; NOT_A_MEASURED_IMPULSE_RESPONSE",
        },
        "output": {
            "path": args.output.name,
            "sample_rate_hz": sample_rate_hz,
            "channels": 1,
            "sample_width_bits": 16,
            "frames": len(output),
            "duration_s": len(output) / sample_rate_hz,
            **metadata,
        },
    }
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
