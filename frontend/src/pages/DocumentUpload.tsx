import React, { useState, useCallback, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Upload,
  FileText,
  Image,
  X,
  CheckCircle,
  AlertCircle,
  Loader2,
  Search,
  ChevronDown,
  ClipboardList,
  Clock,
} from 'lucide-react';
import { ingestionApi, patientApi } from '../services/api';

const DOCUMENT_TYPES = [
  { id: 'prescription', label: 'Prescription', icon: FileText },
  { id: 'lab_report', label: 'Lab Report', icon: FileText },
  { id: 'pharmacy_bill', label: 'Pharmacy Bill', icon: FileText },
  { id: 'discharge_summary', label: 'Discharge Summary', icon: FileText },
  { id: 'vaccination_card', label: 'Vaccination Card', icon: FileText },
  { id: 'general', label: 'General Document', icon: FileText },
];

const DocumentUpload: React.FC = () => {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [documentType, setDocumentType] = useState('prescription');
  const [patientSearch, setPatientSearch] = useState('');
  const [selectedPatient, setSelectedPatient] = useState<any | null>(null);
  const [showPatientDropdown, setShowPatientDropdown] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  // Search patients
  const { data: patients, isLoading: patientsLoading } = useQuery({
    queryKey: ['patient-search', patientSearch],
    queryFn: () => patientApi.search({ firstName: patientSearch, lastName: '', mrn: '', phone: '' }),
    enabled: patientSearch.length >= 2,
  });

  // Ingestion logs
  const { data: ingestionLogs, isLoading: logsLoading } = useQuery({
    queryKey: ['ingestion-logs'],
    queryFn: () => ingestionApi.getLogs(10),
    refetchInterval: 10000,
  });

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: (formData: FormData) => ingestionApi.upload(formData),
    onSuccess: () => {
      setSelectedFile(null);
      setPreview(null);
      setSelectedPatient(null);
      queryClient.invalidateQueries({ queryKey: ['ingestion-logs'] });
      queryClient.invalidateQueries({ queryKey: ['health-stats'] });
    },
  });

  const handleFileSelect = useCallback((file: File) => {
    const validTypes = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf', 'image/tiff'];
    if (!validTypes.includes(file.type) && !file.name.match(/\.(jpg|jpeg|png|webp|tiff|tif|pdf)$/i)) {
      alert('Unsupported file type. Please upload JPEG, PNG, WebP, TIFF, or PDF files.');
      return;
    }
    setSelectedFile(file);
    if (file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = (e) => setPreview(e.target?.result as string);
      reader.readAsDataURL(file);
    } else {
      setPreview(null);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  }, [handleFileSelect]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => setDragOver(false);

  const handleUpload = () => {
    if (!selectedFile) return;
    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('document_type', documentType);
    if (selectedPatient) {
      formData.append('patient_id', selectedPatient.id);
    }
    uploadMutation.mutate(formData);
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'PROCESSED':
        return <span className="badge badge-success"><CheckCircle size={12} /> Processed</span>;
      case 'FAILED':
        return <span className="badge badge-danger"><AlertCircle size={12} /> Failed</span>;
      default:
        return <span className="badge badge-warning"><Clock size={12} /> Pending</span>;
    }
  };

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header">
        <div className="page-header-left">
          <h1 className="page-title">
            <Upload size={22} style={{ marginRight: 8, verticalAlign: 'middle' }} />
            Document Upload
          </h1>
          <p className="page-subtitle">
            Upload photos and PDFs received via WhatsApp to convert them into structured FHIR patient records.
          </p>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-2col" style={{ gap: 24, marginTop: 24 }}>
        {/* Upload Form */}
        <div className="card" style={{ padding: 24 }}>
          <h3 style={{ marginBottom: 20, fontSize: 16, fontWeight: 600, color: '#e2e8f0' }}>
            Upload Document
          </h3>

          {/* Drop Zone */}
          <div
            className={`upload-dropzone ${dragOver ? 'drag-over' : ''} ${selectedFile ? 'has-file' : ''}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => !selectedFile && fileInputRef.current?.click()}
            style={{
              border: `2px dashed ${dragOver ? '#3b82f6' : selectedFile ? '#22c55e' : '#334155'}`,
              borderRadius: 12,
              padding: 32,
              textAlign: 'center',
              cursor: selectedFile ? 'default' : 'pointer',
              transition: 'all 0.2s',
              background: dragOver ? 'rgba(59,130,246,0.08)' : selectedFile ? 'rgba(34,197,94,0.05)' : 'transparent',
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".jpg,.jpeg,.png,.webp,.tiff,.tif,.pdf"
              onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
              style={{ display: 'none' }}
            />

            {selectedFile ? (
              <div>
                {preview ? (
                  <img src={preview} alt="Preview" style={{ maxHeight: 200, maxWidth: '100%', borderRadius: 8, marginBottom: 12 }} />
                ) : (
                  <FileText size={48} color="#3b82f6" style={{ marginBottom: 12 }} />
                )}
                <p style={{ color: '#e2e8f0', fontWeight: 500, marginBottom: 4 }}>{selectedFile.name}</p>
                <p style={{ color: '#94a3b8', fontSize: 13, marginBottom: 12 }}>
                  {(selectedFile.size / 1024 / 1024).toFixed(1)} MB
                </p>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={(e) => { e.stopPropagation(); setSelectedFile(null); setPreview(null); }}
                  style={{ color: '#ef4444' }}
                >
                  <X size={16} /> Remove
                </button>
              </div>
            ) : (
              <div>
                <Upload size={48} color="#64748b" style={{ marginBottom: 12 }} />
                <p style={{ color: '#94a3b8', marginBottom: 4 }}>
                  Drop a document here, or <span style={{ color: '#3b82f6', textDecoration: 'underline' }}>browse</span>
                </p>
                <p style={{ color: '#64748b', fontSize: 12 }}>JPEG, PNG, WebP, TIFF, PDF — max 20 MB</p>
              </div>
            )}
          </div>

          {/* Document Type */}
          <div style={{ marginTop: 20 }}>
            <label className="form-label">Document Type</label>
            <div className="doc-type-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 8 }}>
              {DOCUMENT_TYPES.map((dt) => (
                <button
                  key={dt.id}
                  className={`btn ${documentType === dt.id ? 'btn-primary' : 'btn-ghost'}`}
                  onClick={() => setDocumentType(dt.id)}
                  style={{ justifyContent: 'flex-start', gap: 8, fontSize: 13 }}
                >
                  <dt.icon size={16} />
                  {dt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Patient Search */}
          <div style={{ marginTop: 20, position: 'relative' }}>
            <label className="form-label">
              Link to Patient <span style={{ color: '#64748b', fontSize: 12 }}>(optional)</span>
            </label>
            <div className="search-input-wrapper" style={{ position: 'relative', marginTop: 8 }}>
              <Search size={16} color="#64748b" style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} />
              <input
                type="text"
                className="form-input"
                placeholder="Search by patient name..."
                value={patientSearch}
                onChange={(e) => { setPatientSearch(e.target.value); setShowPatientDropdown(true); }}
                onFocus={() => setShowPatientDropdown(true)}
                style={{ paddingLeft: 36 }}
              />
              {selectedPatient && (
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => { setSelectedPatient(null); setPatientSearch(''); }}
                  style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', color: '#ef4444' }}
                >
                  <X size={14} />
                </button>
              )}
            </div>

            {selectedPatient ? (
              <div className="selected-patient" style={{ marginTop: 8, padding: '8px 12px', background: 'rgba(59,130,246,0.1)', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle size={14} color="#3b82f6" />
                <span style={{ color: '#e2e8f0', fontSize: 13 }}>
                  {selectedPatient.firstName} {selectedPatient.lastName}
                </span>
              </div>
            ) : showPatientDropdown && patientSearch.length >= 2 && (
              <div className="patient-dropdown" style={{
                position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10,
                background: '#1e293b', border: '1px solid #334155', borderRadius: 8,
                marginTop: 4, maxHeight: 200, overflowY: 'auto', boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
              }}>
                {patientsLoading ? (
                  <div style={{ padding: 16, textAlign: 'center', color: '#94a3b8' }}>
                    <Loader2 size={20} className="spin" />
                  </div>
                ) : patients?.length > 0 ? (
                  patients.map((p: any) => (
                    <div
                      key={p.id}
                      className="dropdown-item"
                      onClick={() => {
                        setSelectedPatient(p);
                        setPatientSearch(`${p.firstName} ${p.lastName}`);
                        setShowPatientDropdown(false);
                      }}
                      style={{ padding: '10px 12px', cursor: 'pointer', color: '#e2e8f0', borderBottom: '1px solid #1e293b' }}
                    >
                      <div style={{ fontWeight: 500 }}>{p.firstName} {p.lastName}</div>
                      <div style={{ fontSize: 12, color: '#64748b' }}>
                        {p.gender} · {p.dateOfBirth || 'N/A'} · {p.phone || 'No phone'}
                      </div>
                    </div>
                  ))
                ) : (
                  <div style={{ padding: 12, textAlign: 'center', color: '#64748b', fontSize: 13 }}>
                    No patients found. Upload without linking.
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Upload Button */}
          <button
            className="btn btn-primary"
            onClick={handleUpload}
            disabled={!selectedFile || uploadMutation.isPending}
            style={{ width: '100%', marginTop: 24, padding: 12, fontSize: 15, gap: 8 }}
          >
            {uploadMutation.isPending ? (
              <><Loader2 size={18} className="spin" /> Processing Document...</>
            ) : (
              <><Upload size={18} /> Upload & Process</>
            )}
          </button>

          {uploadMutation.isError && (
            <div className="alert alert-danger" style={{ marginTop: 16 }}>
              <AlertCircle size={16} />
              {uploadMutation.error?.message || 'Upload failed. Please try again.'}
            </div>
          )}

          {uploadMutation.isSuccess && (
            <div className="alert alert-success" style={{ marginTop: 16 }}>
              <CheckCircle size={16} />
              Document processed successfully! FHIR records created.
            </div>
          )}
        </div>

        {/* Recent Uploads */}
        <div className="card" style={{ padding: 24 }}>
          <h3 style={{ marginBottom: 20, fontSize: 16, fontWeight: 600, color: '#e2e8f0' }}>
            Recent Uploads
          </h3>

          {logsLoading ? (
            <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>
              <Loader2 size={24} className="spin" />
            </div>
          ) : ingestionLogs?.length > 0 ? (
            <div className="logs-list">
              {ingestionLogs.map((log: any) => (
                <div key={log.id} className="log-entry" style={{
                  padding: '12px 0',
                  borderBottom: '1px solid #1e293b',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 12,
                }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 8,
                    background: log.status === 'PROCESSED' ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  }}>
                    {log.status === 'PROCESSED' ? (
                      <CheckCircle size={18} color="#22c55e" />
                    ) : (
                      <AlertCircle size={18} color="#ef4444" />
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                      <span style={{ fontSize: 13, fontWeight: 500, color: '#e2e8f0' }}>
                        {log.original_filename || 'Unknown file'}
                      </span>
                      {getStatusBadge(log.status)}
                    </div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>
                      <span>{log.document_type}</span>
                      {log.patient_id && <span> · Patient: {log.patient_id.slice(0, 8)}...</span>}
                      <span> · {log.processing_time_ms ? `${log.processing_time_ms}ms` : ''}</span>
                    </div>
                    <div style={{ fontSize: 11, color: '#475569', marginTop: 2 }}>
                      {formatDate(log.created_at)}
                    </div>
                    {log.error_message && (
                      <div style={{ fontSize: 12, color: '#ef4444', marginTop: 4 }}>
                        {log.error_message}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>
              <ClipboardList size={32} style={{ marginBottom: 12, opacity: 0.5 }} />
              <p>No uploads yet. Start by dropping a document on the left.</p>
            </div>
          )}
        </div>
      </div>

      {/* How It Works */}
      <div className="card" style={{ padding: 24, marginTop: 24 }}>
        <h3 style={{ marginBottom: 16, fontSize: 16, fontWeight: 600, color: '#e2e8f0' }}>
          Manual Relay — How It Works
        </h3>
        <div className="steps-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
          <div className="step-card" style={{ padding: 16, background: 'rgba(59,130,246,0.05)', borderRadius: 8, border: '1px solid #1e293b' }}>
            <div className="step-number" style={{ width: 28, height: 28, borderRadius: '50%', background: '#3b82f6', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 700, fontSize: 14, marginBottom: 8 }}>1</div>
            <h4 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', marginBottom: 4 }}>Receive on WhatsApp</h4>
            <p style={{ fontSize: 13, color: '#94a3b8' }}>Patient sends photo/PDF via WhatsApp Business App (E2EE encrypted)</p>
          </div>
          <div className="step-card" style={{ padding: 16, background: 'rgba(59,130,246,0.05)', borderRadius: 8, border: '1px solid #1e293b' }}>
            <div className="step-number" style={{ width: 28, height: 28, borderRadius: '50%', background: '#3b82f6', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 700, fontSize: 14, marginBottom: 8 }}>2</div>
            <h4 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', marginBottom: 4 }}>Download & Upload</h4>
            <p style={{ fontSize: 13, color: '#94a3b8' }}>Staff downloads from phone, uploads here — select document type and patient</p>
          </div>
          <div className="step-card" style={{ padding: 16, background: 'rgba(59,130,246,0.05)', borderRadius: 8, border: '1px solid #1e293b' }}>
            <div className="step-number" style={{ width: 28, height: 28, borderRadius: '50%', background: '#3b82f6', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 700, fontSize: 14, marginBottom: 8 }}>3</div>
            <h4 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', marginBottom: 4 }}>OCR → AI → FHIR</h4>
            <p style={{ fontSize: 13, color: '#94a3b8' }}>HealthBridge extracts text, AI structures it, creates FHIR R4 records</p>
          </div>
          <div className="step-card" style={{ padding: 16, background: 'rgba(59,130,246,0.05)', borderRadius: 8, border: '1px solid #1e293b' }}>
            <div className="step-number" style={{ width: 28, height: 28, borderRadius: '50%', background: '#3b82f6', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 700, fontSize: 14, marginBottom: 8 }}>4</div>
            <h4 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', marginBottom: 4 }}>Care Agents Act</h4>
            <p style={{ fontSize: 13, color: '#94a3b8' }}>Healthcare-orchestra agents detect new data and take action (follow-ups, adherence checks)</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DocumentUpload;
