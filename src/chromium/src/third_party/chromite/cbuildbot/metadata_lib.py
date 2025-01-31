# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module containing class for recording metadata about a run."""

from __future__ import print_function

import collections
import datetime
import json
import math
import multiprocessing
import os
import re

from chromite.cbuildbot import archive_lib
from chromite.cbuildbot import cbuildbot_config
from chromite.cbuildbot import results_lib
from chromite.cbuildbot import constants
from chromite.lib import clactions
from chromite.lib import cros_build_lib
from chromite.lib import cros_logging as logging
from chromite.lib import gs
from chromite.lib import parallel


# Number of parallel processes used when uploading/downloading GS files.
MAX_PARALLEL = 40

ARCHIVE_ROOT = 'gs://chromeos-image-archive/%(target)s'
# NOTE: gsutil 3.42 has a bug where '/' is ignored in this context unless it
#       is listed twice. So we list it twice here for now.
METADATA_URL_GLOB = os.path.join(ARCHIVE_ROOT,
                                 'R%(milestone)s**//metadata.json')
LATEST_URL = os.path.join(ARCHIVE_ROOT, 'LATEST-master')


GerritPatchTuple = clactions.GerritPatchTuple
GerritChangeTuple = clactions.GerritChangeTuple
CLActionTuple = collections.namedtuple('CLActionTuple',
                                       ['change', 'action', 'timestamp',
                                        'reason'])
CLActionWithBuildTuple = collections.namedtuple(
    'CLActionWithBuildTuple',
    ['change', 'action', 'timestamp', 'reason', 'bot_type', 'build'])


class _DummyLock(object):
  """A Dummy clone of RLock that does nothing."""
  def acquire(self, blocking=1):
    pass

  def release(self):
    pass

  def __exit__(self, exc_type, exc_value, traceback):
    pass

  def __enter__(self):
    pass

