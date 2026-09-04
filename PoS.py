"""
================================================================================
  THESIS: Quantitative Analysis and Optimization of Blockchain-Induced
          Latency in Real-Time Embedded Flight Control Systems
  Author : Nabil / merajpi
  Hardware: Raspberry Pi 5 (Ubuntu) + Pixhawk 2.4.8
  Chain  : Private Ethereum PoS (Geth --dev, SimulatedBeacon, chainId=1337,
           ~12s slot time)
  Geth   : v1.13.15-stable  |  web3.py v6+
  Mode   : Fire-and-forget TX submission (like the PoA script).
           T_submission (~5-15ms) is measured inline; T_confirmation
           (~12-24s) is tracked asynchronously by a background thread.
           Both metrics are logged to CSV for complete thesis analysis.
================================================================================
"""

import time
import curses
import csv
import os
import sys
import threading
import queue

import subprocess
import statistics
from datetime import datetime
from collections import deque

from pymavlink import mavutil
from web3 import Web3

# ============================================================
#  CONFIGURATION — edit only this section if needed
# ============================================================
DEVICE           = '/dev/ttyAMA0'   # MAVLink serial port
BAUD             = 921600           # Serial baud rate
DISPLAY_INTERVAL = 0.1              # Terminal refresh rate (seconds)
TX_INTERVAL      = 2.0              # TX submit interval (fire-and-forget, no need
                                     # to wait for slot; matches PoA interval)

RPC_URL          = 'http://127.0.0.1:8545'
CHAIN_ID         = 1337
MY_ADDRESS       = "0x55fa363e65c1cd9172F8D1E34FFD4A35A52f3998"

LOG_DIR          = "/home/merajpi/Nabil/logs"
WINDOW_SIZE      = 50                # Rolling stats window (messages)

# ============================================================
#  SETUP  (PoS: no PoA middleware — dev-mode blocks carry no
#  Clique extraData, so ExtraDataToPOAMiddleware is not needed)
# ============================================================
w3 = Web3(Web3.HTTPProvider(RPC_URL))

os.makedirs(LOG_DIR, exist_ok=True)
timestamp_str = datetime.now().strftime("%H%M-%d%m%Y")
log_filename  = os.path.join(LOG_DIR, f"latency_pos_ff_{timestamp_str}.csv")

telemetry_gaps = deque(maxlen=WINDOW_SIZE)

# CSV schema: compatible with the PoA script, plus extra confirmation columns.
# "Blockchain_TX_Latency_ms" = T_submission (fire-and-forget, what the flight
#   controller actually experiences — the main-loop blocking time).
# "Confirmation_Latency_ms"  = T_confirmation (background thread, for thesis).
CSV_HEADER = [
    "Timestamp",
    "Telemetry_Gap_ms",
    "Telemetry_Mean_Gap_ms",
    "Telemetry_Max_Gap_ms",
    "Telemetry_Std_Gap_ms",
    "Blockchain_TX_Latency_ms",
    "Confirmation_Latency_ms",
    "TX_Count",
    "Block_Number",
    "Blockchain_Status",
    "Altitude_m",
    "Speed_mps",
    "Heading_deg",
    "Latitude",
    "Longitude",
    "Voltage_V",
    "Current_A",
    "Satellites",
]

# ============================================================
#  SHARED BLOCKCHAIN STATE (written by worker thread, read by UI)
# ============================================================
confirm_queue = queue.Queue()   # main thread -> worker: (tx_hash, submit_time)
stats_lock = threading.Lock()
blockchain_stats = {
    "submit_ms": 0.0,           # T_submission (fire-and-forget, inline)
    "confirm_ms": 0.0,          # T_confirmation (background receipt wait)
    "status": "WAITING FOR FIRST TX...",
    "tx_count": 0,
    "current_block": 0,
}

# ============================================================
#  HELPERS
# ============================================================
def safe_addstr(stdscr, y, x, text, attr=0):
    h, w = stdscr.getmaxyx()
    if y >= h or x >= w:
        return
    text = str(text)
    if x + len(text) > w:
        text = text[:w - x - 1]
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass

def check_blockchain():
    try:
        if not w3.is_connected():
            return False, "HTTPProvider not connected"
        block = w3.eth.block_number
        chain = w3.eth.chain_id
        if chain != CHAIN_ID:
            return False, f"chainId mismatch: got {chain}, expected {CHAIN_ID}"
        return True, block
    except Exception as e:
        return False, str(e)[:60]

