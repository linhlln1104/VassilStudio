import { createApi } from "./src/api.js";
import { createHttp } from "./src/http.js";
import { state } from "./src/state.js";
import { $, formatBytes, formatDuration, showToast, withBusy } from "./src/ui.js";

const api = createApi(getApiKey);
const { authFetch, ensureOk, fetchJson, withAuthQuery } = createHttp(getApiKey);
const API_KEY_STORAGE_KEY = "vassil.apiKey";
const LEGACY_API_KEY_STORAGE_KEY = "vvoice.apiKey";

document.addEventListener("DOMContentLoaded", () => {
  loadApiKey();
  wireEvents();
  refreshRuntime();
  refreshVoices();
  refreshImportCandidates();
  refreshAsrJobs();
  refreshTtsJobs();
  disableDownload();
  handleInitialHash();
  if (window.lucide) {
    window.lucide.createIcons();
  }
});

function wireEvents() {
  $("#saveApiKeyButton").addEventListener("click", saveApiKey);
  $("#clearApiKeyButton").addEventListener("click", clearApiKey);
  $("#refreshStatusButton").addEventListener("click", refreshRuntime);
  $("#warmupButton").addEventListener("click", warmup);
  $("#refreshVoicesButton").addEventListener("click", refreshVoices);
  $("#voiceSearchInput").addEventListener("input", updateVoiceSearch);
  $("#voiceForm").addEventListener("submit", createVoice);
  $("#ttsForm select[name='voice_id']").addEventListener("change", selectVoice);
  $("#ttsForm textarea[name='text']").addEventListener("input", updateScriptCharCount);
  $("#ttsForm input[name='num_steps']").addEventListener("input", updateRangeLabels);
  $("#ttsForm input[name='speed']").addEventListener("input", updateRangeLabels);
  $("#ttsForm").addEventListener("submit", synthesize);
  $("#queueTtsJobButton").addEventListener("click", queueTtsJob);
  $("#quickImportButton").addEventListener("click", importFirstCandidate);
  $("#mobileVoiceButton").addEventListener("click", focusVoiceWorkflow);
  $("#mobileSynthesizeButton").addEventListener("click", () => $("#ttsForm").requestSubmit());
  $("#mobileQueueButton").addEventListener("click", queueTtsJob);
  $("#cleanupTtsJobsButton").addEventListener("click", cleanupTtsJobs);
  $("#refreshTtsJobsButton").addEventListener("click", refreshTtsJobs);
  $("#asrForm").addEventListener("submit", transcribe);
  $("#queueAsrJobButton").addEventListener("click", queueAsrJob);
  $("#cleanupAsrJobsButton").addEventListener("click", cleanupAsrJobs);
  $("#refreshAsrJobsButton").addEventListener("click", refreshAsrJobs);
  $("#startLiveButton").addEventListener("click", startRealtime);
  $("#stopLiveButton").addEventListener("click", stopRealtime);
  $("#clearLiveButton").addEventListener("click", clearLiveTranscript);
  $("#settingsTabButton").addEventListener("click", () => activateSettingsPanel("settings"));
  $("#historyTabButton").addEventListener("click", () => activateSettingsPanel("history"));
  window.addEventListener("hashchange", scrollToCurrentHashTarget);

  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.tab));
  });
  document.querySelectorAll(".nav-link[data-tab]").forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.tab));
  });
  document.querySelectorAll(".prompt-chip[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => usePrompt(button.dataset.prompt));
  });
  updateScriptCharCount();
  updateRangeLabels();
}

async function refreshRuntime() {
  try {
    const [health, modelStatus] = await Promise.all([
      fetchJson(api.health),
      fetchJson(api.modelStatus),
    ]);
    $("#runtimeStatus").textContent =
      `provider=${health.provider} | ready=${modelStatus.ready} | ` +
      `asr=${health.asr_loaded ? "loaded" : "idle"} | ` +
      `tts=${health.tts_loaded ? "loaded" : "idle"}`;
    updateRuntimeInsights(health, modelStatus);
  } catch (error) {
    $("#runtimeStatus").textContent = "runtime unavailable";
    setInsight("#asrInsightCard", "#asrInsightStatus", "error", "Unavailable");
    setInsight("#ttsInsightCard", "#ttsInsightStatus", "error", "Unavailable");
    showToast(error.message, true);
  }
}

async function warmup() {
  const button = $("#warmupButton");
  withBusy(button, async () => {
    await fetchJson(api.warmup, { method: "POST" });
    await refreshRuntime();
    showToast("Runtime loaded");
  });
}

async function refreshVoices() {
  const voices = await fetchJson(api.voices);
  state.voices = Array.isArray(voices) ? voices : voices.value || [];

  if (!state.voices.some((voice) => voice.voice_id === state.selectedVoiceId)) {
    state.selectedVoiceId = state.voices[0]?.voice_id || "";
  }
  if (!state.voices.some((voice) => voice.voice_id === state.editingVoiceId)) {
    state.editingVoiceId = "";
  }

  renderVoices();
  renderVoiceSelect();
}

async function refreshImportCandidates() {
  try {
    const candidates = await fetchJson(api.voiceImportCandidates);
    state.importCandidates = Array.isArray(candidates) ? candidates : candidates.value || [];
    renderImportCandidates();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function createVoice(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);

  const auto = form.elements.auto_transcribe.checked;
  const referenceText = String(formData.get("reference_text") || "").trim();
  if (!auto && !referenceText) {
    showToast("Reference text is required unless auto transcribe is enabled", true);
    return;
  }

  formData.set("auto_transcribe", auto ? "true" : "false");

  await withBusy([form.querySelector("button[type='submit']"), $("#mobileVoiceButton")], async () => {
    const response = await authFetch(api.voices, { method: "POST", body: formData });
    await ensureOk(response);
    const voice = await response.json();
    state.selectedVoiceId = voice.voice_id;
    form.reset();
    form.elements.name.value = "demo";
    await refreshVoices();
    await refreshImportCandidates();
    focusSynthesisComposer();
    showToast("Voice saved");
  });
}

async function importVoiceCandidate(event, filename) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  formData.set("filename", filename);
  formData.set("auto_transcribe", form.elements.auto_transcribe.checked ? "true" : "false");

  const referenceText = String(formData.get("reference_text") || "").trim();
  if (!form.elements.auto_transcribe.checked && !referenceText) {
    showToast("Reference text is required unless auto transcribe is enabled", true);
    return;
  }

  await withBusy([form.querySelector("button[type='submit']"), $("#mobileVoiceButton")], async () => {
    const response = await authFetch(api.voiceImport, { method: "POST", body: formData });
    await ensureOk(response);
    const voice = await response.json();
    state.selectedVoiceId = voice.voice_id;
    await refreshVoices();
    await refreshImportCandidates();
    focusSynthesisComposer();
    showToast(`Imported ${voice.name}`);
  });
}

