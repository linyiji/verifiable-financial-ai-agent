import json
import pytest
from src.adapters.voice_call_budget import reserve,release,charge,require_capacity

def test_window_allocation_no_session_reset(tmp_path,monkeypatch):
 p=tmp_path/'ledger.json';p.write_text(json.dumps({'state':'OPEN','limits':{'TTS':80,'LLM':24,'ASR':16,'TOTAL':120},'attempts':[]}));monkeypatch.setenv('VEFIN_VOICE_CALL_LEDGER',str(p))
 for n in [3,3,5]:
  require_capacity('TTS',n);r=reserve('TTS',n)
  for _ in range(n):charge('TTS','FAKE_NO_NETWORK','fixture')
  release(r)
 assert len(json.loads(p.read_text())['attempts'])==11
 r=reserve('TTS',5);charge('TTS','FAKE_NO_NETWORK','fixture');release(r)
 d=json.loads(p.read_text());assert len(d['attempts'])==12 and d['reservations'][-1]['released_unused']==4
 # New session uses same ledger/environment, no initialization/reset path.
 require_capacity('TTS',68)
 with pytest.raises(RuntimeError):reserve('TTS',69)
 assert len(json.loads(p.read_text())['attempts'])==12
 r=reserve('TTS',68)
 with pytest.raises(RuntimeError):reserve('TTS',1)
 release(r);assert len(json.loads(p.read_text())['attempts'])==12
