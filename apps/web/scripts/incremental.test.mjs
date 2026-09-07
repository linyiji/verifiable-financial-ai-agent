import assert from 'node:assert/strict';
import {createServer} from 'vite';
const server=await createServer({root:new URL('../',import.meta.url).pathname,server:{middlewareMode:true},appType:'custom'});
let count=0;const check=x=>{assert(x);count++;};
try {
 const {decodeIncrementalContext:decode}=await server.ssrLoadModule('/src/types/incremental.ts');
 const context={research_object_id:'OBJ-A',base_run_id:'RUN-A',base_research_view_version:'RVV-A',base_version_number:1,base_as_of:'2026-09-06',target_as_of:'2026-09-07',decisions:[
  ['REUSE','RVV-A','VIEW_CONTEXT'],['REFRESH','MI-M','VERIFIED_METRIC'],['REVALIDATE','MI-C','VERIFIED_CLAIM'],['PREVENT','MI-I','RESOLVED_ISSUE']
 ].map(([decision,source_identity,category])=>({decision,source_identity,category,source_run_id:'RUN-A',statement:'历史材料',reason:'本次独立研究，不继承历史批准',authority:'phase5b-exact-memory-policy/v1'}))};
 const value=decode(context,'OBJ-A');check(Object.isFrozen(value.decisions));check(value.decisions.length===4);
 for(const mutate of [x=>x.research_object_id='OBJ-B',x=>x.base_run_id='RUN-B',x=>x.base_research_view_version='RVV-B',x=>x.decisions[1].decision='REUSE',x=>x.decisions[2].decision='REUSE',x=>x.decisions[3].decision='REUSE',x=>x.decisions[0].source_identity='foreign',x=>x.decisions.push(x.decisions[0]),x=>x.decisions[0].chain_of_thought='private',x=>x.decisions[1].reason='/Users/private/secret',x=>x.target_as_of='2025-01-01',x=>x.base_version_number=0]) {
  const v=structuredClone(context);mutate(v);assert.throws(()=>decode(v,'OBJ-A'));count++;
 }
 const unknown=structuredClone(context);unknown.decisions[1].decision='UNKNOWN';check(decode(unknown,'OBJ-A').decisions[1].decision==='UNKNOWN');
 const {IncrementalContext}=await server.ssrLoadModule('/src/components/IncrementalContext.tsx');
 const {renderToStaticMarkup}=await import('react-dom/server');const {createElement}=await import('react');
 const html=renderToStaticMarkup(createElement(IncrementalContext,{context:value}));
 for(const text of ['基于上次研究','继续沿用','需要更新','重新验证','避免重复问题','全新独立研究','RUN-A','RVV-A']) check(html.includes(text));
} finally {await server.close();}
console.log(`Incremental frontend PASS (${count} checks)`);
