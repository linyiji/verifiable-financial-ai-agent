import { test, expect } from "@playwright/test";
import {
  assertAtomicProjectionEtag,
  assertContractVersionHeader,
  assertNoDemoFallback,
  assertNoPublicSurfaceLeaks,
  assertNoSecondStartRequest,
  CONTRACT,
  decodeAtomicRunProjection,
  decodeConfirmRunResponse,
  decodeErrorEnvelope,
  decodePreparedResearchDraft,
  decodeReleasedFinancialMetricEvidence,
  findFrontendFinancialAuthority,
  findPublicSurfaceLeaks
} from "../src/contracts.mjs";
import {
  apiRoutePathname,
  appendQuery,
  BrowserEvidenceLedger,
  contractControl,
  decodeProjectionLifecycleAttributes,
  identityLocator,
  isExactApiRoute,
  loadedFrontendSources,
  pathnameOf,
  postDataJson,
  responseJson
} from "../src/browser-assertions.mjs";
import { loadBrowserScenario } from "../src/scenario.mjs";

const NEXT_NAME = /^(?:Next|下一步)$/i;
const FULL_NAME = /^(?:Full Research|完整研究)$/i;
const CONFIRM_NAME = /^(?:Confirm(?: and)? Start|Start Research|Confirm Research|开始研究|确认研究)$/i;
const RETRY_NAME = /^(?:Retry|重试)$/i;
const DISMISS_NAME = /^(?:Dismiss|关闭)$/i;
const SECOND_START_NAME = /^(?:Start Execution|Execute|开始执行|启动执行)$/i;
const RESULTS_NAME = /^(?:Results|Financial Results|Financial Report|结果|财务结果|财务报告)$/i;
const TERMINAL_RUN_STATUSES = new Set(["RELEASED", "FAILED", "CANCELLED"]);
const TARGETED_PROJECTION_LATENCY_MILLISECONDS = 8_000;

const controlEvidence = (...controlIds) => ({
  annotation: controlIds.map((controlId) => ({ type: "vs01-control", description: controlId }))
});

let scenario;
let journey;

function primaryApiPath(relativePath) {
  return apiRoutePathname(scenario.primaryApiBaseUrl, relativePath);
}

function projectionRelativePath(runId) {
  return `/research-runs/${encodeURIComponent(runId)}/projection`;
}

function eventsRelativePath(runId) {
  return `/research-runs/${encodeURIComponent(runId)}/events`;
}

function runRelativePath(runId) {
  return `/research-runs/${encodeURIComponent(runId)}`;
}

function resultRelativePath(runId) {
  return `/research-runs/${encodeURIComponent(runId)}/result`;
}

function isPrimaryApiResponse(response, method, relativePath) {
  return response.request().method() === method
    && isExactApiRoute(response.url(), scenario.primaryApiBaseUrl, relativePath);
}

function waitForProjectionResponse(page, runId) {
  return page.waitForResponse((response) =>
    isPrimaryApiResponse(response, "GET", projectionRelativePath(runId))
  );
}

function observeNextProjectionResponse(page, runId) {
  let active = true;
  let resolveResponse;
  const response = new Promise((resolve) => { resolveResponse = resolve; });
  const onResponse = (candidate) => {
    if (!isPrimaryApiResponse(candidate, "GET", projectionRelativePath(runId))) return;
    active = false;
    page.off("response", onResponse);
    resolveResponse(candidate);
  };
  page.on("response", onResponse);
  return {
    response,
    dispose() {
      if (!active) return;
      active = false;
      page.off("response", onResponse);
      resolveResponse(null);
    }
  };
}

function waitForSseResponse(page, runId) {
  return page.waitForResponse((response) =>
    isPrimaryApiResponse(response, "GET", eventsRelativePath(runId))
  );
}

function acceptedRequestVersion(request) {
  const value = request.headers()["x-phase4-contract-version"];
  expect(value === undefined || value === CONTRACT.core).toBe(true);
}

function expectExactKeysAbsent(value, keys) {
  for (const key of keys) expect(Object.hasOwn(value, key), `${key} is outside the frozen wire request`).toBe(false);
}

async function visibleBodyText(page) {
  return page.locator("body").innerText();
}

async function assertPublicPageClean(page, label) {
  const [visibleText, dom] = await Promise.all([visibleBodyText(page), page.content()]);
  expect(findPublicSurfaceLeaks([
    { path: `${label}:visible-ui`, source: visibleText },
    { path: `${label}:dom`, source: dom }
  ], [scenario.secretSentinel])).toEqual([]);
  return visibleText;
}

function assertPublicSourcesClean(sources, label) {
  expect(
    findPublicSurfaceLeaks(sources, [scenario.secretSentinel]),
    `${label} must expose no provider, credential, hidden-reasoning, raw-payload, stack, or internal-path markers`
  ).toEqual([]);
}

async function waitForTypedError(page) {
  const hook = page.getByTestId("typed-error");
  if (await hook.count()) return hook.first();
  return page.getByRole("alert").first();
}

async function decodeProjectionResponse(response, expectedIdentity) {
  expect(response.ok()).toBe(true);
  assertContractVersionHeader(await response.allHeaders());
  const projection = decodeAtomicRunProjection(await responseJson(response), expectedIdentity);
  assertAtomicProjectionEtag(await response.headerValue("etag"), projection);
  return projection;
}

async function assertSseHandshake(response, runId, lastCommittedSequence) {
  const request = response.request();
  const url = new URL(response.url());
  expect(response.status()).toBe(200);
  expect(isExactApiRoute(response.url(), scenario.primaryApiBaseUrl, eventsRelativePath(runId))).toBe(true);
  expect(url.search).toBe("");
  expect(request.method()).toBe("GET");
  expect(request.resourceType()).toBe("fetch");
  expect(request.headers().accept).toBe("text/event-stream");
  expect(request.headers()["last-event-id"]).toBe(String(lastCommittedSequence));
  expect(request.headers()["x-phase4-contract-version"]).toBe(CONTRACT.core);
  expect(response.fromServiceWorker()).toBe(false);
  expect((await response.headerValue("content-type")) ?? "").toMatch(/^text\/event-stream(?:;|$)/i);
  expect((await response.headerValue("cache-control")) ?? "").toMatch(/(?:^|,)\s*no-cache\s*(?:,|$)/i);
  expect(await response.headerValue("x-phase4-contract-version")).toBe(CONTRACT.core);
  expect(await response.headerValue("x-phase4-event-contract-version")).toBe(CONTRACT.event);
}

function connectionHook(page, runId) {
  return identityLocator(page, "runtime-connection", "data-run-id", runId);
}

