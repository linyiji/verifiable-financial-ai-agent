import { test, expect } from "@playwright/test";
import {
  admitContextProjection,
  assertContractVersionHeader,
  assertNoDemoFallback,
  assertNoSecondStartRequest,
  CONTRACT,
  decodeAtomicRunProjection,
  decodeConfirmRunResponse,
  decodeErrorEnvelope,
  decodePreparedResearchDraft,
  findFrontendFinancialAuthority
} from "../src/contracts.mjs";
import {
  appendQuery,
  BrowserEvidenceLedger,
  contractControl,
  identityLocator,
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

const projectionPath = (runId) => `/api/research-runs/${encodeURIComponent(runId)}/projection`;
const runPath = (runId) => `/api/research-runs/${encodeURIComponent(runId)}`;

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

async function waitForTypedError(page) {
  const hook = page.getByTestId("typed-error");
  if (await hook.count()) return hook.first();
  return page.getByRole("alert").first();
}

let scenario;
let journey;

test.describe.serial("Phase 4 VS01 frontend journey", () => {
  test.beforeAll(async () => {
    scenario = await loadBrowserScenario();
  });

  test("VS01-FE-003..007 Object -> Goal -> Scheme -> Confirm -> automatic exact Run Workspace", async ({ page, request }) => {
    const ledger = new BrowserEvidenceLedger(page);
    const objectResponsePromise = page.waitForResponse((response) =>
      response.request().method() === "GET" && pathnameOf(response.url()) === "/api/objects"
    );
    await page.goto("/new");
    const objectResponse = await objectResponsePromise;
    expect(objectResponse.ok()).toBe(true);
    assertContractVersionHeader(await objectResponse.allHeaders());

    const objectOption = identityLocator(
      page,
      "research-object-option",
      "data-object-id",
      scenario.object.objectId
    );
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
      response.request().method() === "POST" && pathnameOf(response.url()) === "/api/research-runs/prepare"
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
      "as_of",
      "preferences",
      "research_goal",
      "research_object_id"
    ]);
    expect(prepareResponse.request().headers()["idempotency-key"]).toBeTruthy();
    expectExactKeysAbsent(prepareRequest, ["mode", "goal_template_id", "plan_id", "tasks", "graph"]);
    assertContractVersionHeader(await prepareResponse.allHeaders());
    const draft = decodePreparedResearchDraft(await responseJson(prepareResponse), {
      objectId: scenario.object.objectId,
      goalText: scenario.goalText
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
      response.request().method() === "POST" && pathnameOf(response.url()) === "/api/research-runs"
    );
    const anyProjectionPromise = page.waitForResponse((response) =>
      response.request().method() === "GET" && /\/api\/research-runs\/[^/]+\/projection$/.test(pathnameOf(response.url()))
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
    expect(pathnameOf(projectionResponse.url())).toBe(projectionPath(confirmResult.admission.runId));
    expect(projectionResponse.ok()).toBe(true);
    assertContractVersionHeader(await projectionResponse.allHeaders());
    const projection = decodeAtomicRunProjection(
      await responseJson(projectionResponse),
      confirmResult.admission
    );

    await expect(page).toHaveURL(new RegExp(`/runs/${encodeURIComponent(projection.runId)}(?:[?#]|$)`));
    const workspace = page.getByTestId("run-workspace");
    await expect(workspace).toBeVisible();
    await expect(workspace).toHaveAttribute("data-run-id", projection.runId);
    await expect(workspace).toHaveAttribute("data-object-id", projection.objectId);
    await expect(workspace).toHaveAttribute("data-goal-id", projection.goalId);
    await expect(workspace).toHaveAttribute("data-scheme-id", projection.schemeId);

    const researchPath = page.getByTestId("research-path");
    await expect(researchPath).toBeVisible();
    await expect(researchPath).toHaveAttribute("data-run-id", projection.runId);
    const renderedTasks = page.getByTestId("research-task");
    await expect(renderedTasks).toHaveCount(projection.taskIds.length);
    const renderedTaskIds = await renderedTasks.evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute("data-task-id"))
    );
    expect(new Set(renderedTaskIds)).toEqual(new Set(projection.taskIds));
    for (const node of await renderedTasks.all()) {
      await expect(node).toHaveAttribute("data-run-id", projection.runId);
    }

    await expect(page.getByRole("button", { name: SECOND_START_NAME })).toHaveCount(0);
    await page.waitForTimeout(300);
    assertNoSecondStartRequest(ledger.requests);
    expect(ledger.requestsFor("POST", "/api/research-runs")).toHaveLength(1);

    const sources = await loadedFrontendSources(page, request);
    const sourceText = sources.map((entry) => entry.source).join("\n");
    assertNoDemoFallback(sourceText, "reachable production module graph");
    expect(findFrontendFinancialAuthority(sources)).toEqual([]);
    assertNoDemoFallback(await visibleBodyText(page), "Run Workspace DOM");
    ledger.assertNoRuntimeFailures();

    journey = Object.freeze({ draft, confirmResult, projection });
  });

  test("VS01-FE-008 stale and wrong-resource state is quarantined", async ({ page }) => {
    expect(journey, "happy-path journey must establish the exact current Run").toBeTruthy();
    const ledger = new BrowserEvidenceLedger(page);
    const current = journey.projection;
    const mixedRoute = appendQuery(`/runs/${encodeURIComponent(current.runId)}`, {
      object: current.objectId,
      task: scenario.foreign.taskId
    });
    const currentProjectionResponsePromise = page.waitForResponse((response) =>
      response.request().method() === "GET" && pathnameOf(response.url()) === projectionPath(current.runId)
    ).catch(() => null);
    await page.goto(mixedRoute);
    const currentProjectionResponse = await currentProjectionResponsePromise;
    if (currentProjectionResponse) expect(currentProjectionResponse.ok()).toBe(true);

    const quarantine = page.getByTestId("identity-quarantine");
    await expect(quarantine).toBeVisible();
    await expect(quarantine).toHaveAttribute("data-reason", /^(?:IDENTITY_MISMATCH|NOT_FOUND|UNAVAILABLE)$/);
    await expect(page).toHaveURL(new RegExp(`/runs/${encodeURIComponent(current.runId)}`));
    const body = await visibleBodyText(page);
    expect(body).not.toContain(scenario.foreign.objectId);
    expect(body).not.toContain(scenario.foreign.runId);
    expect(body).not.toContain(scenario.foreign.taskId);
    for (const sentinel of scenario.foreign.sentinels) expect(body).not.toContain(sentinel);
    expect(ledger.requests.some((request) => request.pathname.includes(encodeURIComponent(scenario.foreign.runId)))).toBe(false);
    expect(ledger.apiMutations()).toEqual([]);

    const staleOracle = admitContextProjection(
      { runId: current.runId },
      {
        requestEpoch: 1,
        objectId: scenario.foreign.objectId,
        runId: scenario.foreign.runId,
        projection: { runId: scenario.foreign.runId }
      },
      { currentRequestEpoch: 2, objectId: current.objectId, runId: current.runId }
    );
    expect(staleOracle).toEqual({ accepted: false, reason: "STALE_RESPONSE", projection: { runId: current.runId } });
    await expect(page.getByTestId("run-workspace")).toHaveAttribute("data-run-id", current.runId);
    assertNoDemoFallback(body, "wrong-resource DOM");
    ledger.assertNoRuntimeFailures();
  });

  test("VS01-FE-009 typed missing-resource error preserves route; retry/dismiss never substitute", async ({ page }) => {
    const ledger = new BrowserEvidenceLedger(page);
    const missingRoute = `/runs/${encodeURIComponent(scenario.missingRunId)}`;
    const errorResponsePromise = page.waitForResponse((response) => {
      const path = pathnameOf(response.url());
      return response.request().method() === "GET"
        && (path === runPath(scenario.missingRunId) || path === projectionPath(scenario.missingRunId))
        && response.status() >= 400;
    });
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
    const bodyBeforeRetry = await visibleBodyText(page);
    expect(bodyBeforeRetry).not.toContain(scenario.object.objectId);
    expect(bodyBeforeRetry).not.toContain(scenario.foreign.runId);
    assertNoDemoFallback(bodyBeforeRetry, "typed error DOM");

    const failedPath = pathnameOf(errorResponse.url());
    const retryResponsePromise = page.waitForResponse((response) =>
      response.request().method() === "GET" && pathnameOf(response.url()) === failedPath
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
    ledger.assertNoRuntimeFailures();
  });

  test("VS01-FE-010..012 backend unavailable shows an error and cannot reach Demo or financial authority", async ({ page, request }) => {
    const ledger = new BrowserEvidenceLedger(page);
    await page.goto(`${scenario.backendUnavailableFrontendUrl}/new`);
    const alert = await waitForTypedError(page);
    await expect(alert).toBeVisible();
    await expect(page.getByTestId("research-object-option")).toHaveCount(0);

    const body = await visibleBodyText(page);
    assertNoDemoFallback(body, "backend-unavailable DOM");
    expect(body).not.toContain(scenario.object.objectId);
    expect(body).not.toContain(scenario.object.symbol);
    expect(body).not.toContain(scenario.object.companyName);
    const hadUnavailableBackend = ledger.requestFailures.length > 0
      || ledger.responses.some((response) => response.status >= 500);
    expect(hadUnavailableBackend, "the scenario must prove the backend was actually unavailable").toBe(true);
    expect(ledger.responses.some((response) => response.status >= 200 && response.status < 300)).toBe(false);

    const sources = await loadedFrontendSources(page, request);
    assertNoDemoFallback(sources.map((entry) => entry.source).join("\n"), "unavailable production module graph");
    expect(findFrontendFinancialAuthority(sources)).toEqual([]);
    ledger.assertNoRuntimeFailures();
  });
});
