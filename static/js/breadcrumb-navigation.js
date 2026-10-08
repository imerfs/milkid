// Breadcrumb Navigation System for MelkID
class BreadcrumbNavigation {
    constructor() {
        this.breadcrumbs = [];
        this.maxBreadcrumbs = 5;
        this.init();
    }

    init() {
        this.createBreadcrumbContainer();
        this.updateBreadcrumbs();
        this.bindEvents();
    }

    createBreadcrumbContainer() {
        // Check if breadcrumb container already exists
        if (document.querySelector('.breadcrumb-container')) {
            return;
        }

        const container = document.createElement('div');
        container.className = 'breadcrumb-container';
        container.style.cssText = `
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 0.75rem 0;
            position: sticky;
            top: 0;
            z-index: 100;
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
        `;

        const breadcrumbNav = document.createElement('nav');
        breadcrumbNav.className = 'container';
        breadcrumbNav.setAttribute('aria-label', 'breadcrumb');

        const breadcrumbList = document.createElement('ol');
        breadcrumbList.className = 'breadcrumb mb-0';
        breadcrumbList.style.cssText = `
            background: none;
            padding: 0;
            margin: 0;
            font-size: 0.9rem;
        `;

        breadcrumbNav.appendChild(breadcrumbList);
        container.appendChild(breadcrumbNav);

        // Insert after navbar
        const navbar = document.querySelector('.navbar');
        if (navbar) {
            navbar.parentNode.insertBefore(container, navbar.nextSibling);
        } else {
            document.body.insertBefore(container, document.body.firstChild);
        }

        this.breadcrumbList = breadcrumbList;
    }

    updateBreadcrumbs() {
        const currentPath = window.location.pathname;
        const breadcrumbs = this.generateBreadcrumbs(currentPath);
        this.renderBreadcrumbs(breadcrumbs);
    }

    generateBreadcrumbs(path) {
        const breadcrumbs = [
            { name: 'خانه', url: '/', icon: 'fas fa-home' }
        ];

        // Define route mappings
        const routeMap = {
            '/dashboard/': { name: 'داشبورد', icon: 'fas fa-tachometer-alt' },
            '/services/': { name: 'خدمات', icon: 'fas fa-clipboard-list' },
            '/properties/': { name: 'املاک', icon: 'fas fa-building' },
            '/profile/': { name: 'پروفایل', icon: 'fas fa-user' },
            '/settings/': { name: 'تنظیمات', icon: 'fas fa-cog' },
            '/about/': { name: 'درباره ما', icon: 'fas fa-info-circle' },
            '/contact/': { name: 'تماس با ما', icon: 'fas fa-phone' },
            
            // Dashboard sub-pages
            '/dashboard/track-requests/': { name: 'پیگیری درخواست‌ها', parent: '/dashboard/' },
            '/dashboard/payments/': { name: 'پرداخت‌ها', parent: '/dashboard/' },
            '/dashboard/messages/': { name: 'پیام‌ها', parent: '/dashboard/' },
            '/dashboard/notifications/': { name: 'اعلان‌ها', parent: '/dashboard/' },
            
            // Services sub-pages
            '/services/request/': { name: 'درخواست جدید', parent: '/services/' },
            '/services/building-permit/': { name: 'پروانه ساختمان', parent: '/services/' },
            '/services/residence-confirmation/': { name: 'تایید سکونت', parent: '/services/' },
            
            // Properties sub-pages
            '/properties/add/': { name: 'افزودن ملک', parent: '/properties/' },
            '/properties/my-ads/': { name: 'آگهی‌های من', parent: '/properties/' },
            '/properties/search/': { name: 'جستجو', parent: '/properties/' },
            
            // Admin pages
            '/admin/': { name: 'مدیریت سیستم', icon: 'fas fa-shield-alt' },
            '/admin/users/': { name: 'کاربران', parent: '/admin/' },
            '/admin/requests/': { name: 'درخواست‌ها', parent: '/admin/' },
            '/admin/properties/': { name: 'املاک', parent: '/admin/' },
        };

        // Handle dynamic routes with parameters
        const dynamicRoutes = [
            { pattern: /^\/services\/(\d+)\/$/, name: 'جزئیات خدمت', parent: '/services/' },
            { pattern: /^\/properties\/(\d+)\/$/, name: 'جزئیات ملک', parent: '/properties/' },
            { pattern: /^\/dashboard\/requests\/(\d+)\/$/, name: 'جزئیات درخواست', parent: '/dashboard/' },
            { pattern: /^\/users\/(\d+)\/$/, name: 'پروفایل کاربر', parent: '/admin/users/' },
        ];

        // Check for exact match first
        if (routeMap[path]) {
            const route = routeMap[path];
            
            // Add parent breadcrumbs if exists
            if (route.parent && routeMap[route.parent]) {
                const parent = routeMap[route.parent];
                breadcrumbs.push({
                    name: parent.name,
                    url: route.parent,
                    icon: parent.icon
                });
            }
            
            breadcrumbs.push({
                name: route.name,
                url: path,
                icon: route.icon,
                active: true
            });
        } else {
            // Check dynamic routes
            let matched = false;
            for (const dynamicRoute of dynamicRoutes) {
                const match = path.match(dynamicRoute.pattern);
                if (match) {
                    // Add parent breadcrumbs
                    if (dynamicRoute.parent && routeMap[dynamicRoute.parent]) {
                        const parent = routeMap[dynamicRoute.parent];
                        breadcrumbs.push({
                            name: parent.name,
                            url: dynamicRoute.parent,
                            icon: parent.icon
                        });
                    }
                    
                    breadcrumbs.push({
                        name: dynamicRoute.name,
                        url: path,
                        active: true
                    });
                    matched = true;
                    break;
                }
            }
            
            // Fallback: generate from path segments
            if (!matched && path !== '/') {
                const segments = path.split('/').filter(segment => segment);
                let currentPath = '';
                
                segments.forEach((segment, index) => {
                    currentPath += '/' + segment;
                    if (index < segments.length - 1) {
                        currentPath += '/';
                    }
                    
                    const isLast = index === segments.length - 1;
                    const route = routeMap[currentPath + '/'] || routeMap[currentPath];
                    
                    breadcrumbs.push({
                        name: route ? route.name : this.formatSegmentName(segment),
                        url: currentPath + (currentPath.endsWith('/') ? '' : '/'),
                        icon: route ? route.icon : null,
                        active: isLast
                    });
                });
            }
        }

        return breadcrumbs.slice(-this.maxBreadcrumbs);
    }

