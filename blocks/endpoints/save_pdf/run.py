"""Save PDF — export report or results as a PDF document."""

import json
import os
from datetime import datetime, timezone

try:
    from backend.block_sdk.exceptions import (
        BlockConfigError, BlockInputError, BlockDataError,
        BlockDependencyError, BlockExecutionError,
    )
except ImportError:
    class BlockConfigError(ValueError):
        def __init__(self, field, message, **kw): super().__init__(message)
    class BlockInputError(ValueError):
        def __init__(self, message, **kw): super().__init__(message)
    class BlockDataError(ValueError):
        pass
    class BlockDependencyError(ImportError):
        def __init__(self, dep, message="", **kw): super().__init__(message or dep)
    class BlockExecutionError(RuntimeError):
        def __init__(self, message, **kw): super().__init__(message)


def _normalize_rows(data):
    """Extract tabular data if present."""
    if isinstance(data, list) and all(isinstance(r, dict) for r in data):
        return data
    if isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list):
            return data["data"]
    return None


def _collect_headers(rows):
    seen = {}
    for row in rows:
        for key in row:
            if key not in seen:
                seen[key] = True
    return list(seen.keys())


def _build_pdf_fpdf(data, out_filepath, title, page_size, orientation, include_charts, include_timestamp, font_size=10, header_text="", footer_text="", max_rows=500):
    """Build PDF using fpdf2 library."""
    from fpdf import FPDF

    orient = "P" if orientation == "portrait" else "L"

    class BlueprintPDF(FPDF):
        def header(self):
            if header_text:
                self.set_font("Helvetica", "I", 8)
                self.cell(0, 6, header_text, ln=True, align="C")
                self.ln(2)

        def footer(self):
            self.set_y(-15)
            self.set_font("Helvetica", "I", 8)
            ft = footer_text if footer_text else f"Page {self.page_no()}/{{nb}}"
            self.cell(0, 10, ft, align="C")

    pdf = BlueprintPDF(orientation=orient, format=page_size)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, title, ln=True, align="C")
    pdf.ln(4)

    # Timestamp
    if include_timestamp:
        pdf.set_font("Helvetica", "", 9)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        pdf.cell(0, 6, f"Generated: {ts}", ln=True, align="C")
        pdf.ln(6)

    # Horizontal rule
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, pdf.get_y(), pdf.w - 10, pdf.get_y())
    pdf.ln(6)

    # Try to render as table
    rows = _normalize_rows(data)
    if rows:
        headers = _collect_headers(rows)
        num_cols = max(len(headers), 1)
        col_width = (pdf.w - 20) / num_cols
        col_width = min(col_width, 60)

        pdf.set_font("Helvetica", "B", 10)
        # Header row
        for h in headers:
            pdf.cell(col_width, 8, str(h)[:20], border=1, align="C")
        pdf.ln()

        # Data rows
        pdf.set_font("Helvetica", "", font_size)
        for row in rows[:max_rows]:
            for h in headers:
                val = str(row.get(h, ""))[:25]
                pdf.cell(col_width, 7, val, border=1)
            pdf.ln()

        pdf.ln(4)
        pdf.set_font("Helvetica", "I", 9)
        total = len(rows)
        shown = min(total, max_rows)
        pdf.cell(0, 6, f"Showing {shown} of {total} rows", ln=True)

        # Simple chart: bar chart of numeric columns
        if include_charts:
            numeric_cols = []
            for h in headers:
                vals = [row.get(h) for row in rows if isinstance(row.get(h), (int, float))]
                if len(vals) >= 2:
                    numeric_cols.append((h, vals))

            if numeric_cols:
                pdf.add_page()
                pdf.set_font("Helvetica", "B", 14)
                pdf.cell(0, 10, "Summary Charts", ln=True, align="C")
                pdf.ln(4)

                for col_name, vals in numeric_cols[:4]:  # Max 4 charts
                    pdf.set_font("Helvetica", "B", 10)
                    avg_val = sum(vals) / len(vals)
                    min_val = min(vals)
                    max_val = max(vals)
                    pdf.cell(0, 7, f"{col_name}: min={min_val:.4g}, avg={avg_val:.4g}, max={max_val:.4g}", ln=True)
                    pdf.ln(2)

    elif isinstance(data, dict):
        # Check for text content first
        if "text" in data and isinstance(data["text"], str):
            pdf.set_font("Helvetica", "", font_size)
            pdf.multi_cell(0, 6, data["text"][:5000])
        else:
            # Render dict as key-value pairs
            pdf.set_font("Helvetica", "", font_size)
            for key, value in data.items():
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(60, 7, str(key), border=1)
                pdf.set_font("Helvetica", "", 10)
                val_str = str(value)[:100]
                pdf.cell(0, 7, val_str, border=1, ln=True)
    elif isinstance(data, str):
        # Render text content
        pdf.set_font("Helvetica", "", font_size)
        pdf.multi_cell(0, 6, data[:5000])
    else:
        pdf.set_font("Helvetica", "", font_size)
        pdf.multi_cell(0, 6, str(data)[:5000])

    pdf.output(out_filepath)


