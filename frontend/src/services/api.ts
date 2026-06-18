const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8080';

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function getToken(): string | null {
  return localStorage.getItem('healthbridge_token');
}

async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem('healthbridge_token');
      localStorage.removeItem('healthbridge_user');
      window.location.href = '/login';
      throw new ApiError('Unauthorized', 401);
    }
    const errorBody = await response.json().catch(() => ({ message: response.statusText }));
    throw new ApiError(errorBody.message || `Request failed with status ${response.status}`, response.status);
  }

  return response;
}

// ---- Patient API ----
export const patientApi = {
  search: async (params: {
    firstName?: string;
    lastName?: string;
    mrn?: string;
    phone?: string;
    searchExternal?: boolean;
  }): Promise<any[]> => {
    const query = new URLSearchParams();
    if (params.firstName) query.set('firstName', params.firstName);
    if (params.lastName) query.set('lastName', params.lastName);
    if (params.mrn) query.set('mrn', params.mrn);
    if (params.phone) query.set('phone', params.phone);
    if (params.searchExternal) query.set('searchExternal', 'true');

    const res = await fetchWithAuth(`/api/patients/search?${query.toString()}`);
    return res.json();
  },

  getById: async (id: string): Promise<any> => {
    const res = await fetchWithAuth(`/api/patients/${id}`);
    return res.json();
  },

  getChart: async (patientId: string): Promise<any> => {
    const res = await fetchWithAuth(`/api/patients/${patientId}/chart`);
    return res.json();
  },
};

