import assert from "node:assert/strict";
import vm from "node:vm";
import test from "node:test";
import {rolldown} from "rolldown";

const bundle = await rolldown({input:new URL("../src/components/ReexecutionAction.tsx", import.meta.url).pathname,
  external:["react","react/jsx-runtime"]});
const source = (await bundle.generate({format:"cjs"})).output[0].code;
await bundle.close();

// Execute the actual component's event handlers with deterministic hook/network adapters.
// No browser, backend, production authorization, or provider is contacted.
function fixture({fail = false, mismatch = false, expired = false, failed = true} = {}) {
  const states = [], refs = [], calls = [], navigation = [];
  let stateIndex = 0, refIndex = 0, effectStarted = false;
  const auth = {authorization_id:"AUTH-X", research_object_id:"OBJ-X", reexecution_of_run_id:"RUN-FAILED",
    scheme_id:"SCHEME-SAME", scheme_hash:"sha256:"+"a".repeat(64), base_run_id:"RUN-BASE",
    base_research_view_version:"VIEW-BASE", expires_at: new Date(Date.now() + (expired ? -1000 : 30000)).toISOString()};
  const react = {
    useState(initial) {const index = stateIndex++; if (!(index in states)) states[index] = initial; return [states[index], value => {states[index] = value;}];},
    useRef(initial) {const index = refIndex++; return refs[index] ??= {current: initial};},
    useEffect(callback) {if (!effectStarted) {effectStarted = true; callback();}},
  };
  const exports = {};
  const jsx = (type, props) => ({type, props});
  const module = {exports};
  vm.runInNewContext(source, {exports, module, require: name => name === "react" ? react : {jsx, jsxs:jsx, Fragment:"fragment"},
    AbortController, Date, crypto, encodeURIComponent, fetch: async (url, options) => {
      calls.push({url, options});
      if (!options.method) return {ok:true, json:async()=>({base_run_id:"RUN-BASE",reexecution_of_run_id:"RUN-EARLIER"})};
      if (fail) return {ok:false};
      return {ok:true, json:async()=>url.endsWith("reexecute")
        ? {...auth,run_id:mismatch ? "RUN-FAILED" : "RUN-NEW"} : auth};
    }});
  function render() {
    stateIndex = refIndex = 0;
    return module.exports.ReexecutionAction({runId:"RUN-FAILED",objectId:"OBJ-X",failed,backendOrigin:"http://local.invalid",onNavigate:path=>navigation.push(path)});
  }
  return {render,calls,navigation};
}
function nodes(tree, type) {
  if (!tree || typeof tree !== "object") return [];
  if (Array.isArray(tree)) return tree.flatMap(child=>nodes(child,type));
  return [...(tree.type === type ? [tree] : []), ...nodes(tree.props?.children,type)];
}
const settle = () => new Promise(resolve=>setImmediate(resolve));

test("two explicit actions retain intent; no prepare; new Run navigation", async()=>{
  const f=fixture(); f.render(); await settle();
  let button=nodes(f.render(),"button")[0];
  assert.equal(button.props.children,"重新执行"); button.props.onClick(); await settle();
  button=nodes(f.render(),"button")[0];
  assert.equal(button.props.children,"确认沿用方案并重新执行"); button.props.onClick(); await settle();
  const posts=f.calls.filter(c=>c.options.method);
  assert.equal(posts.length,2);
  assert.ok(posts[0].url.endsWith("RUN-FAILED/reexecution-authorizations"));
  assert.ok(posts[1].url.endsWith("RUN-FAILED/reexecute"));
  assert.deepEqual(JSON.parse(posts[0].options.body),{research_object_id:"OBJ-X",authorize_reexecution:true});
  assert.deepEqual(JSON.parse(posts[1].options.body),{research_object_id:"OBJ-X",authorization_id:"AUTH-X"});
  assert.ok(posts.every(c=>c.options.headers["Idempotency-Key"]));
  assert.deepEqual(f.navigation,["/runs/RUN-NEW"]);
  assert.ok(nodes(f.render(),"a")[0].props.href.endsWith("RUN-EARLIER"));
});
test("double click sends one authorization", async()=>{
  const f=fixture();f.render();await settle();const button=nodes(f.render(),"button")[0];
  button.props.onClick();button.props.onClick();await settle();
  assert.equal(f.calls.filter(c=>c.options.method).length,1);
});
test("failed POST stops without automatic retry", async()=>{
  const f=fixture({fail:true});f.render();await settle();nodes(f.render(),"button")[0].props.onClick();await settle();
  const button=nodes(f.render(),"button")[0];assert.equal(button.props.disabled,true);
  button.props.onClick();await settle();assert.equal(f.calls.filter(c=>c.options.method).length,1);
  assert.deepEqual(f.navigation,[]);
});
test("wrong response identity cannot navigate", async()=>{
  const f=fixture({mismatch:true});f.render();await settle();
  nodes(f.render(),"button")[0].props.onClick();await settle();
  nodes(f.render(),"button")[0].props.onClick();await settle();
  assert.deepEqual(f.navigation,[]);assert.equal(nodes(f.render(),"button")[0].props.disabled,true);
});
test("expired authorization disables execution", async()=>{
  const f=fixture({expired:true});f.render();await settle();nodes(f.render(),"button")[0].props.onClick();await settle();
  assert.equal(nodes(f.render(),"button")[0].props.disabled,true);
});
test("nonfailed execution shows lineage but no reexecute action", async()=>{
  const f=fixture({failed:false});f.render();await settle();assert.equal(nodes(f.render(),"button").length,0);
  assert.equal(nodes(f.render(),"a").length,1);
});
