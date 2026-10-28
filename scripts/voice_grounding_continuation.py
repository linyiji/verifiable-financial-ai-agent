"""Bounded current-node validation and scoped existing-service reload only."""
import argparse,asyncio,hashlib,json,os,subprocess,time
from pathlib import Path
import httpx,psutil
R=Path(__file__).resolve().parents[1];B=R/'output/voice-cantonese-e2e-20261024';O=B/'grounding-continuation-20261026';P=Path.home()/'.config/vefin/grounding-continuation-20261026'
def dump(name,obj):
 p=O/name;p.write_text(json.dumps(obj,ensure_ascii=False,indent=2));p.chmod(0o600)
class TextOnlyMedia:
 """No media transport in text tests; business journal/control are real."""
 async def room_names(self):return set()
 async def retire_previous_agents(self,*args):pass
 async def delete_room(self,*args):pass
 def token(self,*args):return 'TEXT_ONLY_NO_RTC'

def independent_text_may_continue(records, reviews):
 """A single no-response transport timeout does not invalidate another isolated case.
 Content/grounding failures, refusal, auth errors and repeated timeouts stop.
 This does not satisfy the separate all-cases-PASS gate for RTC.
 """
 if len(records)!=len(reviews):return False
 incomplete=0
 for row,review in zip(records,reviews):
  if review['decision']=='PASS':continue
  if (review['decision']=='INCOMPLETE_TRANSPORT' and row.get('error_type')=='TimeoutError'
      and not row.get('raw_reply') and row.get('observations')
      and row['observations'][-1].get('http_status') is None
      and row['observations'][-1].get('outcome')=='TIMEOUT'):
   incomplete+=1
  else:return False
 return incomplete<=1

async def text_validation(case_index=None):
 from types import SimpleNamespace
 from sqlalchemy import select
 from src.adapters.voice_candidate_profile import candidate_node
 from src.application.voice_dialogue import VoiceDialogue
 from src.application.voice_sessions import VoiceSessions
 from src.infrastructure.database.voice_tables import VoiceEventRow
 from contracts.api.voice_session import WorkerDialogue
 if (O/'text-results.json').exists() and case_index is None:raise RuntimeError('NO_REPEAT_ALLOWED')
 os.environ['VEFIN_VOICE_CALL_LEDGER']=str(O/'call-ledger.json')
 profile=json.loads((O/'profile.json').read_text());cases=json.loads((O/'text-freeze.json').read_text());records=[]
 if case_index is not None:
  records=json.loads((O/'text-results.json').read_text()) if (O/'text-results.json').exists() else []
  if len(records)!=case_index or not 0<=case_index<len(cases):raise RuntimeError('NO_REPEAT_OR_SKIPPED_CASE_ALLOWED')
  if case_index:
   review=json.loads((O/'text-review.json').read_text())['cases']
   if not independent_text_may_continue(records,review):raise RuntimeError('PREVIOUS_SEMANTIC_GATE_NOT_PASSED')
  cases=[cases[case_index]]
 async with httpx.AsyncClient(trust_env=False,follow_redirects=False,transport=httpx.AsyncHTTPTransport(retries=0),timeout=httpx.Timeout(5,connect=3)) as client:
  for case in cases:
   observations=[];raw=[];start=time.monotonic_ns();row={'case':case['id'],'input':case['input'],'expected':case['expected'],'started_wall_ns':time.time_ns(),'business_path':'VoiceSessions -> VoiceDialogue.turn -> kind guard -> grounding -> meaning policy -> renderer -> journal'}
   dbfile=O/('text-journal-'+case['id']+'.sqlite')
   if dbfile.exists():raise RuntimeError('NO_REUSE_OF_TEST_JOURNAL')
   control=VoiceSessions(SimpleNamespace(state=SimpleNamespace()),'sqlite+aiosqlite:///'+str(dbfile),TextOnlyMedia())
   await control.start(background=False);sid=None
   try:
    session=await control.create('isolated-text-user',case['id'],'conversation','yue-HK');sid=session.id
    claim=await control.claim(sid)
    model=candidate_node(profile,'llm',llm_id='deepseek',client=client,observer=observations.append)
    dialogue=VoiceDialogue(control,model,raw_observer=raw.append,structured_constraints=True,instruction_revision=profile['instruction_revision'],history_seed=case.get('history',[]))
    payload=WorkerDialogue(lease_id=claim['lease_id'],turn_id='text:1',text=case['input'],generate=True,metadata={'turn_id':'text:1','connection_id':'text','track_sid':'NO_RTC','turn':1,'input_epoch':1})
    result=await dialogue.turn(sid,payload)
    row.update(business_result=result,rendered=result['text'],effective_kind=result['reply_kind'],status='BUSINESS_COMPLETE_REVIEW_REQUIRED')
   except Exception as e:row.update(status='FAILED_STOP_NO_RETRY',error_type=type(e).__name__,reason=str(e))
   finally:
    if sid:
     await control.end(sid,'isolated-text-user',reason='bounded_text_finished')
     async with control.transaction() as db:
      events=(await db.scalars(select(VoiceEventRow).where(VoiceEventRow.session_id==sid).order_by(VoiceEventRow.cursor))).all()
      row['journal']=[e.payload for e in events]
    await control.close()
   row.update(elapsed_ms=(time.monotonic_ns()-start)/1e6,observations=observations,raw_observations=raw,session_id=sid,session_ended=True)
   if raw:
    row['raw_reply']=raw[-1]['raw_reply'];row['raw_kind']=row['raw_reply']['kind'] if row['raw_reply'] else None
    row['generator']=raw[-1].get('generator','MODEL');row['application_reply']=raw[-1].get('application_reply')
   records.append(row);dump('text-results.json',records)
   if row['status'].startswith('FAILED'):break
 print(json.dumps([{k:r.get(k) for k in ['case','status','elapsed_ms','rendered','reason','raw_kind','effective_kind']} for r in records],ensure_ascii=False))
