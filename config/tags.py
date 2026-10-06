# config/tags.py

DCS_PREFIX = "PDS_BlockPin.PDPM11."

DCS_TAGS = {

    # ==========================
    # SETPOINT
    # ==========================

    "fil_time": "NEW_HDC.SP1",
    "dra_time": "NEW_HDC.SP2",
    "dil_time": "NEW_HDC.SP3",

    # ==========================
    # COMMAND
    # ==========================

    # Single command:
    #   1 = START / RUN
    #   0 = STOP
    "cmd_start": "NEW_HDC.STT",
    

    # RESET:
    #   1 = RESET
    "cmd_reset": "NEW_HDC.RST",

    # ==========================
    # ACTUAL SEQUENCE TIMER (REAL / seconds)
    # ==========================

    # Actual elapsed time of each active sequence.
    # 0.0 when the corresponding sequence is not active.
    "fil_actual": "NEW_HDC.OU1",
    "dra_actual": "NEW_HDC.OU2",
    "dil_actual": "NEW_HDC.OU3",

    # ==========================
    # SEQUENCE INDICATION
    # ==========================

    "fil_seq": "NEW_HDC.FIL",
    "dra_seq": "NEW_HDC.DRA",
    "dil_seq": "NEW_HDC.DIL",

    # ==========================
    # VALVE LIMIT SWITCH
    # ==========================

    "main_valve_limit_open": "NEW_HDC_MAIN.LSO",
    "drain_valve_limit_open": "NEW_HDC_DRAIN.LSO",
    "dill_valve_limit_open": "NEW_HDC_DILL.LSO",

    # ==========================
    # VALVE OPEN COMMAND
    # ==========================

    "main_valve_cmd_open": "NEW_HDC.AO1",
    "drain_valve_cmd_open": "NEW_HDC.AO2",
    "dill_valve_cmd_open": "NEW_HDC.AO3",

    # ==========================
    # VALVE CLOSE COMMAND
    # ==========================

    "main_valve_cmd_close": "NEW_HDC.AC1",
    "drain_valve_cmd_close": "NEW_HDC.AC2",
    "dill_valve_cmd_close": "NEW_HDC.AC3",

    # ==========================
    # VALVE AUTO MODE
    # ==========================

    "main_valve_auto": "NEW_HDC_MAIN.MDE",
    "drain_valve_auto": "NEW_HDC_DRAIN.MDE",
    "dill_valve_auto": "NEW_HDC_DILL.MDE",

    # ==========================
    # PROGRAM SAFETY / WATCHDOG
    # ==========================

    # Python heartbeat toggles 0/1 periodically.
    # DCS watchdog monitors that STA continues changing.
    "program_safety_status": "NEW_HDC.STA",

    # Python internal fault:
    #   0 = normal
    #   1 = fault
    "signal_fault": "NEW_HDC.FLT",

}


HDC_TAGS = {
    tag: f"{DCS_PREFIX}{name}"
    for tag, name in DCS_TAGS.items()
}
