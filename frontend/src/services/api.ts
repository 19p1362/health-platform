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

// ---- Export API ----
export const exportApi = {
  getPatients: async (format: 'csv' | 'json' = 'json', filters?: Record<string, string>): Promise<Response> => {
    const query = new URLSearchParams({ format, ...filters });
    return fetchWithAuth(`/api/v1/exports/patients?${query.toString()}`);
  },

  downloadPatientsCsv: async (): Promise<Blob> => {
    const res = await fetchWithAuth('/api/v1/exports/patients?format=csv');
    return res.blob();
  },

  getPatientFhirBundle: async (patientId: string): Promise<any> => {
    const res = await fetchWithAuth(`/api/v1/exports/patient/${patientId}/fhir-bundle`, {
      method: 'POST',
    });
    return res.json();
  },

  getPatientRecords: async (patientId: string, format: 'csv' | 'json' = 'json'): Promise<Response> => {
    const res = await fetchWithAuth(`/api/v1/exports/patient/${patientId}/records?format=${format}`, {
      method: 'POST',
    });
    return res;
  },

  downloadAuditLogs: async (startDate?: string, endDate?: string): Promise<Blob> => {
    const query = new URLSearchParams();
    if (startDate) query.set('startDate', startDate);
    if (endDate) query.set('endDate', endDate);
    const res = await fetchWithAuth(`/api/v1/exports/audit-logs?${query.toString()}`);
    return res.blob();
  },

  getComplianceReport: async (): Promise<any> => {
    const res = await fetchWithAuth('/api/v1/exports/compliance-report');
    return res.json();
  },

  getHistory: async (): Promise<any[]> => {
    const res = await fetchWithAuth('/api/v1/exports/history');
    return res.json();
  },

  scheduleExport: async (schedule: {
    cronExpression: string;
    format: string;
    scope: string;
  }): Promise<any> => {
    const res = await fetchWithAuth('/api/v1/exports/scheduled', {
      method: 'POST',
      body: JSON.stringify(schedule),
    });
    return res.json();
  },
};

// ---- Connector API ----
export const connectorApi = {
  getTypes: async (): Promise<any[]> => {
    const res = await fetchWithAuth('/api/v1/connectors/types');
    return res.json();
  },

  list: async (): Promise<any[]> => {
    const res = await fetchWithAuth('/api/v1/connectors');
    return res.json();
  },

  register: async (config: {
    type: string;
    name: string;
    config: Record<string, any>;
  }): Promise<any> => {
    const res = await fetchWithAuth('/api/v1/connectors', {
      method: 'POST',
      body: JSON.stringify(config),
    });
    return res.json();
  },

  test: async (connectorId: string): Promise<any> => {
    const res = await fetchWithAuth(`/api/v1/connectors/${connectorId}/test`, {
      method: 'POST',
    });
    return res.json();
  },

  sync: async (connectorId: string): Promise<any> => {
    const res = await fetchWithAuth(`/api/v1/connectors/${connectorId}/sync`, {
      method: 'POST',
    });
    return res.json();
  },

  remove: async (connectorId: string): Promise<any> => {
    const res = await fetchWithAuth(`/api/v1/connectors/${connectorId}`, {
      method: 'DELETE',
    });
    return res.json();
  },

  getStatus: async (connectorId: string): Promise<any> => {
    const res = await fetchWithAuth(`/api/v1/connectors/${connectorId}/status`);
    return res.json();
  },
};

