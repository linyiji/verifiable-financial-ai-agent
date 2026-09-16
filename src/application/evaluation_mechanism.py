"""WP06 frozen offline mechanism evidence; no runtime registration or I/O.

Only evaluate_mechanism admits the four-member cohort. The smaller pure
predicates support isolated contract controls and grant no cohort admission.
Inputs to the cohort entry are exactly manifest, envelopes, snapshots and
schema_pins. Envelope/snapshot arrays contain exact UTF-8 file bytes or None.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

from src.application import evaluation_input as wp05

FROZEN_MANIFEST = {'schema_version': 'vefin-evaluation-cohort/v1',
 'cohort_policy_id': 'WP06_LOCAL_READY_MECHANISM_COHORT_V1',
 'cohort_class': 'MECHANISM_VALIDATION_COHORT',
 'member_case_ids': ['sha256:201b754ffcccbacdb57299066d4d75977a4926998a0b818628377c7b1d175c6b',
                     'sha256:707dd815a56f67782ad9539924341be8c81ac004d977364d1ccfa39c888bd1c3',
                     'sha256:9e309b00743b3ba56cf38a32264171f876f4fc60ebfadc8046a6652b97bc8bf8',
                     'sha256:e1de89f410e4cc298ef4b9b6c916aaada234893f7ea3727e035a91679c137500'],
 'member_envelope_digests': ['sha256:2de3c57ff4d340074badcf63e41b35faaec1cdacba2bcb5a1806fbaa8ac70d96',
                             'sha256:1d22934ba72749bd7b8c8d5dd4c6b48d9a3f69e6cae5178d0c7cd2a4a3cdaebd',
                             'sha256:fa2cb5dd020afee3602f5bc67fb1545e596f92f2e607fb2369a6b52ff12d26ba',
                             'sha256:4e63fcded0de9d82ef8abc4d331c791ca143eac155b3b724dae561af05f216ce'],
 'member_source_scopes': [{'namespace': {'kind': 'DETACHED_OWNER_SNAPSHOT',
                                         'anchor_digest': 'sha256:a1e890b0205cf12cce5e1ac3989ffbededc9d3c796841c23d3df3627d18b775d'},
                           'component_scopes': ['RETAINED_LOCAL_FIXTURE', 'SYNTHETIC_CONTEXT'],
                           'classification': 'LOCAL_SYNTHETIC',
                           'source_manifest': [{'source_namespace': {'anchor_digest': 'sha256:a1e890b0205cf12cce5e1ac3989ffbededc9d3c796841c23d3df3627d18b775d',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Blob',
                                                'source_id': 'sha256:d1a6766540803f224db88b936189b859258eca17bdf0d56a3a08416aeddbae47',
                                                'content_digest': 'sha256:925a2a2bf6cac34747612777d860a27174c8f365785598515cee37b54bf92eca',
                                                'field_selectors': ['/'],
                                                'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                               {'source_namespace': {'anchor_digest': 'sha256:a1e890b0205cf12cce5e1ac3989ffbededc9d3c796841c23d3df3627d18b775d',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Repository',
                                                'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                                'content_digest': 'sha256:13b0a24d86f8c6f960bba9019e5fb401a99382a1beb17c05fc77f66984a2a2e5',
                                                'field_selectors': ['/'],
                                                'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                               {'source_namespace': {'anchor_digest': 'sha256:a1e890b0205cf12cce5e1ac3989ffbededc9d3c796841c23d3df3627d18b775d',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Repository',
                                                'source_id': 'sha256:ded9576e405089f62239f5052c7f9b97401ee42c79b59e06c67c7d690188ef1f',
                                                'content_digest': 'sha256:6f7e0859760e17973b42fa07f8b69233a15585278f68b9ca797ff6f6cec818b4',
                                                'field_selectors': ['/payload_snapshot/execution_receipt'],
                                                'evidence_scope': 'DETACHED_OWNER_SNAPSHOT',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                               {'source_namespace': {'anchor_digest': 'sha256:a1e890b0205cf12cce5e1ac3989ffbededc9d3c796841c23d3df3627d18b775d',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Review',
                                                'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                                'content_digest': 'sha256:97131f06b886341035f16e6882bd76fc7f197f6c082b181cd729f5254a9b47c7',
                                                'field_selectors': ['/'],
                                                'evidence_scope': 'SYNTHETIC_CONTEXT',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'}]},
                          {'namespace': {'kind': 'DETACHED_OWNER_SNAPSHOT',
                                         'anchor_digest': 'sha256:872b2e168c069588b2f41eb1978075fa9e928cf538885825c725aa9df9213c33'},
                           'component_scopes': ['RETAINED_LOCAL_FIXTURE', 'SYNTHETIC_CONTEXT'],
                           'classification': 'LOCAL_SYNTHETIC',
                           'source_manifest': [{'source_namespace': {'anchor_digest': 'sha256:872b2e168c069588b2f41eb1978075fa9e928cf538885825c725aa9df9213c33',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Blob',
                                                'source_id': 'sha256:21b04a6b43269d3685266bf6269823a466c3c71fd3f8c5853cd6474d45855642',
                                                'content_digest': 'sha256:d4c8a46a2f244f3b144f943c28b4440724f60eb11a23de4287138eba28545014',
                                                'field_selectors': ['/'],
                                                'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                               {'source_namespace': {'anchor_digest': 'sha256:872b2e168c069588b2f41eb1978075fa9e928cf538885825c725aa9df9213c33',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Repository',
                                                'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                                'content_digest': 'sha256:eb935046fe9790f6e19df2e11be83de95568f3bcf68a23adc951416b9b0ee3fa',
                                                'field_selectors': ['/'],
                                                'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                               {'source_namespace': {'anchor_digest': 'sha256:872b2e168c069588b2f41eb1978075fa9e928cf538885825c725aa9df9213c33',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Repository',
                                                'source_id': 'sha256:59af622ac46853a01ba716b9d0809808f5f999bf6bf7ba62e7ff8ef02e8a6720',
                                                'content_digest': 'sha256:fa012377cf89339e3cd1d2ecd28596714308c7771191f3a3e355c2c03f14622b',
                                                'field_selectors': ['/payload_snapshot/execution_receipt'],
                                                'evidence_scope': 'DETACHED_OWNER_SNAPSHOT',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                               {'source_namespace': {'anchor_digest': 'sha256:872b2e168c069588b2f41eb1978075fa9e928cf538885825c725aa9df9213c33',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Repository',
                                                'source_id': 'sha256:df8d2011ad90e161d99cbacd102d42b68346912ee2e74eb908a064a23c5296ef',
                                                'content_digest': 'sha256:70e40ccdaec91042d26640b99f5bf4d9f53ddf96f8883679364fd5c84e1288a0',
                                                'field_selectors': ['/payload_snapshot/execution_receipt'],
                                                'evidence_scope': 'DETACHED_OWNER_SNAPSHOT',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                               {'source_namespace': {'anchor_digest': 'sha256:872b2e168c069588b2f41eb1978075fa9e928cf538885825c725aa9df9213c33',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Review',
                                                'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                                'content_digest': 'sha256:97131f06b886341035f16e6882bd76fc7f197f6c082b181cd729f5254a9b47c7',
                                                'field_selectors': ['/'],
                                                'evidence_scope': 'SYNTHETIC_CONTEXT',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'}]},
                          {'namespace': {'kind': 'DETACHED_OWNER_SNAPSHOT',
                                         'anchor_digest': 'sha256:2217e341d8ea95e12b1e9c34dd945743b23b2cb3a4e04b2cb31f45da0da739a0'},
                           'component_scopes': ['RETAINED_LOCAL_FIXTURE', 'SYNTHETIC_CONTEXT'],
                           'classification': 'LOCAL_SYNTHETIC',
                           'source_manifest': [{'source_namespace': {'anchor_digest': 'sha256:2217e341d8ea95e12b1e9c34dd945743b23b2cb3a4e04b2cb31f45da0da739a0',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Blob',
                                                'source_id': 'sha256:678b3b33bcc22f20d9bda4942c6ae7039dbc5d36a79acfbf91abab2b3c11880b',
                                                'content_digest': 'sha256:c222e1444a117c299634a9adca109281442525b943807434e66f47f0a8ff8655',
                                                'field_selectors': ['/'],
                                                'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                               {'source_namespace': {'anchor_digest': 'sha256:2217e341d8ea95e12b1e9c34dd945743b23b2cb3a4e04b2cb31f45da0da739a0',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Repository',
                                                'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                                'content_digest': 'sha256:26f96b10d2cb8f5607e0dc3cd596282035f8c2c3bfa2069011574919eb8aa0ae',
                                                'field_selectors': ['/'],
                                                'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                               {'source_namespace': {'anchor_digest': 'sha256:2217e341d8ea95e12b1e9c34dd945743b23b2cb3a4e04b2cb31f45da0da739a0',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Repository',
                                                'source_id': 'sha256:81e1648b445445e9f4c10b2471051817f489301bd36a68de877ca73ac6bf1323',
                                                'content_digest': 'sha256:2efc95730d97f9cd41d54fbc13ceb4d24c9b896115b7284104728ac0ab614530',
                                                'field_selectors': ['/payload_snapshot/execution_receipt'],
                                                'evidence_scope': 'DETACHED_OWNER_SNAPSHOT',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                               {'source_namespace': {'anchor_digest': 'sha256:2217e341d8ea95e12b1e9c34dd945743b23b2cb3a4e04b2cb31f45da0da739a0',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Review',
                                                'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                                'content_digest': 'sha256:97131f06b886341035f16e6882bd76fc7f197f6c082b181cd729f5254a9b47c7',
                                                'field_selectors': ['/'],
                                                'evidence_scope': 'SYNTHETIC_CONTEXT',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'}]},
                          {'namespace': {'kind': 'DETACHED_OWNER_SNAPSHOT',
                                         'anchor_digest': 'sha256:8c355e204b207032e7a732f38985c7534531bbe562f478ab5c60881989a5cb42'},
                           'component_scopes': ['RETAINED_LOCAL_FIXTURE', 'SYNTHETIC_CONTEXT'],
                           'classification': 'LOCAL_SYNTHETIC',
                           'source_manifest': [{'source_namespace': {'anchor_digest': 'sha256:8c355e204b207032e7a732f38985c7534531bbe562f478ab5c60881989a5cb42',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Blob',
                                                'source_id': 'sha256:b50826201c6443536297b08e2cce0681c9c9754acd881c71241c452bf6fad956',
                                                'content_digest': 'sha256:8e3b28a70daca1dce97aab81953317a61081cbd08b336b342e1b0f654d04b41f',
                                                'field_selectors': ['/'],
                                                'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                               {'source_namespace': {'anchor_digest': 'sha256:8c355e204b207032e7a732f38985c7534531bbe562f478ab5c60881989a5cb42',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Repository',
                                                'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                                'content_digest': 'sha256:2fdcffd8af811857af71e9a7957c6431af5be5d2681c1564a147a396cd97c866',
                                                'field_selectors': ['/'],
                                                'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                               {'source_namespace': {'anchor_digest': 'sha256:8c355e204b207032e7a732f38985c7534531bbe562f478ab5c60881989a5cb42',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Repository',
                                                'source_id': 'sha256:84f599953e09a566ce630f11936ff2ac5b9e14de91e7d3a5fefec59ef9dd25f0',
                                                'content_digest': 'sha256:9ed84f871e5e569efc4d594d978990d292d24cc2bb39c0df00f1ca111a890128',
                                                'field_selectors': ['/payload_snapshot/execution_receipt'],
                                                'evidence_scope': 'DETACHED_OWNER_SNAPSHOT',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                               {'source_namespace': {'anchor_digest': 'sha256:8c355e204b207032e7a732f38985c7534531bbe562f478ab5c60881989a5cb42',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Repository',
                                                'source_id': 'sha256:a4fab6a501d0ce2ce2290ce364b712913887b6728c2d72d89f9d9c0d0c0887bf',
                                                'content_digest': 'sha256:308357ecf6983c9eab10fa14079c48f23457ff8da5f8a67408462c544ad46526',
                                                'field_selectors': ['/payload_snapshot/execution_receipt'],
                                                'evidence_scope': 'DETACHED_OWNER_SNAPSHOT',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                               {'source_namespace': {'anchor_digest': 'sha256:8c355e204b207032e7a732f38985c7534531bbe562f478ab5c60881989a5cb42',
                                                                     'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                                'owner': 'Review',
                                                'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                                'content_digest': 'sha256:97131f06b886341035f16e6882bd76fc7f197f6c082b181cd729f5254a9b47c7',
                                                'field_selectors': ['/'],
                                                'evidence_scope': 'SYNTHETIC_CONTEXT',
                                                'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'}]}],
 'member_output_digests': ['sha256:d1a6766540803f224db88b936189b859258eca17bdf0d56a3a08416aeddbae47',
                           'sha256:21b04a6b43269d3685266bf6269823a466c3c71fd3f8c5853cd6474d45855642',
                           'sha256:678b3b33bcc22f20d9bda4942c6ae7039dbc5d36a79acfbf91abab2b3c11880b',
                           'sha256:b50826201c6443536297b08e2cce0681c9c9754acd881c71241c452bf6fad956'],
 'comparability_status': 'NOT_ESTABLISHED_NO_MODEL_COMPARISON',
 'membership_policy': 'ORDERED_IMMUTABLE_ALL_OR_DIAGNOSTIC',
 'rubric_version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
 'cohort_id': 'sha256:87b6f7eb4c80471496fc05d60418bdced1aebc6f29087b5acf1a24ce8a5f2abe'}
FROZEN_IDENTITIES = [{'schema_version': 'vefin-evaluation-case/v1',
  'evaluation_policy_id': 'WP06_MECHANISM_ONLY_V1',
  'source_scope': {'namespace': {'kind': 'DETACHED_OWNER_SNAPSHOT',
                                 'anchor_digest': 'sha256:a1e890b0205cf12cce5e1ac3989ffbededc9d3c796841c23d3df3627d18b775d'},
                   'component_scopes': ['RETAINED_LOCAL_FIXTURE', 'SYNTHETIC_CONTEXT'],
                   'classification': 'LOCAL_SYNTHETIC',
                   'source_manifest': [{'source_namespace': {'anchor_digest': 'sha256:a1e890b0205cf12cce5e1ac3989ffbededc9d3c796841c23d3df3627d18b775d',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Blob',
                                        'source_id': 'sha256:d1a6766540803f224db88b936189b859258eca17bdf0d56a3a08416aeddbae47',
                                        'content_digest': 'sha256:925a2a2bf6cac34747612777d860a27174c8f365785598515cee37b54bf92eca',
                                        'field_selectors': ['/'],
                                        'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                       {'source_namespace': {'anchor_digest': 'sha256:a1e890b0205cf12cce5e1ac3989ffbededc9d3c796841c23d3df3627d18b775d',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Repository',
                                        'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                        'content_digest': 'sha256:13b0a24d86f8c6f960bba9019e5fb401a99382a1beb17c05fc77f66984a2a2e5',
                                        'field_selectors': ['/'],
                                        'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                       {'source_namespace': {'anchor_digest': 'sha256:a1e890b0205cf12cce5e1ac3989ffbededc9d3c796841c23d3df3627d18b775d',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Repository',
                                        'source_id': 'sha256:ded9576e405089f62239f5052c7f9b97401ee42c79b59e06c67c7d690188ef1f',
                                        'content_digest': 'sha256:6f7e0859760e17973b42fa07f8b69233a15585278f68b9ca797ff6f6cec818b4',
                                        'field_selectors': ['/payload_snapshot/execution_receipt'],
                                        'evidence_scope': 'DETACHED_OWNER_SNAPSHOT',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                       {'source_namespace': {'anchor_digest': 'sha256:a1e890b0205cf12cce5e1ac3989ffbededc9d3c796841c23d3df3627d18b775d',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Review',
                                        'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                        'content_digest': 'sha256:97131f06b886341035f16e6882bd76fc7f197f6c082b181cd729f5254a9b47c7',
                                        'field_selectors': ['/'],
                                        'evidence_scope': 'SYNTHETIC_CONTEXT',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'}]},
  'subject_type': 'WP03_VALUATION_TASK_RESULT',
  'subject_id': 'sha256:09c00d93fddd3a5ee854d70593636c1eb39b619083ee5f33f51e71ed223dfba5',
  'envelope_digest': 'sha256:2de3c57ff4d340074badcf63e41b35faaec1cdacba2bcb5a1806fbaa8ac70d96',
  'native_run_id': 'RUN-WP02-LOCAL-FIXTURE',
  'native_task_id': 'RUN-WP02-LOCAL-FIXTURE:1',
  'task_fingerprint': 'sha256:aa4b563bb30b49e46cdabbc39317ae4fde2ac266e2441a661c5717433b60e1e9',
  'graph_identity': {'graph_id': 'PLAN-WP02-actual',
                     'run_id': 'RUN-WP02-LOCAL-FIXTURE',
                     'semantic_hash': 'sha256:90325b73e2042bc51eee0c389c7fc517d3d1b7c06cc99ffdab2eb157bd393dcf',
                     'version': 1},
  'context_identity': {'turns': [{'context_id': 'sha256:88fc88f56b395787dd7c3fd17b5b2667f95ea46f5a3cabb582906334b6768ecf',
                                  'context_revision': 1,
                                  'source_manifest_digest': 'sha256:68d724c0a28ad097e9f80b496085e15b8c582f1755dfd7cc340bbe57ac98fe0b',
                                  'pre_B_id': 'sha256:9ad21aa57515774c3989ec86619b42d240af6ea1fb70a4cc67f972ce32d514a7',
                                  'request_manifest_digest': 'sha256:cef631e18655895c5119a8e2bb255897beb29cbb6a30b78ee058375cd381b6d2',
                                  'response_schema_digest': 'sha256:3a202039b04e6bdfbd05c52d0f4be34f4a81f2ed9c2b88a685715fabcfc354bd'}],
                       'final_context_id': 'sha256:88fc88f56b395787dd7c3fd17b5b2667f95ea46f5a3cabb582906334b6768ecf',
                       'final_context_revision': 1},
  'native_subject_identity': {'source_namespace': {'anchor_digest': 'sha256:a1e890b0205cf12cce5e1ac3989ffbededc9d3c796841c23d3df3627d18b775d',
                                                   'kind': 'DETACHED_OWNER_SNAPSHOT'},
                              'subject_type': 'WP03_VALUATION_TASK_RESULT',
                              'run_id': 'RUN-WP02-LOCAL-FIXTURE',
                              'task_id': 'RUN-WP02-LOCAL-FIXTURE:1',
                              'task_fingerprint': 'sha256:aa4b563bb30b49e46cdabbc39317ae4fde2ac266e2441a661c5717433b60e1e9',
                              'graph': {'graph_id': 'PLAN-WP02-actual',
                                        'run_id': 'RUN-WP02-LOCAL-FIXTURE',
                                        'semantic_hash': 'sha256:90325b73e2042bc51eee0c389c7fc517d3d1b7c06cc99ffdab2eb157bd393dcf',
                                        'version': 1},
                              'admission_binding_id': 'sha256:d4ce31fca3317bb95dc46b7631eb5555dd09f226f7eb4db7af2800534ee09b61',
                              'ordered_B_ids': ['sha256:80663c4fc5edb7fec002ea0cbafcf599cedcb248bc27f87cb73b391276388242',
                                                'sha256:9ad21aa57515774c3989ec86619b42d240af6ea1fb70a4cc67f972ce32d514a7',
                                                'sha256:ded9576e405089f62239f5052c7f9b97401ee42c79b59e06c67c7d690188ef1f'],
                              'result_id': 'sha256:d45e26d854470991a129cafb5c71254f5d47b9e2574be75ff411088355b494bc',
                              'result_digest': 'sha256:d45e26d854470991a129cafb5c71254f5d47b9e2574be75ff411088355b494bc',
                              'result_version': 1,
                              'current_result_id': 'sha256:d45e26d854470991a129cafb5c71254f5d47b9e2574be75ff411088355b494bc',
                              'final_context_id': 'sha256:88fc88f56b395787dd7c3fd17b5b2667f95ea46f5a3cabb582906334b6768ecf',
                              'final_context_revision': 1,
                              'final_context_manifest_digest': 'sha256:68d724c0a28ad097e9f80b496085e15b8c582f1755dfd7cc340bbe57ac98fe0b',
                              'interaction_id': 'sha256:4bb3b7b34923382116b97b3ae873879cb65ae0c01f7849b684e98303a099fde3',
                              'dispatch_membership': [{'call_id': 'sha256:4bb3b7b34923382116b97b3ae873879cb65ae0c01f7849b684e98303a099fde3:1:1',
                                                       'pre_B_id': 'sha256:9ad21aa57515774c3989ec86619b42d240af6ea1fb70a4cc67f972ce32d514a7',
                                                       'receipt_B_id': 'sha256:ded9576e405089f62239f5052c7f9b97401ee42c79b59e06c67c7d690188ef1f',
                                                       'context_id': 'sha256:88fc88f56b395787dd7c3fd17b5b2667f95ea46f5a3cabb582906334b6768ecf',
                                                       'context_revision': 1}]},
  'output_artifact_id': 'sha256:d1a6766540803f224db88b936189b859258eca17bdf0d56a3a08416aeddbae47',
  'output_digest': 'sha256:d1a6766540803f224db88b936189b859258eca17bdf0d56a3a08416aeddbae47',
  'output_material_digest': 'sha256:7da89a5e719357dda1d711d6030aea7729b5a9ed7a5ce62d262c3f302fb9bc5e',
  'result_id': 'sha256:d45e26d854470991a129cafb5c71254f5d47b9e2574be75ff411088355b494bc',
  'result_digest': 'sha256:d45e26d854470991a129cafb5c71254f5d47b9e2574be75ff411088355b494bc',
  'rubric_version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
  'oracle_refs': [{'oracle_id': 'D1_FIELDS_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:4331d7e3c5488113eecf5388ea3f6f68efb5d7673e388082160e198e7c46412f'},
                  {'oracle_id': 'D2_EXACT_REFS_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:e0b65b310366f2670da122cc7945c2b3211983fe5ba5eb49806e7ee38a2dc52a'},
                  {'oracle_id': 'D5_REVIEW_JOIN_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:e0b65b310366f2670da122cc7945c2b3211983fe5ba5eb49806e7ee38a2dc52a'},
                  {'oracle_id': 'D6_STRICT_FINAL_SCHEMA_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:4331d7e3c5488113eecf5388ea3f6f68efb5d7673e388082160e198e7c46412f'}],
  'input_file_hashes': {'envelope': '7ff212bbbfc3a992897dce7fe24feedee1255d135cbacea9146c95afdd34c250',
                        'snapshot': '6f714d8c6f76697cff70f4640bd13b8e80bd625fd199a75e8ee8efa73b021ecd'}},
 {'schema_version': 'vefin-evaluation-case/v1',
  'evaluation_policy_id': 'WP06_MECHANISM_ONLY_V1',
  'source_scope': {'namespace': {'kind': 'DETACHED_OWNER_SNAPSHOT',
                                 'anchor_digest': 'sha256:872b2e168c069588b2f41eb1978075fa9e928cf538885825c725aa9df9213c33'},
                   'component_scopes': ['RETAINED_LOCAL_FIXTURE', 'SYNTHETIC_CONTEXT'],
                   'classification': 'LOCAL_SYNTHETIC',
                   'source_manifest': [{'source_namespace': {'anchor_digest': 'sha256:872b2e168c069588b2f41eb1978075fa9e928cf538885825c725aa9df9213c33',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Blob',
                                        'source_id': 'sha256:21b04a6b43269d3685266bf6269823a466c3c71fd3f8c5853cd6474d45855642',
                                        'content_digest': 'sha256:d4c8a46a2f244f3b144f943c28b4440724f60eb11a23de4287138eba28545014',
                                        'field_selectors': ['/'],
                                        'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                       {'source_namespace': {'anchor_digest': 'sha256:872b2e168c069588b2f41eb1978075fa9e928cf538885825c725aa9df9213c33',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Repository',
                                        'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                        'content_digest': 'sha256:eb935046fe9790f6e19df2e11be83de95568f3bcf68a23adc951416b9b0ee3fa',
                                        'field_selectors': ['/'],
                                        'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                       {'source_namespace': {'anchor_digest': 'sha256:872b2e168c069588b2f41eb1978075fa9e928cf538885825c725aa9df9213c33',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Repository',
                                        'source_id': 'sha256:59af622ac46853a01ba716b9d0809808f5f999bf6bf7ba62e7ff8ef02e8a6720',
                                        'content_digest': 'sha256:fa012377cf89339e3cd1d2ecd28596714308c7771191f3a3e355c2c03f14622b',
                                        'field_selectors': ['/payload_snapshot/execution_receipt'],
                                        'evidence_scope': 'DETACHED_OWNER_SNAPSHOT',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                       {'source_namespace': {'anchor_digest': 'sha256:872b2e168c069588b2f41eb1978075fa9e928cf538885825c725aa9df9213c33',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Repository',
                                        'source_id': 'sha256:df8d2011ad90e161d99cbacd102d42b68346912ee2e74eb908a064a23c5296ef',
                                        'content_digest': 'sha256:70e40ccdaec91042d26640b99f5bf4d9f53ddf96f8883679364fd5c84e1288a0',
                                        'field_selectors': ['/payload_snapshot/execution_receipt'],
                                        'evidence_scope': 'DETACHED_OWNER_SNAPSHOT',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                       {'source_namespace': {'anchor_digest': 'sha256:872b2e168c069588b2f41eb1978075fa9e928cf538885825c725aa9df9213c33',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Review',
                                        'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                        'content_digest': 'sha256:97131f06b886341035f16e6882bd76fc7f197f6c082b181cd729f5254a9b47c7',
                                        'field_selectors': ['/'],
                                        'evidence_scope': 'SYNTHETIC_CONTEXT',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'}]},
  'subject_type': 'WP03_VALUATION_TASK_RESULT',
  'subject_id': 'sha256:182f2c542e082638c87751f5e1aa7064c6250c5a130239b0527b00b51212634c',
  'envelope_digest': 'sha256:1d22934ba72749bd7b8c8d5dd4c6b48d9a3f69e6cae5178d0c7cd2a4a3cdaebd',
  'native_run_id': 'RUN-WP02-LOCAL-FIXTURE',
  'native_task_id': 'RUN-WP02-LOCAL-FIXTURE:1',
  'task_fingerprint': 'sha256:aa4b563bb30b49e46cdabbc39317ae4fde2ac266e2441a661c5717433b60e1e9',
  'graph_identity': {'graph_id': 'PLAN-WP02-actual',
                     'run_id': 'RUN-WP02-LOCAL-FIXTURE',
                     'semantic_hash': 'sha256:90325b73e2042bc51eee0c389c7fc517d3d1b7c06cc99ffdab2eb157bd393dcf',
                     'version': 1},
  'context_identity': {'turns': [{'context_id': 'sha256:bb00ff68a262e7dff26db006d77ca12542a8fad16d64aad94c72ba97f2274842',
                                  'context_revision': 1,
                                  'source_manifest_digest': 'sha256:d597265e3376f00d2742d7f703c68c5b35691b9c8a411e3b5b4bc6cf0c829382',
                                  'pre_B_id': 'sha256:3ae15b0323ad1d279df8d188bc3f8791c97f7c6f3d7839b1f66afae542bad455',
                                  'request_manifest_digest': 'sha256:3285ae954ded37bf2bc72b3d70ecc7ef8baea1428525ab4965f72d60c268dcdd',
                                  'response_schema_digest': 'sha256:3a202039b04e6bdfbd05c52d0f4be34f4a81f2ed9c2b88a685715fabcfc354bd'},
                                 {'context_id': 'sha256:76ec2c877bf704cba3a760013afca8ef23b6021741963da80c9c8d93ef51671d',
                                  'context_revision': 2,
                                  'source_manifest_digest': 'sha256:d623fc924af66f0069317c1b5d5d74544fdfe220078e57bc346d23a88b6d529a',
                                  'pre_B_id': 'sha256:88f5c12490f92dffd3712469845567b0da2aafca46b2cc553325f87729226927',
                                  'request_manifest_digest': 'sha256:4560a61746604e4095a446098bf1168b4fc74100d05a0e58b39af2fe7ea7498f',
                                  'response_schema_digest': 'sha256:9d9a1310e5cdfc35be22e6b867d8871dda22c6fb2f4d4882bf09827ce8ad1c16'}],
                       'final_context_id': 'sha256:76ec2c877bf704cba3a760013afca8ef23b6021741963da80c9c8d93ef51671d',
                       'final_context_revision': 2},
  'native_subject_identity': {'source_namespace': {'anchor_digest': 'sha256:872b2e168c069588b2f41eb1978075fa9e928cf538885825c725aa9df9213c33',
                                                   'kind': 'DETACHED_OWNER_SNAPSHOT'},
                              'subject_type': 'WP03_VALUATION_TASK_RESULT',
                              'run_id': 'RUN-WP02-LOCAL-FIXTURE',
                              'task_id': 'RUN-WP02-LOCAL-FIXTURE:1',
                              'task_fingerprint': 'sha256:aa4b563bb30b49e46cdabbc39317ae4fde2ac266e2441a661c5717433b60e1e9',
                              'graph': {'graph_id': 'PLAN-WP02-actual',
                                        'run_id': 'RUN-WP02-LOCAL-FIXTURE',
                                        'semantic_hash': 'sha256:90325b73e2042bc51eee0c389c7fc517d3d1b7c06cc99ffdab2eb157bd393dcf',
                                        'version': 1},
                              'admission_binding_id': 'sha256:183e3fc007d83f8f93aa685280f5082cbf32795862588b488f0d59f29e72d1de',
                              'ordered_B_ids': ['sha256:9b02cf8bcf94a420f7626d9bafc4bf652f586d129aed3a747f6adc6dc55bc1a6',
                                                'sha256:3ae15b0323ad1d279df8d188bc3f8791c97f7c6f3d7839b1f66afae542bad455',
                                                'sha256:59af622ac46853a01ba716b9d0809808f5f999bf6bf7ba62e7ff8ef02e8a6720',
                                                'sha256:88f5c12490f92dffd3712469845567b0da2aafca46b2cc553325f87729226927',
                                                'sha256:df8d2011ad90e161d99cbacd102d42b68346912ee2e74eb908a064a23c5296ef'],
                              'result_id': 'sha256:e64b32f13eb5636424c64917458a12254d5b1cb0ca5a30f3e8d0e1ee59663206',
                              'result_digest': 'sha256:e64b32f13eb5636424c64917458a12254d5b1cb0ca5a30f3e8d0e1ee59663206',
                              'result_version': 1,
                              'current_result_id': 'sha256:e64b32f13eb5636424c64917458a12254d5b1cb0ca5a30f3e8d0e1ee59663206',
                              'final_context_id': 'sha256:76ec2c877bf704cba3a760013afca8ef23b6021741963da80c9c8d93ef51671d',
                              'final_context_revision': 2,
                              'final_context_manifest_digest': 'sha256:d623fc924af66f0069317c1b5d5d74544fdfe220078e57bc346d23a88b6d529a',
                              'interaction_id': 'sha256:b023bb65293a03ea0d90aab68abc36e79cd5e1279285f064708c1b4f9932cbfe',
                              'dispatch_membership': [{'call_id': 'sha256:b023bb65293a03ea0d90aab68abc36e79cd5e1279285f064708c1b4f9932cbfe:1:1',
                                                       'pre_B_id': 'sha256:3ae15b0323ad1d279df8d188bc3f8791c97f7c6f3d7839b1f66afae542bad455',
                                                       'receipt_B_id': 'sha256:59af622ac46853a01ba716b9d0809808f5f999bf6bf7ba62e7ff8ef02e8a6720',
                                                       'context_id': 'sha256:bb00ff68a262e7dff26db006d77ca12542a8fad16d64aad94c72ba97f2274842',
                                                       'context_revision': 1},
                                                      {'call_id': 'sha256:b023bb65293a03ea0d90aab68abc36e79cd5e1279285f064708c1b4f9932cbfe:2:1',
                                                       'pre_B_id': 'sha256:88f5c12490f92dffd3712469845567b0da2aafca46b2cc553325f87729226927',
                                                       'receipt_B_id': 'sha256:df8d2011ad90e161d99cbacd102d42b68346912ee2e74eb908a064a23c5296ef',
                                                       'context_id': 'sha256:76ec2c877bf704cba3a760013afca8ef23b6021741963da80c9c8d93ef51671d',
                                                       'context_revision': 2}]},
  'output_artifact_id': 'sha256:21b04a6b43269d3685266bf6269823a466c3c71fd3f8c5853cd6474d45855642',
  'output_digest': 'sha256:21b04a6b43269d3685266bf6269823a466c3c71fd3f8c5853cd6474d45855642',
  'output_material_digest': 'sha256:1be6c64d6249adfb8ad65f1c8e858005db7aded240d22729b3d3491be65d0a30',
  'result_id': 'sha256:e64b32f13eb5636424c64917458a12254d5b1cb0ca5a30f3e8d0e1ee59663206',
  'result_digest': 'sha256:e64b32f13eb5636424c64917458a12254d5b1cb0ca5a30f3e8d0e1ee59663206',
  'rubric_version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
  'oracle_refs': [{'oracle_id': 'D1_FIELDS_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:4331d7e3c5488113eecf5388ea3f6f68efb5d7673e388082160e198e7c46412f'},
                  {'oracle_id': 'D2_EXACT_REFS_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:e0b65b310366f2670da122cc7945c2b3211983fe5ba5eb49806e7ee38a2dc52a'},
                  {'oracle_id': 'D5_REVIEW_JOIN_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:e0b65b310366f2670da122cc7945c2b3211983fe5ba5eb49806e7ee38a2dc52a'},
                  {'oracle_id': 'D6_STRICT_FINAL_SCHEMA_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:4331d7e3c5488113eecf5388ea3f6f68efb5d7673e388082160e198e7c46412f'}],
  'input_file_hashes': {'envelope': '509c61cde7c97ed392035c2e1087462f4eeca48ff6cf02585d4c46399f5fba15',
                        'snapshot': '69bb08bfd9e494623abff92f4c781c089b7940c06c2bb8444ddfa965328a118a'}},
 {'schema_version': 'vefin-evaluation-case/v1',
  'evaluation_policy_id': 'WP06_MECHANISM_ONLY_V1',
  'source_scope': {'namespace': {'kind': 'DETACHED_OWNER_SNAPSHOT',
                                 'anchor_digest': 'sha256:2217e341d8ea95e12b1e9c34dd945743b23b2cb3a4e04b2cb31f45da0da739a0'},
                   'component_scopes': ['RETAINED_LOCAL_FIXTURE', 'SYNTHETIC_CONTEXT'],
                   'classification': 'LOCAL_SYNTHETIC',
                   'source_manifest': [{'source_namespace': {'anchor_digest': 'sha256:2217e341d8ea95e12b1e9c34dd945743b23b2cb3a4e04b2cb31f45da0da739a0',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Blob',
                                        'source_id': 'sha256:678b3b33bcc22f20d9bda4942c6ae7039dbc5d36a79acfbf91abab2b3c11880b',
                                        'content_digest': 'sha256:c222e1444a117c299634a9adca109281442525b943807434e66f47f0a8ff8655',
                                        'field_selectors': ['/'],
                                        'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                       {'source_namespace': {'anchor_digest': 'sha256:2217e341d8ea95e12b1e9c34dd945743b23b2cb3a4e04b2cb31f45da0da739a0',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Repository',
                                        'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                        'content_digest': 'sha256:26f96b10d2cb8f5607e0dc3cd596282035f8c2c3bfa2069011574919eb8aa0ae',
                                        'field_selectors': ['/'],
                                        'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                       {'source_namespace': {'anchor_digest': 'sha256:2217e341d8ea95e12b1e9c34dd945743b23b2cb3a4e04b2cb31f45da0da739a0',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Repository',
                                        'source_id': 'sha256:81e1648b445445e9f4c10b2471051817f489301bd36a68de877ca73ac6bf1323',
                                        'content_digest': 'sha256:2efc95730d97f9cd41d54fbc13ceb4d24c9b896115b7284104728ac0ab614530',
                                        'field_selectors': ['/payload_snapshot/execution_receipt'],
                                        'evidence_scope': 'DETACHED_OWNER_SNAPSHOT',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                       {'source_namespace': {'anchor_digest': 'sha256:2217e341d8ea95e12b1e9c34dd945743b23b2cb3a4e04b2cb31f45da0da739a0',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Review',
                                        'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                        'content_digest': 'sha256:97131f06b886341035f16e6882bd76fc7f197f6c082b181cd729f5254a9b47c7',
                                        'field_selectors': ['/'],
                                        'evidence_scope': 'SYNTHETIC_CONTEXT',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'}]},
  'subject_type': 'WP03_VALUATION_TASK_RESULT',
  'subject_id': 'sha256:539e210c65f0c8e8fcc3ad0fe78ae9b60224b6f97768b2cc6af5893231489ba5',
  'envelope_digest': 'sha256:fa2cb5dd020afee3602f5bc67fb1545e596f92f2e607fb2369a6b52ff12d26ba',
  'native_run_id': 'RUN-WP02-LOCAL-FIXTURE',
  'native_task_id': 'RUN-WP02-LOCAL-FIXTURE:1',
  'task_fingerprint': 'sha256:aa4b563bb30b49e46cdabbc39317ae4fde2ac266e2441a661c5717433b60e1e9',
  'graph_identity': {'graph_id': 'PLAN-WP02-actual',
                     'run_id': 'RUN-WP02-LOCAL-FIXTURE',
                     'semantic_hash': 'sha256:90325b73e2042bc51eee0c389c7fc517d3d1b7c06cc99ffdab2eb157bd393dcf',
                     'version': 1},
  'context_identity': {'turns': [{'context_id': 'sha256:f5c3fd368a0f6ec4e620a4688100ae5c959384972384a47e6d1ab163e898fcc0',
                                  'context_revision': 1,
                                  'source_manifest_digest': 'sha256:d8851d7467e573666a0881501b9232a569dbfbfacbee07b7fd17e50f69915524',
                                  'pre_B_id': 'sha256:c645f58430c21dc4c5595bb0d78abf63a07ae8a2bcf2913320c8ace7ce048017',
                                  'request_manifest_digest': 'sha256:a5f33f271c5d0ff9c1d78b932f5567982c8022d7f69739dcdf99f0a760048420',
                                  'response_schema_digest': 'sha256:3a202039b04e6bdfbd05c52d0f4be34f4a81f2ed9c2b88a685715fabcfc354bd'}],
                       'final_context_id': 'sha256:f5c3fd368a0f6ec4e620a4688100ae5c959384972384a47e6d1ab163e898fcc0',
                       'final_context_revision': 1},
  'native_subject_identity': {'source_namespace': {'anchor_digest': 'sha256:2217e341d8ea95e12b1e9c34dd945743b23b2cb3a4e04b2cb31f45da0da739a0',
                                                   'kind': 'DETACHED_OWNER_SNAPSHOT'},
                              'subject_type': 'WP03_VALUATION_TASK_RESULT',
                              'run_id': 'RUN-WP02-LOCAL-FIXTURE',
                              'task_id': 'RUN-WP02-LOCAL-FIXTURE:1',
                              'task_fingerprint': 'sha256:aa4b563bb30b49e46cdabbc39317ae4fde2ac266e2441a661c5717433b60e1e9',
                              'graph': {'graph_id': 'PLAN-WP02-actual',
                                        'run_id': 'RUN-WP02-LOCAL-FIXTURE',
                                        'semantic_hash': 'sha256:90325b73e2042bc51eee0c389c7fc517d3d1b7c06cc99ffdab2eb157bd393dcf',
                                        'version': 1},
                              'admission_binding_id': 'sha256:c0aeb5525c8879f7c37f667179d93787732d62cc8217d6b0eaac87f0c323df90',
                              'ordered_B_ids': ['sha256:09dc2048b0e8526bbe8ab364a02f7db00bb844c20df51a72102d8ef798445769',
                                                'sha256:c645f58430c21dc4c5595bb0d78abf63a07ae8a2bcf2913320c8ace7ce048017',
                                                'sha256:81e1648b445445e9f4c10b2471051817f489301bd36a68de877ca73ac6bf1323'],
                              'result_id': 'sha256:487a77ae41319ad3d23aa59315406f0799d3d44895fd94c9cc6d754319a34304',
                              'result_digest': 'sha256:487a77ae41319ad3d23aa59315406f0799d3d44895fd94c9cc6d754319a34304',
                              'result_version': 1,
                              'current_result_id': 'sha256:487a77ae41319ad3d23aa59315406f0799d3d44895fd94c9cc6d754319a34304',
                              'final_context_id': 'sha256:f5c3fd368a0f6ec4e620a4688100ae5c959384972384a47e6d1ab163e898fcc0',
                              'final_context_revision': 1,
                              'final_context_manifest_digest': 'sha256:d8851d7467e573666a0881501b9232a569dbfbfacbee07b7fd17e50f69915524',
                              'interaction_id': 'sha256:cb929b28dbea1c0cdfda5d64829d0b62b7c305e837fd90c978b15df593e66c3d',
                              'dispatch_membership': [{'call_id': 'sha256:cb929b28dbea1c0cdfda5d64829d0b62b7c305e837fd90c978b15df593e66c3d:1:1',
                                                       'pre_B_id': 'sha256:c645f58430c21dc4c5595bb0d78abf63a07ae8a2bcf2913320c8ace7ce048017',
                                                       'receipt_B_id': 'sha256:81e1648b445445e9f4c10b2471051817f489301bd36a68de877ca73ac6bf1323',
                                                       'context_id': 'sha256:f5c3fd368a0f6ec4e620a4688100ae5c959384972384a47e6d1ab163e898fcc0',
                                                       'context_revision': 1}]},
  'output_artifact_id': 'sha256:678b3b33bcc22f20d9bda4942c6ae7039dbc5d36a79acfbf91abab2b3c11880b',
  'output_digest': 'sha256:678b3b33bcc22f20d9bda4942c6ae7039dbc5d36a79acfbf91abab2b3c11880b',
  'output_material_digest': 'sha256:555dc4149b568c7997d9b220a5ae463995a4e90cd64d82a2bf7b3386645c4d37',
  'result_id': 'sha256:487a77ae41319ad3d23aa59315406f0799d3d44895fd94c9cc6d754319a34304',
  'result_digest': 'sha256:487a77ae41319ad3d23aa59315406f0799d3d44895fd94c9cc6d754319a34304',
  'rubric_version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
  'oracle_refs': [{'oracle_id': 'D1_FIELDS_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:4331d7e3c5488113eecf5388ea3f6f68efb5d7673e388082160e198e7c46412f'},
                  {'oracle_id': 'D2_EXACT_REFS_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:e0b65b310366f2670da122cc7945c2b3211983fe5ba5eb49806e7ee38a2dc52a'},
                  {'oracle_id': 'D5_REVIEW_JOIN_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:e0b65b310366f2670da122cc7945c2b3211983fe5ba5eb49806e7ee38a2dc52a'},
                  {'oracle_id': 'D6_STRICT_FINAL_SCHEMA_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:4331d7e3c5488113eecf5388ea3f6f68efb5d7673e388082160e198e7c46412f'}],
  'input_file_hashes': {'envelope': '40c34b3d0aee3c9acc18331fb9f27d3a3180286aece08bbb0f311ce1655df967',
                        'snapshot': '2434fed1e002b4c18375abafce56bcd6a2afe799565831ebf34a49ba80fc2c6e'}},
 {'schema_version': 'vefin-evaluation-case/v1',
  'evaluation_policy_id': 'WP06_MECHANISM_ONLY_V1',
  'source_scope': {'namespace': {'kind': 'DETACHED_OWNER_SNAPSHOT',
                                 'anchor_digest': 'sha256:8c355e204b207032e7a732f38985c7534531bbe562f478ab5c60881989a5cb42'},
                   'component_scopes': ['RETAINED_LOCAL_FIXTURE', 'SYNTHETIC_CONTEXT'],
                   'classification': 'LOCAL_SYNTHETIC',
                   'source_manifest': [{'source_namespace': {'anchor_digest': 'sha256:8c355e204b207032e7a732f38985c7534531bbe562f478ab5c60881989a5cb42',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Blob',
                                        'source_id': 'sha256:b50826201c6443536297b08e2cce0681c9c9754acd881c71241c452bf6fad956',
                                        'content_digest': 'sha256:8e3b28a70daca1dce97aab81953317a61081cbd08b336b342e1b0f654d04b41f',
                                        'field_selectors': ['/'],
                                        'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                       {'source_namespace': {'anchor_digest': 'sha256:8c355e204b207032e7a732f38985c7534531bbe562f478ab5c60881989a5cb42',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Repository',
                                        'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                        'content_digest': 'sha256:2fdcffd8af811857af71e9a7957c6431af5be5d2681c1564a147a396cd97c866',
                                        'field_selectors': ['/'],
                                        'evidence_scope': 'RETAINED_LOCAL_FIXTURE',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                       {'source_namespace': {'anchor_digest': 'sha256:8c355e204b207032e7a732f38985c7534531bbe562f478ab5c60881989a5cb42',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Repository',
                                        'source_id': 'sha256:84f599953e09a566ce630f11936ff2ac5b9e14de91e7d3a5fefec59ef9dd25f0',
                                        'content_digest': 'sha256:9ed84f871e5e569efc4d594d978990d292d24cc2bb39c0df00f1ca111a890128',
                                        'field_selectors': ['/payload_snapshot/execution_receipt'],
                                        'evidence_scope': 'DETACHED_OWNER_SNAPSHOT',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                       {'source_namespace': {'anchor_digest': 'sha256:8c355e204b207032e7a732f38985c7534531bbe562f478ab5c60881989a5cb42',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Repository',
                                        'source_id': 'sha256:a4fab6a501d0ce2ce2290ce364b712913887b6728c2d72d89f9d9c0d0c0887bf',
                                        'content_digest': 'sha256:308357ecf6983c9eab10fa14079c48f23457ff8da5f8a67408462c544ad46526',
                                        'field_selectors': ['/payload_snapshot/execution_receipt'],
                                        'evidence_scope': 'DETACHED_OWNER_SNAPSHOT',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'},
                                       {'source_namespace': {'anchor_digest': 'sha256:8c355e204b207032e7a732f38985c7534531bbe562f478ab5c60881989a5cb42',
                                                             'kind': 'DETACHED_OWNER_SNAPSHOT'},
                                        'owner': 'Review',
                                        'source_id': 'RUN-WP02-LOCAL-FIXTURE',
                                        'content_digest': 'sha256:97131f06b886341035f16e6882bd76fc7f197f6c082b181cd729f5254a9b47c7',
                                        'field_selectors': ['/'],
                                        'evidence_scope': 'SYNTHETIC_CONTEXT',
                                        'producer_baseline': 'e290403578cd5485bcee53649ae14f835905d484'}]},
  'subject_type': 'WP03_VALUATION_TASK_RESULT',
  'subject_id': 'sha256:fb1f3102b3b215f8245a18fe76c5aa5bc2223008cc77cdba031c4856ccf37fe3',
  'envelope_digest': 'sha256:4e63fcded0de9d82ef8abc4d331c791ca143eac155b3b724dae561af05f216ce',
  'native_run_id': 'RUN-WP02-LOCAL-FIXTURE',
  'native_task_id': 'RUN-WP02-LOCAL-FIXTURE:1',
  'task_fingerprint': 'sha256:aa4b563bb30b49e46cdabbc39317ae4fde2ac266e2441a661c5717433b60e1e9',
  'graph_identity': {'graph_id': 'PLAN-WP02-actual',
                     'run_id': 'RUN-WP02-LOCAL-FIXTURE',
                     'semantic_hash': 'sha256:90325b73e2042bc51eee0c389c7fc517d3d1b7c06cc99ffdab2eb157bd393dcf',
                     'version': 1},
  'context_identity': {'turns': [{'context_id': 'sha256:3b7c6672c22819c00398dd7d3888e239e158da4b2a53b88a1174eb4025d5b9b0',
                                  'context_revision': 1,
                                  'source_manifest_digest': 'sha256:4942d0508c5cec2282ea479ead57729c7bf4bda18fda5580098f388392f9cb4d',
                                  'pre_B_id': 'sha256:5de9776cb91c9244aea60eeb7d3250f38ed704ed90f10bd91bd272227ee32d2b',
                                  'request_manifest_digest': 'sha256:f5425b0edbf506866b9992035e3865298954521cebf000b6093b3b0ade868034',
                                  'response_schema_digest': 'sha256:3a202039b04e6bdfbd05c52d0f4be34f4a81f2ed9c2b88a685715fabcfc354bd'},
                                 {'context_id': 'sha256:25194a124379823b469399f3ec7974489015823dd8e9c79da8bd05923667b0a3',
                                  'context_revision': 2,
                                  'source_manifest_digest': 'sha256:86e7f24a07b5def1edbd22ef84fa132c98eca92f8602b27d88c107f163f48224',
                                  'pre_B_id': 'sha256:0d412918d97e28ab49c3c86e85896f064e21ac37f9d2cc5346b99e296b3051ea',
                                  'request_manifest_digest': 'sha256:06fdb327fd0a9d34a04c88eede041c4867bc7de782166c2fe1c77f1dd253d3ff',
                                  'response_schema_digest': 'sha256:9d9a1310e5cdfc35be22e6b867d8871dda22c6fb2f4d4882bf09827ce8ad1c16'}],
                       'final_context_id': 'sha256:25194a124379823b469399f3ec7974489015823dd8e9c79da8bd05923667b0a3',
                       'final_context_revision': 2},
  'native_subject_identity': {'source_namespace': {'anchor_digest': 'sha256:8c355e204b207032e7a732f38985c7534531bbe562f478ab5c60881989a5cb42',
                                                   'kind': 'DETACHED_OWNER_SNAPSHOT'},
                              'subject_type': 'WP03_VALUATION_TASK_RESULT',
                              'run_id': 'RUN-WP02-LOCAL-FIXTURE',
                              'task_id': 'RUN-WP02-LOCAL-FIXTURE:1',
                              'task_fingerprint': 'sha256:aa4b563bb30b49e46cdabbc39317ae4fde2ac266e2441a661c5717433b60e1e9',
                              'graph': {'graph_id': 'PLAN-WP02-actual',
                                        'run_id': 'RUN-WP02-LOCAL-FIXTURE',
                                        'semantic_hash': 'sha256:90325b73e2042bc51eee0c389c7fc517d3d1b7c06cc99ffdab2eb157bd393dcf',
                                        'version': 1},
                              'admission_binding_id': 'sha256:cc7faa73c3369da76ddd9283beb33c927af51bad2646a2c09d3aeeeff1d0cb40',
                              'ordered_B_ids': ['sha256:87e800bd8cbbd6b73db73142fb02824b06a0694a601fe8c9d6b9706caee55081',
                                                'sha256:5de9776cb91c9244aea60eeb7d3250f38ed704ed90f10bd91bd272227ee32d2b',
                                                'sha256:a4fab6a501d0ce2ce2290ce364b712913887b6728c2d72d89f9d9c0d0c0887bf',
                                                'sha256:0d412918d97e28ab49c3c86e85896f064e21ac37f9d2cc5346b99e296b3051ea',
                                                'sha256:84f599953e09a566ce630f11936ff2ac5b9e14de91e7d3a5fefec59ef9dd25f0'],
                              'result_id': 'sha256:f3a5fcdfb5aa80340481d062154e314e8090f03f12438a4225faeb0530b8b478',
                              'result_digest': 'sha256:f3a5fcdfb5aa80340481d062154e314e8090f03f12438a4225faeb0530b8b478',
                              'result_version': 1,
                              'current_result_id': 'sha256:f3a5fcdfb5aa80340481d062154e314e8090f03f12438a4225faeb0530b8b478',
                              'final_context_id': 'sha256:25194a124379823b469399f3ec7974489015823dd8e9c79da8bd05923667b0a3',
                              'final_context_revision': 2,
                              'final_context_manifest_digest': 'sha256:86e7f24a07b5def1edbd22ef84fa132c98eca92f8602b27d88c107f163f48224',
                              'interaction_id': 'sha256:848d29ae5964850083f00b809dd2b51fe10fb60f5a886de31160830007a9f9b2',
                              'dispatch_membership': [{'call_id': 'sha256:848d29ae5964850083f00b809dd2b51fe10fb60f5a886de31160830007a9f9b2:1:1',
                                                       'pre_B_id': 'sha256:5de9776cb91c9244aea60eeb7d3250f38ed704ed90f10bd91bd272227ee32d2b',
                                                       'receipt_B_id': 'sha256:a4fab6a501d0ce2ce2290ce364b712913887b6728c2d72d89f9d9c0d0c0887bf',
                                                       'context_id': 'sha256:3b7c6672c22819c00398dd7d3888e239e158da4b2a53b88a1174eb4025d5b9b0',
                                                       'context_revision': 1},
                                                      {'call_id': 'sha256:848d29ae5964850083f00b809dd2b51fe10fb60f5a886de31160830007a9f9b2:2:1',
                                                       'pre_B_id': 'sha256:0d412918d97e28ab49c3c86e85896f064e21ac37f9d2cc5346b99e296b3051ea',
                                                       'receipt_B_id': 'sha256:84f599953e09a566ce630f11936ff2ac5b9e14de91e7d3a5fefec59ef9dd25f0',
                                                       'context_id': 'sha256:25194a124379823b469399f3ec7974489015823dd8e9c79da8bd05923667b0a3',
                                                       'context_revision': 2}]},
  'output_artifact_id': 'sha256:b50826201c6443536297b08e2cce0681c9c9754acd881c71241c452bf6fad956',
  'output_digest': 'sha256:b50826201c6443536297b08e2cce0681c9c9754acd881c71241c452bf6fad956',
  'output_material_digest': 'sha256:6f9ed2bc74f92d221b5ee94c087f7c389ad646c3fe246b8b5e002232cdc1d31a',
  'result_id': 'sha256:f3a5fcdfb5aa80340481d062154e314e8090f03f12438a4225faeb0530b8b478',
  'result_digest': 'sha256:f3a5fcdfb5aa80340481d062154e314e8090f03f12438a4225faeb0530b8b478',
  'rubric_version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
  'oracle_refs': [{'oracle_id': 'D1_FIELDS_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:4331d7e3c5488113eecf5388ea3f6f68efb5d7673e388082160e198e7c46412f'},
                  {'oracle_id': 'D2_EXACT_REFS_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:e0b65b310366f2670da122cc7945c2b3211983fe5ba5eb49806e7ee38a2dc52a'},
                  {'oracle_id': 'D5_REVIEW_JOIN_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:e0b65b310366f2670da122cc7945c2b3211983fe5ba5eb49806e7ee38a2dc52a'},
                  {'oracle_id': 'D6_STRICT_FINAL_SCHEMA_V1',
                   'version': 'WP06_D1_D2_D5_D6_RUBRIC_V1',
                   'source_digest': 'sha256:4331d7e3c5488113eecf5388ea3f6f68efb5d7673e388082160e198e7c46412f'}],
  'input_file_hashes': {'envelope': '22b4a7024bb7fd512f7e2c4d0aabe55226a6c3bf23726cd283dcabfa5a6d8910',
                        'snapshot': '7767563e9528842f4c0f503074c838cccba47172c52e77985ded1692c0c48be3'}}]
SCHEMA_PINS = {'agent_output.py': 'sha256:4331d7e3c5488113eecf5388ea3f6f68efb5d7673e388082160e198e7c46412f',
 'base.py': 'sha256:f629b64e9e5995315160c0dca9daddf9fdff147db8bf3348694b1f9f435b1471',
 'node_binding.py': 'sha256:f79a2fab7ccd4607b0c3c6b864e426e8d272ac6ad71964a5913d254423e2ef1c',
 'valuation_context.py': 'sha256:4b21e37084a10554542bda8601d96431374ae69fe266df2c576c1ea6fb756884',
 'evaluation_input.py': 'sha256:e0b65b310366f2670da122cc7945c2b3211983fe5ba5eb49806e7ee38a2dc52a'}

RUBRIC = 'WP06_D1_D2_D5_D6_RUBRIC_V1'
POLICY = 'WP06_MECHANISM_ONLY_V1'
FIELDS = ('summary', 'key_findings', 'risks', 'limitations', 'requires_follow_up')
DIMENSIONS = {
    'D1_STRUCTURAL_COMPLETENESS': ('D1_FIELDS_V1', ('COMPLETE', 'PARTIAL', 'MISSING')),
    'D2_REFERENCE_INTEGRITY': ('D2_EXACT_REFS_V1', ('PASS', 'FAIL', 'UNKNOWN')),
    'D5_REVIEW_CONTEXT_JOINING': ('D5_REVIEW_JOIN_V1', ('COMPLETE', 'PARTIAL', 'MISSING')),
    'D6_OUTPUT_SCHEMA_VALIDITY': ('D6_STRICT_FINAL_SCHEMA_V1', ('PASS', 'FAIL', 'UNKNOWN')),
}
D1, D2, D5, D6 = DIMENSIONS
INTEGRITY = {'D5_INTEGRITY_PASS', 'D5_INTEGRITY_FAIL', 'D5_INTEGRITY_UNKNOWN'}
REASONS = {
    D1: {'REQUIRED_FIELD_ABSENT', 'OUTPUT_UNAVAILABLE'},
    D2: {'REFERENCE_UNRESOLVED', 'REFERENCE_CONFLICT'},
    D5: INTEGRITY | {'REVIEW_MISSING', 'REVIEW_PARTIAL', 'REVIEW_IDENTITY_CONFLICT',
                    'DIRECT_SUBJECT_LINK_UNKNOWN'},
    D6: {'REQUIRED_FIELD_ABSENT', 'OUTPUT_UNAVAILABLE', 'SCHEMA_UNAVAILABLE',
         'SCHEMA_TYPE', 'SCHEMA_EXTRA_FIELD', 'SCHEMA_LENGTH', 'SCHEMA_BLANK',
         'SCHEMA_DUPLICATE_TEXT', 'FOLLOW_UP_NOT_FALSE', 'FINAL_BRANCH_INVALID'},
}
INVALID_REASONS = set('IDENTITY_MISMATCH DIGEST_MISMATCH MISSING_REQUIRED_INPUT '
                      'UNSUPPORTED_SCHEMA UNSUPPORTED_PROFILE SOURCE_SCOPE_NOT_ADMITTED '
                      'WP05_NOT_READY DUPLICATE_MEMBER MEMBERSHIP_DRIFT'.split())
READINESS_REASONS = wp05.CORE_REASONS | set('MISSING_MODEL_OBSERVATION '
    'MISSING_USAGE_PROVENANCE MISSING_TURN_MEASUREMENT MISSING_REVIEW '
    'METHOD_IDENTITY_UNKNOWN LEGACY_METADATA_ABSENT'.split())
METRIC_REASONS = set('INCOMPLETE_DISPATCH_MEMBERSHIP INCOMPLETE_METRIC_COVERAGE '
                    'PROVENANCE_UNKNOWN NOT_COMPARABLE SCOPE_MISMATCH COST_NOT_ADMITTED '
                    'PROVIDER_LATENCY_NOT_RETAINED'.split())
TOKEN_METRICS = ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_output_tokens')
LATENCY_METRICS = ('model_turn_elapsed', 'provider_only_latency')
STRATA = ('LOCAL_SYNTHETIC_1_TURN', 'LOCAL_SYNTHETIC_2_TURN')
PROFILE = ['fixed-initial', 'new-bound', 'DEFAULT', 'opt-in', 'no-recovery',
           'single-route', 'owned direct client']


class MechanismInputError(ValueError):
    """Fixed error code only; private values and exception text never escape."""


def _require(condition, code='IDENTITY_MISMATCH'):
    if not condition:
        raise MechanismInputError(code)


def _plain(value, *, floats=False, depth=0):
    _require(depth <= 70, 'UNSUPPORTED_SCHEMA')
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and floats and math.isfinite(value):
        return
    if type(value) is list:
        _require(len(value) <= 4096, 'UNSUPPORTED_SCHEMA')
        for item in value:
            _plain(item, floats=floats, depth=depth + 1)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        _require(len(value) <= 4096, 'UNSUPPORTED_SCHEMA')
        for item in value.values():
            _plain(item, floats=floats, depth=depth + 1)
        return
    raise MechanismInputError('UNSUPPORTED_SCHEMA')


def canonical(value):
    """E1 C: no floating identities, coercion, normalization or key repair."""
    _plain(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, UnicodeError):
        raise MechanismInputError('UNSUPPORTED_SCHEMA') from None


def digest(tag, value):
    return 'sha256:' + hashlib.sha256(canonical({'schema': tag, 'value': value})).hexdigest()


def _native(tag, value):
    # Native private records contain finite timing/config floats. Their original
    # algorithm is retained; E1's integer-only rule applies to exported identity.
    _plain(value, floats=True)
    return 'sha256:' + hashlib.sha256(json.dumps(
        {'schema': tag, 'value': value}, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _without(value, *keys):
    return {k: v for k, v in value.items() if k not in keys}


def _copy(value):
    return json.loads(canonical(value))


def decode_json(raw, *, private=False):
    """Decode exact bytes, rejecting duplicate keys and non-JSON numbers."""
    _require(type(raw) is bytes and len(raw) <= 8_000_000, 'UNSUPPORTED_SCHEMA')
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, 'UNSUPPORTED_SCHEMA')
            result[key] = value
        return result
    def bad_number(_):
        raise MechanismInputError('UNSUPPORTED_SCHEMA')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                           parse_constant=bad_number)
        _plain(value, floats=private)
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise MechanismInputError('UNSUPPORTED_SCHEMA') from None


def _keys(value, keys):
    _require(type(value) is dict and set(value) == set(keys), 'UNSUPPORTED_SCHEMA')


def _int(value):
    _require(type(value) is int and value >= 0, 'UNSUPPORTED_SCHEMA')


def _tagged(value):
    _require(type(value) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value) is not None,
             'UNSUPPORTED_SCHEMA')


def validate_file_hashes(value):
    _keys(value, ('envelope', 'snapshot'))
    for item in value.values():
        _require(type(item) is str and re.fullmatch(r'[0-9a-f]{64}', item) is not None,
                 'UNSUPPORTED_SCHEMA')
    return _copy(value)


def _shape(value, spec):
    try:
        wp05._shape(value, spec)
    except (ValueError, TypeError, KeyError):
        raise MechanismInputError('UNSUPPORTED_SCHEMA') from None


def _refs(refs):
    _require(type(refs) is list and len(refs) <= 16, 'UNSUPPORTED_SCHEMA')
    _shape(refs, [wp05.REF_SHAPE])
    for ref in refs:
        _require(1 <= len(ref['field_selectors']) <= 1, 'UNSUPPORTED_SCHEMA')
        _require(ref['owner'] in {'Blob', 'Repository', 'Review', 'Application',
                                 'ContextSource', 'Method', 'Release'}, 'UNSUPPORTED_SCHEMA')


def _codes(value, allowed):
    _require(type(value) is list and all(type(x) is str and x in allowed for x in value),
             'UNSUPPORTED_SCHEMA')
    _require(value == sorted(set(value)), 'UNSUPPORTED_SCHEMA')


def validate_identity(identity):
    """Closed E1 identity with field-specific P2B wire types."""
    _keys(identity, FROZEN_IDENTITIES[0])
    _plain(identity)
    for key in ('subject_id', 'envelope_digest', 'task_fingerprint', 'output_artifact_id',
                'output_digest', 'output_material_digest', 'result_id', 'result_digest'):
        _tagged(identity[key])
    _shape(identity['native_run_id'], 'id')
    _shape(identity['native_task_id'], 'id')
    _require(identity['schema_version'] == 'vefin-evaluation-case/v1'
             and identity['evaluation_policy_id'] == POLICY
             and identity['rubric_version'] == RUBRIC
             and identity['subject_type'] == wp05.SUBJECT, 'UNSUPPORTED_SCHEMA')
    _shape(identity['graph_identity'], wp05.GRAPH_SHAPE)
    context_spec = dict(turns=[dict(context_id='digest', context_revision='int',
        source_manifest_digest='digest', pre_B_id='digest', request_manifest_digest='digest',
        response_schema_digest='digest')], final_context_id='digest', final_context_revision='int')
    _shape(identity['context_identity'], context_spec)
    _require(1 <= len(identity['context_identity']['turns']) <= 2, 'UNSUPPORTED_PROFILE')
    subject = identity['native_subject_identity']
    spec = {k: 'digest' for k in ('task_fingerprint admission_binding_id result_id result_digest '
        'current_result_id final_context_id final_context_manifest_digest interaction_id').split()}
    spec.update(run_id='id', task_id='id', source_namespace=wp05.NS_SHAPE,
        subject_type={wp05.SUBJECT}, graph=wp05.GRAPH_SHAPE, ordered_B_ids=['digest'],
        result_version='int', final_context_revision='int', dispatch_membership=[dict(
        call_id='id', pre_B_id='digest', receipt_B_id='digest', context_id='digest', context_revision='int')])
    _shape(subject, spec)
    _require(1 <= len(subject['dispatch_membership']) <= 2 and len(subject['ordered_B_ids']) <= 5,
             'UNSUPPORTED_PROFILE')
    scope = identity['source_scope']
    _keys(scope, ('namespace', 'component_scopes', 'classification', 'source_manifest'))
    _shape(scope['namespace'], wp05.NS_SHAPE)
    _require(scope['classification'] == 'LOCAL_SYNTHETIC', 'SOURCE_SCOPE_NOT_ADMITTED')
    _require(scope['component_scopes'] == ['RETAINED_LOCAL_FIXTURE', 'SYNTHETIC_CONTEXT'],
             'SOURCE_SCOPE_NOT_ADMITTED')
    _refs(scope['source_manifest'])
    _require(identity['oracle_refs'] == FROZEN_IDENTITIES[0]['oracle_refs'], 'UNSUPPORTED_SCHEMA')
    validate_file_hashes(identity['input_file_hashes'])
    _require(subject['run_id'] == identity['native_run_id']
        and subject['task_id'] == identity['native_task_id']
        and subject['source_namespace'] == scope['namespace']
        and subject['graph'] == identity['graph_identity']
        and subject['task_fingerprint'] == identity['task_fingerprint']
        and subject['result_id'] == identity['result_id']
        and subject['result_digest'] == identity['result_digest']
        and subject['current_result_id'] == identity['result_id']
        and subject['final_context_id'] == identity['context_identity']['final_context_id']
        and subject['final_context_revision'] == identity['context_identity']['final_context_revision']
        and digest('wp05-valuation-subject/v1', subject) == identity['subject_id'])
    return _copy(identity)


def component_scopes(identity):
    """P1's position-bound receipt exception; no blanket detached exception."""
    validate_identity(identity)
    refs = identity['source_scope']['source_manifest']
    members = identity['native_subject_identity']['dispatch_membership']
    _require(len(refs) == len(members) + 3, 'SOURCE_SCOPE_NOT_ADMITTED')
    receipt_ids = {d['receipt_B_id'] for d in members}
    scopes = set()
    for i, ref in enumerate(refs):
        _require(ref['source_namespace'] == identity['source_scope']['namespace'])
        if 2 <= i < 2 + len(members):
            _require(ref['owner'] == 'Repository' and ref['source_id'] in receipt_ids
                and ref['field_selectors'] == ['/payload_snapshot/execution_receipt']
                and ref['evidence_scope'] == 'DETACHED_OWNER_SNAPSHOT', 'SOURCE_SCOPE_NOT_ADMITTED')
        else:
            owner, scope = ('Blob', 'RETAINED_LOCAL_FIXTURE') if i == 0 else (
                ('Repository', 'RETAINED_LOCAL_FIXTURE') if i == 1 else ('Review', 'SYNTHETIC_CONTEXT'))
            _require(ref['owner'] == owner and ref['evidence_scope'] == scope
                     and ref['field_selectors'] == ['/'], 'SOURCE_SCOPE_NOT_ADMITTED')
            _require(ref['source_id'] == (identity['output_artifact_id'] if i == 0 else identity['native_run_id']),
                     'IDENTITY_MISMATCH')
            scopes.add(scope)
    result = sorted(scopes)
    _require(result == identity['source_scope']['component_scopes'], 'SOURCE_SCOPE_NOT_ADMITTED')
    return result


