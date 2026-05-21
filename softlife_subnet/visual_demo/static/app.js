const appState = {
  demo: null,
  frameIndex: 0,
  playing: false,
  timer: null,
  speedMs: 1050,
};

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  cacheElements();
  bindControls();
  const params = new URLSearchParams(window.location.search);
  const seed = params.get("seed") || "42";
  els.seedInput.value = seed;
  loadDemo(seed);
});

function cacheElements() {
  els.runMeta = document.getElementById("runMeta");
  els.phaseRail = document.getElementById("phaseRail");
  els.seedForm = document.getElementById("seedForm");
  els.seedInput = document.getElementById("seedInput");
  els.roomStage = document.getElementById("roomStage");
  els.robot = document.getElementById("robot");
  els.activeMiner = document.getElementById("activeMiner");
  els.stepLabel = document.getElementById("stepLabel");
  els.playButton = document.getElementById("playButton");
  els.stepButton = document.getElementById("stepButton");
  els.resetButton = document.getElementById("resetButton");
  els.speedRange = document.getElementById("speedRange");
  els.progressFill = document.getElementById("progressFill");
  els.readinessValue = document.getElementById("readinessValue");
  els.objectMeter = document.getElementById("objectMeter");
  els.cleanMeter = document.getElementById("cleanMeter");
  els.efficiencyMeter = document.getElementById("efficiencyMeter");
  els.objectScore = document.getElementById("objectScore");
  els.cleanScore = document.getElementById("cleanScore");
  els.efficiencyScore = document.getElementById("efficiencyScore");
  els.eventText = document.getElementById("eventText");
  els.robotZone = document.getElementById("robotZone");
  els.heldObject = document.getElementById("heldObject");
  els.invalidActions = document.getElementById("invalidActions");
  els.publicState = document.getElementById("publicState");
  els.leaderboard = document.getElementById("leaderboard");
  els.trajectoryList = document.getElementById("trajectoryList");
  els.replayLog = document.getElementById("replayLog");
  els.phases = Array.from(document.querySelectorAll(".phase"));
}

function bindControls() {
  els.seedForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const seed = els.seedInput.value || "42";
    const url = new URL(window.location.href);
    url.searchParams.set("seed", seed);
    window.history.replaceState(null, "", url.toString());
    pause();
    loadDemo(seed);
  });

  els.playButton.addEventListener("click", () => {
    if (appState.playing) {
      pause();
    } else {
      play();
    }
  });

  els.stepButton.addEventListener("click", () => {
    pause();
    stepForward();
  });

  els.resetButton.addEventListener("click", () => {
    pause();
    renderFrame(0);
  });

  els.speedRange.addEventListener("input", () => {
    appState.speedMs = Number(els.speedRange.value);
  });
}

async function loadDemo(seed) {
  els.runMeta.textContent = "Loading validator challenge...";
  document.body.classList.add("loading-demo");
  const response = await fetch(`/api/demo?seed=${encodeURIComponent(seed)}`);
  if (!response.ok) {
    throw new Error(`Failed to load demo data: ${response.status}`);
  }
  appState.demo = await response.json();
  appState.frameIndex = 0;
  renderStaticDemo();
  renderFrame(0);
  document.body.classList.remove("loading-demo");
  setTimeout(play, 450);
}

