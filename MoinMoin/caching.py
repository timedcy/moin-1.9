# -*- coding: iso-8859-1 -*-
"""
    MoinMoin caching module

    @copyright: 2001-2004 by J�rgen Hermann <jh@web.de>
    @license: GNU GPL, see COPYING for details.
"""

import os
import warnings

from MoinMoin import config
from MoinMoin.util import filesys, lock

# filter the tempname warning because we create the tempfile only in directories
# where only we should have write access initially
warnings.filterwarnings("ignore", "tempnam.*security", RuntimeWarning, "MoinMoin.caching")

class CacheEntry:
    def __init__(self, request, arena, key, scope='page_or_wiki', do_locking=True):
        """ init a cache entry
            @param request: the request object
            @param arena: either a string or a page object, when we want to use
                          page local cache area
            @param key: under which key we access the cache content
            @param lock: if there should be a lock, normally True
            @param scope: the scope where we are caching:
                          'item' - an item local cache
                          'wiki' - a wiki local cache
                          'farm' - a cache for the whole farm
        """
        self.request = request
        self.key = key
        self.locking = do_locking
        if scope == 'page_or_wiki': # XXX DEPRECATED, remove later
            if isinstance(arena, str):
                self.arena_dir = os.path.join(request.cfg.cache_dir, request.cfg.siteid, arena)
                filesys.makeDirs(self.arena_dir)
            else: # arena is in fact a page object
                self.arena_dir = arena.getPagePath('cache', check_create=1)
        elif scope == 'item': # arena is a Page instance
            # we could move cache out of the page directory and store it to cache_dir
            self.arena_dir = arena.getPagePath('cache', check_create=1)
        elif scope == 'wiki':
            self.arena_dir = os.path.join(request.cfg.cache_dir, request.cfg.siteid, arena)
            filesys.makeDirs(self.arena_dir)
        elif scope == 'farm':
            self.arena_dir = os.path.join(request.cfg.cache_dir, '__common__', arena)
            filesys.makeDirs(self.arena_dir)
        if self.locking:
            self.lock_dir = os.path.join(self.arena_dir, '__lock__')
            self.rlock = lock.LazyReadLock(self.lock_dir, 60.0)
            self.wlock = lock.LazyWriteLock(self.lock_dir, 60.0)

    def _filename(self):
        return os.path.join(self.arena_dir, self.key)

    def _tmpfilename(self):
        return os.tempnam(self.arena_dir, self.key)

    def exists(self):
        return os.path.exists(self._filename())

    def mtime(self):
        try:
            return os.path.getmtime(self._filename())
        except (IOError, OSError):
            return 0

    def needsUpdate(self, filename, attachdir=None):
        if not self.exists():
            return 1

        try:
            ctime = os.path.getmtime(self._filename())
            ftime = os.path.getmtime(filename)
        except os.error:
            return 1

        needsupdate = ftime > ctime

        # if a page depends on the attachment dir, we check this, too:
        if not needsupdate and attachdir:
            try:
                ftime2 = os.path.getmtime(attachdir)
            except os.error:
                ftime2 = 0
            needsupdate = ftime2 > ctime

        return needsupdate

    def copyto(self, filename):
        # currently unused function
        import shutil
        tmpfname = self._tmpfilename()
        fname = self._filename()
        if not self.locking or self.locking and self.wlock.acquire(1.0):
            try:
                shutil.copyfile(filename, tmpfname)
                # this is either atomic or happening with real locks set:
                filesys.rename(tmpfname, fname)
            finally:
                if self.locking:
                    self.wlock.release()
        else:
            self.request.log("Can't acquire write lock in %s" % self.lock_dir)

    def update(self, content, encode=False):
        tmpfname = self._tmpfilename()
        fname = self._filename()
        if encode:
            content = content.encode(config.charset)
        if not self.locking or self.locking and self.wlock.acquire(1.0):
            try:
                # we do not write content to old inode, but to a new file
                # se we don't need to lock when we just want to read the file
                # (at least on POSIX, this works)
                f = open(tmpfname, 'wb')
                f.write(content)
                f.close()
                # this is either atomic or happening with real locks set:
                filesys.rename(tmpfname, fname)
            finally:
                if self.locking:
                    self.wlock.release()
        else:
            self.request.log("Can't acquire write lock in %s" % self.lock_dir)

    def remove(self):
        if not self.locking or self.locking and self.wlock.acquire(1.0):
            try:
                try:
                    os.remove(self._filename())
                except OSError:
                    pass
            finally:
                if self.locking:
                    self.wlock.release()
        else:
            self.request.log("Can't acquire write lock in %s" % self.lock_dir)

    def content(self, decode=False):
        if not self.locking or self.locking and self.rlock.acquire(1.0):
            try:
                f = open(self._filename(), 'rb')
                data = f.read()
                f.close()
            finally:
                if self.locking:
                    self.rlock.release()
        else:
            self.request.log("Can't acquire read lock in %s" % self.lock_dir)
        if decode:
            data = data.decode(config.charset)
        return data

