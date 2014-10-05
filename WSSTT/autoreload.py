import os, sys, subprocess, threading, time

_mtimes = {}
_win = (sys.platform == "win32")

_error_files = []

# this function from: https://ivan-site.com/2013/04/autoreload-code-in-python/
def code_changed():
    filenames = []
    for m in sys.modules.values():
        try:
            filenames.append(m.__file__)
        except AttributeError:
            pass
    for filename in filenames + _error_files:
        if not filename:
            continue
        if filename.endswith(".pyc") or filename.endswith(".pyo"):
            filename = filename[:-1]
        if filename.endswith("$py.class"):
            filename = filename[:-9] + ".py"
        if not os.path.exists(filename):
            continue # File might be in an egg, so it can't be reloaded.
        stat = os.stat(filename)
        mtime = stat.st_mtime
        if _win:
            mtime -= stat.st_ctime
        if filename not in _mtimes:
            _mtimes[filename] = mtime
            continue
        if mtime != _mtimes[filename]:
            _mtimes.clear()
            try:
                del _error_files[_error_files.index(filename)]
            except ValueError:
                pass
            return filename
    return False
