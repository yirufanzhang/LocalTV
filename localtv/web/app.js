const $ = (id) => document.getElementById(id);

const state = {
  catalog: null,
  config: null,
  kind: "image",
  page: "studio",
  image: null,
  video: null,
  media: { image: [], first: null, last: null, refs: [], videos: [], audios: [] },
  preview: null,
  busy: false,
  advanced: localStorage.getItem("localtv.advanced") === "1",
  resultShown: false,
  shownJob: null,
  projects: [],
  projectJobs: [],
  historyProject: "",
  historyKind: "all",
  followJob: "",
};

const TASK_HELP = {
  image: {
    text: "写提示词就能出图。也可以在下面上传参考图，模型会按这些图来画。",
    edit: "先上传要改的图片，提示词只写改什么、保留什么。",
    batch: "一次出一组相关图片。目前只有 Seedream 5.0 lite 支持。",
    layers: "把一张图拆成图层。上传一张 png 或 jpeg。",
  },
  video: {
    text: "写镜头就能出视频。也可以上传参考图。参考视频要公网地址，在「全模态参考」里填。",
    first: "上传一张图当作第一帧，模型从这张图往后演。",
    last: "上传第一帧和最后一帧，模型补中间的过程。",
    omni: "可以同时给参考图、公网视频和音频。视频必须是公网地址，方舟读不到本机文件。",
    edit: "按提示词修改一段已有视频。视频填公网地址。",
    extend: "把一段已有视频往后延长。视频填公网地址。",
    draft: "把之前的样片任务转成正式片，需要样片任务 ID。",
  },
};

const EXAMPLES = {
  image: [
    { label: "城市夜景", prompt: "雨后的城市夜景，地面反光，霓虹灯，电影感", sizeMode: "ratio", ratio: "16:9" },
    { label: "人物肖像", prompt: "窗边的年轻女性肖像，柔光，浅景深，胶片质感", sizeMode: "ratio", ratio: "3:4" },
    { label: "产品静物", prompt: "一只磨砂黑陶瓷杯放在深色石面上，柔和侧光，干净背景", sizeMode: "ratio", ratio: "1:1" },
  ],
  video: [
    { label: "雨中咖啡馆", prompt: "镜头缓慢推近一扇被雨打湿的咖啡馆玻璃，里面灯光温暖，电影感", durationMode: "seconds", duration: 5, ratio: "16:9" },
    { label: "海边走路", prompt: "一个穿风衣的人走在黄昏的海边，风吹动头发，自然光", durationMode: "seconds", duration: 5, ratio: "16:9" },
  ],
};

const TASKS = {
  image: { text: "文生图", edit: "图生图", batch: "组图", layers: "图层拆分" },
  video: {
    text: "文生视频", first: "首帧", last: "首尾帧", omni: "全模态参考",
    edit: "编辑视频", extend: "延长视频", draft: "样片转正式",
  },
};

let previewTimer = 0;
let pollTimer = 0;

boot();

async function boot() {
  state.catalog = await api("/api/catalog");
  state.config = await api("/api/config");
  state.image = freshImage(modelById("image", state.catalog.defaults.image));
  state.video = freshVideo(modelById("video", state.catalog.defaults.video));
  $("kinds").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button?.dataset.kind) return;
    setKind(button.dataset.kind);
  });
  bindDrop($("generator"));
  $("tasks").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    current().task = button.dataset.task;
    coerce();
    renderAll();
    schedulePreview();
  });
  $("prompt").addEventListener("input", () => {
    current().prompt = $("prompt").value;
    renderGuide();
    schedulePreview();
  });
  $("prompt").addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") $("generate").click();
  });
  $("params").addEventListener("change", onParam);
  $("params").addEventListener("input", onParam);
  $("modelBar").addEventListener("change", onParam);
  $("media").addEventListener("change", onMedia);
  $("media").addEventListener("click", onMediaClick);
  $("generate").addEventListener("click", generate);
  $("openHistory").addEventListener("click", openHistory);
  $("projectChip").addEventListener("click", toggleProjectMenu);
  $("projectMenu").addEventListener("click", (event) => {
    const option = event.target.closest("[data-switch]");
    if (option) switchProject(option.dataset.switch);
  });
  $("projectMenuLibrary").addEventListener("click", () => {
    closeProjectMenu();
    openHistory();
  });
  document.addEventListener("click", (event) => {
    if (!$("projectSwitch").contains(event.target)) closeProjectMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeProjectMenu();
  });
  $("newConversation").addEventListener("click", newConversation);
  $("createProject").addEventListener("click", createProject);
  $("projectName").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      createProject();
    }
  });
  $("useProject").addEventListener("click", useProject);
  $("projectList").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-project]");
    if (!button) return;
    state.historyProject = button.dataset.project;
    state.historyKind = "all";
    await loadProjectJobs();
    renderProjects();
  });
  $("categoryBar").addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter]");
    if (!button) return;
    state.historyKind = button.dataset.filter;
    renderProjects();
  });
  document.body.addEventListener("click", (event) => {
    const view = event.target.closest("[data-view]");
    if (view) {
      const job = [...(state.projectJobs || []), ...(state.jobs || [])].find((item) => item.id === view.dataset.view);
      if (!job) return;
      const kind = job.kind === "video" ? "video" : "image";
      if (state.page !== "studio" || state.kind !== kind) setKind(kind);
      showJob(job);
      watch(job);
      $("result").scrollIntoView({ block: "nearest" });
      return;
    }
    const button = event.target.closest("[data-open], [data-reveal]");
    if (!button) return;
    event.stopPropagation();
    api("/api/reveal", {
      method: "POST",
      body: {
        jobId: button.dataset.open || button.dataset.reveal,
        name: button.dataset.name || "",
        mode: button.dataset.open ? "open" : "reveal",
      },
    });
  });
  $("guide").addEventListener("click", (event) => {
    if (event.target.closest("[data-open-settings]")) openSettings();
  });
  $("examples").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    applyPreset(EXAMPLES[state.kind][Number(button.dataset.example)]);
  });
  $("shortcuts").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    applyPreset(JSON.parse(button.dataset.preset));
  });
  $("params").addEventListener("click", (event) => {
    if (!event.target.closest("#toggleAdvanced")) return;
    state.advanced = !state.advanced;
    localStorage.setItem("localtv.advanced", state.advanced ? "1" : "0");
    renderParams();
  });
  $("openSettings").addEventListener("click", openSettings);
  $("closeSettings").addEventListener("click", () => $("settings").close());
  $("settingsForm").addEventListener("submit", saveSettings);
  $("pickLibrary").addEventListener("click", pickLibrary);
  $("providerSettings").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-clear-provider]");
    if (!button) return;
    const data = await api("/api/config", { method: "PUT", body: { clearProvider: button.dataset.clearProvider } });
    if (!data.ok) {
      $("settingsError").textContent = (data.errors || ["没有清除。"])[0];
      return;
    }
    state.config = data;
    renderProviderSettings();
    paintConfig();
  });
  paintConfig();
  renderAll();
  renderResultPlaceholder();
  schedulePreview();
  loadJobs();
  loadProjects();
}

function clearMedia(kind) {
  if (kind === "image") {
    state.media.image = [];
    return;
  }
  state.media.first = null;
  state.media.last = null;
  state.media.refs = [];
  state.media.videos = [];
  state.media.audios = [];
}

