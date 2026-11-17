"""CSV writer for files people open in Excel, Numbers or Google Sheets.

A text cell that starts with = + - @ (or a tab / carriage return) is read as a formula by spreadsheets ("CSV
injection"). Creator names, product names and, above all, audience quotes copied from the internet end up in these
files, so such cells get a leading apostrophe. Numbers (including negative amounts like -5.00) are left alone.
"""
import csv
import re

_NUMBER = re.compile(r"^[-+]?\d[\d,]*(\.\d+)?$")


def safe_cell(v):
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") and not _NUMBER.match(v):
        return "'" + v
    return v


class _Writer:
    def __init__(self, f, **kw):
        self._w = csv.writer(f, **kw)

    def writerow(self, row):
        return self._w.writerow([safe_cell(v) for v in row])

    def writerows(self, rows):
        for r in rows:
            self.writerow(r)


def writer(f, **kw):
    return _Writer(f, **kw)
