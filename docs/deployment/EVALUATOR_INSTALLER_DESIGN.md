# Evaluator installer contract

Status: source/offline foundation; public installer assets are **PUBLICATION_REQUIRED**.
The real Owner gateway is **NOT_DEPLOYED**. Neither publication nor clean-machine
Windows/macOS acceptance is implied by portable tests or a local image build.

## Common module and lifecycle

Thin platform scripts prepare Docker with explicit consent for system installation,
verify release package SHA-256, and build the shared image. Python and Node run inside
Docker; evaluators do not install them separately. The shared `installer/cli.py`
implements install, start, stop, status, doctor, update and open. Host wrappers only
provide mounts, terminal input and the OS default browser.

`installer/state.py` defines the 17 ordered stages from SYSTEM_CHECK through READY.
An interrupted invocation repeats idempotent checks, storage and migrations; saved
stages are observations, not permission to skip validation. The PostgreSQL named
volume and generated local password survive stop and repeated installation. The
Compose project is scoped by installation path. No reset or data deletion is offered.

Backend and web host ports bind to loopback only. Health must pass before a fixed
browser-open signal is consumed. Installation automatically continues into first
startup. Startup cannot become READY without accepted evaluator authorization.

## Credentials and authority

Only encrypted bundles in user-selected locations are discovered. A hidden terminal
prompt supplies the passphrase to the existing bundle parser. Existing zero-cost
readiness verifies gateway authorization; route permissions are ALLOWED, never live
provider certification. No paid provider probe or research admission is performed.

The common CLI transfers the session token through Docker exec standard input to a
short-lived Unix socket in the API container's private tmpfs. The API repeats readiness
before activation. The token is not placed in arguments, environment, Compose JSON,
state or a disk cache. Restart requires unlocking again. Host administrators and the
Docker daemon can inspect process memory; there is no unextractable-secret claim.

The separate local database password is generated randomly and stored in a protected
file (POSIX mode 0600; Windows user-only installation-directory ACL). It is mounted as
a Compose secret. Safe state contains stage/version/image and filename metadata only.
Owned errors suppress raw subprocess output and exception details.

## Release integrity and local packaging

Default resolution uses GitHub's latest stable release, not develop. Explicit version
selection uses an immutable accepted tag by convention; release assets must remain
Owner-controlled. `evaluator-manifest.json` binds schema, version, archive URL and SHA-256.
The hash is verified before extraction/execution. This is HTTPS plus hash integrity,
not a cryptographic release signature. Base image manifests are digest-pinned; Python
dependencies remain package-constrained, not a fully reproducible lockfile build.

For a future publisher, `python -m installer.package --version TAG --output DIRECTORY`
creates local ZIP/manifest assets from a clean committed tree. It does not publish or
create a tag. Uploading assets, publishing scripts and validating public commands are
separate authorized work. Until then, use the repository-relative commands in the
[guided installation page](INSTALL_EVALUATOR.md). An explicitly supplied source package
is a reviewed-source path, not a claim of downloaded release verification.

## Standard versus proof evaluation

Option B is selected: standard containers support browsing and limited workflows.
They do not package an accepted RISC Zero proof runtime or expose the Docker socket
to the API for generated-capability validation. Existing proof/capability release gates
remain enforced. `--full-proof` stops with FULL_PROOF_UNAVAILABLE rather than pretending
to support complete release-gated execution. Use [advanced installation](ADVANCED_INSTALLATION.md)
for that environment. Research, admission, lineage, memory, BYOK, provider capability
and adaptive recovery contracts are unchanged.

## Acceptance boundary

Portable tests exercise common state transitions, release verification, credential
failure mapping, service commands, protected state and browser ordering. Bash syntax
and Windows source contracts are checked separately. Windows native execution and a
fresh macOS user journey through actual gateway readiness remain host-validation work.
Docker image build/import checks are not clean-machine end-to-end acceptance.