class CBuildbotMetadata(object):
  """Class for recording metadata about a run."""

  def __init__(self, metadata_dict=None, multiprocess_manager=None):
    """Constructor for CBuildbotMetadata.

    Args:
      metadata_dict: Optional dictionary containing initial metadata,
                     as returned by loading metadata from json.
      multiprocess_manager: Optional multiprocess.Manager instance. If
                            supplied, the metadata instance will use
                            multiprocess containers so that its state
                            is correctly synced across processes.
    """
    super(CBuildbotMetadata, self).__init__()
    if multiprocess_manager:
      self._metadata_dict = multiprocess_manager.dict()
      self._cl_action_list = multiprocess_manager.list()
      self._per_board_dict = multiprocess_manager.dict()
      self._subdict_update_lock = multiprocess_manager.RLock()
    else:
      self._metadata_dict = {}
      self._cl_action_list = []
      self._per_board_dict = {}
      # If we are not using a manager, then metadata is not expected to be
      # multiprocess safe. Use a dummy RLock.
      self._subdict_update_lock = _DummyLock()

    if metadata_dict:
      self.UpdateWithDict(metadata_dict)

  @staticmethod
  def FromJSONString(json_string):
    """Construct a CBuildbotMetadata from a json representation.

    Args:
      json_string: A string json representation of a CBuildbotMetadata
                   dictionary.

    Returns:
      A CbuildbotMetadata instance.
    """
    return CBuildbotMetadata(json.loads(json_string))

  def UpdateWithDict(self, metadata_dict):
    """Update metadata dictionary with values supplied in |metadata_dict|

    This method is effectively the inverse of GetDict. Existing key-values
    in metadata will be overwritten by those supplied in |metadata_dict|,
    with the exceptions of:
     - the cl_actions list which will be extended with the contents (if any)
     of the supplied dict's cl_actions list.
     - the per-board metadata dict, which will be recursively extended with the
       contents of the supplied dict's board-metadata

    Args:
      metadata_dict: A dictionary of key-value pairs to be added this
                     metadata instance. Keys should be strings, values
                     should be json-able.

    Returns:
      self
    """
    # This is effectively the inverse of the dictionary construction in GetDict,
    # to reconstruct the correct internal representation of a metadata
    # object.
    metadata_dict = metadata_dict.copy()
    cl_action_list = metadata_dict.pop('cl_actions', None)
    per_board_dict = metadata_dict.pop('board-metadata', None)
    self._metadata_dict.update(metadata_dict)
    if cl_action_list:
      self._cl_action_list.extend(cl_action_list)
    if per_board_dict:
      for k, v in per_board_dict.items():
        self.UpdateBoardDictWithDict(k, v)

    return self

  def UpdateBoardDictWithDict(self, board, board_dict):
    """Update the per-board dict for |board| with |board_dict|.

    Note: both |board| and and all the keys of |board_dict| musts be strings
          that do not contain the character ':'

    Returns:
      self
    """
    # Wrap the per-board key-value pairs as key-value pairs in _per_board_dict.
    # Note -- due to http://bugs.python.org/issue6766 it is not possible to
    # store a multiprocess dict proxy inside another multiprocess dict proxy.
    # That is why we are using this flattened representation of board dicts.
    assert not ':' in board
    # Even if board_dict is {}, ensure that an entry with this board
    # gets written.
    self._per_board_dict[board + ':'] = None
    for k, v in board_dict.items():
      assert not ':' in k
      self._per_board_dict['%s:%s' % (board, k)] = v

    return self

  def UpdateKeyDictWithDict(self, key, key_metadata_dict):
    """Update metadata for the given key with values supplied in |metadata_dict|

    This method merges the dictionary for the given key with the given key
    metadata dictionary (allowing them to be effectively updated from any
    stage).

    This method is multiprocess safe.

    Args:
      key: The key name (e.g. 'version' or 'status')
      key_metadata_dict: A dictionary of key-value pairs to be added this
                     metadata key. Keys should be strings, values
                     should be json-able.

    Returns:
      self
    """
    with self._subdict_update_lock:
      # If the key already exists, then use its dictionary
      target_dict = self._metadata_dict.setdefault(key, {})
      target_dict.update(key_metadata_dict)
      self._metadata_dict[key] = target_dict

    return self

  def GetDict(self):
    """Returns a dictionary representation of metadata."""
    # CL actions are be stored in self._cl_action_list instead of
    # in self._metadata_dict['cl_actions'], because _cl_action_list
    # is potentially a multiprocess.lis. So, _cl_action_list needs to
    # be copied into a normal list.
    temp = self._metadata_dict.copy()
    temp['cl_actions'] = list(self._cl_action_list)

    # Similarly, the per-board dicts are stored in a flattened form in
    # _per_board_dict. Un-flatten into nested dict.
    per_board_dict = {}
    for k, v in self._per_board_dict.items():
      board, key = k.split(':')
      board_dict = per_board_dict.setdefault(board, {})
      if key:
        board_dict[key] = v

    temp['board-metadata'] = per_board_dict
    return temp

  # TODO(akeshet): crbug.com/406522 special case cl_actions and board-metadata
  # so that GetValue can work with them as well.
  def GetValue(self, key):
    """Get an item from the metadata dictionary.

    This method is in most cases an inexpensive equivalent to:
    GetDict()[key]

    However, it cannot be used for items like 'cl_actions' or 'board-metadata'
    which are not stored directly in the metadata dictionary.
    """
    return self._metadata_dict[key]

  def GetJSON(self):
    """Return a JSON string representation of metadata."""
    return json.dumps(self.GetDict())

  def RecordCLAction(self, change, action, timestamp=None, reason=''):
    """Record an action that was taken on a CL, to the metadata.

    Args:
      change: A GerritPatch object for the change acted on.
      action: The action taken, should be one of constants.CL_ACTIONS
      timestamp: An integer timestamp such as int(time.time()) at which
                 the action was taken. Default: Now.
      reason: Description of the reason the action was taken. Default: ''

    Returns:
      self
    """
    cl_action = clactions.CLAction.FromGerritPatchAndAction(change, action,
                                                            reason, timestamp)
    self._cl_action_list.append(cl_action.AsMetadataEntry())
    return self

  @staticmethod
  def GetReportMetadataDict(builder_run, get_changes_from_pool,
                            get_statuses_from_slaves, config=None, stage=None,
                            final_status=None, sync_instance=None,
                            completion_instance=None, child_configs_list=None):
    """Return a metadata dictionary summarizing a build.

    This method replaces code that used to exist in the ArchivingStageMixin
    class from cbuildbot_stage. It contains all the Report-stage-time
    metadata construction logic. The logic here is intended to be gradually
    refactored out so that the metadata is constructed gradually by the
    stages that are responsible for pieces of data, as they run.

    Args:
      builder_run: BuilderRun instance for this run.
      get_changes_from_pool: If True, information about patches in the
                             sync_instance.pool will be recorded.
      get_statuses_from_slaves: If True, status information of slave
                                builders will be recorded.
      config: The build config for this run.  Defaults to self._run.config.
      stage: The stage name that this metadata file is being uploaded for.
      final_status: Whether the build passed or failed. If None, the build
                    will be treated as still running.
      sync_instance: The stage instance that was used for syncing the source
                     code. This should be a derivative of SyncStage. If None,
                     the list of commit queue patches will not be included
                     in the metadata.
      completion_instance: The stage instance that was used to wait for slave
                           completion. Used to add slave build information to
                           master builder's metadata. If None, no such status
                           information will be included. It not None, this
                           should be a derivative of
                           MasterSlaveSyncCompletionStage.
      child_configs_list: The list of child config metadata.  If specified it
                          should be added to the metadata.

    Returns:
       A metadata dictionary suitable to be json-serialized.
    """
    config = config or builder_run.config
    start_time = results_lib.Results.start_time
    current_time = datetime.datetime.now()
    start_time_stamp = cros_build_lib.UserDateTimeFormat(timeval=start_time)
    current_time_stamp = cros_build_lib.UserDateTimeFormat(timeval=current_time)
    duration = '%s' % (current_time - start_time,)

    metadata = {
        'status': {
            'current-time': current_time_stamp,
            'status': final_status if final_status else 'running',
            'summary': stage or '',
        },
        'time': {
            'start': start_time_stamp,
            'finish': current_time_stamp if final_status else '',
            'duration': duration,
        }
    }

    metadata['results'] = []
    for entry in results_lib.Results.Get():
      timestr = datetime.timedelta(seconds=math.ceil(entry.time))
      if entry.result in results_lib.Results.NON_FAILURE_TYPES:
        status = constants.FINAL_STATUS_PASSED
      else:
        status = constants.FINAL_STATUS_FAILED
      metadata['results'].append({
          'name': entry.name,
          'status': status,
          # The result might be a custom exception.
          'summary': str(entry.result),
          'duration': '%s' % timestr,
          'board': entry.board,
          'description': entry.description,
          'log': builder_run.ConstructDashboardURL(stage=entry.name),
      })

    if child_configs_list:
      metadata['child-configs'] = child_configs_list

    if get_changes_from_pool:
      changes = []
      pool = sync_instance.pool
      for change in pool.changes:
        details = {'gerrit_number': change.gerrit_number,
                   'patch_number': change.patch_number,
                   'internal': change.internal}
        changes.append(details)
      metadata['changes'] = changes

    # If we were a CQ master, then include a summary of the status of slave cq
    # builders in metadata
    if get_statuses_from_slaves:
      statuses = completion_instance.GetSlaveStatuses()
      if not statuses:
        logging.warning('completion_instance did not have any statuses '
                        'to report. Will not add slave status to metadata.')

      metadata['slave_targets'] = {}
      for builder, status in statuses.iteritems():
        metadata['slave_targets'][builder] = status.AsFlatDict()

    return metadata


