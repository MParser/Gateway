let currentLogFile = null;
let currentPageNumber = 1;
let currentPageSize = 100;
let totalPages = 1;
let historyLogViewer = null;
let webSocket = null;
let autoScroll = true; // 默认开启自动滚动
let isDarkTheme = false;
let wsEnabled = true; // WebSocket连接状态
let heartbeatInterval = null; // 心跳定时器
let isManualDisconnect = false; // 是否是手动断开

// 页面加载完成后执行
window.onload = async function () {
  // 获取配置并设置标题
  try {
    const response = await fetch("/logs/config");
    const config = await response.json();
    document.title = config.title;
  } catch (error) {
    console.error("加载配置失败:", error);
  }

  // 初始化其他功能
  historyLogViewer = document.getElementById("historyLogViewer");
  await loadLogFiles();
  initWebSocket();
  // 初始化自动滚动状态
  updateAutoScrollButton();
  // 更新WebSocket按钮状态
  updateWsButton();
  // 加载日志文件列表
  loadLogFiles();
};

const logViewer = document.getElementById("logViewer");
const scrollButton = document.getElementById("scrollButton");
const themeButton = document.getElementById("themeSwitch");
const connectionStatus = document.getElementById("connectionStatus");

function initWebSocket() {
  if (!wsEnabled) return;

  if (webSocket) {
    webSocket.close();
  }

  // 清空现有日志
  clearLogs();

  webSocket = new WebSocket(`ws://${window.location.host}/logs/ws`);

  webSocket.onopen = function () {
    isManualDisconnect = false; // 重置手动断开标志
    updateConnectionStatus(true);
    updateWsButton();
    // 启动心跳
    startHeartbeat();
  };

  webSocket.onmessage = function (event) {
    const logEntry = JSON.parse(event.data);
    const div = document.createElement("div");
    div.className = `log-entry ${logEntry.level}`;
    div.textContent = logEntry.formatted;

    // 保持最多1000条日志
    while (logViewer.children.length >= 1000) {
      logViewer.removeChild(logViewer.firstChild);
    }

    logViewer.appendChild(div);
    if (autoScroll) {
      scrollToBottom();
    }
  };

  webSocket.onclose = function () {
    updateConnectionStatus(false);
    updateWsButton();
    stopHeartbeat();
    // 如果启用了WebSocket且不是手动断开，3秒后尝试重新连接
    if (wsEnabled && !isManualDisconnect) {
      setTimeout(initWebSocket, 3000);
    }
  };

  webSocket.onerror = function (error) {
    updateConnectionStatus(false);
    updateWsButton();
  };
}

function startHeartbeat() {
  stopHeartbeat(); // 先清除可能存在的心跳
  heartbeatInterval = setInterval(() => {
    if (webSocket && webSocket.readyState === WebSocket.OPEN) {
      webSocket.send("heartbeat");
    }
  }, 30000); // 每30秒发送一次心跳
}

function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval);
    heartbeatInterval = null;
  }
}

function toggleAutoScroll() {
  autoScroll = !autoScroll;
  updateAutoScrollButton();
  if (autoScroll) {
    scrollToBottom();
  }
}

function toggleWebSocket() {
  wsEnabled = !wsEnabled;
  if (!wsEnabled) {
    isManualDisconnect = true; // 设置手动断开标志
  }
  updateWsButton();

  if (wsEnabled) {
    isManualDisconnect = false;
    initWebSocket();
  } else {
    if (webSocket) {
      webSocket.close();
      webSocket = null;
    }
    stopHeartbeat();
  }
}

function clearLogs() {
  logViewer.innerHTML = "";
}

function scrollToBottom() {
  if (autoScroll) {
    logViewer.scrollTop = logViewer.scrollHeight;
  }
}

function toggleTheme() {
  isDarkTheme = !isDarkTheme;
  document.body.classList.toggle("dark-theme", isDarkTheme);
  document
    .querySelector(".tab-container")
    .classList.toggle("dark-theme", isDarkTheme);
  const themeButton = document.querySelector(".theme-switch");
  themeButton.classList.toggle("dark", isDarkTheme);
}

function updateConnectionStatus(connected) {
  connectionStatus.className = `connection-status ${
    connected ? "connected" : "disconnected"
  }`;
  connectionStatus.textContent = connected
    ? "已连接"
    : isManualDisconnect
    ? "已断开"
    : "未连接";
}