function newConversation() {
  const spec = current();
  const model = currentModel();
  const keep = state.kind === "image"
    ? {
      model: spec.model, endpointId: spec.endpointId, watermark: spec.watermark,
      sizeMode: spec.sizeMode, tier: spec.tier, ratio: spec.ratio,
      width: spec.width, height: spec.height, outputFormat: spec.outputFormat, background: spec.background,
    }
    : {
      model: spec.model, endpointId: spec.endpointId, watermark: spec.watermark,
      resolution: spec.resolution, ratio: spec.ratio, durationMode: spec.durationMode,
      duration: spec.duration, generateAudio: spec.generateAudio, outputFormat: spec.outputFormat,
    };
  const fresh = state.kind === "image" ? freshImage(model) : freshVideo(model);
  Object.assign(spec, fresh, keep, { prompt: "", task: "text" });
  clearMedia(state.kind);
  state.resultShown = false;
  state.shownJob = null;
  state.followJob = "";
  renderAll();
  renderResultPlaceholder();
  schedulePreview();
  $("prompt").focus();
}

function setKind(kind) {
  state.kind = kind;
  state.page = "studio";
  paintNav();
  renderAll();
  if (!state.shownJob || state.shownJob.kind !== kind) {
    state.resultShown = false;
    state.shownJob = null;
    renderResultPlaceholder();
  }
  schedulePreview();
}

function paintNav() {
  const projects = state.page === "projects";
  $("workspace").classList.toggle("is-projects", projects);
  $("openHistory").classList.toggle("is-on", projects);
  [...$("kinds").children].forEach((item) => item.classList.toggle("is-on", !projects && item.dataset.kind === state.kind));
}

function bindDrop(target) {
  target.addEventListener("dragover", (event) => {
    if (![...event.dataTransfer.types].includes("Files")) return;
    event.preventDefault();
    target.classList.add("is-over");
  });
  target.addEventListener("dragleave", (event) => {
    if (!target.contains(event.relatedTarget)) target.classList.remove("is-over");
  });
  target.addEventListener("drop", async (event) => {
    event.preventDefault();
    target.classList.remove("is-over");
    await addDropped([...event.dataTransfer.files]);
  });
}

async function addDropped(files) {
  const images = files.filter((file) => file.type.startsWith("image/"));
  const audios = files.filter((file) => /audio\/(wav|mpeg|mp3)/.test(file.type) || /\.(wav|mp3)$/i.test(file.name));
  const task = current().task;
  const model = currentModel();
  if (state.kind === "image") {
    const limit = task === "layers" ? 1 : model.maxRefs;
    const next = task === "layers" ? [] : state.media.image.slice();
    for (const file of images) next.push(await readLocal(file));
    state.media.image = next.slice(-limit);
  } else if (task === "first" || (task === "text" && !model.maxRefImages)) {
    if (images[0]) state.media.first = await readLocal(images[0]);
  } else if (task === "last") {
    if (images[0] && !state.media.first) state.media.first = await readLocal(images[0]);
    else if (images[0]) state.media.last = await readLocal(images[0]);
    if (images[1]) state.media.last = await readLocal(images[1]);
  } else {
    const next = state.media.refs.slice();
    for (const file of images) next.push(await readLocal(file));
    state.media.refs = next.slice(-model.maxRefImages);
    const audioNext = state.media.audios.slice();
    for (const file of audios) audioNext.push(await readLocal(file));
    state.media.audios = audioNext.slice(-(model.maxRefAudios || 0));
  }
  renderMedia();
  schedulePreview();
}

function applyPreset(preset) {
  if (!preset) return;
  const spec = current();
  if (preset.prompt) spec.prompt = preset.prompt;
  ["sizeMode", "ratio", "tier", "durationMode", "duration"].forEach((key) => {
    if (preset[key] !== undefined) spec[key] = preset[key];
  });
  coerce();
  renderAll();
  schedulePreview();
}

function vendorsFor(kind) {
  return (state.catalog.providers || []).filter((provider) => provider.series.some((series) => series.kind === kind));
}

function modelsFor(kind, providerId) {
  const list = kind === "image" ? state.catalog.imageModels : state.catalog.videoModels;
  return list.filter((model) => model.provider === providerId);
}

function activeVendor() {
  const picked = state.vendor?.[state.kind];
  if (picked && vendorsFor(state.kind).some((provider) => provider.id === picked)) return picked;
  return currentModel()?.provider || "ark";
}

function modelById(kind, id) {
  const list = kind === "image" ? state.catalog.imageModels : state.catalog.videoModels;
  return list.find((item) => item.id === id) || list[0];
}

function currentModel() {
  return modelById(state.kind, current().model);
}

function current() {
  return state[state.kind];
}

function freshImage(model) {
  return {
    model: model.id, endpointId: "", task: "text", prompt: "",
    sizeMode: "tier", tier: model.defaultTier, ratio: "1:1", width: 2048, height: 2048,
    outputFormat: model.defaultOutput, background: model.defaultBackground || "opaque",
    optimizeMode: model.defaultOptimize, watermark: true, responseFormat: "url",
    maxImages: 15, stream: false, webSearch: false, layerMax: 30,
    textRecognition: false, safetyIdentifier: "",
  };
}

function freshVideo(model) {
  return {
    model: model.id, endpointId: "", task: "text", prompt: "",
    omniType: "auto", resolution: model.defaultResolution, ratio: model.defaultRatio,
    durationMode: model.defaultDurationMode, duration: 5, frames: 121,
    generateAudio: true, watermark: false, outputFormat: model.defaultOutput,
    seed: -1, cameraFixed: false, returnLastFrame: false, draft: false,
    serviceTier: "default", priority: 0, expiresSeconds: 172800,
    callbackUrl: "", webSearch: false, safetyIdentifier: "", draftTaskId: "",
  };
}

function coerce() {
  if (state.kind === "image") {
    const model = currentModel();
    const spec = state.image;
    if (!model.tasks.includes(spec.task)) spec.task = "text";
    const tiers = spec.task === "layers" ? model.layerTiers : model.tiers;
    if (!tiers.includes(spec.tier)) spec.tier = spec.task === "layers" ? "auto" : model.defaultTier;
    if (!model.outputFormats.includes(spec.outputFormat)) spec.outputFormat = model.defaultOutput;
    if (model.backgrounds.length && !model.backgrounds.includes(spec.background)) spec.background = model.defaultBackground;
    if (!model.optimizeModes.includes(spec.optimizeMode)) spec.optimizeMode = model.defaultOptimize;
    if (spec.task === "layers") spec.sizeMode = "tier";
    if (spec.task !== "batch") spec.stream = false;
    if (!model.webSearch) spec.webSearch = false;
    return;
  }
  const model = currentModel();
  const spec = state.video;
  if (!model.tasks.includes(spec.task)) spec.task = "text";
  if (!model.resolutions.includes(spec.resolution)) spec.resolution = model.defaultResolution;
  if (spec.draft && model.draft) spec.resolution = "480p";
  if (model.lockRatioTasks.includes(spec.task)) spec.ratio = "adaptive";
  if (!["omit", "smart", "seconds", "frames"].includes(spec.durationMode)) spec.durationMode = model.defaultDurationMode;
  if (spec.durationMode === "smart" && !model.smartDuration) spec.durationMode = "seconds";
  if (spec.durationMode === "frames" && !model.frames) spec.durationMode = model.defaultDurationMode;
  if (model.lockDurationTasks.includes(spec.task)) spec.durationMode = "smart";
  if (!model.outputFormats.includes(spec.outputFormat)) spec.outputFormat = model.defaultOutput;
  if (!model.generateAudio) spec.generateAudio = true;
  if (spec.serviceTier === "flex" && !model.serviceTier) spec.serviceTier = "default";
  if (!model.cameraFixed || spec.task === "omni") spec.cameraFixed = false;
  if (!model.seed) spec.seed = -1;
  if (!model.webSearch) spec.webSearch = false;
  if (!model.draft) spec.draft = false;
}

