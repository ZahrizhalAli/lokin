const ui = {
  connectBtn: document.getElementById("connectBtn"),
  muteBtn: document.getElementById("muteBtn"),
  screenBtn: document.getElementById("screenBtn"),
  resetBtn: document.getElementById("resetBtn"),
  statusText: document.getElementById("statusText"),
  statusDot: document.querySelector(".status-dot"),
  hintText: document.getElementById("hintText"),
  signalPill: document.getElementById("signalPill"),
  sessionMeta: document.getElementById("sessionMeta"),
  latencyText: document.getElementById("latencyText"),
  screenStatus: document.getElementById("screenStatus"),
  screenPlaceholder: document.getElementById("screenPlaceholder"),
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

function setStatus(text, level = "idle") {
  ui.statusText.textContent = text;
  ui.statusDot.dataset.status = level;
}

function setHint(text) {
  ui.hintText.textContent = text;
}

function formatDuration(ms) {
  if (!ms) return "--";
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function updateLatency() {
  if (!state.connectedAt) {
    ui.latencyText.textContent = "Audio link: standby";
    return;
  }
  const elapsed = Date.now() - state.connectedAt;
  ui.latencyText.textContent = `Audio link: live for ${formatDuration(elapsed)}`;
}

function setButtons() {
  const isConnected = Boolean(state.pc);
  ui.connectBtn.textContent = "Start Session";
  ui.connectBtn.disabled = isConnected;
  ui.muteBtn.disabled = !isConnected;
  ui.resetBtn.disabled = !isConnected;
  ui.screenBtn.disabled = !isConnected;
  ui.muteBtn.textContent = state.micEnabled ? "Mute Mic" : "Unmute Mic";
  ui.screenBtn.textContent = state.isScreenSharing ? "Stop Share" : "Share Screen";
}

function setScreenUI(active) {
  if (active) {
    ui.screenPlaceholder.style.display = "none";
    ui.screenPreview.style.display = "block";
    ui.screenStatus.textContent = "Sharing";
  } else {
    ui.screenPlaceholder.style.display = "block";
    ui.screenPreview.style.display = "none";
    ui.screenStatus.textContent = "Inactive";
  }
}

function resizeCanvas() {
  const rect = ui.canvas.getBoundingClientRect();
  viz.width = Math.floor(rect.width * viz.dpr);
  viz.height = Math.floor(rect.height * viz.dpr);
  ui.canvas.width = viz.width;
  ui.canvas.height = viz.height;
}

window.addEventListener("resize", () => {
  resizeCanvas();
});

function rms(data) {
  let sum = 0;
  for (let i = 0; i < data.length; i += 1) {
    const v = (data[i] - 128) / 128;
    sum += v * v;
  }
  return Math.sqrt(sum / data.length);
}

function drawVisualization() {
  const { ctx } = viz;
  ctx.clearRect(0, 0, viz.width, viz.height);

  const midX = viz.width / 2;
  const midY = viz.height / 2;

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

  const combinedLevel = Math.min(1, micLevel * 1.4 + outLevel * 1.1);
  const baseRadius = Math.min(viz.width, viz.height) * 0.16;
  const glowRadius = baseRadius + combinedLevel * 120;

  const glow = ctx.createRadialGradient(midX, midY, baseRadius * 0.2, midX, midY, glowRadius);
  glow.addColorStop(0, "rgba(125, 249, 255, 0.55)");
  glow.addColorStop(0.6, "rgba(95, 225, 199, 0.22)");
  glow.addColorStop(1, "rgba(12, 15, 20, 0)");

  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(midX, midY, glowRadius, 0, Math.PI * 2);
  ctx.fill();

  const core = ctx.createRadialGradient(midX, midY, baseRadius * 0.3, midX, midY, baseRadius * 1.4);
  core.addColorStop(0, "rgba(125, 249, 255, 0.9)");
  core.addColorStop(0.7, "rgba(95, 225, 199, 0.55)");
  core.addColorStop(1, "rgba(30, 45, 65, 0.2)");

  ctx.fillStyle = core;
  ctx.beginPath();
  ctx.arc(midX, midY, baseRadius + combinedLevel * 40, 0, Math.PI * 2);
  ctx.fill();

  const barCount = 120;
  const maxBar = Math.min(viz.width, viz.height) * 0.16;
  const innerRadius = baseRadius + 40;

  for (let i = 0; i < barCount; i += 1) {
    const angle = (i / barCount) * Math.PI * 2;
    const micIndex = state.micFreqData
      ? Math.floor((i / barCount) * state.micFreqData.length)
      : 0;
    const outIndex = state.outFreqData
      ? Math.floor((i / barCount) * state.outFreqData.length)
      : 0;
    const micValue = state.micFreqData ? state.micFreqData[micIndex] / 255 : 0;
    const outValue = state.outFreqData ? state.outFreqData[outIndex] / 255 : 0;
    const power = Math.min(1, micValue * 0.7 + outValue * 0.9);
    const barLength = 12 + power * maxBar;

    const x1 = midX + Math.cos(angle) * innerRadius;
    const y1 = midY + Math.sin(angle) * innerRadius;
    const x2 = midX + Math.cos(angle) * (innerRadius + barLength);
    const y2 = midY + Math.sin(angle) * (innerRadius + barLength);

    ctx.strokeStyle = `rgba(125, 249, 255, ${0.15 + power * 0.75})`;
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  }

  const waveData = state.outTimeData || state.micTimeData;
  if (waveData) {
    ctx.strokeStyle = "rgba(255, 158, 125, 0.65)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    const slice = viz.width / waveData.length;
    for (let i = 0; i < waveData.length; i += 1) {
      const v = (waveData[i] - 128) / 128;
      const x = i * slice;
      const y = midY + v * baseRadius * 1.1;
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
  }

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
    setStatus("Mic unavailable", "error");
    setHint("Your browser does not support microphone access.");
    return;
  }

  setStatus("Requesting microphone", "connecting");
  setHint("Grant microphone permission to start the live session.");

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
    const status = state.pc.connectionState;
    if (status === "connected") {
      setStatus("Live", "live");
      state.connectedAt = Date.now();
      ui.signalPill.textContent = state.micEnabled ? "Mic live" : "Mic muted";
    } else if (status === "connecting") {
      setStatus("Connecting", "connecting");
    } else if (status === "disconnected" || status === "failed") {
      setStatus("Disconnected", "error");
      ui.signalPill.textContent = "Mic off";
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

  ui.sessionMeta.textContent = "Negotiating session";
  setStatus("Negotiating", "connecting");

  await negotiate();

  state.micEnabled = true;
  ui.signalPill.textContent = "Mic live";
  ui.sessionMeta.textContent = "Realtime session active";
  setHint("Speak naturally. The assistant responds over audio.");

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
        ui: "Lokin Nebula",
        version: "1.1",
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
    ui.sessionMeta.textContent = "Renegotiating";
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
  ui.signalPill.textContent = state.micEnabled ? "Mic live" : "Mic muted";
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
  ui.sessionMeta.textContent = "Screen sharing active";
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
  ui.sessionMeta.textContent = state.pc ? "Realtime session active" : "Session not started";
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
  ui.remoteAudio.srcObject = null;
  ui.remoteAudio.pause();

  if (state.animationId) {
    cancelAnimationFrame(state.animationId);
    state.animationId = null;
  }

  setStatus("Idle", "idle");
  setHint("Session ended. Tap start to connect again.");
  ui.signalPill.textContent = "Mic off";
  ui.sessionMeta.textContent = "Session not started";
  setScreenUI(false);
  updateLatency();
  setButtons();
}

ui.connectBtn.addEventListener("click", async () => {
  ui.connectBtn.disabled = true;
  try {
    await connectSession();
  } catch (error) {
    console.error(error);
    setStatus("Connection failed", "error");
    setHint("Could not connect. Check server logs and retry.");
    await disconnectSession();
  } finally {
    setButtons();
  }
});

ui.muteBtn.addEventListener("click", toggleMute);
ui.screenBtn.addEventListener("click", () => {
  toggleScreenShare().catch((error) => {
    console.error(error);
  });
});
ui.resetBtn.addEventListener("click", disconnectSession);

setInterval(updateLatency, 1000);
resizeCanvas();
setButtons();
setScreenUI(false);
setStatus("Idle", "idle");