async function importFirstCandidate() {
  const candidate = state.importCandidates[0];
  if (!candidate) {
    focusVoiceWorkflow();
    return;
  }

  const formData = new FormData();
  formData.set("filename", candidate.filename);
  formData.set("name", candidate.name || candidate.filename.replace(/\.[^.]+$/, ""));
  formData.set("reference_text", "");
  formData.set("auto_transcribe", "true");

  await withBusy([$("#quickImportButton"), $("#mobileVoiceButton")], async () => {
    const response = await authFetch(api.voiceImport, { method: "POST", body: formData });
    await ensureOk(response);
    const voice = await response.json();
    state.selectedVoiceId = voice.voice_id;
    await refreshVoices();
    await refreshImportCandidates();
    focusSynthesisComposer();
    showToast(`Imported ${voice.name}`);
  });
}

async function deleteVoice(voiceId) {
  await fetchJson(`${api.voices}/${encodeURIComponent(voiceId)}`, { method: "DELETE" });
  if (state.selectedVoiceId === voiceId) {
    state.selectedVoiceId = "";
  }
  if (state.editingVoiceId === voiceId) {
    state.editingVoiceId = "";
  }
  await refreshVoices();
  showToast("Voice deleted");
}

async function updateVoice(event, voiceId) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);

  await withBusy(form.querySelector("button[type='submit']"), async () => {
    const response = await authFetch(api.voice(voiceId), {
      method: "PATCH",
      body: formData,
    });
    await ensureOk(response);
    state.editingVoiceId = "";
    await refreshVoices();
    showToast("Voice updated");
  });
}

async function synthesize(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  const voiceId = formData.get("voice_id");
  if (!voiceId) {
    showToast("Select a voice", true);
    return;
  }

  await withBusy([form.querySelector("button[type='submit']"), $("#mobileSynthesizeButton")], async () => {
    setTtsResultStatus("Generating speech", "ZipVoice is rendering the current script.", "running");
    try {
      const response = await authFetch(api.ttsVoice(voiceId), { method: "POST", body: formData });
      await ensureOk(response);
      const blob = await response.blob();
      revokeCurrentTtsUrl();
      state.ttsUrl = URL.createObjectURL(blob);
      $("#ttsAudio").src = state.ttsUrl;
      $("#ttsAudio").hidden = false;
      $("#downloadLink").href = state.ttsUrl;
      $("#downloadLink").download = `${safeFileName(selectedVoice()?.name || "vassil")}-direct.wav`;
      $("#downloadLink").setAttribute("aria-disabled", "false");
      state.activeTtsJobId = "";
      state.loadedTtsJobId = "";
      const duration =
        response.headers.get("X-Vassil-Duration-Seconds") ||
        response.headers.get("X-VVoice-Duration-Seconds") ||
        "";
      setTtsResultStatus("Speech ready", duration ? `${duration}s generated output` : "Generated output is ready", "ready");
      revealTtsResult();
      showToast(duration ? `Generated ${duration}s` : "Generated speech");
    } catch (error) {
      setTtsResultStatus("Generation failed", error.message, "error");
      throw error;
    }
  });
}

async function queueTtsJob() {
  const form = $("#ttsForm");
  const formData = new FormData(form);
  const voiceId = formData.get("voice_id");
  if (!voiceId) {
    showToast("Select a voice", true);
    return;
  }

  await withBusy([$("#queueTtsJobButton"), $("#mobileQueueButton")], async () => {
    setTtsResultStatus("Queueing job", "Adding this script to the TTS job list.", "running");
    try {
      const response = await authFetch(api.ttsJobVoice(voiceId), {
        method: "POST",
        body: formData,
      });
      await ensureOk(response);
      const job = await response.json();
      state.activeTtsJobId = job.job_id;
      state.loadedTtsJobId = "";
      await refreshTtsJobs();
      startTtsJobPolling();
      activateSettingsPanel("history");
      setTtsResultStatus("Job queued", `Rendering job ${job.job_id.slice(0, 8)} in History.`, "queued");
      showToast("TTS job queued");
    } catch (error) {
      setTtsResultStatus("Queue failed", error.message, "error");
      throw error;
    }
  });
}

async function refreshTtsJobs() {
  try {
    const jobs = await fetchJson(api.ttsJobs);
    state.ttsJobs = Array.isArray(jobs) ? jobs : jobs.value || [];
    renderTtsJobs();
    syncActiveTtsJobResult();
    if (state.ttsJobs.some((job) => !["succeeded", "failed"].includes(job.status))) {
      startTtsJobPolling();
    } else {
      stopTtsJobPolling();
    }
  } catch (error) {
    showToast(error.message, true);
  }
}

async function deleteTtsJob(jobId) {
  await fetchJson(api.ttsJob(jobId), { method: "DELETE" });
  await refreshTtsJobs();
  showToast("TTS job deleted");
}

async function cleanupTtsJobs() {
  await withBusy($("#cleanupTtsJobsButton"), async () => {
    const result = await fetchJson(api.ttsJobs, { method: "DELETE" });
    await refreshTtsJobs();
    showToast(`Cleaned ${result.deleted || 0} TTS jobs`);
  });
}

async function queueAsrJob() {
  const form = $("#asrForm");
  const formData = new FormData(form);
  const audio = formData.get("audio");
  if (!audio || !audio.name) {
    showToast("Select an audio file", true);
    return;
  }

  await withBusy($("#queueAsrJobButton"), async () => {
    const response = await authFetch(api.asrJobs, {
      method: "POST",
      body: formData,
    });
    await ensureOk(response);
    await refreshAsrJobs();
    startAsrJobPolling();
    showToast("ASR job queued");
  });
}

async function refreshAsrJobs() {
  try {
    const jobs = await fetchJson(api.asrJobs);
    state.asrJobs = Array.isArray(jobs) ? jobs : jobs.value || [];
    renderAsrJobs();
    if (state.asrJobs.some((job) => !["succeeded", "failed"].includes(job.status))) {
      startAsrJobPolling();
    } else {
      stopAsrJobPolling();
    }
  } catch (error) {
    showToast(error.message, true);
  }
}