# The graphite graphs use seconds since epoch start as time value.
EPOCH_START = datetime.datetime(1970, 1, 1)

# Formats we like for output.
NICE_DATE_FORMAT = '%Y/%m/%d'
NICE_TIME_FORMAT = '%H:%M:%S'
NICE_DATETIME_FORMAT = NICE_DATE_FORMAT + ' ' + NICE_TIME_FORMAT


# TODO(akeshet): Merge this class into CBuildbotMetadata.
class BuildData(object):
  """Class for examining metadata from a prior run.

  The raw metadata dict can be accessed at self.metadata_dict or via []
  and get() on a BuildData object.  Some values from metadata_dict are
  also surfaced through the following list of supported properties:

  build_id
  build_number
  stages
  slaves
  chromeos_version
  chrome_version
  bot_id
  status
  start_datetime
  finish_datetime
  start_date_str
  start_time_str
  start_datetime_str
  finish_date_str
  finish_time_str
  finish_datetime_str
  runtime_seconds
  runtime_minutes
  epoch_time_seconds
  count_changes
  run_date
  failure_message
  """

  __slots__ = (
      'gathered_dict',  # Dict with gathered data (sheets version).
      'gathered_url',   # URL to metadata.json.gathered location in GS.
      'metadata_dict',  # Dict representing metadata data from JSON.
      'metadata_url',   # URL to metadata.json location in GS.
  )

  # Regexp for parsing datetimes as stored in metadata.json.  Example text:
  # Fri, 14 Feb 2014 17:00:49 -0800 (PST)
  DATETIME_RE = re.compile(r'^(.+)\s-\d\d\d\d\s\(P\wT\)$')

  SHEETS_VER_KEY = 'sheets_version'

  @staticmethod
  def ReadMetadataURLs(urls, gs_ctx=None, exclude_running=True,
                       get_sheets_version=False):
    """Read a list of metadata.json URLs and return BuildData objects.

    Args:
      urls: List of metadata.json GS URLs.
      gs_ctx: A GSContext object to use.  If not provided gs.GSContext will
        be called to get a GSContext to use.
      exclude_running: If True the metadata for builds that are still running
        will be skipped.
      get_sheets_version: Whether to try to figure out the last sheets version
        that was gathered. This requires an extra gsutil request and is only
        needed if you are writing the metadata to the Google Sheets
        spreadsheet.

    Returns:
      List of BuildData objects.
    """
    gs_ctx = gs_ctx or gs.GSContext()
    logging.info('Reading %d metadata URLs using %d processes now.', len(urls),
                 MAX_PARALLEL)

    build_data_per_url = {}
    def _ReadMetadataURL(url):
      # Read the metadata.json URL and parse json into a dict.
      metadata_dict = json.loads(gs_ctx.Cat(url, print_cmd=False))

      # Read the file next to url which indicates whether the metadata has
      # been gathered before, and with what stats version.
      if get_sheets_version:
        gathered_dict = {}
        gathered_url = url + '.gathered'
        if gs_ctx.Exists(gathered_url, print_cmd=False):
          gathered_dict = json.loads(gs_ctx.Cat(gathered_url,
                                                print_cmd=False))

        sheets_version = gathered_dict.get(BuildData.SHEETS_VER_KEY)
      else:
        sheets_version = None

      bd = BuildData(url, metadata_dict, sheets_version=sheets_version)

      if bd.build_number is None:
        logging.warning('Metadata at %s was missing build number.', url)
        m = re.match(r'.*-b([0-9]*)/.*', url)
        if m:
          inferred_number = int(m.groups()[0])
          logging.warning('Inferred build number %d from metadata url.',
                          inferred_number)
          bd.metadata_dict['build-number'] = inferred_number
      if sheets_version is not None:
        logging.debug('Read %s:\n  build_number=%d, sheets v%d', url,
                      bd.build_number, sheets_version)
      else:
        logging.debug('Read %s:\n  build_number=%d, ungathered', url,
                      bd.build_number)

      build_data_per_url[url] = bd

    with multiprocessing.Manager() as manager:
      build_data_per_url = manager.dict()
      parallel.RunTasksInProcessPool(_ReadMetadataURL, [[url] for url in urls],
                                     processes=MAX_PARALLEL)
      builds = [build_data_per_url[url] for url in urls]

    if exclude_running:
      builds = [b for b in builds if b.status != 'running']
    return builds

  @staticmethod
  def MarkBuildsGathered(builds, sheets_version, gs_ctx=None):
    """Mark specified |builds| as processed for the given stats versions.

    Args:
      builds: List of BuildData objects.
      sheets_version: The Google Sheets version these builds are now processed
        for.
      gs_ctx: A GSContext object to use, if set.
    """
    gs_ctx = gs_ctx or gs.GSContext()

    # Filter for builds that were not already on these versions.
    builds = [b for b in builds if b.sheets_version != sheets_version]
    if builds:
      log_ver_str = 'Sheets v%d' % sheets_version
      logging.info('Marking %d builds gathered (for %s) using %d processes'
                   ' now.', len(builds), log_ver_str, MAX_PARALLEL)

      def _MarkGathered(build):
        build.MarkGathered(sheets_version)
        json_text = json.dumps(build.gathered_dict.copy())
        gs_ctx.Copy('-', build.gathered_url, input=json_text, print_cmd=False)
        logging.debug('Marked build_number %d processed for %s.',
                      build.build_number, log_ver_str)

      inputs = [[build] for build in builds]
      parallel.RunTasksInProcessPool(_MarkGathered, inputs,
                                     processes=MAX_PARALLEL)

  def __init__(self, metadata_url, metadata_dict, sheets_version=None):
    self.metadata_url = metadata_url
    self.metadata_dict = metadata_dict

    # If a stats version is not specified default to -1 so that the initial
    # version (version 0) will be considered "newer".
    self.gathered_url = metadata_url + '.gathered'
    self.gathered_dict = {
        self.SHEETS_VER_KEY: -1 if sheets_version is None else sheets_version,
    }

  def MarkGathered(self, sheets_version):
    """Mark this build as processed for the given stats versions."""
    self.gathered_dict[self.SHEETS_VER_KEY] = sheets_version

  def __getitem__(self, key):
    """Relay dict-like access to self.metadata_dict."""
    return self.metadata_dict[key]

  def get(self, key, default=None):
    """Relay dict-like access to self.metadata_dict."""
    return self.metadata_dict.get(key, default)

  @property
  def sheets_version(self):
    return self.gathered_dict[self.SHEETS_VER_KEY]

  @property
  def build_number(self):
    try:
      return int(self['build-number'])
    except KeyError:
      return None

  @property
  def stages(self):
    return self['results']

  @property
  def slaves(self):
    return self.get('slave_targets', {})

  @property
  def chromeos_version(self):
    try:
      return self['version']['full']
    except KeyError:
      return None

  @property
  def chrome_version(self):
    try:
      return self['version']['chrome']
    except KeyError:
      return None

  @property
  def bot_id(self):
    return self['bot-config']

  @property
  def status(self):
    return self.get('status', {}).get('status', None)

  @classmethod
  def _ToDatetime(cls, time_str):
    match = cls.DATETIME_RE.search(time_str)
    if match:
      return datetime.datetime.strptime(match.group(1), '%a, %d %b %Y %H:%M:%S')
    else:
      raise ValueError('Unexpected metadata datetime format: %s' % time_str)

  @property
  def start_datetime(self):
    return self._ToDatetime(self['time']['start'])

  @property
  def finish_datetime(self):
    return self._ToDatetime(self['time']['finish'])

  @property
  def start_date_str(self):
    return self.start_datetime.strftime(NICE_DATE_FORMAT)

  @property
  def start_time_str(self):
    return self.start_datetime.strftime(NICE_TIME_FORMAT)

  @property
  def start_datetime_str(self):
    return self.start_datetime.strftime(NICE_DATETIME_FORMAT)

  @property
  def finish_date_str(self):
    return self.finish_datetime.strftime(NICE_DATE_FORMAT)

  @property
  def finish_time_str(self):
    return self.finish_datetime.strftime(NICE_TIME_FORMAT)

  @property
  def finish_datetime_str(self):
    return self.finish_datetime.strftime(NICE_DATETIME_FORMAT)

  @property
  def failure_message(self):
    message_list = []
    # First collect failures in the master stages.
    failed_stages = [s for s in self.stages if s['status'] == 'failed']
    for stage in failed_stages:
      if stage['summary']:
        message_list.append('master: %s' % stage['summary'])

    mapping = {}
    # Dedup the messages from the slaves.
    for slave in self.GetFailedSlaves():
      message = self.slaves[slave]['reason']
      mapping[message] = mapping.get(message, []) + [slave]

    for message, slaves in mapping.iteritems():
      if len(slaves) >= 6:
        # Do not print all the names when there are more than 6 (an
        # arbitrary number) builders.
        message_list.append('%d buliders: %s' % (len(slaves), message))
      else:
        message_list.append('%s: %s' % (','.join(slaves), message))

    return ' | '.join(message_list)

  def GetFailedStages(self, with_urls=False):
    """Get names of all failed stages, optionally with URLs for each.

    Args:
      with_urls: If True then also return URLs.  See Returns.

    Returns:
      If with_urls is False, return list of stage names.  Otherwise, return list
        of tuples (stage name, stage URL).
    """
    def _Failed(stage):
      # This can be more discerning in the future, such as for optional stages.
      return stage['status'] == 'failed'

    if with_urls:
      # The "log" url includes "/logs/stdio" on the end.  Strip that off.
      return [(s['name'], os.path.dirname(os.path.dirname(s['log'])))
              for s in self.stages if _Failed(s)]
    else:
      return [s['name'] for s in self.stages if _Failed(s)]

  def GetFailedSlaves(self, with_urls=False):
    def _Failed(slave):
      return slave['status'] == 'fail'

    # Older metadata has no slave_targets entry.
    slaves = self.slaves
    if with_urls:
      return [(name, slave['dashboard_url'])
              for name, slave in slaves.iteritems() if _Failed(slave)]
    else:
      return [name for name, slave in slaves.iteritems() if _Failed(slave)]

    return []

  @property
  def runtime_seconds(self):
    return (self.finish_datetime - self.start_datetime).seconds

  @property
  def runtime_minutes(self):
    return self.runtime_seconds / 60

  @property
  def epoch_time_seconds(self):
    # End time seconds since 1/1/1970, for some reason.
    return int((self.finish_datetime - EPOCH_START).total_seconds())

  @property
  def patches(self):
    return [GerritPatchTuple(gerrit_number=int(change['gerrit_number']),
                             patch_number=int(change['patch_number']),
                             internal=change['internal'])
            for change in self.metadata_dict.get('changes', [])]

  @property
  def count_changes(self):
    if not self.metadata_dict.get('changes', None):
      return 0

    return len(self.metadata_dict['changes'])

  @property
  def build_id(self):
    return self.metadata_dict['build_id']

  @property
  def run_date(self):
    return self.finish_datetime.strftime('%d.%m.%Y')

  def Passed(self):
    """Return True if this represents a successful run."""
    return 'passed' == self.metadata_dict['status']['status'].strip()



