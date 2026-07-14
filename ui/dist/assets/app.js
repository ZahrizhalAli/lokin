const ui = {
  appRoot: document.getElementById("appRoot"),
  callBtn: document.getElementById("callBtn"),
  muteBtn: document.getElementById("muteBtn"),
  speakerBtn: document.getElementById("speakerBtn"),
  screenBtn: document.getElementById("screenBtn"),
  liveBadge: document.getElementById("liveBadge"),
  statusText: document.getElementById("statusText"),
  timerText: document.getElementById("timerText"),
  hintText: document.getElementById("hintText"),
  botAvatar: document.getElementById("botAvatar"),
  userAvatar: document.getElementById("userAvatar"),
  screenPreview: document.getElementById("screenPreview"),
  remoteAudio: document.getElementById("remoteAudio"),
  canvas: document.getElementById("viz"),
};

const state = {
  pc: null,
  pcId: null,
  localStream: null,
  remoteStream: null,
  dataChannel: null,
  audioContext: null,
  micAnalyser: null,
  outAnalyser: null,
  micTimeData: null,
  outTimeData: null,
  micFreqData: null,
  outFreqData: null,
  pendingCandidates: [],
  pingTimer: null,
  animationId: null,
  connectedAt: null,
  micEnabled: false,
  speakerOn: true,
  screenStream: null,
  screenTrack: null,
  screenTransceiver: null,
  isScreenSharing: false,
};

const viz = {
  ctx: ui.canvas.getContext("2d"),
  dpr: window.devicePixelRatio || 1,
  width: 0,
  height: 0,
};

const NAVY = "#2b3990";
const BAR_COUNT = 48;

function setStatus(text, level = "idle") {
  ui.statusText.textContent = text;
  ui.liveBadge.dataset.status = level;
}

function setHint(text) {
  ui.hintText.textContent = text;
}

