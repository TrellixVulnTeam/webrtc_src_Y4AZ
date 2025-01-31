# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for lkgm_manager"""

from __future__ import print_function

import contextlib
import mock
import os
import tempfile
from xml.dom import minidom

from chromite.cbuildbot import constants
from chromite.cbuildbot import lkgm_manager
from chromite.cbuildbot import manifest_version
from chromite.cbuildbot import repository
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import git
from chromite.lib import osutils


FAKE_VERSION_STRING = '1.2.4-rc3'
FAKE_VERSION_STRING_NEXT = '1.2.4-rc4'
CHROME_BRANCH = '13'

FAKE_VERSION = """
CHROMEOS_BUILD=1
CHROMEOS_BRANCH=2
CHROMEOS_PATCH=4
CHROME_BRANCH=13
"""


# pylint: disable=protected-access


class LKGMCandidateInfoTest(cros_test_lib.TestCase):
  """Test methods testing methods in _LKGMCandidateInfo class."""

  def testLoadFromString(self):
    """Tests whether we can load from a string."""
    info = lkgm_manager._LKGMCandidateInfo(version_string=FAKE_VERSION_STRING,
                                           chrome_branch=CHROME_BRANCH)
    self.assertEqual(info.VersionString(), FAKE_VERSION_STRING)

  def testIncrementVersionPatch(self):
    """Tests whether we can increment a lkgm info."""
    info = lkgm_manager._LKGMCandidateInfo(version_string=FAKE_VERSION_STRING,
                                           chrome_branch=CHROME_BRANCH)
    info.IncrementVersion()
    self.assertEqual(info.VersionString(), FAKE_VERSION_STRING_NEXT)

  def testVersionCompare(self):
    """Tests whether our comparision method works."""
    info0 = lkgm_manager._LKGMCandidateInfo('5.2.3-rc100')
    info1 = lkgm_manager._LKGMCandidateInfo('1.2.3-rc1')
    info2 = lkgm_manager._LKGMCandidateInfo('1.2.3-rc2')
    info3 = lkgm_manager._LKGMCandidateInfo('1.2.200-rc1')
    info4 = lkgm_manager._LKGMCandidateInfo('1.4.3-rc1')

    self.assertGreater(info0, info1)
    self.assertGreater(info0, info2)
    self.assertGreater(info0, info3)
    self.assertGreater(info0, info4)
    self.assertGreater(info2, info1)
    self.assertGreater(info3, info1)
    self.assertGreater(info3, info2)
    self.assertGreater(info4, info1)
    self.assertGreater(info4, info2)
    self.assertGreater(info4, info3)
    self.assertEqual(info0, info0)
    self.assertEqual(info1, info1)
    self.assertEqual(info2, info2)
    self.assertEqual(info3, info3)
    self.assertEqual(info4, info4)
    self.assertNotEqual(info0, info1)
    self.assertNotEqual(info0, info2)
    self.assertNotEqual(info0, info3)
    self.assertNotEqual(info0, info4)
    self.assertNotEqual(info1, info0)
    self.assertNotEqual(info1, info2)
    self.assertNotEqual(info1, info3)
    self.assertNotEqual(info1, info4)
    self.assertNotEqual(info2, info0)
    self.assertNotEqual(info2, info1)
    self.assertNotEqual(info2, info3)
    self.assertNotEqual(info2, info4)
    self.assertNotEqual(info3, info0)
    self.assertNotEqual(info3, info1)
    self.assertNotEqual(info3, info2)
    self.assertNotEqual(info3, info4)
    self.assertNotEqual(info4, info0)
    self.assertNotEqual(info4, info1)
    self.assertNotEqual(info4, info1)
    self.assertNotEqual(info4, info3)


@contextlib.contextmanager
def TemporaryManifest():
  with tempfile.NamedTemporaryFile() as f:
    # Create fake but empty manifest file.
    new_doc = minidom.getDOMImplementation().createDocument(
        None, 'manifest', None)
    print(new_doc.toxml())
    new_doc.writexml(f)
    f.flush()
    yield f


