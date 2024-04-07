# -*- coding: utf-8 -*-
from enum import Enum
from pathlib import Path

from discord import Bot, FFmpegOpusAudio, Guild
from yt_dlp import YoutubeDL

from .logger import log
from .settings import DOWNLOAD_DIR


class QueueState(Enum):
    NOW_PLAYING = 'Now playing'
    QUEUED = 'Queued'


class Song:
    def __init__(self, payload: dict) -> None:
        self.id = payload.get('id')
        self.title = payload.get('title')
        self.url = payload.get('webpage_url')
        self.ext = payload.get('ext')

    @property
    def path(self) -> Path:
        """Returns song absolute path"""
        return DOWNLOAD_DIR.joinpath(f'{self.title} [{self.id}].{self.ext}')

    def __str__(self) -> str:
        return self.title

    def __repr__(self) -> str:
        return f'Song<{self.title} [{self.id}]>'

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Song):
            return False
        return self.id == other.id


class Playlist:
    def __init__(self) -> None:
        self._queue: list[Song] = []
        self._ytdl_opts = {
            'format': 'bestaudio',
            'outtmpl': str(DOWNLOAD_DIR.joinpath('%(title)s [%(id)s].%(ext)s')),
            'verbose': True,
            'cookies_from_browser': 'edge',
            'noplaylist': True,
            'default_search': 'ytsearch',
            'logger': log,
            'noprogress': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'web']
                }
            }
        }

    @property
    def queue(self) -> list[Song]:
        return self._queue

    @property
    def current(self) -> Song:
        try:
            return self._queue[0]
        except IndexError:
            return None

    def _download(self, query: str) -> list[Song]:
        """Downloads by query and saves it"""
        with YoutubeDL(self._ytdl_opts) as ytdl:
            data = ytdl.extract_info(query, download=True)
            if (e := data.get('entries')) is None:
                return [Song(data)]
            return [Song(f) for f in e]

    def add(self, query: str) -> list[Song]:
        """Downloads a song or playlist, adds it to queue, and returns its object"""
        songs = self._download(query)
        self._queue.extend(songs)
        return songs

    @property
    def next(self) -> Song | None:
        """Returns next song and shifts queue"""
        try:
            self._queue.pop(0)
            return self._queue[0]
        except IndexError:
            return None

    def remove(self, index: int) -> None:
        """Removes song by index"""
        self._queue.pop(index)

    def clear(self) -> None:
        """Clears queue"""
        self._queue.clear()

    @property
    def titles(self) -> list[str]:
        """Returns list of titles if songs in queue"""
        return [str(song) for song in self._queue]


class AudioController:
    def __init__(self, bot: Bot, playlist: Playlist, guild: Guild) -> None:
        self.bot = bot
        self.playlist = playlist
        self.guild = guild
        self._now_playing: Song = None

    @property
    def now_playing(self) -> Song:
        """Returns now playing song"""
        return self._now_playing

    def play_next(self, error: Exception = None) -> None:
        """Runs after a song is over and play next if there is"""
        if error:
            raise error
        # Queue has not been started or skipped
        if self._now_playing is None:
            if not (current := self.playlist.current):
                raise RuntimeError('Queue is empty')
            song = current
        elif (next := self.playlist.next) is None:
            self._now_playing = None
            return
        else:
            song = next
        self.bot.loop.create_task(self.play_song(song))

    async def play_song(self, song: Song) -> None:
        """Plays a song"""
        self._now_playing = song
        self.guild.voice_client.play(FFmpegOpusAudio(str(song.path)), after=self.play_next)

    def add_songs(self, query: str) -> tuple[QueueState, list[Song]]:
        """Adds songs to queue, starts playing if it's the first"""
        new_songs = self.playlist.add(query)
        if not self.guild.voice_client.is_playing():
            self.play_next()
            status = QueueState.NOW_PLAYING
        else:
            status = QueueState.QUEUED
        return status, new_songs

    def skip(self) -> None:
        """Skips current song"""
        self.guild.voice_client.stop()
        self.play_next()

    def pause(self) -> bool:
        """Switches playing state, returns `True` if pasued and `False` if resumed"""
        if (vc := self.guild.voice_client).is_playing():
            vc.pause()
            return True
        vc.resume()
        return False

    def stop(self) -> None:
        """Stops playing and cleares queue"""
        if (vc := self.guild.voice_client).is_playing():
            vc.pause()
        self.playlist.clear()


