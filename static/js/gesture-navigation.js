// Gesture Navigation for MelkID Mobile
class GestureNavigation {
    constructor() {
        this.isEnabled = this.isMobileDevice();
        this.gestures = {
            swipeLeft: [],
            swipeRight: [],
            swipeUp: [],
            swipeDown: [],
            pinchIn: [],
            pinchOut: [],
            doubleTap: [],
            longPress: []
        };
        
        this.touchStartX = 0;
        this.touchStartY = 0;
        this.touchEndX = 0;
        this.touchEndY = 0;
        this.touchStartTime = 0;
        this.lastTap = 0;
        this.longPressTimer = null;
        
        this.minSwipeDistance = 50;
        this.maxSwipeTime = 300;
        this.doubleTapDelay = 300;
        this.longPressDelay = 500;
        
        if (this.isEnabled) {
            this.init();
        }
    }

    isMobileDevice() {
        return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
               ('ontouchstart' in window) ||
               (navigator.maxTouchPoints > 0);
    }

    init() {
        this.setupDefaultGestures();
        this.bindTouchEvents();
        this.createGestureIndicator();
        this.addGestureHints();
        console.log('👆 Gesture Navigation initialized for mobile');
    }

    setupDefaultGestures() {
        // Navigation gestures
        this.addGesture('swipeRight', () => {
            if (window.history.length > 1) {
                window.history.back();
                this.showGestureToast('بازگشت به صفحه قبل');
            }
        });

        this.addGesture('swipeLeft', () => {
            if (window.history.length > 1) {
                window.history.forward();
                this.showGestureToast('رفتن به صفحه بعد');
            }
        });

        this.addGesture('swipeUp', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
            this.showGestureToast('رفتن به بالای صفحه');
        });

        this.addGesture('swipeDown', () => {
            window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
            this.showGestureToast('رفتن به پایین صفحه');
        });

        // Menu gestures
        this.addGesture('doubleTap', (event) => {
            const target = event.target.closest('.card, .modern-card, .stat-card');
            if (target) {
                target.classList.add('animate-pulse');
                setTimeout(() => target.classList.remove('animate-pulse'), 1000);
                
                // If it's a clickable card, trigger click
                if (target.onclick || target.querySelector('a')) {
                    const link = target.querySelector('a');
                    if (link) {
                        link.click();
                    } else if (target.onclick) {
                        target.click();
                    }
                }
            }
        });

        this.addGesture('longPress', (event) => {
            const target = event.target;
            
            // Show context menu for interactive elements
            if (target.matches('button, .btn, a, .card')) {
                this.showContextMenu(event, target);
            }
        });

        // Zoom gestures for images and maps
        this.addGesture('pinchOut', (event) => {
            const target = event.target.closest('img, .map-container, .image-viewer');
            if (target) {
                this.zoomIn(target);
            }
        });