def validate_dimension(value):
    """Strict P2 dimension decoder; never repair malformed observations."""
    _require(type(value) is dict and value.get('dimension_id') in DIMENSIONS, 'UNSUPPORTED_SCHEMA')
    dim = value['dimension_id']
    keys = {'dimension_id', 'oracle_id', 'rubric_version', 'result', 'reason_codes', 'evidence_refs', 'coverage'}
    _keys(value, keys | ({'context'} if dim == D5 else set()))
    _require(value['oracle_id'] == DIMENSIONS[dim][0] and value['rubric_version'] == RUBRIC
             and value['result'] in DIMENSIONS[dim][1], 'UNSUPPORTED_SCHEMA')
    _codes(value['reason_codes'], REASONS[dim])
    _refs(value['evidence_refs'])
    c = value['coverage']
    _keys(c, ('required_count', 'checked_count', 'missing_count', 'conflict_count'))
    for count in c.values():
        _int(count)
    _require(c['required_count'] == c['checked_count'] + c['missing_count']
             and c['conflict_count'] <= c['checked_count'], 'UNSUPPORTED_SCHEMA')
    if dim == D5:
        tokens = INTEGRITY.intersection(value['reason_codes'])
        _require(len(tokens) == 1, 'UNSUPPORTED_SCHEMA')
        token = next(iter(tokens))
        context = value['context']
        _shape(context, dict(review_id=('id',), record_digest=('digest',),
            native_status=({'PASS', 'BLOCK', 'REVIEW'},), scope=({'RUN_CONTEXT_ONLY'},),
            direct_subject_support={'UNKNOWN'}, check_count='int'))
        _require('DIRECT_SUBJECT_LINK_UNKNOWN' in value['reason_codes'], 'UNSUPPORTED_SCHEMA')
        if value['result'] == 'PARTIAL':
            _require('REVIEW_PARTIAL' in value['reason_codes'], 'UNSUPPORTED_SCHEMA')
        if value['result'] == 'MISSING':
            _require('REVIEW_MISSING' in value['reason_codes'] and all(
                context[k] is None for k in ('review_id', 'record_digest', 'native_status', 'scope'))
                and context['check_count'] == 0, 'UNSUPPORTED_SCHEMA')
        if token == 'D5_INTEGRITY_PASS':
            _require(value['result'] == 'COMPLETE' and c['missing_count'] == 0
                and c['conflict_count'] == 0 and c['checked_count'] > 0
                and all(context[k] is not None for k in ('review_id', 'record_digest', 'native_status', 'scope')),
                'UNSUPPORTED_SCHEMA')
        elif token == 'D5_INTEGRITY_FAIL':
            _require(c['conflict_count'] > 0 and value['evidence_refs']
                and 'REVIEW_IDENTITY_CONFLICT' in value['reason_codes'], 'UNSUPPORTED_SCHEMA')
        else:
            _require(c['missing_count'] > 0 and c['conflict_count'] == 0, 'UNSUPPORTED_SCHEMA')
    elif value['result'] == 'PASS':
        _require(c['missing_count'] == 0 and c['conflict_count'] == 0, 'UNSUPPORTED_SCHEMA')
    return _copy(value)


