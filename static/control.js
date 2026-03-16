// Client-side JavaScript for AI RC Car Dashboard

// API base URL
const API_BASE = '';

// State
let connectionStatus = 'connecting';
let retryCount = 0;

// DOM elements
const videoFeed = document.getElementById('video-feed');
const videoLoader = document.getElementById('video-loader');
const statusIndicator = document.getElementById('status-indicator');
const statusText = document.getElementById('status-text');
const voiceInput = document.getElementById('voice-input');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    testConnection();
    initVideoFeed();
});

// Initialize event listeners
function initEventListeners() {
    // Motor buttons - regular click for forward/back/stop
    document.querySelectorAll('.motor-btn').forEach(btn => {
        const action = btn.dataset.action;
        
        // Special handling for steering (left/right)
        if (action === 'left' || action === 'right') {
            // Mouse events
            btn.addEventListener('mousedown', (e) => {
                e.preventDefault();
                sendSteeringAction(`steer_${action}_hold`);
            });
            btn.addEventListener('mouseup', (e) => {
                e.preventDefault();
                sendSteeringAction('steer_center');
            });
            btn.addEventListener('mouseleave', (e) => {
                sendSteeringAction('steer_center');
            });
            
            // Touch events
            btn.addEventListener('touchstart', (e) => {
                e.preventDefault();
                sendSteeringAction(`steer_${action}_hold`);
            });
            btn.addEventListener('touchend', (e) => {
                e.preventDefault();
                sendSteeringAction('steer_center');
            });
        } else {
            // Regular click for other actions
            btn.addEventListener('click', () => {
                sendMotorAction(action);
            });
        }
    });

    // Mode buttons
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const mode = btn.dataset.mode;
            setMode(mode);
        });
    });

    // Pan slider
    document.getElementById('pan-slider').addEventListener('input', (e) => {
        const angle = parseInt(e.target.value);
        sendPanAction(angle);
    });

    // Tilt slider
    document.getElementById('tilt-slider').addEventListener('input', (e) => {
        const angle = parseInt(e.target.value);
        sendTiltAction(angle);
    });

    // Center camera button
    document.getElementById('center-camera').addEventListener('click', () => {
        centerCamera();
    });

    // Speak button
    document.getElementById('speak-btn').addEventListener('click', () => {
        const text = voiceInput.value.trim();
        if (text) {
            speak(text);
            voiceInput.value = '';
        }
    });

    // Emergency stop
    document.getElementById('emergency-stop').addEventListener('click', () => {
        emergencyStop();
    });

    // Keyboard controls
    document.addEventListener('keydown', handleKeyPress);
    document.addEventListener('keyup', handleKeyPress);
}

// Motor control
async function sendMotorAction(action) {
    try {
        const response = await fetch(`${API_BASE}/motor/${action}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            // Check if it's an obstacle detection
            if (data.reason === 'obstacle_detected') {
                showToast(data.message || 'Object ahead', 'warning');
            } else {
                showToast(data.message || `Motor ${action} failed`, 'error');
            }
            return;
        }
        
        console.log('Motor action:', data);
        showToast(`Motor: ${action}`, 'info');
    } catch (error) {
        console.error('Motor action error:', error);
        showToast('Motor control failed', 'error');
    }
}

// Steering control
async function sendSteeringAction(action) {
    try {
        const response = await fetch(`${API_BASE}/steering/${action}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            console.error('Steering action error:', data);
            return;
        }
        
        console.log('Steering action:', action);
    } catch (error) {
        console.error('Steering action error:', error);
    }
}

// Mode control
async function setMode(mode) {
    try {
        const response = await fetch(`${API_BASE}/mode/${mode}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Mode set:', data);
        
        // Update UI
        document.querySelectorAll('.mode-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.mode === mode) {
                btn.classList.add('active');
            }
        });
    } catch (error) {
        console.error('Set mode error:', error);
        showToast('Failed to set mode', 'error');
    }
}

// Pan control
async function sendPanAction(angle) {
    try {
        const response = await fetch(`${API_BASE}/servo/pan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ angle })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Pan set:', data);
    } catch (error) {
        console.error('Pan error:', error);
    }
}

// Tilt control
async function sendTiltAction(angle) {
    try {
        const response = await fetch(`${API_BASE}/servo/tilt`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ angle })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Tilt set:', data);
    } catch (error) {
        console.error('Tilt error:', error);
    }
}

