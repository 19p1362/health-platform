import React, { useState } from 'react';
import {
  Settings as SettingsIcon,
  User,
  Shield,
  Key,
  Bell,
  Database,
  AlertTriangle,
  Download,
  Trash2,
  Eye,
  EyeOff,
  Save,
  Check,
  Copy,
} from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

const Settings: React.FC = () => {
  const { currentUser } = useAuth();

  const [profileName, setProfileName] = useState(currentUser?.name || '');
  const [profileEmail, setProfileEmail] = useState(currentUser?.email || '');
  const [profileSaved, setProfileSaved] = useState(false);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [passwordSaved, setPasswordSaved] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const [apiKey, setApiKey] = useState('sk-hb-' + Math.random().toString(36).substring(2, 15));
  const [apiKeyCopied, setApiKeyCopied] = useState(false);

  const [notifyEmail, setNotifyEmail] = useState(true);
  const [notifyBreach, setNotifyBreach] = useState(true);
  const [notifyWeekly, setNotifyWeekly] = useState(false);

  const [retentionPeriod, setRetentionPeriod] = useState('3years');
  const [autoErasure, setAutoErasure] = useState(true);

  const handleSaveProfile = (e: React.FormEvent) => {
    e.preventDefault();
    setProfileSaved(true);
    setTimeout(() => setProfileSaved(false), 2000);
  };

  const handleChangePassword = (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError('');

    if (!currentPassword) {
      setPasswordError('Current password is required');
      return;
    }
    if (newPassword.length < 8) {
      setPasswordError('New password must be at least 8 characters');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match');
      return;
    }

    setPasswordSaved(true);
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setTimeout(() => setPasswordSaved(false), 2000);
  };

  const handleCopyApiKey = () => {
    navigator.clipboard.writeText(apiKey);
    setApiKeyCopied(true);
    setTimeout(() => setApiKeyCopied(false), 2000);
  };

  const handleRegenerateApiKey = () => {
    setApiKey('sk-hb-' + Math.random().toString(36).substring(2, 15));
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1>Settings</h1>
        <p className="text-muted text-sm">Manage your account and platform preferences</p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 720 }}>
        {/* Profile Section */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <User size={18} />
              Profile
            </div>
          </div>
          <form onSubmit={handleSaveProfile}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Name</label>
                <input
                  type="text"
                  className="form-input"
                  value={profileName}
                  onChange={(e) => setProfileName(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Email</label>
                <input
                  type="email"
                  className="form-input"
                  value={profileEmail}
                  onChange={(e) => setProfileEmail(e.target.value)}
                />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Role</label>
              <input
                type="text"
                className="form-input"
                value={currentUser?.role || 'Practitioner'}
                disabled
                style={{ opacity: 0.6 }}
              />
            </div>
            <button type="submit" className="btn btn-primary">
              {profileSaved ? (
                <><Check size={16} style={{ color: 'var(--success)' }} /> Saved</>
              ) : (
                <><Save size={16} /> Save Changes</>
              )}
            </button>
          </form>
        </div>

        {/* Security Section */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Shield size={18} />
              Security
            </div>
          </div>
          <form onSubmit={handleChangePassword}>
            <div className="form-group">
              <label className="form-label">Current Password</label>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  className="form-input"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  style={{ paddingRight: 40 }}
                />
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ position: 'absolute', right: 4, top: '50%', transform: 'translateY(-50%)' }}
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">New Password</label>
                <input
                  type="password"
                  className="form-input"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Min. 8 characters"
                />
              </div>
              <div className="form-group">
                <label className="form-label">Confirm New Password</label>
                <input
                  type="password"
                  className={`form-input ${passwordError ? 'error' : ''}`}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>
            </div>
            {passwordError && <div className="form-error">{passwordError}</div>}
            <button type="submit" className="btn btn-primary">
              {passwordSaved ? (
                <><Check size={16} style={{ color: 'var(--success)' }} /> Password Updated</>
              ) : (
                <><Save size={16} /> Change Password</>
              )}
            </button>
          </form>
        </div>

        {/* API Key Management */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Key size={18} />
              API Keys
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Your API Key</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                className="form-input"
                value={apiKey}
                readOnly
                style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}
              />
              <button className="btn btn-secondary" onClick={handleCopyApiKey}>
                {apiKeyCopied ? <Check size={16} style={{ color: 'var(--success)' }} /> : <Copy size={16} />}
              </button>
            </div>
          </div>
          <button className="btn btn-secondary" onClick={handleRegenerateApiKey}>
            <Key size={16} />
            Regenerate Key
          </button>
        </div>

        {/* Notification Preferences */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Bell size={18} />
              Notification Preferences
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label className="form-checkbox">
              <input
                type="checkbox"
                checked={notifyEmail}
                onChange={(e) => setNotifyEmail(e.target.checked)}
              />
              <span>Email notifications for audit events</span>
            </label>
            <label className="form-checkbox">
              <input
                type="checkbox"
                checked={notifyBreach}
                onChange={(e) => setNotifyBreach(e.target.checked)}
              />
              <span>Immediate alerts for breach events</span>
            </label>
            <label className="form-checkbox">
              <input
                type="checkbox"
                checked={notifyWeekly}
                onChange={(e) => setNotifyWeekly(e.target.checked)}
              />
              <span>Weekly compliance summary</span>
            </label>
          </div>
        </div>

        {/* Data Retention Preferences */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Database size={18} />
              Data Retention Preferences
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Audit Log Retention Period</label>
            <select
              className="form-select"
              value={retentionPeriod}
              onChange={(e) => setRetentionPeriod(e.target.value)}
            >
              <option value="1year">1 Year (Minimum)</option>
              <option value="3years">3 Years (DPDP 2025 Standard)</option>
              <option value="5years">5 Years</option>
              <option value="10years">10 Years</option>
            </select>
          </div>
          <label className="form-checkbox" style={{ marginTop: 8 }}>
            <input
              type="checkbox"
              checked={autoErasure}
              onChange={(e) => setAutoErasure(e.target.checked)}
            />
            <span>Auto-erase data after retention period (per DPDP 2025)</span>
          </label>
        </div>

        {/* Danger Zone */}
        <div className="danger-zone">
          <div className="danger-zone-title">
            <AlertTriangle size={18} />
            Danger Zone
          </div>
          <div className="danger-zone-text">
            These actions are irreversible. Please proceed with caution.
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <button className="btn btn-danger">
              <Download size={16} />
              Export All Data
            </button>
            <button className="btn btn-danger" onClick={() => {
              if (window.confirm('Are you sure you want to delete your account? This action cannot be undone.')) {
                // Account deletion logic
              }
            }}>
              <Trash2 size={16} />
              Delete Account
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;
