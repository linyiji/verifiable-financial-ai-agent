"""Finite saved user inputs through the original VoiceDialogue. No route selection or reviewer gate."""
import argparse,asyncio,json,os,time
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import select
from scripts.voice_grounding_continuation import TextOnlyMedia,renew_text_session_lease
from src.application.voice_sessions import VoiceSessions
from src.application.voice_dialogue import VoiceDialogue
from src.adapters.voice_candidate_profile import candidate_node
from src.adapters.voice_candidate_http import create_client,require_receipt
from src.adapters.voice_knowledge import configured_knowledge
from src.infrastructure.database.voice_tables import VoiceEventRow
from contracts.api.voice_session import WorkerDialogue

async def main(P,scenario):
 profile=json.loads((P/'profile.json').read_text());require_receipt(profile,json.loads((P/'tls-preflight.json').read_text()))
 spec=next(x for x in json.loads((P/'text-plan.json').read_text()) if x['id']==scenario)
 out=P/f'text-{scenario}.json';dbpath=P/f'text-{scenario}.sqlite'
 if out.exists() or dbpath.exists():raise RuntimeError('NO_REPLAY')
 os.environ['VEFIN_VOICE_CALL_LEDGER']=str(P/'call-ledger.json');os.environ['VEFIN_VOICE_MODEL_CAPTURE']=str(P/'model-capture.jsonl')
 control=VoiceSessions(SimpleNamespace(state=SimpleNamespace()),'sqlite+aiosqlite:///'+str(dbpath),TextOnlyMedia());await control.start(background=False)
 result={'scenario':spec,'started_at_ns':time.time_ns(),'turns':[]};sid=None
 try:
  session=await control.create('isolated-consultation-user',scenario,'conversation','yue-HK');sid=session.id;claim=await control.claim(sid);state={'session_id':sid,'lease_id':claim['lease_id']}
  async with create_client(profile) as client:
   for n,text in enumerate(spec['inputs'],1):
    state=await renew_text_session_lease(control,state);raw=[];observations=[]
    model=candidate_node(profile,'llm',llm_id='deepseek',client=client,observer=observations.append)
    dialogue=VoiceDialogue(control,model,raw_observer=raw.append,structured_constraints=True,
      instruction_revision=profile['instruction_revision'],communication_revision=profile['communication_revision'],
      knowledge_port=configured_knowledge(profile),skill_config=profile['communication_skill'])
    row={'turn':n,'input':text,'started_ns':time.time_ns(),'started_monotonic':time.monotonic()};result['turns'].append(row)
    try:
     payload=WorkerDialogue(lease_id=state['lease_id'],turn_id=f'text:{n}',text=text,generate=True,metadata=dict(turn_id=f'text:{n}',connection_id='same-text-session',track_sid='NO_RTC',turn=n,input_epoch=n))
     row['result']=await dialogue.turn(sid,payload);row['status']='ACCEPTED'
    except Exception as exc:
     row.update(status='FAILED',error_type=type(exc).__name__,error=str(exc));raise
    finally:
     row.update(observations=observations,raw_observations=raw,ended_ns=time.time_ns(),returned_monotonic=time.monotonic());out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    if spec.get('review_between_turns') and n<len(spec['inputs']):
     gate=P/f'review-{scenario}-turn-{n}.json';until=time.monotonic()+300
     while not gate.exists():
      if time.monotonic()>until:raise RuntimeError('CONTENT_REVIEW_NOT_RECEIVED')
      await asyncio.sleep(1)
     if json.loads(gate.read_text()).get('decision')!='CONTINUE_FIXED_INPUT':raise RuntimeError('CONTENT_REVIEW_STOP')
    if row['result']['skill_state']['status'] in ['COMPLETED','CANCELLED','PARTIAL']:break
  result['status']='COMPLETED_EXECUTION_REQUIRES_CONTENT_REVIEW'
 except Exception as exc:result.update(status='FAILED',error_type=type(exc).__name__,error=str(exc))
 finally:
  if sid:
   await control.end(sid,'isolated-consultation-user',reason='bounded_skill_finished')
   async with control.transaction() as db:
    rows=(await db.scalars(select(VoiceEventRow).where(VoiceEventRow.session_id==sid).order_by(VoiceEventRow.cursor))).all();result['journal']=[e.payload for e in rows]
  await control.close();result.update(session_id=sid,session_ended=True,finished_ns=time.time_ns());out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps({'scenario':scenario,'status':result['status'],'turns':[{'input':t['input'],'output':t.get('result',{}).get('text'),'state':t.get('result',{}).get('skill_state'),'error':t.get('error')} for t in result['turns']]},ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('scenario');a=p.parse_args();asyncio.run(main(Path(a.directory).resolve(),a.scenario))
