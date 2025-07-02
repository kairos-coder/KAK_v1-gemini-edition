# === kronos.py (Updated to respect ollama_busy_event) ===
import multiprocessing
import time
import os
import random
import itertools # For permutations/combinations

from common_utils import (
    setup_logging, set_cpu_affinity,
    DATA_TYPE_KEY, DATA_CONTENT_KEY, DATA_PULSE_KEY,
    PULSE_PYTHON_SCRIPT, PULSE_SEO_CONTENT
)

# Setup logging for Kronos
logger = setup_logging("Kronos")

class Kronos:
    # MODIFIED: Accept ollama_busy_event
    def __init__(self, aion_to_kronos_q, kronos_to_apollo_q, kronos_log_q, current_pulse_shared_value, ollama_busy_event):
        self.aion_to_kronos_q = aion_to_kronos_q
        self.kronos_to_apollo_q = kronos_to_apollo_q
        self.kronos_log_q = kronos_log_q
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

        while self.running_event.is_set():
            # NEW: Pause if Ollama is busy
            if not self.ollama_busy_event.is_set():
                logger.debug("Kronos: Ollama is busy, pausing keyword synthesis.")
                time.sleep(0.5) # Wait a bit and re-check
                continue # Skip to next iteration of while loop

            current_pulse = self.current_pulse_shared_value.value

            if not self.aion_to_kronos_q.empty():
                data = self.aion_to_kronos_q.get()
                data_type = data.get(DATA_TYPE_KEY)
                processed_elements = data.get(DATA_CONTENT_KEY) # This is now a list of elements/fragments
                original_pulse = data.get(DATA_PULSE_KEY)
                logger.info(f"Received {data_type} elements from Aion. Count: {len(processed_elements)}. Pulse: {original_pulse}")

                synthesized_results = []

                if data_type == PULSE_PYTHON_SCRIPT:
                    # Simple synthesis for Python: just take a few random elements
                    # or combine them into a simple "idea" for a script
                    if processed_elements:
                        # Take up to 5 unique random elements to form the "keywords" for Apollo
                        unique_elements = list(set(processed_elements))
                        synthesized_results = random.sample(unique_elements, min(len(unique_elements), 5))
                        logger.info(f"Synthesized Python keywords. Keywords: {synthesized_results}. Pulse: {current_pulse}")
                        self.kronos_log_q.put(f"Synthesized Python Keywords: {synthesized_results}. Pulse: {current_pulse}")
                    else:
                        synthesized_results = ["basic_script_idea"] # Default if no elements
                        logger.warning("No processed elements for Python script. Using default.")

                elif data_type == PULSE_SEO_CONTENT:
                    # For SEO, try to combine fragments into potential keywords or search queries
                    # This is a basic example; more sophisticated NLP could be used here.
                    found_keywords = set()
                    # Example target keywords (expand this list based on desired SEO topics)
                    target_full_keywords = {
                        "digital marketing", "seo strategy", "content creation",
                        "online business", "social media", "search engine optimization",
                        "how to get more website traffic", "best marketing tools",
                        "python programming tutorial", "machine learning basics" # Cross-over potential
                    }

                    # Try single fragments that are full keywords
                    for frag in processed_elements:
                        if frag.lower() in target_full_keywords:
                            found_keywords.add(frag.lower())

                    # Try combining two fragments (e.g., "digital" + "marketing")
                    for f1, f2 in itertools.permutations(processed_elements, 2):
                        combined = (f1 + " " + f2).lower()
                        if combined in target_full_keywords:
                            found_keywords.add(combined)
                        # Also try without space for concatenated fragments
                        combined_no_space = (f1 + f2).lower()
                        if combined_no_space in target_full_keywords:
                            found_keywords.add(combined_no_space)

                    # Try combining three fragments (e.g., "how" + "to" + "seo")
                    for f1, f2, f3 in itertools.permutations(processed_elements, 3):
                        combined = (f1 + " " + f2 + " " + f3).lower()
                        if combined in target_full_keywords:
                            found_keywords.add(combined)
                        # Also try without space for concatenated fragments
                        combined_no_space = (f1 + f2 + f3).lower()
                        if combined_no_space in target_full_keywords:
                            found_keywords.add(combined_no_space)

                    synthesized_results = list(found_keywords)
                    logger.info(f"Synthesized SEO keywords from fragments. Found: {len(synthesized_results)}. Keywords: {synthesized_results}. Pulse: {current_pulse}")
                    self.kronos_log_q.put(f"Synthesized SEO Keywords: {synthesized_results}. Pulse: {current_pulse}")

                else:
                    logger.warning(f"Unknown data type '{data_type}' received in Kronos. Pulse: {current_pulse}")
                    synthesized_results = ["general", "information"] # Default

                # Prepare data to send to Apollo
                output_data = {
                    DATA_TYPE_KEY: data_type,
                    DATA_CONTENT_KEY: synthesized_results, # This is now the synthesized keywords/elements list
                    DATA_PULSE_KEY: original_pulse
                }
                self.kronos_to_apollo_q.put(output_data)
            else:
                time.sleep(0.1)
        logger.info("Shutting down.")
