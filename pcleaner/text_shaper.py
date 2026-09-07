#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastTypeR - Professional Arabic Text Shaping & Visual Physics Engine
===================================================================
محرك التايبست البصري المتطور للنصوص العربية في المانجا:
1. قياس الأوزان البصرية الدقيقة للحروف (Visual Character Physics).
2. حماية الروابط اللغوية وأدوات النفي والجر (Semantic Linguistic Protection).
3. التوزيع التوافقي المتوازن للأسطر مع فرض الغرامات على الكلمات المنعزلة.
4. توزيع الكشيدات وفق الطبقات الجمالية للخطوط العربية (Tiered Kashida Distribution).
"""

import math
import re

# أوزان الحروف البصرية الدقيقة (مأخوذة ومطورة من محرك TypeR)
def get_visual_length(text: str, k_weight: float = 0.48) -> float:
    if not text:
        return 0.0
    
    # إزالة التشكيل
    clean = re.sub(r'[\u064B-\u065F\u0670\u06D6-\u06ED]', '', text)
    total = 0.0
    for ch in clean:
        if ch in ('ـ', '\u0640'):
            total += k_weight
        elif ch == ' ':
            total += 0.55
        elif ch in 'صضطظسش':
            total += 1.45
        elif ch in 'جحخعغفقك':
            total += 1.15
        elif ch in 'بتثني':
            total += 0.95
        elif ch in 'مه':
            total += 0.85
        elif ch in 'اأإآلدذرزوؤءةى':
            total += 0.70
        elif ch in 'WMwm':
            total += 1.35
        elif ch in "ijlI1t.,:;!'\"":
            total += 0.45
        elif ch in '0123456789':
            total += 0.75
        elif ch in '!؟،؛.,:…«»"\'()–—[]{}':
            total += 0.50
        elif ch in '—–':
            total += 1.20
        else:
            total += 0.90
    return total


# الحروف غير القابلة للاتصال بما بعدها
NON_CONNECTING = set("اأإآدذرزوؤءةى ")
ARABIC_LETTERS = set("ابتثجحخدذرزسشصضطظعغفقكلمنهويىةأإآءؤئ")
ALEF_CHARS = set("اأإآ")
DIACRITICS = re.compile(r'[\u064B-\u065F\u0670\u06D6-\u06ED]')
PUNCTUATION = re.compile(r'^[!؟،؛\.,:…«»"\'()\-\[\]{}]+|[!؟،؛\.,:…«»"\'()\-\[\]{}]+$')

# أدوات وحروف الربط التي يجب حمايتها من الوقوع منعزلة في نهايات الأسطر
HANGING_PARTICLES = {"في", "من", "إلى", "على", "عن", "لا", "لم", "لن", "ما", "إن", "أن", "قد", "هل", "يا", "أي", "لو", "كي", "مع", "وإن", "ومع", "فهل"}

# نسب محاذاة الأسطر الافتراضية للفقاعات
DEFAULT_BUBBLE_RATIOS = {
    1: [1.0],
    2: [1.0, 1.0],
    3: [0.80, 1.0, 0.80],
    4: [0.70, 1.0, 1.0, 0.70],
    5: [0.40, 0.75, 1.0, 0.75, 0.40],
    6: [0.40, 0.75, 1.0, 1.0, 0.75, 0.40],
}
BUBBLE_RATIOS = DEFAULT_BUBBLE_RATIOS

# نسب محاذاة الأسطر الافتراضية لمربعات ومستطيلات السرد
DEFAULT_BOX_RATIOS = {
    1: [1.0],
    2: [1.0, 1.0],
    3: [1.0, 1.0, 1.0],
    4: [1.0, 1.0, 1.0, 1.0],
    5: [1.0, 1.0, 1.0, 1.0, 1.0],
    6: [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
}
BOX_RATIOS = DEFAULT_BOX_RATIOS


def clean_script_text(text: str) -> str:
    """تنظيف النص من زوائد السكربت والاقتباسات الفارغة والوسوم"""
    if not text:
        return ""
    
    t = text.strip()
    t = re.sub(r'[\r\n]+', ' ', t)
    t = re.sub(r'ـ', '', t)
    t = re.sub(r'^(<[^>]*>|<>|\[[^\]]*\]|\[\]|《[^》]*》|【[^】]*】)\s*[:：]?', '', t)
    t = re.sub(r'^(\s*[\"\']+\s*[:：\-]?\s*|\s*[:：\-]\s*[\"\']+\s*)', '', t)
    t = re.sub(r'(\s*[\"\']+\s*[:：\-]?\s*|\s*[:：\-]\s*[\"\']+\s*)$', '', t)
    t = re.sub(r'^[0-9]+[\.\:\-]\s*', '', t)
    t = re.sub(r'[\s\u00A0\u200B-\u200D\uFEFF]+', ' ', t)
    t = re.sub(r'\s+([!؟،؛\.,:…]+)', r'\1', t)
    return t.strip()


def evaluate_optimal_arabic_shape(words: list, aspect: float = 1.0, shape_option: int = 8, target_lines: int = None) -> tuple:
    """تقييم الشكل الأنسب وعدد الأسطر بناءً على نسبة أبعاد الفقاعة وعدد الكلمات"""
    w_count = len(words)
    if w_count <= 0:
        return 7, 1
    
    if target_lines and target_lines >= 1:
        req_k = min(target_lines, w_count)
        return (7 if req_k == 1 else req_k - 1), req_k

    if shape_option == 6:
        return 6, 0

    if aspect >= 1.8:
        if w_count <= 5:
            return 7, 1
        if w_count <= 12:
            return 1, 2
        return 2, 3

    if aspect <= 0.65:
        if w_count <= 2:
            return 7, 1
        if w_count <= 4:
            return 1, 2
        if w_count <= 8:
            return 2, 3
        if w_count <= 14:
            return 3, 4
        return 4, 5

    if w_count <= 3:
        return (7 if aspect >= 1.15 else 1), (1 if aspect >= 1.15 else 2)
    if w_count <= 6:
        return 1, 2
    if w_count <= 11:
        return 2, 3
    if w_count <= 17:
        return 3, 4
    if w_count <= 24:
        return 4, 5
    return 5, 6


def apply_kashida_to_line(line_str: str, deficit_visual_length: float, k_weight: float = 0.48) -> str:
    """إدخال الكشيدات وفق مستويات الأولوية الجمالية للخط العربي"""
    kw = k_weight if k_weight > 0 else 0.48
    if deficit_visual_length <= (kw * 0.5):
        return line_str
    
    kashida_needed = round(deficit_visual_length / kw)
    if kashida_needed <= 0:
        return line_str

    line_words = line_str.split(' ')
    if not line_words:
        return line_str

    candidates = []
    for w_idx, word in enumerate(line_words):
        clean_word = DIACRITICS.sub('', word)
        clean_word = PUNCTUATION.sub('', clean_word)
        if len(clean_word) < 2:
            continue

        chars = list(word)
        for c in range(len(chars) - 1):
            curr = chars[c]
            if curr in NON_CONNECTING or curr not in ARABIC_LETTERS:
                continue

            next_idx = c + 1
            while next_idx < len(chars) and DIACRITICS.match(chars[next_idx]):
                next_idx += 1
            if next_idx >= len(chars):
                continue

            next_char = chars[next_idx]
            if next_char not in ARABIC_LETTERS:
                continue

            # منع الكشيدة قطعياً داخل اللام ألف (لا)
            if curr == 'ل' and next_char in ALEF_CHARS:
                continue

            # فحص إذا كان الحرف قبل الأخير المتصل
            is_last_letter = True
            for chk in range(next_idx + 1, len(chars)):
                if chars[chk] in ARABIC_LETTERS and not DIACRITICS.match(chars[chk]):
                    is_last_letter = False
                    break

            score = 30
            if len(clean_word) >= 4:
                if is_last_letter:
                    score = 100  # المستوى الأول: الحرف قبل الأخير في كلمة من 4+ حروف
                elif curr in 'صضطظسش':
                    score = 85   # المستوى الثاني: أسنان السين والشين والصاد
                elif c > 0:
                    score = 65   # المستوى الثالث: الحروف المتوسطة
                else:
                    score = 35
            elif len(clean_word) == 3:
                if is_last_letter:
                    score = 75
                else:
                    score = 45
            elif len(clean_word) == 2:
                score = 25

            if clean_word.startswith('ال') and c <= 1:
                score = 15

            candidates.append({
                'word_idx': w_idx,
                'char_idx': c,
                'score': score,
                'word_len': len(clean_word),
                'count': 0
            })

    if not candidates:
        return line_str

    candidates.sort(key=lambda x: (x['score'], x['word_len']), reverse=True)

    added = 0
    max_rounds = max(kashida_needed * 5, 25)
    round_idx = 0

    while added < kashida_needed and round_idx < max_rounds:
        progress = False
        for cand in candidates:
            if added >= kashida_needed:
                break
            
            if round_idx == 0:
                if cand['score'] < 60 and candidates[0]['score'] >= 60:
                    continue
                limit = 1
            elif round_idx == 1:
                limit = 1
            elif round_idx == 2:
                limit = 2
            elif round_idx == 3:
                limit = 3
            else:
                limit = round_idx

            if cand['count'] < limit:
                cand['count'] += 1
                added += 1
                progress = True

        if not progress:
            for cand in candidates:
                if added >= kashida_needed:
                    break
                cand['count'] += 1
                added += 1
        round_idx += 1

    # إعادة بناء الكلمات المعدلة
    modified_words = list(line_words)
    for w_idx in range(len(modified_words)):
        w_cands = [c for c in candidates if c['word_idx'] == w_idx and c['count'] > 0]
        if not w_cands:
            continue

        w_cands.sort(key=lambda x: x['char_idx'], reverse=True)
        word_chars = list(modified_words[w_idx])
        for c in w_cands:
            pos = c['char_idx'] + 1
            k_chars = ['ـ'] * c['count']
            word_chars[pos:pos] = k_chars
        modified_words[w_idx] = ''.join(word_chars)

    return ' '.join(modified_words)


def shape_arabic_text(
    text: str,
    shape_type: str = "bubble",
    lines_count: int = None,
    aspect_ratio: float = 1.0,
    detected_lines: int = None,
    kashida_weight: float = 0.48,
    custom_ratios: dict = None
) -> str:
    """
    الدالة الرئيسية لتنسيق النصوص العربية وفق محرك TypeR البصري المتقدم:
    - text: النص العربي المراد تنسيقه
    - shape_type: "bubble" (فقاعة دائرية/معين) أو "box" (مربع سرد متساوي)
    - lines_count: عدد الأسطر المطلوب (إذا حُدد يدوياً من المستخدم)
    - aspect_ratio: نسبة العرض إلى الارتفاع للفقاعة
    - detected_lines: عدد أسطر الفقاعة من كاشف النصوص الأصلي
    - kashida_weight: وزن الكشيدة البصري (افتراضياً 0.48)
    """
    clean = clean_script_text(text)
    if not clean:
        return ""

    words = clean.split()
    if len(words) <= 1:
        return clean

    # تحديد خيار الشكل
    shape_option = 6 if shape_type.lower() in ("box", "rect", "square", "مستطيل", "سرد") else 8

    # تقييم الأسطر والنسب
    target_l = lines_count if (lines_count and lines_count > 0) else detected_lines
    smart_shape, smart_k = evaluate_optimal_arabic_shape(words, aspect=aspect_ratio, shape_option=shape_option, target_lines=target_l)

    k = smart_k
    if k > len(words):
        k = len(words)
    if k < 1:
        k = 1

    # تحديد نسب الأطوال المستهدفة
    T = []
    if smart_shape == 6 or shape_option == 6:
        k_box = target_l if (target_l and target_l <= len(words)) else max(1, math.ceil(math.sqrt(len(words))))
        k = min(k_box, len(words))
        T = [1.0] * k
    elif k == 1:
        return clean
    elif k in DEFAULT_BUBBLE_RATIOS:
        T = list(DEFAULT_BUBBLE_RATIOS[k])
    else:
        for oi in range(k):
            norm_dist = (oi - (k - 1) / 2) / ((k - 1) / 2)
            oval_w = max(0.4, math.sqrt(max(0, 1 - norm_dist * norm_dist * 0.7)))
            T.append(oval_w)

    if custom_ratios and k in custom_ratios:
        T = custom_ratios[k]

    total_vis = get_visual_length(' '.join(words), kashida_weight)
    sum_t = sum(T)
    target_lengths = [(T[i] / sum_t) * total_vis for i in range(k)]

    best_lines = []
    best_score = float('inf')

    def score(partition):
        err = 0.0
        for i in range(len(partition)):
            line_words = partition[i]
            line_len = get_visual_length(' '.join(line_words), kashida_weight)
            err += (line_len - target_lengths[i]) ** 2

            # غرامة مضاعفة لوجود كلمة واحدة معزولة في السطر عندما تكون الجملة 4+ كلمات
            if len(line_words) == 1 and len(words) >= 4:
                err += 400.0

            # غرامة للأسطر شديدة القصر
            if line_len < 4.0 and len(words) >= 5:
                err += 250.0

            # غرامة لغوية لتعليق أدوات الجر والربط في نهاية سطر غير نهائي
            if i < len(partition) - 1:
                last_w = line_words[-1]
                if last_w in HANGING_PARTICLES:
                    err += 180.0

        return err

    def search(arr, left, cur):
        nonlocal best_score, best_lines
        if left == 1:
            part = cur + [arr]
            s = score(part)
            if s < best_score:
                best_score = s
                best_lines = part
            return
        max_idx = len(arr) - (left - 1)
        for i in range(1, max_idx + 1):
            search(arr[i:], left - 1, cur + [arr[:i]])

    if len(words) <= 15:
        search(words, k, [])
    else:
        # خوارزمية جشعة للعبارات الطويلة
        lines_arr = []
        word_idx = 0
        for i in range(k):
            cur_line = []
            cur_len = 0.0
            tgt = target_lengths[i]
            if i == k - 1:
                lines_arr.append(words[word_idx:])
                break
            while word_idx < len(words) - (k - 1 - i):
                w = words[word_idx]
                next_len = cur_len + (0.55 if cur_len > 0 else 0) + get_visual_length(w, kashida_weight)
                if len(cur_line) == 0 or abs(next_len - tgt) < abs(cur_len - tgt):
                    cur_line.append(w)
                    cur_len = next_len
                    word_idx += 1
                else:
                    break
            lines_arr.append(cur_line)
        best_lines = lines_arr

    if not best_lines:
        return '\n'.join(words)

    # حساب الوحدة الأساسية للتمديد
    base_unit = 0.0
    for i in range(len(best_lines)):
        line_str = ' '.join(best_lines[i])
        v_len = get_visual_length(line_str, kashida_weight)
        ratio = T[i] if (i < len(T) and T[i] > 0) else 1.0
        req_base = v_len / ratio
        if req_base > base_unit:
            base_unit = req_base

    # تطبيق الكشيدات لمطابقة النسب الهندسية
    final_lines = []
    for i in range(len(best_lines)):
        line_str = ' '.join(best_lines[i])
        v_len = get_visual_length(line_str, kashida_weight)
        ratio = T[i] if (i < len(T) and T[i] > 0) else 1.0
        target_vis_len = base_unit * ratio
        deficit = target_vis_len - v_len
        balanced_line = apply_kashida_to_line(line_str, deficit, kashida_weight)
        final_lines.append(balanced_line)

    return '\n'.join(final_lines)
