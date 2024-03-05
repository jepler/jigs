#!/usr/bin/python3

# SPDX-FileCopyrightText: 2023 Jeff Epler
#
# SPDX-License-Identifier: GPL-3.0-only

import io
import subprocess
import shlex
from diffusers import (
    StableDiffusionXLPipeline,
    EulerDiscreteScheduler,
    UNet2DConditionModel,
)
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
import torch
from bottle import request, response, route, run
from PIL.PngImagePlugin import PngInfo

STEPS = 8
USE_UNET = True
elaborate_command = 'chap -S {0} ask --no-print-prompt -n /dev/null {1}'

base = "stabilityai/stable-diffusion-xl-base-1.0"
repo = "ByteDance/SDXL-Lightning"
if USE_UNET:
    ckpt = f"sdxl_lightning_{STEPS}step_unet.safetensors" # Use the correct ckpt for your step setting!

    # Load model.
    unet = UNet2DConditionModel.from_config(base, subfolder="unet").to(
        "cuda", torch.float16
    )
    unet.load_state_dict(load_file(hf_hub_download(repo, ckpt), device="cuda"))
    pipe = StableDiffusionXLPipeline.from_pretrained(
        base, unet=unet, torch_dtype=torch.float16, variant="fp16"
    ).to("cuda")

else:
    ckpt = f"sdxl_lightning_{STEPS}step_lora.safetensors"  # Use the correct ckpt for your step setting!

    pipe = StableDiffusionXLPipeline.from_pretrained(base, torch_dtype=torch.float16, variant="fp16").to("cuda")
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

@route("/generate", method="ANY")
def generate():
    def maybe_add(kwargs, params, k, conv):
        v = params.get(k)
        if v is not None:
            kwargs[k] = conv(v)

    metadata = PngInfo()
    for k, v in default_metadata.items():
        metadata.add_text(k, str(v))

    prompt = request.params.get("prompt")
    
    if (elaborate_instruction := request.params.get("elaborate_instruction", "")):
        metadata.add_text("original_prompt", prompt)
        metadata.add_text("elaborate_instruction", elaborate_instruction)
        prompt = subprocess.check_output(
            elaborate_command.format(shlex.quote(elaborate_instruction), shlex.quote(prompt)),
            shell=True,
            encoding="utf-8",
            errors="replace",
        )

    metadata.add_text("prompt", prompt)

    kwargs = dict(
        num_inference_steps=STEPS,
        guidance_scale=0,
    )
    maybe_add(kwargs, request.params, "prompt_2", str)
    maybe_add(kwargs, request.params, "negative_prompt", str)
    maybe_add(kwargs, request.params, "negative_prompt_2", str)
    maybe_add(kwargs, request.params, "width", int)
    maybe_add(kwargs, request.params, "height", int)
    maybe_add(kwargs, request.params, "denoising_end", float)
    maybe_add(kwargs, request.params, "guidance_scale", float)

    image = pipe(prompt=prompt, **kwargs).images[0]

    with io.BytesIO() as output:
        image.save(output, format="png", pnginfo=metadata)
        contents = output.getvalue()

    response.content_type = "image/png"
    return contents


run(host="", port=8072, debug=True)
