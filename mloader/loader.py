import logging
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from itertools import chain, count
from typing import Union, Dict, Set, Collection, Optional, Callable, List, ContextManager
from contextlib import contextmanager, nullcontext
import uuid
import os

import click
from requests import Session

from mloader.constants import PageType
from mloader.exporter import ExporterBase
from mloader.response_pb2 import (
    Response,
    MangaViewer,
    TitleDetailView,
    Chapter,
    Title,
)
from mloader.utils import chapter_name_to_int

try:
    from curl_adapter import CurlCffiAdapter
    HAS_CURL_ADAPTER = True
except ImportError:
    HAS_CURL_ADAPTER = False
    CurlCffiAdapter = None

log = logging.getLogger()

MangaList = Dict[int, Set[int]]  # Title ID: Set[Chapter ID]

try:
    WORKERS = int(os.getenv("MAX_WORKERS", 8))
except (TypeError, ValueError):
    log.warning("Invalid worker count, reverting to default (8)")
    WORKERS = 8
if WORKERS < 1 or WORKERS > 8:
    log.warning("Invalid worker count, reverting to default (8)")
    WORKERS = 8


@contextmanager
def json_output_context(json_output: bool) -> ContextManager[None]:
    """
    Context manager to handle JSON output.

    Args:
        json_output: If True, suppress logging output and banner.
    """
    if json_output:
        # Suppress logging output
        logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        if json_output:
            # Re-enable logging output
            logging.disable(logging.NOTSET)


