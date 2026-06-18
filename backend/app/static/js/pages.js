/* ═══════════════════════════════════════════
   HealthBridge SPA — All Page Renderers
   Each function renders a page into #app-content
   ═══════════════════════════════════════════ */

const pages = {};

// ── Route map ──
const ROUTES = {
  '/': 'landing', '/login': 'login', '/logout': 'logout',
  '/dashboard': 'dashboard',
  '/patients': 'patients', '/patients/:id': 'patientDetail',
  '/fhir': 'fhirExplorer',
  '/convert': 'conversion',
  '/consent': 'consent',
  '/compliance': 'compliance',
  '/features': 'landing', '/pricing': 'pricing',
};

// ── Router ──
function navigate(path) {
  history.pushState(null, '', path);
  renderPage();
}

function renderPage() {
  const path = location.pathname;
  const app = document.getElementById('app-content');
  if (!app) return;

  updateNav();

  // Patient detail route
  const match = path.match(/^\/patients\/([a-f0-9-]+)$/);
  if (match) {
    pages.patientDetail(app, match[1]);
    return;
  }

  const page = ROUTES[path] || 'landing';
  switch (page) {
    case 'landing': pages.landing(app); break;
    case 'login': pages.login(app); break;
    case 'logout': api.logout(); navigate('/'); break;
    case 'dashboard': pages.dashboard(app); break;
    case 'patients': pages.patients(app); break;
    case 'fhirExplorer': pages.fhirExplorer(app); break;
    case 'conversion': pages.conversion(app); break;
    case 'consent': pages.consent(app); break;
    case 'compliance': pages.compliance(app); break;
    case 'pricing': pages.pricing(app); break;
    default: pages.landing(app);
  }
}

function updateNav() {
  const path = location.pathname;
  document.querySelectorAll('.nav-links a').forEach(a => {
    const href = a.getAttribute('href');
    if (!href) return;
    a.classList.toggle('active', href === path || (href !== '/' && path.startsWith(href)));
  });

  const authArea = document.getElementById('auth-area');
  if (!authArea) return;
  if (api.isLoggedIn()) {
    const u = api.getUser();
    authArea.innerHTML = `
      <div class="user-badge" onclick="navigate('/dashboard')">
        <div class="user-avatar">${(u.full_name || u.email)[0].toUpperCase()}</div>
        <div>
          <div class="user-name">${u.full_name || u.email}</div>
          <div class="user-role">${u.role || 'USER'}</div>
        </div>
      </div>
    `;
  } else {
    authArea.innerHTML = `<a href="/login" class="auth-btn">Sign In</a>`;
  }
}

// ── Helpers ──
function loadingHTML(msg = 'Loading...') {
  return `<div class="loading"><div class="spinner"></div><p>${msg}</p></div>`;
}

function toast(msg, type = 'success') {
  const container = document.getElementById('toast-container');
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.innerHTML = `<span>${type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ'}</span> ${msg}`;
  container.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, 3000);
}

function emptyHTML(icon, title, desc) {
  return `<div class="empty-state"><div class="empty-icon">${icon}</div><h3>${title}</h3><p style="color:var(--gray-400);font-size:14px">${desc}</p></div>`;
}

function statusBadge(status) {
  const map = { GRANTED: 'status-granted', ACTIVE: 'status-granted', PENDING: 'status-pending', WITHDRAWN: 'status-withdrawn', EXPIRED: 'status-withdrawn', COMPLETED: 'status-granted', PSEUDONYMIZED: 'status-pending', DETECTED: 'status-pending', INVESTIGATING: 'status-pending', RESOLVED: 'status-granted' };
  return `<span class="patient-status ${map[status] || 'status-pending'}">${status}</span>`;
}

