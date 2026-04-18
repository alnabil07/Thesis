import pandas as pd
import glob
import os
import matplotlib.pyplot as plt
from datetime import datetime

def analyze_results():
    print("\n" + "="*70)
    print("      BLOCKCHAIN LATENCY FINAL QUANTITATIVE ANALYSIS")
    print("="*70 + "\n")

    # Log directory
    log_dir = '/home/merajpi/Nabil/logs'

    if not os.path.exists(log_dir):
        print(f"[ERROR] Log directory not found: {log_dir}")
        return

    # Find latest files
    baseline_path = os.path.join(log_dir, 'baseline.csv')

    idle_logs = glob.glob(os.path.join(log_dir, 'latency_log_*.csv'))
    idle_path = max(idle_logs, key=os.path.getctime) if idle_logs else None

    tx_logs = glob.glob(os.path.join(log_dir, 'latency_tx_*.csv'))
    tx_path = max(tx_logs, key=os.path.getctime) if tx_logs else None

    files_to_process = [
        ("BASELINE", baseline_path),
        ("PoA IDLE", idle_path),
        ("PoA ACTIVE (TX)", tx_path)
    ]

    results = []
    plot_data = []

    for label, path in files_to_process:
        if not path or not os.path.exists(path):
            print(f"[SKIP] {label} file not found.")
            continue

        df = pd.read_csv(path)

        # Detect latency column
        if 'Update_Gap_ms' in df.columns:
            latency_col = 'Update_Gap_ms'
        elif 'Latency_ms' in df.columns:
            latency_col = 'Latency_ms'
        else:
            print(f"[ERROR] No latency column found in {label}")
            print("   Columns:", df.columns.tolist())
            continue

        # Remove initial startup noise
        df = df.iloc[50:].reset_index(drop=True)

        metrics = {
            "Mode": label,
            "Avg Gap (ms)": df[latency_col].mean(),
            "Max Gap (ms)": df[latency_col].max(),
            "Jitter (StdDev)": df[latency_col].std(),
            "Samples": len(df)
        }
        results.append(metrics)

        plot_data.append((label, df[latency_col].copy()))

        print(f"[OK] {label:15} → Avg: {df[latency_col].mean():.2f} ms | "
              f"Std: {df[latency_col].std():.2f} ms | Samples: {len(df)}")

    # === Summary Table ===
    if results:
        summary_df = pd.DataFrame(results)
        print("\n" + summary_df.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    else:
        print("[ERROR] No valid log files were processed.")
        return

    # === Conclusions ===
    if len(results) >= 3:
        baseline_avg = results[0]['Avg Gap (ms)']
        active_avg = results[2]['Avg Gap (ms)']
        
        overhead = ((active_avg - baseline_avg) / baseline_avg) * 100
        jitter_impact = results[2]['Jitter (StdDev)'] - results[0]['Jitter (StdDev)']

        print(f"\n[CONCLUSION] Blockchain Overhead          : {overhead:.2f}%")
        print(f"[CONCLUSION] Jitter Increase under TX load : {jitter_impact:.3f} ms")

    # === GRAPH 1: Smoothed Latency Comparison ===
    if plot_data:
        plt.figure(figsize=(11, 6))
        STEP = 20
        window = 50

        for label, series in plot_data:
            smooth = series.rolling(window=window, min_periods=1).mean()
            plt.plot(smooth[::STEP], label=label, linewidth=1.8)

        plt.xlabel("Sample Index (downsampled)")
        plt.ylabel("Latency (ms)")
        plt.title("Telemetry Latency Comparison - Smoothed")
        
        # Auto y-limits
        all_values = pd.concat([s for _, s in plot_data])
        plt.ylim(max(0, all_values.min() * 0.85), all_values.max() * 1.15)

        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        timestamp_str = datetime.now().strftime("%H%M-%d%m%Y")
        save_path1 = os.path.join(log_dir, f"latency_comparison_{timestamp_str}.png")
        plt.savefig(save_path1, dpi=300)
        print(f"\n[INFO] Comparison graph saved → {save_path1}")
        plt.show()

    # === GRAPH 2: Latency Over Time (New) ===
    if plot_data:
        plt.figure(figsize=(12, 7))
        
        for i, (label, series) in enumerate(plot_data):
            # Raw data (light)
            plt.plot(series, alpha=0.25, linewidth=0.8, color=plt.cm.tab10(i))
            
            # Smoothed line (bold)
            smooth = series.rolling(window=100, min_periods=1).mean()
            plt.plot(smooth, label=f"{label} (smoothed)", linewidth=2.2, color=plt.cm.tab10(i))

        plt.xlabel("Sample Index (Time)")
        plt.ylabel("Latency (ms)")
        plt.title("Latency Over Time - Raw vs Smoothed")
        
        all_values = pd.concat([s for _, s in plot_data])
        plt.ylim(max(0, all_values.min() * 0.9), all_values.max() * 1.1)
        
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        save_path2 = os.path.join(log_dir, f"latency_over_time_{timestamp_str}.png")
        plt.savefig(save_path2, dpi=300)
        print(f"[INFO] Latency Over Time graph saved → {save_path2}")
        plt.show()


if __name__ == "__main__":
    analyze_results()