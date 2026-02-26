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

    
}
