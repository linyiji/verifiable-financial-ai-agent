import assert from "node:assert/strict";
import {createServer} from "vite";
import {createElement} from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {readFileSync} from "node:fs";
const server=await createServer({server:{middlewareMode:true,hmr:false},appType:"custom"});
let checks=0;
const check=(ok)=>{assert.ok(ok);checks++;};
try {
 const {ResearchObjectDetailPage:Detail}=await server.ssrLoadModule("/src/pages/ResearchObjectDetailPage.tsx");
 const {ResearchMemory}=await server.ssrLoadModule("/src/components/ResearchMemory.tsx");
 const {decodeResearchObjectDetail}=await server.ssrLoadModule("/src/types/domain.ts");
 const detail=decodeResearchObjectDetail({object:{object_id:"OBJ-TEST",symbol:"TEST",company_name:"Test Company",object_type:"public_company",exchange:"TEST",sector:null,currency:"USD",identity_version:1},latest_released_run_id:null,released_result_availability:{status:"NOT_RELEASED",reason_code:"NO_RELEASED_RUN",retryable:false},run_count:0,last_activity:null,created_at:"2026-01-01T00:00:00Z",updated_at:"2026-01-01T00:00:00Z"},"OBJ-TEST");
 const props={detail,onBeginResearch(){},onOpenRun(){},onOpenMemorySource(){}};
 for(const tab of ["overview","current","memories","compare","history"]){
  const html=renderToStaticMarkup(createElement(Detail,{...props,initialTab:tab}));
  check((html.match(/role="tab"/g)||[]).length===5);
  check(html.includes('id="object-panel-'+tab+'"'));
  check((html.match(/<h1/g)||[]).length===1);
  if(tab==="overview")check(!html.includes('data-testid="research-memory"')&&!html.includes('data-testid="base-vs-current"'));
 }
 const item={memory_item_id:"ITEM-TEST",category:"VERIFIED_METRIC",source_run_id:"RUN-TEST",title:"Test metric",statement:"Governed statement",reference_id:"METRIC-TEST",report_anchor:"metric-test"};
 const view={source_run_id:"RUN-TEST",research_view_version:2,research_view_version_id:"VIEW-TEST",research_object_version:2,as_of:"2026-01-01",summary:"Governed summary",items:[item]};
 const memory={research_object_id:"OBJ-TEST",latest_released_run_id:"RUN-TEST",current_view:view,object_version:null,historical_released_runs:[]};
 const render=pane=>renderToStaticMarkup(createElement(ResearchMemory,{memory,unavailable:false,onOpenSource(){},pane}));
 check(render("current").includes('data-testid="current-research-view"')&&!render("current").includes('data-testid="research-memory"'));
 check(render("memories").includes('data-testid="research-memory"')&&!render("memories").includes('data-testid="current-research-view"'));
 check(render("compare").includes("尚无足够"));
 const foreign=renderToStaticMarkup(createElement(Detail,{...props,initialTab:"current",memory:{...memory,research_object_id:"OBJ-FOREIGN"}}));
 check(!foreign.includes("Governed statement"));
 const css=readFileSync(new URL("../src/styles/workspace-pages.css",import.meta.url),"utf8");
 check(css.includes("grid-template-columns: repeat(2, minmax(0, 1fr))"));
 const shell=readFileSync(new URL("../src/components/shell/AppShell.tsx",import.meta.url),"utf8");
 check(shell.includes('src="/verifiable-financial-agent-logo.png"')&&!shell.includes('className="brand-mark"'));
 const page=readFileSync(new URL("../src/pages/ResearchObjectDetailPage.tsx",import.meta.url),"utf8");
 check(!page.includes("materializeResearchMemory")&&!page.includes("prepareResearchRun"));
 check(page.includes('window.addEventListener("popstate", sync)')&&page.includes('url.searchParams.set("tab", next)'));
 console.log("Object workspace V2 PASS ("+checks+" checks)");
} finally {await server.close();}
