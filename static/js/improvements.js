/**
 * MelkID Improvements JavaScript
 * Loading States, User Feedback, Navigation
 */

(function() {
    'use strict';

    // ============================================
    // Loading Overlay System
    // ============================================
    const LoadingOverlay = {
        show: function(message = 'در حال بارگذاری...') {
            let overlay = document.getElementById('loadingOverlay');
            if (!overlay) {
                overlay = this.create(message);
            }
            overlay.querySelector('.loading-text').textContent = message;
            overlay.classList.add('active');
        },

        hide: function() {
            const overlay = document.getElementById('loadingOverlay');
            if (overlay) {
                overlay.classList.remove('active');
            }
        },

        create: function(message) {
            const overlay = document.createElement('div');
            overlay.id = 'loadingOverlay';
            overlay.className = 'loading-overlay';
            overlay.innerHTML = `
                <div class="loading-content">
                    <div class="spinner spinner-large"></div>
                    <div class="loading-text">${message}</div>
                </div>
            `;
            document.body.appendChild(overlay);
            return overlay;
        }
    };

    // ============================================
    // Form Submission with Loading State
    // ============================================
    document.addEventListener('submit', function(e) {
        const form = e.target;
        if (form.classList.contains('no-loading')) return;

        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn && !submitBtn.classList.contains('btn-loading')) {
            submitBtn.classList.add('btn-loading');
            submitBtn.disabled = true;

            // Show loading overlay
            LoadingOverlay.show('در حال ارسال...');

            // Auto hide if form submission takes too long (fallback)
            setTimeout(() => {
                LoadingOverlay.hide();
                if (submitBtn) {
                    submitBtn.classList.remove('btn-loading');
                    submitBtn.disabled = false;
                }
            }, 10000);
        }
    });

    // Hide loading on page load
    window.addEventListener('load', function() {
        LoadingOverlay.hide();
    });

    // ============================================
    // Feedback Messages System
    // ============================================
    const FeedbackMessage = {
        show: function(message, type = 'info', duration = 3000) {
            const feedbackEl = document.createElement('div');
            feedbackEl.className = `feedback-message ${type}`;
            feedbackEl.innerHTML = `
                <i class="fas fa-${this.getIcon(type)} me-2"></i>
                ${message}
            `;
            document.body.appendChild(feedbackEl);

            // Trigger animation
            setTimeout(() => feedbackEl.classList.add('show'), 10);

            // Auto remove
            setTimeout(() => {
                feedbackEl.classList.remove('show');
                setTimeout(() => feedbackEl.remove(), 300);
            }, duration);
        },

        getIcon: function(type) {
            const icons = {
                success: 'check-circle',
                error: 'exclamation-circle',
                warning: 'exclamation-triangle',
                info: 'info-circle'
            };
            return icons[type] || 'info-circle';
        }
    };

    // Make it globally available
    window.showMessage = FeedbackMessage.show.bind(FeedbackMessage);

    // Show Django messages as feedback
    document.addEventListener('DOMContentLoaded', function() {
        const djangoMessages = document.querySelectorAll('.alert[role="alert"]');
        djangoMessages.forEach(msg => {
            const type = msg.classList.contains('alert-success') ? 'success' :
                        msg.classList.contains('alert-danger') ? 'error' :
                        msg.classList.contains('alert-warning') ? 'warning' : 'info';
            
            FeedbackMessage.show(msg.textContent.trim(), type);
            msg.remove();
        });
    });

    // ============================================
    // Back to Top Button
    // ============================================
    const BackToTop = {
        button: null,

        init: function() {
            this.button = document.createElement('button');
            this.button.id = 'backToTop';
            this.button.innerHTML = '<i class="fas fa-arrow-up"></i>';
            this.button.setAttribute('aria-label', 'بازگشت به بالا');
            document.body.appendChild(this.button);

            this.button.addEventListener('click', () => {
                window.scrollTo({
                    top: 0,
                    behavior: 'smooth'
                });
            });

            window.addEventListener('scroll', () => this.toggle());
        },

        toggle: function() {
            if (window.pageYOffset > 300) {
                this.button.classList.add('show');
            } else {
                this.button.classList.remove('show');
            }
        }
    };

    // ============================================
    // Confirmation Dialogs
    // ============================================
    document.addEventListener('click', function(e) {
        const target = e.target.closest('[data-confirm]');
        if (target) {
            const message = target.getAttribute('data-confirm');
            if (!confirm(message)) {
                e.preventDefault();
                e.stopPropagation();
            }
        }
    });

    // ============================================
    // AJAX Form Submission
    // ============================================
    const AjaxForm = {
        init: function() {
            document.querySelectorAll('.ajax-form').forEach(form => {
                form.addEventListener('submit', (e) => this.handleSubmit(e));
            });
        },

        handleSubmit: function(e) {
            e.preventDefault();
            const form = e.target;
            const formData = new FormData(form);
            const url = form.action;
            const method = form.method.toUpperCase();

            LoadingOverlay.show();

            fetch(url, {
                method: method,
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': this.getCsrfToken()
                }
            })
            .then(response => response.json())
            .then(data => {
                LoadingOverlay.hide();
                if (data.success) {
                    FeedbackMessage.show(data.message || 'عملیات با موفقیت انجام شد', 'success');
                    if (data.redirect) {
                        setTimeout(() => window.location.href = data.redirect, 1000);
                    }
                } else {
                    FeedbackMessage.show(data.message || 'خطایی رخ داد', 'error');
                }
            })
            .catch(error => {
                LoadingOverlay.hide();
                FeedbackMessage.show('خطا در ارتباط با سرور', 'error');
                console.error('Error:', error);
            });
        },

        getCsrfToken: function() {
            return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        }
    };

    // ============================================
    // Auto-hide Alerts
    // ============================================
    document.addEventListener('DOMContentLoaded', function() {
        const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(alert => {
            setTimeout(() => {
                alert.style.opacity = '0';
                setTimeout(() => alert.remove(), 300);
            }, 5000);
        });
    });

    // ============================================
    // Input Character Counter
    // ============================================
    document.querySelectorAll('[data-max-length]').forEach(input => {
        const maxLength = input.getAttribute('data-max-length');
        const counter = document.createElement('small');
        counter.className = 'form-text text-muted';
        input.parentNode.appendChild(counter);

        const updateCounter = () => {
            const remaining = maxLength - input.value.length;
            counter.textContent = `${remaining} کاراکتر باقی‌مانده`;
            if (remaining < 10) {
                counter.classList.add('text-danger');
            } else {
                counter.classList.remove('text-danger');
            }
        };

        input.addEventListener('input', updateCounter);
        updateCounter();
    });

    // ============================================
    // Tooltip Enhancement
    // ============================================
    document.querySelectorAll('[data-toggle="tooltip"]').forEach(el => {
        el.classList.add('tooltip-custom');
        el.setAttribute('data-tooltip', el.getAttribute('title') || el.getAttribute('data-title'));
    });

    // ============================================
    // File Upload Preview
    // ============================================
    document.querySelectorAll('input[type="file"]').forEach(input => {
        input.addEventListener('change', function(e) {
            const fileName = e.target.files[0]?.name || 'فایلی انتخاب نشده';
            const label = document.querySelector(`label[for="${e.target.id}"]`);
            if (label) {
                const originalText = label.getAttribute('data-original-text') || label.textContent;
                label.setAttribute('data-original-text', originalText);
                label.textContent = fileName;
            }

            // Show preview for images
            if (e.target.files[0]?.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = function(event) {
                    let preview = document.getElementById(`preview-${input.id}`);
                    if (!preview) {
                        preview = document.createElement('img');
                        preview.id = `preview-${input.id}`;
                        preview.className = 'img-thumbnail mt-2';
                        preview.style.maxHeight = '200px';
                        input.parentNode.appendChild(preview);
                    }
                    preview.src = event.target.result;
                };
                reader.readAsDataURL(e.target.files[0]);
            }
        });
    });

    // ============================================
    // Debounce Function for Search
    // ============================================
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // Search with debounce
    document.querySelectorAll('[data-search]').forEach(input => {
        const searchFunc = debounce(() => {
            // Trigger search
            LoadingOverlay.show('در حال جستجو...');
            // Your search logic here
        }, 500);

        input.addEventListener('input', searchFunc);
    });

    // ============================================
    // Initialize All
    // ============================================
    document.addEventListener('DOMContentLoaded', function() {
        BackToTop.init();
        AjaxForm.init();
    });

    // ============================================
    // Expose utilities globally
    // ============================================
    window.MelkID = {
        loading: LoadingOverlay,
        message: FeedbackMessage,
        debounce: debounce
    };

})();

// ============================================
// Page Visibility API for better UX
// ============================================
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        console.log('صفحه مخفی شد');
    } else {
        console.log('کاربر بازگشت');
        // Optional: refresh data when user returns
    }
});

// ============================================
// Online/Offline Detection
// ============================================
window.addEventListener('online', function() {
    window.showMessage('اتصال اینترنت برقرار شد', 'success');
});

window.addEventListener('offline', function() {
    window.showMessage('اتصال اینترنت قطع شد', 'warning');
});