def _dimension(dim, result, reasons, refs, checks, context=None):
    _require(type(checks) is list and all(x is None or type(x) is bool for x in checks), 'UNSUPPORTED_SCHEMA')
    out = dict(dimension_id=dim, oracle_id=DIMENSIONS[dim][0], rubric_version=RUBRIC,
        result=result, reason_codes=sorted(set(reasons)), evidence_refs=_copy(refs),
        coverage=dict(required_count=len(checks), checked_count=sum(x is not None for x in checks),
                      missing_count=checks.count(None), conflict_count=sum(x is False for x in checks)))
    if dim == D5:
        out['context'] = context
    return validate_dimension(out)


def structural_completeness(answer, refs):
    checks = [True if type(answer) is dict and answer.get(k) is not None else None for k in FIELDS]
    count = sum(x is True for x in checks)
    return _dimension(D1, 'COMPLETE' if count == 5 else 'PARTIAL' if count else 'MISSING',
        [] if count == 5 else ['REQUIRED_FIELD_ABSENT'], refs, checks)


def reference_integrity(required_checks, optional_checks, refs):
    """Checks are derived joins, never caller authority at the cohort boundary.

    Optional checks are only for isolated scoped controls (for example the
    nullable selected-dependency result_id/result_version in WP05's closed
    dependency shape). No source-manifest/receipt requirement becomes optional.
    """
    checks = required_checks + optional_checks
    result = 'FAIL' if False in checks else 'UNKNOWN' if None in checks else 'PASS'
    reasons = (['REFERENCE_CONFLICT'] if False in checks else []) + (
        ['REFERENCE_UNRESOLVED'] if None in checks else [])
    return _dimension(D2, result, reasons, refs, checks)


