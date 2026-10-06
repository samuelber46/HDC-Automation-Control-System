# utils/logger.py
#
# Console logger / dashboard for HDC Automation.
# Requires: colorama

from datetime import datetime
from colorama import init, Fore, Style

init(autoreset=True)

RESET = Style.RESET_ALL

CYAN = Fore.CYAN
GREEN = Fore.GREEN
YELLOW = Fore.YELLOW
BLUE = Fore.BLUE
MAGENTA = Fore.MAGENTA
RED = Fore.RED
WHITE = Fore.WHITE
GRAY = Fore.LIGHTBLACK_EX

BOLD = Style.BRIGHT

WIDTH = 78


def clear_console():
    """Clear the visible terminal without spawning a shell process."""
    print("\033[2J\033[H", end="")


def _runtime_clear():
    """Clear the live console before every runtime message/dashboard refresh."""
    clear_console()


def _now():
    return datetime.now().strftime("%H:%M:%S")


def _line(char="─", color=WHITE):
    print(color + char * WIDTH + RESET)


def _title(text, color=CYAN):
    print(color + BOLD + text.center(WIDTH) + RESET)


def _kv(label, value, value_color=WHITE, width=18):
    print(
        WHITE + f"  {label:<{width}}: " + RESET
        + value_color + BOLD + str(value) + RESET
    )


def _pill(label, value, color):
    return color + BOLD + f" {label}: {value} " + RESET


def _state_color(state_name):
    return {
        "IDLE": WHITE,
        "FILLING": CYAN,
        "DRAINING": YELLOW,
        "DILUTION": BLUE,
        "FAULT": RED + BOLD,
    }.get(state_name, WHITE)


def _bool_text(value):
    return "ON" if bool(value) else "OFF"


def _bool_color(value, on_color=GREEN):
    return on_color if bool(value) else GRAY


# ==========================================================
# STARTUP / HEADER
# ==========================================================

def startup(write_enable, loop_interval, valve_timeout):
    print()
    _line("═", CYAN)
    _title("HDC AUTOMATION CONTROL SYSTEM", CYAN)
    _title("HIGH DENSITY CLEANER - AUTOMATIC SEQUENCE", WHITE)
    _line("─", CYAN)

    print(
        GRAY + f"  START TIME : {_now()}" + RESET
    )
    _kv("WRITE ENABLE", "ENABLED" if write_enable else "DISABLED",
        GREEN if write_enable else YELLOW)
    _kv("LOOP INTERVAL", f"{loop_interval:.3f} s", CYAN)
    _kv("VALVE TIMEOUT", f"{valve_timeout:.1f} s", YELLOW)

    _line("═", CYAN)
    print()


def info(message):
    _runtime_clear()
    print(GRAY + f"[{_now()}]" + RESET + CYAN + f" [INFO] {message}" + RESET)


def state(old_state, new_state):
    _runtime_clear()
    color = _state_color(new_state)
    print()
    _line("─", MAGENTA)
    print(
        GRAY + f"[{_now()}] " + RESET
        + MAGENTA + "STATE CHANGE  " + RESET
        + WHITE + f"{old_state}" + RESET
        + MAGENTA + "  →  " + RESET
        + color + BOLD + f"{new_state}" + RESET
    )
    _line("─", MAGENTA)


def write(tag_name, value):
    _runtime_clear()
    print(
        GRAY + f"[{_now()}]" + RESET
        + GREEN + " [WRITE] " + RESET
        + WHITE + f"{tag_name:<28}" + RESET
        + GREEN + f" = {value}" + RESET
    )


def write_disabled(tag_name, value):
    _runtime_clear()
    print(
        GRAY + f"[{_now()}]" + RESET
        + YELLOW + " [WRITE OFF] " + RESET
        + WHITE + f"{tag_name:<28}" + RESET
        + YELLOW + f" = {value}" + RESET
    )


def indication(tag_name, value):
    _runtime_clear()
    print(
        GRAY + f"[{_now()}]" + RESET
        + BLUE + " [INDICATION] " + RESET
        + WHITE + f"{tag_name:<28}" + RESET
        + BLUE + f" = {value}" + RESET
    )


