# Precommit source OCR fallback correction — 2026-10-26

Root found the Git-index source snapshot retains the release manifest but excludes ignored weights. That metadata-only directory incorrectly activated strict bundled resolution and broke source OCR spans (root reproduction: 10 FAIL / 2 PASS).

Changed only `core/ocr_models.py` and `tests/test_ocr_bundle_runtime.py`. Default source EN/JP now returns legacy `None` when no expected model `.pdmodel` or `.pdiparams` payload path exists. Manifest/dictionary/notice provenance can remain in the checkout. Any existing expected payload path, including empty/corrupt files or dangling symlinks, activates strict validation; partial staging still fails. Frozen and explicit-root resolution always remain strict.

TDD evidence:
- RED: `pytest tests/test_ocr_bundle_runtime.py -k 'metadata_only or damaged_weight' -q -p no:cacheprovider --basetemp <fresh allowed directory>` produced 2 FAIL / 7 PASS / 8 deselected. The failures were default source English/Japanese raising `OcrModelError` on metadata-only staging; frozen/explicit and damaged-payload guards already passed.
- GREEN: `pytest tests/test_ocr_bundle_runtime.py tests/test_ocr_model_assets.py tests/test_ocr_spans.py -q -p no:cacheprovider --basetemp <fresh allowed directory>` produced 41 PASS in 3.16s.
- `git diff --check -- core/ocr_models.py tests/test_ocr_bundle_runtime.py`: exit 0 (Git's existing CRLF normalization notice only).

Both test runs used `.venv/Scripts/python.exe` with fresh TEMP/TMP/basetemp in the granted visualization root and existing offline/capture guards. No native executable rebuild, asset mutation, staging, commit, or Git-index change was performed. Root owns staged-tree full-suite verification and commit.

Operator recipe updated to prepare into fresh scratch/ocr-assets and pass -ModelDir accordingly: Git already contains metadata-only assets/ocr, and prepare_models intentionally refuses existing output. This avoids overwriting the tracked release manifest or weakening atomic preparation. Scoped review approved the resolver/test correction; root verifies the final staged source tree.

Final Git-index source snapshot: 675 PASS in 64.82s, exit0. Snapshot includes tracked source/tests/fixtures and staged changes, excludes preexisting untracked background tests and ignored model payload/build artifacts. The commit preserves user-only working-tree changes.
