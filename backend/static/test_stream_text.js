class StreamParser {
    constructor() {
        this.buffer = '';           // 缓冲区
        this.bracketCount = 0;       // 花括号计数
        this.inString = false;       // 是否在字符串内
        this.escape = false;         // 是否转义
        this.partialObjects = [];    // 存储解析出的完整对象

        // 存储不同类型的内容
        this.thinking = [];
        this.outlineItems = [];
        this.partialOutline = '';
        this.status = '';
        this.question = null;
    }

    // 处理每个数据块
    feed(chunk) {
        // 将新数据添加到缓冲区
        this.buffer += chunk;
        if (this.isProcessing) {
            this.needProcess = true;
            return;
        }

        this.isProcessing = true;
        let results = [];
        let currentObject = '';
        let i = 0;

        this.bracketCount = 0;
        console.log("======================");
        
        while (i < this.buffer.length) {
            const char = this.buffer[i];

            // 处理转义字符
            if (char === '\\' && !this.escape) {
                this.escape = true;
                currentObject += char;
                i++;
                continue;
            }

            // 处理字符串开始/结束
            if (char === '"' && !this.escape) {
                this.inString = !this.inString;
            }

            // 处理花括号
            if (!this.inString) {
                if (char === '{') {
                    console.log("007...");
                    
                    this.bracketCount++;
                } else if (char === '}') {
                    console.log("008...");
                    
                    this.bracketCount--;
                }
            }

            // console.log(this.bracketCount, "001...", currentObject);

            currentObject += char;
            if(this.bracketCount === 0){
                console.log(currentObject, "009...");
                
            }
            // 如果花括号配对完成，说明收到了一个完整的JSON对象
            if (this.bracketCount === 0 && currentObject.trim().startsWith('{') && currentObject.trim().endsWith('}')) {
                try {
                    const parsed = JSON.parse(currentObject);
                    results.push(parsed);
                    this.processParsedObject(parsed);
                    currentObject = '';
                } catch (e) {
                    // 解析失败，可能还需要更多数据
                    console.log('等待更多数据...');
                }
            }

            // 重置转义标志
            if (this.escape) {
                this.escape = false;
            }

            i++;
        }

        // 保存未完成的部分
        this.buffer = currentObject;

        this.isProcessing = false;
        if (this.needProcess) {
            this.needProcess = false;
            this.feed('');
        }
        console.log(results);

        return results;
    }

    // 处理解析出的完整对象
    processParsedObject(obj) {
        const { type, content, index, total, options, state } = obj;

        switch (type) {
            case 'thinking':
                this.thinking.push(content);
                this.updateUI('thinking', this.thinking);
                break;

            case 'outline':
                if (index && total) {
                    // 完整的大纲项
                    if (!this.outlineItems[index - 1]) {
                        this.outlineItems[index - 1] = {
                            index,
                            total,
                            content: ''
                        };
                    }
                    this.outlineItems[index - 1].content += content;
                    this.partialOutline = ''; // 清空部分内容
                    this.updateUI('outline', this.outlineItems);
                } else {
                    // 部分大纲内容
                    this.partialOutline += content;
                    this.updateUI('outline_partial', {
                        items: this.outlineItems,
                        partial: this.partialOutline,
                        nextIndex: this.outlineItems.length + 1
                    });
                }
                break;

            case 'status':
                this.status = state;
                this.updateUI('status', state);
                break;

            case 'question':
                this.question = { content, options };
                this.updateUI('question', this.question);
                break;
        }
    }

    // 更新UI（根据您的前端框架实现）
    updateUI(type, data) {
        console.log(`更新UI - ${type}:`, data);
        // 这里调用您的渲染函数
        if (window.streamDisplay) {
            window.streamDisplay.handleUpdate(type, data);
        }
    }
}

// UI显示类
class StreamDisplay {
    constructor() {
        this.thinkingEl = document.getElementById('thinking');
        this.outlineEl = document.getElementById('outline');
        this.statusEl = document.getElementById('status');
        this.questionEl = document.getElementById('question');

        this.outlineItems = [];
        this.partialOutline = '';
    }

    handleUpdate(type, data) {
        switch (type) {
            case 'thinking':
                this.renderThinking(data);
                break;

            case 'outline':
                this.outlineItems = data;
                this.renderOutline();
                break;

            case 'outline_partial':
                this.outlineItems = data.items;
                this.partialOutline = data.partial;
                this.renderOutline(true);
                break;

            case 'status':
                this.renderStatus(data);
                break;

            case 'question':
                this.renderQuestion(data);
                break;
        }
    }

