// 音乐播放器模块
class MusicPlayer {
    constructor() {
        this.audio = null;
        this.isPlaying = false;
        this.playerElement = null;
        this.progressElement = null;
        this.timeDisplay = null;
        this.playPauseBtn = null;
        this.musicUrl = '';
        
        // 自动播放相关属性
        this.userInteracted = false;
        this.pageLoadTime = performance.now();
        this.interactionListenerSet = false;
        this.autoplayAttempted = false;
        
        // 本地音乐相关属性
        this.isLocalMode = false;
        this.localMusicList = [];
        this.currentLocalIndex = -1;
        this.lastPlayedIndex = -1;
        
        this.init();
    }

    init() {
        // 从配置中加载音乐URL
        this.loadMusicUrl();
        
        // 只有在背景音乐启用时才创建播放器UI
        if (this.shouldShowPlayer()) {
            // 创建播放器UI
            this.createPlayerUI();
            // 绑定事件
            this.bindEvents();
        }
    }

    updateDiscImage() {
        // 获取自定义光碟图片路径
        if (window.backgroundMusicSettings && window.backgroundMusicSettings.discImage) {
            this.discImage.src = window.backgroundMusicSettings.discImage;
            this.discImage.style.display = 'block';
        } else {
            // 使用默认图片
            this.discImage.src = '/static/images/default-disc.png';
        }
    }

    shouldShowPlayer() {
        // 检查背景音乐是否启用
        if (window.backgroundMusicSettings && window.backgroundMusicSettings.enabled === "是") {
            return true;
        }
        return false;
    }

