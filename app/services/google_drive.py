from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List, Dict, Any, Optional
import logging

from app.config import settings
from app.models import GoogleDriveFile, DocumentType
from prisma.models import User # pyright: ignore[reportMissingImports]

logger = logging.getLogger(__name__)


class GoogleDriveService:
    """Service to interact with Google Drive API."""
    
    # MIME types for Google Workspace files
    MIME_TYPES = {
        "DOCS": "application/vnd.google-apps.document",
        "SHEETS": "application/vnd.google-apps.spreadsheet",
        "SLIDES": "application/vnd.google-apps.presentation",
    }
    
    def __init__(self, user: User):
        self.user = user
        self.credentials = self._get_credentials()
        self.drive_service = build('drive', 'v3', credentials=self.credentials)
        self.docs_service = build('docs', 'v1', credentials=self.credentials)
        self.sheets_service = build('sheets', 'v4', credentials=self.credentials)
        self.slides_service = build('slides', 'v1', credentials=self.credentials)
    
    def _get_credentials(self) -> Credentials:
        if not self.user.accessToken:
            raise ValueError("User has no access token")
        
        return Credentials(
            token=self.user.accessToken,
            refresh_token=self.user.refreshToken,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )
    
    async def list_files(self) -> List[GoogleDriveFile]:
        try:
            # Build query for Google Workspace files
            mime_type_query = " or ".join([
                f"mimeType='{mime_type}'"
                for mime_type in self.MIME_TYPES.values()
            ])
            
            query = f"({mime_type_query}) and trashed=false"
            
            # Fetch files from Drive
            results = self.drive_service.files().list(
                q=query,
                pageSize=100,
                fields="files(id, name, mimeType, modifiedTime)",
                orderBy="modifiedTime desc"
            ).execute()
            
            files = results.get('files', [])
            
            # Convert to GoogleDriveFile models
            drive_files = [
                GoogleDriveFile(
                    id=file['id'],
                    name=file['name'],
                    mimeType=file['mimeType'],
                    modifiedTime=file['modifiedTime']
                )
                for file in files
            ]
            
            logger.info(f"Listed {len(drive_files)} files for user: {self.user.email}")
            
            return drive_files
            
        except HttpError as e:
            logger.error(f"Google Drive API error: {str(e)}")
            raise Exception(f"Failed to list files: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to list files: {str(e)}")
            raise
    
    async def get_document_content(self, document_id: str, mime_type: str) -> Dict[str, Any]:
        try:
            if mime_type == self.MIME_TYPES["DOCS"]:
                return await self._get_docs_content(document_id)
            elif mime_type == self.MIME_TYPES["SHEETS"]:
                return await self._get_sheets_content(document_id)
            elif mime_type == self.MIME_TYPES["SLIDES"]:
                return await self._get_slides_content(document_id)
            else:
                raise ValueError(f"Unsupported MIME type: {mime_type}")
                
        except HttpError as e:
            logger.error(f"Failed to get document content: {str(e)}")
            raise Exception(f"Failed to fetch document: {str(e)}")
        except Exception as e:
            logger.error(f"Error getting document content: {str(e)}")
            raise
    
    async def _get_docs_content(self, document_id: str) -> Dict[str, Any]:
        try:
            document = self.docs_service.documents().get(documentId=document_id).execute()
            
            title = document.get('title', 'Untitled')
            content = self._extract_text_from_docs(document)
            
            return {
                "title": title,
                "content": content,
                "type": DocumentType.DOCS,
                "metadata": {
                    "documentId": document_id,
                    "mimeType": self.MIME_TYPES["DOCS"]
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get Docs content: {str(e)}")
            raise
    
    def _extract_text_from_docs(self, document: Dict[str, Any]) -> str:
        text_parts = []
        
        body = document.get('body', {})
        content = body.get('content', [])
        
        for element in content:
            if 'paragraph' in element:
                paragraph = element['paragraph']
                elements = paragraph.get('elements', [])
                
                for elem in elements:
                    if 'textRun' in elem:
                        text_content = elem['textRun'].get('content', '')
                        text_parts.append(text_content)
            
            elif 'table' in element:
                table = element['table']
                for row in table.get('tableRows', []):
                    for cell in row.get('tableCells', []):
                        for cell_content in cell.get('content', []):
                            if 'paragraph' in cell_content:
                                paragraph = cell_content['paragraph']
                                for elem in paragraph.get('elements', []):
                                    if 'textRun' in elem:
                                        text_content = elem['textRun'].get('content', '')
                                        text_parts.append(text_content)
        
        return ''.join(text_parts).strip()
    
    async def _get_sheets_content(self, spreadsheet_id: str) -> Dict[str, Any]:
        try:
            spreadsheet = self.sheets_service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            
            title = spreadsheet.get('properties', {}).get('title', 'Untitled')
            sheets = spreadsheet.get('sheets', [])
            
            content_parts = []
            
            for sheet in sheets:
                sheet_title = sheet.get('properties', {}).get('title', 'Sheet')
                content_parts.append(f"\n## {sheet_title}\n")
                
                # Get sheet data
                range_name = f"'{sheet_title}'!A1:Z1000"  # Adjust range as needed
                
                result = self.sheets_service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name
                ).execute()
                
                values = result.get('values', [])
                
                if values:
                    # Convert rows to text
                    for row in values:
                        row_text = ' | '.join([str(cell) for cell in row])
                        content_parts.append(row_text)
            
            content = '\n'.join(content_parts).strip()
            
            return {
                "title": title,
                "content": content,
                "type": DocumentType.SHEETS,
                "metadata": {
                    "spreadsheetId": spreadsheet_id,
                    "mimeType": self.MIME_TYPES["SHEETS"],
                    "sheetCount": len(sheets)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get Sheets content: {str(e)}")
            raise
    
    async def _get_slides_content(self, presentation_id: str) -> Dict[str, Any]:
        try:
            presentation = self.slides_service.presentations().get(
                presentationId=presentation_id
            ).execute()
            
            title = presentation.get('title', 'Untitled')
            slides = presentation.get('slides', [])
            
            content_parts = []
            
            for idx, slide in enumerate(slides, 1):
                content_parts.append(f"\n## Slide {idx}\n")
                
                # Extract text from slide elements
                page_elements = slide.get('pageElements', [])
                
                for element in page_elements:
                    if 'shape' in element:
                        shape = element['shape']
                        if 'text' in shape:
                            text_content = self._extract_text_from_shape(shape['text'])
                            if text_content:
                                content_parts.append(text_content)
                    
                    elif 'table' in element:
                        table = element['table']
                        for row in table.get('tableRows', []):
                            for cell in row.get('tableCells', []):
                                if 'text' in cell:
                                    text_content = self._extract_text_from_shape(cell['text'])
                                    if text_content:
                                        content_parts.append(text_content)
            
            content = '\n'.join(content_parts).strip()
            
            return {
                "title": title,
                "content": content,
                "type": DocumentType.SLIDES,
                "metadata": {
                    "presentationId": presentation_id,
                    "mimeType": self.MIME_TYPES["SLIDES"],
                    "slideCount": len(slides)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get Slides content: {str(e)}")
            raise
    
    def _extract_text_from_shape(self, text_structure: Dict[str, Any]) -> str:
        text_parts = []
        
        text_elements = text_structure.get('textElements', [])
        
        for element in text_elements:
            if 'textRun' in element:
                text_content = element['textRun'].get('content', '')
                text_parts.append(text_content)
        
        return ''.join(text_parts).strip()
    
    def get_document_type(self, mime_type: str) -> DocumentType:

        if mime_type == self.MIME_TYPES["DOCS"]:
            return DocumentType.DOCS
        elif mime_type == self.MIME_TYPES["SHEETS"]:
            return DocumentType.SHEETS
        elif mime_type == self.MIME_TYPES["SLIDES"]:
            return DocumentType.SLIDES
        else:
            raise ValueError(f"Unsupported MIME type: {mime_type}")