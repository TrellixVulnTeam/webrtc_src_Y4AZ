# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This module is not automatically loaded by the `cros` helper.  The filename
# would need a "cros_" prefix to make that happen.  It lives here so that it
# is alongside the cros_lint.py file.
#
# For msg namespaces, the 9xxx should generally be reserved for our own use.

"""Additional lint modules loaded by pylint.

This is loaded by pylint directly via its pylintrc file:
  load-plugins=chromite.cli.cros.lint

Then pylint will import the register function and call it.  So we can have
as many/few checkers as we want in this one module.
"""

from __future__ import print_function

import os
import sys

from pylint.checkers import BaseChecker
from pylint.interfaces import IAstroidChecker


# pylint: disable=too-few-public-methods


class DocStringChecker(BaseChecker):
  """PyLint AST based checker to verify PEP 257 compliance

  See our style guide for more info:
  http://dev.chromium.org/chromium-os/python-style-guidelines#TOC-Describing-arguments-in-docstrings

  """
  # TODO: See about merging with the pep257 project:
  # https://github.com/GreenSteam/pep257

  __implements__ = IAstroidChecker

  # pylint: disable=class-missing-docstring,multiple-statements
  class _MessageCP001(object): pass
  class _MessageCP002(object): pass
  class _MessageCP003(object): pass
  class _MessageCP004(object): pass
  class _MessageCP005(object): pass
  class _MessageCP006(object): pass
  class _MessageCP007(object): pass
  class _MessageCP008(object): pass
  class _MessageCP009(object): pass
  class _MessageCP010(object): pass
  class _MessageCP011(object): pass
  class _MessageCP012(object): pass
  class _MessageCP013(object): pass
  class _MessageCP014(object): pass
  class _MessageCP015(object): pass
  # pylint: enable=class-missing-docstring,multiple-statements

  name = 'doc_string_checker'
  priority = -1
  MSG_ARGS = 'offset:%(offset)i: {%(line)s}'
  msgs = {
      'C9001': ('Modules should have docstrings (even a one liner)',
                ('module-missing-docstring'), _MessageCP001),
      'C9002': ('Classes should have docstrings (even a one liner)',
                ('class-missing-docstring'), _MessageCP002),
      'C9003': ('Trailing whitespace in docstring'
                ': %s' % MSG_ARGS,
                ('docstring-trailing-whitespace'), _MessageCP003),
      'C9004': ('Leading whitespace in docstring (excess or missing)'
                ': %s' % MSG_ARGS,
                ('docstring-leading-whitespace'), _MessageCP004),
      'C9005': ('Closing triple quotes should not be cuddled',
                ('docstring-cuddled-quotes'), _MessageCP005),
      'C9006': ('Section names should be preceded by one blank line'
                ': %s' % MSG_ARGS,
                ('docstring-section-newline'), _MessageCP006),
      'C9007': ('Section names should be "Args:", "Returns:", "Yields:", '
                'and "Raises:": %s' % MSG_ARGS,
                ('docstring-section-name'), _MessageCP007),
      'C9008': ('Sections should be in the order: Args, Returns/Yields, Raises',
                ('docstring-section-order'), _MessageCP008),
      'C9009': ('First line should be a short summary',
                ('docstring-first-line'), _MessageCP009),
      'C9010': ('Not all args mentioned in doc string: |%(arg)s|',
                ('docstring-missing-args'), _MessageCP010),
      'C9011': ('Variable args/keywords are named *args/**kwargs, not %(arg)s',
                ('docstring-misnamed-args'), _MessageCP011),
      'C9012': ('Incorrectly formatted Args section: %(arg)s',
                ('docstring-arg-spacing'), _MessageCP012),
      'C9013': ('Too many blank lines in a row: %s' % MSG_ARGS,
                ('docstring-too-many-newlines'), _MessageCP013),
      'C9014': ('Second line should be blank',
                ('docstring-second-line-blank'), _MessageCP014),
      'C9015': ('Section indentation is incorrect: %s' % MSG_ARGS,
                ('docstring-section-indent'), _MessageCP015),
  }
  options = ()

  # TODO: Should we enforce Examples?
  VALID_SECTIONS = ('Args', 'Returns', 'Yields', 'Raises',)

  def visit_function(self, node):
    """Verify function docstrings"""
    if node.doc:
      lines = node.doc.split('\n')
      self._check_common(node, lines)
      self._check_last_line_function(node, lines)
      self._check_section_lines(node, lines)
      self._check_all_args_in_doc(node, lines)
      self._check_func_signature(node)
    else:
      # This is what C0111 already does for us, so ignore.
      pass

  def visit_module(self, node):
    """Verify module docstrings"""
    if node.doc:
      self._check_common(node)
    else:
      # Ignore stub __init__.py files.
      if os.path.basename(node.file) == '__init__.py':
        return
      self.add_message('C9001', node=node)

  def visit_class(self, node):
    """Verify class docstrings"""
    if node.doc:
      self._check_common(node)
    else:
      self.add_message('C9002', node=node, line=node.fromlineno)

  def _check_common(self, node, lines=None):
    """Common checks we enforce on all docstrings"""
    if lines is None:
      lines = node.doc.split('\n')

    funcs = (
        self._check_first_line,
        self._check_second_line_blank,
        self._check_whitespace,
        self._check_last_line,
    )
    for f in funcs:
      f(node, lines)

  def _check_first_line(self, node, lines):
    """Make sure first line is a short summary by itself"""
    if lines[0] == '':
      self.add_message('C9009', node=node, line=node.fromlineno)

  def _check_second_line_blank(self, node, lines):
    """Make sure the second line is blank"""
    if len(lines) > 1 and lines[1] != '':
      self.add_message('C9014', node=node, line=node.fromlineno)

  def _check_whitespace(self, node, lines):
    """Verify whitespace is sane"""
    # Make sure first line doesn't have leading whitespace.
    if lines[0].lstrip() != lines[0]:
      margs = {'offset': 0, 'line': lines[0]}
      self.add_message('C9004', node=node, line=node.fromlineno, args=margs)

    # Verify no trailing whitespace.
    # We skip the last line since it's supposed to be pure whitespace.
    #
    # Also check for multiple blank lines in a row.
    last_blank = False
    for i, l in enumerate(lines[:-1]):
      margs = {'offset': i, 'line': l}

      if l.rstrip() != l:
        self.add_message('C9003', node=node, line=node.fromlineno, args=margs)

      curr_blank = l == ''
      if last_blank and curr_blank:
        self.add_message('C9013', node=node, line=node.fromlineno, args=margs)
      last_blank = curr_blank

    # Now specially handle the last line.
    l = lines[-1]
    if l.strip() != '' and l.rstrip() != l:
      margs = {'offset': len(lines), 'line': l}
      self.add_message('C9003', node=node, line=node.fromlineno, args=margs)

  def _check_last_line(self, node, lines):
    """Make sure last line is all by itself"""
    if len(lines) > 1:
      if lines[-1].strip() != '':
        self.add_message('C9005', node=node, line=node.fromlineno)

  def _check_last_line_function(self, node, lines):
    """Make sure last line is indented"""
    if len(lines) > 1:
      # The -1 line holds the """ itself and that should be indented.
      if lines[-1] == '':
        margs = {'offset': len(lines) - 1, 'line': lines[-1]}
        self.add_message('C9005', node=node, line=node.fromlineno, args=margs)

      # The last line should not be blank.
      if lines[-2] == '':
        margs = {'offset': len(lines) - 2, 'line': lines[-2]}
        self.add_message('C9003', node=node, line=node.fromlineno, args=margs)

  def _check_section_lines(self, node, lines):
    """Verify each section (Args/Returns/Yields/Raises) is sane"""
    lineno_sections = [-1] * len(self.VALID_SECTIONS)
    invalid_sections = (
        # Handle common misnamings.
        'arg', 'argument', 'arguments',
        'ret', 'rets', 'return',
        'yield', 'yeild', 'yeilds',
        'raise', 'throw', 'throws',
    )

    last = lines[0].strip()
    for i, line in enumerate(lines[1:]):
      margs = {'offset': i + 1, 'line': line}
      l = line.strip()

      # Catch semi-common javadoc style.
      if l.startswith('@param') or l.startswith('@return'):
        self.add_message('C9007', node=node, line=node.fromlineno, args=margs)

      # See if we can detect incorrect behavior.
      section = l.split(':', 1)[0]
      if section in self.VALID_SECTIONS or section.lower() in invalid_sections:
        # Make sure it has some number of leading whitespace.
        if not line.startswith(' '):
          self.add_message('C9004', node=node, line=node.fromlineno, args=margs)

        # Make sure it has a single trailing colon.
        if l != '%s:' % section:
          self.add_message('C9007', node=node, line=node.fromlineno, args=margs)

        # Make sure it's valid.
        if section.lower() in invalid_sections:
          self.add_message('C9007', node=node, line=node.fromlineno, args=margs)
        else:
          # Gather the order of the sections.
          lineno_sections[self.VALID_SECTIONS.index(section)] = i

        # Verify blank line before it.
        if last != '':
          self.add_message('C9006', node=node, line=node.fromlineno, args=margs)

      last = l

    # Make sure the sections are in the right order.
    valid_lineno = lambda x: x >= 0
    lineno_sections = filter(valid_lineno, lineno_sections)
    if lineno_sections != sorted(lineno_sections):
      self.add_message('C9008', node=node, line=node.fromlineno)

    # Check the indentation level on all the sections.
    # The -1 line holds the trailing """ itself and that should be indented to
    # the correct number of spaces.  All checks below are relative to this.  If
    # it is off, then these checks might report weird errors, but that's ok as
    # ultimately the docstring is still wrong :).
    indent_len = len(lines[-1])
    for lineno in lineno_sections:
      # First the section header (e.g. Args:).
      lineno += 1
      line = lines[lineno]
      if len(line) - len(line.lstrip(' ')) != indent_len:
        margs = {'offset': lineno, 'line': line}
        self.add_message('C9015', node=node, line=node.fromlineno, args=margs)

  def _check_all_args_in_doc(self, node, lines):
    """All function arguments are mentioned in doc"""
    if not hasattr(node, 'argnames'):
      return

    # Locate the start of the args section.
    arg_lines = []
    for l in lines:
      if arg_lines:
        if l.strip() in [''] + ['%s:' % x for x in self.VALID_SECTIONS]:
          break
      elif l.strip() != 'Args:':
        continue
      arg_lines.append(l)
    else:
      # If they don't have an Args section, then give it a pass.
      return

    # Now verify all args exist.
    # TODO: Should we verify arg order matches doc order ?
    # TODO: Should we check indentation of wrapped docs ?
    missing_args = []
    for arg in node.args.args:
      # Ignore class related args.
      if arg.name in ('cls', 'self'):
        continue
      # Ignore ignored args.
      if arg.name.startswith('_'):
        continue

      for l in arg_lines:
        aline = l.lstrip()
        if aline.startswith('%s:' % arg.name):
          amsg = aline[len(arg.name) + 1:]
          if len(amsg) and len(amsg) - len(amsg.lstrip()) != 1:
            margs = {'arg': l}
            self.add_message('C9012', node=node, line=node.fromlineno,
                             args=margs)
          break
      else:
        missing_args.append(arg.name)

    if missing_args:
      margs = {'arg': '|, |'.join(missing_args)}
      self.add_message('C9010', node=node, line=node.fromlineno, args=margs)

  def _check_func_signature(self, node):
    """Require *args to be named args, and **kwargs kwargs"""
    vararg = node.args.vararg
    if vararg and vararg != 'args' and vararg != '_args':
      margs = {'arg': vararg}
      self.add_message('C9011', node=node, line=node.fromlineno, args=margs)

    kwarg = node.args.kwarg
    if kwarg and kwarg != 'kwargs' and kwarg != '_kwargs':
      margs = {'arg': kwarg}
      self.add_message('C9011', node=node, line=node.fromlineno, args=margs)