def sequential_text_may_continue(records, reviews):
 """Only accepted journal responses can be continued; B is diagnostic, not PASS."""
 if len(records)!=len(reviews):return False
 for row,review in zip(records,reviews):
  if row.get('status')!='BUSINESS_COMPLETE_REVIEW_REQUIRED':return False
  if review.get('decision') not in {'PASS','WARN','STRATEGY_FAIL_DIAGNOSTIC'}:return False
  if review.get('decision')=='STRATEGY_FAIL_DIAGNOSTIC' and review.get('severity')!='B':return False
 return True


async def renew_text_session_lease(control, state):
 """Use normal product poll/claim before a new turn; never revive ended sessions.
 A lease is a Worker execution fence, not the identity of the conversation.
 """
 from src.application.errors import ApplicationError
 try:
  await control.poll(state['session_id'],state['lease_id'])
 except ApplicationError as error:
  if error.code != 'VOICE_LEASE_LOST':raise
  claim=await control.claim(state['session_id'])
  state={**state,'lease_id':claim['lease_id']}
 return state


async def finish_text_turn(control, state, *, end):
 """Only the current lease can release or end. Lost ownership is not cleanup authority."""
 from src.application.errors import ApplicationError
 try:
  if end:
   await control.end(state['session_id'],'isolated-consultation-user',reason='bounded_consultation_finished',lease_id=state['lease_id'])
   return 'ENDED'
  await control.release(state['session_id'],state['lease_id'])
  return 'PAUSED_RELEASED'
 except ApplicationError as error:
  if error.code in {'VOICE_LEASE_LOST','VOICE_SESSION_ENDED','VOICE_SESSION_EXPIRED'}:
   return 'NOT_OWNER_NO_MUTATION'
  raise


