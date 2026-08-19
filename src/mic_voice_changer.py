#!/usr/bin/env python3
"""Explicit-start local microphone voice changer for Pyramid Language v0.3.

No network I/O, no recording, and no microphone access occurs unless the user
runs this program with --start. The live stream uses the same 117-121 Hz
anchored acoustic operator as offline JANUS Voice rendering.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from pyramid_anchor_filter import Pyramid117121Filter

STATUS_SCHEMA = "janus.voice.live_mic_session.v2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live local JANUS 117-121 Hz Pyramid Language voice changer")
    parser.add_argument(
        "--activation",
        type=Path,
        default=Path("configs/pyramid_117_121_space.activation.json"),
    )
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--blocksize", type=int, default=512)
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


def load_activation(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("activation must be a JSON object")
    return data


def build_filter(activation: dict, sample_rate_hz: int) -> Pyramid117121Filter:
    anchor = activation.get("anchor", {})
    room = activation.get("room_tail", {})
    band = anchor.get("band_hz", [117.0, 121.0])
    geometry = room.get("geometry_m", [10.45, 5.20, 5.80])
    if len(band) != 2 or len(geometry) != 3:
        raise ValueError("invalid activation band/geometry")
    return Pyramid117121Filter(
        sample_rate_hz,
        anchor_low_hz=float(band[0]),
        anchor_high_hz=float(band[1]),
        anchor_gain_db=float(anchor.get("gain_db", 11.5)),
        anchor_decay_s=float(anchor.get("decay_s", 1.65)),
        room_decay=float(room.get("room_decay", 0.78)),
        wet=float(room.get("wet", 0.72)),
        dry=float(room.get("dry", 0.62)),
        speed_of_sound_m_s=float(room.get("speed_of_sound_m_s", 343.0)),
        geometry_m=tuple(float(value) for value in geometry),
    )


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

    activation = load_activation(args.activation)
    acoustic = build_filter(activation, args.sample_rate)

    session = {
        "schema": STATUS_SCHEMA,
        "status": "EXPLICIT_LOCAL_MIC_SESSION_STARTING",
        "activation": str(args.activation),
        "operator": "Pyramid117121Filter",
        "anchor_band_hz": list(acoustic.anchor_band_hz),
        "anchor_center_hz": acoustic.anchor_center_hz,
        "anchor_q": acoustic.anchor_q,
        "sample_rate_hz": args.sample_rate,
        "blocksize": args.blocksize,
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
        source = [float(value) for value in indata[:, 0]]
        processed = acoustic.process_block(source)
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
            print("PYRAMID_LANGUAGE_117_121_MIC=ACTIVE; Ctrl+C to stop", file=sys.stderr)
            while True:
                time.sleep(0.25)
    except KeyboardInterrupt:
        print("PYRAMID_LANGUAGE_117_121_MIC=STOPPED", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
