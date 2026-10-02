# project_state.md

Agent skill that builds, updates, and reads Google Forms on Windows through the `gws` npm CLI. See [SKILL.md](SKILL.md) for usage.

## Architecture
- `scripts/form_builder.py`: library. Runs `node run.js` directly (no shell) so JSON escaping cannot break; `run.js` is found next to the `gws` shim on PATH, then under `AppData/Roaming/npm`, or via `GWS_FORMS_GWS_JS` / `GWS_FORMS_NODE_EXE`.
- `json_runner.py` (create), `form_fetcher.py` (snapshot), `form_updater.py` (ops), `form_reader.py` (responses) are thin CLIs over the library.

## Decisions
- Specs are validated before `forms.create`, so a bad spec never leaves an empty form; if items fail after creation, `PartialFormError` carries the Edit URL.
- `batch_update` splits requests to stay under Windows' 32,767-character command line (`MAX_BATCH_ARG_CHARS = 20_000`, measured after quote escaping); the revision guard applies to the first chunk only.
- In `form_updater.py`, a failed snapshot refresh is a warning, not a failed op, to prevent duplicate retries.
- JSON inputs are read with `utf-8-sig`.

## State
- 30 offline tests pass (`tests/run_tests.py`); `tests/simulate_lifecycle.py` runs clean; flake8 clean at 88.
- Pending: live check of the `--after` filter format (see [task.md](task.md)).
