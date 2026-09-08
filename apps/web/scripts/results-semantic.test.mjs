import assert from 'node:assert/strict';
import {decodeSemanticPackage,selectorKey} from '../src/components/results/semanticModel.ts';
const selector={review_id:'REVIEW-A',check_code:'CHECK',subject_refs:['CLAIM-A']};
const fixture=()=>({schema_version:'phase6a-results-semantics/v1',run_id:'RUN-A',object_id:'OBJ-A',company_name:'Example',symbol:'EX',as_of:'2026-09-09',result_id:'RESULT-A',review_id:'REVIEW-A',review_status:'PASS',publication:'RELEASED',limitations:[],categories:['Deterministic Code'],memory_refs:[],recovery:null,html_artifact_id:'HTML-A',legacy_export:false,
 records:[{ref:'CALC-A',category:'Deterministic Code',label:'Growth',status:'PASS',input_refs:[],process:'Retained calculation',output:'0',report_claim_refs:['CLAIM-A']}],
 checks:[{selector:structuredClone(selector),status:'PASS',comparison:[{field:'value',expected:'0',actual:'0'}],execution_refs:['CALC-A']}],
 blocks:[{claim_id:'CLAIM-A',metric_id:'METRIC-A',title:'Growth',statement:'Reviewed zero',calculation_id:'CALC-A',evidence_refs:[],review_selectors:[structuredClone(selector)],execution_refs:['CALC-A']}]});
assert.equal(decodeSemanticPackage(fixture(),'RUN-A').checks[0].comparison[0].actual,'0');
assert.throws(()=>decodeSemanticPackage(fixture(),'RUN-OTHER'));
for(const mutate of [
 p=>p.checks[0].status='BLOCK',p=>p.checks[0].selector.review_id='REVIEW-OTHER',
 p=>p.records.push(p.records[0]),p=>p.checks.push(p.checks[0]),
 p=>p.blocks[0].execution_refs=['OTHER'],p=>p.records[0].input_refs=['OTHER'],
 p=>p.records[0].report_claim_refs=['OTHER'],p=>p.blocks[0].review_selectors=[],
 p=>p.memory_refs=['OTHER'],p=>p.publication='UNPROVEN',
]){const p=fixture();mutate(p);assert.throws(()=>decodeSemanticPackage(p,'RUN-A'));}
const p=fixture();p.checks.push({selector:{...selector,check_code:'AGGREGATE',subject_refs:[]},status:'PASS',comparison:[],execution_refs:[]});
assert.equal(decodeSemanticPackage(p,'RUN-A').checks.length,2);
assert.equal(selectorKey(p.checks[1].selector),'["REVIEW-A","AGGREGATE",[]]');
console.log('Results semantic decoder: 14/14 PASS');
