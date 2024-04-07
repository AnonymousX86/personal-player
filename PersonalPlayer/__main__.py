# -*- coding: utf-8 -*-
from logging import basicConfig, INFO, Logger

from discord import ApplicationContext, Bot, CustomActivity, VoiceChannel
from discord.ext.commands import check, is_owner
from rich.logging import RichHandler

from .audio import AudioController, Playlist
from .errors import NotConnected, NotPlaying
from .logger import log
from .settings import BOT_TOKEN
from .utils import remove_ansi


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

        state, new_songs = audio.add_songs(query)

        if not (l := len(new_songs)):
            msg = 'No tracks added...?'
        msg = f'Added **{l}** track{'s' if l > 1 else ''}. {state.value}: **{new_songs[0]}**'
        if url := new_songs[0].url:
            msg += f' *<{url}>*'
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
        # datefmt='[%Y-%m-%d]',
        handlers=[RichHandler(
            omit_repeated_times=False,
            markup=True,
            rich_tracebacks=True
        )]
    )
    main(log)
