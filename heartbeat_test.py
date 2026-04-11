import time
import curses
from pymavlink import mavutil

# --- Configuration ---
DEVICE = '/dev/ttyAMA0'
BAUD = 921600
DISPLAY_INTERVAL = 0.1  # Update screen every 100ms (10Hz) for readability

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(1) # Check serial port as fast as possible

    stdscr.addstr(1, 0, f"Connecting to {DEVICE}...", curses.A_BOLD)
    stdscr.refresh()
    
    connection = mavutil.mavlink_connection(DEVICE, baud=BAUD)
    connection.wait_heartbeat()
    
    # Request data streams
    connection.mav.request_data_stream_send(
        connection.target_system, connection.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 20, 1)

    last_msg_time = time.time()
    last_display_update = time.time()
    latency = 0.0
    
    data = {
        'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0,
        'volt': 0.0, 'curr': 0.0,
        'alt': 0.0, 'hdg': 0,
        'lat': 0.0, 'lon': 0.0, 'sats': 0, 'fix': 0
    }

    while True:
        key = stdscr.getch()
        if key == ord('q'):
            break

        # 1. PROCESS ALL MESSAGES (Stay Fast)
        while True:
            msg = connection.recv_match(blocking=False)
            if not msg:
                break
            
            m_type = msg.get_type()
            
            # Record latency for the very latest message
            current_time = time.time()
            latency = (current_time - last_msg_time) * 1000
            last_msg_time = current_time

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

        # 2. UPDATE DISPLAY (Throttle for Humans)
        if time.time() - last_display_update > DISPLAY_INTERVAL:
            stdscr.erase() # Clear screen to prevent ghosting
            stdscr.addstr(0, 0, "=== MAVLink STABILIZED Telemetry Dashboard ===", curses.A_REVERSE)
            stdscr.addstr(2, 0, f"Link Status: ONLINE (Update Gap: {latency:.2f}ms)")
            
            stdscr.addstr(4, 0, f"Battery: {data['volt']:.2f}V | {data['curr']:.2f}A")
            stdscr.addstr(5, 0, f"Roll:    {data['roll']:>8.3f} | Pitch: {data['pitch']:>8.3f} | Yaw: {data['yaw']:>8.3f}")
            stdscr.addstr(6, 0, f"Alt:     {data['alt']:>8.1f}m | Heading: {data['hdg']:>3}°")
            stdscr.addstr(7, 0, f"GPS:     {data['lat']:.6f}, {data['lon']:.6f}")
            stdscr.addstr(8, 0, f"Sats:    {data['sats']:>2} | Fix: {data['fix']}")
            
            stdscr.addstr(10, 0, "Controls: [q] Exit Safely", curses.A_DIM)
            stdscr.refresh()
            last_display_update = time.time()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except Exception as e:
        print(f"\n[ERROR] {e}")