def _build_pdf_fallback(data, out_filepath, title, include_timestamp):
    """Fallback: write a styled text file when fpdf2 is not available."""
    lines = [f"=== {title} ===", ""]
    if include_timestamp:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"Generated: {ts}")
        lines.append("")

    rows = _normalize_rows(data)
    if rows:
        headers = _collect_headers(rows)
        lines.append(" | ".join(headers))
        lines.append("-" * (len(" | ".join(headers))))
        for row in rows[:100]:
            lines.append(" | ".join(str(row.get(h, "")) for h in headers))
    elif isinstance(data, dict):
        if "text" in data and isinstance(data["text"], str):
            lines.append(data["text"][:5000])
        else:
            for k, v in data.items():
                lines.append(f"{k}: {v}")
    else:
        lines.append(str(data)[:5000])

    # Write as text since fpdf2 is not available
    base, _ = os.path.splitext(out_filepath)
    txt_path = base + ".txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return txt_path


def run(ctx):
    output_path = ctx.config.get("output_path", "./output").strip()
    filename = ctx.config.get("filename", "report.pdf").strip()
    title = ctx.config.get("title", "Pipeline Report").strip()
    page_size = ctx.config.get("page_size", "A4")
    orientation = ctx.config.get("orientation", "portrait")
    include_charts = ctx.config.get("include_charts", True)
    include_timestamp = ctx.config.get("include_timestamp", True)
    overwrite = ctx.config.get("overwrite_existing", True)
    font_size = int(ctx.config.get("font_size", 10))
    header_text = ctx.config.get("header_text", "").strip()
    footer_text = ctx.config.get("footer_text", "").strip()
    max_rows = int(ctx.config.get("max_rows", 500))

    ctx.log_message("Save PDF starting")
    ctx.report_progress(0, 3)

    # ── Loop-aware file handling ──
    loop = ctx.get_loop_metadata()
    if isinstance(loop, dict):
        file_mode = loop.get("file_mode", "overwrite")
        iteration = loop.get("iteration", 0)
        ctx.log_message(f"[Loop iter {iteration}] file_mode={file_mode}")
        if file_mode == "append":
            ctx.log_message("WARNING: PDF format does not support append mode, using overwrite")
            file_mode = "overwrite"
    else:
        file_mode = "overwrite"
        iteration = 0

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 3)
    raw_data = ctx.resolve_as_data("data")
    if not raw_data:
        raise BlockInputError(
            "No input data provided. Connect a 'data' input.",
            recoverable=False,
        )

    data = raw_data

    # Load optional report config
    try:
        report_config = ctx.resolve_as_dict("config")
        if isinstance(report_config, dict):
            title = report_config.get("title", title)
            page_size = report_config.get("page_size", page_size)
    except (KeyError, ValueError):
        pass

    # ---- Step 2: Resolve path ----
    ctx.report_progress(2, 3)
    if os.path.isabs(output_path):
        out_dir = output_path
    else:
        out_dir = os.path.join(ctx.run_dir, output_path)
    os.makedirs(out_dir, exist_ok=True)

    if not filename.endswith(".pdf"):
        filename += ".pdf"

    # Loop versioned: create iteration-specific filename
    if file_mode == "versioned":
        base, fext = os.path.splitext(filename)
        filename = f"{base}_iter{iteration}{fext}"

    out_filepath = os.path.join(out_dir, filename)

    if os.path.exists(out_filepath) and not overwrite:
        raise BlockInputError(
            f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.",
            recoverable=True,
        )

    # ---- Step 3: Generate PDF ----
    actual_format = "pdf"
    is_simulated = False
    try:
        _build_pdf_fpdf(data, out_filepath, title, page_size, orientation, include_charts, include_timestamp, font_size, header_text, footer_text, max_rows)
        ctx.log_message("PDF generated using fpdf2")
    except ImportError:
        ctx.log_message("⚠️ SIMULATION MODE: fpdf2 not installed. Generating text-only fallback report. Install fpdf2 for real PDF output: pip install fpdf2")
        is_simulated = True
        out_filepath = _build_pdf_fallback(data, out_filepath, title, include_timestamp)
        actual_format = "txt_fallback"

    ctx.log_metric("simulation_mode", 1.0 if is_simulated else 0.0)

    ctx.report_progress(3, 3)
    file_size = os.path.getsize(out_filepath)
    ctx.log_message(f"Saved report to {out_filepath} ({file_size:,} bytes)")

    ctx.save_output("file_path", out_filepath)
    ctx.save_output("summary", {
        "file_size_bytes": file_size,
        "page_size": page_size,
        "format": actual_format,
    })
    ctx.save_artifact("pdf_report", out_filepath)
    ctx.log_metric("file_size_bytes", float(file_size))

    ctx.log_message("Save PDF complete.")
