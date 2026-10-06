# safety/interlock.py


class HDCInterlock:

    def __init__(self):

        self.fault = False
        self.fault_reason = None

    # ==================================================
    # SET FAULT
    # ==================================================

    def set_fault(self, reason):

        self.fault = True
        self.fault_reason = reason

    # ==================================================
    # RESET
    # ==================================================

    def reset(self):

        self.fault = False
        self.fault_reason = None

    # ==================================================
    # AUTO MODE
    # ==================================================

    def check_auto_mode(self, data):

        return (
            bool(data["main_valve_auto"])
            and
            bool(data["drain_valve_auto"])
            and
            bool(data["dill_valve_auto"])
        )

    # ==================================================
    # MAIN OPEN
    # ==================================================

    def check_main_open(self, data):

        return bool(
            data["main_valve_limit_open"]
        )

    # ==================================================
    # DRAIN OPEN
    # ==================================================

    def check_drain_open(self, data):

        return bool(
            data["drain_valve_limit_open"]
        )

    # ==================================================
    # DILUTION OPEN
    # ==================================================

    def check_dilution_open(self, data):

        return bool(
            data["dill_valve_limit_open"]
        )
