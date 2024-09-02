#!/usr/bin/python

# SPDX-FileCopyrightText: 2023 Jeff Epler
#
# SPDX-License-Identifier: GPL-3.0-only

from aiohttp import web
import asyncio
import io
import discord
from chap.key import get_key
import httpx
import hashlib
from discord.ext import commands
from rich.table import Table
from rich.console import Console
from PIL import Image

from .core import unsafe_chars
from .server import make_app

import logging

logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


elaborate_instruction = "Elaborate each query into a more verbose prompt for image generation. Do not output any other text or commentary. Target length: 50 words"
width = 1024
height = 1024


async def agenerate(prompt, negative_prompt=""):
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

discord_bot = commands.Bot(command_prefix="$$", intents=intents)

regenerate = "🔁"
make_art = "🖼️"


@discord_bot.event
async def on_message(message):
    if message.author.bot:
        return
    content = message.content
    if content.startswith("!"):
        prompt = content[1:]
        await generate_common(message.channel, prompt)

    await discord_bot.process_commands(message)


async def generate_common(channel, prompt):
    async with channel.typing():
        prompt = prompt.strip()
        message = await channel.send(content=f"*thinking about {prompt}*")
        text_content, image_content = await agenerate(prompt)
        to_await = [message.edit(content=text_content)]

        if image_content:
            hash = hashlib.sha256(image_content).hexdigest()[:8]
            filename = f"{unsafe_chars.sub('-', prompt)[:96]}-{hash}.png"
            with io.BytesIO(image_content) as f, io.StringIO() as out:
                table = Table(show_header=False, box=None, pad_edge=False)
                table.add_column("k", justify="left", no_wrap=True)
                table.add_column("v", justify="left")
                img = Image.open(f)
                for k, v in img.info.items():
                    table.add_row(k, str(v))
                console = Console(file=out, width=72)
                console.print(table)
                table_content = out.getvalue()
            with io.BytesIO(image_content) as f, io.BytesIO(
                table_content.encode("utf-8")
            ) as df:
                to_await.extend(
                    [
                        message.add_files(
                            discord.File(f, filename=filename, description=prompt),
                            discord.File(
                                df,
                                filename=f"{filename}.txt",
                                description="generation details",
                            ),
                        ),
                        message.add_reaction(regenerate),
                    ]
                )

        return asyncio.gather(*to_await)


@discord_bot.event
async def on_raw_reaction_add(event):
    print(type(event), event, discord_bot.application_id)
    if event.member and event.member.bot:
        return
    if event.user_id == discord_bot.application_id:
        return
    if event.emoji.name in (regenerate, make_art):
        # guild = event.member.guild
        # channel = await guild.fetch_channel(event.channel_id)
        channel = discord_bot.get_channel(event.channel_id)
        if channel is None:
            channel = await discord_bot.fetch_channel(event.channel_id)
        message = await channel.fetch_message(event.message_id)
        print(message)
        await generate_common(channel, message.content.removeprefix("!"))


@discord_bot.hybrid_command(name="sync")
@commands.is_owner()
async def sync(ctx):
    print("syncing", ctx)
    await discord_bot.tree.sync()
    print("sync'd", ctx)


# @discord_bot.hybrid_command(name="gen", description="generate an image")
# async def gen(ctx, prompt: str):
#    await generate_common(ctx, prompt)


def main():
    discord_key = web.AppKey("discord", asyncio.Task[None])

    async def background_tasks(app):
        async with discord_bot:
            app[discord_key] = asyncio.create_task(discord_bot.start(TOKEN))

            yield

            app[discord_key].cancel()
            await app[discord_key]

    # generator = make_generator() # TODO: have discord bot directly call generator
    app = make_app()

    app.cleanup_ctx.append(background_tasks)
    web.run_app(app, port=8072)


if __name__ == "__main__":
    main()
