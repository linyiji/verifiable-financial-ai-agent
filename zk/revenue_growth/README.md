# Revenue Growth RISC Zero Proof

This workspace proves `revenue_growth_v1` as an exact reduced rational:

```text
(current_revenue_minor - prior_revenue_minor) / abs(prior_revenue_minor)
```

The guest commits only the formula id, compiled image id, input commitment, expected output
commitment, and canonical rational result. The input commitment binds the run, calculation,
formula, capability, implementation hash, ordered evidence references, canonical integer inputs,
and expected output commitment.

## Security boundary

- RISC Zero SDK/build crates are pinned to `3.0.6`.
- The host enables `risc0-zkvm/disable-dev-mode`.
- Both the build wrapper and runtime host reject the mere presence of `RISC0_DEV_MODE`.
- `prove` creates a receipt but does not claim verification.
- `verify` runs as a separate process, pins the compiled image id, performs cryptographic receipt
  verification, and compares the verified journal with an independently derived expectation.
- The Python adapter executes the pre-built host binary directly; it never shells out to Cargo.

## Build and execute

Install the official `rzup` toolchain first. Then run the single build boundary:

```sh
./zk/revenue_growth/build-host.sh
```

The resulting executable is:

```text
zk/revenue_growth/target/release/revenue-growth-proof-host
```

Supported commands are `image-id`, `prove --input ... --receipt ...`, and
`verify --input ... --receipt ...`. Each successful command emits one JSON object on stdout.
Errors are sent to stderr and exit non-zero.