function renderAll() {
  $("prompt").value = current().prompt;
  if (!state.busy) $("generate").textContent = state.kind === "image" ? "生成图片" : "生成视频";
  renderGuide();
  renderModelBar();
  renderTasks();
  renderExamples();
  renderShortcuts();
  renderMedia();
  renderParams();
}

function renderGuide() {
  const hasKey = !!state.config?.hasKey;
  if (hasKey) {
    $("guide").className = "guide is-slim";
    $("guide").innerHTML = "";
    return;
  }
  $("guide").className = "guide";
  const hasPrompt = !!current().prompt.trim();
  const steps = [
    {
      title: "1 保存密钥",
      text: hasKey ? `火山方舟已保存，末尾 ···${state.config.keyTail}。其他服务商在设置里分开填。` : "每个服务商的密钥分开保存，只存在这台电脑。",
      done: hasKey,
      action: hasKey ? "" : `<button type="button" data-open-settings>去设置</button>`,
    },
    { title: "2 选模型和任务", text: "默认模型可以直接用。灰色任务是当前模型不支持的。", done: true },
    { title: "3 写提示词", text: "可以自己写，也可以点下面的示例填入。", done: hasPrompt },
    { title: "4 生成", text: "图片通常很快返回。视频会排队，完成后自动存到本机。", done: false },
  ];
  $("guide").innerHTML = steps.map((step) => `
    <article class="step ${step.done ? "is-done" : ""}">
      <b>${step.title}</b>
      <p>${escapeHtml(step.text)}</p>
      ${step.action || ""}
    </article>`).join("");
}

function renderExamples() {
  if (!modelsFor(state.kind, activeVendor()).length) {
    $("examples").innerHTML = "";
    return;
  }
  $("examples").innerHTML = EXAMPLES[state.kind].map((item, index) => (
    `<button type="button" data-example="${index}">试试：${escapeHtml(item.label)}</button>`
  )).join("");
}

function renderShortcuts() {
  if (!modelsFor(state.kind, activeVendor()).length) {
    $("shortcuts").innerHTML = "";
    return;
  }
  const task = current().task;
  const model = currentModel();
  let items = [];
  if (state.kind === "image" && task !== "layers") {
    items = [
      { label: "方图", preset: { sizeMode: "ratio", ratio: "1:1" } },
      { label: "横图 16:9", preset: { sizeMode: "ratio", ratio: "16:9" } },
      { label: "竖图 9:16", preset: { sizeMode: "ratio", ratio: "9:16" } },
      { label: "只选 2K", preset: { sizeMode: "tier", tier: model.tiers.includes("2K") ? "2K" : model.defaultTier } },
    ];
  }
  if (state.kind === "video" && task !== "draft") {
    const lockRatio = model.lockRatioTasks.includes(task);
    items = [
      { label: "5 秒", preset: { durationMode: "seconds", duration: 5 }, disabled: model.lockDurationTasks.includes(task) },
      { label: "10 秒", preset: { durationMode: "seconds", duration: Math.min(10, model.durationMax) }, disabled: model.lockDurationTasks.includes(task) || model.durationMax < 10 },
      { label: "横屏", preset: { ratio: "16:9" }, disabled: lockRatio },
      { label: "竖屏", preset: { ratio: "9:16" }, disabled: lockRatio },
    ];
  }
  $("shortcuts").innerHTML = items.map((item) => (
    `<button type="button" data-preset="${escapeHtml(JSON.stringify(item.preset))}" ${item.disabled ? "disabled" : ""}>${escapeHtml(item.label)}</button>`
  )).join("");
}

function renderResultPlaceholder() {
  if (state.resultShown) return;
  const video = state.kind === "video";
  const title = video ? "视频会显示在这里" : "图片会显示在这里";
  const hint = video ? "在下面写镜头，生成完成后出现在这块画布。" : "在下面写画面，生成完成后出现在这块画布。";
  $("result").innerHTML = `<div class="empty-result"><strong>${title}</strong><p>${hint}</p></div>`;
}

function renderModelBar() {
  const kind = state.kind;
  const vendorId = activeVendor();
  const vendors = vendorsFor(kind);
  const models = modelsFor(kind, vendorId);
  const vendorOptions = vendors.map((provider) => {
    const pending = modelsFor(kind, provider.id).length ? "" : " · 即将接入";
    return `<option value="${escapeHtml(provider.id)}" ${provider.id === vendorId ? "selected" : ""}>${escapeHtml(provider.name)}${pending}</option>`;
  }).join("");
  const modelOptions = models.length
    ? models.map((model) => option(model, current().model)).join("")
    : `<option value="">还没有接入模型</option>`;
  const model = models.find((item) => item.id === current().model) || models[0];
  const provider = vendors.find((item) => item.id === vendorId);
  const note = model
    ? `${model.retiring ? "即将下线。" : ""}${model.note || ""}`
    : (provider?.hint || "这个厂商的模型还在接入。");
  $("modelBar").innerHTML = `
    <div class="model-picks">
      <label class="field"><span>厂商</span><select name="vendor">${vendorOptions}</select></label>
      <label class="field"><span>模型</span><select name="model" ${models.length ? "" : "disabled"}>${modelOptions}</select></label>
    </div>
    <p class="model-meta">${model ? `<code>${escapeHtml(model.id)}</code>` : ""}<span title="${escapeHtml(note)}">${escapeHtml(note)}</span></p>`;
}

function option(model, selected) {
  const marks = [model.recommended ? "默认" : "", model.retiring ? "即将下线" : ""].filter(Boolean).join(" · ");
  return `<option value="${escapeHtml(model.id)}" ${model.id === selected ? "selected" : ""}>${escapeHtml(model.name)}${marks ? " · " + escapeHtml(marks) : ""}</option>`;
}

function renderTasks() {
  if (!modelsFor(state.kind, activeVendor()).length) {
    $("tasks").innerHTML = "";
    $("taskHelp").textContent = "这个厂商的模型还在接入，暂时不能生成。";
    return;
  }
  const model = currentModel();
  const tasks = state.kind === "image" ? state.catalog.imageTasks : state.catalog.videoTasks;
  $("tasks").innerHTML = tasks.map((task) => {
    const enabled = model.tasks.includes(task.id);
    const on = current().task === task.id;
    const reason = enabled ? "" : " title=\"当前模型不支持\"";
    return `<button type="button" data-task="${task.id}" class="${on ? "is-on" : ""}"${reason} ${enabled ? "" : "disabled"}>${task.label}</button>`;
  }).join("");
  let help = TASK_HELP[state.kind][current().task] || "";
  if (state.kind === "video" && current().task === "text" && !model.maxRefImages) {
    help = "写镜头出视频。这个模型没有多张参考图，上传的图片会作为第一帧。";
  }
  $("taskHelp").textContent = help;
}

