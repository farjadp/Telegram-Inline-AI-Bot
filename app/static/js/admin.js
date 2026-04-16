// ============================================================================
// Source: admin.js
// Version: 1.0.0 — 2026-04-16
// Why: Admin panel interactivity — charts, AJAX API testing, sidebar, UI controls
// Env / Identity: Vanilla JavaScript — FastAPI Admin Panel
// ============================================================================

"use strict";

// ---------------------------------------------------------------------------
// Shared Chart.js default configuration
// Overrides global defaults to match our dark theme
// ---------------------------------------------------------------------------
function configureChartDefaults() {
    if (typeof Chart === "undefined") return;

    // Global font
    Chart.defaults.font.family = "'Inter', -apple-system, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = "#8888aa"; // text-secondary

    // Remove default animations for snappier feel
    Chart.defaults.animation.duration = 400;

    // Grid lines
    Chart.defaults.scale.grid = {
        color: "#252540",       // --border
        borderColor: "#252540",
    };
}

// ---------------------------------------------------------------------------
// Dashboard Charts
// Called from dashboard.html once DASHBOARD_DATA is available
// ---------------------------------------------------------------------------
function initDashboardCharts(data) {
    if (typeof Chart === "undefined") {
        console.warn("[admin.js] Chart.js not loaded — dashboard charts skipped");
        return;
    }

    // Extract daily data for x-axis labels and datasets
    const labels = data.daily.map((d) => d.date);
    const textCounts = data.daily.map((d) => d.text_count);
    const imageCounts = data.daily.map((d) => d.image_count);

    // --- Daily Requests Line Chart ---
    const dailyCtx = document.getElementById("chart-daily");
    if (dailyCtx) {
        new Chart(dailyCtx, {
            type: "line",
            data: {
                labels,
                datasets: [
                    {
                        label: "Text",
                        data: textCounts,
                        borderColor: "#3b82f6",
                        backgroundColor: "rgba(59,130,246,0.08)",
                        borderWidth: 2,
                        tension: 0.4,
                        fill: true,
                        pointBackgroundColor: "#3b82f6",
                        pointRadius: 3,
                    },
                    {
                        label: "Image",
                        data: imageCounts,
                        borderColor: "#8b5cf6",
                        backgroundColor: "rgba(139,92,246,0.08)",
                        borderWidth: 2,
                        tension: 0.4,
                        fill: true,
                        pointBackgroundColor: "#8b5cf6",
                        pointRadius: 3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "top", labels: { usePointStyle: true, padding: 16 } },
                    tooltip: { mode: "index", intersect: false },
                },
                scales: {
                    x: { ticks: { maxTicksLimit: 10 } },
                    y: { beginAtZero: true, ticks: { stepSize: 1 } },
                },
            },
        });
    }

    // --- Text vs Image Doughnut Chart ---
    const typeCtx = document.getElementById("chart-types");
    if (typeCtx) {
        new Chart(typeCtx, {
            type: "doughnut",
            data: {
                labels: ["Text", "Image"],
                datasets: [
                    {
                        data: [data.text_requests, data.image_requests],
                        backgroundColor: ["#3b82f6", "#8b5cf6"],
                        borderColor: "#13131f",
                        borderWidth: 3,
                        hoverOffset: 6,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }, // Custom legend in HTML
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                                const pct = total ? Math.round((ctx.parsed / total) * 100) : 0;
                                return ` ${ctx.label}: ${ctx.parsed} (${pct}%)`;
                            },
                        },
                    },
                },
                cutout: "70%",
            },
        });
    }

    // --- Top Users Bar Chart ---
    const usersCtx = document.getElementById("chart-top-users");
    if (usersCtx && data.top_users && data.top_users.length > 0) {
        const userLabels = data.top_users.map((u) => u.username || `user_${u.telegram_id}`);
        const userCounts = data.top_users.map((u) => u.count);

        new Chart(usersCtx, {
            type: "bar",
            data: {
                labels: userLabels,
                datasets: [
                    {
                        label: "Requests",
                        data: userCounts,
                        backgroundColor: "rgba(108,99,255,0.6)",
                        borderColor: "#6c63ff",
                        borderWidth: 1,
                        borderRadius: 4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    y: { beginAtZero: true, ticks: { stepSize: 1 } },
                    x: { ticks: { maxRotation: 30 } },
                },
            },
        });
    }
}

