/**
 * Geographic Cascade Dropdowns - Reusable Module
 * Handles cascading dropdowns for Province -> County -> District -> Dehestan -> City/Village
 */

class GeographicCascade {
    constructor(config) {
        this.provinceSelect = document.getElementById(config.provinceId || 'id_province');
        this.countySelect = document.getElementById(config.countyId || 'id_county');
        this.districtSelect = document.getElementById(config.districtId || 'id_district');
        this.dehestanSelect = document.getElementById(config.dehestanId || 'id_dehestan');
        this.cityVillageSelect = document.getElementById(config.cityVillageId || 'id_city_village');
        this.isVillageCheckbox = document.getElementById(config.isVillageId || 'id_is_village');
        
        this.loadProvincesOnInit = config.loadProvincesOnInit !== false; // default true
        this.init();
    }
    
    init() {
        // Load provinces on initialization if configured
        if (this.loadProvincesOnInit && this.provinceSelect) {
            this.loadProvinces();
        }
        
        // Setup event listeners
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        // Province change handler
        if (this.provinceSelect) {
            this.provinceSelect.addEventListener('change', () => {
                const provinceId = this.provinceSelect.value;
                console.log('Province changed:', provinceId);
                
                this.clearSelect(this.countySelect, 'شهرستان را انتخاب کنید');
                this.clearSelect(this.districtSelect, 'بخش را انتخاب کنید');
                this.clearSelect(this.dehestanSelect, 'دهستان را انتخاب کنید');
                this.clearSelect(this.cityVillageSelect, 'انتخاب کنید');
                
                if (provinceId) {
                    this.enableSelect(this.countySelect);
                    this.loadCounties(provinceId);
                } else {
                    this.disableSelect(this.countySelect);
                    this.disableSelect(this.districtSelect);
                    this.disableSelect(this.dehestanSelect);
                    this.disableSelect(this.cityVillageSelect);
                }
            });
        }
        
        // County change handler
        if (this.countySelect) {
            this.countySelect.addEventListener('change', () => {
                const countyId = this.countySelect.value;
                console.log('County changed:', countyId);
                
                this.clearSelect(this.districtSelect, 'بخش را انتخاب کنید');
                this.clearSelect(this.dehestanSelect, 'دهستان را انتخاب کنید');
                this.clearSelect(this.cityVillageSelect, 'انتخاب کنید');
                
                if (countyId) {
                    this.enableSelect(this.districtSelect);
                    this.loadDistricts(countyId);
                } else {
                    this.disableSelect(this.districtSelect);
                    this.disableSelect(this.dehestanSelect);
                    this.disableSelect(this.cityVillageSelect);
                }
            });
        }
        
        // District change handler
        if (this.districtSelect) {
            this.districtSelect.addEventListener('change', () => {
                const districtId = this.districtSelect.value;
                console.log('District changed:', districtId);
                
                this.clearSelect(this.dehestanSelect, 'دهستان را انتخاب کنید');
                this.clearSelect(this.cityVillageSelect, 'انتخاب کنید');
                
                if (districtId) {
                    if (this.isVillageCheckbox && this.isVillageCheckbox.checked) {
                        this.enableSelect(this.dehestanSelect);
                        this.loadDehestans(districtId);
                        this.disableSelect(this.cityVillageSelect);
                    } else {
                        this.enableSelect(this.cityVillageSelect);
                        this.loadCitiesVillages(districtId, null);
                    }
                } else {
                    this.disableSelect(this.dehestanSelect);
                    this.disableSelect(this.cityVillageSelect);
                }
            });
        }
        
        // Dehestan change handler
        if (this.dehestanSelect) {
            this.dehestanSelect.addEventListener('change', () => {
                const dehestanId = this.dehestanSelect.value;
                const districtId = this.districtSelect ? this.districtSelect.value : null;
                console.log('Dehestan changed:', dehestanId);
                
                this.clearSelect(this.cityVillageSelect, 'انتخاب کنید');
                
                if (dehestanId && districtId) {
                    this.enableSelect(this.cityVillageSelect);
                    this.loadCitiesVillages(districtId, dehestanId);
                } else {
                    this.disableSelect(this.cityVillageSelect);
                }
            });
        }
        
        // Village checkbox handler
        if (this.isVillageCheckbox) {
            this.isVillageCheckbox.addEventListener('change', () => {
                const districtId = this.districtSelect ? this.districtSelect.value : null;
                
                if (this.isVillageCheckbox.checked && districtId) {
                    this.enableSelect(this.dehestanSelect);
                    this.loadDehestans(districtId);
                    this.disableSelect(this.cityVillageSelect);
                    this.clearSelect(this.cityVillageSelect, 'انتخاب کنید');
                } else if (districtId) {
                    this.disableSelect(this.dehestanSelect);
                    this.clearSelect(this.dehestanSelect, 'دهستان را انتخاب کنید');
                    this.enableSelect(this.cityVillageSelect);
                    this.loadCitiesVillages(districtId, null);
                }
            });
        }
    }
    
