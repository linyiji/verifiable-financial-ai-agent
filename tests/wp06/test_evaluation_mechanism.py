"""A01–A30 / P3 bounded controls. No provider, runtime fixture builder or writes.

Only the eight E4 pinned files are private primary inputs. All counterexamples
are in-memory copies. Independent arithmetic below does not use WP06 helpers.
Builder evidence is not independent acceptance; A30 checks only its boundary.
"""
import ast
import builtins
import hashlib
import importlib
import io
import json
import os
import socket
import subprocess
from copy import deepcopy
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from src.application import evaluation_input as wp05
from src.application import evaluation_mechanism as mechanism

HERE = Path(__file__).parent
REPO = HERE.parents[1]
SPEC = json.loads((HERE / 'fixtures/mechanism_cases.json').read_text())
LABELS = ['F_READY_ONE', 'F_READY_TWO', 'zero', 'zero_two']
D1 = 'D1_STRUCTURAL_COMPLETENESS'
D2 = 'D2_REFERENCE_INTEGRITY'
D5 = 'D5_REVIEW_CONTEXT_JOINING'
D6 = 'D6_OUTPUT_SCHEMA_VALIDITY'
RUBRIC = 'WP06_D1_D2_D5_D6_RUBRIC_V1'
CASE_IDS = [
    'sha256:201b754ffcccbacdb57299066d4d75977a4926998a0b818628377c7b1d175c6b',
    'sha256:707dd815a56f67782ad9539924341be8c81ac004d977364d1ccfa39c888bd1c3',
    'sha256:9e309b00743b3ba56cf38a32264171f876f4fc60ebfadc8046a6652b97bc8bf8',
    'sha256:e1de89f410e4cc298ef4b9b6c916aaada234893f7ea3727e035a91679c137500',
]
COHORT_ID = 'sha256:87b6f7eb4c80471496fc05d60418bdced1aebc6f29087b5acf1a24ce8a5f2abe'


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def h(value, tag):
    return 'sha256:' + hashlib.sha256(encode({'schema': tag, 'value': value})).hexdigest()


def without(value, *keys):
    return {k: v for k, v in value.items() if k not in keys}


def obj(snapshot, owner):
    return next(r['payload'] for r in snapshot['records'] if r['owner'] == owner)


def selector(snapshot):
    root = obj(snapshot, 'Repository')
    task_id = next(k for k, v in root['attempts'].items()
                   if v['admission']['authorized_input_requirements']['task']['task_type'] == 'valuation_analysis')
    return dict(source_namespace=deepcopy(snapshot['source_namespace']), run_id=root['run_id'], task_id=task_id)


def selected(snapshot):
    root = obj(snapshot, 'Repository')
    tid = selector(snapshot)['task_id']
    return root, root['results'][root['current_results'][tid]]


def seal(snapshot):
    for record in snapshot['records']:
        record['content_digest'] = h(record['payload'], 'wp05-source-object/v1')
    members = sorted([{k: r[k] for k in ('owner', 'source_id', 'content_digest')}
                     for r in snapshot['records']], key=lambda r: (r['owner'], r['source_id'], r['content_digest']))
    snapshot['source_namespace']['anchor_digest'] = h(members, 'wp05-source-bundle/v1')
    return snapshot


def resign_result(snapshot):
    root, result = selected(snapshot)
    for material in result['output_records']:
        if material['kind'] == 'TASK_OUTPUT_SNAPSHOT':
            material['payload_snapshot']['resolved_inputs'] = result['resolved_input_binding_ids'][:]
            material['record_id'] = material['content_digest'] = h(material['payload_snapshot'], material['record_schema'])
    old = result['result_id']
    result['result_id'] = result['result_digest'] = h(without(result, 'result_id', 'result_digest'), result['schema_version'])
    root['results'].pop(old)
    root['results'][result['result_id']] = result
    root['current_results'][result['producer_task_id']] = result['result_id']
    seal(snapshot)


def project(snapshot):
    return wp05.build_evaluation_input(snapshot, snapshot, selector(snapshot))


def change_answer(snapshot, answer, *, wrapper_kind='FINAL'):
    """Coherently bind a one-turn control to raw Blob, material, B and current R."""
    root, result = selected(snapshot)
    material = next(m for m in result['output_records'] if m['kind'] == 'AGENT_OUTPUT')
    p = material['payload_snapshot']
    blob = next(r for r in snapshot['records'] if r['owner'] == 'Blob' and r['source_id'] == p['artifact_id'])
    raw = json.loads(blob['payload'])
    raw['structured_output'] = deepcopy(answer)
    blob['payload'] = encode(raw).decode()
    raw_hash = 'sha256:' + hashlib.sha256(blob['payload'].encode()).hexdigest()
    old_output_id = p['output_id']
    p.update(structured_output=deepcopy(answer), artifact_id=raw_hash, artifact_sha256=raw_hash,
        artifact_ref='agent-output://sha256/' + raw_hash[7:], artifact_size_bytes=len(blob['payload'].encode()),
        output_id='AGOUT-' + str(uuid5(NAMESPACE_URL, f"{p['run_id']}:{p['task_id']}:{raw_hash[7:]}")))
    material['record_id'] = p['output_id']
    material['content_digest'] = h(p, material['record_schema'])
    blob['source_id'] = raw_hash
    result['observed_execution']['agent_outputs'] = [deepcopy(p)]
    for m in result['output_records']:
        if m['kind'] == 'TASK_OUTPUT_SNAPSHOT':
            task = m['payload_snapshot']['task_output']
            task.update(deepcopy(answer))
            task['agent_output_id'] = p['output_id']
            for outcome in m['payload_snapshot']['output_outcomes']:
                outcome['refs'] = [p['output_id'] if x == old_output_id else x for x in outcome['refs']]
    post = next(root['resolved_inputs'][bid] for bid in result['resolved_input_binding_ids']
                if root['resolved_inputs'][bid]['step_id'].endswith(':receipt'))
    old = post['resolved_input_binding_id']
    pp = post['payload_snapshot']
    pp['response'] = dict(kind=wrapper_kind, answer=deepcopy(answer), request=None)
    outcome_digest = h(pp['response'], 'wp02-node-binding/v1')
    pp['execution_receipt']['outcome_digest'] = outcome_digest
    pp['interaction_counters']['calls'][0]['outcome_digest'] = outcome_digest
    post['input_digest'] = h(pp, 'wp02-input-payload/v1')
    new = h(without(post, 'resolved_input_binding_id'), post['schema_version'])
    post['resolved_input_binding_id'] = new
    root['resolved_inputs'].pop(old)
    root['resolved_inputs'][new] = post
    result['resolved_input_binding_ids'] = [new if x == old else x for x in result['resolved_input_binding_ids']]
    su = result['observed_execution']['wp03_context']
    su['receipt_refs'] = [new]
    su['calls'] = [deepcopy(pp['execution_receipt'])]
    resign_result(snapshot)
    return snapshot


@pytest.fixture(scope='module')
def package():
    """Exact physical allowlist; no directory enumeration or fallback lookup."""
    envelopes, snapshots = [], []
    for row in SPEC['inputs']:
        for kind, array in (('envelope', envelopes), ('snapshot', snapshots)):
            path = Path(row[kind + '_path'])
            assert not path.is_symlink() and str(path.resolve()) == str(path)
            raw = path.read_bytes()
            assert hashlib.sha256(raw).hexdigest() == row[kind + '_sha256']
            array.append(raw)
    pins = {Path(p).name: 'sha256:' + value for p, value in SPEC['source_pins'].items()}
    return dict(manifest=deepcopy(SPEC['manifest']), envelopes=envelopes, snapshots=snapshots, schema_pins=pins)


@pytest.fixture(scope='module')
def report(package):
    return mechanism.evaluate_mechanism(package)


def dimension(case, name):
    return next(d for d in case['dimension_results'] if d['dimension_id'] == name)


def base_context(package):
    return json.loads(package['envelopes'][0])['review_context']


def review_refs(package):
    return base_context(package)['source_refs']


