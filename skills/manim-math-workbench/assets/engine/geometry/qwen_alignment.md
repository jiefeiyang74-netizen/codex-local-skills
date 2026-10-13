# Optional known-text acoustic alignment

The default local Whisper analysis route is unchanged. This optional route
accepts an explicit `request.alignment_path`; it does not install or launch an
aligner, require CUDA, or download model weights. Keep inference assets outside
the distributed Skill. The renderer, geometry validation, audio clock, canvas,
identity and preview/final review gates remain shared with existing jobs.

An attachment declares both `source` and `timing_source` as
`qwen_forced_aligner`. It binds the actual destination WAV SHA, canonical
narration SHA, duration, master file path/SHA and exact Unicode range, plus a
list of immutable chunk JSON references with SHA and destination PCM offsets.
Each reference also binds model artifacts, official implementation artifact,
source revision and the original inference model identity. All paths are
provided by the job; no machine-specific paths are built into the engine.

Chunk documents preserve the exact input text and source range, input-to-output
mapping, actual audio and PCM hashes, sample rate/frame count, original chapter
and full-frame ranges, raw model timestamp bins, timestamp unit, official
fix_timestamp input/output, and per-slot LIS anchor/repaired provenance. Words
retain source indices, raw and processed boundaries, slot indices and zero-span
flags. The engine replays the official LIS postprocessing and verifies the
original PCM content at the declared offsets. A processed repaired slot is never
relabeled as a direct model prediction.

Zero-duration words receive no synthesized positive duration. Motion can use
direct acoustic endpoints inside a source phrase/sentence while retaining
repaired interior words explicitly. This is a bounded acoustic envelope, not a
claim of positive duration or perceptual accuracy for every character. The
known text supplies content authority; no free ASR spelling match is required.
Action audits bind each action, exact cue range, chosen cue envelope and its
containing sentence budget. Animation may borrow time within that sentence,
but cannot extend the source audio or cross the next narration sentence.

This additive alignment contract does not change the geometry schema or
standard/long-lesson production budgets. Inference artifacts and focused
integration checks are not substitutes for actual audible preview and current
video visual review.