function renderStaticDemo() {
  const demo = appState.demo;
  els.runMeta.textContent =
    `Seed ${demo.seed} | challenge ${demo.challenge_id} | adapter ${demo.adapter}`;
  els.activeMiner.textContent = demo.active_miner_id;

  for (const item of Array.from(els.roomStage.querySelectorAll(".zone,.object-token"))) {
    item.remove();
  }

  for (const zone of demo.layout) {
    const node = document.createElement("div");
    node.className = `zone zone-${zone.zone}`;
    node.dataset.zone = zone.zone;
    node.style.left = `${zone.x}%`;
    node.style.top = `${zone.y}%`;
    node.style.width = `${zone.w}%`;
    node.style.height = `${zone.h}%`;
    node.innerHTML =
      `<span class="zone-label">${zone.label}</span>` +
      `<span class="zone-dirt">dirt 0.00</span>`;
    els.roomStage.insertBefore(node, els.robot);
  }

  for (const obj of demo.objects) {
    const node = document.createElement("div");
    node.className = `object-token object-${obj.kind}`;
    node.dataset.objectId = obj.object_id;
    node.title = `${obj.display_kind}: target ${zoneLabel(obj.target_zone)}`;
    node.textContent = obj.short_label;
    els.roomStage.appendChild(node);
  }

  renderPublicState();
  renderTrajectoryList();
}

function renderPublicState() {
  const publicState = appState.demo.public_state;
  const objects = publicState.objects
    .map((obj) => `<span class="pill">${labelForKind(obj.kind)} to ${zoneLabel(obj.target_zone)}</span>`)
    .join("");
  const surfaces = publicState.surfaces
    .map((surface) => `<span class="pill">${zoneLabel(surface.zone)} dirt ${surface.dirt_estimate}</span>`)
    .join("");
  els.publicState.innerHTML =
    `<div>${publicState.objects.length} visible objects, ${publicState.surfaces.length} visible dirty surfaces</div>` +
    `<div class="pill-row">${objects}</div>` +
    `<div class="pill-row">${surfaces}</div>`;
}

function renderTrajectoryList() {
  const activeMiner = appState.demo.miners.find((miner) => miner.miner_id === appState.demo.active_miner_id);
  els.trajectoryList.innerHTML = "";
  for (const [index, action] of activeMiner.trajectory.entries()) {
    const item = document.createElement("li");
    item.dataset.step = String(index + 1);
    item.textContent = describeAction(action);
    els.trajectoryList.appendChild(item);
  }
}

