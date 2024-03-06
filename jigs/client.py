#!/usr/bin/python

# SPDX-FileCopyrightText: 2023 Jeff Epler
#
# SPDX-License-Identifier: GPL-3.0-only

import hashlib
import io
import json
import re
import subprocess
import urllib

import httpx
from PIL import Image

from rich.console import Console
from rich.table import Table

import click

unsafe_chars = re.compile(r"[^a-zA-Z0-9-_]+")


@click.command
@click.option(
    "--negative-prompt",
    type=str,
    default="",
    help="Negative prompt",
)
@click.option(
    "--steps",
    type=int,
    default=50,
    help="Inference steps",
)
@click.option(
    "--no-elaborate",
    "elaborate_instruction",
    flag_value="",
    help="Disable prompt elaboration, equivalent to --elaborate-instruction=''.",
)
@click.option(
    "--elaborate-instruction",
    type=str,
    # default="echo {}",
    default="Elaborate each query into a more verbose prompt for image generation. Do not output any other text or commentary. Target length: 50 words",
    help="Used as the instruction to some LLM (evaluated on the server side) to elaborate the prompt. If the elaborate instruction is empty, no elaboration is performed.",
)
@click.option(
    "--size",
    type=str,
    default="1024x1024",
    help="Valid values include 512x512, 768x768 or 1024x1024, depending on the model",
)
@click.option(
    "--action",
    type=str,
    default="firefox",
    help="Executable program to run on each image (e.g., open, firefox)",
)
@click.option(
    "--url",
    type=str,
    envvar="JIGS_URL",
    metavar="URL",
    default="http://localhost:8072",
    help="The URL of the server. Defaults to the content of the environment variable JIGS_URL. If JIGS_URL is unset, defaults to http://localhost:8072",
)
@click.argument("qstr", nargs=-1, required=False)
def main(size, steps, action, negative_prompt, elaborate_instruction, url, qstr=[]):
    if qstr:
        prompt = " ".join(qstr)
    else:
        prompt = input("Image description: ")

    width, height = map(int, size.split("x"))

    response = httpx.post(
        urllib.parse.urljoin(url, "generate"),
        data={
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "elaborate_instruction": elaborate_instruction,
            "width": width,
            "height": height,
            "num_inference_steps": steps,
        },
        timeout=360,
    )

    if response.status_code != 200:
        try:
            j = response.json()
            raise SystemExit(
                f"Failure {j['error']['message']} ({response.status_code})"
            )
        except (KeyError, IndexError, json.decoder.JSONDecodeError):
            raise SystemExit(f"Failure {response.text} ({response.status_code})")

    try:
        data = response.read()
        hash = hashlib.sha256(data).hexdigest()[:8]
        filename = f"{unsafe_chars.sub('-', prompt)[:96]}-{hash}.png"
        print(f"Saving to {filename}")
        with open(filename, "wb") as f:
            f.write(data)

        with io.BytesIO(data) as f:
            table = Table(show_header=False, box=None, pad_edge=False)
            table.add_column("k", justify="left", no_wrap=True)
            table.add_column("v", justify="left")
            img = Image.open(f)
            for k, v in img.info.items():
                table.add_row(k, v)
            console = Console()
            console.print(table)

        if action:
            subprocess.run([action, filename])

    except (KeyError, IndexError, json.decoder.JSONDecodeError):
        raise SystemExit(f"Failure {response.text} ({response.status_code})")


if __name__ == "__main__":
    main()
