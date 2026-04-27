"""
================================================================================
  THESIS: Quantitative Analysis and Optimization of Blockchain-Induced
          Latency in Real-Time Embedded Flight Control Systems
  Author : Nabil / merajpi
  Hardware: Raspberry Pi 5 (Ubuntu) + Pixhawk 2.4.8
  Chain  : Private Ethereum PoA (Clique, chainId=1337, 2s block time)
  Geth   : v1.13.15-stable  |  web3.py v6+
================================================================================
"""

import time
import curses
import csv
import os
import sys
from datetime import datetime
from collections import deque
import statistics

from pymavlink import mavutil
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

# ============================================================
#  CONFIGURATION  — edit only this section if needed
# ============================================================
DEVICE           = '/dev/ttyAMA0'   # MAVLink serial port
BAUD             = 921600           # Serial baud rate
DISPLAY_INTERVAL = 0.1              # Terminal refresh rate (seconds)
TX_INTERVAL      = 2.0              # Blockchain TX interval (seconds)

RPC_URL          = 'http://127.0.0.1:8545'
CHAIN_ID         = 1337
MY_ADDRESS       = "0x11Db73254c357F47B1194616B0142f738d0f3124"

LOG_DIR          = "/home/merajpi/Nabil/logs"
WINDOW_SIZE      = 50               # Rolling stats window (messages)

# ============================================================
#  SETUP
# ============================================================
w3 = Web3(Web3.HTTPProvider(RPC_URL))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

os.makedirs(LOG_DIR, exist_ok=True)
timestamp_str = datetime.now().strftime("%H%M-%d%m%Y")
log_filename  = os.path.join(LOG_DIR, f"latency_analysis_{timestamp_str}.csv")

telemetry_gaps = deque(maxlen=WINDOW_SIZE)

