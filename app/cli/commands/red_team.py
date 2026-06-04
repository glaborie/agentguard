import logging
import sys
from argparse import Namespace

from scripts.red_team import ALL_ATTACK_TYPES

logger = logging.getLogger(__name__)


def register(sub) -> None:
    p = sub.add_parser(
        "red-team",
        help="Probe guardrail stack with auto-generated adversarial prompts",
    )
    p.add_argument(
        "--attacks",
        nargs="+",
        choices=ALL_ATTACK_TYPES,
        default=None,
        metavar="ATTACK",
        help=f"Attack types (default: all). Choices: {', '.join(ALL_ATTACK_TYPES)}",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Variants per attack type (default: 5)",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Model for generation and probing (default: settings.default_model)",
    )
    p.add_argument(
        "--proxy-url",
        default=None,
        help="LiteLLM proxy URL (default: settings.litellm_base_url)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout per call in seconds (default: 30.0)",
    )
    p.set_defaults(func=cmd_red_team)


def cmd_red_team(args: Namespace) -> None:
    from scripts.red_team import run_red_team

    try:
        passed = run_red_team(
            attack_types=args.attacks,
            n_variants=args.limit,
            model=args.model,
            proxy_url=args.proxy_url,
            timeout=args.timeout,
        )
    except Exception as exc:
        logger.error("Red team error: %s", exc, exc_info=True)
        sys.exit(2)

    sys.exit(0 if passed else 1)
