
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from typing import List
import logging

from app.models import (
    ChatQueryRequest,
    ChatQueryResponse,
    ChatHistoryResponse,
    ChatSessionResponse,
    ChatMessageResponse,
    SummarizeRequest,
    SummarizeResponse,
    SuccessResponse
)
from app.auth.middleware import get_current_user
from app.services.rag import RAGService
from app.services.summarization import SummarizationService
from app.database import db
from prisma.models import User  # pyright: ignore[reportMissingImports]

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/query",
    response_model=ChatQueryResponse,
    summary="Query Chatbot",
    description="Ask a question to the RAG-powered chatbot"
)
async def query_chatbot(
    request: ChatQueryRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        rag_service = RAGService(current_user)
        
        # Process query
        result = await rag_service.query(
            question=request.question,
            session_id=request.session_id
        )
        
        logger.info(f"Processed query for user: {current_user.email}")
        
        return ChatQueryResponse(**result)
        
    except Exception as e:
        logger.error(f"Failed to process query: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process query: {str(e)}"
        )


@router.post(
    "/query/stream",
    summary="Query Chatbot (Streaming)",
    description="Ask a question with streaming response"
)
async def query_chatbot_stream(
    request: ChatQueryRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        rag_service = RAGService(current_user)
        
        async def generate_stream():
            async for chunk in rag_service.query_stream(
                question=request.question,
                session_id=request.session_id
            ):
                yield f"data: {chunk}\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream"
        )
        
    except Exception as e:
        logger.error(f"Failed to stream query: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stream query: {str(e)}"
        )


@router.get(
    "/sessions",
    response_model=List[ChatSessionResponse],
    summary="Get Chat Sessions",
    description="Get all chat sessions for current user"
)
async def get_chat_sessions(current_user: User = Depends(get_current_user)):
    try:
        sessions = await db.chatsession.find_many(
            where={"userId": current_user.id},
            include={"messages": True},
            order={"updatedAt": "desc"}
        )
        
        result = []
        for session in sessions:
            result.append(
                ChatSessionResponse(
                    id=session.id,
                    title=session.title,
                    createdAt=session.createdAt,
                    updatedAt=session.updatedAt,
                    messageCount=len(session.messages) if session.messages else 0
                )
            )
        
        logger.info(f"Retrieved {len(result)} sessions for user: {current_user.email}")
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get sessions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve sessions"
        )


@router.get(
    "/sessions/{session_id}",
    response_model=ChatHistoryResponse,
    summary="Get Chat History",
    description="Get full chat history for a session"
)
async def get_chat_history(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    try:
        session = await db.chatsession.find_first(
            where={
                "id": session_id,
                "userId": current_user.id
            },
            include={"messages": {"order_by": {"createdAt": "asc"}}}
        )
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        messages = [
            ChatMessageResponse.model_validate(msg)
            for msg in (session.messages or [])
        ]
        
        return ChatHistoryResponse(
            session=ChatSessionResponse(
                id=session.id,
                title=session.title,
                createdAt=session.createdAt,
                updatedAt=session.updatedAt,
                messageCount=len(messages)
            ),
            messages=messages
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chat history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat history"
        )


@router.delete(
    "/sessions/{session_id}",
    response_model=SuccessResponse,
    summary="Delete Chat Session",
    description="Delete a chat session and all its messages"
)
async def delete_chat_session(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    try:
        session = await db.chatsession.find_first(
            where={
                "id": session_id,
                "userId": current_user.id
            }
        )
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        await db.chatsession.delete(where={"id": session_id})
        
        logger.info(f"Deleted session {session_id} for user: {current_user.email}")
        
        return SuccessResponse(
            message="Session deleted successfully",
            data={"session_id": session_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete session"
        )


@router.post(
    "/summarize",
    response_model=SummarizeResponse,
    summary="Summarize Documents",
    description="Generate summary of selected documents (Bonus Feature)"
)
async def summarize_documents(
    request: SummarizeRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        summarization_service = SummarizationService(current_user)
        
        result = await summarization_service.summarize_documents(
            document_ids=request.document_ids,
            summary_type=request.summary_type
        )
        
        logger.info(
            f"Generated summary for {len(request.document_ids)} documents: {current_user.email}"
        )
        
        return SummarizeResponse(**result)
        
    except Exception as e:
        logger.error(f"Failed to summarize documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to summarize documents: {str(e)}"
        )