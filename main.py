# main.py

import time

from config.settings import (
    OPC_SERVER_NAME,
    OPC_GROUP_NAME,
    OPC_UPDATE_RATE,
    LOOP_INTERVAL,
    ENABLE_WRITE,
    VALVE_OPEN_TIMEOUT,
    PROGRAM_HEARTBEAT_INTERVAL,
    PROGRAM_WATCHDOG_TIMEOUT
)

from config.tags import HDC_TAGS

from opc.client import OPCClient, OPCConnectionError

from sequence.hdc_sequence import (
    HDCSequence,
    HDCState
)

from utils import logger
from safety.program_safety import ProgramSafety

# ==================================================
# DATA PREPARATION
# ==================================================

def prepare_data(raw):
    """
    Convert raw OPC values into data structure
    used by HDCSequence.
    """

    return {

        # ------------------------------------------
        # SETPOINT
        # ------------------------------------------

        "fil_time":
            raw.get("fil_time", 0),

        "dra_time":
            raw.get("dra_time", 0),

        "dil_time":
            raw.get("dil_time", 0),

        # ------------------------------------------
        # COMMAND
        # ------------------------------------------

        "cmd_start":
            raw.get("cmd_start", 0),

        "cmd_reset":
            raw.get("cmd_reset", 0),

        # ------------------------------------------
        # SEQUENCE
        # ------------------------------------------

        "fil_seq":
            raw.get("fil_seq", 0),

        "dra_seq":
            raw.get("dra_seq", 0),

        "dil_seq":
            raw.get("dil_seq", 0),

        # ------------------------------------------
        # MAIN VALVE
        # ------------------------------------------

        "main_valve_limit_open":
            raw.get(
                "main_valve_limit_open",
                0
            ),

        "main_valve_auto":
            raw.get(
                "main_valve_auto",
                0
            ),

        # ------------------------------------------
        # DRAIN VALVE
        # ------------------------------------------

        "drain_valve_limit_open":
            raw.get(
                "drain_valve_limit_open",
                0
            ),

        "drain_valve_auto":
            raw.get(
                "drain_valve_auto",
                0
            ),

        # ------------------------------------------
        # DILUTION VALVE
        # ------------------------------------------

        "dill_valve_limit_open":
            raw.get(
                "dill_valve_limit_open",
                0
            ),

        "dill_valve_auto":
            raw.get(
                "dill_valve_auto",
                0
            ),
    }


# ==================================================
# MAIN
# ==================================================

