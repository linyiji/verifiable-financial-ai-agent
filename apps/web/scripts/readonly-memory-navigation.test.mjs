import assert from "node:assert/strict";
import {createServer} from "vite";
const v=await createServer({server:{middlewareMode:true,hmr:false},appType:"custom"});
try {
 const {isObservedIncrementalRelease:check}=await v.ssrLoadModule("/src/state/memoryWriteback.ts");
 const p=(runId,status,incremental=true)=>({run:{runId,backendStatus:status},object:{objectId:"OBJ-A"},terminal:{isTerminal:["RELEASED","FAILED"].includes(status)},confirmedScheme:{incrementalContext:incremental?{}:null}});
 assert.equal(check(null,p("R5","RELEASED")),false);
 assert.equal(check(p("R5","RELEASED"),p("R5","RELEASED")),false);
 assert.equal(check(p("R1","RUNNING"),p("R5","RELEASED")),false);
 assert.equal(check(p("R5","RUNNING"),p("R5","RELEASED")),true);
 assert.equal(check(p("R5","RUNNING"),p("R5","RELEASED",false)),false);
 assert.equal(check(p("R5","FAILED"),p("R5","RELEASED")),false);
 assert.equal(check(p("R5","RUNNING"),null),false);
 assert.equal(check(p("R5","RUNNING"),{...p("R5","RELEASED"),object:{objectId:"OTHER"}}),false);
 console.log("Read-only Memory navigation: 8/8 PASS");
} finally {await v.close();}
