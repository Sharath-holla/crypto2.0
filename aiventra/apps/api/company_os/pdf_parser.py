"""Fixed parser entrypoint, executed only in a resource-limited child process."""

import io
import json
import logging
import sys

if __name__ == "__main__":
    # Trusted interpreter site directory, never derived from the PDF or its filename.
    sys.path.insert(0, sys.argv[2])


def parse(raw, page_limit):
    import pypdf
    from pypdf.generic import DictionaryObject, IndirectObject, StreamObject

    if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-1024:]:
        raise ValueError()
    pypdf.overwrite_configuration(
        zlib_maximum_output_length=262144,
        maximum_declared_stream_length=1048576,
        array_based_stream_maximum_output_length=262144,
    )
    reader = pypdf.PdfReader(io.BytesIO(raw), strict=True, root_object_recovery_limit=1000)
    if (
        reader.is_encrypted
        or sum(len(rows) for rows in reader.xref.values()) + len(reader.xref_objStm) > 5000
    ):
        raise ValueError()
    forbidden = {
        "/JS",
        "/JavaScript",
        "/AA",
        "/OpenAction",
        "/Launch",
        "/EmbeddedFiles",
        "/EF",
        "/XFA",
        "/RichMedia",
    }
    references_by_generation = {**reader.xref}
    references_by_generation[0] = {**reader.xref.get(0, {}), **reader.xref_objStm}
    for generation, references in references_by_generation.items():
        for identity in references:
            if not identity:
                continue
            obj = reader.get_object(IndirectObject(identity, generation, reader))
            pending = [obj]
            seen = set()
            while pending:
                value = pending.pop()
                if id(value) in seen:
                    continue
                seen.add(id(value))
                if isinstance(value, DictionaryObject):
                    if forbidden.intersection(value):
                        raise ValueError()
                    if isinstance(value, StreamObject) and value.get("/Subtype") != "/Image":
                        filters = value.get("/Filter", [])
                        if isinstance(filters, str):
                            filters = [filters]
                        if any(item != "/FlateDecode" for item in filters):
                            raise ValueError()
                    pending.extend(child for child in value.values() if not isinstance(child, IndirectObject))
                elif isinstance(value, list):
                    pending.extend(child for child in value if not isinstance(child, IndirectObject))
    if not 1 <= len(reader.pages) <= page_limit:
        raise ValueError()
    content, pages = "", []
    for number, page in enumerate(reader.pages, 1):
        stream = page.get_contents()
        if stream and len(stream.get_data()) > 262144:
            raise ValueError()
        text = page.extract_text() or ""
        content += f"[Page {number}]\n{text.strip()}\n"
        pages.append({"page": number, "has_text": bool(text.strip())})
        if len(content.encode()) > 64000:
            raise ValueError()
    if not any(page["has_text"] for page in pages):
        raise ValueError("No usable text extracted; image-only PDFs require OCR, which is unavailable")
    return {
        "content": content,
        "pages": pages,
        "page_count": len(pages),
        "parser_version": "bounded-pdf-v1/pypdf-" + pypdf.__version__,
    }


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        raw = sys.stdin.buffer.read(1048577)
        if len(raw) > 1048576:
            raise ValueError()
        print(json.dumps(parse(raw, int(sys.argv[1])), ensure_ascii=True))
    except Exception as exc:
        message = (
            "No usable text extracted; image-only PDFs require OCR, which is unavailable"
            if str(exc).startswith("No usable text")
            else "Invalid, encrypted, active-content or resource-limited PDF"
        )
        print(json.dumps({"error": message}))
        sys.exit(1)
