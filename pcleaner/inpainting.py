import os
from collections import namedtuple
from pathlib import Path

from PIL import Image
from loguru import logger
from simple_lama_inpainting import SimpleLama

import pcleaner.config as cfg
import pcleaner.image_ops as ops
import pcleaner.structures as st
import pcleaner.model_downloader as md
import pcleaner.output_structures as ost


class InpaintingModel:
    def __init__(self, config: cfg.Config) -> None:
        self.model_path = md.get_inpainting_model_path(config)
        # Sanity check: Make sure the model exists.
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Model not found: {self.model_path}")
        # Load the path into the env variable: LAMA_MODEL
        os.environ["LAMA_MODEL"] = str(self.model_path)
        self.simple_lama = SimpleLama()

    def __call__(self, image: Image, mask: Image) -> Image:
        """
        Inpaint the image using the mask.
        The mask must be a 1-channel image where 1 is the area to be inpainted and 0 is the area to keep.

        :param image: Input image.
        :param mask: Mask image.
        :return: The inpainted image.
        """
        # Run the model but ensure the output image is the same size as the input.
        inpainted_image = self.simple_lama(image, mask)
        if inpainted_image.size != image.size:
            width, height = image.size
            inpainted_image = inpainted_image.crop((0, 0, width, height))
        return inpainted_image


