// Voice UI for MelkID
class VoiceUI {
    constructor() {
        this.recognition = null;
        this.synthesis = window.speechSynthesis;
        this.isListening = false;
        this.isSupported = this.checkSupport();
        this.commands = this.initCommands();
        this.init();
    }

    checkSupport() {
        return 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window;
    }

    init() {
        if (!this.isSupported) {
            console.log('🎤 Voice recognition not supported in this browser');
            return;
        }

        this.setupRecognition();
        this.createVoiceButton();
        this.setupKeyboardShortcuts();
    }

    setupRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        this.recognition = new SpeechRecognition();
        
        this.recognition.continuous = false;
        this.recognition.interimResults = false;
        this.recognition.lang = 'fa-IR'; // Persian language
        this.recognition.maxAlternatives = 3;

        this.recognition.onstart = () => {
            console.log('🎤 Voice recognition started');
            this.isListening = true;
            this.updateVoiceButton();
            this.showListeningIndicator();
        };

        this.recognition.onend = () => {
            console.log('🎤 Voice recognition ended');
            this.isListening = false;
            this.updateVoiceButton();
            this.hideListeningIndicator();
        };

        this.recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript.trim();
            console.log('🗣️ Voice input:', transcript);
            this.processVoiceCommand(transcript);
        };

        this.recognition.onerror = (event) => {
            console.error('🎤 Voice recognition error:', event.error);
            this.speak('متأسفم، صدای شما را نشنیدم. لطفاً دوباره تلاش کنید.');
            this.isListening = false;
            this.updateVoiceButton();
            this.hideListeningIndicator();
        };
    }

    initCommands() {
        return {
            // Navigation commands
            'صفحه اصلی': () => this.navigate('/'),
            'خانه': () => this.navigate('/'),
            'داشبورد': () => this.navigate('/dashboard/'),
            'پنل کاربری': () => this.navigate('/dashboard/'),
            'خدمات': () => this.navigate('/services/'),
            'املاک': () => this.navigate('/properties/'),
            'پرداخت': () => this.navigate('/dashboard/payments/'),
            'پرداخت ها': () => this.navigate('/dashboard/payments/'),
            'پیام ها': () => this.navigate('/dashboard/messages/'),
            'اعلانات': () => this.navigate('/dashboard/messages/'),

            // Search commands
            'جستجو': () => this.focusSearch(),
            'پیدا کن': () => this.focusSearch(),
            'جست و جو': () => this.focusSearch(),

            // Theme commands
            'تم تاریک': () => this.changeTheme('dark'),
            'حالت تاریک': () => this.changeTheme('dark'),
            'تم روشن': () => this.changeTheme('light'),
            'حالت روشن': () => this.changeTheme('light'),

            // Form commands
            'ثبت درخواست': () => this.navigate('/services/request/'),
            'درخواست جدید': () => this.navigate('/services/request/'),
            'پیگیری درخواست': () => this.navigate('/dashboard/track-requests/'),

            // Help commands
            'راهنما': () => this.showHelp(),
            'کمک': () => this.showHelp(),
            'دستورات صوتی': () => this.showVoiceCommands(),

            // System commands
            'خروج': () => this.logout(),
            'تنظیمات': () => this.navigate('/settings/'),
            'پروفایل': () => this.navigate('/profile/'),
        };
    }

    createVoiceButton() {
        const button = document.createElement('button');
        button.className = 'voice-button';
        button.innerHTML = '🎤';
        button.title = 'دستور صوتی (Ctrl+Space)';
        button.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 1000;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            border: none;
            background: var(--primary-color);
            color: white;
            font-size: 1.5rem;
            cursor: pointer;
            box-shadow: var(--shadow-lg);
            transition: var(--transition);
            display: flex;
            align-items: center;
            justify-content: center;
        `;

        button.addEventListener('click', () => {
            this.toggleListening();
        });

        document.body.appendChild(button);
        this.voiceButton = button;
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl+Space to toggle voice recognition
            if (e.ctrlKey && e.code === 'Space') {
                e.preventDefault();
                this.toggleListening();
            }
        });
    }

    toggleListening() {
        if (!this.isSupported) {
            this.speak('متأسفم، مرورگر شما از تشخیص صدا پشتیبانی نمی‌کند.');
            return;
        }

        if (this.isListening) {
            this.stopListening();
        } else {
            this.startListening();
        }
    }

    startListening() {
        try {
            this.recognition.start();
            this.speak('در حال گوش دادن...');
        } catch (error) {
            console.error('Error starting voice recognition:', error);
            this.speak('خطا در شروع تشخیص صدا');
        }
    }

    stopListening() {
        if (this.recognition) {
            this.recognition.stop();
        }
    }

    updateVoiceButton() {
        if (this.voiceButton) {
            if (this.isListening) {
                this.voiceButton.style.background = 'var(--danger-color)';
                this.voiceButton.innerHTML = '⏹️';
                this.voiceButton.classList.add('animate-pulse');
            } else {
                this.voiceButton.style.background = 'var(--primary-color)';
                this.voiceButton.innerHTML = '🎤';
                this.voiceButton.classList.remove('animate-pulse');
            }
        }
    }

    showListeningIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'listening-indicator';
        indicator.innerHTML = `
            <div class="listening-animation">
                <div class="wave"></div>
                <div class="wave"></div>
                <div class="wave"></div>
            </div>
            <p>در حال گوش دادن...</p>
        `;
        indicator.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            z-index: 2000;
            background: var(--glass-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--glass-border);
            border-radius: var(--border-radius-lg);
            padding: 2rem;
            text-align: center;
            color: var(--text-primary);
            box-shadow: var(--glass-shadow);
        `;

        // Add wave animation styles
        const style = document.createElement('style');
        style.textContent = `
            .listening-animation {
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 4px;
                margin-bottom: 1rem;
            }
            .wave {
                width: 4px;
                height: 20px;
                background: var(--primary-color);
                border-radius: 2px;
                animation: wave 1.2s ease-in-out infinite;
            }
            .wave:nth-child(2) { animation-delay: 0.1s; }
            .wave:nth-child(3) { animation-delay: 0.2s; }
            @keyframes wave {
                0%, 100% { transform: scaleY(1); }
                50% { transform: scaleY(2); }
            }
        `;
        document.head.appendChild(style);

        document.body.appendChild(indicator);
        this.listeningIndicator = indicator;
    }

    hideListeningIndicator() {
        if (this.listeningIndicator) {
            this.listeningIndicator.remove();
            this.listeningIndicator = null;
        }
    }

    processVoiceCommand(transcript) {
        const command = transcript.toLowerCase().trim();
        console.log('Processing voice command:', command);

        // Check for exact matches first
        if (this.commands[command]) {
            this.commands[command]();
            this.speak('انجام شد');
            return;
        }

        // Check for partial matches
        for (const [key, action] of Object.entries(this.commands)) {
            if (command.includes(key.toLowerCase()) || key.toLowerCase().includes(command)) {
                action();
                this.speak(`${key} انجام شد`);
                return;
            }
        }

        // Handle search queries
        if (command.startsWith('جستجو برای') || command.startsWith('پیدا کن')) {
            const searchTerm = command.replace(/^(جستجو برای|پیدا کن)\s+/, '');
            this.performSearch(searchTerm);
            return;
        }

        // Handle form filling
        if (command.startsWith('بنویس') || command.startsWith('وارد کن')) {
            const text = command.replace(/^(بنویس|وارد کن)\s+/, '');
            this.fillActiveInput(text);
            return;
        }

        // If no command matched, try to search
        this.performSearch(command);
        this.speak(`جستجو برای ${command}`);
    }

    navigate(url) {
        window.location.href = url;
    }

    focusSearch() {
        const searchInput = document.querySelector('input[type="search"], input[name*="search"], .search-input');
        if (searchInput) {
            searchInput.focus();
            this.speak('جعبه جستجو فعال شد');
        } else {
            this.speak('جعبه جستجو یافت نشد');
        }
    }

    changeTheme(theme) {
        const themeManager = window.themeManager;
        if (themeManager) {
            themeManager.setTheme(theme);
            this.speak(`تم ${theme === 'dark' ? 'تاریک' : 'روشن'} فعال شد`);
        }
    }

    performSearch(query) {
        const searchInput = document.querySelector('input[type="search"], input[name*="search"], .search-input');
        if (searchInput) {
            searchInput.value = query;
            searchInput.dispatchEvent(new Event('input', { bubbles: true }));
            
            // Try to submit the search form
            const form = searchInput.closest('form');
            if (form) {
                form.dispatchEvent(new Event('submit', { bubbles: true }));
            }
        } else {
            // Fallback: navigate to search page with query
            this.navigate(`/search/?q=${encodeURIComponent(query)}`);
        }
    }

    fillActiveInput(text) {
        const activeElement = document.activeElement;
        if (activeElement && (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA')) {
            activeElement.value = text;
            activeElement.dispatchEvent(new Event('input', { bubbles: true }));
            this.speak('متن وارد شد');
        } else {
            this.speak('لطفاً ابتدا روی فیلد مورد نظر کلیک کنید');
        }
    }

    showHelp() {
        const helpModal = document.createElement('div');
        helpModal.className = 'voice-help-modal';
        helpModal.innerHTML = `
            <div class="modal-backdrop" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: var(--bg-overlay); z-index: 1999;"></div>
            <div class="modal-content" style="
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                z-index: 2000;
                background: var(--bg-modal);
                border-radius: var(--border-radius-lg);
                padding: 2rem;
                max-width: 500px;
                width: 90%;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: var(--shadow-xl);
            ">
                <h3 style="margin-bottom: 1rem; color: var(--text-primary);">راهنمای دستورات صوتی</h3>
                <div style="color: var(--text-secondary); line-height: 1.6;">
                    <p><strong>ناوبری:</strong></p>
                    <ul>
                        <li>صفحه اصلی، خانه</li>
                        <li>داشبورد، پنل کاربری</li>
                        <li>خدمات</li>
                        <li>املاک</li>
                        <li>پرداخت‌ها</li>
                        <li>پیام‌ها، اعلانات</li>
                    </ul>
                    
                    <p><strong>جستجو:</strong></p>
                    <ul>
                        <li>جستجو، پیدا کن</li>
                        <li>جستجو برای [متن]</li>
                    </ul>
                    
                    <p><strong>تنظیمات:</strong></p>
                    <ul>
                        <li>تم تاریک، حالت تاریک</li>
                        <li>تم روشن، حالت روشن</li>
                    </ul>
                    
                    <p><strong>اقدامات:</strong></p>
                    <ul>
                        <li>ثبت درخواست، درخواست جدید</li>
                        <li>پیگیری درخواست</li>
                        <li>بنویس [متن] - برای پر کردن فیلد فعال</li>
                    </ul>
                </div>
                <button onclick="this.closest('.voice-help-modal').remove()" style="
                    margin-top: 1rem;
                    padding: 0.5rem 1rem;
                    background: var(--primary-color);
                    color: white;
                    border: none;
                    border-radius: var(--border-radius-sm);
                    cursor: pointer;
                ">بستن</button>
            </div>
        `;

        document.body.appendChild(helpModal);
        
        // Close on backdrop click
        helpModal.querySelector('.modal-backdrop').addEventListener('click', () => {
            helpModal.remove();
        });
    }

    showVoiceCommands() {
        this.showHelp();
    }

    logout() {
        if (confirm('آیا می‌خواهید از سیستم خارج شوید؟')) {
            window.location.href = '/logout/';
        }
    }

    speak(text) {
        if (this.synthesis) {
            // Cancel any ongoing speech
            this.synthesis.cancel();
            
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'fa-IR';
            utterance.rate = 0.9;
            utterance.pitch = 1;
            utterance.volume = 0.8;
            
            // Try to find a Persian voice
            const voices = this.synthesis.getVoices();
            const persianVoice = voices.find(voice => 
                voice.lang.startsWith('fa') || 
                voice.name.includes('Persian') ||
                voice.name.includes('Farsi')
            );
            
            if (persianVoice) {
                utterance.voice = persianVoice;
            }
            
            this.synthesis.speak(utterance);
        }
    }

    // Public methods for external use
    enableVoice() {
        if (this.voiceButton) {
            this.voiceButton.style.display = 'flex';
        }
    }

    disableVoice() {
        if (this.voiceButton) {
            this.voiceButton.style.display = 'none';
        }
        this.stopListening();
    }

    addCustomCommand(command, action) {
        this.commands[command] = action;
    }

    removeCustomCommand(command) {
        delete this.commands[command];
    }
}

// Initialize Voice UI when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.voiceUI = new VoiceUI();
    
    // Add voice UI info to console
    console.log('🎤 Voice UI loaded. Use Ctrl+Space to activate or click the microphone button.');
    console.log('🗣️ Supported commands: navigation, search, theme switching, and more.');
});