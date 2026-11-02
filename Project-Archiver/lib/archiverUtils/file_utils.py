#  Copyright (c) 2020 by Patrick Rainsberry.
#  :license: Apache2, see LICENSE for more details.

import os


def get_default_dir(dir_name: str) -> str:
    """Get a folder in the user's home directory, creating it if it does not exist."""
    default_dir = os.path.join(os.path.expanduser('~'), dir_name, '')

    if not os.path.exists(default_dir):
        os.makedirs(default_dir)

    return default_dir


def dup_check(name: str) -> str:
    """Append -dup to a file name if a file with that name already exists."""
    if os.path.exists(name):
        base, ext = os.path.splitext(name)
        base += '-dup'
        name = base + ext
        dup_check(name)
    return name
