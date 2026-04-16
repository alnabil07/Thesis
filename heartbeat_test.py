import time
import curses
import csv
import os
from pymavlink import mavutil

# --- Configuration ---
DEVICE = '/dev/ttyAMA0'
BAUD = 921600
DISPLAY_INTERVAL = 0.1  
BLOCKCHAIN_MODE = "ON" # Change this to "ON" manually for Phase 2

# Create log directory
if not os.path.exists('thesis_logs'):
    os.makedirs('thesis_logs')

log_filename = f"thesis_logs/latency_log_{int(time.time())}.csv"

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(1) 

    stdscr.addstr(1, 0, f"Connecting to {DEVICE}...", curses.A_BOLD)
    stdscr.refresh()
    
    connection = mavutil.mavlink_connection(DEVICE, baud=BAUD)
    connection.wait_heartbeat()
    
    connection.mav.request_data_stream_send(
        connection.target_system, connection.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 20, 1)

    # Initialize CSV with Headers
    with open(log_filename, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Update_Gap_ms", "Blockchain_Status"])

    last_msg_time = time.time()
    last_display_update = time.time()
    latency = 0.0
    
    data = {'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0, 'volt': 0.0, 'curr': 0.0, 'alt': 0.0, 'hdg': 0, 'lat': 0.0, 'lon': 0.0, 'sats': 0, 'fix': 0}

    while True:
        key = stdscr.getch()
        if key == ord('q'):
            break

        # 1. PROCESS ALL MESSAGES
        while True:
            msg = connection.recv_match(blocking=False)
            if not msg:
                break
            
            m_type = msg.get_type()
            current_time = time.time()
            latency = (current_time - last_msg_time) * 1000
            last_msg_time = current_time

            # --- DATA LOGGING START ---
            with open(log_filename, mode='a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([current_time, latency, BLOCKCHAIN_MODE])
            # --- DATA LOGGING END ---

            if m_type == 'ATTITUDE':
                data['roll'], data['pitch'], data['yaw'] = msg.roll, msg.pitch, msg.yaw
            elif m_type == 'SYS_STATUS':
                data['volt'] = msg.voltage_battery / 1000.0
                data['curr'] = msg.current_battery / 100.0
            elif m_type == 'VFR_HUD':
                data['alt'], data['hdg'] = msg.alt, msg.heading
            elif m_type == 'GPS_RAW_INT':
                data['lat'], data['lon'] = msg.lat/1e7, msg.lon/1e7
                data['sats'], data['fix'] = msg.satellites_visible, msg.fix_type

        # 2. UPDATE DISPLAY
        if time.time() - last_display_update > DISPLAY_INTERVAL:
            stdscr.erase()
            stdscr.addstr(0, 0, "=== MAVLink THESIS LOGGING DASHBOARD ===", curses.A_REVERSE)
            stdscr.addstr(2, 0, f"Blockchain Status: {BLOCKCHAIN_MODE}", curses.A_BOLD)
            stdscr.addstr(3, 0, f"Logging to: {log_filename}")
            stdscr.addstr(5, 0, f"Link Status: ONLINE (Current Gap: {latency:.2f}ms)")
            stdscr.addstr(7, 0, f"Battery: {data['volt']:.2f}V | Roll: {data['roll']:.3f}")
            stdscr.addstr(10, 0, "Press [q] to stop logging and exit")
            stdscr.refresh()
            last_display_update = time.time()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except Exception as e:
        print(f"\n[ERROR] {e}")