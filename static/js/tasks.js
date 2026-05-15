/* HarnessAudit Task Browser: renders the generated multi-agent task snapshot. */
const DATA = window.HA_TASK_BROWSER_DATA || null;
const DOMAINS = DATA ? DATA.domains : [];
const TASKS = DATA ? DATA.tasks : [];
const TOOLS_BY_DOMAIN = DATA ? DATA.tools : {};

const DOMAIN_ALIASES = {
    social: "social_interaction",
    daily: "daily_life",
    legal: "legal_compliance",
    swe: "software_engineering",
};

function domainOf(id) {
    return DOMAINS.find(d => d.id === id) || {
        id,
        label: prettyLabel(id),
        emoji: "◇",
        color: "#2563eb",
        blurb: "Domain metadata unavailable.",
    };
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
    }[c]));
}

function prettyLabel(value) {
    return String(value || "")
        .replace(/_/g, " ")
        .replace(/\b\w/g, c => c.toUpperCase());
}

function plural(value, singular, pluralLabel = `${singular}s`) {
    return `${value} ${value === 1 ? singular : pluralLabel}`;
}


function taskBlob(task) {
    const metadata = task.metadata || {};
    const agentText = (task.agents || []).flatMap(agent => [
        agent.role,
        agent.description,
        ...(agent.useful_tools || []),
        ...(agent.forbidden_tools || []),
    ]);
    return [
        task.id,
        task.domain,
        task.category,
        task.modality,
        task.fixture,
        task.title,
        task.goal,
        task.source_path,
        ...Object.values(metadata).flatMap(v => Array.isArray(v) ? v : [v]),
        ...(task.roles || []),
        ...(task.tools || []),
        ...agentText,
    ].join(" ").toLowerCase();
}

let activeDomain = DOMAINS[0]?.id || "";
let activeQuery = "";

function renderMissingData() {
    const gridEl = document.getElementById("taskGrid");
    const panel = document.getElementById("domainPanel");
    const countEl = document.getElementById("taskCount");
    if (panel) {
        panel.innerHTML = `<div class="task-empty">Task data is missing. Load <code>static/js/task_data.js</code> before <code>static/js/tasks.js</code>.</div>`;
    }
    if (gridEl) gridEl.innerHTML = `<div class="task-empty">No generated task snapshot was found.</div>`;
    if (countEl) countEl.textContent = "0 tasks";
}

function renderHeroStats() {
    const strip = document.getElementById("statsStrip") || document.querySelector(".stats-strip");
    if (!strip || !DATA) return;
    const stats = DATA.stats || {};
    const cards = [
        [stats.task_count, "Multi-Agent Tasks"],
        [stats.domain_count, "Domains"],
        [stats.category_count, "Categories"],
        [stats.role_template_count, "Role Templates"],
        [stats.tool_definition_count, "Tool Definitions"],
    ];
    strip.innerHTML = cards.map(([num, label]) => `
        <div class="stat-card"><div class="num">${escapeHtml(num)}</div><div class="label">${escapeHtml(label)}</div></div>
    `).join("");
}

function counts() {
    const m = {};
    DOMAINS.forEach(d => { m[d.id] = TASKS.filter(t => t.domain === d.id).length; });
    return m;
}

function renderChips() {
    const chipsEl = document.getElementById("domainChips");
    if (!chipsEl) return;
    const c = counts();
    chipsEl.innerHTML = DOMAINS.map(d => `
        <button class="domain-chip ${activeDomain === d.id ? "active" : ""}" data-d="${d.id}" style="${activeDomain === d.id ? `background:linear-gradient(135deg,${d.color},${d.color}cc);` : ""}">
            <span class="chip-emoji">${d.emoji}</span> ${escapeHtml(d.label)}
            <span class="chip-count">${c[d.id] || 0}</span>
        </button>
    `).join("");
    chipsEl.querySelectorAll(".domain-chip").forEach(btn => {
        btn.addEventListener("click", () => {
            activeDomain = btn.dataset.d;
            renderChips();
            renderTasks();
            renderDomainPanel();
            const params = new URLSearchParams(window.location.search);
            params.set("domain", activeDomain);
            const next = `${window.location.pathname}${params.toString() ? `?${params}` : ""}`;
            window.history.replaceState(null, "", next);
        });
    });
}

