// ============================================================
//  LBKN Automator - Frontend Logic
//  Phase 1+2: Property Scraping & Enquiry
//  Phase 3: Email Reply Monitor
// ============================================================

// ==================== LOGOUT HANDLER ====================

document.getElementById('logout-btn')?.addEventListener('click', async () => {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) { /* ignore */ }
    window.location.href = '/login';
});

// ==================== ADMIN PANEL LOGIC ====================

async function loadAdminUsers() {
    try {
        const resp = await fetch('/api/admin/users');
        if (!resp.ok) return;
        const data = await resp.json();
        const tbody = document.getElementById('admin-users-body');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        data.users.forEach(u => {
            const tr = document.createElement('tr');
            
            const statusBadge = u.is_approved 
                ? '<span class="badge completed">Approved</span>' 
                : '<span class="badge warning" style="background: rgba(245,158,11,0.2); color: #FBBF24;">Pending</span>';
                
            const actions = u.email === 'admin@lbkncapital.com' 
                ? '<em>Admin</em>' 
                : `
                    ${!u.is_approved ? `<button onclick="approveUser('${u.id}')" style="padding: 0.3rem 0.6rem; font-size: 0.75rem; width: auto; margin-right: 0.5rem; background: #10B981;">Approve</button>` : ''}
                    <button onclick="deleteUser('${u.id}')" style="padding: 0.3rem 0.6rem; font-size: 0.75rem; width: auto; background: #EF4444;">Delete</button>
                `;

            tr.innerHTML = `
                <td>${u.email}</td>
                <td>${statusBadge}</td>
                <td>${new Date(u.created_at).toLocaleDateString()}</td>
                <td>${actions}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Failed to load admin users", e);
    }
}

window.approveUser = async function(id) {
    if (!confirm("Approve this user?")) return;
    try {
        await fetch(`/api/admin/users/${id}/approve`, { method: 'POST' });
        loadAdminUsers();
    } catch (e) { console.error(e); }
};

window.deleteUser = async function(id) {
    if (!confirm("Permanently delete this user?")) return;
    try {
        await fetch(`/api/admin/users/${id}`, { method: 'DELETE' });
        loadAdminUsers();
    } catch (e) { console.error(e); }
};

// ==================== PHASE 1+2: SCRAPER ====================

document.getElementById('scrape-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const form = e.target;
    const btn = document.getElementById('start-btn');
    const statusPanel = document.getElementById('status-panel');
    const resultsPanel = document.getElementById('results-panel');
    const badge = document.getElementById('status-badge');
    const statusText = document.getElementById('status-text');
    const progressBar = document.getElementById('progress-bar');

    // Reset UI
    resultsPanel.classList.add('hidden');
    statusPanel.classList.remove('hidden');
    btn.disabled = true;
    btn.innerText = 'Sourcing...';

    badge.className = 'badge running';
    badge.innerText = 'Running';
    statusText.innerText = 'Browser automation has started in the background. Please do not close the browser window that opens...';
    progressBar.className = 'progress-bar animate';
    progressBar.style.width = '100%';
    
    const pd = document.getElementById('progress-details');
    if (pd) pd.classList.add('hidden');

    // Gather data
    const payload = {
        location: form.location.value,
        keyword: form.keyword.value,
        min_size: form.min_size.value ? parseInt(form.min_size.value) : 0,
        max_size: form.max_size.value ? parseInt(form.max_size.value) : 0,
        listing_type: form.listing_type.value,
        max_pages: parseInt(form.max_pages.value) || 1
    };

    try {
        // Start job
        const res = await fetch('/api/scrape', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (data.job_id) {
            pollStatus(data.job_id);
        } else {
            throw new Error("Failed to start job");
        }
    } catch (err) {
        showError(err.message);
    }
});

async function pollStatus(jobId) {
    const interval = setInterval(async () => {
        try {
            const res = await fetch(`/api/status/${jobId}`);
            const data = await res.json();

            if (data.status === 'completed') {
                clearInterval(interval);
                showSuccess(data.results);
            } else if (data.status === 'failed') {
                clearInterval(interval);
                showError(data.error);
            } else if (data.status === 'running' && data.progress) {
                const pd = document.getElementById('progress-details');
                if (pd) pd.classList.remove('hidden');
                
                const pCount = document.getElementById('progress-count');
                const pTitle = document.getElementById('progress-title');
                const pTime = document.getElementById('progress-time');
                const pBar = document.getElementById('progress-bar');
                
                if (pCount) pCount.innerText = `Processing Property [${data.progress.current} / ${data.progress.total}]`;
                if (pTitle) pTitle.innerText = `Current: ${data.progress.title || 'N/A'}`;
                if (pTime) pTime.innerText = `Estimated time remaining: ~${data.progress.est_time_mins} mins`;
                
                if (pBar && data.progress.total > 0) {
                    pBar.classList.remove('animate');
                    const pct = Math.round((data.progress.current / data.progress.total) * 100);
                    pBar.style.width = `${pct}%`;
                }
            }
        } catch (err) {
            console.error("Poll error", err);
        }
    }, 2000);
}

function showSuccess(results) {
    const btn = document.getElementById('start-btn');
    const badge = document.getElementById('status-badge');
    const statusText = document.getElementById('status-text');
    const progressBar = document.getElementById('progress-bar');
    const resultsPanel = document.getElementById('results-panel');
    const tbody = document.getElementById('results-body');

    btn.disabled = false;
    btn.innerText = 'Start Sourcing';

    badge.className = 'badge completed';
    badge.innerText = 'Completed';
    statusText.innerText = `Successfully scraped ${results ? results.length : 0} properties!`;
    progressBar.className = 'progress-bar';
    progressBar.style.width = '100%';

    if (results && results.length > 0) {
        tbody.innerHTML = '';
        results.forEach(item => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${item.title || 'N/A'}</td>
                <td>${item.address || 'N/A'}</td>
                <td>${item.price || 'N/A'}</td>
                <td>${item.size || 'N/A'}</td>
                <td><a href="${item.link}" target="_blank">View</a></td>
            `;
            tbody.appendChild(tr);
        });
        resultsPanel.classList.remove('hidden');
    }
}

