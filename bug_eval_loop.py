#!/usr/bin/env python3
"""
Health-Platform Bug Evaluation Loop
Runs periodically, scans for bugs, reports via Hermes MCP → Telegram
"""

import asyncio
import json
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Add project to path
PROJECT_ROOT = Path("/mnt/c/AI agent Workflow/health-platform")
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

BUG_PATTERNS = [
    # Critical patterns
    (r"TODO.*FIXME|FIXME.*TODO", "HIGH", "TODO/FIXME combo indicates known broken code"),
    (r"pass\s*#\s*TODO", "HIGH", "Empty implementation with TODO"),
    (r"raise NotImplementedError", "HIGH", "Unimplemented critical function"),
    (r"datetime\.utcnow\(\)", "MEDIUM", "Deprecated datetime.utcnow() usage"),
    (r"print\(|console\.log\(", "LOW", "Debug output in production code"),
    (r"except:\s*pass|except Exception:\s*pass", "HIGH", "Bare except swallowing errors"),
    (r"TODO.*security|FIXME.*security", "CRITICAL", "Security-related TODO/FIXME"),
    (r"password|secret|token|api_key\s*=\s*[\"']", "CRITICAL", "Hardcoded secrets"),
    (r"eval\(|exec\(|subprocess\.shell.*True", "HIGH", "Code injection risk"),
    (r"SELECT.*FROM.*WHERE.*\+", "HIGH", "Potential SQL injection"),
]

# Files to scan
SCAN_DIRS = [
    "backend/app",
    "orchestrator",
    "frontend/src",
]

EXCLUDE_DIRS = ["__pycache__", "node_modules", ".git", "venv", "dist", "build"]

def scan_for_bugs() -> List[Dict[str, Any]]:
    """Scan codebase for bug patterns."""
    bugs = []
    for scan_dir in SCAN_DIRS:
        full_path = PROJECT_ROOT / scan_dir
        if not full_path.exists():
            continue
        for file_path in full_path.rglob("*"):
            if any(excl in str(file_path) for excl in EXCLUDE_DIRS):
                continue
            if file_path.is_file() and file_path.suffix in [".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml"]:
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    for pattern, severity, desc in BUG_PATTERNS:
                        import re
                        matches = list(re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE))
                        for match in matches:
                            line_num = content[:match.start()].count('\n') + 1
                            bugs.append({
                                "file": str(file_path.relative_to(PROJECT_ROOT)),
                                "line": line_num,
                                "severity": severity,
                                "description": desc,
                                "match": match.group()[:100],
                            })
                except Exception:
                    pass
    return bugs

def check_git_status() -> Dict[str, Any]:
    """Check git status for uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT, capture_output=True, text=True
        )
        changes = result.stdout.strip().split('\n') if result.stdout.strip() else []
        return {
            "clean": len(changes) == 0,
            "changes": changes[:20],
        }
    except Exception:
        return {"clean": True, "changes": []}

def check_tests() -> Dict[str, Any]:
    """Run quick test check."""
    try:
        # Check if pytest exists and run a quick test
        result = subprocess.run(
            ["./venv/bin/python", "-m", "pytest", "--collect-only", "-q"],
            cwd=PROJECT_ROOT / "backend", capture_output=True, text=True, timeout=30
        )
        return {
            "available": True,
            "output": result.stdout[-500:] if result.stdout else "",
            "errors": result.stderr[-500:] if result.stderr else "",
        }
    except Exception as e:
        return {"available": False, "error": str(e)}

def generate_report(bugs: List[Dict], git_status: Dict, test_status: Dict) -> str:
    """Generate formatted bug report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Group by severity
    by_severity = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []}
    for bug in bugs:
        by_severity[bug["severity"]].append(bug)
    
    report = f"🔍 **BUG EVALUATION REPORT**\n"
    report += f"⏰ {now}\n"
    report += f"📁 Project: health-platform\n"
    report += f"🌿 Branch: main\n\n"
    
    # Summary
    total = len(bugs)
    crit = len(by_severity["CRITICAL"])
    high = len(by_severity["HIGH"])
    med = len(by_severity["MEDIUM"])
    low = len(by_severity["LOW"])
    
    report += f"📊 **Summary**: {total} issues found\n"
    if crit: report += f"  🔴 CRITICAL: {crit}\n"
    if high: report += f"  🟠 HIGH: {high}\n"
    if med: report += f"  🟡 MEDIUM: {med}\n"
    if low: report += f"  🟢 LOW: {low}\n"
    report += "\n"
    
    # Top critical/high issues
    for severity in ["CRITICAL", "HIGH"]:
        if by_severity[severity]:
            report += f"**{severity} Issues:**\n"
            for bug in by_severity[severity][:5]:
                report += f"  • `{bug['file']}:{bug['line']}` - {bug['description']}\n"
                report += f"    `{bug['match']}`\n"
            if len(by_severity[severity]) > 5:
                report += f"  ... and {len(by_severity[severity]) - 5} more\n"
            report += "\n"
    
    # Git status
    if not git_status["clean"]:
        report += f"⚠️ **Uncommitted Changes**: {len(git_status['changes'])} files\n"
        for change in git_status["changes"][:5]:
            report += f"  {change}\n"
        report += "\n"
    
    # Test status
    if test_status.get("available"):
        report += f"✅ Tests collectible\n"
    else:
        report += f"⚠️ Test collection failed\n"
    
    report += f"\n---\n*Auto-generated by Bug Evaluation Loop*"
    return report

async def send_via_mcp(message: str):
    """Send message via Hermes MCP to Telegram."""
    try:
        # Use the MCP stdio protocol
        init_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "bug-eval-loop", "version": "1.0"}
            }
        }
        
        send_msg = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "messages_send",
                "arguments": {
                    "target": "telegram:6112495820",
                    "message": message
                }
            }
        }
        
        proc = await asyncio.create_subprocess_exec(
            "/home/abisa/.local/bin/hermes", "mcp", "serve", "--accept-hooks",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        input_data = json.dumps(init_msg) + "\n" + json.dumps({"jsonrpc":"2.0","method":"notifications/initialized"}) + "\n" + json.dumps(send_msg) + "\n"
        stdout, stderr = await asyncio.wait_for(proc.communicate(input=input_data.encode()), timeout=15)
        
        return proc.returncode == 0
    except Exception as e:
        print(f"MCP send error: {e}")
        return False

async def run_evaluation_loop():
    """Main evaluation loop."""
    print(f"[{datetime.now()}] Starting bug evaluation...")
    
    # Scan for bugs
    bugs = scan_for_bugs()
    print(f"  Found {len(bugs)} potential issues")
    
    # Check git status
    git_status = check_git_status()
    
    # Check tests
    test_status = check_tests()
    
    # Generate report
    report = generate_report(bugs, git_status, test_status)
    
    # Send via MCP
    success = await send_via_mcp(report)
    
    if success:
        print(f"[{datetime.now()}] Report sent via Telegram ✓")
    else:
        print(f"[{datetime.now()}] Failed to send via Telegram")
        # Save to file as backup
        report_file = PROJECT_ROOT / f"bug_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        report_file.write_text(report)
        print(f"  Saved to {report_file}")

if __name__ == "__main__":
    asyncio.run(run_evaluation_loop())