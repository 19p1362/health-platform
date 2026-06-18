import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Search,
  Copy,
  Check,
  AlertCircle,
  RefreshCw,
  Code,
  List,
} from 'lucide-react';
import { fhirApi } from '../services/api';

const RESOURCE_TYPES = [
  'Patient',
  'Condition',
  'Observation',
  'MedicationRequest',
  'MedicationAdministration',
  'Encounter',
  'Procedure',
  'DiagnosticReport',
  'DocumentReference',
  'Organization',
  'Practitioner',
  'AllergyIntolerance',
  'Immunization',
  'CarePlan',
  'CareTeam',
  'Device',
  'Location',
  'Claim',
];

const FhirExplorer: React.FC = () => {
  const [resourceType, setResourceType] = useState('Patient');
  const [resourceId, setResourceId] = useState('');
  const [searchParams, setSearchParams] = useState('');
  const [viewMode, setViewMode] = useState<'json' | 'tree'>('json');
  const [copied, setCopied] = useState(false);
  const [mode, setMode] = useState<'read' | 'search'>('read');

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['fhir', mode, resourceType, resourceId, searchParams],
    queryFn: () => {
      if (mode === 'read') {
        if (!resourceId.trim()) throw new Error('Resource ID is required');
        return fhirApi.read(resourceType, resourceId.trim());
      } else {
        const params: Record<string, string> = {};
        searchParams.split('&').forEach((pair) => {
          const [key, val] = pair.split('=');
          if (key && val) params[key.trim()] = val.trim();
        });
        return fhirApi.search(resourceType, params);
      }
    },
    enabled: false,
  });

  const handleExecute = (e: React.FormEvent) => {
    e.preventDefault();
    refetch();
  };

  const handleCopy = async () => {
    if (data) {
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const formattedJson = data ? JSON.stringify(data, null, 2) : '';

  const renderTree = (obj: any, depth = 0): React.ReactNode => {
    if (obj === null || obj === undefined) return <span style={{ color: 'var(--muted)' }}>null</span>;
    if (typeof obj === 'string') return <span style={{ color: '#22c55e' }}>"{obj}"</span>;
    if (typeof obj === 'number') return <span style={{ color: '#f59e0b' }}>{obj}</span>;
    if (typeof obj === 'boolean') return <span style={{ color: '#06b6d4' }}>{String(obj)}</span>;

    if (Array.isArray(obj)) {
      if (obj.length === 0) return <span style={{ color: 'var(--muted)' }}>[]</span>;
      return (
        <div style={{ paddingLeft: depth > 0 ? 20 : 0 }}>
          {obj.map((item, idx) => (
            <div key={idx} style={{ marginBottom: 4 }}>
              <span style={{ color: 'var(--muted)', marginRight: 8 }}>{idx}:</span>
              {renderTree(item, depth + 1)}
            </div>
          ))}
        </div>
      );
    }

    if (typeof obj === 'object') {
      const entries = Object.entries(obj);
      if (entries.length === 0) return <span style={{ color: 'var(--muted)' }}>{'{}'}</span>;
      return (
        <div style={{ paddingLeft: depth > 0 ? 20 : 0 }}>
          {entries.map(([key, val]) => (
            <div key={key} style={{ marginBottom: 4 }}>
              <span style={{ color: 'var(--primary)', marginRight: 8 }}>{key}:</span>
              {renderTree(val, depth + 1)}
            </div>
          ))}
        </div>
      );
    }

    return String(obj);
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1>FHIR R4 Explorer</h1>
        <p className="text-muted text-sm">Browse and search FHIR resources on the HealthBridge platform</p>
      </div>

      {/* Query Form */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
          <button
            className={`btn ${mode === 'read' ? 'btn-primary' : 'btn-secondary'} btn-sm`}
            onClick={() => setMode('read')}
          >
            <Search size={14} />
            Read by ID
          </button>
          <button
            className={`btn ${mode === 'search' ? 'btn-primary' : 'btn-secondary'} btn-sm`}
            onClick={() => setMode('search')}
          >
            <Activity size={14} />
            Search
          </button>
        </div>

        <form onSubmit={handleExecute}>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Resource Type</label>
              <select
                className="form-select"
                value={resourceType}
                onChange={(e) => setResourceType(e.target.value)}
              >
                {RESOURCE_TYPES.map((rt) => (
                  <option key={rt} value={rt}>{rt}</option>
                ))}
              </select>
            </div>
            {mode === 'read' && (
              <div className="form-group">
                <label className="form-label">Resource ID</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g., patient-123"
                  value={resourceId}
                  onChange={(e) => setResourceId(e.target.value)}
                />
              </div>
            )}
            {mode === 'search' && (
              <div className="form-group">
                <label className="form-label">Search Parameters</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="name=John&birthdate=eq1990-01-01"
                  value={searchParams}
                  onChange={(e) => setSearchParams(e.target.value)}
                />
              </div>
            )}
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={isLoading || (mode === 'read' && !resourceId.trim())}
          >
            {isLoading ? (
              <><div className="spinner spinner-sm" /> Executing...</>
            ) : (
              <><Search size={16} /> Execute</>
            )}
          </button>
        </form>
      </div>

      {/* Results */}
      {isLoading && (
        <div className="loading-container">
          <div className="spinner" />
          <div className="loading-text">Fetching FHIR resource...</div>
        </div>
      )}

      {isError && (
        <div className="error-state">
          <AlertCircle size={44} />
          <div className="error-state-title">Query Failed</div>
          <div className="error-state-text">
            {(error as any)?.message || 'Failed to execute FHIR query.'}
          </div>
          <button className="btn btn-primary" onClick={() => refetch()}>
            <RefreshCw size={16} />
            Retry
          </button>
        </div>
      )}

      {data && !isLoading && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div className="code-block-header">
            <div className="code-block-header-label">
              {mode === 'read' ? `${resourceType}/${resourceId}` : `${resourceType}?${searchParams}`}
            </div>
            <div className="code-block-header-actions">
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setViewMode(viewMode === 'json' ? 'tree' : 'json')}
              >
                {viewMode === 'json' ? <List size={14} /> : <Code size={14} />}
                <span>{viewMode === 'json' ? 'Tree View' : 'JSON View'}</span>
              </button>
              <button className="btn btn-ghost btn-sm" onClick={handleCopy}>
                {copied ? <Check size={14} style={{ color: 'var(--success)' }} /> : <Copy size={14} />}
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
          </div>
          <div className="code-block" style={{ maxHeight: 600, borderTopLeftRadius: 0, borderTopRightRadius: 0 }}>
            {viewMode === 'json' ? formattedJson : renderTree(data)}
          </div>
        </div>
      )}

      {!data && !isLoading && !isError && (
        <div className="empty-state">
          <Activity size={48} />
          <div className="empty-state-title">Execute a query</div>
          <div className="empty-state-text">
            Select a resource type and enter an ID or search parameters to fetch FHIR data.
          </div>
        </div>
      )}
    </div>
  );
};

export default FhirExplorer;
