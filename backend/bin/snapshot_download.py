import sys, os
import logging
from pathlib import Path
from typing import Optional

# Add project root to Python path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.core.config import settings
from huggingface_hub import snapshot_download
from pyannote.audio import Pipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def download_model(repo_id: str, local_dir: str, token: Optional[str] = None) -> str:
    """Download a model from Hugging Face Hub.
    
    Args:
        repo_id: Repository ID on Hugging Face Hub
        local_dir: Local directory to save the model
        token: Hugging Face authentication token (if required)
        
    Returns:
        str: Path to the downloaded model
    """
    try:
        local_path = Path(local_dir)
        local_path.mkdir(parents=True, exist_ok=True)
        
        if not os.access(local_path, os.W_OK):
            raise PermissionError(f"No write permissions for directory: {local_path}")
        
        logger.info(f"Downloading model {repo_id} to {local_path}...")
        
        if "pyannote" in repo_id:
            logger.info("Using pyannote.audio Pipeline for model download...")
            Pipeline.from_pretrained(repo_id, use_auth_token=token, cache_dir=local_path)
            model_path = local_path / f"models--{repo_id.replace('/', '--')}"
        else:
            model_path = snapshot_download(repo_id, token=token, cache_dir=local_path)
        
        logger.info(f"Successfully downloaded model to {model_path}")
        return str(model_path)
        
    except Exception as e:
        logger.error(f"Failed to download model: {str(e)}")
        raise

def verify_model(local_dir: str) -> bool:
    """Verify that the model was downloaded correctly."""
    try:
        local_path = Path(local_dir)
        
        if "models--pyannote" in str(local_path):
            blob_files = list((local_path / "blobs").glob("*"))
            if not blob_files:
                logger.error(f"No model blob files found in {local_path}/blobs")
                return False
            logger.info(f"Found {len(blob_files)} model blob files in cache")
            return True
            
        model_files = list(local_path.rglob("pytorch_model*.bin")) + \
                     list(local_path.rglob("*.safetensors")) + \
                     list(local_path.rglob("*.pt")) + \
                     list(local_path.rglob("*.pth"))
        
        if not model_files:
            logger.error(f"No model weight files found in {local_dir} or its subdirectories")
            return False
            
        logger.info(f"Found model files in {local_dir}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to verify model: {str(e)}")
        return False

def main():
    """Download and verify the model."""
    try:
        if not settings.PYANNOTE_SEGMENTATION_MODEL:
            raise ValueError("PYANNOTE_SEGMENTATION_MODEL is not set in settings")
            
        local_dir = str(settings.intermediate_folder_path / "pyannote-models")
        os.makedirs(local_dir, exist_ok=True)
        logger.info(f"Model will be downloaded to: {local_dir}")
        
        model_path = download_model(
            repo_id=settings.PYANNOTE_SEGMENTATION_MODEL,
            local_dir=local_dir,
            token=settings.HUGGINGFACE_TOKEN or None
        )
        
        if verify_model(model_path):
            logger.info("Model download and verification completed successfully")
            return True
            
        logger.error("Model verification failed")
        return False
            
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        raise

if __name__ == "__main__":
    main()
