# Frontend Reference Versioning

Status: `GOVERNANCE_SPECIFICATION`

## 1. Rule

Every HTML/UX Reference and every Frontend implementation has an explicit version and content
identity. Every audit records their relationship. No audit may compare new TSX against a superseded
prototype without declaring and approving that mismatch.

The minimum visible pairing is:

```text
UX_REFERENCE_V9 <-> FRONTEND_V9
```

The version labels communicate intended semantic compatibility; hashes identify the exact bits.
Both are required.

## 2. Version coordinates

### UX Reference coordinate

```yaml
reference_id: UX_REFERENCE_V9
reference_revision: 9.0.0
status: DRAFT | APPROVED | SUPERSEDED | REVOKED
artifact_paths: []
artifact_sha256: <manifest-hash>
product_contract_versions: []
scene_corpus_version: <version>
interaction_matrix_version: <version>
approved_at: <timestamp>
approved_by: []
supersedes: UX_REFERENCE_V8
```

### Frontend coordinate

```yaml
frontend_id: FRONTEND_V9
frontend_revision: 9.0.0
source_sha: <full-sha>
source_tree_fingerprint: <sha256>
build_artifact_sha256: <sha256>
declared_reference_id: UX_REFERENCE_V9
compatibility_record: REF-COMPAT-...
```

The major `Vn` indicates the intended UX generation. The revision records compatible corrections
within that generation. Teams may use a stricter semantic-version scheme, but may not omit the
stable IDs or hashes.

## 3. Reference manifest contents

A reference version is more than one HTML file. Its manifest may include:

- HTML prototype(s) and assets;
- approved screenshots or visual-state captures with viewport metadata;
- page and component behavior specifications;
- content and product terminology;
- accessibility expectations;
- responsive/breakpoint expectations;
- six-Scene corpus version;
- interaction-contract matrix version;
- backend mapping constraints and known unavailable states;
- explicit limitations such as Demo-only behavior or disabled PDF;
- source documents and precedence order.

Each included file has a path, media type, SHA-256, role, and status. A directory path without a
manifest is not an auditable reference.

## 4. When to create a new reference version

| Change | Required reference action |
|---|---|
| approved visual correction with unchanged behavior | increment reference revision; retain same major generation if compatibility is preserved |
| interaction contract added/removed/changed | version interaction matrix and reference revision; major generation if journeys or model materially change |
| product semantic change | new approved reference version; normally a new major generation |
| Scene setup/steps/outcome/claim change | version Scene corpus and reference revision |
| accessibility/responsive expectation change | version reference revision and affected state captures/specification |
| backend-only wire change with identical UX | record compatibility revision; reference artifact may remain byte-identical |
| editorial documentation correction | patch revision if it changes an audit oracle; otherwise append non-normative erratum |

An implementation may advance without a visual artifact change only when the compatibility record
explains why UX semantics and reference hashes remain valid.

## 5. Compatibility record

Every Candidate has exactly one primary compatibility record:

| Field | Meaning |
|---|---|
| `compatibility_id` | stable record ID |
| `frontend_id` / `candidate_sha` | exact implementation |
| `reference_id` / `reference_sha256` | exact primary UX Reference |
| `relationship` | `EXACT_TARGET`, `COMPATIBLE_WITH_DECLARED_DELTA`, or `MISMATCH` |
| `change_ids` | approvals explaining permitted differences |
| `known_differences` | exhaustive reference-to-Candidate delta list |
| `superseded_reference_used` | boolean |
| `superseded_reason` | required if true |
| `replacement_reference` | current approved reference, if different |
| `required_tests` | tests proving compatibility/delta |
| `audit_disposition` | `PENDING`, `PASS`, or `FAIL` |

Meanings:

- `EXACT_TARGET`: the Candidate is intended to implement this approved reference without semantic
  deviation.
- `COMPATIBLE_WITH_DECLARED_DELTA`: differences are explicitly approved by Change Requests and are
  tested.
- `MISMATCH`: reference and Candidate cannot support a valid comparison; promotion fails.

## 6. Superseded-reference rule

If an auditor intentionally opens or renders a superseded prototype, the report must state:

```yaml
reference_mismatch:
  candidate_frontend: FRONTEND_V10
  compared_reference: UX_REFERENCE_V8
  current_reference: UX_REFERENCE_V10
  reason: <why this historical comparison is useful>
  allowed_purpose: HISTORICAL_REGRESSION_ONLY
  acceptance_authority: NONE
```

Historical comparison may detect regressions but cannot prove conformance to the current reference.
The Candidate must also be audited against its current approved primary reference. If that reference
does not exist or is not approved, the audit result is `FAIL`/`NOT_READY`; the auditor must not
silently treat the old prototype as current.

## 7. V8 seed registration

The existing repository identifies
`../../frontend_reference/financial_agent_workspace_v8_dynamic_path.html` and
`../frontend_v8/00_FRONTEND_READ_FIRST.md` through its companion contracts as the approved V8 UX
input. Before it is used in the first governed implementation-baseline audit, create a reference
manifest that:

1. assigns `UX_REFERENCE_V8` and a revision;
2. hashes the exact HTML and normative companion documents;
3. records document precedence;
4. binds the six-Scene and 64-interaction corpus versions;
5. records Demo/pre-integration and unavailable-capability limitations;
6. identifies any known divergence between the HTML reference and the remediation Candidate.

This registration identifies the approved UX input. It does not approve the React Candidate.

## 8. Audit comparison table

Every Delta Audit contains this table:

| Side | Frontend ID/SHA | UX Reference ID/hash | Relationship | Mismatch recorded | Authority |
|---|---|---|---|---|---|
| Previous baseline | exact values | exact values | approved baseline pairing | yes/no | accepted historical oracle |
| Candidate | exact values | exact values | exact/declared delta/mismatch | yes/no | proposed oracle |

Blank values, labels without hashes, or `latest` aliases fail the reference gate.

## 9. Storage and supersession

- Reference manifests are append-only and immutable after approval.
- New versions point to predecessors and list intentional differences.
- Superseded and revoked references remain accessible for audit history.
- Never overwrite the V8 HTML file and continue calling it `UX_REFERENCE_V8`; changed content gets a
  new revision/hash.
- Screenshots generated from a prototype record browser, viewport, scale, font/assets, locale, theme,
  and generation timestamp when used as visual oracles.
