#!/usr/bin/env python3
"""
CLI launcher for batch converting tracking PDFs to JSON from the terminal.
Outputs JSON matching standard schema: { success, pagination, data: [...] }
"""

import sys
import os
import json
import argparse
from parsers import parse_tracking_pdf
from engine import convert_batch_parallel
from config import DEFAULT_WORKERS

def main():
    parser = argparse.ArgumentParser(
        description="FileToJSON CLI: High-Speed Batch Tracking PDF to JSON Converter (1,000+ docs in seconds)."
    )
    parser.add_argument("files", nargs="*", help="PDF file(s) or directory to convert")
    parser.add_argument("-i", "--input", help="Input directory containing tracking PDFs")
    parser.add_argument("-d", "--output-dir", help="Output directory for individual .json files")
    parser.add_argument("-o", "--output", help="Output path for a single combined .json master array")
    parser.add_argument("-w", "--workers", type=int, default=DEFAULT_WORKERS, help="Number of worker threads (default: auto)")

    args = parser.parse_args()

    file_list = []
    if args.input and os.path.isdir(args.input):
        for f in sorted(os.listdir(args.input)):
            if f.lower().endswith(".pdf") and not f.startswith("."):
                file_list.append(os.path.join(args.input, f))

    for target in args.files:
        if os.path.isfile(target) and target.lower().endswith(".pdf"):
            file_list.append(os.path.abspath(target))
        elif os.path.isdir(target):
            for f in sorted(os.listdir(target)):
                if f.lower().endswith(".pdf") and not f.startswith("."):
                    file_list.append(os.path.join(target, f))

    if not file_list:
        parser.print_help()
        sys.exit(1)

    # 1. Single file terminal output
    if len(file_list) == 1 and not args.output_dir and not args.output:
        result = parse_tracking_pdf(file_list[0])
        response = {
            "success": True,
            "pagination": {
                "page": 1,
                "limit": 1,
                "totalPages": 1,
                "totalCount": 1
            },
            "data": [result]
        }
        print(json.dumps(response, indent=2, ensure_ascii=False))
        return

    # 2. Batch conversion
    stats = convert_batch_parallel(
        items=file_list,
        workers=args.workers,
        output_dir=args.output_dir,
        combined_file=args.output
    )

    total_count = len(stats["results"])
    response = {
        "success": stats["failed"] == 0,
        "pagination": {
            "page": 1,
            "limit": total_count if total_count > 0 else 1,
            "totalPages": 1,
            "totalCount": total_count
        },
        "data": stats["results"]
    }

    if not args.output_dir and not args.output:
        print(json.dumps(response, indent=2, ensure_ascii=False))
    else:
        print(f"\n✅ Converted {total_count} files in {stats['elapsed_seconds']}s ({stats['throughput_docs_per_sec']} docs/sec)\n")

if __name__ == "__main__":
    main()
