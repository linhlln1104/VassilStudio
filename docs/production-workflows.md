# Production projects and batches

The production domain keeps authoring/review metadata in
`data/production/production.sqlite3` (SQLite WAL). Reference snapshots and completed
take WAVs live in sibling `references/` and `audio/` directories. Back up the entire
production directory with the database using an SQLite-aware snapshot, or stop the
application first. Do not back up only the main `.sqlite3` file while WAL writers run.

Projects are visible to their owner, administrators, and explicit members. Global
API scopes are checked in addition to membership: editors write scripts, reviewers
review/select takes, and the owner/admin manages membership. Project exports require
project read access. Account/key membership uses stable `principal_id` values.

## Author, compare and approve

1. `POST /api/v1/projects` with `{ "name": "Training" }`.
2. `POST /api/v1/projects/{project_id}/segments` with `external_id`, `text`,
   `language`, `voice_id` and optional `model_id`.
3. Edit with `PATCH .../segments/{segment_id}` and `expected_revision`. A stale
   revision returns 409. Script snapshots remain available at `/revisions`.
4. `POST .../segments/{segment_id}/takes` with `expected_revision` and optional
   model/voice/step/speed overrides. Multiple takes can be auditioned side by side
   from the returned retained audio URLs. Supply `Idempotency-Key` to safely retry.
5. `PATCH /projects/{project_id}/takes/{take_id}/review` with `expected_revision`,
   `status` (`approved`, `rejected`, or `pending`) and optional `note`.
6. `PUT .../segments/{segment_id}/selection` with `expected_revision` and `take_id`.
   Editing the script clears its selection; a take for an older script cannot be
   silently selected for the new version.
7. `GET /projects/{project_id}/export` returns selected, approved WAVs and a manifest.

Every take freezes the original script, dictionary revision/hash, normalized spoken
text, voice audio/transcript and resolved model deployment/options before it enters
the background dispatcher. Completed audio is copied to production-owned storage;
TTS job cleanup does not delete an approved production asset. Export verifies hashes.
Take review decisions are retained as immutable local review records.

## Pronunciation dictionaries

`GET/PUT /projects/{project_id}/dictionary` reads or updates
`{ expected_revision, entries: [{ source, replacement, language? }] }`.
`POST .../dictionary/preview` accepts `{text, language}`. `/dictionary/revisions`
returns history. Substitution is literal, case-sensitive, at word boundaries and
single-pass (a replacement is never interpreted as another rule). Longer matches
win; a language-specific entry overrides an entry without a language. This is a
pronunciation text substitution feature, not SSML or a regex execution surface.

## CSV/JSON batch workflow

`POST /api/v1/batches/analyze` accepts one source:

```json
{
  "project_id": "project-id",
  "name": "Lessons",
  "defaults": {"voice_id": "voice-id", "language": "vi", "model_id": "zipvoice-vi"},
  "rows": [{"external_id": "lesson-001", "text": "Xin chào."}]
}
```

Use `csv_text` instead of `rows` for server-side CSV parsing. Headers are
`external_id,text,language,voice_id,model_id,num_steps,speed`; only the first two are
required if defaults supply the voice. Quoted commas/newlines and UTF-8 BOM are
supported. IDs retain leading zeroes. Duplicate IDs within a batch or already in
the project are rejected; creating another take for an existing segment is the
explicit regeneration path. Unknown columns, including callback URLs, are rejected.
Limits are 10,000 rows and 10 MB of input text; per-item rendered text follows the
configured TTS text limit.

Analyze returns normalized rows, individual errors/warnings, and a `preflight_token`.
Submit the same input plus this token to `POST /api/v1/batches`; changed dictionary,
deployment or other validation results produce 409 and require fresh analysis.
`Idempotency-Key` makes repeated submission return the original batch. Creation
commits all items together without filling the inference queue in the HTTP request.

The API's background dispatcher reconciles jobs and submits at most four pending
items per pass. Queue-full leaves items pending on disk. Stable take idempotency keys
recover the window where a queue job was accepted but its ID was not yet committed.
SQLite serializes concurrent dispatchers. After restart the dispatcher resumes pending
items; inference still belongs to the configured TTS job worker.

Poll `GET /batches/{batch_id}` and `/items?limit=100&offset=0`. Item records contain
original external ID, segment/take/job IDs, status and review state. Retry failed
items with `POST /batches/{batch_id}/retry-failed`, optionally `{item_ids:[...]}`;
successful takes remain unchanged and previous failed takes remain in history.
`POST .../cancel` immediately cancels pending rows and requests cancellation of active
jobs using their existing safe-point semantics.

`GET /batches/{batch_id}/export` packages each item's approved current take without
requiring project selection. Filenames are generated safely; `manifest.json` preserves
original external IDs, script/deployment provenance, checksums, review decisions and
excluded take IDs. `approved_only=false` explicitly exports unapproved candidates for
internal review. Empty eligible exports return 409. Archive staging files are removed
after the HTTP response. No row-supplied URL is fetched or called.

This implementation is a local SQLite production system. Deploy the API and external
workers on one host/shared local data directory; it is not a distributed object-store
or PostgreSQL deployment. Candidate/approved assets remain until an explicit future
production retention policy is introduced; job retention is separate.