    renderThinking(thinking) {
        if (!this.thinkingEl) return;

        if (thinking.length === 0) {
            this.thinkingEl.innerHTML = '';
            return;
        }

        const html = `
            <div class="thinking-section">
                <h4>🤔 AI思考中</h4>
                ${thinking.map(t => `
                    <div class="thought-item">${t}</div>
                `).join('')}
            </div>
        `;
        this.thinkingEl.innerHTML = html;
    }

    renderOutline(isPartial = false) {
        if (!this.outlineEl) return;

        let html = `
            <div class="outline-section">
                <h4>📋 生成的大纲</h4>
        `;

        // 渲染完整的大纲项
        this.outlineItems.filter(item => item).forEach((item, idx) => {
            html += `
                <div class="outline-item">
                    <span class="outline-number">${idx + 1}.</span>
                    <span class="outline-content">${item.content}</span>
                </div>
            `;
        });

        // 如果有部分内容，渲染正在生成的项
        if (this.partialOutline) {
            const nextIndex = this.outlineItems.length + 1;
            html += `
                <div class="outline-item generating">
                    <span class="outline-number">${nextIndex}.</span>
                    <span class="outline-content partial">${this.partialOutline}</span>
                    <span class="cursor">|</span>
                </div>
            `;
        }

        html += '</div>';
        this.outlineEl.innerHTML = html;

        // 自动滚动到底部
        this.outlineEl.scrollTop = this.outlineEl.scrollHeight;
    }

    renderStatus(status) {
        if (!this.statusEl) return;

        if (status === 'outlined') {
            this.statusEl.innerHTML = '<div class="status">✅ 大纲生成完成</div>';
        }
    }

    renderQuestion(question) {
        if (!this.questionEl) return;

        const html = `
            <div class="question-section">
                <p class="question-text">❓ ${question.content}</p>
                <div class="options">
                    ${question.options.map(opt => `
                        <button class="option-btn" onclick="window.handleOption('${opt}')">
                            ${opt}
                        </button>
                    `).join('')}
                </div>
            </div>
        `;
        this.questionEl.innerHTML = html;
    }
}

// 使用示例
// const parser = new StreamParser();
// window.streamDisplay = new StreamDisplay();

// 模拟WebSocket接收分片数据
const simulateStream = async () => {
    const chunks = [
        '{', '\n', ' ', '"', 'type', '"', ':', ' ', '"', 'thinking', '"', ',', '\n',
        ' ', '"', 'content', '"', ':', ' ', '"', '用户需要一份', 'AI医疗报告', '，这是一个', '技术与应用结合', '的热门主题。', '需要从定义背景', '、核心技术、应用场景、面临', '挑战和未来趋势', '五个维度构建结构', '化报告。', '"', '\n', '}',

        '{', '\n', ' ', '"', 'type', '"', ':', ' ', '"', 'thinking', '"', ',', '\n',
        ' ', '"', 'content', '"', ':', ' ', '"', 'AI', '医疗报告应体现', '专业性与可', '读性平衡，涵盖', '技术原理（如机器', '学习、深度学习）与', '实际落地场景（如影像', '诊断、药物研发', '），同时不回避数据', '安全、伦理等', '关键挑战。', '"', '\n', '}',

        '{', '\n', ' ', '"', 'type', '"', ':', ' ', '"', 'outline', '"', ',', ' ', '"', 'content', '"', ':', ' ', '"', '1. ', ' 引言：AI医疗', '的定义与发展背景', '", ', '"index"', ': ', '1', ', ', '"total"', ': ', '5', '\n', '}',

        '{', '\n', ' ', '"', 'type', '"', ':', ' ', '"', 'outline', '"', ',', ' ', '"', 'content', '"', ':', ' ', '"', '2. ', ' 核心技术：机器学习', '与深度学习在医疗中的', '应用', '", ', '"index"', ': ', '2', ', ', '"total"', ': ', '5', '\n', '}'
    ];

    for (const chunk of chunks) {
        parser.feed(chunk);
        await new Promise(r => setTimeout(r, 50)); // 模拟延迟
    }
};

// 启动模拟
// simulateStream();