class Py3kCompatChecker(BaseChecker):
  """Make sure we enforce py3k compatible features"""

  __implements__ = IAstroidChecker

  # pylint: disable=class-missing-docstring,multiple-statements
  class _MessageR9100(object): pass
  # pylint: enable=class-missing-docstring,multiple-statements

  name = 'py3k_compat_checker'
  priority = -1
  MSG_ARGS = 'offset:%(offset)i: {%(line)s}'
  msgs = {
      'R9100': ('Missing "from __future__ import print_function" line',
                ('missing-print-function'), _MessageR9100),
  }
  options = ()

  def __init__(self, *args, **kwargs):
    super(Py3kCompatChecker, self).__init__(*args, **kwargs)
    self.seen_print_func = False
    self.saw_imports = False

  def close(self):
    """Called when done processing module"""
    if not self.seen_print_func:
      # Do not warn if moduler doesn't import anything at all (like
      # empty __init__.py files).
      if self.saw_imports:
        self.add_message('R9100')

  def _check_print_function(self, node):
    """Verify print_function is imported"""
    if node.modname == '__future__':
      for name, _ in node.names:
        if name == 'print_function':
          self.seen_print_func = True

  def visit_from(self, node):
    """Process 'from' statements"""
    self.saw_imports = True
    self._check_print_function(node)

  def visit_import(self, _node):
    """Process 'import' statements"""
    self.saw_imports = True