async def same_session_text(case_index, model_factory=None):
 """One fresh turn per invocation, same isolated product journal and lease.
 Human content review gates the next invocation; failure ends the session.
 """
 from types import SimpleNamespace
 from sqlalchemy import select
 from src.adapters.voice_candidate_profile import candidate_node
 from src.application.voice_dialogue import VoiceDialogue
 from src.application.voice_sessions import VoiceSessions
 from src.infrastructure.database.voice_tables import VoiceEventRow
 from contracts.api.voice_session import WorkerDialogue
 cases=json.loads((O/'text-freeze.json').read_text())
 records=json.loads((O/'text-results.json').read_text()) if (O/'text-results.json').exists() else []
 if case_index != len(records) or not 0<=case_index<len(cases):raise RuntimeError('NO_REPEAT_OR_SKIP')
 if case_index and not sequential_text_may_continue(records,json.loads((O/'text-review.json').read_text())['cases']):raise RuntimeError('PREVIOUS_TURN_NOT_ACCEPTED')
 os.environ['VEFIN_VOICE_CALL_LEDGER']=str(O/'call-ledger.json')
 profile=json.loads((O/'profile.json').read_text());case=cases[case_index]
 dbfile=O/'same-session-text.sqlite';statefile=O/'text-session.json'
 if case_index==0 and (dbfile.exists() or statefile.exists()):raise RuntimeError('EXISTING_SESSION_NOT_RESTARTED')
 control=VoiceSessions(SimpleNamespace(state=SimpleNamespace()),'sqlite+aiosqlite:///'+str(dbfile),TextOnlyMedia())
 await control.start(background=False);observations=[];raw=[];sid=None;start=time.monotonic_ns()
 row={'case':case['id'],'input':case['input'],'expected':case['expected'],'business_path':'VoiceSessions -> VoiceDialogue.turn -> kind guard -> grounding -> consultation -> renderer -> journal'}
 try:
  if case_index==0:
   session=await control.create('isolated-consultation-user','same-session-consultation','conversation','yue-HK');sid=session.id
   claim=await control.claim(sid);state={'session_id':sid,'lease_id':claim['lease_id']};dump('text-session.json',state)
  else:
   state=json.loads(statefile.read_text());sid=state['session_id']
   state=await renew_text_session_lease(control,state);dump('text-session.json',state)
  if profile.get('require_llm_tls_preflight') and model_factory is None:
   from src.adapters.voice_candidate_http import create_client, require_receipt
   require_receipt(profile,json.loads((O/'tls-preflight.json').read_text()))
   text_client=create_client(profile)
  else:
   text_client=httpx.AsyncClient(trust_env=False,follow_redirects=False,transport=httpx.AsyncHTTPTransport(retries=0),timeout=httpx.Timeout(5,connect=3))
  async with text_client as client:
   model=(model_factory() if model_factory else candidate_node(profile,'llm',llm_id='deepseek',client=client,observer=observations.append))
   from src.adapters.voice_knowledge import configured_knowledge
   dialogue=VoiceDialogue(control,model,skill_config=profile.get("communication_skill"),knowledge_port=configured_knowledge(profile),raw_observer=raw.append,structured_constraints=True,instruction_revision=profile['instruction_revision'],communication_revision=profile.get('communication_revision'),application_concepts=profile.get('application_concepts',False))
   n=case_index+1
   payload=WorkerDialogue(lease_id=state['lease_id'],turn_id=f'text:{n}',text=case['input'],generate=True,metadata={'turn_id':f'text:{n}','connection_id':'same-text-session','track_sid':'NO_RTC','turn':n,'input_epoch':n})
   result=await dialogue.turn(sid,payload)
   row.update(business_result=result,rendered=result['text'],effective_kind=result['reply_kind'],status='BUSINESS_COMPLETE_REVIEW_REQUIRED')
 except Exception as e:row.update(status='FAILED_STOP_NO_RETRY',error_type=type(e).__name__,reason=str(e))
 finally:
  ended=row.get('status','').startswith('FAILED') or case_index==len(cases)-1
  if sid:
   row['lifecycle_exit']=await finish_text_turn(control,state,end=ended)
   ended=row['lifecycle_exit']=='ENDED'
   async with control.transaction() as db:
    events=(await db.scalars(select(VoiceEventRow).where(VoiceEventRow.session_id==sid).order_by(VoiceEventRow.cursor))).all()
    row['journal']=[e.payload for e in events]
  await control.close()
 row.update(session_id=sid,session_ended=ended,elapsed_ms=(time.monotonic_ns()-start)/1e6,observations=observations,raw_observations=raw)
 model_raw=[x for x in raw if not x.get('event')]
 if model_raw:
  row['raw_reply']=model_raw[-1]['raw_reply'];row['raw_kind']=row['raw_reply']['kind'] if row['raw_reply'] else None
  row['generator']=model_raw[-1].get('generator','MODEL');row['application_reply']=model_raw[-1].get('application_reply')
 records.append(row);dump('text-results.json',records)
 print(json.dumps({k:row.get(k) for k in ['case','status','rendered','reason','elapsed_ms','session_id']},ensure_ascii=False))

