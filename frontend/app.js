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
  if (state.activeJobId) {
    await pollLogs();
  }
});

loadConfig();
loadJobs().catch((error) => {
  jobList.innerHTML = `<p class="empty">读取任务失败：${error.message}</p>`;
});