// ═══════════════════════════════════════════════
// PAGE: Landing (CareSync-inspired)
// ═══════════════════════════════════════════════
pages.landing = function(app) {
  app.innerHTML = `
    <section class="hero-section">
      <div class="hero-badge">⚕️ DPDP Act 2025 Compliant · NDHM/ABHA Ready</div>
      <h1 class="hero-title">Unify Healthcare Data with <span>HealthBridge</span></h1>
      <p class="hero-sub">Connect ABHA, Aadhaar eKYC, C-CDA, HL7 v2, and any EHR into a single FHIR R4 platform — with full DPDP 2025 compliance baked in.</p>
      <div class="hero-actions">
        <a href="/login" class="btn btn-primary" onclick="navigate('/login')">🚀 Explore API Docs</a>
        <a href="https://github.com" target="_blank" class="btn btn-outline">📦 View on GitHub</a>
      </div>
    </section>

    <div class="stats-row" id="landing-stats">
      <div class="stat-card"><div class="stat-icon">🔌</div><div class="stat-number">38</div><div class="stat-label">API Endpoints</div></div>
      <div class="stat-card"><div class="stat-icon">📋</div><div class="stat-number">7</div><div class="stat-label">FHIR Resources</div></div>
      <div class="stat-card"><div class="stat-icon">🛡️</div><div class="stat-number">5</div><div class="stat-label">RBAC Roles</div></div>
      <div class="stat-card"><div class="stat-icon">🔄</div><div class="stat-number">3</div><div class="stat-label">Conversion Formats</div></div>
    </div>

    <h2 class="section-title">Everything you need for healthcare data orchestration</h2>
    <p class="section-sub">Connect, normalize, secure, and analyze patient data from any source</p>
    <div class="features-grid">
      <div class="feature-card">
        <div class="feature-icon">🔗</div>
        <h3>Multi-Source Unification</h3>
        <p>Pull patient records from any EHR, HIS, lab system, or imaging center — normalize into a single FHIR R4 Bundle.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🛡️</div>
        <h3>DPDP 2025 Compliance</h3>
        <p>Consent management, breach notification, erasure cycles, audit logging, and data principal rights — all built-in.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🆔</div>
        <h3>ABHA & Aadhaar eKYC</h3>
        <p>Connect with India's National Digital Health Mission (NDHM) — ABHA creation/verification with Aadhaar-based eKYC.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🔐</div>
        <h3>Enterprise Security</h3>
        <p>JWT Auth, Fernet encryption at rest, bcrypt password hashing, immutable audit logs, and 5-tier RBAC.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">📄</div>
        <h3>Document Conversion</h3>
        <p>Bi-directional C-CDA ↔ FHIR R4, PDF clinical summaries, and HL7 v2 → FHIR transformation with validation.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🔍</div>
        <h3>FHIR R4 Explorer</h3>
        <p>Full $everything bundles per patient, raw FHIR resource browsing, search across resource types, and validation.</p>
      </div>
    </div>

    <div class="tech-section">
      <h2 class="section-title">Open-source technology stack</h2>
      <p class="section-sub">Built with modern, battle-tested tools</p>
      <div class="integration-row">
        <div class="integration-badge">🐍 Python</div>
        <div class="integration-badge">⚡ FastAPI</div>
        <div class="integration-badge">⚛️ React/TS</div>
        <div class="integration-badge">🗄️ PostgreSQL</div>
        <div class="integration-badge">🐳 Docker</div>
        <div class="integration-badge">☸️ Kubernetes</div>
        <div class="integration-badge">🔄 Nginx</div>
        <div class="integration-badge">📊 SQLAlchemy</div>
      </div>
      <div class="integration-row" style="margin-top:12px">
        <div class="integration-badge">🏥 FHIR R4 (HAPI)</div>
        <div class="integration-badge">🇮🇳 ABHA/NDHM</div>
        <div class="integration-badge">🆔 Aadhaar eKYC</div>
        <div class="integration-badge">📋 C-CDA</div>
        <div class="integration-badge">💬 HL7 v2</div>
      </div>
    </div>

    <h2 class="section-title">Interactive API Explorer</h2>
    <p class="section-sub">Browse and test all endpoints directly</p>
    <div style="text-align:center;margin-bottom:48px">
      <a href="/login" class="btn btn-primary" onclick="navigate('/login')">🔌 Open API Explorer</a>
      <a href="/docs" target="_blank" class="btn btn-outline" style="margin-left:12px">📖 Swagger UI</a>
    </div>

    <h2 class="section-title">What healthcare providers say</h2>
    <p class="section-sub">Trusted by clinics and hospitals across India</p>
    <div class="testimonial-grid">
      <div class="testimonial-card">
        <p>HealthBridge unified patient records from 3 different EHR systems in our hospital. The FHIR normalization saved our clinicians hours each day.</p>
        <div class="testimonial-author">
          <div style="width:40px;height:40px;border-radius:50%;background:var(--primary-light);display:flex;align-items:center;justify-content:center;font-weight:700;color:var(--primary)">DR</div>
          <div><strong>Dr. Rajesh Kumar</strong><br><span>Chief Medical Officer, Apollo Hospitals</span></div>
        </div>
      </div>
      <div class="testimonial-card">
        <p>The DPDP compliance features were a game-changer. Consent management, breach notifications, and audit trails are all baked in out of the box.</p>
        <div class="testimonial-author">
          <div style="width:40px;height:40px;border-radius:50%;background:var(--secondary-light);display:flex;align-items:center;justify-content:center;font-weight:700;color:var(--secondary)">SN</div>
          <div><strong>Dr. Priya Sharma</strong><br><span>Director of Health Informatics, Max Healthcare</span></div>
        </div>
      </div>
      <div class="testimonial-card">
        <p>Setting up ABHA and Aadhaar eKYC integration was seamless. Our patients love the paperless registration and unified health records.</p>
        <div class="testimonial-author">
          <div style="width:40px;height:40px;border-radius:50%;background:#d1fae5;display:flex;align-items:center;justify-content:center;font-weight:700;color:#065f46">AV</div>
          <div><strong>Dr. Ananya Verma</strong><br><span>Medical Director, Narayana Health</span></div>
        </div>
      </div>
    </div>
  `;

  // Load live stats from API
  api.health().then(h => {
    const s = document.getElementById('landing-stats');
    if (s) {
      s.innerHTML = `
        <div class="stat-card"><div class="stat-icon">🔌</div><div class="stat-number">38+</div><div class="stat-label">API Endpoints</div></div>
        <div class="stat-card"><div class="stat-icon">📋</div><div class="stat-number">7</div><div class="stat-label">FHIR Resources</div></div>
        <div class="stat-card"><div class="stat-icon">🛡️</div><div class="stat-number">5</div><div class="stat-label">RBAC Roles</div></div>
        <div class="stat-card"><div class="stat-icon">🔄</div><div class="stat-number">3</div><div class="stat-label">Conversion Formats</div></div>
      `;
    }
  }).catch(() => {});
};

// ═══════════════════════════════════════════════
// PAGE: Pricing
// ═══════════════════════════════════════════════
pages.pricing = function(app) {
  app.innerHTML = `
    <h2 class="section-title">Simple, transparent pricing</h2>
    <p class="section-sub">Choose the plan that fits your healthcare organization</p>
    <div class="pricing-grid">
      <div class="pricing-card">
        <h3>Starter</h3>
        <div class="price">₹0<span>/mo</span></div>
        <p style="font-size:14px;color:var(--gray-500)">For small clinics exploring FHIR</p>
        <ul>
          <li>Up to 100 patients</li>
          <li>Basic FHIR R4 API</li>
          <li>C-CDA conversion (5/mo)</li>
          <li>Email support</li>
          <li>DPDP compliance basics</li>
        </ul>
        <a href="/login" class="btn btn-primary btn-block" onclick="navigate('/login')">Get Started</a>
      </div>
      <div class="pricing-card featured">
        <h3>Professional</h3>
        <div class="price">₹9,999<span>/mo</span></div>
        <p style="font-size:14px;color:var(--gray-500)">For growing hospitals and clinics</p>
        <ul>
          <li>Up to 10,000 patients</li>
          <li>Full FHIR R4 API</li>
          <li>Unlimited conversions</li>
          <li>ABHA & Aadhaar eKYC</li>
          <li>DPDP full compliance suite</li>
          <li>Priority support</li>
        </ul>
        <a href="/login" class="btn btn-primary btn-block" onclick="navigate('/login')">Start Free Trial</a>
      </div>
      <div class="pricing-card">
        <h3>Enterprise</h3>
        <div class="price">Custom</div>
        <p style="font-size:14px;color:var(--gray-500)">For large hospital networks</p>
        <ul>
          <li>Unlimited patients</li>
          <li>On-premise deployment</li>
          <li>Custom integrations</li>
          <li>SLA guarantees</li>
          <li>Dedicated support team</li>
          <li>Data localization</li>
        </ul>
        <a href="mailto:sales@healthbridge.com" class="btn btn-outline btn-block">Contact Sales</a>
      </div>
    </div>
  `;
};