async function deleteAsrJob(jobId) {
  await fetchJson(api.asrJob(jobId), { method: "DELETE" });
  await refreshAsrJobs();
  showToast("ASR job deleted");
}

async function cleanupAsrJobs() {
  await withBusy($("#cleanupAsrJobsButton"), async () => {
    const result = await fetchJson(api.asrJobs, { method: "DELETE" });
    await refreshAsrJobs();
    showToast(`Cleaned ${result.deleted || 0} ASR jobs`);
  });
}

async function transcribe(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);

  await withBusy(form.querySelector("button[type='submit']"), async () => {
    const response = await authFetch(api.asr, { method: "POST", body: formData });
    await ensureOk(response);
    const result = await response.json();
    $("#asrResult").value = result.text || "";
    showToast("Transcription complete");
  });
}

function renderVoices() {
  const list = $("#voiceList");
  list.innerHTML = "";
  updateVoiceInventoryBadge();
  updateVoiceLibrarySummary();
  const voices = filteredVoices();

  if (!state.voices.length) {
    const empty = document.createElement("div");
    empty.className = "voice-meta";
    empty.textContent = "No voices";
    list.appendChild(empty);
    return;
  }

  if (!voices.length) {
    const empty = document.createElement("div");
    empty.className = "voice-meta";
    empty.textContent = "No saved voices match this search";
    list.appendChild(empty);
    return;
  }

  for (const voice of voices) {
    const card = document.createElement("article");
    card.className = `voice-card ${voice.voice_id === state.selectedVoiceId ? "selected" : ""}`;

    const row = document.createElement("div");
    row.className = "voice-title-row";

    const title = document.createElement("div");
    title.className = "voice-title";
    title.textContent = voice.name;
    row.appendChild(title);

    const source = document.createElement("div");
    source.className = "voice-meta";
    source.textContent = voice.reference_text_source || "user";
    row.appendChild(source);
    card.appendChild(row);

    const meta = document.createElement("div");
    meta.className = "voice-meta";
    meta.textContent = `${voice.duration_seconds.toFixed(2)}s | ${voice.sample_rate} Hz`;
    card.appendChild(meta);

    const text = document.createElement("div");
    text.className = "voice-text";
    text.textContent = voice.reference_text;
    card.appendChild(text);

    const audio = document.createElement("audio");
    audio.className = "reference-audio";
    audio.controls = true;
    audio.preload = "metadata";
    audio.src = withAuthQuery(voice.reference_audio_url || api.voiceAudio(voice.voice_id));
    card.appendChild(audio);

    if (state.editingVoiceId === voice.voice_id) {
      card.appendChild(renderVoiceEditor(voice));
    }

    const actions = document.createElement("div");
    actions.className = "voice-card-actions";
    const useButton = document.createElement("button");
    useButton.type = "button";
    useButton.className = "command";
    useButton.textContent = "Use";
    useButton.addEventListener("click", () => {
      state.selectedVoiceId = voice.voice_id;
      renderVoices();
      renderVoiceSelect();
    });
    actions.appendChild(useButton);

    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.className = "command";
    editButton.textContent = state.editingVoiceId === voice.voice_id ? "Cancel" : "Edit";
    editButton.addEventListener("click", () => {
      state.editingVoiceId = state.editingVoiceId === voice.voice_id ? "" : voice.voice_id;
      renderVoices();
    });
    actions.appendChild(editButton);

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "command danger";
    deleteButton.textContent = "Delete";
    deleteButton.addEventListener("click", () => deleteVoice(voice.voice_id));
    actions.appendChild(deleteButton);
    card.appendChild(actions);

    list.appendChild(card);
  }
}

function renderImportCandidates() {
  const list = $("#importCandidateList");
  list.innerHTML = "";
  updateVoiceInventoryBadge();
  updateVoiceLibrarySummary();
  renderQuickImport();
  const candidates = filteredImportCandidates();

  if (!state.importCandidates.length) {
    const empty = document.createElement("div");
    empty.className = "voice-meta";
    empty.textContent = "No loose audio files in data/voices";
    list.appendChild(empty);
    return;
  }

  if (!candidates.length) {
    const empty = document.createElement("div");
    empty.className = "voice-meta";
    empty.textContent = "No local files match this search";
    list.appendChild(empty);
    return;
  }

  for (const candidate of candidates) {
    const form = document.createElement("form");
    form.className = "import-candidate-card";
    form.addEventListener("submit", (event) => importVoiceCandidate(event, candidate.filename));

    const header = document.createElement("div");
    header.className = "voice-title-row";
    const title = document.createElement("div");
    title.className = "voice-title";
    title.textContent = candidate.filename;
    const meta = document.createElement("div");
    meta.className = "voice-meta";
    meta.textContent = formatBytes(candidate.size_bytes || 0);
    header.appendChild(title);
    header.appendChild(meta);
    form.appendChild(header);

    const audio = document.createElement("audio");
    audio.className = "reference-audio import-preview-audio";
    audio.controls = true;
    audio.preload = "metadata";
    audio.src = withAuthQuery(importCandidateAudioUrl(candidate));
    form.appendChild(audio);

    const nameLabel = document.createElement("label");
    const nameCaption = document.createElement("span");
    nameCaption.textContent = "Voice name";
    const nameInput = document.createElement("input");
    nameInput.name = "name";
    nameInput.type = "text";
    nameInput.value = candidate.name || candidate.filename;
    nameLabel.appendChild(nameCaption);
    nameLabel.appendChild(nameInput);
    form.appendChild(nameLabel);

    const textLabel = document.createElement("label");
    const textCaption = document.createElement("span");
    textCaption.textContent = "Reference text";
    const textArea = document.createElement("textarea");
    textArea.name = "reference_text";
    textArea.rows = 3;
    textArea.placeholder = "Leave empty when auto transcribe is enabled";
    textLabel.appendChild(textCaption);
    textLabel.appendChild(textArea);
    form.appendChild(textLabel);

    const autoLabel = document.createElement("label");
    autoLabel.className = "check-row";
    const autoInput = document.createElement("input");
    autoInput.name = "auto_transcribe";
    autoInput.type = "checkbox";
    autoInput.checked = true;
    const autoText = document.createElement("span");
    autoText.textContent = "Auto transcribe";
    autoLabel.appendChild(autoInput);
    autoLabel.appendChild(autoText);
    form.appendChild(autoLabel);

    const button = document.createElement("button");
    button.className = "command primary";
    button.type = "submit";
    button.innerHTML = `<span>Import</span>`;
    form.appendChild(button);

    list.appendChild(form);
  }
}

