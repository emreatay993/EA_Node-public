# Retained Work-Packet QA Evidence And Spec Navigation

## Purpose
Use this for retained QA matrices, closeout proof, historical packet-set routing, and spec-pack navigation.

## Start Here
- `docs/specs/perf/`
- `docs/specs/requirements/TRACEABILITY_MATRIX.md`
- `docs/specs/INDEX.md`
- `docs/specs/perf/COREX_CHANGE_LOCALITY_QA_MATRIX.md`
- `docs/specs/perf/COREX_INTERNAL_PERFORMANCE_IMPROVEMENT_QA_MATRIX.md`
- `docs/specs/perf/COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md`
- `docs/agent_maps/`
- `scripts/check_traceability.py`
- `scripts/check_markdown_links.py`

## Common Changes
- Register retained closeout evidence in `docs/specs/INDEX.md` and `docs/agent_maps/COVERAGE.md`.
- Keep final packet-set QA matrices under `docs/specs/perf/` and link them from the spec index during closeout.
- Internal performance closeout uses `COREX_INTERNAL_PERFORMANCE_IMPROVEMENT_QA_MATRIX.md` as the canonical retained numeric record; ignored raw artifacts are supporting evidence, not the durable spec source.
- Novice function-plugin closeout uses
  `COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md` for the static-source, schema-2,
  immutable-generation, registry-replacement, worker, documentation, generated
  artifact, full-verification, and Windows-package acceptance record.
- Packet manifests, status ledgers, prompts, and wrap-ups are historical and live only in git history; do not route agents to a live packet-doc directory.
- Register authoritative but unimplemented capabilities under `Planned Capabilities — No Implementation Proof` and keep their traceability rows separate from retained implementation evidence.

## Focused Verification
```powershell
.\venv\Scripts\python.exe .\scripts\check_traceability.py
.\venv\Scripts\python.exe .\scripts\check_markdown_links.py
```

## Breadcrumbs
- [Docs, Traceability, And Hygiene Tests](../testing/docs_traceability_hygiene.md)
- [Verification, Testing, And Docs Hygiene](../subsystems/verification_testing_docs_hygiene.md)

## Update Triggers
Update when QA matrices, proof links, historical packet-set routing, traceability routing, agent-map closeout requirements, function-SDK acceptance evidence, or docs checks change.