function renderMedia() {
  if (!modelsFor(state.kind, activeVendor()).length) {
    $("media").innerHTML = "";
    return;
  }
  const task = current().task;
  const model = currentModel();
  if (state.kind === "image") {
    const limit = task === "layers" ? 1 : model.maxRefs;
    const note = task === "layers"
      ? "图层拆分只收一张 png 或 jpeg。"
      : `参考图 ${state.media.image.length} / ${limit}，可选。不上传就是文生图，上传后会和提示词一起交给模型。`;
    $("media").innerHTML = `
      <div class="media">
        <p class="media-note">${note}</p>
        ${fileDrop("images", task === "layers" ? "选择一张图片" : "上传参考图", task === "layers" ? "png 或 jpeg" : "png、jpeg，可多选，单张不超过 30MB", task !== "layers")}
        <div class="chips">${state.media.image.map((item) => chip(item, "image")).join("")}</div>
      </div>`;
    return;
  }
  const blocks = [];
  if (task === "first" || task === "last") {
    blocks.push(frameSlot("首帧", "first", state.media.first));
  }
  if (task === "last") blocks.push(frameSlot("尾帧", "last", state.media.last));
  if (task === "omni" || task === "edit" || task === "extend") {
    blocks.push(`
      <p class="media-note">参考图 ${state.media.refs.length} / ${model.maxRefImages}</p>
      ${fileDrop("refs", "选择参考图", "可多选", true)}
      <div class="chips">${state.media.refs.map((item) => chip(item, "refs")).join("")}</div>
      <p class="media-note">${state.catalog.limits.videoNote} 现有 ${state.media.videos.length} / ${model.maxRefVideos} 条。</p>
      <div class="generate-row">
        <input name="videoUrl" type="url" placeholder="https://.../clip.mp4">
        <button type="button" class="ghost" data-add="videos">添加视频地址</button>
      </div>
      <div class="chips">${state.media.videos.map((item) => `<span class="chip-file">${escapeHtml(item.url)} <button type="button" data-remove="videos" data-id="${item.id}">移除</button></span>`).join("")}</div>
      <p class="media-note">参考音频 wav / mp3，单段不超过 15MB。${state.media.audios.length} / ${model.maxRefAudios}</p>
      <label class="drop"><input type="file" name="audios" accept="audio/wav,audio/mpeg,audio/mp3,.wav,.mp3" multiple><strong>选择音频</strong><span>wav 或 mp3</span></label>
      <div class="chips">${state.media.audios.map((item) => chip(item, "audios")).join("")}</div>`);
  }
  if (task === "draft") {
    blocks.push(`<p class="media-note">填写右侧的样片任务 ID。样片过期后不能再转正式片。</p>`);
  }
  if (task === "text" && model.maxRefImages > 0) {
    blocks.push(`
      <p class="media-note">参考图 ${state.media.refs.length} / ${model.maxRefImages}，可选。本地图片可以直接选。参考视频要公网地址，请切到「全模态参考」。</p>
      ${fileDrop("refs", "上传参考图", "png、jpeg，可多选", true)}
      <div class="chips">${state.media.refs.map((item) => chip(item, "refs")).join("")}</div>`);
  } else if (task === "text" && model.tasks.includes("first")) {
    blocks.push(`<p class="media-note">这个模型没有多张参考图。上传的图片会作为视频第一帧。</p>`);
    blocks.push(frameSlot("首帧", "first", state.media.first));
  }
  $("media").innerHTML = `<div class="media">${blocks.join("")}</div>`;
}

function frameSlot(label, name, item) {
  return `<p class="media-note">${label}</p>
    ${fileDrop(name, `选择${label}`, "作为视频的这一帧", false)}
    <div class="chips">${item ? chip(item, name) : ""}</div>`;
}

function fileDrop(name, title, hint, multiple) {
  return `<label class="drop"><input type="file" name="${name}" accept="image/*" ${multiple ? "multiple" : ""}><strong>${escapeHtml(title)}</strong><span>${escapeHtml(hint)}</span></label>`;
}

function chip(item, group) {
  const thumb = item.preview ? `<img src="${item.preview}" alt="">` : "";
  return `<span class="chip-file">${thumb}<span>${escapeHtml(item.name || "素材")}</span><button type="button" data-remove="${group}" data-id="${item.id}">移除</button></span>`;
}

function renderParams() {
  if (!modelsFor(state.kind, activeVendor()).length) {
    $("params").innerHTML = `<div class="param-head"><h2>参数</h2></div><p class="meta">这个厂商的模型还在接入，参数会在模型可用后出现。</p>`;
    return;
  }
  const model = currentModel();
  const spec = current();
  const groups = state.kind === "image" ? imageFields(model, spec) : videoFields(model, spec);
  const advanced = groups.advanced.concat([
    textField("endpointId", "接入点 ID", "endpointId", spec.endpointId, "可选。填写后用它调用，参数约束仍按左侧所选模型。"),
  ]);
  $("params").innerHTML = `
    <div class="param-head">
      <h2>参数</h2>
      <button type="button" class="text-button" id="toggleAdvanced">${state.advanced ? "收起高级参数" : "高级参数"}</button>
    </div>
    <section class="param-block"><h3>常用</h3>${groups.common.join("")}</section>
    <section class="param-block" ${state.advanced ? "" : "hidden"}><h3>高级</h3>${advanced.join("")}</section>`;
}

function imageFields(model, spec) {
  const layers = spec.task === "layers";
  const tiers = layers ? model.layerTiers : model.tiers;
  const common = [
    selectField("sizeMode", "尺寸方式", "size", [
      ["tier", "只选分辨率档位"],
      ["ratio", "档位 + 比例"],
      ["custom", "自定义宽高"],
    ], spec.sizeMode, layers, layers ? "图层拆分只能选档位。" : "选了比例会按文档像素表提交宽x高。"),
    selectField("tier", "分辨率", "size", tiers.map((item) => [item, item]), spec.tier, false, "档位越高，画面越大，也更慢。"),
  ];
  const advanced = [];
  if (!layers && spec.sizeMode === "ratio") {
    common.push(selectField("ratio", "比例", "size", state.catalog.ratios.map((item) => [item, item]), spec.ratio, false, "横图用 16:9，竖图用 9:16，头像用 1:1。"));
  }
  if (!layers && spec.sizeMode === "custom") {
    common.push(numberField("width", "宽度", "size", spec.width, 2, 8192));
    common.push(numberField("height", "高度", "size", spec.height, 2, 8192));
  }
  common.push(selectField("outputFormat", "输出格式", "output_format", model.outputFormats.map((item) => [item, item]), spec.outputFormat, model.outputFormats.length < 2, model.outputFormats.length < 2 ? "这个模型只有一种格式。" : "要透明背景就选 png。JPEG 不能透明。"));
  const backgroundOff = layers || !model.backgrounds.length;
  common.push(selectField("background", "透明通道", "background", (model.backgrounds.length ? model.backgrounds : ["opaque"]).map((item) => [item, item]), spec.background || "opaque", backgroundOff, layers ? "图层拆分不能设置透明通道。" : backgroundOff ? "这个模型不能出透明图。" : "不确定就选 auto。"));
  common.push(checkField("watermark", "水印", "watermark", spec.watermark, false, "默认开启，右下角是「AI 生成」。不想要就关掉。"));
  advanced.push(selectField("optimizeMode", "提示词优化", "optimize_prompt_options.mode", model.optimizeModes.map((item) => [item, item === "fast" ? "快速" : "标准"]), spec.optimizeMode, model.optimizeModes.length < 2, model.optimizeModes.length < 2 ? "快速模式只有部分模型提供。" : "让模型先改写提示词。"));
  advanced.push(selectField("responseFormat", "返回方式", "response_format", [["url", "下载链接"], ["b64_json", "Base64"]], spec.responseFormat, false, "两种都会再存成本地文件。"));
  if (spec.task === "batch") {
    common.push(numberField("maxImages", "组图张数上限", "max_images", spec.maxImages, 1, 15));
    advanced.push(checkField("stream", "流式返回", "stream", spec.stream, !model.stream, model.stream ? "每出一张先显示一张。" : "这个模型不能流式返回。"));
  }
  advanced.push(checkField("webSearch", "联网搜索", "tools.web_search", spec.webSearch, !model.webSearch, model.webSearch ? "会更慢一些。" : "只有 Seedream 5.0 lite 可以开。"));
  if (layers && model.layerMax) common.push(numberField("layerMax", "拆分张数上限", "layer_decomposition_options.max_images", spec.layerMax, 2, 100));
  if (layers && model.ocr) advanced.push(checkField("textRecognition", "文字识别", "text_recognition", spec.textRecognition, false, "只对规整文字图层返回样式。"));
  advanced.push(textField("safetyIdentifier", "终端用户标识", "safety_identifier", spec.safetyIdentifier, model.safety ? "可选，不超过 64 个英文字符。" : "这个模型没有这个字段。", !model.safety));
  return { common, advanced };
}

