// frontend/app.js

const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
const AGENT_API_URL = isLocal ? "http://127.0.0.1:8000/api" : `${window.location.origin}/api`;
const CRM_API_URL = isLocal ? "http://127.0.0.1:8001/api" : `${window.location.origin}/api/crm`;

// Conversation context memory: nhớ người đang nói chuyện
let conversationContext = {
    lastMatchedId: null,    // ID của record đang được đề cập
    lastMatchedName: null,  // Tên hiển thị
};

// Conversation history: lưu các lượt hội thoại trước đó
let conversationHistory = [];

// DOM Elements
const savingsAlertsList = document.getElementById("savings-alerts-list");
const oppAlertsList = document.getElementById("opp-alerts-list");
const savingsCount = document.getElementById("savings-count");
const opportunitiesCount = document.getElementById("opportunities-count");
const traceTerminal = document.getElementById("trace-terminal");
const chatMessagesContainer = document.getElementById("chat-messages-container");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const clearChatBtn = document.getElementById("clear-chat-btn");
const roleSelect = document.getElementById("role-select");
const quickChips = document.querySelectorAll(".chip");

// Write logs into UI Terminal
function appendTraceLog(text, type = "system") {
    const timestamp = new Date().toLocaleTimeString();
    const line = document.createElement("div");
    line.className = `terminal-line ${type}-line`;

    let prefix = "[System]";
    if (type === "api") prefix = "[CRM API]";
    if (type === "mcp") prefix = "[MCP Server]";

    line.innerText = `[${timestamp}] ${prefix} ${text}`;
    traceTerminal.appendChild(line);
    traceTerminal.scrollTop = traceTerminal.scrollHeight;
}

// Fetch CRM data to update Left Dashboard
async function loadCRMAlerts() {
    appendTraceLog("Refreshing CRM Sandbox Dashboard alerts...", "api");
    try {
        // 1. Fetch Savings due in 7 days
        const savingsResp = await fetch(`${CRM_API_URL}/customers?due_within_days=7`);
        if (savingsResp.ok) {
            const savings = await savingsResp.json();
            savingsCount.innerText = `${savings.length} Đang chờ`;
            savingsAlertsList.innerHTML = "";

            if (savings.length === 0) {
                savingsAlertsList.innerHTML = `<li class="loading-placeholder">Không có sổ tiết kiệm nào sắp đến hạn.</li>`;
            } else {
                savings.forEach(customer => {
                    const li = document.createElement("li");
                    li.className = "alert-item";
                    li.innerHTML = `
                        <div class="item-top">
                            <span class="item-name">${customer.name} (${customer.type})</span>
                            <span class="item-date badge badge-warning">Hạn: ${customer.savings_due_date}</span>
                        </div>
                        <p class="item-desc">Số dư sổ tiết kiệm: <strong>${customer.savings_balance.toLocaleString()} VND</strong></p>
                        <div class="item-bottom">
                            <span>SĐT: ${customer.phone}</span>
                            <span>Sản phẩm: Tiết kiệm</span>
                        </div>
                    `;
                    savingsAlertsList.appendChild(li);
                });
            }
            appendTraceLog(`Successfully loaded ${savings.length} savings alerts.`, "api");
        }

        // 2. Fetch Opportunities
        // We will query KH001, KH002, KH003 opportunities to show as cross-sell recommendation
        const oppsList = [];
        const customers = ["KH001", "KH002", "KH003"];
        for (const cid of customers) {
            const oppResp = await fetch(`${CRM_API_URL}/customers/${cid}/opportunities`);
            if (oppResp.ok) {
                const opps = await oppResp.json();
                oppsList.push(...opps);
            }
        }

        opportunitiesCount.innerText = `${oppsList.length} Gợi ý`;
        oppAlertsList.innerHTML = "";

        if (oppsList.length === 0) {
            oppAlertsList.innerHTML = `<li class="loading-placeholder">Không có cơ hội bán chéo nào.</li>`;
        } else {
            oppsList.forEach(opp => {
                const li = document.createElement("li");
                li.className = "opp-item";

                // Get customer name from ID
                let cname = opp.customer_id === "KH001" ? "Lê Văn Khang" :
                    opp.customer_id === "KH002" ? "Trần Thị Bình" : "Lê Hoàng Nam";

                li.innerHTML = `
                    <div class="item-top">
                        <span class="item-name">${cname}</span>
                        <span class="badge badge-info">${opp.stage}</span>
                    </div>
                    <p class="item-desc">Gợi ý sản phẩm: <strong>${opp.product_name}</strong></p>
                    <div class="item-bottom">
                        <span>Giá trị: ${opp.expected_revenue.toLocaleString()} VND</span>
                        <span>Độ ưu tiên: Cao</span>
                    </div>
                `;
                oppAlertsList.appendChild(li);
            });
        }
        appendTraceLog(`Loaded ${oppsList.length} cross-sell opportunities.`, "api");
    } catch (err) {
        appendTraceLog(`Failed to fetch CRM data: ${err.message}`, "system");
    }
}

