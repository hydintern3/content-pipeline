# AGENTS.md

## Project Status

This project is currently a Flask API backend plus a Vue 3 / Vite / TypeScript operations workspace frontend. The latest completed feature areas are generation history v1, compliance checking enhancements, and low-token article follow-up revision.

## Generation History Progress

Implemented:

- Added generation-run history as a first-class concept.
- Added backend tables through SQLAlchemy models:
  - `generation_runs`
  - `generation_run_articles`
- Added backend APIs:
  - `GET /api/history/generations`
  - `GET /api/history/generations/<run_id>`
- Extended `POST /api/materials/generate` with optional history fields:
  - `history_run_id`
  - `history_expected_platforms`
- Frontend now creates one shared run ID for a generation action, even though platforms are requested separately.
- Added `GenerationHistoryPanel` as a full-width workspace panel between the main workspace and support panels.
- History list supports refresh, keyword search, and platform filtering.
- History detail can restore material input and generated articles back into the current workspace.
- Restored results are marked as history-sourced in the article cards.

Scope boundaries for v1:

- Only new generations are recorded after this feature is deployed.
- No legacy data backfill.
- No deletion UI.
- No unified timeline for publishing, batch jobs, or image-processing tasks yet.
- Failed platform requests are still shown in the current workspace error area and are not written as history error records.

## Recent Fixes

- Tightened history platform filtering so `platform=zhihu` does not accidentally match `zhihu_qa`.
- Added a regression test for `zhihu` versus `zhihu_qa` filtering.

## Compliance Progress

Implemented:

- Added compliance mock mode through `CONTENT_LLM_MOCK` / `compliance.mock`; it skips LLM semantic checks and only runs regex rules.
- Added independent compliance model config through `CONTENT_LLM_COMPLIANCE_MODEL` / `compliance.llm_model`, falling back to the content generation model.
- Added in-memory LRU compliance result cache keyed by text hash, platform, compliance model, and mock flag.
- `POST /api/compliance/check` now accepts request-level `config` and `force_refresh`.
- Frontend generation now uses configurable generation concurrency and enqueues automatic compliance checks when each article arrives.
- Compliance results and loading state live in the workspace store, so automatic checks and manual re-checks share the same card state.
- Settings drawer now exposes generation concurrency, compliance concurrency, compliance model, cache size, auto-check, and mock mode.
- Rule checklist coverage tests verify supported platforms and core risk categories.

Config keys:

- `generation.concurrency`
- `compliance.mock`
- `compliance.llm_model`
- `compliance.cache_size`
- `compliance.auto_check`
- `compliance.concurrency`

## Article Follow-Up Progress

Implemented:

- Added low-token single-article follow-up revision through `POST /api/articles/<article_id>/follow_up`.
- Follow-up calls do not use model sessions and do not resend full platform prompts, source materials, or full follow-up history.
- Follow-up prompt only includes current article title/content, platform, output format, a short platform summary, and the current instruction.
- Each successful follow-up creates a new `generated_articles` record with `status="revised"` and leaves the original article unchanged.
- Added `article_followups` records linking source article, revised result article, instruction, model, and timestamp.
- Frontend article cards include a "追问优化" dialog. Successful revisions replace the current card and trigger compliance re-check through the existing workspace flow.

Scope boundaries:

- First version only supports single-article follow-up, not batch follow-up.
- No LLM key means an explicit error; there is no fake template fallback for follow-up revisions.
- Revised articles are not automatically appended to generation history runs, avoiding duplicate platform drafts in history detail.

## Verification

Latest checks:

- `pytest tests\test_pipeline.py -q -k "follow_up"`: passed, 4 tests.
- `pytest tests\test_pipeline.py -q -k "follow_up or compliance or generation_history"`: passed, 16 tests.
- `pytest tests\test_pipeline.py -q -k "compliance or config"`: passed, 10 tests.
- `pytest tests\test_pipeline.py -q -k "generation_history"`: passed, 4 tests.
- Frontend production build from `frontend/` with a temporary output directory: passed.

Known environment notes:

- PowerShell output may display Chinese text as mojibake in this workspace. Do not assume the file content is broken just because `Get-Content`, pytest paths, or shell output look garbled. For exact Chinese text, read files with an explicit UTF-8 path, for example `python -c "from pathlib import Path; print(Path('file').read_text(encoding='utf-8'))"`, or inspect escaped output with `.encode('unicode_escape')`.
- Pytest may warn about `.pytest_cache` write permissions on this Windows path; history tests still pass.
- Full backend test runs may hit unrelated environment-dependent failures around local frontend dist assumptions. In this workspace, `test_root_returns_frontend_dev_hint_when_dist_is_missing` fails when `frontend/dist` exists because Flask correctly serves the built app instead of the missing-dist JSON hint.
- Vite build currently reports a large chunk warning; this is not blocking, but later code splitting would be useful.

## Files To Know

Backend:

- `app.py`: generation API and history API routes.
- `pipeline/config.py`: runtime config defaults, environment overrides, and request config normalization.
- `pipeline/generation.py`: full draft generation and low-token article follow-up prompts.
- `pipeline/compliance/checker.py`: regex plus LLM compliance engine, mock mode, and in-memory cache.
- `pipeline/compliance/prompts.py`: condensed platform rule checklists and coverage constants.
- `pipeline/models.py`: history, follow-up, and generated-article relationships.
- `pipeline/repository.py`: history creation plus follow-up article creation and payloads.
- `tests/test_pipeline.py`: backend regression coverage.

Frontend:

- `frontend/src/components/GenerationHistoryPanel.vue`: history UI.
- `frontend/src/stores/workspace.ts`: shared generation run ID, restore-from-history flow, generation concurrency, and automatic compliance queue.
- `frontend/src/api/client.ts`: history API client methods.
- `frontend/src/types.ts`: history and follow-up TypeScript types.
- `frontend/src/components/SettingsDrawer.vue`: browser-local runtime settings, including compliance settings.
- `frontend/src/components/PlatformResultColumns.vue`: article cards, compliance highlighting, follow-up dialog, publish/export actions.
- `frontend/src/views/WorkspaceView.vue`: full-width history panel placement.
- `frontend/src/styles.css`: history panel styling.

## Next Recommended Work

- Add frontend Vitest coverage for history restore, filtering, and API error states.
- Add browser smoke testing for generate -> history appears -> restore to workspace.
- Consider lazy loading or manual chunks for Element Plus-heavy frontend bundles.
- Extend history later only after the current v1 is stable: batch jobs, publishing history, and image workflow records should probably become separate timelines or task records rather than being merged into generation history.
