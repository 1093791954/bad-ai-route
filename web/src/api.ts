export interface UpstreamConfig {
  base_url: string
  api_key: string
  request_timeout: number
  first_chunk_timeout: number
}

export interface ModelEntry {
  name: string
  enabled: boolean
}

export interface Settings {
  listen_host: string
  listen_port: number
  cooldown_seconds: number
  upstream: UpstreamConfig
  models: ModelEntry[]
}

export interface ModelHealth {
  available: boolean
  cooldown_remaining: number
  last_error_code: number | null
  last_error_msg: string
}

export interface HealthResponse {
  models: Record<string, ModelHealth>
  cooldown_seconds: number
}

export interface ProbeResponse {
  status: 'ok' | 'error'
  message?: string
  models: string[]
}

const BASE = ''

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const resp = await fetch(BASE + path, {
    headers: { 'content-type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`
    try {
      const data = await resp.json()
      msg = data.message || data.error?.message || msg
    } catch {
      // ignore
    }
    throw new Error(msg)
  }
  return resp.json()
}

export const api = {
  getConfig: () => request<Settings>('/api/config'),
  updateConfig: (settings: Settings) =>
    request<{ status: string; message: string }>('/api/config', {
      method: 'PUT',
      body: JSON.stringify(settings),
    }),
  probeModels: () =>
    request<ProbeResponse>('/api/models/probe', { method: 'POST' }),
  getHealth: () => request<HealthResponse>('/api/health'),
  resetHealth: () =>
    request<{ status: string }>('/api/health/reset', { method: 'POST' }),
}