def main():

    logger.startup(
        write_enable=ENABLE_WRITE,
        loop_interval=LOOP_INTERVAL,
        valve_timeout=VALVE_OPEN_TIMEOUT
    )

    logger.info(
        f"[WATCHDOG] STA=NEW_HDC.STA | heartbeat={PROGRAM_HEARTBEAT_INTERVAL:.1f}s | "
        f"DCS timeout={PROGRAM_WATCHDOG_TIMEOUT:.1f}s"
    )

    # ==================================================
    # OPC
    # ==================================================

    opc = OPCClient(
        server_name=OPC_SERVER_NAME,
        group_name=OPC_GROUP_NAME,
        update_rate=OPC_UPDATE_RATE
    )

    try:

        # ------------------------------------------
        # CONNECT
        # ------------------------------------------

        opc.connect()

        # ------------------------------------------
        # ADD ALL TAGS
        # ------------------------------------------

        opc.add_items(
            HDC_TAGS
        )

        logger.opc_loaded(len(HDC_TAGS))

        # ==================================================
        # HDC SEQUENCE
        # ==================================================

        sequence = HDCSequence(
            opc=opc,
            tags=HDC_TAGS,
            enable_write=ENABLE_WRITE,
            valve_open_timeout=(
                VALVE_OPEN_TIMEOUT
            )
        )

        logger.hdc_initialized()

        # Read and display the initial setpoint Value + OPC Quality once.
        # This helps verify that SP1/SP2/SP3 are mapped correctly.
        try:
            diagnostic_raw = opc.read_all()
            logger.setpoint_diagnostics(
                values=diagnostic_raw,
                qualities={
                    "fil_time": opc.get_quality("fil_time"),
                    "dra_time": opc.get_quality("dra_time"),
                    "dil_time": opc.get_quality("dil_time"),
                },
            )
        except OPCConnectionError:
            logger.warning("Unable to read initial setpoint diagnostics; main loop will reconnect.")

        # ==================================================
        # PROGRAM WATCHDOG / HEARTBEAT
        # ==================================================

        program_safety = ProgramSafety(
            opc=opc,
            heartbeat_interval=PROGRAM_HEARTBEAT_INTERVAL
        )

        # Write the first heartbeat immediately so DCS can see that
        # Python has successfully initialized the OPC interface.
        program_safety.update_heartbeat(force=True)

        # Initialize the DCS fault indication.
        # The signal is TRUE only while the HDC sequence is in FAULT.
        sequence.update_fault_indication(
            False,
            force=True
        )

        logger.hdc_waiting_start()

        # ==================================================
        # MAIN LOOP
        # ==================================================

        while True:

            try:

                # --------------------------------------
                # OPC CONNECTION HEALTH / AUTO RECONNECT
                # --------------------------------------

                if not opc.connected:
                    logger.warning(
                        "OPC connection unavailable. Starting reconnect..."
                    )
                    opc.reconnect(HDC_TAGS)

                # --------------------------------------
                # READ OPC
                # --------------------------------------

                raw_data = (
                    opc.read_all()
                )

                # --------------------------------------
                # PREPARE DATA
                # --------------------------------------

                data = prepare_data(
                    raw_data
                )

                # --------------------------------------
                # VALVE OPEN RESPONSE TIME
                # --------------------------------------

                sequence.update_valve_lso_response(data)

                # --------------------------------------
                # RUN SEQUENCE
                # --------------------------------------

                sequence.run(
                    data
                )

                # --------------------------------------
                # PROGRAM WATCHDOG / HEARTBEAT
                # --------------------------------------

                # This is intentionally driven from the main loop.
                # If Python hangs and the loop stops executing, STA
                # stops toggling and the DCS watchdog can trip.
                program_safety.update_heartbeat()

                # --------------------------------------
                # DEBUG STATUS
                # --------------------------------------

                if sequence.state == HDCState.FAULT:

                    logger.fault_status(
                        state_name=sequence.state.name,
                        fault_code=sequence.fault_code,
                        reason=sequence.fault_reason,
                        fault_time=sequence.fault_time
                    )

                else:

                    logger.status(
                        state_name=sequence.state.name,
                        start=data["cmd_start"],
                        reset=data["cmd_reset"],
                        main_lso=data["main_valve_limit_open"],
                        drain_lso=data["drain_valve_limit_open"],
                        dill_lso=data["dill_valve_limit_open"],
                        timer_status=sequence.timer_status(data),
                        valve_response=sequence.valve_open_response
                    )

                # --------------------------------------
                # LOOP
                # --------------------------------------

                time.sleep(
                    LOOP_INTERVAL
                )

            except OPCConnectionError as e:

                logger.warning(
                    f"OPC connection lost: {e}"
                )

                # Do not recreate COM objects inside the normal cycle.
                # OPCClient.reconnect() performs a complete COM cleanup
                # and rebuilds the OPC group/items before retrying.
                try:
                    opc.reconnect(HDC_TAGS)
                except Exception as reconnect_error:
                    logger.error(
                        f"OPC reconnect failed: {repr(reconnect_error)}"
                    )
                    time.sleep(2.0)

            except Exception as e:

                logger.main_loop_error(
                    repr(e)
                )

                # Jangan langsung crash.
                # Tunggu sebentar kemudian coba loop kembali.

                time.sleep(1.0)

    except KeyboardInterrupt:

        print(
            "\n[MAIN] "
            "Program stopped by user."
        )

    except Exception as e:

        print(
            f"\n[MAIN ERROR] "
            f"{repr(e)}"
        )

    finally:

        print(
            "[MAIN] Closing OPC..."
        )

        # Always release OPC Automation / COM resources when the
        # process exits, including KeyboardInterrupt and startup errors.
        try:
            opc.close()
        except Exception as e:
            print(
                f"[MAIN] OPC cleanup error: {repr(e)}"
            )

        opc.close()

        print(
            "[MAIN] Program terminated."
        )


# ==================================================
# ENTRY POINT
# ==================================================

if __name__ == "__main__":

    main()