def test_A01_A30_baseline_scope_pins_and_builder_boundary():
    assert subprocess.check_output(['git', 'branch', '--show-current'], cwd=REPO, text=True).strip() == SPEC['baseline']['branch']
    for ref, key in (('HEAD', 'head'), ('HEAD^{tree}', 'tree')):
        assert subprocess.check_output(['git', 'rev-parse', ref], cwd=REPO, text=True).strip() == SPEC['baseline'][key]
    tracked = set(subprocess.check_output(['git', 'diff', '--name-only'], cwd=REPO, text=True).splitlines())
    assert tracked <= {'src/application/__init__.py'}
    for path, expected in SPEC['source_pins'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
    for path, expected in SPEC['authority_pins'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
    allowed = {'src/application/evaluation_mechanism.py', 'tests/wp06/test_evaluation_mechanism.py',
               'tests/wp06/fixtures/mechanism_cases.json'}
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=REPO, text=True).splitlines()
    assert {p for p in untracked if not p.startswith('docs/audits/')} == allowed
    assert subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=REPO) == b''
    assert not (REPO / 'tests/wp06/__init__.py').exists()
    assert SPEC['controls_scope'] == 'LOCAL_SYNTHETIC_ISOLATED_CONTROLS_NEVER_PRIMARY_MEMBERS'


def test_A02_A08_P3_SCOPE_01_HASH_01_frozen_round_trip(package, report):
    assert [r['label'] for r in SPEC['inputs']] == LABELS
    assert report['cohort']['cohort_id'] == COHORT_ID
    assert h(without(SPEC['manifest'], 'cohort_id'), 'wp06-cohort-identity/v1') == COHORT_ID
    assert report['cohort']['cohort_validity'] == 'VALID'
    assert [c['case_id'] for c in report['cases']] == CASE_IDS
    detached = 0
    for i, case in enumerate(report['cases']):
        identity = json.loads(encode(case['identity']))
        assert identity == SPEC['cases'][i]['identity']
        assert mechanism.validate_identity(identity) == identity
        assert h(identity, 'wp06-case-identity/v1') == CASE_IDS[i]
        assert mechanism.component_scopes(identity) == ['RETAINED_LOCAL_FIXTURE', 'SYNTHETIC_CONTEXT']
        assert identity['source_scope']['classification'] == 'LOCAL_SYNTHETIC'
        assert identity['source_scope']['source_manifest'] == json.loads(package['envelopes'][i])['safe_source_manifest']
        for ref in identity['source_scope']['source_manifest']:
            detached += ref['evidence_scope'] == 'DETACHED_OWNER_SNAPSHOT'
        assert h(without(case, 'evaluation_digest'), 'wp06-evaluation-result/v1') == case['evaluation_digest']
        assert report['diagnostics'][i]['input_file_hashes'] == identity['input_file_hashes']
    assert detached == 6
    for field in ('member_case_ids', 'member_envelope_digests', 'member_source_scopes', 'member_output_digests'):
        assert report['cohort'][field] == SPEC['manifest'][field]
    assert mechanism.evaluate_mechanism(deepcopy(package)) == report
    assert mechanism.validate_report(json.loads(encode(report))) == report


@pytest.mark.parametrize('mutation', ['flip_blob', 'foreign_run', 'foreign_task', 'foreign_actor', 'size', 'final_context'])
def test_A03_A04_A05_byte_and_identity_rejection(package, mutation):
    snapshot = json.loads(package['snapshots'][0])
    root, result = selected(snapshot)
    p = next(m['payload_snapshot'] for m in result['output_records'] if m['kind'] == 'AGENT_OUTPUT')
    if mutation == 'flip_blob':
        next(r for r in snapshot['records'] if r['source_id'] == p['artifact_id'])['payload'] += ' '
    elif mutation == 'size':
        p['artifact_size_bytes'] += 1
        m = next(m for m in result['output_records'] if m['kind'] == 'AGENT_OUTPUT')
        m['content_digest'] = h(p, m['record_schema'])
        resign_result(snapshot)
    elif mutation == 'final_context':
        p['input_refs'][-1] = 'sha256:' + 'a' * 64
        resign_result(snapshot)
    else:
        result[{'foreign_run': 'run_id', 'foreign_task': 'producer_task_id', 'foreign_actor': 'task_fingerprint'}[mutation]] = 'FOREIGN'
        resign_result(snapshot)
    seal(snapshot)
    case, diagnostic = mechanism.inspect_case(package['envelopes'][0], encode(snapshot), package['schema_pins'])
    assert case is None
    assert set(diagnostic['invalid_reasons']) & {'IDENTITY_MISMATCH', 'DIGEST_MISMATCH'}
    bad = deepcopy(package)
    bad['snapshots'][0] = encode(snapshot)
    out = mechanism.evaluate_mechanism(bad)
    assert out['cohort']['cohort_validity'] == 'INVALID'
    assert out['cohort']['member_evaluation_digests'][0] is None
    assert len(out['cohort']['excluded_members']) == 1


@pytest.mark.parametrize('slot', ['schema_pins', 'manifest', 'namespace', 'source_scope', 'rubric', 'oracle'])
def test_A05_A06_unsupported_pins_and_scopes(package, slot):
    if slot in ('schema_pins', 'manifest'):
        bad = deepcopy(package)
        if slot == 'manifest':
            bad[slot]['cohort_policy_id'] = 'OTHER'
        else:
            bad[slot]['agent_output.py'] = 'sha256:' + '0' * 64
        with pytest.raises(mechanism.MechanismInputError):
            mechanism.evaluate_mechanism(bad)
    else:
        identity = deepcopy(SPEC['cases'][0]['identity'])
        if slot == 'namespace':
            identity['source_scope']['namespace']['anchor_digest'] = 'sha256:' + '0' * 64
        elif slot == 'source_scope':
            identity['source_scope']['source_manifest'][2]['evidence_scope'] = 'FUTURE_DETACHED'
        elif slot == 'rubric':
            identity['rubric_version'] = 'OTHER'
        else:
            identity['oracle_refs'][0]['source_digest'] = 'sha256:' + '0' * 64
        with pytest.raises(mechanism.MechanismInputError):
            mechanism.component_scopes(identity)


@pytest.mark.parametrize('raw', [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'"\xff"', b'{"x":1.0}'])
def test_A07_strict_json_rejects(raw):
    with pytest.raises(mechanism.MechanismInputError):
        mechanism.decode_json(raw)


def test_A07_canonical_object_array_unicode_null():
    assert mechanism.canonical({'b': 1, 'a': '中文'}) == encode({'a': '中文', 'b': 1})
    assert mechanism.digest('tag', [1, 2]) != mechanism.digest('tag', [2, 1])
    assert mechanism.digest('tag', {'a': None}) != mechanism.digest('tag', {})
    assert mechanism.digest('tag', 'é') != mechanism.digest('tag', 'e\u0301')
    assert mechanism.digest('tag', True) != mechanism.digest('tag', 1)


@pytest.mark.parametrize('kind', ['duplicate', 'reorder', 'empty', 'omit', 'alias', 'missing_bytes'])
def test_A09_fixed_membership_no_successful_subset(package, kind):
    bad = deepcopy(package)
    if kind == 'missing_bytes':
        bad['snapshots'][2] = None
        out = mechanism.evaluate_mechanism(bad)
        assert out['cohort']['cohort_validity'] == 'INVALID'
        assert out['cohort']['member_evaluation_digests'][2] is None
        for dim in out['cohort']['dimension_counts']:
            assert dim['requested_count'] == 2
        return
    if kind == 'duplicate':
        bad['manifest']['member_case_ids'][1] = CASE_IDS[0]
    elif kind == 'reorder':
        bad['manifest']['member_case_ids'].reverse()
    elif kind == 'alias':
        bad['manifest']['member_case_ids'].append(CASE_IDS[2])
    elif kind == 'empty':
        bad['envelopes'] = bad['snapshots'] = []
    else:
        bad['envelopes'].pop()
    with pytest.raises(mechanism.MechanismInputError, match='MEMBERSHIP_DRIFT'):
        mechanism.evaluate_mechanism(bad)


@pytest.mark.parametrize('state,reason', [('PARTIALLY_READY', 'MISSING_USAGE_PROVENANCE'),
    ('NOT_READY', 'MISSING_RESULT_BINDING'), ('LEGACY_UNKNOWN', 'LEGACY_METADATA_ABSENT')])
def test_A10_readiness_never_promoted(package, state, reason):
    # An adversarial stored state is preserved diagnostically even when it
    # contradicts reprojection; it cannot be silently promoted to READY.
    e = json.loads(package['envelopes'][0])
    e['readiness_state'], e['readiness_reasons'] = state, [reason]
    e['envelope_digest'] = h(without(e, 'envelope_digest'), wp05.SCHEMA)
    case, diag = mechanism.inspect_case(encode(e), package['snapshots'][0], package['schema_pins'])
    assert case is None
    assert diag['readiness_state'] == state and diag['readiness_reasons'] == [reason]
    assert diag['invalid_reasons']