        this.addGesture('pinchIn', (event) => {
            const target = event.target.closest('img, .map-container, .image-viewer');
            if (target) {
                this.zoomOut(target);
            }
        });
    }

    bindTouchEvents() {
        let initialDistance = 0;
        let initialScale = 1;

        document.addEventListener('touchstart', (e) => {
            this.touchStartX = e.changedTouches[0].screenX;
            this.touchStartY = e.changedTouches[0].screenY;
            this.touchStartTime = Date.now();

            // Handle multi-touch for pinch gestures
            if (e.touches.length === 2) {
                initialDistance = this.getDistance(e.touches[0], e.touches[1]);
            }

            // Long press detection
            this.longPressTimer = setTimeout(() => {
                this.triggerGesture('longPress', e);
                navigator.vibrate && navigator.vibrate(50); // Haptic feedback
            }, this.longPressDelay);

        }, { passive: false });

        document.addEventListener('touchmove', (e) => {
            // Cancel long press if finger moves
            if (this.longPressTimer) {
                clearTimeout(this.longPressTimer);
                this.longPressTimer = null;
            }

            // Handle pinch gestures
            if (e.touches.length === 2) {
                e.preventDefault();
                const currentDistance = this.getDistance(e.touches[0], e.touches[1]);
                const scale = currentDistance / initialDistance;

                if (scale > 1.2) {
                    this.triggerGesture('pinchOut', e);
                    initialDistance = currentDistance; // Reset to prevent multiple triggers
                } else if (scale < 0.8) {
                    this.triggerGesture('pinchIn', e);
                    initialDistance = currentDistance;
                }
            }
        }, { passive: false });

        document.addEventListener('touchend', (e) => {
            // Clear long press timer
            if (this.longPressTimer) {
                clearTimeout(this.longPressTimer);
                this.longPressTimer = null;
            }

            this.touchEndX = e.changedTouches[0].screenX;
            this.touchEndY = e.changedTouches[0].screenY;
            
            const touchDuration = Date.now() - this.touchStartTime;
            
            // Double tap detection
            const now = Date.now();
            if (now - this.lastTap < this.doubleTapDelay) {
                this.triggerGesture('doubleTap', e);
                navigator.vibrate && navigator.vibrate([50, 50, 50]); // Double tap feedback
            }
            this.lastTap = now;

            // Swipe detection
            if (touchDuration < this.maxSwipeTime) {
                this.detectSwipe(e);
            }
        }, { passive: false });
    }

    getDistance(touch1, touch2) {
        const dx = touch1.clientX - touch2.clientX;
        const dy = touch1.clientY - touch2.clientY;
        return Math.sqrt(dx * dx + dy * dy);
    }

    detectSwipe(event) {
        const deltaX = this.touchEndX - this.touchStartX;
        const deltaY = this.touchEndY - this.touchStartY;
        const absDeltaX = Math.abs(deltaX);
        const absDeltaY = Math.abs(deltaY);

        // Check if swipe distance is sufficient
        if (Math.max(absDeltaX, absDeltaY) < this.minSwipeDistance) {
            return;
        }

        // Determine swipe direction
        if (absDeltaX > absDeltaY) {
            // Horizontal swipe
            if (deltaX > 0) {
                this.triggerGesture('swipeRight', event);
            } else {
                this.triggerGesture('swipeLeft', event);
            }
        } else {
            // Vertical swipe
            if (deltaY > 0) {
                this.triggerGesture('swipeDown', event);
            } else {
                this.triggerGesture('swipeUp', event);
            }
        }
    }

    addGesture(gestureType, callback) {
        if (!this.gestures[gestureType]) {
            this.gestures[gestureType] = [];
        }
        this.gestures[gestureType].push(callback);
    }

    removeGesture(gestureType, callback) {
        if (this.gestures[gestureType]) {
            const index = this.gestures[gestureType].indexOf(callback);
            if (index > -1) {
                this.gestures[gestureType].splice(index, 1);
            }
        }
    }

    triggerGesture(gestureType, event) {
        if (this.gestures[gestureType]) {
            this.gestures[gestureType].forEach(callback => {
                try {
                    callback(event);
                } catch (error) {
                    console.error(`Error in ${gestureType} gesture:`, error);
                }
            });
        }
    }

    createGestureIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'gesture-indicator';
        indicator.style.cssText = `
            position: fixed;
            top: 10px;
            right: 10px;
            z-index: 999;
            background: var(--glass-bg);
            backdrop-filter: blur(10px);
            border: 1px solid var(--glass-border);
            border-radius: 20px;
            padding: 0.5rem;
            font-size: 0.8rem;
            color: var(--text-primary);
            opacity: 0;
            transition: opacity 0.3s ease;
            pointer-events: none;
            max-width: 200px;
            text-align: center;
        `;
        
        document.body.appendChild(indicator);
        this.gestureIndicator = indicator;
    }

    showGestureToast(message) {
        if (this.gestureIndicator) {
            this.gestureIndicator.textContent = message;
            this.gestureIndicator.style.opacity = '1';
            
            setTimeout(() => {
                this.gestureIndicator.style.opacity = '0';
            }, 2000);
        }
    }

    showContextMenu(event, target) {
        // Remove existing context menu
        const existingMenu = document.querySelector('.gesture-context-menu');
        if (existingMenu) {
            existingMenu.remove();
        }

        const menu = document.createElement('div');
        menu.className = 'gesture-context-menu';
        menu.style.cssText = `
            position: fixed;
            z-index: 2000;
            background: var(--bg-modal);
            border: 1px solid var(--border-color);
            border-radius: var(--border-radius);
            box-shadow: var(--shadow-xl);
            padding: 0.5rem 0;
            min-width: 150px;
            animation: slideInUp 0.2s ease-out;
        `;

        // Position menu at touch point
        const rect = target.getBoundingClientRect();
        menu.style.left = `${rect.left}px`;
        menu.style.top = `${rect.bottom + 10}px`;

        // Add menu items based on target type
        const menuItems = this.getContextMenuItems(target);
        menuItems.forEach(item => {
            const menuItem = document.createElement('div');
            menuItem.className = 'context-menu-item';
            menuItem.style.cssText = `
                padding: 0.75rem 1rem;
                cursor: pointer;
                color: var(--text-primary);
                border-bottom: 1px solid var(--border-light);
                transition: background-color 0.2s ease;
            `;
            menuItem.textContent = item.label;
            
            menuItem.addEventListener('click', () => {
                item.action();
                menu.remove();
            });

            menuItem.addEventListener('touchstart', (e) => {
                e.preventDefault();
                menuItem.style.backgroundColor = 'var(--bg-secondary)';
            });

            menu.appendChild(menuItem);
        });

        document.body.appendChild(menu);

        // Remove menu after 5 seconds or on outside touch
        setTimeout(() => {
            if (menu.parentNode) {
                menu.remove();
            }
        }, 5000);

        document.addEventListener('touchstart', function removeMenu(e) {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('touchstart', removeMenu);
            }
        });
    }

    getContextMenuItems(target) {
        const items = [];

        if (target.matches('a')) {
            items.push(
                { label: 'باز کردن لینک', action: () => target.click() },
                { label: 'کپی لینک', action: () => this.copyToClipboard(target.href) }
            );
        }

        if (target.matches('button, .btn')) {
            items.push(
                { label: 'اجرای دکمه', action: () => target.click() }
            );
        }

        if (target.matches('img')) {
            items.push(
                { label: 'مشاهده تصویر', action: () => this.openImageViewer(target) },
                { label: 'کپی آدرس تصویر', action: () => this.copyToClipboard(target.src) }
            );
        }

        if (target.matches('.card, .modern-card')) {
            items.push(
                { label: 'مشاهده جزئیات', action: () => target.click() },
                { label: 'اشتراک‌گذاری', action: () => this.shareContent(target) }
            );
        }

        // Default items
        items.push(
            { label: 'بازگشت', action: () => window.history.back() },
            { label: 'رفرش صفحه', action: () => window.location.reload() }
        );

        return items;
    }

    zoomIn(element) {
        const currentScale = parseFloat(element.style.transform?.match(/scale\(([^)]+)\)/)?.[1] || 1);
        const newScale = Math.min(currentScale * 1.2, 3);
        element.style.transform = `scale(${newScale})`;
        element.style.transition = 'transform 0.3s ease';
        
        this.showGestureToast('بزرگ‌نمایی');
    }

    zoomOut(element) {
        const currentScale = parseFloat(element.style.transform?.match(/scale\(([^)]+)\)/)?.[1] || 1);
        const newScale = Math.max(currentScale * 0.8, 0.5);
        element.style.transform = `scale(${newScale})`;
        element.style.transition = 'transform 0.3s ease';
        
        this.showGestureToast('کوچک‌نمایی');
    }

    copyToClipboard(text) {
        if (navigator.clipboard) {
            navigator.clipboard.writeText(text).then(() => {
                this.showGestureToast('کپی شد');
            });
        } else {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            this.showGestureToast('کپی شد');
        }
    }

    openImageViewer(img) {
        const viewer = document.createElement('div');
        viewer.className = 'image-viewer-modal';
        viewer.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.9);
            z-index: 3000;
            display: flex;
            align-items: center;
            justify-content: center;
            animation: fadeIn 0.3s ease;
        `;

        const viewerImg = document.createElement('img');
        viewerImg.src = img.src;
        viewerImg.alt = img.alt || 'تصویر بزرگ‌شده';
        viewerImg.style.cssText = `
            max-width: 90%;
            max-height: 90%;
            object-fit: contain;
            border-radius: var(--border-radius);
        `;

        const closeBtn = document.createElement('button');
        closeBtn.innerHTML = '✕';
        closeBtn.style.cssText = `
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(255, 255, 255, 0.2);
            border: none;
            color: white;
            font-size: 1.5rem;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            cursor: pointer;
        `;

        closeBtn.addEventListener('click', () => viewer.remove());
        viewer.addEventListener('click', (e) => {
            if (e.target === viewer) viewer.remove();
        });

        viewer.appendChild(viewerImg);
        viewer.appendChild(closeBtn);
        document.body.appendChild(viewer);
    }

    shareContent(element) {
        if (navigator.share) {
            const title = element.querySelector('h1, h2, h3, h4, h5, h6')?.textContent || 'MelkID';
            const text = element.textContent.substring(0, 100) + '...';
            const url = window.location.href;

            navigator.share({
                title: title,
                text: text,
                url: url
            }).then(() => {
                this.showGestureToast('اشتراک‌گذاری شد');
            }).catch(() => {
                this.copyToClipboard(url);
                this.showGestureToast('لینک کپی شد');
            });
        } else {
            this.copyToClipboard(window.location.href);
            this.showGestureToast('لینک کپی شد');
        }
    }

    addGestureHints() {
        // Add subtle hints for gesture-enabled elements
        const style = document.createElement('style');
        style.textContent = `
            .gesture-enabled {
                position: relative;
            }
            
            .gesture-enabled::after {
                content: '👆';
                position: absolute;
                top: 5px;
                right: 5px;
                font-size: 0.8rem;
                opacity: 0.3;
                pointer-events: none;
            }
            
            @media (hover: hover) {
                .gesture-enabled::after {
                    display: none;
                }
            }
        `;
        document.head.appendChild(style);

        // Add gesture hints to interactive elements
        document.querySelectorAll('.card, .modern-card, img, button, .btn').forEach(el => {
            el.classList.add('gesture-enabled');
        });
    }

    // Public methods
    enable() {
        this.isEnabled = true;
        if (this.gestureIndicator) {
            this.gestureIndicator.style.display = 'block';
        }
    }

    disable() {
        this.isEnabled = false;
        if (this.gestureIndicator) {
            this.gestureIndicator.style.display = 'none';
        }
    }

    setMinSwipeDistance(distance) {
        this.minSwipeDistance = distance;
    }

    setMaxSwipeTime(time) {
        this.maxSwipeTime = time;
    }
}

// Initialize Gesture Navigation
(function (init) { if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init(); })(() => {
    window.gestureNavigation = new GestureNavigation();
    
    if (window.gestureNavigation.isEnabled) {
        console.log('👆 Gesture Navigation enabled for mobile device');
        console.log('🤏 Available gestures: swipe, pinch, double-tap, long-press');
    }
});