import pymupdf


def extract_pdf(data: bytes, max_pages: int) -> list[dict]:
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass:
                raise ValueError("Password-protected PDFs are unsupported.")
            if not 0 < len(doc) <= max_pages:
                raise ValueError(f"PDF must contain 1 to {max_pages} pages.")
            pages = []
            for number, page in enumerate(doc, 1):
                text = page.get_text(sort=True)
                # Image-only pages need review; sparse text dividers do not automatically fail.
                substantial_image = any(
                    pymupdf.Rect(info["bbox"]).get_area() > page.rect.get_area() * 0.65
                    for info in page.get_image_info()
                )
                image_only = len(text.strip()) < 50 and substantial_image
                pages.append(
                    {
                        "number": number,
                        "text": text,
                        "warning": "Image-only page; OCR is not supported." if image_only else None,
                    }
                )
            if not any(p["text"].strip() for p in pages):
                raise ValueError("No extractable text. OCR is not supported in v1.")
            return pages
    except (pymupdf.FileDataError, pymupdf.EmptyFileError, RuntimeError) as exc:
        raise ValueError("Invalid or unreadable PDF.") from exc


def make_chunks(pages: list[dict], size: int, overlap: int) -> list[dict]:
    """Sliding character windows preserve every page and literal source text.

    Include the preceding page tail as context, without assigning an agency heuristically.
    Each source segment retains its physical page number.
    """
    if overlap >= size:
        raise ValueError("Overlap must be smaller than chunk size.")
    segments, offset = [], 0
    for p in pages:
        text = p["text"]
        segments.append((offset, offset + len(text), p["number"], text))
        offset += len(text)
    chunks = []
    start = 0
    while start < offset:
        end = min(start + size, offset)
        parts = []
        for left, right, number, text in segments:
            if left < end and right > start:
                parts.append({"page": number, "text": text[max(0, start - left) : end - left]})
        if parts:
            first_page = parts[0]["page"]
            context = [p for p in pages if p["number"] == first_page - 1]
            context_parts = (
                [{"page": p["number"], "text": p["text"][-overlap:]} for p in context]
                if overlap
                else []
            )
            chunks.append({"index": len(chunks), "parts": context_parts + parts})
        if end == offset:
            break
        start = end - overlap
    return chunks
