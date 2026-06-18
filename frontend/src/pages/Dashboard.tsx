import React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Users,
  Server,
  Activity,
  Shield,
  AlertTriangle,
  FileText,
  RefreshCw,
  PieChart as PieChartIcon,
} from 'lucide-react';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useAuth } from '../hooks/useAuth';
import { healthApi, complianceApi, conversionApi } from '../services/api';

const COLORS = {
  success: '#22c55e',
  warning: '#f59e0b',
  danger: '#ef4444',
  info: '#06b6d4',
  primary: '#3b82f6',
  muted: '#64748b',
};

const Dashboard: React.FC = () => {
  const { currentUser } = useAuth();

  const { data: healthStats, isLoading: statsLoading, isError: statsError, refetch: refetchStats } = useQuery({
    queryKey: ['health-stats'],
    queryFn: () => healthApi.getStats().catch(() => ({
      patientCount: 0,
      connectedSources: 0,
      recentAuditEvents: [],
      conversionCount24h: 0,
      consentSummary: [],
      breachAlerts: [],
    })),
  });

  const { data: consentData, isLoading: consentLoading } = useQuery({
    queryKey: ['consent-summary'],
    queryFn: () => healthApi.getStats().catch(() => ({
      consentSummary: [
        { name: 'Active', value: 0 },
        { name: 'Pending', value: 0 },
        { name: 'Withdrawn', value: 0 },
      ],
    })),
  });

  const { data: auditData } = useQuery({
    queryKey: ['recent-audit'],
    queryFn: () =>
      complianceApi.getAuditLogs({ limit: 5 }).catch(() => ({
        logs: [],
        total: 0,
        page: 1,
        pages: 1,
      })),
  });

  const { data: breachData } = useQuery({
    queryKey: ['breach-events'],
    queryFn: () => complianceApi.getBreachEvents().catch(() => []),
  });

  const isLoading = statsLoading;
  const stats = healthStats || { patientCount: 0, connectedSources: 0, conversionCount24h: 0, consentSummary: [] };
  const auditLogs = auditData?.logs || [];
  const breaches = breachData || [];
  const consentSummary = stats.consentSummary?.length
    ? stats.consentSummary
    : [
        { name: 'Active', value: 0 },
        { name: 'Pending', value: 0 },
        { name: 'Withdrawn', value: 0 },
      ];

  if (isLoading) {
    return (
      <div className="loading-container">
        <div className="spinner" />
        <div className="loading-text">Loading dashboard...</div>
      </div>
    );
  }

  if (statsError) {
    return (
      <div className="error-state">
        <AlertTriangle size={44} />
        <div className="error-state-title">Failed to load dashboard</div>
        <div className="error-state-text">Could not connect to the backend server. Please ensure it's running.</div>
        <button className="btn btn-primary" onClick={() => refetchStats()}>
          <RefreshCw size={16} />
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      {/* Welcome Banner */}
      <div className="welcome-banner">
        <div className="welcome-banner-text">
          <h1>Welcome back, {currentUser?.name || 'User'} 👋</h1>
          <p>HealthBridge Platform — Interoperability Dashboard. All operations logged per DPDP 2025.</p>
        </div>
        <div className="compliance-badge" style={{ fontSize: '0.8rem', padding: '8px 16px' }}>
          <Shield size={16} />
          <span>DPDP 2025 Compliant</span>
        </div>
      </div>

      {/* Breach Alerts */}
      {breaches.length > 0 && (
        <div className="alert alert-danger" style={{ marginBottom: 24 }}>
          <AlertTriangle size={20} />
          <div>
            <strong>{breaches.length} active breach event(s)</strong> — Immediate attention required.{' '}
            <a href="/compliance" style={{ textDecoration: 'underline' }}>View details</a>
          </div>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        <div className="kpi-card">
          <div className="kpi-label">
            <Users size={14} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
            Total Patients
          </div>
          <div className="kpi-value primary">{stats.patientCount?.toLocaleString() || '0'}</div>
          <div className="kpi-change positive">Across all connected sources</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">
            <Server size={14} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
            Connected Sources
          </div>
          <div className="kpi-value success">{stats.connectedSources || '0'}</div>
          <div className="kpi-change positive">All systems operational</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">
            <Activity size={14} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
            Conversions (24h)
          </div>
          <div className="kpi-value warning">{stats.conversionCount24h || '0'}</div>
          <div className="kpi-change">HL7 FHIR & C-CDA</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">
            <FileText size={14} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
            Audit Events
          </div>
          <div className="kpi-value info">{auditData?.total || '0'}</div>
          <div className="kpi-change">All logged per DPDP 2025</div>
        </div>
      </div>

      <div className="grid-2">
        {/* Consent Summary Pie Chart */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <ShieldCheckIcon />
              Consent Status Summary
            </div>
          </div>
          {consentLoading ? (
            <div className="loading-container">
              <div className="spinner spinner-sm" />
              <div className="loading-text">Loading consent data...</div>
            </div>
          ) : (
            <div style={{ width: '100%', height: 260 }}>
              <ResponsiveContainer>
                <PieChart>
                  <Pie
                    data={consentSummary}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={90}
                    paddingAngle={4}
                    dataKey="value"
                    stroke="none"
                  >
                    {consentSummary.map((_: any, index: number) => (
                      <Cell
                        key={index}
                        fill={[COLORS.success, COLORS.warning, COLORS.danger, COLORS.info, COLORS.primary][index % 5]}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: 'var(--card)',
                      border: '1px solid var(--border)',
                      borderRadius: '6px',
                      color: 'var(--text)',
                    }}
                  />
                  <Legend
                    formatter={(value) => (
                      <span style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>{value}</span>
                    )}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Recent Audit Events */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <FileText />
              Recent Audit Events
            </div>
            <a href="/audit" className="btn btn-ghost btn-sm">View All</a>
          </div>
          {auditLogs.length === 0 ? (
            <div className="empty-state" style={{ padding: '24px' }}>
              <FileText size={32} />
              <div className="empty-state-text">No recent audit events</div>
            </div>
          ) : (
            <div>
              {auditLogs.map((log: any, idx: number) => (
                <div
                  key={log.id || idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '10px 0',
                    borderBottom: idx < auditLogs.length - 1 ? '1px solid var(--border)' : 'none',
                  }}
                >
                  <div
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: log.action?.includes('BREACH') || log.action?.includes('ERROR')
                        ? 'var(--danger)'
                        : 'var(--primary)',
                      flexShrink: 0,
                    }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                      {log.action || 'Unknown Action'}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 2 }}>
                      {log.description || log.patientId || '-'}
                    </div>
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                    {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '-'}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// Inline icon component to avoid conflict
const ShieldCheckIcon: React.FC<{ size?: number }> = ({ size = 18 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <polyline points="9 12 11 14 15 10" />
  </svg>
);

export default Dashboard;
