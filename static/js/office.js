/* Office pages: one click = one request (double submits are the usual source of duplicate letters/bookings). */
document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form.matches('[data-once]')) return;
    if (form.dataset.sent === '1') { event.preventDefault(); return; }
    var confirmText = form.getAttribute('data-confirm');
    if (confirmText && !window.confirm(confirmText)) { event.preventDefault(); return; }
    form.dataset.sent = '1';
    form.querySelectorAll('button[type="submit"]').forEach(function (button) {
        button.disabled = true;
        button.insertAdjacentHTML('afterbegin', '<span class="spinner-border spinner-border-sm ms-1" role="status" aria-hidden="true"></span>');
    });
});
// Back/forward cache restores a page with its buttons still disabled.
window.addEventListener('pageshow', function () {
    document.querySelectorAll('form[data-once]').forEach(function (form) {
        form.dataset.sent = '0';
        form.querySelectorAll('button[type="submit"]').forEach(function (b) {
            b.disabled = false;
            var spinner = b.querySelector('.spinner-border');
            if (spinner) spinner.remove();
        });
    });
});
