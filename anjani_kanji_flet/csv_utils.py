from __future__ import annotations


def parse_csv(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    row: list[str] = []
    field = ""
    i = 0
    in_quotes = False
    while i < len(text):
        char = text[i]
        if in_quotes:
            if char == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    field += '"'
                    i += 2
                    continue
                in_quotes = False
                i += 1
                continue
            field += char
            i += 1
            continue
        if char == '"':
            in_quotes = True
            i += 1
            continue
        if char == ",":
            row.append(field)
            field = ""
            i += 1
            continue
        if char == "\r":
            i += 1
            continue
        if char == "\n":
            row.append(field)
            field = ""
            if any(cell.strip() for cell in row):
                rows.append(row)
            row = []
            i += 1
            continue
        field += char
        i += 1

    if field or row:
        row.append(field)
        if any(cell.strip() for cell in row):
            rows.append(row)
    return rows


def rows_to_kanji(rows: list[list[str]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in rows:
        character = (row[0] if row else "").strip()
        if not character:
            continue
        meanings = [cell.strip() for cell in row[1:] if cell.strip()]
        result.append({"character": character, "meanings": meanings})
    return result