// Typing Indicator
function showTypingIndicator() {
    const indicator = document.createElement("div");
    indicator.className = "message message-ai typing-indicator-msg";
    indicator.id = "typing-indicator";
    indicator.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content-wrapper">
            <div class="message-content">
                <div class="typing-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        </div>
    `;
    chatMessagesContainer.appendChild(indicator);
    chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
}

function removeTypingIndicator() {
    const indicator = document.getElementById("typing-indicator");
    if (indicator) indicator.remove();
}

// Copy Action Helper
window.copyToClipboard = function (text, buttonEl) {
    navigator.clipboard.writeText(text).then(() => {
        const originalText = buttonEl.innerText;
        buttonEl.innerText = "✓ Đã sao chép";
        setTimeout(() => {
            buttonEl.innerText = originalText;
        }, 2000);
    });
};

// CRM Update Action Helper
window.saveDraftToCRM = async function (customerId, type, content, buttonEl) {
    appendTraceLog(`RM clicked [Ghi nhận CRM] for customer ${customerId}`, "system");
    try {
        let endpoint = type === 'email' ? 'draft-email' : 'call-script';
        let payload = {
            customer_id: customerId,
            rm_name: "Nguyễn Phương Linh"
        };

        if (type === 'email') {
            payload.subject = "[Bank A] Bản nháp chăm sóc khách hàng";
            payload.body = content;
        } else {
            payload.script_content = content;
        }

        buttonEl.disabled = true;
        buttonEl.innerText = "Đang lưu...";

        const resp = await fetch(`${CRM_API_URL}/${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (resp.ok) {
            appendTraceLog(`Successfully saved ${type} draft to CRM for KH: ${customerId}`, "api");
            buttonEl.innerText = "✓ Đã ghi nhận CRM";
            buttonEl.style.backgroundColor = "rgba(16, 185, 129, 0.2)";
            buttonEl.style.color = "#10b981";
            buttonEl.style.borderColor = "#10b981";
            loadCRMAlerts(); // Refresh Alerts dashboard list
        } else {
            buttonEl.disabled = false;
            buttonEl.innerText = "Lỗi khi ghi";
            appendTraceLog(`CRM update error: status ${resp.status}`, "system");
        }
    } catch (err) {
        buttonEl.disabled = false;
        buttonEl.innerText = "Lỗi mạng";
        appendTraceLog(`CRM network error: ${err.message}`, "system");
    }
};

