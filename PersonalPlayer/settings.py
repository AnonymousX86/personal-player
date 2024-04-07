# -*- coding: utf-8 -*-
from os import getenv
from pathlib import Path


BOT_TOKEN = getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise RuntimeError('Missing bot token!')

DOWNLOAD_DIR = Path(getenv('DOWNLOAD_DIR', 'download')).resolve()
if not DOWNLOAD_DIR.exists():
    DOWNLOAD_DIR.mkdir(755)
elif not DOWNLOAD_DIR.is_dir():
    raise RuntimeError('DOWNLOAD_DIR must be a directory!')
