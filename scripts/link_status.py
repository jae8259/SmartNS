import os
import time
import subprocess
from datetime import datetime

# === 配置区 ===
RDMA_DEV = "mlx5_0"
RDMA_PORT = "1"
NET_DEV = "enp28s0np0"

RDMA_METRICS = [
    "np_ecn_marked_roce_packets",  # 收到带ECN的包
    "roce_adp_retrans",  # 丢包引发的重传
    "roce_out_of_sequence",  # 乱序包数量
    "rx_out_of_buffer",  # WQE 耗尽导致的丢包，可能是主机侧 polling 线程太慢了
    "rx_discards_phy",
    "tx_discards_phy",
    "local_ack_timeout_err"  # 本地 ack 超时未收到回包导致的丢包
]

ETHTOOL_METRICS = [
    "rx_pause_ctrl_phy",
    "tx_pause_ctrl_phy",
    "rx_prio3_pause",
    "tx_prio3_pause"
]


def read_rdma_counters():
    counters = {}
    base_path = f"/sys/class/infiniband/{RDMA_DEV}/ports/{RDMA_PORT}/hw_counters/"
    for metric in RDMA_METRICS:
        filepath = os.path.join(base_path, metric)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    counters[metric] = int(f.read().strip())
            except Exception:
                counters[metric] = 0
    return counters


def read_ethtool_counters():
    counters = {}
    try:
        result = subprocess.run(
            ["ethtool", "-S", NET_DEV], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                parts = line.strip().split(': ')
                if len(parts) == 2 and parts[0].strip() in ETHTOOL_METRICS:
                    counters[parts[0].strip()] = int(parts[1])
    except FileNotFoundError:
        pass
    return counters


def main():
    print(
        f"Monitoring {RDMA_DEV}/{NET_DEV} counters every second. Press Ctrl+C to stop.\n")

    prev_rdma = read_rdma_counters()
    prev_ethtool = read_ethtool_counters()

    try:
        while True:
            time.sleep(1.0)
            curr_rdma = read_rdma_counters()
            curr_ethtool = read_ethtool_counters()

            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            print(f"[{timestamp}] Counters Update:")

            # 打印 RDMA 指标
            for metric in RDMA_METRICS:
                old_val = prev_rdma.get(metric, 0)
                new_val = curr_rdma.get(metric, 0)
                print(
                    f"  [RDMA] {metric}: +{new_val - old_val} (Total: {new_val})")

            # 打印 Ethtool 指标
            for metric in ETHTOOL_METRICS:
                old_val = prev_ethtool.get(metric, 0)
                new_val = curr_ethtool.get(metric, 0)
                print(
                    f"  [ETH]  {metric}: +{new_val - old_val} (Total: {new_val})")

            print("-" * 50)

            prev_rdma = curr_rdma
            prev_ethtool = curr_ethtool

    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
