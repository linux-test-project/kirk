"""
.. module:: parallelizable
    :platform: Linux
    :synopsis: Script that checks how many LTP tests can run in parallel
.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import kirk.data
import kirk
import os
import sys
import json
import argparse
import asyncio

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))


async def get_suites(args: argparse.Namespace) -> list:
    """
    Read runtest files and return a list of suites.
    """
    # read runtest names
    runtest_path = os.path.join(args.ltp_dir, "runtest")
    runtest_names = []
    if args.runtest:
        runtest_names.extend(args.runtest)
    else:
        for (_, _, filenames) in os.walk(runtest_path):
            runtest_names.extend(filenames)
            break

    runtests = [
        os.path.join(runtest_path, runtest)
        for runtest in runtest_names
    ]

    # read metadata
    metadata = os.path.join(args.ltp_dir, "metadata", "ltp.json")
    metadata_content = None
    with open(metadata, 'r') as metadata_f:
        metadata_content = json.loads(metadata_f.read())

    # create tasks
    tasks = []
    for runtest in runtests:
        with open(runtest, 'r') as runtest_f:
            task = kirk.data.read_runtest(
                os.path.basename(runtest),
                runtest_f.read(),
                metadata=metadata_content)

            tasks.append(task)

    # execute tasks
    suites = await asyncio.gather(*tasks)
    return suites


async def print_results(suites: list) -> None:
    """
    Print results on console.
    """
    suites_tests = 0
    suites_parallel = 0

    for suite in suites:
        parallel = 0

        for test in suite.tests:
            parallel += 1 if test.parallelizable else 0

        suites_tests += len(suite.tests)
        suites_parallel += parallel

        print(f"Suite: {suite.name}")
        print(f"Total tests: {len(suite.tests)}")
        print(f"Parallelizable tests: {parallel}")
        print()

    percent = (suites_parallel * 100.0) / suites_tests

    print("-------------------------------")
    print(f"Total tests: {suites_tests}")
    print(f"Parallelizable tests: {suites_parallel}")
    print()
    print(f"{percent:.2f}% of the tests are parallelizable")
    print()


async def main(args: argparse.Namespace) -> None:
    """
    Main function of the script.
    """
    suites = await get_suites(args)
    await print_results(suites)


if __name__ == "__main__":
    """
    Script entry point.
    """
    parser = argparse.ArgumentParser(
        description='Parallel testing analysis script for LTP')
    parser.add_argument(
        "--ltp-dir",
        "-l",
        type=str,
        default="/opt/ltp",
        help="LTP install directory")
    parser.add_argument(
        "--runtest",
        "-r",
        nargs="*",
        help="List of runtest files path to analyse")

    args = parser.parse_args()

    if not os.path.isdir(args.ltp_dir):
        parser.error("LTP directory doesn't exist")

    if args.runtest:
        for runtest in args.runtest:
            if not os.path.isfile(
                    os.path.join(args.ltp_dir, "runtest", runtest)):
                parser.error(f"'{runtest}' runtest file doesn't exist")

    kirk.run(main(args))