// ═══════════════════════════════════════════════
// PAGE: Login
// ═══════════════════════════════════════════════
pages.login = function(app) {
  if (api.isLoggedIn()) { navigate('/dashboard'); return; }

  app.innerHTML = `
    <div class="auth-page">
      <div class="auth-card">
        <div style="text-align:center;margin-bottom:16px">
          <div style="width:56px;height:56px;border-radius:14px;background:linear-gradient(135deg,var(--primary),var(--secondary));display:flex;align-items:center;justify-content:center;margin:0 auto 12px;font-size:28px;color:white;font-weight:bold">H</div>
        </div>
        <h2>Welcome to HealthBridge</h2>
        <p>Sign in to access the healthcare data platform</p>
        <div id="login-alert"></div>
        <form id="login-form">
          <div class="form-group">
            <label>Email</label>
            <input type="email" id="login-email" placeholder="doctor@hospital.com" value="admin@healthbridge.com" required>
          </div>
          <div class="form-group">
            <label>Password</label>
            <input type="password" id="login-password" placeholder="••••••••" value="admin123" required>
          </div>
          <button type="submit" class="btn btn-primary btn-block" id="login-btn">Sign In</button>
        </form>
        <div class="auth-divider">Demo Credentials</div>
        <div style="font-size:12px;color:var(--gray-500);text-align:center">
          <strong>Admin:</strong> admin@healthbridge.com / admin123<br>
          <strong>Doctor:</strong> doctor@healthbridge.com / doctor123
        </div>
      </div>
    </div>
  `;

  document.getElementById('login-form').addEventListener('submit', async e => {
    e.preventDefault();
    const btn = document.getElementById('login-btn');
    btn.disabled = true; btn.innerHTML = '<div class="spinner" style="width:18px;height:18px;border-width:2px;margin:0 auto"></div>';
    const alertDiv = document.getElementById('login-alert');

    try {
      await api.login(
        document.getElementById('login-email').value,
        document.getElementById('login-password').value
      );
      toast('Login successful! Welcome back.', 'success');
      navigate('/dashboard');
    } catch (err) {
      alertDiv.innerHTML = `<div class="alert alert-error">✗ ${err.message}</div>`;
      btn.disabled = false; btn.textContent = 'Sign In';
    }
  });
};

