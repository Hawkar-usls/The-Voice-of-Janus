from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src" / "neural_larynx_silero.py"
spec = importlib.util.spec_from_file_location("neural_larynx_silero", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_supported_profile_validates() -> None:
    cfg = module.validate_larynx_config(
        {
            "backend": "silero_v5_5_ru",
            "speaker": "aidar",
            "sample_rate_hz": 48000,
            "chunk_max_chars": 700,
            "inter_chunk_pause_s": 0.18,
            "model_path": "models/v5_5_ru.pt",
            "allow_model_download": False,
        }
    )
    assert cfg["speaker"] == "aidar"
    assert cfg["sample_rate_hz"] == 48000
    assert cfg["allow_model_download"] is False


def test_unknown_speaker_fails_closed() -> None:
    try:
        module.validate_larynx_config(
            {
                "backend": "silero_v5_5_ru",
                "speaker": "not-a-speaker",
                "sample_rate_hz": 48000,
            }
        )
    except ValueError as exc:
        assert "unsupported Silero speaker" in str(exc)
    else:
        raise AssertionError("unknown speaker must be rejected")


def test_chunker_preserves_origin_prime_formula() -> None:
    formula = "ORIGIN → EXPERIENCE → RETURN → ORIGIN_PRIME"
    text = ("Первое предложение. " * 80) + formula + ". Финал."
    chunks = module.split_text_chunks(text, max_chars=240)
    assert chunks
    assert all(len(chunk) <= 240 for chunk in chunks)
    assert formula in " ".join(chunks)


def test_missing_model_fails_before_inference(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pt"
    try:
        module._load_model(missing)
    except FileNotFoundError as exc:
        assert "Silero model not found" in str(exc)
    else:
        raise AssertionError("missing model must fail closed")
