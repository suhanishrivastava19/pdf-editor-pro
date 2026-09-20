"""Custom exception hierarchy.

Every error surfaced to the GUI derives from :class:`PDFEditorError`, so the
UI can show a friendly message without ever crashing on a bad file.
"""


class PDFEditorError(Exception):
    """Base class for all application errors."""


class FileAccessError(PDFEditorError):
    """The file is missing, unreadable or cannot be written."""


class CorruptedPDFError(PDFEditorError):
    """The file is not a valid PDF or is damaged beyond repair."""


class PasswordRequiredError(PDFEditorError):
    """The PDF is encrypted and no (or a wrong) password was supplied."""


class InvalidPageRangeError(PDFEditorError):
    """A page selection such as ``1-3,5`` could not be parsed or is out of range."""


class OperationError(PDFEditorError):
    """A PDF operation failed for a reason not covered by other errors."""
