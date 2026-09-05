# FMP credential pool configuration

Keep real FMP credentials outside the repository in a local file with mode `0600`.
The supported environment shape is a contiguous, finite sequence:

```dotenv
FMP_API_KEY_1=
FMP_API_KEY_2=
FMP_API_KEY_3=
FMP_API_KEY_4=
```

Load that file into the process environment before starting the API or an acceptance
command. Numbered slots take precedence over the legacy single `FMP_API_KEY`. Slots must
start at `FMP_API_KEY_1`, remain contiguous, contain distinct non-empty values, and must
never be committed.

The FMP transport retains a successful slot. An HTTP 429 cools down that slot for the
current process and tries the next slot; HTTP 401 or 403 marks the slot unusable and tries
the next slot. Other provider, network, and data failures do not rotate credentials. Once
all configured slots are unavailable, the adapter fails closed with
`FMP_KEY_POOL_EXHAUSTED`.
