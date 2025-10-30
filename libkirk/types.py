"""
.. module:: types
    :platform: Linux
    :synopsis: module that handles types conversion

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

from typing import Any, Dict, Optional, Type


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
    val = data.get(key, None)
    if not val:
        if default is None:
            return None

        return cls(default)

    cls_type = cls.__name__

    if not isinstance(val, cls) and cls_type not in ["int", "float"]:
        raise TypeError(
            f"dict value must be a {cls.__name__} but it's {type(val).__name__}"
        )

    return cls(val)
