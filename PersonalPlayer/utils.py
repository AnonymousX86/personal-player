# -*- coding: utf-8 -*-
from re import compile


def remove_ansi(text: str) -> str:
    """Removes ANSI ascape codes and returns clean one"""
    escape = compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return escape.sub('', text)
