/**
 * Geographic Selector - Cascading Dropdown Handler
 * 
 * This script provides dynamic cascading dropdown functionality for Iranian geographic data:
 * Province (استان) > County (شهرستان) > District (بخش) > Dehestan (دهستان) > City/Village (شهر/روستا)
 */

(function() {
    'use strict';

    /**
     * Initialize geographic selectors
     */
    function initGeographicSelectors() {
        const patterns = [
            { 
                province: 'id_province_citizen', 
                county: 'id_county_citizen', 
                district: 'id_district_citizen', 
                dehestan: 'id_dehestan_citizen', 
                cityVillage: 'id_city_village_citizen',
                isVillage: 'id_is_village_citizen',
                dehestanContainer: 'dehestan_container_citizen'
            },
            { 
                province: 'id_province_role', 
                county: 'id_county_role', 
                district: 'id_district_role', 
                dehestan: 'id_dehestan_role', 
                cityVillage: 'id_city_village_role',
                isVillage: 'id_is_village_role',
                dehestanContainer: 'dehestan_field'
            },
            { 
                province: 'id_province', 
                county: 'id_county', 
                district: 'id_district', 
                dehestan: 'id_dehestan', 
                cityVillage: 'id_city_village',
                isVillage: 'id_is_village',
                dehestanContainer: 'dehestan-field'
            }
        ];

        patterns.forEach(pattern => {
            const provinceSelect = document.getElementById(pattern.province);
            if (provinceSelect) {
                console.log(`Initializing geographic selector with pattern: ${pattern.province}`);
                setupGeographicSelector(pattern);
            }
        });
    }

    /**
     * Setup a geographic selector with given ID pattern
     */
    function setupGeographicSelector(pattern) {
        const provinceSelect = document.getElementById(pattern.province);
        const countySelect = document.getElementById(pattern.county);
        const districtSelect = document.getElementById(pattern.district);
        const dehestanSelect = document.getElementById(pattern.dehestan);
        const cityVillageSelect = document.getElementById(pattern.cityVillage);
        const isVillageCheckbox = document.getElementById(pattern.isVillage);
        const dehestanContainer = document.getElementById(pattern.dehestanContainer);

        if (!provinceSelect) return;

        // Village checkbox toggle handler
        if (isVillageCheckbox) {
            const toggleDehestan = function() {
                const isChecked = isVillageCheckbox.checked;
                if (dehestanContainer) {
                    if (isChecked) {
                        dehestanContainer.classList.remove('hidden');
                        dehestanContainer.style.display = '';
                    } else {
                        dehestanContainer.classList.add('hidden');
                        dehestanContainer.style.display = 'none';
                        if (dehestanSelect) {
                            resetDropdown(dehestanSelect, 'ابتدا بخش را انتخاب کنید');
                            dehestanSelect.disabled = true;
                        }
                    }
                }
                const districtId = districtSelect ? districtSelect.value : null;
                if (districtId) {
                    if (isChecked && dehestanSelect) {
                        loadDehestans(districtId, dehestanSelect);
                        dehestanSelect.disabled = false;
                    }
                    if (cityVillageSelect) {
                        loadCitiesVillages(districtId, isChecked && dehestanSelect ? dehestanSelect.value : null, cityVillageSelect);
                    }
                }
            };

            isVillageCheckbox.addEventListener('change', toggleDehestan);
            // Initial state
            if (dehestanContainer && !isVillageCheckbox.checked) {
                dehestanContainer.classList.add('hidden');
                dehestanContainer.style.display = 'none';
            }
        }

        // Check initial state on page load (supports post-back after form errors)
        function checkInitialState() {
            const currentProvinceId = provinceSelect.value;
            if (currentProvinceId) {
                if (countySelect) {
                    countySelect.disabled = false;
                    const currentCountyId = countySelect.value || countySelect.dataset.selected;
                    if (currentCountyId) {
                        if (districtSelect) {
                            districtSelect.disabled = false;
                            const currentDistrictId = districtSelect.value || districtSelect.dataset.selected;
                            if (currentDistrictId) {
                                if (cityVillageSelect) {
                                    cityVillageSelect.disabled = false;
                                }
                                if (dehestanSelect) {
                                    dehestanSelect.disabled = false;
                                }
                            } else if (districtSelect.options.length <= 1) {
                                loadDistricts(currentCountyId, districtSelect);
                            }
                        }
                    } else if (countySelect.options.length <= 1) {
                        loadCounties(currentProvinceId, countySelect);
                    }
                }
            } else {
                if (countySelect && !countySelect.value) countySelect.disabled = true;
                if (districtSelect && !districtSelect.value) districtSelect.disabled = true;
                if (cityVillageSelect && !cityVillageSelect.value) cityVillageSelect.disabled = true;
                if (dehestanSelect && !dehestanSelect.value) dehestanSelect.disabled = true;
            }
        }

        // Initialize state right away
        checkInitialState();

        // Province change handler
        provinceSelect.addEventListener('change', function() {
            const provinceId = this.value;
            console.log('Province changed:', provinceId);

            if (countySelect) {
                if (provinceId) {
                    loadCounties(provinceId, countySelect);
                    countySelect.disabled = false;
                } else {
                    resetDropdown(countySelect, 'ابتدا استان را انتخاب کنید');
                    countySelect.disabled = true;
                }
            }

            // Reset child dropdowns
            if (districtSelect) {
                resetDropdown(districtSelect, 'ابتدا شهرستان را انتخاب کنید');
                districtSelect.disabled = true;
            }
            if (dehestanSelect) {
                resetDropdown(dehestanSelect, 'ابتدا بخش را انتخاب کنید');
                dehestanSelect.disabled = true;
            }
            if (cityVillageSelect) {
                resetDropdown(cityVillageSelect, 'ابتدا بخش را انتخاب کنید');
                cityVillageSelect.disabled = true;
            }
        });

        // County change handler
        if (countySelect) {
            countySelect.addEventListener('change', function() {
                const countyId = this.value;
                console.log('County changed:', countyId);

                if (districtSelect) {
                    if (countyId) {
                        loadDistricts(countyId, districtSelect, function() {
                            if (cityVillageSelect) {
                                resetDropdown(cityVillageSelect, 'ابتدا بخش را انتخاب کنید');
                                cityVillageSelect.disabled = true;
                            }
                        });
                        districtSelect.disabled = false;
                    } else {
                        resetDropdown(districtSelect, 'ابتدا شهرستان را انتخاب کنید');
                        districtSelect.disabled = true;
                        if (cityVillageSelect) {
                            resetDropdown(cityVillageSelect, 'ابتدا بخش را انتخاب کنید');
                            cityVillageSelect.disabled = true;
                        }
                    }
                }

                if (dehestanSelect) {
                    resetDropdown(dehestanSelect, 'ابتدا بخش را انتخاب کنید');
                    dehestanSelect.disabled = true;
                }
            });
        }

        // District change handler
        if (districtSelect) {
            districtSelect.addEventListener('change', function() {
                const districtId = this.value;
                console.log('District changed:', districtId);

                if (districtId) {
                    // Load dehestans if village checkbox is checked
                    if (dehestanSelect && isVillageCheckbox && isVillageCheckbox.checked) {
                        loadDehestans(districtId, dehestanSelect);
                        dehestanSelect.disabled = false;
                    }

                    // Load cities/villages
                    if (cityVillageSelect) {
                        loadCitiesVillages(districtId, null, cityVillageSelect);
                        cityVillageSelect.disabled = false;
                    }
                } else {
                    if (dehestanSelect) {
                        resetDropdown(dehestanSelect, 'ابتدا بخش را انتخاب کنید');
                        dehestanSelect.disabled = true;
                    }
                    if (cityVillageSelect) {
                        resetDropdown(cityVillageSelect, 'ابتدا بخش را انتخاب کنید');
                        cityVillageSelect.disabled = true;
                    }
                }
            });
        }

        // Dehestan change handler
        if (dehestanSelect) {
            dehestanSelect.addEventListener('change', function() {
                const dehestanId = this.value;
                const districtId = districtSelect ? districtSelect.value : null;
                console.log('Dehestan changed:', dehestanId);

                if (districtId && cityVillageSelect) {
                    loadCitiesVillages(districtId, dehestanId, cityVillageSelect);
                    cityVillageSelect.disabled = false;
                }
            });
        }
    }

    /**
     * Load counties based on selected province
     */
    function loadCounties(provinceId, selectElement, callback, selectedValue) {
        console.log('Loading counties for province:', provinceId);
        const currentVal = selectedValue || selectElement.value || selectElement.dataset.selected;
        selectElement.innerHTML = '<option value="">در حال بارگذاری شهرستان‌ها...</option>';
        selectElement.disabled = false;
        
        fetch(`/api/geo/counties/?province_id=${provinceId}`)
            .then(response => {
                if (!response.ok) throw new Error('Network response was not ok');
                return response.json();
            })
            .then(data => {
                const counties = Array.isArray(data) ? data : (data.data || []);
                populateDropdown(selectElement, counties, 'شهرستان خود را انتخاب کنید', currentVal);
                selectElement.disabled = false;
                if (typeof callback === 'function') callback(counties);
            })
            .catch(error => {
                console.error('Error loading counties:', error);
                resetDropdown(selectElement, 'خطا در بارگذاری شهرستان‌ها');
            });
    }

    /**
     * Load districts based on selected county
     */
    function loadDistricts(countyId, selectElement, callback, selectedValue) {
        console.log('Loading districts for county:', countyId);
        const currentVal = selectedValue || selectElement.value || selectElement.dataset.selected;
        selectElement.innerHTML = '<option value="">در حال بارگذاری بخش‌ها...</option>';
        selectElement.disabled = false;
        
        fetch(`/api/geo/districts/?county_id=${countyId}`)
            .then(response => {
                if (!response.ok) throw new Error('Network response was not ok');
                return response.json();
            })
            .then(data => {
                const districts = Array.isArray(data) ? data : (data.data || []);
                populateDropdown(selectElement, districts, 'بخش خود را انتخاب کنید', currentVal);
                selectElement.disabled = false;
                if (currentVal) {
                    selectElement.value = currentVal;
                }
                if (typeof callback === 'function') callback(districts);
            })
            .catch(error => {
                console.error('Error loading districts:', error);
                resetDropdown(selectElement, 'خطا در بارگذاری بخش‌ها');
            });
    }

    /**
     * Load dehestans based on selected district
     */
    function loadDehestans(districtId, selectElement, selectedValue) {
        console.log('Loading dehestans for district:', districtId);
        const currentVal = selectedValue || selectElement.value || selectElement.dataset.selected;
        selectElement.innerHTML = '<option value="">در حال بارگذاری دهستان‌ها...</option>';
        
        fetch(`/api/geo/dehestans/?district_id=${districtId}`)
            .then(response => {
                if (!response.ok) throw new Error('Network response was not ok');
                return response.json();
            })
            .then(data => {
                const dehestans = Array.isArray(data) ? data : (data.data || []);
                populateDropdown(selectElement, dehestans, 'دهستان خود را انتخاب کنید (اختیاری)', currentVal);
            })
            .catch(error => {
                console.error('Error loading dehestans:', error);
                resetDropdown(selectElement, 'خطا در بارگذاری دهستان‌ها');
            });
    }

    /**
     * Load cities and villages based on district and optional dehestan
     */
    function loadCitiesVillages(districtId, dehestanId, selectElement, selectedValue) {
        console.log('Loading cities/villages for district:', districtId, 'dehestan:', dehestanId);
        const currentVal = selectedValue || selectElement.value || selectElement.dataset.selected;
        selectElement.innerHTML = '<option value="">در حال بارگذاری شهرها و روستاها...</option>';
        selectElement.disabled = false;
        
        let url = `/api/geo/cities-villages/?district_id=${districtId}`;
        if (dehestanId) {
            url += `&dehestan_id=${dehestanId}`;
        }

        fetch(url)
            .then(response => {
                if (!response.ok) throw new Error('Network response was not ok');
                return response.json();
            })
            .then(data => {
                const items = Array.isArray(data) ? data : (data.data || []);
                selectElement.innerHTML = '';

                const placeholderOption = document.createElement('option');
                placeholderOption.value = '';
                placeholderOption.textContent = items.length > 0 ? 'شهر یا روستای خود را انتخاب کنید' : 'موردی یافت نشد (از دکمه درخواست افزودن استفاده کنید)';
                selectElement.appendChild(placeholderOption);

                items.forEach(item => {
                    const option = document.createElement('option');
                    option.value = item.id;
                    const typeDisplay = item.type_display || (item.settlement_type === 'village' || item.type === 'village' ? 'روستا' : 'شهر');
                    option.textContent = `${item.name} (${typeDisplay})`;
                    if (currentVal && String(item.id) === String(currentVal)) {
                        option.selected = true;
                    }
                    selectElement.appendChild(option);
                });
                selectElement.disabled = false;
                if (currentVal) {
                    selectElement.value = currentVal;
                }
            })
            .catch(error => {
                console.error('Error loading cities/villages:', error);
                resetDropdown(selectElement, 'خطا در بارگذاری شهرها/روستاها');
            });
    }

    /**
     * Populate a dropdown with data
     */
    function populateDropdown(selectElement, data, placeholder, selectedValue) {
        selectElement.innerHTML = '';

        const placeholderOption = document.createElement('option');
        placeholderOption.value = '';
        placeholderOption.textContent = placeholder;
        selectElement.appendChild(placeholderOption);

        data.forEach(item => {
            const option = document.createElement('option');
            option.value = item.id;
            option.textContent = item.name;
            if (selectedValue && String(item.id) === String(selectedValue)) {
                option.selected = true;
            }
            selectElement.appendChild(option);
        });
    }

    /**
     * Reset a dropdown to its initial state
     */
    function resetDropdown(selectElement, placeholder) {
        selectElement.innerHTML = '';
        const option = document.createElement('option');
        option.value = '';
        option.textContent = placeholder || 'انتخاب کنید';
        selectElement.appendChild(option);
    }

    /**
     * Initialize on DOM ready
     */
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initGeographicSelectors);
    } else {
        initGeographicSelectors();
    }

})();
