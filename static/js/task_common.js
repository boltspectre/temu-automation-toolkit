/**
 * 通用任务配置组件
 * 包含：登录类型、Ikun浏览器持续显示、隐藏浏览器模式、强制重新登录、守护任务
 * 以及店铺选择面板的HTML结构
 */

/**
 * 获取通用的任务配置HTML组件（完整版）
 * 包含：登录类型、Ikun浏览器持续显示、隐藏浏览器模式、强制重新登录、守护任务
 */
function getCommonTaskConfigHtml() {
    return `
        <div class="form-group">
            <label><i class="fas fa-user-secret"></i> 登录类型</label>
            <select class="ui fluid dropdown" id="loginTypeSelect">
                <option value="ikun">ikun浏览器</option>
                <option value="bit">比特浏览器</option>
            </select>
            <small>选择登录使用的浏览器类型，默认使用ikun浏览器</small>
        </div>
        <div class="form-group ikun-persist-browser-group" id="ikunPersistBrowserGroup" style="display: none;">
            <label><i class="fas fa-eye"></i> 是否持续显示ikun浏览器</label>
            <div class="ui toggle checkbox" id="ikunPersistBrowserCheckbox">
                <input type="checkbox" id="ikunPersistBrowser">
                <label>勾选后任务执行期间ikun浏览器将持续显示</label>
            </div>
        </div>
        <div class="form-group">
            <label><i class="fas fa-eye"></i> 显示浏览器登录过程</label>
            <div class="ui toggle checkbox" id="headlessCheckbox">
                <input type="checkbox" id="headless">
                <label>显示浏览器</label>
            </div>
        </div>
        <div class="form-group">
            <label><i class="fas fa-redo"></i> 强制重新登录</label>
            <div class="ui toggle checkbox" id="reloadCookiesCheckbox">
                <input type="checkbox" id="reloadCookies">
                <label>提交任务时强制重新登录以刷新Cookies</label>
            </div>
        </div>
        ${getSimpleCommonConfigHtml()}
    `;
}

/**
 * 获取简化的通用任务配置HTML组件（用于虎扑等不需要登录的任务）
 * 只包含：守护任务、定时任务
 */
function getSimpleCommonConfigHtml() {
    return `
        <div class="form-group">
            <label><i class="fas fa-shield-alt"></i> 守护任务</label>
            <div class="ui toggle checkbox" id="isMaintainTaskCheckbox">
                <input type="checkbox" id="isMaintainTask">
                <label>是否为守护任务</label>
            </div>
        </div>
        <div class="form-group" style="border-top: 1px solid #e0e0e0; padding-top: 15px; margin-top: 15px;">
            <label><i class="fas fa-clock"></i> 定时任务</label>
            <div class="ui toggle checkbox" id="enableScheduleCheckbox">
                <input type="checkbox" id="enableSchedule">
                <label>启用定时任务</label>
            </div>
            <small>勾选后可配置任务定时执行</small>
        </div>
        <div class="form-group" id="scheduleConfigGroup" style="display: none;">
            <label><i class="fas fa-cog"></i> 定时类型</label>
            <select class="ui fluid dropdown" id="scheduleType">
                <option value="once">定时执行（每天固定时间）</option>
                <option value="interval">间隔执行（每隔N分钟）</option>
            </select>
        </div>
        <div class="form-group" id="scheduleTimeGroup" style="display: none;">
            <label><i class="fas fa-hourglass-start"></i> 执行时间</label>
            <input type="time" class="form-control" id="scheduleTime" value="">
            <small>设置任务在每天的指定时间执行一次</small>
        </div>
        <div class="form-group" id="scheduleIntervalGroup" style="display: none;">
            <label><i class="fas fa-stopwatch"></i> 执行间隔（分钟）</label>
            <input type="number" class="form-control" id="scheduleInterval" min="1" value="30">
            <small>设置任务每隔多少分钟执行一次</small>
        </div>
        <div class="form-group" id="scheduleImmediateGroup" style="display: none;">
            <label><i class="fas fa-play-circle"></i> 立即执行</label>
            <div class="ui toggle checkbox" id="executeImmediatelyCheckbox">
                <input type="checkbox" id="executeImmediately" checked>
                <label>提交后立即执行一次任务</label>
            </div>
            <small>取消勾选则等待定时条件满足后才执行</small>
        </div>
    `;
}

/**
 * 获取任务右侧店铺选择面板HTML
 */
function getTaskShopPanelHtml() {
    return `
        <div class="task-shop-panel">
            <div id="shopSelectionArea">
                <p>正在加载店铺列表...</p>
            </div>
        </div>
    `;
}