class LKGMManagerTest(cros_test_lib.MockTempDirTestCase):
  """Tests for the BuildSpecs manager."""

  def setUp(self):
    self.push_mock = self.PatchObject(git, 'CreatePushBranch')

    self.source_repo = 'ssh://source/repo'
    self.manifest_repo = 'ssh://manifest/repo'
    self.version_file = 'version-file.sh'
    self.branch = 'master'
    self.build_name = 'x86-generic'
    self.incr_type = 'branch'

    # Create tmp subdirs based on the one provided TempDirMixin.
    self.tmpdir = os.path.join(self.tempdir, "base")
    osutils.SafeMakedirs(self.tmpdir)
    self.tmpmandir = os.path.join(self.tempdir, "man")
    osutils.SafeMakedirs(self.tmpmandir)

    repo = repository.RepoRepository(
        self.source_repo, self.tmpdir, self.branch, depth=1)
    self.manager = lkgm_manager.LKGMManager(
        repo, self.manifest_repo, self.build_name, constants.PFQ_TYPE, 'branch',
        force=False, branch=self.branch, dry_run=True)
    self.manager.manifest_dir = self.tmpmandir
    self.manager.lkgm_path = os.path.join(
        self.tmpmandir, constants.LKGM_MANIFEST)

    self.manager.all_specs_dir = '/LKGM/path'
    manifest_dir = self.manager.manifest_dir
    self.manager.specs_for_builder = os.path.join(manifest_dir,
                                                  self.manager.rel_working_dir,
                                                  'build-name', '%(builder)s')
    self.manager.SLEEP_TIMEOUT = 0

  def _GetPathToManifest(self, info):
    return os.path.join(self.manager.all_specs_dir, '%s.xml' %
                        info.VersionString())

  def testCreateNewCandidate(self):
    """Tests that we can create a new candidate and uprev an old rc."""
    # Let's stub out other LKGMManager calls cause they're already
    # unit tested.

    my_info = lkgm_manager._LKGMCandidateInfo('1.2.3')
    most_recent_candidate = lkgm_manager._LKGMCandidateInfo('1.2.3-rc12')
    self.manager.latest = most_recent_candidate.VersionString()

    new_candidate = lkgm_manager._LKGMCandidateInfo('1.2.3-rc13')
    new_manifest = 'some_manifest'

    build_id = 59271

    self.PatchObject(lkgm_manager.LKGMManager, 'CheckoutSourceCode')
    self.PatchObject(lkgm_manager.LKGMManager, 'CreateManifest',
                     return_value=new_manifest)
    self.PatchObject(lkgm_manager.LKGMManager, 'HasCheckoutBeenBuilt',
                     return_value=False)

    # Do manifest refresh work.
    self.PatchObject(lkgm_manager.LKGMManager, 'RefreshManifestCheckout')
    self.PatchObject(lkgm_manager.LKGMManager, 'GetCurrentVersionInfo',
                     return_value=my_info)
    init_mock = self.PatchObject(lkgm_manager.LKGMManager,
                                 'InitializeManifestVariables')

    # Publish new candidate.
    publish_mock = self.PatchObject(lkgm_manager.LKGMManager, 'PublishManifest')

    candidate_path = self.manager.CreateNewCandidate(build_id=build_id)
    self.assertEqual(candidate_path, self._GetPathToManifest(new_candidate))

    publish_mock.assert_called_once_with(new_manifest,
                                         new_candidate.VersionString(),
                                         build_id=build_id)
    init_mock.assert_called_once_with(my_info)
    self.push_mock.assert_called_once_with(mock.ANY, mock.ANY, sync=False)

  def testCreateFromManifest(self):
    """Tests that we can create a new candidate from another manifest."""
    # Let's stub out other LKGMManager calls cause they're already
    # unit tested.

    version = '2010.0.0-rc7'
    my_info = lkgm_manager._LKGMCandidateInfo('2010.0.0')
    new_candidate = lkgm_manager._LKGMCandidateInfo(version)
    manifest = ('/tmp/manifest-versions-internal/paladin/buildspecs/'
                '20/%s.xml' % version)
    new_manifest = '/path/to/tmp/file.xml'

    build_id = 20162

    filter_mock = self.PatchObject(manifest_version, 'FilterManifest',
                                   return_value=new_manifest)

    # Do manifest refresh work.
    self.PatchObject(lkgm_manager.LKGMManager, 'GetCurrentVersionInfo',
                     return_value=my_info)
    self.PatchObject(lkgm_manager.LKGMManager, 'RefreshManifestCheckout')
    init_mock = self.PatchObject(lkgm_manager.LKGMManager,
                                 'InitializeManifestVariables')

    # Publish new candidate.
    publish_mock = self.PatchObject(lkgm_manager.LKGMManager, 'PublishManifest')

    candidate_path = self.manager.CreateFromManifest(manifest,
                                                     build_id=build_id)
    self.assertEqual(candidate_path, self._GetPathToManifest(new_candidate))
    self.assertEqual(self.manager.current_version, version)

    filter_mock.assert_called_once_with(
        manifest, whitelisted_remotes=constants.EXTERNAL_REMOTES)
    publish_mock.assert_called_once_with(new_manifest, version,
                                         build_id=build_id)
    init_mock.assert_called_once_with(my_info)
    self.push_mock.assert_called_once_with(mock.ANY, mock.ANY, sync=False)

  def testCreateNewCandidateReturnNoneIfNoWorkToDo(self):
    """Tests that we return nothing if there is nothing to create."""
    new_manifest = 'some_manifest'
    my_info = lkgm_manager._LKGMCandidateInfo('1.2.3')
    self.PatchObject(lkgm_manager.LKGMManager, 'CheckoutSourceCode')
    self.PatchObject(lkgm_manager.LKGMManager, 'CreateManifest',
                     return_value=new_manifest)
    self.PatchObject(lkgm_manager.LKGMManager, 'RefreshManifestCheckout')
    self.PatchObject(lkgm_manager.LKGMManager, 'GetCurrentVersionInfo',
                     return_value=my_info)
    init_mock = self.PatchObject(lkgm_manager.LKGMManager,
                                 'InitializeManifestVariables')
    self.PatchObject(lkgm_manager.LKGMManager, 'HasCheckoutBeenBuilt',
                     return_value=True)

    candidate = self.manager.CreateNewCandidate()
    self.assertEqual(candidate, None)
    init_mock.assert_called_once_with(my_info)

  def _CreateManifest(self):
    """Returns a created test manifest in tmpdir with its dir_pfx."""
    self.manager.current_version = '1.2.4-rc21'
    dir_pfx = CHROME_BRANCH
    manifest = os.path.join(self.manager.manifest_dir,
                            self.manager.rel_working_dir, 'buildspecs',
                            dir_pfx, '1.2.4-rc21.xml')
    osutils.Touch(manifest)
    return manifest, dir_pfx

  def testGenerateBlameListSinceLKGM(self):
    """Tests that we can generate a blamelist from two commit messages.

    This test tests the functionality of generating a blamelist for a git log.
    Note in this test there are two commit messages, one commited by the
    Commit Queue and another from Non-Commit Queue.  We test the correct
    handling in both cases.
    """
    fake_git_log = """Author: Sammy Sosa <fake@fake.com>
    Commit: Chris Sosa <sosa@chromium.org>

    Date:   Mon Aug 8 14:52:06 2011 -0700

    Add in a test for cbuildbot

    TEST=So much testing
    BUG=chromium-os:99999

    Change-Id: Ib72a742fd2cee3c4a5223b8easwasdgsdgfasdf
    Reviewed-on: https://chromium-review.googlesource.com/1234
    Reviewed-by: Fake person <fake@fake.org>
    Tested-by: Sammy Sosa <fake@fake.com>
    Author: Sammy Sosa <fake@fake.com>
    Commit: Gerrit <chrome-bot@chromium.org>

    Date:   Mon Aug 8 14:52:06 2011 -0700

    Add in a test for cbuildbot

    TEST=So much testing
    BUG=chromium-os:99999

    Change-Id: Ib72a742fd2cee3c4a5223b8easwasdgsdgfasdf
    Reviewed-on: https://chromium-review.googlesource.com/1235
    Reviewed-by: Fake person <fake@fake.org>
    Tested-by: Sammy Sosa <fake@fake.com>
    """
    self.manager.incr_type = 'build'
    self.PatchObject(cros_build_lib, 'RunCommand', side_effect=Exception())
    exists_mock = self.PatchObject(os.path, 'exists', return_value=True)
    link_mock = self.PatchObject(cros_build_lib, 'PrintBuildbotLink')

    project = {
        'name': 'fake/repo',
        'path': 'fake/path',
        'revision': '1234567890',
    }
    fake_project_handler = mock.Mock(spec=git.Manifest)
    fake_project_handler.checkouts_by_path = {project['path']: project}
    self.PatchObject(git, 'Manifest', return_value=fake_project_handler)

    fake_result = cros_build_lib.CommandResult(output=fake_git_log)
    self.PatchObject(git, 'RunGit', return_value=fake_result)

    self.manager.GenerateBlameListSinceLKGM()

    exists_mock.assert_called_once_with(
        os.path.join(self.tmpdir, project['path']))
    link_mock.assert_has_calls([
        mock.call('CHUMP | repo | fake | 1234',
                  'https://chromium-review.googlesource.com/1234'),
        mock.call('repo | fake | 1235',
                  'https://chromium-review.googlesource.com/1235'),
    ])

  def testAddChromeVersionToManifest(self):
    """Tests whether we can write the chrome version to the manifest file."""
    with TemporaryManifest() as f:
      chrome_version = '35.0.1863.0'
      # Write the chrome element to manifest.
      self.manager._AddChromeVersionToManifest(f.name, chrome_version)

      # Read the manifest file.
      new_doc = minidom.parse(f.name)
      elements = new_doc.getElementsByTagName(lkgm_manager.CHROME_ELEMENT)
      self.assertEqual(len(elements), 1)
      self.assertEqual(
          elements[0].getAttribute(lkgm_manager.CHROME_VERSION_ATTR),
          chrome_version)

  def testAddLKGMToManifest(self, present=True):
    """Tests whether we can write the LKGM version to the manifest file."""
    with TemporaryManifest() as f:
      # Set up LGKM symlink.
      if present:
        lkgm_version = '6377.0.0-rc1'
        os.makedirs(os.path.dirname(self.manager.lkgm_path))
        os.symlink('../foo/%s.xml' % lkgm_version, self.manager.lkgm_path)

      # Write the chrome element to manifest.
      self.manager._AddLKGMToManifest(f.name)

      # Read the manifest file.
      new_doc = minidom.parse(f.name)
      elements = new_doc.getElementsByTagName(lkgm_manager.LKGM_ELEMENT)
      if present:
        self.assertEqual(len(elements), 1)
        self.assertEqual(
            elements[0].getAttribute(lkgm_manager.LKGM_VERSION_ATTR),
            lkgm_version)
      else:
        self.assertEqual(len(elements), 0)

  def testAddLKGMToManifestWithMissingFile(self):
    """Tests writing the LKGM version when LKGM.xml is missing."""
    self.testAddLKGMToManifest(present=False)

  def testAddPatchesToManifest(self):
    """Tests whether we can add a fake patch to an empty manifest file.

    This test creates an empty xml file with just manifest/ tag in it then
    runs the AddPatchesToManifest with one mocked out GerritPatch and ensures
    the newly generated manifest has the correct patch information afterwards.
    """
    with TemporaryManifest() as f:
      gerrit_patch = mock.MagicMock()
      gerrit_patch.remote = 'cros-internal'
      gerrit_patch.gerrit_number = '12345'
      gerrit_patch.project = 'chromite/tacos'
      gerrit_patch.project_url = 'https://host/chromite/tacos'
      gerrit_patch.ref = 'refs/changes/11/12345/4'
      gerrit_patch.tracking_branch = 'master'
      gerrit_patch.change_id = '1234567890'
      gerrit_patch.commit = '0987654321'
      gerrit_patch.patch_number = '4'
      gerrit_patch.owner_email = 'foo@chromium.org'
      gerrit_patch.fail_count = 1
      gerrit_patch.pass_count = 1
      gerrit_patch.total_fail_count = 3
      self.manager._AddPatchesToManifest(f.name, [gerrit_patch])

      new_doc = minidom.parse(f.name)
      element = new_doc.getElementsByTagName(
          lkgm_manager.PALADIN_COMMIT_ELEMENT)[0]
      self.assertEqual(element.getAttribute(
          lkgm_manager.PALADIN_CHANGE_ID_ATTR), gerrit_patch.change_id)
      self.assertEqual(element.getAttribute(
          lkgm_manager.PALADIN_COMMIT_ATTR), gerrit_patch.commit)
      self.assertEqual(element.getAttribute(lkgm_manager.PALADIN_PROJECT_ATTR),
                       gerrit_patch.project)
      self.assertEqual(element.getAttribute(lkgm_manager.PALADIN_REMOTE_ATTR),
                       gerrit_patch.remote)
      self.assertEqual(element.getAttribute(lkgm_manager.PALADIN_BRANCH_ATTR),
                       gerrit_patch.tracking_branch)
      self.assertEqual(element.getAttribute(lkgm_manager.PALADIN_REF_ATTR),
                       gerrit_patch.ref)
      self.assertEqual(
          element.getAttribute(lkgm_manager.PALADIN_OWNER_EMAIL_ATTR),
          gerrit_patch.owner_email)
      self.assertEqual(
          element.getAttribute(lkgm_manager.PALADIN_PROJECT_URL_ATTR),
          gerrit_patch.project_url)
      self.assertEqual(
          element.getAttribute(lkgm_manager.PALADIN_PATCH_NUMBER_ATTR),
          gerrit_patch.patch_number)
      self.assertEqual(
          element.getAttribute(lkgm_manager.PALADIN_FAIL_COUNT_ATTR),
          str(gerrit_patch.fail_count))
      self.assertEqual(
          element.getAttribute(lkgm_manager.PALADIN_PASS_COUNT_ATTR),
          str(gerrit_patch.pass_count))
      self.assertEqual(
          element.getAttribute(lkgm_manager.PALADIN_TOTAL_FAIL_COUNT_ATTR),
          str(gerrit_patch.total_fail_count))

