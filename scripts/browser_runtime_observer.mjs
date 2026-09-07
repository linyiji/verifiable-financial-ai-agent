/** Injectable metadata-only observer. No raw response/error text is retained. */
export function installBrowserRuntimeObserver(runId) {
  window.__vfaRuntimeDiagnostics = { enabled: true, runId, records: [], dropped: 0 };
  const data = window.__vfaBrowserObservation = { schema: 'browser-runtime/v2', run_id: runId, origin: performance.timeOrigin, start: performance.now(), records: [], dropped: 0 };
  let connection = 0, hadWorkspace = false, lastRoute = '', error = false;
  const syncRun = () => {
    const candidate = runId ?? window.__researchMeasurement?.run_id;
    if (!/^RUN-[A-Za-z0-9-]+$/.test(candidate ?? '')) return false;
    runId = candidate; data.run_id = candidate; window.__vfaRuntimeDiagnostics.runId = candidate;
    return true;
  };
  const stamp = (kind, fields = {}) => {
    if (!syncRun()) return;
    if (data.records.length >= 5000) { data.dropped++; return; }
    data.records.push({ kind, run_id: runId, monotonic_ms: performance.now(), ...fields });
  };
  const fetchOriginal = window.fetch.bind(window);
  window.fetch = async (...args) => {
    syncRun();
    const raw = typeof args[0] === 'string' ? args[0] : args[0]?.url ?? '';
    const url = new URL(raw, location.href);
    if (url.pathname !== `/api/research-runs/${runId}/events`) return fetchOriginal(...args);
    const id = ++connection;
    const cursor = new Headers(args[1]?.headers ?? args[0]?.headers).get('Last-Event-ID');
    stamp('sse_open_request', { connection: id, cursor: /^\d+$/.test(cursor ?? '') ? Number(cursor) : null });
    let response;
    try { response = await fetchOriginal(...args); }
    catch (failure) { stamp('sse_fetch_failure', { connection: id }); throw failure; }
    stamp('sse_http', { connection: id, status: response.status });
    if (response.ok && response.body) {
      const reader = response.clone().body.getReader();
      void (async () => {
        let buffer = ''; const decoder = new TextDecoder();
        try {
          for (;;) {
            const {done, value} = await reader.read();
            if (done) { stamp('sse_closed', { connection: id }); break; }
            buffer += decoder.decode(value, {stream: true});
            if (buffer.length > 1048576) { stamp('observer_buffer_limit', {connection: id}); await reader.cancel(); break; }
            const frames = buffer.split(/\r?\n\r?\n/); buffer = frames.pop();
            for (const frame of frames) {
              const line = frame.split(/\r?\n/).filter(l => l.startsWith('data:')).map(l => l.slice(5).trim()).join('\n');
              let event; try { event = JSON.parse(line); } catch { continue; }
              if (event.run_id !== runId || !/^EVT-[A-Za-z0-9-]+$/.test(event.event_id) || !Number.isSafeInteger(event.sequence)) continue;
              stamp('sse_receipt', { connection: id, event_id: event.event_id, sequence: event.sequence });
            }
          }
        } catch { stamp('sse_reader_closed_or_aborted', { connection: id }); }
      })();
    }
    return response;
  };
  const seen = new Set();
  const visible = e => { if (!e || !e.getClientRects().length || getComputedStyle(e).visibility === 'hidden') return false; const r = e.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; };
  const rendered = (kind, e) => {
    if (seen.has(kind) || !visible(e)) return;
    requestAnimationFrame(() => requestAnimationFrame(() => { if (visible(e) && !seen.has(kind)) { seen.add(kind); stamp(kind); } }));
  };
  const scan = () => {
    if (!syncRun()) return;
    const route = location.pathname === `/runs/${runId}` ? 'RUN' : location.pathname === `/runs/${runId}/results/report` ? 'REPORT' : 'OTHER';
    if (route !== lastRoute) { stamp('route', { route }); lastRoute = route; }
    if (route === 'OTHER') return;
    const workspace = document.querySelector('[data-testid="run-workspace"]');
    const present = workspace?.dataset.runId === runId;
    if (present && !hadWorkspace) stamp('workspace_present');
    if (!present && hadWorkspace) stamp('workspace_disappeared');
    hadWorkspace = present;
    const retry = document.querySelector('[data-testid="error-retry"]');
    if (visible(retry) && !error) { error = true; stamp('error_ui_onset'); }
    if (!retry && error) { error = false; stamp('error_ui_removed'); }
    if (present) rendered('report_navigable', document.querySelector('[data-testid="open-results-workspace"]'));
    const results = document.querySelector('[data-testid="results-workspace"]');
    const report = results?.querySelector('[data-testid="interactive-research-report"]');
    const summary = report?.querySelector('.report-summary p');
    if (results?.dataset.runId === runId && summary?.textContent.trim() && report.querySelector('.report-key-metrics') && !summary.textContent.includes('当前没有可展示')) rendered('useful_report_dom', summary);
  };
  new MutationObserver(scan).observe(document, {subtree: true, childList: true, attributes: true});
  addEventListener('popstate', scan);
  addEventListener('scroll', scan);
  document.addEventListener('DOMContentLoaded', scan);
}
