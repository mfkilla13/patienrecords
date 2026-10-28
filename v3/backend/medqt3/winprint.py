"""Send a PDF to a Windows printer at exactly 100% scale.

Each page is rendered at the printer's resolution and placed so that PDF point
(0, 0) lands on the paper's top-left corner: the printer's unprintable margin
(PHYSICALOFFSET) is subtracted, never scaled away. This keeps "start 118 mm
from the top" true on paper, which is what continuing a sheet relies on.
"""

from __future__ import annotations

MAX_DPI = 600


def printers() -> dict:
    import win32print

    names = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
    try:
        default = win32print.GetDefaultPrinter()
    except Exception:  # no default printer configured
        default = names[0] if names else None
    return {"printers": names, "default": default}


def print_pdf(pdf_bytes: bytes, printer: str, title: str, output_file: str | None = None) -> None:
    """output_file is for testing with "Microsoft Print to PDF" (writes the file without a dialog)."""
    import pypdfium2
    import win32con
    import win32ui
    from PIL import ImageWin

    doc = pypdfium2.PdfDocument(pdf_bytes)
    dc = win32ui.CreateDC()
    dc.CreatePrinterDC(printer)
    try:
        dpi = min(dc.GetDeviceCaps(win32con.LOGPIXELSX), MAX_DPI)
        dev_dpi_x = dc.GetDeviceCaps(win32con.LOGPIXELSX)
        dev_dpi_y = dc.GetDeviceCaps(win32con.LOGPIXELSY)
        off_x = dc.GetDeviceCaps(win32con.PHYSICALOFFSETX)
        off_y = dc.GetDeviceCaps(win32con.PHYSICALOFFSETY)
        dc.StartDoc(title, output_file) if output_file else dc.StartDoc(title)
        for page in doc:
            w_pt, h_pt = page.get_size()
            bitmap = page.render(scale=dpi / 72, grayscale=True).to_pil()
            # Target rectangle in device pixels: full paper size, shifted by the unprintable offset.
            w_dev = round(w_pt / 72 * dev_dpi_x)
            h_dev = round(h_pt / 72 * dev_dpi_y)
            dc.StartPage()
            ImageWin.Dib(bitmap).draw(dc.GetHandleOutput(), (-off_x, -off_y, w_dev - off_x, h_dev - off_y))
            dc.EndPage()
        dc.EndDoc()
    finally:
        dc.DeleteDC()
