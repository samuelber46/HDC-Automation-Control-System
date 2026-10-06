# config/settings.py

OPC_SERVER_NAME = "PMD.DDT_OPCDataServer.1"
OPC_GROUP_NAME = "PDPM11OPCGroup"
OPC_UPDATE_RATE = 500  # milliseconds

LOOP_INTERVAL = 0.5  # seconds

ENABLE_WRITE = True

VALVE_OPEN_TIMEOUT = 10.0  # seconds


# ==================================================
# PROGRAM SAFETY / WATCHDOG
# ==================================================

# Python toggles NEW_HDC.STA at this interval.
# DCS should declare the Python watchdog unhealthy if
# STA does not change within PROGRAM_WATCHDOG_TIMEOUT.
PROGRAM_HEARTBEAT_INTERVAL = 1.0  # seconds
PROGRAM_WATCHDOG_TIMEOUT = 3.0    # seconds