    createPlayerUI() {
        // 创建播放器容器
        this.playerElement = document.createElement('div');
        this.playerElement.id = 'music-player';
        this.playerElement.className = 'music-player';
        
        // 播放器HTML结构
        this.playerElement.innerHTML = `
            <div class="player-container">
                <div class="disc-container">
                    <div class="disc">
                        <div class="disc-center"></div>
                        <div class="disc-rotate">
                            <img class="disc-image" src="/static/images/default-disc.png" alt="音乐光碟" onerror="this.style.display='none'">
                        </div>
                    </div>
                </div>
                <div class="player-controls">
                    <div class="player-info">
                        <div class="song-title">背景音乐</div>
                        <div class="time-display">
                            <span id="current-time">0:00</span> / <span id="total-time">0:00</span>
                        </div>
                    </div>
                    <div class="progress-container">
                        <div class="progress-bar">
                            <div class="progress-fill" id="progress-fill"></div>
                        </div>
                    </div>
                    <div class="control-buttons">
                        <button id="prev-btn" class="control-btn" title="上一首">
                            <i class="fas fa-step-backward"></i>
                        </button>
                        <button id="play-pause-btn" class="play-btn">
                            <i class="fas fa-play"></i>
                        </button>
                        <button id="next-btn" class="control-btn" title="下一首">
                            <i class="fas fa-step-forward"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        // 添加到页面
        document.body.appendChild(this.playerElement);
        
        // 获取元素引用
        this.playPauseBtn = document.getElementById('play-pause-btn');
        this.prevBtn = document.getElementById('prev-btn');
        this.nextBtn = document.getElementById('next-btn');
        this.progressFill = document.getElementById('progress-fill');
        this.currentTimeEl = document.getElementById('current-time');
        this.totalTimeEl = document.getElementById('total-time');
        this.discImage = document.querySelector('.disc-image');

        // 设置自定义光碟图片
        this.updateDiscImage();
    }

    bindEvents() {
        // 播放/暂停按钮点击事件
        this.playPauseBtn.addEventListener('click', () => {
            this.togglePlayPause();
        });

        // 上一首按钮点击事件
        this.prevBtn.addEventListener('click', () => {
            this.playPrevTrack();
        });

        // 下一首按钮点击事件
        this.nextBtn.addEventListener('click', () => {
            this.playNextTrack();
        });

        // 进度条点击事件
        const progressBar = document.querySelector('.progress-bar');
        progressBar.addEventListener('click', (e) => {
            if (this.audio) {
                const rect = progressBar.getBoundingClientRect();
                const percent = (e.clientX - rect.left) / rect.width;
                this.audio.currentTime = percent * this.audio.duration;
            }
        });
    }

    loadMusicUrl() {
        // 检查背景音乐是否启用
        if (window.backgroundMusicSettings && window.backgroundMusicSettings.enabled !== "是") {
            console.log('背景音乐未启用，不加载音频');
            return;
        }
        
        // 检查是否启用了本地音乐模式
        if (window.backgroundMusicSettings && window.backgroundMusicSettings.local === "是") {
            this.isLocalMode = true;
            this.loadLocalMusicList();
            return;
        }
        
        // 优先使用从服务器传递的设置
        if (window.backgroundMusicSettings && window.backgroundMusicSettings.enabled === "是" && window.backgroundMusicSettings.url) {
            this.musicUrl = window.backgroundMusicSettings.url;
            this.loadAudio(this.musicUrl);
            return;
        }
        
        // 从服务器获取背景音乐配置
        fetch('/api/get_setting?name=background_music_enabled')
            .then(response => response.json())
            .then(data => {
                if (data.success && data.value === "是") {
                    // 背景音乐已启用，获取音乐URL
                    return fetch('/api/get_setting?name=background_music_url');
                } else {
                    // 背景音乐未启用，不加载
                    return Promise.reject('背景音乐未启用');
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success && data.value) {
                    this.musicUrl = data.value;
                    this.loadAudio(this.musicUrl);
                }
            })
            .catch(error => {
                console.log('背景音乐未设置或未启用:', error);
            });
    }
    
    // 加载本地音乐列表
    async loadLocalMusicList() {
        try {
            // 获取当前token（从全局变量或URL参数）
            const token = window.currentToken || new URLSearchParams(window.location.search).get('token') || '';
            const response = await fetch(`/api/local_music_list?token=${token}`);
            const data = await response.json();
            if (data.success && data.data && data.data.length > 0) {
                this.localMusicList = data.data;
                console.log('本地音乐列表加载成功，共', this.localMusicList.length, '首');
                // 随机播放一首
                this.playRandomLocalMusic();
            } else {
                console.log('本地音乐列表为空');
                this.isLocalMode = false;
            }
        } catch (error) {
            console.log('加载本地音乐列表失败:', error);
            this.isLocalMode = false;
        }
    }
    
    // 随机选择下一首本地音乐（保证不重复播放上一首）
    playRandomLocalMusic() {
        if (this.localMusicList.length === 0) return;
        
        let nextIndex;
        if (this.localMusicList.length === 1) {
            // 只有一首时直接播放
            nextIndex = 0;
        } else {
            // 随机选择，确保不与上一首相同
            do {
                nextIndex = Math.floor(Math.random() * this.localMusicList.length);
            } while (nextIndex === this.lastPlayedIndex);
        }
        
        this.currentLocalIndex = nextIndex;
        this.lastPlayedIndex = nextIndex;
        
        const track = this.localMusicList[nextIndex];
        console.log('播放本地音乐:', track.name);
        
        // 更新歌曲标题
        const songTitle = document.querySelector('.song-title');
        if (songTitle) {
            songTitle.textContent = track.name;
        }
        
        // 加载并播放
        this.loadAudio(track.url);
        // 本地音乐不循环，播放完切换下一首
        if (this.audio) {
            this.audio.loop = false;
        }
    }

    // 播放上一首
    playPrevTrack() {
        if (!this.isLocalMode || this.localMusicList.length === 0) {
            console.log('非本地音乐模式或列表为空，无法切换上一首');
            return;
        }

        let prevIndex;
        if (this.localMusicList.length === 1) {
            prevIndex = 0;
        } else {
            // 切换到上一首（循环）
            prevIndex = this.currentLocalIndex - 1;
            if (prevIndex < 0) {
                prevIndex = this.localMusicList.length - 1;
            }
        }

        this.currentLocalIndex = prevIndex;
        this.lastPlayedIndex = prevIndex;

        const track = this.localMusicList[prevIndex];
        console.log('播放上一首:', track.name);

        // 更新歌曲标题
        const songTitle = document.querySelector('.song-title');
        if (songTitle) {
            songTitle.textContent = track.name;
        }

        // 加载并播放
        this.loadAudio(track.url);
        if (this.audio) {
            this.audio.loop = false;
        }
        this.play();
    }

    // 播放下一首
    playNextTrack() {
        if (!this.isLocalMode || this.localMusicList.length === 0) {
            console.log('非本地音乐模式或列表为空，无法切换下一首');
            return;
        }

        // 使用随机播放逻辑选择下一首
        this.playRandomLocalMusic();
        this.play();
    }

    loadAudio(url) {
        if (!url) return;

        console.log('开始加载音频:', url);

        // 如果已有音频对象，先销毁
        if (this.audio) {
            this.audio.pause();
            this.audio.removeEventListener('timeupdate', this.updateProgress.bind(this));
            this.audio.removeEventListener('loadedmetadata', this.updateDuration.bind(this));
            this.audio.removeEventListener('ended', this.onAudioEnded.bind(this));
            this.audio.removeEventListener('canplay', this.onCanPlay.bind(this));
        }

        // 本地音乐模式需要添加token参数
        let audioUrl = url;
        if (this.isLocalMode && url.includes('/api/local_music/')) {
            const token = window.currentToken || new URLSearchParams(window.location.search).get('token') || '';
            audioUrl = `${url}?token=${token}`;
        }

        // 创建新的音频对象
        this.audio = new Audio(audioUrl);
        // 本地音乐模式不循环（播放完自动切换下一首），其他模式循环播放
        this.audio.loop = !this.isLocalMode;
        this.audio.preload = 'auto';
        this.audio.volume = 1;
        
        // 绑定音频事件
        this.audio.addEventListener('timeupdate', this.updateProgress.bind(this));
        this.audio.addEventListener('loadedmetadata', this.updateDuration.bind(this));
        this.audio.addEventListener('ended', this.onAudioEnded.bind(this));
        this.audio.addEventListener('canplay', this.onCanPlay.bind(this));
        
        // 保存URL
        this.musicUrl = url;
        localStorage.setItem('background_music_url', url);
    }

    onCanPlay() {
        // 检查是否需要自动播放
        if (window.backgroundMusicSettings && window.backgroundMusicSettings.autoplay === "是") {
            // 检查用户是否已经与页面交互
            if (this.hasUserInteracted()) {
                // 用户已交互，直接播放
                this.attemptAutoplay();
            } else {
                // 用户未交互，设置交互监听器
                this.setupInteractionListener();
            }
        }
    }
    
    // 检查用户是否已经与页面交互
    hasUserInteracted() {
        // 检查各种用户交互事件
        return this.userInteracted || 
               document.visibilityState === 'visible' && 
               (performance.now() - this.pageLoadTime > 1000);
    }
    
    // 设置用户交互监听器
    setupInteractionListener() {
        if (this.interactionListenerSet) return;
        
        this.interactionListenerSet = true;
        
        // 监听各种用户交互事件
        const interactionEvents = ['click', 'touchstart', 'keydown', 'scroll', 'mousemove'];
        
        const handleInteraction = () => {
            this.userInteracted = true;
            // 用户交互后尝试自动播放
            this.attemptAutoplay();
            // 移除事件监听器
            interactionEvents.forEach(event => {
                document.removeEventListener(event, handleInteraction, { once: true, passive: true });
            });
        };
        
        // 添加事件监听器
        interactionEvents.forEach(event => {
            document.addEventListener(event, handleInteraction, { once: true, passive: true });
        });
        
        // 设置一个定时器，在一定时间后也尝试播放
        setTimeout(() => {
            if (!this.userInteracted) {
                this.userInteracted = true;
                this.attemptAutoplay();
            }
        }, 3000);
    }
    
    // 尝试自动播放
    attemptAutoplay() {
        if (this.autoplayAttempted) return;
        this.autoplayAttempted = true;
        
        // 创建并播放一个静音的音频，以"唤醒"音频上下文
        const silentAudio = new Audio();
        silentAudio.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';
        silentAudio.volume = 0;
        silentAudio.play().catch(() => {
            // 忽略错误
        }).then(() => {
            // 静音音频播放成功，现在尝试播放实际音频
            setTimeout(() => {
                this.playWithFallback();
            }, 100);
        });
        
        // 如果静音音频方法失败，直接尝试播放
        setTimeout(() => {
            if (!this.isPlaying) {
                this.playWithFallback();
            }
        }, 200);
    }
    
    // 带回退机制的播放方法
    playWithFallback() {
        // 先尝试正常播放
        this.audio.play()
            .then(() => {
                this.isPlaying = true;
                this.updatePlayPauseButton();
                const discElement = document.querySelector('.disc-rotate');
                if (discElement) discElement.style.animationPlayState = 'running';
                console.log('背景音乐自动播放成功');
            })
            .catch((error) => {
                console.log('自动播放失败，尝试静音播放:', error);
                // 尝试静音播放
                this.audio.volume = 0;
                this.audio.play()
                    .then(() => {
                        this.isPlaying = true;
                        this.updatePlayPauseButton();
                        const discElement = document.querySelector('.disc-rotate');
                        if (discElement) discElement.style.animationPlayState = 'running';
                        console.log('背景音乐静音播放成功');
                        
                        // 显示静音播放提示
                        this.showSilentPlayNotification();
                        
                        // 平滑恢复音量到满音量
                        this.fadeInVolume(0, 1, 2000);
                    })
                    .catch((fallbackError) => {
                        console.log('静音播放也失败:', fallbackError);
                        // 显示提示，让用户手动播放
                        this.showAutoplayPrompt();
                    });
            });
    }
    
    // 显示自动播放提示
    showAutoplayPrompt() {
        // 检查是否已经显示过提示
        if (localStorage.getItem('autoplay_prompt_shown') === 'true') return;
        
        // 创建提示元素
        const prompt = document.createElement('div');
        prompt.className = 'autoplay-prompt';
        prompt.innerHTML = `
            <div class="autoplay-prompt-content">
                <i class="music icon"></i>
                <span>浏览器阻止了自动播放，点击此处播放背景音乐</span>
                <button class="ui mini button">播放</button>
            </div>
        `;
        
        // 添加样式
        prompt.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 9999;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 10px 15px;
            border-radius: 8px;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 10px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            animation: slideInRight 0.5s ease-out;
            max-width: 300px;
        `;
        
        // 添加CSS动画
        if (!document.querySelector('#autoplay-prompt-styles')) {
            const style = document.createElement('style');
            style.id = 'autoplay-prompt-styles';
            style.textContent = `
                @keyframes slideInRight {
                    from {
                        transform: translateX(100%);
                        opacity: 0;
                    }
                    to {
                        transform: translateX(0);
                        opacity: 1;
                    }
                }
                .autoplay-prompt-content {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }
                .autoplay-prompt button {
                    margin-left: auto;
                }
            `;
            document.head.appendChild(style);
        }
        
        // 添加到页面
        document.body.appendChild(prompt);
        
        // 绑定点击事件
        const playButton = prompt.querySelector('button');
        playButton.addEventListener('click', () => {
            this.play();
            document.body.removeChild(prompt);
            localStorage.setItem('autoplay_prompt_shown', 'true');
        });
        
        // 5秒后自动隐藏
        setTimeout(() => {
            if (document.body.contains(prompt)) {
                document.body.removeChild(prompt);
            }
        }, 5000);
    }
    
