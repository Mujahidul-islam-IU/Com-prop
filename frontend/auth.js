// ============================================================
//  LBKN Automator — Authentication Pages JavaScript
//  Handles login, register, forgot-password, reset-password forms
// ============================================================

// ==================== UTILITIES ====================

function showMessage(msg, type = 'error') {
    const el = document.getElementById('auth-message');
    if (!el) return;
    el.textContent = msg;
    el.className = `auth-message ${type}`;
    el.classList.remove('hidden');

    // Auto-hide success messages after 5 seconds
    if (type === 'success') {
        setTimeout(() => el.classList.add('hidden'), 5000);
    }
}

function hideMessage() {
    const el = document.getElementById('auth-message');
    if (el) el.classList.add('hidden');
}

function setLoading(btn, loading) {
    if (!btn) return;
    const text = btn.querySelector('.btn-text');
    const loader = btn.querySelector('.btn-loader');
    if (loading) {
        btn.disabled = true;
        if (text) text.classList.add('hidden');
        if (loader) loader.classList.remove('hidden');
    } else {
        btn.disabled = false;
        if (text) text.classList.remove('hidden');
        if (loader) loader.classList.add('hidden');
    }
}

// ==================== PASSWORD TOGGLE ====================

const toggleBtn = document.getElementById('toggle-password');
if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
        const input = document.getElementById('password');
        const icon = document.getElementById('eye-icon');
        if (input.type === 'password') {
            input.type = 'text';
            icon.innerHTML = `
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"></path>
                <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"></path>
                <line x1="1" y1="1" x2="23" y2="23"></line>
            `;
        } else {
            input.type = 'password';
            icon.innerHTML = `
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                <circle cx="12" cy="12" r="3"></circle>
            `;
        }
    });
}

// ==================== LOGIN FORM ====================

const loginForm = document.getElementById('login-form');
if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        hideMessage();

        const btn = document.getElementById('login-btn');
        const email = document.getElementById('email').value.trim();
        const password = document.getElementById('password').value;

        if (!email || !password) {
            showMessage('Please enter both email and password.');
            return;
        }

        setLoading(btn, true);

        try {
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            const data = await res.json();

            if (res.ok && data.success) {
                showMessage('Login successful! Redirecting...', 'success');
                setTimeout(() => window.location.href = '/', 500);
            } else {
                showMessage(data.message || 'Login failed. Please check your credentials.');
            }
        } catch (err) {
            showMessage('Connection error. Please try again.');
        }

        setLoading(btn, false);
    });
}

// ==================== REGISTER FORM ====================

const registerForm = document.getElementById('register-form');
if (registerForm) {
    registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        hideMessage();

        const btn = document.getElementById('register-btn');
        const email = document.getElementById('email').value.trim();
        const password = document.getElementById('password').value;
        const confirmPassword = document.getElementById('confirm-password').value;

        if (!email || !password || !confirmPassword) {
            showMessage('Please fill in all fields.');
            return;
        }

        if (password !== confirmPassword) {
            showMessage('Passwords do not match.');
            return;
        }

        if (password.length < 6) {
            showMessage('Password must be at least 6 characters.');
            return;
        }

        setLoading(btn, true);

        try {
            const res = await fetch('/api/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            const data = await res.json();

            if (res.ok && data.success) {
                showMessage('Account created! Redirecting to login...', 'success');
                setTimeout(() => window.location.href = '/login', 1500);
            } else {
                showMessage(data.message || 'Registration failed.');
            }
        } catch (err) {
            showMessage('Connection error. Please try again.');
        }

        setLoading(btn, false);
    });
}

// ==================== FORGOT PASSWORD FORM ====================

const forgotForm = document.getElementById('forgot-form');
if (forgotForm) {
    forgotForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        hideMessage();

        const btn = document.getElementById('forgot-btn');
        const email = document.getElementById('email').value.trim();

        if (!email) {
            showMessage('Please enter your email address.');
            return;
        }

        setLoading(btn, true);

        try {
            const res = await fetch('/api/auth/forgot-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            });
            const data = await res.json();

            if (res.ok && data.success) {
                showMessage(data.message || 'If an account with that email exists, a reset link has been sent.', 'success');
                // Disable form to prevent re-submission
                document.getElementById('email').disabled = true;
                btn.disabled = true;
            } else {
                showMessage(data.message || 'Something went wrong.');
            }
        } catch (err) {
            showMessage('Connection error. Please try again.');
        }

        setLoading(btn, false);
    });
}

// ==================== RESET PASSWORD FORM ====================

const resetForm = document.getElementById('reset-form');
if (resetForm) {
    // Extract token from URL
    const urlParams = new URLSearchParams(window.location.search);
    const resetToken = urlParams.get('token');

    if (!resetToken) {
        showMessage('Invalid reset link. No token provided.');
        resetForm.querySelector('button[type="submit"]').disabled = true;
    }

    resetForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        hideMessage();

        const btn = document.getElementById('reset-btn');
        const password = document.getElementById('password').value;
        const confirmPassword = document.getElementById('confirm-password').value;

        if (!password || !confirmPassword) {
            showMessage('Please fill in both password fields.');
            return;
        }

        if (password !== confirmPassword) {
            showMessage('Passwords do not match.');
            return;
        }

        if (password.length < 6) {
            showMessage('Password must be at least 6 characters.');
            return;
        }

        setLoading(btn, true);

        try {
            const res = await fetch('/api/auth/reset-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: resetToken, password })
            });
            const data = await res.json();

            if (res.ok && data.success) {
                showMessage('Password reset successfully! Redirecting to login...', 'success');
                setTimeout(() => window.location.href = '/login', 2000);
            } else {
                showMessage(data.message || 'Reset failed. The link may have expired.');
            }
        } catch (err) {
            showMessage('Connection error. Please try again.');
        }

        setLoading(btn, false);
    });
}
