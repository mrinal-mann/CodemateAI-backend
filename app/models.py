from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ENUMS

class DocumentType(str, Enum):
    """Document type enum."""
    DOCS = "DOCS"
    SHEETS = "SHEETS"
    SLIDES = "SLIDES"


class MessageRole(str, Enum):
    """Message role enum."""
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


# AUTH MODELS

class GoogleAuthURL(BaseModel):
    """Response for Google OAuth URL."""
    auth_url: str


class GoogleAuthCallback(BaseModel):
    """Request for Google OAuth callback."""
    code: str


class TokenResponse(BaseModel):
    """Response for successful authentication."""
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    """User response model."""
    id: str
    email: str
    name: Optional[str] = None
    avatar: Optional[str] = None
    createdAt: datetime
    
    class Config:
        from_attributes = True


# DOCUMENT MODELS

class GoogleDriveFile(BaseModel):
    """Google Drive file metadata."""
    id: str
    name: str
    mimeType: str
    modifiedTime: str


class GoogleDriveFilesResponse(BaseModel):
    """Response for listing Google Drive files."""
    files: List[GoogleDriveFile]


class DocumentSelectRequest(BaseModel):
    """Request to select documents for processing."""
    document_ids: List[str] = Field(..., min_items=1)


class DocumentProcessRequest(BaseModel):
    """Request to process a single document."""
    document_id: str


class DocumentResponse(BaseModel):
    """Document response model."""
    id: str
    googleDocId: str
    title: str
    type: DocumentType
    isProcessed: bool
    createdAt: datetime
    updatedAt: datetime
    
    class Config:
        from_attributes = True


class DocumentWithChunksResponse(BaseModel):
    """Document with chunks response."""
    id: str
    googleDocId: str
    title: str
    type: DocumentType
    isProcessed: bool
    chunkCount: int
    createdAt: datetime
    updatedAt: datetime


# CHAT MODELS

class ChatQueryRequest(BaseModel):
    """Request to query the chatbot."""
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    stream: bool = False


class DocumentSource(BaseModel):
    """Document source/citation."""
    documentId: str
    documentTitle: str
    documentType: str
    chunkText: str
    similarity: Optional[float] = None


class ChatQueryResponse(BaseModel):
    """Response from chatbot query."""
    answer: str
    sources: List[DocumentSource]
    session_id: str
    found_in_documents: bool


class ChatMessageResponse(BaseModel):
    """Chat message response."""
    id: str
    role: MessageRole
    content: str
    sources: Optional[List[DocumentSource]] = None
    createdAt: datetime
    
    class Config:
        from_attributes = True


class ChatSessionResponse(BaseModel):
    """Chat session response."""
    id: str
    title: str
    createdAt: datetime
    updatedAt: datetime
    messageCount: int


class ChatHistoryResponse(BaseModel):
    """Chat history response."""
    session: ChatSessionResponse
    messages: List[ChatMessageResponse]


# SUMMARIZATION MODELS

class SummarizeRequest(BaseModel):
    """Request to summarize documents."""
    document_ids: List[str] = Field(..., min_items=1)
    summary_type: str = "concise"  # concise, detailed, bullet_points
    
    @validator('summary_type')
    def validate_summary_type(cls, v):
        allowed_types = ['concise', 'detailed', 'bullet_points']
        if v not in allowed_types:
            raise ValueError(f'summary_type must be one of {allowed_types}')
        return v


class SummarizeResponse(BaseModel):
    """Response for document summarization."""
    summary: str
    documents_summarized: List[str]
    word_count: int


# ERROR MODELS

class ErrorResponse(BaseModel):
    """Error response model."""
    error: str
    detail: Optional[str] = None
    status_code: int


class SuccessResponse(BaseModel):
    """Generic success response."""
    message: str
    data: Optional[Dict[str, Any]] = None


# HEALTH CHECK MODELS

class HealthCheckResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    database: str
    timestamp: datetime