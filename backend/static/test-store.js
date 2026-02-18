/**
 * 测试页面的状态管理
 * 使用 Class 写法，更清晰的结构
 */

class AppStore {
    // ===== 私有属性 =====
    #state = {
        ws: null,
        threadId: 'test-123',
        connected: false,
        messages: [],
        currentStreamingId: null,
        currentStreamingContent: '',
        currentPhase: 'idle', // idle, planning, writing, reviewing
        pendingType: null, // outline, section
        reportSections: [],
        agentStatus: 'unknown'
    };
    
    #subscribers = [];
    
    // ===== 构造函数 =====
    constructor() {
        this.#loadFromStorage();
    }
    
    // ===== 私有方法 =====
    #loadFromStorage() {
        try {
            const saved = localStorage.getItem('appState');
            if (saved) {
                const parsed = JSON.parse(saved);
                this.#state.threadId = parsed.threadId || 'test-123';
            }
        } catch (e) {
            console.error('加载存储失败:', e);
        }
    }
    
    #saveToStorage() {
        try {
            localStorage.setItem('appState', JSON.stringify({
                threadId: this.#state.threadId
            }));
        } catch (e) {
            console.error('保存存储失败:', e);
        }
    }
    
    #notify() {
        this.#subscribers.forEach(callback => callback(this.getState()));
    }
    
    // ===== 公共方法 =====
    
    /**
     * 订阅状态变化
     * @param {Function} callback - 回调函数，接收新状态
     * @returns {Function} 取消订阅的函数
     */
    subscribe(callback) {
        this.#subscribers.push(callback);
        return () => {
            this.#subscribers = this.#subscribers.filter(cb => cb !== callback);
        };
    }
    
    /**
     * 获取当前状态的副本
     * @returns {Object} 状态副本
     */
    getState() {
        return { ...this.#state };
    }
    
    /**
     * 更新状态
     * @param {Object|Function} newState - 新状态或更新函数
     * @param {boolean} notify - 是否通知订阅者
     */
    setState(newState, notify = true) {
        if (typeof newState === 'function') {
            // 函数式更新
            const prevState = this.getState();
            const updates = newState(prevState);
            this.#state = { ...this.#state, ...updates };
        } else {
            // 直接对象更新
            this.#state = { ...this.#state, ...newState };
        }
        
        this.#saveToStorage();
        
        if (notify) {
            this.#notify();
        }
    }
    
    /**
     * 连接 WebSocket
     */
    connect() {
        if (this.#state.ws) return;
        
        const wsUrl = `ws://${window.location.host}/ws/${this.#state.threadId}`;
        const ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            this.setState({ 
                ws, 
                connected: true,
                currentPhase: 'idle'
            });
        };
        
        ws.onclose = () => {
            this.setState({ 
                ws: null, 
                connected: false,
                currentStreamingId: null,
                currentStreamingContent: ''
            });
        };
        
        ws.onerror = (error) => {
            console.error('WebSocket错误:', error);
            this.setState({ 
                ws: null, 
                connected: false 
            });
        };
        
        ws.onmessage = (event) => {
            try {
                
                const data = JSON.parse(event.data);

                this.#dispatch(data);
            } catch (e) {
                console.error('解析消息失败', e);
            }
        };
    }
    
    /**
     * 断开 WebSocket
     */
    disconnect() {
        if (this.#state.ws) {
            this.#state.ws.close();
        }
    }
    
    /**
     * 发送消息到后端
     * @param {string} type - 消息类型
     * @param {Object} data - 消息数据
     * @returns {boolean} 是否发送成功
     */
    sendMessage(type, data = {}) {
        if (!this.#state.ws || this.#state.ws.readyState !== WebSocket.OPEN) {
            console.error('WebSocket未连接');
            return false;
        }
        
        const message = {
            type,
            data,
            request_id: 'req_' + Math.random().toString(36).substr(2, 9)
        };
        
        this.#state.ws.send(JSON.stringify(message));
        return true;
    }
    
    /**
     * 添加用户消息
     * @param {string} content - 消息内容
     */
    addUserMessage(content) {
        this.setState(prev => ({
            messages: [...prev.messages, {
                id: 'user_' + Date.now(),
                role: 'user',
                content,
                streaming: false,
                timestamp: new Date().toISOString()
            }]
        }));
    }
    
    /**
     * 清空所有消息
     */
    clearMessages() {
        this.setState({ 
            messages: [], 
            reportSections: [],
            currentStreamingId: null,
            currentStreamingContent: ''
        });
    }
    
    // ===== 私有消息处理方法 =====
    
    /**
     * 消息分发
     * @param {Object} data - 接收到的消息
     */
    #dispatch(data) {
        console.log(data,"001....");
        
        const { type, content: eventData } = data;
        
        const handlers = {
            'sync': () => this.#handleSync(eventData),
            'chunk': () => this.#handleChunk(eventData),
            'complete': () => this.#handleComplete(eventData),
            'message': () => this.#handleTextMessage(eventData),
            'error': () => this.#handleError(eventData)
        };
        
        const handler = handlers[type];
        if (handler) {
            handler();
        } else {
            console.log('未处理的消息类型:', type, eventData);
        }
    }
    
    #handleSync(eventData) {
        if (eventData.type === 'history' && eventData.messages) {
            // 历史消息
            this.setState({ messages: eventData.messages });
        } else if (eventData.type === 'state') {
            // 状态同步
            const updates = {
                currentPhase: eventData.phase || 'idle',
                pendingType: eventData.pending_type
            };
            
            if (eventData.sections) {
                updates.reportSections = eventData.sections;
            }
            
            this.setState(updates);
        }
    }
    
    #handleChunk(text) {
        this.setState(prev => {
            const newContent = prev.currentStreamingContent + text;
            
            // 如果没有正在流式的消息，创建一个
            if (!prev.currentStreamingId) {
                const msgId = 'stream_' + Date.now();
                return {
                    currentStreamingId: msgId,
                    currentStreamingContent: newContent,
                    messages: [...prev.messages, {
                        id: msgId,
                        role: 'assistant',
                        content: newContent,
                        streaming: true,
                        timestamp: new Date().toISOString()
                    }]
                };
            }
            
            // 更新现有的流式消息
            return {
                currentStreamingContent: newContent,
                messages: prev.messages.map(msg => 
                    msg.id === prev.currentStreamingId 
                        ? { ...msg, content: newContent, streaming: true }
                        : msg
                )
            };
        });
    }
    
    #handleComplete(eventData) {
        // 流式完成，移除光标
        this.setState(prev => ({
            currentStreamingId: null,
            currentStreamingContent: '',
            messages: prev.messages.map(msg => 
                msg.id === prev.currentStreamingId 
                    ? { ...msg, streaming: false, content: eventData.full_content || msg.content }
                    : msg
            )
        }));
    }
    
    #handleTextMessage(eventData) {
        // 普通文本消息（如询问）
        this.setState(prev => ({
            messages: [...prev.messages, {
                id: 'msg_' + Date.now(),
                role: 'assistant',
                content: eventData.content || JSON.stringify(eventData),
                streaming: false,
                timestamp: new Date().toISOString()
            }]
        }));
    }
    
    #handleError(eventData) {
        this.setState(prev => ({
            messages: [...prev.messages, {
                id: 'error_' + Date.now(),
                role: 'system',
                content: `❌ ${eventData.code}: ${eventData.message}`,
                streaming: false,
                isError: true,
                timestamp: new Date().toISOString()
            }]
        }));
    }
}

// ===== 创建单例实例并导出 =====
const AppStoreInstance = new AppStore();