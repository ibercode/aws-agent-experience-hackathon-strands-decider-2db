# Local Strands Decider 2B runtime

This runs the official Qwen3.5-based Strands Decider 2B checkpoint, with the upstream source and model revisions pinned in `model.json`. It is the decision model; the training API separately runs a Strands Agents SDK instructor using Amazon Bedrock.

On an Apple Silicon Mac with Python 3.12 and sufficient free memory:

```sh
uv venv --python 3.12 services/decider/.venv
uv pip install --python services/decider/.venv/bin/python -r services/decider/requirements-macos.lock
services/decider/.venv/bin/python services/decider/prepare.py
services/decider/.venv/bin/python services/decider/serve.py
```

Preparation downloads a public checkpoint and verifies its SHA-256 manifest. First launch downloads the Qwen base weights (approximately 4.5 GB). Models, caches and the virtual environment stay in ignored directories. No Hugging Face token is needed. The base revision is recorded in the checkpoint's provenance and checked during preparation.

The local server defaults to `127.0.0.1:8099`. Apple Silicon defaults to MPS; `DECIDER_DEVICE=cpu` selects CPU. The container sets `DECIDER_HOST=0.0.0.0` so the API can reach it within the task network. Its security group must permit port 8099 only from the API security group.

Requests that exceed the checkpoint's 4,096-token window are rejected rather than silently truncated. The application serialises requests. This unauthenticated loopback service must not be exposed directly to the public internet.

