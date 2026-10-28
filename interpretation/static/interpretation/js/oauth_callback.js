document.addEventListener("DOMContentLoaded", function () {
    const bodyEl = document.getElementById("oauth-callback-body") || document.getElementById("oauth-error-body");
    const redirectUrl = bodyEl ? bodyEl.getAttribute("data-redirect-url") : "";
    const isSuccess = bodyEl && bodyEl.id === "oauth-callback-body" && bodyEl.getAttribute("data-success") === "true";

    // 1. Notify listeners and reload dashboard ONLY on successful authentication
    if (isSuccess) {
        try {
            if (typeof BroadcastChannel !== "undefined") {
                try {
                    const bcPrimary = new BroadcastChannel("voxbento_oauth");
                    bcPrimary.postMessage("oauth_complete");
                } catch (e) {}
                try {
                    const bcLegacy = new BroadcastChannel("oauth_channel");
                    bcLegacy.postMessage("oauth_complete");
                } catch (e) {}
            }
        } catch (e) {
            console.error("BroadcastChannel error:", e);
        }

        try {
            if (window.opener && !window.opener.closed) {
                window.opener.postMessage("oauth_complete", window.location.origin);
                try {
                    window.opener.location.reload();
                } catch (e) {
                    // Cross-origin opener error ignore
                }
            }
        } catch (e) {
            console.error("Opener notification error:", e);
        }
    }

    // 2. Attach click handler to Close Window button
    const closeBtn = document.getElementById("btn-close-window");
    if (closeBtn) {
        closeBtn.addEventListener("click", function () {
            window.close();
            setTimeout(function () {
                if (!window.closed && redirectUrl) {
                    window.location.href = redirectUrl;
                }
            }, 300);
        });
    }

    // 3. Auto-close only on successful connection in a popup
    if (isSuccess) {
        setTimeout(function () {
            try {
                window.close();
            } catch (e) {}

            // Fallback for full tabs where window.close is forbidden: navigate to redirectUrl
            setTimeout(function () {
                if (!window.closed && redirectUrl) {
                    window.location.href = redirectUrl;
                }
            }, 800);
        }, 600);
    }
});