class MangaLoader:
    def __init__(
        self,
        exporter: Callable[[Title, Chapter, Optional[Chapter]], ExporterBase],
        quality: str = "super_high",
        split: bool = False,
    ):
        self.exporter = exporter
        self.quality = quality
        self.split = split
        self._api_url = os.getenv("MANGAPLUS_URL") or "https://jumpg-webapi.tokyo-cdn.com"
        
        # Use CustomSession with curl_adapter if available for better performance
        if HAS_CURL_ADAPTER and CurlCffiAdapter:
            from mloader.utils import CustomSession
            session = CustomSession()
            session.mount("http://", CurlCffiAdapter())
            session.mount("https://", CurlCffiAdapter())
        else:
            session = Session()
        
        self.session = session
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; "
                "rv:72.0) Gecko/20100101 Firefox/72.0",
                "Session-Token": str(uuid.uuid1())
            }
        )

    def _decrypt_image(self, url: str, encryption_hex: str) -> bytearray:
        resp = self.session.get(url)
        data = bytearray(resp.content)
        key = bytes.fromhex(encryption_hex)
        a = len(key)
        for s in range(len(data)):
            data[s] ^= key[s % a]
        return data

    @lru_cache(None)
    def _load_pages(self, chapter_id: Union[str, int]) -> MangaViewer:
        resp = self.session.get(
            f"{self._api_url}/api/manga_viewer",
            params={
                "chapter_id": chapter_id,
                "split": "yes" if self.split else "no",
                "img_quality": self.quality,
            },
        )
        return Response.FromString(resp.content).success.manga_viewer

    @lru_cache(None)
    def _get_title_details(self, title_id: Union[str, int]) -> TitleDetailView:
        resp = self.session.get(
            f"{self._api_url}/api/title_detailV3", params={"title_id": title_id}
        )
        return Response.FromString(resp.content).success.title_detail_view

    def _normalize_ids(
        self,
        title_ids: Collection[int],
        chapter_ids: Collection[int],
        min_chapter: int,
        max_chapter: int,
        last_chapter: bool = False,
    ) -> MangaList:
        # mloader allows you to mix chapters and titles(collections of chapters)
        # This method tries to merge them while trying to avoid unnecessary
        # http requests
        if not any((title_ids, chapter_ids)):
            raise ValueError("Expected at least one title or chapter id")
        title_ids = set(title_ids or [])
        chapter_ids = set(chapter_ids or [])
        mangas = {}
        chapter_meta = namedtuple("ChapterMeta", "id name")
        for cid in chapter_ids:
            viewer = self._load_pages(cid)
            title_id = viewer.title_id
            # Fetching details for this chapter also downloads all other
            # visible chapters for the same title.
            if title_id in title_ids:
                title_ids.remove(title_id)
                mangas.setdefault(title_id, []).extend(
                    chapter_meta(c.chapter_id, c.name) for c in viewer.chapters
                )
            else:
                mangas.setdefault(title_id, []).append(
                    chapter_meta(viewer.chapter_id, viewer.chapter_name)
                )

        for tid in title_ids:
            details = self._get_title_details(tid)
            mangas[tid] = [
                chapter_meta(chapter.chapter_id, chapter.name)
                # Skipping mid_chapter_list, since it contains unavailable chapters
                for chapter in chain.from_iterable(
                    chain(group.first_chapter_list, group.last_chapter_list)
                    for group in details.chapter_list_group
                )
            ]

        for tid in mangas:
            if last_chapter:
                chapters = mangas[tid][-1:]
            else:
                chapters = [
                    c
                    for c in mangas[tid]
                    if min_chapter
                    <= (chapter_name_to_int(c.name) or 0)
                    <= max_chapter
                ]

            mangas[tid] = set(c.id for c in chapters)

        return mangas

    def _download(self, manga_list: MangaList, return_metadata: bool = False) -> List[dict]:
        """
        Download manga chapters and optionally return metadata.

        Args:
            manga_list: Dictionary mapping title IDs to sets of chapter IDs
            return_metadata: If True, collect and return metadata for each downloaded chapter

        Returns:
            List of chapter metadata dicts if return_metadata=True, empty list otherwise
        """
        downloaded_chapters = []
        manga_num = len(manga_list)

        for title_index, (title_id, chapters) in enumerate(manga_list.items(), 1):
            title = self._get_title_details(title_id).title
            title_name = title.name

            if not return_metadata:
                log.info(f"{title_index}/{manga_num}) Manga: {title_name}")
                log.info("    Author: %s", title.author)

            chapter_num = len(chapters)
            for chapter_index, chapter_id in enumerate(sorted(chapters), 1):
                viewer = self._load_pages(chapter_id)
                chapter = viewer.pages[-1].last_page.current_chapter
                next_chapter = viewer.pages[-1].last_page.next_chapter
                next_chapter = (
                    next_chapter if next_chapter.chapter_id != 0 else None
                )
                chapter_name = viewer.chapter_name

                if not return_metadata:
                    log.info(
                        f"    {chapter_index}/{chapter_num}) "
                        f"Chapter {chapter_name}: {chapter.sub_title}"
                    )

                # Collect metadata if requested
                if return_metadata:
                    chapter_info = {
                        "title_id": title_id,
                        "title_name": title_name,
                        "chapter_id": chapter_id,
                        "chapter_no": chapter_name,
                        "chapter_name": f"{chapter.sub_title}" if chapter.sub_title else chapter_name
                    }
                    downloaded_chapters.append(chapter_info)

                exporter = self.exporter(
                    title=title, chapter=chapter, next_chapter=next_chapter
                )
                pages = [
                    p.manga_page for p in viewer.pages if p.manga_page.image_url
                ]

                # Skip progressbar in JSON mode for clean output
                if return_metadata:
                    # Create a dummy progress bar that does nothing
                    class DummyPbar:
                        def update(self, *args, **kwargs): pass
                        def __enter__(self): return self
                        def __exit__(self, *args, **kwargs): pass
                    pbar = DummyPbar()
                else:
                    pbar = click.progressbar(
                        length=len(pages), label=chapter_name, show_pos=True
                    )
                with pbar:
                    page_counter = count()
                    futures = {}
                    completed_images = {}
                    next_to_write = 0

                    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
                        for page_number, (page_index, page) in enumerate(
                            zip(page_counter, pages)
                        ):
                            if PageType(page.type) == PageType.double:
                                page_index = range(page_index, next(page_counter))

                            if exporter.skip_image(page_index):
                                completed_images[page_number] = None
                                pbar.update(1)

                                while next_to_write in completed_images:
                                    completed_image = completed_images.pop(
                                        next_to_write
                                    )
                                    if completed_image is not None:
                                        image_index, image_blob = completed_image
                                        exporter.add_image(image_blob, image_index)
                                    next_to_write += 1
                                continue

                            future = executor.submit(
                                self._decrypt_image,
                                page.image_url,
                                page.encryption_key,
                            )
                            futures[future] = (page_number, page_index)

                        for future in as_completed(futures):
                            page_number, page_index = futures[future]
                            completed_images[page_number] = (
                                page_index,
                                future.result(),
                            )
                            pbar.update(1)

                            while next_to_write in completed_images:
                                completed_image = completed_images.pop(
                                    next_to_write
                                )
                                if completed_image is not None:
                                    image_index, image_blob = completed_image
                                    exporter.add_image(image_blob, image_index)
                                next_to_write += 1

                exporter.close()
        return downloaded_chapters

    def download(
        self,
        *,
        title_ids: Optional[Collection[int]] = None,
        chapter_ids: Optional[Collection[int]] = None,
        min_chapter: int,
        max_chapter: int,
        last_chapter: bool = False,
        return_metadata: bool = False,
    ) -> List[dict]:
        """
        Download manga chapters.

        Returns:
            List of chapter metadata dicts if return_metadata=True, empty list otherwise
        """
        manga_list = self._normalize_ids(
            title_ids, chapter_ids, min_chapter, max_chapter, last_chapter
        )
        return self._download(manga_list, return_metadata=return_metadata)