function formatDuration(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function updateTimer() {
  if (!state.connectedAt) {
    ui.timerText.textContent = "";
    return;
  }
  ui.timerText.textContent = formatDuration(Date.now() - state.connectedAt);
}

function setButtons() {
  const isConnected = Boolean(state.pc);

  ui.callBtn.classList.toggle("end", isConnected);
  ui.callBtn.classList.toggle("start", !isConnected);
  ui.callBtn.setAttribute("aria-label", isConnected ? "End interview" : "Start interview");

  ui.muteBtn.disabled = !isConnected;
  ui.speakerBtn.disabled = !isConnected;
  ui.screenBtn.disabled = !isConnected;

  ui.muteBtn.dataset.on = String(state.micEnabled);
  ui.muteBtn.setAttribute("aria-label", state.micEnabled ? "Mute microphone" : "Unmute microphone");
  ui.speakerBtn.dataset.on = String(state.speakerOn);
  ui.speakerBtn.setAttribute("aria-label", state.speakerOn ? "Mute speaker" : "Unmute speaker");
  ui.screenBtn.classList.toggle("active", state.isScreenSharing);
  ui.screenBtn.setAttribute("aria-label", state.isScreenSharing ? "Stop sharing screen" : "Share screen");
}

function setScreenUI(active) {
  ui.appRoot.dataset.sharing = String(active);
  // The call card resizes when the layout switches, so refit the canvas.
  resizeCanvas();
}

function resizeCanvas() {
  const rect = ui.canvas.getBoundingClientRect();
  viz.width = Math.floor(rect.width * viz.dpr);
  viz.height = Math.floor(rect.height * viz.dpr);
  ui.canvas.width = viz.width;
  ui.canvas.height = viz.height;
  if (!state.animationId) {
    drawIdleViz();
  }
}

window.addEventListener("resize", resizeCanvas);

function rms(data) {
  let sum = 0;
  for (let i = 0; i < data.length; i += 1) {
    const v = (data[i] - 128) / 128;
    sum += v * v;
  }
  return Math.sqrt(sum / data.length);
}

function drawBars(levels) {
  const { ctx } = viz;
  ctx.clearRect(0, 0, viz.width, viz.height);

  const gap = 3 * viz.dpr;
  const barWidth = Math.max(2 * viz.dpr, (viz.width - gap * (BAR_COUNT - 1)) / BAR_COUNT);
  const midY = viz.height / 2;
  const maxHalf = viz.height / 2 - 2 * viz.dpr;
  const minHalf = 2 * viz.dpr;

  for (let i = 0; i < BAR_COUNT; i += 1) {
    const level = levels[i] || 0;
    const half = minHalf + level * (maxHalf - minHalf);
    const x = i * (barWidth + gap);

    ctx.fillStyle = NAVY;
    ctx.globalAlpha = 0.35 + level * 0.65;
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(x, midY - half, barWidth, half * 2, barWidth / 2);
    } else {
      ctx.rect(x, midY - half, barWidth, half * 2);
    }
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function drawIdleViz() {
  drawBars(new Array(BAR_COUNT).fill(0));
}

function drawVisualization() {
  let micLevel = 0;
  let outLevel = 0;

  if (state.micAnalyser) {
    state.micAnalyser.getByteTimeDomainData(state.micTimeData);
    state.micAnalyser.getByteFrequencyData(state.micFreqData);
    micLevel = rms(state.micTimeData);
  }

  if (state.outAnalyser) {
    state.outAnalyser.getByteTimeDomainData(state.outTimeData);
    state.outAnalyser.getByteFrequencyData(state.outFreqData);
    outLevel = rms(state.outTimeData);
  }

  const levels = new Array(BAR_COUNT);
  for (let i = 0; i < BAR_COUNT; i += 1) {
    // Sample the lower ~70% of the spectrum, where voice energy lives.
    let micValue = 0;
    let outValue = 0;
    if (state.micFreqData) {
      micValue = state.micFreqData[Math.floor((i / BAR_COUNT) * state.micFreqData.length * 0.7)] / 255;
    }
    if (state.outFreqData) {
      outValue = state.outFreqData[Math.floor((i / BAR_COUNT) * state.outFreqData.length * 0.7)] / 255;
    }
    levels[i] = Math.min(1, micValue * 0.8 + outValue);
  }
  drawBars(levels);

  ui.botAvatar.classList.toggle("speaking", outLevel > 0.04);
  ui.userAvatar.classList.toggle("speaking", state.micEnabled && micLevel > 0.04);

  state.animationId = requestAnimationFrame(drawVisualization);
}

function initAudioContext() {
  if (state.audioContext) return;
  state.audioContext = new AudioContext();
}

function attachAnalyser(stream, kind) {
  if (!state.audioContext) return;
  const source = state.audioContext.createMediaStreamSource(stream);
  const analyser = state.audioContext.createAnalyser();
  analyser.fftSize = 2048;
  source.connect(analyser);

  const timeData = new Uint8Array(analyser.fftSize);
  const freqData = new Uint8Array(analyser.frequencyBinCount);

  if (kind === "mic") {
    state.micAnalyser = analyser;
    state.micTimeData = timeData;
    state.micFreqData = freqData;
  } else {
    state.outAnalyser = analyser;
    state.outTimeData = timeData;
    state.outFreqData = freqData;
  }
}

async function connectSession() {
  if (!navigator.mediaDevices?.getUserMedia) {
    setStatus("No mic", "error");
    setHint("Your browser does not support microphone access.");
    return;
  }

  setStatus("Mic…", "connecting");
  setHint("Grant microphone permission to start the interview.");

  try {
    state.localStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    state.localStream.getAudioTracks().forEach((track) => {
      track.enabled = true;
    });
  } catch (error) {
    setStatus("Mic denied", "error");
    setHint("Microphone permission is required to connect.");
    console.error(error);
    return;
  }

  initAudioContext();
  await state.audioContext.resume();
  attachAnalyser(state.localStream, "mic");

  state.pc = new RTCPeerConnection({
    iceServers: [],
  });

  state.remoteStream = new MediaStream();
  ui.remoteAudio.srcObject = state.remoteStream;
  ui.remoteAudio.muted = !state.speakerOn;

  state.pc.ontrack = (event) => {
    const [stream] = event.streams;
    if (stream) {
      stream.getTracks().forEach((track) => {
        state.remoteStream.addTrack(track);
      });
    } else if (event.track) {
      state.remoteStream.addTrack(event.track);
    }
    ui.remoteAudio.play().catch(() => {});
    if (state.audioContext && !state.outAnalyser) {
      attachAnalyser(state.remoteStream, "out");
    }
  };

  state.pc.onconnectionstatechange = () => {
    const status = state.pc?.connectionState;
    if (status === "connected") {
      setStatus("Live", "live");
      state.connectedAt = Date.now();
    } else if (status === "connecting") {
      setStatus("Connecting", "connecting");
    } else if (status === "disconnected" || status === "failed") {
      setStatus("Dropped", "error");
    }
  };

  state.pc.onicecandidate = (event) => {
    if (!event.candidate) return;
    if (state.pcId) {
      sendIceCandidates([event.candidate]);
    } else {
      state.pendingCandidates.push(event.candidate);
    }
  };

  state.dataChannel = state.pc.createDataChannel("app");
  state.dataChannel.onopen = () => {
    startPing();
  };
  state.dataChannel.onmessage = (event) => {
    handleDataMessage(event.data);
  };

  state.localStream.getTracks().forEach((track) => {
    state.pc.addTrack(track, state.localStream);
  });

  state.screenTransceiver = state.pc.addTransceiver("video", { direction: "sendonly" });

  setStatus("Connecting", "connecting");

  await negotiate();

  state.micEnabled = true;
  setHint("Speak naturally. Lokin responds over audio. Share your screen when asked to code.");

  if (!state.animationId) {
    resizeCanvas();
    drawVisualization();
  }

  setButtons();
}

async function negotiate({ restart = false } = {}) {
  const offer = await state.pc.createOffer({
    offerToReceiveAudio: true,
    iceRestart: restart,
  });
  await state.pc.setLocalDescription(offer);

  const response = await fetch("/api/offer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sdp: state.pc.localDescription.sdp,
      type: state.pc.localDescription.type,
      pc_id: state.pcId || undefined,
      restart_pc: restart || undefined,
      request_data: {
        ui: "Lokin Interview",
        version: "2.0",
      },
    }),
  });

  if (!response.ok) {
    throw new Error(`Offer failed: ${response.status}`);
  }

  const answer = await response.json();
  state.pcId = answer.pc_id;
  await state.pc.setRemoteDescription({ type: answer.type, sdp: answer.sdp });

  if (state.pendingCandidates.length > 0) {
    const candidates = state.pendingCandidates.slice();
    state.pendingCandidates = [];
    sendIceCandidates(candidates);
  }
}