    // Helper methods
    clearSelect(selectElement, placeholderText) {
        if (selectElement) {
            selectElement.innerHTML = `<option value="">${placeholderText}</option>`;
        }
    }
    
    enableSelect(selectElement) {
        if (selectElement) {
            selectElement.disabled = false;
        }
    }
    
    disableSelect(selectElement) {
        if (selectElement) {
            selectElement.disabled = true;
        }
    }
    
    // API methods
    loadProvinces() {
        console.log('Loading provinces...');
        fetch('/api/provinces/')
            .then(response => response.json())
            .then(data => {
                console.log('Provinces loaded:', data);
                if (this.provinceSelect) {
                    this.provinceSelect.innerHTML = '<option value="">استان را انتخاب کنید</option>';
                    const provinces = Array.isArray(data) ? data : (data.data || []);
                    provinces.forEach(province => {
                        const option = document.createElement('option');
                        option.value = province.id;
                        option.textContent = province.name;
                        this.provinceSelect.appendChild(option);
                    });
                }
            })
            .catch(error => {
                console.error('Error loading provinces:', error);
                alert('خطا در بارگذاری استان‌ها');
            });
    }
    
    loadCounties(provinceId) {
        console.log('Loading counties for province:', provinceId);
        fetch(`/api/geo/counties/?province_id=${provinceId}`)
            .then(response => response.json())
            .then(data => {
                console.log('Counties loaded:', data);
                if (this.countySelect) {
                    this.countySelect.innerHTML = '<option value="">شهرستان را انتخاب کنید</option>';
                    const counties = Array.isArray(data) ? data : (data.data || []);
                    counties.forEach(county => {
                        const option = document.createElement('option');
                        option.value = county.id;
                        option.textContent = county.name;
                        this.countySelect.appendChild(option);
                    });
                }
            })
            .catch(error => {
                console.error('Error loading counties:', error);
                alert('خطا در بارگذاری شهرستان‌ها');
            });
    }
    
    loadDistricts(countyId) {
        console.log('Loading districts for county:', countyId);
        fetch(`/api/geo/districts/?county_id=${countyId}`)
            .then(response => response.json())
            .then(data => {
                console.log('Districts loaded:', data);
                if (this.districtSelect) {
                    this.districtSelect.innerHTML = '<option value="">بخش را انتخاب کنید</option>';
                    const districts = Array.isArray(data) ? data : (data.data || []);
                    districts.forEach(district => {
                        const option = document.createElement('option');
                        option.value = district.id;
                        option.textContent = district.name;
                        this.districtSelect.appendChild(option);
                    });
                }
            })
            .catch(error => {
                console.error('Error loading districts:', error);
                alert('خطا در بارگذاری بخش‌ها');
            });
    }
    
    loadDehestans(districtId) {
        console.log('Loading dehestans for district:', districtId);
        fetch(`/api/geo/dehestans/?district_id=${districtId}`)
            .then(response => response.json())
            .then(data => {
                console.log('Dehestans loaded:', data);
                if (this.dehestanSelect) {
                    this.dehestanSelect.innerHTML = '<option value="">دهستان را انتخاب کنید</option>';
                    const dehestans = Array.isArray(data) ? data : (data.data || []);
                    dehestans.forEach(dehestan => {
                        const option = document.createElement('option');
                        option.value = dehestan.id;
                        option.textContent = dehestan.name;
                        this.dehestanSelect.appendChild(option);
                    });
                }
            })
            .catch(error => {
                console.error('Error loading dehestans:', error);
                alert('خطا در بارگذاری دهستان‌ها');
            });
    }
    
    loadCitiesVillages(districtId, dehestanId) {
        console.log('Loading cities/villages for district:', districtId, 'dehestan:', dehestanId);
        let url = `/api/geo/cities-villages/?district_id=${districtId}`;
        if (dehestanId) {
            url += `&dehestan_id=${dehestanId}`;
        }
        
        fetch(url)
            .then(response => response.json())
            .then(data => {
                console.log('Cities/villages loaded:', data);
                if (this.cityVillageSelect) {
                    this.cityVillageSelect.innerHTML = '<option value="">انتخاب کنید</option>';
                    const citiesVillages = Array.isArray(data) ? data : (data.data || []);
                    citiesVillages.forEach(cv => {
                        const option = document.createElement('option');
                        option.value = cv.id;
                        option.textContent = cv.name + ' (' + cv.type_display + ')';
                        this.cityVillageSelect.appendChild(option);
                    });
                }
            })
            .catch(error => {
                console.error('Error loading cities/villages:', error);
                alert('خطا در بارگذاری شهرها/روستاها');
            });
    }
}
