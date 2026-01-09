import sys
import os

# --------------------------------------------------
# Lambda path shim: make /opt/python behave like
# /var/task/awssdk (legacy layout)
# --------------------------------------------------

LAYER_AWSSDK_PATH = "/opt/python"

if os.path.exists(LAYER_AWSSDK_PATH):
    # 1. Pretend awssdk lives next to Consumer.py
    sys.path.insert(0, LAYER_AWSSDK_PATH)

    # 2. Also insert submodules (matches old os.listdir logic)
    for item in os.listdir(LAYER_AWSSDK_PATH):
        full_path = os.path.join(LAYER_AWSSDK_PATH, item)
        if os.path.isdir(full_path):
            sys.path.insert(0, full_path)