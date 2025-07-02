import time
import argparse
import multiprocessing
import os
from datetime import datetime

# Import common utilities
from common_utils import (
    setup_logging, set_cpu_affinity, ensure_directories_exist,
    PULSE_PYTHON_SCRIPT, PULSE_SEO_CONTENT,
    DATA_TYPE_KEY, DATA_CONTENT_KEY, DATA_PULSE_KEY, DATA_STATUS_KEY
)

# Import your module classes
from kairos_module import Kairos
from aion_module import Aion
from kronos_module import Kronos
from apollo_module import Apollo
from mnemo_module import Mnemo
from lethe_module import Lethe

# --- Logging Setup ---
logger = setup_logging("Spiral Entropy System")

# --- Global Queues ---
# Data flow queues
kairos_to_aion_q = multiprocessing.Queue()
aion_to_kronos_q = multiprocessing.Queue()
kronos_to_apollo_q = multiprocessing.Queue()
apollo_to_mnemo_q = multiprocessing.Queue()
mnemo_to_lethe_q = multiprocessing.Queue()

# Log/Status queues (for internal system monitoring, not data flow)
kronos_log_q = multiprocessing.Queue() # Kronos logs to Mnemo
mnemo_log_q = multiprocessing.Queue() # Mnemo logs to Lethe/Main
lethe_status_q = multiprocessing.Queue() # Lethe signals status/pulse switch to Main

class SpiralEntropySystem:
    def __init__(self, duration_s=60):
        self.duration_s = duration_s
        self.current_pulse = PULSE_PYTHON_SCRIPT # Start with Python pulse
        self.running_event = multiprocessing.Event() # To signal modules to run/stop
        self.processes = []
        self.script_dirs = {} # To store paths for modules

        logger.info("Initializing modules and processes...")
        self._setup_queues()
        self._create_module_instances()
        self._create_process_objects()

    def _setup_queues(self):
        logger.info("Queues created.")
        # Ensure directories exist
        self.script_dirs = ensure_directories_exist(os.getcwd())
        logger.info(f"Ensured script directories exist: {self.script_dirs}")


    def _create_module_instances(self):
        # Pass the pulse type and shared resources to modules
        # Note: The `current_pulse` is dynamic, so modules will get a function to read it.
        # However, for __init__, we pass the initial state.
        self.kairos_instance = Kairos(kairos_to_aion_q)
        self.aion_instance = Aion(kairos_to_aion_q, aion_to_kronos_q)
        self.kronos_instance = Kronos(aion_to_kronos_q, kronos_to_apollo_q, kronos_log_q)
        self.apollo_instance = Apollo(kronos_to_apollo_q, apollo_to_mnemo_q)
        self.mnemo_instance = Mnemo(apollo_to_mnemo_q, mnemo_to_lethe_q, mnemo_log_q, kronos_log_q, self.script_dirs)
        self.lethe_instance = Lethe(mnemo_to_lethe_q, lethe_status_q, mnemo_log_q, self.script_dirs)

        logger.info("Module instances created.")

    def _create_process_objects(self):
        # Use lambda functions to pass the *current* state of self.current_pulse
        # This allows modules to query the latest pulse type.
        self.processes.append(multiprocessing.Process(
            target=self.kairos_instance.run, name="Kairos-Process",
            args=(1, self.running_event, lambda: self.current_pulse)
        ))
        self.processes.append(multiprocessing.Process(
            target=self.aion_instance.run, name="Aion-Process",
            args=(2, self.running_event, lambda: self.current_pulse)
        ))
        self.processes.append(multiprocessing.Process(
            target=self.kronos_instance.run, name="Kronos-Process",
            args=(3, self.running_event, lambda: self.current_pulse)
        ))
        self.processes.append(multiprocessing.Process(
            target=self.apollo_instance.run, name="Apollo-Process",
            args=(1, self.running_event) # Apollo's type handling is based on incoming data
        ))
        self.processes.append(multiprocessing.Process(
            target=self.mnemo_instance.run, name="Mnemo-Process",
            args=(2, self.running_event)
        ))
        self.processes.append(multiprocessing.Process(
            target=self.lethe_instance.run, name="Lethe-Process",
            args=(3, self.running_event)
        ))

        logger.info("Process objects created.")

    def run(self):
        start_time = time.time()

        for proc in self.processes:
            proc.start()
            # Set CPU affinity after process starts
            set_cpu_affinity(proc.pid, int(proc.name.split('-')[0].replace('Process', '')[-1]), logger) # Extract core ID from name
            logger.info(f"Started {proc.name} with PID {proc.pid}.")

        logger.info("All core processes are running.")
        logger.info(f"Entering main run loop for {self.duration_s}s.")

        self.running_event.set() # Signal all processes to begin their work loops

        while time.time() - start_time < self.duration_s:
            try:
                # Check for pulse switch signals from Lethe
                if not lethe_status_q.empty():
                    status_msg = lethe_status_q.get()
                    if status_msg == f"{PULSE_PYTHON_SCRIPT}_complete":
                        self.current_pulse = PULSE_SEO_CONTENT
                        logger.info(f"PULSE SWITCH: Switched to {PULSE_SEO_CONTENT} pulse.")
                    elif status_msg == f"{PULSE_SEO_CONTENT}_complete":
                        self.current_pulse = PULSE_PYTHON_SCRIPT
                        logger.info(f"PULSE SWITCH: Switched to {PULSE_PYTHON_SCRIPT} pulse.")
                    else:
                        logger.warning(f"Unknown status message from Lethe: {status_msg}")
            except Exception as e:
                logger.error(f"Error in main loop while checking Lethe status: {e}")

            time.sleep(0.1) # Small sleep to prevent busy-waiting, adjust as needed

        self._shutdown_system()

    def _shutdown_system(self):
        logger.info("Spiral Entropy System: Shutting down processes...")
        self.running_event.clear() # Signal all modules to gracefully exit their loops

        for proc in self.processes:
            proc.join(timeout=5) # Give processes time to clean up
            if proc.is_alive():
                logger.warning(f"Process {proc.name} (PID {proc.pid}) did not terminate gracefully. Terminating.")
                proc.terminate()

        logger.info("Spiral Entropy System: All processes terminated.")

# --- Main Execution Block ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Spiral Entropy System.")
    parser.add_argument('--duration', type=int, default=60,
                        help='Duration in seconds for the system to run.')
    args = parser.parse_args()

    if args.duration != 60:
        logger.info(f"Spiral Entropy System: Using specified duration {args.duration}s.")
    else:
        logger.info("Spiral Entropy System: No duration argument provided. Using default 60s.")

    system = SpiralEntropySystem(duration_s=args.duration)
    system.run()
