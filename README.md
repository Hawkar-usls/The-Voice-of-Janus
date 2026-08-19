# The Voice of Janus

**Geometry → Resonance → Sound.**

`The-Voice-of-Janus` is the executable audio branch of JANUS: JSON describes geometry, evidence boundaries, presets and render instructions; Python performs deterministic acoustic calculations and DSP rendering.

## Design rule

```text
JSON = contract / configuration / provenance / receipt
Python = calculation / validation / DSP / rendering
AI audio = optional texture layer, never the precision-frequency authority
```

## Initial pipeline

```text
GEOMETRY
  -> MODAL_SOLVER
  -> EVIDENCE_GATE
  -> PHYSICAL_MODAL_BANK
  -> OPTIONAL_CREATIVE_TRANSLATION
  -> WAV_RENDER
  -> PROVENANCE_RECEIPT
```

The first implementation models rectangular chambers with:

`f_pqr = (c / 2) * sqrt((p/Lx)^2 + (q/Ly)^2 + (r/Lz)^2)`

where `p,q,r` are non-negative integers and are not all zero.

## Repository layout

- `data/` — canonical JSON instructions and system contracts.
- `presets/` — JSON room/chamber presets.
- `src/` — Python implementation.
- `receipts/` — generated provenance receipts; large audio should not be committed by default.

## First run

```bash
python src/voice_of_janus.py presets/great_pyramid_kings_chamber.example.json --out voice_of_janus.wav --receipt receipts/last_render.json
```

The Great Pyramid preset is explicitly **illustrative/model-based** until its dimensions and acoustic measurements are source-verified.

## Epistemic boundary

- A chamber can support acoustic eigenmodes and standing waves.
- A room has many modes, not one universal magical frequency.
- Predicted modal frequencies are not the same thing as measured resonances.
- Structural vibration modes and air-acoustic room modes are separate phenomena.
- Creative octave translation must preserve the original physical frequency in metadata.
- Generative audio systems may be used later for texture/orchestration, but exact frequency synthesis belongs to deterministic DSP.

**METAPHOR != PHYSICS**
