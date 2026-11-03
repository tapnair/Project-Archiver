#  Copyright (c) 2019-2026 Patrick Rainsberry
#  Licensed under the Apache License, Version 2.0. See LICENSE for details.

"""Helpers for local file and folder names and paths."""

import os
import re

# Characters that are not allowed in file or folder names on Windows or macOS, plus control characters.
# Names are sanitized the same way on every OS so an archive can be moved between them.
ILLEGAL_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

# Device names that Windows does not allow as a file name, with or without an extension.
WINDOWS_RESERVED_NAMES = {'CON', 'PRN', 'AUX', 'NUL'} | {f'COM{i}' for i in range(1, 10)} | {f'LPT{i}' for i in range(1, 10)}


def sanitize_name(name: str) -> str:
    """Make a Fusion document, component or folder name safe to use as a file or folder name.

    Illegal characters are replaced with a dash, trailing spaces and periods are removed since
    Windows drops them, and Windows reserved device names get a trailing dash.
    """
    name = ILLEGAL_NAME_CHARS.sub('-', name).strip().rstrip('. ')

    # Windows checks the part before the first period, so add the dash there
    base = name.split('.')[0]
    if base.upper() in WINDOWS_RESERVED_NAMES:
        name = base + '-' + name[len(base):]

    return name


def get_default_dir(dir_name: str) -> str:
    """Get a folder in the user's home directory, creating it if it does not exist."""
    default_dir = os.path.join(os.path.expanduser('~'), dir_name, '')

    if not os.path.exists(default_dir):
        os.makedirs(default_dir)

    return default_dir


def dup_check(path: str) -> str:
    """Return path, with -dup added before the extension as many times as needed to make it unused."""
    base, ext = os.path.splitext(path)
    while os.path.exists(path):
        base += '-dup'
        path = base + ext
    return path
