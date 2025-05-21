# config_loader.py

import configparser
import os

_config = None

def get_config(config_path="config.conf"):
    global _config
    if _config is None:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Файл конфигурации '{config_path}' не найден.")

        _config = configparser.ConfigParser()
        _config.read(config_path, encoding="utf-8")
    return _config