@pytest.mark.parametrize('count,expected', [(5, 'COMPLETE'), (4, 'PARTIAL'), (1, 'PARTIAL'), (0, 'MISSING')])
def test_A11_structural_presence(count, expected, package):
    answer = dict(summary='', key_findings=[], risks=[], limitations=[], requires_follow_up=False)
    answer = dict(list(answer.items())[:count])
    result = mechanism.structural_completeness(answer, review_refs(package))
    assert result['result'] == expected
    assert result['coverage']['required_count'] == 5
    assert result['coverage']['missing_count'] == 5 - count
    assert result['coverage']['conflict_count'] == 0


def test_P3_D6_01_fully_bound_positive(package):
    snapshot = change_answer(json.loads(package['snapshots'][0]), SPEC['control_answer'])
    envelope = project(snapshot)
    assert envelope['readiness_state'] == 'READY' and envelope['readiness_reasons'] == []
    root, result = selected(snapshot)
    p = next(m['payload_snapshot'] for m in result['output_records'] if m['kind'] == 'AGENT_OUTPUT')
    raw = next(r['payload'] for r in snapshot['records'] if r['owner'] == 'Blob' and r['source_id'] == p['artifact_id'])
    assert 'sha256:' + hashlib.sha256(raw.encode()).hexdigest() == p['artifact_id']
    assert json.loads(raw)['structured_output'] == SPEC['control_answer'] == p['structured_output']
    post = root['resolved_inputs'][envelope['subject_identity']['dispatch_membership'][-1]['receipt_B_id']]
    assert post['payload_snapshot']['response'] == dict(kind='FINAL', answer=SPEC['control_answer'], request=None)
    assert envelope['context_identity']['turns'][-1]['response_schema_digest'] == SPEC['cases'][0]['identity']['context_identity']['turns'][-1]['response_schema_digest']
    case, diag = mechanism.inspect_case(encode(envelope), encode(snapshot), package['schema_pins'])
    assert diag['invalid_reasons'] == [] and case['case_validity'] == 'VALID'
    assert case['case_id'] not in CASE_IDS
    d = dimension(case, D6)
    assert d['result'] == 'PASS' and d['oracle_id'] == 'D6_STRICT_FINAL_SCHEMA_V1'
    assert d['reason_codes'] == [] and d['coverage']['missing_count'] == d['coverage']['conflict_count'] == 0
    assert dimension(case, D1)['result'] == 'COMPLETE'
    bad = deepcopy(package)
    bad['envelopes'][0], bad['snapshots'][0] = encode(envelope), encode(snapshot)
    assert mechanism.evaluate_mechanism(bad)['cohort']['cohort_validity'] == 'INVALID'


@pytest.mark.parametrize('field,value,code', [
    ('summary', 7, 'SCHEMA_TYPE'), ('summary', '   ', 'SCHEMA_BLANK'),
    ('summary', 'x' * 801, 'SCHEMA_LENGTH'), ('key_findings', [], 'SCHEMA_LENGTH'),
    ('key_findings', ['x', ' x '], 'SCHEMA_DUPLICATE_TEXT'), ('risks', [' '], 'SCHEMA_BLANK'),
    ('risks', ['x' * 801], 'SCHEMA_LENGTH'), ('limitations', ['1', '2', '3', '4', '5', '6'], 'SCHEMA_LENGTH'),
    ('requires_follow_up', True, 'FOLLOW_UP_NOT_FALSE'), ('requires_follow_up', 0, 'FOLLOW_UP_NOT_FALSE'),
    ('requires_follow_up', 'false', 'FOLLOW_UP_NOT_FALSE'), ('risks', [{'secret': 'PRIVATE'}], 'SCHEMA_TYPE'),
    ('extra', 'PRIVATE', 'SCHEMA_EXTRA_FIELD'), ('summary', None, 'REQUIRED_FIELD_ABSENT'),
])
def test_A12_P3_D6_02_each_strict_predicate(package, field, value, code):
    answer = deepcopy(SPEC['control_answer'])
    answer[field] = value
    d = mechanism.schema_validity(answer, dict(kind='FINAL', answer=answer, request=None),
        package['schema_pins']['agent_output.py'], SPEC['cases'][0]['identity']['context_identity']['turns'][-1]['response_schema_digest'],
        review_refs(package))
    assert d['result'] == 'FAIL' and code in d['reason_codes']
    assert 'PRIVATE' not in encode(d).decode()
    # Coherent private controls still cannot replace a frozen member. WP05's
    # stricter prerequisite failures remain invalid rather than a D6 promotion.
    snapshot = change_answer(json.loads(package['snapshots'][0]), answer)
    envelope = project(snapshot)
    case, diag = mechanism.inspect_case(encode(envelope), encode(snapshot), package['schema_pins'])
    if case is not None:
        assert dimension(case, D6)['result'] == 'FAIL'
    else:
        assert diag['invalid_reasons']


@pytest.mark.parametrize('kind', ['RETRIEVE', 'wrong_answer', 'request', 'missing_wrapper', 'missing_schema'])
def test_A13_final_branch_and_authority(package, kind):
    answer = deepcopy(SPEC['control_answer'])
    wrapper = dict(kind='FINAL', answer=answer, request=None)
    schema = package['schema_pins']['agent_output.py']
    if kind == 'RETRIEVE':
        wrapper['kind'] = 'RETRIEVE'
    elif kind == 'wrong_answer':
        wrapper['answer'] = {'summary': 'foreign'}
    elif kind == 'request':
        wrapper['request'] = {}
    elif kind == 'missing_wrapper':
        wrapper = None
    else:
        schema = None
    d = mechanism.schema_validity(answer, wrapper, schema,
        SPEC['cases'][0]['identity']['context_identity']['turns'][-1]['response_schema_digest'], review_refs(package))
    assert d['result'] == ('UNKNOWN' if kind.startswith('missing') else 'FAIL')
    assert d['coverage']['missing_count'] > 0 if kind.startswith('missing') else d['coverage']['conflict_count'] > 0


def test_A14_P3_D2_01_02_03_optional_and_required(package, report):
    assert all(dimension(case, D2)['result'] == 'PASS' for case in report['cases'])
    envelope = json.loads(package['envelopes'][0])
    # Exact optionality authority: WP05 dependency_identity EVIDENCE result_id /
    # result_version are nullable. Selector '/' on that selected evidence stays
    # required; only this absent optional producer-result proof is uninspectable.
    dependency = next(d for d in envelope['dependency_identity'] if d['kind'] == 'EVIDENCE')
    assert dependency['field_selectors'] == ['/'] and dependency['result_id'] is None
    refs = [r for r in envelope['safe_source_manifest']
            if r['owner'] == 'Repository' and r['source_id'] == envelope['task_identity']['run_id']]
    d = mechanism.reference_integrity([True], [None], refs)
    assert d['result'] == 'UNKNOWN' and d['reason_codes'] == ['REFERENCE_UNRESOLVED']
    assert d['coverage'] == dict(required_count=2, checked_count=1, missing_count=1, conflict_count=0)
    d = mechanism.reference_integrity([True, False], [None], refs)
    assert d['result'] == 'FAIL' and 'REFERENCE_CONFLICT' in d['reason_codes']
    snapshot = json.loads(package['snapshots'][0])
    output_id = SPEC['cases'][0]['identity']['output_artifact_id']
    snapshot['records'] = [r for r in snapshot['records'] if r['source_id'] != output_id]
    seal(snapshot)
    case, diag = mechanism.inspect_case(package['envelopes'][0], encode(snapshot), package['schema_pins'])
    assert case is None and 'MISSING_REQUIRED_INPUT' in diag['invalid_reasons']


def test_A15_P3_D5_01_native_block_is_complete_pass(package, report):
    for case in report['cases']:
        d = dimension(case, D5)
        assert d['result'] == 'COMPLETE'
        assert d['reason_codes'] == ['D5_INTEGRITY_PASS', 'DIRECT_SUBJECT_LINK_UNKNOWN']
        assert d['context']['native_status'] == 'BLOCK'
        assert d['context']['scope'] == 'RUN_CONTEXT_ONLY'
        assert d['context']['direct_subject_support'] == 'UNKNOWN'
        assert all(ref['evidence_scope'] == 'SYNTHETIC_CONTEXT' for ref in d['evidence_refs'])


@pytest.mark.parametrize('result,integrity', [
    ('COMPLETE', 'PASS'), ('COMPLETE', 'FAIL'), ('COMPLETE', 'UNKNOWN'),
    ('PARTIAL', 'FAIL'), ('PARTIAL', 'UNKNOWN'), ('MISSING', 'FAIL'), ('MISSING', 'UNKNOWN')])
