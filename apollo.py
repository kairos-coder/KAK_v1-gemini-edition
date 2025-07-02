import multiprocessing
import time
import os
import requests
import json
from datetime import datetime
import re # <--- Ensure this is imported

from common_utils import (
    setup_logging, set_cpu_affinity,
    DATA_TYPE_KEY, DATA_CONTENT_KEY, DATA_PULSE_KEY, DATA_STATUS_KEY,
    OLLAMA_API_BASE_URL, OLLAMA_TIMEOUT,
    PULSE_PYTHON_SCRIPT, PULSE_SEO_CONTENT,
    LETHE_STATUS_MESSAGE_KEY, LETHE_ERROR_MESSAGE_KEY
)

# Setup logging for Apollo
logger = setup_logging("Apollo")

class Apollo:
    # MODIFIED: Accept ollama_busy_event
    def __init__(self, kronos_to_apollo_q, apollo_to_mnemo_q, lethe_to_apollo_feedback_q, ollama_busy_event):
        self.kronos_to_apollo_q = kronos_to_apollo_q
        self.apollo_to_mnemo_q = apollo_to_mnemo_q
        self.lethe_to_apollo_feedback_q = lethe_to_apollo_feedback_q
        self.running_event = None
        self.cpu_affinity = None
        self.ollama_busy_event = ollama_busy_event # STORE: the new event

        # Feedback state variables
        self.last_lethe_status = "NONE" # Can be "NONE", "STABLE", "UNSTABLE"
        self.last_lethe_error = "N/A"
        self.current_feedback_prompt_addon = "" # Dynamic prompt modifier based on feedback

        # Model configuration (can be made dynamic later)
        self.python_model = "tinydolphin:latest"
        self.seo_model = "tinydolphin:latest" # Using tinydolphin for both for consistency

        logger.info("Initialized.")

    def run(self, cpu_affinity, running_event):
        self.cpu_affinity = cpu_affinity
        self.running_event = running_event
        set_cpu_affinity(os.getpid(), self.cpu_affinity, logger)
        logger.info(f"Starting on PID {os.getpid()} (assigned CPU {self.cpu_affinity}).")

        while self.running_event.is_set():
            # Check for new keywords/elements from Kronos
            if not self.kronos_to_apollo_q.empty():
                data = self.kronos_to_apollo_q.get()
                data_type = data.get(DATA_TYPE_KEY)
                keywords = data.get(DATA_CONTENT_KEY)
                original_pulse = data.get(DATA_PULSE_KEY)
                logger.info(f"Received {data_type} keywords/elements from Kronos. Count: {len(keywords)}. Pulse: {original_pulse}")

                generated_content = None
                model_to_use = ""

                # Decide which model and prompt to use based on the data type and feedback
                if data_type == PULSE_PYTHON_SCRIPT:
                    model_to_use = self.python_model
                    prompt = self._construct_python_prompt(keywords)
                elif data_type == PULSE_SEO_CONTENT:
                    model_to_use = self.seo_model
                    prompt = self._construct_seo_prompt(keywords)
                else:
                    logger.warning(f"Unknown data type '{data_type}' received. Skipping generation.")
                    continue

                logger.info(f"Generating {data_type} content using model '{model_to_use}'...")

                # --- NEW: Signal KAK modules to pause before Ollama call ---
                logger.debug("Apollo: Clearing ollama_busy_event (pausing KAK).")
                self.ollama_busy_event.clear()

                generated_content = self._generate_with_ollama(model_to_use, prompt)

                # --- NEW: Signal KAK modules to resume after processing/queueing ---
                if generated_content:
                    # For Python scripts, try to extract just the code block
                    if data_type == PULSE_PYTHON_SCRIPT:
                        extracted_code = self._extract_code_block(generated_content)
                        if extracted_code:
                            generated_content = extracted_code
                            logger.info("Extracted Python code block successfully.")
                        else:
                            logger.warning("Could not extract Python code block. Using full generated content.")

                    # Prepare data to send to Mnemo
                    output_data = {
                        DATA_TYPE_KEY: data_type,
                        DATA_CONTENT_KEY: generated_content,
                        DATA_PULSE_KEY: original_pulse # Pass original pulse to Mnemo
                    }
                    self.apollo_to_mnemo_q.put(output_data)
                    logger.info(f"Generated and sent {data_type} content to Mnemo (length: {len(generated_content)}).")
                    logger.debug("Apollo: Setting ollama_busy_event (resuming KAK).")
                    self.ollama_busy_event.set() # Resume KAK only after successfully sending to Mnemo
                else:
                    logger.error(f"Failed to generate {data_type} content.")
                    logger.debug("Apollo: Setting ollama_busy_event (resuming KAK, even on failure to avoid deadlock).")
                    self.ollama_busy_event.set() # Always re-set to avoid KAK deadlock even if generation fails

            # Check for feedback from Lethe
            if not self.lethe_to_apollo_feedback_q.empty():
                feedback = self.lethe_to_apollo_feedback_q.get()
                self.last_lethe_status = feedback.get(LETHE_STATUS_MESSAGE_KEY, "NONE")
                self.last_lethe_error = feedback.get(LETHE_ERROR_MESSAGE_KEY, "N/A")
                logger.info(f"Received feedback from Lethe: Status='{self.last_lethe_status}', Error='{self.last_lethe_error}'.")

                # Dynamically adjust prompt based on feedback
                if self.last_lethe_status == "UNSTABLE":
                    self.current_feedback_prompt_addon = f"The previous attempt failed with error: '{self.last_lethe_error}'. Please try to correct this and generate a working version."
                else:
                    self.current_feedback_prompt_addon = "" # Reset if stable or no specific error

            else:
                time.sleep(0.1) # Small delay to prevent busy-waiting
        logger.info("Shutting down.")

    def _construct_python_prompt(self, keywords):
        # Base prompt for Python script generation
        base_prompt = (
            "You are an expert Python programmer. Generate a complete, concise, and functional Python script based on the following keywords/requirements. "
            "The script should be self-contained and ready to run. Include necessary imports. "
            "Wrap the entire script in a single markdown code block with '```python' at the beginning and '```' at the end.\n\n"
            f"Keywords/Requirements: {', '.join(keywords)}.\n\n"
            "Example: If keywords are 'file io, read, write', generate a script that reads from one file and writes to another."
        )
        return base_prompt + self.current_feedback_prompt_addon

    def _construct_seo_prompt(self, keywords):
        # Base prompt for SEO content generation
        base_prompt = (
            "You are an expert SEO content creator. Generate a concise, well-structured, and engaging piece of SEO-optimized content "
            "based on the following keywords/phrases. Focus on natural language and incorporate keywords effectively. "
            "Do not include any code blocks or special formatting outside of standard paragraphs. "
            "Return only the content.\n\n"
            f"Keywords/Phrases: {', '.join(keywords)}.\n\n"
            "Example: If keywords are 'best coffee shop, downtown, reviews', generate a paragraph reviewing a coffee shop."
        )
        return base_prompt + self.current_feedback_prompt_addon

    def _extract_code_block(self, text):
        """
        Extracts content within a Python markdown code block (```python ... ```).
        If multiple blocks are present, it takes the first one.
        If no block is found, returns None.
        """
        # This regex looks for ```python followed by any characters (non-greedy) up to ```
        match = re.search(r"```python\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _generate_with_ollama(self, model, prompt):
        url = f"{OLLAMA_API_BASE_URL}/api/generate"
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False # We want the full response at once
        }

        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=OLLAMA_TIMEOUT)
            response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)

            response_data = response.json()
            generated_text = response_data.get("response", "").strip()

            logger.debug(f"Ollama raw generated text:\n{generated_text}")

            if generated_text:
                return generated_text
            else:
                logger.warning(f"Ollama returned empty response for model {model} with prompt: {prompt}")
                return None

        except requests.exceptions.Timeout:
            logger.error(f"Ollama request timed out after {OLLAMA_TIMEOUT} seconds for model {model}.")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Could not connect to Ollama server at {OLLAMA_API_BASE_URL}: {e}")
            logger.error("Please ensure Ollama is running and the model is available.")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error from Ollama: {e.response.status_code} - {e.response.text}")
            logger.debug(f"Ollama error response body: {e.response.text}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from Ollama response: {e}")
            logger.debug(f"Ollama raw response that caused JSONDecodeError: {response.text}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred during Ollama generation: {e}")
            return None
