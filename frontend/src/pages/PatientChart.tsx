import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  User,
  FileText,
  Calendar,
  Pill,
  Beaker,
  Activity,
  Heart,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  ShieldCheck,
  FileDown,
  AlertCircle,
  RefreshCw,
  ArrowLeft,
  Stethoscope,
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { patientApi } from '../services/api';

type Tab = 'overview' | 'timeline' | 'medications' | 'labResults' | 'documents';

const PatientChart: React.FC = () => {
  const { patientId } = useParams<{ patientId: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    conditions: true,
    medications: true,
    vitals: true,
  });

  const { data: patient, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['patient', patientId],
    queryFn: () => patientApi.getById(patientId!),
    enabled: !!patientId,
  });

  const { data: chartData } = useQuery({
    queryKey: ['patient-chart', patientId],
    queryFn: () => patientApi.getChart(patientId!).catch(() => null),
    enabled: !!patientId,
  });

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => ({ ...prev, [section]: !prev[section] }));
  };

  const getConsentBadge = (status?: string) => {
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

  if (isLoading) {
    return (
      <div className="loading-container">
        <div className="spinner" />
        <div className="loading-text">Loading patient chart...</div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="error-state">
        <AlertCircle size={44} />
        <div className="error-state-title">Failed to load patient</div>
        <div className="error-state-text">
          {(error as any)?.message || 'Patient not found or unavailable.'}
        </div>
        <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
          <button className="btn btn-secondary" onClick={() => navigate('/patients')}>
            <ArrowLeft size={16} />
            Back to Search
          </button>
          <button className="btn btn-primary" onClick={() => refetch()}>
            <RefreshCw size={16} />
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!patient) {
    return (
      <div className="empty-state">
        <User size={48} />
        <div className="empty-state-title">Patient not found</div>
        <div className="empty-state-text">The requested patient record could not be found.</div>
        <button className="btn btn-secondary" onClick={() => navigate('/patients')}>
          <ArrowLeft size={16} />
          Back to Search
        </button>
      </div>
    );
  }

  const patientName = [patient.firstName, patient.lastName].filter(Boolean).join(' ') || 'Unknown Patient';
  const consentStatus = patient.consentStatus || patient.consent?.status || 'Unknown';
  const sources = patient.sources || chartData?.sources || [];
  const recordCounts = chartData?.recordCounts || { conditions: 0, medications: 0, observations: 0, documents: 0 };
  const conditions = chartData?.conditions || [];
  const medications = chartData?.medications || [];
  const vitalsData = chartData?.vitals || [];

  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: 'overview', label: 'Overview', icon: <User size={16} /> },
    { key: 'timeline', label: 'Timeline', icon: <Calendar size={16} /> },
    { key: 'medications', label: 'Medications', icon: <Pill size={16} /> },
    { key: 'labResults', label: 'Lab Results', icon: <Beaker size={16} /> },
    { key: 'documents', label: 'Documents', icon: <FileText size={16} /> },
  ];

  const renderOverview = () => (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 20 }}>
      <div>
        {/* Conditions */}
        <div className="expandable-section">
          <div className="expandable-header" onClick={() => toggleSection('conditions')}>
            <div className="expandable-header-left">
              {expandedSections.conditions ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              <span className="expandable-header-title">Conditions</span>
            </div>
            <span className="expandable-header-count">{conditions.length}</span>
          </div>
          {expandedSections.conditions && (
            <div className="expandable-body">
              {conditions.length === 0 ? (
                <p className="text-muted text-sm">No conditions recorded</p>
              ) : (
                conditions.map((c: any, idx: number) => (
                  <div
                    key={c.id || idx}
                    style={{
                      padding: '8px 0',
                      borderBottom: idx < conditions.length - 1 ? '1px solid var(--border)' : 'none',
                    }}
                  >
                    <div style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                      {c.code?.text || c.display || c.code || 'Unknown condition'}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 2 }}>
                      {c.onsetDateTime || c.recordedDate || ''}
                      {c.clinicalStatus ? ` — ${c.clinicalStatus}` : ''}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Medications */}
        <div className="expandable-section">
          <div className="expandable-header" onClick={() => toggleSection('medications')}>
            <div className="expandable-header-left">
              {expandedSections.medications ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              <span className="expandable-header-title">Medications</span>
            </div>
            <span className="expandable-header-count">{medications.length}</span>
          </div>
          {expandedSections.medications && (
            <div className="expandable-body">
              {medications.length === 0 ? (
                <p className="text-muted text-sm">No medications recorded</p>
              ) : (
                medications.map((m: any, idx: number) => (
                  <div
                    key={m.id || idx}
                    style={{
                      padding: '8px 0',
                      borderBottom: idx < medications.length - 1 ? '1px solid var(--border)' : 'none',
                    }}
                  >
                    <div style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                      {m.medicationCodeableConcept?.text || m.medicationReference?.display || m.code || 'Unknown medication'}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 2 }}>
                      {m.dosageInstruction?.[0]?.text || ''}
                      {m.status ? ` — ${m.status}` : ''}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Vital Signs */}
        <div className="expandable-section">
          <div className="expandable-header" onClick={() => toggleSection('vitals')}>
            <div className="expandable-header-left">
              {expandedSections.vitals ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              <span className="expandable-header-title">Vital Signs</span>
            </div>
            <span className="expandable-header-count">{vitalsData.length}</span>
          </div>
          {expandedSections.vitals && (
            <div className="expandable-body">
              {vitalsData.length === 0 ? (
                <p className="text-muted text-sm">No vital signs recorded</p>
              ) : (
                <div style={{ width: '100%', height: 220 }}>
                  <ResponsiveContainer>
                    <LineChart data={vitalsData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis dataKey="date" tick={{ fill: 'var(--muted)', fontSize: 11 }} />
                      <YAxis tick={{ fill: 'var(--muted)', fontSize: 11 }} />
                      <Tooltip
                        contentStyle={{
                          background: 'var(--card)',
                          border: '1px solid var(--border)',
                          borderRadius: '6px',
                          color: 'var(--text)',
                        }}
                      />
                      <Line
                        type="monotone"
                        dataKey="systolic"
                        stroke="#3b82f6"
                        strokeWidth={2}
                        dot={{ fill: '#3b82f6', r: 3 }}
                        name="Systolic BP"
                      />
                      <Line
                        type="monotone"
                        dataKey="diastolic"
                        stroke="#22c55e"
                        strokeWidth={2}
                        dot={{ fill: '#22c55e', r: 3 }}
                        name="Diastolic BP"
                      />
                      <Line
                        type="monotone"
                        dataKey="heartRate"
                        stroke="#f59e0b"
                        strokeWidth={2}
                        dot={{ fill: '#f59e0b', r: 3 }}
                        name="Heart Rate"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Sidebar */}
      <div>
        {/* Record Counts */}
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title" style={{ marginBottom: 12, fontSize: '0.9rem' }}>
            <FileText size={16} />
            Record Summary
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              { label: 'Conditions', count: recordCounts.conditions || conditions.length, color: 'var(--primary)' },
              { label: 'Medications', count: recordCounts.medications || medications.length, color: 'var(--success)' },
              { label: 'Observations', count: recordCounts.observations || vitalsData.length, color: 'var(--warning)' },
              { label: 'Documents', count: recordCounts.documents || 0, color: 'var(--info)' },
            ].map((item) => (
              <div
                key={item.label}
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
              >
                <span style={{ fontSize: '0.82rem', color: 'var(--muted)' }}>{item.label}</span>
                <span style={{ fontSize: '0.9rem', fontWeight: 600, color: item.color }}>{item.count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Connected Sources */}
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title" style={{ marginBottom: 12, fontSize: '0.9rem' }}>
            <Activity size={16} />
            Connected Sources
          </div>
          {sources.length === 0 ? (
            <p className="text-muted text-sm">No sources connected</p>
          ) : (
            sources.map((source: any, idx: number) => (
              <div key={idx} className="source-item">
                <div className={`source-dot ${source.online !== false ? 'online' : 'offline'}`} />
                <div>
                  <div className="source-name">{source.name || `Source ${idx + 1}`}</div>
                  <div className="source-status">
                    {source.online !== false ? 'Online' : 'Offline'}
                    {source.type ? ` · ${source.type}` : ''}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button
            className="btn btn-primary w-full"
            onClick={() => navigate(`/patients/${patientId}/vitals`)}
          >
            <Stethoscope size={16} />
            Record Vital Signs
          </button>
          <button
            className="btn btn-primary w-full"
            onClick={() => navigate(`/consent?patientId=${patientId}`)}
          >
            <ShieldCheck size={16} />
            Manage Consent
          </button>
          <button
            className="btn btn-secondary w-full"
            onClick={() => navigate(`/fhir?patientId=${patientId}`)}
          >
            <ExternalLink size={16} />
            FHIR Bundle Viewer
          </button>
          <button className="btn btn-secondary w-full" disabled data-tooltip="Coming soon">
            <FileDown size={16} />
            Export PDF
          </button>
        </div>
      </div>
    </div>
  );

  const renderTabContent = () => {
    switch (activeTab) {
      case 'overview':
        return renderOverview();
      case 'timeline':
        return (
          <div className="empty-state">
            <Calendar size={48} />
            <div className="empty-state-title">Timeline</div>
            <div className="empty-state-text">Clinical timeline view coming soon.</div>
          </div>
        );
      case 'medications':
        return (
          <div>
            {medications.length === 0 ? (
              <div className="empty-state">
                <Pill size={48} />
                <div className="empty-state-title">No Medications</div>
                <div className="empty-state-text">No medication records found for this patient.</div>
              </div>
            ) : (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>Medication</th>
                      <th>Dosage</th>
                      <th>Status</th>
                      <th>Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {medications.map((m: any, idx: number) => (
                      <tr key={m.id || idx}>
                        <td style={{ fontWeight: 500 }}>
                          {m.medicationCodeableConcept?.text || m.code || 'Unknown'}
                        </td>
                        <td>{m.dosageInstruction?.[0]?.text || '-'}</td>
                        <td>
                          <span className={`badge badge-${m.status === 'active' ? 'success' : m.status === 'stopped' ? 'danger' : 'neutral'}`}>
                            {m.status || 'Unknown'}
                          </span>
                        </td>
                        <td>{m.authoredOn || m.date || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      case 'labResults':
        return (
          <div className="empty-state">
            <Beaker size={48} />
            <div className="empty-state-title">Lab Results</div>
            <div className="empty-state-text">Lab results viewer coming soon.</div>
          </div>
        );
      case 'documents':
        return (
          <div className="empty-state">
            <FileText size={48} />
            <div className="empty-state-title">Documents</div>
            <div className="empty-state-text">Document viewer coming soon.</div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div>
      {/* Back button */}
      <button
        className="btn btn-ghost btn-sm"
        onClick={() => navigate('/patients')}
        style={{ marginBottom: 16 }}
      >
        <ArrowLeft size={16} />
        Back to Search
      </button>

      {/* Patient Header */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: '50%',
                background: 'var(--primary-light)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--primary)',
                fontWeight: 700,
                fontSize: '1.1rem',
              }}
            >
              {patientName.charAt(0).toUpperCase()}
            </div>
            <div>
              <h1 style={{ marginBottom: 2 }}>{patientName}</h1>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span className="text-muted text-sm">
                  MRN: <strong style={{ color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{patient.mrn || patient.id || '-'}</strong>
                </span>
                <span className="text-muted text-sm">
                  DOB: <strong style={{ color: 'var(--text-secondary)' }}>{patient.dob || patient.birthDate || '-'}</strong>
                </span>
                <span className="text-muted text-sm" style={{ textTransform: 'capitalize' }}>
                  Gender: <strong style={{ color: 'var(--text-secondary)' }}>{patient.gender || '-'}</strong>
                </span>
                {getConsentBadge(consentStatus)}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={`tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {tab.icon}
              {tab.label}
            </span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {renderTabContent()}
    </div>
  );
};

export default PatientChart;
