import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Heart,
  Droplet,
  Thermometer,
  Activity,
  Weight,
  Ruler,
  AlertTriangle,
  Save,
  Loader2,
  ArrowLeft,
  Stethoscope,
  X,
  CheckCircle,
} from 'lucide-react';
import { patientApi } from '../services/api';
import { vitalsApi } from '../services/api';

type VitalType = 
  | 'SYSTOLIC_BP'
  | 'DIASTOLIC_BP'
  | 'HEART_RATE'
  | 'RESPIRATORY_RATE'
  | 'TEMPERATURE'
  | 'SPO2'
  | 'RBS'
  | 'WEIGHT'
  | 'HEIGHT'
  | 'BMI';

interface VitalSignFormData {
  vital_type: VitalType;
  value: string;
  value_numeric?: number;
  unit?: string;
  recorded_at: string;
  device_name?: string;
  device_serial?: string;
  method?: string;
  position?: string;
  notes?: string;
  reference_range_low?: number;
  reference_range_high?: number;
  encounter_id?: string;
}

const VITAL_CONFIG: Record<VitalType, {
  label: string;
  icon: React.ReactNode;
  unit: string;
  placeholder: string;
  referenceRange: { low: number; high: number };
  inputType: 'bp' | 'number' | 'text';
  step?: number;
  min?: number;
  max?: number;
}> = {
  SYSTOLIC_BP: {
    label: 'Systolic BP',
    icon: <Heart className="w-5 h-5" />,
    unit: 'mmHg',
    placeholder: '120',
    referenceRange: { low: 90, high: 140 },
    inputType: 'number',
    min: 50,
    max: 250,
  },
  DIASTOLIC_BP: {
    label: 'Diastolic BP',
    icon: <Heart className="w-5 h-5" />,
    unit: 'mmHg',
    placeholder: '80',
    referenceRange: { low: 60, high: 90 },
    inputType: 'number',
    min: 30,
    max: 150,
  },
  HEART_RATE: {
    label: 'Heart Rate',
    icon: <Activity className="w-5 h-5" />,
    unit: '/min',
    placeholder: '72',
    referenceRange: { low: 60, high: 100 },
    inputType: 'number',
    min: 30,
    max: 200,
  },
  RESPIRATORY_RATE: {
    label: 'Respiratory Rate',
    icon: <Droplet className="w-5 h-5" />,
    unit: '/min',
    placeholder: '16',
    referenceRange: { low: 12, high: 20 },
    inputType: 'number',
    min: 5,
    max: 50,
  },
  TEMPERATURE: {
    label: 'Temperature',
    icon: <Thermometer className="w-5 h-5" />,
    unit: '°C',
    placeholder: '37.0',
    referenceRange: { low: 36.1, high: 37.5 },
    inputType: 'number',
    step: 0.1,
    min: 30,
    max: 43,
  },
  SPO2: {
    label: 'SpO₂',
    icon: <Droplet className="w-5 h-5" />,
    unit: '%',
    placeholder: '98',
    referenceRange: { low: 95, high: 100 },
    inputType: 'number',
    min: 70,
    max: 100,
  },
  RBS: {
    label: 'Random Blood Sugar',
    icon: <Droplet className="w-5 h-5" />,
    unit: 'mg/dL',
    placeholder: '100',
    referenceRange: { low: 70, high: 140 },
    inputType: 'number',
    min: 20,
    max: 500,
  },
  WEIGHT: {
    label: 'Weight',
    icon: <Weight className="w-5 h-5" />,
    unit: 'kg',
    placeholder: '70',
    referenceRange: { low: 40, high: 120 },
    inputType: 'number',
    step: 0.1,
    min: 1,
    max: 300,
  },
  HEIGHT: {
    label: 'Height',
    icon: <Ruler className="w-5 h-5" />,
    unit: 'cm',
    placeholder: '170',
    referenceRange: { low: 140, high: 200 },
    inputType: 'number',
    step: 0.1,
    min: 30,
    max: 250,
  },
  BMI: {
    label: 'BMI',
    icon: <Weight className="w-5 h-5" />,
    unit: 'kg/m²',
    placeholder: '24.2',
    referenceRange: { low: 18.5, high: 24.9 },
    inputType: 'number',
    step: 0.1,
    min: 10,
    max: 60,
  },
};

