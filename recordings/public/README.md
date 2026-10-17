# Public replay timeline

`v3/` is a derived playback dataset. It schedules real Strands Decider 2B and Amazon Bedrock results from the original durable timestamps of fictional scripted ATC scenarios. Building or playing it makes no model calls.

The original nine sampled recordings in [`../v3/`](../v3/) stay unchanged. The active incorrect-readback / Correction only case is the separately recorded clean [retake](../retake-partial-20261017/). Each derived bundle identifies its selected source by SHA-256; a retake also identifies the source it supersedes. The original timeout recording remains available for inspection.

## Generate

From the repository root:

```sh
backend/.venv/bin/python scripts/build_replay_timeline.py \
  --input recordings/v3 \
  --replace-from recordings/retake-partial-20261017 \
  --output recordings/public/v3
```

The output directory must be new. Input manifest hashes are verified, sources are never modified, and replacements must match the original scenario definition and preset. Additional `--replace-from` arguments can select explicitly reviewed, sanitized recordings in future builds. Raw private captures are not accepted by this builder; sanitize and review them first with `scripts/export_replays.py`.

## Frontend contract

The manifest retains `schemaVersion: atc-assistant-public-replay-manifest/1` and adds `timelineVersion: durable-timestamps/1`. Each entry contains:

- `id` / `recordingId`, `file`, `src`, SHA-256 and byte size.
- Scenario ID/version, title, description, objective, initial setup, preset and fictional `durationMs`.
- `recordingDurationMs`, which also includes the original model processing and capture time.
- The original execution-quality summary, source sample count, derived frame count and explicit retake selection.

Each selected bundle retains `schemaVersion: atc-assistant-public-replay/1`. Its `frames` array is ordered by `elapsedMs`; render `frame.view` with the existing `Session` presentation components. Frame provenance names the recorded transitions, selected observation snapshot and token-usage sample. Choose the last frame whose elapsed time is at or before the playback clock. Load one selected bundle at a time; importing the small manifest does not require loading all frames.

The frontend may replace `src` with a bundler-generated asset URL. The default `src` is a same-origin `/recordings/v3/` path. These are static files: public playback must not initialize Cognito, contact the application API or make inference requests.

## What the derived frames mean

- Events enter the timeline at their original `recordedAt`.
- Assessments and activities enter at `startedAt`. Until `endedAt`, they show pending/running status and exclude their later result, error, duration, usage and completion fields. Their real saved results appear at `endedAt`.
- The monitor is projected offline from only the evidence available at that time. It can therefore show an early recorded mismatch even when a slow poll missed that screen state. Corrected instructions reset the current comparison; historical issues remain.
- Aircraft position comes only from an allowed observation whose snapshot was already saved. The display holds that recorded position between updates. Simulation time advances at recorded anchors; hidden world state and interpolated movement are excluded. Observation freshness follows the same simulation-time rule as the application.
- Cumulative Bedrock token totals and partial-usage flags change only at original captured sample times. Before the first sample, usage is `null` and frame provenance says `not-yet-sampled`. The builder never divides final tokens among earlier calls or estimates intermediate totals.
- Completion and published advisory text remain gated by their original timestamps. The final frame must match the selected source's final events, assessments, activity, monitor and token totals.

These frames are a reconstruction from recorded timestamps, not a frame-exact browser video. Label the player **Recorded demonstration — no new inference** and metrics as recorded measurements. `providerMode: live` describes the original run. A `complete` quality value means clean execution; it does not assert that every experimental model judgment was correct. Preserved `unclear` decisions remain unclear.

The immutable source captures remain the authority for polling coverage. Derived pending intervals are supported by saved start/end timestamps; they must not be presented as additional browser observations.
