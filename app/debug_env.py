import os
from config import Config

def check_security():
    master_key = os.environ.get("AEON_MASTER_KEY", "IKKE FUNDET")
    config_key = Config.MASTER_KEY
    node_mapping = Config.VALID_NODE_IDS.get("NODE_GEMINI_01", "INGEN MAPPING")
    
    print(f"--- AEON DEBUG ---")
    print(f"OS Environ Key (første 4 tegn): {master_key[:4]}...")
    print(f"Config Class Key (første 4 tegn): {config_key[:4]}...")
    print(f"Node Mapping Key (første 4 tegn): {node_mapping[:4]}...")
    print(f"------------------")

if __name__ == "__main__":
    check_security()