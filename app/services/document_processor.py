"""
Document processor service for chunking and embedding documents.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List, Dict, Any
import logging
import json

from app.services.embeddings import EmbeddingService
from app.database import db
from prisma.models import User   # pyright: ignore[reportMissingImports]

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Service for processing and embedding documents."""
    
    def __init__(self, user: User):
        """
        Initialize document processor.
        
        Args:
            user: User model
        """
        self.user = user
        self.embedding_service = EmbeddingService()
        
        # Text splitter for chunking
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
    
    async def process_documents(
        self,
        document_ids: List[str],
        drive_service,
        is_refresh: bool = False
    ):
        """
        Process documents: fetch, chunk, embed, and store.
        
        Args:
            document_ids: List of Google document IDs
            drive_service: GoogleDriveService instance
            is_refresh: Whether this is a refresh operation
        """
        try:
            logger.info(f"Processing {len(document_ids)} documents for user: {self.user.email}")
            
            for doc_id in document_ids:
                try:
                    await self._process_single_document(doc_id, drive_service, is_refresh)
                except Exception as e:
                    logger.error(f"Failed to process document {doc_id}: {str(e)}")
                    continue
            
            logger.info(f"Completed processing {len(document_ids)} documents")
            
        except Exception as e:
            logger.error(f"Document processing failed: {str(e)}")
            raise
    
    async def _process_single_document(
        self,
        document_id: str,
        drive_service,
        is_refresh: bool
    ):
        """
        Process a single document.
        
        Args:
            document_id: Google document ID
            drive_service: GoogleDriveService instance
            is_refresh: Whether this is a refresh operation
        """
        try:
            # Get file metadata directly (avoid re-listing all files)
            logger.info(f"Fetching metadata for document: {document_id}")
            
            try:
                file_metadata = drive_service.drive_service.files().get(
                    fileId=document_id,
                    fields='id, name, mimeType'
                ).execute()
            except Exception as e:
                logger.error(f"Failed to get file metadata: {str(e)}")
                raise ValueError(f"Document {document_id} not found or inaccessible")
            
            doc_name = file_metadata.get('name', 'Untitled')
            mime_type = file_metadata.get('mimeType')
            
            logger.info(f"Fetching content for: {doc_name}")
            
            # Fetch document content
            doc_data = await drive_service.get_document_content(document_id, mime_type)
            
            # Check if document already exists
            existing_doc = await db.document.find_unique(
                where={"googleDocId": document_id}
            )
            
            if existing_doc and not is_refresh:
                logger.info(f"Document already exists: {doc_name}")
                return
            
            # Create or update document
            if existing_doc:
                # Delete old chunks
                await db.documentchunk.delete_many(
                    where={"documentId": existing_doc.id}
                )
                
                document = await db.document.update(
                    where={"id": existing_doc.id},
                    data={
                        "title": doc_data["title"],
                        "content": doc_data["content"],
                        "metadata": json.dumps(doc_data.get("metadata", {})),
                        "isProcessed": False
                    }
                )
                logger.info(f"Updated existing document: {doc_name}")
            else:
                document = await db.document.create(
                    data={
                        "userId": self.user.id,
                        "googleDocId": document_id,
                        "title": doc_data["title"],
                        "type": doc_data["type"],
                        "content": doc_data["content"],
                        "metadata": json.dumps(doc_data.get("metadata", {})),
                        "isProcessed": False
                    }
                )
                logger.info(f"Created new document: {doc_name}")
            
            # Chunk the document
            logger.info(f"Chunking document: {doc_data['title']}")
            chunks = self.text_splitter.split_text(doc_data["content"])
            
            if not chunks:
                logger.warning(f"No chunks generated for: {doc_data['title']}")
                # Mark as processed even if no chunks
                await db.document.update(
                    where={"id": document.id},
                    data={"isProcessed": True}
                )
                return
            
            logger.info(f"Generated {len(chunks)} chunks")
            
            # Generate embeddings for chunks
            logger.info(f"Generating embeddings for {len(chunks)} chunks")
            embeddings = await self.embedding_service.embed_documents(chunks)
            
            # Store chunks with embeddings
            chunks_embeddings = list(zip(chunks, embeddings))
            logger.info(f"Storing {len(chunks_embeddings)} chunks with embeddings")
            
            for idx, (chunk_text, embedding) in enumerate(chunks_embeddings):
                try:
                    # Create chunk
                    chunk = await db.documentchunk.create(
                        data={
                            "documentId": document.id,
                            "content": chunk_text,
                            "chunkIndex": idx,
                            "metadata": json.dumps({
                                "chunk_size": len(chunk_text),
                                "document_title": doc_data["title"]
                            })
                        }
                    )
                    
                    # Update embedding using raw SQL (pgvector)
                    embedding_str = "[" + ",".join(map(str, embedding)) + "]"
                    await db.execute_raw(
                        'UPDATE "DocumentChunk" SET embedding = $1::vector WHERE id = $2',
                        embedding_str,
                        chunk.id
                    )
                    
                    # Log progress every 5 chunks
                    if (idx + 1) % 5 == 0 or (idx + 1) == len(chunks_embeddings):
                        logger.info(f"Stored {idx + 1}/{len(chunks_embeddings)} chunks")
                    
                except Exception as e:
                    logger.error(f"Failed to store chunk {idx}: {str(e)}")
                    raise
            
            # Mark document as processed
            await db.document.update(
                where={"id": document.id},
                data={"isProcessed": True}
            )
            
            logger.info(f"✅ Successfully processed: {doc_data['title']} ({len(chunks_embeddings)} chunks)")
            
        except Exception as e:
            logger.error(f"Failed to process document {document_id}: {str(e)}")
            raise