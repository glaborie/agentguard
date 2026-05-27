"""CLI smoke tests — parser recognition, missing-command exit, dispatch wiring."""

import sys

import pytest

from app.cli.app import _build_parser, main

# (argv, expected handler name)
_ALL_COMMANDS = [
    (["ingest"],                                                    "cmd_ingest"),
    (["query", "what is langfuse?"],                                "cmd_query"),
    (["chat"],                                                      "cmd_chat"),
    (["agent", "what is langfuse?"],                                "cmd_agent"),
    (["agent-chat"],                                                "cmd_agent_chat"),
    (["evaluate", "--dataset", "my-ds"],                            "cmd_evaluate"),
    (["online-eval"],                                               "cmd_online_eval"),
    (["experiment", "--dataset", "my-ds", "--models", "m1"],        "cmd_experiment"),
    (["seed-dataset"],                                              "cmd_seed_dataset"),
    (["regression-gate"],                                           "cmd_regression_gate"),
]


class TestParserRecognizesCommands:
    @pytest.mark.parametrize("argv,_", _ALL_COMMANDS)
    def test_command_name(self, argv, _):
        args = _build_parser().parse_args(argv)
        assert args.command == argv[0]


class TestMissingCommandExitsNonzero:
    def test_exits_nonzero(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["agentguard"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code != 0


class TestDispatchWiring:
    @pytest.mark.parametrize("argv,expected_func", _ALL_COMMANDS)
    def test_func_assigned(self, argv, expected_func):
        args = _build_parser().parse_args(argv)
        assert args.func.__name__ == expected_func


class TestSessionUserFlags:
    """--session and --user must be accepted and wired consistently."""

    @pytest.mark.parametrize("cmd", ["query", "chat", "agent-chat"])
    def test_session_and_user_accepted(self, cmd):
        argv = [cmd] + (["q"] if cmd == "query" else [])
        argv += ["--session", "s1", "--user", "u1"]
        args = _build_parser().parse_args(argv)
        assert args.session == "s1"
        assert args.user == "u1"

    def test_agent_session_and_user_accepted(self):
        args = _build_parser().parse_args(["agent", "q", "--session", "s1", "--user", "u1"])
        assert args.session == "s1"
        assert args.user == "u1"

    @pytest.mark.parametrize("cmd", ["query", "chat", "agent", "agent-chat"])
    def test_session_user_default_none(self, cmd):
        argv = [cmd] + (["q"] if cmd in ("query", "agent") else [])
        args = _build_parser().parse_args(argv)
        assert args.session is None
        assert args.user is None