def test_P3_D5_01_through_07_P3_WIRE_01_allowed_pairs(package, result, integrity):
    context = deepcopy(base_context(package))
    if result == 'PARTIAL':
        context['reviewer'] = None
    elif result == 'MISSING':
        context = None
    checks = [True] * 5
    if integrity == 'FAIL':
        checks[0] = False
    if integrity == 'UNKNOWN' or result != 'COMPLETE':
        checks[-1] = None
    d = mechanism.review_join(context, checks, review_refs(package))
    assert d['result'] == result and 'D5_INTEGRITY_' + integrity in d['reason_codes']
    assert d['reason_codes'] == sorted(set(d['reason_codes']))
    assert len(set(d['reason_codes']) & {'D5_INTEGRITY_PASS', 'D5_INTEGRITY_FAIL', 'D5_INTEGRITY_UNKNOWN'}) == 1
    assert set(d) == {'dimension_id', 'oracle_id', 'rubric_version', 'result', 'reason_codes', 'evidence_refs', 'coverage', 'context'}
    assert mechanism.validate_dimension(json.loads(encode(d))) == d
    assert 'integrity' not in d and 'integrity' not in d['context'] and 'integrity' not in d['coverage']


@pytest.mark.parametrize('mutation', ['foreign', 'foreign_partial', 'partial', 'missing', 'missing_proof'])
def test_A16_P3_D5_package_precedence(package, mutation):
    snapshot = json.loads(package['snapshots'][0])
    review = obj(snapshot, 'Review')
    if mutation.startswith('foreign'):
        review['run_id'] = 'RUN-FOREIGN'
    if mutation in ('partial', 'foreign_partial'):
        review.pop('reviewer')
        review.pop('status')
    elif mutation == 'missing':
        snapshot['records'] = [r for r in snapshot['records'] if r['owner'] != 'Review']
    elif mutation == 'missing_proof':
        review.pop('requirement_context')
    seal(snapshot)
    envelope = project(snapshot)
    original_readiness = envelope['readiness_state'], envelope['readiness_reasons'][:]
    case, diag = mechanism.inspect_case(encode(envelope), encode(snapshot), package['schema_pins'])
    assert case is None or case['case_validity'] == 'INVALID'
    assert (diag['readiness_state'], diag['readiness_reasons']) == original_readiness
    expected = 'IDENTITY_MISMATCH' if mutation.startswith('foreign') else 'MISSING_REQUIRED_INPUT'
    assert expected in diag['invalid_reasons']
    if case is not None:
        assert case['dimension_results'] == []


@pytest.mark.parametrize('mutation', ['partial_pass', 'missing_pass', 'no_token', 'two_tokens', 'duplicate',
    'unknown_token', 'unsorted', 'extra', 'context_extra', 'coverage_extra', 'bool_count', 'negative',
    'unknown_without_missing', 'fail_without_conflict', 'missing_fail_no_evidence', 'token_on_D1'])
def test_P3_D5_08_P3_WIRE_01_invalid_wire(package, mutation):
    d = mechanism.review_join(base_context(package), [True] * 5, review_refs(package))
    if mutation in ('partial_pass', 'missing_pass'):
        d['result'] = mutation.split('_')[0].upper()
        d['reason_codes'] = sorted(d['reason_codes'] + ['REVIEW_' + d['result']])
    elif mutation == 'no_token':
        d['reason_codes'].remove('D5_INTEGRITY_PASS')
    elif mutation == 'two_tokens':
        d['reason_codes'] = sorted(d['reason_codes'] + ['D5_INTEGRITY_UNKNOWN'])
    elif mutation == 'duplicate':
        d['reason_codes'].insert(0, 'D5_INTEGRITY_PASS')
    elif mutation == 'unknown_token':
        d['reason_codes'][0] = 'D5_INTEGRITY_FUTURE'
    elif mutation == 'unsorted':
        d['reason_codes'].reverse()
    elif mutation == 'extra':
        d['integrity'] = 'PASS'
    elif mutation == 'context_extra':
        d['context']['integrity'] = 'PASS'
    elif mutation == 'coverage_extra':
        d['coverage']['integrity'] = 'PASS'
    elif mutation == 'bool_count':
        d['coverage']['missing_count'] = False
    elif mutation == 'negative':
        d['coverage']['conflict_count'] = -1
    elif mutation == 'unknown_without_missing':
        d['reason_codes'][0] = 'D5_INTEGRITY_UNKNOWN'
    elif mutation == 'fail_without_conflict':
        d['reason_codes'] = sorted(['D5_INTEGRITY_FAIL', 'REVIEW_IDENTITY_CONFLICT', 'DIRECT_SUBJECT_LINK_UNKNOWN'])
    elif mutation == 'missing_fail_no_evidence':
        d = mechanism.review_join(None, [False, None], review_refs(package))
        d['evidence_refs'] = []
    else:
        d = mechanism.structural_completeness(SPEC['control_answer'], review_refs(package))
        d['reason_codes'] = ['D5_INTEGRITY_PASS']
    with pytest.raises(mechanism.MechanismInputError):
        mechanism.validate_dimension(d)


def test_P3_WIRE_02_aggregate_accounting(package):
    a = mechanism.review_join(base_context(package), [True] * 5, review_refs(package))
    b = mechanism.review_join(base_context(package), [True, True, True, True, None], review_refs(package))
    out = mechanism.dimension_counts('LOCAL_SYNTHETIC_1_TURN', D5, [a, b])
    assert out['outcome_counts'] == dict(COMPLETE=2, PARTIAL=0, MISSING=0)
    assert out['assessed_count'] == 2 and out['unknown_count'] == 1
    tokens = [next(x for x in d['reason_codes'] if x.startswith('D5_INTEGRITY_')) for d in [a, b]]
    assert [tokens.count('D5_INTEGRITY_' + k) for k in ['PASS', 'FAIL', 'UNKNOWN']] == [1, 0, 1]
    excluded = mechanism.dimension_counts('LOCAL_SYNTHETIC_1_TURN', D5, [a, b, None])
    assert excluded['outcome_counts'] == out['outcome_counts']
    assert excluded['assessed_count'] == 2 and excluded['unknown_count'] == 1
    assert excluded['excluded_count'] == 1 and excluded['requested_count'] == 3


@pytest.mark.parametrize('field', ['envelope', 'snapshot'])
@pytest.mark.parametrize('mutation', ['prefix', 'uppercase', 'space', 'newline', 'length', 'type'])
def test_P3_HASH_01_bare_file_hash_boundary(field, mutation):
    identity = deepcopy(SPEC['cases'][0]['identity'])
    value = identity['input_file_hashes'][field]
    identity['input_file_hashes'][field] = {
        'prefix': 'sha256:' + value, 'uppercase': value.upper(), 'space': ' ' + value,
        'newline': value + '\n', 'length': value[:-1], 'type': 123,
    }[mutation]
    with pytest.raises(mechanism.MechanismInputError):
        mechanism.validate_identity(identity)


@pytest.mark.parametrize('mutation', ['bare', 'uppercase', 'space', 'newline', 'length', 'type'])
def test_P3_HASH_01_tagged_boundaries_recursive(mutation):
    original = SPEC['cases'][0]['identity']
    def locations(value, path=()):
        if type(value) is dict:
            for k, v in value.items():
                yield from locations(v, path + (k,))
        elif type(value) is list:
            for i, v in enumerate(value):
                yield from locations(v, path + (i,))
        elif type(value) is str and len(value) == 71 and value.startswith('sha256:'):
            yield path
    for path in locations(original):
        identity = deepcopy(original)
        node = identity
        for key in path[:-1]:
            node = node[key]
        v = node[path[-1]]
        node[path[-1]] = {'bare': v[7:], 'uppercase': v.upper(), 'space': ' ' + v,
                         'newline': v + '\n', 'length': v[:-1], 'type': 7}[mutation]
        with pytest.raises(mechanism.MechanismInputError):
            mechanism.component_scopes(identity)


@pytest.mark.parametrize('mutation', ['aggregate_detached', 'delete_scope', 'receipt_id', 'receipt_position'])
def test_P3_SCOPE_01_no_reclassification(mutation):
    identity = deepcopy(SPEC['cases'][0]['identity'])
    refs = identity['source_scope']['source_manifest']
    if mutation == 'aggregate_detached':
        identity['source_scope']['component_scopes'].insert(0, 'DETACHED_OWNER_SNAPSHOT')
    elif mutation == 'delete_scope':
        refs[2].pop('evidence_scope')
    elif mutation == 'receipt_id':
        refs[2]['source_id'] = 'NEW_RECEIPT'
    else:
        refs[1], refs[2] = refs[2], refs[1]
    with pytest.raises(mechanism.MechanismInputError):
        mechanism.component_scopes(identity)