def review_join(context, checks, refs):
    """P2 completeness is presence; integrity is the independently checked joins."""
    slots = ('review_id', 'run_id', 'reviewer', 'status', 'input_snapshot_hash',
             'record_digest', 'requirement_context_digest', 'checks', 'scope')
    _require(context is None or type(context) is dict, 'UNSUPPORTED_SCHEMA')
    present = sum(context.get(k) is not None and (k != 'checks' or bool(context[k]))
                  for k in slots) if context else 0
    result = 'COMPLETE' if present == len(slots) else 'PARTIAL' if present else 'MISSING'
    integrity = 'FAIL' if False in checks else 'UNKNOWN' if None in checks or result != 'COMPLETE' else 'PASS'
    # Missing context itself is an unresolved integrity obligation.
    if result != 'COMPLETE' and None not in checks:
        checks = checks + [None]
    reasons = ['D5_INTEGRITY_' + integrity, 'DIRECT_SUBJECT_LINK_UNKNOWN']
    if result != 'COMPLETE':
        reasons.append('REVIEW_' + result)
    if integrity == 'FAIL':
        reasons.append('REVIEW_IDENTITY_CONFLICT')
    c = context or {}
    exported = dict(review_id=c.get('review_id'), record_digest=c.get('record_digest'),
        native_status=c.get('status'), scope=c.get('scope'), direct_subject_support='UNKNOWN',
        check_count=len(c.get('checks') or []))
    return _dimension(D5, result, reasons, refs, checks, exported)


