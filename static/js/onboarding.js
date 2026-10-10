// Onboarding Tutorial System for MelkID
class OnboardingTutorial {
    constructor() {
        this.currentStep = 0;
        this.steps = [];
        this.isActive = false;
        this.overlay = null;
        this.tooltip = null;
        this.userProgress = this.loadProgress();
        this.init();
    }

    init() {
        this.createOverlay();
        this.createTooltip();
        this.setupTutorials();
        this.checkAutoStart();
    }

    loadProgress() {
        const saved = localStorage.getItem('melkid-onboarding-progress');
        return saved ? JSON.parse(saved) : {};
    }

    saveProgress() {
        localStorage.setItem('melkid-onboarding-progress', JSON.stringify(this.userProgress));
    }

    setupTutorials() {
        // Define different tutorials for different pages
        this.tutorials = {
            home: [
                {
                    target: '.navbar-brand',
                    title: 'خوش آمدید به MelkID',
                    content: 'این سامانه جامع خدمات شهری و روستایی است که به شما کمک می‌کند تا به راحتی درخواست‌های خود را ثبت و پیگیری کنید.',
                    position: 'bottom'
                },
                {
                    target: '.services-grid',
                    title: 'خدمات موجود',
                    content: 'از اینجا می‌توانید انواع خدمات مانند صدور پروانه ساختمان، تایید سکونت و سایر خدمات شهرداری را مشاهده کنید.',
                    position: 'top'
                },
                {
                    target: '.theme-toggle',
                    title: 'تنظیمات ظاهری',
                    content: 'با کلیک روی این دکمه می‌توانید بین حالت روشن و تاریک تغییر دهید. برای تنظیمات بیشتر، آن را نگه دارید.',
                    position: 'bottom'
                }
            ],
            dashboard: [
                {
                    target: '.user-info',
                    title: 'اطلاعات کاربری',
                    content: 'در این بخش اطلاعات پروفایل شما نمایش داده می‌شود. می‌توانید آن را ویرایش کنید.',
                    position: 'bottom'
                },
                {
                    target: '.stats-cards',
                    title: 'آمار درخواست‌ها',
                    content: 'اینجا خلاصه‌ای از درخواست‌های شما و وضعیت آن‌ها را مشاهده می‌کنید.',
                    position: 'top'
                },
                {
                    target: '.quick-actions',
                    title: 'اقدامات سریع',
                    content: 'از این بخش می‌توانید به سرعت درخواست جدید ثبت کنید یا درخواست‌های قبلی را پیگیری نمایید.',
                    position: 'left'
                },
                {
                    target: '.recent-requests',
                    title: 'درخواست‌های اخیر',
                    content: 'آخرین درخواست‌های شما در این قسمت نمایش داده می‌شود.',
                    position: 'top'
                }
            ],
            services: [
                {
                    target: '.service-categories',
                    title: 'دسته‌بندی خدمات',
                    content: 'خدمات بر اساس نوع دسته‌بندی شده‌اند. می‌توانید خدمت مورد نظر خود را انتخاب کنید.',
                    position: 'bottom'
                },
                {
                    target: '.service-search',
                    title: 'جستجوی خدمات',
                    content: 'برای پیدا کردن سریع خدمت مورد نظر، از جعبه جستجو استفاده کنید.',
                    position: 'bottom'
                }
            ],
            properties: [
                {
                    target: '.property-filters',
                    title: 'فیلترهای جستجو',
                    content: 'با استفاده از این فیلترها می‌توانید املاک را بر اساس نوع، قیمت و منطقه جستجو کنید.',
                    position: 'bottom'
                },
                {
                    target: '.add-property-btn',
                    title: 'افزودن ملک',
                    content: 'برای ثبت ملک جدید یا آگهی املاک، از این دکمه استفاده کنید.',
                    position: 'left'
                }
            ]
        };
    }

