# Copyright 2020 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For further info, check https://github.com/canonical/charmcraft

import argparse
import io
import pathlib
import textwrap
from unittest.mock import patch

from charmcraft import __version__, logsetup
from charmcraft.main import Dispatcher, main
from charmcraft.cmdbase import BaseCommand, CommandError
from tests.factory import create_command

import pytest


# --- Tests for the CustomArgumentParser


def get_generated_help(groups):
    """Helper to use the dispatcher to make the custom arg parser to generate special help."""
    dispatcher = Dispatcher([], groups)
    with patch.object(argparse.ArgumentParser, 'format_help', str):
        generated_help = dispatcher.main_parser.format_help()
    return generated_help


def test_customhelp_simplest():
    """Simplest situation: one command in (of course) one group."""
    groups = [
        ('test-group', "simple stuff (test)", [create_command('cmd-name', 'cmd help blah')]),
    ]
    generated_help = get_generated_help(groups)
    expected_help = """
        commands:

            simple stuff (test):
                cmd-name   cmd help blah
    """
    assert generated_help == textwrap.dedent(expected_help)


def test_customhelp_onegroup_severalcommands():
    """Multiple commands in the same group.

    Note that commands are ordered.
    """
    groups = [
        ('test-group', 'whatever title', [
            create_command('name1', 'cmd help 1'),
            create_command('zz-name2', 'cmd help 2'),
            create_command('other-name', 'super long help'),
        ]),
    ]
    generated_help = get_generated_help(groups)
    expected_help = """
        commands:

            whatever title:
                name1        cmd help 1
                other-name   super long help
                zz-name2     cmd help 2
    """
    assert generated_help == textwrap.dedent(expected_help)


def test_customhelp_several_simple_groups():
    """Multiple groups (each one simple).

    Note that the groups order are respected.
    """
    groups = [
        ('test-group-1', 'whatever title', [
            create_command('cmd-name', 'cmd help 1'),
        ]),
        ('test-group-2', 'other title', [
            create_command('cmd-longer-name', 'cmd help 2'),
        ]),
    ]
    generated_help = get_generated_help(groups)
    expected_help = """
        commands:

            whatever title:
                cmd-name          cmd help 1

            other title:
                cmd-longer-name   cmd help 2
    """
    assert generated_help == textwrap.dedent(expected_help)


def test_customhelp_combined():
    """Several commands in several groups."""
    groups = [
        ('test-group-1', 'this is very long title but we do not prejudge much', [
            create_command('1-name', 'cmd help 1'),
        ]),
        ('test-group-2', 'short', [
            create_command('cmd-B1', 'cmd help which is very long but whatever'),
            create_command('cmd-B2', 'cmd help'),
            create_command('cmd-longer-name', 'cmd help'),
        ]),
    ]
    generated_help = get_generated_help(groups)
    expected_help = """
        commands:

            this is very long title but we do not prejudge much:
                1-name            cmd help 1

            short:
                cmd-B1            cmd help which is very long but whatever
                cmd-B2            cmd help
                cmd-longer-name   cmd help
    """
    assert generated_help == textwrap.dedent(expected_help)


# --- Tests for the Dispatcher


def test_dispatcher_no_command():
    """When no command is given we should get the "usage" help."""
    groups = [('test-group', 'title', [create_command('cmd-name', 'cmd help')])]
    dispatcher = Dispatcher([], groups)
    fake_stdout = io.StringIO()
    with patch('sys.stdout', fake_stdout):
        retcode = dispatcher.run()
    assert retcode == 1
    assert "usage: charmcraft" in fake_stdout.getvalue()


def test_dispatcher_command_execution_ok():
    """Command execution depends of the indicated name in command line, return code ok."""
    class MyCommandControl(BaseCommand):
        help_msg = "some help"

        def __init__(self, group):
            super().__init__(group)
            self.executed = None

        def run(self, parsed_args):
            self.executed = parsed_args

    class MyCommand1(MyCommandControl):
        name = 'name1'

    class MyCommand2(MyCommandControl):
        name = 'name2'

    groups = [('test-group', 'title', [MyCommand1, MyCommand2])]
    dispatcher = Dispatcher(['name2'], groups)
    dispatcher.run()
    assert dispatcher.commands['name1'].executed is None
    assert isinstance(dispatcher.commands['name2'].executed, argparse.Namespace)


def test_dispatcher_command_execution_crash():
    """Command crashing doesn't pass through, we inform nicely"""
    class MyCommand(BaseCommand):
        help_msg = "some help"
        name = 'cmdname'

        def run(self, parsed_args):
            raise ValueError()

    groups = [('test-group', 'title', [MyCommand])]
    dispatcher = Dispatcher(['cmdname'], groups)
    with pytest.raises(ValueError):
        dispatcher.run()


