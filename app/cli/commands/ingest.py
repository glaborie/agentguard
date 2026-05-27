from argparse import Namespace


def cmd_ingest(args: Namespace) -> None:
    from app.rag.ingest import ingest

    ingest(chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    print("Done.")
