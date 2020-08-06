import importlib
import sys
from os.path import dirname, join, abspath

def preload(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

homeassistant_path = dirname(importlib.util.find_spec("homeassistant").origin)

tests_path = join(dirname(homeassistant_path), "tests/__init__.py")
preload("tests", tests_path)

custom_components_path = join(dirname(dirname(abspath(__file__))), "custom_components/__init__.py")
preload("custom_components", custom_components_path)
