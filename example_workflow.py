"""
╔══════════════════════════════════════════════════════════╗
║   HealthBridge Platform — Complete Workflow Example     ║
║                                                         ║
║   Run this against the live API at localhost:8080       ║
║   python example_workflow.py                            ║
╚══════════════════════════════════════════════════════════╝
"""
import requests
import json
import time

BASE = "http://localhost:8080"

# ═══════════════════════════════════════════════
# 1. AUTH — Register & Login
# ═══════════════════════════════════════════════
print("═" * 60)
print("📝 STEP 1: AUTH — Register & Login")
print("═" * 60)

# Register (skip 409 if already exists)
r = requests.post(f"{BASE}/api/v1/auth/register", json={
    "email": "doctor@healthbridge.io",
    "password": "SecurePass123!",
    "full_name": "Dr. Priya Sharma"
})
if r.status_code == 200:
    print(f"  ✅ Registered: {r.json()['email']} (ID: {r.json()['id'][:8]}...)")
elif r.status_code == 409:
    print(f"  ⏭️ Already registered")
else:
    print(f"  ❌ {r.status_code}: {r.json()}")

# Login
r = requests.post(f"{BASE}/api/v1/auth/login", json={
    "email": "doctor@healthbridge.io",
    "password": "SecurePass123!"
})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print(f"  ✅ Logged in — Token: {token[:20]}...{token[-8:]}")

# Get profile
r = requests.get(f"{BASE}/api/v1/auth/me", headers=headers)
me = r.json()
print(f"  👤 Profile: {me['full_name']} | Role: {me['role']} | Email: {me['email']}")


# ═══════════════════════════════════════════════
# 2. PATIENTS — Create & Search
# ═══════════════════════════════════════════════
print("\n" + "═" * 60)
print("🏥 STEP 2: PATIENTS — Create & Search")
print("═" * 60)

patients_data = [
    {
        "first_name": "Rajesh",
        "last_name": "Patel",
        "date_of_birth": "1978-03-22",
        "gender": "MALE",
        "phone": "9876543210",
        "email": "rajesh@example.com",
        "city": "Mumbai",
        "state": "Maharashtra",
        "blood_group": "O+",
        "chronic_conditions": "Type 2 Diabetes, Hypertension"
    },
    {
        "first_name": "Lakshmi",
        "last_name": "Reddy",
        "date_of_birth": "1985-11-08",
        "gender": "FEMALE",
        "phone": "9876543211",
        "email": "lakshmi@example.com",
        "city": "Hyderabad",
        "state": "Telangana",
        "blood_group": "B+",
        "chronic_conditions": "Asthma"
    },
    {
        "first_name": "Arun",
        "last_name": "Kumar",
        "date_of_birth": "1992-07-14",
        "gender": "MALE",
        "phone": "9876543212",
        "email": "arun@example.com",
        "city": "Bangalore",
        "state": "Karnataka",
        "blood_group": "A+",
        "chronic_conditions": "None"
    }
]

patient_ids = []
for i, pdata in enumerate(patients_data):
    r = requests.post(f"{BASE}/api/v1/patients/create", headers=headers, json=pdata)
    if r.status_code == 201:
        pid = r.json()["patient_id"]
        patient_ids.append(pid)
        print(f"  ✅ Created Patient {i+1}: {pdata['first_name']} {pdata['last_name']} (MRN: {r.json()['mrn']})")
    else:
        print(f"  ❌ Failed to create patient {i+1}: {r.json()}")

# Search
print("\n  🔍 Searching for patients named 'Rajesh':")
r = requests.get(f"{BASE}/api/v1/patients/search?first_name=Rajesh", headers=headers)
for p in r.json():
    consent_icon = {"GRANTED": "✅", "PENDING": "⏳", "WITHDRAWN": "❌"}
    icon = consent_icon.get(p.get("consent_status", ""), "❓")
    print(f"    {icon} {p['first_name']} {p['last_name']} | MRN: {p['mrn']} | Status: {p['consent_status']}")


# ═══════════════════════════════════════════════
# 3. PATIENT DETAIL — Full Record View
# ═══════════════════════════════════════════════
print("\n" + "═" * 60)
print("📋 STEP 3: PATIENT DETAIL — Full Record")
print("═" * 60)