function videoFields(model, spec) {
  const lockRatio = model.lockRatioTasks.includes(spec.task);
  const lockDuration = model.lockDurationTasks.includes(spec.task);
  const draftLock = spec.draft && model.draft;
  const durationModes = [["omit", "模型默认，不传"]];
  if (model.smartDuration) durationModes.push(["smart", "智能时长 -1"]);
  durationModes.push(["seconds", "指定秒数"]);
  if (model.frames) durationModes.push(["frames", "指定帧数"]);
  const common = [];
  const advanced = [];
  if (spec.task === "omni") {
    common.push(selectField("omniType", "全模态意图", "omni_reference_task_type", [["auto", "自动"], ["reference", "参考生视频"], ["edit", "编辑"], ["extend", "延长"]], spec.omniType, false, "不确定就选自动。"));
  }
  if (spec.task === "draft") {
    common.push(textField("draftTaskId", "样片任务 ID", "draft_task.id", spec.draftTaskId, "用 Seedance 2.5 样片模式生成的任务 ID。"));
  }
  common.push(selectField("resolution", "分辨率", "resolution", model.resolutions.map((item) => [item, item]), draftLock ? "480p" : spec.resolution, draftLock, draftLock ? "样片模式锁定 480p。" : "第一次试片用 720p 就够。"));
  const ratioHint = lockRatio
    ? "这个任务只能跟随素材。"
    : (spec.task === "first" || spec.task === "last" ? "和首帧不一致时会居中裁剪。" : "");
  common.push(selectField("ratio", "宽高比", "ratio", state.catalog.videoRatios.map((item) => [item, item]), lockRatio ? "adaptive" : spec.ratio, lockRatio, ratioHint || "横屏 16:9，竖屏 9:16。adaptive 跟随素材。"));
  common.push(selectField("durationMode", "时长方式", "duration", durationModes, lockDuration ? "smart" : spec.durationMode, lockDuration, lockDuration ? "编辑任务只能智能时长。" : `${model.durationMin}–${model.durationMax} 秒。第一次可以指定 5 秒。`));
  if (!lockDuration && spec.durationMode === "seconds") {
    common.push(numberField("duration", "秒数", "duration", spec.duration, model.durationMin, model.durationMax));
  }
  if (spec.durationMode === "frames") {
    common.push(numberField("frames", "帧数", "frames", spec.frames, 29, 289));
  }
  common.push(checkField("generateAudio", "生成声音", "generate_audio", spec.generateAudio, !model.generateAudio, model.generateAudio ? "默认开启。想要角色说话，把台词放在双引号里。" : "1.0 没有这个开关。"));
  common.push(checkField("watermark", "水印", "watermark", spec.watermark, false, "视频默认关闭。"));
  advanced.push(selectField("outputFormat", "封装", "output_format", model.outputFormats.map((item) => [item, item]), spec.outputFormat, model.outputFormats.length < 2, "一般用 mp4。MOV 只在 Seedance 2.5。"));
  advanced.push(numberField("seed", "随机种子", "seed", spec.seed, -1, 2147483647, !model.seed));
  advanced.push(checkField("cameraFixed", "固定镜头", "camera_fixed", spec.cameraFixed, !model.cameraFixed || spec.task === "omni", "只在 Seedance 1.0，参考图场景不可用。"));
  advanced.push(checkField("returnLastFrame", "返回尾帧", "return_last_frame", spec.returnLastFrame, false, "尾帧会和视频一起存到本地，方便接下一段。"));
  advanced.push(checkField("draft", "样片模式", "draft", spec.draft, !model.draft || spec.task === "draft", model.draft ? "先出 480p 预览，满意后再转正式片。" : "只有 Seedance 2.5 标准版可以开。"));
  advanced.push(selectField("serviceTier", "服务等级", "service_tier", [["default", "在线"], ["flex", "离线，约半价"]], spec.serviceTier, !model.serviceTier, "离线推理只有 1.0，提交后不能改。"));
  advanced.push(numberField("priority", "排队优先级", "priority", spec.priority, 0, 9, !model.priority || spec.serviceTier === "flex"));
  advanced.push(numberField("expiresSeconds", "任务过期（秒）", "execution_expires_after", spec.expiresSeconds, 3600, 259200));
  advanced.push(textField("callbackUrl", "回调地址", "callback_url", spec.callbackUrl, "留空则只在本机轮询。"));
  advanced.push(checkField("webSearch", "联网搜索", "tools.web_search", spec.webSearch, !model.webSearch, model.webSearch ? "会更慢一些。" : "1.0 不能联网搜索。"));
  advanced.push(textField("safetyIdentifier", "终端用户标识", "safety_identifier", spec.safetyIdentifier, "可选，不超过 64 个英文字符。"));
  return { common, advanced };
}

function selectField(name, label, code, options, value, disabled, hint) {
  const html = options.map(([id, text]) => `<option value="${escapeHtml(id)}" ${String(id) === String(value) ? "selected" : ""}>${escapeHtml(text)}</option>`).join("");
  return wrap(name, label, code, `<select name="${name}" ${disabled ? "disabled" : ""}>${html}</select>`, hint, disabled);
}
function numberField(name, label, code, value, min, max, disabled = false) {
  return wrap(name, label, code, `<input name="${name}" type="number" value="${value}" min="${min}" max="${max}" ${disabled ? "disabled" : ""}>`, `${min}–${max}`, disabled);
}
function checkField(name, label, code, checked, disabled, hint) {
  return wrap(name, label, code, `<input name="${name}" type="checkbox" ${checked ? "checked" : ""} ${disabled ? "disabled" : ""}>`, hint, disabled);
}
function textField(name, label, code, value, hint, disabled = false) {
  return wrap(name, label, code, `<input name="${name}" type="text" value="${escapeHtml(value || "")}" ${disabled ? "disabled" : ""}>`, hint, disabled);
}
function wrap(name, label, code, control, hint, disabled) {
  return `<label class="field ${disabled ? "is-off" : ""}"><span>${label} <code>${code}</code></span>${control}<small>${escapeHtml(hint || "")}</small></label>`;
}