// ---------------------------------------------------------------------------
// Analytics Page Charts
// Called from analytics.html with more comprehensive data
// ---------------------------------------------------------------------------
function initAnalyticsCharts(data) {
    if (typeof Chart === "undefined") return;

    const labels = data.daily.map((d) => d.date);

    // Reuse daily request line chart (same as dashboard)
    const dailyCtx = document.getElementById("chart-an-daily");
    if (dailyCtx) {
        new Chart(dailyCtx, {
            type: "line",
            data: {
                labels,
                datasets: [
                    {
                        label: "Text requests",
                        data: data.daily.map((d) => d.text_count),
                        borderColor: "#3b82f6",
                        backgroundColor: "rgba(59,130,246,0.07)",
                        borderWidth: 2,
                        tension: 0.4,
                        fill: true,
                    },
                    {
                        label: "Image requests",
                        data: data.daily.map((d) => d.image_count),
                        borderColor: "#8b5cf6",
                        backgroundColor: "rgba(139,92,246,0.07)",
                        borderWidth: 2,
                        tension: 0.4,
                        fill: true,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "top", labels: { usePointStyle: true } } },
                scales: { y: { beginAtZero: true } },
            },
        });
    }

    // Doughnut for analytics page
    const typeCtx = document.getElementById("chart-an-types");
    if (typeCtx) {
        new Chart(typeCtx, {
            type: "doughnut",
            data: {
                labels: ["Text", "Image"],
                datasets: [
                    {
                        data: [data.text_requests, data.image_requests],
                        backgroundColor: ["#3b82f6", "#8b5cf6"],
                        borderColor: "#13131f",
                        borderWidth: 3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                cutout: "68%",
            },
        });
    }

    // Top users bar chart
    const usersCtx = document.getElementById("chart-an-users");
    if (usersCtx && data.top_users && data.top_users.length > 0) {
        new Chart(usersCtx, {
            type: "bar",
            data: {
                labels: data.top_users.map((u) => u.username || `user_${u.telegram_id}`),
                datasets: [
                    {
                        data: data.top_users.map((u) => u.count),
                        backgroundColor: "rgba(108,99,255,0.55)",
                        borderColor: "#6c63ff",
                        borderWidth: 1,
                        borderRadius: 4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true } },
            },
        });
    }

    // Daily cost line chart
    const costCtx = document.getElementById("chart-an-cost");
    if (costCtx) {
        new Chart(costCtx, {
            type: "line",
            data: {
                labels,
                datasets: [
                    {
                        label: "Cost (USD)",
                        data: data.daily.map((d) => d.cost.toFixed(5)),
                        borderColor: "#10b981",
                        backgroundColor: "rgba(16,185,129,0.08)",
                        borderWidth: 2,
                        tension: 0.4,
                        fill: true,
                        pointRadius: 3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => ` $${parseFloat(ctx.raw).toFixed(5)}`,
                        },
                    },
                },
                scales: { y: { beginAtZero: true } },
            },
        });
    }
}

// ---------------------------------------------------------------------------
// API Key Testing — called by the "Test" buttons on the settings page
// ---------------------------------------------------------------------------

/**
 * Test an API key by sending it to the server-side test endpoint.
 * Updates the result span next to the button with success/error feedback.
 *
 * @param {HTMLElement} button - The "Test" button element (has data-provider and data-field attrs)
 */
async function testApiKey(button) {
    const provider = button.getAttribute("data-provider");
    const fieldId = button.getAttribute("data-field");
    const resultId = `result-${provider}`;

    const field = document.getElementById(fieldId);
    const resultEl = document.getElementById(resultId);

    if (!field || !resultEl) return;

    // Read the current field value — if masked, read from field
    let apiKey = field.value.trim();
    if (!apiKey || apiKey === "••••••••••••••••") {
        resultEl.textContent = "⚠️ Enter a key to test";
        resultEl.style.color = "#eab308";
        return;
    }

    // Show loading state
    button.disabled = true;
    button.textContent = "Testing…";
    resultEl.textContent = "";

    try {
        const response = await fetch("/admin/settings/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ provider, api_key: apiKey }),
        });

        const data = await response.json();

        resultEl.textContent = data.message;
        resultEl.style.color = data.success ? "#10b981" : "#ef4444";
    } catch (err) {
        resultEl.textContent = `❌ Request failed: ${err.message}`;
        resultEl.style.color = "#ef4444";
    } finally {
        button.disabled = false;
        button.textContent = "Test";
    }
}

// ---------------------------------------------------------------------------
// Field Visibility Toggle — show/hide sensitive API key values
// ---------------------------------------------------------------------------

/**
 * Toggle a password input between 'password' (hidden) and 'text' (visible).
 *
 * @param {string} fieldId - The ID of the input field to toggle
 */
function toggleField(fieldId) {
    const field = document.getElementById(fieldId);
    if (!field) return;
    field.type = field.type === "password" ? "text" : "password";
}

// ---------------------------------------------------------------------------
// Sidebar Mobile Toggle
// ---------------------------------------------------------------------------

function initSidebar() {
    const toggle = document.getElementById("menu-toggle");
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("sidebar-overlay");

    if (!toggle || !sidebar) return;

    function openSidebar() {
        sidebar.classList.add("open");
        overlay.classList.add("visible");
        overlay.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden"; // Prevent background scroll
    }

    function closeSidebar() {
        sidebar.classList.remove("open");
        overlay.classList.remove("visible");
        overlay.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";
    }

    toggle.addEventListener("click", () => {
        sidebar.classList.contains("open") ? closeSidebar() : openSidebar();
    });

    // Close sidebar when tapping the overlay
    if (overlay) {
        overlay.addEventListener("click", closeSidebar);
    }

    // Close sidebar when pressing Escape
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && sidebar.classList.contains("open")) {
            closeSidebar();
        }
    });
}

// ---------------------------------------------------------------------------
// Flash Message Auto-dismiss
// Automatically removes flash messages after 4 seconds
// ---------------------------------------------------------------------------
function initFlashMessages() {
    const flash = document.getElementById("flash-message");
    if (!flash) return;

    // Auto-dismiss after 4 seconds
    setTimeout(() => {
        flash.style.transition = "opacity 0.4s ease, max-height 0.4s ease";
        flash.style.opacity = "0";
        flash.style.maxHeight = "0";
        flash.style.overflow = "hidden";
        setTimeout(() => flash.remove(), 400);
    }, 4000);
}

// ---------------------------------------------------------------------------
// Image provider UI toggle (settings page)
// Shows/hides the relevant API key field based on selected provider
// ---------------------------------------------------------------------------
function updateImageProviderUI(provider) {
    const replicateGroup = document.getElementById("group-replicate-key");
    const falGroup = document.getElementById("group-fal-key");

    if (replicateGroup) replicateGroup.style.display = provider === "replicate" ? "" : "none";
    if (falGroup) falGroup.style.display = provider === "fal" ? "" : "none";
}

// ---------------------------------------------------------------------------
// Initialize everything when the DOM is ready
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    configureChartDefaults();
    initSidebar();
    initFlashMessages();
});
