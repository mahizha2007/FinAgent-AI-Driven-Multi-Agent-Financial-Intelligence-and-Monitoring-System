from __future__ import annotations

from io import BytesIO

import pandas as pd
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT

from utils.timezone import now_ist_iso


class ReportingService:
    """Generate downloadable financial intelligence reports."""

    @staticmethod
    def _escape_text(value: str) -> str:
        """Escape paragraph text after normalizing common glyph artifacts."""
        normalized = str(value).replace("â€¢", "•")
        return normalized.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _build_flowchart(self, line: str) -> Drawing:
        """Build a simple vertical flowchart from a FLOWCHART line."""
        nodes = [item.strip() for item in line.replace("FLOWCHART:", "", 1).split("->") if item.strip()]
        if not nodes:
            return Drawing(1, 1)
        box_width = 340
        box_height = 32
        gap = 20
        height = max(70, (len(nodes) * (box_height + gap)) + 20)
        drawing = Drawing(430, height)
        center_x = 215
        top_y = height - 18

        for index, label in enumerate(nodes):
            y = top_y - ((index + 1) * (box_height + gap))
            x = center_x - (box_width / 2)
            drawing.add(
                Rect(
                    x,
                    y,
                    box_width,
                    box_height,
                    rx=10,
                    ry=10,
                    fillColor=colors.HexColor("#f5f8fc"),
                    strokeColor=colors.HexColor("#7dd3fc"),
                    strokeWidth=1.1,
                )
            )
            drawing.add(
                String(
                    center_x,
                    y + 10,
                    label[:72],
                    fontName="Helvetica-Bold",
                    fontSize=9.5,
                    textAnchor="middle",
                    fillColor=colors.HexColor("#0b2240"),
                )
            )
            if index < len(nodes) - 1:
                line_top = y - 4
                line_bottom = y - gap + 8
                drawing.add(Line(center_x, line_top, center_x, line_bottom, strokeColor=colors.HexColor("#0ea5e9"), strokeWidth=1.4))
                drawing.add(
                    Polygon(
                        [center_x, line_bottom - 4, center_x - 4, line_bottom + 4, center_x + 4, line_bottom + 4],
                        fillColor=colors.HexColor("#0ea5e9"),
                        strokeColor=colors.HexColor("#0ea5e9"),
                    )
                )
        return drawing

    def _build_styles(self, technical: bool = False):
        """Create the PDF style palette used by reports and manuals."""
        base = getSampleStyleSheet()
        return {
            "title": ParagraphStyle(
                "ManualTitle",
                parent=base["Title"],
                fontName="Helvetica-Bold",
                fontSize=24,
                leading=28,
                textColor=colors.HexColor("#13233b"),
                alignment=TA_CENTER,
                spaceAfter=8,
            ),
            "subtitle": ParagraphStyle(
                "ManualSubtitle",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=10.5,
                leading=14,
                textColor=colors.HexColor("#42556e"),
                alignment=TA_CENTER,
                spaceAfter=12,
            ),
            "section": ParagraphStyle(
                "ManualSection",
                parent=base["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=14,
                leading=18,
                textColor=colors.HexColor("#0f4370"),
                spaceBefore=8,
                spaceAfter=6,
                alignment=TA_LEFT,
            ),
            "body": ParagraphStyle(
                "ManualBody",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=10.3,
                leading=14.5,
                textColor=colors.HexColor("#182435"),
                alignment=TA_LEFT if technical else TA_JUSTIFY,
                spaceAfter=4,
            ),
            "bullet": ParagraphStyle(
                "ManualBullet",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=10.1,
                leading=14,
                leftIndent=16,
                firstLineIndent=-8,
                textColor=colors.HexColor("#182435"),
                spaceAfter=3,
            ),
            "formula": ParagraphStyle(
                "ManualFormula",
                parent=base["BodyText"],
                fontName="Courier",
                fontSize=9.6,
                leading=13.2,
                leftIndent=14,
                rightIndent=10,
                borderWidth=0.7,
                borderPadding=8,
                borderColor=colors.HexColor("#d6e7f7"),
                backColor=colors.HexColor("#f7fbff"),
                textColor=colors.HexColor("#15314d"),
                alignment=TA_LEFT,
                spaceAfter=5,
            ),
            "callout": ParagraphStyle(
                "ManualCallout",
                parent=base["BodyText"],
                fontName="Helvetica-Oblique",
                fontSize=9.8,
                leading=13.4,
                leftIndent=12,
                rightIndent=8,
                borderWidth=0.6,
                borderPadding=8,
                borderColor=colors.HexColor("#cae7ff"),
                backColor=colors.HexColor("#eef7ff"),
                textColor=colors.HexColor("#23445f"),
                alignment=TA_LEFT,
                spaceAfter=5,
            ),
            "caption": ParagraphStyle(
                "ManualCaption",
                parent=base["Italic"],
                fontName="Helvetica-Oblique",
                fontSize=9.2,
                leading=12,
                textColor=colors.HexColor("#5a6b80"),
                alignment=TA_LEFT,
                spaceAfter=6,
            ),
        }

    def _draw_document_chrome(self, canvas, doc, title: str, watermark_text: str) -> None:
        """Draw page header, footer, and watermark."""
        canvas.saveState()
        page_width, page_height = A4

        canvas.setFillColor(colors.HexColor("#f6f9fd"))
        canvas.rect(0, page_height - 48, page_width, 48, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#0f4370"))
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(doc.leftMargin, page_height - 30, title[:70])

        canvas.setStrokeColor(colors.HexColor("#d7e8ff"))
        canvas.setLineWidth(0.8)
        canvas.line(doc.leftMargin, page_height - 50, page_width - doc.rightMargin, page_height - 50)

        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(colors.HexColor("#6a7b8f"))
        canvas.drawString(doc.leftMargin, 20, f"Generated in IST | {now_ist_iso()}")
        canvas.drawRightString(page_width - doc.rightMargin, 20, f"Page {canvas.getPageNumber()}")

        canvas.translate(page_width / 2, page_height / 2)
        canvas.rotate(35)
        canvas.setFont("Helvetica-Bold", 44)
        canvas.setFillColor(colors.Color(0.2, 0.35, 0.55, alpha=0.08))
        canvas.drawCentredString(0, 0, watermark_text[:48])
        canvas.restoreState()

    def _build_pdf_from_lines(
        self,
        title: str,
        lines: list[str],
        subtitle: str | None = None,
        watermark_text: str = "Financial Operating System",
        technical: bool = False,
    ) -> bytes:
        """Build a styled PDF document from line-based content."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=0.65 * inch, rightMargin=0.65 * inch, topMargin=0.95 * inch, bottomMargin=0.7 * inch)
        styles = self._build_styles(technical=technical)
        safe_title = self._escape_text(title)
        story = [Paragraph(safe_title, styles["title"])]
        if subtitle:
            story.append(Paragraph(self._escape_text(subtitle), styles["subtitle"]))
        story.append(HRFlowable(width="100%", color=colors.HexColor("#cfe3f7"), thickness=1.2, spaceAfter=12, spaceBefore=2))

        for line in lines:
            raw = str(line).strip()
            if not raw:
                story.append(Spacer(1, 8))
                continue
            if raw.startswith("FLOWCHART:"):
                story.append(Paragraph("Flowchart", styles["section"]))
                story.append(Paragraph("The following diagram summarizes the operational sequence for this section.", styles["caption"]))
                story.append(self._build_flowchart(raw))
                story.append(Spacer(1, 10))
                continue
            safe = self._escape_text(raw)
            if safe.endswith(":") or (safe[:2].isdigit() and "." in safe[:5]):
                story.append(Paragraph(safe, styles["section"]))
                continue
            if raw.startswith("• ") or raw.startswith("- "):
                bullet_text = safe[2:].strip()
                story.append(Paragraph(f"&bull; {bullet_text}", styles["bullet"]))
                continue
            if safe.startswith("Step "):
                story.append(Paragraph(f"&bull; {safe}", styles["bullet"]))
                continue
            if raw.startswith("Important:") or raw.startswith("Interpretation:") or raw.startswith("Note:"):
                story.append(Paragraph(safe, styles["callout"]))
                continue
            if technical and (
                " = " in raw
                or raw.startswith("hybrid_score")
                or raw.startswith("profit =")
                or raw.startswith("z =")
                or raw.startswith("all_time_")
            ):
                story.append(Paragraph(safe, styles["formula"]))
                continue
            story.append(Paragraph(safe, styles["body"]))
        doc.build(
            story,
            onFirstPage=lambda canvas, doc_ref: self._draw_document_chrome(canvas, doc_ref, title, watermark_text),
            onLaterPages=lambda canvas, doc_ref: self._draw_document_chrome(canvas, doc_ref, title, watermark_text),
        )
        return buffer.getvalue()

    def build_master_draft_text(self, context: dict, username: str) -> str:
        """Build a text master draft from the live context."""
        latest = context["dataframe"].iloc[-1]
        latest_decision = context.get("latest_decision", {})
        alerts = context.get("alerts", [])
        alert_lines = "\n".join(
            f"- {item['transaction_id']} | {item['decision']} | risk={item.get('risk_probability', 0.0):.2f} | impact={item.get('financial_impact', 0.0):,.0f}"
            for item in alerts[:5]
        ) or "- No active alert records."

        insights = "\n".join(f"- {item}" for item in context.get("insights", []))
        decision_history_df = pd.DataFrame(context.get("decision_history", []))
        history_lines = "\n".join(
            f"- {row['event_time']} | {row['transaction_id']} | {row['decision']} | confidence={row['confidence_score']:.2f}"
            for _, row in decision_history_df.head(8).iterrows()
        ) if not decision_history_df.empty else "- No decision history available."

        return f"""Financial Decision Intelligence Master Draft

Prepared for: {username}
Generated at: {now_ist_iso()} IST

Executive Summary

- Latest transaction: {latest['transaction_id']}
- Latest revenue: {latest['revenue']:,.0f}
- Latest expenses: {latest['expenses']:,.0f}
- Latest anomaly score: {latest['anomaly_score']:.2f}
- Latest risk level: {latest['risk_level']}
- Decision: {latest_decision.get('decision', latest.get('decision', 'N/A'))}
- Risk probability: {latest_decision.get('risk_probability', 0.0):.2f}
- Confidence score: {latest_decision.get('confidence_score', 0.0):.2f}
- Financial impact: {latest_decision.get('financial_impact', 0.0):,.0f}

## Reasoning Trace

{latest_decision.get('reasoning_trace', 'No reasoning trace available.')}

## Recommended Action

{latest_decision.get('recommended_action', 'No recommendation available.')}

## Impact Chain

{latest_decision.get('impact_chain', 'No impact chain available.')}

## Financial Insights

{insights or '- No insights generated.'}

## Active Alerts

{alert_lines}

## Decision History

{history_lines}

## Governance Snapshot

- Email alerts enabled: {"Yes" if context.get("email_alert_enabled") else "No"}
- Model version records: {len(context.get("model_versions", []))}
"""

    def build_master_draft_pdf(self, context: dict, username: str) -> bytes:
        """Build a PDF master draft."""
        text = self.build_master_draft_text(context, username)
        return self._build_pdf_from_lines(
            "Financial Decision Intelligence Master Draft",
            text.splitlines(),
            subtitle="Executive report generated from the live decision context.",
            watermark_text="Financial Decision Draft",
        )

    def build_master_draft_csv(self, context: dict, username: str) -> bytes:
        """Build a CSV snapshot of key intelligence fields."""
        latest = context["dataframe"].iloc[-1]
        latest_decision = context.get("latest_decision", {})
        data = pd.DataFrame(
            [
                {"field": "prepared_for", "value": username},
                {"field": "generated_at_ist", "value": now_ist_iso()},
                {"field": "latest_transaction", "value": latest["transaction_id"]},
                {"field": "latest_revenue", "value": latest["revenue"]},
                {"field": "latest_expenses", "value": latest["expenses"]},
                {"field": "latest_anomaly_score", "value": latest["anomaly_score"]},
                {"field": "latest_risk_level", "value": latest["risk_level"]},
                {"field": "decision", "value": latest_decision.get("decision", "")},
                {"field": "risk_probability", "value": latest_decision.get("risk_probability", 0.0)},
                {"field": "confidence_score", "value": latest_decision.get("confidence_score", 0.0)},
                {"field": "financial_impact", "value": latest_decision.get("financial_impact", 0.0)},
                {"field": "recommended_action", "value": latest_decision.get("recommended_action", "")},
            ]
        )
        return data.to_csv(index=False).encode("utf-8")

    def build_logs_pdf(self, logs_df: pd.DataFrame) -> bytes:
        """Build a PDF from log records."""
        lines = []
        for _, row in logs_df.head(200).iterrows():
            line = f"{row.get('timestamp', '')} | {row.get('source', '')} | {row.get('user', '')} | {row.get('action', '')} | {row.get('message', '')}"
            lines.append(line)
        return self._build_pdf_from_lines(
            "System Logs Report (IST)",
            lines,
            subtitle="Audit-ready export of the filtered application logs.",
            watermark_text="Financial OS Logs",
        )

    def build_manual_pdf(
        self,
        manual_lines: list[str],
        title: str = "Financial Operating System Manual",
        subtitle: str = "Structured product guide with explanations, terminology, workflow notes, and visuals.",
        watermark_text: str = "Financial Operating System",
        technical: bool = False,
    ) -> bytes:
        """Build a downloadable product manual PDF."""
        return self._build_pdf_from_lines(
            title,
            manual_lines,
            subtitle=subtitle,
            watermark_text=watermark_text,
            technical=technical,
        )