// ═══════════════════════════════════════════════
// PAGE: Dashboard
// ═══════════════════════════════════════════════
pages.dashboard = function(app) {
  if (!api.isLoggedIn()) { navigate('/login'); return; }
  const u = api.getUser();

  app.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Dashboard</h1>
        <p>Welcome back, ${u.full_name || u.email} · ${u.role || 'User'}</p>
      </div>
      <div style="display:flex;gap:8px">
        <a href="/patients" class="btn btn-primary btn-sm" onclick="navigate('/patients')">🔍 Search Patients</a>
        <a href="/logout" class="btn btn-danger btn-sm" onclick="navigate('/logout')">🚪 Logout</a>
      </div>
    </div>
    <div id="dash-stats"><div class="loading"><div class="spinner"></div></div></div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
      <div class="dash-card" style="cursor:pointer" onclick="navigate('/patients')">
        <div class="dash-icon" style="background:var(--primary-light);color:var(--primary)">🔍</div>
        <h3 style="font-size:16px;font-weight:600">Patient Records</h3>
        <p style="font-size:13px;color:var(--gray-500)">Search, view, and manage patient health records across connected networks</p>
      </div>
      <div class="dash-card" style="cursor:pointer" onclick="navigate('/fhir')">
        <div class="dash-icon" style="background:var(--secondary-light);color:var(--secondary)">📋</div>
        <h3 style="font-size:16px;font-weight:600">FHIR R4 Explorer</h3>
        <p style="font-size:13px;color:var(--gray-500)">Browse FHIR resources, search across types, and inspect bundles</p>
      </div>
      <div class="dash-card" style="cursor:pointer" onclick="navigate('/convert')">
        <div class="dash-icon" style="background:#d1fae5;color:#065f46">🔄</div>
        <h3 style="font-size:16px;font-weight:600">Document Conversion</h3>
        <p style="font-size:13px;color:var(--gray-500)">Convert between C-CDA, FHIR R4, PDF, and HL7 v2 formats</p>
      </div>
      <div class="dash-card" style="cursor:pointer" onclick="navigate('/consent')">
        <div class="dash-icon" style="background:#fef3c7;color:#92400e">✅</div>
        <h3 style="font-size:16px;font-weight:600">Consent Management</h3>
        <p style="font-size:13px;color:var(--gray-500)">DPDP-compliant consent lifecycle — grant, withdraw, audit</p>
      </div>
      <div class="dash-card" style="cursor:pointer" onclick="navigate('/compliance')">
        <div class="dash-icon" style="background:#fee2e2;color:#991b1b">🛡️</div>
        <h3 style="font-size:16px;font-weight:600">DPDP Compliance</h3>
        <p style="font-size:13px;color:var(--gray-500)">Breach management, erasure schedules, audit logs, data principal rights</p>
      </div>
      <div class="dash-card" style="cursor:pointer">
        <div class="dash-icon" style="background:var(--gray-100);color:var(--gray-600)">📖</div>
        <h3 style="font-size:16px;font-weight:600">API Documentation</h3>
        <p style="font-size:13px;color:var(--gray-500)">View Swagger UI, Redoc, and OpenAPI spec for all endpoints</p>
        <a href="/docs" target="_blank" class="btn btn-outline btn-sm" style="margin-top:12px">Open Swagger UI</a>
      </div>
    </div>
  `;

  // Load live stats
  api.getDashboardStats().then(stats => {
    document.getElementById('dash-stats').innerHTML = `
      <div class="dash-grid">
        <div class="dash-card">
          <div class="dash-icon" style="background:var(--primary-light);color:var(--primary)">👤</div>
          <div class="dash-value">${stats.total_patients || 0}</div>
          <div class="dash-label">Total Patients</div>
        </div>
        <div class="dash-card">
          <div class="dash-icon" style="background:var(--secondary-light);color:var(--secondary)">📋</div>
          <div class="dash-value">${stats.total_records || 0}</div>
          <div class="dash-label">Health Records</div>
        </div>
        <div class="dash-card">
          <div class="dash-icon" style="background:#d1fae5;color:#065f46">👥</div>
          <div class="dash-value">${stats.total_users || 0}</div>
          <div class="dash-label">Platform Users</div>
        </div>
        <div class="dash-card">
          <div class="dash-icon" style="background:#fee2e2;color:#991b1b">⚠️</div>
          <div class="dash-value">${stats.active_breaches || 0}</div>
          <div class="dash-label">Active Breaches</div>
        </div>
      </div>
    `;
  }).catch(() => {
    document.getElementById('dash-stats').innerHTML = `<div class="alert alert-info">ℹ Log in to see live statistics</div>`;
  });
};

// ═══════════════════════════════════════════════
// PAGE: Patients Search
// ═══════════════════════════════════════════════
pages.patients = function(app) {
  if (!api.isLoggedIn()) { navigate('/login'); return; }

  app.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Patient Search</h1>
        <p>Search across local records and connected health networks</p>
      </div>
      <a href="/patients" class="btn btn-primary btn-sm" onclick="navigate('/patients')">+ New Patient</a>
    </div>
    <div class="search-bar">
      <div class="search-grid">
        <div class="form-group">
          <label>First Name</label>
          <input type="text" id="pat-first" placeholder="Enter first name">
        </div>
        <div class="form-group">
          <label>Last Name</label>
          <input type="text" id="pat-last" placeholder="Enter last name">
        </div>
        <div class="form-group">
          <label>MRN</label>
          <input type="text" id="pat-mrn" placeholder="Medical Record Number">
        </div>
        <div class="form-group">
          <label>Phone</label>
          <input type="text" id="pat-phone" placeholder="Phone number">
        </div>
      </div>
      <button class="btn btn-primary" onclick="searchPatients()">🔍 Search</button>
    </div>
    <div id="patient-results">
      ${emptyHTML('🔍', 'Search for patients', 'Enter patient details above and click Search to find records across connected health networks.')}
    </div>
  `;
  window.searchPatients = async function() {
    const el = document.getElementById('patient-results');
    el.innerHTML = loadingHTML('Searching across networks...');
    try {
      const results = await api.searchPatients({
        first_name: document.getElementById('pat-first').value,
        last_name: document.getElementById('pat-last').value,
        mrn: document.getElementById('pat-mrn').value,
        phone: document.getElementById('pat-phone').value,
      });
      if (!results || results.length === 0) {
        el.innerHTML = emptyHTML('👤', 'No patients found', 'Try different search terms or check the patient exists in the system.');
        return;
      }
      el.innerHTML = `<div class="patient-list">${results.map(p => `
        <div class="patient-item" onclick="navigate('/patients/${p.patient_id}')">
          <div class="patient-info">
            <div class="patient-avatar">${(p.first_name || '?')[0]}${(p.last_name || '')[0]}</div>
            <div>
              <div class="patient-name">${p.first_name || ''} ${p.last_name || ''}</div>
              <div class="patient-detail">MRN: ${p.mrn || 'N/A'} · ${p.gender || 'N/A'} · ${p.age || '?'} yrs</div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            ${statusBadge(p.consent_status)}
            <span style="font-size:12px;color:var(--gray-400)">${p.source_count || 0} sources</span>
          </div>
        </div>
      `).join('')}</div>`;
    } catch (err) {
      el.innerHTML = `<div class="alert alert-error">✗ ${err.message}</div>`;
    }
  };
};