def test_A17_excluded_dimensions_and_authority(package, report):
    assert all(json.loads(raw)['method_dependency_context'] == [] for raw in package['envelopes'])
    assert all([d['dimension_id'] for d in c['dimension_results']] == [D1, D2, D5, D6] for c in report['cases'])
    forbidden = {'score', 'quality_score', 'composite', 'ranking', 'human_score', 'llm_judge', 'D3', 'D4', 'effectiveness'}
    def keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)
    assert not forbidden.intersection(keys(report))
    assert report['authority_role'] == 'DERIVED_OFFLINE_EVALUATION_EVIDENCE'


def test_A18_A19_exact_key_and_no_independent_self_pair(package, report):
    envelopes = [json.loads(x) for x in package['envelopes']]
    cases = report['cases']
    key = mechanism.task_input_key(cases[0]['identity'], envelopes[0])
    assert h(key, 'wp06-task-input-key/v1') == mechanism.digest('wp06-task-input-key/v1', key)
    assert key['method_dependency_context'] == []
    assert mechanism.compare_keys(key, deepcopy(key)) == (True, [])
    for field in key:
        different = deepcopy(key)
        different[field] = None
        assert mechanism.compare_keys(key, different) == (False, [field])
        different[field] = {'locally_changed': True}
        assert mechanism.compare_keys(key, different) == (False, [field])
    assert mechanism.compare_cases(cases[0], envelopes[0], cases[0], envelopes[0]) == (False, ['SAME_CASE'])
    for i in range(4):
        for j in range(i + 1, 4):
            ok, reasons = mechanism.compare_cases(cases[i], envelopes[i], cases[j], envelopes[j])
            assert ok is False and 'context_identity' in reasons
    _, reasons = mechanism.compare_cases(cases[0], envelopes[0], cases[1], envelopes[1], dimension_id=D5)
    assert 'context_identity' in reasons


def test_A20_A21_A22_A23_A24_metrics(package, report):
    for i, case in enumerate(report['cases']):
        input_metric = next(m for m in case['usage_coverage'] if m['metric_id'] == 'input_tokens')
        assert input_metric['complete_for_metric'] is True
        assert input_metric['complete_total'] == [100, 180, 0, 0][i]
        for m in case['usage_coverage'] + case['latency_coverage'] + [case['cost_coverage']]:
            assert m['comparison_eligible'] is False
            if m['metric_id'] in ('cached_input_tokens', 'reasoning_output_tokens', 'cost', 'provider_only_latency'):
                assert m['complete_total'] is None and m['complete_for_metric'] is False
        latency = case['latency_coverage'][0]
        assert latency['scope'] == 'MODEL_TURN_ELAPSED' and latency['unit'] == 'milliseconds'
        assert latency['complete_total'] == json.loads(package['envelopes'][i])['usage_aggregate']['model_turn_elapsed']['complete_total']['value']
    e = json.loads(package['envelopes'][1])
    unknown = dict(value=None, provenance='UNKNOWN', source_refs=[], missing_reason='NOT_RETAINED', derivation_rule=None)
    e['dispatches'][1]['input_tokens'] = deepcopy(unknown)
    m = mechanism.metric_coverage(e, 'input_tokens', comparable=True)
    assert m['observed_subtotal'] == 100 and m['complete_total'] is None and not m['comparison_eligible']
    assert m['unknown_dispatch_ids'] == [e['dispatches'][1]['dispatch_id']]
    e['dispatches'][1]['model_turn_elapsed'] = deepcopy(unknown)
    latency = mechanism.metric_coverage(e, 'model_turn_elapsed', comparable=True)
    assert latency['complete_total'] is None and not latency['comparison_eligible']
    zero = json.loads(package['envelopes'][2])
    zero['dispatches'][0]['input_tokens']['value'] = None
    zero['dispatches'][0]['input_tokens']['provenance'] = 'UNKNOWN'
    zero['dispatches'][0]['input_tokens']['missing_reason'] = 'UNPROVEN_DEFAULT'
    zero['dispatches'][0]['input_tokens']['derivation_rule'] = None
    m = mechanism.metric_coverage(zero, 'input_tokens')
    assert m['complete_total'] is None and m['observed_subtotal'] is None
    e['usage_aggregate']['cost']['complete_total']['value'] = 0
    e['usage_aggregate']['cost']['complete_for_metric'] = True
    cost = mechanism.metric_coverage(e, 'cost', comparable=True)
    assert cost['complete_total'] is None and cost['exclusion_reasons'] == ['COST_NOT_ADMITTED']


def test_A25_closed_nested_export_injections(report):
    sentinel = 'https://sentinel.invalid/private?token=PRIVATE_PROMPT_COT'
    def paths(value, path=()):
        if type(value) is dict:
            for k, v in value.items():
                yield path + (k,)
                yield from paths(v, path + (k,))
        elif type(value) is list:
            for i, v in enumerate(value):
                yield path + (i,)
                yield from paths(v, path + (i,))
    # Every nested scalar/status/ref/count/container position is a typed boundary.
    for path in paths(report):
        bad = deepcopy(report)
        node = bad
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = sentinel
        with pytest.raises((mechanism.MechanismInputError, TypeError, KeyError)):
            mechanism.validate_report(bad)
    for path in [(), ('cases', 0), ('cases', 0, 'identity'), ('cases', 0, 'dimension_results', 2, 'context'),
                 ('cases', 0, 'cost_coverage'), ('cohort',), ('diagnostics', 0)]:
        bad = deepcopy(report)
        node = bad
        for key in path:
            node = node[key]
        node['raw_prompt'] = sentinel
        with pytest.raises(mechanism.MechanismInputError):
            mechanism.validate_report(bad)
    assert sentinel not in encode(report).decode()
    assert all(x not in encode(report).decode() for x in ('/Users/', '/private/', 'raw_prompt', 'artifact_ref', 'structured_output'))


def test_A26_A29_import_and_calls_no_io_no_mutation(package, report, monkeypatch):
    source = (REPO / 'src/application/evaluation_mechanism.py').read_text()
    code = compile(source, '<isolated-wp06-import>', 'exec')
    tree = ast.parse(source)
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imports <= {'__future__', 'src.application'}
    assert {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} <= {'hashlib', 'json', 'math', 're'}
    before = deepcopy(package)
    snapshots_before = [hashlib.sha256(x).hexdigest() for x in package['snapshots']]
    calls = []
    def forbidden(*args, **kwargs):
        calls.append('FORBIDDEN_IO')
        raise AssertionError('FORBIDDEN_IO')
    with monkeypatch.context() as guard:
        for module, name in [(builtins, 'open'), (io, 'open'), (os, 'getenv'), (os, 'open'),
                             (socket, 'socket'), (socket, 'create_connection'), (subprocess, 'Popen')]:
            guard.setattr(module, name, forbidden)
        scope = {'__name__': 'isolated_wp06'}
        exec(code, scope)
        assert scope['evaluate_mechanism'](package) == report
        bad = deepcopy(package)
        bad['snapshots'][0] = b'{"x":1,"x":2}'
        assert scope['evaluate_mechanism'](bad)['cohort']['cohort_validity'] == 'INVALID'
        with pytest.raises(mechanism.MechanismInputError):
            mechanism.evaluate_mechanism({'provider_callback': forbidden})
    assert calls == [] and package == before
    assert snapshots_before == [hashlib.sha256(x).hexdigest() for x in package['snapshots']]
    # No endpoint imports or default registration means no route exists from
    # the evaluator to repository/Review/Release/Memory/DB/provider writers.
    for raw, row in zip(package['snapshots'], SPEC['inputs']):
        assert hashlib.sha256(raw).hexdigest() == row['snapshot_sha256']


def test_A27_A28_identity_provenance_and_denominators(package, report):
    for i, case in enumerate(report['cases']):
        envelope = json.loads(package['envelopes'][i])
        original = deepcopy(envelope['dispatches'])
        for d in envelope['dispatches']:
            assert d['requested_model']['provenance'] == 'CONFIGURED'
            assert d['resolved_model']['provenance'] == 'CLIENT_OBSERVATION'
            assert d['observed_model']['provenance'] == 'PROVIDER_RESPONSE'
            assert d['requested_model'] != d['observed_model']
        assert json.loads(package['envelopes'][i])['dispatches'] == original
        assert case['identity']['source_scope'] == SPEC['manifest']['member_source_scopes'][i]
    for d in report['cohort']['dimension_counts']:
        assert d['requested_count'] == d['eligible_count'] == d['assessed_count'] == 2
        assert sum(d['outcome_counts'].values()) == 2
        assert d['excluded_count'] == d['unknown_count'] == 0
    assert len(report['cases']) + len(report['cohort']['excluded_members']) == 4
    assert all(m['requested_member_count'] == 2 and m['comparison_eligible'] is False
               for m in report['cohort']['metric_coverage'])
    bad = deepcopy(package)
    bad['snapshots'][0] = None
    out = mechanism.evaluate_mechanism(bad)
    assert len(out['cases']) == 3 and len(out['cohort']['excluded_members']) == 1
    for d in out['cohort']['dimension_counts'][:4]:
        assert d['assessed_count'] == 1 and d['excluded_count'] == 1 and d['requested_count'] == 2


