// Modern Interactions for MelkID

// HTML-escape text before it goes into innerHTML.
function escapeHtml(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
        return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
}

/* ========== THEME SYSTEM ========== */
class ThemeManager {
    constructor() {
        this.currentTheme = localStorage.getItem('theme') || 'light';
        this.currentColor = localStorage.getItem('color-theme') || 'default';
        this.init();
    }

    init() {
        this.applyTheme();
        this.createThemeToggle();
        this.createThemeSelector();
        this.bindEvents();
    }

    applyTheme() {
        document.documentElement.setAttribute('data-theme', this.currentTheme);
        if (this.currentColor !== 'default') {
            document.documentElement.setAttribute('data-color', this.currentColor);
        }
    }

    createThemeToggle() {
        const toggle = document.createElement('div');
        toggle.className = 'theme-toggle';
        toggle.innerHTML = this.currentTheme === 'dark' ? '🌙' : '☀️';
        toggle.title = 'تغییر تم';
        document.body.appendChild(toggle);

        toggle.addEventListener('click', () => {
            this.toggleTheme();
        });
    }

    createThemeSelector() {
        const selector = document.createElement('div');
        selector.className = 'theme-selector';
        selector.innerHTML = `
            <div class="theme-section">
                <h6 style="margin-bottom: 0.5rem; color: var(--text-primary);">حالت نمایش</h6>
                <div class="theme-option" data-theme="light">
                    <span>☀️</span>
                    <span>روشن</span>
                </div>
                <div class="theme-option" data-theme="dark">
                    <span>🌙</span>
                    <span>تاریک</span>
                </div>
            </div>
            <div class="theme-section">
                <h6 style="margin-bottom: 0.5rem; color: var(--text-primary);">رنگ‌بندی</h6>
                <div class="theme-option" data-color="default">
                    <div class="theme-color" style="background: #2563eb;"></div>
                    <span>پیش‌فرض</span>
                </div>
                <div class="theme-option" data-color="blue">
                    <div class="theme-color" style="background: #2196F3;"></div>
                    <span>آبی</span>
                </div>
                <div class="theme-option" data-color="green">
                    <div class="theme-color" style="background: #4CAF50;"></div>
                    <span>سبز</span>
                </div>
                <div class="theme-option" data-color="purple">
                    <div class="theme-color" style="background: #9C27B0;"></div>
                    <span>بنفش</span>
                </div>
                <div class="theme-option" data-color="orange">
                    <div class="theme-color" style="background: #FF9800;"></div>
                    <span>نارنجی</span>
                </div>
                <div class="theme-option" data-color="red">
                    <div class="theme-color" style="background: #F44336;"></div>
                    <span>قرمز</span>
                </div>
                <div class="theme-option" data-color="teal">
                    <div class="theme-color" style="background: #009688;"></div>
                    <span>سبز دریایی</span>
                </div>
            </div>
        `;
        document.body.appendChild(selector);

        // Mark active options
        this.updateActiveOptions();
    }

    bindEvents() {
        // Theme toggle on long press
        const toggle = document.querySelector('.theme-toggle');
        let pressTimer;

        toggle.addEventListener('mousedown', () => {
            pressTimer = setTimeout(() => {
                this.showThemeSelector();
            }, 500);
        });

        toggle.addEventListener('mouseup', () => {
            clearTimeout(pressTimer);
        });

        toggle.addEventListener('mouseleave', () => {
            clearTimeout(pressTimer);
        });

        // Theme selector options
        document.addEventListener('click', (e) => {
            if (e.target.closest('.theme-option')) {
                const option = e.target.closest('.theme-option');
                
                if (option.dataset.theme) {
                    this.setTheme(option.dataset.theme);
                }
                
                if (option.dataset.color) {
                    this.setColorTheme(option.dataset.color);
                }
                
                this.hideThemeSelector();
            } else if (!e.target.closest('.theme-selector') && !e.target.closest('.theme-toggle')) {
                this.hideThemeSelector();
            }
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'd') {
                e.preventDefault();
                this.toggleTheme();
            }
        });
    }

    toggleTheme() {
        this.currentTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        this.setTheme(this.currentTheme);
    }

    setTheme(theme) {
        this.currentTheme = theme;
        localStorage.setItem('theme', theme);
        this.applyTheme();
        
        // Update toggle icon
        const toggle = document.querySelector('.theme-toggle');
        toggle.innerHTML = theme === 'dark' ? '🌙' : '☀️';
        
        this.updateActiveOptions();
        this.animateThemeChange();
    }

    setColorTheme(color) {
        this.currentColor = color;
        localStorage.setItem('color-theme', color);
        
        if (color === 'default') {
            document.documentElement.removeAttribute('data-color');
        } else {
            document.documentElement.setAttribute('data-color', color);
        }
        
        this.updateActiveOptions();
    }

    showThemeSelector() {
        const selector = document.querySelector('.theme-selector');
        selector.classList.add('show');
    }

    hideThemeSelector() {
        const selector = document.querySelector('.theme-selector');
        selector.classList.remove('show');
    }

    updateActiveOptions() {
        // Update theme options
        document.querySelectorAll('[data-theme]').forEach(option => {
            option.classList.toggle('active', option.dataset.theme === this.currentTheme);
        });

        // Update color options
        document.querySelectorAll('[data-color]').forEach(option => {
            option.classList.toggle('active', option.dataset.color === this.currentColor);
        });
    }

    animateThemeChange() {
        document.body.style.transition = 'all 0.3s ease';
        setTimeout(() => {
            document.body.style.transition = '';
        }, 300);
    }
}

