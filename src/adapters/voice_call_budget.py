"""Optional operator-set, process-safe call cap. No credential or input logging."""
import fcntl
import json
import os
import time
import contextvars
from uuid import uuid4
from pathlib import Path


_active_reservation = contextvars.ContextVar('voice_budget_reservation', default=None)

def _held(ledger, node=None, exclude=None):
    return sum(r['remaining'] for r in ledger.get('reservations', [])
               if r['state']=='ACTIVE' and r['id']!=exclude and (node is None or r['node']==node))

def reserve(node, required):
    path=os.getenv('VEFIN_VOICE_CALL_LEDGER')
    if not path:return None
    if required<0:raise ValueError('NEGATIVE_RESERVATION')
    with open(path,'r+',encoding='utf-8') as f:
        fcntl.flock(f,fcntl.LOCK_EX);d=json.load(f)
        if d['state']!='OPEN':raise RuntimeError('VOICE_CALL_BUDGET_CLOSED')
        used=sum(a['node']==node for a in d['attempts'])
        if used+_held(d,node)+required>d['limits'][node] or len(d['attempts'])+_held(d)+required>d['limits']['TOTAL']:
            raise RuntimeError('VOICE_CALL_BUDGET_INSUFFICIENT_FOR_COMPLETE_ANSWER')
        ident=uuid4().hex;d.setdefault('reservations',[]).append({'id':ident,'node':node,'reserved':required,'remaining':required,'state':'ACTIVE'})
        f.seek(0);json.dump(d,f,ensure_ascii=False,indent=2);f.truncate();f.flush()
    return (ident,_active_reservation.set(ident))

def release(reservation):
    if reservation is None:return
    ident,token=reservation
    try:
        with open(os.environ['VEFIN_VOICE_CALL_LEDGER'],'r+',encoding='utf-8') as f:
            fcntl.flock(f,fcntl.LOCK_EX);d=json.load(f)
            r=next(x for x in d['reservations'] if x['id']==ident)
            r.update(state='RELEASED',released_unused=r['remaining'],remaining=0)
            f.seek(0);json.dump(d,f,ensure_ascii=False,indent=2);f.truncate();f.flush()
    finally:_active_reservation.reset(token)

def require_capacity(node: str, required: int) -> None:
    """Preflight a whole answer; charge still checks atomically per request."""
    path = os.getenv("VEFIN_VOICE_CALL_LEDGER")
    if not path:
        return
    with open(path, encoding="utf-8") as file:
        fcntl.flock(file, fcntl.LOCK_SH)
        ledger = json.load(file)
        if str(ledger.get('state', '')).upper() in {'CLOSED', 'SEALED', 'EXHAUSTED'}:
            raise RuntimeError('VOICE_CALL_BUDGET_CLOSED')
        used = sum(a['node'] == node for a in ledger['attempts'])
        total = sum(a['node'] != 'LOCAL_ASR' for a in ledger['attempts'])
        if required > ledger['limits'][node] - used - _held(ledger,node,exclude=_active_reservation.get()) or required > ledger['limits']['TOTAL'] - total - _held(ledger,exclude=_active_reservation.get()):
            raise RuntimeError('VOICE_CALL_BUDGET_INSUFFICIENT_FOR_COMPLETE_ANSWER')


def charge(node: str, provider: str, model: str) -> None:
    path = os.getenv("VEFIN_VOICE_CALL_LEDGER")
    if not path:
        return
    with open(path, "r+", encoding="utf-8") as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        ledger = json.load(file)
        if str(ledger.get('state','')).upper() in {'CLOSED','SEALED','EXHAUSTED'}:
            raise RuntimeError('VOICE_CALL_BUDGET_CLOSED')
        attempts = ledger["attempts"]
        count = sum(a["node"] == node for a in attempts)
        external = sum(a["node"] != "LOCAL_ASR" for a in attempts)
        if count + _held(ledger,node,exclude=_active_reservation.get()) >= ledger["limits"][node] or (node != "LOCAL_ASR" and external + _held(ledger,exclude=_active_reservation.get()) >= ledger["limits"]["TOTAL"]):
            raise RuntimeError("VOICE_CALL_BUDGET_EXHAUSTED")
        ident=_active_reservation.get()
        if ident:
            r=next(x for x in ledger['reservations'] if x['id']==ident)
            if r['state']!='ACTIVE' or r['node']!=node or r['remaining']<=0:raise RuntimeError('VOICE_RESERVATION_EXHAUSTED')
            r['remaining']-=1
        attempts.append({"node": node, "provider": provider, "requested_model": model,
                         "started_wall_ns": time.time_ns(), "attempt": count + 1})
        file.seek(0); json.dump(ledger, file, ensure_ascii=False, indent=2); file.truncate();file.flush()


def capture_model(row):
    """Opt-in self-audio diagnosis. Row is adapter-owned and contains no auth."""
    path = os.getenv("VEFIN_VOICE_MODEL_CAPTURE")
    if path:
        with open(path, "a", encoding="utf-8") as file:
            fcntl.flock(file, fcntl.LOCK_EX)
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def charge_rtc_input(path, session_id, round_number, input_sha256):
    """Count a real test-track attempt separately from external provider calls."""
    with open(path, 'r+', encoding='utf-8') as file:
        fcntl.flock(file, fcntl.LOCK_EX); ledger=json.load(file)
        if ledger['state']!='OPEN':raise RuntimeError('VOICE_CALL_BUDGET_CLOSED')
        rows=ledger.setdefault('rtc_inputs', [])
        if len(rows)>=ledger['limits']['RTC']:raise RuntimeError('RTC_INPUT_BUDGET_EXHAUSTED')
        if any(x.get('session_id')==session_id and x.get('round')==round_number for x in rows):
            raise RuntimeError('RTC_INPUT_ALREADY_ATTEMPTED')
        rows.append({'session_id':session_id,'round':round_number,'input_sha256':input_sha256,'started_at_ms':time.time_ns()//1000000})
        file.seek(0);json.dump(ledger,file,ensure_ascii=False,indent=2);file.truncate();file.flush()
