"use strict";

const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="studio-token"]').content;
const modes = Array.from(document.querySelectorAll("[data-mode]"));
const video = $("video");
const scrub = $("scrub");
const track = $("timeline-track");
const preview = $("preview-media");
const pathDialog = $("path-dialog");
const jobDialog = $("job-dialog");

const state = {
  ready: false, importing: false, clips: [], selected: null, excluded: new Set(),
  mode: "cut", ranges: new Map(), audio: new Map(), explicitName: false,
  position: 0, frameMode: false, loaded: false, job: null, sending: false,
};
const modeNames = {cut: "자르기", concat: "이어 붙이기", shorts: "쇼츠"};
const cutHints = {
  fast: "재인코딩 없이 저장합니다. 시작점은 키프레임에 맞춰질 수 있어요.",
  precise: "지정한 시간에 맞춰 자르고 H.264로 다시 인코딩합니다.",
  split: "지정 위치의 앞뒤를 각각 저장합니다. 뒷부분의 시작점은 키프레임에 맞춰질 수 있어요.",
};
const timeFormat = new Intl.NumberFormat("en", {minimumIntegerDigits: 2, useGrouping: false});
let frameTimer;
let pollTimer;

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const use = document.createElementNS(svg.namespaceURI, "use");
  svg.setAttribute("aria-hidden", "true");
  use.setAttribute("href", "#i-" + name);
  svg.append(use);
  return svg;
}

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function clip() {
  return state.clips.find((item) => item.id === state.selected);
}

function selectedForConcat() {
  return state.clips.filter((item) => !state.excluded.has(item.id));
}

function formatTime(value, decimals = true) {
  const total = Math.max(0, Math.round(value * 1000));
  const aggregate = Math.floor(total / 1000);
  const base = [
    Math.floor(aggregate / 3600),
    Math.floor(aggregate / 60) % 60,
    aggregate % 60,
  ].map((part) => timeFormat.format(part)).join(":");
  return decimals ? base + "." + String(total % 1000).padStart(3, "0") : base;
}

function readTime(text) {
  const value = text.trim().replace(",", ".");
  if (/^\d+(?:\.\d+)?$/.test(value)) return Number(value);
  if (!/^\d+(?::\d{1,2}){1,2}(?:\.\d+)?$/.test(value)) return NaN;
  const parts = value.split(":").map(Number);
  if (parts.slice(1).some((part) => part >= 60)) return NaN;
  return parts.reduce((total, part) => total * 60 + part);
}

function editingMode() {
  return state.mode === "cut" ? $("cut-mode").value : state.mode;
}

async function api(url, body) {
  const response = await fetch(url, body === undefined ? {} : {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Studio-Token": token},
    body: JSON.stringify(body),
  });
  if (!response.headers.get("Content-Type")?.includes("application/json")) {
    throw new Error("편집기 서버에 연결할 수 없습니다.");
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error);
  return data;
}

function notify(message, isError = false) {
  const toast = element("div", isError ? "notice error" : "notice", message);
  $("notifications").append(toast);
  setTimeout(() => toast.remove(), isError ? 8000 : 3300);
}

function running() {
  return state.sending || state.job?.status === "running";
}

function renderLibrary() {
  const list = $("clip-list");
  const focusedId = list.contains(document.activeElement) ? document.activeElement.dataset.clipId : null;
  const focusType = document.activeElement.type;
  list.replaceChildren();
  for (const item of state.clips) {
    const active = state.selected === item.id;
    const row = element("div", active ? "clip-row selected" : "clip-row");
    const button = element("button", "clip-button");
    button.type = "button";
    button.title = item.name;
    button.dataset.clipId = item.id;
    button.setAttribute("aria-pressed", String(active));
    const thumb = element("span", "thumb");
    if (item.thumbnail) {
      const img = element("img");
      img.alt = "";
      img.src = "/clip/" + item.id + "/thumbnail";
      img.loading = "lazy";
      thumb.append(img);
    } else {
      thumb.append(icon("film"));
    }
    const details = element("span", "clip-text");
    details.append(element("span", "clip-name", item.name),
      element("span", "clip-detail", formatTime(item.duration, false) + " · " + item.height + "p"));
    button.append(thumb, details);
    button.addEventListener("click", () => selectClip(item.id));
    row.append(button);
    if (state.mode === "concat") {
      const checkbox = element("input", "clip-checkbox");
      checkbox.type = "checkbox";
      checkbox.dataset.clipId = item.id;
      checkbox.checked = !state.excluded.has(item.id);
      checkbox.setAttribute("aria-label", item.name + " 이어 붙이기에 포함");
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) state.excluded.delete(item.id);
        else state.excluded.add(item.id);
        renderEstimate();
      });
      row.append(checkbox);
    }
    list.append(row);
    if (focusedId === item.id) {
      (focusType === "checkbox" ? row.querySelector("input") : button)?.focus({preventScroll: true});
    }
  }
  $("clip-count").textContent = state.clips.length;
  $("drop-zone").hidden = state.clips.length > 0;
  const index = state.clips.findIndex((item) => item.id === state.selected);
  $("move-up").disabled = index <= 0;
  $("move-down").disabled = index < 0 || index >= state.clips.length - 1;
  $("remove-clip").disabled = index < 0 || (running() && state.job?.clips.includes(state.selected));
}

