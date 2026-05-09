// ===== 增强 switchSection 函数（HTML head 中已有基础定义，这里添加完整功能） =====
/**
 * 切换页面区域（完整版本，覆盖 HTML head 中的简化版本）
 * @param {string} sectionId - 区域ID
 */
(function () {
    // 保存可能已存在的简化版本
    const originalSwitchSection = window.switchSection;

    // 定义完整版本
    window.switchSection = function (sectionId) {
        // 如果DOM还未加载完成，等待一下
        if (!document.getElementById(sectionId)) {
            console.warn('section元素不存在，等待DOM加载:', sectionId);
            setTimeout(function () {
                window.switchSection(sectionId);
            }, 100);
            return;
        }

        // 执行基础切换逻辑（与 HTML head 中的版本一致）
        document.querySelectorAll('.section').forEach(section => section.classList.remove('active'));
        document.querySelectorAll('.menu-item').forEach(item => item.classList.remove('active'));
        document.getElementById(sectionId).classList.add('active');
        const menuItem = document.querySelector(`.menu-item[data-section="${sectionId}"]`);
        if (menuItem) {
            menuItem.classList.add('active');
        }

        // 更新全局变量
        if (typeof currentSection !== 'undefined') {
            currentSection = sectionId;
        }
        
        // 更新URL标记
        if (typeof updateURLHash === 'function') {
            updateURLHash(sectionId);
        } else {
            // 如果updateURLHash函数不存在，直接更新URL
            const url = new URL(window.location);
            url.hash = '#' + sectionId;
            window.history.replaceState({}, '', url);
        }

        // 如果是任务管理页面，立即加载任务列表
        if (sectionId === 'task-manager') {
            // 直接调用，不检查 active 类（因为此时已经添加了）
            setTimeout(() => {
                if (typeof loadTasks === 'function') {
                    const container = document.getElementById('tasksContainer');
                    if (container) {
                        console.log('切换到任务管理页面，开始加载任务列表');
                        loadTasks();
                    } else {
                        console.warn('tasksContainer 元素不存在，50ms 后重试');
                        // 如果容器不存在，稍后再试
                        setTimeout(() => {
                            const retryContainer = document.getElementById('tasksContainer');
                            if (retryContainer && typeof loadTasks === 'function') {
                                console.log('重试加载任务列表');
                                loadTasks();
                            } else {
                                console.error('tasksContainer 元素仍然不存在，无法加载任务列表');
                            }
                        }, 50);
                    }
                } else {
                    console.error('loadTasks 函数未定义');
                }
            }, 20);
        }

        // 延迟执行其他函数，确保它们已定义
        setTimeout(function () {
            if (sectionId === 'shop-manager' && typeof loadShopList === 'function') {
                loadShopList();
            }
            if (sectionId === 'task-manager') {
                if (typeof initializeTaskFilterDropdowns === 'function') {
                    initializeTaskFilterDropdowns();
                }
                // 初始化搜索全部任务复选框
                if (typeof $ !== 'undefined' && $.fn) {
                    $('#searchAllTasksCheckbox').checkbox();
                }
                console.log('切换到任务管理页面，开始加载店铺缩写选项');
                // 加载店铺缩写选项
                setTimeout(() => {
                    if (typeof loadShopAbbrOptions === 'function') {
                        loadShopAbbrOptions().then(() => {
                            console.log('店铺缩写选项加载完成');
                        }).catch(err => {
                            console.error('店铺缩写选项加载失败:', err);
                        });
                    }
                }, 100);
            }
            if (sectionId === 'server-control' && typeof loadServerStatus === 'function') {
                loadServerStatus();
            }
            if (sectionId === 'settings' && typeof loadSettings === 'function') {
                loadSettings();
            }
        }, 0);
    };
})();

// 兼容性：也作为普通函数定义（使用 function 声明，会被提升到作用域顶部）
function switchSection(sectionId) {
    window.switchSection(sectionId);
}

// ===== 全局变量 =====
let currentToken = "";
let currentSection = 'dashboard';
let currentPage = 1;
let totalPages = 1;
let selectedShops = [];
let logWebSocket = null;
let taskData = {};
let currentModalData = {};
let cachedShopList = []; // 缓存店铺列表数据
let appVersion = "..."; // 默认版本号，从响应头获取后更新
let appInfo = "当前为内测版本，仅测试核心功能，有问题及时反馈"; // 默认程序说明，从响应头获取后更新
let currentTaskPage = 1; // 任务列表当前页码
let totalTaskPages = 1; // 任务列表总页数
// 缓存后端返回的所有任务ID（用于“一键清空所有任务”）
window.__allTaskIdListCache = window.__allTaskIdListCache || [];
let connectConfigModalInitialized = false; // 连接配置弹窗是否已初始化
// 店铺选择逻辑已移至 task_common.js

/**
 * 统一处理接口返回结果
 * 根据 success 字段判断成功或失败，并显示相应的提示
 * @param {Object} result - 接口返回结果 {success: true/false, message: "...", error_msg: "..."}
 * @param {Object} options - 配置选项
 * @param {Function} options.onSuccess - 成功时的回调函数
 * @param {string} options.errorPrefix - 错误提示前缀，默认为"操作失败"
 */
function handleApiResult(result, options = {}) {
    const { onSuccess, errorPrefix = "操作失败" } = options;

    if (result.success) {
        // 成功时显示成功提示
        if (result.message) {
            showSuccess(result.message);
        }
        // 执行成功回调
        if (onSuccess && typeof onSuccess === 'function') {
            onSuccess(result);
        }
    } else {
        // 失败时优先使用 error_msg，如果没有则使用 message
        const errorMsg = result.error_msg || result.message || '未知错误';
        showError(`${errorPrefix}：${errorMsg}`);
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', async function () {
    // 初始化版本号显示
    updateVersionDisplay();
    
    // 从URL中获取token参数
    const urlParams = new URLSearchParams(window.location.search);
    const urlToken = urlParams.get('token');
    
    // 先获取Token（会从响应头获取版本号并更新显示）
    // 如果URL中有token参数，优先使用URL中的token
    currentToken = urlToken || await getTokenFromBackend() || "";
    
    loadTaskCount();
    // 预先加载所有店铺数据用于缓存（用于任务管理的下拉框）
    requestGet('/api/page', {
        page: 1,
        page_size: 100,
        keyword: ""
    }).then(result => {
        if (result && result.success && result.data.length > 0) {
            cachedShopList = result.data;
        }
    }).catch(err => {
        console.error('预加载店铺数据失败:', err);
    });
    loadShopList();
    loadServerStatus();
    updateLogStatus(false);

    // 加载并应用CDN模式（只在页面加载时应用一次）
    try {
        const effectResult = await requestGet('/api/get_effect_settings', {});
        if (effectResult.success && effectResult.data) {
            const cdnMode = effectResult.cdn_mode || '云端';
            console.log('页面加载时应用CDN模式:', cdnMode);
            applyCdnMode(cdnMode);
        }
    } catch (error) {
        console.error('加载CDN设置失败:', error);
    }

    // 初始化 Semantic UI 组件
    if (typeof $ !== 'undefined' && $.fn) {
        // 先初始化任务筛选下拉框，确保"全部"选项显示（排除这些，避免被通用初始化影响）
        initializeTaskFilterDropdowns();
        // 初始化其他 dropdown（排除任务筛选的下拉框）
        $('.ui.dropdown').not('#filterTaskStatus, #filterTaskType, #filterShopAbbr, #filterScheduledTask').dropdown();
        // 初始化服务器设置页面的下拉框
        $('.ui.selection.dropdown').dropdown();
        // 初始化搜索全部任务复选框
        $('#searchAllTasksCheckbox').checkbox();
        // 初始化模态框（但不在此时显示）
        $('.ui.modal').modal({
            closable: true,
            onHide: function () {
                // 清除模态框数据
                currentModalData = {};
            },
            onVisible: function () {
                // 确保模态框在显示时居中
                $(this).modal('refresh');
            }
        });

        // 为关闭图标绑定点击事件
        $('.ui.modal .close.icon').on('click', function () {
            $(this).closest('.ui.modal').modal('hide');
        });

        // 定时任务类型下拉框变化事件
        $('#scheduleType').on('change', function() {
            updateScheduleFields();
        });
        // 连接配置弹窗：确认按钮使用 onclick 属性绑定（与任务提交按钮一致）
    }
});


/**
 * 打开店铺连接配置弹窗（与提交任务配置选择逻辑一致）
 * @param {string} uid - 店铺UID
 * @param {string} shopName - 店铺名称（用于展示，可选）
 */
async function openConnectConfigModal(uid, shopName) {
    const uidEl = document.getElementById('connectConfigUid');
    const infoEl = document.getElementById('connectConfigShopInfo');
    if (uidEl) uidEl.value = uid || '';
    if (infoEl) infoEl.textContent = shopName ? `店铺：${shopName}` : '连接配置';

    // 重置所有状态为默认值
    const loginType = document.getElementById('connectConfigLoginType');
    const windowSize = document.getElementById('connectConfigWindowSize');
    const ikunPersist = document.getElementById('connectConfigIkunPersistBrowser');
    const reloadCookies = document.getElementById('connectConfigReloadCookies');
    const headless = document.getElementById('connectConfigHeadless');
    const ikunGrp = document.getElementById('connectConfigIkunPersistBrowserGroup');

    // 先设置默认值
    if (loginType) loginType.value = 'ikun';
    if (windowSize) windowSize.value = '[1920,1080]';
    if (ikunPersist) ikunPersist.checked = false;
    if (reloadCookies) { reloadCookies.checked = false; reloadCookies.disabled = false; }
    if (headless) { headless.checked = false; headless.disabled = false; }
    if (ikunGrp) ikunGrp.style.display = 'block';

    // 显示弹窗
    $('#connectConfigModal').modal('show');

    // 使用 setTimeout 确保 DOM 更新后再初始化（与任务处理部分一致）
    setTimeout(async () => {
        // 查询并填充已保存的配置（在组件初始化之前查询）
        let savedConfig = null;
        if (uid) {
            try {
                const result = await requestPost('/api/get_connect_shop_config', {}, {
                    uid: uid,
                    save: 0  // 0是查询
                });

                if (result && result.success && result.data) {
                    savedConfig = result.data;
                }
            } catch (error) {
                console.warn('查询连接配置失败:', error);
                // 查询失败不影响弹窗显示，使用默认值
            }
        }

        if (typeof $ !== 'undefined' && $.fn) {
            if (!$('#connectConfigLoginType').parent().hasClass('ui dropdown')) {
                $('#connectConfigLoginType').dropdown({
                    clearable: false,
                    showOnFocus: false,
                    placeholder: '请选择'
                });
            }

            if (!$('#connectConfigWindowSize').parent().hasClass('ui dropdown')) {
                $('#connectConfigWindowSize').dropdown({
                    clearable: false,
                    showOnFocus: false,
                    placeholder: '请选择窗口大小'
                });
            }

            if ($('#connectConfigHeadlessCheckbox').length) $('#connectConfigHeadlessCheckbox').checkbox();
            if ($('#connectConfigReloadCookiesCheckbox').length) $('#connectConfigReloadCookiesCheckbox').checkbox();
            if ($('#connectConfigIkunPersistBrowserCheckbox').length) $('#connectConfigIkunPersistBrowserCheckbox').checkbox();

            // 如果有保存的配置，使用保存的值，否则使用默认值
            if (savedConfig) {
                // 设置登录类型
                if (savedConfig.login_type) {
                    $('#connectConfigLoginType').dropdown('set selected', savedConfig.login_type);
                } else {
                    $('#connectConfigLoginType').dropdown('set selected', 'ikun');
                }

                // 设置窗口大小
                if (savedConfig.window_size && Array.isArray(savedConfig.window_size)) {
                    // 将数组转换为字符串格式，如 [1920,1080]
                    const windowSizeStr = `[${savedConfig.window_size[0]},${savedConfig.window_size[1]}]`;
                    $('#connectConfigWindowSize').dropdown('set selected', windowSizeStr);
                } else {
                    // 默认值
                    $('#connectConfigWindowSize').dropdown('set selected', '[1920,1080]');
                }

                // 设置是否持续显示Ikun浏览器（对应 auto_close）
                if (savedConfig.auto_close !== undefined) {
                    // auto_close: false 表示持续显示（勾选），true 表示不持续显示（不勾选）
                    if (savedConfig.auto_close === false) {
                        $('#connectConfigIkunPersistBrowserCheckbox').checkbox('set checked');
                    } else {
                        $('#connectConfigIkunPersistBrowserCheckbox').checkbox('set unchecked');
                    }
                } else {
                    $('#connectConfigIkunPersistBrowserCheckbox').checkbox('set unchecked');
                }

                // 设置强制重新登录
                if (savedConfig.reload_cookies !== undefined) {
                    if (savedConfig.reload_cookies) {
                        $('#connectConfigReloadCookiesCheckbox').checkbox('set checked');
                    } else {
                        $('#connectConfigReloadCookiesCheckbox').checkbox('set unchecked');
                    }
                } else {
                    $('#connectConfigReloadCookiesCheckbox').checkbox('set unchecked');
                }

                // 设置显示浏览器登录过程
                if (savedConfig.headless !== undefined) {
                    // headless: false 表示显示浏览器（勾选），true 表示隐藏浏览器（不勾选）
                    if (savedConfig.headless === false) {
                        $('#connectConfigHeadlessCheckbox').checkbox('set checked');
                    } else {
                        $('#connectConfigHeadlessCheckbox').checkbox('set unchecked');
                    }
                } else {
                    $('#connectConfigHeadlessCheckbox').checkbox('set unchecked');
                }
            } else {
                $('#connectConfigLoginType').dropdown('set selected', 'ikun');
                $('#connectConfigWindowSize').dropdown('set selected', '[1920,1080]');
                $('#connectConfigIkunPersistBrowserCheckbox').checkbox('set checked');
                $('#connectConfigReloadCookiesCheckbox').checkbox('set checked');
                $('#connectConfigHeadlessCheckbox').checkbox('set unchecked');
            }

            // 根据是否持续显示Ikun浏览器联动设置其他选项
            const ikunPersistBrowserCheckbox = document.getElementById('connectConfigIkunPersistBrowser');
            const reloadCookiesCheckbox = document.getElementById('connectConfigReloadCookies');
            const headlessEl = document.getElementById('connectConfigHeadless');
            
            if (ikunPersistBrowserCheckbox && ikunPersistBrowserCheckbox.checked) {
                // 勾选持续显示时，强制勾选显示浏览器和强制重新登录
                if (reloadCookiesCheckbox) {
                    reloadCookiesCheckbox.checked = true;
                    reloadCookiesCheckbox.disabled = true;
                    if (typeof $ !== 'undefined' && $.fn && $('#connectConfigReloadCookiesCheckbox').length) {
                        $('#connectConfigReloadCookiesCheckbox').checkbox('set checked');
                    }
                }
                if (headlessEl) {
                    headlessEl.checked = true;
                    headlessEl.disabled = true;
                    if (typeof $ !== 'undefined' && $.fn && $('#connectConfigHeadlessCheckbox').length) {
                        $('#connectConfigHeadlessCheckbox').checkbox('set checked');
                    }
                }
            } else {
                // 未勾选持续显示时，恢复选择权
                if (reloadCookiesCheckbox) {
                    reloadCookiesCheckbox.disabled = false;
                }
                if (headlessEl) {
                    headlessEl.disabled = false;
                }
            }
        }

        // 只在第一次打开时绑定事件监听器（与任务处理部分一致）
        if (!connectConfigModalInitialized) {
            // 初始化登录类型选择框的change事件
            const loginTypeSelect = document.getElementById('connectConfigLoginType');
            if (loginTypeSelect) {
                loginTypeSelect.addEventListener('change', function () {
                    const ikunPersistBrowserGroup = document.getElementById('connectConfigIkunPersistBrowserGroup');
                    const ikunPersistBrowserCheckbox = document.getElementById('connectConfigIkunPersistBrowser');
                    const reloadCookiesCheckbox = document.getElementById('connectConfigReloadCookies');

                    if (this.value === 'ikun') {
                        ikunPersistBrowserGroup.style.display = 'block';
                    } else {
                        ikunPersistBrowserGroup.style.display = 'none';
                        // 隐藏时取消勾选
                        if (ikunPersistBrowserCheckbox) {
                            ikunPersistBrowserCheckbox.checked = false;
                        }
                        // 恢复reload_cookies的选择权
                        if (reloadCookiesCheckbox) {
                            reloadCookiesCheckbox.disabled = false;
                        }
                        // 恢复显示浏览器模式可选
                        const headlessEl = document.getElementById('connectConfigHeadless');
                        if (headlessEl) {
                            headlessEl.disabled = false;
                        }
                    }
                });
            }

            // 初始化Ikun持续显示勾选框的change事件
            const ikunPersistBrowserCheckbox = document.getElementById('connectConfigIkunPersistBrowser');
            if (ikunPersistBrowserCheckbox) {
                ikunPersistBrowserCheckbox.addEventListener('change', function () {
                    const reloadCookiesCheckbox = document.getElementById('connectConfigReloadCookies');
                    const headlessEl = document.getElementById('connectConfigHeadless');
                    if (reloadCookiesCheckbox) {
                        if (this.checked) {
                            // 勾选时强制reload_cookies为true
                            reloadCookiesCheckbox.checked = true;
                            reloadCookiesCheckbox.disabled = true;
                        } else {
                            // 取消勾选时恢复选择权
                            reloadCookiesCheckbox.disabled = false;
                        }
                    }
                    if (headlessEl) {
                        if (this.checked) {
                            headlessEl.checked = true;
                            headlessEl.disabled = true;
                            if (typeof $ !== 'undefined' && $.fn && $('#connectConfigHeadlessCheckbox').length) {
                                $('#connectConfigHeadlessCheckbox').checkbox('set checked');
                            }
                        } else {
                            headlessEl.checked = false;
                            headlessEl.disabled = false;
                            if (typeof $ !== 'undefined' && $.fn && $('#connectConfigHeadlessCheckbox').length) {
                                $('#connectConfigHeadlessCheckbox').checkbox('set unchecked');
                            }
                        }
                    }
                });
            }

            connectConfigModalInitialized = true;
        }

        // 每次打开时检查当前选择并显示/隐藏分组
        const loginTypeSelect = document.getElementById('connectConfigLoginType');
        if (loginTypeSelect) {
            const currentValue = loginTypeSelect.value || (savedConfig ? savedConfig.login_type : 'ikun');
            if (currentValue === 'ikun') {
                const ikunPersistBrowserGroup = document.getElementById('connectConfigIkunPersistBrowserGroup');
                if (ikunPersistBrowserGroup) {
                    ikunPersistBrowserGroup.style.display = 'block';
                }
            } else {
                const ikunPersistBrowserGroup = document.getElementById('connectConfigIkunPersistBrowserGroup');
                if (ikunPersistBrowserGroup) {
                    ikunPersistBrowserGroup.style.display = 'none';
                }
            }
        }

        // 如果加载了保存的配置，需要同步更新相关状态（如禁用状态等）
        if (savedConfig) {
            const ikunPersistBrowserCheckbox = document.getElementById('connectConfigIkunPersistBrowser');
            const reloadCookiesCheckbox = document.getElementById('connectConfigReloadCookies');
            const headlessEl = document.getElementById('connectConfigHeadless');

            // 如果持续显示Ikun浏览器被勾选，需要禁用相关选项
            if (ikunPersistBrowserCheckbox && ikunPersistBrowserCheckbox.checked) {
                if (reloadCookiesCheckbox) {
                    reloadCookiesCheckbox.disabled = true;
                }
                if (headlessEl) {
                    headlessEl.disabled = true;
                }
            }
        }
    }, 100);
}

/**
 * 保存连接配置（不执行连接，只保存配置）
 */
async function saveConnectConfig() {
    const uid = document.getElementById('connectConfigUid')?.value?.trim();
    if (!uid) {
        showError('保存失败：缺少店铺 UID');
        return;
    }

    // 获取登录类型
    const loginTypeEl = document.getElementById('connectConfigLoginType');
    const loginType = loginTypeEl ? (loginTypeEl.value || 'ikun') : 'ikun';

    // 获取窗口大小
    const windowSizeEl = document.getElementById('connectConfigWindowSize');
    let windowSize = [1920, 1080]; // 默认值
    if (windowSizeEl && windowSizeEl.value) {
        try {
            // 解析字符串格式的数组，如 "[1920,1080]"
            windowSize = JSON.parse(windowSizeEl.value);
        } catch (e) {
            console.warn('解析窗口大小失败，使用默认值:', e);
            windowSize = [1920, 1080];
        }
    }

    // 获取其他参数
    const reloadCookies = !!document.getElementById('connectConfigReloadCookies')?.checked;
    // 显示浏览器登录过程：勾选 => 传 false（headless为false表示显示浏览器）
    const headless = !document.getElementById('connectConfigHeadless')?.checked;
    // 是否持续显示Ikun浏览器 就是 auto_close 字段
    // 需求：勾选"持续显示" => auto_close 为 false；未勾选 => true
    const autoClose = !document.getElementById('connectConfigIkunPersistBrowser')?.checked;

    const saveBtn = document.getElementById('connectConfigSaveBtn');
    const originalText = saveBtn ? saveBtn.innerHTML : '';
    if (saveBtn) {
        saveBtn.innerHTML = '<i class="spinner loading icon"></i> 保存中...';
        saveBtn.classList.add('loading');
        saveBtn.disabled = true;
    }

    try {
        const result = await requestPost('/api/get_connect_shop_config', {}, {
            uid: uid,
            login_type: loginType,
            window_size: windowSize,
            reload_cookies: reloadCookies,
            headless: headless,
            auto_close: autoClose,
            save: 1  // 1是保存
        });

        if (result && result.success) {
            showSuccess(result.message || '配置保存成功');
        } else {
            const errorMsg = result?.error_msg || result?.message || '未知错误';
            showError('保存失败：' + errorMsg);
        }
    } catch (error) {
        showError('保存失败：' + error.message);
    } finally {
        if (saveBtn) {
            saveBtn.innerHTML = originalText;
            saveBtn.classList.remove('loading');
            saveBtn.disabled = false;
        }
    }
}

/**
 * 确认连接（从连接配置弹窗提交）
 */
async function submitConnectConfig() {
    const uid = document.getElementById('connectConfigUid')?.value?.trim();
    if (!uid) {
        showError('连接失败：缺少店铺 UID');
        return;
    }

    // 获取登录类型（与任务提交部分一致）
    const loginTypeEl = document.getElementById('connectConfigLoginType');
    const loginType = loginTypeEl ? (loginTypeEl.value || 'ikun') : 'ikun';

    // 获取窗口大小
    const windowSizeEl = document.getElementById('connectConfigWindowSize');
    let windowSize = [1920, 1080]; // 默认值
    if (windowSizeEl && windowSizeEl.value) {
        try {
            // 解析字符串格式的数组，如 "[1920,1080]"
            windowSize = JSON.parse(windowSizeEl.value);
        } catch (e) {
            console.warn('解析窗口大小失败，使用默认值:', e);
            windowSize = [1920, 1080];
        }
    }

    // 获取其他参数
    const reloadCookies = !!document.getElementById('connectConfigReloadCookies')?.checked;
    // 显示浏览器登录过程：勾选 => 传 false（headless为false表示显示浏览器）
    const headless = !document.getElementById('connectConfigHeadless')?.checked;
    // 是否持续显示Ikun浏览器 就是 auto_close 字段
    // 需求：勾选“持续显示” => auto_close 为 false；未勾选 => true
    const autoClose = !document.getElementById('connectConfigIkunPersistBrowser')?.checked;

    try {
        const result = await requestPost('/api/toggle_shop_connection', {}, {
            uid: uid,
            login_type: loginType,
            window_size: windowSize,
            reload_cookies: reloadCookies,
            headless: headless,
            auto_close: autoClose
        });
        if (result.success) {
            showSuccess(result.message);
            $('#connectConfigModal').modal('hide');
            if (currentSection === 'shop-manager') {
                loadShopList(currentPage);
            }
            if (document.getElementById('taskModal')?.classList.contains('active')) {
                loadShopSelection();
            }
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError('连接失败：' + errorMsg);
        }
    } catch (error) {
        if (error.message !== '用户取消操作') {
            showError('连接失败：' + error.message);
        }
    }
}

/**
 * 切换店铺连接状态（断开时直接调用；连接时通过 openConnectConfigModal 弹窗配置后提交）
 * @param {string} uid - 店铺UID
 * @param {boolean} isConnect - true为连接（会先弹窗），false为断开
 */
async function toggleShopConnection(uid, isConnect) {
    if (isConnect) {
        openConnectConfigModal(uid, '');
        return;
    }
    const action = '断开';
    try {
        const result = await requestPost('/api/toggle_shop_connection', {}, { uid: uid });

        if (result.success) {
            showSuccess(result.message);
            if (currentSection === 'shop-manager') {
                loadShopList(currentPage);
            }
            if (document.getElementById('taskModal')?.classList.contains('active')) {
                loadShopSelection();
            }
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError(`${action}失败：${errorMsg}`);
        }
    } catch (error) {
        if (error.message !== '用户取消操作') {
            showError(`${action}失败：${error.message}`);
        }
    }
}



/**
 * 通用GET请求函数（携带Token）
 * @param {string} url - 请求地址
 * @param {object} params - URL查询参数（键值对）
 * @returns {Promise} 响应结果
 */
async function requestGet(url, params = {}) {
    try {
        // 添加Token参数
        params.token = currentToken;
        const queryString = new URLSearchParams(params).toString();
        const fullUrl = queryString ? `${url}?${queryString}` : url;

        const headers = { 'Accept': 'application/json' };
        if (params.uid != null && params.uid !== '') {
            headers['uid'] = String(params.uid);
        }

        const response = await fetch(fullUrl, {
            method: 'GET',
            headers: headers
        });

        // 从响应头获取版本号和程序说明
        const versionHeader = response.headers.get('x-app-version');
        const appInfoHeader = response.headers.get('x-app-appinfo');
        if (versionHeader) {
            appVersion = decodeHeaderValue(versionHeader);
        }
        if (appInfoHeader) {
            appInfo = decodeHeaderValue(appInfoHeader);
        }
        if (versionHeader || appInfoHeader) {
            updateVersionDisplay();
        }

        const result = await response.json();
        return result;
    } catch (error) {
        console.error("GET请求失败：", error);
        throw error;
    }
}

/**
 * 通用POST请求函数（携带Token）
 * @param {string} url - 请求地址
 * @param {object} queryParams - URL查询参数（可选）
 * @param {object} bodyParams - 请求体参数（JSON格式）
 * @returns {Promise} 响应结果
 */
async function requestPost(url, queryParams = {}, bodyParams = {}) {
    try {
        console.log('requestPost called with:', url, queryParams, bodyParams);
        // 添加Token参数到URL
        queryParams.token = currentToken;
        const queryString = new URLSearchParams(queryParams).toString();
        const fullUrl = queryString ? `${url}?${queryString}` : url;

        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        };
        if (bodyParams.uid != null && bodyParams.uid !== '') {
            headers['uid'] = String(bodyParams.uid);
        }

        console.log('Making POST request to:', fullUrl, 'with headers:', headers, 'and body:', bodyParams);
        const response = await fetch(fullUrl, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(bodyParams)
        });

        // 从响应头获取版本号和程序说明
        const versionHeader = response.headers.get('x-app-version');
        const appInfoHeader = response.headers.get('x-app-appinfo');
        if (versionHeader) {
            appVersion = decodeHeaderValue(versionHeader);
        }
        if (appInfoHeader) {
            appInfo = decodeHeaderValue(appInfoHeader);
        }
        if (versionHeader || appInfoHeader) {
            updateVersionDisplay();
        }

        const result = await response.json();
        return result;
    } catch (error) {
        // 网络请求失败，静默处理
        throw error;
    }
}

// URL解码函数，用于解码响应头中的URL编码内容
function decodeHeaderValue(value) {
    if (!value) return value;
    try {
        return decodeURIComponent(value);
    } catch (e) {
        // 如果解码失败，返回原值
        console.warn('解码响应头值失败:', e);
        return value;
    }
}

// 更新版本号和程序说明显示
function updateVersionDisplay() {
    // 更新侧边栏版本号
    const versionText = document.querySelector('.version-text');
    if (versionText) {
        versionText.textContent = appVersion;
    }

    // 更新控制面板程序说明
    const programHeader = document.querySelector('#dashboard .ui.message.info .header');
    const programContent = document.querySelector('#dashboard .ui.message.info .content p');
    if (programHeader) {
        programHeader.textContent = `版本 ${appVersion}`;
    }
    if (programContent) {
        // 支持多行文本，将换行符转换为HTML换行
        programContent.innerHTML = appInfo.replace(/\n/g, '<br>');
    }
}

// 从后端获取动态Token的函数
async function getTokenFromBackend() {
    try {
        const response = await fetch('/api/get_token');
        // 从响应头获取版本号和程序说明
        const versionHeader = response.headers.get('x-app-version');
        const appInfoHeader = response.headers.get('x-app-appinfo');
        if (versionHeader) {
            appVersion = decodeHeaderValue(versionHeader);
        }
        if (appInfoHeader) {
            appInfo = decodeHeaderValue(appInfoHeader);
        }
        if (versionHeader || appInfoHeader) {
            updateVersionDisplay();
        }

        const result = await response.json();
        if (result.success) {
            return result.token;
        } else {
            showError("获取Token失败：" + result.message);
            return null;
        }
    } catch (error) {
        showError("获取Token异常：" + error.message);
        return null;
    }
}


function getSectionName(sectionId) {
    const sections = {
        'dashboard': '控制面板',
        'task-manager': '任务管理',
        'shop-manager': '店铺管理',
        'log-viewer': '日志监控',
        'server-control': '服务控制',
        'settings': '系统设置'
    };
    return sections[sectionId] || '';
}

// 打开任务模态框






// 月份选择器状态
let _currentPickerYear = new Date().getFullYear();
let _selectedMonths = new Set();

// 渲染月份选择器
function renderMonthPicker(containerId = 'monthPickerContainer') {
    const container = document.getElementById(containerId);
    if (!container) return;

    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth() + 1; // 1-12

    let gridHtml = '';
    for (let m = 1; m <= 12; m++) {
        const monthStr = String(m).padStart(2, '0');
        const value = `${_currentPickerYear}.${monthStr}`;

        let isFuture = false;
        if (_currentPickerYear > currentYear) isFuture = true;
        else if (_currentPickerYear === currentYear && m > currentMonth) isFuture = true;

        const isSelected = _selectedMonths.has(value);
        const className = `month-picker-item ${isSelected ? 'active' : ''} ${isFuture ? 'disabled' : ''}`;

        // onclick handler
        const clickHandler = isFuture ? '' : `onclick="toggleMonthSelection('${value}')"`;

        gridHtml += `<div class="${className}" ${clickHandler}>${m}月</div>`;
    }

    const html = `
        <div class="month-picker-container">
            <div class="month-picker-header">
                <button type="button" onclick="changePickerYear(-1)"><i class="fas fa-chevron-left"></i></button>
                <div class="month-picker-year">${_currentPickerYear}年</div>
                <button type="button" onclick="changePickerYear(1)" ${_currentPickerYear >= currentYear ? 'disabled' : ''}><i class="fas fa-chevron-right"></i></button>
            </div>
            <div class="month-picker-grid">
                ${gridHtml}
            </div>
            <div class="month-picker-summary" id="monthPickerSummary">
                ${renderMonthSummary()}
            </div>
        </div>
    `;

    container.innerHTML = html;
}

function renderMonthSummary() {
    if (_selectedMonths.size === 0) return '未选择月份';
    const sorted = Array.from(_selectedMonths).sort().reverse(); // 最近的在前面
    return '已选: ' + sorted.map(m => `<span>${m}</span>`).join('');
}

function changePickerYear(delta) {
    const now = new Date();
    const currentYear = now.getFullYear();
    const nextYear = _currentPickerYear + delta;

    if (nextYear > currentYear) return; // 不能超过当前年份

    _currentPickerYear = nextYear;
    renderMonthPicker();
}

function toggleMonthSelection(value) {
    if (_selectedMonths.has(value)) {
        _selectedMonths.delete(value);
    } else {
        _selectedMonths.add(value);
    }
    renderMonthPicker();
}