function showError(errorMsg) {
    const btn = document.getElementById('start-btn');
    const badge = document.getElementById('status-badge');
    const statusText = document.getElementById('status-text');
    const progressBar = document.getElementById('progress-bar');

    btn.disabled = false;
    btn.innerText = 'Start Sourcing';

    badge.className = 'badge failed';
    badge.innerText = 'Failed';
    statusText.innerText = `Error: ${errorMsg}`;
    progressBar.className = 'progress-bar';
    progressBar.style.width = '100%';
    progressBar.style.background = '#EF4444';
}

// ==================== ENQUIRY SETTINGS ====================

async function loadEnquirySettings() {
    try {
        const res = await fetch('/api/settings/enquiry');
        if (res.ok) {
            const data = await res.json();
            document.getElementById('enquiry_name').value = data.name || '';
            document.getElementById('enquiry_email').value = data.email || '';
            document.getElementById('enquiry_phone').value = data.phone || '';
            document.getElementById('enquiry_template').value = data.template || '';
        }
    } catch (e) {
        console.error("Failed to load enquiry settings", e);
    }
}

document.getElementById('enquiry-settings-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('save-enquiry-settings-btn');
    const statusText = document.getElementById('enquiry-settings-status');
    btn.disabled = true;
    btn.innerText = 'Saving...';
    statusText.innerText = '';

    const payload = {
        name: document.getElementById('enquiry_name').value,
        email: document.getElementById('enquiry_email').value,
        phone: document.getElementById('enquiry_phone').value,
        template: document.getElementById('enquiry_template').value
    };

    try {
        const res = await fetch('/api/settings/enquiry', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            statusText.style.color = '#10B981';
            statusText.innerText = 'Settings saved successfully!';
            setTimeout(() => statusText.innerText = '', 3000);
        } else {
            statusText.style.color = '#EF4444';
            statusText.innerText = 'Failed to save settings.';
        }
    } catch (err) {
        statusText.style.color = '#EF4444';
        statusText.innerText = 'Error saving settings.';
    } finally {
        btn.disabled = false;
        btn.innerText = 'Save Settings';
    }
});

