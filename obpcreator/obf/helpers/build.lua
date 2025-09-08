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
	if
		not wait(function()
			local hv_current = machine.get_hv_current()
			return hv_current ~= nil and hv_current <= 1.0
		end, 30)
	then
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
	"Parameters",
	"Name",
	"PreHeatRepetitions",
	"repetitions",
	0
	-- build_info.layers[1].jumpSafe[1].repetitions
)
mqtt.publish_field("Parameters", "Name", "PostHeatRepetitions", "repetitions", 0)

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
if
	not wait(function()
		if not machine.beam_is_on() and not machine.restartHV(60) then
			logfatal("Failed to start beam")
		end
		local temperature = machine.get_temperature(temperature_sensor)
		return temperature and temperature >= target_temperature
	end, start_heat.timeout, { interval = 0.5 })
then
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

		system.print("Jump safe reps to add: " .. currentJumpSafeReps .. "")

		if layer.jumpSafe ~= nil then
			for _, obp in ipairs(layer.jumpSafe) do
				system.print("Jump Safe reps: " .. obp.repetitions .. "")
				system.print("Total Jump Safe reps: " .. obp.repetitions + currentJumpSafeReps .. "")
				table.insert(
					jumpSafePatterns,
					{ file = obp.file, repetitions = math.max(0, currentJumpSafeReps + obp.repetitions) }
				)
			end
		end

		-- SPATTER SAFE

		if layer.spatterSafe ~= nil then
			for _, obp in ipairs(layer.spatterSafe) do
				table.insert(spatterSafePatterns, { file = obp.file, repetitions = obp.repetitions })
			end
		end

		-- MELT
		if layer.melt ~= nil then
			for _, obp in ipairs(layer.melt) do
				table.insert(meltPatterns, { file = obp.file, repetitions = obp.repetitions })
			end
		end

		-- HEAT BALANCE
		-- Use the mqtt-value as an offset to the layer's reps

		-- Check if layer specific heat balance exists, if not, add an empty table

		-- If the table above is empty, use the layer default instead.
		-- This is handles the same for both jumpSafe, spatterSafe, and heatBalance.

		local heatBalanceRepetitions = mqtt.get_field(heat_balance_input, "repetitions")

		system.print("Heat balance reps to add: " .. heatBalanceRepetitions .. "")
		if layer.heatBalance ~= nil then
			for _, obp in ipairs(layer.heatBalance) do
				system.print("Base Heat Balance reps: " .. obp.repetitions .. "")
				system.print("Total Heat Balance reps: " .. obp.repetitions + heatBalanceRepetitions .. "")
				table.insert(
					heatBalancePatterns,
					{ file = obp.file, repetitions = math.max(0, obp.repetitions + heatBalanceRepetitions) }
				)
			end
		end

		-- EXPOSURE
		log(string.format("Exposing OBP files of layer %d.%s", index, retryCount > 0 and " Retry " .. retryCount or ""))
		local err_id = machine.start_process_step_exposures(
			jumpSafePatterns,
			spatterSafePatterns,
			meltPatterns,
			heatBalancePatterns
		)
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
			if not machine.restart_after_arc_trip(newPowderLayer, 60, layerfeed) then
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
end -- all layers loop

-- ========== TEARDOWN ==========

machine.clear_exposure_queue()
log("Waiting for beam power low")
wait_for_beam_power_low()
log("Turning off the beam")
machine.beam_off()
log("Turning off the PSU")
machine.power_off()
log("Build finished")