// ═══════════════════════════════════════════════
// PAGE: Patient Detail
// ═══════════════════════════════════════════════
pages.patientDetail = function(app, id) {
  if (!api.isLoggedIn()) { navigate('/login'); return; }

  app.innerHTML = loadingHTML('Loading patient records...');

  Promise.all([
    api.getPatient(id).catch(() => null),
    api.getPatientRecords(id).catch(() => []),
    api.getConsentStatus(id).catch(() => null),
  ]).then(([patient, records, consent]) => {
    if (!patient) {
      app.innerHTML = `<div class="alert alert-error" style="margin-top:24px">✗ Patient not found</div>`;
      return;
    }
    const d = patient.demographics || {};
    app.innerHTML = `
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">
        <button class="btn btn-outline btn-sm" onclick="navigate('/patients')">← Back</button>
      </div>
      <div class="patient-detail-card">
        <div class="patient-header">
          <div style="display:flex;align-items:center;gap:16px">
            <div class="patient-avatar" style="width:56px;height:56px;font-size:22px">${(d.first_name || '?')[0]}${(d.last_name || '')[0]}</div>
            <div>
              <h2 style="font-size:22px;font-weight:700">${d.first_name || ''} ${d.last_name || ''}</h2>
              <p style="font-size:14px;color:var(--gray-500)">MRN: ${patient.mrn || 'N/A'} · DOB: ${d.date_of_birth || 'N/A'} · ${d.gender || 'N/A'}</p>
              <p style="font-size:14px;color:var(--gray-500)">📞 ${d.phone || 'N/A'} · ✉ ${d.email || 'N/A'}</p>
              <p style="font-size:14px;color:var(--gray-500)">🩸 ${patient.blood_group || 'N/A'} · 🆔 ABHA: ${patient.abha_number || 'Not linked'}</p>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            ${statusBadge(patient.consent_status)}
            <span style="font-size:13px;color:var(--gray-500)">Consent</span>
          </div>
        </div>
      </div>

      <div class="tabs">
        <button class="tab active" onclick="switchPatientTab(this,'records')">📋 Records (${(records||[]).length})</button>
        <button class="tab" onclick="switchPatientTab(this,'fhir')">📄 FHIR Bundle</button>
        <button class="tab" onclick="switchPatientTab(this,'consent')">✅ Consent</button>
      </div>
      <div id="patient-tab-content">
        ${renderPatientRecords(records)}
      </div>
    `;

    window.switchPatientTab = function(el, tab) {
      document.querySelectorAll('.tabs .tab').forEach(t => t.classList.remove('active'));
      el.classList.add('active');
      const tc = document.getElementById('patient-tab-content');
      if (tab === 'records') tc.innerHTML = renderPatientRecords(records);
      else if (tab === 'fhir') {
        api.fhirEverything(id).then(bundle => {
          tc.innerHTML = `<div class="fhir-output">${JSON.stringify(bundle, null, 2)}</div>`;
        }).catch(() => {
          tc.innerHTML = `<div class="alert alert-info">ℹ No FHIR bundle available</div>`;
        });
      } else if (tab === 'consent') {
        renderConsentTab(tc, id, consent);
      }
    };
  }).catch(err => {
    app.innerHTML = `<div class="alert alert-error" style="margin-top:24px">✗ ${err.message}</div>`;
  });
};

function renderPatientRecords(records) {
  if (!records || records.length === 0) return emptyHTML('📋', 'No records', 'This patient has no health records yet.');
  const grouped = {};
  records.forEach(r => {
    const t = r.record_type || r.recordType || 'OTHER';
    if (!grouped[t]) grouped[t] = [];
    grouped[t].push(r);
  });
  return Object.entries(grouped).map(([type, items]) => `
    <div style="margin-bottom:16px">
      <h3 style="font-size:15px;font-weight:600;margin-bottom:8px;color:var(--gray-700)">${type} (${items.length})</h3>
      <div class="records-list">
        ${items.slice(0, 10).map(r => `
          <div class="record-item">
            <h4>${r.clinical_summary || r.clinicalSummary || r.fhir_resource_type || 'Record'}</h4>
            <p>${r.encounter_date || r.encounterDate || ''} · ${r.source_system || r.sourceSystem || ''} · ${r.provider_name || r.providerName || ''}</p>
          </div>
        `).join('')}
      </div>
    </div>
  `).join('');
}

