if (typeof BroadcastChannel !== 'undefined') {
    const handleOAuthComplete = function (event) {
        if (event.data === 'oauth_complete') {
            window.location.reload();
        }
    };
    try {
        const bcPrimary = new BroadcastChannel('voxbento_oauth');
        bcPrimary.onmessage = handleOAuthComplete;
    } catch (e) {}
    try {
        const bcLegacy = new BroadcastChannel('oauth_channel');
        bcLegacy.onmessage = handleOAuthComplete;
    } catch (e) {}
}

window.addEventListener('message', function (event) {
    if (event.origin === window.location.origin && event.data === 'oauth_complete') {
        window.location.reload();
    }
});

function openVoxbentoPopup(url, width, height) {
    width = parseInt(width || '600', 10);
    height = parseInt(height || '700', 10);
    const left = Math.max(0, Math.round(window.screenX + (window.outerWidth - width) / 2));
    const top = Math.max(0, Math.round(window.screenY + (window.outerHeight - height) / 2));
    const popup = window.open(
        url,
        'voxbento_oauth',
        'width=' + width + ',height=' + height + ',left=' + left + ',top=' + top + ',resizable=yes,scrollbars=yes,status=no'
    );
    if (popup && popup.focus) {
        popup.focus();
    }
    return popup;
}

// Global capture-phase click handler (CSP-safe, captures clicks before default navigation)
document.addEventListener('click', function (e) {
    const link = e.target && e.target.closest ? e.target.closest('.js-voxbento-popup') : null;
    if (link) {
        e.preventDefault();
        e.stopPropagation();
        const popup = openVoxbentoPopup(
            link.href,
            link.getAttribute('data-popup-width'),
            link.getAttribute('data-popup-height')
        );
        if (!popup || popup.closed || typeof popup.closed === 'undefined') {
            window.location.href = link.href;
        }
        return false;
    }
}, true);

// jQuery delegation fallback
if (typeof $ !== 'undefined') {
    $(document).on('click', '.js-voxbento-popup', function (e) {
        e.preventDefault();
        e.stopPropagation();
        const popup = openVoxbentoPopup(
            this.href,
            this.getAttribute('data-popup-width'),
            this.getAttribute('data-popup-height')
        );
        if (!popup || popup.closed || typeof popup.closed === 'undefined') {
            window.location.href = this.href;
        }
        return false;
    });
}

document.addEventListener('DOMContentLoaded', function () {
    // Auto-dismiss success alerts after 5 seconds
    const successAlerts = document.querySelectorAll('.alert-success');
    successAlerts.forEach(function (alert) {
        setTimeout(function () {
            alert.style.transition = 'opacity 0.8s ease-out';
            alert.style.opacity = '0';
            setTimeout(function () {
                if (alert.parentNode) {
                    alert.parentNode.removeChild(alert);
                } else {
                    alert.style.display = 'none';
                }
            }, 800);
        }, 5000);
    });

    // Deep-linking to rooms tab and specific room panel
    if (window.location.hash === '#rooms' || window.location.search.indexOf('room=') !== -1) {
        if (typeof $ !== 'undefined' && $('.nav-tabs a[href="#rooms"]').length) {
            $('.nav-tabs a[href="#rooms"]').tab('show');
        }
    }
    const match = window.location.search.match(/room=(\d+)/);
    if (match && match[1] && typeof $ !== 'undefined') {
        const roomId = match[1];
        const $panel = $('#room-panel-' + roomId);
        if ($panel.length) {
            setTimeout(function () {
                $panel.collapse('show');
                if ($panel[0] && $panel[0].scrollIntoView) {
                    $panel[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }, 100);
        }
    }
});