// 打开任务模态框
function openTaskModal(taskType, isEdit = false, taskId = null) {
    const modal = document.getElementById('taskModal');
    const modalTitle = document.getElementById('modalTitle');
    const modalBody = document.getElementById('modalBody');
    currentModalData = { taskType, isEdit, taskId };

    // 获取通用组件HTML
    const commonConfigHtml = getCommonTaskConfigHtml();
    const simpleCommonConfigHtml = getSimpleCommonConfigHtml();
    const taskShopPanelHtml = getTaskShopPanelHtml();

    // 默认通过 task-modal-layout 布局
    let taskFormContent = '';

    if (taskType === 'upload_real_pic') {
        modalTitle.textContent = getTaskTitle(1);
        taskFormContent = `
            <div class="form-group">
                <label><i class="fas fa-info-circle"></i> 任务说明</label>
                <p>实拍图全部重跑任务（完整逻辑。不筛选，执行所有订单）</p>
            </div>
            <div class="form-group">
                <label><i class="fas fa-tags"></i> 实拍图识别类型（多选）</label>
                <select class="ui fluid search dropdown" multiple id="inputCheckTypeList">
                    <option value="22">22（纺织标签）</option>
                    <option value="135">135（小地毯）</option>
                </select>
                <small>不选择表示不筛选，处理所有类型</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-filter"></i> 快速筛选</label>
                <select class="ui fluid dropdown" id="inputRapidScreenStatusList">
                    <option value="">所有</option>
                    <option value="1">待上传</option>
                    <option value="4">图中标签有异常</option>
                </select>
            </div>
            <div class="form-group">
                <label><i class="fas fa-barcode"></i> 指定SPU ID</label>
                <input type="text" class="form-control" id="inputSpuIdList" placeholder="输入SPU ID，多个用逗号或空格分隔，例如: 2909264548,7219364236">
                <small>不输入表示不筛选，处理所有SPU</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-shield-alt"></i> 敏感词识别结果（多选）</label>
                <select class="ui fluid search dropdown" multiple id="blackWordTypeList">
                    <option value="1">1. 敏感词知识产权相关敏感词</option>
                    <option value="2">2. 内容相关安全敏感词</option>
                    <option value="3">3. 商品合规相关敏感词</option>
                    <option value="4">4. 未存在敏感词</option>
                </select>
                <small>不选择表示不筛选，处理所有类型</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-shopping-bag"></i> 商品状态筛选（多选）</label>
                <select class="ui fluid search dropdown" multiple id="goodsStatusList">
                    <option value="1">1. 在售中</option>
                    <option value="2">2. 未发布到站点</option>
                    <option value="3">3. 已下架</option>
                    <option value="4">4. 已终止</option>
                </select>
                <small>不选择表示不筛选，处理所有状态</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-moon"></i> 是否执行额外的休息</label>
                <div class="ui toggle checkbox" id="sleepOpenCheckbox">
                    <input type="checkbox" id="sleepOpen">
                    <label>开启额外休息</label>
                </div>
                <small>默认关闭，开启后会在任务执行过程中增加额外的休息时间</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-image"></i> 是否上传自定义固定上传图片</label>
                <div class="ui toggle checkbox" id="customFixedUploadImgCheckbox">
                    <input type="checkbox" id="customFixedUploadImg">
                    <label>上传自定义固定上传图片</label>
                </div>
                <small>默认关闭，开启后会执行合规信息实拍图上传（自定义固定上传图片）</small>
            </div>
        `;
    } else if (taskType === 'modify_price') {
        modalTitle.textContent = '自动核价任务';
        taskFormContent = `
            <div class="form-group">
                <label><i class="fas fa-info-circle"></i> 任务说明</label>
                <p>自动核价任务，批量处理价格调整</p>
            </div>
            <div class="form-group">
                <label><i class="fas fa-barcode"></i> 指定SPU ID</label>
                <input type="text" class="form-control" id="inputSpuIdList" placeholder="输入SPU ID，多个用逗号或空格分隔，例如: 2909264548,7219364236">
                <small>不输入表示不筛选，处理所有SPU</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-sort-numeric-up"></i> 最大核价次数</label>
                <input type="number" class="form-control" id="inputModifyTimes" min="1" placeholder="留空使用系统配置">
            </div>
            <div class="form-group">
                <label><i class="fas fa-coins"></i> 每次降价金额</label>
                <input type="number" class="form-control" id="inputMinuPrice" step="0.01" min="0" placeholder="留空使用系统配置">
            </div>
            <p class="text-muted" style="font-size: 12px; margin: -8px 0 12px 0;">留空则使用核价默认配置</p>
        `;
    } else if (taskType === 'jit_govern') {
        modalTitle.textContent = 'JIT维护库存任务';
        taskFormContent = `
            <div class="form-group">
                <label><i class="fas fa-info-circle"></i> 任务说明</label>
                <p>JIT维护库存任务，批量管理JIT库存</p>
            </div>
            <div class="form-group">
                <label><i class="fas fa-barcode"></i> 指定SPU列表</label>
                <input type="text" class="form-control" id="inputSkcSpuList" placeholder="输入SPU ID，多个用逗号或空格分隔，例如: 123456,789012">
                <small>不输入表示使用日期范围获取，优先使用SPU列表</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-calendar-alt"></i> 日期范围</label>
                <div class="modern-date-range-picker">
                    <div class="date-input-container">
                        <div class="date-input-wrapper">
                            <input type="text" class="form-control date-input" id="inputStartDateDisplay" readonly placeholder="开始日期">
                            <input type="hidden" id="inputStartDate">
                            <button type="button" class="calendar-btn" id="startDateCalendarBtn">
                                <i class="fas fa-calendar"></i>
                            </button>
                        </div>
                        <span class="date-separator">-</span>
                        <div class="date-input-wrapper">
                            <input type="text" class="form-control date-input" id="inputEndDateDisplay" readonly placeholder="结束日期">
                            <input type="hidden" id="inputEndDate">
                            <button type="button" class="calendar-btn" id="endDateCalendarBtn">
                                <i class="fas fa-calendar"></i>
                            </button>
                        </div>
                    </div>
                    <div class="calendar-container" id="startDateCalendar" style="display: none;">
                        <div class="calendar-header">
                            <button type="button" class="calendar-nav prev-month"><i class="fas fa-chevron-left"></i></button>
                            <div class="calendar-title">2024年1月</div>
                            <button type="button" class="calendar-nav next-month"><i class="fas fa-chevron-right"></i></button>
                        </div>
                        <div class="calendar-body">
                            <div class="calendar-weekdays">
                                <div class="weekday">日</div>
                                <div class="weekday">一</div>
                                <div class="weekday">二</div>
                                <div class="weekday">三</div>
                                <div class="weekday">四</div>
                                <div class="weekday">五</div>
                                <div class="weekday">六</div>
                            </div>
                            <div class="calendar-days"></div>
                        </div>
                    </div>
                    <div class="calendar-container" id="endDateCalendar" style="display: none;">
                        <div class="calendar-header">
                            <button type="button" class="calendar-nav prev-month"><i class="fas fa-chevron-left"></i></button>
                            <div class="calendar-title">2024年1月</div>
                            <button type="button" class="calendar-nav next-month"><i class="fas fa-chevron-right"></i></button>
                        </div>
                        <div class="calendar-body">
                            <div class="calendar-weekdays">
                                <div class="weekday">日</div>
                                <div class="weekday">一</div>
                                <div class="weekday">二</div>
                                <div class="weekday">三</div>
                                <div class="weekday">四</div>
                                <div class="weekday">五</div>
                                <div class="weekday">六</div>
                            </div>
                            <div class="calendar-days"></div>
                        </div>
                    </div>
                </div>
                <small>点击日历图标选择日期</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-calendar-day"></i> 仅一天</label>
                <div class="ui toggle checkbox" id="onlyOneDayCheckbox">
                    <input type="checkbox" id="onlyOneDay">
                    <label>仅一天</label>
                </div>
                <small>勾选后只选择一天，开始日期和结束日期相同</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-warehouse"></i> 目标库存数量</label>
                <input type="number" class="form-control" id="inputFinalNum" min="1" placeholder="留空使用系统默认值">
            </div>
        `;
    } else if (taskType === 'adjust_price') {
        modalTitle.textContent = '调价管理';
        taskFormContent = `
            <div class="form-group">
                <label><i class="fas fa-info-circle"></i> 任务说明</label>
                <p>按SKC或订单ID筛选执行调价，其他登录参数与核价一致</p>
            </div>
            <div class="form-group">
                <label><i class="fas fa-qrcode"></i> 指定SKC ID</label>
                <input type="text" class="form-control" id="inputSkcIdList" placeholder="输入SKC ID，多个用逗号或空格分隔，例如: 123,456">
                <small>留空表示不筛选SKC</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-list-ol"></i> 指定订单ID列表</label>
                <input type="text" class="form-control" id="inputOrderIdList" placeholder="输入订单ID，多个用逗号或空格分隔">
                <small>留空表示不筛选订单ID</small>
            </div>
        `;
    } else if (taskType === 'apply_activity') {
        modalTitle.textContent = '报活动任务';
        taskFormContent = `
            <div class="form-group">
                <label><i class="fas fa-info-circle"></i> 任务说明</label>
                <p>自动申报活动，支持限时秒杀、官方大促、清仓甩卖等多种活动类型</p>
            </div>
            <div class="form-group">
                <label><i class="fas fa-barcode"></i> 指定SPU ID列表</label>
                <input type="text" class="form-control" id="inputSpuIdList" placeholder="输入SPU ID，多个用逗号或空格分隔，例如: 2909264548,7219364236">
                <small>不输入表示不筛选，处理所有SPU</small>
            </div>
            
            <!-- 活动选择方式选项卡 -->
            <div class="form-group">
                <label><i class="fas fa-list-alt"></i> 活动选择方式</label>
                <div class="ui top attached tabular menu" id="activitySelectModeTabs" style="border: 1px solid #d4d4d5; border-bottom: 1px solid #d4d4d5; border-radius: 4px 4px 0 0;">
                    <a class="active item" data-tab="quick" style="border: 1px solid #d4d4d5; border-bottom: none; border-radius: 4px 4px 0 0; margin-right: 4px;">快速选择</a>
                    <a class="item" data-tab="detailed" style="border: 1px solid #d4d4d5; border-bottom: none; border-radius: 4px 4px 0 0;">详细筛选</a>
                </div>
                <div class="ui bottom attached active tab segment" data-tab="quick" id="quickSelectTab" style="border: 1px solid #d4d4d5; border-top: none; border-radius: 0 0 4px 4px;">
                    <div class="form-group">
                        <label>活动类型列表</label>
                        <div class="ui fluid multiple search selection dropdown" id="activityTypeDropdown">
                            <input type="hidden" id="inputActivityTypeList">
                            <i class="dropdown icon"></i>
                            <div class="default text">选择活动类型</div>
                            <div class="menu">
                                <div class="item" data-value="1">限时秒杀</div>
                                <div class="item" data-value="5">官方大促</div>
                                <div class="item" data-value="27">清仓甩卖</div>
                                <div class="item" data-value="10000001">所有小活动</div>
                            </div>
                        </div>
                        <small>支持多选</small>
                    </div>
                </div>
                <div class="ui bottom attached tab segment" data-tab="detailed" id="detailedSelectTab" style="border: 1px solid #d4d4d5; border-top: none; border-radius: 0 0 4px 4px;">
                    <div class="form-group">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <label style="margin-bottom: 0;">详细活动筛选</label>
                            <button class="ui mini primary button" onclick="fetchAndUpdateActivityList()">
                                <i class="sync icon"></i> 更新活动列表
                            </button>
                        </div>
                        <div class="ui fluid multiple search selection dropdown" id="detailedActivityDropdown">
                            <input type="hidden" id="inputDetailedActivityList">
                            <i class="dropdown icon"></i>
                            <div class="default text">选择具体活动</div>
                            <div class="menu" id="detailedActivityMenu"></div>
                        </div>
                        <small id="activityListStatus">从已保存的活动列表中选择（支持多选）</small>
                    </div>
                </div>
            </div>
            
            <div class="form-group">
                <label><i class="fas fa-ban"></i> 排除SKC列表</label>
                <div class="form-group" style="margin-top: 10px;">
                    <button class="ui button" id="notSkcListExpandBtn" style="width: 100%; text-align: left;">
                        <i class="caret down icon"></i>
                        <span>管理排除SKC列表</span>
                    </button>
                </div>
                <div id="notSkcListSection" style="display: none; margin-top: 10px; padding: 15px; border: 1px solid #ddd; border-radius: 4px; background-color: #f9f9f9;">
                    <div class="form-group" style="margin-bottom: 10px;">
                        <label>SKC ID列表（空格、英文逗号或中文逗号分隔）</label>
                        <textarea class="form-control" id="inputNotSkcList" rows="4" placeholder="输入要排除的SKC ID，例如: 12345, 67890 或 12345 67890"></textarea>
                    </div>
                    <div style="text-align: center; margin-top: 10px;">
                        <button class="ui primary button" onclick="loadNotSkcList()">加载</button>
                        <button class="ui primary button" onclick="saveNotSkcList()">保存</button>
                    </div>
                </div>
            </div>
            <div class="form-group">
                <div class="ui checkbox">
                    <input type="checkbox" id="openLogFalseCheckbox">
                    <label for="openLogFalseCheckbox">显示价格比对日志</label>
                </div>
            </div>
        `;
    } else if (taskType === 'purchase_delivery') {
        modalTitle.textContent = '批量加入发货台';
        taskFormContent = `
            <div class="form-group">
                <label><i class="fas fa-info-circle"></i> 任务说明</label>
                <p>自动翻页查询备货单，批量加入发货台，失败自动上传实拍图后重试（最多5轮）</p>
            </div>
            <div class="form-group">
                <label><i class="fas fa-redo"></i> 最大重试轮次</label>
                <input type="number" class="form-control" id="inputMaxCycles" min="1" max="20" value="5">
                <small>每轮会先加入发货台，失败SPU自动上传实拍图后进入下一轮，默认5轮</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-image"></i> 上传固定标签图</label>
                <div class="ui toggle checkbox" id="customFixedUploadImgCheckbox">
                    <input type="checkbox" id="customFixedUploadImg">
                    <label>上传固定标签图（勾选后上传实拍图时使用固定标签）</label>
                </div>
            </div>
            <div class="form-group">
                <label><i class="fas fa-ban"></i> 不自动上传实拍图</label>
                <div class="ui toggle checkbox" id="skipUploadPicCheckbox">
                    <input type="checkbox" id="skipUploadPic">
                    <label>勾选后失败SPU不上传实拍图，直接输出失败列表</label>
                </div>
            </div>
        `;
    } else if (taskType === 'expected_goods_place') {
        modalTitle.textContent = '批量修改期望到货地点';
        taskFormContent = `
            <div class="form-group">
                <label><i class="fas fa-info-circle"></i> 任务说明</label>
                <p>批量修改商品期望到货地点，支持SKC列表、类目筛选与最大页数限制</p>
            </div>
            <div class="form-group">
                <label><i class="fas fa-qrcode"></i> 指定SKC ID</label>
                <input type="text" class="form-control" id="inputExpectedSkcIdList" placeholder="输入SKC ID 空格或逗号分割">
                <small>不输入表示不按SKC筛选</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-tags"></i> 选择类目</label>
                <div class="ui fluid multiple search selection dropdown" id="expectedCatIdDropdown">
                    <input type="hidden" id="inputExpectedCatIdList">
                    <i class="dropdown icon"></i>
                    <div class="default text">选择类目</div>
                    <div class="menu"></div>
                </div>
            </div>
            <div class="form-group">
                <label><i class="fas fa-search"></i> 类目搜索</label>
                <div class="form-group" style="margin-top: 5px;">
                    <button class="ui button" id="expectedCategoryExpandBtn" style="width: 100%; text-align: left;">
                        <i class="caret down icon"></i>
                        <span>展开类目搜索</span>
                    </button>
                </div>
                <div id="expectedCategoryAddSection" style="display: none; margin-top: 10px;">
                    <div class="ui top attached tabular menu" id="expectedCategoryModeTabs" style="border: 1px solid #d4d4d5; border-bottom: 1px solid #d4d4d5; border-radius: 4px 4px 0 0;">
                        <a class="active item" data-tab="keyword-search" style="border: 1px solid #d4d4d5; border-bottom: none; border-radius: 4px 4px 0 0; margin-right: 4px;">关键词搜索</a>
                        <a class="item" data-tab="goods-sn-search" style="border: 1px solid #d4d4d5; border-bottom: none; border-radius: 4px 4px 0 0;">货号搜索</a>
                    </div>
                    <div class="ui bottom attached active tab segment" data-tab="keyword-search" id="keywordSearchTab" style="border: 1px solid #d4d4d5; border-top: none; border-radius: 0 0 4px 4px;">
                        <div class="form-group" style="margin-bottom: 8px;">
                            <input type="text" class="form-control" id="inputExpectedCategorySearch" placeholder="输入类目关键词进行搜索">
                        </div>
                        <div class="form-group" style="margin-bottom: 8px;">
                            <div class="ui fluid multiple search selection dropdown" id="expectedCategoryResultDropdown">
                                <input type="hidden" id="inputExpectedCategoryResult">
                                <i class="dropdown icon"></i>
                                <div class="default text">搜索结果将显示在这里</div>
                                <div class="menu"></div>
                            </div>
                            <small id="expectedCategorySearchStatus" style="color: #666; display: block; text-align: center; margin-top: 5px;">选择店铺，输入类目关键词，搜索结果</small>
                        </div>
                        <div style="text-align: center; margin-top: 10px;">
                            <button class="ui primary button" onclick="searchExpectedCategory()">搜索</button>
                            <button class="ui primary button" onclick="confirmAddExpectedCategory()">确认添加</button>
                        </div>
                    </div>
                    <div class="ui bottom attached tab segment" data-tab="goods-sn-search" id="goodsSnSearchTab" style="border: 1px solid #d4d4d5; border-top: none; border-radius: 0 0 4px 4px; display: none;">
                        <div class="form-group">
                            <label>输入货号</label>
                            <div style="display: flex; gap: 10px;">
                                <input type="text" class="form-control" id="inputGoodsSn" placeholder="输入货号，如: CLS" style="flex: 1;">
                                <button class="ui primary button" onclick="searchCategoryByGoodsSn()">搜索</button>
                            </div>
                            <small id="goodsSnSearchStatus">搜索店铺内已有的商品类目（只能搜索到店铺内已有的类目，如需搜索其他类目请切换到"关键词搜索"标签页）</small>
                        </div>
                        <div id="goodsSnCategoryResult" style="display: none; margin-top: 10px; padding: 10px; border: 1px solid #ddd; border-radius: 4px; background-color: #f9f9f9;">
                            <div>
                                <strong>匹配类目：</strong>
                                <span id="goodsSnCategoryName"></span>
                            </div>
                            <div style="margin-top: 10px; display: flex; gap: 10px;">
                                <button class="ui primary button" onclick="saveGoodsSnCategory()">保存</button>
                                <button class="ui button" onclick="clearGoodsSnCategory()">清空</button>
                            </div>
                            <input type="hidden" id="goodsSnCategoryId">
                        </div>
                    </div>
                </div>
            </div>
            <div class="form-group">
                <label><i class="fas fa-map-marker-alt"></i> 期望到货地点</label>
                <div class="ui form">
                    <div class="fields">
                        <div class="twelve wide field">
                            <div class="expected-area-option">
                                <input type="radio" name="expectedArea" value="1" id="expectedArea1" checked>
                                <label for="expectedArea1">1 广东</label>
                            </div>
                        </div>
                        <div class="twelve wide field">
                            <div class="expected-area-option">
                                <input type="radio" name="expectedArea" value="2" id="expectedArea2">
                                <label for="expectedArea2">2 义乌</label>
                            </div>
                        </div>
                        <div class="twelve wide field">
                            <div class="expected-area-option">
                                <input type="radio" name="expectedArea" value="3" id="expectedArea3" checked>
                                <label for="expectedArea3">3 按历史推荐</label>
                            </div>
                        </div>
                    </div>
                </div>
                <style>
                    .expected-area-option {
                        display: flex;
                        align-items: center;
                        padding: 10px 0;
                    }
                    .expected-area-option input[type="radio"] {
                        appearance: none;
                        -webkit-appearance: none;
                        width: 22px;
                        height: 22px;
                        border: 2px solid #2185d0;
                        border-radius: 50%;
                        margin-right: 10px;
                        cursor: pointer;
                        position: relative;
                        transition: all 0.2s ease;
                    }
                    .expected-area-option input[type="radio"]:hover {
                        border-color: #1678c2;
                        box-shadow: 0 0 5px rgba(33, 133, 208, 0.3);
                    }
                    .expected-area-option input[type="radio"]:checked {
                        background-color: #2185d0;
                        border-color: #2185d0;
                    }
                    .expected-area-option input[type="radio"]:checked::after {
                        content: '';
                        position: absolute;
                        top: 50%;
                        left: 50%;
                        transform: translate(-50%, -50%);
                        width: 10px;
                        height: 10px;
                        background-color: white;
                        border-radius: 50%;
                    }
                    .expected-area-option label {
                        cursor: pointer;
                        font-size: 15px;
                        color: #333;
                        margin: 0;
                        user-select: none;
                    }
                    .expected-area-option label:hover {
                        color: #2185d0;
                    }
                </style>
            </div>
        `;
    } else if (taskType === 'hupu_post_list') {
        modalTitle.textContent = '虎扑帖子列表采集';
        taskFormContent = `
            <div class="form-group">
                <label><i class="fas fa-info-circle"></i> 任务说明</label>
                <p>采集虎扑帖子列表数据</p>
            </div>
            <div class="form-group">
                <label><i class="fas fa-key"></i> 关键词 <span style="color: red;">*</span></label>
                <input type="text" class="form-control" id="hupuKeyword" placeholder="请输入搜索关键词">
                <small>必填项，用于搜索虎扑帖子</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-file-alt"></i> 页数 <span style="color: red;">*</span></label>
                <input type="number" class="form-control" id="hupuMaxPages" min="1" value="1" placeholder="请输入要爬取的页数">
                <small>必填项，默认为1页</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-clock"></i> 休息时间（秒）</label>
                <input type="number" class="form-control" id="hupuSleepTime" min="0" step="0.1" value="0.3" placeholder="请输入休息时间">
                <small>可选，默认为0.3秒</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-sort"></i> 排序方式</label>
                <select class="ui fluid dropdown" id="hupuSortby">
                    <option value="general">综合排序</option>
                    <option value="createtime">按发布时间最新排序</option>
                    <option value="createtimeasc">按发布时间最早排序</option>
                    <option value="replytime">按回复时间排序</option>
                    <option value="light">按亮回复数排序(近1月)</option>
                    <option value="reply">按回复数排序(近1月)</option>
                </select>
                <small>可选，默认为综合排序</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-hashtag"></i> 话题ID</label>
                <input type="text" class="form-control" id="hupuTopicId" placeholder="请输入话题ID">
                <small>可选，留空表示不限制话题</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-file"></i> 只爬取指定页</label>
                <div class="ui toggle checkbox" id="hupuOnlyOnePageCheckbox">
                    <input type="checkbox" id="hupuOnlyOnePage">
                    <label>只爬取指定页</label>
                </div>
                <small>可选，开启后只爬取指定的那一页</small>
            </div>
            <div class="form-group" id="hupuSpecificPageGroup" style="display: none;">
                <label><i class="fas fa-bookmark"></i> 指定页数 <span style="color: red;">*</span></label>
                <input type="number" class="form-control" id="hupuSpecificPage" min="1" value="1" placeholder="请输入要爬取的指定页数">
                <small>开启"只爬取指定页"后必填，指定要爬取的页码</small>
            </div>
        `;
    } else if (taskType === 'hupu_detail_list') {
        modalTitle.textContent = '虎扑帖子详情采集';
        taskFormContent = `
            <div class="form-group">
                <label><i class="fas fa-info-circle"></i> 任务说明</label>
                <p>采集虎扑帖子详情数据</p>
            </div>
            <div class="form-group">
                <label><i class="fas fa-id-card"></i> 帖子ID/帖子URL <span style="color: red;">*</span></label>
                <input type="text" class="form-control" id="hupuDetailName" placeholder="请输入帖子ID或帖子URL" oninput="autoGetPostTitle()">
                <small>必填项，支持格式：帖子ID 或 完整URL</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-heading"></i> 帖子标题</label>
                <input type="text" class="form-control" id="hupuDetailTitle" placeholder="自动获取帖子标题" readonly>
                <small>根据帖子ID自动获取，支持URL和ID格式</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-file-alt"></i> 页数 <span style="color: red;">*</span></label>
                <input type="number" class="form-control" id="hupuDetailMaxPages" min="1" value="1" placeholder="请输入要爬取的页数">
                <small>必填项，默认为1页</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-clock"></i> 休息时间（秒）</label>
                <input type="number" class="form-control" id="hupuDetailSleepTime" min="0" step="0.1" value="0.3" placeholder="请输入休息时间">
                <small>可选，默认为0.3秒</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-file"></i> 只爬取指定页</label>
                <div class="ui toggle checkbox" id="hupuDetailOnlyOnePageCheckbox">
                    <input type="checkbox" id="hupuDetailOnlyOnePage">
                    <label>只爬取指定页</label>
                </div>
                <small>可选，开启后只爬取指定的那一页</small>
            </div>
            <div class="form-group" id="hupuDetailSpecificPageGroup" style="display: none;">
                <label><i class="fas fa-bookmark"></i> 指定页数 <span style="color: red;">*</span></label>
                <input type="number" class="form-control" id="hupuDetailSpecificPage" min="1" value="1" placeholder="请输入要爬取的指定页数">
                <small>开启"只爬取指定页"后必填，指定要爬取的页码</small>
            </div>
        `;
    } else if (taskType === 'hupu_score_list') {
        modalTitle.textContent = '虎扑评分采集';
        taskFormContent = `
            <div class="form-group">
                <label><i class="fas fa-info-circle"></i> 任务说明</label>
                <p>采集虎扑评分数据</p>
            </div>
            <div class="form-group">
                <label><i class="fas fa-star"></i> 评分ID/评分URL <span style="color: red;">*</span></label>
                <input type="text" class="form-control" id="hupuScoreId" placeholder="请输入评分ID或评分URL" oninput="autoGetScoreTitle()">
                <small>必填项，支持格式：评分ID 或 完整URL</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-heading"></i> 评分标题</label>
                <input type="text" class="form-control" id="hupuScoreTitle" placeholder="自动获取评分标题" readonly>
                <small>根据评分ID自动获取，支持URL和ID格式</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-file-alt"></i> 页数 <span style="color: red;">*</span></label>
                <input type="number" class="form-control" id="hupuScoreMaxPages" min="1" value="1" placeholder="请输入要爬取的页数">
                <small>必填项，默认为1页</small>
            </div>
            <div class="form-group">
                <label><i class="fas fa-clock"></i> 休息时间（秒）</label>
                <input type="number" class="form-control" id="hupuScoreSleepTime" min="0" step="0.1" value="0.3" placeholder="请输入休息时间">
                <small>可选，默认为0.3秒</small>
            </div>
        `;
    } else if (taskType === 'financial_full' || taskType === 'financial_export' || taskType === 'financial_merge' || taskType === 'financial_record' || taskType === 'financial_calculate' || taskType === 'sku_summary') {
        modalTitle.textContent = getTaskTitle(taskType);
        let desc = '财务报表任务';
        if (taskType === 'financial_export' || taskType === 'financial_full') desc = '导出所选月份账单';
        else if (taskType === 'financial_merge') desc = '融合所选月份账单';
        else if (taskType === 'financial_record') desc = '记录所需列到总表';
        else if (taskType === 'financial_calculate') desc = '计算并生成财务报表';
        else if (taskType === 'sku_summary') desc = '融合多个月份的SKU表生成汇总表';

        taskFormContent = `
            <div class="form-group">
                <label><i class="fas fa-info-circle"></i> 任务说明</label>
                <p>${desc}</p>
            </div>
            <div class="form-group">
                <label><i class="fas fa-calendar-alt"></i> 选择月份</label>
                <div id="monthPickerContainer"></div>
                <small>最多选择12个月份，仅限当前及历史月份</small>
            </div>
        `;
    } else {
        modalTitle.textContent = getTaskTitle(taskType);
        taskFormContent = `
            <div class="form-group">
                <label><i class="fas fa-info-circle"></i> 任务说明</label>
                <p>任务配置</p>
            </div>
        `;
    }

    // 组装最终HTML
    // 虎扑任务使用居中布局（没有店铺选择，但有简化的通用配置）
    if (taskType === 'hupu_post_list' || taskType === 'hupu_detail_list' || taskType === 'hupu_score_list') {
        // 虎扑任务使用居中布局（没有店铺选择，但有简化的通用配置）
        modalBody.innerHTML = `
            <div class="task-modal-layout centered">
                <div class="task-form-panel">
                    ${taskFormContent}
                    ${simpleCommonConfigHtml}
                </div>
            </div>
        `;
    } else if (isEdit) {
        // 编辑模式使用居中布局（没有店铺选择，但有完整的通用配置）
        modalBody.innerHTML = `
            <div class="task-modal-layout edit-mode">
                <div class="task-form-panel">
                    ${taskFormContent}
                    ${commonConfigHtml}
                </div>
            </div>
        `;
    } else {
        // Temu任务和财务任务使用两栏布局：左侧表单（包含特有表单+通用配置），右侧店铺
        modalBody.innerHTML = `
            <div class="task-modal-layout">
                <div class="task-form-panel">
                    ${taskFormContent}
                    ${commonConfigHtml}
                </div>
                ${taskShopPanelHtml}
            </div>
        `;
    }

    // 加载店铺数据（非虎扑任务且非编辑模式）
    if (taskType !== 'hupu_post_list' && taskType !== 'hupu_detail_list' && taskType !== 'hupu_score_list' && !isEdit) {
        loadShopSelection();
    }

    // 初始化组件
    setTimeout(() => {
        if (taskType === 'hupu_post_list') {
            // 初始化虎扑帖子列表任务的复选框
            if ($('#hupuOnlyOnePageCheckbox').length) $('#hupuOnlyOnePageCheckbox').checkbox();
        } else if (taskType === 'hupu_detail_list') {
            // 初始化虎扑帖子详情任务的复选框
            if ($('#hupuDetailOnlyOnePageCheckbox').length) $('#hupuDetailOnlyOnePageCheckbox').checkbox();
        } else if (taskType === 'financial_full' || taskType === 'financial_export' || taskType === 'financial_merge' || taskType === 'financial_record' || taskType === 'financial_calculate' || taskType === 'sku_summary') {
            // 初始化月份选择器（财务报表任务）
            _selectedMonths = new Set();
            _currentPickerYear = new Date().getFullYear();
            renderMonthPicker();
        }

        if (typeof $ !== 'undefined' && $.fn) {
            // 初始化多选下拉
            $('.ui.dropdown[multiple]').dropdown({
                clearable: true,
                placeholder: '请选择',
                forceSelection: false,
                fullTextSearch: false,
                preserveHTML: false // 纯文本匹配
            });

            // 初始化其他单选下拉（排除已在 initCommonTaskConfigListeners 初始化的）
            // 但为了保险，可以全都初始化一遍，semantic ui 支持多次调用
            $('.ui.dropdown:not([multiple])').dropdown({
                clearable: true,
                placeholder: '请选择'
            });

            // 初始化复选框
            if ($('#sleepOpenCheckbox').length) $('#sleepOpenCheckbox').checkbox();
            if ($('#customFixedUploadImgCheckbox').length) $('#customFixedUploadImgCheckbox').checkbox();
        }

        // 初始化通用监听器
        initCommonTaskConfigListeners();

        // 为特定任务类型的组件初始化监听器
        if (taskType === 'upload_real_pic') {
            const checkTypeMode = document.getElementById('checkTypeMode');
            if (checkTypeMode) {
                checkTypeMode.addEventListener('change', function () {
                    const container = document.getElementById('checkTypeInputContainer');
                    if (container) {
                        container.style.display = this.value === '2' ? 'block' : 'none';
                    }
                });
            }
        }
    }, 200);

    // 添加"只爬取指定页"的事件监听器
    setTimeout(() => {
        if (taskType === 'hupu_post_list') {
            const onlyOnePageEl = document.getElementById('hupuOnlyOnePage');
            const specificPageGroup = document.getElementById('hupuSpecificPageGroup');
            
            if (onlyOnePageEl && specificPageGroup) {
                onlyOnePageEl.addEventListener('change', function() {
                    specificPageGroup.style.display = this.checked ? 'block' : 'none';
                });
            }
        } else if (taskType === 'hupu_detail_list') {
            const onlyOnePageEl = document.getElementById('hupuDetailOnlyOnePage');
            const specificPageGroup = document.getElementById('hupuDetailSpecificPageGroup');
            
            if (onlyOnePageEl && specificPageGroup) {
                onlyOnePageEl.addEventListener('change', function() {
                    specificPageGroup.style.display = this.checked ? 'block' : 'none';
                });
            }
        } else if (taskType === 'jit_govern') {
            const onlyOneDayEl = document.getElementById('onlyOneDay');
            const startDateEl = document.getElementById('inputStartDate');
            const endDateEl = document.getElementById('inputEndDate');
            const startDateDisplayEl = document.getElementById('inputStartDateDisplay');
            const endDateDisplayEl = document.getElementById('inputEndDateDisplay');
            
            // 初始化日历组件
            initModernDatePicker('start');
            initModernDatePicker('end');
            
            // 加载并显示默认库存数量
            loadJitDefaultNum();
            
            if (onlyOneDayEl && startDateEl && endDateEl && startDateDisplayEl && endDateDisplayEl) {
                onlyOneDayEl.addEventListener('change', function() {
                    if (this.checked) {
                        if (startDateEl.value) {
                            endDateEl.value = startDateEl.value;
                            endDateDisplayEl.value = startDateDisplayEl.value;
                        } else if (endDateEl.value) {
                            startDateEl.value = endDateEl.value;
                            startDateDisplayEl.value = endDateDisplayEl.value;
                        }
                    }
                });
            }
        }
        
        if (taskType === 'apply_activity') {
            const activityTypeDropdown = document.getElementById('activityTypeDropdown');
            
            if (typeof $ !== 'undefined' && $.fn && activityTypeDropdown) {
                $(activityTypeDropdown).dropdown();
            }
            
            // 初始化选项卡 - 使用手动切换方式
            const activitySelectModeTabs = document.getElementById('activitySelectModeTabs');
            const quickSelectTab = document.getElementById('quickSelectTab');
            const detailedSelectTab = document.getElementById('detailedSelectTab');
            
            if (activitySelectModeTabs) {
                const tabItems = activitySelectModeTabs.querySelectorAll('.item');
                tabItems.forEach(item => {
                    item.addEventListener('click', function(e) {
                        e.preventDefault();
                        const tabName = this.getAttribute('data-tab');
                        
                        // 切换选项卡激活状态
                        tabItems.forEach(i => i.classList.remove('active'));
                        this.classList.add('active');
                        
                        // 切换内容显示
                        if (tabName === 'quick') {
                            if (quickSelectTab) {
                                quickSelectTab.classList.add('active');
                                quickSelectTab.style.display = 'block';
                            }
                            if (detailedSelectTab) {
                                detailedSelectTab.classList.remove('active');
                                detailedSelectTab.style.display = 'none';
                            }
                        } else if (tabName === 'detailed') {
                            if (quickSelectTab) {
                                quickSelectTab.classList.remove('active');
                                quickSelectTab.style.display = 'none';
                            }
                            if (detailedSelectTab) {
                                detailedSelectTab.classList.add('active');
                                detailedSelectTab.style.display = 'block';
                            }
                        }
                    });
                });
            }
            
            // 初始化详细活动下拉框
            const detailedActivityDropdown = document.getElementById('detailedActivityDropdown');
            if (typeof $ !== 'undefined' && $.fn && detailedActivityDropdown) {
                $(detailedActivityDropdown).dropdown();
            }
            
            // 加载已保存的详细活动列表
            if (!isEdit) {
                loadSavedDetailedActivityList();
            }
            
            // 初始化排除SKC列表展开按钮
            const notSkcListExpandBtn = document.getElementById('notSkcListExpandBtn');
            if (notSkcListExpandBtn) {
                notSkcListExpandBtn.addEventListener('click', function() {
                    const section = document.getElementById('notSkcListSection');
                    if (section) {
                        const isHidden = section.style.display === 'none';
                        section.style.display = isHidden ? 'block' : 'none';
                        const icon = this.querySelector('.icon');
                        if (icon) {
                            icon.className = isHidden ? 'caret up icon' : 'caret down icon';
                        }
                    }
                });
            }
        } else if (taskType === 'expected_goods_place') {
            const expectedMaxPageDropdown = document.getElementById('expectedMaxPageDropdown');
            const expectedCatIdDropdown = document.getElementById('expectedCatIdDropdown');
            const expectedAddCategoryCheckbox = document.getElementById('expectedAddCategoryCheckbox');
            if (typeof $ !== 'undefined' && $.fn) {
                if (expectedCatIdDropdown) {
                    $(expectedCatIdDropdown).dropdown({ clearable: false });
                }
                // 期望到货地点使用原生radio按钮，不需要初始化
                // 初始化类目搜索展开按钮
                const expectedCategoryExpandBtn = document.getElementById('expectedCategoryExpandBtn');
                if (expectedCategoryExpandBtn) {
                    expectedCategoryExpandBtn.addEventListener('click', function() {
                        const addSection = document.getElementById('expectedCategoryAddSection');
                        const btnSpan = this.querySelector('span');
                        if (addSection) {
                            const isHidden = addSection.style.display === 'none';
                            addSection.style.display = isHidden ? 'block' : 'none';
                            const icon = this.querySelector('.icon');
                            if (icon) {
                                icon.className = isHidden ? 'caret up icon' : 'caret down icon';
                            }
                            if (btnSpan) {
                                btnSpan.textContent = isHidden ? '收起类目搜索' : '展开类目搜索';
                            }
                        }
                    });
                }

                const expectedCategoryModeTabs = document.getElementById('expectedCategoryModeTabs');
                const keywordSearchTab = document.getElementById('keywordSearchTab');
                const goodsSnSearchTab = document.getElementById('goodsSnSearchTab');

                if (expectedCategoryModeTabs) {
                    const tabItems = expectedCategoryModeTabs.querySelectorAll('.item');
                    tabItems.forEach(item => {
                        item.addEventListener('click', function(e) {
                            e.preventDefault();
                            const tabName = this.getAttribute('data-tab');

                            tabItems.forEach(i => i.classList.remove('active'));
                            this.classList.add('active');

                            if (tabName === 'keyword-search') {
                                if (keywordSearchTab) {
                                    keywordSearchTab.classList.add('active');
                                    keywordSearchTab.style.display = 'block';
                                }
                                if (goodsSnSearchTab) {
                                    goodsSnSearchTab.classList.remove('active');
                                    goodsSnSearchTab.style.display = 'none';
                                }
                            } else if (tabName === 'goods-sn-search') {
                                if (keywordSearchTab) {
                                    keywordSearchTab.classList.remove('active');
                                    keywordSearchTab.style.display = 'none';
                                }
                                if (goodsSnSearchTab) {
                                    goodsSnSearchTab.classList.add('active');
                                    goodsSnSearchTab.style.display = 'block';
                                }
                            }
                        });
                    });
                }

                // 从数据库加载类目列表
                // 编辑模式下不调用，因为 fillTaskParams 会调用并传入需要选中的类目
                if (!isEdit) {
                    loadSavedCategoryList();
                }
            }
        }
    }, 200);

    // 更新提交按钮文本（编辑模式显示"修改"，否则显示"提交"）
    setTimeout(() => {
        const submitBtn = document.getElementById('taskModalSubmitBtn') || document.querySelector('#taskModal .actions .ui.primary.button');
        if (submitBtn) {
            if (isEdit) {
                submitBtn.textContent = '修改';
            } else {
                submitBtn.textContent = '提交任务';
            }
        }
    }, 300);

    // 模态框样式调整
    if (typeof $ !== 'undefined' && $.fn.modal) {
        // 虎扑任务或编辑模式使用单面板模态框（不带店铺管理，较窄）
        if (taskType === 'hupu_post_list' || taskType === 'hupu_detail_list' || taskType === 'hupu_score_list' || isEdit) {
            $('#taskModal').removeClass('wide-modal').addClass('single-panel-modal').modal('show');
        } else {
            // Temu任务和财务任务使用宽模态框（带店铺管理）
            $('#taskModal').removeClass('single-panel-modal').addClass('wide-modal').modal('show');
        }
    } else {
        // 虎扑任务或编辑模式使用单面板模态框（不带店铺管理，较窄）
        if (taskType === 'hupu_post_list' || taskType === 'hupu_detail_list' || taskType === 'hupu_score_list' || isEdit) {
            modal.classList.remove('wide-modal');
            modal.classList.add('single-panel-modal');
        } else {
            // Temu任务和财务任务使用宽模态框（带店铺管理）
            modal.classList.remove('single-panel-modal');
            modal.classList.add('wide-modal');
        }
        modal.classList.add('active');
    }
}

function getTaskTitle(taskType) {
    const titles = {
        'upload_real_pic': '实拍图全部重跑任务',
        'modify_price': '自动核价任务',
        'jit_govern': 'JIT维护库存任务',
        'adjust_price': '调价管理',
        'apply_activity': '报活动任务',
        'expected_goods_place': '批量修改期望到货地点',
        'financial_full': '生成财务报表全流程',
        'financial_export': '导出月份账单',
        'financial_merge': '融合月份账单',
        'financial_record': '记录到总表',
        'financial_calculate': '计算并生成财务报表',
        'sku_summary': '生成SKU汇总表',
        'hupu_post_list': '虎扑帖子列表采集',
        'hupu_detail_list': '虎扑帖子详情采集',
        'hupu_score_list': '虎扑评分采集',
        'purchase_delivery': '批量加入发货台'
    };
    return titles[taskType] || '任务配置';
}

// 店铺选择相关函数已移至 task_common.js

// 自动获取帖子标题
let getPostTitleTimer = null;

async function autoGetPostTitle() {
    const postInput = document.getElementById('hupuDetailName');
    const titleInput = document.getElementById('hupuDetailTitle');
    
    if (!postInput || !titleInput) {
        return;
    }
    
    const postValue = postInput.value.trim();
    
    // 清除之前的定时器
    if (getPostTitleTimer) {
        clearTimeout(getPostTitleTimer);
    }
    
    // 如果输入为空，清空标题
    if (!postValue) {
        titleInput.value = '';
        return;
    }
    
    // 设置防抖定时器（500ms）
    getPostTitleTimer = setTimeout(async () => {
        try {
            const result = await requestPost('/api/get_post_title', {}, { post_input: postValue });
            
            if (result && result.success) {
                const postTitle = result.data.post_title || '';
                titleInput.value = postTitle;
                console.log('获取帖子标题成功:', postTitle);
            } else {
                console.error('获取帖子标题失败:', result.error_msg || '未知错误');
            }
        } catch (error) {
            console.error('获取帖子标题异常:', error);
        }
    }, 500);
}

// 自动获取评分标题
let getScoreTitleTimer = null;

async function autoGetScoreTitle() {
    const scoreInput = document.getElementById('hupuScoreId');
    const titleInput = document.getElementById('hupuScoreTitle');
    
    if (!scoreInput || !titleInput) {
        return;
    }
    
    const scoreValue = scoreInput.value.trim();
    
    // 清除之前的定时器
    if (getScoreTitleTimer) {
        clearTimeout(getScoreTitleTimer);
    }
    
    // 如果输入为空，清空标题
    if (!scoreValue) {
        titleInput.value = '';
        return;
    }
    
    // 设置防抖定时器（500ms）
    getScoreTitleTimer = setTimeout(async () => {
        try {
            const result = await requestPost('/api/get_score_title', {}, { score_input: scoreValue });
            
            if (result && result.success) {
                const scoreTitle = result.data.score_title || '';
                titleInput.value = scoreTitle;
                console.log('获取评分标题成功:', scoreTitle);
            } else {
                console.error('获取评分标题失败:', result.error_msg || '未知错误');
            }
        } catch (error) {
            console.error('获取评分标题异常:', error);
        }
    }, 500);
}

