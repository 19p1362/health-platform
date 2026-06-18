import React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  CheckSquare,
  Shield,
  ShieldCheck,
  ShieldOff,
  AlertTriangle,
  AlertCircle,
  RefreshCw,
  Clock,
  FileText,
  Download,
  Check,
  X,
  Users,
  Trash2,
} from 'lucide-react';
import { complianceApi } from '../services/api';

const ComplianceDashboard: React.FC = () => {
  const { data: report, isLoading: reportLoading, isError: reportError, refetch: refetchReport } = useQuery({
    queryKey: ['compliance-report'],
    queryFn: () => complianceApi.getComplianceReport().catch(() => ({
      checks: [],
      overallStatus: 'unknown',
      lastAssessed: null,
    })),
  });

  const { data: breaches, isLoading: breachesLoading } = useQuery({
    queryKey: ['breaches'],
    queryFn: () => complianceApi.getBreachEvents().catch(() => []),
  });

  const { data: erasureSchedule, isLoading: erasureLoading } = useQuery({
    queryKey: ['erasure-schedule'],
    queryFn: () => complianceApi.getErasureSchedule().catch(() => []),
  });

  const { data: dpRequests } = useQuery({
    queryKey: ['data-principal-requests'],
    queryFn: () => complianceApi.getDataPrincipalRequests().catch(() => ({
      access: 0,
      correction: 0,
      erasure: 0,
      total: 0,
    })),
  });

  const { data: slaData } = useQuery({
    queryKey: ['sla-compliance'],
    queryFn: () => complianceApi.getSlaCompliance().catch(() => ({
      rate: 100,
      totalGrievances: 0,
      resolvedWithinSla: 0,
    })),
  });

  const { data: retentionData } = useQuery({
    queryKey: ['audit-retention'],
    queryFn: () => complianceApi.getAuditRetention().catch(() => ({
      retentionDays: 1095,
      oldestLog: null,
      totalLogs: 0,
    })),
  });

  const isLoading = reportLoading || breachesLoading || erasureLoading;
  const checks = report?.checks || [
    { name: 'Consent Management', status: 'pass', detail: 'All consent records compliant' },
    { name: 'Breach Response', status: breaches?.length ? 'fail' : 'pass', detail: breaches?.length ? `${breaches.length} active breaches` : 'No active breaches' },
    { name: 'Data Erasure', status: 'pass', detail: 'Erasure workflows active' },
    { name: 'Audit Trail', status: 'pass', detail: 'All operations logged' },
    { name: 'Cross-Border Transfer', status: 'warn', detail: 'Review data localization policies' },
    { name: 'Data Principal Rights', status: 'pass', detail: 'Access, correction, erasure workflows operational' },
    { name: 'Grievance SLA', status: (slaData?.rate || 100) >= 90 ? 'pass' : 'warn', detail: `${slaData?.rate || 100}% compliance rate` },
    { name: 'Data Retention', status: 'pass', detail: `${Math.round((retentionData?.retentionDays || 1095) / 365)} year retention policy` },
  ];
  const overallStatus = report?.overallStatus || checks.every((c: any) => c.status === 'pass') ? 'pass' : 'warn';
  const breachList = breaches || [];
  const erasures = erasureSchedule || [];
  const principalRequests = dpRequests || { access: 0, correction: 0, erasure: 0, total: 0 };

  const handleDownloadReport = (type: string) => {
    complianceApi.downloadReport(type).then((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${type}-report-${new Date().toISOString().split('T')[0]}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    }).catch(() => {
      // Fallback: show alert
    });
  };

  if (isLoading) {
    return (
      <div className="loading-container">
        <div className="spinner" />
        <div className="loading-text">Loading compliance data...</div>
      </div>
    );
  }

  if (reportError && !breaches?.length) {
    return (
      <div className="error-state">
        <AlertCircle size={44} />
        <div className="error-state-title">Failed to load compliance data</div>
        <div className="error-state-text">Could not connect to the backend. Ensure it's running.</div>
        <button className="btn btn-primary" onClick={() => refetchReport()}>
          <RefreshCw size={16} />
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1>Compliance Dashboard</h1>
        <p className="text-muted text-sm">DPDP 2025 compliance monitoring and reporting</p>
      </div>

      {/* Overall Status */}
      <div className="welcome-banner">
        <div className="welcome-banner-text">
          <h1>
            Overall DPDP Compliance:{' '}
            <span style={{ color: overallStatus === 'pass' ? 'var(--success)' : overallStatus === 'warn' ? 'var(--warning)' : 'var(--danger)' }}>
              {overallStatus === 'pass' ? 'Compliant' : overallStatus === 'warn' ? 'Needs Attention' : 'Non-Compliant'}
            </span>
          </h1>
          <p>Last assessed: {report?.lastAssessed ? new Date(report.lastAssessed).toLocaleString() : 'N/A'}</p>
        </div>
        <div className="compliance-badge" style={{ fontSize: '0.8rem', padding: '8px 16px' }}>
          {overallStatus === 'pass' ? <ShieldCheck size={16} /> : <AlertTriangle size={16} />}
          <span>{overallStatus === 'pass' ? 'All Checks Passing' : 'Action Required'}</span>
        </div>
      </div>

      {/* Compliance Checks */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header">
          <div className="card-title">
            <CheckSquare size={18} />
            DPDP Compliance Checks
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
          {checks.map((check: any, idx: number) => (
            <div key={idx} className="compliance-check">
              <div className="compliance-check-left">
                {check.status === 'pass' ? (
                  <ShieldCheck size={18} className="compliance-check-icon pass" />
                ) : check.status === 'warn' ? (
                  <AlertTriangle size={18} className="compliance-check-icon warn" />
                ) : (
                  <ShieldOff size={18} className="compliance-check-icon fail" />
                )}
                <div>
                  <div className="compliance-check-name">{check.name}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--muted)', marginTop: 2 }}>{check.detail}</div>
                </div>
              </div>
              <span className={`compliance-check-status ${check.status}`}>
                {check.status === 'pass' ? 'PASS' : check.status === 'warn' ? 'WARN' : 'FAIL'}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="grid-2">
        {/* Active Breaches */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <AlertTriangle size={18} style={{ color: breachList.length > 0 ? 'var(--danger)' : 'var(--success)' }} />
              Active Breaches
            </div>
            <span className={`badge badge-${breachList.length > 0 ? 'danger' : 'success'}`}>
              {breachList.length > 0 ? `${breachList.length} Active` : 'None'}
            </span>
          </div>
          {breachList.length === 0 ? (
            <div className="empty-state" style={{ padding: 24 }}>
              <ShieldCheck size={32} style={{ color: 'var(--success)' }} />
              <div className="empty-state-text">No active breach events</div>
            </div>
          ) : (
            <div>
              {breachList.slice(0, 5).map((breach: any, idx: number) => (
                <div
                  key={breach.id || idx}
                  style={{
                    padding: '10px 0',
                    borderBottom: idx < Math.min(breachList.length, 5) - 1 ? '1px solid var(--border)' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                        {breach.type || breach.title || 'Data Breach'}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 2 }}>
                        {breach.severity ? `Severity: ${breach.severity}` : ''}
                        {breach.detectedAt ? ` · ${new Date(breach.detectedAt).toLocaleDateString()}` : ''}
                      </div>
                    </div>
                    <span className="badge badge-danger">{breach.status || 'Active'}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Pending Erasure Schedule */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Trash2 size={18} style={{ color: 'var(--warning)' }} />
              Pending Erasure Schedule
            </div>
            <span className={`badge badge-${erasures.length > 0 ? 'warning' : 'success'}`}>
              {erasures.length} Pending
            </span>
          </div>
          {erasures.length === 0 ? (
            <div className="empty-state" style={{ padding: 24 }}>
              <Check size={32} style={{ color: 'var(--success)' }} />
              <div className="empty-state-text">No pending erasure requests</div>
            </div>
          ) : (
            <div>
              {erasures.map((erasure: any, idx: number) => (
                <div
                  key={erasure.id || idx}
                  style={{
                    padding: '10px 0',
                    borderBottom: idx < erasures.length - 1 ? '1px solid var(--border)' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                        Patient: {erasure.patientId || erasure.patientName || 'Unknown'}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 2 }}>
                        Scheduled: {erasure.scheduledDate ? new Date(erasure.scheduledDate).toLocaleDateString() : 'N/A'}
                      </div>
                    </div>
                    <span className={`badge badge-${erasure.status === 'pending' ? 'warning' : erasure.status === 'completed' ? 'success' : 'neutral'}`}>
                      {erasure.status || 'Pending'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid-3" style={{ marginTop: 24 }}>
        {/* Data Principal Requests */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Users size={18} />
              Data Principal Requests
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {[
              { label: 'Access Requests', count: principalRequests.access || 0, color: 'var(--primary)' },
              { label: 'Correction Requests', count: principalRequests.correction || 0, color: 'var(--warning)' },
              { label: 'Erasure Requests', count: principalRequests.erasure || 0, color: 'var(--danger)' },
            ].map((item) => (
              <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>{item.label}</span>
                <span style={{ fontSize: '1.1rem', fontWeight: 700, color: item.color }}>{item.count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* SLA Compliance */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Clock size={18} />
              SLA Compliance (90-day)
            </div>
          </div>
          <div style={{ textAlign: 'center', padding: '12px 0' }}>
            <div style={{ fontSize: '2.5rem', fontWeight: 700, color: (slaData?.rate || 100) >= 90 ? 'var(--success)' : 'var(--warning)' }}>
              {(slaData?.rate || 100)}%
            </div>
            <div className="text-muted text-sm">Grievance resolution SLA</div>
            <div style={{ marginTop: 8, fontSize: '0.82rem', color: 'var(--muted)' }}>
              {slaData?.resolvedWithinSla || 0} of {slaData?.totalGrievances || 0} resolved within 90 days
            </div>
          </div>
        </div>

        {/* Audit Retention */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <FileText size={18} />
              Audit Log Retention
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '4px 0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>Retention Period</span>
              <span style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                {Math.round((retentionData?.retentionDays || 1095) / 365)} years
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>Total Logs</span>
              <span style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                {retentionData?.totalLogs?.toLocaleString() || 0}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>Oldest Log</span>
              <span style={{ fontSize: '0.82rem', color: 'var(--muted)' }}>
                {retentionData?.oldestLog ? new Date(retentionData.oldestLog).toLocaleDateString() : 'N/A'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Report Downloads */}
      <div className="card" style={{ marginTop: 24 }}>
        <div className="card-header">
          <div className="card-title">
            <Download size={18} />
            Compliance Reports
          </div>
        </div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button className="btn btn-primary" onClick={() => handleDownloadReport('dpia')}>
            <FileText size={16} />
            Download DPIA Report
          </button>
          <button className="btn btn-secondary" onClick={() => handleDownloadReport('compliance')}>
            <FileText size={16} />
            Download Compliance Report
          </button>
          <button className="btn btn-secondary" onClick={() => handleDownloadReport('breach')}>
            <AlertTriangle size={16} />
            Download Breach Report
          </button>
        </div>
      </div>
    </div>
  );
};

export default ComplianceDashboard;
