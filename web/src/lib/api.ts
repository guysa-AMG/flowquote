const API_BASE = '/api'

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  redirectOnUnauthorized = true,
): Promise<T> {
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
    if (response.status === 401 && redirectOnUnauthorized) {
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
  status: string
  quote_id?: string | null
  kind: 'quote' | 'variation'
  based_on_version: number | null
  [key: string]: any
}

export const api = {
  auth: {
    login: (pin: string) => request<{ token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ pin }),
    }),
    changePin: (currentPin: string, newPin: string) =>
      request<{ status: string }>('/auth/pin', {
        method: 'POST',
        body: JSON.stringify({ current_pin: currentPin, new_pin: newPin }),
      }, false),
  },

  memos: {
    upload: (
      file: File,
      kind: 'quote' | 'variation' = 'quote',
      quoteId?: string,
      metadata: { customerName?: string; siteAddress?: string; basedOnVersion?: number } = {},
    ) => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('kind', kind)
      if (quoteId) formData.append('quote_id', quoteId)
      if (metadata.customerName) formData.append('customer_name', metadata.customerName)
      if (metadata.siteAddress) formData.append('site_address', metadata.siteAddress)
      if (metadata.basedOnVersion !== undefined) {
        formData.append('based_on_version', String(metadata.basedOnVersion))
      }

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
    list: () => request<Array<{
      id: string
      number: string
      customer_name: string | null
      site_address: string | null
      status: string
      created_at: string
      total_cents: number | null
      currency: string
    }>>('/quotes'),
    get: (id: string) => request<{ quote: any; version: any; lines: any[]; currency: string; vat_rate_bp: number }>(`/quotes/${id}`),
    getLines: (id: string) => request<{ lines: any[] }>(`/quotes/${id}/lines`),
    getCandidates: (quoteId: string, lineId: string) =>
      request<{ outcome: string; flag_reason: string | null; candidates: Array<{ price_item_id: number; sku: string; name: string; unit: string; price_cents: number; score: number }> }>(
        `/quotes/${quoteId}/lines/${lineId}/candidates`,
      ),
    updateLine: (quoteId: string, lineId: string, data: any) =>
      request<{ status: string; line_id: string; version: number; subtotal_cents: number; vat_cents: number; total_cents: number }>(`/quotes/${quoteId}/lines/${lineId}`, {
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
      }).then(async res => {
        if (!res.ok) {
          const error = await res.json().catch(() => ({ detail: 'PDF request failed' }))
          throw new ApiError(res.status, error.detail || 'PDF request failed')
        }
        return res.blob()
      })
    },
  },

  variations: {
    create: (
      quoteId: string,
      memoId: string,
      basedOnVersion: number,
      lines: Array<{ spoken: string; kind: string; price_item_id: number; quantity_milli: number }>,
    ) =>
      request<{
        variation_id: string
        number: string
        status: string
        total_cents: number
      }>(`/quotes/${quoteId}/variations`, {
        method: 'POST',
        body: JSON.stringify({ memo_id: memoId, based_on_version: basedOnVersion, lines }),
      }),
    approve: (id: string, approverName: string) =>
      request<{ status: string }>(`/variations/${id}/approve`, {
        method: 'POST',
        body: JSON.stringify({ approver_name: approverName }),
      }),
    getPdf: (id: string) => {
      const token = localStorage.getItem('talkquote_token')
      return fetch(`${API_BASE}/variations/${id}/pdf`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      }).then(async res => {
        if (!res.ok) {
          const error = await res.json().catch(() => ({ detail: 'Variation PDF request failed' }))
          throw new ApiError(res.status, error.detail || 'Variation PDF request failed')
        }
        return res.blob()
      })
    },
  },

  pricelist: {
    list: () => request<Array<{
      id: number
      sku: string
      name: string
      unit: string
      price_cents: number
      category: string
      attrs: Record<string, string>
      active: number
      currency: string
    }>>('/pricelist'),
    import: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const token = localStorage.getItem('talkquote_token')
      return fetch(`${API_BASE}/pricelist/import`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      }).then(async res => {
        if (!res.ok) {
          const error = await res.json().catch(() => ({ detail: 'Import failed' }))
          throw new ApiError(res.status, error.detail || 'Import failed')
        }
        return res.json() as Promise<{ imported: number }>
      })
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