function updateWsButton() {
  const button = document.getElementById("wsSwitch");
  if (!button) return;

  const isConnected = webSocket && webSocket.readyState === WebSocket.OPEN;
  button.textContent = isConnected ? "断开" : "连接";
  button.classList.remove("connected", "disconnected");
  button.classList.add(isConnected ? "connected" : "disconnected");
}

function updateAutoScrollButton() {
  const button = document.getElementById("scrollButton");
  button.classList.toggle("disabled", !autoScroll);
  button.innerHTML = autoScroll
    ? '<i class="fas fa-scroll"></i> 关闭自动滚动'
    : '<i class="fas fa-scroll"></i> 开启自动滚动';
}

function switchTab(tab) {
  document
    .getElementById("realtimeTab")
    .classList.toggle("active", tab === "realtime");
  document
    .getElementById("historyTab")
    .classList.toggle("active", tab === "history");
  document.getElementById("realtimeView").style.display =
    tab === "realtime" ? "block" : "none";
  document.getElementById("historyView").style.display =
    tab === "history" ? "block" : "none";
  document.getElementById("realtimeControls").style.display =
    tab === "realtime" ? "flex" : "none";
  document.getElementById("selectLogButton").style.display =
    tab === "history" ? "block" : "none";
}

async function showLogFiles() {
  try {
    const response = await fetch("/logs/files");
    const files = await response.json();

    const logFilesList = document.getElementById("logFilesList");
    if (logFilesList) {
      logFilesList.innerHTML = "";

      files.forEach((file) => {
        const div = document.createElement("div");
        div.className = "log-file-item";
        div.onclick = () => loadLogFile(file.filename);

        const infoDiv = document.createElement("div");
        infoDiv.className = "log-file-info";

        const nameDiv = document.createElement("div");
        nameDiv.className = "log-file-name";
        nameDiv.textContent = file.filename;

        const detailsDiv = document.createElement("div");
        detailsDiv.className = "log-file-details";
        detailsDiv.textContent = `创建时间: ${file.ctime}`;

        const sizeDiv = document.createElement("div");
        sizeDiv.className = "log-file-size";
        sizeDiv.textContent = file.size;

        infoDiv.appendChild(nameDiv);
        infoDiv.appendChild(detailsDiv);
        div.appendChild(infoDiv);
        div.appendChild(sizeDiv);

        logFilesList.appendChild(div);
      });
    }

    const modal = document.getElementById("logFilesModal");
    if (modal) {
      modal.style.display = "block";
    }

    // 隐藏分页控件
    const paginationControls = document.querySelector('.pagination-controls');
    if (paginationControls) {
      paginationControls.style.display = 'none';
    }
  } catch (error) {
    console.error("获取日志文件列表失败:", error);
  }
}

function closeModal() {
  document.getElementById("logFilesModal").style.display = "none";
}

async function loadLogFile(filename) {
  try {
    currentLogFile = filename;
    currentPageNumber = 1; // 重置页码
    await loadHistoryLogs();

    // 更新选择按钮文本
    const selectButton = document.getElementById("selectLogButton");
    if (selectButton) {
      selectButton.textContent = `当前日志: ${filename}`;
    }

    // 关闭模态框
    closeModal();

    // 切换到历史日志视图
    switchTab("history");
  } catch (error) {
    console.error("加载日志文件失败:", error);
  }
}

async function loadHistoryLogs() {
  if (!currentLogFile) {
    console.error("未选择日志文件");
    return;
  }

  try {
    // 对文件名进行URL编码
    const encodedFilename = encodeURIComponent(currentLogFile);
    const response = await fetch(
      `/logs/content/${encodedFilename}?page=${currentPageNumber}&page_size=${currentPageSize}`
    );
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();

    if (data.error) {
      console.error("加载日志失败:", data.error);
      return;
    }

    if (historyLogViewer) {
      historyLogViewer.innerHTML = "";
      if (!Array.isArray(data.logs)) {
        console.error("日志数据格式错误");
        return;
      }

      data.logs.forEach((log) => {
        if (!log) return; // 跳过空日志

        const div = document.createElement("div");
        div.className = "log-entry";

        let logText = log;
        // 如果是JSON字符串，尝试解析
        if (typeof log === "string" && log.trim().startsWith("{")) {
          try {
            const logObj = JSON.parse(log);
            logText = logObj.text || log;
          } catch (e) {
            // 如果解析失败，使用原始文本
            logText = log;
          }
        }

        // 移除尾部的换行符
        logText = logText.trim();

        // 解析日志级别并设置样式
        const levelMatch = logText.match(
          /\|\s*(INFO|ERROR|WARNING|DEBUG)\s*\|/
        );
        if (levelMatch) {
          div.classList.add(levelMatch[1].toUpperCase());
        }

        div.textContent = logText;
        historyLogViewer.appendChild(div);
      });
    }

    // 更新分页信息
    totalPages = data.total_pages || 1;
    currentPageNumber = data.current_page || currentPageNumber;
    updatePaginationControls();

    // 显示分页控件
    const paginationControls = document.querySelector('.pagination-controls');
    if (paginationControls) {
      paginationControls.style.display = '';
    }
  } catch (error) {
    console.error("加载日志失败:", error);
    totalPages = 1;
    updatePaginationControls();
  }
}

