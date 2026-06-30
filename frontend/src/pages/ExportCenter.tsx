import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Download,
  Upload,
  Database,
  FileText,
  Calendar,
  Clock,
  RefreshCw,
  Check,
  X,
  AlertTriangle,
  Link as LinkIcon,
  Unlink,
  Activity,
  Settings as SettingsIcon,
  Server,
  Plus,
  Trash2,
  TestTube,
  Loader,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Copy,
  FileJson,
  FileSpreadsheet,
  List,
} from 'lucide-react';
import { exportApi, connectorApi } from '../services/api';

const CONNECTOR_TYPE_INFO: Record<string, { label: string; icon: string; fields: { key: string; label: string; type: string; required: boolean }[] }> = {
  abdm: {
    label: 'ABDM (Ayushman Bharat)',
    icon: '🏛️',
    fields: [
      { key: 'client_id', label: 'Client ID', type: 'text', required: true },
      { key: 'client_secret', label: 'Client Secret', type: 'password', required: true },
      { key: 'base_url', label: 'API Base URL', type: 'text', required: false },
    ],
  },
  openmrs: {
    label: 'OpenMRS',
    icon: '🩺',
    fields: [
      { key: 'base_url', label: 'OpenMRS Base URL', type: 'text', required: true },
      { key: 'username', label: 'Username', type: 'text', required: true },
      { key: 'password', label: 'Password', type: 'password', required: true },
    ],
  },
  fhir: {
    label: 'Generic FHIR R4',
    icon: '🔗',
    fields: [
      { key: 'fhir_base_url', label: 'FHIR Server Base URL', type: 'text', required: true },
      { key: 'auth_token', label: 'Bearer Token (optional)', type: 'password', required: false },
      { key: 'extra_headers', label: 'Extra Headers (JSON, optional)', type: 'text', required: false },
    ],
  },
};

