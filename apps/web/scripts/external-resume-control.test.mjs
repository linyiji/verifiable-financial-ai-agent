import assert from 'node:assert/strict';
import vm from 'node:vm';
import test from 'node:test';
import {rolldown} from 'rolldown';
const bundle = await rolldown({input: new URL('../src/components/ExternalResumeAction.tsx', import.meta.url).pathname,
  external: ['react', 'react/jsx-runtime']});
const code = (await bundle.generate({format: 'cjs'})).output[0].code;
await bundle.close();
function fixture({denied=false, lost=false, pending=false}={}) {
  const states=[], refs=[], calls=[];
  let si=0, ri=0, started=false, poll, changed=0;
  let truth={schema_version:'external-failure-control/v1',run_id:'RUN-A',state:'EXTERNAL_FAILURE_PAUSED',
    binding_revision:1,current_cycle_id:null,
    legal_actions:[{command:'ResumeExternalFailure', expectations:{run_id:'RUN-A',actor:'LOCAL_SINGLE_USER', expected_failure_cycle_identity:{operation_id:'old'}}}]};
  if(pending) truth={...truth,state:'EXTERNAL_RESUME_PENDING',current_cycle_id:'cycle-one',legal_actions:[]};
  const react={useState(v){const i=si++; if(!(i in states))states[i]=v; return [states[i],v=>states[i]=v];},
    useRef(v){return refs[ri++]??=( {current:v});},useEffect(cb){if(!started){started=true;cb();}}};
  const module={exports:{}};
  const jsx=(type,props)=>({type,props});
  vm.runInNewContext(code,{module,exports:module.exports,require:n=>n==='react'?react:{jsx,jsxs:jsx},
    AbortController,crypto,encodeURIComponent,setInterval:cb=>{poll=cb;return 1;},clearInterval(){},
    fetch:async(url,options)=>{calls.push({url,options});
      if(!options.method)return {ok:true,json:async()=>truth};
      truth={...truth,binding_revision:2,state:'EXTERNAL_RESUME_PENDING',current_cycle_id:'cycle-one',legal_actions:[]};
      if(lost)throw Error('lost');
      return {ok:!denied,json:async()=>({projection:truth})};}});
  const render=()=>{si=ri=0;return module.exports.ExternalResumeAction({runId:'RUN-A',backendOrigin:'http://local',onChanged:()=>changed++});};
  return {render,calls,poll:()=>poll(),changed:()=>changed};
}
const settle=()=>new Promise(r=>setImmediate(r));
function buttons(tree){if(!tree||typeof tree!=='object')return [];if(Array.isArray(tree))return tree.flatMap(buttons);return [...(tree.type==='button'?[tree]:[]),...buttons(tree.props?.children)];}
test('only explicit click authorizes; duplicate click lock; server truth disables action',async()=>{
  const f=fixture();f.render();await settle();assert.equal(f.calls.length,1);
  const b=buttons(f.render())[0];b.props.onClick();b.props.onClick();await settle();
  const posts=f.calls.filter(c=>c.options.method);assert.equal(posts.length,1);
  const body=JSON.parse(posts[0].options.body);assert.equal(body.authorize_resume,true);
  assert.equal(body.run_id,'RUN-A');assert.equal(body.idempotency_key,posts[0].options.headers['Idempotency-Key']);
  assert.equal(buttons(f.render()).length,0);assert.ok(f.changed());
});
test('lost response reconnect reads durable pending state without reposting',async()=>{
  const f=fixture({lost:true});f.render();await settle();buttons(f.render())[0].props.onClick();await settle();
  f.poll();await settle();assert.equal(buttons(f.render()).length,0);
  assert.equal(f.calls.filter(c=>c.options.method).length,1);
  const fresh=fixture({pending:true});fresh.render();await settle();assert.equal(buttons(fresh.render()).length,0);
  assert.equal(fresh.calls.filter(c=>c.options.method).length,0);
});
test('stale denial replaces stale legal actions with current state',async()=>{
  const f=fixture({denied:true});f.render();await settle();buttons(f.render())[0].props.onClick();await settle();
  assert.equal(buttons(f.render()).length,0);
});