function updatePaginationControls() {
  const firstPageBtn = document.getElementById("firstPageBtn");
  const prevPageBtn = document.getElementById("prevPageBtn");
  const nextPageBtn = document.getElementById("nextPageBtn");
  const lastPageBtn = document.getElementById("lastPageBtn");
  const currentPageInput = document.getElementById("currentPage");
  const totalPagesSpan = document.getElementById("totalPages");

  if (firstPageBtn) firstPageBtn.disabled = currentPageNumber <= 1;
  if (prevPageBtn) prevPageBtn.disabled = currentPageNumber <= 1;
  if (nextPageBtn) nextPageBtn.disabled = currentPageNumber >= totalPages;
  if (lastPageBtn) lastPageBtn.disabled = currentPageNumber >= totalPages;

  if (currentPageInput) currentPageInput.value = currentPageNumber;
  if (totalPagesSpan) totalPagesSpan.textContent = totalPages;
}

function changePage(action) {
  switch (action) {
    case "first":
      currentPageNumber = 1;
      break;
    case "prev":
      if (currentPageNumber > 1) {
        currentPageNumber--;
      }
      break;
    case "next":
      if (currentPageNumber < totalPages) {
        currentPageNumber++;
      }
      break;
    case "last":
      currentPageNumber = totalPages;
      break;
  }
  loadHistoryLogs();
}

function goToPage(page) {
  const pageNum = parseInt(page);
  if (pageNum >= 1 && pageNum <= totalPages) {
    currentPageNumber = pageNum;
    loadHistoryLogs();
  } else {
    document.getElementById("currentPage").value = currentPageNumber;
  }
}

function changePageSize() {
  const pageSizeSelect = document.getElementById("pageSize");
  if (pageSizeSelect) {
    const newPageSize = parseInt(pageSizeSelect.value);
    if (isNaN(newPageSize) || newPageSize <= 0) {
      console.error("无效的页面大小");
      return;
    }

    // 计算新的页码，保持显示内容的连续性
    const currentStartIndex = (currentPageNumber - 1) * currentPageSize;
    currentPageNumber = Math.floor(currentStartIndex / newPageSize) + 1;
    currentPageSize = newPageSize;

    // 重新加载日志
    loadHistoryLogs();
  }
}

// 启动WebSocket连接
// connectWebSocket();

// 点击模态框外部关闭
window.onclick = function (event) {
  const modal = document.getElementById("logFilesModal");
  if (event.target === modal) {
    closeModal();
  }
};

// 初始化页面大小选择器
function initializePageSize() {
  const pageSizeSelect = document.getElementById("pageSize");
  if (pageSizeSelect) {
    pageSizeSelect.value = currentPageSize.toString();
  }
}

// 页面加载完成后初始化
document.addEventListener("DOMContentLoaded", function () {
  initializePageSize();
});

// 加载日志文件列表
async function loadLogFiles() {
  try {
    // 获取日志文件列表
    const response = await fetch("/logs/files");
    const files = await response.json();

    // 更新文件列表
    const fileList = document.getElementById("logFilesList");
    fileList.innerHTML = "";

    files.forEach((file) => {
      const div = document.createElement("div");
      div.className = "log-file-item";
      div.innerHTML = `
                        <div class="log-file-name" onclick="loadLogFile('${file.filename}')">${file.filename}</div>
                        <div class="log-file-details">
                            <span>创建时间: ${file.ctime}</span>
                            <span>文件大小: ${file.size}</span>
                        </div>
                    `;
      fileList.appendChild(div);
    });
  } catch (error) {
    console.error("加载日志文件列表失败:", error);
  }
}
