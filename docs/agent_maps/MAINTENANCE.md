# Agent Map Maintenance

These docs are durable lookup and breadcrumbing aids. They do not replace requirements, specs, tests, or QA matrices.

## Required Update Rule

Update the affected map and [Coverage Matrix](COVERAGE.md) in the same change when you alter any of these:

- feature routing or workflow entry points
- subsystem ownership or module boundaries
- public contracts, schemas, action IDs, bridge payloads, or file formats
- common insertion points future agents should use
- focused verification commands or test ownership
- generated asset workflows or packaging commands
- work-packet status, retained proof location, or QA matrix routing

If no map update is needed, say that explicitly in the final response.

## How To Update

1. Open [Coverage Matrix](COVERAGE.md) and find the affected source area, feature route, packet, node family, QML family, or test family.
2. Open the linked subsystem or feature-route page.
3. Update only facts that changed: owner files, do-not-start-here notes, focused tests, breadcrumbs, or update triggers.
4. If a new feature or folder appears, add a coverage row immediately.
5. If a route becomes formal spec or closeout proof, link it from the relevant spec-pack artifact instead of moving these lookup docs into `docs/specs/`.

## Page Shape

Use this compact shape for new pages:

- Purpose
- Start here
- Do not start here
- Common changes
- Focused verification
- Breadcrumbs
- Update triggers

Prefer route accuracy and links over long prose. Keep implementation detail in code, tests, specs, or work-packet docs.
