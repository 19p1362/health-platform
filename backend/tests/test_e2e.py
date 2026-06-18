"""HealthBridge Platform — E2E Integration Test"""
import requests
import sys
BASE = "http://localhost:8080"
pass_count = 0
fail_count = 0
skipped_count = 0

def test(name, method, url, **kwargs):
    global pass_count, fail_count, skipped_count
    try:
        r = requests.request(method, url, **kwargs, timeout=10)
        data = r.json() if r.text else {}
        if r.status_code == 409 and "already registered" in str(data.get("detail", "")):
            print(f"  ⏭️ {name} [{r.status_code}] — already exists")
            skipped_count += 1
            return data
        if r.ok:
            print(f"  ✅ {name} [{r.status_code}]")
            pass_count += 1
        else:
            print(f"  ❌ {name} [{r.status_code}]")
            print(f"     Error: {data.get('detail', r.text[:200])}")
            fail_count += 1
        return data
    except Exception as e:
        print(f"  ❌ {name} — Exception: {e}")
        fail_count += 1
        return {}

# ── 1. Register ──
print("\n=== REGISTER ===")
reg = test("Register user", "POST", f"{BASE}/api/v1/auth/register",
           json={"email": "admin@healthbridge.io", "password": "Admin2025!", "full_name": "Admin User"})

# ── 2. Login ──
print("\n=== LOGIN ===")
login = test("Login", "POST", f"{BASE}/api/v1/auth/login",
             json={"email": "admin@healthbridge.io", "password": "Admin2025!"})
token = login.get("access_token", "")
headers = {"Authorization": f"Bearer {token}"} if token else {}

# ── 3. Get /me ──
print("\n=== PROFILE ===")
me = test("Get /me", "GET", f"{BASE}/api/v1/auth/me", headers=headers)

# ── 4. Create Patient ──
print("\n=== PATIENTS ===")
patient = test("Create patient", "POST", f"{BASE}/api/v1/patients/create", headers=headers,
               json={"first_name": "Ravi", "last_name": "Sharma", "date_of_birth": "1985-06-15",
                     "gender": "MALE", "phone": "9876543210", "email": "ravi@example.com",
                     "city": "Hyderabad", "state": "Telangana"})
patient_id = patient.get("patient_id", "")

if patient_id:
    search = test("Search patients", "GET", f"{BASE}/api/v1/patients/search?first_name=Ravi", headers=headers)
    detail = test("Patient detail", "GET", f"{BASE}/api/v1/patients/{patient_id}", headers=headers)

# ── 5. FHIR ──
print("\n=== FHIR ===")
if patient_id:
    fhir = test("FHIR $everything", "GET", f"{BASE}/fhir/Patient/{patient_id}/$everything", headers=headers)

# ── 6. Consent ──
print("\n=== CONSENT ===")
if patient_id:
    consent = test("Grant consent", "POST", f"{BASE}/api/v1/consent/grant", headers=headers,
                   json={"patient_id": patient_id, "purpose": "TREATMENT",
                         "data_categories": ["DEMOGRAPHICS", "CLINICAL"], "duration_days": 365})

# ── 7. Admin ──
print("\n=== ADMIN ===")
stats = test("Admin stats", "GET", f"{BASE}/api/v1/admin/stats", headers=headers)

# ── 8. Compliance ──
print("\n=== COMPLIANCE ===")
report = test("Compliance report", "GET", f"{BASE}/api/v1/compliance/report", headers=headers)

# ── 9. Conversion ──
print("\n=== CONVERSION ===")
validate = test("FHIR Validation", "POST", f"{BASE}/api/v1/convert/validate",
                headers=headers,
                json={"content": '{"resourceType":"Bundle","type":"document","entry":[]}', "format": "FHIR_R4"})

# ── Summary ──
total = pass_count + fail_count + skipped_count
print(f"\n{'═══════════════════════════════════════'}")
print(f"  RESULTS: {pass_count} passed, {fail_count} failed, {skipped_count} skipped")
print(f"{'═══════════════════════════════════════'}")
if fail_count == 0:
    print("  ALL TESTS PASSED ✅")
else:
    print(f"  {fail_count} TEST(S) FAILED ❌")

sys.exit(fail_count)
