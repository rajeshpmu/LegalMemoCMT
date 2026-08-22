# Active Annotation Stage

This package adds an additive, provenance-preserving active/semi-supervised annotation layer to Phase 2.

Implemented now:

- schema extension without overwriting existing labels
- diverse seed selection
- configurable annotation-priority scoring
- reviewer queue export
- optional text/audio model suggestions
- human-annotation merge with canonical-label validation
- annotation-status and provenance validation

Deferred until diarization, role mapping, and a human seed set exist:

- automatic pseudo-label acceptance
- iterative warm-start retraining
- benchmark/test-set selection by uncertainty
- contradiction-pair construction
- automatic video affect inference

The scripts are intentionally usable on a copy of a manifest first.
