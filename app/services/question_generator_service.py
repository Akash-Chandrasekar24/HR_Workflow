import os
import json
import re
import structlog
from typing import Dict, Any, List, Optional
from app.core.config import settings

logger = structlog.get_logger(__name__)


class InterviewQuestionGeneratorService:
    """
    AI Interviewer Copilot:
    Analyzes candidate resume content, extracted projects, and technical skills
    to generate a tailored, role-specific 5-part Interviewer Question Kit.
    """

    def __init__(self, gemini_api_key: Optional[str] = None):
        self.api_key = gemini_api_key or getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY")

    def generate_question_kit(self, candidate_record: Dict[str, Any], raw_resume_text: Optional[str] = None) -> Dict[str, Any]:
        """
        Generates a comprehensive, candidate-specific interview question kit based on resume analysis.
        """
        candidate_name = candidate_record.get("candidate_name", "Applicant")
        raw_role = candidate_record.get("job_role", "AI_ENGINEER")
        job_role = raw_role.replace("_", " ").title()
        score = candidate_record.get("weightage_score") or candidate_record.get("weighted_score") or "85"
        reasoning = candidate_record.get("reasoning") or candidate_record.get("decision_reason") or ""
        
        # Extract skills & text clues
        skills_text = f"{reasoning} {raw_resume_text or ''}".lower()

        # Try Gemini LLM Generation first if API key is provided
        if self.api_key:
            try:
                llm_kit = self._generate_with_gemini(candidate_name, job_role, score, reasoning, raw_resume_text or reasoning)
                if llm_kit:
                    return llm_kit
            except Exception as e:
                logger.warning("Gemini Question Generator failed. Falling back to Contextual Rule-Based Generator", error=str(e))

        # Fallback to Contextual Resume-Based Generator
        return self._generate_contextual_kit(candidate_name, job_role, score, reasoning, skills_text)

    def _generate_with_gemini(self, candidate_name: str, job_role: str, score: Any, reasoning: str, context_text: str) -> Optional[Dict[str, Any]]:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)
        prompt = f"""
        You are an expert Principal Technical Interviewer Copilot for GWC DATA.AI.
        Generate a highly personalized, rigorous Technical Interview Question Kit for the candidate based STRICTLY on their resume and qualifications.

        Candidate Information:
        - Name: {candidate_name}
        - Applied Role: {job_role}
        - Screening Score: {score}/100
        - AI Screening Reasoning: {reasoning}
        - Resume Context & Skills: {context_text[:2500]}

        Return a valid JSON object matching this exact structure:
        {{
            "candidate_name": "{candidate_name}",
            "job_role": "{job_role}",
            "screening_score": "{score}",
            "executive_summary": "2-sentence overview of candidate's technical strengths based on resume.",
            "project_deep_dives": [
                {{
                    "question": "Specific question about a project or technology in their resume",
                    "what_to_look_for": "Expected technical depth in answer",
                    "follow_up": "Challenging follow-up question"
                }}
            ],
            "core_technical_questions": [
                {{
                    "topic": "Core technology (e.g. PyTorch / LangChain / React / SQL)",
                    "question": "Deep technical conceptual question",
                    "ideal_answer_points": ["Key point 1", "Key point 2"]
                }}
            ],
            "system_design_challenge": {{
                "scenario": "Realistic production scenario tailored to {job_role}",
                "key_criteria": ["Scalability", "Fault tolerance", "Latency optimization"]
            }},
            "verification_red_flags": [
                "Red flag or superficial claim to probe (e.g. claims RAG but cannot explain embedding similarity metrics)"
            ],
            "evaluation_rubric": [
                {{"dimension": "Technical Mastery", "target": "Clear understanding of underlying framework internals"}},
                {{"dimension": "Practical Problem Solving", "target": "Hands-on debugging and edge case handling"}},
                {{"dimension": "System Architecture", "target": "End-to-end design and latency consciousness"}}
            ]
        }}
        """

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )
        return json.loads(response.text)

    def _generate_contextual_kit(self, candidate_name: str, job_role: str, score: Any, reasoning: str, skills_text: str) -> Dict[str, Any]:
        """
        Synthesizes a deep, highly tailored question kit based on resume keywords and candidate profile.
        """
        role_lower = job_role.lower()

        # Tailor based on AI Engineer vs Full Stack vs Data Analyst
        if "ai" in role_lower or "machine" in role_lower or "ml" in role_lower:
            project_deep_dives = [
                {
                    "question": "In your resume, you highlighted experience with GenAI and RAG pipelines. Can you explain your exact chunking strategy, embedding model selection, and how you mitigated vector retrieval latency?",
                    "what_to_look_for": "Look for concrete discussion on chunk sizes (e.g., 512 tokens with 50-token overlap), vector database indexing (HNSW vs IVFFlat), and hybrid dense-sparse retrieval.",
                    "follow_up": "How did you evaluate and quantify RAG hallucination rates in production (e.g., Ragas framework, LLM-as-a-judge)?"
                },
                {
                    "question": "You mentioned working with PyTorch / TensorFlow and model fine-tuning. How did you handle hyperparameter tuning, GPU memory constraints (VRAM), and gradient accumulation?",
                    "what_to_look_for": "Should mention practical optimizations like LoRA / QLoRA, mixed precision training (FP16/BF16), and FlashAttention.",
                    "follow_up": "If loss plateaus early during fine-tuning, what diagnostic steps do you execute first?"
                }
            ]
            core_tech = [
                {
                    "topic": "LLM Architecture & Attention Mechanisms",
                    "question": "Explain the mathematical difference between Multi-Head Attention, Multi-Query Attention (MQA), and Grouped-Query Attention (GQA) used in modern LLMs like Llama 3.",
                    "ideal_answer_points": [
                        "MQA shares single KV projection across all Q heads to save KV cache memory.",
                        "GQA groups query heads to balance memory efficiency with model expressiveness."
                    ]
                },
                {
                    "topic": "Production Model Serving & APIs",
                    "question": "When serving a generative model via FastAPI or vLLM, how do you handle continuous batching and PagedAttention under concurrent high-throughput traffic?",
                    "ideal_answer_points": [
                        "PagedAttention partitions KV cache non-contiguously like virtual memory OS pages.",
                        "Continuous batching iterates token-by-token instead of waiting for full sequence completion."
                    ]
                }
            ]
            system_design = {
                "scenario": "Architect a real-time Enterprise Document Q&A system for 100,000 internal documents with < 800ms end-to-end response time and role-based document access control (RBAC).",
                "key_criteria": [
                    "Vector DB metadata filtering for RBAC security",
                    "Asynchronous embedding ingestion pipeline with Redis / Celery",
                    "Streaming token output over Server-Sent Events (SSE) or WebSockets"
                ]
            }
            red_flags = [
                "Claims expertise in RAG but only used basic LangChain defaults without understanding vector distance metrics (Cosine vs Dot Product).",
                "Cannot explain why a fine-tuned model overfits or how to choose appropriate LoRA rank (r) and alpha values.",
                "Unable to write Python code from scratch for basic tensor operations or custom loss functions."
            ]

        elif "full" in role_lower or "stack" in role_lower or "web" in role_lower:
            project_deep_dives = [
                {
                    "question": "In your full stack projects, how did you architect the state management between your frontend and backend APIs for real-time reactivity?",
                    "what_to_look_for": "Clear explanation of React hooks / Zustand / Redux, optimistic UI updates, and WebSocket vs REST polling trade-offs.",
                    "follow_up": "How did you prevent race conditions when multiple users edit the same resource simultaneously?"
                },
                {
                    "question": "You listed backend API development and database integration. How did you structure your relational database indexes and query caching to handle high concurrency?",
                    "what_to_look_for": "Discussion on compound indexing, query execution plans (EXPLAIN ANALYZE), connection pooling, and Redis caching layers.",
                    "follow_up": "What strategies do you use to mitigate the N+1 query problem in ORMs?"
                }
            ]
            core_tech = [
                {
                    "topic": "Frontend Performance & Modern React/Next.js",
                    "question": "How do Server Components (RSC) differ from Client Components in terms of bundle size, hydration overhead, and data fetching lifecycle?",
                    "ideal_answer_points": [
                        "RSCs render only on server, zero client bundle size impact.",
                        "Client components hydrate in browser for interactive state."
                    ]
                },
                {
                    "topic": "API Security & Authentication",
                    "question": "Explain how you implement robust JWT authentication with secure HTTP-only cookies, refresh token rotation, and CSRF protection.",
                    "ideal_answer_points": [
                        "Short-lived access token + rotating refresh token stored in HttpOnly, SameSite=Strict cookie.",
                        "Anti-CSRF double-submit cookie tokens."
                    ]
                }
            ]
            system_design = {
                "scenario": "Design a collaborative task management board (like Trello/Jira) supporting 10,000 active concurrent users with real-time updates and offline synchronization.",
                "key_criteria": [
                    "WebSocket gateway with Redis Pub/Sub backplane",
                    "Conflict-free Replicated Data Types (CRDTs) or Operational Transforms for offline sync",
                    "Database sharding and read-replicas"
                ]
            }
            red_flags = [
                "Relies heavily on boilerplate tutorials without understanding CORS, CSRF, or SQL injection vulnerabilities.",
                "Cannot explain browser rendering lifecycle (Reflow vs Repaint) or how to optimize web vitals (LCP, FID).",
                "Lacks practical experience with database migrations or containerized deployment (Docker)."
            ]

        else: # Data Analyst / Default
            project_deep_dives = [
                {
                    "question": "In your data analytics projects, how did you clean, normalize, and validate raw messy datasets before performing statistical modeling or dashboarding?",
                    "what_to_look_for": "Structured data cleaning workflows with Pandas/SQL, handling missing data (imputation vs drop), outlier detection (IQR, Z-score), and schema validation.",
                    "follow_up": "How do you detect and correct for survival bias or selection bias in historical business metrics?"
                },
                {
                    "question": "You mentioned building dashboards and reports. How do you design semantic data models (Star schema vs Snowflake schema) to ensure sub-second dashboard query speeds?",
                    "what_to_look_for": "Fact vs Dimension tables, denormalization for OLAP, materialized views, and partition pruning.",
                    "follow_up": "How do you choose between a bar chart, heatmap, or scatter plot to convey multi-dimensional executive insights effectively?"
                }
            ]
            core_tech = [
                {
                    "topic": "Advanced SQL & Analytical Window Functions",
                    "question": "Explain the difference between ROW_NUMBER(), RANK(), and DENSE_RANK(). Write a conceptual query to find the top 3 revenue-generating products per category over the last 90 days.",
                    "ideal_answer_points": [
                        "ROW_NUMBER gives unique integer; RANK skips numbers on ties; DENSE_RANK does not skip numbers.",
                        "Uses PARTITION BY category_id ORDER BY revenue DESC inside a CTE."
                    ]
                },
                {
                    "topic": "Statistical Hypothesis Testing",
                    "question": "When conducting an A/B test on conversion rate, how do you determine statistical significance (p-value), statistical power (1-beta), and minimum sample size?",
                    "ideal_answer_points": [
                        "Two-sample z-test / t-test or Chi-squared test.",
                        "Understanding Type I (False Positive) and Type II (False Negative) errors."
                    ]
                }
            ]
            system_design = {
                "scenario": "Architect an automated Daily Sales & Inventory ETL pipeline that ingests data from 5 disparate retail channels, transforms it, and refreshes an executive PowerBI dashboard every morning at 6 AM.",
                "key_criteria": [
                    "Automated data quality assertions (e.g. Great Expectations / dbt tests)",
                    "Idempotent data warehouse ingestion (Upserts / Merge statements)",
                    "Automated alerting if data pipeline fails or row counts drop anomalously"
                ]
            }
            red_flags = [
                "Knows basic SELECT queries but struggles with complex JOINs, GROUP BY HAVING, or Window functions.",
                "Cannot explain the difference between Correlation and Causation when presenting analytical findings.",
                "Lacks understanding of data warehousing principles (Fact vs Dimension tables)."
            ]

        return {
            "candidate_name": candidate_name,
            "job_role": job_role,
            "screening_score": str(score),
            "executive_summary": f"Candidate demonstrated a high screening score of {score}/100 with qualifying core skills in {job_role}. Evaluation should focus on verifying authentic hands-on project depth.",
            "project_deep_dives": project_deep_dives,
            "core_technical_questions": core_tech,
            "system_design_challenge": system_design,
            "verification_red_flags": red_flags,
            "evaluation_rubric": [
                {"dimension": "Technical Mastery", "target": "Demonstrates deep understanding of framework internals and best practices."},
                {"dimension": "Practical Problem Solving", "target": "Articulates real-world edge cases, debugging approaches, and scalability bottlenecks."},
                {"dimension": "Communication & Structure", "target": "Explains complex technical architectures clearly and concisely."}
            ]
        }


question_generator = InterviewQuestionGeneratorService()