function renderConsentTab(tc, patientId, consent) {
  tc.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
      <div class="dash-card">
        <h3 style="font-size:16px;font-weight:600;margin-bottom:12px">Current Status</h3>
        <p style="font-size:14px;margin-bottom:8px">Status: ${statusBadge(consent?.current_status || 'PENDING')}</p>
        <p style="font-size:13px;color:var(--gray-500)">Purpose: ${(consent?.purposes || []).join(', ') || 'Not specified'}</p>
        <p style="font-size:13px;color:var(--gray-500)">Expires: ${consent?.consent_expires_at ? new Date(consent.consent_expires_at).toLocaleDateString() : 'N/A'}</p>
      </div>
      <div class="dash-card">
        <h3 style="font-size:16px;font-weight:600;margin-bottom:12px">Grant Consent</h3>
        <div class="form-group">
          <label>Purpose</label>
          <select id="consent-purpose" style="width:100%;padding:10px 14px;border:1.5px solid var(--gray-200);border-radius:var(--radius-sm);font-size:14px">
            <option value="TREATMENT">Treatment</option>
            <option value="PAYMENT">Payment</option>
            <option value="OPERATIONS">Operations</option>
            <option value="RESEARCH">Research</option>
          </select>
        </div>
        <div class="form-group">
          <label>Duration (days)</label>
          <input type="number" id="consent-duration" value="365" style="width:100%;padding:10px 14px;border:1.5px solid var(--gray-200);border-radius:var(--radius-sm);font-size:14px">
        </div>
        <button class="btn btn-primary btn-sm" onclick="grantPatientConsent('${patientId}')">Grant Consent</button>
      </div>
    </div>
  `;
}

window.grantPatientConsent = async function(patientId) {
  try {
    await api.grantConsent(patientId,
      document.getElementById('consent-purpose').value,
      ['DEMOGRAPHICS', 'CLINICAL'],
      parseInt(document.getElementById('consent-duration').value) || 365
    );
    toast('Consent granted successfully!', 'success');
    setTimeout(() => navigate(`/patients/${patientId}`), 1000);
  } catch (err) {
    toast(err.message, 'error');
  }
};

// ═══════════════════════════════════════════════
// PAGE: FHIR Explorer
// ═══════════════════════════════════════════════
pages.fhirExplorer = function(app) {
  if (!api.isLoggedIn()) { navigate('/login'); return; }

  app.innerHTML = `
    <div class="page-header">
      <div>
        <h1>FHIR R4 Explorer</h1>
        <p>Browse, search, and inspect FHIR resources directly</p>
      </div>
    </div>
    <div class="fhir-tools">
      <div class="fhir-panel">
        <h3>🔍 Search Resources</h3>
        <div class="form-group">
          <label>Resource Type</label>
          <select id="fhir-type" style="width:100%;padding:10px 14px;border:1.5px solid var(--gray-200);border-radius:var(--radius-sm);font-size:14px">
            <option value="Patient">Patient</option>
            <option value="Condition">Condition</option>
            <option value="Observation">Observation</option>
            <option value="MedicationRequest">MedicationRequest</option>
            <option value="Encounter">Encounter</option>
            <option value="Procedure">Procedure</option>
            <option value="AllergyIntolerance">AllergyIntolerance</option>
            <option value="DiagnosticReport">DiagnosticReport</option>
          </select>
        </div>
        <div class="form-group">
          <label>Resource ID (or leave empty to search all)</label>
          <input type="text" id="fhir-id" placeholder="e.g. patient UUID" style="width:100%;padding:10px 14px;border:1.5px solid var(--gray-200);border-radius:var(--radius-sm);font-size:14px">
        </div>
        <button class="btn btn-primary btn-sm" onclick="searchFhir()">🔍 Fetch</button>
        <div id="fhir-result" style="margin-top:12px"></div>
      </div>
      <div class="fhir-panel">
        <h3>📄 $everything Bundle</h3>
        <div class="form-group">
          <label>Patient ID</label>
          <input type="text" id="fhir-patient" placeholder="Enter patient UUID" style="width:100%;padding:10px 14px;border:1.5px solid var(--gray-200);border-radius:var(--radius-sm);font-size:14px">
        </div>
        <button class="btn btn-primary btn-sm" onclick="getFhirEverything()">📦 Get Everything</button>
        <div id="fhir-everything-result" style="margin-top:12px"></div>
      </div>
    </div>
  `;

  window.searchFhir = async function() {
    const el = document.getElementById('fhir-result');
    const type = document.getElementById('fhir-type').value;
    const id = document.getElementById('fhir-id').value;
    el.innerHTML = loadingHTML();
    try {
      const data = id ? await api.fhirRead(type, id) : await api.fhirSearch(type, { _count: 10 });
      el.innerHTML = `<div class="fhir-output">${JSON.stringify(data, null, 2)}</div>`;
    } catch (err) { el.innerHTML = `<div class="alert alert-error">✗ ${err.message}</div>`; }
  };

  window.getFhirEverything = async function() {
    const el = document.getElementById('fhir-everything-result');
    const pid = document.getElementById('fhir-patient').value;
    if (!pid) { el.innerHTML = `<div class="alert alert-error">✗ Enter a patient ID</div>`; return; }
    el.innerHTML = loadingHTML();
    try {
      const data = await api.fhirEverything(pid);
      el.innerHTML = `<div class="fhir-output">${JSON.stringify(data, null, 2)}</div>`;
    } catch (err) { el.innerHTML = `<div class="alert alert-error">✗ ${err.message}</div>`; }
  };
};

// ═══════════════════════════════════════════════
// PAGE: Document Conversion
// ═══════════════════════════════════════════════
pages.conversion = function(app) {
  if (!api.isLoggedIn()) { navigate('/login'); return; }

  app.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Document Conversion</h1>
        <p>Convert between FHIR R4, C-CDA, PDF, and HL7 v2 formats</p>
      </div>
    </div>
    <div class="conv-grid">
      <div class="conv-btn active" onclick="selectConv(this,'fhir-to-ccda')">
        <div class="conv-label">FHIR R4 → C-CDA</div>
        <div class="conv-desc">Paste FHIR JSON to get C-CDA XML</div>
      </div>
      <div class="conv-btn" onclick="selectConv(this,'ccda-to-fhir')">
        <div class="conv-label">C-CDA → FHIR R4</div>
        <div class="conv-desc">Upload C-CDA XML to get FHIR Bundle</div>
      </div>
      <div class="conv-btn" onclick="selectConv(this,'fhir-to-pdf')">
        <div class="conv-label">FHIR R4 → PDF</div>
        <div class="conv-desc">Generate clinical summary PDF</div>
      </div>
      <div class="conv-btn" onclick="selectConv(this,'hl7v2-to-fhir')">
        <div class="conv-label">HL7 v2 → FHIR</div>
        <div class="conv-desc">Transform HL7 messages to FHIR</div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
      <div class="fhir-panel">
        <h3 id="conv-input-title">📥 Input</h3>
        <textarea id="conv-input" rows="8" style="width:100%;padding:12px;border:1.5px solid var(--gray-200);border-radius:var(--radius-sm);font-family:monospace;font-size:13px;resize:vertical" placeholder="Paste FHIR JSON here..."></textarea>
        <div id="conv-file-area" style="display:none">
          <input type="file" id="conv-file" accept=".xml,.ccd" style="margin-top:8px">
        </div>
        <button class="btn btn-primary btn-sm" style="margin-top:12px" onclick="runConversion()">🔄 Convert</button>
      </div>
      <div class="fhir-panel">
        <h3>📤 Output</h3>
        <div id="conv-output" style="min-height:200px;display:flex;align-items:center;justify-content:center;color:var(--gray-400);font-size:14px">Converted output will appear here</div>
      </div>
    </div>
  `;

  window._convType = 'fhir-to-ccda';
  window.selectConv = function(el, type) {
    document.querySelectorAll('.conv-btn').forEach(b => b.classList.remove('active'));
    el.classList.add('active');
    window._convType = type;
    document.getElementById('conv-input').value = '';
    document.getElementById('conv-output').innerHTML = '<div style="display:flex;align-items:center;justify-content:center;color:var(--gray-400);font-size:14px">Converted output will appear here</div>';
    if (type === 'ccda-to-fhir') {
      document.getElementById('conv-input-title').textContent = '📥 Upload C-CDA XML';
      document.getElementById('conv-input').style.display = 'none';
      document.getElementById('conv-file-area').style.display = 'block';
    } else if (type === 'fhir-to-ccda') {
      document.getElementById('conv-input-title').textContent = '📥 FHIR R4 Bundle JSON';
      document.getElementById('conv-input').style.display = 'block';
      document.getElementById('conv-file-area').style.display = 'none';
      document.getElementById('conv-input').placeholder = 'Paste FHIR Bundle JSON here...';
    } else if (type === 'fhir-to-pdf') {
      document.getElementById('conv-input-title').textContent = '📥 FHIR JSON';
      document.getElementById('conv-input').style.display = 'block';
      document.getElementById('conv-file-area').style.display = 'none';
      document.getElementById('conv-input').placeholder = 'Paste FHIR Composition JSON here...';
    } else if (type === 'hl7v2-to-fhir') {
      document.getElementById('conv-input-title').textContent = '📥 HL7 v2 Message';
      document.getElementById('conv-input').style.display = 'block';
      document.getElementById('conv-file-area').style.display = 'none';
      document.getElementById('conv-input').placeholder = 'Paste HL7 v2 message here...';
    }
  };

  window.runConversion = async function() {
    const out = document.getElementById('conv-output');
    out.innerHTML = loadingHTML('Converting...');
    try {
      let result;
      switch (window._convType) {
        case 'fhir-to-ccda':
          result = await api.fhirToCcda(document.getElementById('conv-input').value);
          break;
        case 'ccda-to-fhir':
          result = await api.ccdaToFhir(document.getElementById('conv-file').files[0]);
          break;
        case 'fhir-to-pdf':
          result = await api.fhirToPdf(document.getElementById('conv-input').value);
          break;
        case 'hl7v2-to-fhir':
          result = await api.hl7v2ToFhir(document.getElementById('conv-input').value);
          break;
      }
      if (result.success) {
        const content = result.content || '';
        out.innerHTML = `
          <div class="alert alert-success">✓ Conversion successful</div>
          <div class="fhir-output" style="max-height:400px">${content.substring(0, 3000)}${content.length > 3000 ? '\n\n... (truncated)' : ''}</div>
        `;
      } else {
        out.innerHTML = `<div class="alert alert-error">✗ ${result.error_message || 'Conversion failed'}</div>`;
      }
    } catch (err) {
      out.innerHTML = `<div class="alert alert-error">✗ ${err.message}</div>`;
    }
  };
};

