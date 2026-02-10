"""CLI entry point for content pipeline."""
from pathlib import Path

import click

from src.database import Database
from src.feed_manager import FeedManager


def get_db() -> Database:
    """Get database instance."""
    db_path = Path(__file__).parent.parent / "data" / "pipeline.db"
    return Database(db_path)


@click.group()
def cli():
    """AI Research Assistant - Import articles, videos, and podcasts to Obsidian."""
    pass


# === Pipeline Commands ===


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would be processed without doing it")
@click.option("--limit", "-n", type=int, default=None, help="Limit number of items to process")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed progress during execution")
def run(dry_run: bool, limit: int | None, verbose: bool):
    """Run the content pipeline."""
    import logging

    from src.pipeline import run_pipeline

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    db = get_db()
    result = run_pipeline(db, dry_run=dry_run, limit=limit, verbose=verbose)

    click.echo(f"Processed: {result.processed}, Failed: {result.failed}")
    if result.retried:
        click.echo(f"Retried: {result.retried}")
    if result.skipped:
        click.echo(f"Skipped (dry run): {result.skipped}")


@cli.command()
def status():
    """Show pipeline status: pending items, retry queue, last run."""
    db = get_db()
    fm = FeedManager(db)

    # Last run info
    last_run = db.get_last_successful_run()
    if last_run:
        click.echo(f"Last successful run: {last_run.strftime('%Y-%m-%d %H:%M')}")
    else:
        click.echo("No previous runs")

    # Pending items
    entries = fm.fetch_new_entries()
    click.echo(f"Pending items: {len(entries)}")

    # Retry queue
    retry_entries = db.get_retry_candidates()
    click.echo(f"In retry queue: {len(retry_entries)}")

    # Feed counts
    feeds = fm.list_feeds()
    by_category = {}
    for f in feeds:
        by_category[f.category] = by_category.get(f.category, 0) + 1
    click.echo(f"Feeds: {by_category}")


# === Feed Management Commands ===


@cli.group()
def feeds():
    """Manage feed subscriptions."""
    pass


@feeds.command("add")
@click.argument("url")
@click.option(
    "--category",
    "-c",
    type=click.Choice(["articles", "youtube", "podcasts"]),
    help="Feed category (auto-detected if not specified)",
)
def feeds_add(url: str, category: str | None):
    """Add a new feed subscription."""
    db = get_db()
    fm = FeedManager(db)

    try:
        feed = fm.add_feed(url, category)
        click.echo(f"Added: {feed.title} ({feed.category})")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@feeds.command("remove")
@click.argument("url")
def feeds_remove(url: str):
    """Remove a feed subscription."""
    db = get_db()
    fm = FeedManager(db)

    fm.remove_feed(url)
    click.echo(f"Removed: {url}")


@feeds.command("list")
@click.option(
    "--category",
    "-c",
    type=click.Choice(["articles", "youtube", "podcasts"]),
    help="Filter by category",
)
def feeds_list(category: str | None):
    """List all feed subscriptions."""
    db = get_db()
    fm = FeedManager(db)

    feed_list = fm.list_feeds(category)
    for feed in feed_list:
        click.echo(f"[{feed.category}] {feed.title}")
        click.echo(f"    {feed.url}")


@feeds.command("export")
@click.option(
    "--output",
    "-o",
    default="exports/feeds.opml",
    help="Output file path (default: exports/feeds.opml)",
)
def feeds_export(output: str):
    """Export feeds to OPML format."""
    db = get_db()
    fm = FeedManager(db)

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fm.export_opml(output_path)
    click.echo(f"Exported to: {output_path}")


@feeds.command("import")
@click.argument("opml_file", type=click.Path(exists=True))
def feeds_import(opml_file: str):
    """Import feeds from OPML file."""
    db = get_db()
    fm = FeedManager(db)

    count = fm.import_opml(Path(opml_file))
    click.echo(f"Imported {count} feeds")


from src.setup import setup  # noqa: E402

cli.add_command(setup)

if __name__ == "__main__":
    cli()
