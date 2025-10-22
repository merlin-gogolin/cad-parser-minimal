import os
import json
import logging

class CADLogger:
    def __init__(self, log_dir="logs", filename="log.json", log_level=logging.INFO):
        os.makedirs(log_dir, exist_ok=True)
        self.path = os.path.join(log_dir, filename)
        self.logs = []

        # Configure logging
        self.logger = logging.getLogger("CADLogger")
        self.logger.setLevel(log_level)

        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        self.logger.addHandler(handler)
        self.logger.propagate = False  # Avoid duplicate logs

    def log_step(self, step_num, action, observation, debug=True):
        entry = {
            "step": step_num,
            "action": str(action),
            "observation": self._sanitize(observation)
        }
        self.logs.append(entry)
        if debug: 
            self.logger.debug(f"Step {step_num} | Action: {action} | Observation: {self._shorten(entry['observation'])}")

    def info(self, msg):
        self.logger.info(msg)

    def debug(self, msg):
        self.logger.debug(msg)

    def warning(self, msg):
        self.logger.warning(msg)

    def error(self, msg):
        self.logger.error(msg)

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.logs, f, indent=2)
        self.logger.info(f"Logs saved to {self.path}")

    def _sanitize(self, obj):
        def safe(val):
            try:
                json.dumps(val)
                return val
            except TypeError:
                return str(val)

        if isinstance(obj, dict):
            return {k: self._sanitize(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._sanitize(i) for i in obj]
        else:
            return safe(obj)

    def _shorten(self, obj, max_len=100):
        text = str(obj)
        return text if len(text) <= max_len else text[:max_len] + "..."
