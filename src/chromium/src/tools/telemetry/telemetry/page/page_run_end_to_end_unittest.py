# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import re
import shutil
import sys
import StringIO
import tempfile
import unittest

from telemetry import benchmark
from telemetry import story
from telemetry.core import exceptions
from telemetry.core import util
from telemetry import decorators
from telemetry.internal.browser import browser_finder
from telemetry.internal.browser import user_agent
from telemetry.internal.results import results_options
from telemetry.internal import story_runner
from telemetry.internal.testing.page_sets import example_domain
from telemetry.internal.util import exception_formatter
from telemetry.page import page as page_module
from telemetry.page import page_test
from telemetry.page import shared_page_state
from telemetry.page import test_expectations
from telemetry.testing import options_for_unittests
from telemetry.testing import system_stub


# pylint: disable=bad-super-call

SIMPLE_CREDENTIALS_STRING = """
{
  "test": {
    "username": "example",
    "password": "asdf"
  }
}
"""
class DummyTest(page_test.PageTest):
  def ValidateAndMeasurePage(self, *_):
    pass


def SetUpStoryRunnerArguments(options):
  parser = options.CreateParser()
  story_runner.AddCommandLineArgs(parser)
  options.MergeDefaultValues(parser.get_default_values())
  story_runner.ProcessCommandLineArgs(parser, options)

class EmptyMetadataForTest(benchmark.BenchmarkMetadata):
  def __init__(self):
    super(EmptyMetadataForTest, self).__init__('')

class StubCredentialsBackend(object):
  def __init__(self, login_return_value):
    self.did_get_login = False
    self.did_get_login_no_longer_needed = False
    self.login_return_value = login_return_value

  @property
  def credentials_type(self):
    return 'test'

  def LoginNeeded(self, *_):
    self.did_get_login = True
    return self.login_return_value

  def LoginNoLongerNeeded(self, _):
    self.did_get_login_no_longer_needed = True


def GetSuccessfulPageRuns(results):
  return [run for run in results.all_page_runs if run.ok or run.skipped]


def CaptureStderr(func, output_buffer):
  def wrapper(*args, **kwargs):
    original_stderr, sys.stderr = sys.stderr, output_buffer
    try:
      return func(*args, **kwargs)
    finally:
      sys.stderr = original_stderr
  return wrapper


