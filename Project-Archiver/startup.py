import os
import sys


def _remove_from_path(name):
    while name in sys.path:
        sys.path.remove(name)


def get_app_path(app_file):
    app_path = os.path.dirname(app_file)
    return app_path


def get_apper_path(app_file):
    return os.path.join(get_app_path(app_file), 'apper')


def apper_available(app_file):
    """Return True when the apper submodule is actually checked out.

    An empty 'apper' directory is still importable by Python 3 as an empty
    namespace package, which surfaces as the confusing
    "cannot import name 'AppObjects' from 'apper' (unknown location)" error
    when the repository was downloaded without its submodule.
    """
    return os.path.isfile(os.path.join(get_apper_path(app_file), 'apper', '__init__.py'))


def _remove_paths(app_path):
    _remove_from_path(app_path)
    _remove_from_path(os.path.join(app_path, 'apper'))
    _remove_from_path(os.path.join(app_path, 'lib'))


def _add_paths(app_path):
    # Only add directories that exist, and only add the apper directory when it
    # really contains the package. Adding an empty one would shadow the real
    # package as a namespace package.
    for path in (os.path.join(app_path, 'lib'), app_path):
        if os.path.isdir(path):
            sys.path.insert(0, path)

    apper_path = os.path.join(app_path, 'apper')
    if os.path.isfile(os.path.join(apper_path, 'apper', '__init__.py')):
        sys.path.insert(0, apper_path)


def setup_app(app_file):
    app_path = get_app_path(app_file)

    _remove_paths(app_path)

    # Fusion runs every add-in in one shared interpreter, so generic top-level
    # module names may already be cached by a different add-in. Without this,
    # `import config` can return another add-in's config module, which fails
    # with "module 'config' has no attribute 'app_name'" (issue #27).
    for module_name in ('apper', 'config'):
        sys.modules.pop(module_name, None)

    _add_paths(app_path)


def cleanup_app(app_file):
    app_path = get_app_path(app_file)
    _remove_paths(app_path)
