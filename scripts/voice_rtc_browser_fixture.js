/* Local browser acceptance input only. The product UI and LiveKit path stay real. */
(() => {
  if (window.__vefinAutomationAudio) return;
  const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  const context = new AudioContext({ sampleRate: 48000 });
  let destination = context.createMediaStreamDestination();
  // A continuous zero source keeps the synthetic microphone clock alive between files.
  // It adds no speech and never touches the remote response audio.
  const silence = context.createConstantSource();
  silence.offset.value = 0;
  silence.connect(destination);
  silence.start();
  const events = [];
  window.addEventListener("vefin-voice-media", event => events.push(event.detail));
  navigator.mediaDevices.getUserMedia = async constraints => {
    if (constraints && constraints.audio) {
      await context.resume();
      if (destination.stream.getAudioTracks()[0].readyState !== "live")
        { destination = context.createMediaStreamDestination(); silence.disconnect(); silence.connect(destination); }
      return destination.stream;
    }
    return original(constraints);
  };
  window.__vefinAutomationAudio = {
    events,
    async playBase64(base64) {
      await context.resume();
      const bytes = Uint8Array.from(atob(base64), char => char.charCodeAt(0));
      const audio = await context.decodeAudioData(bytes.buffer);
      const source = context.createBufferSource();
      source.buffer = audio;
      source.connect(destination);
      const startedAt = Date.now();
      source.start();
      await new Promise(resolve => { source.onended = resolve; });
      return { startedAt, endedAt: Date.now(), durationSeconds: audio.duration,
        contextState: context.state, trackReadyState: destination.stream.getAudioTracks()[0].readyState };
    },
  };
})();

/* Browser-only acceptance instrumentation; no product source is changed. */
(() => {
  if (window.__vefinOutputProbe) return;
  const context = new AudioContext();
  const outputs = [];
  const events = [];
  let nextId = 0;
  const attach = element => {
    if (!element.matches('audio[data-vefin-worker-audio]')) return;
    const stream = element.srcObject;
    if (!(stream instanceof MediaStream)) return;
    if (element.__vefinProbedStream === stream) return;
    element.__vefinProbedStream = stream;
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    context.createMediaStreamSource(stream).connect(analyser);
    const gain = context.createGain(); gain.gain.value = 0;
    analyser.connect(gain).connect(context.destination);
    const samples = new Float32Array(analyser.fftSize);
    const entry = { id: ++nextId, trackSid: element.dataset.vefinTrackSid,
      attachedAt: Date.now(), intervals: [], playingEvents: [], removedAt: null };
    outputs.push(entry);
    element.addEventListener('playing', () => entry.playingEvents.push({ kind: 'playing', at: Date.now() }));
    element.addEventListener('pause', () => entry.playingEvents.push({ kind: 'pause', at: Date.now() }));
    const timer = setInterval(() => {
      if (!element.isConnected || element.srcObject !== stream) {
        entry.removedAt = Date.now(); clearInterval(timer); return;
      }
      analyser.getFloatTimeDomainData(samples);
      let max = 0; for (const sample of samples) max = Math.max(max, Math.abs(sample));
      const now = Date.now();
      if (max > 0.006) {
        const last = entry.intervals[entry.intervals.length - 1];
        if (!last || now - last.lastAt > 400) entry.intervals.push({ firstAt: now, lastAt: now, peak: max });
        else { last.lastAt = now; last.peak = Math.max(last.peak, max); }
      }
    }, 20);
  };
  const observer = new MutationObserver(() => document.querySelectorAll('audio[data-vefin-worker-audio]').forEach(attach));
  observer.observe(document.body, { childList: true, subtree: true });
  document.querySelectorAll('audio[data-vefin-worker-audio]').forEach(attach);
  window.addEventListener('vefin-voice-media', event => events.push(event.detail));
  window.__vefinOutputProbe = { outputs, events, resume: () => context.resume(),
    state: () => context.state, stop: () => { observer.disconnect(); context.close(); } };
  void context.resume();
})();

({inputInstalled:!!window.__vefinAutomationAudio,outputInstalled:!!window.__vefinOutputProbe,at:Date.now()});
