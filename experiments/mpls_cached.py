#!/usr/bin/python

import subprocess
import time
import os

from mininet.log import setLogLevel
from mininet.net import Mininet, CLI
from mininet.node import RemoteController

from topology.polska_4_hosts import Polska
from metrics.collector import MetricsCollector

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULTS_DIR = "results/mpls_cached/"
LOGS_DIR = "results/mpls_cached/logs"
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

PE_SWITCHES = ["Gdansk", "Rzeszow", "Wroclaw", "Szczecin"]


def start_ryu(env):
    return subprocess.Popen(
        ["ryu-manager", "mpls_controller_cached.py", "--observe-links"],
        # stdout=subprocess.DEVNULL,
        # stderr=subprocess.DEVNULL,
        env=env,
    )


def stop_ryu(proc):
    proc.terminate()

    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def setup_network():
    net = Mininet(topo=Polska(), controller=None)

    net.addController(
        "controller", controller=RemoteController, ip="127.0.0.1", port=6633
    )

    net.start()

    time.sleep(5)

    net.pingAll()

    return net


def start_traffic(net, warmup=10):
    hosts = {
        "h1": net.get("h_Gdansk"),
        "h2": net.get("h_Rzeszow"),
        "h3": net.get("h_Wroclaw"),
        "h4": net.get("h_Szczecin"),
    }

    for name, host in hosts.items():
        path = os.path.join(BASE_DIR, name)

        host.cmd(f"cd {path} && java -jar traffic.jar &")

    time.sleep(warmup)

    return list(hosts.values())


def run_experiment(run_id):
    net = setup_network()

    try:
        hosts = start_traffic(net)

        collector = MetricsCollector(
            net=net,
            hosts=hosts,
            pe_switches=PE_SWITCHES,
            p_switches=[sw.name for sw in net.switches],
        )

        collector.collect_all(
            throughput_csv=f"{RESULTS_DIR}/throughput_{run_id}.csv",
            flow_csv=f"{RESULTS_DIR}/flows_{run_id}.csv",
            control_csv=f"{RESULTS_DIR}/control_{run_id}.csv",
            duration=60,
            interval=1,
        )

    finally:
        net.stop()

def run_cli():
    net = setup_network()

    try:
        hosts = start_traffic(net)
        CLI(net)
    finally:
        net.stop()


if __name__ == "__main__":
    setLogLevel("info")

    RUNS = 3

    for run_id in range(1, RUNS + 1):
        env = os.environ.copy()
        env["RUN_ID"] = str(run_id)

        print(f"\n=== RUN {run_id} ===\n")

        subprocess.run(["sudo", "mn", "-c"])

        time.sleep(5)

        ryu_proc = start_ryu(env)

        time.sleep(8)

        try:
            run_experiment(run_id)

        finally:
            stop_ryu(ryu_proc)

    subprocess.run(["sudo", "mn", "-c"])

    # ryu_proc = start_ryu()
    # run_cli()
    # stop_ryu(ryu_proc)

    # subprocess.run(["sudo", "mn", "-c"])
