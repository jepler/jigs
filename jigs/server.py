#!/usr/bin/python3

# SPDX-FileCopyrightText: 2023 Jeff Epler
#
# SPDX-License-Identifier: GPL-3.0-only

import functools
from aiohttp import web

import io
from diffusers import (
    StableDiffusionXLPipeline,
    EulerDiscreteScheduler,
    UNet2DConditionModel,
)
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
import torch
from PIL.PngImagePlugin import PngInfo
from chap.session import new_session
from chap.core import get_api
import click

FAST = False
MODEL_STEPS = 8
STEPS = 12  # STEPS
USE_UNET = True
elaborate_command = "chap -S {0} ask --no-print-prompt -n /dev/null {1}"

base = "stabilityai/stable-diffusion-xl-base-1.0"
repo = "ByteDance/SDXL-Lightning"


@functools.cache
def make_generator():
    print("loading model")
    if FAST:

        def generate(request_params):
            return open(
                "/usr/share/icons/gnome/32x32/places/xfce-trash_empty.png", "rb"
            ).read()
    else:
        if USE_UNET:
            ckpt = f"sdxl_lightning_{MODEL_STEPS}step_unet.safetensors"  # Use the correct ckpt for your step setting!

            # Load model.
            unet = UNet2DConditionModel.from_config(base, subfolder="unet").to(
                "cuda", torch.float16
            )
            unet.load_state_dict(load_file(hf_hub_download(repo, ckpt), device="cuda"))
            pipe = StableDiffusionXLPipeline.from_pretrained(
                base, unet=unet, torch_dtype=torch.float16, variant="fp16"
            ).to("cuda")

        else:
            ckpt = f"sdxl_lightning_{MODEL_STEPS}step_lora.safetensors"  # Use the correct ckpt for your step setting!

            pipe = StableDiffusionXLPipeline.from_pretrained(
                base, torch_dtype=torch.float16, variant="fp16"
            ).to("cuda")
            pipe.load_lora_weights(hf_hub_download(repo, ckpt))
            pipe.fuse_lora()
        pipe.enable_model_cpu_offload()

        # Ensure sampler uses "trailing" timesteps.
        pipe.scheduler = EulerDiscreteScheduler.from_config(
            pipe.scheduler.config, timestep_spacing="trailing"
        )

        default_metadata = {
            "base": base,
            "repo": repo,
            "ckpt": ckpt,
        }

        ctx = click.Context(click.Command("jigs-server"))
        chap_api = get_api(ctx)

        def generate(request_params):
            def maybe_add(kwargs, params, k, conv):
                v = params.get(k)
                if v is not None:
                    kwargs[k] = conv(v)

            metadata = PngInfo()
            for k, v in default_metadata.items():
                metadata.add_text(k, str(v))

            prompt = request_params.get("prompt")

            if elaborate_instruction := request_params.get("elaborate_instruction", ""):
                metadata.add_text("original_prompt", prompt)
                metadata.add_text("elaborate_instruction", elaborate_instruction)
                chap_session = new_session(elaborate_instruction)
                prompt = chap_api.ask(chap_session, prompt)

            metadata.add_text("prompt", prompt)

            kwargs = dict(
                num_inference_steps=STEPS,
                guidance_scale=0,
            )
            maybe_add(kwargs, request_params, "prompt_2", str)
            maybe_add(kwargs, request_params, "negative_prompt", str)
            maybe_add(kwargs, request_params, "negative_prompt_2", str)
            maybe_add(kwargs, request_params, "width", int)
            maybe_add(kwargs, request_params, "height", int)
            maybe_add(kwargs, request_params, "denoising_end", float)
            maybe_add(kwargs, request_params, "guidance_scale", float)

            image = pipe(prompt=prompt, **kwargs).images[0]

            with io.BytesIO() as output:
                image.save(output, format="png", pnginfo=metadata)
                contents = output.getvalue()

            return contents

    print("model loaded")
    return generate


def make_app():
    generate = make_generator()

    async def handle(request):
        request_params = await request.post()
        contents = generate(request_params)
        return web.Response(body=contents, content_type="image/png")

    app = web.Application()
    app.add_routes(
        [
            web.post("/generate", handle),
        ]
    )
    return app


def main():
    app = make_app()
    web.run_app(app, port=8072)
    print("returned from run_app, weird")


if __name__ == "__main__":
    main()
