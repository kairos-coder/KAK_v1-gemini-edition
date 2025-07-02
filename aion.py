# === aion.py (Updated to respect ollama_busy_event) ===
import multiprocessing
import time
import os
import re # For simple pattern matching

from common_utils import (
    setup_logging, set_cpu_affinity,
    DATA_TYPE_KEY, DATA_CONTENT_KEY, DATA_PULSE_KEY,
    PULSE_PYTHON_SCRIPT, PULSE_SEO_CONTENT
)

# Setup logging for Aion
logger = setup_logging("Aion")

class Aion:
    # MODIFIED: Accept ollama_busy_event
    def __init__(self, kairos_to_aion_q, aion_to_kronos_q, current_pulse_shared_value, ollama_busy_event):
        self.kairos_to_aion_q = kairos_to_aion_q
        self.aion_to_kronos_q = aion_to_kronos_q
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

        logger.info("Entering main processing loop.")
        while self.running_event.is_set():
            # NEW: Pause if Ollama is busy
            if not self.ollama_busy_event.is_set():
                logger.debug("Aion: Ollama is busy, pausing data processing.")
                time.sleep(0.5) # Wait a bit and re-check
                continue # Skip to next iteration of while loop

            current_pulse = self.current_pulse_shared_value.value

            if not self.kairos_to_aion_q.empty():
                data = self.kairos_to_aion_q.get()
                data_type = data.get(DATA_TYPE_KEY)
                raw_data = data.get(DATA_CONTENT_KEY)
                original_pulse = data.get(DATA_PULSE_KEY)
                logger.info(f"Received {data_type} raw data from Kairos (length {len(raw_data)}). Pulse: {original_pulse}")

                processed_elements = []

                if data_type == PULSE_PYTHON_SCRIPT:
                    # Simple heuristic: Split by common Python delimiters like space, dot, underscore
                    processed_elements = list(set(re.split(r'[ \._]+', raw_data)))
                    processed_elements = [elem.strip() for elem in processed_elements if elem.strip()]
                    logger.info(f"Filtered Python raw data. Found {len(processed_elements)} potential elements. Pulse: {current_pulse}")

                elif data_type == PULSE_SEO_CONTENT:
                    # For SEO content, look for common words or phrases as fragments
                    # Example fragments (can be expanded later)
                    target_fragments = [
                        "the", "and", "for", "with", "new", "best", "top",
                        "online", "guide", "review", "how to", "what is",
                        "seo", "digital", "marketing", "content", "strategy",
                        "blog", "article", "website", "traffic", "rank",
                        "google", "bing", "youtube", "facebook", "twitter", # common platforms
                        "inst", "gram", "insta", "instagram" # Example of breaking down a keyword
                    ]

                    found_fragments = []
                    # Search for each target fragment in the raw data
                    for fragment in target_fragments:
                        # Use re.finditer to find all non-overlapping occurrences
                        for match in re.finditer(re.escape(fragment), raw_data, re.IGNORECASE):
                            found_fragments.append(match.group(0).lower()) # Append the actual matched string

                    # Filter out duplicates
                    processed_elements = list(set(found_fragments))

                    logger.info(f"Filtered SEO raw data. Found {len(processed_elements)} potential fragments. Pulse: {current_pulse}")

                else:
                    logger.warning(f"Unknown data type '{data_type}' received in Aion. Pulse: {current_pulse}")
                    processed_elements = [raw_data[:100]] # Take a sample if unknown

                # Prepare data to send to Kronos
                output_data = {
                    DATA_TYPE_KEY: data_type,
                    DATA_CONTENT_KEY: processed_elements, # This is now a list of elements/fragments
                    DATA_PULSE_KEY: original_pulse
                }
                self.aion_to_kronos_q.put(output_data)
            else:
                time.sleep(0.1)
        logger.info("Shutting down.")
