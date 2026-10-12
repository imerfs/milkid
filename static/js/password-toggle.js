// Adds a show/hide eye button to every <input type="password" data-pw-toggle>.
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('input[type="password"][data-pw-toggle]').forEach(function (input) {
        const wrap = document.createElement('div');
        wrap.style.position = 'relative';
        input.parentNode.insertBefore(wrap, input);
        wrap.appendChild(input);
        input.style.paddingLeft = '2.75rem';

        const button = document.createElement('button');
        button.type = 'button';
        button.setAttribute('aria-label', 'نمایش رمز عبور');
        button.setAttribute('aria-pressed', 'false');
        button.innerHTML = '<i class="fas fa-eye" aria-hidden="true"></i>';
        button.style.cssText = 'position:absolute;left:.5rem;top:50%;transform:translateY(-50%);' +
            'background:none;border:0;padding:.5rem;cursor:pointer;color:#6b7280;line-height:1;';
        wrap.appendChild(button);

        button.addEventListener('click', function () {
            const show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            button.setAttribute('aria-pressed', show ? 'true' : 'false');
            button.setAttribute('aria-label', show ? 'پنهان کردن رمز عبور' : 'نمایش رمز عبور');
            button.firstChild.className = show ? 'fas fa-eye-slash' : 'fas fa-eye';
        });
    });
});
