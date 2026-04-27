"""
CASE 1: BASELINE - Pure MAVLink Latency Measurement (No Blockchain)
"""

import time
import csv
import os
import sys
import curses
from datetime import datetime
from pymavlink import mavutil

# ========================== CONFIG ==========================
DEVICE = '/dev/ttyAMA0'
BAUD = 921600
LOG_DIR = "/home/merajpi/Nabil/logs"
DISPLAY_INTERVAL = 0.2   # How often to refresh screen (seconds)

# ============================================================
os.makedirs(LOG_DIR, exist_ok=True)
timestamp_str = datetime.now().strftime("%H%M-%d%m%Y")
log_filename = os.path.join(LOG_DIR, f"case1_baseline_{timestamp_str}.csv")

def safe_addstr(stdscr, y, x, text, attr=0):
    """Safe print that won't crash if text goes out of bounds"""
    try:
        h, w = stdscr.getmaxyx()
        if y >= h or x >= w - 1:
            return
        stdscr.addstr(y, x, text[:w - x - 1], attr)
    except:
        pass

def main(stdscr):
    # Curses setup
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)

    # Connect to Pixhawk
    safe_addstr(stdscr, 1, 2, "Connecting to Pixhawk via MAVLink...", curses.A_BOLD)
    stdscr.refresh()

    try:
        conn = mavutil.mavlink_connection(DEVICE, baud=BAUD)
        conn.wait_heartbeat(timeout=10)
        safe_addstr(stdscr, 2, 2, f"✓ Connected! System ID: {conn.target_system}", curses.color_pair(1))
    except Exception as e:
        safe_addstr(stdscr, 2, 2, f"✗ Connection Failed: {e}", curses.color_pair(2))
        stdscr.refresh()
        stdscr.getch()
        return

    # Request high-rate telemetry
    conn.mav.request_data_stream_send(
        conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 20, 1
    )

    # Create CSV log
    with open(log_filename, mode='w', newline='') as f:
        csv.writer(f).writerow(["Timestamp", "Telemetry_Gap_ms", "Mean_Gap_ms", "Max_Gap_ms"])

    safe_addstr(stdscr, 4, 2, f"Logging to: {os.path.basename(log_filename)}", curses.A_BOLD)
    safe_addstr(stdscr, 6, 2, "Starting measurement in 2 seconds...", curses.A_BOLD)
    stdscr.refresh()
    time.sleep(2)

    # Variables
    last_msg_time = time.perf_counter()
    last_display = time.perf_counter()
    msg_count = 0
    gaps = []                     # For mean/max calculation
    current_gap = 0.0
    mean_gap = 0.0
    max_gap = 0.0

    safe_addstr(stdscr, 8, 2, "Recording MAVLink latency... (Press Ctrl+C to stop)", curses.A_BOLD)
    stdscr.refresh()

    try:
        while True:
            msg = conn.recv_match(blocking=False)

            if msg:
                now = time.perf_counter()
                current_gap = (now - last_msg_time) * 1000.0   # in ms
                last_msg_time = now
                msg_count += 1

                gaps.append(current_gap)
                if len(gaps) > 100:          # Keep last 100 samples
                    gaps.pop(0)

                mean_gap = sum(gaps) / len(gaps)
                max_gap = max(gaps) if gaps else 0.0

                # Log to CSV
                with open(log_filename, mode='a', newline='') as f:
                    csv.writer(f).writerow([
                        datetime.now().isoformat(),
                        f"{current_gap:.3f}",
                        f"{mean_gap:.3f}",
                        f"{max_gap:.3f}"
                    ])

            else:
                time.sleep(0.001)   # Prevent 100% CPU

            # Update display
            if time.perf_counter() - last_display >= DISPLAY_INTERVAL:
                last_display = time.perf_counter()

                stdscr.clear()
                h, w = stdscr.getmaxyx()

                safe_addstr(stdscr, 0, 0, "=" * (w-2), curses.A_BOLD)
                safe_addstr(stdscr, 1, 2, "THESIS — CASE 1: BASELINE (No Blockchain)", curses.A_BOLD | curses.A_REVERSE)
                safe_addstr(stdscr, 2, 0, "=" * (w-2), curses.A_BOLD)

                safe_addstr(stdscr, 4, 2, f"Messages Received : {msg_count:,}")
                safe_addstr(stdscr, 5, 2, f"Log File          : {os.path.basename(log_filename)}")

                safe_addstr(stdscr, 7, 2, "TELEMETRY LATENCY", curses.A_BOLD | curses.color_pair(3))
                safe_addstr(stdscr, 9, 4, f"Current Gap   : {current_gap:8.3f} ms")
                safe_addstr(stdscr, 10, 4, f"Mean Gap      : {mean_gap:8.3f} ms")
                safe_addstr(stdscr, 11, 4, f"Max Gap       : {max_gap:8.3f} ms")

                safe_addstr(stdscr, 13, 2, "BLOCKCHAIN : DISABLED (Pure Baseline)", curses.color_pair(2) | curses.A_BOLD)

                safe_addstr(stdscr, h-3, 2, "Press Ctrl+C to stop recording", curses.A_BOLD)
                safe_addstr(stdscr, h-2, 0, "=" * (w-2), curses.A_BOLD)

                stdscr.refresh()

    except KeyboardInterrupt:
        pass
    finally:
        curses.nocbreak()
        stdscr.keypad(False)
        curses.echo()
        curses.endwin()

        print("\n✓ Stopped cleanly.")
        print(f"Total messages received : {msg_count}")
        print(f"Log saved to            : {log_filename}")
        print("\nYou now have pure baseline latency data (no blockchain overhead).")


if __name__ == '__main__':
    try:
        curses.wrapper(main)
    except Exception as e:
        curses.endwin()
        print(f"Error: {e}")