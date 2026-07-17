import React, { useState, useEffect, useCallback, useRef, Fragment } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Search,
  Pill,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Info,
  AlertCircle,
  Plus,
  Minus,
  Trash2,
  Save,
  Printer,
  Eye,
  ChevronDown,
  ChevronUp,
  Loader2,
  Shield,
  Heart,
  User,
  Calendar,
  Settings,
  Download,
  Copy,
  RotateCcw,
  Flag,
  Zap,
  Home,
  FileText,
} from 'lucide-react';
import { prescriptionApi, DrugSearchResponse, PrescriptionLineCreate, PrescriptionCreate, SafetyCheckResponse } from '../services/api';

const PRESCRIPTION_FREQUENCIES = [
  { value: 'OD', label: 'OD - Once Daily' },
  { value: 'BD', label: 'BD - Twice Daily' },
  { value: 'TDS', label: 'TDS - Three Times Daily' },
  { value: 'QID', label: 'QID - Four Times Daily' },
  { value: 'SOS', label: 'SOS - As Needed' },
  { value: 'HS', label: 'HS - At Bedtime' },
  { value: 'Q6H', label: 'Q6H - Every 6 Hours' },
  { value: 'Q8H', label: 'Q8H - Every 8 Hours' },
  { value: 'Q12H', label: 'Q12H - Every 12 Hours' },
  { value: 'STAT', label: 'STAT - Immediately' },
  { value: 'PRN', label: 'PRN - As Required' },
  { value: 'CUSTOM', label: 'Custom Schedule' },
];

const PRESCRIPTION_ROUTES = [
  { value: 'PO', label: 'PO - Oral' },
  { value: 'IV', label: 'IV - Intravenous' },
  { value: 'IM', label: 'IM - Intramuscular' },
  { value: 'SC', label: 'SC - Subcutaneous' },
  { value: 'SL', label: 'SL - Sublingual' },
  { value: 'TOPICAL', label: 'Topical' },
  { value: 'INHALATION', label: 'Inhalation' },
  { value: 'PR', label: 'PR - Per Rectum' },
  { value: 'PV', label: 'PV - Per Vaginam' },
  { value: 'OPHTHALMIC', label: 'Ophthalmic' },
  { value: 'OTIC', label: 'Otic' },
  { value: 'NASAL', label: 'Nasal' },
];

const DRUG_FORMS = [
  { value: 'TABLET', label: 'Tablet' },
  { value: 'CAPSULE', label: 'Capsule' },
  { value: 'SYRUP', label: 'Syrup' },
  { value: 'SUSPENSION', label: 'Suspension' },
  { value: 'INJECTION', label: 'Injection' },
  { value: 'INFUSION', label: 'Infusion' },
  { value: 'CREAM', label: 'Cream' },
  { value: 'OINTMENT', label: 'Ointment' },
  { value: 'GEL', label: 'Gel' },
  { value: 'DROPS', label: 'Drops' },
  { value: 'INHALER', label: 'Inhaler' },
  { value: 'NEBULIZER', label: 'Nebulizer' },
  { value: 'PATCH', label: 'Patch' },
  { value: 'SUPPOSITORY', label: 'Suppository' },
  { value: 'LOZENGE', label: 'Lozenge' },
  { value: 'SPRAY', label: 'Spray' },
  { value: 'POWDER', label: 'Powder' },
  { value: 'SOLUTION', label: 'Solution' },
];

const QUANTITY_UNITS = ['tablets', 'capsules', 'mL', 'vials', 'ampoules', 'tubes', 'bottles', 'patches', 'units'];

