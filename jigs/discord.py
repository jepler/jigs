#!/usr/bin/python

# SPDX-FileCopyrightText: 2023 Jeff Epler
#
# SPDX-License-Identifier: GPL-3.0-only

import asyncio
import io
import discord
from chap.key import get_key
import httpx
import hashlib
from discord.ext import commands

from .core import unsafe_chars

elaborate_instruction = "Elaborate each query into a more verbose prompt for image generation. Do not output any other text or commentary. Target length: 50 words"
width = 1024
height = 1024

# fast = True
fast = False


async def agenerate(prompt, negative_prompt=""):
    if fast:
        return (
            prompt,
            open(
                "/usr/share/icons/gnome/32x32/places/xfce-trash_empty.png", "rb"
            ).read(),
        )

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(
                "http://eric:8072/generate",
                data={
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "elaborate_instruction": elaborate_instruction,
                    # "width": width,
                    # "height": height,
                },
                timeout=360,
            )

            return (prompt, response.read())

        except Exception as e:
            return (f"Exception: {e}", None)


TOKEN = get_key("DISCORD_API_KEY")

intents = discord.Intents.default()
intents.typing = False
intents.presences = False
intents.messages = True
intents.message_content = True
intents.reactions = True

# client = discord.Client(intents=intents)

client = commands.Bot(command_prefix="$$", intents=intents)

regenerate = "🔁"
make_art = "🖼️"


@client.event
async def on_message(message):
    print("on_message")
    if message.author.bot:
        return
    content = message.content
    if content.startswith("!"):
        prompt = content[1:]
        await generate_common(message.channel, prompt)

    await client.process_commands(message)


async def generate_common(channel, prompt):
    async with channel.typing():
        prompt = prompt.strip()
        message = await channel.send(content=f"*thinking about {prompt}*")
        text_content, image_content = await agenerate(prompt)
        to_await = [message.edit(content=text_content)]

        if image_content:
            hash = hashlib.sha256(image_content).hexdigest()[:8]
            filename = f"{unsafe_chars.sub('-', prompt)[:96]}-{hash}.png"
            with io.BytesIO(image_content) as f:
                to_await.extend(
                    [
                        message.add_files(
                            discord.File(f, filename=filename, description=prompt)
                        ),
                        message.add_reaction(regenerate),
                    ]
                )
        return asyncio.gather(*to_await)


@client.event
async def on_raw_reaction_add(event):
    print("on_raw_reaction", event)
    if event.emoji.name in (regenerate, make_art) and not event.member.bot:
        guild = event.member.guild
        channel = await guild.fetch_channel(event.channel_id)
        message = await channel.fetch_message(event.message_id)
        print("->", message.content)
        await generate_common(channel, message.content.removeprefix("!"))


@client.hybrid_command(name="sync")
@commands.is_owner()
async def sync(ctx):
    print("syncing", ctx)
    await client.tree.sync()
    print("sync'd", ctx)


# @client.hybrid_command(name="gen", description="generate an image")
# async def gen(ctx, prompt: str):
#    await generate_common(ctx, prompt)

client.run(TOKEN)
