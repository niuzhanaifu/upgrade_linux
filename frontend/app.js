const state = {
  activeJobId: null,
  logOffset: 0,
  pollTimer: null,
};

const serviceStatus = document.querySelector("#serviceStatus");
const configList = document.querySelector("#configList");
const logView = document.querySelector("#logView");
const jobMeta = document.querySelector("#jobMeta");
const jobList = document.querySelector("#jobList");
const firmwareList = document.querySelector("#firmwareList");
const buildRecordList = document.querySelector("#buildRecordList");
const incrementalBuildButton = document.querySelector("#incrementalBuildButton");
const fullBuildButton = document.querySelector("#fullBuildButton");
const upgradeButton = document.querySelector("#upgradeButton");
const refreshButton = document.querySelector("#refreshButton");

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep HTTP status message.
    }
    throw new Error(message);
  }
  return response.json();
}

function setServiceStatus(ok, text) {
  serviceStatus.textContent = text;
  serviceStatus.className = `status-pill ${ok ? "ok" : "error"}`;
}

function renderConfig(config) {
  const rows = [
    ["代码仓库", config.repo_configured],
    ["编译脚本", config.build_script_configured],
    ["固件路径", Boolean(config.firmware_path)],
    ["升级命令", config.upgrade_command_configured],
    ["OTA发布", config.ota_firmware_configured],
  ];
  configList.innerHTML = rows
    .map(([label, ready]) => {
      const tagClass = ready ? "ready" : "missing";
      const tagText = ready ? "已配置" : "待配置";
      return `<div class="config-row"><strong>${label}</strong><span class="tag ${tagClass}">${tagText}</span></div>`;
    })
    .join("");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

function jobLabel(job) {
  const kindMap = {
    build: "编译",
    build_incremental: "增量编译",
    build_full: "全量编译",
    upgrade: "升级",
  };
  const kind = kindMap[job.kind] || job.kind;
  const statusMap = {
    queued: "排队中",
    running: "运行中",
    succeeded: "成功",
    failed: "失败",
  };
  return `${kind} · ${statusMap[job.status] || job.status}`;
}

function recordStatusText(status) {
  const statusMap = {
    queued: "排队中",
    running: "运行中",
    succeeded: "成功",
    failed: "失败",
  };
  return statusMap[status] || status || "-";
}

function modeText(mode) {
  return mode === "full" ? "全量" : "增量";
}

function setButtonsBusy(busy) {
  incrementalBuildButton.disabled = busy;
  fullBuildButton.disabled = busy;
  upgradeButton.disabled = busy;
}

async function loadConfig() {
  try {
    const config = await api("/api/v1/config");
    renderConfig(config);
    setServiceStatus(true, "在线");
  } catch (error) {
    setServiceStatus(false, "离线");
    logView.textContent = `无法连接服务：${error.message}`;
  }
}

async function loadJobs() {
  const data = await api("/api/v1/jobs");
  if (!data.jobs.length) {
    jobList.innerHTML = `<p class="empty">暂无历史任务</p>`;
    return;
  }
  jobList.innerHTML = data.jobs
    .slice(0, 8)
    .map((job) => {
      const createdAt = new Date(job.created_at).toLocaleString();
      return `
        <div class="job-item">
          <button type="button" data-job-id="${job.id}">${jobLabel(job)}</button>
          <div class="job-line"><span>${createdAt}</span><span>${job.log_count} 行</span></div>
        </div>
      `;
    })
    .join("");

  jobList.querySelectorAll("button[data-job-id]").forEach((button) => {
    button.addEventListener("click", () => selectJob(button.dataset.jobId));
  });
}

async function loadFirmwares() {
  const data = await api("/api/v1/firmwares");
  if (!data.firmwares.length) {
    firmwareList.innerHTML = `<p class="empty">暂无可下载固件</p>`;
    return;
  }

  firmwareList.innerHTML = data.firmwares
    .map((firmware) => {
      const disabled = firmware.exists ? "" : "disabled";
      const href = firmware.exists ? `/api/v1/firmwares/${encodeURIComponent(firmware.id)}/download` : "#";
      const sizeText = firmware.exists ? `${Math.ceil(firmware.size / 1024)} KB` : "文件不存在";
      return `
        <div class="record-item">
          <div class="record-title">${escapeHtml(firmware.name)}</div>
          <div class="record-line"><span>版本</span><strong>${escapeHtml(firmware.firmware_version || "-")}</strong></div>
          <div class="record-line"><span>类型</span><strong>${modeText(firmware.mode)}</strong></div>
          <div class="record-line"><span>大小</span><strong>${sizeText}</strong></div>
          <div class="record-path">${escapeHtml(firmware.output_dir || "")}</div>
          <a class="download-button ${disabled}" href="${href}">下载</a>
        </div>
      `;
    })
    .join("");
}

async function loadBuildRecords() {
  const data = await api("/api/v1/build-records");
  if (!data.records.length) {
    buildRecordList.innerHTML = `<p class="empty">暂无编译记录</p>`;
    return;
  }

  buildRecordList.innerHTML = data.records
    .slice(0, 20)
    .map((record) => {
      return `
        <div class="record-item">
          <div class="record-title">${modeText(record.mode)}编译 · ${recordStatusText(record.status)}</div>
          <div class="record-line"><span>触发</span><strong>${formatTime(record.created_at)}</strong></div>
          <div class="record-line"><span>结束</span><strong>${formatTime(record.finished_at)}</strong></div>
          <div class="record-line"><span>版本</span><strong>${escapeHtml(record.firmware_version || "-")}</strong></div>
          <div class="record-path">${escapeHtml(record.output_dir || "无输出目录")}</div>
          <div class="record-path">${escapeHtml(record.merged_bin || "无固件路径")}</div>
        </div>
      `;
    })
    .join("");
}

async function startJob(kind) {
  const endpoints = {
    build_incremental: "/api/v1/build/incremental",
    build_full: "/api/v1/build/full",
    upgrade: "/api/v1/upgrade",
  };
  const endpoint = endpoints[kind];
  setButtonsBusy(true);
  logView.textContent = "任务已提交，等待输出...";
  try {
    const data = await api(endpoint, { method: "POST" });
    await selectJob(data.job.id);
    await loadJobs();
    await loadBuildRecords();
    await loadFirmwares();
  } catch (error) {
    logView.textContent = `启动失败：${error.message}`;
    setButtonsBusy(false);
  }
}

async function selectJob(jobId) {
  state.activeJobId = jobId;
  state.logOffset = 0;
  logView.textContent = "";
  clearInterval(state.pollTimer);
  await pollLogs();
  state.pollTimer = setInterval(pollLogs, 1500);
}

async function pollLogs() {
  if (!state.activeJobId) {
    return;
  }
  try {
    const data = await api(`/api/v1/jobs/${state.activeJobId}/logs?offset=${state.logOffset}`);
    const lines = data.lines || [];
    if (lines.length) {
      logView.textContent += `${lines.join("\n")}\n`;
      logView.scrollTop = logView.scrollHeight;
    }
    state.logOffset = data.next_offset;
    jobMeta.textContent = jobLabel(data.job);
    const busy = data.job.status === "queued" || data.job.status === "running";
    setButtonsBusy(busy);
    if (!busy) {
      clearInterval(state.pollTimer);
      await loadJobs();
      await loadBuildRecords();
      await loadFirmwares();
    }
  } catch (error) {
    jobMeta.textContent = "日志读取失败";
    logView.textContent += `\n日志读取失败：${error.message}\n`;
    clearInterval(state.pollTimer);
    setButtonsBusy(false);
  }
}

incrementalBuildButton.addEventListener("click", () => startJob("build_incremental"));
fullBuildButton.addEventListener("click", () => startJob("build_full"));
upgradeButton.addEventListener("click", () => startJob("upgrade"));
refreshButton.addEventListener("click", async () => {
  await loadConfig();
  await loadJobs();
  await loadBuildRecords();
  await loadFirmwares();
  if (state.activeJobId) {
    await pollLogs();
  }
});

loadConfig();
loadJobs().catch((error) => {
  jobList.innerHTML = `<p class="empty">读取任务失败：${error.message}</p>`;
});
loadBuildRecords().catch((error) => {
  buildRecordList.innerHTML = `<p class="empty">读取编译记录失败：${error.message}</p>`;
});
loadFirmwares().catch((error) => {
  firmwareList.innerHTML = `<p class="empty">读取固件失败：${error.message}</p>`;
});
