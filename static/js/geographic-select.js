/**
 * Cascading Geographic Dropdowns
 * Handles Province -> County -> District -> CityVillage selection
 */

document.addEventListener('DOMContentLoaded', function() {
    const provinceSelect = document.getElementById('id_province');
    const countySelect = document.getElementById('id_county');
    const districtSelect = document.getElementById('id_district');
    const cityVillageSelect = document.getElementById('id_city_village');
    
    if (!provinceSelect) return; // Exit if not on a form with geographic selects
    
    // Reset and disable dependent dropdowns
    function resetDropdown(selectElement, placeholder = 'انتخاب کنید...') {
        selectElement.innerHTML = `<option value="">-- ${placeholder} --</option>`;
        selectElement.disabled = true;
    }
    
    // Populate dropdown with data
    function populateDropdown(selectElement, data, placeholder = 'انتخاب کنید...') {
        selectElement.innerHTML = `<option value="">-- ${placeholder} --</option>`;
        data.forEach(item => {
            const option = document.createElement('option');
            option.value = item.id;
            option.textContent = item.name;
            if (item.settlement_type) {
                const type = item.settlement_type === 'city' ? 'شهر' : 'روستا';
                option.textContent = `${item.name} (${type})`;
            }
            selectElement.appendChild(option);
        });
        selectElement.disabled = false;
    }
    
    // Load counties based on province
    provinceSelect.addEventListener('change', function() {
        const provinceId = this.value;
        
        // Reset dependent dropdowns
        resetDropdown(countySelect, 'ابتدا استان را انتخاب کنید');
        resetDropdown(districtSelect, 'ابتدا شهرستان را انتخاب کنید');
        resetDropdown(cityVillageSelect, 'ابتدا بخش را انتخاب کنید');
        
        if (!provinceId) return;
        
        // Fetch counties
        fetch(`/api/counties/${provinceId}/`)
            .then(response => response.json())
            .then(data => {
                populateDropdown(countySelect, data, 'شهرستان را انتخاب کنید');
            })
            .catch(error => {
                console.error('Error loading counties:', error);
                alert('خطا در بارگذاری شهرستان‌ها');
            });
    });
    
    // Load districts based on county
    countySelect.addEventListener('change', function() {
        const countyId = this.value;
        
        // Reset dependent dropdowns
        resetDropdown(districtSelect, 'ابتدا شهرستان را انتخاب کنید');
        resetDropdown(cityVillageSelect, 'ابتدا بخش را انتخاب کنید');
        
        if (!countyId) return;
        
        // Fetch districts
        fetch(`/api/districts/${countyId}/`)
            .then(response => response.json())
            .then(data => {
                populateDropdown(districtSelect, data, 'بخش را انتخاب کنید');
            })
            .catch(error => {
                console.error('Error loading districts:', error);
                alert('خطا در بارگذاری بخش‌ها');
            });
    });
    
    // Load city/villages based on district
    districtSelect.addEventListener('change', function() {
        const districtId = this.value;
        
        // Reset dependent dropdown
        resetDropdown(cityVillageSelect, 'ابتدا بخش را انتخاب کنید');
        
        if (!districtId) return;
        
        // Fetch city/villages
        fetch(`/api/city-villages/${districtId}/`)
            .then(response => response.json())
            .then(data => {
                populateDropdown(cityVillageSelect, data, 'شهر/روستا را انتخاب کنید');
            })
            .catch(error => {
                console.error('Error loading city/villages:', error);
                alert('خطا در بارگذاری شهرها/روستاها');
            });
    });
});