    createOverlay() {
        this.overlay = document.createElement('div');
        this.overlay.className = 'onboarding-overlay';
        this.overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            z-index: 9998;
            display: none;
            transition: opacity 0.3s ease;
        `;
        document.body.appendChild(this.overlay);
    }

    createTooltip() {
        this.tooltip = document.createElement('div');
        this.tooltip.className = 'onboarding-tooltip';
        this.tooltip.style.cssText = `
            position: absolute;
            z-index: 9999;
            background: var(--bg-modal);
            border: 1px solid var(--border-color);
            border-radius: var(--border-radius-lg);
            box-shadow: var(--shadow-xl);
            padding: 1.5rem;
            max-width: 350px;
            display: none;
            animation: slideInUp 0.3s ease-out;
        `;

        this.tooltip.innerHTML = `
            <div class="tooltip-header">
                <h4 class="tooltip-title" style="margin: 0 0 0.5rem 0; color: var(--text-primary);"></h4>
                <button class="tooltip-close" style="
                    position: absolute;
                    top: 1rem;
                    left: 1rem;
                    background: none;
                    border: none;
                    font-size: 1.2rem;
                    cursor: pointer;
                    color: var(--text-muted);
                ">✕</button>
            </div>
            <div class="tooltip-content" style="
                color: var(--text-secondary);
                line-height: 1.6;
                margin-bottom: 1.5rem;
            "></div>
            <div class="tooltip-footer" style="
                display: flex;
                justify-content: space-between;
                align-items: center;
            ">
                <div class="step-indicator" style="
                    color: var(--text-muted);
                    font-size: 0.9rem;
                "></div>
                <div class="tooltip-buttons">
                    <button class="btn-skip" style="
                        background: none;
                        border: 1px solid var(--border-color);
                        color: var(--text-secondary);
                        padding: 0.5rem 1rem;
                        border-radius: var(--border-radius-sm);
                        margin-left: 0.5rem;
                        cursor: pointer;
                    ">رد کردن</button>
                    <button class="btn-prev" style="
                        background: var(--secondary-color);
                        border: none;
                        color: white;
                        padding: 0.5rem 1rem;
                        border-radius: var(--border-radius-sm);
                        margin-left: 0.5rem;
                        cursor: pointer;
                        display: none;
                    ">قبلی</button>
                    <button class="btn-next" style="
                        background: var(--primary-color);
                        border: none;
                        color: white;
                        padding: 0.5rem 1rem;
                        border-radius: var(--border-radius-sm);
                        cursor: pointer;
                    ">بعدی</button>
                </div>
            </div>
        `;

        document.body.appendChild(this.tooltip);
        this.bindTooltipEvents();
    }

    bindTooltipEvents() {
        const closeBtn = this.tooltip.querySelector('.tooltip-close');
        const skipBtn = this.tooltip.querySelector('.btn-skip');
        const prevBtn = this.tooltip.querySelector('.btn-prev');
        const nextBtn = this.tooltip.querySelector('.btn-next');

        closeBtn.addEventListener('click', () => this.stop());
        skipBtn.addEventListener('click', () => this.skip());
        prevBtn.addEventListener('click', () => this.previousStep());
        nextBtn.addEventListener('click', () => this.nextStep());

        // Close on overlay click
        this.overlay.addEventListener('click', () => this.stop());
    }

    checkAutoStart() {
        const currentPage = this.getCurrentPage();
        const hasSeenTutorial = this.userProgress[currentPage];

        // Auto-start tutorial for new users
        if (!hasSeenTutorial && this.tutorials[currentPage]) {
            setTimeout(() => {
                this.showWelcomeDialog();
            }, 1000);
        }
    }

    getCurrentPage() {
        const path = window.location.pathname;
        
        if (path === '/' || path === '/home/') return 'home';
        if (path.includes('/dashboard/')) return 'dashboard';
        if (path.includes('/services/')) return 'services';
        if (path.includes('/properties/')) return 'properties';
        
        return 'home';
    }

    showWelcomeDialog() {
        const dialog = document.createElement('div');
        dialog.className = 'welcome-dialog';
        dialog.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            z-index: 10000;
            background: var(--bg-modal);
            border-radius: var(--border-radius-lg);
            padding: 2rem;
            max-width: 400px;
            width: 90%;
            box-shadow: var(--shadow-xl);
            text-align: center;
            animation: zoomIn 0.3s ease-out;
        `;

        dialog.innerHTML = `
            <div style="font-size: 3rem; margin-bottom: 1rem;">👋</div>
            <h3 style="color: var(--text-primary); margin-bottom: 1rem;">خوش آمدید!</h3>
            <p style="color: var(--text-secondary); margin-bottom: 2rem; line-height: 1.6;">
                آیا می‌خواهید راهنمای کوتاهی از نحوه استفاده از سامانه مشاهده کنید؟
            </p>
            <div>
                <button class="btn-decline" style="
                    background: none;
                    border: 1px solid var(--border-color);
                    color: var(--text-secondary);
                    padding: 0.75rem 1.5rem;
                    border-radius: var(--border-radius-sm);
                    margin-left: 1rem;
                    cursor: pointer;
                ">نه، ممنون</button>
                <button class="btn-accept" style="
                    background: var(--primary-color);
                    border: none;
                    color: white;
                    padding: 0.75rem 1.5rem;
                    border-radius: var(--border-radius-sm);
                    cursor: pointer;
                ">بله، شروع کنیم</button>
            </div>
        `;

        // Add backdrop
        const backdrop = document.createElement('div');
        backdrop.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 9999;
        `;

        document.body.appendChild(backdrop);
        document.body.appendChild(dialog);

        dialog.querySelector('.btn-accept').addEventListener('click', () => {
            backdrop.remove();
            dialog.remove();
            this.start();
        });

        dialog.querySelector('.btn-decline').addEventListener('click', () => {
            backdrop.remove();
            dialog.remove();
            this.markAsCompleted();
        });
    }

    start(tutorialName = null) {
        const currentPage = tutorialName || this.getCurrentPage();
        this.steps = this.tutorials[currentPage] || [];
        
        if (this.steps.length === 0) {
            console.log('No tutorial available for current page');
            return;
        }

        this.currentStep = 0;
        this.isActive = true;
        this.overlay.style.display = 'block';
        
        setTimeout(() => {
            this.overlay.style.opacity = '1';
            this.showStep();
        }, 100);
    }

    stop() {
        this.isActive = false;
        this.overlay.style.opacity = '0';
        this.tooltip.style.display = 'none';
        
        setTimeout(() => {
            this.overlay.style.display = 'none';
            this.clearHighlight();
        }, 300);
    }

    skip() {
        this.markAsCompleted();
        this.stop();
    }

    nextStep() {
        if (this.currentStep < this.steps.length - 1) {
            this.currentStep++;
            this.showStep();
        } else {
            this.complete();
        }
    }

    previousStep() {
        if (this.currentStep > 0) {
            this.currentStep--;
            this.showStep();
        }
    }

    showStep() {
        const step = this.steps[this.currentStep];
        if (!step) return;

        const target = document.querySelector(step.target);
        if (!target) {
            console.warn(`Tutorial target not found: ${step.target}`);
            this.nextStep();
            return;
        }

        this.highlightElement(target);
        this.positionTooltip(target, step);
        this.updateTooltipContent(step);
        this.updateTooltipButtons();
    }

    highlightElement(element) {
        this.clearHighlight();
        
        const rect = element.getBoundingClientRect();
        const highlight = document.createElement('div');
        highlight.className = 'onboarding-highlight';
        highlight.style.cssText = `
            position: absolute;
            top: ${rect.top + window.scrollY - 5}px;
            left: ${rect.left + window.scrollX - 5}px;
            width: ${rect.width + 10}px;
            height: ${rect.height + 10}px;
            border: 3px solid var(--primary-color);
            border-radius: var(--border-radius);
            z-index: 9997;
            pointer-events: none;
            animation: pulse 2s infinite;
            box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.7);
        `;

        // Add pulse animation
        const style = document.createElement('style');
        style.textContent = `
            @keyframes pulse {
                0% {
                    box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.7);
                }
                70% {
                    box-shadow: 0 0 0 10px rgba(37, 99, 235, 0);
                }
                100% {
                    box-shadow: 0 0 0 0 rgba(37, 99, 235, 0);
                }
            }
        `;
        document.head.appendChild(style);

        document.body.appendChild(highlight);
        this.currentHighlight = highlight;

        // Scroll element into view
        element.scrollIntoView({
            behavior: 'smooth',
            block: 'center',
            inline: 'center'
        });
    }

    clearHighlight() {
        if (this.currentHighlight) {
            this.currentHighlight.remove();
            this.currentHighlight = null;
        }
    }

    positionTooltip(target, step) {
        const rect = target.getBoundingClientRect();
        const tooltipRect = this.tooltip.getBoundingClientRect();
        
        let top, left;

        switch (step.position) {
            case 'top':
                top = rect.top + window.scrollY - tooltipRect.height - 20;
                left = rect.left + window.scrollX + (rect.width / 2) - (tooltipRect.width / 2);
                break;
            case 'bottom':
                top = rect.bottom + window.scrollY + 20;
                left = rect.left + window.scrollX + (rect.width / 2) - (tooltipRect.width / 2);
                break;
            case 'left':
                top = rect.top + window.scrollY + (rect.height / 2) - (tooltipRect.height / 2);
                left = rect.left + window.scrollX - tooltipRect.width - 20;
                break;
            case 'right':
                top = rect.top + window.scrollY + (rect.height / 2) - (tooltipRect.height / 2);
                left = rect.right + window.scrollX + 20;
                break;
            default:
                top = rect.bottom + window.scrollY + 20;
                left = rect.left + window.scrollX;
        }

        // Keep tooltip within viewport
        const maxLeft = window.innerWidth - tooltipRect.width - 20;
        const maxTop = window.innerHeight + window.scrollY - tooltipRect.height - 20;
        
        left = Math.max(20, Math.min(left, maxLeft));
        top = Math.max(20, Math.min(top, maxTop));

        this.tooltip.style.top = `${top}px`;
        this.tooltip.style.left = `${left}px`;
        this.tooltip.style.display = 'block';
    }

    updateTooltipContent(step) {
        this.tooltip.querySelector('.tooltip-title').textContent = step.title;
        this.tooltip.querySelector('.tooltip-content').textContent = step.content;
        this.tooltip.querySelector('.step-indicator').textContent = 
            `مرحله ${this.currentStep + 1} از ${this.steps.length}`;
    }

    updateTooltipButtons() {
        const prevBtn = this.tooltip.querySelector('.btn-prev');
        const nextBtn = this.tooltip.querySelector('.btn-next');

        prevBtn.style.display = this.currentStep > 0 ? 'inline-block' : 'none';
        nextBtn.textContent = this.currentStep === this.steps.length - 1 ? 'پایان' : 'بعدی';
    }

    complete() {
        this.markAsCompleted();
        this.showCompletionMessage();
        this.stop();
    }

    markAsCompleted() {
        const currentPage = this.getCurrentPage();
        this.userProgress[currentPage] = true;
        this.saveProgress();
    }

    showCompletionMessage() {
        const message = document.createElement('div');
        message.className = 'completion-message';
        message.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            z-index: 10000;
            background: var(--success-color);
            color: white;
            padding: 1.5rem 2rem;
            border-radius: var(--border-radius-lg);
            box-shadow: var(--shadow-xl);
            text-align: center;
            animation: zoomIn 0.3s ease-out;
        `;

        message.innerHTML = `
            <div style="font-size: 2rem; margin-bottom: 0.5rem;">🎉</div>
            <h4 style="margin: 0;">راهنما تکمیل شد!</h4>
            <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">حالا می‌توانید از تمام امکانات استفاده کنید.</p>
        `;

        document.body.appendChild(message);

        setTimeout(() => {
            message.remove();
        }, 3000);
    }

    // Public methods
    startTutorial(tutorialName) {
        this.start(tutorialName);
    }

    resetProgress() {
        localStorage.removeItem('melkid-onboarding-progress');
        this.userProgress = {};
    }

    addCustomTutorial(name, steps) {
        this.tutorials[name] = steps;
    }

    isCompleted(tutorialName = null) {
        const page = tutorialName || this.getCurrentPage();
        return this.userProgress[page] || false;
    }
}

// Initialize Onboarding Tutorial
(function (init) { if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init(); })(() => {
    window.onboardingTutorial = new OnboardingTutorial();
    
    // Add tutorial trigger button to help menu
    const helpButton = document.createElement('button');
    helpButton.className = 'tutorial-trigger';
    helpButton.innerHTML = '❓';
    helpButton.title = 'راهنمای استفاده';
    helpButton.style.cssText = `
        position: fixed;
        bottom: 90px;
        right: 20px;
        z-index: 1000;
        width: 50px;
        height: 50px;
        border-radius: 50%;
        border: none;
        background: var(--info-color);
        color: white;
        font-size: 1.2rem;
        cursor: pointer;
        box-shadow: var(--shadow-md);
        transition: var(--transition);
    `;

    helpButton.addEventListener('click', () => {
        window.onboardingTutorial.start();
    });

    document.body.appendChild(helpButton);
    
    console.log('📚 Onboarding Tutorial system loaded');
});