function applyModel(id) {
  const spec = current();
  const prompt = spec.prompt;
  const endpointId = spec.endpointId;
  const watermark = spec.watermark;
  spec.model = id;
  const fresh = state.kind === "image" ? freshImage(currentModel()) : freshVideo(currentModel());
  Object.assign(spec, fresh, { model: id, prompt, endpointId, watermark });
  coerce();
  renderAll();
}

function chooseVendor(id) {
  state.vendor = state.vendor || {};
  state.vendor[state.kind] = id;
  const models = modelsFor(state.kind, id);
  if (models.length) applyModel((models.find((item) => item.recommended) || models[0]).id);
  else renderAll();
  schedulePreview();
}

function onParam(event) {
  const input = event.target;
  if (!input.name || input.disabled) return;
  if (input.name === "vendor") {
    chooseVendor(input.value);
    return;
  }
  const spec = current();
  if (input.type === "checkbox") spec[input.name] = input.checked;
  else if (input.type === "number") spec[input.name] = Number(input.value);
  else spec[input.name] = input.value;
  if (input.name === "model") {
    applyModel(input.value);
  } else if (["task", "sizeMode", "durationMode", "draft", "serviceTier"].includes(input.name)) {
    coerce();
    renderAll();
  }
  schedulePreview();
}

async function onMedia(event) {
  const input = event.target;
  if (input.type !== "file" || !input.files) return;
  const files = [...input.files];
  if (input.name === "images") {
    const limit = current().task === "layers" ? 1 : currentModel().maxRefs;
    const next = current().task === "layers" ? [] : state.media.image.slice();
    for (const file of files) next.push(await readLocal(file));
    state.media.image = next.slice(-limit);
  } else if (input.name === "first" || input.name === "last") {
    state.media[input.name] = await readLocal(files[0]);
  } else if (input.name === "refs") {
    const next = state.media.refs.slice();
    for (const file of files) next.push(await readLocal(file));
    state.media.refs = next.slice(-currentModel().maxRefImages);
  } else if (input.name === "audios") {
    const next = state.media.audios.slice();
    for (const file of files) next.push(await readLocal(file));
    state.media.audios = next.slice(-currentModel().maxRefAudios);
  }
  renderMedia();
  schedulePreview();
}

function onMediaClick(event) {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.add === "videos") {
    const input = $("media").querySelector('input[name="videoUrl"]');
    const url = input.value.trim();
    if (!url) return;
    state.media.videos.push({ id: crypto.randomUUID(), url });
    state.media.videos = state.media.videos.slice(-currentModel().maxRefVideos);
    renderMedia();
    schedulePreview();
    return;
  }
  const group = button.dataset.remove;
  const id = button.dataset.id;
  if (!group) return;
  if (group === "first" || group === "last") state.media[group] = null;
  else state.media[group === "image" ? "image" : group] = state.media[group === "image" ? "image" : group].filter((item) => item.id !== id);
  renderMedia();
  schedulePreview();
}

function readLocal(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = async () => {
      const alpha = file.type === "image/png" && await pngHasAlpha(file) ? 1 : 0;
      const type = file.type || "application/octet-stream";
      resolve({
        id: crypto.randomUUID(),
        name: file.name,
        dataUrl: reader.result,
        placeholder: `data-local:${type};bytes=${file.size};alpha=${alpha}`,
        preview: type.startsWith("image/") ? reader.result : "",
      });
    };
    reader.readAsDataURL(file);
  });
}

async function pngHasAlpha(file) {
  const bytes = new Uint8Array(await file.slice(0, 32).arrayBuffer());
  return bytes.length > 25 && (bytes[25] === 4 || bytes[25] === 6);
}

function specFor(real) {
  if (state.kind === "image") {
    const images = state.media.image.map((item) => (real ? item.dataUrl : item.placeholder)).filter(Boolean);
    return { ...state.image, images };
  }
  const pick = (item) => (item ? (real ? item.dataUrl : item.placeholder) : "");
  return {
    ...state.video,
    firstFrame: pick(state.media.first),
    lastFrame: pick(state.media.last),
    images: state.media.refs.map((item) => (real ? item.dataUrl : item.placeholder)).filter(Boolean),
    videos: state.media.videos.map((item) => item.url),
    audios: state.media.audios.map((item) => (real ? item.dataUrl : item.placeholder)).filter(Boolean),
  };
}

function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(runPreview, 250);
}

async function runPreview() {
  const data = await api("/api/preview", { method: "POST", body: { kind: state.kind, spec: specFor(false) } });
  state.preview = data;
  $("errors").innerHTML = (data.errors || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  $("warnings").innerHTML = (data.warnings || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  $("payload").textContent = JSON.stringify(data.payload || {}, null, 2);
  const missing = realMissing();
  const firstError = (data.errors || [])[0];
  const ready = providerReady();
  const vendorOpen = modelsFor(state.kind, activeVendor()).length > 0;
  $("generate").disabled = state.busy || !vendorOpen || !ready || !data.ok || missing;
  if (!vendorOpen) $("genState").textContent = "这个厂商的模型还在接入。";
  else if (!ready) $("genState").textContent = "还不能生成：先在设置里保存当前模型所属服务商的密钥。";
  else if (missing) $("genState").textContent = "文件还在读取，稍等一下。";
  else if (firstError) $("genState").textContent = firstError;
  else $("genState").textContent = "可以生成。快捷键 ⌘/Ctrl + Enter。";
}

function providerReady() {
  const providerId = currentModel()?.provider || "ark";
  const provider = (state.config?.providers || []).find((item) => item.id === providerId);
  if (!provider) return !!state.config?.hasKey;
  return !!(provider.hasKey || provider.hasSecret);
}

function realMissing() {
  const items = state.kind === "image"
    ? state.media.image
    : [state.media.first, state.media.last, ...state.media.refs, ...state.media.audios].filter(Boolean);
  return items.some((item) => !item.dataUrl);
}

async function generate() {
  if ($("generate").disabled) return;
  state.busy = true;
  $("generate").disabled = true;
  $("genState").textContent = "正在提交…";
  const data = await api("/api/jobs", { method: "POST", body: { kind: state.kind, spec: specFor(true) } });
  state.busy = false;
  if (!data.ok) {
    $("errors").innerHTML = (data.errors || ["生成失败。"]).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    $("genState").textContent = "";
    $("generate").disabled = false;
    if (data.job) showJob(data.job);
    loadJobs();
    return;
  }
  showJob(data.job);
  watch(data.job);
  loadJobs();
  $("genState").textContent = data.job.status === "succeeded" ? "已保存到本地" : "已提交，正在等方舟";
  $("generate").disabled = false;
}

function showJob(job) {
  if (!job) return;
  state.resultShown = true;
  state.shownJob = job;
  const files = job.outputs || [];
  const media = files.map((file) => file.kind === "video"
    ? `<video src="${file.url}" controls></video>`
    : `<img src="${file.url}" alt="">`).join("");
  const error = job.error ? `<p class="error-line">${escapeHtml(job.error)}</p>` : "";
  const status = `<span class="stage-status" title="${escapeHtml(job.remoteId || "")}">${escapeHtml(statusText(job))}</span>`;
  const image = files.find((file) => file.kind === "image");
  const video = files.find((file) => file.kind === "video");
  const primary = video || files[0];
  const saved = primary?.path ? `<span class="saved-path">${escapeHtml(showPath(primary.path))}</span>` : "";
  const actions = `
    ${primary ? fileButton(job, primary, "open") : ""}
    ${primary ? fileButton(job, primary, "reveal") : ""}
    ${image && !video ? `<button type="button" class="ghost" id="toVideo">接着做视频</button>` : ""}
    ${job.prompt ? `<button type="button" class="text-button" id="reusePrompt">用这条提示词</button>` : ""}`;
  const many = files.length > 1 ? " is-multi" : "";
  const emptyMedia = files.length ? "" : `<div class="empty-result is-inset"><strong>${escapeHtml(statusText(job))}</strong><p>${escapeHtml(job.error || "还没有画面。")}</p></div>`;
  $("result").innerHTML = `<section class="stage"><div class="gallery${many}">${media || emptyMedia}</div><div class="stage-bar"><div class="stage-meta">${status}${saved}${error}</div><div class="result-actions">${actions}</div></div></section>`;
  const toVideo = $("toVideo");
  if (toVideo) toVideo.onclick = () => continueToVideo(image, job.prompt || "");
  const reuse = $("reusePrompt");
  if (reuse) reuse.onclick = () => reusePrompt(job);
}

async function continueToVideo(file, prompt) {
  const response = await fetch(file.url);
  const blob = await response.blob();
  const dataUrl = await new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(blob);
  });
  const item = {
    id: crypto.randomUUID(),
    name: file.name,
    dataUrl,
    placeholder: `data-local:${blob.type || "image/png"};bytes=${blob.size};alpha=0`,
    preview: dataUrl,
  };
  const model = modelById("video", state.video.model);
  if (model.maxRefImages > 0) {
    state.media.refs = [item];
    state.video.task = "text";
  } else if (model.tasks.includes("first")) {
    state.media.first = item;
    state.video.task = "first";
  }
  if (prompt && !state.video.prompt) state.video.prompt = prompt;
  setKind("video");
}