function selectClip(id) {
  if (state.selected === id) return;
  state.selected = id;
  state.position = 0;
  state.frameMode = false;
  state.loaded = false;
  clearTimeout(frameTimer);
  video.pause();
  video.removeAttribute("src");
  $("still").removeAttribute("src");
  const item = clip();
  if (item) {
    if (!state.ranges.has(id)) {
      state.ranges.set(id, {start: formatTime(0), end: formatTime(item.duration), split: formatTime(item.duration / 2)});
    }
    video.src = "/clip/" + item.id + "/media";
  }
  video.load();
  scrub.max = item ? item.duration : 1;
  $("empty-monitor").hidden = Boolean(item);
  $("preview-name").textContent = item?.name || "";
  $("preview-name").title = item?.name || "";
  $("source-size").hidden = !item;
  $("source-size").textContent = item ? item.width + " × " + item.height + " · " + item.codec.toUpperCase() : "";
  $("duration").textContent = " / " + formatTime(item?.duration || 0);
  $("ticks").replaceChildren(...[0, .25, .5, .75, 1].map((point) =>
    element("span", "", formatTime(point * (item?.duration || 0), false))));
  refreshTransport();
  resizePreview();
  renderLibrary();
  renderSettings();
}

function resizePreview() {
  const item = clip();
  if (!item) return;
  const monitor = $("monitor");
  const aspect = item.width / item.height;
  const height = Math.min(monitor.clientHeight, monitor.clientWidth / aspect);
  preview.style.height = height + "px";
  preview.style.width = height * aspect + "px";
  $("shorts-guides").style.setProperty("--crop-width", Math.min(100, 100 * 4 / 3 / aspect) + "%");
}

function refreshTransport() {
  const item = clip();
  preview.hidden = !item;
  video.hidden = state.frameMode;
  $("still").hidden = !state.frameMode;
  $("frame-note").hidden = !state.frameMode;
  $("play").disabled = !item || !state.loaded || state.frameMode;
  $("jump-start").disabled = !item;
  $("jump-end").disabled = !item;
  $("fullscreen").disabled = !item;
  scrub.disabled = !item;
  track.classList.toggle("has-clip", Boolean(item));
  $("fullscreen").title = document.fullscreenElement ? "전체 화면 닫기" : "전체 화면";
  $("fullscreen").setAttribute("aria-label", $("fullscreen").title);
  updatePosition(state.position);
  updatePlayButton();
}

function updatePosition(time) {
  const item = clip();
  state.position = Math.max(0, Math.min(item?.duration || 0, time));
  scrub.value = state.position;
  $("play-time").textContent = formatTime(state.position);
  scrub.setAttribute("aria-valuetext", formatTime(state.position));
  track.style.setProperty("--position", (item ? 100 * state.position / item.duration : 0) + "%");
}

function requestFrame() {
  const item = clip();
  if (item) $("still").src = "/clip/" + item.id + "/frame?t=" + state.position.toFixed(3);
}

function seek(time) {
  if (!clip()) return;
  updatePosition(time);
  if (state.frameMode) {
    clearTimeout(frameTimer);
    frameTimer = setTimeout(requestFrame, 110);
  } else if (state.loaded) {
    video.currentTime = Math.min(state.position, Number.isFinite(video.duration) ? video.duration : state.position);
  }
}