function updateVoiceSearch(event) {
  state.voiceSearch = normalizeSearch(event.currentTarget.value);
  renderVoices();
  renderImportCandidates();
}

function filteredVoices() {
  if (!state.voiceSearch) {
    return state.voices;
  }
  return state.voices.filter((voice) => voiceMatchesSearch(voice));
}

function filteredImportCandidates() {
  if (!state.voiceSearch) {
    return state.importCandidates;
  }
  return state.importCandidates.filter((candidate) => candidateMatchesSearch(candidate));
}

function voiceMatchesSearch(voice) {
  return normalizeSearch(
    [
      voice.name,
      voice.reference_text,
      voice.reference_text_source,
      `${voice.duration_seconds?.toFixed?.(2) || voice.duration_seconds || ""}`,
      `${voice.sample_rate || ""}`,
    ].join(" ")
  ).includes(state.voiceSearch);
}

function candidateMatchesSearch(candidate) {
  return normalizeSearch([candidate.filename, candidate.name, formatBytes(candidate.size_bytes || 0)].join(" ")).includes(
    state.voiceSearch
  );
}

function updateVoiceLibrarySummary() {
  const summary = $("#voiceLibrarySummary");
  const voiceCount = state.voices.length;
  const candidateCount = state.importCandidates.length;
  const filteredVoiceCount = filteredVoices().length;
  const filteredCandidateCount = filteredImportCandidates().length;
  const base = `${voiceCount} saved ${voiceCount === 1 ? "voice" : "voices"} | ${candidateCount} local ${
    candidateCount === 1 ? "file" : "files"
  }`;
  summary.textContent = state.voiceSearch
    ? `${filteredVoiceCount + filteredCandidateCount} matches | ${base}`
    : base;
}

function normalizeSearch(value) {
  return String(value || "").trim().toLowerCase();
}

function updateVoiceInventoryBadge() {
  const badge = $("#voiceCountBadge");
  const voiceCount = state.voices.length;
  const candidateCount = state.importCandidates.length;
  const total = voiceCount + candidateCount;
  badge.textContent = String(total);
  badge.dataset.active = candidateCount ? "true" : "false";
  badge.title = candidateCount
    ? `${voiceCount} saved voices, ${candidateCount} local files ready`
    : `${voiceCount} saved voices`;
}

function renderQuickImport() {
  const panel = $("#quickImportPanel");
  const name = $("#quickImportName");
  const audio = $("#quickImportAudio");
  const candidate = state.importCandidates[0];
  const hasVoice = Boolean(selectedVoice());
  panel.hidden = hasVoice || !candidate;
  if (!candidate) {
    audio.removeAttribute("src");
    return;
  }
  name.textContent = candidate.filename;
  audio.src = withAuthQuery(importCandidateAudioUrl(candidate));
}

function importCandidateAudioUrl(candidate) {
  return candidate.audio_url || api.voiceImportCandidateAudio(candidate.filename);
}

function renderVoiceEditor(voice) {
  const form = document.createElement("form");
  form.className = "voice-edit-form";
  form.addEventListener("submit", (event) => updateVoice(event, voice.voice_id));

  const nameLabel = document.createElement("label");
  const nameCaption = document.createElement("span");
  nameCaption.textContent = "Name";
  const nameInput = document.createElement("input");
  nameInput.name = "name";
  nameInput.type = "text";
  nameInput.value = voice.name;
  nameLabel.appendChild(nameCaption);
  nameLabel.appendChild(nameInput);
  form.appendChild(nameLabel);

  const textLabel = document.createElement("label");
  const textCaption = document.createElement("span");
  textCaption.textContent = "Reference text";
  const textArea = document.createElement("textarea");
  textArea.name = "reference_text";
  textArea.rows = 4;
  textArea.value = voice.reference_text;
  textLabel.appendChild(textCaption);
  textLabel.appendChild(textArea);
  form.appendChild(textLabel);

  const saveButton = document.createElement("button");
  saveButton.type = "submit";
  saveButton.className = "command primary";
  saveButton.textContent = "Save";
  form.appendChild(saveButton);

  return form;
}

function renderVoiceSelect() {
  const select = $("#ttsForm select[name='voice_id']");
  select.innerHTML = "";
  for (const voice of state.voices) {
    const option = document.createElement("option");
    option.value = voice.voice_id;
    option.textContent = voice.name;
    option.selected = voice.voice_id === state.selectedVoiceId;
    select.appendChild(option);
  }
  renderSelectedVoiceCard();
  updateVoiceDependentUi();
}

function selectVoice(event) {
  state.selectedVoiceId = event.currentTarget.value;
  renderVoices();
  renderSelectedVoiceCard();
  updateVoiceDependentUi();
}

function selectedVoice() {
  return state.voices.find((voice) => voice.voice_id === state.selectedVoiceId) || null;
}

function renderSelectedVoiceCard() {
  const card = $("#selectedVoiceCard");
  const voice = selectedVoice();
  card.innerHTML = "";
  card.hidden = !voice;
  if (!voice) {
    return;
  }

  const summary = document.createElement("div");
  summary.className = "selected-voice-summary";
  const title = document.createElement("strong");
  title.textContent = voice.name;
  const meta = document.createElement("span");
  meta.textContent =
    `${formatDuration(voice.duration_seconds)} | ${voice.sample_rate} Hz | ` +
    `${voice.reference_text_source || "user"}`;
  summary.appendChild(title);
  summary.appendChild(meta);
  card.appendChild(summary);

  const audio = document.createElement("audio");
  audio.className = "reference-audio";
  audio.controls = true;
  audio.preload = "metadata";
  audio.src = withAuthQuery(voice.reference_audio_url || api.voiceAudio(voice.voice_id));
  card.appendChild(audio);
}

function updateVoiceDependentUi() {
  const hasVoice = Boolean(selectedVoice());
  const voice = selectedVoice();
  $("#synthesizeButton").disabled = !hasVoice;
  $("#queueTtsJobButton").disabled = !hasVoice;
  $("#mobileSynthesizeButton").disabled = !hasVoice;
  $("#mobileQueueButton").disabled = !hasVoice;
  $("#ttsForm select[name='voice_id']").disabled = !state.voices.length;
  $("#noVoiceEmptyState").hidden = hasVoice;
  $("#noVoiceSettingsHint").hidden = hasVoice;
  $("#mobileVoiceLabel").textContent = voice ? voice.name : "No voice";
  renderQuickImport();
}

