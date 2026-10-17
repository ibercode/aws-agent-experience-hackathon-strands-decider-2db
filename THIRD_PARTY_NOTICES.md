# Third-party notices

Reviewed on 17 October 2026 against the checked-in dependency locks and the pinned model/runtime metadata.

## Scope

The project's own application code, reusable Guardrails pattern, configuration and documentation are licensed under [Apache-2.0](LICENSE). Third-party components retain their original licenses. This document is an attribution and dependency inventory; it does not relicense those components or grant trademark rights.

The source repository includes dependency declarations and lockfiles. It excludes installed dependencies, virtual environments, fetched runtime repositories, model weights, training datasets, container images and build output. Those materials are obtained separately during installation or local container builds. Sanitized replay JSON contains fictional scripted communications and results of this project's model calls, not a redistribution of model weights or training datasets.

## Browser distribution

The web build does deliver third-party JavaScript to visitors. Preserve [the complete browser license notices](frontend/public/third-party-notices.txt) alongside the built site. Vite copies this public asset to `/third-party-notices.txt`. The file contains the full applicable license texts and public copyright attributions copied from the pinned packages, including generated build helpers.

| Component | Pinned version | License | Upstream |
| --- | --- | --- | --- |
| React and React DOM | 19.3.1 | MIT | [React](https://github.com/react/react) |
| Scheduler | 0.28.0 | MIT | [React](https://github.com/react/react) |
| oidc-client-ts | 3.5.0 | Apache-2.0 | [authTS](https://github.com/authts/oidc-client-ts) |
| jwt-decode | 4.0.0 | MIT | [jwt-decode](https://github.com/auth0/jwt-decode) |
| Vite core and generated helpers | 7.3.7 | MIT | [Vite](https://github.com/vitejs/vite) |
| Rollup core and generated helpers | 4.64.7 | MIT | [Rollup](https://github.com/rollup/rollup) |
| Rollup plugin helpers | Versions included in the Vite package | MIT | [Rollup plugins](https://github.com/rollup/plugins) |
| esbuild generated helpers | 0.28.2 | MIT | [esbuild](https://github.com/evanw/esbuild) |

The browser notices do not imply that the full build tools execute in the browser. They retain the notices for library code and generated helper code. The installed oidc-client-ts npm package supplies its complete Apache license and no separate NOTICE file.

## Python dependencies

The following inventory combines [the API lock](backend/requirements-linux-arm64.lock), [the Linux Decider lock](services/decider/requirements-linux-arm64.lock) and [the native macOS Decider lock](services/decider/requirements-macos.lock). Versions and package-level license declarations were checked against installed metadata. Runtime dependencies are installed separately; their license and NOTICE files must stay with any redistributed packages or container images. This table is not a replacement for those complete upstream notices, especially for binary wheels with bundled native libraries.

| Package | Pinned version/revision | Declared license / scope |
| --- | --- | --- |
| `accelerate` | 1.15.0 | Apache-2.0 |
| `annotated-doc` | 0.0.5 | MIT |
| `annotated-types` | 0.8.0 | MIT |
| `anyio` | 4.15.1 | MIT |
| `attrs` | 26.1.0 | MIT |
| `boto3` | 1.43.114 | Apache-2.0 |
| `botocore` | 1.43.114 | Apache-2.0 |
| `certifi` | 2026.7.22 | MPL-2.0 |
| `cffi` | 2.1.1 | MIT-0 |
| `click` | 8.5.0 | BSD-3-Clause |
| `cryptography` | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| `docstring-parser` | 0.18.0 | MIT |
| `fastapi` | 0.143.3 | MIT |
| `filelock` | 4.2.0 | MIT |
| `fsspec` | 2026.9.0 | BSD-3-Clause |
| `h11` | 0.16.0 | MIT |
| `hf-xet` | 1.7.0 | Apache-2.0 |
| `httpcore` | 1.0.9 | BSD-3-Clause |
| `httpcore2` | 2.13.1 | BSD-3-Clause |
| `httptools` | 0.9.0 | MIT |
| `httpx` | 0.28.1 | BSD-3-Clause |
| `httpx2` | 2.13.1 | BSD-3-Clause |
| `huggingface-hub` | 1.33.0 | Apache-2.0 |
| `idna` | 3.20 | BSD-3-Clause |
| `jinja2` | 3.1.6 | BSD-3-Clause |
| `jmespath` | 1.1.0 | MIT |
| `jsonschema` | 4.26.0 | MIT |
| `jsonschema-specifications` | 2025.9.1 | MIT |
| `markdown-it-py` | 4.2.0 | MIT |
| `markupsafe` | 3.0.4 | BSD-3-Clause |
| `mcp` | 2.1.1 | MIT |
| `mcp-types` | 2.1.1 | MIT |
| `mdurl` | 0.1.2 | MIT |
| `mpmath` | 1.3.0 | BSD-3-Clause |
| `networkx` | 3.7 | BSD-3-Clause |
| `numpy` | 2.5.4 | BSD-3-Clause core; see binary-component note below |
| `opentelemetry-api` | 1.45.1 | Apache-2.0 |
| `opentelemetry-instrumentation` | 0.66b1 | Apache-2.0 |
| `opentelemetry-instrumentation-threading` | 0.66b1 | Apache-2.0 |
| `opentelemetry-sdk` | 1.45.1 | Apache-2.0 |
| `opentelemetry-semantic-conventions` | 0.66b1 | Apache-2.0 |
| `packaging` | 26.3 | Apache-2.0 OR BSD-2-Clause |
| `peft` | 0.21.0 | Apache-2.0 |
| `psutil` | 7.2.2 | BSD-3-Clause |
| `pycparser` | 3.11 | BSD-3-Clause |
| `pydantic` | 2.14.1 | MIT |
| `pydantic-core` | 2.50.1 | MIT |
| `pydantic-settings` | 2.16.0 | MIT |
| `pygments` | 2.21.0 | BSD-2-Clause |
| `pyjwt` | 2.15.1 | MIT |
| `python-dateutil` | 2.9.0.post0 | Apache-2.0 OR BSD-3-Clause |
| `python-dotenv` | 1.2.4 | BSD-3-Clause |
| `python-multipart` | 0.0.32 | Apache-2.0 |
| `pyyaml` | 6.0.3 | MIT |
| `referencing` | 0.37.0 | MIT |
| `regex` | 2026.9.29 | Apache-2.0 AND CNRI-Python |
| `rich` | 15.0.0 | MIT |
| `rpds-py` | 2026.9.1 | MIT |
| `s3transfer` | 0.19.2 | Apache-2.0 |
| `safetensors` | 0.8.0 | Apache-2.0 |
| `setuptools` | 84.0.0 | MIT |
| `shellingham` | 1.5.4 | ISC |
| `six` | 1.17.0 | MIT |
| `sse-starlette` | 3.5.0 | BSD-3-Clause |
| `starlette` | 1.8.0 | BSD-3-Clause |
| `strands-agents` | 1.61.1 | Apache-2.0 |
| `strands-decider` | 930e6d5de16309be32579f5631a7369a3322140c | Apache-2.0 |
| `sympy` | 1.14.0 | BSD-3-Clause |
| `tokenizers` | 0.23.3 | Apache-2.0 |
| `torch` | 2.7.1, 2.7.1+cpu | BSD-3-Clause core; bundled components retain additional notices |
| `tqdm` | 4.70.1 | MPL-2.0 AND MIT |
| `transformers` | 5.17.0 | Apache-2.0 |
| `truststore` | 0.10.5 | MIT |
| `typer` | 0.27.3 | MIT |
| `typing-extensions` | 4.16.0 | PSF-2.0 |
| `typing-inspection` | 0.4.4 | MIT |
| `urllib3` | 2.8.0 | MIT |
| `uvicorn` | 0.54.0 | BSD-3-Clause |
| `uvloop` | 0.23.0 | MIT AND Apache-2.0 |
| `watchdog` | 6.0.0 | Apache-2.0 |
| `watchfiles` | 1.3.0 | MIT |
| `websockets` | 17.2 | BSD-3-Clause |
| `wrapt` | 2.5.1 | BSD-2-Clause |

### License details requiring separate treatment

- **certifi** uses MPL-2.0. **tqdm** declares MPL-2.0 AND MIT. Keep their original notices; when distributing covered source or binaries, retain the recipients' access to the covered source under the applicable terms. These terms do not relicense this project's independent files. See [certifi's license](https://github.com/certifi/python-certifi/blob/master/LICENSE), [tqdm's license](https://github.com/tqdm/tqdm/blob/master/LICENCE) and [Mozilla's MPL guidance](https://www.mozilla.org/en-US/MPL/2.0/FAQ/).
- **regex** declares Apache-2.0 AND CNRI-Python; **typing-extensions** uses PSF-2.0. Preserve their complete package license texts rather than replacing them with the project's Apache license.
- **NumPy** has a BSD-3-Clause core and separately licensed bundled components. The inspected macOS wheel's license file also identifies OpenBLAS and GCC runtime libraries under `GPL-3.0-or-later WITH GCC-exception-3.1`. Binary contents vary by platform; retain the actual wheel's full licenses and exceptions. The package-level metadata alone is not a complete binary inventory. See [NumPy's license](https://github.com/numpy/numpy/blob/main/LICENSE.txt) and [the GCC runtime exception](https://www.gnu.org/licenses/gcc-exception-3.1.html).
- **PyTorch** includes a BSD-3-Clause core plus other notices in its supplied LICENSE and NOTICE. Keep both files when distributing a wheel or image containing it. This repository does not vendor PyTorch or NumPy binaries.
- **uvloop**, **cryptography**, **packaging** and **python-dateutil** have combined or alternative license declarations shown above; the wording must not be reduced to a blanket claim that all dependencies are Apache-2.0.

## Decider runtime and model artifacts

The model and source revisions are recorded in [services/decider/model.json](services/decider/model.json):

| Material obtained separately | Pin | License / source |
| --- | --- | --- |
| Strands Decider runtime | `930e6d5de16309be32579f5631a7369a3322140c` | [Apache-2.0 license](https://github.com/strands-labs/strands-decider/blob/930e6d5de16309be32579f5631a7369a3322140c/LICENSE), [upstream third-party notices](https://github.com/strands-labs/strands-decider/blob/930e6d5de16309be32579f5631a7369a3322140c/THIRD_PARTY_NOTICES.md) |
| Strands Decider 2B checkpoint, Qwen3.5 v1 | `216d1ccb46a9e9b036eb9187b248db98480f77d4` | [Apache-2.0 model license and provenance notes](https://huggingface.co/StrandsAgents/strands-decider-2B-qwen3.5-v1-2610/blob/216d1ccb46a9e9b036eb9187b248db98480f77d4/LICENSE.md) |
| Qwen3.5-2B-Base weights | `b1485b2fa6dfa1287294f269f5fb618e03d52d7c` | [Apache-2.0 base-model license](https://huggingface.co/Qwen/Qwen3.5-2B-Base/blob/b1485b2fa6dfa1287294f269f5fb618e03d52d7c/LICENSE) |

These are references and download/build inputs, not bundled weights or vendored runtime source in this repository. The model publisher's license also documents training sources with separate terms; the project does not redistribute those datasets. Do not infer a dataset redistribution license from the model's Apache-2.0 designation.

The runtime's upstream notice identifies its adaptation of a Transformers Qwen3.5 MPS kernel. That upstream attribution is reproduced in full below for users building the runtime. The application and reusable guard communicate through the runtime's API; they do not copy the model implementation into project source.

**Container builders:** keep the model's LICENSE.md, the pinned base-model LICENSE, the runtime's THIRD_PARTY_NOTICES.md, and each installed package's licenses/NOTICE with any redistributed image. This repository's inventory is not a complete notice bundle for a Docker image: Debian, CPython and platform-specific native libraries retain additional terms. Do not remove their supplied license metadata when minimizing an image.

Amazon Bedrock and Amazon Nova are accessed as AWS services, not redistributed model weights. Their service terms are separate from this repository's source license.

## Frontend build dependencies and infrastructure tools

[frontend/package-lock.json](frontend/package-lock.json) pins the full build graph and records Apache-2.0 for this project's root package. Dependency entries may omit license fields, so the locally installed package license files were inspected. Besides the browser components above, the inspected build packages declare MIT, ISC, BSD-3-Clause, Apache-2.0 and CC-BY-4.0. In particular:

- TypeScript 5.9.3 and baseline-browser-mapping 2.11.29 declare Apache-2.0. TypeScript also supplies ThirdPartyNoticeText.txt.
- caniuse-lite 1.0.30001816 is browser-support data under [CC-BY-4.0](https://github.com/browserslist/caniuse-lite/blob/main/LICENSE), used by the build toolchain. Its data is not project-authored Apache-2.0 material. If distributing that dataset, preserve its license and attribution.
- The installed Babel, esbuild and Rollup package families and React type packages declare MIT; source-map-js declares BSD-3-Clause; several small utilities declare ISC. Vite and Rollup also supply bundled-dependency notices in their own LICENSE.md files.
- Optional platform-specific packages in the lock may not be installed on a given build host. Review the actual package notices before redistributing a toolchain for another platform. The source repository does not include those optional binaries.

Terraform configuration is project source. The cached, pinned [AWS provider 6.69.1](https://github.com/hashicorp/terraform-provider-aws/blob/v6.69.1/LICENSE) and [Random provider 3.9.1](https://github.com/hashicorp/terraform-provider-random/blob/v3.9.1/LICENSE) each supply MPL-2.0. Terraform executables, provider binaries, Docker base-image contents and AWS service SDK installations are separate materials under their respective upstream terms; a source-code license for this project does not relicense them. Provider versions are pinned in the Terraform lockfiles, and downloaded providers are ignored.

## Illustration, symbols and demonstration material

[atc-pilot-hero.png](frontend/src/assets/atc-pilot-hero.png) was generated specifically for this project with the built-in image_gen tool on 17 October 2026. [Its provenance note](frontend/src/assets/atc-pilot-hero.txt) records the method and prompt. It depicts fictional illustrative people. The matching portraits are CSS views of the same asset; no separate stock-photo or icon-library dependency is included. The application symbol, schematic and UI icons are project source. Product names identify the services used and do not imply sponsorship or grant trademark rights.

The [README overview image](docs/assets/atc-assistant-overview.png) is a screenshot of this project's landing-page illustration and interface, supplied by the project owner. It uses the same fictional portraits and is retained unchanged; the original generated asset and its provenance remain available above.

The scenarios and sanitized replay records concern fictional scripted exchanges. They are not third-party incident transcripts or recordings of real air traffic control operations. Model outputs and AI-generated imagery are provided as project demonstration material; this notice does not promise copyright exclusivity in generated output.

## Upstream attribution notices retained for runtime builders

The following notices are reproduced from the installed packages and the pinned Decider runtime. They identify upstream components; they do not mean those package implementations are vendored in this source repository. The full Apache-2.0 license is in [LICENSE](LICENSE); the Decider notice also includes its original license text.

### boto3

```text
boto3
Copyright 2013-2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
```

### botocore

```text
Botocore
Copyright 2012-2022 Amazon.com, Inc. or its affiliates. All Rights Reserved.

----

Botocore includes vendorized parts of the requests python library for backwards compatibility.

Requests License
================

Copyright 2013 Kenneth Reitz

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

Botocore includes vendorized parts of the urllib3 library for backwards compatibility.

Urllib3 License
===============

This is the MIT license: http://www.opensource.org/licenses/mit-license.php

Copyright 2008-2011 Andrey Petrov and contributors (see CONTRIBUTORS.txt),
Modifications copyright 2012 Kenneth Reitz.

Permission is hereby granted, free of charge, to any person obtaining a copy of this
software and associated documentation files (the "Software"), to deal in the Software
without restriction, including without limitation the rights to use, copy, modify, merge,
publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons
to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.

Bundle of CA Root Certificates
==============================

***** BEGIN LICENSE BLOCK *****
This Source Code Form is subject to the terms of the
Mozilla Public License, v. 2.0. If a copy of the MPL
was not distributed with this file, You can obtain
one at http://mozilla.org/MPL/2.0/.

***** END LICENSE BLOCK *****
```

### strands-agents

```text
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
```

### Strands Decider runtime — upstream THIRD_PARTY_NOTICES.md

The following is the complete upstream notice at runtime revision `930e6d5de16309be32579f5631a7369a3322140c`.

# Third-party notices

This repository contains code adapted from third-party projects. The notices required by
their licences are below. Each notice names the file that carries the adapted code, the
project it comes from and what was changed.

## Hugging Face Transformers

`src/strands_decider/mps_kernels.py` adapts `torch_chunk_gated_delta_rule` from the Qwen3.5 model
code of Transformers 5.17 (`transformers/models/qwen3_5/modeling_qwen3_5.py`).

Copyright 2025 The Qwen Team and The HuggingFace Inc. team. All rights reserved.

Licensed under the Apache License, Version 2.0. Changes made: the two triangular solves
of the reference are replaced by one recursive block inversion of the unit-lower-triangular
system, whose result is applied to both right-hand sides; the function was restructured
around that change and its variables renamed. The text of the licence follows.

```
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   APPENDIX: How to apply the Apache License to your work.

      To apply the Apache License to your work, attach the following
      boilerplate notice, with the fields enclosed by brackets "[]"
      replaced with your own identifying information. (Don't include
      the brackets!)  The text should be enclosed in the appropriate
      comment syntax for the file format. We also recommend that a
      file or class name and description of purpose be included on the
      same "printed page" as the copyright notice for easier
      identification within third-party archives.

   Copyright [yyyy] [name of copyright owner]

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
```