def FindLatestFullVersion(builder, version):
  """Find the latest full version number built by |builder| on |version|.

  Args:
    builder: Builder to load information from. E.g. daisy-release
    version: Version that we are interested in. E.g. 5602.0.0

  Returns:
    The latest corresponding full version number, including milestone prefix.
    E.g. R35-5602.0.0. For some builders, this may also include a -rcN or
    -bNNNN suffix.
  """
  gs_ctx = gs.GSContext()
  config = cbuildbot_config.GetConfig()[builder]
  base_url = archive_lib.GetBaseUploadURI(config)
  latest_file_url = os.path.join(base_url, 'LATEST-%s' % version)
  try:
    return gs_ctx.Cat(latest_file_url).strip()
  except gs.GSNoSuchKey:
    return None


def GetBuildMetadata(builder, full_version):
  """Fetch the metadata.json object for |builder| and |full_version|.

  Args:
    builder: Builder to load information from. E.g. daisy-release
    full_version: Version that we are interested in, including milestone
        prefix. E.g. R35-5602.0.0. For some builders, this may also include a
        -rcN or -bNNNN suffix.

  Returns:
    A newly created CBuildbotMetadata object with the metadata from the given
    |builder| and |full_version|.
  """
  gs_ctx = gs.GSContext()
  config = cbuildbot_config.GetConfig()[builder]
  base_url = archive_lib.GetBaseUploadURI(config)
  try:
    archive_url = os.path.join(base_url, full_version)
    metadata_url = os.path.join(archive_url, constants.METADATA_JSON)
    output = gs_ctx.Cat(metadata_url)
    return CBuildbotMetadata(json.loads(output))
  except gs.GSNoSuchKey:
    return None


