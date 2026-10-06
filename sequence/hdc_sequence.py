# sequence/hdc_sequence.py

import time
import re
from enum import Enum

from safety.interlock import HDCInterlock
from utils import logger


class HDCState(Enum):

    IDLE = 0
    FILLING = 1
    DRAINING = 2
    DILUTION = 3
    FAULT = 4


class HDCSequence:

    def __init__(
        self,
        opc,
        tags,
        enable_write=True,
        valve_open_timeout=10.0
    ):

        self.opc = opc
        self.tags = tags

        self.enable_write = enable_write

        self.valve_open_timeout = (
            valve_open_timeout
        )

        # ------------------------------------------
        # CURRENT STATE
        # ------------------------------------------

        self.state = HDCState.IDLE

        # ------------------------------------------
        # STATE TIMER
        # ------------------------------------------

        self.state_start_time = (
            time.monotonic()
        )

        # ------------------------------------------
        # VALVE OPEN RESPONSE TIMER
        # ------------------------------------------
        # Measures real elapsed time from OPEN command to LSO=1.
        self.valve_open_command_time = {
            "MAIN": None,
            "DRAIN": None,
            "DILUTION": None,
        }
        self.valve_lso_waiting = {
            "MAIN": False,
            "DRAIN": False,
            "DILUTION": False,
        }
        self.valve_open_response = {
            "MAIN": None,
            "DRAIN": None,
            "DILUTION": None,
        }

        # ------------------------------------------
        # VALVE OPENING TIMEOUT TIMER
        # ------------------------------------------

        self.valve_wait_start = None

        # ------------------------------------------
        # SAFETY / INTERLOCK
        # ------------------------------------------

        self.interlock = HDCInterlock()

        # ------------------------------------------
        # RESET EDGE DETECTION
        #
        # cmd_start is a LEVEL command:
        #   1 = START / RUN
        #   0 = STOP
        # ------------------------------------------
        # ------------------------------------------

        self.previous_reset = False

        # ------------------------------------------
        # PREVENT REPEATED OPC WRITES
        # ------------------------------------------

        self.last_commands = {}

        # ------------------------------------------
        # PREVENT REPEATED INDICATION WRITES
        # ------------------------------------------

        self.last_indications = {}

        # ------------------------------------------
        # FAULT INFORMATION
        # ------------------------------------------

        self.fault_reason = None
        self.fault_code = None
        self.fault_time = None

        # DCS fault indication:
        #   0 = normal
        #   1 = HDC sequence fault
        self.last_fault_signal = None

    # ==================================================
    # TIME
    # ==================================================

    def elapsed(self):

        return (
            time.monotonic()
            - self.state_start_time
        )

    def timer_status(self, data):
        """Return live actual/countdown values for the three sequence steps.

        Actual time is elapsed time since the current HDC state started.
        Countdown is the remaining time to the configured setpoint.
        Only the active sequence carries a non-zero value.
        """

        setpoints = {
            "FILLING": self.safe_float(data.get("fil_time", 0), "fil_time"),
            "DRAINING": self.safe_float(data.get("dra_time", 0), "dra_time"),
            "DILUTION": self.safe_float(data.get("dil_time", 0), "dil_time"),
        }

        states = {
            "FILLING": "fil",
            "DRAINING": "dra",
            "DILUTION": "dil",
        }

        result = {
            "fil": {"actual": 0.0, "remaining": 0.0, "setpoint": setpoints["FILLING"]},
            "dra": {"actual": 0.0, "remaining": 0.0, "setpoint": setpoints["DRAINING"]},
            "dil": {"actual": 0.0, "remaining": 0.0, "setpoint": setpoints["DILUTION"]},
        }

        state_name = self.state.name
        if state_name in states:
            key = states[state_name]
            actual = max(0.0, float(self.elapsed()))
            setpoint = max(0.0, float(setpoints[state_name]))
            remaining = max(0.0, setpoint - actual)
            result[key] = {
                "actual": actual,
                "remaining": remaining,
                "setpoint": setpoint,
            }

        return result

    # ==================================================
    # CHANGE STATE
    # ==================================================

    def change_state(self, new_state):

        if self.state == new_state:
            return

        old_state = self.state

        self.state = new_state

        self.state_start_time = (
            time.monotonic()
        )

        self.valve_wait_start = None

        logger.state(
            old_state.name,
            new_state.name
        )

        self.update_sequence_indication()

    # ==================================================
    # RISING EDGE
    # ==================================================

    @staticmethod
    def rising_edge(current, previous):

        return (
            bool(current)
            and not bool(previous)
        )

    # ==================================================
    # FAULT CODE
    # ==================================================

    @staticmethod
    def make_fault_code(reason):

        """
        Generate a readable fault code from
        the first part of the reason.

        Examples:
            MAIN_VALVE_OPEN_TIMEOUT
            INVALID_SETPOINT
            OPC_WRITE_ERROR
        """

        if not reason:
            return "UNKNOWN_FAULT"

        code_source = str(reason).split(":", 1)[0]

        code = re.sub(
            r"[^A-Za-z0-9]+",
            "_",
            code_source
        )

        code = code.strip("_").upper()

        return code or "UNKNOWN_FAULT"

    # ==================================================
    # OPC WRITE
    # ==================================================

    def write(
        self,
        tag_name,
        value,
        force=False
    ):

        value = int(bool(value))

        # Avoid repeated writes
        if not force:

            if (
                tag_name in self.last_commands
                and self.last_commands[tag_name] == value
            ):
                return True

        if not self.enable_write:

            logger.write_disabled(
                tag_name,
                value
            )

            return True

        try:

            # IMPORTANT:
            # OPCClient uses alias names, not full
            # DCS tag names.
            self.opc.write(
                tag_name,
                value
            )

            self.last_commands[tag_name] = value

            logger.write(
                tag_name,
                value
            )

            return True

        except Exception as e:

            logger.error(
                f"WRITE ERROR {tag_name}: {repr(e)}"
            )

            self.enter_fault(
                f"OPC_WRITE_ERROR: "
                f"Failed to write {tag_name}: {repr(e)}"
            )

            return False

    # ==================================================
    # ACTUAL SEQUENCE TIMER
    # ==================================================

    def update_actual_timer(self):

        # The sequence timer uses the same state_start_time
        # that controls the state transition. Values are REAL
        # seconds and are written to the DCS every main-loop cycle.
        # Only the active sequence has a non-zero value.
        elapsed = max(0.0, float(self.elapsed()))

        actual_timers = {
            "fil_actual": elapsed if self.state == HDCState.FILLING else 0.0,
            "dra_actual": elapsed if self.state == HDCState.DRAINING else 0.0,
            "dil_actual": elapsed if self.state == HDCState.DILUTION else 0.0,
        }

        for tag_name, value in actual_timers.items():

            if not self.enable_write:
                logger.indication_disabled(tag_name, value)
                continue

            try:
                # Do NOT use write(), because write() is intentionally
                # for digital commands and converts values to 0/1.
                self.opc.write(tag_name, float(value))

            except Exception as e:

                logger.error(
                    f"ACTUAL TIMER WRITE ERROR "
                    f"{tag_name}: {repr(e)}"
                )

                if self.state != HDCState.FAULT:
                    self.enter_fault(
                        f"OPC_ACTUAL_TIMER_WRITE_ERROR: "
                        f"Failed to write {tag_name}: {repr(e)}"
                    )
                    return

    # ==================================================
    # SEQUENCE INDICATION
    # ==================================================

    def update_sequence_indication(self):

        indications = {

            "fil_seq":
                self.state == HDCState.FILLING,

            "dra_seq":
                self.state == HDCState.DRAINING,

            "dil_seq":
                self.state == HDCState.DILUTION,

        }

        for tag_name, value in indications.items():

            value = int(bool(value))

            if (
                tag_name in self.last_indications
                and self.last_indications[tag_name] == value
            ):
                continue

            if not self.enable_write:

                logger.indication_disabled(
                    tag_name,
                    value
                )

                self.last_indications[tag_name] = value

                continue

            try:

                self.opc.write(
                    tag_name,
                    value
                )

                self.last_indications[tag_name] = value

                logger.indication(
                    tag_name,
                    value
                )

            except Exception as e:

                logger.error(
                    f"INDICATION ERROR "
                    f"{tag_name}: {repr(e)}"
                )

                # Do not recursively call enter_fault()
                # from indication failure while state
                # transitions are already in progress.

                if self.state != HDCState.FAULT:
                    self.enter_fault(
                        f"OPC_INDICATION_WRITE_ERROR: "
                        f"Failed to write {tag_name}: {repr(e)}"
                    )

    # ==================================================
    # VALVE LSO RESPONSE TIME
    # ==================================================

    def _start_valve_open_response(self, valve_name, command_ok):
        if not command_ok:
            return

        self.valve_open_command_time[valve_name] = time.monotonic()
        self.valve_lso_waiting[valve_name] = True
        self.valve_open_response[valve_name] = None

        logger.valve_open_command(valve_name)

    def _stop_valve_open_response(self, valve_name):
        if not self.valve_lso_waiting[valve_name]:
            return

        start = self.valve_open_command_time[valve_name]
        if start is None:
            return

        elapsed = max(0.0, time.monotonic() - start)
        self.valve_open_response[valve_name] = elapsed
        self.valve_lso_waiting[valve_name] = False
        self.valve_open_command_time[valve_name] = None

        logger.valve_open_response(valve_name, elapsed)

    def _reset_valve_open_response(self, valve_name):
        self.valve_open_command_time[valve_name] = None
        self.valve_lso_waiting[valve_name] = False
        self.valve_open_response[valve_name] = None

    def update_valve_lso_response(self, data):
        lso_values = {
            "MAIN": bool(data.get("main_valve_limit_open", 0)),
            "DRAIN": bool(data.get("drain_valve_limit_open", 0)),
            "DILUTION": bool(data.get("dill_valve_limit_open", 0)),
        }

        for valve_name, lso in lso_values.items():
            if lso:
                self._stop_valve_open_response(valve_name)

    # ==================================================
    # MAIN VALVE
    # ==================================================

    def main_open(self):

        command_ok = self.write(
            "main_valve_cmd_open",
            1
        )

        self.write(
            "main_valve_cmd_close",
            0
        )

        self._start_valve_open_response("MAIN", command_ok)

    def main_close(self):

        self.write(
            "main_valve_cmd_open",
            0
        )

        self.write(
            "main_valve_cmd_close",
            1
        )

        self._reset_valve_open_response("MAIN")

    # ==================================================
    # DRAIN VALVE
    # ==================================================

    def drain_open(self):

        command_ok = self.write(
            "drain_valve_cmd_open",
            1
        )

        self.write(
            "drain_valve_cmd_close",
            0
        )

        self._start_valve_open_response("DRAIN", command_ok)

    def drain_close(self):

        self.write(
            "drain_valve_cmd_open",
            0
        )

        self.write(
            "drain_valve_cmd_close",
            1
        )

        self._reset_valve_open_response("DRAIN")

    # ==================================================
    # DILUTION VALVE
    # ==================================================

    def dilution_open(self):

        command_ok = self.write(
            "dill_valve_cmd_open",
            1
        )

        self.write(
            "dill_valve_cmd_close",
            0
        )

        self._start_valve_open_response("DILUTION", command_ok)

    def dilution_close(self):

        self.write(
            "dill_valve_cmd_open",
            0
        )

        self.write(
            "dill_valve_cmd_close",
            1
        )

        self._reset_valve_open_response("DILUTION")

    # ==================================================
    # ALL VALVES CLOSE
    # ==================================================

    def all_valves_close(self):

        self.main_close()
        self.drain_close()
        self.dilution_close()

    # ==================================================
    # START VALVE WAIT
    # ==================================================

    def start_valve_wait(self):

        if self.valve_wait_start is None:

            self.valve_wait_start = (
                time.monotonic()
            )

            logger.info(
                "Waiting for valve OPEN LSO..."
            )

    # ==================================================
    # VALVE TIMEOUT
    # ==================================================

    def valve_timeout(self):

        if self.valve_wait_start is None:
            return False

        return (
            time.monotonic()
            - self.valve_wait_start
            >= self.valve_open_timeout
        )

    # ==================================================
    # DCS FAULT INDICATION
    # ==================================================

    def update_fault_indication(self, fault, force=False):

        """Write the HDC fault state to NEW_HDC.FLT.

        This signal is a boolean/DI indication:
            0 = normal
            1 = fault

        The write is deliberately handled separately from write(),
        because write() is intended for command outputs and applies
        digital conversion.  This method also avoids recursively
        calling enter_fault() if the FLT write itself fails.
        """

        value = int(bool(fault))

        if (
            not force
            and self.last_fault_signal is not None
            and self.last_fault_signal == value
        ):
            return True

        if not self.enable_write:
            logger.write_disabled(
                "signal_fault",
                value
            )
            self.last_fault_signal = value
            return True

        try:
            self.opc.write(
                "signal_fault",
                value
            )

            self.last_fault_signal = value

            logger.write(
                "signal_fault",
                value
            )

            return True

        except Exception as e:

            logger.error(
                f"FAULT INDICATION WRITE ERROR: {repr(e)}"
            )

            # Do NOT call enter_fault() here.  Otherwise an OPC
            # failure while writing FLT would recursively generate
            # another fault.
            return False

    # ==================================================
    # ENTER FAULT
    # ==================================================

    def enter_fault(self, reason):

        # Avoid repeated FAULT handling
        if self.state == HDCState.FAULT:
            return

        self.fault_reason = str(reason)

        self.fault_code = (
            self.make_fault_code(
                self.fault_reason
            )
        )

        self.fault_time = time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        logger.fault(
            reason=self.fault_reason,
            fault_time=self.fault_time,
            fault_code=self.fault_code
        )

        self.interlock.set_fault(
            self.fault_reason
        )

        # Notify DCS that HDC is in FAULT.
        self.update_fault_indication(
            True,
            force=True
        )

        # Go to FAULT
        self.change_state(
            HDCState.FAULT
        )

        # Close all valves
        self.all_valves_close()

    # ==================================================
    # RESET
    # ==================================================

    def reset(self):

        logger.info(
            "RESET command received"
        )

        self.interlock.reset()

        # Clear fault information
        self.fault_reason = None
        self.fault_code = None
        self.fault_time = None

        # Clear DCS fault indication only after a valid RESET.
        self.update_fault_indication(
            False,
            force=True
        )

        self.valve_wait_start = None

        self.change_state(
            HDCState.IDLE
        )

        # Make sure all sequence indications and actual timers are OFF/zero.
        self.update_sequence_indication()
        self.update_actual_timer()

    # ==================================================
    # STOP
    # ==================================================

    def stop(self):

        logger.info(
            "STOP command received"
        )

        # Close all valves
        self.all_valves_close()

        # Clear timer
        self.valve_wait_start = None

        # Return IDLE
        self.change_state(
            HDCState.IDLE
        )

        # Immediately clear actual sequence timers.
        self.update_actual_timer()

    # ==================================================
    # MAIN RUN
    # ==================================================

    def run(self, data):

        # --------------------------------------------------
        # RESET EVENT
        # --------------------------------------------------

        reset_event = self.rising_edge(
            data["cmd_reset"],
            self.previous_reset
        )

        self.previous_reset = (
            bool(data["cmd_reset"])
        )

        if reset_event:

            if self.state == HDCState.FAULT:
                self.reset()

        # --------------------------------------------------
        # ACTUAL TIMER OUTPUT
        # --------------------------------------------------

        self.update_actual_timer()

        # --------------------------------------------------
        # SINGLE START / STOP COMMAND
        #
        # cmd_start = 1 -> START / RUN
        # cmd_start = 0 -> STOP
        #
        # This is intentionally LEVEL based, not edge based.
        # Therefore a DCS command that stays at 1 keeps the
        # automatic HDC sequence running, while 0 immediately
        # stops the sequence.
        # --------------------------------------------------

        if not bool(data["cmd_start"]):

            # Do not clear a FAULT with the normal STOP command.
            # A FAULT still requires RESET.
            if self.state != HDCState.IDLE and self.state != HDCState.FAULT:

                self.stop()

            elif self.state == HDCState.IDLE:

                # Keep all valves in the safe CLOSE command
                # while waiting for cmd_start = 1.
                self.all_valves_close()

            elif self.state == HDCState.FAULT:

                self.fault(data)

            return

        # --------------------------------------------------
        # STATE MACHINE
        # --------------------------------------------------

        if self.state == HDCState.IDLE:

            self.idle(data)

        elif self.state == HDCState.FILLING:

            self.filling(data)

        elif self.state == HDCState.DRAINING:

            self.draining(data)

        elif self.state == HDCState.DILUTION:

            self.dilution(data)

        elif self.state == HDCState.FAULT:

            self.fault(data)

    # ==================================================
    # IDLE
    # ==================================================

    def idle(self, data):

        # cmd_start is a level command.
        # run() only calls idle() when cmd_start == 1.
        logger.info(
            "START command active"
        )

        # --------------------------------------------------
        # CHECK AUTO
        # --------------------------------------------------

        if not self.interlock.check_auto_mode(
            data
        ):

            self.enter_fault(
                "START_INTERLOCK: "
                "Cannot START because not all valves are AUTO"
            )

            return

        # --------------------------------------------------
        # START FILLING
        # --------------------------------------------------

        self.change_state(
            HDCState.FILLING
        )

        # --------------------------------------------------
        # INITIAL VALVE POSITION
        # --------------------------------------------------

        self.drain_close()
        self.dilution_close()
        self.main_open()

    # ==================================================
    # FILLING
    # ==================================================

    def filling(self, data):

        # --------------------------------------------------
        # AUTO CHECK
        # --------------------------------------------------

        if not self.interlock.check_auto_mode(
            data
        ):

            self.enter_fault(
                "VALVE_AUTO_LOST: "
                "One or more valves changed to MANUAL "
                "during FILLING"
            )

            return

        # --------------------------------------------------
        # MAIN VALVE OPEN CHECK
        # --------------------------------------------------

        main_open = (
            self.interlock.check_main_open(
                data
            )
        )

        if not main_open:

            self.start_valve_wait()

            if self.valve_timeout():

                self.enter_fault(
                    "MAIN_VALVE_OPEN_TIMEOUT: "
                    "Main valve did not reach LSO=1 "
                    f"within {self.valve_open_timeout:.1f} seconds"
                )

            return

        # --------------------------------------------------
        # MAIN VALVE OPEN
        # --------------------------------------------------

        self.valve_wait_start = None

        # --------------------------------------------------
        # FILL TIME
        # --------------------------------------------------

        try:

            fil_time = self.safe_float(
                data["fil_time"],
                "fil_time"
            )

        except ValueError as e:

            self.enter_fault(
                f"INVALID_SETPOINT: {e}"
            )

            return

        if fil_time <= 0:

            self.enter_fault(
                "INVALID_SETPOINT: "
                f"FILLING time = {fil_time}"
            )

            return

        if self.elapsed() >= fil_time:

            logger.info(
                "FILLING complete"
            )

            # Change state first
            self.change_state(
                HDCState.DRAINING
            )

            # Valve configuration
            self.main_close()
            self.dilution_close()
            self.drain_open()

    # ==================================================
    # DRAINING
    # ==================================================

    def draining(self, data):

        # --------------------------------------------------
        # AUTO CHECK
        # --------------------------------------------------

        if not self.interlock.check_auto_mode(
            data
        ):

            self.enter_fault(
                "VALVE_AUTO_LOST: "
                "One or more valves changed to MANUAL "
                "during DRAINING"
            )

            return

        # --------------------------------------------------
        # DRAIN VALVE OPEN CHECK
        # --------------------------------------------------

        drain_open = (
            self.interlock.check_drain_open(
                data
            )
        )

        if not drain_open:

            self.start_valve_wait()

            if self.valve_timeout():

                self.enter_fault(
                    "DRAIN_VALVE_OPEN_TIMEOUT: "
                    "Drain valve did not reach LSO=1 "
                    f"within {self.valve_open_timeout:.1f} seconds"
                )

            return

        self.valve_wait_start = None

        # --------------------------------------------------
        # DRAIN TIME
        # --------------------------------------------------

        try:

            dra_time = self.safe_float(
                data["dra_time"],
                "dra_time"
            )

        except ValueError as e:

            self.enter_fault(
                f"INVALID_SETPOINT: {e}"
            )

            return

        if dra_time <= 0:

            self.enter_fault(
                "INVALID_SETPOINT: "
                f"DRAINING time = {dra_time}"
            )

            return

        if self.elapsed() >= dra_time:

            logger.info(
                "DRAINING complete"
            )

            # Change state
            self.change_state(
                HDCState.DILUTION
            )

            # Valve configuration
            self.main_close()
            self.drain_close()
            self.dilution_open()

    # ==================================================
    # DILUTION
    # ==================================================

    def dilution(self, data):

        # --------------------------------------------------
        # AUTO CHECK
        # --------------------------------------------------

        if not self.interlock.check_auto_mode(
            data
        ):

            self.enter_fault(
                "VALVE_AUTO_LOST: "
                "One or more valves changed to MANUAL "
                "during DILUTION"
            )

            return

        # --------------------------------------------------
        # DILUTION VALVE OPEN CHECK
        # --------------------------------------------------

        dilution_open = (
            self.interlock.check_dilution_open(
                data
            )
        )

        if not dilution_open:

            self.start_valve_wait()

            if self.valve_timeout():

                self.enter_fault(
                    "DILUTION_VALVE_OPEN_TIMEOUT: "
                    "Dilution valve did not reach LSO=1 "
                    f"within {self.valve_open_timeout:.1f} seconds"
                )

            return

        self.valve_wait_start = None

        # --------------------------------------------------
        # DILUTION TIME
        # --------------------------------------------------

        try:

            dil_time = self.safe_float(
                data["dil_time"],
                "dil_time"
            )

        except ValueError as e:

            self.enter_fault(
                f"INVALID_SETPOINT: {e}"
            )

            return

        if dil_time <= 0:

            self.enter_fault(
                "INVALID_SETPOINT: "
                f"DILUTION time = {dil_time}"
            )

            return

        if self.elapsed() >= dil_time:

            logger.info(
                "DILUTION complete"
            )

            # Return to FILLING
            self.change_state(
                HDCState.FILLING
            )

            # Valve configuration
            self.drain_close()
            self.dilution_close()
            self.main_open()

    # ==================================================
    # FAULT STATE
    # ==================================================

    def fault(self, data):

        # --------------------------------------------------
        # Sequence indication remains OFF
        # --------------------------------------------------

        self.update_sequence_indication()

        # --------------------------------------------------
        # Keep all valves CLOSE
        # --------------------------------------------------

        self.all_valves_close()

        # --------------------------------------------------
        # Wait for RESET
        # --------------------------------------------------

        return

    # ==================================================
    # SAFE FLOAT
    # ==================================================

    @staticmethod
    def safe_float(value, tag_name="unknown"):

        try:

            return float(value)

        except (TypeError, ValueError) as e:

            raise ValueError(
                f"Invalid numeric value "
                f"for {tag_name}: "
                f"{value!r} "
                f"type={type(value)}"
            ) from e