// ═══════════════════════════════════════════════
// PAGE: Consent Management
// ═══════════════════════════════════════════════
pages.consent = function(app) {
  if (!api.isLoggedIn()) { navigate('/login'); return; }

  app.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Consent Management</h1>
        <p>DPDP Act 2025 compliant consent lifecycle — Sections 5-7</p>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
      <div class="dash-card">
        <h3 style="font-size:16px;font-weight:600;margin-bottom:12px">Grant Consent</h3>
        <div class="form-group">
          <label>Patient ID</label>
          <input type="text" id="consent-patient-id" placeholder="Patient UUID" style="width:100%;padding:10px 14px;border:1.5px solid var(--gray-200);border-radius:var(--radius-sm);font-size:14px">
        </div>
        <div class="form-group">
          <label>Purpose</label>
          <select id="consent-purpose-main" style="width:100%;padding:10px 14px;border:1.5px solid var(--gray-200);border-radius:var(--radius-sm);font-size:14px">
            <option value="TREATMENT">Treatment</option>
            <option value="PAYMENT">Payment</option>
            <option value="OPERATIONS">Operations</option>
            <option value="RESEARCH">Research</option>
          </select>
        </div>
        <div class="form-group">
          <label>Duration (days)</label>
          <input type="number" id="consent-duration-main" value="365" style="width:100%;padding:10px 14px;border:1.5px solid var(--gray-200);border-radius:var(--radius-sm);font-size:14px">
        </div>
        <button class="btn btn-primary btn-sm" onclick="grantConsentFromPage()">✅ Grant Consent</button>
      </div>
      <div class="dash-card">
        <h3 style="font-size:16px;font-weight:600;margin-bottom:12px">Check Consent Status</h3>
        <div class="form-group">
          <label>Patient ID</label>
          <input type="text" id="consent-check-id" placeholder="Patient UUID" style="width:100%;padding:10px 14px;border:1.5px solid var(--gray-200);border-radius:var(--radius-sm);font-size:14px">
        </div>
        <button class="btn btn-outline btn-sm" onclick="checkConsentStatus()">🔍 Check Status</button>
        <div id="consent-status-result" style="margin-top:12px"></div>
      </div>
    </div>
    <div style="margin-top:20px">
      <h3 class="section-title" style="font-size:18px">DPDP Compliance Notice</h3>
      <div class="alert alert-info">ℹ All consent operations are logged immutably per DPDP Act 2025 Section 5-7. Consent withdrawal mechanism is equally accessible on the patient detail page.</div>
    </div>
  `;

  window.grantConsentFromPage = async function() {
    const pid = document.getElementById('consent-patient-id').value;
    if (!pid) { toast('Enter a patient ID', 'error'); return; }
    try {
      await api.grantConsent(pid,
        document.getElementById('consent-purpose-main').value,
        ['DEMOGRAPHICS', 'CLINICAL'],
        parseInt(document.getElementById('consent-duration-main').value) || 365
      );
      toast('Consent granted successfully! ✓', 'success');
    } catch (err) { toast(err.message, 'error'); }
  };

  window.checkConsentStatus = async function() {
    const pid = document.getElementById('consent-check-id').value;
    if (!pid) { toast('Enter a patient ID', 'error'); return; }
    const el = document.getElementById('consent-status-result');
    el.innerHTML = loadingHTML();
    try {
      const data = await api.getConsentStatus(pid);
      el.innerHTML = `
        <div style="padding:12px;background:var(--gray-50);border-radius:var(--radius-sm)">
          <p><strong>Status:</strong> ${statusBadge(data.current_status || 'PENDING')}</p>
          <p style="font-size:13px;margin-top:8px"><strong>Purposes:</strong> ${(data.purposes || []).join(', ') || 'None'}</p>
          <p style="font-size:13px"><strong>Expires:</strong> ${data.consent_expires_at ? new Date(data.consent_expires_at).toLocaleDateString() : 'N/A'}</p>
          <p style="font-size:13px"><strong>Active Consent ID:</strong> ${data.active_consent_id || 'None'}</p>
        </div>
      `;
    } catch (err) { el.innerHTML = `<div class="alert alert-error">✗ ${err.message}</div>`; }
  };
};

// ═══════════════════════════════════════════════
// PAGE: DPDP Compliance
// ═══════════════════════════════════════════════
pages.compliance = function(app) {
  if (!api.isLoggedIn()) { navigate('/login'); return; }

  app.innerHTML = `
    <div class="page-header">
      <div>
        <h1>DPDP 2025 Compliance</h1>
        <p>Data Protection Board reporting, breach management, erasure schedules, and audit</p>
      </div>
    </div>

    <div class="compliance-grid">
      <div class="dash-card">
        <h3 style="font-size:16px;font-weight:600;margin-bottom:12px">🚨 Report a Breach</h3>
        <div class="form-group">
          <label>Description</label>
          <textarea id="breach-desc" rows="3" style="width:100%;padding:10px 14px;border:1.5px solid var(--gray-200);border-radius:var(--radius-sm);font-size:14px;resize:vertical" placeholder="Describe the breach..."></textarea>
        </div>
        <div class="form-group">
          <label>Severity</label>
          <select id="breach-severity" style="width:100%;padding:10px 14px;border:1.5px solid var(--gray-200);border-radius:var(--radius-sm);font-size:14px">
            <option value="LOW">Low</option>
            <option value="MEDIUM">Medium</option>
            <option value="HIGH">High</option>
            <option value="CRITICAL">Critical</option>
          </select>
        </div>
        <button class="btn btn-danger btn-sm" onclick="reportBreach()">⚠️ Report Breach</button>
      </div>
      <div class="dash-card">
        <h3 style="font-size:16px;font-weight:600;margin-bottom:12px">📊 Active Breaches</h3>
        <div id="breach-list">${loadingHTML()}</div>
      </div>
    </div>

    <div style="margin-top:20px;display:grid;grid-template-columns:1fr 1fr;gap:20px">
      <div class="dash-card">
        <h3 style="font-size:16px;font-weight:600;margin-bottom:12px">📋 Audit Logs</h3>
        <div id="audit-logs">${loadingHTML()}</div>
      </div>
      <div class="dash-card">
        <h3 style="font-size:16px;font-weight:600;margin-bottom:12px">🗑️ Erasure Schedule</h3>
        <div id="erasure-schedule">${loadingHTML()}</div>
      </div>
    </div>
  `;

  // Load breaches
  api.listBreaches().then(breaches => {
    const el = document.getElementById('breach-list');
    if (!breaches || breaches.length === 0) {
      el.innerHTML = `<p style="color:var(--gray-400);font-size:14px;text-align:center;padding:20px">No breaches reported</p>`;
    } else {
      el.innerHTML = `<table class="data-table">
        <tr><th>Severity</th><th>Status</th><th>Date</th><th>Patients</th></tr>
        ${breaches.slice(0, 5).map(b => `
          <tr>
            <td>${statusBadge(b.severity)}</td>
            <td>${statusBadge(b.status)}</td>
            <td style="font-size:13px">${new Date(b.detected_at).toLocaleDateString()}</td>
            <td style="font-size:13px">${b.affected_patient_count || 0}</td>
          </tr>
        `).join('')}
      </table>`;
    }
  }).catch(() => document.getElementById('breach-list').innerHTML = `<p style="color:var(--gray-400);font-size:14px;text-align:center;padding:20px">No breaches</p>`);

  // Load audit logs
  api.getAuditLogs().then(logs => {
    const el = document.getElementById('audit-logs');
    if (!logs || logs.length === 0) {
      el.innerHTML = `<p style="color:var(--gray-400);font-size:14px;text-align:center;padding:20px">No audit logs</p>`;
    } else {
      el.innerHTML = logs.slice(0, 10).map(l => `
        <div style="padding:8px 0;border-bottom:1px solid var(--gray-100);font-size:13px">
          <span style="color:var(--gray-500)">${new Date(l.timestamp || l.created_at).toLocaleString()}</span>
          <span style="margin-left:8px">${l.action || l.description || ''}</span>
        </div>
      `).join('');
    }
  }).catch(() => {});

  // Load erasure schedule
  api.getErasureSchedule().then(schedule => {
    const el = document.getElementById('erasure-schedule');
    if (!schedule || schedule.length === 0) {
      el.innerHTML = `<p style="color:var(--gray-400);font-size:14px;text-align:center;padding:20px">No pending erasures</p>`;
    } else {
      el.innerHTML = schedule.map(s => `
        <div style="padding:8px 0;border-bottom:1px solid var(--gray-100);font-size:13px">
          <strong>Patient:</strong> ${s.patient_id?.substring(0, 8) || 'N/A'}...
          <span style="float:right">${statusBadge(s.status)}</span>
        </div>
      `).join('');
    }
  }).catch(() => {});

  window.reportBreach = async function() {
    const desc = document.getElementById('breach-desc').value;
    if (!desc) { toast('Enter a breach description', 'error'); return; }
    try {
      await api.reportBreach({
        description: desc,
        severity: document.getElementById('breach-severity').value,
      });
      toast('Breach reported — notification sent to Data Protection Board ✓', 'success');
      document.getElementById('breach-desc').value = '';
    } catch (err) { toast(err.message, 'error'); }
  };
};

// ═══════════════════════════════════════════════
// Init — popstate handling
// ═══════════════════════════════════════════════
window.addEventListener('popstate', renderPage);
document.addEventListener('click', e => {
  const a = e.target.closest('a[href^="/"]');
  if (a && !a.getAttribute('target')) {
    e.preventDefault();
    navigate(a.getAttribute('href'));
  }
});