function renderDomainPanel() {
    const panel = document.getElementById("domainPanel");
    if (!panel || !DATA) return;
    const stats = DATA.stats || {};
    const d = domainOf(activeDomain);
    const dStats = (stats.by_domain || {})[activeDomain] || {};
    panel.innerHTML = `
        <div class="domain-panel-icon" style="background:linear-gradient(135deg,${d.color},${d.color}cc);">${d.emoji}</div>
        <div style="flex:1;min-width:0;">
            <div class="domain-panel-label" style="color:${d.color}">${escapeHtml(d.label)}</div>
            <p class="domain-panel-blurb">${escapeHtml(d.blurb)}</p>
            <div class="domain-panel-stats">
                <span><strong>${dStats.task_count || 0}</strong> tasks</span>
                <span><strong>${dStats.category_count || 0}</strong> categories</span>
                <span><strong>${dStats.role_count || 0}</strong> roles</span>
                <span><strong>${dStats.task_tool_count || 0}</strong> task tools</span>
            </div>
        </div>
    `;
}

function filteredTasks() {
    const q = activeQuery.trim().toLowerCase();
    return TASKS.filter(t => {
        if (activeDomain && t.domain !== activeDomain) return false;
        return !q || taskBlob(t).includes(q);
    });
}

function renderTasks() {
    const gridEl = document.getElementById("taskGrid");
    const countEl = document.getElementById("taskCount");
    if (!gridEl) return;
    const filtered = filteredTasks();
    if (countEl) countEl.textContent = `${filtered.length} task${filtered.length === 1 ? "" : "s"} shown`;
    if (filtered.length === 0) {
        gridEl.innerHTML = `<div class="task-empty">No tasks match your filter.</div>`;
        return;
    }
    gridEl.innerHTML = filtered.map(t => {
        const d = domainOf(t.domain);
        return `
        <div class="task-card" data-id="${escapeHtml(t.id)}" style="border-left-color:${d.color}">
            <div class="task-id">${escapeHtml(t.id)} · ${escapeHtml(t.category)}</div>
            <div class="task-title">${escapeHtml(t.title)}</div>
            <div class="task-meta">
                <span class="meta-pill" style="background:${d.color}1a;color:${d.color}">${d.emoji} ${escapeHtml(d.label)}</span>
                <span class="meta-pill role">${plural((t.roles || []).length, "role")}</span>
                <span class="meta-pill" style="background:rgba(13,148,136,0.10);color:#0d9488">${plural((t.tools || []).length, "tool")}</span>
                ${t.modality === "multimodal" ? `<span class="meta-pill" style="background:rgba(234,88,12,0.10);color:#ea580c">multimodal</span>` : ""}
            </div>
            <div class="task-snippet">${escapeHtml(t.goal)}</div>
        </div>`;
    }).join("");
    gridEl.querySelectorAll(".task-card").forEach(card => {
        card.addEventListener("click", () => openTaskModal(card.dataset.id));
    });
}

function renderToolTags(names, extraClass = "") {
    if (!names || names.length === 0) return `<span class="muted">—</span>`;
    return names.map(name => {
        const cls = ["tool-tag", extraClass].filter(Boolean).join(" ");
        return `<code class="${cls}">${escapeHtml(name)}</code>`;
    }).join("");
}

function renderRoleCards(task) {
    return (task.agents || []).map(agent => `
        <div class="role-tool-card">
            <div class="role-tool-head">
                <span>${escapeHtml(agent.role)}</span>
                <small>${escapeHtml(agent.description || "")}</small>
            </div>
            <div class="role-tool-row"><strong>Useful</strong><div>${renderToolTags(agent.useful_tools || [], "useful")}</div></div>
            <div class="role-tool-row"><strong>Forbidden</strong><div>${renderToolTags(agent.forbidden_tools || [], "forbidden")}</div></div>
        </div>
    `).join("");
}

function renderSummaryGrid(items) {
    return `<div class="summary-grid">${items.map(([label, value]) => `
        <div class="summary-item"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
    `).join("")}</div>`;
}

function renderAccessSummary(summary) {
    const byType = summary.by_type || {};
    const severity = summary.by_severity || {};
    const items = [["Access rules", summary.total || 0]];
    Object.keys(byType).sort().forEach(k => items.push([k, byType[k]]));
    Object.keys(severity).sort().forEach(k => items.push([`severity.${k}`, severity[k]]));
    return `<ul class="modal-list compact-list">${items.map(([label, value]) => `
        <li><strong>${escapeHtml(label)}</strong>: ${escapeHtml(value)}</li>
    `).join("")}</ul>`;
}

function renderCompletionSummary(summary) {
    const byType = summary.by_type || {};
    const ruleTypes = summary.rule_types || {};
    const items = [["Completion checkpoints", summary.total || 0]];
    Object.keys(byType).sort().forEach(k => items.push([k, byType[k]]));
    Object.keys(ruleTypes).sort().forEach(k => items.push([`rule.${k}`, ruleTypes[k]]));
    return `<ul class="modal-list compact-list">${items.map(([label, value]) => `
        <li><strong>${escapeHtml(label)}</strong>: ${escapeHtml(value)}</li>
    `).join("")}</ul>`;
}

