#!/usr/bin/env python3
"""Local neural larynx backend for The Voice of Janus.

Silero supplies articulation/timbre only. Pyramid Language remains a separate
acoustic operator applied downstream. The model is intentionally not committed
into Git; the caller provides a local .pt model path.
"""

from __future__ import annotations

import hashlib
import math
import re
import struct
import wave
from pathlib import Path
from typing import Any

BACKEND_ID = "SILERO_TTS_V5_5_RU"
OFFICIAL_MODEL_URL = "https://models.silero.ai/models/tts/ru/v5_5_ru.pt"
ALLOWED_SPEAKERS = ("aidar", "baya", "kseniya", "xenia", "eugene")
ALLOWED_SAMPLE_RATES = (8000, 24000, 48000)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_larynx_config(config: dict[str, Any]) -> dict[str, Any]:
    backend = str(config.get("backend", ""))
    if backend != "silero_v5_5_ru":
        raise ValueError("larynx.backend must be 'silero_v5_5_ru'")

    speaker = str(config.get("speaker", "aidar"))
    if speaker not in ALLOWED_SPEAKERS:
        raise ValueError(f"unsupported Silero speaker: {speaker}")

    sample_rate_hz = int(config.get("sample_rate_hz", 48000))
    if sample_rate_hz not in ALLOWED_SAMPLE_RATES:
        raise ValueError(f"sample_rate_hz must be one of {ALLOWED_SAMPLE_RATES}")

    max_chars = int(config.get("chunk_max_chars", 700))
    if not 120 <= max_chars <= 1000:
        raise ValueError("chunk_max_chars must be within 120..1000")

    pause_s = float(config.get("inter_chunk_pause_s", 0.18))
    if not math.isfinite(pause_s) or not 0.0 <= pause_s <= 2.0:
        raise ValueError("inter_chunk_pause_s must be within 0..2")

    model_path = Path(str(config.get("model_path", "models/v5_5_ru.pt")))
    return {
        "backend": backend,
        "speaker": speaker,
        "sample_rate_hz": sample_rate_hz,
        "chunk_max_chars": max_chars,
        "inter_chunk_pause_s": pause_s,
        "model_path": model_path,
        "model_url": str(config.get("model_url", OFFICIAL_MODEL_URL)),
        "allow_model_download": bool(config.get("allow_model_download", False)),
    }


def split_text_chunks(text: str, max_chars: int = 700) -> list[str]:
    clean = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n").replace("\r", "\n")).strip()
    if not clean:
        raise ValueError("text must not be empty")

    units = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", clean) if part.strip()]
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current:
            chunks.append(current.strip())
            current = ""

    for unit in units:
        if len(unit) > max_chars:
            flush()
            words = unit.split()
            piece = ""
            for word in words:
                candidate = word if not piece else f"{piece} {word}"
                if len(candidate) > max_chars and piece:
                    chunks.append(piece)
                    piece = word
                else:
                    piece = candidate
            if piece:
                chunks.append(piece)
            continue

        candidate = unit if not current else f"{current} {unit}"
        if len(candidate) > max_chars:
            flush()
            current = unit
        else:
            current = candidate
    flush()
    return chunks


def _load_model(model_path: Path):
    if not model_path.is_file():
        raise FileNotFoundError(
            f"Silero model not found: {model_path}. Download v5_5_ru.pt from the official "
            "Silero model URL recorded in the larynx config. Automatic download is disabled "
            "by default so runtime network access remains explicit."
        )
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("Silero neural larynx requires PyTorch") from exc

    importer = torch.package.PackageImporter(str(model_path))
    model = importer.load_pickle("tts_models", "model")
    model.to(torch.device("cpu"))
    return model


def _write_pcm16_mono(path: Path, sample_rate_hz: int, samples: list[float]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = max((abs(float(v)) for v in samples), default=0.0)
    normalization = 0.94 / peak if peak > 0.94 else 1.0
    pcm = bytearray()
    for sample in samples:
        value = max(-1.0, min(1.0, float(sample) * normalization))
        pcm.extend(struct.pack("<h", int(round(value * 32767.0))))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate_hz)
        wav.writeframes(bytes(pcm))
    return {
        "sample_rate_hz": sample_rate_hz,
        "channels": 1,
        "sample_width_bits": 16,
        "frames": len(samples),
        "duration_s": len(samples) / sample_rate_hz,
        "normalization_gain": normalization,
        "sha256": sha256_path(path),
        "bytes": path.stat().st_size,
    }


def synthesize_to_wav(text: str, config: dict[str, Any], output_path: Path) -> dict[str, Any]:
    cfg = validate_larynx_config(config)
    if cfg["allow_model_download"]:
        raise RuntimeError(
            "Automatic model download is intentionally not implemented in the runtime path. "
            "Provision the model explicitly, then rerun with allow_model_download=false."
        )

    model = _load_model(cfg["model_path"])
    chunks = split_text_chunks(text, cfg["chunk_max_chars"])
    pause_frames = int(round(cfg["inter_chunk_pause_s"] * cfg["sample_rate_hz"]))
    samples: list[float] = []

    for index, chunk in enumerate(chunks):
        audio = model.apply_tts(
            text=chunk,
            speaker=cfg["speaker"],
            sample_rate=cfg["sample_rate_hz"],
        )
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu()
        values = audio.flatten().tolist() if hasattr(audio, "flatten") else list(audio)
        samples.extend(float(value) for value in values)
        if index + 1 < len(chunks) and pause_frames:
            samples.extend([0.0] * pause_frames)

    wav_meta = _write_pcm16_mono(output_path, cfg["sample_rate_hz"], samples)
    return {
        "backend_id": BACKEND_ID,
        "backend": cfg["backend"],
        "speaker": cfg["speaker"],
        "model_path": str(cfg["model_path"]),
        "model_sha256": sha256_path(cfg["model_path"]),
        "model_url_provenance": cfg["model_url"],
        "model_download_performed": False,
        "network_io": False,
        "chunk_count": len(chunks),
        "chunk_max_chars": cfg["chunk_max_chars"],
        "inter_chunk_pause_s": cfg["inter_chunk_pause_s"],
        "dry_wav": wav_meta,
    }