// Load settings on startup if authenticated
document.addEventListener('DOMContentLoaded', () => {
    fetch('/api/auth/me').then(r => r.json()).then(data => {
        if (data.authenticated) {
            loadEnquirySettings();
        }
    }).catch(() => {});
});

// ==================== PHASE 3: REPLY MONITOR ====================

// Preview unread emails (no Claude needed)
document.getElementById('preview-inbox-btn').addEventListener('click', async () => {
    const btn = document.getElementById('preview-inbox-btn');
    const replyBadge = document.getElementById('reply-badge');
    const previewPanel = document.getElementById('email-preview-panel');
    const previewBody = document.getElementById('email-preview-body');
    const replyStatusPanel = document.getElementById('reply-status-panel');
    const replyStatusText = document.getElementById('reply-status-text');

    btn.disabled = true;
    btn.innerText = 'Loading...';
    replyBadge.className = 'badge running';
    replyBadge.innerText = 'Scanning';
    replyStatusPanel.classList.remove('hidden');
    replyStatusText.innerText = 'Connecting to Outlook inbox...';

    try {
        const res = await fetch('/api/recent-emails');
        const data = await res.json();

        if (data.status === 'ok') {
            replyBadge.className = 'badge completed';
            replyBadge.innerText = `${data.count} Unread`;
            replyStatusText.innerText = `Found ${data.count} unread email(s) in inbox.`;

            previewBody.innerHTML = '';
            if (data.emails && data.emails.length > 0) {
                data.emails.forEach(email => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${email.from || 'N/A'}</td>
                        <td>${email.subject || 'N/A'}</td>
                        <td>${email.date || 'N/A'}</td>
                        <td class="preview-cell">${email.preview || ''}</td>
                    `;
                    previewBody.appendChild(tr);
                });
                previewPanel.classList.remove('hidden');
            } else {
                replyStatusText.innerText = 'No unread emails found.';
                previewPanel.classList.add('hidden');
            }
        } else {
            replyBadge.className = 'badge failed';
            replyBadge.innerText = 'Error';
            replyStatusText.innerText = `Error: ${data.message || 'Failed to fetch emails'}`;
        }
    } catch (err) {
        replyBadge.className = 'badge failed';
        replyBadge.innerText = 'Error';
        replyStatusText.innerText = `Connection error: ${err.message}`;
    }

    btn.disabled = false;
    btn.innerText = 'Preview Unread Emails';
});

// Check replies with Claude extraction (requires Anthropic credits)
document.getElementById('check-inbox-btn').addEventListener('click', async () => {
    const btn = document.getElementById('check-inbox-btn');
    const replyBadge = document.getElementById('reply-badge');
    const replyStatusPanel = document.getElementById('reply-status-panel');
    const replyStatusText = document.getElementById('reply-status-text');
    const replyProgressBar = document.getElementById('reply-progress-bar');

    btn.disabled = true;
    btn.innerText = 'Processing Replies...';
    replyBadge.className = 'badge running';
    replyBadge.innerText = 'Processing';
    replyStatusPanel.classList.remove('hidden');
    replyProgressBar.className = 'progress-bar animate';
    replyStatusText.innerText = 'Scanning inbox, extracting data with Claude AI, and updating Google Sheets...';

    try {
        const res = await fetch('/api/check-replies', { method: 'POST' });
        const data = await res.json();

        replyProgressBar.className = 'progress-bar';
        replyProgressBar.style.width = '100%';

        if (data.status === 'success') {
            replyBadge.className = 'badge completed';
            replyBadge.innerText = 'Done';
            replyStatusText.innerText = `Successfully processed ${data.processed} agent reply email(s). Google Sheet updated.`;
        } else {
            replyBadge.className = 'badge failed';
            replyBadge.innerText = 'Error';
            replyStatusText.innerText = `Error: ${data.message || 'Processing failed'}`;
        }
    } catch (err) {
        replyProgressBar.className = 'progress-bar';
        replyBadge.className = 'badge failed';
        replyBadge.innerText = 'Error';
        replyStatusText.innerText = `Connection error: ${err.message}`;
    }

    btn.disabled = false;
    btn.innerText = 'Check Inbox for Replies';
});
