import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Stethoscope, Building2, User, ArrowRight, ArrowLeft, CheckCircle, Shield, AlertCircle, Loader } from 'lucide-react';

type Step = 'org' | 'admin' | 'confirm';

const Signup: React.FC = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>('org');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [org, setOrg] = useState({ name: '', email: '', phone: '', address: '' });
  const [admin, setAdmin] = useState({ email: '', password: '', full_name: '' });
  const [result, setResult] = useState<any>(null);

  const handleOrgSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!org.name.trim()) { setError('Organization name is required'); return; }
    setError('');
    setStep('admin');
  };

  const handleAdminSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!admin.email.trim() || !admin.password || !admin.full_name.trim()) {
      setError('All fields are required'); return;
    }
    if (admin.password.length < 8) { setError('Password must be at least 8 characters'); return; }
    setError('');
    setStep('confirm');
  };

  const handleRegister = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/v1/organizations/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          organization_name: org.name,
          organization_email: org.email || undefined,
          organization_phone: org.phone || undefined,
          address: org.address || undefined,
          admin_email: admin.email,
          admin_password: admin.password,
          admin_full_name: admin.full_name,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Registration failed');
      setResult(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (result) {
    return (
      <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40 }}>
        <div style={{ maxWidth: 480, width: '100%', textAlign: 'center' }}>
          <div style={{ width: 64, height: 64, borderRadius: 16, background: 'rgba(20, 184, 166, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 24px' }}>
            <CheckCircle size={32} color="#14b8a6" />
          </div>
          <h1 style={{ fontSize: '1.8rem', fontWeight: 700, marginBottom: 8 }}>Welcome to HealthBridge!</h1>
          <p style={{ color: '#94a3b8', marginBottom: 24 }}>Your organization <strong>{result.org_name}</strong> is ready.</p>
          <div style={{ background: '#1e293b', borderRadius: 12, padding: 24, marginBottom: 24, textAlign: 'left' }}>
            <p style={{ margin: '0 0 12px', fontSize: 14, color: '#94a3b8' }}>Sign in with your admin credentials:</p>
            <div style={{ fontSize: 14, marginBottom: 4 }}><span style={{ color: '#94a3b8' }}>Email:</span> {result.user_email}</div>
            <div style={{ fontSize: 14, marginBottom: 16 }}><span style={{ color: '#94a3b8' }}>Organization:</span> {result.org_name}</div>
            <div style={{ display: 'flex', gap: 4, fontSize: 12, color: '#f59e0b', background: 'rgba(245, 158, 11, 0.1)', padding: '8px 12px', borderRadius: 8 }}>
              <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
              <span>Save your credentials. You'll need them to sign in.</span>
            </div>
          </div>
          <button onClick={() => { localStorage.setItem('healthbridge_token', result.access_token); navigate('/'); }}
            style={{ width: '100%', padding: '14px', borderRadius: 10, border: 'none', background: 'linear-gradient(135deg, #14b8a6, #0d9488)', color: 'white', cursor: 'pointer', fontWeight: 600, fontSize: 16 }}>
            Go to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '10px 14px', borderRadius: 8, border: '1px solid #334155',
    background: '#0f172a', color: '#e2e8f0', fontSize: 14, outline: 'none', boxSizing: 'border-box',
  };

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40 }}>
      <div style={{ maxWidth: 480, width: '100%' }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, marginBottom: 32 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg, #14b8a6, #0d9488)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Stethoscope size={18} color="white" />
          </div>
          <span style={{ fontSize: '1.2rem', fontWeight: 700 }}>HealthBridge</span>
        </div>

        {/* Steps */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginBottom: 32 }}>
          {['org', 'admin', 'confirm'].map((s, i) => (
            <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: step === s ? 'linear-gradient(135deg, #14b8a6, #0d9488)' : 
                  ['org','admin','confirm'].indexOf(step) > i ? '#14b8a6' : '#334155',
                color: 'white', fontSize: 13, fontWeight: 600 }}>{i + 1}</div>
              <span style={{ fontSize: 13, color: step === s ? '#e2e8f0' : '#64748b', display: ['org','admin','confirm'].indexOf(step) >= i ? 'block' : 'none' }}>
                {['Clinic', 'Admin', 'Confirm'][i]}
              </span>
              {i < 2 && <div style={{ width: 24, height: 1, background: '#334155' }} />}
            </div>
          ))}
        </div>

        <div style={{ background: '#1e293b', borderRadius: 16, padding: 32, border: '1px solid #334155' }}>
          {error && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', borderRadius: 8, background: 'rgba(239, 68, 68, 0.1)', color: '#fca5a5', fontSize: 13, marginBottom: 16 }}>
              <AlertCircle size={16} /> {error}
            </div>
          )}

          {step === 'org' && (
            <form onSubmit={handleOrgSubmit}>
              <h2 style={{ fontSize: '1.3rem', fontWeight: 700, marginBottom: 4 }}>Your Clinic</h2>
              <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 24 }}>Tell us about your healthcare organization.</p>
              
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 13, marginBottom: 6, color: '#94a3b8' }}>Organization name *</label>
                <input style={inputStyle} placeholder="e.g. Apollo Clinic - Hyderabad" value={org.name} onChange={e => setOrg({...org, name: e.target.value})} />
              </div>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 13, marginBottom: 6, color: '#94a3b8' }}>Organization email</label>
                <input style={inputStyle} type="email" placeholder="clinic@hospital.org" value={org.email} onChange={e => setOrg({...org, email: e.target.value})} />
              </div>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 13, marginBottom: 6, color: '#94a3b8' }}>Phone</label>
                <input style={inputStyle} placeholder="+91 98765 43210" value={org.phone} onChange={e => setOrg({...org, phone: e.target.value})} />
              </div>
              <div style={{ marginBottom: 24 }}>
                <label style={{ display: 'block', fontSize: 13, marginBottom: 6, color: '#94a3b8' }}>Address</label>
                <textarea style={{...inputStyle, resize: 'vertical', minHeight: 60}} placeholder="Clinic address" value={org.address} onChange={e => setOrg({...org, address: e.target.value})} />
              </div>
              <button type="submit" style={{ width: '100%', padding: '12px', borderRadius: 10, border: 'none', background: 'linear-gradient(135deg, #14b8a6, #0d9488)', color: 'white', cursor: 'pointer', fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                Next <ArrowRight size={18} />
              </button>
            </form>
          )}

          {step === 'admin' && (
            <form onSubmit={handleAdminSubmit}>
              <h2 style={{ fontSize: '1.3rem', fontWeight: 700, marginBottom: 4 }}>Admin Account</h2>
              <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 24 }}>Create the administrator account for your organization.</p>
              
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 13, marginBottom: 6, color: '#94a3b8' }}>Full name *</label>
                <input style={inputStyle} placeholder="Dr. Sameer Kumar" value={admin.full_name} onChange={e => setAdmin({...admin, full_name: e.target.value})} />
              </div>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 13, marginBottom: 6, color: '#94a3b8' }}>Email *</label>
                <input style={inputStyle} type="email" placeholder="dr.sameer@hospital.org" value={admin.email} onChange={e => setAdmin({...admin, email: e.target.value})} />
              </div>
              <div style={{ marginBottom: 24 }}>
                <label style={{ display: 'block', fontSize: 13, marginBottom: 6, color: '#94a3b8' }}>Password *</label>
                <input style={inputStyle} type="password" placeholder="At least 8 characters" value={admin.password} onChange={e => setAdmin({...admin, password: e.target.value})} />
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>Min 8 characters. Use a strong password.</div>
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <button type="button" onClick={() => setStep('org')} style={{ flex: 1, padding: '12px', borderRadius: 10, border: '1px solid #334155', background: 'transparent', color: '#e2e8f0', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  <ArrowLeft size={18} /> Back
                </button>
                <button type="submit" style={{ flex: 2, padding: '12px', borderRadius: 10, border: 'none', background: 'linear-gradient(135deg, #14b8a6, #0d9488)', color: 'white', cursor: 'pointer', fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  Next <ArrowRight size={18} />
                </button>
              </div>
            </form>
          )}

          {step === 'confirm' && (
            <div>
              <h2 style={{ fontSize: '1.3rem', fontWeight: 700, marginBottom: 4 }}>Confirm & Register</h2>
              <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 24 }}>Review your details before creating your organization.</p>

              <div style={{ background: '#0f172a', borderRadius: 10, padding: 20, marginBottom: 24 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: '#14b8a6' }}><Building2 size={14} style={{ marginRight: 6 }} />Organization</h3>
                <div style={{ fontSize: 13, marginBottom: 4 }}>{org.name}</div>
                {org.email && <div style={{ fontSize: 13, color: '#94a3b8' }}>{org.email}</div>}
                {org.phone && <div style={{ fontSize: 13, color: '#94a3b8' }}>{org.phone}</div>}
                {org.address && <div style={{ fontSize: 13, color: '#94a3b8', marginTop: 4 }}>{org.address}</div>}

                <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, marginTop: 20, color: '#14b8a6' }}><User size={14} style={{ marginRight: 6 }} />Admin</h3>
                <div style={{ fontSize: 13, marginBottom: 4 }}>{admin.full_name}</div>
                <div style={{ fontSize: 13, color: '#94a3b8' }}>{admin.email}</div>
              </div>

              <div style={{ display: 'flex', gap: 12 }}>
                <button type="button" onClick={() => setStep('admin')} style={{ flex: 1, padding: '12px', borderRadius: 10, border: '1px solid #334155', background: 'transparent', color: '#e2e8f0', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  <ArrowLeft size={18} /> Back
                </button>
                <button onClick={handleRegister} disabled={loading} style={{ flex: 2, padding: '12px', borderRadius: 10, border: 'none', background: 'linear-gradient(135deg, #14b8a6, #0d9488)', color: 'white', cursor: loading ? 'not-allowed' : 'pointer', fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, opacity: loading ? 0.7 : 1 }}>
                  {loading ? <><Loader size={18} className="spinner" /> Creating...</> : <>Create Organization <CheckCircle size={18} /></>}
                </button>
              </div>
            </div>
          )}
        </div>

        <p style={{ textAlign: 'center', fontSize: 13, color: '#64748b', marginTop: 24 }}>
          Already have an account? <Link to="/login" style={{ color: '#14b8a6', textDecoration: 'none' }}>Sign in</Link>
        </p>
      </div>
    </div>
  );
};

export default Signup;