def test_P3_D5_07_missing_review_with_independent_expected_join_conflict(package):
    snapshot = json.loads(package['snapshots'][0])
    snapshot['records'] = [r for r in snapshot['records'] if r['owner'] != 'Review']
    obj(snapshot, 'Application')['run_id'] = 'RUN-FOREIGN'
    seal(snapshot)
    envelope = project(snapshot)
    case, diag = mechanism.inspect_case(encode(envelope), encode(snapshot), package['schema_pins'])
    assert case is None and 'IDENTITY_MISMATCH' in diag['invalid_reasons']
    expected = json.loads(package['envelopes'][0])
    refs = [r for r in expected['safe_source_manifest'] if r['owner'] == 'Repository'
            and r['source_id'] == expected['task_identity']['run_id']]
    observation = mechanism.review_join(None, [False, None], refs)
    assert observation['result'] == 'MISSING'
    assert 'D5_INTEGRITY_FAIL' in observation['reason_codes']
    assert 'REVIEW_IDENTITY_CONFLICT' in observation['reason_codes']


# PC1: these are normal fresh-interpreter imports, independent of pytest's
# warmed graph. Python hooks cannot attest native extension initialization.
# Such a boundary is retained as UNKNOWN, never relabeled a loader read.
_COLD_IMPORT_PROBE = r'''
import sys
import os
import json
import importlib._bootstrap as bootstrap
import importlib._bootstrap_external as external
import io

# Harness inputs are supplied before guards; no input file is opened by the evaluator.
wire = json.loads(sys.stdin.read())
invocation_package = wire.get('package')
if invocation_package is not None:
    for key in ('snapshots', 'envelopes'):
        invocation_package[key] = [value.encode('utf-8') for value in invocation_package[key]]

phase = 'COLD_IMPORT'
events = []
module_order = []
loading = []
active = False
initial_modules = sorted(sys.modules)
relevant = [n for n in initial_modules if n == 'src' or n.startswith('src.')
            or n == 'pydantic' or n.startswith('pydantic.')
            or n == 'finrobot' or n.startswith('finrobot.')]
assert relevant == [], relevant
assert sys.dont_write_bytecode


class ProhibitedIO(AssertionError):
    pass


def record(kind, target, classification, rule, reason):
    frame = sys._getframe(2)
    stack = []
    while frame is not None and len(stack) < 14:
        stack.append({'file': frame.f_code.co_filename,
                      'function': frame.f_code.co_name, 'line': frame.f_lineno})
        frame = frame.f_back
    events.append({'event_ordinal': len(events) + 1, 'phase': phase,
                   'event_type': kind, 'target': str(target),
                   'immediate_caller': stack[0] if stack else 'UNKNOWN',
                   'relevant_stack_slice': stack,
                   'module_being_loaded': loading[-1] if loading else 'NONE',
                   'classification': classification, 'rule_id': rule,
                   'reason': reason})
    if classification == 'APPLICATION_SIDE_EFFECT_IO' and phase != 'LATER_EXPLICIT_SYMBOL_ACCESS':
        raise ProhibitedIO(kind)


original_find = bootstrap._find_and_load

def find(name, importer):
    if active and phase != 'LATER_EXPLICIT_SYMBOL_ACCESS' and (
            name.startswith(('src.application.service', 'src.application.repository',
                             'src.application.execution', 'src.observability', 'finrobot', 'pydantic'))):
        record('application_endpoint_import', name, 'APPLICATION_SIDE_EFFECT_IO', 'PC1.1',
               'Eager service/provider/repository/telemetry branch attempt')
    loading.append(name)
    try:
        return original_find(name, importer)
    finally:
        loading.pop()
bootstrap._find_and_load = find

# Wrap the actual filesystem primitives used by the normal loader. Each
# wrapper records one attempt; correlated audit notifications are not counted
# twice. Qualification requires the immediate loader operation AND module.
loader_depth = 0

def loader_wrapper(original, operation):
    def wrapped(target, *args, **kwargs):
        global loader_depth
        caller = sys._getframe(1)
        direct_loader = caller.f_code.co_filename == '<frozen importlib._bootstrap_external>'
        if active:
            allowed = phase in ('COLD_IMPORT', 'LATER_EXPLICIT_SYMBOL_ACCESS') and direct_loader and bool(loading)
            record(operation, target,
                   'NORMAL_MODULE_LOADER_IO' if allowed else 'APPLICATION_SIDE_EFFECT_IO',
                   'PC1.2' if allowed else 'PC1.1',
                   'Immediate frozen loader primitive resolving named executable module'
                   if allowed else 'Filesystem inspection outside the cold executable-loader interval')
        loader_depth += 1
        try:
            return original(target, *args, **kwargs)
        finally:
            loader_depth -= 1
    return wrapped

external._os.stat = loader_wrapper(external._os.stat, 'stat')
external._os.listdir = loader_wrapper(external._os.listdir, 'listdir')
# os keeps aliases separate from importlib's posix module; guard both entry points.
os.stat = external._os.stat
os.listdir = external._os.listdir
for primitive in ('lstat', 'readlink', 'access', 'getcwd', 'read', 'pread', 'write', 'fstat', 'readv', 'writev'):
    if hasattr(os, primitive):
        original = getattr(os, primitive)
        def guarded(*args, _original=original, _name=primitive, **kwargs):
            if active:
                record(_name, '<arguments redacted>', 'APPLICATION_SIDE_EFFECT_IO', 'PC1.1',
                       'Direct non-loader filesystem/descriptor primitive')
            return _original(*args, **kwargs)
        setattr(os, primitive, guarded)
# get_data delegates to _io.open_code for executable code, observed by audit.

original_getitem = os._Environ.__getitem__
original_iter = os._Environ.__iter__
original_len = os._Environ.__len__

def env_getitem(self, key):
    if active:
        record('environment_reads', key, 'APPLICATION_SIDE_EFFECT_IO', 'PC1.1',
               'Environment access is always prohibited; values not recorded')
    return original_getitem(self, key)

def env_iter(self):
    if active:
        record('environment_reads', '<iteration>', 'APPLICATION_SIDE_EFFECT_IO', 'PC1.1',
               'Environment iteration is prohibited')
    return original_iter(self)

def env_len(self):
    if active:
        record('environment_reads', '<length>', 'APPLICATION_SIDE_EFFECT_IO', 'PC1.1',
               'Environment inspection is prohibited')
    return original_len(self)

os._Environ.__getitem__ = env_getitem
os._Environ.__iter__ = env_iter
os._Environ.__len__ = env_len


def audit(event, args):
    if not active:
        return
    if event == 'exec':
        module_order.append(args[0].co_filename)
    elif event == 'open':
        caller = sys._getframe(1)
        path, mode, flags = args
        read_only = not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        code_loader = (phase in ('COLD_IMPORT', 'LATER_EXPLICIT_SYMBOL_ACCESS') and caller.f_code.co_filename == '<frozen importlib._bootstrap_external>'
                       and caller.f_code.co_name == 'get_data' and bool(loading))
        record('open', path, 'NORMAL_MODULE_LOADER_IO' if read_only and code_loader
               else 'APPLICATION_SIDE_EFFECT_IO', 'PC1.2' if read_only and code_loader else 'PC1.1',
               'Direct get_data executable code read' if read_only and code_loader
               else 'Non-loader file access or write')
    elif event in ('os.listdir', 'os.scandir'):
        if not loader_depth:
            record(event, args[0], 'APPLICATION_SIDE_EFFECT_IO', 'PC1.1',
                   'Directory access outside observed loader operation')
    elif event.startswith(('socket.', 'subprocess.', 'sqlite3.', 'ctypes.', 'os.spawn',
                           'os.exec', 'os.fork', 'os.system', 'os.putenv', 'os.unsetenv',
                           'os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.link', 'os.symlink',
                           'os.chdir', 'os.chmod', 'os.chown', 'os.truncate', 'os.utime',
                           'os.posix_spawn', 'os.kill', 'syslog.', 'http.client.', 'urllib.',
                           'ftplib.', 'smtplib.', 'shutil.')):
        record(event, '<arguments redacted>', 'APPLICATION_SIDE_EFFECT_IO', 'PC1.1',
               'Prohibited endpoint attempt')

sys.addaudithook(audit)
# Audit hooks do not observe writes to an already-open text stream or DB calls
# on an existing connection. Guard those channels explicitly as well.
class GuardedStream:
    def __init__(self, stream, label):
        self.stream, self.label = stream, label

    def __getattr__(self, name):
        value = getattr(self.stream, name)
        if name in ('buffer', 'raw'):
            return GuardedStream(value, self.label + '.' + name)
        if name in ('write', 'writelines', 'read', 'readline', 'readlines', 'readinto', 'flush'):
            def operation(*args, **kwargs):
                if active:
                    record('existing_stream_' + name, self.label, 'APPLICATION_SIDE_EFFECT_IO', 'PC1.1',
                           'Existing standard-stream I/O, including console telemetry')
                return value(*args, **kwargs)
            return operation
        return value

    def __iter__(self):
        if active:
            record('existing_stream_iteration', self.label, 'APPLICATION_SIDE_EFFECT_IO', 'PC1.1',
                   'Existing input-stream iteration')
        return iter(self.stream)

for stream_name in ('stdin', 'stdout', 'stderr'):
    setattr(sys, stream_name, GuardedStream(getattr(sys, stream_name), stream_name))

endpoint_prefixes = ('src.application.service', 'src.application.repository',
                     'src.application.execution', 'src.observability', 'finrobot', 'logging', 'sqlite3')

def profile(frame, event, arg):
    if not active or phase == 'LATER_EXPLICIT_SYMBOL_ACCESS':
        return
    if event == 'call':
        module = frame.f_globals.get('__name__', '')
    elif event == 'c_call':
        module = getattr(arg, '__module__', '') or ''
        owner = getattr(arg, '__self__', None)
        if owner is not None and type(owner).__module__.startswith('sqlite3'):
            module = type(owner).__module__
    else:
        return
    if module.startswith(endpoint_prefixes):
        record('application_endpoint_dispatch', module, 'APPLICATION_SIDE_EFFECT_IO', 'PC1.1',
               'Service/provider/repository/DB/telemetry function call')

sys.setprofile(profile)
original_create = external.ExtensionFileLoader.create_module
original_exec = external.ExtensionFileLoader.exec_module

def native_create(self, spec):
    if active:
        record('native_initialization_coverage_gap', spec.name, 'UNKNOWN', 'PC1.3',
               'Executable loading and native initialization cannot be separated by Python audit hooks; '
               'native getenv/file/socket operations have no independent observation')
        events[-1]['binary_path'] = spec.origin
    return original_create(self, spec)

external.ExtensionFileLoader.create_module = native_create
control_results = []
if sys.argv[1] == 'CONTROLS':
    phase = 'GUARD_CONTROLS'
    controls = [
        ('builtins.open/read', lambda: open('/WP06_GUARD_CONTROL_NOT_A_REAL_INPUT', 'rb')),
        ('builtins.open/write', lambda: open('/WP06_GUARD_CONTROL_NOT_A_REAL_OUTPUT', 'wb')),
        ('io.open', lambda: io.open('/WP06_GUARD_CONTROL_NOT_A_REAL_INPUT', 'rb')),
        ('os.open', lambda: os.open('/WP06_GUARD_CONTROL_NOT_A_REAL_INPUT', os.O_RDONLY)),
        ('environ.lookup', lambda: os.environ['WP06_GUARD_CONTROL']),
        ('getenv', lambda: os.getenv('WP06_GUARD_CONTROL')),
        ('environ.iteration', lambda: list(os.environ)),
        ('environ.length', lambda: len(os.environ)),
        ('os.stat', lambda: os.stat('/WP06_GUARD_CONTROL_NOT_A_REAL_INPUT')),
        ('os.listdir', lambda: os.listdir('/WP06_GUARD_CONTROL_NOT_A_REAL_INPUT')),
        ('os.read', lambda: os.read(-1, 1)),
        ('os.write', lambda: os.write(-1, b'x')),
    ]
    # Validate actual endpoint audit producers using stdlib imports outside the guard interval.
    import socket
    import subprocess
    import sqlite3
    import logging
    connection = sqlite3.connect(':memory:')
    controls += [('stdout.write', lambda: sys.stdout.write('NEVER_WRITTEN')),
                 ('stderr.write', lambda: sys.stderr.write('NEVER_WRITTEN')),
                 ('sqlite.read', lambda: connection.execute('SELECT 1')),
                 ('sqlite.write', lambda: connection.execute('CREATE TABLE never_created (x)')),
                 ('telemetry.log', lambda: logging.warning('NEVER_LOGGED')),
                 ('service.branch', lambda: find('src.application.service', __import__)),
                 ('repository.branch', lambda: find('src.application.repository', __import__)),
                 ('provider.branch', lambda: find('finrobot', __import__))]
    controls += [('socket.socket', lambda: socket.socket()),
                 ('subprocess.Popen', lambda: subprocess.Popen(['/WP06_NEVER_EXECUTED'])),
                 ('sqlite3.connect', lambda: sqlite3.connect(':memory:'))]
    for name, operation in controls:
        sys.setprofile(profile)
        offset = len(events)
        active = True
        try:
            operation()
        except ProhibitedIO:
            control_results.append({'name': name, 'blocked': True, 'event_count': len(events) - offset})
        finally:
            active = False
    sys.setprofile(profile)
    offset = len(events)
    active = True
    assert sum([1, 2, 3]) == 6 and json.loads('{"ok":true}') == {'ok': True}
    active = False
    assert sys.getprofile() is profile
    connection.close()
    assert len(events) == offset
    print(json.dumps({'controls': control_results, 'expected_control_count': len(controls),
                      'negative_control_event_count': len(events) - offset, 'events': events}))
    sys.exit(0)
active = True
completed = False
error = None
try:
    if sys.argv[1] == 'FI1':
        import src.application.evaluation_mechanism
    else:
        import src.application
    completed = True
except BaseException as exc:
    error = type(exc).__name__
finally:
    active = False
cold_events = list(events)
service_loaded = any(n == 'src.application.service' or n == 'pydantic' or n.startswith('pydantic.')
                     or n == 'finrobot' or n.startswith('finrobot.') for n in sys.modules)
counts = {key: sum(e['classification'] == key for e in cold_events)
          for key in ('NORMAL_MODULE_LOADER_IO', 'APPLICATION_SIDE_EFFECT_IO', 'UNKNOWN')}
result = {'phase': phase, 'initial_relevant_modules': relevant,
          'instrumentation_preloads': initial_modules,
          'startup_boundary': 'After ordinary interpreter startup and instrumentation, before src parent entry',
          'python': sys.version, 'executable': sys.executable,
          'bytecode_writes_disabled': sys.dont_write_bytecode,
          'import_completed': completed, 'error': error, 'service_loaded': service_loaded,
          'module_body_order': list(module_order), 'counts': counts, 'events': cold_events,
          'coverage': 'Python audit, loader/filesystem/descriptor primitives, environ, existing standard streams and endpoint call guards; native gaps explicitly UNKNOWN',
          'deduplication': 'Wrapped stat/listdir attempts counted once; matching listdir audit notification correlated by loader_depth',
          'later_explicit_symbol_access': 'NOT_RUN',
          'guard_interval': 'Before first src parent lookup through completed or failed literal import; no counter reset',
          'endpoint_profile_intact': sys.getprofile() is profile,
          'native_initialization_side_effect_total': 'UNKNOWN',
          'native_coverage': 'NOT_PROVEN: native environment, syscalls and loss accounting',
          'invocation': 'NOT_RUN'}
if sys.argv[1] == 'FI1' and completed and not counts['APPLICATION_SIDE_EFFECT_IO']:
    phase = 'EVALUATOR_INVOCATION'
    offset = len(events)
    active = True
    try:
        import src.application.evaluation_mechanism as cached
        assert cached is sys.modules['src.application.evaluation_mechanism']
        normal = cached.evaluate_mechanism(invocation_package)
        try:
            cached.evaluate_mechanism({'provider_callback': lambda: (_ for _ in ()).throw(AssertionError('CALLBACK'))})
        except cached.MechanismInputError:
            invalid_input_rejected = True
        else:
            invalid_input_rejected = False
        result['invocation'] = {'normal_report': normal, 'invalid_input_rejected': invalid_input_rejected,
                                'cached_module_identity': True}
    finally:
        active = False
    result['invocation_events'] = events[offset:]

# Do not proceed into a later phase after a cold-import stop condition.
if sys.argv[1] == 'FI2' and completed and not counts['APPLICATION_SIDE_EFFECT_IO'] and not counts['UNKNOWN']:
    phase = 'LATER_EXPLICIT_SYMBOL_ACCESS'
    active = True
    try:
        from src.application import ResearchApplicationService
        from src.application.service import ResearchApplicationService as original
        assert ResearchApplicationService is original
        result['later_explicit_symbol_access'] = 'PASS'
    finally:
        active = False
    result['later_events'] = events[len(cold_events):]
    result['later_module_body_order'] = module_order[len(result['module_body_order']):]
print(json.dumps(result, sort_keys=True))
'''