def schema_validity(answer, final_response, schema_digest, response_schema_digest, refs):
    """Finite E2 predicates. final_response is retained proof, never synthesized."""
    checks, reasons = [], []
    def check(ok, reason):
        checks.append(ok)
        if ok is not True:
            reasons.append(reason)
    check(True if schema_digest == SCHEMA_PINS['agent_output.py'] else None, 'SCHEMA_UNAVAILABLE')
    check(True if response_schema_digest in wp05.RESPONSE_SCHEMAS.values() else None, 'SCHEMA_UNAVAILABLE')
    if answer is None:
        check(None, 'OUTPUT_UNAVAILABLE')
    elif type(answer) is not dict:
        check(False, 'SCHEMA_TYPE')
    else:
        for key in FIELDS:
            check(key in answer and answer[key] is not None, 'REQUIRED_FIELD_ABSENT')
        check(not (set(answer) - set(FIELDS)), 'SCHEMA_EXTRA_FIELD')
        summary = answer.get('summary')
        check(type(summary) is str, 'SCHEMA_TYPE')
        if type(summary) is str:
            check(1 <= len(summary) <= 800, 'SCHEMA_LENGTH')
            check(bool(summary.strip()), 'SCHEMA_BLANK')
        for field in FIELDS[1:4]:
            items = answer.get(field)
            check(type(items) is list, 'SCHEMA_TYPE')
            if type(items) is list:
                check((1 if field == 'key_findings' else 0) <= len(items) <= 5, 'SCHEMA_LENGTH')
                stripped = []
                for item in items:
                    check(type(item) is str, 'SCHEMA_TYPE')
                    if type(item) is str:
                        check(bool(item.strip()), 'SCHEMA_BLANK')
                        check(len(item.strip()) <= 800, 'SCHEMA_LENGTH')
                        stripped.append(item.strip())
                check(len(stripped) == len(set(stripped)), 'SCHEMA_DUPLICATE_TEXT')
        check(answer.get('requires_follow_up') is False, 'FOLLOW_UP_NOT_FALSE')
    if final_response is None:
        check(None, 'FINAL_BRANCH_INVALID')
    elif response_schema_digest == wp05.RESPONSE_SCHEMAS[2]:
        # The native second turn schema IS the business answer, as retained by
        # WP05; E2 permits this exact final-answer/receipt binding route.
        check(type(final_response) is dict and final_response == answer and 'kind' not in final_response,
              'FINAL_BRANCH_INVALID')
    else:
        check(type(final_response) is dict and set(final_response) == {'kind', 'answer', 'request'}
            and final_response.get('kind') == 'FINAL' and final_response.get('request') is None
            and canonical(final_response.get('answer')) == canonical(answer), 'FINAL_BRANCH_INVALID')
    result = 'FAIL' if False in checks else 'UNKNOWN' if None in checks else 'PASS'
    return _dimension(D6, result, reasons, refs, checks)


