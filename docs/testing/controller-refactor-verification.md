# Controller refactor verification

Date: 2026-10-21. Baseline: `956e719`. Execution: inline in the existing
`feature/ram-optimization-subtitle-styling` checkout, as requested.

## Scope

Extracted four views, sidebar/cards, immutable render snapshots and presentation
helpers. SettingsCoordinator owns persistence, rollback and runtime application.
ControllerWindow retains composition, navigation, Start/Stop and explicit
compatibility aliases. `main.apply_selected_region` delegates once to the public
window API. No dependency, engine, retry, thread shutdown or configuration-schema
changes. Existing changes to `config.json` and `Microsoft/` were left alone.

## Automated verification

Environment: Windows, existing Python 3.10 virtual environment, PyQt5, pytest,
pytest-qt. Tests use existing network/capture/model guards and temporary config.
The sandbox could not access pytest's existing temporary directory; verification
was rerun with approved access outside the sandbox.

- Before extraction: `python -B -m pytest tests -q` — 121 passed.
- After R01–R09: full suite — 169 passed.
- Final R10 suite: `python -B -m pytest tests -q` — 169 passed.
- New-module tests were run before implementation and failed on the expected
  missing module/API. Characterization tests ran against the existing behavior.
- Each task's specified regression command passed before its commit and again
  when recorded in the execution ledger.
- Coverage includes safe error messages; rollback before error; persistence
  before worker/overlay application; all ten setting groups; negative coordinates;
  custom models; cursor/selection/echo preservation; signal blocking; parented
  highlight timer; interval initialization once; overlay replacement/disconnection;
  repeated navigation without duplicate saves; public region application once.
- AST boundary checks resolve absolute and relative imports. Views do not import
  persistence/runtime; coordinator does not import pages/window. View imports
  were reloaded with runtime constructors and config loading made fatal.

## Visual verification and limits

A temporary pytest smoke harness rendered both `956e719:ui/controller.py` and the
refactored window under the same guarded configuration and fake worker. Segoe UI
was loaded into the harness because the Qt offscreen environment did not discover
system fonts automatically. No application font behavior was changed.

[Comparison image](controller-refactor-comparison.png): baseline left, refactor
right; rows are Overview, AI, OCR, Subtitle. The four pages preserve the observed
layout, labels, colors, controls, icons and logo. Some text clipping is present in
both versions at the baseline size; no visual redesign was attempted.

The harness also exercised 740×560 initial size, 660×480 minimum, 205px sidebar,
and scroll/resize for all three settings pages. Permanent tests check key
visibility, custom/provider values, save failures, preview, language/interval,
region callbacks, Start/Stop/Quit and overlay position signals.

Interactive desktop mouse dragging, selector selection/cancellation and live
OCR/translation were not manually exercised. Overlay movement was verified with
fakes/signals and existing rollback tests. This report does not claim a full
manual Windows acceptance pass or live API verification.

## Follow-up task map

| Existing task | Location after extraction |
|---|---|
| S04/S06 retry/lifecycle | Worker/lifecycle; window connects commands |
| S08 status/error | Window, sidebar and Console status rendering |
| C01 secret storage | Config/SecretStore, coordinator and AI input view |
| C03 readiness probe | Separate probe service, window routing, AI view |
| C06 usage/budget | Worker/budget, Console rendering, coordinator options |
| C07 glossary/OCR | Engine/core, OCR view intents, coordinator persistence |
| C08 profiles | Profile service applies via coordinator |

No completion boxes in other plans were changed.

## Final independent review

A fresh-context GPT-6 Astra reviewer inspected `956e719..f8c2214`, the plan/spec,
tests, old/new handlers and comparison image. No Critical or Important findings;
ready to merge. The reviewer did not rerun tests. One deferred Minor: 18 trailing
whitespace lines copied from baseline, with no runtime effect.

Execution decisions and their limits:

1. Worked in the current checkout at the user's request; commits share the existing
   feature branch rather than an isolated branch.
2. Used native Python bookkeeping because bundled Bash could not resolve basename
   and its task extractor did not recognize R01–R10 headings; only bookkeeping differs.
3. Desktop dragging/selector acceptance remains unverified; a desktop-specific
   interaction regression could escape fake/signal coverage.
4. Live OCR/translation was not revalidated; a live integration issue could remain.
5. Preserved baseline label clipping; existing readability issues remain.
6. Preserved geometry/mask and lifecycle/status behavior, including duplicate startup
   preset application, for later scoped fixes; their existing limitations remain.
7. Preserved plaintext .env and key autosave as required by C01 scope boundaries;
   existing storage/autosave limitations remain.
8. Preserved the empty model editor retaining its last saved model; editor and
   persistence can temporarily differ, as before.