    // 音量淡入效果
    fadeInVolume(startVolume, endVolume, duration) {
        const volumeStep = (endVolume - startVolume) / (duration / 50); // 每50ms更新一次
        let currentVolume = startVolume;
        
        const fadeInterval = setInterval(() => {
            currentVolume += volumeStep;
            
            if (currentVolume >= endVolume) {
                currentVolume = endVolume;
                clearInterval(fadeInterval);
                console.log('音量淡入完成，当前音量:', currentVolume);
            }
            
            this.audio.volume = currentVolume;
        }, 50);
    }
    
    // 显示静音播放通知
    showSilentPlayNotification() {
        // 检查是否已经显示过静音播放提示
        if (localStorage.getItem('silent_play_notification_shown') === 'true') return;
        
        // 创建通知元素
        const notification = document.createElement('div');
        notification.className = 'silent-play-notification';
        notification.innerHTML = `
            <div class="notification-content">
                <i class="volume up icon"></i>
                <span>背景音乐正在静音播放中，音量将逐渐恢复</span>
            </div>
        `;
        
        // 添加样式
        notification.style.cssText = `
            position: fixed;
            bottom: 80px;
            right: 20px;
            z-index: 9998;
            background: rgba(33, 186, 69, 0.9);
            color: white;
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 10px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            animation: slideInRight 0.5s ease-out, fadeOut 0.5s ease-out 3.5s forwards;
            max-width: 320px;
        `;
        
        // 添加CSS动画
        if (!document.querySelector('#silent-play-notification-styles')) {
            const style = document.createElement('style');
            style.id = 'silent-play-notification-styles';
            style.textContent = `
                @keyframes fadeOut {
                    from {
                        opacity: 1;
                    }
                    to {
                        opacity: 0;
                    }
                }
                .notification-content {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }
            `;
            document.head.appendChild(style);
        }
        
        // 添加到页面
        document.body.appendChild(notification);
        
        // 4秒后移除通知
        setTimeout(() => {
            if (document.body.contains(notification)) {
                document.body.removeChild(notification);
            }
        }, 4000);
        
        // 标记已显示过
        localStorage.setItem('silent_play_notification_shown', 'true');
    }

