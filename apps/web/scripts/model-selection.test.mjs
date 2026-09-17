import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createServer} from "vite";
import {renderToStaticMarkup} from "react-dom/server";

const options = JSON.parse(readFileSync(0, "utf8"));
const server = await createServer({server: {middlewareMode: true}, appType: "custom"});
try {
  const {NewResearchTaskPage} = await server.ssrLoadModule("/src/pages/NewResearchTaskPage.tsx");
  const {modelSelectionPreferences, decodeModelSelectionOptions} = await server.ssrLoadModule("/src/types/modelSelection.ts");
  const {HttpFrontendDataSource} = await server.ssrLoadModule("/src/data/HttpFrontendDataSource.ts");
  const {createPhase4Mutation} = await server.ssrLoadModule("/src/data/FrontendDataSource.ts");
  const safeOptions = decodeModelSelectionOptions(options);
  const terra = safeOptions.find(option => option.label === "Terra");
  assert.ok(terra);
  const bodies = [];
  const source = new HttpFrontendDataSource({fetch: async (_url, init) => {
    bodies.push(JSON.parse(init.body));
    throw new TypeError("offline capture only");
  }});
  const props = {step: "GOAL", objects: [], selected: null, goal: "Offline", asOf: "2026-09-17",
    draft: null, preparing: false, confirming: false, modelOptions: safeOptions,
    onSelectObject() {}, onGoalChange() {}, onStepChange() {}, onPrepare() {}, onConfirm() {}};
  function findSelect(element) {
    if (!element || typeof element !== "object") return undefined;
    if (element.type === "select") return element;
    return [element.props?.children].flat(Infinity).map(findSelect).find(Boolean);
  }
  for (const choice of ["", terra.route_id]) {
    let route = "";
    const tree = NewResearchTaskPage({...props, modelRoute: route, onModelChange: value => {route = value;}});
    const select = findSelect(tree);
    assert.ok(select && !select.props.disabled);
    select.props.onChange({target: {value: choice}});
    assert.equal(route, choice);
    const updated = NewResearchTaskPage({...props, modelRoute: route});
    assert.equal(findSelect(updated).props.value, choice);
    const html = renderToStaticMarkup(updated);
    assert.match(html, /Terra/u);
    assert.match(html, /Default/u);
    await assert.rejects(source.prepareResearchRun(createPhase4Mutation({researchObjectId: "OBJ-local",
      researchGoal: props.goal, asOf: props.asOf, preferences: modelSelectionPreferences(route)})));
  }
  assert.deepEqual(bodies[0].preferences, {});
  assert.deepEqual(bodies[1].preferences, {model_selection: {route_id: terra.route_id}});
  assert.throws(() => decodeModelSelectionOptions([{route_id: "x"}]));
  process.stdout.write(JSON.stringify(bodies));
} finally {
  await server.close();
}
