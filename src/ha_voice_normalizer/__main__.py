"""Command line interface: ``python -m ha_voice_normalizer "stav Alfa Bravo"``."""

import argparse
import json
import sys

from .pipeline import normalize_text
from .spelling import SpellingMode


def main(argv: list[str] | None = None) -> int:
    """Normalize text from the command line and print the result."""
    parser = argparse.ArgumentParser(
        prog="ha_voice_normalizer",
        description="Normalize speech-to-text output (phonetic spelling and friends).",
    )
    parser.add_argument("text", nargs="*", help="text to normalize; omit to read stdin")
    parser.add_argument("-l", "--language", default=None, help='language tag, e.g. "nb"')
    parser.add_argument(
        "-m",
        "--mode",
        default=SpellingMode.STRICT.value,
        choices=[mode.value for mode in SpellingMode],
        help="spelling mode (default: strict)",
    )
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)

    text = " ".join(args.text) if args.text else sys.stdin.read().strip()
    result = normalize_text(text, args.language, spelling_mode=args.mode)

    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(result.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
