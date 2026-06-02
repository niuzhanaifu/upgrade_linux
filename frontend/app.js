const state = {
  activeJobId: null,
  logOffset: 0,
  pollTimer: null,
  selectedFirmwareId: null,
  otaPackages: [],
};

const serviceStatus = document.querySelector("#serviceStatus");
const configList = document.querySelector("#configList");
const logView = document.querySelector("#logView");
const jobMeta = document.querySelector("#jobMeta");
const jobList = document.querySelector("#jobList");
const firmwareList = document.querySelector("#firmwareList");
const firmwareDetails = document.querySelector("#firmwareDetails");
const firmwareCount = document.querySelector("#firmwareCount");
const buildRecordList = document.querySelector("#buildRecordList");
const buildRecordDetails = document.querySelector("#buildRecordDetails");
const buildRecordCount = document.querySelector("#buildRecordCount");
const tabButtons = document.querySelectorAll(".tab-button");
const productViews = document.querySelectorAll(".product-view");
const incrementalBuildButton = document.querySelector("#incrementalBuildButton");
const fullBuildButton = document.querySelector("#fullBuildButton");
const upgradeButton = document.querySelector("#upgradeButton");
const refreshButton = document.querySelector("#refreshButton");
const otaPublishPanel = document.querySelector("#otaPublishPanel");
const otaPackageSelect = document.querySelector("#otaPackageSelect");
const otaPublishPassword = document.querySelector("#otaPublishPassword");
const otaPublishSubmit = document.querySelector("#otaPublishSubmit");
const otaUnpublishSubmit = document.querySelector("#otaUnpublishSubmit");
const otaPublishStatus = document.querySelector("#otaPublishStatus");
const otaPublishHistory = document.querySelector("#otaPublishHistory");
const otaStats = document.querySelector("#otaStats");
const otaRecordList = document.querySelector("#otaRecordList");

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

function switchProductView(targetId) {
  productViews.forEach((view) => {
    const active = view.id === targetId;
    view.classList.toggle("active", active);
    view.hidden = !active;
  });

  tabButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.target === targetId);
  });
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
    ["升级包目录", config.ota_package_dir_configured],
  ];
  configList.innerHTML = rows
    .map(([label, ready]) => {
      const tagClass = ready ? "ready" : "missing";
      const tagText = ready ? "已配置" : "待配置";
      return `<div class="config-row"><strong>${label}</strong><span class="tag ${tagClass}">${tagText}</span></div>`;
    })
    .join("");
  configList.insertAdjacentHTML(
    "beforeend",
    `<div class="config-row"><strong>OTA发布</strong><button class="inline-button" id="showOtaPublishButton" type="button">发布</button></div>`,
  );
  document.querySelector("#showOtaPublishButton").addEventListener("click", showOtaPublishPanel);
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
    upgrade: "获取升级包",
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

function otaRecordStatusText(status) {
  const statusMap = {
    success: "成功",
    failed: "失败",
  };
  return statusMap[status] || status || "-";
}

function otaRecordResultText(record) {
  if (record.status === "success" && record.result_source === "default") {
    return "默认成功";
  }
  if (record.status === "success" && record.result_source === "device") {
    return "设备成功";
  }
  return otaRecordStatusText(record.status);
}

function otaRecordStats(records) {
  const ipSet = new Set();
  const stats = records.reduce(
    (result, record) => {
      result.total += 1;
      if (record.status === "success") {
        result.success += 1;
      }
      if (record.status === "failed") {
        result.failed += 1;
      }
      if (record.result_source === "device") {
        result.reported += 1;
      }
      if (record.ip) {
        ipSet.add(record.ip);
      }
      return result;
    },
    { total: 0, success: 0, failed: 0, reported: 0, unique_ips: 0 },
  );
  stats.unique_ips = ipSet.size;
  return stats;
}

function groupOtaRecordsByVersion(records) {
  const groups = [];
  const groupMap = new Map();
  records.forEach((record) => {
    const version = record.target_version || "未知版本";
    if (!groupMap.has(version)) {
      const group = { version, records: [] };
      groupMap.set(version, group);
      groups.push(group);
    }
    groupMap.get(version).records.push(record);
  });
  return groups.map((group) => ({
    ...group,
    stats: otaRecordStats(group.records),
  }));
}

function renderOtaRecord(record) {
  const status = record.status || (record.success ? "success" : "failed");
  return `
    <div class="ota-record-item ${escapeHtml(status)}">
      <div class="ota-record-main">
        <strong>${escapeHtml(record.ip || "-")}</strong>
        <span class="ota-status ${escapeHtml(status)}">${otaRecordResultText(record)}</span>
      </div>
      <div class="ota-record-grid">
        <span>时间</span><strong>${formatTime(record.requested_at)}</strong>
        <span>板型</span><strong>${escapeHtml(record.board || "-")}</strong>
        <span>当前版本</span><strong>${escapeHtml(record.current_version || "-")}</strong>
        <span>上报</span><strong>${formatTime(record.reported_at)}</strong>
        <span>来源</span><strong>${escapeHtml(record.result_source || "-")}</strong>
      </div>
      <div class="record-path">${escapeHtml(record.package_name || record.report_error || record.reason || "-")}</div>
    </div>
  `;
}

