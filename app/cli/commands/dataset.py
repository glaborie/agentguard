from argparse import Namespace


def register(sub) -> None:
    p = sub.add_parser("seed-dataset", help="Create the rag-eval-v1 dataset in Langfuse")
    p.set_defaults(func=cmd_seed_dataset)


def cmd_seed_dataset(args: Namespace) -> None:
    from scripts.seed_dataset import main as seed_main

    seed_main()