function renderFrame(index) {
  const frames = appState.demo.timeline;
  const frameIndex = Math.max(0, Math.min(index, frames.length - 1));
  appState.frameIndex = frameIndex;
  const frame = frames[frameIndex];

  updateZones(frame);
  updateObjects(frame);
  updateRobot(frame);
  updateScores(frame);
  updateEventPanel(frame);
  updateReplayLog(frame);
  updateLeaderboard(frame);
  updatePhases(frame);

  const total = Math.max(1, frame.total_steps);
  els.stepLabel.textContent = `Step ${frame.step} / ${frame.total_steps}`;
  els.progressFill.style.width = `${(frame.step / total) * 100}%`;

  for (const item of Array.from(els.trajectoryList.children)) {
    const active = Number(item.dataset.step) === frame.step;
    item.classList.toggle("active", active);
    if (active) {
      item.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }
}

function updateZones(frame) {
  const surfacesByZone = new Map(frame.surfaces.map((surface) => [surface.zone, surface]));
  for (const zone of appState.demo.layout) {
    const node = els.roomStage.querySelector(`[data-zone="${zone.zone}"]`);
    const surface = surfacesByZone.get(zone.zone);
    const dirt = surface ? surface.dirt : 0;
    node.style.setProperty("--dirt", String(Math.min(1, Math.max(0, dirt))));
    node.classList.toggle("robot-zone", frame.robot_zone === zone.zone);
    const dirtLabel = node.querySelector(".zone-dirt");
    dirtLabel.textContent = surface ? `dirt ${dirt.toFixed(2)}` : "no scored surface";
  }
}

function updateObjects(frame) {
  const grouped = groupObjectsByZone(frame.objects);
  for (const [zone, objects] of grouped.entries()) {
    objects.sort((left, right) => left.object_id.localeCompare(right.object_id));
    objects.forEach((obj, index) => {
      const node = els.roomStage.querySelector(`[data-object-id="${obj.object_id}"]`);
      const point = objectPoint(zone, index, objects.length);
      node.style.setProperty("--move-delay", `${Math.min(index * 24, 120)}ms`);
      node.style.left = `${point.x}%`;
      node.style.top = `${point.y}%`;
      node.classList.toggle("hidden-to-miner", !obj.visible_to_miner);
      node.classList.toggle("held", obj.held);
      node.classList.toggle("at-target", obj.at_target);
    });
  }
}

function updateRobot(frame) {
  const point = zoneCenter(frame.robot_zone);
  els.robot.style.left = `${point.x}%`;
  els.robot.style.top = `${point.y + 5}%`;
}

function updateScores(frame) {
  const score = frame.score;
  els.readinessValue.textContent = score.readiness.toFixed(3);
  els.objectScore.textContent = score.object_score.toFixed(3);
  els.cleanScore.textContent = score.cleanliness_score.toFixed(3);
  els.efficiencyScore.textContent = score.efficiency_score.toFixed(3);
  els.objectMeter.style.width = `${Math.min(100, (score.object_score / 55) * 100)}%`;
  els.cleanMeter.style.width = `${Math.min(100, (score.cleanliness_score / 35) * 100)}%`;
  els.efficiencyMeter.style.width = `${Math.min(100, (score.efficiency_score / 10) * 100)}%`;
}

function updateEventPanel(frame) {
  els.eventText.textContent = frame.event
    ? `Replay ${String(frame.step).padStart(2, "0")}: ${frame.event.message}`
    : "Validator generated the hidden messy room and sent the public state to miners.";
  els.robotZone.textContent = zoneLabel(frame.robot_zone);
  els.heldObject.textContent = frame.held_object_id || "none";
  els.invalidActions.textContent = String(frame.invalid_actions);
}

function updateReplayLog(frame) {
  els.replayLog.innerHTML = "";
  const events = appState.demo.timeline
    .slice(1, frame.step + 1)
    .map((item) => item.event)
    .filter(Boolean);
  for (const event of events.slice(-12)) {
    const item = document.createElement("li");
    item.className = event.action_index === frame.step - 1 ? "active" : "";
    item.textContent = `${event.ok ? "ok" : "invalid"}: ${event.message}`;
    els.replayLog.appendChild(item);
  }
  const active = els.replayLog.querySelector(".active");
  if (active) {
    active.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function updateLeaderboard(frame) {
  const rows = liveLeaderboardRows(frame);
  els.leaderboard.innerHTML = "";
  for (const row of rows) {
    const node = document.createElement("div");
    node.className = "leader-row";
    node.innerHTML =
      `<strong>${row.miner_id}</strong>` +
      `<span>${row.score.toFixed(3)}</span>` +
      `<div class="weight-track"><span style="width:${row.weight * 100}%"></span></div>`;
    els.leaderboard.appendChild(node);
  }
}

function updatePhases(frame) {
  const total = Math.max(1, frame.total_steps);
  const progress = frame.step / total;
  let activePhase = "hidden";
  const complete = new Set();

  if (frame.step === 0) {
    activePhase = "hidden";
  } else if (progress < 0.2) {
    activePhase = "miner";
    complete.add("hidden");
  } else if (progress < 0.82) {
    activePhase = "replay";
    complete.add("hidden");
    complete.add("miner");
  } else if (progress < 1) {
    activePhase = "score";
    complete.add("hidden");
    complete.add("miner");
    complete.add("replay");
  } else {
    activePhase = "weights";
    complete.add("hidden");
    complete.add("miner");
    complete.add("replay");
    complete.add("score");
  }

  for (const phase of els.phases) {
    const name = phase.dataset.phase;
    phase.classList.toggle("active", name === activePhase);
    phase.classList.toggle("complete", complete.has(name));
  }
}

function liveLeaderboardRows(frame) {
  const scores = appState.demo.miners.map((miner) => ({
    miner_id: miner.miner_id,
    score: miner.miner_id === appState.demo.active_miner_id
      ? frame.score.readiness
      : miner.score.readiness,
  }));
  const total = scores.reduce((sum, item) => sum + Math.max(0, item.score), 0) || 1;
  return scores
    .map((item) => ({ ...item, weight: Math.max(0, item.score) / total }))
    .sort((left, right) => right.score - left.score || left.miner_id.localeCompare(right.miner_id));
}

function play() {
  if (!appState.demo || appState.playing) {
    return;
  }
  appState.playing = true;
  els.playButton.textContent = "Pause";
  scheduleNextFrame();
}

function pause() {
  appState.playing = false;
  els.playButton.textContent = "Play";
  if (appState.timer) {
    clearTimeout(appState.timer);
    appState.timer = null;
  }
}

function scheduleNextFrame() {
  if (!appState.playing) {
    return;
  }
  appState.timer = setTimeout(() => {
    if (!stepForward()) {
      pause();
    } else {
      scheduleNextFrame();
    }
  }, appState.speedMs);
}

function stepForward() {
  if (!appState.demo) {
    return false;
  }
  const next = appState.frameIndex + 1;
  if (next >= appState.demo.timeline.length) {
    renderFrame(appState.demo.timeline.length - 1);
    return false;
  }
  renderFrame(next);
  return true;
}

function groupObjectsByZone(objects) {
  const grouped = new Map();
  for (const obj of objects) {
    const zone = obj.display_zone;
    if (!grouped.has(zone)) {
      grouped.set(zone, []);
    }
    grouped.get(zone).push(obj);
  }
  return grouped;
}

function objectPoint(zoneId, index, count) {
  const zone = appState.demo.layout.find((item) => item.zone === zoneId) || appState.demo.layout[0];
  const center = zoneCenter(zone.zone);
  const offsets = [
    { x: -5, y: -3 },
    { x: 5, y: -3 },
    { x: -5, y: 5 },
    { x: 5, y: 5 },
    { x: 0, y: 0 },
    { x: -8, y: 9 },
    { x: 8, y: 9 },
    { x: 0, y: -9 },
  ];
  const offset = offsets[index % offsets.length];
  const spread = count > 4 ? 0.82 : 1;
  return {
    x: clamp(center.x + offset.x * spread, zone.x + 6, zone.x + zone.w - 6),
    y: clamp(center.y + offset.y * spread, zone.y + 8, zone.y + zone.h - 7),
  };
}

function zoneCenter(zoneId) {
  const zone = appState.demo.layout.find((item) => item.zone === zoneId) || appState.demo.layout[0];
  return { x: zone.x + zone.w / 2, y: zone.y + zone.h / 2 };
}

function zoneLabel(zoneId) {
  const zone = appState.demo && appState.demo.layout.find((item) => item.zone === zoneId);
  return zone ? zone.label : zoneId.replaceAll("_", " ");
}

function labelForKind(kind) {
  const labels = {
    towel: "Towel",
    pillow: "Pillow",
    mug: "Cup",
    remote: "Remote",
    shoes: "Shoes",
    trash: "Trash",
    toiletry: "Bottle",
  };
  return labels[kind] || kind;
}

function describeAction(action) {
  if (action.type === "move_to_zone") {
    return `move_to_zone(${zoneLabel(action.zone)})`;
  }
  if (action.type === "move_to_object") {
    return `move_to_object(${action.object_id})`;
  }
  if (action.type === "pick") {
    return `pick(${action.object_id})`;
  }
  if (action.type === "place") {
    return `place(${action.object_id}, ${zoneLabel(action.zone)})`;
  }
  if (action.type === "clean_surface") {
    return `clean_surface(${zoneLabel(action.zone)})`;
  }
  if (action.type === "dispose") {
    return `dispose(${action.object_id})`;
  }
  return action.type;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}