class SourceChecker(BaseChecker):
  """Make sure we enforce rules on the source."""

  __implements__ = IAstroidChecker

  # pylint: disable=class-missing-docstring,multiple-statements
  class _MessageR9200(object): pass
  class _MessageR9201(object): pass
  class _MessageR9202(object): pass
  # pylint: enable=class-missing-docstring,multiple-statements

  name = 'source_checker'
  priority = -1
  MSG_ARGS = 'offset:%(offset)i: {%(line)s}'
  msgs = {
      'R9200': ('Shebang should be #!/usr/bin/python2 or #!/usr/bin/python3',
                ('bad-shebang'), _MessageR9200),
      'R9201': ('Shebang is missing, but file is executable',
                ('missing-shebang'), _MessageR9201),
      'R9202': ('Shebang is set, but file is not executable',
                ('spurious-shebang'), _MessageR9202),
  }
  options = ()

  def visit_module(self, node):
    """Called when the whole file has been read"""
    stream = node.file_stream
    stream.seek(0)
    self._check_shebang(node, stream)

  def _check_shebang(self, _node, stream):
    """Verify the shebang is version specific"""
    st = os.fstat(stream.fileno())
    mode = st.st_mode
    executable = bool(mode & 0o0111)

    shebang = stream.readline()
    if shebang[0:2] != '#!':
      if executable:
        self.add_message('R9201')
      return
    elif not executable:
      self.add_message('R9202')

    parts = shebang.split()
    if parts[0] not in ('#!/usr/bin/python2', '#!/usr/bin/python3'):
      self.add_message('R9200')