    formatSegmentName(segment) {
        // Convert URL segment to readable Persian name
        const segmentMap = {
            'dashboard': 'داشبورد',
            'services': 'خدمات',
            'properties': 'املاک',
            'profile': 'پروفایل',
            'settings': 'تنظیمات',
            'admin': 'مدیریت',
            'users': 'کاربران',
            'requests': 'درخواست‌ها',
            'payments': 'پرداخت‌ها',
            'messages': 'پیام‌ها',
            'notifications': 'اعلان‌ها',
            'add': 'افزودن',
            'edit': 'ویرایش',
            'view': 'مشاهده',
            'search': 'جستجو'
        };

        return segmentMap[segment] || segment.replace(/-/g, ' ');
    }

    renderBreadcrumbs(breadcrumbs) {
        if (!this.breadcrumbList) return;

        this.breadcrumbList.innerHTML = breadcrumbs.map((crumb, index) => {
            const isLast = index === breadcrumbs.length - 1;
            const icon = crumb.icon ? `<i class="${crumb.icon} me-1"></i>` : '';
            
            if (isLast || crumb.active) {
                return `
                    <li class="breadcrumb-item active" aria-current="page">
                        ${icon}${crumb.name}
                    </li>
                `;
            } else {
                return `
                    <li class="breadcrumb-item">
                        <a href="${crumb.url}" class="text-decoration-none" style="color: var(--primary-color);">
                            ${icon}${crumb.name}
                        </a>
                    </li>
                `;
            }
        }).join('');

        // Add custom styles
        this.addBreadcrumbStyles();
    }

    addBreadcrumbStyles() {
        if (document.querySelector('#breadcrumb-styles')) return;

        const style = document.createElement('style');
        style.id = 'breadcrumb-styles';
        style.textContent = `
            .breadcrumb-item {
                color: var(--text-secondary);
                font-weight: 500;
            }
            
            .breadcrumb-item.active {
                color: var(--text-primary);
                font-weight: 600;
            }
            
            .breadcrumb-item + .breadcrumb-item::before {
                content: "←";
                color: var(--text-muted);
                margin: 0 0.5rem;
            }
            
            .breadcrumb-item a:hover {
                color: var(--primary-dark) !important;
                text-decoration: underline !important;
            }
            
            @media (max-width: 768px) {
                .breadcrumb-container {
                    padding: 0.5rem 0;
                }
                
                .breadcrumb {
                    font-size: 0.8rem;
                }
                
                .breadcrumb-item {
                    max-width: 100px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }
            }
        `;
        document.head.appendChild(style);
    }

    bindEvents() {
        // Update breadcrumbs on navigation
        window.addEventListener('popstate', () => {
            this.updateBreadcrumbs();
        });

        // Update breadcrumbs on AJAX navigation (if used)
        document.addEventListener('DOMContentLoaded', () => {
            this.updateBreadcrumbs();
        });
    }