function updatePlayButton() {
  const name = video.paused ? "재생" : "일시정지";
  $("play").replaceChildren(icon(video.paused ? "play" : "pause"));
  $("play").title = name;
  $("play").setAttribute("aria-label", name);
}

async function togglePlayback() {
  if (!state.loaded || state.frameMode) return;
  if (!video.paused) {
    video.pause();
    return;
  }
  try {
    await video.play();
  } catch (error) {
    if (error.name !== "AbortError") notify("영상 재생을 시작할 수 없습니다.", true);
  }
}

function suggestName() {
  if (state.explicitName) return;
  const item = clip();
  const stem = item?.name.replace(/\.[^.]+$/, "").replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_") || "영상";
  $("filename").value = state.mode === "concat" ? "이어 붙인 영상" :
    item ? stem + {shorts: "_short", split: "", fast: "_clip", precise: "_clip"}[editingMode()] : "";
}

function audioOptions() {
  const item = clip();
  const audio = $("audio");
  const isShorts = state.mode === "shorts";
  audio.replaceChildren();
  if (!item) {
    audio.add(new Option("영상 선택 후 설정", "none"));
    audio.disabled = true;
    return;
  }
  for (const channel of item.audio) {
    const extra = [channel.title, channel.language === "und" ? "" : channel.language,
      channel.codec.toUpperCase()].filter(Boolean).join(" · ");
    audio.add(new Option("트랙 " + (channel.index + 1) + (extra ? " · " + extra : ""), channel.index));
  }
  if (!isShorts && item.audio.length > 1) audio.add(new Option("모든 오디오 트랙", "all"));
  audio.add(new Option("오디오 없음", "none"));
  audio.disabled = !item.audio.length;
  const index = isShorts ? 1 : 2;
  const defaultTrack = item.audio.length ? String(item.audio.length > index ? index : 0) : "none";
  audio.value = state.audio.get(item.id + state.mode) || defaultTrack;
}

function renderSettings() {
  const item = clip();
  const split = editingMode() === "split";
  $("settings-title").textContent = modeNames[state.mode] + " 설정";
  $("cut-controls").hidden = state.mode !== "cut";
  $("concat-controls").hidden = state.mode !== "concat";
  $("shorts-controls").hidden = state.mode !== "shorts";
  $("range-controls").hidden = state.mode === "concat";
  $("point-actions").hidden = state.mode === "concat";
  $("audio-controls").hidden = state.mode === "concat" || split;
  $("cut-hint").textContent = cutHints[$("cut-mode").value];
  $("shorts-guides").hidden = state.mode !== "shorts" || !item || item.width / item.height <= 4 / 3;
  $("start-label").textContent = split ? "분할 시간" : "시작 시간";
  $("set-start").querySelector("span").textContent = split ? "분할 위치 지정" : "시작 지정";
  $("set-start").disabled = !item;
  $("set-end").disabled = !item;
  $("set-end").hidden = split;
  $("end-field").hidden = split;
  $("start-time").disabled = !item;
  $("end-time").disabled = !item;
  const range = state.ranges.get(state.selected);
  $("start-time").value = (split ? range?.split : range?.start) || formatTime(0);
  $("end-time").value = range?.end || formatTime(0);
  $("file-format").disabled = state.mode === "shorts";
  if (state.mode === "shorts") $("file-format").value = "mp4";
  audioOptions();
  suggestName();
  renderEstimate();
}

function getRange() {
  const item = clip();
  const split = editingMode() === "split";
  const start = readTime($("start-time").value);
  const end = split ? item?.duration : readTime($("end-time").value);
  let message = "";
  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    message = "시:분:초 또는 초 단위로 입력해 주세요.";
  } else if (split && !(start > 0 && start < end)) {
    message = "영상의 시작과 끝 사이를 선택해 주세요.";
  } else if (!split && !(start >= 0 && start < end && end <= item.duration + .0005 && start < item.duration)) {
    message = "시작·종료 시간을 영상 길이 안에서 확인해 주세요.";
  }
  return {start, end, message};
}