function reusePrompt(job) {
  const kind = job.kind === "video" ? "video" : "image";
  state[kind].prompt = job.prompt || "";
  if (state.kind !== kind) setKind(kind);
  else {
    $("prompt").value = state[kind].prompt;
    renderGuide();
    schedulePreview();
  }
}

function fileButton(job, file, mode) {
  const openLabel = file.kind === "video" ? "打开视频" : "打开图片";
  const label = mode === "open" ? openLabel : "在访达中显示";
  const attr = mode === "open" ? "data-open" : "data-reveal";
  const klass = mode === "open" ? "solid" : "ghost";
  return `<button type="button" class="${klass}" ${attr}="${job.id}" data-name="${escapeHtml(file.name)}">${label}</button>`;
}

function watch(job) {
  clearInterval(pollTimer);
  state.followJob = job.id;
  if (job.kind !== "video" || !["running", "queued"].includes(job.status)) return;
  pollTimer = setInterval(async () => {
    const data = await api(`/api/jobs/${job.id}/sync`, { method: "POST" });
    if (!data.job) return;
    if (state.followJob === data.job.id) showJob(data.job);
    loadJobs();
    if (!["running", "queued"].includes(data.job.status)) {
      clearInterval(pollTimer);
      if (state.followJob === data.job.id) {
        $("genState").textContent = data.job.status === "succeeded" ? "已保存到本地" : "生成没有完成";
      }
    }
  }, 5000);
}

async function openHistory() {
  state.page = "projects";
  paintNav();
  await loadProjects();
  state.historyProject = state.historyProject || state.config?.projectId || "default";
  await loadProjectJobs();
  renderProjects();
}

async function loadProjects() {
  const data = await api("/api/projects");
  state.projects = data.projects || [];
  renderProjectMenu();
}

function toggleProjectMenu() {
  if ($("projectMenu").hidden) openProjectMenu();
  else closeProjectMenu();
}

async function openProjectMenu() {
  $("projectSwitch").classList.add("is-open");
  $("projectMenu").hidden = false;
  $("projectChip").setAttribute("aria-expanded", "true");
  if (!state.projects.length) await loadProjects();
  else renderProjectMenu();
}

function closeProjectMenu() {
  $("projectSwitch").classList.remove("is-open");
  $("projectMenu").hidden = true;
  $("projectChip").setAttribute("aria-expanded", "false");
}

function renderProjectMenu() {
  const projects = state.projects || [];
  $("projectMenuList").innerHTML = projects.length
    ? projects.map((project) => `
      <button type="button" class="project-option${project.current ? " is-on" : ""}" data-switch="${project.id}">
        <b>${escapeHtml(project.name)}</b>
        <small>图片 ${project.imageCount} · 视频 ${project.videoCount}</small>
      </button>`).join("")
    : `<p class="media-note">还没有其他项目</p>`;
}

async function switchProject(id) {
  if (!id) return false;
  if (id === state.config?.projectId) {
    closeProjectMenu();
    return true;
  }
  const data = await api("/api/projects/current", { method: "PUT", body: { id } });
  if (!data.ok) return false;
  state.config = data.config || state.config;
  state.projects = data.projects || [];
  state.historyProject = id;
  state.resultShown = false;
  state.shownJob = null;
  state.followJob = "";
  clearInterval(pollTimer);
  paintConfig();
  closeProjectMenu();
  await loadJobs();
  if (state.page === "projects") {
    state.historyKind = "all";
    await loadProjectJobs();
    renderProjects();
  } else {
    renderResultPlaceholder();
  }
  return true;
}

async function loadProjectJobs() {
  const data = await api(`/api/projects/${state.historyProject}/jobs`);
  state.projectJobs = data.jobs || [];
}

async function createProject() {
  const name = $("projectName").value.trim();
  const data = await api("/api/projects", { method: "POST", body: { name } });
  if (!data.ok) {
    $("projectError").textContent = (data.errors || ["没有建成。"])[0];
    return;
  }
  $("projectError").textContent = "";
  $("projectName").value = "";
  state.projects = data.projects || [];
  state.historyProject = data.created || state.historyProject;
  state.historyKind = "all";
  await loadProjectJobs();
  renderProjects();
}

async function useProject() {
  const ok = await switchProject(state.historyProject);
  if (!ok) {
    $("projectError").textContent = "没有切换。";
    return;
  }
  setKind(state.kind);
}

function renderProjects() {
  $("projectList").innerHTML = state.projects.map((project) => `
    <button type="button" data-project="${project.id}" class="${project.id === state.historyProject ? "is-on" : ""}">
      <span class="project-name"><b>${escapeHtml(project.name)}</b>${project.current ? "<em>当前</em>" : ""}</span>
      <small><span>图片 ${project.imageCount}</span><span>视频 ${project.videoCount}</span></small>
    </button>`).join("");
  const project = state.projects.find((item) => item.id === state.historyProject);
  $("projectTitle").textContent = project?.name || "项目";
  const total = (project?.imageCount || 0) + (project?.videoCount || 0);
  const folder = showPath(project?.path);
  $("projectStats").textContent = project
    ? `${total} 条记录 · 图片 ${project.imageCount} · 视频 ${project.videoCount}${folder ? ` · ${folder}` : ""}`
    : "";
  $("useProject").disabled = !project || project.current;
  $("useProject").textContent = project?.current ? "当前创作项目" : "在此项目中创作";
  const counts = {
    all: state.projectJobs.length,
    image: state.projectJobs.filter((job) => job.kind === "image").length,
    video: state.projectJobs.filter((job) => job.kind === "video").length,
  };
  const filters = [["all", "全部"], ["image", "图片"], ["video", "视频"]];
  $("categoryBar").innerHTML = filters.map(([id, label]) => `
    <button type="button" data-filter="${id}" class="${state.historyKind === id ? "is-on" : ""}">${label} ${counts[id]}</button>`).join("");
  renderGroupedHistory();
}

