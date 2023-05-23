"""
.. module:: tempfile
    :platform: Linux
    :synopsis: module that contains temporary files handling

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import pwd
import shutil
import pathlib
import tempfile


class TempDir:
    """
    Temporary directory handler.
    """
    SYMLINK_NAME = "latest"
    FOLDER_PREFIX = "kirk."

    def __init__(self, root: str = None, max_rotate: int = 5) -> None:
        """
        :param root: root directory (i.e. /tmp). If None, TempDir will handle
            requests without adding any file or directory.
        :type root: str | None
        :param max_rotate: maximum number of temporary directories
        :type max_rotate: int
        """
        if root and not os.path.isdir(root):
            raise ValueError(f"root folder doesn't exist: {root}")

        self._root = root
        if root:
            self._root = os.path.abspath(root)

        self._max_rotate = max(max_rotate, 0)
        self._folder = self._rotate()

    def _rotate(self) -> str:
        """
        Check for old folders and remove them, then create a new one and return
        its full path.
        """
        if not self._root:
            return ""

        name = pwd.getpwuid(os.getuid()).pw_name
        tmpbase = os.path.join(self._root, f"{self.FOLDER_PREFIX}{name}")

        os.makedirs(tmpbase, exist_ok=True)

        # delete the first max_rotate items
        sorted_paths = sorted(
            pathlib.Path(tmpbase).iterdir(),
            key=os.path.getmtime)

        # don't consider latest symlink
        num_paths = len(sorted_paths) - 1

        if num_paths >= self._max_rotate:
            max_items = num_paths - self._max_rotate + 1
            paths = sorted_paths[:max_items]

            for path in paths:
                if path.name == self.SYMLINK_NAME:
                    continue

                shutil.rmtree(str(path.resolve()))

        # create a new folder
        folder = tempfile.mkdtemp(dir=tmpbase)

        # create symlink to the latest temporary directory
        latest = os.path.join(tmpbase, self.SYMLINK_NAME)
        if os.path.islink(latest):
            os.remove(latest)

        os.symlink(
            folder,
            os.path.join(tmpbase, self.SYMLINK_NAME),
            target_is_directory=True)

        return folder

    @property
    def root(self) -> str:
        """
        The root folder. For example, if temporary folder is
        "/tmp/kirk.acer/tmpf547ftxv" the method will return "/tmp".
        If root folder has not been given during object creation, this
        method returns an empty string.
        """
        return self._root if self._root else ""

    @property
    def abspath(self) -> str:
        """
        Absolute path of the temporary directory.
        """
        return self._folder

    def mkdir(self, path: str) -> None:
        """
        Create a directory inside temporary directory.
        :param path: path of the directory
        :type path: str
        :returns: folder path.
        """
        if not self._folder:
            return

        dpath = os.path.join(self._folder, path)
        os.mkdir(dpath)

    def mkfile(self, path: str, content: bytes) -> None:
        """
        Create a file inside temporary directory.
        :param path: path of the file
        :type path: str
        :param content: file content
        :type content: str
        """
        if not self._folder:
            return

        fpath = os.path.join(self._folder, path)
        with open(fpath, "w+", encoding="utf-8") as mypath:
            mypath.write(content)
