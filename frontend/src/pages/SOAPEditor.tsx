import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FileText,
  Heart,
  Stethoscope,
  Brain,
  ClipboardList,
  Save,
  Loader2,
  ArrowLeft,
  AlertTriangle,
  CheckCircle,
  Clock,
  Search,
  Plus,
  Trash2,
  Download,
  Eye,
  RotateCcw,
  Bell,
  Pill,
  FlaskConical,
  UserPlus,
  Calendar,
  Type,
  Zap,
} from 'lucide-react';
import { soapApi } from '../services/api';
import { vitalsApi } from '../services/api';
import { opdApi } from '../services/api';

type TabType = 'subjective' | 'objective' | 'assessment' | 'plan';

interface ICD10Code {
  code: string;
  description: string;
  category?: string;
  subcategory?: string;
  is_billable: boolean;
  primary?: boolean;
}

interface Medication {
  name: string;
  dose?: string;
  frequency?: string;
  duration?: string;
  route?: string;
  instructions?: string;
}

interface Investigation {
  name: string;
  type?: string;
  priority?: string;
  notes?: string;
}

interface Referral {
  specialty: string;
  reason: string;
  urgency?: string;
  provider?: string;
}

interface VitalSign {
  type: string;
  value: string;
  unit: string;
  recorded_at: string;
  is_abnormal: boolean;
  reference_range_low?: string;
  reference_range_high?: string;
}

interface SOAPNote {
  id: string;
  patient_id: string;
  encounter_id: string;
  token_id: string;
  subjective: string;
  objective: string;
  assessment: string;
  plan: string;
  chief_complaint: string;
  icd10_codes: ICD10Code[];
  medications: Medication[];
  investigations: Investigation[];
  referrals: Referral[];
  follow_up_date: string | null;
  follow_up_notes: string | null;
  status: string;
  version: number;
  word_count: number;
  time_spent_seconds: number;
  last_autosaved_at: string | null;
  patient_name: string;
  patient_age: number | null;
  patient_gender: string | null;
  token_number: number | null;
  uhid: string | null;
  latest_vitals: VitalSign[];
}

const TABS: { id: TabType; label: string; icon: React.ReactNode }[] = [
  { id: 'subjective', label: 'Subjective', icon: <FileText className="w-5 h-5" /> },
  { id: 'objective', label: 'Objective', icon: <Heart className="w-5 h-5" /> },
  { id: 'assessment', label: 'Assessment', icon: <Brain className="w-5 h-5" /> },
  { id: 'plan', label: 'Plan', icon: <ClipboardList className="w-5 h-5" /> },
];

const QUICK_TEMPLATES = [
  {
    id: 'htn',
    name: 'HTN Follow-up',
    subjective: 'Patient presents for routine hypertension follow-up. Reports good medication adherence. No chest pain, dyspnea, headache, or visual disturbances. Home BP readings averaging 130-140/80-85 mmHg.',
    objective: '',
    assessment: 'Essential hypertension - controlled on current regimen.',
    plan: 'Continue current antihypertensive medications. Lifestyle modifications reinforced. Follow-up in 3 months. Order lipid profile and basic metabolic panel.',
    icd10_codes: [{ code: 'I10', description: 'Essential (primary) hypertension', primary: true }],
  },
  {
    id: 'dm',
    name: 'Diabetes Review',
    subjective: 'Patient here for diabetes mellitus follow-up. Reports fair glycemic control. Occasional post-prandial hyperglycemia. No symptoms of hypoglycemia. Denies polyuria, polydipsia, blurred vision.',
    objective: '',
    assessment: 'Type 2 diabetes mellitus - suboptimal control. Needs intensification.',
    plan: 'Adjust metformin dose. Add SGLT2 inhibitor. Counsel on diet and exercise. Order HbA1c, renal function, lipid profile. Ophthalmology referral for annual retinal exam. Follow-up in 1 month.',
    icd10_codes: [{ code: 'E11.65', description: 'Type 2 diabetes mellitus with hyperglycemia', primary: true }],
  },
  {
    id: 'uri',
    name: 'Acute URI',
    subjective: 'Acute onset sore throat, rhinorrhea, cough x 3 days. Low-grade fever yesterday (38.2°C). No dyspnea, chest pain. No sick contacts with similar symptoms.',
    objective: '',
    assessment: 'Acute upper respiratory infection, likely viral.',
    plan: 'Symptomatic management: hydration, rest, antipyretics PRN. Warm saline gargles. Return if symptoms worsen or persist >7 days. No antibiotics indicated at this time.',
    icd10_codes: [{ code: 'J06.9', description: 'Acute upper respiratory infection, unspecified', primary: true }],
  },
];

const MEDICATION_FREQUENCIES = ['OD', 'BD', 'TDS', 'QID', 'SOS', 'HS', 'Weekly', 'Monthly'];
const MEDICATION_ROUTES = ['PO', 'IV', 'IM', 'SC', 'SL', 'Topical', 'Inhalation', 'PR', 'PV'];
const INVESTIGATION_TYPES = ['LAB', 'IMAGING', 'ECG', 'ECHO', 'SPIROMETRY', 'OTHER'];
const INVESTIGATION_PRIORITIES = ['ROUTINE', 'URGENT', 'STAT'];
const REFERRAL_URGENCIES = ['ROUTINE', 'URGENT', 'EMERGENT'];