const ExportCenter: React.FC = () => {
  const queryClient = useQueryClient();

  // ── Tab state ──
  const [activeTab, setActiveTab] = useState<'exports' | 'connectors'>('exports');

  // ── Export states ──
  const [exportFilter, setExportFilter] = useState<'all' | 'patients' | 'audit' | 'compliance'>('all');
  const [dateRangeStart, setDateRangeStart] = useState('');
  const [dateRangeEnd, setDateRangeEnd] = useState('');
  const [patientId, setPatientId] = useState('');
  const [exportPatientFormat, setExportPatientFormat] = useState<'json' | 'fhir'>('json');
  const [downloadStatus, setDownloadStatus] = useState<string | null>(null);
  const [scheduleCron, setScheduleCron] = useState('0 2 * * *');
  const [scheduleFormat, setScheduleFormat] = useState('csv');
  const [scheduleScope, setScheduleScope] = useState('all');
  const [scheduleStatus, setScheduleStatus] = useState<string | null>(null);

  // ── Connector states ──
  const [showAddConnector, setShowAddConnector] = useState(false);
  const [connectorType, setConnectorType] = useState('fhir');
  const [connectorName, setConnectorName] = useState('');
  const [connectorConfig, setConnectorConfig] = useState<Record<string, string>>({});
  const [connectorError, setConnectorError] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);

  // ── Queries ──
  const { data: exportHistory, isLoading: histLoading, refetch: refetchHistory } = useQuery({
    queryKey: ['export-history'],
    queryFn: () => exportApi.getHistory().catch(() => []),
  });

  const { data: connectorTypes } = useQuery({
    queryKey: ['connector-types'],
    queryFn: () => connectorApi.getTypes().catch(() => []),
  });

  const { data: connectors, isLoading: connLoading, refetch: refetchConnectors } = useQuery({
    queryKey: ['connectors'],
    queryFn: () => connectorApi.list().catch(() => []),
  });

  // ── Download helper ──
  const triggerDownload = (blob: Blob, filename: string) => {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  };

  // ── Export handlers ──
  const handleDownloadPatientsCsv = async () => {
    setDownloadStatus('Downloading patients CSV...');
    try {
      const blob = await exportApi.downloadPatientsCsv();
      triggerDownload(blob, `patients-export-${new Date().toISOString().slice(0, 10)}.csv`);
      setDownloadStatus('Patients CSV downloaded successfully');
      refetchHistory();
    } catch (e: any) {
      setDownloadStatus(`Error: ${e.message}`);
    }
    setTimeout(() => setDownloadStatus(null), 3000);
  };

  const handleExportPatientFhir = async () => {
    if (!patientId.trim()) return;
    setDownloadStatus('Exporting patient FHIR bundle...');
    try {
      const bundle = await exportApi.getPatientFhirBundle(patientId.trim());
      const jsonStr = JSON.stringify(bundle, null, 2);
      const blob = new Blob([jsonStr], { type: 'application/json' });
      triggerDownload(blob, `patient-${patientId}-fhir-bundle.json`);
      setDownloadStatus('FHIR bundle exported successfully');
      refetchHistory();
    } catch (e: any) {
      setDownloadStatus(`Error: ${e.message}`);
    }
    setTimeout(() => setDownloadStatus(null), 3000);
  };

  const handleDownloadAuditLogs = async () => {
    setDownloadStatus('Downloading audit logs...');
    try {
      const blob = await exportApi.downloadAuditLogs(dateRangeStart || undefined, dateRangeEnd || undefined);
      triggerDownload(blob, `audit-logs-${new Date().toISOString().slice(0, 10)}.csv`);
      setDownloadStatus('Audit logs downloaded');
      refetchHistory();
    } catch (e: any) {
      setDownloadStatus(`Error: ${e.message}`);
    }
    setTimeout(() => setDownloadStatus(null), 3000);
  };

  const handleDownloadComplianceReport = async () => {
    setDownloadStatus('Downloading compliance report...');
    try {
      const report = await exportApi.getComplianceReport();
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
      triggerDownload(blob, `compliance-report-${new Date().toISOString().slice(0, 10)}.json`);
      setDownloadStatus('Compliance report downloaded');
      refetchHistory();
    } catch (e: any) {
      setDownloadStatus(`Error: ${e.message}`);
    }
    setTimeout(() => setDownloadStatus(null), 3000);
  };

  const handleScheduleExport = async () => {
    setScheduleStatus('Scheduling...');
    try {
      const result = await exportApi.scheduleExport({
        cronExpression: scheduleCron,
        format: scheduleFormat,
        scope: scheduleScope,
      });
      setScheduleStatus(`Scheduled! ID: ${result.id}`);
      refetchHistory();
    } catch (e: any) {
      setScheduleStatus(`Error: ${e.message}`);
    }
    setTimeout(() => setScheduleStatus(null), 4000);
  };

  // ── Connector handlers ──
  const handleConnectorTypeChange = (type: string) => {
    setConnectorType(type);
    setConnectorConfig({});
  };

  const handleConnectorFieldChange = (key: string, value: string) => {
    setConnectorConfig((prev) => ({ ...prev, [key]: value }));
  };

  const handleRegisterConnector = async () => {
    setConnectorError('');
    if (!connectorName.trim()) {
      setConnectorError('Connector name is required');
      return;
    }
    const typeInfo = CONNECTOR_TYPE_INFO[connectorType];
    const missing = typeInfo.fields.filter((f) => f.required && !connectorConfig[f.key]);
    if (missing.length > 0) {
      setConnectorError(`Required fields: ${missing.map((f) => f.label).join(', ')}`);
      return;
    }

    setConnecting(true);
    try {
      await connectorApi.register({
        type: connectorType,
        name: connectorName.trim(),
        config: connectorConfig,
      });
      setShowAddConnector(false);
      setConnectorName('');
      setConnectorConfig({});
      refetchConnectors();
    } catch (e: any) {
      setConnectorError(e.message);
    }
    setConnecting(false);
  };

  const handleTestConnector = async (id: string) => {
    setTestingId(id);
    try {
      await connectorApi.test(id);
      refetchConnectors();
    } catch (e: any) {
      // Error handled in status
    }
    setTestingId(null);
  };

  const handleSyncConnector = async (id: string) => {
    setSyncingId(id);
    try {
      await connectorApi.sync(id);
      refetchConnectors();
    } catch (e: any) {
      // Error handled in status
    }
    setSyncingId(null);
  };

  const handleRemoveConnector = async (id: string) => {
    if (!window.confirm('Remove this EHR connector? This cannot be undone.')) return;
    try {
      await connectorApi.remove(id);
      refetchConnectors();
    } catch (e: any) {
      console.error(e);
    }
  };

  const formatDate = (ts: string | null) => {
    if (!ts) return 'Never';
    return new Date(ts).toLocaleString();
  };

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1>Export Center</h1>
        <p className="text-muted text-sm">
          Export patient data, audit logs, and compliance reports. Manage EHR system connectors.
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="tabs" style={{ marginBottom: 24 }}>
        <button
          className={`tab ${activeTab === 'exports' ? 'active' : ''}`}
          onClick={() => setActiveTab('exports')}
        >
          <Download size={16} />
          Data Exports
        </button>
        <button
          className={`tab ${activeTab === 'connectors' ? 'active' : ''}`}
          onClick={() => setActiveTab('connectors')}
        >
          <Server size={16} />
          EHR Connectors
        </button>
      </div>

      {/* ────────────────────────────────────── */}
      {/* TAB: Exports                           */}
      {/* ────────────────────────────────────── */}
      {activeTab === 'exports' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Quick Export Buttons */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <Download size={18} />
                Quick Exports
              </div>
            </div>
            <div className="grid-3" style={{ gap: 12, padding: '4px 0' }}>
              <button className="btn btn-secondary" onClick={handleDownloadPatientsCsv} style={{ justifyContent: 'flex-start' }}>
                <FileSpreadsheet size={18} />
                Patients CSV
              </button>
              <button className="btn btn-secondary" onClick={handleDownloadAuditLogs} style={{ justifyContent: 'flex-start' }}>
                <FileText size={18} />
                Audit Logs CSV
              </button>
              <button className="btn btn-secondary" onClick={handleDownloadComplianceReport} style={{ justifyContent: 'flex-start' }}>
                <FileJson size={18} />
                Compliance Report
              </button>
            </div>
            {downloadStatus && (
              <div style={{ marginTop: 8, fontSize: '0.82rem', color: downloadStatus.startsWith('Error') ? 'var(--danger)' : 'var(--success)' }}>
                {downloadStatus.startsWith('Error') ? <AlertTriangle size={14} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} /> : <Check size={14} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />}
                {downloadStatus}
              </div>
            )}
          </div>

          {/* Patient FHIR Export */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <FileJson size={18} />
                Patient FHIR Bundle Export
              </div>
            </div>
            <p className="text-muted text-sm" style={{ marginBottom: 12 }}>
              Export a single patient's data as a FHIR R4 Bundle (Patient + all clinical records).
            </p>
            <div className="form-row">
              <div className="form-group" style={{ flex: 2 }}>
                <label className="form-label">Patient ID</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Enter patient UUID..."
                  value={patientId}
                  onChange={(e) => setPatientId(e.target.value)}
                />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label className="form-label">Export Format</label>
                <select className="form-select" value={exportPatientFormat} onChange={(e) => setExportPatientFormat(e.target.value as any)}>
                  <option value="json">JSON (FHIR Bundle)</option>
                  <option value="fhir">FHIR JSON</option>
                </select>
              </div>
            </div>
            <button className="btn btn-primary" onClick={handleExportPatientFhir} disabled={!patientId.trim()}>
              <Download size={16} />
              Export FHIR Bundle
            </button>
          </div>

          {/* Audit Log Export */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <Calendar size={18} />
                Audit Log Export
              </div>
            </div>
            <p className="text-muted text-sm" style={{ marginBottom: 12 }}>
              Filter audit logs by date range and download as CSV (DPDP 2025 compliant).
            </p>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Start Date</label>
                <input
                  type="date"
                  className="form-input"
                  value={dateRangeStart}
                  onChange={(e) => setDateRangeStart(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label className="form-label">End Date</label>
                <input
                  type="date"
                  className="form-input"
                  value={dateRangeEnd}
                  onChange={(e) => setDateRangeEnd(e.target.value)}
                />
              </div>
            </div>
            <button className="btn btn-primary" onClick={handleDownloadAuditLogs}>
              <Download size={16} />
              Download Audit Logs CSV
            </button>
          </div>

          {/* Scheduled Exports */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <Clock size={18} />
                Scheduled Exports (Cron)
              </div>
            </div>
            <p className="text-muted text-sm" style={{ marginBottom: 12 }}>
              Schedule recurring data exports using cron expressions.
            </p>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Cron Expression</label>
                <input
                  type="text"
                  className="form-input"
                  value={scheduleCron}
                  onChange={(e) => setScheduleCron(e.target.value)}
                  placeholder="0 2 * * *"
                />
                <span className="text-muted" style={{ fontSize: '0.72rem', marginTop: 2, display: 'block' }}>
                  Examples: 0 2 * * * (daily 2AM), 0 */6 * * * (every 6h)
                </span>
              </div>
              <div className="form-group">
                <label className="form-label">Format</label>
                <select className="form-select" value={scheduleFormat} onChange={(e) => setScheduleFormat(e.target.value)}>
                  <option value="csv">CSV</option>
                  <option value="json">JSON</option>
                  <option value="fhir">FHIR Bundle</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Scope</label>
                <select className="form-select" value={scheduleScope} onChange={(e) => setScheduleScope(e.target.value)}>
                  <option value="all">All Patients</option>
                  <option value="audit">Audit Logs</option>
                  <option value="compliance">Compliance Report</option>
                </select>
              </div>
            </div>
            <button className="btn btn-primary" onClick={handleScheduleExport}>
              <Clock size={16} />
              Schedule Export
            </button>
            {scheduleStatus && (
              <div style={{ marginTop: 8, fontSize: '0.82rem', color: scheduleStatus.startsWith('Error') ? 'var(--danger)' : 'var(--success)' }}>
                {scheduleStatus}
              </div>
            )}
          </div>

          {/* Export History */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <List size={18} />
                Export History
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => refetchHistory()}>
                <RefreshCw size={14} />
              </button>
            </div>
            {histLoading ? (
              <div className="loading-container">
                <div className="spinner spinner-sm" />
              </div>
            ) : !exportHistory || exportHistory.length === 0 ? (
              <div className="empty-state" style={{ padding: '24px' }}>
                <List size={32} />
                <div className="empty-state-text">No exports yet</div>
              </div>
            ) : (
              <div>
                {exportHistory.slice().reverse().map((exp: any, idx: number) => (
                  <div
                    key={exp.id || idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      padding: '10px 0',
                      borderBottom: idx < exportHistory.length - 1 ? '1px solid var(--border)' : 'none',
                    }}
                  >
                    <div
                      style={{
                        width: 8, height: 8, borderRadius: '50%',
                        background: exp.status === 'completed' ? 'var(--success)' : exp.status === 'failed' ? 'var(--danger)' : 'var(--warning)',
                        flexShrink: 0,
                      }}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: '0.85rem', fontWeight: 500 }}>
                        {exp.type || exp.scope || 'Export'}
                        <span className="badge" style={{ marginLeft: 8, fontSize: '0.7rem' }}>{exp.format || 'json'}</span>
                      </div>
                      <div className="text-muted" style={{ fontSize: '0.75rem', marginTop: 2 }}>
                        {exp.description || `${exp.scope || 'data'} export`} — {exp.record_count || 0} records — {formatDate(exp.timestamp || exp.created_at)}
                      </div>
                    </div>
                    {exp.status && (
                      <span className={`badge ${exp.status === 'completed' ? 'badge-success' : exp.status === 'failed' ? 'badge-danger' : 'badge-warning'}`}>
                        {exp.status}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ────────────────────────────────────── */}
      {/* TAB: EHR Connectors                    */}
      {/* ────────────────────────────────────── */}
      {activeTab === 'connectors' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Add Connector */}
          {!showAddConnector ? (
            <button className="btn btn-primary" onClick={() => setShowAddConnector(true)} style={{ width: 'fit-content' }}>
              <Plus size={16} />
              Add EHR Connector
            </button>
          ) : (
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <Plus size={18} />
                  Register New EHR Connector
                </div>
                <button className="btn btn-ghost btn-sm" onClick={() => { setShowAddConnector(false); setConnectorError(''); }}>
                  <X size={16} />
                </button>
              </div>

              <div className="form-group">
                <label className="form-label">Connector Type</label>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {Object.entries(CONNECTOR_TYPE_INFO).map(([key, info]) => (
                    <button
                      key={key}
                      className={`btn ${connectorType === key ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => handleConnectorTypeChange(key)}
                      style={{ fontSize: '0.82rem' }}
                    >
                      {info.icon} {info.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Connector Name</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g., Hospital A - OpenMRS"
                  value={connectorName}
                  onChange={(e) => setConnectorName(e.target.value)}
                />
              </div>

              {CONNECTOR_TYPE_INFO[connectorType]?.fields.map((field) => (
                <div className="form-group" key={field.key}>
                  <label className="form-label">
                    {field.label}
                    {field.required && <span style={{ color: 'var(--danger)', marginLeft: 2 }}>*</span>}
                  </label>
                  <input
                    type={field.type}
                    className="form-input"
                    placeholder={`Enter ${field.label}`}
                    value={connectorConfig[field.key] || ''}
                    onChange={(e) => handleConnectorFieldChange(field.key, e.target.value)}
                  />
                </div>
              ))}

              {connectorError && (
                <div className="form-error" style={{ marginBottom: 12 }}>{connectorError}</div>
              )}

              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button className="btn btn-secondary" onClick={() => { setShowAddConnector(false); setConnectorError(''); }}>
                  Cancel
                </button>
                <button className="btn btn-primary" onClick={handleRegisterConnector} disabled={connecting}>
                  {connecting ? <><Loader size={16} className="spin" /> Connecting...</> : <><LinkIcon size={16} /> Register</>}
                </button>
              </div>
            </div>
          )}

          {/* Connector List */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <Server size={18} />
                Registered EHR Connectors
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => refetchConnectors()}>
                <RefreshCw size={14} />
              </button>
            </div>

            {connLoading ? (
              <div className="loading-container">
                <div className="spinner spinner-sm" />
              </div>
            ) : !connectors || connectors.length === 0 ? (
              <div className="empty-state" style={{ padding: '24px' }}>
                <Unlink size={32} />
                <div className="empty-state-text">No EHR connectors registered</div>
                <div className="empty-state-subtext">
                  Add a connector to sync patient data from external EHR systems
                </div>
              </div>
            ) : (
              <div>
                {connectors.map((conn: any, idx: number) => {
                  const typeInfo = CONNECTOR_TYPE_INFO[conn.type] || { label: conn.type, icon: '🔌' };
                  return (
                    <div
                      key={conn.id || idx}
                      style={{
                        padding: '16px',
                        marginBottom: idx < connectors.length - 1 ? 8 : 0,
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-md)',
                        background: 'var(--bg-secondary)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <span style={{ fontSize: '1.5rem' }}>{typeInfo.icon}</span>
                          <div>
                            <div style={{ fontWeight: 600 }}>{conn.name || conn.id?.slice(0, 8)}</div>
                            <div className="text-muted text-sm">{typeInfo.label}</div>
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                          <span
                            className={`badge ${conn.status?.connected ? 'badge-success' : 'badge-danger'}`}
                            style={{ fontSize: '0.72rem' }}
                          >
                            {conn.status?.connected ? 'Connected' : 'Disconnected'}
                          </span>
                        </div>
                      </div>

                      <div style={{ display: 'flex', gap: 16, fontSize: '0.78rem', color: 'var(--muted)', marginBottom: 12 }}>
                        <span>Last sync: {formatDate(conn.status?.last_sync)}</span>
                        <span>Errors: {conn.status?.error_count || 0}</span>
                        {conn.status?.last_error && (
                          <span style={{ color: 'var(--danger)' }}>
                            Last error: {conn.status.last_error}
                          </span>
                        )}
                      </div>

                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleTestConnector(conn.id)}
                          disabled={testingId === conn.id}
                        >
                          {testingId === conn.id ? <Loader size={14} className="spin" /> : <TestTube size={14} />}
                          Test
                        </button>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => handleSyncConnector(conn.id)}
                          disabled={syncingId === conn.id}
                        >
                          {syncingId === conn.id ? <Loader size={14} className="spin" /> : <RefreshCw size={14} />}
                          Sync
                        </button>
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => handleRemoveConnector(conn.id)}
                        >
                          <Trash2 size={14} />
                          Remove
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ExportCenter;