def _envelope(envelope):
    try:
        wp05._export_shape(envelope)
    except (ValueError, KeyError, TypeError):
        raise MechanismInputError('UNSUPPORTED_SCHEMA') from None
    _codes(envelope['readiness_reasons'], READINESS_REASONS)
    _require(envelope['envelope_digest'] == digest(wp05.SCHEMA, _without(envelope, 'envelope_digest')),
             'DIGEST_MISMATCH')
    _require(len(envelope['dispatches']) <= 2 and len(envelope['safe_source_manifest']) <= 16,
             'UNSUPPORTED_PROFILE')


def _record_index(snapshot):
    _keys(snapshot, ('source_namespace', 'records'))
    _shape(snapshot['source_namespace'], wp05.NS_SHAPE)
    _require(snapshot['source_namespace']['kind'] == 'DETACHED_OWNER_SNAPSHOT', 'SOURCE_SCOPE_NOT_ADMITTED')
    _require(type(snapshot['records']) is list and len(snapshot['records']) <= 16, 'UNSUPPORTED_SCHEMA')
    records = {}
    for record in snapshot['records']:
        _keys(record, ('owner', 'source_id', 'payload', 'content_digest', 'evidence_scope'))
        _shape(record['owner'], {'Repository', 'Application', 'Blob', 'Review', 'ContextSource', 'Method', 'Release'})
        _shape(record['source_id'], 'id')
        _shape(record['evidence_scope'], {'RETAINED_LOCAL_FIXTURE', 'SYNTHETIC_CONTEXT', 'DETACHED_OWNER_SNAPSHOT'})
        _tagged(record['content_digest'])
        key = record['owner'], record['source_id']
        _require(key not in records, 'IDENTITY_MISMATCH')
        _require(record['content_digest'] == _native('wp05-source-object/v1', record['payload']), 'DIGEST_MISMATCH')
        records[key] = record
    members = sorted([{k: r[k] for k in ('owner', 'source_id', 'content_digest')}
                      for r in records.values()], key=lambda r: (r['owner'], r['source_id'], r['content_digest']))
    _require(snapshot['source_namespace']['anchor_digest'] == digest('wp05-source-bundle/v1', members), 'DIGEST_MISMATCH')
    return records


def _selected(envelope, snapshot):
    records = _record_index(snapshot)
    task = envelope['task_identity']
    _require(task is not None, 'MISSING_REQUIRED_INPUT')
    run_id, task_id = task['run_id'], task['task_id']
    record = records.get(('Repository', run_id))
    _require(record is not None, 'MISSING_REQUIRED_INPUT')
    root = record['payload']
    subject = envelope['subject_identity']
    _require(subject is not None, 'MISSING_REQUIRED_INPUT')
    _require(subject['source_namespace'] == snapshot['source_namespace'])
    rid = root['current_results'].get(task_id)
    _require(rid is not None and rid in root['results'], 'MISSING_REQUIRED_INPUT')
    result = root['results'][rid]
    _require(rid == subject['result_id'] == subject['current_result_id'] == result['result_id'])
    _require(result['result_digest'] == rid == _native(result['schema_version'],
             _without(result, 'result_id', 'result_digest')), 'DIGEST_MISMATCH')
    _require(result['run_id'] == run_id and result['producer_task_id'] == task_id
             and result['graph'] == envelope['graph_identity']
             and result['task_fingerprint'] == task['task_fingerprint'])
    outputs = [m for m in result['output_records'] if m['kind'] == 'AGENT_OUTPUT'
               and m['payload_snapshot'].get('task_id') == task_id]
    _require(len(outputs) == 1, 'MISSING_REQUIRED_INPUT' if not outputs else 'IDENTITY_MISMATCH')
    material = outputs[0]
    p = material['payload_snapshot']
    _require(material['record_schema'] == 'agent-output-record/v1', 'UNSUPPORTED_SCHEMA')
    _require(material['content_digest'] == _native(material['record_schema'], p), 'DIGEST_MISMATCH')
    blob = records.get(('Blob', p['artifact_id']))
    _require(blob is not None, 'MISSING_REQUIRED_INPUT')
    _require(type(blob['payload']) is str, 'UNSUPPORTED_SCHEMA')
    raw = blob['payload'].encode('utf-8')
    h = 'sha256:' + hashlib.sha256(raw).hexdigest()
    _require(h == p['artifact_id'] == p['artifact_sha256'], 'DIGEST_MISMATCH')
    _require(type(p['artifact_size_bytes']) is int and p['artifact_size_bytes'] == len(raw), 'DIGEST_MISMATCH')
    _require(p['artifact_ref'] == 'agent-output://sha256/' + h[7:])
    data = decode_json(raw, private=True)
    _require(p['run_id'] == run_id and p['task_id'] == task_id and p['actor'] == 'valuation_analyst'
             and p['status'] == 'SUCCESS' and p['output_id'] == material['record_id'])
    for key in ('run_id', 'task_id', 'actor', 'structured_output', 'input_refs', 'actual_model'):
        _require(_native('wp06-private-equality/v1', data.get(key)) ==
                 _native('wp06-private-equality/v1', p.get(key)))
    context = envelope['context_identity']
    _require(context is not None, 'MISSING_REQUIRED_INPUT')
    _require(context['final_context_id'] in p['input_refs'])
    dispatch = subject['dispatch_membership'][-1]
    post = root['resolved_inputs'].get(dispatch['receipt_B_id'])
    pre = root['resolved_inputs'].get(dispatch['pre_B_id'])
    _require(post is not None and pre is not None, 'MISSING_REQUIRED_INPUT')
    response = post['payload_snapshot'].get('response')
    schema = pre['payload_snapshot'].get('response_schema_digest')
    _require(schema == context['turns'][-1]['response_schema_digest'])
    return records, root, result, material, data, response, schema


def _review_observation(envelope, records):
    context = envelope['review_context']
    task = envelope['task_identity'] or {}
    record = records.get(('Review', task.get('run_id')))
    expected = [r for r in envelope['safe_source_manifest'] if r['owner'] == 'Review']
    refs = expected or (context or {}).get('source_refs', [])
    if not record:
        return review_join(context, [None] * 5, refs)
    review = record['payload']
    if type(review) is not dict:
        raise MechanismInputError('UNSUPPORTED_SCHEMA')
    if not context:
        # Retain partial slots privately; the closed D5 context exports only its
        # allowed scalar subset. No synthetic completeness or readiness upgrade.
        partial = {k: review.get(k) for k in ('review_id', 'run_id', 'reviewer', 'status',
                   'input_snapshot_hash', 'checks')}
        partial.update(record_digest=record['content_digest'], scope='RUN_CONTEXT_ONLY')
        checks = [review['run_id'] == task.get('run_id') if review.get('run_id') else None,
                  None, None, None, None]
        return review_join(partial, checks, refs)
    checks = [
        review.get('run_id') == context['run_id'] == task.get('run_id'),
        all(r['source_namespace'] == envelope['subject_identity']['source_namespace'] for r in refs)
            if refs else None,
        record['content_digest'] == context['record_digest'] == _native('wp05-source-object/v1', review),
        review.get('input_snapshot_hash') == context['input_snapshot_hash']
            if review.get('input_snapshot_hash') is not None else None,
        _native('wp02-node-binding/v1', review.get('requirement_context')) == context['requirement_context_digest']
            if 'requirement_context' in review else None,
    ]
    for ref in expected:
        checks.append(ref['content_digest'] == record['content_digest'])
    return review_join(context, checks, refs)


