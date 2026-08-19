#!/usr/bin/env python3
"""Explicit-start local microphone voice changer for Pyramid Language.

No network I/O, no recording, and no microphone access occurs unless the user
runs this program with --start. The real-time backend is optional (`sounddevice`).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from pyramid_dsp import build_filter_from_preset, load_preset


STATUS_SCHEMA = "janus.voice.live_mic_session.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live local Pyramid Language microphone voice changer")
    parser.add_argument("--preset", type=Path, default=Path("presets/great_pyramid_kings_chamber.example.json"))
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--blocksize", type=int, default=512)
    parser.add_argument("--mode-count", type=int, default=6)
    parser.add_argument("--decay", type=float, default=0.22)
    parser.add_argument("--wet", type=float, default=0.72)
    parser.add_argument("--dry", type=float, default=0.62)
    parser.add_argument("--gain", type=float, default=0.82)
    parser.add_argument("--device", default=None, help="Optional sounddevice device id/name")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--start", action="store_true", help="Required explicit permission to open the microphone")
    return parser.parse_args()


def _load_sounddevice():
    try:
        import sounddevice as sd  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Live microphone mode requires optional dependency 'sounddevice'. "
            "Install the live-audio extras locally before use."
        ) from exc
    return sd


def main() -> int:
    args = parse_args()
    sd = _load_sounddevice()

    if args.list_devices:
        print(sd.query_devices())
        return 0

    if not args.start:
        raise SystemExit("MICROPHONE_NOT_OPENED: explicit --start is required")
    if args.blocksize < 64 or args.blocksize > 8192:
        raise SystemExit("blocksize must be between 64 and 8192")

    preset = load_preset(args.preset)
    acoustic, modes = build_filter_from_preset(
        preset,
        sample_rate_hz=args.sample_rate,
        mode_count=args.mode_count,
        decay_s=args.decay,
        wet=args.wet,
        dry=args.dry,
        output_gain=args.gain,
    )

    session = {
        "schema": STATUS_SCHEMA,
        "status": "EXPLICIT_LOCAL_MIC_SESSION_STARTING",
        "preset": str(args.preset),
        "sample_rate_hz": args.sample_rate,
        "blocksize": args.blocksize,
        "mode_count": len(modes),
        "modes": [
            {
                "physical_hz": mode.physical_hz,
                "render_hz": mode.render_hz,
                "octave_multiplier": mode.octave_multiplier,
            }
            for mode in modes
        ],
        "control": {
            "explicit_user_start": True,
            "network_io": False,
            "recording": False,
            "automatic_start": False,
        },
    }
    print(json.dumps(session, ensure_ascii=False))

    def callback(indata, outdata, frames, time_info, status):  # noqa: ANN001
        if status:
            print(status, file=sys.stderr)
        source = indata[:, 0]
        processed = acoustic.process_block(float(value) for value in source)
        outdata[:, 0] = processed

    stream_kwargs = {
        "samplerate": args.sample_rate,
        "blocksize": args.blocksize,
        "channels": 1,
        "dtype": "float32",
        "callback": callback,
    }
    if args.device is not None:
        stream_kwargs["device"] = args.device

    try:
        with sd.Stream(**stream_kwargs):
            print("PYRAMID_LANGUAGE_MIC=ACTIVE; Ctrl+C to stop", file=sys.stderr)
            while True:
                time.sleep(0.25)
    except KeyboardInterrupt:
        print("PYRAMID_LANGUAGE_MIC=STOPPED", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