@pytest.mark.parametrize("options", [
    ['--verbose'],
    ['-v'],
    ['somecommand', '--verbose'],
    ['somecommand', '-v'],
    ['-v', 'somecommand'],
    ['--verbose', 'somecommand'],
])
def test_dispatcher_generic_setup_verbose(options):
    """Generic parameter handling for verbose log setup, directly or after the command."""
    cmd = create_command('somecommand')
    groups = [('test-group', 'title', [cmd])]
    dispatcher = Dispatcher(options, groups)
    logsetup.message_handler.mode = None
    dispatcher.run()
    assert logsetup.message_handler.mode == logsetup.message_handler.VERBOSE


@pytest.mark.parametrize("options", [
    ['--quiet'],
    ['-q'],
    ['somecommand', '--quiet'],
    ['somecommand', '-q'],
    ['-q', 'somecommand'],
    ['--quiet', 'somecommand'],
])
def test_dispatcher_generic_setup_quiet(options):
    """Generic parameter handling for quiet log setup, directly or after the command."""
    cmd = create_command('somecommand')
    groups = [('test-group', 'title', [cmd])]
    dispatcher = Dispatcher(options, groups)
    logsetup.message_handler.mode = None
    dispatcher.run()
    assert logsetup.message_handler.mode == logsetup.message_handler.QUIET


@pytest.mark.parametrize("options", [
    ['--quiet', '--verbose'],
    ['---v', '-q'],
    # XXX Facundo 2020-08-25: we need to do this check when we escape out of argparsing parsing
    # for global options and commands, as argparse doesn't support mutex options between parsers
    # Related issue: https://github.com/canonical/charmcraft/issues/138
    # ['--verbose', 'somecommand', '--quiet'],
    # ['-q', 'somecommand', '-v'],
])
def test_dispatcher_generic_setup_mutually_exclusive(options):
    """Disallow mutually exclusive generic options."""
    cmd = create_command('somecommand')
    groups = [('test-group', 'title', [cmd])]
    # test the system exit, which is done automatically by argparse
    with pytest.raises(SystemExit) as cm:
        Dispatcher(options, groups)
    assert cm.value.code == 2


def test_dispatcher_load_commands_ok():
    """Correct command loading."""
    cmd0, cmd1, cmd2 = [create_command('cmd-name-{}'.format(n), 'cmd help') for n in range(3)]
    groups = [
        ('test-group-A', 'whatever title', [cmd0]),
        ('test-group-B', 'other title', [cmd1, cmd2]),
    ]
    dispatcher = Dispatcher([], groups)
    assert len(dispatcher.commands) == 3
    for cmd, group in [(cmd0, 'test-group-A'), (cmd1, 'test-group-B'), (cmd2, 'test-group-B')]:
        expected_cmd = dispatcher.commands[cmd.name]
        assert isinstance(expected_cmd, BaseCommand)
        assert expected_cmd.group == group


def test_dispatcher_load_commands_repeated():
    """Error while loading commands with repeated name."""
    class Foo(BaseCommand):
        help_msg = "some help"
        name = 'repeated'

    class Bar(BaseCommand):
        help_msg = "some help"
        name = 'cool'

    class Baz(BaseCommand):
        help_msg = "some help"
        name = 'repeated'

    groups = [
        ('test-group-1', 'whatever title', [Foo, Bar]),
        ('test-group-2', 'other title', [Baz]),
    ]
    expected_msg = "Multiple commands with same name: (Foo|Baz) and (Baz|Foo)"
    with pytest.raises(RuntimeError, match=expected_msg):
        Dispatcher([], groups)


# --- Tests for the main entry point

# In all the test methods below we patch Dispatcher.run so we don't really exercise any
# command machinery, even if we call to main using a real command (which is to just
# make argument parsing system happy).


def test_main_ok():
    """Work ended ok: message handler notified properly, return code in 0."""
    with patch.object(logsetup, 'message_handler') as mh_mock:
        with patch('charmcraft.main.Dispatcher.run') as d_mock:
            d_mock.return_value = None
            retcode = main(['charmcraft', 'version'])

    assert retcode == 0
    assert mh_mock.ended_ok.called_once()


def test_main_no_args():
    """The setup.py entry_point function needs to work with no arguments."""
    with patch('sys.argv', ['charmcraft']):
        with patch.object(logsetup, 'message_handler') as mh_mock:
            with patch('charmcraft.main.Dispatcher.run') as d_mock:
                d_mock.side_effect = CommandError('boom', retcode=42)
                retcode = main()

    assert retcode == 42
    assert mh_mock.ended_ok.called_once()


def test_main_controlled_error():
    """Work raised CommandError: message handler notified properly, use indicated return code."""
    simulated_exception = CommandError('boom', retcode=33)
    with patch.object(logsetup, 'message_handler') as mh_mock:
        with patch('charmcraft.main.Dispatcher.run') as d_mock:
            d_mock.side_effect = simulated_exception
            retcode = main(['charmcraft', 'version'])

    assert retcode == 33
    assert mh_mock.ended_cmderror.called_once_with(simulated_exception)


