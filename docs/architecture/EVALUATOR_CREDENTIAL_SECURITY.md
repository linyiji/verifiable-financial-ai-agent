# Evaluator credential security foundation

[简体中文](EVALUATOR_CREDENTIAL_SECURITY.zh-CN.md)

In gateway evaluator mode, provider keys are server-side only. An evaluator machine receives an opaque, scoped, expiring, revocable, quota-limited bearer credential, not encrypted copies of upstream keys. Local machine owners/admins can extract process secrets: **no unextractable-local-secret claim** is made. Gateway policy is the authority boundary.

Current evaluation guidance (2026-09-08): the Owner gateway is NOT_DEPLOYED, so investors and testers should use direct-API BYOK for facilitated testing. BYOK uses a user's own key or an independently scoped test key supplied privately by the Owner and configured locally. Built-in API integration does not mean keys embedded in source, images or installers. The one-command installer remains a gateway-only foundation, not a one-command BYOK installation path; see [advanced installation](../deployment/ADVANCED_INSTALLATION.md).

## Components and authority

Local product → EvaluatorGatewayLLM / EvaluatorGatewayFinancialData → Owner gateway → existing MiMo / TeamoRouter / FMP authority. Explicit `VFA_CREDENTIAL_MODE=evaluator` requires an activated in-process session. Missing gateway/session authority fails closed; it never selects BYOK based on missing keys. Legacy configuration defaults to BYOK for compatibility. Investors/testers should explicitly configure BYOK following the current direct-API instructions rather than rely on defaults or an automatic gateway fallback.

Gateway-issued bearer secrets are 32 random bytes (URL-safe encoding, `vfa_` prefix). The private SQLite store retains only SHA-256 verifier, public ID and policy/accounting state. High token entropy, not a human password, protects the verifier against guessing. Expiry/revocation/scope/quota/rate are checked transactionally before each dispatch; readiness also rechecks expiry/revocation. Tokens do not confer admin access, arbitrary models, host/path selection or provider secret retrieval. A stolen token can spend its remaining authorized allowance until expiry/revocation.

## Portable encrypted bundle

Version 1 uses AES-256-GCM, random 96-bit nonce and 128-bit authentication tag, with a 32-byte key derived by Scrypt (`N=32768, r=8, p=1`) and random 128-bit salt. Gateway URL, version and credential ID are authenticated associated data. Changing metadata or ciphertext fails closed. The parser rejects duplicate/unknown fields, oversized/corrupt envelopes and unsupported versions; fixed KDF parameters cannot be raised by an untrusted bundle. Passwords must be 12–1024 characters; use a random high-entropy activation secret, not a guessable phrase. Offline password guessing is still possible if the encrypted file is stolen.

These are established cryptography-library primitives, not custom cryptography: [cryptography AESGCM documentation](https://cryptography.io/en/latest/hazmat/primitives/aead/) and [Scrypt documentation](https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/). AEAD authenticates the bundle metadata with the password-derived key; it is not an Owner digital signature. Obtain the bundle and separate secret through trusted Owner channels. HTTPS and an optional configured origin pin protect intended gateway routing. Evaluator-to-gateway and gateway model transports disable redirects and ambient HTTP proxies. The existing Owner FMP transport retains its environment-proxy behavior; the Owner must secure that environment. Explicit loopback HTTP is development-only.

## Local credential lifecycle

The launcher prompts using hidden terminal input and fails if secure prompting is unavailable. It decrypts to memory, calls readiness and activates only after the credential ID matches. No token argument, environment variable, plaintext dotenv, local token cache or UI field is supported. The native launcher starts the backend in the same process. The Docker installer instead transfers the token through subprocess standard input and a private tmpfs Unix socket; the API repeats readiness before in-process activation. Neither path persists a token cache. Exit clears the session reference; Python cannot promise immediate memory zeroization. Crash dumps, swap, debugger access, malicious dependencies, terminal capture and compromised hosts are outside this foundation's protection. Protect the host and bundle/password distribution accordingly.

macOS Keychain: **NOT_IMPLEMENTED**. Windows Credential Manager: **NOT_IMPLEMENTED**. Both platforms and WSL2 use the portable session-only path. POSIX paths with spaces/Unicode and Windows drive-path syntax have offline coverage; native Windows/WSL2 host execution and full native proof parity were not validated in this task.

## Failure and telemetry boundaries

EvaluationAuthorizationError is separate from ordinary LLM/provider failures. Expiry, revocation, route denial, budget/rate exhaustion and gateway authority unavailability stop execution rather than attempting all providers. Adaptive recovery records failed attempt/terminal evidence, not a switch. Genuine upstream read/connect/protocol failures retain existing bounded policy decisions; no gateway fallback replaces the Main-Agent runtime. Same Run/Task identity and original candidate priority are preserved. Readiness is configured authorization, never new capability certification.

Only owned error classes are returned; request validation does not echo submitted fields. Gateway audit excludes bearer values, upstream credentials, Authorization headers, prompts and hidden reasoning. Known Owner keys/token are filtered from outgoing response bodies; this is defense-in-depth, not a guarantee against a compromised upstream intentionally encoding a secret. The gateway never intentionally includes provider keys in model prompts or data payloads. TLS keys, deployment logs, proxy/APM settings and crash dumps remain Owner responsibilities.

## Explicit limitations

This is a bounded evaluation gateway, not enterprise Auth/RBAC/SSO, commercial billing, per-dollar cost enforcement, distributed quota service or protection from a compromised Owner server. Request-count quota may be consumed by retries or failed/uncertain operations. In-flight authorized requests can finish after revocation. Fixed-minute limits require edge controls for burst/unauthenticated traffic. Database backups and permissions must remain private and consistent; rolling counters backward is unsafe.

Tests establish offline contract behavior, not real deployment or universal secrecy. No live provider calls, production research Runs or actual gateway deployment were made in this task. See [Owner deployment requirements](../deployment/EVALUATOR_GATEWAY.md).
