/**
 * Jalali Date Picker for MelkID
 * Simple Persian date picker with validation
 */

(function() {
    'use strict';
    
    // Persian months
    const persianMonths = [
        'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
        'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'
    ];
    
    // Persian weekdays
    const persianWeekdays = [
        'شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه'
    ];
    
    // Utility functions for Jalali date conversion
    const JalaliUtils = {
        // Check if Jalali year is leap
        isLeapYear: function(year) {
            const breaks = [
                -61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210,
                1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178
            ];
            
            let jp = breaks[0];
            let jump = 0;
            for (let j = 1; j < breaks.length; j++) {
                const jm = breaks[j];
                jump = jm - jp;
                if (year < jm) break;
                jp = jm;
            }
            
            let n = year - jp;
            if (n < jump) {
                if (jump - n < 6) n = n - jump + ((jump + 4) / 6) * 6;
                const leap = ((n + 1) % 33) % 4;
                if (jump == 33 && leap == 1) return true;
                return leap == 1;
            }
            return false;
        },
        
        // Get days in Jalali month
        getDaysInMonth: function(year, month) {
            if (month <= 6) return 31;
            if (month <= 11) return 30;
            return this.isLeapYear(year) ? 30 : 29;
        },
        
        // Validate Jalali date
        isValidDate: function(year, month, day) {
            if (year < 1 || year > 3178) return false;
            if (month < 1 || month > 12) return false;
            if (day < 1) return false;
            
            const daysInMonth = this.getDaysInMonth(year, month);
            return day <= daysInMonth;
        },
        
        // Parse Jalali date string
        parseDate: function(dateString) {
            if (!dateString) return null;
            
            const parts = dateString.split('/');
            if (parts.length !== 3) return null;
            
            const year = parseInt(parts[0]);
            const month = parseInt(parts[1]);
            const day = parseInt(parts[2]);
            
            if (isNaN(year) || isNaN(month) || isNaN(day)) return null;
            if (!this.isValidDate(year, month, day)) return null;
            
            return { year, month, day };
        },
        
        // Format Jalali date
        formatDate: function(year, month, day) {
            const y = year.toString();
            const m = month.toString().padStart(2, '0');
            const d = day.toString().padStart(2, '0');
            return `${y}/${m}/${d}`;
        }
    };
    
    // Initialize date pickers
    function initializeDatePickers() {
        const dateInputs = document.querySelectorAll('.jalali-date, .jalali-datetime');
        
        dateInputs.forEach(input => {
            setupDateInput(input);
        });
    }
    
    function setupDateInput(input) {
        // Add input validation
        input.addEventListener('input', function(e) {
            validateDateInput(e.target);
        });
        
        input.addEventListener('blur', function(e) {
            formatDateInput(e.target);
        });
        
        // Add placeholder behavior
        input.addEventListener('focus', function(e) {
            if (!e.target.value) {
                e.target.placeholder = 'YYYY/MM/DD';
            }
        });
        
        input.addEventListener('blur', function(e) {
            if (!e.target.value) {
                if (e.target.classList.contains('jalali-datetime')) {
                    e.target.placeholder = 'مثال: 1403/08/15 14:30';
                } else {
                    e.target.placeholder = 'مثال: 1403/08/15';
                }
            }
        });
        
        // Add keyboard navigation
        input.addEventListener('keydown', function(e) {
            handleKeyNavigation(e);
        });
    }
    
    function validateDateInput(input) {
        const value = input.value.trim();
        if (!value) {
            clearValidation(input);
            return;
        }
        
        // Check for basic format
        const dateTimePattern = /^\d{4}\/\d{1,2}\/\d{1,2}(\s+\d{1,2}:\d{1,2})?$/;
        if (!dateTimePattern.test(value)) {
            showValidationError(input, 'فرمت تاریخ صحیح نیست');
            return;
        }
        
        // Extract date part
        const datePart = value.split(' ')[0];
        const parsedDate = JalaliUtils.parseDate(datePart);
        
        if (!parsedDate) {
            showValidationError(input, 'تاریخ وارد شده معتبر نیست');
            return;
        }
        
        // Validate time part if exists
        if (input.classList.contains('jalali-datetime') && value.includes(' ')) {
            const timePart = value.split(' ')[1];
            if (timePart && !validateTime(timePart)) {
                showValidationError(input, 'زمان وارد شده معتبر نیست');
                return;
            }
        }
        
        showValidationSuccess(input);
    }
    
    function validateTime(timeString) {
        const timePattern = /^\d{1,2}:\d{1,2}$/;
        if (!timePattern.test(timeString)) return false;
        
        const [hour, minute] = timeString.split(':').map(Number);
        return hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59;
    }
    
    function formatDateInput(input) {
        const value = input.value.trim();
        if (!value) return;
        
        try {
            const parts = value.split(' ');
            const datePart = parts[0];
            const timePart = parts[1];
            
            const parsedDate = JalaliUtils.parseDate(datePart);
            if (parsedDate) {
                let formattedValue = JalaliUtils.formatDate(parsedDate.year, parsedDate.month, parsedDate.day);
                
                if (timePart && input.classList.contains('jalali-datetime')) {
                    const timePattern = /^(\d{1,2}):(\d{1,2})$/;
                    const timeMatch = timePart.match(timePattern);
                    if (timeMatch) {
                        const hour = timeMatch[1].padStart(2, '0');
                        const minute = timeMatch[2].padStart(2, '0');
                        formattedValue += ` ${hour}:${minute}`;
                    }
                }
                
                input.value = formattedValue;
            }
        } catch (error) {
            console.warn('Date formatting error:', error);
        }
    }
    
    function handleKeyNavigation(e) {
        const input = e.target;
        const value = input.value;
        
        // Auto-add slashes
        if (e.key >= '0' && e.key <= '9') {
            const cursorPos = input.selectionStart;
            const newValue = value.slice(0, cursorPos) + e.key + value.slice(cursorPos);
            
            // Add slash after year (4 digits)
            if (newValue.length === 4 && !newValue.includes('/')) {
                setTimeout(() => {
                    input.value = newValue + '/';
                    input.setSelectionRange(5, 5);
                }, 0);
                e.preventDefault();
                return;
            }
            
            // Add slash after month
            if (newValue.length === 7 && newValue.split('/').length === 2) {
                setTimeout(() => {
                    input.value = newValue + '/';
                    input.setSelectionRange(8, 8);
                }, 0);
                e.preventDefault();
                return;
            }
        }
        
        // Handle backspace
        if (e.key === 'Backspace') {
            const cursorPos = input.selectionStart;
            if (cursorPos > 0 && value[cursorPos - 1] === '/') {
                setTimeout(() => {
                    const newPos = Math.max(0, cursorPos - 1);
                    input.setSelectionRange(newPos, newPos);
                }, 0);
            }
        }
    }
    
    function showValidationError(input, message) {
        clearValidation(input);
        
        input.classList.add('is-invalid');
        
        const errorDiv = document.createElement('div');
        errorDiv.className = 'invalid-feedback';
        errorDiv.textContent = message;
        
        input.parentNode.appendChild(errorDiv);
    }
    
    function showValidationSuccess(input) {
        clearValidation(input);
        input.classList.add('is-valid');
    }
    
    function clearValidation(input) {
        input.classList.remove('is-invalid', 'is-valid');
        
        const existingFeedback = input.parentNode.querySelector('.invalid-feedback, .valid-feedback');
        if (existingFeedback) {
            existingFeedback.remove();
        }
    }
    
    // Add today button functionality
    function addTodayButton(input) {
        const todayBtn = document.createElement('button');
        todayBtn.type = 'button';
        todayBtn.className = 'btn btn-outline-secondary btn-sm mt-1';
        todayBtn.innerHTML = '<i class="fas fa-calendar-day me-1"></i>امروز';
        
        todayBtn.addEventListener('click', function() {
            const today = new Date();
            // Convert to Jalali (this is a simplified conversion)
            // In a real implementation, you'd use a proper conversion library
            const jalaliYear = today.getFullYear() - 621;
            const jalaliMonth = today.getMonth() + 1;
            const jalaliDay = today.getDate();
            
            input.value = JalaliUtils.formatDate(jalaliYear, jalaliMonth, jalaliDay);
            validateDateInput(input);
        });
        
        input.parentNode.appendChild(todayBtn);
    }
    
    // Initialize when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        initializeDatePickers();
    });
    
    // Re-initialize for dynamically added elements
    document.addEventListener('input', function(e) {
        if (e.target.matches('.jalali-date, .jalali-datetime') && !e.target.dataset.initialized) {
            setupDateInput(e.target);
            e.target.dataset.initialized = 'true';
        }
    });
    
    // Export for global use
    window.JalaliDatePicker = {
        init: initializeDatePickers,
        setupInput: setupDateInput,
        utils: JalaliUtils
    };
})();