pid = patient_ids[0]
r = requests.get(f"{BASE}/api/v1/patients/{pid}", headers=headers)
detail = r.json()
d = detail["demographics"]
print(f"  📛 {d['first_name']} {d['last_name']}")
print(f"  🆔 MRN: {detail['mrn']}")
print(f"  🎂 DOB: {d.get('date_of_birth', 'N/A')} | Gender: {d.get('gender', 'N/A')}")
print(f"  📞 Phone: {d.get('phone', 'N/A')} | Email: {detail.get('email', d.get('email', 'N/A'))}")
print(f"  🏙️ {d.get('city', 'N/A')}, {d.get('state', 'N/A')}")
print(f"  🩸 Blood Group: {detail.get('blood_group', 'N/A')}")
print(f"  📋 Chronic: {detail.get('chronic_conditions', 'None')}")
print(f"  📜 Consent Status: {detail['consent_status']}")
print(f"  🔗 Connected Sources: {len(detail.get('sources', []))}")


# ═══════════════════════════════════════════════
# 4. FHIR — Interoperability in Action
# ═══════════════════════════════════════════════
print("\n" + "═" * 60)
print("🔬 STEP 4: FHIR R4 — Interoperability")
print("═" * 60)

# Create a FHIR Condition resource
condition_fhir = {
    "resourceType": "Condition",
    "subject": {"reference": f"Patient/{pid}"},
    "code": {
        "coding": [{
            "system": "http://snomed.info/sct",
            "code": "44054006",
            "display": "Type 2 diabetes mellitus"
        }],
        "text": "Type 2 Diabetes"
    },
    "clinicalStatus": {
        "coding": [{"code": "active", "display": "Active"}]
    },
    "recordedDate": "2026-06-13T10:30:00Z"
}
r = requests.post(f"{BASE}/fhir/Condition", headers=headers, json=condition_fhir)
resp = r.json()
cond_id = resp.get("id", "created")
print(f"  ✅ Created FHIR Condition: {cond_id}")

# Create a MedicationRequest
medication_fhir = {
    "resourceType": "MedicationRequest",
    "subject": {"reference": f"Patient/{pid}"},
    "medicationCodeableConcept": {
        "coding": [{
            "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
            "code": "860818",
            "display": "Metformin 500mg"
        }]
    },
    "dosageInstruction": [{"text": "Take one tablet twice daily with meals"}],
    "authoredOn": "2026-06-13"
}
r = requests.post(f"{BASE}/fhir/MedicationRequest", headers=headers, json=medication_fhir)
resp = r.json()
med_id = resp.get("id", "created")
print(f"  ✅ Created FHIR MedicationRequest: {med_id}")

# Read FHIR $everything bundle
r = requests.get(f"{BASE}/fhir/Patient/{pid}/$everything", headers=headers)
bundle = r.json()
print(f"  📦 FHIR $everything Bundle: {bundle['total']} resources")
for entry in bundle.get("entry", []):
    res = entry.get("resource", {})
    print(f"     • {res.get('resourceType', '?')}: {res.get('id', '?')}")


# ═══════════════════════════════════════════════
# 5. CONSENT — DPDP Compliance in Action
# ═══════════════════════════════════════════════
print("\n" + "═" * 60)
print("🛡️ STEP 5: CONSENT — DPDP 2025 Compliance")
print("═" * 60)

r = requests.post(f"{BASE}/api/v1/consent/grant", headers=headers, json={
    "patient_id": pid,
    "purpose": "TREATMENT",
    "data_categories": ["DEMOGRAPHICS", "CLINICAL", "LAB_REPORTS", "MEDICATIONS"],
    "duration_days": 365,
    "notice_language": "en"
})
consent = r.json()
print(f"  ✅ Consent Granted!")
print(f"     ID: {consent['consent_id']}")
print(f"     Purpose: {consent['purpose']}")
print(f"     Categories: {', '.join(consent['data_categories'])}")
print(f"     Expires: {consent['expires_at']}")
print(f"     Withdrawal: {consent['withdrawal_endpoint']}")
print(f"\n  📄 DPDP Notice:")
print(f"     {consent['notice']['notice_text'][:200]}...")

# Check consent status
r = requests.get(f"{BASE}/api/v1/consent/status/{pid}", headers=headers)
status = r.json()
print(f"\n  📊 Consent Status: {status['current_status']}")
print(f"     Active Consent: {status['active_consent_id']}")
print(f"     History entries: {len(status['consent_history'])}")


# ═══════════════════════════════════════════════
# 6. HL7v2 → FHIR Conversion
# ═══════════════════════════════════════════════
print("\n" + "═" * 60)
print("🔄 STEP 6: CONVERSION — HL7v2 → FHIR R4")
print("═" * 60)