    togglePlayPause() {
        if (!this.audio) {
            if (this.musicUrl) {
                this.loadAudio(this.musicUrl);
            } else {
                // 如果没有音乐URL，尝试从配置中获取
                this.fetchMusicUrl();
                return;
            }
        }
        
        if (this.isPlaying) {
            this.pause();
        } else {
            this.play();
        }
    }

    play() {
        if (!this.audio) return;
        
        this.audio.play()
            .then(() => {
                this.isPlaying = true;
                this.updatePlayPauseButton();
                document.querySelector('.disc-rotate').style.animationPlayState = 'running';
            })
            .catch((error) => {
                console.error('播放失败:', error);
                this.showNotification('播放失败，请检查音乐链接是否有效');
            });
    }

    pause() {
        if (!this.audio) return;
        
        this.audio.pause();
        this.isPlaying = false;
        this.updatePlayPauseButton();
        document.querySelector('.disc-rotate').style.animationPlayState = 'paused';
    }

    updatePlayPauseButton() {
        const icon = this.playPauseBtn.querySelector('i');
        if (this.isPlaying) {
            icon.className = 'fas fa-pause';
        } else {
            icon.className = 'fas fa-play';
        }
    }

    updateProgress() {
        if (!this.audio) return;
        
        if (isNaN(this.audio.duration) || !isFinite(this.audio.duration)) return;
        
        const percent = (this.audio.currentTime / this.audio.duration) * 100;
        this.progressFill.style.width = `${percent}%`;
        this.currentTimeEl.textContent = this.formatTime(this.audio.currentTime);
    }

