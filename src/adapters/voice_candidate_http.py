"""Explicit isolated official-client construction and credential-free RTC gate."""
import asyncio
import hashlib
import json
import ssl
import time
from pathlib import Path
import certifi
import httpx


def config(profile):
    node = next(n for n in profile['nodes']['llm'] if n['id'] == profile['llm_selected'])
    if node['base_url'].rstrip('/') != 'https://api.deepseek.com' or profile.get('llm_trust_env') is not False:
        raise ValueError('UNSUPPORTED_TRUST_PREFLIGHT_CONFIGURATION')
    return {'base_url': node['base_url'].rstrip('/'), 'trust_env': False,
            'proxy': None, 'verify': True, 'check_hostname': True, 'retries': 0,
            'follow_redirects': False, 'connect_seconds': 3, 'io_seconds': 5,
            'ca_path': certifi.where(), 'ca_sha256': hashlib.sha256(Path(certifi.where()).read_bytes()).hexdigest()}


def create_client(profile):
    c = config(profile)
    ctx = ssl.create_default_context(cafile=c['ca_path'])
    return httpx.AsyncClient(trust_env=False, follow_redirects=False,
        transport=httpx.AsyncHTTPTransport(verify=ctx, retries=0, trust_env=False),
        timeout=httpx.Timeout(5, connect=3))


def fingerprint(profile):
    return hashlib.sha256(json.dumps({'configuration': config(profile), 'profile': profile,
        'constructor_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, sort_keys=True).encode()).hexdigest()


def require_receipt(profile, receipt):
    if receipt.get('fingerprint') != fingerprint(profile) or receipt.get('status') != 'PASS':
        raise RuntimeError('LLM_TLS_PREFLIGHT_MISSING_OR_CONFIGURATION_CHANGED')
    if len(receipt.get('connections', [])) != 2 or not all(x.get('verified') for x in receipt['connections']):
        raise RuntimeError('LLM_TLS_PREFLIGHT_INCOMPLETE')


async def preflight(profile):
    result = {'fingerprint': fingerprint(profile), 'configuration': config(profile), 'connections': [], 'status': 'FAIL'}
    for _ in range(2):
        started = time.monotonic(); events = []
        async def trace(name, info):
            events.append({'event': name, 'seconds': time.monotonic()-started})
        row = {'new_client': True, 'credential_free': True}
        try:
            async with create_client(profile) as client:
                async with asyncio.timeout(5):
                    response = await client.get(config(profile)['base_url']+'/', extensions={'trace': trace})
                stream = response.extensions.get('network_stream')
                obj = stream.get_extra_info('ssl_object') if stream else None
                row.update(http_status=response.status_code, url=str(response.url),
                    verified=obj is not None and str(response.url)=='https://api.deepseek.com/' and not response.is_redirect,
                    certificate=obj.getpeercert() if obj else None, tls_version=obj.version() if obj else None)
        except Exception as exc:
            row.update(verified=False, error_type=type(exc).__name__, error=str(exc))
        row.update(elapsed_s=time.monotonic()-started, events=events);result['connections'].append(row)
        if not row['verified']:break
    if len(result['connections'])==2 and all(r['verified'] for r in result['connections']):result['status']='PASS'
    return result

if __name__ == '__main__':
    import sys
    profile = json.loads(Path(sys.argv[2]).read_text()); path = Path(sys.argv[3])
    if sys.argv[1]=='check':require_receipt(profile,json.loads(path.read_text()))
    elif sys.argv[1]=='probe':
        r=asyncio.run(preflight(profile));path.write_text(json.dumps(r,ensure_ascii=False,indent=2));print(r['status'])
        if r['status']!='PASS':raise SystemExit(1)
