from datetime import datetime
import os
import json
import shutil
from importlib.resources import files


def generate_obf_directories(folder_path, name=""):
    if name == "":
        now = datetime.now()
        name = f"build_{now.year}_{now.month:02}_{now.day:02}_{now.hour:02}_{now.minute:02}_{now.second:02}"
    path = f"{folder_path}/{name}"
    # Create the directory if it doesn't exist
    os.makedirs(path, exist_ok=True)
    os.makedirs(f"{path}/buildProcessors")
    os.makedirs(f"{path}/buildProcessors/lua")
    os.makedirs(f"{path}/obp")
    print(f"Directory '{path}' created or already exists.")
    return path

def generate_other_files(base_folder):
    """
    Copy helper files from the obpcreator package to a target base folder.
    This works from installed packages or source.
    """
    file_map = {
        "buildProcessors.json": "buildProcessors.json",
        "dependencies.json": "dependencies.json",
        "manifest.json": "manifest.json",
        "build.lua": os.path.join("buildProcessors", "lua", "build.lua"),
        "start_heat.obp": os.path.join("obp", "start_heat.obp"),
        "pre_heat.obp": os.path.join("obp", "pre_heat.obp"),
        "post_heat.obp": os.path.join("obp", "post_heat.obp"),
        "obpviewer.py": os.path.join("obp", "obpviewer.py"),
    }

    for src_filename, relative_dest in file_map.items():
        source = files("obpcreator.obf.helpers").joinpath(src_filename)
        destination = os.path.join(base_folder, relative_dest)

        # Ensure destination directories exist
        os.makedirs(os.path.dirname(destination), exist_ok=True)

        # Copy the file
        with source.open("rb") as fsrc, open(destination, "wb") as fdst:
            shutil.copyfileobj(fsrc, fdst)
