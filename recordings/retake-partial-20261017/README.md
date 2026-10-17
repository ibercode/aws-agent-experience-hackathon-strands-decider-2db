# Incorrect readback / Correction only — recorded retake

This separate real-provider run was captured on 17 October 2026. The ATC exchange is a fictional script; the Decider decisions and Bedrock advisory are actual recorded inference. Public playback performs no new inference.

The session completed with a current published advisory, **8 Decider requests**, **3 Bedrock calls**, **15 activities**, and **5,150 recorded Bedrock tokens**. No runtime errors or incomplete-usage flag were recorded. The final communication result is `matches`, with a separate holding observation.

The [manifest](manifest.json) provides the sanitized recording's hash and size; [verification](verification.json) preserves the single-run checks. Four polled frames and 29 persisted allowed observations are retained. The first sampled frame arrived after the original readback; the complete saved event and decision timestamps remain available for the derived public timeline.

This retake is selected for the public player's incorrect-readback / Correction only option. It does not overwrite or erase the [original recording](../v3/incorrect-readback-v3-partial.json), which retains the live-advisory timeout, two associated error traces, later recovery, and incomplete token-accounting flag. Derived public assets explicitly record both source hashes when selecting this retake.

Raw records remain in the ignored private capture directory. This directory contains sanitized output only; owner, Cognito and infrastructure identifiers are excluded.