/**
 * 初始化通用任务配置的事件监听器
 * 包括：Semantic UI组件初始化、联动逻辑
 */
function initCommonTaskConfigListeners() {
    if (typeof $ !== 'undefined' && $.fn) {
        if ($('#loginTypeSelect').length) $('#loginTypeSelect').dropdown();
        if ($('#headlessCheckbox').length) $('#headlessCheckbox').checkbox();
        if ($('#reloadCookiesCheckbox').length) $('#reloadCookiesCheckbox').checkbox();
        if ($('#ikunPersistBrowserCheckbox').length) $('#ikunPersistBrowserCheckbox').checkbox();
        if ($('#isMaintainTaskCheckbox').length) $('#isMaintainTaskCheckbox').checkbox();
        if ($('#enableScheduleCheckbox').length) $('#enableScheduleCheckbox').checkbox();
        if ($('#executeImmediatelyCheckbox').length) $('#executeImmediatelyCheckbox').checkbox();
        if ($('#scheduleType').length) $('#scheduleType').dropdown();
    }

    const loginTypeSelect = document.getElementById('loginTypeSelect');
    if (loginTypeSelect) {

        // 登录类型切换事件
        const handleLoginTypeChange = function () {
            const ikunPersistBrowserGroup = document.getElementById('ikunPersistBrowserGroup');
            const ikunPersistBrowserCheckbox = document.getElementById('ikunPersistBrowser');
            const reloadCookiesCheckbox = document.getElementById('reloadCookies');

            if (this.value === 'ikun') {
                if (ikunPersistBrowserGroup) ikunPersistBrowserGroup.style.display = 'block';
            } else {
                if (ikunPersistBrowserGroup) ikunPersistBrowserGroup.style.display = 'none';

                // 隐藏时取消勾选持续显示
                if (ikunPersistBrowserCheckbox) {
                    ikunPersistBrowserCheckbox.checked = false;
                    // 手动触发change事件以重置相关联动
                    const event = new Event('change');
                    ikunPersistBrowserCheckbox.dispatchEvent(event);
                }

                // 恢复reload_cookies的选择权
                if (reloadCookiesCheckbox) {
                    reloadCookiesCheckbox.disabled = false;
                }
                // 恢复显示浏览器模式可选
                const headlessEl = document.getElementById('headless');
                if (headlessEl) {
                    headlessEl.disabled = false;
                }
            }
        };

        loginTypeSelect.addEventListener('change', handleLoginTypeChange);

        // 初始化时检查当前状态
        if (loginTypeSelect.value === 'ikun') {
            const ikunPersistBrowserGroup = document.getElementById('ikunPersistBrowserGroup');
            if (ikunPersistBrowserGroup) ikunPersistBrowserGroup.style.display = 'block';
        }
    }

    // Ikun持续显示勾选框联动事件
    const ikunPersistBrowserCheckbox = document.getElementById('ikunPersistBrowser');
    if (ikunPersistBrowserCheckbox) {
        ikunPersistBrowserCheckbox.addEventListener('change', function () {
            const reloadCookiesCheckbox = document.getElementById('reloadCookies');
            const headlessEl = document.getElementById('headless');

            if (reloadCookiesCheckbox) {
                if (this.checked) {
                    // 勾选时强制reload_cookies为true
                    reloadCookiesCheckbox.checked = true;
                    reloadCookiesCheckbox.disabled = true;
                    // 更新Semantic UI样式
                    if (typeof $ !== 'undefined' && $.fn && $('#reloadCookiesCheckbox').length) {
                        // Semantic UI checkbox behavior handles visual update if input is checked
                    }
                } else {
                    // 取消勾选时恢复选择权
                    // 检查loginType是否为bit，如果是则不恢复？不，逻辑是ikun下才显示此chkbox
                    reloadCookiesCheckbox.disabled = false;
                }
            }

            if (headlessEl) {
                if (this.checked) {
                    headlessEl.checked = true;
                    headlessEl.disabled = true;
                    if (typeof $ !== 'undefined' && $.fn && $('#headlessCheckbox').length) {
                        $('#headlessCheckbox').checkbox('set checked');
                    }
                } else {
                    headlessEl.disabled = false;
                }
            }
        });
    }

    // 定时任务相关事件监听器
    const enableScheduleCheckbox = document.getElementById('enableSchedule');
    if (enableScheduleCheckbox) {
        enableScheduleCheckbox.addEventListener('change', function () {
            const scheduleConfigGroup = document.getElementById('scheduleConfigGroup');
            const scheduleTimeGroup = document.getElementById('scheduleTimeGroup');
            const scheduleIntervalGroup = document.getElementById('scheduleIntervalGroup');
            const scheduleImmediateGroup = document.getElementById('scheduleImmediateGroup');
            const scheduleType = document.getElementById('scheduleType');
            const scheduleTimeInput = document.getElementById('scheduleTime');

            if (this.checked) {
                // 显示定时配置
                if (scheduleConfigGroup) scheduleConfigGroup.style.display = 'block';
                if (scheduleImmediateGroup) scheduleImmediateGroup.style.display = 'block';
                
                // 根据定时类型显示对应的配置项
                if (scheduleType && scheduleType.value === 'once') {
                    if (scheduleTimeGroup) scheduleTimeGroup.style.display = 'block';
                    if (scheduleIntervalGroup) scheduleIntervalGroup.style.display = 'none';
                    
                    // 设置默认时间为当前时间
                    if (scheduleTimeInput && !scheduleTimeInput.value) {
                        const now = new Date();
                        const hours = String(now.getHours()).padStart(2, '0');
                        const minutes = String(now.getMinutes()).padStart(2, '0');
                        scheduleTimeInput.value = `${hours}:${minutes}`;
                    }
                } else if (scheduleType && scheduleType.value === 'interval') {
                    if (scheduleTimeGroup) scheduleTimeGroup.style.display = 'none';
                    if (scheduleIntervalGroup) scheduleIntervalGroup.style.display = 'block';
                }
            } else {
                // 隐藏所有定时配置
                if (scheduleConfigGroup) scheduleConfigGroup.style.display = 'none';
                if (scheduleTimeGroup) scheduleTimeGroup.style.display = 'none';
                if (scheduleIntervalGroup) scheduleIntervalGroup.style.display = 'none';
                if (scheduleImmediateGroup) scheduleImmediateGroup.style.display = 'none';
            }
        });
    }

    // 定时类型切换事件
    const scheduleType = document.getElementById('scheduleType');
    if (scheduleType) {
        scheduleType.addEventListener('change', function () {
            const scheduleTimeGroup = document.getElementById('scheduleTimeGroup');
            const scheduleIntervalGroup = document.getElementById('scheduleIntervalGroup');
            const scheduleTimeInput = document.getElementById('scheduleTime');

            if (this.value === 'once') {
                if (scheduleTimeGroup) scheduleTimeGroup.style.display = 'block';
                if (scheduleIntervalGroup) scheduleIntervalGroup.style.display = 'none';
                
                // 设置默认时间为当前时间
                if (scheduleTimeInput && !scheduleTimeInput.value) {
                    const now = new Date();
                    const hours = String(now.getHours()).padStart(2, '0');
                    const minutes = String(now.getMinutes()).padStart(2, '0');
                    scheduleTimeInput.value = `${hours}:${minutes}`;
                }
            } else if (this.value === 'interval') {
                if (scheduleTimeGroup) scheduleTimeGroup.style.display = 'none';
                if (scheduleIntervalGroup) scheduleIntervalGroup.style.display = 'block';
            }
        });
    }
}

