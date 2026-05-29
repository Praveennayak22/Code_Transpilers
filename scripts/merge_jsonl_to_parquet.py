#!/usr/bin/env python3
"""
merge_jsonl_to_parquet.py
=========================
Merges all output JSONL chunk files from the transpilation pipeline
into a single compressed Parquet file with the supervisor-approved schema.

Final Parquet schema (11 columns):
    repo_name, repo_url, github_id, blob_id, path,
    source_language, source_code,
    canonical_IR, transformed_IR,
    target_code, target_language

Usage:
    python3 merge_jsonl_to_parquet.py \\
        --input_dir  /path/to/output/chunks/ \\
        --output_file /path/to/final_dataset.parquet
"""

import os
import sys
import glob
import json
import argparse
import pyarrow as pa
import pyarrow.parquet as pq


def main():
    parser = argparse.ArgumentParser(description="Merge JSONL files into a single Parquet file")
    parser.add_argument("--input_dir",   required=True, help="Directory containing .jsonl files")
    parser.add_argument("--output_file", required=True, help="Output .parquet file path")
    args = parser.parse_args()

    input_dir   = args.input_dir
    output_file = args.output_file

    if not os.path.isdir(input_dir):
        print(f"Error: {input_dir} is not a valid directory.")
        sys.exit(1)

    jsonl_files = sorted(glob.glob(os.path.join(input_dir, "*.jsonl")))
    if not jsonl_files:
        print(f"Error: No .jsonl files found in {input_dir}")
        sys.exit(1)

    print(f"Found {len(jsonl_files)} JSONL files to merge.")

    # ── Strict 11-column supervisor-approved schema ───────────────────────────
    schema = pa.schema([
        ('repo_name',        pa.string()),   # name of repository
        ('repo_url',         pa.string()),   # url of repository
        ('github_id',        pa.string()),   # github repository id
        ('blob_id',          pa.string()),   # file blob_id
        ('path',             pa.string()),   # path of file inside repository
        ('source_language',  pa.string()),   # source programming language
        ('source_code',      pa.string()),   # original source code (content)
        ('canonical_IR',     pa.string()),   # IR after Stage 3 Lift (JSON)
        ('transformed_IR',   pa.string()),   # IR after Stage 4 Transform (JSON)
        ('target_code',      pa.string()),   # generated transpiled code
        ('target_language',  pa.string()),   # target programming language
    ])

    writer    = None
    total_rows = 0

    try:
        writer = pq.ParquetWriter(output_file, schema, compression='snappy')

        for i, file_path in enumerate(jsonl_files):
            if i % 100 == 0 and i > 0:
                print(f"  Processed {i}/{len(jsonl_files)} files... ({total_rows:,} rows so far)")

            batch_data = {
                'repo_name':       [],
                'repo_url':        [],
                'github_id':       [],
                'blob_id':         [],
                'path':            [],
                'source_language': [],
                'source_code':     [],
                'canonical_IR':    [],
                'transformed_IR':  [],
                'target_code':     [],
                'target_language': [],
            }

            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)

                        # Skip rows that failed transpilation
                        if not row.get('transpile_success', True) and not row.get('target_code'):
                            if not row.get('canonical_IR') and not row.get('transformed_IR'):
                                continue

                        batch_data['repo_name'].append(       str(row.get('repo_name', '') or ''))
                        batch_data['repo_url'].append(        str(row.get('repo_url', '') or ''))
                        batch_data['github_id'].append(       str(row.get('github_id', '') or ''))
                        batch_data['blob_id'].append(         str(row.get('blob_id', '') or ''))
                        batch_data['path'].append(            str(row.get('path', '') or ''))
                        batch_data['source_language'].append( str(row.get('source_language', '') or ''))
                        batch_data['source_code'].append(     str(row.get('source_code', '') or ''))

                        # IRs are JSON strings — keep as-is, handle dict fallback
                        can_ir = row.get('canonical_IR') or row.get('canonical_ir', '')
                        if isinstance(can_ir, dict):
                            can_ir = json.dumps(can_ir)
                        batch_data['canonical_IR'].append(str(can_ir) if can_ir else '')

                        trans_ir = row.get('transformed_IR') or row.get('transformed_ir', '')
                        if isinstance(trans_ir, dict):
                            trans_ir = json.dumps(trans_ir)
                        batch_data['transformed_IR'].append(str(trans_ir) if trans_ir else '')

                        batch_data['target_code'].append(     str(row.get('target_code', '') or ''))
                        batch_data['target_language'].append( str(row.get('target_language', '') or ''))

                        total_rows += 1

                    except json.JSONDecodeError:
                        continue

            if batch_data['source_code']:
                table = pa.Table.from_pydict(batch_data, schema=schema)
                writer.write_table(table)

    except Exception as e:
        print(f"\nError writing to Parquet: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
    finally:
        if writer:
            writer.close()

    size_mb = os.path.getsize(output_file) / 1e6 if os.path.exists(output_file) else 0
    print(f"\n{'='*60}")
    print(f"SUCCESS: Merged {total_rows:,} rows into:")
    print(f"  {output_file}")
    print(f"  File size: {size_mb:.1f} MB")
    print(f"\nFinal schema ({len(schema)} columns):")
    for field in schema:
        print(f"  {field.name}")


if __name__ == "__main__":
    main()
