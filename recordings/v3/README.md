# Recorded live-model demonstrations — scenario version 3

Nine real-provider runs captured from the deployed application on 17 October 2026. The controller and pilot exchanges are fictional scripts. These files contain actual Strands Decider 2B decisions and Amazon Bedrock results, not real incident recordings.

This is the original captured dataset, retained as test evidence. The deployed public player uses the separately derived [active catalog](../public/v3/manifest.json), including a clean retake of the one degraded case; the original recording files here remain unchanged. The authenticated judges’ workspace is separate at `/live`. Opening these JSON files performs no inference.

See [manifest.json](manifest.json) for file hashes and sizes, and [verification.json](verification.json) for the recorded test outcomes.

| Scenario | Controller response | Final readback | Physical evidence | Activities | Runtime result |
|---|---|---|---|---|---|
| Incorrect readback | Correction + observation | matches | holding | 35 | Clean |
| Incorrect readback | No correction | mismatch | holding | 18 | Clean |
| Incorrect readback | Correction only | matches | holding | 32 | Recovered after live-advisory timeout |
| Missing evidence | Correction + observation | matches | holding | 44 | Clean |
| Missing evidence | No correction | mismatch | unverified | 12 | Clean |
| Missing evidence | Correction only | matches | unverified | 14 | Clean |
| Words versus actions | Correction + observation | unclear | holding | 31 | Clean |
| Words versus actions | No correction | matches | runway entered | 16 | Clean |
| Words versus actions | Correction only | unclear | holding | 17 | Clean |

All nine sessions completed and published a current final advisory. Eight had no runtime errors. Incorrect readback / Correction only contains two trace errors caused by one 45-second live-advisory deadline expiry; its final invocation recovered and published. This recording is explicitly marked `degraded`, and its Bedrock usage remains partial. Its failure evidence has not been removed or replaced.

Words versus actions / Correction only and Correction + observation ended with an amber readback status. For “stop immediately; hold position” versus “Stopping, holding position,” Decider selected `unclear` with confidence `0.3593`. The separate aircraft observation showed the aircraft stopped. These are preserved experimental model outcomes, not runtime failures. A `complete` recording quality flag means execution completed cleanly; it does not mean every model judgment matched the intended scenario interpretation.

The runs contain **219 activities**, **97 Decider requests** and **51 Bedrock calls**. Median completed Decider request RTT was **3.68 seconds**. Recorded Bedrock usage totals **97,439 tokens**; one run has incomplete accounting, so this is not a complete billing total or a dollar-cost estimate.

## Playback contract

- `frames`: sampled persisted session views, including actual decision outputs, pending/completed activity states, metrics and evidence. `elapsedMs` is observed wall time from the original start. The simulation clock may stop while assessment continues.
- `recordedObservations`: every persisted scenario-allowed observation, with its original save/observation time and freshness. Hidden world state is excluded. A pre-start observation may have a negative elapsed offset.
- The final frame contains the complete event, assessment and activity records and their original timestamps. The separate derived catalog uses these timestamps to schedule replay without additional model calls. Do not invent missing decisions or intermediate cumulative token usage.
- Polling can miss short display transitions. In particular, the missing-evidence / Correction only capture has four sampled frames; its original mismatch decision is retained in the final assessment history. Frame gaps and observed-start coverage are explicit in every summary.
- Render `Recorded demonstration — no new inference` and label metrics as recorded measurements. Original `providerMode: live` describes the captured run; it must not be shown as a currently connected model.
- The public player must load only static assets and remain usable when the API and Decider services are stopped. Keep Cognito and all API/model requests in the separate Live Demo path.

## Privacy and provenance

Owner identifiers, Cognito data, infrastructure references and raw provider exception details are excluded. Session/event/decision/activity IDs are remapped consistently. Scenario hashes and model versions are retained. Raw captures remain under ignored `.data/recordings/` and are not part of this public dataset.

The first six recordings used a Query/META revision check; the final three used META-before/Query/META-after. Independent checks found no inconsistent frames in the first six. Each bundle records its actual consistency strategy.

Generate a new dataset with `scripts/record_replays.py` and `scripts/export_replays.py`; do not overwrite these results or present modified values as measured results.
