"""
Unittest for liburing module.
"""
import stat
import pytest
from libkirk.data import Test
from libkirk.host import HostSUT
from libkirk.liburing import Liburing

pytestmark = pytest.mark.asyncio


class TestLiburing:
    """
    Tests for Liburing framework implementation.
    """
    TESTS_NUM = 10

    @pytest.fixture(autouse=True)
    def prepare_tmpdir(self, tmpdir):
        """
        Prepare the temporary directory adding liburing like tests.
        """
        makefile = tmpdir / "Makefile"
        makefile.write('test_targets = ')
        names = []

        for i in range(0, self.TESTS_NUM):
            name = f"test{i}"
            names.append(name)

            test = tmpdir / f"test{i}"
            test.write(f"echo -n {i}")
            test.chmod(stat.S_IEXEC)

            test = tmpdir / f"test{i}.c"
            test.write("void main() {}")

        makefile.write('test_targets = ' + ' '.join(names))

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
        The liburing framework object.
        """
        obj = Liburing()
        obj.setup(root=str(tmpdir))
        yield obj

    async def test_get_suites(self, framework, sut):
        """
        Test get_suites method.
        """
        suites = await framework.get_suites(sut)
        assert suites == ["default"]

    async def test_find_command(self, framework, sut, tmpdir):
        """
        Test find_command method.
        """
        test = await framework.find_command(sut, "test0 ciao bepi")
        assert test.name == "test0"
        assert test.command == "test0"
        assert test.arguments == ["ciao", "bepi"]
        assert not test.parallelizable
        assert test.env == {"PATH": str(tmpdir)}
        assert test.cwd == str(tmpdir)

    async def test_find_suite(self, framework, sut, tmpdir):
        """
        Test find_suite method.
        """
        suite = await framework.find_suite(sut, "default")

        assert len(suite.tests) == self.TESTS_NUM
        for i in range(0, self.TESTS_NUM):
            test = tmpdir / f"test{i}"
            assert suite.tests[i].command == str(test)
            assert not suite.tests[i].arguments
            assert not suite.tests[i].env
            assert suite.tests[i].cwd == str(tmpdir)
            assert suite.tests[i].parallelizable

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
        test = Test(name="test", cmd="echo",
                    args=["skipping", "test", "\n", "skipping", "test"])
        result = await framework.read_result(
            test, "skipping test\nskipping test\n", 0, 0.1)
        assert result.passed == 1
        assert result.failed == 0
        assert result.broken == 0
        assert result.skipped == 2
        assert result.warnings == 0
        assert result.exec_time == 0.1
        assert result.test == test
        assert result.return_code == 0
        assert result.stdout == "skipping test\nskipping test\n"