_RUNTIME_MANIFEST = Path('/Users/mac/codex-observability-setup/vefin-build-state/wp06-pc-t1-prospective-platform-baseline/WP06_EXACT_PINNED_RUNTIME_MANIFEST_V2.json')
_RUNTIME_MANIFEST_SHA256 = '3fc9748c8741dfa31642c2eb4ba6ba0c8327c530c90d47ff4a8cd7ba4092b2a9'


def _verify_option_t_manifest():
    import sys
    raw = _RUNTIME_MANIFEST.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == _RUNTIME_MANIFEST_SHA256
    manifest = json.loads(raw)
    assert manifest['status'] == 'ACTIVE_EXACT_MANIFEST_BOUND_PROSPECTIVELY'
    assert manifest['pc_t1'] == 'CLOSED' and manifest['required_missing_identities'] == []
    identity = manifest['frozen_python_identity']
    assert sys.version == identity['version']
    assert Path(sys.executable).resolve() == Path(identity['realpath'])
    for row in manifest['directly_hashable_identities']:
        path = Path(row['path'])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['expected_sha256']
        assert str(path.resolve()) == (row['expected_realpath'] or row['current_realpath'])
    assert subprocess.check_output(['/usr/bin/sw_vers'], text=True) == manifest['os_context']['macos']
    assert subprocess.check_output(['/usr/bin/uname', '-a'], text=True) == manifest['os_context']['darwin_kernel']
    assert subprocess.check_output(['/usr/bin/uname', '-m'], text=True).strip() == manifest['os_context']['architecture']
    return manifest