async function waitForConnection(page, runId, allowedStates) {
  const hook = connectionHook(page, runId);
  await expect(hook).toBeVisible();
  await expect(hook).toHaveAttribute("role", "status");
  await expect(hook).toHaveAttribute("aria-live", "polite");
  await expect.poll(async () => allowedStates.includes(
    await hook.getAttribute("data-connection-state")
  )).toBe(true);
  const state = await hook.getAttribute("data-connection-state");
  const lastSequenceText = await hook.getAttribute("data-last-sequence");
  expect(lastSequenceText).toMatch(/^(?:0|[1-9][0-9]*)$/);
  return {
    hook,
    state,
    lastSequence: Number(lastSequenceText),
    stale: await hook.getAttribute("data-stale")
  };
}

async function assertLiveResponsePending(page, response, label) {
  const request = response.request();
  let active = true;
  let resolveEvent;
  const eventSettlement = new Promise((resolve) => { resolveEvent = resolve; });
  const cleanup = () => {
    if (!active) return;
    active = false;
    page.off("requestfinished", onFinished);
    page.off("requestfailed", onFailed);
  };
  const settle = (kind, source) => {
    if (!active) return;
    cleanup();
    resolveEvent(Object.freeze({ kind, source }));
  };
  const onFinished = (candidate) => {
    if (candidate === request) settle("FINISHED", "REQUEST_FINISHED");
  };
  const onFailed = (candidate) => {
    if (candidate === request) settle("FAILED", "REQUEST_FAILED");
  };
  page.on("requestfinished", onFinished);
  page.on("requestfailed", onFailed);
  const responseSettlement = response.finished().then((error) => Object.freeze({
    kind: error === null ? "FINISHED" : "FAILED",
    source: "RESPONSE_FINISHED"
  }));
  const preexistingFailure = request.failure();
  const settlement = preexistingFailure
    ? Promise.resolve(Object.freeze({ kind: "FAILED", source: "PREEXISTING_FAILURE" }))
    : Promise.race([eventSettlement, responseSettlement]);
  const alreadyFinished = await Promise.race([
    settlement.then(() => true, () => true),
    new Promise((resolve) => setTimeout(() => resolve(false), 75))
  ]);
  if (alreadyFinished) cleanup();
  expect(alreadyFinished, `${label} must still be an active network request`).toBe(false);
  return settlement.finally(cleanup);
}

function projectionLifecycleHook(page) {
  return page.getByTestId("projection-lifecycle");
}

async function readProjectionLifecycle(page) {
  const hook = projectionLifecycleHook(page);
  await expect(hook, "public projection request lifecycle hook is mandatory").toHaveCount(1);
  await expect(hook).toBeVisible();
  await expect(hook).toHaveAttribute("role", "status");
  const attributes = await hook.evaluate((node) => ({
    runId: node.getAttribute("data-run-id"),
    requestEpoch: node.getAttribute("data-request-epoch"),
    settled: node.getAttribute("data-settled"),
    consumedRunId: node.getAttribute("data-consumed-run-id"),
    consumedRequestEpoch: node.getAttribute("data-consumed-request-epoch"),
    consumedProjectionRevision: node.getAttribute("data-consumed-projection-revision"),
    consumedProjectionSequence: node.getAttribute("data-consumed-projection-sequence"),
    discardedRunId: node.getAttribute("data-last-discarded-run-id"),
    discardedRequestEpoch: node.getAttribute("data-last-discarded-request-epoch"),
    discardedProjectionRevision: node.getAttribute("data-last-discarded-projection-revision"),
    discardedProjectionSequence: node.getAttribute("data-last-discarded-projection-sequence"),
    discardReason: node.getAttribute("data-last-discard-reason")
  }));
  return decodeProjectionLifecycleAttributes(attributes);
}

async function waitForSettledProjectionLifecycle(page, projection, minimumEpoch = 1) {
  await expect.poll(async () => {
    try {
      const state = await readProjectionLifecycle(page);
      return state.runId === projection.runId
        && state.requestEpoch >= minimumEpoch
        && state.settled
        && state.consumed?.runId === projection.runId
        && state.consumed?.requestEpoch === state.requestEpoch
        && state.consumed?.projectionRevision === projection.projectionRevision
        && state.consumed?.projectionSequence === projection.projectionSequence;
    } catch {
      return false;
    }
  }, { message: `projection lifecycle must settle exact Run ${projection.runId}` }).toBe(true);
  return readProjectionLifecycle(page);
}

async function waitForPendingProjectionLifecycle(page, runId, afterEpoch) {
  await expect.poll(async () => {
    try {
      const state = await readProjectionLifecycle(page);
      return state.runId === runId && state.requestEpoch > afterEpoch && !state.settled;
    } catch {
      return false;
    }
  }, { message: `projection lifecycle must expose pending exact Run ${runId}` }).toBe(true);
  return readProjectionLifecycle(page);
}

async function waitForDiscardedProjectionLifecycle(page, currentProjection, discardedProjection, epochs) {
  await expect.poll(async () => {
    try {
      const state = await readProjectionLifecycle(page);
      return state.runId === currentProjection.runId
        && state.requestEpoch === epochs.current
        && state.settled
        && state.consumed?.runId === currentProjection.runId
        && state.consumed?.requestEpoch === epochs.current
        && state.consumed?.projectionRevision === currentProjection.projectionRevision
        && state.consumed?.projectionSequence === currentProjection.projectionSequence
        && state.discarded?.runId === discardedProjection.runId
        && state.discarded?.requestEpoch === epochs.discarded
        && state.discarded?.projectionRevision === discardedProjection.projectionRevision
        && state.discarded?.projectionSequence === discardedProjection.projectionSequence
        && state.discarded?.reason === "STALE_RESPONSE";
    } catch {
      return false;
    }
  }, { message: "frontend must publicly settle/quarantine the exact delayed stale response" }).toBe(true);
  return readProjectionLifecycle(page);
}

