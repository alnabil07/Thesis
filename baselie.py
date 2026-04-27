"""
╔══════════════════════════════════════════════════════════════════╗
║ THESIS — CASE 1: BASELINE (No Blockchain) ║
║ Measures pure MAVLink telemetry latency with zero BC overhead ║
╚══════════════════════════════════════════════════════════════════╝
"""

import time
import csv
import os
import sys
import statistics
from datetime import datetime
from collections import deque
from pymavlink import mavutil
import curses

# ══════════════════════════════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════════════════════════════
DEVICE = '/dev/ttyAMA0'
BAUD = 921600
LOG_DIR = '/home/merajpi/Nabil/logs'
DISPLAY_RATE = 0.5      # Refresh every 0.5 seconds
WINDOW_SIZE = 100

# ══════════════════════════════════════════════════════════════════
# CSV HEADER
# ══════════════════════════════════════════════════════════════════
CSV_HEADER = [
    'Timestamp', 'Case', 'Telemetry_Gap_ms', 'Mean_Gap_ms', 'Max_Gap_ms',
    'Std_Gap_ms', 'T_h_ms', 'T_p_ms', 'T_c_ms', 'T_d_ms', 'T_bc_ms',
    'TX_Count', 'Block_Number', 'BC_Status',
    'Altitude_m', 'Speed_mps', 'Heading_deg',
    'Latitude', 'Longitude', 'Voltage_V', 'Current_A', 'Satellites'
]

