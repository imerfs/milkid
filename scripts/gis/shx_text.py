"""Read the legacy Persian text of the survey drawings.

Their text uses the SHX fonts ``naskhd.shx`` / ``naskhn.shx`` of an old Persian CAD add-on, which are not installed
with AutoCAD: without them the legend shows as ``???`` glyphs. The font maps Persian onto single bytes: the ASCII
letters follow the Persian keyboard layout (isolated and initial forms) and the high bytes are the joined forms. A
character AutoCAD could not store appears as ``%%ddd`` (decimal byte), and digits are stored in reverse order
("051" is 150).

The table below was built by reading the plan's legend: each entry was confirmed in a word of the legend or notes
(مسکونی, تجاری, حریم کمی قنات ...). Bytes not in the table decode to ``<xx>`` so a gap is visible, never guessed.
"""
import re

KB = dict(zip("qwertyuiop[]asdfghjkl;'zxcvbnm,", "ضصثقفغعهخحجچشسیبلاتنمکگظطزرذدپو"))
KB.update({'H': 'آ', '`': 'پ', '{': 'ج', '}': 'چ', '|': 'ژ', ':': 'ک', '"': 'گ', '<': 'و', '>': '.'})

HIGH = {
    0x97: 'ا', 0x8b: 'ی', 0xa2: 'ن', 0x8c: 'ی', 0x8d: 'ی', 0xc1: 'ر', 0xe2: 'و', 0xb8: 'س', 0xdc: 'ک', 0xa0: 'ن',
    0xdf: 'گ', 0xa3: 'م', 0xb5: 'ق', 0x82: 'ش', 0x9b: 'ه', 0x9c: 'ه', 0xa4: 'م', 0x85: 'ذ', 0x91: 'ب', 0x93: 'ب',
    0x9d: 'ت', 0xd0: 'ج', 0x9a: 'ه', 0x88: 'ز', 0x95: 'ل', 0x96: 'ل', 0xb2: 'ض', 0xbb: 'ف', 0xaf: 'ح', 0xa9: 'د',
    0x9e: 'ت', 0xa1: 'ن', 0xc7: 'ط', 0xa5: 'م', 0xbe: 'ع', 0x94: 'س', 0xde: 'ک', 0xba: 'ی', 0x92: '؟',
    0xbd: 'ف', 0xcd: 'ظ', 0xdd: 'ک', 0xcc: 'غ', 0xe0: 'گ', 0xc4: 'ص', 0x84: 'ش',     # word-final forms, read off the legend rows
    0x9f: 'ت', 0xc9: 'ط', 0xca: 'غ', 0xc0: 'ع', 0xac: 'خ', 0x83: 'ش', 0xc8: 'ط', 0xb9: 'س', 0xeb: 'ل', 0xb1: 'ح', 0x90: 'ث',
}


def to_bytes(text):
    out = bytearray()
    for ch in re.sub(r'%%(\d{3})', lambda m: chr(int(m.group(1))), text):
        o = ord(ch)
        if o < 128 or 0x80 <= o <= 0xFF:
            out.append(o)
            continue
        for codec in ('cp1252', 'cp1256'):
            try:
                out += ch.encode(codec)
                break
            except UnicodeEncodeError:
                continue
        else:
            out += b'?'
    return bytes(out)


def decode(text):
    out = []
    for c in to_bytes(text):
        if c < 128:
            out.append(KB.get(chr(c), chr(c)))
        else:
            out.append(HIGH.get(c, f'<{c:02x}>'))
    return ''.join(out)


def reverse_digit_runs(text):
    """Digits are stored last-to-first in these strings ("051" -> "150")."""
    return re.sub(r'\d+', lambda m: m.group(0)[::-1], text)


def read(text):
    """The Persian text of ``text`` as stored in the drawing, digits in reading order."""
    return reverse_digit_runs(decode(text))