const SAFETY_COLORS = {
  SAFE: { bg: 'bg-green-50', text: 'text-green-700', border: 'border-green-200', icon: CheckCircle, label: 'Safe' },
  CAUTION: { bg: 'bg-yellow-50', text: 'text-yellow-700', border: 'border-yellow-200', icon: AlertTriangle, label: 'Caution' },
  CONTRAINDICATED: { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200', icon: XCircle, label: 'Contraindicated' },
  PENDING: { bg: 'bg-gray-50', text: 'text-gray-500', border: 'border-gray-200', icon: Loader2, label: 'Checking...' },
};

const PrescriptionWriter: React.FC = () => {
  const { patientId } = useParams<{ patientId: string }>();
  const [searchParams] = useSearchParams();
  const encounterId = searchParams.get('encounter');
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // State
  const [drugSearchQuery, setDrugSearchQuery] = useState('');
  const [drugSearchResults, setDrugSearchResults] = useState<DrugSearchResponse[]>([]);
  const [showDrugResults, setShowDrugResults] = useState(false);
  const [selectedDrugIndex, setSelectedDrugIndex] = useState(-1);
  const [activeLineIndex, setActiveLineIndex] = useState<number | null>(null);
  const [safetyResults, setSafetyResults] = useState<SafetyCheckResponse | null>(null);
  const [isRunningSafetyCheck, setIsRunningSafetyCheck] = useState(false);
  const [showPrintPreview, setShowPrintPreview] = useState(false);
  const [prescriptionToPrint, setPrescriptionToPrint] = useState<PrescriptionResponse | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  // Form state
  const [formData, setFormData] = useState({
    diagnosis: '',
    icd10_codes: [] as any[],
    notes: '',
    lines: [] as PrescriptionLineCreate[],
  });

  // Initialize with one empty line
  useEffect(() => {
    if (formData.lines.length === 0) {
      addEmptyLine();
    }
  }, []);

  // Fetch patient data for safety checks
  const { data: patient } = useQuery({
    queryKey: ['patient', patientId],
    queryFn: async () => {
      const res = await fetch(`/api/patients/${patientId}`);
      return res.json();
    },
    enabled: !!patientId,
  });

  // Fetch patient allergies for display
  const { data: allergies } = useQuery({
    queryKey: ['allergies', patientId],
    queryFn: () => prescriptionApi.getPatientAllergies(patientId!),
    enabled: !!patientId,
  });

  // Drug search debounce
  useEffect(() => {
    if (drugSearchQuery.length >= 2) {
      const timeout = setTimeout(async () => {
        try {
          const results = await prescriptionApi.searchDrugs({ q: drugSearchQuery, page_size: 20 });
          setDrugSearchResults(results.drugs);
          setShowDrugResults(true);
          setSelectedDrugIndex(0);
        } catch {
          setDrugSearchResults([]);
        }
      }, 300);
      return () => clearTimeout(timeout);
    } else {
      setDrugSearchResults([]);
      setShowDrugResults(false);
    }
  }, [drugSearchQuery]);

  // Run safety check when lines change
  useEffect(() => {
    if (formData.lines.some(l => l.drug_name) && patientId) {
      const timeout = setTimeout(() => {
        runSafetyCheck();
      }, 500);
      return () => clearTimeout(timeout);
    }
  }, [formData.lines, patientId]);

  const addEmptyLine = () => {
    const newLine: PrescriptionLineCreate = {
      drug_name: '',
      generic_name: '',
      strength: '',
      form: '',
      route: 'PO',
      dose: '',
      frequency: 'BD',
      duration: '',
      quantity: '',
      quantity_unit: 'tablets',
      refills: 0,
      instructions: '',
      before_food: null,
      at_bedtime: false,
      sequence: formData.lines.length,
    };
    setFormData(prev => ({ ...prev, lines: [...prev.lines, newLine] }));
    setActiveLineIndex(formData.lines.length);
  };

  const removeLine = (index: number) => {
    if (formData.lines.length <= 1) return;
    setFormData(prev => ({
      ...prev,
      lines: prev.lines.filter((_, i) => i !== index).map((l, i) => ({ ...l, sequence: i })),
    }));
    if (activeLineIndex === index) setActiveLineIndex(null);
  };

  const updateLine = (index: number, field: keyof PrescriptionLineCreate, value: any) => {
    setFormData(prev => ({
      ...prev,
      lines: prev.lines.map((l, i) => i === index ? { ...l, [field]: value } : l),
    }));
    // Clear safety results for this line to trigger re-check
    if (safetyResults) {
      setSafetyResults(null);
    }
  };

  const selectDrug = (drug: DrugSearchResponse, lineIndex: number) => {
    updateLine(lineIndex, 'drug_id', drug.id);
    updateLine(lineIndex, 'drug_name', drug.name);
    updateLine(lineIndex, 'generic_name', drug.generic_name);
    updateLine(lineIndex, 'strength', drug.strength);
    updateLine(lineIndex, 'form', drug.form);
    updateLine(lineIndex, 'route', drug.route);
    setDrugSearchQuery('');
    setShowDrugResults(false);
    setActiveLineIndex(lineIndex);
  };

  const runSafetyCheck = async () => {
    if (!patientId || formData.lines.length === 0) return;
    
    const linesWithDrugs = formData.lines.filter(l => l.drug_name.trim());
    if (linesWithDrugs.length === 0) return;

    setIsRunningSafetyCheck(true);
    try {
      const result = await prescriptionApi.checkSafety({
        patient_id: patientId,
        lines: linesWithDrugs,
        encounter_id: encounterId || undefined,
      });
      setSafetyResults(result);
    } catch (error) {
      console.error('Safety check failed:', error);
    } finally {
      setIsRunningSafetyCheck(false);
    }
  };

  const getLineSafetyStatus = (lineIndex: number): string => {
    if (!safetyResults) return 'PENDING';
    const lineCheck = safetyResults.line_checks.find((lc: any) => lc.line_index === lineIndex);
    return lineCheck?.safety_status || 'SAFE';
  };

  const getLineWarnings = (lineIndex: number): any[] => {
    if (!safetyResults) return [];
    const lineCheck = safetyResults.line_checks.find((lc: any) => lc.line_index === lineIndex);
    return lineCheck?.warnings || [];
  };

  const SafetyBadge: React.FC<{ status: string }> = ({ status }) => {
    const config = SAFETY_COLORS[status as keyof typeof SAFETY_COLORS] || SAFETY_COLORS.PENDING;
    const Icon = config.icon;
    return (
      <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.bg} ${config.text} ${config.border}`}>
        <Icon className="w-3 h-3" />
        {config.label}
      </span>
    );
  };

  const handleSaveDraft = async () => {
    if (!patientId) return;
    setIsSaving(true);
    setSaveStatus('saving');
    try {
      const prescriptionData: PrescriptionCreate = {
        patient_id: patientId,
        encounter_id: encounterId || undefined,
        diagnosis: formData.diagnosis || undefined,
        icd10_codes: formData.icd10_codes,
        notes: formData.notes || undefined,
        lines: formData.lines.filter(l => l.drug_name.trim()),
      };
      const result = await prescriptionApi.createPrescription(prescriptionData);
      setSaveStatus('saved');
      queryClient.invalidateQueries({ queryKey: ['prescriptions', encounterId] });
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch (error: any) {
      console.error('Save failed:', error);
      setSaveStatus('error');
      alert(error.message || 'Failed to save prescription');
    } finally {
      setIsSaving(false);
    }
  };

  const handleFinalize = async () => {
    if (!patientId) return;
    // First save as draft, then update status to ACTIVE
    setIsSaving(true);
    setSaveStatus('saving');
    try {
      const prescriptionData: PrescriptionCreate = {
        patient_id: patientId,
        encounter_id: encounterId || undefined,
        diagnosis: formData.diagnosis || undefined,
        icd10_codes: formData.icd10_codes,
        notes: formData.notes || undefined,
        lines: formData.lines.filter(l => l.drug_name.trim()),
      };
      const result = await prescriptionApi.createPrescription(prescriptionData);
      // Update to ACTIVE status
      await prescriptionApi.updatePrescription(result.id, { status: 'ACTIVE' });
      setSaveStatus('saved');
      queryClient.invalidateQueries({ queryKey: ['prescriptions', encounterId] });
      alert('Prescription finalized and sent to pharmacy!');
      navigate(`/patients/${patientId}/chart`);
    } catch (error: any) {
      console.error('Finalize failed:', error);
      setSaveStatus('error');
      alert(error.message || 'Failed to finalize prescription');
    } finally {
      setIsSaving(false);
    }
  };

  const handlePrint = async () => {
    if (!patientId) return;
    try {
      // For now, just open print preview with current form data
      // In production, this would call a PDF generation endpoint
      setPrescriptionToPrint({
        id: 'draft',
        prescription_number: `RX-DRAFT-${Date.now()}`,
        patient_id: patientId,
        encounter_id: encounterId,
        doctor_id: '',
        status: 'DRAFT',
        diagnosis: formData.diagnosis,
        icd10_codes: formData.icd10_codes,
        notes: formData.notes,
        prescribed_at: new Date().toISOString(),
        started_at: null,
        completed_at: null,
        expires_at: null,
        lines: formData.lines.filter(l => l.drug_name.trim()).map((l, i) => ({
          id: `line-${i}`,
          drug_id: l.drug_id || null,
          drug_name: l.drug_name,
          generic_name: l.generic_name,
          strength: l.strength,
          form: l.form,
          route: l.route,
          dose: l.dose,
          frequency: l.frequency,
          frequency_custom: l.frequency_custom,
          duration: l.duration,
          duration_days: null,
          quantity: l.quantity,
          quantity_unit: l.quantity_unit,
          refills: l.refills,
          instructions: l.instructions,
          before_food: l.before_food,
          at_bedtime: l.at_bedtime,
          sequence: i,
          safety_status: getLineSafetyStatus(i),
          interaction_warnings: getLineWarnings(i).filter(w => w.type === 'drug_interaction'),
          allergy_warnings: getLineWarnings(i).filter(w => w.type === 'allergy'),
          duplicate_therapy_warnings: getLineWarnings(i).filter(w => w.type === 'duplicate_therapy'),
          dose_warnings: getLineWarnings(i).filter(w => w.type === 'dose_range'),
          pregnancy_warnings: getLineWarnings(i).filter(w => w.type === 'pregnancy_warning'),
        })),
        patient_name: patient?.first_name + ' ' + patient?.last_name,
        patient_age: patient?.age_years,
        patient_gender: patient?.gender,
        uhid: patient?.uhid,
        doctor_name: 'Dr. Current User',
      });
      setShowPrintPreview(true);
    } catch (error) {
      console.error('Print failed:', error);
    }
  };

  const handleBack = () => {
    if (encounterId) {
      navigate(`/patients/${patientId}/soap?token=${encounterId}`);
    } else {
      navigate(`/patients/${patientId}/chart`);
    }
  };

  if (!patientId) {
    return <div className="loading-container"><Loader2 className="spinner" /> Loading...</div>;
  }

  return (
    <div className="prescription-writer-page">
      {/* Header */}
      <div className="rx-header">
        <button className="btn btn-ghost btn-sm" onClick={handleBack}>
          <Home className="w-4 h-4 mr-1" /> Back to Patient
        </button>
        <div className="header-info">
          <h1><Pill className="w-6 h-6 inline mr-2" /> Prescription Writer</h1>
          <div className="patient-badges">
            <span className="badge badge-primary">{patient?.first_name} {patient?.last_name}</span>
            {patient?.age_years && <span className="badge badge-secondary">{patient.age_years}y</span>}
            {patient?.gender && <span className="badge badge-secondary">{patient.gender}</span>}
            {patient?.uhid && <span className="badge badge-outline">{patient.uhid}</span>}
            {encounterId && <span className="badge badge-outline">Encounter: {encounterId.slice(0,8)}</span>}
          </div>
        </div>
        <div className="header-actions">
          <button className="btn btn-outline" onClick={handlePrint} disabled={formData.lines.every(l => !l.drug_name.trim())}>
            <Printer className="w-4 h-4 mr-1" /> Print Preview
          </button>
          <button className="btn btn-secondary" onClick={handleSaveDraft} disabled={isSaving || formData.lines.every(l => !l.drug_name.trim())}>
            <Save className="w-4 h-4 mr-1" /> {isSaving ? 'Saving...' : 'Save Draft'}
          </button>
          <button className="btn btn-primary" onClick={handleFinalize} disabled={isSaving || formData.lines.every(l => !l.drug_name.trim())}>
            <Zap className="w-4 h-4 mr-1" /> {isSaving ? 'Finalizing...' : 'Finalize & Send to Pharmacy'}
          </button>
        </div>
      </div>

      {/* Safety Summary Bar */}
      {safetyResults && (
        <div className="safety-summary-bar">
          <div className="safety-overall">
            <Shield className={`w-5 h-5 ${safetyResults.overall_safety === 'CONTRAINDICATED' ? 'text-red-500' : safetyResults.overall_safety === 'CAUTION' ? 'text-yellow-500' : 'text-green-500'}`} />
            <span className="font-medium">Overall Safety: </span>
            <SafetyBadge status={safetyResults.overall_safety} />
          </div>
          <div className="safety-counts">
            {safetyResults.summary && (
              <>
                {safetyResults.summary.interactions > 0 && (
                  <span className="badge badge-warning">{safetyResults.summary.interactions} Interactions</span>
                )}
                {safetyResults.summary.allergies > 0 && (
                  <span className="badge badge-danger">{safetyResults.summary.allergies} Allergies</span>
                )}
                {safetyResults.summary.duplicate_therapy > 0 && (
                  <span className="badge badge-warning">{safetyResults.summary.duplicate_therapy} Duplicate Therapy</span>
                )}
                {safetyResults.summary.dose_warnings > 0 && (
                  <span className="badge badge-info">{safetyResults.summary.dose_warnings} Dose Warnings</span>
                )}
                {safetyResults.summary.pregnancy_warnings > 0 && (
                  <span className="badge badge-warning">{safetyResults.summary.pregnancy_warnings} Pregnancy</span>
                )}
              </>
            )}
          </div>
          {isRunningSafetyCheck && <Loader2 className="w-4 h-4 animate-spin text-muted" />}
        </div>
      )}

      {/* Patient Allergies Alert */}
      {allergies && allergies.length > 0 && (
        <div className="allergy-alert">
          <AlertTriangle className="w-4 h-4 text-yellow-500" />
          <span className="font-medium">Known Allergies:</span>
          {allergies.map((a: any) => (
            <span key={a.id} className="badge badge-warning mr-1">
              {a.substance} ({a.reaction_type}){a.manifestation && ` - ${a.manifestation}`}
            </span>
          ))}
        </div>
      )}

      {/* Main Content */}
      <div className="rx-main-grid">
        {/* Left Panel - Prescription Form */}
        <div className="rx-form-panel">
          {/* Diagnosis Section */}
          <div className="form-section">
            <h3 className="section-title"><FileText className="w-4 h-4 mr-1" /> Diagnosis & Notes</h3>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Primary Diagnosis</label>
                <input
                  type="text"
                  className="form-input"
                  value={formData.diagnosis}
                  onChange={e => setFormData(prev => ({ ...prev, diagnosis: e.target.value }))}
                  placeholder="e.g., Type 2 Diabetes Mellitus with Hypertension"
                />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">ICD-10 Codes</label>
                <div className="icd10-chips">
                  {formData.icd10_codes.map((code: any, idx: number) => (
                    <span key={idx} className="badge badge-primary">
                      {code.code} - {code.description}
                      <button type="button" className="ml-1" onClick={() => setFormData(prev => ({ ...prev, icd10_codes: prev.icd10_codes.filter((_, i) => i !== idx) }))}>×</button>
                    </span>
                  ))}
                </div>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Clinical Notes</label>
              <textarea
                className="form-input"
                rows={3}
                value={formData.notes}
                onChange={e => setFormData(prev => ({ ...prev, notes: e.target.value }))}
                placeholder="Additional clinical notes, follow-up instructions, etc."
              />
            </div>
          </div>

          {/* Prescription Lines */}
          <div className="form-section">
            <div className="section-header">
              <h3 className="section-title"><Pill className="w-4 h-4 mr-1" /> Medications</h3>
              <button className="btn btn-sm btn-outline" onClick={addEmptyLine}>
                <Plus className="w-3 h-3 mr-1" /> Add Medication
              </button>
            </div>

            <div className="prescription-lines">
              <div className="rx-table-header">
                <div className="col-drug">Drug</div>
                <div className="col-dose">Dose</div>
                <div className="col-freq">Frequency</div>
                <div className="col-duration">Duration</div>
                <div className="col-qty">Qty</div>
                <div className="col-route">Route</div>
                <div className="col-safety">Safety</div>
                <div className="col-actions">Actions</div>
              </div>

              {formData.lines.map((line, index) => (
                <React.Fragment key={index}>
                  <div className={`rx-line ${activeLineIndex === index ? 'active' : ''}`}>
                    {/* Drug Search */}
                    <div className="col-drug">
                      <div className="drug-search-wrapper">
                        <input
                          type="text"
                          className="form-input drug-search-input"
                          placeholder="Search drug by name, generic, or category..."
                          value={drugSearchQuery}
                          onChange={e => { setDrugSearchQuery(e.target.value); setActiveLineIndex(index); }}
                          onFocus={() => { setActiveLineIndex(index); if (drugSearchQuery.length >= 2) setShowDrugResults(true); }}
                          onBlur={() => setTimeout(() => setShowDrugResults(false), 200)}
                          autoComplete="off"
                        />
                        <Search className="search-icon" />
                        {showDrugResults && drugSearchResults.length > 0 && (
                          <div className="drug-dropdown">
                            {drugSearchResults.map((drug, idx) => (
                              <button
                                key={drug.id}
                                className={`drug-result-item ${selectedDrugIndex === idx ? 'selected' : ''}`}
                                onClick={() => selectDrug(drug, index)}
                                onMouseEnter={() => setSelectedDrugIndex(idx)}
                              >
                                <div className="drug-main">
                                  <span className="drug-name">{drug.name}</span>
                                  <span className="drug-generic">{drug.generic_name}</span>
                                </div>
                                <div className="drug-meta">
                                  <span className="drug-strength">{drug.strength}</span>
                                  <span className="drug-form">{drug.form}</span>
                                  <span className="drug-route">{drug.route}</span>
                                  {drug.formulary_price && <span className="drug-price">{drug.formulary_price} {drug.currency}</span>}
                                  {drug.is_preferred && <span className="badge badge-success badge-xs">Preferred</span>}
                                  {drug.is_restricted && <span className="badge badge-warning badge-xs">Restricted</span>}
                                </div>
                              </button>
                            ))}
                            {drugSearchResults.length === 0 && (
                              <div className="drug-no-results">No drugs found matching "{drugSearchQuery}"</div>
                            )}
                          </div>
                        )}
                      </div>
                      {line.drug_id && (
                        <div className="selected-drug-info">
                          <span className="drug-name-selected">{line.drug_name}</span>
                          {line.generic_name && <span className="drug-generic-selected">({line.generic_name})</span>}
                          {line.strength && <span className="drug-strength-selected">{line.strength}</span>}
                          {line.form && <span className="drug-form-selected">{line.form}</span>}
                        </div>
                      )}
                    </div>

                    {/* Dose */}
                    <div className="col-dose">
                      <input
                        type="text"
                        className="form-input"
                        placeholder="e.g., 500mg"
                        value={line.dose}
                        onChange={e => updateLine(index, 'dose', e.target.value)}
                      />
                    </div>

                    {/* Frequency */}
                    <div className="col-freq">
                      <select
                        className="form-select"
                        value={line.frequency}
                        onChange={e => updateLine(index, 'frequency', e.target.value)}
                      >
                        {PRESCRIPTION_FREQUENCIES.map(f => (
                          <option key={f.value} value={f.value}>{f.label}</option>
                        ))}
                      </select>
                      {line.frequency === 'CUSTOM' && (
                        <input
                          type="text"
                          className="form-input mt-1"
                          placeholder="Cron expression (e.g., 0 8,20 * * *)"
                          value={line.frequency_custom || ''}
                          onChange={e => updateLine(index, 'frequency_custom', e.target.value)}
                        />
                      )}
                    </div>

                    {/* Duration */}
                    <div className="col-duration">
                      <input
                        type="text"
                        className="form-input"
                        placeholder="e.g., 7 days"
                        value={line.duration}
                        onChange={e => updateLine(index, 'duration', e.target.value)}
                      />
                    </div>

                    {/* Quantity */}
                    <div className="col-qty">
                      <div className="qty-input-wrapper">
                        <input
                          type="text"
                          className="form-input qty-value"
                          placeholder="Qty"
                          value={line.quantity}
                          onChange={e => updateLine(index, 'quantity', e.target.value)}
                        />
                        <select
                          className="form-select qty-unit"
                          value={line.quantity_unit}
                          onChange={e => updateLine(index, 'quantity_unit', e.target.value)}
                        >
                          {QUANTITY_UNITS.map(u => <option key={u} value={u}>{u}</option>)}
                        </select>
                      </div>
                      <input
                        type="number"
                        className="form-input mt-1"
                        placeholder="Refills"
                        min="0"
                        max="10"
                        value={line.refills}
                        onChange={e => updateLine(index, 'refills', parseInt(e.target.value) || 0)}
                      />
                    </div>

                    {/* Route */}
                    <div className="col-route">
                      <select
                        className="form-select"
                        value={line.route}
                        onChange={e => updateLine(index, 'route', e.target.value)}
                      >
                        {PRESCRIPTION_ROUTES.map(r => (
                          <option key={r.value} value={r.value}>{r.label}</option>
                        ))}
                      </select>
                    </div>

                    {/* Safety Badge */}
                    <div className="col-safety">
                      <SafetyBadge status={getLineSafetyStatus(index)} />
                      {getLineWarnings(index).length > 0 && (
                        <button
                          className="warning-toggle"
                          onClick={() => setActiveLineIndex(activeLineIndex === index ? null : index)}
                        >
                          <AlertCircle className="w-3 h-3" />
                        </button>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="col-actions">
                      <button
                        className="btn btn-ghost btn-xs"
                        onClick={() => removeLine(index)}
                        disabled={formData.lines.length <= 1}
                        title="Remove"
                      >
                        <Trash2 className="w-4 h-4 text-danger" />
                      </button>
                    </div>
                  </div>

                  {/* Warning Details Row */}
                  {activeLineIndex === index && getLineWarnings(index).length > 0 && (
                    <div className="rx-warning-row">
                      <div className="warning-content">
                        {getLineWarnings(index).map((warning: any, wi: number) => (
                          <div key={wi} className={`warning-item ${warning.severity?.toLowerCase() || 'info'}`}>
                            <span className="warning-type">{warning.type.replace(/_/g, ' ').toUpperCase()}</span>
                            <span className="warning-message">{warning.message || warning.clinical_effect || JSON.stringify(warning)}</span>
                            {warning.management && <span className="warning-mgmt">⟶ {warning.management}</span>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </React.Fragment>
              ))}

              {formData.lines.length === 0 && (
                <div className="rx-empty-state">
                  <Pill className="w-12 h-12 text-muted mx-auto mb-2" />
                  <p className="text-muted">No medications added yet. Click "Add Medication" to start.</p>
                </div>
              )}
            </div>
          </div>

          {/* Instructions Section */}
          <div className="form-section">
            <h3 className="section-title"><Settings className="w-4 h-4 mr-1" /> Special Instructions (per line)</h3>
            <div className="instructions-grid">
              {formData.lines.map((line, index) => (
                line.drug_name && (
                  <div key={index} className="instruction-card">
                    <div className="instruction-header">
                      <span className="instruction-drug">{line.drug_name}</span>
                      <span className="instruction-dose">{line.dose} {line.frequency} × {line.duration}</span>
                    </div>
                    <div className="instruction-fields">
                      <label className="checkbox-inline">
                        <input
                          type="checkbox"
                          checked={!!line.before_food}
                          onChange={e => updateLine(index, 'before_food', e.target.checked ? true : null)}
                        />
                        <span>{line.before_food === true ? 'Before Food' : line.before_food === false ? 'After Food' : 'With Food'}</span>
                      </label>
                      <label className="checkbox-inline">
                        <input
                          type="checkbox"
                          checked={line.at_bedtime}
                          onChange={e => updateLine(index, 'at_bedtime', e.target.checked)}
                        />
                        <span>At Bedtime</span>
                      </label>
                    </div>
                    <textarea
                      className="form-input"
                      rows={2}
                      placeholder="Additional instructions (e.g., 'Take with plenty of water', 'Avoid dairy products')"
                      value={line.instructions || ''}
                      onChange={e => updateLine(index, 'instructions', e.target.value)}
                    />
                  </div>
                )
              ))}
            </div>
          </div>
        </div>

        {/* Right Panel - Drug Info & Safety */}
        <div className="rx-sidebar">
          {/* Drug Details Panel */}
          {activeLineIndex !== null && formData.lines[activeLineIndex]?.drug_id && (
            <div className="sidebar-card">
              <h3 className="sidebar-title">Drug Information</h3>
              <DrugDetailPanel drugId={formData.lines[activeLineIndex].drug_id!} />
            </div>
          )}

          {/* Safety Check Panel */}
          <div className="sidebar-card">
            <h3 className="sidebar-title"><Shield className="w-4 h-4 mr-1" /> Real-time Safety Check</h3>
            {safetyResults ? (
              <div className="safety-details">
                <div className={`safety-overall ${safetyResults.overall_safety.toLowerCase()}`}>
                  <SafetyBadge status={safetyResults.overall_safety} />
                </div>
                <div className="safety-breakdown">
                  {safetyResults.summary && (
                    <>
                      <div className="safety-stat">
                        <span className="stat-value text-red-600">{safetyResults.summary.interactions}</span>
                        <span className="stat-label">Drug Interactions</span>
                      </div>
                      <div className="safety-stat">
                        <span className="stat-value text-red-600">{safetyResults.summary.allergies}</span>
                        <span className="stat-label">Allergy Alerts</span>
                      </div>
                      <div className="safety-stat">
                        <span className="stat-value text-yellow-600">{safetyResults.summary.duplicate_therapy}</span>
                        <span className="stat-label">Duplicate Therapy</span>
                      </div>
                      <div className="safety-stat">
                        <span className="stat-value text-blue-600">{safetyResults.summary.dose_warnings}</span>
                        <span className="stat-label">Dose Warnings</span>
                      </div>
                      <div className="safety-stat">
                        <span className="stat-value text-purple-600">{safetyResults.summary.pregnancy_warnings}</span>
                        <span className="stat-label">Pregnancy/Lactation</span>
                      </div>
                    </>
                  )}
                </div>
              </div>
            ) : (
              <div className="safety-pending">
                <Loader2 className="w-8 h-8 animate-spin text-muted mx-auto mb-2" />
                <p className="text-center text-muted">Enter medications to run safety checks</p>
              </div>
            )}
          </div>

          {/* Quick Actions */}
          <div className="sidebar-card">
            <h3 className="sidebar-title"><Zap className="w-4 h-4 mr-1" /> Quick Actions</h3>
            <div className="quick-actions">
              <button className="quick-action-btn" onClick={handlePrint} disabled={formData.lines.every(l => !l.drug_name.trim())}>
                <Printer className="w-5 h-5" /> Print Prescription
              </button>
              <button className="quick-action-btn" onClick={handleSaveDraft} disabled={isSaving}>
                <Save className="w-5 h-5" /> Save as Draft
              </button>
              <button className="quick-action-btn primary" onClick={handleFinalize} disabled={isSaving || formData.lines.every(l => !l.drug_name.trim())}>
                <Zap className="w-5 h-5" /> Finalize & Send
              </button>
            </div>
          </div>

          {/* Patient Context */}
          <div className="sidebar-card">
            <h3 className="sidebar-title"><User className="w-4 h-4 mr-1" /> Patient Context</h3>
            <div className="patient-context">
              <div className="context-item">
                <span className="context-label">Age</span>
                <span className="context-value">{patient?.age_years || 'N/A'} years</span>
              </div>
              <div className="context-item">
                <span className="context-label">Gender</span>
                <span className="context-value">{patient?.gender || 'N/A'}</span>
              </div>
              <div className="context-item">
                <span className="context-label">UHID</span>
                <span className="context-value">{patient?.uhid || 'N/A'}</span>
              </div>
              <div className="context-item">
                <span className="context-label">Weight</span>
                <span className="context-value">{patient?.weight_kg || 'Not recorded'} kg</span>
              </div>
              <div className="context-item">
                <span className="context-label">Renal Function</span>
                <span className="context-value">{patient?.egfr || 'Not available'}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Print Preview Modal */}
      {showPrintPreview && prescriptionToPrint && (
        <div className="modal-overlay" onClick={() => setShowPrintPreview(false)}>
          <div className="modal-content print-preview" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2><Printer className="w-5 h-5 mr-2" /> Prescription Preview</h2>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowPrintPreview(false)}>
                <XCircle className="w-4 h-4" />
              </button>
            </div>
            <PrescriptionPrintView prescription={prescriptionToPrint} />
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => window.print()}>
                <Printer className="w-4 h-4 mr-1" /> Print
              </button>
              <button className="btn btn-primary" onClick={() => setShowPrintPreview(false)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Drug Detail Panel Component
const DrugDetailPanel: React.FC<{ drugId: string }> = ({ drugId }) => {
  const { data: detail, isLoading } = useQuery({
    queryKey: ['drugDetail', drugId],
    queryFn: () => prescriptionApi.getDrugDetail(drugId),
    enabled: !!drugId,
  });

  if (isLoading) return <div className="loading-small"><Loader2 className="w-4 h-4 animate-spin" /></div>;
  if (!detail) return <div className="text-muted text-sm">Drug details not available</div>;

  return (
    <div className="drug-detail">
      <div className="detail-row"><span className="detail-label">Generic:</span> <span>{detail.generic_name}</span></div>
      <div className="detail-row"><span className="detail-label">Strength:</span> <span>{detail.strength}</span></div>
      <div className="detail-row"><span className="detail-label">Form:</span> <span>{detail.form}</span></div>
      <div className="detail-row"><span className="detail-label">Route:</span> <span>{detail.route}</span></div>
      <div className="detail-row"><span className="detail-label">Class:</span> <span>{detail.drug_class}</span></div>
      <div className="detail-row"><span className="detail-label">ATC Code:</span> <span>{detail.atc_code || 'N/A'}</span></div>
      <div className="detail-row"><span className="detail-label">Pregnancy:</span> <span className={`badge ${detail.pregnancy_category === 'X' ? 'badge-danger' : detail.pregnancy_category === 'D' ? 'badge-warning' : 'badge-success'}`}>{detail.pregnancy_category}</span></div>
      <div className="detail-row"><span className="detail-label">Price:</span> <span>{detail.price} {detail.currency}</span></div>
      
      {detail.dosing_adult && Object.keys(detail.dosing_adult).length > 0 && (
        <div className="detail-section">
          <h4>Adult Dosing</h4>
          <pre className="dosing-json">{JSON.stringify(detail.dosing_adult, null, 2)}</pre>
        </div>
      )}
    </div>
  );
};

// Prescription Print View Component
interface PrescriptionResponse {
  id: string;
  prescription_number: string | null;
  patient_id: string;
  encounter_id: string | null;
  doctor_id: string | null;
  status: string;
  diagnosis: string | null;
  icd10_codes: any[];
  notes: string | null;
  prescribed_at: string;
  started_at: string | null;
  completed_at: string | null;
  expires_at: string | null;
  lines: any[];
  patient_name: string | null;
  patient_age: number | null;
  patient_gender: string | null;
  uhid: string | null;
  doctor_name: string | null;
}

const PrescriptionPrintView: React.FC<{ prescription: PrescriptionResponse }> = ({ prescription }) => {
  const formatDate = (dateStr: string) => new Date(dateStr).toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric'
  });

  const getFrequencyLabel = (freq: string) => {
    const map: Record<string, string> = {
      'OD': 'Once Daily', 'BD': 'Twice Daily', 'TDS': 'Three Times Daily',
      'QID': 'Four Times Daily', 'SOS': 'As Needed', 'HS': 'At Bedtime',
      'Q6H': 'Every 6 Hours', 'Q8H': 'Every 8 Hours', 'Q12H': 'Every 12 Hours',
      'STAT': 'Immediately', 'PRN': 'As Required',
    };
    return map[freq] || freq;
  };

  const getRouteLabel = (route: string) => {
    const map: Record<string, string> = {
      'PO': 'Oral', 'IV': 'Intravenous', 'IM': 'Intramuscular', 'SC': 'Subcutaneous',
      'SL': 'Sublingual', 'TOPICAL': 'Topical', 'INHALATION': 'Inhalation',
    };
    return map[route] || route;
  };

  const getInstructions = (line: any) => {
    const parts = [];
    if (line.before_food === true) parts.push('Before food');
    else if (line.before_food === false) parts.push('After food');
    else parts.push('With food');
    if (line.at_bedtime) parts.push('At bedtime');
    if (line.instructions) parts.push(line.instructions);
    return parts.join('; ');
  };

  return (
    <div className="print-prescription" style={{ maxWidth: '210mm', margin: '0 auto', padding: '20mm' }}>
      {/* Hospital Header */}
      <div className="rx-print-header" style={{ textAlign: 'center', marginBottom: '20px', borderBottom: '2px solid #1e3a5f', paddingBottom: '15px' }}>
        <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#1e3a5f' }}>HEALTHBRIDGE CLINIC</div>
        <div style={{ fontSize: '14px', color: '#666', marginTop: '4px' }}>123 Healthcare Avenue, Medical District, City - 400001</div>
        <div style={{ fontSize: '12px', color: '#666' }}>Phone: +91-22-XXXX-XXXX | Email: info@healthbridge.in | Reg: MH-XXXX</div>
      </div>

      {/* Rx Symbol and Title */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px', paddingBottom: '10px', borderBottom: '1px solid #ddd' }}>
        <div style={{ fontSize: '36px', fontWeight: 'bold', color: '#1e3a5f', fontFamily: 'serif' }}>℞</div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '18px', fontWeight: 'bold' }}>PRESCRIPTION</div>
          <div style={{ fontSize: '12px', color: '#666' }}>Rx No: {prescription.prescription_number}</div>
          <div style={{ fontSize: '12px', color: '#666' }}>Date: {formatDate(prescription.prescribed_at)}</div>
        </div>
      </div>

      {/* Patient Info */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px', paddingBottom: '15px', borderBottom: '1px solid #ddd' }}>
        <div>
          <div style={{ fontWeight: 'bold', fontSize: '16px' }}>{prescription.patient_name}</div>
          <div style={{ fontSize: '12px', color: '#666' }}>Age: {prescription.patient_age} | Gender: {prescription.patient_gender} | UHID: {prescription.uhid}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '12px', color: '#666' }}>Dr. {prescription.doctor_name}</div>
          {prescription.diagnosis && <div style={{ fontSize: '12px', marginTop: '4px' }}>Dx: {prescription.diagnosis}</div>}
        </div>
      </div>

      {/* Medications Table */}
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: '20px' }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #1e3a5f' }}>
            <th style={{ textAlign: 'left', padding: '8px', fontSize: '12px', color: '#1e3a5f' }}>#</th>
            <th style={{ textAlign: 'left', padding: '8px', fontSize: '12px', color: '#1e3a5f' }}>Drug (Generic)</th>
            <th style={{ textAlign: 'left', padding: '8px', fontSize: '12px', color: '#1e3a5f' }}>Strength</th>
            <th style={{ textAlign: 'left', padding: '8px', fontSize: '12px', color: '#1e3a5f' }}>Dose</th>
            <th style={{ textAlign: 'left', padding: '8px', fontSize: '12px', color: '#1e3a5f' }}>Frequency</th>
            <th style={{ textAlign: 'left', padding: '8px', fontSize: '12px', color: '#1e3a5f' }}>Duration</th>
            <th style={{ textAlign: 'left', padding: '8px', fontSize: '12px', color: '#1e3a5f' }}>Qty</th>
            <th style={{ textAlign: 'left', padding: '8px', fontSize: '12px', color: '#1e3a5f' }}>Route</th>
            <th style={{ textAlign: 'left', padding: '8px', fontSize: '12px', color: '#1e3a5f' }}>Instructions</th>
          </tr>
        </thead>
        <tbody>
          {prescription.lines.map((line, i) => (
            <tr key={line.id} style={{ borderBottom: '1px solid #eee' }}>
              <td style={{ padding: '8px', fontSize: '12px' }}>{i + 1}</td>
              <td style={{ padding: '8px', fontSize: '12px' }}>
                <div style={{ fontWeight: '500' }}>{line.drug_name}</div>
                {line.generic_name && <div style={{ fontSize: '11px', color: '#666' }}>({line.generic_name})</div>}
              </td>
              <td style={{ padding: '8px', fontSize: '12px' }}>{line.strength || '-'}</td>
              <td style={{ padding: '8px', fontSize: '12px' }}>{line.dose}</td>
              <td style={{ padding: '8px', fontSize: '12px' }}>{getFrequencyLabel(line.frequency)}</td>
              <td style={{ padding: '8px', fontSize: '12px' }}>{line.duration}</td>
              <td style={{ padding: '8px', fontSize: '12px' }}>{line.quantity} {line.quantity_unit}</td>
              <td style={{ padding: '8px', fontSize: '12px' }}>{getRouteLabel(line.route)}</td>
              <td style={{ padding: '8px', fontSize: '11px', color: '#333' }}>{getInstructions(line)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Safety Warnings */}
      {prescription.lines.some((l: any) => l.interaction_warnings?.length > 0 || l.allergy_warnings?.length > 0 || l.duplicate_therapy_warnings?.length > 0) && (
        <div style={{ marginTop: '20px', padding: '15px', background: '#fff8f0', border: '1px solid #f0d8b0', borderRadius: '4px' }}>
          <h4 style={{ color: '#b8860b', marginBottom: '10px' }}>⚠ Safety Alerts</h4>
          {prescription.lines.map((line: any) => (
            <div key={line.id} style={{ marginBottom: '8px' }}>
              <div style={{ fontWeight: 'bold', fontSize: '12px' }}>{line.drug_name}:</div>
              {line.interaction_warnings?.map((w: any, wi: number) => (
                <div key={wi} style={{ fontSize: '11px', color: '#c00', marginLeft: '10px' }}>Interaction: {w.clinical_effect} - {w.management}</div>
              ))}
              {line.allergy_warnings?.map((w: any, wi: number) => (
                <div key={wi} style={{ fontSize: '11px', color: '#c00', marginLeft: '10px' }}>Allergy: {w.substance} - {w.manifestation}</div>
              ))}
              {line.duplicate_therapy_warnings?.map((w: any, wi: number) => (
                <div key={wi} style={{ fontSize: '11px', color: '#b8860b', marginLeft: '10px' }}>Duplicate Therapy: {w.message}</div>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Footer */}
      <div style={{ marginTop: '30px', display: 'flex', justifyContent: 'space-between' }}>
        <div style={{ textAlign: 'left' }}>
          <div style={{ borderTop: '1px solid #333', width: '200px', marginTop: '40px', paddingTop: '4px', fontSize: '12px' }}>Patient Signature</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ borderTop: '1px solid #333', width: '200px', marginTop: '40px', marginLeft: 'auto', paddingTop: '4px', fontSize: '12px' }}>Doctor Signature</div>
        </div>
      </div>

      <div style={{ marginTop: '30px', textAlign: 'center', fontSize: '10px', color: '#999' }}>
        This is a computer-generated prescription. Valid only with doctor's signature and stamp.
      </div>
    </div>
  );
};

export default PrescriptionWriter;