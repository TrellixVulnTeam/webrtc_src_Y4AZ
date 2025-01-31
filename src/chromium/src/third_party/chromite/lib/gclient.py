# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common functions used for syncing Chrome."""

from __future__ import print_function

import os
import pprint

from chromite.cbuildbot import constants
from chromite.lib import cros_build_lib
from chromite.lib import git
from chromite.lib import osutils

CHROME_COMMITTER_URL = 'https://chromium.googlesource.com/chromium/src'
STATUS_URL = 'https://chromium-status.appspot.com/current?format=json'


def FindGclientFile(path):
  """Returns the nearest higher-level gclient file from the specified path.

  Args:
    path: The path to use. Defaults to cwd.
  """
  return osutils.FindInPathParents(
      '.gclient', path, test_func=os.path.isfile)


def FindGclientCheckoutRoot(path):
  """Get the root of your gclient managed checkout."""
  gclient_path = FindGclientFile(path)
  if gclient_path:
    return os.path.dirname(gclient_path)
  return None


def _LoadGclientFile(path):
  """Load a gclient file and return the solutions defined by the gclient file.

  Args:
    path: The gclient file to load.

  Returns:
    A list of solutions defined by the gclient file or an empty list if no
    solutions exists.
  """
  global_scope = {}
  # Similar to depot_tools, we use execfile() to evaluate the gclient file,
  # which is essentially a Python script, and then extract the solutions
  # defined by the gclient file from the 'solutions' variable in the global
  # scope.
  execfile(path, global_scope)
  return global_scope.get('solutions', [])


def _FindOrAddSolution(solutions, name):
  """Find a solution of the specified name from the given list of solutions.

  If no solution with the specified name is found, a solution with the
  specified name is appended to the given list of solutions. This function thus
  always returns a solution.

  Args:
    solutions: The list of solutions to search from.
    name: The solution name to search for.

  Returns:
    The solution with the specified name.
  """
  for solution in solutions:
    if solution['name'] == name:
      return solution

  solution = {'name': name}
  solutions.append(solution)
  return solution


def _GetGclientURLs(internal, rev):
  """Get the URLs and deps_file values to use in gclient file.

  See WriteConfigFile below.
  """
  results = []

  if rev is None or git.IsSHA1(rev):
    # Regular chromium checkout; src may float to origin/master or be pinned.
    url = constants.CHROMIUM_GOB_URL
    if rev:
      url += ('@' + rev)
    # TODO(szager): .DEPS.git will eventually be deprecated in favor of DEPS.
    # When that happens, this could should continue to work, because gclient
    # will fall back to DEPS if .DEPS.git doesn't exist.  Eventually, this
    # code should be cleaned up to stop referring to non-existent .DEPS.git.
    results.append(('src', url, '.DEPS.git'))
    if internal:
      results.append(
          ('src-internal', constants.CHROME_INTERNAL_GOB_URL, '.DEPS.git'))
  elif internal:
    # Internal buildspec: check out the buildspec repo and set deps_file to
    # the path to the desired release spec.
    url = constants.INTERNAL_GOB_URL + '/chrome/tools/buildspec.git'
    results.append(('CHROME_DEPS', url, 'releases/%s/.DEPS.git' % rev))
  else:
    # External buildspec: use the main chromium src repository, pinned to the
    # release tag, with deps_file set to .DEPS.git (which is created by
    # publish_deps.py).
    url = constants.CHROMIUM_GOB_URL + '@refs/tags/' + rev
    results.append(('src', url, '.DEPS.git'))

  return results


def _GetGclientSolutions(internal, rev, template):
  """Get the solutions array to write to the gclient file.

  See WriteConfigFile below.
  """
  urls = _GetGclientURLs(internal, rev)
  solutions = _LoadGclientFile(template) if template is not None else []
  for (name, url, deps_file) in urls:
    solution = _FindOrAddSolution(solutions, name)
    # Always override 'url' and 'deps_file' of a solution as we need to specify
    # the revision information.
    solution['url'] = url
    if deps_file:
      solution['deps_file'] = deps_file

    # Use 'custom_deps' and 'custom_vars' of a solution when specified by the
    # template gclient file.
    solution.setdefault('custom_deps', {})
    solution.setdefault('custom_vars', {})

  return solutions


def _GetGclientSpec(internal, rev, template, use_cache):
  """Return a formatted gclient spec.

  See WriteConfigFile below.
  """
  solutions = _GetGclientSolutions(internal=internal, rev=rev,
                                   template=template)
  result = 'solutions = %s\n' % pprint.pformat(solutions)

  # Horrible hack, I will go to hell for this.  The bots need to have a git
  # cache set up; but how can we tell whether this code is running on a bot
  # or a developer's machine?
  if cros_build_lib.HostIsCIBuilder() and use_cache:
    result += "cache_dir = '/b/git-cache'\n"

  return result

def WriteConfigFile(gclient, cwd, internal, rev, template=None,
                    use_cache=True):
  """Initialize the specified directory as a gclient checkout.

  For gclient documentation, see:
    http://src.chromium.org/svn/trunk/tools/depot_tools/README.gclient

  Args:
    gclient: Path to gclient.
    cwd: Directory to sync.
    internal: Whether you want an internal checkout.
    rev: Revision or tag to use.
        - If None, use the latest from trunk.
        - If this is a sha1, use the specified revision.
        - Otherwise, treat this as a chrome version string.
    template: An optional file to provide a template of gclient solutions.
              _GetGclientSolutions iterates through the solutions specified
              by the template and performs appropriate modifications such as
              filling information like url and revision and adding extra
              solutions.
    use_cache: An optional Boolean flag to indicate if the git cache should
               be used when available (on a continuous-integration builder).
  """
  spec = _GetGclientSpec(internal=internal, rev=rev, template=template,
                         use_cache=use_cache)
  cmd = [gclient, 'config', '--spec', spec]
  cros_build_lib.RunCommand(cmd, cwd=cwd)


def Revert(gclient, cwd):
  """Revert all local changes.

  Args:
    gclient: Path to gclient.
    cwd: Directory to revert.
  """
  cros_build_lib.RunCommand([gclient, 'revert', '--nohooks'], cwd=cwd)


def Sync(gclient, cwd, reset=False):
  """Sync the specified directory using gclient.

  Args:
    gclient: Path to gclient.
    cwd: Directory to sync.
    reset: Reset to pristine version of the source code.
  """
  cmd = [gclient, 'sync', '--verbose', '--nohooks', '--transitive',
         '--with_branch_heads', '--with_tags']

  if reset:
    cmd += ['--reset', '--force', '--delete_unversioned_trees']
  cros_build_lib.RunCommand(cmd, cwd=cwd)