async function assertRenderedProjection(page, projection) {
  const workspace = page.getByTestId("run-workspace");
  await expect(workspace).toBeVisible();
  await expect(workspace).toHaveAttribute("data-run-id", projection.runId);
  await expect(workspace).toHaveAttribute("data-object-id", projection.objectId);
  await expect(workspace).toHaveAttribute("data-goal-id", projection.goalId);
  await expect(workspace).toHaveAttribute("data-scheme-id", projection.schemeId);
  await expect(workspace).toHaveAttribute("data-run-status", projection.status);
  await expect(workspace).toHaveAttribute("data-run-stage", projection.stage);
  await expect(workspace).toHaveAttribute("data-projection-revision", String(projection.projectionRevision));
  await expect(workspace).toHaveAttribute("data-projection-sequence", String(projection.projectionSequence));

  const researchPath = page.getByTestId("research-path");
  await expect(researchPath).toBeVisible();
  await expect(researchPath).toHaveAttribute("data-run-id", projection.runId);
  const renderedTasks = researchPath.getByTestId("research-task");
  await expect(renderedTasks).toHaveCount(projection.tasks.length);
  for (const task of projection.tasks) {
    const node = identityLocator(researchPath, "research-task", "data-task-id", task.taskId);
    await expect(node).toHaveCount(1);
    await expect(node).toHaveAttribute("data-run-id", projection.runId);
    await expect(node).toHaveAttribute("data-task-status", task.status);
    await expect(node).toHaveAttribute("data-task-progress", String(task.progress));
    await expect(node).toHaveAttribute("data-parent-task-id", task.parentTaskId ?? "");
    await expect(node).toHaveAttribute("data-dependency-ids", JSON.stringify(task.dependencyIds));
  }
}

async function readRenderedWorkspaceTruth(page) {
  return page.getByTestId("run-workspace").evaluate((workspace) => {
    const researchPath = workspace.querySelector('[data-testid="research-path"]');
    const taskRows = [...(researchPath?.querySelectorAll('[data-testid="research-task"]') ?? [])].map((node) => ({
      runId: node.getAttribute("data-run-id"),
      taskId: node.getAttribute("data-task-id"),
      status: node.getAttribute("data-task-status"),
      progress: node.getAttribute("data-task-progress"),
      parentTaskId: node.getAttribute("data-parent-task-id"),
      dependencyIds: JSON.parse(node.getAttribute("data-dependency-ids") ?? "null")
    }));
    taskRows.sort((left, right) => String(left.taskId).localeCompare(String(right.taskId)));
    return {
      runId: workspace.getAttribute("data-run-id"),
      objectId: workspace.getAttribute("data-object-id"),
      goalId: workspace.getAttribute("data-goal-id"),
      schemeId: workspace.getAttribute("data-scheme-id"),
      status: workspace.getAttribute("data-run-status"),
      stage: workspace.getAttribute("data-run-stage"),
      projectionRevision: workspace.getAttribute("data-projection-revision"),
      projectionSequence: workspace.getAttribute("data-projection-sequence"),
      researchPathRunId: researchPath?.getAttribute("data-run-id") ?? null,
      route: `${window.location.pathname}${window.location.search}${window.location.hash}`,
      tasks: taskRows
    };
  });
}

async function observeWorkspaceTruth(page) {
  const routes = [new URL(page.url()).pathname + new URL(page.url()).search + new URL(page.url()).hash];
  const onFrameNavigated = (frame) => {
    if (frame === page.mainFrame()) {
      const url = new URL(frame.url());
      routes.push(`${url.pathname}${url.search}${url.hash}`);
    }
  };
  page.on("framenavigated", onFrameNavigated);
  const state = await page.locator("html").evaluateHandle(() => {
    const snapshots = [];
    const attributeMutations = [];
    const childMutations = [];
    const trackedSelector = [
      '[data-testid="run-workspace"]',
      '[data-testid="research-path"]',
      '[data-testid="research-task"]'
    ].join(",");
    const trackedNodes = (node) => {
      if (!(node instanceof Element)) return [];
      return [
        ...(node.matches(trackedSelector) ? [node] : []),
        ...node.querySelectorAll(trackedSelector)
      ].map((element) => ({
        testId: element.getAttribute("data-testid"),
        runId: element.getAttribute("data-run-id"),
        objectId: element.getAttribute("data-object-id"),
        goalId: element.getAttribute("data-goal-id"),
        schemeId: element.getAttribute("data-scheme-id"),
        status: element.getAttribute("data-run-status") ?? element.getAttribute("data-task-status"),
        stage: element.getAttribute("data-run-stage"),
        projectionRevision: element.getAttribute("data-projection-revision"),
        projectionSequence: element.getAttribute("data-projection-sequence"),
        taskId: element.getAttribute("data-task-id"),
        progress: element.getAttribute("data-task-progress"),
        parentTaskId: element.getAttribute("data-parent-task-id"),
        dependencyIds: element.getAttribute("data-dependency-ids")
      }));
    };
    const capture = () => {
      const workspace = document.querySelector('[data-testid="run-workspace"]');
      const researchPath = workspace?.querySelector('[data-testid="research-path"]') ?? null;
      const tasks = [...(researchPath?.querySelectorAll('[data-testid="research-task"]') ?? [])]
        .map((node) => ({
          runId: node.getAttribute("data-run-id"),
          taskId: node.getAttribute("data-task-id"),
          status: node.getAttribute("data-task-status"),
          progress: node.getAttribute("data-task-progress"),
          parentTaskId: node.getAttribute("data-parent-task-id"),
          dependencyIds: JSON.parse(node.getAttribute("data-dependency-ids") ?? "null")
        }))
        .sort((left, right) => String(left.taskId).localeCompare(String(right.taskId)));
      snapshots.push({
        runId: workspace?.getAttribute("data-run-id") ?? null,
        objectId: workspace?.getAttribute("data-object-id") ?? null,
        goalId: workspace?.getAttribute("data-goal-id") ?? null,
        schemeId: workspace?.getAttribute("data-scheme-id") ?? null,
        status: workspace?.getAttribute("data-run-status") ?? null,
        stage: workspace?.getAttribute("data-run-stage") ?? null,
        projectionRevision: workspace?.getAttribute("data-projection-revision") ?? null,
        projectionSequence: workspace?.getAttribute("data-projection-sequence") ?? null,
        researchPathRunId: researchPath?.getAttribute("data-run-id") ?? null,
        route: `${window.location.pathname}${window.location.search}${window.location.hash}`,
        tasks
      });
    };
    capture();
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "attributes") {
          attributeMutations.push({
            testId: record.target.getAttribute("data-testid"),
            taskId: record.target.getAttribute("data-task-id"),
            attributeName: record.attributeName,
            oldValue: record.oldValue,
            currentValue: record.target.getAttribute(record.attributeName)
          });
          continue;
        }
        for (const node of record.addedNodes) {
          const tracked = trackedNodes(node);
          if (tracked.length) childMutations.push({ kind: "ADDED", tracked });
        }
        for (const node of record.removedNodes) {
          const tracked = trackedNodes(node);
          if (tracked.length) childMutations.push({ kind: "REMOVED", tracked });
        }
      }
      capture();
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeOldValue: true,
      childList: true,
      subtree: true,
      attributeFilter: [
        "data-run-id",
        "data-object-id",
        "data-goal-id",
        "data-scheme-id",
        "data-run-status",
        "data-run-stage",
        "data-projection-revision",
        "data-projection-sequence",
        "data-task-id",
        "data-task-status",
        "data-task-progress",
        "data-parent-task-id",
        "data-dependency-ids"
      ]
    });
    return { attributeMutations, capture, childMutations, observer, snapshots };
  });
  return async () => {
    page.off("framenavigated", onFrameNavigated);
    const observation = await state.evaluate((value) => {
      value.observer.disconnect();
      value.capture();
      return {
        attributeMutations: value.attributeMutations,
        childMutations: value.childMutations,
        snapshots: value.snapshots
      };
    });
    await state.dispose();
    return { ...observation, routes };
  };
}

