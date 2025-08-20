"""
Unittest for types module.
"""

import pytest
import libkirk.types


def test_dict_item():
    """
    Test `dict_item` method.
    """
    val = libkirk.types.dict_item({"key": "value"}, "key", str)

    assert val == "value"


def test_dict_item_wrong_type():
    """
    Test `dict_item` method hwen wrong type is asked.
    """
    with pytest.raises(TypeError):
        libkirk.types.dict_item({"key": 10}, "key", str)


def test_dict_item_float():
    """
    Test `dict_item` method when using float numeric types.
    """
    val = libkirk.types.dict_item({"key": 10}, "key", float)

    assert val == 10.0


def test_dict_item_int():
    """
    Test `dict_item` method when using int numeric types.
    """
    val = libkirk.types.dict_item({"key": 10.0}, "key", int)

    assert val == 10


def test_dict_item_default_none():
    """
    Test `dict_item` method when default None is given.
    """
    val = libkirk.types.dict_item({"key2": "value"}, "key", str, None)

    assert val is None


def test_dict_item_default_str():
    """
    Test `dict_item` method when default string is given.
    """
    val = libkirk.types.dict_item({"key2": "value"}, "key", str, "ciao")

    assert val == "ciao"
