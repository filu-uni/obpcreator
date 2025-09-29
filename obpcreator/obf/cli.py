
"""Command-line tool to convert BOSS files to OBF."""

# Built-in
import argparse
import json
import os
import pathlib
import sys
import uuid
import zipfile

# Third-party
import yaml


LUA_SCRIPT = """
-- api objects: machine, mqtt, nir_camera, obf, system

function wait(predicate, timeout, settings)
    local interval = 1
    if settings ~= nil and settings.interval ~= nil then
        interval = settings.interval
    end
    local deadline = os.time() + timeout
    while not predicate() do
        system.sleep(interval)
        if os.time() >= deadline then
            return false
        end
    end
    return true
end

function wait_for_beam_power_low()
    if not wait(function()
            local hv_current = machine.get_hv_current()
            return hv_current ~= nil and hv_current <= 1.0
        end, 30) then
        machine.clear_exposure_queue()
        error("Build Aborted: BeamPowerLow condition timed out")
    end
end

function should_do_heat_balance(heat_balance)
    return heat_balance.repetitions ~= nil and heat_balance.repetitions > 0
end

function log(message)
    system.print(message)
    mqtt.publish_field("BuildStatus", "Trace", "Activity", "current_activity", message)
end

function logfatal(message)
    message = string.format("Build Error: %s", message)
    log(message)
    machine.clear_exposure_queue()
    error(message)
end

local build_info = obf.get_build_info()
local start_heat = build_info.startHeat
local temperature_sensor = start_heat.temperatureSensor
local target_temperature = start_heat.targetTemperature

local jumpSafeDefault = build_info.jumpSafe or {}
local heatBalanceDefault = build_info.heatBalance or {}
local num_layers = #build_info.layers
local layerfeed = build_info.layerDefaults["layerFeed"] or {}

local jump_safe_input = mqtt.construct_topic("Parameters", "Name", "PreHeatRepetitions")
local heat_balance_input = mqtt.construct_topic("Parameters", "Name", "PostHeatRepetitions")

local maxRetryCount = 10

mqtt.publish("BuildStatus", "Trace", "Layers", {
    build_layers = num_layers,
    current_layer = 0,
})

mqtt.add_subscription(jump_safe_input)
mqtt.add_subscription(heat_balance_input)

mqtt.publish_field(
    "Parameters", "Name",
    "PreHeatRepetitions", "repetitions",
    0
-- build_info.layers[1].jumpSafe[1].repetitions
)
mqtt.publish_field(
    "Parameters", "Name",
    "PostHeatRepetitions", "repetitions",
    0
)

-- ========== START HEAT ==========
log("Init")
log("Turning on the beam")
if not machine.beam_is_on() and not machine.restartHV(60) then
    logfatal("Failed to start beam")
end
log("The beam is active")
log("Start heating to target temperature: " .. target_temperature)
machine.start_exposure(start_heat.file, 4294967295)
system.print("Waiting for " .. start_heat.timeout .. " seconds or until target temperature is reached.")
if not wait(function()
        if not machine.beam_is_on() and not machine.restartHV(60) then
            logfatal("Failed to start beam")
        end
        local temperature = machine.get_temperature(temperature_sensor)
        return temperature and temperature >= target_temperature
    end, start_heat.timeout, { interval = 0.5 }) then
    logfatal("Failed to reach target temperature")
end
if not machine.clear_exposure_queue() then
    logfatal("Failed to clear exposure queue")
end
-- ========== END START HEAT ==========

system.print("OBF has " .. num_layers .. " layers.")
for index, layer in ipairs(build_info.layers) do
    system.print("Starting to process layer " .. index)
    mqtt.publish("BuildStatus", "Trace", "Layers", {
        build_layers = num_layers,
        current_layer = index,
    })
    log("Waiting for beam power low")
    wait_for_beam_power_low()

    -- ========== RECOATE CYCLE ==========
    log("Recoat cycle. Layer " .. index .. "")
    if not machine.recoat_cycle(layerfeed) then
        logfatal("Unable to complete Layerfeed.")
    end
    -- (proheat should be in heating position)
    if not machine.beam_is_on() then
        log("Beam was off after recoating. Turning it on!")
        if not machine.restartHV(60) then
            logfatal("Timeout waiting for beam on")
        end
    end

    -- ========== EXPOSE LAYER'S OBP FILES ==========
    local layerDone = false
    local retryCount = 0
    while not layerDone do
        -- There are four process steps:
        local jumpSafePatterns = {}
        local spatterSafePatterns = {}
        local meltPatterns = {}
        local heatBalancePatterns = {}

        -- JUMP SAFE
        -- Uses the mqtt value of currentJumpSafeReps as an absolute value,
        -- meaning that it replaces the original value.




        local currentJumpSafeReps = mqtt.get_field(jump_safe_input, "repetitions")

        system.print("Jump safe reps: " .. currentJumpSafeReps .. "")

        if layer.jumpSafe ~= nil then
            for _, obp in ipairs(layer.jumpSafe) do
                table.insert(jumpSafePatterns, { file = obp.file, repetitions = currentJumpSafeReps + obp.repetitions })
            end
        end

        -- SPATTER SAFE

        if layer.spatterSafe ~= nil then
            for _, obp in ipairs(layer.melt) do
                table.insert(meltPatterns, { file = obp.file, repetitions = obp.repetitions })
            end
        end

        -- MELT
        for _, obp in ipairs(layer.melt) do
            table.insert(meltPatterns, { file = obp.file, repetitions = obp.repetitions })
        end

        -- HEAT BALANCE
        -- Use the mqtt-value as an offset to the layer's reps

        -- Check if layer specific heat balance exists, if not, add an empty table

        -- If the table above is empty, use the layer default instead.
        -- This is handles the same for both jumpSafe, spatterSafe, and heatBalance.


        local heatBalanceRepetitions = mqtt.get_field(heat_balance_input, "repetitions")

        system.print("Heat balance reps: " .. heatBalanceRepetitions .. "")

        if layer.heatBalance ~= nil then
            for _, obp in ipairs(layer.heatBalance) do
                table.insert(heatBalancePatterns,
                    { file = obp.file, repetitions = obp.repetitions + heatBalanceRepetitions })
            end
        end

        -- EXPOSURE
        log(string.format("Exposing OBP files of layer %d.%s", index, retryCount > 0 and " Retry " .. retryCount or ""))
        local err_id = machine.start_process_step_exposures(
            jumpSafePatterns, spatterSafePatterns, meltPatterns, heatBalancePatterns)
        if err_id == 0 then
            layerDone = true
        elseif err_id == 1 then
            log("Arc trip during Jump Safe exposure")
            layerDone = false
            newPowderLayer = false
        elseif err_id == 2 then
            log("Arc trip during Spatter Safe exposure")
            layerDone = false
            newPowderLayer = false
        elseif err_id == 3 then
            log("Arc trip during Melt exposure")
            layerDone = false
            newPowderLayer = true
        elseif err_id == 4 then
            log("Arc trip during Heat Balance exposure")
            layerDone = true
            newPowderLayer = false
        end
        if err_id ~= 0 then
            machine.clear_exposure_queue()
            if not machine.restart_after_arc_trip(newPowderLayer, 60) then
                logfatal("Unable to recover from arc trip")
            end
        end
        if not layerDone then
            retryCount = retryCount + 1
        end
        if retryCount > maxRetryCount then
            logfatal("Maximum retry count exceeded!")
        end
    end -- this layer done loop
end     -- all layers loop

-- ========== TEARDOWN ==========

machine.clear_exposure_queue()
log("Waiting for beam power low")
wait_for_beam_power_low()
log("Turning off the beam")
machine.beam_off()
log("Turning off the PSU")
machine.power_off()
log("Build finished")
"""