/* ========== MICRO-ANIMATIONS MANAGER ========== */
class AnimationManager {
    constructor() {
        this.init();
    }

    init() {
        this.observeElements();
        this.addHoverEffects();
        this.addClickEffects();
        this.addScrollAnimations();
    }

    observeElements() {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    this.animateElement(entry.target);
                }
            });
        }, {
            threshold: 0.1,
            rootMargin: '0px 0px -50px 0px'
        });

        // Observe cards and important elements
        document.querySelectorAll('.card, .stat-card, .modern-card, .glass-card').forEach(el => {
            observer.observe(el);
        });
    }

    animateElement(element) {
        // Add staggered animation based on position
        const elements = Array.from(element.parentNode.children);
        const index = elements.indexOf(element);
        
        element.style.animationDelay = `${index * 0.1}s`;
        element.classList.add('animate-slide-up');
    }

    addHoverEffects() {
        // Add hover effects to buttons
        document.querySelectorAll('.btn, .modern-card, .stat-card').forEach(el => {
            el.addEventListener('mouseenter', () => {
                el.classList.add('hover-lift');
            });
        });

        // Add pulse effect to important buttons
        document.querySelectorAll('.btn-primary, .btn-success').forEach(el => {
            el.classList.add('hover-pulse');
        });
    }

    addClickEffects() {
        // Add click ripple effect
        document.addEventListener('click', (e) => {
            if (e.target.matches('.btn, .card, .theme-option')) {
                this.createRipple(e);
            }
        });
    }

    createRipple(event) {
        const button = event.currentTarget;
        const ripple = document.createElement('span');
        const rect = button.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        const x = event.clientX - rect.left - size / 2;
        const y = event.clientY - rect.top - size / 2;

        ripple.style.cssText = `
            position: absolute;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.6);
            transform: scale(0);
            animation: ripple 0.6s linear;
            width: ${size}px;
            height: ${size}px;
            left: ${x}px;
            top: ${y}px;
            pointer-events: none;
        `;

        // Add ripple keyframes if not exists
        if (!document.querySelector('#ripple-styles')) {
            const style = document.createElement('style');
            style.id = 'ripple-styles';
            style.textContent = `
                @keyframes ripple {
                    to {
                        transform: scale(2);
                        opacity: 0;
                    }
                }
            `;
            document.head.appendChild(style);
        }

        button.style.position = 'relative';
        button.style.overflow = 'hidden';
        button.appendChild(ripple);

        setTimeout(() => {
            ripple.remove();
        }, 600);
    }

    addScrollAnimations() {
        let ticking = false;

        window.addEventListener('scroll', () => {
            if (!ticking) {
                requestAnimationFrame(() => {
                    this.handleScroll();
                    ticking = false;
                });
                ticking = true;
            }
        });
    }

    handleScroll() {
        const scrolled = window.pageYOffset;
        const parallax = document.querySelectorAll('.parallax');
        
        parallax.forEach(el => {
            const speed = el.dataset.speed || 0.5;
            el.style.transform = `translateY(${scrolled * speed}px)`;
        });

        // Add floating animation to theme toggle based on scroll
        const themeToggle = document.querySelector('.theme-toggle');
        if (themeToggle) {
            themeToggle.style.transform = `translateY(${Math.sin(scrolled * 0.01) * 5}px)`;
        }
    }
}

