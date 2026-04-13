/**
 * API Client — centralised HTTP layer for all backend calls.
 */

const BASE = '/api'

function adminHeaders() {
    const token = getAdminToken()
    return token ? { 'X-Omniflow-Admin-Token': token } : {}
}

export function getAdminToken() {
    return window.localStorage.getItem('omniflow_admin_token') || ''
}

export function setAdminToken(token) {
    const trimmed = String(token || '').trim()
    if (trimmed) {
        window.localStorage.setItem('omniflow_admin_token', trimmed)
    } else {
        window.localStorage.removeItem('omniflow_admin_token')
    }
}

async function request(path, options = {}) {
    const url = `${BASE}${path}`
    const resp = await fetch(url, {
        headers: {
            'Content-Type': 'application/json',
            ...adminHeaders(),
            ...options.headers,
        },
        ...options,
    })
    if (!resp.ok) {
        const error = new Error(`API ${resp.status}: ${resp.statusText}`)
        error.status = resp.status
        throw error
    }
    return resp.json()
}

export const api = {
    // Health
    health: () => request('/health'),

    // Config
    getConfig: () => request('/config'),
    patchConfig: (data) =>
        request('/config', { method: 'PATCH', body: JSON.stringify(data) }),

    // Workflow
    triggerRun: () => request('/workflow/run', { method: 'POST' }),

    // Logs
    getLogs: (limit = 50) => request(`/logs?limit=${limit}`),

    // Status
    getStatus: () => request('/status'),

    // Items
    getItems: (limit = 50) => request(`/items?limit=${limit}`),

    // Runs
    getRuns: (limit = 20) => request(`/runs?limit=${limit}`),

    // Plugin discovery
    discoverPlugins: () => request('/plugins/discover'),

    // Prompt files
    getSoulPrompt: () => request('/prompt/soul'),
    saveSoulPrompt: (content) =>
        request('/prompt/soul', {
            method: 'PATCH',
            body: JSON.stringify({ content }),
        }),

    // SSE stream (returns EventSource instance)
    streamLogs: () => new EventSource(`${BASE}/logs/stream`),
}