def indication_disabled(tag_name, value):
    _runtime_clear()
    print(
        GRAY + f"[{_now()}]" + RESET
        + YELLOW + " [INDICATION OFF] " + RESET
        + WHITE + f"{tag_name:<24}" + RESET
        + YELLOW + f" = {value}" + RESET
    )


def warning(message):
    _runtime_clear()
    print(
        GRAY + f"[{_now()}]" + RESET
        + YELLOW + BOLD + f" [WARNING] {message}" + RESET
    )


def error(message):
    _runtime_clear()
    print(
        GRAY + f"[{_now()}]" + RESET
        + RED + BOLD + f" [ERROR] {message}" + RESET
    )


def main_loop_error(message):
    _runtime_clear()
    print(
        GRAY + f"[{_now()}]" + RESET
        + RED + BOLD + f" [MAIN LOOP ERROR] {message}" + RESET
    )


def valve_open_command(valve_name):
    _runtime_clear()
    print(
        GRAY + f"[{_now()}]" + RESET
        + CYAN + " [VALVE OPEN] " + RESET
        + WHITE + f"{valve_name:<10}" + RESET
        + CYAN + " command sent - waiting LSO=1" + RESET
    )


def valve_open_response(valve_name, elapsed):
    _runtime_clear()
    print(
        GRAY + f"[{_now()}]" + RESET
        + GREEN + BOLD + " [VALVE LSO] " + RESET
        + WHITE + f"{valve_name:<10}" + RESET
        + GREEN + BOLD + f" OPEN confirmed | response time = {elapsed:.3f} s" + RESET
    )


# ==========================================================
# FAULT
# ==========================================================

def fault(reason, fault_time=None, fault_code=None):
    _runtime_clear()
    print()
    _line("═", RED)
    _title("HDC FAULT", RED)
    _line("─", RED)

    if fault_code:
        _kv("FAULT CODE", fault_code, RED)
    if fault_time:
        _kv("FAULT TIME", fault_time, RED)
    _kv("REASON", reason or "UNKNOWN", RED)

    _line("═", RED)
    print()


def fault_status(state_name, reason, fault_time=None, fault_code=None):
    _runtime_clear()
    print()
    _line("═", RED)
    _title("HDC FAULT ACTIVE", RED)
    _line("─", RED)
    _kv("STATE", state_name, RED)
    _kv("FAULT CODE", fault_code or "-", RED)
    _kv("FAULT TIME", fault_time or "-", RED)
    _kv("REASON", reason or "-", RED)
    _line("═", RED)


# ==========================================================
# LIVE STATUS DASHBOARD
# ==========================================================

def status(
    state_name,
    start,
    reset,
    main_lso,
    drain_lso,
    dill_lso,
    timer_status=None,
    valve_response=None,
):
    _runtime_clear()
    """Compact live HDC dashboard printed once per main loop."""

    sc = _state_color(state_name)

    print()
    _line("─", CYAN)
    print(
        GRAY + f"  {_now()}  |  HDC LIVE STATUS" + RESET
    )
    _line("─", CYAN)

    print(
        "  "
        + WHITE + "STATE " + RESET
        + sc + BOLD + f"{state_name:<10}" + RESET
        + _pill("CMD", _bool_text(start), _bool_color(start, GREEN))
        + _pill("RESET", _bool_text(reset), _bool_color(reset, YELLOW))
    )

    print()
    print(WHITE + "  VALVE LIMIT SWITCH" + RESET)
    print(
        "  "
        + _pill("MAIN", _bool_text(main_lso), _bool_color(main_lso, GREEN))
        + _pill("DRAIN", _bool_text(drain_lso), _bool_color(drain_lso, YELLOW))
        + _pill("DILUTION", _bool_text(dill_lso), _bool_color(dill_lso, BLUE))
    )

    # ----------------------------------------------------------
    # VALVE OPEN RESPONSE TIME
    # ----------------------------------------------------------

    print()
    print(WHITE + "  VALVE OPEN RESPONSE" + RESET)
    print(
        GRAY + "  "
        + f"{'VALVE':<12} {'OPEN → LSO':>14}"
        + RESET
    )

    valve_response = valve_response or {}
    for valve_name, color in (("MAIN", CYAN), ("DRAIN", YELLOW), ("DILUTION", BLUE)):
        response = valve_response.get(valve_name)
        waiting = response is None and valve_name in (
            "MAIN", "DRAIN", "DILUTION"
        )
        text_value = f"{response:.3f} s" if response is not None else "-"
        print(
            "  " + color + f"{valve_name:<12}" + RESET
            + GREEN + f"{text_value:>14}" + RESET
        )

    # ----------------------------------------------------------
    # SEQUENCE TIMER / COUNTDOWN
    # ----------------------------------------------------------

    print()
    print(WHITE + "  SEQUENCE TIMER" + RESET)
    print(
        GRAY
        + "  "
        + f"{'SEQUENCE':<12} {'SETPOINT':>12} {'ACTUAL':>12} {'COUNTDOWN':>12} {'STATUS':>12}"
        + RESET
    )

    timer_status = timer_status or {}
    timer_rows = (
        ("FILLING", "fil", CYAN),
        ("DRAINING", "dra", YELLOW),
        ("DILUTION", "dil", BLUE),
    )

    for name, key, color in timer_rows:
        timer = timer_status.get(key, {})
        setpoint = float(timer.get("setpoint", 0.0))
        actual = float(timer.get("actual", 0.0))
        remaining = float(timer.get("remaining", 0.0))
        active = actual > 0.0 or state_name == name
        status_text = "RUNNING" if state_name == name else "IDLE"
        status_color = color if state_name == name else GRAY

        print(
            "  "
            + color + f"{name:<12}" + RESET
            + WHITE + f" {setpoint:>10.1f} s" + RESET
            + color + f" {actual:>10.1f} s" + RESET
            + YELLOW + f" {remaining:>10.1f} s" + RESET
            + status_color + BOLD + f" {status_text:>12}" + RESET
        )

    print()
    _line("─", CYAN)