    // Public methods
    addCustomBreadcrumb(name, url, icon = null) {
        this.breadcrumbs.push({ name, url, icon });
        this.updateBreadcrumbs();
    }

    clearBreadcrumbs() {
        this.breadcrumbs = [];
        this.updateBreadcrumbs();
    }

    hide() {
        const container = document.querySelector('.breadcrumb-container');
        if (container) {
            container.style.display = 'none';
        }
    }

    show() {
        const container = document.querySelector('.breadcrumb-container');
        if (container) {
            container.style.display = 'block';
        }
    }
}

// Quick Actions Panel
class QuickActionsPanel {
    constructor() {
        this.isVisible = false;
        this.actions = [];
        this.init();
    }

    init() {
        this.setupDefaultActions();
        this.createPanel();
        this.bindEvents();
    }

    setupDefaultActions() {
        this.actions = [
            {
                id: 'new-request',
                name: 'درخواست جدید',
                icon: 'fas fa-plus',
                url: '/services/request/',
                color: 'var(--primary-color)',
                shortcut: 'Ctrl+N'
            },
            {
                id: 'track-requests',
                name: 'پیگیری درخواست‌ها',
                icon: 'fas fa-search',
                url: '/dashboard/track-requests/',
                color: 'var(--info-color)',
                shortcut: 'Ctrl+T'
            },
            {
                id: 'payments',
                name: 'پرداخت‌ها',
                icon: 'fas fa-credit-card',
                url: '/dashboard/payments/',
                color: 'var(--warning-color)',
                shortcut: 'Ctrl+Shift+P'
            },
            {
                id: 'messages',
                name: 'پیام‌ها',
                icon: 'fas fa-envelope',
                url: '/dashboard/messages/',
                color: 'var(--success-color)',
                shortcut: 'Ctrl+M'
            },
            {
                id: 'properties',
                name: 'املاک',
                icon: 'fas fa-building',
                url: '/properties/',
                color: 'var(--secondary-color)',
                shortcut: 'Ctrl+P'
            },
            {
                id: 'profile',
                name: 'پروفایل',
                icon: 'fas fa-user',
                url: '/profile/',
                color: 'var(--text-secondary)',
                shortcut: 'Alt+P'
            }
        ];
    }

    createPanel() {
        const panel = document.createElement('div');
        panel.className = 'quick-actions-panel';
        panel.style.cssText = `
            position: fixed;
            top: 50%;
            left: -300px;
            transform: translateY(-50%);
            width: 280px;
            background: var(--glass-bg);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--glass-border);
            border-radius: 0 var(--border-radius-lg) var(--border-radius-lg) 0;
            box-shadow: var(--glass-shadow);
            z-index: 1000;
            transition: left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            padding: 1.5rem;
        `;

        const header = document.createElement('div');
        header.style.cssText = `
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border-light);
        `;

        header.innerHTML = `
            <h6 style="margin: 0; color: var(--text-primary); font-weight: 600;">
                <i class="fas fa-bolt me-2"></i>
                اقدامات سریع
            </h6>
            <button class="close-panel" style="
                background: none;
                border: none;
                color: var(--text-muted);
                font-size: 1.2rem;
                cursor: pointer;
                padding: 0.25rem;
                border-radius: 4px;
                transition: var(--transition-fast);
            ">
                <i class="fas fa-times"></i>
            </button>
        `;

        const actionsList = document.createElement('div');
        actionsList.className = 'actions-list';
        actionsList.innerHTML = this.actions.map(action => `
            <a href="${action.url}" class="action-item" data-action="${action.id}" style="
                display: flex;
                align-items: center;
                gap: 1rem;
                padding: 1rem;
                margin-bottom: 0.5rem;
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: var(--border-radius);
                text-decoration: none;
                color: var(--text-primary);
                transition: var(--transition);
                position: relative;
                overflow: hidden;
            ">
                <div class="action-icon" style="
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    background: ${action.color};
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 1.1rem;
                ">
                    <i class="${action.icon}"></i>
                </div>
                <div class="action-content" style="flex: 1;">
                    <div class="action-name" style="font-weight: 600; margin-bottom: 0.25rem;">
                        ${action.name}
                    </div>
                    <div class="action-shortcut" style="
                        font-size: 0.8rem;
                        color: var(--text-muted);
                        font-family: monospace;
                    ">
                        ${action.shortcut}
                    </div>
                </div>
                <i class="fas fa-chevron-left" style="color: var(--text-muted); font-size: 0.9rem;"></i>
            </a>
        `).join('');

        // Toggle button
        const toggleButton = document.createElement('button');
        toggleButton.className = 'quick-actions-toggle';
        toggleButton.style.cssText = `
            position: fixed;
            top: 50%;
            left: 10px;
            transform: translateY(-50%);
            width: 50px;
            height: 50px;
            background: var(--primary-color);
            border: none;
            border-radius: 0 25px 25px 0;
            color: white;
            font-size: 1.2rem;
            cursor: pointer;
            z-index: 999;
            transition: var(--transition);
            box-shadow: var(--shadow-md);
        `;
        toggleButton.innerHTML = '<i class="fas fa-bolt"></i>';
        toggleButton.title = 'اقدامات سریع (Alt+Q)';

        panel.appendChild(header);
        panel.appendChild(actionsList);
        document.body.appendChild(panel);
        document.body.appendChild(toggleButton);

        this.panel = panel;
        this.toggleButton = toggleButton;

        this.addPanelStyles();
    }