// ---- Vitals API ----
export const vitalsApi = {
  create: async (vital: any): Promise<any> => {
    const res = await fetchWithAuth('/api/v1/vitals', {
      method: 'POST',
      body: JSON.stringify(vital),
    });
    return res.json();
  },

  getByPatient: async (patientId: string, params?: {
    vital_type?: string;
    start_date?: string;
    end_date?: string;
    limit?: number;
    offset?: number;
  }): Promise<any> => {
    const query = new URLSearchParams();
    if (params?.vital_type) query.set('vital_type', params.vital_type);
    if (params?.start_date) query.set('start_date', params.start_date);
    if (params?.end_date) query.set('end_date', params.end_date);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const res = await fetchWithAuth(`/api/v1/vitals/patient/${patientId}?${query.toString()}`);
    return res.json();
  },

  getLatest: async (patientId: string): Promise<any[]> => {
    const res = await fetchWithAuth(`/api/v1/vitals/patient/${patientId}/latest`);
    return res.json();
  },

  getById: async (vitalId: string): Promise<any> => {
    const res = await fetchWithAuth(`/api/v1/vitals/${vitalId}`);
    return res.json();
  },

  update: async (vitalId: string, data: any): Promise<any> => {
    const res = await fetchWithAuth(`/api/v1/vitals/${vitalId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    return res.json();
  },

  delete: async (vitalId: string): Promise<void> => {
    await fetchWithAuth(`/api/v1/vitals/${vitalId}`, { method: 'DELETE' });
  },

  getTypes: async (): Promise<any[]> => {
    const res = await fetchWithAuth('/api/v1/vitals/types/list');
    return res.json();
  },
};

// ---- OPD API ----
export const opdApi = {
  register: async (data: {
    first_name: string;
    last_name: string;
    age?: number;
    gender?: string;
    phone?: string;
    address?: string;
    emergency_contact_name?: string;
    emergency_contact_phone?: string;
    chief_complaint?: string;
    existing_patient_id?: string;
  }): Promise<{
    registration_id: string;
    uhid: string;
    token_number: number;
    estimated_wait_minutes: number;
    patient_name: string;
    registration_date: string;
  }> => {
    const res = await fetchWithAuth('/api/v1/opd/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return res.json();
  },

  search: async (params: {
    phone?: string;
    uhid?: string;
    first_name?: string;
    last_name?: string;
  }): Promise<any[]> => {
    const query = new URLSearchParams();
    if (params.phone) query.set('phone', params.phone);
    if (params.uhid) query.set('uhid', params.uhid);
    if (params.first_name) query.set('first_name', params.first_name);
    if (params.last_name) query.set('last_name', params.last_name);
    const res = await fetchWithAuth(`/api/v1/opd/search?${query.toString()}`);
    return res.json();
  },

  getQueue: async (status?: string): Promise<{
    tokens: any[];
    total_waiting: number;
    total_in_progress: number;
    current_token?: number;
    next_token?: number;
  }> => {
    const query = status ? `?status=${status}` : '';
    const res = await fetchWithAuth(`/api/v1/opd/queue${query}`);
    return res.json();
  },

  queueAction: async (tokenId: string, action: string, room?: string): Promise<any> => {
    const query = new URLSearchParams({ token_id: tokenId, action: action });
    if (room) query.set('room', room);
    const res = await fetchWithAuth(`/api/v1/opd/queue/action?${query.toString()}`, {
      method: 'POST',
    });
    return res.json();
  },

  getTokenDetails: async (tokenId: string): Promise<any> => {
    const res = await fetchWithAuth(`/api/v1/opd/queue/${tokenId}`);
    return res.json();
  },

  getRegistration: async (registrationId: string): Promise<any> => {
    const res = await fetchWithAuth(`/api/v1/opd/registration/${registrationId}`);
    return res.json();
  },
};

// ---- SOAP API ----
export interface ICD10Code {
  code: string;
  description: string;
  category?: string;
  subcategory?: string;
  is_billable: boolean;
}

export interface Medication {
  name: string;
  dose?: string;
  frequency?: string;
  duration?: string;
  route?: string;
  instructions?: string;
}

export interface Investigation {
  name: string;
  type?: string;
  priority?: string;
  notes?: string;
}

export interface Referral {
  specialty: string;
  reason: string;
  urgency?: string;
  provider?: string;
}

export interface ICD10CodeEntry {
  code: string;
  description: string;
  primary?: boolean;
}

export interface SOAPNoteCreate {
  patient_id: string;
  encounter_id: string;
  token_id: string;
  subjective?: string;
  objective?: string;
  assessment?: string;
  plan?: string;
  chief_complaint?: string;
  icd10_codes: ICD10CodeEntry[];
  medications: Medication[];
  investigations: Investigation[];
  referrals: Referral[];
  follow_up_date?: string;
  follow_up_notes?: string;
  status?: string;
  word_count?: number;
  time_spent_seconds?: number;
}

export interface SOAPNoteUpdate {
  subjective?: string;
  objective?: string;
  assessment?: string;
  plan?: string;
  chief_complaint?: string;
  icd10_codes?: ICD10CodeEntry[];
  medications?: Medication[];
  investigations?: Investigation[];
  referrals?: Referral[];
  follow_up_date?: string;
  follow_up_notes?: string;
  status?: string;
  word_count?: number;
  time_spent_seconds?: number;
}

export interface VitalSign {
  type: string;
  value: string;
  unit: string;
  recorded_at: string;
  is_abnormal: boolean;
  reference_range_low?: string;
  reference_range_high?: string;
}

export interface SOAPNote {
  id: string;
  patient_id: string;
  encounter_id: string;
  token_id: string;
  subjective: string;
  objective: string;
  assessment: string;
  plan: string;
  chief_complaint: string;
  icd10_codes: ICD10CodeEntry[];
  medications: Medication[];
  investigations: Investigation[];
  referrals: Referral[];
  follow_up_date: string | null;
  follow_up_notes: string | null;
  status: string;
  version: number;
  word_count: number;
  time_spent_seconds: number;
  last_autosaved_at: string | null;
  pdf_generated_at: string | null;
  created_by: string | null;
  finalized_by: string | null;
  finalized_at: string | null;
  created_at: string;
  updated_at: string;
  patient_name: string;
  patient_age: number | null;
  patient_gender: string | null;
  token_number: number | null;
  uhid: string | null;
  latest_vitals: VitalSign[];
}

export interface SOAPVersion {
  id: string;
  soap_note_id: string;
  version_number: number;
  subjective: string | null;
  objective: string | null;
  assessment: string | null;
  plan: string | null;
  icd10_codes: ICD10CodeEntry[];
  medications: Medication[];
  investigations: Investigation[];
  referrals: Referral[];
  follow_up_date: string | null;
  follow_up_notes: string | null;
  word_count: number;
  time_spent_seconds: number;
  is_autosave: boolean;
  changed_by: string | null;
  change_summary: string | null;
  created_at: string;
}

export interface ICD10SearchResponse {
  codes: ICD10Code[];
  total: number;
}

export const soapApi = {
  createOrUpdate: async (patientId: string, data: SOAPNoteCreate | SOAPNoteUpdate): Promise<SOAPNote> => {
    const res = await fetchWithAuth('/api/v1/clinical/soap', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return res.json();
  },

  getByEncounter: async (patientId: string): Promise<SOAPNote> => {
    const res = await fetchWithAuth(`/api/v1/clinical/soap/${patientId}`);
    return res.json();
  },

  getVersions: async (patientId: string): Promise<SOAPVersion[]> => {
    const res = await fetchWithAuth(`/api/v1/clinical/soap/${patientId}/versions`);
    return res.json();
  },

  autosave: async (patientId: string, data: SOAPNoteUpdate): Promise<SOAPNote> => {
    const res = await fetchWithAuth(`/api/v1/clinical/soap/${patientId}/autosave`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return res.json();
  },

  finalize: async (patientId: string): Promise<SOAPNote> => {
    const res = await fetchWithAuth(`/api/v1/clinical/soap/${patientId}/finalize`, {
      method: 'POST',
    });
    return res.json();
  },

  exportPDF: async (patientId: string): Promise<string> => {
    const res = await fetchWithAuth(`/api/v1/clinical/soap/${patientId}/pdf`);
    return res.text();
  },

  searchICD10: async (query: string): Promise<ICD10SearchResponse> => {
    const res = await fetchWithAuth(`/api/v1/clinical/icd10/search?q=${encodeURIComponent(query)}`);
    return res.json();
  },
};

export { API_BASE, ApiError, fetchWithAuth };