function renderMetadata(metadata) {
    const entries = Object.entries(metadata || {});
    if (!entries.length) return `<span class="muted">No compact metadata fields.</span>`;
    return `<div class="metadata-list">${entries.map(([k, v]) => `
        <div><strong>${escapeHtml(prettyLabel(k))}</strong><span>${escapeHtml(Array.isArray(v) ? v.join(", ") : v)}</span></div>
    `).join("")}</div>`;
}

function openTaskModal(id) {
    const task = TASKS.find(x => x.id === id);
    if (!task) return;
    const domain = domainOf(task.domain);
    const modal = document.getElementById("taskModal");
    const body = document.getElementById("modalBody");
    document.getElementById("modalId").textContent = `${task.id} · ${domain.label} · ${task.category}`;
    document.getElementById("modalTitle").textContent = task.title;
    document.getElementById("modalMeta").innerHTML = `
        <span class="meta-pill" style="background:${domain.color}1a;color:${domain.color}">${domain.emoji} ${escapeHtml(domain.label)}</span>
        <span class="meta-pill role">${plural((task.roles || []).length, "role")}</span>
        <span class="meta-pill" style="background:rgba(13,148,136,0.10);color:#0d9488">${plural((task.tools || []).length, "tool")}</span>
        <span class="meta-pill">${escapeHtml(task.modality)}</span>
        ${task.fixture ? `<span class="meta-pill">fixture: ${escapeHtml(task.fixture)}</span>` : ""}
    `;
    body.innerHTML = `
        <div class="field">
            <h4>Goal</h4>
            <p>${escapeHtml(task.goal)}</p>
        </div>
        ${renderSummaryGrid([
            ["Task ID", task.id],
            ["Category", prettyLabel(task.category)],
            ["Source", task.source_path],
            ["Input Assets", (task.input_assets || []).length],
            ["Access Rules", (task.access_summary || {}).total || 0],
        ])}
        <div class="field">
            <h4>Roles & Tool Scope</h4>
            <div class="role-tool-grid">${renderRoleCards(task)}</div>
        </div>
        <div class="field">
            <h4>Task Tool Set</h4>
            <div class="tool-list">${renderToolTags(task.tools || [])}</div>
        </div>
        <div class="field">
            <h4>Boundary Rule Summary</h4>
            ${renderAccessSummary(task.access_summary || {})}
        </div>
        <div class="field">
            <h4>Completion Checks</h4>
            ${renderCompletionSummary(task.completion_summary || {})}
        </div>
        <div class="field">
            <h4>Input Assets</h4>
            ${(task.input_assets || []).length ? `<ul class="modal-list">${task.input_assets.map(asset => `
                <li><strong>${escapeHtml(asset.asset_type || "asset")}</strong>: ${escapeHtml(asset.path || "")} ${asset.description ? `— ${escapeHtml(asset.description)}` : ""}</li>
            `).join("")}</ul>` : `<p class="modal-note">No declared multimodal input assets.</p>`}
        </div>
        <div class="field">
            <h4>Metadata</h4>
            ${renderMetadata(task.metadata || {})}
        </div>
    `;
    modal.classList.add("open");
    document.body.style.overflow = "hidden";
}

function closeTaskModal() {
    const modal = document.getElementById("taskModal");
    if (!modal) return;
    modal.classList.remove("open");
    document.body.style.overflow = "";
}

document.addEventListener("DOMContentLoaded", () => {
    if (!DATA) {
        renderMissingData();
        return;
    }
    renderHeroStats();
    const params = new URLSearchParams(window.location.search);
    const requested = params.get("domain");
    const normalized = DOMAIN_ALIASES[requested] || requested;
    if (normalized && DOMAINS.some(d => d.id === normalized)) {
        activeDomain = normalized;
    }
    renderChips();
    renderDomainPanel();
    renderTasks();

    const search = document.getElementById("taskSearch");
    if (search) {
        search.addEventListener("input", e => {
            activeQuery = e.target.value;
            renderTasks();
        });
    }

    const closeBtn = document.getElementById("modalClose");
    if (closeBtn) closeBtn.addEventListener("click", closeTaskModal);
    const modal = document.getElementById("taskModal");
    if (modal) modal.addEventListener("click", e => { if (e.target === modal) closeTaskModal(); });
    document.addEventListener("keydown", e => {
        if (e.key === "Escape" && modal && modal.classList.contains("open")) closeTaskModal();
    });
});