/* ========== SMART FORMS ========== */
class SmartForms {
    constructor() {
        this.init();
    }

    init() {
        this.addAutoComplete();
        this.addValidationEffects();
        this.addFloatingLabels();
        this.addCharacterCounters();
    }

    addAutoComplete() {
        // Auto-complete for common Persian cities
        const cities = [
            'تهران', 'مشهد', 'اصفهان', 'شیراز', 'تبریز', 'کرج', 'قم', 'اهواز',
            'کرمانشاه', 'ارومیه', 'رشت', 'زاهدان', 'همدان', 'کرمان', 'یزد', 'اردبیل'
        ];

        document.querySelectorAll('input[name*="city"], input[name*="شهر"]').forEach(input => {
            this.createAutoComplete(input, cities);
        });
    }

    createAutoComplete(input, suggestions) {
        const wrapper = document.createElement('div');
        wrapper.className = 'autocomplete-wrapper';
        wrapper.style.position = 'relative';
        
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        const dropdown = document.createElement('div');
        dropdown.className = 'autocomplete-dropdown';
        dropdown.style.cssText = `
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--border-radius-sm);
            box-shadow: var(--shadow-lg);
            max-height: 200px;
            overflow-y: auto;
            z-index: 1000;
            display: none;
        `;
        wrapper.appendChild(dropdown);

        input.addEventListener('input', (e) => {
            const value = e.target.value.toLowerCase();
            const matches = suggestions.filter(item => 
                item.toLowerCase().includes(value)
            ).slice(0, 5);

            if (matches.length > 0 && value.length > 0) {
                dropdown.innerHTML = matches.map(match => 
                    `<div class="autocomplete-item" style="padding: 0.5rem; cursor: pointer; border-bottom: 1px solid var(--border-light);">${escapeHtml(match)}</div>`
                ).join('');
                dropdown.style.display = 'block';
            } else {
                dropdown.style.display = 'none';
            }
        });

        dropdown.addEventListener('click', (e) => {
            if (e.target.classList.contains('autocomplete-item')) {
                input.value = e.target.textContent;
                dropdown.style.display = 'none';
                input.dispatchEvent(new Event('change'));
            }
        });

        document.addEventListener('click', (e) => {
            if (!wrapper.contains(e.target)) {
                dropdown.style.display = 'none';
            }
        });
    }

    addValidationEffects() {
        document.querySelectorAll('input, textarea, select').forEach(input => {
            input.addEventListener('blur', () => {
                this.validateField(input);
            });

            input.addEventListener('input', () => {
                if (input.classList.contains('is-invalid')) {
                    this.validateField(input);
                }
            });
        });
    }

    validateField(field) {
        const isValid = field.checkValidity();
        
        field.classList.toggle('is-valid', isValid);
        field.classList.toggle('is-invalid', !isValid);

        if (!isValid) {
            field.classList.add('animate-shake');
            setTimeout(() => {
                field.classList.remove('animate-shake');
            }, 500);
        }
    }

    addFloatingLabels() {
        document.querySelectorAll('.form-floating').forEach(container => {
            const input = container.querySelector('input, textarea');
            const label = container.querySelector('label');

            if (input && label) {
                input.addEventListener('focus', () => {
                    label.classList.add('animate-slide-up');
                });

                input.addEventListener('blur', () => {
                    if (!input.value) {
                        label.classList.remove('animate-slide-up');
                    }
                });
            }
        });
    }

    addCharacterCounters() {
        document.querySelectorAll('textarea[maxlength], input[maxlength]').forEach(input => {
            const maxLength = input.getAttribute('maxlength');
            const counter = document.createElement('small');
            counter.className = 'character-counter';
            counter.style.cssText = `
                display: block;
                text-align: left;
                margin-top: 0.25rem;
                color: var(--text-muted);
            `;
            
            input.parentNode.appendChild(counter);

            const updateCounter = () => {
                const remaining = maxLength - input.value.length;
                counter.textContent = `${remaining} کاراکتر باقی‌مانده`;
                
                if (remaining < 10) {
                    counter.style.color = 'var(--danger-color)';
                } else if (remaining < 50) {
                    counter.style.color = 'var(--warning-color)';
                } else {
                    counter.style.color = 'var(--text-muted)';
                }
            };

            input.addEventListener('input', updateCounter);
            updateCounter();
        });
    }
}

