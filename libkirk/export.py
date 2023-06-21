"""
.. module:: export
    :platform: Linux
    :synopsis: module containing exporters definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import json
import logging
from libkirk import KirkException
from libkirk.results import ResultStatus


class ExporterError(KirkException):
    """
    Raised when an error occurs during Exporter operations.
    """


class Exporter:
    """
    A class used to export Results into report file.
    """

    async def save_file(self, results: list, path: str) -> None:
        """
        Save report into a file by taking information from SUT and testing
        results.
        :param results: list of suite results to export.
        :type results: list(SuiteResults)
        :param path: path of the file to save.
        :type path: str
        """
        raise NotImplementedError()


class JSONExporter(Exporter):
    """
    Export testing results into a JSON file.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("kirk.json")

    # pylint: disable=too-many-locals
    async def save_file(self, results: list, path: str) -> None:
        if not results or len(results) == 0:
            raise ValueError("results is empty")

        if not path:
            raise ValueError("path is empty")

        if os.path.exists(path):
            raise ExporterError(f"'{path}' already exists")

        self._logger.info("Exporting JSON report into %s", path)

        results_json = []

        for result in results:
            for test_report in result.tests_results:
                status = ""
                if test_report.status == ResultStatus.PASS:
                    status = "pass"
                elif test_report.status == ResultStatus.BROK:
                    status = "brok"
                elif test_report.status == ResultStatus.WARN:
                    status = "warn"
                elif test_report.status == ResultStatus.CONF:
                    status = "conf"
                else:
                    status = "fail"

                data_test = {
                    "test_fqn": test_report.test.name,
                    "status": status,
                    "test": {
                        "command": test_report.test.command,
                        "arguments": test_report.test.arguments,
                        "log": test_report.stdout,
                        "retval": [str(test_report.return_code)],
                        "duration": test_report.exec_time,
                        "failed": test_report.failed,
                        "passed": test_report.passed,
                        "broken": test_report.broken,
                        "skipped": test_report.skipped,
                        "warnings": test_report.warnings,
                        "result": status,
                    },
                }

                results_json.append(data_test)

        data = {
            "results": results_json,
            "stats": {
                "runtime": results[0].exec_time,
                "passed": results[0].passed,
                "failed": results[0].failed,
                "broken": results[0].broken,
                "skipped": results[0].skipped,
                "warnings": results[0].warnings
            },
            "environment": {
                "distribution": results[0].distro,
                "distribution_version": results[0].distro_ver,
                "kernel": results[0].kernel,
                "arch": results[0].arch,
                "cpu": results[0].cpu,
                "swap": results[0].swap,
                "RAM": results[0].ram,
            },
        }

        with open(path, "w+", encoding='UTF-8') as outfile:
            json.dump(data, outfile, indent=4)

        self._logger.info("Report exported")
