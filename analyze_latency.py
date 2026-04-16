import pandas as pd
import glob
import os

def analyze_results():
    print("\n" + "="*50)
    print("  BLOCKCHAIN LATENCY QUANTITATIVE ANALYSIS")
    print("="*50 + "\n")

    # Path to your logs
    log_dir = 'thesis_logs'
    
    # 1. Look for baseline.csv
    baseline_path = os.path.join(log_dir, 'baseline.csv')
    
    # 2. Look for the most recent PoA log
    all_logs = glob.glob(os.path.join(log_dir, 'latency_log_*.csv'))
    if not all_logs:
        print("[ERROR] No PoA log files found!")
        return
    poa_path = max(all_logs, key=os.path.getctime) # Get the newest one

    files_to_process = [("BASELINE", baseline_path), ("PoA ACTIVE", poa_path)]

    results = []

    for label, path in files_to_process:
        if not os.path.exists(path):
            print(f"[SKIP] {label} file not found at {path}")
            continue
            
        df = pd.read_csv(path)
        
        # We skip the first 50 rows (approx 5 seconds) to allow 
        # the MAVLink buffer to stabilize for a cleaner measurement.
        df = df.iloc[50:] 

        metrics = {
            "Mode": label,
            "Avg Gap (ms)": df['Update_Gap_ms'].mean(),
            "Max Gap (ms)": df['Update_Gap_ms'].max(),
            "Jitter (StdDev)": df['Update_Gap_ms'].std(),
            "Total Samples": len(df)
        }
        results.append(metrics)

    # Display Table
    summary_df = pd.DataFrame(results)
    print(summary_df.to_string(index=False))
    
    # Calculate Overhead
    if len(results) == 2:
        overhead = ((results[1]['Avg Gap (ms)'] - results[0]['Avg Gap (ms)']) / results[0]['Avg Gap (ms)']) * 100
        print(f"\n[CONCLUSION] Blockchain induced a {overhead:.2f}% increase in average latency.")
        
        jitter_inc = results[1]['Jitter (StdDev)'] - results[0]['Jitter (StdDev)']
        print(f"[CONCLUSION] Blockchain increased flight control jitter by {jitter_inc:.2f}ms.")

if __name__ == "__main__":
    analyze_results()