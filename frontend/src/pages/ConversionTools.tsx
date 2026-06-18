import React, { useState, useRef } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  ArrowLeftRight,
  FileText,
  Download,
  AlertTriangle,
  AlertCircle,
  RefreshCw,
  Upload,
  Copy,
  Check,
  Clock,
  FileCode,
  FileJson,
  Activity,
} from 'lucide-react';
import { conversionApi } from '../services/api';

type ConversionMode = 'ccda-fhir' | 'fhir-ccda' | 'fhir-pdf' | 'ccda-pdf' | 'hl7-fhir';

const MODES: { key: ConversionMode; label: string; icon: React.ReactNode; inputType: 'file' | 'textarea' | 'none' }[] = [
  { key: 'ccda-fhir', label: 'C-CDA → FHIR', icon: <FileCode size={24} />, inputType: 'file' },
  { key: 'fhir-ccda', label: 'FHIR → C-CDA', icon: <FileText size={24} />, inputType: 'textarea' },
  { key: 'fhir-pdf', label: 'FHIR → PDF', icon: <FileText size={24} />, inputType: 'textarea' },
  { key: 'ccda-pdf', label: 'C-CDA → PDF', icon: <FileText size={24} />, inputType: 'file' },
  { key: 'hl7-fhir', label: 'HL7v2 → FHIR', icon: <Activity size={24} />, inputType: 'textarea' },
];

