"""
Unittests for data module.
"""
import asyncio
import pytest
import kirk.data


pytestmark = pytest.mark.asyncio


async def test_read_runtest_error():
    """
    Test read_runtest method when raising errors.
    """
    with pytest.raises(ValueError):
        await kirk.data.read_runtest("suite", None)

    with pytest.raises(ValueError):
        await kirk.data.read_runtest("suite", "test01")


async def test_read_runtest():
    """
    Test read_runtest method.
    """
    tasks = []
    for i in range(100):
        content = "# this is a test file\ntest01 test -f .\ntest02 test -d .\n"
        tasks.append(kirk.data.read_runtest(f"suite{i}", content))

    suites = await asyncio.gather(*tasks, return_exceptions=True)

    for suite in suites:
        assert suite.tests[0].name == "test01"
        assert suite.tests[0].command == "test"
        assert suite.tests[0].arguments == ['-f', '.']
        assert not suite.tests[0].parallelizable

        assert suite.tests[1].name == "test02"
        assert suite.tests[1].command == "test"
        assert suite.tests[1].arguments == ['-d', '.']
        assert not suite.tests[1].parallelizable


async def test_read_runtest_metadata_blacklist():
    """
    Test read_runtest method using metadata to blacklist some tests.
    """
    tasks = []
    for param in kirk.data.PARALLEL_BLACKLIST:
        content = "# this is a test file\ntest01 test -f .\ntest02 test -d .\n"
        metadata = {
            "tests": {
                "test01": {
                    param: "myvalue"
                },
                "test02": {}
            }
        }

        tasks.append(kirk.data.read_runtest(
            "suite",
            content,
            metadata=metadata))

    suites = await asyncio.gather(*tasks, return_exceptions=True)

    for suite in suites:
        assert suite.name == "suite"
        assert suite.tests[0].name == "test01"
        assert suite.tests[0].command == "test"
        assert suite.tests[0].arguments == ['-f', '.']
        assert not suite.tests[0].parallelizable

        assert suite.tests[1].name == "test02"
        assert suite.tests[1].command == "test"
        assert suite.tests[1].arguments == ['-d', '.']
        assert suite.tests[1].parallelizable
