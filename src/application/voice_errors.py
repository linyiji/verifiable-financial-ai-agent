"""Node error vocabulary; original codes/exceptions remain available to adapters."""
import asyncio


def voice_error_category(error):
    code = str(getattr(error, 'code', ''))
    name = type(error).__name__
    if isinstance(error, asyncio.CancelledError):
        return 'CANCELLED'
    if 'NO_WORDS' in code:
        return 'NO_WORDS'  # Not evidence of silence.
    if 'GROUNDING' in code:
        return 'GROUNDING_FAILED'
    if isinstance(error, TimeoutError) or 'TIMEOUT' in code or 'DEADLINE' in code:
        return 'TIMEOUT'
    if 'StructuredOutput' in name or 'SCHEMA' in code:
        return 'SCHEMA_FAILED'
    if any(s in code for s in ('UNAUTHORIZED', 'FORBIDDEN', 'QUOTA', 'REJECTED')):
        return 'PROVIDER_REJECTED'
    if 'UPLOAD' in code:
        return 'UPLOAD_FAILED'
    if any(s in code + name for s in ('CONNECT', 'Connect', 'TRANSPORT', 'Transport')):
        return 'CONNECTION_FAILED'
    if 'FORMAT' in code or 'INVALID_PCM' in str(error):
        return 'FORMAT_FAILED'
    return 'NODE_FAILED'
