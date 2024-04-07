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
        self.channel = payload.get('channel')
        self.artist = payload.get('artist')

    @property
    def path(self) -> Path:
        """Returns song absolute path"""
        return DOWNLOAD_DIR.joinpath(f'{self.id}.{self.ext}')

    def __str__(self) -> str:
        title = str(self.title) or 'Unknown title'
        source = self.artist or self.channel
        if source is None:
            pass
        elif source not in title:
            title = f'{source} - {title}'
        return title

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Song):
            return False
        return self.id == other.id


class Playlist:
    def __init__(self) -> None:
        self._queue: list[Song] = [None]
        self._ytdl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(DOWNLOAD_DIR.joinpath('%(id)s.%(ext)s')),
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

    def _download(self, query: str) -> list[Song]:
        """Downloads by query and saves it"""
        with YoutubeDL(self._ytdl_opts) as ytdl:
            data = ytdl.extract_info(query)
            if (e := data.get('entries')) is None:
                return [Song(data)]
            # TODO - handle playlists
            return [Song(e[0])]

    def add(self, query: str) -> list[Song]:
        """Downloads a song or playlist, adds it to queue, and returns it's object"""
        songs = self._download(query)
        self._queue.append(*songs)
        return songs

    def add_dummy(self) -> None:
        """Adds dummy entry for proper `next()` usage"""
        self._queue.append(None)

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
        """Clears queue and adds dummy entry"""
        self._queue.clear()
        self.add_dummy()

    @property
    def titles(self) -> list[str]:
        """Returns list of titles if songs in queue"""
        return [str(song) for song in filter(lambda x: isinstance(x, Song), self._queue)]


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
        if (song := self.playlist.next) is None:
            self.playlist.add_dummy()
            self._now_playing = None
            return
        self.bot.loop.create_task(self.play_song(song))

    async def play_song(self, song: Song) -> None:
        """Plays a song"""
        self._now_playing = song
        self.guild.voice_client.play(FFmpegOpusAudio(str(song.path)), after=self.play_next)

    def add_song(self, query: str) -> tuple[QueueState, list[Song]]:
        """Adds song to queue, starts playing if it's the first"""
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


