import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  Activity,
  ArrowLeftRight,
  ShieldCheck,
  FileSearch,
  CheckSquare,
  Settings,
  Menu,
  X,
  Shield,
  LogOut,
  Bell,
  Upload,
  Download,
} from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/patients', icon: Users, label: 'Patients' },
  { to: '/fhir', icon: Activity, label: 'FHIR Explorer' },
  { to: '/convert', icon: ArrowLeftRight, label: 'Conversion' },
  { to: '/consent', icon: ShieldCheck, label: 'Consent Manager' },
  { to: '/audit', icon: FileSearch, label: 'Audit Log' },
  { to: '/compliance', icon: CheckSquare, label: 'Compliance' },
  { to: '/upload', icon: Upload, label: 'Upload' },
  { to: '/exports', icon: Download, label: 'Exports' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

const Layout: React.FC = () => {
  const { currentUser, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();

  const toggleSidebar = () => setSidebarOpen((prev) => !prev);
  const closeSidebar = () => setSidebarOpen(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const userInitial = currentUser?.name?.charAt(0)?.toUpperCase() || 'U';

  return (
    <div className="app-layout">
      {/* Sidebar overlay for mobile */}
      {sidebarOpen && <div className="sidebar-overlay mobile-visible" onClick={closeSidebar} />}

      {/* Sidebar */}
      <aside className={`app-sidebar ${sidebarOpen ? 'mobile-open' : ''}`}>
        <div className="sidebar-header">
          <div className="sidebar-logo">HB</div>
          <div>
            <div className="sidebar-brand">HealthBridge</div>
            <div className="sidebar-brand-sub">DPDP 2025 Compliant</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `sidebar-nav-item ${isActive ? 'active' : ''}`
              }
              onClick={closeSidebar}
            >
              <item.icon />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-footer-avatar">{userInitial}</div>
          <div>
            <div className="sidebar-footer-name">{currentUser?.name || 'User'}</div>
            <div className="sidebar-footer-role">{currentUser?.role || 'Practitioner'}</div>
          </div>
        </div>
      </aside>

      {/* Main area */}
      <div className="app-main" style={{ flex: 1, minWidth: 0 }}>
        {/* Top Header */}
        <header className={`app-header ${sidebarOpen ? 'expanded' : ''}`}>
          <div className="header-left">
            <button className="hamburger-btn" onClick={toggleSidebar} aria-label="Toggle sidebar">
              {sidebarOpen ? <X size={22} /> : <Menu size={22} />}
            </button>
            <span className="header-title">HealthBridge Platform</span>
          </div>
          <div className="header-right">
            <div className="compliance-badge">
              <Shield size={14} />
              <span>DPDP 2025 Compliant</span>
            </div>
            <button className="btn btn-ghost btn-sm" style={{ position: 'relative' }}>
              <Bell size={18} />
            </button>
            <div className="header-user">
              <div className="header-user-avatar">{userInitial}</div>
              <span className="header-user-name">{currentUser?.name || 'User'}</span>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={handleLogout} title="Logout">
              <LogOut size={18} />
            </button>
          </div>
        </header>

        {/* Content Area */}
        <main className={`app-content ${sidebarOpen ? 'expanded' : ''}`}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default Layout;