// ================= 店铺选择逻辑封装 =================

/** 提交任务-店铺选择：同手机号互斥用。uid -> 同手机号的其他 uid 列表 */
let shopSelectionSamePhoneMap = {};
/** 同手机号分组，每项为 uid[]，用于全选时每组只选一个 */
let shopSelectionDuplicateGroups = [];
let _onShopSelectionDuplicatePhoneChangeHandler = null;

/**
 * 从 duplicate_phone_list 和店铺数据构建 uid -> 同手机号其他 uid 列表，并填充 shopSelectionDuplicateGroups。
 */
function buildSamePhoneMap(shopData, duplicatePhoneList) {
    const map = {};
    shopSelectionDuplicateGroups = [];

    if (!Array.isArray(shopData) || !Array.isArray(duplicatePhoneList)) {
        return map;
    }

    const phoneToUids = {};
    for (const shop of shopData) {
        const phone = (shop.phone || '').trim();
        const uid = String(shop.uid || '');
        if (phone && uid) {
            if (!phoneToUids[phone]) {
                phoneToUids[phone] = [];
            }
            phoneToUids[phone].push(uid);
        }
    }

    for (const phone of duplicatePhoneList) {
        const uids = phoneToUids[phone] || [];
        if (uids.length >= 2) {
            shopSelectionDuplicateGroups.push(uids);
            for (const uid of uids) {
                map[uid] = uids.filter(u => u !== uid);
            }
        }
    }
    return map;
}

