"""
Lightweight Standalone GPU Inpainting Server for FastTypeR
Pure PyTorch TorchScript implementation of Anime-LaMa / Big-LaMa.
Zero external logging dependencies - uses standard logging, torch, torchvision, PIL, and FastAPI.
"""

import io
import os
import base64
import logging
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image
import torch
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("InpaintingServer")

app = FastAPI(title="FastTypeR Pure PyTorch Inpainting Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ANIME_LAMA_URL = "https://github.com/Sanster/models/releases/download/AnimeMangaInpainting/anime-manga-big-lama.pt"
BIG_LAMA_URL = "https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt"

_lama_model = None
_device = "cuda" if torch.cuda.is_available() else "cpu"


def ensure_lama_model_exists(models_dir: Path = None) -> Path:
    if models_dir is None:
        models_dir = Path(__file__).resolve().parent.parent / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    candidates = [
        models_dir / "anime-manga-big-lama.pt",
        models_dir / "anime-lama.pt",
        models_dir / "big-lama.pt",
        Path.home() / ".cache" / "torch" / "hub" / "checkpoints" / "anime-manga-big-lama.pt",
        Path.home() / ".cache" / "torch" / "hub" / "checkpoints" / "big-lama.pt",
    ]
    for c in candidates:
        if c.exists() and c.stat().st_size > 1000000:
            return c

    dest = models_dir / "anime-manga-big-lama.pt"
    logger.info(f"Downloading Anime-LaMa Inpainting model to {dest}...")
    try:
        urllib.request.urlretrieve(ANIME_LAMA_URL, str(dest))
    except Exception as e:
        logger.warning(f"Failed to download Anime-LaMa ({e}), trying fallback...")
        urllib.request.urlretrieve(BIG_LAMA_URL, str(dest))

    logger.info("Inpainting model downloaded successfully!")
    return dest


def get_lama_engine():
    global _lama_model
    if _lama_model is None:
        model_path = ensure_lama_model_exists()
        logger.info(f"Loading TorchScript LaMa Model ({model_path.name}) onto {_device}...")
        try:
            _lama_model = torch.jit.load(str(model_path), map_location=_device)
            _lama_model.eval()
            logger.info(f"LaMa GPU Inpainting Engine is READY on {_device.upper()}!")
        except Exception as e:
            logger.error(f"Error loading TorchScript model: {e}")
            raise e
    return _lama_model


def inpaint_image_lama(image: Image.Image, mask: Image.Image) -> Image.Image:
    orig_w, orig_h = image.size
    model = get_lama_engine()

    pad_w = (8 - orig_w % 8) % 8
    pad_h = (8 - orig_h % 8) % 8

    img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
    mask_np = np.array(mask.convert("L")).astype(np.float32) / 255.0
    mask_np = (mask_np > 0).astype(np.float32)

    if pad_w > 0 or pad_h > 0:
        img_np = np.pad(img_np, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")
        mask_np = np.pad(mask_np, ((0, pad_h), (0, pad_w)), mode="edge")

    img_tensor = torch.from_numpy(img_np).permute(2, 0, 1).unsqueeze(0).to(_device)
    mask_tensor = torch.from_numpy(mask_np).unsqueeze(0).unsqueeze(0).to(_device)

    with torch.no_grad():
        out_tensor = model(img_tensor, mask_tensor)

    out_np = out_tensor[0].permute(1, 2, 0).detach().cpu().numpy()
    out_np = np.clip(out_np * 255.0, 0, 255).astype(np.uint8)

    out_img = Image.fromarray(out_np)
    if pad_w > 0 or pad_h > 0:
        out_img = out_img.crop((0, 0, orig_w, orig_h))

    return out_img


@app.get("/")
@app.get("/api/v1/model")
def get_active_model():
    return {
        "name": "anime-lama",
        "model": "anime-lama",
        "device": _device,
        "status": "online"
    }


@app.post("/api/v1/model")
def switch_model(req: dict = None):
    return {"name": "anime-lama", "status": "switched"}


@app.post("/api/v1/inpaint")
async def inpaint_handler(request: Request):
    data = await request.json()
    raw_img_b64 = data.get("image", "")
    raw_mask_b64 = data.get("mask", "")

    if "," in raw_img_b64:
        raw_img_b64 = raw_img_b64.split(",", 1)[-1]
    if "," in raw_mask_b64:
        raw_mask_b64 = raw_mask_b64.split(",", 1)[-1]

    img_bytes = base64.b64decode(raw_img_b64)
    mask_bytes = base64.b64decode(raw_mask_b64)

    pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    pil_mask = Image.open(io.BytesIO(mask_bytes)).convert("L")

    result_img = inpaint_image_lama(pil_img, pil_mask)

    out_buffer = io.BytesIO()
    result_img.save(out_buffer, format="PNG")
    out_bytes = out_buffer.getvalue()

    headers = {"ngrok-skip-browser-warning": "true"}
    return Response(content=out_bytes, media_type="image/png", headers=headers)


if __name__ == "__main__":
    get_lama_engine()
    uvicorn.run(app, host="127.0.0.1", port=8088, log_level="warning")
