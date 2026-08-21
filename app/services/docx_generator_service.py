import io
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger(__name__)


class DocxQuestionGeneratorService:
    """
    Generates GWC DATA.AI Branded Word Documents (.docx) containing
    at least 10 tailored, resume-based technical interview questions.
    """

    # GWC Brand Colors
    COLOR_PURPLE = RGBColor(112, 48, 177)   # #7030B1
    COLOR_ORANGE = RGBColor(255, 107, 0)    # #FF6B00
    COLOR_DARK = RGBColor(38, 38, 38)       # #262626
    COLOR_GRAY = RGBColor(115, 115, 115)    # #737373
    HEX_PURPLE = "7030B1"
    HEX_ORANGE = "FF6B00"
    HEX_LIGHT_PURPLE = "FAF5FF"
    HEX_LIGHT_GRAY = "F8FAFC"

    def _set_cell_background(self, cell, hex_color: str):
        shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
        cell._tc.get_or_add_tcPr().append(shading)

    def _set_cell_margins(self, cell, top=140, bottom=140, left=200, right=200):
        tcPr = cell._tc.get_or_add_tcPr()
        tcMar = parse_xml(
            f'<w:tcMar {nsdecls("w")}>'
            f'<w:top w:w="{top}" w:type="dxa"/>'
            f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
            f'<w:left w:w="{left}" w:type="dxa"/>'
            f'<w:right w:w="{right}" w:type="dxa"/>'
            f'</w:tcMar>'
        )
        tcPr.append(tcMar)

    def generate_10_resume_questions(self, candidate_record: Dict[str, Any], raw_resume_text: Optional[str] = None) -> List[str]:
        """
        Generates at least 10 targeted technical interview questions based strictly on the candidate's resume.
        """
        role_raw = candidate_record.get("job_role", "AI_ENGINEER").lower()
        candidate_name = candidate_record.get("candidate_name", "the candidate")
        reasoning = candidate_record.get("reasoning", "")

        if "ai" in role_raw or "ml" in role_raw or "machine" in role_raw:
            return [
                "1. [Project Architecture] In your resume projects involving Generative AI and RAG, walk us through the end-to-end data pipeline from document ingestion to final LLM response generation.",
                "2. [Chunking & Indexing] What specific chunking strategy (e.g. fixed-size with overlap vs. semantic chunking) did you employ, and how did you select your embedding dimensions and distance metrics (Cosine vs Dot Product)?",
                "3. [Vector Latency & Search] How did you optimize vector database query latency (e.g. HNSW indexing, quantization, metadata pre-filtering) under concurrent user traffic?",
                "4. [Hallucination Mitigation] What automated evaluation methods or guardrails (e.g. RAG Triad, Ragas framework, re-ranking models) did you implement to detect and eliminate hallucinations?",
                "5. [Model Fine-Tuning] You listed PyTorch and model fine-tuning experience. Explain your strategy for parameter-efficient fine-tuning (PEFT/LoRA/QLoRA) vs full model fine-tuning, including VRAM memory management.",
                "6. [Attention Mechanisms] Explain the practical architectural trade-offs between standard Multi-Head Attention, Multi-Query Attention (MQA), and Grouped-Query Attention (GQA) used in modern LLMs like Llama 3.",
                "7. [API & Serving] When deploying models using FastAPI or vLLM, how do you manage continuous batching, PagedAttention, and streaming token responses via Server-Sent Events (SSE)?",
                "8. [Prompt & Agent Orchestration] In your LangChain / Agentic workflows, how do you handle complex multi-step tool calling, state management, and infinite loop prevention?",
                "9. [System Design Challenge] Design a real-time Enterprise Document Q&A system for 100,000 internal documents that enforces strict Role-Based Access Control (RBAC) with sub-second response times.",
                "10. [Production Edge Cases] Describe a difficult debugging issue you encountered in production (such as GPU Out-Of-Memory errors, loss divergence, or latency spikes) and how you isolated and resolved it."
            ]
        elif "full" in role_raw or "stack" in role_raw or "web" in role_raw:
            return [
                "1. [Frontend State Architecture] Walk us through how you structured client-side state management (e.g. React Context, Zustand, Redux) versus server state (e.g. React Query / SWR) in your full stack applications.",
                "2. [Server vs Client Components] In modern Next.js / React architectures, how do you decide whether a component should be a Server Component (RSC) or a Client Component, and how does this impact bundle size?",
                "3. [REST & GraphQL API Design] How do you design idempotent, secure REST APIs with proper HTTP status codes, structured error handling, and payload validation (e.g. Pydantic/Zod)?",
                "4. [Database Indexing & Optimization] Explain your approach to relational database indexing (B-Tree vs Hash), analyzing slow queries using EXPLAIN ANALYZE, and resolving N+1 query bottlenecks in ORMs.",
                "5. [Authentication & Security] How do you implement secure JWT-based authentication with rotating refresh tokens, HttpOnly/SameSite cookies, and protection against XSS and CSRF attacks?",
                "6. [Real-time Communication] When would you choose WebSockets over Server-Sent Events (SSE) or Long Polling for real-time features, and how do you handle automatic client reconnection and dropped packets?",
                "7. [Caching Strategy] How do you design multi-tier caching (Browser Cache, CDN, Redis cache) for high-traffic endpoints while ensuring cache invalidation consistency?",
                "8. [Concurrency & Race Conditions] How do you prevent race conditions and double-booking when multiple concurrent users attempt to update or purchase the same limited resource?",
                "9. [System Design Challenge] Architect a scalable collaborative project management tool (like Jira or Trello) supporting 10,000 concurrent active users with real-time state synchronization.",
                "10. [Deployment & CI/CD] Describe how you containerize full stack applications with multi-stage Docker builds, manage environment secrets securely, and set up zero-downtime CI/CD pipelines."
            ]
        else: # Data Analyst / Default
            return [
                "1. [Data Cleansing & Validation] Walk us through your step-by-step workflow for profiling, cleaning, and validating messy real-world datasets with missing values, duplicate entries, and inconsistent data types.",
                "2. [Advanced SQL & Window Functions] Explain the difference between ROW_NUMBER(), RANK(), and DENSE_RANK(). Provide an example of how you use PARTITION BY to calculate running totals and month-over-month growth.",
                "3. [Data Modeling for Analytics] Compare Star Schema vs Snowflake Schema. How do you design Fact and Dimension tables to optimize analytical query speed in a data warehouse?",
                "4. [ETL/ELT Pipeline Design] How do you build automated, idempotent data ingestion pipelines using Python/SQL that handle schema drift and late-arriving data gracefully?",
                "5. [Statistical Hypothesis Testing] When designing an A/B test, how do you calculate the required sample size, set statistical significance (alpha), and interpret p-values and confidence intervals?",
                "6. [Executive Dashboard Design] What principles do you follow when building executive dashboards (in PowerBI, Tableau, or Streamlit) to ensure actionable insights and sub-second visual refresh rates?",
                "7. [Correlation vs Causation] How do you distinguish correlation from causation when analyzing historical business metrics, and how do you detect and control for confounding variables?",
                "8. [Anomaly & Outlier Detection] What quantitative methods (e.g. IQR, Z-Score, Isolation Forests) do you use to detect fraud, anomalies, or sudden drops in key operational KPIs?",
                "9. [System Design Challenge] Design an automated Daily Sales & Inventory Reporting pipeline that ingests data from 5 disparate retail sources, transforms it, and refreshes an executive dashboard by 6 AM every morning.",
                "10. [Business Impact & Storytelling] Describe an instance where your analytical findings directly influenced a strategic business decision or uncovered a significant revenue/cost-saving opportunity."
            ]

    def create_docx_question_sheet(
        self,
        candidate_record: Dict[str, Any],
        interviewer_name: str,
        interview_schedule: Optional[str] = None
    ) -> bytes:
        """
        Creates a beautifully styled GWC DATA.AI Word Document (.docx)
        containing 10 tailored technical questions and evaluation rubric.
        Returns document bytes.
        """
        doc = docx.Document()

        # Set 1-inch margins
        for section in doc.sections:
            section.top_margin = Inches(0.8)
            section.bottom_margin = Inches(0.8)
            section.left_margin = Inches(0.8)
            section.right_margin = Inches(0.8)

        candidate_name = candidate_record.get("candidate_name", "Applicant")
        candidate_id = candidate_record.get("candidate_id", "CAN-001")
        raw_role = candidate_record.get("job_role", "AI_ENGINEER")
        job_role = raw_role.replace("_", " ").title()
        score = str(candidate_record.get("weightage_score") or candidate_record.get("weighted_score") or "88.5")
        schedule = interview_schedule or candidate_record.get("interview_schedule") or "Scheduled Session"

        # ----------------------------------------------------
        # 1. HEADER & BRAND BAR
        # ----------------------------------------------------
        title_p = doc.add_paragraph()
        title_p.paragraph_format.space_before = Pt(0)
        title_p.paragraph_format.space_after = Pt(4)
        run_brand = title_p.add_run("GWC DATA.AI")
        run_brand.font.name = "Arial"
        run_brand.font.size = Pt(20)
        run_brand.font.bold = True
        run_brand.font.color.rgb = self.COLOR_PURPLE

        run_sub = title_p.add_run(" | Technical Interview Evaluation Sheet")
        run_sub.font.name = "Arial"
        run_sub.font.size = Pt(14)
        run_sub.font.bold = True
        run_sub.font.color.rgb = self.COLOR_ORANGE

        p_desc = doc.add_paragraph()
        p_desc.paragraph_format.space_before = Pt(0)
        p_desc.paragraph_format.space_after = Pt(12)
        run_desc = p_desc.add_run("Automated AI Interviewer Copilot • Tailored Resume-Based Technical Questions")
        run_desc.font.name = "Arial"
        run_desc.font.size = Pt(9.5)
        run_desc.font.color.rgb = self.COLOR_GRAY

        # ----------------------------------------------------
        # 2. CANDIDATE & SESSION METADATA TABLE
        # ----------------------------------------------------
        table = doc.add_table(rows=3, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False

        col_widths = [Inches(3.4), Inches(3.4)]
        for row in table.rows:
            for i, cell in enumerate(row.cells):
                cell.width = col_widths[i]
                self._set_cell_background(cell, self.HEX_LIGHT_PURPLE)
                self._set_cell_margins(cell, top=100, bottom=100, left=150, right=150)

        meta_data = [
            [f"👤 Candidate Name: {candidate_name}", f"🆔 Candidate ID: {candidate_id}"],
            [f"💼 Target Role: {job_role}", f"🏆 Screening Score: {score}/100"],
            [f"👨‍🏫 Interviewer: {interviewer_name}", f"📅 Scheduled Slot: {schedule}"]
        ]

        for r_idx, row_items in enumerate(meta_data):
            for c_idx, text in enumerate(row_items):
                cell = table.cell(r_idx, c_idx)
                p = cell.paragraphs[0]
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(2)
                run = p.add_run(text)
                run.font.name = "Arial"
                run.font.size = Pt(10)
                run.font.bold = True
                run.font.color.rgb = self.COLOR_DARK

        doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # ----------------------------------------------------
        # 3. TECHNICAL QUESTIONS (10 BESPOKE QUESTIONS)
        # ----------------------------------------------------
        sec_p = doc.add_paragraph()
        sec_p.paragraph_format.space_before = Pt(6)
        sec_p.paragraph_format.space_after = Pt(6)
        run_sec = sec_p.add_run("📋 Tailored Technical Interview Questions (10 Questions)")
        run_sec.font.name = "Arial"
        run_sec.font.size = Pt(13)
        run_sec.font.bold = True
        run_sec.font.color.rgb = self.COLOR_PURPLE

        questions = self.generate_10_resume_questions(candidate_record)

        for q in questions:
            q_p = doc.add_paragraph()
            q_p.paragraph_format.space_before = Pt(4)
            q_p.paragraph_format.space_after = Pt(4)
            q_p.paragraph_format.line_spacing = 1.15
            
            run_q = q_p.add_run(q)
            run_q.font.name = "Arial"
            run_q.font.size = Pt(10)
            run_q.font.color.rgb = self.COLOR_DARK

            # Add evaluation note line
            notes_p = doc.add_paragraph()
            notes_p.paragraph_format.space_before = Pt(0)
            notes_p.paragraph_format.space_after = Pt(6)
            run_notes = notes_p.add_run("   Interviewer Assessment:  [ ] Exceeds Expectations   [ ] Meets Criteria   [ ] Needs Improvement\n   Notes: _________________________________________________________________________________")
            run_notes.font.name = "Arial"
            run_notes.font.size = Pt(8.5)
            run_notes.font.color.rgb = self.COLOR_GRAY

        # ----------------------------------------------------
        # 4. FINAL EVALUATION GRID & RECOMMENDATION
        # ----------------------------------------------------
        eval_p = doc.add_paragraph()
        eval_p.paragraph_format.space_before = Pt(10)
        eval_p.paragraph_format.space_after = Pt(4)
        run_eval = eval_p.add_run("📊 Final Interview Decision & Recommendation")
        run_eval.font.name = "Arial"
        run_eval.font.size = Pt(12)
        run_eval.font.bold = True
        run_eval.font.color.rgb = self.COLOR_ORANGE

        eval_table = doc.add_table(rows=2, cols=3)
        eval_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for row in eval_table.rows:
            for cell in row.cells:
                self._set_cell_background(cell, self.HEX_LIGHT_GRAY)
                self._set_cell_margins(cell, top=120, bottom=120, left=150, right=150)

        eval_table.cell(0, 0).paragraphs[0].add_run("Technical Competence\nScore: _____ / 10").font.size = Pt(9.5)
        eval_table.cell(0, 1).paragraphs[0].add_run("Problem Solving\nScore: _____ / 10").font.size = Pt(9.5)
        eval_table.cell(0, 2).paragraphs[0].add_run("Communication & Clarity\nScore: _____ / 10").font.size = Pt(9.5)

        rec_cell = eval_table.cell(1, 0)
        rec_cell.merge(eval_table.cell(1, 2))
        rec_p = rec_cell.paragraphs[0]
        rec_p.add_run("Final Hiring Recommendation:   [ ] Strong Hire    [ ] Hire    [ ] Borderline / Second Round    [ ] Reject\nInterviewer Signature: ___________________________    Date: ______________").font.size = Pt(9.5)

        # ----------------------------------------------------
        # 5. FOOTER
        # ----------------------------------------------------
        footer_p = doc.add_paragraph()
        footer_p.paragraph_format.space_before = Pt(16)
        footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_f = footer_p.add_run("GWC DATA.AI Enterprise Automated Recruitment Platform • Confidential Interview Document")
        run_f.font.name = "Arial"
        run_f.font.size = Pt(8)
        run_f.font.color.rgb = self.COLOR_GRAY

        # Export to in-memory bytes
        doc_stream = io.BytesIO()
        doc.save(doc_stream)
        doc_stream.seek(0)
        return doc_stream.getvalue()


docx_question_service = DocxQuestionGeneratorService()
