"""
Test Framework implementations.
"""
import os
import json
import pytest
from libkirk.ltp import LTPFramework
from libkirk.host import HostSUT

pytestmark = pytest.mark.asyncio


class TestLTPFramework:
    """
    Inherit this class to implement framework tests.
    """
    TESTS_NUM = 6
    SUITES_NUM = 3

    @pytest.fixture
    async def sut(self):
        """
        Host SUT communication object.
        """
        obj = HostSUT()
        obj.setup()

        await obj.communicate()
        yield obj
        await obj.stop()

    @pytest.fixture
    def ltp(self, tmpdir):
        """
        LTP framework object.
        """
        fw = LTPFramework()
        fw.setup(root=str(tmpdir))

        yield fw

    @pytest.fixture(autouse=True)
    def prepare_tmpdir(self, tmpdir):
        """
        Prepare the temporary directory adding runtest folder.
        """
        # create simple testing suites
        content = ""
        for i in range(self.TESTS_NUM):
            content += f"test0{i} echo ciao\n"

        tmpdir.mkdir("testcases").mkdir("bin")
        runtest = tmpdir.mkdir("runtest")

        for i in range(self.SUITES_NUM):
            suite = runtest / f"suite{i}"
            suite.write(content)

        # create a suite that is executing slower than the others
        # and it's parallelizable
        content = ""
        for i in range(self.TESTS_NUM, self.TESTS_NUM * 2):
            content += f"slow_test0{i} sleep 0.05\n"

        suite = runtest / f"slow_suite"
        suite.write(content)

        tests = {}
        for i in range(self.TESTS_NUM, self.TESTS_NUM * 2):
            name = f"slow_test0{i}"
            tests[name] = {}

        metadata_d = {"tests": tests}
        metadata = tmpdir.mkdir("metadata") / "ltp.json"
        metadata.write(json.dumps(metadata_d))

    def test_name(self, ltp):
        """
        Test that name property is not empty.
        """
        assert ltp.name == "ltp"

    async def test_get_suites(self, ltp, sut, tmpdir):
        """
        Test get_suites method.
        """
        suites = await ltp.get_suites(sut)
        assert "suite0" in suites
        assert "suite1" in suites
        assert "suite2" in suites
        assert "slow_suite" in suites

    async def test_find_suite(self, ltp, sut, tmpdir):
        """
        Test find_suite method.
        """
        for i in range(self.SUITES_NUM):
            suite = await ltp.find_suite(sut, f"suite{i}")
            assert len(suite.tests) == self.TESTS_NUM

            for j in range(self.TESTS_NUM):
                test = suite.tests[j]
                assert test.name == f"test0{j}"
                assert test.command == "echo"
                assert test.arguments == ["ciao"]
                assert test.cwd == os.path.join(
                    str(tmpdir),
                    "testcases",
                    "bin")
                assert not test.parallelizable
                assert "LTPROOT" in test.env
                assert "TMPDIR" in test.env
                assert "LTP_COLORIZE_OUTPUT" in test.env

        suite = await ltp.find_suite(sut, "slow_suite")
        assert len(suite.tests) == self.TESTS_NUM

        for test in suite.tests:
            assert test.command == "sleep"
            assert test.arguments == ["0.05"]
            assert test.cwd == os.path.join(
                str(tmpdir),
                "testcases",
                "bin")
            assert test.parallelizable
            assert "LTPROOT" in test.env
            assert "TMPDIR" in test.env
            assert "LTP_COLORIZE_OUTPUT" in test.env
