#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2025 Li Wang <liwang@redhat.com>
# Copyright (c) 2025 Ping Fang <pifang@redhat.com>
"""
This script parses JSON results from kirk and produces LTP traditional logs.
"""
import os
import json
import click

@click.command()
@click.option('--resfile', default='results.json', help='result file name')
@click.option('--sumfile', default='summary.log', help='summary file name')
@click.option('--failfile', default='fails.log', help='fail log file name')
@click.option('--runfile', default='run.log', help='run log file name')

def process_kirk_results(resfile, sumfile, runfile, failfile):
    summary = ''
    fail_logs = ''
    run_logs = ''

    # Load the results data from the JSON file
    with open(resfile, 'r') as results:
        results_data = json.load(results)

    for test in results_data['results']:
        test_fqn = test.get("test_fqn", "UNKNOWN")
        status = test.get("status", "unknown")
        summary += f'{test_fqn:30}{status}\n'

        test_data = test.get("test", {})
        command = test_data.get("command", "N/A")
        arguments = " ".join(test_data.get("arguments", []))
        output = test_data.get("log", "")
        duration = test_data.get("duration", 0.0)

        test_log = (
                f'==== {test_fqn} ====\n'
                f'command: {command} {arguments}\n'
                f'{output}\n'
                f'Duration: {duration:.3f}s\n\n\n'
                )

        run_logs += test_log

        if status not in ('pass', 'conf'):
            fail_logs += test_log

    stats = results_data.get("stats", {})
    env = results_data.get("environment", {})

    stats_env = (
            f'\n\nruntime:      {stats.get("runtime", 0.0):.3f}s'
            f'\npassed          {stats.get("passed", 0)}'
            f'\nfailed          {stats.get("failed", 0)}'
            f'\nbroken          {stats.get("broken", 0)}'
            f'\nskipped         {stats.get("skipped", 0)}'
            f'\nwarnings        {stats.get("warnings", 0)}'
            f'\nDistribution:   {env.get("distribution", "")}-'
            f'{env.get("distribution_version", "")}'
            f'\nKernel Version: {env.get("kernel", "")}'
            f'\nSWAP:           {env.get("swap", "")}'
            f'\nRAM:            {env.get("RAM", "")}'
            )

    with open(sumfile, 'w') as summary_file:
        summary_file.write(summary)
        summary_file.write(stats_env)

    with open(failfile, 'w') as fails_file:
        fails_file.write(fail_logs)

    with open(runfile, 'w') as run_file:
        run_file.write(run_logs)

if __name__ == "__main__":
    process_kirk_results()