// Center camera
async function centerCamera() {
    try {
        const response = await fetch(`${API_BASE}/servo/center`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Camera centered:', data);
        
        // Update sliders
        document.getElementById('pan-slider').value = 90;
        document.getElementById('tilt-slider').value = 90;
    } catch (error) {
        console.error('Center camera error:', error);
    }
}

// Speak
async function speak(text) {
    try {
        const response = await fetch(`${API_BASE}/speak`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Speak:', data);
    } catch (error) {
        console.error('Speak error:', error);
        showToast('Failed to speak', 'error');
    }
}

// Emergency stop
async function emergencyStop() {
    await sendMotorAction('stop');
    showToast('EMERGENCY STOP', 'warning');
}

// Test connection
async function testConnection() {
    try {
        const response = await fetch(`${API_BASE}/status`);
        if (response.ok) {
            updateConnectionStatus('online');
        } else {
            updateConnectionStatus('offline');
        }
    } catch (error) {
        updateConnectionStatus('offline');
    }
}

function updateConnectionStatus(status) {
    connectionStatus = status;
    statusIndicator.className = 'indicator ' + status;
    
    if (status === 'online') {
        statusText.textContent = 'Online';
    } else {
        statusText.textContent = 'Offline';
    }
}

// Video feed
function initVideoFeed() {
    videoFeed.addEventListener('load', () => {
        videoLoader.style.display = 'none';
    });
    
    videoFeed.addEventListener('error', () => {
        videoLoader.style.display = 'flex';
        videoLoader.querySelector('p').textContent = 'Camera unavailable';
    });
}

// Keyboard control state
const keyState = {
    forward: false,
    backward: false,
    left: false,
    right: false
};

// Keyboard controls
function handleKeyPress(e) {
    // Don't trigger if typing in input
    if (e.target.tagName === 'INPUT') return;
    
    // Handle key down
    if (e.type === 'keydown') {
        switch(e.key) {
            case 'w':
            case 'W':
            case 'ArrowUp':
                e.preventDefault();
                if (!keyState.forward) {
                    keyState.forward = true;
                    sendMotorAction('front');
                }
                break;
            case 's':
            case 'S':
            case 'ArrowDown':
                e.preventDefault();
                if (!keyState.backward) {
                    keyState.backward = true;
                    sendMotorAction('back');
                }
                break;
            case 'a':
            case 'A':
            case 'ArrowLeft':
                e.preventDefault();
                if (!keyState.left) {
                    keyState.left = true;
                    sendSteeringAction('steer_left_hold');
                }
                break;
            case 'd':
            case 'D':
            case 'ArrowRight':
                e.preventDefault();
                if (!keyState.right) {
                    keyState.right = true;
                    sendSteeringAction('steer_right_hold');
                }
                break;
            case ' ':
                e.preventDefault();
                emergencyStop();
                break;
        }
    } else if (e.type === 'keyup') {
        switch(e.key) {
            case 'w':
            case 'W':
            case 'ArrowUp':
                e.preventDefault();
                if (keyState.forward) {
                    keyState.forward = false;
                    sendMotorAction('stop');
                }
                break;
            case 's':
            case 'S':
            case 'ArrowDown':
                e.preventDefault();
                if (keyState.backward) {
                    keyState.backward = false;
                    sendMotorAction('stop');
                }
                break;
            case 'a':
            case 'A':
            case 'ArrowLeft':
                e.preventDefault();
                if (keyState.left) {
                    keyState.left = false;
                    sendSteeringAction('steer_center');
                }
                break;
            case 'd':
            case 'D':
            case 'ArrowRight':
                e.preventDefault();
                if (keyState.right) {
                    keyState.right = false;
                    sendSteeringAction('steer_center');
                }
                break;
        }
    }
}

// Toast notifications
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        padding: 15px 20px;
        background: ${type === 'error' ? '#ff6b35' : type === 'warning' ? '#ffa500' : '#00e5ff'};
        color: ${type === 'error' || type === 'warning' ? '#fff' : '#000'};
        border-radius: 8px;
        z-index: 1000;
        animation: slideIn 0.3s ease;
        font-weight: bold;
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// CSS animations for toast
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(style);