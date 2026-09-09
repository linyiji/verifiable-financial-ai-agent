# Private investor credentials

[简体中文](README.zh-CN.md)

Receive `VFA-Investor-Access.vfacred` privately from the Owner. Copy/rename it to
`<unpacked-repository>/credentials/active.vfacred` (Windows:
`<unpacked-repository>\credentials\active.vfacred`). Never upload either file.

After the documented platform installer has been run, use `vfa start`. Enter
`Credential passphrase:` in the terminal; input is hidden. Do not put the
passphrase in command arguments, environment files or chat. `vfa doctor` shows
configuration only, not proof of successful live provider access. `vfa stop`
stops this installation while preserving its research database.

The installer records the selected unpacked product directory separately from
its private installation/database directory. Keep that product directory in place;
rerun the platform installer from a newly selected release when changing it.
Only its fixed `credentials` directory is mounted read-only for bundle discovery.

An existing `active.vfacred` selects DIRECT_REGISTRY first. A conflicting explicit
bundle path is rejected. A corrupt direct bundle does not fall back to gateway
or default keys. Without it, existing `.vfaeval` gateway discovery remains available.
Native BYOK remains a separate documented configuration, never merged into direct
mode. An explicit `--bundle` may select a `.vfacred` file; startup never recursively
searches for direct bundles.

Direct payload scope: four FMP keys with existing bounded pool policy; Bocha Web
Search only; MiMo `mimo-v2.5`; TeamoRouter `gpt-5.6-sol`, `gpt-5.6-luna`,
`gpt-5.6-terra`. States are CONFIGURED, not automatically LIVE_PROVEN.

Encryption: AES-256-GCM with random salt/nonce and fixed scrypt parameters. Decrypted
secrets exist only in process memory and the local private socket handoff, not
provider `.env`/JSON/temp files or Docker arguments/environment. A privileged local
user can inspect running process memory; this is not an unextractability guarantee.

The 2026-09-09 local acceptance verified direct-bundle startup, exact image identity,
the packaged Linux RISC Zero runtime, governed Sandbox Broker and one isolated NVDA
Live. This is bounded local Alpha evidence, not a guarantee of upstream availability,
Windows clean-machine acceptance or production security.

Owner issuance (from the repository's configured Python environment):
`python -m src.evaluator.direct_bundle --registry /private/path/provider-registry.local.json --output credentials/active.vfacred`
The command asks for hidden input twice and verifies round-trip before writing
the encrypted file. It refuses to overwrite an existing bundle. The plaintext
staging registry remains Owner-only and is never part of investor installation.
