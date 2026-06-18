import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Shield, Stethoscope, Activity, Upload, Brain, FileText, Users, Lock, ArrowRight, CheckCircle } from 'lucide-react';

const Landing: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0' }}>
      {/* Nav */}
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 40px', borderBottom: '1px solid #1e293b' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg, #14b8a6, #0d9488)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Stethoscope size={18} color="white" />
          </div>
          <span style={{ fontSize: '1.2rem', fontWeight: 700 }}>HealthBridge</span>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button onClick={() => navigate('/login')} style={{ padding: '8px 20px', borderRadius: 8, border: '1px solid #334155', background: 'transparent', color: '#e2e8f0', cursor: 'pointer', fontSize: 14 }}>Sign In</button>
          <button onClick={() => navigate('/signup')} style={{ padding: '8px 20px', borderRadius: 8, border: 'none', background: 'linear-gradient(135deg, #14b8a6, #0d9488)', color: 'white', cursor: 'pointer', fontWeight: 600, fontSize: 14 }}>Get Started</button>
        </div>
      </header>

      {/* Hero */}
      <section style={{ textAlign: 'center', padding: '80px 40px 60px', maxWidth: 800, margin: '0 auto' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 20, background: 'rgba(20, 184, 166, 0.1)', color: '#14b8a6', fontSize: 13, marginBottom: 24 }}>
          <Shield size={14} /> DPDP 2025 Compliant
        </div>
        <h1 style={{ fontSize: '3rem', fontWeight: 800, lineHeight: 1.1, margin: '0 0 16px', background: 'linear-gradient(135deg, #e2e8f0, #14b8a6)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
          From Paper Records to AI-Powered Patient Care
        </h1>
        <p style={{ fontSize: '1.1rem', color: '#94a3b8', lineHeight: 1.6, maxWidth: 600, margin: '0 auto 32px' }}>
          The unified healthcare platform that converts photos, PDFs, and scans into structured FHIR records — then deploys 10 AI agents to monitor every patient, 24/7.
        </p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
          <button onClick={() => navigate('/signup')} style={{ padding: '14px 32px', borderRadius: 10, border: 'none', background: 'linear-gradient(135deg, #14b8a6, #0d9488)', color: 'white', cursor: 'pointer', fontWeight: 600, fontSize: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
            Start Free <ArrowRight size={18} />
          </button>
          <button onClick={() => navigate('/login')} style={{ padding: '14px 32px', borderRadius: 10, border: '1px solid #334155', background: 'transparent', color: '#e2e8f0', cursor: 'pointer', fontSize: 16 }}>Sign In</button>
        </div>
      </section>

      {/* Features */}
      <section style={{ padding: '60px 40px', maxWidth: 1100, margin: '0 auto' }}>
        <h2 style={{ textAlign: 'center', fontSize: '1.8rem', fontWeight: 700, marginBottom: 48 }}>Everything you need to digitize your clinic</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24 }}>
          {[
            { icon: <Upload size={24} />, title: 'Document Ingestion', desc: 'Snap a photo of any prescription, lab report, or discharge summary. AI extracts structured data automatically.' },
            { icon: <FileText size={24} />, title: 'FHIR R4 API', desc: 'Every record becomes a standards-compliant FHIR resource. Interoperable with ABDM, Epic, and Cerner.' },
            { icon: <Brain size={24} />, title: '10 AI Care Agents', desc: 'Agents monitor medications, follow-ups, lab results, risk scores, and insurance claims around the clock.' },
            { icon: <Users size={24} />, title: 'Multi-tenant SaaS', desc: 'One platform for your entire clinic. Doctors, nurses, coordinators — each with role-based access.' },
            { icon: <Lock size={24} />, title: 'DPDP 2025 Compliant', desc: 'End-to-end encryption, consent management, audit logging, breach detection. Built for India\'s data protection law.' },
            { icon: <Activity size={24} />, title: 'WhatsApp Integration', desc: 'Patients send documents via WhatsApp. Receive automated appointment reminders, medication alerts, and test results.' },
          ].map((f, i) => (
            <div key={i} style={{ padding: 28, borderRadius: 12, background: '#1e293b', border: '1px solid #334155' }}>
              <div style={{ width: 44, height: 44, borderRadius: 10, background: 'rgba(20, 184, 166, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16, color: '#14b8a6' }}>{f.icon}</div>
              <h3 style={{ margin: '0 0 8px', fontSize: 16, fontWeight: 600, color: '#f1f5f9' }}>{f.title}</h3>
              <p style={{ margin: 0, fontSize: 14, color: '#94a3b8', lineHeight: 1.6 }}>{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section style={{ padding: '60px 40px', maxWidth: 1100, margin: '0 auto' }}>
        <h2 style={{ textAlign: 'center', fontSize: '1.8rem', fontWeight: 700, marginBottom: 8 }}>Simple pricing</h2>
        <p style={{ textAlign: 'center', color: '#94a3b8', marginBottom: 48 }}>Start free. Upgrade when you grow.</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
          {[
            { name: 'Free', price: '₹0', patients: '100', staff: '5', features: ['Document ingestion', 'FHIR API', '1 AI agent', 'Email support'] },
            { name: 'Starter', price: '₹9,999/mo', patients: '1,000', staff: '15', features: ['All Free features', '10 AI agents', 'WhatsApp integration', 'DPDP compliance suite', 'Email + chat support'] },
            { name: 'Professional', price: '₹29,999/mo', patients: '10,000', staff: '50', features: ['All Starter features', 'ABDM integration', 'Custom AI agents', 'Priority support', 'API rate limit increase'] },
            { name: 'Enterprise', price: 'Custom', patients: 'Unlimited', staff: 'Unlimited', features: ['All Professional features', 'On-premise deployment', 'SLA guarantee', 'Dedicated support', 'Custom integrations'] },
          ].map((p, i) => (
            <div key={i} style={{ padding: 28, borderRadius: 12, background: i === 1 ? '#1e293b' : '#0f172a', border: i === 1 ? '2px solid #14b8a6' : '1px solid #1e293b', position: 'relative' }}>
              {i === 1 && <div style={{ position: 'absolute', top: -12, left: '50%', transform: 'translateX(-50%)', padding: '4px 16px', borderRadius: 20, background: '#14b8a6', color: 'white', fontSize: 12, fontWeight: 600 }}>Popular</div>}
              <h3 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 600 }}>{p.name}</h3>
              <div style={{ fontSize: '1.8rem', fontWeight: 700, marginBottom: 16 }}>{p.price}</div>
              <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 16 }}>{p.patients} patients · {p.staff} staff</div>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {p.features.map((f, j) => (
                  <li key={j} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#cbd5e1', marginBottom: 8 }}>
                    <CheckCircle size={14} color="#14b8a6" /> {f}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section style={{ textAlign: 'center', padding: '80px 40px' }}>
        <h2 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: 12 }}>Ready to digitize your clinic?</h2>
        <p style={{ color: '#94a3b8', marginBottom: 24 }}>Free plan includes 100 patients and 5 staff. No credit card required.</p>
        <button onClick={() => navigate('/signup')} style={{ padding: '14px 40px', borderRadius: 10, border: 'none', background: 'linear-gradient(135deg, #14b8a6, #0d9488)', color: 'white', cursor: 'pointer', fontWeight: 600, fontSize: 16 }}>Create Your Organization</button>
      </section>

      {/* Footer */}
      <footer style={{ textAlign: 'center', padding: '24px 40px', borderTop: '1px solid #1e293b', color: '#64748b', fontSize: 13 }}>
        HealthBridge Platform — DPDP 2025 Compliant · ABDM Integrated · Made in India
      </footer>
    </div>
  );
};

export default Landing;
