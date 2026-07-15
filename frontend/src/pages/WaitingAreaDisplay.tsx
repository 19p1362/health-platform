import React, { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { opdApi } from '../services/api';

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

const WaitingDisplay: React.FC = () => {
  const [currentToken, setCurrentToken] = useState<number | null>(null);
  const [nextToken, setNextToken] = useState<number | null>(null);
  const [currentRoom, setCurrentRoom] = useState<string>('');
  const [announcementQueue, setAnnouncementQueue] = useState<number[]>([]);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const { data: queueData, isLoading, error, refetch } = useQuery({
    queryKey: ['opd-queue-display'],
    queryFn: () => opdApi.getQueue(),
    refetchInterval: 3000,
    staleTime: 1000,
  });

  // Announce token using Web Speech API
  const announceToken = (tokenNumber: number, room: string) => {
    if ('speechSynthesis' in window) {
      const utterance = new SpeechSynthesisUtterance(
        `Token number ${tokenNumber}, please proceed to ${room || 'the consultation room'}`
      );
      utterance.rate = 0.9;
      utterance.pitch = 1;
      utterance.volume = 1;
      utterance.onstart = () => setIsSpeaking(true);
      utterance.onend = () => setIsSpeaking(false);
      speechSynthesis.speak(utterance);
    }
  };

  // Process queue changes and announce
  useEffect(() => {
    if (!queueData) return;

    const tokens = queueData.tokens || [];
    const inProgress = tokens.filter(t => t.status === 'IN_PROGRESS' || t.status === 'CALLED');
    const waiting = tokens.filter(t => t.status === 'WAITING').sort((a, b) => a.token_number - b.token_number);

    const newCurrent = inProgress.length > 0
      ? Math.min(...inProgress.map(t => t.token_number))
      : waiting.length > 0
        ? waiting[0].token_number
        : null;

    const newNext = waiting.length > 0
      ? (newCurrent === waiting[0].token_number ? waiting[1]?.token_number : waiting[0].token_number)
      : null;

    const newRoom = inProgress.length > 0
      ? inProgress.find(t => t.token_number === newCurrent)?.room
      : '';

    // Announce when token changes to CALLED/IN_PROGRESS
    if (newCurrent !== null && newCurrent !== currentToken) {
      const tokenInfo = tokens.find(t => t.token_number === newCurrent);
      if (tokenInfo && (tokenInfo.status === 'CALLED' || tokenInfo.status === 'IN_PROGRESS')) {
        setAnnouncementQueue(prev => [...prev, newCurrent]);
      }
    }

    setCurrentToken(newCurrent);
    setNextToken(newNext);
    setCurrentRoom(newRoom || '');
  }, [queueData, currentToken]);

  // Process announcement queue
  useEffect(() => {
    if (announcementQueue.length > 0 && !isSpeaking) {
      const tokenToAnnounce = announcementQueue[0];
      const tokenInfo = queueData?.tokens?.find(t => t.token_number === tokenToAnnounce);
      if (tokenInfo?.room) {
        announceToken(tokenToAnnounce, tokenInfo.room);
        setAnnouncementQueue(prev => prev.slice(1));
      }
    }
  }, [announcementQueue, isSpeaking, queueData]);

  if (isLoading) {
    return (
      <div className="waiting-display">
        <div className="loading">Loading queue...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="waiting-display">
        <div className="error">Failed to load queue</div>
      </div>
    );
  }

  const tokens = queueData?.tokens || [];
  const waitingTokens = tokens
    .filter(t => t.status === 'WAITING')
    .sort((a, b) => a.token_number - b.token_number)
    .slice(0, 10);
  const calledTokens = tokens
    .filter(t => t.status === 'CALLED' || t.status === 'IN_PROGRESS')
    .sort((a, b) => a.token_number - b.token_number);

  return (
    <div className="waiting-display">
      {/* Current Token - Large Display */}
      <div className="current-token-section">
        <div className="section-label">NOW SERVING</div>
        <div className="token-display">
          {currentToken ? (
            <>
              <div className="token-number-large">#{currentToken}</div>
              {currentRoom && <div className="room-display">Room: {currentRoom}</div>}
            </>
          ) : (
            <div className="token-number-large">—</div>
          )}
        </div>
      </div>

      {/* Next Token */}
      <div className="next-token-section">
        <div className="section-label">NEXT TOKEN</div>
        <div className="next-token-display">
          {nextToken ? `#${nextToken}` : '—'}
        </div>
      </div>

      {/* Waiting Queue */}
      <div className="queue-section">
        <div className="section-header">
          <span className="section-label">WAITING QUEUE</span>
          <span className="queue-count">{waitingTokens.length} waiting</span>
        </div>
        <div className="token-list">
          {waitingTokens.length > 0 ? (
            waitingTokens.map((token) => (
              <div key={token.id} className="token-item waiting">
                <span className="token-num">#{token.token_number}</span>
                <span className="token-name">{token.patient_name}</span>
                <span className="token-meta">
                  {token.age ? `${token.age}y ` : ''}
                  {token.gender ? `• ${token.gender} ` : ''}
                  {token.chief_complaint ? `• ${token.chief_complaint}` : ''}
                </span>
                <span className={`status-badge ${token.status.toLowerCase()}`}>
                  {token.status.replace('_', ' ')}
                </span>
              </div>
            ))
          ) : (
            <div className="empty-queue">No patients waiting</div>
          )}
        </div>
      </div>

      {/* Called/In Progress Tokens */}
      {calledTokens.length > 0 && (
        <div className="queue-section called-section">
          <div className="section-header">
            <span className="section-label">IN CONSULTATION</span>
            <span className="queue-count">{calledTokens.length} active</span>
          </div>
          <div className="token-list">
            {calledTokens.map((token) => (
              <div key={token.id} className="token-item called">
                <span className="token-num">#{token.token_number}</span>
                <span className="token-name">{token.patient_name}</span>
                <span className="token-room">
                  {token.room && <span className="room-badge">Room: {token.room}</span>}
                </span>
                <span className={`status-badge ${token.status.toLowerCase()}`}>
                  {token.status.replace('_', ' ')}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <style jsx>{`
        .waiting-display {
          padding: 24px;
          max-width: 100%;
          height: 100vh;
          display: flex;
          flex-direction: column;
          background: #0f172a;
          color: #f8fafc;
          font-family: 'Segoe UI', system-ui, sans-serif;
        }
        .section-label {
          font-size: 14px;
          font-weight: 600;
          color: #94a3b8;
          text-transform: uppercase;
          letter-spacing: 0.1em;
          margin-bottom: 8px;
        }
        .current-token-section {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 40px 20px;
          text-align: center;
        }
        .token-display {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 16px;
        }
        .token-number-large {
          font-size: clamp(120px, 20vw, 200px);
          font-weight: 800;
          color: #22c55e;
          font-family: 'SF Mono', 'Monospace', monospace;
          text-shadow: 0 0 40px rgba(34, 197, 94, 0.5), 0 0 80px rgba(34, 197, 94, 0.3);
          animation: pulse 2s ease-in-out infinite;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.8; transform: scale(1.02); }
        }
        .room-display {
          font-size: clamp(24px, 4vw, 36px);
          font-weight: 600;
          color: #3b82f6;
          background: rgba(59, 130, 246, 0.1);
          padding: 12px 32px;
          border-radius: 12px;
          border: 2px solid rgba(59, 130, 246, 0.3);
        }
        .next-token-section {
          padding: 24px;
          text-align: center;
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.1), rgba(139, 92, 246, 0.1));
          border-radius: 16px;
          margin: 0 24px 24px;
          border: 1px solid rgba(59, 130, 246, 0.2);
        }
        .next-token-display {
          font-size: clamp(48px, 8vw, 72px);
          font-weight: 700;
          color: #3b82f6;
          font-family: 'SF Mono', 'Monospace', monospace;
        }
        .queue-section, .called-section {
          flex: 1;
          padding: 0 24px 24px;
          overflow-y: auto;
        }
        .called-section {
          border-top: 1px solid rgba(148, 163, 184, 0.1);
        }
        .section-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
          padding-bottom: 12px;
          border-bottom: 1px solid rgba(148, 163, 184, 0.1);
        }
        .queue-count {
          font-size: 14px;
          color: #94a3b8;
        }
        .token-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .token-item {
          display: grid;
          grid-template-columns: 80px 1fr auto auto;
          align-items: center;
          gap: 16px;
          padding: 16px 20px;
          background: rgba(30, 41, 59, 0.8);
          border-radius: 12px;
          border: 1px solid rgba(148, 163, 184, 0.1);
          transition: all 0.2s;
        }
        .token-item:hover {
          border-color: rgba(59, 130, 246, 0.3);
          background: rgba(30, 41, 59, 1);
        }
        .token-item.called {
          border-color: rgba(59, 130, 246, 0.3);
        }
        .token-num {
          font-size: 20px;
          font-weight: 700;
          color: #3b82f6;
          font-family: 'SF Mono', monospace;
        }
        .token-name {
          font-size: 16px;
          font-weight: 500;
          color: #f8fafc;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .token-meta {
          font-size: 13px;
          color: #94a3b8;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .token-room {
          display: flex;
          align-items: center;
        }
        .room-badge {
          background: rgba(34, 197, 94, 0.15);
          color: #22c55e;
          padding: 4px 12px;
          border-radius: 20px;
          font-size: 12px;
          font-weight: 600;
        }
        .status-badge {
          padding: 6px 12px;
          border-radius: 20px;
          font-size: 11px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          white-space: nowrap;
        }
        .status-badge.waiting { background: rgba(245, 158, 11, 0.2); color: #f59e0b; }
        .status-badge.called { background: rgba(59, 130, 246, 0.2); color: #3b82f6; }
        .status-badge.in_progress { background: rgba(139, 92, 246, 0.2); color: #8b5cf6; }
        .empty-queue {
          text-align: center;
          padding: 40px;
          color: #64748b;
          font-size: 16px;
        }
        .loading, .error {
          text-align: center;
          padding: 60px;
          color: #64748b;
          font-size: 18px;
        }
        .error { color: #ef4444; }

        @media (max-width: 768px) {
          .token-item {
            grid-template-columns: 70px 1fr;
            grid-template-rows: auto auto;
          }
          .token-meta { grid-column: 2; }
          .token-room { grid-column: 2; justify-self: start; }
          .status-badge { grid-column: 1 / -1; justify-self: end; }
        }
      `}</style>
    </div>
  );
};

export default WaitingDisplay;