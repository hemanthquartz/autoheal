import os
import shutil

SRC_DIR = "/opt/python"
DST_DIR = "/var/task/awssdk"

def bootstrap_awssdk():
    if not os.path.exists(SRC_DIR):
        print(f"Source layer path missing: {SRC_DIR}")
        return

    if not os.path.exists(DST_DIR):
        os.makedirs(DST_DIR, exist_ok=True)

        for item in os.listdir(SRC_DIR):
            src_path = os.path.join(SRC_DIR, item)
            dst_path = os.path.join(DST_DIR, item)

            if os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            else:
                shutil.copy2(src_path, dst_path)

        print(f"Copied {SRC_DIR} → {DST_DIR}")
    else:
        print(f"{DST_DIR} already exists")

bootstrap_awssdk()