def setpoint_diagnostics(values, qualities=None):
    """Print initial OPC setpoint Value/Quality diagnostics."""
    qualities = qualities or {}
    _runtime_clear()
    print()
    _line("─", CYAN)
    _title("OPC SETPOINT DIAGNOSTICS", CYAN)
    _line("─", CYAN)
    print(WHITE + f"  {'SETPOINT':<10} {'TAG':<18} {'VALUE':>12} {'QUALITY':>12}" + RESET)
    for alias, tag, key in (
        ("SP1", "NEW_HDC.SP1", "fil_time"),
        ("SP2", "NEW_HDC.SP2", "dra_time"),
        ("SP3", "NEW_HDC.SP3", "dil_time"),
    ):
        value = values.get(key)
        quality = qualities.get(key)
        q_text = str(quality) if quality is not None else "-"
        q_color = GREEN if quality in (192, 0xC0) else YELLOW
        print(
            "  " + CYAN + f"{alias:<10}" + RESET
            + WHITE + f"{tag:<18}" + RESET
            + WHITE + f"{str(value):>12}" + RESET
            + q_color + f"{q_text:>12}" + RESET
        )
    print()
    print(GRAY + "  OPC Quality 192 (0xC0) = GOOD. The process value is read from Value, not Quality." + RESET)
    _line("─", CYAN)

def opc_connecting(server_name):
    _runtime_clear()
    print(GRAY + f"[{_now()}]" + RESET + CYAN + BOLD + f" [OPC] Connecting → {server_name}" + RESET)


def opc_connected():
    _runtime_clear()
    print(GRAY + f"[{_now()}]" + RESET + GREEN + BOLD + " [OPC] ✓ Connected successfully" + RESET)


def opc_loaded(count):
    _runtime_clear()
    print(GRAY + f"[{_now()}]" + RESET + GREEN + BOLD + f" [OPC] ✓ {count} tags loaded" + RESET)


def opc_closing():
    _runtime_clear()
    print(GRAY + f"[{_now()}]" + RESET + YELLOW + " [OPC] Closing connection..." + RESET)


def hdc_initialized():
    _runtime_clear()
    print(GRAY + f"[{_now()}]" + RESET + GREEN + BOLD + " [HDC] ✓ Sequence initialized" + RESET)


def hdc_waiting_start():
    _runtime_clear()
    print(GRAY + f"[{_now()}]" + RESET + CYAN + " [HDC] Waiting for START command..." + RESET)


def hdc_command(command):
    _runtime_clear()
    print(GRAY + f"[{_now()}]" + RESET + CYAN + BOLD + f" [HDC] {command}" + RESET)
