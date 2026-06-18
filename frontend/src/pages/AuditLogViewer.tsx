import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  FileSearch,
  AlertCircle,
  RefreshCw,
  Download,
  ChevronLeft,
  ChevronRight,
  Filter,
  Info,
} from 'lucide-react';
import { complianceApi } from '../services/api';

const ACTION_TYPES = [
  '',
  'PATIENT_VIEW',
  'PATIENT_SEARCH',
  'CONSENT_GRANT',
  'CONSENT_WITHDRAW',
  'CONVERSION_CREATE',
  'FHIR_READ',
  'FHIR_SEARCH',
  'DATA_EXPORT',
  'BREACH_DETECTED',
  'ERASURE_REQUEST',
  'ERASURE_COMPLETE',
  'LOGIN',
  'LOGOUT',
];

const AuditLogViewer: React.FC = () => {
  const [action, setAction] = useState('');
  const [patientId, setPatientId] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [page, setPage] = useState(1);
  const limit = 20;

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['audit-logs', action, patientId, startDate, endDate, page],
    queryFn: () =>
      complianceApi.getAuditLogs({
        action: action || undefined,
        patientId: patientId || undefined,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
        page,
        limit,
      }),
  });

  const logs = data?.logs || [];
  const totalPages = data?.pages || 1;
  const total = data?.total || 0;

  const handleExportCsv = () => {
    if (logs.length === 0) return;
    const headers = ['Timestamp', 'Action', 'Patient ID', 'User', 'Description', 'IP Address'];
    const rows = logs.map((log: any) => [
      log.timestamp || '',
      log.action || '',
      log.patientId || '',
      log.user || log.userId || '',
      `"${(log.description || '').replace(/"/g, '""')}"`,
      log.ipAddress || '',
    ]);
    const csv = [headers.join(','), ...rows.map((r: string[]) => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit-log-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleFilter = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    refetch();
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1>Audit Log Viewer</h1>
        <p className="text-muted text-sm">View and export audit trail for DPDP 2025 compliance</p>
      </div>

      {/* DPDP Retention Notice */}
      <div className="dpdp-notice">
        <Info size={16} />
        <span>
          DPDP 2025 requires audit logs to be retained for a minimum of 3 years.
          All access and operations are logged immutably.
        </span>
      </div>

      {/* Filters */}
      <div className="filter-bar">
        <form onSubmit={handleFilter} style={{ width: '100%' }}>
          <div className="form-row">
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Action Type</label>
              <select className="form-select" value={action} onChange={(e) => setAction(e.target.value)}>
                <option value="">All Actions</option>
                {ACTION_TYPES.filter(Boolean).map((a) => (
                  <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Patient ID</label>
              <input
                type="text"
                className="form-input"
                placeholder="Filter by patient"
                value={patientId}
                onChange={(e) => setPatientId(e.target.value)}
              />
            </div>
          </div>
          <div className="form-row" style={{ marginTop: 12 }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Start Date</label>
              <input
                type="date"
                className="form-input"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">End Date</label>
              <input
                type="date"
                className="form-input"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 12 }}>
            <button type="submit" className="btn btn-primary" disabled={isLoading}>
              {isLoading ? (
                <><div className="spinner spinner-sm" /> Loading...</>
              ) : (
                <><Filter size={16} /> Apply Filters</>
              )}
            </button>
            <button type="button" className="btn btn-secondary" onClick={handleExportCsv} disabled={logs.length === 0}>
              <Download size={16} />
              Export CSV
            </button>
          </div>
        </form>
      </div>

      {/* Results */}
      {isLoading && (
        <div className="loading-container">
          <div className="spinner" />
          <div className="loading-text">Loading audit logs...</div>
        </div>
      )}

      {isError && (
        <div className="error-state">
          <AlertCircle size={44} />
          <div className="error-state-title">Failed to load audit logs</div>
          <div className="error-state-text">
            {(error as any)?.message || 'An error occurred while fetching audit logs.'}
          </div>
          <button className="btn btn-primary" onClick={() => refetch()}>
            <RefreshCw size={16} />
            Retry
          </button>
        </div>
      )}

      {!isLoading && !isError && logs.length === 0 && (
        <div className="empty-state">
          <FileSearch size={48} />
          <div className="empty-state-title">No audit logs found</div>
          <div className="empty-state-text">Try adjusting your filters or select a different date range.</div>
        </div>
      )}

      {!isLoading && !isError && logs.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div
            style={{
              padding: '12px 20px',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
              {total} log{total !== 1 ? 's' : ''} found
            </span>
          </div>
          <div className="table-container" style={{ border: 'none' }}>
            <table>
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Action</th>
                  <th>Patient</th>
                  <th>User</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log: any, idx: number) => (
                  <tr key={log.id || idx}>
                    <td style={{ fontSize: '0.78rem', whiteSpace: 'nowrap' }}>
                      {log.timestamp ? new Date(log.timestamp).toLocaleString() : '-'}
                    </td>
                    <td>
                      <span className={`badge badge-${
                        log.action?.includes('BREACH') || log.action?.includes('ERROR')
                          ? 'danger'
                          : log.action?.includes('CONSENT')
                          ? 'warning'
                          : 'info'
                      }`} style={{ fontSize: '0.65rem' }}>
                        {log.action?.replace(/_/g, ' ') || '-'}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.8rem', fontFamily: 'monospace' }}>
                      {log.patientId || '-'}
                    </td>
                    <td style={{ fontSize: '0.82rem' }}>{log.user || log.userId || '-'}</td>
                    <td style={{ fontSize: '0.8rem', maxWidth: 250 }} className="truncate">
                      {log.description || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="pagination">
            <button
              className="pagination-btn"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft size={16} />
            </button>
            {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
              const pageNum = i + 1;
              return (
                <button
                  key={pageNum}
                  className={`pagination-btn ${page === pageNum ? 'active' : ''}`}
                  onClick={() => setPage(pageNum)}
                >
                  {pageNum}
                </button>
              );
            })}
            <button
              className="pagination-btn"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AuditLogViewer;
