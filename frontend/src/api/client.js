/**
 * API Client — centralised HTTP layer for all backend calls.
 */

const BASE = '/api'

async function request(path, options = {}) {
    const url = `${BASE}${path}`
    const resp = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    })
    if (!resp.ok) {
        throw new Error(`API ${resp.status}: ${resp.statusText}`)
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

    // Plugin discovery
    discoverPlugins: () => request('/plugins/discover'),

    // SSE stream (returns EventSource instance)
    streamLogs: () => new EventSource(`${BASE}/logs/stream`),
}
