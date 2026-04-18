import time
import curses
import csv
import os
from datetime import datetime
from pymavlink import mavutil
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

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

# --- Logging Path (UPDATED) ---
LOG_DIR = "/home/merajpi/Nabil/logs"

# Create directory if not exists
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Filename format: HHMM-DDMMYYYY
timestamp_str = datetime.now().strftime("%H%M-%d%m%Y")
log_filename = os.path.join(LOG_DIR, f"latency_tx_{timestamp_str}.csv")

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


def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)

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

    # Create CSV with header
    with open(log_filename, mode='w', newline='') as f:
        csv.writer(f).writerow(["Timestamp", "Latency_ms", "Blockchain_Status"])

    last_msg_time = time.time()
    last_display_update = time.time()
    last_tx_time = time.time()

    latency = 0.0
    tx_count = 0
    status_msg = "READY"

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

        msg = connection.recv_match(blocking=False)
        if msg:
            now = time.time()
            latency = (now - last_msg_time) * 1000
            last_msg_time = now

            # Write log
            with open(log_filename, mode='a', newline='') as f:
                csv.writer(f).writerow([now, latency, BLOCKCHAIN_MODE])

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
                telemetry['speed'], telemetry['heading'] = msg.groundspeed, msg.heading

            elif m_type == 'GPS_RAW_INT':
                telemetry['satellites'] = msg.satellites_visible

            # --- Height Fix ---
            raw_height = -telemetry['pos_z']
            if height_offset is None:
                height_offset = raw_height
            telemetry['altitude'] = raw_height - height_offset

            # --- Blockchain ---
            if now - last_tx_time > TX_INTERVAL:
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
                    tx_count += 1
                    status_msg = "OK"

                except:
                    status_msg = "ERROR"

                last_tx_time = now

        # --- DISPLAY ---
        if time.time() - last_display_update > DISPLAY_INTERVAL:
            stdscr.erase()

            safe_addstr(stdscr, 0, 0, "=== PIXHAWK TELEMETRY with BLOCKCHAIN ACTIVE LOGGING ===", curses.A_REVERSE)

            safe_addstr(stdscr, 2, 0, f"Mode: {BLOCKCHAIN_MODE} | TX: {tx_count}")
            safe_addstr(stdscr, 3, 0, f"Link Gap: {latency:.2f} ms")

            location_str = f"{telemetry['latitude']:.6f}, {telemetry['longitude']:.6f}"
            safe_addstr(stdscr, 5, 0, f"Location: {location_str:<30} | Satellites: {telemetry['satellites']}")

            safe_addstr(stdscr, 7, 0, f"Altitude: {telemetry['altitude']:.2f} m    Speed: {telemetry['speed']:.2f} m/s")
            safe_addstr(stdscr, 8, 0, f"Heading: {telemetry['heading']} deg")

            safe_addstr(stdscr, 10, 0, f"Voltage: {telemetry['voltage']:.2f} V    Current: {telemetry['current']:.2f} A")

            color = curses.color_pair(1) if status_msg == "OK" else curses.color_pair(2)
            safe_addstr(stdscr, 12, 0, "Blockchain: ")
            safe_addstr(stdscr, 12, 12, status_msg, color)

            safe_addstr(stdscr, 14, 0, "Press [q] to exit")

            stdscr.refresh()
            last_display_update = time.time()


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")