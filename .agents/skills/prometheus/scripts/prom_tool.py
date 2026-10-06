#!/usr/bin/env python3
"""Prometheus and Alertmanager diagnostic CLI tool for elite-flux-cluster.

Queries Prometheus and Alertmanager via Kubernetes API server proxy using
'kubectl get --raw', eliminating the need for port-forwarding or in-pod curl.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path

# Handle BrokenPipeError cleanly when piped to head/less/etc.
signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def get_kubeconfig_arg() -> list[str]:
    """Find the active kubeconfig path and return kubectl argument list."""
    if os.environ.get("KUBECONFIG"):
        return ["--kubeconfig", os.environ["KUBECONFIG"]]
    candidate = Path.home() / ".kube" / "config" / "k3s.yaml"
    if candidate.is_file():
        return ["--kubeconfig", str(candidate)]
    standard = Path.home() / ".kube" / "config"
    if standard.is_file():
        return ["--kubeconfig", str(standard)]
    return []


def kubectl_raw(path: str) -> dict | list:
    """Execute 'kubectl get --raw <path>' and parse JSON response."""
    cmd = ["kubectl", "get", "--raw", path] + get_kubeconfig_arg()
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(f"Error querying {path}:\n{result.stderr}\n")
        sys.exit(result.returncode)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as err:
        sys.stderr.write(f"Failed to decode JSON from {path}: {err}\n")
        sys.exit(1)


def cmd_alerts(args: argparse.Namespace) -> None:
    """Fetch and categorize active alerts from Alertmanager."""
    path = "/api/v1/namespaces/observability/services/kube-prometheus-stack-alertmanager:9093/proxy/api/v2/alerts"
    alerts = kubectl_raw(path)
    if not isinstance(alerts, list):
        sys.stderr.write("Unexpected alert payload format.\n")
        return

    # Filter active only unless --all specified
    if not args.all:
        alerts = [a for a in alerts if a.get("status", {}).get("state") == "active"]

    by_name = defaultdict(list)
    for a in alerts:
        name = a.get("labels", {}).get("alertname", "Unknown")
        by_name[name].append(a)

    print(f"Total alerts: {len(alerts)} across {len(by_name)} alert types\n")
    for name, group in sorted(by_name.items(), key=lambda x: len(x[1]), reverse=True):
        sev = group[0].get("labels", {}).get("severity", "unknown")
        print(f"=== {name} [{sev.upper()}] (Count: {len(group)}) ===")
        for a in group:
            labels = a.get("labels", {})
            ann = a.get("annotations", {})
            summary = ann.get("summary") or ann.get("description") or ""
            desc = ann.get("description") or ""
            ns = labels.get("namespace") or labels.get("exported_namespace", "")
            pod = labels.get("pod", "")
            ds = labels.get("daemonset", "")
            pvc = labels.get("persistentvolumeclaim", "")
            res = labels.get("name", "")
            info_parts = [f"{k}={v}" for k, v in [("ns", ns), ("pod", pod), ("ds", ds), ("pvc", pvc), ("name", res)] if v]
            info_str = f"[{', '.join(info_parts)}] " if info_parts else ""
            print(f"  * {info_str}{summary}")
            if desc and desc != summary and args.verbose:
                print(f"      Details: {desc}")
        print()


def cmd_targets(args: argparse.Namespace) -> None:
    """Fetch scrape targets and show unhealthy targets."""
    path = "/api/v1/namespaces/observability/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/targets"
    data = kubectl_raw(path)
    active = data.get("data", {}).get("activeTargets", [])
    down = [t for t in active if t.get("health") != "up"]

    print(f"Scrape Targets: {len(active)} active, {len(down)} failing/down\n")
    if not down:
        print("All targets healthy!")
        return

    for t in down:
        labels = t.get("labels", {})
        job = labels.get("job", "unknown")
        instance = labels.get("instance", "unknown")
        health = t.get("health", "unknown").upper()
        last_error = t.get("lastError", "No error reported")
        scrape_url = t.get("scrapeUrl", "")
        print(f"[{health}] Job: {job} | Instance: {instance}")
        print(f"  URL: {scrape_url}")
        print(f"  Error: {last_error}\n")


def cmd_query(args: argparse.Namespace) -> None:
    """Execute PromQL query and print results."""
    encoded_query = urllib.parse.quote(args.promql)
    path = f"/api/v1/namespaces/observability/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query={encoded_query}"
    data = kubectl_raw(path)
    result = data.get("data", {}).get("result", [])
    print(f"Query: {args.promql}")
    print(f"Results: {len(result)}\n")
    for item in result:
        metric = item.get("metric", {})
        value = item.get("value", [])
        val = value[1] if len(value) > 1 else ""
        metric_str = ", ".join(f'{k}="{v}"' for k, v in metric.items())
        print(f"{{{metric_str}}} => {val}")


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Prometheus & Alertmanager inspection tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_alerts = subparsers.add_parser("alerts", help="List active firing alerts")
    p_alerts.add_argument("-v", "--verbose", action="store_true", help="Show full descriptions")
    p_alerts.add_argument("-a", "--all", action="store_true", help="Include non-active alerts")
    p_alerts.set_defaults(func=cmd_alerts)

    p_targets = subparsers.add_parser("targets", help="List failing scrape targets")
    p_targets.set_defaults(func=cmd_targets)

    p_query = subparsers.add_parser("query", help="Execute PromQL query")
    p_query.add_argument("promql", help="PromQL expression string")
    p_query.set_defaults(func=cmd_query)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
