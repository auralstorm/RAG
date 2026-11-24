"""Source binding guard shared by parser adapters without executing a parser."""

from app.modules.parsing.domain.contracts import ParsedDocument, ParserInput


def validate_parser_output(source: ParserInput, parsed: ParsedDocument) -> ParsedDocument:
    """Reject another version/format/digest; real format detection and parser quality remain adapter checks."""
    if (
        any(
            getattr(source, field) != getattr(parsed, field)
            for field in ("kb_id", "document_id", "document_version_id", "document_version", "mime_type")
        )
        or source.original.sha256 != parsed.file_hash
    ):
        raise ValueError("Parser output does not belong to the authorized source version")
    return parsed