class ChromiteLoggingChecker(BaseChecker):
  """Make sure we enforce rules on importing logging."""

  __implements__ = IAstroidChecker

  # pylint: disable=class-missing-docstring,multiple-statements
  class _MessageR9301(object): pass
  # pylint: enable=class-missing-docstring,multiple-statements

  name = 'chromite_logging_checker'
  priority = -1
  MSG_ARGS = 'offset:%(offset)i: {%(line)s}'
  msgs = {
      'R9301': ('logging is deprecated. Use "from chromite.lib import '
                'cros_logging as logging" to import chromite/lib/cros_logging',
                ('cros-logging-import'), _MessageR9301),
  }
  options = ()
  # This checker is disabled by default because we only want to disallow "import
  # logging" in chromite and not in other places cros lint is used. To enable
  # this checker, modify the pylintrc file.
  enabled = False

  def visit_import(self, node):
    """Called when node is an import statement."""
    for name, _ in node.names:
      if name == 'logging':
        self.add_message('R9301', line=node.lineno)


def register(linter):
  """pylint will call this func to register all our checkers"""
  # Walk all the classes in this module and register ours.
  this_module = sys.modules[__name__]
  for member in dir(this_module):
    if (not member.endswith('Checker') or
        member in ('BaseChecker', 'IAstroidChecker')):
      continue
    cls = getattr(this_module, member)
    linter.register_checker(cls(linter))