- [Official inference documentation](https://github.com/strands-labs/strands-decider/blob/930e6d5de16309be32579f5631a7369a3322140c/docs/inference.md)
- [Published model](https://huggingface.co/StrandsAgents/strands-decider-2B-qwen3.5-v1-2610/tree/216d1ccb46a9e9b036eb9187b248db98480f77d4)

## Linux ARM64 containers

Both Dockerfiles use a digest-pinned Python 3.12 / Debian Trixie base, pinned Linux ARM64 Python dependencies, a non-root runtime user, and one worker. All setuid/setgid executable bits are removed from the final filesystem. Build from the repository root:

```sh
# Download public artifacts once if this machine has no model cache yet.
services/decider/.venv/bin/python services/decider/prepare.py --include-base
services/decider/.venv/bin/python services/decider/prepare_image.py
docker buildx build --platform linux/arm64 --provenance=false --load \
  --build-context decider_models=.data/container-models \
  -f services/decider/Dockerfile -t clearance-gap-decider:aws-local .
docker buildx build --platform linux/arm64 --provenance=false --load \
  -f backend/Dockerfile -t clearance-gap-api:aws-local .
```

The model staging script verifies the checkpoint manifest, provenance and pinned base-file SHA-256 hashes. It copies only public model artifacts to a separate, ignored Docker context. The root context uses an allowlist, excluding `.env`, Terraform state, cloud credentials, local databases, reports and virtual environments. There are no credentials in either image.

The Decider image contains the checkpoint and base model weights (about 4.5 GB before runtime dependencies). Hugging Face offline mode prevents downloads at runtime; the public cache is not mounted from the host. The image can run with no network egress. Port 8099 `/health` becomes ready only after model loading completes. ECS should allow a five-minute startup grace period.

Use ARM64 Linux tasks. The API serves port 8000 and `/api/health`; the model serves port 8099 and `/health`. Fargate requires CPU inference because it has no GPU support. The official CPU engine promotes model weights to float32, so begin with 4 vCPU and 16 GiB RAM for Decider, then measure actual memory and latency before reducing it. The text torso alone expands from 3.505 GiB to 7.010 GiB, plus adapters, runtime and inference buffers; a local 6 GiB startup test exhausted its memory cap. `OMP_NUM_THREADS` and `MKL_NUM_THREADS` default to 4. Keep one model worker: extra workers would duplicate its memory.

Both images support a read-only root filesystem; provide a writable `/tmp` task volume for libraries that create temporary files. The Dockerfiles declare `VOLUME /tmp` and set its owner to UID/GID 10001 with mode 0700. Use that exact container path in the ECS mount configuration so the data plane preserves the image's volume ownership. Pass AWS permissions through ECS task roles, Cognito and storage settings through task environment variables, and never bake an AWS profile or keys into the images. Public access belongs at the authenticated application edge, not at the Decider endpoint.

The Linux dependency lock was resolved for Python 3.12 and `aarch64-unknown-linux-gnu`; it is separate from the native macOS lock. Torch uses the official CPU wheel index and the runtime source is pinned to the commit in `model.json`. Rebuild the API image after backend code changes.

## Container security review — 2026-10-17

Both final `demo-20261017-v2` images completed ECR basic scanning with the same **3 High, 9 Medium and 3 Low findings** listed below. This is the actual v2 inventory, rather than a prediction from the earlier Bookworm scan. The affected runtime packages are glibc `2.41-12+deb13u4` and zlib `1:1.3.dfsg+really1.3.1-1+b1`; both are also the current Trixie apt candidates, so a normal package upgrade supplies no fix at this review date.

The preceding Bookworm image had 7 High, 2 Medium and 2 Low findings. Moving to Trixie obtained packaged util-linux fixes for CVE-2026-53613, CVE-2026-53615 and CVE-2026-13595. The completed v2 scans contain no util-linux findings, but identify additional glibc issues, so the lower High count does not imply all risks were removed. See [Debian's advisory](https://security-tracker.debian.org/tracker/DSA-6442-1) and [partition metadata issue](https://security-tracker.debian.org/tracker/CVE-2026-53615).

Review evidence: application and model-serving source was searched for the affected functions and dynamic native invocation; the model export utilities are not part of the serving path. Undefined ELF-symbol imports were inspected across 92 API and 128 Decider native libraries/extensions under `/opt/venv` and `/usr/local/lib`. No imports were found for `strfmon`, `strfmon_l`, `ns_printrrf`, `ns_printrr`, `fp_nquery`, `gzprintf`, `gzvprintf`, `gzwrite`, `wordexp`, `wordfree`, `tsearch`, `tdelete`, or `iconv`. Generic `fopen` imports do exist and are assessed separately below. Static inspection cannot prove the absence of every indirect or future call path.

| Actual v2 finding | Deployment relevance and residual risk |
| --- | --- |
| [CVE-2026-19499](https://security-tracker.debian.org/tracker/CVE-2026-19499) — High | glibc monetary formatting through `strfmon`/`strfmon_l` with particular width padding. No application call or native import was identified. The product does not expose native monetary formatting. Debian marks Trixie unfixed; the unstable fixed package is `2.43-5`. |
| [CVE-2026-5435](https://security-tracker.debian.org/tracker/CVE-2026-5435) — High; [CVE-2026-6238](https://security-tracker.debian.org/tracker/CVE-2026-6238) — Medium | Deprecated native DNS debugging/printing functions, not the ordinary DNS lookup path. No affected imports or application calls were identified. Debian marks Trixie unfixed; the unstable fixed package is `2.43-3`. |
| [CVE-2026-85091](https://security-tracker.debian.org/tracker/CVE-2026-85091) — High | zlib's native `gzprintf`/`gzvprintf` buffered file-writing path. No affected imports or caller-controlled stream reaching that interface were identified. Ordinary Python compression uses a different API; this is retained as a residual dependency finding rather than called a false positive. Debian still marks zlib unfixed. |
| [CVE-2026-18374](https://nvd.nist.gov/vuln/detail/CVE-2026-18374) — Medium | glibc `fopen` mode strings containing an attacker-controlled empty `,ccs=` encoding suffix. Native dependencies import generic `fopen`, but application input is not forwarded as a native mode string and no `ccs` forwarding path was identified. Review again if configurable file handling or native FFI is introduced. |
| [CVE-2026-8674](https://security-tracker.debian.org/tracker/CVE-2026-8674) — Medium | Resolver initialization with an excessive DNS search domain. DNS is used, but search-domain configuration is supplied by the ECS/VPC environment, not by application users. `LOCALDOMAIN` is unset in the images; the task role and application cannot change VPC DHCP settings. Avoid adding user-controlled resolver environment settings. |
| [CVE-2026-77117](https://nvd.nist.gov/vuln/detail/CVE-2026-77117), [CVE-2026-80489](https://nvd.nist.gov/vuln/detail/CVE-2026-80489) — Medium | Native `iconv` conversion of specific SHIFT_JISX0213/EUC_JISX0213 sequences. No native `iconv` imports were identified in the inspected application libraries; the API/scenarios use UTF-8. No application encoding selector exposes these conversion paths. |
| [CVE-2026-89092](https://nvd.nist.gov/vuln/detail/CVE-2026-89092) — Medium | Requires the `nscd` daemon processing a large malicious DNS response. The executable is absent and no such daemon is started by these single-process application containers. |
| [CVE-2026-19542](https://nvd.nist.gov/vuln/detail/CVE-2026-19542) — Medium | Native `tsearch`/`tdelete` trees with roughly a million nodes. Neither affected interface was imported by the inspected libraries or called by application source. Python application collections do not expose this native tree API. |
| [CVE-2026-6791](https://nvd.nist.gov/vuln/detail/CVE-2026-6791) — Medium; [CVE-2026-6368](https://nvd.nist.gov/vuln/detail/CVE-2026-6368) — Low | Native shell-style `wordexp`/`wordfree` processing. No imports or application calls were identified; the application does not invoke a shell to interpret trainee messages or scenario input. |
| [CVE-2026-86805](https://security-tracker.debian.org/tracker/CVE-2026-86805) — Medium; [CVE-2026-95818](https://security-tracker.debian.org/tracker/CVE-2026-95818) — Low | glibc loader issues requiring special setuid/setgid execution conditions. All such bits were removed and checked absent in the final images. Tasks run as UID 10001 with all capabilities dropped and a read-only root filesystem. |
| [CVE-2026-97399](https://nvd.nist.gov/vuln/detail/CVE-2026-97399) — Low | Faulty Power8-specific glibc optimization. These images and tasks are ARM64. |

No exposed application path to the three High findings was identified by this scoped review, and current stable vendor packages supply no further fix. This supports proceeding with the restricted hackathon prototype while retaining the findings as documented residual risk; it is not a claim of zero vulnerabilities or a complete security audit. Re-scan and review when vendor updates appear, the base digest changes, or the application adds native formatting, encoding, file handling, subprocesses or privileged operations. Do not enable privileged mode or restore executable privilege bits to bypass an application error.
