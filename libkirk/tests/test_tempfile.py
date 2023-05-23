"""
Unittest for temporary module.
"""
import os
import pytest
from libkirk.tempfile import TempDir


class TestTempDir:
    """
    Test the TempDir class implementation.
    """

    def test_constructor(self):
        """
        Test TempDir constructor.
        """
        with pytest.raises(ValueError):
            TempDir(root="this_folder_doesnt_exist")

    # for some reasons, following test fails on systems which are slow
    # to release directories after remove (in particular remote containers)
    # even after os.sync or time.sleep. So we XFAIL this test by default
    @pytest.mark.xfail
    def test_rotate(self, tmpdir):
        """
        Test folders rotation.
        """
        max_rotate = 5
        plus_rotate = 5

        currdir = str(tmpdir)

        tempdir = None
        for _ in range(0, max_rotate + plus_rotate):
            tempdir = TempDir(currdir, max_rotate=max_rotate)

            assert tempdir.abspath is not None
            assert tempdir.abspath == os.readlink(
                os.path.join(tempdir.abspath, "..", tempdir.SYMLINK_NAME))

        os.sync()

        total = 0
        for _, dirs, _ in os.walk(os.path.join(tempdir.abspath, "..")):
            for mydir in dirs:
                if mydir != "latest":
                    total += 1

        assert total == max_rotate

    def test_rotate_empty_root(self):
        """
        Test folders rotation with empty root.
        """
        tempdir = TempDir(None)
        assert not os.path.isdir(tempdir.abspath)

    def test_mkdir(self, tmpdir):
        """
        Test mkdir method.
        """
        tempdir = TempDir(str(tmpdir))
        tempdir.mkdir("myfolder")
        assert os.path.isdir(os.path.join(tempdir.abspath, "myfolder"))

        for i in range(0, 10):
            tempdir.mkdir(f"myfolder/{i}")
            assert os.path.isdir(os.path.join(
                tempdir.abspath, f"myfolder/{i}"))

    def test_mkdir_no_root(self):
        """
        Test mkdir method without root.
        """
        tempdir = TempDir(None)
        tempdir.mkdir("myfolder")
        assert not os.path.isdir(os.path.join(tempdir.abspath, "myfolder"))

    def test_mkfile(self, tmpdir):
        """
        Test mkfile method.
        """
        content = "mystuff"
        tempdir = TempDir(str(tmpdir))

        for i in range(0, 10):
            tempdir.mkfile(f"myfile{i}", content)

            pos = os.path.join(tempdir.abspath, f"myfile{i}")
            assert os.path.isfile(pos)
            assert open(pos, "r").read() == "mystuff"

    def test_mkfile_no_root(self):
        """
        Test mkfile method without root.
        """
        content = "mystuff"
        tempdir = TempDir(None)

        tempdir.mkfile("myfile", content)
        assert not os.path.isfile(os.path.join(tempdir.abspath, "myfile"))

    def test_mkdir_mkfile(self, tmpdir):
        """
        Test mkfile after mkdir.
        """
        content = "mystuff"
        tempdir = TempDir(str(tmpdir))

        tempdir.mkdir("mydir")
        tempdir.mkfile("mydir/myfile", content)

        pos = os.path.join(tempdir.abspath, "mydir", "myfile")
        assert os.path.isfile(pos)
        assert open(pos, "r").read() == "mystuff"
