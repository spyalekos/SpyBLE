import json
import os

CONFIG_FILE = "config.json"

def load_config():
    default_config = {
        "thermometer_mac": "",
        "miflora_mac": "",
        "poll_interval": 30,
        "live_mode": True,
        "last_readings": {
            "thermometer": {},
            "miflora": {}
        }
    }
    if not os.path.exists(CONFIG_FILE):
        save_config(default_config)
        return default_config
    
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure default keys exist
            for k, v in default_config.items():
                if k not in data:
                    data[k] = v
            return data
    except Exception:
        return default_config

def save_config(config_data):
    try:
        # Preserve last_readings if existing
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    if "last_readings" in existing and "last_readings" not in config_data:
                        config_data["last_readings"] = existing["last_readings"]
            except Exception:
                pass
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False

def save_last_readings(sensor_type, readings_dict):
    try:
        config = load_config()
        if "last_readings" not in config:
            config["last_readings"] = {}
        config["last_readings"][sensor_type] = readings_dict
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False