/* ========== DRAG & DROP INTERFACE ========== */
class DragDropManager {
    constructor() {
        this.init();
    }

    init() {
        this.setupFileDropZones();
        this.setupSortableElements();
    }

    setupFileDropZones() {
        document.querySelectorAll('input[type="file"]').forEach(input => {
            this.createDropZone(input);
        });
    }

    createDropZone(input) {
        const dropZone = document.createElement('div');
        dropZone.className = 'drop-zone';
        dropZone.style.cssText = `
            border: 2px dashed var(--border-color);
            border-radius: var(--border-radius);
            padding: 2rem;
            text-align: center;
            cursor: pointer;
            transition: var(--transition);
            background: var(--bg-secondary);
            margin-bottom: 1rem;
        `;

        dropZone.innerHTML = `
            <div class="drop-zone-content">
                <i class="fas fa-cloud-upload-alt" style="font-size: 2rem; color: var(--text-muted); margin-bottom: 1rem;"></i>
                <p style="margin: 0; color: var(--text-secondary);">فایل را اینجا بکشید یا کلیک کنید</p>
                <small style="color: var(--text-muted);">حداکثر حجم: 10MB</small>
            </div>
        `;

        input.parentNode.insertBefore(dropZone, input);
        input.style.display = 'none';

        // Events
        dropZone.addEventListener('click', () => input.click());
        
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.style.borderColor = 'var(--primary-color)';
            dropZone.style.backgroundColor = 'var(--glass-bg)';
            dropZone.classList.add('animate-pulse');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.style.borderColor = 'var(--border-color)';
            dropZone.style.backgroundColor = 'var(--bg-secondary)';
            dropZone.classList.remove('animate-pulse');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            const files = e.dataTransfer.files;
            input.files = files;
            this.showFilePreview(dropZone, files);
            input.dispatchEvent(new Event('change'));
        });

        input.addEventListener('change', () => {
            if (input.files.length > 0) {
                this.showFilePreview(dropZone, input.files);
            }
        });
    }

    showFilePreview(dropZone, files) {
        const file = files[0];
        const preview = document.createElement('div');
        preview.className = 'file-preview animate-slide-up';
        preview.style.cssText = `
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem;
            background: var(--bg-primary);
            border-radius: var(--border-radius-sm);
            margin-top: 1rem;
        `;

        const icon = this.getFileIcon(file.type);
        preview.innerHTML = `
            <span style="font-size: 1.5rem;">${icon}</span>
            <div>
                <div style="font-weight: 600; color: var(--text-primary);">${escapeHtml(file.name)}</div>
                <small style="color: var(--text-muted);">${this.formatFileSize(file.size)}</small>
            </div>
            <button type="button" class="btn btn-sm btn-outline-danger ms-auto" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        `;

        // Remove existing preview
        const existingPreview = dropZone.querySelector('.file-preview');
        if (existingPreview) {
            existingPreview.remove();
        }

        dropZone.appendChild(preview);
    }

    getFileIcon(mimeType) {
        if (mimeType.startsWith('image/')) return '🖼️';
        if (mimeType.includes('pdf')) return '📄';
        if (mimeType.includes('word')) return '📝';
        if (mimeType.includes('excel')) return '📊';
        return '📎';
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    setupSortableElements() {
        // Add sortable functionality to lists
        document.querySelectorAll('.sortable').forEach(list => {
            this.makeSortable(list);
        });
    }

    makeSortable(container) {
        let draggedElement = null;

        container.addEventListener('dragstart', (e) => {
            draggedElement = e.target;
            e.target.style.opacity = '0.5';
        });

        container.addEventListener('dragend', (e) => {
            e.target.style.opacity = '';
            draggedElement = null;
        });

        container.addEventListener('dragover', (e) => {
            e.preventDefault();
        });

        container.addEventListener('drop', (e) => {
            e.preventDefault();
            if (draggedElement && e.target !== draggedElement) {
                const rect = e.target.getBoundingClientRect();
                const next = (e.clientY - rect.top) / (rect.bottom - rect.top) > 0.5;
                container.insertBefore(draggedElement, next ? e.target.nextSibling : e.target);
            }
        });
    }
}

