# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module containing the generic builders."""

from __future__ import print_function

import multiprocessing
import os
import sys
import tempfile
import traceback

from chromite.cbuildbot import constants
from chromite.cbuildbot import failures_lib
from chromite.cbuildbot import results_lib
from chromite.cbuildbot import trybot_patch_pool
from chromite.cbuildbot.stages import build_stages
from chromite.cbuildbot.stages import report_stages
from chromite.cbuildbot.stages import sync_stages
from chromite.lib import cidb
from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import cros_logging as logging
from chromite.lib import git
from chromite.lib import parallel


class Builder(object):
  """Parent class for all builder types.

  This class functions as an abstract parent class for various build types.
  Its intended use is builder_instance.Run().

  Attributes:
    _run: The BuilderRun object for this run.
    archive_stages: Dict of BuildConfig keys to ArchiveStage values.
    patch_pool: TrybotPatchPool.
  """

  def __init__(self, builder_run):
    """Initializes instance variables. Must be called by all subclasses."""
    self._run = builder_run

    # TODO: all the fields below should not be part of the generic builder.
    # We need to restructure our SimpleBuilder and see about creating a new
    # base in there for holding them.
    if self._run.config.chromeos_official:
      os.environ['CHROMEOS_OFFICIAL'] = '1'

    self.archive_stages = {}
    self.patch_pool = trybot_patch_pool.TrybotPatchPool()
    self._build_image_lock = multiprocessing.Lock()

  def Initialize(self):
    """Runs through the initialization steps of an actual build."""
    if self._run.options.resume:
      results_lib.LoadCheckpoint(self._run.buildroot)

    self._RunStage(report_stages.BuildStartStage)

    self._RunStage(build_stages.CleanUpStage)

  def _GetStageInstance(self, stage, *args, **kwargs):
    """Helper function to get a stage instance given the args.

    Useful as almost all stages just take in builder_run.
    """
    # Normally the default BuilderRun (self._run) is used, but it can
    # be overridden with "builder_run" kwargs (e.g. for child configs).
    builder_run = kwargs.pop('builder_run', self._run)
    return stage(builder_run, *args, **kwargs)

  def _SetReleaseTag(self):
    """Sets run.attrs.release_tag from the manifest manager used in sync.

    Must be run after sync stage as syncing enables us to have a release tag,
    and must be run before any usage of attrs.release_tag.

    TODO(mtennant): Find a bottleneck place in syncing that can set this
    directly.  Be careful, as there are several kinds of syncing stages, and
    sync stages have been known to abort with sys.exit calls.
    """
    manifest_manager = getattr(self._run.attrs, 'manifest_manager', None)
    if manifest_manager:
      self._run.attrs.release_tag = manifest_manager.current_version
    else:
      self._run.attrs.release_tag = None

    logging.debug('Saved release_tag value for run: %r',
                  self._run.attrs.release_tag)

  def _RunStage(self, stage, *args, **kwargs):
    """Wrapper to run a stage.

    Args:
      stage: A BuilderStage class.
      args: args to pass to stage constructor.
      kwargs: kwargs to pass to stage constructor.

    Returns:
      Whatever the stage's Run method returns.
    """
    stage_instance = self._GetStageInstance(stage, *args, **kwargs)
    return stage_instance.Run()

  @staticmethod
  def _RunParallelStages(stage_objs):
    """Run the specified stages in parallel.

    Args:
      stage_objs: BuilderStage objects.
    """
    steps = [stage.Run for stage in stage_objs]
    try:
      parallel.RunParallelSteps(steps)

    except BaseException as ex:
      # If a stage threw an exception, it might not have correctly reported
      # results (e.g. because it was killed before it could report the
      # results.) In this case, attribute the exception to any stages that
      # didn't report back correctly (if any).
      for stage in stage_objs:
        for name in stage.GetStageNames():
          if not results_lib.Results.StageHasResults(name):
            results_lib.Results.Record(name, ex, str(ex))

      if cidb.CIDBConnectionFactory.IsCIDBSetup():
        db = cidb.CIDBConnectionFactory.GetCIDBConnectionForBuilder()
        if db:
          for stage in stage_objs:
            for build_stage_id in stage.GetBuildStageIDs():
              if not db.HasBuildStageFailed(build_stage_id):
                failures_lib.ReportStageFailureToCIDB(db,
                                                      build_stage_id,
                                                      ex)

      raise

  def _RunSyncStage(self, sync_instance):
    """Run given |sync_instance| stage and be sure attrs.release_tag set."""
    try:
      sync_instance.Run()
    finally:
      self._SetReleaseTag()

  def SetVersionInfo(self):
    """Sync the builder's version info with the buildbot runtime."""
    self._run.attrs.version_info = self.GetVersionInfo()

  def GetVersionInfo(self):
    """Returns a manifest_version.VersionInfo object for this build.

    Subclasses must override this method.
    """
    raise NotImplementedError()

  def GetSyncInstance(self):
    """Returns an instance of a SyncStage that should be run.

    Subclasses must override this method.
    """
    raise NotImplementedError()

  def GetCompletionInstance(self):
    """Returns the MasterSlaveSyncCompletionStage for this build.

    Subclasses may override this method.

    Returns:
      None
    """
    return None

  def RunStages(self):
    """Subclasses must override this method.  Runs the appropriate code."""
    raise NotImplementedError()

  def _ReExecuteInBuildroot(self, sync_instance):
    """Reexecutes self in buildroot and returns True if build succeeds.

    This allows the buildbot code to test itself when changes are patched for
    buildbot-related code.  This is a no-op if the buildroot == buildroot
    of the running chromite checkout.

    Args:
      sync_instance: Instance of the sync stage that was run to sync.

    Returns:
      True if the Build succeeded.
    """
    if not self._run.options.resume:
      results_lib.WriteCheckpoint(self._run.options.buildroot)

    args = sync_stages.BootstrapStage.FilterArgsForTargetCbuildbot(
        self._run.options.buildroot, constants.PATH_TO_CBUILDBOT,
        self._run.options)

    # Specify a buildroot explicitly (just in case, for local trybot).
    # Suppress any timeout options given from the commandline in the
    # invoked cbuildbot; our timeout will enforce it instead.
    args += ['--resume', '--timeout', '0', '--notee', '--nocgroups',
             '--buildroot', os.path.abspath(self._run.options.buildroot)]

    if hasattr(self._run.attrs, 'manifest_manager'):
      # TODO(mtennant): Is this the same as self._run.attrs.release_tag?
      ver = self._run.attrs.manifest_manager.current_version
      args += ['--version', ver]

    pool = getattr(sync_instance, 'pool', None)
    if pool:
      filename = os.path.join(self._run.options.buildroot,
                              'validation_pool.dump')
      pool.Save(filename)
      args += ['--validation_pool', filename]

    # Reset the cache dir so that the child will calculate it automatically.
    if not self._run.options.cache_dir_specified:
      commandline.BaseParser.ConfigureCacheDir(None)

    with tempfile.NamedTemporaryFile(prefix='metadata') as metadata_file:
      metadata_file.write(self._run.attrs.metadata.GetJSON())
      metadata_file.flush()
      args += ['--metadata_dump', metadata_file.name]

      # Re-run the command in the buildroot.
      # Finally, be generous and give the invoked cbuildbot 30s to shutdown
      # when something occurs.  It should exit quicker, but the sigterm may
      # hit while the system is particularly busy.
      return_obj = cros_build_lib.RunCommand(
          args, cwd=self._run.options.buildroot, error_code_ok=True,
          kill_timeout=30)
      return return_obj.returncode == 0

  def _InitializeTrybotPatchPool(self):
    """Generate patch pool from patches specified on the command line.

    Do this only if we need to patch changes later on.
    """
    changes_stage = sync_stages.PatchChangesStage.StageNamePrefix()
    check_func = results_lib.Results.PreviouslyCompletedRecord
    if not check_func(changes_stage) or self._run.options.bootstrap:
      options = self._run.options
      self.patch_pool = trybot_patch_pool.TrybotPatchPool.FromOptions(
          gerrit_patches=options.gerrit_patches,
          local_patches=options.local_patches,
          sourceroot=options.sourceroot,
          remote_patches=options.remote_patches)

  def _GetBootstrapStage(self):
    """Constructs and returns the BootStrapStage object.

    We return None when there are no chromite patches to test, and
    --test-bootstrap wasn't passed in.
    """
    stage = None
    chromite_pool = self.patch_pool.Filter(project=constants.CHROMITE_PROJECT)
    if self._run.config.internal:
      manifest_pool = self.patch_pool.FilterIntManifest()
    else:
      manifest_pool = self.patch_pool.FilterExtManifest()
    chromite_branch = git.GetChromiteTrackingBranch()
    if (chromite_pool or manifest_pool or
        self._run.options.test_bootstrap or
        chromite_branch != self._run.options.branch):
      stage = sync_stages.BootstrapStage(self._run, chromite_pool,
                                         manifest_pool)
    return stage

  def Run(self):
    """Main runner for this builder class.  Runs build and prints summary.

    Returns:
      Whether the build succeeded.
    """
    self._InitializeTrybotPatchPool()

    if self._run.options.bootstrap:
      bootstrap_stage = self._GetBootstrapStage()
      if bootstrap_stage:
        # BootstrapStage blocks on re-execution of cbuildbot.
        bootstrap_stage.Run()
        return bootstrap_stage.returncode == 0

    print_report = True
    exception_thrown = False
    success = True
    sync_instance = None
    try:
      self.Initialize()
      sync_instance = self.GetSyncInstance()
      self._RunSyncStage(sync_instance)

      if self._run.ShouldPatchAfterSync():
        # Filter out patches to manifest, since PatchChangesStage can't handle
        # them.  Manifest patches are patched in the BootstrapStage.
        non_manifest_patches = self.patch_pool.FilterManifest(negate=True)
        if non_manifest_patches:
          self._RunStage(sync_stages.PatchChangesStage, non_manifest_patches)

      # Now that we have a fully synced & patched tree, we can let the builder
      # extract version information from the sources for this particular build.
      self.SetVersionInfo()
      if self._run.ShouldReexecAfterSync():
        print_report = False
        success = self._ReExecuteInBuildroot(sync_instance)
      else:
        self._RunStage(report_stages.BuildReexecutionFinishedStage)
        self.RunStages()

    except Exception as ex:
      exception_thrown = True
      if results_lib.Results.BuildSucceededSoFar():
        # If the build is marked as successful, but threw exceptions, that's a
        # problem. Print the traceback for debugging.
        if isinstance(ex, failures_lib.CompoundFailure):
          print(str(ex))

        traceback.print_exc(file=sys.stdout)
        raise

      if not (print_report and isinstance(ex, failures_lib.StepFailure)):
        # If the failed build threw a non-StepFailure exception, we
        # should raise it.
        raise

    finally:
      if print_report:
        results_lib.WriteCheckpoint(self._run.options.buildroot)
        completion_instance = self.GetCompletionInstance()
        self._RunStage(report_stages.ReportStage, sync_instance,
                       completion_instance)
        success = results_lib.Results.BuildSucceededSoFar()
        if exception_thrown and success:
          success = False
          cros_build_lib.PrintBuildbotStepWarnings()
          print("""\
Exception thrown, but all stages marked successful. This is an internal error,
because the stage that threw the exception should be marked as failing.""")

    return success
