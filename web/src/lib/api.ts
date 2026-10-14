const API_BASE = '/api'

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('talkquote_token')
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  }

  if (token) {
    ;(headers as Record<string, string>)['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  })

  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem('talkquote_token')
      window.location.href = '/login'
    }
    const error = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new ApiError(response.status, error.detail || 'Request failed')
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

interface MemoResponse {
  id: string
  transcript: string
  extraction_json: string
  quote_id?: string | null
  [key: string]: any
}

export const api = {
  auth: {
    login: (pin: string) => request<{ token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ pin }),
    }),
  },

  memos: {
    upload: (file: File, kind: string = 'quote', quoteId?: string) => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('kind', kind)
      if (quoteId) formData.append('quote_id', quoteId)

      const token = localStorage.getItem('talkquote_token')
      return fetch(`${API_BASE}/memos`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      }).then(res => {
        if (!res.ok) throw new ApiError(res.status, 'Upload failed')
        return res.json()
      })
    },
    get: (id: string) => request<MemoResponse>(`/memos/${id}`),
  },

  jobs: {
    getStatus: (id: string) => request<{ id: string; state: string; error?: string }>(`/jobs/${id}`),
    subscribe: (id: string, onMessage: (data: any) => void) => {
      const token = localStorage.getItem('talkquote_token')
      const url = `${API_BASE}/jobs/${id}/events${token ? `?token=${token}` : ''}`
      const es = new EventSource(url)
      es.onmessage = (e) => onMessage(JSON.parse(e.data))
      es.onerror = () => es.close()
      return () => es.close()
    },
  },

  quotes: {
    get: (id: string) => request<{ quote: any; version: any; lines: any[] }>(`/quotes/${id}`),
    getLines: (id: string) => request<{ lines: any[] }>(`/quotes/${id}/lines`),
    updateLine: (quoteId: string, lineId: string, data: any) =>
      request<{ status: string }>(`/quotes/${quoteId}/lines/${lineId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    approve: (id: string, approverName: string) =>
      request<{ status: string }>(`/quotes/${id}/approve`, {
        method: 'POST',
        body: JSON.stringify({ approver_name: approverName }),
      }),
    send: (id: string) =>
      request<{ status: string; total_cents: number }>(`/quotes/${id}/send`, {
        method: 'POST',
      }),
    getPdf: (id: string) => {
      const token = localStorage.getItem('talkquote_token')
      return fetch(`${API_BASE}/quotes/${id}/pdf`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      }).then(res => res.blob())
    },
  },

  variations: {
    create: (quoteId: string, memoId: string) =>
      request<{ id: string }>(`/quotes/${quoteId}/variations`, {
        method: 'POST',
        body: JSON.stringify({ memo_id: memoId }),
      }),
    approve: (id: string, approverName: string) =>
      request<{ status: string }>(`/variations/${id}/approve`, {
        method: 'POST',
        body: JSON.stringify({ approver_name: approverName }),
      }),
  },

  pricelist: {
    list: () => request<any[]>(`/pricelist`),
    import: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const token = localStorage.getItem('talkquote_token')
      return fetch(`${API_BASE}/pricelist/import`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      }).then(res => res.json())
    },
  },

  aliases: {
    list: () => request<any[]>(`/aliases`),
    create: (phrase: string, priceItemId: number) =>
      request<any>(`/aliases`, {
        method: 'POST',
        body: JSON.stringify({ phrase, price_item_id: priceItemId }),
      }),
    delete: (id: number) =>
      request<void>(`/aliases/${id}`, { method: 'DELETE' }),
  },

  audit: {
    get: (quoteId: string) => request<any[]>(`/audit?quote_id=${quoteId}`),
  },

  system: {
    get: () => request<any>(`/system`),
  },
}

export { ApiError }