def init_csv():
    with open(log_filename, mode='w', newline='') as f:
        csv.writer(f).writerow(CSV_HEADER)

def append_csv(row: list):
    with open(log_filename, mode='a', newline='') as f:
        csv.writer(f).writerow(row)

# ============================================================
#  BACKGROUND WORKER — waits for PoS confirmation receipts
#  (~12-24s) without stalling the MAVLink/UI main loop.
#  The main loop does fire-and-forget send_transaction() and
#  pushes (tx_hash, submit_time_ns) here for receipt tracking.
# ============================================================
def confirmation_worker():
    while True:
        tx_hash, submit_time = confirm_queue.get()

        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            t_confirm = (time.perf_counter() - submit_time) * 1000.0

            with stats_lock:
                blockchain_stats["confirm_ms"]    = t_confirm
                blockchain_stats["current_block"] = receipt['blockNumber']

        except Exception as e:
            with stats_lock:
                blockchain_stats["confirm_ms"] = -1.0

        confirm_queue.task_done()

# ============================================================
#  MAIN CURSES LOOP
# ============================================================
def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN,  -1)
    curses.init_pair(2, curses.COLOR_RED,    -1)
    curses.init_pair(3, curses.COLOR_CYAN,   -1)
    curses.init_pair(4, curses.COLOR_YELLOW, -1)

    BOLD  = curses.A_BOLD
    REV   = curses.A_REVERSE
    GREEN = curses.color_pair(1)
    RED   = curses.color_pair(2)
    CYAN  = curses.color_pair(3)

    # ── Startup: verify blockchain ────────────────────────────
    stdscr.erase()
    safe_addstr(stdscr, 0, 0,
        "=== THESIS: BLOCKCHAIN LATENCY IN EMBEDDED FLIGHT CONTROL (PoS) ===", REV)
    safe_addstr(stdscr, 2, 0, "Checking blockchain node...", BOLD)
    stdscr.refresh()

    ok, info = check_blockchain()
    if ok:
        safe_addstr(stdscr, 3, 0,
            f"  Blockchain OK — chainId={CHAIN_ID}  current block=#{info}",
            GREEN | BOLD)
    else:
        safe_addstr(stdscr, 3, 0,
            f"  Blockchain UNREACHABLE: {info}", RED | BOLD)
        safe_addstr(stdscr, 5, 0,
            "  Start Geth first, then re-run.  Press any key to exit.")
        stdscr.nodelay(False)
        stdscr.getch()
        return

    # Start the background TX/confirmation worker
    worker_thread = threading.Thread(target=confirmation_worker, daemon=True)
    worker_thread.start()

    # ── Startup: MAVLink ──────────────────────────────────────
    safe_addstr(stdscr, 5, 0,
        f"  Connecting MAVLink: {DEVICE} @ {BAUD} baud ...", BOLD)
    stdscr.refresh()

    port_check = subprocess.run(["fuser", DEVICE], capture_output=True, text=True)
    if port_check.stdout.strip():
        pids = port_check.stdout.strip()
        safe_addstr(stdscr, 6, 0,
            f"  MAVLink FAILED: {DEVICE} is already held by PID {pids}", RED | BOLD)
        safe_addstr(stdscr, 7, 0,
            f"  Run: kill {pids}   then restart this script.", RED)
        safe_addstr(stdscr, 9, 0, "  Press any key to exit.")
        stdscr.nodelay(False)
        stdscr.getch()
        return

    try:
        connection = mavutil.mavlink_connection(DEVICE, baud=BAUD)
        connection.wait_heartbeat(timeout=10)
    except Exception as e:
        safe_addstr(stdscr, 6, 0, f"  MAVLink FAILED: {e}", RED | BOLD)
        safe_addstr(stdscr, 8, 0, "  Press any key to exit.")
        stdscr.nodelay(False)
        stdscr.getch()
        return

    connection.mav.request_data_stream_send(
        connection.target_system,
        connection.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL,
        20, 1
    )

    init_csv()

    # ── State variables ───────────────────────────────────────
    last_msg_time     = time.perf_counter()
    last_display_time = time.perf_counter()
    last_tx_time      = time.perf_counter() - TX_INTERVAL

    nonce_cache       = None

    gap      = 0.0
    mean_gap = 0.0
    max_gap  = 0.0
    std_gap  = 0.0

    height_offset = None

    telemetry = {
        'latitude': 0.0, 'longitude': 0.0,
        'altitude': 0.0, 'pos_z':     0.0,
        'voltage':  0.0, 'current':   0.0,
        'speed':    0.0, 'heading':   0,
        'satellites': 0,
    }

    # ============================================================
    #  MAIN LOOP
    # ============================================================
    while True:
        key = stdscr.getch()
        if key == ord('q'):
            break
        if key == ord('r'):
            height_offset = None

        try:
            msg = connection.recv_match(blocking=False)
        except Exception as serial_err:
            safe_addstr(stdscr, 20, 0,
                f"  !! SERIAL DISCONNECTED: {str(serial_err)[:60]}",
                RED | BOLD)
            stdscr.refresh()
            time.sleep(2)
            break

        if msg:
            now = time.perf_counter()

            gap = (now - last_msg_time) * 1000.0
            telemetry_gaps.append(gap)
            last_msg_time = now

            n = len(telemetry_gaps)
            mean_gap = statistics.mean(telemetry_gaps)
            max_gap  = max(telemetry_gaps)
            std_gap  = statistics.stdev(telemetry_gaps) if n >= 2 else 0.0

            m = msg.get_type()
            if m == 'GLOBAL_POSITION_INT':
                telemetry['latitude']  = msg.lat / 1e7
                telemetry['longitude'] = msg.lon / 1e7
            elif m == 'LOCAL_POSITION_NED':
                telemetry['pos_z'] = msg.z
            elif m == 'SYS_STATUS':
                telemetry['voltage'] = msg.voltage_battery / 1000.0
                telemetry['current'] = msg.current_battery / 100.0
            elif m == 'VFR_HUD':
                telemetry['speed']   = msg.groundspeed
                telemetry['heading'] = msg.heading
            elif m == 'GPS_RAW_INT':
                telemetry['satellites'] = msg.satellites_visible

            raw_h = -telemetry['pos_z']
            if height_offset is None:
                height_offset = raw_h
            telemetry['altitude'] = raw_h - height_offset

            # ── Fire-and-forget TX (inline, ~5-15ms) ───────────
            if now - last_tx_time >= TX_INTERVAL:
                last_tx_time = now
                tx_start = time.perf_counter()

                try:
                    payload = (
                        f"ALT:{telemetry['altitude']:.2f},"
                        f"SPD:{telemetry['speed']:.2f},"
                        f"LAT:{telemetry['latitude']:.6f},"
                        f"LON:{telemetry['longitude']:.6f},"
                        f"HDG:{telemetry['heading']},"
                        f"SAT:{telemetry['satellites']}"
                    )

                    if nonce_cache is None:
                        nonce_cache = w3.eth.get_transaction_count(
                            MY_ADDRESS, 'pending'
                        )

                    tx = {
                        'from': MY_ADDRESS,
                        'to': MY_ADDRESS,
                        'value': 0,
                        'gas': 120_000,
                        'maxFeePerGas': w3.to_wei(2, 'gwei'),
                        'maxPriorityFeePerGas': w3.to_wei(1, 'gwei'),
                        'nonce': nonce_cache,
                        'data': w3.to_hex(text=payload),
                        'chainId': CHAIN_ID,
                    }

                    tx_hash = w3.eth.send_transaction(tx)
                    t_submit = (time.perf_counter() - tx_start) * 1000.0
                    nonce_cache += 1

                    with stats_lock:
                        blockchain_stats["submit_ms"] = t_submit
                        blockchain_stats["status"]    = "OK"
                        blockchain_stats["tx_count"] += 1

                    # Hand hash to background thread for receipt tracking
                    confirm_queue.put((tx_hash, tx_start))

                except Exception as e:
                    err_msg = str(e)[:40]
                    with stats_lock:
                        blockchain_stats["submit_ms"] = -1.0
                        blockchain_stats["status"]    = f"ERR: {err_msg}"

                    if "nonce" in err_msg.lower() or "underpriced" in err_msg.lower():
                        nonce_cache = None

            # ── Read latest blockchain stats & log ─────────────
            with stats_lock:
                bc_submit  = blockchain_stats["submit_ms"]
                bc_confirm = blockchain_stats["confirm_ms"]
                bc_status  = blockchain_stats["status"]
                bc_txcount = blockchain_stats["tx_count"]
                bc_block   = blockchain_stats["current_block"]

            append_csv([
                datetime.now().isoformat(),
                f"{gap:.3f}",
                f"{mean_gap:.3f}",
                f"{max_gap:.3f}",
                f"{std_gap:.3f}",
                f"{bc_submit:.3f}",
                f"{bc_confirm:.3f}",
                bc_txcount,
                bc_block,
                bc_status,
                f"{telemetry['altitude']:.3f}",
                f"{telemetry['speed']:.3f}",
                telemetry['heading'],
                f"{telemetry['latitude']:.7f}",
                f"{telemetry['longitude']:.7f}",
                f"{telemetry['voltage']:.3f}",
                f"{telemetry['current']:.3f}",
                telemetry['satellites'],
            ])

        # ── Display ───────────────────────────────────────────
        if time.perf_counter() - last_display_time >= DISPLAY_INTERVAL:
            with stats_lock:
                bc_submit  = blockchain_stats["submit_ms"]
                bc_confirm = blockchain_stats["confirm_ms"]
                bc_status  = blockchain_stats["status"]
                bc_txcount = blockchain_stats["tx_count"]
                bc_block   = blockchain_stats["current_block"]

            stdscr.erase()

            safe_addstr(stdscr, 0, 0,
                "=== BLOCKCHAIN LATENCY IN EMBEDDED FLIGHT CONTROL SYSTEM (PoS) ===",
                REV)

            safe_addstr(stdscr, 2, 0,
                f"Log: {os.path.basename(log_filename)}"
                f"   Block: #{bc_block}"
                f"   TX count: {bc_txcount}", CYAN)

            safe_addstr(stdscr, 4, 0, "TELEMETRY LINK QUALITY", BOLD)
            safe_addstr(stdscr, 5, 2, f"Current gap : {gap:8.3f} ms")
            safe_addstr(stdscr, 6, 2,
                f"Mean gap    : {mean_gap:8.3f} ms"
                f"  (window={len(telemetry_gaps)})")
            safe_addstr(stdscr, 7, 2, f"Max gap     : {max_gap:8.3f} ms")
            safe_addstr(stdscr, 8, 2, f"Std dev     : {std_gap:8.3f} ms")

            safe_addstr(stdscr, 10, 0, "BLOCKCHAIN (PoS fire-and-forget)", BOLD)
            bc_color = GREEN if bc_status == "OK" else RED
            safe_addstr(stdscr, 11, 2, "T_submit    : ")
            safe_addstr(stdscr, 11, 16,
                f"{bc_submit:8.3f} ms" if bc_submit >= 0 else "      FAILED",
                bc_color | BOLD)
            safe_addstr(stdscr, 12, 2, "T_confirm   : ")
            safe_addstr(stdscr, 12, 16,
                f"{bc_confirm:8.3f} ms" if bc_confirm >= 0 else "   PENDING",
                CYAN | BOLD)
            safe_addstr(stdscr, 13, 2, f"Status      : {bc_status}", bc_color)
            safe_addstr(stdscr, 14, 2,
                "(T_submit = inline latency; T_confirm = background receipt)",
                CYAN)

            safe_addstr(stdscr, 16, 0, "FLIGHT DATA", BOLD)
            safe_addstr(stdscr, 17, 2,
                f"Altitude : {telemetry['altitude']:7.2f} m"
                f"   Speed : {telemetry['speed']:5.2f} m/s"
                f"   Heading : {telemetry['heading']:3d} deg")
            safe_addstr(stdscr, 18, 2,
                f"GPS      : {telemetry['latitude']:11.7f},"
                f" {telemetry['longitude']:12.7f}"
                f"   Sats: {telemetry['satellites']}")
            safe_addstr(stdscr, 19, 2,
                f"Battery  : {telemetry['voltage']:.2f} V"
                f"  /  {telemetry['current']:.2f} A")

            safe_addstr(stdscr, 21, 0,
                "[q] quit   [r] reset altitude baseline", CYAN)

            stdscr.refresh()
            last_display_time = time.perf_counter()

    curses.endwin()
    print(f"\nSession complete.")
    print(f"CSV log : {log_filename}")
    with stats_lock:
        print(f"Total TX confirmed: {blockchain_stats['tx_count']}")

# ============================================================
#  ENTRY POINT
# ============================================================
if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        print("\nAborted.")
    except Exception as e:
        try:
            curses.endwin()
        except Exception:
            pass
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        sys.exit(1)