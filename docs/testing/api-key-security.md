# C01 — API key storage

Implemented on 2026-10-25 against the existing dialogue/overlay architecture.

## Behavior

- Settings are copied once from the legacy source-directory config into the fixed
  QStandardPaths generic user-data location under `TranslateHUD/TranslateHUD`.
  The new config has `schema_version=1`; known credential fields are stripped.
  The original settings file is never changed by migration.
- Credentials use Windows DPAPI with the current user's scope and
  `CRYPTPROTECT_UI_FORBIDDEN`. No machine-wide encryption flag is used.
  Only encrypted bytes are written to atomic temporary files in the credential
  directory. Provider filenames come from a fixed whitelist.
- Typing does not save or reconfigure the worker. **Áp dụng key** explicitly
  applies the draft; the checkbox selects encrypted persistence or RAM only.
  RAM mode removes any previously persisted key before accepting the session key.
  A failed operation preserves the previously applied credential and worker state.
- **Xóa key** deletes protected/session credentials and invalidates the worker
  snapshot. Key changes use the existing revision, client/cache invalidation,
  and overlay reset paths.
- A corrupt/unreadable credential does not prevent startup. The UI reports the
  problem and supports entering a replacement or choosing RAM-only operation.
  Failed persistence keeps the draft so RAM mode can be selected without retyping.
- **Nhập key cũ từ .env** is the only normal path that reads legacy keys.
  Import never removes the source file automatically. After successful protected
  import, a separate confirmation can remove only that provider's key lines.
  Declining leaves the original file intact; unrelated lines remain unchanged.
- Normal credential reads/writes neither import environment keys nor copy keys
  into `os.environ`. Source development can explicitly opt in with
  `TRANSLATE_HUD_DEV_ENV=1`; frozen builds ignore this flag.
- Key status describes storage, not verified provider connectivity.

## Verification

Use `.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider`.
The default suite uses temporary settings/credential directories, fake network,
capture, and OCR. It does not import or modify real keys or user settings.
Final run: **503 passed in 54.74 seconds**, exit code 0. The targeted diff
whitespace check also passed. No provider/network smoke request was performed.

New coverage includes encrypted round-trip, session-only restart behavior,
DPAPI failure, corrupt blobs, provider path traversal, atomic replacement failure,
delete/conversion failure, excessive UTF-8 input, explicit legacy import/cleanup,
config migration and UI apply/delete/import. A native Windows DPAPI test uses a
fake key and a temporary directory; no real provider request is made.

An independent read-only review found no Critical/Important issues. Its Unicode
size-limit finding was reproduced with a failing test and fixed by checking
encoded byte size before replacing a credential. Offscreen UI inspection used
an empty key and a sample model.

## Boundaries

DPAPI protects credentials at rest; it is not protection against malware running
as the same Windows user. Existing plaintext legacy keys remain until explicitly
imported and removed. This change does not change HTTP endpoint policy, translation
content logging, model download verification, or release packaging.