function renderTtsJobs() {
  const list = $("#ttsJobList");
  list.innerHTML = "";
  updateJobBadge("#ttsJobCountBadge", state.ttsJobs);
  renderRightHistory();

  if (!state.ttsJobs.length) {
    const empty = document.createElement("div");
    empty.className = "voice-meta";
    empty.textContent = "No jobs";
    list.appendChild(empty);
    return;
  }

  for (const job of state.ttsJobs.slice(0, 12)) {
    const card = document.createElement("article");
    card.className = `job-card ${job.status}`;

    const row = document.createElement("div");
    row.className = "voice-title-row";
    const title = document.createElement("div");
    title.className = `status-pill ${job.status}`;
    title.textContent = job.status;
    row.appendChild(title);
    const meta = document.createElement("div");
    meta.className = "voice-meta";
    meta.textContent = job.duration_seconds ? `${Number(job.duration_seconds).toFixed(2)}s` : job.job_id.slice(0, 8);
    row.appendChild(meta);
    card.appendChild(row);

    const text = document.createElement("div");
    text.className = "voice-text";
    text.textContent = job.text;
    card.appendChild(text);

    const detail = document.createElement("div");
    detail.className = "job-detail-grid";
    const voiceDetail = document.createElement("span");
    voiceDetail.textContent = voiceNameById(job.voice_id) || job.voice_id.slice(0, 8);
    const paramsDetail = document.createElement("span");
    paramsDetail.textContent = `steps ${job.num_steps || "default"} | speed ${job.speed || "default"}`;
    detail.appendChild(voiceDetail);
    detail.appendChild(paramsDetail);
    card.appendChild(detail);

    if (job.error) {
      const error = document.createElement("div");
      error.className = "job-error";
      error.textContent = job.error;
      card.appendChild(error);
    }

    if (job.audio_url) {
      const audio = document.createElement("audio");
      audio.className = "reference-audio";
      audio.controls = true;
      audio.preload = "metadata";
      audio.src = withAuthQuery(job.audio_url);
      card.appendChild(audio);
    }

    if (["succeeded", "failed"].includes(job.status)) {
      const actions = document.createElement("div");
      actions.className = "voice-card-actions";

      if (job.audio_url) {
        const useButton = document.createElement("button");
        useButton.type = "button";
        useButton.className = "command";
        useButton.textContent = "Use output";
        useButton.addEventListener("click", () => useTtsJobOutput(job, { focus: true }));
        actions.appendChild(useButton);

        const download = document.createElement("a");
        download.className = "command";
        download.href = withAuthQuery(job.audio_url);
        download.download = ttsJobFileName(job);
        download.textContent = "Download";
        actions.appendChild(download);
      }

      const retryButton = document.createElement("button");
      retryButton.type = "button";
      retryButton.className = "command";
      retryButton.textContent = "Retry";
      retryButton.addEventListener("click", () => restoreTtsJob(job));
      actions.appendChild(retryButton);

      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "command danger";
      deleteButton.textContent = "Delete";
      deleteButton.addEventListener("click", () => deleteTtsJob(job.job_id));
      actions.appendChild(deleteButton);
      card.appendChild(actions);
    }

    list.appendChild(card);
  }
}

function syncActiveTtsJobResult() {
  if (!state.activeTtsJobId) {
    return;
  }

  const job = state.ttsJobs.find((item) => item.job_id === state.activeTtsJobId);
  if (!job) {
    return;
  }

  if (job.status === "queued" || job.status === "running") {
    setTtsResultStatus(
      job.status === "queued" ? "Job queued" : "Job running",
      `Rendering job ${job.job_id.slice(0, 8)} in History.`,
      "queued"
    );
    return;
  }

  if (job.status === "succeeded") {
    if (state.loadedTtsJobId !== job.job_id) {
      useTtsJobOutput(job, { announce: true });
    }
    state.activeTtsJobId = "";
    return;
  }

  if (job.status === "failed") {
    setTtsResultStatus("Job failed", job.error || "The queued TTS job failed.", "error");
    state.activeTtsJobId = "";
  }
}

function useTtsJobOutput(job, options = {}) {
  if (!job.audio_url) {
    showToast("This job has no audio output yet", true);
    return;
  }

  const audioUrl = withAuthQuery(job.audio_url);
  revokeCurrentTtsUrl();
  state.ttsUrl = audioUrl;
  state.loadedTtsJobId = job.job_id;
  $("#ttsAudio").src = audioUrl;
  $("#ttsAudio").hidden = false;
  $("#downloadLink").href = audioUrl;
  $("#downloadLink").download = ttsJobFileName(job);
  $("#downloadLink").setAttribute("aria-disabled", "false");
  setTtsResultStatus(
    "Job output ready",
    `${formatDuration(job.duration_seconds)} generated from ${voiceNameById(job.voice_id) || "saved voice"}`,
    "ready"
  );

  if (options.focus) {
    activateTab("synthesize");
    document.querySelector(".workspace").scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(revealTtsResult, 180);
  } else {
    revealTtsResult();
  }
  if (options.announce) {
    showToast("Queued TTS finished");
  }
}

function restoreTtsJob(job) {
  if (state.voices.some((voice) => voice.voice_id === job.voice_id)) {
    state.selectedVoiceId = job.voice_id;
    renderVoices();
    renderVoiceSelect();
  }

  const form = $("#ttsForm");
  form.elements.text.value = job.text || "";
  if (job.num_steps) {
    form.elements.num_steps.value = job.num_steps;
  }
  if (job.speed) {
    form.elements.speed.value = job.speed;
  }
  updateScriptCharCount();
  updateRangeLabels();
  activateSettingsPanel("settings");
  focusSynthesisComposer();
  showToast("Job restored");
}

function voiceNameById(voiceId) {
  return state.voices.find((voice) => voice.voice_id === voiceId)?.name || "";
}

function ttsJobFileName(job) {
  return `${safeFileName(voiceNameById(job.voice_id) || "vassil")}-${job.job_id.slice(0, 8)}.wav`;
}

function safeFileName(value) {
  return (
    String(value || "vassil")
      .trim()
      .replace(/[^a-z0-9]+/gi, "-")
      .replace(/^-+|-+$/g, "")
      .toLowerCase() || "vassil"
  );
}

function revokeCurrentTtsUrl() {
  if (state.ttsUrl?.startsWith("blob:")) {
    URL.revokeObjectURL(state.ttsUrl);
  }
}

