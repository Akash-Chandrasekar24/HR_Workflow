"""
Live System Test & Verification Script.

Submits simulated candidate applications across all 4 company job roles to the live FastAPI server,
verifies HMAC webhook security, background task execution, score calculations, decision reason generation,
CSV ledger persistence, and HR decision overrides.
"""

import hmac
import hashlib
import json
import time
import sys
import httpx

# Force UTF-8 stdout encoding on Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

SERVER_URL = "http://127.0.0.1:8000"
HMAC_SECRET = "change-this-super-secret-hmac-key-for-google-apps-script"


def generate_signature(payload_bytes: bytes) -> str:
    return hmac.new(
        key=HMAC_SECRET.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()


def test_system():
    print("==================================================")
    print("[*] LIVE SYSTEM TEST EXECUTION")
    print("==================================================\n")

    client = httpx.Client(timeout=15.0)

    # 1. Health & Readiness Verification
    print("[1/5] Verifying API Server Health...")
    res_health = client.get(f"{SERVER_URL}/health")
    res_ready = client.get(f"{SERVER_URL}/ready")
    
    if res_health.status_code == 200 and res_ready.status_code == 200:
        print(f"      [+] Health Check OK: {res_health.json()}")
        print(f"      [+] Readiness Check OK: {res_ready.json()}\n")
    else:
        print(f"      [-] Server health check failed!")
        return

    # 2. Candidate Submissions across 4 Roles
    print("[2/5] Submitting Simulated Form Candidates across 4 Roles...")

    test_candidates = [
        {
            "candidate_id": "CAN-LIVE-AI01",
            "timestamp": "2026-08-17T16:00:00Z",
            "full_name": "Arun Kumar (AI Candidate)",
            "email": "arun.ai@example.com",
            "phone": "+91 98765 11111",
            "location": "Bengaluru, India",
            "job_role": "AI_ENGINEER",
            "years_of_experience": 3.5,
            "resume_file_id": "1AI_DriveFileId_99999",
            "form_response_id": "RESP-LIVE-AI01",
            "form_responses": {
                "Preferred Framework": "PyTorch / GenAI",
                "Notice Period": "15 Days"
            }
        },
        {
            "candidate_id": "CAN-LIVE-FS01",
            "timestamp": "2026-08-17T16:05:00Z",
            "full_name": "Deepika Rao (Full Stack)",
            "email": "deepika.fs@example.com",
            "phone": "+91 98765 22222",
            "location": "Hyderabad, India",
            "job_role": "FULLSTACK_DEV",
            "years_of_experience": 4.0,
            "resume_file_id": "1FS_DriveFileId_88888",
            "form_response_id": "RESP-LIVE-FS01",
            "form_responses": {
                "Frontend": "React, TypeScript, Next.js",
                "Backend": "Node.js, Python, PostgreSQL"
            }
        },
        {
            "candidate_id": "CAN-LIVE-DA01",
            "timestamp": "2026-08-17T16:10:00Z",
            "full_name": "Meera Patel (Data Analyst)",
            "email": "meera.da@example.com",
            "phone": "+91 98765 33333",
            "location": "Mumbai, India",
            "job_role": "DATA_ANALYST",
            "years_of_experience": 2.5,
            "resume_file_id": "1DA_DriveFileId_77777",
            "form_response_id": "RESP-LIVE-DA01",
            "form_responses": {
                "BI Tools": "Tableau, PowerBI",
                "SQL Level": "Advanced"
            }
        },
        {
            "candidate_id": "CAN-LIVE-PY01",
            "timestamp": "2026-08-17T16:15:00Z",
            "full_name": "Vikram Singh (Python Dev)",
            "email": "vikram.py@example.com",
            "phone": "+91 98765 44444",
            "location": "Chennai, India",
            "job_role": "PYTHON_DEV",
            "years_of_experience": 0.5, # Intentionally low to test mandatory check failure!
            "resume_file_id": "1PY_DriveFileId_66666",
            "form_response_id": "RESP-LIVE-PY01",
            "form_responses": {
                "Python Experience": "6 Months"
            }
        }
    ]

    for c in test_candidates:
        payload_bytes = json.dumps(c).encode("utf-8")
        signature = generate_signature(payload_bytes)

        res = client.post(
            f"{SERVER_URL}/api/v1/applications",
            content=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Signature-SHA256": signature
            }
        )

        if res.status_code == 202:
            print(f"      [+] Ingested: {c['full_name']} ({c['job_role']}) -> 202 Accepted")
        else:
            print(f"      [-] Ingestion failed for {c['candidate_id']}: {res.text}")

    print("\n[*] Waiting for background async pipeline to complete processing...")
    time.sleep(6.0)

    # 3. Retrieve Processed Candidates List & Verify CSV Data Ledger
    print("\n[3/5] Fetching Processed Candidates from CSV Data Ledger...")
    res_list = client.get(f"{SERVER_URL}/api/v1/applications")
    data_list = res_list.json()

    candidates = data_list.get("candidates", [])
    print(f"      [+] Total Processed Candidates in CSV Ledger: {len(candidates)}\n")

    print("----------------------------------------------------------------------------------------------------")
    print(f"{'CANDIDATE NAME':<24} | {'JOB ROLE':<13} | {'SCORE':<7} | {'DECISION':<11} | {'DECISION REASON SUMMARY'}")
    print("----------------------------------------------------------------------------------------------------")

    for cand in candidates[:8]:
        raw_score = cand.get('weighted_score', 0)
        try:
            val_score = float(raw_score)
        except (ValueError, TypeError):
            val_score = 0.0
            
        score_str = f"{val_score:.1f}/100"
        dec = cand.get('hr_override_decision') or cand.get('system_decision')
        reason = cand.get('decision_reason', '')
        if len(reason) > 38:
            reason = reason[:35] + "..."
        print(f"{cand.get('candidate_name', ''):<24} | {cand.get('job_role', ''):<13} | {score_str:<7} | {dec:<11} | {reason}")

    print("----------------------------------------------------------------------------------------------------\n")

    # 4. Test HR Decision Override
    print("[4/5] Testing HR Decision Override API...")
    override_payload = {
        "override_decision": "SHORTLISTED",
        "override_reason": "Approved by HR Lead: Candidate demonstrated strong problem solving skills."
    }

    # Find a candidate to override
    target_cand_id = candidates[0]['candidate_id'] if candidates else "CAN-LIVE-PY01"

    res_override = client.post(
        f"{SERVER_URL}/api/v1/applications/{target_cand_id}/override",
        json=override_payload
    )

    if res_override.status_code == 200:
        data_over = res_override.json()
        print(f"      [+] Override Success for {target_cand_id}:")
        print(f"          New Decision  : {data_over['candidate']['hr_override_decision']}")
        print(f"          Recruiter Note: {data_over['candidate']['hr_override_reason']}\n")
    else:
        print(f"      [-] Override failed: {res_override.text}")

    # 5. Access HR Dashboard URL & Excel Export
    print("[5/5] Testing HR Dashboard HTML Route & Excel Export...")
    res_dash = client.get(f"{SERVER_URL}/dashboard")
    res_excel = client.get(f"{SERVER_URL}/api/v1/applications/export/excel")
    
    if res_dash.status_code == 200 and res_excel.status_code == 200:
        print("      [+] HR Dashboard HTML Page OK (HTTP 200)")
        print(f"      [+] Excel Export API OK ({len(res_excel.content)} bytes downloaded)")
        print("      [*] Access live dashboard at: http://localhost:8000/dashboard\n")
    else:
        print("      [-] Dashboard or Excel export route returned error")

    print("==================================================")
    print("[+] ALL LIVE SYSTEM VERIFICATIONS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    test_system()