// ---- Consent API ----
export const consentApi = {
  getStatus: async (patientId: string): Promise<any> => {
    const res = await fetchWithAuth(`/api/consent/${patientId}/status`);
    return res.json();
  },

  grant: async (patientId: string, payload: {
    purpose: string;
    dataCategories: string[];
    durationDays: number;
  }): Promise<any> => {
    const res = await fetchWithAuth(`/api/consent/${patientId}/grant`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    return res.json();
  },

  withdraw: async (patientId: string, consentId: string): Promise<any> => {
    const res = await fetchWithAuth(`/api/consent/${patientId}/withdraw`, {
      method: 'POST',
      body: JSON.stringify({ consentId }),
    });
    return res.json();
  },

  getHistory: async (patientId?: string): Promise<any[]> => {
    const query = patientId ? `?patientId=${patientId}` : '';
    const res = await fetchWithAuth(`/api/consent/history${query}`);
    return res.json();
  },

  getAll: async (): Promise<any[]> => {
    const res = await fetchWithAuth('/api/consent');
    return res.json();
  },
};

// ---- Conversion API ----
export const conversionApi = {
  ccdaToFhir: async (ccdaXml: string | File): Promise<any> => {
    const body = ccdaXml instanceof File ? ccdaXml : JSON.stringify({ xml: ccdaXml });
    const headers: Record<string, string> = {};
    if (!(ccdaXml instanceof File)) {
      headers['Content-Type'] = 'application/json';
    }
    const res = await fetchWithAuth('/api/convert/ccda-to-fhir', {
      method: 'POST',
      headers,
      body,
    });
    return res.json();
  },

  fhirToCcda: async (fhirBundle: any): Promise<any> => {
    const res = await fetchWithAuth('/api/convert/fhir-to-ccda', {
      method: 'POST',
      body: JSON.stringify(fhirBundle),
    });
    return res.json();
  },

  fhirToPdf: async (fhirBundle: any): Promise<Blob> => {
    const res = await fetchWithAuth('/api/convert/fhir-to-pdf', {
      method: 'POST',
      body: JSON.stringify(fhirBundle),
    });
    return res.blob();
  },

  hl7v2ToFhir: async (hl7Message: string): Promise<any> => {
    const res = await fetchWithAuth('/api/convert/hl7v2-to-fhir', {
      method: 'POST',
      body: JSON.stringify({ message: hl7Message }),
    });
    return res.json();
  },

  validate: async (content: any, format: string): Promise<any> => {
    const res = await fetchWithAuth('/api/convert/validate', {
      method: 'POST',
      body: JSON.stringify({ content, format }),
    });
    return res.json();
  },

  getHistory: async (): Promise<any[]> => {
    const res = await fetchWithAuth('/api/convert/history');
    return res.json();
  },

  getStats: async (): Promise<any> => {
    const res = await fetchWithAuth('/api/convert/stats');
    return res.json();
  },
};

// ---- FHIR API ----
export const fhirApi = {
  read: async (resourceType: string, id: string): Promise<any> => {
    const res = await fetchWithAuth(`/api/fhir/${resourceType}/${id}`);
    return res.json();
  },

  search: async (resourceType: string, params: Record<string, string>): Promise<any> => {
    const query = new URLSearchParams(params).toString();
    const res = await fetchWithAuth(`/api/fhir/${resourceType}?${query}`);
    return res.json();
  },

  create: async (resourceType: string, resource: any): Promise<any> => {
    const res = await fetchWithAuth(`/api/fhir/${resourceType}`, {
      method: 'POST',
      body: JSON.stringify(resource),
    });
    return res.json();
  },
};

// ---- Compliance API ----
export const complianceApi = {
  getAuditLogs: async (params?: {
    action?: string;
    patientId?: string;
    startDate?: string;
    endDate?: string;
    page?: number;
    limit?: number;
  }): Promise<{ logs: any[]; total: number; page: number; pages: number }> => {
    const query = new URLSearchParams();
    if (params?.action) query.set('action', params.action);
    if (params?.patientId) query.set('patientId', params.patientId);
    if (params?.startDate) query.set('startDate', params.startDate);
    if (params?.endDate) query.set('endDate', params.endDate);
    if (params?.page) query.set('page', String(params.page));
    if (params?.limit) query.set('limit', String(params.limit));
    const res = await fetchWithAuth(`/api/compliance/audit-logs?${query.toString()}`);
    return res.json();
  },

  getBreachEvents: async (): Promise<any[]> => {
    const res = await fetchWithAuth('/api/compliance/breaches');
    return res.json();
  },

  getComplianceReport: async (): Promise<any> => {
    const res = await fetchWithAuth('/api/compliance/report');
    return res.json();
  },

  getErasureSchedule: async (): Promise<any[]> => {
    const res = await fetchWithAuth('/api/compliance/erasure-schedule');
    return res.json();
  },

  getDataPrincipalRequests: async (): Promise<any> => {
    const res = await fetchWithAuth('/api/compliance/data-principal-requests');
    return res.json();
  },

  getSlaCompliance: async (): Promise<any> => {
    const res = await fetchWithAuth('/api/compliance/sla');
    return res.json();
  },

  getAuditRetention: async (): Promise<any> => {
    const res = await fetchWithAuth('/api/compliance/audit-retention');
    return res.json();
  },

  downloadReport: async (type: string): Promise<Blob> => {
    const res = await fetchWithAuth(`/api/compliance/report/download/${type}`);
    return res.blob();
  },
};

// ---- Ingestion API ----
export const ingestionApi = {
  getLogs: async (limit: number = 20): Promise<any[]> => {
    const res = await fetchWithAuth(`/api/v1/ingest/logs?limit=${limit}`);
    return res.json();
  },

  upload: async (formData: FormData): Promise<any> => {
    const token = localStorage.getItem('healthbridge_token');
    const res = await fetch(`${API_BASE}/api/v1/ingest/upload`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ message: res.statusText }));
      throw new Error(err.detail || err.message || 'Upload failed');
    }
    return res.json();
  },

  getLogDetail: async (logId: string): Promise<any> => {
    const res = await fetchWithAuth(`/api/v1/ingest/logs/${logId}`);
    return res.json();
  },
};

// ---- Health API ----
export const healthApi = {
  getStatus: async (): Promise<any> => {
    const res = await fetch(`${API_BASE}/api/health`);
    return res.json();
  },

  getStats: async (): Promise<any> => {
    const res = await fetchWithAuth('/api/health/stats');
    return res.json();
  },
};

export { API_BASE, ApiError, fetchWithAuth };
