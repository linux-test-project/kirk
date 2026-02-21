"""
.. module:: types
    :platform: Linux
    :synopsis: module that handles types conversion

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

from typing import (
    Any,
    Dict,
    Optional,
    Type,
)


def dict_item(
    data: Dict[str, Any], key: str, cls: Type, default: Optional[Any] = None
) -> Any:
    """
    Extract a value from a dictionary according to the key, ensuring that
    correct type is returned.

    :param data: Dictionary from where we want to extract data.
    :type data: dict
    :param key: Key we are searching for.
    :type key: str
    :param cls: Type we want to extract.
    :type cls: Type
    :param default: Default value.
    :type default: Any | None
    :return: Type of the default value.
    :rtype: Any
    """
    if key not in data:
        return cls(default) if default is not None else None

    val = data[key]

    cls_name = cls.__name__
    numeric_types = {"int", "float"}

    # Check type compatibility (skip for numeric conversions)
    if not isinstance(val, cls) and cls_name not in numeric_types:
        raise TypeError(
            f"dict value must be a {cls_name} but it's {type(val).__name__}"
        )

    return cls(val)