/* ========== INITIALIZATION ========== */
document.addEventListener('DOMContentLoaded', () => {
    // Initialize all managers
    new ThemeManager();
    new AnimationManager();
    new SmartForms();
    new DragDropManager();

    // Add loading states to forms
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', (e) => {
            const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> در حال ارسال...';
            }
        });
    });

    // Add smooth scrolling
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // Add keyboard shortcuts info
    console.log('🎨 Theme Shortcuts: Ctrl+D (Toggle Dark Mode)');
});
// Enhanced user experience with smooth animations and interactions

class ModernUI {
    constructor() {
        this.init();
    }

    init() {
        this.setupLoadingStates();
        this.setupFormEnhancements();
        this.setupTableEnhancements();
        this.setupNotifications();
        this.setupSearchEnhancements();
        this.setupModalEnhancements();
        this.setupProgressBars();
        this.setupTooltips();
        this.setupLazyLoading();
        this.setupKeyboardShortcuts();
    }

    // ========== Loading States ==========
    setupLoadingStates() {
        // Add loading state to buttons on form submit
        document.addEventListener('submit', (e) => {
            const form = e.target;
            const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
            
            if (submitBtn && !submitBtn.disabled) {
                this.setButtonLoading(submitBtn, true);
                
                // Reset loading state after 5 seconds (fallback)
                setTimeout(() => {
                    this.setButtonLoading(submitBtn, false);
                }, 5000);
            }
        });
    }

    setButtonLoading(button, isLoading) {
        if (isLoading) {
            button.disabled = true;
            button.dataset.originalText = button.textContent;
            button.innerHTML = `
                <span class="loading-spinner" style="width: 1rem; height: 1rem; margin-left: 0.5rem;"></span>
                در حال پردازش...
            `;
        } else {
            button.disabled = false;
            button.textContent = button.dataset.originalText || 'ارسال';
        }
    }

    // ========== Form Enhancements ==========
    setupFormEnhancements() {
        // Auto-resize textareas
        document.querySelectorAll('textarea').forEach(textarea => {
            textarea.addEventListener('input', () => {
                textarea.style.height = 'auto';
                textarea.style.height = textarea.scrollHeight + 'px';
            });
        });

        // Add character counter to text inputs
        document.querySelectorAll('input[maxlength], textarea[maxlength]').forEach(input => {
            this.addCharacterCounter(input);
        });

        // Enhanced file upload
        document.querySelectorAll('input[type="file"]').forEach(input => {
            this.enhanceFileInput(input);
        });

        // Form validation feedback
        document.querySelectorAll('form').forEach(form => {
            form.addEventListener('submit', (e) => {
                this.validateForm(form, e);
            });
        });

        // Real-time validation
        document.querySelectorAll('input, textarea, select').forEach(input => {
            input.addEventListener('blur', () => {
                this.validateField(input);
            });
        });
    }

    addCharacterCounter(input) {
        const maxLength = input.getAttribute('maxlength');
        const counter = document.createElement('div');
        counter.className = 'character-counter';
        counter.style.cssText = `
            font-size: 0.75rem;
            color: #94a3b8;
            text-align: left;
            margin-top: 0.25rem;
        `;
        
        const updateCounter = () => {
            const remaining = maxLength - input.value.length;
            counter.textContent = `${input.value.length}/${maxLength}`;
            counter.style.color = remaining < 10 ? '#dc2626' : '#94a3b8';
        };

        input.addEventListener('input', updateCounter);
        updateCounter();
        
        input.parentNode.appendChild(counter);
    }