def test_FI1_FI2_guard_controls():
    import sys
    child = subprocess.run([sys.executable, '-B', '-c', _COLD_IMPORT_PROBE, 'CONTROLS'],
                           input='{}', cwd=REPO, capture_output=True, text=True, timeout=60)
    assert child.returncode == 0, child.stderr
    result = json.loads(child.stdout)
    print('PC1_GUARD_CONTROLS=' + json.dumps(result, sort_keys=True))
    assert len(result['controls']) == result['expected_control_count']
    assert all(row['blocked'] and row['event_count'] == 1 for row in result['controls'])
    assert result['negative_control_event_count'] == 0


@pytest.mark.parametrize('phase', ['FI1', 'FI2'])
def test_FI1_FI2_normal_cold_import_accounting(phase, package, report):
    import sys
    manifest = _verify_option_t_manifest()
    wire = deepcopy(package)
    for key in ('envelopes', 'snapshots'):
        wire[key] = [value.decode('utf-8') for value in wire[key]]
    child = subprocess.run([sys.executable, '-B', '-c', _COLD_IMPORT_PROBE, phase],
                           input=json.dumps({'package': wire} if phase == 'FI1' else {}),
                           cwd=REPO, capture_output=True, text=True, timeout=60)
    assert child.returncode == 0, child.stderr
    result = json.loads(child.stdout)
    modules = {row['name']: row for row in manifest['modules']}
    unknowns = [e for e in result['events'] if e['classification'] == 'UNKNOWN']
    dispositions = []
    for event in unknowns:
        module = modules.get(event['target'])
        if (event['event_type'] == 'native_initialization_coverage_gap' and module is not None
                and event.get('binary_path') == module['binary_path']):
            dispositions.append({'event_ordinal': event['event_ordinal'], 'module': event['target'],
                                 'binary_path': module['binary_path'], 'sha256': module['sha256'],
                                 'raw_classification': 'UNKNOWN',
                                 'disposition': 'TRUSTED_PINNED_RUNTIME_BOUNDARY_NOT_FULLY_OBSERVED',
                                 'reason': 'Exact module origin and binary hash match active prospective manifest; native initialization remains not fully observed'})
    result['boundary_dispositions'] = dispositions
    result['other_unadmitted_unknown_count'] = len(unknowns) - len(dispositions)
    result['runtime_manifest_sha256'] = _RUNTIME_MANIFEST_SHA256
    result['claim'] = 'NO_OBSERVED_VEFIN_APPLICATION_SIDE_EFFECT_IO_ON_IMPORT AND NO_EAGER_SERVICE_BRANCH AND PINNED_RUNTIME_BOUNDARY_EXPLICIT'
    print('PC1_IO_RESULT=' + json.dumps(result, sort_keys=True))
    assert result['initial_relevant_modules'] == []
    assert result['endpoint_profile_intact']
    assert result['import_completed'], result['error']
    assert not result['service_loaded']
    assert result['counts']['APPLICATION_SIDE_EFFECT_IO'] == 0, 'APPLICATION_SIDE_EFFECT_IO_NONZERO'
    assert result['other_unadmitted_unknown_count'] == 0, 'UNADMITTED_UNKNOWN_IO_NONZERO'
    assert len({row['module'] for row in dispositions}) == len(dispositions)
    if phase == 'FI1':
        assert {row['module'] for row in dispositions} == {'_hashlib', '_blake2', 'math', '_uuid'}
        assert result['invocation_events'] == []
        assert result['invocation']['normal_report'] == report
        assert result['invocation']['invalid_input_rejected']
    else:
        assert result['later_explicit_symbol_access'] == 'PASS'
    # External execution evidence additionally checks loaded-image UUIDs and shared cache before/after FI1–FI5.
    _verify_option_t_manifest()


@pytest.mark.parametrize('ordering', ['package-first', 'direct-service-first'])
def test_FI3_original_public_class_identity(ordering):
    import sys
    probe = r'''
import sys
import importlib
if sys.argv[1] == 'direct-service-first':
    from src.application.service import ResearchApplicationService as original
    import src.application
else:
    import src.application
    for name in ('evaluation_input', 'evaluation_mechanism', 'persistence', 'closure_recovery', 'unknown_name'):
        try:
            getattr(src.application, name)
        except AttributeError:
            pass
        else:
            raise AssertionError(name)
    assert 'src.application.service' not in sys.modules
    from src.application import evaluation_input, evaluation_mechanism
    assert 'src.application.service' not in sys.modules
assert src.application.__all__ == ['ResearchApplicationService']
from src.application import ResearchApplicationService as from_package
from src.application.service import ResearchApplicationService as original
assert from_package is original
assert src.application.ResearchApplicationService is original
from src.application import *
assert ResearchApplicationService is original
assert isinstance(original, type) and original.__module__ == 'src.application.service'
assert src.application.ResearchApplicationService is src.application.ResearchApplicationService
try:
    src.application.unknown_name
except AttributeError:
    pass
else:
    raise AssertionError('unknown export')
from src.application import evaluation_input, evaluation_mechanism, persistence, closure_recovery
for module in (evaluation_input, evaluation_mechanism, persistence, closure_recovery):
    assert importlib.import_module(module.__name__) is module
    assert module is sys.modules[module.__name__]
assert src.application.__all__ == ['ResearchApplicationService']
'''
    child = subprocess.run([sys.executable, '-B', '-c', probe, ordering],
                           cwd=REPO, capture_output=True, text=True, timeout=60)
    assert child.returncode == 0, child.stderr


def test_FI4_cached_import_and_direct_environment_guards(package, report, monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append('FORBIDDEN_IO')
        raise AssertionError('FORBIDDEN_IO')

    with monkeypatch.context() as guard:
        for module, name in [(builtins, 'open'), (io, 'open'), (os, 'open'), (os, 'getenv'),
                             (os, 'stat'), (os, 'listdir'), (socket, 'socket'),
                             (socket, 'create_connection'), (subprocess, 'Popen'),
                             (os._Environ, '__getitem__'), (os._Environ, '__iter__')]:
            guard.setattr(module, name, forbidden)
        # Separate positive controls validate direct access and iteration guards.
        for control in (lambda: os.environ['WP06_GUARD_CONTROL'], lambda: list(os.environ)):
            with pytest.raises(AssertionError, match='FORBIDDEN_IO'):
                control()
        assert len(calls) == 2
        calls.clear()
        assert importlib.import_module('src.application.evaluation_mechanism') is mechanism
        assert mechanism.evaluate_mechanism(package) == report
        with pytest.raises(mechanism.MechanismInputError):
            mechanism.evaluate_mechanism({'provider_callback': forbidden})
        assert calls == []
