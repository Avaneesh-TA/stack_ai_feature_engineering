# Starter Code — Churn Feature Pipeline

This is scaffolding, not a solution. Every file under `features/`, `feature_store/`,
`scripts/`, and `tests/` contains function signatures, docstrings, and `TODO`s only — no
working implementation. `feature_spec.md` is the one exception worth calling out
explicitly: it ships as **headers only**, with `<<LEARNER: ...>>` prompts instead of content
— not because it's less important, but because filling it in is the one part of this
assignment that's entirely your own judgment call, not Claude's. You do this by correcting
Claude's Stage 0-generated `data_dictionary.md` and candidate-feature proposal against
`skill.md`'s Domain Context section — reacting to and fixing Claude's draft, not writing from
a blank page, but the correcting is yours alone. See "What fills this in" below.

## How this relates to `skills/churn-feature-pipeline/skill.md`

`skill.md` is the build spec Claude follows once your `feature_spec.md` is confirmed. The
folder layout and function signatures in this scaffolding (`features/build.py`'s
`build_features(as_of, source_paths=...)`, `feature_store/store.py`'s
`register_version(feature_name, values_df, description, source_columns,
transform_summary, business_rationale, parameters) -> version`, `get_latest`,
`get_version`, `list_versions`, etc.) match exactly what `skill.md`'s Workflow section and
its "Repo scaffold to create" specify — this scaffold is the shape Claude fills in at the
same paths, not a different or relocated design. When you invoke the skill, Claude fills in
these same files in place; it does not create a parallel structure elsewhere.

## What fills this in

Claude (invoked via the `churn-feature-pipeline` skill's Stage 0, to generate
`data_dictionary.md` and a candidate-feature proposal from the raw sources), then you (correcting
that proposal into `feature_spec.md` against `skill.md`'s Domain Context section, replacing
every `<<LEARNER: ...>>` prompt in the skeleton), then Claude again (invoked via the same
skill's build stage once your corrected spec is confirmed) fill in:

- `feature_spec.md` — **you**, alone, by correcting Stage 0's proposal — not Claude, and not
  a blank page either. The content under each heading is entirely your own judgment to
  decide, even where it ends up agreeing with Stage 0's original proposal.
- `features/` — ingestion (`ingest.py`), transforms (`transforms.py`), schema
  (`schema.py`), quality checks (`quality_checks.py`), and the single shared build entry
  point (`build.py`)
- `feature_store/` — the SQLite registry + parquet value snapshots (`store.py`, then the
  generated `registry.db` and `values/`)
- `scripts/` — the training-build, scoring, and version-comparison entry points
- `tests/` — the real test suite (this scaffold only has skipped test stubs)

Claude also generates `FEATURE_LINEAGE.md`, `ARTIFACT_NOTES.md`, `PARITY_CHECK.md`,
`VERSION_COMPARISON.md`, and `review_log.md` at the repo root, per `skill.md`.

See `Assignment Document.docx`, `Helper Guide.docx`, and
`skills/churn-feature-pipeline/skill.md` for the full sequence.

## Layout

```
starter-code/
  feature_spec.md     headers only — <<LEARNER: ...>> prompts, yours to fill in before Claude sees it
  features/           ingest.py, transforms.py, schema.py, quality_checks.py, build.py
  feature_store/      store.py
  scripts/            build_training_features.py, score_customer.py, compare_feature_versions.py
  tests/              test_transforms.py, test_parity.py, test_quality_checks.py, test_feature_store.py
  outputs/artifacts/  generated reports/logs/screenshots go here, not in features/, scripts/, or tests/
  requirements.txt
  pytest.ini          sets pythonpath so `pytest` resolves features/feature_store imports with no extra flags
  .env.example
```

This mirrors `skill.md`'s "Repo scaffold to create" exactly (the raw data files and
`requirements.txt` also live at this same repo root once you bring them in during setup — see
`Helper Guide.docx`'s setup steps; `data_dictionary.md` is not among them — it doesn't exist
yet at setup time, Claude generates it afterward via Stage 0. `feature_spec.md` is the one
file already provided here as a skeleton, not something you create from a blank file).
