import logging
import re
import sys
import json
from functools import partial
from typing import Optional, Set

import click

from mloader import __version__ as about
from mloader.exporter import RawExporter, CBZExporter
from mloader.loader import MangaLoader

log = logging.getLogger()

def setup_logging(json_output: bool = False):
    for logger in ("requests", "urllib3"):
        logging.getLogger(logger).setLevel(logging.WARNING)
    handlers = [logging.StreamHandler(sys.stdout)]
    logging.basicConfig(
        handlers=handlers,
        format=(
            "{asctime:^} | {levelname: ^8} | "
            "{filename: ^14} {lineno: <4} | {message}"
        ),
        style="{",
        datefmt="%d.%m.%Y %H:%M:%S",
        level=logging.INFO if not json_output else logging.CRITICAL,
    )

def validate_urls(ctx: click.Context, param, value):
    if not value:
        return value

    res = {"viewer": set(), "titles": set()}
    for url in value:
        match = re.search(r"(\w+)/(\d+)", url)
        if not match:
            raise click.BadParameter(f"Invalid url: {url}")
        try:
            res[match.group(1)].add(int(match.group(2)))
        except (ValueError, KeyError):
            raise click.BadParameter(f"Invalid url: {url}")

    ctx.params.setdefault("titles", set()).update(res["titles"])
    ctx.params.setdefault("chapters", set()).update(res["viewer"])

def validate_ids(ctx: click.Context, param, value):
    if not value:
        return value

    assert param.name in ("chapter", "title")

    ctx.params.setdefault(f"{param.name}s", set()).update(value)

EPILOG = f"""
Examples:

{click.style('• download manga chapter 1 as CBZ archive', fg="green")}

    $ mloader https://mangaplus.shueisha.co.jp/viewer/1

{click.style('• download all chapters for manga title 2 and save '
'to current directory', fg="green")}

    $ mloader https://mangaplus.shueisha.co.jp/titles/2 -o .

{click.style('• download chapter 1 AND all available chapters from '
'title 2 (can be two different manga) in low quality and save as '
'separate images', fg="green")}

    $ mloader https://mangaplus.shueisha.co.jp/viewer/1
    https://mangaplus.shueisha.co.jp/titles/2 -r -q low
"""

@click.command(
    help=about.__description__,
    epilog=EPILOG,
)
@click.version_option(
    about.__version__,
    prog_name=about.__title__,
    message="%(prog)s by Hurlenko, version %(version)s\n"
    f"Check {about.__url__} for more info",
)
@click.option(
    "--out",
    "-o",
    "out_dir",
    type=click.Path(exists=False, writable=True),
    metavar="<directory>",
    default="mloader_downloads",
    show_default=True,
    help="Save directory (not a file)",
    envvar="MLOADER_EXTRACT_OUT_DIR",
)
@click.option(
    "--raw",
    "-r",
    is_flag=True,
    default=False,
    show_default=True,
    help="Save raw images",
    envvar="MLOADER_RAW",
)
@click.option(
    "--quality",
    "-q",
    default="super_high",
    type=click.Choice(["super_high", "high", "low"]),
    show_default=True,
    help="Image quality",
    envvar="MLOADER_QUALITY",
)
@click.option(
    "--split",
    "-s",
    is_flag=True,
    default=False,
    show_default=True,
    help="Split combined images",
    envvar="MLOADER_SPLIT",
)
@click.option(
    "--chapter",
    "-c",
    type=click.INT,
    multiple=True,
    help="Chapter id",
    expose_value=False,
    callback=validate_ids,
)
@click.option(
    "--title",
    "-t",
    type=click.INT,
    multiple=True,
    help="Title id",
    expose_value=False,
    callback=validate_ids,
)
@click.option(
    "--begin",
    "-b",
    type=click.IntRange(min=0),
    default=0,
    show_default=True,
    help="Minimal chapter to try to download",
)
@click.option(
    "--end",
    "-e",
    type=click.IntRange(min=1),
    help="Maximal chapter to try to download",
)
@click.option(
    "--last",
    "-l",
    is_flag=True,
    default=False,
    show_default=True,
    help="Download only the last chapter for title",
)
@click.option(
    "--chapter-title",
    is_flag=True,
    default=False,
    show_default=True,
    help="Include chapter titles in filenames",
)
@click.option(
    "--chapter-subdir",
    is_flag=True,
    default=False,
    show_default=True,
    help="Save raw images in sub directory by chapter",
)
@click.option(
    "--json",
    "-j",
    "json_output",
    is_flag=True,
    default=False,
    show_default=True,
    help="Output JSON metadata of downloaded chapters after download completes",
)
@click.argument("urls", nargs=-1, callback=validate_urls, expose_value=False)
@click.pass_context
def main(
    ctx: click.Context,
    out_dir: str,
    raw: bool,
    quality: str,
    split: bool,
    begin: int,
    end: int,
    last: bool,
    chapter_title: bool,
    chapter_subdir: bool,
    json_output: bool,  # Add this parameter
    chapters: Optional[Set[int]] = None,
    titles: Optional[Set[int]] = None,
):
    if not json_output:
        click.echo(click.style(about.__doc__, fg="blue"))
    if not any((chapters, titles)):
        click.echo(ctx.get_help())
        return
    end = end or float("inf")

    setup_logging(json_output)

    if not json_output:
        log.info("Started export")

    exporter = RawExporter if raw else CBZExporter
    exporter = partial(
        exporter,
        destination=out_dir,
        add_chapter_title=chapter_title,
        add_chapter_subdir=chapter_subdir,
    )

    loader = MangaLoader(exporter, quality, split)
    try:
        downloaded_metadata = loader.download(
            title_ids=titles,
            chapter_ids=chapters,
            min_chapter=begin,
            max_chapter=end,
            last_chapter=last,
            return_metadata=json_output,  # Pass the flag
        )

        # If JSON output is requested, print the metadata after download
        if json_output:
            result = {"status": "success", "chapters": downloaded_metadata}
            print(json.dumps(result, indent=4, ensure_ascii=False))
        else:
            log.info("SUCCESS")
    except Exception:
        log.exception("Failed to download manga")
        if json_output:
            error_json = {"status": "error", "chapters": []}
            print(json.dumps(error_json, indent=4))

if __name__ == "__main__":
    main(prog_name=about.__title__)
