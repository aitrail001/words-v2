from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from app.services.source_imports import EpubTextExtractor, iter_normalized_words


def suspicious_tokens(tokens: list[str]) -> list[tuple[str, int]]:
    counts = Counter(
        token
        for token in tokens
        if (len(token) == 1 and token not in {"a", "i"})
        or "--" in token
        or token in {"enguin", "ouse", "om", "imprintof", "formymotherandfather"}
    )
    return counts.most_common(12)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect EPUB extraction quality on a directory of EPUB files.")
    parser.add_argument(
        "epub_dir",
        nargs="?",
        default="/Users/johnson/Downloads/Organized/Ebooks",
        help="Directory containing EPUB files",
    )
    parser.add_argument("--limit", type=int, default=12, help="Maximum number of EPUB files to inspect")
    args = parser.parse_args()

    epub_dir = Path(args.epub_dir)
    files = sorted(epub_dir.glob("*.epub"))[: args.limit]
    extractor = EpubTextExtractor()

    for path in files:
        metadata, chunks = extractor.extract_metadata_and_chunks(path)
        chunk_list = list(chunks)
        token_list = iter_normalized_words(" ".join(chunk_list[:10]))
        print(f"\nFILE: {path.name}")
        print(f"  Title: {metadata.title}")
        print(f"  Author: {metadata.author}")
        print(f"  Publisher: {metadata.publisher}")
        print(f"  Year: {metadata.published_year}")
        print(f"  ISBN: {metadata.isbn}")
        print(f"  Chunks: {len(chunk_list)}")
        print(f"  Tokens(sample): {token_list[:20]}")
        suspicious = suspicious_tokens(token_list)
        if suspicious:
            print(f"  Suspicious tokens: {suspicious}")
        else:
            print("  Suspicious tokens: none")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
