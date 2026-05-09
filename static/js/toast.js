/**
 * 自定义 Toast 提示组件
 * 用于替换原生 alert() 提示
 */

// Toast 容器
let toastContainer = null;

/**
 * 初始化 Toast 容器
 */
function initToastContainer() {
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'toast-container';
        document.body.appendChild(toastContainer);
    }
}

/**
 * 显示 Toast 提示
 * @param {string} message - 提示消息
 * @param {string} type - 提示类型: 'success', 'error', 'warning', 'info' (默认: 'info')
 * @param {number} duration - 显示时长（毫秒），默认 3000，0 表示不自动关闭
 * @returns {Promise} 返回一个 Promise，在提示关闭时 resolve
 */
function showToast(message, type = 'info', duration = 3000) {
    return new Promise((resolve) => {
        initToastContainer();
        
        // 创建 Toast 元素
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        // 根据类型设置图标
        let icon = '';
        switch (type) {
            case 'success':
                icon = '<i class="check circle icon"></i>';
                break;
            case 'error':
                icon = '<i class="times circle icon"></i>';
                break;
            case 'warning':
                icon = '<i class="exclamation triangle icon"></i>';
                break;
            case 'info':
            default:
                icon = '<i class="info circle icon"></i>';
                break;
        }
        
        toast.innerHTML = `
            <div class="toast-content">
                <div class="toast-icon">${icon}</div>
                <div class="toast-message">${escapeHtml(message)}</div>
                <button class="toast-close" onclick="this.parentElement.parentElement.remove()">
                    <i class="times icon"></i>
                </button>
            </div>
        `;
        
        // 添加到容器
        toastContainer.appendChild(toast);
        
        // 触发动画
        setTimeout(() => {
            toast.classList.add('show');
        }, 10);
        
        // 自动关闭
        let timeoutId = null;
        if (duration > 0) {
            timeoutId = setTimeout(() => {
                closeToast(toast);
                resolve();
            }, duration);
        }
        
        // 点击关闭按钮
        const closeBtn = toast.querySelector('.toast-close');
        closeBtn.addEventListener('click', () => {
            if (timeoutId) clearTimeout(timeoutId);
            closeToast(toast);
            resolve();
        });
        
        // 点击 Toast 本身也可以关闭
        toast.addEventListener('click', (e) => {
            if (e.target === toast || e.target.closest('.toast-content')) {
                if (timeoutId) clearTimeout(timeoutId);
                closeToast(toast);
                resolve();
            }
        });
    });
}

/**
 * 关闭 Toast
 */
function closeToast(toast) {
    toast.classList.remove('show');
    toast.classList.add('hide');
    setTimeout(() => {
        if (toast.parentElement) {
            toast.remove();
        }
    }, 300);
}

/**
 * HTML 转义，防止 XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 成功提示
 */
function showSuccess(message, duration = 3000) {
    return showToast(message, 'success', duration);
}

/**
 * 错误提示
 */
function showError(message, duration = 4000) {
    return showToast(message, 'error', duration);
}

/**
 * 警告提示
 */
function showWarning(message, duration = 3500) {
    return showToast(message, 'warning', duration);
}

/**
 * 信息提示
 */
function showInfo(message, duration = 3000) {
    return showToast(message, 'info', duration);
}

/**
 * 确认对话框（替换 confirm）
 * @param {string} message - 确认消息
 * @returns {Promise<boolean>} 返回 true 表示确认，false 表示取消
 */
function showConfirm(message) {
    return new Promise((resolve) => {
        initToastContainer();
        
        const confirmDialog = document.createElement('div');
        confirmDialog.className = 'confirm-dialog-overlay';
        confirmDialog.innerHTML = `
            <div class="confirm-dialog">
                <div class="confirm-header">
                    <i class="question circle icon"></i>
                    <span>确认操作</span>
                </div>
                <div class="confirm-message">${escapeHtml(message)}</div>
                <div class="confirm-actions">
                    <button class="ui button confirm-btn-cancel" onclick="this.closest('.confirm-dialog-overlay').remove(); window.__confirmResolve(false);">
                        取消
                    </button>
                    <button class="ui primary button confirm-btn-ok" onclick="this.closest('.confirm-dialog-overlay').remove(); window.__confirmResolve(true);">
                        确认
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(confirmDialog);
        
        // 显示动画
        setTimeout(() => {
            confirmDialog.classList.add('show');
        }, 10);
        
        // 存储 resolve 函数
        window.__confirmResolve = (result) => {
            confirmDialog.classList.remove('show');
            setTimeout(() => {
                confirmDialog.remove();
                delete window.__confirmResolve;
            }, 300);
            resolve(result);
        };
        
        // 点击遮罩层关闭（取消）
        confirmDialog.addEventListener('click', (e) => {
            if (e.target === confirmDialog) {
                window.__confirmResolve(false);
            }
        });
    });
}

/**
 * 确认对话框（支持自定义按钮文本）
 * @param {string} title - 对话框标题
 * @param {string} message - 确认消息（支持HTML）
 * @param {string} confirmText - 确认按钮文本
 * @param {string} cancelText - 取消按钮文本
 * @returns {Promise<boolean>} 返回 true 表示确认，false 表示取消
 */
function showConfirmDialog(title, message, confirmText = '确认', cancelText = '取消') {
    return new Promise((resolve) => {
        initToastContainer();
        
        const confirmDialog = document.createElement('div');
        confirmDialog.className = 'confirm-dialog-overlay';
        confirmDialog.innerHTML = `
            <div class="confirm-dialog">
                <div class="confirm-header">
                    <i class="question circle icon"></i>
                    <span>${escapeHtml(title)}</span>
                </div>
                <div class="confirm-message">${message}</div>
                <div class="confirm-actions">
                    <button class="ui button confirm-btn-cancel" onclick="this.closest('.confirm-dialog-overlay').remove(); window.__confirmResolve(false);">
                        ${escapeHtml(cancelText)}
                    </button>
                    <button class="ui primary button confirm-btn-ok" onclick="this.closest('.confirm-dialog-overlay').remove(); window.__confirmResolve(true);">
                        ${escapeHtml(confirmText)}
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(confirmDialog);
        
        // 显示动画
        setTimeout(() => {
            confirmDialog.classList.add('show');
        }, 10);
        
        // 存储 resolve 函数
        window.__confirmResolve = (result) => {
            confirmDialog.classList.remove('show');
            setTimeout(() => {
                confirmDialog.remove();
                delete window.__confirmResolve;
            }, 300);
            resolve(result);
        };
        
        // 点击遮罩层关闭（取消）
        confirmDialog.addEventListener('click', (e) => {
            if (e.target === confirmDialog) {
                window.__confirmResolve(false);
            }
        });
    });
}

// 确保函数在全局作用域中可用（用于在 HTML 中直接调用）
if (typeof window !== 'undefined') {
    window.showToast = showToast;
    window.showSuccess = showSuccess;
    window.showError = showError;
    window.showWarning = showWarning;
    window.showInfo = showInfo;
    window.showConfirm = showConfirm;
    window.showConfirmDialog = showConfirmDialog;
}

// 页面加载时初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initToastContainer);
} else {
    initToastContainer();
}