CSV_HEADER = [
    "Timestamp",
    "Telemetry_Gap_ms",
    "Telemetry_Mean_Gap_ms",
    "Telemetry_Max_Gap_ms",
    "Telemetry_Std_Gap_ms",
    "Blockchain_TX_Latency_ms",
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
        "=== THESIS: BLOCKCHAIN LATENCY IN EMBEDDED FLIGHT CONTROL ===", REV)
    safe_addstr(stdscr, 2, 0, "Checking blockchain node...", BOLD)
    stdscr.refresh()

    ok, info = check_blockchain()
    if ok:
        safe_addstr(stdscr, 3, 0,
            f"  Blockchain OK — chainId=1337  current block=#{info}",
            GREEN | BOLD)
    else:
        safe_addstr(stdscr, 3, 0,
            f"  Blockchain UNREACHABLE: {info}", RED | BOLD)
        safe_addstr(stdscr, 5, 0,
            "  Start Geth first, then re-run.  Press any key to exit.")
        stdscr.nodelay(False)
        stdscr.getch()
        return

    # ── Startup: MAVLink ──────────────────────────────────────
    safe_addstr(stdscr, 5, 0,
        f"  Connecting MAVLink: {DEVICE} @ {BAUD} baud ...", BOLD)
    stdscr.refresh()

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

    gap      = 0.0
    mean_gap = 0.0
    max_gap  = 0.0
    std_gap  = 0.0

    tx_count           = 0
    blockchain_latency = 0.0
    blockchain_status  = "WAITING FOR FIRST TX..."
    height_offset      = None
    nonce_cache        = None
    current_block      = 0

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

        msg = connection.recv_match(blocking=False)
        if msg:
            now = time.perf_counter()

            # Telemetry gap
            gap = (now - last_msg_time) * 1000.0
            telemetry_gaps.append(gap)
            last_msg_time = now

            n = len(telemetry_gaps)
            mean_gap = statistics.mean(telemetry_gaps)
            max_gap  = max(telemetry_gaps)
            std_gap  = statistics.stdev(telemetry_gaps) if n >= 2 else 0.0

            # Parse MAVLink message
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

            # ── Blockchain TX ─────────────────────────────────
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

                    # --- FIXED NONCE HANDLING ---
                    if nonce_cache is None:
                        nonce_cache = w3.eth.get_transaction_count(MY_ADDRESS, 'pending')
                    # ----------------------------

                    tx = {
                        'from':     MY_ADDRESS,
                        'to':       MY_ADDRESS,
                        'value':    0,
                        'gas':      120_000,
                        'gasPrice': max(w3.eth.gas_price,
                                        w3.to_wei(1, 'gwei')),
                        'nonce':    nonce_cache,
                        'data':     w3.to_hex(text=payload),
                        'chainId':  CHAIN_ID,
                    }

                    w3.eth.send_transaction(tx)
                    nonce_cache       += 1
                    blockchain_latency = (time.perf_counter() - tx_start) * 1000.0
                    tx_count          += 1
                    current_block      = w3.eth.block_number
                    blockchain_status  = "OK"

                except Exception as e:
                    blockchain_latency = -1.0
                    err_msg = str(e)[:40]
                    blockchain_status  = f"ERR: {err_msg}"
                    
                    # Failsafe: if the network rejects the nonce, reset it so the 
                    # next loop pulls a fresh, accurate nonce from the pending block.
                    if "nonce" in err_msg.lower() or "underpriced" in err_msg.lower():
                        nonce_cache = None

            # ── CSV row ───────────────────────────────────────
            append_csv([
                datetime.now().isoformat(),
                f"{gap:.3f}",
                f"{mean_gap:.3f}",
                f"{max_gap:.3f}",
                f"{std_gap:.3f}",
                f"{blockchain_latency:.3f}",
                tx_count,
                current_block,
                blockchain_status,
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
            stdscr.erase()

            safe_addstr(stdscr, 0, 0,
                "=== THESIS: BLOCKCHAIN LATENCY IN EMBEDDED FLIGHT CONTROL ===",
                REV)

            safe_addstr(stdscr, 2, 0,
                f"Log: {os.path.basename(log_filename)}"
                f"   Block: #{current_block}"
                f"   TX count: {tx_count}", CYAN)

            safe_addstr(stdscr, 4, 0, "TELEMETRY LINK QUALITY", BOLD)
            safe_addstr(stdscr, 5, 2,
                f"Current gap : {gap:8.3f} ms")
            safe_addstr(stdscr, 6, 2,
                f"Mean gap    : {mean_gap:8.3f} ms"
                f"  (window={len(telemetry_gaps)})")
            safe_addstr(stdscr, 7, 2,
                f"Max gap     : {max_gap:8.3f} ms")
            safe_addstr(stdscr, 8, 2,
                f"Std dev     : {std_gap:8.3f} ms")

            safe_addstr(stdscr, 10, 0, "BLOCKCHAIN", BOLD)
            bc_color = GREEN if blockchain_status == "OK" else RED
            safe_addstr(stdscr, 11, 2, "TX latency  : ")
            safe_addstr(stdscr, 11, 16,
                f"{blockchain_latency:8.3f} ms"
                if blockchain_latency >= 0 else "      FAILED",
                bc_color | BOLD)
            safe_addstr(stdscr, 12, 2,
                f"Status      : {blockchain_status}", bc_color)

            safe_addstr(stdscr, 14, 0, "FLIGHT DATA", BOLD)
            safe_addstr(stdscr, 15, 2,
                f"Altitude : {telemetry['altitude']:7.2f} m"
                f"   Speed : {telemetry['speed']:5.2f} m/s"
                f"   Heading : {telemetry['heading']:3d} deg")
            safe_addstr(stdscr, 16, 2,
                f"GPS      : {telemetry['latitude']:11.7f},"
                f" {telemetry['longitude']:12.7f}"
                f"   Sats: {telemetry['satellites']}")
            safe_addstr(stdscr, 17, 2,
                f"Battery  : {telemetry['voltage']:.2f} V"
                f"  /  {telemetry['current']:.2f} A")

            safe_addstr(stdscr, 19, 0,
                "[q] quit   [r] reset altitude baseline", CYAN)

            stdscr.refresh()
            last_display_time = time.perf_counter()

    curses.endwin()
    print(f"\nSession complete.")
    print(f"CSV log : {log_filename}")
    print(f"Total TX: {tx_count}")

# ============================================================
#  ENTRY POINT
# ============================================================
if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        print("\nAborted.")
    except Exception as e:
        curses.endwin()
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        sys.exit(1)