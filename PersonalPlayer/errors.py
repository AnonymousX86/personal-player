# -*- coding: utf-8 -*-
from discord.ext.commands import CheckFailure


class NotConnected(CheckFailure):
    pass


class NotPlaying(CheckFailure):
    pass
