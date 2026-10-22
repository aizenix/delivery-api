import argparse
import asyncio

from app.db import SessionLocal, engine
from app.services.catalog import import_catalog


async def run_import(path: str) -> None:
    with open(path, encoding="utf-8-sig", newline="") as f:
        async with SessionLocal() as session:
            report = await import_catalog(session, f)
    await engine.dispose()

    print(f"created: {report.created}, updated: {report.updated}, skipped: {len(report.errors)}")
    for error in report.errors:
        print(f"  line {error.line}: {error.error}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    import_cmd = commands.add_parser("import-catalog", help="upsert products from a supplier CSV")
    import_cmd.add_argument("path")

    args = parser.parse_args()
    if args.command == "import-catalog":
        asyncio.run(run_import(args.path))


if __name__ == "__main__":
    main()
