# === kairos.py (Updated to respect ollama_busy_event) ===
import multiprocessing
import time
import os
import random
import string
from datetime import datetime

from common_utils import (
    setup_logging, set_cpu_affinity,
    DATA_TYPE_KEY, DATA_CONTENT_KEY, DATA_PULSE_KEY,
    PULSE_PYTHON_SCRIPT, PULSE_SEO_CONTENT
)

# Setup logging for Kairos
logger = setup_logging("Kairos")

class Kairos:
    # MODIFIED: __init__ now accepts ollama_busy_event
    def __init__(self, kairos_to_aion_q, current_pulse_shared_value, ollama_busy_event):
        self.kairos_to_aion_q = kairos_to_aion_q
        self.running_event = None
        self.cpu_affinity = None
        self.current_pulse_shared_value = current_pulse_shared_value
        self.ollama_busy_event = ollama_busy_event # STORE: the new event
        logger.info("Initialized.")

    def run(self, cpu_affinity, running_event):
        self.cpu_affinity = cpu_affinity
        self.running_event = running_event
        set_cpu_affinity(os.getpid(), self.cpu_affinity, logger)
        logger.info(f"Starting on PID {os.getpid()} (assigned CPU {self.cpu_affinity}).")

        logger.info("Entering main generation loop.")
        while self.running_event.is_set():
            # NEW: Pause if Ollama is busy
            if not self.ollama_busy_event.is_set():
                logger.debug("Kairos: Ollama is busy, pausing raw data generation.")
                time.sleep(0.5) # Wait a bit and re-check
                continue # Skip to next iteration of while loop

            current_pulse = self.current_pulse_shared_value.value
            logger.info(f"Kairos: Current system pulse is '{current_pulse}'.")
            raw_data = self._generate_raw_data(5000) # Generate 5KB of raw data

            # Simulate different data types based on the current pulse
            data_type = ""
            if current_pulse == PULSE_PYTHON_SCRIPT:
                data_type = "python_script"
            elif current_pulse == PULSE_SEO_CONTENT:
                data_type = "seo_content"
            else:
                logger.warning(f"Unknown pulse type: {current_pulse}. Defaulting to python_script.")
                data_type = "python_script"

            data = {
                DATA_TYPE_KEY: data_type,
                DATA_CONTENT_KEY: raw_data,
                DATA_PULSE_KEY: current_pulse # Pass the current pulse down the pipeline
            }
            self.kairos_to_aion_q.put(data)
            logger.info(f"Generated raw data (length {len(raw_data)}). Pulse: {current_pulse}")

            time.sleep(1) # Simulate work

        logger.info("Shutting down.")

    def _generate_raw_data(self, size):
        """Generates a random string of specified size."""
        return ''.join(random.choices(string.ascii_letters + string.digits + string.punctuation + ' ', k=size))
