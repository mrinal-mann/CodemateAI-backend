
from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks
from typing import List
import logging

from app.models import (
    GoogleDriveFilesResponse,
    DocumentSelectRequest,
    DocumentResponse,
    DocumentWithChunksResponse,
    SuccessResponse
)
from app.auth.middleware import get_current_user
from app.services.google_drive import GoogleDriveService
from app.services.document_processor import DocumentProcessor
from app.database import db
from prisma.models import User  # pyright: ignore[reportMissingImports]

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/list",
    response_model=GoogleDriveFilesResponse,
    summary="List Google Drive Files",
    description="List all Google Docs, Sheets, and Slides from user's Google Drive"
)
async def list_documents(current_user: User = Depends(get_current_user)):
    try:
        drive_service = GoogleDriveService(current_user)
        files = await drive_service.list_files()
        
        logger.info(f"Listed {len(files)} files for user: {current_user.email}")
        
        return GoogleDriveFilesResponse(files=files)
        
    except Exception as e:
        logger.error(f"Failed to list documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch documents: {str(e)}"
        )


@router.post(
    "/select",
    response_model=SuccessResponse,
    summary="Select Documents",
    description="Select documents to add to the knowledge base"
)
async def select_documents(
    request: DocumentSelectRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    try:
        drive_service = GoogleDriveService(current_user)
        processor = DocumentProcessor(current_user)
        
        # Add background task to process documents
        background_tasks.add_task(
            processor.process_documents,
            request.document_ids,
            drive_service
        )
        
        logger.info(
            f"Queued {len(request.document_ids)} documents for processing: {current_user.email}"
        )
        
        return SuccessResponse(
            message=f"Processing {len(request.document_ids)} document(s)",
            data={
                "document_count": len(request.document_ids),
                "status": "processing"
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to select documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process documents: {str(e)}"
        )


@router.get(
    "/my-documents",
    response_model=List[DocumentWithChunksResponse],
    summary="Get User Documents",
    description="Get all documents in user's knowledge base"
)
async def get_my_documents(current_user: User = Depends(get_current_user)):
    try:
        documents = await db.document.find_many(
            where={"userId": current_user.id},
            include={"chunks": True},
            order={"createdAt": "desc"}
        )
        
        result = []
        for doc in documents:
            result.append(
                DocumentWithChunksResponse(
                    id=doc.id,
                    googleDocId=doc.googleDocId,
                    title=doc.title,
                    type=doc.type,
                    isProcessed=doc.isProcessed,
                    chunkCount=len(doc.chunks) if doc.chunks else 0,
                    createdAt=doc.createdAt,
                    updatedAt=doc.updatedAt
                )
            )
        
        logger.info(f"Retrieved {len(result)} documents for user: {current_user.email}")
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve documents"
        )


@router.delete(
    "/{document_id}",
    response_model=SuccessResponse,
    summary="Delete Document",
    description="Remove document from knowledge base"
)
async def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user)
):
    try:
        # Verify document belongs to user
        document = await db.document.find_first(
            where={
                "id": document_id,
                "userId": current_user.id
            }
        )
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        # Delete document (chunks will be deleted via cascade)
        await db.document.delete(where={"id": document_id})
        
        logger.info(f"Deleted document {document_id} for user: {current_user.email}")
        
        return SuccessResponse(
            message="Document deleted successfully",
            data={"document_id": document_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document"
        )


@router.post(
    "/refresh",
    response_model=SuccessResponse,
    summary="Refresh Documents",
    description="Re-sync documents from Google Drive and reprocess"
)
async def refresh_documents(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    try:
        # Get all user documents
        documents = await db.document.find_many(
            where={"userId": current_user.id}
        )
        
        if not documents:
            return SuccessResponse(
                message="No documents to refresh",
                data={"document_count": 0}
            )
        
        document_ids = [doc.googleDocId for doc in documents]
        
        # Process documents in background
        drive_service = GoogleDriveService(current_user)
        processor = DocumentProcessor(current_user)
        
        background_tasks.add_task(
            processor.process_documents,
            document_ids,
            drive_service,
            is_refresh=True
        )
        
        logger.info(f"Queued {len(document_ids)} documents for refresh: {current_user.email}")
        
        return SuccessResponse(
            message=f"Refreshing {len(document_ids)} document(s)",
            data={
                "document_count": len(document_ids),
                "status": "processing"
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to refresh documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh documents"
        )