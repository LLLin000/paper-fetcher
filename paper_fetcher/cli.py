"""CLI interface for paper-fetcher."""

import logging
import os
import sys
from pathlib import Path

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import typer
from rich.console import Console
from rich.table import Table

from .config import Config
from .fetcher import PaperFetcher
from .sources import semantic_scholar
from .sources.pubmed_search import search as pubmed_search

app = typer.Typer(
    name="paper-fetcher",
    help="Fetch academic papers via Open Access, university proxy, or arXiv.",
    no_args_is_help=True,
)
console = Console()


def _setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _ensure_email(config: Config):
    """Prompt user to set email if not configured (needed for Unpaywall)."""
    if not config.email:
        console.print("[yellow]Email not configured (needed for Unpaywall OA detection).[/yellow]")
        email = typer.prompt("Enter your email address")
        config.email = email
        config.save()
        console.print(f"[green]Email saved: {email}[/green]")


@app.command()
def login(
    force: bool = typer.Option(False, "--force", "-f", help="Force re-login even if session is valid."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
):
    """Initialize or refresh university proxy session."""
    _setup_logging(verbose)
    config = Config.load()
    fetcher = PaperFetcher(config)

    if not config.proxy_base:
        console.print("[red]No proxy configured. Set it with:[/red]")
        console.print("  paper-fetcher config-cmd --proxy https://webvpn.your-university.edu.cn/")
        raise typer.Exit(1)

    console.print(f"[bold]Checking {fetcher.auth._proxy_type.upper()} session...[/bold]")
    if fetcher.auth.login(force=force):
        console.print("[green]Proxy session is active.[/green]")
    else:
        console.print("[red]Failed to authenticate with proxy.[/red]")
        raise typer.Exit(1)


@app.command()
def fetch(
    identifier: str = typer.Argument(help="DOI or URL of the paper to fetch."),
    output: str = typer.Option("", "--output", "-o", help="Output directory for PDFs."),
    format: str = typer.Option("json", "--format", "-f", help="Output format: json, markdown, text."),
    text_only: bool = typer.Option(False, "--text-only", "-t", help="Output only plain text (minimal tokens)."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass cache."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
):
    """Fetch a single paper by DOI or URL."""
    _setup_logging(verbose)
    config = Config.load()
    _ensure_email(config)
    if output:
        config.output_dir = output

    fetcher = PaperFetcher(config)
    try:
        console.print(f"[bold]Fetching:[/bold] {identifier}")
        paper = fetcher.fetch(identifier, use_cache=not no_cache)

        if not paper.full_text and not paper.abstract:
            console.print("[yellow]Warning: Could not extract full text.[/yellow]")

        if text_only:
            console.print(paper.to_text())
        elif format == "markdown":
            console.print(paper.to_markdown())
        elif format == "text":
            console.print(paper.to_text())
        else:
            console.print(paper.to_json())

        if paper.pdf_path:
            console.print(f"\n[dim]PDF saved to: {paper.pdf_path}[/dim]")
        console.print(f"[dim]Source: {paper.source}[/dim]")

    finally:
        fetcher.close()


@app.command()
def batch(
    file: Path = typer.Argument(help="File containing DOIs or PMIDs (one per line)."),
    output: str = typer.Option("", "--output", "-o", help="Output directory."),
    format: str = typer.Option("json", "--format", "-f", help="Output format: json, markdown, text."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
):
    """Fetch multiple papers from a file of identifiers (DOI or PMID)."""
    _setup_logging(verbose)

    if not file.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    identifiers = [
        line.strip()
        for line in file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not identifiers:
        console.print("[yellow]No identifiers found in file.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]Found {len(identifiers)} identifiers to fetch.[/bold]")

    config = Config.load()
    if output:
        config.output_dir = output

    fetcher = PaperFetcher(config)
    results_dir = Path(config.output_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    succeeded = 0
    failed = 0
    no_full_text = 0

    try:
        for i, identifier in enumerate(identifiers, 1):
            console.print(f"\n[bold][{i}/{len(identifiers)}][/bold] Fetching: {identifier}")
            try:
                paper = fetcher.fetch(identifier)
                if paper.full_text:
                    succeeded += 1
                    # Determine safe filename
                    if identifier.startswith("10."):
                        safe_name = identifier.replace("/", "_").replace(":", "_")
                    else:
                        safe_name = f"PMID_{identifier}"
                    
                    if format == "markdown":
                        out_file = results_dir / f"{safe_name}.md"
                        out_file.write_text(paper.to_markdown(), encoding="utf-8")
                    elif format == "text":
                        out_file = results_dir / f"{safe_name}.txt"
                        out_file.write_text(paper.to_text(), encoding="utf-8")
                    else:
                        out_file = results_dir / f"{safe_name}.json"
                        out_file.write_text(paper.to_json(), encoding="utf-8")
                    console.print(f"  [green]OK[/green] → {out_file.name}")
                elif paper.abstract:
                    no_full_text += 1
                    console.print("  [yellow]Abstract only (no full text)[/yellow]")
                else:
                    failed += 1
                    console.print("  [red]No content extracted[/red]")
            except Exception as e:
                failed += 1
                console.print(f"  [red]Error: {e}[/red]")

        console.print(f"\n[bold]Done:[/bold] {succeeded} succeeded, {no_full_text} abstract only, {failed} failed out of {len(identifiers)}.")

    finally:
        fetcher.close()


@app.command()
def search(
    query: str = typer.Argument(help="Search query."),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum results."),
    year: str = typer.Option("", "--year", "-y", help="Year range, e.g., '2020-2024' or '2020-'."),
    source: str = typer.Option("semantic_scholar", "--source", "-s", help="Source: semantic_scholar, pubmed."),
    do_fetch: bool = typer.Option(False, "--fetch", help="Also fetch full text for results with DOIs."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
):
    """Search for papers via Semantic Scholar or PubMed."""
    _setup_logging(verbose)

    console.print(f"[bold]Searching {source}:[/bold] {query}")
    
    if source == "pubmed":
        # Parse year range for PubMed
        year_from = None
        year_to = None
        if year:
            if "-" in year:
                parts = year.split("-")
                year_from = int(parts[0]) if parts[0] else None
                year_to = int(parts[1]) if parts[1] else None
            else:
                year_from = int(year)
        
        results = pubmed_search(query, limit=limit, date_from=f"{year_from}/01/01" if year_from else None, 
                                date_to=f"{year_to}/12/31" if year_to else None)
        
        if not results:
            console.print("[yellow]No results found.[/yellow]")
            raise typer.Exit(0)
        
        table = Table(title=f"PubMed Search Results ({len(results)})")
        table.add_column("#", style="dim", width=3)
        table.add_column("Year", width=5)
        table.add_column("Title", max_width=60)
        table.add_column("Journal", max_width=25)
        table.add_column("PMID", width=10)
        
        for i, r in enumerate(results, 1):
            pub_year = r.pub_date.split("-")[0] if r.pub_date else ""
            table.add_row(
                str(i),
                pub_year,
                r.title[:60] if r.title else "",
                r.journal[:25] if r.journal else "",
                r.pmid,
            )
        
        console.print(table)
        
        # Optionally fetch full texts
        if do_fetch:
            fetchable = [r for r in results if r.pmid]
            if fetchable:
                console.print(f"\n[bold]Fetching {len(fetchable)} papers...[/bold]")
                config = Config.load()
                fetcher = PaperFetcher(config)
                try:
                    for r in fetchable:
                        console.print(f"  Fetching PMID: {r.pmid}")
                        try:
                            paper = fetcher.fetch(r.pmid)
                            status = "[green]OK[/green]" if paper.full_text else "[yellow]No text[/yellow]"
                            console.print(f"    {status}")
                        except Exception as e:
                            console.print(f"    [red]Error: {e}[/red]")
                finally:
                    fetcher.close()
    else:
        results = semantic_scholar.search(query, limit=limit, year_range=year or None)

        if not results:
            console.print("[yellow]No results found.[/yellow]")
            raise typer.Exit(0)

        table = Table(title=f"Semantic Scholar Results ({len(results)})")
        table.add_column("#", style="dim", width=3)
        table.add_column("Year", width=5)
        table.add_column("Title", max_width=60)
        table.add_column("Authors", max_width=30)
        table.add_column("DOI", max_width=25)
        table.add_column("Cites", width=5, justify="right")

        for i, r in enumerate(results, 1):
            authors_str = ", ".join(r.authors[:3])
            if len(r.authors) > 3:
                authors_str += " et al."
            table.add_row(
                str(i),
                str(r.year or ""),
                r.title[:60],
                authors_str[:30],
                r.doi[:25] if r.doi else r.arxiv_id[:25] if r.arxiv_id else "",
                str(r.citation_count),
            )

        console.print(table)

        if do_fetch:
            fetchable = [r for r in results if r.doi or r.arxiv_id]
            if fetchable:
                console.print(f"\n[bold]Fetching {len(fetchable)} papers...[/bold]")
                config = Config.load()
                fetcher = PaperFetcher(config)
                try:
                    for r in fetchable:
                        identifier = r.doi or f"arxiv:{r.arxiv_id}"
                        console.print(f"  Fetching: {identifier}")
                        try:
                            paper = fetcher.fetch(identifier)
                            status = "[green]OK[/green]" if paper.full_text else "[yellow]No text[/yellow]"
                            console.print(f"    {status}")
                        except Exception as e:
                            console.print(f"    [red]Error: {e}[/red]")
                finally:
                    fetcher.close()


@app.command()
def cache(
    action: str = typer.Argument(help="Action: 'clear' to remove cached results."),
):
    """Manage the paper cache."""
    if action == "clear":
        config = Config.load()
        fetcher = PaperFetcher(config)
        fetcher.clear_cache()
        console.print("[green]Cache cleared.[/green]")
    else:
        console.print(f"[red]Unknown action: {action}. Use 'clear'.[/red]")
        raise typer.Exit(1)


@app.command()
def config_cmd(
    show: bool = typer.Option(True, "--show", help="Show current config."),
    set_email: str = typer.Option("", "--email", help="Set email for Unpaywall API."),
    set_output: str = typer.Option("", "--output-dir", help="Set default output directory."),
    set_proxy: str = typer.Option("", "--proxy", help="Set university proxy URL (e.g., https://webvpn.sdu.edu.cn/)."),
):
    """View or update configuration."""
    cfg = Config.load()

    if set_email:
        cfg.email = set_email
        cfg.save()
        console.print(f"[green]Email set to: {set_email}[/green]")

    if set_output:
        cfg.output_dir = set_output
        cfg.save()
        console.print(f"[green]Output dir set to: {set_output}[/green]")

    if set_proxy:
        cfg.proxy_base = set_proxy
        cfg.save()
        console.print(f"[green]Proxy set to: {set_proxy}[/green]")

    if show and not set_email and not set_output and not set_proxy:
        console.print("[bold]Current configuration:[/bold]")
        console.print(f"  Proxy base:  {cfg.proxy_base or '(not set)'}")
        console.print(f"  Email:       {cfg.email}")
        console.print(f"  Output dir:  {cfg.output_dir}")
        console.print(f"  Cache dir:   {cfg.cache_dir}")
        console.print(f"  Cookie path: {cfg.cookie_path}")
        
        if not cfg.proxy_base:
            console.print("\n[yellow]Note: No proxy configured. Set your university proxy to access paywalled papers.[/yellow]")
            console.print("  Example: paper-fetcher config-cmd --proxy https://webvpn.sdu.edu.cn/")


if __name__ == "__main__":
    app()
