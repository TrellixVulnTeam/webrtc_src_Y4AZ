# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the locking library."""

from __future__ import print_function

import itertools
import multiprocessing
import os
import sys
import time

from chromite.lib import cros_test_lib
from chromite.lib import locking
from chromite.lib import osutils


LOCK_ACQUIRED = 5
LOCK_NOT_ACQUIRED = 6


class LockingTest(cros_test_lib.TempDirTestCase):
  """Test the Locking class."""

  def setUp(self):
    self.lock_file = os.path.join(self.tempdir, 'lockfile')

  def _HelperSingleLockTest(self, blocking, shared, locktype):
    """Helper method that runs a basic test with/without blocking/sharing."""
    self.assertFalse(os.path.exists(self.lock_file))

    lock = locking.FileLock(
        self.lock_file, blocking=blocking, locktype=locktype)
    self.assertFalse(lock.IsLocked())

    lock.write_lock()
    self.assertTrue(lock.IsLocked())
    self.assertTrue(os.path.exists(self.lock_file))

    # Acquiring the lock again should be safe.
    lock.lock(shared)
    self.assertTrue(lock.IsLocked())

    lock.close()
    self.assertFalse(lock.IsLocked())

    osutils.SafeUnlink(self.lock_file)

  def _HelperInsideProcess(self, blocking, shared, locktype=locking.LOCKF):
    """Helper method that runs a basic test with/without blocking."""
    try:
      lock = locking.FileLock(
          self.lock_file, blocking=blocking, locktype=locktype)
      with lock.lock(shared):
        pass
      sys.exit(LOCK_ACQUIRED)
    except locking.LockNotAcquiredError:
      sys.exit(LOCK_NOT_ACQUIRED)

  def _HelperStartProcess(self, blocking=False, shared=False):
    """Create a process and invoke _HelperInsideProcess in it."""
    p = multiprocessing.Process(target=self._HelperInsideProcess,
                                args=(blocking, shared))
    p.start()

    # It's highly probably that p will have tried to grab the lock before the
    # timer expired, but not certain.
    time.sleep(0.1)

    return p

  def _HelperWithProcess(self, expected, blocking=False, shared=False,
                         locktype=locking.LOCKF):
    """Create a process and invoke _HelperInsideProcess in it."""
    p = multiprocessing.Process(target=self._HelperInsideProcess,
                                args=(blocking, shared, locktype))
    p.start()
    p.join()
    self.assertEquals(p.exitcode, expected)

  def testSingleLock(self):
    """Just test getting releasing a lock with options."""
    arg_list = [
        [True, False], # blocking
        [True, False], # shared
        [locking.FLOCK, locking.LOCKF], # locking mechanism
    ]
    for args in itertools.product(*arg_list):
      self._HelperSingleLockTest(*args)

  def testDoubleLockWithFlock(self):
    """Tests that double locks do block with flock."""
    lock1 = locking.FileLock(
        self.lock_file, blocking=False, locktype=locking.FLOCK)
    lock2 = locking.FileLock(
        self.lock_file, blocking=False, locktype=locking.FLOCK)

    with lock1.write_lock():
      self.assertTrue(lock1.IsLocked())
      self.assertFalse(lock2.IsLocked())

      self.assertRaises(locking.LockNotAcquiredError, lock2.write_lock)
      self.assertTrue(lock1.IsLocked())
      self.assertFalse(lock2.IsLocked())

    self.assertFalse(lock1.IsLocked())
    self.assertFalse(lock2.IsLocked())

    lock2.unlock()
    self.assertFalse(lock1.IsLocked())
    self.assertFalse(lock2.IsLocked())

  def testDoubleLockWithLockf(self):
    """Tests that double locks don't block with lockf."""
    lock1 = locking.FileLock(
        self.lock_file, blocking=False, locktype=locking.LOCKF)
    lock2 = locking.FileLock(
        self.lock_file, blocking=False, locktype=locking.LOCKF)
    with lock1.write_lock():
      self.assertTrue(lock1.IsLocked())
      self.assertFalse(lock2.IsLocked())

      # With lockf, we can lock the same file twice in the same process.
      with lock2.write_lock():
        self.assertTrue(lock1.IsLocked())
        self.assertTrue(lock2.IsLocked())

    self.assertFalse(lock1.IsLocked())
    self.assertFalse(lock2.IsLocked())

  def testContextMgr(self):
    """Make sure we behave properly with 'with'."""
    # Create an instance, and use it in a with.
    prelock = locking.FileLock(self.lock_file)
    self._HelperWithProcess(expected=LOCK_ACQUIRED)

    with prelock.write_lock() as lock:
      # Assert the instance didn't change.
      self.assertIs(prelock, lock)
      self._HelperWithProcess(expected=LOCK_NOT_ACQUIRED)

    self._HelperWithProcess(expected=LOCK_ACQUIRED)

    # Construct the instance in the with expression.
    with locking.FileLock(self.lock_file).write_lock() as lock:
      self.assertIsInstance(lock, locking.FileLock)
      self._HelperWithProcess(expected=LOCK_NOT_ACQUIRED)

    self._HelperWithProcess(expected=LOCK_ACQUIRED)

  def testAcquireBeforeWith(self):
    """Sometimes you want to grab a lock and then return it into 'with'."""
    lock = locking.FileLock(self.lock_file, blocking=False)

    lock.write_lock()
    self._HelperWithProcess(expected=LOCK_NOT_ACQUIRED)

    with lock:
      self._HelperWithProcess(expected=LOCK_NOT_ACQUIRED)

    self._HelperWithProcess(expected=LOCK_ACQUIRED)

  def testSingleProcessLock(self):
    """Test grabbing the same lock in processes with no conflicts."""
    arg_list = [
        [LOCK_ACQUIRED],
        [True, False], # blocking
        [True, False], # shared
        [locking.FLOCK, locking.LOCKF], # locking mechanism
    ]
    for args in itertools.product(*arg_list):
      self._HelperWithProcess(*args)

  def testNonBlockingConflicts(self):
    """Test that we get a lock conflict for non-blocking locks."""
    with locking.FileLock(self.lock_file).write_lock():
      self._HelperWithProcess(expected=LOCK_NOT_ACQUIRED)

      self._HelperWithProcess(expected=LOCK_NOT_ACQUIRED, shared=True)

    # Can grab it after it's released.
    self._HelperWithProcess(expected=LOCK_ACQUIRED)

  def testSharedLocks(self):
    """Test lock conflict for blocking locks."""
    # Intial lock is NOT shared.
    with locking.FileLock(self.lock_file).write_lock():
      self._HelperWithProcess(expected=LOCK_NOT_ACQUIRED, shared=True)

    # Intial lock IS shared.
    with locking.FileLock(self.lock_file).read_lock():
      self._HelperWithProcess(expected=LOCK_ACQUIRED, shared=True)
      self._HelperWithProcess(expected=LOCK_NOT_ACQUIRED,
                              shared=False)

  def testBlockingConflicts(self):
    """Test lock conflict for blocking locks."""
    # Intial lock is blocking, exclusive.
    with locking.FileLock(self.lock_file, blocking=True).write_lock():
      self._HelperWithProcess(expected=LOCK_NOT_ACQUIRED, blocking=False)

      p = self._HelperStartProcess(blocking=True, shared=False)

    # when the with clause exits, p should unblock and get the lock, setting
    # its exit code to sucess now.
    p.join()
    self.assertEquals(p.exitcode, LOCK_ACQUIRED)

    # Intial lock is NON blocking.
    with locking.FileLock(self.lock_file, blocking=False).write_lock():
      self._HelperWithProcess(expected=LOCK_NOT_ACQUIRED)

      p = self._HelperStartProcess(blocking=True, shared=False)

    # when the with clause exits, p should unblock and get the lock, setting
    # it's exit code to sucess now.
    p.join()
    self.assertEquals(p.exitcode, LOCK_ACQUIRED)

    # Intial lock is shared, blocking lock is exclusive.
    with locking.FileLock(self.lock_file, blocking=False).read_lock():
      self._HelperWithProcess(expected=LOCK_NOT_ACQUIRED)
      self._HelperWithProcess(expected=LOCK_ACQUIRED, shared=True)

      p = self._HelperStartProcess(blocking=True, shared=False)
      q = self._HelperStartProcess(blocking=True, shared=False)

    # when the with clause exits, p should unblock and get the lock, setting
    # it's exit code to sucess now.
    p.join()
    self.assertEquals(p.exitcode, LOCK_ACQUIRED)
    q.join()
    self.assertEquals(p.exitcode, LOCK_ACQUIRED)