def inpaint_page(i_data: st.InpainterData, model: InpaintingModel) -> Image:
    """
    Load the MaskData from the json file and perform the inpainting process.

    :param i_data: All the data needed for the inpainting process.
    :param model: The inpainting model.
    :return: Analytics.
    """
    # Alias.
    m_conf = i_data.masker_config
    d_conf = i_data.denoiser_config
    i_conf = i_data.inpainter_config

    # Load all the cached data.
    page_data = st.PageData.from_json(i_data.page_data_json_path.read_text(encoding="utf-8"))
    exact_mask_image = Image.open(page_data.mask_path)
    mask_data = st.MaskData.from_json(i_data.mask_data_json_path.read_text(encoding="utf-8"))
    mask_image = Image.open(mask_data.mask_path)

    original_image = Image.open(mask_data.original_path)
    mask_image_bit = mask_image.convert("1")
    exact_mask_image = exact_mask_image.convert("1")
    original_image = original_image.convert("RGB")
    original_path: Path = mask_data.original_path
    # Ensure original_path is an image path, not a json path.
    if str(original_path).endswith(".json"):
        original_path = Path(page_data.original_path)

    path_gen = ost.OutputPathGenerator(original_path, i_data.cache_dir, i_data.page_data_json_path)

    if original_image.size[0] == 0 or original_image.size[1] == 0:
        logger.warning(f"Skipping inpainting for zero-size image: {original_path}")
        original_image.save(path_gen.inpainting)
        original_image.convert("RGBA").save(path_gen.clean_inpaint)
        return st.InpaintingAnalytic([], original_path, 0, 0, 0, 0)

    if not mask_data.boxes_with_stats:
        logger.info(f"No boxes to inpaint for {original_path}")

    # Collect the boxes to inpaint.
    BoxInpaintData = namedtuple("BoxInpaintData", ["box", "image", "deviation"])
    boxes_to_inpaint: list[BoxInpaintData] = []
    analytics_thicknesses: list[int] = []

    # First, find boxes that failed to be masked.
    failed_boxes_deviation: list[tuple[st.Box, float]] = [
        (box, deviation)
        for box, deviation, failed, thickness in mask_data.boxes_with_stats
        if failed
    ]
    # If automatic inpainting is enabled, calculate a dynamic threshold based on the deviations.
    if i_conf.inpainting_auto:
        deviations = [
            deviation
            for _, deviation, failed, thickness in mask_data.boxes_with_stats
            if not failed and thickness is not None
        ]
        if deviations:
            import statistics

            try:
                median_val = statistics.median(deviations)
                stdev_val = statistics.stdev(deviations) if len(deviations) > 1 else 0
                
                # === Adaptive threshold logic ===
                # Tier 1: If median is very low (< 2.0), the page is mostly clean white.
                #   → Use a moderate threshold so only truly messy bubbles get inpainted.
                # Tier 2: If median is moderate-high, page has gradients/complex backgrounds.
                #   → Use an aggressive (low) threshold to catch gradient artifacts.
                if median_val < 2.0:
                    threshold = max(2.0, median_val + 2 * stdev_val)
                else:
                    threshold = max(0.5, median_val - stdev_val)
            except (statistics.StatisticsError, IndexError):
                threshold = 0.5
                median_val, stdev_val = 0, 0
            
            logger.info(
                f"Adaptive inpainting: threshold={threshold:.2f} "
                f"(median={median_val:.2f}, stdev={stdev_val:.2f})"
            )
        else:
            threshold = m_conf.mask_max_standard_deviation

        # Adaptive parameters: Resolution-aware aggressive mode.
        img_h = original_image.height
        min_inp_radius = max(15, img_h // 60)
        max_inp_radius = min(min_inp_radius * 3, 80)
        rad_multiplier = 0.3
        fade_radius = max(4, min_inp_radius // 4)
        isolation_radius = fade_radius + 3
    else:
        threshold = i_conf.inpainting_min_std_dev
        min_inp_radius = i_conf.min_inpainting_radius
        max_inp_radius = i_conf.max_inpainting_radius
        rad_multiplier = i_conf.inpainting_radius_multiplier
        isolation_radius = i_conf.inpainting_isolation_radius
        fade_radius = i_conf.inpainting_fade_radius

    # Next, find the boxes meeting the minimum deviation and maximum thickness.
    poorly_fitted_boxes_deviation: list[tuple[st.Box, float]] = [
        (box, deviation)
        for box, deviation, failed, thickness in mask_data.boxes_with_stats
        if not failed
        and deviation >= threshold
        and thickness
        is not None  # For box masks, this is none. We don't need to inpaint those, they are always good.
        and thickness <= min_inp_radius
    ]

    # For the failed boxes, synthesize new masks grown to the minimum size.
    # Sample from the exact mask.
    for box, deviation in failed_boxes_deviation:
        mask = ops.cut_out_box(exact_mask_image, box)
        # Grow the mask to the minimum size.
        mask = ops.grow_mask(mask, m_conf.min_mask_thickness)
        boxes_to_inpaint.append(BoxInpaintData(box, mask, deviation))

    for box, deviation in poorly_fitted_boxes_deviation:
        mask = ops.cut_out_box(mask_image_bit, box)
        boxes_to_inpaint.append(BoxInpaintData(box, mask, deviation))

    # Now grow each mask according to the minimum inpainting radius, and the box's deviation.
    padded_boxes_to_inpaint: list[BoxInpaintData] = []
    for box, mask, deviation in boxes_to_inpaint:
        growth = min_inp_radius
        growth += int(deviation * rad_multiplier)
        growth = min(growth, max_inp_radius)
        # The isolation radius is added ahead of time here. We will grow it by this later, but only after
        # the inpainting.
        growth_with_isolation = growth + isolation_radius
        # Grow the box, then the mask, ensuring it stays within the image bounds.
        box_padded = box.pad(growth_with_isolation, mask_image.size)
        mask_padded = Image.new("1", mask_image.size, 0)
        offset: tuple[int, int] = box.x1 - box_padded.x1, box.y1 - box_padded.y1
        mask_padded.paste(mask, offset)
        mask_padded = ops.grow_mask(mask_padded, growth)
        padded_boxes_to_inpaint.append(BoxInpaintData(box_padded, mask_padded, deviation))
        analytics_thicknesses.append(growth)

    # Merge all the masks into one, then scale it up to the original image size.
    combined_mask = Image.new("1", mask_image.size, 0)
    for box, mask, _ in padded_boxes_to_inpaint:
        combined_mask.paste(mask, (box.x1, box.y1), mask)

    # Scale up the masks before inpainting.
    if original_image.size != mask_image.size:
        combined_mask = combined_mask.resize(original_image.size, resample=Image.NEAREST)

    # Inpaint the image.
    if boxes_to_inpaint:
        import cv2
        import numpy as np

        inpainted_image = original_image.copy()
        
        # Find isolated regions in the combined mask to inpaint them separately
        # This dramatically reduces memory usage and speeds up the AI model
        mask_np = np.array(combined_mask, dtype=np.uint8) * 255
        contours, _ = cv2.findContours(mask_np, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        context_padding = 256
        
        # 1. Collect all initial padded bounding boxes
        crop_boxes = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            left = max(0, x - context_padding)
            top = max(0, y - context_padding)
            right = min(original_image.width, x + w + context_padding)
            bottom = min(original_image.height, y + h + context_padding)
            crop_boxes.append([left, top, right, bottom])

        # 2. Merge overlapping boxes to prevent SimpleLama from running multiple times 
        # on fragmented small components, which kills performance due to model overhead.
        def merge_overlapping_boxes(boxes):
            merged = []
            for box in boxes:
                for m in merged:
                    # Check if box overlaps with m
                    if not (box[2] < m[0] or box[0] > m[2] or box[3] < m[1] or box[1] > m[3]):
                        # Merge them
                        m[0] = min(m[0], box[0])
                        m[1] = min(m[1], box[1])
                        m[2] = max(m[2], box[2])
                        m[3] = max(m[3], box[3])
                        break
                else:
                    merged.append(box)
            return merged

        while True:
            new_boxes = merge_overlapping_boxes(crop_boxes)
            if len(new_boxes) == len(crop_boxes):
                break
            crop_boxes = new_boxes

        # 3. Run SimpleLama on the merged crops
        for box in crop_boxes:
            crop_box = tuple(box)
            crop_img = inpainted_image.crop(crop_box)
            crop_mask = combined_mask.crop(crop_box)

            # Only inpaint if the mask crop has any pixels to inpaint
            if crop_mask.getbbox() is not None:
                crop_inpainted = model(crop_img, crop_mask)
                inpainted_image.paste(crop_inpainted, crop_box[:2])
    else:
        inpainted_image = original_image

    # Lastly, grow the masks again by the isolation radius to cut out the inpainted areas.
    isolated_combined_mask = Image.new("1", mask_image.size, 0)
    for box, mask, deviation in padded_boxes_to_inpaint:
        mask = ops.grow_mask(mask, isolation_radius)
        isolated_combined_mask.paste(mask, (box.x1, box.y1), mask)
    if original_image.size != mask_image.size:
        isolated_combined_mask = isolated_combined_mask.resize(
            original_image.size, resample=Image.NEAREST
        )
    if fade_radius:
        # Fade the mask edges for a smoother transition.
        mask_faded = ops.fade_mask_edges(combined_mask, fade_radius)
    else:
        mask_faded = combined_mask.convert("L")

    # Create a new output with these inpainted areas overlayed.
    # But first, apply the cleaning masks.
    # Don't bother copying as we won't need this anymore, so overwrite.
    cleaned_image = original_image.convert("RGBA")
    # We need to scale up the mask image to the original image size.
    if original_image.size != mask_image.size:
        mask_image = mask_image.resize(original_image.size, resample=Image.NEAREST)
    cleaned_image.paste(mask_image, (0, 0), mask_image)
    # Then, if denoising was enabled, apply that next.
    if d_conf.denoising_enabled and path_gen.noise_mask.is_file():
        noise_mask = Image.open(path_gen.noise_mask)
        cleaned_image.paste(noise_mask, (0, 0), noise_mask)

    # Cut away the rest according to the isolated combined mask.
    final_mask = Image.new("L", original_image.size, 0)
    final_mask.paste(mask_faded, (0, 0), isolated_combined_mask)
    inpainted_image.putalpha(final_mask)

    cleaned_image.alpha_composite(inpainted_image)
    cleaned_image.putalpha(255)

    # Save output.
    inpainted_image.save(path_gen.inpainting)
    cleaned_image.save(path_gen.clean_inpaint)

    # Package the analytics. We're only interested in the thicknesses.
    return st.InpaintingAnalytic(
        analytics_thicknesses,
        original_path,
        threshold,
        min_inp_radius,
        isolation_radius,
        fade_radius,
    )
