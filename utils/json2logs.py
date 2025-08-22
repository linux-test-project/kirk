#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2025 Li Wang <liwang@redhat.com>
# Copyright (c) 2025 Ping Fang <pifang@redhat.com>
"""
This script parses JSON results from kirk and produces LTP traditional logs.
"""

import argparse
import json


def process_kirk_results(resfile, sumfile, runfile, failfile):
    try:
        with open(resfile, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading JSON file: {e}")
        return

    summary_lines = []
    run_logs = []
    fail_logs = []

    for test in data.get("results", []):
        fqn = test.get("test_fqn", "UNKNOWN")
        status = test.get("status", "unknown")
        test_info = test.get("test", {})

        summary_lines.append(f"{fqn:30}{status}")

        command = test_info.get("command", "")
        arguments = " ".join(test_info.get("arguments", []))
        log = test_info.get("log", "")
        duration = test_info.get("duration", 0.0)

        test_log = (
            f"==== {fqn} ====\n"
            f"command: {command} {arguments}\n"
            f"{log}\n"
            f"Duration: {duration:.3f}s\n\n"
        )

        run_logs.append(test_log)

        if status not in ("pass", "conf"):
            fail_logs.append(test_log)
            with open(f"{fqn}.fail.log", "w") as f:
                f.write(test_log)

    env = data.get("environment", {})
    stats = data.get("stats", {})

    stats_summary = (
        f"\n\nruntime:      {stats.get('runtime', 0.0):.3f}s\n"
        f"passed        {stats.get('passed', 0)}\n"
        f"failed        {stats.get('failed', 0)}\n"
        f"broken        {stats.get('broken', 0)}\n"
        f"skipped       {stats.get('skipped', 0)}\n"
        f"warnings      {stats.get('warnings', 0)}\n"
        f"Distribution: {env.get('distribution', '')}-{env.get('distribution_version', '')}\n"
        f"Kernel:       {env.get('kernel', '')}\n"
        f"SWAP:         {env.get('swap', '')}\n"
        f"RAM:          {env.get('RAM', '')}\n"
    )

    with open(sumfile, "w") as f:
        f.write("\n".join(summary_lines))
        f.write(stats_summary)

    with open(runfile, "w") as f:
        f.write("".join(run_logs))

    with open(failfile, "w") as f:
        f.write("".join(fail_logs))

    print(f"Logs written to:\n  {sumfile}\n  {runfile}\n  {failfile}")


def run():
    parser = argparse.ArgumentParser(description="Process Kirk test results from JSON.")
    parser.add_argument(
        "--resfile", default="results.json", help="Input JSON result file"
    )
    parser.add_argument("--sumfile", default="summary.log", help="Summary output file")
    parser.add_argument("--failfile", default="fails.log", help="Failures log file")
    parser.add_argument("--runfile", default="run.log", help="All runs log file")

    args = parser.parse_args()
    process_kirk_results(args.resfile, args.sumfile, args.runfile, args.failfile)


if __name__ == "__main__":
    run()