function renderEstimate() {
  const item = clip();
  const concat = state.mode === "concat";
  const split = editingMode() === "split";
  const range = item && !concat ? getRange() : null;
  const hasSelection = Boolean(range && !range.message);
  track.classList.toggle("has-selection", hasSelection);
  if (hasSelection) {
    track.style.setProperty("--in", (100 * range.start / item.duration) + "%");
    track.style.setProperty("--out", (100 * Math.min(range.end, item.duration) / item.duration) + "%");
  }
  $("range-error").hidden = !range?.message;
  $("range-error").textContent = range?.message || "";
  const items = concat ? selectedForConcat() : [];
  const count = items.length;
  const estimate = concat && count ? items.reduce((total, current) => total + current.duration, 0)
    : hasSelection ? Math.min(range.end, item.duration) - range.start : null;
  $("estimate-label").textContent = split ? "앞부분 / 뒷부분" : concat && count ? "예상 길이 · " + count + "개" : "예상 길이";
  $("estimate").textContent = estimate === null ? "—" : split
    ? formatTime(range.start, false) + " / " + formatTime(estimate, false) : formatTime(estimate);
  $("export-button").disabled = !state.ready || state.importing || running() ||
    !(concat ? count >= 2 : hasSelection) || !$("filename").value.trim();
}

function keepRange(event) {
  const range = state.ranges.get(state.selected);
  if (!range) return;
  const key = event.target.id === "end-time" ? "end" : editingMode() === "split" ? "split" : "start";
  range[key] = event.target.value;
  renderEstimate();
}

function setPoint(id) {
  if (!clip()) return;
  const field = $(id);
  field.value = formatTime(state.position);
  field.dispatchEvent(new Event("input"));
}

function addClip(item) {
  state.clips.push(item);
  if (!state.selected) selectClip(item.id);
  else {
    renderLibrary();
    renderEstimate();
  }
}

function setImporting(value) {
  state.importing = value;
  for (const id of ["open-button", "open-path", "drop-zone"]) {
    $(id).disabled = !state.ready || value;
  }
  renderEstimate();
}

function upload(file, update) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/api/upload");
    request.setRequestHeader("X-Studio-Token", token);
    request.setRequestHeader("X-File-Name", encodeURIComponent(file.name));
    request.setRequestHeader("Content-Type", "application/octet-stream");
    request.responseType = "json";
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) update(event.loaded / event.total);
    };
    request.onload = () => {
      if (request.status === 201 && request.response) resolve(request.response);
      else reject(new Error(request.response?.error || "가져오기를 완료할 수 없습니다."));
    };
    request.onerror = () => reject(new Error("편집기 서버 연결이 끊어졌습니다."));
    request.send(file);
  });
}

async function importFiles(files) {
  if (!state.ready || state.importing || !files.length) return;
  setImporting(true);
  const status = $("import-progress");
  const description = status.querySelector(".import-description");
  const progress = status.querySelector("progress");
  status.hidden = false;
  try {
    for (const file of files) {
      description.textContent = file.name + " 가져오는 중";
      progress.value = 0;
      try {
        addClip(await upload(file, (fraction) => {
          progress.value = Math.round(fraction * 100);
          if (fraction === 1) description.textContent = file.name + " 분석 중";
        }));
      } catch (error) {
        notify(file.name + " · " + error.message, true);
      }
    }
  } finally {
    status.hidden = true;
    setImporting(false);
  }
}

function moveClip(change) {
  const index = state.clips.findIndex((item) => item.id === state.selected);
  const target = index + change;
  if (index < 0 || target < 0 || target >= state.clips.length) return;
  const [item] = state.clips.splice(index, 1);
  state.clips.splice(target, 0, item);
  renderLibrary();
}

async function removeClip() {
  const id = state.selected;
  if (!id) return;
  try {
    await api("/api/remove", {id});
    const index = state.clips.findIndex((item) => item.id === id);
    if (index < 0) return;
    state.clips.splice(index, 1);
    state.excluded.delete(id);
    state.ranges.delete(id);
    if (state.selected === id) selectClip(state.clips[Math.min(index, state.clips.length - 1)]?.id || null);
    else {
      renderLibrary();
      renderEstimate();
    }
  } catch (error) {
    notify(error.message, true);
  }
}