const SOAPEditor: React.FC = () => {
  const { patientId } = useParams<{ patientId: string }>();
  const [searchParams] = useSearchParams();
  const tokenId = searchParams.get('token');
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<TabType>('subjective');
  const [formData, setFormData] = useState<Partial<SOAPNote>>({
    subjective: '',
    objective: '',
    assessment: '',
    plan: '',
    chief_complaint: '',
    icd10_codes: [],
    medications: [],
    investigations: [],
    referrals: [],
    follow_up_date: '',
    follow_up_notes: '',
    status: 'DRAFT',
    word_count: 0,
    time_spent_seconds: 0,
  });
  const [icd10Search, setIcd10Search] = useState('');
  const [icd10Results, setIcd10Results] = useState<ICD10Code[]>([]);
  const [showIcd10Results, setShowIcd10Results] = useState(false);
  const [selectedIcd10Index, setSelectedIcd10Index] = useState(-1);
  const [autosaveStatus, setAutosaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showFinalizeConfirm, setShowFinalizeConfirm] = useState(false);
  const [startTime] = useState(Date.now());
  const [lastAutosaveTime, setLastAutosaveTime] = useState<number | null>(null);
  const autosaveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const icd10SearchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const textareaRefs = useRef<Record<TabType, HTMLTextAreaElement | null>>({
    subjective: null,
    objective: null,
    assessment: null,
    plan: null,
  });

  // Fetch existing SOAP note
  const { data: soapNote, isLoading, error } = useQuery({
    queryKey: ['soap', patientId, tokenId],
    queryFn: () => soapApi.getByEncounter(patientId!),
    enabled: !!patientId && !!tokenId,
    retry: false,
  });

  // Fetch latest vitals for Objective tab
  const { data: latestVitals } = useQuery({
    queryKey: ['vitals', patientId, 'latest'],
    queryFn: () => vitalsApi.getLatest(patientId!),
    enabled: !!patientId,
  });

  // Fetch token details for chief complaint
  const { data: tokenDetails } = useQuery({
    queryKey: ['token', tokenId],
    queryFn: () => opdApi.getTokenDetails(tokenId!),
    enabled: !!tokenId,
  });

  // Initialize form data
  useEffect(() => {
    if (soapNote) {
      setFormData({
        subjective: soapNote.subjective || '',
        objective: soapNote.objective || '',
        assessment: soapNote.assessment || '',
        plan: soapNote.plan || '',
        chief_complaint: soapNote.chief_complaint || tokenDetails?.chief_complaint || '',
        icd10_codes: soapNote.icd10_codes || [],
        medications: soapNote.medications || [],
        investigations: soapNote.investigations || [],
        referrals: soapNote.referrals || [],
        follow_up_date: soapNote.follow_up_date ? soapNote.follow_up_date.split('T')[0] : '',
        follow_up_notes: soapNote.follow_up_notes || '',
        status: soapNote.status,
        word_count: soapNote.word_count,
        time_spent_seconds: Math.floor((Date.now() - startTime) / 1000),
      });
    } else if (tokenDetails?.chief_complaint && !formData.chief_complaint) {
      setFormData(prev => ({ ...prev, chief_complaint: tokenDetails.chief_complaint }));
    }
  }, [soapNote, tokenDetails]);

  // Auto-populate Objective from vitals
  useEffect(() => {
    if (latestVitals && latestVitals.length > 0 && !formData.objective) {
      const vitalsText = latestVitals
        .map(v => {
          const refLow = v.reference_range_low;
          const refHigh = v.reference_range_high;
          const ref = refLow && refHigh ? ` (Ref: ${refLow}–${refHigh} ${v.unit})` : '';
          const abnormal = v.is_abnormal ? ' ⚠ ABNORMAL' : '';
          return `${v.type.replace(/_/g, ' ').toUpperCase()}: ${v.value} ${v.unit}${ref}${abnormal}`;
        })
        .join('\n');
      setFormData(prev => ({ ...prev, objective: `Vitals:\n${vitalsText}\n\n` }));
    }
  }, [latestVitals]);

  // Auto-save every 30 seconds
  useEffect(() => {
    autosaveTimeoutRef.current = setTimeout(() => {
      if (formData.subjective || formData.objective || formData.assessment || formData.plan) {
        autosave();
      }
    }, 30000);
    return () => {
      if (autosaveTimeoutRef.current) clearTimeout(autosaveTimeoutRef.current);
    };
  }, [formData]);

  // ICD-10 search debounce
  useEffect(() => {
    if (icd10Search.length >= 2) {
      if (icd10SearchTimeoutRef.current) clearTimeout(icd10SearchTimeoutRef.current);
      icd10SearchTimeoutRef.current = setTimeout(() => {
        searchICD10(icd10Search);
      }, 300);
    } else {
      setIcd10Results([]);
    }
    return () => {
      if (icd10SearchTimeoutRef.current) clearTimeout(icd10SearchTimeoutRef.current);
    };
  }, [icd10Search]);

  // Update time spent
  useEffect(() => {
    const interval = setInterval(() => {
      setFormData(prev => ({ ...prev, time_spent_seconds: Math.floor((Date.now() - startTime) / 1000) }));
    }, 1000);
    return () => clearInterval(interval);
  }, [startTime]);

  // Calculate word count
  useEffect(() => {
    const count = [formData.subjective, formData.objective, formData.assessment, formData.plan, formData.chief_complaint]
      .filter(Boolean)
      .join(' ')
      .split(/\s+/)
      .filter(w => w.length > 0).length;
    setFormData(prev => ({ ...prev, word_count: count }));
  }, [formData.subjective, formData.objective, formData.assessment, formData.plan, formData.chief_complaint]);

  // Mutations
  const saveMutation = useMutation({
    mutationFn: (data: Partial<SOAPNote>) => soapApi.createOrUpdate(patientId!, data),
    onSuccess: (savedNote) => {
      setAutosaveStatus('saved');
      setLastAutosaveTime(Date.now());
      setTimeout(() => setAutosaveStatus('idle'), 2000);
      queryClient.invalidateQueries({ queryKey: ['soap', patientId, tokenId] });
    },
    onError: () => {
      setAutosaveStatus('error');
      setTimeout(() => setAutosaveStatus('idle'), 3000);
    },
  });

  const finalizeMutation = useMutation({
    mutationFn: () => soapApi.finalize(patientId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['soap', patientId, tokenId] });
      queryClient.invalidateQueries({ queryKey: ['opd-queue'] });
      alert('Visit completed successfully! Follow-up created if specified.');
      navigate('/opd/queue');
    },
    onError: (err: any) => {
      alert(err.response?.data?.detail || 'Failed to finalize visit');
    },
  });

  const searchICD10 = async (query: string) => {
    try {
      const results = await soapApi.searchICD10(query);
      setIcd10Results(results.codes);
      setShowIcd10Results(true);
    } catch {
      setIcd10Results([]);
    }
  };

  const handleChange = (field: keyof typeof formData, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleTextChange = (tab: TabType, value: string) => {
    setFormData(prev => ({ ...prev, [tab]: value }));
  };

  const addICD10 = (code: ICD10Code) => {
    setFormData(prev => {
      const exists = prev.icd10_codes?.some(c => c.code === code.code);
      if (exists) return prev;
      const newCodes = [...(prev.icd10_codes || []), { ...code, primary: prev.icd10_codes?.length === 0 }];
      return { ...prev, icd10_codes: newCodes };
    });
    setIcd10Search('');
    setShowIcd10Results(false);
    setSelectedIcd10Index(-1);
  };

  const removeICD10 = (index: number) => {
    setFormData(prev => ({
      ...prev,
      icd10_codes: prev.icd10_codes?.filter((_, i) => i !== index) || [],
    }));
  };

  const setPrimaryICD10 = (index: number) => {
    setFormData(prev => ({
      ...prev,
      icd10_codes: prev.icd10_codes?.map((c, i) => ({ ...c, primary: i === index })) || [],
    }));
  };

  const addMedication = () => {
    setFormData(prev => ({
      ...prev,
      medications: [...(prev.medications || []), { name: '', dose: '', frequency: 'BD', duration: '', route: 'PO', instructions: '' }],
    }));
  };

  const updateMedication = (index: number, field: keyof Medication, value: string) => {
    setFormData(prev => ({
      ...prev,
      medications: prev.medications?.map((m, i) => i === index ? { ...m, [field]: value } : m) || [],
    }));
  };

  const removeMedication = (index: number) => {
    setFormData(prev => ({
      ...prev,
      medications: prev.medications?.filter((_, i) => i !== index) || [],
    }));
  };

  const addInvestigation = () => {
    setFormData(prev => ({
      ...prev,
      investigations: [...(prev.investigations || []), { name: '', type: 'LAB', priority: 'ROUTINE', notes: '' }],
    }));
  };

  const updateInvestigation = (index: number, field: keyof Investigation, value: string) => {
    setFormData(prev => ({
      ...prev,
      investigations: prev.investigations?.map((i, idx) => idx === index ? { ...i, [field]: value } : i) || [],
    }));
  };

  const removeInvestigation = (index: number) => {
    setFormData(prev => ({
      ...prev,
      investigations: prev.investigations?.filter((_, i) => i !== index) || [],
    }));
  };

  const addReferral = () => {
    setFormData(prev => ({
      ...prev,
      referrals: [...(prev.referrals || []), { specialty: '', reason: '', urgency: 'ROUTINE', provider: '' }],
    }));
  };

  const updateReferral = (index: number, field: keyof Referral, value: string) => {
    setFormData(prev => ({
      ...prev,
      referrals: prev.referrals?.map((r, i) => i === index ? { ...r, [field]: value } : r) || [],
    }));
  };

  const removeReferral = (index: number) => {
    setFormData(prev => ({
      ...prev,
      referrals: prev.referrals?.filter((_, i) => i !== index) || [],
    }));
  };

  const applyTemplate = (template: typeof QUICK_TEMPLATES[0]) => {
    setFormData(prev => ({
      ...prev,
      subjective: template.subjective,
      assessment: template.assessment,
      plan: template.plan,
      icd10_codes: template.icd10_codes,
    }));
    setActiveTab('subjective');
  };

  const autosave = () => {
    setAutosaveStatus('saving');
    saveMutation.mutate({
      ...formData,
      time_spent_seconds: Math.floor((Date.now() - startTime) / 1000),
    } as Partial<SOAPNote>);
  };

  const handleSave = () => {
    autosave();
  };

  const handleFinalize = () => {
    // Validate required fields
    if (!formData.subjective?.trim()) {
      alert('Subjective section is required');
      setActiveTab('subjective');
      return;
    }
    if (!formData.assessment?.trim()) {
      alert('Assessment section is required');
      setActiveTab('assessment');
      return;
    }
    if (!formData.icd10_codes?.length) {
      alert('At least one ICD-10 diagnosis code is required');
      setActiveTab('assessment');
      return;
    }
    setShowFinalizeConfirm(true);
  };

  const confirmFinalize = () => {
    setShowFinalizeConfirm(false);
    finalizeMutation.mutate();
  };

  const handleExportPDF = async () => {
    try {
      const html = await soapApi.exportPDF(patientId!);
      const newWindow = window.open('', '_blank');
      if (newWindow) {
        newWindow.document.write(html);
        newWindow.document.close();
        setTimeout(() => newWindow.print(), 500);
      }
    } catch (err) {
      alert('Failed to export PDF');
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  if (isLoading) {
    return (
      <div className="soap-editor-page">
        <div className="loading-container">
          <div className="spinner" />
          <div className="loading-text">Loading SOAP note...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="soap-editor-page">
        <div className="error-container">
          <AlertTriangle className="w-12 h-12 text-danger mx-auto mb-4" />
          <h2>Unable to load SOAP note</h2>
          <p className="text-muted">This encounter may not have a SOAP note yet. Start documenting below.</p>
        </div>
      </div>
    );
  }

  const patientName = soapNote?.patient_name || 'Unknown Patient';
  const patientAge = soapNote?.patient_age;
  const patientGender = soapNote?.patient_gender;
  const tokenNumber = soapNote?.token_number;
  const uhid = soapNote?.uhid;

  return (
    <div className="soap-editor-page">
      {/* Header */}
      <div className="soap-header">
        <button className="btn btn-ghost btn-sm" onClick={() => navigate(-1)}>
          <ArrowLeft size={16} /> Back to Queue
        </button>
        <div className="header-info">
          <h1>SOAP Clinical Note</h1>
          <div className="patient-badges">
            <span className="badge badge-primary">{patientName}</span>
            {patientAge && <span className="badge badge-secondary">{patientAge}y</span>}
            {patientGender && <span className="badge badge-secondary">{patientGender}</span>}
            {tokenNumber && <span className="badge badge-outline">Token #{tokenNumber}</span>}
            {uhid && <span className="badge badge-outline">{uhid}</span>}
            <span className={`badge ${formData.status === 'FINALIZED' ? 'badge-success' : 'badge-warning'}`}>
              {formData.status}
            </span>
          </div>
        </div>
        <div className="header-meta">
          <div className="meta-item">
            <Clock size={14} />
            <span>{formatTime(formData.time_spent_seconds)}</span>
          </div>
          <div className="meta-item">
            <Type size={14} />
            <span>{formData.word_count} words</span>
          </div>
          <div className="meta-item">
            <RotateCcw size={14} />
            <span v>{formData.version || 1}</span>
          </div>
          {lastAutosaveTime && (
            <div className="meta-item autosave-indicator">
              <span className={`autosave-dot ${autosaveStatus === 'saving' ? 'saving' : autosaveStatus === 'saved' ? 'saved' : ''}`} />
              <span>Auto-saved {Math.floor((Date.now() - lastAutosaveTime) / 1000)}s ago</span>
            </div>
          )}
        </div>
      </div>

      {/* Quick Templates */}
      <div className="soap-templates">
        <span className="templates-label">Quick Templates:</span>
        {QUICK_TEMPLATES.map(t => (
          <button
            key={t.id}
            className="btn btn-sm btn-outline template-btn"
            onClick={() => applyTemplate(t)}
          >
            {t.name}
          </button>
        ))}
      </div>

      {/* Tab Navigation */}
      <div className="soap-tabs" role="tablist">
        {TABS.map(tab => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`soap-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="soap-tab-content">
        {/* Subjective Tab */}
        {activeTab === 'subjective' && (
          <div className="tab-panel">
            <div className="form-group">
              <label className="form-label">Chief Complaint</label>
              <textarea
                className="form-input"
                value={formData.chief_complaint || ''}
                onChange={e => handleChange('chief_complaint', e.target.value)}
                placeholder="Patient's main reason for visit..."
                rows={2}
              />
            </div>
            <div className="form-group">
              <label className="form-label">History of Present Illness / Subjective</label>
              <textarea
                ref={el => textareaRefs.current.subjective = el}
                className="form-input soap-textarea"
                value={formData.subjective || ''}
                onChange={e => handleTextChange('subjective', e.target.value)}
                placeholder="Patient's symptoms, history, concerns in their own words..."
                rows={15}
                spellCheck={true}
              />
            </div>
          </div>
        )}

        {/* Objective Tab */}
        {activeTab === 'objective' && (
          <div className="tab-panel">
            <div className="vitals-summary">
              <h4><Heart size={16} /> Latest Vitals (auto-populated)</h4>
              {latestVitals && latestVitals.length > 0 ? (
                <div className="vitals-grid">
                  {latestVitals.map(v => (
                    <div key={v.type} className={`vital-card ${v.is_abnormal ? 'abnormal' : ''}`}>
                      <div className="vital-label">{v.type.replace(/_/g, ' ').toUpperCase()}</div>
                      <div className="vital-value">{v.value} <span className="vital-unit">{v.unit}</span></div>
                      {v.reference_range_low && v.reference_range_high && (
                        <div className="vital-ref">Ref: {v.reference_range_low}–{v.reference_range_high} {v.unit}</div>
                      )}
                      {v.is_abnormal && <AlertTriangle className="vital-alert" title="Abnormal value" />}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted">No vitals recorded for this encounter. Go to Vitals tab first.</p>
              )}
            </div>
            <div className="form-group">
              <label className="form-label">Physical Examination / Objective Findings</label>
              <textarea
                ref={el => textareaRefs.current.objective = el}
                className="form-input soap-textarea"
                value={formData.objective || ''}
                onChange={e => handleTextChange('objective', e.target.value)}
                placeholder="Examination findings, observations, test results..."
                rows={15}
                spellCheck={true}
              />
            </div>
          </div>
        )}

        {/* Assessment Tab */}
        {activeTab === 'assessment' && (
          <div className="tab-panel">
            <div className="form-group">
              <label className="form-label">Clinical Assessment / Diagnosis</label>
              <textarea
                ref={el => textareaRefs.current.assessment = el}
                className="form-input soap-textarea"
                value={formData.assessment || ''}
                onChange={e => handleTextChange('assessment', e.target.value)}
                placeholder="Clinical impression, differential diagnosis, reasoning..."
                rows={8}
                spellCheck={true}
              />
            </div>

            {/* ICD-10 Search */}
            <div className="form-group">
              <label className="form-label">ICD-10 Diagnosis Codes <span className="text-danger">*</span></label>
              <div className="icd10-search-wrapper">
                <div className="search-input-wrapper">
                  <Search className="search-icon" />
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Search ICD-10 (e.g., diabetes, hypertension, I10)..."
                    value={icd10Search}
                    onChange={e => setIcd10Search(e.target.value)}
                    onFocus={() => icd10Search && setShowIcd10Results(true)}
                  />
                </div>
                {showIcd10Results && icd10Results.length > 0 && (
                  <div className="icd10-dropdown">
                    {icd10Results.map((code, idx) => (
                      <button
                        key={code.code}
                        className={`icd10-result ${selectedIcd10Index === idx ? 'selected' : ''}`}
                        onClick={() => addICD10(code)}
                        onMouseEnter={() => setSelectedIcd10Index(idx)}
                      >
                        <span className="icd10-code">{code.code}</span>
                        <span className="icd10-desc">{code.description}</span>
                        {code.category && <span className="icd10-cat">{code.category}</span>}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Selected ICD-10 Codes */}
              {(formData.icd10_codes || []).length > 0 && (
                <div className="selected-icd10">
                  <h5>Selected Diagnoses:</h5>
                  <div className="icd10-chips">
                    {formData.icd10_codes.map((code, idx) => (
                      <div key={code.code} className={`icd10-chip ${code.primary ? 'primary' : ''}`}>
                        <span className="icd10-chip-code">{code.code}</span>
                        <span className="icd10-chip-desc">{code.description}</span>
                        {code.primary && <span className="primary-badge">Primary</span>}
                        {!code.primary && (
                          <button
                            className="primary-btn"
                            onClick={() => setPrimaryICD10(idx)}
                            title="Set as primary"
                          >
                            ⭐
                          </button>
                        )}
                        <button
                          className="remove-btn"
                          onClick={() => removeICD10(idx)}
                          aria-label="Remove diagnosis"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Plan Tab */}
        {activeTab === 'plan' && (
          <div className="tab-panel">
            <div className="form-group">
              <label className="form-label">Treatment Plan</label>
              <textarea
                ref={el => textareaRefs.current.plan = el}
                className="form-input soap-textarea"
                value={formData.plan || ''}
                onChange={e => handleTextChange('plan', e.target.value)}
                placeholder="Management plan, instructions, advice..."
                rows={8}
                spellCheck={true}
              />
            </div>

            {/* Medications */}
            <div className="plan-section">
              <div className="section-header">
                <h4><Pill size={18} /> Medications</h4>
                <button className="btn btn-sm btn-primary" onClick={addMedication}>
                  <Plus size={14} /> Add
                </button>
              </div>
              {(formData.medications || []).length === 0 ? (
                <p className="text-muted">No medications added yet.</p>
              ) : (
                <div className="medication-list">
                  {formData.medications.map((med, idx) => (
                    <div key={idx} className="medication-card">
                      <div className="med-row">
                        <input
                          type="text"
                          className="form-input med-name"
                          placeholder="Drug name"
                          value={med.name}
                          onChange={e => updateMedication(idx, 'name', e.target.value)}
                        />
                        <input
                          type="text"
                          className="form-input med-dose"
                          placeholder="Dose (e.g., 500mg)"
                          value={med.dose}
                          onChange={e => updateMedication(idx, 'dose', e.target.value)}
                        />
                        <select
                          className="form-input med-freq"
                          value={med.frequency}
                          onChange={e => updateMedication(idx, 'frequency', e.target.value)}
                        >
                          {MEDICATION_FREQUENCIES.map(f => <option key={f} value={f}>{f}</option>)}
                        </select>
                        <input
                          type="text"
                          className="form-input med-dur"
                          placeholder="Duration (e.g., 30 days)"
                          value={med.duration}
                          onChange={e => updateMedication(idx, 'duration', e.target.value)}
                        />
                        <select
                          className="form-input med-route"
                          value={med.route}
                          onChange={e => updateMedication(idx, 'route', e.target.value)}
                        >
                          {MEDICATION_ROUTES.map(r => <option key={r} value={r}>{r}</option>)}
                        </select>
                        <button className="btn btn-icon btn-danger" onClick={() => removeMedication(idx)}>
                          <Trash2 size={16} />
                        </button>
                      </div>
                      <input
                        type="text"
                        className="form-input med-inst"
                        placeholder="Special instructions..."
                        value={med.instructions}
                        onChange={e => updateMedication(idx, 'instructions', e.target.value)}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Investigations */}
            <div className="plan-section">
              <div className="section-header">
                <h4><FlaskConical size={18} /> Investigations</h4>
                <button className="btn btn-sm btn-primary" onClick={addInvestigation}>
                  <Plus size={14} /> Add
                </button>
              </div>
              {(formData.investigations || []).length === 0 ? (
                <p className="text-muted">No investigations ordered.</p>
              ) : (
                <div className="investigation-list">
                  {formData.investigations.map((inv, idx) => (
                    <div key={idx} className="investigation-card">
                      <input
                        type="text"
                        className="form-input inv-name"
                        placeholder="Test name (e.g., HbA1c, Chest X-Ray)"
                        value={inv.name}
                        onChange={e => updateInvestigation(idx, 'name', e.target.value)}
                      />
                      <select
                        className="form-input inv-type"
                        value={inv.type}
                        onChange={e => updateInvestigation(idx, 'type', e.target.value)}
                      >
                        {INVESTIGATION_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                      </select>
                      <select
                        className="form-input inv-priority"
                        value={inv.priority}
                        onChange={e => updateInvestigation(idx, 'priority', e.target.value)}
                      >
                        {INVESTIGATION_PRIORITIES.map(p => <option key={p} value={p}>{p}</option>)}
                      </select>
                      <input
                        type="text"
                        className="form-input inv-notes"
                        placeholder="Notes..."
                        value={inv.notes}
                        onChange={e => updateInvestigation(idx, 'notes', e.target.value)}
                      />
                      <button className="btn btn-icon btn-danger" onClick={() => removeInvestigation(idx)}>
                        <Trash2 size={16} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Referrals */}
            <div className="plan-section">
              <div className="section-header">
                <h4><UserPlus size={18} /> Referrals</h4>
                <button className="btn btn-sm btn-primary" onClick={addReferral}>
                  <Plus size={14} /> Add
                </button>
              </div>
              {(formData.referrals || []).length === 0 ? (
                <p className="text-muted">No referrals added.</p>
              ) : (
                <div className="referral-list">
                  {formData.referrals.map((ref, idx) => (
                    <div key={idx} className="referral-card">
                      <input
                        type="text"
                        className="form-input ref-spec"
                        placeholder="Specialty (e.g., Cardiology)"
                        value={ref.specialty}
                        onChange={e => updateReferral(idx, 'specialty', e.target.value)}
                      />
                      <input
                        type="text"
                        className="form-input ref-reason"
                        placeholder="Reason for referral"
                        value={ref.reason}
                        onChange={e => updateReferral(idx, 'reason', e.target.value)}
                      />
                      <select
                        className="form-input ref-urgency"
                        value={ref.urgency}
                        onChange={e => updateReferral(idx, 'urgency', e.target.value)}
                      >
                        {REFERRAL_URGENCIES.map(u => <option key={u} value={u}>{u}</option>)}
                      </select>
                      <input
                        type="text"
                        className="form-input ref-prov"
                        placeholder="Preferred provider (optional)"
                        value={ref.provider}
                        onChange={e => updateReferral(idx, 'provider', e.target.value)}
                      />
                      <button className="btn btn-icon btn-danger" onClick={() => removeReferral(idx)}>
                        <Trash2 size={16} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Follow-up */}
            <div className="plan-section followup-section">
              <h4><Calendar size={18} /> Follow-up</h4>
              <div className="followup-fields">
                <div className="form-group">
                  <label className="form-label">Follow-up Date</label>
                  <input
                    type="date"
                    className="form-input"
                    value={formData.follow_up_date || ''}
                    onChange={e => handleChange('follow_up_date', e.target.value)}
                    min={new Date().toISOString().split('T')[0]}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Follow-up Notes</label>
                  <textarea
                    className="form-input"
                    value={formData.follow_up_notes || ''}
                    onChange={e => handleChange('follow_up_notes', e.target.value)}
                    placeholder="Reason for follow-up, specific instructions..."
                    rows={2}
                  />
                </div>
              </div>
            </div>
          </div>
        )}

      </div>

      {/* Bottom Actions */}
      <div className="soap-footer">
        <div className="footer-left">
          <button className="btn btn-secondary" onClick={handleExportPDF} disabled={isSubmitting}>
            <Download size={16} /> Export PDF
          </button>
          <button className="btn btn-outline" onClick={autosave} disabled={autosaveStatus === 'saving' || isSubmitting}>
            <Save size={16} /> Save Draft
            {autosaveStatus === 'saving' && <Loader2 size={14} className="spin" />}
            {autosaveStatus === 'saved' && <CheckCircle size={14} className="text-success" />}
          </button>
        </div>
        <div className="footer-right">
          {formData.status !== 'FINALIZED' && (
            <button
              className="btn btn-primary btn-lg"
              onClick={handleFinalize}
              disabled={isSubmitting || finalizeMutation.isPending}
            >
              <Zap size={18} />
              {finalizeMutation.isPending ? 'Finalizing...' : 'Finalize Visit'}
            </button>
          )}
        </div>
      </div>

      {/* Finalize Confirmation Modal */}
      {showFinalizeConfirm && (
        <div className="modal-overlay" onClick={() => setShowFinalizeConfirm(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3><AlertTriangle className="w-6 h-6 text-warning inline" /> Confirm Visit Completion</h3>
            <p>This will mark the visit as complete and advance the queue. A follow-up appointment will be created if a date is specified.</p>
            <div className="modal-checklist">
              <label><input type="checkbox" checked={!!formData.subjective?.trim()} disabled /> Subjective documented</label>
              <label><input type="checkbox" checked={!!formData.assessment?.trim()} disabled /> Assessment documented</label>
              <label><input type="checkbox" checked={(formData.icd10_codes || []).length > 0} disabled /> ICD-10 diagnosis added</label>
              {formData.follow_up_date && <label><input type="checkbox" checked disabled /> Follow-up scheduled for {formData.follow_up_date}</label>}
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowFinalizeConfirm(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={confirmFinalize} disabled={finalizeMutation.isPending}>
                {finalizeMutation.isPending ? 'Completing...' : 'Complete Visit'}
              </button>
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .soap-editor-page {
          padding: 24px;
          max-width: 1200px;
          margin: 0 auto;
          min-height: 100vh;
          background: var(--bg);
        }
        .soap-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 16px;
          margin-bottom: 20px;
          padding-bottom: 16px;
          border-bottom: 1px solid var(--border);
        }
        .header-info h1 { margin: 0 0 8px; font-size: 1.75rem; color: var(--text); }
        .patient-badges { display: flex; flex-wrap: wrap; gap: 8px; }
        .header-meta { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; font-size: 0.875rem; color: var(--muted); }
        .meta-item { display: flex; align-items: center; gap: 6px; }
        .autosave-indicator { color: var(--success); }
        .autosave-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); transition: all 0.2s; }
        .autosave-dot.saving { background: var(--warning); animation: pulse 1s infinite; }
        .autosave-dot.saved { background: var(--success); }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

        .soap-templates { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }
        .templates-label { font-size: 0.875rem; font-weight: 500; color: var(--muted); }
        .template-btn { font-size: 0.8rem; padding: 6px 12px; }

        .soap-tabs { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }
        .soap-tab { display: flex; align-items: center; gap: 8px; padding: 10px 16px; border: none; background: none; border-radius: 8px 8px 0 0; cursor: pointer; color: var(--muted); font-weight: 500; transition: all 0.2s; }
        .soap-tab:hover { background: var(--card); color: var(--text); }
        .soap-tab.active { background: var(--primary-light); color: var(--primary); }

        .soap-tab-content { background: var(--card); border-radius: 0 0 12px 12px; border: 1px solid var(--border); border-top: none; padding: 24px; }
        .tab-panel { animation: fadeIn 0.2s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }

        .form-group { margin-bottom: 20px; }
        .form-label { display: block; margin-bottom: 8px; font-weight: 500; color: var(--text); font-size: 0.9375rem; }
        .form-label .text-danger { color: var(--danger); }
        .form-input { width: 100%; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; font-size: 0.9375rem; background: var(--bg); color: var(--text); transition: all 0.2s; }
        .form-input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-light); }
        .soap-textarea { min-height: 200px; resize: vertical; font-family: inherit; line-height: 1.7; }

        .vitals-summary { margin-bottom: 24px; padding: 16px; background: var(--bg); border-radius: 8px; border: 1px solid var(--border); }
        .vitals-summary h4 { margin: 0 0 12px; display: flex; align-items: center; gap: 8px; color: var(--text); }
        .vitals-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
        .vital-card { padding: 12px; background: var(--card); border-radius: 8px; border: 1px solid var(--border); }
        .vital-card.abnormal { border-color: var(--danger); background: rgba(239,68,68,0.05); }
        .vital-label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; color: var(--muted); margin-bottom: 4px; }
        .vital-value { font-size: 1.25rem; font-weight: 600; color: var(--text); }
        .vital-unit { font-size: 0.875rem; font-weight: 400; color: var(--muted); }
        .vital-ref { font-size: 0.7rem; color: var(--muted); margin-top: 4px; }
        .vital-alert { color: var(--danger); margin-left: auto; }

        .icd10-search-wrapper { position: relative; }
        .search-input-wrapper { position: relative; display: flex; align-items: center; }
        .search-icon { position: absolute; left: 12px; color: var(--muted); pointer-events: none; }
        .search-input-wrapper .form-input { padding-left: 40px; }
        .icd10-dropdown { position: absolute; top: 100%; left: 0; right: 0; background: var(--card); border: 1px solid var(--border); border-radius: 8px; margin-top: 4px; max-height: 300px; overflow-y: auto; z-index: 100; box-shadow: 0 8px 24px rgba(0,0,0,0.1); }
        .icd10-result { display: flex; align-items: center; gap: 12px; padding: 10px 12px; cursor: pointer; transition: background 0.15s; }
        .icd10-result:hover, .icd10-result.selected { background: var(--primary-light); }
        .icd10-code { font-weight: 600; color: var(--primary); min-width: 80px; font-family: monospace; }
        .icd10-desc { flex: 1; color: var(--text); }
        .icd10-cat { font-size: 0.75rem; color: var(--muted); background: var(--bg); padding: 2px 8px; border-radius: 4px; }

        .selected-icd10 { margin-top: 16px; }
        .selected-icd10 h5 { margin: 0 0 10px; font-size: 0.875rem; color: var(--muted); }
        .icd10-chips { display: flex; flex-wrap: wrap; gap: 8px; }
        .icd10-chip { display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; background: var(--bg); border: 1px solid var(--border); border-radius: 20px; font-size: 0.875rem; }
        .icd10-chip.primary { border-color: var(--primary); background: var(--primary-light); }
        .icd10-chip-code { font-weight: 600; font-family: monospace; }
        .icd10-chip-desc { color: var(--muted); max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .primary-badge { font-size: 0.65rem; background: var(--primary); color: white; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }
        .primary-btn { background: none; border: none; cursor: pointer; padding: 2px; color: var(--muted); }
        .primary-btn:hover { color: var(--primary); }
        .remove-btn { background: none; border: none; cursor: pointer; padding: 2px; color: var(--danger); font-weight: bold; }

        .plan-section { margin-bottom: 28px; padding-bottom: 24px; border-bottom: 1px solid var(--border); }
        .plan-section:last-of-type { border-bottom: none; }
        .followup-section { border-bottom: none; }
        .section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
        .section-header h4 { margin: 0; display: flex; align-items: center; gap: 8px; color: var(--text); }

        .medication-list, .investigation-list, .referral-list { display: flex; flex-direction: column; gap: 12px; }
        .medication-card, .investigation-card, .referral-card { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end; padding: 12px; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; }
        .med-row { display: flex; flex-wrap: wrap; gap: 8px; width: 100%; align-items: flex-end; }
        .med-name { flex: 1; min-width: 180px; }
        .med-dose { min-width: 100px; }
        .med-freq { min-width: 100px; }
        .med-dur { min-width: 120px; }
        .med-route { min-width: 100px; }
        .med-inst { width: 100%; margin-top: 8px; }
        .inv-name { flex: 1; min-width: 200px; }
        .inv-type { min-width: 120px; }
        .inv-priority { min-width: 100px; }
        .inv-notes { min-width: 200px; }
        .ref-spec { flex: 1; min-width: 180px; }
        .ref-reason { flex: 1; min-width: 200px; }
        .ref-urgency { min-width: 120px; }
        .ref-prov { min-width: 180px; }
        .btn-icon { padding: 8px; }
        .btn-icon svg { width: 16px; height: 16px; }

        .followup-fields { display: grid; grid-template-columns: 200px 1fr; gap: 16px; align-items: end; }
        .followup-fields .form-group { margin-bottom: 0; }

        .soap-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--border); flex-wrap: wrap; gap: 16px; }
        .footer-left { display: flex; gap: 12px; }
        .footer-right { display: flex; gap: 12px; }
        .btn-lg { padding: 14px 28px; font-size: 1rem; font-weight: 600; }
        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

        .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 24px; }
        .modal { background: var(--card); border-radius: 12px; padding: 24px; min-width: 400px; max-width: 500px; box-shadow: 0 20px 40px rgba(0,0,0,0.2); }
        .modal h3 { margin: 0 0 12px; display: flex; align-items: center; gap: 8px; color: var(--text); }
        .modal p { margin: 0 0 16px; color: var(--muted); line-height: 1.6; }
        .modal-checklist { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; padding: 16px; background: var(--bg); border-radius: 8px; }
        .modal-checklist label { display: flex; align-items: center; gap: 8px; font-size: 0.9375rem; color: var(--text); cursor: default; }
        .modal-actions { display: flex; justify-content: flex-end; gap: 12px; }

        .loading-container, .error-container { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 400px; text-align: center; }
        .loading-text { margin-top: 16px; color: var(--muted); }
        .error-container h2 { margin: 16px 0 8px; }
        .error-container p { color: var(--muted); max-width: 400px; }

        .badge { display: inline-flex; align-items: center; padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }
        .badge-primary { background: var(--primary-light); color: var(--primary); }
        .badge-secondary { background: var(--secondary-light); color: var(--secondary); }
        .badge-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
        .badge-success { background: rgba(34,197,94,0.1); color: var(--success); }
        .badge-warning { background: rgba(245,158,11,0.1); color: var(--warning); }
        .badge-danger { background: rgba(239,68,68,0.1); color: var(--danger); }

        @media (max-width: 768px) {
          .soap-editor-page { padding: 16px; }
          .soap-header { flex-direction: column; align-items: stretch; }
          .header-meta { justify-content: center; }
          .med-row, .medication-card, .investigation-card, .referral-card { flex-direction: column; align-items: stretch; }
          .med-name, .med-dose, .med-freq, .med-dur, .med-route, .inv-name, .inv-type, .inv-priority, .inv-notes, .ref-spec, .ref-reason, .ref-urgency, .ref-prov { min-width: 100%; width: 100%; }
          .followup-fields { grid-template-columns: 1fr; }
          .footer-left, .footer-right { width: 100%; }
          .footer-right button { flex: 1; }
        }
      `}</style>
    </div>
  );
};

export default SOAPEditor;