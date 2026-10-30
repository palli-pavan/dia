"""Top-level Streamlit runner bridging to the modular app/Home.py Command Center.
"""
import os
import sys
import runpy

_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

_app_dir = os.path.join(_root, "app")
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

home_path = os.path.join(_app_dir, "Home.py")
runpy.run_path(home_path, run_name="__main__")
