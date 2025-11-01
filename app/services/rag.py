"""
RAG (Retrieval-Augmented Generation) service using LangChain and Gemini.
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from typing import List, Dict, Any, Optional, AsyncGenerator
import logging
import json
from datetime import datetime

from app.services.embeddings import EmbeddingService
from app.database import db
from app.models import DocumentSource
from prisma.models import User # pyright: ignore[reportMissingImports]
from app.config import settings

logger = logging.getLogger(__name__)


class RAGService:
    """Service for RAG-powered question answering."""
    
    def __init__(self, user: User):
        """
        Initialize RAG service.
        
        Args:
            user: User model
        """
        self.user = user
        self.embedding_service = EmbeddingService()
        
        # Initialize Gemini 2.0 Flash (FREE)
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-exp",
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.7,
        )
    
    async def query(
        self,
        question: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query the RAG system.
        
        Args:
            question: User's question
            session_id: Optional chat session ID
            
        Returns:
            Dictionary with answer, sources, and metadata
        """
        try:
            # Create or get session
            if not session_id:
                session = await db.chatsession.create(
                    data={
                        "userId": self.user.id,
                        "title": question[:50] + "..." if len(question) > 50 else question
                    }
                )
                session_id = session.id
            
            # Save user message
            await db.chatmessage.create(
                data={
                    "sessionId": session_id,
                    "role": "USER",
                    "content": question
                }
            )
            
            # Generate query embedding
            logger.info(f"Generating embedding for question: {question[:100]}")
            query_embedding = await self.embedding_service.embed_text(question)
            
            # Search for relevant chunks
            relevant_chunks = await self._search_similar_chunks(query_embedding)
            
            # Generate answer
            if relevant_chunks:
                logger.info(f"Found {len(relevant_chunks)} relevant chunks, generating contextual answer")
                answer = await self._generate_answer_with_context(
                    question,
                    relevant_chunks
                )
                found_in_documents = True
            else:
                logger.info("No relevant chunks found, generating fallback answer")
                answer = await self._generate_fallback_answer(question)
                found_in_documents = False
            
            # Prepare sources
            sources = [
                DocumentSource(
                    documentId=chunk["documentId"],
                    documentTitle=chunk["documentTitle"],
                    documentType=chunk["documentType"],
                    chunkText=chunk["content"][:200] + "..." if len(chunk["content"]) > 200 else chunk["content"],
                    similarity=chunk.get("similarity")
                )
                for chunk in relevant_chunks
            ]
            
            # Save assistant message
            await db.chatmessage.create(
                data={
                    "sessionId": session_id,
                    "role": "ASSISTANT",
                    "content": answer,
                    "sources": json.dumps([s.dict() for s in sources])
                }
            )
            
            # Update session
            await db.chatsession.update(
                where={"id": session_id},
                data={"updatedAt": datetime.now()}
            )
            
            return {
                "answer": answer,
                "sources": sources,
                "session_id": session_id,
                "found_in_documents": found_in_documents
            }
            
        except Exception as e:
            logger.error(f"RAG query failed: {str(e)}")
            logger.exception("Full traceback:")
            raise
    
    async def _search_similar_chunks(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        similarity_threshold: float = 0.3  # LOWERED from 0.7 to 0.3
    ) -> List[Dict[str, Any]]:
        """
        Search for similar document chunks using vector similarity.
        
        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score (0.0 to 1.0)
            
        Returns:
            List of relevant chunks with metadata
        """
        try:
            # Get user's documents
            user_documents = await db.document.find_many(
                where={
                    "userId": self.user.id,
                    "isProcessed": True
                }
            )
            
            if not user_documents:
                logger.warning("No processed documents found for user")
                return []
            
            document_ids = [doc.id for doc in user_documents]
            logger.info(f"Searching in {len(document_ids)} processed documents")
            
            # Vector similarity search using pgvector
            embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
            
            # Updated query - removed threshold filter in WHERE clause
            query = """
                SELECT 
                    dc.id,
                    dc."documentId",
                    dc.content,
                    dc."chunkIndex",
                    d.title as "documentTitle",
                    d.type as "documentType",
                    (1 - (dc.embedding <=> $1::vector)) as similarity
                FROM "DocumentChunk" dc
                JOIN "Document" d ON dc."documentId" = d.id
                WHERE dc."documentId" = ANY($2::text[])
                AND dc.embedding IS NOT NULL
                ORDER BY dc.embedding <=> $1::vector
                LIMIT $3
            """
            
            # Get more results than needed, then filter
            results = await db.query_raw(
                query,
                embedding_str,
                document_ids,
                top_k * 2  # Get double, then filter
            )
            
            # Filter by similarity threshold
            filtered_results = [
                r for r in results 
                if r.get('similarity', 0) >= similarity_threshold
            ]
            
            # Log similarity scores for debugging
            if filtered_results:
                top_similarities = [r.get('similarity', 0) for r in filtered_results[:3]]
                logger.info(f"Found {len(filtered_results)} chunks above threshold {similarity_threshold}")
                logger.info(f"Top 3 similarity scores: {top_similarities}")
            else:
                logger.warning(f"No chunks found above similarity threshold {similarity_threshold}")
                # Log what we did find
                if results:
                    all_similarities = [r.get('similarity', 0) for r in results[:5]]
                    logger.info(f"Top 5 similarity scores (unfiltered): {all_similarities}")
            
            return filtered_results[:top_k]
            
        except Exception as e:
            logger.error(f"Vector search failed: {str(e)}")
            logger.exception("Full traceback:")
            return []
    
    async def _generate_answer_with_context(
        self,
        question: str,
        chunks: List[Dict[str, Any]]
    ) -> str:
        """
        Generate answer using retrieved context.
        
        Args:
            question: User's question
            chunks: Retrieved document chunks
            
        Returns:
            Generated answer
        """
        try:
            # Build context from chunks
            context_parts = []
            for idx, chunk in enumerate(chunks, 1):  # FIXED: removed [Dict[str, Any]]
                context_parts.append(
                    f"[Document {idx}: {chunk['documentTitle']}]\n{chunk['content']}\n"
                )
            
            context = "\n".join(context_parts)
            
            # Create prompt
            prompt = f"""You are a helpful AI assistant that answers questions based on the user's Google Docs, Sheets, and Slides.

Context from user's documents:
{context}

User's question: {question}

Instructions:
1. Answer the question based ONLY on the context provided above
2. Be specific and cite which document(s) you're referencing
3. If the context contains the answer, provide a detailed response
4. Use a conversational and helpful tone
5. Format your response in a clear, readable way

Answer:"""
            
            # Generate answer
            response = await self.llm.ainvoke(prompt)
            answer = response.content
            
            logger.info("Generated answer with context")
            
            return answer
            
        except Exception as e:
            logger.error(f"Answer generation failed: {str(e)}")
            logger.exception("Full traceback:")
            raise
    
    async def _generate_fallback_answer(self, question: str) -> str:
        """
        Generate fallback answer when no relevant documents found.
        
        Args:
            question: User's question
            
        Returns:
            Generated answer from general knowledge
        """
        try:
            prompt = f"""You are a helpful AI assistant.

The user asked: "{question}"

However, I couldn't find relevant information in their Google Docs, Sheets, or Slides.

Please respond with:
1. First, explicitly state: "I couldn't find information about this in your documents."
2. Then provide a helpful answer based on your general knowledge
3. Be conversational and helpful

Response:"""
            
            response = await self.llm.ainvoke(prompt)
            answer = response.content
            
            logger.info("Generated fallback answer")
            
            return answer
            
        except Exception as e:
            logger.error(f"Fallback answer generation failed: {str(e)}")
            logger.exception("Full traceback:")
            raise
    
    async def query_stream(
        self,
        question: str,
        session_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Query with streaming response.
        
        Args:
            question: User's question
            session_id: Optional chat session ID
            
        Yields:
            Response chunks as JSON strings
        """
        try:
            # Generate query embedding
            query_embedding = await self.embedding_service.embed_text(question)
            
            # Search for relevant chunks
            relevant_chunks = await self._search_similar_chunks(query_embedding)
            
            # Build context
            if relevant_chunks:
                context_parts = []
                for chunk in relevant_chunks:
                    context_parts.append(
                        f"[{chunk['documentTitle']}]\n{chunk['content']}\n"
                    )
                context = "\n".join(context_parts)
                
                prompt = f"""Answer based on context:

{context}

Question: {question}

Answer:"""
            else:
                prompt = f"""The user asked: "{question}"

No relevant documents found. Provide answer from general knowledge, but first state that you couldn't find it in their documents.

Answer:"""
            
            # Stream response
            async for chunk in self.llm.astream(prompt):
                yield json.dumps({"content": chunk.content})
                
        except Exception as e:
            logger.error(f"Streaming query failed: {str(e)}")
            yield json.dumps({"error": str(e)})