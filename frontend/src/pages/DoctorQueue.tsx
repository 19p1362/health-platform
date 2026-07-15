import React, { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { opdApi } from '../services/api';
import { useNavigate } from 'react-router-dom';

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

const DoctorQueue: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedToken, setSelectedToken] = useState<TokenQueueItem | null>(null);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [room, setRoom] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(true);

  const { data: queueData, isLoading, error, refetch } = useQuery({
    queryKey: ['opd-queue'],
    queryFn: () => opdApi.getQueue(),
    refetchInterval: autoRefresh ? 5000 : false,
    staleTime: 3000,
  });

  const actionMutation = useMutation({
    mutationFn: ({ tokenId, action, room }: { tokenId: string; action: string; room?: string }) =>
      opdApi.queueAction(tokenId, action, room),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['opd-queue'] });
      setActionInProgress(null);
      setSelectedToken(null);
      setRoom('');
    },
    onError: (err: any) => {
      alert(err.response?.data?.detail || 'Action failed');
      setActionInProgress(null);
    },
  });

  const handleAction = (token: TokenQueueItem, action: string) => {
    setSelectedToken(token);
    setActionInProgress(action);
    if (action === 'CALL_NEXT' || action === 'RECALL' || action === 'COMPLETE') {
      // Prompt for room
    } else {
      // Execute immediately for SKIP
      actionMutation.mutate({ tokenId: token.id, action, room });
    }
  };

  const confirmAction = () => {
    if (selectedToken && actionInProgress) {
      actionMutation.mutate({ tokenId: selectedToken.id, action: actionInProgress, room });
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'WAITING': return '#f59e0b';
      case 'CALLED': return '#3b82f6';
      case 'IN_PROGRESS': return '#8b5cf6';
      case 'DONE': return '#22c55e';
      case 'SKIPPED': return '#ef4444';
      case 'NO_SHOW': return '#94a3b8';
      default: return '#64748b';
    }
  };

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      WAITING: 'Waiting',
      CALLED: 'Called',
      IN_PROGRESS: 'In Progress',
      DONE: 'Completed',
      SKIPPED: 'Skipped',
      NO_SHOW: 'No Show',
    };
    return labels[status] || status;
  };

  if (isLoading) {
    return (
      <div className="doctor-queue page-container">
        <div className="loading">Loading queue...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="doctor-queue page-container">
        <div className="error">Failed to load queue</div>
      </div>
    );
  }

  const tokens = queueData?.tokens || [];
  const waitingTokens = tokens.filter(t => t.status === 'WAITING' || t.status === 'CALLED');
  const inProgressTokens = tokens.filter(t => t.status === 'IN_PROGRESS');
  const completedTokens = tokens.filter(t => t.status === 'DONE');

  return (
    <div className="doctor-queue page-container">
      <div className="page-header">
        <h1>Doctor Queue Dashboard</h1>
        <div className="header-actions">
          <label className="auto-refresh-toggle">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh (5s)
          </label>
          <button onClick={() => refetch()} className="btn btn-secondary" disabled={isLoading}>
            Refresh Now
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="summary-cards">
        <div className="summary-card waiting">
          <span className="summary-label">Waiting</span>
          <span className="summary-value">{queueData?.total_waiting || 0}</span>
        </div>
        <div className="summary-card in-progress">
          <span className="summary-label">In Progress</span>
          <span className="summary-value">{queueData?.total_in_progress || 0}</span>
        </div>
        <div className="summary-card current">
          <span className="summary-label">Current Token</span>
          <span className="summary-value">{queueData?.current_token || '—'}</span>
        </div>
        <div className="summary-card next">
          <span className="summary-label">Next Token</span>
          <span className="summary-value">{queueData?.next_token || '—'}</span>
        </div>
      </div>

      {/* Quick Action for Next Patient */}
      {waitingTokens.length > 0 && inProgressTokens.length === 0 && (
        <div className="next-patient-banner">
          <div className="banner-content">
            <span className="banner-label">Next Patient:</span>
            <span className="banner-token">Token #{waitingTokens[0].token_number}</span>
            <span className="banner-name">{waitingTokens[0].patient_name}</span>
            <span className="banner-complaint">{waitingTokens[0].chief_complaint || 'No complaint recorded'}</span>
          </div>
          <button
            onClick={() => handleAction(waitingTokens[0], 'CALL_NEXT')}
            className="btn btn-primary call-next-btn"
            disabled={actionInProgress === 'CALL_NEXT'}
          >
            {actionInProgress === 'CALL_NEXT' ? 'Calling...' : 'Call Next Patient'}
          </button>
        </div>
      )}

      {/* Token Lists */}
      <div className="queue-sections">
        {/* In Progress */}
        {inProgressTokens.length > 0 && (
          <div className="queue-section in-progress-section">
            <h3>In Progress</h3>
            <div className="token-cards">
              {inProgressTokens.map((token) => (
                <TokenCard
                  key={token.id}
                  token={token}
                  onVitals={() => navigate(`/patients/${token.id}/vitals?token=${token.id}`)}
                  onSoap={() => navigate(`/patients/${token.id}/soap?token=${token.id}`)}
                  onComplete={() => { setRoom(''); handleAction(token, 'COMPLETE'); }}
                  onSkip={() => handleAction(token, 'SKIP')}
                  onRecall={() => { setRoom(''); handleAction(token, 'RECALL'); }}
                />
              ))}
            </div>
          </div>
        )}

        {/* Waiting */}
        {waitingTokens.length > 0 && (
          <div className="queue-section waiting-section">
            <h3>Waiting ({waitingTokens.length})</h3>
            <div className="token-list">
              {waitingTokens.map((token) => (
                <TokenListItem
                  key={token.id}
                  token={token}
                  isCurrent={token.token_number === queueData?.current_token}
                  onCall={() => handleAction(token, 'CALL_NEXT')}
                  onRecall={() => { setRoom(''); handleAction(token, 'RECALL'); }}
                />
              ))}
            </div>
          </div>
        )}

        {/* Completed */}
        {completedTokens.length > 0 && (
          <div className="queue-section completed-section">
            <h3>Completed Today ({completedTokens.length})</h3>
            <div className="token-list">
              {completedTokens.slice(0, 10).map((token) => (
                <TokenListItem
                  key={token.id}
                  token={token}
                  isCompleted
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Action Confirmation Modal */}
      {(actionInProgress === 'CALL_NEXT' || actionInProgress === 'RECALL' || actionInProgress === 'COMPLETE') && selectedToken && (
        <div className="modal-overlay" onClick={() => { setActionInProgress(null); setSelectedToken(null); setRoom(''); }}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{actionInProgress === 'CALL_NEXT' ? 'Call Patient' : actionInProgress === 'RECALL' ? 'Recall Patient' : 'Complete Visit'}</h3>
            <p>Token #{selectedToken.token_number} — {selectedToken.patient_name}</p>
            <div className="form-group">
              <label>Room Number</label>
              <input
                type="text"
                value={room}
                onChange={(e) => setRoom(e.target.value)}
                placeholder="e.g., Room 1"
                className="form-input"
                autoFocus
              />
            </div>
            <div className="modal-actions">
              <button onClick={confirmAction} className="btn btn-primary" disabled={actionInProgress === 'CALL_NEXT' || actionInProgress === 'RECALL' || actionInProgress === 'COMPLETE'}>
                Confirm
              </button>
              <button onClick={() => { setActionInProgress(null); setSelectedToken(null); setRoom(''); }} className="btn btn-secondary">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .page-container { padding: 24px; max-width: 1400px; margin: 0 auto; }
        .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
        .page-header h1 { margin: 0; color: #1e293b; }
        .header-actions { display: flex; align-items: center; gap: 16px; }
        .auto-refresh-toggle { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #475569; cursor: pointer; }
        .summary-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
        .summary-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); display: flex; flex-direction: column; gap: 8px; }
        .summary-card.waiting { border-left: 4px solid #f59e0b; }
        .summary-card.in-progress { border-left: 4px solid #8b5cf6; }
        .summary-card.current { border-left: 4px solid #3b82f6; }
        .summary-card.next { border-left: 4px solid #22c55e; }
        .summary-label { font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
        .summary-value { font-size: 32px; font-weight: 700; color: #1e293b; font-family: monospace; }
        .next-patient-banner { background: linear-gradient(135deg, #3b82f6, #2563eb); border-radius: 12px; padding: 20px 24px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; color: white; box-shadow: 0 4px 12px rgba(59,130,246,0.3); }
        .banner-content { display: flex; flex-direction: column; gap: 4px; }
        .banner-label { font-size: 13px; opacity: 0.9; }
        .banner-token { font-size: 24px; font-weight: 700; font-family: monospace; }
        .banner-name { font-size: 18px; font-weight: 500; }
        .banner-complaint { font-size: 13px; opacity: 0.8; }
        .call-next-btn { padding: 12px 24px; font-size: 15px; font-weight: 600; white-space: nowrap; }
        .queue-sections { display: flex; flex-direction: column; gap: 24px; }
        .queue-section { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .queue-section h3 { margin: 0 0 16px; color: #1e293b; font-size: 16px; display: flex; align-items: center; gap: 8px; }
        .token-cards { display: flex; flex-direction: column; gap: 12px; }
        .token-list { display: flex; flex-direction: column; gap: 8px; }
        .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
        .modal { background: white; border-radius: 12px; padding: 24px; min-width: 360px; box-shadow: 0 20px 40px rgba(0,0,0,0.2); }
        .modal h3 { margin: 0 0 8px; color: #1e293b; }
        .modal p { margin: 0 0 16px; color: #64748b; }
        .modal .form-group { margin-bottom: 16px; }
        .modal .form-group label { display: block; margin-bottom: 6px; font-size: 13px; font-weight: 500; color: #475569; }
        .modal .form-input { width: 100%; padding: 10px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 14px; }
        .modal .form-input:focus { outline: none; border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }
        .modal-actions { display: flex; justify-content: flex-end; gap: 12px; }
        .loading, .error { text-align: center; padding: 60px; color: #64748b; }
        .error { color: #ef4444; }
        .btn { padding: 10px 16px; border-radius: 8px; border: none; cursor: pointer; font-weight: 500; transition: all 0.2s; }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .btn-primary { background: #3b82f6; color: white; }
        .btn-primary:hover:not(:disabled) { background: #2563eb; }
        .btn-secondary { background: #f1f5f9; color: #475569; }
        .btn-secondary:hover:not(:disabled) { background: #e2e8f0; }
        @media (max-width: 1024px) {
          .summary-cards { grid-template-columns: repeat(2, 1fr); }
        }
        @media (max-width: 640px) {
          .summary-cards { grid-template-columns: 1fr; }
          .next-patient-banner { flex-direction: column; gap: 16px; align-items: stretch; }
        }
      `}</style>
    </div>
  );
};

// Token Card for In Progress patients
const TokenCard: React.FC<{
  token: TokenQueueItem;
  onVitals: () => void;
  onSoap: () => void;
  onComplete: () => void;
  onSkip: () => void;
  onRecall: () => void;
}> = ({ token, onVitals, onSoap, onComplete, onSkip, onRecall }) => {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'IN_PROGRESS': return '#8b5cf6';
      case 'CALLED': return '#3b82f6';
      default: return '#64748b';
    }
  };

  return (
    <div className="token-card" style={{ borderLeftColor: getStatusColor(token.status) }}>
      <div className="token-header">
        <div className="token-main">
          <span className="token-number">Token #{token.token_number}</span>
          <span className="token-name">{token.patient_name}</span>
          <span className="token-meta">
            {token.age ? `${token.age}y` : ''} {token.gender ? `• ${token.gender}` : ''}
          </span>
        </div>
        <span className="token-status" style={{ background: getStatusColor(token.status) }}>
          {token.status.replace('_', ' ')}
        </span>
      </div>
      {token.chief_complaint && (
        <div className="token-complaint">Chief Complaint: {token.chief_complaint}</div>
      )}
      <div className="token-actions">
        <button onClick={onVitals} className="btn btn-outline">Vitals</button>
        <button onClick={onSoap} className="btn btn-outline">SOAP</button>
        <button onClick={onRecall} className="btn btn-secondary">Recall</button>
        <button onClick={onSkip} className="btn btn-secondary">Skip</button>
        <button onClick={onComplete} className="btn btn-primary">Complete Visit</button>
      </div>
      <style jsx>{`
        .token-card { border-left: 4px solid; border-radius: 8px; padding: 16px; background: #fafafa; transition: all 0.2s; }
        .token-card:hover { background: #f5f5f5; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
        .token-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
        .token-main { display: flex; flex-direction: column; gap: 4px; }
        .token-number { font-size: 18px; font-weight: 700; color: #1e293b; font-family: monospace; }
        .token-name { font-size: 16px; font-weight: 500; color: #1e293b; }
        .token-meta { font-size: 13px; color: #64748b; }
        .token-status { padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 600; color: white; text-transform: uppercase; letter-spacing: 0.5px; }
        .token-complaint { font-size: 13px; color: #475569; padding: 8px 12px; background: white; border-radius: 6px; margin-bottom: 12px; border-left: 3px solid #e2e8f0; }
        .token-actions { display: flex; gap: 8px; flex-wrap: wrap; }
        .btn { padding: 8px 14px; border-radius: 6px; border: none; cursor: pointer; font-weight: 500; font-size: 13px; transition: all 0.2s; }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .btn-primary { background: #22c55e; color: white; }
        .btn-primary:hover:not(:disabled) { background: #16a34a; }
        .btn-secondary { background: #f1f5f9; color: #475569; }
        .btn-secondary:hover:not(:disabled) { background: #e2e8f0; }
        .btn-outline { background: white; color: #3b82f6; border: 1px solid #3b82f6; }
        .btn-outline:hover:not(:disabled) { background: #eff6ff; }
      `}</style>
    </div>
  );
};

// Token List Item for Waiting/Completed
const TokenListItem: React.FC<{
  token: TokenQueueItem;
  isCurrent?: boolean;
  isCompleted?: boolean;
  onCall?: () => void;
  onRecall?: () => void;
}> = ({ token, isCurrent, isCompleted, onCall, onRecall }) => {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'WAITING': return '#f59e0b';
      case 'CALLED': return '#3b82f6';
      case 'DONE': return '#22c55e';
      case 'SKIPPED': return '#ef4444';
      case 'NO_SHOW': return '#94a3b8';
      default: return '#64748b';
    }
  };

  return (
    <div className={`token-item ${isCurrent ? 'current' : ''} ${isCompleted ? 'completed' : ''}`}>
      <div className="token-info">
        <span className="token-number">#{token.token_number}</span>
        <span className="token-name">{token.patient_name}</span>
        <span className="token-meta">
          {token.age ? `${token.age}y` : ''} {token.gender ? `• ${token.gender}` : ''}
          {token.chief_complaint ? `• ${token.chief_complaint}` : ''}
        </span>
      </div>
      <div className="token-right">
        <span className="token-status" style={{ background: getStatusColor(token.status) }}>
          {token.status.replace('_', ' ')}
        </span>
        {!isCompleted && onCall && (
          <button onClick={onCall} className="btn btn-sm btn-primary" disabled={token.status === 'CALLED'}>
            {token.status === 'CALLED' ? 'Called' : 'Call'}
          </button>
        )}
        {!isCompleted && onRecall && token.status === 'CALLED' && (
          <button onClick={onRecall} className="btn btn-sm btn-secondary">Recall</button>
        )}
      </div>
      <style jsx>{`
        .token-item { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: #fafafa; border-radius: 8px; transition: all 0.2s; gap: 16px; }
        .token-item:hover { background: #f5f5f5; }
        .token-item.current { background: #eff6ff; border: 1px solid #3b82f6; }
        .token-item.completed { opacity: 0.7; }
        .token-info { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
        .token-number { font-size: 16px; font-weight: 700; color: #1e293b; font-family: monospace; }
        .token-name { font-size: 14px; font-weight: 500; color: #1e293b; }
        .token-meta { font-size: 12px; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .token-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .token-status { padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; color: white; text-transform: uppercase; letter-spacing: 0.5px; white-space: nowrap; }
        .btn-sm { padding: 6px 12px; font-size: 12px; }
      `}</style>
    </div>
  );
};

export default DoctorQueue;