"""VSS signal paths used by the vehicle apps (one place, so a rename is one edit).

Standard VSS signals come from COVESA VSS 4.x. The Vehicle.Fleet.* and
Vehicle.Hazard.* signals are our own overlay (see vehicle/vss/fleet_overlay.vspec).

Every standard path below exists in VSS 5.1, the catalogue that ships with
kuksa-databroker 0.6.0. The overlay paths come from vehicle/vss/fleet_overlay.json.
"""

# --- standard VSS ---
SPEED = "Vehicle.Speed"                                                  # km/h
ACCEL_LONG = "Vehicle.Acceleration.Longitudinal"                         # m/s^2 (negative = braking)
TCS_ENGAGED = "Vehicle.ADAS.TCS.IsEngaged"                               # bool
LATITUDE = "Vehicle.CurrentLocation.Latitude"
LONGITUDE = "Vehicle.CurrentLocation.Longitude"
SOC = "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current"         # %
ODOMETER = "Vehicle.TraveledDistance"                                    # km
POWER_STATE = "Vehicle.LowVoltageSystemState"                           # "ON" / "OFF" (engine status)
COOLANT_TEMP = "Vehicle.Powertrain.ElectricMotor.CoolantTemperature"     # deg C
HAZARD_LIGHTS = "Vehicle.Body.Lights.Hazard.IsSignaling"                 # bool

# --- our overlay: fleet ---
FLEET_VEHICLE_ID = "Vehicle.Fleet.VehicleId"
FLEET_ROUTE_ID = "Vehicle.Fleet.RouteId"
FLEET_TRIP_ID = "Vehicle.Fleet.TripId"

# --- our overlay: hazard (written together by the HazardDetector) ---
HAZARD_TYPE = "Vehicle.Hazard.Type"              # e.g. "TRACTION_LOSS", "NONE"
HAZARD_SEVERITY = "Vehicle.Hazard.Severity"      # 0 none, 1 warning, 2 high, 3 critical
HAZARD_DETAIL = "Vehicle.Hazard.Detail"          # human-readable text
HAZARD_DETECTED_AT = "Vehicle.Hazard.DetectedAt" # t0, Unix time in milliseconds

HAZARD_PATHS = [HAZARD_TYPE, HAZARD_SEVERITY, HAZARD_DETAIL, HAZARD_DETECTED_AT]
NO_HAZARD = "NONE"