// Send user query to Backend Agent Orchestrator
async function sendUserMessage(message) {
    if (!message.trim()) return;

    // Add user message bubble
    const userMsgHTML = `
        <div class="message message-user">
            <div class="message-avatar">PL</div>
            <div class="message-content-wrapper">
                <div class="message-content">${message}</div>
                <span class="message-time">Bởi RM</span>
            </div>
        </div>
    `;
    chatMessagesContainer.insertAdjacentHTML('beforeend', userMsgHTML);
    chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;

    chatInput.value = "";

    // Show AI typing status
    showTypingIndicator();

    appendTraceLog(`Sending query to Agent Backend: "${message}"`);

    try {
        const response = await fetch(`${AGENT_API_URL}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: message,
                rm_name: "Nguyễn Phương Linh",
                role: roleSelect ? roleSelect.value : "rm",  // ← vai trò từ dropdown (RBAC)
                customer_id: conversationContext.lastMatchedId,  // ← gửi context cũ
                history: conversationHistory  // ← các lượt TRƯỚC, chưa gồm tin hiện tại
            })
        });

        removeTypingIndicator();

        if (response.ok) {
            const data = await response.json();

            // ── Lưu lại lượt hội thoại vào conversationHistory ──────────────
            conversationHistory.push({ role: 'user', content: message });
            conversationHistory.push({ role: 'assistant', content: data.response });

            // ── Cập nhật conversation context ──────────────────────────────
            if (data.matched_customer_id && data.matched_customer_id !== "N/A") {
                conversationContext.lastMatchedId = data.matched_customer_id;
                conversationContext.lastMatchedName = data.matched_customer_id;
                // Hiển thị badge "đang nói về ai" trên chat input
                const ctxBadge = document.getElementById("context-badge");
                if (ctxBadge) {
                    ctxBadge.textContent = `📌 Đang xem: ${data.matched_customer_id}`;
                    ctxBadge.style.display = "inline-block";
                }
            }

            // Output trace logs from Backend to UI console
            if (data.trace_logs) {
                data.trace_logs.forEach(log => {
                    if (log.includes("MCP")) {
                        appendTraceLog(log, "mcp");
                    } else if (log.includes("GET") || log.includes("POST")) {
                        appendTraceLog(log, "api");
                    } else {
                        appendTraceLog(log, "system");
                    }
                });
            }

            // Generate AI bubble
            const messageId = `msg-${Date.now()}`;
            const aiMsgEl = document.createElement("div");
            aiMsgEl.className = "message message-ai";
            aiMsgEl.innerHTML = `
                <div class="message-avatar">🤖</div>
                <div class="message-content-wrapper">
                    <div class="message-content">
                        <div class="message-text" id="${messageId}"></div>
                        <div class="message-actions" id="actions-${messageId}"></div>
                    </div>
                    <span class="message-time">Bởi AI Co-Pilot</span>
                </div>
            `;
            chatMessagesContainer.appendChild(aiMsgEl);

            // Render markdown content
            document.getElementById(messageId).innerHTML = marked.parse(data.response);

            // Add custom utility action buttons for Email or Phone Scripts
            const actionsArea = document.getElementById(`actions-${messageId}`);

            // Detect if response contains email or scripts and add CRM/Copy triggers dynamically
            if (data.matched_customer_id) {
                const actionType = data.action_required || "email";
                const actionLabel = actionType === "email" ? "Ghi nhận CRM" : "Lưu Script";

                actionsArea.innerHTML = `
                    <button class="btn-action" onclick="copyToClipboard(document.getElementById('${messageId}').innerText, this)">Copy toàn bộ</button>
                    <button class="btn-action" onclick="saveDraftToCRM('${data.matched_customer_id}', '${actionType}', document.getElementById('${messageId}').innerText, this)">${actionLabel}</button>
                `;
            }

            chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;

        } else {
            appendTraceLog(`Agent Backend returned error code ${response.status}`, "system");
            const errorMsgHTML = `
                <div class="message message-ai">
                    <div class="message-avatar">🤖</div>
                    <div class="message-content-wrapper">
                        <div class="message-content">Rất tiếc, máy chủ AI Backend hiện tại đang bận hoặc gặp sự cố kết nối. Vui lòng thử lại sau!</div>
                    </div>
                </div>
            `;
            chatMessagesContainer.insertAdjacentHTML('beforeend', errorMsgHTML);
        }
    } catch (err) {
        removeTypingIndicator();
        appendTraceLog(`Network/Connection failure: ${err.message}`, "system");
    }
}

// Send trigger
sendBtn.addEventListener("click", () => {
    sendUserMessage(chatInput.value);
});

chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
        sendUserMessage(chatInput.value);
    }
});

// Clear chat history
clearChatBtn.addEventListener("click", () => {
    conversationHistory = [];
    chatMessagesContainer.innerHTML = `
        <div class="message message-ai">
            <div class="message-avatar">🤖</div>
            <div class="message-content-wrapper">
                <div class="message-content">Hội thoại đã được xóa. Tôi sẵn sàng hỗ trợ bạn thực hiện các tác vụ tiếp theo!</div>
            </div>
        </div>
    `;
});

// Quick Chips listeners
quickChips.forEach(chip => {
    chip.addEventListener("click", () => {
        const query = chip.getAttribute("data-query");
        sendUserMessage(query);
    });
});

// Initial load
window.addEventListener("load", () => {
    appendTraceLog("Web UI loaded. Fetching database components...");
    loadCRMAlerts();
});

// Settings Modal DOM Elements
const openSettingsBtn = document.getElementById("open-settings-btn");
const settingsModal = document.getElementById("settings-modal");
const closeSettingsBtn = document.getElementById("close-settings-btn");

const databaseFileInput = document.getElementById("database-file-input");
const selectDatabaseBtn = document.getElementById("select-database-btn");
const databaseFileName = document.getElementById("database-file-name");
const uploadDatabaseBtn = document.getElementById("upload-database-btn");

const modalStatusMsg = document.getElementById("modal-status-msg");

// Toggle Settings Modal
openSettingsBtn.addEventListener("click", () => {
    settingsModal.classList.add("active");
    modalStatusMsg.style.display = "none";
});

closeSettingsBtn.addEventListener("click", () => {
    settingsModal.classList.remove("active");
});

// Close modal if clicking outside content
window.addEventListener("click", (e) => {
    if (e.target === settingsModal) {
        settingsModal.classList.remove("active");
    }
});

// Database Upload File Binding
selectDatabaseBtn.addEventListener("click", () => {
    databaseFileInput.click();
});

databaseFileInput.addEventListener("change", () => {
    if (databaseFileInput.files.length > 0) {
        databaseFileName.innerText = databaseFileInput.files[0].name;
        uploadDatabaseBtn.disabled = false;
    } else {
        databaseFileName.innerText = "Chưa chọn file";
        uploadDatabaseBtn.disabled = true;
    }
});

uploadDatabaseBtn.addEventListener("click", async () => {
    const file = databaseFileInput.files[0];
    if (!file) return;

    uploadDatabaseBtn.disabled = true;
    uploadDatabaseBtn.innerText = "Đang tải...";
    showModalStatus("Đang tải cơ sở dữ liệu lên...", "info");

    const appendCheckbox = document.getElementById("append-data-checkbox");
    const isAppend = appendCheckbox ? appendCheckbox.checked : false;

    const formData = new FormData();
    formData.append("file", file);

    try {
        const response = await fetch(`${AGENT_API_URL}/upload-database?append=${isAppend}`, {
            method: "POST",
            body: formData
        });
        const result = await response.json();

        if (response.ok && result.status === "success") {
            showModalStatus(result.message, "success");
            appendTraceLog(`Đã nạp thành công CSDL mới: ${file.name}!`, "system");
            databaseFileInput.value = "";
            databaseFileName.innerText = "Chưa chọn file";
            if (appendCheckbox) appendCheckbox.checked = false;
            loadCRMAlerts();
        } else {
            showModalStatus(result.detail || "Upload thất bại", "error");
        }
    } catch (err) {
        showModalStatus(`Lỗi kết nối server: ${err.message}`, "error");
    } finally {
        uploadDatabaseBtn.disabled = false;
        uploadDatabaseBtn.innerText = "Tải lên";
    }
});

const clearDatabaseBtn = document.getElementById("clear-database-btn");
if (clearDatabaseBtn) {
    clearDatabaseBtn.addEventListener("click", async () => {
        if (!confirm("Bạn có chắc chắn muốn xóa toàn bộ dữ liệu tùy biến đã nạp và quay về CSDL mặc định của Bank A không?")) {
            return;
        }

        clearDatabaseBtn.disabled = true;
        clearDatabaseBtn.innerText = "Đang xóa...";
        showModalStatus("Đang dọn dẹp cơ sở dữ liệu...", "info");

        try {
            const response = await fetch(`${AGENT_API_URL}/upload-database`, {
                method: "DELETE"
            });
            const result = await response.json();

            if (response.ok && result.status === "success") {
                showModalStatus(result.message, "success");
                appendTraceLog("Đã dọn dẹp CSDL tùy biến, khôi phục CSDL mặc định!", "system");
                loadCRMAlerts();
            } else {
                showModalStatus(result.detail || "Xóa thất bại", "error");
            }
        } catch (err) {
            showModalStatus(`Lỗi kết nối server: ${err.message}`, "error");
        } finally {
            clearDatabaseBtn.disabled = false;
            clearDatabaseBtn.innerText = "🗑️ Xóa toàn bộ dữ liệu";
        }
    });
}

function showModalStatus(text, type) {
    modalStatusMsg.innerText = text;
    modalStatusMsg.className = `modal-status-message ${type}`;
    modalStatusMsg.style.display = "block";

    if (type === "info") {
        modalStatusMsg.style.background = "rgba(59, 130, 246, 0.15)";
        modalStatusMsg.style.border = "1px solid rgba(59, 130, 246, 0.3)";
        modalStatusMsg.style.color = "#60a5fa";
    }
}
