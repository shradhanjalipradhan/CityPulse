"""
deploy.py — Deploys the CityPulse inference server to HuggingFace Spaces.

Steps:
  1. Copies trained model files from models/saved_models/ into huggingface_space/models/
  2. Uploads the entire huggingface_space/ directory to the HF Space repo

Usage:
  python huggingface_space/deploy.py

Requires:
  pip install huggingface_hub
  HF_TOKEN, HF_USERNAME, HF_SPACE_NAME in .env
"""

import logging
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
SAVED_MODELS_DIR = PROJECT_ROOT / "models" / "saved_models"
SPACE_DIR = PROJECT_ROOT / "huggingface_space"
SPACE_MODELS_DIR = SPACE_DIR / "models"

HF_TOKEN = os.environ["HF_TOKEN"]
HF_USERNAME = os.environ["HF_USERNAME"]
HF_SPACE_NAME = os.environ["HF_SPACE_NAME"]
REPO_ID = f"{HF_USERNAME}/{HF_SPACE_NAME}"


def copy_model_files() -> int:
    """Copies .pt and .pkl files from saved_models/ into huggingface_space/models/.

    Returns:
        Number of files copied.
    """
    SPACE_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src in SAVED_MODELS_DIR.glob("*"):
        if src.suffix in (".pt", ".pkl"):
            dst = SPACE_MODELS_DIR / src.name
            shutil.copy2(src, dst)
            logger.info("Copied: %s → %s", src.name, dst)
            copied += 1
    return copied


def push_to_huggingface() -> None:
    """Uploads the huggingface_space/ directory to HuggingFace Spaces."""
    try:
        from huggingface_hub import HfApi
    except ImportError:
        logger.error("huggingface_hub not installed. Run: pip install huggingface_hub")
        sys.exit(1)

    api = HfApi()
    logger.info("Uploading to HuggingFace Space: %s", REPO_ID)

    api.upload_folder(
        folder_path=str(SPACE_DIR),
        repo_id=REPO_ID,
        repo_type="space",
        token=HF_TOKEN,
        commit_message="Deploy CityPulse inference server",
        ignore_patterns=["__pycache__", "*.pyc", ".DS_Store"],
    )
    logger.info("Upload complete.")
    print(f"\nSpace URL: https://huggingface.co/spaces/{REPO_ID}")
    print(f"API URL:   https://{HF_USERNAME}-{HF_SPACE_NAME}.hf.space")


if __name__ == "__main__":
    print("=" * 60)
    print("CityPulse — HuggingFace Spaces Deploy")
    print("=" * 60)

    # Step 1 — copy model files
    print("\n[1/2] Copying model files into huggingface_space/models/...")
    n = copy_model_files()
    if n == 0:
        print("  WARNING: No model files found in models/saved_models/")
        print("  Run 'python models/train_models.py' first to generate models.")
        sys.exit(1)
    print(f"  Copied {n} files.")

    # Step 2 — push to HF
    print(f"\n[2/2] Pushing to HuggingFace Space '{REPO_ID}'...")
    push_to_huggingface()
    print("\nDeploy complete.")
