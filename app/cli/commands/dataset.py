from argparse import Namespace


def cmd_seed_dataset(args: Namespace) -> None:
    from scripts.seed_dataset import main as seed_main

    seed_main()
