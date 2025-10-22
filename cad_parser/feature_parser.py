import re
from .constants import FEATURE_TYPES

class FeatureParser:
    @staticmethod
    def extract_feature_blocks(text):
        pattern = re.compile(r'features\.(\w+)\s*=\s*function\(id\)\s*{(.*?if\s*\(\s*true\s*\)\s*{.*?})\s*};', re.DOTALL)
        return re.findall(pattern, text)

    @staticmethod
    def extract_name(block):
        match = re.search(r'annotation\s*{\s*"Feature Name"\s*:\s*"([^\"]+)"\s*}', block)
        return match.group(1) if match else "Unknown"

    @staticmethod
    def extract_description(block):
        match = re.search(r'if\s*\(\s*true\s*\)\s*{(.*)}', block, re.DOTALL)
        return match.group(1).strip() if match else ""

    @staticmethod
    def extract_type_and_id(description):
        for t in FEATURE_TYPES:
            match = re.search(rf'{t}\s*\(\s*context\s*,\s*id\s*\+\s*"([^"]+)"', description)
            if match:
                return t, match.group(1)
        return "unknown", "unknown"