# TODO: remove test cases that use real browsers and replace with a
# story_runner or shared_page_state unittest that tests the same logic.
class PageRunEndToEndTests(unittest.TestCase):
  # TODO(nduca): Move the basic "test failed, test succeeded" tests from
  # page_test_unittest to here.

  def setUp(self):
    self._story_runner_logging_stub = None
    self._formatted_exception_buffer = StringIO.StringIO()
    self._original_formatter = exception_formatter.PrintFormattedException

  def tearDown(self):
    self.RestoreExceptionFormatter()

  def CaptureFormattedException(self):
    exception_formatter.PrintFormattedException = CaptureStderr(
        exception_formatter.PrintFormattedException,
        self._formatted_exception_buffer)
    self._story_runner_logging_stub = system_stub.Override(
        story_runner, ['logging'])

  @property
  def formatted_exception(self):
    return self._formatted_exception_buffer.getvalue()

  def RestoreExceptionFormatter(self):
    exception_formatter.PrintFormattedException = self._original_formatter
    if self._story_runner_logging_stub:
      self._story_runner_logging_stub.Restore()
      self._story_runner_logging_stub = None

  def assertFormattedExceptionIsEmpty(self):
    self.longMessage = False
    self.assertEquals(
        '', self.formatted_exception,
        msg='Expected empty formatted exception: actual=%s' % '\n   > '.join(
            self.formatted_exception.split('\n')))

  def assertFormattedExceptionOnlyHas(self, expected_exception_name):
    self.longMessage = True
    actual_exception_names = re.findall(r'^Traceback.*?^(\w+)',
                                        self.formatted_exception,
                                        re.DOTALL | re.MULTILINE)
    self.assertEquals([expected_exception_name], actual_exception_names,
                      msg='Full formatted exception: %s' % '\n   > '.join(
                          self.formatted_exception.split('\n')))

  def testRaiseBrowserGoneExceptionFromRestartBrowserBeforeEachPage(self):
    self.CaptureFormattedException()
    story_set = story.StorySet()
    expectations = test_expectations.TestExpectations()
    story_set.AddStory(page_module.Page(
        'file://blank.html', story_set, base_dir=util.GetUnittestDataDir()))
    story_set.AddStory(page_module.Page(
        'file://blank.html', story_set, base_dir=util.GetUnittestDataDir()))

    class Test(page_test.PageTest):
      def __init__(self, *args):
        super(Test, self).__init__(
            *args, needs_browser_restart_after_each_page=True)
        self.run_count = 0

      def RestartBrowserBeforeEachPage(self):
        old_run_count = self.run_count
        self.run_count += 1
        if old_run_count == 0:
          raise exceptions.BrowserGoneException(None)
        return self._needs_browser_restart_after_each_page

      def ValidateAndMeasurePage(self, page, tab, results):
        pass

    options = options_for_unittests.GetCopy()
    options.output_formats = ['none']
    options.suppress_gtest_report = True
    test = Test()
    SetUpStoryRunnerArguments(options)
    results = results_options.CreateResults(EmptyMetadataForTest(), options)
    story_runner.Run(test, story_set, expectations, options, results)
    self.assertEquals(2, test.run_count)
    self.assertEquals(1, len(GetSuccessfulPageRuns(results)))
    self.assertEquals(1, len(results.failures))
    self.assertFormattedExceptionIsEmpty()

  def testNeedsBrowserRestartAfterEachPage(self):
    self.CaptureFormattedException()
    story_set = story.StorySet()
    expectations = test_expectations.TestExpectations()
    story_set.AddStory(page_module.Page(
        'file://blank.html', story_set, base_dir=util.GetUnittestDataDir()))
    story_set.AddStory(page_module.Page(
        'file://blank.html', story_set, base_dir=util.GetUnittestDataDir()))

    class Test(page_test.PageTest):
      def __init__(self, *args, **kwargs):
        super(Test, self).__init__(*args, **kwargs)
        self.browser_starts = 0

      def DidStartBrowser(self, *args):
        super(Test, self).DidStartBrowser(*args)
        self.browser_starts += 1

      def ValidateAndMeasurePage(self, page, tab, results):
        pass

    options = options_for_unittests.GetCopy()
    options.output_formats = ['none']
    options.suppress_gtest_report = True
    test = Test(needs_browser_restart_after_each_page=True)
    SetUpStoryRunnerArguments(options)
    results = results_options.CreateResults(EmptyMetadataForTest(), options)
    story_runner.Run(test, story_set, expectations, options, results)
    self.assertEquals(2, len(GetSuccessfulPageRuns(results)))
    self.assertEquals(2, test.browser_starts)
    self.assertFormattedExceptionIsEmpty()

  @decorators.Disabled('android') # https://crbug.com/444240
  def testHandlingOfCrashedTabWithExpectedFailure(self):
    self.CaptureFormattedException()
    story_set = story.StorySet()
    expectations = test_expectations.TestExpectations()
    expectations.Fail('chrome://crash')
    page1 = page_module.Page('chrome://crash', story_set)
    story_set.AddStory(page1)

    options = options_for_unittests.GetCopy()
    options.output_formats = ['none']
    options.suppress_gtest_report = True
    SetUpStoryRunnerArguments(options)
    results = results_options.CreateResults(EmptyMetadataForTest(), options)
    story_runner.Run(DummyTest(), story_set, expectations, options, results)
    self.assertEquals(1, len(GetSuccessfulPageRuns(results)))
    self.assertEquals(0, len(results.failures))
    self.assertFormattedExceptionOnlyHas('DevtoolsTargetCrashException')

  def testCredentialsWhenLoginFails(self):
    self.CaptureFormattedException()
    credentials_backend = StubCredentialsBackend(login_return_value=False)
    did_run = self.runCredentialsTest(credentials_backend)
    assert credentials_backend.did_get_login == True
    assert credentials_backend.did_get_login_no_longer_needed == False
    assert did_run == False
    self.assertFormattedExceptionIsEmpty()

  def testCredentialsWhenLoginSucceeds(self):
    credentials_backend = StubCredentialsBackend(login_return_value=True)
    did_run = self.runCredentialsTest(credentials_backend)
    assert credentials_backend.did_get_login == True
    assert credentials_backend.did_get_login_no_longer_needed == True
    assert did_run

  def runCredentialsTest(self, credentials_backend):
    story_set = story.StorySet()
    expectations = test_expectations.TestExpectations()
    did_run = [False]

    try:
      with tempfile.NamedTemporaryFile(delete=False) as f:
        page = page_module.Page(
        'file://blank.html', story_set, base_dir=util.GetUnittestDataDir(),
        credentials_path=f.name)
        page.credentials = "test"
        story_set.AddStory(page)

        f.write(SIMPLE_CREDENTIALS_STRING)

      class TestThatInstallsCredentialsBackend(page_test.PageTest):
        def __init__(self, credentials_backend):
          super(TestThatInstallsCredentialsBackend, self).__init__()
          self._credentials_backend = credentials_backend

        def DidStartBrowser(self, browser):
          browser.credentials.AddBackend(self._credentials_backend)

        def ValidateAndMeasurePage(self, *_):
          did_run[0] = True

      test = TestThatInstallsCredentialsBackend(credentials_backend)
      options = options_for_unittests.GetCopy()
      options.output_formats = ['none']
      options.suppress_gtest_report = True
      SetUpStoryRunnerArguments(options)
      results = results_options.CreateResults(EmptyMetadataForTest(), options)
      story_runner.Run(test, story_set, expectations, options, results)
    finally:
      os.remove(f.name)

    return did_run[0]

  @decorators.Disabled('chromeos')  # crbug.com/483212
  def testUserAgent(self):
    story_set = story.StorySet()
    expectations = test_expectations.TestExpectations()
    page = page_module.Page(
        'file://blank.html', story_set, base_dir=util.GetUnittestDataDir(),
        shared_page_state_class=shared_page_state.SharedTabletPageState)
    story_set.AddStory(page)

    class TestUserAgent(page_test.PageTest):
      def ValidateAndMeasurePage(self, _1, tab, _2):
        actual_user_agent = tab.EvaluateJavaScript('window.navigator.userAgent')
        expected_user_agent = user_agent.UA_TYPE_MAPPING['tablet']
        assert actual_user_agent.strip() == expected_user_agent

        # This is so we can check later that the test actually made it into this
        # function. Previously it was timing out before even getting here, which
        # should fail, but since it skipped all the asserts, it slipped by.
        self.hasRun = True # pylint: disable=W0201

    test = TestUserAgent()
    options = options_for_unittests.GetCopy()
    options.output_formats = ['none']
    options.suppress_gtest_report = True
    SetUpStoryRunnerArguments(options)
    results = results_options.CreateResults(EmptyMetadataForTest(), options)
    story_runner.Run(test, story_set, expectations, options, results)

    self.assertTrue(hasattr(test, 'hasRun') and test.hasRun)

  # Ensure that story_runner forces exactly 1 tab before running a page.
  @decorators.Enabled('has tabs')
  def testOneTab(self):
    story_set = story.StorySet()
    expectations = test_expectations.TestExpectations()
    page = page_module.Page(
        'file://blank.html', story_set, base_dir=util.GetUnittestDataDir())
    story_set.AddStory(page)

    class TestOneTab(page_test.PageTest):
      def DidStartBrowser(self, browser):
        browser.tabs.New()

      def ValidateAndMeasurePage(self, _, tab, __):
        assert len(tab.browser.tabs) == 1

    test = TestOneTab()
    options = options_for_unittests.GetCopy()
    options.output_formats = ['none']
    options.suppress_gtest_report = True
    SetUpStoryRunnerArguments(options)
    results = results_options.CreateResults(EmptyMetadataForTest(), options)
    story_runner.Run(test, story_set, expectations, options, results)

  # Ensure that story_runner allows >1 tab for multi-tab test.
  @decorators.Enabled('has tabs')
  def testMultipleTabsOkayForMultiTabTest(self):
    story_set = story.StorySet()
    expectations = test_expectations.TestExpectations()
    page = page_module.Page(
        'file://blank.html', story_set, base_dir=util.GetUnittestDataDir())
    story_set.AddStory(page)

    class TestMultiTabs(page_test.PageTest):
      def TabForPage(self, _, browser):
        return browser.tabs.New()

      def ValidateAndMeasurePage(self, _, tab, __):
        assert len(tab.browser.tabs) == 2

    test = TestMultiTabs()
    options = options_for_unittests.GetCopy()
    options.output_formats = ['none']
    options.suppress_gtest_report = True
    SetUpStoryRunnerArguments(options)
    results = results_options.CreateResults(EmptyMetadataForTest(), options)
    story_runner.Run(test, story_set, expectations, options, results)

  # Ensure that story_runner allows the test to customize the browser
  # before it launches.
  def testBrowserBeforeLaunch(self):
    story_set = story.StorySet()
    expectations = test_expectations.TestExpectations()
    page = page_module.Page(
        'file://blank.html', story_set, base_dir=util.GetUnittestDataDir())
    story_set.AddStory(page)

    class TestBeforeLaunch(page_test.PageTest):
      def __init__(self):
        super(TestBeforeLaunch, self).__init__()
        self._did_call_will_start = False
        self._did_call_did_start = False

      def WillStartBrowser(self, platform):
        self._did_call_will_start = True
        # TODO(simonjam): Test that the profile is available.

      def DidStartBrowser(self, browser):
        assert self._did_call_will_start
        self._did_call_did_start = True

      def ValidateAndMeasurePage(self, *_):
        assert self._did_call_did_start

    test = TestBeforeLaunch()
    options = options_for_unittests.GetCopy()
    options.output_formats = ['none']
    options.suppress_gtest_report = True
    SetUpStoryRunnerArguments(options)
    results = results_options.CreateResults(EmptyMetadataForTest(), options)
    story_runner.Run(test, story_set, expectations, options, results)

  def testRunPageWithStartupUrl(self):
    story_set = story.StorySet()
    expectations = test_expectations.TestExpectations()
    expectations = test_expectations.TestExpectations()
    page = page_module.Page(
        'file://blank.html', story_set, base_dir=util.GetUnittestDataDir(),
        startup_url='about:blank')
    story_set.AddStory(page)

    class Measurement(page_test.PageTest):
      def __init__(self):
        super(Measurement, self).__init__()
        self.browser_restarted = False

      def CustomizeBrowserOptionsForSinglePage(self, story_set, options):
        self.browser_restarted = True
        super(Measurement, self).CustomizeBrowserOptionsForSinglePage(story_set,
                                                                      options)
      def ValidateAndMeasurePage(self, page, tab, results):
        pass

    options = options_for_unittests.GetCopy()
    options.page_repeat = 2
    options.output_formats = ['none']
    options.suppress_gtest_report = True
    if not browser_finder.FindBrowser(options):
      return
    test = Measurement()
    SetUpStoryRunnerArguments(options)
    results = results_options.CreateResults(EmptyMetadataForTest(), options)
    story_runner.Run(test, story_set, expectations, options, results)
    self.assertEquals('about:blank', options.browser_options.startup_url)
    self.assertTrue(test.browser_restarted)

  # Ensure that story_runner calls cleanUp when a page run fails.
  def testCleanUpPage(self):
    story_set = story.StorySet()
    expectations = test_expectations.TestExpectations()
    page = page_module.Page(
        'file://blank.html', story_set, base_dir=util.GetUnittestDataDir())
    story_set.AddStory(page)

    class Test(page_test.PageTest):
      def __init__(self):
        super(Test, self).__init__()
        self.did_call_clean_up = False

      def ValidateAndMeasurePage(self, *_):
        raise page_test.Failure

      def CleanUpAfterPage(self, page, tab):
        self.did_call_clean_up = True


    test = Test()
    options = options_for_unittests.GetCopy()
    options.output_formats = ['none']
    options.suppress_gtest_report = True
    SetUpStoryRunnerArguments(options)
    results = results_options.CreateResults(EmptyMetadataForTest(), options)
    story_runner.Run(test, story_set, expectations, options, results)
    assert test.did_call_clean_up

  # Ensure skipping the test if shared state cannot be run on the browser.
  def testSharedPageStateCannotRunOnBrowser(self):
    story_set = story.StorySet()

    class UnrunnableSharedState(shared_page_state.SharedPageState):
      def CanRunOnBrowser(self, _):
        return False
      def ValidateAndMeasurePage(self, _):
        pass

    story_set.AddStory(page_module.Page(
        url='file://blank.html', page_set=story_set,
        base_dir=util.GetUnittestDataDir(),
        shared_page_state_class=UnrunnableSharedState))
    expectations = test_expectations.TestExpectations()

    class Test(page_test.PageTest):
      def __init__(self, *args, **kwargs):
        super(Test, self).__init__(*args, **kwargs)
        self.will_navigate_to_page_called = False

      def ValidateAndMeasurePage(self, *_args):
        raise Exception('Exception should not be thrown')

      def WillNavigateToPage(self, _1, _2):
        self.will_navigate_to_page_called = True

    test = Test()
    options = options_for_unittests.GetCopy()
    options.output_formats = ['none']
    options.suppress_gtest_report = True
    SetUpStoryRunnerArguments(options)
    results = results_options.CreateResults(EmptyMetadataForTest(), options)
    story_runner.Run(test, story_set, expectations, options, results)
    self.assertFalse(test.will_navigate_to_page_called)
    self.assertEquals(1, len(GetSuccessfulPageRuns(results)))
    self.assertEquals(1, len(results.skipped_values))
    self.assertEquals(0, len(results.failures))

  def testRunPageWithProfilingFlag(self):
    story_set = story.StorySet()
    expectations = test_expectations.TestExpectations()
    story_set.AddStory(page_module.Page(
        'file://blank.html', story_set, base_dir=util.GetUnittestDataDir()))

    class Measurement(page_test.PageTest):
      def ValidateAndMeasurePage(self, page, tab, results):
        pass

    options = options_for_unittests.GetCopy()
    options.output_formats = ['none']
    options.suppress_gtest_report = True
    options.reset_results = None
    options.upload_results = None
    options.results_label = None
    options.output_dir = tempfile.mkdtemp()
    options.profiler = 'trace'
    try:
      SetUpStoryRunnerArguments(options)
      results = results_options.CreateResults(EmptyMetadataForTest(), options)
      story_runner.Run(Measurement(), story_set, expectations, options, results)
      self.assertEquals(1, len(GetSuccessfulPageRuns(results)))
      self.assertEquals(0, len(results.failures))
      self.assertEquals(0, len(results.all_page_specific_values))
      self.assertTrue(os.path.isfile(
          os.path.join(options.output_dir, 'blank_html.zip')))
    finally:
      shutil.rmtree(options.output_dir)

  def _RunPageTestThatRaisesAppCrashException(self, test, max_failures):
    class TestPage(page_module.Page):
      def RunNavigateSteps(self, _):
        raise exceptions.AppCrashException

    story_set = story.StorySet()
    for _ in range(5):
      story_set.AddStory(
          TestPage('file://blank.html', story_set,
                   base_dir=util.GetUnittestDataDir()))
    expectations = test_expectations.TestExpectations()
    options = options_for_unittests.GetCopy()
    options.output_formats = ['none']
    options.suppress_gtest_report = True
    SetUpStoryRunnerArguments(options)
    results = results_options.CreateResults(EmptyMetadataForTest(), options)
    story_runner.Run(test, story_set, expectations, options, results,
                          max_failures=max_failures)
    return results

  def testSingleTabMeansCrashWillCauseFailureValue(self):
    self.CaptureFormattedException()
    class SingleTabTest(page_test.PageTest):
      # Test is not multi-tab because it does not override TabForPage.
      def ValidateAndMeasurePage(self, *_):
        pass

    test = SingleTabTest()
    results = self._RunPageTestThatRaisesAppCrashException(test, max_failures=1)
    self.assertEquals([], GetSuccessfulPageRuns(results))
    self.assertEquals(2, len(results.failures))  # max_failures + 1
    self.assertFormattedExceptionIsEmpty()

  @decorators.Enabled('has tabs')
  def testMultipleTabsMeansCrashRaises(self):
    self.CaptureFormattedException()
    class MultipleTabsTest(page_test.PageTest):
      # Test *is* multi-tab because it overrides TabForPage.
      def TabForPage(self, page, browser):
        return browser.tabs.New()
      def ValidateAndMeasurePage(self, *_):
        pass

    test = MultipleTabsTest()
    with self.assertRaises(page_test.MultiTabTestAppCrashError):
      self._RunPageTestThatRaisesAppCrashException(test, max_failures=1)
    self.assertFormattedExceptionOnlyHas('AppCrashException')

  def testWebPageReplay(self):
    story_set = example_domain.ExampleDomainPageSet()
    expectations = test_expectations.TestExpectations()
    body = []
    class TestWpr(page_test.PageTest):
      def ValidateAndMeasurePage(self, _, tab, __):
        body.append(tab.EvaluateJavaScript('document.body.innerText'))
    test = TestWpr()
    options = options_for_unittests.GetCopy()
    options.output_formats = ['none']
    options.suppress_gtest_report = True
    SetUpStoryRunnerArguments(options)
    results = results_options.CreateResults(EmptyMetadataForTest(), options)

    story_runner.Run(test, story_set, expectations, options, results)

    self.longMessage = True
    self.assertIn('Example Domain', body[0],
                  msg='URL: %s' % story_set.stories[0].url)
    self.assertIn('Example Domain', body[1],
                  msg='URL: %s' % story_set.stories[1].url)

    self.assertEquals(2, len(GetSuccessfulPageRuns(results)))
    self.assertEquals(0, len(results.failures))

