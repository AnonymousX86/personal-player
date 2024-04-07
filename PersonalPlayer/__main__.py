# -*- coding: utf-8 -*-
from enum import Enum
from logging import basicConfig, getLogger, INFO, Logger
from os import getenv
from pathlib import Path
from re import compile

from discord import ApplicationContext, Bot, CustomActivity, FFmpegOpusAudio, Guild, VoiceChannel
from discord.ext.commands import check, CheckFailure, is_owner
from rich.logging import RichHandler
from yt_dlp import YoutubeDL


BOT_TOKEN = getenv('BOT_TOKEN')
DOWNLOAD_DIR = Path('download').resolve()


class NotConnected(CheckFailure):
    pass


class NotPlaying(CheckFailure):
    pass


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

    def _download(self, query: str) -> list[Song]:
        """Downloads by query and saves it to returned `Path`"""
        print(f'Requested download: {query}')

        with YoutubeDL({
            'format': 'bestaudio/best',
            'outtmpl': str(DOWNLOAD_DIR.joinpath('%(id)s.%(ext)s')),
            'default_search': 'ytsearch',
            'no_playlist': True,
            'logger': getLogger('rich')
        }) as ytdl:
            data = ytdl.extract_info(query)
            songs = []
            if data.get('_type') == 'playlist':
                for entry in data.get('entries'):
                    songs.append(Song(entry))
            else:
                songs.append(Song(data))
            return songs

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

    async def add_song(self, query: str) -> tuple[QueueState, list[Song]]:
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


def remove_ansi(text: str) -> str:
    """Removes ANSI ascape codes and returns clean one"""
    escape = compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return escape.sub('', text)


def is_connected() -> check:
    async def predicate(ctx: ApplicationContext) -> bool:
        if ctx.guild.voice_client is None:
            raise NotConnected('I\'m not connected anywhere')
        return True
    return check(predicate)


def is_playing() -> check:
    async def predicate(ctx: ApplicationContext) -> bool:
        if not (vc := ctx.guild.voice_client):
            raise NotConnected('I\'m not connected anywhere')
        if not vc.is_playing():
            raise NotPlaying('I\'m not playing anything')
        return True
    return check(predicate)


def main(log: Logger):
    bot = Bot(
        owner_id=309270832683679745,
        activity=CustomActivity(
            name='Słucha swojego pana'
        )
    )
    audio_controllers: dict[int, AudioController] = {}

    async def get_audio(guild_id: int) -> AudioController:
        """Returns audio controller from specific guild, creates a new one if necessary"""
        if (audio := audio_controllers.get(guild_id)) is None:
            new_audio = AudioController(bot, Playlist(), await bot.fetch_guild(guild_id))
            audio_controllers[guild_id] = new_audio
            return new_audio
        return audio

    @bot.event
    async def on_ready() -> None:
        log.info(f'{bot.user} is ready and online!')

    @bot.slash_command(name = 'ping', description = 'Test the bot')
    async def ping(ctx: ApplicationContext) -> None:
        await ctx.respond(f'Pong! Latency: **{int(bot.latency * 1000)}ms**.')

    @bot.slash_command(name='sync', description='Forces commands synchronization')
    @is_owner()
    async def sync(ctx: ApplicationContext) -> None:
        log.info(f'Syncing commands in {ctx.guild.name} ({ctx.guild_id})')
        await bot.sync_commands(guild_ids=[ctx.guild_id])
        await ctx.respond('Done.')

    @bot.slash_command(name='play', description='Play something in current voice channel')
    async def play(ctx: ApplicationContext, query: str) -> None:
        # Check if requester is in any voice channel
        if not ctx.author.voice.channel:
            await ctx.respond('OK, playing for myself.')
            return

        # Make sure target channel is not Stage
        if not isinstance(member_channel := ctx.author.voice.channel, VoiceChannel):
            await ctx.respond(f'It\'s impossible to connect to **{member_channel.name}**.')
            return

        res = await ctx.respond('Please wait...')

        # Bot is not connected, so connect to memebr directly
        if not (client := ctx.guild.voice_client):
            client = await member_channel.connect()

        # Bot is connected somewhere else, so move to member
        if member_channel.id != client.channel.id:
            await client.move_to(member_channel)

        # Get audio controller for specific guild
        audio = await get_audio(ctx.guild_id)
        state, new_songs = await audio.add_song(query)

        if (l := len(new_songs)) > 1:
            msg = f'Added **{l}** tracks.'
        else:
            msg = f'{state.value}: **{new_songs[0]}**'
            if url := new_songs[0].url:
                msg += f'\n*<{url}>*'
        await res.edit(content=msg)

    @play.error
    async def play_error(ctx: ApplicationContext, error: Exception):
        while ((parent := error.__cause__) is not None):
            error = parent
        await ctx.edit(content=f'During adding the song, an error heppened:```\n{remove_ansi(str(error))}\n```')

    @bot.slash_command(name='queue', description='Preview next songs')
    @is_playing()
    async def queue(ctx: ApplicationContext) -> None:
        audio = await get_audio(ctx.guild_id)
        if not len(titles := audio.playlist.titles):
            await ctx.respond('Queue is empty.')
            return
        res = ''
        for i, title in enumerate(titles):
            res += f'{i + 1}. {title}\n'
        await ctx.respond(res)

    @bot.slash_command(name='skip', description='Skips current song')
    @is_playing()
    async def skip(ctx: ApplicationContext) -> None:
        audio = await get_audio(ctx.guild_id)
        now_playing = audio.now_playing
        audio.skip()
        await ctx.respond(f'Skipping **{now_playing}**.' if now_playing else 'I\'m not playing anything.')

    @bot.slash_command(name='pause', description='Switches pause and unpasue')
    @is_playing()
    async def pause(ctx: ApplicationContext) -> None:
        audio = await get_audio(ctx.guild_id)
        is_paused = audio.pause()
        await ctx.respond('Paused.' if is_paused else 'Resumed.')

    @bot.slash_command(name='stop', description='Stops playing and clears queue')
    @is_playing()
    async def stop(ctx: ApplicationContext) -> None:
        audio = await get_audio(ctx.guild_id)
        audio.stop()
        await ctx.respond('Stopped playing and cleared queue.')

    @queue.error
    @skip.error
    @pause.error
    @stop.error
    async def playing_common_error(ctx: ApplicationContext, error: Exception):
        if isinstance(error, NotConnected):
            await ctx.respond(error)
        elif isinstance(error, NotPlaying):
            await ctx.respond(error)

    bot.run(BOT_TOKEN)


if __name__ == '__main__':
    basicConfig(
        level=INFO,
        format='%(message)s',
        datefmt='[%x]',
        handlers=[RichHandler(rich_tracebacks=True)]
    )
    log = getLogger('rich')
    main(log)