function showJob(job) {
  const changed = state.job?.id !== job.id || state.job?.status !== job.status;
  state.job = job;
  clearTimeout(pollTimer);
  if (!jobDialog.open) jobDialog.showModal();
  const busy = job.status === "running";
  const done = job.status === "done";
  $("job-title").textContent = busy ? "영상 내보내는 중" : done ? "내보내기 완료" :
    job.status === "cancelled" ? "내보내기 취소" : "내보내기 실패";
  $("job-progress-row").hidden = !busy && !done;
  $("job-progress").value = job.progress;
  $("job-percent").textContent = job.progress + "%";
  $("close-job").hidden = busy;
  $("cancel-job").hidden = !busy;
  $("job-message").textContent = busy ? "FFmpeg가 영상을 처리하고 있습니다." :
    done ? "exports 폴더에 저장했습니다." : job.error;
  $("job-message").classList.toggle("inline-error", job.status === "failed");
  $("output-files").replaceChildren(...job.files.map((file) => {
    const link = element("a", "button secondary");
    link.href = file.url;
    link.download = file.name;
    link.append(icon("download"), file.name);
    return link;
  }));
  renderEstimate();
  if (changed) renderLibrary();
  if (busy) pollTimer = setTimeout(pollJob, 460);
}

async function pollJob() {
  try {
    const job = await api("/api/job");
    if (job) {
      showJob(job);
    } else {
      state.job = null;
      jobDialog.close();
      renderEstimate();
      notify("편집기가 다시 시작되었습니다. 영상을 다시 열어 주세요.", true);
    }
  } catch {
    $("job-message").textContent = "편집기 연결을 다시 확인하고 있습니다.";
    pollTimer = setTimeout(pollJob, 1800);
  }
}

async function exportVideo(event) {
  event.preventDefault();
  if ($("export-button").disabled) return;
  const mode = editingMode();
  const audio = $("audio").value;
  const options = {
    mode, format: $("file-format").value, name: $("filename").value,
    clips: mode === "concat" ? selectedForConcat().map((item) => item.id) : [state.selected],
    audio: /^\d+$/.test(audio) ? Number(audio) : audio,
  };
  if (mode !== "concat") {
    const {start, end} = getRange();
    Object.assign(options, {start, end});
  }
  state.sending = true;
  renderEstimate();
  try {
    $("cancel-job").disabled = false;
    showJob(await api("/api/export", options));
  } catch (error) {
    notify(error.message, true);
  } finally {
    state.sending = false;
    renderEstimate();
  }
}

for (const button of modes) {
  button.addEventListener("click", () => {
    state.mode = button.dataset.mode;
    for (const mode of modes) mode.setAttribute("aria-pressed", String(mode === button));
    renderLibrary();
    renderSettings();
  });
}
$("cut-mode").addEventListener("change", renderSettings);
$("audio").addEventListener("change", (event) => state.audio.set(state.selected + state.mode, event.target.value));
$("filename").addEventListener("input", (event) => {
  state.explicitName = Boolean(event.target.value.trim());
  renderEstimate();
});
$("start-time").addEventListener("input", keepRange);
$("end-time").addEventListener("input", keepRange);
$("set-start").addEventListener("click", () => setPoint("start-time"));
$("set-end").addEventListener("click", () => setPoint("end-time"));
$("move-up").addEventListener("click", () => moveClip(-1));
$("move-down").addEventListener("click", () => moveClip(1));
$("remove-clip").addEventListener("click", removeClip);
$("play").addEventListener("click", togglePlayback);
$("jump-start").addEventListener("click", () => seek(0));
$("jump-end").addEventListener("click", () => seek(clip()?.duration || 0));
$("fullscreen").addEventListener("click", async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await $("monitor").requestFullscreen();
  } catch {
    notify("이 창에서는 전체 화면을 열 수 없습니다.", true);
  }
});
document.addEventListener("fullscreenchange", refreshTransport);
scrub.addEventListener("input", () => seek(Number(scrub.value)));
scrub.addEventListener("keydown", (event) => {
  const action = {ArrowLeft: -1, ArrowDown: -1, ArrowUp: 1, ArrowRight: 1}[event.key];
  if (action) {
    event.preventDefault();
    seek(state.position + action * (event.shiftKey ? .1 : 1));
  }
});
video.addEventListener("loadedmetadata", () => {
  state.loaded = true;
  if (state.position > 0) seek(state.position);
  refreshTransport();
});
video.addEventListener("timeupdate", () => {
  if (state.loaded && !state.frameMode) updatePosition(video.currentTime);
});
for (const name of ["play", "pause", "ended"]) video.addEventListener(name, updatePlayButton);
video.addEventListener("error", () => {
  if (!clip() || !video.getAttribute("src")) return;
  state.frameMode = true;
  refreshTransport();
  requestFrame();
});
new ResizeObserver(resizePreview).observe($("monitor"));

