"""
Test kselftest implementations.
"""
import os
import pytest
from libkirk.data import Test
from libkirk.host import HostSUT
from libkirk.kselftests import KselftestFramework

pytestmark = pytest.mark.asyncio


class TestKselftestsFramework:
    """
    Kselftests framework unittests.
    """
    GROUPS = [
        "cgroup",
        "bpf"
    ]

    TESTS = [
        "test_first",
        "test_second",
        "test_third",
        "test_fourth"
    ]

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
    def framework(self, tmpdir):
        """
        LTP framework object.
        """
        fw = KselftestFramework()
        fw.setup(root=str(tmpdir))

        yield fw

    @pytest.fixture(autouse=True)
    def prepare_tmpdir(self, tmpdir):
        """
        Prepare the temporary directory adding runtest folder.
        """
        for group in self.GROUPS:
            group_dir = tmpdir.mkdir(group)

            if group == "cgroup":
                for name in self.TESTS:
                    # use a generic script simulating binary build
                    test_binfile = group_dir / name
                    test_binfile.write(f"#!/bin/sh\n\necho -n {name}\n")

                    # source code of the test we are simulating
                    test_file = group_dir / f"{name}.c"
                    test_file.write("int main() { return 0; }\n\n")

            if group == "bpf":
                test_binfile = group_dir / "test_progs"
                with test_binfile.open('w') as f:
                    print("#!/bin/sh\n", file=f)

                    for name in self.TESTS:
                        print(f"echo {name}", file=f)

                test_binfile.chmod(0o700)

    def test_name(self, framework):
        """
        Test that name property is not empty.
        """
        assert framework.name == "kselftests"

    async def test_get_suites(self, framework, sut):
        """
        Test get_suites method.
        """
        suites = await framework.get_suites(sut)
        assert suites == self.GROUPS

    async def test_find_command(self, framework, sut, tmpdir):
        """
        Test find_command method.
        """
        test = await framework.find_command(sut, "test_progs")
        assert test.name == "test_progs"
        assert test.command == "test_progs"
        assert not test.arguments
        assert not test.parallelizable
        assert test.env == {"PATH": str(tmpdir / "bpf")}
        assert test.cwd == str(tmpdir / "bpf")

    async def test_find_suite(self, framework, sut, tmpdir):
        """
        Test find_suite method.
        """
        for group in self.GROUPS:
            suite = await framework.find_suite(sut, group)

            assert len(suite.tests) == len(self.TESTS)

            for i in range(0, len(self.TESTS)):
                test = suite.tests[i]

                assert not test.env
                assert test.cwd == str(tmpdir / group)
                assert not test.parallelizable

                if suite == "cgroup":
                    assert os.path.basename(test.command) in self.TESTS
                    assert not test.arguments
                elif suite == "bpf":
                    assert test.command == "./test_progs"
                    assert test.arguments[0] == "-t"
                    assert test.arguments[1] in self.TESTS

    async def test_read_result_passed(self, framework):
        """
        Test read_result method when test passes.
        """
        test = Test(name="test", cmd="echo", args="ciao")
        result = await framework.read_result(test, 'ciao\n', 0, 0.1)
        assert result.passed == 1
        assert result.failed == 0
        assert result.broken == 0
        assert result.skipped == 0
        assert result.warnings == 0
        assert result.exec_time == 0.1
        assert result.test == test
        assert result.return_code == 0
        assert result.stdout == "ciao\n"

    async def test_read_result_failure(self, framework):
        """
        Test read_result method when test fails.
        """
        test = Test(name="test", cmd="echo")
        result = await framework.read_result(test, '', 1, 0.1)
        assert result.passed == 0
        assert result.failed == 1
        assert result.broken == 0
        assert result.skipped == 0
        assert result.warnings == 0
        assert result.exec_time == 0.1
        assert result.test == test
        assert result.return_code == 1
        assert result.stdout == ""

    async def test_read_result_broken(self, framework):
        """
        Test read_result method when test is broken.
        """
        test = Test(name="test", cmd="echo")
        result = await framework.read_result(test, '', -1, 0.1)
        assert result.passed == 0
        assert result.failed == 0
        assert result.broken == 1
        assert result.skipped == 0
        assert result.warnings == 0
        assert result.exec_time == 0.1
        assert result.test == test
        assert result.return_code == -1
        assert result.stdout == ""

    async def test_read_result_skipped(self, framework):
        """
        Test read_result method when test has skip.
        """
        test = Test(name="test", cmd="echo", args=["skip"])
        result = await framework.read_result(test, "skip\n", 4, 0.1)
        assert result.passed == 0
        assert result.failed == 0
        assert result.broken == 0
        assert result.skipped == 1
        assert result.warnings == 0
        assert result.exec_time == 0.1
        assert result.test == test
        assert result.return_code == 4
        assert result.stdout == "skip\n"