const VITAL_GROUPS = [
  {
    title: 'Blood Pressure',
    icon: <Heart className="w-5 h-5" />,
    vitals: ['SYSTOLIC_BP', 'DIASTOLIC_BP'] as VitalType[],
  },
  {
    title: 'Cardiopulmonary',
    icon: <Activity className="w-5 h-5" />,
    vitals: ['HEART_RATE', 'RESPIRATORY_RATE', 'SPO2'] as VitalType[],
  },
  {
    title: 'Metabolic',
    icon: <Droplet className="w-5 h-5" />,
    vitals: ['TEMPERATURE', 'RBS'] as VitalType[],
  },
  {
    title: 'Anthropometric',
    icon: <Ruler className="w-5 h-5" />,
    vitals: ['WEIGHT', 'HEIGHT', 'BMI'] as VitalType[],
  },
];

const getAbnormalStatus = (vitalType: VitalType, value: number | undefined): 'normal' | 'abnormal' | 'critical' => {
  if (value === undefined) return 'normal';
  const range = VITAL_CONFIG[vitalType].referenceRange;
  if (value < range.low * 0.7 || value > range.high * 1.3) return 'critical';
  if (value < range.low || value > range.high) return 'abnormal';
  return 'normal';
};

const VitalSignsEntry: React.FC = () => {
  const { patientId } = useParams<{ patientId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [formData, setFormData] = useState<Record<VitalType, VitalSignFormData>>(
    {} as Record<VitalType, VitalSignFormData>
  );
  const [expandedGroups, setExpandedGroups] = useState<string[]>(
    VITAL_GROUPS.map(g => g.title)
  );
  const [submitting, setSubmitting] = useState(false);
  const [submittedVitals, setSubmittedVitals] = useState<Set<VitalType>>(new Set());

  // Initialize form data
  useEffect(() => {
    const initial: Record<VitalType, VitalSignFormData> = {} as Record<VitalType, VitalSignFormData>;
    Object.keys(VITAL_CONFIG).forEach((key) => {
      const vt = key as VitalType;
      const config = VITAL_CONFIG[vt];
      initial[vt] = {
        vital_type: vt,
        value: '',
        value_numeric: undefined,
        unit: config.unit,
        recorded_at: new Date().toISOString(),
        method: 'Manual',
        position: 'sitting',
        reference_range_low: config.referenceRange.low,
        reference_range_high: config.referenceRange.high,
      };
    });
    setFormData(initial);
  }, []);

  // Fetch patient for display
  const { data: patient, isLoading: patientLoading } = useQuery({
    queryKey: ['patient', patientId],
    queryFn: () => patientApi.getById(patientId!),
    enabled: !!patientId,
  });

  // Submit mutation
  const submitMutation = useMutation({
    mutationFn: async (vital: VitalSignFormData) => {
      return vitalsApi.create(vital);
    },
    onSuccess: (_, vital) => {
      setSubmittedVitals(prev => new Set(prev).add(vital.vital_type));
      queryClient.invalidateQueries({ queryKey: ['vitals', patientId] });
      queryClient.invalidateQueries({ queryKey: ['patient-chart', patientId] });
    },
    onError: (error: any) => {
      alert(`Failed to save ${vital.vital_type}: ${error.message}`);
    },
  });

  const handleChange = (vitalType: VitalType, field: keyof VitalSignFormData, value: any) => {
    setFormData(prev => ({
      ...prev,
      [vitalType]: { ...prev[vitalType], [field]: value },
    }));

    // Auto-calculate numeric value from string
    if (field === 'value') {
      const num = parseFloat(value);
      if (!isNaN(num)) {
        setFormData(prev => ({
          ...prev,
          [vitalType]: { ...prev[vitalType], value_numeric: num },
        }));
      }
    }

    // Auto-calculate BMI when weight or height changes
    if ((vitalType === 'WEIGHT' || vitalType === 'HEIGHT') && field === 'value_numeric') {
      const weight = vitalType === 'WEIGHT' ? value : formData.WEIGHT?.value_numeric;
      const height = vitalType === 'HEIGHT' ? value : formData.HEIGHT?.value_numeric;
      if (weight && height) {
        const bmi = weight / Math.pow(height / 100, 2);
        setFormData(prev => ({
          ...prev,
          BMI: {
            ...prev.BMI,
            value: bmi.toFixed(1),
            value_numeric: bmi,
          },
        }));
      }
    }
  };

  const handleSubmit = async (vitalType: VitalType) => {
    const vital = formData[vitalType];
    if (!vital.value || vital.value.trim() === '') {
      alert('Please enter a value');
      return;
    }

    setSubmitting(true);
    try {
      await submitMutation.mutateAsync(vital);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitAll = async () => {
    const vitalsToSubmit = Object.values(formData).filter(v => v.value && v.value.trim() !== '');
    if (vitalsToSubmit.length === 0) {
      alert('Please enter at least one vital sign');
      return;
    }

    setSubmitting(true);
    try {
      await Promise.all(vitalsToSubmit.map(v => submitMutation.mutateAsync(v)));
      alert('All vital signs saved successfully!');
    } catch (error) {
      alert('Some vital signs failed to save');
    } finally {
      setSubmitting(false);
    }
  };

  const toggleGroup = (title: string) => {
    setExpandedGroups(prev => 
      prev.includes(title) 
        ? prev.filter(t => t !== title) 
        : [...prev, title]
    );
  };

  const isSubmitted = (vitalType: VitalType) => submittedVitals.has(vitalType);
  const getStatus = (vitalType: VitalType) => {
    const vital = formData[vitalType];
    if (!vital.value_numeric) return 'empty';
    if (isSubmitted(vitalType)) return 'saved';
    return getAbnormalStatus(vitalType, vital.value_numeric);
  };

  const StatusBadge = ({ vitalType }: { vitalType: VitalType }) => {
    const status = getStatus(vitalType);
    if (status === 'empty') return <span className="badge badge-neutral">—</span>;
    if (status === 'saved') return <CheckCircle className="w-4 h-4 text-success" title="Saved" />;
    if (status === 'critical') return <AlertTriangle className="w-4 h-4 text-danger" title="Critical" />;
    if (status === 'abnormal') return <AlertTriangle className="w-4 h-4 text-warning" title="Abnormal" />;
    return <CheckCircle className="w-4 h-4 text-success" title="Normal" />;
  };

  if (patientLoading) {
    return (
      <div className="loading-container">
        <div className="spinner" />
        <div className="loading-text">Loading patient...</div>
      </div>
    );
  }

  const patientName = patient 
    ? `${patient.firstName || ''} ${patient.lastName || ''}`.trim() || 'Unknown Patient'
    : 'Unknown Patient';

  return (
    <div className="vitals-entry-page">
      {/* Header */}
      <div className="page-header" style={{ marginBottom: 24 }}>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate(-1)}>
          <ArrowLeft size={16} /> Back to Chart
        </button>
        <div style={{ marginTop: 16 }}>
          <h1 style={{ margin: 0, fontSize: '1.5rem' }}>Vital Signs Entry</h1>
          <div style={{ display: 'flex', gap: 16, marginTop: 8, flexWrap: 'wrap', color: 'var(--muted)' }}>
            <span><strong>Patient:</strong> {patientName}</span>
            <span><strong>MRN:</strong> {patient?.mrn || '-'}</span>
            <span><strong>DOB:</strong> {patient?.demographics?.dateOfBirth || '-'}</span>
            <span><strong>Gender:</strong> {patient?.demographics?.gender || '-'}</span>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-title" style={{ marginBottom: 16 }}>
          <Stethoscope size={20} /> Quick Actions
        </div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button 
            className="btn btn-primary" 
            onClick={handleSubmitAll}
            disabled={submitting}
          >
            <Save size={16} /> Save All ({Object.values(formData).filter(v => v.value).length})
          </button>
          <button 
            className="btn btn-secondary" 
            onClick={() => navigate(`/patients/${patientId}`)}
          >
            <X size={16} /> Cancel
          </button>
        </div>
        <p className="text-sm text-muted" style={{ marginTop: 8 }}>
          Enter values and click <strong>Save All</strong> or save individual vitals using the save button next to each field.
          Abnormal values are highlighted: <span className="badge badge-warning">Abnormal</span> 
          <span className="badge badge-danger">Critical</span>
        </p>
      </div>

      {/* Vital Sign Groups */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {VITAL_GROUPS.map((group) => (
          <div key={group.title} className="card">
            <button
              className="card-title"
              style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: 8, 
                cursor: 'pointer',
                background: 'none',
                border: 'none',
                padding: 0,
                font: 'inherit',
                color: 'inherit',
                width: '100%',
                textAlign: 'left',
              }}
              onClick={() => toggleGroup(group.title)}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {group.icon}
                <span>{group.title}</span>
              </span>
              <span style={{ marginLeft: 'auto' }}>
                {expandedGroups.includes(group.title) ? '▼' : '▶'}
              </span>
            </button>

            {expandedGroups.includes(group.title) && (
              <div className="card-body" style={{ paddingTop: 0 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
                  {group.vitals.map((vitalType) => {
                    const config = VITAL_CONFIG[vitalType];
                    const vital = formData[vitalType];
                    const status = getStatus(vitalType);
                    const isSaved = isSubmitted(vitalType);

                    return (
                      <div 
                        key={vitalType} 
                        className={`vital-field ${status === 'critical' ? 'critical' : ''} ${status === 'abnormal' ? 'abnormal' : ''} ${isSaved ? 'saved' : ''}`}
                        style={{
                          border: status === 'critical' ? '2px solid var(--danger)' : 
                                status === 'abnormal' ? '2px solid var(--warning)' :
                                isSaved ? '2px solid var(--success)' : '1px solid var(--border)',
                          borderRadius: 12,
                          padding: 16,
                          background: status === 'critical' ? 'rgba(239, 68, 68, 0.05)' :
                                    status === 'abnormal' ? 'rgba(245, 158, 11, 0.05)' :
                                    isSaved ? 'rgba(34, 197, 94, 0.05)' : 'var(--card)',
                          transition: 'all 0.2s',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 12 }}>
                          <div style={{ 
                            display: 'flex', 
                            alignItems: 'center', 
                            justifyContent: 'center',
                            width: 40,
                            height: 40,
                            borderRadius: 8,
                            background: 'var(--primary-light)',
                            color: 'var(--primary)',
                          }}>
                            {config.icon}
                          </div>
                          <div style={{ flex: 1 }}>
                            <label className="form-label" style={{ marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
                              {config.label}
                              <StatusBadge vitalType={vitalType} />
                            </label>
                            <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
                              Reference: {config.referenceRange.low}–{config.referenceRange.high} {config.unit}
                            </div>
                          </div>
                        </div>

                        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
                          <input
                            type={config.inputType === 'bp' ? 'text' : 'number'}
                            className="form-input"
                            style={{ flex: 1 }}
                            placeholder={config.placeholder}
                            value={vital.value}
                            onChange={(e) => handleChange(vitalType, 'value', e.target.value)}
                            step={config.step}
                            min={config.min}
                            max={config.max}
                            disabled={isSaved}
                            autoFocus={!vital.value && !isSaved}
                          />
                          <span className="form-unit" style={{ color: 'var(--muted)', fontSize: '0.875rem' }}>
                            {config.unit}
                          </span>
                        </div>

                        <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                          <select
                            className="form-select"
                            style={{ width: 'auto' }}
                            value={vital.method || 'Manual'}
                            onChange={(e) => handleChange(vitalType, 'method', e.target.value)}
                            disabled={isSaved}
                          >
                            <option value="Manual">Manual</option>
                            <option value="Automated">Automated</option>
                            <option value="Calculated">Calculated</option>
                          </select>
                          <select
                            className="form-select"
                            style={{ width: 'auto' }}
                            value={vital.position || 'sitting'}
                            onChange={(e) => handleChange(vitalType, 'position', e.target.value)}
                            disabled={isSaved}
                          >
                            <option value="sitting">Sitting</option>
                            <option value="standing">Standing</option>
                            <option value="supine">Supine</option>
                          </select>
                          <button
                            className={`btn btn-sm ${isSaved ? 'btn-secondary' : 'btn-primary'}`}
                            onClick={() => handleSubmit(vitalType)}
                            disabled={!vital.value || isSaved || submitting}
                          >
                            {isSaved ? (
                              <>
                                <CheckCircle size={14} /> Saved
                              </>
                            ) : submitting ? (
                              <>
                                <Loader2 size={14} className="animate-spin" /> Saving...
                              </>
                            ) : (
                              <>
                                <Save size={14} /> Save
                              </>
                            )}
                          </button>
                        </div>

                        {/* Optional notes */}
                        <textarea
                          className="form-input"
                          style={{ marginTop: 12, minHeight: 60 }}
                          placeholder="Notes (optional)..."
                          value={vital.notes || ''}
                          onChange={(e) => handleChange(vitalType, 'notes', e.target.value)}
                          disabled={isSaved}
                          rows={2}
                        />
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default VitalSignsEntry;