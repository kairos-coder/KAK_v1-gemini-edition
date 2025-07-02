import multiprocessing
import time
import os
import subprocess
from datetime import datetime

from common_utils import (
    setup_logging, set_cpu_affinity,
    DATA_TYPE_KEY, DATA_CONTENT_KEY, DATA_PULSE_KEY, DATA_STATUS_KEY,
    PULSE_PYTHON_SCRIPT, PULSE_SEO_CONTENT,
    LETHE_STATUS_MESSAGE_KEY, LETHE_ERROR_MESSAGE_KEY
)

# Setup logging for Lethe
logger = setup_logging("Lethe")

class Lethe:
    # MODIFIED: __init__ now accepts current_pulse_shared_value and mnemo_log_q
    def __init__(self, mnemo_to_lethe_q, lethe_to_apollo_feedback_q, current_pulse_shared_value, script_dirs, mnemo_log_q):
        self.mnemo_to_lethe_q = mnemo_to_lethe_q
        self.lethe_to_apollo_feedback_q = lethe_to_apollo_feedback_q # This is the queue for feedback to Apollo
        self.current_pulse_shared_value = current_pulse_shared_value # STORE: shared value for pulse switching
        self.script_dirs = script_dirs
        self.mnemo_log_q = mnemo_log_q # This queue will also carry feedback for Apollo
        self.running_event = None # Will be set in run method
        self.cpu_affinity = None # Will be set in run method
        logger.info("Initialized.")

    def run(self, cpu_affinity, running_event):
        self.cpu_affinity = cpu_affinity
        self.running_event = running_event
        set_cpu_affinity(os.getpid(), self.cpu_affinity, logger)
        logger.info(f"Starting on PID {os.getpid()} (assigned CPU {self.cpu_affinity}).")

        while self.running_event.is_set():
            if not self.mnemo_to_lethe_q.empty():
                data = self.mnemo_to_lethe_q.get()
                logger.info(f"Received data for testing/archiving: {data.get(DATA_TYPE_KEY)}")

                data_type = data.get(DATA_TYPE_KEY)
                file_path = data.get(DATA_CONTENT_KEY) # This is now the full path
                original_pulse = data.get(DATA_PULSE_KEY)
                file_name = os.path.basename(file_path)

                status = "UNKNOWN"
                error_message = "N/A"

                try:
                    if data_type == "python_script":
                        status, error_message = self._test_python_script(file_path)
                    elif data_type == "seo_content":
                        status, error_message = self._validate_seo_content(file_path)
                    else:
                        logger.warning(f"Unknown data type received for testing: {data_type}")
                        status = "UNSTABLE"
                        error_message = f"Unknown data type: {data_type}"

                except Exception as e:
                    logger.error(f"Error during testing of {data_type} {file_path}: {e}")
                    status = "UNSTABLE"
                    error_message = f"Exception during test: {e}"

                # Update the data with status for archiving
                data[DATA_STATUS_KEY] = status

                # Send feedback to Mnemo (which will then route to Apollo)
                feedback_message = {
                    "source": "Lethe",
                    DATA_TYPE_KEY: data_type,
                    LETHE_STATUS_MESSAGE_KEY: status,
                    LETHE_ERROR_MESSAGE_KEY: error_message,
                    "timestamp": datetime.now().isoformat()
                }
                # Use mnemo_log_q to send feedback to Mnemo.
                # Mnemo will need to distinguish this from regular log messages.
                self.mnemo_log_q.put(feedback_message)
                logger.debug(f"Sent feedback to Mnemo: Status={status}, Error='{error_message}'")


                self._archive_content(data, file_name, original_pulse)

                # Signal main system if this pulse type is complete (for pulse switching)
                # MODIFIED: Access shared value directly
                if status == "STABLE": # Only switch pulse if current pulse generation is stable
                    # Switch pulse to the other type
                    if self.current_pulse_shared_value.value == PULSE_PYTHON_SCRIPT:
                        self.current_pulse_shared_value.value = PULSE_SEO_CONTENT
                        logger.info(f"Successfully processed {original_pulse} data. Switching pulse to {PULSE_SEO_CONTENT}.")
                    elif self.current_pulse_shared_value.value == PULSE_SEO_CONTENT:
                        self.current_pulse_shared_value.value = PULSE_PYTHON_SCRIPT
                        logger.info(f"Successfully processed {original_pulse} data. Switching pulse to {PULSE_PYTHON_SCRIPT}.")
                    else:
                        logger.warning(f"Unexpected pulse value '{self.current_pulse_shared_value.value}'. Not switching pulse.")

                elif status == "UNSTABLE":
                    # For now, an unstable output still signals a pulse switch,
                    # so we don't get stuck in a bad generation loop.
                    # This behavior can be refined later.
                    # Switch pulse to the other type
                    if self.current_pulse_shared_value.value == PULSE_PYTHON_SCRIPT:
                        self.current_pulse_shared_value.value = PULSE_SEO_CONTENT
                        logger.warning(f"UNSTABLE {original_pulse} detected. Switching pulse to {PULSE_SEO_CONTENT} to continue.")
                    elif self.current_pulse_shared_value.value == PULSE_SEO_CONTENT:
                        self.current_pulse_shared_value.value = PULSE_PYTHON_SCRIPT
                        logger.warning(f"UNSTABLE {original_pulse} detected. Switching pulse to {PULSE_PYTHON_SCRIPT} to continue.")
                    else:
                        logger.warning(f"Unexpected pulse value '{self.current_pulse_shared_value.value}'. Not switching pulse.")

            else:
                time.sleep(0.1)
        logger.info("Shutting down.")

    def _test_python_script(self, file_path):
        logger.info(f"Testing Python script: {file_path}")
        try:
            # Use subprocess to run the script and capture its output and errors
            # We add a timeout to prevent indefinitely running scripts
            result = subprocess.run(
                ['python3', file_path],
                capture_output=True,
                text=True,
                timeout=10, # Timeout after 10 seconds
                check=False # Do not raise CalledProcessError for non-zero exit codes
            )

            if result.returncode == 0:
                logger.info(f"Python script {file_path} executed successfully.")
                # You might want to analyze stdout for expected output here too
                return "STABLE", "N/A"
            else:
                error_msg = result.stderr.strip() if result.stderr else "No specific error output."
                logger.warning(f"Python script {file_path} exited with non-zero code {result.returncode}. Error: {error_msg}")
                return "UNSTABLE", error_msg
        except subprocess.TimeoutExpired:
            logger.warning(f"Python script {file_path} timed out after 10 seconds.")
            return "UNSTABLE", "Script timed out."
        except Exception as e:
            logger.error(f"Error executing Python script {file_path}: {e}")
            return "UNSTABLE", f"Execution error: {e}"

    def _validate_seo_content(self, file_path):
        logger.info(f"Validating SEO content: {file_path}")
        # For now, just check if the file is not empty.
        # More sophisticated validation (e.g., keyword density, structure)
        # can be added here later.
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            if content:
                logger.info(f"SEO content {file_path} validated (not empty).")
                return "STABLE", "N/A"
            else:
                logger.warning(f"SEO content {file_path} is empty.")
                return "UNSTABLE", "Content is empty."
        except Exception as e:
            logger.error(f"Error reading SEO content {file_path}: {e}")
            return "UNSTABLE", f"File read error: {e}"

    def _archive_content(self, data, file_name, original_pulse):
        data_type = data.get(DATA_TYPE_KEY)
        status = data.get(DATA_STATUS_KEY)
        file_path = data.get(DATA_CONTENT_KEY)

        archive_dir = ""
        if data_type == "python_script":
            if status == "STABLE":
                archive_dir = self.script_dirs["lethian_archive_stable_python"]
            else:
                archive_dir = self.script_dirs["lethian_archive_unstable_python"]
        elif data_type == "seo_content":
            if status == "STABLE":
                archive_dir = self.script_dirs["lethian_archive_stable_seo"]
            else:
                archive_dir = self.script_dirs["lethian_archive_unstable_seo"]
        else:
            logger.warning(f"Cannot archive unknown data type: {data_type}")
            return

        destination_path = os.path.join(archive_dir, file_name)
        try:
            os.rename(file_path, destination_path)
            logger.info(f"Archived {file_name} as {status} to {archive_dir}")
        except Exception as e:
            logger.error(f"Error archiving {file_name} from {file_path} to {destination_path}: {e}")