for (const id of ["open-button", "drop-zone"]) $(id).addEventListener("click", () => $("file-input").click());
$("file-input").addEventListener("change", (event) => {
  const files = Array.from(event.target.files);
  event.target.value = "";
  importFiles(files);
});
$("open-path").addEventListener("click", () => {
  $("path-error").hidden = true;
  pathDialog.showModal();
  $("path-input").focus();
});
$("close-path").addEventListener("click", () => pathDialog.close());
$("path-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.importing) return;
  const errorBox = $("path-error");
  const submit = $("submit-path");
  errorBox.hidden = true;
  submit.disabled = true;
  submit.textContent = "분석 중…";
  setImporting(true);
  try {
    addClip(await api("/api/open", {path: $("path-input").value}));
    pathDialog.close();
    $("path-input").value = "";
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
    if (!pathDialog.open && !jobDialog.open) pathDialog.showModal();
  } finally {
    submit.disabled = false;
    submit.textContent = "열기";
    setImporting(false);
  }
});

let dragDepth = 0;
const overlay = $("drop-overlay");
document.addEventListener("dragenter", (event) => {
  if (!event.dataTransfer.types.includes("Files")) return;
  event.preventDefault();
  dragDepth += 1;
  overlay.hidden = !state.ready || state.importing || pathDialog.open || jobDialog.open;
});
document.addEventListener("dragover", (event) => {
  if (!event.dataTransfer.types.includes("Files")) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = overlay.hidden ? "none" : "copy";
});
document.addEventListener("dragleave", (event) => {
  if (!event.dataTransfer.types.includes("Files")) return;
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) overlay.hidden = true;
});
document.addEventListener("drop", (event) => {
  if (!event.dataTransfer.types.includes("Files")) return;
  event.preventDefault();
  dragDepth = 0;
  overlay.hidden = true;
  if (!jobDialog.open && !pathDialog.open) importFiles(Array.from(event.dataTransfer.files));
});
window.addEventListener("blur", () => {
  dragDepth = 0;
  overlay.hidden = true;
});

$("export-form").addEventListener("submit", exportVideo);
$("close-job").addEventListener("click", () => jobDialog.close());
jobDialog.addEventListener("cancel", (event) => {
  if (running()) event.preventDefault();
});
$("cancel-job").addEventListener("click", async () => {
  $("cancel-job").disabled = true;
  try {
    await api("/api/cancel", {id: state.job.id});
  } catch (error) {
    $("cancel-job").disabled = false;
    $("job-message").textContent = error.message;
  }
});
document.addEventListener("keydown", (event) => {
  if (event.defaultPrevented || pathDialog.open || jobDialog.open) return;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "o") {
    event.preventDefault();
    if (!$("open-button").disabled) $("file-input").click();
  } else if (event.code === "Space" && !event.target.closest("button, input, select, textarea, a") &&
             !$("play").disabled) {
    event.preventDefault();
    togglePlayback();
  }
});

async function init() {
  setImporting(false);
  renderSettings();
  selectClip(null);
  $("ticks").replaceChildren(...Array.from({length: 5}, () => element("span", "", "00:00:00")));
  try {
    const workspace = await api("/api/state");
    state.ready = workspace.ready;
    state.clips = workspace.clips;
    if (state.clips.length) selectClip(state.clips[0].id);
    else renderLibrary();
    $("engine-status").textContent = state.ready ? "FFmpeg 연결됨" : "FFmpeg 설치 필요";
    $("engine-lamp").classList.add(state.ready ? "ready" : "error");
    if (workspace.job?.status === "running" || workspace.job?.status === "done") showJob(workspace.job);
  } catch {
    $("engine-lamp").classList.add("error");
    $("engine-status").textContent = "편집기 연결 끊김";
  } finally {
    setImporting(false);
  }
}

init();