# ══════════════════════════════════════════════════════════════════
# CURSES DISPLAY (Fixed version)
# ══════════════════════════════════════════════════════════════════
def show_display(stdscr, log_file, msg_count, gap_ms, mean_gap, max_gap, std_gap, tel):
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    if h < 30 or w < 60:  # Minimum size check
        stdscr.addstr(0, 0, "Terminal window too small! Resize and try again.")
        stdscr.refresh()
        return

    # Title
    title = " THESIS | CASE 1: BASELINE (No Blockchain) "
    stdscr.addstr(0, max(0, (w - len(title)) // 2), title, curses.A_BOLD | curses.A_REVERSE)

    # Info
    log_name = os.path.basename(log_file)
    stdscr.addstr(2, 2, f"Log file      : {log_name}")
    stdscr.addstr(3, 2, f"Messages      : {msg_count:,}")

    # Separators (using safe ASCII '-')
    stdscr.hline(4, 2, '-', w - 4)

    # Telemetry Section
    stdscr.addstr(6, 2, "TELEMETRY LINK QUALITY", curses.A_BOLD)
    stdscr.addstr(8, 4, f"Current gap   : {gap_ms:9.3f} ms")
    stdscr.addstr(9, 4, f"Mean gap      : {mean_gap:9.3f} ms  (last {WINDOW_SIZE} msgs)")
    stdscr.addstr(10, 4, f"Max gap       : {max_gap:9.3f} ms")
    stdscr.addstr(11, 4, f"Std dev       : {std_gap:9.3f} ms")

    stdscr.hline(13, 2, '-', w - 4)

    # Blockchain
    stdscr.addstr(15, 2, "BLOCKCHAIN STATUS", curses.A_BOLD)
    stdscr.addstr(17, 4, "● NOT ACTIVE — Pure Baseline Measurement", 
                  curses.color_pair(1) | curses.A_BOLD)

    stdscr.hline(19, 2, '-', w - 4)

    # Flight Data
    stdscr.addstr(21, 2, "FLIGHT DATA", curses.A_BOLD)
    stdscr.addstr(23, 4, f"Altitude      : {tel['altitude']:7.2f} m")
    stdscr.addstr(24, 4, f"Speed         : {tel['speed']:6.2f} m/s   Heading: {tel['heading']:3d}°")
    stdscr.addstr(25, 4, f"GPS           : {tel['latitude']:.6f}, {tel['longitude']:.6f}")
    stdscr.addstr(26, 4, f"Battery       : {tel['voltage']:.2f} V   |   {tel['current']:.2f} A")
    stdscr.addstr(27, 4, f"Satellites    : {tel['satellites']}")

    # Footer
    footer = " Press Ctrl+C to stop recording "
    stdscr.addstr(max(0, h - 2), max(0, (w - len(footer)) // 2), footer, 
                  curses.A_BOLD | curses.A_REVERSE)

    stdscr.refresh()


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════
def main(stdscr):
    # Curses setup
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)

    # Connect to Pixhawk
    stdscr.addstr(0, 0, "Connecting to Pixhawk via MAVLink...")
    stdscr.refresh()

    try:
        conn = mavutil.mavlink_connection(DEVICE, baud=BAUD)
        conn.wait_heartbeat(timeout=10)
        stdscr.addstr(1, 0, f"✓ Connected! System ID: {conn.target_system}")
    except Exception as e:
        stdscr.addstr(1, 0, f"✗ Connection FAILED: {e}")
        stdscr.addstr(3, 0, "Check DEVICE and BAUD. Press any key to exit.")
        stdscr.refresh()
        stdscr.getch()
        return

    conn.mav.request_data_stream_send(
        conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 20, 1
    )

    # Create log file
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%H%M-%d%m%Y')
    log_path = os.path.join(LOG_DIR, f'case1_baseline_{timestamp}.csv')

    with open(log_path, 'w', newline='') as f:
        csv.writer(f).writerow(CSV_HEADER)

    stdscr.addstr(3, 0, f"✓ Log file: {os.path.basename(log_path)}")
    stdscr.addstr(5, 0, "Starting measurement in 2 seconds...")
    stdscr.refresh()
    time.sleep(2)

    # Variables
    gaps = deque(maxlen=WINDOW_SIZE)
    last_msg_time = time.perf_counter()
    last_display = time.perf_counter()
    msg_count = 0
    height_offset = None

    tel = {
        'altitude': 0.0, 'pos_z': 0.0, 'speed': 0.0, 'heading': 0,
        'latitude': 0.0, 'longitude': 0.0,
        'voltage': 0.0, 'current': 0.0, 'satellites': 0
    }

    stdscr.addstr(7, 0, "Recording... (Press Ctrl+C to stop)")
    stdscr.refresh()

    try:
        while True:
            msg = conn.recv_match(blocking=False)

            if msg:
                now = time.perf_counter()
                gap_ms = (now - last_msg_time) * 1000.0
                gaps.append(gap_ms)
                last_msg_time = now
                msg_count += 1

                # Parse telemetry (same as before)
                mtype = msg.get_type()
                if mtype == 'GLOBAL_POSITION_INT':
                    tel['latitude'] = msg.lat / 1e7
                    tel['longitude'] = msg.lon / 1e7
                elif mtype == 'LOCAL_POSITION_NED':
                    tel['pos_z'] = msg.z
                elif mtype == 'SYS_STATUS':
                    tel['voltage'] = msg.voltage_battery / 1000.0
                    tel['current'] = msg.current_battery / 100.0
                elif mtype == 'VFR_HUD':
                    tel['speed'] = msg.groundspeed
                    tel['heading'] = msg.heading
                elif mtype == 'GPS_RAW_INT':
                    tel['satellites'] = msg.satellites_visible

                raw_h = -tel['pos_z']
                if height_offset is None:
                    height_offset = raw_h
                tel['altitude'] = raw_h - height_offset

                # Statistics
                n = len(gaps)
                mean_gap = statistics.mean(gaps)
                max_gap = max(gaps) if gaps else 0
                std_gap = statistics.stdev(gaps) if n >= 2 else 0.0

                # Save to CSV
                with open(log_path, 'a', newline='') as f:
                    csv.writer(f).writerow([
                        datetime.now().isoformat(), 'BASELINE',
                        f'{gap_ms:.3f}', f'{mean_gap:.3f}', f'{max_gap:.3f}', f'{std_gap:.3f}',
                        0, 0, 0, 0, 0, 0, 0, 'N/A',
                        f'{tel["altitude"]:.3f}', f'{tel["speed"]:.3f}', tel['heading'],
                        f'{tel["latitude"]:.7f}', f'{tel["longitude"]:.7f}',
                        f'{tel["voltage"]:.3f}', f'{tel["current"]:.3f}', tel['satellites']
                    ])

            else:
                time.sleep(0.001)

            # Update display
            if time.perf_counter() - last_display >= DISPLAY_RATE:
                last_display = time.perf_counter()
                current_gap = gap_ms if 'gap_ms' in locals() else 0.0
                current_mean = mean_gap if 'mean_gap' in locals() else 0.0
                current_max = max_gap if 'max_gap' in locals() else 0.0
                current_std = std_gap if 'std_gap' in locals() else 0.0

                show_display(stdscr, log_path, msg_count, current_gap,
                             current_mean, current_max, current_std, tel)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        stdscr.addstr(10, 2, f"Error: {e}", curses.color_pair(1))
        stdscr.refresh()
        time.sleep(2)
    finally:
        # Safe cleanup
        curses.nocbreak()
        stdscr.keypad(False)
        curses.echo()
        curses.endwin()

        print("\n✓ Recording stopped cleanly.")
        print(f"Total messages received : {msg_count}")
        print(f"Log saved to            : {log_path}")
        print("\nNext step: Run case2_poa.py with Geth PoA running.\n")


if __name__ == '__main__':
    try:
        curses.wrapper(main)
    except Exception as e:
        curses.endwin()  # Extra safety
        print(f"\nUnexpected error: {e}")