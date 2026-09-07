import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const renderer = await createServer({ server: { middlewareMode: true }, appType: "custom" });
let checks = 0;
const check = (condition, message) => { assert.ok(condition, message); checks++; };
try {
  const { normalizeObjectInput, objectCreationFailure } = await renderer.ssrLoadModule("/src/pages/createObjectModel.ts");
  const { HttpFrontendDataSource } = await renderer.ssrLoadModule("/src/data/HttpFrontendDataSource.ts");
  const { createPhase4Mutation } = await renderer.ssrLoadModule("/src/data/FrontendDataSource.ts");
  const { Phase4ApiError } = await renderer.ssrLoadModule("/src/api/client.ts");
  const { ResearchObjectsPage } = await renderer.ssrLoadModule("/src/pages/ResearchObjectsPage.tsx");
  const { ResearchObjectDetailPage } = await renderer.ssrLoadModule("/src/pages/ResearchObjectDetailPage.tsx");
  const valid = { symbol: " qa-test ", companyName: " Isolated Test ", exchange: " test ", currency: " usd ", sector: " " };
  const input = normalizeObjectInput(valid);
  check(JSON.stringify(input) === JSON.stringify({ symbol: "QA-TEST", companyName: "Isolated Test", exchange: "TEST", currency: "USD", sector: null }), "normalized minimum identity is explicit and sector remains absent");
  for (const patch of [{symbol:""},{symbol:"../NVDA"},{symbol:"A/B"},{companyName:" "},{companyName:"x".repeat(201)},{exchange:""},{currency:"US"},{currency:"123"},{sector:"x".repeat(121)}]) {
    assert.throws(() => normalizeObjectInput({...valid,...patch}));checks++;
  }
  const wire = {
    object: {object_id:"OBJ-QA-TEST",symbol:input.symbol,company_name:input.companyName,exchange:input.exchange,currency:input.currency,sector:null,object_type:"public_company",identity_version:1},
    run_count:0,latest_released_run_id:null,last_activity:null,
    released_result_availability:{status:"NOT_RELEASED",reason_code:"NO_RELEASED_RUN",retryable:false},
    created_at:"2026-09-07T00:00:00Z",updated_at:"2026-09-07T00:00:00Z"
  };
  const requests=[];
  const reply=(body,status=201)=>new Response(JSON.stringify(body),{status,headers:{"Content-Type":"application/json; charset=utf-8","X-Phase4-Contract-Version":"phase4-core/v1"}});
  let response=wire;
  const source=new HttpFrontendDataSource({baseUrl:"http://test.invalid",fetch:async(url,init)=>{requests.push({url:String(url),init});return reply(response)}});
  const mutation=createPhase4Mutation(input,"m7-r3-fixed-retry-key");
  const created=await source.createResearchObject(mutation);
  check(created.object.objectId==="OBJ-QA-TEST"&&created.runCount===0&&created.latestReleasedRunId===null&&created.lastActivity===null,"creation decodes returned Object with no borrowed history");
  await source.createResearchObject(mutation);
  check(requests.length===2&&requests.every(x=>x.url.endsWith('/api/objects')&&x.init.method==="POST"),"creation capability uses Object POST only, not Run prepare or confirm");
  check(requests.every(x=>new Headers(x.init.headers).get('Idempotency-Key')==="m7-r3-fixed-retry-key")&&requests[0].init.body===requests[1].init.body,"unchanged mutation retries identical key and body");
  check(Object.isFrozen(mutation.input),"retry identity snapshot is immutable");
  const list=renderToStaticMarkup(createElement(ResearchObjectsPage,{objects:[created],onCreate(){},onOpen(){}}));
  const detail=renderToStaticMarkup(createElement(ResearchObjectDetailPage,{detail:created,onBeginResearch(){},onOpenRun(){}}));
  check(list.includes("创建研究对象")&&list.includes("Isolated Test"),"actual Objects page advertises creation and renders returned identity");
  check([list,detail].every(x=>x.includes("尚未发布")&&x.includes("尚无 Run 活动")&&!x.includes("NVIDIA")),"new Object views have neutral absence, never NVIDIA results");
  response={...wire,object:{...wire.object,object_id:"OBJ-NVDA",symbol:"NVDA",company_name:"NVIDIA Corporation"}};
  await assert.rejects(()=>source.createResearchObject(createPhase4Mutation(input)));checks++;
  const app=await readFile(new URL("../src/Phase4Application.tsx",import.meta.url),"utf8");
  check(app.includes("onCreate={() => setCreatingObject(true)}")&&app.includes("source.createResearchObject(mutation)")&&app.includes("encodeURIComponent(detail.object.objectId)"),"primary CTA opens creation UI and returns via server Object identity");
  check(objectCreationFailure(new Error("private raw provider payload")).uncertain&&!objectCreationFailure(new Error("private raw provider payload")).message.includes("private"),"unknown/lost response is safe uncertainty, not raw error exposure");
  const conflict=new Phase4ApiError(409,{error:{code:"CONFLICT"}},{method:"POST",path:"/api/objects"});
  check(!objectCreationFailure(conflict).uncertain&&objectCreationFailure(conflict).message.includes("股票代码已存在"),"duplicate identity has actionable safe conflict copy");
  console.log(`M7-R3 creation checks: ${checks}/${checks} PASS`);
} finally {await renderer.close()}
