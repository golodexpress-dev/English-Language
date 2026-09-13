# -*- coding: utf-8 -*-
"""
make_audio.py
สร้างไฟล์เสียง mp3 จากรายการคำศัพท์ ด้วย Google Text-to-Speech (gTTS)

วิธีใช้
    1) pip install gTTS
    2) วางไฟล์นี้ไว้กับ audio_bee.json และ audio_sci.json ในโฟลเดอร์เดียวกัน
    3) python make_audio.py

คุณสมบัติ
    - รันซ้ำได้ ไฟล์ที่มีอยู่แล้วจะถูกข้าม (resume) ถ้าหลุดกลางคันให้รันคำสั่งเดิมซ้ำ
    - ลองใหม่อัตโนมัติเมื่อเน็ตสะดุด (3 ครั้ง)
    - สร้าง manifest.json ในแต่ละโฟลเดอร์ บอกว่าคำไหนตรงกับไฟล์ไหน

รูปแบบไฟล์ JSON ที่รองรับ (บันทึกเป็น UTF-8)
    A) ["apple", "banana", "cat"]
    B) {"apple": "apple", "q01": "What color is the sky?"}
    C) [{"id": "0001_apple", "text": "apple", "lang": "en"},
        {"id": "0002_th",    "text": "แสง",   "lang": "th"}]
       รูปแบบ C ใส่ "lang" แยกรายคำได้ ใช้ได้ทั้งอังกฤษและไทยในไฟล์เดียวกัน
"""

import json
import os
import re
import sys
import time
import unicodedata

try:
    from gtts import gTTS
except ImportError:
    print("ยังไม่ได้ติดตั้ง gTTS")
    print("ให้พิมพ์คำสั่งนี้ใน Command Prompt ก่อน:  pip install gTTS")
    sys.exit(1)

# ------------------------------------------------------------------
# ตั้งค่า
# ------------------------------------------------------------------
JOBS = [
    {"json": "audio_bee.json", "out": os.path.join("audio", "bee")},
    {"json": "audio_sci.json", "out": os.path.join("audio", "sci")},
]

LANG = "en"      # ภาษาเริ่มต้น ถ้ารายการไหนใส่ "lang" มาเองจะใช้ของรายการนั้น
TLD = "com"      # สำเนียง: com = อเมริกัน, co.uk = อังกฤษ, com.au = ออสเตรเลีย
SLOW = False     # True = พูดช้า
DELAY = 0.4      # หน่วงระหว่างคำ (วินาที) กันโดน Google จำกัดจำนวนครั้ง
RETRIES = 3


# ------------------------------------------------------------------
def slugify(text):
    """แปลงข้อความเป็นชื่อไฟล์ที่ปลอดภัย เช่น  "What's up?" -> whats_up"""
    text = unicodedata.normalize("NFKD", str(text))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = text.replace("'", "").replace("\u2019", "")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "item"


def load_items(path):
    """อ่าน JSON แล้วคืนค่าเป็น list ของ (ชื่อไฟล์ไม่รวมนามสกุล, ข้อความ, ภาษา)"""
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    items = []
    if isinstance(data, dict):
        for key, value in data.items():
            text = value if isinstance(value, str) else str(value)
            items.append((slugify(key), text, LANG))
    elif isinstance(data, list):
        for entry in data:
            if isinstance(entry, str):
                items.append((slugify(entry), entry, LANG))
            elif isinstance(entry, dict):
                text = entry.get("text") or entry.get("word") or entry.get("en") or ""
                name = entry.get("id") or entry.get("file") or text
                lang = entry.get("lang") or LANG
                if text:
                    items.append((slugify(name), text, lang))
    else:
        raise ValueError("รูปแบบ JSON ไม่ถูกต้อง")

    # กันชื่อไฟล์ซ้ำ
    seen = {}
    result = []
    for name, text, lang in items:
        if name in seen:
            seen[name] += 1
            name = "%s_%d" % (name, seen[name])
        else:
            seen[name] = 1
        result.append((name, text, lang))
    return result


def speak(text, out_path, lang):
    """สร้างไฟล์ mp3 หนึ่งไฟล์ ลองใหม่ได้ถ้าเน็ตสะดุด"""
    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            tld = TLD if lang == "en" else "com"
            tts = gTTS(text=text, lang=lang, tld=tld, slow=SLOW)
            tmp = out_path + ".part"
            tts.save(tmp)
            os.replace(tmp, out_path)
            return True, None
        except Exception as exc:          # noqa: BLE001
            last_error = exc
            if attempt < RETRIES:
                wait = attempt * 5
                print("      ...พลาด ลองใหม่ในอีก %d วินาที (%s)" % (wait, exc))
                time.sleep(wait)
    return False, last_error


def run_job(job):
    json_path = job["json"]
    out_dir = job["out"]

    if not os.path.exists(json_path):
        print("!! ไม่พบไฟล์ %s  ข้ามงานนี้" % json_path)
        return 0, 0, []

    items = load_items(json_path)
    os.makedirs(out_dir, exist_ok=True)

    print("")
    print("=" * 60)
    print("%s  ->  %s   (%d รายการ)" % (json_path, out_dir, len(items)))
    print("=" * 60)

    created = skipped = 0
    failed = []
    manifest = {}
    total = len(items)

    for index, (name, text, lang) in enumerate(items, start=1):
        filename = name + ".mp3"
        out_path = os.path.join(out_dir, filename)
        manifest[lang + "|" + text] = filename

        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            skipped += 1
            print("[%4d/%d] ข้าม (มีแล้ว)  %s" % (index, total, filename))
            continue

        print("[%4d/%d] %-40s -> %s" % (index, total, text[:40], filename))
        ok, err = speak(text, out_path, lang)
        if ok:
            created += 1
            time.sleep(DELAY)
        else:
            failed.append((text, str(err)))
            print("      !! ไม่สำเร็จ: %s" % err)

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return created, skipped, failed


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)) or ".")
    start = time.time()

    total_created = total_skipped = 0
    all_failed = []

    for job in JOBS:
        created, skipped, failed = run_job(job)
        total_created += created
        total_skipped += skipped
        all_failed.extend(failed)

    minutes = (time.time() - start) / 60
    print("")
    print("=" * 60)
    print("เสร็จแล้ว ใช้เวลา %.1f นาที" % minutes)
    print("สร้างใหม่ %d ไฟล์   ข้ามเพราะมีอยู่แล้ว %d ไฟล์" % (total_created, total_skipped))

    if all_failed:
        print("ไม่สำเร็จ %d รายการ  ให้รัน python make_audio.py ซ้ำอีกครั้ง" % len(all_failed))
        for text, err in all_failed[:20]:
            print("   - %s  (%s)" % (text, err))
    else:
        print("ครบทุกรายการ ไม่มีที่ค้าง")
    print("=" * 60)


if __name__ == "__main__":
    main()
