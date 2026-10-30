# Completed-download intake

`romsort.py` shares `backend/handler/rom_identification.py` with RomM's upload
preflight and publication guard. It uses content headers, ZIP member headers,
and unique CHD SHA-1 matches against existing platform folders. File extensions,
track modes, disc capacity and game titles never select a platform.

```sh
python3 integrations/romsort/romsort.py \
  --inbox /path/to/completed-downloads /path/to/manual-inbox \
  --library /path/to/roms --dry-run
```

Remove `--dry-run` to import recognized files. Sources remain in their original
locations in every mode, including duplicates and unresolved files. `auto` uses
hard links on the same filesystem and copies otherwise. Use `copy` when the
source could be edited after import. Existing different files are never replaced.
An atomic staging step hides incomplete copies from scans. A library lock
serializes sorter runs.

Ordinary download collections are traversed as separate games. Folders with a
CUE, GDI or M3U descriptor, or numbered disc subfolders, are kept together.
Descriptor references must stay inside the bundle. Symlinks and special files
are rejected. Unknown files stay in the inbox and are recorded in
`.romsort-content-v2.json`; delete their ledger entry to retry after resolving
an issue. New or changed files are retried automatically.

Only monitor completed downloads. The stability interval detects changes during
intake; it cannot prove that a paused download is complete. Header recognition
also does not prove that the entire image is intact. An existing-library CHD
match is identified separately from an external catalog verification.

## Host installation

The deployed launcher is `/usr/local/bin/romsort.py`. With Python's isolated mode,
it loads the shared detector from `/data/emulators/operations/romm-intake/`:

- `handler/__init__.py` (empty)
- `handler/rom_identification.py`
- `utils/__init__.py` (empty)
- `utils/chd.py`
- `utils/platform_slugs.py`

Update these together and retain the previous launcher and detector for rollback.
The existing `romsort.service` invokes the launcher with `--mode auto` and the
existing two-minute `romsort.timer` schedules it. No new service is required.

```sh
PYTHONPATH=backend python3 -m unittest discover -s integrations/romsort -p 'test_*.py'
```