function renderGroupedHistory() {
  const jobs = state.projectJobs.filter((job) => state.historyKind === "all" || job.kind === state.historyKind);
  if (!jobs.length) {
    const label = state.historyKind === "image" ? "图片" : state.historyKind === "video" ? "视频" : "记录";
    $("historyList").innerHTML = `<div class="project-empty"><strong>还没有${label}</strong><p>在这个项目里生成之后，会按任务分组出现在这里。失败和排队中的也会留下。</p></div>`;
    return;
  }
  const groups = new Map();
  jobs.forEach((job) => {
    const key = `${job.kind}:${job.task}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(job);
  });
  $("historyList").innerHTML = [...groups].map(([key, items]) => {
    const [kind, task] = key.split(":");
    const title = `${kind === "video" ? "视频" : "图片"} · ${TASKS[kind]?.[task] || task}`;
    return `<section class="history-group"><h3>${escapeHtml(title)}<span>${items.length}</span></h3>${items.map(historyRow).join("")}</section>`;
  }).join("");
}

async function loadJobs() {
  const data = await api("/api/jobs");
  state.jobs = data.jobs || [];
  paintRail();
}

function historyRow(job) {
  const thumb = (job.outputs || []).find((file) => file.kind === "image");
  const video = (job.outputs || []).find((file) => file.kind === "video");
  const file = video || thumb;
  const when = (job.createdAt || "").replace("T", " ").slice(5, 16);
  const preview = thumb
    ? `<img src="${thumb.url}" alt="">`
    : video
      ? `<video src="${video.url}" muted playsinline preload="metadata"></video>`
      : `<div class="thumb"></div>`;
  const error = job.error ? `<small class="error-line">${escapeHtml(job.error)}</small>` : "";
  return `<article class="history-card">
    <div class="history-poster">
      ${preview}
      <span class="status-pill is-${escapeHtml(job.status || "")}">${escapeHtml(statusText(job))}</span>
    </div>
    <div class="history-copy">
      <b>${escapeHtml(TASKS[job.kind]?.[job.task] || job.task)}</b>
      <small>${escapeHtml(when)} · ${escapeHtml(modelName(job.model))}</small>
      <p>${escapeHtml(job.prompt || "没有提示词")}</p>
      ${error}
    </div>
    <div class="result-actions">
      <button type="button" class="solid" data-view="${job.id}">查看</button>
      ${file ? fileButton(job, file, "open") : ""}
      ${file ? fileButton(job, file, "reveal") : ""}
    </div>
    <details><summary>这次提交的字段</summary><pre>${escapeHtml(JSON.stringify(job.payload || {}, null, 2))}</pre></details>
  </article>`;
}

function modelName(id) {
  const models = [...(state.catalog?.imageModels || []), ...(state.catalog?.videoModels || [])];
  return models.find((item) => item.id === id)?.name || id || "";
}

function statusText(job) {
  return {
    running: "生成中", queued: "排队中", succeeded: "完成", failed: "失败", expired: "已过期", cancelled: "已取消",
  }[job.status] || job.status;
}

function showPath(path) {
  const docs = state.config?.documentsPath || "";
  if (path && docs && (path === docs || path.startsWith(`${docs}/`))) return `文稿${path.slice(docs.length)}`;
  return path || "";
}

function paintRail() {
  const name = state.config?.projectName || "默认项目";
  const count = state.jobs?.length || 0;
  $("historyCount").textContent = count ? `${name} · ${count}` : name;
}

function paintConfig() {
  const config = state.config || {};
  $("projectChipName").textContent = config.projectName || "默认项目";
  renderProjectMenu();
  paintRail();
  const readyProviders = (config.providers || []).filter((item) => item.hasKey || item.hasAccessKey || item.hasSecret);
  $("keychip").textContent = readyProviders.length
    ? readyProviders.map((item) => `${item.name}${item.keyTail || item.accessTail ? ` ···${item.keyTail || item.accessTail}` : " 已配置"}`).join(" · ")
    : "未配置密钥";
  $("keychip").classList.toggle("is-ready", readyProviders.length > 0);
  const library = $("libraryPath");
  if (library && document.activeElement !== library) library.value = config.libraryPath || "";
  library.disabled = !!config.libraryLocked;
  $("pickLibrary").disabled = !!config.libraryLocked;
  const folder = config.libraryDisplay || config.projectDisplay || showPath(config.projectPath);
  $("configMeta").textContent = `当前项目 ${config.projectName || "默认项目"}。成片在 ${folder}。密钥文件 ${config.configPath || ""}。`;
  if (state.catalog) renderGuide();
  runPreview();
}

function renderProviderSettings() {
  const specs = state.catalog?.providers || [];
  const saved = Object.fromEntries((state.config?.providers || []).map((item) => [item.id, item]));
  const fieldLabel = { apiKey: "API Key", baseUrl: "接口地址", accessKey: "Access Key", secretKey: "Secret Key" };
  $("providerSettings").innerHTML = specs.map((spec) => {
    const current = saved[spec.id] || {};
    const fields = (spec.fields || ["apiKey", "baseUrl"]).map((field) => {
      const secret = field !== "baseUrl";
      const value = field === "baseUrl" ? (current.baseUrl || spec.defaultBaseUrl || "") : "";
      const placeholder = secret
        ? (current.hasKey || current.hasAccessKey || current.hasSecret ? "留空表示不修改已保存的密钥" : "还没有保存")
        : "";
      return `<label><span>${fieldLabel[field] || field}</span><input data-provider="${spec.id}" data-field="${field}" type="${secret ? "password" : "url"}" autocomplete="off" value="${escapeHtml(value)}" placeholder="${escapeHtml(placeholder)}"></label>`;
    }).join("");
    const using = current.keySource === "env" ? `<p class="meta">当前实际使用环境变量 ${escapeHtml(spec.envKey || "")}。</p>` : "";
    return `<section class="provider-card"><h3>${escapeHtml(spec.name)}</h3><p class="meta">${escapeHtml(spec.hint || "")}</p>${using}${fields}<button type="button" class="ghost danger" data-clear-provider="${spec.id}">清除此服务商密钥</button></section>`;
  }).join("");
}

function openSettings() {
  $("settingsError").textContent = "";
  renderProviderSettings();
  $("settings").showModal();
}

async function pickLibrary() {
  $("settingsError").textContent = "正在打开文件夹选择窗口…";
  const data = await api("/api/library/pick", { method: "POST" });
  if (!data.ok || !data.path) {
    $("settingsError").textContent = (data.errors || ["没有选择文件夹。"])[0];
    return;
  }
  $("libraryPath").value = data.path;
  $("settingsError").textContent = "";
}

async function saveSettings(event) {
  event.preventDefault();
  const providers = {};
  $("providerSettings").querySelectorAll("[data-provider]").forEach((input) => {
    const id = input.dataset.provider;
    providers[id] = providers[id] || {};
    providers[id][input.dataset.field] = input.value.trim();
  });
  const body = { providers, libraryPath: $("libraryPath").value.trim() };
  const data = await api("/api/config", { method: "PUT", body });
  if (!data.ok) {
    $("settingsError").textContent = (data.errors || ["没有保存。"])[0];
    return;
  }
  state.config = data;
  $("settings").close();
  paintConfig();
  loadJobs();
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    method: options.method || "GET",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok && data.detail && !data.errors) {
    data.errors = [typeof data.detail === "string" ? data.detail : "请求失败。"];
    data.ok = false;
  }
  return data;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}
