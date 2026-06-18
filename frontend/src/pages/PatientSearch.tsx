import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Search,
  Users,
  AlertCircle,
  Info,
  ExternalLink,
  Filter,
  RefreshCw,
} from 'lucide-react';
import { patientApi } from '../services/api';

const PatientSearch: React.FC = () => {
  const navigate = useNavigate();
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [mrn, setMrn] = useState('');
  const [phone, setPhone] = useState('');
  const [searchExternal, setSearchExternal] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const {
    data: patients,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['patients', { firstName, lastName, mrn, phone, searchExternal }],
    queryFn: () => patientApi.search({ firstName, lastName, mrn, phone, searchExternal }),
    enabled: false, // Don't auto-run, only on search
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setHasSearched(true);
    refetch();
  };

  const getConsentBadge = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'active':
      case 'granted':
        return <span className="badge badge-success">{status}</span>;
      case 'pending':
        return <span className="badge badge-warning">{status}</span>;
      case 'withdrawn':
      case 'expired':
      case 'revoked':
        return <span className="badge badge-danger">{status}</span>;
      default:
        return <span className="badge badge-neutral">{status || 'Unknown'}</span>;
    }
  };

  const handleRowClick = (patientId: string) => {
    navigate(`/patients/${patientId}/chart`);
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1>Patient Search</h1>
          <p className="text-muted text-sm">Search across connected healthcare systems</p>
        </div>
      </div>

      {/* DPDP Compliance Notice */}
      <div className="dpdp-notice">
        <Info size={16} />
        <span>All searches are logged per DPDP 2025 requirements for audit trail compliance.</span>
      </div>

      {/* Search Form */}
      <div className="filter-bar">
        <form onSubmit={handleSearch} style={{ width: '100%' }}>
          <div className="form-row" style={{ marginBottom: 12 }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">First Name</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g., John"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
              />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Last Name</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g., Doe"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
              />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">MRN</label>
              <input
                type="text"
                className="form-input"
                placeholder="Medical Record Number"
                value={mrn}
                onChange={(e) => setMrn(e.target.value)}
              />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Phone</label>
              <input
                type="text"
                className="form-input"
                placeholder="Phone number"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12 }}>
            <label className="form-checkbox">
              <input
                type="checkbox"
                checked={searchExternal}
                onChange={(e) => setSearchExternal(e.target.checked)}
              />
              <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Search external networks (ABDM, Care Net)
              </span>
            </label>
            <button type="submit" className="btn btn-primary" disabled={isLoading}>
              {isLoading ? (
                <><div className="spinner spinner-sm" /> Searching...</>
              ) : (
                <><Search size={16} /> Search</>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Results */}
      {isLoading && (
        <div className="loading-container">
          <div className="spinner" />
          <div className="loading-text">Searching patients...</div>
        </div>
      )}

      {isError && (
        <div className="error-state">
          <AlertCircle size={44} />
          <div className="error-state-title">Search Failed</div>
          <div className="error-state-text">
            {(error as any)?.message || 'An error occurred while searching. Please try again.'}
          </div>
          <button className="btn btn-primary" onClick={() => refetch()}>
            <RefreshCw size={16} />
            Retry
          </button>
        </div>
      )}

      {hasSearched && !isLoading && !isError && patients && patients.length === 0 && (
        <div className="empty-state">
          <Users size={48} />
          <div className="empty-state-title">No patients found</div>
          <div className="empty-state-text">
            No matching records found. Try adjusting your search criteria or enable external search.
          </div>
        </div>
      )}

      {hasSearched && !isLoading && !isError && patients && patients.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Users size={16} style={{ color: 'var(--primary)' }} />
            <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>
              {patients.length} patient{patients.length !== 1 ? 's' : ''} found
            </span>
          </div>
          <div className="table-container" style={{ border: 'none' }}>
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>MRN</th>
                  <th>DOB</th>
                  <th>Gender</th>
                  <th>Consent Status</th>
                  <th>Sources</th>
                </tr>
              </thead>
              <tbody>
                {patients.map((patient: any) => (
                  <tr
                    key={patient.id || patient.patientId}
                    className="clickable"
                    onClick={() => handleRowClick(patient.id || patient.patientId)}
                  >
                    <td style={{ fontWeight: 500 }}>
                      {[patient.firstName, patient.lastName].filter(Boolean).join(' ') || 'Unknown'}
                    </td>
                    <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                      {patient.mrn || '-'}
                    </td>
                    <td>{patient.dob || patient.birthDate || '-'}</td>
                    <td style={{ textTransform: 'capitalize' }}>{patient.gender || '-'}</td>
                    <td>{getConsentBadge(patient.consentStatus || patient.consent?.status)}</td>
                    <td>
                      <span className="badge badge-info">
                        {patient.sourceCount || patient.sources?.length || 0}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!hasSearched && !isLoading && (
        <div className="empty-state">
          <Filter size={48} />
          <div className="empty-state-title">Search for patients</div>
          <div className="empty-state-text">
            Enter patient details above and click Search to find records across all connected systems.
          </div>
        </div>
      )}
    </div>
  );
};

export default PatientSearch;
