# Mangaplus Downloader

![Python](https://img.shields.io/badge/python-v3.10+-blue.svg)
![License](https://img.shields.io/badge/license-GPLv3-blue.svg)

## **mloader** - download manga from mangaplus.shueisha.co.jp

Working fork of https://github.com/hurlenko/mloader/ with some [modifications](#-improvements), with future-proofing and performance in mind

## 🚩 Table of Contents

- [Installation](#-installation)
- [Usage](#-usage)
- [Command line interface](#%EF%B8%8F-command-line-interface)
- [Future-Proofing](#future-proofing)

## 💾 Installation

The recommended installation method is using `uv`:

```bash
uv tool install git+https://github.com/infernalsaber/mloader.git
```


If you prefer `pip`, you can still install it directly:

```bash
pip install git+https://github.com/infernalsaber/mloader.git
```

After installation, the `mloader` command will be available. Check the [command line](%EF%B8%8F-command-line-interface) section for supported commands.

## 📙 Usage

Copy the url of the chapter or title you want to download and pass it to `mloader`.

You can use `--title` and `--chapter` command line argument to download by title and chapter id.

You can download individual chapters or full title (but only available chapters).

Chapters can be saved as `CBZ` archives (default) or separate images by passing the `--raw` parameter.

## 🖥️ Command line interface

Currently `mloader` supports these commands

```
Usage: mloader [OPTIONS] [URLS]...

  Command-line tool to download manga from mangaplus

Options:
  --version                       Show the version and exit.
  -o, --out <directory>           Save directory (not a file)  [default:
                                  mloader_downloads]
  -r, --raw                       Save raw images  [default: False]
  -q, --quality [super_high|high|low]
                                  Image quality  [default: super_high]
  -s, --split                     Split combined images  [default: False]
  -c, --chapter INTEGER           Chapter id
  -t, --title INTEGER             Title id
  -b, --begin INTEGER RANGE       Minimal chapter to try to download
                                  [default: 0;x>=0]
  -e, --end INTEGER RANGE         Maximal chapter to try to download  [x>=1]
  -l, --last                      Download only the last chapter for title
                                  [default: False]
  --chapter-title                 Include chapter titles in filenames
                                  [default: False]
  --chapter-subdir                Save raw images in sub directory by chapter
                                  [default: False]
  --help                          Show this message and exit.
```

## 🔧 Improvements

- Generates `Session-Token` for MangaPlus access
- Mimics a browser's TLS fingerprint for future-proofing
- Uses multiple workers for faster downloads
- Overwritable configs incase of site changes
