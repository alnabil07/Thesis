import time
import curses
import csv
import os
from pymavlink import mavutil
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from collections import deque

# --- Configuration ---
DEVICE = '/dev/ttyAMA0'
BAUD = 921600
DISPLAY_INTERVAL = 0.1
BLOCKCHAIN_MODE = "ON_TRANSACTION"
TX_INTERVAL = 2.0

# --- Blockchain Setup ---
w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
my_address = "0x65e24BBF350cC4665309513d423eA4f6F1CC49f7"

# --- Logging ---
if not os.path.exists('thesis_logs'):
    os.makedirs('thesis_logs')
log_filename = f"thesis_logs/latency_tx_{int(time.time())}.csv"

# --- Safe Print ---
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

# --- Graph Bar ---
def draw_bar(value, max_value=1, width=2):
    if max_value <= 0:
        return "--"
    ratio = max(0, min(value / max_value, 1.0))
    filled = int(ratio * width)
    return "█" * filled + "-" * (width - filled)

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)

    # Colors
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)

    safe_addstr(stdscr, 1, 0, f"Connecting to {DEVICE}...", curses.A_BOLD)
    stdscr.refresh()

    connection = mavutil.mavlink_connection(DEVICE, baud=BAUD)
    connection.wait_heartbeat()

    connection.mav.request_data_stream_send(
        connection.target_system,
        connection.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL,
        20, 1
    )

    with open(log_filename, mode='w', newline='') as f:
        csv.writer(f).writerow(["Timestamp", "Latency_ms", "Blockchain_Status"])

    # Variables
    last_msg_time = time.time()
    last_display_update = time.time()
    last_tx_time = time.time()

    latency = 0.0
    tx_count = 0
    status_msg = "READY"

    alt_history = deque(maxlen=100)
    speed_history = deque(maxlen=100)

    height_offset = None

    telemetry = {
        'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0,
        'latitude': 0.0, 'longitude': 0.0,
        'altitude': 0.0,
        'voltage': 0.0, 'current': 0.0,
        'speed': 0.0, 'heading': 0,
        'satellites': 0, 'gps_fix': 0,
        'pos_x': 0.0, 'pos_y': 0.0, 'pos_z': 0.0
    }

    while True:
        key = stdscr.getch()
        if key == ord('q'):
            break

        msg = connection.recv_match(blocking=False)
        if msg:
            now = time.time()
            latency = (now - last_msg_time) * 1000
            last_msg_time = now

            with open(log_filename, mode='a', newline='') as f:
                csv.writer(f).writerow([now, latency, BLOCKCHAIN_MODE])

            m_type = msg.get_type()

            # --- Mapping ---
            if m_type == 'ATTITUDE':
                telemetry['roll'], telemetry['pitch'], telemetry['yaw'] = msg.roll, msg.pitch, msg.yaw

            elif m_type == 'GLOBAL_POSITION_INT':
                telemetry['latitude'] = msg.lat / 1e7
                telemetry['longitude'] = msg.lon / 1e7

            elif m_type == 'LOCAL_POSITION_NED':
                telemetry['pos_x'], telemetry['pos_y'], telemetry['pos_z'] = msg.x, msg.y, msg.z

            elif m_type == 'SYS_STATUS':
                telemetry['voltage'] = msg.voltage_battery / 1000.0
                telemetry['current'] = msg.current_battery / 100.0

            elif m_type == 'VFR_HUD':
                telemetry['speed'], telemetry['heading'] = msg.groundspeed, msg.heading

            elif m_type == 'GPS_RAW_INT':
                telemetry['satellites'] = msg.satellites_visible
                telemetry['gps_fix'] = msg.fix_type

            # --- Height Fix ---
            raw_height = -telemetry['pos_z']
            if height_offset is None:
                height_offset = raw_height
            height = raw_height - height_offset
            telemetry['altitude'] = height

            alt_history.append(height)
            speed_history.append(telemetry['speed'])

            # --- Blockchain ---
            if now - last_tx_time > TX_INTERVAL:
                try:
                    log_str = f"H:{height:.2f},S:{telemetry['speed']:.2f}"

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
                    tx_count += 1
                    status_msg = "OK"

                except:
                    status_msg = "ERROR"

                last_tx_time = now

        # --- DISPLAY ---
        if time.time() - last_display_update > DISPLAY_INTERVAL:
            stdscr.erase()
            h, w = stdscr.getmaxyx()

            safe_addstr(stdscr, 0, 0, "=== PIXHAWK TELEMETRY with BLOCKCHAIN ACTIVE LOGGING ===", curses.A_REVERSE)

            safe_addstr(stdscr, 2, 0, f"Mode: {BLOCKCHAIN_MODE} | TX: {tx_count}")
            safe_addstr(stdscr, 3, 0, f"Link Gap: {latency:.2f} ms")

            # ✅ LOCATION + SATELLITE (FIXED)
            location_str = f"{telemetry['latitude']:.6f}, {telemetry['longitude']:.6f}"
            sat_str = f"{telemetry['satellites']} sats"
            safe_addstr(stdscr, 5, 0, f"Location: {location_str:<30}    |   Satellite: {sat_str}")

            safe_addstr(stdscr, 7, 0, f"Altitude: {telemetry['altitude']:.2f} m    Speed: {telemetry['speed']:.2f} m/s")
            safe_addstr(stdscr, 8, 0, f"Heading: {telemetry['heading']} deg")

            safe_addstr(stdscr, 10, 0, f"Voltage: {telemetry['voltage']:.2f} V    Current: {telemetry['current']:.2f} A")

            color = curses.color_pair(1) if status_msg == "OK" else curses.color_pair(2)
            safe_addstr(stdscr, 12, 0, "Blockchain: ")
            safe_addstr(stdscr, 12, 12, status_msg, color)

            # Graphs
            max_points = max(1, w // 3)

            max_spd = max(speed_history) if speed_history else 1
            spd_graph = "".join(draw_bar(v, max_spd, 2) for v in list(speed_history)[-max_points:])
            safe_addstr(stdscr, 17, 0, "Speed Trend:")
            safe_addstr(stdscr, 18, 0, spd_graph)

            safe_addstr(stdscr, h - 1, 0, "Press [q] to exit")

            stdscr.refresh()
            last_display_update = time.time()


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")