    enhanceFileInput(input) {
        // DragDropManager already gave this input a drop zone with its own preview
        if (input.previousElementSibling?.classList.contains('drop-zone')) return;
        const wrapper = document.createElement('div');
        wrapper.className = 'file-input-wrapper';
        wrapper.style.cssText = `
            position: relative;
            display: inline-block;
            width: 100%;
        `;

        const label = document.createElement('label');
        label.className = 'btn-modern btn-modern-secondary';
        label.style.cssText = `
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            width: 100%;
            min-height: 3rem;
            border: 2px dashed #e2e8f0;
            background: #f8fafc;
            transition: all 0.3s ease;
        `;
        label.innerHTML = `
            <svg width="20" height="20" fill="currentColor" viewBox="0 0 20 20">
                <path d="M16.88 9.1A4 4 0 0 1 16 17H5a5 5 0 0 1-1-9.9V7a3 3 0 0 1 4.52-2.59A4.98 4.98 0 0 1 17 8c0 .38-.04.74-.12 1.1zM11 11h3l-4-4-4 4h3v3h2v-3z"/>
            </svg>
            انتخاب فایل
        `;

        const preview = document.createElement('div');
        preview.className = 'file-preview';
        preview.style.cssText = `
            margin-top: 0.5rem;
            padding: 0.5rem;
            background: #f1f5f9;
            border-radius: 0.5rem;
            display: none;
        `;

        if (!input.id) input.id = 'file-' + Math.random().toString(36).slice(2);
        label.htmlFor = input.id;
        input.style.display = 'none';
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(label);
        wrapper.appendChild(input);
        wrapper.appendChild(preview);

        label.addEventListener('dragover', (e) => {
            e.preventDefault();
            label.style.borderColor = '#2563eb';
            label.style.background = '#eff6ff';
        });

        label.addEventListener('dragleave', () => {
            label.style.borderColor = '#e2e8f0';
            label.style.background = '#f8fafc';
        });

        label.addEventListener('drop', (e) => {
            e.preventDefault();
            label.style.borderColor = '#e2e8f0';
            label.style.background = '#f8fafc';
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                input.files = files;
                this.showFilePreview(files[0], preview, label);
            }
        });

