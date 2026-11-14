// Wall-E Companion - Cockpit JavaScript

class WallECockpit {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 1000;
        this.hardwareConfig = null;
        this.servoSliders = {};
        this.traitSliders = {};
        this.currentMood = null;
        this.cameraCtx = null;
        this.cameraCanvas = null;

        this.init();
    }

    async init() {
        this.setupElements();
        this.setupEventListeners();
        await this.loadHardwareConfig();
        this.createServoControls();
        this.createTraitControls();
        this.connectWebSocket();
        this.startStatusPolling();
    }

    setupElements() {
        this.statusDot = document.getElementById('statusDot');
        this.statusText = document.getElementById('statusText');
        this.modeEl = document.getElementById('mode');
        this.moodEl = document.getElementById('mood');
        this.batteryBar = document.getElementById('batteryBar');
        this.batteryText = document.getElementById('batteryText');
        this.voltageEl = document.getElementById('voltage');
        this.tempEl = document.getElementById('temp');
        this.uptimeEl = document.getElementById('uptime');
        this.servoGrid = document.getElementById('servoGrid');
        this.traitGrid = document.getElementById('traitGrid');
        this.moodButtons = document.querySelectorAll('.mood-btn');
        this.conversationLog = document.getElementById('conversationLog');
        this.cameraCanvas = document.getElementById('cameraCanvas');
        this.cameraCtx = this.cameraCanvas.getContext('2d');
    }

    setupEventListeners() {
        // Mood buttons
        this.moodButtons.forEach(btn => {
            btn.addEventListener('click', () => this.setMood(btn.dataset.mood));
        });

        // Emergency stop
        document.getElementById('emergencyStop').addEventListener('click', () => this.emergencyStop());

        // Reset
        document.getElementById('resetBtn').addEventListener('click', () => this.resetRobot());

        // Speak
        document.getElementById('speakBtn').addEventListener('click', () => this.speakText());
        document.getElementById('speakText').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.speakText();
        });

        // AI actions
        document.getElementById('greetBtn').addEventListener('click', () => this.triggerGreeting());
        document.getElementById('celebrateBtn').addEventListener('click', () => this.triggerCelebrate());
        document.getElementById('surpriseBtn').addEventListener('click', () => this.triggerSurprise());

        // Window unload
        window.addEventListener('beforeunload', () => this.disconnect());
    }

    async loadHardwareConfig() {
        try {
            const response = await fetch('/api/hardware-config');
            this.hardwareConfig = await response.json();
        } catch (error) {
            console.error('Failed to load hardware config:', error);
        }
    }

    createServoControls() {
        if (!this.hardwareConfig?.servos) return;

        this.servoGrid.innerHTML = '';

        for (const [id, config] of Object.entries(this.hardwareConfig.servos)) {
            const div = document.createElement('div');
            div.className = 'servo-control';
            div.innerHTML = `
                <label>
                    <span class="servo-name">${id.replace('_', ' ')}</span>
                    <span class="servo-value" id="${id}-value">${config.default_angle}°</span>
                </label>
                <input type="range" class="servo-slider" id="${id}-slider"
                    min="${config.angle_range[0]}" max="${config.angle_range[1]}"
                    step="1" value="${config.default_angle}">
            `;
            this.servoGrid.appendChild(div);

            const slider = document.getElementById(`${id}-slider`);
            const valueEl = document.getElementById(`${id}-value`);
            this.servoSliders[id] = { slider, valueEl, config };

            slider.addEventListener('input', (e) => {
                valueEl.textContent = `${e.target.value}°`;
            });

            slider.addEventListener('change', (e) => {
                this.moveServo(id, parseFloat(e.target.value));
            });
        }
    }

    createTraitControls() {
        const traits = [
            'curiosity', 'empathy', 'playfulness',
            'cautiousness', 'persistence', 'expressiveness'
        ];

        this.traitGrid.innerHTML = '';

        for (const trait of traits) {
            const div = document.createElement('div');
            div.className = 'trait-control';
            div.innerHTML = `
                <label>
                    <span class="trait-name">${trait}</span>
                    <span class="trait-value" id="${trait}-value">0.5</span>
                </label>
                <input type="range" class="trait-slider" id="${trait}-slider"
                    min="0" max="1" step="0.05" value="0.5">
            `;
            this.traitGrid.appendChild(div);

            const slider = document.getElementById(`${trait}-slider`);
            const valueEl = document.getElementById(`${trait}-value`);
            this.traitSliders[trait] = { slider, valueEl };

            slider.addEventListener('input', (e) => {
                valueEl.textContent = parseFloat(e.target.value).toFixed(2);
            });

            slider.addEventListener('change', (e) => {
                this.setPersonalityTrait(trait, parseFloat(e.target.value));
            });
        }
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.setConnectionStatus(true);
            this.reconnectAttempts = 0;
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                this.handleWebSocketMessage(msg);
            } catch (error) {
                console.error('WS message parse error:', error);
            }
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.setConnectionStatus(false);
            this.attemptReconnect();
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    attemptReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('Max reconnect attempts reached');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1);
        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

        setTimeout(() => this.connectWebSocket(), delay);
    }

    handleWebSocketMessage(msg) {
        switch (msg.type) {
            case 'status_update':
                this.updateStatus(JSON.parse(msg.data));
                break;
            case 'pong':
                // Heartbeat response
                break;
            case 'servo_response':
                this.updateServoDisplay(msg.servo_id, msg.ok);
                break;
        }
    }

    updateStatus(data) {
        // State machine status
        if (data.state_machine) {
            const sm = data.state_machine;
            this.modeEl.textContent = sm.mode || '-';
            this.moodEl.textContent = sm.mood || '-';

            // Update mood button active state
            this.moodButtons.forEach(btn => {
                btn.classList.toggle('active', btn.dataset.mood === sm.mood);
            });

            // Battery
            const battery = sm.battery_percent || 0;
            this.batteryBar.style.setProperty('--battery-width', `${battery}%`);
            this.batteryBar.className = 'battery-bar';
            if (battery <= 20) this.batteryBar.classList.add('critical');
            else if (battery <= 40) this.batteryBar.classList.add('low');
            this.batteryText.textContent = `${battery}%`;

            // Hardware
            if (data.hardware) {
                const hw = data.hardware;
                this.voltageEl.textContent = `${hw.battery_voltage?.toFixed(2) || '--'} V`;
                this.tempEl.textContent = `${hw.temperature_c?.toFixed(1) || '--'} °C`;

                // Uptime
                const uptimeMs = hw.uptime_ms || 0;
                const seconds = Math.floor(uptimeMs / 1000);
                const mins = Math.floor(seconds / 60);
                const hrs = Math.floor(mins / 60);
                this.uptimeEl.textContent = `${hrs}h ${mins % 60}m ${seconds % 60}s`;

                // Servo positions
                if (hw.servos) {
                    for (const [id, servo] of Object.entries(hw.servos)) {
                        if (this.servoSliders[id]) {
                            const angle = servo.current_angle?.toFixed(1) || 0;
                            this.servoSliders[id].valueEl.textContent = `${angle}°`;
                            this.servoSliders[id].slider.value = angle;
                        }
                    }
                }
            }
        }

        // Personality traits
        if (data.personality?.personality) {
            for (const [trait, value] of Object.entries(data.personality.personality)) {
                if (this.traitSliders[trait]) {
                    this.traitSliders[trait].slider.value = value;
                    this.traitSliders[trait].valueEl.textContent = value.toFixed(2);
                }
            }
        }
    }

    setConnectionStatus(connected) {
        this.statusDot.className = 'status-dot ' + (connected ? 'connected' : 'disconnected');
        this.statusText.textContent = connected ? 'Conectado' : 'Desconectado';
    }

    async startStatusPolling() {
        // Fallback polling if WebSocket fails
        setInterval(async () => {
            if (this.ws?.readyState !== WebSocket.OPEN) {
                await this.fetchStatus();
            }
        }, 5000);
    }

    async fetchStatus() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            this.updateStatus(data);
        } catch (error) {
            console.error('Status fetch error:', error);
        }
    }

    // Servo control
    async moveServo(servoId, angle, speed = null) {
        try {
            const response = await fetch('/api/servo/move', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ servo_id: servoId, angle, speed })
            });
            const result = await response.json();
            if (!result.ok) {
                console.error(`Servo ${servoId} move failed:`, result.msg);
            }
        } catch (error) {
            console.error('Move servo error:', error);
        }
    }

    async moveServos(positions) {
        try {
            const response = await fetch('/api/servo/move-multiple', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ positions })
            });
            return await response.json();
        } catch (error) {
            console.error('Move servos error:', error);
        }
    }

    // Mood control
    async setMood(mood) {
        try {
            const response = await fetch('/api/mood/set', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mood })
            });
            const result = await response.json();
            if (result.ok) {
                this.currentMood = mood;
                this.moodButtons.forEach(btn => {
                    btn.classList.toggle('active', btn.dataset.mood === mood);
                });
                this.addLogEntry('system', `Mood changed to: ${mood}`);
            }
        } catch (error) {
            console.error('Set mood error:', error);
        }
    }

    // Robot actions
    async emergencyStop() {
        if (!confirm('¿Ejecutar EMERGENCY STOP? Esto detiene todos los servos inmediatamente.')) return;

        try {
            const response = await fetch('/api/robot/emergency-stop', { method: 'POST' });
            const result = await response.json();
            this.addLogEntry('error', 'EMERGENCY STOP activado');
        } catch (error) {
            console.error('Emergency stop error:', error);
        }
    }

    async resetRobot() {
        try {
            const response = await fetch('/api/robot/reset', { method: 'POST' });
            const result = await response.json();
            if (result.ok) {
                // Reset sliders to defaults
                for (const [id, { slider, config }] of Object.entries(this.servoSliders)) {
                    slider.value = config.default_angle;
                    document.getElementById(`${id}-value`).textContent = `${config.default_angle}°`;
                }
                this.addLogEntry('system', 'Robot reset to home position');
            }
        } catch (error) {
            console.error('Reset error:', error);
        }
    }

    // Speech
    async speakText() {
        const input = document.getElementById('speakText');
        const text = input.value.trim();
        if (!text) return;

        try {
            const response = await fetch('/api/robot/speak', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            const result = await response.json();
            if (result.ok) {
                this.addLogEntry('robot', text);
                input.value = '';
            }
        } catch (error) {
            console.error('Speak error:', error);
        }
    }

    // Personality
    async setPersonalityTrait(trait, value) {
        try {
            const response = await fetch('/api/personality/trait', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ trait, value })
            });
            const result = await response.json();
        } catch (error) {
            console.error('Set trait error:', error);
        }
    }

    // AI Actions
    async triggerGreeting() {
        await this.callAI('/api/ai/greet');
        this.addLogEntry('system', 'Triggered: Greeting');
    }

    async triggerCelebrate() {
        await this.callAI('/api/ai/celebrate');
        this.addLogEntry('system', 'Triggered: Celebration');
    }

    async triggerSurprise() {
        await this.callAI('/api/ai/surprise');
        this.addLogEntry('system', 'Triggered: Surprise');
    }

    async callAI(endpoint) {
        try {
            const response = await fetch(endpoint, { method: 'POST' });
            return await response.json();
        } catch (error) {
            console.error(`AI action ${endpoint} error:`, error);
        }
    }

    // Logging
    addLogEntry(type, message) {
        const entry = document.createElement('div');
        entry.className = `log-entry ${type}`;
        const time = new Date().toLocaleTimeString();
        entry.textContent = `[${time}] ${message}`;
        this.conversationLog.appendChild(entry);
        this.conversationLog.scrollTop = this.conversationLog.scrollHeight;

        // Limit log entries
        while (this.conversationLog.children.length > 100) {
            this.conversationLog.removeChild(this.conversationLog.firstChild);
        }
    }

    // Camera rendering (placeholder for future MJPEG/WebRTC stream)
    renderCameraFrame(frameData) {
        // This would be called with actual frame data
        // For now, draw a placeholder
        const ctx = this.cameraCtx;
        const canvas = this.cameraCanvas;

        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.fillStyle = '#30363d';
        ctx.font = '14px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('Cámara no disponible', canvas.width / 2, canvas.height / 2);
        ctx.fillText('Conecta una cámara USB', canvas.width / 2, canvas.height / 2 + 20);
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.cockpit = new WallECockpit();
});