// 提交任务
async function submitTask() {
    // 处理添加类目的逻辑
    handleExpectedCategoryAdd();
    
    const { taskType, taskId, isEdit } = currentModalData;
    console.log('submitTask called, taskType:', taskType, 'isEdit:', isEdit);
    let requestData = {
        task_type: taskType
    };

    // 如果是编辑模式，添加任务ID
    if (isEdit && taskId) {
        requestData.task_id = taskId;
    }

    // 虎扑任务不需要店铺选择（编辑模式下也不需要验证）
    if (!isEdit && taskType !== 'hupu_post_list' && taskType !== 'hupu_detail_list' && taskType !== 'hupu_score_list') {
        const selectedCheckboxes = document.querySelectorAll('#shopSelectionArea input[type="checkbox"]:checked');
        if (selectedCheckboxes.length === 0) {
            showWarning('请至少选择一个店铺！');
            return;
        }
        // 获取选中的店铺UID
        const selectedShopUids = Array.from(selectedCheckboxes).map(cb => {
            const shop = JSON.parse(cb.dataset.shop);
            return shop.uid;
        }); // 过滤掉undefined或null的uid

        if (selectedShopUids.length === 0) {
            showWarning('请至少选择一个有效的店铺（需要包含UID）！');
            return;
        }
        requestData.selected_shop_uids = selectedShopUids;
    }

    if (taskType === 'upload_real_pic') {
            console.log('Processing upload_real_pic task');
            // 实拍图全部重跑任务 - 使用新的参数格式
            const taskKwargs = {};

            // 实拍图识别类型（多选下拉）
            const checkTypeDropdown = $('#inputCheckTypeList');
            let selectedCheckTypes = [];
            try {
                const value = checkTypeDropdown.dropdown('get value');
                // Semantic UI 多选下拉返回的可能是字符串或数组
                if (Array.isArray(value)) {
                    selectedCheckTypes = value;
                } else if (typeof value === 'string' && value) {
                    selectedCheckTypes = [value];
                } else if (value) {
                    selectedCheckTypes = [value];
                }
            } catch (e) {
                console.warn('获取实拍图识别类型失败:', e);
            }
            taskKwargs.input_check_type_list = selectedCheckTypes.length > 0
                ? selectedCheckTypes.map(v => parseInt(String(v))).filter(v => !isNaN(v))
                : [];

            // 快速筛选（单选下拉）
            const rapidScreenStatusEl = document.getElementById('inputRapidScreenStatusList');
            const rapidScreenStatus = rapidScreenStatusEl ? rapidScreenStatusEl.value : '';
            taskKwargs.input_rapid_screen_status_list = rapidScreenStatus
                ? [parseInt(rapidScreenStatus)]
                : [];

            // 指定SPU ID（手动输入）
            const spuIdsInputEl = document.getElementById('inputSpuIdList');
            const spuIdsInput = spuIdsInputEl ? spuIdsInputEl.value.trim() : '';
            taskKwargs.input_spu_id_list = spuIdsInput
                ? spuIdsInput.split(/[,，\s]+/).map(id => parseInt(id.trim())).filter(id => !isNaN(id) && id > 0)
                : [];

            // 敏感词识别结果（多选下拉）
            const blackWordDropdown = $('#blackWordTypeList');
            let selectedBlackWords = [];
            try {
                const value = blackWordDropdown.dropdown('get value');
                if (Array.isArray(value)) {
                    selectedBlackWords = value;
                } else if (typeof value === 'string' && value) {
                    selectedBlackWords = [value];
                } else if (value) {
                    selectedBlackWords = [value];
                }
            } catch (e) {
                console.warn('获取敏感词识别结果失败:', e);
            }
            taskKwargs.black_word_type_list = selectedBlackWords.length > 0
                ? selectedBlackWords.map(v => parseInt(String(v))).filter(v => !isNaN(v))
                : [];

            // 商品状态筛选（多选下拉）
            const goodsStatusDropdown = $('#goodsStatusList');
            let selectedGoodsStatus = [];
            try {
                const value = goodsStatusDropdown.dropdown('get value');
                if (Array.isArray(value)) {
                    selectedGoodsStatus = value;
                } else if (typeof value === 'string' && value) {
                    selectedGoodsStatus = [value];
                } else if (value) {
                    selectedGoodsStatus = [value];
                }
            } catch (e) {
                console.warn('获取商品状态筛选失败:', e);
            }
            taskKwargs.goods_status_list = selectedGoodsStatus.length > 0
                ? selectedGoodsStatus.map(v => parseInt(String(v))).filter(v => !isNaN(v))
                : [];

            // 是否执行额外的休息（开关）
            const sleepOpenEl = document.getElementById('sleepOpen');
            taskKwargs.sleep_open = sleepOpenEl ? sleepOpenEl.checked : false;

            // 是否上传自定义固定上传图片（开关）
            const customFixedUploadImgEl = document.getElementById('customFixedUploadImg');
            taskKwargs.custom_fixed_upload_img = customFixedUploadImgEl ? customFixedUploadImgEl.checked : false;

            // 登录类型 & 无头 & 重置 cookies
            const loginTypeEl = document.getElementById('loginTypeSelect');
            taskKwargs.login_type = loginTypeEl ? (loginTypeEl.value || 'ikun') : 'ikun';
            const headlessInput = document.getElementById('headless');
            taskKwargs.headless = headlessInput ? !headlessInput.checked : false;
            const reloadCookiesInput = document.getElementById('reloadCookies');
            taskKwargs.reload_cookies = reloadCookiesInput ? !!reloadCookiesInput.checked : false;
            const ikunPersistBrowserInput = document.getElementById('ikunPersistBrowser');
            // 需求：勾选“持续显示” => auto_close 为 false；未勾选 => true
            taskKwargs.auto_close = ikunPersistBrowserInput ? !ikunPersistBrowserInput.checked : true;

            // 构建新的请求格式 - 确保 task_kwargs 总是传递一个对象
            console.log('Setting task_kwargs for upload_real_pic:', taskKwargs);
            
            // 编辑模式：保留原有的uid和main_task_id
            if (isEdit && currentModalData) {
                if (currentModalData.originalUid !== undefined) {
                    taskKwargs.uid = currentModalData.originalUid;
                }
                if (currentModalData.originalMainTaskId !== undefined) {
                    taskKwargs.main_task_id = currentModalData.originalMainTaskId;
                }
            }
            
            requestData.task_kwargs = taskKwargs;
            console.log('Final requestData for upload_real_pic:', requestData);
    }

    const submitBtn = document.getElementById('taskModalSubmitBtn') || document.querySelector('#taskModal .actions .ui.primary.button');
    if (!submitBtn) {
        showError('无法找到提交按钮');
        return;
    }
    const originalText = submitBtn.innerHTML;
    submitBtn.innerHTML = '<i class="spinner loading icon"></i> 提交中...';
    submitBtn.classList.add('loading');
    submitBtn.disabled = true;

    try {
        // 如果是自动核价任务/调价任务，确保携带登陆参数和筛选参数
        if (taskType === 'modify_price') {
            const loginTypeEl = document.getElementById('loginTypeSelect');
            const login_type = loginTypeEl ? (loginTypeEl.value || 'ikun') : 'ikun';
            const headlessInput = document.getElementById('headless');
            const reloadCookiesInput = document.getElementById('reloadCookies');

            // 指定SPU ID（手动输入）
            const spuIdsInputEl = document.getElementById('inputSpuIdList');
            const spuIdsInput = spuIdsInputEl ? spuIdsInputEl.value.trim() : '';
            const input_spu_id_list = spuIdsInput
                ? spuIdsInput.split(/[,，\s]+/).map(id => parseInt(id.trim())).filter(id => !isNaN(id) && id > 0)
                : [];

            const ikunPersistBrowserInput = document.getElementById('ikunPersistBrowser');
            const taskKwargs = {
                login_type: login_type,
                headless: headlessInput ? !headlessInput.checked : false,
                reload_cookies: reloadCookiesInput ? !!reloadCookiesInput.checked : false,
                // 需求：勾选“持续显示” => auto_close 为 false；未勾选 => true
                auto_close: ikunPersistBrowserInput ? !ikunPersistBrowserInput.checked : true,
                input_spu_id_list: input_spu_id_list
            };
            // 核价次数、降价金额：留空使用系统配置，临时修改优先于系统配置
            const modifyTimesEl = document.getElementById('inputModifyTimes');
            const modifyTimesRaw = modifyTimesEl ? modifyTimesEl.value.trim() : '';
            const modifyTimes = modifyTimesRaw ? parseInt(modifyTimesRaw, 10) : NaN;
            if (!isNaN(modifyTimes) && modifyTimes >= 1) taskKwargs.modify_times = modifyTimes;
            const minuPriceEl = document.getElementById('inputMinuPrice');
            const minuPriceRaw = minuPriceEl ? minuPriceEl.value.trim() : '';
            const minuPrice = minuPriceRaw ? parseFloat(minuPriceRaw) : NaN;
            if (!isNaN(minuPrice) && minuPrice >= 0) taskKwargs.minu_price = minuPrice;
            
            // 编辑模式：保留原有的uid和main_task_id
            if (isEdit && currentModalData) {
                if (currentModalData.originalUid !== undefined) {
                    taskKwargs.uid = currentModalData.originalUid;
                }
                if (currentModalData.originalMainTaskId !== undefined) {
                    taskKwargs.main_task_id = currentModalData.originalMainTaskId;
                }
            }
            
            requestData.task_kwargs = taskKwargs;
        } else if (taskType === 'jit_govern') {
            const loginTypeEl = document.getElementById('loginTypeSelect');
            const login_type = loginTypeEl ? (loginTypeEl.value || 'ikun') : 'ikun';
            const headlessInput = document.getElementById('headless');
            const reloadCookiesInput = document.getElementById('reloadCookies');

            const spuIdInputEl = document.getElementById('inputSkcSpuList');
            const spuIdInput = spuIdInputEl ? spuIdInputEl.value.trim() : '';
            const spu_id_list = spuIdInput
                ? spuIdInput.split(/[,，\s]+/).map(id => parseInt(id.trim())).filter(id => !isNaN(id) && id > 0)
                : [];

            const startDateEl = document.getElementById('inputStartDate');
            const endDateEl = document.getElementById('inputEndDate');
            const onlyOneDayEl = document.getElementById('onlyOneDay');
            const onlyOneDay = onlyOneDayEl ? onlyOneDayEl.checked : false;

            let start_date = startDateEl ? startDateEl.value.trim() : '';
            let end_date = endDateEl ? endDateEl.value.trim() : '';

            if (onlyOneDay) {
                if (start_date) {
                    end_date = start_date;
                } else if (end_date) {
                    start_date = end_date;
                }
            }

            const finalNumEl = document.getElementById('inputFinalNum');
            const finalNumRaw = finalNumEl ? finalNumEl.value.trim() : '';
            const final_num = finalNumRaw ? parseInt(finalNumRaw, 10) : null;

            const ikunPersistBrowserInput = document.getElementById('ikunPersistBrowser');
            
            const formatDateForApi = (dateStr) => {
                if (!dateStr) return null;
                const parts = dateStr.split('-');
                if (parts.length === 3) {
                    return parts[0] + parts[1] + parts[2];
                }
                return dateStr;
            };
            
            const taskKwargs = {
                login_type: login_type,
                headless: headlessInput ? !headlessInput.checked : false,
                reload_cookies: reloadCookiesInput ? !!reloadCookiesInput.checked : false,
                auto_close: ikunPersistBrowserInput ? !ikunPersistBrowserInput.checked : true,
                spu_id_list: spu_id_list.length > 0 ? spu_id_list : null,
                start_date: formatDateForApi(start_date),
                end_date: formatDateForApi(end_date)
            };
            if (final_num !== null && !isNaN(final_num) && final_num >= 1) taskKwargs.final_num = final_num;
            
            // 编辑模式：保留原有的uid和main_task_id
            if (isEdit && currentModalData) {
                if (currentModalData.originalUid !== undefined) {
                    taskKwargs.uid = currentModalData.originalUid;
                }
                if (currentModalData.originalMainTaskId !== undefined) {
                    taskKwargs.main_task_id = currentModalData.originalMainTaskId;
                }
            }
            
            requestData.task_kwargs = taskKwargs;
        } else if (taskType === 'adjust_price') {
            const loginTypeEl = document.getElementById('loginTypeSelect');
            const login_type = loginTypeEl ? (loginTypeEl.value || 'ikun') : 'ikun';
            const headlessInput = document.getElementById('headless');
            const reloadCookiesInput = document.getElementById('reloadCookies');

            const skcInputEl = document.getElementById('inputSkcIdList');
            const orderInputEl = document.getElementById('inputOrderIdList');

            const skc_id_list = skcInputEl && skcInputEl.value
                ? skcInputEl.value.split(/[,，\s]+/).map(id => parseInt(id.trim())).filter(id => !isNaN(id) && id > 0)
                : [];
            const order_id_list = orderInputEl && orderInputEl.value
                ? orderInputEl.value.split(/[,，\s]+/).map(id => parseInt(id.trim())).filter(id => !isNaN(id) && id > 0)
                : [];

            const ikunPersistBrowserInput = document.getElementById('ikunPersistBrowser');
            const taskKwargs = {
                login_type: login_type,
                headless: headlessInput ? !headlessInput.checked : false,
                reload_cookies: reloadCookiesInput ? !!reloadCookiesInput.checked : false,
                // 需求：勾选“持续显示” => auto_close 为 false；未勾选 => true
                auto_close: ikunPersistBrowserInput ? !ikunPersistBrowserInput.checked : true,
                skc_id_list,
                order_id_list
            };
            
            // 编辑模式：保留原有的uid和main_task_id
            if (isEdit && currentModalData) {
                if (currentModalData.originalUid !== undefined) {
                    taskKwargs.uid = currentModalData.originalUid;
                }
                if (currentModalData.originalMainTaskId !== undefined) {
                    taskKwargs.main_task_id = currentModalData.originalMainTaskId;
                }
            }
            
            requestData.task_kwargs = taskKwargs;
        } else if (taskType === 'apply_activity') {
            const loginTypeEl = document.getElementById('loginTypeSelect');
            const login_type = loginTypeEl ? (loginTypeEl.value || 'ikun') : 'ikun';
            const headlessInput = document.getElementById('headless');
            const reloadCookiesInput = document.getElementById('reloadCookies');

            const spuIdsInputEl = document.getElementById('inputSpuIdList');
            const spuIdsInput = spuIdsInputEl ? spuIdsInputEl.value.trim() : '';
            const spu_id_list = spuIdsInput
                ? spuIdsInput.split(/[,，\s]+/).map(id => parseInt(id.trim())).filter(id => !isNaN(id) && id > 0)
                : [];

            const activityTypeListEl = document.getElementById('inputActivityTypeList');
            const activityTypeManualEl = document.getElementById('inputActivityTypeManual');
            const activityTypeManual = activityTypeManualEl ? activityTypeManualEl.value.trim() : '';
            
            let activityTypeList = [];
            
            if (activityTypeManual) {
                activityTypeList = activityTypeManual.split(/[,，\s]+/).map(id => parseInt(id.trim())).filter(id => !isNaN(id) && id > 0);
            } else if (activityTypeListEl && activityTypeListEl.value) {
                activityTypeList = activityTypeListEl.value.split(',').map(id => parseInt(id.trim())).filter(id => !isNaN(id) && id > 0);
            }

            const ikunPersistBrowserInput = document.getElementById('ikunPersistBrowser');
            const openLogFalseCheckbox = document.getElementById('openLogFalseCheckbox');
            
            // 获取排除SKC列表
            const notSkcInputEl = document.getElementById('inputNotSkcList');
            const notSkcInput = notSkcInputEl ? notSkcInputEl.value.trim() : '';
            const not_skc_list = notSkcInput
                ? notSkcInput.split(/[,，\s]+/).map(id => parseInt(id.trim())).filter(id => !isNaN(id) && id > 0)
                : [];
            
            // 判断当前选择的活动选择方式
            const quickSelectTab = document.getElementById('quickSelectTab');
            const isQuickSelect = quickSelectTab && quickSelectTab.classList.contains('active');
            
            let finalActivityTypeList = null;
            let detailedActivityList = null;
            
            if (isQuickSelect) {
                // 快速选择模式
                if (activityTypeList.length > 0) {
                    finalActivityTypeList = activityTypeList;
                }
            } else {
                // 详细筛选模式
                const detailedActivityDropdown = document.getElementById('detailedActivityDropdown');
                const detailedActivityMenu = document.getElementById('detailedActivityMenu');
                if (detailedActivityDropdown && detailedActivityMenu) {
                    const selectedValues = $(detailedActivityDropdown).dropdown('get value');
                    if (selectedValues) {
                        // 多选模式下，值是以逗号分隔的字符串
                        const valueArray = selectedValues.split(',').filter(v => v.trim());
                        detailedActivityList = [];
                        // 根据选中的ID从菜单中获取对应的活动数据
                        valueArray.forEach(activityId => {
                            const item = detailedActivityMenu.querySelector(`.item[data-value="${activityId}"]`);
                            if (item && item.dataset.activity) {
                                try {
                                    detailedActivityList.push(JSON.parse(item.dataset.activity));
                                } catch (e) {
                                    console.error('解析详细活动数据失败:', e);
                                }
                            }
                        });
                    }
                }
                if (!detailedActivityList || detailedActivityList.length === 0) {
                    showWarning('请至少选择一个具体活动');
                    return;
                }
            }
            
            const taskKwargs = {
                login_type: login_type,
                headless: headlessInput ? !headlessInput.checked : false,
                reload_cookies: reloadCookiesInput ? !!reloadCookiesInput.checked : false,
                auto_close: ikunPersistBrowserInput ? !ikunPersistBrowserInput.checked : true,
                spu_id_list: spu_id_list.length > 0 ? spu_id_list : null,
                activityType_list: finalActivityTypeList,
                detailed_activity_list: detailedActivityList,
                open_log_false: openLogFalseCheckbox ? openLogFalseCheckbox.checked : false,
                not_skc_list: not_skc_list.length > 0 ? not_skc_list : null
            };
            
            // 编辑模式：保留原有的uid和main_task_id
            if (isEdit && currentModalData) {
                if (currentModalData.originalUid !== undefined) {
                    taskKwargs.uid = currentModalData.originalUid;
                }
                if (currentModalData.originalMainTaskId !== undefined) {
                    taskKwargs.main_task_id = currentModalData.originalMainTaskId;
                }
            }
            
            requestData.task_kwargs = taskKwargs;
        } else if (taskType === 'purchase_delivery') {
            const loginTypeEl = document.getElementById('loginTypeSelect');
            const login_type = loginTypeEl ? (loginTypeEl.value || 'ikun') : 'ikun';
            const headlessInput = document.getElementById('headless');
            const reloadCookiesInput = document.getElementById('reloadCookies');
            const ikunPersistBrowserInput = document.getElementById('ikunPersistBrowser');

            const maxCyclesEl = document.getElementById('inputMaxCycles');
            const maxCycles = maxCyclesEl ? parseInt(maxCyclesEl.value) || 5 : 5;

            const customFixedUploadImgEl = document.getElementById('customFixedUploadImg');
            const custom_fixed_upload_img = customFixedUploadImgEl ? customFixedUploadImgEl.checked : false;

            const skipUploadPicEl = document.getElementById('skipUploadPic');
            const skip_upload_pic = skipUploadPicEl ? skipUploadPicEl.checked : false;

            const taskKwargs = {
                login_type: login_type,
                headless: headlessInput ? !headlessInput.checked : false,
                reload_cookies: reloadCookiesInput ? !!reloadCookiesInput.checked : false,
                auto_close: ikunPersistBrowserInput ? !ikunPersistBrowserInput.checked : true,
                max_cycles: maxCycles,
                skip_upload_pic: skip_upload_pic,
                custom_fixed_upload_img: custom_fixed_upload_img
            };

            if (isEdit && currentModalData) {
                if (currentModalData.originalUid !== undefined) {
                    taskKwargs.uid = currentModalData.originalUid;
                }
                if (currentModalData.originalMainTaskId !== undefined) {
                    taskKwargs.main_task_id = currentModalData.originalMainTaskId;
                }
            }

            requestData.task_kwargs = taskKwargs;
        } else if (taskType === 'expected_goods_place') {
            const loginTypeEl = document.getElementById('loginTypeSelect');
            const login_type = loginTypeEl ? (loginTypeEl.value || 'ikun') : 'ikun';
            const headlessInput = document.getElementById('headless');
            const reloadCookiesInput = document.getElementById('reloadCookies');

            const expectedAreaEl = document.querySelector('input[name="expectedArea"]:checked');
            if (!expectedAreaEl) {
                showWarning('请选择期望到货地点！');
                return;
            }
            const exceptReceiveAreaConfigType = parseInt(expectedAreaEl.value, 10);

            const skcInput = document.getElementById('inputExpectedSkcIdList');
            let selectedSkcValues = [];
            if (skcInput) {
                const value = skcInput.value.trim();
                if (value) {
                    // 支持空格、逗号、换行符分割
                    selectedSkcValues = value.split(/[\s,\n]+/).filter(v => v);
                }
            }
            const skc_id_list = selectedSkcValues.length > 0
                ? selectedSkcValues.map(v => parseInt(String(v))).filter(v => !isNaN(v) && v > 0)
                : [];

            const catDropdown = $('#expectedCatIdDropdown');
            let selectedCatValues = [];
            let cat_id_list = [];
            try {
                const value = catDropdown.dropdown('get value');
                if (Array.isArray(value)) {
                    selectedCatValues = value;
                } else if (typeof value === 'string' && value) {
                    selectedCatValues = value.split(',').map(v => v.trim()).filter(v => v);
                }
                
                if (selectedCatValues.length > 0) {
                    console.log('选中的类目值:', selectedCatValues);
                    try {
                        const data = await requestPost('/api/get_saved_category_list', {}, {});
                        console.log('从API获取的类目列表:', data);
                        if (data.success) {
                            const categoryList = data.data || [];
                            console.log('数据库中的类目列表长度:', categoryList.length);
                            selectedCatValues.forEach(selectedValue => {
                                console.log('正在匹配选中的值:', selectedValue);
                                categoryList.forEach(cat => {
                                    const catId = cat.cat_ids && cat.cat_ids.length > 0 ? String(cat.cat_ids[cat.cat_ids.length - 1]) : '';
                                    console.log('比较:', selectedValue, '===', catId, ':', String(selectedValue) === catId);
                                    if (catId === String(selectedValue)) {
                                        if (cat.cat_ids && cat.cat_names) {
                                            cat_id_list.push({
                                                cat_ids: cat.cat_ids,
                                                cat_names: cat.cat_names
                                            });
                                            console.log('匹配成功，添加类目:', cat);
                                        }
                                    }
                                });
                            });
                            console.log('最终构建的 cat_id_list:', cat_id_list);
                        }
                    } catch (e) {
                        console.warn('获取类目列表失败:', e);
                    }
                }
            } catch (e) {
                console.warn('获取类目列表失败:', e);
            }

            if (cat_id_list.length === 0 && skc_id_list.length === 0) {
                showWarning('请至少选择一个类目或输入SKC列表！');
                return;
            }

            const ikunPersistBrowserInput = document.getElementById('ikunPersistBrowser');
            const taskKwargs = {
                login_type: login_type,
                headless: headlessInput ? !headlessInput.checked : false,
                reload_cookies: reloadCookiesInput ? !!reloadCookiesInput.checked : false,
                auto_close: ikunPersistBrowserInput ? !ikunPersistBrowserInput.checked : true,
                skc_id_list,
                cat_id_list,
                exceptReceiveAreaConfigType
            };

            if (isEdit && currentModalData) {
                if (currentModalData.originalUid !== undefined) {
                    taskKwargs.uid = currentModalData.originalUid;
                }
                if (currentModalData.originalMainTaskId !== undefined) {
                    taskKwargs.main_task_id = currentModalData.originalMainTaskId;
                }
            }

            requestData.task_kwargs = taskKwargs;
        } else if (taskType === 'hupu_post_list') {
            // 虎扑帖子列表采集任务
            // 获取必填项：关键词
            const keywordEl = document.getElementById('hupuKeyword');
            const keyword = keywordEl ? keywordEl.value.trim() : '';
            if (!keyword) {
                showWarning('请输入关键词！');
                return;
            }

            // 获取必填项：最大页数
            const maxPagesEl = document.getElementById('hupuMaxPages');
            const maxPages = maxPagesEl ? parseInt(maxPagesEl.value) : 1;
            if (!maxPages || maxPages < 1) {
                showWarning('请输入有效的最大页数！');
                return;
            }

            // 获取可选参数
            const sleepTimeEl = document.getElementById('hupuSleepTime');
            const sleepTime = sleepTimeEl ? parseFloat(sleepTimeEl.value) : 0.3;

            const sortbyEl = document.getElementById('hupuSortby');
            const sortby = sortbyEl ? sortbyEl.value : 'general';

            const topicIdEl = document.getElementById('hupuTopicId');
            const topicId = topicIdEl ? topicIdEl.value.trim() : '';

            const onlyOnePageEl = document.getElementById('hupuOnlyOnePage');
            const onlyOnePage = onlyOnePageEl ? onlyOnePageEl.checked : false;

            // 获取指定页数
            let specificPage = 1;
            if (onlyOnePage) {
                const specificPageEl = document.getElementById('hupuSpecificPage');
                specificPage = specificPageEl ? parseInt(specificPageEl.value) : 1;
                if (!specificPage || specificPage < 1) {
                    showWarning('请输入有效的指定页数！');
                    return;
                }
            }

            // 生成任务名称（仅在非编辑模式下）
            if (!isEdit) {
                const taskName = `虎扑帖子列表-${keyword}`;
                requestData.task_name = taskName;
            }

            const taskKwargs = {
                keyword: keyword,
                max_pages: maxPages,
                sleep_time: sleepTime,
                sortby: sortby,
                topic_id: topicId,
                only_one_page: onlyOnePage,
                specific_page: specificPage
            };
            
            // 编辑模式：保留原有的uid和main_task_id
            if (isEdit && currentModalData) {
                if (currentModalData.originalUid !== undefined) {
                    taskKwargs.uid = currentModalData.originalUid;
                }
                if (currentModalData.originalMainTaskId !== undefined) {
                    taskKwargs.main_task_id = currentModalData.originalMainTaskId;
                }
            }
            
            requestData.task_kwargs = taskKwargs;
        } else if (taskType === 'hupu_detail_list') {
            // 虎扑帖子详情采集任务
            // 获取必填项：帖子ID/名称
            const nameEl = document.getElementById('hupuDetailName');
            let name = nameEl ? nameEl.value.trim() : '';
            if (!name) {
                showWarning('请输入帖子ID或名称！');
                return;
            }

            // 提取帖子ID（如果输入的是URL）
            let postId = name;
            if (name.includes('hupu.com')) {
                // 从URL中提取帖子ID
                // 格式: https://bbs.hupu.com/637618639.html
                const parts = name.split('/');
                for (const part of parts) {
                    if (part.endsWith('.html')) {
                        postId = part.replace('.html', '');
                        break;
                    }
                }
            } else if (name.includes('-')) {
                // 如果是 "标题-ID" 格式，提取ID
                postId = name.split('-').pop();
            }

            // 获取帖子标题
            const titleEl = document.getElementById('hupuDetailTitle');
            const postTitle = titleEl ? titleEl.value.trim() : '';

            // 如果帖子标题为空，弹出确认对话框
            if (!postTitle) {
                try {
                    await openConfirmModal('未获取到帖子标题，是否不获取标题直接提交？');
                } catch (error) {
                    // 用户取消操作
                    return;
                }
            }

            // 获取必填项：页数
            const maxPagesEl = document.getElementById('hupuDetailMaxPages');
            const maxPages = maxPagesEl ? parseInt(maxPagesEl.value) : 1;
            if (!maxPages || maxPages < 1) {
                showWarning('请输入有效的页数！');
                return;
            }

            // 获取可选参数
            const sleepTimeEl = document.getElementById('hupuDetailSleepTime');
            const sleepTime = sleepTimeEl ? parseFloat(sleepTimeEl.value) : 0.3;

            const onlyOnePageEl = document.getElementById('hupuDetailOnlyOnePage');
            const onlyOnePage = onlyOnePageEl ? onlyOnePageEl.checked : false;

            // 获取指定页数
            let specificPage = 1;
            if (onlyOnePage) {
                const specificPageEl = document.getElementById('hupuDetailSpecificPage');
                specificPage = specificPageEl ? parseInt(specificPageEl.value) : 1;
                if (!specificPage || specificPage < 1) {
                    showWarning('请输入有效的指定页数！');
                    return;
                }
            }

            // 生成任务名称（仅在非编辑模式下）
            if (!isEdit) {
                const taskName = postTitle ? `虎扑帖子详情-${postTitle}` : `虎扑帖子详情-id${postId}`;
                requestData.task_name = taskName;
            }

            const taskKwargs = {
                name: postId,
                post_title: postTitle,
                max_pages: maxPages,
                sleep_time: sleepTime,
                only_one_page: onlyOnePage,
                specific_page: specificPage
            };
            
            // 编辑模式：保留原有的uid和main_task_id
            if (isEdit && currentModalData) {
                if (currentModalData.originalUid !== undefined) {
                    taskKwargs.uid = currentModalData.originalUid;
                }
                if (currentModalData.originalMainTaskId !== undefined) {
                    taskKwargs.main_task_id = currentModalData.originalMainTaskId;
                }
            }
            
            requestData.task_kwargs = taskKwargs;
        } else if (taskType === 'hupu_score_list') {
            // 虎扑评分采集任务
            // 获取必填项：评分ID
            const scoreIdEl = document.getElementById('hupuScoreId');
            let scoreId = scoreIdEl ? scoreIdEl.value.trim() : '';
            if (!scoreId) {
                showWarning('请输入评分ID！');
                return;
            }

            // 提取评分ID（如果输入的是URL）
            let actualScoreId = scoreId;
            if (scoreId.includes('hupu.com')) {
                // 处理第一种格式：https://bbsactivity.hupu.com/pc-viewer/index.html?t=https%3A%2F%2Fm.hupu.com%2Fscore-item%2Fcommon_second%2F26848
                if (scoreId.includes('bbsactivity.hupu.com') && scoreId.includes('?')) {
                    try {
                        const url = new URL(scoreId);
                        const tParam = url.searchParams.get('t');
                        if (tParam) {
                            // URL解码
                            const actualUrl = decodeURIComponent(tParam);
                            // 从实际URL中提取评分ID
                            // 格式: https://m.hupu.com/score-item/common_second/26848
                            const parts = actualUrl.split('/');
                            for (const part of parts) {
                                if (/^\d+$/.test(part)) {
                                    actualScoreId = part;
                                    break;
                                }
                            }
                        }
                    } catch (e) {
                        console.error('解析URL失败:', e);
                    }
                } else {
                    // 处理第二种格式：https://m.hupu.com/score-item/common_second/26848
                    const parts = scoreId.split('/');
                    for (const part of parts) {
                        if (/^\d+$/.test(part)) {
                            actualScoreId = part;
                            break;
                        }
                    }
                }
            }

            // 获取评分标题
            const titleEl = document.getElementById('hupuScoreTitle');
            const scoreTitle = titleEl ? titleEl.value.trim() : '';

            // 如果评分标题为空，弹出确认对话框
            if (!scoreTitle) {
                try {
                    await openConfirmModal('未获取到评分标题，是否不获取标题直接提交？');
                } catch (error) {
                    // 用户取消操作
                    return;
                }
            }

            // 获取必填项：最大页数
            const maxPagesEl = document.getElementById('hupuScoreMaxPages');
            const maxPages = maxPagesEl ? parseInt(maxPagesEl.value) : 1;
            if (!maxPages || maxPages < 1) {
                showWarning('请输入有效的最大页数！');
                return;
            }

            // 获取可选参数
            const sleepTimeEl = document.getElementById('hupuScoreSleepTime');
            const sleepTime = sleepTimeEl ? parseFloat(sleepTimeEl.value) : 0.3;

            // 生成任务名称（仅在非编辑模式下）
            if (!isEdit) {
                const taskName = scoreTitle ? `虎扑评分采集-${scoreTitle}` : `虎扑评分采集-id${actualScoreId}`;
                requestData.task_name = taskName;
            }

            const taskKwargs = {
                score_id: actualScoreId,
                score_title: scoreTitle,
                max_pages: maxPages,
                sleep_time: sleepTime
            };
            
            // 编辑模式：保留原有的uid和main_task_id
            if (isEdit && currentModalData) {
                if (currentModalData.originalUid !== undefined) {
                    taskKwargs.uid = currentModalData.originalUid;
                }
                if (currentModalData.originalMainTaskId !== undefined) {
                    taskKwargs.main_task_id = currentModalData.originalMainTaskId;
                }
            }
            
            requestData.task_kwargs = taskKwargs;
        } else if (taskType === 'financial_full' || taskType === 'financial_export' || taskType === 'financial_merge' || taskType === 'financial_record' || taskType === 'financial_calculate' || taskType === 'sku_summary') {
            // 财务报表任务 - 使用完整登录配置
            const loginTypeEl = document.getElementById('loginTypeSelect');
            const login_type = loginTypeEl ? (loginTypeEl.value || 'ikun') : 'ikun';
            const headlessInput = document.getElementById('headless');
            const reloadCookiesInput = document.getElementById('reloadCookies');
            const ikunPersistBrowserInput = document.getElementById('ikunPersistBrowser');

            // 获取月份列表
            let monthList = Array.from(_selectedMonths);

            if (monthList.length === 0) {
                showWarning('请至少选择一个月份！');
                return;
            }

            const taskKwargs = {
                login_type: login_type,
                headless: headlessInput ? !headlessInput.checked : false,
                reload_cookies: reloadCookiesInput ? !!reloadCookiesInput.checked : false,
                auto_close: ikunPersistBrowserInput ? !ikunPersistBrowserInput.checked : true,
                months_list: monthList
            };
            
            // 编辑模式：保留原有的uid和main_task_id
            if (isEdit && currentModalData) {
                if (currentModalData.originalUid !== undefined) {
                    taskKwargs.uid = currentModalData.originalUid;
                }
                if (currentModalData.originalMainTaskId !== undefined) {
                    taskKwargs.main_task_id = currentModalData.originalMainTaskId;
                }
            }
            
            requestData.task_kwargs = taskKwargs;
        }
        
        // is_maintain_task 放在请求体外层
        requestData.is_maintain_task = (document.getElementById('isMaintainTask') && document.getElementById('isMaintainTask').checked) ? 1 : 0;
        
        // 添加定时任务参数
        const enableSchedule = document.getElementById('enableSchedule');
        if (enableSchedule && enableSchedule.checked) {
            const scheduleType = document.getElementById('scheduleType').value;
            const scheduleTime = document.getElementById('scheduleTime').value;
            const scheduleInterval = document.getElementById('scheduleInterval').value;
            const executeImmediately = document.getElementById('executeImmediately').checked;
            
            requestData.schedule_enabled = true;
            requestData.schedule_type = scheduleType;
            requestData.execute_immediately = executeImmediately;
            
            if (scheduleType === 'once') {
                requestData.schedule_time = scheduleTime;
            } else if (scheduleType === 'interval') {
                requestData.schedule_interval = parseInt(scheduleInterval);
            }
        } else {
            requestData.schedule_enabled = false;
        }
        
        // 根据任务类型和编辑状态选择不同的接口
        let apiUrl;
        if (isEdit) {
            // 编辑模式：使用更新任务接口
            apiUrl = '/api/update_task';
        } else if (taskType === 'hupu_post_list' || taskType === 'hupu_detail_list' || taskType === 'hupu_score_list') {
            // 虎扑爬虫任务使用专门的接口
            apiUrl = '/api/submit_spider_task';
        } else {
            // 其他任务使用Temu任务接口
            apiUrl = '/api/submit_temu_task';
        }
        
        console.log('About to submit task to:', apiUrl, 'with data:', requestData);
        const result = await requestPost(apiUrl, {}, requestData);
        if (result.success) {
            showSuccess(result.message || result.msg);
            closeModal();
            loadTaskCount();
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError(`${isEdit ? '修改' : '提交'}失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`${isEdit ? '修改' : '提交'}失败：${error.message} `);
    } finally {
        submitBtn.innerHTML = originalText;
        submitBtn.classList.remove('loading');
        submitBtn.disabled = false;
    }
}

// 添加示例SPU
function addExampleSPU() {
    document.getElementById('spuIds').value = '123456,789012,345678,901234';
}

// 关闭模态框
function closeModal() {
    const modal = document.getElementById('taskModal');
    // 使用 Semantic UI 的模态框 API
    if (typeof $ !== 'undefined' && $.fn.modal) {
        $('#taskModal').modal('hide');
    } else {
        modal.classList.remove('active');
    }
    currentModalData = {};
}

// 确认模态框
function openConfirmModal(message) {
    return new Promise((resolve, reject) => {
        showConfirm(message).then(result => {
            if (result) resolve();
            else reject(new Error("用户取消操作"));
        });
    });
}

// 初始化气泡特效
function initBubbleEffects() {
    let lastMoveTime = 0;
    
    // 鼠标移动事件
    document.addEventListener('mousemove', function(e) {
        const now = Date.now();
        // 限制气泡生成频率，每50ms最多生成1次
        if (now - lastMoveTime > 50) {
            createMoveBubbles(e.clientX, e.clientY);
            lastMoveTime = now;
        }
    });
    
    // 鼠标点击事件
    document.addEventListener('click', function(e) {
        createClickBubbles(e.clientX, e.clientY);
    });
}

// 创建点击触发的气泡
function createClickBubbles(x, y) {
    // 生成8-12个气泡
    const bubbleCount = Math.floor(Math.random() * 5) + 8;
    
    for (let i = 0; i < bubbleCount; i++) {
        setTimeout(() => {
            const bubble = document.createElement('div');
            bubble.classList.add('bubble', 'click');
            
            // 随机大小：8-15px
            const size = Math.random() * 8 + 8;
            bubble.style.width = size + 'px';
            bubble.style.height = size + 'px';
            
            // 扩散半径50-80px
            const radius = Math.random() * 30 + 50;
            const angle = (i / bubbleCount) * Math.PI * 2;
            const offsetX = Math.cos(angle) * radius;
            const offsetY = Math.sin(angle) * radius;
            
            bubble.style.left = (x + offsetX - size/2) + 'px';
            bubble.style.top = (y + offsetY - size/2) + 'px';
            
            // 渐变彩色
            const colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FECA57'];
            const color = colors[Math.floor(Math.random() * colors.length)];
            bubble.style.backgroundColor = color;
            bubble.style.opacity = (Math.random() * 0.2 + 0.7).toString(); // 70%-90%透明度
            
            // 添加到页面
            document.body.appendChild(bubble);
            
            // 动画结束后移除
            setTimeout(() => {
                if (bubble.parentNode) {
                    bubble.remove();
                }
            }, 600);
        }, i * 50);
    }
}

// 创建滑动触发的气泡
function createMoveBubbles(x, y) {
    // 生成2-3个气泡
    const bubbleCount = Math.floor(Math.random() * 2) + 2;
    
    for (let i = 0; i < bubbleCount; i++) {
        setTimeout(() => {
            const bubble = document.createElement('div');
            bubble.classList.add('bubble', 'move');
            
            // 随机大小：8-15px
            const size = Math.random() * 8 + 8;
            bubble.style.width = size + 'px';
            bubble.style.height = size + 'px';
            
            // 沿滑动方向轻微偏移
            const offsetX = (Math.random() - 0.5) * 15;
            const offsetY = (Math.random() - 0.5) * 15;
            bubble.style.left = (x + offsetX - size/2) + 'px';
            bubble.style.top = (y + offsetY - size/2) + 'px';
            
            // 渐变彩色
            const colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FECA57'];
            const color = colors[Math.floor(Math.random() * colors.length)];
            bubble.style.backgroundColor = color;
            bubble.style.opacity = (Math.random() * 0.2 + 0.7).toString(); // 70%-90%透明度
            
            // 添加到页面
            document.body.appendChild(bubble);
            
            // 动画结束后移除
            setTimeout(() => {
                if (bubble.parentNode) {
                    bubble.remove();
                }
            }, 1100);
        }, i * 100);
    }
}

// 初始化气泡特效
function initBubbleEffects() {
    let lastMoveTime = 0;
    
    // 鼠标移动事件
    document.addEventListener('mousemove', function(e) {
        const now = Date.now();
        // 限制气泡生成频率，每50ms最多生成1次
        if (now - lastMoveTime > 50) {
            createMoveBubbles(e.clientX, e.clientY);
            lastMoveTime = now;
        }
    });
    
    // 鼠标点击事件
    document.addEventListener('click', function(e) {
        createClickBubbles(e.clientX, e.clientY);
    });
}

// 创建点击触发的气泡
function createClickBubbles(x, y) {
    // 生成8-12个气泡
    const bubbleCount = Math.floor(Math.random() * 5) + 8;
    
    for (let i = 0; i < bubbleCount; i++) {
        setTimeout(() => {
            const bubble = document.createElement('div');
            bubble.classList.add('bubble', 'click');
            
            // 随机大小：8-15px
            const size = Math.random() * 8 + 8;
            bubble.style.width = size + 'px';
            bubble.style.height = size + 'px';
            
            // 扩散半径50-80px
            const radius = Math.random() * 30 + 50;
            const angle = (i / bubbleCount) * Math.PI * 2;
            const offsetX = Math.cos(angle) * radius;
            const offsetY = Math.sin(angle) * radius;
            
            bubble.style.left = (x + offsetX - size/2) + 'px';
            bubble.style.top = (y + offsetY - size/2) + 'px';
            
            // 渐变彩色
            const colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FECA57'];
            const color = colors[Math.floor(Math.random() * colors.length)];
            bubble.style.backgroundColor = color;
            bubble.style.opacity = (Math.random() * 0.2 + 0.7).toString(); // 70%-90%透明度
            
            // 添加到页面
            document.body.appendChild(bubble);
            
            // 动画结束后移除
            setTimeout(() => {
                if (bubble.parentNode) {
                    bubble.remove();
                }
            }, 600);
        }, i * 50);
    }
}

// 创建滑动触发的气泡
function createMoveBubbles(x, y) {
    // 生成2-3个气泡
    const bubbleCount = Math.floor(Math.random() * 2) + 2;
    
    for (let i = 0; i < bubbleCount; i++) {
        setTimeout(() => {
            const bubble = document.createElement('div');
            bubble.classList.add('bubble', 'move');
            
            // 随机大小：8-15px
            const size = Math.random() * 8 + 8;
            bubble.style.width = size + 'px';
            bubble.style.height = size + 'px';
            
            // 沿滑动方向轻微偏移
            const offsetX = (Math.random() - 0.5) * 15;
            const offsetY = (Math.random() - 0.5) * 15;
            bubble.style.left = (x + offsetX - size/2) + 'px';
            bubble.style.top = (y + offsetY - size/2) + 'px';
            
            // 渐变彩色
            const colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FECA57'];
            const color = colors[Math.floor(Math.random() * colors.length)];
            bubble.style.backgroundColor = color;
            bubble.style.opacity = (Math.random() * 0.2 + 0.7).toString(); // 70%-90%透明度
            
            // 添加到页面
            document.body.appendChild(bubble);
            
            // 动画结束后移除
            setTimeout(() => {
                if (bubble.parentNode) {
                    bubble.remove();
                }
            }, 1100);
        }, i * 100);
    }
}

// 店铺管理相关接口
async function addShop(browserId) {
    try {
        const result = await requestPost('/api/add_shop', {}, { browser_id: browserId });
        if (result.success) {
            showSuccess(result.message);
            loadShopList();
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError(`添加失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`添加失败：${error.message} `);
    }
}

async function updateAllShops() {
    try {
        const result = await requestPost('/api/update_all_shops', {}, {
            update_type: "full",
            timestamp: new Date().getTime()
        });
        if (result.success) {
            showSuccess(result.message);
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError(`更新失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`请求异常：${error.message} `);
    }
}

async function modifyShopBrowserId(shopAbbr, newBrowserId) {
    try {
        const result = await requestPost('/api/modify_shop_id', {}, {
            shop_abbr: shopAbbr,
            new_browser_id: newBrowserId
        });
        if (result.success) {
            showSuccess(result.message);
            loadShopList();
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError(`修改失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`修改失败：${error.message} `);
    }
}

async function deletePageRecord(shopAbbr) {
    try {
        const result = await requestPost('/api/delete_page_record', {}, { shop_abbr: shopAbbr });
        if (result.success) {
            showSuccess(result.message);
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError(`删除失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`删除失败：${error.message} `);
    }
}

// 删除店铺（基于UID）
async function deleteShop(uid, browserIdForDisplay = '') {
    const displayId = browserIdForDisplay || uid;
    const confirmed = await showConfirm(`确定要删除店铺（标识：${displayId}）吗？此操作不可恢复！`);
    if (!confirmed) {
        return;
    }

    try {
        const result = await requestPost('/api/delete_shop', {}, { uid: uid });
        if (result.success) {
            showSuccess(result.message);
            loadShopList(currentPage);
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError(`删除失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`删除失败：${error.message} `);
    }
}

// 修改店铺（基于UID）
function openModifyShopModal(uid, browserId, shopName = '', shopAbbr = '', phone = '', password = '') {
    const modal = document.getElementById('modifyShopModal');
    if (!modal) return;

    // 记录当前要修改的店铺UID
    const uidInput = document.getElementById('modifyShopUid');
    if (uidInput) {
        uidInput.value = uid || '';
    }

    document.getElementById('modifyShopBrowserId').value = browserId;
    document.getElementById('modifyShopName').value = shopName;
    document.getElementById('modifyShopAbbr').value = shopAbbr;
    document.getElementById('modifyShopPhone').value = phone || '';
    document.getElementById('modifyShopPassword').value = password || '';

    // 使用 Semantic UI 的模态框 API
    if (typeof $ !== 'undefined' && $.fn.modal) {
        $('#modifyShopModal').modal('show');
    } else {
        modal.classList.add('active');
    }
}

function closeModifyShopModal() {
    const modal = document.getElementById('modifyShopModal');
    if (modal) {
        // 使用 Semantic UI 的模态框 API
        if (typeof $ !== 'undefined' && $.fn.modal) {
            $('#modifyShopModal').modal('hide');
        } else {
            modal.classList.remove('active');
        }
    }
}

async function submitModifyShop() {
    const uid = document.getElementById('modifyShopUid')?.value.trim();
    const browserId = document.getElementById('modifyShopBrowserId')?.value.trim();
    const shopName = document.getElementById('modifyShopName')?.value.trim() || '';
    const shopAbbr = document.getElementById('modifyShopAbbr')?.value.trim() || '';
    const phone = document.getElementById('modifyShopPhone')?.value.trim() || '';
    const password = document.getElementById('modifyShopPassword')?.value || '';

    if (!uid) {
        showError('店铺UID缺失，无法提交修改');
        return;
    }

    const submitBtn = document.querySelector('#modifyShopModal .actions .ui.primary.button');
    const originalText = submitBtn?.innerHTML;
    if (submitBtn) {
        submitBtn.innerHTML = '<i class="spinner loading icon"></i> 提交中...';
        submitBtn.classList.add('loading');
        submitBtn.disabled = true;
    }

    try {
        const result = await requestPost('/api/modify_shop', {}, {
            uid: uid,
            browser_id: browserId,
            shop_name: shopName,
            shop_abbr: shopAbbr,
            phone: phone,
            password: password
        });
        if (result.success) {
            showSuccess(result.message);
            closeModifyShopModal();
            loadShopList(currentPage);
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError(`修改失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`修改失败：${error.message} `);
    } finally {
        if (submitBtn) {
            submitBtn.innerHTML = originalText || '保存';
            submitBtn.classList.remove('loading');
            submitBtn.disabled = false;
        }
    }
}

// 添加新店铺：弹窗打开/关闭/提交
function openAddShopModalNew() {
    const modal = document.getElementById('addShopModal');
    if (!modal) return;
    const browserInput = document.getElementById('newShopBrowserId');
    const nameInput = document.getElementById('newShopName');
    const abbrInput = document.getElementById('newShopAbbr');
    const phoneInput = document.getElementById('newShopPhone');
    const passwordInput = document.getElementById('newShopPassword');
    if (browserInput) browserInput.value = '';
    if (nameInput) nameInput.value = '';
    if (abbrInput) abbrInput.value = '';
    if (phoneInput) phoneInput.value = '';
    if (passwordInput) passwordInput.value = '';
    // 使用 Semantic UI 的模态框 API
    if (typeof $ !== 'undefined' && $.fn.modal) {
        $('#addShopModal').modal('show');
    } else {
        modal.classList.add('active');
    }
}

function closeAddShopModal() {
    const modal = document.getElementById('addShopModal');
    if (modal) {
        // 使用 Semantic UI 的模态框 API
        if (typeof $ !== 'undefined' && $.fn.modal) {
            $('#addShopModal').modal('hide');
        } else {
            modal.classList.remove('active');
        }
    }
}

async function submitNewShop() {
    const browserInput = document.getElementById('newShopBrowserId');
    const nameInput = document.getElementById('newShopName');
    const abbrInput = document.getElementById('newShopAbbr');
    const phoneInput = document.getElementById('newShopPhone');
    const passwordInput = document.getElementById('newShopPassword');
    const submitBtn = document.querySelector('#addShopModal .actions .ui.primary.button');

    const browserId = browserInput?.value.trim() || '';

    const payload = {
        browser_id: browserId,
        shop_name: nameInput?.value.trim() || "",
        shop_abbr: abbrInput?.value.trim() || "",
        phone: phoneInput?.value.trim() || "",
        password: passwordInput?.value || ""
    };

    const originalText = submitBtn?.innerHTML;
    if (submitBtn) {
        submitBtn.innerHTML = '<i class="spinner loading icon"></i> 提交中...';
        submitBtn.classList.add('loading');
        submitBtn.disabled = true;
    }

    try {
        const result = await requestPost('/api/add_shop', {}, payload);
        if (result.success) {
            showSuccess(result.message);
            closeAddShopModal();
            loadShopList();
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError(`添加失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`添加失败：${error.message} `);
    } finally {
        if (submitBtn) {
            submitBtn.innerHTML = originalText || '添加';
            submitBtn.classList.remove('loading');
            submitBtn.disabled = false;
        }
    }
}

// 打开各类操作模态框
function openAddShopModal() {
    openConfirmModal('请选择新增店铺方式：').then(() => {
        const browserId = prompt('请输入browser_id（输入"all123"更新所有店铺）：');
        if (browserId?.trim()) addShop(browserId.trim());
    }).catch(err => console.log(err));
}

async function openUpdateShopModal() {
    try {
        await openConfirmModal('确认更新所有店铺信息吗？');
        await updateAllShops();
    } catch (error) {
        if (error.message !== "用户取消操作") showError("更新失败：" + error.message);
    }
}

// 旧的修改店铺ID函数（已废弃，使用openModifyShopModal替代）
function openModifyShopIdModal() {
    const shopAbbr = prompt('请输入要修改的店铺缩写：');
    if (shopAbbr?.trim()) {
        const newBrowserId = prompt(`请输入店铺 ${shopAbbr} 的新 browser_id：`);
        if (newBrowserId?.trim()) modifyShopBrowserId(shopAbbr.trim(), newBrowserId.trim());
    }
}

function openDeletePageModal() {
    const shopAbbr = prompt('请输入店铺缩写（输入"all123"删除所有店铺页码）：');
    if (shopAbbr?.trim()) deletePageRecord(shopAbbr.trim());
}

// 任务计数/列表加载（使用列表接口获取数量）
async function loadTaskCount() {
    try {
        // 使用列表接口获取任务数量，查询总数时始终传递 is_maintain_task=1
        const requestData = {
            is_main_task: 1,
            page: 1,
            page_size: 99
        };

        const result = await requestPost('/api/get_tasks', {}, requestData);
        if (result.success) {
            // 使用返回结果的 count 字段
            const taskCountElement = document.getElementById('taskCount');
            if (taskCountElement) {
                taskCountElement.textContent = result.count || 0;
            }
        }
    } catch (error) {
        // 加载任务计数失败，静默处理
        // 出错时显示0
        const taskCountElement = document.getElementById('taskCount');
        if (taskCountElement) {
            taskCountElement.textContent = 0;
        }
    }
}

// 更新店铺缩写下拉选项（使用缓存的店铺数据）- 重新实现，确保"全部"选项始终存在
// 使用全局标志位防止 onChange 死循环
let isUpdatingShopAbbr = false;

function updateShopAbbrDropdown() {
    const select = document.getElementById('filterShopAbbr');
    if (!select) {
        return;
    }

    // 保存当前选中的值
    const currentValue = select.value || '';

    // 设置标志位，防止在更新过程中触发 onChange
    isUpdatingShopAbbr = true;

    // 如果已经初始化过 Semantic UI，先销毁
    if (typeof $ !== 'undefined' && $.fn) {
        const $filterShopAbbr = $('#filterShopAbbr');
        if ($filterShopAbbr.hasClass('ui dropdown')) {
            $filterShopAbbr.dropdown('destroy');
        }
    }

    // 收集所有店铺缩写（去重）
    const shopAbbrs = new Set();
    if (cachedShopList && cachedShopList.length > 0) {
        cachedShopList.forEach((shop) => {
            const abbr = shop['店铺缩写'] || shop.shop_abbr || shop.abbr || '';
            if (abbr && abbr.trim()) {
                shopAbbrs.add(abbr.trim());
            }
        });
    }

    // 先保存"全部"选项（如果存在）
    let allOptionExists = false;
    const existingAllOption = Array.from(select.options).find(opt => opt.value === '' && opt.textContent.trim() === '全部');

    // 清空所有选项（除了"全部"选项）
    // 方法：保留"全部"选项，删除其他选项
    if (existingAllOption) {
        allOptionExists = true;
        // 清空所有非"全部"选项
        Array.from(select.options).forEach(opt => {
            if (opt.value !== '' || opt.textContent.trim() !== '全部') {
                opt.remove();
            }
        });
    } else {
        // 如果没有"全部"选项，清空所有选项后添加
        select.innerHTML = '';
    }

    // 如果"全部"选项不存在，先添加它
    if (!allOptionExists) {
        const allOption = document.createElement('option');
        allOption.value = '';
        allOption.textContent = '全部';
        select.appendChild(allOption);
    }

    // 添加店铺缩写选项（按字母顺序排序）
    const sortedAbbrs = Array.from(shopAbbrs).sort();
    sortedAbbrs.forEach(abbr => {
        const option = document.createElement('option');
        option.value = abbr;
        option.textContent = abbr;
        select.appendChild(option);
    });

    // 恢复之前选中的值（如果还存在）
    if (currentValue && Array.from(select.options).some(opt => opt.value === currentValue)) {
        select.value = currentValue;
    } else {
        select.value = '';
    }

    // 重新初始化 Semantic UI 下拉框
    if (typeof $ !== 'undefined' && $.fn) {
        const $filterShopAbbr = $('#filterShopAbbr');

        // 再次确保"全部"选项存在
        if (!Array.from(select.options).some(opt => opt.value === '' && opt.textContent.trim() === '全部')) {
            const allOption = document.createElement('option');
            allOption.value = '';
            allOption.textContent = '全部';
            select.insertBefore(allOption, select.firstChild);
        }

        // 保存当前下拉框的值，用于判断是否真正改变
        let lastShopAbbrValue = select.value || '';

        // 初始化 Semantic UI dropdown
        $filterShopAbbr.dropdown({
            clearable: false, // 不使用 clearable，因为我们已经有了"全部"选项
            placeholder: '全部',
            forceSelection: false,
            selectOnKeydown: false,
            showOnFocus: true,
            fullTextSearch: false,
            allowReselection: true,
            onChange: function (value) {
                // 防止在更新过程中触发 onChange（避免死循环）
                if (isUpdatingShopAbbr) {
                    // 跳过 onChange 事件，防止死循环
                    return;
                }

                // 防止重复触发（值没有真正改变）
                const currentValue = value || '';
                if (currentValue === lastShopAbbrValue) {
                    console.log('店铺缩写值未改变，跳过 onChange 事件');
                    return;
                }

                console.log('店铺缩写下拉值变化:', value, '从', lastShopAbbrValue, '到', currentValue);
                lastShopAbbrValue = currentValue;

                // 如果选择了"全部"或空值，确保值为空字符串并清空显示
                if (!value || value === '' || value === '全部') {
                    const nativeSelect = document.getElementById('filterShopAbbr');
                    if (nativeSelect && nativeSelect.value !== '') {
                        nativeSelect.value = '';
                        lastShopAbbrValue = '';
                        $filterShopAbbr.dropdown('clear');
                    }
                }

                // 不自动触发刷新，只有点击搜索按钮时才刷新
                // if (typeof loadTasks === 'function') {
                //     clearTimeout(window.shopAbbrLoadTasksTimer);
                //     window.shopAbbrLoadTasksTimer = setTimeout(function() {
                //         loadTasks();
                //     }, 300);
                // }
            },
            onShow: function () {
                const $menu = $(this).next('.menu');
                if ($menu.length) {
                    let $allItem = $menu.find('.item[data-value=""]');
                    if ($allItem.length === 0) {
                        $allItem = $('<div class="item" data-value="">全部</div>');
                        $menu.prepend($allItem);
                    }
                    $allItem.removeClass('filtered hidden disabled').show().css({
                        'display': '',
                        'visibility': 'visible',
                        'opacity': '1'
                    });
                    $allItem.off('click.ensureAll').on('click.ensureAll', function (e) {
                        e.stopPropagation();
                        $filterShopAbbr.dropdown('clear');
                        $filterShopAbbr.dropdown('set value', '');
                        $filterShopAbbr.dropdown('hide');
                    });
                }
            }
        });

        // 刷新 dropdown 以确保选项同步
        setTimeout(function () {
            try {
                // 恢复之前选中的值到 Semantic UI dropdown
                if (currentValue && Array.from(select.options).some(opt => opt.value === currentValue)) {
                    $filterShopAbbr.dropdown('set value', currentValue);
                } else {
                    $filterShopAbbr.dropdown('set value', '');
                }

                $filterShopAbbr.dropdown('refresh');
                // 验证"全部"选项是否在菜单中
                const $menu = $filterShopAbbr.next('.menu');
                if ($menu.length) {
                    const $allItem = $menu.find('.item[data-value=""]');
                    if ($allItem.length === 0) {
                        console.warn('Semantic UI 菜单中缺少"全部"选项，尝试添加');
                        // 如果菜单中没有，强制添加
                        const allItem = $('<div class="item active" data-value="">全部</div>');
                        $menu.prepend(allItem);
                        // 绑定点击事件
                        allItem.off('click.ensureAll').on('click.ensureAll', function (e) {
                            e.stopPropagation();
                            $filterShopAbbr.dropdown('clear');
                            $filterShopAbbr.dropdown('set value', '');
                            $filterShopAbbr.dropdown('hide');
                        });
                    } else {
                        console.log('"全部"选项已存在于 Semantic UI 菜单中');
                    }
                }
            } catch (e) {
                console.error('刷新dropdown失败:', e);
            } finally {
                // 更新完成后，清除标志位
                isUpdatingShopAbbr = false;
            }
        }, 100);
    } else {
        // 如果没有 jQuery，也要清除标志位
        isUpdatingShopAbbr = false;
    }
}

// 加载店铺缩写下拉选项（从任务列表的 task_group 中提取前缀）
async function loadShopAbbrOptions() {
    // 确保下拉框元素存在
    const select = document.getElementById('filterShopAbbr');
    if (!select) {
        return;
    }

    try {
        // 调用任务列表接口获取所有任务（不分页，获取全部以提取店铺缩写）
        const result = await requestPost('/api/get_tasks', {}, {
            page: 1,
            page_size: 1000,
            is_main_task: 1
        });

        console.log('任务列表接口返回结果:', result);

        if (!result || !result.success) {
            console.error('接口调用失败:', result?.error_msg || result?.message);
            return;
        }

        // 从 task_group 中提取店铺缩写前缀（下划线前面的部分）
        const shopAbbrs = new Set();
        if (result.tasks && Array.isArray(result.tasks)) {
            result.tasks.forEach((task) => {
                const taskGroup = task.task_group || '';
                if (taskGroup && taskGroup.includes('_')) {
                    // 提取下划线前面的部分作为店铺缩写
                    const abbr = taskGroup.split('_')[0];
                    if (abbr && abbr.trim()) {
                        shopAbbrs.add(abbr.trim());
                    }
                }
            });
        }

        console.log('从 task_group 提取的店铺缩写:', Array.from(shopAbbrs));

        // 更新下拉框选项
        updateShopAbbrDropdownFromSet(shopAbbrs);

    } catch (error) {
        console.error('加载店铺列表异常:', error);
        console.error('错误堆栈:', error.stack);
    }
}

// 从 Set 集合更新店铺缩写下拉选项
function updateShopAbbrDropdownFromSet(shopAbbrs) {
    const select = document.getElementById('filterShopAbbr');
    if (!select) {
        return;
    }

    // 保存当前选中的值
    const currentValue = select.value || '';

    // 设置标志位，防止在更新过程中触发 onChange
    isUpdatingShopAbbr = true;

    // 如果已经初始化过 Semantic UI，先销毁
    if (typeof $ !== 'undefined' && $.fn) {
        const $filterShopAbbr = $('#filterShopAbbr');
        if ($filterShopAbbr.hasClass('ui dropdown')) {
            $filterShopAbbr.dropdown('destroy');
        }
    }

    // 清空所有选项
    select.innerHTML = '';

    // 添加"全部"选项
    const allOption = document.createElement('option');
    allOption.value = '';
    allOption.textContent = '全部';
    select.appendChild(allOption);

    // 添加店铺缩写选项（按字母顺序排序）
    const sortedAbbrs = Array.from(shopAbbrs).sort();
    sortedAbbrs.forEach(abbr => {
        const option = document.createElement('option');
        option.value = abbr;
        option.textContent = abbr;
        select.appendChild(option);
    });

    // 恢复之前选中的值（如果还存在）
    if (currentValue && Array.from(select.options).some(opt => opt.value === currentValue)) {
        select.value = currentValue;
    } else {
        select.value = '';
    }

    // 重新初始化 Semantic UI 下拉框
    if (typeof $ !== 'undefined' && $.fn) {
        const $filterShopAbbr = $('#filterShopAbbr');

        $filterShopAbbr.dropdown({
            placeholder: '全部',
            forceSelection: false,
            selectOnKeydown: false,
            showOnFocus: true,
            fullTextSearch: false,
            allowReselection: true,
            onChange: function (value) {
                // 防止重复触发（值没有真正改变）
                const currentValue = value || '';
                if (currentValue === lastShopAbbrValue) {
                    console.log('店铺缩写值未改变，跳过 onChange 事件');
                    return;
                }

                console.log('店铺缩写下拉值变化:', value, '从', lastShopAbbrValue, '到', currentValue);
                lastShopAbbrValue = currentValue;

                // 如果选择了"全部"或空值，确保值为空字符串并清空显示
                if (!value || value === '' || value === '全部') {
                    const nativeSelect = document.getElementById('filterShopAbbr');
                    if (nativeSelect) {
                        nativeSelect.value = '';
                    }
                    $filterShopAbbr.dropdown('set value', '');
                    $filterShopAbbr.dropdown('clear');
                }

                // 不自动触发刷新，只有点击搜索按钮时才刷新
            },
            onShow: function () {
                const $menu = $(this).next('.menu');
                if ($menu.length) {
                    let $allItem = $menu.find('.item[data-value=""]');
                    if ($allItem.length === 0) {
                        $allItem = $('<div class="item" data-value="">全部</div>');
                        $menu.prepend($allItem);
                    }
                    $allItem.removeClass('filtered hidden disabled').show().css({
                        'display': '',
                        'visibility': 'visible',
                        'opacity': '1'
                    });
                    $allItem.off('click.ensureAll').on('click.ensureAll', function (e) {
                        e.stopPropagation();
                        $filterShopAbbr.dropdown('clear');
                        $filterShopAbbr.dropdown('set value', '');
                        $filterShopAbbr.dropdown('hide');
                    });
                }
            }
        });

        // 确保 dropdown 显示正确的文本
        setTimeout(() => {
            const nativeSelect = document.getElementById('filterShopAbbr');
            if (nativeSelect) {
                const currentValue = nativeSelect.value;
                if (!currentValue || currentValue === '' || currentValue === '全部') {
                    $filterShopAbbr.dropdown('clear');
                } else {
                    $filterShopAbbr.dropdown('set text', currentValue);
                    $filterShopAbbr.dropdown('set value', currentValue);
                }
            }
            isUpdatingShopAbbr = false;
        }, 100);
    } else {
        isUpdatingShopAbbr = false;
    }
}

// 转义HTML
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// 初始化任务筛选下拉框，确保"全部"选项正确显示
function initializeTaskFilterDropdowns() {
    if (typeof $ === 'undefined' || !$.fn) {
        return;
    }

    // 初始化任务状态下拉框
    const $filterTaskStatus = $('#filterTaskStatus');
    if ($filterTaskStatus.length) {
        if ($filterTaskStatus.hasClass('ui dropdown')) {
            $filterTaskStatus.dropdown('destroy');
        }
        // 确保"全部"选项存在
        const statusSelect = document.getElementById('filterTaskStatus');
        if (statusSelect) {
            const hasAllOption = Array.from(statusSelect.options).some(opt => opt.value === '' && opt.textContent.trim() === '全部');
            if (!hasAllOption) {
                const allOption = document.createElement('option');
                allOption.value = '';
                allOption.textContent = '全部';
                statusSelect.insertBefore(allOption, statusSelect.firstChild);
            }
        }
        // 初始化dropdown，使用onAdd回调确保空值选项被保留
        $filterTaskStatus.dropdown({
            placeholder: '全部',
            forceSelection: false,
            selectOnKeydown: false,
            showOnFocus: true,
            fullTextSearch: false,
            allowReselection: true,
            onChange: function (value) {
                // 如果选择了"全部"或空值，确保值为空字符串并清空显示
                if (!value || value === '' || value === '全部') {
                    $(this).dropdown('set value', '');
                    $(this).dropdown('clear');
                    // 触发loadTasks重新加载
                    if (typeof loadTasks === 'function') {
                        loadTasks();
                    }
                }
            },
            onShow: function () {
                // 强制添加"全部"选项到菜单中
                const $menu = $(this).next('.menu');
                if ($menu.length) {
                    let $allItem = $menu.find('.item[data-value=""]');
                    if ($allItem.length === 0) {
                        // 创建"全部"选项并放在最前面
                        $allItem = $('<div class="item" data-value="">全部</div>');
                        $menu.prepend($allItem);
                    }
                    // 确保可见并绑定点击事件
                    $allItem.removeClass('filtered hidden disabled').show().css({
                        'display': '',
                        'visibility': 'visible',
                        'opacity': '1'
                    });
                    // 绑定点击事件（每次显示时重新绑定，避免重复绑定）
                    $allItem.off('click.ensureAll').on('click.ensureAll', function (e) {
                        e.stopPropagation();
                        $filterTaskStatus.dropdown('clear');
                        $filterTaskStatus.dropdown('set value', '');
                        $filterTaskStatus.dropdown('hide');
                        if (typeof loadTasks === 'function') {
                            loadTasks();
                        }
                    });
                }
            }
        });

        // 在dropdown初始化完成后，强制添加"全部"选项（多次尝试确保添加成功）
        const ensureAllOption = function () {
            const $menu = $filterTaskStatus.next('.menu');
            if ($menu.length) {
                let $allItem = $menu.find('.item[data-value=""]');
                if ($allItem.length === 0) {
                    $allItem = $('<div class="item" data-value="">全部</div>');
                    $menu.prepend($allItem);
                }
                $allItem.removeClass('filtered hidden disabled').show().css({
                    'display': '',
                    'visibility': 'visible',
                    'opacity': '1'
                });
                $allItem.off('click.ensureAll').on('click.ensureAll', function (e) {
                    e.stopPropagation();
                    $filterTaskStatus.dropdown('clear');
                    $filterTaskStatus.dropdown('set value', '');
                    $filterTaskStatus.dropdown('hide');
                    if (typeof loadTasks === 'function') {
                        loadTasks();
                    }
                });
            }
        };
        // 多次尝试，确保菜单创建后能添加"全部"选项
        setTimeout(ensureAllOption, 100);
        setTimeout(ensureAllOption, 300);
        setTimeout(ensureAllOption, 500);
    }

    // 初始化任务类型下拉框
    const $filterTaskType = $('#filterTaskType');
    if ($filterTaskType.length) {
        if ($filterTaskType.hasClass('ui dropdown')) {
            $filterTaskType.dropdown('destroy');
        }
        // 确保"全部"选项存在
        const typeSelect = document.getElementById('filterTaskType');
        if (typeSelect) {
            const hasAllOption = Array.from(typeSelect.options).some(opt => opt.value === '' && opt.textContent.trim() === '全部');
            if (!hasAllOption) {
                const allOption = document.createElement('option');
                allOption.value = '';
                allOption.textContent = '全部';
                typeSelect.insertBefore(allOption, typeSelect.firstChild);
            }
        }
        // 先初始化dropdown
        $filterTaskType.dropdown({
            placeholder: '全部',
            forceSelection: false,
            selectOnKeydown: false,
            showOnFocus: true,
            fullTextSearch: false,
            allowReselection: true,
            onChange: function (value) {
                // 如果选择了"全部"或空值，确保值为空字符串并清空显示
                if (!value || value === '' || value === '全部') {
                    $(this).dropdown('set value', '');
                    $(this).dropdown('clear');
                    // 触发loadTasks重新加载
                    if (typeof loadTasks === 'function') {
                        loadTasks();
                    }
                }
            },
            onShow: function () {
                // 强制添加"全部"选项到菜单中
                const $menu = $(this).next('.menu');
                if ($menu.length) {
                    let $allItem = $menu.find('.item[data-value=""]');
                    if ($allItem.length === 0) {
                        // 创建"全部"选项并放在最前面
                        $allItem = $('<div class="item" data-value="">全部</div>');
                        $menu.prepend($allItem);
                    }
                    // 确保可见并绑定点击事件
                    $allItem.removeClass('filtered hidden disabled').show().css({
                        'display': '',
                        'visibility': 'visible'
                    });
                    // 绑定点击事件（每次显示时重新绑定，避免重复绑定）
                    $allItem.off('click.ensureAll').on('click.ensureAll', function (e) {
                        e.stopPropagation();
                        $filterTaskType.dropdown('clear');
                        $filterTaskType.dropdown('set value', '');
                        $filterTaskType.dropdown('hide');
                        if (typeof loadTasks === 'function') {
                            loadTasks();
                        }
                    });
                }
            }
        });

        // 在dropdown初始化完成后，强制添加"全部"选项（多次尝试确保添加成功）
        const ensureAllOptionType = function () {
            const $menu = $filterTaskType.next('.menu');
            if ($menu.length) {
                let $allItem = $menu.find('.item[data-value=""]');
                if ($allItem.length === 0) {
                    $allItem = $('<div class="item" data-value="">全部</div>');
                    $menu.prepend($allItem);
                }
                $allItem.removeClass('filtered hidden disabled').show().css({
                    'display': '',
                    'visibility': 'visible',
                    'opacity': '1'
                });
                $allItem.off('click.ensureAll').on('click.ensureAll', function (e) {
                    e.stopPropagation();
                    $filterTaskType.dropdown('clear');
                    $filterTaskType.dropdown('set value', '');
                    $filterTaskType.dropdown('hide');
                    if (typeof loadTasks === 'function') {
                        loadTasks();
                    }
                });
            }
        };
        // 多次尝试，确保菜单创建后能添加"全部"选项
        setTimeout(ensureAllOptionType, 100);
        setTimeout(ensureAllOptionType, 300);
        setTimeout(ensureAllOptionType, 500);
    }

    // 店铺缩写下拉框：只确保"全部"选项存在，具体初始化由 updateShopAbbrDropdown 处理
    const selectShopAbbr = document.getElementById('filterShopAbbr');
    if (selectShopAbbr) {
        // 确保"全部"选项存在于原生 select 中
        if (!Array.from(selectShopAbbr.options).some(opt => opt.value === '' && opt.textContent.trim() === '全部')) {
            const allOption = document.createElement('option');
            allOption.value = '';
            allOption.textContent = '全部';
            selectShopAbbr.insertBefore(allOption, selectShopAbbr.firstChild);
        }
        // 店铺下拉框的完整初始化由 updateShopAbbrDropdown() 统一处理
        // 这里不做 Semantic UI 初始化，避免与 updateShopAbbrDropdown 冲突
    }

    // 初始化守护任务下拉框
    if (typeof $ !== 'undefined' && $.fn) {
        const $filterMaintainTask = $('#filterMaintainTask');
        if ($filterMaintainTask.length) {
            if ($filterMaintainTask.hasClass('ui dropdown')) {
                $filterMaintainTask.dropdown('destroy');
            }
            // 确保"全部"选项存在
            const maintainSelect = document.getElementById('filterMaintainTask');
            if (maintainSelect) {
                const hasAllOption = Array.from(maintainSelect.options).some(opt => opt.value === '' && opt.textContent.trim() === '全部');
                if (!hasAllOption) {
                    const allOption = document.createElement('option');
                    allOption.value = '';
                    allOption.textContent = '全部';
                    maintainSelect.insertBefore(allOption, maintainSelect.firstChild);
                }
            }
            // 初始化dropdown
            $filterMaintainTask.dropdown({
                placeholder: '全部',
                forceSelection: false,
                selectOnKeydown: false,
                showOnFocus: true,
                fullTextSearch: false,
                allowReselection: true,
                onChange: function (value) {
                    if (!value || value === '' || value === '全部') {
                        $(this).dropdown('set value', '');
                        $(this).dropdown('clear');
                        if (typeof loadTasks === 'function') {
                            loadTasks();
                        }
                    }
                },
                onShow: function () {
                    const $menu = $(this).next('.menu');
                    if ($menu.length) {
                        let $allItem = $menu.find('.item[data-value=""]');
                        if ($allItem.length === 0) {
                            $allItem = $('<div class="item" data-value="">全部</div>');
                            $menu.prepend($allItem);
                        }
                        $allItem.removeClass('filtered hidden disabled').show().css({
                            'display': '',
                            'visibility': 'visible',
                            'opacity': '1'
                        });
                        $allItem.off('click.ensureAll').on('click.ensureAll', function (e) {
                            e.stopPropagation();
                            $filterMaintainTask.dropdown('clear');
                            $filterMaintainTask.dropdown('set value', '');
                            $filterMaintainTask.dropdown('hide');
                            if (typeof loadTasks === 'function') {
                                loadTasks();
                            }
                        });
                    }
                }
            });

            const ensureAllOptionMaintain = function () {
                const $menu = $filterMaintainTask.next('.menu');
                if ($menu.length) {
                    let $allItem = $menu.find('.item[data-value=""]');
                    if ($allItem.length === 0) {
                        $allItem = $('<div class="item" data-value="">全部</div>');
                        $menu.prepend($allItem);
                    }
                    $allItem.removeClass('filtered hidden disabled').show().css({
                        'display': '',
                        'visibility': 'visible',
                        'opacity': '1'
                    });
                    $allItem.off('click.ensureAll').on('click.ensureAll', function (e) {
                        e.stopPropagation();
                        $filterMaintainTask.dropdown('clear');
                        $filterMaintainTask.dropdown('set value', '');
                        $filterMaintainTask.dropdown('hide');
                        if (typeof loadTasks === 'function') {
                            loadTasks();
                        }
                    });
                }
            };
            setTimeout(ensureAllOptionMaintain, 100);
            setTimeout(ensureAllOptionMaintain, 300);
            setTimeout(ensureAllOptionMaintain, 500);
        }
    }

    // 初始化定时任务下拉框
    if (typeof $ !== 'undefined' && $.fn) {
        const $filterScheduledTask = $('#filterScheduledTask');
        if ($filterScheduledTask.length) {
            if ($filterScheduledTask.hasClass('ui dropdown')) {
                $filterScheduledTask.dropdown('destroy');
            }
            // 确保"全部"选项存在
            const scheduledSelect = document.getElementById('filterScheduledTask');
            if (scheduledSelect) {
                const hasAllOption = Array.from(scheduledSelect.options).some(opt => opt.value === '' && opt.textContent.trim() === '全部');
                if (!hasAllOption) {
                    const allOption = document.createElement('option');
                    allOption.value = '';
                    allOption.textContent = '全部';
                    scheduledSelect.insertBefore(allOption, scheduledSelect.firstChild);
                }
            }
            // 初始化dropdown
            $filterScheduledTask.dropdown({
                placeholder: '全部',
                forceSelection: false,
                selectOnKeydown: false,
                showOnFocus: true,
                fullTextSearch: false,
                allowReselection: true,
                onChange: function (value) {
                    if (!value || value === '' || value === '全部') {
                        $(this).dropdown('set value', '');
                        $(this).dropdown('clear');
                        if (typeof loadTasks === 'function') {
                            loadTasks();
                        }
                    }
                },
                onShow: function () {
                    const $menu = $(this).next('.menu');
                    if ($menu.length) {
                        let $allItem = $menu.find('.item[data-value=""]');
                        if ($allItem.length === 0) {
                            $allItem = $('<div class="item" data-value="">全部</div>');
                            $menu.prepend($allItem);
                        }
                        $allItem.removeClass('filtered hidden disabled').show().css({
                            'display': '',
                            'visibility': 'visible',
                            'opacity': '1'
                        });
                        $allItem.off('click.ensureAll').on('click.ensureAll', function (e) {
                            e.stopPropagation();
                            $filterScheduledTask.dropdown('clear');
                            $filterScheduledTask.dropdown('set value', '');
                            $filterScheduledTask.dropdown('hide');
                            if (typeof loadTasks === 'function') {
                                loadTasks();
                            }
                        });
                    }
                }
            });

            const ensureAllOptionScheduled = function () {
                const $menu = $filterScheduledTask.next('.menu');
                if ($menu.length) {
                    let $allItem = $menu.find('.item[data-value=""]');
                    if ($allItem.length === 0) {
                        $allItem = $('<div class="item" data-value="">全部</div>');
                        $menu.prepend($allItem);
                    }
                    $allItem.removeClass('filtered hidden disabled').show().css({
                        'display': '',
                        'visibility': 'visible',
                        'opacity': '1'
                    });
                    $allItem.off('click.ensureAll').on('click.ensureAll', function (e) {
                        e.stopPropagation();
                        $filterScheduledTask.dropdown('clear');
                        $filterScheduledTask.dropdown('set value', '');
                        $filterScheduledTask.dropdown('hide');
                        if (typeof loadTasks === 'function') {
                            loadTasks();
                        }
                    });
                }
            };
            setTimeout(ensureAllOptionScheduled, 100);
            setTimeout(ensureAllOptionScheduled, 300);
            setTimeout(ensureAllOptionScheduled, 500);
        }
    }
}

// 搜索任务（重置到第一页）
function searchTasks() {
    currentTaskPage = 1;
    loadTasks();
}

// 重置任务筛选条件
function resetTaskFilters() {
    // 重置任务状态
    if (typeof $ !== 'undefined' && $.fn) {
        $('#filterTaskStatus').dropdown('set value', '');
    } else {
        document.getElementById('filterTaskStatus').value = '';
    }

    // 重置任务ID
    document.getElementById('filterTaskId').value = '';

    // 重置任务类型
    if (typeof $ !== 'undefined' && $.fn) {
        $('#filterTaskType').dropdown('set value', '');
    } else {
        document.getElementById('filterTaskType').value = '';
    }

    // 重置店铺缩写
    const shopAbbrSelect = document.getElementById('filterShopAbbr');
    if (shopAbbrSelect) {
        shopAbbrSelect.value = '';
        // 如果使用了 Semantic UI 下拉框，同步更新
        if (typeof $ !== 'undefined' && $.fn) {
            $('#filterShopAbbr').dropdown('set value', '');
        }
    }

    // 重置守护任务筛选
    if (typeof $ !== 'undefined' && $.fn) {
        $('#filterMaintainTask').dropdown('set value', '');
    } else {
        const maintainTaskSelect = document.getElementById('filterMaintainTask');
        if (maintainTaskSelect) {
            maintainTaskSelect.value = '';
        }
    }

    // 重置定时任务筛选
    if (typeof $ !== 'undefined' && $.fn) {
        $('#filterScheduledTask').dropdown('set value', '');
    } else {
        const scheduledTaskSelect = document.getElementById('filterScheduledTask');
        if (scheduledTaskSelect) {
            scheduledTaskSelect.value = '';
        }
    }

    // 重置搜索全部任务复选框
    const searchAllTasksCheckbox = document.getElementById('searchAllTasks');
    if (searchAllTasksCheckbox) {
        searchAllTasksCheckbox.checked = false;
        if (typeof $ !== 'undefined' && $.fn) {
            $('#searchAllTasksCheckbox').checkbox('set unchecked');
        }
    }

    // 重置到第一页
    currentTaskPage = 1;
    loadTasks();
}

// 更新任务列表分页控件
function updateTaskPaginationControls() {
    const pagination = document.getElementById('taskPagination');
    if (!pagination) {
        console.warn('taskPagination 元素不存在，尝试查找...');
        // 延迟重试
        setTimeout(() => {
            const retryPagination = document.getElementById('taskPagination');
            if (retryPagination) {
                updateTaskPaginationControls();
            } else {
                console.error('taskPagination 元素仍然不存在');
            }
        }, 100);
        return;
    }

    // 确保容器有分页样式类
    pagination.classList.add('pagination');

    const page = currentTaskPage || 1;
    const totalPages = totalTaskPages || 1;

    console.log('更新分页控件，当前页:', page, '总页数:', totalPages);

    // 如果只有1页，显示当前页信息但不显示分页按钮
    if (totalPages <= 1) {
        pagination.innerHTML = `<div style="text-align: center; color: #666; padding: 15px; background: #f5f5f5; border-radius: 4px; border: 1px solid #e0e0e0;">共 1 页，当前第 1 页</div>`;
        return;
    }

    let html = `<div class="pagination" style="display: flex; gap: 0.5rem; justify-content: center; align-items: center; flex-wrap: wrap; padding: 15px; background: #f9f9f9; border-radius: 4px; border: 1px solid #e0e0e0;">`;

    const hasPrev = page > 1;
    const hasNext = page < totalPages;

    html += `<button class="page-btn" onclick="loadTasksPage(${page - 1})" ${!hasPrev ? 'disabled' : ''} style="min-width: 80px; padding: 8px 16px; border: 1px solid #ddd; border-radius: 4px; background: #fff; cursor: pointer; transition: all 0.3s ease; font-size: 14px;">上一页</button>`;

    for (let i = 1; i <= totalPages; i++) {
        if (i === page) {
            html += `<button class="page-btn active" style="min-width: 40px; padding: 8px 12px; border: 1px solid #1890ff; border-radius: 4px; background: #1890ff; color: #fff; font-weight: 500; cursor: default; font-size: 14px;">${i}</button>`;
        } else if (i === 1 || i === totalPages || Math.abs(i - page) <= 2) {
            html += `<button class="page-btn" onclick="loadTasksPage(${i})" style="min-width: 40px; padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; background: #fff; cursor: pointer; transition: all 0.3s ease; font-size: 14px;">${i}</button>`;
        } else if (Math.abs(i - page) === 3) {
            html += `<span style="padding: 0 8px; color: #666; font-size: 14px;">...</span>`;
        }
    }

    html += `<button class="page-btn" onclick="loadTasksPage(${page + 1})" ${!hasNext ? 'disabled' : ''} style="min-width: 80px; padding: 8px 16px; border: 1px solid #ddd; border-radius: 4px; background: #fff; cursor: pointer; transition: all 0.3s ease; font-size: 14px;">下一页</button>`;

    // 显示分页信息，移到右侧
    html += `<div style="margin-left: 15px; color: #666; font-size: 14px; font-weight: 500;">共 ${totalPages} 页，当前第 ${page} 页</div>`;

    html += `</div>`;

    pagination.innerHTML = html;
}

// 加载指定页的任务列表
function loadTasksPage(page) {
    if (page < 1) page = 1;
    if (page > totalTaskPages) page = totalTaskPages;
    currentTaskPage = page;
    loadTasks();
}

async function loadTasks(page) {
    // 如果传入了页码参数，使用该页码，否则使用当前页码
    if (page !== undefined && page !== null) {
        currentTaskPage = page;
    }

    const container = document.getElementById('tasksContainer');
    if (!container) {
        console.warn('loadTasks: tasksContainer 元素不存在');
        return;
    }

    console.log('loadTasks: 开始加载任务列表，页码:', currentTaskPage);
    container.innerHTML = '<div class="ui active centered inline loader"></div><p style="text-align: center; margin-top: 10px;">正在加载任务列表...</p>';

    try {
        // 获取筛选条件（使用jQuery获取Semantic UI下拉框的值）
        let taskStatus = '';
        if (typeof $ !== 'undefined') {
            taskStatus = $('#filterTaskStatus').dropdown('get value') || '';
        } else {
            taskStatus = document.getElementById('filterTaskStatus')?.value || '';
        }

        let taskType = '';
        if (typeof $ !== 'undefined') {
            taskType = $('#filterTaskType').dropdown('get value') || '';
        } else {
            taskType = document.getElementById('filterTaskType')?.value || '';
        }
        let shopAbbr = '';

        // 获取店铺缩写（从下拉框）
        const shopAbbrSelect = document.getElementById('filterShopAbbr');
        if (shopAbbrSelect) {
            shopAbbr = shopAbbrSelect.value || '';
            console.log('从select获取店铺缩写:', shopAbbr);
        }

        // 获取守护任务筛选条件
        let maintainTask = '';
        if (typeof $ !== 'undefined') {
            maintainTask = $('#filterMaintainTask').dropdown('get value') || '';
        } else {
            maintainTask = document.getElementById('filterMaintainTask')?.value || '';
        }

        // 获取定时任务筛选条件
        let scheduledTask = '';
        if (typeof $ !== 'undefined') {
            scheduledTask = $('#filterScheduledTask').dropdown('get value') || '';
        } else {
            scheduledTask = document.getElementById('filterScheduledTask')?.value || '';
        }

        // 获取搜索全部任务复选框状态
        const searchAllTasksCheckbox = document.getElementById('searchAllTasks');
        const searchAllTasks = searchAllTasksCheckbox ? searchAllTasksCheckbox.checked : false;

        // 构建请求参数
        const requestData = {};
        if (taskStatus) requestData.task_status = taskStatus;
        // 注意：后端接口目前只支持 task_status 和 task_id，店铺缩写和任务类型需要在后端扩展支持
        // 这里先保存到requestData，如果后端不支持则前端过滤
        if (taskType) requestData.task_type = taskType;
        if (shopAbbr) requestData.shop_abbr = shopAbbr;
        if (maintainTask !== '') requestData.is_maintain_task = maintainTask;
        if (scheduledTask !== '') requestData.has_scheduled_task = scheduledTask;
        // 勾选"搜索全部任务"时不传 is_main_task，不勾选时传入 is_main_task=1
        if (!searchAllTasks) {
            requestData.is_main_task = 1;
        }

        // 添加分页参数（任务管理列表：每页 10 条）
        const TASK_PAGE_SIZE = 10;
        requestData.page = currentTaskPage || 1;
        requestData.page_size = TASK_PAGE_SIZE;
        
        // 添加排序参数：按更新时间降序排列（越新的任务越靠前）
        requestData.sort_field = 'update_time';
        requestData.sort_order = 'DESC';

        // 调用接口
        const result = await requestPost('/api/get_tasks', {}, requestData);

        if (result.success) {
            // 缓存后端返回的所有任务ID列表（用于“一键清空所有任务”按钮）
            try {
                window.__allTaskIdListCache = normalizeAllTaskIdList(result.all_task_id_list);
            } catch (e) {
                console.warn('解析 all_task_id_list 失败:', e);
                window.__allTaskIdListCache = [];
            }

            // 更新分页信息
            const pageSize = TASK_PAGE_SIZE;
            if (result.total !== undefined && result.total !== null) {
                totalTaskPages = Math.ceil(result.total / pageSize) || 1;
                console.log('任务总数:', result.total, '总页数:', totalTaskPages, '当前页:', currentTaskPage);
            } else if (result.count !== undefined) {
                // 如果没有total字段，但有count字段，如果当前页数据满了，可能还有下一页
                const currentCount = result.count || 0;
                if (currentCount >= pageSize) {
                    // 当前页数据满了，可能还有更多页
                    totalTaskPages = (currentTaskPage || 1) + 1;
                } else {
                    // 当前页数据不满，说明这是最后一页
                    totalTaskPages = currentTaskPage || 1;
                }
                console.warn('接口未返回total字段，使用估算值，当前页数据量:', currentCount);
            } else {
                // 都没有，默认1页
                totalTaskPages = 1;
            }

            if (result.tasks && result.tasks.length > 0) {
                let tasks = result.tasks;

                // 注意：任务类型和店铺缩写筛选已交由后端处理，前端不再进行二次过滤
                // 后端使用 task_name = ? 匹配任务类型，使用 task_group LIKE 'AE_%' 匹配店铺前缀

                if (tasks.length === 0) {
                    container.innerHTML = '<p style="text-align: center; color: #999;">没有符合条件的任务</p>';
                    // 清空分页
                    const pagination = document.getElementById('taskPagination');
                    if (pagination) {
                        pagination.innerHTML = '';
                    }
                    return;
                }

                // 生成任务列表HTML
                let html = `
    <div class="task-list-table">
                    <div class="task-list-header">
                        <div class="task-col checkbox">
                            <span id="selectAllTasks" class="basketball-select" title="全选/取消全选" onclick="toggleSelectAllTasks(this)">🏀</span>
                        </div>
                        <div class="task-col id">ID</div>
                        <div class="task-col type">任务名称</div>
                        <div class="task-col status">状态</div>
                        <div class="task-col msg">信息</div>
                        <div class="task-col remarks">备注</div>
                        <div class="task-col time">更新时间</div>
                        <div class="task-col create-time">创建时间</div>
                        <div class="task-col operation">操作</div>
                    </div>
                    <div class="task-list-body">
            `;

                // 计算序号起始值（基于当前页）
                const sequenceStart = ((currentTaskPage || 1) - 1) * pageSize + 1;

                tasks.forEach((task, index) => {
                    const taskId = escapeHtml(task.task_id || 'N/A');
                    const taskName = escapeHtml(task.task_name || task.task_group || 'N/A');
                    const status = task.status || 'unknown';
                    const statusText = getTaskStatusText(status);
                    const msg = escapeHtml(task.msg || '-');
                    const remarks = escapeHtml(task.remarks || '-');
                    const updateTime = task.update_time ? (typeof task.update_time === 'string' ? task.update_time : new Date(task.update_time * 1000).toLocaleString('zh-CN')) : 'N/A';
                    const createTime = task.create_time ? (typeof task.create_time === 'string' ? task.create_time : new Date(task.create_time * 1000).toLocaleString('zh-CN')) : 'N/A';
                    const sequenceNumber = sequenceStart + index; // 序号从当前页的起始值开始

                    // 状态样式（支持中英文状态，验证码显示黄色）
                    const statusClass = (status === '已完成' || status === 'success' || status === '执行成功') ? 'success' :
                        (status === '异常' || status === 'failed' || status === '执行失败') ? 'error' :
                            (status === '进行中' || status === 'running') ? 'warning' :
                                (status === '验证码' || status === 'captcha') ? 'captcha' :
                                    (status === '待处理' || status === 'pending' || status === '待执行') ? 'info' :
                                        (status === '已超时' || status === 'timeout') ? 'error' :
                                            (status === '已退出' || status === 'stopped') ? 'default' : 'default';

                    html += `
                    <div class="task-item-row">
                        <div class="task-col checkbox">
                            <input type="checkbox" class="task-checkbox" data-task-id="${escapeHtml(task.task_id || '')}" onchange="updateBatchActionsVisibility()">
                        </div>
                        <div class="task-col id" title="任务ID: ${taskId}">${sequenceNumber}</div>
                        <div class="task-col type" title="${taskName}">${taskName}</div>
                        <div class="task-col status">
                            <span class="ui label ${statusClass}">${statusText}</span>
                        </div>
                        <div class="task-col msg" title="${msg}">${msg}</div>
                        <div class="task-col remarks" title="${remarks}">${remarks}</div>
                        <div class="task-col time" title="${updateTime}">${updateTime}</div>
                        <div class="task-col create-time" title="${createTime}">${createTime}</div>
                        <div class="task-col operation">
                            <div class="task-operation-buttons">
                                <div class="task-operation-column">
                                    <button class="ui primary button" onclick="rerunTask('${escapeHtml(task.task_id || '')}')" title="重跑任务">
                                        <i class="play icon"></i> 重跑
                                    </button>
                                    <button class="ui button" onclick="stopTask('${escapeHtml(task.task_id || '')}')" title="停止任务" style="background-color: #faa64b; color: white;">
                                        <i class="stop icon"></i> 停止
                                    </button>
                                </div>
                                <div class="task-operation-column">
                                    <button class="ui violet button" onclick="viewTaskLog('${escapeHtml(task.task_id || '')}')" title="查看日志">
                                        <i class="file text icon"></i> 日志
                                    </button>
                                    <button class="ui button" onclick="editTask('${escapeHtml(task.task_id || '')}')" title="设置任务">
                                        <i class="cog icon"></i> 设置
                                    </button>
                                    <button class="ui red button" onclick="deleteTask('${escapeHtml(task.task_id || '')}')" title="删除任务">
                                        <i class="trash icon"></i> 删除
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                });

                html += `
                    </div>
                </div>
    `;

                container.innerHTML = html;
                // 初始化批量操作按钮的显示状态
                updateBatchActionsVisibility();
            } else {
                container.innerHTML = '<p style="text-align: center; color: #999;">暂无任务</p>';
                // 没有任务时隐藏批量操作按钮
                updateBatchActionsVisibility();
            }

            // 无论是否有数据，都更新分页控件
            updateTaskPaginationControls();
        } else {
            container.innerHTML = '<p style="text-align: center; color: #999;">暂无任务</p>';
            // 清空分页
            updateTaskPaginationControls();
        }
    } catch (error) {
        container.innerHTML = `<p style="color: red; text-align: center;">加载任务列表失败: ${error.message}</p>`;
        console.error('加载任务列表失败:', error);
    }
}

function getTaskStatusText(status) {
    const statusMap = {
        'running': '进行中',
        'pending': '待执行',
        'success': '执行成功',
        'failed': '执行失败',
        'timeout': '执行超时',
        'completed': '已完成',
        'captcha': '验证码',
        '进行中': '进行中',
        '待处理': '待处理',
        '已完成': '已完成',
        '异常': '异常',
        '已超时': '已超时',
        '已退出': '已退出',
        '验证码': '验证码'
    };
    return statusMap[status] || status;
}

// 获取任务类型信息（文本 + 颜色标记 + key）
function getTaskTypeInfo(taskId, funcName, taskName = '') {
    const sourceText = `${taskId || ''} ${funcName || ''} ${taskName || ''} `;
    if (
        sourceText.includes('上传实拍图') ||
        sourceText.includes('upload_real_pic')
    ) {
        return {
            key: 'upload',
            text: '上传实拍图任务',
            className: 'type-upload'
        };
    }
    if (
        sourceText.includes('核价') ||
        sourceText.includes('modify_price')
    ) {
        return {
            key: 'price',
            text: '核价任务',
            className: 'type-price'
        };
    }
    if (
        sourceText.includes('调价') ||
        sourceText.includes('adjust_price')
    ) {
        return {
            key: 'adjust',
            text: '调价管理',
            className: 'type-adjust'
        };
    }
    if (
        sourceText.includes('批量修改期望到货地点') ||
        sourceText.includes('expected_goods_place')
    ) {
        return {
            key: 'expected_goods_place',
            text: '批量修改期望到货地点',
            className: 'type-adjust'
        };
    }
    if (
        sourceText.includes('批量加入发货台') ||
        sourceText.includes('purchase_delivery')
    ) {
        return {
            key: 'purchase_delivery',
            text: '批量加入发货台',
            className: 'type-adjust'
        };
    }
    if (
        sourceText.includes('虎扑帖子列表') ||
        sourceText.includes('hupu_post_list')
    ) {
        return {
            key: 'hupu_post',
            text: '虎扑帖子列表',
            className: 'type-hupu-post'
        };
    }
    if (
        sourceText.includes('虎扑帖子详情') ||
        sourceText.includes('hupu_detail_list')
    ) {
        return {
            key: 'hupu_detail',
            text: '虎扑帖子详情',
            className: 'type-hupu-detail'
        };
    }
    if (
        sourceText.includes('虎扑评分采集') ||
        sourceText.includes('hupu_score_list')
    ) {
        return {
            key: 'hupu_score',
            text: '虎扑评分采集',
            className: 'type-hupu-score'
        };
    }
    return {
        key: 'other',
        text: '其他任务',
        className: 'type-default'
    };
}

// 查看任务详情
async function viewTaskDetail(taskId) {
    try {
        // 从当前任务列表中查找任务详情
        const result = await requestPost('/api/get_tasks', {}, { task_id: taskId });
        if (result.success && result.tasks && result.tasks.length > 0) {
            const task = result.tasks[0];
            // 构建详情内容
            const detailHtml = `
    <div style="max-width: 800px;">
                    <h3>任务详情</h3>
                    <table class="ui celled table">
                        <tbody>
                            <tr>
                                <td><strong>任务ID</strong></td>
                                <td>${escapeHtml(task.task_id || 'N/A')}</td>
                            </tr>
                            <tr>
                                <td><strong>任务名称</strong></td>
                                <td>${escapeHtml(task.task_name || 'N/A')}</td>
                            </tr>
                            <tr>
                                <td><strong>状态</strong></td>
                                <td>${escapeHtml(getTaskStatusText(task.status || 'unknown'))}</td>
                            </tr>
                            <tr>
                                <td><strong>函数名</strong></td>
                                <td>${escapeHtml(task.func_name || 'N/A')}</td>
                            </tr>
                            <tr>
                                <td><strong>任务组</strong></td>
                                <td>${escapeHtml(task.task_group || 'N/A')}</td>
                            </tr>
                            <tr>
                                <td><strong>信息</strong></td>
                                <td>${escapeHtml(task.msg || '-')}</td>
                            </tr>
                            <tr>
                                <td><strong>备注</strong></td>
                                <td>${escapeHtml(task.remarks || '-')}</td>
                            </tr>
                            <tr>
                                <td><strong>创建时间</strong></td>
                                <td>${task.create_time ? (typeof task.create_time === 'string' ? task.create_time : new Date(task.create_time * 1000).toLocaleString('zh-CN')) : 'N/A'}</td>
                            </tr>
                            <tr>
                                <td><strong>更新时间</strong></td>
                                <td>${task.update_time ? (typeof task.update_time === 'string' ? task.update_time : new Date(task.update_time * 1000).toLocaleString('zh-CN')) : 'N/A'}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
    `;
            // 使用 Semantic UI 的模态框显示详情
            if (typeof $ !== 'undefined' && $.fn) {
                const modal = $('<div class="ui modal" id="taskDetailModal"><div class="header">任务详情</div><div class="content">' + detailHtml + '</div><div class="actions"><div class="ui button" onclick="$(\'#taskDetailModal\').modal(\'hide\')">关闭</div></div></div>');
                $('body').append(modal);
                modal.modal('show');
                modal.on('hidden', function () {
                    modal.remove();
                });
            } else {
                alert('任务详情：\n' + JSON.stringify(task, null, 2));
            }
        } else {
            showError('获取任务详情失败：任务不存在');
        }
    } catch (error) {
        showError(`获取任务详情失败：${error.message} `);
    }
}

// 查看任务日志（带自动刷新）
let taskLogRefreshInterval = null;
let currentLogTaskId = null;
let isAutoRefreshEnabled = true; // 自动刷新开关状态

async function viewTaskLog(taskId) {
    // 如果已经有日志窗口打开，先关闭之前的
    if (taskLogRefreshInterval) {
        clearInterval(taskLogRefreshInterval);
        taskLogRefreshInterval = null;
    }

    // 如果已经有模态框打开，先移除
    const existingModal = $('#taskLogModal');
    if (existingModal.length) {
        existingModal.modal('hide');
        existingModal.remove();
    }

    currentLogTaskId = taskId;
    isAutoRefreshEnabled = true; // 默认开启自动刷新

    // 标志：是否已经检查过日志长度（只在第一次点击时检查）
    let hasCheckedLogLength = false;

    // 创建模态框
    const modalId = 'taskLogModal';
    const logContainerId = 'taskLogContent';

    const logHtml = `
    <div style="max-width: 1000px;">
            <h4>任务日志：${escapeHtml(taskId)}</h4>
            <div id="${logContainerId}" style="background: #1a202c; color: #fff; padding: 1rem; border-radius: 4px; max-height: 500px; overflow-y: auto; font-family: 'Consolas', 'Monaco', 'Courier New', monospace; font-size: 0.875rem; white-space: pre-wrap; word-wrap: break-word; min-height: 200px;">
                <div style="text-align: center; color: #888; padding: 2rem;">正在加载日志...</div>
            </div>
        </div>
    `;

    const modal = $(`
    <div class="ui modal" id="${modalId}">
            <div class="header">
                <i class="file text icon"></i> 任务日志
                <span id="taskLogRefreshStatus" style="font-size: 0.8em; color: #999; margin-left: 10px;">（自动刷新中）</span>
                <span style="font-size: 0.75em; color: #999; margin-left: 10px;">复制内容时请先暂停</span>
            </div>
            <div class="content">${logHtml}</div>
            <div class="actions">
                <div class="ui orange button" onclick="toggleTaskLogAutoRefresh()" id="toggleAutoRefreshBtn">
                    <i class="pause icon"></i> 暂停刷新
                </div>
                <div class="ui green button" onclick="scrollTaskLogUp()">
                    <i class="arrow up icon"></i> 翻到顶部
                </div>
                <div class="ui purple button" onclick="scrollTaskLogDown()">
                    <i class="arrow down icon"></i> 翻到底部
                </div>
                <div class="ui red button" onclick="clearTaskLog('${escapeHtml(taskId)}')">
                    <i class="trash icon"></i> 清除日志
                </div>
                <div class="ui button" onclick="closeTaskLogModal()">关闭</div>
            </div>
        </div >
    `);

    $('body').append(modal);

    // 加载日志的函数
    const loadLog = async () => {
        try {
            const result = await requestPost('/api/get_task_log', {}, { task_id: taskId });
            if (result.success) {
                const logContent = result.log || '暂无日志';
                const logLength = logContent.length;
                const logThreshold = 1216112;  // 阈值：458056字符的2倍
                console.log(`任务日志长度: ${logLength}, 阈值: 2倍458056, 已检查: ${hasCheckedLogLength}`);

                // 只在第一次加载时检查日志长度
                if (!hasCheckedLogLength && logLength > logThreshold) {
                    hasCheckedLogLength = true;  // 标记已检查

                    // 日志过大，弹出确认框
                    const shouldClean = await showConfirmDialog(
                        '任务日志内容过多',
                        `当前任务日志字符数为 ${logLength}，超过阈值 ${logThreshold}。<br><br>` +
                        `日志过多可能导致页面加载缓慢或崩溃。<br><br>` +
                        `是否清除该任务的日志？`,
                        '清除日志',
                        '取消'
                    );

                    if (shouldClean) {
                        // 用户确认清除日志，保留最新20%
                        const cleanResult = await requestPost('/api/clean_task_log_with_keep', {}, { task_id_list: [taskId], keep_ratio: 0.2 });
                        if (cleanResult && cleanResult.success) {
                            showSuccess(cleanResult.msg || '任务日志已清除');
                            // 清除后重新加载日志
                            await loadLog();
                            return;
                        } else {
                            showError('清除日志失败：' + (cleanResult.error_msg || cleanResult.message || '未知错误'));
                            // 即使清除失败，也继续显示日志
                        }
                    }
                }

                const logContainer = document.getElementById(logContainerId);
                if (logContainer) {
                    // 保存滚动位置
                    const scrollTop = logContainer.scrollTop;
                    const isScrolledToBottom = logContainer.scrollHeight - logContainer.scrollTop <= logContainer.clientHeight + 10;

                    // 直接显示所有日志内容
                    logContainer.textContent = logContent;

                    // 如果之前滚动到底部，自动滚动到底部
                    if (isScrolledToBottom) {
                        logContainer.scrollTop = logContainer.scrollHeight;
                    } else {
                        logContainer.scrollTop = scrollTop;
                    }
                }
            } else {
                const errorMsg = result.error_msg || result.message || '未知错误';
                const logContainer = document.getElementById(logContainerId);
                if (logContainer) {
                    logContainer.innerHTML = `< div style = "color: #f44336;" > 获取日志失败：${escapeHtml(errorMsg)}</div > `;
                }
            }
        } catch (error) {
            const logContainer = document.getElementById(logContainerId);
            if (logContainer) {
                logContainer.innerHTML = `< div style = "color: #f44336;" > 获取日志失败：${escapeHtml(error.message)}</div > `;
            }
        }
    };

    // 立即加载一次
    await loadLog();

    // 启动自动刷新
    startTaskLogAutoRefresh(modalId, loadLog);

    // 显示模态框
    modal.modal({
        onHidden: function () {
            // 关闭时清除定时器
            if (taskLogRefreshInterval) {
                clearInterval(taskLogRefreshInterval);
                taskLogRefreshInterval = null;
            }
            currentLogTaskId = null;
            modal.remove();
        }
    }).modal('show');
}

// 向上翻任务日志（直接翻到顶部）
function scrollTaskLogUp() {
    const logContainer = document.getElementById('taskLogContent');
    if (logContainer) {
        // 直接滚动到顶部
        logContainer.scrollTop = 0;
    }
}

// 向下翻任务日志（直接翻到底部）
function scrollTaskLogDown() {
    const logContainer = document.getElementById('taskLogContent');
    if (logContainer) {
        // 直接滚动到底部
        logContainer.scrollTop = logContainer.scrollHeight;
    }
}

// 清除任务日志（清空显示并清除服务器端日志）
async function clearTaskLog(taskId) {
    // 如果没有传递参数，尝试使用当前打开的任务ID
    if (!taskId && typeof currentLogTaskId !== 'undefined') {
        taskId = currentLogTaskId;
    }

    if (!taskId) {
        showError('任务ID不能为空');
        return;
    }

    try {
        const shouldClean = await showConfirmDialog(
            '清除任务日志',
            '确定要清除该任务的日志吗？此操作不可恢复！',
            '确认清除',
            '取消'
        );
        
        if (!shouldClean) {
            return;
        }
        
        // 先清空显示
        const logContainer = document.getElementById('taskLogContent');
        if (logContainer) {
            logContainer.textContent = '';
        }

        // 清除服务器端日志
        const result = await requestPost('/api/clean_task_log', {}, { task_id_list: [taskId] });
        if (result.success) {
            showSuccess(result.msg || '日志清除成功');
            // 重新加载日志（此时应该显示为空或已清除的状态）
            const loadLog = async () => {
                try {
                    const logResult = await requestPost('/api/get_task_log', {}, { task_id: taskId });
                    if (logResult.success) {
                        const logContent = logResult.log || '日志已清除';
                        const logContainer = document.getElementById('taskLogContent');
                        if (logContainer) {
                            logContainer.textContent = logContent;
                            logContainer.scrollTop = logContainer.scrollHeight;
                        }
                    }
                } catch (error) {
                    console.error('重新加载日志失败:', error);
                }
            };
            await loadLog();
        } else {
            showError(result.error_msg || result.message || '清除日志失败');
        }
    } catch (error) {
        console.error('清除日志失败:', error);
        showError('清除日志失败：' + error.message);
    }
}

// 启动任务日志自动刷新
function startTaskLogAutoRefresh(modalId, loadLog) {
    // 如果已经有定时器在运行，先清除
    if (taskLogRefreshInterval) {
        clearInterval(taskLogRefreshInterval);
        taskLogRefreshInterval = null;
    }

    // 设置定时刷新，每隔1秒刷新一次
    taskLogRefreshInterval = setInterval(async () => {
        // 检查自动刷新是否启用
        if (!isAutoRefreshEnabled) {
            return;
        }

        // 检查模态框是否还存在且可见
        const modalElement = document.getElementById(modalId);
        if (modalElement && modalElement.classList.contains('active')) {
            await loadLog();
        } else {
            // 如果模态框已关闭，清除定时器
            if (taskLogRefreshInterval) {
                clearInterval(taskLogRefreshInterval);
                taskLogRefreshInterval = null;
            }
        }
    }, 1000);
}

// 停止任务日志自动刷新
function stopTaskLogAutoRefresh() {
    if (taskLogRefreshInterval) {
        clearInterval(taskLogRefreshInterval);
        taskLogRefreshInterval = null;
    }
}

// 切换任务日志自动刷新
function toggleTaskLogAutoRefresh() {
    isAutoRefreshEnabled = !isAutoRefreshEnabled;

    const statusSpan = document.getElementById('taskLogRefreshStatus');
    const toggleBtn = document.getElementById('toggleAutoRefreshBtn');

    if (isAutoRefreshEnabled) {
        // 开启自动刷新
        if (statusSpan) {
            statusSpan.textContent = '（自动刷新中）';
        }
        if (toggleBtn) {
            toggleBtn.innerHTML = '<i class="pause icon"></i> 暂停刷新';
        }
    } else {
        // 关闭自动刷新
        if (statusSpan) {
            statusSpan.innerHTML = '<span style="color: #FFD700;">（已暂停）</span>';
        }
        if (toggleBtn) {
            toggleBtn.innerHTML = '<i class="play icon"></i> 开始刷新';
        }
    }
}

// 关闭任务日志模态框
function closeTaskLogModal() {
    if (taskLogRefreshInterval) {
        clearInterval(taskLogRefreshInterval);
        taskLogRefreshInterval = null;
    }
    $('#taskLogModal').modal('hide');
    currentLogTaskId = null;
    isAutoRefreshEnabled = true; // 重置为默认状态
}

// 任务日志/停止（保留旧函数名以兼容）
function viewTaskLogs(taskId) {
    viewTaskLog(taskId);
}

// 刷新任务（重新加载任务列表）
function refreshTask(taskId) {
    loadTasks();
    showSuccess('任务列表已刷新');
}

async function rerunTask(taskId) {
    if (!taskId) {
        showError('重跑失败：任务ID缺失');
        return;
    }

    // 二次确认
    try {
        await openConfirmModal(`确认重跑该任务吗？重跑会检测是否运行并先执行停止再开始重跑`);
    } catch (error) {
        if (error && error.message !== '用户取消操作') {
            showError('重跑失败：' + (error.message || '未知错误'));
        }
        // 用户取消或出错都不继续调用接口
        return;
    }

    try {
        const result = await requestPost('/api/re_run_task', {}, { task_id: taskId });
        if (result && result.success) {
            showSuccess(result.message || '重跑任务已提交');
            // 重跑成功后刷新任务列表
            loadTasks();
        } else {
            const errorMsg = (result && (result.error_msg || result.message)) || '未知错误';
            showError(`重跑失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`重跑失败：${error.message || '请求异常'} `);
    }
}

async function stopTask(taskId) {
    if (!taskId) {
        showError('停止失败：任务ID缺失');
        return;
    }

    // 二次确认
    try {
        await openConfirmModal(`确认停止该任务吗？`);
    } catch (error) {
        if (error && error.message !== '用户取消操作') {
            showError('停止失败：' + (error.message || '未知错误'));
        }
        // 用户取消或出错都不继续调用接口
        return;
    }

    try {
        const result = await requestPost('/api/stop_task', {}, { task_id: taskId });
        if (result && result.success) {
            showSuccess(result.message || '停止任务已提交');
            // 停止成功后刷新任务列表
            loadTasks();
        } else {
            const errorMsg = (result && (result.error_msg || result.message)) || '未知错误';
            showError(`停止失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`停止失败：${error.message || '请求异常'} `);
    }
}

async function editTask(taskId) {
    if (!taskId) {
        showError('设置失败：任务ID缺失');
        return;
    }

    try {
        const result = await requestPost('/api/get_tasks', {}, { task_id: taskId });
        if (result.success && result.tasks && result.tasks.length > 0) {
            const task = result.tasks[0];
            
            // 根据任务类型确定taskType
            const taskName = task.task_name || task.task_group || '';
            const funcName = task.func_name || '';
            let taskType = '';
            
            if (taskName.includes('上传实拍图') || funcName === 'upload_real_pic') {
                taskType = 'upload_real_pic';
            } else if (taskName.includes('核价') || funcName === 'modify_price') {
                taskType = 'modify_price';
            } else if (taskName.includes('JIT维护库存') || funcName === 'jit_govern') {
                taskType = 'jit_govern';
            } else if (taskName.includes('调价') || taskName.includes('价格申报') || funcName === 'adjust_price') {
                taskType = 'adjust_price';
            } else if (taskName.includes('虎扑帖子列表') || funcName === 'hupu_post_list') {
                taskType = 'hupu_post_list';
            } else if (taskName.includes('虎扑帖子详情') || funcName === 'hupu_detail_list') {
                taskType = 'hupu_detail_list';
            } else if (taskName.includes('虎扑评分') || funcName === 'hupu_score_list') {
                taskType = 'hupu_score_list';
            } else if (taskName.includes('生成财务报表全流程') || funcName.includes('all_make_caiwu_excel_wrapper')) {
                taskType = 'financial_full';
            } else if (taskName.includes('导出所选月份账单') || taskName.includes('导出月份账单') || funcName.includes('download_export_excel_wrapper')) {
                taskType = 'financial_export';
            } else if (taskName.includes('融合所选月份账单') || taskName.includes('融合月份账单') || funcName.includes('merge_all_months_excel_wrapper')) {
                taskType = 'financial_merge';
            } else if (taskName.includes('记录所需列到总表') || taskName.includes('记录到总表') || funcName.includes('record_all_need_colum_to_excel_wrapper')) {
                taskType = 'financial_record';
            } else if (taskName.includes('计算并生成财务报表') || funcName.includes('make_caiwu_excel_wrapper')) {
                taskType = 'financial_calculate';
            } else if (taskName.includes('生成SKU汇总表') || funcName.includes('sku_summary_wrapper')) {
                taskType = 'sku_summary';
            } else if (taskName.includes('报活动任务') || funcName === 'apply_activity') {
                taskType = 'apply_activity';
            } else if (taskName.includes('批量修改期望到货地点') || funcName === 'expected_goods_place') {
                taskType = 'expected_goods_place';
            } else if (taskName.includes('批量加入发货台') || funcName === 'purchase_delivery') {
                taskType = 'purchase_delivery';
            }
            
            if (!taskType) {
                showError('无法识别任务类型：' + taskName);
                return;
            }
            
            // 打开任务模态框，并标记为编辑模式
            currentModalData = { taskType, taskId, isEdit: true };
            openTaskModal(taskType, true, taskId);

            // 等待模态框加载完成后填充参数
            // 注意：loadSavedCategoryList 在 openTaskModal 的 setTimeout(..., 200) 中被调用
            // fillTaskParams 需要在其之后执行，这里使用 600ms 确保 loadSavedCategoryList 的 API 返回
            setTimeout(async () => {
                fillTaskParams(task, true);

                // 加载定时任务配置
                await loadScheduleConfig(taskId);
            }, 600);
            
        } else {
            showError('获取任务详情失败：任务不存在');
        }
    } catch (error) {
        showError(`获取任务详情失败：${error.message}`);
    }
}

async function loadScheduleConfig(taskId) {
    try {
        console.log('开始加载定时任务配置，taskId:', taskId);
        const result = await requestPost('/api/get_schedule_task', {}, { task_id: taskId });
        console.log('API响应结果:', result);
        
        // 等待一段时间，确保通用任务配置监听器已经初始化
        await new Promise(resolve => setTimeout(resolve, 200));
        
        if (result && result.success && result.data) {
            const schedule = result.data;
            console.log('定时任务配置数据:', schedule);
            
            // 勾选启用定时任务复选框
            const enableScheduleCheckbox = document.getElementById('enableSchedule');
            console.log('enableScheduleCheckbox 元素:', enableScheduleCheckbox);
            
            if (enableScheduleCheckbox) {
                enableScheduleCheckbox.checked = true;
                console.log('已勾选启用定时任务复选框');
                // 触发change事件以显示定时配置区域
                const event = new Event('change');
                enableScheduleCheckbox.dispatchEvent(event);
                
                // 等待一段时间，确保定时配置区域已经显示
                await new Promise(resolve => setTimeout(resolve, 200));
            }
            
            // 填充定时任务配置
            if (schedule.schedule_type) {
                const scheduleTypeEl = document.getElementById('scheduleType');
                if (scheduleTypeEl) {
                    scheduleTypeEl.value = schedule.schedule_type;
                    console.log('已设置定时类型:', schedule.schedule_type);
                    // 触发change事件以更新显示字段
                    const scheduleTypeEvent = new Event('change');
                    scheduleTypeEl.dispatchEvent(scheduleTypeEvent);
                    
                    // 等待一段时间，确保相关字段已经显示
                    await new Promise(resolve => setTimeout(resolve, 200));
                    
                    // 确保立即执行选项组显示
                    const scheduleImmediateGroup = document.getElementById('scheduleImmediateGroup');
                    if (scheduleImmediateGroup) {
                        scheduleImmediateGroup.style.display = 'block';
                        console.log('已显示立即执行选项组');
                    }
                }
            }
            
            if (schedule.schedule_time) {
                const scheduleTimeEl = document.getElementById('scheduleTime');
                if (scheduleTimeEl) {
                    scheduleTimeEl.value = schedule.schedule_time;
                    console.log('已设置执行时间:', schedule.schedule_time);
                }
            }
            
            if (schedule.schedule_interval) {
                const scheduleIntervalEl = document.getElementById('scheduleInterval');
                if (scheduleIntervalEl) {
                    scheduleIntervalEl.value = schedule.schedule_interval;
                    console.log('已设置执行间隔:', schedule.schedule_interval);
                }
            }
            
            // schedule_enabled 表示是否启用定时任务
            // 由于 scheduled_tasks 表中没有存储 execute_immediately 字段，所以默认不勾选"立即执行"
            // 用户如果需要立即执行，可以手动勾选
            const executeImmediatelyCheckbox = document.getElementById('executeImmediately');
            if (executeImmediatelyCheckbox) {
                executeImmediatelyCheckbox.checked = false;
                if ($('#executeImmediatelyCheckbox').length) {
                    $('#executeImmediatelyCheckbox').checkbox('set unchecked');
                }
                console.log('已设置立即执行为false（默认值）');
            }
        } else {
            console.log('没有定时任务配置，取消勾选启用定时任务复选框');
            // 没有定时任务配置，取消勾选启用定时任务复选框
            const enableScheduleCheckbox = document.getElementById('enableSchedule');
            if (enableScheduleCheckbox) {
                enableScheduleCheckbox.checked = false;
                // 触发change事件以隐藏定时配置区域
                const event = new Event('change');
                enableScheduleCheckbox.dispatchEvent(event);
            }
        }
    } catch (error) {
        console.error('加载定时任务配置失败:', error);
        showError('加载定时任务配置失败：' + error.message);
    }
}

function fillTaskParams(task, isEdit = false) {
    try {
        const taskName = task.task_name || task.task_group || '';
        const funcName = task.func_name || '';
        
        // 从task_kwargs中获取参数（数据库存储的字段名）
        const taskKwargs = task.task_kwargs || task.params || {};
        const params = typeof taskKwargs === 'string' ? JSON.parse(taskKwargs) : taskKwargs;
        
        // 保存原有的uid和main_task_id，用于编辑时保留这些值
        if (isEdit && currentModalData) {
            currentModalData.originalUid = params.uid;
            currentModalData.originalMainTaskId = params.main_task_id;
        }
        
        // 填充上传实拍图任务参数
        if (taskName.includes('上传实拍图') || task.func_name === 'upload_real_pic') {
            if (params) {
                if (params.input_check_type_list) {
                    $('#inputCheckTypeList').dropdown('set selected', params.input_check_type_list);
                }
                if (params.input_rapid_screen_status_list) {
                    $('#inputRapidScreenStatusList').dropdown('set value', params.input_rapid_screen_status_list);
                }
                if (params.input_spu_id_list) {
                    $('#inputSpuIdList').val(params.input_spu_id_list);
                }
                if (params.black_word_type_list) {
                    $('#blackWordTypeList').dropdown('set selected', params.black_word_type_list);
                }
                if (params.goods_status_list) {
                    $('#goodsStatusList').dropdown('set selected', params.goods_status_list);
                }
                if (params.sleep_open !== undefined) {
                    $('#sleepOpen').prop('checked', params.sleep_open);
                    $('#sleepOpenCheckbox').checkbox(params.sleep_open ? 'set checked' : 'set unchecked');
                }
                if (params.custom_fixed_upload_img !== undefined) {
                    $('#customFixedUploadImg').prop('checked', params.custom_fixed_upload_img);
                    $('#customFixedUploadImgCheckbox').checkbox(params.custom_fixed_upload_img ? 'set checked' : 'set unchecked');
                }
            }
        }
        
        // 填充核价任务参数
        else if (taskName.includes('核价') || task.func_name === 'modify_price') {
            if (params) {
                if (params.input_spu_id_list) {
                    $('#inputSpuIdList').val(params.input_spu_id_list);
                }
                if (params.modify_times) {
                    $('#inputModifyTimes').val(params.modify_times);
                }
                if (params.minu_price) {
                    $('#inputMinuPrice').val(params.minu_price);
                }
            }
        }
        
        // 填充JIT维护库存任务参数
        else if (taskName.includes('JIT维护库存') || task.func_name === 'jit_govern') {
            if (params) {
                if (params.spu_id_list) {
                    $('#inputSkcSpuList').val(params.spu_id_list.join(','));
                }
                if (params.start_date) {
                    const parseDate = (dateStr) => {
                        if (!dateStr || dateStr.length !== 8) return { display: '', hidden: '' };
                        const year = dateStr.substring(0, 4);
                        const month = dateStr.substring(4, 6);
                        const day = dateStr.substring(6, 8);
                        return {
                            display: `${year}-${month}-${day}`,
                            hidden: dateStr
                        };
                    };
                    const startDate = parseDate(params.start_date);
                    $('#inputStartDate').val(startDate.hidden);
                    $('#inputStartDateDisplay').val(startDate.display);
                }
                if (params.end_date) {
                    const parseDate = (dateStr) => {
                        if (!dateStr || dateStr.length !== 8) return { display: '', hidden: '' };
                        const year = dateStr.substring(0, 4);
                        const month = dateStr.substring(4, 6);
                        const day = dateStr.substring(6, 8);
                        return {
                            display: `${year}-${month}-${day}`,
                            hidden: dateStr
                        };
                    };
                    const endDate = parseDate(params.end_date);
                    $('#inputEndDate').val(endDate.hidden);
                    $('#inputEndDateDisplay').val(endDate.display);
                }
                if (params.final_num) {
                    $('#inputFinalNum').val(params.final_num);
                }
            }
        }
        
        // 填充调价管理任务参数
        else if (taskName.includes('调价') || taskName.includes('价格申报') || task.func_name === 'adjust_price') {
            if (params) {
                if (params.skc_id_list) {
                    $('#inputSkcIdList').val(params.skc_id_list.join(','));
                }
                if (params.order_id_list) {
                    $('#inputOrderIdList').val(params.order_id_list.join(','));
                }
            }
        }
        
        // 填充虎扑帖子列表采集参数
        else if (taskName.includes('虎扑帖子列表') || task.func_name === 'hupu_post_list') {
            if (params) {
                if (params.keyword) {
                    $('#hupuKeyword').val(params.keyword);
                }
                if (params.max_pages) {
                    $('#hupuMaxPages').val(params.max_pages);
                }
                if (params.sleep_time) {
                    $('#hupuSleepTime').val(params.sleep_time);
                }
                if (params.sortby) {
                    $('#hupuSortby').dropdown('set value', params.sortby);
                }
                if (params.topic_id) {
                    $('#hupuTopicId').val(params.topic_id);
                }
                if (params.only_one_page !== undefined) {
                    $('#hupuOnlyOnePage').prop('checked', params.only_one_page);
                    $('#hupuOnlyOnePageCheckbox').checkbox(params.only_one_page ? 'set checked' : 'set unchecked');
                    if (params.only_one_page) {
                        $('#hupuSpecificPageGroup').show();
                    }
                }
                if (params.specific_page) {
                    $('#hupuSpecificPage').val(params.specific_page);
                }
            }
        }
        
        // 填充虎扑帖子详情采集参数
        else if (taskName.includes('虎扑帖子详情') || task.func_name === 'hupu_detail_list') {
            if (params) {
                if (params.name) {
                    $('#hupuDetailName').val(params.name);
                    autoGetPostTitle();
                }
                if (params.title) {
                    $('#hupuDetailTitle').val(params.title);
                }
                if (params.max_pages) {
                    $('#hupuDetailMaxPages').val(params.max_pages);
                }
                if (params.sleep_time) {
                    $('#hupuDetailSleepTime').val(params.sleep_time);
                }
                if (params.only_one_page !== undefined) {
                    $('#hupuDetailOnlyOnePage').prop('checked', params.only_one_page);
                    $('#hupuDetailOnlyOnePageCheckbox').checkbox(params.only_one_page ? 'set checked' : 'set unchecked');
                    if (params.only_one_page) {
                        $('#hupuDetailSpecificPageGroup').show();
                    }
                }
                if (params.specific_page) {
                    $('#hupuDetailSpecificPage').val(params.specific_page);
                }
            }
        }
        
        // 填充虎扑评分采集参数
        else if (taskName.includes('虎扑评分') || task.func_name === 'hupu_score_list') {
            if (params) {
                if (params.post_id) {
                    $('#hupuScorePostId').val(params.post_id);
                    autoGetScorePostTitle();
                }
                if (params.title) {
                    $('#hupuScorePostTitle').val(params.title);
                }
                if (params.max_pages) {
                    $('#hupuScoreMaxPages').val(params.max_pages);
                }
                if (params.sleep_time) {
                    $('#hupuScoreSleepTime').val(params.sleep_time);
                }
            }
        }
        
        // 填充报活动任务参数
        else if (taskName.includes('报活动任务') || task.func_name === 'apply_activity') {
            if (params) {
                if (params.spu_id_list && params.spu_id_list.length > 0) {
                    $('#inputSpuIdList').val(params.spu_id_list.join(','));
                }
                if (params.activityType_list && params.activityType_list.length > 0) {
                    const activityTypeDropdown = document.getElementById('activityTypeDropdown');
                    if (activityTypeDropdown) {
                        setTimeout(() => {
                            const dropdown = $(activityTypeDropdown);
                            dropdown.dropdown('clear');
                            params.activityType_list.forEach(value => {
                                dropdown.dropdown('set selected', String(value));
                            });
                        }, 300);
                    }
                }
                
                // 恢复排除SKC列表
                if (params.not_skc_list && params.not_skc_list.length > 0) {
                    const notSkcInput = document.getElementById('inputNotSkcList');
                    if (notSkcInput) {
                        notSkcInput.value = params.not_skc_list.join(', ');
                    }
                }
                
                // 恢复"隐藏低效日志"复选框状态
                if (params.open_log_false !== undefined) {
                    const openLogFalseCheckbox = document.getElementById('openLogFalseCheckbox');
                    if (openLogFalseCheckbox) {
                        openLogFalseCheckbox.checked = params.open_log_false; // UI状态与参数一致
                    }
                }
            }
        }

        else if (taskName.includes('批量修改期望到货地点') || task.func_name === 'expected_goods_place') {
            if (params) {
                if (params.skc_id_list && params.skc_id_list.length > 0) {
                    const skcInput = document.getElementById('inputExpectedSkcIdList');
                    if (skcInput) {
                        skcInput.value = params.skc_id_list.join(' ');
                    }
                }
                if (params.max_page) {
                    const maxPageDropdown = document.getElementById('expectedMaxPageDropdown');
                    if (maxPageDropdown) {
                        setTimeout(() => {
                            const dropdown = $(maxPageDropdown);
                            if (params.max_page !== null && params.max_page !== undefined) {
                                dropdown.dropdown('set selected', String(params.max_page));
                            }
                        }, 300);
                    }
                }
                if (params.cat_id_list && params.cat_id_list.length > 0) {
                    const catDropdown = document.getElementById('expectedCatIdDropdown');
                    if (catDropdown) {
                        const menu = catDropdown.querySelector('.menu');
                        const dropdown = $(catDropdown);

                        // 先清空现有选项
                        menu.innerHTML = '';

                        // 直接从参数中创建选项
                        params.cat_id_list.forEach(cat => {
                            if (cat.cat_ids && cat.cat_ids.length > 0 && cat.cat_names && cat.cat_names.length > 0) {
                                const catId = String(cat.cat_ids[cat.cat_ids.length - 1]);
                                const catName = cat.cat_names[cat.cat_names.length - 1];

                                const item = document.createElement('div');
                                item.className = 'item';
                                item.setAttribute('data-value', catId);
                                item.dataset.value = catId;
                                item.dataset.catIds = JSON.stringify(cat.cat_ids);
                                item.dataset.catNames = JSON.stringify(cat.cat_names);

                                const contentDiv = document.createElement('div');
                                contentDiv.style.display = 'flex';
                                contentDiv.style.justifyContent = 'space-between';
                                contentDiv.style.alignItems = 'center';
                                contentDiv.style.width = '100%';

                                const textSpan = document.createElement('span');
                                textSpan.textContent = `${catId} ${catName}`;
                                textSpan.style.flex = '1';
                                textSpan.style.overflow = 'hidden';
                                textSpan.style.textOverflow = 'ellipsis';
                                textSpan.style.whiteSpace = 'nowrap';

                                contentDiv.appendChild(textSpan);
                                item.appendChild(contentDiv);
                                menu.appendChild(item);
                            }
                        });

                        // 设置选中的值
                        const selectedValues = params.cat_id_list
                            .filter(cat => cat.cat_ids && cat.cat_ids.length > 0)
                            .map(cat => String(cat.cat_ids[cat.cat_ids.length - 1]));

                        dropdown.dropdown('refresh');
                        console.log('准备选中的值:', selectedValues);

                        // 手动设置选中状态
                        setTimeout(() => {
                            const menu = catDropdown.querySelector('.menu');
                            const allItems = menu.querySelectorAll('.item');
                            const selectedCatIdSet = new Set(selectedValues);

                            allItems.forEach(item => {
                                const itemValue = String($(item).data('value'));
                                if (selectedCatIdSet.has(itemValue)) {
                                    item.classList.add('selected');
                                } else {
                                    item.classList.remove('selected');
                                }
                            });

                            // 同时更新隐藏输入字段
                            const hiddenInput = catDropdown.querySelector('input[type="hidden"]');
                            if (hiddenInput) {
                                hiddenInput.value = selectedValues.join(',');
                            }

                            console.log('期望类目已选中:', selectedValues);
                        }, 300);
                    }
                }
                if (params.exceptReceiveAreaConfigType) {
                    const targetRadio = document.querySelector(`input[name="expectedArea"][value="${params.exceptReceiveAreaConfigType}"]`);
                    if (targetRadio) {
                        targetRadio.checked = true;
                    }
                }
            }
        }

        else if (taskName.includes('批量加入发货台') || task.func_name === 'purchase_delivery') {
            if (params) {
                if (params.max_cycles) {
                    const maxCyclesEl = document.getElementById('inputMaxCycles');
                    if (maxCyclesEl) {
                        maxCyclesEl.value = params.max_cycles;
                    }
                }
                if (params.custom_fixed_upload_img !== undefined) {
                    const el = document.getElementById('customFixedUploadImg');
                    if (el) {
                        el.checked = params.custom_fixed_upload_img;
                        if (typeof $ !== 'undefined' && $.fn && $('#customFixedUploadImgCheckbox').length) {
                            $('#customFixedUploadImgCheckbox').checkbox(params.custom_fixed_upload_img ? 'set checked' : 'set unchecked');
                        }
                    }
                }
                if (params.skip_upload_pic !== undefined) {
                    const el = document.getElementById('skipUploadPic');
                    if (el) {
                        el.checked = params.skip_upload_pic;
                        if (typeof $ !== 'undefined' && $.fn && $('#skipUploadPicCheckbox').length) {
                            $('#skipUploadPicCheckbox').checkbox(params.skip_upload_pic ? 'set checked' : 'set unchecked');
                        }
                    }
                }
            }
        }
        
        // 填充财务任务参数
        else if (taskName.includes('财务') || task.func_name?.startsWith('financial_') ||
                 taskName.includes('导出所选月份账单') || taskName.includes('导出月份账单') ||
                 taskName.includes('融合所选月份账单') || taskName.includes('融合月份账单') ||
                 taskName.includes('记录所需列到总表') || taskName.includes('记录到总表') ||
                 taskName.includes('计算并生成财务报表') ||
                 taskName.includes('生成SKU汇总表') ||
                 funcName.includes('download_export_excel_wrapper') ||
                 funcName.includes('merge_all_months_excel_wrapper') ||
                 funcName.includes('record_all_need_colum_to_excel_wrapper') ||
                 funcName.includes('make_caiwu_excel_wrapper') ||
                 funcName.includes('sku_summary_wrapper')) {
            if (params) {
                if (params.months_list && params.months_list.length > 0) {
                    _selectedMonths = new Set(params.months_list);
                    const firstMonth = params.months_list[0];
                    const year = parseInt(firstMonth.split('.')[0]);
                    if (!isNaN(year)) {
                        _currentPickerYear = year;
                    }
                    // 延迟渲染，确保DOM已加载
                    setTimeout(() => {
                        renderMonthPicker();
                    }, 150);
                }
            }
        }
        
        // 填充店铺选择（非虎扑任务、非财务任务且非编辑模式）
        if (taskName && !taskName.includes('虎扑') && !taskName.includes('财务') && 
            task.func_name && !task.func_name.startsWith('hupu_') && !isEdit) {
            if (task.uid) {
                setTimeout(() => {
                    const shopCheckbox = document.querySelector(`#shopSelectionArea input[type="checkbox"][data-shop*="${task.uid}"]`);
                    if (shopCheckbox) {
                        shopCheckbox.checked = true;
                    }
                }, 200);
            }
        }
        
        // 填充通用参数（守护任务、登录参数等）
        fillCommonTaskParams(task, params);
        
    } catch (error) {
        console.error('填充任务参数失败:', error);
        showError('填充任务参数失败：' + error.message);
    }
}

function fillCommonTaskParams(task, params) {
    try {
        // 填充守护任务参数
        const isMaintainTaskCheckbox = document.getElementById('isMaintainTask');
        if (isMaintainTaskCheckbox) {
            const isMaintainTask = task.is_maintain_task === 1 || task.is_maintain_task === true || task.is_maintain_task === '1';
            isMaintainTaskCheckbox.checked = isMaintainTask;
            if ($('#isMaintainTaskCheckbox').length) {
                $('#isMaintainTaskCheckbox').checkbox(isMaintainTask ? 'set checked' : 'set unchecked');
            }
        }
        
        // 填充登录参数（所有任务类型，除了虎扑任务）
        const taskName = task.task_name || task.task_group || '';
        const funcName = task.func_name || '';
        const isNotHupuTask = !taskName.includes('虎扑') && !funcName.startsWith('hupu_');
        
        if (isNotHupuTask) {
            // 填充登录类型
            const loginTypeSelect = document.getElementById('loginTypeSelect');
            if (loginTypeSelect && params.login_type) {
                loginTypeSelect.value = params.login_type;
                // 触发change事件以更新UI状态
                const event = new Event('change');
                loginTypeSelect.dispatchEvent(event);
            }
            
            // 填充显示浏览器（headless）
            const headlessCheckbox = document.getElementById('headless');
            if (headlessCheckbox && params.headless !== undefined) {
                headlessCheckbox.checked = !params.headless;
                if ($('#headlessCheckbox').length) {
                    $('#headlessCheckbox').checkbox(!params.headless ? 'set checked' : 'set unchecked');
                }
            }
            
            // 填充强制重新登录（reload_cookies）
            const reloadCookiesCheckbox = document.getElementById('reloadCookies');
            if (reloadCookiesCheckbox && params.reload_cookies !== undefined) {
                reloadCookiesCheckbox.checked = params.reload_cookies;
                if ($('#reloadCookiesCheckbox').length) {
                    $('#reloadCookiesCheckbox').checkbox(params.reload_cookies ? 'set checked' : 'set unchecked');
                }
            }
            
            // 填充是否持续显示ikun浏览器（ikun_persist_browser / auto_close）
            const ikunPersistBrowserCheckbox = document.getElementById('ikunPersistBrowser');
            if (ikunPersistBrowserCheckbox) {
                // 兼容两种参数名：ikun_persist_browser 或 auto_close
                const persistBrowser = params.ikun_persist_browser !== undefined ? params.ikun_persist_browser : !params.auto_close;
                ikunPersistBrowserCheckbox.checked = persistBrowser;
                if ($('#ikunPersistBrowserCheckbox').length) {
                    $('#ikunPersistBrowserCheckbox').checkbox(persistBrowser ? 'set checked' : 'set unchecked');
                }
            }
        }
        
    } catch (error) {
        console.error('填充通用任务参数失败:', error);
    }
}

async function deleteTask(taskId) {
    if (!taskId) {
        showError('删除失败：任务ID缺失');
        return;
    }

    // 二次确认
    try {
        await openConfirmModal(`确认删除该任务吗？此操作不可恢复，将永久删除任务记录。`);
    } catch (error) {
        if (error && error.message !== '用户取消操作') {
            showError('删除失败：' + (error.message || '未知错误'));
        }
        // 用户取消或出错都不继续调用接口
        return;
    }

    try {
        const result = await requestPost('/api/delete_task', {}, { task_id_list: [taskId] });
        if (result && result.success) {
            showSuccess(result.msg || result.message || '任务删除成功');
            // 删除成功后刷新任务列表
            loadTasks();
        } else {
            const errorMsg = (result && (result.error_msg || result.message)) || '未知错误';
            showError(`删除失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`删除失败：${error.message || '请求异常'} `);
    }
}

// 兼容后端返回的 all_task_id_list 结构（可能是 ["id1"] 或 [{"task_id":"id1"}]）
function normalizeAllTaskIdList(allTaskIdList) {
    if (!Array.isArray(allTaskIdList)) return [];
    const ids = [];
    for (const item of allTaskIdList) {
        if (!item) continue;
        if (typeof item === 'string') {
            const s = item.trim();
            if (s) ids.push(s);
            continue;
        }
        // sqlite3.Row / dict / object
        const taskId = (item.task_id || item.taskId || item.id || '').toString().trim();
        if (taskId) ids.push(taskId);
    }
    // 去重
    return Array.from(new Set(ids));
}

// 一键清空所有任务（复用删除任务接口）
async function clearAllTasks() {
    // 二次确认
    try {
        await openConfirmModal('确认清空所有任务吗？此操作不可恢复，将永久删除所有任务记录（但不会停止运行中的子任务，需要手动停止）。');
    } catch (error) {
        if (error && error.message !== '用户取消操作') {
            showError('清空失败：' + (error.message || '未知错误'));
        }
        return;
    }

    try {
        // 优先使用缓存；如果没有缓存，则请求一次任务接口拿 all_task_id_list
        let allIds = normalizeAllTaskIdList(window.__allTaskIdListCache);
        if (!allIds || allIds.length === 0) {
            const fetchResult = await requestPost('/api/get_tasks', {}, { page: 1, page_size: 1 });
            if (fetchResult && fetchResult.success) {
                allIds = normalizeAllTaskIdList(fetchResult.all_task_id_list);
                window.__allTaskIdListCache = allIds;
            }
        }

        if (!allIds || allIds.length === 0) {
            showError('暂无任务可清空');
            return;
        }

        const result = await requestPost('/api/delete_task', {}, { task_id_list: allIds });
        if (result && result.success) {
            showSuccess(result.msg || result.message || `已清空 ${allIds.length} 个任务`);
            // 清空缓存并刷新列表/计数
            window.__allTaskIdListCache = [];
            loadTasks();
            if (typeof loadTaskCount === 'function') {
                loadTaskCount();
            }
        } else {
            const errorMsg = (result && (result.error_msg || result.message)) || '未知错误';
            showError(`清空失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`清空失败：${error.message || '请求异常'} `);
    }
}

// 获取所有选中的任务ID
function getSelectedTaskIds() {
    const checkboxes = document.querySelectorAll('.task-checkbox:checked');
    const taskIds = [];
    checkboxes.forEach(checkbox => {
        const taskId = checkbox.getAttribute('data-task-id');
        if (taskId) {
            taskIds.push(taskId);
        }
    });
    return taskIds;
}

// 全选/取消全选
function toggleSelectAllTasks(selectAllElement) {
    const checkboxes = document.querySelectorAll('.task-checkbox');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);

    // 如果全部选中，则取消全选；否则全选
    const shouldSelectAll = !allChecked;
    checkboxes.forEach(checkbox => {
        checkbox.checked = shouldSelectAll;
    });

    // 更新篮球样式
    updateBasketballStyle(selectAllElement, shouldSelectAll);

    updateBatchActionsVisibility();
}

// 更新篮球样式
function updateBasketballStyle(element, isSelected) {
    if (isSelected) {
        element.textContent = '🏀';
        element.style.opacity = '1';
        element.style.transform = 'scale(1.2)';
    } else {
        element.textContent = '🏀';
        element.style.opacity = '0.5';
        element.style.transform = 'scale(1)';
    }
}

// 更新批量操作按钮的显示状态
function updateBatchActionsVisibility() {
    const batchActions = document.getElementById('batchActions');

    // 始终显示批量操作按钮
    if (batchActions) {
        batchActions.style.display = 'flex';
        batchActions.style.alignItems = 'center';
        batchActions.style.gap = '10px';
    }

    // 更新全选篮球的状态
    const selectAllElement = document.getElementById('selectAllTasks');
    if (selectAllElement) {
        const allCheckboxes = document.querySelectorAll('.task-checkbox');
        const checkedCount = document.querySelectorAll('.task-checkbox:checked').length;

        if (allCheckboxes.length === 0) {
            // 全部未选
            selectAllElement.textContent = '🏀';
            selectAllElement.style.opacity = '0.5';
            selectAllElement.style.transform = 'scale(1)';
        } else if (checkedCount === allCheckboxes.length) {
            // 全部选中（全选）
            selectAllElement.textContent = '🏀';
            selectAllElement.style.opacity = '1';
            selectAllElement.style.transform = 'scale(1.2)';
        } else if (checkedCount > 0) {
            // 部分选中（半选）
            selectAllElement.textContent = '🐔';
            selectAllElement.style.opacity = '1';
            selectAllElement.style.transform = 'scale(1.1)';
        } else {
            // 全部未选
            selectAllElement.textContent = '🏀';
            selectAllElement.style.opacity = '0.5';
            selectAllElement.style.transform = 'scale(1)';
        }
    }
}

// 添加守护任务（多选，传 main_task_id_list）
async function addMaintainTasks() {
    const main_task_id_list = getSelectedTaskIds();
    if (!main_task_id_list || main_task_id_list.length === 0) {
        showWarning('请先选择要设为守护任务的任务');
        return;
    }

    // 关闭批量操作弹窗
    closeBatchActionsModal();

    try {
        const result = await requestPost('/api/add_maintain_task', {}, { main_task_id_list });
        if (result && result.success) {
            showSuccess(result.message || '已添加守护任务');
            if (typeof loadTasks === 'function') loadTasks();
            if (typeof loadTaskCount === 'function') loadTaskCount();
        } else {
            showError(result?.error_msg || result?.message || '添加守护任务失败');
        }
    } catch (error) {
        showError('添加守护任务失败：' + (error.message || '请求异常'));
    }
}

// 删除守护任务（多选，传 main_task_id_list）
async function delMaintainTasks() {
    const main_task_id_list = getSelectedTaskIds();
    if (!main_task_id_list || main_task_id_list.length === 0) {
        showWarning('请先选择要取消守护的任务');
        return;
    }

    // 关闭批量操作弹窗
    closeBatchActionsModal();

    try {
        const result = await requestPost('/api/del_maintain_task', {}, { main_task_id_list });
        if (result && result.success) {
            showSuccess(result.message || '已删除守护任务');
            if (typeof loadTasks === 'function') loadTasks();
            if (typeof loadTaskCount === 'function') loadTaskCount();
        } else {
            showError(result?.error_msg || result?.message || '删除守护任务失败');
        }
    } catch (error) {
        showError('删除守护任务失败：' + (error.message || '请求异常'));
    }
}

// 清空任务日志（多选，只清空选中任务的日志）
async function clearTaskLogs() {
    const taskIds = getSelectedTaskIds();
    if (!taskIds || taskIds.length === 0) {
        showWarning('请先选择要清空日志的任务');
        return;
    }

    // 关闭批量操作弹窗
    closeBatchActionsModal();

    // 二次确认
    try {
        await openConfirmModal(`确认清空选中的 ${taskIds.length} 个任务的所有日志吗？此操作不可恢复！`);
    } catch (error) {
        if (error && error.message !== '用户取消操作') {
            showError('操作已取消');
        }
        return;
    }

    try {
        const result = await requestPost('/api/clear_task_logs', {}, { task_id_list: taskIds });
        if (result && result.success) {
            showSuccess(result.message || `成功清空 ${taskIds.length} 个任务的日志`);
            if (typeof loadTasks === 'function') loadTasks();
        } else {
            showError(result?.error_msg || result?.message || '清空任务日志失败');
        }
    } catch (error) {
        showError('清空任务日志失败：' + (error.message || '请求异常'));
    }
}

// 批量重跑任务
async function batchRerunTasks() {
    const taskIds = getSelectedTaskIds();
    if (taskIds.length === 0) {
        showError('请先选择要重跑的任务');
        return;
    }

    // 关闭批量操作弹窗
    closeBatchActionsModal();

    // 二次确认
    try {
        await openConfirmModal(`确认重跑选中的 ${taskIds.length} 个任务吗？重跑会检测是否运行并先执行停止再开始重跑`);
    } catch (error) {
        if (error && error.message !== '用户取消操作') {
            showError('批量重跑失败：' + (error.message || '未知错误'));
        }
        return;
    }

    try {
        let successCount = 0;
        let failCount = 0;
        const errors = [];

        // 逐个调用重跑接口
        for (const taskId of taskIds) {
            try {
                const result = await requestPost('/api/re_run_task', {}, { task_id: taskId });
                if (result && result.success) {
                    successCount++;
                } else {
                    failCount++;
                    errors.push(`${taskId}: ${result?.error_msg || result?.message || '未知错误'} `);
                }
            } catch (error) {
                failCount++;
                errors.push(`${taskId}: ${error.message || '请求异常'} `);
            }
        }

        if (successCount > 0) {
            showSuccess(`批量重跑完成：成功 ${successCount} 个，失败 ${failCount} 个`);
            if (failCount > 0 && errors.length > 0) {
                console.error('批量重跑失败详情:', errors);
            }
            // 刷新任务列表
            loadTasks();
        } else {
            showError(`批量重跑失败：所有任务都重跑失败`);
            if (errors.length > 0) {
                console.error('批量重跑失败详情:', errors);
            }
        }
    } catch (error) {
        showError(`批量重跑失败：${error.message || '请求异常'} `);
    }
}

// 批量停止任务
async function batchStopTasks() {
    const taskIds = getSelectedTaskIds();
    if (taskIds.length === 0) {
        showError('请先选择要停止的任务');
        return;
    }

    // 关闭批量操作弹窗
    closeBatchActionsModal();

    // 二次确认
    try {
        await openConfirmModal(`确认停止选中的 ${taskIds.length} 个任务吗？`);
    } catch (error) {
        if (error && error.message !== '用户取消操作') {
            showError('批量停止失败：' + (error.message || '未知错误'));
        }
        return;
    }

    try {
        let successCount = 0;
        let failCount = 0;
        const errors = [];

        // 逐个调用停止接口
        for (const taskId of taskIds) {
            try {
                const result = await requestPost('/api/stop_task', {}, { task_id: taskId });
                if (result && result.success) {
                    successCount++;
                } else {
                    failCount++;
                    errors.push(`${taskId}: ${result?.error_msg || result?.message || '未知错误'} `);
                }
            } catch (error) {
                failCount++;
                errors.push(`${taskId}: ${error.message || '请求异常'} `);
            }
        }

        if (successCount > 0) {
            showSuccess(`批量停止完成：成功 ${successCount} 个，失败 ${failCount} 个`);
            if (failCount > 0 && errors.length > 0) {
                console.error('批量停止失败详情:', errors);
            }
            // 刷新任务列表
            loadTasks();
        } else {
            showError(`批量停止失败：所有任务都停止失败`);
            if (errors.length > 0) {
                console.error('批量停止失败详情:', errors);
            }
        }
    } catch (error) {
        showError(`批量停止失败：${error.message || '请求异常'} `);
    }
}

// 批量删除任务
async function batchDeleteTasks() {
    const taskIds = getSelectedTaskIds();
    if (taskIds.length === 0) {
        showError('请先选择要删除的任务');
        return;
    }

    // 关闭批量操作弹窗
    closeBatchActionsModal();

    // 二次确认
    try {
        await openConfirmModal(`确认删除选中的 ${taskIds.length} 个任务吗？此操作不可恢复，将永久删除任务记录。`);
    } catch (error) {
        if (error && error.message !== '用户取消操作') {
            showError('批量删除失败：' + (error.message || '未知错误'));
        }
        return;
    }

    try {
        // 批量删除接口已经支持多选
        const result = await requestPost('/api/delete_task', {}, { task_id_list: taskIds });
        if (result && result.success) {
            showSuccess(result.msg || result.message || `成功删除 ${taskIds.length} 个任务`);
            // 删除成功后刷新任务列表
            loadTasks();
        } else {
            const errorMsg = (result && (result.error_msg || result.message)) || '未知错误';
            showError(`批量删除失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`批量删除失败：${error.message || '请求异常'} `);
    }
}

// 批量添加定时任务
async function batchAddScheduledTasks() {
    const taskIds = getSelectedTaskIds();
    if (taskIds.length === 0) {
        showError('请先选择要添加定时任务的任务');
        return;
    }

    // 关闭批量操作弹窗
    closeBatchActionsModal();

    // 打开定时任务配置弹窗
    openScheduledTaskModal(taskIds);
}

// 批量删除定时任务
async function batchRemoveScheduledTasks() {
    const taskIds = getSelectedTaskIds();
    if (taskIds.length === 0) {
        showError('请先选择要关闭定时任务的任务');
        return;
    }

    // 关闭批量操作弹窗
    closeBatchActionsModal();

    // 二次确认
    try {
        await openConfirmModal(`确认关闭选中的 ${taskIds.length} 个任务的定时任务吗？`);
    } catch (error) {
        if (error && error.message !== '用户取消操作') {
            showError('批量关闭定时任务失败：' + (error.message || '未知错误'));
        }
        return;
    }

    try {
        let successCount = 0;
        for (const taskId of taskIds) {
            const result = await requestPost('/api/delete_schedule_task', {}, { task_id: taskId });
            if (result && result.success) {
                successCount++;
            }
        }

        if (successCount > 0) {
            showSuccess(`成功关闭 ${successCount} 个任务的定时任务`);
            loadTasks();
        } else {
            showError('关闭定时任务失败');
        }
    } catch (error) {
        showError(`批量关闭定时任务失败：${error.message || '请求异常'} `);
    }
}

// 打开定时任务配置弹窗
function openScheduledTaskModal(taskIds) {
    const modal = document.getElementById('scheduledTaskModal');
    if (!modal) {
        console.error('scheduledTaskModal 元素不存在');
        return;
    }

    // 保存任务ID到弹窗
    modal.dataset.taskIds = JSON.stringify(taskIds);

    // 获取当前时间（HH:MM格式）
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const currentTime = `${hours}:${minutes}`;

    // 初始化默认值
    document.getElementById('scheduleType').value = 'once';
    document.getElementById('scheduleTime').value = currentTime;
    document.getElementById('scheduleInterval').value = 30;
    document.getElementById('executeImmediately').checked = false;

    // 显示对应的字段
    updateScheduleFields();

    // 初始化 Semantic UI 组件
    if (typeof $ !== 'undefined' && $.fn) {
        $('#scheduleType').dropdown();
        $('.ui.checkbox').checkbox();
    }

    // 打开弹窗
    if (typeof $ !== 'undefined' && $.fn) {
        $(modal).modal('show');
    } else {
        modal.style.display = 'block';
    }
}

// 关闭定时任务配置弹窗
function closeScheduledTaskModal() {
    const modal = document.getElementById('scheduledTaskModal');
    if (!modal) {
        console.error('scheduledTaskModal 元素不存在');
        return;
    }

    if (typeof $ !== 'undefined' && $.fn) {
        $(modal).modal('hide');
    } else {
        modal.style.display = 'none';
    }
}

// 打开批量操作弹窗
function showBatchActionsModal() {
    const selectedCheckboxes = document.querySelectorAll('.task-checkbox:checked');
    if (selectedCheckboxes.length === 0) {
        showWarning('请先选择要操作的任务！');
        return;
    }

    const modal = document.getElementById('batchActionsModal');
    if (modal) {
        $(modal).modal({
            closable: true,
            onApprove: function() {
                // 点击遮罩层关闭
            },
            onDeny: function() {
                // 点击取消按钮关闭
            }
        }).modal('show');
    }
}

// 关闭批量操作弹窗
function closeBatchActionsModal() {
    const modal = document.getElementById('batchActionsModal');
    if (modal) {
        $(modal).modal('hide');
    }
}

// 更新定时任务字段显示
function updateScheduleFields() {
    const scheduleType = document.getElementById('scheduleType').value;
    const scheduleTimeField = document.getElementById('scheduleTimeField');
    const scheduleIntervalField = document.getElementById('scheduleIntervalField');
    const scheduleTimeInput = document.getElementById('scheduleTime');

    if (scheduleType === 'once') {
        scheduleTimeField.style.display = 'block';
        scheduleIntervalField.style.display = 'none';
        
        // 设置默认时间为当前时间
        if (!scheduleTimeInput.value) {
            const now = new Date();
            const hours = String(now.getHours()).padStart(2, '0');
            const minutes = String(now.getMinutes()).padStart(2, '0');
            scheduleTimeInput.value = `${hours}:${minutes}`;
        }
    } else if (scheduleType === 'interval') {
        scheduleTimeField.style.display = 'none';
        scheduleIntervalField.style.display = 'block';
    }
}

// 提交定时任务配置
async function submitScheduledTask() {
    const modal = document.getElementById('scheduledTaskModal');
    if (!modal) {
        console.error('scheduledTaskModal 元素不存在');
        return;
    }

    const taskIds = JSON.parse(modal.dataset.taskIds || '[]');
    if (taskIds.length === 0) {
        showError('没有选择任务');
        return;
    }

    const scheduleType = document.getElementById('scheduleType').value;
    const scheduleTime = document.getElementById('scheduleTime').value;
    const scheduleInterval = parseInt(document.getElementById('scheduleInterval').value) || 30;
    const executeImmediately = document.getElementById('executeImmediately').checked;

    // 验证
    if (scheduleType === 'once' && !scheduleTime) {
        showError('请选择执行时间');
        return;
    }

    if (scheduleType === 'interval' && scheduleInterval < 1) {
        showError('执行间隔必须大于0分钟');
        return;
    }

    try {
        let successCount = 0;
        for (const taskId of taskIds) {
            const requestData = {
                task_id: taskId,
                schedule_enabled: true,
                schedule_type: scheduleType,
                execute_immediately: executeImmediately
            };

            if (scheduleType === 'once') {
                requestData.schedule_time = scheduleTime;
            } else if (scheduleType === 'interval') {
                requestData.schedule_interval = scheduleInterval;
            }

            const result = await requestPost('/api/add_schedule_task', {}, requestData);
            if (result && result.success) {
                successCount++;
            }
        }

        if (successCount > 0) {
            showSuccess(`成功为 ${successCount} 个任务添加定时任务`);
            closeScheduledTaskModal();
            loadTasks();
        } else {
            showError('添加定时任务失败');
        }
    } catch (error) {
        showError(`添加定时任务失败：${error.message || '请求异常'} `);
    }
}

// 店铺列表加载/搜索/分页
async function loadShopList(page = 1, keyword = "", sortField = "id", sortOrder = "asc") {
    const container = document.getElementById('shopList');
    const pagination = document.getElementById('shopPagination');
    container.innerHTML = '<p>正在加载店铺列表...</p>';
    try {
        const result = await requestGet('/api/page', {
            page: page,
            page_size: 10,
            keyword: keyword,
            sort_field: sortField,
            sort_order: sortOrder
        });
        // 缓存店铺数据（用于任务管理的下拉框）
        if (result.success && result.data.length > 0) {
            // 在店铺管理页面加载时，总是获取并缓存所有店铺数据
            if (page === 1 && !keyword) {
                // 异步获取所有店铺数据用于缓存（不阻塞当前显示）
                requestGet('/api/page', {
                    page: 1,
                    page_size: 100,
                    keyword: ""
                }).then(allShopsResult => {
                    if (allShopsResult && allShopsResult.success && allShopsResult.data.length > 0) {
                        cachedShopList = allShopsResult.data;
                        // 更新任务管理的店铺下拉选项
                        updateShopAbbrDropdown();
                    }
                }).catch(err => {
                    console.error('缓存店铺数据失败:', err);
                });
            }
            // 转义函数，防止XSS和特殊字符问题
            const escapeHtml = (str) => {
                if (!str) return '';
                return String(str)
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
            };

            const escapeJs = (str) => {
                if (!str) return '';
                return String(str)
                    .replace(/\\/g, '\\\\')
                    .replace(/'/g, "\\'")
                    .replace(/"/g, '\\"')
                    .replace(/\n/g, '\\n')
                    .replace(/\r/g, '\\r');
            };

            let html = `
    <div class="shop-list-table">
                    <div class="shop-list-header">
                        <div class="shop-col name">店铺名称</div>
                        <div class="shop-col abbr">店铺缩写</div>
                        <div class="shop-col id">Browser ID</div>
                        <div class="shop-col phone">手机号</div>
                        <div class="shop-col password">密码</div>
                        <div class="shop-col status">连接状态</div>
                        <div class="shop-col auth-status">检测连接状态</div>
                        <div class="shop-col action">操作</div>
                    </div>
                    <div class="shop-list-body">
            `;
            for (const shop of result.data) {
                // 后端应返回uid作为店铺唯一标识
                const uid = escapeJs(shop.uid || '');
                const isConnected = await checkShopConnectionStatus(uid);
                const statusText = isConnected ? '已连接' : '未连接';
                const statusClass = isConnected ? 'connected' : 'disconnected';
                // 店铺管理部分：统一使用“连接”按钮样式，不展示“断开”样式
                const btnText = '连接';
                const btnClass = 'btn-success';

                const shopName = escapeJs(shop['店铺名称'] || '');
                const shopAbbr = escapeJs(shop['店铺缩写'] || '');
                const browserId = escapeJs(shop.browser_id || '');
                // 后端可能不返回phone和password字段，使用可选链安全获取
                const shopPhone = escapeJs((shop.phone || '') || '');
                const shopPassword = escapeJs((shop.password || '') || '');

                // 密码显示：明文显示密码
                const passwordDisplay = shop['password'] || shopPassword || '-';

                html += `
                    <div class="shop-item-row">
                        <div class="shop-col name">${escapeHtml(shop['店铺名称'] || '-')}</div>
                        <div class="shop-col abbr">${escapeHtml(shop['店铺缩写'] || '-')}</div>
                        <div class="shop-col id">${escapeHtml(shop.browser_id || '-')}</div>
                        <div class="shop-col phone">${escapeHtml(shop.phone || shopPhone || '-')}</div>
                        <div class="shop-col password">${escapeHtml(passwordDisplay)}</div>
                        <div class="shop-col status">
                            <span class="status-badge ${statusClass}">${statusText}</span>
                        </div>
                        <div class="shop-col auth-status">
                            <button class="btn btn-outline btn-sm" onclick="triggerShopAuthCheck('${uid}', this)" title="检测店铺连接状态">
                                <i class="fas fa-shield-alt"></i> 检测
                            </button>
                        </div>
                        <div class="shop-col action">
                            <div class="action-buttons">
                                <button class="btn ${btnClass} btn-sm" onclick="openConnectConfigModal('${uid}', '${shopName}')">${btnText}</button>
                                <button class="btn btn-primary btn-sm" onclick="openModifyShopModal('${uid}', '${browserId}', '${shopName}', '${shopAbbr}', '${shopPhone}', '${shopPassword}')">
                                    <i class="fas fa-edit"></i> 修改
                                </button>
                                <button class="btn btn-danger btn-sm" onclick="deleteShop('${uid}', '${browserId}')">
                                    <i class="fas fa-trash"></i> 删除
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            }
            html += `
                    </div>
                </div>
    `;
            container.innerHTML = html;
            updatePaginationControls(pagination, result.pagination);
            currentPage = result.pagination.page;
            totalPages = result.pagination.total_pages;
        } else {
            // 检查是否是第一页且没有搜索关键词，如果是则提示添加店铺
            if (page === 1 && !keyword) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 40px 20px;">
                        <i class="fas fa-store-slash" style="font-size: 48px; color: #999; margin-bottom: 20px;"></i>
                        <p style="color: #666; font-size: 16px; margin-bottom: 15px;">暂无店铺数据</p>
                        <button class="ui green button" onclick="openAddShopModalNew()">
                            <i class="plus icon"></i> 添加新店铺
                        </button>
                    </div>
                `;
            } else {
                container.innerHTML = '<p>暂无店铺数据</p>';
            }
        }
    } catch (error) {
        console.error('加载店铺列表异常:', error);
        // 检查是否是真正的加载失败（网络错误等）还是数据库为空
        const errorMessage = error.message || '';
        if (errorMessage.includes('Failed to fetch') || errorMessage.includes('NetworkError')) {
            container.innerHTML = `<p style="color: red;">加载店铺列表失败: 网络连接异常，请检查服务器状态</p>`;
        } else {
            container.innerHTML = `<p style="color: red;">加载店铺列表失败: ${errorMessage}</p>`;
        }
    }
}


function searchShops() {
    const keyword = document.getElementById('shopSearchInput')?.value.trim() || "";
    loadShopList(1, keyword);
}

// 处理添加类目逻辑
function handleExpectedCategoryAdd() {
    const addCategoryCheckbox = document.getElementById('inputExpectedAddCategory');
    const categoryResultDropdown = document.getElementById('expectedCategoryResultDropdown');
    
    if (addCategoryCheckbox && addCategoryCheckbox.checked && categoryResultDropdown) {
        // 从下拉框获取选中的值
        const selectedValues = $(categoryResultDropdown).dropdown('get value');
        const resultValue = Array.isArray(selectedValues) ? selectedValues.join(',') : (selectedValues || '');
        
        if (resultValue) {
            // 将搜索结果添加到类目下拉框
            const catDropdown = document.getElementById('expectedCatIdDropdown');
            if (catDropdown) {
                // 从下拉框的选项中查找对应的类目ID
                const menuItems = $(catDropdown).find('.menu .item');
                const newValues = [];
                
                // 遍历选中的值
                const valuesArray = Array.isArray(selectedValues) ? selectedValues : [selectedValues];
                for (const value of valuesArray) {
                    // 从下拉框选项中查找匹配的项
                    for (const item of menuItems) {
                        const itemValue = $(item).data('value');
                        if (itemValue == value) {
                            if (value && !newValues.includes(value)) {
                                newValues.push(value);
                            }
                            break;
                        }
                    }
                }
                
                const currentValues = $(catDropdown).dropdown('get value') || [];
                const updatedValues = [...currentValues, ...newValues];
                $(catDropdown).dropdown('set value', updatedValues);
                // 清空搜索结果下拉框
                $(categoryResultDropdown).dropdown('clear');
            }
        }
    }
}

// 确认添加类目
async function confirmAddExpectedCategory() {
    const resultDropdown = document.getElementById('expectedCategoryResultDropdown');
    const resultInput = document.getElementById('inputExpectedCategoryResult');

    console.log('confirmAddExpectedCategory 被调用');
    console.log('resultDropdown:', resultDropdown);
    console.log('resultInput:', resultInput);

    if (resultDropdown && resultInput) {
        const selectedValues = $(resultDropdown).dropdown('get value');
        console.log('selectedValues:', selectedValues);
        
        // 确保 selectedValues 是数组（处理字符串 "1831,1693" 的情况）
        let selectedValuesArray;
        if (Array.isArray(selectedValues)) {
            selectedValuesArray = selectedValues;
        } else if (typeof selectedValues === 'string' && selectedValues) {
            selectedValuesArray = selectedValues.split(',').map(v => v.trim()).filter(v => v);
        } else {
            selectedValuesArray = [];
        }
        
        const resultValue = selectedValuesArray.join(',');
        console.log('resultValue:', resultValue);

        if (resultValue) {
            const catDropdown = document.getElementById('expectedCatIdDropdown');
            if (catDropdown) {
                const menu = catDropdown.querySelector('.menu');
                const newValues = [];

                // 获取当前已选中的值
                const currentValues = $(catDropdown).dropdown('get value') || [];
                const currentValuesArray = Array.isArray(currentValues) ? currentValues : [currentValues];
                currentValuesArray.forEach(v => {
                    if (v && !newValues.includes(v)) {
                        newValues.push(v);
                    }
                });

                // 获取搜索结果列表（从下拉框选项）
                const searchResults = [];
                const resultMenuItems = resultDropdown.querySelectorAll('.menu .item');
                resultMenuItems.forEach(item => {
                    const value = $(item).data('value');
                    const text = item.textContent;
                    const catIds = $(item).data('catIds');
                    const catNames = $(item).data('catNames');
                    
                    console.log('item data:', { value, catIds, catNames });
                    
                    if (value && catIds && catNames) {
                        try {
                            const parsedCatIds = typeof catIds === 'string' ? JSON.parse(catIds) : catIds;
                            const parsedCatNames = typeof catNames === 'string' ? JSON.parse(catNames) : catNames;
                            
                            searchResults.push({ 
                                cat_id: value, 
                                cat_name: text,
                                cat_ids: parsedCatIds,
                                cat_names: parsedCatNames
                            });
                        } catch (error) {
                            console.error('解析类目数据失败:', error, catIds, catNames);
                        }
                    }
                });

                console.log('searchResults:', searchResults);

                // 遍历选中的值
                const valuesArray = selectedValuesArray;
                console.log('valuesArray:', valuesArray);
                
                for (const value of valuesArray) {
                    // 在搜索结果中查找对应的项
                    const catPath = searchResults.find(r => String(r.cat_id) === String(value));
                    console.log('查找 value:', value, '找到 catPath:', catPath);

                    if (catPath) {
                        // 检查选项是否已存在于下拉框
                        let itemExists = false;
                        const existingItems = menu.querySelectorAll('.item');
                        for (const item of existingItems) {
                            if (String($(item).data('value')) === String(catPath.cat_id)) {
                                itemExists = true;
                                break;
                            }
                        }

                        // 如果选项不存在，动态添加
                        if (!itemExists) {
                            const newItem = document.createElement('div');
                            newItem.className = 'item';
                            newItem.dataset.value = catPath.cat_id;
                            newItem.dataset.catIds = JSON.stringify(catPath.cat_ids);
                            newItem.dataset.catNames = JSON.stringify(catPath.cat_names);
                            
                            // 创建内容容器
                            const contentDiv = document.createElement('div');
                            contentDiv.style.display = 'flex';
                            contentDiv.style.justifyContent = 'space-between';
                            contentDiv.style.alignItems = 'center';
                            contentDiv.style.width = '100%';
                            
                            // 类目名称：只显示子类目ID和子类目名
                            const textSpan = document.createElement('span');
                            const subCatName = catPath.cat_names && catPath.cat_names.length > 0 ? catPath.cat_names[catPath.cat_names.length - 1] : '';
                            textSpan.textContent = `${catPath.cat_id} ${subCatName}`;
                            textSpan.style.flex = '1';
                            textSpan.style.overflow = 'hidden';
                            textSpan.style.textOverflow = 'ellipsis';
                            textSpan.style.whiteSpace = 'nowrap';
                            
                            // 删除按钮（从数据库删除）- 使用 deleteBtn 类名区分
                            const deleteBtn = document.createElement('span');
                            deleteBtn.className = 'deleteBtn';
                            deleteBtn.innerHTML = '&times;';
                            deleteBtn.style.cursor = 'pointer';
                            deleteBtn.style.color = '#999';
                            deleteBtn.style.fontSize = '18px';
                            deleteBtn.style.marginLeft = '10px';
                            deleteBtn.style.padding = '0 5px';
                            deleteBtn.style.lineHeight = '1';
                            deleteBtn.title = '从数据库删除此类目';
                            
                            // 点击删除按钮时阻止事件冒泡
                            deleteBtn.addEventListener('click', async function(e) {
                                e.stopPropagation();
                                e.preventDefault();
                                e.stopImmediatePropagation();

                                const confirmed = await showConfirm(`确定要删除类目"${subCatName}"吗？`);
                                if (confirmed) {
                                    try {
                                        const result = await requestPost('/api/delete_saved_category', {}, { cat_id: catPath.cat_id });
                                        if (result.success) {
                                            // 从下拉框中移除该项
                                            newItem.remove();
                                            // 更新下拉框的值（如果该项已被选中）
                                            const currentValues = $(catDropdown).dropdown('get value') || [];
                                            const currentValuesArray = Array.isArray(currentValues) ? currentValues : (currentValues ? [String(currentValues)] : []);
                                            const newValues = currentValuesArray.filter(v => String(v) !== String(catPath.cat_id));
                                            $(catDropdown).dropdown('set value', newValues);
                                            showSuccess('删除成功');
                                        } else {
                                            showWarning(result.error_msg || '删除失败');
                                        }
                                    } catch (error) {
                                        console.error('删除类目失败:', error);
                                        showWarning('删除失败');
                                    }
                                }
                            });
                            
                            // 鼠标悬停效果
                            deleteBtn.addEventListener('mouseenter', function() {
                                deleteBtn.style.color = '#db2828';
                            });
                            deleteBtn.addEventListener('mouseleave', function() {
                                deleteBtn.style.color = '#999';
                            });
                            
                            contentDiv.appendChild(textSpan);
                            contentDiv.appendChild(deleteBtn);
                            newItem.appendChild(contentDiv);
                            menu.appendChild(newItem);
                        }

                        // 添加到新值列表
                        if (catPath.cat_id && !newValues.includes(String(catPath.cat_id))) {
                            newValues.push(String(catPath.cat_id));
                        }
                    }
                }

                // 保存选中的类目到数据库
                const selectedCategories = [];
                for (const value of valuesArray) {
                    const catPath = searchResults.find(r => String(r.cat_id) === String(value));
                    if (catPath) {
                        selectedCategories.push({
                            cat_ids: catPath.cat_ids || [Number(catPath.cat_id)],
                            cat_names: catPath.cat_names || [catPath.cat_name]
                        });
                    }
                }
                console.log('selectedCategories:', selectedCategories);
                
                if (selectedCategories.length > 0) {
                    try {
                        const result = await requestPost('/api/save_saved_category_list', {}, { category_list: selectedCategories });
                        if (result.success) {
                            showSuccess('类目添加成功');
                            // 保存成功后刷新类目列表
                            await loadSavedCategoryList();
                        } else {
                            showWarning(result.error_msg || '添加失败');
                        }
                        console.log('保存成功');
                    } catch (error) {
                        console.error('保存类目列表失败:', error);
                        showWarning('保存失败');
                    }
                }

                // 设置新的值
                if (newValues.length > 0) {
                    // 重新初始化下拉框以确保新添加的选项能被识别
                    $(catDropdown).dropdown('refresh');
                    $(catDropdown).dropdown('set value', newValues);
                }

                // 清空搜索结果
                resultInput.value = '';
                $(resultDropdown).dropdown('clear');

                console.log('添加完成，选中的类目:', newValues);
            }
        } else {
            showWarning('请先搜索类目');
        }
    }
}

// 搜索类目（根据勾选的第一个店铺的uid进行搜索）
async function searchExpectedCategory() {
    const searchInput = document.getElementById('inputExpectedCategorySearch');
    const resultInput = document.getElementById('inputExpectedCategoryResult');
    const statusText = document.getElementById('expectedCategorySearchStatus');
    
    if (searchInput && resultInput) {
        const keyword = searchInput.value.trim();
        if (!keyword) {
            resultInput.value = '';
            return;
        }
        
        if (statusText) {
            statusText.textContent = '登录中...';
            statusText.style.color = '#21ba45';
        }
        
        try {
            // 获取勾选的第一个店铺的uid
            const shopCheckboxes = document.querySelectorAll('#shopSelectionArea input[type="checkbox"]:checked');
            if (shopCheckboxes.length === 0) {
                resultInput.value = '请先勾选店铺进行搜索';
                if (statusText) {
                    statusText.textContent = '请先勾选店铺进行搜索';
                    statusText.style.color = '#f2711c';
                }
                return;
            }
            
            const firstShop = JSON.parse(shopCheckboxes[0].dataset.shop);
            const uid = firstShop.uid;
            
            // 1. 调用后端API启动异步登录任务
            const startResult = await requestPost('/api/search_category', {}, {
                uid: uid,
                keyword: keyword
            });
            
            if (!startResult.success || !startResult.task_id) {
                if (statusText) {
                    statusText.textContent = startResult.error_msg || '启动任务失败';
                    statusText.style.color = '#db2828';
                }
                return;
            }
            
            const task_id = startResult.task_id;
            
            // 2. 轮询获取任务结果
            let pollResult;
            let pollCount = 0;
            const maxPollCount = 120; // 最多轮询120次，每次1秒
            
            while (pollCount < maxPollCount) {
                pollResult = await requestPost('/api/get_search_category_result', {}, {
                    task_id: task_id,
                    uid: uid,
                    keyword: keyword
                });
                
                if (pollResult.status === 'success') {
                    break;
                } else if (pollResult.status === 'failed') {
                    if (statusText) {
                        statusText.textContent = pollResult.error_msg || '登录或搜索失败';
                        statusText.style.color = '#db2828';
                    }
                    return;
                } else if (pollResult.status === 'timeout') {
                    if (statusText) {
                        statusText.textContent = '任务超时';
                        statusText.style.color = '#db2828';
                    }
                    return;
                }
                
                pollCount++;
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
            
            if (pollResult && pollResult.success && pollResult.data) {
                // 填充搜索结果到下拉框
                const catPaths = pollResult.data;
                const resultDropdown = document.getElementById('expectedCategoryResultDropdown');

                if (resultDropdown) {
                    // 清空下拉框选项
                    const menu = resultDropdown.querySelector('.menu');
                    menu.innerHTML = '';
                    
                    // 添加新的选项
                    catPaths.forEach((path, index) => {
                        const catNames = path.cat_names || [];
                        const catIds = path.cat_ids || [];
                        
                        // 构建显示文本：类目路径
                        const displayText = catNames.join(' > ');
                        // 使用最后一个类目ID作为值
                        const lastCatId = catIds.length > 0 ? catIds[catIds.length - 1] : catNames.length > 0 ? catNames[catNames.length - 1] : '';
                        
                        const item = document.createElement('div');
                        item.className = 'item';
                        item.dataset.value = lastCatId;
                        item.dataset.catIds = JSON.stringify(catIds);
                        item.dataset.catNames = JSON.stringify(catNames);
                        item.textContent = `${lastCatId} ${displayText}`;
                        menu.appendChild(item);
                    });
                    
                    // 初始化下拉框（支持多选）
                    $(resultDropdown).dropdown({
                        allowReselection: true,
                        forceSelection: false,
                        useLabels: true
                    });
                    
                    // 同步下拉框值到隐藏输入框
                    const selectedValues = $(resultDropdown).dropdown('get value');
                    resultInput.value = Array.isArray(selectedValues) ? selectedValues.join(',') : selectedValues || '';
                }
                
                // 显示查询成功提示
                if (statusText) {
                    statusText.textContent = pollResult.msg || '查询成功！请点击下拉框选择结果！';
                    statusText.style.color = '#21ba45';
                }
            } else {
                resultInput.value = pollResult?.error_msg || '未找到相关类目';
                if (statusText) {
                    statusText.textContent = pollResult?.error_msg || '未找到相关类目';
                    statusText.style.color = '#f2711c';
                }
            }
        } catch (error) {
            resultInput.value = `搜索失败: ${error.message}`;
            if (statusText) {
                statusText.textContent = `搜索失败: ${error.message}`;
                statusText.style.color = '#db2828';
            }
            console.error('搜索类目失败:', error);
        }
    }
}

// 从数据库加载已保存的类目列表到期望类目下拉框
async function loadSavedCategoryList(catIdsToSelect = []) {
    const catDropdown = document.getElementById('expectedCatIdDropdown');
    if (!catDropdown) {
        console.warn('期望类目下拉框不存在');
        return;
    }

    try {
        const dropdown = $(catDropdown);
        const data = await requestPost('/api/get_saved_category_list', {}, {});
        if (data.success) {
            const categoryList = data.data || [];
            const menu = catDropdown.querySelector('.menu');

            // 获取当前已存在的选项值
            const existingItems = menu.querySelectorAll('.item');
            const existingCatIds = new Set();
            existingItems.forEach(item => {
                existingCatIds.add(String($(item).data('value')));
            });

            // 构建需要选中的值集合
            const selectedCatIdSet = new Set(catIdsToSelect.map(id => String(id)));

            // 添加新的类目选项（不清空现有选项）
            const addedCatIds = new Set();
            categoryList.forEach(cat => {
                const catId = cat.cat_ids && cat.cat_ids.length > 0 ? String(cat.cat_ids[cat.cat_ids.length - 1]) : '';
                const catName = cat.cat_names && cat.cat_names.length > 0 ? cat.cat_names[cat.cat_names.length - 1] : '';

                if (catId && catName && !addedCatIds.has(String(catId))) {
                    addedCatIds.add(String(catId));

                    // 如果选项已存在，跳过创建（保留原有选中状态）
                    if (existingCatIds.has(String(catId))) {
                        return;
                    }

                    const item = document.createElement('div');
                    item.className = 'item';
                    item.dataset.value = catId;
                    item.dataset.catIds = JSON.stringify(cat.cat_ids);
                    item.dataset.catNames = JSON.stringify(cat.cat_names);
                    
                    // 创建内容容器
                    const contentDiv = document.createElement('div');
                    contentDiv.style.display = 'flex';
                    contentDiv.style.justifyContent = 'space-between';
                    contentDiv.style.alignItems = 'center';
                    contentDiv.style.width = '100%';
                    
                    // 类目名称：只显示子类目ID和子类目名
                    const textSpan = document.createElement('span');
                    textSpan.textContent = `${catId} ${catName}`;
                    textSpan.style.flex = '1';
                    textSpan.style.overflow = 'hidden';
                    textSpan.style.textOverflow = 'ellipsis';
                    textSpan.style.whiteSpace = 'nowrap';
                    
                    // 删除按钮（从数据库删除）- 使用 deleteBtn 类名区分
                    const deleteBtn = document.createElement('span');
                    deleteBtn.className = 'deleteBtn';
                    deleteBtn.innerHTML = '&times;';
                    deleteBtn.style.cursor = 'pointer';
                    deleteBtn.style.color = '#999';
                    deleteBtn.style.fontSize = '18px';
                    deleteBtn.style.marginLeft = '10px';
                    deleteBtn.style.padding = '0 5px';
                    deleteBtn.style.lineHeight = '1';
                    deleteBtn.title = '从数据库删除此类目';
                    
                    // 点击删除按钮时阻止事件冒泡
                    deleteBtn.addEventListener('click', async function(e) {
                        e.stopPropagation();
                        e.preventDefault();
                        e.stopImmediatePropagation();

                        const confirmed = await showConfirm(`确定要删除类目"${catName}"吗？`);
                        if (confirmed) {
                            try {
                                const result = await requestPost('/api/delete_saved_category', {}, { cat_id: catId });
                                if (result.success) {
                                    // 从下拉框中移除该项
                                    item.remove();
                                    // 更新下拉框的值（如果该项已被选中）
                                    const currentValues = $(catDropdown).dropdown('get value') || [];
                                    const currentValuesArray = Array.isArray(currentValues) ? currentValues : (currentValues ? [String(currentValues)] : []);
                                    const newValues = currentValuesArray.filter(v => String(v) !== String(catId));
                                    $(catDropdown).dropdown('set value', newValues);
                                    showSuccess('删除成功');
                                } else {
                                    showWarning(result.error_msg || '删除失败');
                                }
                            } catch (error) {
                                console.error('删除类目失败:', error);
                                showWarning('删除失败');
                            }
                        }
                    });
                    
                    // 鼠标悬停效果
                    deleteBtn.addEventListener('mouseenter', function() {
                        deleteBtn.style.color = '#db2828';
                    });
                    deleteBtn.addEventListener('mouseleave', function() {
                        deleteBtn.style.color = '#999';
                    });
                    
                    contentDiv.appendChild(textSpan);
                    contentDiv.appendChild(deleteBtn);
                    item.appendChild(contentDiv);
                    menu.appendChild(item);
                }
            });

            // 设置需要选中的值
            if (catIdsToSelect.length > 0) {
                console.log('设置选中的类目值:', catIdsToSelect);
                // 重新初始化下拉框以确保新添加的选项能被识别
                dropdown.dropdown('refresh');

                // 遍历所有选项，匹配完整的类目路径
                const allItems = menu.querySelectorAll('.item');
                const selectedValues = [];

                allItems.forEach(item => {
                    const catIds = JSON.parse(item.dataset.catIds || '[]');
                    const catIdsStr = catIds.map(id => String(id));

                    // 检查是否在需要选中的列表中
                    const isSelected = catIdsToSelect.some(catId => catIdsStr.includes(String(catId)));
                    if (isSelected) {
                        selectedValues.push(catIdsStr[catIdsStr.length - 1]);
                    }
                });

                dropdown.dropdown('set value', selectedValues);
                console.log('实际选中的类目值:', selectedValues);
            }

            console.log('已保存类目列表加载成功:', categoryList);
        } else {
            console.error('加载已保存类目列表失败:', data.error_msg);
        }
    } catch (error) {
        console.error('加载已保存类目列表失败:', error);
    }
}

// 加载排除SKC列表
async function loadNotSkcList() {
    try {
        const result = await requestPost('/api/get_config', {}, { key: 'apply_activity_not_skc_list' });
        if (result.success) {
            const skcList = result.data || '';
            const inputEl = document.getElementById('inputNotSkcList');
            if (inputEl) {
                inputEl.value = skcList;
                showSuccess('排除SKC列表加载成功');
            }
        } else {
            showWarning(result.error_msg || '加载失败');
        }
    } catch (error) {
        console.error('加载排除SKC列表失败:', error);
        showError('加载排除SKC列表失败');
    }
}

// 保存排除SKC列表
async function saveNotSkcList() {
    try {
        const inputEl = document.getElementById('inputNotSkcList');
        if (!inputEl) {
            showWarning('输入框不存在');
            return;
        }
        const skcList = inputEl.value.trim();
        
        const result = await requestPost('/api/set_config', {}, { 
            key: 'apply_activity_not_skc_list', 
            value: skcList 
        });
        if (result.success) {
            showSuccess('排除SKC列表保存成功');
        } else {
            showWarning(result.error_msg || '保存失败');
        }
    } catch (error) {
        console.error('保存排除SKC列表失败:', error);
        showError('保存排除SKC列表失败');
    }
}

// ==================== 详细活动筛选功能 ====================

// 获取并更新活动列表（使用已勾选的店铺）
async function fetchAndUpdateActivityList() {
    // 获取已勾选的店铺
    const selectedCheckboxes = document.querySelectorAll('#shopSelectionArea input[type="checkbox"]:checked');
    if (selectedCheckboxes.length === 0) {
        showWarning('请先勾选店铺');
        return;
    }
    
    // 获取选中的店铺UID
    const selectedShopUids = Array.from(selectedCheckboxes).map(cb => {
        const shop = JSON.parse(cb.dataset.shop);
        return shop.uid;
    }).filter(uid => uid);
    
    if (selectedShopUids.length === 0) {
        showWarning('请至少选择一个有效的店铺');
        return;
    }
    
    // 使用第一个勾选的店铺
    const uid = selectedShopUids[0];
    const statusEl = document.getElementById('activityListStatus');
    
    try {
        if (statusEl) {
            statusEl.textContent = '正在获取活动列表...';
            statusEl.style.color = '#1890ff';
        }
        
        const result = await requestPost('/api/fetch_activity_list', {}, { uid: uid });
        
        if (result.success) {
            // 保存到数据库
            await requestPost('/api/set_config', {}, {
                key: 'apply_activity_detailed_list',
                value: JSON.stringify(result.data || [])
            });
            
            // 刷新下拉框
            await loadSavedDetailedActivityList();
            
            if (statusEl) {
                statusEl.textContent = `活动列表更新成功，共${result.data ? result.data.length : 0}个活动`;
                statusEl.style.color = '#52c41a';
            }
            showSuccess('活动列表更新成功');
        } else {
            if (statusEl) {
                statusEl.textContent = '获取活动列表失败：' + (result.error_msg || '未知错误');
                statusEl.style.color = '#ff4d4f';
            }
            showWarning(result.error_msg || '获取活动列表失败');
        }
    } catch (error) {
        console.error('获取活动列表失败:', error);
        if (statusEl) {
            statusEl.textContent = '获取活动列表失败';
            statusEl.style.color = '#ff4d4f';
        }
        showError('获取活动列表失败');
    }
}

// 加载已保存的详细活动列表
async function loadSavedDetailedActivityList(activityIdToSelect = null) {
    const dropdown = document.getElementById('detailedActivityDropdown');
    const menu = document.getElementById('detailedActivityMenu');
    if (!dropdown || !menu) {
        console.warn('详细活动下拉框不存在');
        return;
    }
    
    try {
        const result = await requestPost('/api/get_config', {}, { key: 'apply_activity_detailed_list' });
        if (result.success) {
            const activityList = JSON.parse(result.data || '[]');
            
            // 清空现有选项
            menu.innerHTML = '';
            
            if (activityList.length === 0) {
                menu.innerHTML = '<div class="item" data-value=""><div class="default text">暂无活动数据，请先更新活动列表</div></div>';
            } else {
                // 添加选项
                activityList.forEach((activity, index) => {
                    const item = document.createElement('div');
                    item.className = 'item';
                    
                    // 构建显示文本：【activityName】activityThematicName
                    let displayText = '';
                    if (activity.activityThematicName) {
                        displayText = `【${activity.activityName || ''}】${activity.activityThematicName}`;
                    } else {
                        displayText = activity.activityName || '未知活动';
                    }
                    
                    // 使用索引作为简单ID，避免JSON字符串中的特殊字符问题
                    const activityId = `activity_${index}`;
                    item.setAttribute('data-value', activityId);
                    item.textContent = displayText;
                    
                    // 存储活动数据
                    item.dataset.activity = JSON.stringify(activity);
                    
                    menu.appendChild(item);
                });
            }
            
            // 重新初始化下拉框
            if (typeof $ !== 'undefined' && $.fn.dropdown) {
                $(dropdown).dropdown('refresh');
                
                // 如果有需要选中的值
                if (activityIdToSelect) {
                    // 查找匹配的活动
                    const items = menu.querySelectorAll('.item');
                    items.forEach(item => {
                        const activityData = JSON.parse(item.dataset.activity || '{}');
                        if (activityData.activityThematicId === activityIdToSelect || 
                            activityData.activityType === activityIdToSelect) {
                            $(dropdown).dropdown('set selected', item.getAttribute('data-value'));
                        }
                    });
                }
            }
            
            console.log('详细活动列表加载成功:', activityList);
        } else {
            console.error('加载详细活动列表失败:', result.error_msg);
        }
    } catch (error) {
        console.error('加载详细活动列表失败:', error);
    }
}

function updatePaginationControls(container, pagination) {
    if (!container) {
        console.warn('分页容器不存在');
        return;
    }

    // 确保容器有分页样式类
    container.classList.add('pagination');

    const { page, total_pages, has_prev, has_next } = pagination;

    // 如果只有1页，显示当前页信息但不显示分页按钮
    if (total_pages <= 1) {
        container.innerHTML = `<div style="text-align: center; color: #666; padding: 15px; background: #f5f5f5; border-radius: 4px; border: 1px solid #e0e0e0;">共 1 页，当前第 1 页</div>`;
        return;
    }

    let html = `<div class="pagination" style="display: flex; gap: 0.5rem; justify-content: center; align-items: center; flex-wrap: wrap; padding: 15px; background: #f9f9f9; border-radius: 4px; border: 1px solid #e0e0e0;">`;

    html += `<button class="page-btn" onclick="loadShopList(${page - 1})" ${!has_prev ? 'disabled' : ''} style="min-width: 80px; padding: 8px 16px; border: 1px solid #ddd; border-radius: 4px; background: #fff; cursor: pointer; transition: all 0.3s ease; font-size: 14px;">上一页</button>`;

    for (let i = 1; i <= total_pages; i++) {
        if (i === page) {
            html += `<button class="page-btn active" style="min-width: 40px; padding: 8px 12px; border: 1px solid #1890ff; border-radius: 4px; background: #1890ff; color: #fff; font-weight: 500; cursor: default; font-size: 14px;">${i}</button>`;
        } else if (i === 1 || i === total_pages || Math.abs(i - page) <= 2) {
            html += `<button class="page-btn" onclick="loadShopList(${i})" style="min-width: 40px; padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; background: #fff; cursor: pointer; transition: all 0.3s ease; font-size: 14px;">${i}</button>`;
        } else if (Math.abs(i - page) === 3) {
            html += `<span style="padding: 0 8px; color: #666; font-size: 14px;">...</span>`;
        }
    }

    html += `<button class="page-btn" onclick="loadShopList(${page + 1})" ${!has_next ? 'disabled' : ''} style="min-width: 80px; padding: 8px 16px; border: 1px solid #ddd; border-radius: 4px; background: #fff; cursor: pointer; transition: all 0.3s ease; font-size: 14px;">下一页</button>`;

    // 显示分页信息，移到右侧
    html += `<div style="margin-left: 15px; color: #666; font-size: 14px; font-weight: 500;">共 ${total_pages} 页，当前第 ${page} 页</div>`;

    html += `</div>`;

    container.innerHTML = html;
}

// 店铺连接状态检测
async function checkShopConnectionStatus(uid) {
    try {
        const result = await requestGet('/api/check_shop_status', { uid });
        return result.success && result.connected;
    } catch (error) {
        console.error(`检测店铺${uid} 连接状态失败: `, error);
        return false;
    }
}

/**
 * 检测店铺连接状态
 * @param {string} uid - 店铺UID
 * @returns {Promise<Object>} 检测结果
 */
async function checkShopAuthStatus(uid) {
    try {
        const result = await requestPost('/api/toggle_shop_connection/test', {}, {
            uid: uid
        });
        return result;
    } catch (error) {
        console.error(`检测店铺${uid} 连接状态失败: `, error);
        return {
            success: false,
            error_msg: error.message || '检测失败'
        };
    }
}

/**
 * 触发店铺连接状态检测
 * @param {string} uid - 店铺UID
 * @param {HTMLElement} buttonElement - 触发按钮元素
 */
async function triggerShopAuthCheck(uid, buttonElement) {
    if (!uid) {
        showWarning('店铺UID不能为空');
        return;
    }

    const originalText = buttonElement.innerHTML;
    const originalDisabled = buttonElement.disabled;

    // 设置按钮为检测中状态
    buttonElement.innerHTML = '<i class="spinner loading icon"></i> 检测中...';
    buttonElement.disabled = true;
    buttonElement.classList.add('loading');

    try {
        const result = await checkShopAuthStatus(uid);
        if (result.success) {
            showSuccess(`授权检测任务已提交：${result.message || '任务ID: ' + (result.task_id || 'N/A')} `);
            // 可以在这里添加状态更新逻辑
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError(`授权检测失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`授权检测失败：${error.message} `);
    } finally {
        // 恢复按钮状态
        buttonElement.innerHTML = originalText;
        buttonElement.disabled = originalDisabled;
        buttonElement.classList.remove('loading');
    }
}

// 日志监控相关
function switchToLogMode() {
    openConfirmModal('切换到纯日志模式后，将不再显示任务菜单，只显示实时日志。确认切换吗？').then(() => {
        switchSection('log-viewer');
        connectLogs();
        showInfo('已切换到日志模式。输入 "1" 切换回任务管理菜单 | "0" 直接退出程序');
    }).catch(err => console.log(err));
}

async function connectLogs() {
    const connectBtn = document.getElementById('connectBtn');
    try {
        connectBtn.classList.add('loading');

        // 获取参数
        const maxLinesInput = document.getElementById('logMaxLines');
        const keywordInput = document.getElementById('logKeyword');

        // 构建请求参数
        const params = {};

        // 如果输入了最大行数，添加到参数中
        if (maxLinesInput && maxLinesInput.value && maxLinesInput.value.trim()) {
            const maxLines = parseInt(maxLinesInput.value.trim());
            if (!isNaN(maxLines) && maxLines > 0) {
                params.max_lines = maxLines;
            }
        }

        // 如果输入了关键词，添加到参数中
        if (keywordInput && keywordInput.value && keywordInput.value.trim()) {
            params.keyword = keywordInput.value.trim();
        }

        // 先获取日志长度检查是否过大
        const checkResult = await requestPost('/api/check_log_length', {}, {});
        console.log('日志长度检查结果:', checkResult);
        if (checkResult && checkResult.success) {
            const logLength = checkResult.log_length || 0;
            const logThreshold = 0;  // 改为0，任何非空日志都会触发弹窗
            console.log(`日志长度: ${logLength}, 阈值: ${logThreshold}`);

            if (logLength > logThreshold) {
                // 日志过大，弹出确认框
                const shouldClean = await showConfirmDialog(
                    '日志文件过大',
                    `当前日志文件字符数为 ${logLength}，超过阈值 ${logThreshold}。<br><br>` +
                    `文件过大可能导致页面加载缓慢或崩溃。<br><br>` +
                    `是否自动清除旧日志并保留最新的20%部分？`,
                    '清除旧日志',
                    '取消'
                );

                if (shouldClean) {
                    // 用户确认清除旧日志
                    const cleanResult = await requestPost('/api/clean_old_logs', {}, { keep_ratio: 0.2 });
                    if (cleanResult && cleanResult.success) {
                        showSuccess(cleanResult.msg || '旧日志已清除，保留最新20%');
                    } else {
                        showError('清除旧日志失败：' + (cleanResult.error_msg || cleanResult.message || '未知错误'));
                        connectBtn.classList.remove('loading');
                        return;
                    }
                } else {
                    // 用户取消，继续显示完整日志
                    showWarning('将显示完整日志，可能加载较慢');
                }
            } else {
                console.log('日志长度未超过阈值，不弹出确认框');
            }
        } else {
            console.log('日志长度检查失败或返回结果不正确:', checkResult);
        }

        // 如果查所有日志就传空对象 {}，否则传参数字典
        const result = await requestPost('/api/connect_total_log', {}, params);
        if (result && result.success) {
            const logsContainer = document.getElementById('logsContainer');
            logsContainer.innerHTML = '';

            // 处理返回的 total_log_content 字段
            if (result.total_log_content) {
                // 按 \n 分割字符串
                const lines = result.total_log_content.split('\n').filter(line => line.trim());
                // 逐行显示，根据日志级别设置颜色
                lines.forEach(line => {
                    addLogWithLevel(line);
                });
            } else {
                addLog('已请求连接日志接口 /api/connect_total_log', 'info');
            }
            showSuccess(result.msg || result.message || '日志连接请求已发送');
        } else {
            const errorMsg = (result && (result.error_msg || result.message)) || '未知错误';
            showError(`连接日志失败：${errorMsg} `);
        }
    } catch (error) {
        showError('连接日志失败：' + (error.message || '请求异常'));
    } finally {
        connectBtn.classList.remove('loading');
    }
}

// 解析日志行并添加带颜色的日志
function addLogWithLevel(logLine) {
    if (!logLine || !logLine.trim()) return;

    const logsContainer = document.getElementById('logsContainer');

    // 解析日志格式，常见格式：[时间] LEVEL 消息内容
    // 匹配时间格式，如 [2024-01-15 15:00:43] 或 [01-15 15:00:43]
    const timeMatch = logLine.match(/^(\[[^\]]+\])/);
    const timeStr = timeMatch ? timeMatch[1] : '';
    const contentAfterTime = timeMatch ? logLine.substring(timeMatch[0].length).trim() : logLine;

    // 更精确地检测日志级别（匹配独立的级别标识）
    let level = 'info'; // 默认白色
    let message = contentAfterTime;
    let levelText = '';

    // 匹配日志级别（如 "INFO", "TRACE", "ERROR" 等，前后可能有空格）
    const levelMatch = contentAfterTime.match(/^\s*(INFO|TRACE|ERROR|WARN|WARNING|DEBUG)\s+/i);
    if (levelMatch) {
        levelText = levelMatch[1].toUpperCase();
        message = contentAfterTime.substring(levelMatch[0].length).trim();

        if (/^ERROR$/i.test(levelText)) {
            level = 'error'; // 红色
        } else if (/^TRACE$/i.test(levelText)) {
            level = 'trace'; // 蓝色
        } else if (/^INFO$/i.test(levelText)) {
            level = 'info'; // 白色
        } else {
            level = 'info'; // 其他级别默认白色
        }
    } else {
        // 如果没有明确的级别标识，尝试从内容中检测
        if (/ERROR|错误/i.test(contentAfterTime)) {
            level = 'error';
            levelText = 'ERROR';
        } else if (/TRACE/i.test(contentAfterTime)) {
            level = 'trace';
            levelText = 'TRACE';
        } else {
            level = 'info';
            levelText = 'INFO';
        }
    }

    // 创建日志条目
    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry';

    // 根据级别设置颜色
    let levelColor = '#ffffff'; // info 白色
    if (level === 'error') {
        levelColor = '#f44336'; // error 红色
    } else if (level === 'trace') {
        levelColor = '#2196F3'; // trace 蓝色
    }

    logEntry.innerHTML = `
    < span class="log-time" style = "color: #006400;" > ${escapeHtml(timeStr)}</span >
        <span class="log-level ${level}" style="color: ${levelColor};">${levelText || level.toUpperCase()}</span>
        <span style="color: ${levelColor};">${escapeHtml(message)}</span>
`;

    logsContainer.appendChild(logEntry);
    logsContainer.scrollTop = logsContainer.scrollHeight;
}

function updateLogStatus(connected) {
    const statusIndicator = document.getElementById('logStatus');
    if (!statusIndicator) {
        // logStatus 元素不存在（可能被注释掉了），直接返回
        return;
    }
    const statusDot = statusIndicator.querySelector('.status-dot');
    const statusText = statusIndicator.querySelector('span:last-child');
    if (connected) {
        statusIndicator.className = 'status-indicator running';
        if (statusDot) statusDot.className = 'status-dot running';
        if (statusText) statusText.textContent = '已连接';
    } else {
        statusIndicator.className = 'status-indicator stopped';
        if (statusDot) statusDot.className = 'status-dot stopped';
        if (statusText) statusText.textContent = '未连接';
    }
}

function addLog(message, level = 'info') {
    const logsContainer = document.getElementById('logsContainer');
    const now = new Date();
    const timeStr = `[${String(now.getMonth() + 1).padStart(2, '0')} -${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}]`;
    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry';
    logEntry.innerHTML = `
    < span class="log-time" > ${timeStr}</span >
        <span class="log-level ${level}">${level.toUpperCase()}</span>
        <span>${message}</span>
`;
    logsContainer.appendChild(logEntry);
    logsContainer.scrollTop = logsContainer.scrollHeight;
}

async function clearLogs() {
    try {
        const shouldClean = await showConfirmDialog(
            '清空全局日志',
            '确定要清空所有全局日志吗？此操作不可恢复！',
            '确认清空',
            '取消'
        );
        
        if (!shouldClean) {
            return;
        }
        
        const result = await requestPost('/api/clean_total_log', {}, {});
        if (result && result.success) {
            const logsContainer = document.getElementById('logsContainer');
            const now = new Date();
            const timeStr = `[${now.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }).replace(/[年月]/g, '-').replace('日', '')}]`;
            logsContainer.innerHTML = `
    < div class="log-entry" >
                    <span class="log-time">${timeStr}</span>
                    <span class="log-level info">INFO</span>
                    <span>${result.msg || result.message || '全局日志已清空'}</span>
                </div >
    `;
            showSuccess(result.msg || result.message || '全局日志已清空');
        } else {
            const errorMsg = (result && (result.error_msg || result.message)) || '未知错误';
            showError(`清空日志失败：${errorMsg} `);
        }
    } catch (error) {
        showError('清空日志失败：' + (error.message || '请求异常'));
    }
}

// 一键清空所有任务日志
async function cleanAllTaskLogs() {
    const confirmed = await showConfirm('确定要清空所有任务日志吗？此操作不可恢复！');
    if (!confirmed) {
        return;
    }

    try {
        const result = await requestPost('/api/clean_task_log_all', {}, {});
        if (result && result.success) {
            showSuccess(result.msg || result.message || '所有任务日志已清空');
        } else {
            const errorMsg = (result && (result.error_msg || result.message)) || '未知错误';
            showError(`一键清空任务日志失败：${errorMsg} `);
        }
    } catch (error) {
        showError('一键清空任务日志失败：' + (error.message || '请求异常'));
    }
}

async function exportLogs() {
    try {
        const result = await requestPost('/api/export_total_log', {}, {});
        if (result && result.success) {
            // 如果后端返回下载链接或文件内容，可在这里处理
            if (result.url) {
                window.open(result.url, '_blank');
            } else if (result.content) {
                const blob = new Blob([result.content], { type: 'text/plain;charset=utf-8' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = result.filename || `logs_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.txt`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }
            showSuccess(result.msg || result.message || '日志导出任务已触发');
        } else {
            const errorMsg = (result && (result.error_msg || result.message)) || '未知错误';
            showError(`导出日志失败：${errorMsg} `);
        }
    } catch (error) {
        showError('导出日志失败：' + (error.message || '请求异常'));
    }
}

// 服务器状态/控制
async function loadServerStatus() {
    const serverStatus = document.getElementById('serverStatus');
    const processList = document.getElementById('processList');
    try {
        const result = await requestGet('/api/server_status');
        if (result.success) {
            serverStatus.innerHTML = `
    <p><strong>状态:</strong> <span class="status-indicator ${result.running ? 'running' : 'stopped'}">
                    <span class="status-dot ${result.running ? 'running' : 'stopped'}"></span>
                    <div class="status-text-container">
                        <span class="status-char">运</span>
                        <span class="status-char">行</span>
                        <span class="status-char">中</span>
                    </div>
                </span></p>
                <p><strong>启动时间:</strong> ${result.start_time || 'N/A'}</p>
                <p><strong>运行时长:</strong> ${result.uptime || 'N/A'}</p>
                <p><strong>版本:</strong> ${appVersion || result.version || '1.0.0'}</p>
`;
            const startBtn = document.getElementById('startServerBtn');
            const stopBtn = document.getElementById('stopServerBtn');
            if (startBtn) startBtn.disabled = result.running;
            if (stopBtn) stopBtn.disabled = !result.running;

            if (result.processes && result.processes.length > 0) {
                let processHtml = '';
                result.processes.forEach(proc => {
                    processHtml += `
    <div style="margin-bottom: 10px; padding: 10px; background: white; border-radius: 4px; border: 1px solid #ddd;">
                            <p><strong>PID:</strong> ${proc.pid}</p>
                            <p><strong>端口:</strong> ${proc.port}</p>
                            <p><strong>Worker数:</strong> ${proc.workers}</p>
                            <p><strong>状态:</strong> ${proc.status}</p>
                        </div>
    `;
                });
                processList.innerHTML = processHtml;
            } else {
                processList.innerHTML = '<p>无运行中的进程</p>';
            }
        } else {
            serverStatus.innerHTML = `<p style="color: red;">获取服务器状态失败: ${result.error_msg}</p>`;
        }
    } catch (error) {
        serverStatus.innerHTML = `<p style="color: red;">获取服务器状态失败: ${error.message}</p>`;
    }
}

async function startServer() {
    try {
        const result = await requestPost('/api/start_server', {}, {});
        if (result.success) {
            showSuccess(result.message);
            loadServerStatus();
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError(`启动失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`启动失败：${error.message} `);
    }
}

async function stopServer() {
    try {
        await openConfirmModal('确认停止服务器吗？');
        const result = await requestPost('/api/stop_server', {}, {});
        if (result.success) {
            showSuccess(result.message);
            loadServerStatus();
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError(`停止失败：${errorMsg} `);
        }
    } catch (error) {
        if (error.message !== "用户取消操作") showError(`停止失败：${error.message} `);
    }
}

async function restartServer() {
    try {
        await openConfirmModal('确认重启服务器吗？');
        const result = await requestPost('/api/restart_server', {}, {});
        if (result.success) {
            showSuccess(result.message);
            setTimeout(loadServerStatus, 2000);
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError(`重启失败：${errorMsg} `);
        }
    } catch (error) {
        if (error.message !== "用户取消操作") showError(`重启失败：${error.message} `);
    }
}

async function loadSettings() {
    try {
        // 先初始化下拉框
        if ($('#process').length) {
            $('#process').dropdown();
        }
        if ($('#worker_per_proc').length) {
            $('#worker_per_proc').dropdown();
        }
        if ($('#thread_mode').length) {
            $('#thread_mode').dropdown();
        }
        if ($('#mode').length) {
            $('#mode').dropdown();
        }
        if ($('#restart').length) {
            $('#restart').dropdown();
        }
        if ($('#cdn_mode').length) {
            $('#cdn_mode').dropdown();
        }
        if ($('#themeSelect').length) {
            $('#themeSelect').dropdown();
        }
        // 初始化auth_enabled复选框
        if ($('#auth_enabled').length) {
            $('#auth_enabled').checkbox();
        }

        const result = await requestGet('/api/get_settings', {});
        if (result.success && result.data) {
            const data = result.data;
            // 填充表单
            if (document.getElementById('internalIp')) {
                document.getElementById('internalIp').value = data.internal_ip || '';
            }
            if (document.getElementById('externalIp')) {
                document.getElementById('externalIp').value = data.external_ip || '';
            }
            if (document.getElementById('port')) {
                document.getElementById('port').value = data.port || '1234';
            }
            if (document.getElementById('process')) {
                // 设置下拉框的值
                $('#process').dropdown('set selected', data.process_count || '1');
            }
            if (document.getElementById('worker_per_proc')) {
                // 设置下拉框的值
                $('#worker_per_proc').dropdown('set selected', data.worker_per_proc || '1');
            }
            if (document.getElementById('token')) {
                document.getElementById('token').value = data.token || '';
            }
            if (document.getElementById('auth_enabled')) {
                const authEnabled = data.auth_enabled === 'true' || data.auth_enabled === true;
                document.getElementById('auth_enabled').checked = authEnabled;
                // 使用Semantic UI的方式设置复选框状态
                if ($('#auth_enabled').length) {
                    $('#auth_enabled').checkbox(authEnabled ? 'set checked' : 'set unchecked');
                }
            }
            if (document.getElementById('thread_mode')) {
                // 设置下拉框的值
                $('#thread_mode').dropdown('set selected', data.thread_mode || '0');
            }
            if (document.getElementById('mode')) {
                // 设置下拉框的值
                $('#mode').dropdown('set selected', data.mode || '0');
            }
            if (document.getElementById('restart')) {
                // 设置下拉框的值
                $('#restart').dropdown('set selected', data.restart_interval || '不重启');
            }
            if (document.getElementById('cdn_mode')) {
                // 设置下拉框的值
                $('#cdn_mode').dropdown('set selected', data.cdn_mode || '云端');
            }
            if (document.getElementById('backgroundMusicEnabledCheckbox')) {
                document.getElementById('backgroundMusicEnabledCheckbox').checked = data.background_music_enabled === '是';
            }
            if (document.getElementById('backgroundMusicAutoplayCheckbox')) {
                document.getElementById('backgroundMusicAutoplayCheckbox').checked = data.background_music_autoplay === '是';
            }
            if (document.getElementById('backgroundMusicLocalCheckbox')) {
                document.getElementById('backgroundMusicLocalCheckbox').checked = data.background_music_local === '是';
            }
            if (document.getElementById('backgroundMusicUrl')) {
                document.getElementById('backgroundMusicUrl').value = data.background_music_url || '';
            }
            
            // 加载特效效果设置
            try {
                const effectResult = await requestGet('/api/get_effect_settings', {});
                if (effectResult.success && effectResult.data) {
                    const effectData = effectResult.data;
                    
                    if (document.getElementById('yinghuaEffectEnabledCheckbox')) {
                        document.getElementById('yinghuaEffectEnabledCheckbox').checked = effectData.yinghua_html === '是';
                    }
                    if (document.getElementById('qipaoEffectEnabledCheckbox')) {
                        document.getElementById('qipaoEffectEnabledCheckbox').checked = effectData.qipao_html === '是';
                    }
                    if (document.getElementById('roseEffectEnabledCheckbox')) {
                        document.getElementById('roseEffectEnabledCheckbox').checked = effectData.rose_html === '是';
                    }
                    if (document.getElementById('themeSelect')) {
                        $('#themeSelect').dropdown('set selected', effectData.theme || '默认主题');
                    }
                    
                    // CDN设置
                    if (document.getElementById('cdn_mode')) {
                        $('#cdn_mode').dropdown('set selected', effectData.cdn_mode || '云端');
                    }
                    
                    // 不自动应用CDN模式，避免切换页面时重新加载资源导致元素丢失
                    // CDN模式应该在页面加载时确定，不应该在切换页面时改变
                    // applyCdnMode(effectData.cdn_mode || '云端');
                }
            } catch (error) {
                console.error('加载特效设置失败:', error);
            }
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            console.error(`加载设置失败：${errorMsg} `);
        }
    } catch (error) {
        console.error(`加载设置失败：${error.message} `);
    }
}

async function saveSettings() {
    const internalIp = document.getElementById('internalIp')?.value?.trim() || '';
    const externalIp = document.getElementById('externalIp')?.value?.trim() || '';
    const port = document.getElementById('port')?.value?.trim() || '1234';
    const process = document.getElementById('process')?.value?.trim() || '1';
    const workerPerProc = document.getElementById('worker_per_proc')?.value?.trim() || '1';
    const token = document.getElementById('token')?.value?.trim() || '';
    const oldToken = currentToken;  // 保存旧的token值
    const authEnabled = document.getElementById('auth_enabled')?.checked || false;
    const threadMode = document.getElementById('thread_mode')?.value?.trim() || '0';
    const mode = document.getElementById('mode')?.value?.trim() || '0';
    const restart = document.getElementById('restart')?.value?.trim() || '不重启';
    const cdnMode = document.getElementById('cdn_mode')?.value?.trim() || '云端';
    const backgroundMusicEnabled = document.getElementById('backgroundMusicEnabledCheckbox')?.checked ? '是' : '否';
    const backgroundMusicAutoplay = document.getElementById('backgroundMusicAutoplayCheckbox')?.checked ? '是' : '否';
    const backgroundMusicLocal = document.getElementById('backgroundMusicLocalCheckbox')?.checked ? '是' : '否';
    const backgroundMusicUrl = document.getElementById('backgroundMusicUrl')?.value?.trim() || '';
    
    // 获取特效效果设置
    const yinghuaEffectEnabled = document.getElementById('yinghuaEffectEnabledCheckbox')?.checked ? '是' : '否';
    const qipaoEffectEnabled = document.getElementById('qipaoEffectEnabledCheckbox')?.checked ? '是' : '否';
    const roseEffectEnabled = document.getElementById('roseEffectEnabledCheckbox')?.checked ? '是' : '否';
    const themeSelect = document.getElementById('themeSelect')?.value?.trim() || '默认主题';

    // 基本设置（不包含token）
    const settings = {
        internal_ip: internalIp,
        external_ip: externalIp,
        port: port,
        process_count: process,
        worker_per_proc: workerPerProc,
        auth_enabled: authEnabled,
        thread_mode: threadMode,
        mode: mode,
        restart_interval: restart,
        cdn_mode: cdnMode,
        background_music_enabled: backgroundMusicEnabled,
        background_music_autoplay: backgroundMusicAutoplay,
        background_music_url: backgroundMusicUrl,
        background_music_local: backgroundMusicLocal
    };
    
    // 特效效果设置
    const effectSettings = {
        yinghua_html: yinghuaEffectEnabled,
        qipao_html: qipaoEffectEnabled,
        rose_html: roseEffectEnabled,
        theme: themeSelect,
        background_music_enabled: backgroundMusicEnabled,
        background_music_autoplay: backgroundMusicAutoplay,
        background_music_url: backgroundMusicUrl,
        background_music_local: backgroundMusicLocal,
        cdn_mode: cdnMode
    };

    try {
        // 1. 先保存基本设置（不包含token）
        const result = await requestPost('/api/save_settings', {}, settings);
        if (result.success) {
            // 2. 保存特效效果设置
            try {
                const effectResult = await requestPost('/api/save_effect_settings', {}, effectSettings);
                if (effectResult.success) {
                    // 3. 最后单独保存token
                    try {
                        const tokenResult = await requestPost('/api/save_settings', {}, { token: token });
                        if (tokenResult.success) {
                            // 检查token是否变化
                            if (token !== oldToken) {
                                // token变化了，跳转到新token的URL
                                const currentUrl = new URL(window.location.href);
                                currentUrl.searchParams.set('token', token);
                                window.location.href = currentUrl.toString();
                            } else {
                                showSuccess('设置保存成功！');
                                // 如果特效设置有变化，提示用户刷新页面
                                if (effectResult.need_refresh) {
                                    const confirmed = await showConfirm('特效设置已更改，是否刷新页面以应用新设置？');
                                    if (confirmed) {
                                        window.location.reload();
                                    }
                                }
                            }
                        } else {
                            const errorMsg = tokenResult.error_msg || tokenResult.message || '未知错误';
                            showError(`Token保存失败：${errorMsg} `);
                        }
                    } catch (error) {
                        console.error('保存Token失败:', error);
                        showError(`Token保存失败：${error.message} `);
                    }
                } else {
                    const errorMsg = effectResult.error_msg || effectResult.message || '未知错误';
                    showError(`特效设置保存失败：${errorMsg} `);
                }
            } catch (error) {
                console.error('保存特效设置失败:', error);
                showError(`特效设置保存失败：${error.message} `);
            }
        } else {
            const errorMsg = result.error_msg || result.message || '未知错误';
            showError(`保存失败：${errorMsg} `);
        }
    } catch (error) {
        showError(`保存失败：${error.message} `);
    }
}

// 定期更新数据 - 已禁用自动刷新
// setInterval(() => {
//     // 任务管理自动刷新已注释
//     // if (currentSection === 'task-manager') loadTasks();
//     if (currentSection === 'server-control') loadServerStatus();
// }, 10000);

// CDN模式管理函数
// CDN模式管理函数
function applyCdnMode(cdnMode) {
    // 根据CDN模式设置资源加载方式
    const semanticUiLocal = document.getElementById('semantic-ui-local');
    const semanticUiCdn = document.getElementById('semantic-ui-cdn');
    const fontAwesomeLocal = document.getElementById('font-awesome-local');
    const fontAwesomeCdn = document.getElementById('font-awesome-cdn');

    if (cdnMode === '本地') {
        // 仅使用本地资源
        if (semanticUiCdn) {
            semanticUiCdn.setAttribute('disabled', 'disabled');
            semanticUiCdn.removeAttribute('href');
        }
        if (fontAwesomeCdn) {
            fontAwesomeCdn.setAttribute('disabled', 'disabled');
            fontAwesomeCdn.removeAttribute('href');
        }
        if (semanticUiLocal) {
            semanticUiLocal.removeAttribute('disabled');
        }
        if (fontAwesomeLocal) {
            fontAwesomeLocal.removeAttribute('disabled');
        }
    } else if (cdnMode === '云端') {
        // 仅使用CDN资源
        if (semanticUiLocal) {
            semanticUiLocal.setAttribute('disabled', 'disabled');
        }
        if (fontAwesomeLocal) {
            fontAwesomeLocal.setAttribute('disabled', 'disabled');
        }
        if (semanticUiCdn) {
            semanticUiCdn.removeAttribute('disabled');
            semanticUiCdn.href = 'https://cdn.bootcdn.net/ajax/libs/semantic-ui/2.5.0/semantic.min.css';
        }
        if (fontAwesomeCdn) {
            fontAwesomeCdn.removeAttribute('disabled');
            fontAwesomeCdn.href = 'https://cdn.bootcdn.net/ajax/libs/font-awesome/6.4.0/css/all.min.css';
        }
    } else {
        // 混合模式：本地优先，CDN作为备用
        if (semanticUiCdn) {
            semanticUiCdn.setAttribute('disabled', 'disabled');
            semanticUiCdn.removeAttribute('href');
        }
        if (fontAwesomeCdn) {
            fontAwesomeCdn.setAttribute('disabled', 'disabled');
            fontAwesomeCdn.removeAttribute('href');
        }
        if (semanticUiLocal) {
            semanticUiLocal.removeAttribute('disabled');
        }
        if (fontAwesomeLocal) {
            fontAwesomeLocal.removeAttribute('disabled');
        }
    }
}


// 格式化音乐链接
function formatMusicUrl() {
    const urlInput = document.getElementById('backgroundMusicUrl');
    if (!urlInput) return;
    
    let url = urlInput.value.trim();
    if (!url) {
        showWarning('请先输入音乐链接');
        return;
    }
    
    // 如果不是完整URL，添加协议
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = 'https://' + url;
    }
    
    // 验证URL格式
    try {
        new URL(url);
        urlInput.value = url;
        showSuccess('音乐链接格式化成功');
    } catch (e) {
        showError('无效的URL格式');
    }
}

// 打开音乐链接工具
function openFormatTool() {
    // 创建模态框
    const modalHtml = `
        <div class="ui modal" id="formatToolModal">
            <i class="close icon" onclick="closeFormatToolModal()"></i>
            <div class="header">
                <i class="tools icon"></i> 音乐链接工具
            </div>
            <div class="content">
                <div class="ui form">
                    <div class="field">
                        <label>输入文本</label>
                        <textarea id="formatInput" rows="5" placeholder="输入需要格式化的文本..."></textarea>
                    </div>
                    <div class="field">
                        <label>格式化选项</label>
                        <div class="ui fluid multiple search selection dropdown" id="formatOptions">
                            <option value="json">JSON格式化</option>
                            <option value="url">URL编码/解码</option>
                            <option value="base64">Base64编码/解码</option>
                            <option value="timestamp">时间戳转换</option>
                            <option value="unicode">Unicode转中文</option>
                            <option value="html">HTML转义</option>
                        </div>
                    </div>
                    <div class="field">
                        <label>输出结果</label>
                        <textarea id="formatOutput" rows="5" readonly placeholder="格式化结果..."></textarea>
                    </div>
                </div>
            </div>
            <div class="actions">
                <div class="ui cancel button" onclick="closeFormatToolModal()">关闭</div>
                <div class="ui primary button" onclick="executeFormat()">执行格式化</div>
            </div>
        </div>
    `;
    
    // 添加到页面
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // 初始化模态框
    $('#formatToolModal').modal({
        closable: false,
        onShow: function() {
            // 初始化下拉框
            $('#formatOptions').dropdown();
        }
    }).modal('show');
}

// 关闭音乐链接工具模态框
function closeFormatToolModal() {
    $('#formatToolModal').modal('hide');
    setTimeout(() => {
        const modal = document.getElementById('formatToolModal');
        if (modal) modal.remove();
    }, 500);
}

// 执行格式化
function executeFormat() {
    const input = document.getElementById('formatInput').value.trim();
    const options = $('#formatOptions').dropdown('get value');
    const output = document.getElementById('formatOutput');
    
    if (!input) {
        showWarning('请输入需要格式化的文本');
        return;
    }
    
    if (!options || options.length === 0) {
        showWarning('请选择格式化选项');
        return;
    }
    
    try {
        let result = '';
        
        // 根据选择的选项执行不同的格式化
        if (options.includes('json')) {
            result = JSON.stringify(JSON.parse(input), null, 2);
        } else if (options.includes('url')) {
            // 检测是否已编码
            if (input.includes('%')) {
                result = decodeURIComponent(input);
            } else {
                result = encodeURIComponent(input);
            }
        } else if (options.includes('base64')) {
            // 检测是否是Base64
            if (/^[A-Za-z0-9+/]*={0,2}$/.test(input)) {
                result = atob(input);
            } else {
                result = btoa(input);
            }
        } else if (options.includes('timestamp')) {
            const timestamp = parseInt(input);
            if (!isNaN(timestamp)) {
                const date = new Date(timestamp * 1000);
                result = date.toString();
            } else {
                const date = new Date(input);
                result = Math.floor(date.getTime() / 1000).toString();
            }
        } else if (options.includes('unicode')) {
            result = input.replace(/\\u[\dA-Fa-f]{4}/g, (match) => {
                return String.fromCharCode(parseInt(match.replace(/\\u/g, ''), 16));
            });
        } else if (options.includes('html')) {
            const textarea = document.createElement('textarea');
            textarea.textContent = input;
            result = textarea.innerHTML;
        }
        
        output.value = result;
        showSuccess('格式化完成');
    } catch (e) {
        showError('格式化失败：' + e.message);
    }
}

// 现代风格日期选择器实现
function initModernDatePicker(type) {
    const prefix = type === 'start' ? 'start' : 'end';
    const calendarBtn = document.getElementById(`${prefix}DateCalendarBtn`);
    const calendar = document.getElementById(`${prefix}DateCalendar`);
    const dateInput = document.getElementById(`input${prefix === 'start' ? 'Start' : 'End'}DateDisplay`);
    const hiddenInput = document.getElementById(`input${prefix === 'start' ? 'Start' : 'End'}Date`);
    
    if (!calendarBtn || !calendar || !dateInput || !hiddenInput) return;
    
    let currentDate = new Date();
    let selectedDate = null;
    let currentMonth = currentDate.getMonth();
    let currentYear = currentDate.getFullYear();
    
    // 如果输入框已有值，初始化selectedDate
    if (hiddenInput.value && hiddenInput.value.length === 8) {
        const year = parseInt(hiddenInput.value.substring(0, 4));
        const month = parseInt(hiddenInput.value.substring(4, 6)) - 1;
        const day = parseInt(hiddenInput.value.substring(6, 8));
        selectedDate = new Date(year, month, day);
        currentMonth = selectedDate.getMonth();
        currentYear = selectedDate.getFullYear();
    }
    
    // 点击日历按钮显示/隐藏日历
    calendarBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        
        // 关闭其他日历
        const otherPrefix = type === 'start' ? 'end' : 'start';
        const otherCalendar = document.getElementById(`${otherPrefix}DateCalendar`);
        if (otherCalendar) {
            otherCalendar.style.display = 'none';
        }
        
        // 切换当前日历显示状态
        if (calendar.style.display === 'block') {
            calendar.style.display = 'none';
        } else {
            calendar.style.display = 'block';
            renderCalendar();
        }
    });
    
    // 点击页面其他地方关闭日历
    document.addEventListener('click', function(e) {
        if (!calendar.contains(e.target) && e.target !== calendarBtn) {
            calendar.style.display = 'none';
        }
    });
    
    // 渲染日历
    function renderCalendar() {
        const calendarTitle = calendar.querySelector('.calendar-title');
        const calendarDays = calendar.querySelector('.calendar-days');
        
        // 更新标题
        calendarTitle.textContent = `${currentYear}年${currentMonth + 1}月`;
        
        // 清空日期
        calendarDays.innerHTML = '';
        
        // 获取当月第一天和最后一天
        const firstDay = new Date(currentYear, currentMonth, 1);
        const lastDay = new Date(currentYear, currentMonth + 1, 0);
        const prevLastDay = new Date(currentYear, currentMonth, 0);
        
        // 获取第一天是星期几
        const firstDayOfWeek = firstDay.getDay();
        
        // 添加上月末尾日期
        for (let i = firstDayOfWeek - 1; i >= 0; i--) {
            const day = prevLastDay.getDate() - i;
            const dayElement = createDayElement(day, 'prev', new Date(currentYear, currentMonth - 1, day));
            calendarDays.appendChild(dayElement);
        }
        
        // 添加当月日期
        for (let day = 1; day <= lastDay.getDate(); day++) {
            const date = new Date(currentYear, currentMonth, day);
            const dayElement = createDayElement(day, 'current', date);
            
            // 如果是选中的日期，添加选中样式
            if (selectedDate && isSameDay(date, selectedDate)) {
                dayElement.classList.add('selected');
            }
            
            // 如果是今天，添加今天样式
            if (isSameDay(date, new Date())) {
                dayElement.classList.add('today');
            }
            
            calendarDays.appendChild(dayElement);
        }
        
        // 添加下月开始日期
        const remainingDays = 42 - (firstDayOfWeek + lastDay.getDate()); // 6行 * 7天 = 42
        for (let day = 1; day <= remainingDays; day++) {
            const dayElement = createDayElement(day, 'next', new Date(currentYear, currentMonth + 1, day));
            calendarDays.appendChild(dayElement);
        }
        
        // 添加月份导航事件
        const prevMonthBtn = calendar.querySelector('.prev-month');
        const nextMonthBtn = calendar.querySelector('.next-month');
        
        prevMonthBtn.onclick = function(e) {
            e.stopPropagation();
            currentMonth--;
            if (currentMonth < 0) {
                currentMonth = 11;
                currentYear--;
            }
            renderCalendar();
        };
        
        nextMonthBtn.onclick = function(e) {
            e.stopPropagation();
            currentMonth++;
            if (currentMonth > 11) {
                currentMonth = 0;
                currentYear++;
            }
            renderCalendar();
        };
    }
    
    // 创建日期元素
    function createDayElement(day, type, date) {
        const dayElement = document.createElement('div');
        dayElement.className = 'calendar-day';
        if (type !== 'current') {
            dayElement.classList.add(type);
        }
        dayElement.textContent = day;
        
        dayElement.addEventListener('click', function(e) {
            e.stopPropagation();
            selectDate(date);
        });
        
        return dayElement;
    }
    
    // 选择日期
    function selectDate(date) {
        selectedDate = date;
        
        // 更新输入框显示
        const formattedDate = formatDate(date);
        dateInput.value = formattedDate;
        
        // 更新隐藏输入框的值（YYYYMMDD格式）
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        hiddenInput.value = `${year}${month}${day}`;
        
        // 触发"仅一天"复选框逻辑
        const onlyOneDayEl = document.getElementById('onlyOneDay');
        if (onlyOneDayEl && onlyOneDayEl.checked) {
            const otherPrefix = type === 'start' ? 'end' : 'start';
            const otherDateInput = document.getElementById(`input${otherPrefix === 'start' ? 'Start' : 'End'}DateDisplay`);
            const otherHiddenInput = document.getElementById(`input${otherPrefix === 'start' ? 'Start' : 'End'}Date`);
            
            if (otherDateInput && otherHiddenInput) {
                otherDateInput.value = formattedDate;
                otherHiddenInput.value = hiddenInput.value;
            }
        }
        
        // 关闭日历
        calendar.style.display = 'none';
        
        // 重新渲染日历以显示选中状态
        renderCalendar();
    }
    
    // 格式化日期
    function formatDate(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }
    
    // 判断是否是同一天
    function isSameDay(date1, date2) {
        return date1.getFullYear() === date2.getFullYear() &&
               date1.getMonth() === date2.getMonth() &&
               date1.getDate() === date2.getDate();
    }
}

// ==================== 全局函数定义 ====================
// 以下函数需要在全局作用域中，以便 onclick 事件可以调用

// 加载JIT默认库存数量
async function loadJitDefaultNum() {
    try {
        const response = await requestPost('/api/jit_default_config', { action: 'get' });
        if (response && response.success) {
            const defaultNum = response.default_final_num;
            const hintEl = document.getElementById('jitDefaultNumHint');
            if (hintEl) {
                hintEl.textContent = `当前系统默认值：${defaultNum}`;
            }
        } else {
            const hintEl = document.getElementById('jitDefaultNumHint');
            if (hintEl) {
                hintEl.textContent = '获取默认值失败';
            }
        }
    } catch (error) {
        const hintEl = document.getElementById('jitDefaultNumHint');
        if (hintEl) {
            hintEl.textContent = '获取默认值失败';
        }
    }
}

// 通过货号搜索类目
async function searchCategoryByGoodsSn() {
    console.log('[searchCategoryByGoodsSn] 函数被调用');
    
    const selectedCheckboxes = document.querySelectorAll('#shopSelectionArea input[type="checkbox"]:checked');
    console.log('[searchCategoryByGoodsSn] 选中的店铺数量:', selectedCheckboxes.length);
    
    if (selectedCheckboxes.length === 0) {
        console.log('[searchCategoryByGoodsSn] 未选择店铺，显示警告');
        showWarning('请先勾选店铺');
        return;
    }

    const selectedShopUids = Array.from(selectedCheckboxes).map(cb => {
        console.log('[searchCategoryByGoodsSn] checkbox dataset.shop:', cb.dataset.shop);
        const shop = JSON.parse(cb.dataset.shop);
        return shop.uid;
    }).filter(uid => uid);
    
    console.log('[searchCategoryByGoodsSn] 有效的店铺UID列表:', selectedShopUids);

    if (selectedShopUids.length === 0) {
        console.log('[searchCategoryByGoodsSn] 没有有效的店铺UID');
        showWarning('请至少选择一个有效的店铺');
        return;
    }

    const goodsSnInput = document.getElementById('inputGoodsSn');
    console.log('[searchCategoryByGoodsSn] goodsSnInput:', goodsSnInput);
    
    // 货号转为大写，实现不区分大小写搜索
    const goodsSn = goodsSnInput ? goodsSnInput.value.trim().toUpperCase() : '';
    console.log('[searchCategoryByGoodsSn] 货号:', goodsSn);

    if (!goodsSn) {
        console.log('[searchCategoryByGoodsSn] 货号为空');
        showWarning('请输入货号');
        return;
    }

    const statusEl = document.getElementById('goodsSnSearchStatus');
    console.log('[searchCategoryByGoodsSn] statusEl:', statusEl);

    try {
        if (statusEl) {
            statusEl.textContent = '登录中...';
            statusEl.style.color = '#21ba45';
        }

        const uid = selectedShopUids[0];
        console.log('[searchCategoryByGoodsSn] 开始调用API, uid:', uid, 'goods_sn:', goodsSn);
        
        // 1. 调用后端API启动异步登录任务
        const startResult = await requestPost('/api/search_category_by_goods_sn', {}, { uid: uid, goods_sn: goodsSn });
        console.log('[searchCategoryByGoodsSn] API启动结果:', startResult);

        if (!startResult.success || !startResult.task_id) {
            if (statusEl) {
                statusEl.textContent = startResult.error_msg || '启动任务失败';
                statusEl.style.color = '#db2828';
            }
            return;
        }

        const task_id = startResult.task_id;

        // 2. 轮询获取任务结果
        let pollResult;
        let pollCount = 0;
        const maxPollCount = 120; // 最多轮询120次，每次1秒

        while (pollCount < maxPollCount) {
            pollResult = await requestPost('/api/get_goods_sn_category_result', {}, {
                task_id: task_id,
                uid: uid,
                goods_sn: goodsSn
            });
            
            if (pollResult.status === 'success') {
                break;
            } else if (pollResult.status === 'failed') {
                if (statusEl) {
                    statusEl.textContent = pollResult.error_msg || '登录或搜索失败';
                    statusEl.style.color = '#db2828';
                }
                // 检查是否是店铺登录失效的错误
                const errorMsg = pollResult.error_msg || '';
                if (errorMsg.includes('重新连接店铺') || errorMsg.includes('登录已失效')) {
                    showError('店铺登录已失效，请重新连接店铺');
                    loadShopList();
                } else {
                    showWarning(errorMsg);
                }
                return;
            } else if (pollResult.status === 'timeout') {
                if (statusEl) {
                    statusEl.textContent = '任务超时';
                    statusEl.style.color = '#db2828';
                }
                return;
            }
            
            pollCount++;
            await new Promise(resolve => setTimeout(resolve, 1000));
        }

        if (pollResult && pollResult.success && pollResult.data) {
            console.log('[searchCategoryByGoodsSn] 搜索成功，数据:', pollResult.data);
            const resultDiv = document.getElementById('goodsSnCategoryResult');
            const nameSpan = document.getElementById('goodsSnCategoryName');
            const idInput = document.getElementById('goodsSnCategoryId');
            
            console.log('[searchCategoryByGoodsSn] DOM元素:', { resultDiv, nameSpan, idInput });

            if (resultDiv && nameSpan && idInput) {
                // 后端返回的是 cat_ids 和 cat_names 列表格式
                const catIds = pollResult.data.cat_ids || [];
                const catNames = pollResult.data.cat_names || [];
                
                // 显示类目路径（用 > 分隔）
                nameSpan.textContent = catNames.join(' > ') || '未知类目';
                // 存储 JSON 格式的完整数据
                idInput.value = JSON.stringify({ cat_ids: catIds, cat_names: catNames });
                resultDiv.style.display = 'block';
                console.log('[searchCategoryByGoodsSn] 已更新DOM显示, cat_ids:', catIds, 'cat_names:', catNames);
            }

            if (statusEl) {
                statusEl.textContent = '匹配成功';
                statusEl.style.color = '#52c41a';
            }
            showSuccess('类目匹配成功');
        } else {
            console.log('[searchCategoryByGoodsSn] 搜索失败或无数据:', pollResult ? pollResult.error_msg : '无结果');
            if (statusEl) {
                statusEl.textContent = '未找到匹配的类目（仅支持搜索店铺内已有的类目，如需搜索其他类目请切换到"关键词搜索"标签页）';
                statusEl.style.color = '#ff4d4f';
            }
            showWarning(pollResult ? pollResult.error_msg : '未找到匹配的类目');
        }
    } catch (error) {
        console.error('[searchCategoryByGoodsSn] 捕获到异常:', error);
        if (statusEl) {
            statusEl.textContent = '搜索失败';
            statusEl.style.color = '#ff4d4f';
        }
        showError('货号搜索类目失败');
    }
}

// 清除货号搜索类目结果
function clearGoodsSnCategory() {
    console.log('[clearGoodsSnCategory] 函数被调用');
    const resultDiv = document.getElementById('goodsSnCategoryResult');
    const nameSpan = document.getElementById('goodsSnCategoryName');
    const idInput = document.getElementById('goodsSnCategoryId');
    const statusEl = document.getElementById('goodsSnSearchStatus');

    if (resultDiv) resultDiv.style.display = 'none';
    if (nameSpan) nameSpan.textContent = '';
    if (idInput) idInput.value = '';
    if (statusEl) {
        statusEl.textContent = '搜索店铺内已有的商品类目（只能搜索到店铺内已有的类目，如需搜索其他类目请切换到"类目选择"标签页）';
        statusEl.style.color = '#666';
    }
}

// 保存货号搜索类目结果
async function saveGoodsSnCategory() {
    console.log('[saveGoodsSnCategory] 函数被调用');
    
    const idInput = document.getElementById('goodsSnCategoryId');
    const nameSpan = document.getElementById('goodsSnCategoryName');
    
    if (!idInput || !idInput.value) {
        showWarning('没有可保存的类目数据');
        return;
    }
    
    try {
        // 解析存储的 JSON 数据
        const categoryDataParsed = JSON.parse(idInput.value);
        const catIds = categoryDataParsed.cat_ids || [];
        const catNames = categoryDataParsed.cat_names || [];
        
        if (!catIds.length) {
            showWarning('类目数据格式错误');
            return;
        }
        
        // 构建类目数据结构（与类目选择保持一致）
        const categoryData = [{
            cat_ids: catIds,
            cat_names: catNames
        }];
        
        const result = await requestPost('/api/save_saved_category_list', {}, { category_list: categoryData });
        
        if (result.success) {
            showSuccess('类目保存成功');
            // 保存成功后刷新类目列表
            await loadSavedCategoryList();
        } else {
            showWarning(result.error_msg || '保存失败');
        }
    } catch (error) {
        console.error('[saveGoodsSnCategory] 保存失败:', error);
        showError('保存失败');
    }
}

console.log('[main.js] 全局函数 searchCategoryByGoodsSn 和 clearGoodsSnCategory 已定义');