function startTtsJobPolling() {
  if (state.ttsJobPollTimer) {
    return;
  }
  state.ttsJobPollTimer = setInterval(refreshTtsJobs, 2500);
}

function stopTtsJobPolling() {
  if (!state.ttsJobPollTimer) {
    return;
  }
  clearInterval(state.ttsJobPollTimer);
  state.ttsJobPollTimer = null;
}

function renderAsrJobs() {
  const list = $("#asrJobList");
  list.innerHTML = "";
  updateJobBadge("#asrJobCountBadge", state.asrJobs);
  renderRightHistory();

  if (!state.asrJobs.length) {
    const empty = document.createElement("div");
    empty.className = "voice-meta";
    empty.textContent = "No jobs";
    list.appendChild(empty);
    return;
  }

  for (const job of state.asrJobs.slice(0, 12)) {
    const card = document.createElement("article");
    card.className = `job-card ${job.status}`;

    const row = document.createElement("div");
    row.className = "voice-title-row";
    const title = document.createElement("div");
    title.className = `status-pill ${job.status}`;
    title.textContent = job.status;
    row.appendChild(title);
    const meta = document.createElement("div");
    meta.className = "voice-meta";
    meta.textContent = job.duration_seconds ? `${Number(job.duration_seconds).toFixed(2)}s` : job.job_id.slice(0, 8);
    row.appendChild(meta);
    card.appendChild(row);

    const filename = document.createElement("div");
    filename.className = "voice-meta";
    filename.textContent = job.filename || "audio";
    card.appendChild(filename);

    if (job.text) {
      const text = document.createElement("div");
      text.className = "voice-text";
      text.textContent = job.text;
      card.appendChild(text);
    }

    if (job.error) {
      const error = document.createElement("div");
      error.className = "job-error";
      error.textContent = job.error;
      card.appendChild(error);
    }

    if (["succeeded", "failed"].includes(job.status)) {
      const actions = document.createElement("div");
      actions.className = "voice-card-actions";

      if (job.text) {
        const useButton = document.createElement("button");
        useButton.type = "button";
        useButton.className = "command";
        useButton.textContent = "Use transcript";
        useButton.addEventListener("click", () => {
          $("#asrResult").value = job.text || "";
        });
        actions.appendChild(useButton);

        const scriptButton = document.createElement("button");
        scriptButton.type = "button";
        scriptButton.className = "command";
        scriptButton.textContent = "Use as script";
        scriptButton.addEventListener("click", () => openHistoryJob({ ...job, kind: "ASR" }));
        actions.appendChild(scriptButton);
      }

      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "command danger";
      deleteButton.textContent = "Delete";
      deleteButton.addEventListener("click", () => deleteAsrJob(job.job_id));
      actions.appendChild(deleteButton);
      card.appendChild(actions);
    }

    list.appendChild(card);
  }
}

function startAsrJobPolling() {
  if (state.asrJobPollTimer) {
    return;
  }
  state.asrJobPollTimer = setInterval(refreshAsrJobs, 2500);
}

function stopAsrJobPolling() {
  if (!state.asrJobPollTimer) {
    return;
  }
  clearInterval(state.asrJobPollTimer);
  state.asrJobPollTimer = null;
}

function activateTab(name) {
  document.querySelectorAll(".tab").forEach((button) => {
    const isActive = button.dataset.tab === name;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  document.querySelectorAll(".nav-link[data-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === name);
  });
  $("#synthesizeTab").classList.toggle("active", name === "synthesize");
  $("#transcribeTab").classList.toggle("active", name === "transcribe");
  $("#liveTab").classList.toggle("active", name === "live");
}

function activateSettingsPanel(name) {
  const isHistory = name === "history";
  $("#settingsTabButton").classList.toggle("active", !isHistory);
  $("#historyTabButton").classList.toggle("active", isHistory);
  $("#settingsPanelContent").hidden = isHistory;
  $("#historyPanelContent").hidden = !isHistory;
}

function renderRightHistory() {
  const list = $("#rightHistoryList");
  if (!list) {
    return;
  }

  const jobs = state.ttsJobs
    .map((job) => ({ ...job, kind: "TTS" }))
    .concat(state.asrJobs.map((job) => ({ ...job, kind: "ASR" })))
    .sort((left, right) => String(right.created_at).localeCompare(String(left.created_at)))
    .slice(0, 8);

  list.innerHTML = "";
  if (!jobs.length) {
    const empty = document.createElement("div");
    empty.className = "voice-meta";
    empty.textContent = "No recent jobs";
    list.appendChild(empty);
    return;
  }

  for (const job of jobs) {
    const row = document.createElement("article");
    row.className = "history-row";
    const canOpenTtsOutput = job.kind === "TTS" && job.audio_url;
    const canUseAsrText = job.kind === "ASR" && job.text;
    if (canOpenTtsOutput || canUseAsrText) {
      row.classList.add("clickable");
      row.tabIndex = 0;
      row.setAttribute("role", "button");
      row.title = canOpenTtsOutput ? "Use this TTS output" : "Use this transcript as script";
      row.addEventListener("click", () => openHistoryJob(job));
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openHistoryJob(job);
        }
      });
    }
    const status = document.createElement("span");
    status.className = `status-pill ${job.status}`;
    status.textContent = job.kind;
    const title = document.createElement("strong");
    title.textContent = job.kind === "TTS" ? job.text || job.job_id : job.filename || job.job_id;
    const meta = document.createElement("span");
    meta.textContent = `${job.status} | ${job.duration_seconds ? formatDuration(job.duration_seconds) : job.job_id.slice(0, 8)}`;
    row.appendChild(status);
    row.appendChild(title);
    row.appendChild(meta);
    list.appendChild(row);
  }
}

function openHistoryJob(job) {
  if (job.kind === "TTS" && job.audio_url) {
    useTtsJobOutput(job, { focus: true });
    return;
  }

  if (job.kind === "ASR" && job.text) {
    $("#ttsForm textarea[name='text']").value = job.text;
    $("#asrResult").value = job.text;
    updateScriptCharCount();
    focusSynthesisComposer();
    showToast("Transcript moved to script");
  }
}

function usePrompt(prompt) {
  const input = $("#ttsForm textarea[name='text']");
  input.value = prompt || "";
  updateScriptCharCount();
  input.focus();
}

function updateScriptCharCount() {
  const input = $("#ttsForm textarea[name='text']");
  const count = input.value.trim().length;
  $("#scriptCharCount").textContent = `${count} ${count === 1 ? "character" : "characters"}`;
}

