import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { opdApi } from '../services/api';

interface PatientSearchResult {
  source: 'patient' | 'opd_registration';
  id: string;
  mrn?: string;
  uhid?: string;
  name: string;
  age?: number;
  gender?: string;
  phone?: string;
  last_visit?: string;
}

interface OPDRegisterResponse {
  registration_id: string;
  uhid: string;
  token_number: number;
  estimated_wait_minutes: number;
  patient_name: string;
  registration_date: string;
}

interface TokenQueueItem {
  id: string;
  uhid: string;
  token_number: number;
  patient_name: string;
  age?: number;
  gender?: string;
  status: string;
  doctor_id?: string;
  room?: string;
  chief_complaint?: string;
  called_at?: string;
  started_at?: string;
  estimated_wait_minutes: number;
}

interface QueueStatusResponse {
  tokens: TokenQueueItem[];
  total_waiting: number;
  total_in_progress: number;
  current_token?: number;
  next_token?: number;
}

const OPDRegister: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState({ phone: '', uhid: '', first_name: '', last_name: '' });
  const [searchResults, setSearchResults] = useState<PatientSearchResult[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<PatientSearchResult | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [showNewPatientForm, setShowNewPatientForm] = useState(false);
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    age: '',
    gender: 'UNKNOWN',
    phone: '',
    address: '',
    emergency_contact_name: '',
    emergency_contact_phone: '',
    chief_complaint: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [registrationResult, setRegistrationResult] = useState<OPDRegisterResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const searchPatients = async () => {
    if (!searchQuery.phone && !searchQuery.uhid && !searchQuery.first_name && !searchQuery.last_name) {
      setError('Please enter at least one search field');
      return;
    }
    setIsSearching(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (searchQuery.phone) params.append('phone', searchQuery.phone);
      if (searchQuery.uhid) params.append('uhid', searchQuery.uhid);
      if (searchQuery.first_name) params.append('first_name', searchQuery.first_name);
      if (searchQuery.last_name) params.append('last_name', searchQuery.last_name);
      const data = await opdApi.search({
        phone: searchQuery.phone || undefined,
        uhid: searchQuery.uhid || undefined,
        first_name: searchQuery.first_name || undefined,
        last_name: searchQuery.last_name || undefined,
      });
      if (data.length === 1) {
        setSelectedPatient(data[0]);
        setShowNewPatientForm(false);
        // Pre-fill form
        if (data[0].source === 'patient') {
          const [first, last] = data[0].name.split(' ');
          setFormData(prev => ({
            ...prev,
            first_name: first || '',
            last_name: last || '',
            age: data[0].age?.toString() || '',
            gender: data[0].gender || 'UNKNOWN',
            phone: data[0].phone || '',
          }));
        } else if (data[0].source === 'opd_registration') {
          const [first, last] = data[0].name.split(' ');
          setFormData(prev => ({
            ...prev,
            first_name: first || '',
            last_name: last || '',
            age: data[0].age?.toString() || '',
            gender: data[0].gender || 'UNKNOWN',
            phone: data[0].phone || '',
          }));
        }
      } else if (data.length > 1) {
        setSelectedPatient(null);
        setShowNewPatientForm(false);
      } else {
        setSelectedPatient(null);
        setShowNewPatientForm(true);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Search failed');
    } finally {
      setIsSearching(false);
    }
  };

  const registerMutation = useMutation({
    mutationFn: (data: any) => opdApi.register(data),
    onSuccess: (data) => {
      setRegistrationResult(data);
      setFormData({
        first_name: '',
        last_name: '',
        age: '',
        gender: 'UNKNOWN',
        phone: '',
        address: '',
        emergency_contact_name: '',
        emergency_contact_phone: '',
        chief_complaint: '',
      });
      setSearchQuery({ phone: '', uhid: '', first_name: '', last_name: '' });
      setSearchResults([]);
      setSelectedPatient(null);
      setShowNewPatientForm(false);
      queryClient.invalidateQueries({ queryKey: ['opd-queue'] });
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Registration failed');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const payload = {
      ...formData,
      age: formData.age ? parseInt(formData.age) : undefined,
      existing_patient_id: selectedPatient?.source === 'patient' ? selectedPatient.id : undefined,
    };
    registerMutation.mutate(payload);
  };

  const handlePrintToken = () => {
    window.print();
  };

  return (
    <div className="opd-register page-container">
      <div className="page-header">
        <h1>OPD Registration Desk</h1>
        <p>Register patients and assign tokens</p>
      </div>

      {registrationResult && (
        <div className="registration-success print-only-hidden">
          <div className="token-slip">
            <div className="token-header">
              <h2>HealthBridge Clinic</h2>
              <span className="token-label">OPD TOKEN</span>
            </div>
            <div className="token-body">
              <div className="token-row">
                <span className="token-field">UHID</span>
                <span className="token-value">{registrationResult.uhid}</span>
              </div>
              <div className="token-row">
                <span className="token-field">Token #</span>
                <span className="token-value token-large">{registrationResult.token_number}</span>
              </div>
              <div className="token-row">
                <span className="token-field">Patient</span>
                <span className="token-value">{registrationResult.patient_name}</span>
              </div>
              <div className="token-row">
                <span className="token-field">Date</span>
                <span className="token-value">{new Date(registrationResult.registration_date).toLocaleDateString()}</span>
              </div>
              <div className="token-row">
                <span className="token-field">Est. Wait</span>
                <span className="token-value">{registrationResult.estimated_wait_minutes} min</span>
              </div>
            </div>
            <div className="token-footer">
              <p>Please wait for your token to be called</p>
            </div>
          </div>
          <button onClick={handlePrintToken} className="btn btn-primary print-btn">
            Print Token Slip
          </button>
        </div>
      )}

      <div className="register-layout">
        {/* Search Panel */}
        <div className="panel search-panel">
          <h3>Search Existing Patient</h3>
          <div className="search-form">
            <div className="form-row">
              <input
                type="text"
                placeholder="Phone Number"
                value={searchQuery.phone}
                onChange={(e) => setSearchQuery(prev => ({ ...prev, phone: e.target.value }))}
                className="form-input"
              />
              <input
                type="text"
                placeholder="UHID"
                value={searchQuery.uhid}
                onChange={(e) => setSearchQuery(prev => ({ ...prev, uhid: e.target.value }))}
                className="form-input"
              />
            </div>
            <div className="form-row">
              <input
                type="text"
                placeholder="First Name"
                value={searchQuery.first_name}
                onChange={(e) => setSearchQuery(prev => ({ ...prev, first_name: e.target.value }))}
                className="form-input"
              />
              <input
                type="text"
                placeholder="Last Name"
                value={searchQuery.last_name}
                onChange={(e) => setSearchQuery(prev => ({ ...prev, last_name: e.target.value }))}
                className="form-input"
              />
            </div>
            <button
              onClick={searchPatients}
              disabled={isSearching}
              className="btn btn-secondary search-btn"
            >
              {isSearching ? 'Searching...' : 'Search'}
            </button>
          </div>

          {error && <div className="error-message">{error}</div>}

          {searchResults.length > 0 && (
            <div className="search-results">
              <h4>Search Results ({searchResults.length})</h4>
              {searchResults.map((patient) => (
                <div
                  key={patient.id}
                  className={`result-item ${selectedPatient?.id === patient.id ? 'selected' : ''}`}
                  onClick={() => setSelectedPatient(patient)}
                >
                  <div className="result-info">
                    <span className="result-name">{patient.name}</span>
                    <span className="result-meta">
                      {patient.age ? `${patient.age}y ` : ''}
                      {patient.gender ? `${patient.gender} ` : ''}
                      {patient.phone ? `📞 ${patient.phone}` : ''}
                    </span>
                    {patient.uhid && <span className="result-uhid">UHID: {patient.uhid}</span>}
                    {patient.mrn && <span className="result-mrn">MRN: {patient.mrn}</span>}
                  </div>
                  <span className="result-source">{patient.source === 'patient' ? 'Patient Record' : 'Previous Visit'}</span>
                </div>
              ))}
            </div>
          )}

          {selectedPatient && (
            <div className="selected-patient">
              <h4>Selected: {selectedPatient.name}</h4>
              <p>Review details and register for today's visit</p>
            </div>
          )}
        </div>

        {/* Registration Form Panel */}
        <div className="panel form-panel">
          <h3>{selectedPatient ? 'Register for Visit' : 'New Patient Registration'}</h3>
          <form onSubmit={handleSubmit} className="registration-form">
            <div className="form-row">
              <div className="form-group">
                <label>First Name *</label>
                <input
                  type="text"
                  value={formData.first_name}
                  onChange={(e) => setFormData(prev => ({ ...prev, first_name: e.target.value }))}
                  required
                  className="form-input"
                />
              </div>
              <div className="form-group">
                <label>Last Name *</label>
                <input
                  type="text"
                  value={formData.last_name}
                  onChange={(e) => setFormData(prev => ({ ...prev, last_name: e.target.value }))}
                  required
                  className="form-input"
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Age</label>
                <input
                  type="number"
                  value={formData.age}
                  onChange={(e) => setFormData(prev => ({ ...prev, age: e.target.value }))}
                  min="0"
                  max="120"
                  className="form-input"
                />
              </div>
              <div className="form-group">
                <label>Gender</label>
                <select
                  value={formData.gender}
                  onChange={(e) => setFormData(prev => ({ ...prev, gender: e.target.value }))}
                  className="form-input"
                >
                  <option value="MALE">Male</option>
                  <option value="FEMALE">Female</option>
                  <option value="OTHER">Other</option>
                  <option value="UNKNOWN">Unknown</option>
                </select>
              </div>
            </div>

            <div className="form-group">
              <label>Phone</label>
              <input
                type="tel"
                value={formData.phone}
                onChange={(e) => setFormData(prev => ({ ...prev, phone: e.target.value }))}
                className="form-input"
              />
            </div>

            <div className="form-group">
              <label>Address</label>
              <textarea
                value={formData.address}
                onChange={(e) => setFormData(prev => ({ ...prev, address: e.target.value }))}
                rows={2}
                className="form-input"
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Emergency Contact Name</label>
                <input
                  type="text"
                  value={formData.emergency_contact_name}
                  onChange={(e) => setFormData(prev => ({ ...prev, emergency_contact_name: e.target.value }))}
                  className="form-input"
                />
              </div>
              <div className="form-group">
                <label>Emergency Contact Phone</label>
                <input
                  type="tel"
                  value={formData.emergency_contact_phone}
                  onChange={(e) => setFormData(prev => ({ ...prev, emergency_contact_phone: e.target.value }))}
                  className="form-input"
                />
              </div>
            </div>

            <div className="form-group">
              <label>Chief Complaint</label>
              <textarea
                value={formData.chief_complaint}
                onChange={(e) => setFormData(prev => ({ ...prev, chief_complaint: e.target.value }))}
                rows={2}
                placeholder="Reason for visit..."
                className="form-input"
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting || registerMutation.isPending}
              className="btn btn-primary submit-btn"
            >
              {registerMutation.isPending ? 'Registering...' : 'Register & Generate Token'}
            </button>
          </form>
        </div>
      </div>

      <style jsx>{`
        .page-container { padding: 24px; max-width: 1400px; margin: 0 auto; }
        .page-header { margin-bottom: 24px; }
        .page-header h1 { margin: 0 0 8px; color: #1e293b; }
        .page-header p { margin: 0; color: #64748b; }
        .register-layout { display: grid; grid-template-columns: 400px 1fr; gap: 24px; }
        .panel { background: white; border-radius: 12px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .panel h3 { margin: 0 0 16px; color: #1e293b; font-size: 16px; }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        .form-group { display: flex; flex-direction: column; gap: 6px; }
        .form-group label { font-size: 13px; font-weight: 500; color: #475569; }
        .form-input { padding: 10px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 14px; }
        .form-input:focus { outline: none; border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }
        .search-form { display: flex; flex-direction: column; gap: 12px; }
        .search-btn { margin-top: 8px; }
        .search-results { margin-top: 16px; }
        .search-results h4 { margin: 0 0 12px; font-size: 14px; color: #475569; }
        .result-item { padding: 12px; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 8px; cursor: pointer; transition: all 0.2s; display: flex; justify-content: space-between; align-items: center; }
        .result-item:hover { border-color: #3b82f6; background: #f8fafc; }
        .result-item.selected { border-color: #3b82f6; background: #eff6ff; }
        .result-info { display: flex; flex-direction: column; gap: 4px; }
        .result-name { font-weight: 500; color: #1e293b; }
        .result-meta { font-size: 12px; color: #64748b; }
        .result-uhid { font-size: 11px; color: #3b82f6; font-weight: 500; }
        .result-mrn { font-size: 11px; color: #64748b; }
        .result-source { font-size: 11px; color: #94a3b8; background: #f1f5f9; padding: 4px 8px; border-radius: 4px; }
        .selected-patient { margin-top: 16px; padding: 12px; background: #f0fdf4; border-radius: 8px; border: 1px solid #bbf7d0; }
        .selected-patient h4 { margin: 0 0 4px; color: #166534; }
        .selected-patient p { margin: 0; font-size: 13px; color: #15803d; }
        .registration-form { display: flex; flex-direction: column; gap: 16px; }
        .submit-btn { margin-top: 8px; padding: 14px; font-size: 15px; font-weight: 600; }
        .registration-success { margin-top: 24px; animation: slideIn 0.3s ease; }
        @keyframes slideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .token-slip { background: white; border: 2px dashed #3b82f6; border-radius: 12px; padding: 24px; max-width: 320px; }
        .token-header { text-align: center; margin-bottom: 20px; }
        .token-header h2 { margin: 0 0 4px; color: #1e293b; }
        .token-label { background: #3b82f6; color: white; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .token-body { display: flex; flex-direction: column; gap: 12px; }
        .token-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #e2e8f0; }
        .token-field { color: #64748b; font-size: 14px; }
        .token-value { font-weight: 600; color: #1e293b; font-size: 14px; }
        .token-value.token-large { font-size: 32px; color: #3b82f6; font-family: monospace; }
        .token-footer { text-align: center; margin-top: 16px; padding-top: 16px; border-top: 1px solid #e2e8f0; }
        .token-footer p { margin: 0; color: #64748b; font-size: 13px; }
        .print-btn { width: 100%; margin-top: 16px; }
        .print-only-hidden { display: block; }
        @media print {
          .print-only-hidden { display: none !important; }
          .page-container { padding: 0; }
          .panel { box-shadow: none; border: none; padding: 0; }
          .token-slip { border: 2px solid #3b82f6; }
        }
        .error-message { color: #ef4444; font-size: 13px; margin-top: 8px; }
        .btn { padding: 10px 16px; border-radius: 8px; border: none; cursor: pointer; font-weight: 500; transition: all 0.2s; }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .btn-primary { background: #3b82f6; color: white; }
        .btn-primary:hover:not(:disabled) { background: #2563eb; }
        .btn-secondary { background: #f1f5f9; color: #475569; }
        .btn-secondary:hover:not(:disabled) { background: #e2e8f0; }
      `}</style>
    </div>
  );
};

export default OPDRegister;