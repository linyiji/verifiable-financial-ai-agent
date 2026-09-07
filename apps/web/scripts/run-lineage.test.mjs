import assert from "node:assert/strict";
import test from "node:test";
import {rolldown} from "rolldown";
import {projectionWire} from "./product-contract-fixtures.mjs";
const bundle=await rolldown({input:new URL("../src/types/domain.ts",import.meta.url).pathname});
const compiled=(await bundle.generate({format:"esm"})).output[0].code;
await bundle.close();
const {decodeRunProjection,decodeResearchRunDetail}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);

function decodeBoth(fields) {
  const wire=projectionWire(); Object.assign(wire.run,fields);
  const detail={...wire.run,terminal:false,projection_revision:1,projection_sequence:2};
  return [decodeRunProjection(wire,"RUN-A").run,decodeResearchRunDetail(detail,"RUN-A","OBJ-A")];
}
test("legacy omitted lineage stays omitted",()=>{
  for(const run of decodeBoth({})) {
    assert.equal(Object.hasOwn(run,"baseRunId"),false);
    assert.equal(Object.hasOwn(run,"reexecutionOfRunId"),false);
  }
});
test("explicit null lineage remains null",()=>{
  for(const run of decodeBoth({base_run_id:null,base_research_view_version:null,reexecution_of_run_id:null})) {
    assert.equal(run.baseRunId,null);assert.equal(run.reexecutionOfRunId,null);
  }
});
test("incremental first attempt keeps knowledge base without predecessor",()=>{
  for(const run of decodeBoth({base_run_id:"RUN-R1",base_research_view_version:"RVV-V1"})) {
    assert.equal(run.baseRunId,"RUN-R1");assert.equal(run.baseResearchViewVersion,"RVV-V1");
    assert.equal(run.reexecutionOfRunId,undefined);
  }
});
test("future reexecution keeps distinct knowledge and execution lineage",()=>{
  for(const run of decodeBoth({base_run_id:"RUN-R1",base_research_view_version:"RVV-V1",reexecution_of_run_id:"RUN-R2"})) {
    assert.equal(run.baseRunId,"RUN-R1");assert.equal(run.reexecutionOfRunId,"RUN-R2");
  }
});
for(const fields of [
  {definitely_unknown_run_field:true}, {base_run_id:"RUN-R1"},
  {base_research_view_version:"RVV-V1"}, {reexecution_of_run_id:"RUN-R2"},
  {base_run_id:"RUN-A",base_research_view_version:"RVV-V1"},
  ...["RUN-A","RUN-R1",42,"",{},"x".repeat(1025)].map(parent=>({base_run_id:"RUN-R1",base_research_view_version:"RVV-V1",reexecution_of_run_id:parent})),
  {base_run_id:42,base_research_view_version:"RVV-V1"},
  {base_run_id:"RUN-R1",base_research_view_version:[]},
]) {
  test(`reject unsupported/malformed lineage ${JSON.stringify(fields)}`,()=>{
    const wire=projectionWire();Object.assign(wire.run,fields);
    assert.throws(()=>decodeRunProjection(wire,"RUN-A"));
    assert.throws(()=>decodeResearchRunDetail({...wire.run,terminal:false,projection_revision:1,projection_sequence:2},"RUN-A"));
  });
}