function updateRangeLabels() {
  const steps = $("#ttsForm input[name='num_steps']");
  const speed = $("#ttsForm input[name='speed']");
  $("#stepsValue").textContent = steps.value;
  $("#speedValue").textContent = `${Number(speed.value).toFixed(1)}x`;
}

function setTtsResultStatus(title, detail, stateName = "idle") {
  const status = $("#ttsResultStatus");
  status.dataset.state = stateName;
  status.querySelector("strong").textContent = title;
  status.querySelector("span:last-child").textContent = detail;
}

function focusVoiceWorkflow() {
  const voice = selectedVoice();
  if (voice) {
    $("#ttsForm select[name='voice_id']").focus();
    return;
  }

  const quickImport = $("#quickImportPanel");
  if (quickImport && !quickImport.hidden) {
    $("#noVoiceEmptyState").scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
    window.setTimeout(() => $("#quickImportButton").focus({ preventScroll: true }), 250);
    return;
  }

  document.querySelector("#voiceLibrary").scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

function focusSynthesisComposer() {
  activateTab("synthesize");
  document.querySelector(".workspace").scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
  window.setTimeout(() => {
    $("#ttsForm textarea[name='text']").focus({ preventScroll: true });
  }, 250);
}

function revealTtsResult() {
  const result = $(".output-card");
  if (!result) {
    return;
  }

  result.scrollIntoView({
    behavior: "smooth",
    block: "nearest",
  });
}

function handleInitialHash() {
  window.setTimeout(scrollToCurrentHashTarget, 250);
}

function scrollToCurrentHashTarget() {
  if (!window.location.hash) {
    return;
  }

  const id = window.location.hash.slice(1);
  if (!id) {
    return;
  }

  const target = document.getElementById(decodeURIComponent(id));
  if (!target) {
    return;
  }

  target.scrollIntoView({
    behavior: "auto",
    block: "start",
  });
}

async function startRealtime() {
  if (state.realtime.active) {
    return;
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    showToast("Microphone capture is unavailable", true);
    return;
  }

  const startButton = $("#startLiveButton");
  startButton.disabled = true;
  $("#liveStatus").textContent = "Starting...";
  setInsight("#liveInsightCard", "#liveInsightStatus", "starting", "Starting");

  try {
    const socket = new WebSocket(api.realtimeAsr());
    socket.binaryType = "arraybuffer";
    state.realtime.socket = socket;

    const opened = new Promise((resolve, reject) => {
      socket.onopen = resolve;
      socket.onerror = () => reject(new Error("Realtime socket failed"));
      socket.onmessage = handleRealtimeMessage;
      socket.onclose = () => {
        cleanupRealtimeAudio();
        setLiveActive(false);
        $("#liveStatus").textContent = "Stopped";
      };
    });

    await opened;
    socket.send(
      JSON.stringify({
        type: "config",
        sample_rate: state.realtime.targetSampleRate,
        encoding: "pcm_f32le",
      })
    );

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    const audioContext = new AudioContextCtor();
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    const mute = audioContext.createGain();
    mute.gain.value = 0;

    processor.onaudioprocess = (event) => {
      if (!state.realtime.active || socket.readyState !== WebSocket.OPEN) {
        return;
      }

      const input = event.inputBuffer.getChannelData(0);
      updateLiveLevel(input);
      const pcm = resampleFloat32(input, audioContext.sampleRate, state.realtime.targetSampleRate);
      socket.send(pcm.buffer);
    };

    source.connect(processor);
    processor.connect(mute);
    mute.connect(audioContext.destination);

    Object.assign(state.realtime, {
      stream,
      audioContext,
      source,
      processor,
      mute,
      active: true,
    });
    setLiveActive(true);
    $("#liveStatus").textContent = "Listening";
    setInsight("#liveInsightCard", "#liveInsightStatus", "listening", "Listening");
  } catch (error) {
    cleanupRealtimeSocket();
    cleanupRealtimeAudio();
    setLiveActive(false);
    $("#liveStatus").textContent = "Idle";
    setInsight("#liveInsightCard", "#liveInsightStatus", "error", "Error");
    showToast(error.message, true);
  } finally {
    startButton.disabled = state.realtime.active;
  }
}

function stopRealtime() {
  const socket = state.realtime.socket;
  cleanupRealtimeAudio();
  setLiveActive(false);
  $("#liveStatus").textContent = "Stopping...";
  setInsight("#liveInsightCard", "#liveInsightStatus", "stopping", "Stopping");

  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "flush" }));
    socket.send(JSON.stringify({ type: "close" }));
    return;
  }

  cleanupRealtimeSocket();
  $("#liveStatus").textContent = "Stopped";
  setInsight("#liveInsightCard", "#liveInsightStatus", "standby", "Stopped");
}

function handleRealtimeMessage(event) {
  const message = JSON.parse(event.data);

  if (message.type === "ready") {
    state.realtime.targetSampleRate = message.sample_rate || state.realtime.targetSampleRate;
    $("#liveStatus").textContent = "Ready";
    setInsight("#liveInsightCard", "#liveInsightStatus", "ready", "Ready");
    return;
  }

  if (message.type === "configured") {
    $("#liveStatus").textContent = `Ready | ${message.sample_rate} Hz`;
    setInsight("#liveInsightCard", "#liveInsightStatus", "ready", `${message.sample_rate} Hz`);
    return;
  }

  if (message.type === "transcript") {
    if (message.skipped) {
      $("#liveStatus").textContent = "Listening | silence";
      setInsight("#liveInsightCard", "#liveInsightStatus", "silence", "Silence");
      return;
    }

    if (message.text) {
      appendLiveTranscript(message.text);
    }
    $("#liveStatus").textContent = `Listening | segment ${message.sequence}`;
    setInsight("#liveInsightCard", "#liveInsightStatus", "listening", `Segment ${message.sequence}`);
    return;
  }

  if (message.type === "error") {
    setInsight("#liveInsightCard", "#liveInsightStatus", "error", "Error");
    showToast(message.message || "Realtime error", true);
    return;
  }

  if (message.type === "closed") {
    cleanupRealtimeSocket();
    $("#liveStatus").textContent = "Stopped";
    setInsight("#liveInsightCard", "#liveInsightStatus", "standby", "Stopped");
  }
}

function appendLiveTranscript(text) {
  const result = $("#liveResult");
  result.value = result.value ? `${result.value}\n${text}` : text;
  result.scrollTop = result.scrollHeight;
}