/**
 * 更新店铺选择区：根据已勾选状态，禁用同手机号的其他复选框
 */
function updateShopSelectionDuplicatePhoneState(container) {
    const area = container || document.getElementById('shopSelectionArea');
    if (!area) return;

    const checkboxes = area.querySelectorAll('input[type="checkbox"][data-uid]');
    const checkedUids = new Set();

    for (const cb of checkboxes) {
        if (cb.checked) {
            const uid = cb.dataset.uid || '';
            if (uid) checkedUids.add(uid);
        }
    }

    const toDisable = new Set();
    for (const uid of checkedUids) {
        const same = shopSelectionSamePhoneMap[uid];
        if (same) {
            same.forEach(u => toDisable.add(u));
        }
    }

    for (const cb of checkboxes) {
        const uid = cb.dataset.uid || '';
        const isDisabled = toDisable.has(uid);
        cb.disabled = isDisabled;

        const row = cb.closest('.shop-selection-row');
        if (row) {
            if (isDisabled) {
                row.classList.add('disabled-row');
            } else {
                row.classList.remove('disabled-row');
            }
        }
    }
}

function _onShopSelectionDuplicatePhoneChange() {
    updateShopSelectionDuplicatePhoneState(document.getElementById('shopSelectionArea'));
}

function attachShopSelectionDuplicatePhoneListeners(container) {
    const area = container || document.getElementById('shopSelectionArea');
    if (!area) return;

    const checkboxes = area.querySelectorAll('input[type="checkbox"][data-uid]');
    checkboxes.forEach(cb => {
        cb.removeEventListener('change', _onShopSelectionDuplicatePhoneChange);
        cb.addEventListener('change', _onShopSelectionDuplicatePhoneChange);
    });

    // 添加店铺行点击事件监听器
    const shopRows = area.querySelectorAll('.shop-selection-row');
    shopRows.forEach(row => {
        row.addEventListener('click', function(e) {
            // 避免点击按钮时触发
            if (e.target.tagName === 'BUTTON' || e.target.closest('button')) {
                return;
            }
            
            // 找到当前行的复选框
            const checkbox = row.querySelector('input[type="checkbox"][data-uid]');
            if (checkbox && !checkbox.disabled) {
                // 切换复选框状态
                checkbox.checked = !checkbox.checked;
                // 触发change事件
                const event = new Event('change');
                checkbox.dispatchEvent(event);
            }
        });
    });
}

/**
 * 加载店铺选择区域
 */
