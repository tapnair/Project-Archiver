import os
import sys


def _remove_from_path(name):
    if name in sys.path:
        sys.path.remove(name)
        _remove_from_path(name)


def get_app_path(app_file):
    app_path = os.path.dirname(app_file)
    return app_path


def _remove_paths(app_path):
    _remove_from_path(app_path)
    _remove_from_path(os.path.join(app_path, 'apper'))
    _remove_from_path(os.path.join(app_path, 'lib'))


def _add_paths(app_path):
    sys.path.insert(0, app_path)
    sys.path.insert(0, os.path.join(app_path, 'apper'))
    sys.path.insert(0, os.path.join(app_path, 'lib'))


def setup_app(app_file):
    app_path = get_app_path(app_file)

    _remove_paths(app_path)

    if sys.modules.get('apper', False):
        # TODO possibly add a message to inform user that there is a potential conflict
        # Do some kind of version check?
        del sys.modules['apper']

    _add_paths(app_path)


def cleanup_app(app_file):
    app_path = get_app_path(app_file)
    _remove_paths(app_path)

