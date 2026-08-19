# Local neural larynx models

Model weights are intentionally **not committed** to this repository.

Current canonical neural larynx profile:

- backend: `silero_v5_5_ru`
- expected local file: `models/v5_5_ru.pt`
- official model provenance: `https://models.silero.ai/models/tts/ru/v5_5_ru.pt`
- default speaker: `aidar`
- supported project speakers: `aidar`, `baya`, `kseniya`, `xenia`, `eugene`

The model supplies articulation/timbre only. It must not modify the canonical
`PYRAMID_LANGUAGE_117_121_ANCHORED_SPACE_v0.3` acoustic parameters.

Runtime network download is disabled by default. Provision the model explicitly,
then run `src/semantic_recitation_v4.py` with
`configs/osiris_origin_prime_recitation.v4_neural_human.json`.
