
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import List, Dict, Any
import logging

from app.database import db
from prisma.models import User # pyright: ignore[reportMissingImports]
from app.config import settings

logger = logging.getLogger(__name__)


class SummarizationService:
    """Service for document summarization."""
    
    def __init__(self, user: User):
        self.user = user
        
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-exp",
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.5,
        )
    
    async def summarize_documents(
        self,
        document_ids: List[str],
        summary_type: str = "concise"
    ) -> Dict[str, Any]:
        try:
            documents = await db.document.find_many(
                where={
                    "id": {"in": document_ids},
                    "userId": self.user.id
                }
            )
            
            if not documents:
                raise ValueError("No documents found")
            
            # Prepare content
            content_parts = []
            document_titles = []
            
            for doc in documents:
                document_titles.append(doc.title)
                content_parts.append(
                    f"### {doc.title} ({doc.type})\n\n{doc.content}\n\n"
                )
            
            combined_content = "\n".join(content_parts)
            
            # Generate summary based on type
            if summary_type == "concise":
                summary = await self._generate_concise_summary(
                    combined_content,
                    document_titles
                )
            elif summary_type == "detailed":
                summary = await self._generate_detailed_summary(
                    combined_content,
                    document_titles
                )
            elif summary_type == "bullet_points":
                summary = await self._generate_bullet_summary(
                    combined_content,
                    document_titles
                )
            else:
                raise ValueError(f"Invalid summary type: {summary_type}")
            
            word_count = len(summary.split())
            
            logger.info(f"Generated {summary_type} summary for {len(documents)} documents")
            
            return {
                "summary": summary,
                "documents_summarized": document_titles,
                "word_count": word_count
            }
            
        except Exception as e:
            logger.error(f"Summarization failed: {str(e)}")
            raise
    
    async def _generate_concise_summary(
        self,
        content: str,
        titles: List[str]
    ) -> str:
        """Generate concise summary (2-3 paragraphs)."""
        
        prompt = f"""Summarize the following documents in 2-3 concise paragraphs:

Documents: {', '.join(titles)}

Content:
{content[:5000]}

Provide a clear, concise summary that captures the main points and key information.

Summary:"""
        
        response = await self.llm.ainvoke(prompt)
        return response.content
    
    async def _generate_detailed_summary(
        self,
        content: str,
        titles: List[str]
    ) -> str:
        """Generate detailed summary (4-6 paragraphs)."""
        
        prompt = f"""Provide a detailed summary of the following documents:

Documents: {', '.join(titles)}

Content:
{content[:8000]}

Include:
1. Overview of each document
2. Main topics and themes
3. Key findings or information
4. Important details and data points

Summary:"""
        
        response = await self.llm.ainvoke(prompt)
        return response.content
    
    async def _generate_bullet_summary(
        self,
        content: str,
        titles: List[str]
    ) -> str:
        """Generate bullet point summary."""
        
        prompt = f"""Summarize the following documents as bullet points:

Documents: {', '.join(titles)}

Content:
{content[:6000]}

Format:
- Use clear, concise bullet points
- Group related information
- Highlight key takeaways
- Include important data/facts

Summary:"""
        
        response = await self.llm.ainvoke(prompt)
        return response.content