async function assertNoPriorWorkspaceIdentity(page, priorProjection) {
  const truth = await readRenderedWorkspaceTruth(page);
  expect(truth.runId).not.toBe(priorProjection.runId);
  const priorTaskIds = new Set(priorProjection.taskIds);
  expect(truth.tasks.some((task) => task.runId === priorProjection.runId)).toBe(false);
  expect(truth.tasks.some((task) => priorTaskIds.has(task.taskId))).toBe(false);
}

async function clickRunNavigation(page, runId) {
  const link = identityLocator(page, "run-navigation-item", "data-run-id", runId);
  await expect(link).toHaveCount(1);
  await expect(link).toHaveAttribute("href", new RegExp(`/runs/${encodeURIComponent(runId)}(?:[?#]|$)`));
  await link.click({ noWaitAfter: true });
}

function waitForAppliedNetworkRule(cdp, ruleId, expectedUrl) {
  const requestMetadata = new Map();
  const appliedRuleIds = new Map();
  let settled = false;
  let resolveMatch;
  const promise = new Promise((resolve) => { resolveMatch = resolve; });

  const inspect = (requestId) => {
    const request = requestMetadata.get(requestId);
    if (
      !settled
      && request?.method === "GET"
      && request.url === expectedUrl
      && appliedRuleIds.get(requestId) === ruleId
    ) {
      settled = true;
      cdp.off("Network.requestWillBeSent", onRequest);
      cdp.off("Network.requestWillBeSentExtraInfo", onExtraInfo);
      resolveMatch();
    }
  };
  const onRequest = (event) => {
    requestMetadata.set(event.requestId, { method: event.request.method, url: event.request.url });
    inspect(event.requestId);
  };
  const onExtraInfo = (event) => {
    appliedRuleIds.set(event.requestId, event.appliedNetworkConditionsId ?? null);
    inspect(event.requestId);
  };
  cdp.on("Network.requestWillBeSent", onRequest);
  cdp.on("Network.requestWillBeSentExtraInfo", onExtraInfo);
  return {
    promise,
    dispose() {
      cdp.off("Network.requestWillBeSent", onRequest);
      cdp.off("Network.requestWillBeSentExtraInfo", onExtraInfo);
    }
  };
}