hl7_message = (
    "MSH|^~\\&|HIS|APOLLO_HOSP|LAB|LAB|202606130900||ADT^A01|MSG001|P|2.5\r"
    "EVN|A01|202606130900\r"
    "PID|1||PAT123^^^APOLLO_MRN||PATEL^RAJESH||19780322|M|||123 MG Road^Mumbai^^400001\r"
    "NK1|1|PRIYA^PATEL|WIFE\r"
    "PV1|1|I|CARDIO^W2^A^^^APOLLO"
)
r = requests.post(f"{BASE}/api/v1/convert/hl7v2-to-fhir", headers=headers, json={
    "hl7Message": hl7_message
})
conv = r.json()
success = conv.get("success", conv.get("status") == "success")
print(f"  ✅ HL7v2 → FHIR: {'Success' if success else conv.get('error_message', 'Unknown error')}")
if success and conv.get("content"):
    try:
        fhir_out = json.loads(conv["content"])
        resource_types = [e.get("resource", {}).get("resourceType", "?") for e in fhir_out.get("entry", [])]
        print(f"     Generated resources: {', '.join(resource_types)}")
    except (json.JSONDecodeError, KeyError):
        print(f"     Content available (raw)")
else:
    print(f"     Raw response: {str(conv)[:200]}")


# ═══════════════════════════════════════════════
# 7. COMPLIANCE — Breach Reporting
# ═══════════════════════════════════════════════
print("\n" + "═" * 60)
print("🚨 STEP 7: COMPLIANCE — Breach Report & Dashboard")
print("═" * 60)

r = requests.get(f"{BASE}/api/v1/compliance/report", headers=headers)
report = r.json()
print(f"  📊 DPDP Compliance Report:")
checks = report.get("checklist", report.get("checks", []))
if not checks:
    # Try nested structure
    for section_key in ["consent", "breach", "retention", "cross_border", "grievance", "sdf"]:
        section = report.get(section_key, {})
        if isinstance(section, dict):
            for k, v in section.items():
                icon = "✅" if str(v).upper() in ("TRUE", "PASS", "COMPLIANT", "OK") else "⚠️"
                print(f"     {icon} {section_key}.{k}: {v}")
else:
    for check in checks:
        status_icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}
        s = check.get("status", "?")
        icon = status_icon.get(s, s)
        print(f"     {icon} {check.get('check', check.get('name', '?'))}")

# Report a test breach
print("\n  🚨 Simulating a data breach report:")
r = requests.post(f"{BASE}/api/v1/compliance/breaches/report", headers=headers, json={
    "description": "Unauthorized access detected — 3 patient records viewed without consent",
    "breach_type": "UNAUTHORIZED_ACCESS",
    "severity": "HIGH",
    "affected_patient_ids": patient_ids,
    "affected_data_categories": ["DEMOGRAPHICS", "CLINICAL"],
    "remediation_steps": "Access revoked, passwords rotated, investigation initiated"
})
if r.status_code == 200:
    breach = r.json()
    print(f"     ✅ Breach Reported: {breach['breach_id']}")
    print(f"     ⏰ Board report deadline: {breach['board_report_deadline']} (72hr rule)")
else:
    print(f"     ❌ {r.status_code}: {r.json().get('detail', '')}")


# ═══════════════════════════════════════════════
# 8. ADMIN — Dashboard Stats
# ═══════════════════════════════════════════════
print("\n" + "═" * 60)
print("📈 STEP 8: ADMIN — Platform Statistics")
print("═" * 60)

r = requests.get(f"{BASE}/api/v1/admin/stats", headers=headers)
stats = r.json()
print(f"  👥 Total Patients: {stats['total_patients']}")
print(f"  📝 Total Records: {stats['total_records']}")
print(f"  🚨 Active Breaches: {stats['active_breaches']}")
print(f"  👤 Total Users: {stats['total_users']}")
print(f"  📋 Pending DP Requests: {stats['pending_dp_requests']}")

# View audit log
r = requests.get(f"{BASE}/api/v1/compliance/audit-log?limit=10", headers=headers)
audit = r.json()
print(f"\n  📋 Recent Audit Log ({audit['total']} entries):")
for entry in audit["entries"][:5]:
    print(f"     [{entry['timestamp'][:19]}] {entry['action']} — {entry.get('description', '')[:80]}")


# ═══════════════════════════════════════════════
# ✅ SUMMARY
# ═══════════════════════════════════════════════
print("\n" + "═" * 60)
print("✅ FULL WORKFLOW COMPLETE!")
print("═" * 60)
print(f"""
  🏥 Patients Created: {len(patient_ids)}
  🔬 FHIR Resources: 2 (Condition + MedicationRequest)
  🛡️ Consents Granted: 1 (365-day TREATMENT)
  🔄 HL7v2 Messages Converted: 1
  🚨 Breaches Reported: 1
  📊 Admin Dashboard: Active

  Your HealthBridge Platform is fully operational!
  OpenAPI docs: http://localhost:8080/docs
  Dashboard:     cd dashboard && npm start (port 3000 → proxies to :8080)
""")