async function sendIceCandidates(candidates) {
  if (!state.pcId || candidates.length === 0) return;
  const payloadCandidates = candidates
    .filter((candidate) => candidate && candidate.candidate)
    .filter((candidate) => candidate.sdpMid !== null && candidate.sdpMLineIndex !== null)
    .map((candidate) => ({
      candidate: candidate.candidate,
      sdp_mid: candidate.sdpMid,
      sdp_mline_index: candidate.sdpMLineIndex,
    }));

  if (payloadCandidates.length === 0) return;
  await fetch("/api/offer", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pc_id: state.pcId,
      candidates: payloadCandidates,
    }),
  });
}

function startPing() {
  if (state.pingTimer) clearInterval(state.pingTimer);
  state.pingTimer = setInterval(() => {
    if (state.dataChannel && state.dataChannel.readyState === "open") {
      state.dataChannel.send(`ping ${Date.now()}`);
    }
  }, 1500);
}

function handleDataMessage(payload) {
  if (typeof payload !== "string") return;
  let message;
  try {
    message = JSON.parse(payload);
  } catch (_) {
    return;
  }

  if (message.type === "signalling" && message.message?.type === "renegotiate") {
    negotiate({ restart: false }).catch((error) => {
      console.error(error);
    });
  }
}

function toggleMute() {
  if (!state.localStream) return;
  state.micEnabled = !state.micEnabled;
  state.localStream.getAudioTracks().forEach((track) => {
    track.enabled = state.micEnabled;
  });
  setButtons();
}

function toggleSpeaker() {
  state.speakerOn = !state.speakerOn;
  ui.remoteAudio.muted = !state.speakerOn;
  setButtons();
}

