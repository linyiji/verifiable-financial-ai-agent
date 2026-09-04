# CONTRACT_CHANGE_REQUEST — WS-V Proof Persistence

Status: `REQUESTED`

Owner requested: Coordinator / PostgreSQL single writer

Requester: WS-V RISC Zero Proof

## Reason

WS-V deliberately does not modify the frozen shared contracts, global database configuration, or
Alembic schema. Phase 3 integration needs durable proof lineage rather than treating the receipt
path returned by the adapter as the system of record.

## Requested durable records

Persist the already-frozen domain fields without changing their meaning:

- `ProofInputCommitment`: commitment id, run id, calculation id, formula id, capability id,
  implementation hash, ordered evidence refs, canonical inputs, input commitment, expected output
  commitment, timestamps.
- `ProofRecord`: proof id, run id, calculation id, backend, program id, image id, implementation
  hash, input commitment, receipt artifact ref/hash, journal hash, status, proving duration,
  timestamps.
- `ProofVerificationRecord`: verification id, proof id, verifier, image id, receipt hash, journal
  hash, status, verified, detail, timestamps.
- `ProofArtifactReference`: artifact id, proof id, artifact type/ref, content hash, byte size,
  timestamps.

## Integrity requirements

- Foreign keys must tie proof records to their run and calculation and verification/artifact rows
  to their proof.
- `proof_id`, `commitment_id`, `verification_id`, and `artifact_id` are unique/idempotent keys.
- Store the receipt outside relational JSON; persist only its controlled artifact reference,
  SHA-256 hash, and size.
- Persist ordered evidence references and canonical inputs losslessly.
- A `VERIFIED` transition must require matching program image id, input commitment, receipt hash,
  and journal hash. Failure may never overwrite a prior immutable verification record.

## Integration note

The adapter currently returns all required values in `ProofResult.verifier_result` and the receipt
artifact path in `ProofResult.receipt_ref`. The Coordinator should map those values into frozen
domain models and the migration after merging WS-V. No persistence migration is included in the
WS-V branch.
