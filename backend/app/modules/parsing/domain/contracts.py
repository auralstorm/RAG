"""Parser output carries source evidence, never SDK objects, URLs or authorization."""

from enum import StrEnum
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from app.core.contracts import VersionedContract
from app.modules.documents.domain.contracts import DocumentMimeType, DocumentVersionRef, StoredObjectRef
from app.modules.knowledge_base.domain.contracts import ConfigurationVersion, ContentHash


class BoundingBox(VersionedContract):
    """Normalized [0,1] coordinates, origin at the page's top-left, in displayed orientation."""

    left: float = Field(ge=0, le=1, allow_inf_nan=False)
    top: float = Field(ge=0, le=1, allow_inf_nan=False)
    right: float = Field(ge=0, le=1, allow_inf_nan=False)
    bottom: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def require_positive_area(self) -> Self:
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("Source bounding boxes require positive area")
        return self


class PdfSourceLocation(VersionedContract):
    kind: Literal["pdf"] = "pdf"
    page_no: int = Field(ge=1, strict=True)
    bbox: BoundingBox | None = None


class MarkdownSourceLocation(VersionedContract):
    """Half-open Unicode code-point offsets in the original decoded Markdown source."""

    kind: Literal["markdown"] = "markdown"
    char_start: int = Field(ge=0, strict=True)
    char_end: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def require_nonempty_range(self) -> Self:
        if self.char_end <= self.char_start:
            raise ValueError("Markdown source offsets require a nonempty half-open range")
        return self


class DocxSourceLocation(VersionedContract):
    """Zero-based body element index, counting paragraphs and tables in original order."""

    kind: Literal["docx"] = "docx"
    element_index: int = Field(ge=0, strict=True)
    element_type: Literal["paragraph", "table"]


type SourceLocation = Annotated[
    PdfSourceLocation | MarkdownSourceLocation | DocxSourceLocation, Field(discriminator="kind")
]


class ParsedBlockType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    CAPTION = "caption"


class ParsedTable(VersionedContract):
    """Rectangular normalized cell text; unsupported structural loss needs a parser warning."""

    rows: tuple[tuple[str, ...], ...] = Field(min_length=1, repr=False)

    @model_validator(mode="after")
    def require_rectangular_cells(self) -> Self:
        width = len(self.rows[0])
        if not width or any(len(row) != width for row in self.rows):
            raise ValueError("Normalized table rows must have the same nonzero column count")
        return self


class ParsedBlock(VersionedContract):
    block_id: str = Field(min_length=1, max_length=128, pattern=r"\S")
    block_type: ParsedBlockType
    text: str = Field(min_length=1, pattern=r"\S", repr=False)
    heading_path: tuple[str, ...] = ()
    source_location: SourceLocation
    table: ParsedTable | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def require_matching_structure(self) -> Self:
        if (self.block_type is ParsedBlockType.TABLE) != (self.table is not None):
            raise ValueError("Table blocks require structured cells; other blocks cannot carry a table")
        if any(not heading.strip() for heading in self.heading_path):
            raise ValueError("Heading paths cannot contain blank entries")
        return self


class ParsedPage(VersionedContract):
    """PDF has real page numbers; unpaginated sources use one container with page_no=None."""

    page_no: int | None = Field(ge=1, strict=True)
    blocks: tuple[ParsedBlock, ...] = Field(repr=False)


class ParsingWarning(VersionedContract):
    """Stable adapter-mapped warning code; raw parser exception text is absent."""

    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")
    source_location: SourceLocation | None = None


class ParsedDocumentMetadata(VersionedContract):
    title: str | None = Field(default=None, min_length=1, max_length=512, repr=False)
    language: str | None = Field(default=None, min_length=2, max_length=35, pattern=r"^[A-Za-z][A-Za-z0-9-]*$")


class ParsedDocument(DocumentVersionRef):
    file_hash: ContentHash
    mime_type: DocumentMimeType
    parser_name: str = Field(min_length=1, max_length=64, pattern=r"\S")
    parser_version: ConfigurationVersion
    pages: tuple[ParsedPage, ...] = Field(min_length=1, repr=False)
    warnings: tuple[ParsingWarning, ...] = ()
    metadata: ParsedDocumentMetadata = Field(default_factory=ParsedDocumentMetadata)

    @model_validator(mode="after")
    def require_source_consistency(self) -> Self:
        is_pdf = self.mime_type == "application/pdf"
        kind = "pdf" if is_pdf else "markdown" if self.mime_type == "text/markdown" else "docx"
        if is_pdf:
            numbers = [page.page_no for page in self.pages]
            if numbers != list(range(1, len(self.pages) + 1)):
                raise ValueError("PDF pages must retain contiguous one-based original page numbers")
        elif len(self.pages) != 1 or self.pages[0].page_no is not None:
            raise ValueError("Unpaginated sources require one container without an invented page number")
        block_ids: set[str] = set()
        for page in self.pages:
            for block in page.blocks:
                if block.block_id in block_ids:
                    raise ValueError("Parsed block IDs must be unique within a document version")
                block_ids.add(block.block_id)
                if block.source_location.kind != kind:
                    raise ValueError("Block source location does not match the document format")
                if (
                    isinstance(block.source_location, PdfSourceLocation)
                    and block.source_location.page_no != page.page_no
                ):
                    raise ValueError("Block source page does not match its containing page")
        for warning in self.warnings:
            location = warning.source_location
            if location is not None and (
                location.kind != kind
                or (isinstance(location, PdfSourceLocation) and location.page_no > len(self.pages))
            ):
                raise ValueError("Parser warning location does not belong to this source")
        return self


class ParserInput(DocumentVersionRef):
    """Private input resolved by a trusted ingestion use case after source authorization."""

    mime_type: DocumentMimeType
    original: StoredObjectRef = Field(repr=False)


class Parser(Protocol):
    """Adapter owns bounded execution and output mapping; ingestion owns state and storage."""

    async def parse(self, source: ParserInput) -> ParsedDocument: ...
