/**
 * Theme Initialization Script
 * Ensures theme is applied immediately on page load
 */

(function() {
    'use strict';
    
    // Get stored theme or default to light
    const storedTheme = localStorage.getItem('melkid-theme');
    const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    const theme = storedTheme || systemTheme;
    
    // Apply theme immediately to prevent flash
    document.documentElement.setAttribute('data-theme', theme);
    
    // Apply high contrast if enabled
    const highContrast = localStorage.getItem('melkid-high-contrast');
    if (highContrast === 'true') {
        document.documentElement.classList.add('high-contrast');
    }
    
    // Apply font size
    const fontSize = localStorage.getItem('melkid-font-size');
    if (fontSize && fontSize !== 'normal') {
        document.documentElement.classList.add(`font-size-${fontSize}`);
    }
    
    // Update theme toggle icon when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        updateThemeIcon(theme);
    });
    
    function updateThemeIcon(theme) {
        const themeIcon = document.getElementById('themeIcon');
        const themeToggle = document.getElementById('themeToggle');
        
        if (themeIcon && themeToggle) {
            const icons = {
                light: 'fas fa-moon',
                dark: 'fas fa-sun'
            };

            const titles = {
                light: 'تغییر به تم تاریک',
                dark: 'تغییر به تم روشن'
            };

            themeIcon.className = icons[theme] || icons.light;
            themeToggle.title = titles[theme] || titles.light;
        }
        
        // Also update menu icon
        const themeIconMenu = document.getElementById('themeIconMenu');
        if (themeIconMenu) {
            themeIconMenu.className = (theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon') + ' me-2';
        }
    }
    
    // Listen for theme changes
    window.addEventListener('storage', function(e) {
        if (e.key === 'melkid-theme') {
            const newTheme = e.newValue || 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            updateThemeIcon(newTheme);
        }
    });
    
    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
        if (!localStorage.getItem('melkid-theme')) {
            const newTheme = e.matches ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            updateThemeIcon(newTheme);
        }
    });
})();