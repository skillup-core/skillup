Font Files for Skillup
=======================

This directory contains font files used across the Skillup application.

NanumGothic.ttf
---------------
Source: Naver NanumGothic (나눔고딕)
License: Open Font License (OFL)
URL: https://hangeul.naver.com/font

Modifications:
The original NanumGothic.ttf file contained legacy TSI (TrueType instruction)
tables (TSI0, TSI1, TSI2, TSI3, TSI5) that caused OpenType Sanitizer (OTS)
warnings in Chromium-based browsers:

  "Failed to decode downloaded font"
  "OTS parsing error: TSI3: zero-length table"

These warnings did not affect font rendering but polluted the console logs.
To resolve this issue, the TSI tables were removed using Python fonttools:

  from fontTools import ttLib
  font = ttLib.TTFont('NanumGothic.ttf')
  for table in ['TSI0', 'TSI1', 'TSI2', 'TSI3', 'TSI5']:
      if table in font:
          del font[table]
  font.save('NanumGothic.ttf')

The cleaned font file is functionally identical to the original, with only
the problematic TSI tables removed. Font size reduced from 4.5MB to 4.2MB.

D2Coding.ttf
------------
Source: Naver D2Coding
License: Open Font License (OFL)
URL: https://github.com/naver/d2codingfont

Used for monospace text (terminal logs, code display).

NotoEmoji-Regular.ttf
---------------------
Source: Google Noto Emoji
License: Open Font License (OFL)
URL: https://github.com/googlefonts/noto-emoji

Used for emoji support across all platforms.

Courgette-Regular.ttf
---------------------
Source: Google Fonts / Sorkin Type Co
License: Open Font License (OFL)
URL: https://github.com/google/fonts/tree/main/ofl/courgette

Modern cursive script font used for the "Skill" logo in the desktop UI.
Elegant, flowing letterforms with a contemporary handwritten style.