function clearLiveTranscript() {
  $("#liveResult").value = "";
  if (state.realtime.socket?.readyState === WebSocket.OPEN) {
    state.realtime.socket.send(JSON.stringify({ type: "clear" }));
  }
}

function setLiveActive(active) {
  document.body.classList.toggle("live-active", active);
  $("#startLiveButton").disabled = active;
  $("#stopLiveButton").disabled = !active;
}

function cleanupRealtimeAudio() {
  state.realtime.active = false;

  try {
    state.realtime.processor?.disconnect();
    state.realtime.source?.disconnect();
    state.realtime.mute?.disconnect();
  } catch {
    // Nodes may already be disconnected by the browser.
  }

  state.realtime.stream?.getTracks().forEach((track) => track.stop());
  if (state.realtime.audioContext?.state !== "closed") {
    state.realtime.audioContext?.close();
  }

  Object.assign(state.realtime, {
    stream: null,
    audioContext: null,
    source: null,
    processor: null,
    mute: null,
    active: false,
  });
  resetLiveLevel();
}

function cleanupRealtimeSocket() {
  if (state.realtime.socket && state.realtime.socket.readyState < WebSocket.CLOSING) {
    state.realtime.socket.close();
  }
  state.realtime.socket = null;
}

function resampleFloat32(input, sourceSampleRate, targetSampleRate) {
  if (sourceSampleRate === targetSampleRate) {
    return new Float32Array(input);
  }

  const ratio = sourceSampleRate / targetSampleRate;
  const outputLength = Math.max(1, Math.round(input.length / ratio));
  const output = new Float32Array(outputLength);

  for (let index = 0; index < outputLength; index += 1) {
    const position = index * ratio;
    const left = Math.floor(position);
    const right = Math.min(left + 1, input.length - 1);
    const weight = position - left;
    output[index] = input[left] * (1 - weight) + input[right] * weight;
  }

  return output;
}

function updateRuntimeInsights(health, modelStatus) {
  const checks = modelStatus.checks || {};
  const asrConfigured = ["asr_encoder", "asr_decoder", "asr_joiner", "asr_tokens"].every(
    (key) => checks[key]
  );
  const ttsConfigured = ["tts_encoder", "tts_decoder", "tts_vocoder", "tts_tokens"].every(
    (key) => checks[key]
  );

  setInsight(
    "#asrInsightCard",
    "#asrInsightStatus",
    health.asr_loaded ? "loaded" : asrConfigured ? "ready" : "error",
    health.asr_loaded ? "Loaded" : asrConfigured ? "Ready" : "Check files"
  );
  setInsight(
    "#ttsInsightCard",
    "#ttsInsightStatus",
    health.tts_loaded ? "loaded" : ttsConfigured ? "ready" : "error",
    health.tts_loaded ? "Loaded" : ttsConfigured ? "Ready" : "Check files"
  );

  document.body.classList.toggle("runtime-ready", Boolean(modelStatus.ready));
}

function setInsight(cardSelector, statusSelector, status, text) {
  const card = $(cardSelector);
  const statusNode = $(statusSelector);
  if (card) {
    card.dataset.status = status;
  }
  if (statusNode) {
    statusNode.textContent = text;
  }
}

function updateJobBadge(selector, jobs) {
  const badge = $(selector);
  if (!badge) {
    return;
  }

  const active = jobs.filter((job) => !["succeeded", "failed"].includes(job.status)).length;
  badge.textContent = active ? `${active}/${jobs.length}` : String(jobs.length);
  badge.dataset.active = active ? "true" : "false";
  document.body.classList.toggle(
    "has-running-jobs",
    state.asrJobs.concat(state.ttsJobs).some((job) => !["succeeded", "failed"].includes(job.status))
  );
}

function updateLiveLevel(input) {
  let sum = 0;
  for (const sample of input) {
    sum += sample * sample;
  }
  const rms = Math.sqrt(sum / Math.max(1, input.length));
  const level = Math.min(1, rms * 7.5);
  document.documentElement.style.setProperty("--live-level", level.toFixed(3));
  document.documentElement.style.setProperty("--live-scale-low", (0.24 + level * 0.42).toFixed(3));
  document.documentElement.style.setProperty("--live-scale-high", (0.78 + level * 0.62).toFixed(3));
  document.documentElement.style.setProperty("--wave-duration", `${Math.max(680, 1500 - level * 620).toFixed(0)}ms`);
}

function resetLiveLevel() {
  document.documentElement.style.setProperty("--live-level", "0");
  document.documentElement.style.setProperty("--live-scale-low", "0.28");
  document.documentElement.style.setProperty("--live-scale-high", "1");
  document.documentElement.style.setProperty("--wave-duration", "1.6s");
}

function loadApiKey() {
  $("#apiKeyInput").value = getApiKey();
  document.body.classList.toggle("has-api-key", Boolean(getApiKey()));
}

function saveApiKey() {
  const value = $("#apiKeyInput").value.trim();
  if (value) {
    window.localStorage.setItem(API_KEY_STORAGE_KEY, value);
    window.localStorage.removeItem(LEGACY_API_KEY_STORAGE_KEY);
    document.body.classList.add("has-api-key");
    showToast("API key saved");
    refreshRuntime();
    refreshVoices();
    refreshImportCandidates();
    refreshAsrJobs();
    refreshTtsJobs();
  } else {
    clearApiKey();
  }
}

function clearApiKey() {
  window.localStorage.removeItem(API_KEY_STORAGE_KEY);
  window.localStorage.removeItem(LEGACY_API_KEY_STORAGE_KEY);
  $("#apiKeyInput").value = "";
  document.body.classList.remove("has-api-key");
  showToast("API key cleared");
  refreshRuntime();
  refreshVoices();
  refreshImportCandidates();
  refreshAsrJobs();
  refreshTtsJobs();
}

function getApiKey() {
  const value = window.localStorage.getItem(API_KEY_STORAGE_KEY);
  if (value) {
    return value;
  }

  const legacyValue = window.localStorage.getItem(LEGACY_API_KEY_STORAGE_KEY);
  if (legacyValue) {
    window.localStorage.setItem(API_KEY_STORAGE_KEY, legacyValue);
    return legacyValue;
  }

  return "";
}

function disableDownload() {
  $("#downloadLink").setAttribute("aria-disabled", "true");
  $("#ttsAudio").hidden = true;
  setTtsResultStatus("No output yet", "Latest render will appear here.", "idle");
}