function modeText(mode) {
  return mode === "full" ? "全量" : "增量";
}

function formatSize(size) {
  if (!Number.isFinite(Number(size))) {
    return "-";
  }
  return `${Math.ceil(Number(size) / 1024)} KB`;
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
  if (firmwareCount) {
    firmwareCount.textContent = String(data.firmwares.length);
  }
  if (!data.firmwares.length) {
    firmwareList.innerHTML = `<p class="empty">暂无可下载固件</p>`;
    return;
  }

  firmwareList.innerHTML = data.firmwares
    .map((firmware) => {
      const disabled = firmware.exists ? "" : "disabled";
      const selected = firmware.id === state.selectedFirmwareId ? "selected" : "";
      const href = firmware.exists ? `/api/v1/firmwares/${encodeURIComponent(firmware.id)}/download` : "#";
      const sizeText = firmware.exists ? `${Math.ceil(firmware.size / 1024)} KB` : "文件不存在";
      return `
        <div class="record-item firmware-item ${selected}" data-firmware-id="${escapeHtml(firmware.id)}">
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
  if (buildRecordDetails) {
    buildRecordDetails.dataset.count = String(data.records.length);
  }
  if (buildRecordCount) {
    buildRecordCount.textContent = String(data.records.length);
  }
  if (!data.records.length) {
    buildRecordList.innerHTML = `<p class="empty">暂无编译记录</p>`;
    return;
  }

  buildRecordList.innerHTML = data.records
    .slice(0, 20)
    .map((record) => {
      const selectable = record.status === "succeeded" && record.firmware_exists;
      return `
        <div class="record-item build-record-item ${selectable ? "clickable" : ""}" data-record-id="${escapeHtml(record.id)}" data-selectable="${selectable ? "1" : "0"}">
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

  buildRecordList.querySelectorAll(".build-record-item[data-selectable='1']").forEach((item) => {
    item.addEventListener("click", async () => {
      state.selectedFirmwareId = item.dataset.recordId;
      if (firmwareDetails) {
        firmwareDetails.open = true;
      }
      await loadFirmwares();
      const firmwareItem = Array.from(firmwareList.querySelectorAll("[data-firmware-id]")).find(
        (item) => item.dataset.firmwareId === state.selectedFirmwareId,
      );
      if (firmwareItem) {
        firmwareItem.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    });
  });
}

async function loadOtaUpgradeRecords() {
  const data = await api("/api/v1/ota-upgrade-records");
  const stats = data.stats || {};
  const records = data.records || [];
  const versionGroups = Array.isArray(data.version_groups) ? data.version_groups : groupOtaRecordsByVersion(records);

  otaStats.innerHTML = [
    ["总升级", stats.total || 0],
    ["成功", stats.success || 0],
    ["失败", stats.failed || 0],
    ["已上报", stats.reported || 0],
    ["IP数", stats.unique_ips || 0],
  ]
    .map(
      ([label, value]) => `
        <div class="ota-stat-item">
          <strong>${value}</strong>
          <span>${label}</span>
        </div>
      `,
    )
    .join("");

  if (!versionGroups.length) {
    otaRecordList.innerHTML = `<p class="empty">暂无 OTA 升级请求记录</p>`;
    return;
  }

  otaRecordList.innerHTML = versionGroups
    .map((group) => {
      const groupStats = group.stats || {};
      const groupRecords = group.records || [];
      return `
        <section class="ota-version-group">
          <div class="ota-version-header">
            <strong>目标版本 ${escapeHtml(group.version || "未知版本")}</strong>
            <span>
              总 ${groupStats.total || 0}
              · 成功 ${groupStats.success || 0}
              · 失败 ${groupStats.failed || 0}
              · 已上报 ${groupStats.reported || 0}
              · IP ${groupStats.unique_ips || 0}
            </span>
          </div>
          <div class="ota-version-records">
            ${groupRecords.map(renderOtaRecord).join("")}
          </div>
        </section>
      `;
    })
    .join("");
}

async function showOtaPublishPanel() {
  otaPublishPanel.hidden = false;
  otaPublishStatus.textContent = "正在读取升级包...";
  await Promise.all([loadOtaPackages(), loadOtaPublishHistory()]);
}

async function loadOtaPackages() {
  try {
    const data = await api("/api/v1/ota-packages");
    state.otaPackages = data.packages || [];
    if (!state.otaPackages.length) {
      otaPackageSelect.innerHTML = `<option value="">没有可发布的 OTA 包</option>`;
      otaPublishSubmit.disabled = true;
      otaPublishStatus.textContent = "没有找到符合格式的 OTA 包";
      return;
    }

    otaPackageSelect.innerHTML = state.otaPackages
      .map((item) => {
        const label = `${item.name} · ${item.version} · ${formatSize(item.size)}`;
        return `<option value="${escapeHtml(item.name)}">${escapeHtml(label)}</option>`;
      })
      .join("");
    otaPublishSubmit.disabled = false;
    otaPublishStatus.textContent = `已找到 ${state.otaPackages.length} 个 OTA 包`;
  } catch (error) {
    otaPackageSelect.innerHTML = `<option value="">读取失败</option>`;
    otaPublishSubmit.disabled = true;
    otaPublishStatus.textContent = `读取失败：${error.message}`;
  }
}

async function loadOtaPublishHistory() {
  try {
    const data = await api("/api/v1/ota-publish/history");
    const records = data.records || [];
    if (!records.length) {
      otaPublishHistory.innerHTML = `<p class="empty">暂无发布历史</p>`;
      return;
    }
    otaPublishHistory.innerHTML = records
      .slice(0, 5)
      .map(
        (record) => `
          <div class="publish-history-item">
            <strong>${escapeHtml(record.action === "unpublish" ? "已下架 OTA 发布包" : record.package_name)}</strong>
            <span>${formatTime(record.published_at)} · ${escapeHtml(record.board || "-")} · ${escapeHtml(record.version || record.action || "-")}</span>
          </div>
        `,
      )
      .join("");
  } catch (error) {
    otaPublishHistory.innerHTML = `<p class="empty">读取发布历史失败：${escapeHtml(error.message)}</p>`;
  }
}

async function publishOtaPackage() {
  const packageName = otaPackageSelect.value;
  const password = otaPublishPassword.value;
  if (!packageName) {
    otaPublishStatus.textContent = "请先选择一个 OTA 包";
    return;
  }
  if (!password) {
    otaPublishStatus.textContent = "请输入发布密码";
    return;
  }

  otaPublishSubmit.disabled = true;
  otaPublishStatus.textContent = "正在发布...";
  try {
    const data = await api("/api/v1/ota-publish", {
      method: "POST",
      body: JSON.stringify({ package_name: packageName, password }),
    });
    otaPublishPassword.value = "";
    otaPublishStatus.textContent = `已发布：${data.record.package_name}`;
    logView.textContent = [
      "OTA发布完成",
      `包名：${data.record.package_name}`,
      `版本：${data.record.version}`,
      `源文件：${data.record.source_path}`,
      `发布到：${data.record.publish_path}`,
    ].join("\n");
    await loadOtaPublishHistory();
  } catch (error) {
    otaPublishStatus.textContent = `发布失败：${error.message}`;
  } finally {
    otaPublishSubmit.disabled = !state.otaPackages.length;
  }
}

async function unpublishOtaPackage() {
  const password = otaPublishPassword.value;
  if (!password) {
    otaPublishStatus.textContent = "请输入发布密码";
    return;
  }

  otaUnpublishSubmit.disabled = true;
  otaPublishSubmit.disabled = true;
  otaPublishStatus.textContent = "正在下架...";
  try {
    const data = await api("/api/v1/ota-publish/unpublish", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    otaPublishPassword.value = "";
    otaPublishStatus.textContent = `已下架，删除 ${data.record.removed_count || 0} 个发布文件`;
    logView.textContent = [
      "OTA发布包已下架",
      `板型：${data.record.board}`,
      `发布目录：${data.record.publish_path}`,
      `删除文件数：${data.record.removed_count || 0}`,
      `残留文件数：${(data.record.failed_remove_files || []).length}`,
      "私钥和公钥未改动",
    ].join("\n");
    await loadOtaPublishHistory();
  } catch (error) {
    otaPublishStatus.textContent = `下架失败：${error.message}`;
  } finally {
    otaUnpublishSubmit.disabled = false;
    otaPublishSubmit.disabled = !state.otaPackages.length;
  }
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
    await loadOtaUpgradeRecords();
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
      await loadOtaUpgradeRecords();
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
otaPublishSubmit.addEventListener("click", publishOtaPackage);
otaUnpublishSubmit.addEventListener("click", unpublishOtaPackage);
tabButtons.forEach((button) => {
  button.addEventListener("click", () => switchProductView(button.dataset.target));
});
refreshButton.addEventListener("click", async () => {
  await loadConfig();
  await loadJobs();
  await loadBuildRecords();
  await loadFirmwares();
  await loadOtaUpgradeRecords();
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
loadOtaUpgradeRecords().catch((error) => {
  otaRecordList.innerHTML = `<p class="empty">读取 OTA 升级记录失败：${error.message}</p>`;
});
