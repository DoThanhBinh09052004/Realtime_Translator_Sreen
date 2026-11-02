# Project instructions for Codex

## Development Workflow Routing

This project uses both Superpowers and Ponytail.

### Small Tasks — Ponytail Primary

Examples:
- Small UI adjustments
- Localized bug fixes
- Simple logic changes
- Minor refactoring
- Configuration changes

Rules:
- Prefer Ponytail's minimal-change approach.
- Avoid unnecessary planning and abstractions.
- Skip optional heavyweight workflows when permitted.
- Preserve existing behavior and run relevant tests.

### Complex Tasks — Superpowers Primary

Examples:
- Building new features from scratch
- Architectural changes
- Multi-module implementations
- Complex debugging
- Large refactoring

Rules:
- Follow the relevant Superpowers workflows.
- Use brainstorming and planning when applicable.
- Follow TDD and verification requirements.
- Keep Ponytail's simplicity principles secondary.

### Conflict Resolution

- Only one workflow should be primary per task.
- Small task: Ponytail is primary.
- Complex task: Superpowers is primary.
- Explicit user instructions take precedence.
- Do not override mandatory plugin instructions silently.
- If task complexity changes, reassess the workflow.
- Correctness, security and test coverage must not be sacrificed.

## Code exploration

- Default to `rg` and targeted source reads for locating implementations, answering small questions, inspecting known files, and reviewing code across multiple files. Read the relevant symbols and surrounding context rather than dumping entire directories or many large files at once.
- Keep searches focused on relevant symbols and project-relative paths. Prefer application code in `main.py`, `core/`, `engines/`, and `ui/`; include `tests/` for relevant contracts. Avoid unrelated scripts under `.agent/` and `.agents/`.
- The MORT reference repository is outside this checkout at `../MORT`. Read it with `rg` and direct file reads only when the task requires that reference. Do not add a symlink/junction into this checkout.
- Follow the active runtime path and verify signal/callback wiring where relevant. Distinguish legacy or test-only helpers from production dispatch, trace results through the final consumer, and state any gaps rather than treating search hits as proof of behavior.
- CodeGraph has been removed from this project. Do not use it or recreate its index unless the user explicitly requests it.
- Use normal tools to edit files and run appropriate checks. Source exploration does not replace tests or verification.

These defaults apply to this repository. Follow any additional instructions in nested `AGENTS.md` files when working in their directories.

## Planning documents

- Keep all project plans, design specs, and execution progress in docs/plans/ only, using dated filenames.
- Do not create alternate planning directories such as docs/superpowers/ or .superpowers/sdd/, even when a skill suggests them.
