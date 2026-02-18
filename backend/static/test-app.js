/**
 * 测试页面的UI逻辑
 * 使用 Class 版本的 AppStore
 */

// ===== DOM 元素 =====
const elements = {
    threadId: document.getElementById('threadId'),
    connectBtn: document.getElementById('connectBtn'),
    disconnectBtn: document.getElementById('disconnectBtn'),
    sendBtn: document.getElementById('sendBtn'),
    messageInput: document.getElementById('messageInput'),
    messagesContainer: document.getElementById('messagesContainer'),
    reportContent: document.getElementById('reportContent'),
    connectionStatus: document.getElementById('connectionStatus'),
    welcomeScreen: document.getElementById('welcomeScreen'),
    examplePrompts: document.getElementById('examplePrompts')
};

// ===== 示例提示 =====
const EXAMPLES = [
    { text: '帮我写一份关于AI医疗的报告', label: '🏥 AI医疗报告' },
    { text: '分析2024年新能源汽车市场趋势', label: '🚗 新能源车市场分析' },
    { text: '写一份数字化转型的技术报告', label: '💻 数字化转型报告' },
    { text: '帮我规划一篇关于量子计算的综述', label: '⚛️ 量子计算综述' }
];

// ===== 初始化 =====
function init() {
    renderExamples();
    AppStoreInstance.subscribe(render);
    bindEvents();
    setupTextarea();
}

// ===== 渲染示例 =====
function renderExamples() {
    if (!elements.examplePrompts) return;
    
    elements.examplePrompts.innerHTML = EXAMPLES.map(ex => 
        `<div class="example-item" data-prompt="${ex.text}">${ex.label}</div>`
    ).join('');
    
    document.querySelectorAll('.example-item').forEach(el => {
        el.addEventListener('click', () => {
            elements.messageInput.value = el.dataset.prompt;
            elements.messageInput.focus();
        });
    });
}

// ===== 绑定事件 =====
function bindEvents() {
    elements.connectBtn.addEventListener('click', handleConnect);
    elements.disconnectBtn.addEventListener('click', handleDisconnect);
    elements.sendBtn.addEventListener('click', handleSend);
    
    elements.messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    });
}

// ===== 设置文本域 =====
function setupTextarea() {
    elements.messageInput.addEventListener('input', () => {
        elements.messageInput.style.height = 'auto';
        elements.messageInput.style.height = elements.messageInput.scrollHeight + 'px';
    });
}

// ===== 事件处理 =====
function handleConnect() {
    const threadId = elements.threadId.value.trim();
    if (!threadId) {
        alert('请输入对话ID');
        return;
    }
    
    AppStoreInstance.setState({ threadId });
    AppStoreInstance.connect();
}

function handleDisconnect() {
    AppStoreInstance.disconnect();
}

function handleSend() {
    const content = elements.messageInput.value.trim();
    if (!content) return;
    
    const state = AppStoreInstance.getState();
    
    if (!state.connected) {
        alert('请先连接');
        return;
    }
    
    AppStoreInstance.addUserMessage(content);
    
    const hasHistory = state.messages.length > 0;
    
    if (!hasHistory || state.currentPhase === 'idle') {
        AppStoreInstance.sendMessage('start', { title: content });
    } else {
        AppStoreInstance.sendMessage('message', { content });
    }
    
    elements.messageInput.value = '';
    elements.messageInput.style.height = 'auto';
}

// ===== 渲染UI =====
function render(state) {
    updateConnectionStatus(state.connected);
    updateButtons(state.connected);
    updateThreadId(state.threadId);
    toggleWelcomeScreen(state.connected);
    renderMessages(state.messages);
    renderReportPreview(state.reportSections);
}

// ===== 更新连接状态 =====
function updateConnectionStatus(connected) {
    if (connected) {
        elements.connectionStatus.className = 'status-badge status-connected';
        elements.connectionStatus.textContent = '已连接';
    } else {
        elements.connectionStatus.className = 'status-badge status-disconnected';
        elements.connectionStatus.textContent = '未连接';
    }
}

// ===== 更新按钮状态 =====
function updateButtons(connected) {
    elements.connectBtn.disabled = connected;
    elements.disconnectBtn.disabled = !connected;
    elements.sendBtn.disabled = !connected;
}

// ===== 更新对话ID =====
function updateThreadId(threadId) {
    if (elements.threadId.value !== threadId) {
        elements.threadId.value = threadId;
    }
}

// ===== 切换欢迎界面 =====
function toggleWelcomeScreen(connected) {
    if (connected && elements.welcomeScreen) {
        elements.welcomeScreen.style.display = 'none';
    } else if (!connected && elements.welcomeScreen) {
        elements.welcomeScreen.style.display = 'block';
    }
}

// ===== 渲染消息 =====
function renderMessages(messages) {
    // console.log(messages);
    
    if (!elements.messagesContainer) return;
    
    elements.messagesContainer.innerHTML = '';
    
    messages.forEach(msg => {
        const wrapper = document.createElement('div');
        wrapper.className = 'message-wrapper';
        
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${getMessageClass(msg)}`;
        
        let content = escapeHtml(msg.content);
        content = formatMarkdown(content);
        
        if (msg.streaming) {
            msgDiv.innerHTML = content + '<span class="cursor"></span>';
        } else {
            msgDiv.innerHTML = content;
        }
        
        const timeDiv = document.createElement('div');
        timeDiv.className = `message-time ${msg.role === 'user' ? 'user-time' : ''}`;
        timeDiv.textContent = formatTime(msg.timestamp);
        
        wrapper.appendChild(msgDiv);
        wrapper.appendChild(timeDiv);
        elements.messagesContainer.appendChild(wrapper);
    });
    
    elements.messagesContainer.scrollTop = elements.messagesContainer.scrollHeight;
}

// ===== 获取消息样式 =====
function getMessageClass(msg) {
    if (msg.role === 'user') return 'user-message';
    if (msg.role === 'assistant') {
        return msg.streaming ? 'assistant-message streaming-message' : 'assistant-message';
    }
    if (msg.isError) return 'system-message';
    return 'system-message';
}

// ===== 转义HTML =====
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ===== 格式化Markdown =====
function formatMarkdown(text) {
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/```(.*?)```/gs, '<pre><code>$1</code></pre>')
        .replace(/`(.*?)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>');
}

// ===== 格式化时间 =====
function formatTime(timestamp) {
    if (!timestamp) return '';
    try {
        const date = new Date(timestamp);
        return date.toLocaleTimeString();
    } catch (e) {
        return '';
    }
}

// ===== 渲染报告预览 =====
function renderReportPreview(sections) {
    if (!elements.reportContent) return;
    
    if (!sections || sections.length === 0) {
        elements.reportContent.innerHTML = '<div class="preview-placeholder">等待生成报告...</div>';
        return;
    }
    
    let html = '';
    sections.forEach((section, index) => {
        html += `
            <div class="report-section">
                <div class="section-title">${index + 1}. ${section.title || section}</div>
                <div class="section-content">${section.content || '等待生成...'}</div>
            </div>
        `;
    });
    
    elements.reportContent.innerHTML = html;
}

// ===== 启动应用 =====
init();