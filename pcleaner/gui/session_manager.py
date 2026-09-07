import json
from pathlib import Path
from typing import Optional, Any
from loguru import logger
import pcleaner.gui.image_file as imf
import pcleaner.output_structures as ost

SESSION_FILE_NAME = "pcleaner_session.json"

def save_session(image_files: list[imf.ImageFile], session_dir: Path) -> bool:
    """
    Save the current processing session to a JSON file.
    
    :param image_files: List of image files in the current session.
    :param session_dir: The directory where the session should be saved (usually the cache dir).
    :return: True if saved successfully, False otherwise.
    """
    session_data = []
    for image in image_files:
        analytics_dict = {}
        if image.analytics_data:
            for cat in ost.ImageAnalyticCategory:
                analytics_dict[cat.name] = image.analytics_data.get_category(cat)
                
        data = {
            "path": str(image.path),
            "export_path": str(image.export_path) if image.export_path else None,
            "split_from": str(image.split_from) if image.split_from else None,
            "uuid": image.uuid,
            "canceled": image.canceled,
            "analytics_data": analytics_dict
        }
        session_data.append(data)
        
    session_path = session_dir / SESSION_FILE_NAME
    try:
        with open(session_path, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=4)
        logger.info(f"Session saved to {session_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save session: {e}")
        return False

def load_session(session_dir: Path) -> Optional[list[dict[str, Any]]]:
    """
    Load the session data from a JSON file.
    
    :param session_dir: The directory where the session file is expected.
    :return: The loaded session data list, or None if no session exists or it fails.
    """
    session_path = session_dir / SESSION_FILE_NAME
    if not session_path.is_file():
        return None
        
    try:
        with open(session_path, "r", encoding="utf-8") as f:
            session_data = json.load(f)
        logger.info(f"Session loaded from {session_path}")
        return session_data
    except Exception as e:
        logger.error(f"Failed to load session: {e}")
        return None

def has_session(session_dir: Path) -> bool:
    """
    Check if a saved session file exists.
    """
    return (session_dir / SESSION_FILE_NAME).is_file()

def apply_session_data_to_images(
    session_data: list[dict[str, Any]], 
    image_files_dict: dict[Path, imf.ImageFile],
    current_profile: Any,  # cfg.Profile
    cache_dir: Path
) -> None:
    """
    Apply loaded session data to the reconstructed ImageFile objects.
    
    :param session_data: The list of dicts loaded from JSON.
    :param image_files_dict: The dict mapping original paths to the new ImageFile objects.
    :param current_profile: The current profile to populate the output checksums with.
    :param cache_dir: The cache directory where intermediate files are stored.
    """
    for data in session_data:
        path = Path(data["path"])
        if path in image_files_dict:
            image = image_files_dict[path]
            image.uuid = data.get("uuid", image.uuid)
            image.canceled = data.get("canceled", False)
            
            analytics_dict = data.get("analytics_data", {})
            if image.analytics_data and analytics_dict:
                for cat in ost.ImageAnalyticCategory:
                    val = analytics_dict.get(cat.name, "")
                    if val:
                        image.analytics_data._data[cat] = val
                        
            # Reconnect existing outputs in cache so that processing will skip completed steps.
            path_gen = ost.OutputPathGenerator(image.path, cache_dir, uuid_source=image.uuid)
            for output_enum in ost.Output:
                if output_enum == ost.Output.write_output:
                    continue
                try:
                    out_path = path_gen.for_output(output_enum)
                    if out_path.exists() and output_enum in image.outputs:
                        image.outputs[output_enum].update(out_path, current_profile)
                except ValueError:
                    pass
