# run.py
import subprocess
import time
import sys
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging. INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("launcher")

# Reconfigure stdout to use UTF-8 to prevent encoding errors on Windows
if getattr(sys.stdout, "encoding", None) and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not reconfigure stdout to UTF-8: %s", exc)


def _start_service(py_executable, module, host, port, name):
    """Start a uvicorn service and return the Popen handle, or None on failure."""
    try:
        process = subprocess. Popen(
            [py_executable, "-m", "uvicorn", module, "--host", host, "--port", str(port)]
        )
        logger.info("[+] Started %s (PID %s) on http://%s:%s", name, process.pid, host, port)
        return process
    except FileNotFoundError:
        logger.error("[x] Python executable not found: %s", py_executable)
    except Exception as exc:
        logger.error("[x] Failed to start %s: %s", name, exc)
    return None


def _stop_process(process, name):
    """Terminate a process cleanly, killing it if it does not exit in time."""
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess. TimeoutExpired:
            logger.warning("[!] %s did not stop in time, killing it...", name)
            process.kill()
            process.wait(timeout=5)
    except Exception as exc:
        logger.error("[x] Error while stopping %s: %s", name, exc)


def run_services():
    print("=" * 60)
    print("   BANK A CRM AI AGENT CO-PILOT - LAUNCHER")
    print("=" * 60)

    py_executable = sys.executable

    # Resolve exposed port (Cloud/Local compatibility), with validation
    raw_port = os.environ.get("PORT", "8000")
    try:
        port = int(raw_port)
        if not (0 < port < 65536):
            raise ValueError(f"port out of range: {port}")
    except ValueError as exc:
        logger.warning("[!] Invalid PORT value '%s' (%s). Falling back to 8000.", raw_port, exc)
        port = 8000

    crm_process = None
    agent_process = None

    try:
        # 1. Start CRM API Service (Port 8001)
        print("\n[+] Starting Mock CRM Server on http://127.0.0.1:8001...")
        crm_process = _start_service(
            py_executable, "mock_crm.main:app", "127.0.0.1", 8001, "Mock CRM Server"
        )
        if crm_process is None:
            logger.error("[x] Aborting launch: Mock CRM Server failed to start.")
            return

        # 2. Give the CRM server a moment to bind and start
        time.sleep(2)
        if crm_process.poll() is not None:
            logger.error(
                "[x] Mock CRM Server exited during startup with code %s. Aborting.",
                crm_process.returncode,
            )
            return

        # 3. Start Agent Backend Service (exposed port)
        print(f"[+] Starting Agent Backend & Web host on http://0.0.0.0:{port}...")
        agent_process = _start_service(
            py_executable, "agent_backend.main:app", "0.0.0.0", port, "Agent Backend Server"
        )
        if agent_process is None:
            logger.error("[x] Aborting launch: Agent Backend Server failed to start.")
            return

        print("\n" + "=" * 60)
        print("🚀 ALL DOCKING SYSTEMS OPERATIONAL!")
        print("👉 MOCK CRM Sandbox APIs:  http://127.0.0.1:8001/docs")
        print(f"👉 RM Chat Interface UI:   http://127.0.0.1:{port}")
        print("=" * 60)
        print("\nPress Ctrl+C to terminate all services.\n")

        while True:
            crm_status = crm_process.poll()
            agent_status = agent_process.poll()

            if crm_status is not None:
                logger.warning("[-] CRM Mock Server terminated with code %s", crm_status)
                break
            if agent_status is not None:
                logger.warning("[-] Agent Backend Server terminated with code %s", agent_status)
                break

            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[!] Shutting down services...")
    except Exception as exc:
        logger.error("[x] Unexpected error: %s", exc)
    finally:
        # Terminate processes cleanly
        _stop_process(agent_process, "Agent Backend Server")
        _stop_process(crm_process, "Mock CRM Server")
        print("[✓] All services stopped successfully. Goodbye!")


if __name__ == "__main__":
    # Ensure current directory is in PYTHONPATH so imports work correctly
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    run_services()
