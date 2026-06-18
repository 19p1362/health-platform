/* ═══════════════════════════════════════════
   HealthBridge SPA — API Service Layer
   Talks to the actual FastAPI backend
   ═══════════════════════════════════════════ */

const API_BASE = '';

const api = {
  _token: null,
  _user: null,

  init() {
    this._token = localStorage.getItem('hb_token');
    this._user = JSON.parse(localStorage.getItem('hb_user') || 'null');
  },

  isLoggedIn() { return !!this._token; },
  getUser() { return this._user; },

  async request(method, path, body = null, isFormData = false) {
    const headers = {};
    if (!isFormData) headers['Content-Type'] = 'application/json';
    if (this._token) headers['Authorization'] = `Bearer ${this._token}`;

    const opts = { method, headers };
    if (body) {
      opts.body = isFormData ? body : JSON.stringify(body);
    }

    const res = await fetch(`${API_BASE}${path}`, opts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  // ── Auth ──
  async login(email, password) {
    const data = await this.request('POST', '/api/v1/auth/login', { email, password });
    this._token = data.access_token;
    this._user = data.user;
    localStorage.setItem('hb_token', data.access_token);
    localStorage.setItem('hb_user', JSON.stringify(data.user));
    return data;
  },

  logout() {
    this._token = null;
    this._user = null;
    localStorage.removeItem('hb_token');
    localStorage.removeItem('hb_user');
  },

  async register(email, password, full_name) {
    return this.request('POST', '/api/v1/auth/register', { email, password, full_name });
  },

  // ── Patients ──
  async searchPatients(params) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v) q.set(k, v); });
    return this.request('GET', `/api/v1/patients/search?${q}`);
  },

  async getPatient(id) {
    return this.request('GET', `/api/v1/patients/${id}`);
  },

  async getPatientChart(id) {
    return this.request('GET', `/api/v1/patients/${id}/chart`);
  },

  async getPatientRecords(patientId) {
    return this.request('GET', `/api/v1/records/patient/${patientId}`);
  },

  async createPatient(data) {
    return this.request('POST', '/api/v1/patients', data);
  },

  // ── FHIR ──
  async fhirRead(resourceType, id) {
    return this.request('GET', `/fhir/${resourceType}/${id}`);
  },

  async fhirSearch(resourceType, params) {
    const q = new URLSearchParams(params);
    return this.request('GET', `/fhir/${resourceType}?${q}`);
  },

  async fhirEverything(patientId) {
    return this.request('GET', `/fhir/Patient/${patientId}/$everything`);
  },

  // ── Consent ──
  async getConsentStatus(patientId) {
    return this.request('GET', `/api/v1/consent/status/${patientId}`);
  },

  async grantConsent(patientId, purpose, data_categories, duration_days) {
    return this.request('POST', '/api/v1/consent/grant', {
      patient_id: patientId, purpose, data_categories, duration_days
    });
  },

  async withdrawConsent(patientId, consentId) {
    return this.request('POST', '/api/v1/consent/withdraw', {
      patient_id: patientId, consent_id: consentId
    });
  },

  // ── Conversion ──
  async fhirToCcda(fhirJson) {
    return this.request('POST', '/api/v1/convert/fhir-to-ccda', { fhirBundleJson: fhirJson });
  },

  async fhirToPdf(fhirJson) {
    return this.request('POST', '/api/v1/convert/fhir-to-pdf', { fhirJson });
  },

  async ccdaToFhir(file) {
    const fd = new FormData();
    fd.append('file', file);
    return this.request('POST', '/api/v1/convert/ccda-to-fhir?validateOutput=true', fd, true);
  },

  async hl7v2ToFhir(hl7Message) {
    return this.request('POST', '/api/v1/convert/hl7v2-to-fhir', { hl7Message });
  },

  // ── Compliance ──
  async listBreaches() {
    return this.request('GET', '/api/v1/compliance/breaches');
  },

  async reportBreach(data) {
    return this.request('POST', '/api/v1/compliance/breaches', data);
  },

  async getAuditLogs() {
    return this.request('GET', '/api/v1/compliance/audit-logs');
  },

  async getErasureSchedule() {
    return this.request('GET', '/api/v1/compliance/erasure-schedule');
  },

  // ── Admin ──
  async listUsers() {
    return this.request('GET', '/api/v1/admin/users');
  },

  async getDashboardStats() {
    return this.request('GET', '/api/v1/admin/stats');
  },

  // ── Health ──
  async health() {
    return this.request('GET', '/health');
  }
};

api.init();