test.describe.serial("Phase 4 VS01 frontend journey", () => {
  test.beforeAll(async () => {
    scenario = await loadBrowserScenario();
  });

  test("real journey: VS01-FE-003, VS01-FE-004, VS01-FE-005, VS01-FE-006, VS01-FE-007, VS01-DYN-001", controlEvidence(
    "VS01-FE-003",
    "VS01-FE-004",
    "VS01-FE-005",
    "VS01-FE-006",
    "VS01-FE-007",
    "VS01-DYN-001"
  ), async ({ page, request }) => {
    const ledger = new BrowserEvidenceLedger(page, {
      apiBaseUrl: scenario.primaryApiBaseUrl,
      secretSentinel: scenario.secretSentinel
    });
    const objectResponsePromise = page.waitForResponse((response) =>
      isPrimaryApiResponse(response, "GET", "/objects")
    );
    await page.goto("/new");
    const objectResponse = await objectResponsePromise;
    expect(objectResponse.ok()).toBe(true);
    assertContractVersionHeader(await objectResponse.allHeaders());

    const objectOption = identityLocator(page, "research-object-option", "data-object-id", scenario.object.objectId);
    await expect(objectOption).toBeVisible();
    await expect(objectOption).toContainText(scenario.object.symbol);
    await expect(objectOption).toContainText(scenario.object.companyName);
    await objectOption.click();

    const firstNext = await contractControl(page, "wizard-next", "button", NEXT_NAME);
    await firstNext.click();

    const fullResearch = await contractControl(page, "full-research", "button", FULL_NAME);
    await expect(fullResearch).toBeVisible();
    await fullResearch.click();
    const goal = page.getByRole("textbox", { name: /Research Goal|研究目标/i });
    await expect(goal).toBeVisible();
    await goal.fill(scenario.goalText);

    const prepareResponsePromise = page.waitForResponse((response) =>
      isPrimaryApiResponse(response, "POST", "/research-runs/prepare")
    );
    const secondNext = await contractControl(page, "wizard-next", "button", NEXT_NAME);
    await secondNext.click();
    const prepareResponse = await prepareResponsePromise;
    expect(prepareResponse.ok()).toBe(true);
    acceptedRequestVersion(prepareResponse.request());
    const prepareRequest = postDataJson(prepareResponse.request());
    expect(prepareRequest.research_object_id).toBe(scenario.object.objectId);
    expect(prepareRequest.research_goal).toBe(scenario.goalText);
    expect(prepareRequest.as_of).toBe(scenario.asOf);
    expect(prepareRequest.preferences).toEqual({});
    expect(Object.keys(prepareRequest).sort()).toEqual([
      "as_of", "preferences", "research_goal", "research_object_id"
    ]);
    expect(prepareResponse.request().headers()["idempotency-key"]).toBeTruthy();
    expectExactKeysAbsent(prepareRequest, ["mode", "goal_template_id", "plan_id", "tasks", "graph"]);
    assertContractVersionHeader(await prepareResponse.allHeaders());
    const draft = decodePreparedResearchDraft(await responseJson(prepareResponse), {
      objectId: scenario.object.objectId,
      goalText: scenario.goalText,
      asOf: scenario.asOf,
      preferences: {}
    });

    const schemePreview = page.getByTestId("scheme-preview");
    await expect(schemePreview).toBeVisible();
    await expect(schemePreview).toHaveAttribute("data-object-id", draft.objectId);
    await expect(schemePreview).toHaveAttribute("data-goal-id", draft.goalId);
    await expect(schemePreview).toHaveAttribute("data-scheme-id", draft.schemeId);
    await expect(schemePreview).toHaveAttribute("data-draft-id", draft.draftId);
    await expect(page.getByTestId("research-task")).toHaveCount(0);

    const schemeNext = await contractControl(page, "wizard-next", "button", NEXT_NAME);
    await schemeNext.click();
    const confirm = await contractControl(page, "confirm-run", "button", CONFIRM_NAME);
    await expect(confirm).toBeVisible();

    const confirmResponsePromise = page.waitForResponse((response) =>
      isPrimaryApiResponse(response, "POST", "/research-runs")
    );
    const anyProjectionPromise = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && new URL(response.url()).origin === new URL(scenario.primaryApiBaseUrl).origin
      && /\/research-runs\/[^/]+\/projection$/.test(pathnameOf(response.url()))
    );
    await confirm.dblclick({ delay: 10 });
    const confirmResponse = await confirmResponsePromise;
    expect(confirmResponse.status()).toBe(201);
    acceptedRequestVersion(confirmResponse.request());
    const confirmRequest = postDataJson(confirmResponse.request());
    expect(confirmRequest).toEqual({
      draft_id: draft.draftId,
      draft_version: draft.draftVersion,
      draft_hash: draft.draftHash,
      research_object_id: draft.objectId,
      confirm_scheme: true
    });
    expect(confirmResponse.request().headers()["idempotency-key"]).toBeTruthy();
    assertContractVersionHeader(await confirmResponse.allHeaders());
    const confirmResult = decodeConfirmRunResponse(await responseJson(confirmResponse), draft);
    expect(confirmResult.responseMeta.idempotencyReplayed).toBe(false);

    const projectionResponse = await anyProjectionPromise;
    expect(isExactApiRoute(
      projectionResponse.url(),
      scenario.primaryApiBaseUrl,
      projectionRelativePath(confirmResult.admission.runId)
    )).toBe(true);
    const projectionExpectation = Object.freeze({
      ...confirmResult.admission,
      goal: draft.goal,
      schemeSnapshot: draft.schemeSnapshot
    });
    const projection = await decodeProjectionResponse(projectionResponse, projectionExpectation);
    expect(projection.tasks.length, "DYN-001 requires at least one authoritative projected Task").toBeGreaterThan(0);

    await expect(page).toHaveURL(new RegExp(`/runs/${encodeURIComponent(projection.runId)}(?:[?#]|$)`));
    await assertRenderedProjection(page, projection);
    await expect(page.getByRole("button", { name: SECOND_START_NAME })).toHaveCount(0);
    assertNoSecondStartRequest(ledger.requests, primaryApiPath("/research-runs"));
    expect(ledger.requestsFor("POST", primaryApiPath("/research-runs"))).toHaveLength(1);

    const sources = await loadedFrontendSources(page, request, [scenario.secretSentinel]);
    const sourceText = sources.map((entry) => entry.source).join("\n");
    assertNoDemoFallback(sourceText, "reachable production module graph");
    assertPublicSourcesClean(sources, "reachable production module graph");
    expect(findFrontendFinancialAuthority(sources)).toEqual([]);
    const workspaceBody = await assertPublicPageClean(page, "Run Workspace");
    assertNoDemoFallback(workspaceBody, "Run Workspace DOM");
    ledger.assertApiBinding(scenario.primaryApiBaseUrl);
    await ledger.drainAndAssertPublicEvidenceClean();

    journey = Object.freeze({ draft, confirmResult, projectionExpectation, projection, projectionUrl: projectionResponse.url() });
  });

  test("real same-Object Run switch and delayed authentic projection quarantine: VS01-REC-008, VS01-ID-003", controlEvidence(
    "VS01-REC-008",
    "VS01-ID-003"
  ), async ({ page, context }) => {
    expect(journey, "happy-path journey must establish Run A").toBeTruthy();
    const runA = journey.projection;
    const ledger = new BrowserEvidenceLedger(page, {
      apiBaseUrl: scenario.primaryApiBaseUrl,
      secretSentinel: scenario.secretSentinel
    });

    const projectionAPromise = waitForProjectionResponse(page, runA.runId);
    const streamAPromise = waitForSseResponse(page, runA.runId);
    await page.goto(`/runs/${encodeURIComponent(runA.runId)}`);
    const projectionAResponse = await projectionAPromise;
    const projectionA = await decodeProjectionResponse(projectionAResponse, journey.projectionExpectation);
    expect(TERMINAL_RUN_STATUSES.has(projectionA.status), "Run A must be a live nonterminal acceptance Run").toBe(false);
    await assertRenderedProjection(page, projectionA);
    const streamAResponse = await streamAPromise;
    await assertSseHandshake(streamAResponse, projectionA.runId, projectionA.projectionSequence);
    const openA = await waitForConnection(page, projectionA.runId, ["OPEN"]);
    expect(openA.stale).toBe("false");
    const streamAEnd = await assertLiveResponsePending(page, streamAResponse, "Run A SSE before Run switch");

    const projectionBPromise = waitForProjectionResponse(page, scenario.alternate.runId);
    const streamBPromise = waitForSseResponse(page, scenario.alternate.runId);
    await clickRunNavigation(page, scenario.alternate.runId);
    const projectionB = await decodeProjectionResponse(await projectionBPromise, {
      runId: scenario.alternate.runId,
      objectId: scenario.alternate.objectId
    });
    expect(projectionB.taskIds).toContain(scenario.alternate.taskId);
    expect(TERMINAL_RUN_STATUSES.has(projectionB.status), "Run B must be a live nonterminal acceptance Run").toBe(false);
    const streamBResponse = await streamBPromise;
    await assertSseHandshake(streamBResponse, projectionB.runId, projectionB.projectionSequence);
    await waitForConnection(page, projectionB.runId, ["OPEN"]);
    expect(["FINISHED", "FAILED"]).toContain((await streamAEnd).kind);
    await expect(page).toHaveURL(new RegExp(`/runs/${encodeURIComponent(projectionB.runId)}(?:[?#]|$)`));
    await assertRenderedProjection(page, projectionB);
    const initialBProjectionLifecycle = await waitForSettledProjectionLifecycle(page, projectionB);
    await assertNoPriorWorkspaceIdentity(page, projectionA);
    expect(ledger.requestsFor("GET", primaryApiPath(eventsRelativePath(projectionA.runId)))).toHaveLength(1);

    const cdp = await context.newCDPSession(page);
    let appliedRule;
    let stopWorkspaceObserver = null;
    try {
      await cdp.send("Network.enable");
      await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
      const latency = await cdp.send("Network.emulateNetworkConditionsByRule", {
        matchedNetworkConditions: [{
          urlPattern: projectionAResponse.url(),
          latency: TARGETED_PROJECTION_LATENCY_MILLISECONDS,
          downloadThroughput: -1,
          uploadThroughput: -1
        }]
      });
      expect(latency.ruleIds).toHaveLength(1);
      appliedRule = waitForAppliedNetworkRule(cdp, latency.ruleIds[0], projectionAResponse.url());

      const delayedARequestPromise = page.waitForRequest((request) =>
        request.method() === "GET" && request.url() === projectionAResponse.url()
      );
      const delayedAResponsePromise = page.waitForResponse((response) =>
        response.request().method() === "GET" && response.url() === projectionAResponse.url()
      );
      await clickRunNavigation(page, projectionA.runId);
      await Promise.all([delayedARequestPromise, appliedRule.promise]);
      const pendingAProjectionLifecycle = await waitForPendingProjectionLifecycle(
        page,
        projectionA.runId,
        initialBProjectionLifecycle.requestEpoch
      );

      let delayedAResponseArrived = false;
      void delayedAResponsePromise.then(() => { delayedAResponseArrived = true; });
      const secondProjectionBPromise = waitForProjectionResponse(page, projectionB.runId);
      const secondStreamBPromise = waitForSseResponse(page, projectionB.runId);
      await clickRunNavigation(page, projectionB.runId);
      const secondProjectionB = await decodeProjectionResponse(await secondProjectionBPromise, {
        runId: projectionB.runId,
        objectId: projectionB.objectId
      });
      const secondStreamB = await secondStreamBPromise;
      await assertSseHandshake(secondStreamB, secondProjectionB.runId, secondProjectionB.projectionSequence);
      await waitForConnection(page, secondProjectionB.runId, ["OPEN"]);
      await assertRenderedProjection(page, secondProjectionB);
      const currentBProjectionLifecycle = await waitForSettledProjectionLifecycle(
        page,
        secondProjectionB,
        pendingAProjectionLifecycle.requestEpoch + 1
      );
      await assertNoPriorWorkspaceIdentity(page, projectionA);
      stopWorkspaceObserver = await observeWorkspaceTruth(page);
      expect(delayedAResponseArrived, "Run B must bind before the delayed authentic Run A response arrives").toBe(false);
      await expect(page).toHaveURL(new RegExp(`/runs/${encodeURIComponent(secondProjectionB.runId)}(?:[?#]|$)`));
      const beforeDelayedA = await readRenderedWorkspaceTruth(page);

      const delayedAResponse = await delayedAResponsePromise;
      const delayedA = await decodeProjectionResponse(delayedAResponse, journey.projectionExpectation);
      expect(await delayedAResponse.finished()).toBeNull();
      const settledLifecycle = await waitForDiscardedProjectionLifecycle(
        page,
        secondProjectionB,
        delayedA,
        {
          current: currentBProjectionLifecycle.requestEpoch,
          discarded: pendingAProjectionLifecycle.requestEpoch
        }
      );
      expect(settledLifecycle.settled).toBe(true);
      expect(delayedA.runId).toBe(projectionA.runId);
      await expect(page).toHaveURL(new RegExp(`/runs/${encodeURIComponent(secondProjectionB.runId)}(?:[?#]|$)`));
      await assertRenderedProjection(page, secondProjectionB);
      await assertNoPriorWorkspaceIdentity(page, delayedA);
      expect(await readRenderedWorkspaceTruth(page)).toEqual(beforeDelayedA);
      const observedWorkspace = await stopWorkspaceObserver();
      stopWorkspaceObserver = null;
      expect(observedWorkspace.snapshots.length).toBeGreaterThan(0);
      for (const observed of observedWorkspace.snapshots) expect(observed).toEqual(beforeDelayedA);
      for (const mutation of observedWorkspace.attributeMutations) {
        expect(
          mutation.currentValue,
          `public ${mutation.testId ?? "workspace"} ${mutation.attributeName} changed while stale A was consumed`
        ).toBe(mutation.oldValue);
      }
      expect(
        observedWorkspace.childMutations,
        "workspace/Research Path/Task nodes must not be inserted or removed while stale A is consumed"
      ).toEqual([]);
      for (const route of observedWorkspace.routes) expect(route).toBe(beforeDelayedA.route);
      expect(ledger.requestsFor("GET", primaryApiPath(eventsRelativePath(projectionA.runId)))).toHaveLength(1);
      expect(ledger.apiMutations()).toEqual([]);
      ledger.assertApiBinding(scenario.primaryApiBaseUrl);
      await ledger.drainAndAssertPublicEvidenceClean({
        allowedRequestFailures: [{
          method: "GET",
          pathname: primaryApiPath(eventsRelativePath(projectionA.runId)),
          kinds: ["EXPECTED_NAVIGATION_ABORT"]
        }]
      });
    } finally {
      if (stopWorkspaceObserver) await stopWorkspaceObserver().catch(() => {});
      appliedRule?.dispose();
      await cdp.send("Network.emulateNetworkConditionsByRule", { matchedNetworkConditions: [] }).catch(() => {});
      await cdp.send("Network.setCacheDisabled", { cacheDisabled: false }).catch(() => {});
      await cdp.detach();
    }
  });

  test("real SSE offline recovery from last committed cursor: VS01-REC-009", controlEvidence(
    "VS01-REC-009"
  ), async ({ page, context }) => {
    const ledger = new BrowserEvidenceLedger(page, {
      apiBaseUrl: scenario.primaryApiBaseUrl,
      secretSentinel: scenario.secretSentinel
    });
    const runId = scenario.alternate.runId;
    const projectionPromise = waitForProjectionResponse(page, runId);
    const initialStreamPromise = waitForSseResponse(page, runId);
    await page.goto(`/runs/${encodeURIComponent(runId)}`);
    const projection = await decodeProjectionResponse(await projectionPromise, {
      runId,
      objectId: scenario.alternate.objectId
    });
    expect(TERMINAL_RUN_STATUSES.has(projection.status), "offline recovery requires a nonterminal real Run").toBe(false);
    await assertRenderedProjection(page, projection);
    const initialStream = await initialStreamPromise;
    await assertSseHandshake(initialStream, runId, projection.projectionSequence);
    const open = await waitForConnection(page, runId, ["OPEN"]);
    expect(open.stale).toBe("false");
    expect(open.lastSequence, "offline target must be quiescent at the decoded projection cursor").toBe(
      projection.projectionSequence
    );
    await assertRenderedProjection(page, projection);
    const beforeDisconnect = await readRenderedWorkspaceTruth(page);
    const initialStreamEnd = await assertLiveResponsePending(
      page,
      initialStream,
      "same-Run SSE before browser-offline disconnect"
    );

    let finalProjectionObservation = null;
    await context.setOffline(true);
    try {
      await expect.poll(() => page.evaluate(() => navigator.onLine)).toBe(false);
      const disconnected = await waitForConnection(page, runId, ["RECOVERING", "BACKOFF"]);
      expect(disconnected.stale).toBe("true");
      const initialSettlement = await initialStreamEnd;
      expect(
        initialSettlement,
        "browser-offline must end the old live SSE through requestfailed"
      ).toEqual({ kind: "FAILED", source: "REQUEST_FAILED" });
      const lastCommitted = await waitForConnection(page, runId, ["RECOVERING", "BACKOFF"]);
      expect(lastCommitted.lastSequence).toBe(projection.projectionSequence);
      await expect(page.getByTestId("run-workspace")).toHaveAttribute("data-run-id", runId);
      await expect(page.getByTestId("run-workspace")).not.toHaveAttribute("data-run-status", "FAILED");
      await expect(page.getByTestId("typed-error")).toHaveCount(0);
      expect(await readRenderedWorkspaceTruth(page)).toEqual(beforeDisconnect);
      expect(ledger.apiMutations()).toEqual([]);

      const reconnectStreamPromise = waitForSseResponse(page, runId);
      finalProjectionObservation = observeNextProjectionResponse(page, runId);
      await context.setOffline(false);
      await expect.poll(() => page.evaluate(() => navigator.onLine)).toBe(true);
      const reconnectStream = await reconnectStreamPromise;
      await assertSseHandshake(reconnectStream, runId, lastCommitted.lastSequence);
      const reconnected = await waitForConnection(page, runId, ["OPEN", "TERMINAL"]);
      expect(reconnected.stale).toBe("false");
      await expect(page.getByTestId("run-workspace")).toHaveAttribute("data-run-id", runId);
      await expect(page.getByTestId("run-workspace")).not.toHaveAttribute("data-run-status", "FAILED");
      if (reconnected.state === "TERMINAL") {
        const finalProjectionResponse = await finalProjectionObservation.response;
        expect(finalProjectionResponse, "TERMINAL reconnect must consume an authoritative projection").not.toBeNull();
        const finalProjection = await decodeProjectionResponse(finalProjectionResponse, {
          runId,
          objectId: scenario.alternate.objectId
        });
        expect(TERMINAL_RUN_STATUSES.has(finalProjection.status)).toBe(true);
        expect(finalProjection.status).not.toBe("FAILED");
        await assertRenderedProjection(page, finalProjection);
      } else {
        expect(reconnected.lastSequence).toBe(projection.projectionSequence);
        await assertRenderedProjection(page, projection);
        expect(await readRenderedWorkspaceTruth(page)).toEqual(beforeDisconnect);
      }
      finalProjectionObservation.dispose();
      expect(ledger.requests.some((request) =>
        request.pathname.includes("/research-runs/")
        && request.pathname.endsWith("/events")
        && request.pathname !== primaryApiPath(eventsRelativePath(runId))
      )).toBe(false);
      expect(ledger.apiMutations()).toEqual([]);
      ledger.assertApiBinding(scenario.primaryApiBaseUrl);
      await ledger.drainAndAssertPublicEvidenceClean({
        allowExpectedBrowserOffline: true,
        allowedRequestFailures: [{
          method: "GET",
          pathname: primaryApiPath(eventsRelativePath(runId)),
          kinds: ["EXPECTED_BROWSER_OFFLINE"]
        }]
      });
    } finally {
      finalProjectionObservation?.dispose();
      await context.setOffline(false);
    }
  });

  test("real wrong-resource network/DOM quarantine only: VS01-FE-008", controlEvidence(
    "VS01-FE-008"
  ), async ({ page }) => {
    expect(journey, "happy-path journey must establish the exact current Run").toBeTruthy();
    const ledger = new BrowserEvidenceLedger(page, {
      apiBaseUrl: scenario.primaryApiBaseUrl,
      secretSentinel: scenario.secretSentinel
    });
    const current = journey.projection;
    const mixedRoute = appendQuery(`/runs/${encodeURIComponent(current.runId)}`, {
      object: current.objectId,
      task: scenario.foreign.taskId
    });
    await page.goto(mixedRoute);

    const quarantine = page.getByTestId("identity-quarantine");
    await expect(quarantine).toBeVisible();
    await expect(quarantine).toHaveAttribute("data-reason", /^(?:IDENTITY_MISMATCH|NOT_FOUND|UNAVAILABLE)$/);
    await expect(page).toHaveURL(new RegExp(`/runs/${encodeURIComponent(current.runId)}`));
    const body = await assertPublicPageClean(page, "wrong-resource quarantine");
    expect(body).not.toContain(scenario.foreign.objectId);
    expect(body).not.toContain(scenario.foreign.runId);
    expect(body).not.toContain(scenario.foreign.taskId);
    for (const sentinel of scenario.foreign.sentinels) expect(body).not.toContain(sentinel);
    expect(ledger.requests.some((request) => request.pathname.includes(encodeURIComponent(scenario.foreign.runId)))).toBe(false);
    expect(ledger.apiMutations()).toEqual([]);

    await expect(page.getByTestId("run-workspace")).toHaveAttribute("data-run-id", current.runId);
    assertNoDemoFallback(body, "wrong-resource DOM");
    ledger.assertApiBinding(scenario.primaryApiBaseUrl);
    await ledger.drainAndAssertPublicEvidenceClean();
  });

  test("typed missing-resource retry/dismiss: VS01-FE-009", controlEvidence(
    "VS01-FE-009"
  ), async ({ page }) => {
    const ledger = new BrowserEvidenceLedger(page, {
      apiBaseUrl: scenario.primaryApiBaseUrl,
      secretSentinel: scenario.secretSentinel
    });
    const missingRoute = `/runs/${encodeURIComponent(scenario.missingRunId)}`;
    const errorResponsePromise = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && [runRelativePath(scenario.missingRunId), projectionRelativePath(scenario.missingRunId)]
        .some((relativePath) => isExactApiRoute(response.url(), scenario.primaryApiBaseUrl, relativePath))
      && response.status() >= 400
    );
    await page.goto(missingRoute);
    const errorResponse = await errorResponsePromise;
    const error = decodeErrorEnvelope(await responseJson(errorResponse), errorResponse.status());
    expect(error.code).toBe(scenario.missingErrorCode);
    expect(error.resource).toEqual({ type: "research_run", id: scenario.missingRunId });

    const alert = await waitForTypedError(page);
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(error.message);
    if (await alert.getAttribute("data-testid")) {
      await expect(alert).toHaveAttribute("data-error-code", error.code);
      if (error.resource) await expect(alert).toHaveAttribute("data-resource-id", error.resource.id);
    }
    await expect(page).toHaveURL(new RegExp(`/runs/${encodeURIComponent(scenario.missingRunId)}(?:[?#]|$)`));
    const bodyBeforeRetry = await assertPublicPageClean(page, "typed missing-resource error");
    expect(bodyBeforeRetry).not.toContain(scenario.object.objectId);
    expect(bodyBeforeRetry).not.toContain(scenario.foreign.runId);
    assertNoDemoFallback(bodyBeforeRetry, "typed error DOM");

    const failedUrl = errorResponse.url();
    const retryResponsePromise = page.waitForResponse((response) =>
      response.request().method() === "GET" && response.url() === failedUrl
    );
    const retry = await contractControl(page, "error-retry", "button", RETRY_NAME);
    await retry.click();
    await retryResponsePromise;
    await expect(page).toHaveURL(new RegExp(`/runs/${encodeURIComponent(scenario.missingRunId)}(?:[?#]|$)`));
    expect(ledger.apiMutations()).toEqual([]);

    const requestsBeforeDismiss = ledger.requests.length;
    const dismiss = await contractControl(page, "error-dismiss", "button", DISMISS_NAME);
    await dismiss.click();
    await expect(alert).toBeHidden();
    expect(ledger.requests).toHaveLength(requestsBeforeDismiss);
    await expect(page).toHaveURL(new RegExp(`/runs/${encodeURIComponent(scenario.missingRunId)}(?:[?#]|$)`));
    ledger.assertApiBinding(scenario.primaryApiBaseUrl);
    await ledger.drainAndAssertPublicEvidenceClean();
  });

  test("real released adversarial decimal is lossless wire-to-render: VS01-FE-012", controlEvidence(
    "VS01-FE-012"
  ), async ({ page, request }) => {
    const ledger = new BrowserEvidenceLedger(page, {
      apiBaseUrl: scenario.primaryApiBaseUrl,
      secretSentinel: scenario.secretSentinel
    });
    const projectionPromise = waitForProjectionResponse(page, scenario.financial.runId);
    const resultResponsePromise = page.waitForResponse((response) =>
      isPrimaryApiResponse(response, "GET", resultRelativePath(scenario.financial.runId))
    );
    await page.goto(`/runs/${encodeURIComponent(scenario.financial.runId)}`);
    const projection = await decodeProjectionResponse(await projectionPromise, {
      runId: scenario.financial.runId,
      objectId: scenario.financial.objectId
    });
    expect(projection.status, "financial evidence target must be a real released Run").toBe("RELEASED");
    await assertRenderedProjection(page, projection);

    const resultsTab = await contractControl(page, "result-tab", "tab", RESULTS_NAME);
    await expect(resultsTab).toBeVisible();
    await resultsTab.click();
    const resultResponse = await resultResponsePromise;
    expect(resultResponse.ok()).toBe(true);
    assertContractVersionHeader(await resultResponse.allHeaders());
    const metric = decodeReleasedFinancialMetricEvidence(await responseJson(resultResponse), {
      runId: scenario.financial.runId,
      metricId: scenario.financial.metricId,
      adversarialProperty: scenario.financial.adversarialProperty
    });
    expect(String(Number(metric.canonicalValue))).not.toBe(metric.canonicalValue);

    const metricNode = identityLocator(page, "released-financial-metric", "data-metric-id", metric.metricId);
    await expect(metricNode).toHaveCount(1);
    await expect(metricNode).toBeVisible();
    await expect(metricNode).toHaveAttribute("data-run-id", metric.runId);
    await expect(metricNode).toHaveAttribute("data-canonical-value", metric.canonicalValue);
    const canonicalValueNode = metricNode.getByTestId("canonical-financial-value");
    await expect(canonicalValueNode).toHaveCount(1);
    await expect(canonicalValueNode).toBeVisible();
    expect(await canonicalValueNode.evaluate((node) => node.textContent)).toBe(metric.canonicalValue);

    const sources = await loadedFrontendSources(page, request, [scenario.secretSentinel]);
    assertPublicSourcesClean(sources, "released financial production module graph");
    expect(findFrontendFinancialAuthority(sources)).toEqual([]);
    await assertPublicPageClean(page, "released adversarial financial value");
    ledger.assertApiBinding(scenario.primaryApiBaseUrl);
    await ledger.drainAndAssertPublicEvidenceClean();
  });

  test("unavailable backend/public surface: VS01-FE-010, VS01-FE-011", controlEvidence(
    "VS01-FE-010",
    "VS01-FE-011"
  ), async ({ page, request }) => {
    const ledger = new BrowserEvidenceLedger(page, {
      apiBaseUrl: scenario.unavailableApiBaseUrl,
      secretSentinel: scenario.secretSentinel
    });
    await page.goto(`${scenario.backendUnavailableFrontendUrl}/new`);
    const alert = await waitForTypedError(page);
    await expect(alert).toBeVisible();
    await expect(page.getByTestId("research-object-option")).toHaveCount(0);

    const body = await assertPublicPageClean(page, "backend-unavailable frontend");
    assertNoDemoFallback(body, "backend-unavailable DOM");
    expect(body).not.toContain(scenario.object.objectId);
    expect(body).not.toContain(scenario.object.symbol);
    expect(body).not.toContain(scenario.object.companyName);
    const hadUnavailableBackend = ledger.requestFailures.length > 0
      || ledger.responses.some((response) => response.status >= 500);
    expect(hadUnavailableBackend, "the scenario must prove the backend was actually unavailable").toBe(true);
    expect(ledger.responses.some((response) => response.status >= 200 && response.status < 300)).toBe(false);

    const sources = await loadedFrontendSources(page, request, [scenario.secretSentinel]);
    assertNoDemoFallback(sources.map((entry) => entry.source).join("\n"), "unavailable production module graph");
    assertPublicSourcesClean(sources, "unavailable production module graph");
    expect(findFrontendFinancialAuthority(sources)).toEqual([]);
    assertNoPublicSurfaceLeaks(
      JSON.stringify(ledger.responses),
      "sanitized browser response evidence",
      [scenario.secretSentinel]
    );
    ledger.assertApiBinding(scenario.unavailableApiBaseUrl);
    const unavailableBase = new URL(scenario.unavailableApiBaseUrl);
    await ledger.drainAndAssertPublicEvidenceClean({
      allowExpectedBackendUnavailable: true,
      allowedRequestFailures: [{
        origin: unavailableBase.origin,
        pathnamePrefix: unavailableBase.pathname.replace(/\/$/, "") || "/",
        kinds: ["EXPECTED_BACKEND_UNAVAILABLE"]
      }]
    });
  });
});
