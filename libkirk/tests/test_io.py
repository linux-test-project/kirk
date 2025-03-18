"""
Unittests for io module.
"""
import pytest
from libkirk.io import AsyncFile

pytestmark = pytest.mark.asyncio


async def test_seek(tmpdir):
    """
    Test `seek()` method.
    """
    myfile = tmpdir / "myfile"

    with open(myfile, "w", encoding="utf-8") as fdata:
        fdata.write("kirkdata")

    async with AsyncFile(myfile, 'r') as fdata:
        await fdata.seek(4)
        assert await fdata.read() == "data"


async def test_tell(tmpdir):
    """
    Test `tell()` method.
    """
    myfile = tmpdir / "myfile"

    with open(myfile, "w", encoding="utf-8") as fdata:
        fdata.write("kirkdata")

    async with AsyncFile(myfile, 'r') as fdata:
        await fdata.seek(4)
        assert await fdata.tell() == 4


async def test_read(tmpdir):
    """
    Test `read()` method.
    """
    myfile = tmpdir / "myfile"

    with open(myfile, "w", encoding="utf-8") as fdata:
        fdata.write("kirkdata")

    async with AsyncFile(myfile, 'r') as fdata:
        assert await fdata.read() == "kirkdata"


async def test_write(tmpdir):
    """
    Test `write()` method.
    """
    myfile = tmpdir / "myfile"

    async with AsyncFile(myfile, "w") as fdata:
        await fdata.write("kirkdata")

    with open(myfile, "r", encoding="utf-8") as fdata:
        assert fdata.read() == "kirkdata"


async def test_readline(tmpdir):
    """
    Test `readline()` method.
    """
    myfile = tmpdir / "myfile"

    with open(myfile, "w", encoding="utf-8") as fdata:
        fdata.write("kirkdata\n")
        fdata.write("kirkdata\n")

    async with AsyncFile(myfile, 'r') as fdata:
        assert await fdata.readline() == "kirkdata\n"
        assert await fdata.readline() == "kirkdata\n"
        assert await fdata.readline() == ''


async def test_file_no_open(tmpdir):
    """
    Test a file when it's not open.
    """
    myfile = tmpdir / "myfile"

    with open(myfile, "w", encoding="utf-8") as fdata:
        fdata.write("kirkdata")

    fdata = AsyncFile(myfile, 'r')
    await fdata.seek(4)
    assert not await fdata.tell()
    assert not await fdata.read()
    assert not await fdata.readline()
    await fdata.write("faaaa")
    await fdata.close()
    await fdata.close()
    await fdata.close()


async def test_open(tmpdir):
    """
    Test `open()` method.
    """
    myfile = tmpdir / "myfile"
    fdata = AsyncFile(myfile, 'w')
    await fdata.open()
    await fdata.open()
    try:
        await fdata.write("ciao")
    finally:
        await fdata.close()
        await fdata.close()


async def test_mutliple_open_close(tmpdir):
    """
    Test `open()` and `close()` methods when open/close multiple times.
    """
    myfile = tmpdir / "myfile"
    fdata = AsyncFile(myfile, 'w')
    await fdata.open()
    await fdata.open()
    await fdata.open()
    await fdata.close()
    await fdata.close()