        input.addEventListener('change', () => {
            if (input.files.length > 0) {
                this.showFilePreview(input.files[0], preview, label);
            }
        });
    }

    showFilePreview(file, preview, label) {
        const fileSize = (file.size / 1024 / 1024).toFixed(2);
        const fileIcon = this.getFileIcon(file.type);
        
        preview.innerHTML = `
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <div style="font-size: 1.5rem;">${fileIcon}</div>
                <div style="flex: 1;">
                    <div style="font-weight: 500; color: #1e293b;">${escapeHtml(file.name)}</div>
                    <div style="font-size: 0.75rem; color: #64748b;">${fileSize} MB</div>
                </div>
                <button type="button" onclick="this.closest('.file-input-wrapper').querySelector('input').value=''; this.closest('.file-preview').style.display='none';" 
                        style="background: none; border: none; color: #dc2626; cursor: pointer;">
                    <svg width="16" height="16" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"/>
                    </svg>
                </button>
            </div>
        `;
        
        preview.style.display = 'block';
        label.innerHTML = `
            <svg width="20" height="20" fill="currentColor" viewBox="0 0 20 20">
                <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
            فایل انتخاب شد
        `;
        label.style.borderColor = '#059669';
        label.style.background = '#ecfdf5';
        label.style.color = '#059669';
    }

    getFileIcon(fileType) {
        if (fileType.startsWith('image/')) return '🖼️';
        if (fileType.includes('pdf')) return '📄';
        if (fileType.includes('word')) return '📝';
        if (fileType.includes('excel') || fileType.includes('spreadsheet')) return '📊';
        if (fileType.includes('dwg') || fileType.includes('dxf')) return '📐';
        return '📎';
    }

    validateForm(form, event) {
        let isValid = true;
        const inputs = form.querySelectorAll('input[required], textarea[required], select[required]');
        
        inputs.forEach(input => {
            if (!this.validateField(input)) {
                isValid = false;
            }
        });

        if (!isValid) {
            event.preventDefault();
            this.showNotification('لطفاً تمام فیلدهای ضروری را پر کنید', 'error');
        }
    }

    validateField(input) {
        const value = input.value.trim();
        let isValid = true;
        let message = '';

        // Remove existing error styling
        input.classList.remove('is-invalid');
        const existingError = input.parentNode.querySelector('.field-error');
        if (existingError) {
            existingError.remove();
        }

        // Required field validation
        if (input.hasAttribute('required') && !value) {
            isValid = false;
            message = 'این فیلد ضروری است';
        }

        // Email validation
        if (input.type === 'email' && value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
            isValid = false;
            message = 'ایمیل معتبر وارد کنید';
        }

        // Phone validation (Iranian mobile)
        if (input.name === 'mobile_number' && value && !/^09\d{9}$/.test(value)) {
            isValid = false;
            message = 'شماره موبایل معتبر وارد کنید (09xxxxxxxxx)';
        }

        // National ID validation
        if (input.name === 'national_id' && value && !/^\d{10}$/.test(value)) {
            isValid = false;
            message = 'کد ملی باید 10 رقم باشد';
        }

        if (!isValid) {
            input.classList.add('is-invalid');
            const errorDiv = document.createElement('div');
            errorDiv.className = 'field-error';
            errorDiv.style.cssText = `
                color: #dc2626;
                font-size: 0.75rem;
                margin-top: 0.25rem;
            `;
            errorDiv.textContent = message;
            input.parentNode.appendChild(errorDiv);
        }

        return isValid;
    }

    // ========== Table Enhancements ==========
    setupTableEnhancements() {
        document.querySelectorAll('table').forEach(table => {
            this.enhanceTable(table);
        });
    }

    enhanceTable(table) {
        // Add sorting capability
        const headers = table.querySelectorAll('th');
        headers.forEach((header, index) => {
            if (header.textContent.trim()) {
                header.style.cursor = 'pointer';
                header.addEventListener('click', () => {
                    this.sortTable(table, index);
                });
            }
        });

        // Add row hover effects
        const rows = table.querySelectorAll('tbody tr');
        rows.forEach(row => {
            row.addEventListener('mouseenter', () => {
                row.style.backgroundColor = '#f8fafc';
            });
            row.addEventListener('mouseleave', () => {
                row.style.backgroundColor = '';
            });
        });
    }

    sortTable(table, columnIndex) {
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        
        const isAscending = table.dataset.sortDirection !== 'asc';
        table.dataset.sortDirection = isAscending ? 'asc' : 'desc';

        rows.sort((a, b) => {
            const aText = a.cells[columnIndex].textContent.trim();
            const bText = b.cells[columnIndex].textContent.trim();
            
            const aNum = parseFloat(aText.replace(/[^\d.-]/g, ''));
            const bNum = parseFloat(bText.replace(/[^\d.-]/g, ''));
            
            if (!isNaN(aNum) && !isNaN(bNum)) {
                return isAscending ? aNum - bNum : bNum - aNum;
            }
            
            return isAscending ? aText.localeCompare(bText) : bText.localeCompare(aText);
        });

        rows.forEach(row => tbody.appendChild(row));
    }

    // ========== Notifications ==========
    setupNotifications() {
        // Create notification container
        if (!document.getElementById('notification-container')) {
            const container = document.createElement('div');
            container.id = 'notification-container';
            container.style.cssText = `
                position: fixed;
                top: 1rem;
                right: 1rem;
                z-index: 10000;
                max-width: 400px;
            `;
            document.body.appendChild(container);
        }
    }

    showNotification(message, type = 'info', duration = 5000) {
        const container = document.getElementById('notification-container');
        const notification = document.createElement('div');
        
        const colors = {
            success: { bg: '#ecfdf5', border: '#059669', text: '#059669' },
            error: { bg: '#fef2f2', border: '#dc2626', text: '#dc2626' },
            warning: { bg: '#fffbeb', border: '#d97706', text: '#d97706' },
            info: { bg: '#eff6ff', border: '#2563eb', text: '#2563eb' }
        };
        
        const color = colors[type] || colors.info;
        
        notification.style.cssText = `
            background: ${color.bg};
            border: 1px solid ${color.border};
            color: ${color.text};
            padding: 1rem;
            border-radius: 0.5rem;
            margin-bottom: 0.5rem;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
            transform: translateX(100%);
            transition: transform 0.3s ease;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        `;
        
        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️',
            info: 'ℹ️'
        };
        
        notification.innerHTML = `
            <span style="font-size: 1.2rem;">${icons[type] || icons.info}</span>
            <span style="flex: 1;">${escapeHtml(message)}</span>
            <button onclick="this.parentElement.remove()" style="
                background: none;
                border: none;
                color: ${color.text};
                cursor: pointer;
                font-size: 1.2rem;
                padding: 0;
                width: 1.5rem;
                height: 1.5rem;
                display: flex;
                align-items: center;
                justify-content: center;
            ">×</button>
        `;
        
        container.appendChild(notification);
        
        // Animate in
        setTimeout(() => {
            notification.style.transform = 'translateX(0)';
        }, 10);
        
        // Auto remove
        if (duration > 0) {
            setTimeout(() => {
                notification.style.transform = 'translateX(100%)';
                setTimeout(() => {
                    if (notification.parentNode) {
                        notification.remove();
                    }
                }, 300);
            }, duration);
        }
    }

    // ========== Search Enhancements ==========
    setupSearchEnhancements() {
        document.querySelectorAll('input[type="search"], input[name*="search"]').forEach(input => {
            this.enhanceSearch(input);
        });
    }

    enhanceSearch(input) {
        let searchTimeout;
        
        input.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                this.performSearch(input);
            }, 300);
        });
    }

    performSearch(input) {
        const query = input.value.trim();
        const targetTable = input.dataset.target || input.closest('form')?.querySelector('table');
        
        if (targetTable) {
            this.filterTable(targetTable, query);
        }
    }

    filterTable(table, query) {
        const rows = table.querySelectorAll('tbody tr');
        
        rows.forEach(row => {
            const text = row.textContent.toLowerCase();
            const matches = query === '' || text.includes(query.toLowerCase());
            row.style.display = matches ? '' : 'none';
        });
    }

    // ========== Keyboard Shortcuts ==========
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + K for search
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                const searchInput = document.querySelector('input[type="search"], input[name*="search"]');
                if (searchInput) {
                    searchInput.focus();
                }
            }
            
            // Escape to close modals
            if (e.key === 'Escape') {
                const openModal = document.querySelector('.modal.show');
                if (openModal) {
                    const closeBtn = openModal.querySelector('[data-bs-dismiss="modal"]');
                    if (closeBtn) {
                        closeBtn.click();
                    }
                }
            }
        });
    }

    // ========== Lazy Loading ==========
    setupLazyLoading() {
        const images = document.querySelectorAll('img[data-src]');
        
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                        imageObserver.unobserve(img);
                    }
                });
            });
            
            images.forEach(img => imageObserver.observe(img));
        }
    }

    // ========== Progress Bars ==========
    setupProgressBars() {
        document.querySelectorAll('.progress-bar').forEach(bar => {
            const value = bar.dataset.value || 0;
            bar.style.width = '0%';
            
            setTimeout(() => {
                bar.style.transition = 'width 1s ease-in-out';
                bar.style.width = value + '%';
            }, 100);
        });
    }

    // ========== Tooltips ==========
    setupTooltips() {
        document.querySelectorAll('[data-tooltip]').forEach(element => {
            element.addEventListener('mouseenter', (e) => {
                this.showTooltip(e.target, e.target.dataset.tooltip);
            });
            
            element.addEventListener('mouseleave', () => {
                this.hideTooltip();
            });
        });
    }

    showTooltip(element, text) {
        const tooltip = document.createElement('div');
        tooltip.id = 'custom-tooltip';
        tooltip.textContent = text;
        tooltip.style.cssText = `
            position: absolute;
            background: #1e293b;
            color: white;
            padding: 0.5rem 0.75rem;
            border-radius: 0.25rem;
            font-size: 0.75rem;
            z-index: 10001;
            pointer-events: none;
            white-space: nowrap;
        `;
        
        document.body.appendChild(tooltip);
        
        const rect = element.getBoundingClientRect();
        tooltip.style.top = (rect.top - tooltip.offsetHeight - 5) + 'px';
        tooltip.style.left = (rect.left + rect.width / 2 - tooltip.offsetWidth / 2) + 'px';
    }

    hideTooltip() {
        const tooltip = document.getElementById('custom-tooltip');
        if (tooltip) {
            tooltip.remove();
        }
    }

    // ========== Modal Enhancements ==========
    setupModalEnhancements() {
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('show.bs.modal', () => {
                document.body.style.overflow = 'hidden';
            });
            
            modal.addEventListener('hidden.bs.modal', () => {
                document.body.style.overflow = '';
            });
        });
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.modernUI = new ModernUI();
});

// Utility functions for global use
window.showNotification = (message, type, duration) => {
    if (window.modernUI) {
        window.modernUI.showNotification(message, type, duration);
    }
};

window.setButtonLoading = (button, isLoading) => {
    if (window.modernUI) {
        window.modernUI.setButtonLoading(button, isLoading);
    }
};