async function startScreenShare() {
  if (!state.pc) return;
  if (!navigator.mediaDevices?.getDisplayMedia) {
    setHint("Screen sharing is not supported in this browser.");
    return;
  }

  try {
    state.screenStream = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: false,
    });
  } catch (error) {
    console.error(error);
    setHint("Screen share permission was denied.");
    return;
  }

  const [track] = state.screenStream.getVideoTracks();
  if (!track) return;

  state.screenTrack = track;
  ui.screenPreview.srcObject = state.screenStream;
  ui.screenPreview.play().catch(() => {});

  track.onended = () => {
    stopScreenShare();
  };

  if (state.screenTransceiver) {
    await state.screenTransceiver.sender.replaceTrack(track);
  } else {
    state.screenTransceiver = state.pc.addTransceiver(track, { direction: "sendonly" });
  }

  state.isScreenSharing = true;
  setScreenUI(true);
  setHint("Lokin can see your screen now.");
  setButtons();

  await negotiate({ restart: false });
}

async function stopScreenShare({ renegotiate = true } = {}) {
  if (state.screenTrack) {
    state.screenTrack.onended = null;
    state.screenTrack.stop();
  }

  if (state.screenStream) {
    state.screenStream.getTracks().forEach((track) => track.stop());
  }

  if (state.screenTransceiver) {
    await state.screenTransceiver.sender.replaceTrack(null);
  }

  state.screenStream = null;
  state.screenTrack = null;
  state.isScreenSharing = false;
  ui.screenPreview.srcObject = null;
  setScreenUI(false);
  if (state.pc) {
    setHint("Screen sharing stopped.");
  }
  setButtons();

  if (state.pc && renegotiate) {
    await negotiate({ restart: false });
  }
}

async function toggleScreenShare() {
  if (state.isScreenSharing) {
    await stopScreenShare({ renegotiate: false });
  } else {
    await startScreenShare();
  }
}

async function disconnectSession() {
  if (state.pingTimer) clearInterval(state.pingTimer);
  state.pingTimer = null;

  if (state.isScreenSharing) {
    await stopScreenShare();
  }

  if (state.dataChannel) {
    state.dataChannel.close();
  }

  if (state.pc) {
    state.pc.getSenders().forEach((sender) => {
      if (sender.track) sender.track.stop();
    });
    state.pc.close();
  }

  if (state.localStream) {
    state.localStream.getTracks().forEach((track) => track.stop());
  }

  state.pc = null;
  state.pcId = null;
  state.dataChannel = null;
  state.localStream = null;
  state.remoteStream = null;
  state.screenTransceiver = null;
  state.micEnabled = false;
  state.connectedAt = null;
  state.pendingCandidates = [];
  state.outAnalyser = null;
  state.outFreqData = null;
  state.outTimeData = null;
  state.micAnalyser = null;
  state.micFreqData = null;
  state.micTimeData = null;
  ui.remoteAudio.srcObject = null;
  ui.remoteAudio.pause();

  if (state.animationId) {
    cancelAnimationFrame(state.animationId);
    state.animationId = null;
  }

  ui.botAvatar.classList.remove("speaking");
  ui.userAvatar.classList.remove("speaking");

  setStatus("Idle", "idle");
  setHint("Interview ended. Press the green button to start again.");
  setScreenUI(false);
  updateTimer();
  drawIdleViz();
  setButtons();
}

ui.callBtn.addEventListener("click", async () => {
  if (state.pc) {
    await disconnectSession();
    return;
  }
  ui.callBtn.disabled = true;
  try {
    await connectSession();
  } catch (error) {
    console.error(error);
    setStatus("Failed", "error");
    setHint("Could not connect. Check server logs and retry.");
    await disconnectSession();
  } finally {
    ui.callBtn.disabled = false;
    setButtons();
  }
});

ui.muteBtn.addEventListener("click", toggleMute);
ui.speakerBtn.addEventListener("click", toggleSpeaker);
ui.screenBtn.addEventListener("click", () => {
  toggleScreenShare().catch((error) => {
    console.error(error);
  });
});

setInterval(updateTimer, 1000);
resizeCanvas();
setButtons();
setScreenUI(false);
setStatus("Idle", "idle");
