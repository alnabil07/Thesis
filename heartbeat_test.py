import time
import curses
import csv
import os
from datetime import datetime
from collections import deque
import statistics

from pymavlink import mavutil
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

# ========================= CONFIGURATION FOR THESIS EXPERIMENTS =========================
DEVICE = '/dev/ttyAMA0'
BAUD = 921600
DISPLAY_INTERVAL = 0.1
TX_INTERVAL = 2.0

# === IMPORTANT: Change this for different experiments ===
BLOCKCHAIN_ENABLED = True        # ← Set to False for "Blockchain OFF" run
# =======================================================

# Blockchain Setup (only used when BLOCKCHAIN_ENABLED = True)
w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
my_address = "0x65e24BBF350cC4665309513d423eA4f6F1CC49f7"

# Logging - Clear filename based on mode (helps you separate files easily)
LOG_DIR = "/home/merajpi/Nabil/logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

mode_str = "ON" if BLOCKCHAIN_ENABLED else "OFF"
timestamp_str = datetime.now().strftime("%H%M-%d%m%Y")
log_filename = os.path.join(LOG_DIR, f"latency_experiment_{mode_str}_{timestamp_str}.csv")

# Rolling window for telemetry statistics
TELEMETRY_WINDOW_SIZE = 50
telemetry_gaps = deque(maxlen=TELEMETRY_WINDOW_SIZE)

# ========================= SAFE PRINT =========================
def safe_addstr(stdscr, y, x, text, attr=0):
    h, w = stdscr.getmaxyx()
    if y >= h or x >= w:
        return
    text = str(text)
    if x + len(text) > w:
        text = text[:w - x - 1]
    try:
        stdscr.addstr(y, x, text, attr)
    except:
        pass

