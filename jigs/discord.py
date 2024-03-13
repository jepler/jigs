#!/usr/bin/python

# SPDX-FileCopyrightText: 2023 Jeff Epler
#
# SPDX-License-Identifier: GPL-3.0-only

import asyncio
import io
import discord
from chap.key import get_key
import httpx

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

client = discord.Client(intents=intents)

regenerate = "🔁"


@client.event
async def on_message(message):
    print("on_message")
    if message.author.bot:
        return
    content = message.content
    if content.startswith("!"):
        prompt = content[1:]
        await generate_common(message.channel, prompt)


async def generate_common(channel, prompt):
    message = await channel.send(content=f"JIGS is now rendering: {prompt}")
    text_content, image_content = await agenerate(prompt)
    to_await = [message.edit(content=text_content)]

    if image_content:
        with io.BytesIO(image_content) as f:
            to_await.extend(
                [
                    message.add_files(
                        discord.File(f, filename="jigs-image.png", description=prompt)
                    ),
                    message.add_reaction(regenerate),
                ]
            )
    return asyncio.gather(*to_await)


@client.event
async def on_reaction_add(reaction, user):
    print("on_reaction")
    print(reaction.emoji, str(reaction), repr(reaction))
    message = reaction.message
    print(message.author.id, client.user.id)
    print(reaction.emoji == regenerate)
    print(str(reaction.emoji) == regenerate)
    if (
        message.author.id == client.user.id
        and reaction.emoji == regenerate
        and reaction.count > 1
    ):
        await generate_common(message.channel, message.content)


@client.event
async def on_raw_reaction_add(*args):
    print("on_raw_reaction", args)


client.run(TOKEN)
