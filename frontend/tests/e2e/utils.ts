/**
 * HealthBridge Platform - E2E Test Utilities
 */

import { Page, BrowserContext, APIRequestContext } from '@playwright/test';

export const TEST_USERS = {
  admin: { email: 'admin@healthbridge.io', password: 'Admin2025!' },
  doctor1: { email: 'doctor1@healthbridge.io', password: 'Doctor2025!' },
  doctor2: { email: 'doctor2@healthbridge.io', password: 'Doctor2025!' },
  doctor3: { email: 'doctor3@healthbridge.io', password: 'Doctor2025!' },
  nurse: { email: 'nurse@healthbridge.io', password: 'Nurse2025!' },
  frontDesk: { email: 'frontdesk@healthbridge.io', password: 'FrontDesk2025!' },
};

export const BASE_URL = process.env.BASE_URL || 'http://localhost:3001';
export const API_BASE = process.env.API_BASE || 'http://localhost:8080';

export async function login(page: Page, user = TEST_USERS.admin) {
  await page.goto(`${BASE_URL}/login`);
  await page.fill('input[type="email"]', user.email);
  await page.fill('input[type="password"]', user.password);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/dashboard/);
  await page.waitForLoadState('networkidle');
}

export async function getAuthToken(request: APIRequestContext, user = TEST_USERS.admin): Promise<string> {
  const response = await request.post(`${API_BASE}/api/v1/auth/login`, {
    data: { email: user.email, password: user.password },
  });
  const data = await response.json();
  return data.access_token;
}

export interface PatientRegistration {
  patientId: string;
  encounterId: string;
  tokenId: string;
  uhid: string;
  tokenNumber: number;
}

export async function registerPatientViaAPI(
  request: APIRequestContext,
  token: string,
  patientData: {
    first_name: string;
    last_name: string;
    age?: number;
    gender?: string;
    phone?: string;
    address?: string;
    emergency_contact_name?: string;
    emergency_contact_phone?: string;
    chief_complaint?: string;
    existing_patient_id?: string;
  }
): Promise<PatientRegistration> {
  const response = await request.post(`${API_BASE}/api/v1/opd/register`, {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    data: patientData,
  });
  const data = await response.json();
  return {
    patientId: data.patient_id || data.registration_id,
    encounterId: data.registration_id,
    tokenId: data.token_id || data.registration_id,
    uhid: data.uhid,
    tokenNumber: data.token_number,
  };
}

export async function createVitalsViaAPI(
  request: APIRequestContext,
  token: string,
  patientId: string,
  encounterId: string,
  vitals: Array<{
    vital_type: string;
    value: string;
    value_numeric: number;
    unit: string;
  }>
) {
  for (const vital of vitals) {
    await request.post(`${API_BASE}/api/v1/vitals`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: {
        patient_id: patientId,
        encounter_id: encounterId,
        ...vital,
        recorded_at: new Date().toISOString(),
        method: 'Manual',
        position: 'sitting',
      },
    });
  }
}