const ConversionTools: React.FC = () => {
  const [activeMode, setActiveMode] = useState<ConversionMode>('ccda-fhir');
  const [inputText, setInputText] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [output, setOutput] = useState<any>(null);
  const [validationWarnings, setValidationWarnings] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: history } = useQuery({
    queryKey: ['conversion-history'],
    queryFn: () => conversionApi.getHistory().catch(() => []),
  });

  const convertMutation = useMutation({
    mutationFn: async () => {
      setValidationWarnings([]);
      setOutput(null);

      switch (activeMode) {
        case 'ccda-fhir':
          if (selectedFile) {
            return conversionApi.ccdaToFhir(selectedFile);
          }
          if (inputText) {
            return conversionApi.ccdaToFhir(inputText);
          }
          throw new Error('Please provide C-CDA XML input');

        case 'fhir-ccda': {
          if (!inputText) throw new Error('Please enter FHIR JSON');
          const bundle = JSON.parse(inputText);
          return conversionApi.fhirToCcda(bundle);
        }

        case 'fhir-pdf': {
          if (!inputText) throw new Error('Please enter FHIR JSON');
          const bundle = JSON.parse(inputText);
          const blob = await conversionApi.fhirToPdf(bundle);
          return { blob, isPdf: true };
        }

        case 'ccda-pdf':
          if (selectedFile) {
            // Use C-CDA to FHIR first, then FHIR to PDF
            const fhirResult = await conversionApi.ccdaToFhir(selectedFile);
            const blob = await conversionApi.fhirToPdf(fhirResult);
            return { blob, isPdf: true };
          }
          throw new Error('Please select a C-CDA file');

        case 'hl7-fhir': {
          if (!inputText) throw new Error('Please enter HL7v2 message');
          return conversionApi.hl7v2ToFhir(inputText);
        }

        default:
          throw new Error('Unknown conversion mode');
      }
    },
    onSuccess: async (result) => {
      if (result?.isPdf && result?.blob) {
        // Create download link for PDF
        const url = URL.createObjectURL(result.blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `converted-${Date.now()}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
        setOutput({ message: 'PDF downloaded successfully' });
      } else {
        setOutput(result);
        // Validate output
        try {
          const validation = await conversionApi.validate(result, activeMode.split('-')[1] || 'fhir');
          if (validation?.warnings?.length) {
            setValidationWarnings(validation.warnings);
          }
        } catch {}
      }
    },
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      const reader = new FileReader();
      reader.onload = (ev) => {
        setInputText(ev.target?.result as string || '');
      };
      reader.readAsText(file);
    }
  };

  const handleCopy = async () => {
    if (output) {
      const text = output.blob ? 'PDF downloaded' : JSON.stringify(output, null, 2);
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleModeSelect = (mode: ConversionMode) => {
    setActiveMode(mode);
    setOutput(null);
    setValidationWarnings([]);
    setSelectedFile(null);
    setInputText('');
  };

  const currentMode = MODES.find((m) => m.key === activeMode)!;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1>Conversion Tools</h1>
        <p className="text-muted text-sm">Convert between healthcare data formats</p>
      </div>

      {/* Conversion Mode Cards */}
      <div className="conversion-modes">
        {MODES.map((mode) => (
          <div
            key={mode.key}
            className={`conversion-mode-card ${activeMode === mode.key ? 'active' : ''}`}
            onClick={() => handleModeSelect(mode.key)}
          >
            {mode.icon}
            <div className="conversion-mode-card-label">{mode.label}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Input Panel */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <ArrowLeftRight size={18} />
              Input
            </div>
            <span className="badge badge-info">{currentMode.label}</span>
          </div>

          {currentMode.inputType === 'file' && (
            <div style={{ marginBottom: 16 }}>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xml,.txt"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
              <button
                className="btn btn-secondary w-full"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload size={16} />
                {selectedFile ? selectedFile.name : 'Choose C-CDA XML File'}
              </button>
            </div>
          )}

          <div className="form-group">
            <label className="form-label">
              {currentMode.inputType === 'file' ? 'Or paste content below' : 'Input Content'}
            </label>
            <textarea
              className="form-textarea"
              rows={10}
              placeholder={
                activeMode === 'hl7-fhir'
                  ? 'MSH|^~\\&|...'
                  : activeMode.includes('fhir')
                  ? '{\n  "resourceType": "Bundle",\n  ...\n}'
                  : '<?xml version="1.0"?>\n<ClinicalDocument>...'
              }
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              style={{ fontFamily: 'monospace', fontSize: '0.78rem' }}
            />
          </div>

          <button
            className="btn btn-primary w-full"
            onClick={() => convertMutation.mutate()}
            disabled={convertMutation.isPending}
          >
            {convertMutation.isPending ? (
              <><div className="spinner spinner-sm" /> Converting...</>
            ) : (
              <><RefreshCw size={16} /> Convert</>
            )}
          </button>
        </div>

        {/* Output Panel */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <FileText size={18} />
              Output
            </div>
            {output && !output.blob && (
              <button className="btn btn-ghost btn-sm" onClick={handleCopy}>
                {copied ? <Check size={14} style={{ color: 'var(--success)' }} /> : <Copy size={14} />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            )}
          </div>

          {convertMutation.isPending && (
            <div className="loading-container">
              <div className="spinner" />
              <div className="loading-text">Converting...</div>
            </div>
          )}

          {convertMutation.isError && (
            <div className="error-state" style={{ padding: 24 }}>
              <AlertCircle size={32} />
              <div className="error-state-title">Conversion Failed</div>
              <div className="error-state-text">
                {(convertMutation.error as any)?.message || 'An error occurred during conversion.'}
              </div>
            </div>
          )}

          {/* Validation Warnings */}
          {validationWarnings.length > 0 && (
            <div className="alert alert-warning" style={{ marginBottom: 12 }}>
              <AlertTriangle size={16} />
              <div>
                <strong>Validation Warnings:</strong>
                <ul style={{ margin: '4px 0 0 16px', fontSize: '0.82rem' }}>
                  {validationWarnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {output && !convertMutation.isPending && (
            <div className="code-block" style={{ maxHeight: 400 }}>
              {output.blob
                ? 'PDF file has been downloaded.'
                : JSON.stringify(output, null, 2)}
            </div>
          )}

          {!output && !convertMutation.isPending && !convertMutation.isError && (
            <div className="empty-state" style={{ padding: 24 }}>
              <FileText size={32} />
              <div className="empty-state-text">Enter input and click Convert to see results</div>
            </div>
          )}
        </div>
      </div>

      {/* Conversion History */}
      <div className="card" style={{ marginTop: 24 }}>
        <div className="card-header">
          <div className="card-title">
            <Clock size={18} />
            Conversion History
          </div>
        </div>
        {!history || history.length === 0 ? (
          <div className="empty-state" style={{ padding: 24 }}>
            <Clock size={32} />
            <div className="empty-state-text">No conversions yet</div>
          </div>
        ) : (
          <div className="table-container" style={{ border: 'none' }}>
            <table>
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Type</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {history.slice(0, 10).map((h: any, idx: number) => (
                  <tr key={h.id || idx}>
                    <td>{h.timestamp ? new Date(h.timestamp).toLocaleString() : '-'}</td>
                    <td>{h.type || h.conversionType || '-'}</td>
                    <td>
                      <span className={`badge badge-${h.status === 'success' ? 'success' : h.status === 'failed' ? 'danger' : 'neutral'}`}>
                        {h.status || 'Completed'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default ConversionTools;