async function loadShopSelection() {
    const container = document.getElementById('shopSelectionArea');
    if (!container) return;

    try {
        const result = await requestGet('/api/page', {
            page: 1,
            page_size: 100,
            keyword: ""
        });

        if (result && result.success && result.data.length > 0) {
            const duplicatePhoneList = result.duplicate_phone_list || [];
            shopSelectionSamePhoneMap = buildSamePhoneMap(result.data, duplicatePhoneList);

            let html = `
                <div class="form-group">
                    <label><i class="fas fa-store"></i> 选择店铺</label>
                    <div style="margin-bottom: 10px;">
                        <button class="btn btn-outline" onclick="selectAllShops()">
                            <i class="fas fa-check-square"></i> 全选
                        </button>
                        <button class="btn btn-outline" onclick="deselectAllShops()">
                            <i class="fas fa-square"></i> 全不选
                        </button>
                    </div>
                    <div class="shop-selection-table">
                        <div class="shop-selection-header">
                            <div class="shop-col select">选择</div>
                            <div class="shop-col name">店铺名称</div>
                            <div class="shop-col abbr">店铺缩写</div>
                            <div class="shop-col phone">手机号</div>
                            <div class="shop-col id">Browser ID</div>
                            <div class="shop-col status">连接状态</div>
                            <div class="shop-col action">操作</div>
                        </div>
                        <div class="shop-selection-body">
            `;

            const phoneDuplicateMap = {};
            for (const phone of duplicatePhoneList) {
                phoneDuplicateMap[phone] = true;
            }

            const _escapeHtml = (typeof escapeHtml === 'function') ? escapeHtml : (str => str ? String(str).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m]) : '');

            for (const shop of result.data) {
                const uid = shop.uid || '';
                const phone = (shop.phone || '').trim();
                const isPhoneDuplicate = phone && phoneDuplicateMap[phone];

                let isConnected = false;
                if (typeof checkShopConnectionStatus === 'function') {
                    isConnected = await checkShopConnectionStatus(uid);
                }

                const statusText = isConnected ? '已连接' : '未连接';
                const statusClass = isConnected ? 'connected' : 'disconnected';
                const btnClass = isConnected ? 'btn-secondary' : 'btn-success';
                const shopNameEscaped = String(shop['店铺名称'] || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');

                const connectBtn = `<button class="btn ${btnClass} btn-sm" onclick="openConnectConfigModal('${uid}', '${shopNameEscaped}')">连接</button>`;

                const phoneDisplay = phone
                    ? (isPhoneDuplicate
                        ? `<span style="color: #ff6b6b; font-weight: 600;">${_escapeHtml(phone)} <i class="fas fa-exclamation-triangle" style="color: #ff6b6b; margin-left: 4px;" title="相同手机号只能同时提交一个任务"></i></span>`
                        : _escapeHtml(phone))
                    : '<span style="color: #999;">-</span>';

                html += `
                    <div class="shop-selection-row ${isPhoneDuplicate ? 'duplicate-phone-row' : ''}">
                        <div class="shop-col select">
                            <input type="checkbox" id="shop_${shop.browser_id}" value="${shop.browser_id}" data-uid="${String(uid).replace(/"/g, '&quot;')}" data-shop='${JSON.stringify(shop)}'>
                        </div>
                        <div class="shop-col name">${shop['店铺名称']}</div>
                        <div class="shop-col abbr">${shop['店铺缩写']}</div>
                        <div class="shop-col phone">${phoneDisplay}</div>
                        <div class="shop-col id">${shop['browser_id']}</div>
                        <div class="shop-col status">
                            <span class="status-badge ${statusClass}">${statusText}</span>
                        </div>
                        <div class="shop-col action">
                            ${connectBtn}
                        </div>
                    </div>
                `;
            }
            html += `
                        </div>
                    </div>
                </div>
            `;
            container.innerHTML = html;
            attachShopSelectionDuplicatePhoneListeners(container);
            updateShopSelectionDuplicatePhoneState(container);
        } else {
            container.innerHTML = `
                <div style="text-align: center; padding: 40px 20px;">
                    <i class="fas fa-store-slash" style="font-size: 48px; color: #999; margin-bottom: 20px;"></i>
                    <p style="color: #666; font-size: 16px; margin-bottom: 15px;">暂无店铺数据</p>
                    <button class="ui green button" onclick="openAddShopModalNew()">
                        <i class="plus icon"></i> 添加新店铺
                    </button>
                </div>
            `;
        }
    } catch (error) {
        container.innerHTML = `
            <div style="text-align: center; padding: 40px 20px;">
                <i class="fas fa-exclamation-circle" style="font-size: 48px; color: #e74c3c; margin-bottom: 20px;"></i>
                <p style="color: #666; font-size: 16px;">加载店铺列表失败: ${error.message}</p>
            </div>
        `;
    }
}

function selectAllShops() {
    const area = document.getElementById('shopSelectionArea');
    if (!area) return;

    const checkboxes = area.querySelectorAll('input[type="checkbox"][data-uid]');
    const inDuplicate = new Set();
    const pickOnePerGroup = new Set();

    if (shopSelectionDuplicateGroups && Array.isArray(shopSelectionDuplicateGroups)) {
        for (const g of shopSelectionDuplicateGroups) {
            g.forEach(u => inDuplicate.add(u));
            if (g.length) pickOnePerGroup.add(g[0]);
        }
    }

    for (const cb of checkboxes) {
        cb.checked = false;
    }

    for (const cb of checkboxes) {
        const uid = cb.dataset.uid || '';
        if (pickOnePerGroup.has(uid)) {
            cb.checked = true;
        } else if (!inDuplicate.has(uid)) {
            cb.checked = true;
        }
    }
    updateShopSelectionDuplicatePhoneState(area);
}

function deselectAllShops() {
    const area = document.getElementById('shopSelectionArea');
    if (!area) return;
    area.querySelectorAll('input[type="checkbox"][data-uid]').forEach(cb => {
        cb.checked = false;
    });
    updateShopSelectionDuplicatePhoneState(area);
}

// Ensure global availability
window.loadShopSelection = loadShopSelection;
window.selectAllShops = selectAllShops;
window.deselectAllShops = deselectAllShops;
window.getTaskShopPanelHtml = getTaskShopPanelHtml;
window.getCommonTaskConfigHtml = getCommonTaskConfigHtml;
window.getSimpleCommonConfigHtml = getSimpleCommonConfigHtml;
window.initCommonTaskConfigListeners = initCommonTaskConfigListeners;