export async function finalizeSOAPViaAPI(
  request: APIRequestContext,
  token: string,
  encounterId: string
) {
  const response = await request.post(
    `${API_BASE}/api/v1/clinical/soap/${encounterId}/finalize`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  return response.json();
}

export async function getQueueStatus(
  request: APIRequestContext,
  token: string
) {
  const response = await request.get(`${API_BASE}/api/v1/opd/queue`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return response.json();
}

export async function waitForQueueUpdate(
  page: Page,
  selector: string,
  timeout = 2000
) {
  const startTime = Date.now();
  await page.waitForSelector(selector, { timeout });
  return Date.now() - startTime;
}

export async function takeScreenshot(page: Page, name: string) {
  const fs = require('fs');
  const path = `/home/abisa/health-platform/frontend/test-results/${name}.png`;
  await page.screenshot({ path, fullPage: true });
  return path;
}

export async function measurePageLoad(page: Page, url: string): Promise<number> {
  const start = Date.now();
  await page.goto(url);
  await page.waitForLoadState('networkidle');
  return Date.now() - start;
}

export function expectWithinLimit(actual: number, limit: number, operation: string) {
  console.log(`${operation}: ${actual}ms (limit: ${limit}ms)`);
  if (actual > limit) {
    throw new Error(`${operation} took ${actual}ms, exceeds limit of ${limit}ms`);
  }
}

// Performance thresholds
export const PERFORMANCE_THRESHOLDS = {
  registration: 60000,      // 60 seconds
  vitalsEntry: 90000,       // 90 seconds
  soapCompletion: 300000,   // 5 minutes (new), 180000 for follow-up
  queueLatency: 500,        // 500ms
  pageTransition: 1000,     // 1 second
};

// Test data generators
export function generateTestPatient(overrides = {}) {
  const timestamp = Date.now();
  return {
    first_name: 'Test',
    last_name: `Patient${timestamp}`,
    age: 30,
    gender: 'MALE',
    phone: `98765${timestamp.toString().slice(-5)}`,
    address: '123 Test Street',
    emergency_contact_name: 'Emergency Contact',
    emergency_contact_phone: `98765${(timestamp + 1).toString().slice(-5)}`,
    chief_complaint: 'Test visit',
    ...overrides,
  };
}

export const VITALS_TEMPLATE = [
  { vital_type: 'SYSTOLIC_BP', value: '120', value_numeric: 120, unit: 'mmHg' },
  { vital_type: 'DIASTOLIC_BP', value: '80', value_numeric: 80, unit: 'mmHg' },
  { vital_type: 'HEART_RATE', value: '72', value_numeric: 72, unit: '/min' },
  { vital_type: 'RESPIRATORY_RATE', value: '16', value_numeric: 16, unit: '/min' },
  { vital_type: 'TEMPERATURE', value: '36.8', value_numeric: 36.8, unit: '°C' },
  { vital_type: 'SPO2', value: '98', value_numeric: 98, unit: '%' },
  { vital_type: 'RBS', value: '100', value_numeric: 100, unit: 'mg/dL' },
  { vital_type: 'WEIGHT', value: '70', value_numeric: 70, unit: 'kg' },
  { vital_type: 'HEIGHT', value: '170', value_numeric: 170, unit: 'cm' },
];

export const SOAP_TEMPLATE = {
  subjective: 'Patient reports feeling well. No new complaints.',
  objective: 'Vitals stable. BP 120/80, HR 72, SpO2 98%, Temp 36.8°C.',
  assessment: 'Stable on current treatment.',
  plan: 'Continue current medications. Follow-up in 2 weeks.',
  chief_complaint: 'Routine follow-up',
  icd10_codes: [
    { code: 'I10', description: 'Essential (primary) hypertension', primary: true },
  ],
  medications: [
    { name: 'Amlodipine', dose: '5mg', frequency: 'OD', duration: '30 days', route: 'Oral' },
  ],
  investigations: [],
  referrals: [],
  follow_up_date: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
  follow_up_notes: 'Routine follow-up',
};

import { expect } from '@playwright/test';

// UI-based registration helper
export interface RegistrationResult {
  uhid: string;
  tokenNumber: number;
  patientId: string;
  encounterId: string;
  tokenId: string;
  registrationTime: number;
}

export async function registerPatient(page: Page, patientData: any): Promise<RegistrationResult> {
  const startTime = Date.now();
  await page.goto(`${BASE_URL}/opd/register`);
  await page.waitForLoadState('networkidle');

  // Search for existing patient first
  await page.fill('input[placeholder="Phone Number"]', patientData.phone);
  await page.click('button:has-text("Search")');
  await page.waitForTimeout(500);

  // If new patient, fill form
  const newPatientForm = page.locator('form.registration-form');
  if (await newPatientForm.isVisible({ timeout: 1000 }).catch(() => false)) {
    await page.fill('input[placeholder="First Name"]', patientData.first_name || patientData.firstName);
    await page.fill('input[placeholder="Last Name"]', patientData.last_name || patientData.lastName);
    await page.fill('input[placeholder="Age"]', String(patientData.age || ''));
    await page.selectOption('select[name="gender"]', patientData.gender || 'MALE');
    await page.fill('input[placeholder="Phone"]', patientData.phone);
    await page.fill('textarea[placeholder="Address"]', patientData.address || '');
    await page.fill('input[placeholder="Emergency Contact Name"]', patientData.emergency_contact_name || '');
    await page.fill('input[placeholder="Emergency Contact Phone"]', patientData.emergency_contact_phone || '');
    await page.fill('textarea[placeholder="Reason for visit..."]', patientData.chief_complaint || patientData.chiefComplaint || '');
    await page.click('button:has-text("Register & Generate Token")');
    await page.waitForLoadState('networkidle');
  }

  // Wait for token slip to appear
  await expect(page.locator('.token-slip, .registration-success')).toBeVisible({ timeout: 10000 });
  
  const registrationTime = Date.now() - startTime;
  console.log(`Registration took ${registrationTime}ms`);

  // Extract UHID and token number
  const uhid = await page.locator('.token-value:has-text("UHID")').textContent().catch(() => '');
  const tokenText = await page.locator('.token-large, .token-value.token-number').textContent().catch(() => '');
  
  // Extract IDs from URL or page data
  const url = page.url();
  const patientIdMatch = url.match(/patients\/([^/]+)/);
  const patientId = patientIdMatch ? patientIdMatch[1] : '';
  
  return { 
    uhid: uhid?.replace('UHID: ', '').trim() || '',
    tokenNumber: parseInt(tokenText?.replace(/\D/g, '') || '0', 10),
    patientId,
    encounterId: patientId,
    tokenId: patientId,
    registrationTime 
  };
}

// UI-based vitals entry helper
export async function enterVitals(page: Page, patientId: string, vitals: Record<string, string>) {
  const startTime = Date.now();
  await page.goto(`${BASE_URL}/patients/${patientId}/vitals`);
  await page.waitForLoadState('networkidle');
  await page.waitForSelector('input[placeholder="120"], input[data-vital="SYSTOLIC_BP"]', { timeout: 15000 });
  
  for (const [key, value] of Object.entries(vitals)) {
    const input = page.locator(`input[data-vital="${key}"], input[placeholder="${value}"]`).first();
    if (await input.isVisible({ timeout: 1000 }).catch(() => false)) {
      await input.fill(value);
    } else {
      const label = key.replace(/_/g, ' ');
      const field = page.locator(`label:has-text("${label}")`).locator('..').locator('input').first();
      if (await field.isVisible({ timeout: 1000 }).catch(() => false)) {
        await field.fill(value);
      }
    }
  }
  
  await page.click('button:has-text("Save All")');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=All vital signs saved, text=Successfully saved')).toBeVisible({ timeout: 10000 });
  
  const vitalsTime = Date.now() - startTime;
  console.log(`Vitals entry took ${vitalsTime}ms`);
  return vitalsTime;
}

// UI-based SOAP completion helper
export async function completeSOAP(page: Page, patientId: string, tokenId: string, encounterId: string, soapData: any) {
  const startTime = Date.now();
  await page.goto(`${BASE_URL}/patients/${patientId}/soap?token=${tokenId}&encounter=${encounterId}`);
  await page.waitForLoadState('networkidle');
  await page.waitForSelector('[role="tab"]:has-text("Subjective"), button:has-text("Subjective")', { timeout: 15000 });
  
  // Verify vitals auto-populated in Objective tab
  await page.click('[role="tab"]:has-text("Objective"), button:has-text("Objective")');
  await page.waitForTimeout(500);
  
  const objectiveContent = await page.locator('[data-tab="objective"], .objective-tab, .tab-panel:has-text("Objective")').textContent();
  
  // Fill SOAP sections
  await page.click('[role="tab"]:has-text("Subjective"), button:has-text("Subjective")');
  await page.fill('textarea[name="subjective"], [data-field="subjective"]', soapData.subjective);
  
  await page.click('[role="tab"]:has-text("Assessment"), button:has-text("Assessment")');
  await page.fill('textarea[name="assessment"], [data-field="assessment"]', soapData.assessment);
  
  // Add ICD-10 codes
  for (const icd of soapData.icd10_codes) {
    await page.fill('input[placeholder*="ICD"], input[placeholder*="Search diagnosis"]', icd.code);
    await page.waitForTimeout(300);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(300);
  }
  
  await page.click('[role="tab"]:has-text("Plan"), button:has-text("Plan")');
  await page.fill('textarea[name="plan"], [data-field="plan"]', soapData.plan);
  
  // Add medications
  for (const med of soapData.medications) {
    await page.click('button:has-text("Add Medication")');
    await page.fill('input[name="medicationName"]', med.name);
    await page.fill('input[name="dose"]', med.dose);
    await page.fill('input[name="frequency"]', med.frequency);
    await page.fill('input[name="duration"]', med.duration);
    await page.click('button:has-text("Save")');
  }
  
  // Set follow-up
  await page.fill('input[name="followUpDate"], input[type="date"]', soapData.followUpDate);
  await page.fill('textarea[name="followUpNotes"]', soapData.followUpNotes);
  
  // Finalize visit
  await page.click('button:has-text("Finalize Visit"), button:has-text("Complete Visit")');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Visit completed, text=Successfully finalized, text=Follow-up created')).toBeVisible({ timeout: 20000 });
  
  const soapTime = Date.now() - startTime;
  console.log(`SOAP completion took ${soapTime}ms`);
  return soapTime;
}

// Queue verification helper
export async function verifyQueueAdvance(page: Page, expectedNextToken: number) {
  await page.goto(`${BASE_URL}/doctor-queue`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);
  
  const currentToken = await page.locator('.current-token, .summary-value:has-text("Current")').textContent().catch(() => '');
  expect(parseInt(currentToken?.replace(/\D/g, '') || '0', 10)).toBe(expectedNextToken);
}

// Follow-up verification helper
export async function verifyFollowUpToken(page: Page, patientPhone: string) {
  await page.goto(`${BASE_URL}/opd/register`);
  await page.fill('input[placeholder="Phone Number"]', patientPhone);
  await page.click('button:has-text("Search")');
  await page.waitForLoadState('networkidle');
  
  const results = page.locator('.result-item, .search-results .patient');
  await expect(results.first()).toBeVisible({ timeout: 5000 });
  
  await results.first().click();
  await page.click('button:has-text("Register & Generate Token")');
  await page.waitForLoadState('networkidle');
  
  await expect(page.locator('.token-slip, .registration-success')).toBeVisible({ timeout: 5000 });
}

// Previous SOAP verification helper
export async function verifyPreviousSOAPVisible(page: Page, patientId: string) {
  await page.goto(`${BASE_URL}/patients/${patientId}`);
  await page.waitForLoadState('networkidle');
  
  await page.click('button:has-text("Clinical History"), [role="tab"]:has-text("History")');
  await page.waitForTimeout(500);
  
  const historyContent = await page.locator('.clinical-history, .patient-chart, .history-tab').textContent();
  expect(historyContent).toContain('Hypertension');
  expect(historyContent).toContain('Amlodipine');
  expect(historyContent).toContain('Metformin');
}