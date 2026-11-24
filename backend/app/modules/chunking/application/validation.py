"""Source relationships and parent containment are checked without creating chunks or IO."""

from app.modules.chunking.domain.contracts import Chunk, ChunkRole
from app.modules.parsing.domain.contracts import ParsedDocument


def validate_chunk_set(parsed: ParsedDocument, chunks: tuple[Chunk, ...]) -> tuple[Chunk, ...]:
    """Validate version, text evidence and parents; token measurement belongs to the tokenizer adapter."""
    blocks = {block.block_id: block for page in parsed.pages for block in page.blocks}
    block_order = {block_id: index for index, block_id in enumerate(blocks)}
    by_id = {chunk.id: chunk for chunk in chunks}
    if len(by_id) != len(chunks) or len({chunk.chunk_index for chunk in chunks}) != len(chunks):
        raise ValueError("Chunk IDs and indices must be unique within a version")
    configurations = {(chunk.chunking_config_version, chunk.tokenizer_version) for chunk in chunks}
    if len(configurations) > 1:
        raise ValueError("One chunk set must use one chunking and tokenizer configuration")
    for chunk in chunks:
        if any(
            getattr(chunk, field) != getattr(parsed, field)
            for field in ("kb_id", "document_id", "document_version_id", "document_version")
        ):
            raise ValueError("Chunk belongs to another document version")
        slices: list[str] = []
        previous_order, previous_end = -1, 0
        for span in chunk.source.spans:
            block = blocks.get(span.block_id)
            if block is None or span.location != block.source_location or span.char_end > len(block.text):
                raise ValueError("Chunk source span is missing, out of bounds or has incorrect source coordinates")
            order = block_order[span.block_id]
            if order < previous_order or (order == previous_order and span.char_start < previous_end):
                raise ValueError("Chunk spans must follow parsed reading order without repeating source text")
            previous_order, previous_end = order, span.char_end
            slices.append(block.text[span.char_start : span.char_end])
        if chunk.content != "\n\n".join(slices):
            raise ValueError("Chunk text must equal its ordered source slices joined by two newlines")
        if chunk.metadata.heading_path != blocks[chunk.source.spans[0].block_id].heading_path:
            raise ValueError("Chunk heading path must match its first source block")
        if chunk.role is ChunkRole.CHILD:
            parent = by_id.get(chunk.parent_chunk_id) if chunk.parent_chunk_id is not None else None
            if parent is None or parent.role is not ChunkRole.PARENT:
                raise ValueError("Child chunk requires a parent in the same validated set")
            for span in chunk.source.spans:
                if not any(
                    source.block_id == span.block_id
                    and source.location == span.location
                    and source.char_start <= span.char_start < span.char_end <= source.char_end
                    for source in parent.source.spans
                ):
                    raise ValueError("Child source evidence is outside its parent")
    return chunks