    updateDuration() {
        if (!this.audio) return;
        
        if (isNaN(this.audio.duration) || !isFinite(this.audio.duration)) return;
        
        this.totalTimeEl.textContent = this.formatTime(this.audio.duration);
    }

    onAudioEnded() {
        // 本地音乐模式：播放结束时自动播放下一首随机曲目
        if (this.isLocalMode && this.localMusicList.length > 0) {
            this.playRandomLocalMusic();
            this.play();
            return;
        }
        
        // 因为设置了循环播放，这个事件通常不会触发
        if (!this.audio.loop) {
            this.isPlaying = false;
            this.updatePlayPauseButton();
            document.querySelector('.disc-rotate').style.animationPlayState = 'paused';
        }
    }

    formatTime(seconds) {
        if (isNaN(seconds)) return '0:00';
        
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = Math.floor(seconds % 60);
        return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
    }

    fetchMusicUrl() {
        // 从服务器获取音乐URL配置
        this.loadMusicUrl();
        if (this.audio) {
            this.play();
        }
    }

    showNotification(message) {
        // 创建一个简单的通知
        const notification = document.createElement('div');
        notification.className = 'music-notification';
        notification.textContent = message;
        notification.style.position = 'fixed';
        notification.style.bottom = '120px';
        notification.style.right = '20px';
        notification.style.backgroundColor = 'rgba(0, 0, 0, 0.7)';
        notification.style.color = 'white';
        notification.style.padding = '10px 15px';
        notification.style.borderRadius = '4px';
        notification.style.zIndex = '9999';
        notification.style.opacity = '0';
        notification.style.transition = 'opacity 0.3s';
        
        document.body.appendChild(notification);
        
        // 显示通知
        setTimeout(() => {
            notification.style.opacity = '1';
        }, 10);
        
        // 3秒后隐藏
        setTimeout(() => {
            notification.style.opacity = '0';
            setTimeout(() => {
                document.body.removeChild(notification);
            }, 300);
        }, 3000);
    }

