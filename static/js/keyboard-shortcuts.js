// Keyboard Shortcuts System for MelkID
class KeyboardShortcuts {
    constructor() {
        this.shortcuts = new Map();
        this.isEnabled = true;
        this.helpVisible = false;
        this.init();
    }

    init() {
        this.setupDefaultShortcuts();
        this.bindEvents();
        this.createHelpOverlay();
        this.showInitialHint();
    }

    setupDefaultShortcuts() {
        // Navigation shortcuts
        this.addShortcut('ctrl+h', () => this.navigate('/'), 'رفتن به صفحه اصلی');
        this.addShortcut('ctrl+d', () => this.navigate('/dashboard/'), 'رفتن به داشبورد');
        this.addShortcut('ctrl+s', () => this.navigate('/services/'), 'رفتن به خدمات');
        this.addShortcut('ctrl+p', () => this.navigate('/properties/'), 'رفتن به املاک');
        this.addShortcut('ctrl+m', () => this.navigate('/dashboard/messages/'), 'رفتن به پیام‌ها');

        // Search shortcuts
        this.addShortcut('ctrl+k', () => this.focusSearch(), 'فعال کردن جستجو');
        this.addShortcut('/', () => this.focusSearch(), 'فعال کردن جستجو');
        this.addShortcut('escape', () => this.clearSearch(), 'پاک کردن جستجو');

        // Form shortcuts
        this.addShortcut('ctrl+enter', () => this.submitActiveForm(), 'ارسال فرم فعال');
        this.addShortcut('ctrl+r', () => this.resetActiveForm(), 'ریست کردن فرم');

        // UI shortcuts
        this.addShortcut('ctrl+shift+d', () => this.toggleTheme(), 'تغییر تم');
        this.addShortcut('ctrl+shift+h', () => this.toggleHelp(), 'نمایش/مخفی کردن راهنما');
        this.addShortcut('ctrl+shift+k', () => this.showShortcutsHelp(), 'نمایش میانبرها');

        // Quick actions
        this.addShortcut('ctrl+n', () => this.newRequest(), 'درخواست جدید');
        this.addShortcut('ctrl+t', () => this.trackRequests(), 'پیگیری درخواست‌ها');
        this.addShortcut('ctrl+shift+p', () => this.viewPayments(), 'مشاهده پرداخت‌ها');

        // Accessibility shortcuts
        this.addShortcut('alt+1', () => this.focusMainContent(), 'رفتن به محتوای اصلی');
        this.addShortcut('alt+2', () => this.focusNavigation(), 'رفتن به منوی ناوبری');
        this.addShortcut('alt+3', () => this.focusSidebar(), 'رفتن به نوار کناری');

        // Developer shortcuts (only in debug mode)
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            this.addShortcut('ctrl+shift+i', () => this.toggleDevInfo(), 'اطلاعات توسعه‌دهنده');
            this.addShortcut('ctrl+shift+r', () => window.location.reload(), 'رفرش سخت');
        }
    }

    addShortcut(keys, callback, description = '') {
        const normalizedKeys = this.normalizeKeys(keys);
        this.shortcuts.set(normalizedKeys, {
            callback,
            description,
            keys: keys
        });
    }

    removeShortcut(keys) {
        const normalizedKeys = this.normalizeKeys(keys);
        this.shortcuts.delete(normalizedKeys);
    }

    normalizeKeys(keys) {
        return keys.toLowerCase()
            .replace(/\s+/g, '')
            .split('+')
            .sort()
            .join('+');
    }

    bindEvents() {
        document.addEventListener('keydown', (e) => {
            if (!this.isEnabled) return;

            // Don't trigger shortcuts when typing in inputs
            if (this.isTypingInInput(e.target)) {
                // Allow some shortcuts even in inputs
                if (!this.isAllowedInInput(e)) {
                    return;
                }
            }

            const pressedKeys = this.getPressedKeys(e);
            const normalizedKeys = this.normalizeKeys(pressedKeys);
            
            const shortcut = this.shortcuts.get(normalizedKeys);
            if (shortcut) {
                e.preventDefault();
                e.stopPropagation();
                
                try {
                    shortcut.callback(e);
                    this.showShortcutFeedback(shortcut.keys, shortcut.description);
                } catch (error) {
                    console.error('Error executing shortcut:', error);
                }
            }
        });

        // Show available shortcuts on long Ctrl press
        let ctrlPressTime = 0;
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Control') {
                ctrlPressTime = Date.now();
            }
        });

        document.addEventListener('keyup', (e) => {
            if (e.key === 'Control') {
                const pressDuration = Date.now() - ctrlPressTime;
                if (pressDuration > 1000) { // 1 second
                    this.showQuickShortcuts();
                }
            }
        });
    }

    isTypingInInput(element) {
        const inputTypes = ['INPUT', 'TEXTAREA', 'SELECT'];
        return inputTypes.includes(element.tagName) || 
               element.contentEditable === 'true' ||
               element.isContentEditable;
    }

    isAllowedInInput(e) {
        const allowedShortcuts = ['escape', 'ctrl+enter', 'ctrl+k'];
        const pressedKeys = this.getPressedKeys(e);
        const normalizedKeys = this.normalizeKeys(pressedKeys);
        
        return allowedShortcuts.some(shortcut => 
            this.normalizeKeys(shortcut) === normalizedKeys
        );
    }

    getPressedKeys(e) {
        const keys = [];
        
        if (e.ctrlKey) keys.push('ctrl');
        if (e.altKey) keys.push('alt');
        if (e.shiftKey) keys.push('shift');
        if (e.metaKey) keys.push('meta');
        
        // Handle special keys
        const specialKeys = {
            ' ': 'space',
            'Enter': 'enter',
            'Escape': 'escape',
            'Tab': 'tab',
            'Backspace': 'backspace',
            'Delete': 'delete',
            'ArrowUp': 'up',
            'ArrowDown': 'down',
            'ArrowLeft': 'left',
            'ArrowRight': 'right'
        };

        const key = specialKeys[e.key] || e.key.toLowerCase();
        if (key !== 'control' && key !== 'alt' && key !== 'shift' && key !== 'meta') {
            keys.push(key);
        }

        return keys.join('+');
    }

    createHelpOverlay() {
        this.helpOverlay = document.createElement('div');
        this.helpOverlay.className = 'shortcuts-help-overlay';
        this.helpOverlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            z-index: 10000;
            display: none;
            align-items: center;
            justify-content: center;
            backdrop-filter: blur(5px);
        `;

        const helpContent = document.createElement('div');
        helpContent.className = 'shortcuts-help-content';
        helpContent.style.cssText = `
            background: var(--bg-modal);
            border-radius: var(--border-radius-lg);
            padding: 2rem;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
            box-shadow: var(--shadow-xl);
            animation: zoomIn 0.3s ease-out;
        `;

        helpContent.innerHTML = `
            <div class="help-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
                <h3 style="margin: 0; color: var(--text-primary);">میانبرهای صفحه‌کلید</h3>
                <button class="close-help" style="
                    background: none;
                    border: none;
                    font-size: 1.5rem;
                    cursor: pointer;
                    color: var(--text-muted);
                ">✕</button>
            </div>
            <div class="shortcuts-grid" style="
                display: grid;
                grid-template-columns: 1fr 2fr;
                gap: 1rem;
                color: var(--text-secondary);
            "></div>
            <div class="help-footer" style="
                margin-top: 2rem;
                padding-top: 1rem;
                border-top: 1px solid var(--border-color);
                text-align: center;
                color: var(--text-muted);
                font-size: 0.9rem;
            ">
                برای بستن این راهنما، کلید Escape را فشار دهید
            </div>
        `;

        this.helpOverlay.appendChild(helpContent);
        document.body.appendChild(this.helpOverlay);

        // Bind close events
        helpContent.querySelector('.close-help').addEventListener('click', () => {
            this.hideShortcutsHelp();
        });

        this.helpOverlay.addEventListener('click', (e) => {
            if (e.target === this.helpOverlay) {
                this.hideShortcutsHelp();
            }
        });

        this.populateShortcutsHelp();
    }

    populateShortcutsHelp() {
        const grid = this.helpOverlay.querySelector('.shortcuts-grid');
        
        // Group shortcuts by category
        const categories = {
            'ناوبری': ['ctrl+h', 'ctrl+d', 'ctrl+s', 'ctrl+p', 'ctrl+m'],
            'جستجو': ['ctrl+k', '/', 'escape'],
            'فرم‌ها': ['ctrl+enter', 'ctrl+r'],
            'رابط کاربری': ['ctrl+shift+d', 'ctrl+shift+h', 'ctrl+shift+k'],
            'اقدامات سریع': ['ctrl+n', 'ctrl+t', 'ctrl+shift+p'],
            'دسترسی‌پذیری': ['alt+1', 'alt+2', 'alt+3']
        };

        Object.entries(categories).forEach(([category, shortcuts]) => {
            const categoryHeader = document.createElement('div');
            categoryHeader.style.cssText = `
                grid-column: 1 / -1;
                font-weight: 600;
                color: var(--primary-color);
                margin-top: 1rem;
                margin-bottom: 0.5rem;
                border-bottom: 1px solid var(--border-light);
                padding-bottom: 0.25rem;
            `;
            categoryHeader.textContent = category;
            grid.appendChild(categoryHeader);

            shortcuts.forEach(shortcutKey => {
                const normalizedKey = this.normalizeKeys(shortcutKey);
                const shortcut = this.shortcuts.get(normalizedKey);
                
                if (shortcut) {
                    const keyElement = document.createElement('div');
                    keyElement.style.cssText = `
                        font-family: monospace;
                        background: var(--bg-tertiary);
                        padding: 0.25rem 0.5rem;
                        border-radius: var(--border-radius-sm);
                        font-size: 0.9rem;
                        text-align: center;
                    `;
                    keyElement.textContent = this.formatKeys(shortcut.keys);

                    const descElement = document.createElement('div');
                    descElement.textContent = shortcut.description;

                    grid.appendChild(keyElement);
                    grid.appendChild(descElement);
                }
            });
        });
    }

    formatKeys(keys) {
        return keys.replace(/ctrl/g, 'Ctrl')
                  .replace(/alt/g, 'Alt')
                  .replace(/shift/g, 'Shift')
                  .replace(/enter/g, 'Enter')
                  .replace(/escape/g, 'Esc')
                  .replace(/\+/g, ' + ');
    }

    showInitialHint() {
        // Show a subtle hint about keyboard shortcuts
        setTimeout(() => {
            const hint = document.createElement('div');
            hint.className = 'shortcuts-hint';
            hint.style.cssText = `
                position: fixed;
                bottom: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: var(--glass-bg);
                backdrop-filter: blur(10px);
                border: 1px solid var(--glass-border);
                border-radius: var(--border-radius-lg);
                padding: 1rem 1.5rem;
                color: var(--text-primary);
                font-size: 0.9rem;
                z-index: 1000;
                animation: slideInUp 0.5s ease-out;
                cursor: pointer;
            `;
            
            hint.innerHTML = `
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <span>⌨️</span>
                    <span>برای مشاهده میانبرهای صفحه‌کلید، <kbd style="background: var(--bg-tertiary); padding: 0.2rem 0.4rem; border-radius: 4px;">Ctrl + Shift + K</kbd> را فشار دهید</span>
                    <button style="background: none; border: none; color: var(--text-muted); cursor: pointer; margin-right: 0.5rem;">✕</button>
                </div>
            `;

            document.body.appendChild(hint);

            // Auto-hide after 5 seconds
            setTimeout(() => {
                if (hint.parentNode) {
                    hint.style.animation = 'slideOutDown 0.5s ease-out';
                    setTimeout(() => hint.remove(), 500);
                }
            }, 5000);

            // Manual close
            hint.querySelector('button').addEventListener('click', () => {
                hint.remove();
            });

            // Click to show shortcuts
            hint.addEventListener('click', (e) => {
                if (e.target.tagName !== 'BUTTON') {
                    this.showShortcutsHelp();
                    hint.remove();
                }
            });
        }, 3000);
    }

    showShortcutFeedback(keys, description) {
        const feedback = document.createElement('div');
        feedback.className = 'shortcut-feedback';
        feedback.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: var(--success-color);
            color: white;
            padding: 0.75rem 1rem;
            border-radius: var(--border-radius);
            font-size: 0.9rem;
            z-index: 9999;
            animation: slideInRight 0.3s ease-out;
            box-shadow: var(--shadow-md);
        `;

        feedback.innerHTML = `
            <div style="font-weight: 600; margin-bottom: 0.25rem;">${this.formatKeys(keys)}</div>
            <div style="opacity: 0.9; font-size: 0.8rem;">${description}</div>
        `;

        document.body.appendChild(feedback);

        setTimeout(() => {
            feedback.style.animation = 'slideOutRight 0.3s ease-out';
            setTimeout(() => feedback.remove(), 300);
        }, 2000);
    }

    showQuickShortcuts() {
        const quickShortcuts = document.createElement('div');
        quickShortcuts.className = 'quick-shortcuts';
        quickShortcuts.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: var(--glass-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--glass-border);
            border-radius: var(--border-radius-lg);
            padding: 1.5rem;
            z-index: 9999;
            animation: zoomIn 0.3s ease-out;
            box-shadow: var(--glass-shadow);
        `;

        const commonShortcuts = [
            'ctrl+k', 'ctrl+h', 'ctrl+d', 'ctrl+n', 'ctrl+shift+k'
        ];

        let content = '<h4 style="margin: 0 0 1rem 0; color: var(--text-primary);">میانبرهای پرکاربرد</h4>';
        
        commonShortcuts.forEach(shortcutKey => {
            const normalizedKey = this.normalizeKeys(shortcutKey);
            const shortcut = this.shortcuts.get(normalizedKey);
            
            if (shortcut) {
                content += `
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <span style="color: var(--text-secondary);">${shortcut.description}</span>
                        <kbd style="background: var(--bg-tertiary); padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.8rem;">${this.formatKeys(shortcut.keys)}</kbd>
                    </div>
                `;
            }
        });

        quickShortcuts.innerHTML = content;
        document.body.appendChild(quickShortcuts);

        setTimeout(() => {
            quickShortcuts.remove();
        }, 3000);
    }

    // Shortcut action methods
    navigate(url) {
        window.location.href = url;
    }

    focusSearch() {
        const searchInput = document.querySelector('input[type="search"], input[name*="search"], .search-input, #search');
        if (searchInput) {
            searchInput.focus();
            searchInput.select();
        } else {
            // Create a temporary search overlay
            this.createSearchOverlay();
        }
    }

    createSearchOverlay() {
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 10000;
            display: flex;
            align-items: flex-start;
            justify-content: center;
            padding-top: 10vh;
        `;

        const searchBox = document.createElement('div');
        searchBox.style.cssText = `
            background: var(--bg-modal);
            border-radius: var(--border-radius-lg);
            padding: 1.5rem;
            width: 90%;
            max-width: 500px;
            box-shadow: var(--shadow-xl);
        `;

        searchBox.innerHTML = `
            <input type="text" placeholder="جستجو در سایت..." style="
                width: 100%;
                padding: 1rem;
                border: 1px solid var(--border-color);
                border-radius: var(--border-radius);
                font-size: 1.1rem;
                background: var(--bg-primary);
                color: var(--text-primary);
            ">
            <div style="margin-top: 1rem; color: var(--text-muted); font-size: 0.9rem;">
                Enter برای جستجو، Escape برای بستن
            </div>
        `;

        overlay.appendChild(searchBox);
        document.body.appendChild(overlay);

        const input = searchBox.querySelector('input');
        input.focus();

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const query = input.value.trim();
                if (query) {
                    window.location.href = `/search/?q=${encodeURIComponent(query)}`;
                }
            } else if (e.key === 'Escape') {
                overlay.remove();
            }
        });

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.remove();
            }
        });
    }

    clearSearch() {
        const searchInputs = document.querySelectorAll('input[type="search"], input[name*="search"], .search-input');
        searchInputs.forEach(input => {
            input.value = '';
            input.dispatchEvent(new Event('input', { bubbles: true }));
        });
    }

    submitActiveForm() {
        const activeElement = document.activeElement;
        const form = activeElement.closest('form');
        if (form) {
            form.dispatchEvent(new Event('submit', { bubbles: true }));
        }
    }

    resetActiveForm() {
        const activeElement = document.activeElement;
        const form = activeElement.closest('form');
        if (form) {
            form.reset();
        }
    }

    toggleTheme() {
        if (window.themeManager) {
            window.themeManager.toggleTheme();
        }
    }

    toggleHelp() {
        if (window.onboardingTutorial) {
            window.onboardingTutorial.start();
        }
    }

    showShortcutsHelp() {
        this.helpOverlay.style.display = 'flex';
        this.helpVisible = true;
    }

    hideShortcutsHelp() {
        this.helpOverlay.style.display = 'none';
        this.helpVisible = false;
    }

    newRequest() {
        this.navigate('/services/request/');
    }

    trackRequests() {
        this.navigate('/dashboard/track-requests/');
    }

    viewPayments() {
        this.navigate('/dashboard/payments/');
    }

    focusMainContent() {
        const main = document.querySelector('main, .main-content, #main');
        if (main) {
            main.focus();
            main.scrollIntoView({ behavior: 'smooth' });
        }
    }

    focusNavigation() {
        const nav = document.querySelector('nav, .navbar, .navigation');
        if (nav) {
            const firstLink = nav.querySelector('a, button');
            if (firstLink) {
                firstLink.focus();
            }
        }
    }

    focusSidebar() {
        const sidebar = document.querySelector('.sidebar, .side-nav, aside');
        if (sidebar) {
            const firstLink = sidebar.querySelector('a, button');
            if (firstLink) {
                firstLink.focus();
            }
        }
    }

    toggleDevInfo() {
        console.log('🔧 Development Info:');
        console.log('Current shortcuts:', Array.from(this.shortcuts.keys()));
        console.log('Theme:', document.documentElement.getAttribute('data-theme'));
        console.log('User agent:', navigator.userAgent);
        console.log('Viewport:', `${window.innerWidth}x${window.innerHeight}`);
    }

    // Public methods
    enable() {
        this.isEnabled = true;
    }

    disable() {
        this.isEnabled = false;
    }

    addCustomShortcut(keys, callback, description) {
        this.addShortcut(keys, callback, description);
        this.populateShortcutsHelp(); // Refresh help
    }

    removeCustomShortcut(keys) {
        this.removeShortcut(keys);
        this.populateShortcutsHelp(); // Refresh help
    }
}

// Initialize Keyboard Shortcuts
document.addEventListener('DOMContentLoaded', () => {
    window.keyboardShortcuts = new KeyboardShortcuts();
    console.log('⌨️ Keyboard Shortcuts system loaded');
    console.log('💡 Press Ctrl+Shift+K to see all available shortcuts');
});