def metric_coverage(envelope, metric, *, comparable=False):
    """E3 coverage: provenance-backed zero, explicit unknown subtotal/total."""
    _require(metric in TOKEN_METRICS + LATENCY_METRICS + ('cost',), 'UNSUPPORTED_SCHEMA')
    ds = envelope['dispatches']
    _require(type(ds) is list and len(ds) <= 2, 'UNSUPPORTED_PROFILE')
    aggregate = envelope['usage_aggregate']
    m = aggregate[metric]
    _int(m['observed_metric_count'])
    _shape(m['complete_for_metric'], 'bool')
    expected = m['expected_dispatch_count']
    _require(expected is None or type(expected) is int and 0 <= expected <= 2, 'UNSUPPORTED_SCHEMA')
    if metric in ('cost', 'provider_only_latency'):
        return dict(metric_id=metric, unit='UNKNOWN', scope='UNKNOWN', coverage_status='MISSING',
            expected_dispatch_count=expected, observed_metric_count=0, complete_for_metric=False,
            complete_total=None, observed_subtotal=None, unknown_dispatch_ids=[d['dispatch_id'] for d in ds],
            source_refs=[], comparison_eligible=False,
            exclusion_reasons=['COST_NOT_ADMITTED' if metric == 'cost' else 'PROVIDER_LATENCY_NOT_RETAINED'])
    known, unknown, refs = [], [], []
    for d in ds:
        evidence = d[metric]
        try:
            wp05._evidence(evidence, 'int')
        except (ValueError, KeyError, TypeError):
            raise MechanismInputError('UNSUPPORTED_SCHEMA') from None
        admitted = (evidence['provenance'] == ('RUNTIME_MEASUREMENT' if metric == 'model_turn_elapsed'
                                             else 'PROVIDER_RESPONSE')
                    and evidence['value'] is not None and bool(evidence['source_refs']))
        if metric == 'model_turn_elapsed':
            admitted = admitted and evidence['derivation_rule'] == 'MODEL_TURN_ELAPSED'
        if admitted:
            known.append(evidence['value'])
            for ref in evidence['source_refs']:
                if ref not in refs:
                    refs.append(ref)
        else:
            unknown.append(d['dispatch_id'])
    membership = aggregate['membership_complete'] is True and expected == len(ds) and expected in (1, 2)
    complete = membership and not unknown and len(known) == expected and m['complete_for_metric'] is True
    complete = complete and m['observed_metric_count'] == expected and m['unknown_dispatch_ids'] == []
    subtotal = sum(known) if known else None
    complete = complete and m['complete_total']['value'] == subtotal
    reasons = []
    if not membership:
        reasons.append('INCOMPLETE_DISPATCH_MEMBERSHIP')
    if not complete:
        reasons.append('INCOMPLETE_METRIC_COVERAGE')
    if unknown:
        reasons.append('PROVENANCE_UNKNOWN')
    if not comparable:
        reasons.append('NOT_COMPARABLE')
    out = dict(metric_id=metric, unit='milliseconds' if metric == 'model_turn_elapsed' else 'tokens',
        scope='MODEL_TURN_ELAPSED' if metric == 'model_turn_elapsed' else 'EXACT_DISPATCH',
        coverage_status='COMPLETE' if complete else 'PARTIAL' if known else 'MISSING',
        expected_dispatch_count=expected, observed_metric_count=len(known), complete_for_metric=bool(complete),
        complete_total=subtotal if complete else None, observed_subtotal=subtotal,
        unknown_dispatch_ids=unknown, source_refs=refs, comparison_eligible=bool(complete and comparable),
        exclusion_reasons=sorted(reasons))
    _refs(refs)
    return out


def task_input_key(identity, envelope):
    validate_identity(identity)
    _envelope(envelope)
    _require(identity['envelope_digest'] == envelope['envelope_digest'])
    return dict(subject_type=identity['subject_type'], task_fingerprint=identity['task_fingerprint'],
        graph_identity=identity['graph_identity'], context_identity=identity['context_identity'],
        dependency_identity=envelope['dependency_identity'],
        method_dependency_context=envelope['method_dependency_context'],
        output_contract=dict(business_schema_digest=SCHEMA_PINS['agent_output.py'],
            response_schema_digests=[t['response_schema_digest'] for t in identity['context_identity']['turns']]),
        rubric_version=RUBRIC, source_scope_class={k: identity['source_scope'][k]
            for k in ('classification', 'component_scopes')}, profile=PROFILE[:])


def compare_keys(left, right, *, same_case=False):
    """Isolated equality predicate; it makes no model-comparison admission."""
    keys = {'subject_type', 'task_fingerprint', 'graph_identity', 'context_identity',
            'dependency_identity', 'method_dependency_context', 'output_contract', 'rubric_version',
            'source_scope_class', 'profile'}
    _keys(left, keys)
    _keys(right, keys)
    if same_case:
        return False, ['SAME_CASE']
    reasons = sorted(k for k in keys if left[k] is None or right[k] is None
                     or canonical(left[k]) != canonical(right[k]))
    return not reasons, reasons


def compare_cases(left, left_envelope, right, right_envelope, *, dimension_id=None):
    if left['case_validity'] != 'VALID' or right['case_validity'] != 'VALID':
        return False, ['NOT_COMPARABLE']
    same = left['case_id'] == right['case_id']
    ok, reasons = compare_keys(task_input_key(left['identity'], left_envelope),
                              task_input_key(right['identity'], right_envelope), same_case=same)
    if dimension_id == D5 and not same:
        fields = ('review_id', 'record_digest', 'input_snapshot_hash', 'scope')
        a, b = left_envelope['review_context'], right_envelope['review_context']
        if a is None or b is None or any(a[k] != b[k] for k in fields):
            ok, reasons = False, sorted(set(reasons) | {'review_context'})
    return ok, reasons


def _case_identity(envelope, snapshot, material, file_hashes):
    p = material['payload_snapshot']
    subject = envelope['subject_identity']
    identity = dict(schema_version='vefin-evaluation-case/v1', evaluation_policy_id=POLICY,
        source_scope=dict(namespace=snapshot['source_namespace'],
            component_scopes=['RETAINED_LOCAL_FIXTURE', 'SYNTHETIC_CONTEXT'], classification='LOCAL_SYNTHETIC',
            source_manifest=envelope['safe_source_manifest']), subject_type=wp05.SUBJECT,
        subject_id=envelope['subject_id'], envelope_digest=envelope['envelope_digest'],
        native_run_id=subject['run_id'], native_task_id=subject['task_id'],
        task_fingerprint=subject['task_fingerprint'], graph_identity=envelope['graph_identity'],
        context_identity=envelope['context_identity'], native_subject_identity=subject,
        output_artifact_id=p['artifact_id'], output_digest=p['artifact_sha256'],
        output_material_digest=material['content_digest'], result_id=subject['result_id'],
        result_digest=subject['result_digest'], rubric_version=RUBRIC,
        oracle_refs=FROZEN_IDENTITIES[0]['oracle_refs'], input_file_hashes=file_hashes)
    component_scopes(identity)
    return _copy(identity)


def inspect_case(envelope_bytes, snapshot_bytes, schema_pins):
    """Pure isolated bound-case inspection; never changes the primary manifest.

    Returns (case or None, closed diagnostic). A synthetic control may use this
    function to prove a predicate, but evaluate_mechanism additionally enforces
    all eight frozen file hashes and the four literal case identities.
    """
    _require(type(envelope_bytes) is bytes and type(snapshot_bytes) is bytes, 'MISSING_REQUIRED_INPUT')
    hashes = dict(envelope=hashlib.sha256(envelope_bytes).hexdigest(),
                  snapshot=hashlib.sha256(snapshot_bytes).hexdigest())
    diagnostic = dict(input_file_hashes=hashes, case_id=None, readiness_state=None,
                      readiness_reasons=[], invalid_reasons=[])
    try:
        envelope = decode_json(envelope_bytes)
        _envelope(envelope)
        diagnostic.update(readiness_state=envelope['readiness_state'],
                          readiness_reasons=envelope['readiness_reasons'][:])
        _plain(schema_pins)
        _require(schema_pins == SCHEMA_PINS, 'UNSUPPORTED_SCHEMA')
        snapshot = decode_json(snapshot_bytes, private=True)
        records = _record_index(snapshot)
        task = envelope['task_identity']
        if task is None:
            _require(envelope['readiness_state'] != 'READY', 'MISSING_REQUIRED_INPUT')
            diagnostic['invalid_reasons'] = ['WP05_NOT_READY']
            return None, diagnostic
        selector = dict(source_namespace=snapshot['source_namespace'], run_id=task['run_id'], task_id=task['task_id'])
        # Existing accepted pure WP05 projection validates all native A/B/R/K
        # joins and provenance. Reprojection grants no new runtime authority.
        projected = wp05.build_evaluation_input(snapshot, snapshot, selector)
        if projected != envelope:
            reasons = set(projected['readiness_reasons'])
            if reasons.intersection({'IDENTITY_MISMATCH', 'USAGE_IDENTITY_MISMATCH', 'STALE_RESULT_POINTER'}):
                raise MechanismInputError('IDENTITY_MISMATCH')
            if reasons - set(envelope['readiness_reasons']):
                raise MechanismInputError('MISSING_REQUIRED_INPUT')
            raise MechanismInputError('IDENTITY_MISMATCH')
        if envelope['readiness_state'] != 'READY':
            if set(envelope['readiness_reasons']).intersection({'IDENTITY_MISMATCH', 'USAGE_IDENTITY_MISMATCH'}):
                raise MechanismInputError('IDENTITY_MISMATCH')
            diagnostic['invalid_reasons'] = (['MISSING_REQUIRED_INPUT'] if 'MISSING_REVIEW' in envelope['readiness_reasons'] else ['WP05_NOT_READY'])
            return None, diagnostic
        _require(envelope['readiness_reasons'] == [], 'IDENTITY_MISMATCH')
        records, root, result, material, data, response, schema = _selected(envelope, snapshot)
        identity = _case_identity(envelope, snapshot, material, hashes)
        refs = identity['source_scope']['source_manifest']
        # Exact input_refs resolution; narrative strings never become citations.
        known_ids = {identity['native_task_id'], identity['context_identity']['final_context_id']}
        known_ids.update(d['source_id'] for d in envelope['dependency_identity'])
        known_ids.update(m['record_id'] for m in result['output_records'])
        input_checks = [ref in known_ids for ref in data['input_refs']]
        d2 = reference_integrity([True] * len(refs) + input_checks, [], refs)
        d5 = _review_observation(envelope, records)
        d6 = schema_validity(data['structured_output'], response, schema_pins['agent_output.py'], schema, refs[:1])
        case_id = digest('wp06-case-identity/v1', identity)
        diagnostic['case_id'] = case_id
        invalid = []
        if 'D5_INTEGRITY_FAIL' in d5['reason_codes']:
            invalid.append('IDENTITY_MISMATCH')
        elif 'D5_INTEGRITY_UNKNOWN' in d5['reason_codes']:
            invalid.append('MISSING_REQUIRED_INPUT')
        case = dict(identity=identity, case_id=case_id,
            case_validity='INVALID' if invalid else 'VALID', invalid_reasons=invalid,
            dimension_results=[] if invalid else [structural_completeness(data['structured_output'], refs[:1]), d2, d5, d6],
            usage_coverage=[metric_coverage(envelope, m) for m in TOKEN_METRICS],
            latency_coverage=[metric_coverage(envelope, m) for m in LATENCY_METRICS],
            cost_coverage=metric_coverage(envelope, 'cost'),
            review_context_ref={k: envelope['review_context'][k] for k in ('review_id', 'record_digest', 'scope', 'source_refs')})
        case['evaluation_digest'] = digest('wp06-evaluation-result/v1', case)
        diagnostic['invalid_reasons'] = invalid[:]
        return case, diagnostic
    except MechanismInputError as exc:
        diagnostic['invalid_reasons'] = [exc.args[0]]
    except (KeyError, TypeError, IndexError, ValueError, AttributeError, RecursionError, UnicodeError):
        diagnostic['invalid_reasons'] = ['MISSING_REQUIRED_INPUT']
    return None, diagnostic


def dimension_counts(stratum_id, dimension_id, observations):
    """P2: None is excluded; integrity UNKNOWN overlaps assessed completeness."""
    _require(stratum_id in STRATA and dimension_id in DIMENSIONS, 'UNSUPPORTED_SCHEMA')
    buckets = {outcome: 0 for outcome in DIMENSIONS[dimension_id][1]}
    unknown = assessed = 0
    for observation in observations:
        if observation is None:
            continue
        validate_dimension(observation)
        _require(observation['dimension_id'] == dimension_id, 'UNSUPPORTED_SCHEMA')
        buckets[observation['result']] += 1
        assessed += 1
        unknown += int('D5_INTEGRITY_UNKNOWN' in observation['reason_codes'] if dimension_id == D5
                       else observation['result'] == 'UNKNOWN')
    return dict(stratum_id=stratum_id, dimension_id=dimension_id, requested_count=len(observations),
        eligible_count=assessed, assessed_count=assessed, unknown_count=unknown,
        excluded_count=len(observations) - assessed, outcome_counts=buckets)


