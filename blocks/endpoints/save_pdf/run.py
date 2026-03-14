"""Save PDF — export report or results as a PDF document."""

import csv as csv_mod
import json
import os
from datetime import datetime, timezone

from backend.block_sdk.exceptions import BlockInputError


def _read_jsonl(f):
    """Read JSONL file with per-line error handling."""
    records = []
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"_raw_line": line, "_parse_error": True})
    return records


def _resolve_data(raw):
    """Resolve raw input to a Python object, handling any upstream format."""
    if isinstance(raw, str):
        if os.path.isfile(raw):
            ext = os.path.splitext(raw)[1].lower()
            try:
                if ext == ".jsonl":
                    with open(raw, "r", encoding="utf-8", errors="replace") as f:
                        return _read_jsonl(f)
                elif ext in (".json",):
                    with open(raw, "r", encoding="utf-8") as f:
                        return json.load(f)
                elif ext == ".csv":
                    with open(raw, "r", encoding="utf-8", errors="replace") as f:
                        return list(csv_mod.DictReader(f))
                elif ext in (".yaml", ".yml"):
                    try:
                        import yaml
                        with open(raw, "r", encoding="utf-8") as f:
                            result = yaml.safe_load(f)
                            return result if result is not None else {}
                    except ImportError:
                        with open(raw, "r", encoding="utf-8", errors="replace") as f:
                            return {"text": f.read()}
                else:
                    with open(raw, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    try:
                        return json.loads(content)
                    except (json.JSONDecodeError, ValueError):
                        return {"text": content}
            except (UnicodeDecodeError, json.JSONDecodeError):
                return {"text": f"<unreadable file: {os.path.basename(raw)}>"}
        if os.path.isdir(raw):
            for name in ("data.json", "results.json", "output.json", "data.csv", "data.yaml"):
                fpath = os.path.join(raw, name)
                if os.path.isfile(fpath):
                    return _resolve_data(fpath)
            try:
                files = [f for f in os.listdir(raw) if not f.startswith(".")]
            except OSError:
                files = []
            return {"text": f"Directory: {raw}\nFiles: {', '.join(files)}"}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {"text": raw}
    if isinstance(raw, (dict, list)):
        return raw
    return {"text": str(raw)}


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

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 3)
    raw_data = ctx.load_input("data")
    if raw_data is None:
        raise BlockInputError(
            "No input data provided. Connect a 'data' input.",
            recoverable=False,
        )

    data = _resolve_data(raw_data)

    # Load optional report config
    try:
        report_config = ctx.load_input("config")
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
    out_filepath = os.path.join(out_dir, filename)

    if os.path.exists(out_filepath) and not overwrite:
        raise BlockInputError(
            f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.",
            recoverable=True,
        )

    # ---- Step 3: Generate PDF ----
    actual_format = "pdf"
    try:
        _build_pdf_fpdf(data, out_filepath, title, page_size, orientation, include_charts, include_timestamp, font_size, header_text, footer_text, max_rows)
        ctx.log_message("PDF generated using fpdf2")
    except ImportError:
        ctx.log_message("WARNING: fpdf2 not installed. Install with: pip install fpdf2. Falling back to text report.")
        out_filepath = _build_pdf_fallback(data, out_filepath, title, include_timestamp)
        actual_format = "txt_fallback"

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