def reload_services():
 envs={role:json.loads((P/(role+'-env.json')).read_text()) for role in ['api','worker']}
 with httpx.Client(trust_env=False,timeout=3) as c:
  r=c.get('http://127.0.0.1:18364/internal/voice/sessions',headers={'Authorization':'Bearer '+envs['worker']['VEFIN_VOICE_WORKER_SECRET']});r.raise_for_status();assert r.json()==[]
 before=json.loads((O/'process-before.json').read_text())
 for row in before:
  p=psutil.Process(row['pid']);assert abs(p.create_time()-row['started'])<.01;p.terminate();p.wait(timeout=15)
 actual={}
 for role,cmd in [('api',[str(R/'.venv/bin/uvicorn'),'apps.api.main:app','--host','127.0.0.1','--port','18364']),('worker',[str(R/'.venv/bin/python'),'-m','apps.voice_worker.main'])]:
  e=envs[role];e.update(VEFIN_VOICE_CALL_LEDGER=str(O/'call-ledger.json'),VEFIN_VOICE_MODEL_CAPTURE=str(O/'model-capture.jsonl'),VEFIN_VOICE_TEST_TRACE_DIR=str(B),HF_HUB_OFFLINE='1')
  if role=='api':e['VEFIN_VOICE_TEST_ADMISSION_FILE']=str(O/'test-admission.json')
  p=subprocess.Popen(cmd,cwd=R,env=e,stdout=(O/(role+'.log')).open('ab'),stderr=subprocess.STDOUT,start_new_session=True);actual[role]=p.pid
 p=R/'deploy/voice/runtime/product-pids.json';data=json.loads(p.read_text());data['api']=actual['api'];p.write_text(json.dumps(data))
 dump('activation.json',{'scope':'SELF_TEST_ONLY_NOT_PRODUCT_DEFAULT',**actual,'time':time.time_ns(),'profile_sha256':hashlib.sha256((O/'profile.json').read_bytes()).hexdigest()});dump('test-admission.json',{'enabled':False});print(json.dumps(actual))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['text','text-sequence','reload']);p.add_argument('--evidence-dir',default=O.name);p.add_argument('--case-index',type=int);args=p.parse_args()
 if not args.evidence_dir or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.evidence_dir):raise ValueError('INVALID_EVIDENCE_SCOPE')
 O=B/args.evidence_dir;P=Path.home()/'.config/vefin'/args.evidence_dir
 if args.mode=='text-sequence':asyncio.run(same_session_text(args.case_index))
 elif args.mode=='text':asyncio.run(text_validation(args.case_index))
 else:reload_services()
