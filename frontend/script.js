// ============================================================
//  LBKN Automator - Frontend Logic
//  Phase 1+2: Property Scraping & Enquiry
//  Phase 3: Email Reply Monitor
// ============================================================

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

    // Gather data
    const payload = {
        location: form.location.value,
        keyword: form.keyword.value,
        min_size: form.min_size.value ? parseInt(form.min_size.value) : 0,
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