class MetadataException(Exception):
  """Base exception class for exceptions in this module."""


class GetMilestoneError(MetadataException):
  """Base exception class for exceptions in this module."""


def GetLatestMilestone():
  """Get the latest milestone from CQ Master LATEST-master file."""
  # Use CQ Master target to get latest milestone.
  latest_url = LATEST_URL % {'target': constants.CQ_MASTER}
  gs_ctx = gs.GSContext()

  logging.info('Getting latest milestone from %s', latest_url)
  try:
    content = gs_ctx.Cat(latest_url).strip()

    # Expected syntax is like the following: "R35-1234.5.6-rc7".
    assert content.startswith('R')
    milestone = content.split('-')[0][1:]
    logging.info('Latest milestone determined to be: %s', milestone)
    return int(milestone)

  except gs.GSNoSuchKey:
    raise GetMilestoneError('LATEST file missing: %s' % latest_url)


def GetMetadataURLsSince(target, start_date, end_date):
  """Get metadata.json URLs for |target| from |start_date| until |end_date|.

  The modified time of the GS files is used to compare with start_date, so
  the completion date of the builder run is what is important here.

  Args:
    target: Builder target name.
    start_date: datetime.date object of starting date.
    end_date: datetime.date object of ending date.

  Returns:
    Metadata urls for runs found.
  """
  ret = []
  milestone = GetLatestMilestone()
  gs_ctx = gs.GSContext()
  while True:
    base_url = METADATA_URL_GLOB % {'target': target, 'milestone': milestone}
    logging.info('Getting %s builds for R%d from "%s"', target, milestone,
                 base_url)

    try:
      # Get GS URLs.  We want the datetimes to quickly know when we are done
      # collecting URLs.
      urls = gs_ctx.List(base_url, details=True)
    except gs.GSNoSuchKey:
      # We ran out of metadata to collect.  Stop searching back in time.
      logging.info('No %s builds found for $%d.  I will not continue search'
                   ' to older milestones.', target, milestone)
      break

    # Sort by timestamp.
    urls = sorted(urls, key=lambda x: x.creation_time, reverse=True)

    # Add relevant URLs to our list.
    ret.extend([x.url for x in urls
                if (x.creation_time.date() >= start_date and
                    x.creation_time.date() <= end_date)])

    # See if we have gone far enough back by checking datetime of oldest URL
    # in the current batch.
    if urls[-1].creation_time.date() < start_date:
      break
    else:
      milestone -= 1
      logging.info('Continuing on to R%d.', milestone)

  return ret