    // 公共方法：更新音乐URL
    updateMusicUrl(url) {
        if (url) {
            this.loadAudio(url);
            if (this.isPlaying) {
                this.play();
            }
        }
    }

    // 公共方法：更新光碟图片
    updateDiscImageUrl(url) {
        if (this.discImage && url) {
            this.discImage.src = url;
            this.discImage.style.display = 'block';
        }
    }

    // 公共方法：显示或隐藏播放器
    togglePlayerVisibility(enabled) {
        if (enabled === "是" && !this.playerElement) {
            // 如果需要显示播放器但不存在，则创建
            this.createPlayerUI();
            this.bindEvents();
            // 重新加载音乐URL
            this.loadMusicUrl();
        } else if (enabled !== "是" && this.playerElement) {
            // 如果需要隐藏播放器且存在，则移除
            if (this.audio) {
                this.audio.pause();
                this.audio = null;
            }
            this.isPlaying = false;
            this.isLocalMode = false;
            this.localMusicList = [];
            this.currentLocalIndex = -1;
            this.lastPlayedIndex = -1;
            document.body.removeChild(this.playerElement);
            this.playerElement = null;
        }
    }
}

// 页面加载完成后初始化音乐播放器
document.addEventListener('DOMContentLoaded', () => {
    window.musicPlayer = new MusicPlayer();
});

// 监听设置更新事件，用于实时更新音乐URL和播放器可见性
window.addEventListener('settingsUpdated', (event) => {
    if (event.detail) {
        // 如果背景音乐URL发生变化，更新音乐URL
        if (event.detail.background_music_url) {
            window.musicPlayer.updateMusicUrl(event.detail.background_music_url);
        }
        
        // 如果背景音乐启用状态发生变化，显示或隐藏播放器
        if (event.detail.background_music_enabled !== undefined) {
            window.musicPlayer.togglePlayerVisibility(event.detail.background_music_enabled);
        }
        
        // 如果光碟图片路径发生变化，更新光碟图片
        if (event.detail.background_music_disc_image) {
            window.musicPlayer.updateDiscImageUrl(event.detail.background_music_disc_image);
        }
        
        // 如果本地音乐设置发生变化，切换模式
        if (event.detail.background_music_local !== undefined) {
            const wasLocal = window.musicPlayer.isLocalMode;
            window.musicPlayer.isLocalMode = event.detail.background_music_local === "是";
            
            if (window.musicPlayer.isLocalMode && !wasLocal) {
                // 切换到本地音乐模式
                window.musicPlayer.loadLocalMusicList();
            } else if (!window.musicPlayer.isLocalMode && wasLocal) {
                // 切换回在线音乐模式
                window.musicPlayer.localMusicList = [];
                window.musicPlayer.currentLocalIndex = -1;
                window.musicPlayer.lastPlayedIndex = -1;
                // 恢复歌曲标题
                const songTitle = document.querySelector('.song-title');
                if (songTitle) {
                    songTitle.textContent = '背景音乐';
                }
                // 重新加载在线音乐
                window.musicPlayer.loadMusicUrl();
            }
        }
    }
});