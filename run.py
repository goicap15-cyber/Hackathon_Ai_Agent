# run.py
import subprocess
import time
import sys
import os

# Reconfigure stdout to use UTF-8 to prevent encoding errors on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def run_services():
    print("=" * 60)
    print("   BANK A CRM AI AGENT CO-PILOT - LAUNCHER")
    print("=" * 60)
    
    # Check if virtual environment / python interpreter is correct
    py_executable = sys.executable
    
    # 1. Start CRM API Service (Port 8001)
    print("\n[+] Starting Mock CRM Server on http://127.0.0.1:8001...")
    crm_process = subprocess.Popen(
        [py_executable, "-m", "uvicorn", "mock_crm.main:app", "--host", "127.0.0.1", "--port", "8001"]
    )
    
    # 2. Give the CRM server 2 seconds to bind and start
    time.sleep(2)
    
    # 3. Start Agent Backend Service (Exposed port for Cloud/Local compatibility)
    port = os.environ.get("PORT", "8000")
    print(f"[+] Starting Agent Backend & Web host on http://0.0.0.0:{port}...")
    agent_process = subprocess.Popen(
        [py_executable, "-m", "uvicorn", "agent_backend.main:app", "--host", "0.0.0.0", "--port", port]
    )
    
    print("\n" + "=" * 60)
    print("🚀 ALL DOCKING SYSTEMS OPERATIONAL!")
    print("👉 MOCK CRM Sandbox APIs:  http://127.0.0.1:8001/docs")
    print("👉 RM Chat Interface UI:   http://127.0.0.1:8000")
    print("=" * 60)
    print("\nPress Ctrl+C to terminate all services.\n")
    
    try:
        while True:
            crm_status = crm_process.poll()
            agent_status = agent_process.poll()
            
            if crm_status is not None:
                print(f"\n[-] CRM Mock Server terminated with code {crm_status}")
                break
            if agent_status is not None:
                print(f"\n[-] Agent Backend Server terminated with code {agent_status}")
                break
                
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[!] Shutting down services...")
    finally:
        # Terminate processes cleanly
        crm_process.terminate()
        agent_process.terminate()
        
        try:
            crm_process.wait(timeout=2)
            agent_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            crm_process.kill()
            agent_process.kill()
            
        print("[✓] All services stopped successfully. Goodbye!")

if __name__ == "__main__":
    # Ensure current directory is in PYTHONPATH so imports work correctly
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    run_services()