    addPanelStyles() {
        if (document.querySelector('#quick-actions-styles')) return;

        const style = document.createElement('style');
        style.id = 'quick-actions-styles';
        style.textContent = `
            .action-item:hover {
                background: rgba(255, 255, 255, 0.2) !important;
                border-color: rgba(255, 255, 255, 0.3) !important;
                transform: translateX(5px);
            }
            
            .action-item:hover .action-icon {
                transform: scale(1.1);
            }
            
            .quick-actions-toggle:hover {
                background: var(--primary-dark);
                transform: translateY(-50%) scale(1.1);
            }
            
            .close-panel:hover {
                background: rgba(255, 255, 255, 0.1);
                color: var(--text-primary);
            }
            
            @media (max-width: 768px) {
                .quick-actions-panel {
                    width: 250px;
                    left: -250px;
                    padding: 1rem;
                }
                
                .action-item {
                    padding: 0.75rem;
                }
                
                .action-icon {
                    width: 35px !important;
                    height: 35px !important;
                    font-size: 1rem !important;
                }
            }
        `;
        document.head.appendChild(style);
    }

    bindEvents() {
        // Toggle panel
        this.toggleButton.addEventListener('click', () => {
            this.toggle();
        });

        // Close panel
        this.panel.querySelector('.close-panel').addEventListener('click', () => {
            this.hide();
        });

        // Close on outside click
        document.addEventListener('click', (e) => {
            if (this.isVisible && 
                !this.panel.contains(e.target) && 
                !this.toggleButton.contains(e.target)) {
                this.hide();
            }
        });

        // Keyboard shortcut
        document.addEventListener('keydown', (e) => {
            if (e.altKey && e.key === 'q') {
                e.preventDefault();
                this.toggle();
            }
            
            if (e.key === 'Escape' && this.isVisible) {
                this.hide();
            }
        });

        // Action item clicks
        this.panel.addEventListener('click', (e) => {
            const actionItem = e.target.closest('.action-item');
            if (actionItem) {
                const actionId = actionItem.dataset.action;
                this.executeAction(actionId);
            }
        });
    }

    show() {
        this.panel.style.left = '0';
        this.toggleButton.style.left = '280px';
        this.isVisible = true;
        
        // Add animation to action items
        const actionItems = this.panel.querySelectorAll('.action-item');
        actionItems.forEach((item, index) => {
            item.style.animationDelay = `${index * 0.1}s`;
            item.classList.add('animate-slide-right');
        });
    }

    hide() {
        this.panel.style.left = '-300px';
        this.toggleButton.style.left = '10px';
        this.isVisible = false;
    }

    toggle() {
        if (this.isVisible) {
            this.hide();
        } else {
            this.show();
        }
    }

    executeAction(actionId) {
        const action = this.actions.find(a => a.id === actionId);
        if (action) {
            // Add click effect
            const actionElement = this.panel.querySelector(`[data-action="${actionId}"]`);
            if (actionElement) {
                actionElement.style.transform = 'scale(0.95)';
                setTimeout(() => {
                    actionElement.style.transform = '';
                }, 150);
            }
            
            // Navigate after animation
            setTimeout(() => {
                window.location.href = action.url;
            }, 200);
        }
    }

    addCustomAction(action) {
        this.actions.push(action);
        this.refreshPanel();
    }

    removeAction(actionId) {
        this.actions = this.actions.filter(a => a.id !== actionId);
        this.refreshPanel();
    }

    refreshPanel() {
        const actionsList = this.panel.querySelector('.actions-list');
        actionsList.innerHTML = this.actions.map(action => `
            <a href="${action.url}" class="action-item" data-action="${action.id}">
                <!-- Action item HTML -->
            </a>
        `).join('');
    }
}

// Initialize components
document.addEventListener('DOMContentLoaded', () => {
    window.breadcrumbNavigation = new BreadcrumbNavigation();
    window.quickActionsPanel = new QuickActionsPanel();
    
    console.log('🧭 Breadcrumb Navigation loaded');
    console.log('⚡ Quick Actions Panel loaded (Alt+Q to toggle)');
});