# ========================= MAIN =========================
def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)   # OK
    curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)     # ERROR
    curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_YELLOW, curses.COLOR_BLACK)

    safe_addstr(stdscr, 1, 0, f"Connecting to {DEVICE} at {BAUD} baud...", curses.A_BOLD)
    stdscr.refresh()

    # MAVLink Connection
    connection = mavutil.mavlink_connection(DEVICE, baud=BAUD)
    connection.wait_heartbeat(timeout=10)
    connection.mav.request_data_stream_send(
        connection.target_system,
        connection.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL,
        20, 1
    )

    # Create CSV with clear headers for analysis & graphing
    with open(log_filename, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "Timestamp", 
            "Telemetry_Link_Gap_ms", 
            "Telemetry_Mean_Gap_ms",
            "Telemetry_Max_Gap_ms",
            "Telemetry_Std_Gap_ms",
            "Blockchain_Tx_Latency_ms",
            "Tx_Count",
            "Blockchain_Mode",          # "ON" or "OFF"
            "Blockchain_Status",
            "Altitude_m",
            "Speed_mps",
            "Latitude",
            "Longitude"
        ])

    # Variables
    last_msg_time = time.perf_counter()
    last_display_update = time.perf_counter()
    last_tx_time = time.perf_counter()

    tx_count = 0
    status_msg = "READY"
    blockchain_latency = 0.0
    height_offset = None

    telemetry = {
        'latitude': 0.0, 'longitude': 0.0,
        'altitude': 0.0,
        'voltage': 0.0, 'current': 0.0,
        'speed': 0.0, 'heading': 0,
        'satellites': 0,
        'pos_z': 0.0
    }

    while True:
        key = stdscr.getch()
        if key == ord('q'):
            break
        if key == ord('r'):           # Reset height offset
            height_offset = None

        msg = connection.recv_match(blocking=False)
        if msg:
            now = time.perf_counter()

            # === TELEMETRY LATENCY ===
            gap = (now - last_msg_time) * 1000
            telemetry_gaps.append(gap)
            last_msg_time = now

            mean_gap = statistics.mean(telemetry_gaps) if telemetry_gaps else 0
            max_gap = max(telemetry_gaps) if telemetry_gaps else 0
            std_gap = statistics.stdev(telemetry_gaps) if len(telemetry_gaps) > 1 else 0

            # Parse telemetry
            m_type = msg.get_type()
            if m_type == 'GLOBAL_POSITION_INT':
                telemetry['latitude'] = msg.lat / 1e7
                telemetry['longitude'] = msg.lon / 1e7
            elif m_type == 'LOCAL_POSITION_NED':
                telemetry['pos_z'] = msg.z
            elif m_type == 'SYS_STATUS':
                telemetry['voltage'] = msg.voltage_battery / 1000.0
                telemetry['current'] = msg.current_battery / 100.0
            elif m_type == 'VFR_HUD':
                telemetry['speed'] = msg.groundspeed
                telemetry['heading'] = msg.heading
            elif m_type == 'GPS_RAW_INT':
                telemetry['satellites'] = msg.satellites_visible

            # Height calculation
            raw_height = -telemetry['pos_z']
            if height_offset is None:
                height_offset = raw_height
            telemetry['altitude'] = raw_height - height_offset

            # === BLOCKCHAIN (Only when enabled) ===
            blockchain_latency = 0.0
            if BLOCKCHAIN_ENABLED and (now - last_tx_time > TX_INTERVAL):
                tx_start = time.perf_counter()
                try:
                    log_str = f"H:{telemetry['altitude']:.2f},S:{telemetry['speed']:.2f}"
                    tx = {
                        'from': my_address,
                        'to': my_address,
                        'value': 0,
                        'gas': 120000,
                        'gasPrice': w3.eth.gas_price,
                        'nonce': w3.eth.get_transaction_count(my_address),
                        'data': w3.to_hex(text=log_str),
                    }
                    w3.eth.send_transaction(tx)
                    tx_end = time.perf_counter()
                    blockchain_latency = (tx_end - tx_start) * 1000
                    status_msg = "TX_OK"
                    tx_count += 1
                except Exception as e:
                    blockchain_latency = -1.0
                    status_msg = f"TX_ERROR"
                last_tx_time = now
            else:
                if not BLOCKCHAIN_ENABLED:
                    status_msg = "BLOCKCHAIN_OFF"

            # === LOG TO CSV ===
            with open(log_filename, mode='a', newline='') as f:
                csv.writer(f).writerow([
                    datetime.now().isoformat(),
                    f"{gap:.2f}",
                    f"{mean_gap:.2f}",
                    f"{max_gap:.2f}",
                    f"{std_gap:.2f}",
                    f"{blockchain_latency:.2f}",
                    tx_count,
                    "ON" if BLOCKCHAIN_ENABLED else "OFF",
                    status_msg,
                    f"{telemetry['altitude']:.2f}",
                    f"{telemetry['speed']:.2f}",
                    f"{telemetry['latitude']:.6f}",
                    f"{telemetry['longitude']:.6f}"
                ])

        # === DISPLAY ===
        if time.perf_counter() - last_display_update > DISPLAY_INTERVAL:
            stdscr.erase()
            safe_addstr(stdscr, 0, 0, "=== PIXHAWK BLOCKCHAIN LATENCY EXPERIMENT (THESIS) ===", curses.A_REVERSE)

            safe_addstr(stdscr, 2, 0, f"Experiment Mode: BLOCKCHAIN {'ON' if BLOCKCHAIN_ENABLED else 'OFF'}")
            safe_addstr(stdscr, 3, 0, f"TX Interval: {TX_INTERVAL}s | TX Count: {tx_count}")

            safe_addstr(stdscr, 5, 0, f"Telemetry Link Gap: {gap if 'gap' in locals() else 0:.2f} ms")
            safe_addstr(stdscr, 6, 0, f"Telemetry Stats → Mean: {mean_gap:.2f} ms | Max: {max_gap:.2f} ms | Std: {std_gap:.2f} ms")

            location_str = f"{telemetry['latitude']:.6f}, {telemetry['longitude']:.6f}"
            safe_addstr(stdscr, 8, 0, f"Location: {location_str:<30} | Sat: {telemetry['satellites']}")

            safe_addstr(stdscr, 10, 0, f"Altitude: {telemetry['altitude']:.2f} m | Speed: {telemetry['speed']:.2f} m/s")

            safe_addstr(stdscr, 12, 0, f"Battery: {telemetry['voltage']:.2f} V | {telemetry['current']:.2f} A")

            color = curses.color_pair(1) if status_msg == "TX_OK" else curses.color_pair(2)
            safe_addstr(stdscr, 14, 0, "Blockchain Tx Latency: ")
            safe_addstr(stdscr, 14, 22, f"{blockchain_latency:.2f} ms", color)
            safe_addstr(stdscr, 15, 0, f"Status: {status_msg}", color)

            safe_addstr(stdscr, 17, 0, "Press [q] to exit | [r] to reset altitude offset")
            stdscr.refresh()
            last_display_update = time.perf_counter()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")