def snake_to_camel(snake_str: str) -> str:
    """
    Convert snake_case string to camelCase string.

    Args:
        snake_str (str): The snake_case string.

    Returns:
        str: The camelCase string.
    """
    parts = snake_str.split("_")
    # The first part is lowercase, subsequent parts are capitalized
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


def convert_keys_to_camel(obj: dict) -> dict:
    """
    Recursively convert dictionary keys from snake_case to camelCase.

    Args:
        obj (dict): The dictionary to process.

    Returns:
        dict: A new dictionary with keys in camelCase.
    """
    if not isinstance(obj, dict):
        raise TypeError("Input must be a dictionary.")

    new_dict = {}
    for key, value in obj.items():
        new_key = snake_to_camel(key)
        if isinstance(value, dict):
            new_value = convert_keys_to_camel(value)
        else:
            new_value = value
        new_dict[new_key] = new_value
    return new_dict


def convert(input_dir: str, output_obf: str, name: str) -> None:
    """Convert a directory of BOSS files to an OBF (PoC).

    PROOF OF CONCEPT -- NOT PRODUCTION READY.
    """

    input_path = pathlib.Path(input_dir)
    print(f"Input path is {input_dir}")
    yaml_files = list(input_path.glob("*.yaml")) + list(input_path.glob("*.yml"))
    if len(yaml_files) != 1:
        raise ValueError(
            f"Expected exactly one yaml file in input directory, found {yaml_files}"
        )

    with open(yaml_files[0]) as build_yaml:
        boss_data = yaml.safe_load(build_yaml)

    obf_name = name or pathlib.Path(output_obf).stem
    print(f"Using name {obf_name}!")

    manifest = {
        "formatVersion": "3.0",
        "project": {
            "id": str(uuid.uuid4()),
            "name": "obf3.0",
            "description": "Converted from BOSS to OBF 3.0",
            "revision": {"number": 1, "note": ""},
        },
        "author": {"email": "convert_boss_to_obf@example.com"},
        "reference": {
            "name": "convert-boss-to-obf",
            "uri": "https://gitlab.com/freemelt/openmelt/obflib-python",
        },
    }

    build_processors_info = {
        "default": {
            "type": "lua",
            "entryPoint": "buildProcessors/default/build.lua",
        }
    }

    dependencies = {
        "material": {"name": "Unspecified", "powderSize": 0},
        "software": {},
    }

    boss_start_heat = boss_data["build"]["start_heat"]
    boss_preheat = boss_data["build"]["preheat"]
    boss_postheat = boss_data["build"]["postheat"]

    jump_safe_dict = {
        "file": f"obp/{pathlib.PurePath(boss_preheat['file']).name}",
        "repetitions": boss_preheat["repetitions"],
    }

    heat_balance_dict = {
        "file": f"obp/{pathlib.PurePath(boss_postheat['file']).name}",
        "repetitions": boss_postheat["repetitions"],
    }

    build_info = {
        "startHeat": {
            "file": f"obp/{pathlib.PurePath(boss_start_heat['file']).name}",
            "temperatureSensor": boss_start_heat["temp_sensor"],
            "targetTemperature": boss_start_heat["target_temperature"],
            "timeout": boss_start_heat["timeout"],
        },
        "layerDefaults": {
            "layerFeed": convert_keys_to_camel(boss_data["build"]["layerfeed"])
        },
        "layers": [],
    }

    while len(build_info["layers"]) < boss_data["build"]["build"]["layers"]:
        for boss_layer in boss_data["build"]["build"]["files"]:
            if len(build_info["layers"]) >= boss_data["build"]["build"]["layers"]:
                break

            files = boss_layer if isinstance(boss_layer, list) else [boss_layer]
            layer = {
                "jumpSafe": [jump_safe_dict],
                "melt": [],
                "heatBalance": [heat_balance_dict],
            }

            for file in files:
                file_dict = dict()
                file_dict["file"] = f"obp/{pathlib.PurePath(file).name}"
                file_dict["repetitions"] = 1

                layer["melt"].append(file_dict)

            build_info["layers"].append(layer)

    obp_files = []
    basenames = set()
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.endswith(".obp") or file.endswith(".gz"):
                full_path = os.path.join(root, file)
                basename = os.path.basename(file)
                if basename in basenames:
                    raise ValueError(f"Duplicate file name found: {basename}")
                basenames.add(basename)
                obp_files.append(full_path)

    print(f"Number of obp files found: {len(obp_files)}")

    with zipfile.ZipFile(output_obf, "w", compression=zipfile.ZIP_DEFLATED) as obf:
        print(f"Writing manifest.json")
        obf.writestr("manifest.json", json.dumps(manifest, indent=2))

        print(f"Writing buildProcessors.json")
        obf.writestr(
            "buildProcessors.json",
            json.dumps(build_processors_info, indent=2),
        )

        print(f"Writing dependencies.json")
        obf.writestr("dependencies.json", json.dumps(dependencies, indent=2))

        print(f"Writing buildProcessors/default/build.lua")
        obf.writestr("buildProcessors/default/build.lua", LUA_SCRIPT)

        print(f"Writing buildInfo.json")
        obf.writestr("buildInfo.json", json.dumps(build_info, indent=2))

        for obp in obp_files:
            relative_path = os.path.relpath(obp, input_dir)
            print(f"Adding obp: {relative_path}")

            with (
                obf.open(f"obp/{os.path.basename(obp)}", "w") as output_obp,
                open(obp, "rb") as input_obp,
            ):
                output_obp.write(input_obp.read())

    print(f"Done! Wrote OBF to '{output_obf}")


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="convert-boss-to-obf")
    parser.add_argument(
        "input_boss_dir",
        type=pathlib.Path,
        help="The BOSS directory to be converted",
    )
    parser.add_argument(
        "--output-obf",
        type=pathlib.Path,
        help="Output OBF file name (default: input directory name with .obf suffix)",
    )
    parser.add_argument(
        "--name",
        type=str,
    )
    return parser


def main() -> None:
    parser = get_parser()
    args = parser.parse_args()

    if not args.input_boss_dir.is_dir():
        print(f"Error: {args.input_boss_dir} is not a directory or does not exist.")
        sys.exit(1)

    if args.output_obf is None:
        args.output_obf = args.input_boss_dir.with_suffix(".obf")

    try:
        convert(args.input_boss_dir, args.output_obf, args.name)
    except KeyboardInterrupt:
        print("Bye")


if __name__ == "__main__":
    main()

