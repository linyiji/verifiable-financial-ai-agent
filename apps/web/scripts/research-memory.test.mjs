import assert from 'node:assert/strict';
import {createServer} from 'vite';
const s=await createServer({root:new URL('../',import.meta.url).pathname,server:{middlewareMode:true},appType:'custom'});
let count=0;const check=(x)=>{assert(x);count++;};
try{
 const {decodeResearchMemory:decode}=await s.ssrLoadModule('/src/types/researchMemory.ts');
 const identity={research_object_id:'OBJ-A',source_run_id:'RUN-A',source_released_result_id:'RESULT-A',source_report_id:'REPORT-A',source_canonical_record_id:'CER-A',created_at:'2026-09-07T00:00:00Z'};
 const item={memory_item_id:'MI-A',category:'VERIFIED_CLAIM',source_run_id:'RUN-A',reference_id:'CLAIM-A',title:'Revenue',statement:'Revenue increased',display_value:null,display_unit:null,calculation_id:'CALC-A',evidence_ids:['EVD-A'],review_id:'REVIEW-A',report_id:'REPORT-A',report_anchor:'metric-revenue-growth',task_id:null,agent_output_id:null};
 const wire={schema_version:'phase5a-memory/v1',research_object_id:'OBJ-A',latest_released_run_id:'RUN-A',latest_research_object_version:1,latest_research_view_version:1,
 object_version:{...identity,schema_version:'phase5a-object-version/v1',object_version:1,object_version_id:'ROV-A'},
 current_view:{...identity,schema_version:'phase5a-view-version/v1',research_object_version:1,research_view_version:1,research_view_version_id:'RVV-A',as_of:'2026-09-06',summary:'Revenue increased',items:[item],unavailable_categories:['PEER_CONTEXT','PATH_CONTEXT','REUSABLE_CONTEXT']},historical_released_runs:[]};
 const memory=decode(wire,'OBJ-A');check(Object.isFrozen(memory.current_view.items));check(memory.latest_released_run_id==='RUN-A');
 const mutations=[x=>x.research_object_id='OBJ-B',x=>x.current_view.source_run_id='RUN-B',x=>x.current_view.research_object_version=2,x=>x.latest_research_view_version=2,x=>x.current_view=null,x=>x.current_view.items[0].source_run_id='RUN-B',x=>x.current_view.items[0].report_id='REPORT-B',x=>x.current_view.items.push(x.current_view.items[0]),x=>x.current_view.items[0].chain_of_thought='private',x=>x.current_view.items[0].statement='/Users/private/secret',x=>x.current_view.source_released_result_id='RESULT-B',x=>x.object_version.object_version=0,x=>x.current_view.unavailable_categories=['invented'],x=>x.historical_released_runs=[{research_object_id:'OBJ-B',source_run_id:'RUN-B',status:'RELEASED',as_of:'2026-09-06',source_released_result_id:'RESULT-B',research_view_version:null,availability:'AVAILABLE'}]];
 for(const mutate of mutations){const x=structuredClone(wire);mutate(x);assert.throws(()=>decode(x,'OBJ-A'));count++;}
 const empty={...wire,latest_released_run_id:null,latest_research_object_version:null,latest_research_view_version:null,object_version:null,current_view:null};check(decode(empty,'OBJ-A').current_view===null);
 const {ResearchMemory}=await s.ssrLoadModule('/src/components/ResearchMemory.tsx');
 const {renderToStaticMarkup}=await import('react-dom/server');const {createElement}=await import('react');
 const html=renderToStaticMarkup(createElement(ResearchMemory,{memory,unavailable:false,onOpenSource(){}}));
 check(html.includes('Current Research View')&&html.includes('Research Memory'));check(html.includes('RUN-A')&&html.includes('ROV-A')&&html.includes('RVV-A'));check(html.includes('NOT_OBSERVED')&&html.includes('memory-source-link'));
}finally{await s.close();}
console.log(`Research Memory frontend PASS (${count} checks)`);
