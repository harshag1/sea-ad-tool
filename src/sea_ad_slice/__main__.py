import argparse
import json
from pathlib import Path

from .core import Catalog, build_index, inspect_source


def main():
    parser = argparse.ArgumentParser(prog='sea-ad-slice')
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('source')
    index = commands.add_parser('index')
    index.add_argument('source')
    index.add_argument('--db', required=True)
    index.add_argument('--force', action='store_true')
    for name in ['summary', 'preview', 'export', 'pseudobulk']:
        command = commands.add_parser(name)
        command.add_argument('--db', required=True)
        if name == 'summary':
            continue
        command.add_argument('--filters', default='{}')
        command.add_argument('--donor-field', default='Donor ID')
        if name == 'preview':
            continue
        command.add_argument('--genes', nargs='*')
        command.add_argument('--layer', default='X' if name == 'export' else None)
        command.add_argument('--engine', choices=['rust', 'scipy'], default='rust')
        command.add_argument('--output', required=True)
        if name == 'export':
            command.add_argument('--limit', type=int)
            command.add_argument('--split-seed', type=int)
            command.add_argument('--batch-rows', type=int, default=2048)
    args = parser.parse_args()
    if args.command == 'inspect':
        result = inspect_source(args.source)
    elif args.command == 'index':
        result = build_index(args.source, args.db, force=args.force)
    else:
        catalog = Catalog(args.db)
        if args.command == 'summary':
            result = catalog.summary()
        elif args.command == 'preview':
            result = catalog.preview(json.loads(args.filters), args.donor_field)
        elif args.command == 'export':
            result = catalog.export(args.output, filters=json.loads(args.filters), genes=args.genes, layer=args.layer, limit=args.limit, batch_rows=args.batch_rows, engine=args.engine, split_seed=args.split_seed, donor_field=args.donor_field)
        else:
            output = Path(args.output)
            if output.exists():
                raise FileExistsError(output)
            output.parent.mkdir(parents=True, exist_ok=True)
            data = catalog.pseudobulk(filters=json.loads(args.filters), genes=args.genes, layer=args.layer, donor_field=args.donor_field, engine=args.engine)
            data.write_h5ad(output)
            result = {'output': str(output), 'shape': list(data.shape), 'provenance': json.loads(data.uns['sea_ad_slice'])}
            output.with_suffix(output.suffix + '.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
