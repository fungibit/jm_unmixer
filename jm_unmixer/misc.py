"""
Misc general purpose tools used in this package.
"""

import os

################################################################################
# memoized_property
# based on: https://wiki.python.org/moin/PythonDecoratorLibrary#Cached_Properties

class memoized_property(object):

    def __init__(self, fget):
        self.fget = fget
        self.__doc__ = fget.__doc__
        self.__name__ = fget.__name__
        self.__module__ = fget.__module__

    def __get__(self, inst, owner):
        try:
            value = inst._cache[self.__name__]
        except (KeyError, AttributeError):
            value = self.fget(inst)
            try:
                cache = inst._cache
            except AttributeError:
                cache = inst._cache = {}
            cache[self.__name__] = value
        return value

################################################################################
# pickle related

import pickle

def pkl_append(fn, obj):
    with gzopen(fn, 'ab') as f:
        pickle.dump(obj, f)

def iter_pkl_list(fn):
    with gzopen(fn, 'rb') as f:
        while True:
            try:
                yield pickle.load(f)
            except (EOFError, IOError):
                break

################################################################################
# reading/writing gzipped files

from gzip import GzipFile

GZIP_EXTENSIONS = [
    ( '.tgz', '.tar' ),
    ( '.gz', '' ),
]

def gzopen(path, mode = 'r', add_ext = None, **kwargs):
    """
    Intelligently open a file as a zipped file (.gz) or regular file.
    """
    
    look_for_existing = mode[0] in 'ra'  # read or append
    if add_ext is None:
        add_ext = look_for_existing

    orig_path = path
    orig_path_exists = os.path.isfile(orig_path)
    if add_ext:
        gz_path = _to_gzip_extension(orig_path)
    else:
        gz_path = orig_path
    gz_path_exists = os.path.isfile(gz_path)
    
    if add_ext:
        target_path = gz_path
    else:
        target_path = orig_path

    if look_for_existing:
        if not orig_path_exists and gz_path_exists:
            target_path = gz_path
        else:
            target_path = orig_path
        
    if _is_gzip(target_path):
        open_func = GzipFile
    else:
        open_func = open
        
    return open_func(target_path, mode, **kwargs)
    
def _is_gzip(path):
    return _to_gzip_extension(path) == path

def _to_gzip_extension(path, strict = False):
    return _modify_gzip_extension(path, GZIP_EXTENSIONS, strict = strict)

def _modify_gzip_extension(path, extensions, strict = True):
    path = str(path)
    if not strict:
        for tgt_ext, src_ext in extensions:
            if path.endswith(tgt_ext):
                # already target-like
                return path
    for tgt_ext, src_ext in extensions:
        if path.endswith(src_ext):
            base_path = path[:-len(src_ext)] if src_ext else path
            return base_path + tgt_ext
    if strict:
        assert 0
    else:
        return path

###############################################################################
# progress bar

try:
    from click import progressbar
except ImportError:
    class progressbar(object):
        def __init__(self, x):
            self.x = x
        def __enter__(self):
            return self.x
        def __exit__(self, *args):
            return False

from concurrent.futures import ProcessPoolExecutor, as_completed

def map_with_progressbar(func, arglist, num_workers, preserve_order = True):
    """
    Run tasks in a process-pool and generate the results, while displaying
    a progress bar.
    """
    with ProcessPoolExecutor(max_workers = num_workers) as executor:
        futs = [ executor.submit(func, args) for args in arglist ]
        if preserve_order:
            prgbar = progressbar(futs)
        else:
            prgbar = progressbar(as_completed(futs), length = len(futs))
        with prgbar as futures:
            for fut in futures:
                yield fut.result()

###############################################################################
