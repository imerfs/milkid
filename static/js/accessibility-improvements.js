/**
 * Accessibility and Contrast Improvements for MelkID
 */

// Theme Management
class ThemeManager {
    constructor() {
        this.themes = ['light', 'dark', 'blue', 'green', 'purple', 'orange', 'red', 'teal'];
        this.currentTheme = this.getStoredTheme() || this.getSystemTheme();
        this.init();
    }

    init() {
        this.applyTheme(this.currentTheme);
        this.setupEventListeners();
        this.setupSystemThemeListener();
    }

    getStoredTheme() {
        return localStorage.getItem('melkid-theme');
    }

    getSystemTheme() {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        this.currentTheme = theme;
        localStorage.setItem('melkid-theme', theme);
        this.updateThemeIcon(theme);
        this.announceThemeChange(theme);
    }

    updateThemeIcon(theme) {
        const themeIcon = document.getElementById('themeIcon');
        const themeToggle = document.getElementById('themeToggle');
        
        if (themeIcon && themeToggle) {
            const icons = {
                light: 'fas fa-moon',
                dark: 'fas fa-sun',
                blue: 'fas fa-palette',
                green: 'fas fa-leaf',
                purple: 'fas fa-gem',
                orange: 'fas fa-fire',
                red: 'fas fa-heart',
                teal: 'fas fa-water'
            };

            const titles = {
                light: 'تغییر به تم تاریک',
                dark: 'تغییر به تم روشن',
                blue: 'تم آبی فعال',
                green: 'تم سبز فعال',
                purple: 'تم بنفش فعال',
                orange: 'تم نارنجی فعال',
                red: 'تم قرمز فعال',
                teal: 'تم فیروزه‌ای فعال'
            };

            themeIcon.className = icons[theme] || icons.light;
            themeToggle.title = titles[theme] || titles.light;
        }
    }

    toggleTheme() {
        const nextTheme = this.currentTheme === 'dark' ? 'light' : 'dark';
        this.applyTheme(nextTheme);
    }

    setTheme(theme) {
        if (this.themes.includes(theme)) {
            this.applyTheme(theme);
        }
    }

    announceThemeChange(theme) {
        // Announce theme change to screen readers
        const announcement = document.createElement('div');
        announcement.setAttribute('aria-live', 'polite');
        announcement.setAttribute('aria-atomic', 'true');
        announcement.className = 'sr-only';
        announcement.textContent = `تم ${theme === 'dark' ? 'تاریک' : 'روشن'} فعال شد`;
        
        document.body.appendChild(announcement);
        
        setTimeout(() => {
            document.body.removeChild(announcement);
        }, 1000);
    }

    setupEventListeners() {
        // Theme toggle button
        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', () => this.toggleTheme());
        }

        // Keyboard shortcut (Ctrl/Cmd + Shift + T)
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'T') {
                e.preventDefault();
                this.toggleTheme();
            }
        });
    }

    setupSystemThemeListener() {
        // Listen for system theme changes
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        mediaQuery.addEventListener('change', (e) => {
            if (!this.getStoredTheme()) {
                this.applyTheme(e.matches ? 'dark' : 'light');
            }
        });
    }
}

// Contrast Enhancement
class ContrastEnhancer {
    constructor() {
        this.highContrastMode = this.getHighContrastPreference();
        this.init();
    }

    init() {
        this.applyHighContrast(this.highContrastMode);
        this.setupEventListeners();
    }

    getHighContrastPreference() {
        const stored = localStorage.getItem('melkid-high-contrast');
        if (stored !== null) {
            return stored === 'true';
        }
        return window.matchMedia('(prefers-contrast: high)').matches;
    }

    applyHighContrast(enabled) {
        if (enabled) {
            document.documentElement.classList.add('high-contrast');
        } else {
            document.documentElement.classList.remove('high-contrast');
        }
        
        this.highContrastMode = enabled;
        localStorage.setItem('melkid-high-contrast', enabled.toString());
    }

    toggleHighContrast() {
        this.applyHighContrast(!this.highContrastMode);
        this.announceContrastChange();
    }

    announceContrastChange() {
        const announcement = document.createElement('div');
        announcement.setAttribute('aria-live', 'polite');
        announcement.className = 'sr-only';
        announcement.textContent = `حالت کنتراست بالا ${this.highContrastMode ? 'فعال' : 'غیرفعال'} شد`;
        
        document.body.appendChild(announcement);
        
        setTimeout(() => {
            document.body.removeChild(announcement);
        }, 1000);
    }

    setupEventListeners() {
        // Keyboard shortcut (Ctrl/Cmd + Shift + C)
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'C') {
                e.preventDefault();
                this.toggleHighContrast();
            }
        });

        // Listen for system contrast changes
        const mediaQuery = window.matchMedia('(prefers-contrast: high)');
        mediaQuery.addEventListener('change', (e) => {
            if (localStorage.getItem('melkid-high-contrast') === null) {
                this.applyHighContrast(e.matches);
            }
        });
    }
}

// Font Size Controller
class FontSizeController {
    constructor() {
        this.sizes = ['small', 'normal', 'large', 'extra-large'];
        this.currentSize = this.getStoredFontSize() || 'normal';
        this.init();
    }

