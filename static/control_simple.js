// Simple Motor Control for AI RC Car

// API base URL
const API_BASE = '';

// State
let connectionStatus = 'connecting';
let joystickActive = false;
let joystickInterval = null;
let currentSteeringDirection = 'center'; // Track current steering state
let currentMotorDirection = 'stop'; // Track current motor command to avoid re-sending

// DOM elements
const statusIndicator = document.getElementById('status-indicator');
const statusText = document.getElementById('status-text');
const joystickBase = document.getElementById('joystick-base');
const joystickHandle = document.getElementById('joystick-handle');

// Joystick state
let joystickCenter = { x: 0, y: 0 };
let joystickMaxRadius = 50;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    initJoystick();
    testConnection();
});

// Initialize event listeners
function initEventListeners() {
    // Motor buttons
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
            // Regular click for other actions (forward, back, stop)
            btn.addEventListener('click', () => {
                sendMotorAction(action);
            });
        }
    });

    // Emergency stop button
    document.getElementById('emergency-stop').addEventListener('click', () => {
        emergencyStop();
    });

    // Keyboard controls
    document.addEventListener('keydown', handleKeyPress);
    document.addEventListener('keyup', handleKeyPress);
}

// Initialize joystick
function initJoystick() {
    const rect = joystickBase.getBoundingClientRect();
    joystickCenter = {
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2
    };
    joystickMaxRadius = rect.width / 2 - 25; // Account for handle size

    // Touch events
    joystickBase.addEventListener('touchstart', handleJoystickStart, { passive: false });
    joystickBase.addEventListener('touchmove', handleJoystickMove, { passive: false });
    joystickBase.addEventListener('touchend', handleJoystickEnd, { passive: false });
    joystickBase.addEventListener('touchcancel', handleJoystickEnd, { passive: false });

    // Mouse events for desktop testing
    joystickBase.addEventListener('mousedown', handleJoystickStart);
    document.addEventListener('mousemove', handleJoystickMove);
    document.addEventListener('mouseup', handleJoystickEnd);
}

// Joystick event handlers
function handleJoystickStart(e) {
    e.preventDefault();
    joystickActive = true;
    
    const point = getEventPoint(e);
    updateJoystickPosition(point);
    
    // Start continuous motor control
    if (joystickInterval) clearInterval(joystickInterval);
    joystickInterval = setInterval(updateMotorFromJoystick, 100);
}

function handleJoystickMove(e) {
    if (!joystickActive) return;
    e.preventDefault();
    
    const point = getEventPoint(e);
    if (point) {
        updateJoystickPosition(point);
    }
}

function handleJoystickEnd(e) {
    if (!joystickActive) return;
    joystickActive = false;
    
    // Reset joystick position
    joystickHandle.style.transform = 'translate(-50%, -50%)';

    // Stop motor
    currentMotorDirection = 'stop';
    sendMotorAction('stop');

    // Center steering
    sendSteeringAction('steer_center');
    currentSteeringDirection = 'center';
    
    // Clear interval
    if (joystickInterval) {
        clearInterval(joystickInterval);
        joystickInterval = null;
    }
}

function getEventPoint(e) {
    // Get touch or mouse position
    try {
        if (e.touches && e.touches.length > 0) {
            return { x: e.touches[0].clientX, y: e.touches[0].clientY };
        } else if (e.changedTouches && e.changedTouches.length > 0) {
            return { x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY };
        } else if (e.clientX !== undefined && e.clientY !== undefined) {
            return { x: e.clientX, y: e.clientY };
        }
    } catch (err) {
        console.error('Error getting event point:', err);
    }
    return null;
}

function updateJoystickPosition(point) {
    const dx = point.x - joystickCenter.x;
    const dy = point.y - joystickCenter.y;
    const distance = Math.sqrt(dx * dx + dy * dy);
    
    // Limit to maximum radius
    const clampedDistance = Math.min(distance, joystickMaxRadius);
    const ratio = clampedDistance / joystickMaxRadius;
    
    const angle = Math.atan2(dy, dx);
    const x = Math.cos(angle) * clampedDistance;
    const y = Math.sin(angle) * clampedDistance;
    
    // Update handle position
    joystickHandle.style.transform = `translate(${x - 25}px, ${y - 25}px)`;
    
    // Store normalized values (-1 to 1)
    joystickHandle.dataset.x = (x / joystickMaxRadius).toFixed(2);
    joystickHandle.dataset.y = (y / joystickMaxRadius).toFixed(2);
}

function updateMotorFromJoystick() {
    if (!joystickActive) return;
    
    const x = parseFloat(joystickHandle.dataset.x || 0);
    const y = parseFloat(joystickHandle.dataset.y || 0);
    
    // Deadzone
    const deadzone = 0.2;
    if (Math.abs(x) < deadzone && Math.abs(y) < deadzone) {
        if (currentMotorDirection !== 'stop') {
            currentMotorDirection = 'stop';
            sendMotorAction('stop');
        }
        // Center steering when in deadzone
        if (currentSteeringDirection !== 'center') {
            sendSteeringAction('steer_center');
            currentSteeringDirection = 'center';
        }
        return;
    }
    
    // Determine direction based on joystick position
    // Y axis: negative = forward, positive = backward
    // X axis: negative = left, positive = right

    if (Math.abs(y) > Math.abs(x)) {
        // Vertical movement dominant - handle front/back
        if (y < -deadzone) {
            if (currentMotorDirection !== 'front') {
                currentMotorDirection = 'front';
                sendMotorAction('front');
            }
        } else if (y > deadzone) {
            if (currentMotorDirection !== 'back') {
                currentMotorDirection = 'back';
                sendMotorAction('back');
            }
        }
        // Center steering when moving forward/back
        if (currentSteeringDirection !== 'center') {
            sendSteeringAction('steer_center');
            currentSteeringDirection = 'center';
        }
    } else {
        // Horizontal movement dominant - handle steering
        if (x < -deadzone) {
            // Left steering - only send once when direction changes
            if (currentSteeringDirection !== 'left') {
                sendSteeringAction('steer_left_hold');
                currentSteeringDirection = 'left';
            }
            // Keep motor stopped during steering
            if (currentMotorDirection !== 'stop') {
                currentMotorDirection = 'stop';
                sendMotorAction('stop');
            }
        } else if (x > deadzone) {
            // Right steering - only send once when direction changes
            if (currentSteeringDirection !== 'right') {
                sendSteeringAction('steer_right_hold');
                currentSteeringDirection = 'right';
            }
            // Keep motor stopped during steering
            if (currentMotorDirection !== 'stop') {
                currentMotorDirection = 'stop';
                sendMotorAction('stop');
            }
        }
    }
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
        // Don't show toast for every action to reduce noise - just errors
        if (action === 'stop') {
            // Silence stop notifications
        }
    } catch (error) {
        console.error('Motor action error:', error);
        showToast('Motor control failed', 'error');
    }
}

// Steering control
async function sendSteeringAction(action) {
    try {
        console.log('Sending steering action:', action);
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
        
        console.log('Steering action success:', action);
    } catch (error) {
        console.error('Steering action error:', error);
    }
}

// Emergency stop
async function emergencyStop() {
    await sendMotorAction('stop');
    showToast('🛑 EMERGENCY STOP', 'warning');
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

// Keyboard controls
// Keyboard control state for joystick simple control
const keyState = {
    forward: false,
    backward: false,
    left: false,
    right: false
};

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
    }, 2000);
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