def evaluate_mechanism(supplied_package):
    """Evaluate the exact four frozen members, with no I/O or mutable owners."""
    _keys(supplied_package, ('manifest', 'envelopes', 'snapshots', 'schema_pins'))
    manifest = supplied_package['manifest']
    _plain(manifest)
    _require(canonical(manifest) == canonical(FROZEN_MANIFEST), 'MEMBERSHIP_DRIFT')
    _plain(supplied_package['schema_pins'])
    _require(supplied_package['schema_pins'] == SCHEMA_PINS, 'UNSUPPORTED_SCHEMA')
    envelopes, snapshots = supplied_package['envelopes'], supplied_package['snapshots']
    _require(type(envelopes) is list and type(snapshots) is list and len(envelopes) == len(snapshots) == 4,
             'MEMBERSHIP_DRIFT')
    cases, diagnostics, aligned, exclusions = [], [], [], []
    for i, (envelope, snapshot) in enumerate(zip(envelopes, snapshots)):
        expected = FROZEN_IDENTITIES[i]
        if envelope is None or snapshot is None:
            case = None
            diag = dict(input_file_hashes=_copy(expected['input_file_hashes']), case_id=None,
                readiness_state=None, readiness_reasons=[], invalid_reasons=['MISSING_REQUIRED_INPUT'])
        else:
            case, diag = inspect_case(envelope, snapshot, supplied_package['schema_pins'])
            if diag['input_file_hashes'] != expected['input_file_hashes']:
                diag['invalid_reasons'] = sorted(set(diag['invalid_reasons']) | {'DIGEST_MISMATCH'})
                case = None
            if case is not None and (case['identity'] != expected or case['case_id'] != manifest['member_case_ids'][i]):
                diag['invalid_reasons'] = sorted(set(diag['invalid_reasons']) | {'IDENTITY_MISMATCH'})
                case = None
        diagnostics.append(diag)
        if case is not None and case['case_validity'] == 'VALID':
            cases.append(case)
            aligned.append(case['evaluation_digest'])
        else:
            aligned.append(None)
            exclusions.append(dict(case_id=manifest['member_case_ids'][i], readiness_state=diag['readiness_state'],
                readiness_reasons=diag['readiness_reasons'], invalid_reasons=diag['invalid_reasons']))
    by_id = {c['case_id']: c for c in cases}
    counts, metrics = [], []
    for stratum, indices in zip(STRATA, ((0, 2), (1, 3))):
        ids = [manifest['member_case_ids'][i] for i in indices]
        for dimension_id in DIMENSIONS:
            obs = [next(d for d in by_id[cid]['dimension_results'] if d['dimension_id'] == dimension_id)
                   if cid in by_id else None for cid in ids]
            counts.append(dimension_counts(stratum, dimension_id, obs))
        for metric in TOKEN_METRICS + LATENCY_METRICS + ('cost',):
            values = []
            for cid in ids:
                if cid in by_id:
                    case = by_id[cid]
                    values.extend(m for m in case['usage_coverage'] + case['latency_coverage'] + [case['cost_coverage']]
                                  if m['metric_id'] == metric)
            reasons = {'NOT_COMPARABLE'}
            for m in values:
                reasons.update(m['exclusion_reasons'])
            if len(values) != 2:
                reasons.add('INCOMPLETE_METRIC_COVERAGE')
            metrics.append(dict(stratum_id=stratum, metric_id=metric, member_case_ids=ids,
                complete_member_count=sum(m['complete_for_metric'] for m in values), requested_member_count=2,
                comparison_eligible=False, exclusion_reasons=sorted(reasons)))
    cohort = _copy(manifest)
    cohort.update(member_evaluation_digests=aligned, dimension_counts=counts, metric_coverage=metrics,
                  excluded_members=exclusions, cohort_validity='INVALID' if exclusions else 'VALID')
    cohort['cohort_digest'] = digest('wp06-cohort-result/v1', cohort)
    report = dict(schema_version='vefin-mechanism-evaluation/v1',
        authority_role='DERIVED_OFFLINE_EVALUATION_EVIDENCE', cases=cases, cohort=cohort, diagnostics=diagnostics)
    validate_report(report)
    return _copy(report)


def _validate_metric(metric):
    _keys(metric, ('metric_id', 'unit', 'scope', 'coverage_status', 'expected_dispatch_count',
        'observed_metric_count', 'complete_for_metric', 'complete_total', 'observed_subtotal',
        'unknown_dispatch_ids', 'source_refs', 'comparison_eligible', 'exclusion_reasons'))
    _shape(metric['metric_id'], set(TOKEN_METRICS + LATENCY_METRICS + ('cost',)))
    _shape(metric['unit'], {'tokens', 'milliseconds', 'UNKNOWN'})
    _shape(metric['scope'], {'EXACT_DISPATCH', 'MODEL_TURN_ELAPSED', 'UNKNOWN'})
    _shape(metric['coverage_status'], {'COMPLETE', 'PARTIAL', 'MISSING'})
    for key in ('expected_dispatch_count', 'complete_total', 'observed_subtotal'):
        if metric[key] is not None:
            _int(metric[key])
    _int(metric['observed_metric_count'])
    for key in ('complete_for_metric', 'comparison_eligible'):
        _shape(metric[key], 'bool')
    _shape(metric['unknown_dispatch_ids'], ['id'])
    _require(len(metric['unknown_dispatch_ids']) <= 2, 'UNSUPPORTED_SCHEMA')
    _refs(metric['source_refs'])
    _codes(metric['exclusion_reasons'], METRIC_REASONS)
    if metric['complete_for_metric']:
        _require(metric['coverage_status'] == 'COMPLETE' and metric['complete_total'] is not None
            and metric['observed_metric_count'] == metric['expected_dispatch_count']
            and metric['unknown_dispatch_ids'] == [], 'UNSUPPORTED_SCHEMA')
    else:
        _require(metric['complete_total'] is None and metric['comparison_eligible'] is False,
                 'UNSUPPORTED_SCHEMA')
    if metric['metric_id'] in ('cost', 'provider_only_latency'):
        reason = 'COST_NOT_ADMITTED' if metric['metric_id'] == 'cost' else 'PROVIDER_LATENCY_NOT_RETAINED'
        _require(metric['unit'] == metric['scope'] == 'UNKNOWN'
            and metric['coverage_status'] == 'MISSING' and metric['observed_metric_count'] == 0
            and metric['complete_for_metric'] is False and metric['observed_subtotal'] is None
            and metric['source_refs'] == [] and metric['exclusion_reasons'] == [reason], 'UNSUPPORTED_SCHEMA')


def _validate_report(report):
    """Recursively closed public export, including digests and accounting."""
    _plain(report)
    _keys(report, ('schema_version', 'authority_role', 'cases', 'cohort', 'diagnostics'))
    _require(report['schema_version'] == 'vefin-mechanism-evaluation/v1'
        and report['authority_role'] == 'DERIVED_OFFLINE_EVALUATION_EVIDENCE', 'UNSUPPORTED_SCHEMA')
    _require(type(report['cases']) is list and len(report['cases']) <= 4
        and type(report['diagnostics']) is list and len(report['diagnostics']) == 4, 'UNSUPPORTED_SCHEMA')
    for diagnostic in report['diagnostics']:
        _keys(diagnostic, ('input_file_hashes', 'case_id', 'readiness_state', 'readiness_reasons', 'invalid_reasons'))
        validate_file_hashes(diagnostic['input_file_hashes'])
        _shape(diagnostic['case_id'], ('digest',))
        _shape(diagnostic['readiness_state'], ({'READY', 'PARTIALLY_READY', 'NOT_READY', 'LEGACY_UNKNOWN'},))
        _codes(diagnostic['readiness_reasons'], READINESS_REASONS)
        _codes(diagnostic['invalid_reasons'], INVALID_REASONS)
    ids = []
    for case in report['cases']:
        _keys(case, ('identity', 'case_id', 'case_validity', 'invalid_reasons', 'dimension_results',
            'usage_coverage', 'latency_coverage', 'cost_coverage', 'review_context_ref', 'evaluation_digest'))
        validate_identity(case['identity'])
        component_scopes(case['identity'])
        _tagged(case['case_id'])
        _require(case['case_id'] == digest('wp06-case-identity/v1', case['identity']))
        _require(case['case_id'] in FROZEN_MANIFEST['member_case_ids'])
        pos = FROZEN_MANIFEST['member_case_ids'].index(case['case_id'])
        _require(case['identity'] == FROZEN_IDENTITIES[pos])
        _shape(case['case_validity'], {'VALID', 'INVALID', 'EXCLUDED_DIAGNOSTIC'})
        _codes(case['invalid_reasons'], INVALID_REASONS)
        _require(type(case['dimension_results']) is list, 'UNSUPPORTED_SCHEMA')
        if case['case_validity'] == 'VALID':
            _require(case['invalid_reasons'] == [] and [d['dimension_id'] for d in case['dimension_results']] == list(DIMENSIONS),
                     'UNSUPPORTED_SCHEMA')
        else:
            _require(case['dimension_results'] == [], 'UNSUPPORTED_SCHEMA')
        for dimension in case['dimension_results']:
            validate_dimension(dimension)
        for key, expected in (('usage_coverage', TOKEN_METRICS), ('latency_coverage', LATENCY_METRICS)):
            _require(type(case[key]) is list and [m['metric_id'] for m in case[key]] == list(expected), 'UNSUPPORTED_SCHEMA')
            for metric in case[key]:
                _validate_metric(metric)
        _validate_metric(case['cost_coverage'])
        _require(case['cost_coverage']['metric_id'] == 'cost', 'UNSUPPORTED_SCHEMA')
        review = case['review_context_ref']
        if review is not None:
            _shape(review, dict(review_id='id', record_digest='digest', scope={'RUN_CONTEXT_ONLY'}, source_refs=[wp05.REF_SHAPE]))
            _refs(review['source_refs'])
        _tagged(case['evaluation_digest'])
        _require(case['evaluation_digest'] == digest('wp06-evaluation-result/v1', _without(case, 'evaluation_digest')))
        ids.append(case['case_id'])
    _require(len(ids) == len(set(ids)), 'DUPLICATE_MEMBER')
    cohort = report['cohort']
    extra = {'member_evaluation_digests', 'dimension_counts', 'metric_coverage', 'excluded_members', 'cohort_validity', 'cohort_digest'}
    _keys(cohort, set(FROZEN_MANIFEST) | extra)
    _require({k: cohort[k] for k in FROZEN_MANIFEST} == FROZEN_MANIFEST, 'MEMBERSHIP_DRIFT')
    _require(type(cohort['member_evaluation_digests']) is list and len(cohort['member_evaluation_digests']) == 4,
             'MEMBERSHIP_DRIFT')
    _shape(cohort['member_evaluation_digests'], [('digest',)])
    by_id = {case['case_id']: case for case in report['cases']}
    _require(ids == [cid for cid in FROZEN_MANIFEST['member_case_ids'] if cid in by_id], 'MEMBERSHIP_DRIFT')
    for cid, value in zip(FROZEN_MANIFEST['member_case_ids'], cohort['member_evaluation_digests']):
        _require(value == (by_id[cid]['evaluation_digest'] if cid in by_id else None))
    _require(type(cohort['dimension_counts']) is list and len(cohort['dimension_counts']) == 8, 'UNSUPPORTED_SCHEMA')
    for idx, count in enumerate(cohort['dimension_counts']):
        _keys(count, ('stratum_id', 'dimension_id', 'requested_count', 'eligible_count', 'assessed_count',
                     'unknown_count', 'excluded_count', 'outcome_counts'))
        dim = list(DIMENSIONS)[idx % 4]
        stratum = STRATA[idx // 4]
        members = (0, 2) if idx < 4 else (1, 3)
        obs = [next(d for d in by_id[FROZEN_MANIFEST['member_case_ids'][i]]['dimension_results']
                    if d['dimension_id'] == dim) if FROZEN_MANIFEST['member_case_ids'][i] in by_id else None
               for i in members]
        for k in ('requested_count', 'eligible_count', 'assessed_count', 'unknown_count', 'excluded_count'):
            _int(count[k])
        _keys(count['outcome_counts'], DIMENSIONS[dim][1])
        for v in count['outcome_counts'].values():
            _int(v)
        _require(count == dimension_counts(stratum, dim, obs), 'UNSUPPORTED_SCHEMA')
    _require(type(cohort['metric_coverage']) is list and len(cohort['metric_coverage']) == 14, 'UNSUPPORTED_SCHEMA')
    metric_ids = TOKEN_METRICS + LATENCY_METRICS + ('cost',)
    for idx, metric in enumerate(cohort['metric_coverage']):
        _keys(metric, ('stratum_id', 'metric_id', 'member_case_ids', 'complete_member_count',
                      'requested_member_count', 'comparison_eligible', 'exclusion_reasons'))
        _int(metric['complete_member_count'])
        _int(metric['requested_member_count'])
        _shape(metric['comparison_eligible'], 'bool')
        _codes(metric['exclusion_reasons'], METRIC_REASONS)
        indices = (0, 2) if idx < 7 else (1, 3)
        _require(metric['stratum_id'] == STRATA[idx // 7] and metric['metric_id'] == metric_ids[idx % 7]
            and metric['member_case_ids'] == [FROZEN_MANIFEST['member_case_ids'][i] for i in indices]
            and metric['requested_member_count'] == 2 and metric['complete_member_count'] <= 2
            and metric['comparison_eligible'] is False and 'NOT_COMPARABLE' in metric['exclusion_reasons'], 'UNSUPPORTED_SCHEMA')
    _require(type(cohort['excluded_members']) is list and len(cohort['excluded_members']) <= 4, 'UNSUPPORTED_SCHEMA')
    missing = [cid for cid in FROZEN_MANIFEST['member_case_ids'] if cid not in by_id]
    _require([x['case_id'] for x in cohort['excluded_members']] == missing, 'MEMBERSHIP_DRIFT')
    for excluded in cohort['excluded_members']:
        _keys(excluded, ('case_id', 'readiness_state', 'readiness_reasons', 'invalid_reasons'))
        _tagged(excluded['case_id'])
        _shape(excluded['readiness_state'], ({'READY', 'PARTIALLY_READY', 'NOT_READY', 'LEGACY_UNKNOWN'},))
        _codes(excluded['readiness_reasons'], READINESS_REASONS)
        _codes(excluded['invalid_reasons'], INVALID_REASONS)
    _require(cohort['cohort_validity'] == ('INVALID' if missing else 'VALID'))
    _tagged(cohort['cohort_digest'])
    _require(cohort['cohort_digest'] == digest('wp06-cohort-result/v1', _without(cohort, 'cohort_digest')))
    return _copy(report)


def validate_report(report):
    """Reject malformed exports with a fixed code, without exception payloads."""
    try:
        return _validate_report(report)
    except MechanismInputError:
        raise
    except (TypeError, KeyError, IndexError, ValueError, AttributeError, RecursionError):
        raise MechanismInputError('UNSUPPORTED_SCHEMA') from None