    init() {
        this.applyFontSize(this.currentSize);
        this.setupEventListeners();
    }

    getStoredFontSize() {
        return localStorage.getItem('melkid-font-size');
    }

    applyFontSize(size) {
        // Remove all font size classes
        this.sizes.forEach(s => {
            document.documentElement.classList.remove(`font-size-${s}`);
        });
        
        // Add current font size class
        if (size !== 'normal') {
            document.documentElement.classList.add(`font-size-${size}`);
        }
        
        this.currentSize = size;
        localStorage.setItem('melkid-font-size', size);
    }

    increaseFontSize() {
        const currentIndex = this.sizes.indexOf(this.currentSize);
        if (currentIndex < this.sizes.length - 1) {
            this.applyFontSize(this.sizes[currentIndex + 1]);
            this.announceFontSizeChange();
        }
    }

    decreaseFontSize() {
        const currentIndex = this.sizes.indexOf(this.currentSize);
        if (currentIndex > 0) {
            this.applyFontSize(this.sizes[currentIndex - 1]);
            this.announceFontSizeChange();
        }
    }

    resetFontSize() {
        this.applyFontSize('normal');
        this.announceFontSizeChange();
    }

    announceFontSizeChange() {
        const sizeNames = {
            'small': 'کوچک',
            'normal': 'عادی',
            'large': 'بزرگ',
            'extra-large': 'خیلی بزرگ'
        };

        const announcement = document.createElement('div');
        announcement.setAttribute('aria-live', 'polite');
        announcement.className = 'sr-only';
        announcement.textContent = `اندازه فونت به ${sizeNames[this.currentSize]} تغییر کرد`;
        
        document.body.appendChild(announcement);
        
        setTimeout(() => {
            document.body.removeChild(announcement);
        }, 1000);
    }

    setupEventListeners() {
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === '=') {
                e.preventDefault();
                this.increaseFontSize();
            } else if ((e.ctrlKey || e.metaKey) && e.key === '-') {
                e.preventDefault();
                this.decreaseFontSize();
            } else if ((e.ctrlKey || e.metaKey) && e.key === '0') {
                e.preventDefault();
                this.resetFontSize();
            }
        });
    }
}

// Focus Management
class FocusManager {
    constructor() {
        this.init();
    }

    init() {
        this.setupSkipLinks();
        this.setupFocusTrapping();
        this.setupKeyboardNavigation();
    }

    setupSkipLinks() {
        // Add skip to main content link
        const skipLink = document.createElement('a');
        skipLink.href = '#main-content';
        skipLink.className = 'skip-link sr-only sr-only-focusable';
        skipLink.textContent = 'پرش به محتوای اصلی';
        skipLink.style.cssText = `
            position: absolute;
            top: -40px;
            left: 6px;
            background: var(--primary-color);
            color: white;
            padding: 8px;
            text-decoration: none;
            border-radius: 4px;
            z-index: 9999;
            transition: top 0.3s;
        `;
        
        skipLink.addEventListener('focus', () => {
            skipLink.style.top = '6px';
        });
        
        skipLink.addEventListener('blur', () => {
            skipLink.style.top = '-40px';
        });
        
        document.body.insertBefore(skipLink, document.body.firstChild);

        // Ensure main content has ID
        const mainContent = document.querySelector('main') || document.querySelector('.container').parentElement;
        if (mainContent && !mainContent.id) {
            mainContent.id = 'main-content';
        }
    }

    setupFocusTrapping() {
        // Trap focus in modals
        document.addEventListener('shown.bs.modal', (e) => {
            const modal = e.target;
            const focusableElements = modal.querySelectorAll(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
            );
            
            if (focusableElements.length > 0) {
                focusableElements[0].focus();
            }
        });
    }

    setupKeyboardNavigation() {
        // Escape key to close modals and dropdowns
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                // Close open dropdowns
                const openDropdowns = document.querySelectorAll('.dropdown-menu.show');
                openDropdowns.forEach(dropdown => {
                    const toggle = document.querySelector(`[data-bs-toggle="dropdown"][aria-expanded="true"]`);
                    if (toggle) {
                        toggle.click();
                    }
                });
            }
        });
    }
}

// Initialize all accessibility features
document.addEventListener('DOMContentLoaded', () => {
    window.themeManager = new ThemeManager();
    window.contrastEnhancer = new ContrastEnhancer();
    window.fontSizeController = new FontSizeController();
    window.focusManager = new FocusManager();
});

// Global functions for backward compatibility
function toggleTheme() {
    if (window.themeManager) {
        window.themeManager.toggleTheme();
    }
}

function setTheme(theme) {
    if (window.themeManager) {
        window.themeManager.setTheme(theme);
    }
}

function toggleHighContrast() {
    if (window.contrastEnhancer) {
        window.contrastEnhancer.toggleHighContrast();
    }
}

function increaseFontSize() {
    if (window.fontSizeController) {
        window.fontSizeController.increaseFontSize();
    }
}

function decreaseFontSize() {
    if (window.fontSizeController) {
        window.fontSizeController.decreaseFontSize();
    }
}