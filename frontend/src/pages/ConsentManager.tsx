import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ShieldCheck,
  ShieldOff,
  Shield,
  AlertCircle,
  RefreshCw,
  Download,
  Clock,
  Info,
  Check,
  X,
} from 'lucide-react';
import { consentApi } from '../services/api';
import { useSearchParams } from 'react-router-dom';

const DATA_CATEGORIES = [
  'Demographics',
  'Medical History',
  'Medications',
  'Lab Results',
  'Diagnostic Reports',
  'Immunizations',
  'Genomic Data',
  'Social History',
  'Financial Information',
];

const PURPOSES = [
  'Treatment',
  'Payment',
  'Healthcare Operations',
  'Research',
  'Public Health',
  'Quality Improvement',
  'Care Coordination',
];

const ConsentManager: React.FC = () => {
  const [searchParams] = useSearchParams();
  const patientIdParam = searchParams.get('patientId') || '';
  const queryClient = useQueryClient();

  const [selectedPatientId, setSelectedPatientId] = useState(patientIdParam);
  const [showGrantFlow, setShowGrantFlow] = useState(false);
  const [selectedPurpose, setSelectedPurpose] = useState('');
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [durationDays, setDurationDays] = useState(365);
  const [showWithdrawConfirm, setShowWithdrawConfirm] = useState<string | null>(null);

  const { data: consentRecords, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['consent', selectedPatientId || 'all'],
    queryFn: () =>
      selectedPatientId
        ? consentApi.getHistory(selectedPatientId)
        : consentApi.getAll(),
  });

  const { data: consentStatus } = useQuery({
    queryKey: ['consent-status', selectedPatientId],
    queryFn: () => consentApi.getStatus(selectedPatientId),
    enabled: !!selectedPatientId,
  });

  const grantMutation = useMutation({
    mutationFn: () =>
      consentApi.grant(selectedPatientId, {
        purpose: selectedPurpose,
        dataCategories: selectedCategories,
        durationDays,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['consent'] });
      setShowGrantFlow(false);
      setSelectedPurpose('');
      setSelectedCategories([]);
      setDurationDays(365);
    },
  });

  const withdrawMutation = useMutation({
    mutationFn: (consentId: string) => consentApi.withdraw(selectedPatientId, consentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['consent'] });
      setShowWithdrawConfirm(null);
    },
  });

  const toggleCategory = (cat: string) => {
    setSelectedCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
  };

  const getStatusBadge = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'active':
      case 'granted':
        return <span className="badge badge-success">{status}</span>;
      case 'pending':
        return <span className="badge badge-warning">{status}</span>;
      case 'withdrawn':
      case 'expired':
      case 'revoked':
        return <span className="badge badge-danger">{status}</span>;
      default:
        return <span className="badge badge-neutral">{status || 'Unknown'}</span>;
    }
  };

  const records = consentRecords || [];
  const status = consentStatus || { status: 'unknown' };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1>Consent Manager</h1>
        <p className="text-muted text-sm">Manage patient data consent per DPDP 2025 regulations</p>
      </div>

      {/* DPDP Notice */}
      <div className="dpdp-notice">
        <Info size={16} />
        <span>
          DPDP 2025 requires explicit, informed consent for all health data processing.
          All consent actions are logged for audit compliance.
        </span>
      </div>

      {/* Patient ID Input */}
      <div className="filter-bar">
        <div className="form-group" style={{ marginBottom: 0, flex: 1 }}>
          <label className="form-label">Patient ID</label>
          <input
            type="text"
            className="form-input"
            placeholder="Enter patient ID to manage consent"
            value={selectedPatientId}
            onChange={(e) => setSelectedPatientId(e.target.value)}
          />
        </div>
        <button className="btn btn-primary" onClick={() => refetch()} style={{ marginTop: 22 }}>
          <RefreshCw size={16} />
          Load
        </button>
      </div>

      {!selectedPatientId && (
        <div className="empty-state">
          <ShieldCheck size={48} />
          <div className="empty-state-title">Enter a Patient ID</div>
          <div className="empty-state-text">
            Enter a patient ID above to view and manage their consent preferences.
          </div>
        </div>
      )}

      {isLoading && selectedPatientId && (
        <div className="loading-container">
          <div className="spinner" />
          <div className="loading-text">Loading consent data...</div>
        </div>
      )}

      {isError && selectedPatientId && (
        <div className="error-state">
          <AlertCircle size={44} />
          <div className="error-state-title">Failed to load consent data</div>
          <div className="error-state-text">{(error as any)?.message || 'An error occurred.'}</div>
          <button className="btn btn-primary" onClick={() => refetch()}>
            <RefreshCw size={16} />
            Retry
          </button>
        </div>
      )}

      {selectedPatientId && !isLoading && !isError && (
        <>
          {/* Current Consent Status */}
          <div className="card" style={{ marginBottom: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <Shield size={24} style={{ color: status.status === 'active' || status.status === 'granted' ? 'var(--success)' : 'var(--muted)' }} />
                <div>
                  <div style={{ fontSize: '0.88rem', color: 'var(--muted)' }}>Current Consent Status</div>
                  <div style={{ fontSize: '1.2rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
                    {getStatusBadge(status.status)}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-success btn-sm" onClick={() => setShowGrantFlow(true)}>
                  <ShieldCheck size={14} />
                  Grant Consent
                </button>
                {(status.status === 'active' || status.status === 'granted') && (
                  <button className="btn btn-danger btn-sm" onClick={() => setShowWithdrawConfirm('current')}>
                    <ShieldOff size={14} />
                    Withdraw
                  </button>
                )}
              </div>
            </div>

            {status.purpose && (
              <div style={{ marginTop: 12, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Purpose: <strong>{status.purpose}</strong>
                {status.expiresAt && (
                  <span style={{ marginLeft: 16, color: 'var(--muted)' }}>
                    Expires: {new Date(status.expiresAt).toLocaleDateString()}
                  </span>
                )}
              </div>
            )}

            {status.dataCategories && status.dataCategories.length > 0 && (
              <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {status.dataCategories.map((cat: string) => (
                  <span key={cat} className="badge badge-info">{cat}</span>
                ))}
              </div>
            )}
          </div>

          {/* Grant Consent Flow */}
          {showGrantFlow && (
            <div className="card" style={{ marginBottom: 20, borderColor: 'var(--success-border)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <h3 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <ShieldCheck size={18} style={{ color: 'var(--success)' }} />
                  Grant Consent
                </h3>
                <button className="btn btn-ghost btn-sm" onClick={() => setShowGrantFlow(false)}>
                  <X size={16} />
                </button>
              </div>

              <div className="consent-flow-step">
                <div className="consent-flow-step-title">1. Select Purpose</div>
                <div className="form-row">
                  {PURPOSES.slice(0, 4).map((p) => (
                    <label key={p} className="form-checkbox" onClick={() => setSelectedPurpose(p)}>
                      <input
                        type="radio"
                        name="purpose"
                        checked={selectedPurpose === p}
                        onChange={() => {}}
                      />
                      <span>{p}</span>
                    </label>
                  ))}
                </div>
                <div className="form-row" style={{ marginTop: 8 }}>
                  {PURPOSES.slice(4).map((p) => (
                    <label key={p} className="form-checkbox" onClick={() => setSelectedPurpose(p)}>
                      <input
                        type="radio"
                        name="purpose"
                        checked={selectedPurpose === p}
                        onChange={() => {}}
                      />
                      <span>{p}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="consent-flow-step">
                <div className="consent-flow-step-title">2. Select Data Categories</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                  {DATA_CATEGORIES.map((cat) => (
                    <label key={cat} className="form-checkbox" onClick={() => toggleCategory(cat)}>
                      <input
                        type="checkbox"
                        checked={selectedCategories.includes(cat)}
                        onChange={() => {}}
                      />
                      <span style={{ fontSize: '0.82rem' }}>{cat}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="consent-flow-step">
                <div className="consent-flow-step-title">3. Duration</div>
                <div className="form-group" style={{ maxWidth: 200 }}>
                  <label className="form-label">Duration (days)</label>
                  <input
                    type="number"
                    className="form-input"
                    value={durationDays}
                    onChange={(e) => setDurationDays(Number(e.target.value))}
                    min={1}
                    max={3650}
                  />
                </div>
              </div>

              <button
                className="btn btn-success w-full"
                onClick={() => grantMutation.mutate()}
                disabled={grantMutation.isPending || !selectedPurpose || selectedCategories.length === 0}
              >
                {grantMutation.isPending ? (
                  <><div className="spinner spinner-sm" /> Granting Consent...</>
                ) : (
                  <><ShieldCheck size={16} /> Confirm & Grant Consent</>
                )}
              </button>
            </div>
          )}

          {/* Withdraw Confirm */}
          {showWithdrawConfirm && (
            <div className="alert alert-danger" style={{ marginBottom: 20 }}>
              <AlertCircle size={20} />
              <div>
                <strong>Withdraw Consent?</strong>
                <p style={{ margin: '4px 0', fontSize: '0.85rem' }}>
                  This will revoke all data sharing permissions. The patient's data will no longer be accessible.
                </p>
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <button
                    className="btn btn-danger btn-sm"
                    onClick={() => withdrawMutation.mutate(showWithdrawConfirm)}
                    disabled={withdrawMutation.isPending}
                  >
                    {withdrawMutation.isPending ? 'Withdrawing...' : 'Yes, Withdraw'}
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={() => setShowWithdrawConfirm(null)}>
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Consent History */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <Clock size={18} />
                Consent History
              </div>
              <button className="btn btn-ghost btn-sm">
                <Download size={14} />
                Download Artifact
              </button>
            </div>

            {records.length === 0 ? (
              <div className="empty-state" style={{ padding: 24 }}>
                <Clock size={32} />
                <div className="empty-state-text">No consent records found</div>
              </div>
            ) : (
              <div className="table-container" style={{ border: 'none' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Timestamp</th>
                      <th>Action</th>
                      <th>Purpose</th>
                      <th>Categories</th>
                      <th>Status</th>
                      <th>Expires</th>
                    </tr>
                  </thead>
                  <tbody>
                    {records.map((record: any, idx: number) => (
                      <tr key={record.id || idx}>
                        <td style={{ fontSize: '0.8rem' }}>
                          {record.timestamp ? new Date(record.timestamp).toLocaleString() : '-'}
                        </td>
                        <td style={{ textTransform: 'capitalize', fontWeight: 500 }}>
                          {record.action || record.type || '-'}
                        </td>
                        <td>{record.purpose || '-'}</td>
                        <td>
                          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            {(record.dataCategories || record.categories || []).slice(0, 3).map((c: string) => (
                              <span key={c} className="badge badge-neutral" style={{ fontSize: '0.65rem' }}>
                                {c}
                              </span>
                            ))}
                            {(record.dataCategories?.length || 0) > 3 && (
                              <span className="badge badge-neutral" style={{ fontSize: '0.65rem' }}>
                                +{record.dataCategories.length - 3}
                              </span>
                            )}
                          </div>
                        </td>
                        <td>{getStatusBadge(record.status)}</td>
                        <td style={{ fontSize: '0.8rem' }}>
                          {record.expiresAt ? new Date(record.expiresAt).toLocaleDateString() : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default ConsentManager;
