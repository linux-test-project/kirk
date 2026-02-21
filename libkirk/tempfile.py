"""
.. module:: tempfile
    :platform: Linux
    :synopsis: module that contains temporary files handling

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

import os
import pathlib
import pwd
import shutil
import tempfile
from typing import Optional


class TempDir:
    """
    Temporary directory handler.
    """

    SYMLINK_NAME = "latest"
    FOLDER_PREFIX = "kirk."

    def __init__(self, root: Optional[str], max_rotate: int = 5) -> None:
        """
        :param root: Root directory (i.e. /tmp). If None, TempDir will handle
            requests without adding any file or directory.
        :type root: str | None
        :param max_rotate: Maximum number of temporary directories.
        :type max_rotate: int
        """
        if root and not os.path.isdir(root):
            raise ValueError(f"root folder doesn't exist: {root}")

        self._root = os.path.abspath(root) if root else None
        self._max_rotate = max(max_rotate, 0)
        self._username = pwd.getpwuid(os.getuid()).pw_name if root else None
        self._folder = self._rotate()

    def _rotate(self) -> str:
        """
        Check for old folders and remove them, then create a new one and return
        its full path.
        """
        if not self._root:
            return ""

        tmpbase = os.path.join(self._root, f"{self.FOLDER_PREFIX}{self._username}")

        os.makedirs(tmpbase, exist_ok=True)

        # filter out symlink before sorting and counting
        all_paths = list(pathlib.Path(tmpbase).iterdir())
        sorted_paths = sorted(
            (p for p in all_paths if p.name != self.SYMLINK_NAME), key=os.path.getmtime
        )

        num_paths = len(sorted_paths)

        if num_paths >= self._max_rotate:
            max_items = num_paths - self._max_rotate + 1
            paths_to_remove = sorted_paths[:max_items]

            for path in paths_to_remove:
                shutil.rmtree(str(path.resolve()))

        # create a new folder
        folder = tempfile.mkdtemp(dir=tmpbase)

        # create symlink to the latest temporary directory
        latest = os.path.join(tmpbase, self.SYMLINK_NAME)
        if os.path.islink(latest):
            os.remove(latest)

        os.symlink(folder, latest, target_is_directory=True)

        return folder

    @property
    def root(self) -> str:
        """
        :return: The root folder. For example, if temporary folder is
            "/tmp/kirk.acer/tmpf547ftxv" the method will return "/tmp".
            If root folder has not been given during object creation, this
            method returns an empty string.
        :rtype: str
        """
        return self._root or ""

    @property
    def abspath(self) -> str:
        """
        :return: Absolute path of the temporary directory.
        :rtype: str
        """
        return self._folder

    def mkdir(self, path: str) -> None:
        """
        Create a directory inside temporary directory.

        :param path: Path of the directory.
        :type path: str
        :returns: Folder path.
        """
        if not self._folder:
            return

        os.mkdir(os.path.join(self._folder, path))

    def mkfile(self, path: str, content: str) -> None:
        """
        Create a file inside temporary directory.

        :param path: Path of the file.
        :type path: str
        :param content: File content.
        :type content: str
        """
        if not self._folder:
            return

        fpath = os.path.join(self._folder, path)
        with open(fpath, "w+", encoding="utf-8") as mypath:
            mypath.write(content)
