import os
import logging
from datetime import datetime
import psutil

LETHE_STATUS_MESSAGE_KEY = "lethe_status"
LETHE_ERROR_MESSAGE_KEY = "lethe_error"

# --- Logging Configuration (Centralized) ---
def setup_logging(name):
    log_format = '[%(asctime)s] %(name)s: %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format, datefmt='%Y-%m-%dT%H:%M:%S')
    return logging.getLogger(name)

# --- CPU Affinity Setter ---
def set_cpu_affinity(pid, core_id, logger):
    try:
        p = psutil.Process(pid)
        p.cpu_affinity([core_id])
        logger.info(f"PID {pid}: Successfully set CPU affinity to core {core_id}.")
    except Exception as e:
        logger.error(f"PID {pid}: Failed to set CPU affinity to core {core_id}: {e}")

# --- Directory Management ---
def ensure_directories_exist(base_dir):
    script_dirs = {
        "active_scripts": os.path.join(base_dir, "generated_scripts", "active", "python_scripts"),
        "stable_scripts": os.path.join(base_dir, "generated_scripts", "active", "stable_python_scripts"),
        "active_seo_keywords": os.path.join(base_dir, "generated_scripts", "active", "seo_keywords"),
        "lethian_archive_unstable_python": os.path.join(base_dir, "generated_scripts", "lethian_archive", "unstable_python_scripts"),
        "lethian_archive_stable_python": os.path.join(base_dir, "generated_scripts", "lethian_archive", "stable_python_scripts"), # For archiving stable if needed, or simply keeping them in 'active/stable'
        "lethian_archive_unstable_seo": os.path.join(base_dir, "generated_scripts", "lethian_archive", "unstable_seo_keywords"),
        "lethian_archive_stable_seo": os.path.join(base_dir, "generated_scripts", "lethian_archive", "stable_seo_keywords") # For archiving stable if needed
    }
    for key, path in script_dirs.items():
        os.makedirs(path, exist_ok=True)
    return script_dirs

# --- Pulse Type Constants ---
PULSE_PYTHON_SCRIPT = "python_script"
PULSE_SEO_CONTENT = "seo_content"

# --- Data Tagging Keys ---
DATA_TYPE_KEY = "type"
DATA_CONTENT_KEY = "content"
DATA_PULSE_KEY = "pulse" # To indicate which pulse generated this data
DATA_STATUS_KEY = "status" # For Lethe to mark STABLE/UNSTABLE

# --- Ollama Configuration ---
OLLAMA_API_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL_NAME = "tinydolphin:latest"
OLLAMA_TIMEOUT = 90 # Extended timeout for LLM generation

# --- Python Script Testing Configuration ---
PYTHON_TEST_TIMEOUT = 10 # Seconds for script execution timeout
