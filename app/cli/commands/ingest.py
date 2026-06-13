from argparse import Namespace


def register(sub) -> None:
    p = sub.add_parser("ingest", help="Ingest docs into Qdrant")
    p.add_argument("--corpus-dir", default=None, help="Path to corpus directory (default: mock_corpus/)")
    p.add_argument("--chunk-size", type=int, default=800)
    p.add_argument("--chunk-overlap", type=int, default=200)
    p.set_defaults(func=cmd_ingest)


def cmd_ingest(args: Namespace) -> None:
    from app.rag.service import ingest

    ingest(corpus_dir=args.corpus_dir, chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    print("Done.")