def test_main_crash():
    """Work crashed: message handler notified properly, return code in 1."""
    simulated_exception = ValueError('boom')
    with patch.object(logsetup, 'message_handler') as mh_mock:
        with patch('charmcraft.main.Dispatcher.run') as d_mock:
            d_mock.side_effect = simulated_exception
            retcode = main(['charmcraft', 'version'])

    assert retcode == 1
    assert mh_mock.ended_crash.called_once_with(simulated_exception)


def test_main_interrupted():
    """Work interrupted: message handler notified properly, return code in 1."""
    with patch.object(logsetup, 'message_handler') as mh_mock:
        with patch('charmcraft.main.Dispatcher.run') as d_mock:
            d_mock.side_effect = KeyboardInterrupt
            retcode = main(['charmcraft', 'version'])

    assert retcode == 1
    assert mh_mock.ended_interrupt.called_once()


# --- Tests for the bootstrap version message


def test_initmsg_default():
    """Without any option, the init msg only goes to disk."""
    cmd = create_command('somecommand')
    fake_stream = io.StringIO()
    with patch('charmcraft.main.COMMAND_GROUPS', [('test-group', 'whatever title', [cmd])]):
        with patch.object(logsetup.message_handler, 'ended_ok') as ended_ok_mock:
            with patch.object(logsetup.message_handler._stderr_handler, 'stream', fake_stream):
                main(['charmcraft', 'somecommand'])

    # get the logfile first line before removing it
    ended_ok_mock.assert_called_once_with()
    logged_to_file = pathlib.Path(logsetup.message_handler._log_filepath).read_text()
    file_first_line = logged_to_file.split('\n')[0]
    logsetup.message_handler.ended_ok()

    # get the terminal first line
    captured = fake_stream.getvalue()
    terminal_first_line = captured.split('\n')[0]

    expected = "Starting charmcraft version " + __version__
    assert expected in file_first_line
    assert expected not in terminal_first_line


def test_initmsg_quiet():
    """In quiet mode, the init msg only goes to disk."""
    cmd = create_command('somecommand')
    fake_stream = io.StringIO()
    with patch('charmcraft.main.COMMAND_GROUPS', [('test-group', 'whatever title', [cmd])]):
        with patch.object(logsetup.message_handler, 'ended_ok') as ended_ok_mock:
            with patch.object(logsetup.message_handler._stderr_handler, 'stream', fake_stream):
                main(['charmcraft', '--quiet', 'somecommand'])

    # get the logfile first line before removing it
    ended_ok_mock.assert_called_once_with()
    logged_to_file = pathlib.Path(logsetup.message_handler._log_filepath).read_text()
    file_first_line = logged_to_file.split('\n')[0]
    logsetup.message_handler.ended_ok()

    # get the terminal first line
    captured = fake_stream.getvalue()
    terminal_first_line = captured.split('\n')[0]

    expected = "Starting charmcraft version " + __version__
    assert expected in file_first_line
    assert expected not in terminal_first_line


def test_initmsg_verbose():
    """In verbose mode, the init msg goes both to disk and terminal."""
    cmd = create_command('somecommand')
    fake_stream = io.StringIO()
    with patch('charmcraft.main.COMMAND_GROUPS', [('test-group', 'whatever title', [cmd])]):
        with patch.object(logsetup.message_handler, 'ended_ok') as ended_ok_mock:
            with patch.object(logsetup.message_handler._stderr_handler, 'stream', fake_stream):
                main(['charmcraft', '--verbose', 'somecommand'])

    # get the logfile first line before removing it
    ended_ok_mock.assert_called_once_with()
    logged_to_file = pathlib.Path(logsetup.message_handler._log_filepath).read_text()
    file_first_line = logged_to_file.split('\n')[0]
    logsetup.message_handler.ended_ok()

    # get the terminal first line
    captured = fake_stream.getvalue()
    terminal_first_line = captured.split('\n')[0]

    expected = "Starting charmcraft version " + __version__
    assert expected in file_first_line
    assert expected in terminal_first_line


def test_initmsg_debug(monkeypatch):
    """When in DEBUG, the init msg goes both to disk and terminal."""
    monkeypatch.setenv('DEBUG', '1')

    cmd = create_command('somecommand')
    fake_stream = io.StringIO()
    with patch('charmcraft.main.COMMAND_GROUPS', [('test-group', 'whatever title', [cmd])]):
        with patch.object(logsetup.message_handler, 'ended_ok') as ended_ok_mock:
            with patch.object(logsetup.message_handler._stderr_handler, 'stream', fake_stream):
                main(['charmcraft', 'somecommand'])

    # get the logfile first line before removing it
    ended_ok_mock.assert_called_once_with()
    logged_to_file = pathlib.Path(logsetup.message_handler._log_filepath).read_text()
    file_first_line = logged_to_file.split('\n')[0]
    logsetup.message_handler.ended_ok()

    # get the terminal first line
    captured = fake_stream.getvalue()
    terminal_first_line = captured.split('\n')[0]

    expected = "Starting charmcraft version " + __version__
    assert expected in file_first_line
    assert expected in terminal_first_line
