import json
import re
import urllib.request
import urllib.error
from pathlib import Path
from loguru import logger

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Cascading model list: fast, reliable, active Gemini 3.x models
DEFAULT_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
]


def _call_gemini_rest(prompt: str, api_key: str, model_names: list = None, timeout: int = 180) -> str:
    """
    Call Gemini REST API directly using urllib (no SDK needed).
    Cascades through model_names on failure.
    Returns the raw text response or None.
    """
    if model_names is None:
        model_names = DEFAULT_MODELS

    headers = {"Content-Type": "application/json"}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }
    data = json.dumps(body).encode("utf-8")

    for model_name in model_names:
        url = GEMINI_API_URL.format(model=model_name) + f"?key={api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            logger.info(f"Dispatching request to: {model_name} (REST API)...")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                candidates = result.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "").strip()
                        if text:
                            logger.info(f"Successfully received response from {model_name}.")
                            return text
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            logger.warning(f"HTTP {e.code} from {model_name}: {error_body[:200]}. Cascading...")
        except Exception as e:
            logger.warning(f"Attempt with {model_name} failed: {e}. Cascading...")

    return None


def _clean_json_response(text: str) -> str:
    """Remove markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def parse_arabic_manga_script(raw_text) -> dict:
    """
    Intelligently parses Arabic manga translation scripts:
    1. Normalizes invisible characters (zero-width spaces, BOM, etc.).
    2. Identifies all standard page markers (01, 1, 01:, [01], P01, P.01, صفحة 1, ص 01, etc.).
    3. Filters out translator signatures, chapter titles, and metadata before the first page.
    4. Treats each dialogue line as an individual bubble.
    5. PRESERVES all tag prefixes ([], ::, "", //:, etc.) so that TypeR can automatically apply font presets!
    
    Returns:
        {
            "has_page_headers": bool,
            "pages": { "page_1": ["[]: نص 1", "//: نص 2", ...], ... },
            "flat_dialogues": ["[]: نص 1", ...]
        }
    """
    if isinstance(raw_text, (list, tuple)):
        raw_text = "\n".join(str(l) for l in raw_text)
    elif not isinstance(raw_text, str):
        raw_text = str(raw_text or "")

    clean_text = raw_text.replace('\u200b', '').replace('\ufeff', '').replace('\xa0', ' ')
    raw_lines = [l.strip() for l in clean_text.splitlines() if l.strip()]

    # Universal page header regex:
    # Matches: '01', '1', '01:', '1:', '[01]', '(01)', 'Page 01', 'صفحة 1', 'الصفحة 01', 'ص 01', 'ص1', 'P.01', 'P01', etc.
    page_header_pattern = re.compile(
        r'^(?:(?:\*{0,2})(?:صفحة|الصفحة|ص|page|p\.?)\s*(\d+)(?:\*{0,2})|[\[\(]?\s*(\d{1,3})\s*[\]\)]?[:\-\.]?)$',
        re.IGNORECASE
    )
    chapter_header_pattern = re.compile(r'^(?:\*{0,2})(?:الفصل|فصل|chapter|ch\.?)\s*(\d+)', re.IGNORECASE)

    pages_dict = {}
    current_page_key = None
    header_metadata = []

    for line in raw_lines:
        # Skip chapter title/number headers
        if chapter_header_pattern.match(line):
            continue

        # Check for page headers
        m_page = page_header_pattern.match(line)
        if m_page:
            p_num = m_page.group(1) or m_page.group(2)
            current_page_idx = int(p_num)
            current_page_key = f'page_{current_page_idx}'
            if current_page_key not in pages_dict:
                pages_dict[current_page_key] = []
            continue

        # Lines before the first page header are translator metadata / signatures (e.g. 'Rivenya', team credits)
        if current_page_key is None:
            header_metadata.append(line)
        else:
            pages_dict[current_page_key].append(line)

    found_page_headers = len(pages_dict) > 0

    # If no page headers were found at all, treat non-header lines as flat dialogues
    if not found_page_headers:
        valid_pages = {"page_1": header_metadata}
        flat_all = list(header_metadata)
    else:
        valid_pages = {k: v for k, v in pages_dict.items() if len(v) > 0}
        flat_all = []
        for p_key in sorted(valid_pages.keys(), key=lambda x: int(x.split('_')[-1]) if x.split('_')[-1].isdigit() else 999):
            flat_all.extend(valid_pages[p_key])

    return {
        "has_page_headers": found_page_headers,
        "pages": valid_pages,
        "flat_dialogues": flat_all
    }


def perform_ai_batch_semantic_match(all_pages_bubbles: dict, arabic_raw_text: str, api_key: str) -> dict:
    """
    Sends a structured, high-accuracy semantic alignment request to Gemini AI.
    Features:
    1. Deterministic Page-Anchor Alignment: If the Arabic script contains page headers (صفحة 1, 2...),
       each page is aligned independently to guarantee ZERO cascade shifting.
    2. Intelligent Scanlation Credit & Watermark Filtering: Non-story bubbles (credits, websites, logos) are assigned "".
    3. Tag Preservation: Preserves translator bracket markers ([], ::, //:) for automated TypeR styling.
    """
    if not api_key:
        raise ValueError("API key is missing.")

    parsed_script = parse_arabic_manga_script(arabic_raw_text)
    has_page_headers = parsed_script["has_page_headers"]
    script_pages = parsed_script["pages"]
    flat_dialogues = parsed_script["flat_dialogues"]

    logger.info(f"Script parsed successfully. Found page headers: {has_page_headers}, Total dialogue units: {len(flat_dialogues)}")

    final_batch = {}
    pages_needing_ai = {}

    # Sort pages by natural order
    page_keys = list(all_pages_bubbles.keys())

    # --- PHASE 1: DETERMINISTIC PAGE-BY-PAGE ANCHORING ---
    if has_page_headers:
        for idx, p_stem in enumerate(page_keys):
            bubbles_dict = all_pages_bubbles[p_stem]
            num_bubbles = len(bubbles_dict)
            
            # Match by numeric stem (e.g. "01" -> 1, "02" -> 2) or by sequence index (idx + 1)
            num_match = re.search(r'\d+', p_stem)
            target_page_num = int(num_match.group()) if num_match else (idx + 1)
            script_key = f"page_{target_page_num}"

            page_dialogues = script_pages.get(script_key, [])

            # Perfect 1:1 match only if exact same count
            if num_bubbles > 0 and len(page_dialogues) == num_bubbles:
                logger.info(f"✅ Page '{p_stem}' has exact {num_bubbles} bubbles matching script page '{script_key}'. Applied deterministic 1:1 alignment.")
                page_res = {}
                for b_id, d_text in zip(bubbles_dict.keys(), page_dialogues):
                    page_res[b_id] = d_text
                final_batch[p_stem] = page_res
            else:
                # Needs AI alignment / disambiguation for this page (e.g. extra credit boxes or SFX)
                pages_needing_ai[p_stem] = {
                    "script_key": script_key,
                    "bubbles": bubbles_dict,
                    "dialogues": page_dialogues if page_dialogues else []
                }

        # If all pages matched deterministically 1:1, return immediately (zero API wait!)
        if not pages_needing_ai:
            logger.info("🎉 All pages matched with 100% exact 1:1 deterministic alignment!")
            return final_batch
    else:
        for p_stem in page_keys:
            pages_needing_ai[p_stem] = {
                "script_key": "global",
                "bubbles": all_pages_bubbles[p_stem],
                "dialogues": flat_dialogues
            }

    # --- PHASE 2: HIGH-ACCURACY GEMINI SEMANTIC ALIGNMENT ---
    prompt = f"""
You are an expert Manga Lettering & Typesetting Alignment AI.

TASK:
Map speech bubbles in each manga page to their corresponding Arabic translation lines based on semantic meaning, dialogue progression, and top-to-bottom reading order.

CRITICAL RULES:
1. SOUND EFFECTS (SFX) & CREDITS MUST BE EMPTY:
   - If a bubble contains Sound Effects (SFX e.g. BOOM, CRASH, 쾅, 啪, HEH...), action noises, laughter, panel background sound effects, scanlation credits, or website URLs (e.g. QIMANGA.COM) that are NOT in the Arabic translation script, assign an EMPTY string "" to that bubble ID!
   - DO NOT place character dialogue lines into sound effect (SFX) bubbles!
2. SEMANTIC SPEECH MATCHING:
   - Compare the original text inside the speech bubbles (English/Japanese OCR) with the Arabic translation lines to find the true correct match.
   - The Arabic translation lines are in the chronological dialogue sequence of the chapter.
3. NO HALLUCINATIONS / STRICT VERBATIM OUTPUT:
   - The assigned value for each bubble ID MUST BE EITHER an EXACT string copied verbatim from the provided Arabic list, OR an empty string "".
   - NEVER output single characters like "放", "none", "null", or any invented text not present in the Arabic list.
4. PRESERVE TAGS: 
   - Keep translator tags ([], ::, "", //:, etc.) intact at the beginning of each Arabic line.

INPUT DATA:
"""

    if has_page_headers:
        prompt += "\n--- PAGES TO ALIGN (Scoped by Page Header) ---\n"
        for p_stem, info in pages_needing_ai.items():
            prompt += f"\nPAGE: {p_stem} (Script Header: {info['script_key']})\n"
            prompt += f"Detected Bubbles (Top-to-Bottom):\n{json.dumps(info['bubbles'], ensure_ascii=False, indent=2)}\n"
            prompt += f"Required Arabic Dialogue Lines for this page (in sequence):\n"
            for i, d in enumerate(info['dialogues']):
                prompt += f"  [{i+1}] {repr(d)}\n"
    else:
        prompt += "\n--- ALL DETECTED BUBBLES ACROSS PAGES ---\n"
        prompt += json.dumps(all_pages_bubbles, ensure_ascii=False, indent=2) + "\n"
        prompt += "\n--- SEQUENTIAL ARABIC TRANSLATION SCRIPT (Top-to-Bottom) ---\n"
        for i, d in enumerate(flat_dialogues):
            prompt += f"[{i+1}] {repr(d)}\n"

    prompt += """
RESPONSE FORMAT:
Return ONLY a valid JSON object mapping page names and bubble IDs to their assigned Arabic strings.
Example:
{
  "01": { 
    "bubble_1": "", 
    "bubble_2": "", 
    "bubble_9": "[]: العالمُ على سرعةِ 300 كم/ساعة…", 
    "bubble_10": "[]: فيه يفقدُ الغلافُ الجويُّ خصائصَه..." 
  }
}
No markdown fences, no explanatory text.
"""

    response_text = _call_gemini_rest(prompt, api_key, timeout=300)

    if response_text:
        try:
            result_mapping = json.loads(_clean_json_response(response_text))
            if isinstance(result_mapping, dict) and len(result_mapping) > 0:
                for p_stem in page_keys:
                    if p_stem in final_batch:
                        continue # Already exact

                    bubbles_dict = all_pages_bubbles[p_stem]
                    bubble_keys_list = list(bubbles_dict.keys())
                    gemini_page_res = result_mapping.get(p_stem, {})

                    # Valid dialogues for this page
                    page_dialogues = pages_needing_ai.get(p_stem, {}).get("dialogues", []) if has_page_headers else flat_dialogues
                    valid_dialogue_set = set(page_dialogues)

                    page_res = {}
                    assigned_dialogues = []

                    # 1. First Pass: Apply verified Gemini matches (strictly rejecting hallucinations like '放')
                    for b_id in bubble_keys_list:
                        raw_val = gemini_page_res.get(b_id, "").strip()
                        if raw_val in valid_dialogue_set and raw_val not in assigned_dialogues:
                            page_res[b_id] = raw_val
                            assigned_dialogues.append(raw_val)
                        else:
                            page_res[b_id] = ""

                    # 2. Second Pass: If any dialogues from the page script were missed, assign them sequentially to unassigned bubbles
                    unassigned_dialogues = [d for d in page_dialogues if d not in assigned_dialogues]
                    if unassigned_dialogues:
                        unassigned_bubbles = [b_id for b_id in bubble_keys_list if not page_res[b_id]]
                        for d_text in unassigned_dialogues:
                            if unassigned_bubbles:
                                target_b_id = unassigned_bubbles.pop(0)
                                page_res[target_b_id] = d_text

                    final_batch[p_stem] = page_res
                return final_batch
        except Exception as e:
            logger.warning(f"Could not parse Gemini JSON response: {e}")

    # --- PHASE 3: ROBUST SEQUENTIAL FALLBACK (If AI fails) ---
    logger.warning("Applying robust sequential fallback alignment based on parsed dialogue units.")
    if has_page_headers:
        for p_stem, info in pages_needing_ai.items():
            bubbles_dict = info["bubbles"]
            d_list = info["dialogues"]
            page_res = {}
            for i, b_id in enumerate(bubbles_dict.keys()):
                page_res[b_id] = d_list[i] if i < len(d_list) else ""
            final_batch[p_stem] = page_res
    else:
        d_ptr = 0
        for p_stem, bubbles_dict in all_pages_bubbles.items():
            page_res = {}
            for b_id in bubbles_dict.keys():
                if d_ptr < len(flat_dialogues):
                    page_res[b_id] = flat_dialogues[d_ptr]
                    d_ptr += 1
                else:
                    page_res[b_id] = ""
            final_batch[p_stem] = page_res

    return final_batch


def perform_ai_semantic_match(english_bubbles, arabic_raw_text, api_key: str) -> dict:
    """Single page wrapper around perform_ai_batch_semantic_match."""
    if isinstance(english_bubbles, list):
        bubbles_dict = {str(it.get("id", idx+1)): it.get("text", "") for idx, it in enumerate(english_bubbles)}
    else:
        bubbles_dict = english_bubbles or {}
    res = perform_ai_batch_semantic_match({"page_01": bubbles_dict}, arabic_raw_text, api_key)
    return res.get("page_01", {})
